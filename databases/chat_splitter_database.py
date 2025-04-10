# --- START OF FILE chat_splitter_database.py ---

import json
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List

from databases.local_database import LocalDatabase


class ChatSplitterDatabase(LocalDatabase):
    """
    用于管理长聊天分析任务（Chat Splitter Task）的数据库操作类。
    继承自 LocalDatabase，提供任务的创建、状态更新、进度跟踪和查询功能。
    """

    def __init__(self, *args, **kwargs):
        """
        初始化数据库连接和表。
        """
        # 指定数据库文件名，并调用父类初始化
        super().__init__(db_name="chat_splitter_task", *args, **kwargs)
        self.create_task_table()

    def create_task_table(self):
        """
        创建用于存储聊天分析任务信息的表 chat_splitter_task。
        如果表已存在，则此操作不执行任何操作。
        """
        # 注意：SQLite 不支持在 CREATE TABLE 中直接使用 ON UPDATE CURRENT_TIMESTAMP
        # updated_at 需要在 UPDATE 语句中手动更新
        query = """
            CREATE TABLE IF NOT EXISTS chat_splitter_task (
                task_id TEXT PRIMARY KEY,              -- 任务唯一ID (建议使用 UUID)
                conversation_id TEXT NOT NULL,         -- 对应前端的对话 ID (关联 Conversations 表)
                triggering_message_id TEXT,            -- 触发此任务的用户消息 ID (关联 ConversationMessages 表)
                user_query TEXT NOT NULL,              -- 用户的原始请求文本
                input_data_ref TEXT,                   -- 输入数据的引用 (例如: 文件路径)
                input_data_json TEXT,                  -- 直接存储的输入数据 (适用于较小数据)
                status TEXT NOT NULL CHECK(status IN (
                    'PENDING',      -- 待处理
                    'PLANNING',     -- 规划中 (理解查询)
                    'CHUNKING',     -- 分块中
                    'EXTRACTING',   -- 提取信息中
                    'REDUCING',     -- 缩减上下文中 (如果需要多层总结)
                    'SYNTHESIZING', -- 合成最终答案中
                    'COMPLETED',    -- 已完成
                    'FAILED',       -- 已失败
                    'PAUSED'        -- 已暂停 (未来扩展)
                )),                                    -- 任务当前状态
                current_step TEXT,                     -- 当前或最后成功完成的 LangGraph 节点名 (可选)
                total_chunks INTEGER,                  -- 总分块数 (可选, 用于进度显示)
                processed_chunk_index INTEGER DEFAULT -1, -- 最后成功处理的块的索引 (从0开始, -1表示还未开始)
                intermediate_results_ref TEXT,         -- 中间结果的引用 (例如: JSON Lines 文件路径)
                intermediate_results_json TEXT,        -- 直接存储的中间结果 (适用于较小数据)
                final_answer TEXT,                     -- 最终生成的答案
                error_message TEXT,                    -- 记录任务失败时的错误信息
                retry_count INTEGER DEFAULT 0,         -- 任务重试次数
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP, -- 任务创建时间
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP  -- 任务最后更新时间
            )
        """
        self.execute_query(query, commit=True)
        # 可以考虑为 conversation_id 和 triggering_message_id 添加索引以提高查询效率
        self.execute_query("CREATE INDEX IF NOT EXISTS idx_task_conversation_id ON chat_splitter_task (conversation_id);", commit=True)
        self.execute_query("CREATE INDEX IF NOT EXISTS idx_task_triggering_message_id ON chat_splitter_task (triggering_message_id);", commit=True)
        self.execute_query("CREATE INDEX IF NOT EXISTS idx_task_status ON chat_splitter_task (status);", commit=True)


    def create_task(self,
                    conversation_id: str,
                    triggering_message_id: str,
                    user_query: str,
                    input_data_ref: Optional[str] = None,
                    input_data_json: Optional[str] = None,
                    task_id: Optional[str] = None,
                    initial_status: str = 'PENDING') -> str:
        """
        创建一个新的聊天分析任务记录。

        :param conversation_id: 关联的对话 ID。
        :param triggering_message_id: 触发任务的消息 ID。
        :param user_query: 用户的原始查询。
        :param input_data_ref: 输入数据的引用（如文件路径）。
        :param input_data_json: 直接存储的输入数据 JSON 字符串。
        :param task_id: 可选的任务 ID，如果未提供则自动生成 UUID。
        :param initial_status: 任务的初始状态，默认为 'PENDING'。
        :return: 创建的任务的 task_id。
        :raises ValueError: 如果 input_data_ref 和 input_data_json 都未提供。
        """
        if not input_data_ref and not input_data_json:
            raise ValueError("必须提供 input_data_ref 或 input_data_json 中的至少一个。")

        task_id = task_id if task_id else str(uuid.uuid4().hex)
        # 使用 SQLite 的 CURRENT_TIMESTAMP 获取当前时间
        query = """
            INSERT INTO chat_splitter_task (
                task_id, conversation_id, triggering_message_id, user_query,
                input_data_ref, input_data_json, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
        params = (
            task_id, conversation_id, triggering_message_id, user_query,
            input_data_ref, input_data_json, initial_status
        )
        self.execute_query(query, params, commit=True)
        print(f"任务已创建: task_id={task_id}")
        return task_id

    def update_task_status(self,
                           task_id: str,
                           status: str,
                           current_step: Optional[str] = None,
                           final_answer: Optional[str] = None,
                           error_message: Optional[str] = None):
        """
        更新任务的状态和其他相关字段（如当前步骤、最终答案或错误信息）。
        同时会自动更新 updated_at 时间戳。

        :param task_id: 要更新的任务 ID。
        :param status: 新的任务状态。
        :param current_step: 当前执行到的步骤名 (可选)。
        :param final_answer: 最终答案 (可选, 通常在 COMPLETED 时设置)。
        :param error_message: 错误信息 (可选, 通常在 FAILED 时设置)。
        """
        fields_to_update = {"status": status, "updated_at": "CURRENT_TIMESTAMP"}
        params = [status]

        if current_step is not None:
            fields_to_update["current_step"] = "?"
            params.append(current_step)
        if final_answer is not None:
            fields_to_update["final_answer"] = "?"
            params.append(final_answer)
        if error_message is not None:
            fields_to_update["error_message"] = "?"
            params.append(error_message)
            # 如果设置了错误信息，通常意味着任务失败
            if status != 'FAILED':
                 print(f"警告: 为任务 {task_id} 设置了错误信息，但状态不是 'FAILED' (当前状态: {status})。")

        set_clause = ", ".join(f"{key} = {value}" for key, value in fields_to_update.items())
        query = f"UPDATE chat_splitter_task SET {set_clause} WHERE task_id = ?"
        params.append(task_id)

        self.execute_query(query, tuple(params), commit=True)
        print(f"任务状态已更新: task_id={task_id}, status={status}")

    def update_task_progress(self,
                             task_id: str,
                             processed_chunk_index: int,
                             intermediate_results_ref: Optional[str] = None,
                             intermediate_results_json: Optional[str] = None,
                             total_chunks: Optional[int] = None):
        """
        更新任务的分块处理进度和中间结果。
        同时会自动更新 updated_at 时间戳。

        :param task_id: 要更新的任务 ID。
        :param processed_chunk_index: 最新处理完成的块索引。
        :param intermediate_results_ref: 中间结果的文件引用 (如果使用文件存储)。
        :param intermediate_results_json: 中间结果的 JSON 字符串 (如果直接存储)。
        :param total_chunks: 总块数 (可选, 如果已知)。
        """
        fields_to_update = {
            "processed_chunk_index": "?",
            "updated_at": "CURRENT_TIMESTAMP"
        }
        params = [processed_chunk_index]

        if intermediate_results_ref is not None:
            fields_to_update["intermediate_results_ref"] = "?"
            params.append(intermediate_results_ref)
        if intermediate_results_json is not None:
            # 注意：如果结果非常大，这里可能成为瓶颈
            fields_to_update["intermediate_results_json"] = "?"
            params.append(intermediate_results_json)
        if total_chunks is not None:
            fields_to_update["total_chunks"] = "?"
            params.append(total_chunks)

        set_clause = ", ".join(f"{key} = {value}" for key, value in fields_to_update.items())
        query = f"UPDATE chat_splitter_task SET {set_clause} WHERE task_id = ?"
        params.append(task_id)

        self.execute_query(query, tuple(params), commit=True)
        # 避免过于频繁的打印，可以考虑只在特定条件下打印
        # print(f"任务进度已更新: task_id={task_id}, processed_chunk_index={processed_chunk_index}")


    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        根据 task_id 获取任务的详细信息。

        :param task_id: 要查询的任务 ID。
        :return: 包含任务所有字段的字典，如果未找到则返回 None。
        """
        query = "SELECT * FROM chat_splitter_task WHERE task_id = ?"
        cursor = self.execute_query(query, (task_id,))
        row = cursor.fetchone()
        if row:
            # 获取列名
            columns = [description[0] for description in cursor.description]
            return dict(zip(columns, row))
        return None

    def get_tasks_by_conversation(self, conversation_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        获取指定对话关联的所有任务列表，按创建时间降序排列。

        :param conversation_id: 要查询的对话 ID。
        :param limit: 返回的最大任务数量。
        :return: 任务信息字典的列表。
        """
        query = "SELECT * FROM chat_splitter_task WHERE conversation_id = ? ORDER BY created_at DESC LIMIT ?"
        cursor = self.execute_query(query, (conversation_id, limit))
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def increment_retry_count(self, task_id: str):
        """
        将指定任务的重试次数加 1。
        同时会自动更新 updated_at 时间戳。

        :param task_id: 要更新的任务 ID。
        """
        query = "UPDATE chat_splitter_task SET retry_count = retry_count + 1, updated_at = CURRENT_TIMESTAMP WHERE task_id = ?"
        self.execute_query(query, (task_id,), commit=True)
        print(f"任务重试次数已增加: task_id={task_id}")

    def delete_task(self, task_id: str):
        """
        删除指定的任务记录。
        注意：此操作不会自动删除关联的外部文件（如果使用了 *_ref）。

        :param task_id: 要删除的任务 ID。
        """
        # 可以在这里添加逻辑来删除关联的文件 (如果 intermediate_results_ref 或 input_data_ref 被使用)
        # task_info = self.get_task(task_id)
        # if task_info:
        #     if task_info.get('intermediate_results_ref'):
        #         # os.remove(task_info['intermediate_results_ref'])
        #         pass
        #     if task_info.get('input_data_ref'):
        #         # os.remove(task_info['input_data_ref'])
        #         pass

        query = "DELETE FROM chat_splitter_task WHERE task_id = ?"
        self.execute_query(query, (task_id,), commit=True)
        print(f"任务已删除: task_id={task_id}")


if __name__ == '__main__':
    print("测试 ChatSplitterDatabase...")
    # 假设 DATA_PATH 已经定义在 utils.project_path
    # from utils.project_path import DATA_PATH

    # 创建实例 (会创建数据库文件和表)
    db = ChatSplitterDatabase() # 使用默认路径

    # 1. 创建一个新任务
    print("\n--- 创建任务 ---")
    conv_id = "test_conv_123"
    msg_id = "test_msg_abc"
    query_text = "分析一下张三的性格特点"
    # 假设输入数据较小，直接存 JSON
    input_json_data = json.dumps({"meta": {}, "data": [{"sender": "张三", "content": "我觉得这个方案可行。"}]})
    try:
        new_task_id = db.create_task(
            conversation_id=conv_id,
            triggering_message_id=msg_id,
            user_query=query_text,
            input_data_json=input_json_data
        )
        print(f"创建的任务 ID: {new_task_id}")
    except Exception as e:
        print(f"创建任务失败: {e}")
        new_task_id = None

    if new_task_id:
        # 2. 获取任务信息
        print("\n--- 获取任务信息 ---")
        task_info = db.get_task(new_task_id)
        if task_info:
            print(f"获取到任务信息: status={task_info.get('status')}, created_at={task_info.get('created_at')}")
            # print(task_info) # 打印完整信息
        else:
            print("未能获取到任务信息。")

        # 3. 更新任务状态和进度 (模拟 Agent 执行)
        print("\n--- 更新任务状态和进度 ---")
        db.update_task_status(new_task_id, status='EXTRACTING', current_step='extract_info')
        # 模拟处理完第一个块
        intermediate_json = json.dumps(["张三认为方案可行。"]) # 假设提取结果
        db.update_task_progress(new_task_id, processed_chunk_index=0, intermediate_results_json=intermediate_json, total_chunks=1)
        task_info = db.get_task(new_task_id)
        print(f"更新后状态: {task_info.get('status')}, 进度: {task_info.get('processed_chunk_index')}/{task_info.get('total_chunks')}")

        # 4. 更新为完成状态
        print("\n--- 更新为完成状态 ---")
        final_answer_text = "张三看起来比较务实，倾向于认可可行的方案。"
        db.update_task_status(new_task_id, status='COMPLETED', final_answer=final_answer_text)
        task_info = db.get_task(new_task_id)
        print(f"完成状态: {task_info.get('status')}, 答案: {task_info.get('final_answer')}")

        # 5. 获取某个对话的所有任务
        print("\n--- 获取对话的所有任务 ---")
        tasks_for_conv = db.get_tasks_by_conversation(conv_id)
        print(f"对话 {conv_id} 共有 {len(tasks_for_conv)} 个任务。")
        if tasks_for_conv:
            print(f"  最新任务 ID: {tasks_for_conv[0]['task_id']}, 状态: {tasks_for_conv[0]['status']}")

        # 6. 增加重试次数
        print("\n--- 增加重试次数 ---")
        db.increment_retry_count(new_task_id)
        task_info = db.get_task(new_task_id)
        print(f"重试次数: {task_info.get('retry_count')}")

        # 7. 删除任务 (测试完成后)
        # print("\n--- 删除任务 ---")
        # db.delete_task(new_task_id)
        # task_info = db.get_task(new_task_id)
        # print(f"删除后查询任务: {task_info}")

    print("\n测试完成。")

# --- END OF FILE chat_splitter_database.py ---