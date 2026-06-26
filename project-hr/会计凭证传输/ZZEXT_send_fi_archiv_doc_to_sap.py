# -*- coding: UTF-8 -*-
"""
@File    : ZZEXT_send_fi_archiv_doc_to_sap.py
@Author  : tianzhao.li@dxdstech.com
@Date    : 2026/1/10 15:03
@explain : 会计凭证过账推送接口

  调用方向:   秘火->SAP
  模块名称:   会计引擎
  接口名称:   会计凭证过账推送接口
  接口说明：  会计过账凭证, 汇总凭证传输过账, 调 SAP RFC(ZRFC_MH_DOC_POST_MASS),
             按 公司代码+年度+期间 查待过账凭证, 逐条推送并回写结果至
             t_fi_doc_for_archiv_transfer_log / t_fi_doc_for_archiv_head。

  收发方式参照 ZZ_standard_cost_update.py / ZZ_semiproduct_deduct_push.py:
    入口 Request().body() 取参, Response.set_body/commit 返回;
    返回体 {code, msg, data, display}, 查询支持 _payload_ 过滤/排序/分页/导出。
"""
import json
import traceback
from datetime import datetime
from functools import lru_cache

from DbHelper import DbHelper
from libenhance import Request, Response
from ToolsMethods import (
    GetExportData,
    Paginator,
    calc_time,
    create_table_alias,
    display_to_entozh,
    generate_raw_sql,
)
from utils import ItfBizError, query_db_records_by_cond, update_db_record_by_cond
from ZZEXT_SapRFC import SAPRFC

# ---------- 固定值(按接口需求, 集中维护) ----------
# RFC 函数模块
RFC_INTERFACE_CODE = "ZRFC_MH_DOC_POST_MASS"
INTERFACE_NAME = "会计凭证过账推送接口"
# 会计凭证类型默认 EA(成本中心相关的去掉)
DOC_TYPE = "EA"
accounting_document_type = "EA"

# 业务表
ARCHIV_HEAD_TABLE = "t_fi_doc_for_archiv_head"
ARCHIV_DETAIL_TABLE = "t_fi_doc_for_archiv_details"
TRANSFER_LOG_TABLE = "t_fi_doc_for_archiv_transfer_log"

# 抬头查询列(推送组装 + 查询展示 共用)
HEAD_COLUMNS = '''`id`,
                `fi_ledger`,
                `company_code`,
                `accounting_document_type`,
                `fi_sum_doc_type`,
                `archiv_doc_num`,
                `document_date`,
                `posting_date`,
                `year`,
                `period`,
                `summary_unique_number`,
                `transaction_currency`,
                `basic_currency`,
                `exchange_rate`,
                `header_text`,
                `sum_dr_amount_bc`,
                `sum_cr_amount_bc`,
                `posting_status`,
                `verify_status`,
                `document_category`,
                `associated_doc_type`,
                `attachment_qty`,
                `posting_person`,
                `reference1_head`,
                `reference2_head`,
                `note`,
                `update_time`'''

# 模块级缓存 / 数据库
company_cost_element_info = {}

db = DbHelper()


# ---------- 公共参数校验(posting / query 共用) ----------
def validate_fi_archiv_doc_params(data):
    """校验会计凭证过账接口的公共参数(company_code / year / period)

    与其他接口一致: 必填 company_code/year/period; year 4 位数字; period 1-12 补零。

    :param data: 请求里的 data 字典(即 body["data"])
    :return: (is_valid, message, params)
        params 成功时含 {"company_code","year","period"}; 失败为 {}
    """
    if not isinstance(data, dict) or not data:
        return False, "请求数据(data)为空或格式错误", {}

    company_code = data.get("company_code")
    year = data.get("year")
    period = data.get("period")

    company_code = company_code.strip() if isinstance(company_code, str) else company_code
    year = str(year).strip() if year is not None else ""
    period = str(period).strip() if period is not None else ""

    missing = []
    if not company_code:
        missing.append("company_code(公司代码)")
    if not year:
        missing.append("year(年度)")
    if not period:
        missing.append("period(期间)")
    if missing:
        return False, f"缺少必填参数: {'、'.join(missing)}", {}

    if not (year.isdigit() and len(year) == 4):
        return False, f"年度(year)应为4位数字, 当前: {year!r}", {}
    if not period.isdigit():
        return False, f"期间(period)必须为数字, 当前: {period!r}", {}
    period_num = int(period)
    if period_num < 1 or period_num > 12:
        return False, f"期间(period)必须在1-12之间, 当前: {period}", {}
    period = f"{period_num:02d}"

    params = {"company_code": str(company_code), "year": year, "period": period}
    return True, "校验通过", params


