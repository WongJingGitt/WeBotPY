from datetime import datetime

from libs.contact import Contact
from dataclasses import dataclass, field
from requests import post


def contact_captor(keywords: str, micro_msg_db_handle: str, port: int, fuzzy: bool = False) -> dict[str, str|dict]:
    """
    联系人捕获器，用于根据提供的条件捕获联系人。

    :param keywords: 在联系人的备注或昵称中搜索的关键词。
    :param micro_msg_db_handle: 联系人数据库的句柄。
    :param port: 机器人API服务器的端口号。
    :param fuzzy: 如果为 True，则使用 LIKE 进行模糊搜索。默认为 False。
    :return: ContactCaptorResult: 联系人捕获结果。
    """
    match = f"Remark = \"{keywords}\" OR NickName = \"{keywords}\"" if not fuzzy else f"Remark LIKE \"%{keywords}%\" OR NickName LIKE \"%{keywords}%\""

    body = {
        "dbHandle": micro_msg_db_handle,
        "sql": f"""
            SELECT Contact.*, ContactHeadImgUrl.bigHeadImgUrl
            FROM Contact
            LEFT JOIN ContactHeadImgUrl
            ON Contact.UserName = ContactHeadImgUrl.usrName
            WHERE {match}
            """
    }
    response = post(f'http://127.0.0.1:{port}/api/execSql', json=body).json()
    contact = response.get('data')

    if not contact:
        return {
            "type": "none",
            "data": []
        }

    if len(contact) > 2:
        return {
            "type": "multi",
            "data": [Contact(*item).data for index, item in enumerate(contact) if index > 0]
        }

    contact = Contact(*contact[1])
    return {
        "type": "single",
        "data": [contact.data]
    }



