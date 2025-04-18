from typing import List, Dict, Tuple
from pathlib import Path
from base64 import b64encode
from json import loads

from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import MessagesState
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel

from llm.llm import LLMFactory
from agent.agent import BASE_CHECKPOINTER

class ParseResult(BaseModel):
    output: List[str]

class ImageRecognitionAgent:

    def __init__(self, model_name: str = "glm-4v-flash", llm_options: dict = {}, webot_port: int = 19001):
        
        self.llm = LLMFactory.llm(model_name, **llm_options)

        self.agent = create_react_agent(
            model=self.llm,
            tools=[],
            prompt=SystemMessage(content=self.__system_prompt)
        )
        self._parser = JsonOutputParser(pydantic_object=ParseResult)


    @property
    def __system_prompt(self):
        return """
# **角色设定**
你是一位专业的图片内容分析师，专长是精确识别和描述图片信息。

# **工作流程**
你会收到嵌入在微信聊天记录中的图片。

# **核心职责**
你的任务是为每一张接收到的图片提供一段准确、客观、信息密集的中文文本描述。

# **描述要求**
1.  **客观性**: 只描述你看到的视觉内容，不添加主观判断、情感色彩或推测图片背景故事。
2.  **关键元素**: 重点识别并描述图片中的主要对象、人物（数量、大致动作）、关键物品、环境场景以及任何清晰可见的文字信息。
3.  **简洁性**: 描述应尽可能简洁明了，抓住核心信息。
4.  **服务目标**: 牢记这些描述是为后续的AI模型分析聊天上下文服务的，因此信息的准确性和相关性至关重要。
5.  **输出要求**: 你必须输出一个字典，用`output`键设置一个列表，列表按照输入的顺序，输出每个描述的图片识别结果。例如：
    用户输入：
        ```json
        [{"type": "image_url", "image_url":"data:image/png;base64, xxx"}, {"type": "image_url", "image_url":"data:image/png;base64, xxx"}]
        ```
    你应该输出：
        ```json
        {
            "output": [
                "图中是一个苹果",
                "图中是一个香蕉"
            ]
        }
        ```

# **强制性异常处理**
在任何情况下，如果图片无法加载、无法识别其内容（例如图片模糊、损坏、内容过于抽象或无法辨认），或遇到任何技术问题导致无法生成有意义的描述，**必须且仅能**返回文本：“无具体描述”。不得返回任何其他错误信息或解释。
"""


    def invoke(self, img_path: Dict[str, str] | List[Dict[str, str]] ) -> Tuple[List[str], List[str | int]]:
        if isinstance(img_path, dict):
            img_path_list = [img_path]
        else:
            img_path_list = img_path

        image_base64_list = []
        message_id_list = []

        for item in img_path_list:
            _path = item.get("path")
            _message_id = item.get("message_id")
            _path = Path(_path)
            if not _path.exists():
                continue

            with _path.open("rb") as rb:
                img_base64 = b64encode(rb.read()).decode('utf-8')
            
            image_base64_list.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{img_base64}"
                }
            })
            message_id_list.append(_message_id)
        messages = MessagesState(messages=[HumanMessage(content=image_base64_list)])
        response = self.agent.invoke(messages, config={"configurable": {"thread_id": 43}})
        try:
            result = self._parser.parse(response.get('messages')[-1].content)
            result = result.get('output')
        except Exception as e:
            result = None

        return result, message_id_list