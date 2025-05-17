from webot.utils.project_path import ROOT_PATH
from pathlib import Path

ROOT_PATH = Path(ROOT_PATH)
PROMPTS_PATH = ROOT_PATH / "prompts"
TOOLS_PROMPT_PATH = PROMPTS_PATH / "tools_prompts"


class ToolsPrompts:

    @staticmethod
    def get_current_time_prompt() -> str:
        return TOOLS_PROMPT_PATH.joinpath("get_current_time_prompt.md").read_text(encoding="utf-8")

    @staticmethod
    def get_contact_prompt() -> str:
        return TOOLS_PROMPT_PATH.joinpath("get_contact_prompt.md").read_text(encoding="utf-8")

    @staticmethod
    def get_user_info_prompt() -> str:
        return TOOLS_PROMPT_PATH.joinpath("get_user_info_prompt.md").read_text(encoding="utf-8")

    @staticmethod
    def get_message_by_wxid_and_time_prompt() -> str:
        return TOOLS_PROMPT_PATH.joinpath("get_message_by_wxid_and_time_prompt.md").read_text(encoding="utf-8")

    @staticmethod
    def send_text_message_prompt() -> str:
        return TOOLS_PROMPT_PATH.joinpath("send_text_message_prompt.md").read_text(encoding="utf-8")

    @staticmethod
    def send_mention_message_prompt() -> str:
        return TOOLS_PROMPT_PATH.joinpath("send_mention_message_prompt.md").read_text(encoding="utf-8")

    @staticmethod
    def export_message_prompt() -> str:
        return TOOLS_PROMPT_PATH.joinpath("export_message_prompt.md").read_text(encoding="utf-8")

    @staticmethod
    def get_memories_prompt() -> str:
        return TOOLS_PROMPT_PATH.joinpath("get_memories_prompt.md").read_text(encoding="utf-8")

    @staticmethod
    def add_memory_prompt() -> str:
        return TOOLS_PROMPT_PATH.joinpath("add_memory_prompt.md").read_text(encoding="utf-8")

    @staticmethod
    def delete_memory_prompt() -> str:
        return TOOLS_PROMPT_PATH.joinpath("delete_memory_prompt.md").read_text(encoding="utf-8")