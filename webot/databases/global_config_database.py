from webot.databases.local_database import LocalDatabase


class LLMConfigDatabase(LocalDatabase):

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
            {"model_name": "glm-4-flash",
             "description": "免费的模型，可以前往<a href='https://open.bigmodel.cn/' target='__blank'>智谱开放平台</a>申请APIKEY使用",
             "base_url": "https://open.bigmodel.cn/api/paas/v4/", "model_format_name": "GLM4 Flash"},
            {"model_name": "gemini-2.0-flash-exp",
             "description": "免费的模型，需要翻墙，可以前往<a href='https://aistudio.google.com/app/apikey' target='__blank'>谷歌AI Studio</a>申请APIKEY使用",
             "base_url": "null", "model_format_name": "Gemini 2.0 Flash"},
            {"model_name": "qwen2.5-14b-instruct-1m",
             "description": "新用户赠送额度，可以前往<a href='https://bailian.console.aliyun.com/' target='__blank'>阿里云百炼</a>申请APIKEY使用",
             "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model_format_name": "通义千问2.5"},
            {"model_name": "deepseek-chat",
             "description": "新用户赠送额度，可以前往<a href='https://platform.deepseek.com/' target='__blank'>DeepSeek官方开放平台</a>申请APIKEY使用",
             "base_url": "https://api.deepseek.com", "model_format_name": "DeepSeek V3(官方)"},
            # {"model_name": "doubao-1-5-pro-256k-250115", "description": "新用户赠送额度，可以前往<a href='https://console.volcengine.com/ark' target='__blank'>火山引擎</a>申请APIKEY使用", "base_url": "https://ark.cn-beijing.volces.com/api/v3/", "model_format_name": "豆包1.5Pro 256K"},
            {"model_name": "deepseek-v3-241226",
             "description": "新用户赠送额度，可以前往<a href='https://console.volcengine.com/ark' target='__blank'>火山引擎</a>申请APIKEY使用",
             "base_url": "https://ark.cn-beijing.volces.com/api/v3/", "model_format_name": "DeepSeek V3(火山引擎)"}
        ]
        for model in _base_model_list:
            if self.get_model_by_name(model.get("model_name")) is None:
                self.add_model(**model)

    def add_model(self, model_format_name: str, model_name: str, description: str = None, base_url: str = None,
                  apikey_id: int = None) -> int:
        """
        添加新模型到数据库
        :param model_format_name: 模型格式名称
        :param model_name: 模型名称（唯一）
        :param description: 模型描述（可选）
        :param base_url: 模型基础URL
        :param apikey_id: 关联的APIKEY ID（可选）
        :return: 新插入模型的ID
        """
        result = self.execute_query("""
        INSERT INTO model_list (model_format_name, model_name, description, base_url, apikey_id)
        VALUES (?, ?, ?, ?, ?)
        """, (model_format_name, model_name, description, base_url, apikey_id), commit=True)
        return result.lastrowid

    def add_apikey(self, apikey: str, description: str = None) -> int:
        """
        添加新的APIKEY到数据库
        :param apikey: 需要添加的APIKEY
        :param description: APIKEY描述（可选）
        :return: 新插入APIKEY的ID
        """
        result = self.execute_query("""
        INSERT INTO apikey_list (apikey, description)
        VALUES (?, ?)
        """, (apikey, description), commit=True)
        return result.lastrowid

    def get_model_list_with_apikey(self) -> list:
        """
        获取所有模型及其关联的APIKEY列表
        :return: 包含（模型名称, APIKEY, 描述）的元组列表
        """
        result = self.execute_query("""
        SELECT m.model_id, m.model_format_name, m.model_name, a.apikey, m.description, m.base_url
        FROM model_list m
        LEFT JOIN apikey_list a ON m.apikey_id = a.apikey_id
        """)
        return result.fetchall()

    def get_model_list(self) -> list:
        """
        获取所有模型列表，不包含明文APIKEY
        :return: 包含（模型名称, 模型格式名称, 模型描述, 模型基础URL）的元组列表
        """
        result = self.execute_query("""
        SELECT model_id, model_name, model_format_name, description, base_url, apikey_id
        FROM model_list
        """)
        return result.fetchall()

    def get_model_by_id(self, model_id: int) -> tuple:
        """
        根据模型ID获取完整模型信息（包含关联的APIKEY明文）
        :param model_id: 需要查询的模型ID
        :return: 包含完整信息的元组（model_id, model_format_name, model_name, base_url, apikey, description, apikey_id）
        """
        result = self.execute_query("""
        SELECT m.model_id, m.model_format_name, m.model_name, m.base_url, a.apikey, m.description, m.apikey_id
        FROM model_list m
        LEFT JOIN apikey_list a ON m.apikey_id = a.apikey_id
        WHERE m.model_id = ?
        """, (model_id,))
        return result.fetchone()

    def get_apikey_list(self) -> list:
        """
        获取所有APIKEY列表
        :return: 包含（APIKEY, 描述）的元组列表
        """
        result = self.execute_query("""
        SELECT apikey_id, description 
        FROM apikey_list
        """)
        return result.fetchall()

    def get_model_by_name(self, model_name: str) -> tuple:
        """
        根据模型名称获取完整模型信息
        :param model_name: 需要查询的模型名称
        :return: 包含模型完整信息的元组
        """
        result = self.execute_query("""
        SELECT model_id, model_format_name, model_name, base_url, apikey_id, description
        FROM model_list
        WHERE model_name = ?
        """, (model_name,))
        return result.fetchone()

    def get_apikey_by_id(self, apikey_id: int) -> tuple:
        """
        根据ID获取APIKEY信息
        :param apikey_id: 需要查询的APIKEY ID
        :return: 包含（APIKEY, 描述）的元组
        """
        result = self.execute_query("""
        SELECT apikey, description
        FROM apikey_list
        WHERE apikey_id = ?
        """, (apikey_id,))
        return result.fetchone()

    def update_model_base_url(self, model_id: int, base_url: str) -> None:
        """
        更新模型基础URL
        :param model_id: 需要更新的模型ID
        :param base_url: 新的基础URL
        """
        self.execute_query("""
        UPDATE model_list
        SET base_url = ?
        WHERE model_id = ?
        """, (base_url, model_id), commit=True)

    def update_model_format_name(self, model_id: int, model_format_name: str) -> None:
        """
        更新模型格式名称
        :param model_id: 需要更新的模型ID
        :param model_format_name: 新的格式名称
        """
        self.execute_query("""
        UPDATE model_list
        SET model_format_name = ?
        WHERE model_id = ?
        """, (model_format_name, model_id), commit=True)

    def update_model_name(self, model_id: int, model_name: str) -> None:
        """
        更新模型名称
        :param model_id: 需要更新的模型ID
        :param model_name: 新的模型名称
        """
        self.execute_query("""
        UPDATE model_list
        SET model_name = ?
        WHERE model_id = ?
        """, (model_name, model_id), commit=True)

    def update_model_apikey(self, model_id: int, apikey_id: int) -> None:
        """
        更新模型关联的APIKEY
        :param model_id: 需要更新的模型ID
        :param apikey_id: 新的APIKEY ID
        """
        self.execute_query("""
        UPDATE model_list
        SET apikey_id = ?
        WHERE model_id = ?
        """, (apikey_id, model_id), commit=True)

    def update_model_description(self, model_name: str, description: str) -> None:
        """
        更新模型描述信息
        :param model_name: 需要更新的模型名称
        :param description: 新的描述内容
        """
        self.execute_query("""
        UPDATE model_list
        SET description = ?
        WHERE model_name = ?
        """, (description, model_name), commit=True)

    def update_apikey_description(self, apikey_id: int, description: str) -> None:
        """
        更新APIKEY描述信息
        :param apikey: 需要更新的APIKEY
        :param description: 新的描述内容
        """
        self.execute_query("""
        UPDATE apikey_list
        SET description = ?
        WHERE apikey_id = ?
        """, (description, apikey_id), commit=True)

    def delete_model(self, model_id: int) -> None:
        """
        删除指定模型
        :param model_id: 需要删除的模型ID
        """
        self.execute_query("""
        DELETE FROM model_list
        WHERE model_id = ?
        """, (model_id,), commit=True)

    def delete_apikey_by_id(self, apikey_id: int) -> None:
        """
        删除指定APIKEY
        :param apikey: 需要删除的APIKEY
        """
        self.execute_query("""
        DELETE FROM apikey_list
        WHERE apikey_id = ?
        """, (apikey_id,), commit=True)

    def check_model_apikey(self, model_id: int) -> bool:
        """
        检查模型是否设置有效APIKEY
        :param model_id: 需要检查的模型ID
        :return: 存在有效APIKEY返回True，否则返回False
        """
        result = self.execute_query("""
        SELECT apikey_id 
        FROM model_list 
        WHERE model_id = ? AND apikey_id IS NOT NULL
        """, (model_id,))
        return result.fetchone() is not None


