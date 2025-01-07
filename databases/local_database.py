from threading import Lock
from queue import Queue
from os import path, mkdir
import sqlite3

from utils.project_path import DATA_PATH


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
            raise
        finally:
            self.release_connection(conn)
        return cursor