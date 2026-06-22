#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@File    : Z_generate_batch_number.py
@Author  : long.wang@dxdstech.com
@Date    : 2025/12/18
@explain : 批次号生成规则主文件

form Z_generate_batch_number import generate_batch_number
data = [
        {"mat_code":xxxx, "无关字段":""},
    ]
code, msg, reult = generate_batch_number(data)
# print(reult)  # {"mat_code":"xxxx", "无关字段":"", "batch_sn":"", "batch_status":"", "check_info":""}
可以传递无关字段,`batch_sn`，`batch_status`， 'check_info' 不建议放在字典中(会更新掉)
"""
import re
import time
from collections import defaultdict
from datetime import datetime

from DbHelper import DbHelper
from GenerateSerialNum import generate_serial_num, redis_handler, redis_lock
from SystemHelper import EnvKeys, SystemHelper
from ZZEXT_DXBatchDataSave import enhance_check

dbh = DbHelper()
sh = SystemHelper()
current_date = datetime.now().strftime("%y%m%d")

# 通过物料编码获取物料组映射关系
CODE_GROUP_MAP = {}
# 支持那些物料组进行一个批次号生成
EXITS_GROUP = [
    "1001", "1002", "1003", "1004", "2001COF", "2001", "2002",
    "2003", "3005", "3008", "2011", "3001", "3002", "3003",
    "3004", "3006", "3007", "3099", "4001ZIP", "4001", "2001COG"
]
# 不同物料组的必填字段都有那些
GROUP_REQUIRD_FIELD = {
    "1001": ["wafer_id"],
    "1002": ["wafer_id", "batch_type", "uf_quality_type"],
    "1003": ["wafer_id", "batch_type", "uf_quality_type"],
    "1004": ["wafer_id", "batch_type", "uf_quality_type"],
    "2001COF": ["uf_ZT25", "uf_ZT18", "receive_date", "uf_runcard", "batch_type", "uf_quality_type"],
    "2001": ["uf_ZT25", "uf_ZT18", "receive_date", "batch_type", "uf_quality_type"],
    "2002": ["uf_ZT59", "receive_date", "batch_type",
             "uf_quality_type"],
    "2003": ["uf_ZT60", "receive_date", "batch_type",
             "uf_quality_type"],
    "3005": ["vendor_batch", "uf_electroplating_date"],
    "3002": ["wafer_id"],
    "3003": ["wafer_id"],
    "3004": ["wafer_id"],
    "4001ZIP": ["wafer_id"],
}
# 不同物料组都需要那些字段去查询t_batch_number表中是否已经存在对应的批次号  必填字段 不等于 查询字段
GROUP_SELECT_FIELD = {
    "1001": ["lot_no", "wafer_id"],
    "1002": ["lot_no", "wafer_id", "batch_type", "uf_quality_type"],
    "1003": ["lot_no", "wafer_id", "batch_type", "uf_quality_type"],
    "1004": ["lot_no", "wafer_id", "batch_type", "uf_quality_type"],
    "2001COF": ["uf_ZT25", "lot_no", "uf_ZT18", "receive_date", "uf_runcard", "batch_type", "uf_quality_type",
                "uf_ZT26"],
    "2001": ["uf_ZT25", "lot_no", "uf_ZT18", "receive_date", "batch_type", "uf_ZT26", "uf_quality_type"],
    "2002": ["uf_ZT59", "lot_no", "uf_ZT18", "receive_date", "batch_type",
             "uf_quality_type", "uf_runcard", "uf_ZT07"],
    "2003": ["uf_ZT60", "lot_no", "uf_ZT18", "receive_date", "batch_type",
             "uf_quality_type", "uf_box_no", "uf_ZT07", "uf_runcard"],
    "3005": ["vendor_batch", "uf_electroplating_date", "uf_ZT26"],
    "3002": ["lot_no", "wafer_id"],
    "3003": ["lot_no", "wafer_id"],
    "3004": ["lot_no", "wafer_id"],
    "4001ZIP": ["lot_no", "wafer_id"],
}
# 校验传入数据每项 是否符合 表中对应字段的类型和长度
CHECK_FIELD_MAP = {}
# uf_ZT04对应的lot_no
ZT04_LOT_MAP = {}
# po_sn 和 wo_type 对应关系
PO_WO_MAP = {}
# 用来保存可用参数的映射
BATCH_NUMBER_MAP = {}
# 用来更新流水号记录表
GEN_BATCH_LIST = []


def load_data(mat_code_list: list, uf_ZT04_list: list, po_sn_list: list):
    """
    通用方法: 预加载所需数据进行映射
    - 参数
        mat_code_list: 一个包含多个物料编码的列表数据
        uf_ZT04_list: 一个包含多个uf_ZT04数据的列表
        po_sn_list: 一个包含多个po_sn数据的列表
    - 返回
        函数无返回值,会修改全局变量
    """
    start_time = time.time()
    global CODE_GROUP_MAP, CHECK_FIELD_MAP, ZT04_LOT_MAP, PO_WO_MAP, dbpool

    # 加载 物料编码 和 物料组 之间的对应关系
    if not mat_code_list:
        CODE_GROUP_MAP = {}
    else:
        if len(mat_code_list) == 1:
            where_sql = f" WHERE mat_code = '{mat_code_list[0]}'"
        else:
            where_sql = " WHERE mat_code IN (" + ",".join(f"'{x}'" for x in mat_code_list) + ")"
        base_sql = f"""
            SELECT mat_code, mat_group, uf_pkg, mat_type
            FROM t_mmd_material_basic_data
            {where_sql}
        """
        data_list = dbh.query_sql(base_sql)
        CODE_GROUP_MAP = {
            d["mat_code"]: {
                "mat_group": d["mat_group"],
                "uf_pkg": d["uf_pkg"],
                "mat_type": d["mat_type"]
            }
            for d in data_list
        }

    # 加载t_batch_number表的字段名称、字段类型、字段长度,方便后续数据校验
    # DATABASE = dbh.get_database_name()
    # data_list = dbh.query_sql(f"""
    #     SELECT
    #         COLUMN_NAME AS 'field_name',
    #         COLUMN_COMMENT AS 'field_desc',
    #         DATA_TYPE AS 'field_type',
    #         CHARACTER_MAXIMUM_LENGTH AS 'field_length',
    #         NUMERIC_PRECISION AS 'field_decimal_total',
    #         NUMERIC_SCALE AS 'field_decimal_length'
    #         FROM INFORMATION_SCHEMA.COLUMNS
    #         WHERE TABLE_SCHEMA = '{DATABASE}'
    #     AND TABLE_NAME = 't_batch_number'
    # """)
    # for each in data_list:
    #     if each["field_name"] in ["id", "create_time", "update_time", "create_id", "update_id"]:
    #         continue
    #     CHECK_FIELD_MAP[each["field_name"]] = {
    #         "description": each["field_desc"],  # 字段中文描述
    #         "type": each["field_type"],  # 字段类型
    #         "lenth": each["field_length"],  # varchar字段类型长度
    #         "decimal_total": each["field_decimal_total"],  # 数字类型整体长度
    #         "decimal_length": each["field_decimal_length"]  # 数字类型小数位长度
    #     }
    DATABASE = dbh.get_columns_by_table("t_batch_number")
    
    def convert_field_mapping_v2(DATABASE):
        return [
            {
                "field_name": f['name'],
                "field_desc": f['comment'],
                "field_type": f['type'].split('(')[0] if '(' in f['type'] else f['type'],
                "field_length": f.get('length', 0),
                "field_decimal_total": f.get('precision', 0),
                "field_decimal_length": f.get('scale', 0)
            }
            for f in DATABASE
            if f['name'] not in ["id", "create_time", "update_time", "create_id", "update_id"]
        ]
    
    data_list = convert_field_mapping_v2(DATABASE)
    # 将转换后的数据存入CHECK_FIELD_MAP
    for each in data_list:
        CHECK_FIELD_MAP[each["field_name"]] = {
            "description": each["field_desc"],
            "type": each["field_type"],
            "lenth": each["field_length"],
            "decimal_total": each["field_decimal_total"],
            "decimal_length": each["field_decimal_length"]
        }

    # 加载uf_ZT04 和 lot_no 的映射关系
    if not uf_ZT04_list:
        ZT04_LOT_MAP = {}
    else:
        if len(uf_ZT04_list) == 1:
            where_sql = f" WHERE uf_ZT04 = '{uf_ZT04_list[0]}'"
        else:
            where_sql = " WHERE uf_ZT04 IN (" + ",".join(f"'{x}'" for x in uf_ZT04_list) + ")"
        base_sql = f"""
            SELECT uf_ZT04, uf_lot_no
            FROM ut_chipone_foundry_lot
            {where_sql}
        """
        data_list = dbh.query_sql(base_sql)
        ZT04_LOT_MAP = {
            d["uf_ZT04"]: d["uf_lot_no"]
            for d in data_list
        }

    # 加载po_sn 和 wo_type 的映射关系
    # # print("po_sn_list:", po_sn_list)
    if not po_sn_list:
        PO_WO_MAP = {}
    else:
        if len(po_sn_list) == 1:
            where_sql = f" WHERE po_sn = '{po_sn_list[0]}'"
        else:
            where_sql = " WHERE po_sn IN (" + ",".join(f"'{x}'" for x in po_sn_list) + ")"
        base_sql = f"""
            SELECT po_sn, wo_type
            FROM t_po_header
            {where_sql}
        """
        # print("po_sn_sql:", base_sql)
        data_list = dbh.query_sql(base_sql)
        PO_WO_MAP = {
            d["po_sn"]: d["wo_type"]
            for d in data_list
        }

    # print("数据预加载耗时:", time.time() - start_time)


