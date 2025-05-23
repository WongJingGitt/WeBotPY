根据指定的wxid（用户或群聊）和时间范围，获取聊天记录。

### 前置步骤:

1.  通常需要先调用 `get_contact` 确认目标用户或群聊的准确 `wxid`。
2.  如果用户提供了相对时间（如“昨天”，“最近一周”），需要先调用 `get_current_time` 获取当前时间，并计算出精确的 `start_time` 和 `end_time`。

### 参数说明:

- `port` (int): 运行目标微信实例的端口号。
- `wxid` (str): 要获取聊天记录的目标用户或群聊的wxid。
- `start_time` (str): 聊天记录的开始时间，必须严格使用 "YYYY-MM-DD HH:MM:SS" 格式。
- `end_time` (str): 聊天记录的结束时间，必须严格使用 "YYYY-MM-DD HH:MM:SS" 格式。

### 返回参数说明:

返回一个包含聊天记录的字典。**注意：具体返回结构依赖于底层 `write_txt` 函数的实现，以下为基于原描述的推测结构:**

- `meta` (dict): 可能包含数据结构的元信息或定义。
- `data` (List[dict]): 一个列表，包含了时间范围内的聊天消息。列表中的每个元素是一个字典，代表一条消息：
- `sender` (str): 消息发送者的微信昵称。
- `remark` (str): 你为消息发送者设置的备注名 (如果对方是联系人且有备注)。
- `content` (str): 消息的具体文本内容。
- `time` (str): 消息发送的时间戳或格式化时间字符串。
- `mentioned` (List[str] | None): (仅群聊记录) 此消息中@提及的用户的微信昵称列表。如果没有提及，则为 `None` 或空列表。
- `wxid` (str): 消息发送者的wxid。可用于判断消息是否来自同一个人。