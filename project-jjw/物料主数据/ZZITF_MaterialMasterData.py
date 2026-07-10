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
import json
from decimal import Decimal

from DbHelper import DbHelper
from DxMaintainMaterialData import maintain_data
from libenhance import get_cnf
from ZZEXT_PostgreSqlDB import PostgreSQL

# ---------- 固定值 ----------
PLANT_NORMAL = "1000"    # 正常工厂
PLANT_CUSTODY = "100N"   # 客供料工厂

# ---------- 数仓源表 ----------
SOURCE_WIDE_TABLE = "ads_cost_erp_material_info"

# 每批从数仓读取的条数(表数据量大, 分批读取, 读到不足一批即止)
BATCH_SIZE = 2



# ==================== 各视图字段(与 0701 文档 / 接口结构 / 数仓列同名) ====================
# 数仓 ads_cost_erp_material_info 列名与文档字段同名, _pick 直接按字段名取值。

# 基本视图 t_mmd_material_basic_data
_BASIC_FIELDS = [
    "mat_code", "mat_description", "old_mat_code", "old_description",
    "basic_uom", "parallel_uom", "parallel_uom_mark",
    "mat_type", "mat_group",
]

# 工厂视图 t_mmd_material_plant_data
_PLANT_FIELDS = [
    "mat_code", "plant_code", "batch_mark", "pur_uom", "prod_uom",
    "source_mark", "safety_stock_quantity", "reorder_point", "pur_type",
    "shelf_life_days", "bulk_material",
]



# 从数仓表中查找的 SC工厂视图 t_mmd_material_plant_data
_PLANT_SC_FIELDS = [
    "mat_code", "plant_code", "batch_mark", "pur_uom", "prod_uom",
    "safety_stock_quantity", "reorder_point",
    "shelf_life_days", "bulk_material",
]

# 财务视图 t_mmd_material_financial_data
_FINANCIAL_FIELDS = ["mat_code", "plant_code", "profit_center", "plant_val_class"]


# 从数仓表中查找的 SC财务视图 t_mmd_material_financial_data
_FINANCIAL_SC_FIELDS = ["mat_code", "plant_code", "profit_center", "plant_val_class"]


# 成本视图 t_mmd_material_cost_data
_COST_FIELDS = [
    "mat_code", "plant_code", "cost_uom", "plant_val_mark", "version_val_mark",
    "batch_val_mark", "other_special_val_mark", "outsource_val_mark",
    "project_val_mark", "stor_loc_val_mark", "so_val_mark", "valgroup_value",
    "mat_cost_classify", "co_currency", "plan_cost_bc", "plan_cost_rate",
    "effective_start_date", "basic_currency", "price_control", "price_unit",
    "cost_lot", "special_pur_cc", "mat_consumption", "plan_cost_currency",
    "wbs_elements",
]

# 从数仓表中查找的 SC成本视图 t_mmd_material_cost_data
_COST_SC_FIELDS = [
    "mat_code", "plant_code", "cost_uom", "plant_val_mark", 
    "mat_cost_classify", "co_currency",
    "basic_currency", "price_control", "price_unit",
    "cost_lot", "special_pur_cc", 
]

# 单位换算 t_mmd_uom_conversion
_UOMCONV_FIELDS = [
    "mat_code", "primary_uom_qty", "primary_uom",
    "secondary_uom_qty", "secondary_uom",
]


# ==================== 数仓源列(ads_cost_erp_material_info) ====================
# 数仓表 ads_cost_erp_material_info 列名与 0701 文档字段完全同名,
# 故 SELECT 直接取文档字段, 不需要 ERP→烽火字段映射/别名。
# 增量基线 = 烽火 t_mmd_material_basic_data.MAX(update_time), 见 _get_max_update_time。


# ==================== 工具: 表行 -> 嵌套结构 ====================




# 自定义JSON编码器，处理Decimal
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            # 转float 或 转字符串二选一
            return float(obj)
            # return str(obj)
        return super().default(obj)


def _val(row, key):
    """取 row[key]; None / 纯空白串 -> '' (数仓用 ' ' 表示空)。非字符串原样返回。"""
    v = row.get(key)
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    return v