def sql_literal(val):
    if val is None:
        return "NULL"
    if isinstance(val, (int, float)):
        return str(val)
    # 字符串：转义单引号
    return "'" + str(val).replace("'", "''") + "'"


def load_batch_sn(data_list, dh, chunk_size=500):
    start_time = time.time()
    global BATCH_NUMBER_MAP

    mat_code_map = defaultdict(list)
    for row in data_list:
        mat_code = row.get("mat_code")
        if mat_code:
            mat_code_map[mat_code].append(row)

    for mat_code, datas in mat_code_map.items():
        info = CODE_GROUP_MAP.get(mat_code)
        if not info:
            continue

        mat_group = info["mat_group"]
        if mat_group == "3008":
            continue
        if "COF" in info["uf_pkg"] and mat_group == "2001":
            mat_group = "2001COF"
        if info["mat_type"] == "ZIP1" and mat_group == "4001":
            mat_group = "4001ZIP"

        select_fields = GROUP_SELECT_FIELD.get(mat_group)
        if not select_fields:
            continue

        select_field_sql = ",".join(select_fields)

        # 去重
        where_values = list({
            tuple(data.get(field) for field in select_fields)
            for data in datas
        })

        # 🔥 分批，防 SQL 过长
        for i in range(0, len(where_values), chunk_size):
            chunk = where_values[i:i + chunk_size]

            in_sql = ",".join(
                f"({','.join(sql_literal(v) for v in vals)})"
                for vals in chunk
            )

            sql = f"""
                SELECT mat_code, {select_field_sql}, batch_sn
                FROM t_batch_number
                WHERE mat_code = {sql_literal(mat_code)}
                  AND ({select_field_sql}) IN ({in_sql})
            """

            rows = dh.query_sql(sql)

            for row in rows:
                key = tuple(row[field] for field in select_fields)
                BATCH_NUMBER_MAP[(mat_code, key)] = row["batch_sn"]

    # print(f"load_batch_sn cost: {time.time() - start_time:.4f}s")


