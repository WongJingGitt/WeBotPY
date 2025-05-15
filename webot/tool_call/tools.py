import re
from datetime import datetime
from typing import List, Dict, Any
from os import path

from langchain_core.tools import StructuredTool
from requests import post

from webot.bot.write_doc import write_txt, get_memory
from webot.tool_call.tools_types import CurrentTimeResult, GetContentInput, ContentResult, UserInfoResult, \
    GetUserInfoInput, \
    GetMessageByWxidAndTimeInput, SendTextMessageInput, GetMemoriesInput, GetMemoriesResult, AddMemoryInput, \
    SendMentionsMessageInput, DeleteMemoryInput
from webot.databases.global_config_database import MemoryDatabase


def get_db_info(port: int) -> List[Dict[str, Any]]:
    return post(f'http://127.0.0.1:{port}/api/getDBInfo').json().get('data')


def get_micro_msg_handle(port: int):
    [micro_msg_database] = [item for item in get_db_info(port) if item.get('databaseName') == "MicroMsg.db"]
    return micro_msg_database.get('handle')


def get_msg_handle(port: int) -> List:
    return [item.get('handle') for item in get_db_info(port) if re.match(r'^MSG\d+\.db$', item.get('databaseName'))]


# ========== 分割线 ==========
# 上部分放依赖函数，下部分放导出的工具函数

def get_current_time() -> CurrentTimeResult:
    now = datetime.now()
    return CurrentTimeResult(**{
        "current_time_format": now.strftime("%Y-%m-%d %H:%M:%S"),
        "current_time_unix": now.timestamp(),
        "current_weekday": now.strftime("%A"),
        "current_timezone": str(now.astimezone().tzinfo),
    })


def get_contact(port, keyword) -> List[ContentResult]:
    """
    根据关键字搜索联系人，并返回一个包含搜索结果的列表。

    :param keyword: 搜索的关键字，可以是微信名或者备注。
    :param port: 当前微信的Port，格式为int，整数。
    :return: 一个包含搜索结果的列表，没有结果则返回空列表。
    """
    port = int(port)
    micro_msg_database_handle = get_micro_msg_handle(port)

    if not isinstance(keyword, (str, list)):
        raise TypeError(f'keyword 传递了 {type(keyword)} 不在 str, list 内。')

    sql = f"""
    SELECT Contact.*, ContactHeadImgUrl.bigHeadImgUrl
    FROM Contact
    LEFT JOIN ContactHeadImgUrl
    ON Contact.UserName = ContactHeadImgUrl.usrName
    WHERE Remark LIKE "%{keyword}%" OR NickName LIKE "%{keyword}%"
    """
    result = post(
        f"http://127.0.0.1:{port}/api/execSql",
        json={
            "sql": sql,
            "dbHandle": micro_msg_database_handle
        }
    ).json().get('data')
    return [ContentResult(wxid=item[0], remark=item[10], name=item[11], avatar=item[-1], alias_id=item[1]) for item in result[1:]]


def get_user_info(port) -> UserInfoResult:
    port = int(port)
    result = post(f'http://127.0.0.1:{port}/api/userInfo').json().get('data')
    return UserInfoResult(
        avatar=result.get('headImage'),
        city=result.get('city'),
        country=result.get('country'),
        mobile=result.get('mobile'),
        name=result.get('name'),
        province=result.get('province'),
        signature=result.get('signature'),
        wxid=result.get('wxid')
    )


def get_message_by_wxid_and_time(wxid, port, start_time, end_time):
    port = int(port)
    return write_txt(
        msg_db_handle=get_msg_handle(port),
        micro_msg_db_handle=get_micro_msg_handle(port),
        wxid=wxid,
        port=port,
        start_time=start_time,
        end_time=end_time,
        endswith_txt=True,
        file_type=None
    )


