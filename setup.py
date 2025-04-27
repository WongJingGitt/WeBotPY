from setuptools import setup, find_packages

RELEASE_PACKAGE_NAME = "ai-webot"
CURRENT_PACKAGE_NAME = "webot"

setup(
    name=RELEASE_PACKAGE_NAME,
    version="0.1.0",
    description="一个基于大语言模型 (LLM) 的智能微信助手，专注于本地聊天记录分析与管理。",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/WongJingGitt/WeBotPY",
    author="WongJingGit",
    author_email="WongJingGit@163.com",
    license="MIT",
    packages=find_packages(include=[CURRENT_PACKAGE_NAME, f"{CURRENT_PACKAGE_NAME}.*"]),
    package_dir={CURRENT_PACKAGE_NAME: CURRENT_PACKAGE_NAME},
    include_package_data=True,
    install_requires=[
        "flask",
        "dotenv",
        "langchain_openai",
        "langchain_google_genai",
        "beautifulsoup4",
        "lxml",
        "wxhook",
        "python-docx",
        "zhipuai",
        "langgraph",
        "flask_cors",
        "langchain_text_splitters",
        "langgraph-checkpoint-sqlite",
        "pydantic",
        "langchain_core",
        "xmltodict",
        "lz4",
        "dill",
        "tomlkit",
        "pluggy",
        "protobuf==3.20.2"
    ],
    entry_points={
        "console_scripts": [
            "webot=webot.main:command_runner"
        ]
    }
)