def generate_batch_number(data_list, mode=False):
    """
         - 参数说明
            -data_list: [
                {
                    "mat_code":"物料编码(必填)",
                    "lot_no":"制造批号(选填)",
                    "wafer_id":"制造序号(选填)",
                    "batch_type":"批次类型(选填)",
                    "uf_quality_type":"品质类型(选填)",
                    "uf_ZT25":"封装订单号(选填)",
                    "uf_ZT18":"生产周(选填)",
                    "receive_date":"收货日期(选填)",
                    "uf_runcard":"Runcard(选填)",
                    "uf_ZT04":"晶圆批次(Foundry Lot NO)(选填)",
                    "uf_ZT59":"FT订单号(选填)",
                    "uf_ZT07":"BIN(选填)",
                    "uf_ZT60":"PK订单号(选填)",
                    "uf_box_no":"箱号(选填)",
                    "vendor_batch":"供应商批次(选填)",
                    "uf_electroplating_date":"电镀日期(选填)"
                }
            ]
            - mode : 批次号存储模式,True存储其他相关字段,False只保留物料编码和批次号
        注: 上述字段并不是每个字段都必填,根据物料对应物料组来决定那些字段必填,此处可以通过返回的报错信息定位到缺失那个字段
    """
    print("准备进行批次号生成数据:", data_list)
    # 先进行数据预加载
    mat_code_list, uf_ZT04_list, po_sn_list = [], [], []

    for each in data_list:
        mat_code_list.append(each["mat_code"])
        if each.get("uf_ZT04", ""):
            uf_ZT04_list.append(each["uf_ZT04"])
        if each.get("po_sn", ""):
            po_sn_list.append(each["po_sn"])
    mat_code_list = list(set(mat_code_list))
    uf_ZT04_list = list(set(uf_ZT04_list))
    po_sn_list = list(set(po_sn_list))
    load_data(mat_code_list, uf_ZT04_list, po_sn_list)

    # 进行数据预校验,不合格直接返回
    is_status, is_msg = check_field(data_list)
    user_id = sh.getEnv(EnvKeys.user_id)
    if not is_status:
        print("返回code:", 500)
        print("返回msg:", is_msg)
        print("返回数据:", data_list)
        return 500, is_msg, data_list
    try:
        # 进行lot_no数据填充
        is_status, is_msg = parse_lot_data_list(data_list, user_id)
        if not is_status:
            print("返回code:", 500)
            print("返回msg:", is_msg)
            print("返回数据:", data_list)
            return 500, is_msg, data_list
    except Exception as e:
        print("当前直接报错.....")
        raise ValueError(e)

    # 进行数据分组
    result = group_material_data(data_list)

    # 进行数据预加载,
    load_batch_sn(data_list, DbHelper())

    # 开始进行批次号生成
    batch_insert_data, batch_special_data, return_data = gen_batch_sn(result, user_id)
    # print("当前未进行批量保存总用时:", time.time() - gen_start_time)
    u_time = time.time()
    code, msg, batch_sn_ls = CreateBatchDataBatch(batch_insert_data, DbHelper())
    if code != 200:
        # 部分批次号插入异常
        for each in return_data:
            if each["batch_sn"] not in batch_sn_ls:
                each["batch_status"] = "E"
                each["check_info"] = "批次号插入异常"
        return code, msg, return_data
    # 特殊批次保存
    u_time = time.time()
    insert_special_batch(batch_special_data, user_id)
    # 批次号流水表更新
    update_batch_number_log(GEN_BATCH_LIST, user_id)
    print("code:", code)
    print("msg:", msg)
    print("预期返回数据:", return_data)
    return code, msg, return_data


def insert_special_batch(batch_special_data, user_id):
    if not batch_special_data:
        return
    values_sql = []
    for item in batch_special_data:
        mat_code = item["mat_code"]
        values_sql.append(
            f"('{mat_code}', '9999999999', '{user_id}', '{user_id}')"
        )

    values_part = ",\n".join(values_sql)
    dbh.exec_sql(f"""
        INSERT INTO t_batch_number(
            mat_code,
            batch_sn,
            create_id,
            update_id
        )
        VALUES
        {values_part}
        ON DUPLICATE KEY UPDATE
            update_id = VALUES(update_id)
    """)
    dbh.dbCommit()


def gen_batch_sn(data_list, user_id):
    global GEN_BATCH_LIST
    gen_start_time = time.time()
    db = DbHelper()

    batch_insert_data = []
    batch_special_data = []
    return_data = []

    for datas in data_list:
        # print("datas:", datas)
        item = datas[0]
        mat_code = item["mat_code"]

        mat_group_config = CODE_GROUP_MAP.get(mat_code, {})
        mat_group = mat_group_config.get("mat_group", "")
        uf_pkg = mat_group_config.get("uf_pkg", "")
        mat_type = mat_group_config.get("mat_type", "")
        insert_status = False
        if "COF" in uf_pkg and mat_group == "2001":
            mat_group = "2001COF"

        # print("mat_group:", mat_group)
        # print("uf_pkg:", uf_pkg)
        # 🔵 特殊客户组
        if mat_group == "3008":
            for each in datas:
                each.update({
                    "batch_sn": "9999999999",
                    "batch_status": "S",
                    "check_info": "成功"
                })
                return_data.append(each)

            batch_special_data.append(item)
            continue
        if "COG" in uf_pkg and mat_group == "2001":
            mat_group = "2001COG"
        if mat_type == "ZIP1" and mat_group == "4001":
            mat_group = "4001ZIP"
        if mat_group in ("2001COG", "2011", "3001", "3006", "3007", "3099", "4001"):
            for each in datas:
                # print("======================")
                # print(each)
                batch_sn = generate_batch_num(mat_code, current_date, db, user_id)
                # print("batch_sn:", batch_sn)
                each.update({
                    "batch_sn": batch_sn,
                    "batch_status": "S",
                    "check_info": "成功"
                })

                GEN_BATCH_LIST.append(
                    {
                        "mat_code": mat_code,
                        "date": current_date,
                        "batch_sn": batch_sn
                    }
                )
                # print("each:", each)
                # print("===================")
                batch_insert_data.append(each)
                return_data.append(each)
            continue

        # 🔵 普通客户组 —— 用 MAP
        select_fields = GROUP_SELECT_FIELD[mat_group]

        key = tuple(item.get(field) for field in select_fields)

        batch_sn = BATCH_NUMBER_MAP.get((mat_code, key))

        if not batch_sn:
            insert_status = True
            batch_sn = generate_batch_num(mat_code, current_date, db, user_id)
            GEN_BATCH_LIST.append(
                {
                    "mat_code": mat_code,
                    "date": current_date,
                    "batch_sn": batch_sn
                }
            )
        for each in datas:
            each.update({
                "batch_sn": batch_sn,
                "batch_status": "S",
                "check_info": "成功"
            })
            return_data.append(each)
        if insert_status:
            batch_insert_data.append(item)

    # print("批次号生成用时:", time.time() - gen_start_time)
    return batch_insert_data, batch_special_data, return_data


