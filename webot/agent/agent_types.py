from typing import Literal, TypedDict
from langgraph.graph import MessagesState


class TaskStatus(TypedDict):
    status: Literal['IN_PROGRESS', 'COMPLETED', 'NEED_CLARIFICATION']

    messages: MessagesState

    model_name: str

    llm_options: dict

    current_step: int | None