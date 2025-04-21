from pydantic import BaseModel, Field
from databases.database_type import MemoryEventType


class CurrentTimeResult(BaseModel):
    current_time_format: str = Field(..., description="当前时间的格式化字符串，例如：\"2023-07-01 12:34:56\"。")
    current_time_unix: int | float = Field(..., description="当前时间的Unix时间戳，精确到秒。")
    current_weekday: str = Field(..., description="当前星期几，例如：\"Monday\"。")
    current_timezone: str = Field(..., description="当前时区，例如：\"中国标准时间\"。")


class GetContentInput(BaseModel):
    port: int | float = Field(..., description="当前微信的Port，格式为int，整数。")
    keyword: str = Field(...,
                         description="查询的关键字，可以是微信名或者备注。将用此关键字在数据库进行模糊搜索，匹配的结果可能是一个，也可能是多个。")


class ContentResult(BaseModel):
    wxid: str = Field(..., description="联系人的wxid，例如：\"wxid_abcdefg123456\"。")
    remark: str = Field(..., description="用户对这个联系人的备注名，例如：\"我的好友\"。")
    name: str = Field(..., description="这个联系人的微信名，例如：\"小明\"。")
    avatar: str = Field(...,
                        description="这个联系人的头像地址，例如：\"https://wx.qlogo.cn/mmhead/ver_1/abcdefg1234567890/132\"。")


class GetUserInfoInput(BaseModel):
    port: int | float = Field(..., description="当前微信的Port，格式为int，整数。")


class UserInfoResult(BaseModel):
    wxid: str = Field(..., description="当前用户的wxid，例如：\"wxid_abcdefg123456\"。")
    name: str = Field(..., description="用户的微信名，例如：\"吴彦祖\"。")
    avatar: str = Field(...,
                        description="这个联系人的头像地址，例如：\"https://wx.qlogo.cn/mmhead/ver_1/abcdefg1234567890/132\"。")
    mobile: str = Field(..., description="用户的手机号，例如：\"13800000000\"。")
    province: str = Field(..., description="用户的省份，例如：\"Zhejiang\"。")
    city: str = Field(..., description="用户的城市，例如：\"Hangzhou\"。")
    country: str = Field(..., description="用户的国家，例如：\"CN\"。")
    signature: str = Field(..., description="用户的个性签名，例如：\"Hello World!\"。")


class GetMessageByWxidAndTimeInput(BaseModel):
    port: int | float = Field(..., description="当前微信的Port，格式为int，整数。")
    wxid: str = Field(..., description="联系人的wxid，例如：\"wxid_abcdefg123456\"。")
    start_time: str = Field(...,
                            description="查询的起始时间，格式为\"YYYY-MM-DD HH:MM:SS\"，例如：\"2023-07-01 12:34:56\"。")
    end_time: str = Field(..., description="查询的结束时间，格式为\"YYYY-MM-DD HH:MM:SS\"，例如：\"2023-07-01 12:34:56\"。")


class SendTextMessageInput(BaseModel):
    port: int | float = Field(..., description="当前微信的Port，格式为int，整数。")
    wxid: str = Field(..., description="消息接收人的wxid，例如：\"wxid_abcdefg123456\"。")
    message: str = Field(..., description="要发送的文本消息，例如：\"Hello World!\"。")


class SendMentionsMessageInput(BaseModel):
    port: int | float = Field(..., description="当前微信的Port，格式为int，整数。")
    chatroom_id: str = Field(..., description="消息接收群聊的id，例如：\"123456789@chatroom\"。")
    message: str = Field(..., description="@消息中附带的文本内容，例如：\"Hello World!\"。")
    at_users_wxid = Field(..., description="要@的人的wxid列表，当需要提及所有人时传递`notify@all`。例如：[\"wxid_abcdefg123456\", \"wxid_abcdefg123456\"]、[\"notify@all\"]。")

class GetMemoriesInput(BaseModel):
    wxid: str = Field(..., description="这份记忆主体对象的wxid，如果是关于群聊或者群成员的记忆，这里应该传递群聊的wxid。")
    port: int = Field(..., description="当前微信的Port。")


class GetMemoriesResult(BaseModel):
    type: MemoryEventType = Field(..., description="记忆的类型。内容仅会限定在：'event', 'topic', 'social_network', 'nickname', 'keyword', 'summary'之一。")
    content: str = Field(..., description="记忆的内容。")
    event_time: str | None = Field(default=None, description="记忆的事件发生时间，通常只有event才会记录。")
    wxid: str = Field(..., description="记忆主体对象的wxid，如果是关于群聊或者群成员的记忆，这里应该会是群聊的wxid。")


class AddMemoryInput(BaseModel):
    wxid: str = Field(..., description="这份记忆主体对象的wxid，如果是关于群聊或者群成员的记忆，这里应该传递群聊的wxid。")
    port: int = Field(..., description="当前微信的Port。")
    type: MemoryEventType = Field(..., description="记忆的类型。在以下选项中选择一项：'event', 'topic', 'social_network', 'nickname', 'keyword', 'summary'")
    content: str = Field(..., description="记忆的内容。")
    event_time: str | None = Field(default=None, description="记忆的事件发生时间，通常只有event才会记录。")
