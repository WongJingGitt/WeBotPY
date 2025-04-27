from dataclasses import dataclass, field
from typing import Any, Dict, Callable, Literal


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
                if item not in self.body or not self.body.get(item):
                    return False
        return True

    @property
    def check_query(self):
        if self.query_keys:
            for item in self.query_keys:
                if item not in self.query or not self.query.get(item):
                    return False
        return True

@dataclass
class Router:
    rule: str
    endpoint: str | None = None
    view_func: Callable or None = None
    provide_automatic_options: bool | None = None
    methods: Literal['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'] | None = 'GET'
    options: Dict[str, Any] = field(default_factory=dict)

    @property
    def json(self) -> Dict:
        return {
            "rule": self.rule,
            "endpoint": self.endpoint,
            "view_func": self.view_func,
            "provide_automatic_options": self.provide_automatic_options,
            "methods": self.methods,
            **self.options
        }
