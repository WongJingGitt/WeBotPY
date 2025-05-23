import ast
import json
import re
import uuid
from typing import List, Dict, Any
from sqlite3 import connect

from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.sqlite import SqliteSaver

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, BaseMessage

from webot.llm.llm import LLMFactory
from webot.tool_call.tools import ALL_TOOLS
from webot.utils.project_path import DATA_PATH, path
from webot.prompts.system_prompts import SystemPrompts

CHECKPOINT_DB_PATH = path.join(DATA_PATH, 'databases', 'webot_checkpoint.db')


def extract_openai_json_object(text: str) -> dict | None:
    """
    从响应体中解析出openai规范的json
    """
    try:
        # 寻找第一个 '{'
        start_index = text.index('{')
    except ValueError:
        return None

    open_braces = 0
    in_string = False  # 用于处理字符串中的括号

    for i in range(start_index, len(text)):
        char = text[i]

        # 简单处理字符串，避免字符串中的引号和括号干扰计数
        if char == '"':
            # 检查前一个字符是否是转义符
            if i > 0 and text[i - 1] == '\\':
                pass  # 这是个转义的引号，不改变in_string状态
            else:
                in_string = not in_string

        if not in_string:  # 只在字符串外部计数括号
            if char == '{':
                open_braces += 1
            elif char == '}':
                open_braces -= 1

        if open_braces == 0 and i >= start_index:  # 确保至少匹配过一次 '{'
            potential_json_str = text[start_index: i + 1]
            try:
                data = json.loads(potential_json_str)
                # 确保解析出来的是一个字典 (JSON 对象)
                if isinstance(data, dict):
                    return data
                else:
                    # 继续寻找下一个可能的 '{' (这个简化版本不处理)
                    return None
            except json.JSONDecodeError:
                return None
    return None


def extract_xml_tool_call(text: str) -> Dict[str, Any] | None:
    """
    从文本中提取 <tool_call>...</tool_call> 内容并解析。
    期望的内部格式是 Python 字典的字符串表示。
    """
    match = re.search(r'<tool_call>(.*?)</tool_call>', text, re.DOTALL)
    if not match:
        return None

    tool_call_str_content = match.group(1).strip()
    try:
        # 使用 ast.literal_eval 安全地评估字符串
        # 这可以处理 {'name': '...', 'arguments': {...}} 这样的格式
        tool_call_data = ast.literal_eval(tool_call_str_content)
        if isinstance(tool_call_data, dict) and 'name' in tool_call_data and 'arguments' in tool_call_data:
            # 为其生成 LangGraph 需要的 tool_calls 结构
            tool_name = tool_call_data['name']
            tool_args = tool_call_data['arguments']
            # LangGraph agent期望的tool_calls格式
            # 我们需要为XML格式的工具调用生成一个唯一的ID
            tool_id = f"call_{uuid.uuid4().hex[:24]}"  # 生成一个随机ID

            formatted_tool_calls = [
                {
                    "name": tool_name,
                    "args": tool_args,  # arguments 已经是 dict 了
                    "id": tool_id,
                    "type": "tool_call"  # LangGraph内部使用的type
                }
            ]
            # additional_kwargs 模仿 OpenAI 的结构，方便 LangGraph 处理
            additional_kwargs_tool_calls = [
                {
                    "id": tool_id,
                    "type": "function",  # OpenAI 称之为 function
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(tool_args)  # OpenAI 的 arguments 是 JSON string
                    }
                }
            ]
            return {
                "tool_calls": formatted_tool_calls,
                "additional_kwargs_tool_calls": additional_kwargs_tool_calls,
                "original_tool_call_string": match.group(0)  # 返回包含<tool_call>标签的完整字符串
            }
        return None
    except (ValueError, SyntaxError) as e:
        print(f"Error parsing XML tool_call content: {tool_call_str_content}, Error: {e}")
        return None