# ==================== 推送入口 ====================
@calc_time
def send_fi_archiv_doc():
    """会计凭证过账推送接口 按钮(无参 HTTP 入口)
    按 company_code + year + period 查待过账凭证, 逐条调 RFC 过账并回写。
    """
    print("===会计凭证过账推送接口===")
    req = Request()
    res = Response()
    body = json.loads(req.body())
    print("body---", body)
    user_id = req.header("user_id")

    payload = body.get("data") or {}
    task_id = payload.get("task_id")  # 仅日志关联用, 缺省为 None

    # 公共参数校验, 失败直接返回
    ok, msg, params = validate_fi_archiv_doc_params(payload)
    if not ok:
        response = {"code": 500, "type": "E", "msg": msg}
        print(f"===会计凭证过账推送接口=== 参数校验失败: {msg}")
        res.set_body(json.dumps(response))
        res.commit(True)
        return

    # 校验通过, 调推送 core
    res_bus = send_fi_archiv_doc_core(user_id, task_id, params["company_code"], params["year"], params["period"])
    print(f"===会计凭证过账推送接口=== 处理结束!!! 返回: {res_bus}")
    res.set_body(json.dumps(res_bus))
    res.commit(True)


@calc_time
def send_fi_archiv_doc_core(user_id, task_id, company_code, year, period):
    """会计凭证过账 核心逻辑

    按 公司代码+年度+期间 查待过账(posting_status != 'S')的汇总凭证抬头,
    所有凭证合并到一次 SAP RFC(ZRFC_MH_DOC_POST_MASS)调用过账, 整批共用一个返回结果,
    逐条回写, 最后回查最新状态返回(供前端刷新)。

    :return: {"code", "msg", "data", "display"}
    """
    code, msg = 200, "无可过账记录"
    body = {"data": {"company_code": company_code, "year": year, "period": period}}
    print(f"===会计凭证过账 core=== user_id={user_id} task_id={task_id} "
          f"company_code={company_code} {year}-{period}")

    # 查询待过账抬头(posting_status != 'S')
    heads = get_pending_archiv_head_list(company_code, year, period)
    print("待过账抬头--", heads)

    total = len(heads)
    if total:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        operator_data = {"create_id": user_id, "create_time": now, "update_id": user_id, "update_time": now}
        try:
            # 一次性推送: 所有凭证合并到一次 RFC 调用
            DATA, doc_meta_list, zero_meta_list = prepare_rfc_batch_request(heads)

            # 无明细(金额为0)的凭证无需过账, 直接落库成功
            for meta in zero_meta_list:
                handle_sap_response({**meta, **operator_data,
                                     "external_sn": "", "posting_status": "S", "note": "金额为0, 无需过账"})

            if DATA.get("TABLE"):
                rfc_resp = send_rfc_request(DATA)
                if not rfc_resp:
                    raise ItfBizError("RFC接口返回空数据")
                type_txt, message_txt, external_sn = extract_rfc_batch_response(rfc_resp)
                # 整批共用一个返回结果, 逐条回写
                for meta in doc_meta_list:
                    handle_sap_response({**meta, **operator_data,
                                         "external_sn": external_sn, "posting_status": type_txt, "note": message_txt})
                if type_txt == "S":
                    code, msg = 200, f"过账成功 {total} 条"
                else:
                    code = 206
                    msg = f"过账失败 {total} 条; {message_txt}"
            else:
                code, msg = 200, f"过账成功 {total} 条" + ("(金额为0, 无需过账)" if zero_meta_list else "")
        except Exception as e:
            traceback.print_exc()
            code = 206
            msg = f"过账异常 {total} 条; {e}"
            # 异常时把进入 TABLE 的凭证置为失败
            for meta in doc_meta_list:
                handle_sap_response({**meta, **operator_data,
                                     "external_sn": "", "posting_status": "E", "note": str(e)})

    # 回查最终状态(供前端刷新表格)
    data, display = send_fi_archiv_doc_query_data(body)
    return {"code": code, "msg": msg, "data": data, "display": display}


