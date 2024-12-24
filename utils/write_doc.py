from datetime import datetime
from base64 import b64decode
from os import path, sep, rename

from libs.message import TextMessageFromDB
from utils.msg_pb2 import MessageBytesExtra

from requests import post
from docx import Document
from docx.shared import Pt
import xmltodict

UTILS_PATH = path.dirname(path.abspath(__file__))
ROOT_PATH = path.dirname(UTILS_PATH)
DATA_PATH = path.join(ROOT_PATH, 'data')


def get_all_message(db_handle, wxid, include_image, start_time=None, end_time=None, port=19001):
    message_type = "(\"3\", \"1\")" if include_image else "(\"1\")"
    body = {
        "dbHandle": db_handle,
        "sql": f"SELECT * FROM MSG WHERE StrTalker = \"{wxid}\" AND Type in {message_type} ORDER BY CreateTime DESC",
    }
    return (post(f'http://127.0.0.1:{port}/api/execSql', json=body).json()).get('data')


def check_mention_list(bytes_extra: str):
    bytes_string = b64decode(bytes_extra)
    msg_bytes_extra = MessageBytesExtra()
    msg_bytes_extra.ParseFromString(bytes_string)
    msg_source = ''
    mention_list = []
    for item in msg_bytes_extra.message2:
        if item.field1 == 7:
            msg_source = item.field2
            break
    if not msg_source:
        return mention_list

    parse_result = xmltodict.parse(msg_source)
    msg_source = parse_result.get('msgsource', {})
    at_user_list: str = msg_source.get('atuserlist')
    if not at_user_list:
        return mention_list

    mention_list = at_user_list.split(',')
    return mention_list


def get_sender_form_room_msg(bytes_extra: str) -> str:
    bytes_string = b64decode(bytes_extra)
    msg_bytes_extra = MessageBytesExtra()
    msg_bytes_extra.ParseFromString(bytes_string)
    for item in msg_bytes_extra.message2:
        if item.field1 == 1:
            return item.field2
    return ""


def decode_img(message: TextMessageFromDB, save_dir, port=19001) -> str:
    if message.Type != '3':
        return ""

    DATA_PATH = post(f'http://127.0.0.1:{port}/api/userInfo').json().get('data').get('dataSavePath')

    message_id = message.MsgSvrID

    post(f'http://127.0.0.1:{port}/api/downloadAttach', json={"msgId": message_id})

    bs64 = message.BytesExtra
    text = b64decode(bs64)

    msg_bytes_extra = MessageBytesExtra()
    msg_bytes_extra.ParseFromString(text)

    image_path = r""

    for item in msg_bytes_extra.message2:
        if item.field1 == 4:
            image_path = item.field2
            break

    dir_path, filename = path.split(image_path)
    image_path = path.join(sep.join(dir_path.split(sep)[1:]), filename)

    body = {
        'filePath': path.join(DATA_PATH, image_path),
        'storeDir': save_dir
    }
    resp = post(f'http://127.0.0.1:{port}/api/decodeImage', json=body)

    if resp.json().get('code') == 0:
        return ""

    result_file_path = path.join(save_dir, filename.replace('.dat', '.jpg'))
    if path.exists(result_file_path):
        return result_file_path

    dat_result_path = result_file_path.replace('.jpg', '.dat')
    if path.exists(dat_result_path):
        rename(dat_result_path, result_file_path)
        return result_file_path
    return ""


def get_talker_name(db_handle, wxid, port=19001) -> tuple[str, str]:
    """
    从数据库获取微信用户的微信名
    :param db_handle: MicroMsg.db数据库句柄
    :param wxid: 微信id
    :param port: 端口号
    :return: tuple[备注, 微信名]
    """
    body = {
        "dbHandle": db_handle,
        "sql": f"SELECT Remark,NickName From Contact Where UserName = \"{wxid}\""
    }
    resp = post(f'http://127.0.0.1:{port}/api/execSql', json=body).json()
    if resp.get('code') != 1:
        return '', ''

    result = resp.get('data')
    if len(result) < 2:
        return '', ''

    remark, nick_name = result[-1]
    return remark, nick_name


def write_doc(msg_db_handle, micro_msg_db_handle, wxid, doc_filename=None, include_image=False,
              port=19001):
    data = get_all_message(msg_db_handle, wxid, include_image, port=port)
    doc = Document()

    main_remark, main_username = get_talker_name(micro_msg_db_handle, wxid, port=port)
    doc_filename = f"{main_username}_{main_remark}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.docx"if not \
        doc_filename else doc_filename

    for index, item in enumerate(data):
        if index == 0:
            continue

        message = TextMessageFromDB(*item)

        # 获取发送人名称
        image_path = ""
        sender_id = get_sender_form_room_msg(message.BytesExtra) if message.room else message.StrTalker
        remark, nick_name = get_talker_name(micro_msg_db_handle, sender_id, port)
        sender = f"{nick_name}({remark})" if remark else nick_name

        room = message.room
        mention_list = ""

        if room:
            # 获取提及人名称
            mention_list = check_mention_list(message.BytesExtra)
            mention_list = [get_talker_name(micro_msg_db_handle, user_id, port) for user_id in mention_list if user_id]
            mention_list = [f"{_nick_name}({_remark})" if _remark else _nick_name for _remark, _nick_name in
                            mention_list]
            mention_list = ' || '.join(mention_list)

        if message.Type == '3':
            image_path = decode_img(message, path.join(DATA_PATH, 'images'), port=port)

        temp = {
            "role": "other" if message.IsSender == "0" else "me",
            "content": message.StrContent if message.Type == '1' else image_path,
            "time": datetime.fromtimestamp(int(message.CreateTime)).strftime('%Y-%m-%d %H:%M:%S'),
            "type": "text" if message.Type == "1" else "image"
        }

        if temp['type'] == "image" and temp['content'] == '':
            continue

        doc.add_paragraph("=== 消息开始 ===")
        doc.add_paragraph(f'发送人：{"我" if temp["role"] == "me" else sender}')
        if room: doc.add_paragraph(f'提及人：{mention_list}')
        doc.add_paragraph(f'时间：{temp["time"]}')

        if temp["type"] == "text":
            doc.add_paragraph(f'内容：\n{temp["content"]}')
            doc.add_paragraph("=== 消息结束 ===")
            continue

        if temp["type"] == "image" and path.exists(image_path):
            doc.add_paragraph(f'内容：')
            try:
                doc.add_picture(image_path, width=Pt(300))
            except Exception as e:
                print(e)
                doc.add_paragraph(f'图片添加失败')
        else:
            doc.add_paragraph(f'内容：\n图片获取失败')

        doc.add_paragraph("=== 消息结束 ===")

    file_name = path.join(DATA_PATH, 'exports', doc_filename)
    doc.save(file_name)

    return file_name


