#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@File    : test_standard_cost_rfc.py
@Date    : 2026/06/19
@explain : 标准成本更新接口 - 测试脚本

两种用法:
  1) 连通性自检(走 SAPRFC 直连, 调标准 BAPI, 不需要业务参数/不依赖业务库):
       python test_standard_cost_rfc.py --mode conn

  2) 直连调 ZBAPI_MATVAL_PRICE_CHANGE(排障/验证RFC结构用):
       从业务库取一条真实待更新记录, 用与正式接口相同的逻辑组装请求,
       直连SAP并打印原始返回(不回写), 用于核对参数键名/响应字段位置。
       python test_standard_cost_rfc.py --mode direct \
           --plant 1001 --year 2026 --period 06 --mat-code ZTEST0008
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


def mode_direct(plant_code, year, period, mat_code):
    """用法2: 直连调 ZBAPI_MATVAL_PRICE_CHANGE, 打印原始返回(验证RFC结构)"""
    print("=== [2] SAPRFC 直连调用 ZBAPI_MATVAL_PRICE_CHANGE ===")
    print(f"条件: plant_code={plant_code}, year={year}, period={period}, mat_code={mat_code}")

    from ZZ_standard_cost_update import (
        INTERFACE_CODE,
        get_standard_cost_update_list,
        prepare_price_change_request,
    )
    from ZZEXT_SapRFC import SAPRFC

    # 取一条真实待更新记录(posting_status != 'S')
    records = get_standard_cost_update_list(plant_code, year, period, mat_code)
    if not records:
        print("未找到符合条件的待更新记录 "
              "(检查 plant/year/period/mat_code, 或该记录已是 posting_status='S')")
        return
    record = records[0]
    print(f"命中记录: {_dumps(record)}")

    # 组装请求(与正式接口完全一致)
    sap_send_data = prepare_price_change_request(record)
    print(f"发送参数: {_dumps(sap_send_data)}")

    sap = SAPRFC()
    try:
        # 直连参数键名以 SAP SE37 中函数模块的 signature 为准
        result = sap.call(INTERFACE_CODE, sap_send_data)
        print(f"SAP 原始返回: {_dumps(result)}")
    finally:
        sap.close()


def main():
    parser = argparse.ArgumentParser(description="标准成本更新接口 - 测试脚本")
    parser.add_argument("--mode", choices=["conn", "direct"], default="conn",
                        help="conn=连通性自检; direct=直连调ZBAPI_MATVAL_PRICE_CHANGE(默认 conn)")
    parser.add_argument("--plant", dest="plant_code", default="", help="工厂代码")
    parser.add_argument("--year", default="", help="年度")
    parser.add_argument("--period", default="", help="期间")
    parser.add_argument("--mat-code", dest="mat_code", default="", help="物料编码")
    args = parser.parse_args()

    try:
        if args.mode == "conn":
            mode_conn()
        elif args.mode == "direct":
            biz_args = [args.plant_code, args.year, args.period, args.mat_code]
            if not all(biz_args):
                parser.error("direct 模式需要: --plant --year --period --mat-code")
            mode_direct(args.plant_code, args.year, args.period, args.mat_code)
    except Exception as e:
        print(f"=== 测试失败: {e} ===")
        raise


if __name__ == "__main__":
    main()


