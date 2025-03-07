import json
from typing import List, Dict

from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, BaseMessage
from langchain_text_splitters.json import RecursiveJsonSplitter

from agent.agent_types import StepItem, PlannerResult
from llm.llm import LLMFactory
from tool_call.tools import ALL_TOOLS


# TODO:
#   执行师不会执行JSON格式的任务，需要考虑计划师的输出格式，考虑输出自然语言，并且指示执行师需要执行推理或者询问用户。
class PlannerAgent:
    def __init__(self, mode_name: str = "glm-4-flash", llm_options: dict = {}, webot_port: int = 19001):
        self.port = webot_port
        self.llm = {
            "glm-4-flash": LLMFactory.glm_llm(**llm_options),
            "gemini-2.0-flash-exp": LLMFactory.gemini_llm(**llm_options),
            "deepseek-v3-aliyun": LLMFactory.aliyun_deepseek_llm(**llm_options),
            "deepseek-r1-aliyun": LLMFactory.aliyun_deepseek_r1_llm(**llm_options)
        }.get(mode_name, LLMFactory.glm_llm())

        self.checkpoint = MemorySaver()
        self.agent = create_react_agent(
            model=self.llm,
            checkpointer=self.checkpoint,
            prompt=SystemMessage(
                content=self.prompt
            ),
            tools=[],
        )

    @property
    def prompt(self):
        tools_description = ""
        for _tool in ALL_TOOLS:
            function_name = _tool.name
            args = [
                f"\n---\n-参数名：{arg_name}\n-参数类型：{arg_value.annotation}\n-必填：{arg_value.is_required()}\n-描述：{arg_value.description}"
                for arg_name, arg_value in _tool.args_schema.model_fields.items()]
            tools_description = tools_description + f"""
函数名：{function_name}
函数描述：
{_tool.description}
参数：
{''.join(args)[5:] or "无"}

"""

        _prompt = f"""
你是一个微信智能助手的**任务规划专家**，负责将用户需求拆解为可执行的分步操作，提供给**任务执行专家**进行执行。请严格按照以下规则操作：

### 微信Port说明：
- **当前微信的Port**：`{self.port}`，当工具函数中需要微信的Port时，请传入此值。

### 可用工具列表（按需调用）：
{tools_description}

### 任务规划规则：
1. **步骤顺序**：
   - 必须先调用 `get_contact` 确认联系人存在。
   - 涉及聊天记录时，必须先调用 `get_message_by_wxid_and_time` 获取数据。
   - 时间推断需优先调用 `get_current_time`，通过现在的时间推断用户表达的意图。（如用户提到“明天”、“下周”、“2.5-2.6”）。
2. **参数传递**：
   - 从历史步骤结果中提取参数（如 `wxid` 必须来自 `get_contact` 的结果列表）。
   - 时间范围需转换为 `time_range` 格式（如“最近三天” → `"time_range": "3d"`）。
3. **错误预防**：
   - 若用户提供的关键字获取到多个联系人，必须添加用户人工确认步骤。
   - 若时间描述模糊（如“尽快”），需调用 `get_current_time` 辅助推断。

### 输出要求（严格 JSON 格式）：
{{
  "status": "IN_PROGRESS | COMPLETED | NEED_CLARIFICATION",
  "steps": [
    {{
      "step_id": 1,
      "description": "步骤描述（显示给用户）",
      "tool": "工具名",
      "input": {{参数}},
      "depends_on": []  // 依赖的步骤ID（可选）,
      "clarification": "可能会涉及到需要用户澄清的内容（如有）",
      "decision_required": "可能会需要任务执行专家进行自主推理和决策的内容（如有）"
    }}
  ]
}}

### 示例：
用户输入："看下深圳兼职群这两天都发了什么工作"
输出：
{{
  "status": "IN_PROGRESS",
  "steps": [
    {{
      "step_id": 1,
      "description": "查找包含“深圳兼职群”关键字的联系人",
      "tool": "get_contact",
      "input": {{
        "port": {self.port},
        "keyword": "深圳兼职群"
      }},
      "depends_on": [],
      "clarification": "如果找到了多个联系人，需用户确认选择",
      "decision_required": ""
    }},
    {{
      "step_id": 2,
      "description": "获取当前时间，推断过去两天的时间范围",
      "tool": "get_current_time",
      "input": {{}},
      "depends_on": [],
      "clarification": "",
      "decision_required": "推断过去两天的具体时间范围。"
    }},
    {{
      "step_id": 3,
      "description": "获取深圳兼职群的聊天记录，查询过去两天发布的工作内容",
      "tool": "get_message_by_wxid_and_time",
      "input": {{
        "port": {self.port},
        "wxid": "{{步骤1输出的wxid}}",
        "start_time": "{{根据步骤2输出的，当前时间推断出的时间范围}}",
        "end_time": "{{根据步骤2输出的，当前时间推断出的时间范围}}"
      }},
      "depends_on": [1, 2],
      "clarification": "",
      "decision_required": "总结并提取聊天记录中的岗位信息。"
    }}
  ]
}}

"""
        return _prompt

    def chat(self, message):
        return self.agent.invoke(message, config={"configurable": {"thread_id": 41}})


