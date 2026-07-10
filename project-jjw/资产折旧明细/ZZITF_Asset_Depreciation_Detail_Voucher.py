#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@File    : ZZITF_Asset_Depreciation_Detail_Voucher.py
@Date    : 2026/07/08
@explain : 资产折旧明细 -> 会计凭证 接口(接收外部传入, 落库抬头+行项目)

  背景: NC 资产折旧科目不按资产类别划分; 秘火需按资产类型区分不同折旧费用科目。

  本接口职责(与"推 SAP"无关):
    外部系统调用本接口, 把会计凭证(抬头 + 行项目)传过来, 直接落库到:
      ut_fi_voucher_head      会计凭证抬头表(二开: 表名加 ut_ 前缀, 业务字段加 uf_ 前缀)
      ut_fi_voucher_details   会计凭证行项目表
    只插入, 不做删除(调用方需自行保证凭证号唯一)。

  二开命名约定(重要):
    库里 表名加 ut_ 前缀, 业务字段加 uf_ 前缀(审计列 id/create_id/create_time/update_id/update_time/note 不加前缀);
    其他人传入的字段名(逻辑名)和值都不变。
    接口内部"识别并处理": 写库前把行 dict 的键(逻辑名)按规则映射 -> 库表字段名, 例如:
      调用方传 fi_document_number  ->  写库列 uf_fi_document_number
      调用方传 company_code        ->  写库列 uf_company_code

  请求体示例:
    {
      "data": {
        "voucher_data": [
          {
            "header": {
              "fi_document_number": "AA20260708001",
              "company_code": "1000", "year": "2026", "period": "07",
              "department": "D01", "module": "M01",
              "document_date": "20260708", "posting_date": "20260708",
              "header_text": "资产折旧科目调整"
            },
            "items": [
              {"item_no": 1, "accounting_subjects": "1601001010",
               "cost_center": "M01", "debit_credit_mark": "Dr", "amount_tc": 1000.00},
              {"item_no": 2, "accounting_subjects": "6601001010",
               "cost_center": "D01", "debit_credit_mark": "Cr", "amount_tc": 1000.00}
            ]
          }
        ]
      }
    }
