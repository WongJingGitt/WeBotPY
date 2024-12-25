from dataclasses import dataclass
from os import environ
from typing import Literal, List, Dict, NewType

from utils.write_doc import write_doc, write_txt
from wxhook import Bot
from wxhook.model import Response

ExportFileType = NewType("ExportFileType", str)


class ExportFileTypeList:
    JSON: ExportFileType = ExportFileType("json")
    TXT: ExportFileType = ExportFileType("txt")
    YAML: ExportFileType = ExportFileType("yaml")
    YML: ExportFileType = ExportFileType("yml")
    DOCX: ExportFileType = ExportFileType("docx")


@dataclass
class Contact:
    wxid: str  # id
    custom_id: str  # 自定义的微信号
    encrypt_username: str  # 用途为止
    del_flag: str  # 看起来像是删除判定，待验证
    type: str  # 类型，猜测是用来判断联系人类型 公众号、联系人、群聊之类的
    verify_flag: str  # 验证类型？
    reserved1: str
    reserved2: str
    reserved3: str
    reserved4: str
    remark: str  # 给好友的备注
    name: str  # 好友自己取的微信名
    label_id_list: str
    domain_list: str
    chat_room_type: str
    py_initial: str
    quan_pin: str
    remark_py_initial: str
    remark_quan_pin: str
    big_head_img_url: str
    small_head_img_url: str
    head_img_md5: str
    chat_room_notify: str
    reserved5: str
    reserved6: str
    reserved7: str
    extra_buf: str
    reserved8: str
    reserved9: str
    reserved10: str
    reserved11: str

    def room(self):
        return '@chatroom' in self.wxid

    def openim(self):
        return '@openim' in self.wxid


class WeBot(Bot):

    def __init__(self, log_level="info", *args, **kwargs):
        environ['WXHOOK_LOG_LEVEL'] = log_level.upper()
        super().__init__(*args, **kwargs)

    @property
    def __get_micro_msg_handle(self):
        """
        获取MicroMsg数据库的句柄。

        :return: 返回MicroMsg数据库的句柄。
        """
        [micro_msg_database] = [item for item in self.get_db_info() if item.get('databaseName') == "MicroMsg.db"]
        return micro_msg_database.get('handle')

    @property
    def __get_msg_handle(self):
        """
        获取MSG0数据库的句柄。

        :return: 返回MSG0数据库的句柄。
        """
        [database] = [item for item in self.get_db_info() if item.get('databaseName') == 'MSG0.db']
        return database.get('handle')

    def get_db_info(self) -> List[Dict]:
        """
         调用API获取数据库信息。

         :return: 返回数据库信息的列表，列表中的每一项是一个字典，包含数据库的相关信息。
         """
        return self.call_api('/api/getDBInfo').get('data')

    def get_contacts(self) -> List[Contact]:
        """
        从本地数据库中获取所有联系人信息。

        :return: 返回包含所有联系人信息的列表，每个联系人是一个Contact对象。
        """
        micro_msg_database_handle = self.__get_micro_msg_handle
        result = self.exec_sql(micro_msg_database_handle, 'SELECT * FROM Contact')
        return [Contact(*item) for item in result.data[1:]]

    def get_contact(self, keyword: str | list, _type: Literal['wxid', 'remark', 'name'] = "wxid") -> List[Contact]:
        """
        搜索联系人，因原有的方法不会返回对联系人的备注，改写了原有的方法，并且拓展了一些功能。

        取值：从本地数据库中的表格搜寻联系人
        功能：可以一次搜索一个或者多个联系人。搜索方式可以是 微信名、备注、wxid

        :param keyword: 搜索的关键字 传值受控于_type。如果_type传 wxid 则 keyword 需要传 keyword，remark传备注名， name传微信名。
        :param _type: wxid\remark\name 三选一，默认wxid。
        :return: 一个包含搜索结果的列表，没有结果则返回空列表。
        """

        micro_msg_database_handle = self.__get_micro_msg_handle
        _mapping = {
            'wxid': "UserName",
            'remark': 'Remark',
            'name': 'NickName'
        }

        if not _mapping.get(_type):
            raise TypeError(f'_type 传递的 {_type} 不在 {", ".join(list(_mapping.keys()))} 内。')

        if not isinstance(keyword, (str, list)):
            raise TypeError(f'keyword 传递了 {type(keyword)} 不在 str, list 内。')

        in_keywords = [f'"{keyword}"'] if isinstance(keyword, str) else [f'"{item}"' for item in keyword]

        sql = f'SELECT * FROM Contact WHERE {_mapping.get(_type) or "UserName"} IN ({",".join(in_keywords)})'
        result = self.exec_sql(micro_msg_database_handle, sql)
        return [Contact(*item) for item in result.data[1:]]

    def get_message_from_db(self, talker_id: str, limit: int = 120, text_only=True) -> List[List]:
        """
        从本地数据库获取指定群聊、指定联系人的历史聊天记录

        :param talker_id: 需要获取的聊天对象，可以传wxid, room_id
        :param limit: 上限，默认120条
        :param text_only 仅获取文字消息
        :return:
        """
        handel = self.__get_msg_handle

        _type = "AND Type = \"1\"" if text_only else ""
        sql = f"SELECT * FROM MSG WHERE StrTalker = \"{talker_id}\" {_type} ORDER BY CreateTime ASC LIMIT {limit}"

        result = self.exec_sql(handel, sql)

        return result.data[1:]

    def get_concat_profile(self, wxid: str) -> Response:
        """
        获取群成员基础信息，传入wxid

        wxhelper 的作者描述是用来获取群成员的信息，但实际测试公众号与好友的wxid也可以获取到

        :param wxid: wxid
        :return: 群成员的 头像、昵称、自定义的微信账号。
        """
        response = self.call_api('/api/getContactProfile', json={"wxid": wxid})
        return Response(**response)

    def export_message_file(self, wxid, filename=None, include_image=False, start_time=None, end_time=None,
                            export_type: ExportFileType = "json", endswith_txt: bool = True):
        """
        导出聊天记录到文件
        :param wxid: 导出聊天记录的群聊或好友的wxid
        :param filename: 导出的文件名称，选填
        :param include_image: 是否包含图片，默认不包含
        :param start_time: 开始时间
        :param end_time: 结束时间
        :param export_type: 文件格式，目前支持json、yaml和docx
        :param endswith_txt: 在导出json和yaml时，是否在文件名用.txt后缀，因为大部分大预言模型不支持直接上传这两种文件
        :return: 生成文件的绝对路径
        """
        if export_type == ExportFileTypeList.DOCX:
            return write_doc(
                self.__get_msg_handle, self.__get_micro_msg_handle,
                wxid=wxid, include_image=include_image, doc_filename=filename,
                port=self.remote_port, start_time=start_time, end_time=end_time
            )

        return write_txt(
            self.__get_msg_handle, self.__get_micro_msg_handle,
            wxid=wxid, filename=filename, start_time=start_time, end_time=end_time,
            port=self.remote_port, endswith_txt=endswith_txt, file_type=export_type
        )
