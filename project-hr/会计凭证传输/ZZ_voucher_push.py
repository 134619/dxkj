# -*- coding: UTF-8 -*-
"""
@File    : ZZ_voucher_push.py
@Author  : @dxdstech.com
@Date    : 2026/1/10 15:03
@explain : 接口说明

  调用方向:   秘火->SAP
  模块名称:   会计引擎
  接口名称:   会计凭证过账推送接口
  接口说明：  会计过账凭证, 汇总凭证传输过账

  按《华润润安接口文档-会计凭证传输接口_v2.0》调 SAP RFC ZRFC_MH_DOC_POST_MASS:
    1) 查询: 按公司代码/年度/期间 在 t_fi_doc_for_archiv_head 取归档凭证,
       过账状态/外部凭证号/备注 由 t_fi_doc_for_archiv_transfer_log 按公司代码+年度+汇总唯一号关联。
    2) 推送: 本期所有"未成功"(transfer_log.posting_status<>'S')的凭证合并成一次 MASS 调用,
       DATA_IN 每行 = 该凭证抬头字段 + 行项目字段, 以 EMSDOC(=归档凭证号) 区分不同凭证
       (DATA_IN 不含 IP_INDEX, SAP 会拒绝); 回执 DATA_OUT 按行顺序/EMSDOC 归并到各凭证,
       逐张回写 external_sn/posting_status/note。
"""
import json
import traceback
from datetime import datetime
from functools import lru_cache

from DbHelper import DbHelper
from libenhance import Request, Response
from OracleDB import OracleDB
from SummaryCertificate import getSummaryCertificate as send_fi_archiv_doc_to_oracle
from ToolsMethods import (
    GetDisplay,
    GetEnToZh,
    GetExportData,
    Paginator,
    calc_time,
    create_table_alias,
    display_to_entozh,
    generate_limit_sql,
    generate_raw_sql,
    get_total_count,
)
from utils import ItfBizError, update_db_record_by_cond
from ZZEXT_SapRFC import SAPRFC
from ZZEXT_SendRequest import SendToSap

archive_creator_info = {}
interface_config_cache = {}
company_cost_element_info = {}

db = DbHelper()
UUID = ""
DOC_TYPE = "EA"   # 会计凭证类型默认EA，成本中心相关的去掉
accounting_document_type = "EA"   # 会计凭证类型默认EA，成本中心相关的去掉

# ---------- 固定值(按接口文档 v2.0, 集中维护) ----------
# SAP RFC 函数名 / 是否过账标识
INTERFACE_CODE = "ZRFC_MH_DOC_POST_MASS"
FLAG_POST = "Y"                       # FLAG: Y=过账, 空=检查(文档 R9)

# 源表 / 明细表 / 结果(传输日志)表
ARCHIV_HEAD_TABLE = "t_fi_doc_for_archiv_head"
ARCHIV_DETAIL_TABLE = "t_fi_doc_for_archiv_details"
TRANSFER_LOG_TABLE = "t_fi_doc_for_archiv_transfer_log"

# 查询展示字段(查询/推送回查 复用)
DISPLAY = [
    {"field": "company_code", "description": "公司代码"},
    {"field": "year", "description": "年度"},
    {"field": "period", "description": "期间"},
    {"field": "summary_unique_number", "description": "汇总唯一号"},
    {"field": "archiv_doc_num", "description": "归档凭证号"},
    {"field": "fi_sum_doc_type", "description": "凭证类型"},
    {"field": "document_date", "description": "凭证日期"},
    {"field": "posting_date", "description": "过账日期"},
    {"field": "transaction_currency", "description": "货币码"},
    {"field": "header_text", "description": "抬头文本"},
    {"field": "posting_status", "description": "过账状态"},
    {"field": "external_sn", "description": "会计凭证号"},
    {"field": "note", "description": "备注"},
]


