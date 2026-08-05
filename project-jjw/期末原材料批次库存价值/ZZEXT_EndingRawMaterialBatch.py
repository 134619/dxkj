#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@File    : ZZEXT_EndingRawMaterialBatch.py
@explain : 期末原材料批次库存价值报表

  查询条件(前端传入):
    year         年度    必填(单选)
    period       期间    必填(单选)
    plant_code   工厂    选填(多选, 空不过滤)
    stor_loc_code 库存地点 选填(多选, 空不过滤)
    mat_code     物料编码 选填(多选, 空不过滤)

  主表 t_inventory_batch_data 按条件查, 关联取名称:
    mat_description / basic_uom / parallel_uom  取自 t_mmd_material_basic_data(docx 标批次表是笔误)
    plant_name                                取自 t_os_plant.plant_description
    stor_loc_description                      取自 t_os_plant_storage_location_alloc.stor_loc_desc
    basic_qty / batch_sn / parallel_qty       取自主表(parallel_qty 按 docx, 待运行验证列存在)

  金额(inv)与货币(currency)按 price_control 分支计算(先用 mat_code+plant 查 t_mmd_material_cost_data):
    price_control = S: 查 t_cc_actual_cost 取 ending_inv_qty_sku / ending_inv_total_cost_bc / basic_currency
                    金额 = ending_inv_total_cost_bc / ending_inv_qty_sku * basic_qty
                    货币 = basic_currency
                    (该表项目代码未引用, 按 docx 字段实现; 查询失败该行金额置空, 不阻断)
    price_control = V: 查 ut_rm_production_batch(mat_code + 工厂作 company + batch_sn, 年度期间小于所选)
                    合计 uf_qty_m / uf_cur_m, 取 uf_currency
                    金额 = uf_cur_m合计 / uf_qty_m合计 * basic_qty
                    货币 = uf_currency
    分母为 0 或查不到成本数据: 金额/货币置空(null)
"""
import json

from DbHelper import DbHelper
from libenhance import Request, Response

# ==================== 返回前端 code ====================
CODE_OK = 200  # 成功
CODE_MISSING_PARAM = 401  # 缺少参数 / 查询失败

# ==================== 表名 ====================
T_BATCH = "t_inventory_batch_data"  # 主表: 批次库存
T_BASIC = "t_mmd_material_basic_data"  # 物料主数据(名称/单位)
T_PLANT = "t_os_plant"  # 工厂(名称)
T_STOR = "t_os_plant_storage_location_alloc"  # 工厂-库存地点分配(库地名称)
T_COST = "t_mmd_material_cost_data"  # 物料成本(price_control)
T_ACTUAL = "t_cc_actual_cost"  # S 价实际成本(docx 指定; 项目代码未引用, 运行时验证)
T_PROD = "ut_rm_production_batch"  # V 价: 原材料生产批次

PRICE_S = "S"
PRICE_V = "V"

# 前端表格列定义(display): field 对应返回数据键, description 为列标题; 手写(参考 InventoryReceiptDetailReport.QueryDetail)
DISPLAY = [
    {"field": "year", "description": "年度", "type": "varchar", "length": 4, "decimal": 0, "readOnly": True, "required": False},
    {"field": "period", "description": "期间", "type": "varchar", "length": 2, "decimal": 0, "readOnly": True, "required": False},
    {"field": "plant_code", "description": "工厂", "type": "varchar", "length": 6, "decimal": 0, "readOnly": True, "required": False},
    {"field": "plant_name", "description": "工厂名称", "type": "varchar", "length": 40, "decimal": 0, "readOnly": True, "required": False},
    {"field": "stor_loc_code", "description": "库存地点", "type": "varchar", "length": 50, "decimal": 0, "readOnly": True, "required": False},
    {"field": "stor_loc_description", "description": "库存地点名称", "type": "varchar", "length": 40, "decimal": 0, "readOnly": True, "required": False},
    {"field": "mat_code", "description": "物料编码", "type": "varchar", "length": 40, "decimal": 0, "readOnly": True, "required": False},
    {"field": "mat_description", "description": "物料名称", "type": "varchar", "length": 80, "decimal": 0, "readOnly": True, "required": False},
    {"field": "batch_sn", "description": "批次", "type": "varchar", "length": 40, "decimal": 0, "readOnly": True, "required": False},
    {"field": "basic_qty", "description": "数量", "type": "decimal", "length": 0, "decimal": 2, "readOnly": True, "required": False},
    {"field": "basic_uom", "description": "单位", "type": "varchar", "length": 4, "decimal": 0, "readOnly": True, "required": False},
    {"field": "parallel_qty", "description": "平行数量", "type": "decimal", "length": 0, "decimal": 2, "readOnly": True, "required": False},
    {"field": "parallel_uom", "description": "平行单位", "type": "varchar", "length": 4, "decimal": 0, "readOnly": True, "required": False},
    {"field": "inv", "description": "金额", "type": "decimal", "length": 0, "decimal": 2, "readOnly": True, "required": False},
    {"field": "currency", "description": "货币", "type": "varchar", "length": 10, "decimal": 0, "readOnly": True, "required": False},
]


# ==================== 基础工具 ====================
def _esc(v):
    """SQL 字符串转义(单引号转为两个单引号)。"""
    return str(v).replace("'", "''") if v is not None else ""


def _to_float(v, default=0.0):
    """转 float; 转不了取 default。"""
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _in_clause(col, vals):
    """拼 col IN ('a','b'); 空集返回 None(表示跳过)。"""
    xs = [str(v) for v in vals if str(v) != ""]
    if not xs:
        return None
    return "{} IN ({})".format(col, ",".join("'" + _esc(v) + "'" for v in xs))


def _build_where(flt):
    """year/period 必填(单值 =), plant/stor_loc/mat 选填(多值 IN, 空不过滤)。
    :return (where_sql, year, period, err) err 非空表示缺必填。"""
    year = flt.get("year") if isinstance(flt, dict) else None
    period = flt.get("period") if isinstance(flt, dict) else None
    if year in (None, "") or period in (None, ""):
        return None, None, None, "缺少必填查询条件: year / period"
    clauses = [
        "d.`year` = '{}'".format(_esc(year)),
        "d.`period` = '{}'".format(_esc(period)),
    ]
    multi = {
        "plant_code": "d.`plant_code`",
        "stor_loc_code": "d.`stor_loc_code`",
        "mat_code": "d.`mat_code`",
    }
    for key, col in multi.items():
        val = flt.get(key)
        if val in (None, ""):
            continue
        if isinstance(val, (list, tuple)):
            c = _in_clause(col, val)
            if c:
                clauses.append(c)
        else:
            clauses.append("{} = '{}'".format(col, _esc(val)))
    where = " ".join("AND " + c for c in clauses)
    return where, str(year), str(period), None


# ==================== 主查询 ====================
def _build_main_sql(where):
    """主表 + 物料/工厂/库存地点 名称关联。"""
    return """
