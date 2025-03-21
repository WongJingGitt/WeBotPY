from typing import TypedDict, List, Union, Any
from os import getenv
from json import dumps

from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.types import Command, Send, interrupt
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.pregel import RetryPolicy
from langchain_core.output_parsers import JsonOutputParser
from sqlite3 import connect
from dotenv import load_dotenv

from llm.llm import LLMFactory
from utils.project_path import DATA_PATH, path
from tool_call.tools import ALL_TOOLS
from graph_types import StepItemModel, PlanResult, ExecuteToolError, PlanGenerationError

load_dotenv()


class BaseState(TypedDict):
    messages: MessagesState
    model_name: str
    llm_options: dict
    webot_port: int
    plan: List[StepItemModel]
    current_step_id: int
    next_step_id: Union[int, None]
    plan_result: List[PlanResult]
    final_result: Any
    plan_retry_count: int
    plan_retry_description: str


class Graph:

    def __init__(self):
        checkpointer_database_path = path.join(DATA_PATH, 'databases', 'checkpoint.db')
        self._checkpointer = SqliteSaver(
            conn=connect(
                database=checkpointer_database_path,
                check_same_thread=False
            )
        )

        self._parser = JsonOutputParser()

        self._graph = StateGraph(BaseState)

        self._graph.add_node('main_agent', self._main_agent)
        self._graph.add_node('chat_agent', self._chat_agent)
        self._graph.add_node('plan_agent', self._plan_agent, retry=RetryPolicy(retry_on=PlanGenerationError))
        self._graph.add_node('execute_tool_agent', self._execute_tool_agent, retry=RetryPolicy(retry_on=ExecuteToolError))
        self._graph.add_conditional_edges(START, self._main_agent, ['chat_agent', 'plan_agent'])
        self._agent = self._graph.compile(checkpointer=self._checkpointer)

    @property
    def agent(self):
        return self._agent

    def get_tools_description(self, with_args=False):
        _description = ''
        for item in ALL_TOOLS:
            _description += f"函数名：{item.name}\n描述 ：{item.description}\n"
            if with_args:
                _description += f"接收参数：{item.args}\n"
            _description += '=' * 10 + '\n'
        return _description

    def _main_agent(self, state: BaseState) -> Send:
        _prompt = f"""
你是一位专业的意图分析大师，专责对用户输入进行精准意图判断。请严格按照以下规则执行：
1. 分析用户输入，判断是否涉及工具调用需求。
2. 若用户意图仅为闲聊，回复固定文本“chat”；若涉及工具调用，回复固定文本“tool”。
3. 回复内容仅限“chat”或“tool”，不能包含任何其他说明或多余信息。
4. 你只负责意图分析，不负责调用工具或处理工具结果。工具函数信息请参照：
    {self.get_tools_description()}
5. 若用户输入包含混合意图或不明确情况，则优先判断是否存在工具调用需求，存在则回复“tool”，否则回复“chat”。
6. 必须确保决策稳定、一致，对相似输入始终输出相同结果，避免因细微差异导致随机响应。
"""
        _llm = LLMFactory.llm(model_name=state['model_name'], **state['llm_options'])
        _agent = create_react_agent(
            model=_llm,
            prompt=_prompt,
            tools=[]
        )
        response = _agent.invoke(state['messages'], config={"configurable": {"thread_id": 42}})
        # print(response.get('messages')[-1].content)
        if response.get('messages')[-1].content == 'chat':
            print("CHAT AGENT 调用")
            return Send('chat_agent', state)
        elif response.get('messages')[-1].content == 'tool':
            print("PLAN AGENT 调用")
            return Send('plan_agent', state)
        else:
            print("CHAT AGENT 调用")
            return Send('chat_agent', state)

    def _chat_agent(self, state: BaseState):

        _prompt = f"""
你是一个微信机器人助手，你的职责是结合工具函数的描述解答用户任何问题，你的具体职责如下：
1. 你主要负责解答用户的任何问题，不论有没有涉及到工具函数的描述。
2. 当用户的问题涉及到工具函数时，你需要结合工具函数来解答用户的疑问。
3. 你仅负责回答用户的问题，不需要调用任何工具函数。

## 支持的工具函数：
{self.get_tools_description(with_args=True)}
    """
        _llm = LLMFactory.llm(model_name=state['model_name'], **state['llm_options'])
        _agent = create_react_agent(
            model=_llm,
            prompt=_prompt,
            tools=[]
        )
        response = _agent.invoke(state['messages'])
        state['messages']['messages'].append(response)
        return Command(goto=END, update=state)

    def _plan_agent(self, state: BaseState):
        if not state.get('plan_retry_count'): state['plan_retry_count'] = 0
        if state['plan_retry_count'] > 3:
            state['final_result'] = "抱歉，我无法理解您的意图。请重新输入。"
            return Command(goto=END, update=state)
        plan_retry_description = state.get('plan_retry_description')
        if plan_retry_description:
            state['messages']['messages'].append(HumanMessage(content=plan_retry_description))
        _prompt = f"""
你是一位专业的任务规划大师，你的主要职责是：

## 背景信息：
    - 当前的微信prot：{state['webot_port']}

## 核心职责:
    1. 根据用户的输入，判断用户的核心意图。
    2. 根据用户的意图，结合工具函数描述给出一份任务规划。

## 输出要求:
    1. 你必须输出一个多维数组形式的计划。
    2. 以下数组中步骤字典的描述：
        {{
            "step_id": 2, // 步骤的唯一标识符，用于标识当前步骤在任务中的顺序和引用。
            "description": "xxx", // 对当前步骤的简要描述，这里的内容将会显示给用户，帮助用户理解该步骤的目的和任务。
            "tool": "get_weather", // 执行该步骤所调用的工具函数名称。
            "input": {{ }}, // 调用工具函数时所需要的输入参数，格式为字典。
            "depends_on": [1], // 该步骤依赖的其他步骤的ID列表，用于定义执行顺序和依赖关系。
            "clarification": "", // 当该步骤可能需要用户澄清或确认时，提供相应提示信息。
            "decision_required": "", // 描述该步骤中可能需要模型推理或任务执行专家进行自主决策的内容。
        }}
    3. 示例：假设用户输入，帮我总结一下昨天我和吴彦祖的聊天中最后的决定的行程安排，然后转发给小王，并且提醒他根据形成订好机票。
            [
                {{
                    "step_id": 1,
                    "description": "获取当前系统时间确定时间范围",
                    "tool": "get_current_time",
                    "input": {{"port": 19001}},
                    "depends_on": [],
                    "clarification": "",
                    "decision_required": "根据当前时间自动推算昨日时间区间"
                }},
                {{
                    "step_id": 2,
                    "description": "检索联系人「吴彦祖」的wxid",
                    "tool": "get_contact",
                    "input": {{"port": 19001, "keyword": "吴彦祖"}},
                    "depends_on": [],
                    "clarification": "发现3个匹配联系人，请确认是否需要选择第一个结果",
                    "decision_required": "自动选择匹配度最高的结果"
                }},
                {{
                    "step_id": 3,
                    "description": "提取昨日指定时段的聊天记录",
                    "tool": "get_message_by_wxid_and_time",
                    "input": {{
                        "port": 19001,
                        "wxid": "$2.wxid", 
                        "start_time": "$1.current_time_format.split()[0] + ' 00:00:00' - 1day",
                        "end_time": "$1.current_time_format.split()[0] + ' 23:59:59' - 1day"
                    }},
                    "depends_on": [1,2],
                    "clarification": "",
                    "decision_required": "时间表达式自动转换逻辑"
                }},
                {{
                    "step_id": 4,
                    "description": "智能分析聊天关键决策点",
                    "tool": "",
                    "input": {{"messages": "$3.data"}},
                    "depends_on": [3],
                    "clarification": "检测到5处可能行程安排，请确认最终版本",
                    "decision_required": "自然语言理解模型执行摘要生成"
                }},
                {{
                    "step_id": 5,
                    "description": "定位联系人「小王」的wxid",
                    "tool": "get_contact",
                    "input": {{"port": 19001, "keyword": "小王"}},
                    "depends_on": [],
                    "clarification": "",
                    "decision_required": "昵称模糊匹配算法"
                }},
                {{
                    "step_id": 6,
                    "description": "发送行程摘要至目标联系人",
                    "tool": "send_text_message",
                    "input": {{
                        "port": 19001,
                        "wxid": "$5.wxid",
                        "message": "最终行程安排：\n$4.summary"
                    }},
                    "depends_on": [4,5],
                    "clarification": "",
                    "decision_required": "消息模板自动生成策略"
                }},
                {{
                    "step_id": 7,
                    "description": "追加机票预订提醒",
                    "tool": "send_text_message",
                    "input": {{
                        "port": 19001,
                        "wxid": "$5.wxid",
                        "message": "请依据上述行程尽快预订机票，出发前72小时我会再次提醒"
                    }},
                    "depends_on": [6],
                    "clarification": "",
                    "decision_required": "提醒时机智能推算"
                }}
            ]

## 支持的工具函数：
    {self.get_tools_description(with_args=True)}
"""
        _llm = LLMFactory.llm(model_name=state['model_name'], **state['llm_options'])
        _agent = create_react_agent(
            model=_llm,
            prompt=_prompt,
            tools=[],
        )
        try:
            response = _agent.invoke(state['messages'], config={"configurable": {"thread_id": 42}})
            _result = response.get('messages')[-1].content
            state['plan'] = [StepItemModel(**item) for item in self._parser.parse(_result)]
            return Command(goto="execute_tool_agent", update=state)
        except Exception as e:
            raise PlanGenerationError(f"{e}")


    def _execute_tool_agent(self, state: BaseState):
        """
        [
            StepItemModel(step_id=1, description='获取当前系统时间确定昨天的时间范围', tool='get_current_time', input={'port': 19001}, depends_on=[], clarification='', decision_required='根据当前时间自动推算昨天的日期，并拼接出早上8点和中午12点的时间格式'), 
            StepItemModel(step_id=2, description='检索群聊「人生何处不青山」的wxid', tool='get_contact', input={'port': 19001, 'keyword': '人生何处不青山'}, depends_on=[], clarification='若发现多个匹配群聊，请确认是否需要选择第一个结果', decision_required='自动选择匹配度最高的结果'), 
            StepItemModel(step_id=3, description='提取指定群聊在昨天早上8点到中午12点的聊天记录', tool='get_message_by_wxid_and_time', input={'port': 19001, 'wxid': '$2.wxid', 'start_time': "$1.current_time_format.split()[0] + ' 08:00:00' - 1day", 'end_time': "$1.current_time_format.split()[0] + ' 12:00:00' - 1day"}, depends_on=[1, 2], clarification='', decision_required='时间表达式自动转换逻辑'), 
            StepItemModel(step_id=4, description='智能分析聊天记录话题热度，并展示TOP10话题', tool='', input={'messages': '$3.data'}, depends_on=[3], clarification='若话题数量不足10个，将展示全部话题', decision_required='自然语言处理模型进行话题提取和热度统计')
        ]
        """
        try:
            plan = state['plan']
            print(plan)
            plan_result = state.get('plan_result', []) 
            current_step_id = state.get('current_step_id') or plan[0].step_id
            current_step = ([item for item in plan if item.step_id == current_step_id] or [None])[0]
            
            if not current_step:
                return Command(goto="plan_agent", update=state)
            
            # TODO : 逻辑待完成，使用原子任务执行专家方案，这个函数应该专注于执行单个任务，遍历工作需要另外用工具负责


            _prompt = f"""
    你是一个专业的工作流执行专家，专注于任务的执行，具体说明如下：

    ## 当前你需要执行的任务是：
        {current_step.description}

    ## 你需要使用以下工具函数来执行任务：
        **需要调用的工具函数**：{current_step.tool}
        **需要传递的参数**：{current_step.input}

    ## 依赖说明：

    """
            
            return Command(goto=END, update=state)
        except Exception as e:
            state['plan_retry_count'] += 1
            state['plan_retry_description'] = f"你制定的任务执行时出选了以下错误: \n\n{e}\n\n 你上次做出的规划是：\n\n{plan}\n\n现在请你重新规划任务"
            return Command(goto="plan_agent", update=state)