def parse_lot_data_list(data_list, user_id):
    """
    对一些lot_no值为空的数据进行补充
    """
    global ZT04_LOT_MAP
    lot_start_time = time.time()
    is_status = True
    is_msg = ""
    for each in data_list:
        if not is_status:
            each["check_info"] = ""
            each["batch_sn"] = ""
            each["batch_status"] = ""
            continue
        # 20250105 物料组以3或4开头,不需要补充lot_no
        mat_group_config = CODE_GROUP_MAP.get(each["mat_code"], {})
        mat_group = mat_group_config.get("mat_group", "")
        uf_pkg = mat_group_config.get("uf_pkg", "")
        mat_type = mat_group_config.get("mat_type", "")
        if "COG" in uf_pkg and mat_group == "2001":
            mat_group = "2001COG"
        if mat_type == "ZIP1" and mat_group == "4001":
            mat_group = "4001ZIP"
        # print("lot_no_mat_group:", mat_group)
        if mat_group in ("2011", "3001", "3005", "3006", "3007", "3008", "3099", "4001", "2001COG"):
            each.update({
                "check_info": "",
                "batch_sn": "",
                "batch_status": ""
            })
            continue

        if not each.get("lot_no", ""):
            wo_type = PO_WO_MAP.get(each["po_sn"], "")
            if not wo_type:
                is_status = False
                is_msg = "制造批号为空时,采购订单编号必填且已存在"
                each["check_info"] = "制造批号为空时,采购订单编号必填且已存在;"
                each["batch_sn"] = ""
                each["batch_status"] = "E"
                continue
            elif wo_type not in ["MP", "RD"]:
                is_status = False
                is_msg = "制造批号为空时,采购订单编号对应工单类型应为MP或RD;"
                each["check_info"] = "制造批号为空时,采购订单编号对应工单类型应为MP或RD;"
                each["batch_sn"] = ""
                each["batch_status"] = "E"
                continue

            if wo_type.upper() == "MP":
                start_batch_sn = "D"
            else:
                start_batch_sn = "E"

            lot_no = ZT04_LOT_MAP.get(each["uf_ZT04"], "")
            if not lot_no:
                lot_no = generate_lot_num(each["uf_ZT04"], user_id)
            ZT04_LOT_MAP[each["uf_ZT04"]] = lot_no
            each["lot_no"] = start_batch_sn + lot_no
    # print("lot_no数据补充用时:", time.time() - lot_start_time)
    return is_status, is_msg


def check_field(data_list):
    """
    遍历数据,校验内置数据是否合法
    - 参数列表
        data_list: []
    - 返回值
        is_status: True/False 数据校验状态
        is_msg: 详细报错信息
    """
    check_start_time = time.time()
    is_status = True
    is_msg = ""
    for item in data_list:
        if not is_status:
            item["check_info"] = ""
            item["batch_sn"] = ""
            item["batch_status"] = ""
            continue
        status, check_info = validate_data_items_enhanced(item)
        if not status:
            is_status = False
            is_msg = check_info
            item["check_info"] = check_info
            item["batch_sn"] = ""
            item["batch_status"] = "E"
        else:
            item["check_info"] = ""
            item["batch_sn"] = ""
            item["batch_status"] = ""
    # print("数据长度、类型、必填项校验用时:", time.time() - check_start_time)
    return is_status, is_msg


def validate_data_items_enhanced(data_item):
    """
    校验数据是否合法
    - 参数
        {
            "mat_code":"xxxx", ...
        }
    - 返回值
        is_status: True/False 返回校验结果
        check_info: "成功"/"报错信息" 返回详细信息
    """
    is_status = True
    field_errors = []

    # 先判断是否在对应物料组中,并且相关必填字段是否完整
    mat_group_config = CODE_GROUP_MAP.get(data_item.get("mat_code", ""), {})
    mat_group = mat_group_config.get("mat_group", "")
    mat_type = mat_group_config.get("mat_type", "")
    if not mat_group:
        return False, "当前物料编码字段未找到对应物料组"
    uf_pkg = mat_group_config.get("uf_pkg", "")
    if "COF" in uf_pkg and mat_group == "2001":
        mat_group = "2001COF"
    if mat_type == "ZIP1" and mat_group == "4001":
        mat_group = "4001ZIP"
    if "COG" in uf_pkg and mat_group == "2001":
        mat_group = "2001COG"

    if mat_group not in EXITS_GROUP:
        return False, "当前物料组不在可选范围内"
    required_fields = GROUP_REQUIRD_FIELD.get(mat_group, [])
    required_lot_fields = []
    # 20260105 物料组以3或4开头时,无需补充lot_no
    if mat_group not in ("2011", "3001", "3005", "3006", "3007", "3008", "3099", "4001", "2001COG"):
        required_lot_fields = ["uf_ZT04", "po_sn"]
    # if not (mat_group.startswith("3") or mat_group.startswith("4")):

    for field_name, field_value in data_item.items():
        field_config = CHECK_FIELD_MAP.get(field_name, "")

        if not field_config:
            continue

        field_descript = field_config.get("description", field_name)
        field_type = field_config.get("type", "").lower()
        if field_name in required_fields and not field_value:
            field_errors.append(f"{field_descript}必填;")
        if field_name in required_lot_fields and not field_value:
            field_errors.append(f"制造批号为空时,{field_descript}必填;")
        try:
            if not field_value:
                continue
            if field_type in ["varchar", "char"]:
                # 字符串类型
                if not isinstance(field_value, str):
                    field_errors.append(f"{field_descript}应为字符串类型")
                else:
                    max_length = field_config.get("lenth")
                    if max_length and len(field_value) > max_length:
                        field_errors.append(f"{field_descript}长度不能超过{max_length}字符")

            elif field_type in ["int", "integer"]:
                # 整数类型
                if not isinstance(field_value, int):
                    try:
                        int(field_value)
                    except (ValueError, TypeError):
                        field_errors.append(f"{field_descript}应为整数")

            elif field_type in ["decimal", "numeric"]:
                # 精确小数
                try:
                    decimal_value = float(field_value)
                    total_digits = field_config.get("decimal_total", 0)
                    decimal_places = field_config.get("decimal_length", 0)

                    # 检查总位数和小数位数
                    str_value = str(decimal_value).replace('-', '')  # 去掉负号
                    if '.' in str_value:
                        integer_part, decimal_part = str_value.split('.')
                        total_actual = len(integer_part) + len(decimal_part)
                        if total_digits and total_actual > total_digits:
                            field_errors.append(f"{field_descript}总位数不能超过{total_digits}")
                        if decimal_places and len(decimal_part) > decimal_places:
                            field_errors.append(f"{field_descript}小数位不能超过{decimal_places}")
                except (ValueError, TypeError):
                    field_errors.append(f"{field_descript}应为数字格式")

            elif field_type == "float":
                # 浮点数
                try:
                    float(field_value)
                except (ValueError, TypeError):
                    field_errors.append(f"{field_descript}应为浮点数格式")

            elif field_type == "date":
                # 日期类型 - 支持多种格式
                if not isinstance(field_value, (str, int)):
                    field_errors.append(f"{field_descript}应为日期字符串或数字")
                else:
                    date_str = str(field_value)
                    if not _is_valid_date(date_str):
                        field_errors.append(
                            f"{field_descript}格式不正确")

            elif field_type == "time":
                # 时间类型 - 支持多种格式
                if not isinstance(field_value, (str, int)):
                    field_errors.append(f"{field_descript}应为时间字符串或数字")
                else:
                    time_str = str(field_value)
                    if not _is_valid_time(time_str):
                        field_errors.append(f"{field_descript}格式不正确")

            elif field_type == "datetime":
                # 日期时间类型 - 支持多种格式
                if not isinstance(field_value, (str, int)):
                    field_errors.append(f"{field_descript}应为日期时间字符串或数字")
                else:
                    datetime_str = str(field_value)
                    if not _is_valid_datetime(datetime_str):
                        field_errors.append(
                            f"{field_descript}格式不正确")

        except Exception as e:
            field_errors.append(f"{field_descript}校验异常: {str(e)}")

    check_info = "; ".join(field_errors) if field_errors else "成功"
    if check_info != "成功":
        is_status = False

    return is_status, check_info


