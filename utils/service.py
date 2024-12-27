import traceback
from datetime import datetime
from json import loads
from threading import Thread, Event
from os import path
from utils.toolkit import CONFIG_PATH
from dataclasses import asdict

from utils.service_type import Response, Request
from utils.toolkit import get_latest_wechat_version
from libs.webot import WeBot
from utils.chat_glm import chat_glm

from flask import Flask, request
from flask_cors import CORS
from requests import post as http_post

event = Event()
app = Flask(__name__)
CORS(app)
app.config['TIMEOUT'] = 300

bot: dict[dict[WeBot, dict]] = {}
latest_bot: WeBot | None = None


def get_bot(port) -> dict | None:
    return bot.get(port, {})


def generate_multi_contact_text(contacts: dict[str, dict | list]) -> str:
    print(contacts)

    if type(contacts.get('data')) == 'dict':
        contacts['data'] = [contacts.get('data')]
    result = f"找到了**{len(contacts.get('data'))}**个联系人：  \n\n   "
    for index, contact in enumerate(contacts.get('data')):
        result += f"{index + 1}. **微信名**: `{contact.get('name')}`  \n   **备注**: {contact.get('remark')}  \n   **wxid**: `{contact.get('wxid')}`  \n   **微信号**: `{contact.get('custom_id')}`  \n"
        if index != len(contacts.get('data')) - 1:
            result += "----\n  "
    return result if len(contacts.get('data')) == 1 else result + "\n<br><br>哪个是你要找的联系人呢？"


def get_function_tools(_bot: WeBot) -> dict:
    def get_contact_text(*args, **kwargs):
        contacts = _bot.get_concat_from_keyword(*args, **kwargs)

        if contacts.get('type') == 'none':
            return {"data": "没有找到这个联系人，请确认关键字是否正确。"}

        return {"data": generate_multi_contact_text(contacts)}

    def send_text(content: str, keywords: str = None, wxid: str = None):
        if wxid:
            _bot.send_text(wxid=wxid, msg=content)
            return {"data": "发送成功"}

        contacts = _bot.get_concat_from_keyword(keywords)
        if contacts.get('type') == 'none':
            return {"data": "没有找到这个联系人，请确认关键字是否正确。"}

        if contacts.get('type') == 'multi':
            return {"data": generate_multi_contact_text(contacts)}

        if contacts.get('type') == 'single':
            return {"data": generate_multi_contact_text(contacts) + "  \n\n找到了这个联系人，确认发送吗？"}

        return {"data": '未知错误'}

    return {
        "contact_captor": get_contact_text,
        "message_summary": _bot.get_message_summary,
        "send_text": send_text
    }


def chat_with_glm(ask_message: list[dict], _bot: WeBot, prompt: str = None, function_tools: list = None):
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
            summary_result = chat_glm(ask_message, function_tools=function_tools, prompt=prompt).model_dump().get(
                'content')
            return summary_result
        return return_data.get('data')
    return result.get('content')


def on_bot_start(b: WeBot):
    global bot
    global latest_bot
    bot.setdefault(b.remote_port, {"object": b})
    latest_bot = b
    event.set()


def on_bot_login(b: WeBot, event):
    global bot
    bot[b.remote_port] = {"object": b, "info": asdict(b.info)}
    print(bot)


def on_bot_stop(b: WeBot):
    print('bot stop')


def start_bot(version):
    _bot = WeBot(
        faked_version=version,
        on_start=on_bot_start,
        on_stop=on_bot_stop,
        on_login=on_bot_login
    )
    _bot.run()


@app.after_request
def after_request(response):
    global latest_bot
    if request.endpoint == 'start':
        latest_bot = None
        event.clear()
    return response


@app.route('/')
def hello_world():
    app.logger.debug('Hello, World!')
    response = Response(code=200, message='success', data="Hello, World!")
    return response.json


@app.route('/api/bot/get_latest_version')
def get_latest_version():
    response = Response(code=200, message='success', data=None)
    response.set_data(function=get_latest_wechat_version)
    return response.json


