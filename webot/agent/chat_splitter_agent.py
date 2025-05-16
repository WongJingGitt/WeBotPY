import os
import json
import time
from typing import TypedDict, List, Dict, Any, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph

from webot.llm.llm import LLMFactory
from webot.prompts.system_prompts import SystemPrompts


# --- 1. 定义状态（类外部） ---
class AgentState(TypedDict):
    input_dict: Dict[str, Any]  # 原始聊天记录字典
    user_query: str  # 用户的原始问题
    # --- 查询理解 ---
    intent: Optional[str]  # 推断的用户意图
    entities: Optional[Dict]  # 提取的关键实体
    chunk_processing_prompt: Optional[str]  # 动态生成的用于处理块的 Prompt
    # --- 分块 ---
    messages: List[Dict]  # 从 input_dict 提取的原始消息列表
    message_chunks: List[List[Dict]]  # 分块后的消息列表
    # --- 提取 ---
    extracted_data: List[str]  # 从各块提取的信息列表
    # --- 最终答案 ---
    final_answer: Optional[str]  # 最终给用户的答案
    # --- 错误处理 ---
    error_message: Optional[str]  # 记录处理过程中的错误


# --- 2. 定义Agent类 ---
class ChatSplitterAgent:
    """
    一个使用 LangGraph 构建的 Agent，用于分析长聊天记录并回答特定问题。
    它使用字节数来控制文本分块，以适应基于字节数计费/限制的模型。
    """

    def __init__(
            self,
            llm_query_understanding: BaseChatModel,  # 用于理解查询和规划的 LLM 实例。
            llm_extraction: BaseChatModel = None,  # 用于从块中提取信息的 LLM 实例。
            llm_synthesis: BaseChatModel = None,  # 用于合成最终答案的 LLM 实例。
            max_bytes_per_chunk: int = 25000,  # 基于字节数的块大小上限 (需要根据模型调整)
            max_bytes_pre_recursive_fuse_chunk: int = 25000,
            prompt_overhead_bytes: int = 500,  # 估算的 Prompt 开销字节数 (需要调整)
            byte_encoding: str = 'utf-8',  # 用于计算字节数的编码
            recursion_limit: int = 15,
            rpm_limit=10,
    ):
        """
        初始化 Agent.

        Args:
            llm_query_understanding: 用于理解查询和规划的 LLM 实例。建议使用高参数模型，例如：DeepSeek V3
            llm_extraction: 用于从块中提取信息的 LLM 实例。默认使用 llm_query_understanding。主要的Token消耗环节，可以使用低参数模型，但是不建议，低参数模型丢失细节比较严重。建议使用豆包1.5pro 256k
            llm_synthesis: 用于最终合成答案的 LLM 实例。默认使用 llm_query_understanding。建议使用高参数模型，例如：DeepSeek V3
            max_bytes_per_chunk: 每个块的最大目标字节数 (不含 Prompt 开销)。单位是bytes
            max_bytes_pre_recursive_fuse_chunk: 在递归融合之前，每个块的最大目标字节数 (不含 Prompt 开销)。单位是bytes
            prompt_overhead_bytes: 为 Prompt 和其他开销预留的估计字节数。单位是bytes
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
        self.max_bytes_pre_recursive_fuse_chunk = max_bytes_pre_recursive_fuse_chunk
        self.prompt_overhead_bytes = prompt_overhead_bytes
        self.byte_encoding = byte_encoding
        self.recursion_limit = recursion_limit
        self.rpm_limit = rpm_limit

        # 构建并编译 LangGraph 应用
        self.app = self._build_graph()

    # --- 辅助方法 ---
    def _format_single_message_for_llm(self, message: Dict) -> str:
        """
        将单条消息字典格式化为包含关键ID和简化内容的字符串表示。
        格式: timestamp - [wxid] sender (remark): simplified_content (msg_id: ..., reply_to: ..., mentions: N)
        """
        sender = message.get('sender', 'Unknown')
        remark = message.get('remark')
        content = message.get('content', '')
        timestamp = message.get('time', 'no-timestamp')  # 使用默认值防止 KeyErrors
        wxid = message.get('wxid', 'no-wxid')
        msg_id = message.get('msg_id', 'no-msgid')
        reply_msg_id = message.get('reply_msg_id')  # 可能为 None
        mentioned = message.get('mentioned', [])  # 默认为空列表

        # --- 格式化发送者信息 (包含 wxid) ---
        sender_info = f"[{wxid}] {sender}"
        if remark:
            sender_info += f" ({remark})"

        # --- 简化内容 (保留部分结构信息，避免完全丢失类型) ---
        simplified_content = ""
        if isinstance(content, str):
            simplified_content = content  # 默认使用原始内容
            if content.startswith('[') and ']' in content:
                try:
                    main_type_end = content.find(':') if ':' in content else content.find(']')
                    if main_type_end != -1:
                        main_type = content[1:main_type_end].strip()
                        # 对于某些类型，尝试保留简短标题或子类型
                        title_or_subtype = ""
                        if ':' in content[1:main_type_end + 2]:  # 检查是否有冒号分隔
                            details_start = main_type_end + 1
                            details_end = content.find(']', details_start)
                            details_part = content[details_start: details_end if details_end != -1 else None].strip(
                                " |")
                            # 提取 '||' 分隔符前的部分作为标题/子类型 (如果存在)
                            title_or_subtype = details_part.split('||')[0].strip()
                            # 限制标题/子类型长度
                            if len(title_or_subtype) > 40:
                                title_or_subtype = title_or_subtype[:37] + "..."

                        if title_or_subtype:
                            simplified_content = f"[{main_type}: {title_or_subtype}]"
                        # 对引用消息做特殊简化，避免嵌套过深
                        elif main_type == "引用消息":
                            simplified_content = "[引用消息]"  # 可以考虑提取回复内容，但会增加复杂性
                        elif main_type == "聊天记录":
                            simplified_content = "[聊天记录片段]"
                        else:  # 其他类型只保留主类型
                            simplified_content = f"[{main_type}消息]"
                    else:
                        # 如果格式不规范，例如只有 "[视频]"
                        bracket_content = content[1:content.find(']')]
                        if bracket_content and len(bracket_content) < 20:
                            simplified_content = f"[{bracket_content}消息]"
                        else:
                            simplified_content = "[特殊格式内容]"
                except Exception:
                    simplified_content = "[内容解析错误]"  # 解析出错时的回退
            # else: content is plain text, keep simplified_content = content
        elif not isinstance(content, str):
            simplified_content = "[非文本消息]"
        else:
            simplified_content = str(content)  # 确保是字符串

        # --- 构建消息元数据字符串 (msg_id, reply_to, mentions count) ---
        meta_parts = []
        meta_parts.append(f"msg_id: {msg_id}")  # 始终包含 msg_id

        if reply_msg_id:
            meta_parts.append(f"reply_to: {reply_msg_id}")

        mention_count = 0
        if isinstance(mentioned, list):
            mention_count = len(mentioned)
        if mention_count > 0:
            meta_parts.append(f"mentions: {mention_count}")
            # 如果你需要知道具体提到了谁的 wxid，可以取消下面的注释，但这会显著增加长度
            # mentioned_wxids = [m.get('wxid', 'unknown') for m in mentioned if isinstance(m, dict)]
            # if mentioned_wxids:
            #     meta_parts.append(f"mentioned_wxids: [{','.join(mentioned_wxids)}]")

        meta_str = ""
        if meta_parts:
            meta_str = f" ({', '.join(meta_parts)})"

        # --- 组合最终字符串 ---
        final_string = f"{timestamp} - {sender_info}: {simplified_content}{meta_str}"
        return final_string

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

        print(f"\n   开始按字节数分块（每块有效最大字节数：{effective_max_bytes}）...")

        for i, message in enumerate(messages):
            formatted_message = self._format_single_message_for_llm(message)
            try:
                message_bytes = len(formatted_message.encode(self.byte_encoding)) + len(
                    '\n'.encode(self.byte_encoding))  # 加上换行符字节
            except Exception as e:
                print(f"\n   警告：无法编码消息 {i}，跳过其字节计数。错误：{e}")
                message_bytes = 10  # 给一个小的估计值，避免完全忽略

            # 检查单条消息是否超限
            if message_bytes > effective_max_bytes:
                print(
                    f"\n   警告：单条消息 {i} 超过有效最大字节限制 ({message_bytes} > {effective_max_bytes})。尝试截断...")
                # 尝试截断消息以适应限制，如果仍然不行则跳过
                allowed_str_len = int(
                    effective_max_bytes / (message_bytes / len(formatted_message) + 1e-6))  # 估计允许的字符串长度
                truncated_message_str = formatted_message[:allowed_str_len] + "...[截断]"
                message_bytes = len(truncated_message_str.encode(self.byte_encoding))
                if message_bytes > effective_max_bytes:
                    print(f"\n      截断后仍然超长，跳过消息 {i}。")
                    continue
                else:
                    # 使用截断后的消息，需要修改原始消息内容或创建一个新的表示
                    # 这里简化处理，直接跳过，但实际应用中可能需要保留部分信息
                    print(f"\n      截断成功，但为简化，仍跳过消息 {i}。")
                    continue  # 跳过这条过长的消息（或者可以添加截断后的版本）

            # 检查加入这条消息后是否会超限
            if current_byte_count + message_bytes > effective_max_bytes and current_chunk:
                # 当前块已满，保存当前块，开始新块
                chunks.append(current_chunk)
                print(f"     块 {len(chunks)} 创建，包含 {len(current_chunk)} 条消息，字节数 ~{current_byte_count}")
                current_chunk = [message]
                current_byte_count = message_bytes
            else:
                # 加入当前块
                current_chunk.append(message)
                current_byte_count += message_bytes

        # 加入最后一个块（如果非空）
        if current_chunk:
            chunks.append(current_chunk)
            print(f"     块 {len(chunks)} 创建（最后），包含 {len(current_chunk)} 条消息，字节数 ~{current_byte_count}")

        if not chunks and messages:
            print("\n   警告：未能成功分块，可能是因为所有消息都过长或配置问题。")

        print(f"\n   分块完成：{len(messages)} 条消息 -> {len(chunks)} 个块（目标最大字节数：{self.max_bytes_per_chunk}）")
        return chunks

    # --- 图节点方法 ---
    def _understand_query_node(self, state: AgentState) -> Dict[str, Any]:
        """节点：理解查询与规划。"""
        print("\n", "--- 运行节点：understand_query_node ---")
        user_query = state['user_query']
        context_info = state['input_dict'].get('meta', {}).get('context', {}).get('memories', [])
        context_str = "\n".join(
            [f"- {mem.get('type')}: {mem.get('content')}" for mem in context_info if mem.get('content')])

        if not context_str.strip():
            context_str = "当前聊天记录没有可用上下文"
        else:
            encoded_context = context_str.encode(self.byte_encoding)
            if len(encoded_context) > self.max_bytes_pre_recursive_fuse_chunk:
                print(
                    f"\n   警告：背景信息字节数过长 ({len(encoded_context)} bytes)，将截断至 {self.max_bytes_pre_recursive_fuse_chunk} bytes。")
                context_str = encoded_context[:self.max_bytes_pre_recursive_fuse_chunk].decode(self.byte_encoding,
                                                                                               errors='ignore') + "\n[...背景信息过长已截断...]"

        prompt_template = ChatPromptTemplate.from_messages([
            ("system", SystemPrompts.chat_splitter_understand_prompt()),
            ("human", "{user_query}")  # 只期望 user_query 作为输入变量
        ])
        parser = JsonOutputParser()
        chain = prompt_template | self.llm_query_understanding | parser
        try:
            print(f"\n   分析用户查询：'{user_query}'")
            # *** 修正 invoke 调用，只传入模板需要的变量 ***
            response = chain.invoke({"user_query": user_query, "context_background": context_str})
            print(f"\n   LLM分析结果：{response}")

            # 增强检查，确保生成的 Prompt 非空
            if not isinstance(response, dict) or not all(
                    k in response for k in ["intent", "entities", "chunk_processing_prompt"]) or not response.get(
                "chunk_processing_prompt"):
                raise ValueError("LLM对查询理解的响应无效或未生成有效的chunk_processing_prompt。")
            return {
                "intent": response.get("intent"),
                "entities": response.get("entities"),
                "chunk_processing_prompt": response.get("chunk_processing_prompt")
            }
        except Exception as e:
            error_msg = f"无法理解查询或生成处理提示：{e}"
            # 添加更详细的错误追溯信息
            import traceback
            traceback_str = traceback.format_exc()
            print(f"\n   understand_query_node中出错：{error_msg}\nTraceback:\n{traceback_str}")
            return {"error_message": error_msg}

    def _chunk_node(self, state: AgentState) -> Dict[str, Any]:
        """节点：加载消息并按字节数分块。"""
        print(f"\n--- 运行节点：chunk_node（最大字节数：{self.max_bytes_per_chunk}）---")
        if state.get("error_message"): return {}  # 如果上一步出错，则跳过
        try:
            messages = state['input_dict'].get('data', [])
            if not messages:
                return {"error_message": "输入数据中未找到消息 ('data' key is missing or empty)。"}
            if not isinstance(messages, list):
                return {"error_message": f"输入数据的 'data' 字段必须是列表，实际类型是 {type(messages)}。"}

            message_chunks = self._chunk_by_byte_count(messages)
            # 即使分块结果为空（可能所有消息都超长被跳过），也继续流程，后续节点会处理空提取结果
            # if not message_chunks and messages: # 如果有消息但没有分块，可能是问题
            #      return {"error_message": "分块结果为零块，但输入消息不为空。请检查数据或分块逻辑/阈值。"}
            return {"messages": messages, "message_chunks": message_chunks}
        except Exception as e:
            error_msg = f"消息分块过程中失败：{e}"
            import traceback
            traceback_str = traceback.format_exc()
            print(f"\n   chunk_node中出错：{error_msg}\nTraceback:\n{traceback_str}")
            return {"error_message": error_msg}

    def _extract_info_node(self, state: AgentState) -> Dict[str, Any]:
        """节点：分块信息提取。"""
        print("\n", "--- 运行节点：extract_info_node ---")
        if state.get("error_message"): return {}
        message_chunks = state.get('message_chunks')
        chunk_processing_prompt = state.get('chunk_processing_prompt')

        if chunk_processing_prompt is None:  # 明确检查 None
            return {"error_message": "缺少用于提取的处理提示 (chunk_processing_prompt)。"}
        if message_chunks is None:  # 明确检查 None
            return {"error_message": "缺少消息块 (message_chunks)。"}
        if not message_chunks:
            print("\n   没有消息块需要处理，提取阶段跳过。")
            return {"extracted_data": []}  # 返回空列表，而不是错误

        extracted_data = []
        parser = StrOutputParser()
        # 使用 f-string 动态构建模板，确保 chunk_processing_prompt 被正确嵌入
        try:
            prompt_template = ChatPromptTemplate.from_template(
                f"""
{chunk_processing_prompt}

