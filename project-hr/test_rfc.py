#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@File    : test_rfc.py
@Date    : 2026/06/15
@explain : 会计凭证过账推送接口 - 测试脚本
"""
import argparse
import json


def _dumps(obj):
    """格式化打印(兼容 Decimal/datetime 等不可序列化对象)"""
    return json.dumps(obj, ensure_ascii=False, default=str, indent=2)


def mode_conn():
    """用法1: SAPRFC 连通性自检"""
    print("=== [1] SAPRFC 连通性自检 ===")
    from ZZEXT_SapRFC import SAPRFC

    sap = SAPRFC()  # 读 rfc.* 配置建连, 连不上会抛异常
    try:
        result = sap.call("BAPI_COMPANYCODE_GETLIST")
        company_list = result.get("COMPANYCODE_LIST", [])
        print(f"SAP 连接成功, 共返回 {len(company_list)} 个公司代码:")
        for c in company_list[:10]:
            print(f"  - {c}")
    finally:
        sap.close()


def mode_post(system, summary_unique_number, company_code, year, archiv_doc_num, user_id, special_sign):
    """用法2: 调推送接口(走 SendToSap 中间件)"""
    print(f"=== [2] 调推送接口 (system={system}) ===")
    from ZZEXT_send_fi_archiv_doc_to_sap import (
        send_fi_archiv_doc_to_rfc,
        send_fi_archiv_doc_to_sap,
    )

    payload = {
        "summary_unique_number": summary_unique_number,
        "company_code": company_code,
        "year": year,
        "archiv_doc_num": archiv_doc_num,
    }
    print(f"请求参数: {_dumps(payload)}")

    if system == "sap":
        resp = send_fi_archiv_doc_to_sap(payload, user_id=user_id, special_sign=special_sign)
    else:
        resp = send_fi_archiv_doc_to_rfc(payload, user_id=user_id, special_sign=special_sign)
    print(f"返回结果: {_dumps(resp)}")


def mode_direct(summary_unique_number, company_code, year, archiv_doc_num, special_sign, rfc_name):
    """用法3: 绕过中间件, SAPRFC 直连 SAP 函数模块(排障中间件用)"""
    print(f"=== [3] SAPRFC 直连调用 {rfc_name} ===")
    from ZZEXT_SapRFC import SAPRFC
    from ZZEXT_send_fi_archiv_doc_to_sap import prepare_sap_request

    # 复用接口的数据组装逻辑, 拿到要发给 SAP 的 head/items
    sap_send_data = prepare_sap_request(summary_unique_number, company_code, year, archiv_doc_num, special_sign)
    head = sap_send_data["head"]
    items = sap_send_data["items"]
    # 剥离内部辅助字段(非 SAP DDIC 字段, 直连传入 pyrfc 可能报错)
    for k in ("accounting_document_type", "fi_sum_doc_type"):
        head.pop(k, None)
    print(f"抬头: {_dumps(head)}")
    print(f"明细行数: {len(items)}")

    sap = SAPRFC()
    try:
        # 直连参数键名以 SAP SE37 中函数模块的 signature 为准
        result = sap.call(rfc_name, {"HEAD": head, "ITEMS": items})
        print(f"SAP 返回: {_dumps(result)}")
    finally:
        sap.close()


def main():
    parser = argparse.ArgumentParser(description="会计凭证过账推送接口 - 测试脚本")
    parser.add_argument("--mode", choices=["conn", "post", "direct"], default="conn",
                        help="conn=连通性自检; post=调推送接口; direct=SAPRFC直连(默认 conn)")
    parser.add_argument("--system", choices=["sap", "rfc"], default="sap",
                        help="post 模式下推送的目标系统: sap=大写字段; rfc=全小写字段")
    parser.add_argument("--summary-unique-number", dest="summary_unique_number", default="")
    parser.add_argument("--company-code", dest="company_code", default="")
    parser.add_argument("--year", default="")
    parser.add_argument("--archiv-doc-num", dest="archiv_doc_num", default="")
    parser.add_argument("--user-id", dest="user_id", type=int, default=0)
    parser.add_argument("--special-sign", dest="special_sign", action="store_true", help="特殊标志")
    parser.add_argument("--rfc-name", dest="rfc_name", default="ZRFC_MH_DOC_POST_MASS",
                        help="direct 模式下直连的 SAP 函数模块名")
    args = parser.parse_args()

    biz_args = [args.summary_unique_number, args.company_code, args.year, args.archiv_doc_num]

    try:
        if args.mode == "conn":
            mode_conn()
        elif args.mode == "post":
            if not all(biz_args):
                parser.error("post 模式需要: --summary-unique-number --company-code --year --archiv-doc-num")
            mode_post(args.system, args.summary_unique_number, args.company_code,
                      args.year, args.archiv_doc_num, args.user_id, args.special_sign)
        elif args.mode == "direct":
            if not all(biz_args):
                parser.error("direct 模式需要: --summary-unique-number --company-code --year --archiv-doc-num")
            mode_direct(args.summary_unique_number, args.company_code, args.year,
                        args.archiv_doc_num, args.special_sign, args.rfc_name)
    except Exception as e:
        print(f"=== 测试失败: {e} ===")
        raise


if __name__ == "__main__":
    main()
