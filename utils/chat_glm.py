from datetime import datetime
from os import environ
from pathlib import Path
from json import loads

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



