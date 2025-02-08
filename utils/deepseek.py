from datetime import datetime
from json import loads
from os import environ, path

from openai import OpenAI

from utils.project_path import CONFIG_PATH

with open(path.join(CONFIG_PATH, 'function_tools.json'), 'r', encoding='utf-8') as f:
    tools = loads(f.read())

apikey = environ.get('deepseek_apikey')

client = OpenAI(api_key=apikey, base_url="https://api.deepseek.com")

today = datetime.now().strftime("%Y-%m-%d")
time_now = datetime.now().strftime("%H:%M:%S")
week_day = datetime.now().strftime("%A")

prompt = f"""
你是一个微信机器人助手，你的职责如下：
- 今天是`{today}，现在是北京时间`{time_now}，`{week_day}`。
- 用户的名字是`WongJingGit`，所以聊天记录中的`WongJingGit`是用户自己。
- 总结用户的聊天内容，并给出回答；
- 分析用户的需求，按需调用tools函数；
- 当涉及到转发内容时，请先判断用户是否有指定原文，如果有原文：请你务必转发原文，不要篡改任何内容；
"""

response = client.chat.completions.create(
    model="deepseek-chat",
    stream=False,
    messages=[
        {"role": "system", "content": prompt},
        {"role": "user", "content": "你好，帮我总结一下和吴彦祖最近三天的聊天记录"},
        # {"role": "assistant", "content": "找到了两个联系人：\n\n\t姓名：吴彦祖\nwxid：wxid_123\n\t姓名：吴彦祖\nwxid：wxid_456\n\n请问你要找的是哪个呢？"},
        # {"role": "user", "content": "第1个"},
    ],
    tools=tools,
)

print(response.choices)