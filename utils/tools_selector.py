from bot.webot import WeBot


def generate_multi_contact_text(contacts: dict[str, dict | list]) -> str:
    if type(contacts.get('data')) == 'dict':
        contacts['data'] = [contacts.get('data')]
    result = f"找到了**{len(contacts.get('data'))}**个联系人：  \n\n   "
    for index, contact in enumerate(contacts.get('data')):
        result += f"{index + 1}. **微信名**: `{contact.get('name')}`  \n   **备注**: {contact.get('remark')}  \n   **wxid**: `{contact.get('wxid')}`  \n   **微信号**: `{contact.get('custom_id')}`  \n"
        if index != len(contacts.get('data')) - 1:
            result += "----\n  "
    return result if len(contacts.get('data')) == 1 else result + "\n<br><br>哪个是你要找的联系人呢？"


def get_function_tools(_bot: WeBot) -> dict:
    def get_contact_text(*args, **kwargs):
        contacts = _bot.get_contact_by_keyword(*args, **kwargs)

        if contacts.get('type') == 'none':
            return {"data": "没有找到这个联系人，请确认关键字是否正确。"}

        return {"data": generate_multi_contact_text(contacts)}

    def get_message_summary(*args, **kwargs) -> dict:
        result = _bot.get_message_summary(*args, **kwargs)
        if result.get('type') == 'contact':
            return {"data": "没有找到这个联系人，请确认关键字是否正确。"} if len(result.get('data')) == 0 else {
                "data": generate_multi_contact_text(result)}
        return result

    def send_text(content: str, keywords: str = None, wxid: str = None):
        if wxid:
            _bot.send_text(wxid=wxid, msg=content)
            return {"data": "发送成功"}

        contacts = _bot.get_contact_by_keyword(keywords)
        if contacts.get('type') == 'none':
            return {"data": "没有找到这个联系人，请确认关键字是否正确。"}

        if contacts.get('type') == 'multi':
            return {"data": generate_multi_contact_text(contacts)}

        if contacts.get('type') == 'single':
            return {"data": generate_multi_contact_text(contacts) + "  \n\n找到了这个联系人，确认发送吗？"}

        return {"data": '未知错误'}

    return {
        "contact_captor": get_contact_text,
        "message_summary": get_message_summary,
        "send_text": send_text
    }
