#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@File    : ZZITF_MaterialMasterData.py
@explain : 物料主数据同步(数仓 -> 秘火)
@Author  : yang.zhang@dxdstech.com

  嵌套结构:
      {"data": [ {"basic":.., "plant":.., "financial":.., "cost":.., "uomconv":..}, ... ]}
  按 mat_code 是否已存在走 新增(A)/修改(B)
  双工厂(1000 + 100N) 各调一次 maintain_data(bapi) 落库
  流程: 查表(ZZEXT_PostgreSqlDB) -> 组结构 -> 调 bapi 存表
"""
import copy

from DbHelper import DbHelper
from DxBusinessDataConvertUtil import convert_material_unit_qty
from DxMaintainMaterialData import maintain_data
from ZZEXT_PostgreSqlDB import PostgreSQL

# ---------- 固定值 ----------
PLANT_NORMAL = "1000"    # 正常工厂
PLANT_CUSTODY = "100N"   # 客供料工厂

# ---------- 数仓源表 ----------
# (模拟占位, 真实表名确定后改这一处即可; 同步条件见 _query_source_data 的 WHERE)
SOURCE_WIDE_TABLE = "ads_dim_material_wide"



# ==================== 各视图字段(与接口结构 / xlsx 一致) ====================
# 数仓表列名暂按"目标字段同名"取值; 真实数仓表列名确定后, 改 _pick 的取值来源即可。

# 基本视图 t_mmd_material_basic_data
_BASIC_FIELDS = [
    "mat_code", "mat_description", "old_mat_code", "old_description",
    "basic_uom", "parallel_uom", "parallel_uom_mark", "capacity_dimension",
    "note", "mat_type1", "mat_type2", "mat_type3", "mat_type4",
]

# 工厂视图 t_mmd_material_plant_data
_PLANT_FIELDS = [
    "mat_code", "plant_code", "batch_mark", "pur_uom", "prod_uom",
    "source_mark", "safety_stock_quantity", "reorder_point", "pur_type",
    "shelf_life_days", "bulk_material",
]

# 财务视图 t_mmd_material_financial_data
_FINANCIAL_FIELDS = ["mat_code", "plant_code", "profit_center", "plant_val_class"]


# 成本视图 t_mmd_material_cost_data
_COST_FIELDS = [
    "mat_code", "plant_code", "cost_uom", "plant_val_mark", "version_val_mark",
    "batch_val_mark", "other_special_val_mark", "outsource_val_mark",
    "project_val_mark", "stor_loc_val_mark", "so_val_mark", "valgroup_value",
    "mat_cost_classify", "co_currency", "plan_cost_bc", "plan_cost_rate",
    "effective_start_date", "basic_currency", "price_control", "price_unit",
    "cost_lot", "special_pur_cc", "mat_consumption", "plan_cost_currency",
    "plan_price_unit", "wbs_elements",
]

# 单位换算 t_mmd_uom_conversion
_UOMCONV_FIELDS = [
    "mat_code", "primary_uom_qty", "primary_uom",
    "secondary_uom_qty", "secondary_uom",
]


# ==================== 工具: 表行 -> 嵌套结构 ====================
def _val(row, key):
    """取 row[key], None -> '' (接口结构里空值统一用空串)"""
    v = row.get(key)
    return "" if v is None else v


def _pick(row, fields):
    """从表行里按字段清单摘出一个视图 dict"""
    return {f: _val(row, f) for f in fields}


def _build_basic(row):
    """基本视图。note 兼容 save_mainmaterial_basic_data 读的 remarks(memo 长文本)"""
    basic = _pick(row, _BASIC_FIELDS)
    basic.setdefault("remarks", basic.get("note", ""))
    return basic


def _build_uomconv(row):
    """单位换算 -> 列表。主/辅单位都没有则不下发"""
    item = _pick(row, _UOMCONV_FIELDS)
    if not item.get("primary_uom") and not item.get("secondary_uom"):
        return []
    return [item]


def _flat_row_to_item(row):
    """表一行 -> 接口结构一个物料 {basic, plant, financial, cost, uomconv}。
    plant/financial/cost 是单元素列表(表一行一个物料, 每个视图一行);
    uomconv 按有无数据 0~N 行。
    """
    return {
        "basic": _build_basic(row),
        "plant": [_pick(row, _PLANT_FIELDS)],
        "financial": [_pick(row, _FINANCIAL_FIELDS)],
        "cost": [_pick(row, _COST_FIELDS)],
        "uomconv": _build_uomconv(row),
    }


# ==================== 查表(暂空) ====================
def _query_source_data(pg):
    """从ERP查数据，等待确认
    """
    sql = (
        "SELECT mat_code, mat_description, old_mat_code, old_description, basic_uom, "
        "       parallel_uom, parallel_uom_mark, capacity_dimension, note, "
        "       mat_type1, mat_type2, mat_type3, mat_type4, "
        "       plant_code, batch_mark, pur_uom, prod_uom, source_mark, "
        "       safety_stock_quantity, reorder_point, pur_type, shelf_life_days, bulk_material, "
        "       profit_center, plant_val_class, "
        "       cost_uom, plant_val_mark, version_val_mark, batch_val_mark, "
        "       other_special_val_mark, outsource_val_mark, project_val_mark, "
        "       stor_loc_val_mark, so_val_mark, valgroup_value, mat_cost_classify, "
        "       co_currency, plan_cost_bc, plan_cost_rate, effective_start_date, "
        "       basic_currency, price_control, price_unit, cost_lot, special_pur_cc, "
        "       mat_consumption, plan_cost_currency, plan_price_unit, wbs_elements, "
        "       primary_uom_qty, primary_uom, secondary_uom_qty, secondary_uom "
        "FROM {table} "
        # "WHERE <同步条件> "                     # <- 同步条件确定后取消此行注释即启用查询
        .format(table=SOURCE_WIDE_TABLE)
    )
    if "WHERE" not in sql.upper():   # WHERE 还注释着 = 同步条件未定, 暂不执行
        return []
    return pg.query(sql)


# ==================== 落库: 视图组装 & save (就地实现) ====================
def _escape_sql_text(value):
    """转义 SQL 文本里的反斜杠/单引号/双引号。"""
    if value is None:
        return ""
    return (str(value)
            .replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace('"', '\\"'))


def _fill_missing(target, source, fields):
    """target 里为空的字段用 source 回填(修改时保留库里已有值)。"""
    for f in fields:
        if not target.get(f):
            target[f] = source.get(f)


def _compute_mat_type(t1, t2, t4):
    """由前端物料类型标志推 SAP 物料类型 Z001~Z004。"""
    if t1 != "M":
        return "Z004" if t2 == "C" else "Z002"
    return "Z003" if t4 == "K" else "Z001"


def _get_bulk_material(db, plant_code, mat_group):
    """查物料组消耗标识; mat_consumption=='2' 视为散料, 返回 (bulk_material, mat_consumption)。"""
    rows = db.query_sql(
        "SELECT `mat_consumption` FROM `t_mmd_material_group_consumption` "
        "WHERE `plant_code` = '{}' AND `mat_group` = '{}'".format(plant_code, mat_group))
    mat_consumption = rows[0].get("mat_consumption") if rows else ""
    return (1 if mat_consumption == "2" else 0), mat_consumption


def _query_basic_existing(db, mat_code, with_parallel_uom=False):
    """查 t_mmd_material_basic_data 已有抬头(回填缺失字段用)。"""
    cols = "`process_code`, `mat_description`, `mat_type`, `mat_group`, `basic_uom`"
    if with_parallel_uom:
        cols += ", `parallel_uom`"
    rows = db.query_sql(
        "SELECT {} FROM `t_mmd_material_basic_data` WHERE `mat_code` = '{}'".format(cols, mat_code))
    return rows[0] if rows else None


def _fill_plant_row(row, plant_code, bulk_material=None, pur_type=None):
    """填工厂视图行。
    传 bulk_material -> 新增(补 pur_group/标识位, 可选 pur_type); 不传 -> 修改(只设 plant_code)。
    """
    row["plant_code"] = plant_code
    if bulk_material is not None:
        row["pur_group"] = "100"
        row["bulk_material"] = bulk_material
        row["source_mark"] = 0
        row["deleted_mark"] = 0
        row["lock_flag"] = 0
        if pur_type is not None:
            row["pur_type"] = pur_type
    return row


def _fill_cost_row(db, row, mat_code, plant_code, basic_uom, mat_consumption, full):
    """填成本视图行。
    full=True(新增): 补齐估值/货币/消耗标识, 并按基本单位换算计划价;
    full=False(修改): 仅补基本字段。price_control 缺失则回填。
    """
    row["plant_code"] = plant_code
    row["cost_uom"] = basic_uom
    row["plant_val_mark"] = 1
    row["price_unit"] = 1
    row["cost_lot"] = 1
    if full:
        row.update({
            "version_val_mark": 0, "batch_val_mark": 0, "other_special_val_mark": 0,
            "outsource_val_mark": 0, "project_val_mark": 0, "stor_loc_val_mark": 0,
            "so_val_mark": 0, "co_currency": "CNY", "basic_currency": "CNY",
            "plan_cost_currency": "CNY", "mat_consumption": mat_consumption,
        })
        _, _, qty = convert_material_unit_qty(
            mat_code, row.get("plan_price_unit"), basic_uom, row.get("plan_cost_bc"))
        row["plan_cost_bc"] = qty
    existing = db.query_sql(
        "SELECT `price_control` FROM `t_mmd_material_cost_data` "
        "WHERE `mat_code` = '{}' AND `plant_code` = '{}'".format(mat_code, plant_code))
    if existing and not row.get("price_control"):
        row["price_control"] = existing[0].get("price_control")
    return row


def _fill_financial_row(db, row, mat_code, plant_code, full):
    """填财务视图行。full=True(新增)补 deleted_mark/lock_flag; plant_val_class 缺失则回填。"""
    row["plant_code"] = plant_code
    if full:
        row["deleted_mark"] = 0
        row["lock_flag"] = 0
    existing = db.query_sql(
        "SELECT `plant_val_class` FROM `t_mmd_material_financial_data` "
        "WHERE `mat_code` = '{}' AND `plant_code` = '{}'".format(mat_code, plant_code))
    if existing and not row.get("plant_val_class"):
        row["plant_val_class"] = existing[0].get("plant_val_class")
    return row


def _build_views_for_add(db, dz, basic, mat_code):
    """新增: 推导 mat_type/mat_group, 补齐各视图默认值, 双工厂 1000 + 100N。"""
    mat_type1, mat_type2 = basic.get("mat_type1"), basic.get("mat_type2")
    mat_type3, mat_type4 = basic.get("mat_type3"), basic.get("mat_type4")
    basic_uom = basic.get("basic_uom")
    remarks = basic.get("remarks")

    basic["parallel_uom"] = ""
    old_mat_code = _escape_sql_text(basic.get("old_mat_code"))
    mat_description = _escape_sql_text(basic.get("mat_description"))[:40]

    existing = _query_basic_existing(db, mat_code, with_parallel_uom=False)
    if existing:
        _fill_missing(basic, existing,
                      ["process_code", "mat_description", "mat_type", "mat_group", "basic_uom"])

    basic["mat_type"] = _compute_mat_type(mat_type1, mat_type2, mat_type4)
    mat_group = mat_type3
    basic["mat_group"] = mat_group
    basic["mat_description"] = mat_description
    basic["old_mat_code"] = old_mat_code

    # 工厂视图(双工厂): 100N 的散料标识固定查 NS1
    plant = dz.get("plant", [])
    plant1 = copy.deepcopy(plant)
    bulk, mat_consumption = _get_bulk_material(db, PLANT_NORMAL, mat_group)
    bulk1, mat_consumption1 = _get_bulk_material(db, PLANT_CUSTODY, "NS1")
    for row in plant:
        _fill_plant_row(row, PLANT_NORMAL, bulk_material=bulk)
    for row in plant1:
        _fill_plant_row(row, PLANT_CUSTODY, bulk_material=bulk1, pur_type="F")

    # 成本视图(双工厂)
    cost = dz.get("cost", [])
    for row in cost:
        if not row.get("mat_code"):
            row["mat_code"] = mat_code
    cost1 = copy.deepcopy(cost)
    for row in cost:
        _fill_cost_row(db, row, mat_code, PLANT_NORMAL, basic_uom, mat_consumption, full=True)
    for row in cost1:
        _fill_cost_row(db, row, mat_code, PLANT_CUSTODY, basic_uom, mat_consumption1, full=True)

    # 财务视图(双工厂)
    financial = dz.get("financial", [])
    for row in financial:
        _fill_financial_row(db, row, mat_code, PLANT_NORMAL, full=True)
    financial1 = copy.deepcopy(financial)
    for row in financial1:
        _fill_financial_row(db, row, mat_code, PLANT_CUSTODY, full=True)

    uomconv = dz.get("uomconv", [])
    memo = {"mat_code": mat_code, "long_text": remarks}
    return plant, plant1, cost, cost1, financial, financial1, uomconv, memo


def _build_views_for_update(db, dz, basic, mat_code):
    """修改: mat_type/mat_group 用库里已有值, 仅补基本字段, 双工厂 1000 + 100N。"""
    remarks = basic.get("remarks", "")

    existing = _query_basic_existing(db, mat_code, with_parallel_uom=True)
    if existing:
        _fill_missing(basic, existing,
                      ["process_code", "mat_description", "mat_type", "mat_group",
                       "basic_uom", "parallel_uom"])

    basic_uom = basic.get("basic_uom")

    plant = dz.get("plant", [])
    plant1 = copy.deepcopy(plant)
    for row in plant:
        _fill_plant_row(row, PLANT_NORMAL)
    for row in plant1:
        _fill_plant_row(row, PLANT_CUSTODY)

    cost = dz.get("cost", [])
    for row in cost:
        if not row.get("mat_code"):
            row["mat_code"] = mat_code
    cost1 = copy.deepcopy(cost)
    for row in cost:
        _fill_cost_row(db, row, mat_code, PLANT_NORMAL, basic_uom, "", full=False)
    for row in cost1:
        _fill_cost_row(db, row, mat_code, PLANT_CUSTODY, basic_uom, "", full=False)

    financial = dz.get("financial", [])
    for row in financial:
        _fill_financial_row(db, row, mat_code, PLANT_NORMAL, full=False)
    financial1 = copy.deepcopy(financial)
    for row in financial1:
        _fill_financial_row(db, row, mat_code, PLANT_CUSTODY, full=False)

    uomconv = dz.get("uomconv", [])
    memo = {"mat_code": mat_code, "long_text": remarks}
    return plant, plant1, cost, cost1, financial, financial1, uomconv, memo


def save_mainmaterial_basic_data(payload, user_id):
    """保存物料主数据: 按有无 mat_code 走新增(A)/修改(B), 双工厂各落一次。

    :param payload: {"data": [ {"basic", "plant", "financial", "cost", "uomconv"}, ... ]}
    :param user_id: 创建/操作人 id, 透传给 maintain_data。
    :return: {"type": "S"/"E", "message": ...}
    """
    db = DbHelper()
    code, msg = "S", "保存成功"

    mat_code_list = [r["mat_code"] for r in
                     db.query_sql("SELECT `id`, `mat_code` FROM `t_mmd_material_basic_data`")]
    data = payload.get("data")
    print("data----",data)
    for dz in data:
        basic = dz.get("basic")
        mat_code = basic.get("mat_code")

        if mat_code not in mat_code_list:
            mode = "A"
            views = _build_views_for_add(db, dz, basic, mat_code)
        else:
            mode = "B"
            views = _build_views_for_update(db, dz, basic, mat_code)
        plant, plant1, cost, cost1, financial, financial1, uomconv, memo = views

        # 先按真实 mode 落 1000, 成功后再以 mode='B' 落 100N
        sales = []
        code_x, msg, error_list, _ = maintain_data(
            0, basic, plant, sales, financial, cost, uomconv, memo, [], mode, user_id, quality=[])
        if 200 != code_x:
            code, msg = "E", str(error_list)
            continue

        code1_x, msg, error_list1, _ = maintain_data(
            0, basic, plant1, sales, financial1, cost1, uomconv, memo, [], "B", user_id, quality=[])
        code, msg = ("S", msg) if 200 == code1_x else ("E", str(error_list1))

    return {"type": code, "message": msg}




# ---------- 测试用 rows (结构同 _query_source_data 的返回: list[dict]) ----------
_BASE = {
    # ---- 基本视图 ----
    "mat_code": "", "mat_description": "", "old_mat_code": "", "old_description": "",
    "basic_uom": "EA", "parallel_uom": "", "parallel_uom_mark": 0,
    "capacity_dimension": "", "note": "",
    "mat_type1": "", "mat_type2": "", "mat_type3": "", "mat_type4": "",
    # ---- 工厂视图 ----
    "plant_code": "1000", "batch_mark": 0, "pur_uom": "EA", "prod_uom": "EA",
    "source_mark": 0, "safety_stock_quantity": 0, "reorder_point": 0,
    "pur_type": "E", "shelf_life_days": 0, "bulk_material": 0,
    # ---- 财务视图 ----
    "profit_center": "", "plant_val_class": "1000",
    # ---- 成本视图 ----
    "cost_uom": "EA", "plant_val_mark": 1,
    "version_val_mark": 0, "batch_val_mark": 0, "other_special_val_mark": 0,
    "outsource_val_mark": 0, "project_val_mark": 0, "stor_loc_val_mark": 0, "so_val_mark": 0,
    "valgroup_value": "", "mat_cost_classify": "Z001",
    "co_currency": "CNY", "plan_cost_bc": 0, "plan_cost_rate": 1,
    "effective_start_date": "2026-07-01", "basic_currency": "CNY",
    "price_control": "S", "price_unit": 1, "cost_lot": 1,
    "special_pur_cc": "E", "mat_consumption": "", "plan_cost_currency": "CNY",
    "plan_price_unit": "EA", "wbs_elements": "",
    # ---- 单位换算(默认无) ----
    "primary_uom_qty": "", "primary_uom": "", "secondary_uom_qty": "", "secondary_uom": "",
}

rows = [
    # 1) 成品 / 自制 / 有单位换算(1 BOX = 100 EA) / mat_type 推 Z001 (t1=M,t4!=K)
    {**_BASE, **{
        "mat_code": "TEST-PROD-0001", "mat_description": "测试成品-芯片A",
        "old_mat_code": "OLD-0001", "old_description": "旧芯片A",
        "note": "接口测试-成品", "mat_type1": "M", "mat_type3": "MWG",
        "batch_mark": 1, "source_mark": 1, "pur_type": "E",
        "safety_stock_quantity": 500, "reorder_point": 200, "shelf_life_days": 365,
        "profit_center": "P1000", "plan_cost_bc": 12.50, "special_pur_cc": "E",
        "primary_uom_qty": 100, "primary_uom": "BOX",
        "secondary_uom_qty": 1, "secondary_uom": "EA",
    }},
    # 2) Wafer / 外购 / 无单位换算 / 物料组 WARFE / mat_type 推 Z002 (t1!=M,t2!=C)
    {**_BASE, **{
        "mat_code": "TEST-WAFER-0002", "mat_description": "测试-Wafer WARFE",
        "basic_uom": "PCS", "mat_type1": "", "mat_type2": "", "mat_type3": "WARFE",
        "pur_uom": "PCS", "prod_uom": "PCS", "pur_type": "F", "special_pur_cc": "F",
        "price_control": "S",  # WARFE 都是 S
        "valgroup_value": "TEST-PROD-0001",  # 母料号
    }},
    # 3) 散料(膜厚 NS1)/ 外购 / mat_type 推 Z004 (t1!=M,t2=C) —— 触发 _get_bulk_material 查 NS1
    {**_BASE, **{
        "mat_code": "TEST-BULK-0003", "mat_description": "测试-散料膜厚",
        "mat_type1": "", "mat_type2": "C", "mat_type3": "NS1",
        "pur_type": "F", "special_pur_cc": "F", "batch_mark": 1,
        "plan_cost_bc": 0.05,
    }},
]


# ==================== 入口 ====================
def material_master_data_push(user_id=0):
    """物料主数据同步入口: 查表 -> 组接口结构 -> 调 save_mainmaterial_basic_data(bapi) 落库。

    :param user_id: 创建/操作人 id, 透传给 maintain_data。
    :return: {"type": "S"/"E", "message": ...}
    """
    pg = PostgreSQL()

    # 1. 查表(暂空) TODO: 待确认数仓表名/同步条件
    # rows = _query_source_data(pg)
    if not rows:
        return {"type": "S", "message": "无待同步数据"}

    # 2. 组结构: 表每行 -> 一个物料嵌套结构
    payload = {"data": [_flat_row_to_item(r) for r in rows]}

    print('payload----',payload)
    # 3. 调 bapi 存表(内部按 mat_code 新增/修改 + 双工厂各落一次)
    return save_mainmaterial_basic_data(payload, user_id)



if __name__ == "__main__":
    print(material_master_data_push(user_id=0))
