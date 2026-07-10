#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@File    : ZZITE_MaterialReceiptSlip.py
@Date    : 2026/07/09
@Author  : yang.zhang@dxdstech.com
@explain : 物料凭证(单据)接口: NC 推送物料凭证 → 落库 → 映射移动类型 → 转平台格式 → 调 external_system_save → 回写
           (本接口不再自己过账; 格式/必填校验 + 落 t_external_sys_md_* 交给无单据过账平台 external_system_save)


    (主流程):
    1. 接收 NC 推送的 {header, items}
    2. 幂等检查(同一 uf_api_id 已提交平台成功则直接返回, 不重复处理)
    3. 轻量必填校验
    4. 落库 t_md_header / t_md_item(状态=待处理)
    5. 用 (business_type, document_type) 查 ut_nc_doc_move_type_map 回填 movement_type
    6. 转成 external_system_save 期望的平台格式(补 reversal_mark / external_sys_document_create_date /
       external_sys_unique_doc_sn / external_sys_unique_doc_items / pricing_unit_quantity / pricing_unit_of_measure)
    7. 调 external_system_save 由平台做格式/必填校验并落 t_external_sys_md_*
    8. 按 uf_api_id 回写 document_status / message(无 mat_doc_sn, 过账由平台后续触发)

  状态 document_status暂定，后期确认:
    1 待处理 / 3 映射失败 / 4 已提交平台成功 / 6 校验失败

  请求体示例:
    {"data": {
        "header": {"uf_api_id":"NC20260709001", "business_type":"入库",
                   "document_type":"采购入库单", "document_date":"2026-07-09",
                   "posting_date":"2026-07-09", "company_code":"1001"},
        "items":  [{"line_id":1, "plant_code":"1001", "stor_loc_code":"W01",
                    "mat_code":"M0001", "batch_sn":"B001", "transaction_qty":100,
                    "transaction_uom":"PC", "basic_uom":"PC",
                    "po_sn":"4500000001", "po_items":10, "vendor_code":"V001"}]
    }}
    
