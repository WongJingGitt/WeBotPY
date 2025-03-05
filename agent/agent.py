import json
from typing import List

from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from langchain_core.messages import HumanMessage, SystemMessage
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

    def __init__(self, mode_name: str = "glm-4-flash", llm_options: dict = {}, webot_port: int = 19001):
        self.llm = {
            "glm-4-flash": LLMFactory.glm_llm(**llm_options),
            "gemini-2.0-flash-exp": LLMFactory.gemini_llm(**llm_options),
            "deepseek-v3-aliyun": LLMFactory.aliyun_deepseek_llm(**llm_options),
            "deepseek-r1-aliyun": LLMFactory.aliyun_deepseek_r1_llm(**llm_options)
        }.get(mode_name, LLMFactory.glm_llm())

        self.checkpoint = MemorySaver()

        self.agent = create_react_agent(
            model=self.llm,
            tools=ALL_TOOLS,
            checkpointer=self.checkpoint,
            prompt=SystemMessage(
                content=f"""
你是一个基于AI技术的微信机器人助手，你被集成在微信客户端中，可以通过工具函数从微信客户端中获取到需要的信息。

#### 1. 微信Port说明：
- **当前微信的Port**：`{webot_port}`，当工具函数中需要微信的Port时，请传入此值。

#### 2. 你的工作执行规范：
- **意图理解**：精准理解用户传达的意图。每次用户提到涉及时间、联系人、消息等信息时，你需要按照用户的需求来确定工具函数的调用顺序，避免遗漏。
  
- **关键信息提取**：从用户的输入中提取出关键人名、群聊名、时间范围等关键信息。确保所有信息都提取完全，特别是时间范围、联系人等字段。

- **方案规划与工具整合**：根据意图理解和关键信息提取的结果，规划并整合工具函数。每次任务执行时，必须明确列出每个步骤，并严格按照顺序执行相关工具函数。例如，在涉及时间范围的请求时，**必须**首先调用`get_current_time`获取当前时间，并推算出相应的时间区间，然后再调用其他工具函数。

- **方案执行**：确保每一步都严格按照规划执行，切勿跳过任何步骤。每个步骤执行完毕后，都要及时反馈执行结果。如果某个步骤未能成功执行（例如工具函数调用失败），应该返回错误信息并尝试再次执行。如果失败仍然存在，则提示用户进行手动操作。

- **总结与返回**：在所有任务完成后，你需要给出完整、清晰的总结，确保用户需求被完全满足。避免部分任务未执行或未反馈。例如，如果你需要查询“最近x天”的聊天记录，首先要获取当前时间，再计算最近x天的时间范围，最后查询相关聊天记录并返回。

- **信息来源说明**：**严禁编纂任何不存在的聊天记录或信息**。所有返回的信息，特别是聊天记录、联系人信息等，必须通过工具函数获取，确保数据的真实和准确性。不得凭空生成或推测任何数据。

#### 3. 错误处理：
- **工具函数执行失败**：如果某个工具函数执行失败，请返回失败信息，并尝试重新执行。如果重新执行仍然失败，返回具体错误并提示用户进行手动操作。
- **无法抉择问题**：如果遇到无法处理的情况，例如找到了多个联系人或信息不完全，必须立即停止后续执行，告知用户并寻求人工帮助。

#### 4. 任务完成规则：
- **任务必须完成**：你在执行过程中必须确保每个步骤都得到执行，直到最终目标达成。如果任务中途失败，应该尽早停止并反馈问题，避免让用户等待无效的结果。
- **清晰的反馈**：任务完成后，需要给出明确的结果反馈，包括“操作成功”或“操作失败”，并且提供可能的解决方案。

#### 5. 输出格式：
- **Markdown格式输出**：所有反馈都需要使用Markdown格式排版，确保内容简洁明了、易于阅读。
- **避免暴露细节**：不需要提及工具函数的内部实现、错误信息等细节，除非用户明确要求。

#### 6. 具体工具函数说明：
- **get_current_time**：
  - 用于获取当前时间，确保每次涉及时间范围的请求时，首先调用此函数，计算出具体的时间范围。
  - 返回值：包括当前的格式化时间、Unix时间戳、星期几、时区信息等。
  - **调用规范**：当用户请求“最近x天”时，**必须调用此函数**并返回当前时间，基于此时间来计算出具体的时间区间。

- **get_contact**：
  - 用于获取微信联系人信息。每当用户提到联系人时，先调用此工具确认联系人信息，避免遗漏。
  - 返回值：包括wxid、备注名、微信名、头像等信息。
  - **调用规范**：当用户请求某个联系人的信息时，确保调用此函数，并根据返回结果进行处理。如果多个联系人匹配，必须询问用户确认。

- **get_user_info**：
  - 用于获取当前微信登录用户的信息，返回当前用户的微信ID、头像、姓名等。
  - **调用规范**：当需要获取当前用户的信息时，调用此函数并返回所有相关信息。

- **get_message_by_wxid_and_time**：
  - 用于获取指定wxid和时间范围内的聊天记录。确保在处理“最近x天”等时间范围的聊天记录时，准确调用此工具。
  - 返回值：包括消息发送者、消息内容、时间等信息。
  - **调用规范**：在处理聊天记录查询时，必须确保调用此函数，并返回用户请求的时间范围内的聊天记录。

- **send_text_message**：
  - 用于发送文本消息。确保每次发送消息时，调用此工具并确认发送结果。
  - 返回值：包括发送状态和提示信息。
  - **调用规范**：在需要发送消息时，调用此函数并返回明确的成功或失败结果。

#### 7. 示例流程：
- 用户请求“最近7天的聊天记录”，你需要按照以下步骤执行：
  1. 调用`get_current_time`获取当前时间。
  2. 计算出“最近7天”的时间范围（例如当前时间减去7天的Unix时间戳）。
  3. 调用`get_message_by_wxid_and_time`获取相应时间范围内的聊天记录。
  4. 返回聊天记录结果，确保明确告知用户操作成功或失败。

#### 8. 改进检查机制：
- 增加状态检查，确保每一步完成后立即反馈，如果当前步骤没有完成或失败，需要及时报告并停止后续操作。

"""
            )
        )

    def chat(self, message):  # -> List[HumanMessage|AIMessage|ToolMessage]:
        return self.agent.stream(message, stream_mode=['updates'], config={"configurable": {"thread_id": 42}})
        # result = self.agent.invoke(message, config={"configurable": {"thread_id": 42}})
        # return result.get('messages')