# ==================== 查询接口 ====================
@calc_time
def send_fi_archiv_doc_query():
    """会计凭证过账查询接口
    支持 _payload_ 里的 filter_info / sort_info / page / export_excel
    """
    print("===会计凭证过账查询接口===")
    req = Request()
    res = Response()
    body = json.loads(req.body())
    print("body----", body)

    # 公共参数校验(company_code/year/period), 失败直接返回
    ok, msg, _ = validate_fi_archiv_doc_params(body.get("data") or {})
    if not ok:
        response = {"code": 500, "type": "E", "msg": msg}
        print(f"===会计凭证过账查询接口=== 参数校验失败: {msg}")
        res.set_body(json.dumps(response))
        res.commit(True)
        return

    payload = body.get("_payload_", {})
    filter_info = payload.get("filter_info", {})
    sort_info = payload.get("sort_info", {})
    export_excel = payload.get("export_excel")

    query_data, display = send_fi_archiv_doc_query_data(body)
    if export_excel:
        stamp_suffix = datetime.now().strftime("%Y%m%d%H%M%S")
        excel_filename = f"会计凭证过账-{stamp_suffix}.xlsx"
        format_data = [{"sheet1": query_data}]
        field_dict = display_to_entozh(display)
        GetExportData(format_data, excel_filename, field_dict)
    else:
        page_size = payload.get("page", {}).get("page_size", 0)
        page_num = payload.get("page", {}).get("page_num", 1)
        paginator = Paginator(query_data, page_size)
        page_items = paginator.get_page(page_num)
        total_pages = paginator.total_pages
        data_sum = len(query_data)

        response = {
            "code": 200,
            "msg": "成功",
            "data": page_items,
            "page": {
                "page_size": page_size if page_size else len(query_data),
                "page_num": page_num,
                "page_sum": total_pages,
                "data_sum": data_sum,
            },
            "rule": {"sort_info": sort_info, "filter_info": filter_info},
            "display": display,
        }
        print(f"===会计凭证过账查询接口=== 处理结束!!! 返回: {response}")
        res.set_body(json.dumps(response))
        res.commit(True)


def send_fi_archiv_doc_query_data(body):
    """会计凭证过账 查询核心逻辑(查询接口/导出/过账回查复用)
    :return: (query_data, display)
    """
    data_filter = body.get("data") or {}
    payload = body.get("_payload_", {})
    filter_info = payload.get("filter_info", {})
    sort_info = payload.get("sort_info", {})

    # 前置筛选(任务级固定条件): 公司/年度/期间/过账状态/归档凭证号
    prefix_filter = {}
    for field in ("company_code", "year", "period", "posting_status", "archiv_doc_num"):
        val = data_filter.get(field)
        if val not in (None, ""):
            prefix_filter[field] = val

    query_sql = f"""
            SELECT
                {HEAD_COLUMNS}
            FROM
                `{ARCHIV_HEAD_TABLE}`
            WHERE 1 = 1
        """

    table_alias = create_table_alias(HEAD_COLUMNS)
    where_sql, sort_sql = generate_raw_sql(prefix_filter, filter_info, sort_info, table_alias)
    if not sort_sql:
        sort_sql = " ORDER BY `id` DESC"
    if where_sql:
        where_sql = where_sql.replace("WHERE ", " AND ")
        full_query_sql = query_sql + where_sql + sort_sql
    else:
        full_query_sql = query_sql + sort_sql

    full_query_sql = full_query_sql.replace("    ", " ").strip()
    print(full_query_sql)
    query_data = db.query_sql(full_query_sql)

    display = [
        {"field": "company_code", "description": "公司代码"},
        {"field": "fi_ledger", "description": "财务核算分类账"},
        {"field": "accounting_document_type", "description": "会计凭证类型"},
        {"field": "fi_sum_doc_type", "description": "归档汇总类型"},
        {"field": "archiv_doc_num", "description": "归档汇总凭证号"},
        {"field": "document_date", "description": "凭证日期"},
        {"field": "posting_date", "description": "过账日期"},
        {"field": "year", "description": "年度"},
        {"field": "period", "description": "期间"},
        {"field": "summary_unique_number", "description": "汇总号"},
        {"field": "transaction_currency", "description": "交易货币"},
        {"field": "basic_currency", "description": "本位币"},
        {"field": "exchange_rate", "description": "汇率"},
        {"field": "header_text", "description": "抬头文本"},
        {"field": "sum_dr_amount_bc", "description": "汇总借方金额_本位币"},
        {"field": "sum_cr_amount_bc", "description": "汇总贷方金额_本位币"},
        {"field": "posting_status", "description": "过账状态"},
        {"field": "verify_status", "description": "校验状态"},
        {"field": "document_category", "description": "单据类别"},
        {"field": "associated_doc_type", "description": "业务凭证类型"},
        {"field": "attachment_qty", "description": "附件数"},
        {"field": "posting_person", "description": "过账人"},
        {"field": "reference1_head", "description": "参考信息1"},
        {"field": "reference2_head", "description": "参考信息2"},
        {"field": "note", "description": "备注"},
        {"field": "update_time", "description": "更新时间"},
    ]

    return query_data, display


