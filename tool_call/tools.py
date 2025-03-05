import re
from datetime import datetime
from typing import List, Dict, Any

from langchain_core.tools import StructuredTool
from requests import post

from bot.write_doc import write_txt
from tool_call.tools_types import CurrentTimeResult, GetContentInput, ContentResult, UserInfoResult, GetUserInfoInput, \
    GetMessageByWxidAndTimeInput, SendTextMessageInput


def get_current_time() -> CurrentTimeResult:
    now = datetime.now()
    return CurrentTimeResult(**{
        "current_time_format": now.strftime("%Y-%m-%d %H:%M:%S"),
        "current_time_unix": now.timestamp(),
        "current_weekday": now.strftime("%A"),
        "current_timezone": str(now.astimezone().tzinfo),
    })


def get_db_info(port: int) -> List[Dict[str, Any]]:
    return post(f'http://127.0.0.1:{port}/api/getDBInfo').json().get('data')


def get_micro_msg_handle(port: int):
    [micro_msg_database] = [item for item in get_db_info(port) if item.get('databaseName') == "MicroMsg.db"]
    return micro_msg_database.get('handle')


def get_msg_handle(port: int):
    return [item.get('handle') for item in get_db_info(port) if re.match(r'^MSG\d+\.db$', item.get('databaseName'))]


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
    return [ContentResult(wxid=item[0], remark=item[10], name=item[11], avatar=item[-1]) for item in result[1:]]


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
    return write_txt(
        msg_db_handle=get_msg_handle(port),
        micro_msg_db_handle=get_micro_msg_handle(port),
        wxid=wxid,
        port=port,
        start_time=start_time,
        end_time=end_time,
        endswith_txt=True,
        file_type='json'
    )


def send_text_message(port, wxid, message):
    port = int(port)
    return post(
        f"http://127.0.0.1:{port}/api/sendTextMsg",
        json={
            "wxid": wxid,
            "msg": message
        }
    ).json()


ALL_TOOLS = [
    StructuredTool.from_function(
        name="get_current_time",
        func=get_current_time,
        description="""
一个用作获取当前时间的工具函数，可以用作推断用户想要的时间。例如：用户表示最近x天、最近x个月。返回字段：
    - `current_time_format`: 当前的格式化时间，格式为: %Y-%m-%d %H:%M:%S
    - `current_time_unix`: 使用`datetime.now().timestamp()`获取的当前Unix时间戳
    - `current_weekday`: 使用`datetime.now().strftime("%A")`获取的当前星期几
    - `current_timezone`: 使用`datetime.now().astimezone().tzinfo`获取的当前时区信息
"""
    ),
    StructuredTool.from_function(
        name="get_contact",
        func=get_contact,
        args_schema=GetContentInput,
        description="""
一个用作从获取微信联系人的工具函数，通过提供的关键字，获取包含该关键字的所有联系人。返回一个包含一个或者多个字典的列表，具体字段说明：
    - `wxid`：联系人的wxid，例如："wxid_abcdefg123456"。
    - `remark`：用户对当前联系人的备注名，例如："阿祖"。
    - `name`：这个联系人的微信名，例如："吴彦祖"。
    - `avatar`：这个联系人的微信头像，一个网址。
"""
    ),
    StructuredTool.from_function(
        name="get_user_info",
        func=get_user_info,
        args_schema=GetUserInfoInput,
        description="""
一个用作获取当前微信登录用户信息的工具函数，返回一个`UserInfoResult`，具体字段说明：
    - `wxid`： 当前用户的wxid，例如："wxid_abcdefg123456"。
    - `avatar`：当前用户的头像地址，例如："https://wx.qlogo.cn/mmhead/ver_1/abcdefg1234567890/132"。
    - `name`：当前用户的微信名，例如："吴彦祖"。
    - `province`：当前用户的省份，例如："ZheJiang"。
    - `city`：当前用户的城市，例如："HangZhou"。
    - `country`：当前用户的国家，例如："CN"。
    - `signature`：当前用户的个性签名，例如："Hello World!"
    - `mobile`：当前用户的手机号，例如：13800000000
"""
    ),
    StructuredTool.from_function(
        name="get_message_by_wxid_and_time",
        func=get_message_by_wxid_and_time,
        args_schema=GetMessageByWxidAndTimeInput,
        description="""
一个用作获取聊天记录的工具函数，传入wxid与时间范围，返回一个聊天记录字典，具体字段说明：
    - `meta`：聊天记录的数据结构定义
    - `data`：聊天记录的具体数据，是一个列表，列表中的每个元素是一个字典，包含以下字段：
        - `sender`：这条消息发送者的微信名。
        - `remark`：用户对消息发送人的备注，如果为空则代表该联系人没有备注。
        - `content`：具体的消息内容
        - `time`：消息发送时间
        - `mentioned`：只有群聊的聊天记录才会有的字段，代表消息中提及到的用户，如果为空则代表这条消息没有提及任何人。
        - `wxid`：这条消息发送人的wxid，可以通过wxid判断消息是否是同一人发送。
"""
    ),
    StructuredTool.from_function(
        name="send_text_message",
        func=send_text_message,
        args_schema=SendTextMessageInput,
        description="""
一个用作发送文本消息的工具函数，返回一个字典，具体字段说明：
    - `code`: 返回状态,不为0代表发送成功, 0代表发送失败
    - `result`: 成功提示
"""
    ),
    StructuredTool.from_function(
        name="export_message",
        func=export_message,
        args_schema=GetMessageByWxidAndTimeInput,
        description="""
一个用作导出聊天记录文件的工具函数，传入wxid与时间范围，将聊天记录导出为txt文件保存在本地，并且返回文件的绝对路径
"""
    )
]

