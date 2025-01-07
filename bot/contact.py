from dataclasses import dataclass


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
    big_head_img_url_discard: str
    small_head_img_url_discard: str
    head_img_md5_discard: str
    chat_room_notify: str
    reserved5: str
    reserved6: str
    reserved7: str
    extra_buf: str
    reserved8: str
    reserved9: str
    reserved10: str
    reserved11: str
    BigHeadImgUrl: str = None

    def room(self):
        return '@chatroom' in self.wxid

    def openim(self):
        return '@openim' in self.wxid

    @property
    def data(self):
        return {
            "wxid": self.wxid,
            "custom_id": self.custom_id,
            "encrypt_username": self.encrypt_username,
            "del_flag": self.del_flag,
            "type": self.type,
            "verify_flag": self.verify_flag,
            "reserved1": self.reserved1,
            "reserved2": self.reserved2,
            "reserved3": self.reserved3,
            "reserved4": self.reserved4,
            "remark": self.remark,
            "name": self.name,
            "label_id_list": self.label_id_list,
            "domain_list": self.domain_list,
            "chat_room_type": self.chat_room_type,
            "py_initial": self.py_initial,
            "quan_pin": self.quan_pin,
            "remark_py_initial": self.remark_py_initial,
            "remark_quan_pin": self.remark_quan_pin,
            "chat_room_notify": self.chat_room_notify,
            "reserved5": self.reserved5,
            "reserved6": self.reserved6,
            "reserved7": self.reserved7,
            "extra_buf": self.extra_buf,
            "reserved8": self.reserved8,
            "reserved9": self.reserved9,
            "reserved10": self.reserved10,
            "reserved11": self.reserved11,
            "BigHeadImgUrl": self.BigHeadImgUrl
        }