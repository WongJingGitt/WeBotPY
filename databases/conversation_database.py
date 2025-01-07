from uuid import uuid4

from databases.local_database import LocalDatabase


class ConversationsDatabase(LocalDatabase):
    def __init__(self, *args, **kwargs):
        super().__init__(db_name="conversation", *args, **kwargs)
        self.create_tables()

    def create_tables(self):
        self.execute_query("""
            CREATE TABLE IF NOT EXISTS Conversations (
                conversation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                start_time DATETIME NOT NULL,
                end_time DATETIME,
                summary TEXT
            )
        """, commit=True)
        self.execute_query("""
            CREATE TABLE IF NOT EXISTS ConversationMessages (
                message_id TEXT PRIMARY KEY,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                visible INTEGER DEFAULT 1,
                wechat_message_config TEXT,
                timestamp DATETIME NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES Conversations(conversation_id)
            )
        """, commit=True)

    def add_conversation(self, user_id: str, start_time: str, end_time: str = None, summary: str = None) -> int:
        """
        增加会话
        :param user_id: 这个字段应该上传登录用户的wxid
        :param start_time: 对话的开始时间
        :param end_time: 对话的结束时间
        :param summary: 对话的总结，可以作为前端的标题使用
        :return: 新增会话的 conversation_id
        """
        query = """
            INSERT INTO Conversations (user_id, start_time, end_time, summary)
            VALUES (?, ?, ?, ?)
        """
        cursor = self.execute_query(query, (user_id, start_time, end_time, summary), commit=True)
        return cursor.lastrowid

    def add_message(self, conversation_id: int, role: str, content: str, timestamp: str, visible: int = 1,
                    wechat_message_config: str = None, message_id: str = None) -> str:
        """
        添加消息
        :param message_id:
        :param wechat_message_config:
        :param conversation_id: 会话的id
        :param role: 消息的角色，可以是user、assistant、system
        :param content: 消息的内容
        :param timestamp: 消息的时间戳
        :return: 新增消息的 message_id
        """
        message_id = message_id if message_id else str(uuid4())
        query = """
            INSERT INTO ConversationMessages (conversation_id, role, content, timestamp, visible, wechat_message_config, message_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        self.execute_query(query,
                           (conversation_id, role, content, timestamp, visible, wechat_message_config, message_id),
                           commit=True)
        return message_id

    def get_conversation_by_user(self, user_id: str) -> list:
        """
        获取用户的所有会话
        :param user_id: wxid
        :return: 用户的所有会话列表
        """
        query = """
            SELECT * FROM Conversations WHERE user_id = ? ORDER BY start_time DESC
        """
        cursor = self.execute_query(query, (user_id,))
        return [
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "start_time": start_time,
                "end_time": end_time,
                "summary": summary
            }
            for conversation_id, user_id, start_time, end_time, summary in cursor.fetchall()
        ]

    def get_messages(self, conversation_id: int, visible: list[int] | None = None) -> list:
        """
        获取会话的所有消息
        :param visible:
        :param conversation_id: 会话的id
        :return: 会话的所有消息列表
        """
        if visible is None:
            visible = [1]

        placeholders = ",".join("?" * len(visible))
        query = f"""
            SELECT * FROM ConversationMessages WHERE conversation_id = ? AND visible in ({placeholders}) ORDER BY timestamp ASC
        """
        cursor = self.execute_query(query, (conversation_id, *visible))
        return [
            {
                "message_id": message_id,
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
                "visible": visible,
                "wechat_message_config": wechat_message_config,
                "timestamp": timestamp
            }
            for message_id, conversation_id, role, content, visible, wechat_message_config, timestamp in
            cursor.fetchall()
        ]

    def delete_message(self, message_id: str):
        query = """
            DELETE FROM ConversationMessages WHERE message_id = ?
        """
        self.execute_query(query, (message_id,), commit=True)

    def delete_conversation(self, conversation_id: int):
        """
        删除会话
        :param conversation_id: 会话的id
        """
        query = """
            DELETE FROM Conversations WHERE conversation_id = ?
        """
        query_delete_messages = """
            DELETE FROM ConversationMessages WHERE conversation_id = ?
        """
        self.execute_query(query, (conversation_id,), commit=True)
        self.execute_query(query_delete_messages, (conversation_id,), commit=True)

    def update_conversation_summary(self, conversation_id: int, summary: str):
        """
        更新会话的摘要
        :param conversation_id: 会话的id
        :param summary: 会话的摘要
        """
        query = """
            UPDATE Conversations SET summary = ? WHERE conversation_id = ?
        """
        self.execute_query(query, (summary, conversation_id), commit=True)

    def update_conversation_end_time(self, conversation_id: int, end_time: str):
        """
        更新会话的结束时间
        :param conversation_id: 会话的id
        :param end_time: 会话的结束时间
        """
        query = """
            UPDATE Conversations SET end_time = ? WHERE conversation_id = ?
        """
        self.execute_query(query, (end_time, conversation_id), commit=True)
