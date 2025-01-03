from utils.service_type import Response, Request
from utils.local_database import ConversationsDatabase
from utils.bot_storage import BotStorage, BotItem

from flask import Blueprint, request


class ServiceConversations(Blueprint):

    def __init__(self, name: str = 'conversation', import_name=__name__, *args, **kwargs):
        super().__init__(name, import_name, *args, **kwargs)
        self._bot: BotStorage = BotStorage()
        for rule in self._route_map:
            self.add_url_rule(**rule)

    @property
    def _route_map(self):
        return [
            {"rule": "/api/conversations/list", "endpoint": "conversations_list", "methods": ['POST'],
             "view_func": self._conversations_list},
            {"rule": "/api/conversations/messages", "endpoint": "conversations_messages", "methods": ['POST'],
             "view_func": self._conversations_messages},
            {"rule": "/api/conversations/messages/delete", "endpoint": "conversations_messages_delete",
             "methods": ['POST'],
             "view_func": self._conversations_messages_delete},
            {"rule": "/api/conversations/delete", "endpoint": "conversations_delete", "methods": ['POST'],
             "view_func": self._conversations_delete},
            {"rule": "/api/conversations/summary/update", "endpoint": "conversations_summary_update",
             "methods": ['POST'],
             "view_func": self._conversations_summary_update},
        ]

    def _conversations_list(self):
        body = Request(body=request.json, body_keys=['port'])
        response = Response(code=200, message='success', data=None)
        _bot = self._bot.get_bot(body.body.get('port'))
        _conversations = ConversationsDatabase().get_conversation_by_user(_bot.get('info').get('wxid'))
        response.data = _conversations
        return response.json

    def _conversations_messages(self):
        body = Request(body=request.json, body_keys=['port', 'conversation_id'])
        response = Response(code=200, message='success', data=None)
        _bot = self._bot.get_bot(body.body.get('port'))
        _conversations = ConversationsDatabase().get_messages(body.body.get('conversation_id'))
        response.data = _conversations
        return response.json

    def _conversations_messages_delete(self):
        body = Request(body=request.json, body_keys=['port', 'message_id'])
        response = Response(code=200, message='success', data=None)
        ConversationsDatabase().delete_message(body.body.get('message_id'))
        return response.json

    def _conversations_delete(self):
        body = Request(body=request.json, body_keys=['port', 'conversation_id'])
        response = Response(code=200, message='success', data=None)
        ConversationsDatabase().delete_conversation(body.body.get('conversation_id'))
        return response.json

    def _conversations_summary_update(self):
        body = Request(body=request.json, body_keys=['port', 'conversation_id', 'summary'])
        if not body.check_body:
            return Response(code=400, message='body error', data=None).json
        response = Response(code=200, message='success', data=None)
        ConversationsDatabase().update_conversation_summary(body.body.get('conversation_id'), body.body.get('summary'))
        return response.json
