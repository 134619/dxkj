#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@File    : ZZITF_AssetDepreciationDetail.py
@Date    : 2026/07/09
@Author  : yang.zhang@dxdstech.com
@explain : 资产折旧明细接收接口: 前端传 data, 落库 ut_discount_details

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
然后去调用document_post接口，生成凭证号后将数据保存到t_fi_voucher_head和t_fi_voucher_details表中

"""

from datetime import datetime

from DbHelper import DbHelper
from DxManualVoucherEntry import document_post

# ==================== 明细表 ====================
TABLE = "ut_discount_details"

# 字段映射: 前端逻辑名 -> 库表字段名(业务字段 uf_ 前缀, 全小写; batchInsertToDB 按列名严格匹配)
FIELD_MAP = {
    "year": "uf_year",
    "period": "uf_period",
    "company_code": "uf_company_code",
    "asset_code": "uf_asset_code",
    "asset_type": "uf_asset_type",
    "item": "uf_item",
    "currency_amount": "uf_currency_amount",
    "currency": "uf_currency",
    "center": "uf_center",
    "module": "uf_module",
    "text": "uf_text",
    "note": "note",
}
REQUIRED = ["year", "period", "company_code", "asset_code", "item"]  # 必填(逻辑名)

# ==================== 凭证落库 ====================
VOUCHER_HEAD = "t_fi_voucher_head"  # 财务凭证抬头(平台标准表, 无 uf_ 前缀)
VOUCHER_ITEM = "t_fi_voucher_details"  # 财务凭证行项目(标准表; 行号列 fi_document_item)
MAP_TABLE = "ut_data_relation_mapping"  # 资产类型 → 借/贷科目 映射表
DOCUMENT_CATEGORY = "FSDC"
DOC_TYPE = "AA02"  # 财务凭证类型(过账缺省兜底; 与 ZZITF_Asset_Depreciation_Detail_Voucher 一致)
FI_LEDGER = (
    "YS0"  # 财务核算分类账(t_fi_voucher_head.fi_ledger NOT NULL; 与 save_voucher 一致)
)
DEBIT, CREDIT = "Dr", "Cr"  # 借贷标识

# 凭证 upsert 去重键(列名与标准表一致)
HEAD_KEY = ("company_code", "fi_document_number", "year", "fi_ledger")
ITEM_KEY = (
    "fi_document_number",
    "fi_document_item",
    "fi_ledger",
    "company_code",
    "year",
)

# ==================== 返回前端 code ====================
CODE_OK = 200  # 成功
CODE_MISSING_PARAM = 401  # 缺少参数 / 校验失败


# ==================== 基础工具 ====================
def _val(d, key, default=""):
    """取 d[key], None -> default(空串)"""
    v = d.get(key)
    return default if v is None else v


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _esc(v):
    """SQL 字符串转义"""
    return str(v).replace("'", "''") if v is not None else ""


def _ci_get(d, key):
    """大小写不敏感取 dict 值(query_sql 返回键大小写不确定时兜底)"""
    if not isinstance(d, dict):
        return None
    if key in d:
        return d[key]
    lk = str(key).lower()
    for k, v in d.items():
        if str(k).lower() == lk:
            return v
    return None


def _normalize_to_list(data):
    """dict -> [dict]; list -> 原样; 其它 -> None。"""
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data
    return None


# ==================== NOT NULL 列自动补占位(根治 ORA-01400) ====================
_NOTNULL_CACHE = {}  # table -> [(column_name, data_type_upper), ...]

# 框架自动管理的列, 自动补值不碰(id 主键序列生成; create_id 按 user_id 填; *_time 框架补)
_AUTOFILL_SKIP = {"id", "create_id", "update_id", "create_time", "update_time"}


def _notnull_cols(table, db):
    """查表所有 NOT NULL 列(带缓存); 走框架 schema 反射 get_columns_by_table(同文件
    save_discount_detail 已验证 Oracle 可用), 不直接查 all_tab_columns(框架会把它双引号小写化 → ORA-00942)。
    nullable/data_type 键名兼容多种命名(information_schema / Oracle)。
    :return [(column_name, data_type_upper), ...]; 查询失败返回 [](不阻断主流程)"""
    if table in _NOTNULL_CACHE:
        return _NOTNULL_CACHE[table]
    cols = []
    try:
        raw = db.get_columns_by_table(table) or []
        for c in raw:
            if not isinstance(c, dict):
                continue
            # nullable 键名兼容: Oracle NULLABLE='N' / information_schema IS_NULLABLE='NO' / 布尔 False
            nullable_val = None
            for nk in ("nullable", "is_nullable", "NULLABLE", "IS_NULLABLE", "null"):
                if nk in c:
                    nullable_val = c[nk]
                    break
            # NOT NULL: 'N'/'NO'/False/'FALSE'/'0'(表结构 dump 中 false 列 == 报 ORA-01400 的列)
            if str(nullable_val).strip().upper() in ("N", "NO", "FALSE", "0"):
                dt = ""
                for tk in ("data_type", "type", "DATA_TYPE", "COLUMN_TYPE"):
                    if tk in c:
                        dt = str(c[tk] or "").upper()
                        break
                cols.append((_ci_get(c, "name"), dt))
    except Exception as e:
        print("[notnull] 读取 {} 列信息失败: {}".format(table, e))
    # 没识别到 NOT NULL 列时, 打印列字典键名以便定位 nullable 字段(框架版本相关)
    if not cols:
        try:
            raw = db.get_columns_by_table(table) or []
            if raw and isinstance(raw[0], dict):
                print(
                    "[notnull] {} 未识别到 NOT NULL 列, 列字典键: {}".format(
                        table, list(raw[0].keys())
                    )
                )
        except Exception:
            pass
    _NOTNULL_CACHE[table] = cols
    return cols


def _fill_notnull(table, rows, db):
    """为 NOT NULL 列补占位值(Oracle 空串即 NULL, NOT NULL 列给空会撞 ORA-01400)。
    rows 键须为库表真实列名: CHAR/VARCHAR/CLOB → 单空格, NUMBER/INT/FLOAT → 0。
    仅补"空"值, 已有非空值不覆盖; DATE/TIMESTAMP 不强制(由调用方补 create_time 等)。"""
    nn = _notnull_cols(table, db)
    if not nn:
        return rows
    for r in rows:
        for col, dt in nn:
            if not col or str(col).lower() in _AUTOFILL_SKIP:
                continue
            if r.get(col) in ("", None):
                if "CHAR" in dt or "CLOB" in dt:
                    r[col] = " "
                elif (
                    dt.startswith("NUMBER")
                    or "INT" in dt
                    or "FLOAT" in dt
                    or "DECIMAL" in dt
                ):
                    r[col] = 0
                elif "DATE" in dt or "TIME" in dt:  # DATE / DATETIME / TIMESTAMP
                    r[col] = _now()
    return rows


# ==================== 通用 upsert(查已有 id → 命中更新 / 否则新建) ====================
def _fetch_existing_ids(table, key_cols, filter_col, rows, db):
    """查 table 中 filter_col 命中的已有行, 按 key_cols 组键返回 {key_tuple: id}。
    查询失败返回 {}(本批全部走新建)。读值用 _ci_get 兜底结果键大小写。"""
    filt_vals = sorted(
        {
            str(r.get(filter_col))
            for r in rows
            if str(r.get(filter_col)) not in ("", "None")
        }
    )
    existing = {}
    if not filt_vals:
        return existing
    in_list = ",".join("'" + _esc(x) + "'" for x in filt_vals)
    sel = ", ".join("`{}`".format(c) for c in (["id"] + key_cols))
    try:
        ex = (
            db.query_sql(
                "SELECT {0} FROM `{1}` WHERE `{2}` IN ({3})".format(
                    sel, table, filter_col, in_list
                )
            )
            or []
        )
    except Exception as e:
        print("[upsert] 查询 {} 已有行失败, 本批全部走新建: {}".format(table, e))
        return existing
    for er in ex:
        k = tuple(str(_ci_get(er, c)) for c in key_cols)
        if k not in existing:
            existing[k] = _ci_get(er, "id")
    return existing


def _upsert_by_key(table, rows, key_cols, filter_col, db, user_id, fill_notnull=False):
    """按 key_cols 去重 upsert: 以 filter_col IN(...) 拉已有行, Python 内按完整 key_cols 精确匹配,
    命中→按 id 更新, 否则→新建(任一 key 列为空的行无法判重, 走新建)。
    fill_notnull=True 时仅给新建行补 NOT NULL 占位(更新行只改指定列, 不被占位覆盖)。
    :return (insert_count, update_count)
    """
    if not rows:
        return 0, 0
    key_cols = list(key_cols)
    existing = _fetch_existing_ids(table, key_cols, filter_col, rows, db)

    to_insert, to_update = [], []
    for r in rows:
        vals = [r.get(c) for c in key_cols]
        if any(str(v) in ("", "None") for v in vals):
            to_insert.append(r)  # 去重键不全 → 无法判重 → 新建
            continue
        k = tuple(str(v) for v in vals)
        if k in existing:
            r["id"] = existing[k]
            r.pop("create_time", None)  # 更新不改创建时间
            to_update.append(r)
        else:
            to_insert.append(r)

    if to_insert:
        rows_to_insert = (
            _fill_notnull(table, to_insert, db) if fill_notnull else to_insert
        )
        db.batchInsertToDB(table, rows_to_insert, user_id=user_id)
    if to_update:
        db.batchUpdateToDB(table, to_update, user_id=user_id)
    return len(to_insert), len(to_update)


# ==================== 明细落库 (ut_discount_details) ====================
def _resolve_field_map(db):
    """按库表真实列名(大小写)校正 FIELD_MAP, 返回 (field_map, real_cols)。
    batchInsertToDB 按列名严格匹配, 大小写不一致字段会被静默丢弃, 故需按库表真实大小写校正。"""
    real_cols = {
        str(c.get("name", "")).lower(): c.get("name")
        for c in (db.get_columns_by_table(TABLE) or [])
    }
    field_map = {
        logical: real_cols.get(str(col).lower(), col)
        for logical, col in FIELD_MAP.items()
    }
    return field_map, real_cols


def _build_detail_rows(details, field_map, now):
    """必填校验 + 组行(仅落 field_map 里有值的字段); 返回 (rows, errors)。"""
    rows, errors = [], []
    for idx, d in enumerate(details):
        missing = [f for f in REQUIRED if _val(d, f) in ("", None)]
        if missing:
            errors.append("第{}条: 缺少必填字段 {}".format(idx + 1, ",".join(missing)))
            continue
        row = {}
        for logical, col in field_map.items():
            if logical in d and d[logical] is not None and d[logical] != "":
                row[col] = d[logical]
        row["create_time"] = now  # create_id 由 batchInsertToDB 按 user_id 自动写
        rows.append(row)
    return rows, errors


def save_discount_detail(detail, user_id=0):
    """保存资产折旧明细到 ut_discount_details。
    按 (uf_asset_code, uf_item) 去重: 已存在则按 id 更新该行(保留原行 id/创建时间), 不存在才新建。
    :return: {"type": "S"/"E", "message": ..., "count": n}
    """
    details = _normalize_to_list(detail)
    if not details:
        return {
            "type": "E",
            "code": CODE_MISSING_PARAM,
            "message": "无待保存数据",
            "count": 0,
        }

    db = DbHelper()
    field_map, _real_cols = _resolve_field_map(db)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows, errors = _build_detail_rows(details, field_map, now)
    if errors:  # 有任一条校验不过 -> 整批不落库, 返回明细错误
        return {
            "type": "E",
            "code": CODE_MISSING_PARAM,
            "message": "校验失败: " + " | ".join(errors),
            "count": 0,
        }

    col_asset = field_map["asset_code"]
    col_item = field_map["item"]
    n_ins, n_upd = _upsert_by_key(
        TABLE, rows, [col_asset, col_item], col_asset, db, user_id
    )
    db.updateDBObj()
    return {
        "type": "S",
        "code": CODE_OK,
        "message": "保存成功: 新增{}条, 更新{}条".format(n_ins, n_upd),
        "count": len(rows),
    }


# ==================== 凭证生成 (document_post → t_fi_voucher_*) ====================
def _load_subject_mapping(asset_types, db):
    """asset_type → (借方科目=uf_field_code1_desc, 贷方科目=uf_field_code2_desc)。
    匹配 ut_data_relation_mapping.uf_out_field_code1_desc; 查询失败返回 {}。"""
    mapping = {}
    if not asset_types:
        return mapping
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
    except Exception as e:
        print("[voucher] 查询 {} 失败: {}".format(MAP_TABLE, e))
        return mapping
    for r in rows:
        key = _ci_get(r, "uf_out_field_code1_desc")
        if key not in mapping:
            mapping[key] = (
                _ci_get(r, "uf_field_code1_desc"),
                _ci_get(r, "uf_field_code2_desc"),
            )
    return mapping


def _post_item_line(subject, dc, amt, currency, cost_center):
    """构造 document_post 的一行入参。"""
    line = {
        "accounting_subjects": subject,
        "debit_credit_mark": dc,
        "transaction_currency_amount": amt,
        # 本位币金额(折旧=交易币金额; document_post 据此累加 dr/cr_amount_bc, 缺省→0 会报"总金额不能为0")
        "basic_currency_amount": amt,
        "transaction_currency": currency,
    }
    if cost_center:
        line["cost_center"] = cost_center
    return line


def _build_post_input(
    debit_subj,
    credit_subj,
    amt,
    currency,
    cost_center,
    company_code,
    posting_date,
    document_date,
    doc_type,
    header_text,
):
    """构造 document_post 入参 (head, item); fi_document_number 置空 → 过账时由平台生成。"""
    head = {
        "company_code": company_code,
        "document_category": DOCUMENT_CATEGORY,
        "posting_date": posting_date,
        "document_date": document_date,
        "accounting_document_type": doc_type,
        "transaction_currency": currency,
        "header_text": header_text,
        "fi_document_number": "",
    }
    item = [
        _post_item_line(debit_subj, DEBIT, amt, currency, cost_center),
        _post_item_line(credit_subj, CREDIT, amt, currency, cost_center),
    ]
    return head, item


def _run_document_post(d, idx, head, item, user_id):
    """调 document_post(test_run=0 正式; 内部落标准分表 t_fi_voucher_details_{co}_{yr}{pd} 并返回凭证号)。
    成功返 (year, fi_document_number, None), 失败返 (None, None, errmsg)。
    msg 与 error_list 全拼进错误(避免 msg 非空时吞掉 error_list)。"""
    asset_code = _val(d, "asset_code")
    try:
        _code, msg, error_list, year, fi_document_number = document_post(
            0, user_id, head, item
        )
    except Exception as e:
        return (
            None,
            None,
            "第{}条 资产{}: document_post 异常: {}".format(idx + 1, asset_code, e),
        )
    if error_list:
        joined = ";".join(m for m in [msg] + list(error_list or []) if m)
        return (
            None,
            None,
            "第{}条 资产{}: 过账失败 {}".format(idx + 1, asset_code, joined),
        )
    return year, fi_document_number, None


def _build_voucher_head_row(
    fi_document_number,
    year,
    company_code,
    period,
    document_date,
    posting_date,
    doc_type,
    currency,
    header_text,
):
    """组装 t_fi_voucher_head 一行(逻辑名即标准表列名, 无 uf_ 前缀)。"""
    return {
        "fi_document_number": fi_document_number,
        "fi_ledger": FI_LEDGER,
        "company_code": company_code,
        "year": year,
        "period": period,
        "document_date": document_date,
        "posting_date": posting_date,
        "accounting_document_type": doc_type,
        "transaction_currency": currency,
        "header_text": header_text,
        "attachment_qty": 2,  # 附件数量(NOT NULL; 折旧凭证固定 Dr+Cr 两行, 与 save_voucher 取 len(items) 同义)
        "create_time": _now(),
    }


def _build_voucher_item_rows(
    fi_document_number, year, company_code, debit_subj, credit_subj, amt, cost_center
):
    """组装 t_fi_voucher_details 的 Dr+Cr 两行(行号列 fi_document_item; 去重键五列齐全)。"""
    rows = []
    for row_no, (subj, dc) in enumerate(
        [(debit_subj, DEBIT), (credit_subj, CREDIT)], start=1
    ):
        row = {
            "fi_document_item": row_no,
            "fi_document_number": fi_document_number,
            "fi_ledger": FI_LEDGER,
            "company_code": company_code,
            "year": year,
            "accounting_subjects": subj,
            "debit_credit_mark": dc,
            "amount_tc": amt,
            "create_time": _now(),
        }
        if cost_center:
            row["cost_center"] = cost_center
        rows.append(row)
    return rows


def _process_one_asset(d, idx, mapping, user_id, today):
    """处理单条资产: 校验映射/金额 → 构造过账入参 → document_post → 组装凭证行。
    :return {"err": msg} 或 {"head_row":..., "item_rows":[...], "fi_document_number":...}
    """
    asset_code = _val(d, "asset_code")
    asset_type = _val(d, "asset_type")
    amt = _val(d, "currency_amount")

    if asset_type not in mapping:
        return {
            "err": "第{}条 资产{}: 资产类型[{}]无科目映射".format(
                idx + 1, asset_code, asset_type
            )
        }
    debit_subj, credit_subj = mapping[asset_type]
    if amt in ("", None):
        return {
            "err": "第{}条 资产{}: 缺少折旧金额(currency_amount)".format(
                idx + 1, asset_code
            )
        }

    company_code = _val(d, "company_code")
    posting_date = _val(d, "posting_date") or today
    document_date = _val(d, "document_date") or today
    doc_type = _val(d, "accounting_document_type") or DOC_TYPE
    currency = _val(d, "currency") or "CNY"
    cost_center = _val(d, "center")
    header_text = _val(d, "text") or "资产折旧"

    head, item = _build_post_input(
        debit_subj,
        credit_subj,
        amt,
        currency,
        cost_center,
        company_code,
        posting_date,
        document_date,
        doc_type,
        header_text,
    )
    year, fi_document_number, err = _run_document_post(d, idx, head, item, user_id)
    if err:
        return {"err": err}

    period = _val(d, "period") or posting_date[5:7]
    yr = year or posting_date[:4]
    head_row = _build_voucher_head_row(
        fi_document_number,
        yr,
        company_code,
        period,
        document_date,
        posting_date,
        doc_type,
        currency,
        header_text,
    )
    item_rows = _build_voucher_item_rows(
        fi_document_number, yr, company_code, debit_subj, credit_subj, amt, cost_center
    )
    return {
        "head_row": head_row,
        "item_rows": item_rows,
        "fi_document_number": fi_document_number,
    }


def _post_depreciation_voucher(details, user_id, db):
    """明细落库后, 按资产类型生成财务凭证: 查科目映射 → 调 document_post 过账 → 落 t_fi_voucher_head/details。
    :return {"ok": [fi_document_number,...], "errs": [msg,...]}
    """
    asset_types = {
        _val(d, "asset_type")
        for d in details
        if isinstance(d, dict) and _val(d, "asset_type")
    }
    mapping = _load_subject_mapping(asset_types, db)

    # 过账/凭证日期缺省兜底: check_fi_doc_period 按 YYYY-MM-DD 解析(取 [:4]=年, [5:7]=月), 必须带横杠
    today = datetime.now().strftime("%Y-%m-%d")
    head_rows, item_rows, ok_list, errs = [], [], [], []
    for idx, d in enumerate(details):
        if not isinstance(d, dict):
            continue
        res = _process_one_asset(d, idx, mapping, user_id, today)
        if "err" in res:
            errs.append(res["err"])
            continue
        head_rows.append(res["head_row"])
        item_rows.extend(res["item_rows"])
        ok_list.append(res["fi_document_number"])

    # upsert 落标准凭证表(head 按 HEAD_KEY, item 按 ITEM_KEY); fill_notnull 仅补新建行, 避免更新行被占位覆盖
    _upsert_by_key(
        VOUCHER_HEAD,
        head_rows,
        HEAD_KEY,
        "fi_document_number",
        db,
        user_id,
        fill_notnull=True,
    )
    _upsert_by_key(
        VOUCHER_ITEM,
        item_rows,
        ITEM_KEY,
        "fi_document_number",
        db,
        user_id,
        fill_notnull=True,
    )
    db.updateDBObj()
    return {"ok": ok_list, "errs": errs}


# ==================== 接收入口 ====================
def save_asset_depreciation_detail(payload, user_id):
    """资产折旧明细接收接口
    接收参数: {"interface_code":..., "payload":{"guid":..., "data":[{year,period,company_code,asset_code,item,...}, ...]}}
    :return {"type":"S"/"E", "message":...}
    """
    raw = payload.get("data") if isinstance(payload, dict) else payload
    data = _normalize_to_list(raw)
    if not data:
        return {"type": "E", "code": CODE_MISSING_PARAM, "message": "无数据(data 为空)"}

    res = save_discount_detail(data, user_id=user_id)
    if res["type"] != "S":
        return {
            "type": res["type"],
            "code": res.get("code", CODE_MISSING_PARAM),
            "message": res["message"],
        }

    # 明细落库成功 → 按资产类型生成财务凭证(document_post 过账 + 落 t_fi_voucher_head/details)
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
