from pydantic import BaseModel, Field


class CurrentTimeResult(BaseModel):
    current_time_format: str = Field(..., description="当前时间的格式化字符串，例如：\"2023-07-01 12:34:56\"。")
    current_time_unix: int | float = Field(..., description="当前时间的Unix时间戳，精确到秒。")
    current_weekday: str = Field(..., description="当前星期几，例如：\"Monday\"。")
    current_timezone: str = Field(..., description="当前时区，例如：\"中国标准时间\"。")



