from os import environ
from pathlib import Path
from json import loads

from libs.webot import WeBot
from utils.toolkit import get_function_tools

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
        tools=function_tools or {}
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


def chat_with_function_tools(ask_message: list[dict], _bot: WeBot, prompt: str = None, function_tools: list = None):
    """
    使用glm-4-flash模型，结合函数工具进行聊天

    :param ask_message: 聊天内容，需要传入完整的对话上下文
    :param _bot: WeBot对象
    :param prompt: 对机器人的人设。
    :param function_tools: 工具函数
    :return: 返回字符串。如果是工具函数返回的内容，在工具函数内需要返回一个字典，并且把需要给前端的消息字符串放在"data"字段。
    """

    result = chat_glm(ask_message, prompt, function_tools)
    result = result.model_dump()
    if result.get('tool_calls') and len(result.get('tool_calls')) > 0:
        function_name = result.get('tool_calls')[0].get('function').get('name')
        function_args = result.get('tool_calls')[0].get('function').get('arguments')
        return_data = get_function_tools(_bot).get(function_name)(**loads(function_args))
        if function_name == 'message_summary' and return_data.get('type') == 'prompt':
            ask_message.append({"role": "assistant",
                                "content": f"好的，我获取到了下面这份聊天记录:  \n  {return_data.get('data')}  \n  你需要的是这个吗？"})
            ask_message.append({"role": "user", "content": "是的，没错。"})
            # TODO：
            #  现在的问题是，加了这两行对话历史，不会返回给前端，用完就没了。后续的上下文中无法读取到这段聊天记录。
            #  目前的计划是，完整的上下文，包括这两条存到数据库，然后加一个字段判断是否应该展示在前端。
            #  每次前端请求对话时以完整的上下文发送请求，但是前端获取展示时过滤掉这两条。
            #  得考虑上下文中聊天记录的存储方式，如果直接存储在上下文字段中，存在表里会不会太长了？最大可能会出现十几兆的数据？
            #  或者可以考虑存储参数到一个新的字段，例如这条对话涉及到了什么参数，然后前端请求时再根据参数重新获取对应的聊天记录。
            summary_result = chat_glm(ask_message, function_tools=function_tools, prompt=prompt).model_dump().get(
                'content')
            return summary_result
        return return_data.get('data')
    return result.get('content')