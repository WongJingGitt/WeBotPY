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