# ==================== RFC 通道(批量) ====================
def prepare_rfc_batch_request(heads):
    """组装 批量 RFC 请求数据: 所有待过账凭证合并到一次调用(ZRFC_MH_DOC_POST_MASS)

    每条凭证的明细行都带上本凭证抬头字段(IP_INDEX=summary_unique_number 作为凭证唯一标识,
    供 SAP 在一个 TABLE 里区分多凭证), 全部并入一个 TABLE, 共用一个 BUKRS(company_code)。
    无明细(金额为0)的凭证不进 TABLE, 由调用方直接落库成功。

    :param heads: 待过账抬头列表
    :return: (DATA, doc_meta_list, zero_meta_list)
        DATA            = {"BUKRS": company_code, "TABLE": [有明细凭证的所有行]}
        doc_meta_list   = 进入 TABLE 的凭证回写元信息
        zero_meta_list  = 无明细(金额为0)的凭证回写元信息
    """
    if not heads:
        return {"BUKRS": "", "TABLE": []}, [], []

    company_code = heads[0].get("company_code", "")
    table_rows = []
    doc_meta_list = []    # 有明细, 进入 TABLE
    zero_meta_list = []   # 无明细(金额为0), 不进 TABLE

    for head in heads:
        summary_unique_number = head.get("summary_unique_number", "")
        head_company_code = head.get("company_code", "") or company_code
        head_year = head.get("year", "")

        meta = {
            "summary_unique_number": summary_unique_number,
            "company_code": head_company_code,
            "year": head_year,
            "archiv_doc_num": head.get("archiv_doc_num", ""),
            "fi_sum_doc_type": head.get("fi_sum_doc_type", ""),
        }

        detail_list = find_fi_doc_for_archiv_details(summary_unique_number, head_company_code, head_year)
        if not detail_list:
            zero_meta_list.append(meta)
            continue

        # 字段转换(按 t_fi_post_erp_value_transfer 配置)
        for i in get_fi_post_erp_value_transfer_data():
            if head.get(i["field_name"]) == i["before_value"]:
                head[i["field_name"]] = i["after_value"]
            for j in detail_list:
                if j.get(i["field_name"]) == i["before_value"]:
                    j[i["field_name"]] = i["after_value"]

        cost_element_dict = get_company_cost_element_info(head_company_code)
        rfc_head = build_rfc_send_data_head(head)
        rfc_items = build_rfc_send_data_items(detail_list, cost_element_dict)
        # 每条明细行带上本凭证抬头(含 IP_INDEX 凭证标识)
        for item in rfc_items:
            table_rows.append({**rfc_head, **item})

        doc_meta_list.append(meta)

    DATA = {"BUKRS": company_code, "TABLE": table_rows}
    print(f"===RFC批量请求数据=== {RFC_INTERFACE_CODE}: 凭证 {len(heads)} 条, "
          f"有明细 {len(doc_meta_list)} 条, 明细行 {len(table_rows)} 行")
    return DATA, doc_meta_list, zero_meta_list


