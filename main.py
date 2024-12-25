# import os
# os.environ["WXHOOK_LOG_LEVEL"] = "INFO" # 修改日志输出级别
# os.environ["WXHOOK_LOG_FORMAT"] = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{message}</level>" # 修改日志输出格式
from os import remove, path
from cmd import Cmd
from argparse import ArgumentParser
from threading import Thread

from wxhook import events
from wxhook.model import Event

from libs.webot import WeBot

ROOT_PATH = path.dirname(path.abspath(__file__))


def on_start(bot: WeBot):
    # print("微信客户端打开之后会触发这个函数")
    pass


def on_stop(bot: WeBot):
    # print("关闭微信客户端之前会触发这个函数")
    print('bot stop')


def on_before_message(bot: WeBot, event: Event):
    # print("消息事件处理之前")
    pass


def on_after_message(bot: WeBot, event: Event):
    # print("消息事件处理之后")
    pass


bot = WeBot(
    faked_version="3.9.12.17",  # 解除微信低版本限制
    on_start=on_start,
    on_stop=on_stop,
    on_before_message=on_before_message,
    on_after_message=on_after_message
)


@bot.handle(events.TEXT_MESSAGE)
def on_message(bot: WeBot, event: Event):
    pass


bot.run()
