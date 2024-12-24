from time import sleep
from threading import Thread, Event

from utils.service_type import Response, Request
from utils.toolkit import get_latest_wechat_version
from libs.webot import WeBot

from flask import Flask, request
from requests import post as http_post, get as http_get

event = Event()
app = Flask(__name__)
app.config['TIMEOUT'] = 300

bot: WeBot = None


def on_bot_start(b: WeBot):
    global bot
    bot = b
    event.set()


def start_bot(version):
    global bot
    bot = WeBot(
        faked_version=version,
        on_start=on_bot_start
    )
    bot.run()


@app.route('/')
def hello_world():
    response = Response(code=200, message='success', data="Hello, World!")
    return response.json


@app.route('/get_latest_version')
def get_latest_version():
    response = Response(code=200, message='success', data=None)
    response.set_data(function=get_latest_wechat_version)
    return response.json


@app.route('/start', methods=['POST'])
def start():
    body = request.json
    version = body.get('version')
    if not version:
        version = get_latest_wechat_version()

    t = Thread(target=start_bot, kwargs={"version": version})
    t.start()
    event.wait()
    response = Response(code=200, message='success', data={"port": bot.remote_port})
    return response.json


@app.route('/login_heartbeat', methods=['POST'])
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


if __name__ == '__main__':
    app.run(port=3569)
