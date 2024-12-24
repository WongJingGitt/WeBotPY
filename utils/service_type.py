from dataclasses import dataclass
from typing import Any, Dict, Callable


@dataclass
class Response:

    code: int
    data: Any
    message: str

    @property
    def json(self) -> Dict:
        return {
            "code": self.code,
            "data": self.data,
            "message": self.message
        }

    def set_data(self, function: Callable, *args, **kwargs):
        """
        用作动态设置返回数据，首个参数为函数，后续参数为函数的参数
        :param function: 需要执行的函数，返回值将作为data
        :return:
        """
        if not callable(function):
            self.message = 'Function is not callable'
            self.code = 500
            return
        result = None
        try:
            result = function(*args, **kwargs)
        except Exception as e:
            self.code = 500
            self.message = str(e)
        finally:
            self.data = result


@dataclass
class Request:

    body: dict = None
    body_keys: list = None
    query: dict = None
    query_keys: list = None

    @property
    def check_body(self):
        if self.body_keys:
            for item in self.body_keys:
                if item not in self.body:
                    return False
        return True

