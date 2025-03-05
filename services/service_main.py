import traceback
from datetime import datetime
from json import loads
from threading import Thread, Event
from os import path
from typing import List, Dict, Callable
from dataclasses import asdict
from uuid import uuid4

from utils.project_path import CONFIG_PATH, ROOT_PATH
from services.service_type import Response, Request
from utils.toolkit import get_latest_wechat_version
from bot.webot import WeBot
from utils.chat_glm import chat_with_function_tools as chat_with_glm
from bot.bot_storage import BotStorage
from services.service_conversations import ServiceConversations
from databases.conversation_database import ConversationsDatabase
from agent.agent import WeBotAgent

from flask import Flask, request, has_request_context, send_file
from flask_cors import CORS
from flask_socketio import SocketIO, emit, disconnect
from requests import post as http_post


class ServiceMain(Flask):
    """
    后端服务类，用作处理自定义逻辑，在WXHOOK原生请求之外加一层服务来实现一些自定义逻辑。
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs, import_name=__name__, static_url_path="/",
                         static_folder=path.join(ROOT_PATH, 'static'))
        self.config['TIMEOUT'] = 300
        CORS(self)
        self._bot: BotStorage = BotStorage()
        self._latest_bot: WeBot | None = None
        self._event = Event()
        self._conversions_database = ConversationsDatabase()
        self.socketio = SocketIO(self, path='/api/ai/stream', cors_allowed_origins="http://localhost:3000")
        self.socketio.init_app(self)

    def after_request(self, f):
        """
        覆写after_request方法，执行了一些回收工作。
        - 在请求结束后，如果请求是start，则将_latest_bot设置为None，清理变量为下次多开微信做准备。
        - 调用_event.clear()，清理事件状态。
        """
        response = super().after_request(f)
        if not has_request_context():
            return response
        if request.endpoint == 'start':
            self._latest_bot = None
            self._event.clear()
        return response

    def _on_bot_start(self, _bot: WeBot):
        """
        bot启动时的回调函数，这里主要是把当前启动的Webot实例化对象存到了bot字典里面。
        :param _bot:
        :return:
        """
        self._bot.set_bot(_bot.remote_port, bot=_bot)
        self._latest_bot = _bot
        self._event.set()

    def _on_bot_login(self, _bot: WeBot, _event):
        self._bot.set_bot(_bot.remote_port, bot=_bot, info=asdict(_bot.info))

    def _hello_world(self):
        return send_file(path.join(ROOT_PATH, 'static', 'index.html'))

    def _start_bot(self):
        body = request.json
        version = body.get('version')
        if not version:
            version = get_latest_wechat_version()

        def run_bot():
            _bot = WeBot(
                faked_version=version,
                on_start=self._on_bot_start,
                on_login=self._on_bot_login
            )
            _bot.run()

        t = Thread(target=run_bot, daemon=True)
        t.start()
        self._event.wait()
        response = Response(code=200, message='success', data={"port": self._latest_bot.remote_port})
        return response.json

    def _bot_list(self):
        response = Response(code=200, message='success',
                            data=[{"port": port, "info": data.get('info')} for port, data in self._bot.bots.items()])
        return response.json

    def _login_heartbeat(self):
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
        info = self._bot.get_bot(body.body.get('port')).get('info')
        response.data = {"status": True, "info": info}
        return response.json

    def _export_message_file(self):
        body = Request(body=request.json, body_keys=['port', 'wxid'])
        response = Response(code=200, message='success', data=None)
        if not body.check_body:
            response.code = 400
            response.message = '参数缺失'
            return response.json

        port = body.body.get('port')
        wxid = body.body.get('wxid')

        _bot = self._bot.get_bot(port)

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

    def _ai_chat(self):
        body = Request(body=request.json, body_keys=['port', 'messages'])
        response = Response(code=200, message='success', data=None)
        if not body.check_body:
            response.code = 400
            response.message = "参数错误，可能是微信未启动。  \n请先点击左侧 **登录微信** 按钮启动微信，并且登录。" if not body.body.get(
                'port') else '参数缺失'
            return response.json

        port = body.body.get('port')

        _bot = self._bot.get_bot(port)

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

            conversation_id = body.body.get('conversation_id')

            summary = None
            start_time = None
            new_conversation = False

            if not conversation_id:
                start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                summary = f"新对话 {start_time}"
                conversation_id = self._conversions_database.add_conversation(
                    user_id=_bot_info.get('wxid'),
                    start_time=start_time,
                    summary=summary
                )
                new_conversation = True

            conversation_id = int(conversation_id)
            self._conversions_database.add_message(
                conversation_id=conversation_id,
                role="user",
                content=body.body.get('messages')[-1].get('content'),
                timestamp=datetime.fromtimestamp(body.body.get('messages')[-1].get('createAt') / 1000).strftime(
                    "%Y-%m-%d %H:%M:%S"),
                visible=1,
                wechat_message_config=None,
                message_id=body.body.get('messages')[-1].get('message_id')
            )

            result = chat_with_glm(
                ask_message=body.body.get('messages'),
                prompt=f"""
            你是一个微信机器人助手，你的职责如下：
            - 今天是`{today}，现在是北京时间`{time_now}，`{week_day}`。
            - 用户的名字是`{_bot_info.get('name')}`，所以聊天记录中的`{_bot_info.get('name')}`是用户自己。
            - 总结用户的聊天内容，并给出回答；
            - 分析用户的需求，按需调用tools函数；
            - 当涉及到转发内容时，请先判断用户是否有指定原文，如果有原文：请你务必转发原文，不要篡改任何内容；
            """,
                function_tools=tools,
                _bot=_bot_object,
                conversation_id=conversation_id
            )

            response.data = {
                "message": result,
                "conversation_id": conversation_id,
                "new_conversation": new_conversation,
                "start_time": start_time,
                "summary": summary
            }

            self._conversions_database.add_message(
                conversation_id=conversation_id,
                role="assistant",
                content=result,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                visible=1,
                wechat_message_config=None,
                message_id=body.body.get('assistant_id')
            )

            return response.json

        except Exception as e:
            response.code = 500
            response.message = str(e)
            traceback.print_exc()
            return response.json

    def _handle_connect(self):
        print('Client connected to /api/ai/stream')

    def _handle_disconnect(self):
        print('Client disconnected from /api/ai/stream')

    def _handle_chat_message(self, data):
        if not data:
            emit('chat_message', "")
            disconnect()
            return

        body = Request(body=data, body_keys=['port', 'messages'])

        response = Response(code=200, message='success', data=None)

        if not body.check_body:
            response.code = 400
            response.message = "参数错误，可能是微信未启动。  \n请先点击左侧 **登录微信** 按钮启动微信，并且登录。" if not body.body.get(
                'port') else '参数缺失'
            emit('chat_message', response.json)
            disconnect()
            return

        port = body.body.get('port')

        _bot = self._bot.get_bot(port)

        if not _bot:
            response.code = 400
            response.message = '未找到对应端口的机器人'
            return response.json

        _bot_object = _bot.get('object')
        _bot_info = _bot.get('info')

        try:
            agent = WeBotAgent(
                mode_name="gemini-2.0-flash-exp",
                llm_options={
                    "temperature": 0.1,
                    "top_p": 0.1
                },
                webot_port=port
            )

            conversation_id = body.body.get('conversation_id')

            summary = None
            start_time = None
            new_conversation = False

            if not conversation_id:
                start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                summary = f"新对话 {start_time}"
                conversation_id = self._conversions_database.add_conversation(
                    user_id=_bot_info.get('wxid'),
                    start_time=start_time,
                    summary=summary
                )
                new_conversation = True

            conversation_id = int(conversation_id)
            self._conversions_database.add_message(
                conversation_id=conversation_id,
                role="user",
                content=body.body.get('messages')[-1].get('content'),
                timestamp=datetime.fromtimestamp(body.body.get('messages')[-1].get('createAt') / 1000).strftime(
                    "%Y-%m-%d %H:%M:%S"),
                visible=1,
                wechat_message_config=None,
                message_id=body.body.get('messages')[-1].get('message_id')
            )

            for event, message in agent.chat({"messages": body.body.get('messages')}):
                result = message.get('agent')
                if not result:
                    continue

                result = result.get('messages')[0].content
                response_message_id = str(uuid4())
                response_message_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                response.data = {
                    "message": result,
                    "conversation_id": conversation_id,
                    "new_conversation": new_conversation,
                    "start_time": start_time,
                    "summary": summary,
                    "message_id": response_message_id,
                    "message_time": response_message_time
                }

                self._conversions_database.add_message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=result,
                    timestamp=response_message_time,
                    visible=1,
                    wechat_message_config=None,
                    message_id=response_message_id
                )
                emit('chat_message', response.json)
            disconnect()
            return
        except Exception as e:
            response.code = 500
            response.message = str(e)
            traceback.print_exc()
            emit('chat_message', response.json)
            disconnect()

    def register_socketio_events(self):
        self.socketio.on('connect', namespace='/api/ai/stream')(self._handle_connect)
        self.socketio.on('disconnect', namespace='/api/ai/stream')(self._handle_disconnect)
        self.socketio.on('chat_message', namespace='/api/ai/stream')(self._handle_chat_message)

    @property
    def _route_map(self) -> List[Dict[str, Callable | str]]:
        return [
            {"rule": '/', "endpoint": "hello_world", "methods": ['GET'], "view_func": self._hello_world},
            {"rule": "/api/bot/start", "endpoint": "start", "methods": ['POST'], "view_func": self._start_bot},
            {"rule": "/api/bot/list", "endpoint": "bot_list", "methods": ['GET'], "view_func": self._bot_list},
            {"rule": "/api/bot/login_heartbeat", "endpoint": "login_heartbeat", "methods": ['POST'],
             "view_func": self._login_heartbeat},
            {"rule": "/api/bot/export_message_file", "endpoint": "export_message_file", "methods": ['POST'],
             "view_func": self._export_message_file},
            {"rule": "/api/ai/chat", "endpoint": "ai_chat", "methods": ['POST'], "view_func": self._ai_chat}
        ]

    def run(self, port: int = 16001, *args, **kwargs):
        for route in self._route_map:
            self.add_url_rule(**route)
        self.register_blueprint(ServiceConversations())
        self.register_socketio_events()
        super().run(port=port, *args, **kwargs)


if __name__ == '__main__':
    app = ServiceMain()
    app.run()
