#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@File    : ZZEXT_EndingInventory.py
@Date    : 2026/07/16
@Author  : yang.zhang@dxdstech.com
@explain : 期末库存查询接口

传入参数(查询条件, 均可选; 传哪个按哪个过滤):
    plant_code      工厂代码     → plant_data.plant_code
    mat_code        物料编码     → plant_data.mat_code
    stor_loc_code   库存地点     → plant_data.stor_loc_code(物料默认收货库位)
    mat_type        物料类型     → basic_data.mat_type
    mat_group       物料组       → basic_data.mat_group
    # batch_sn / po_sn / vendor_code 这四张表里没有, 传了会被忽略


传出数据(每行 = 一个 物料×工厂):
    mat_code / mat_description               物料编码/描述
    plant_code                               工厂代码
    plant_name                               工厂名称        (主数据无 → 空)
    stor_loc_code                            库存地点        (物料默认收货库位)
    stor_loc_description                     库存地点描述    (主数据无 → 空)
    batch_sn                                 批次号          (主数据无 → 空)
    basic_uom / basic_qty                    基本单位/数量   (数量主数据无 → 空)
    cost_uom / cost_qty                      成本单位/数量   (数量主数据无 → 空)
    parallel_uom / parallel_qty              平行单位/数量   (数量主数据无 → 空)
    inventory_status / inventory_status_description  库存状态/描述  (主数据无 → 空)
    po_sn / po_items                         采购订单/行号   (主数据无 → 空)
    vendor_code / vendor_name                供应商编码/描述 (主数据无 → 空)
"""

from DbHelper import DbHelper

# ==================== 返回前端 code ====================
CODE_OK = 200             # 成功
CODE_MISSING_PARAM = 401  # 缺少参数 / 查询失败

T_BASIC = "t_mmd_material_basic_data"
T_PLANT = "t_mmd_material_plant_data"
T_FINANCIAL = "t_mmd_material_financial_data"
T_COST = "t_mmd_material_cost_data"


FILTER_COLS = {
    "plant_code": "p.`plant_code`",
    "mat_code": "p.`mat_code`",
    "stor_loc_code": "p.`stor_loc_code`",
    "mat_type": "b.`mat_type`",
    "mat_group": "b.`mat_group`",
}


def _esc(v):
    """SQL 字符串转义(单引号 → 两个单引号)"""
    return str(v).replace("'", "''") if v is not None else ""


def _extract_filter(payload):
    """从 payload 取过滤条件 dict; 兼容 {data:[...]} / {payload:{data:[...]}} / 扁平 dict。"""
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    if data is None:
        inner = payload.get("payload")
        if isinstance(inner, dict):
            data = inner.get("data")
    if isinstance(data, list):
        return data[0] if data and isinstance(data[0], dict) else {}
    if isinstance(data, dict):
        return data
    return payload  # 直接当扁平过滤条件


def _build_where(flt):
    """按 FILTER_COLS 把非空条件拼成 'AND ... AND ...'(无则空串)。"""
    clauses = []
    for key, col in FILTER_COLS.items():
        val = flt.get(key) if isinstance(flt, dict) else None
        if val is None or val == "":
            continue
        if isinstance(val, (list, tuple)):
            vals = [str(v) for v in val if str(v) != ""]
            if not vals:
                continue
            in_list = ",".join("'" + _esc(v) + "'" for v in vals)
            clauses.append("{} IN ({})".format(col, in_list))
        else:
            clauses.append("{} = '{}'".format(col, _esc(val)))
    return " ".join("AND " + c for c in clauses)


def _build_inventory_sql(where):
    return """
SELECT
    b.`mat_code`,
    b.`mat_description`,
    p.`plant_code`,
    '' AS `plant_name`,
    p.`stor_loc_code`,
    '' AS `stor_loc_description`,
    '' AS `batch_sn`,
    b.`basic_uom`,
    '' AS `basic_qty`,
    c.`cost_uom`,
    '' AS `cost_qty`,
    b.`parallel_uom`,
    '' AS `parallel_qty`,
    '' AS `inventory_status`,
    '' AS `inventory_status_description`,
    '' AS `po_sn`,
    '' AS `po_items`,
    '' AS `vendor_code`,
    '' AS `vendor_name`
FROM `{T_PLANT}` p
JOIN `{T_BASIC}` b ON b.`mat_code` = p.`mat_code`
LEFT JOIN `{T_FINANCIAL}` f ON f.`mat_code` = p.`mat_code` AND f.`plant_code` = p.`plant_code`
LEFT JOIN `{T_COST}` c ON c.`mat_code` = p.`mat_code` AND c.`plant_code` = p.`plant_code`
WHERE 1 = 1
{where}
""".format(T_PLANT=T_PLANT, T_BASIC=T_BASIC, T_FINANCIAL=T_FINANCIAL, T_COST=T_COST, where=where)


def get_ending_inventory(payload, user_id):
    """查询期末库存(仅物料主数据四表; 库存交易类字段置空)。
    :param payload: 见模块 docstring 的数据格式(过滤条件)
    :param user_id: 操作人 id(预留)
    :return {"type":"S"/"E", "code":..., "message":..., "data":[...], "count": n}
    """
    db = DbHelper()
    flt = _extract_filter(payload)
    where = _build_where(flt)
    sql = _build_inventory_sql(where)
    try:
        rows = db.query_sql(sql) or []
    except Exception as e:
        print("[ending_inventory] 查询失败: {}".format(e))
        print("[ending_inventory] SQL:\n{}".format(sql))  # 失败时打出实际 SQL 便于定位
        return {"type": "E", "code": CODE_MISSING_PARAM,
                "message": "查询失败: {}".format(e), "data": [], "count": 0}
    return {"type": "S", "code": CODE_OK, "message": "查询成功",
            "data": rows, "count": len(rows)}


if __name__ == "__main__":
    # 本地测试: 过滤条件均可选, 改成你想测的组合(标量 → =, 列表 → IN)
    sample_payload = {
        "payload": {
            "data": [
                {
                    "plant_code": "J0008",
                    "mat_code": "J11020010001",
                    # "stor_loc_code": "02",
                    # "batch_sn": "...",
                    # "mat_type": "...",
                    # "mat_group": "...",
                    # "po_sn": "...",
                    # "vendor_code": "...",
                }
            ]
        }
    }
    result = get_ending_inventory(sample_payload, user_id=0)
    print("type={} count={} message={}".format(result.get("type"), result.get("count"), result.get("message")))
    for _row in (result.get("data") or [])[:5]:
        print(_row)
