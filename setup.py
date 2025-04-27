from setuptools import setup, find_packages

setup(
    name="webot",
    version="0.1.0",
    packages=find_packages(where='webot'),
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