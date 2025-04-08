from typing import List, Dict

from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver


from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, BaseMessage

from llm.llm import LLMFactory
from tool_call.tools import ALL_TOOLS

BASE_CHECKPOINTER = MemorySaver()

class WeBotAgent:

    def __init__(self, model_name: str = "glm-4-flash", llm_options: dict = {}, webot_port: int = 19001):
        self.llm = LLMFactory.llm(model_name=model_name, **llm_options)

        self.checkpoint = MemorySaver()

        self.agent = create_react_agent(
            model=self.llm,
            tools=ALL_TOOLS,
            checkpointer=self.checkpoint,
            prompt=SystemMessage(
                content=f"""
你是一个基于AI的微信机器人助手，通过工具函数从微信客户端获取信息。  
请严格按照以下规则操作：

## 1. 前置说明  
    - **微信Port：** 使用 `{webot_port}` 作为微信Port参数。
    - **工具函数使用规范：** 请务必结合实际场景调用工具函数，例如：
        - `get_message_by_wxid_and_time`用于获取聊天记录字典（主要供模型二次分析，不供用户直接使用）；
        - `export_message`用于将聊天记录导出为本地文件，当用户要求导出、提取或下载聊天记录时应调用此函数。

## 2. 思考与决策流程   
1. **分析现状**：理解用户目标、当前已有的信息、以及上一步工具执行的结果
2. **制定策略**：判断距离最终目标还有多远？下一步最有效的行动是什么？是需要调用工具获取更多信息，还是已经可以总结答案？
3. **策略执行**：结合制定的策略分步调用工具函数（如：先调用 `get_current_time` 获取当前时间，再计算时间区间，后续调用其它函数）。
     > **在每次决定使用工具前，你必须先进行内部思考（Thought），分析当前情况和目标，确定调用此工具是当前最佳的、必要的步骤，然后再进行执行操作。**
   - **状态反馈**：每一步操作后立即反馈结果，并且描述当前操作内容；如遇失败，重试或提示用户手动操作。  
   - **总结返回**：任务结束后，用Markdown格式总结并反馈操作结果（成功或失败及解决方案）。

4. **数据要求**  
   - 返回的信息必须来自工具函数获取，严禁编造数据。
   - 多个联系人需要用户二次确认时，需要带上名称、备注与wxid。

5. **错误处理**  
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
    

class BaseAgent:

    def __init__(self, model_name: str = "glm-4-flash", llm_options: dict = {}, webot_port: int = 19001):
        pass