def build_rfc_send_data_head(archiv_doc_head_data):
    """组装 RFC 请求 head 数据(字段全大写)"""
    head = {
        "MANDT": "",  # [CLNT|3] 集团 (SAP自动填充)
        "IP_INDEX": archiv_doc_head_data.get("summary_unique_number"),  # [NUMC|18] 序列编号(唯一号)
        "ITEMNO_ACC": "",  # [NUMC|3] 行项目编号(抬头不用)
        "EMSDOC": "",  # [CHAR|3] 报账单号
        "DOC_TYPE": archiv_doc_head_data.get("fi_sum_doc_type", ''),  # [CHAR|2] 凭证类型
        "COMP_CODE": archiv_doc_head_data.get("company_code"),  # [CHAR|4] 公司代码
        "FISC_YEAR": archiv_doc_head_data.get("year"),  # [NUMC|4] 会计年度
        "DOC_DATE": archiv_doc_head_data.get("document_date"),  # [DATS|8] 凭证日期
        "PSTNG_DATE": archiv_doc_head_data.get("posting_date"),  # [DATS|8] 过账日期
        "FIS_PERIOD": archiv_doc_head_data.get("period"),  # [NUMC|2] 会计期间
        "HEADER_TXT": archiv_doc_head_data.get("year", "") + archiv_doc_head_data.get("period", "") + archiv_doc_head_data.get(
            "header_text", ""),  # [CHAR|25] 凭证抬头文本
        "REF_DOC_NO": archiv_doc_head_data.get("archiv_doc_num"),  # [CHAR|16] 参考凭证编号
        "CURRENCY": archiv_doc_head_data.get("transaction_currency"),  # [CUKY|5] 货币码
        "TYPE": "",  # [CHAR|1] 单字符标记
        "ACCOUNTING_DOCUMENT_TYPE": accounting_document_type,
    }
    return head


def build_rfc_send_data_items(archiv_doc_detail_list, cost_element_dict):
    """组装 RFC 请求 item 数据(字段全大写)"""
    items = []
    for item in archiv_doc_detail_list:
        amount_tc = float(item.get("dc_amount_tc", 0))  # 凭证货币金额
        amount_bc = float(item.get("dc_amount_bc", 0))  # 本币金额
        debit_credit_mark = item.get("debit_credit_mark")  # 凭证借贷标识 Dr/Cr

        val_sp_gl_ind = ""  # 特别总账标志
        val_bschl = ""      # 过账代码
        val_xnege = ""      # 负过账标识 (金额>0空; 金额<0传X)
        val_rstgr = ""      # 付款原因代码
        val_value_date = ""  # 起息日
        val_alloc_nbr = item.get("mat_doc_sn", "") + " " + item.get("mat_doc_items", "") if item.get(
            "fi_sum_doc_type") == "Z9" else ""  # 分配编号
        val_tax_code = ""   # 税码

        kostl = item.get("cost_center", "")
        aufnr = item.get("prodosn", "") or item.get("cost_business_object1", "")
        projk = item.get("wbs_elements", "")

        item = {
            "ITEMNO_ACC": item.get("summary_line"),  # [NUMC|3] 行项目编号
            "BSCHL": val_bschl,                      # [CHAR|2] 过账代码
            "GL_ACCOUNT": item.get("accounting_subjects", ""),  # [CHAR|10] 总账科目
            "SP_GL_IND": val_sp_gl_ind,              # [CHAR|1] 特别总账标志
            "CS_TRANS_T": item.get("asset_business_type", ""),  # [CHAR|3] 业务类型
            "DE_CRE_IND": debit_credit_mark,         # [CHAR|1] 借/贷标识
            "AMT_DOCCUR": str(round(amount_bc, 2)),  # [CURR|23] 本币金额
            "WRBTR": str(round(amount_tc, 2)),       # [CURR|23] 凭证货币金额
            "WAERS": "",                             # [CUKY|5] 货币码 (抬头已传CURRENCY)
            "ITEM_TEXT": item.get("item_text", ""),  # [CHAR|50] 项目文本
            "VALUE_DATE": val_value_date,            # [DATS|8] 起息日
            "ALLOC_NBR": val_alloc_nbr,              # [CHAR|18] 分配编号
            "COSTCENTER": kostl if cost_element_dict.get(item.get("accounting_subjects", "")) else "",
            # [CHAR|10] 成本中心
            "PROFIT_CTR": item.get("profit_center", ""),        # [CHAR|10] 利润中心
            "ORDERID": aufnr if cost_element_dict.get(item.get("accounting_subjects", "")) else "",
            # [CHAR|12] 订单编号
            "WBS_ELEMENT": projk if cost_element_dict.get(item.get("accounting_subjects", "")) else "",
            # [CHAR|24] WBS元素
            "TAX_CODE": val_tax_code,                 # [CHAR|2] 税码
            "MATERIAL": item.get("mat_code", ""),     # [CHAR|40] 物料编号
            "QUANTITY": item.get("basic_uom", 0),     # [QUAN|13] 数量
            "MEINS": "" if not item.get("basic_qty", "") else item.get("basic_qty", ""),
            # [UNIT|3] 基本计量单位
            "TRADE_ID": item.get("trade_partner_code", ""),  # [CHAR|6] 贸易伙伴
            "PNTRMS": item.get("payment_terms", ""),         # [CHAR|4] 付款条件
            "BLNNE_DATE": item.get("baseline_date", ""),     # [DATS|8] 到期日计算基准日期
            "CMT_ITEM": "",  # [CHAR|14] 承诺项目
            "BUS_AREA": "",  # [CHAR|4] 业务范围
            "KNDNR": item.get("customer_code", ""),  # [CHAR|10] 客户
            "ARTNR": item.get("mat_code", ""),       # [CHAR|40] 产品号
            "PRCTR": item.get("profit_center", ""),  # [CHAR|10] 利润中心
            "RSTGR": val_rstgr,                      # [CHAR|3] 付款原因代码
            "ASSET_NO": item.get("asset_code1", ""),   # [CHAR|12] 主要资产编号
            "SUB_NUMBER": item.get("asset_code2", ""),  # [CHAR|4] 资产子编号
            "XNEGE": val_xnege,                       # [CHAR|1] 负过账标识
        }
        items.append(item)
    return items


