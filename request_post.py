import json

import requests


def send_request():
    """
    发送 HTTP POST 请求到指定 URL
    """
    url = "https://secretfire-qas.chiponeic.com/manage/#/customized/data/db"
    
    # 请求头设置
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    # 请求体参数
    payload = {
        "a": "aa"
    }
    
    try:
        # 发送 POST 请求
        response = requests.post(
            url=url,
            headers=headers,
            data=json.dumps(payload)  # 将字典转换为 JSON 字符串
        )
        
        # 打印响应信息
        print(f"请求状态码: {response.status_code}")
        print(f"响应头: {dict(response.headers)}")
        print(f"响应内容: {response.text}")
        
        return response
        
    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
        return None

if __name__ == "__main__":
    send_request()