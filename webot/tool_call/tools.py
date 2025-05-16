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
from webot.prompts.tools_prompts import ToolsPrompts


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
    if not memory_id and memory_id != 0:
        raise ValueError("memory_id 不能为空。")

    md = MemoryDatabase()
    return md.delete_memory(memory_id=memory_id)


ALL_TOOLS = [
    StructuredTool.from_function(
        name="get_current_time",
        func=get_current_time,
        description=ToolsPrompts.get_current_time_prompt()
    ),
    StructuredTool.from_function(
        name="get_contact",
        func=get_contact,
        args_schema=GetContentInput,
        description=ToolsPrompts.get_contact_prompt()
    ),
    StructuredTool.from_function(
        name="get_user_info",
        func=get_user_info,
        args_schema=GetUserInfoInput,
        description=ToolsPrompts.get_user_info_prompt()
    ),
    StructuredTool.from_function(
        name="get_message_by_wxid_and_time",
        func=get_message_by_wxid_and_time,
        args_schema=GetMessageByWxidAndTimeInput,
        description=ToolsPrompts.get_message_by_wxid_and_time_prompt()
    ),
    StructuredTool.from_function(
        name="send_text_message",
        func=send_text_message,
        args_schema=SendTextMessageInput,
        description=ToolsPrompts.send_text_message_prompt()
    ),
    StructuredTool.from_function(
        name="send_mention_message",
        func=send_mention_message,
        args_schema=SendMentionsMessageInput,
        description=ToolsPrompts.send_mention_message_prompt()
    ),
    StructuredTool.from_function(
        name="export_message",
        func=export_message,
        args_schema=GetMessageByWxidAndTimeInput,
        description=ToolsPrompts.export_message_prompt()
    ),
    StructuredTool.from_function(
        name="get_memories",
        func=get_memories,
        args_schema=GetMemoriesInput,
        description=ToolsPrompts.get_memories_prompt()
    ),
    StructuredTool.from_function(
        name="add_memory",
        func=add_memory,
        args_schema=AddMemoryInput,
        description=ToolsPrompts.add_memory_prompt()
    ),
    StructuredTool.from_function(
        name="delete_memory",
        func=delete_memory,
        args_schema=DeleteMemoryInput,
        description=ToolsPrompts.delete_memory_prompt()
    )
]
