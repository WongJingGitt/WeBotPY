from os import environ
from pathlib import Path
from json import loads

from zhipuai import ZhipuAI


def chat_glm(ask_message, prompt: str = None):
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
        temperature=0.95
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
        - 这是一份聊天记录文件;
        - 每条消息使用 --- 分隔;
        - 角色`我`代表我发送的消息，`对方`代表对方发送的消息;
        - 内容字段代表聊天内容;
        - 时间字段代表这条消息发送的时间;
        - 深刻的理解聊天内容，并给出回答;
    """

    response = client.chat.completions.create(
        model="glm-4-flash",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": "深度总结一下这份聊天的内容"}
        ]
    )
    return response.choices


if __name__ == '__main__':
    # chat_with_file(r'D:\wangyingjie\WeBot\libs\chat_record.docx')
    print(bool(1))