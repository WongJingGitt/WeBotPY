import os
import json
import time
from typing import TypedDict, List, Dict, Any, Optional

from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from langgraph.graph import StateGraph, END

from llm.llm import LLMFactory

# --- 1. 定义状态（类外部） ---
class AgentState(TypedDict):
    input_dict: Dict[str, Any]      # 原始聊天记录字典
    user_query: str                 # 用户的原始问题
    # --- 查询理解 ---
    intent: Optional[str]           # 推断的用户意图
    entities: Optional[Dict]        # 提取的关键实体
    chunk_processing_prompt: Optional[str] # 动态生成的用于处理块的 Prompt
    # --- 分块 ---
    messages: List[Dict]            # 从 input_dict 提取的原始消息列表
    message_chunks: List[List[Dict]]# 分块后的消息列表
    # --- 提取 ---
    extracted_data: List[str]       # 从各块提取的信息列表
    # --- 最终答案 ---
    final_answer: Optional[str]     # 最终给用户的答案
    # --- 错误处理 ---
    error_message: Optional[str]    # 记录处理过程中的错误

# --- 2. 定义Agent类 ---
class ChatSplitterAgent:
    """
    一个使用 LangGraph 构建的 Agent，用于分析长聊天记录并回答特定问题。
    它使用字节数来控制文本分块，以适应基于字节数计费/限制的模型。
    """
    def __init__(
        self,
        llm_query_understanding: BaseChatModel, # 用于理解查询和规划的 LLM 实例。
        llm_extraction: BaseChatModel = None,  # 用于从块中提取信息的 LLM 实例。
        llm_synthesis: BaseChatModel = None,   # 用于合成最终答案的 LLM 实例。
        max_bytes_per_chunk: int = 12000, # 基于字节数的块大小上限 (需要根据模型调整)
        prompt_overhead_bytes: int = 500,  # 估算的 Prompt 开销字节数 (需要调整)
        byte_encoding: str = 'utf-8',      # 用于计算字节数的编码
        recursion_limit: int = 15,
        rpm_limit = 10,

    ):
        """
        初始化 Agent.

        Args:
            llm_query_understanding: 用于理解查询和规划的 LLM 实例。
            llm_extraction: 用于从块中提取信息的 LLM 实例。
            llm_synthesis: 用于最终合成答案的 LLM 实例。
            max_bytes_per_chunk: 每个块的最大目标字节数 (不含 Prompt 开销)。
            prompt_overhead_bytes: 为 Prompt 和其他开销预留的估计字节数。
            byte_encoding: 计算字节数时使用的字符串编码。
            recursion_limit: LangGraph 的递归深度限制。
            rpm_limit: 模型每分钟处理的最大请求数。
        """
        # 设置 LLM 实例，如果未提供则使用默认值
        if not isinstance(llm_query_understanding, BaseChatModel):
            raise ValueError("llm_query_understanding must be a BaseChatModel instance.")
        
        self.llm_query_understanding = llm_query_understanding 
        self.llm_extraction = llm_extraction or llm_query_understanding
        self.llm_synthesis = llm_synthesis or llm_query_understanding

        # 配置参数
        self.max_bytes_per_chunk = max_bytes_per_chunk
        self.prompt_overhead_bytes = prompt_overhead_bytes
        self.byte_encoding = byte_encoding
        self.recursion_limit = recursion_limit
        self.rpm_limit = rpm_limit

        # 构建并编译 LangGraph 应用
        self.app = self._build_graph()

    # --- 辅助方法 ---
    def _format_single_message_for_llm(self, message: Dict) -> str:
        """将单条消息字典格式化为简洁的字符串表示。"""
        sender = message.get('sender', 'Unknown')
        remark = message.get('remark')
        content = message.get('content', '')
        timestamp = message.get('time', '')
        prefix = f"{sender}"
        if remark:
            prefix += f" ({remark})"

        # 简化特殊消息表示
        if content.startswith('[') and ']' in content:
            try:
                main_type_end = content.find(':') if ':' in content else content.find(']')
                if main_type_end != -1:
                     main_type = content[1:main_type_end]
                     content = f"[{main_type}消息]"
                else:
                     content = "[特殊消息]"
            except:
                content = "[特殊消息]" # Fallback

        return f"{timestamp} - {prefix}: {content}"

    def _format_chunk_for_llm(self, chunk: List[Dict[str, Any]]) -> str:
        """将消息字典列表（一个块）转换为多行文本表示。"""
        return "\n".join([self._format_single_message_for_llm(msg) for msg in chunk])

    def _chunk_by_byte_count(self, messages: List[Dict]) -> List[List[Dict]]:
        """按字节数分割消息列表。"""
        chunks = []
        current_chunk = []
        current_byte_count = 0
        effective_max_bytes = self.max_bytes_per_chunk - self.prompt_overhead_bytes
        if effective_max_bytes <= 0:
             raise ValueError("max_bytes_per_chunk is too small compared to prompt_overhead_bytes.")

        print("\n",f"   开始按字节数分块（每块有效最大字节数：{effective_max_bytes}）...")

        for message in messages:
            formatted_message = self._format_single_message_for_llm(message)
            try:
                message_bytes = len(formatted_message.encode(self.byte_encoding))
            except Exception as e:
                print("\n",f"警告：无法编码消息，跳过其字节计数。错误：{e}")
                message_bytes = 0 # 或者给一个估计值

            # 检查单条消息是否超限
            if message_bytes > effective_max_bytes:
                print("\n",f"警告：单条消息超过有效最大字节限制（{message_bytes} > {effective_max_bytes}）。跳过这条消息：{formatted_message[:100]}...")
                continue # 跳过这条过长的消息

            # 检查加入这条消息后是否会超限
            if current_byte_count + message_bytes > effective_max_bytes and current_chunk:
                # 当前块已满，保存当前块，开始新块
                chunks.append(current_chunk)
                current_chunk = [message]
                current_byte_count = message_bytes
            else:
                # 加入当前块
                current_chunk.append(message)
                current_byte_count += message_bytes

        # 加入最后一个块（如果非空）
        if current_chunk:
            chunks.append(current_chunk)

        print("\n",f"   分块完成：{len(messages)} 条消息 -> {len(chunks)} 个块（目标最大字节数：{self.max_bytes_per_chunk}）")
        return chunks

    # --- 图节点方法 ---
    def _understand_query_node(self, state: AgentState) -> Dict[str, Any]:
        """节点：理解查询与规划。"""
        print("\n","--- 运行节点：understand_query_node ---")
        user_query = state['user_query']
        context = state['input_dict'].get('meta', {'context': []}).get('context')
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", """你是一位智能任务规划师。你的任务是分析用户关于聊天记录的问题，并生成一个清晰的指令（Prompt），用于指导后续步骤从聊天记录的 *单个* 文本块中提取所需信息。

    请识别用户的核心意图和关键实体。然后，根据意图和实体，生成一个简洁、明确、可操作的 Prompt，这个 Prompt 将被应用于聊天记录的每个小块文本。

    在生成指令时，你可以参考由AI生成的历史聊天上下文协助你生成指令。例如：特定的梗、昵称、事件、行为等等
             
    输出格式必须是 JSON，包含以下字段:
    - "intent": 对用户意图的简短描述 (例如: "性格分析", "事件总结", "查找特定发言", "常规摘要")。
    - "entities": 一个包含关键实体的字典 (例如: {{"person": "张三"}}, {{"date": "2025-04-08"}}, {{"topic": "项目会议"}})。如果无明显实体，则为空字典。
    - "chunk_processing_prompt": 生成的用于处理单个文本块的 Prompt 字符串。这个 Prompt 应该指导如何从一小段聊天记录中提取与用户原始问题相关的信息。例如，如果用户问"张三的性格"，这个 Prompt 应该要求提取"张三"在该块中的发言。

    用户问题:
    {user_query}
    
    历史聊天上下文:
    {context}

    请生成 JSON 输出："""),
            ("human", "{user_query}") # 再次提供 user_query 可能有助于某些模型
        ])
        parser = JsonOutputParser()
        chain = prompt_template | self.llm_query_understanding | parser
        try:
            print("\n",f"   分析用户查询：'{user_query}'")
            response = chain.invoke({"user_query": user_query, "context": context})
            print("\n",f"   LLM分析结果：{response}")
            if not all(k in response for k in ["intent", "entities", "chunk_processing_prompt"]) or not response.get("chunk_processing_prompt"):
                 raise ValueError("LLM对查询理解的响应无效。")
            return {
                "intent": response.get("intent"),
                "entities": response.get("entities"),
                "chunk_processing_prompt": response.get("chunk_processing_prompt")
            }
        except Exception as e:
            print("\n",f"   understand_query_node中出错：{e}")
            return {"error_message": f"无法理解查询或生成处理提示：{e}"}

    def _chunk_node(self, state: AgentState) -> Dict[str, Any]:
        """节点：加载消息并按字节数分块。"""
        print("\n",f"--- 运行节点：chunk_node（最大字节数：{self.max_bytes_per_chunk}）---")
        if state.get("error_message"): return {}
        try:
            messages = state['input_dict'].get('data', [])
            if not messages:
                return {"error_message": "输入数据中未找到消息。"}
            message_chunks = self._chunk_by_byte_count(messages)
            if not message_chunks:
                 return {"error_message": "分块结果为零块。请检查数据或分块逻辑。"}
            return {"messages": messages, "message_chunks": message_chunks}
        except Exception as e:
            print("\n",f"   chunk_node中出错：{e}")
            return {"error_message": f"消息分块过程中失败：{e}"}

    def _extract_info_node(self, state: AgentState) -> Dict[str, Any]:
        """节点：分块信息提取。"""
        print("\n","--- 运行节点：extract_info_node ---")
        if state.get("error_message"): return {}
        message_chunks = state.get('message_chunks')
        chunk_processing_prompt = state.get('chunk_processing_prompt')
        if not message_chunks or not chunk_processing_prompt:
            return {"error_message": "缺少消息块或提取的处理提示。"}

        extracted_data = []
        parser = StrOutputParser()
        prompt_template = ChatPromptTemplate.from_template(
            f"{chunk_processing_prompt}\n\n聊天记录片段:\n```\n{{chunk_text}}\n```\n\n提取的相关信息 (如果此片段不包含相关信息，请明确说明'无相关信息'):"
        )
        chain = prompt_template | self.llm_extraction | parser
        print("\n",f"   使用生成的提示处理{len(message_chunks)}个块...")

        min_interval = 60.0 / self.rpm_limit if self.rpm_limit > 0 else 0
        last_call_time = time.monotonic()
        for i, chunk in enumerate(message_chunks):
            formatted_chunk = self._format_chunk_for_llm(chunk)
            if not formatted_chunk.strip():
                print("\n",f"   跳过空块 {i+1}/{len(message_chunks)}")
                continue
            try:
                current_time = time.monotonic()
                elapsed = current_time - last_call_time
                if elapsed < min_interval:
                    wait_time = min_interval - elapsed
                    print("\n",f"   等待{wait_time:.2f}秒以避免速率限制...")
                    time.sleep(wait_time)

                result = chain.invoke({"chunk_text": formatted_chunk})
                last_call_time = time.monotonic()
                if "无相关信息" not in result: # 过滤掉明确的否定回答
                    extracted_data.append(result)
            except Exception as e:
                print("\n",f"   处理块{i+1}时出错：{e}")
                last_call_time = time.monotonic()
                extracted_data.append(f"[处理块{i+1}时出错：{e}]")
            print("\n",f"   已处理块 {i+1}/{len(message_chunks)}")
        print("\n",f"   提取完成。在{len(extracted_data)}个块中找到相关信息。")
        return {"extracted_data": extracted_data}

    def _synthesize_answer_node(self, state: AgentState) -> Dict[str, Any]:
        """节点：最终合成答案。"""
        print("\n","--- 运行节点：synthesize_answer_node ---")
        if state.get("error_message"): return {}
        user_query = state['user_query']
        extracted_data = state.get('extracted_data')
        intent = state.get('intent', '回答用户问题')
        if not extracted_data:
            print("\n","   未提取到相关信息。")
            return {"final_answer": f"根据提供的聊天记录，未能找到与您的问题 '{user_query}' 直接相关的信息。"}
        if not user_query:
             return {"error_message": "最终合成缺少用户查询。"}

        combined_context = "\n\n---\n\n".join(extracted_data)
        prompt_template = ChatPromptTemplate.from_template(
             f"你是一个乐于助人的AI助手。用户的原始问题是：\"{user_query}\"。\n"
             f"根据从长聊天记录中提取的相关信息片段，请综合分析并回答用户的原始问题。\n"
             f"用户的意图是：{intent}。\n\n"
             "提取的相关信息片段如下:\n"
             "```\n{combined_context}\n```\n\n"
             "请根据以上信息，清晰、连贯地回答用户的原始问题：\"{user_query}\"\n"
             "最终回答:"
        )
        
        parser = StrOutputParser()
        chain = prompt_template | self.llm_synthesis | parser
        try:
            print("\n","\n","   合成最终答案...")
            final_answer = chain.invoke({"combined_context": combined_context, "user_query": user_query})
            print("\n","   已生成最终答案。")
            return {"final_answer": final_answer}
        except Exception as e:
            print("\n",f"   synthesize_answer_node中出错：{e}")
            return {"error_message": f"最终答案合成过程中失败：{e}"}

    def _handle_error_node(self, state: AgentState) -> Dict[str, Any]:
        """节点：处理错误。"""
        print("\n","--- 运行节点：handle_error_node ---")
        error = state.get("error_message", "发生未知错误。")
        print("\n",f"   捕获到错误：{error}")
        return {"final_answer": f"抱歉，处理您的请求时遇到问题：\n{error}"}

    # --- 条件边缘逻辑 ---
    def _should_continue(self, state: AgentState) -> str:
        """决定是继续还是跳转到错误处理。"""
        if state.get("error_message"):
            print("\n","--- 边缘条件：检测到错误，路由到handle_error ---")
            return "error"
        else:
            # print("\n","--- 边缘条件：无错误，继续正常流程 ---") # 减少打印
            return "continue"

    # --- 图构建方法 ---
    def _build_graph(self) -> StateGraph:
        """构建 LangGraph 工作流。"""
        workflow = StateGraph(AgentState)

        # 添加节点
        workflow.add_node("understand_query", self._understand_query_node)
        workflow.add_node("chunker", self._chunk_node)
        workflow.add_node("extract_info", self._extract_info_node)
        workflow.add_node("synthesize_answer", self._synthesize_answer_node)
        workflow.add_node("handle_error", self._handle_error_node)

        # 设置入口点
        workflow.set_entry_point("understand_query")

        # 添加边和条件路由
        workflow.add_conditional_edges("understand_query", self._should_continue, {"continue": "chunker", "error": "handle_error"})
        workflow.add_conditional_edges("chunker", self._should_continue, {"continue": "extract_info", "error": "handle_error"})
        workflow.add_conditional_edges("extract_info", self._should_continue, {"continue": "synthesize_answer", "error": "handle_error"}) # 即使提取有错也尝试合成
        workflow.add_conditional_edges("synthesize_answer", self._should_continue, {"continue": END, "error": "handle_error"})
        workflow.add_edge("handle_error", END)

        # 编译图
        print("\n","Agent图构建成功。")
        return workflow.compile()

    # --- 公共执行方法 ---
    def run(self, chat_data: Dict[str, Any], user_query: str) -> Dict[str, Any]:
        """
        执行 Agent 来处理聊天数据并回答问题。

        Args:
            chat_data: 包含 'meta' 和 'data' 的聊天记录字典。
            user_query: 用户的问题字符串。

        Returns:
            包含最终状态的字典，其中 'final_answer' 是给用户的答案。
        """
        if not isinstance(chat_data, dict) or 'data' not in chat_data:
            raise ValueError("Invalid chat_data format. Expected a dict with a 'data' key.")
        if not isinstance(user_query, str) or not user_query:
             raise ValueError("user_query must be a non-empty string.")

        initial_state = {
            "input_dict": chat_data,
            "user_query": user_query,
            # 初始化其他字段为 None 或空列表/字典
            "intent": None,
            "entities": None,
            "chunk_processing_prompt": None,
            "messages": [],
            "message_chunks": [],
            "extracted_data": [],
            "final_answer": None,
            "error_message": None,
        }

        print("\n","\n--- 开始Agent执行 ---")
        # 使用 invoke 获取最终结果
        final_state = self.app.invoke(initial_state, config={"recursion_limit": self.recursion_limit})
        print("\n","--- Agent执行完成 ---")

        return final_state

# TODO: 
#   1. 增加任务表格绑定拓展断点重试
#   2. 使用 Celery 或 RQ创建任务队列系统 `pip install celery redis`
#   3. 最后融合总结时，若是得出的chunk总结又超出了融合模型的最大输入。又要分块？
#       CREATE TABLE IF NOT EXISTS long_tasks (
#             task_id TEXT PRIMARY KEY,              -- 任务唯一ID (建议使用 UUID)
#             conversation_id TEXT NOT NULL,         -- 对应前端的对话 ID
#             triggering_message_id TEXT,            -- 触发此任务的用户消息 ID (可选)
#             user_query TEXT NOT NULL,              -- 用户的原始请求
#             input_data_ref TEXT,                   -- 指向输入数据的方式 (例如: 文件路径, S3 key, 或直接存储小输入的 JSON)
#             status TEXT NOT NULL CHECK(status IN ('PENDING', 'PLANNING', 'CHUNKING', 'EXTRACTING', 'SYNTHESIZING', 'COMPLETED', 'FAILED', 'PAUSED')), -- 任务状态
#             current_step TEXT,                     -- 当前或最后成功完成的 LangGraph 节点名 (可选)
#             total_chunks INTEGER,                  -- 总分块数 (可选, 用于进度显示)
#             processed_chunk_index INTEGER DEFAULT -1, -- 最后成功处理的块的索引 (从0开始, -1表示还未开始)
#             intermediate_results TEXT,             -- 存储累积的提取结果 (例如: JSON 格式的列表)
#             final_answer TEXT,                     -- 最终生成的答案
#             error_message TEXT,                    -- 记录错误信息
#             retry_count INTEGER DEFAULT 0,         -- 重试次数
#             created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
#             updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
#         );
#         -- 可以为 conversation_id 创建索引以加速查询
#         CREATE INDEX IF NOT EXISTS idx_conversation_id ON long_tasks (conversation_id);
#   4. 考虑把intermediate_results指向到JSONL中，优化SQLite的性能


if __name__ == "__main__":
    
    with open('D:\wangyingjie\WeBot\data\exports\上海交大🇨🇳人生何处不青山__2025-04-02_17-55-22.txt', 'r', encoding='utf-8') as r:
        chat_data = json.load(r)
    
    user_query = "请你针对这份聊天记录深度分析一下刘奶和李阳之间的关系，并且列出一些数据来支撑的你结论"

    try:
        agent = ChatSplitterAgent(
            max_bytes_per_chunk=20480,
            prompt_overhead_bytes=2048,
            llm_query_understanding=LLMFactory.deepseek_v3_llm(),
            llm_extraction=LLMFactory.gemini_llm(),
            llm_synthesis=LLMFactory.deepseek_v3_llm()
        )

        # 运行 Agent
        final_state = agent.run(chat_data, user_query)

        # 打印最终答案
        print("\n","\n--- 最终答案 ---")
        print("\n",final_state.get("final_answer", "未生成最终答案。"))
        if final_state.get("error_message"):
             print("\n",f"\n--- 记录的错误信息 ---")
             print("\n",final_state.get("error_message"))

    except ValueError as ve:
         print("\n",f"输入错误：{ve}")
    except Exception as e:
         print("\n",f"Agent执行过程中发生意外错误：{e}")