"""
from datetime import datetime

from DbHelper import DbHelper
from ToolsMethods import ResetResponse, ResponseData, ResponseStatusCode

# ==================== 表名(集中维护, 便于替换; 二开统一加 ut_ 前缀) ====================
VOUCHER_HEAD = "ut_fi_voucher_head"        # 会计凭证抬头表
VOUCHER_DETAIL = "ut_fi_voucher_details"   # 会计凭证行项目表


_AUDIT_COLS = {"id", "create_id", "create_time", "update_id", "update_time", "note"}


def _uf_row(row):
    """逻辑字段名行 -> 库表字段名行: 业务字段加 uf_ 前缀, 审计列(id/create_*/update_*/note)不加前缀, 值原样保留。

    其他人传入用的是逻辑字段名(fi_document_number 等), 库里业务列名是 uf_ 前缀;
    审计列(create_id/create_time 等)不加前缀。这里统一映射, 避免 batchInsertToDB 按实际列名匹配时静默丢字段。
    """
    return {k if k in _AUDIT_COLS else "uf_" + str(k): v for k, v in row.items()}

# ==================== 抬头固定值(调用方未传时回填的默认值) ====================
FI_LEDGER = "YS0"                   # 财务核算分类帐
DOC_TYPE = "AA02"                   # 财务凭证类型
TRANSACTION_CURRENCY = "CNY"        # 交易货币
HEADER_TEXT = "资产折旧科目调整"      # 抬头文本
DEBIT, CREDIT = "Dr", "Cr"          # 借贷标识

# ==================== 必填字段(逻辑名, 与调用方传入一致) ====================
HEAD_REQUIRED = ["fi_document_number", "company_code", "year", "period",
                 "document_date", "posting_date"]

ITEM_REQUIRED = ["item_no", "accounting_subjects", "debit_credit_mark", "amount_tc"]


def _val(d, key, default=""):
    """取 d[key], None -> default(空串)"""
    v = d.get(key)
    return default if v is None else v


def _validate_head(head):
    """抬头必填校验, 返回错误信息列表(空=通过)"""
    errs = []
    for f in HEAD_REQUIRED:
        if _val(head, f) in ("", None):
            errs.append("抬头缺少必填字段: {}".format(f))
    return errs


def _validate_item(item):
    """行项目必填校验, 返回错误信息列表(空=通过)"""
    errs = []
    for f in ITEM_REQUIRED:
        if _val(item, f) in ("", None):
            errs.append("行项目缺少必填字段: {}".format(f))
    dc = _val(item, "debit_credit_mark")
    if dc and dc not in (DEBIT, CREDIT):
        errs.append("debit_credit_mark 只能是 Dr/Cr, 实际: {}".format(dc))
    return errs


def save_voucher(voucher_data, user_id=0):
    """保存会计凭证(抬头 + 行项目), 直接插入(不做删除)。

    :param voucher_data: 凭证列表, 每张 = {"header": {...}, "items": [{...}, ...]}
                         (传单个 dict 也可, 内部自动包成列表)
    :param user_id:      操作人 id, 透传给 batchInsertToDB 写 create_id
    :return: {"type": "S"/"E", "message": ..., "head_count": n, "item_count": n}
    """
    db = DbHelper()

    # 兼容单张凭证 dict / 列表
    if isinstance(voucher_data, dict):
        voucher_data = [voucher_data]
    if not voucher_data:
        return {"type": "E", "message": "无待保存数据", "head_count": 0, "item_count": 0}

    head_rows, item_rows = [], []
    errors = []

    for idx, doc in enumerate(voucher_data):
        head = doc.get("header") or {}
        items = doc.get("items") or []

        # ---- 抬头校验 ----
        head_errs = _validate_head(head)
        if head_errs:
            errors.append("第{}张凭证: {}".format(idx + 1, "; ".join(head_errs)))
            continue

        # ---- 行项目校验 ----
        if not items:
            errors.append("第{}张凭证: 行项目为空".format(idx + 1))
            continue
        item_errs = []
        for j, it in enumerate(items):
            for e in _validate_item(it):
                item_errs.append("第{}行: {}".format(j + 1, e))
        if item_errs:
            errors.append("第{}张凭证: {}".format(idx + 1, "; ".join(item_errs)))
            continue

        doc_no = _val(head, "fi_document_number")

        # ---- 抬头补默认值(逻辑名) ----
        head_row = dict(head)
        head_row.setdefault("fi_ledger", FI_LEDGER)
        head_row.setdefault("accounting_document_type", DOC_TYPE)
        head_row.setdefault("transaction_currency", TRANSACTION_CURRENCY)
        head_row.setdefault("header_text", HEADER_TEXT)
        head_row["attachment_qty"] = head_row.get("attachment_qty", len(items))
        head_rows.append(head_row)

        # ---- 行项目回填凭证号(逻辑名, 与抬头一致) ----
        for it in items:
            row = dict(it)
            row["fi_document_number"] = doc_no
            item_rows.append(row)

    # 有任一张凭证校验不过 -> 整批不落库, 返回明细错误
    if errors:
        return {"type": "E", "message": "校验失败: " + " | ".join(errors),
                "head_count": 0, "item_count": 0}

    # ---- 二开前缀: 逻辑字段名 -> 库表字段名(业务字段加 uf_, 审计列不加), 值不变 ----
    # create_id 由 batchInsertToDB 按 user_id 自动补; create_time 框架不补, 这里手动给
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for r in head_rows:
        r.setdefault("create_time", now)
    for r in item_rows:
        r.setdefault("create_time", now)
    head_rows = [_uf_row(r) for r in head_rows]
    item_rows = [_uf_row(r) for r in item_rows]

    # ---- 直接落库(行键已是 ut_ 库表字段名, batchInsertToDB 按实际列匹配落库) ----
    db.batchInsertToDB(VOUCHER_HEAD, head_rows, user_id=user_id)
    db.batchInsertToDB(VOUCHER_DETAIL, item_rows, user_id=user_id)

    return {"type": "S",
            "message": "保存成功: 抬头{}张, 行项目{}行".format(len(head_rows), len(item_rows)),
            "head_count": len(head_rows), "item_count": len(item_rows)}


@ResetResponse(params=["voucher_data"], user_id=True)
def asset_depreciation_voucher_save(voucher_data, user_id=0):
    """会计凭证接收接口: 外部系统传入凭证(抬头+行项目), 落库到抬头表/行项目表。

    请求体: {"data": {"voucher_data": [ {"header": {...}, "items": [...]} ] }}
    :return: ResponseData(code=200 成功 / 400 失败, msg, data)
    """
    res = save_voucher(voucher_data, user_id=user_id)
    if res["type"] == "S":
        return ResponseData(ResponseStatusCode.Success, res["message"], res)
    return ResponseData(ResponseStatusCode.Error, res["message"], res)


if __name__ == "__main__":
    sample = [
        {
            "header": {
                "fi_document_number": "AA20260708-TEST-001",
                "company_code": "1000", "year": "2026", "period": "07",
                "department": "D01", "module": "M01",
                "document_date": "20260708", "posting_date": "20260708",
            },
            "items": [
                {"item_no": 1, "accounting_subjects": "1601001010",
                 "cost_center": "M01", "debit_credit_mark": "Dr", "amount_tc": 1000.00},
                {"item_no": 2, "accounting_subjects": "6601001010",
                 "cost_center": "D01", "debit_credit_mark": "Cr", "amount_tc": 1000.00},
            ],
        }
    ]
    print(save_voucher(sample, user_id=0))