@app.route('/api/bot/start', methods=['POST'])
def start():
    global latest_bot
    body = request.json
    version = body.get('version')
    if not version:
        version = get_latest_wechat_version()

    t = Thread(target=start_bot, kwargs={"version": version})
    t.daemon = True
    t.start()
    event.wait()
    response = Response(code=200, message='success', data={"port": latest_bot.remote_port})
    return response.json


@app.route('/api/bot/list', methods=['GET'])
def bot_list():
    response = Response(code=200, message='success',
                        data=[{"port": port, "info": data.get('info')} for port, data in bot.items()])
    return response.json


@app.route('/api/bot/login_heartbeat', methods=['POST'])
def login_heartbeat():
    body = Request(body=request.json, body_keys=['port'])
    response = Response(code=200, message='success', data=None)
    if not body.check_body:
        response.code = 400
        response.message = '参数缺失'
        return response.json

    login_status = None
    try:
        login_status = http_post(f'http://127.0.0.1:{body.body.get("port")}/api/checkLogin').json()
    except Exception as e:
        response.code = 500
        response.message = str(e)
        return response.json

    if login_status.get('code') == 0:
        response.data = {"status": False}
        return response.json
    info = bot.get(body.body.get('port')).get('info')
    response.data = {"status": True, "info": info}
    return response.json


@app.route('/api/bot/export_message_file', methods=['POST'])
def export_message_file():
    body = Request(body=request.json, body_keys=['port', 'wxid'])
    response = Response(code=200, message='success', data=None)
    if not body.check_body:
        response.code = 400
        response.message = '参数缺失'
        return response.json

    port = body.body.get('port')
    wxid = body.body.get('wxid')

    _bot = get_bot(int(port))

    if not _bot:
        response.code = 400
        response.message = '未找到对应端口的机器人'
        return response.json

    _bot = _bot.get('object')

    try:
        file_path = _bot.export_message_file(
            wxid=wxid,
            filename=body.body.get('filename', None),
            include_image=body.body.get('include_image', False),
            start_time=body.body.get('start_time', None),
            end_time=body.body.get('end_time', None),
            export_type=body.body.get('export_type', 'json'),
            endswith_txt=body.body.get('endswith_txt', True)
        )

        response.data = {
            "filepath": file_path
        }

        return response.json

    except Exception as e:
        response.code = 500
        response.message = str(e)
        return response.json


@app.route('/api/ai/chat', methods=['POST'])
def ai_chat():
    body = Request(body=request.json, body_keys=['port', 'messages'])
    response = Response(code=200, message='success', data=None)
    if not body.check_body:
        response.code = 400
        response.message = "参数错误，可能是微信未启动。  \n请先点击左侧 **登录微信** 按钮启动微信，并且登录。" if not body.body.get('port') else '参数缺失'
        return response.json

    port = body.body.get('port')

    _bot = get_bot(int(port))

    if not _bot:
        response.code = 400
        response.message = '未找到对应端口的机器人'
        return response.json

    _bot_object = _bot.get('object')
    _bot_info = _bot.get('info')

    try:
        with open(path.join(CONFIG_PATH, 'function_tools.json'), 'r', encoding='utf-8') as f:
            tools = loads(f.read())
        today = datetime.now().strftime("%Y-%m-%d")
        time_now = datetime.now().strftime("%H:%M:%S")
        week_day = datetime.now().strftime("%A")
        result = chat_with_glm(
            ask_message=body.body.get('messages'),
            prompt=f"""
        你是一个微信机器人助手，你的职责如下：
        - 今天是`{today}，现在是北京时间`{time_now}，`{week_day}`。
        - 用户的名字是`{_bot_info.get('name')}`，所以聊天记录中的`{_bot_info.get('name')}`是用户自己。
        - 总结用户的聊天内容，并给出回答；
        - 分析用户的需求，按需调用tools函数；
        - 当涉及到转发内容时，请你务必转发原文，不要篡改任何内容；
        """,
            function_tools=tools,
            _bot=_bot_object
        )
        response.data = result
        return response.json

    except Exception as e:
        response.code = 500
        response.message = str(e)
        traceback.print_exc()
        return response.json


if __name__ == '__main__':
    app.run(port=16001)