# TODO：
#   重新规划整体的Agent架构，结合StateGraph实现多Agent协同
#   创建聊天记录拆分Agent，传入主Prompt，根据主Prompt提取关键信息，最后创建专门用作总结的Agent，把所有分批次总结的Prompt聚合起来总结最终的报告。以规避API输入长度限制的问题。
#   需要动态配置各个节点的模型使用，兼容全局使用一个模型或者每个步骤单独使用模型的场景。例如：任务规划师使用高参数模型，原子任务执行师使用低参数模型（需要考虑每分钟调用上限？？？）

if __name__ == '__main__':
    with open(r"D:/wangyingjie/WeBot/data/exports/上海交大🇨🇳人生何处不青山__2025-03-11_13-34-19.txt", "r", encoding='utf-8') as f:
        content = f.read()
    graph = Graph()
    _agent = graph.agent
    result = _agent.invoke(
        {
            "messages": MessagesState(messages=[
                HumanMessage(content="请帮我根据群聊：人生何处不青山，3月11日的聊天记录，总结一下大家都在聊什么话题，按热度进行降序展示TOP10"),
                AIMessage(content=f"好的，我已经获取到了3月11日的聊天记录：\n\n{content}"),
                AIMessage(content="""
根据聊天记录的内容，以下是按讨论热度降序排列的TOP10话题总结：

**1. 红包互动**  
• 高频出现"谢谢红包"及抢红包调侃  
• 涉及金额、专属红包争议、流量抱怨  
• 典型案例：甜辣小团子连续5次感谢红包

**2. 线下见面与火锅计划**  
• 刘心奶黄包与星星讨论约饭细节  
• 群友调侃"日不到也不准别人日"  
• 延伸至"车震""乱伦"等成人玩笑

**3. 男女关系与成人话题**  
• 高频提及"少妇""出轨""约炮"  
• 包含"干姐姐""酒店过夜"等隐喻  
• 典型案例：余余总结"四次约会发展论"

**4. 工作与薪资讨论**  
• 抱怨上班状态（"脸青口唇白"）  
• 询问发工资时间  
• 调侃"摸鱼"与放假诉求

**5. 咖啡/奶茶社交邀请**  
• 墨轩与美味猫堡互相@请客  
• 延伸至金额调侃（"9块9自己买"）  
• 引发群友集体"求请喝"

**6. 群友互怼与网络暴力**  
• 攻击性言论："废物""小三""狐狸精"  
• 威胁踢人、版本过低无法互动  
• 典型案例：呆呆魚指控老公发红包

**7. 时事新闻热议**  
• 摸鱼早报提及女性就业歧视、微信视频升级  
• 涉及国际局势（波兰核武、叙利亚内乱）  
• 但讨论深度较浅，多作为话题引子

**8. 群规管理争议**  
• 止初威胁清理"僵尸成员"  
• 关于红包专属权限的争论  
• 多次出现"踢人"相关发言

**9. 表情包文化**  
• 共出现17次[动画表情]  
• 用于缓解冲突、表达情绪  
• 典型案例：NPC连续发表情打断对话

**10. 地域交通吐槽**  
• 涉及龙华、蜀山、包河等地点  
• 抱怨堵车（"堵的皮爆"）  
• 讨论地铁线路与通勤时间

**注**：话题热度综合考量了讨论次数、参与人数、互动激烈程度及话题延展性。成人向内容虽出现频率高，但因部分涉及隐喻未列更高位。
"""),
                HumanMessage(content="那请你再看下谁最活跃？")
            ]),
            "model_name": "deepseek-v3-241226",
            "llm_options": {
                "apikey": getenv('VOLCENGINE_API_KEY'),
                "base_url": 'https://ark.cn-beijing.volces.com/api/v3/'
            },
            # "model_name": "gemini-2.0-flash-exp",
            # "llm_options": {
            #     "apikey": getenv("GEMINI_API_KEY"),
            #     "base_url": ""
            # },
            # "model_name": "doubao-1-5-pro-32k-250115",
            # "llm_options": {
            #     "apikey": getenv('VOLCENGINE_API_KEY'),
            #     "base_url": 'https://ark.cn-beijing.volces.com/api/v3/'
            # },
            "webot_port": 19001
        },
        config={"configurable": {"thread_id": 42}},
        # stream_mode=['updates']
    )

    print(result)