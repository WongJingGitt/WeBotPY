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