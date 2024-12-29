from typing import Dict

from libs.webot import WeBot


class BotStorage(dict):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_bot(self, port) -> Dict[str, Dict | WeBot] | None:
        """
        通过端口号获取bot对象
        :param port: 端口号
        :return: 返回一个字典 { "object": WeBot实例化对象, "info": 字典，当前账号的信息 }
        """
        return self.get(port, {})