# ---------- 公共参数校验(推送 / 查询 共用) ----------
def validate_voucher_params(data):
    """校验会计凭证接口的公共参数(company_code / year / period)
    :param data: 请求里的 data 字典(即 body["data"])
    :return: (is_valid, message, params)
        params 成功时为 {"company_code", "year", "period"}; 失败为 {}
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


# 会计凭证推送 按钮
@calc_time
def voucher_push():
    """会计凭证推送接口 按钮"""
    print("===会计凭证推送接口===")
    req = Request()
    res = Response()
    body = json.loads(req.body())
    print("body---", body)
    user_id = req.header("user_id") or ""

    payload = body.get("data") or {}

    # 公共参数校验, 失败直接返回
    ok, msg, params = validate_voucher_params(payload)
    if not ok:
        response = {"code": 500, "type": "E", "msg": msg}
        print(f"===会计凭证推送接口=== 参数校验失败: {msg}")
        res.set_body(json.dumps(response))
        res.commit(True)
        return

    res_bus = voucher_push_core(user_id, params["company_code"], params["year"], params["period"])
    print(f"===会计凭证推送接口=== 处理结束!!! 返回: {res_bus}")
    res.set_body(json.dumps(res_bus))
    res.commit(True)


@calc_time
def voucher_push_core(user_id, company_code, year, period):
    """会计凭证推送 核心逻辑

    查本期待推送(transfer_log.posting_status<>'S')归档凭证, 合并成一次 MASS 调用打 RFC,
    按 行顺序/EMSDOC(=归档凭证号) 把 DATA_OUT 归并到各凭证回写, 最后回查最新状态返回。

    :return: {"code", "msg", "data", "display"}
    """
    code, msg = 200, "无可推送记录"
    body = {"data": {"company_code": company_code, "year": year, "period": period}}
    print(f"===会计凭证推送 core=== user_id={user_id} company_code={company_code} {year}-{period}")

    # 1) 查询待推送凭证(未成功即推: 含从未推送、失败)
    docs = get_pending_voucher_list(company_code, year, period)
    print("待推送凭证--", docs)
    if not docs:
        data, display = voucher_query_data(body)
        return {"code": code, "msg": msg, "data": data, "display": display}

    # 2) 合并所有凭证行 -> 一次 MASS 调用
    rfc_data, pushed_list, pass_list, row_sun_map = prepare_mass_rfc_request(docs, company_code)
    print(f"===MASS推送=== 待推{len(pushed_list)}张, 跳过(无明细){len(pass_list)}张, "
          f"DATA_IN行数={len(rfc_data.get('DATA_IN', []))}")

    # 无明细(金额为0)凭证: 直接落成功, 不进 SAP
    for p in pass_list:
        writeback_transfer_log(p["sun"], p["company_code"], p["year"], "", "S", "金额为0, 无需过账", user_id)

    # 本期凭证均无明细: 无需调 SAP
    if not pushed_list:
        try:
            db.dbCommit()
        except Exception as ce:
            print("dbCommit异常:", ce)
        code, msg = (200, f"无明细凭证 {len(pass_list)} 张, 已置成功") if pass_list else (200, "无可推送记录")
        data, display = voucher_query_data(body)
        return {"code": code, "msg": msg, "data": data, "display": display}

    # 3) 调 SAP RFC + 解析回写
    if pushed_list:
        try:
            if not rfc_data.get("DATA_IN"):
                raise ItfBizError("无有效行项目可推送")
            sap_resp = send_rfc_request(rfc_data)
            results = extract_mass_response(sap_resp, pushed_list, row_sun_map)
            for p in pushed_list:
                r = results.get(str(p["sun"]), {})
                writeback_transfer_log(p["sun"], p["company_code"], p["year"],
                                       r.get("external_sn", ""), r.get("posting_status", "E"),
                                       r.get("note", ""), user_id)

            succ = sum(1 for p in pushed_list
                       if results.get(str(p["sun"]), {}).get("posting_status") == "S")
            if succ == len(pushed_list):
                code, msg = 200, f"推送成功 {succ} 张"
            else:
                code = 206
                fails = [str(p["sun"]) for p in pushed_list
                         if results.get(str(p["sun"]), {}).get("posting_status") != "S"]
                first_note = next((results.get(str(p["sun"]), {}).get("note", "")
                                   for p in pushed_list
                                   if results.get(str(p["sun"]), {}).get("posting_status") != "S"), "")
                msg = f"推送成功 {succ}/{len(pushed_list)} 张; 失败凭证: {','.join(fails)}; {first_note}"
        except Exception as e:
            traceback.print_exc()
            code = 206
            msg = f"推送异常 {len(pushed_list)} 张; {e}"
            # 异常时把整批置为失败
            for p in pushed_list:
                writeback_transfer_log(p["sun"], p["company_code"], p["year"], "", "E", str(e), user_id)

    # 提交回写
    try:
        db.dbCommit()
    except Exception as ce:
        print("dbCommit异常:", ce)

    # 4) 回查最终状态(供前端刷新表格)
    data, display = voucher_query_data(body)
    return {"code": code, "msg": msg, "data": data, "display": display}


# 会计凭证 查询接口
@calc_time
def voucher_query():
    """会计凭证查询接口
    支持 _payload_ 里的 filter_info / sort_info / page / export_excel
    """
    print("===会计凭证查询接口===")
    req = Request()
    res = Response()
    body = json.loads(req.body())
    print("body----", body)

    # 公共参数校验(company_code/year/period), 失败直接返回
    ok, msg, _ = validate_voucher_params(body.get("data") or {})
    if not ok:
        response = {"code": 500, "type": "E", "msg": msg}
        print(f"===会计凭证查询接口=== 参数校验失败: {msg}")
        res.set_body(json.dumps(response))
        res.commit(True)
        return

    payload = body.get("_payload_", {})
    filter_info = payload.get("filter_info", {})
    sort_info = payload.get("sort_info", {})
    export_excel = payload.get("export_excel")

    query_data, display = voucher_query_data(body)
    if export_excel:
        stamp_suffix = datetime.now().strftime("%Y%m%d%H%M%S")
        excel_filename = f"会计凭证-{stamp_suffix}.xlsx"
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
        print(f"===会计凭证查询接口=== 处理结束!!! 返回: {response}")
        res.set_body(json.dumps(response))
        res.commit(True)


# 会计凭证 查询核心逻辑(查询接口/导出/推送回查 复用)
def voucher_query_data(body):
    """查 t_fi_doc_for_archiv_head(LEFT JOIN transfer_log) 会计凭证
    :return: (query_data, display)
    """
    data_filter = body.get("data") or {}
    payload = body.get("_payload_", {})
    filter_info = payload.get("filter_info", {})
    sort_info = payload.get("sort_info", {})

    # 前置筛选: 公司代码/年度/期间/过账状态/归档凭证号
    prefix_filter = {}
    for field in ("company_code", "year", "period", "posting_status", "archiv_doc_num"):
        val = data_filter.get(field)
        if val not in (None, ""):
            prefix_filter[field] = val

    columns = '''t1.`company_code` AS `company_code`,
                t1.`year` AS `year`,
                t1.`period` AS `period`,
                t1.`summary_unique_number` AS `summary_unique_number`,
                t1.`archiv_doc_num` AS `archiv_doc_num`,
                t1.`fi_sum_doc_type` AS `fi_sum_doc_type`,
                t1.`document_date` AS `document_date`,
                t1.`posting_date` AS `posting_date`,
                t1.`transaction_currency` AS `transaction_currency`,
                t1.`header_text` AS `header_text`,
                t2.`posting_status` AS `posting_status`,
                t2.`external_sn` AS `external_sn`,
                t2.`note` AS `note`,
                t2.`update_time` AS `update_time`'''

    query_sql = f'''
            SELECT
                {columns}
            FROM
                `{ARCHIV_HEAD_TABLE}` AS t1
            LEFT JOIN `{TRANSFER_LOG_TABLE}` AS t2
                ON t1.`company_code` = t2.`company_code`
                AND t1.`year` = t2.`year`
                AND t1.`summary_unique_number` = t2.`summary_unique_number`
            WHERE 1=1
        '''

    table_alias = create_table_alias(columns)
    where_sql, sort_sql = generate_raw_sql(prefix_filter, filter_info, sort_info, table_alias)
    if not sort_sql:
        sort_sql = " ORDER BY `summary_unique_number` ASC"
    if where_sql:
        where_sql = where_sql.replace("WHERE ", " AND ")
        full_query_sql = query_sql + where_sql + sort_sql
    else:
        full_query_sql = query_sql + sort_sql
    full_query_sql = full_query_sql.replace("    ", " ").strip()
    print(full_query_sql)
    query_data = db.query_sql(full_query_sql)

    return query_data, DISPLAY


# ---------- 待推送凭证查询 ----------
def get_pending_voucher_list(company_code, year, period):
    """查询本期待推送的会计凭证(transfer_log.posting_status<>'S', 含从未推送与失败)

    :return: list[dict] 每张凭证含 company_code/year/summary_unique_number/archiv_doc_num/fi_sum_doc_type/period
    """
    sql = f'''
        SELECT DISTINCT
            t1.`company_code` AS `company_code`,
            t1.`year` AS `year`,
            t1.`period` AS `period`,
            t1.`summary_unique_number` AS `summary_unique_number`,
            t1.`archiv_doc_num` AS `archiv_doc_num`,
            t1.`fi_sum_doc_type` AS `fi_sum_doc_type`
        FROM `{ARCHIV_HEAD_TABLE}` AS t1
        LEFT JOIN `{TRANSFER_LOG_TABLE}` AS t2
            ON t1.`company_code` = t2.`company_code`
            AND t1.`year` = t2.`year`
            AND t1.`summary_unique_number` = t2.`summary_unique_number`
        WHERE t1.`company_code` = '{company_code}'
            AND t1.`year` = '{year}'
            AND t1.`period` = '{period}'
            AND (t2.`posting_status` IS NULL OR t2.`posting_status` <> 'S')
        ORDER BY t1.`summary_unique_number` ASC
    '''
    print(sql)
    return db.query_sql(sql)


# ---------- SAP RFC 组装/发送/解析/回写 ----------
def prepare_mass_rfc_request(docs, company_code):
    """把多张待推凭证合并成一次 MASS 调用的 DATA_IN

    遍历每张凭证: 查抬头+明细 -> 值转换 -> 成本要素 -> 拼 head+items 行;
    无明细的凭证归入 pass_list(直接落成功, 不进 SAP)。

    :return: (rfc_data, pushed_list, pass_list, row_sun_map)
        rfc_data     = {"BUKRS", "FLAG", "DATA_IN": [行...]}
        pushed_list  = [{"sun", "company_code", "year", "archiv_doc_num"}]  # 进 SAP 的凭证
        pass_list    = [{"sun", "company_code", "year"}]                    # 无明细凭证
        row_sun_map  = [sun, ...]  # 与 DATA_IN 同序, 用于把 DATA_OUT 按行还原到所属凭证
    """
    data_in = []
    pushed_list = []
    pass_list = []
    row_sun_map = []

    cost_element_dict = get_company_cost_element_info(company_code)
    value_transfer = get_fi_post_erp_value_transfer()

    for doc in docs:
        sun = doc.get("summary_unique_number")
        year = doc.get("year")
        archiv_doc_num = doc.get("archiv_doc_num")

        head_data = get_fi_doc_for_archiv_head(sun, company_code, year, archiv_doc_num)
        if not head_data:
            print(f"汇总凭证记录不存在, 跳过: sun={sun}")
            continue
        detail_list = find_fi_doc_for_archiv_details(sun, company_code, year)

        # 字段值转换(按 t_fi_post_erp_value_transfer 配置)
        for cfg in value_transfer:
            fname, before, after = cfg.get("field_name"), cfg.get("before_value"), cfg.get("after_value")
            if head_data.get(fname) == before:
                head_data[fname] = after
            for j in detail_list:
                if j.get(fname) == before:
                    j[fname] = after

        # 无明细(金额为0): 直接落成功
        if not detail_list:
            pass_list.append({"sun": sun, "company_code": company_code, "year": year})
            continue

        # 每行 = 抬头字段 + 行项目字段; EMSDOC(=归档凭证号) 区分不同凭证, 不带 IP_INDEX(SAP 会拒绝)
        head_fields = build_rfc_head(head_data)
        items = build_rfc_items(detail_list, cost_element_dict)
        for item in items:
            data_in.append({**head_fields, **item})
            row_sun_map.append(str(sun))   # 与 data_in 同序, 用于把 DATA_OUT 按行还原到所属凭证
        pushed_list.append({"sun": sun, "company_code": company_code, "year": year, "archiv_doc_num": archiv_doc_num})

    rfc_data = {"BUKRS": company_code, "FLAG": FLAG_POST, "DATA_IN": data_in}
    print(f"组装MASS请求数据完成--- BUKRS={company_code} FLAG={FLAG_POST} DATA_IN行数={len(data_in)}")
    return rfc_data, pushed_list, pass_list, row_sun_map


def build_rfc_head(head_data):
    """组装 DATA_IN 抬头字段(凭证级, 全大写)

    注意: DATA_IN 不含 IP_INDEX(SAP 会拒绝), 用 EMSDOC(=归档凭证号) 区分不同凭证。
    """
    return {
        "EMSDOC": str(head_data.get("archiv_doc_num") or ""),            # 报账单号/注释(凭证分组键)
        "DOC_TYPE": str(head_data.get("fi_sum_doc_type") or ""),         # 凭证类型
        "COMP_CODE": str(head_data.get("company_code") or ""),           # 公司代码
        "FISC_YEAR": str(head_data.get("year") or ""),                   # 会计年度
        "DOC_DATE": _to_ymd(head_data.get("document_date")),             # 凭证日期 YYYYMMDD
        "PSTNG_DATE": _to_ymd(head_data.get("posting_date")),            # 过账日期 YYYYMMDD
        "FIS_PERIOD": str(head_data.get("period") or ""),                # 会计期间
        "HEADER_TXT": "{}{}{}".format(head_data.get("year", ""),
                                      head_data.get("period", ""),
                                      head_data.get("header_text", ""))[:25],  # 凭证抬头文本(<=25)
        "REF_DOC_NO": str(head_data.get("archiv_doc_num") or "")[:16],   # 参考凭证编号(<=16)
        "CURRENCY": str(head_data.get("transaction_currency") or ""),    # 货币码
        "TYPE": accounting_document_type,                                # 单字符标记(默认EA)
    }


def build_rfc_items(detail_list, cost_element_dict):
    """组装 DATA_IN 行项目字段(全大写)

    借/贷映射按 v2.0 文档 R31/R35: debit_credit_mark Dr->BSCHL=40,DE_CRE_IND=S; Cr->50,H。
    成本中心/订单/WBS 仅当科目属该公司成本要素时填(否则传空)。
    """
    items = []
    for item in detail_list:
        amount_tc = float(item.get("dc_amount_tc") or 0)   # 凭证货币金额
        amount_bc = float(item.get("dc_amount_bc") or 0)   # 本币金额
        dcm = str(item.get("debit_credit_mark") or "").strip()
        is_debit = dcm.upper().startswith("D")             # Dr 借 / Cr 贷

        is_cost_elem = bool(cost_element_dict.get(str(item.get("accounting_subjects") or "")))
        kostl = str(item.get("cost_center") or "")
        aufnr = str(item.get("prodosn") or "") or str(item.get("cost_business_object1") or "")
        projk = str(item.get("wbs_elements") or "")

        # 分配编号: 仅 Z9 类型取 物料凭证号+行号
        alloc_nmbr = ""
        if str(item.get("fi_sum_doc_type") or "") == "Z9":
            alloc_nmbr = "{} {}".format(item.get("mat_doc_sn", ""), item.get("mat_doc_items", "")).strip()

        items.append({
            "ITEMNO_ACC": item.get("summary_line", ""),                      # 行项目编号(=汇总行号)
            "BSCHL": "40" if is_debit else "50",                             # 过账代码 Dr->40/Cr->50
            "GL_ACCOUNT": str(item.get("accounting_subjects") or ""),        # 总账科目
            "SP_GL_IND": "",                                                 # 特别总账标志
            "CS_TRANS_T": str(item.get("asset_business_type") or ""),        # 事务类型
            "DE_CRE_IND": "S" if is_debit else "H",                          # 借/贷标识 Dr->S/Cr->H
            "AMT_DOCCUR": str(round(amount_bc, 2)),                          # 以本币计的金额
            "WRBTR": str(round(amount_tc, 2)),                               # 凭证货币金额
            "WAERS": "",                                                     # 货币码(抬头CURRENCY已传)
            "ITEM_TEXT": str(item.get("item_text") or ""),                   # 项目文本
            "VALUE_DATE": "",                                                # 起息日
            "ALLOC_NMBR": alloc_nmbr,                                        # 分配编号
            "COSTCENTER": kostl if is_cost_elem else "",                     # 成本中心(费用科目要输)
            "PROFIT_CTR": str(item.get("profit_center") or ""),              # 利润中心
            "ORDERID": aufnr if is_cost_elem else "",                        # 订单编号
            "WBS_ELEMENT": projk if is_cost_elem else "",                    # WBS元素
            "TAX_CODE": "",                                                  # 税码
            "MATERIAL": str(item.get("mat_code") or ""),                     # 物料编号
            "QUANTITY": item.get("basic_uom") or 0,                          # 数量
            "MEINS": "" if not item.get("basic_qty") else item.get("basic_qty"),  # 基本计量单位
            "TRADE_ID": str(item.get("trade_partner_code") or ""),           # 贸易伙伴
            "PMNTTRMS": str(item.get("payment_terms") or ""),                # 付款条件
            "BLINE_DATE": _to_ymd(item.get("baseline_date")),                # 到期日计算基准日期
            "CMMT_ITEM": "",                                                 # 承诺项目
            "BUS_AREA": "",                                                  # 业务范围
            "KNDNR": str(item.get("customer_code") or ""),                   # 客户
            "ARTNR": str(item.get("mat_code") or ""),                        # 产品号
            "PRCTR": str(item.get("profit_center") or ""),                   # 利润中心
            "RSTGR": "",                                                     # 付款原因代码
            "ASSET_NO": str(item.get("asset_code1") or ""),                  # 主要资产编号
            "SUB_NUMBER": str(item.get("asset_code2") or ""),                # 资产子编号
            "XNEGP": "",                                                     # 负过账标识
        })
    return items


def send_rfc_request(rfc_data):
    """调用 SAPRFC 推送 ZRFC_MH_DOC_POST_MASS
    :param rfc_data: {"BUKRS", "FLAG", "DATA_IN": [...]}
    :return: SAPRFC.call 返回结果(dict: 顶层导出参数 + DATA_OUT 表)
    """
    print(f"===RFC请求数据=== {INTERFACE_CODE}: BUKRS={rfc_data.get('BUKRS')} "
          f"FLAG={rfc_data.get('FLAG')} DATA_IN行数={len(rfc_data.get('DATA_IN', []))}")
    sap_rfc = SAPRFC()
    try:
        resp = sap_rfc.call(INTERFACE_CODE, rfc_data)
    finally:
        sap_rfc.close()
    print(f"===RFC请求返回结果===: {resp}")
    return resp


def extract_mass_response(sap_resp, pushed_list, row_sun_map):
    """把 DATA_OUT 归并到各凭证(DATA_IN 无 IP_INDEX)

    归并策略:
      1) 主: DATA_IN 无 IP_INDEX, 靠"输入行顺序"与 DATA_OUT 行顺序一一对应还原每行所属凭证
         (row_sun_map 与 data_in 同序, 精确、不受归档凭证号重复影响)。
      2) 兜底: DATA_OUT 行数与输入不一致时, 改按 EMSDOC(=归档凭证号) 归并。
      3) DATA_OUT 缺失: 用顶层 MSG_TYP/MSG/BELNR 平摊给所有凭证。

    :return: dict {sun: {"external_sn", "posting_status", "note"}}
             posting_status: 'S' 成功 / 'E' 失败
    """
    sap_resp = sap_resp or {}
    result = {}

    data_out = sap_resp.get("DATA_OUT")
    if not isinstance(data_out, list):
        data_out = []

    # 顶层兜底(DATA_OUT 缺失时用)
    top_type = str(sap_resp.get("MSG_TYP") or sap_resp.get("TYPE") or "E").upper()
    top_msg = sap_resp.get("MSG") or ""
    top_belnr = sap_resp.get("BELNR") or ""

    if data_out:
        sun_rows = {}

        if row_sun_map and len(data_out) == len(row_sun_map):
            # 1) 行顺序一一对应(最可靠, 不依赖 EMSDOC 回带)
            for sun, row in zip(row_sun_map, data_out):
                if isinstance(row, dict):
                    sun_rows.setdefault(str(sun), []).append(row)
        else:
            # 2) 行数不一致: 按 EMSDOC(=归档凭证号) 归并
            emsdoc_to_sun = {str(p.get("archiv_doc_num") or ""): str(p["sun"])
                             for p in pushed_list if p.get("archiv_doc_num")}
            for row in data_out:
                if not isinstance(row, dict):
                    continue
                sun = emsdoc_to_sun.get(str(row.get("EMSDOC") or ""))
                if sun:
                    sun_rows.setdefault(sun, []).append(row)

        # 3) 汇总每张凭证
        for p in pushed_list:
            sun = str(p["sun"])
            rows = sun_rows.get(sun, [])
            if not rows:
                result[sun] = {"external_sn": "", "posting_status": "E",
                               "note": top_msg or "SAP未返回该凭证结果"}
            else:
                result[sun] = _summarize_rows(rows, top_msg)
    else:
        # DATA_OUT 缺失: 顶层结果平摊给所有凭证
        ok = top_type == "S"
        for p in pushed_list:
            result[str(p["sun"])] = {
                "external_sn": str(top_belnr) if ok else "",
                "posting_status": "S" if ok else "E",
                "note": "凭证创建成功" if ok else (top_msg or "SAP返回失败"),
            }
    return result


def _summarize_rows(rows, top_msg=""):
    """把一张凭证的若干 DATA_OUT 行汇总成 {external_sn, posting_status, note}"""
    belnrs = [str(r.get("BELNR") or "") for r in rows if r.get("BELNR")]
    external_sn = ",".join(dict.fromkeys(belnrs))   # 去重保序
    statuses = [str(r.get("MSG_TYP") or "").upper() for r in rows]
    ok = all(s == "S" for s in statuses) and bool(external_sn)
    fail_msgs = [str(r.get("MSG") or "") for r in rows
                 if str(r.get("MSG_TYP") or "").upper() != "S"]
    note = fail_msgs[0] if fail_msgs else ("凭证创建成功" if ok else (top_msg or "SAP返回失败"))
    return {"external_sn": external_sn, "posting_status": "S" if ok else "E", "note": note}


def writeback_transfer_log(sun, company_code, year, external_sn, posting_status, note, user_id):
    """回写 t_fi_doc_for_archiv_transfer_log: 会计凭证号/过账状态/备注/更新人/更新时间
    关联键: company_code + year + summary_unique_number
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = {
        "company_code": company_code,
        "year": year,
        "summary_unique_number": sun,
        "external_sn": external_sn,
        "posting_status": posting_status,
        "note": (note or "")[:65535],
        "update_id": user_id,
        "update_time": now_str,
    }
    cond = (f" AND `company_code`='{company_code}' AND `year`='{year}'"
            f" AND `summary_unique_number`='{sun}'")
    cols = ("external_sn", "posting_status", "note", "update_id", "update_time")
    update_db_record_by_cond(db, TRANSFER_LOG_TABLE, cond, cols, data)


