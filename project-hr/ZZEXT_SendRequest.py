# -*- coding: UTF-8 -*-
"""
@File    : SendRequest.py
@Author  : tianzhao.li@dxdstech.com
@Date    : 2026/1/8 20:18 
@explain : 发送请求，推送数据，并保存日志
"""
import json
import traceback
import uuid
from datetime import datetime

import requests
from libenhance import get_cnf
from requests.auth import HTTPBasicAuth
from SapInteractionLog import createSapLog
from ZZEXT_HanaDB import HanaDB


def SendToSap(interface_code, interface_name, payload, synchronizatio_user=0):
    """
    :param interface_code: 业务路由
    :param interface_name: 业务路由
    :param payload: 请求体参数
    :return: 响应体
    """

    start_timestamp = int(datetime.timestamp(datetime.now()))
    guid = 'MH' + uuid.uuid4().hex

    try:
        if interface_code == "PLM_WORKCENTER":
            response = requests.post(
                get_cnf("plm.url"),
                json=payload
            )
        else:
            if "UUID" not in payload:
                payload["UUID"] = guid
            payload["SYSID"] = "MH"
            response = requests.post(
                get_cnf("restsap.url") + f"{interface_code}" + f"{'_600' if get_cnf('hana.client') == '600' else ''}",
                auth=HTTPBasicAuth(get_cnf("restsap.username"), get_cnf("restsap.password")),
                json=payload
            )

        end_timestamp = int(datetime.timestamp(datetime.now()))
        time_difference = end_timestamp - start_timestamp

        status_code = response.status_code
        res = {}
        if status_code == 200:
            res = response.json()
        elif status_code == 400:
            print(f"status_code: {status_code} 客户端错误：请求无效")
        elif status_code == 401:
            print(f"status_code: {status_code} 未授权, 请检查相应的账号密码")
        elif status_code == 403:
            print(f"status_code: {status_code} 禁止访问")
        elif status_code == 404:
            print(f"status_code: {status_code} 资源未找到")
        elif status_code == 500:
            print(f"status_code: {status_code} 服务器内部错误")
        else:
            print(f"状态码: {status_code}")

        createSapLog([{"GUID": guid,
                       "interface_code": interface_code,
                       "interface_name": interface_name,
                       "interface_data": json.dumps([payload]),
                       "interface_returns_data": json.dumps([res]),
                       "message_type": res.get("TYPE") or res.get("errcode"),
                       "message_text": res.get("MSG") or res.get("errmsg"),
                       "start_timestamp": start_timestamp,
                       "end_timestamp": end_timestamp,
                       "time_difference": time_difference,
                       "synchronizatio_user": synchronizatio_user
                       }])

    except Exception as e:
        print(str(e))
        traceback.print_exc()
    return res


def SendToERP(interface_code, interface_name, payload, synchronizatio_user=0):
    """
    :param interface_code: 业务路由
    :param interface_name: 业务路由
    :param payload: 请求体参数
    :return: 响应体
    """

    start_timestamp = int(datetime.timestamp(datetime.now()))
    guid = uuid.uuid4().hex

    # 获取token
    token_payload = {
        "client_id": get_cnf("erp.token_client_id"),
        "client_secret": get_cnf("erp.token_client_secret"),
        "username": get_cnf("erp.token_username"),
        "accountId": get_cnf("erp.token_accountId"),
        "nonce": guid,
        "timestamp": str(datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
        "language": "zh_CN"
    }
    token_response = requests.post(get_cnf("erp.token_url"), json=token_payload)
    token = token_response.json().get("data", {}).get("access_token", "")
    print(f"token:{token}")
    # 发请求
    headers = {
        "access_token": token,
        "Content-Type": "application/json; charset=UTF-8"
    }
    response = requests.post(get_cnf("erp.ip_port") + payload.pop("url", ""), json=payload, headers=headers)
    print(f"status_code:{response.status_code}")
    print(f"response:{response}")
    res = response.json()

    print(res)

    # 将返回转成秘火统一格式
    if not res.get("data"):
        res["TYPE"] = "S" if res.get("status") else "E"
        res["MSG"] = res.get("message")
    elif res.get("data", {}).get("output"):
        res["TYPE"] = "S" if res.get("data", {}).get("output", {}).get("returnMap", {}).get("code") == "0" else "E"
        res["MSG"] = res.get("data", {}).get("output", {}).get("returnMap", {}).get("message")
    elif res.get("data", {}).get("result"):
        res["TYPE"] = "S" if res.get("status") else "E"
        res["MSG"] = res.get("message")
    else:
        res["TYPE"] = "E"
        res["MSG"] = "秘火未取到金蝶返回结构中的状态信息"

    # 存日志
    end_timestamp = int(datetime.timestamp(datetime.now()))
    time_difference = end_timestamp - start_timestamp

    createSapLog([{"GUID": guid,
                   "interface_code": interface_code,
                   "interface_name": interface_name,
                   "interface_data": json.dumps([payload]),
                   "interface_returns_data": json.dumps([res]),
                   "message_type": res.get("TYPE") or "",
                   "message_text": res.get("MSG") or "",
                   "start_timestamp": start_timestamp,
                   "end_timestamp": end_timestamp,
                   "time_difference": time_difference,
                   "synchronizatio_user": synchronizatio_user
                   }])

    return res


def SendToOA(interface_code, interface_name, payload, synchronizatio_user=0):
    """
    :param interface_code: 业务路由
    :param interface_name: 业务路由
    :param payload: 请求体参数
    :return: 响应体
    """

    start_timestamp = int(datetime.timestamp(datetime.now()))
    guid = uuid.uuid4().hex

    response = requests.post(get_cnf("oa.url"), data=payload)
    res = response.json()

    # 将返回转成秘火统一格式
    res["TYPE"] = "S" if res.pop("success", False) else "E"
    res["MSG"] = res.pop("msg", "")

    # 存日志
    end_timestamp = int(datetime.timestamp(datetime.now()))
    time_difference = end_timestamp - start_timestamp

    createSapLog([{"GUID": guid,
                   "interface_code": interface_code,
                   "interface_name": interface_name,
                   "interface_data": json.dumps([payload]),
                   "interface_returns_data": json.dumps([res]),
                   "message_type": res.get("TYPE"),
                   "message_text": res.get("MSG"),
                   "start_timestamp": start_timestamp,
                   "end_timestamp": end_timestamp,
                   "time_difference": time_difference,
                   "synchronizatio_user": synchronizatio_user
                   }])

    return res