def export_message(wxid, port, start_time, end_time):
    port = int(port)
    file_path = write_txt(
        msg_db_handle=get_msg_handle(port),
        micro_msg_db_handle=get_micro_msg_handle(port),
        wxid=wxid,
        port=port,
        start_time=start_time,
        end_time=end_time,
        endswith_txt=True,
        file_type='json'
    )
    filename = path.basename(file_path)
    return {
        "file_path": file_path,
        "filename": filename,
        "download_link": f"/api/bot/download_export_file/{filename}"
    }


def send_text_message(port, wxid, message):
    port = int(port)
    return post(
        f"http://127.0.0.1:{port}/api/sendTextMsg",
        json={
            "wxid": wxid,
            "msg": message
        }
    ).json()


def send_mention_message(port, room_wxid, message, at_users_wxid: List[str] = []):
    port = int(port)
    if at_users_wxid is None:
        raise ValueError("at_users_wxid 不能为空。")
    if not isinstance(at_users_wxid, list):
        raise TypeError("at_users_wxid 必须为 list 类型。")
    if not all(isinstance(item, str) for item in at_users_wxid):
        raise TypeError("at_users_wxid 的元素必须为 str 类型。")
    if len(at_users_wxid) == 0:
        raise ValueError("at_users_wxid 不能为空。")
    at_users_wxid = ','.join(at_users_wxid)
    return post(
        f"http://127.0.0.1:{port}/api/sendAtText",
        json={
            "chatRoomId": room_wxid,
            "msg": message,
            "wxids": at_users_wxid
        }
    ).json()


def get_memories(wxid: str, port: int) -> List[GetMemoriesResult]:
    user_info = get_user_info(port=port)
    from_user = user_info.wxid
    return get_memory(from_user=from_user, to_user=wxid)


def add_memory(wxid: str, port: int, content: str, type: str, event_time: str):
    user_info = get_user_info(port=port)
    md = MemoryDatabase()
    return md.add_memory(
        from_user=user_info.wxid,
        to_user=wxid,
        content=content,
        type=type,
        event_time=event_time
    )


def delete_memory(memory_id: int) -> bool:
    md = MemoryDatabase()
    return md.delete_memory(memory_id=memory_id)


