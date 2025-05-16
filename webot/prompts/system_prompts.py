from webot.utils.project_path import ROOT_PATH
from pathlib import Path

ROOT_PATH = Path(ROOT_PATH)
PROMPTS_PATH = ROOT_PATH / "prompts"
SYSTEM_PROMPT_PATH = PROMPTS_PATH / "system_prompts"


class SystemPrompts:

    @staticmethod
    def webot_system_prompt(webot_port: int, username: str = '') -> str:
        """
        Webot 核心提示词
        :param webot_port: 微信服务端口号
        :param username: 登录账号信息，用户名
        :return: 完整的提示词
        """
        return SYSTEM_PROMPT_PATH.joinpath("webot_system_prompt.md").read_text(encoding="utf-8").format(
            webot_port=webot_port, username=username)

    @staticmethod
    def chat_splitter_understand_prompt() -> str:
        """
        长聊天拆分的任务规划师提示词
        :return:
        """
        return SYSTEM_PROMPT_PATH.joinpath("chat_splitter_understand_prompt.md").read_text(encoding="utf-8")

    @staticmethod
    def chat_splitter_fusion_directive_template() -> str:
        """
        长聊天拆分的递归融合提示词
        :return:
        """
        return SYSTEM_PROMPT_PATH.joinpath("chat_splitter_fusion_directive_template.md").read_text(encoding="utf-8")

    @staticmethod
    def chat_splitter_synthesis_prompt() -> str:
        """
        长聊天拆分的最终融合提示词
        :return:
        """
        return SYSTEM_PROMPT_PATH.joinpath("chat_splitter_synthesis_prompt.md").read_text(encoding="utf-8")

    @staticmethod
    def image_recognition_prompt() -> str:
        """
        图片识别提示词
        :return:
        """
        return SYSTEM_PROMPT_PATH.joinpath("image_recognition_prompt.md").read_text(encoding="utf-8")
