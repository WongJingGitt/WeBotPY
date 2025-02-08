import json
from datetime import datetime
from os import environ
from pathlib import Path
from json import loads

from bot.webot import WeBot
from utils.tools_selector import get_function_tools
from databases.conversation_database import ConversationsDatabase

from zhipuai import ZhipuAI


def chat_glm(ask_message, prompt: str = None, function_tools: list = None):
    apikey = environ.get('glm_apikey')

    client = ZhipuAI(api_key=apikey)

    msg = [
        {
            "role": "system",
            "content": prompt or """
                你叫王大锤，请你带入这个角色参与聊天。
    回复的主体是最新一条带有 @王大锤 的消息，其他的消息当作上下文参考。
            """
        }
    ]

    resp = client.chat.completions.create(
        model="glm-4-flash",
        messages=[*msg, *ask_message],
        temperature=0.1,
        tools=function_tools
    )

    return resp.choices[0].message


def chat_with_file(file_path):
    apikey = environ.get('glm_apikey')

    client = ZhipuAI(api_key=apikey)

    file = client.files.create(
        file=Path(file_path),
        purpose="file-extract"
    )
    content = loads(client.files.content(file.id).content)
    prompt = f"""
        请你针对{content.get('content')}的内容进行分析，并遵循以下提示对用户的问题给出答复：
        - 文档中数据说明部分表示了文档的主要数据格式;
        - 文档中数据部分表示了文档的主要数据内容;
        - 请你根据文档的数据格式和数据内容，深刻的理解聊天内容，并给出回答;
    """

    response = client.chat.completions.create(
        model="glm-4-flash",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": "深度总结一下这份聊天的内容"}
        ]
    )
    return response.choices[0].message


def chat_with_function_tools(ask_message: list[dict], _bot: WeBot, prompt: str = None, function_tools: list = None,
                             conversation_id: int = None):
    """
    使用glm-4-flash模型，结合函数工具进行聊天

    :param ask_message: 聊天内容，需要传入完整的对话上下文
    :param _bot: WeBot对象
    :param prompt: 对机器人的人设。
    :param function_tools: 工具函数
    :param conversation_id: 数据库的对话ID，用来记录当前消息属于哪个对话。
    :return: 返回字符串。如果是工具函数返回的内容，在工具函数内需要返回一个字典，并且把需要给前端的消息字符串放在"data"字段。
    """

    # 首次调用模型回答，是否调用tools由这里决定
    result = chat_glm(ask_message, prompt, function_tools)
    result = result.model_dump()
    # 如果有工具函数调用，则调用工具函数，并返回结果
    if result.get('tool_calls') and len(result.get('tool_calls')) > 0:
        function_name = result.get('tool_calls')[0].get('function').get('name')
        function_args = result.get('tool_calls')[0].get('function').get('arguments')
        # 调用工具函数，返回结果，只负责将模型决定调用的函数名传入，具体调用由get_function_tools负责
        return_data = get_function_tools(_bot).get(function_name)(**loads(function_args))
        # message_summary的特殊处理逻辑
        if function_name == 'message_summary' and return_data.get('type') == 'prompt':
            cdb = ConversationsDatabase()
            # TODO:
            #   聊天记录太长的话会截断上下文，读不到最初的问题了，需要考虑优化，分块总结？

            # 制造伪对话，把聊天记录放入上下文中
            ask_message.append({"role": "assistant",
                                "content": f"好的，我获取到了下面这份聊天记录:  \n  {return_data.get('data')}  \n  你需要的是这个吗？"})
            ask_message.append({"role": "user", "content": "是的，没错。"})

            # 添加到数据库中
            cdb.add_message(conversation_id, "assistant",
                            "好的，我获取到了下面这份聊天记录:  \n  {{聊天记录}}  \n  你需要的是这个吗？",
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 0,
                            json.dumps({"function_name": function_name, "function_args": function_args}))
            cdb.add_message(conversation_id, "user", "是的，没错。", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 0)

            summary_result = chat_glm(ask_message, function_tools=function_tools, prompt=prompt).model_dump().get(
                'content')
            return summary_result
        return return_data.get('data')
    return result.get('content')