class TaskExecutorAgent:
    def __init__(self, mode_name: str = "glm-4-flash", llm_options: dict = {},
                 current_step: StepItem = None, plan: PlannerResult = None, webot_port: int = 19001, *args, **kwargs):
        self.llm = {
            "glm-4-flash": LLMFactory.glm_llm(**llm_options),
            "gemini-2.0-flash-exp": LLMFactory.gemini_llm(**llm_options),
            "deepseek-v3-aliyun": LLMFactory.aliyun_deepseek_llm(**llm_options),
            "deepseek-r1-aliyun": LLMFactory.aliyun_deepseek_r1_llm(**llm_options)
        }.get(mode_name, LLMFactory.glm_llm())

        self.agent = create_react_agent(
            model=self.llm,
            tools=ALL_TOOLS,
            prompt=SystemMessage(
                content=f"""
你是一个微信智能助手的**任务执行专家**”，主要负责调用相关的工具函数，将任务执行并且落地。
- 当前微信的Port为{webot_port}

## 流程简介：
1. 你会收到一份由任务规划专家给到的任务计划，其中包含若干个步骤。
2. 你需要根据步骤中提到的工具函数，按照顺序依次执行。
3. 遵循相关的步骤依赖计划，按需传递参数

## 核心原则：
1. 必须优先保证工具函数被正确的执行，包括函数的执行与参数传递。
"""
            ),
            checkpointer=MemorySaver()
        )

    def chat(self, message):
        return self.agent.stream(message, config={"configurable": {"thread_id": 40}}, stream_mode=['updates'])


class WeBotAgent:

    def __init__(self, model_name: str = "glm-4-flash", llm_options: dict = {}, webot_port: int = 19001):
        # TODO: 增加了模型数据库，需要优化这里的逻辑
        self.llm = {
            "glm-4-flash": LLMFactory.glm_llm(**llm_options),
            "gemini-2.0-flash-exp": LLMFactory.gemini_llm(**llm_options),
            "deepseek-v3-aliyun": LLMFactory.aliyun_deepseek_llm(**llm_options),
            "deepseek-r1-aliyun": LLMFactory.aliyun_deepseek_r1_llm(**llm_options),
            "qwen2.5": LLMFactory.aliyun_qwen2_5_14b_llm(**llm_options),
            "deepseek_v3": LLMFactory.deepseek_v3_llm(**llm_options)
        }.get(model_name, LLMFactory.glm_llm())

        self.checkpoint = MemorySaver()

        self.agent = create_react_agent(
            model=self.llm,
            tools=ALL_TOOLS,
            checkpointer=self.checkpoint,
            prompt=SystemMessage(
                content=f"""
你是一个基于AI的微信机器人助手，通过工具函数从微信客户端获取信息。  
请严格按照以下规则操作：

1. **说明**  
   - **微信Port：**使用 `{webot_port}` 作为微信Port参数。
   - **工具函数使用规范：**注意结合实际场景调用工具函数，例如：
        - `get_message_by_wxid_and_time`用于获取聊天记录字典（主要供模型二次分析，不供用户直接使用）；
        - `export_message`用于将聊天记录导出为本地文件，当用户要求导出、提取或下载聊天记录时应调用此函数。

2. **工作流程**  
   - **意图识别与信息提取**：准确捕捉用户意图，提取关键数据（如时间、联系人、群聊等）。  
   - **方案规划与执行**：根据需求分步调用工具函数（如：先调用 `get_current_time` 获取当前时间，再计算时间区间，后续调用其它函数）。  
   - **状态反馈**：每一步操作后立即反馈结果，并且描述当前操作内容；如遇失败，重试或提示用户手动操作。  
   - **总结返回**：任务结束后，用Markdown格式总结并反馈操作结果（成功或失败及解决方案）。

3. **数据要求**  
   - 返回的信息必须来自工具函数获取，严禁编造数据。
   - 多个联系人需要用户二次确认时，需要带上名称、备注与wxid。

4. **错误处理**  
   - 工具函数调用失败时返回错误信息并重试；如多次失败，则提示用户介入。  
   - 如遇模糊匹配（多个联系人或信息不全），立即停止后续操作，通知用户并请求人工干预。

**示例流程**：  
用户请求“最近7天的聊天记录”：  
① 调用 `get_current_time` 获取当前时间；  
② 计算最近7天时间区间；  
③ 调用 `get_message_by_wxid_and_time` 查询聊天记录；  
④ 返回结果并反馈执行状态。

每步操作均需检查状态，异常时立即上报。
"""
            )
        )

    def chat(self, message: Dict[str, List[BaseMessage | dict]]):  # -> List[HumanMessage|AIMessage|ToolMessage]:
        return self.agent.stream(message, stream_mode=['updates'], config={"configurable": {"thread_id": 42}})
        # result = self.agent.invoke(message, config={"configurable": {"thread_id": 42}})
        # return result.get('messages')


if __name__ == '__main__':
    agent = WeBotAgent(model_name='deepseek_v3')
    result = agent.chat({
        "messages": [
            HumanMessage(content="看下'人生何处不青山'今天中午到现在都在聊些什么")
        ]
    })

    for item in result:
        print(item)
        print('-----')