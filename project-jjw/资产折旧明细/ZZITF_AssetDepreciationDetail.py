#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@File    : ZZITF_AssetDepreciationDetail.py
@Date    : 2026/07/09
@Author  : yang.zhang@dxdstech.com
@explain : 资产折旧明细接收接口: 前端传 data, 落库 ut_discount_details

  职责:
    前端把折旧明细参数放在 body.data 里调本接口, 直接插入 ut_discount_details 表。
    必填: year, period, company_code, asset_code, item; 其余字段有则存, 无则不存。

  请求体示例:
    {
      "data": {
        "year": "2026", "period": "07", "company_code": "1000",
        "asset_code": "A0001", "item": 1,
        "asset_type": "机器设备", "currency_amount": 1200.00,
        "currency": "CNY", "center": "D01", "module": "M01", "text": "7月折旧"
      }
    }
"""
from datetime import datetime

from DbHelper import DbHelper
from ToolsMethods import ResetResponse, ResponseData, ResponseStatusCode

# ==================== 表名(二开表名加 ut_ 前缀) ====================
TABLE = "ut_discount_details"

# ==================== 字段映射: 前端逻辑名 -> 库表字段名 ====================
# 业务字段 uf_ 前缀; 注意 uf_Item/uf_Module/uf_Text 建表首字母大写,
# batchInsertToDB 按 information_schema.COLUMN_NAME 严格大小写匹配列名, 必须与建表完全一致。
FIELD_MAP = {
    "year":            "uf_year",
    "period":          "uf_period",
    "company_code":    "uf_company_code",
    "asset_code":      "uf_asset_code",
    "asset_type":      "uf_asset_type",
    "item":            "uf_Item",
    "currency_amount": "uf_currency_amount",
    "currency":        "uf_currency",
    "center":          "uf_center",
    "module":          "uf_Module",
    "text":            "uf_Text",
    "note":            "note",
}

# 必填字段(逻辑名, 与前端传入一致)
REQUIRED = ["year", "period", "company_code", "asset_code", "item"]


def _val(d, key, default=""):
    """取 d[key], None -> default(空串)"""
    v = d.get(key)
    return default if v is None else v


def save_discount_detail(detail, user_id=0):
    """保存资产折旧明细到 ut_discount_details, 直接插入(不做删除)。

    :param detail:  单条 dict {year, period, company_code, asset_code, item, ...}
                    (传 list[dict] 也可, 内部按条校验后批量插入)
    :param user_id: 操作人 id, 透传给 batchInsertToDB 自动写 create_id
    :return: {"type": "S"/"E", "message": ..., "count": n}
    """
    db = DbHelper()

    # 兼容单条 dict / 列表
    if isinstance(detail, dict):
        details = [detail]
    elif isinstance(detail, list):
        details = detail
    else:
        return {"type": "E", "message": "无待保存数据", "count": 0}
    if not details:
        return {"type": "E", "message": "无待保存数据", "count": 0}

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows, errors = [], []

    for idx, d in enumerate(details):
        # ---- 必填校验 ----
        missing = [f for f in REQUIRED if _val(d, f) in ("", None)]
        if missing:
            errors.append("第{}条: 缺少必填字段 {}".format(idx + 1, ",".join(missing)))
            continue

        # ---- 组行: 只放 FIELD_MAP 里"有值"的字段(有则存, 没有不存) ----
        row = {}
        for logical, col in FIELD_MAP.items():
            if logical in d and d[logical] is not None and d[logical] != "":
                row[col] = d[logical]
        # create_time 框架不自动补, 这里补上; create_id 由 batchInsertToDB 按 user_id 自动写
        row["create_time"] = now
        rows.append(row)

    # 有任一条校验不过 -> 整批不落库, 返回明细错误
    if errors:
        return {"type": "E", "message": "校验失败: " + " | ".join(errors), "count": 0}

    # ---- 直接落库(行键已是库表字段名; batchInsertToDB 按实际列名匹配, 自动补 create_id) ----
    db.batchInsertToDB(TABLE, rows, user_id=user_id)

    return {"type": "S", "message": "保存成功: {}条".format(len(rows)), "count": len(rows)}


@ResetResponse(params=["year", "period", "company_code", "asset_code", "item"], user_id=True)
def asset_depreciation_detail_save(year, period, company_code, asset_code, item, user_id=0, **extra):
    """资产折旧明细接收接口: 前端传 data, 落库 ut_discount_details。

    必填: year, period, company_code, asset_code, item
    可选(有则存, 没有不存): asset_type, currency_amount, currency, center, module, text, note
    请求体: {"data": {"year":..., "period":..., "company_code":..., "asset_code":..., "item":..., ...}}
    :return: ResponseData(code=200 成功 / 400 失败, msg, data)
    """
    detail = {
        "year": year, "period": period, "company_code": company_code,
        "asset_code": asset_code, "item": item,
    }
    detail.update(extra)  # 其余可选字段有则带入
    res = save_discount_detail(detail, user_id=user_id)
    if res["type"] == "S":
        return ResponseData(ResponseStatusCode.Success, res["message"], res)
    return ResponseData(ResponseStatusCode.Error, res["message"], res)


if __name__ == "__main__":
    sample = {
        "year": "2026", "period": "07", "company_code": "1000",
        "asset_code": "A0001", "item": 1,
        "asset_type": "机器设备", "currency_amount": 1200.00,
        "currency": "CNY", "center": "D01", "module": "M01", "text": "7月折旧",
    }
    print(save_discount_detail(sample, user_id=0))
