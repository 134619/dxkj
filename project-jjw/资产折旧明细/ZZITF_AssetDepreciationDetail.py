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

根据ut_discount_details表中uf_asset_type，对比ut_data_relation_mapping表中的uf_out_field_code1_desc,取uf_field_code1_desc和uf_field_code2_desc的值
然后去调用document_post接口，生成凭证号后将数据保存到ut_fi_voucher_head和ut_fi_voucher_item表中



"""

from datetime import datetime

from DbHelper import DbHelper
from DxManualVoucherEntry import document_post, document_rev

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

# ==================== 返回前端 code ====================
CODE_OK = 200  # 成功
CODE_MISSING_PARAM = 401  # 缺少参数 / 校验失败

# ==================== 凭证落库表名 + 科目映射表 ====================
VOUCHER_HEAD = "ut_fi_voucher_head"  # 财务凭证抬头(二开; 与 save_voucher 同表)
VOUCHER_ITEM = (
    "ut_fi_voucher_item"  # 财务凭证行项目(二开; 注意不是 ut_fi_voucher_details)
)
MAP_TABLE = "ut_data_relation_mapping"  # 资产类型 → 借/贷科目 映射表

# 二开前缀: 业务字段加 uf_, 审计列(id/create_*/update_*/note)不加; 与 save_voucher 一致
_AUDIT_COLS = {"id", "create_id", "create_time", "update_id", "update_time", "note"}
DEBIT, CREDIT = "Dr", "Cr"  # 借贷标识


def _val(d, key, default=""):
    """取 d[key], None -> default(空串)"""
    v = d.get(key)
    return default if v is None else v


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _esc(v):
    """SQL 字符串转义"""
    return str(v).replace("'", "''") if v is not None else ""


def _uf_row(row):
    """逻辑字段名行 → 库表字段名行: 业务字段加 uf_ 前缀, 审计列不加, 值原样。"""
    return {k if k in _AUDIT_COLS else "uf_" + str(k): v for k, v in row.items()}


def save_discount_detail(detail, user_id=0):
    """保存资产折旧明细到 ut_discount_details, 直接插入(不做删除)。
    :return: {"type": "S"/"E", "message": ..., "count": n}
    """

    db = DbHelper()

    # 兼容单条 dict / 列表
    if isinstance(detail, dict):
        details = [detail]
    elif isinstance(detail, list):
        details = detail
    else:
        return {
            "type": "E",
            "code": CODE_MISSING_PARAM,
            "message": "无待保存数据",
            "count": 0,
        }
    if not details:
        return {
            "type": "E",
            "code": CODE_MISSING_PARAM,
            "message": "无待保存数据",
            "count": 0,
        }

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
        return {
            "type": "E",
            "code": CODE_MISSING_PARAM,
            "message": "校验失败: " + " | ".join(errors),
            "count": 0,
        }

    # ---- 直接落库(行键已是库表字段名; batchInsertToDB 按实际列名匹配, 自动补 create_id) ----
    db.batchInsertToDB(TABLE, rows, user_id=user_id)
    return {
        "type": "S",
        "code": CODE_OK,
        "message": "保存成功: {}条".format(len(rows)),
        "count": len(rows),
    }


def _post_depreciation_voucher(details, user_id, db):
    """明细落库后, 按资产类型生成财务凭证: 查科目映射 → 调 document_post 过账 → 落 ut_fi_voucher_head/item。
    :return {"ok": [fi_document_number,...], "errs": [msg,...]}
    """
    # 1. 批量查科目映射: asset_type 匹配 uf_out_field_code1_desc → (借方科目=uf_field_code1_desc, 贷方科目=uf_field_code2_desc)
    asset_types = {
        _val(d, "asset_type")
        for d in details
        if isinstance(d, dict) and _val(d, "asset_type")
    }
    mapping = {}
    if asset_types:
        in_list = ",".join("'" + _esc(a) + "'" for a in asset_types)
        try:
            rows = (
                db.query_sql(
                    "SELECT `uf_out_field_code1_desc`,`uf_field_code1_desc`,`uf_field_code2_desc`"
                    " FROM `{}` WHERE `uf_out_field_code1_desc` IN ({})".format(
                        MAP_TABLE, in_list
                    )
                )
                or []
            )
            print(
                (
                    "SELECT `uf_out_field_code1_desc`,`uf_field_code1_desc`,`uf_field_code2_desc`"
                    " FROM `{}` WHERE `uf_out_field_code1_desc` IN ({})".format(
                        MAP_TABLE, in_list
                    )
                )
                or []
            )
            for r in rows:
                mapping[r.get("uf_out_field_code1_desc")] = (
                    r.get("uf_field_code1_desc"),
                    r.get("uf_field_code2_desc"),
                )
        except Exception as e:
            print("[voucher] 查询 {} 失败: {}".format(MAP_TABLE, e))

    head_rows, item_rows, ok_list, errs = [], [], [], []

    for idx, d in enumerate(details):
        if not isinstance(d, dict):
            continue
        asset_code = _val(d, "asset_code")
        asset_type = _val(d, "asset_type")
        amt = _val(d, "currency_amount")

        # 1) 映射命中
        if asset_type not in mapping:
            errs.append(
                "第{}条 资产{}: 资产类型[{}]无科目映射".format(
                    idx + 1, asset_code, asset_type
                )
            )
            continue
        debit_subj, credit_subj = mapping[asset_type]

        # 2) 前端补传的过账必填字段
        company_code = _val(d, "company_code")
        posting_date = _val(d, "posting_date")
        document_date = _val(d, "document_date")
        doc_type = _val(d, "accounting_document_type")
        if not (
            company_code and posting_date and document_date and doc_type
        ) or amt in ("", None):
            errs.append(
                "第{}条 资产{}: 缺少过账必填"
                "(posting_date/document_date/accounting_document_type/currency_amount)".format(
                    idx + 1, asset_code
                )
            )
            continue

        currency = _val(d, "currency") or "CNY"
        cost_center = _val(d, "center")
        header_text = _val(d, "text") or "资产折旧"

        # 3) 构造 document_post 入参(fi_document_number 置空 → 过账时由平台生成)
        head = {
            "company_code": company_code,
            "posting_date": posting_date,
            "document_date": document_date,
            "accounting_document_type": doc_type,
            "transaction_currency": currency,
            "header_text": header_text,
            "fi_document_number": "",
        }
        item = [
            {
                "accounting_subjects": debit_subj,
                "debit_credit_mark": DEBIT,
                "transaction_currency_amount": amt,
                "transaction_currency": currency,
                **({"cost_center": cost_center} if cost_center else {}),
            },
            {
                "accounting_subjects": credit_subj,
                "debit_credit_mark": CREDIT,
                "transaction_currency_amount": amt,
                "transaction_currency": currency,
                **({"cost_center": cost_center} if cost_center else {}),
            },
        ]

        # 4) 调 document_post(test_run=0 正式; 内部落标准分表 t_fi_voucher_details_{co}_{yr}{pd} 并返回凭证号)
        try:
            code, msg, error_list, year, fi_document_number = document_post(
                0, user_id, head, item
            )
        except Exception as e:
            errs.append(
                "第{}条 资产{}: document_post 异常: {}".format(idx + 1, asset_code, e)
            )
            continue
        if code != 200 or not fi_document_number:
            errs.append(
                "第{}条 资产{}: 过账失败 {}".format(
                    idx + 1, asset_code, msg or ";".join(error_list or [])
                )
            )
            continue

        # 5) 组装二开凭证行(逻辑名; 落库前 _uf_row 加 uf_ 前缀)
        period = _val(d, "period") or posting_date[5:7]
        head_rows.append(
            {
                "fi_document_number": fi_document_number,
                "company_code": company_code,
                "year": year or posting_date[:4],
                "period": period,
                "document_date": document_date,
                "posting_date": posting_date,
                "accounting_document_type": doc_type,
                "transaction_currency": currency,
                "header_text": header_text,
                "create_time": _now(),
            }
        )
        for row_no, (subj, dc) in enumerate(
            [(debit_subj, DEBIT), (credit_subj, CREDIT)], start=1
        ):
            row = {
                "item_no": row_no,
                "fi_document_number": fi_document_number,
                "accounting_subjects": subj,
                "debit_credit_mark": dc,
                "amount_tc": amt,  # ← ut_fi_voucher_item 金额列名按 save_voucher 推断, 需 dump 核对
                "create_time": _now(),
            }
            if cost_center:
                row["cost_center"] = cost_center
            item_rows.append(row)
        ok_list.append(fi_document_number)

    # 6) 落二开凭证表(逻辑名 → uf_ 前缀; batchInsertToDB 按实际列名匹配, 列名不符会静默丢字段)
    if head_rows:
        db.batchInsertToDB(
            VOUCHER_HEAD, [_uf_row(r) for r in head_rows], user_id=user_id
        )
    if item_rows:
        db.batchInsertToDB(
            VOUCHER_ITEM, [_uf_row(r) for r in item_rows], user_id=user_id
        )
    return {"ok": ok_list, "errs": errs}


def save_asset_depreciation_detail(payload, user_id):
    """资产折旧明细接收接口
    接收参数: {"interface_code":..., "payload":{"guid":..., "data":[{year,period,company_code,asset_code,item,...}, ...]}}
    :return {"type":"S"/"E", "message":...}
    """

    data = payload.get("data") if isinstance(payload, dict) else payload
    if isinstance(data, dict):
        data = [data]
    if not data:
        return {"type": "E", "code": CODE_MISSING_PARAM, "message": "无数据(data 为空)"}
    res = save_discount_detail(data, user_id=user_id)
    if res["type"] != "S":
        return {
            "type": res["type"],
            "code": res.get("code", CODE_MISSING_PARAM),
            "message": res["message"],
        }

    # 明细落库成功 → 按资产类型生成财务凭证(document_post 过账 + 落 ut_fi_voucher_head/item)
    voucher_res = _post_depreciation_voucher(data, user_id, DbHelper())

    msg = "明细 {} 条".format(res["count"])
    if voucher_res["errs"]:
        msg += "; 凭证失败: " + " | ".join(voucher_res["errs"])
    return {
        "type": "S",
        "code": CODE_OK,
        "message": msg,
        "count": res["count"],
        "voucher_ok": len(voucher_res["ok"]),
    }


if __name__ == "__main__":
    sample = {
        "year": "2026",
        "period": "07",
        "company_code": "J008",
        "asset_code": "A0001",
        "item": 1,
        "asset_type": "电子设备",
        "currency_amount": 1200.00,
        "currency": "CNY",
        "center": "D01",
        "module": "M01",
        "text": "7月折旧",
        # 凭证过账必填(折旧明细只有 year/period, 以下由前端补传)
        "posting_date": "2026-07-31",
        "document_date": "2026-07-31",
        "accounting_document_type": "AA02",
    }
    # 走完整链路: 落明细 → 查映射 → document_post 过账 → 落 ut_fi_voucher_head/item
    print(save_asset_depreciation_detail({"data": [sample]}, user_id=0))