SELECT
    d.`year`, d.`period`,
    d.`plant_code`, p.`plant_description` AS `plant_name`,
    d.`stor_loc_code`, s.`stor_loc_desc` AS `stor_loc_description`,
    d.`mat_code`, b.`mat_description`,
    d.`batch_sn`,
    d.`basic_qty`,
    b.`basic_uom`,
    d.`parallel_qty`,
    b.`parallel_uom`
FROM `{T_BATCH}` d
LEFT JOIN `{T_BASIC}` b ON b.`mat_code` = d.`mat_code`
LEFT JOIN `{T_PLANT}` p ON p.`plant_code` = d.`plant_code`
LEFT JOIN `{T_STOR}` s ON s.`plant_code` = d.`plant_code` AND s.`stor_loc_code` = d.`stor_loc_code`
WHERE 1 = 1
{where}
""".format(T_BATCH=T_BATCH, T_BASIC=T_BASIC, T_PLANT=T_PLANT, T_STOR=T_STOR, where=where)


# ==================== 金额计算所需数据批量预取 ====================
def _load_price_control(pairs, db):
    """批量查 price_control。pairs: {(mat_code, plant_code)}。
    :return {(mat_code, plant_code): price_control}"""
    out = {}
    if not pairs:
        return out
    mats = sorted({m for m, _ in pairs if m})
    plants = sorted({p for _, p in pairs if p})
    if not mats or not plants:
        return out
    sql = "SELECT `mat_code`,`plant_code`,`price_control` FROM `{}` WHERE `mat_code` IN ({}) AND `plant_code` IN ({})".format(
        T_COST,
        ",".join("'" + _esc(m) + "'" for m in mats),
        ",".join("'" + _esc(p) + "'" for p in plants),
    )
    try:
        rows = db.query_sql(sql) or []
    except Exception as e:
        print("[price_control] 查询失败: {}".format(e))
        return out
    for r in rows:
        out[(r.get("mat_code"), r.get("plant_code"))] = r.get("price_control")
    return out


def _load_s_cost(pairs, year, period, db):
    """S 价: 批量查 t_cc_actual_cost。pairs: {(mat, plant)}。
    :return {(mat, plant): (ending_inv_qty_sku, ending_inv_total_cost_bc, basic_currency)}"""
    out = {}
    if not pairs:
        return out
    mats = sorted({m for m, _ in pairs if m})
    plants = sorted({p for _, p in pairs if p})
    sql = (
        "SELECT `mat_code`,`plant_code`,`ending_inv_qty_sku`,`ending_inv_total_cost_bc`,`basic_currency`"
        " FROM `{}` WHERE `year` = '{}' AND `period` = '{}' AND `mat_code` IN ({}) AND `plant_code` IN ({})"
    ).format(
        T_ACTUAL, _esc(year), _esc(period),
        ",".join("'" + _esc(m) + "'" for m in mats),
        ",".join("'" + _esc(p) + "'" for p in plants),
    )
    try:
        rows = db.query_sql(sql) or []
    except Exception as e:
        # 表/字段不存在时这里兜住, S 价行金额置空, 不阻断主流程
        print("[s_cost] 查询 {} 失败(可能表或字段不存在): {}".format(T_ACTUAL, e))
        return out
    for r in rows:
        out[(r.get("mat_code"), r.get("plant_code"))] = (
            _to_float(r.get("ending_inv_qty_sku")),
            _to_float(r.get("ending_inv_total_cost_bc")),
            r.get("basic_currency"),
        )
    return out


def _load_v_cost(triples, year, period, db):
    """V 价: 批量查 ut_rm_production_batch(年度+期间小于所选, 工厂带入公司字段)。
    triples: {(mat, plant_as_company, batch_sn)}
    :return {(mat, company, batch_sn): (uf_qty_m合计, uf_cur_m合计, uf_currency)}"""
    out = {}
    if not triples:
        return out
    mats = sorted({t[0] for t in triples if t[0]})
    companies = sorted({t[1] for t in triples if t[1]})  # 工厂值作为 uf_company_code
    batches = sorted({t[2] for t in triples if t[2]})
    if not (mats and companies and batches):
        return out
    sql = (
        "SELECT `uf_mat_code`,`uf_company_code`,`uf_batch_sn`,"
        " SUM(`uf_qty_m`) AS qty_sum, SUM(`uf_cur_m`) AS cur_sum,"
        " MAX(`uf_currency`) AS currency"
        " FROM `{tbl}`"
        " WHERE (`uf_year` < '{y}' OR (`uf_year` = '{y}' AND `uf_period` < '{p}'))"
        " AND `uf_mat_code` IN ({mats}) AND `uf_company_code` IN ({companies}) AND `uf_batch_sn` IN ({batches})"
        " GROUP BY `uf_mat_code`,`uf_company_code`,`uf_batch_sn`"
    ).format(
        tbl=T_PROD, y=_esc(year), p=_esc(period),
        mats=",".join("'" + _esc(m) + "'" for m in mats),
        companies=",".join("'" + _esc(c) + "'" for c in companies),
        batches=",".join("'" + _esc(b) + "'" for b in batches),
    )
    try:
        rows = db.query_sql(sql) or []
    except Exception as e:
        print("[v_cost] 查询 {} 失败: {}".format(T_PROD, e))
        return out
    for r in rows:
        out[(r.get("uf_mat_code"), r.get("uf_company_code"), r.get("uf_batch_sn"))] = (
            _to_float(r.get("qty_sum")),
            _to_float(r.get("cur_sum")),
            r.get("currency"),
        )
    return out


def _calc_amounts(rows, pc_map, s_map, v_map):
    """逐行按 price_control 算金额(inv)与货币(currency), 写回每行。"""
    for r in rows:
        mat = r.get("mat_code")
        plant = r.get("plant_code")
        batch = r.get("batch_sn")
        basic_qty = _to_float(r.get("basic_qty"))
        pc = pc_map.get((mat, plant))
        inv, cur = None, None
        if pc == PRICE_S:
            rec = s_map.get((mat, plant))
            if rec and rec[0] != 0:  # 分母 ending_inv_qty_sku 不为 0
                inv = round(rec[1] / rec[0] * basic_qty, 2)
                cur = rec[2]
        elif pc == PRICE_V:
            rec = v_map.get((mat, plant, batch))
            if rec and rec[0] != 0:  # 分母 uf_qty_m合计 不为 0
                inv = round(rec[1] / rec[0] * basic_qty, 2)
                cur = rec[2]
        r["inv"] = inv
        r["currency"] = cur



# def standard_cost_update_query(body):
#     """标准成本更新查询接口(框架 HTTP 入口)"""
#     req = Request()
#     res = Response()
#     body = json.loads(req.body())
#     print("body----", body)
#     result = StandardCostUpdate().query(body)
#     res.set_body(json.dumps(result))
#     res.commit(True)



# ==================== 查询核心(不依赖 HTTP 请求, 可独立测试) ====================
def _do_query(body):
    """查询核心: 接收 body({data:{查询条件}, _payload_:{page,filter_info,sort_info}}),
    返回 {code, msg, data, page, rule, display}(对齐 ZZ_standard_cost_update 传出结构; page 分页)。
    """
    db = DbHelper()
    data_filter = body.get("data") or {}
    ext = body.get("_payload_") or {}
    page_info = ext.get("page") or {}
    filter_info = ext.get("filter_info") or {}
    sort_info = ext.get("sort_info") or {}
    rule = {"sort_info": sort_info, "filter_info": filter_info}

    where, year, period, err = _build_where(data_filter)
    if err:
        return {"code": 500, "type": "E", "msg": err, "data": [], "page": {}, "rule": rule, "display": DISPLAY}

    sql = _build_main_sql(where)
    try:
        rows = db.query_sql(sql) or []
    except Exception as e:
        print("[ending_raw] 主查询失败: {}".format(e))
        print("[ending_raw] SQL:\n{}".format(sql))
        return {"code": 500, "type": "E", "msg": "查询失败: {}".format(e),
                "data": [], "page": {}, "rule": rule, "display": DISPLAY}

    if rows:
        # 预取 price_control, 再按 S/V 分别批量取成本数据, 最后逐行算金额
        pc_pairs = {(r.get("mat_code"), r.get("plant_code")) for r in rows}
        pc_map = _load_price_control(pc_pairs, db)
        s_pairs = {k for k in pc_pairs if pc_map.get(k) == PRICE_S}
        v_triples = {
            (r.get("mat_code"), r.get("plant_code"), r.get("batch_sn"))
            for r in rows
            if pc_map.get((r.get("mat_code"), r.get("plant_code"))) == PRICE_V
        }
        s_map = _load_s_cost(s_pairs, year, period, db)
        v_map = _load_v_cost(v_triples, year, period, db)
        _calc_amounts(rows, pc_map, s_map, v_map)

    # 分页: page_size=0 或缺省取全量(对齐前端 _payload_.page 约定)
    total = len(rows)
    page_size = page_info.get("page_size", 0) or 0
    page_num = page_info.get("page_num", 1) or 1
    if page_size > 0:
        start = (page_num - 1) * page_size
        page_items = rows[start:start + page_size]
        page_sum = (total + page_size - 1) // page_size
    else:
        page_items, page_sum = rows, (1 if total else 0)

    return {
        "code": CODE_OK, "msg": "成功",
        "data": page_items,
        "page": {
            "page_size": page_size or total,
            "page_num": page_num,
            "page_sum": page_sum,
            "data_sum": total,
        },
        "rule": rule,
        "display": DISPLAY,
    }


# ==================== 接收入口(框架 HTTP 入口) ====================
def get_ending_raw_material_batch():
    """期末原材料批次库存价值报表 查询接口(框架 HTTP 入口)。
    req.body() 取 {data:{查询条件}, _payload_:{page,filter_info,sort_info}};
    res.set_body 返回 {code, msg, data, page, rule, display}(对齐 ZZ_standard_cost_update)。
    """
    req = Request()
    res = Response()
    try:
        body = json.loads(req.body() or "{}")
    except Exception as e:
        print("[ending_raw] body 解析失败: {}".format(e))
        body = {}
    print("body----", body)
    result = _do_query(body)
    res.set_body(json.dumps(result, ensure_ascii=False))
    res.commit(True)
    return result



if __name__ == "__main__":
    sample_payload = {
        "data": {"year": "2026", "period": "07", "plant_code": "J0008"},
        "_payload_": {"page": {"page_size": 0, "page_num": 1}},
    }
    result = _do_query(sample_payload)
    print("code={} msg={} data_sum={}".format(
        result.get("code"), result.get("msg"), (result.get("page") or {}).get("data_sum")))
    for _row in (result.get("data") or [])[:5]:
        print(_row)