def post_model_hook(states: Dict[str, Any]) -> Dict[str, Any]:
    if not states.get('messages'):
        return states  # 返回原状态，避免后续处理None

    messages: List[BaseMessage] = states['messages']
    if not messages or not isinstance(messages[-1], AIMessage):
        # 如果最后一条消息不是AIMessage，或者列表为空，则直接返回，不修改
        states['messages'] = [messages[-1]]
        return states

    last_message: AIMessage = messages[-1]
    original_content: str = last_message.content

    # 1. 分离 <think> 和后续内容
    think_pattern = r'<think>(.*?)</think>\s*(.*)'
    match = re.match(think_pattern, original_content, re.DOTALL)

    if not match:
        # 没有 <think> 标签，可能LLM直接返回了内容 (纯文本或直接的工具调用JSON)
        # 尝试直接解析整个 content 是否为工具调用
        think_content_formatted = ""  # 没有思考内容
        # content_after_think 就是原始内容
        content_after_think = original_content.strip()
    else:
        think_text = match.group(1).strip()
        content_after_think = match.group(2).strip()

        think_chunk_list = think_text.split('\n')
        think_chunk_list = [f'- {chunk_item}' for chunk_item in think_chunk_list if chunk_item.strip()]
        think_content_formatted = '\n\n'.join(think_chunk_list)
        if think_content_formatted:  # 只有当有实际思考内容时才添加标题
            think_content_formatted = f"## 思考内容\n\n{think_content_formatted}\n\n-----"

    is_tool_call_processed = False

    # 2. 尝试解析 OpenAI 格式的 JSON 工具调用
    # extract_openai_json_object 需要整个包含 JSON 的文本
    # content_after_think 应该是包含 JSON 的那部分
    openai_json_tool_call = extract_openai_json_object(content_after_think)
    if openai_json_tool_call and isinstance(openai_json_tool_call.get('delta'), dict):
        delta = openai_json_tool_call['delta']
        raw_tool_calls = delta.get('tool_calls')  # 这是OpenAI原始的tool_calls列表

        if raw_tool_calls:
            parsed_tool_calls = []
            for call in raw_tool_calls:
                try:
                    function_details = call.get('function', {})
                    tool_name = function_details.get('name')
                    # OpenAI的arguments是字符串，需要json.loads
                    tool_args_str = function_details.get('arguments', '{}')
                    tool_args = json.loads(tool_args_str)
                    tool_id = call.get('id')

                    if tool_name and tool_id:  # 确保关键字段存在
                        parsed_tool_calls.append({
                            "name": tool_name,
                            "id": tool_id,
                            "args": tool_args,
                            'type': 'tool_call'
                        })
                except json.JSONDecodeError as e:
                    print(f"Error decoding arguments for OpenAI tool call: {tool_args_str}, Error: {e}")
                    continue  # 跳过这个错误的工具调用
                except Exception as e:
                    print(f"Error processing OpenAI tool call item: {call}, Error: {e}")
                    continue

            if parsed_tool_calls:
                last_message.tool_calls = parsed_tool_calls
                last_message.additional_kwargs = {"tool_calls": raw_tool_calls}  # 存储原始的 additional_kwargs

                # 构建显示内容
                # 如果 delta 中有 content，它通常是 null 或空字符串在工具调用时
                # 但如果LLM填充了，我们也应该显示它
                final_display_content = content_after_think  # 这是原始的JSON字符串
                if delta.get("content"):
                    # 如果 delta.content 有实际文本，这通常意味着LLM在调用工具的同时也想说点什么
                    # 在这种情况下，content_after_think 应该就是 delta.content 本身，而非JSON对象字符串
                    # 这里需要根据实际情况调整，如果 content_after_think 始终是json对象字符串，则如下：
                    # final_display_content = f"{delta.get('content')}\n(工具调用信息: {json.dumps(openai_json_tool_call, ensure_ascii=False, indent=2)})"
                    # 假设 content_after_think 是完整的 JSON 字符串，并且 delta.content 可能为 null
                    pass  # content_after_think 已经是包含工具调用的 JSON 字符串了

                last_message.content = f"{think_content_formatted}\n\n{final_display_content}".strip()
                is_tool_call_processed = True

    # 3. 如果不是 OpenAI JSON 工具调用，尝试解析 XML 格式的工具调用
    if not is_tool_call_processed:
        xml_tool_call_data = extract_xml_tool_call(content_after_think)
        if xml_tool_call_data:
            last_message.tool_calls = xml_tool_call_data['tool_calls']
            last_message.additional_kwargs = {"tool_calls": xml_tool_call_data['additional_kwargs_tool_calls']}

            # content_after_think 在XML场景下是包含<tool_call>的文本
            # 为了显示，我们可以只显示工具调用信息，或者整个 content_after_think
            # 这里使用 xml_tool_call_data['original_tool_call_string'] 来只显示工具调用部分
            tool_call_display = xml_tool_call_data['original_tool_call_string']
            last_message.content = f"{think_content_formatted}\n\n{tool_call_display}".strip()
            is_tool_call_processed = True

    # 4. 如果两种工具调用都未处理，则视为普通文本回复
    if not is_tool_call_processed:
        if think_content_formatted:  # 如果有思考过程
            last_message.content = f"{think_content_formatted}\n\n{content_after_think}".strip()
        else:  # 如果没有思考过程，直接就是回复
            last_message.content = content_after_think

    states['messages'] = [last_message]  # 仅保留最后处理过的消息或更新最后一条消息
    return states


class WeBotAgent:

    def __init__(self, model_name: str = "glm-4-flash", llm_options: dict = {}, webot_port: int = 19001, username: str = ''):
        self.llm = LLMFactory.llm(model_name=model_name, **llm_options)

        self._sqlite_con = connect(CHECKPOINT_DB_PATH, check_same_thread=False)
        self.checkpoint = SqliteSaver(conn=self._sqlite_con)
        username = f"\n   - **用户名：** 当前与你对话的用户叫做：`{username}`，你可以使用`{username}`称呼用户。" if username else ''
        system_prompt = SystemPrompts.webot_system_prompt(webot_port=webot_port, username=username)

        self.agent = create_react_agent(
            model=self.llm,
            tools=ALL_TOOLS,
            checkpointer=self.checkpoint,
            prompt=SystemMessage(content=system_prompt),
            post_model_hook=post_model_hook
        )

    def chat(self, message: Dict[str, List[BaseMessage | dict]],
             thread_id: int | str = -1):  # -> List[HumanMessage|AIMessage|ToolMessage]:
        return self.agent.stream(message, stream_mode=['updates'],
                                 config={"configurable": {"thread_id": str(thread_id)}})