def _pick(row, fields):
    """从表行里按字段清单摘出一个视图 dict"""
    return {f: _val(row, f) for f in fields}


def _build_basic(row):
    """基本视图(字段名与数仓列、文档一致)。"""
    return _pick(row, _BASIC_FIELDS)


def _build_uomconv(row):
    """单位换算 -> 列表。主/辅单位都没有则不下发"""
    item = _pick(row, _UOMCONV_FIELDS)
    if not item.get("primary_uom") and not item.get("secondary_uom"):
        return []
    return [item]


# 接口里 boolean 类型字段; 数仓用 'y'/'n' 表示, 需统一成 0/1
_BOOL_FIELDS = {
    "parallel_uom_mark", "batch_mark", "source_mark", "bulk_material",
    "plant_val_mark", "version_val_mark", "batch_val_mark",
    "other_special_val_mark", "outsource_val_mark", "project_val_mark",
    "stor_loc_val_mark", "so_val_mark",
}


def _to_bool(v):
    """'y'/'n' 或 0/1 -> 1/0; 空/未知 -> ''(交给后续默认/回填逻辑)。"""
    if v is None or v == "":
        return ""
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (int, float)):
        return 1 if v else 0
    s = str(v).strip().lower()
    if s in ("y", "yes", "true", "1", "t"):
        return 1
    if s in ("n", "no", "false", "0", "f"):
        return 0
    return ""


def _flat_row_to_item(row):
    """表一行 -> 接口结构一个物料 {basic, plant, financial, cost, uomconv}。
    plant/financial/cost 是单元素列表(表一行一个物料, 每个视图一行);
    uomconv 按有无数据 0~N 行。先归一 boolean 字段, 再按字段名取值。
    """
    norm = dict(row)
    for f in _BOOL_FIELDS:
        if f in norm:
            norm[f] = _to_bool(norm[f])
    return {
        "basic": _build_basic(norm),
        "plant": [_pick(norm, _PLANT_FIELDS)],
        "financial": [_pick(norm, _FINANCIAL_FIELDS)],
        "cost": [_pick(norm, _COST_FIELDS)],
        "uomconv": _build_uomconv(norm),
    }


# ==================== 查表(数仓宽表 ads_cost_erp_material_info) ====================
def _source_columns():
    """数仓 SELECT 列 = 各视图字段的去重并集(即 0701 文档全部字段, 与数仓列同名)。"""
    cols = []
    for fields in (_BASIC_FIELDS, _PLANT_SC_FIELDS, _COST_SC_FIELDS,
                   _FINANCIAL_SC_FIELDS, _UOMCONV_FIELDS):
        
        for f in fields:
            if f not in cols:
                cols.append(f)
    return cols


def _fmt_ts(dt):
    """时间戳格式化成 PG 可比较的 'YYYY-MM-DD HH:MM:SS'; None -> 极早时间(全量)。"""
    if dt is None:
        return "1900-01-01 00:00:00"
    if hasattr(dt, "strftime"):
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return str(dt)


def _pg_literal(value):
    """PG 字符串字面量: 单引号包裹, 内部单引号双写(防注入/防语法错)。"""
    return "'" + str(value).replace("'", "''") + "'"


def _get_max_update_time(db):
    """取烽火 t_mmd_material_basic_data 的最大 update_time(增量同步基线); 表空返回 None。"""
    rows = db.query_sql("SELECT MAX(`update_time`) AS `max_ut` FROM `t_mmd_material_basic_data`")
    if rows and rows[0].get("max_ut"):
        return rows[0]["max_ut"]
    return None


