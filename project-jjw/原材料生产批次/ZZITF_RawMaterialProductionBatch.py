#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@File    : ZZITF_RawMaterialProductionBatch.py
@Date    : 2026/07/22
@explain : 原材料批次成本接口
  落库 ut_rm_production_batch 后, 转过账平台格式调 external_system_save:
    uf_qty_m 负数, 移动类型为 SC01; 正数/零为 S001

  落库表 ut_rm_production_batch
    uf_mat_code      物料编码      必填
    uf_company_code  公司          必填
    uf_year          年度          必填  (原样存入前端传入值)
    uf_period        期间          必填
    uf_batch_sn      批次          必填
    uf_stor_loc_code 库存地点      必填
    uf_currency      货币          必填, 默认 CNF
    uf_qty_m         本月发生数量  必填(decimal, 缺省 0)
    uf_cur_m         本月发生金额  必填(decimal, 缺省 0)
    uf_basic_uom     单位          必填(varchar, 缺省单空格)
  请求体示例:
    {"data": [{"mat_code":"...", "company_code":"...", "year":"2026", "period":"07",
               "batch_sn":"...", "stor_loc_code":"02", "currency":"CNY", "qty_m":100, "cur_m":5000, "basic_uom":"013"}]}

"""

from datetime import datetime

from DbHelper import DbHelper
from without_documents_posting_platform import external_system_save

db = DbHelper()


# ==================== 落库表(二开 ut_ 前缀) ====================
TABLE = "ut_rm_production_batch"

# 字段映射: 外部逻辑名 -> 库表列名(uf_ 前缀; batchInsertToDB 按列名严格匹配, 大小写须与库表一致)
FIELD_MAP = {
    "mat_code": "uf_mat_code",  # 物料编码(必填)
    "company_code": "uf_company_code",  # 公司(必填)
    "year": "uf_year",  # 年度(必填)
    "period": "uf_period",  # 期间(必填)
    "batch_sn": "uf_batch_sn",  # 批次(必填)
    "stor_loc_code": "uf_stor_loc_code",  # 库存地点(必填)
    "qty_m": "uf_qty_m",  # 本月发生数量(非必填, decimal)
    "cur_m": "uf_cur_m",  # 本月发生金额(非必填, decimal)
    "basic_uom": "uf_basic_uom",  # 单位(非必填, varchar)
    "currency": "uf_currency",  # 货币(必填, 默认 CNF)
}
REQUIRED = [
    "mat_code",
    "company_code",
    "year",
    "period",
    "batch_sn",
    "stor_loc_code",
]  # 必填(逻辑名); currency 默认 CNF 兜底

# NOT NULL 列默认/占位(调用方未传时补, 已传不覆盖; Oracle 空串=NULL 撞 ORA-01400)
DEFAULTS = {
    "uf_currency": "CNF",  # 货币: 业务默认 CNF(若实际是 CNY, 改这里)
    "uf_basic_uom": " ",  # 单位: 非必填, NOT NULL varchar 缺省单空格占位
    "uf_qty_m": 0,  # 本月发生数量: 非必填, NOT NULL decimal 缺省 0
    "uf_cur_m": 0,  # 本月发生金额: 非必填, NOT NULL decimal 缺省 0
    "note": " ",  # 备注: NOT NULL varchar 缺省单空格占位
}

# ==================== 过账平台映射(external_system_save 入参) ====================
# 移动类型: 本月发生数量(uf_qty_m) 负数取 SC01(发出), 正数/零取 S001(入库)
MOVE_TYPE_NEG = "SC01"
MOVE_TYPE_POS = "S001"
# 库存地点(stor_loc_code): 前端入参传入(须为 plant_code=company_code 下真实存在的库存地点)

# ==================== 返回前端 code ====================
CODE_OK = 200  # 成功
CODE_MISSING_PARAM = 401  # 缺少参数 / 校验失败


# ==================== 基础工具 ====================
def _val(d, key, default=""):
    """取 d[key], None -> default(空串)"""
    if not isinstance(d, dict):
        return default
    v = d.get(key)
    return default if v is None else v


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normalize_to_list(data):
    """dict -> [dict]; list -> 原样; 其它 -> None。"""
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data
    return None


def _build_rows(details, field_map, now):
    """必填校验 + 组行 + NOT NULL 占位; 返回 (rows, errors)。"""
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
        # NOT NULL 列占位(未传则补, 已传不覆盖)
        for col, default in DEFAULTS.items():
            row.setdefault(col, default)
        row["create_time"] = now  # create_id 由 batchInsertToDB 按 user_id 自动写
        rows.append(row)
    return rows, errors


# ==================== 落库 upsert ====================
# 去重键(库列名): 物料编码 + 批次, 对应唯一索引 MAT_CODE_BACH_SN
BATCH_KEY_COLS = ["uf_mat_code", "uf_batch_sn"]


def _esc(v):
    """SQL 字符串转义(单引号转为两个单引号)。"""

    return str(v).replace("'", "''") if v is not None else ""


def _upsert_batches(rows, db, user_id):
    """按 (uf_mat_code, uf_batch_sn) 去重 upsert(对应 唯一索引 MAT_CODE_BACH_SN):
    物料+批次已存在则按 id 更新该行; 不存在则新建。
    Oracle 下 DuplicateSQLKey(ON DUPLICATE) 不可靠(同项目 external_system_save 也用手动
    DELETE+INSERT 规避), 故采用查 id, 命中更新否则新建(同 ZZITF_AssetDepreciationDetail)。
    :return (insert_count, update_count)
    """

    if not rows:
        return 0, 0
    key_cols = BATCH_KEY_COLS
    filter_col = key_cols[0]  # 用 mat_code 做 IN 过滤, Python 内再按完整两列精确匹配
    # 拉本批 mat_code 命中的已有行 id(缩小范围), 再 Python 内按 (mat_code, batch_sn) 精确匹配
    filt_vals = sorted(
        {
            str(r.get(filter_col))
            for r in rows
            if str(r.get(filter_col)) not in ("", "None")
        }
    )
    existing = {}
    if filt_vals:
        in_list = ",".join("'" + _esc(x) + "'" for x in filt_vals)
        sel = ", ".join("`{}`".format(c) for c in ["id"] + key_cols)
        try:
            ex = (
                db.query_sql(
                    "SELECT {0} FROM `{1}` WHERE `{2}` IN ({3})".format(
                        sel, TABLE, filter_col, in_list
                    )
                )
                or []
            )
        except Exception as e:
            print("[upsert] 查询 {} 已有行失败, 本批全部走新建: {}".format(TABLE, e))
            ex = []
        for er in ex:
            k = tuple(str(er.get(c)) for c in key_cols)
            if k not in existing:
                existing[k] = er.get("id")
    # 分流: 去重键齐全且命中则更新(带 id); 否则新建
    to_insert, to_update = [], []
    for r in rows:
        vals = [r.get(c) for c in key_cols]
        if any(str(v) in ("", "None") for v in vals):
            to_insert.append(r)
            continue
        k = tuple(str(v) for v in vals)
        if k in existing:
            r["id"] = existing[k]
            r.pop("create_time", None)  # 更新不改创建时间
            to_update.append(r)
        else:
            to_insert.append(r)
    if to_insert:
        db.batchInsertToDB(TABLE, to_insert, user_id=user_id)
    if to_update:
        db.batchUpdateToDB(TABLE, to_update, user_id=user_id)
    return len(to_insert), len(to_update)


# ==================== 转过账平台格式 (external_system_save 入参) ====================
def _to_float(v):
    """转 float; 转不了(空/None/非数) 缺省 0.0(平台 transaction_qty/pricing_unit_quantity 必填 float)。"""

    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _doc_date(year, period):
    """uf_year(如 2026) + uf_period(如 7/07) 推算当月1号 YYYY-MM-DD(平台 document_date/posting_date
    必填, 长度须=10)。解析失败返回空串, 交平台校验报"凭证日期格式错误"。"""

    try:
        return "{:04d}-{:02d}-01".format(int(str(year)), int(str(period)))
    except (TypeError, ValueError):
        return ""


def _build_doc_data(details):
    """把原材料批次明细重组为 external_system_save 入参: 每条明细组为 1 张凭证(1 header + 1 item)。
    字段来源(平台必填 取自 ut_rm_production_batch/入参):
      company_code             取入参 company_code
      plant_code               取 get_plant_by_company(company_code) 反查
      stor_loc_code             取前端入参 stor_loc_code
      document_date / posting_date / external_sys_document_create_date 取 year+period 当月1号
      movement_type             取 uf_qty_m 负数 SC01, 正数/零 S001
      external_sys_unique_doc_sn 取 batch_sn(批次为空则 公司_物料 兜底)
      transaction_qty / pricing_unit_quantity 取 uf_qty_m(float)
      transaction_uom / pricing_unit_of_measure 取 uf_basic_uom
    """

    docs = []
    for d in details:
        company_code = _val(d, "company_code")
        mat_code = _val(d, "mat_code")
        batch_sn = _val(d, "batch_sn")
        uom = _val(d, "basic_uom") or " "  # Oracle NOT NULL 占位
        qty = _to_float(_val(d, "qty_m", 0))
        movement_type = MOVE_TYPE_NEG if qty < 0 else MOVE_TYPE_POS  # 0 归正数(入库)
        doc_date = _doc_date(_val(d, "year"), _val(d, "period"))
        sn = batch_sn or "{}_{}".format(
            company_code, mat_code
        )  # 唯一凭证号: 优先批次号
        header = {
            "external_sys_unique_doc_sn": sn,
            "document_date": doc_date,
            "posting_date": doc_date,
            "company_code": company_code,
            "reversal_mark": 0,  # 无冲销语义, 默认 0
            "external_sys_document_create_date": doc_date,  # 取凭证日期(同 ZZITE)
            "message_text": "",  # 占位, 由 external_system_check 回填
        }
        item = {
            "external_sys_unique_doc_sn": sn,
            "external_sys_unique_doc_items": 1,
            "line_id": 1,
            "movement_type": movement_type,
            "plant_code": get_plant_by_company(
                company_code
            ),  # 工厂: 由 company_code 反查 t_os_company_plant_alloc
            "company_code": company_code,
            "stor_loc_code": _val(d, "stor_loc_code"),  # 库存地点(前端入参)
            "mat_code": mat_code,
            "batch_sn": batch_sn,
            "transaction_qty": qty,
            "transaction_uom": uom,
            "pricing_unit_quantity": qty,
            "pricing_unit_of_measure": uom,
            "pir_version": " ",  # Oracle NOT NULL 占位(评估版本)
            # rel_po_sn 必须给键(可空): 平台 price 规则 required_func_depend=["rel_po_sn"]
            # 直接 full_data["rel_po_sn"] 取值, 缺键抛 KeyError(被外层 catch 成"平台调用异常")
            "rel_po_sn": "",
        }
        docs.append({**header, "item": [item]})
    return docs


# 平台物料凭证行项目表(external_system_save 落库目标)
T_EXT_MD_ITEM = "t_external_sys_md_item"
RESERVED1_VAL = "原材料入库"  # t_external_sys_md_item.reserved1 回写值(长度限制 255)


def _update_md_item_reserved1(details, db):
    """external_system_save 成功后, 按 (mat_code, batch_sn) 把 t_external_sys_md_item.reserved1
    更新为"原材料入库"。未落库(校验未过 / mat_code·batch_sn 缺失)的行命中 0 行无副作用; 回写失败不阻断主流程。"""
    for d in details:
        mat_code = _val(d, "mat_code")
        batch_sn = _val(d, "batch_sn")
        if not mat_code or not batch_sn:
            continue
        sql = "UPDATE `{}` SET `reserved1` = '{}' WHERE `mat_code` = '{}' AND `batch_sn` = '{}'".format(
            T_EXT_MD_ITEM, RESERVED1_VAL, _esc(mat_code), _esc(batch_sn)
        )
        try:
            db.exec_sql(sql)
        except Exception as e:  # 回写失败不应让已成功的过账丢失结果
            print(
                "[reserved1] 更新失败 mat={} batch={}: {}".format(mat_code, batch_sn, e)
            )


# ==================== 接收入口 ====================
def save_raw_material_production_batch(payload, user_id):
    """原材料生产批次接收接口
    接收参数: {"interface_code":..., "payload":{"guid":..., "data":[{...}, ...]}}
               或 {"data": [...]} / 直接扁平传 list
    :param user_id: 操作人 id
    :return {"type":"S"/"E", "code":..., "message":..., "count": n}
    """
    raw = payload.get("data") if isinstance(payload, dict) else payload
    data = _normalize_to_list(raw)
    if not data:
        return {
            "type": "E",
            "code": CODE_MISSING_PARAM,
            "message": "无数据(data 为空)",
            "count": 0,
        }

    now = _now()
    rows, errors = _build_rows(data, FIELD_MAP, now)
    if errors:  # 有任一条校验不过 -> 整批不落库, 返回明细错误
        return {
            "type": "E",
            "code": CODE_MISSING_PARAM,
            "message": "校验失败: " + " | ".join(errors),
            "count": 0,
        }

    # 落库: 按 (uf_mat_code, uf_batch_sn) upsert(唯一索引 MAT_CODE_BACH_SN), 相同物料+批次则更新, 否则新建
    n_ins, n_upd = _upsert_batches(rows, db, user_id)
    db.updateDBObj()

    # 落库后转平台格式调 external_system_save(平台校验 + 落 t_external_sys_md_*)。
    # 平台失败不回滚已落库明细: 落库是接收主目的, 平台结果附加在 message / platform_* 字段透出。
    plat_ok, plat_all, plat_msg = 0, len(rows), ""
    try:
        doc_data = _build_doc_data(data)
        all_count, pass_count, _items, msg = external_system_save(doc_data)
        plat_all, plat_ok, plat_msg = all_count, pass_count, msg or ""

        print(
            "plat_ok={}, plat_all={}, plat_msg={}".format(plat_ok, plat_all, plat_msg)
        )

    except Exception as e:  # 平台调用异常不应让已落库的明细丢失结果
        plat_msg = "平台调用异常: {}".format(e)

    if plat_msg:
        return {
            "type": "S",
            "code": CODE_OK,
            "message": "保存成功: 新增{}条, 更新{}条; 平台提交失败: {}".format(
                n_ins, n_upd, plat_msg
            ),
            "count": len(rows),
            "platform_ok": 0,
            "platform_all": plat_all,
        }
    # external_system_save 成功后按 mat_code+batch_sn 回写 t_external_sys_md_item.reserved1 = "原材料入库"
    _update_md_item_reserved1(data, db)
    note = (
        "已提交平台"
        if plat_ok >= plat_all
        else "已提交平台(部分未通过校验: 成功{}/共{})".format(plat_ok, plat_all)
    )
    return {
        "type": "S",
        "code": CODE_OK,
        "message": "保存成功: 新增{}条, 更新{}条; {}".format(n_ins, n_upd, note),
        "count": len(rows),
        "platform_ok": plat_ok,
        "platform_all": plat_all,
    }


def get_company_by_plant(plant_code):
    """根据工厂代码获取公司代码"""
    query_sql = "SELECT `company_code` FROM `t_os_company_plant_alloc` "
    if plant_code:
        query_sql += " WHERE `plant_code` = {}".format(repr(plant_code))
    result_data = db.query_sql(query_sql)
    company_code = result_data[0].get("company_code") if result_data else ""
    return company_code


def get_plant_by_company(company_code):
    """根据公司代码获取工厂代码"""
    query_sql = "SELECT `plant_code` FROM `t_os_company_plant_alloc` "
    if company_code:
        query_sql += " WHERE `company_code` = {}".format(repr(company_code))
    result_data = db.query_sql(query_sql)
    plant_code = result_data[0].get("plant_code") if result_data else ""
    return plant_code


if __name__ == "__main__":
    # 本地测试: 必填给全, 非必填/货币留空看默认值兜底
    sample_payload = {
        "data": [
            {
                "mat_code": "J11020010001",
                "company_code": "J0008",
                "year": "2026",
                "period": "07",
                "batch_sn": "P20260722001",
                "currency": "CNY",
                "qty_m": 100,
                "cur_m": 5000,
                "basic_uom": "013",
                "stor_loc_code": "02",  # 库存地点
            }
        ]
    }
    result = save_raw_material_production_batch(sample_payload, user_id=0)
    print(
        "type={} count={} message={}".format(
            result.get("type"), result.get("count"), result.get("message")
        )
    )

# {
#     "payload": {
#         "data": [
#             {
#                 "mat_code": "J11020010001",
#                 "company_code": "J0008",
#                 "year": "2026",
#                 "period": "07",
#                 "batch_sn": "P20260722001",
#                 "currency": "CNY",
#                 "qty_m": 100,
#                 "cur_m": 5000,
#                 "basic_uom": "013",
#                 "stor_loc_code": "02"
#             }
#         ],
#         "guid": "0001AA100000008XR5"
#     },
#     "interface_code": "erp_raw_material_production_batch"
# }
