from typing import Dict
from dataclasses import dataclass

from webot.bot.bot import WeBot


@dataclass
class BotItem:
    object: WeBot
    info: Dict[str, str] = None

    def get(self, key: str):
        return self.__dict__.get(key, None)


class BotStorage:
    instances = None
    bots: Dict[int, BotItem] = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __new__(cls, *args, **kwargs):
        if not cls.instances:
            cls.instances = super().__new__(cls)
            cls.bots = {}
        return cls.instances

    def set_bot(self, port: int, bot: WeBot, info: Dict[str, str] = None) -> None:
        """
        添加一个bot对象
        :param port: 端口号
        :param bot: WeBot实例化对象
        :param info: 字典，当前账号的信息
        :return: None
        """
        self.bots[port] = BotItem(bot, info)

    def get_bot(self, port) -> BotItem:
        """
        通过端口号获取bot对象
        :param port: 端口号
        :return: 返回一个字典 { "object": WeBot实例化对象, "info": 字典，当前账号的信息 }
        """
        return self.bots.get(port, {})