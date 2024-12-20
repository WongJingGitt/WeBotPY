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
    pass


def on_before_message(bot: WeBot, event: Event):
    # print("消息事件处理之前")
    pass


def on_after_message(bot: WeBot, event: Event):
    # print("消息事件处理之后")
    pass


class Runner(Cmd):
    prompt = ""
    intro = "欢迎使用WeBot，输入help查看帮助信息"

    def __init__(self):
        super().__init__()
        self._status = 0
        self._bot: WeBot = None
        self._in_conversation = False

    def on_login(self, bot: WeBot, event: Event):
        self.prompt = "WeBot> "
        print()
        print("登录成功")
        print()

    def _start_bot(self):
        bot = WeBot(
            faked_version="3.9.12.17",  # 解除微信低版本限制
            on_login=self.on_login,
            on_start=on_start,
            on_stop=on_stop,
            on_before_message=on_before_message,
            on_after_message=on_after_message
        )

        @bot.handle(events.TEXT_MESSAGE)
        def on_message(bot: WeBot, event: Event):
            pass

        bot.run()
        self._bot = bot
        self._status = 1

    def do_start(self, arg):
        if self._status == 0:
            t = Thread(target=self._start_bot)
            t.daemon = True
            t.start()

    def do_summary_char(self, arg):
        # if self._status == 0:
        #     print("请先启动WeBot")
        #     return
        parser = ArgumentParser()
        parser.add_argument('-n', '--name', type=str, help='根据微信名。')
        parser.add_argument('-r', '--remark', type=str, help='根据备注。')
        # parser.add_argument('-p', '--path', type=str, help='导出的文件路径。', default="./")
        namespace = None
        try:
            namespace = parser.parse_args(arg.split())
        except SystemExit as E:
            print("参数错误:", E)

        if not namespace:
            print("请输入关键字")
            return

        _keyword = None
        _type = None
        if namespace.remark:
            _keyword = namespace.remark
            _type = "remark"
        else:
            _keyword = namespace.name
            _type = "name"

        if not _keyword:
            print("请输入关键字")
            return

        search_result = self._bot.get_contact(keyword=_keyword, _type=_type)
        if len(search_result) < 1:
            print("未找到该用户")
            return

        contact = search_result[0]

        print(contact)
        # TODO: 考虑使用React写页面直接调用API来搞


if __name__ == '__main__':
    Runner().cmdloop()
