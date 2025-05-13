from os import getenv

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import SecretStr

from webot.llm.llm_types import MissingApiKeyError

load_dotenv()


class LLMFactory:

    @staticmethod
    def llm(model_name, apikey, base_url, *args, **kwargs):
        if "gemini" not in model_name:
            return ChatOpenAI(
                model=model_name,
                api_key=SecretStr(apikey),
                base_url=base_url,
                *args, **kwargs
            )

        if "gemini" in model_name:
            return ChatGoogleGenerativeAI(
                api_key=SecretStr(apikey),
                model=model_name,
                **kwargs,
            )

    @staticmethod
    def glm_llm(model="glm-4-flash", *args, **kwargs):
        api_key = getenv("GLM_API_KEY")
        if not api_key:
            raise MissingApiKeyError("GLM_API_KEY is not set, please set it in .env file")

        return ChatOpenAI(
            model=model,
            base_url="https://open.bigmodel.cn/api/paas/v4/",
            api_key=SecretStr(api_key),
            *args,
            **kwargs,
        )

    @staticmethod
    def gemini_llm(model="gemini-2.0-flash-exp", **kwargs):
        api_key = getenv("GEMINI_API_KEY")
        if not api_key:
            raise MissingApiKeyError("GEMINI_API_KEY is not set, please set it in .env file")

        return ChatGoogleGenerativeAI(
            api_key=SecretStr(api_key),
            model=model,
            max_retries=10,
            **kwargs
        )

    @staticmethod
    def aliyun_deepseek_llm(model="deepseek-v3", *args, **kwargs):
        api_key = getenv("ALIYUN_API_KEY")
        if not api_key:
            raise MissingApiKeyError("ALIYUN_API_KEY is not set, please set it in .env file")

        return ChatOpenAI(
            model=model,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=SecretStr(api_key),
            *args,
            **kwargs,
        )

    @staticmethod
    def aliyun_deepseek_r1_llm(model="deepseek-r1", *args, **kwargs):
        api_key = getenv("ALIYUN_API_KEY")
        if not api_key:
            raise MissingApiKeyError("ALIYUN_API_KEY is not set, please set it in .env file")

        return ChatOpenAI(
            model=model,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=SecretStr(api_key),
            *args,
            **kwargs,
        )

    @staticmethod
    def aliyun_qwen2_5_14b_llm(model="qwen2.5-14b-instruct-1m", *args, **kwargs):
        api_key = getenv("ALIYUN_API_KEY")
        if not api_key:
            raise MissingApiKeyError("ALIYUN_API_KEY is not set, please set it in .env file")
        return ChatOpenAI(
            model=model,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=SecretStr(api_key),
            *args,
            **kwargs,
        )

    @staticmethod
    def deepseek_v3_llm(model="deepseek-chat", *args, **kwargs):
        api_key = getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise MissingApiKeyError("DEEPSEEK_API_KEY is not set, please set it in .env file")
        return ChatOpenAI(
            model=model,
            base_url="https://api.deepseek.com",
            api_key=SecretStr(api_key),
            *args,
            **kwargs,
        )


    @staticmethod
    def volcengine_llm(model="doubao-pro-256k-241115", *args, **kwargs):
        api_key = getenv("VOLCENGINE_API_KEY")
        if not api_key:
            raise MissingApiKeyError("VOLCENGINE_API_KEY is not set, please set it in .env file")
        return ChatOpenAI(
            model=model,
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key=SecretStr(api_key),
            *args,
            **kwargs,
        )