"""
from datetime import datetime

from DbHelper import DbHelper
from ToolsMethods import ResetResponse, ResponseData, ResponseStatusCode
from without_documents_posting_platform import external_system_save

# ==================== 表名 ====================
T_HEADER = "ut_md_header"            # 物料凭证抬头表
T_ITEM = "ut_md_item"                # 物料凭证行项目表
T_MAP = "ut_nc_doc_move_type_map"   # NC 单据类型 → 移动类型 映射表

# ==================== 状态机 ====================
ST_PENDING = 1      # 待处理(已落 NC 台账)
ST_MAP_FAILED = 3   # 映射失败(business_type+document_type 查不到 movement_type)
ST_SUBMIT_OK = 4    # 已提交平台成功(external_system_save 校验通过并落 t_external_sys_md_*)
ST_VALID_FAIL = 6   # 校验失败(NC 必填缺失 / external 校验 msg 非空)

# ==================== 回写列(若实际列名不同, 仅改这里) ====================
WB_COLS = ["document_status", "mat_doc_sn", "year", "message", "update_id", "update_time"]

# ==================== 字段映射: NC 逻辑名 → 库列名 ====================
# 抬头业务字段(uf_api_id/document_status/mat_doc_sn/year/message/create_time 由接口单独写)
HEADER_MAP = {
    "document_date": "document_date",
    "posting_date": "posting_date",
    "post_code": "post_code",
    "company_code": "company_code",
    "exchange_rate": "exchange_rate",
    "remarks_1": "remarks_1",
    "remarks_2": "remarks_2",
    "business_type": "business_type",
    "document_type": "document_type",
}

# 行项目业务字段
ITEM_MAP = {
    "line_id": "line_id",
    "plant_code": "plant_code",
    "stor_loc_code": "stor_loc_code",
    "batch_sn": "batch_sn",
    "inventory_status": "inventory_status",
    "special_inventory_status2": "special_inventory_status2",
    "movement_type": "movement_type",
    "mat_code": "mat_code",
    "transaction_qty": "transaction_qty",
    "transaction_uom": "transaction_uom",
    "transaction_amount": "transaction_amount",
    "basic_qty": "basic_qty",
    "basic_uom": "basic_uom",
    "vendor_code": "vendor_code",
    "customer_code": "customer_code",
    "cost_center": "cost_center",
    "wbs_elements": "wbs_elements",
    "po_sn": "po_sn",
    "po_items": "po_items",
    "prodosn": "prodosn",
    "so_sn": "so_sn",
    "so_items": "so_items",
    "debit_credit_mark": "debit_credit_mark",
    "rcv_plant_code": "rcv_plant_code",
    "rcv_stor_loc_code": "rcv_stor_loc_code",
    "rcv_mat_code": "rcv_mat_code",
    "rcv_batch_sn": "rcv_batch_sn",
}

# 行项目必填字段(NC 逻辑名)
ITEM_REQUIRED = ["plant_code", "mat_code", "transaction_qty", "transaction_uom"]


# ==================== 基础工具 ====================
def _val(d, key, default=""):
    """取 d[key], None/缺失 → default(空串)"""
    if not isinstance(d, dict):
        return default
    v = d.get(key)
    return default if v is None else v


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _esc(v):
    """SQL 字符串转义(单引号翻倍)"""
    return str(v).replace("'", "''") if v is not None else ""


def _gen_api_id(header):
    """NC 未传 uf_api_id 时生成唯一接口单号(基于 NC 单号+时间, 尽量稳定)"""
    import uuid
    seed = _val(header, "mat_doc_sn") or _val(header, "document_type") or _now()
    return "NC" + uuid.uuid5(uuid.NAMESPACE_URL, seed).hex[:20].upper()


# ==================== 校验 ====================
def _validate_header(header):
    """抬头轻量必填校验, 返回 [err, ...](空=通过)"""
    errs = []
    if _val(header, "document_date") == "":
        errs.append("凭证日期(document_date)必填")
    if _val(header, "posting_date") == "":
        errs.append("过账日期(posting_date)必填")
    pc = _val(header, "post_code")
    if pc != "" and str(pc) not in ("1", "2", "3", "4", "5", "6", "7"):
        errs.append("过账类型(post_code)须为 1-7")
    return errs


def _validate_item(it, idx):
    """单行必填校验, 返回 [err, ...]"""
    errs = []
    for f in ITEM_REQUIRED:
        v = it.get(f) if isinstance(it, dict) else None
        if v is None or v == "":
            errs.append("第{}行缺少必填字段 {}".format(idx + 1, f))
    return errs


# ==================== 映射 / 推导 ====================
def _map_movement_type(items, header, db):
    """用 (business_type, document_type) 批量查 ut_nc_doc_move_type_map, 回填 movement_type 到 items。
    :return (ok, missed): ok=False 时 missed 为未命中清单 [(line_id, bt, dt), ...] 或错误说明 str
    """
    def pair_of(it):
        bt = _val(it, "business_type") or _val(header, "business_type")
        dt = _val(it, "document_type") or _val(header, "document_type")
        return bt, dt

    pairs = {pair_of(it) for it in items}
    pairs.discard(("", ""))
    if not pairs:
        return False, "未提供 business_type / document_type, 无法映射移动类型"

    in_clause = ",".join("('{}','{}')".format(_esc(bt), _esc(dt)) for bt, dt in pairs)
    sql = ("SELECT `business_type`,`document_type`,`movement_type` FROM `{}` "
           "WHERE `enable_flag`=1 AND (business_type,document_type) IN ({})").format(T_MAP, in_clause)
    rows = db.query_sql(sql) or []
    mapping = {(_val(r, "business_type"), _val(r, "document_type")): _val(r, "movement_type") for r in rows}

    missed = []
    for it in items:
        bt, dt = pair_of(it)
        mt = mapping.get((bt, dt))
        if mt:
            it["movement_type"] = mt
        else:
            missed.append((it.get("line_id"), bt, dt))
    return (len(missed) == 0), missed


# ==================== 落库 / 回写 ====================
def _build_header_row(header, uf_api_id, now, status, msg):
    row = {"uf_api_id": uf_api_id, "document_status": status,
           "mat_doc_sn": _val(header, "mat_doc_sn"), "year": _val(header, "year"),
           "message": msg, "create_time": now}
    for logical, col in HEADER_MAP.items():
        v = header.get(logical)
        if v is not None and v != "":
            row[col] = v
    return row


def _build_item_row(it, uf_api_id, now, status, msg):
    row = {"uf_api_id": uf_api_id, "document_status": status,
           "mat_doc_sn": "", "message": msg, "create_time": now}
    for logical, col in ITEM_MAP.items():
        v = it.get(logical)
        if v is not None and v != "":
            row[col] = v
    return row


def _cleanup(uf_api_id, db):
    """清除该 uf_api_id 的旧台账行, 保证重推幂等(失败重试 / 重复推送只保留最新一条)"""
    aid = _esc(uf_api_id)
    db.exec_sql("DELETE FROM `{}` WHERE `uf_api_id`='{}'".format(T_ITEM, aid))
    db.exec_sql("DELETE FROM `{}` WHERE `uf_api_id`='{}'".format(T_HEADER, aid))


def _persist(header, items, uf_api_id, now, status, msg, db, user_id):
    """落库 header(1 行) + items(N 行); 落库前先清旧台账行避免重推产生重复"""
    _cleanup(uf_api_id, db)
    header_row = _build_header_row(header, uf_api_id, now, status, msg)
    item_rows = [_build_item_row(it, uf_api_id, now, status, msg) for it in items]
    db.batchInsertToDB(T_HEADER, [header_row], user_id=user_id)
    if item_rows:
        db.batchInsertToDB(T_ITEM, item_rows, user_id=user_id)


def _writeback(uf_api_id, status, mat_doc_sn, year, message, db, user_id):
    """按 uf_api_id 精确 UPDATE header + item(回写不中断主流程, 列名错仅打印告警)"""
    now = _now()
    sets = [
        "`document_status`={}".format(status),
        "`mat_doc_sn`='{}'".format(_esc(mat_doc_sn)),
        "`year`='{}'".format(_esc(year)),
        "`message`='{}'".format(_esc((message or "")[:255])),
        "`update_id`={}".format(int(user_id or 0)),
        "`update_time`='{}'".format(now),
    ]
    where = "`uf_api_id`='{}'".format(_esc(uf_api_id))
    for tbl in (T_HEADER, T_ITEM):
        sql = "UPDATE `{}` SET {} WHERE {}".format(tbl, ",".join(sets), where)
        try:
            db.exec_sql(sql)
        except Exception as e:  # 回写列名/约束问题不应让已成功的过账丢失结果
            print("[writeback] {} 回写失败: {}".format(tbl, e))


def _check_duplicate(uf_api_id, db):
    """幂等: 该 uf_api_id 是否已过账成功, 返回 (exists, mat_doc_sn, year)"""
    rows = db.query_sql("SELECT `mat_doc_sn`,`year`,`document_status` FROM `{}` "
                        "WHERE `uf_api_id`='{}' LIMIT 1".format(T_HEADER, _esc(uf_api_id)))
    if rows and int(rows[0].get("document_status", 0) or 0) == ST_SUBMIT_OK:
        return True, rows[0].get("mat_doc_sn", ""), rows[0].get("year", "")
    return False, "", ""


# ==================== 转平台格式 (external_system_save 入参) ====================
# external_system_save 期望 doc_data 是 list, 每项一个 header dict, 内含 'item'(items 列表) 与
# 'message_text'(空串占位) 两键, 否则 external_system_check 取键时 KeyError。
# NC 缺口的平台必填字段在此补默认值(见 _build_external_doc_data docstring)。
def _build_external_doc_data(header, items, uf_api_id):
    """把 NC 的 {header, items} 重组为 external_system_save 入参格式(单元素 list)。
    补齐平台必填但 NC 未传的字段:
      reversal_mark=0 / external_sys_document_create_date=凭证日期 /
      external_sys_unique_doc_sn=uf_api_id / external_sys_unique_doc_items=line_id /
      pricing_unit_quantity=transaction_qty / pricing_unit_of_measure=transaction_uom
    """
    doc_date = _val(header, "document_date")
    ext_header = {
        "external_sys_unique_doc_sn": uf_api_id,
        "document_date": doc_date,
        "posting_date": _val(header, "posting_date"),
        "company_code": _val(header, "company_code"),
        "reversal_mark": 0,                              # NC 无冲销语义, 默认 0
        "external_sys_document_create_date": doc_date,   # 取凭证日期
        "message_text": "",                              # 占位, 由 external_system_check 回填
    }
    for f in ("exchange_rate", "summary_unique_number", "remarks_1", "remarks_2"):
        v = header.get(f)
        if v is not None and v != "":
            ext_header[f] = v

    # 可选行字段(同名直传, 有则传)
    opt_fields = ("mat_code", "batch_sn", "basic_qty", "basic_uom", "vendor_code",
                  "customer_code", "cost_center", "wbs_elements", "prodosn",
                  "inventory_status", "special_inventory_status2",
                  "rcv_plant_code", "rcv_stor_loc_code", "rcv_mat_code", "rcv_batch_sn")
    # NC → 平台 字段名转换(po_sn/so_sn → rel_po_sn/rel_so_sn)
    rename = {"po_sn": "rel_po_sn", "po_items": "rel_po_items",
              "so_sn": "rel_so_sn", "so_items": "rel_so_items"}

    ext_items = []
    for it in items:
        qty = it.get("transaction_qty")
        uom = _val(it, "transaction_uom")
        ext_it = {
            "external_sys_unique_doc_sn": uf_api_id,
            "external_sys_unique_doc_items": it.get("line_id"),  # 平台唯一行号 ← line_id
            "line_id": it.get("line_id"),
            "movement_type": _val(it, "movement_type"),          # 已由 _map_movement_type 回填
            "plant_code": _val(it, "plant_code"),
            "company_code": _val(header, "company_code"),         # 行项目公司取抬头
            "stor_loc_code": _val(it, "stor_loc_code"),
            "transaction_qty": qty,
            "transaction_uom": uom,
            "pricing_unit_quantity": qty,                         # 兜底 ← 交易数量
            "pricing_unit_of_measure": uom,                       # 兜底 ← 交易单位
        }
        for f in opt_fields:
            v = it.get(f)
            if v is not None and v != "":
                ext_it[f] = v
        for src, dst in rename.items():
            v = it.get(src)
            if v is not None and v != "":
                ext_it[dst] = v
        ext_items.append(ext_it)

    return [{**ext_header, "item": ext_items}]


# ==================== 主流程编排 ====================
def material_receipt_receive(header=None, items=None, user_id=0, **extra):
    """内部主流程编排(便于 __main__ 调试), 返回结果 dict。
    :return {"type":"S"/"E", "message":..., "uf_api_id":..., "status":...,
             成功时附 all_count/pass_count; 幂等命中(已提交平台)时附 mat_doc_sn/year}
    """
    db = DbHelper()
    header = header or {}
    # 兼容 item / items / 单 dict
    if items is None:
        items = extra.get("item") or []
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        return {"type": "E", "message": "items 必须是列表", "status": ST_VALID_FAIL}

    uf_api_id = _val(header, "uf_api_id") or _gen_api_id(header)
    header["uf_api_id"] = uf_api_id
    now = _now()

    # 0. 幂等
    dup, md, yr = _check_duplicate(uf_api_id, db)
    if dup:
        return {"type": "S", "message": "该单据已提交平台成功, 请勿重复推送",
                "uf_api_id": uf_api_id, "mat_doc_sn": md, "year": yr, "status": ST_SUBMIT_OK}

    # 1. 必填校验
    errs = _validate_header(header)
    for idx, it in enumerate(items):
        errs += _validate_item(it, idx)
    if errs or not items:
        msg = ";".join(errs) or "无行项目数据"
        _persist(header, items, uf_api_id, now, ST_VALID_FAIL, msg, db, user_id)
        return {"type": "E", "message": "校验失败: " + msg, "uf_api_id": uf_api_id, "status": ST_VALID_FAIL}

    # 2. 映射 movement_type(回填到 items 内存对象)
    ok, missed = _map_movement_type(items, header, db)
    if not ok:
        msg = missed if isinstance(missed, str) else \
            "未配置移动类型映射: " + ",".join("line{}(bt={},dt={})".format(ln, bt, dt) for ln, bt, dt in missed)
        _persist(header, items, uf_api_id, now, ST_MAP_FAILED, msg, db, user_id)
        return {"type": "E", "message": msg, "uf_api_id": uf_api_id, "status": ST_MAP_FAILED}

    # 3. 落库(状态=待处理, 已含映射后的 movement_type)
    _persist(header, items, uf_api_id, now, ST_PENDING, "", db, user_id)

    # 4. 转平台格式 + 调 external_system_save(平台做格式/必填校验并落 t_external_sys_md_*)
    doc_data = _build_external_doc_data(header, items, uf_api_id)
    all_count, pass_count, _items_data, msg = external_system_save(doc_data)

    # 5. 回写 NC 台账
    if msg:
        _writeback(uf_api_id, ST_VALID_FAIL, "", "", msg, db, user_id)
        return {"type": "E", "message": "提交平台校验失败: " + msg,
                "uf_api_id": uf_api_id, "status": ST_VALID_FAIL}
    note = "已提交平台" if pass_count >= all_count else \
        "已提交平台(部分行未通过校验: 成功{}/共{})".format(pass_count, all_count)
    _writeback(uf_api_id, ST_SUBMIT_OK, "", "", note, db, user_id)
    return {"type": "S", "message": note, "uf_api_id": uf_api_id,
            "all_count": all_count, "pass_count": pass_count, "status": ST_SUBMIT_OK}


@ResetResponse(params=["header", "items"], user_id=True)
def material_document_receive(header, items, user_id=0, **extra):
    """NC 推送入口: 接收 {header, items}, 走 落库→映射→转平台格式→调 external_system_save→回写 全流程(不过账)。
    请求体: {"data":{"header":{...},"items":[...]}}
    :return ResponseData(Success/Error, msg, data)
    """
    res = material_receipt_receive(header=header, items=items, user_id=user_id, **extra)
    if res.get("type") == "S":
        return ResponseData(ResponseStatusCode.Success, res.get("message", "完成"), res)
    return ResponseData(ResponseStatusCode.Error, res.get("message", "失败"), res)


# ==================== 辅助: 上线前核对表结构 ====================
def dump_columns(db=None):
    """打印三张表实际列名, 用于核对 FIELD_MAP / 回写列(WB_COLS)与建表是否一致"""
    db = db or DbHelper()
    for tbl in (T_HEADER, T_ITEM, T_MAP):
        rows = db.query_sql(
            "SELECT COLUMN_NAME FROM information_schema.columns WHERE table_name='{}' ORDER BY ORDINAL_POSITION".format(tbl)
        ) or []
        cols = [r.get("COLUMN_NAME") or r.get("column_name") for r in rows]
        print("==== {} ====\n{}".format(tbl, cols))


if __name__ == "__main__":
    sample = {
        "header": {
            "uf_api_id": "NC20260709001",
            "business_type": "入库",
            "document_type": "采购入库单",
            "document_date": "2026-07-09",
            "posting_date": "2026-07-09",
            "post_code": "1",
            "company_code": "1001",
        },
        "items": [
            {"line_id": 1, "plant_code": "1001", "stor_loc_code": "W01",
             "mat_code": "M0001", "batch_sn": "B001", "transaction_qty": 100,
             "transaction_uom": "PC", "basic_uom": "PC",
             "po_sn": "4500000001", "po_items": 10, "vendor_code": "V001"},
        ],
    }
    print(material_receipt_receive(header=sample["header"], items=sample["items"], user_id=0))
