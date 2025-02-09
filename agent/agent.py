from datetime import datetime

from langchain.agents import initialize_agent, AgentType
from langchain.tools import StructuredTool


from agent_types import CurrentTimeResult
from llm import LLMFactory


def get_current_time() -> CurrentTimeResult:
    return CurrentTimeResult(**{
        "current_time_format": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "current_time_unix": datetime.now().timestamp(),
        "current_weekday": datetime.now().strftime("%A"),
        "current_timezone": str(datetime.now().astimezone().tzinfo),
    })


class WeBotAgent:

    def __init__(self):
        self.llm = LLMFactory.gemini_llm()
        self.agent = initialize_agent(
            tools=[
                StructuredTool.from_function(
                    func=get_current_time,
                    name="get_current_time",
                    description="获取当前时间",
                    output_schema=CurrentTimeResult
                )
            ],
            llm=self.llm,
            agent=AgentType.OPENAI_MULTI_FUNCTIONS,
            verbose=True,
            early_stopping_method="generate",
            handle_parsing_errors=True,
            return_intermediate_steps=True
        )

    def chat(self, message):
        result = self.agent.invoke({"input": message})
        return result.get('output')


if __name__ == '__main__':
    agent = WeBotAgent()
    print(agent.chat('你好,你是谁，现在是什么时候'))