def _is_valid_date(date_str):
    """
    检查日期格式是否有效
    支持格式:
    - YYYY-MM-DD (2024-01-15)
    - YYYYMMDD (20240115)
    - YYYY/MM/DD (2024/01/15)
    """
    # 正则表达式匹配常见日期格式
    patterns = [
        r'^\d{4}-\d{2}-\d{2}$',  # YYYY-MM-DD
        r'^\d{8}$',  # YYYYMMDD
        r'^\d{4}/\d{2}/\d{2}$',  # YYYY/MM/DD
    ]

    for pattern in patterns:
        if re.match(pattern, date_str):
            try:
                # 尝试解析日期
                if pattern == r'^\d{4}-\d{2}-\d{2}$':
                    datetime.strptime(date_str, '%Y-%m-%d')
                elif pattern == r'^\d{8}$':
                    datetime.strptime(date_str, '%Y%m%d')
                elif pattern == r'^\d{4}/\d{2}/\d{2}$':
                    datetime.strptime(date_str, '%Y/%m/%d')
                return True
            except ValueError:
                continue

    return False


def _is_valid_time(time_str):
    """
    检查时间格式是否有效
    支持格式:
    - HH:MM:SS (14:30:25)
    - HHMMSS (143025)
    - HH:MM (14:30)
    - HHMM (1430)
    """
    # 正则表达式匹配常见时间格式
    patterns = [
        r'^\d{2}:\d{2}:\d{2}$',  # HH:MM:SS
        r'^\d{6}$',  # HHMMSS
        r'^\d{2}:\d{2}$',  # HH:MM
        r'^\d{4}$',  # HHMM
    ]

    for pattern in patterns:
        if re.match(pattern, time_str):
            try:
                # 尝试解析时间
                if pattern == r'^\d{2}:\d{2}:\d{2}$':
                    datetime.strptime(time_str, '%H:%M:%S')
                elif pattern == r'^\d{6}$':
                    datetime.strptime(time_str, '%H%M%S')
                elif pattern == r'^\d{2}:\d{2}$':
                    datetime.strptime(time_str, '%H:%M')
                elif pattern == r'^\d{4}$':
                    datetime.strptime(time_str, '%H%M')
                return True
            except ValueError:
                continue

    return False


def _is_valid_datetime(datetime_str):
    """
    检查日期时间格式是否有效
    支持格式:
    - YYYY-MM-DD HH:MM:SS (2024-01-15 14:30:25)
    - YYYYMMDDHHMMSS (20240115143025)
    - YYYY/MM/DD HH:MM:SS (2024/01/15 14:30:25)
    """
    # 正则表达式匹配常见日期时间格式
    patterns = [
        r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$',  # YYYY-MM-DD HH:MM:SS
        r'^\d{14}$',  # YYYYMMDDHHMMSS
        r'^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}$',  # YYYY/MM/DD HH:MM:SS
    ]

    for pattern in patterns:
        if re.match(pattern, datetime_str):
            try:
                # 尝试解析日期时间
                if pattern == r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$':
                    datetime.strptime(datetime_str, '%Y-%m-%d %H:%M:%S')
                elif pattern == r'^\d{14}$':
                    datetime.strptime(datetime_str, '%Y%m%d%H%M%S')
                elif pattern == r'^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}$':
                    datetime.strptime(datetime_str, '%Y/%m/%d %H:%M:%S')
                return True
            except ValueError:
                continue

    return False


def generate_lot_num(ZT04, user_id):
    """新增一条uf_ZT04和lot_no的映射关系"""
    redis_key = "ut_chipone_foundry_lot"
    with redis_lock(f"gln_{redis_key}"):
        counter_exits = redis_handler.redis_execute(f"EXISTS {redis_key}")

        if not int(counter_exits):
            set_count_key = redis_handler.redis_string(f"SET {redis_key} 0")

        current_number = int(redis_handler.redis_execute(f"INCR {redis_key}"))
        current_str = normalize_serial_lot(str(current_number))
        dbh.exec_sql(
            f"""INSERT INTO ut_chipone_foundry_lot (uf_ZT04, uf_lot_no, create_id, update_id)VALUES('{ZT04}', '{current_str}', '{user_id}', '{user_id}')"""
        )
        dbh.dbCommit()
    return current_str


