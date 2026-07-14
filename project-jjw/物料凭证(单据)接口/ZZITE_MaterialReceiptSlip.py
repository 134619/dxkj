#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@File    : ZZITE_MaterialReceiptSlip.py
@Date    : 2026/07/09
@Author  : yang.zhang@dxdstech.com
@explain : 物料凭证(单据)接口: NC 推送物料凭证 → 落库 → 映射移动类型 → 转平台格式 →
            调 external_system_save → 回写

    1 待处理 / 3 映射失败 / 4 已提交平台成功 / 6 校验失败
  请求体示例:
    {"data": {
        "header": {"uf_api_id":"NC20260709001", "business_type":"入库",
                   "document_type":"采购入库单", "document_date":"2026-07-09",
                   "posting_date":"2026-07-09", "post_code":"1", "company_code":"1001"},
        "items":  [{"line_id":1, "erp_document_items":"0001", "document_flag":"PK001",
                    "plant_code":"1001", "stor_loc_code":"W01",
                    "mat_code":"M0001", "batch_sn":"B001", "transaction_qty":100,
                    "transaction_uom":"PC", "basic_uom":"PC",
                    "po_sn":"4500000001", "po_items":10, "vendor_code":"V001",
                    "transfer_warehouse_num":"TR001", "transfer_warehouse_items":"10"}]
    }}
