from webot.databases.local_database import LocalDatabase


class ImageRecognitionDatabase(LocalDatabase):
    def __init__(self, db_name="image_recognition"):
        super().__init__(db_name)
        self.create_table()

    def create_table(self):
        self.execute_query(
            """
            CREATE TABLE IF NOT EXISTS image_recognition (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL,
                recognition_result TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                message_time DATETIME DEFAULT NULL
            );
            """, commit=True
        )

    def add_recognition_result(self, message_id, recognition_result, message_time):
        cursor = self.execute_query(
            """
            INSERT INTO image_recognition (message_id, recognition_result, message_time)
            VALUES (?, ?, ?);
            """,
            (message_id, recognition_result, message_time), commit=True
        )
        return cursor.lastrowid

    def get_recognition_result(self, message_id):
        cursor = self.execute_query(
            """
            SELECT message_id, recognition_result, message_time FROM image_recognition WHERE message_id = ?;
            """,
            (message_id,), commit=True
        )
        result = cursor.fetchone()
        if not result: return None, None, None
        return result

    def get_all_recognition_results(self):
        cursor = self.execute_query(
            """
            SELECT message_id, recognition_result, message_time FROM image_recognition;
            """, commit=True
        )
        return cursor.fetchall()

    def update_recognition_result(self, message_id, recognition_result):
        cursor = self.execute_query(
            """
            UPDATE image_recognition SET recognition_result = ? WHERE message_id = ?;
            """,
            (recognition_result, message_id), commit=True
        )
        return cursor.rowcount

    def delete_recognition_result(self, message_id):
        cursor = self.execute_query(
            """
            DELETE FROM image_recognition WHERE message_id = ?;
            """,
            (message_id,), commit=True
        )
        return cursor.rowcount
