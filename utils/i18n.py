import json
import os
import re

def get_msg(path, lang='zh', **kwargs):
    """
    獲取翻譯文字
    path: 例如 'proposal.too_soon'
    lang: 'zh' 或 'en'
    kwargs: 用於取代字串中的變數，如 min_time="14:00"
    """
    file_path = os.path.join(os.path.dirname(__file__), 'messages.json')
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    keys = path.split('.')
    result = data.get(lang, data['zh']) # 預設中文
    
    try:
        for key in keys:
            result = result[key]
        return result.format(**kwargs) if kwargs else result
    except Exception:
        return path # 若找不到則回傳原路徑

def parse_index(text: str):
    """從字串中解析出第一個數字序號"""
    m = re.search(r'(\d+)', text)
    return int(m.group(1)) if m else None