def normalize_serial_lot(serial: str) -> str:
    """
    将流水号统一为 lot_no 格式（不递增，仅转换）

    规则：
    - <= 99999          -> 保持 5 位数字
    - 100000 ~ 199999   -> A0001 ~ A9999
    - 200000 ~ 299999   -> B0001 ~ B9999
    - ...
    - 269999            -> Z9999
    - 超过              -> 报错
    """
    if not serial:
        return "00001"

    serial = str(serial).upper().strip()

    # 已是字母前缀格式，直接返回
    if re.fullmatch(r"[A-Z]\d{4}", serial):
        return serial

    # 必须是纯数字
    if not serial.isdigit():
        raise ValueError(f"非法流水号格式: {serial}")

    num = int(serial)

    # 1️⃣ 纯数字 <= 99999
    if num <= 99999:
        return f"{num:05d}"

    # 2️⃣ 转换为 字母 + 4 位数字
    offset = num - 100000
    prefix_index = offset // 10000
    suffix = offset % 10000 + 1

    if prefix_index >= 26 or suffix > 9999:
        raise ValueError(f"流水号超出最大范围: {serial}")

    prefix = chr(ord("A") + prefix_index)
    return f"{prefix}{suffix:04d}"


def group_material_data(data):
    """
    逻辑：
    1. 基于 mat_code 分组

    3. 根据 group_select_fields 找到对应要比对的字段
    4. 同字段值相同的为一组
    """
    # Step 1: 先按 mat_code 分组
    group_start_tiem = time.time()
    code_groups = defaultdict(list)
    for row in data:
        mat_code = row.get("mat_code", "UNKNOWN")
        code_groups[mat_code].append(row)

    final_groups = []

    # Step 2: 对每个 mat_code 进行处理
    for mat_code, rows in code_groups.items():
        group_info = CODE_GROUP_MAP.get(mat_code)

        # 获取物料组
        if group_info and group_info.get("mat_group") in EXITS_GROUP:
            mat_group = group_info["mat_group"]
        else:
            mat_group = "UNKNOWN"

        if "COF" in group_info["uf_pkg"] and mat_group == "2001":
            mat_group = "2001COF"
        if "COG" in group_info["uf_pkg"] and mat_group == "2001":
            mat_group = "2001COG"
        if group_info["mat_type"] == "ZIP1" and mat_group == "4001":
            mat_group = "4001ZIP"

        # 找分组需要对比的字段
        compare_fields = GROUP_SELECT_FIELD.get(mat_group, [])

        # 没有字段规则 => 整体为一组
        if not compare_fields:
            final_groups.append(rows)
            continue

        # Step 3: 按字段值进行二次分组
        field_groups = defaultdict(list)
        for row in rows:
            key = tuple(row.get(f) for f in compare_fields)
            field_groups[key].append(row)

        final_groups.extend(field_groups.values())
    # print("数据分组用时:", time.time() - group_start_tiem)
    return final_groups


def generate_batch_num(mat_code, uf_date, db_helper, user_id):
    redis_counter_key = f"generate_batch_num:{mat_code}_{uf_date}"
    with redis_lock(f"generate_batch_init:{mat_code}"):
        counter_exits = redis_handler.redis_execute(f"EXISTS {redis_counter_key}")

        if not int(counter_exits):
            set_count_key = redis_handler.redis_string(f"SET {redis_counter_key} 0 EX 90000")

        current_number = int(redis_handler.redis_execute(f"INCR {redis_counter_key}"))
        current_str = num_to_serial(current_number)
        # exec_sql = f"""
        #             INSERT INTO ut_batch_number_log(
        #                 uf_mat_code,
        #                 uf_date_format,
        #                 uf_serial_qty,
        #                 uf_current_value,
        #                 create_id,
        #                 update_id
        #             )
        #             VALUES ('{mat_code}', '{uf_date}', '4','{current_str}', '{user_id}', '{user_id}')
        #             ON DUPLICATE KEY UPDATE
        #                 uf_current_value = VALUES(uf_current_value),
        #                 update_id = VALUES(update_id)
        # """
        # db_helper.exec_sql(exec_sql, logflg=False)
        # db_helper.dbCommit()

    return f"{uf_date}{current_str}"


def num_to_serial(num: int) -> str:
    if num <= 9999:
        return f"{num:04d}"
    num -= 10000
    prefix_index = num // 999
    suffix = num % 999 + 1
    if prefix_index >= 26:
        raise ValueError("流水号已达最大值: Z999")
    prefix = chr(ord('A') + prefix_index)
    return f"{prefix}{suffix:03d}"


