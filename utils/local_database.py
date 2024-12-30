# TODO:
#  需要完善会话记录和消息记录的储存

from os import path, mkdir

from utils.project_path import DATA_PATH

from sqlite3 import connect


class LocalDatabase:

    def __init__(self, db_name: str, db_path: str = path.join(DATA_PATH, 'databases')):
        self._db_path = db_path
        if not path.exists(db_path):
            mkdir(db_path)
        db_name = db_name if db_name.endswith(".db") else f"{db_name}.db"
        self._db_connection = connect(path.join(db_path, db_name))

    @property
    def connection(self) -> connect:
        return self._db_connection

    def close(self):
        self._db_connection.close()


class ConversationsDatabase(LocalDatabase):
    def __init__(self, *args, **kwargs):
        super().__init__(db_name="conversation", *args, **kwargs)
        self.create_tables()

    def create_tables(self):
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS Conversations (
                conversation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                start_time DATETIME NOT NULL,
                end_time DATETIME,
                summary TEXT
            )
        """)
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS ConversationMessages (
                message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES Conversations(conversation_id)
            )
        """)
        self.connection.commit()

    def add_conversation(self, user_id: str, start_time: str, end_time: str = None, summary: str = None):
        """
        增加会话
        :param user_id: 这个字段应该上传登录用户的wxid
        :param start_time: 对话的开始时间
        :param end_time: 对话的结束时间
        :param summary: 对话的总结，可以作为前端的标题使用
        :return:
        """
        cursor = self.connection.cursor()
        cursor.execute("""
            INSERT INTO Conversations (user_id, start_time, end_time, summary)
            VALUES (?, ?, ?, ?)
        """, (user_id, start_time, end_time, summary))
        self.connection.commit()
        return cursor.lastrowid

    def add_message(self, conversation_id: int, role: str, content: str, timestamp: str):
        """
        添加消息
        :param conversation_id: 会话的id
        :param role: 消息的角色，可以是user、assistant、system
        :param content: 消息的内容
        :param timestamp: 消息的时间戳
        :return:
        """
        cursor = self.connection.cursor()
        cursor.execute("""
            INSERT INTO ConversationMessages (conversation_id, role, content, timestamp)
            VALUES (?, ?, ?, ?)
        """, (conversation_id, role, content, timestamp))
        self.connection.commit()
        return cursor.lastrowid

    def get_conversation_by_user(self, user_id: str):
        """
        获取用户的所有会话
        :param user_id: wxid
        :return:
        """
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT * FROM Conversations WHERE user_id = ? ORDER BY start_time DESC
        """, (user_id,))
        return [{"conversation_id": conversation_id, "wxid": wxid, "start_time": start_time, "end_time": end_time, "summary": summary} for conversation_id, wxid, start_time, end_time, summary in cursor.fetchall()]

    def get_messages(self, conversation_id: int):
        """
        获取会话的所有消息
        :param conversation_id: 会话的id
        :return:
        """
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT * FROM ConversationMessages WHERE conversation_id = ? ORDER BY timestamp ASC 
        """, (conversation_id,))
        return cursor.fetchall()

    def update_conversation_end_time(self, conversation_id: int, end_time: str):
        """
        更新会话的结束时间
        :param conversation_id: 会话的id
        :param end_time: 会话的结束时间
        :return:
        """
        cursor = self.connection.cursor()
        cursor.execute("""
            UPDATE Conversations SET end_time = ? WHERE conversation_id = ?
        """, (end_time, conversation_id))
        self.connection.commit()

    def update_conversation_summary(self, conversation_id: int, summary: str):
        """
        更新会话的总结
        :param conversation_id: 会话的id
        :param summary: 会话的总结
        :return:
        """
        cursor = self.connection.cursor()
        cursor.execute("""
            UPDATE Conversations SET summary = ? WHERE conversation_id = ?
        """, (summary, conversation_id))
        self.connection.commit()


if __name__ == '__main__':
    c = ConversationsDatabase()
    print(c.get_conversation_by_user('wxid_543lj3yk4jv222'))