def send_rfc_request(DATA):
    """发送 RFC 请求 (ZRFC_MH_DOC_POST_MASS)
    :param DATA: {"BUKRS": 公司代码, "TABLE": [所有凭证的明细行(各行含本凭证抬头字段 + IP_INDEX)]}
    """
    print(f"===RFC请求数据=== {RFC_INTERFACE_CODE}: {DATA}")

    sap_rfc = SAPRFC()
    try:
        rfc_resp_data = sap_rfc.call(RFC_INTERFACE_CODE, DATA)
    finally:
        sap_rfc.close()
    print(f"===RFC请求返回结果===: {rfc_resp_data}")
    return rfc_resp_data


def extract_rfc_batch_response(rfc_resp_data):
    """解析批量 RFC 返回(整批共用一个结果)
    :return: (type_txt, message_txt, external_sn)
    """
    rfc_resp_data = rfc_resp_data or {}

    # 消息类型/消息: pyrfc 顶层导出参数 MSG_TYP / MSG (兼容历史 TYPE / msg_typ)
    type_txt = str(rfc_resp_data.get("MSG_TYP") or rfc_resp_data.get("TYPE") or rfc_resp_data.get("msg_typ") or "E")
    message_txt = rfc_resp_data.get("MSG") or rfc_resp_data.get("msg") or "RFC接口调用失败"
    if type_txt != "S":
        type_txt = "E"
    else:
        message_txt = "凭证创建成功"

    # 会计凭证号: 顶层 BELNR 或返回表内逐行 BELNR
    external_sns = []
    belnr = rfc_resp_data.get("BELNR") or rfc_resp_data.get("belnr") or ""
    if belnr:
        external_sns.append(str(belnr))
    if not external_sns:
        for value in rfc_resp_data.values():
            if isinstance(value, list):
                for row in value:
                    if isinstance(row, dict):
                        row_belnr = row.get("BELNR") or row.get("belnr") or ""
                        if row_belnr:
                            external_sns.append(str(row_belnr))

    return type_txt, message_txt, ",".join(external_sns)


# ==================== 查询: 待过账抬头 / 凭证明细 ====================
def get_pending_archiv_head_list(company_code, year, period):
    """查询待过账的汇总凭证抬头(company_code/year/period 且 posting_status != 'S')
    :return: list[dict]
    """
    cond = (
        f" AND `company_code`='{company_code}'"
        f" AND `year`='{year}'"
        f" AND `period`='{period}'"
        f" AND `posting_status` != 'S'"
        f" ORDER BY `id` ASC"
    )
    return query_db_records_by_cond(db, ARCHIV_HEAD_TABLE, cond, HEAD_COLUMNS)


