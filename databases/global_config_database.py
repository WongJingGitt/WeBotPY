from databases.local_database import LocalDatabase


class GlobalDatabase(LocalDatabase):

    def __init__(self, db_name="global_config", *args, **kwargs):
        super().__init__(db_name=db_name, *args, **kwargs)
        self._create_tables()
        self._model_init()

    def _create_tables(self):
        self.execute_query("""
        CREATE TABLE IF NOT EXISTS model_list (
            model_id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_format_name TEXT,
            model_name TEXT NOT NULL UNIQUE,
            base_url TEXT NOT NULL,
            apikey_id INTEGER,
            description TEXT
        ) 
        """, commit=True)
        self.execute_query("""
        CREATE TABLE IF NOT EXISTS apikey_list (
            apikey_id INTEGER PRIMARY KEY AUTOINCREMENT,
            apikey TEXT NOT NULL UNIQUE,
            description TEXT
        ) 
        """, commit=True)

    def _model_init(self):
        _base_model_list = [
            {"model_name": "glm-4-flash", "description": "免费的模型，可以前往<Text link={{href: 'https://open.bigmodel.cn/', target: '__blank'}}>智谱开放平台</Text>申请APIKEY使用", "base_url": "https://open.bigmodel.cn/api/paas/v4/", "model_format_name": "GLM4 Flash"},
            {"model_name": "gemini-2.0-flash-exp", "description": "免费的模型，需要翻墙，可以前往<Text link={{href: 'https://aistudio.google.com/app/apikey', target: '__blank'}}>谷歌AI Studio</Text>申请APIKEY使用", "base_url": "null", "model_format_name": "Gemini 2.0 Flash"},
            {"model_name": "qwen2.5", "description": "新用户赠送额度，可以前往<Text link={{href: 'https://bailian.console.aliyun.com/', target: '__blank'}}>阿里云百炼</Text>申请APIKEY使用", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model_format_name": "通义千问2.5"},
            {"model_name": "deepseek_v3", "description": "新用户赠送额度，可以前往<Text link={{href: 'https://platform.deepseek.com/', target: '__blank'}}>DeepSeek官方开放平台</Text>申请APIKEY使用", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model_format_name": "DeepSeek V3(官方)"},
            {"model_name": "doubao-1-5-pro-256k", "description": "新用户赠送额度，可以前往<Text link={{href: 'https://console.volcengine.com/ark', target: '__blank'}}>火山引擎</Text>申请APIKEY使用", "base_url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions", "model_format_name": "豆包1.5Pro 256K"},
            {"model_name": "deepseek-v3", "description": "新用户赠送额度，可以前往<Text link={{href: 'https://console.volcengine.com/ark', target: '__blank'}}>火山引擎</Text>申请APIKEY使用", "base_url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions", "model_format_name": "DeepSeek V3(火山引擎)"},
        ]
        for model in _base_model_list:
            # 判断模型是否存在
            if self.get_model_by_name(model.get("model_name")) is not None:
                continue
            self.add_model(**model)

    def add_model(self, model_name: str, description: str = None, base_url: str = None, apikey_id: int = None) -> int:
        """
        Add a new model to the database.
        :param model_name: The name of the model.
        :param description: An optional description of the model.
        :param base_url: The base URL of the model.
        :param apikey_id: The ID of the API key associated with the model.
        :return: The ID of the newly added model.
        """
        result = self.execute_query("""
        INSERT INTO model_list (model_name, description, base_url, apikey_id)
        VALUES (?, ?, ?, ?)
        """, (model_name, description, base_url, apikey_id), commit=True)
        return result.lastrowid

    def add_apikey(self, apikey: str, description: str = None) -> int:
        """
        Add a new API key to the database.
        :param apikey: The API key to add.
        :param description: An optional description of the API key.
        :return: The ID of the newly added API key.
        """
        result = self.execute_query("""
        INSERT INTO apikey_list (apikey, description)
        VALUES (?, ?)
        """, (apikey, description), commit=True)
        return result.lastrowid

    def get_model_list_with_apikey(self) -> list:
        """
        Get a list of all models with their associated API keys.
        :return: A list of tuples containing the model name, API key, and description.
        """
        result = self.execute_query("""
        SELECT model_list.model_name, apikey_list.apikey, model_list.description
        FROM model_list
        JOIN apikey_list ON model_list.apikey_id = apikey_list.apikey_id
        )""")
        return result.fetchall()

    def get_apikey_list(self) -> list:
        """
        Get a list of all API keys.
        :return: A list of tuples containing the API key and description.
        """
        result = self.execute_query("""
        SELECT apikey_list.apikey, apikey_list.description
        FROM apikey_list
        )""")
        return result.fetchall()

    def get_model_by_name(self, model_name: str) -> tuple:
        """
        Get a model by its name.
        :param model_name: The name of the model to retrieve.
        :return: A tuple containing the model name, API key, and description.
        """
        result = self.execute_query("""
        SELECT model_list.model_name, apikey_list.apikey, model_list.description
        FROM model_list
        JOIN apikey_list ON model_list.apikey_id = apikey_list.apikey_id
        WHERE model_list.model_name = ?
        """, (model_name,))
        return result.fetchone()

    def get_apikey_by_id(self, apikey_id: int) -> tuple:
        """
        Get an API key by its ID.
        :param apikey_id: The ID of the API key to retrieve.
        :return: A tuple containing the API key and description.
        """
        result = self.execute_query("""
        SELECT apikey_list.apikey, apikey_list.description
        FROM apikey_list
        WHERE apikey_list.apikey_id = ?
        """, (apikey_id,))
        return result.fetchone()

    def update_model_base_url(self, model_id: str, base_url: str) -> None:
        """
        Update the base URL of a model.
        :param model_id: The ID of the model to update.
        :param base_url: The new base URL.
        """
        self.execute_query("""
        UPDATE model_list
        SET base_url = ?
        WHERE model_list.model_id = ?
        """, (base_url, model_id), commit=True)

    def update_model_format_name(self, model_id: str, model_format_name: str) -> None:
        """
        Update the format name of a model.
        :param model_id: The ID of the model to update.
        :param model_format_name: The new format name.
        """
        self.execute_query("""
        UPDATE model_list
        SET model_format_name = ?
        WHERE model_list.model_id = ?
        """, (model_format_name, model_id), commit=True)

    def update_model_name(self, model_id: str, model_name: str) -> None:
        """
        Update the name of a model.
        :param model_id: The ID of the model to update.
        :param model_name: The new name.
        """
        self.execute_query("""
        UPDATE model_list
        SET model_name = ?
        WHERE model_list.model_id = ?
        """, (model_name, model_id), commit=True)
    def update_model_apikey(self, model_id: str, apikey_id: int) -> None:
        """
        Update the API key associated with a model.
        :param model_id: The ID of the model to update.
        :param apikey_id: The ID of the new API key.
        """
        self.execute_query("""
        UPDATE model_list
        SET apikey_id = ?
        WHERE model_list.model_id = ?
        """, (apikey_id, model_id), commit=True)

    def update_model_description(self, model_name: str, description: str) -> None:
        """
        Update the description of a model.
        :param model_name: The name of the model to update.
        :param description: The new description.
        """
        self.execute_query("""
        UPDATE model_list
        SET description = ?
        WHERE model_list.model_name = ?
        """, (description, model_name), commit=True)

    def update_apikey_description(self, apikey: str, description: str) -> None:
        """
        Update the description of an API key.
        :param apikey: The API key to update.
        :param description: The new description.
        """
        self.execute_query("""
        UPDATE apikey_list
        SET description = ?
        WHERE apikey_list.apikey = ?
        """, (description, apikey), commit=True)

    def delete_model(self, model_id: str) -> None:
        """
        Delete a model from the database.
        :param model_id: The ID of the model to delete.
        """
        self.execute_query("""
        DELETE FROM model_list
        WHERE model_list.model_id = ?
        """, (model_id,), commit=True)

    def delete_apikey(self, apikey: str) -> None:
        """
        Delete an API key from the database.
        :param apikey: The API key to delete.
        """
        self.execute_query("""
        DELETE FROM apikey_list
        WHERE apikey_list.apikey = ?
        """, (apikey,), commit=True)

    def check_model_apikey(self, model_id: str) -> bool:
        """
        判断模型是否设置了APIKEY
        :param model_id: The id of the model to check.
        :return: True if the model has an associated API key, False otherwise.
        """
        result = self.execute_query("""
        SELECT apikey_id FROM model_list
        WHERE model_list.model_id = ?
        """, (model_id,))
        return result.fetchone() is not None
