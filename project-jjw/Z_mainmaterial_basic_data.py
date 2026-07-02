#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@File    : Z_mainmaterial_basic_data.py
@explain : 物料主数据保存

  按 mat_code 是否已存在走 新增(A) / 修改(B), 每个物料按"双工厂"拆成两份:
  正常工厂 1000 + 客供料工厂 100N, 各视图(基本/工厂/成本/财务/单位换算/特性)落库。
  最终调 maintain_data 两次(1000 用真实 mode, 100N 固定 mode='B')。
"""
import copy
from datetime import date

from DbHelper import DbHelper
from DxBusinessDataConvertUtil import convert_material_unit_qty
from DxMaintainMaterialData import maintain_data

# ---------- 固定值 ----------
PLANT_NORMAL = "1000"    # 正常工厂
PLANT_CUSTODY = "100N"   # 客供料工厂

# 特性组: 前端编码 -> 秘火短码
_FIELD_CODE_MAP = {
    "wyse_centralizedsupply": "JZGY",   # 是否集中供应
    "wyse_bom": "BOM",                  # 是否BOM
    "wyse_lifetime": "LT",              # LifeTime
    "wyse_lifetimeunit": "LTDW",        # LifeTime单位
    "wyse_amorticount": "WC",           # Wafer Count
    "wyse_certification": "RZZT",       # 认证状态
}

# ==================== 工具 ====================
def _escape_sql_text(value):
    """转义 SQL 文本里的反斜杠/单引号/双引号"""
    if value is None:
        return ""
    return (str(value)
            .replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace('"', '\\"'))


def _fill_missing(target, source, fields):
    """target 里为空的字段用 source 回填(修改时保留库里已有值)"""
    for f in fields:
        if not target.get(f):
            target[f] = source.get(f)


def _infer_field_type(value):
    """根据 Python 值类型推断 (field_type, field_length)"""
    if isinstance(value, str):
        return "varchar", "255"
    if isinstance(value, int):
        return "int", "10"
    if isinstance(value, float):
        return "decimal", "16"
    if isinstance(value, date):
        return "date", "10"
    return "varchar", "255"


def _compute_mat_type(t1, t2, t4):
    """由前端物料类型标志推 SAP 物料类型 Z001~Z004"""
    if t1 != "M":
        return "Z004" if t2 == "C" else "Z002"
    return "Z003" if t4 == "K" else "Z001"


def _get_bulk_material(db, plant_code, mat_group):
    """查物料组消耗标识; mat_consumption=='2' 视为散料, 返回 (bulk_material, mat_consumption)"""
    rows = db.query_sql(
        "SELECT mat_consumption FROM t_mmd_material_group_consumption "
        "WHERE plant_code = '{}' AND mat_group = '{}'".format(plant_code, mat_group))
    mat_consumption = rows[0].get("mat_consumption") if rows else ""
    return (1 if mat_consumption == "2" else 0), mat_consumption


def _query_basic_existing(db, mat_code, with_parallel_uom=False):
    """查 t_mmd_material_basic_data 已有抬头(回填缺失字段用)"""
    cols = "process_code, mat_description, mat_type, mat_group, basic_uom"
    if with_parallel_uom:
        cols += ", parallel_uom"
    rows = db.query_sql(
        "SELECT {} FROM t_mmd_material_basic_data WHERE mat_code = '{}'".format(cols, mat_code))
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
            "mat_consumption": mat_consumption,
        })
        _, _, qty = convert_material_unit_qty(
            mat_code, row.get("plan_price_unit"), basic_uom, row.get("plan_cost_bc"))
        row["plan_cost_bc"] = qty
    existing = db.query_sql(
        "SELECT price_control FROM t_mmd_material_cost_data "
        "WHERE mat_code = '{}' AND plant_code = '{}'".format(mat_code, plant_code))
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
        "SELECT plant_val_class FROM t_mmd_material_financial_data "
        "WHERE mat_code = '{}' AND plant_code = '{}'".format(mat_code, plant_code))
    if existing and not row.get("plant_val_class"):
        row["plant_val_class"] = existing[0].get("plant_val_class")
    return row


def _build_detail_rows(detail, mat_group):
    """特性组 -> t_mmd_material_field_details 行(编码映射 + 类型推断)"""
    rows = []
    for item in detail:
        field_code = item.get("field_code")
        field_value = item.get("field_value")
        if field_code == "JH":   # 是否临时键合: 按物料组取 是/否
            field_value = "是" if mat_group == "MWG" else "否"
        else:
            field_code = _FIELD_CODE_MAP.get(field_code, field_code)
        field_type, field_length = _infer_field_type(field_value)
        rows.append({
            "property_group": "WY01",
            "field_code": str(field_code),
            "field_value": str(field_value),
            "field_type": str(field_type),
            "field_length": str(field_length),
            "field_name": str(field_code),
            "field_value_from": "",
            "field_value_to": "",
            "field_mark": "1",   # 0 范围 / 1 单一值
            "mat_code": item.get("mat_code"),
        })
    return rows


# ==================== 视图组装(新增 / 修改) ====================
def _build_views_for_add(db, dz, basic, mat_code):
    """新增: 推导 mat_type/mat_group, 补齐各视图默认值, 双工厂 1000 + 100N"""
    mat_type1, mat_type2 = basic.get("mat_type1"), basic.get("mat_type2")
    mat_type3, mat_type4 = basic.get("mat_type3"), basic.get("mat_type4")
    basic_uom = basic.get("basic_uom")
    remarks = basic.get("remarks")

    basic["parallel_uom"] = ""
    old_mat_code = _escape_sql_text(basic.get("old_mat_code"))
    mat_description = _escape_sql_text(basic.get("mat_description"))[:80]

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
    detail_new = _build_detail_rows(dz.get("detail", []), mat_group)
    memo = {"mat_code": mat_code, "long_text": remarks}
    return plant, plant1, cost, cost1, financial, financial1, uomconv, detail_new, memo


def _build_views_for_update(db, dz, basic, mat_code):
    """修改: mat_type/mat_group 用库里已有值, 仅补基本字段, 双工厂 1000 + 100N"""
    remarks = basic.get("remarks", "")

    existing = _query_basic_existing(db, mat_code, with_parallel_uom=True)
    if existing:
        _fill_missing(basic, existing,
                      ["process_code", "mat_description", "mat_type", "mat_group",
                       "basic_uom", "parallel_uom"])

    mat_group = basic.get("mat_group")
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
    detail_new = _build_detail_rows(dz.get("detail", []), mat_group)
    memo = {"mat_code": mat_code, "long_text": remarks}
    return plant, plant1, cost, cost1, financial, financial1, uomconv, detail_new, memo


# ==================== 入口 ====================
def save_mainmaterial_basic_data(payload, user_id):
    """保存物料主数据: 按有无 mat_code 走新增(A)/修改(B), 双工厂各落一次。"""
    db = DbHelper()
    code, msg = "S", "保存成功"

    mat_code_list = [r["mat_code"] for r in
                     db.query_sql("SELECT id, mat_code FROM t_mmd_material_basic_data")]
    data = payload.get("data")

    for dz in data:
        basic = dz.get("basic")
        mat_code = basic.get("mat_code")

        if mat_code not in mat_code_list:
            mode = "A"
            views = _build_views_for_add(db, dz, basic, mat_code)
        else:
            mode = "B"
            views = _build_views_for_update(db, dz, basic, mat_code)
        plant, plant1, cost, cost1, financial, financial1, uomconv, detail_new, memo = views

        # 先按真实 mode 落 1000, 成功后再以 mode='B' 落 100N
        sales = []
        code_x, msg, error_list, _ = maintain_data(
            0, basic, plant, sales, financial, cost, uomconv, memo, detail_new, mode, user_id, quality=[])
        if 200 != code_x:
            code, msg = "E", str(error_list)
            continue

        code1_x, msg, error_list1, _ = maintain_data(
            0, basic, plant1, sales, financial1, cost1, uomconv, memo, detail_new, "B", user_id, quality=[])
        code, msg = ("S", msg) if 200 == code1_x else ("E", str(error_list1))

    return {"type": code, "message": msg}
