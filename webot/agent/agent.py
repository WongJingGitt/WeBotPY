from typing import List, Dict
from sqlite3 import connect

from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.sqlite import SqliteSaver

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, BaseMessage

from webot.llm.llm import LLMFactory
from webot.tool_call.tools import ALL_TOOLS
from webot.utils.project_path import DATA_PATH, path
from webot.prompts.system_prompts import SystemPrompts

CHECKPOINT_DB_PATH = path.join(DATA_PATH, 'databases', 'webot_checkpoint.db')


class WeBotAgent:

    def __init__(self, model_name: str = "glm-4-flash", llm_options: dict = {}, webot_port: int = 19001, username: str = ''):
        self.llm = LLMFactory.llm(model_name=model_name, **llm_options)

        self._sqlite_con = connect(CHECKPOINT_DB_PATH, check_same_thread=False)
        self.checkpoint = SqliteSaver(conn=self._sqlite_con)
        username = f"\n   - **用户名：** 当前登录的用户名叫：`{username}`，你可以使用`{username}`称呼用户。" if username else ''
        system_prompt = SystemPrompts.webot_system_prompt(webot_port=webot_port, username=username)

        self.agent = create_react_agent(
            model=self.llm,
            tools=ALL_TOOLS,
            checkpointer=self.checkpoint,
            prompt=SystemMessage(content=system_prompt)
        )

    def chat(self, message: Dict[str, List[BaseMessage | dict]],
             thread_id: int | str = -1):  # -> List[HumanMessage|AIMessage|ToolMessage]:
        return self.agent.stream(message, stream_mode=['updates'],
                                 config={"configurable": {"thread_id": str(thread_id)}})
