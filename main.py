# import os
# os.environ["WXHOOK_LOG_LEVEL"] = "INFO" # 修改日志输出级别
# os.environ["WXHOOK_LOG_FORMAT"] = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{message}</level>" # 修改日志输出格式
import sys
from os import remove, path
from json import loads

from wxhook import events
from wxhook.model import Event

from libs.webot import WeBot
from libs.message import TextMessage
from utils.chat_glm import chat_glm
from libs.message import TextMessageFromDB


ROOT_PATH = path.dirname(path.abspath(__file__))


def on_login(bot: WeBot, event: Event):
    # print("登录成功之后会触发这个函数")
    pass


def on_start(bot: WeBot):
    # print("微信客户端打开之后会触发这个函数")
    pass


def on_stop(bot: WeBot):
    # print("关闭微信客户端之前会触发这个函数")
    pass


def on_before_message(bot: WeBot, event: Event):
    # print("消息事件处理之前")
    pass


def on_after_message(bot: WeBot, event: Event):
    # print("消息事件处理之后")
    pass


bot = WeBot(
    faked_version="3.9.12.17",  # 解除微信低版本限制
    on_login=on_login,
    on_start=on_start,
    on_stop=on_stop,
    on_before_message=on_before_message,
    on_after_message=on_after_message
)


# 消息回调地址
# bot.set_webhook_url("http://127.0.0.1:8000")

@bot.handle(events.TEXT_MESSAGE)
def on_message(bot: WeBot, event: Event):
    pass
    # text_message = TextMessage(**event.__dict__, bot=bot)
    # talker = bot.get_contact(text_message.fromUser)
    # if len(talker) > 0:
    #     if int(talker[0].type) == 1:
    #         return

    # if not text_message.room:
    #     return
    #
    # if text_message.room and not text_message.mention_me:
    #     return
    #
    # message_detail = text_message.message_detail
    #
    # # flag_text = "来自群聊" if text_message.room else "来自私聊"
    # ask_messages = []
    #
    # message_list = bot.get_message_from_db(text_message.fromUser, 1000)
    #
    # for item in message_list:
    #     md = TextMessageFromDB(*item)
    #     talker_id = md.talker_id
    #     talker_detail = bot.get_concat_profile(talker_id).data or {}
    #     talker_name = talker_detail.get('nickname', "")
    #
    #     # 解析完的wxid。有的联系人的wxid会是自定义的，自定义最少需要6位，如果解析完wxid少余6位则可以判定为自己。
    #     role = "assistant" if 0 < len(talker_id) < 6 else "user"
    #     content = md.content if role == 'assistant' else f"{talker_name}：{md.content.replace('@王大锤', '')}"
    #     ask_messages.append({'role': role, 'content': content})
    #
    # ask_messages.append({'role': 'user', 'content': '简洁的回复，不用携带前缀，内容多时可以使用Emoji进行适当的排版。'})
    # result = chat_glm(ask_messages)
    #
    # print(result)
    #
    # if result.content:
    #     text_message.reply_text(f"\n{result.content}", [message_detail.from_user])
    #     return


bot.run()