聊天记录片段:

```
{{chunk_text}}
```

提取的相关信息 (如果此片段不包含相关信息，请明确说明'无相关信息'):

**若是遇到其他预料外任何无法提取的场景，你应该返回 '由于xxxx原因，该片段无法总结。'，不要返回错误状态码。**
"""
            )
            chain = prompt_template | self.llm_extraction | parser
        except Exception as e:
            error_msg = f"创建提取链时出错: {e}"
            print(f"\n   {error_msg}")
            return {"error_message": error_msg}

        print(f"\n   使用生成的提示处理 {len(message_chunks)} 个块...")

        min_interval = 60.0 / self.rpm_limit if self.rpm_limit > 0 else 0
        last_call_time = time.monotonic()
        chunk_duration_list = []

        for i, chunk in enumerate(message_chunks):
            print(f"\n   处理块 {i + 1}/{len(message_chunks)}...")
            format_start = time.monotonic()
            formatted_chunk = self._format_chunk_for_llm(chunk)
            print(f"\n     格式化块 {i + 1} 耗时 {time.monotonic() - format_start:.2f} 秒。")
            if not formatted_chunk.strip():
                print(f"\n   跳过空块 {i + 1}")
                continue
            try:
                current_time = time.monotonic()
                elapsed = current_time - last_call_time
                if elapsed < min_interval:
                    wait_time = min_interval - elapsed
                    print(f"     等待 {wait_time:.2f} 秒以避免速率限制...")
                    time.sleep(wait_time)

                # 调用提取链
                invoke_start_time = time.monotonic()
                result = chain.invoke({"chunk_text": formatted_chunk})
                print(f"     块 {i + 1} 信息提取完成，耗时 {time.monotonic() - invoke_start_time:.2f} 秒。")
                last_call_time = time.monotonic()

                # 更鲁棒地检查是否无相关信息（忽略大小写和空格）
                if "无相关信息" not in result.strip().lower():
                    extracted_data.append(result)
                    print(f"     块 {i + 1} 提取到信息。")
                else:
                    print(f"     块 {i + 1} 无相关信息。")
                chunk_duration = time.monotonic() - format_start
                chunk_duration_list.append(chunk_duration)

                duration_all = sum(chunk_duration_list) / len(chunk_duration_list) * len(message_chunks)
                duration_left = duration_all - sum(chunk_duration_list)
                print(f"     块 {i + 1} 总耗时：{chunk_duration:.2f} 秒。")
                print(f"     预计总耗时: {duration_all:.2f} 秒，剩余 {duration_left:.2f} 秒")
            except Exception as e:
                error_msg = f"处理块 {i + 1} 时出错：{e}"
                import traceback
                traceback_str = traceback.format_exc()
                print(f"\n     {error_msg}\nTraceback:\n{traceback_str}")
                last_call_time = time.monotonic()
                extracted_data.append(f"[处理块 {i + 1} 时出错：{e}]")  # 记录错误信息

        print(f"\n   提取完成。在 {len(extracted_data)} 个结果中可能包含有效信息（包括错误标记）。")
        return {"extracted_data": extracted_data}

    def _synthesize_answer_node(self, state: AgentState) -> Dict[str, Any]:
        """节点：最终合成答案。"""
        print("\n", "--- 运行节点：synthesize_answer_node ---")
        if state.get("error_message"): return {}
        user_query = state['user_query']
        extracted_data = state.get('extracted_data')
        intent = state.get('intent', '回答用户问题')  # 使用从state获取的意图

        if user_query is None:
            return {"error_message": "最终合成缺少用户查询 (user_query)。"}
        if extracted_data is None:
            return {"error_message": "最终合成缺少提取数据 (extracted_data)。"}

        # 过滤掉之前标记的错误信息，只保留有效提取结果
        valid_extracted_data = [item for item in extracted_data if not item.startswith("[处理块")]
        error_markers = [item for item in extracted_data if item.startswith("[处理块")]

        if not valid_extracted_data:
            print("\n   未提取到任何有效相关信息。")
            error_report = "\n此外，处理部分数据块时遇到以下问题：\n" + "\n".join(error_markers) if error_markers else ""
            return {
                "final_answer": f"根据提供的聊天记录，未能找到与您的问题 '{user_query}' 直接相关的信息。{error_report}"}

        combined_context = "\n\n---\n\n".join(valid_extracted_data)
        print(f"\n   合并有效提取数据后的初始字节数: {len(combined_context.encode(self.byte_encoding))}")
        if error_markers:
            print(f"\n   注意到在提取阶段存在 {len(error_markers)} 个错误。")

        # 如果合并后的文本超出最大字节数，则进行递归融合
        if len(combined_context.encode(self.byte_encoding)) > self.max_bytes_per_chunk:
            print(f"\n   提取数据过长 ({len(combined_context.encode(self.byte_encoding))} bytes)，启动递归融合...")
            # 定义融合指令模板
            fusion_directive_template = SystemPrompts.chat_splitter_fusion_directive_template()
            try:
                # 将 user_query 放入模板，因为它对融合很重要
                formatted_fusion_template = fusion_directive_template.format(user_query=user_query,
                                                                             context="{context}")  # 预格式化user_query部分
                combined_context = self._recursive_fuse(
                    valid_extracted_data,  # 只融合有效数据
                    self.max_bytes_pre_recursive_fuse_chunk,
                    formatted_fusion_template  # 传递包含 user_query 的模板字符串
                )
                print(f"\n   递归融合后的最终字节数: {len(combined_context.encode(self.byte_encoding))}")
                if len(combined_context.encode(self.byte_encoding)) > self.max_bytes_per_chunk:
                    print("\n   警告：递归融合后文本仍超过最大字节数，可能影响最终合成质量。")
            except Exception as e:
                error_msg = f"递归融合过程中失败: {e}"
                import traceback
                traceback_str = traceback.format_exc()
                print(f"\n   {error_msg}\nTraceback:\n{traceback_str}")
                # 即使融合失败，也尝试用原始合并文本继续，但添加错误信息
                combined_context = "\n\n---\n\n".join(valid_extracted_data)  # 使用原始合并文本
                state['error_message'] = (state.get('error_message') or "") + f"; {error_msg}"  # 附加错误
                print("\n   融合失败，将尝试使用原始合并数据进行合成。")

        else:
            print("\n   提取数据未超长或已成功融合，无需（进一步）递归融合。")

        # --- 用于最终答案合成的链 ---
        # 使用 f-string 动态构建最终合成提示
        synthesis_prompt = SystemPrompts.chat_splitter_synthesis_prompt()  # 模板变量是 combined_context

        try:
            synthesis_prompt_template = ChatPromptTemplate.from_template(synthesis_prompt)
            parser = StrOutputParser()
            synthesis_chain = synthesis_prompt_template | self.llm_synthesis | parser

            print("\n   合成最终答案...")
            # 调用合成链，只需要传入 combined_context
            final_answer = synthesis_chain.invoke({"combined_context": combined_context, "user_query": user_query, "intent": intent})

            # 添加在提取阶段遇到的错误信息（如果存在）
            if error_markers:
                final_answer += "\n\n[请注意：在处理原始聊天记录的过程中，部分数据块未能成功提取信息，这可能影响答案的完整性。]"

            print("\n   已生成最终答案。")
            return {"final_answer": final_answer}

        except Exception as e:
            error_msg = f"最终答案合成过程中失败：{e}"
            import traceback
            traceback_str = traceback.format_exc()
            print(f"\n   {error_msg}\nTraceback:\n{traceback_str}")
            # 即使合成失败，也更新错误信息
            state['error_message'] = (state.get('error_message') or "") + f"; {error_msg}"
            # 尝试返回一个错误消息给用户，包含之前的错误（如果有）
            final_error_message = state.get("error_message", "发生未知错误")
            return {"final_answer": f"抱歉，在生成最终答案时遇到问题：{final_error_message}"}

    def _recursive_fuse(self, chunks: List[str], max_bytes: int, fusion_directive_template: str, level: int = 0) -> str:
        """
        递归融合函数，将多个摘要逐轮融合为一个摘要，确保最终文本不超过指定的最大字节数。

        参数:
            chunks: 一个字符串列表，每个字符串是之前提取或融合后的摘要文本。
            max_bytes: 模型允许的最大输入字节数（包括提示）。
            fusion_directive_template: 融合指令的字符串模板，应包含 {context} 占位符。
            level: 当前递归层数。

        返回:
            融合后的最终摘要文本。
        """
        print(f"\n   递归融合 - 层级 {level} - 输入块数: {len(chunks)}")
        # 增加递归深度限制
        if level > 7:  # 稍微增加深度限制
            print(f"\n   警告：递归融合层数超过限制（{level}），返回当前合并结果。")
            # 返回合并结果前尝试最后一次融合（如果需要）
            all_text_fallback = "\n\n---\n\n".join(chunks)
            if len(all_text_fallback.encode(self.byte_encoding)) > max_bytes:
                print("\n      合并结果仍超长，将进行截断处理。")
                # 简单的截断策略
                allowed_len = int(max_bytes * 0.95 / (
                        len(all_text_fallback.encode(self.byte_encoding)) / len(all_text_fallback) + 1e-6))
                return all_text_fallback[:allowed_len] + "...[因递归深度超限截断]"
            return all_text_fallback

        all_text = "\n\n---\n\n".join(chunks)
        # *** 关键：检查 all_text 加上 fusion_directive_template 的总长度 ***
        try:
            # 估算完整的 Prompt 字节数
            full_prompt_for_check = fusion_directive_template.format(context=all_text)
            full_prompt_bytes = len(full_prompt_for_check.encode(self.byte_encoding))
        except Exception as e:
            print(f"\n   警告：无法格式化融合模板以检查长度，使用近似值。错误: {e}")
            full_prompt_bytes = len(fusion_directive_template.encode(self.byte_encoding)) + len(
                all_text.encode(self.byte_encoding))

        print(f"\n   递归融合 - 层级 {level} - 估算总 Prompt 字节数: {full_prompt_bytes} / {max_bytes}")

        # --- 定义融合链 ---
        try:
            fusion_prompt = ChatPromptTemplate.from_template(fusion_directive_template)
            # 确保使用 StrOutputParser
            fusion_chain = fusion_prompt | self.llm_synthesis | StrOutputParser()
        except Exception as e:
            error_msg = f"递归融合 - 层级 {level} - 创建融合链失败: {e}"
            print(f"\n   错误：{error_msg}")
            raise ValueError(error_msg)  # 创建链失败是严重问题，直接抛出

        if full_prompt_bytes <= max_bytes:
            print(f"\n   递归融合 - 层级 {level} - 达到字节限制或只需一轮，执行最后融合。")
            try:
                # 调用链的 invoke，传入包含模板所需变量的字典
                # 模板现在只需要 'context'，因为 user_query 已包含在模板字符串中
                merged = fusion_chain.invoke({"context": all_text})
                print(f"\n   递归融合 - 层级 {level} - 最后融合完成。")
                return merged
            except Exception as e:
                error_msg = f"递归融合 - 层级 {level} - 最后融合调用LLM失败: {e}"
                import traceback
                traceback_str = traceback.format_exc()
                print(f"\n   错误：{error_msg}\nTraceback:\n{traceback_str}")
                raise  # 重新抛出异常，让上层处理（如 synthesize_answer_node 中的 try-except）

        # 超长则分组处理
        print(f"\n   递归融合 - 层级 {level} - 文本超长，进行分组融合。")
        grouped_chunks = []
        current_group = []
        current_len_bytes = 0

        # 估算融合提示本身的开销 (不含 context 部分)
        try:
            estimated_prompt_only_bytes = len(fusion_directive_template.format(context="").encode(self.byte_encoding))
        except Exception:
            estimated_prompt_only_bytes = 200  # 粗略估计

        # 为分组内容留出的有效字节数
        effective_max_bytes_for_group = max_bytes - estimated_prompt_only_bytes - 150  # 再减去一些余量给分隔符和模型开销

        if effective_max_bytes_for_group <= 0:
            print(
                f"\n   警告：递归融合 - 层级 {level} - 计算出的分组有效最大字节数过小 ({effective_max_bytes_for_group})，可能导致分组问题。调整为 {max_bytes // 2}")
            effective_max_bytes_for_group = max_bytes // 2

        print(f"\n   递归融合 - 层级 {level} - 分组时内容最大有效字节数: {effective_max_bytes_for_group}")
        separator_bytes = len("\n\n---\n\n".encode(self.byte_encoding))

        for i, chunk in enumerate(chunks):
            try:
                chunk_bytes = len(chunk.encode(self.byte_encoding))
            except Exception as e:
                print(f"\n   警告：无法编码块 {i} 进行分组，跳过。错误: {e}")
                continue

            # 检查单块是否超长（理论上不应发生，因为块是融合结果，但做个检查）
            if chunk_bytes > effective_max_bytes_for_group:
                print(
                    f"\n   警告：递归融合 - 层级 {level} - 单个融合块 {i} 仍超过分组限制 ({chunk_bytes} > {effective_max_bytes_for_group})，尝试截断。")
                # 简单截断
                allowed_chunk_len = int(effective_max_bytes_for_group * 0.95 / (chunk_bytes / len(chunk) + 1e-6))
                chunk = chunk[:allowed_chunk_len] + "...[截断]"
                chunk_bytes = len(chunk.encode(self.byte_encoding))
                if chunk_bytes > effective_max_bytes_for_group:
                    print("\n      截断后仍超长，此块无法分组。")
                    continue  # 跳过无法处理的块

            # 判断是否需要新开分组
            # 需要考虑加入当前块的字节数和分隔符字节数（如果不是第一个块）
            bytes_if_added = current_len_bytes + chunk_bytes + (separator_bytes if current_group else 0)

            if bytes_if_added > effective_max_bytes_for_group and current_group:
                # 当前分组已满，保存
                grouped_chunks.append("\n\n---\n\n".join(current_group))
                print(
                    f"\n     分组 {len(grouped_chunks)} 创建，包含 {len(current_group)} 个块，内容字节数 ~{current_len_bytes}")
                current_group = [chunk]
                current_len_bytes = chunk_bytes  # 新分组的初始长度
            else:
                # 加入当前分组
                current_group.append(chunk)
                current_len_bytes += chunk_bytes + (
                    separator_bytes if len(current_group) > 1 else 0)  # 只有第二个及之后的块才加分隔符长度

        # 加入最后一个分组
        if current_group:
            grouped_chunks.append("\n\n---\n\n".join(current_group))
            print(
                f"\n     分组 {len(grouped_chunks)} 创建（最后），包含 {len(current_group)} 个块，内容字节数 ~{current_len_bytes}")

        if not grouped_chunks and chunks:  # 如果有输入但没分成分组
            print(
                "\n   错误：递归融合 - 层级 {level} - 未能创建任何分组。可能是因为单个块即使截断后也超长，或字节计算问题。")
            # 返回原始合并文本（可能超长）或抛出错误
            return all_text  # 或者 raise ValueError("无法创建分组进行融合")
        elif not grouped_chunks and not chunks:  # 如果输入为空
            return ""  # 返回空字符串

        fused_chunks = []
        print(f"\n   递归融合 - 层级 {level} - 开始融合 {len(grouped_chunks)} 个分组...")
        min_interval = 60.0 / self.rpm_limit if self.rpm_limit > 0 else 0  # 应用速率限制
        last_call_time = time.monotonic()

        for i, group in enumerate(grouped_chunks):
            print(f"\n     融合分组 {i + 1}/{len(grouped_chunks)}...")
            try:
                current_time = time.monotonic()
                elapsed = current_time - last_call_time
                if elapsed < min_interval:
                    wait_time = min_interval - elapsed
                    print(f"\n       等待 {wait_time:.2f} 秒以避免速率限制...")
                    time.sleep(wait_time)

                # 调用融合链
                group_summary = fusion_chain.invoke({"context": group})
                last_call_time = time.monotonic()
                fused_chunks.append(group_summary)
                print(f"\n     分组 {i + 1} 融合完成。")
            except Exception as e:
                error_msg = f"递归融合 - 层级 {level} - 融合分组 {i + 1} 调用LLM失败: {e}"
                import traceback
                traceback_str = traceback.format_exc()
                print(f"\n   错误：{error_msg}\nTraceback:\n{traceback_str}")
                last_call_time = time.monotonic()
                # 记录错误并继续，避免整个流程失败
                fused_chunks.append(f"[融合分组 {i + 1} 时出错: {e}]")

        # 递归调用，处理融合后的块
        return self._recursive_fuse(fused_chunks, max_bytes, fusion_directive_template, level + 1)

    def _handle_error_node(self, state: AgentState) -> Dict[str, Any]:
        """节点：处理错误。"""
        print("\n", "--- 运行节点：handle_error_node ---")
        error = state.get("error_message", "发生未知错误。")
        print(f"\n   捕获到错误：{error}")
        # 在最终答案中包含错误信息
        final_answer = f"抱歉，处理您的请求时遇到问题：\n{error}"
        # 即使出错，也返回 final_answer 键，符合图的最终输出预期
        return {"final_answer": final_answer, "error_message": error}  # 保留错误信息

    # --- 条件边缘逻辑 ---
    def _should_continue(self, state: AgentState) -> str:
        """决定是继续还是跳转到错误处理。"""
        if state.get("error_message"):
            print("\n", "--- 边缘条件：检测到错误，路由到 handle_error ---")
            return "error"
        else:
            # 检查关键数据是否存在以决定下一步
            current_node = state.get('__node__', '')  # Langgraph 内部状态可能包含当前节点名
            if current_node == "chunker" and not state.get("message_chunks"):
                # 如果分块后没有块（即使输入有消息），这可能是一个有效状态（例如所有消息都超长）
                # 应该继续到提取阶段，提取阶段会处理空列表
                print("\n", "--- 边缘条件：分块后无有效块，继续到提取 ---")
                return "continue"
            print(f"\n--- 边缘条件：无错误，从 {current_node or '入口'} 继续 ---")
            return "continue"

    # --- 图构建方法 ---
    def _build_graph(self) -> CompiledStateGraph:
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
        # 每个可能产生错误的节点后都进行检查
        workflow.add_conditional_edges(
            "understand_query",
            self._should_continue,
            {"continue": "chunker", "error": "handle_error"}
        )
        workflow.add_conditional_edges(
            "chunker",
            self._should_continue,
            {"continue": "extract_info", "error": "handle_error"}
        )
        workflow.add_conditional_edges(
            "extract_info",
            self._should_continue,
            # 即使提取有部分错误（记录在 extracted_data 中），也应尝试合成，合成节点会处理错误标记
            {"continue": "synthesize_answer", "error": "handle_error"}
        )
        # synthesize_answer 节点内部已经处理了最终的错误情况，如果它自己失败了，
        # 它的返回值会包含 error_message，所以这里也需要检查
        workflow.add_conditional_edges(
            "synthesize_answer",
            self._should_continue,
            {"continue": END, "error": "handle_error"}
        )
        # 错误处理节点是终点
        workflow.add_edge("handle_error", END)

        return workflow.compile()

    # --- 公共执行方法 ---
    def run(self, _chat_data: Dict[str, Any], user_query: str) -> Dict[str, Any]:
        """
        执行 Agent 来处理聊天数据并回答问题。

        Args:
            _chat_data: 包含 'meta' 和 'data' 的聊天记录字典。'data'应为消息列表。
            user_query: 用户的问题字符串。

        Returns:
            包含最终状态的字典，其中 'final_answer' 是给用户的答案或错误信息。
        """
        if not isinstance(_chat_data, dict) or 'data' not in _chat_data:
            raise ValueError("Invalid chat_data format. Expected a dict with a 'data' key.")
        if not isinstance(user_query, str) or not user_query.strip():
            raise ValueError("user_query must be a non-empty string.")

        initial_state: AgentState = {
            "input_dict": _chat_data,
            "user_query": user_query,
            "intent": None,
            "entities": None,
            "chunk_processing_prompt": None,
            "messages": [],
            "message_chunks": [],
            "extracted_data": [],
            "final_answer": None,
            "error_message": None,
        }

        print("\n\n--- 开始Agent执行 ---")
        final_state = {}
        try:
            config = {"recursion_limit": self.recursion_limit}
            final_state = self.app.invoke(initial_state, config=config)
            print("\n--- Agent执行完成 ---")

        except Exception as e:
            # 捕获 LangGraph 执行期间未被内部错误处理捕获的意外错误
            error_msg = f"Agent执行期间发生意外错误: {e}"
            import traceback
            traceback_str = traceback.format_exc()
            print(f"\n   {error_msg}\nTraceback:\n{traceback_str}")
            # 构建一个表示错误的最终状态
            final_state = initial_state.copy()  # 复制初始状态
            final_state['error_message'] = error_msg
            final_state['final_answer'] = f"抱歉，处理请求时发生系统级错误：{e}"

        # 确保 final_state 总是包含 final_answer 和 error_message
        if 'final_answer' not in final_state:
            final_state['final_answer'] = "处理已完成，但未生成明确的最终答案。"
        if 'error_message' not in final_state:
            final_state['error_message'] = None  # 或根据情况设置

        return final_state

# TODO:
#   1. 增加任务表格绑定拓展断点重试
#   2. 使用 Celery 或 RQ创建任务队列系统 `pip install celery redis`
#   3. 最后融合总结时，若是得出的chunk总结又超出了融合模型的最大输入。又要分块？  -- 2025/05/12 使用递归融合方案，待接入主程序
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
#   4. 考虑把intermediate_results指向到JSONL中，优化SQLite的性能
