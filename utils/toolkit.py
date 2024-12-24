import requests
from bs4 import BeautifulSoup
from typing import Optional


def get_latest_wechat_version() -> Optional[str]:
    request_headers = {
        'Host': 'github.com',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
    }

    try:
        # 发送同步请求
        response = requests.get('https://github.com/tom-snow/wechat-windows-versions/tags', headers=request_headers)
        response.raise_for_status()  # 检查请求是否成功
    except requests.RequestException:
        return None

    tags_html = response.text
    soup = BeautifulSoup(tags_html, 'html.parser')

    # 获取版本信息
    version_title = soup.find('a', class_='Link--primary Link')
    if version_title:
        version = version_title.get_text()
        version = version.replace('v', '').strip()
        return version

    return None