class MemoryDatabase(LocalDatabase):
    def __init__(self, db_name: str = "memory_database", *args, **kwargs):
        super().__init__(db_name)
        self._create_table()

    def _create_table(self):
        """
        from_user: 记忆归属者主账号，也就是属于哪个登录的账户，传wxid。
        to_user: 记忆的对象，也就是关于谁的记忆，传wxid在获取该用户的聊天时传入。
        type: 记忆类型，目前规划：
            - event: 重要事件记录
            - topic: 长期话题记录
            - social_network: 成员关系网(针对群聊)
            - nickname: 别称记录。
            - keyword: 高频关键字记录与解释。
            - summary: 针对群聊的额外总结。
        event_time: 事件发生时间。
        """
        sql = """
CREATE TABLE IF NOT EXISTS memory (
    memory_id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_user TEXT,
    to_user TEXT,
    type TEXT,
    content TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    event_time DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""
        self.execute_query(sql, commit=True)

    def add_memory(self, from_user: str, to_user: str, type: str, content: str, event_time: str = None) -> int:
        """
        添加一条记忆记录。
        :param from_user: 记忆归属者主账号，也就是属于哪个登录的账户，传wxid。
        :param to_user: 记忆的对象，也就是关于谁的记忆，传wxid在获取该用户的聊天时传入。
        :param type: 记忆类型，目前规划：
            - event: 重要事件记录
            - topic: 长期话题记录
            - social_network: 成员关系网(针对群聊)
            - nickname: 别称记录。
            - keyword: 高频关键字记录与解释。
            - summary: 针对群聊的额外总结。
        :param content: 记忆内容。
        :return: 记忆ID。
        """
        sql = """
