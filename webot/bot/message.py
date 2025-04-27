from dataclasses import dataclass, field
from typing import NewType, Optional, Any
from base64 import b64decode
from re import sub

from wxhook.model import Event, Response

MessageTypes = NewType('MessageTypes', str)


class MessageType:
    """
    定义各种消息类型的常量。
    """

    #: 通知消息事件
    NOTICE_MESSAGE = MessageTypes("10000")

    #: 系统消息事件
    SYSTEM_MESSAGE = MessageTypes("10002")

    #: 全部消息事件
    ALL_MESSAGE = MessageTypes("99999")

    #: 文本消息事件
    TEXT_MESSAGE = MessageTypes("1")

    #: 图片消息事件
    IMAGE_MESSAGE = MessageTypes("3")

    #: 语音消息事件
    VOICE_MESSAGE = MessageTypes("34")

    #: 好友验证请求消息事件
    FRIEND_VERIFY_MESSAGE = MessageTypes("37")

    #: 卡片消息事件
    CARD_MESSAGE = MessageTypes("42")

    #: 视频消息事件
    VIDEO_MESSAGE = MessageTypes("43")

    #: 表情消息事件
    EMOJI_MESSAGE = MessageTypes("47")

    #: 位置消息事件
    LOCATION_MESSAGE = MessageTypes("48")

    #: XML消息事件
    XML_MESSAGE = MessageTypes("49")

    #: 视频/语音通话消息事件
    VOIP_MESSAGE = MessageTypes("50")

    #: 手机端同步消息事件
    PHONE_MESSAGE = MessageTypes("51")


@dataclass
class Message(Event):
    bot: Any = field(default=None)
    bytes_trans: str = field(default=None)

    @property
    def room(self) -> bool:
        return '@chatroom' in self.fromUser


@dataclass
class MessageDetail:
    #: 消息发送人
    from_user: str

    #: 消息接收人，私聊将返回自己的ID，群聊将返回@的用户ID，若消息没有@用户将返回空列表
    to_user: list

    #: 群聊id
    room: str

    message_id: int


@dataclass
class TextMessageDetail(MessageDetail):
    """
    微信消息文本详情
    """

    #: 原始的消息内容
    content: str


@dataclass
class TextMessage(Message):

    @property
    def text_content(self) -> str:
        """
        返回纯文本消息，去除群聊消息中的额外信息
        :return: str
        """
        if not self.room:
            return self.content

        wxid, content = self.content.split(':\n', 1) or ("", "")
        return content

    @property
    def message_detail(self) -> TextMessageDetail:
        """
        消息详情，包含发送人、接收人、消息内容，群聊ID(如果是来自群聊)。
        :return: TextMessageDetail
        """
        if not self.room:
            return TextMessageDetail(from_user=self.fromUser, content=self.content, room='', to_user=[self.toUser],
                                     message_id=self.msgId)

        wxid, content = self.content.split(':\n', 1) or ("", "")
        signature = self.signature if isinstance(self.signature, dict) else {}
        msg_sources = signature.get('msgsource', {})
        origin_at_user_list = msg_sources.get('atuserlist', '')
        at_user_list = origin_at_user_list.split(',') if origin_at_user_list != "" else []

        return TextMessageDetail(from_user=wxid, content=content, room=self.fromUser, to_user=at_user_list,
                                 message_id=self.msgId)

    @property
    def mention_me(self) -> bool:
        """
        检查消息是否@我，返回True或者False. 如果消息为私聊时会固定返回True
        :return: bool
        """
        self_id = self.bot.info.wxid
        return self_id in self.message_detail.to_user

    def reply_text(self, message: str, mention_list: Optional[list] = None) -> Response:
        """
        快捷回复文本消息，直接回复至发送方

        :param message: 需要发送的消息内容
        :param mention_list: @的人的列表，如果为空，则不@任何人，只有再回复群聊时才会生效。
        :return:
        """
        if not self.room:
            return self.bot.send_text(wxid=self.fromUser, msg=message)

        if not mention_list:
            return self.bot.send_text(wxid=self.fromUser, msg=message)

        if not isinstance(mention_list, list):
            raise TypeError(f"mention_list must be list, but got {type(mention_list)}")

        return self.bot.send_room_at(room_id=self.fromUser, msg=message, wxids=mention_list)

    def reply_room_pat(self, wxid: str = None) -> Response:
        """
        快捷回复拍一拍，仅在群聊下生效。
        :param wxid: 需要拍的用户，不传递则直接拍该条消息的发送用户。
        :return:
        """
        if not self.room:
            return Response(code=0, data={}, msg="不是群聊")
        message_detail = self.message_detail
        wxid = wxid if wxid is not None else message_detail.from_user
        return self.bot.send_pat(message_detail.room, wxid)

    def reply_image(self, image_path) -> Response:
        """
        回复图片消息。
        :param image_path: 图片路径
        :return:
        """
        return self.bot.send_image(self.fromUser, image_path)


@dataclass
class TextMessageFromDB:
    localId: str
    TalkerId: str
    MsgSvrID: str
    Type: str   # 消息类型，1 = 文字消息， 3 = 图片消息， 34 = 语音消息， 47 = 表情消息
    SubType: str
    IsSender: str
    CreateTime: str
    Sequence: str
    StatusEx: str
    FlagEx: str
    Status: str
    MsgServerSeq: str
    MsgSequence: str
    StrTalker: str
    StrContent: str
    DisplayContent: str
    Reserved0: str
    Reserved1: str
    Reserved2: str
    Reserved3: str
    Reserved4: str
    Reserved5: str
    Reserved6: str
    CompressContent: str
    BytesExtra: str
    BytesTrans: str

    @property
    def room(self) -> str | None:
        if "chatroom" not in self.StrTalker:
            return None
        return self.StrTalker

    @property
    def talker_id(self) -> str:
        decoded_str = b64decode(self.BytesExtra)
        decoded_str = str(decoded_str)
        xml_start_index = decoded_str.find('<')
        if xml_start_index != -1:
            cleaned_str = decoded_str[:xml_start_index]
        else:
            cleaned_str = decoded_str
        cleaned_str = sub(r'\\x[0-9a-fA-F]{2}', '', cleaned_str)
        cleaned_str = sub(r'\\s|\\n|\\t|\\r|[b\']', '', cleaned_str)
        return cleaned_str

    @property
    def content(self) -> str:
        return self.StrContent

    @property
    def data(self):
        return {
            "localId": self.localId,
            "TalkerId": self.TalkerId,
            "MsgSvrID": self.MsgSvrID,
            "Type": self.Type,
            "SubType": self.SubType,
            "IsSender": self.IsSender,
            "CreateTime": self.CreateTime,
            "Sequence": self.Sequence,
            "StatusEx": self.StatusEx,
            "FlagEx": self.FlagEx,
            "Status": self.Status,
            "MsgServerSeq": self.MsgServerSeq,
            "MsgSequence": self.MsgSequence,
            "StrTalker": self.StrTalker,
            "StrContent": self.StrContent,
            "DisplayContent": self.DisplayContent,
            "Reserved0": self.Reserved0,
            "Reserved1": self.Reserved1,
            "Reserved2": self.Reserved2,
            "Reserved3": self.Reserved3,
            "Reserved4": self.Reserved4,
            "Reserved5": self.Reserved5,
            "Reserved6": self.Reserved6,
            "CompressContent": self.CompressContent,
            "BytesExtra": self.BytesExtra,
            "BytesTrans": self.BytesTrans
        }