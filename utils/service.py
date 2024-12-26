from datetime import datetime
from json import loads
from threading import Thread, Event
from typing import Callable, Dict, List

from libs.contact import Contact
from utils.service_type import Response, Request
from utils.toolkit import get_latest_wechat_version
from libs.webot import WeBot
from utils.chat_glm import chat_glm
from utils.contact_captor import contact_captor

from flask import Flask, request
from requests import post as http_post

event = Event()
app = Flask(__name__)
app.config['TIMEOUT'] = 300

bot: dict[dict[WeBot, dict]] = {}
latest_bot: WeBot | None = None


def get_bot(port) -> WeBot | None:
    return bot.get(port).get('object')


def get_function_tools(_bot: WeBot) -> dict:
    return {
        "contact_captor": _bot.get_concat_from_keyword
    }


def chat_with_glm(ask_message, _bot: WeBot, prompt: str = None, function_tools: list = None):
    result = chat_glm(ask_message, prompt, function_tools)
    result = result.model_dump()
    if result.get('tool_calls') and len(result.get('tool_calls')) > 0:
        function_name = result.get('tool_calls')[0].get('function').get('name')
        function_args = result.get('tool_calls')[0].get('function').get('arguments')
        return_data = get_function_tools(_bot).get(function_name)(**loads(function_args))
        return return_data
    return result.get('message')


def on_bot_start(b: WeBot):
    global bot
    global latest_bot
    bot.setdefault(b.remote_port, {"object": b, "info": b.info})
    latest_bot = b
    event.set()


def on_bot_stop(b: WeBot):
    print('bot stop')


def start_bot(version):
    _bot = WeBot(
        faked_version=version,
        on_start=on_bot_start,
        on_stop=on_bot_stop
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
    response = Response(code=200, message='success', data={port: {"info": bot.get(port).get('info')} for port in bot})
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
        response.data = 0
        return response.json
    response.data = 1
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
        response.message = '参数缺失'
        return response.json

    port = body.body.get('port')

    _bot = get_bot(int(port))

    if not _bot:
        response.code = 400
        response.message = '未找到对应端口的机器人'
        return response.json

    try:
        with open(r'../config/function_tools.json', 'r', encoding='utf-8') as f:
            tools = loads(f.read())

        result = chat_with_glm(
            ask_message=body.body.get('messages'),
            prompt=f"""
        你是一个微信机器人助手，你的职责如下：
        - 今天是{datetime.now()}。
        - 总结用户的聊天内容，并给出回答；
        - 分析用户的需求，按需调用tools函数；
        """,
            function_tools=tools,
            _bot=_bot
        )
        response.data = result
        return response.json

    except Exception as e:
        response.code = 500
        response.message = str(e)
        return response.json


if __name__ == '__main__':
    app.run(port=16001)