INSERT INTO memory (from_user, to_user, type, content, event_time) VALUES (?, ?, ?, ?, ?)
"""
        result = self.execute_query(sql, (from_user, to_user, type, content, event_time), commit=True)
        return result.lastrowid

    def get_memory(self, from_user: str, to_user: str, type: str = None, event_time: str = None) -> list:
        """
        获取记忆记录。
        :param from_user: 记忆归属者主账号，也就是属于哪个登录的账户，传wxid。
        :param to_user: 记忆的对象，也就是关于谁的记忆，传wxid在获取该用户的聊天时传入。
        :param type: 记忆类型，目前规划：
            - event: 重要事件记录
            - topic: 长期话题记录
            - social_network: 成员关系网(针对群聊)
            - nickname: 别称记录。
            - keyword: 高频关键字记录与解释。
            - summary: 针对群聊的额外总结。
        :param event_time: 事件发生时间。
        :return: 记忆记录列表。
        """
        sql = """
SELECT memory_id, type, content, event_time, created_at FROM memory WHERE from_user = ? AND to_user = ?
"""
        if type:
            sql += " AND type = ?"
            params = (from_user, to_user, type)
        else:
            params = (from_user, to_user)

        if event_time:
            sql += " AND event_time = ?"
            params += (event_time,)
        result = self.execute_query(sql, params)
        return result.fetchall()

    def delete_memory(self, memory_id: int) -> None:
        """
        删除一条记忆记录。
        :param memory_id: 记忆ID。
        """
        sql = """
DELETE FROM memory WHERE memory_id = ?
"""
        self.execute_query(sql, (memory_id,), commit=True)

    def update_memory(self, memory_id: int, content: str) -> None:
        """
        更新一条记忆记录。
        :param memory_id: 记忆ID。
        :param content: 记忆内容。
        """
        sql = """
UPDATE memory SET content = ?, updated_at = CURRENT_TIMESTAMP WHERE memory_id = ?
"""
        self.execute_query(sql, (content, memory_id), commit=True)

        return
