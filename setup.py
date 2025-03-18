from setuptools import setup, find_packages

setup(
    name="Webot",
    version="0.1.0",
    packages=find_packages(),
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
        "langchain_core"
    ]
)