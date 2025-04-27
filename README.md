# WeBot 微宝机器人

[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) [![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/) [![WXHOOK](https://img.shields.io/badge/Based%20on-WXHOOK-blueviolet)](https://github.com/miloira/wxhook) [![WechatMsg/留痕](https://img.shields.io/badge/Based%20on-WechatMsg/留痕-blueviolet)](https://github.com/LC044/WeChatMsg) [![WXHelper](https://img.shields.io/badge/Based%20on-WXHelper-blueviolet)](https://github.com/ttttupup/wxhelper)

### 基于大语言模型 (LLM) 的智能微信助手，专注于本地聊天记录分析与管理。

WeBot 是一个结合 [WXHOOK](https://github.com/miloira/wxhook) 和大型语言模型 (LLM) 的工具，旨在帮助您更智能地管理和理解您的微信信息。它的**核心优势在于处理和分析存储在您本地计算机上的聊天记录和联系人数据**。

**主要功能包括：**

*   **与 AI 智能交互**: 就您的微信数据进行提问和获取帮助 (支持上下文、工具调用)。
*   **聊天记录分析与总结**:
    *   *示例: 帮我总结一下我和迪丽热巴最近一周的聊天记录*
    *   *示例: 迪丽热巴上周五为什么生气？帮我从聊天记录中分析一下。*
*   **基础消息发送**: (注意：请阅读下方风险提示)
    *   *示例: 帮我跟迪丽热巴说一下，今晚我不会去吃饭了。*
    *   *示例: 帮我总结一下我和吴彦祖昨天的行程规划，然后把总结好的行程发给小王并且提醒他记得订机票。*

**⚠️ 请注意：功能侧重与使用风险**

1.  **重点在于分析**: 本项目的设计初衷是作为一个强大的**信息处理助手**，帮助您从**本地**聊天记录中提取价值、进行总结和分析。这类**读取和分析操作通常是安全的**，在作者的测试中未遇到因仅执行此类操作而导致的封号问题。
2.  **消息发送是辅助功能**: 虽然 WeBot 具备通过代码发送消息的能力，但这被视为一个**基础且辅助性**的功能。**不建议**将其用于构建**自动回复机器人**或进行**高频率**的消息发送，因为这类行为违反微信使用策略，**有较高的封号风险**。本项目不会重点开发应答机器人相关的复杂功能。
3.  **用户责任**: 使用任何非官方接口与微信交互都存在潜在风险。请用户自行判断并承担使用风险，**避免进行批量加好友、自动拉群、消息轰炸等明确违规的操作**。

## ✨ 功能特性

*   **启动和管理微信机器人**: 通过 API 控制 WXHOOK 实例的启动和状态检查，支持微信多开。
*   **AI 智能对话**:
    *   集成 Langgraph ReAct Agent，能够理解用户意图、调用工具并进行多轮对话。
    *   支持多种 LLM (例如 GLM-4-Flash, DeepSeek，Gemini)，可在前端手动切换。
    *   流式响应 (Server-Sent Events)，实时显示 AI 思考过程、工具调用和最终结果。
*   **微信信息交互**:
    *   读取联系人信息 (支持精确/模糊搜索)。
    *   读取指定联系人/群聊的聊天记录。
    *   导出聊天记录为多种格式文件 (JSON, TXT, YAML, DOCX)。
*   **聊天记录处理**:
    *   调用 LLM 对导出的聊天记录进行内容总结和分析。
*   **Web 服务**:
    *   基于 Flask 提供 HTTP API 接口，方便前端或其他服务集成。
    *   提供美观的 Web 界面。
*   **数据持久化**:
    *   存储和管理 AI 对话历史 (`ConversationsDatabase`)。
    *   管理 LLM 配置信息 (`LLMConfigDatabase`)。

## 🛠️ 技术栈

*   **微信交互**: WXHOOK
*   **AI Agent**: Langchain, Langgraph
*   **Web 框架**: Flask, Flask-CORS
*   **数据库**: SQLite (默认，用于存储对话和配置)
*   **LLM**: 支持 ZhipuAI (GLM), DeepSeek，Gemini 等，具体可以在前端页面配置
*   **核心语言**: Python

## 🚀 环境要求

*   **Python**: 3.10+ (推荐)
*   **微信客户端**:  **必需要安装[微信3.9.5.81](https://github.com/tom-snow/wechat-windows-versions/releases/download/v3.9.5.81/WeChatSetup-3.9.5.81.exe)版本。**
*   **依赖库**: 查看 `setup.py` 文件。
*   **LLM API Key**: 需要配置所使用的大语言模型的 API Key，可在前端配置，API Key仅会保存在本地数据库 `LLMConfigDatabase` 中。

## ⚙️ 安装与启动

1.  **克隆仓库**:
    ```bash
    git clone https://github.com/WongJingGitt/WeBotPY.git
    cd WeBotPY
    ```

2.  **安装依赖**:
    ```bash
    # (建议在虚拟环境中执行)
    pip install .
    ```

3.  **配置**:
    *   确保已安装兼容版本的微信 PC 客户端。

4.  **运行后端服务**:
    ```bash
    # 默认使用16001端口启动WEB服务
    webot
    ```
    *   服务将在 `http://127.0.0.1:16001` 启动。
    ---
    ```bash
    # 或者可以使用 -P 指定启动的端口号
    webot -P 17001
    ```
    *  服务将在 `http://127.0.0.1:17001` 启动。

5.  **开始交互**:
    *   可以通过访问 `http://127.0.0.1:16001/` 或直接调用 API 与 AI Agent 进行交互。

6. **启动微信**:
    1. 打开网页 `http://127.0.0.1:16001/`
    2. 点击右上角`登陆新账号`按钮启动微信
    
        > 勿直接在桌面点击微信图标启动，会提示版本过低无法启动。
        若是微信自动更新了新版本，导致登录不成功，需要重新安装3.9.5.81版本    

7. **配置模型与API Key**:
    *   可以在前端页面中增加第三方模型、配置API Key。
    *   在添加模型之前，请确保模型务必支持`Function Call`

## 🧩 API 说明

具体查看Services模块源代码

## 🏗️ 核心模块

*   **`main.py`**: 程序入口，启动 Flask Web 服务。
*   **`agent/`**: 包含 AI Agent 的定义 (`agent.py`) 和相关类型 (`agent_types.py`)。负责处理用户请求，调用 LLM 和工具。
*   **`bot/`**: 包含与 WXHOOK 和微信数据交互的逻辑。
    *   `webot.py`: 封装了 WXHOOK 的常用操作，如获取联系人、消息、导出记录等。
    *   `write_doc.py`/`write_txt.py`: 辅助导出聊天记录到不同文件格式。
    *   `contact_captor.py`: 辅助进行联系人搜索。
*   **`llm/`**: LLM 相关封装，提供统一的接口调用不同的语言模型。
*   **`services/`**: Flask 服务层。
    *   `service_main.py`: 主服务逻辑，定义核心 API 路由。
    *   `service_conversations.py`: 处理对话历史相关的 API。
    *   `service_llm.py`: 处理 LLM 配置相关的 API。
*   **`databases/`**: 数据库模型和操作，用于持久化存储。
*   **`tool_call/`**: 定义了 AI Agent 可以使用的工具函数 (例如 `get_contact`, `export_message` 等)。
*   **`utils/`**: 通用工具函数和辅助模块。
*   **`static/`**: 前端静态文件。

## ⚠️ 注意事项

*   **微信版本依赖**: 本项目强依赖于 WXHOOK 所支持的特定微信 PC 版本。请确保使用的微信版本与 WXHOOK 兼容。
*   **稳定性**: WXHOOK 通过逆向工程实现，微信版本更新可能导致其失效。
*   **LLM 成本**: 使用 LLM API 会产生费用，请注意控制使用量。
*   **错误处理**: 代码中包含一定的错误处理，但实际使用中可能遇到未覆盖的异常情况。

## 🛡️ 数据安全与隐私

**请仔细阅读以下说明：**

*   **API Key 安全**: 您的 LLM API Key **仅会**存储在您运行本服务**本地计算机**的 SQLite 数据库 (`llm_configs.db`) 中。本项目**绝不会**将您的 API Key 上传到任何远程服务器或进行收集。数据库文件本身也存储在本地。
*   **聊天记录处理**:
    *   **本地存储**: 本项目本身**不会**持久化存储您的完整微信聊天记录内容。对话历史数据库 (`conversations.db`) 主要存储 AI 对话的上下文信息（如消息 ID、会话 ID），而非原始的、完整的微信聊天记录。当您执行**导出**操作时，聊天记录会被读取并保存为您指定的本地文件。
    *   **LLM 分析**: 当您使用需要调用 LLM 进行**内容总结或分析**的功能时 (例如，对获取的聊天记录进行分析)，相应的文本数据**会被发送**给您所配置的第三方 LLM 服务提供商 (如 ZhipuAI, DeepSeek 等)。**这是您主动触发的操作，数据仅在处理该请求时传输**。请务必了解并信任您所使用的 LLM 服务商的隐私政策和数据处理方式。
    *   **导出文件**: 使用“导出聊天记录”功能创建的文件 (JSON, TXT, DOCX 等) **只会保存在您的本地计算机上**，项目本身**不会**自动上传或分享这些文件到任何地方。
*   **本地运行**: 整个后端服务、WXHOOK 均在您的本地环境运行，直接与本地微信客户端交互。除了上述调用 LLM API 的特定情况外，数据处理主要在您的本地设备上完成。

**总之：您的 API Key 和微信聊天记录主要保留在您的本地控制之下。只有在您明确使用需要调用大模型的分析功能时，相关文本才会发送给对应的 LLM 服务商。导出文件完全本地保存。**

请确保您的运行环境安全，并妥善保管您的 API Key。


## License

本项目遵循 [MIT](LICENSE) 协议。详情请查看 [LICENSE](LICENSE) 文件。