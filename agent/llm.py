from os import getenv

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import SecretStr

load_dotenv()


class LLMFactory:

    @staticmethod
    def glm_llm(model="glm-4-flash", *args, **kwargs):
        api_key = getenv("GLM_API_KEY")
        if not api_key:
            raise EnvironmentError("GLM_API_KEY is not set, please set it in .env file")

        return ChatOpenAI(
            model=model,
            base_url="https://open.bigmodel.cn/api/paas/v4/",
            api_key=SecretStr(api_key),
            *args,
            **kwargs,
        )

    @staticmethod
    def gemini_llm(model="gemini-2.0-flash-exp", *args, **kwargs):
        api_key = getenv("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY is not set, please set it in .env file")

        return ChatGoogleGenerativeAI(
            api_key=SecretStr(api_key),
            model=model,
            *args,
            **kwargs,
        )

    @staticmethod
    def aliyun_deepseek_llm(model="deepseek-v3", *args, **kwargs):
        api_key = getenv("ALIYUN_API_KEY")
        if not api_key:
            raise EnvironmentError("ALIYUN_API_KEY is not set, please set it in .env file")

        return ChatOpenAI(
            model=model,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=SecretStr(api_key),
            *args,
            **kwargs,
        )