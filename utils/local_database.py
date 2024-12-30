from threading import Lock
from queue import Queue
from os import path, mkdir
from uuid import uuid4
import sqlite3
import logging

from utils.project_path import DATA_PATH

# 设置日志记录
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LocalDatabase:
    def __init__(self, db_name: str, db_path: str = path.join(DATA_PATH, 'databases')):
        self._db_path = db_path
        if not path.exists(db_path):
            mkdir(db_path)
        self._db_name = db_name if db_name.endswith(".db") else f"{db_name}.db"
        self._pool = Queue(maxsize=50)  # 设置连接池大小
        self._lock = Lock()
        for _ in range(self._pool.maxsize):
            self._pool.put(self._create_connection())

    def _create_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(path.join(self._db_path, self._db_name), check_same_thread=False)

    @property
    def connection(self) -> sqlite3.Connection:
        with self._lock:
            return self._pool.get()

    def release_connection(self, conn: sqlite3.Connection):
        with self._lock:
            self._pool.put(conn)

    def execute_query(self, query: str, params: tuple = None, commit: bool = False) -> sqlite3.Cursor:
        conn = self.connection
        cursor = conn.cursor()
        try:
            cursor.execute(query, params or ())
            if commit:
                conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Error executing query: {query} with params {params}. Error: {e}")
            raise
        finally:
            self.release_connection(conn)
        return cursor


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

    def get_messages(self, conversation_id: int, visible: int = 1) -> list:
        """
        获取会话的所有消息
        :param visible:
        :param conversation_id: 会话的id
        :return: 会话的所有消息列表
        """
        query = """
            SELECT * FROM ConversationMessages WHERE conversation_id = ? AND visible = ? ORDER BY timestamp ASC
        """
        cursor = self.execute_query(query, (conversation_id, visible))
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
            for message_id, conversation_id, role, content, timestamp, visible, wechat_message_config in
            cursor.fetchall()
        ]

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
        logger.info(f"Updated conversation {conversation_id} end_time to {end_time}")


if __name__ == '__main__':
    db = ConversationsDatabase()
    print(db.get_conversation_by_user('wxid_543lj3yk4jv222'))