def batch_data_check(db, data):
    from dateutil import parser

    vendor_sql = """
    select vendor_code from t_bpv_vendor_basic_data
    """
    vendor_data = db.query_sql(vendor_sql)

    vendor_data_ls = [d['vendor_code'] for d in vendor_data]

    batch_sn_sql = """select mat_code,batch_sn from t_batch_number 
    """
    batch_sn_data = db.query_sql(batch_sn_sql)

    batch_sn_dic = defaultdict(set)

    for i in batch_sn_data:
        batch_sn_dic[i['mat_code']].add(i['batch_sn'])

    msg = ""

    if isinstance(data, dict):
        data = [data]

    for params in data:
        mat_code = params.get('mat_code', '')
        if not mat_code:
            msg += '物料编码不能为空,'
            continue
        else:

            batch_sn = params.get('batch_sn', '')
            tag = params.get('_tag_', 'insert')
            if batch_sn and tag == 'insert':
                if batch_sn in batch_sn_dic.get(mat_code, []):
                    msg += '物料{}-批次号{}已存在不可新增,'.format(mat_code, batch_sn)
                    continue
            vendor_code = params.get('vendor_code', '')
            if vendor_code:
                if not vendor_code in vendor_data_ls:
                    msg += '{}供应商编码不在系统内,'.format(vendor_code)
                    continue
            property = params.get('property', [])
            if property:
                for i in property:
                    field_code = i.get('field_code', '')
                    field_type = i.get('field_type', '')
                    field_mark = i.get('field_mark', '')
                    field_value = i.get('field_value', '')
                    field_value_from = i.get('field_value_from', '')
                    field_value_to = i.get('field_value_to', '')

                    if field_code and field_type and field_mark:
                        if field_type not in ['int', 'date', 'time', 'decimal', 'varchar']:
                            msg += "附加特性值 字段类型只能选择'int'/'date'/'time'/'decimal'/'varchar',"
                            break
                        if field_mark not in ['0', '1']:
                            msg += "附加特性值 字段标识只能填'0','1' "
                            break
                        if field_type == 'decimal':
                            try:
                                if field_value:
                                    float(field_value)
                                if field_value_from:
                                    float(field_value_from)
                                if field_value_to:
                                    float(field_value_to)
                            except Exception as e:
                                msg += "{} 输入类型错误-{}".format(field_code, field_type)
                        elif field_type == 'int':

                            try:
                                if field_value:
                                    int(field_value)
                                if field_value_from:
                                    int(field_value_from)
                                if field_value_to:
                                    int(field_value_to)
                            except Exception as e:
                                msg += "{} 输入类型错误-{}".format(field_code, field_type)

                        elif field_type == 'date':
                            try:
                                if field_value:
                                    parser.parse(field_value).strftime("%Y-%m-%d")
                                if field_value_from:
                                    parser.parse(field_value_from).strftime("%Y-%m-%d")
                                if field_value_to:
                                    parser.parse(field_value_to).strftime("%Y-%m-%d")
                            except Exception as e:
                                msg += "{} 输入类型错误-{}".format(field_code, field_type)
                        elif field_type == 'time':
                            try:
                                if field_value:
                                    parser.parse(field_value).strftime("HH:MM:SS")
                                if field_value_from:
                                    parser.parse(field_value_from).strftime("HH:MM:SS")
                                if field_value_to:
                                    parser.parse(field_value_to).strftime("HH:MM:SS")
                            except Exception as e:
                                msg += "{} 输入类型错误-{}".format(field_code, field_type)


                    else:
                        msg += "附加特性值 字段值 字段类型 字段标识 必填,"
                        break
    if msg:
        check_res = False
        msg = msg.strip(',')
    else:
        check_res = True
    # check_res, msg = enhance_check(db, data, check_res, msg)
    return check_res, msg


def CreateBatchDataBatch(params, db=None):
    """
    创建批次主数据
    物料编码必填 user_id必填
    其他选填   批次编号不传默认为空会自动生成批次号 批次属性数据不传默认为空
    选填请使用键值对方式传入   如property=[]
    [{
    mat_code	                 物料编码
    user_id                      创建人id
    batch_sn	                 批次编号
    property                     批次属性数据
     [
     {
        "field_code": "color",   字段代码
        "field_name": "颜色",     字段名称
        "field_value": "",       字段值
        "field_value_from": "red", 字段值从
        "field_value_to": "black", 字段值到
        "field_type": "varchar",   字段类型
        "field_class": "mat_ty",   字段分组
        "field_mark": "0"          字段标识
    }
    ]
    maturity_date	             到期日期
    # expiration_day	             到期天数   int
    packing_id	                 包装编码
    packing_seal_date	         包装日期
    production_date	             生产日期
    receive_date	             收货日期
    vendor_batch	             供应商批次
    vendor_code	                 供应商
    wafer_id	                 制造序号
    cp_vendor	                 制造商编码
    grade1	                     等级1
    grade2	                     等级2
    grade3	                     等级3
    lot_no	                     制造批号
    batch_type	                 批次类型
    batch_type_description	     批次类型描述
    extended_batch_attributes1	 附加属性1
    extended_batch_attributes2	 附加属性2
    extended_batch_attributes3	 附加属性3
    extended_batch_date1	     附加日期1
    extended_batch_date2	     附加日期2
    extended_batch_date3	     附加日期3
    bin	                         档位
    note	                     备注
    }]
    :return:
    code
    msg
    batch_sn
    """
    code = 200
    msg = "成功"
    new_db_flag = False
    if not db:
        new_db_flag = True
        db = DbHelper()
    # 校验
    u_time = time.time()
    if not params:
        return code, msg, ""
    check_res, msg = batch_data_check(db, params)
    # print("保存批量校验用时:", time.time() - u_time)

    if not check_res:
        return 500, msg, ''
    sh = SystemHelper()
    user_id = sh.getEnv(EnvKeys.user_id)
    batch_sn_ls = []
    u_time = time.time()
    for item in params:
        batch_sn = item.get('batch_sn', '')
        mat_code = item.get('mat_code', '')
        if batch_sn == '':
            code, msg, batch_sn = CreateBatchSn(mat_code, db)

            if code == 500:
                return code, msg, batch_sn
            else:
                batch_sn_ls.append(batch_sn)

        property = item.get('property', [])
        item['batch_sn'] = batch_sn
        if property:
            code, msg = BatchPropertyData(item, batch_sn, db, user_id)
    # print("保存处理特性值用时:", time.time() - u_time)
    u_time = time.time()
    # 分批插入,每次最多插入30条数据 20260127 防止长事务占用过多时间,导致数据库锁异常
    batch_size = 10
    total_count = len(params)
    batch_sn_ls = []
    # 新建一个数据表操作对象 20260127
    dbi = DbHelper()
    for i in range(0, total_count, batch_size):
        insert_batch = params[i:i+batch_size]
        try:
            status = dbi.batchInsertToDB('t_batch_number', insert_batch)
            if status < 0:
                # 适当跳出循环,直接返回异常
                code = 500
                msg = "批次号插入异常"
                break
            batch_sn_ls.extend([each["batch_sn"]] for each in insert_batch)
            dbi.dbCommit()
        except Exception as e:
            code = 500
            msg = "批次号插入异常"
            break
    
    # # 数据新增
    # status = db.batchInsertToDB('t_batch_number', params)
    # # print("保存数据用时:", time.time() - u_time)
    # if status < 0:
    #     code, msg = 500, '新增失败'
    # if new_db_flag:
    #     db.dbCommit()
    return code, msg, batch_sn_ls