@calc_time
def find_fi_doc_for_archiv_details(summary_unique_number, company_code, year):
    """查某条汇总凭证的明细(全字段, LEFT JOIN 抬头取 posting_date/exchange_rate)
    :param summary_unique_number: 汇总唯一号(定位单条凭证)
    :return: 明细列表
    """
    cond = f" AND t1.`summary_unique_number`='{summary_unique_number}'"
    if company_code:
        cond += f" AND t1.`company_code`='{company_code}'"
    if year:
        cond += f" AND t1.`year`='{year}'"

    sql = f"""
    SELECT
        t1.`id`,
        t1.`fi_ledger`,
        t1.`summary_unique_number`,
        t1.`summary_line`,
        t1.`company_code`,
        t1.`year`,
        t1.`archiv_doc_num`,
        t1.`debit_credit_mark`,
        t1.`accounting_subjects`,
        t1.`post_customer_code`,
        t1.`post_vendor_code`,
        t1.`basic_uom`,
        t1.`basic_qty`,
        t1.`basic_qty_dc_mark`,
        t1.`cost_uom`,
        t1.`cost_qty`,
        t1.`cost_qty_dc_mark`,
        t1.`transaction_currency`,
        t1.`transaction_currency_amount`,
        t1.`dc_amount_tc`,
        t1.`basic_currency`,
        t1.`basic_currency_amount`,
        t1.`dc_amount_bc`,
        t1.`vendor_code`,
        t1.`customer_code`,
        t1.`trade_partner_code`,
        t1.`payment_terms`,
        t1.`baseline_date`,
        t1.`due_date`,
        t1.`asset_code1`,
        t1.`asset_code2`,
        t1.`equipment_id`,
        t1.`cost_center`,
        t1.`expense_type`,
        t1.`profit_center`,
        t1.`tax_code`,
        t1.`project_sn`,
        t1.`wbs_elements`,
        t1.`cost_business_object1`,
        t1.`cost_business_object`,
        t1.`plant_code`,
        t1.`mat_code`,
        t1.`asset_business_type`,
        t1.`prodosn`,
        t1.`po_sn`,
        t1.`po_items`,
        t1.`invoice_doc_sn`,
        t1.`invoice_doc_item`,
        t1.`so_sn`,
        t1.`so_items`,
        t1.`sales_invoice`,
        t1.`sales_invoice_item`,
        t1.`dn_sn`,
        t1.`dn_item`,
        t1.`mat_doc_sn`,
        t1.`mat_doc_items`,
        t1.`clearing_document_number`,
        t1.`clearing_fiscal_year`,
        t1.`clearing_date`,
        t1.`cash_flow`,
        t1.`item_no`,
        t1.`item_text`,
        t1.`customization_field1`,
        t1.`customization_field2`,
        t1.`customization_field3`,
        t1.`customization_field4`,
        t1.`house_bank_code`,
        t1.`house_bank_account`,
        t1.`group_account_chart`,
        t1.`group_accounting_subjects`,
        t1.`parallel_account_chart`,
        t1.`parallel_accounting_subjects`,
        t1.`data_type`,
        t1.`create_id`,
        t1.`create_time`,
        t1.`update_id`,
        t1.`update_time`,
        t1.`note`,
        t2.`posting_date`,
        t2.`exchange_rate`
    FROM `{ARCHIV_DETAIL_TABLE}` AS t1
    LEFT JOIN `{ARCHIV_HEAD_TABLE}` AS t2 using(`year`,`company_code`,`summary_unique_number`)
    WHERE 1 =1  {cond}
    ORDER BY t1.`id` ASC;
    """
    data = db.query_sql(sql)
    return data


@lru_cache(maxsize=1)
def get_fi_post_erp_value_transfer_data():
    """获取所有 ERP 值转换配置(带缓存)"""
    transfer_sql = "SELECT `field_name`, `before_value`, `after_value` FROM `t_fi_post_erp_value_transfer` "
    return db.query_sql(transfer_sql)


def get_company_cost_element_info(company_code):
    """获取公司代码相关的成本要素(带缓存)"""
    global company_cost_element_info

    if company_code not in company_cost_element_info:
        query_sql = f"SELECT `cost_element`, `company_code`, `cost_area` FROM `t_os_company` LEFT JOIN `t_acd_cost_element` USING(`cost_area`) WHERE `company_code` = '{company_code}' "
        cost_element_data = db.query_sql(query_sql)
        cost_element_info = {i["cost_element"]: i for i in cost_element_data} if cost_element_data else {}
        company_cost_element_info[company_code] = cost_element_info
    else:
        cost_element_info = company_cost_element_info.get(company_code, {})

    return cost_element_info