# ---------- 归档凭证数据 / 配置(带缓存, 复用 send_fi_copy 逻辑) ----------
def get_fi_doc_for_archiv_head(summary_unique_number, company_code, year, archiv_doc_num):
    """查 t_fi_doc_for_archiv_head 抬头(单条, 取最新)"""
    cond = f" AND `summary_unique_number`='{summary_unique_number}'"
    if company_code:
        cond += f" AND `company_code`='{company_code}'"
    if archiv_doc_num:
        cond += f" AND `archiv_doc_num`='{archiv_doc_num}'"
    if year:
        cond += f" AND `year`='{year}'"
    sql = f"""SELECT `id`,`company_code`,`fi_sum_doc_type`,`archiv_doc_num`,`document_date`,
                     `posting_date`,`year`,`period`,`summary_unique_number`,
                     `transaction_currency`,`basic_currency`,`exchange_rate`,`header_text`,
                     `sum_dr_amount_bc`,`sum_cr_amount_bc`,`posting_status`,`verify_status`
              FROM `{ARCHIV_HEAD_TABLE}` WHERE 1=1 {cond} ORDER BY `id` DESC LIMIT 1"""
    data = db.query_sql(sql)
    return data[0] if data else {}


def find_fi_doc_for_archiv_details(summary_unique_number, company_code, year):
    """查 t_fi_doc_for_archiv_details 明细(LEFT JOIN 抬头取 posting_date/exchange_rate)"""
    cond = f" AND t1.`summary_unique_number`='{summary_unique_number}'"
    if company_code:
        cond += f" AND t1.`company_code`='{company_code}'"
    if year:
        cond += f" AND t1.`year`='{year}'"
    sql = f"""SELECT t1.`id`,t1.`year`,t1.`company_code`,t1.`summary_unique_number`,
                     t1.`dc_amount_tc`,t1.`dc_amount_bc`,t1.`debit_credit_mark`,
                     t1.`mat_doc_sn`,t1.`mat_doc_items`,t1.`cost_center`,t1.`prodosn`,
                     t1.`cost_business_object1`,t1.`wbs_elements`,t1.`summary_line`,
                     t1.`accounting_subjects`,t1.`customer_code`,t1.`vendor_code`,
                     t1.`asset_code1`,t1.`asset_code2`,t1.`asset_business_type`,
                     t1.`profit_center`,t1.`item_text`,t1.`mat_code`,t1.`trade_partner_code`,
                     t1.`payment_terms`,t1.`baseline_date`,t1.`basic_uom`,t1.`basic_qty`,
                     t1.`so_sn`,t1.`so_items`,
                     t2.`fi_sum_doc_type`,t2.`posting_date`,t2.`exchange_rate`
              FROM `{ARCHIV_DETAIL_TABLE}` AS t1
              LEFT JOIN `{ARCHIV_HEAD_TABLE}` AS t2
              ON t1.`year` = t2.`year` AND t1.`company_code` = t2.`company_code`
              AND t1.`summary_unique_number` = t2.`summary_unique_number`
              WHERE 1=1 {cond} ORDER BY t1.`id` ASC"""
    return db.query_sql(sql)


