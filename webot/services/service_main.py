import threading
import time
from datetime import datetime
from json import dumps
from threading import Thread, Event
from os import path
from typing import List, Dict, Callable, Union
from dataclasses import asdict
from uuid import uuid4
import traceback
import webbrowser

from webot.utils.project_path import ROOT_PATH, DATA_PATH, path
from webot.services.service_type import Response, Request
from webot.utils.toolkit import get_latest_wechat_version
from webot.bot.bot import WeBot
from webot.bot.bot_storage import BotStorage
from webot.services.service_conversations import ServiceConversations
from webot.services.service_llm import ServiceLLM
from webot.databases.conversation_database import ConversationsDatabase
from webot.databases.global_config_database import LLMConfigDatabase
from webot.agent.agent import WeBotAgent
from webot.bot.image_recognition import ImageRecognition

from flask import Flask, request, has_request_context, send_file, stream_with_context, Response as FlaskResponse, send_from_directory
from flask_cors import CORS
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
        self._llm_config_database = LLMConfigDatabase()

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

    # TODO: 需要增加聊天上下文 (优先级: 低)
    #   - 目前聊天超出LLM API上下文会直接返回API错误信息，但是目前可通过前端开启新对话规避，所以优先级不高。
    #   - 需要增加上下文摘要功能，达到阈值自动总结最前面的内容，缩短聊天。
    #   - 摘要上下文和前端展示上下文隔离问题需要考虑，展示需要全量
    #   - 需要考虑不同模型的上下文不同，并且用户自定义模型无法感知到上下文大小。
    #   - 获取微信聊天记录场景也要考虑，获取一份长聊天之后插入在上下文超长了，但实际LLM上下文可能就三四条。单条消息极端长的场景
    def _ai_stream(self):
        body = request.json
        port = body.get('port')
        message = body.get('message', '')

        model_result = self._llm_config_database.get_model_by_id(body.get('model_id'))
        if not model_result:
            return Response(code=400, message='模型不存在', data=None).json

        model_id, model_format_name, model_name, base_url, apikey, description, apikey_id = model_result

        if not apikey:
            return Response(code=400, message='apikey不存在', data=None).json

        _bot = self._bot.get_bot(port)

        conversation_id = self._create_conversation(body, _bot)
        user_message_id = str(uuid4())

        self._conversions_database.add_message(
            conversation_id=conversation_id,
            role="user",
            content=message,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            visible=1,
            wechat_message_config=dumps({"model_id": model_id}),
            message_id=user_message_id
        )

        all_messages = self._conversions_database.get_messages(conversation_id)
        all_messages = [
            {"role": "user" if _message.get('role') == 'user' else 'assistant', "content": _message.get('content')} for
            _message in all_messages if _message.get('content')]

        def event_stream():
            # 初始化响应流
            yield "data: [START]\n\n"
            try:

                agent = WeBotAgent(
                    model_name=model_name,
                    webot_port=port,
                    llm_options={"apikey": apikey, "base_url": base_url},
                    username=_bot.info.get('name')
                )

                original_assistant_message = {
                    "role": "assistant",
                    "contant": "",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "message_id": str(uuid4()),
                    "wechat_message_config": {
                        "pending": True,
                        "tools": []
                    },
                    "conversation_id": conversation_id
                }

                # 流式处理AI响应
                for event, message in agent.chat({"messages": all_messages}, thread_id=conversation_id):
                    print('=' * 10, message, '=' * 10)
                    chunk = self._process_message_chunk(message, conversation_id, user_message_id=user_message_id,
                                                        original_assistant_message=original_assistant_message)
                    if chunk:
                        yield f"data: {chunk}\n\n"
            except GeneratorExit as ge:
                raise ge
            except Exception as e:
                stack_trace = traceback.format_exc()
                format_err = f'{str(e)}\n {stack_trace}'
                self._save_message(
                    cid=conversation_id,
                    role="assistant",
                    content=format_err,
                    message_id=str(uuid4()),
                    wechat_message_config=dumps({"type": "error", "message": "后端出错"}),
                )
                yield f"""data: {dumps([{'role': 'assistant', 'content': format_err, 'wechat_message_config': '{"type": "error", "message": "后端出错"}'}])}\n\n"""
            finally:
                yield "data: [DONE]\n\n"

        return FlaskResponse(
            stream_with_context(event_stream()),
            mimetype="text/event-stream",
            headers={'X-Accel-Buffering': 'no'}  # 禁用Nginx缓冲
        )

    def _image_recognition(self):
        body = Request(body=request.json, body_keys=['model_id', 'wxid', 'start_time', "end_time", "port"])
        response = Response(code=200, message='success', data=None)
        if not body.check_body:
            response.code = 400
            response.message = '参数缺失'
            return response.json

        image_recognition = ImageRecognition(
            model_id=body.body.get('model_id'),
            port=body.body.get('port'),
        )

        def event_stream():
            yield "data: [START]\n\n"
            try:
                runner = image_recognition.run(
                    wxid=body.body.get('wxid'),
                    start_time=body.body.get('start_time'),
                    end_time=body.body.get('end_time'),
                    duration=body.body.get('duration', 1),
                    only_failed=body.body.get('only_failed', False),
                )

                for event in runner:
                    yield f'data: {event}\n\n'

            except Exception as e:
                yield f'data: {e}\n\n'
            finally:
                yield "data: [DONE]\n\n"

        return FlaskResponse(
            stream_with_context(event_stream()),
            mimetype="text/event-stream",
            headers={'X-Accel-Buffering': 'no'}  # 禁用Nginx缓冲
        )

    def _download_export_file(self, filename):

        if '..' in filename or filename.startswith('/'):
            return Response(code=400, message='Invalid filename', data=None).json
        export_dir = path.join(DATA_PATH, 'exports')
        file_path = path.join(export_dir, filename)

        if not path.exists(file_path):
            return Response(code=400, message='文件不存在', data=None).json

        try:
            return send_from_directory(
                directory=export_dir,
                path=filename,
                as_attachment=True,
                mimetype='application/octet-stream'
            )
        except Exception as e:
            return Response(code=400, message=str(e), data=None).json

    def _create_conversation(self, body, _bot):
        """创建新对话记录"""
        if not body.get('conversation_id') or body.get('conversation_id') == '':
            start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return self._conversions_database.add_conversation(
                user_id=_bot.get('info').get('wxid'),
                start_time=start_time,
                summary=f"新对话 {start_time}"
            )
        return body['conversation_id']

    def _process_message_chunk(self, message, conversation_id, user_message_id="", original_assistant_message={}):
        results = []

        def get_timestamp():
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if 'post_model_hook' in message:
            for msg in message['post_model_hook']['messages']:
                message_id = str(uuid4())
                content = msg.content
                if isinstance(content, list):
                    content = ''.join(content)
                # 使用getattr判断tool_calls是否存在且非空
                tool_calls = []
                if getattr(msg, 'tool_calls', None):
                    try:
                        tool_calls = [{
                            "call_id": tc.get('id'),
                            "tool_name": tc.get('function').get('name'),
                            "parameters": tc.get('function').get('arguments'),
                            "timestamp": get_timestamp(),
                            "type": 'tool_call'
                        } for tc in msg.additional_kwargs.get('tool_calls', [])]
                    except Exception as e:
                        print(f"Tool call解析失败: {e}")

                # 保存agent消息及其工具调用信息
                self._save_message(
                    cid=conversation_id,
                    content=content,
                    role='assistant' if len(tool_calls) == 0 else 'tools',
                    message_id=message_id,
                    wechat_message_config=dumps({
                        'tools': tool_calls,
                        "type": 'tool_call' if len(tool_calls) > 0 else 'assistant',
                        "user_message_id": user_message_id
                    })
                )

                results.append({
                    "message_id": message_id,
                    "conversation_id": conversation_id,
                    "timestamp": get_timestamp(),
                    "content": content,
                    'role': 'assistant' if len(tool_calls) == 0 else 'tools',
                    "wechat_message_config": dumps({
                        'tools': tool_calls,
                        "type": 'tool_call' if len(tool_calls) > 0 else 'assistant',
                        "user_message_id": user_message_id
                    })
                })

        elif 'tools' in message:
            for msg in message['tools']['messages']:
                message_id = str(uuid4())
                content = msg.content
                if isinstance(content, list):
                    content = ''.join(content)
                tool_result = {
                    "call_id": msg.tool_call_id,
                    "tool_name": msg.name,
                    "result": content,
                    "success": True,  # 根据实际业务可调整判断逻辑
                    "timestamp": get_timestamp(),
                    "type": 'tool_result'
                }

                self._save_message(
                    cid=conversation_id,
                    content=content,
                    role='tools',
                    message_id=message_id,
                    wechat_message_config=dumps({
                        "tools": tool_result,
                        "type": 'tool_result',
                        "user_message_id": user_message_id
                    })
                )

                results.append({
                    "message_id": message_id,
                    "conversation_id": conversation_id,
                    "timestamp": tool_result['timestamp'],
                    'role': 'tools',
                    'content': tool_result.get('result'),
                    "wechat_message_config": dumps({
                        "tools": tool_result,
                        "type": 'tool_result',
                        "user_message_id": user_message_id
                    })
                })

        return dumps(results, ensure_ascii=False)

    def _save_message(self, cid, content, role='assistant', wechat_message_config='', message_id=str(uuid4())):
        """保存消息到数据库"""
        if isinstance(wechat_message_config, dict) or isinstance(wechat_message_config, list):
            wechat_message_config = dumps(wechat_message_config)
        self._conversions_database.add_message(
            conversation_id=cid,
            role=role,
            content=content,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            visible=1,
            wechat_message_config=wechat_message_config,
            message_id=message_id
        )

    @property
    def _route_map(self) -> List[Dict[str, Union[Callable, str]]]:
        return [
            {"rule": '/', "endpoint": "hello_world", "methods": ['GET'], "view_func": self._hello_world},
            {"rule": "/api/bot/start", "endpoint": "start", "methods": ['POST'], "view_func": self._start_bot},
            {"rule": "/api/bot/list", "endpoint": "bot_list", "methods": ['GET'], "view_func": self._bot_list},
            {"rule": "/api/bot/login_heartbeat", "endpoint": "login_heartbeat", "methods": ['POST'],
             "view_func": self._login_heartbeat},
            {"rule": "/api/bot/export_message_file", "endpoint": "export_message_file", "methods": ['POST'],
             "view_func": self._export_message_file},
            {"rule": "/api/ai/stream", "endpoint": "ai_stream", "methods": ['POST'], "view_func": self._ai_stream},
            {"rule": "/api/bot/image_recognition", "endpoint": "image_recognition", "methods": ['POST'],
             "view_func": self._image_recognition},
            {"rule": "/api/bot/download_export_file/<filename>", "endpoint": "download_export_file", "methods": ['GET'],
             "view_func": self._download_export_file}
        ]

    @staticmethod
    def open_browser(wait_time=3, url="http://127.0.0.1:16001"):
        time.sleep(wait_time)
        webbrowser.open(url)

    def run(self, port: int = 16001, *args, **kwargs):
        for route in self._route_map:
            self.add_url_rule(**route)
        self.register_blueprint(ServiceConversations())
        self.register_blueprint(ServiceLLM())

        threading.Thread(target=self.open_browser, args=(0.5, f"http://127.0.0.1:{port}")).start()

        super().run(port=port, *args, **kwargs)


if __name__ == '__main__':
    app = ServiceMain()
    app.run()