def _query_source_batch(pg, max_ut, cursor_ut, cursor_mc, limit=BATCH_SIZE):
    """分批查数仓 ads_cost_erp_material_info:
    增量条件 update_time > 烽火最大 update_time(max_ut); max_ut 为空则全量(不加该条件)。游标 (cursor_ut, cursor_mc)
    续读避免重复/漏行(cursor_mc 为 None 即第一批)。按 (update_time, mat_code) 排序。
    """
    
    schema = get_cnf("pgsql.schema")
    cols = ", ".join(_source_columns() + ["update_time"])  # update_time 仅作游标, 不进接口结构
    clauses = []
    # print(max_ut)
    # print(cursor_ut)
    # print(cursor_mc)
    # if max_ut:   # 有基线才加增量条件; 空(烽火表空/无值) -> 全量, 不用 update_time 作条件
    #     clauses.append("update_time > {}".format(_pg_literal(_fmt_ts(max_ut))))
    
    # if cursor_mc is not None:
    #     clauses.append("(update_time, mat_code) > ({}, {})".format(
    #         _pg_literal(_fmt_ts(cursor_ut)), _pg_literal(cursor_mc)))
    
    where = " AND ".join(clauses) if clauses else "1=1"
    sql = ("SELECT {} FROM {}.{} WHERE {} "
           "ORDER BY update_time, mat_code LIMIT {}").format(
        cols, schema, SOURCE_WIDE_TABLE, where, limit)
    print(sql)
    
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
        # plan_cost_bc 由数仓直供(文档字段), 不再做单位换算
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
    """新增: mat_type/mat_group 由数仓直供(文档字段), 补齐各视图默认值, 双工厂 1000 + 100N。"""
    basic_uom = basic.get("basic_uom")
    remarks = basic.get("remarks", "")  # 文档无数仓备注列, 默认空串给 memo

    basic["parallel_uom"] = ""
    old_mat_code = _escape_sql_text(basic.get("old_mat_code"))
    mat_description = _escape_sql_text(basic.get("mat_description"))[:40]

    existing = _query_basic_existing(db, mat_code, with_parallel_uom=False)
    if existing:
        _fill_missing(basic, existing,
                      ["process_code", "mat_description", "mat_type", "mat_group", "basic_uom"])

    mat_group = basic.get("mat_group")  # 数仓直供(文档字段)
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
    # print("data----", json.dumps(data, cls=DecimalEncoder, ensure_ascii=False, indent=4))
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
        print("error_list----", error_list)
        if 200 != code_x:
            code, msg = "E", str(error_list)
            continue

        code1_x, msg, error_list1, _ = maintain_data(
            0, basic, plant1, sales, financial1, cost1, uomconv, memo, [], "B", user_id, quality=[])
        code, msg = ("S", msg) if 200 == code1_x else ("E", str(error_list1))

    return {"type": code, "message": msg}








# ==================== 入口 ====================
def material_master_data_push(user_id=0):
    """物料主数据同步入口: 增量 + 分批查数仓 -> 组接口结构 -> 调 save 落库, 直到读不出数据。

    增量: 只查 update_time > 烽火 t_mmd_material_basic_data 最大 update_time 的数据。
    分批: 每批 BATCH_SIZE 条, 按 (update_time, mat_code) 游标续读。

    :param user_id: 创建/操作人 id, 透传给 maintain_data。
    :return: {"type": "S"/"E", "message": ...}
    """
    db = DbHelper()
    pg = PostgreSQL()

    max_ut = _get_max_update_time(db)          # 增量基线(烽火表空 -> None -> 全量)
    cursor_ut, cursor_mc = None, None           # 游标: 第一批不带上界
    total, batch_no = 0, 0

    while True:
        rows = _query_source_batch(pg, max_ut, cursor_ut, cursor_mc)
        if not rows:
            break
        print(rows)
        batch_no += 1
        payload = {"data": [_flat_row_to_item(r) for r in rows]}
        print("第 {} 批 {} 条".format(batch_no, len(rows)))
        print(payload)
        save_mainmaterial_basic_data(payload, user_id)

        total += len(rows)
        last = rows[-1]
        cursor_ut, cursor_mc = last.get("update_time"), last.get("mat_code", "")
        if len(rows) < BATCH_SIZE:              # 不足一批 = 已读完
            break
        break

    return {"type": "S", "message": "同步完成, 共 {} 批 {} 条".format(batch_no, total)}



if __name__ == "__main__":
    print(material_master_data_push(user_id=0))
