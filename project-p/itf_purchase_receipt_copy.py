#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@File    : itf_purchase_receipt.py
@Author  : long.wang@dxdstech.com
@Date    : 2025/9/28 17:04
@explain : 秘火外购收货接口
"""
import json
import uuid
from collections import defaultdict
from datetime import datetime

from DbHelper import DbHelper  # type:ignore
from DxCompanyPeriodUtil import check_material_period  # type:ignore
from libenhance import Request, Response
from Z_posting_date_verify import (
    verify_material_period,  # type:ignore 🌿 2026年1月2日 增加过账日期校验
)

dh = DbHelper()

from decimal import ROUND_HALF_UP, Decimal, getcontext

# 全局精度至少要 >= 5 + 运算位数
getcontext().prec = 28


def compare_numeric_strings(str1, str2, price_unit, decimal_places=8):
    """
    比较 str1 是否等于 str2 * price_unit（支持 8 位小数）
    """
    print("str1:", str1)
    print("str2:", str2)
    print("price_unit:", price_unit)

    num1 = Decimal(str1)
    num2 = Decimal(str2)
    unit = Decimal(str(price_unit))

    # 计算结果
    calculated = num2 * unit

    # 统一量化到指定小数位
    quant = Decimal("1").scaleb(-decimal_places)
    num1_q = num1.quantize(quant, rounding=ROUND_HALF_UP)
    calculated_q = calculated.quantize(quant, rounding=ROUND_HALF_UP)

    return num1_q == calculated_q


def check_length_type_field(data: dict):
    """校验数据类型是否合法,长度是否合法"""
    header_check = {
        "uf_guid": ("varchar", 64, "GUID"),
        "uf_bs_category": ("varchar", 64, "业务类别"),
        "uf_vendor_short_name": ("varchar", 20, "供应商简称"),
        "uf_posting_date": ("date", 0, "过账日期"),
        "uf_posting_time": ("datetime", 0, "过账时间"),
        "uf_company_code": ("varchar", 6, "公司主体"),
        "uf_remarks": ("varchar", 255, "抬头备注"),
    }

    item_check = {
        "uf_po_sn": ("varchar", 18, "采购订单号"),
        "uf_po_items": ("int", 0, "采购订单行号"),
        "uf_mat_code": ("varchar", 40, "物料编码"),
        # 此处长度校验作废
        "uf_unit_price_including_tax": ("decimal", (30, 10), "含税单价"),
        "uf_ZT04": ("varchar", 20, "Fountry Lot"),
        "uf_wafer_id": ("varchar", 80, "晶圆片号"),
        "uf_vendor_batch": ("varchar", 24, "供应商批次"),
        "uf_stor_loc_code": ("varchar", 50, "库存地点"),
        "uf_target_plant_code": ("varchar", 6, "目标工厂代码"),
        "uf_target_stor_loc_code": ("varchar", 50, "目标库存地点"),
        "uf_transaction_qty": ("decimal", (16, 3), "交易数量(片数)"),
        "uf_parallel_qty": ("decimal", (16, 3), "平行数量(颗数)"),
        "uf_reference1_item": ("varchar", 255, "发票号"),
        "uf_ZT13": ("varchar", 70, "光罩号"),
        "uf_extended_batch_attributes1": ("varchar", 80, "备注"),
        "uf_ZT26": ("varchar", 10, "贸易类型"),
        "uf_movement_type": ("varchar", 6, "移动类型"),
        "uf_plant_code": ("varchar", 6, "工厂代码"),
        "uf_inventory_status": ("varchar", 4, "库存状态"),
        "uf_electroplating_date": ("date", 0, "电镀日期"),
        "uf_quality_type": ("varchar", 10, "品质类型"),
        "uf_tracking_number": ("varchar", 50, "运单号")
    }

    errors = []
    # verify_material_period(data, errors)  # 🌿 2026年1月2日 增加过账日期校验
    # print('---1',errors)
    def check_field(name, value, rule):
        dtype, limit, cname = rule
        if value is None or value == "":
            return  # 空值不校验（如需必填，可额外处理）

        if dtype == "varchar":
            if not isinstance(value, str):
                errors.append(f"{cname}({name}) 应为字符串，但得到 {type(value).__name__}")
            elif len(value) > limit:
                errors.append(f"{cname}({name}) 超过最大长度 {limit}，实际长度 {len(value)}")

        elif dtype == "int":
            try:
                int(value)
            except Exception:
                errors.append(f"{cname}({name}) 应为整数，但值为 {value}")

        elif dtype == "decimal":
            total, scale = limit
            try:
                d = Decimal(str(value))
                int_len = len(d.as_tuple().digits) - abs(d.as_tuple().exponent)  # type:ignore
                frac_len = abs(d.as_tuple().exponent)  # type:ignore
                if int_len + frac_len > total or frac_len > scale:
                    errors.append(f"{cname}({name}) 超出精度 (max {total},{scale})，实际 {d}")
            except Exception:
                errors.append(f"{cname}({name}) 应为小数，但值为 {value}")

        elif dtype == "date":
            try:
                datetime.strptime(value, "%Y-%m-%d")
            except Exception:
                errors.append(f"{cname}({name}) 日期格式错误，应为 YYYY-MM-DD，实际 {value}")

        elif dtype == "time":
            try:
                datetime.strptime(value, "%H:%M:%S")
            except Exception:
                errors.append(f"{cname}({name}) 时间格式错误，应为 HH:MM:SS，实际 {value}")

    # 校验 header
    print('校验 header')
    for k, rule in header_check.items():
        v = data.get(k)
        check_field(k, v, rule)

    # 校验 items
    print('校验 items')
    items = data.get("items", [])
    if not isinstance(items, list):
        errors.append("items 应为数组")
    else:
        for idx, item in enumerate(items):
            for k, rule in item_check.items():
                v = item.get(k)
                check_field(k, v, rule)

    print('---2',errors)
    if len(errors) > 0:
        return False, ";".join(errors)
    else:
        return True, ""


def check_item_required(item):
    po_sn, po_items = item.get("uf_po_sn", ""), item.get("uf_po_items", "")
    if len(item.get("uf_wafer_id", "")) != 0 and len(item.get("uf_wafer_id", "")) != 2:
        return False, 0, f"晶圆片号仅可为空或长度为2的字符串", po_sn, po_items
    typer = 0  # 0: 晶圆、 1非晶圆
    if not item.get("uf_po_sn", ""):
        return False, typer, "采购订单号必填", po_sn, po_items
    if not item.get("uf_po_items", ""):
        return False, typer, "采购订单行号必填", po_sn, po_items

    uf_mat_code = item.get("uf_mat_code", "")
    if not uf_mat_code:
        return False, typer, f"物料编码必填", po_sn, po_items
    mat_group_list = dh.query_sql(f"""
        SELECT
            mat_group, mat_type
        FROM  t_mmd_material_basic_data
        WHERE mat_code = '{uf_mat_code}'
    """)
    if not mat_group_list:
        return False, 0, f"采购订单号{po_sn},行号{po_items}未找到对应的物料组", po_sn, po_items
    mat_info = mat_group_list[0]
    mat_group = mat_info["mat_group"]
    mat_type = mat_info["mat_type"]
    if mat_group == "4001" and mat_type == "ZIP1":
        mat_group = "4001ZIP"

    if str(mat_group) == "1001":
        typer = 0
        item["uf_quality_type"] = "run" if not item.get("uf_quality_type", "") else item["uf_quality_type"]
    # 202601011
    elif str(mat_group) in ("3002", "3003", "3004", "4001ZIP"):
        typer = 2
        item["uf_quality_type"] = "run" if not item.get("uf_quality_type", "") else item["uf_quality_type"]
    else:
        typer = 1

    if str(mat_group) == "3005" and not item.get("uf_electroplating_date", ""):
        return False, typer, f"当前物料对应电镀日期必填", po_sn, po_items

    """校验字段必填项是否完整"""
    if not item.get("uf_unit_price_including_tax", 0):
        return False, typer, "含税单价必填", po_sn, po_items
    if not item.get("uf_stor_loc_code", ""):
        return False, typer, "库存地点必填", po_sn, po_items
    plant_code, stor_loc_code = item.get("uf_plant_code", ""), item.get("uf_stor_loc_code", "")
    data_list = dh.query_sql(
        f"""
            select
                id
            FROM t_os_plant_storage_location_alloc
            WHERE plant_code = '{plant_code}' AND stor_loc_code = '{stor_loc_code}'
        """
    )
    if not data_list:
        return False, typer, f"采购订单号{po_sn},行号{po_items}: 工厂{plant_code}与 库存地点{stor_loc_code}未找到对应关系", po_sn, po_items
    if typer in [0, 2]:
        target_plant_code, target_stor_loc_code = item.get("uf_target_plant_code", ""), item.get(
            "uf_target_stor_loc_code", "")
        data_list = dh.query_sql(
            f"""
                select
                    id
                FROM t_os_plant_storage_location_alloc
                WHERE plant_code = '{target_plant_code}' AND stor_loc_code = '{target_stor_loc_code}'
            """
        )
        if not data_list:
            return False, typer, f"采购订单号{po_sn},行号{po_items}: 目标工厂{plant_code}与 目标库存地点{stor_loc_code}未找到对应关系", po_sn, po_items
    # uf_transaction_qty = item.get("uf_transaction_qty", "")
    # if uf_transaction_qty == "":
    #     return False, typer, "交易数量必填", po_sn, po_items
    # if not item.get("uf_transaction_qty", 0):

    if typer == 0:
        # 晶圆判断
        # 20260106 晶圆 交易数量、平行数量都必填
        if not item.get("uf_ZT04", ""):
            return False, typer, f"采购订单号{po_sn},行号{po_items}Fountry Lot字段必填", po_sn, po_items
        if not item.get("uf_wafer_id", ""):
            return False, typer, f"采购订单号{po_sn},行号{po_items}晶圆片号字段必填", po_sn, po_items
        if not item.get("uf_target_plant_code", ""):
            return False, typer, f"采购订单号{po_sn},行号{po_items}目标工厂代码必填", po_sn, po_items
        if not item.get("uf_target_stor_loc_code", ""):
            return False, typer, f"采购订单号{po_sn},行号{po_items}目标库存地点必填", po_sn, po_items
        if not float(item.get("uf_transaction_qty", "0")):
            return False, typer, f"采购订单号{po_sn},行号{po_items}交易数量必填", po_sn, po_items
        if not item.get("uf_parallel_qty", ""):
            return False, typer, f"采购订单号{po_sn},行号{po_items}平行数量必填", po_sn, po_items
        if item.get("uf_vendor_batch", ""):
            return False, typer, f"采购订单号{po_sn},行号{po_items}供应商批次应为空值", po_sn, po_items
        code, msg = check_hsdj(item, po_sn, po_items, typer)
        if not code:
            return False, typer, msg, po_sn, po_items
    elif typer == 2:
        if not item.get("uf_ZT04", ""):
            return False, typer, f"采购订单号{po_sn},行号{po_items}Fountry Lot字段必填", po_sn, po_items
        if not item.get("uf_wafer_id", ""):
            return False, typer, f"采购订单号{po_sn},行号{po_items}晶圆片号字段必填", po_sn, po_items
        if not item.get("uf_target_plant_code", ""):
            return False, typer, f"采购订单号{po_sn},行号{po_items}目标工厂代码必填", po_sn, po_items
        if not item.get("uf_target_stor_loc_code", ""):
            return False, typer, f"采购订单号{po_sn},行号{po_items}目标库存地点必填", po_sn, po_items
        # if not item.get("uf_transaction_qty", ""):
        #     return False, typer, f"采购订单号{po_sn},行号{po_items}交易数量必填", po_sn, po_items
        if not item.get("uf_parallel_qty", ""):
            return False, typer, f"采购订单号{po_sn},行号{po_items}平行数量必填", po_sn, po_items
        if item.get("uf_vendor_batch", ""):
            return False, typer, f"采购订单号{po_sn},行号{po_items}供应商批次应为空值", po_sn, po_items
        code, msg = check_hsdj(item, po_sn, po_items, typer)
        if not code:
            return False, typer, msg, po_sn, po_items
    else:
        # 非晶圆判断
        # 20250106 非晶圆 平行数量必填 交易数量为0或者空
        if item.get("uf_ZT04", ""):
            return False, typer, f"采购订单号{po_sn},行号{po_items}Fountry Lot字段应为空值", po_sn, po_items
        if item.get("uf_wafer_id", ""):
            return False, typer, f"采购订单号{po_sn},行号{po_items}晶圆片号字段应为空值", po_sn, po_items
        if item.get("uf_target_plant_code", ""):
            return False, typer, f"采购订单号{po_sn},行号{po_items}目标工厂代码应为空值", po_sn, po_items
        if item.get("uf_target_stor_loc_code", ""):
            return False, typer, f"采购订单号{po_sn},行号{po_items}目标库存地点应为空值", po_sn, po_items
        if not item.get("uf_parallel_qty", ""):
            return False, typer, f"采购订单号{po_sn},行号{po_items}平行数量必填", po_sn, po_items
        if float(item.get("uf_transaction_qty", "0")):
            return False, typer, f"采购订单号{po_sn},行号{po_items}交易数量应为空值", po_sn, po_items
        if not item.get("uf_vendor_batch", ""):
            return False, typer, f"采购订单号{po_sn},行号{po_items}供应商批次字段必填", po_sn, po_items

    return True, typer, "", po_sn, po_items

def check_hsdj(item, po_sn, po_items, typer):
    data_list = dh.query_sql(f"""
                SELECT 
                    mat_code, plant_code, received_pur_qty, 
                    order_qty, unit_price_including_tax
                FROM t_po_item
                WHERE po_sn = '{po_sn}' AND po_items = '{po_items}'
                """)
    if not data_list:
        return False, f"采购订单号{po_sn},行号{po_items}数据不存在"
    price_list = dh.query_sql(f"""
                SELECT
                    price_unit,
                    SUM(unit_price_including_tax) as total_price
                FROM t_po_price_data
                WHERE po_sn = '{po_sn}' AND po_items = '{po_items}'
            """)
    if not price_list:
        return False, f"采购订单号{po_sn},行号{po_items}未找到价格信息"
    data = data_list[0]
    unit_price_including_tax = price_list[0]["total_price"]
    price_unit = price_list[0]["price_unit"]
    if item["uf_mat_code"] != data["mat_code"]:
        return False, f"采购订单号{po_sn},行号{po_items}数据物料编码不一致"
    if typer == 0:
        if item["uf_target_plant_code"] != data["plant_code"]:
            return False, f"采购订单号{po_sn},行号{po_items}数据工厂代码不一致"
    print("===================")
    print(unit_price_including_tax)
    print(item["uf_unit_price_including_tax"])
    if not compare_numeric_strings(str(unit_price_including_tax), str(item["uf_unit_price_including_tax"]),
                                   price_unit):
        return False, f"采购订单号{po_sn},行号{po_items}数据单价不一致"
    item["uf_unit_price_including_tax"] = unit_price_including_tax
    received_pur_qty = data["received_pur_qty"]
    if received_pur_qty == "":
        received_pur_qty = 0
    else:
        received_pur_qty = float(received_pur_qty)
    uf_transaction_qty = float(item["uf_transaction_qty"])
    order_qty = data["order_qty"]
    if order_qty == "":
        order_qty = 0
    else:
        order_qty = float(order_qty)
    if received_pur_qty + uf_transaction_qty > order_qty:
        Z = order_qty - received_pur_qty
        return False, f"采购订单号{po_sn},行号{po_items}数据交易数量超过最大交易数量({Z})"
    return True, ""


def check_items(item_list):
    for item in item_list:
        status, typer, msg, po_sn, po_items = check_item_required(item)
        if not status:
            return False, msg
    return True, ""


# 业务类别，guid，过账日期，采购订单号，行号，移动类型，物料编码，交易类型
def check_header(data_list):
    print('开始校验必填字段:',data_list)
    if not data_list.get("bs_category", ""):
        return False, "业务类别必填"
    if not data_list.get("vendor_short_name", ""):
        return False, "供应商简称必填"
    if not data_list.get("uf_posting_date", ""):
        return False, "过账日期必填"
    if not data_list.get("uf_posting_time", ""):
        return False, "过账时间必填"
    if not data_list.get("uf_company_code", ""):
        return False, "公司主体必填"
    # if not data_list.get("uf_remarks", ""):
    #     return False, "抬头备注必填"
    company_code, posting_date = data_list.get("uf_company_code", ""), data_list.get("uf_posting_date", "")
    if not check_material_period(company_code, posting_date):
        return False, "账期未开"
    return True, ""


def save_data(data_list, GUID, user_id):
    print('data_list:::',data_list)
    index = 1
    items_list = data_list.pop("item")
    data_list["uf_guid"] = GUID
    data_list["create_id"] = user_id
    data_list["update_id"] = user_id
    # header_list = [data_list]
    # dh.batchInsertToDB("ut_emes_post_data_header", header_list)
    # print('items_list:::',items_list)

    for each in items_list:
        print('each:::',each)
        each.setdefault("uf_movement_type", "R001")
        each["uf_guid"] = GUID
        each["uf_line_id"] = index
        each["create_id"] = user_id
        each["update_id"] = user_id
        each["uf_po_sn"] = each.get("customer_po")
        each["uf_po_items"] = each.get("Invoice_Date ")
        each['uf_bs_category'] = 1
        index += 1
    print('items_list:',items_list)
    code, msg, processed = offiline_post_data(items_list)
    print('offiline_post_data成功了:',items_list)
    return code, msg, processed



def purchase_receipt(payload, user_id):
    """
    - 参数说明
            {
                "guid":"DF72087E590C1EEFBZYZNGZZJQZXLPXY",
                "data":{
                    "uf_bs_category":"业务类别",
                    "uf_vendor_short_name":"供应商简称",
                    "uf_posting_date":"过账日期",
                    "uf_posting_time":"过账时间",
                    "uf_company_code":"公司主体",
                    "uf_remarks":"备注",
                    "items":[
                        {
                            "uf_po_sn":"采购订单号",
                            "uf_po_items":"采购订单行号",
                            "uf_movement_type":"移动类型",
                            "uf_mat_code":"物料编码",
                            "uf_unit_price_including_tax":"含税单价",
                            "uf_ZT04":"Fountry Lot",
                            "uf_wafer_id":"晶圆片号",
                            "uf_vendor_batch":"供应商批次",
                            "uf_stor_loc_code":"库存地点",
                            "uf_target_plant_code":"目标工厂代码",
                            "uf_target_stor_loc_code":"目标库存地点",
                            "uf_transaction_qty":"交易数量(片数)",
                            "uf_parallel_qty":"平行数量(颗数)",
                            "uf_reference1_item":"发票号",
                            "uf_ZT13":"光罩号",
                            "uf_extended_batch_attributes1":"备注",
                            "uf_ZT26":"贸易类型",
                            "uf_plant_code":"工厂代码",
                            "uf_inventory_status":"库存状态"
                        },
                        ....
                    ]
                }

            }
    """
    # ===================== 【新增：文件传参 List → 标准接口结构】=====================
    if isinstance(payload, list):
        # 按 invoice_number 分组
        item_group = {}
        for item in payload:
            ito_sn = item.get('invoice_number', '')
            if not ito_sn:
                continue
            if ito_sn not in item_group:
                item_group[ito_sn] = []
            item_group[ito_sn].append(item)

        # 生成最终标准结构
        converted_payloads = []
        print("items:---",item_group)
        for ito_sn, items in item_group.items():
            # 每个交货单生成独立 GUID
            guid = str(uuid.uuid4())
            posting_date = ""
            posting_time = ""
            processed_items = []
            # 行号从 1 开始自增
            line_id = 1
            print("items:---",items)
            for row in items:
                # 复制一份，避免修改原数据
                new_row = row.copy()
                new_row['uf_batch_sn'] = ''
                new_row['uf_ZT05'] = ''
                # 1. 生成自增 line_id
                new_row['line_id'] = line_id
                line_id += 1
                # 2. 处理 uf_mat_code：使用 uf_ipn 的值
                new_row['uf_mat_code'] = new_row.get('uf_ipn', '')
                # 自动取 chip_qty 或 wafer_qty
                ship_qty = str(new_row.get('ship_qty', '')).strip()
                # wafer_qty = str(new_row.get('uf_wafer_qty', '')).strip()
                # has_ship = bool(ship_qty)
                # has_wafer = bool(wafer_qty)
                posting_date = new_row.get('uf_posting_date', '')
                if posting_date:
                    posting_date = posting_date[:10]
                posting_time = new_row.get('uf_posting_date', '')
                # ============== 错误带上 uf_ito_sn + uf_ito_items ==============
                # item_no = new_row.get('uf_ito_items', '未知行')
                # sn = new_row.get('uf_ito_sn', '未知单号')
                # if not has_chip and not has_wafer:
                #     return {
                #         "type": "E",
                #         "message": f"调拨单[{sn}] 行项目[{item_no}]：Chip Qty 和 Wafer Qty 不能同时为空"
                #     }
                # if has_chip and has_wafer:
                #     return {
                #         "type": "E",
                #         "message": f"调拨单[{sn}] 行项目[{item_no}]：Chip Qty 和 Wafer Qty 不能同时有值"
                #     }
                if ship_qty:
                    new_row['ship_qty'] = float(ship_qty)
                # elif wafer_qty:
                #     new_row['uf_qty'] = float(wafer_qty)
                else:
                    new_row['uf_qty'] = 0.0
                print("new_row:---",new_row)
                processed_items.append(new_row)
            new_data = {
                "guid": guid,
                "data": {
                    "header": [
                        {
                            "item": processed_items,
                            "uf_bs_category": "37",        # 固定值
                            "uf_guid": guid,
                            "uf_ito_sn": ito_sn,
                            "uf_posting_date": posting_date,
                            "uf_posting_time": posting_time,
                            "uf_tracking_number": ""
                        }
                    ]
                }
            }
            print("new_row:---",new_data)
            converted_payloads.append(new_data)
        print('最终converted_payloads===---', converted_payloads)
        # ===================== 循环处理每个转换后的payload =====================
        result_list = []
        if len(converted_payloads) <= 0 :
            return {
                "type": "E",
                "message": "数据分组失败，联系后端重新审核分组逻辑"
            }
        for p in converted_payloads:
            res = purchase_receipt(p, user_id)
            result_list.append(res)
        print(result_list,'result_list========')
        if len(result_list) == 1:
            return result_list[0]
        else:
            # 合并多个结果
            all_messages = [r.get('message', '') for r in result_list]
            has_error = any(r.get('type') == 'E' for r in result_list)
            guids = [r.get('guid', '') for r in result_list]
            return {
                "type": "E" if has_error else "S",
                "message": "; ".join(all_messages),
                "guid": ",".join(guids)
            }

    # 先进行数据合法性校验
    print('数据合法性校验:')
    data_list = payload.get("data", [])
    status, msg = check_length_type_field(data_list)

    print('status, msg:',status, msg)
    if not status:
        return {
            "type": "E",
            "message": msg
        }
    
    # # 检验抬头数据是否合法
    # print('检验抬头数据是否合法:')
    # status, msg = check_header(data_list)
    # if not status:
    #     return {
    #         "type": "E",
    #         "message": msg
    #     }
    # # 在校验item数据是否合法
    # print('检验item数据是否合法:')
    # items = data_list.get("items", [])
    # status, msg = check_items(items)
    # if not status:
    #     return {
    #         "type": "E",
    #         "message": msg
    #     }

    # 校验通过后执行保存操作
    guid = payload["guid"]
    data = payload.get("data")
    head = data.get("header")
    dict_head = head[0]
    item = dict_head['item']
    
    print('head:::::',head)

    print('开始走过账了1，save_data:',data_list)
    code, msg, processed = save_data(dict_head, payload['guid'], user_id)
    if code != 200:
        return {
            "type": "E",
            "message": msg
        }
    return {
        "type": "S",
        "message": msg,
        "processed": processed
    }



# 2026.5.28日包装下原有的EMS过账逻辑(原逻辑没有入参，直接从body = json.loads(req.body())取数据)
BUYOUT = '01'
OFFLINE = '03'
CANCEL_OFFLINE = '04'
OUTSOURCED_PROCESSING = '05'
POST_CODE_MAP = {
    BUYOUT: '1',
    OFFLINE: '4',
    CANCEL_OFFLINE: '4',
    OUTSOURCED_PROCESSING: '7'
}

def offiline_post_data(data):
    res = Response()
    print(f'调用过账接口入参-----------{data}')
    if not data:
        res.set_body(json.dumps({"code": 400, "msg": '过账数据不能为空', "data": data}))
        res.commit(True)

    if 'S' in {item.get('uf_post_status', '') for item in data}:
        res.set_body(json.dumps({"code": 400, "msg": '过账成功不能再次过账', "data": data}))
        res.commit(True)
    grouped = defaultdict(list)
    for item in data: 
        item['uf_posting_date'] = item['uf_posting_date']

        grouped[item['uf_guid']].append(item)
    print('grouped',grouped)
    code = 200
    msg = '过账成功'
    all_processed = []
    from Z_post_emes_data import do_post
    for _, items in grouped.items():
        print(f'过账开始-----------{items}')
        code, msg, processed = do_post(items)
        all_processed.extend(processed)
        if code != 200:
            code = 400
            msg = msg

    res.set_body(json.dumps({"code": code, "msg": msg, "data": all_processed}))
    res.commit(True)
    return code, msg, processed

para_mapping = {
    # 顶层字段映射
    'uf_guid': 'GUID',
    'uf_bs_category': 'ZYWLB',
    'uf_vendor_code': 'BU_SORT1',
    'uf_posting_date': 'BUDAT',
    'uf_posting_time': 'CPUTM',
    'uf_company_code': 'BUKRS',
    'uf_remarks': 'ZBZ',

    # ITEM数组中的字段映射
    'uf_line_id': 'ZEILE',
    'uf_group_id': 'GROUP_ID',
    'uf_po_sn': 'EBELN',
    'uf_po_items': 'EBELP',
    'uf_plant_code': 'WERKS',
    'uf_stor_loc_code': 'LGORT',
    'uf_mat_code': 'MATNR',
    'uf_lot_no': 'ZLOT',
    'uf_ZT04': 'ZT04',
    'uf_wafer_id': 'ZWAFERNO',
    'uf_auxiliary_material_batch_sn': 'ZFLCHARG',
    'uf_ZT18': 'ZT18',
    'uf_inventory_status': 'INSMK',
    'uf_runcard': 'ZT66',
    'uf_ZT07': 'ZT07',
    'uf_batch_sn': 'CHARG',
    'uf_box_no': 'ZT67',
    'uf_vendor_batch': 'ZT62',
    'uf_movement_type': 'BWART',
    'uf_transaction_qty': 'ZLOTQTY',
    'uf_parallel_qty': 'MENGE',
    'uf_unit_price_excluding_tax':'NETPR',  ## 新增不含税单价
    'uf_vendor_batch':'ZGYPC',   ## 新增供应商批次
    'uf_target_plant_code':'ZMBGC',
    'uf_target_stor_loc_code':'ZMBKW',
    'uf_reference1_item': 'ZIN',
    'uf_ZT26':'ZMYLX',
    'uf_electroplating_date':'ZT63',
    'uf_tracking_number':'ZYDH',
    'uf_ZT03':'ZT03',
    'uf_ZT22':'ZT22',
    'uf_ZT23':'ZT23',
    'uf_ZT24':'ZT24',
    'uf_ZGD':'ZGD',
    'uf_ZFHUSER':'ZFHUSER'

}


def get_param_mapping(params):
    global para_mapping
    import uuid
    guid = uuid.uuid1()
    header = []
    convert_dic = {}
    guid = params[para_mapping['uf_guid']] if 'GUID' in params else guid
    bs_category = params[para_mapping['uf_bs_category']] if 'ZYWLB' in params else '03'
    vendor_code = params[para_mapping['uf_vendor_code']] if 'BU_SORT1' in params else ''
    posting_date = params[para_mapping['uf_posting_date']] if 'BUDAT' in params else '2025-11-26'
    posting_time = params[para_mapping['uf_posting_time']] if 'CPUTM' in params else '17:06:05'
    company_code = params[para_mapping['uf_company_code']] if 'BUKRS' in params else ''
    remarks = params[para_mapping['uf_remarks']] if 'ZBZ' in params else ''

    convert_dic['uf_bs_category'] = bs_category
    convert_dic['uf_vendor_code'] = vendor_code
    convert_dic['uf_posting_date'] = posting_date
    convert_dic['uf_posting_time'] = posting_time
    convert_dic['uf_company_code'] = company_code
    convert_dic['uf_remarks'] = remarks

    item_ls = []
    # 直接传SAP参数 循环 params['ITEM'], 若传参数为excel_data 循环 params
    # for item in params['ITEM']:
    for item in params:
        dic = {}
        dic['line_id'] = item[para_mapping['uf_line_id']] if 'ZEILE' in params else 1
        dic['group_id'] = item[para_mapping['uf_group_id']] if 'GROUP_ID' in params else ''
        dic['po_sn'] = item[para_mapping['uf_po_sn']]  if 'EBELN' in params else 'A260326021'
        dic['po_items'] = item[para_mapping['uf_po_items']]  if 'EBELP' in params else 10
        dic['plant_code'] = item[para_mapping['uf_plant_code']]  if 'WERKS' in params else ''
        dic['stor_loc_code'] = item[para_mapping['uf_stor_loc_code']]  if 'LGORT' in params else ''
        dic['mat_code'] = item[para_mapping['uf_mat_code']] if 'MATNR' in params else ''
        dic['lot_no'] = item[para_mapping['uf_lot_no']] if 'ZLOT' in params else ''
        dic['ZT04'] = item[para_mapping['uf_ZT04']] if 'ZT04' in params else ''
        dic['wafer_id'] = item[para_mapping['uf_wafer_id']] if 'ZWAFERNO' in params else '12'
        dic['auxiliary_material_batch_sn'] = item[para_mapping['uf_auxiliary_material_batch_sn']] if 'ZFLCHARG' in params else ''
        dic['ZT18'] = item[para_mapping['uf_ZT18']] if 'ZT18' in params else ''
        dic['inventory_status'] = item[para_mapping['uf_inventory_status']] if 'INSMK' in params else '0'
        dic['runcard'] = item[para_mapping['uf_runcard']] if 'ZT66' in params else ''
        dic['ZT07'] = item[para_mapping['uf_ZT07']] if 'ZT07' in params else ''
        dic['batch_sn'] = item[para_mapping['uf_batch_sn']] if 'CHARG' in params else ''
        dic['box_no'] = item[para_mapping['uf_box_no']] if 'ZT67' in params else ''
        dic['vendor_batch'] = item[para_mapping['uf_vendor_batch']] if 'ZT62' in params else ''
        dic['movement_type'] = item[para_mapping['uf_movement_type']] if 'BWART' in params else ''
        dic['transaction_qty'] = item[para_mapping['uf_transaction_qty']] if 'ZLOTQTY' in params else ''
        dic['parallel_qty'] = item[para_mapping['uf_parallel_qty']] if 'MENGE' in params else ''
        dic['uf_unit_price_excluding_tax'] = item[para_mapping['uf_uf_unit_price_excluding_tax']] if 'NETPR' in params else ''
        dic['uf_vendor_batch'] = item[para_mapping['uf_vendor_batch']] if 'ZGYPC' in params else ''
        dic['uf_target_plant_code'] = item[para_mapping['uf_target_plant_code']] if 'ZMBGC' in params else ''
        dic['uf_target_stor_loc_code'] = item[para_mapping['uf_target_stor_loc_code']] if 'ZMBKW' in params else ''
        dic['uf_reference1_item'] = item[para_mapping['uf_reference1_item']] if 'ZIN' in params else ''
        dic['uf_ZT26'] = item[para_mapping['uf_ZT26']] if 'ZMYLX' in params else ''
        dic['uf_electroplating_date'] = item[para_mapping['uf_electroplating_date']] if 'ZT63' in params else ''
        dic['uf_tracking_number'] = item[para_mapping['uf_tracking_number']] if 'ZYDH' in params else ''
        dic['uf_ZT03'] = item[para_mapping['uf_ZT03']] if 'ZT03' in params else ''
        dic['uf_ZT22'] = item[para_mapping['uf_ZT22']] if 'ZT22' in params else ''
        dic['uf_ZT23'] = item[para_mapping['uf_ZT23']] if 'ZT23' in params else ''
        dic['uf_ZT24'] = item[para_mapping['uf_ZT24']] if 'ZT24' in params else ''
        dic['uf_ZGD'] = item[para_mapping['uf_ZGD']] if 'ZGD' in params else ''
        dic['uf_ZFHUSER'] = item[para_mapping['uf_ZFHUSER']] if 'ZFHUSER' in params else ''
        item_ls.append(dic)

    convert_dic['ITEM'] = item_ls

    header.append(convert_dic)

    play_body = {}
    play_body['data'] = {}
    play_body['guid'] = guid
    play_body['data']['header'] = header


    return play_body




def get_all_sap_params(excel_datas):
    source = {}
    item_ls = []

    for item in excel_datas:
        item_dict = {}
        item_dict['ZEILE'] = ''
        item_dict['GROUP_ID'] = item['Group_ID']
        item_dict['EBELN'] = item['委外工单号']
        item_dict['EBELP'] = 10
        item_dict['WERKS'] = item['工厂单号']
        item_dict['LGORT'] = item['库存地点']
        item_dict['MATNR'] = item['物料']
        item_dict['ZLOT'] = item['CHIPONELOT']
        item_dict['ZT04'] = item['FOUNDRYLOT']
        item_dict['ZWAFERNO'] = item['Wafer id']
        item_dict['ZFLCHARG'] = item['辅料批次']
        item_dict['ZT18'] = ''
        item_dict['INSMK'] = ''
        item_dict['ZT66'] = item['Runcard']
        item_dict['ZT07'] = ''
        item_dict['CHARG'] = ''
        item_dict['ZT67'] = ''
        item_dict['ZT62'] = ''
        item_dict['BWART'] = item['移动类型']
        item_dict['ZLOTQTY'] = item['数量(片数)']
        item_dict['MENGE'] = item['数量（颗数）']
        item_ls.append(item_dict)

    source['GUID'] = ''
    source['ZYWLB'] = '03'
    source['BU_SORT1'] = ''
    source['BUDAT'] = ''
    source['CPUTM'] = ''
    source['BUKRS'] = ''
    source['ZBZ'] = ''
    source['ITEM'] = item_ls

    return source