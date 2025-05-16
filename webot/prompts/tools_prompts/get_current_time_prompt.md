获取当前的日期、时间和时区信息。此工具不接受任何参数。
主要用途：当用户查询涉及相对时间（如“昨天”、“上周”、“最近几天”）时，可调用此工具获取当前精确时间，以便计算出绝对的时间范围，供其他需要时间参数的工具（如 `get_message_by_wxid_and_time`, `export_message`, `add_memory`）使用。

### 返回参数说明 (`CurrentTimeResult`):
- `current_time_format` (str): 当前的格式化时间，格式为: "%Y-%m-%d %H:%M:%S"。例如: "2023-10-27 15:30:00"。
- `current_time_unix` (float): 当前的Unix时间戳 (自1970-01-01 00:00:00 UTC以来的秒数)。例如: 1698391800.123456。
- `current_weekday` (str): 当前是星期几 (英文全称)。例如: "Friday"。
- `current_timezone` (str): 当前系统的时区信息。例如: "Asia/Shanghai" 或 "UTC+8"。