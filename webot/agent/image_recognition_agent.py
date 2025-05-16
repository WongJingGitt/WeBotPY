from typing import List, Dict, Tuple
from pathlib import Path
from base64 import b64encode

from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import MessagesState
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel

from webot.llm.llm import LLMFactory
from webot.prompts.system_prompts import SystemPrompts


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
        return SystemPrompts.image_recognition_prompt()

    def invoke(self, img_path: Dict[str, str] | List[Dict[str, str]]) -> Tuple[List[str], List[str | int]]:
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
            if len(message_id_list) == 1 and len(result) > 1:
                result = [' | '.join(result)]
        except Exception as e:
            result = ["无具体描述"] * len(message_id_list)

        return result, message_id_list