@lru_cache(maxsize=1)
def get_fi_post_erp_value_transfer():
    """ERP 字段值转换配置(带缓存)"""
    return db.query_sql("SELECT `field_name`,`before_value`,`after_value` FROM `t_fi_post_erp_value_transfer`")


def get_company_cost_element_info(company_code):
    """公司代码对应的成本要素(带缓存), 决定成本中心/订单/WBS 是否填"""
    global company_cost_element_info
    if company_code not in company_cost_element_info:
        rows = db.query_sql(
            f"SELECT `cost_element` FROM `t_os_company` LEFT JOIN `t_acd_cost_element` "
            f"USING(`cost_area`) WHERE `company_code`='{company_code}'")
        company_cost_element_info[company_code] = {r.get("cost_element"): r for r in rows} if rows else {}
    return company_cost_element_info.get(company_code, {})


# ---------- 工具 ----------
def _to_ymd(date_value):
    """日期格式化为 YYYYMMDD, 失败返回空串"""
    if not date_value:
        return ""
    if isinstance(date_value, datetime):
        return date_value.strftime("%Y%m%d")
    try:
        text = str(date_value).replace("-", "").replace("/", "").replace(":", "").strip()
        return text[:8]
    except Exception:
        return ""


# ==================== Test ====================
Text_voucher_push_payload = {
    "_payload_": {
        "sort_info": [],
        "filter_info": {},
        "group_info": [],
        "statistic_info": [],
        "page": {"page_size": 0, "page_num": 1},
        "export_excel": "false"
    },
    "data": {
        "company_code": "RACQ",
        "year": "2026",
        "period": "06",
        "task_id": 605
    }
}


@calc_time
def Text_voucher_push():
    """会计凭证推送接口 测试"""
    print("===会计凭证推送接口===")
    user_id = "testuser"
    payload = Text_voucher_push_payload.get("data") or {}

    ok, msg, params = validate_voucher_params(payload)
    if not ok:
        print(f"===会计凭证推送接口=== 参数校验失败: {msg}")
        return
    res_bus = voucher_push_core(user_id, params["company_code"], params["year"], params["period"])
    print(f"===会计凭证推送接口=== 处理结束!!! 返回: {res_bus}")
    return res_bus


if __name__ == "__main__":
    Text_voucher_push()
