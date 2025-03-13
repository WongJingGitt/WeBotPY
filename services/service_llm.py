from services.service_type import Response, Request
from databases.global_config_database import LLMConfigDatabase

from flask import Blueprint, request

class ServiceLLM(Blueprint):

    def __init__(self, name: str = 'llm', import_name=__name__, *args, **kwargs):
        super().__init__(name, import_name, *args, **kwargs)
        self._db: LLMConfigDatabase = LLMConfigDatabase()
        for route in self._route_map:
            self.add_url_rule(**route)


    @property
    def _route_map(self) -> list[dict[str, callable or str]]:
        return [
            {'rule': '/api/model/model/add','view_func': self._add_model,'methods': ['POST'], 'endpoint': 'add_model'},
            {'rule': '/api/model/apikey/add','view_func': self._add_apikey,'methods': ['POST'], 'endpoint': 'add_apikey'},
            {'rule': '/api/models', 'view_func': self._get_models, 'methods': ['GET'], 'endpoint': 'get_models'},
            {'rule': '/api/model/<int:model_id>', 'view_func': self._get_model, 'methods': ['GET'],
             'endpoint': 'get_model'},
            {'rule': '/api/model/update', 'view_func': self._update_model, 'methods': ['PUT'],
             'endpoint': 'update_model'},
            {'rule': '/api/model/delete', 'view_func': self._delete_model, 'methods': ['DELETE'],
             'endpoint': 'delete_model'},
            {'rule': '/api/apikeys', 'view_func': self._get_apikeys, 'methods': ['GET'], 'endpoint': 'get_apikeys'},
            {'rule': '/api/apikey/delete', 'view_func': self._delete_apikey, 'methods': ['DELETE'],
             'endpoint': 'delete_apikey'},
            {'rule': '/api/apikey/update', 'view_func': self._update_apikey_desc, 'methods': ['PUT'],
             'endpoint': 'update_apikey_desc'},
        ]


    def _add_model(self):
        _request = Request(body=request.json, body_keys=['model_format_name', 'model_name'])
        _response = Response(code=200, message='success', data=None)

        if not _request.check_body:
            _response.code = 400
            _response.message = '参数缺失'
            return _response.json

        model_id = self._db.add_model(**_request.body)
        if model_id:
            _response.data = model_id
        else:
            _response.code = 500
            _response.message = '添加失败'
        return _response.json


    def _add_apikey(self):
        _request = Request(body=request.json, body_keys=['apikey', 'description'])
        _response = Response(code=200, message='success', data=None)

        if not _request.check_body:
            _response.code = 400
            _response.message = '参数缺失'
            return _response.json

        apikey_id = self._db.add_apikey(**_request.body)
        if apikey_id:
            _response.data = apikey_id
        else:
            _response.code = 500
            _response.message = '添加失败'

        return _response.json

    def _get_models(self):
        """获取所有模型列表（含APIKEY）"""
        _response = Response(code=200, message='success', data=None)
        try:
            models = self._db.get_model_list()
            _response.data = [dict(zip(["model_id","model_name", "model_format_name", "description", "base_url", "apikey_id"], m)) for m in models]
        except Exception as e:
            _response.code = 500
            _response.message = f'查询失败: {str(e)}'
        return _response.json

    def _get_model(self, model_id: int):
        """根据ID获取单个模型详情"""
        _response = Response(code=200, message='success', data=None)
        model = self._db.get_model_by_id(model_id)
        if model:
            result = dict(zip(
                ['model_id', 'model_format_name', 'model_name', 'base_url', 'apikey', 'description', 'apikey_id'],
                model
            ))
            result.pop('apikey')
            _response.data = result
        else:
            _response.code = 404
            _response.message = '模型不存在'
        return _response.json

    def _update_model(self):
        """更新模型信息（通用更新）"""
        _request = Request(
            body=request.json,
            body_keys=['model_id', 'field', 'value'],
        )
        _response = Response(code=200, message='更新成功', data=None)

        if not _request.check_body or _request.body['field'] not in _request.body.get('field') not in ['model_name', 'model_format_name', 'base_url', 'apikey_id', 'description']:
            _response.code = 400
            _response.message = '非法参数'
            return _response.json

        update_map = {
            'model_name': self._db.update_model_name,
            'model_format_name': self._db.update_model_format_name,
            'base_url': self._db.update_model_base_url,
            'apikey_id': self._db.update_model_apikey,
            'description': self._db.update_model_description
        }

        try:
            update_map[_request.body['field']](_request.body['model_id'], _request.body['value'])
        except Exception as e:
            _response.code = 500
            _response.message = f'更新失败: {str(e)}'

        return _response.json

    def _delete_model(self):
        """删除指定模型"""
        _request = Request(body=request.json, body_keys=['model_id'])
        _response = Response(code=200, message='删除成功', data=None)

        if not _request.check_body:
            _response.code = 400
            _response.message = '需要model_id参数'
            return _response.json

        try:
            self._db.delete_model(_request.body['model_id'])
        except Exception as e:
            _response.code = 500
            _response.message = f'删除失败: {str(e)}'

        return _response.json

    def _get_apikeys(self):
        """获取所有APIKEY列表"""
        _response = Response(code=200, message='success', data=None)
        try:
            keys = self._db.get_apikey_list()
            _response.data = [dict(zip(['apikey_id', 'description'], k)) for k in keys]
        except Exception as e:
            _response.code = 500
            _response.message = f'查询失败: {str(e)}'
        return _response.json

    def _delete_apikey(self):
        """删除指定APIKEY"""
        _request = Request(body=request.json, body_keys=['apikey'])
        _response = Response(code=200, message='删除成功', data=None)

        if not _request.check_body:
            _response.code = 400
            _response.message = '需要apikey参数'
            return _response.json

        try:
            self._db.delete_apikey(_request.body['apikey'])
        except Exception as e:
            _response.code = 500
            _response.message = f'删除失败: {str(e)}'

        return _response.json

    def _update_apikey_desc(self):
        """更新APIKEY描述"""
        _request = Request(body=request.json, body_keys=['apikey', 'description'])
        _response = Response(code=200, message='更新成功', data=None)

        if not _request.check_body:
            _response.code = 400
            _response.message = '参数缺失'
            return _response.json

        try:
            self._db.update_apikey_description(
                _request.body['apikey'],
                _request.body['description']
            )
        except Exception as e:
            _response.code = 500
            _response.message = f'更新失败: {str(e)}'

        return _response.json