def BatchPropertyData(params, batch_sn, db, user_id):
    mat_code = params.get("mat_code", '')
    property_data = params.get('property', [])
    time = params.get("time", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    code, msg = 200, '成功'
    # 删除批次属性
    property_data_all = []
    all_sql = []
    batchproperty_delete_sql = """delete from t_batch_additional_property where mat_code = '%s' and batch_sn = '%s'""" % (
        mat_code, batch_sn)
    for index, item in enumerate(property_data):
        item['batch_sn'] = batch_sn
        item['mat_code'] = mat_code
        item['create_id'] = user_id
        item['update_id'] = user_id
        item['field_value_int'] = ''
        item['field_value_int_from'] = 0
        item['field_value_int_to'] = 0
        item['field_value_date'] = ''
        item['field_value_date_from'] = ''
        item['field_value_date_to'] = ''
        item['field_value_time'] = ''
        item['field_value_time_from'] = ''
        item['field_value_time_to'] = ''
        item['field_value_decimal'] = 0
        item['field_value_decimal_from'] = 0
        item['field_value_decimal_to'] = 0
        if 'id' in item:
            item.pop('id')
        field_type = item.get('field_type', '')
        if field_type == 'int':
            item['field_value_int'] = item.get('field_value', 0)
            item['field_value_int_from'] = item.get('field_value_from', 0)
            item['field_value_int_to'] = item.get('field_value_to', 0)
            item['field_value'] = ''
            item['field_value_from'] = ''
            item['field_value_to'] = ''

        elif field_type == 'date':
            item['field_value_date'] = item.get('field_value', '')
            item['field_value_date_from'] = item.get('field_value_from', '')
            item['field_value_date_to'] = item.get('field_value_to', '')
            item['field_value'] = ''
            item['field_value_from'] = ''
            item['field_value_to'] = ''
        elif field_type == 'time':
            item['field_value_time'] = item.get('field_value', '')
            item['field_value_time_from'] = item.get('field_value_from', '')
            item['field_value_time_to'] = item.get('field_value_to', '')
            item['field_value'] = ''
            item['field_value_from'] = ''
            item['field_value_to'] = ''
        elif field_type == 'decimal':
            item['field_value_decimal'] = item.get('field_value', 0)
            item['field_value_decimal_from'] = item.get('field_value_from', 0)
            item['field_value_decimal_to'] = item.get('field_value_to', 0)
            item['field_value'] = ''
            item['field_value_from'] = ''
            item['field_value_to'] = ''
        elif field_type == 'varchar':
            item['field_value'] = item.get('field_value', '')
            item['field_value_from'] = item.get('field_value_from', '')
            item['field_value_to'] = item.get('field_value_to', '')
        else:
            continue
        property_data_all.append(item)
    all_sql.append(batchproperty_delete_sql)

    status = db.exec_sql(batchproperty_delete_sql)
    if status < 0:
        code = 500
        msg = '批量更新失败'
        return code, msg
    if property_data_all:
        # print(property_data_all)
        status = db.batchInsertToDB('t_batch_additional_property', property_data_all, printSql=True)
        if status < 0:
            code, msg = 500, '批次属性操作失败'
    return code, msg


def CreateBatchSn(mat_code, db):
    """
    自动创建批次编号
    批次编号 :前缀 + 连接符 + 日期 + 连接符 + 当前流水号 + 连接符 + 后缀
    :return:
    """
    mat_type_sql = """
    SELECT mat_code, mat_type
    from t_mmd_material_basic_data
    where mat_code = {}
    group by mat_code
    """.format(repr(mat_code))

    mat_type_data = db.query_sql(mat_type_sql)
    batch_sn = ''
    if not mat_type_data:
        code = 500
        msg = '此物料编码不存在'
    else:
        object_code = mat_type_data[0]['mat_type']
        serial_num_result = generate_serial_num('batch_code', object_code,
                                                db_helper=db)
        external_number = serial_num_result['external_number']
        batch_sn = serial_num_result['serial_num']

        if external_number == 1:
            code = 500
            msg = '必须外部给号'
        else:
            code = 200
            msg = '批次号创建成功'

    return code, msg, batch_sn,


def update_batch_number_log(data_list, user_id):
    """
    :param data_list: [{"mat_code":"物料编码", "date":"日期", "batch_sn":"批次号"}, ....]
    :param user_id: 操作人
    :return: True
    """
    result = {}

    for row in data_list:
        mat_code = row.get("mat_code")
        date = row.get("date")
        batch_sn = row.get("batch_sn")

        if not (mat_code and date and batch_sn):
            continue

        # 1. 计算流水号（去掉日期前缀）
        if not batch_sn.startswith(date):
            continue

        serial = batch_sn[len(date):]
        serial_num = serial_to_num(serial)

        # 2. 按物料取最大流水号
        if mat_code not in result:
            result[mat_code] = (date, serial_num)
            continue

        old_date, old_serial_num = result[mat_code]

        if date != old_date or serial_num > old_serial_num:
            result[mat_code] = (date, serial_num)

    if not result:
        return None

    # 3. 生成批量 INSERT SQL
    values_sql = []
    for mat_code, (date, serial_num) in result.items():
        current_str = num_to_serial(serial_num)
        values_sql.append(
            f"('{mat_code}', '{date}', '4', '{current_str}', '{user_id}', '{user_id}')"
        )

    values_part = ",\n".join(values_sql)

    sql = f"""
        INSERT INTO ut_batch_number_log(
            uf_mat_code,
            uf_date_format,
            uf_serial_qty,
            uf_current_value,
            create_id,
            update_id
        )
        VALUES
        {values_part}
        ON DUPLICATE KEY UPDATE
            uf_current_value = VALUES(uf_current_value),
            update_id = VALUES(update_id)
    """
    dhb = DbHelper()
    dhb.exec_sql(sql)
    return True


def serial_to_num(serial: str) -> int:
    """
    0001 -> 1
    9999 -> 9999
    A001 -> 10000
    Z999 -> 最大
    """
    if serial.isdigit():
        return int(serial)

    prefix = serial[0]
    suffix = int(serial[1:])

    prefix_index = ord(prefix) - ord('A')
    return 10000 + prefix_index * 999 + (suffix - 1)