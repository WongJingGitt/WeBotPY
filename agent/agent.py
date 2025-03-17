from typing import List, Dict, TypedDict

from langgraph.prebuilt import create_react_agent
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.graph.graph import CompiledGraph
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, Send
from langchain_text_splitters import RecursiveJsonSplitter

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, BaseMessage

from llm.llm import LLMFactory
from agent_types import TaskStatus, StepItem
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
    


if __name__ == '__main__':
    class BaseState(TypedDict):
        messages: MessagesState
        model_name: str
        llm_options: dict
        webot_port: int = 19001


    # TODO：
    #   重新规划整体的Agent架构，结合StateGraph实现多Agent协同
    #   创建聊天记录拆分Agent，传入主Prompt，根据主Prompt提取关键信息，最后创建专门用作总结的Agent，把所有分批次总结的Prompt聚合起来总结最终的报告。以规避API输入长度限制的问题。

    def main_agent(state: BaseState) -> Command:
        _prompt = """
    你是一位专业的意图分析大师，你需要根据用户的输入分析出用户的意图，你的主要职责如下：
    1. 分析用户的意图，并根据意图做出回复
    2. 你的回复仅限于：chat/tool，你不负责任何工具的调用。
    3. 当识别到用户的意图只是闲聊时，你应该回复：chat
    4. 但识别到用户的意图中需要使用工具时，你应该回复：tool
    """
        _llm = LLMFactory.llm(model_name=state['model_name'], **state['llm_options'])
        _agent = create_react_agent(
            model=_llm,
            checkpointer=BASE_CHECKPOINTER,
            prompt=_prompt,
            tools=ALL_TOOLS
        )
        response = _agent.invoke(state['messages'])
        # print(response.get('messages')[-1].content)
        if response.get('messages')[-1].content == 'chat':
            return Send('chat_agent', state)
        elif response.get('messages')[-1].content == 'tool':
            return Send('tool_agent', state)
        else:
            return Send('chat_agent', state)


    def chat_agent(state):

        _prompt = """
    你是一个微信机器人助手，你的职责是结合工具函数的描述解答用户任何问题，你的具体职责如下：
    1. 你主要负责解答用户的任何问题，不论有没有涉及到工具函数的描述。
    2. 当用户的问题涉及到工具函数时，你需要结合工具函数来解答用户的疑问。
    3. 你仅负责回答用户的问题，不需要调用任何工具函数。
    """
        _llm = LLMFactory.llm(model_name=state['model_name'], **state['llm_options'])
        _agent = create_react_agent(
            model=_llm,
            checkpointer=BASE_CHECKPOINTER,
            prompt=_prompt,
            tools=ALL_TOOLS
        )
        response = _agent.invoke(state['messages'])
        state['messages']['messages'].append(response)
        # print(response)
        return Command(goto=END, update=state)


    def plan_agent(state):
        _prompt = """
    你是一位专业的任务规划大师，你的主要职责是：
    """
        _llm = LLMFactory.llm(model_name=state['model_name'], **state['llm_options'])
        _agent = create_react_agent(
            model=_llm,
            checkpointer=BASE_CHECKPOINTER,
            prompt=_prompt,
            tools=ALL_TOOLS
        )
        response = _agent.invoke(state['messages']['messages'])


    def tool_agent(state):
        _prompt = """
    """
        _llm = LLMFactory.llm(model_name=state['model_name'], **state['llm_options'])
        _agent = create_react_agent(
            model=_llm,
            checkpointer=BASE_CHECKPOINTER,
            prompt=_prompt,
            tools=ALL_TOOLS
        )
        response = _agent.invoke(state['messages'])
        state['messages']['messages'].append(response)
        return Command(goto=END, update=state)


    graph = StateGraph(
        BaseState
    )

    graph.add_node(main_agent)
    graph.add_node(chat_agent)
    graph.add_node(tool_agent)

    graph.add_conditional_edges(START, main_agent, ['chat_agent', 'tool_agent'])
    # graph.add_edge

    agent = graph.compile()

    result = agent.invoke(
        {
            "messages": MessagesState(messages=[HumanMessage(content="你好, 请帮我查询我现在的微信名字是什么？")]),
            "model_name": "gemini-2.0-flash-exp",
            "llm_options": {
                "apikey": "",
                "base_url": ''
            }
        }
    )

    print(result)