ALL_TOOLS = [
    StructuredTool.from_function(
        name="get_current_time",
        func=get_current_time,
        description="""
获取当前的日期、时间和时区信息。此工具不接受任何参数。
主要用途：当用户查询涉及相对时间（如“昨天”、“上周”、“最近几天”）时，可调用此工具获取当前精确时间，以便计算出绝对的时间范围，供其他需要时间参数的工具（如 `get_message_by_wxid_and_time`, `export_message`, `add_memory`）使用。

### 返回参数说明 (`CurrentTimeResult`):
    - `current_time_format` (str): 当前的格式化时间，格式为: "%Y-%m-%d %H:%M:%S"。例如: "2023-10-27 15:30:00"。
    - `current_time_unix` (float): 当前的Unix时间戳 (自1970-01-01 00:00:00 UTC以来的秒数)。例如: 1698391800.123456。
    - `current_weekday` (str): 当前是星期几 (英文全称)。例如: "Friday"。
    - `current_timezone` (str): 当前系统的时区信息。例如: "Asia/Shanghai" 或 "UTC+8"。
"""
    ),
    StructuredTool.from_function(
        name="get_contact",
        func=get_contact,
        args_schema=GetContentInput,
        description="""
根据关键字搜索微信联系人或群聊。

### 参数说明:
    - `port` (int): 运行目标微信实例的端口号。
    - `keyword` (str): 用于搜索的关键字。会匹配联系人的备注名（Remark）或微信昵称（NickName）。

### 返回参数说明:
返回一个列表 (`List[ContentResult]`)，其中每个元素是一个字典，代表一个匹配的联系人或群聊。如果未找到匹配项，则返回空列表 `[]`。
每个字典包含以下字段：
    - `wxid` (str): 联系人或群聊的唯一ID (wxid)。个人wxid通常格式如 "wxid_abcdefg123456"，群聊wxid以 "@chatroom" 结尾，例如 "123456789@chatroom"。
    - `remark` (str): 你为该联系人设置的备注名。如果是群聊或没有设置备注，可能为空或为群聊名称。
    - `name` (str): 该联系人的微信昵称或群聊的名称。
    - `avatar` (str): 联系人或群聊的头像图片URL地址。
    - `alias_id` (str): 联系人对外展示的微信号，由联系人自定义。
"""
    ),
    StructuredTool.from_function(
        name="get_user_info",
        func=get_user_info,
        args_schema=GetUserInfoInput,
        description="""
获取当前通过指定端口登录的微信账号的用户信息。

### 参数说明:
    - `port` (int): 运行当前微信实例的端口号。

### 返回参数说明 (`UserInfoResult`):
返回一个包含当前登录用户详细信息的字典：
    - `wxid` (str): 当前登录用户的wxid。
    - `name` (str): 当前用户的微信昵称。
    - `avatar` (str): 当前用户的头像图片URL地址。
    - `mobile` (str): 当前用户绑定的手机号 (可能为空或部分隐藏)。
    - `signature` (str): 当前用户的个性签名。
    - `country` (str): 用户设置的国家。
    - `province` (str): 用户设置的省份。
    - `city` (str): 用户设置的城市。
"""
    ),
    StructuredTool.from_function(
        name="get_message_by_wxid_and_time",
        func=get_message_by_wxid_and_time,
        args_schema=GetMessageByWxidAndTimeInput,
        description="""
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
"""
    ),
    StructuredTool.from_function(
        name="send_text_message",
        func=send_text_message,
        args_schema=SendTextMessageInput,
        description="""
向指定的用户或群聊发送纯文本消息。

### 前置步骤:
1.  需要先通过 `get_contact` 获取目标用户或群聊的准确 `wxid`。

### 使用示例：

> 假设在端口为19001的微信中，想在群聊“机器人交流群”发送一条“今早出门好热啊！大家还好吗？”
1. 通过`get_contact`获取到了相关群聊的id：
    - **机器人交流群**：123456789@chatroom
2. 调用本工具函数(`send_text_message`)。
```python
send_text_message(
    port=19001,
    wxid="123456789@chatroom",
    message="今早出门好热啊！大家还好吗？"
)
```

> 假设在端口为19001的微信中，想对“迪丽热巴”说，“今晚我不回去吃饭了”
1. 通过`get_contact`获取到了“迪丽热巴”的id：
    - **迪丽热巴**：wxid_123456
2. 调用本工具函数(`send_text_message`)。
```python
send_text_message(
    port=19001,
    wxid="wxid_123456",
    message="今晚我不回去吃饭了"
)
```

### 参数说明:
    - `port` (int): 运行目标微信实例的端口号。
    - `wxid` (str): 消息接收方（用户或群聊）的wxid。
    - `message` (str): 要发送的纯文本消息内容。

### 返回参数说明：
返回调用API后的原始JSON响应，通常为一个字典，包含以下关键字段：
    - `code`: 返回状态码。**注意：根据底层库约定，`0` 代表发送失败，非 `0` (通常是正整数) 代表发送成功。**
    - `msg`: 描述信息，例如 "success" 或错误提示。
"""
    ),
    StructuredTool.from_function(
        name="send_mention_message",
        func=send_mention_message,
        args_schema=SendMentionsMessageInput,
        description="""
在指定的群聊中发送带有@提及成员的文本消息。

### 前置步骤:
1.  需要先通过 `get_contact` 获取目标群聊的 `room_wxid`。
2.  如果需要@特定成员（而不是@所有人），需要先通过 `get_contact` 获取这些成员的 `wxid`。

### 使用示例：

> 提醒“吴彦祖”和“谢霆锋”明天带伞。
1. 获取ID:
    - **机器人交流群**: 123456789@chatroom
    - **吴彦祖**: wxid_1234
    - **谢霆锋**: wxid_5678
2. 调用:
```python
send_mention_message(
    port=19001,
    room_wxid="123456789@chatroom",
    message="明天会下雨，二位记得出门时携带雨伞哦！",
    at_users_wxid=["wxid_1234", "wxid_5678"]
)
```
3. 效果: @吴彦祖 @谢霆锋 明天会下雨，二位记得出门时携带雨伞哦！

> 提醒“所有人”明天带伞。
1. 获取群ID:
    - **机器人交流群**: 123456789@chatroom
2. 调用 (@所有人使用固定wxid: "notify@all"):
```python
send_mention_message(
    port=19001,
    room_wxid="123456789@chatroom",
    message="明天会下雨，大家记得出门时携带雨伞哦！",
    at_users_wxid=["notify@all"]
)
```
3. 效果: @所有人 明天会下雨，大家记得出门时携带雨伞哦！

### 参数说明:
    - `port` (int): 运行目标微信实例的端口号。
    - `room_wxid` (str): 目标群聊的wxid (必须以 "@chatroom" 结尾)。
    - `message` (str): 要发送的消息文本内容。
    - `at_users_wxid` (List[str]): 需要@提及的用户的wxid列表。若要@所有人，请传入 `["notify@all"]`。此列表不能为空。

### 返回参数说明：
返回调用API后的原始JSON响应，通常为一个字典，包含以下关键字段：
    - `code`: 返回状态码。通常，大于`0`的值代表成功, `-1` 代表失败。
    - `msg`: 描述信息，例如 "success" 或错误提示。
"""
    ),
    StructuredTool.from_function(
        name="export_message",
        func=export_message,
        args_schema=GetMessageByWxidAndTimeInput,
        description="""
将指定用户或群聊在特定时间范围内的聊天记录导出为本地文件。

**重要使用约束：仅当用户明确表示需要 “导出” 、“下载”、“保存到文件”、“提取聊天记录”等意图时，才应调用此工具。**

### 前置步骤:
1.  通常需要先调用 `get_contact` 确认目标用户或群聊的准确 `wxid`。
2.  如果用户提供了相对时间（如“昨天”，“最近一周”），需要先调用 `get_current_time` 获取当前时间，并计算出精确的 `start_time` 和 `end_time`。

### 参数说明:
    - `port` (int): 运行目标微信实例的端口号。
    - `wxid` (str): 要导出聊天记录的目标用户或群聊的wxid。
    - `start_time` (str): 聊天记录的开始时间，必须严格使用 "YYYY-MM-DD HH:MM:SS" 格式。
    - `end_time` (str): 聊天记录的结束时间，必须严格使用 "YYYY-MM-DD HH:MM:SS" 格式。

### 返回参数说明:
    - file_path(str): 本地 **.txt 文件的绝对路径**。该 TXT 文件内部包含的是 **JSON 格式** 的聊天记录数据。如果导出失败，可能返回错误信息或空字符串（具体取决于 `write_txt` 的实现）。
    - filename: 导出的具体文件明
    - download_link: 下载链接，需要以 `[filename](download_link)` 形式展示出下载入口提供给用户快捷下载。
"""
    ),
    StructuredTool.from_function(
        name="get_memories",
        func=get_memories,
        args_schema=GetMemoriesInput,
        description="""
获取与指定联系人或群聊 (`wxid`) 相关的所有已存储记忆。这些记忆是由当前登录用户视角记录的关于目标 `wxid` 的信息。
主要用于帮助AI理解与特定对象的历史交互、关键信息或背景，例如在总结聊天记录或进行个性化回应时。

### 前置步骤:
1.  需要先调用 `get_contact` 获取目标用户或群聊的准确 `wxid`。

### 参数说明:
    - `port` (int): 运行当前微信实例的端口号 (用于识别是哪个用户在查询)。
    - `wxid` (str): 你想查询相关记忆的目标用户或群聊的wxid。

### 返回参数说明 (`List[GetMemoriesResult]`):
返回一个列表，包含所有与目标 `wxid` 相关的记忆。每个记忆是一个字典，包含：
    - `content` (str): 记忆的具体内容文本。
    - `type` (str): 记忆的类型。推荐使用的类型包括：'event' (事件), 'topic' (主题), 'social_network' (社交关系), 'nickname' (昵称/称呼), 'keyword' (关键词), 'summary' (摘要)。
    - `event_time` (str | None): 与该记忆相关的事件发生时间，格式为 "YYYY-MM-DD HH:MM:SS"。如果记忆与特定时间点无关，则可能为 `None`。
    - `wxid` (str): 这条记忆所关联的主体对象的wxid (即输入的 `wxid` 参数)。
"""
    ),
    StructuredTool.from_function(
        name="add_memory",
        func=add_memory,
        args_schema=AddMemoryInput,
        description=""""
为指定的联系人或群聊 (`wxid`) 添加一条新的记忆。记忆是从当前登录用户的视角记录的。

### 前置步骤:
1.  需要先调用 `get_contact` 获取目标用户或群聊的准确 `wxid`。
2.  如果记忆内容涉及特定时间点，且用户提供了相对时间（如“昨天发生的”），可能需要先调用 `get_current_time` 计算出精确的 `event_time`。

### 参数说明:
    - `port` (int): 运行当前微信实例的端口号 (用于识别是哪个用户在添加记忆)。
    - `wxid` (str): 你要为其添加记忆的目标用户或群聊的wxid。
    - `content` (str): 要记录的记忆内容文本。
    - `type` (str): 记忆的类型。**强烈建议** 从以下列表中选择一个：'event','topic', 'social_network', 'nickname', 'keyword', 'summary'。虽然代码层面未做强制校验，但使用这些标准类型有助于后续查询和管理。
    - `event_time` (str | None): 与该记忆相关的事件发生时间，格式应为 "YYYY-MM-DD HH:MM:SS"。如果用户没有提及具体时间，或者记忆与时间无关，请将此参数设置为 `None`。

### 返回参数说明:
    - (int): 成功添加记忆后，返回该条记忆在数据库中的唯一行ID (last row id)。这是一个整数。如果添加失败，行为可能取决于数据库操作，可能抛出异常或返回一个非正整数值（需要根据实际测试确定失败情况下的返回值）。
"""
    ),
    StructuredTool.from_function(
        name="delete_memory",
        func=delete_memory,
        args_schema=DeleteMemoryInput,
        description="""
用作删除一条记忆，接收一个`memory_id`作为参数，运行后会删除该`memory_id`的记忆。

## 使用须知：
- 由于用户无法直接感知到`memory_id`，通常会用自然语言描述删除的记忆。需要先通过`get_memories`函数获取所有记忆，推断出需要删除的是哪一条。
- 函数会返回一个布尔值，`True`代表删除成功，`False`代表删除失败。

## 示例：
- 用户输入：帮我删除关于迪丽热巴不喜欢我的记忆。
- 你的操作流程：
    1. 调用`get_contact`函数，传递关键字`迪丽热巴`，查询出`迪丽热巴`的wxid。
    2. 调用`get_memories`，传递`迪丽热巴`的wxid，获取所有关于`迪丽热巴`的记忆。
    3. 根据所有关于`迪丽热巴`的记忆，推断出符合用户描述的记忆。
        * 匹配到多条结果，例如：`迪丽热巴`分别在5月2日和3月18日说了两次不喜欢我。主动询问用户需要删除哪一条。
        * 匹配到单条结果，例如：`迪丽热巴`仅在4月6日说了不喜欢我。将匹配到的记忆发送给用户，二次确认是否删除。
    4. 根据用户的答复，调用`delete_memory`(本函数)删除用户确认的记忆。
    5. 根据`delete_memory`的返回值，告知用户是否删除成功。
        """
    )
]