# ==================== 回写 ====================
def handle_sap_response(resp_dto_data):
    """处理返回数据: 回写 transfer_log, 并同步 head 过账状态(供待推送判定/展示)"""
    print(f"===RFC请求成功后处理=== 转换后数据: {resp_dto_data}")
    save_archiv_doc_transfer_log(resp_dto_data, db)
    update_archiv_head_status(resp_dto_data, db)


def save_archiv_doc_transfer_log(data, db=None):
    """回写 transfer_log(只 UPDATE 不 INSERT)"""
    cond = f" AND company_code='{data.get('company_code')}' AND year='{data.get('year')}' AND summary_unique_number='{data.get('summary_unique_number')}'"
    update_cols = ("external_sn", "posting_status", "update_id", "update_time", "note")
    update_db_record_by_cond(db, TRANSFER_LOG_TABLE, cond, update_cols, data)


def update_archiv_head_status(data, db=None):
    """同步更新 head 过账状态/备注(让 posting_status!='S' 的待推送判定生效)"""
    cond = f" AND company_code='{data.get('company_code')}' AND year='{data.get('year')}' AND summary_unique_number='{data.get('summary_unique_number')}'"
    update_cols = ("posting_status", "note", "update_id", "update_time")
    update_db_record_by_cond(db, ARCHIV_HEAD_TABLE, cond, update_cols, data)


# ==================== Test ====================
Test_send_fi_archiv_doc_payload = {'data': {'id': 24, 'task_code': '1780905368759',
'step': '09-00', 'task_id': 602, 'up_task_id': 0,
'company_code': 'RACQ',
'step_name': '在制差异调整过账', 'status': '1', 'excute_user': '',
'operator_time': '', 'create_id': 1004, 'create_time': '2026-06-18 16:01:29',
'update_id': 1004, 'update_time': '2026-06-18 16:01:29', 'note': '',
'order_num': 9, 'action_type': '', 'progress': '0/0', 'percent': '0%',
'plant_code': 'RAC1', 'description': '润安模拟月结', 'year': '2026',
'period': '06', 'cost_area': 'CRM', 'cost_version': '0', 'version_description': '核算版本',

'task_info': [{'company_code': 'RACQ', 'plant_code': ['RAC0', 'RAC1']}], 'company_code_list': [{'value': 'RACQ', 'description': '华润润安公司', 'label': 'RACQ 华润润安公司'}], 'plant_code_list': [{'value': 'RAC0', 'description': '华润润安无价值工厂', 'label': 'RAC0 华润润安无价值工厂'}, {'value': 'RAC1', 'description': '华润润安有价值工厂', 'label': 'RAC1 华润润安有价值工厂'}], 'label': '1780905368759 润安模拟月结', 'value': '1780905368759', 'company_code': 'RACQ', 'company_code_desc': '华润润安公司', 'task_code_desc': '润安模拟月结', 'condition': {'task_code': '1780905368759', 'description': '润安模拟月结', 'year': '2026', 'period': '06', 'cost_area': 'CRM', 'cost_area_description': '润安成本管理组织', 'cost_version': '0', 'version_description': '核算版本', 'status': '1', 'task_info': [{'company_code': 'RACQ', 'plant_code': ['RAC0', 'RAC1']}], 'company_code_list': [{'value': 'RACQ', 'description': '华润润安公司', 'label': 'RACQ 华润润安公司'}], 'plant_code_list': [{'value': 'RAC0', 'description': '华润润安无价值工厂', 'label': 'RAC0 华润润安无价值工厂'}, {'value': 'RAC1', 'description': '华润润安有价值工厂', 'label': 'RAC1 华润润安有价值工厂'}], 'label': '1780905368759 润安模拟月结', 'value': '1780905368759', 'company_code': 'RACQ', 'company_code_desc': '华润润安公司', 'plant_code': 'RAC0', 'task_code_desc': '润安模拟月结'}, 'type': 'query'}}


def Test_send_fi_archiv_doc():
    """会计凭证过账推送接口 测试入口"""
    user_id = "test_user"
    payload = Test_send_fi_archiv_doc_payload.get("data", {}) if isinstance(Test_send_fi_archiv_doc_payload, dict) else {}
    company_code = payload.get("company_code", "")
    year = payload.get("year", "")
    period = payload.get("period", "")
    res_bus = send_fi_archiv_doc_core(user_id, None, company_code, year, period)
    print(f"===会计凭证过账推送接口=== 测试返回: {res_bus}")
    return res_bus


if __name__ == '__main__':
    Test_send_fi_archiv_doc()