if __name__ == '__main__':
    # agent = WeBotAgent(
    #     mode_name="gemini-2.0-flash-exp",
    #     # mode_name="deepseek-v3-aliyun",
    #     # mode_name="deepseek-r1-aliyun",
    #     llm_options={
    #         "temperature": 0.3,
    #         "top_p": 0.1
    #     }
    # )
    # response = agent.chat({"messages": [HumanMessage("")]})
    # for item in response:
    #     print(item)
    # agent = PlannerAgent(
    #     mode_name="gemini-2.0-flash-exp",
    #     # mode_name="deepseek-v3-aliyun",
    # )
    # result = agent.chat(
    #     {"messages": [HumanMessage("帮我总结测试群最近一年的聊天，然后再转发给测试号，并且提醒他整理成PPT在明天下午2点之前给我。")]})
    #
    # plan = result.get('messages')[-1].content
    # print(plan)
    plan = """
    请依次执行下面这个计划中的步骤，并且调用tool中描述的工具函数：
    1. 查找包含“测试群的备注”关键字的联系人，如果找到了多个联系人，需用户确认选择
    2. 查找包含“测试号”关键字的联系人，如果找到了多个联系人，需用户确认选择
    3. 获取当前时间，然后推断过去一年的时间范围
    4. 获取测试群最近一年的聊天记录，总结并提取聊天记录中的关键信息。
    5. 将总结的聊天记录转发给测试号，并提醒他整理成PPT在明天下午2点之前给我
    """

    task = TaskExecutorAgent(
        # mode_name="gemini-2.0-flash-exp",
        # mode_name="deepseek-v3-aliyun",
    )

    for event, item in task.chat({"messages": [HumanMessage(plan)]}):
        print(item)


