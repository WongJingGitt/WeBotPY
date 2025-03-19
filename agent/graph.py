from typing import TypedDict, List, Union, Any
from os import getenv
from json import dumps

from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.types import Command, Send
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_core.messages import HumanMessage
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
        self._graph.add_node('tool_agent', self._tool_agent)
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
        # print(response)
        return Command(goto=END, update=state)

    def _plan_agent(self, state: BaseState):
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
            state['plan'] = self._parser.parse(_result)
            return Command(goto="execute_tool_agent", update=state)
        except Exception as e:
            raise PlanGenerationError(f"{e}")

    # TODO: 灵感阻塞，敲不出来，打个火锅去先
    def _execute_tool_agent(self, state: BaseState):
        plan = state['plan']
        _agent = create_react_agent(
            model=LLMFactory.llm(model_name=state['model_name'], **state['llm_options']),
            prompt=f"""
你是一位专业的任务执行大师，你会接收到一个包含若干步骤的执行计划，你需要根据这个计划，执行每一个步骤，具体要求如下：

## 返回格式要求：
    1. 你需要返回一个JSON格式的内容，格式如下：
    {{
        "completed_steps": [0, 1, 2], // 记录已完成步骤的列表，存放的内容为`step_id`,
        "last_step_id": 3, // 最后一次执行的步骤ID，在每执行完一个步骤，你都要更新这个字段，以便出错时进行快速重试。"
        "result": [ // 记录每个步骤的执行结果
            {{
                "step_id": 0,   // 步骤的唯一标识符，用于标识当前步骤在任务中的顺序和引用。
                "status": "success", // 当前步骤的执行结果状态，仅允许三个值：success/error/pending，其中
                "output": {{}}, // 当前步骤的输出结果，格式为字典，根据工具函数的返回值进行解析。
                "error": ""  // 当前步骤的错误信息，如果步骤执行成功，则该字段为空。
                "clarification": ""  // 如若需要用户澄清时，展示给用户的的澄清信息，不需要澄清则为空。
                "user_feedback": ""  // 基于澄清步骤，用户返回的结果，在用户回馈之后再补充进来。
                "decision_log": ""  // 基于当前步骤决策的日志，用于记录当前步骤的决策过程。
            }}
        ], 
    }}

## 步骤字段解释：
    {{
        "step_id": 2, // 步骤的唯一标识符，用于标识当前步骤在任务中的顺序和引用。
        "description": "xxx", // 对当前步骤的简要描述，这里的内容将会显示给用户，帮助用户理解该步骤的目的和任务。
        "tool": "get_weather", // 执行该步骤所调用的工具函数名称。
        "input": {{ }}, // 调用工具函数时所需要的输入参数，格式为字典。
        "depends_on": [1], // 该步骤依赖的其他步骤的ID列表，用于定义执行顺序和依赖关系。
        "clarification": "", // 当该步骤可能需要用户澄清或确认时，对应的提示信息参考，你需要根据这个字段进行拓展描述返回给用户。例如：get_contact获取到了多个联系人时对应的提示信息。
        "decision_required": "", // 描述该步骤中可能需要你进行推理或自主决策的内容。例如：根据get_current_time函数结果推断昨天的具体日期。
    }}
""",
            tools=ALL_TOOLS,
        )
        try:
            input_message = MessagesState(messages=[HumanMessage(content=dumps(plan))])
            print(input_message)
            response = _agent.stream(input_message, config={"configurable": {"thread_id": 42}}, stream_mode='updates')
            for item in response:
                print(item)
            # _result = self._parser.parse(response.get('messages')[-1].content)
            # print(_result)
            return Command(goto=END, update=state)
        except Exception as e:
            raise ExecuteToolError(f"{e}")


    def _tool_agent(self, state: BaseState):
        _prompt = """
这是一个测试对话，不管用户输入什么，请你按一下格式回复：
输入：用户的原始数据。
输出：模拟tool输出
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


# TODO：
#   重新规划整体的Agent架构，结合StateGraph实现多Agent协同
#   创建聊天记录拆分Agent，传入主Prompt，根据主Prompt提取关键信息，最后创建专门用作总结的Agent，把所有分批次总结的Prompt聚合起来总结最终的报告。以规避API输入长度限制的问题。
#   需要动态配置各个节点的模型使用，兼容全局使用一个模型或者每个步骤单独使用模型的场景。例如：任务规划师使用高参数模型，原子任务执行师使用低参数模型（需要考虑每分钟调用上限？？？）

if __name__ == '__main__':
    graph = Graph()
    _agent = graph.agent
    result = _agent.invoke(
        {
            "messages": MessagesState(messages=[HumanMessage(
                content="请帮我根据群聊：人生何处不青山，昨天早上8点到中午12点的聊天记录，总结一下大家都在聊什么话题，按热度进行降序展示TOP10")]),
            # "model_name": "deepseek-v3-241226",
            # "llm_options": {
            #     "apikey": getenv('VOLCENGINE_API_KEY'),
            #     "base_url": 'https://ark.cn-beijing.volces.com/api/v3/'
            # },
            "model_name": "gemini-2.0-flash-exp",
            "llm_options": {
                "apikey": getenv("GEMINI_API_KEY"),
                "base_url": ""
            },
            # "model_name": "doubao-1-5-pro-32k-250115",
            # "llm_options": {
            #     "apikey": getenv('VOLCENGINE_API_KEY'),
            #     "base_url": 'https://ark.cn-beijing.volces.com/api/v3/'
            # },
            # "webot_port": 19001
        },
        config={"configurable": {"thread_id": 42}},
        stream_mode=['updates']
    )