"""

from datetime import datetime

from DbHelper import DbHelper
from ToolsMethods import ResetResponse, ResponseData, ResponseStatusCode
from without_documents_posting_platform import external_system_save

# ==================== 表名 ====================
T_HEADER = "t_md_header"            # 物料凭证抬头表
T_ITEM = "t_md_item"                # 物料凭证行项目表
T_MAP = "ut_nc_doc_move_type_map"  # 映射表名常量(映射逻辑已停用, 仅留名供 dump_columns/后续恢复用)

# ==================== 状态机 ====================
ST_PENDING = 1      # 待处理(已落 NC 台账)
ST_SUBMIT_OK = 4    # 已提交平台成功(external_system_save 校验通过并落 t_external_sys_md_*)
ST_VALID_FAIL = 6   # 校验失败(NC 必填缺失 / external 校验 msg 非空)

# ==================== 返回前端 code ====================
CODE_OK = 200             # 成功
CODE_MISSING_PARAM = 401  # 缺少参数 / 校验失败

# ==================== 接口控制列 → 复用预留字段 ====================
COL_API_ID = "reserved9"  # uf_api_id (两表共用: 幂等 / 关联 header↔item / 清理)
# header 另复用预留列(裸名直写): reserved1=document_status(状态机 1/4/6) / reserved2=message(回写消息)

# ==================== 字段映射: NC 逻辑名 → 库列名 ====================
HEADER_MAP = {
    "document_date": "document_date",
    "posting_date": "posting_date",
    "post_code": "post_code",
    "company_code": "company_code",
    "exchange_rate": "exchange_rate",
    "summary_unique_number": "summary_unique_number",
    "remarks_1": "remarks_1",
    "remarks_2": "remarks_2",
    "vendor_dn": "vendor_dn",
}


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
    # ---- 新增: 落 reserved 预留字段(按最新字段表) ----
    "erp_document_items": "reserved1",  # ERP单据行号
    "document_flag": "reserved2",  # 来源单据PK标识
    "transfer_warehouse_num": "reserved3",  # 转库单号
    "transfer_warehouse_items": "reserved4",  # 转库单行号
    "form_transfer_warehouse_num": "reserved5",  # 形态转换单号
    "form_transfer_warehouse_items": "reserved6",  # 形态转换单行号
    "transfer_order_no": "reserved7",  # 调拨订单号
    "transfer_order_items": "reserved8",  # 调拨订单行号
    "document_type": "reserved10",  # 单据类型(抬头级, 落 item; 取值 item 优先 header 兜底)
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
    """SQL 字符串转义"""

    return str(v).replace("'", "''") if v is not None else ""

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


# ==================== 落库 / 回写 ====================
def _build_header_row(header, uf_api_id, now, status, msg):
    row = {
        COL_API_ID: uf_api_id,
        "reserved1": status,  # document_status
        "mat_doc_sn": _val(header, "mat_doc_sn"),
        "year": _val(header, "year"),
        "reserved2": msg,  # message
        "create_time": now,
    }
    for logical, col in HEADER_MAP.items():
        v = header.get(logical)
        if v is not None and v != "":
            row[col] = v
    return row


def _build_item_row(it, uf_api_id, now, header=None):
    row = {
        COL_API_ID: uf_api_id,
        "mat_doc_sn": "",
        "pir_version": "测试1",  # Oracle 视空串为 NULL, 用单空格占位满足 NOT NULL
        "create_time": now,
    }
    for logical, col in ITEM_MAP.items():
        v = it.get(logical)
        if (v is None or v == "") and logical == "document_type" and header:
            v = header.get("document_type")  # 抬头级兜底: 行内未传则取 header
        if v is not None and v != "":
            row[col] = v
    return row


def _cleanup(uf_api_id, db):
    """清除该 uf_api_id 的旧台账行, 保证重推幂等(失败重试 / 重复推送只保留最新一条)"""
    aid = _esc(uf_api_id)
    db.exec_sql("DELETE FROM `{}` WHERE `{}`='{}'".format(T_ITEM, COL_API_ID, aid))
    db.exec_sql("DELETE FROM `{}` WHERE `{}`='{}'".format(T_HEADER, COL_API_ID, aid))


def _persist(header, items, uf_api_id, now, status, msg, db, user_id):
    """落库 header(1 行) + items(N 行)"""

    _cleanup(uf_api_id, db)
    header_row = _build_header_row(header, uf_api_id, now, status, msg)
    item_rows = [_build_item_row(it, uf_api_id, now, header) for it in items]
    db.batchInsertToDB(T_HEADER, [header_row], user_id=user_id)
    if item_rows:
        db.batchInsertToDB(T_ITEM, item_rows, user_id=user_id)


def _write_price_data(header, items, db, user_id):
    """po_sn 不为空的行, 写入 t_external_sys_md_price_data(物料凭证价格数据):
    external_sys_unique_doc_sn ← header.mat_doc_sn,
    external_sys_unique_doc_items ← item.erp_document_items,
    unit_price_excluding_tax ← item.transaction_amount。
    无 mat_doc_sn 或该行无 po_sn 则跳过。
    """
    mat_doc_sn = _val(header, "mat_doc_sn")
    if not mat_doc_sn:
        return  # 无 ERP 单号无法定位价格数据
    rows = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if _val(it, "po_sn") == "":
            continue  # po_sn 为空不写
        rows.append(
            {
                "external_sys_unique_doc_sn": mat_doc_sn,
                "external_sys_unique_doc_items": it.get("erp_document_items"),
                "unit_price_excluding_tax": it.get("transaction_amount"),
                "create_time": _now(),
            }
        )
    if rows:
        # 先删该单号的旧价格数据, 保证重推幂等(避免撞唯一索引 IDX_T_EXTERNAL_SYS_MD_PRICE_DATA_UNIQUE_INDEX)
        db.exec_sql(
            "DELETE FROM `t_external_sys_md_price_data`"
            " WHERE `external_sys_unique_doc_sn`='{}'".format(_esc(mat_doc_sn))
        )
        db.batchInsertToDB("t_external_sys_md_price_data", rows, user_id=user_id)
        db.updateDBObj()


def _writeback(uf_api_id, status, mat_doc_sn, year, message, db, user_id):
    """按 uf_api_id 精确 UPDATE t_md_header(item 表无 status/message 列, 不回写)。
    回写不中断主流程, 列名错仅打印告警。"""

    now = _now()
    sets = [
        "`reserved1`={}".format(status),  # document_status
        "`mat_doc_sn`='{}'".format(_esc(mat_doc_sn)),
        "`year`='{}'".format(_esc(year)),
        "`reserved2`='{}'".format(_esc((message or "")[:255])),  # message
        "`update_id`={}".format(int(user_id or 0)),
        "`update_time`='{}'".format(now),
    ]
    where = "`{}`='{}'".format(COL_API_ID, _esc(uf_api_id))
    sql = "UPDATE `{}` SET {} WHERE {}".format(T_HEADER, ",".join(sets), where)
    try:
        db.exec_sql(sql)
    except Exception as e:  # 回写列名/约束问题不应让已成功的过账丢失结果
        print("[writeback] {} 回写失败: {}".format(T_HEADER, e))


def _check_duplicate(uf_api_id, db):
    """幂等: 该 uf_api_id 是否已过账成功, 返回 (exists, mat_doc_sn, year)"""
    rows = db.query_sql(
        "SELECT `mat_doc_sn`,`year`,`reserved1` FROM `{}` "
        "WHERE `{}`='{}' LIMIT 1".format(T_HEADER, COL_API_ID, _esc(uf_api_id))
    )
    if rows and int(rows[0].get("reserved1", 0) or 0) == ST_SUBMIT_OK:
        return True, rows[0].get("mat_doc_sn", ""), rows[0].get("year", "")
    return False, "", ""


# ==================== 转平台格式 (external_system_save 入参) ====================

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
        "reversal_mark": 0,  # NC 无冲销语义, 默认 0
        "external_sys_document_create_date": doc_date,  # 取凭证日期
        "message_text": "",  # 占位, 由 external_system_check 回填
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
    # 平台要求 int 的 rename 目标(NC 常以零填充字符串 "00010" 传入, 需转 int)
    rename_int = {"rel_po_items", "rel_so_items"}

    ext_items = []
    for it in items:
        qty = it.get("transaction_qty")
        uom = _val(it, "transaction_uom")
        ext_it = {
            "external_sys_unique_doc_sn": uf_api_id,
            "external_sys_unique_doc_items": it.get(
                "line_id"
            ),  # 平台唯一行号 ← line_id
            "line_id": it.get("line_id"),
            "movement_type": _val(it, "movement_type"),  # NC 行项目自带(映射逻辑已停用)
            "plant_code": _val(it, "plant_code"),
            "company_code": _val(header, "company_code"),  # 行项目公司取抬头
            "stor_loc_code": _val(it, "stor_loc_code"),
            "transaction_qty": qty,
            "transaction_uom": uom,
            "pricing_unit_quantity": qty,  # 兜底 ← 交易数量
            "pricing_unit_of_measure": uom,  # 兜底 ← 交易单位
            "pir_version": " ",  # Oracle NOT NULL 占位(评估版本, NC 无此概念); 空串在 Oracle 即 NULL 会撞 ORA-01400
        }
        # price(交易金额) ← transaction_amount: 平台要求 list 类型, 关联采购订单(rel_po_sn)存在时必填
        amt = it.get("transaction_amount")
        if amt is not None and amt != "":
            ext_it["price"] = [amt]
        for f in opt_fields:
            v = it.get(f)
            if v is not None and v != "":
                ext_it[f] = v
        for src, dst in rename.items():
            v = it.get(src)
            if v is not None and v != "":
                if dst in rename_int:
                    try:
                        v = int(v)
                    except (TypeError, ValueError):
                        pass  # 转不了 int 就原样传, 交给平台类型校验报错
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
        return {"type": "E", "code": CODE_MISSING_PARAM, "message": "items 必须是列表", "status": ST_VALID_FAIL}

    uf_api_id = _val(header, "uf_api_id")
    header["uf_api_id"] = uf_api_id
    now = _now()

    # 0. 幂等
    dup, md, yr = _check_duplicate(uf_api_id, db)
    if dup:
        return {"type": "S", "code": CODE_OK, "message": "该单据已提交平台成功, 请勿重复推送",
                "uf_api_id": uf_api_id, "mat_doc_sn": md, "year": yr, "status": ST_SUBMIT_OK}

    # 1. 必填校验
    errs = _validate_header(header)
    for idx, it in enumerate(items):
        errs += _validate_item(it, idx)
    if errs or not items:
        msg = ";".join(errs) or "无行项目数据"
        _persist(header, items, uf_api_id, now, ST_VALID_FAIL, msg, db, user_id)
        return {"type": "E", "code": CODE_MISSING_PARAM, "message": "校验失败: " + msg, "uf_api_id": uf_api_id, "status": ST_VALID_FAIL}

    # 2. 落库(状态=待处理)
    _persist(header, items, uf_api_id, now, ST_PENDING, "", db, user_id)

    # 3.5 po_sn 不为空的行写价格数据到 t_external_sys_md_price_data(失败不中断主流程)
    try:
        _write_price_data(header, items, db, user_id)
    except Exception as e:
        print("[price_data] 写入失败: {}".format(e))

    # 4. 转平台格式 + 调 external_system_save(平台做格式/必填校验并落 t_external_sys_md_*)
    doc_data = _build_external_doc_data(header, items, uf_api_id)

    print("doc_data----", doc_data)
    all_count, pass_count, _items_data, msg = external_system_save(doc_data)

    # 5. 回写 NC 台账
    if msg:
        _writeback(uf_api_id, ST_VALID_FAIL, "", "", msg, db, user_id)
        return {"type": "E", "code": CODE_MISSING_PARAM, "message": "提交平台校验失败: " + msg,
                "uf_api_id": uf_api_id, "status": ST_VALID_FAIL}
    note = "已提交平台" if pass_count >= all_count else \
        "已提交平台(部分行未通过校验: 成功{}/共{})".format(pass_count, all_count)
    _writeback(uf_api_id, ST_SUBMIT_OK, "", "", note, db, user_id)
    return {"type": "S", "code": CODE_OK, "message": note, "uf_api_id": uf_api_id,
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
    """打印三张表实际列名, 用于核对 HEADER_MAP / ITEM_MAP 与建表是否一致。
    库无关: 走 DbHelper.get_columns_by_table(MySQL/Oracle 均可), 避免手写 information_schema.columns
    在 Oracle 上报 ORA-00942。开头打印 get_db_type() 便于确认当前连接类型。
    """
    db = db or DbHelper()
    try:
        print("db_type = {}".format(db.get_db_type()))
    except Exception as e:
        print("db_type 获取失败: {}".format(e))
    for tbl in (T_HEADER, T_ITEM, T_MAP):
        try:
            rows = db.get_columns_by_table(tbl) or []
            cols = [r.get("name") for r in rows if isinstance(r, dict)]
            print("==== {} ====\n{}".format(tbl, cols))
        except Exception as e:
            print("==== {} ====\n[获取列失败] {}".format(tbl, e))


# ==================== 扁平式接收(ExtendHandler 体系: payload={guid, data:[...]}) ====================
# 前端不分 header/items, 全部扁平放 data; 按 uf_api_id 聚合: 同号多条 = 一张凭证多行。
# 抬头字段(HEADER_FIELDS)从组内首个非空提取, 其余字段作为行项目落 item, 复用 material_receipt_receive。
HEADER_FIELDS = (
    "uf_api_id",
    "mat_doc_sn",
    "year",
    "document_date",
    "posting_date",
    "post_code",
    "company_code",
    "document_type",
    "business_type",
    "exchange_rate",
    "summary_unique_number",
    "remarks_1",
    "remarks_2",
    "vendor_dn",
)


def _flat_to_groups(payload):
    """扁平 payload → [(header, items), ...], 按 uf_api_id 聚合。
    :param payload: {"guid":..., "data":[{抬头+行字段扁平}, ...]} 或直接 list[dict]
    :return [(header_dict, [row, ...]), ...]
    """
    data = payload.get("data") if isinstance(payload, dict) else payload
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not data:
        return []

    groups, order = {}, []
    for row in data:
        if not isinstance(row, dict):
            continue
        aid = _val(row, "uf_api_id")
        if aid not in groups:
            groups[aid] = []
            order.append(aid)
        groups[aid].append(row)

    result = []
    for aid in order:
        rows = groups[aid]
        header = {"uf_api_id": aid}
        for f in HEADER_FIELDS:
            if f == "uf_api_id":
                continue
            for row in rows:  # 组内首个非空
                v = row.get(f)
                if v is not None and v != "":
                    header[f] = v
                    break
        result.append((header, rows))
    return result


def save_receive_material_document_flat(payload, user_id):
    """物料凭证(单据)接收接口(扁平式, ExtendHandler 体系)。
    前端: {"interface_code":"ZMM_INT_040", "payload":{"guid":..., "data":[{扁平抬头+行字段}, ...]}}
    按 uf_api_id 聚合后复用 material_receipt_receive 落库 → external_system_save → 回写。
    :param payload: {"guid":..., "data":[...]}
    :param user_id: 操作人 id
    :return {"type":"S"/"E", "message":...}
    """
    groups = _flat_to_groups(payload)
    if not groups:
        return {"type": "E", "code": CODE_MISSING_PARAM, "message": "无数据(data 为空)"}

    results, errs = [], []
    total_rows = 0
    for header, items in groups:
        total_rows += len(items)
        res = material_receipt_receive(header=header, items=items, user_id=user_id)
        results.append(res)
        if res.get("type") != "S":
            errs.append("{}: {}".format(header["uf_api_id"], res.get("message", "")))

    if errs:
        return {"type": "E", "code": CODE_MISSING_PARAM, "message": "; ".join(errs)}
    return {
        "type": "S",
        "code": CODE_OK,
        "message": "成功: {} 张凭证 / {} 行".format(len(results), total_rows),
    }


if __name__ == "__main__":
    sample = {
        "header": {
            "uf_api_id": "NC20260710001",
            "mat_doc_sn": "5000000001",
            "year": "2026",
            "document_date": "2026-07-10",
            "posting_date": "2026-07-10",
            "post_code": "",
            "company_code": "J0008",
            "document_type": "采购入库单",
            "business_type": "入库",
            "exchange_rate": "",
            "summary_unique_number": "1",
            "remarks_1": "7月采购入库",
            "remarks_2": "",
            "vendor_dn": "",
        },
        "items": [
            {
                # 采购入库行: 采购订单 / 供应商 / 成本中心
                "line_id": 1,
                "erp_document_items": "0001",
                "document_flag": "PK20260710001",
                "plant_code": "FSDA",
                "stor_loc_code": "W001",
                "batch_sn": "B2026071001",
                "inventory_status": "",
                "special_inventory_status2": "",
                "movement_type": "101",
                "mat_code": "M000000001",
                "transaction_qty": 100.000,
                "transaction_uom": "PC",
                "transaction_amount": 12000.00,
                "basic_qty": 100.000,
                "basic_uom": "PC",
                "vendor_code": "V001000",
                "customer_code": "",
                "cost_center": "C00100",
                "wbs_elements": "",
                "po_sn": "4500000001",
                "po_items": "00010",
                "prodosn": "",
                "so_sn": "",
                "so_items": "",
                "debit_credit_mark": "S",
                "transfer_warehouse_num": "",
                "transfer_warehouse_items": "",
                "form_transfer_warehouse_num": "",
                "form_transfer_warehouse_items": "",
                "transfer_order_no": "",
                "transfer_order_items": "",
                "rcv_plant_code": "",
                "rcv_stor_loc_code": "",
            }
        ],
    }
    print(material_receipt_receive(header=sample["header"], items=sample["items"], user_id=0))
