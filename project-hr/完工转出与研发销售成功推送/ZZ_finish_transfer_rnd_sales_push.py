# -*- coding: UTF-8 -*-
"""
@File    : ZZ_finish_transfer_rnd_sales_push.py
@Author  : yang.zhang@dxdstech.com
@Date    : 2026/1/10 15:03
@explain : 完工转出与研发销售成功推送接口

  调用方向:   秘火->SAP
  模块名称:   会计引擎
  接口名称:   完工转出与研发销售成功推送接口
  接口说明：  月结执行中按 公司代码/年度/期间, 查询已过账的研发完工转出(RACT)、
             销售研发成本(RACD)会计凭证, 在界面展示并推送至SAP。

  与 Z_Work_Order_Input_Detail_Voucher.py 同构(查询 + 推送 两个接口)。

  业务逻辑:
    1) 查询: 按公司代码/年度/期间/单据类别(RACT/RACD) 在 t_fi_integration_relation 过滤,
       过账状态/归档凭证号/外部凭证号/详细信息 由 t_fi_doc_for_archiv_transfer_log 按公司代码+年度+汇总唯一号关联。
    2) 推送: 一个归档凭证对应多个SAP凭证, 按 archiv_doc_num+summary_unique_number 去重后逐条推送,
       SAP生成财务凭证后回写 external_sn, 刷新界面。
"""

import json
from datetime import datetime

from DbHelper import DbHelper
from libenhance import Request, Response
from logger import LoggerConfig, LogLevel
from ToolsMethods import (
    GetExportData,
    Paginator,
    ResetResponse,
    ResponseData,
    calc_time,
    create_table_alias,
    display_to_entozh,
    generate_raw_sql,
)
from utils import ItfBizError, update_db_record_by_cond
from ZZEXT_SendRequest import SendToSap


def send_sap_request(sap_send_data):
    """
    发送SAP请求
    :param sap_send_data: 包含头数据和明细数据的请求数据
    :return sap_res_data: 响应数据
    """
    global UUID

    # 调用SAP接口
    interface_code = "ACC_DOCUMENT_POST"
    interface_name = "会计凭证过账推送接口"
    UUID = sap_send_data["head"].pop("ZOAID")
    sap_send_data["head"]["ZOAID"] = ""
    sap_req_param = {
        "UUID": UUID,
        "INPUT": {
            "HEAD": sap_send_data.get("head"),
            "ITEMS": sap_send_data.get("items")
        }
    }
    print(f"===SAP请求数据===: {sap_req_param}")
    sap_resp_data = SendToSap(interface_code, interface_name, sap_req_param)
    print(f"===SAP请求返回结果===: {sap_resp_data}")
    return sap_resp_data



# ---------- 固定值(按接口需求, 集中维护) ----------
# 推送任务配置
PUSH_TASK_ID = 609
PUSH_LOG_CODE = '03003E0002'
PUSH_HELP_TEXT = '研发完工转出与研发销售成本凭证推送SAP'

# 单据类别 / 会计凭证类型: 研发完工转出=RACT, 销售研发成本=RACD
DOCUMENT_CATEGORY_LIST = ['RACT', 'RACD']
ACCOUNTING_DOCUMENT_TYPE_LIST = ['RACT', 'RACD']



# SAP 推送相关(本文件自实现, 走中间件 ACC_DOCUMENT_POST)
accounting_document_type = "EA"   # 会计凭证类型默认 EA
ARCHIV_HEAD_TABLE = "t_fi_doc_for_archiv_head"
ARCHIV_DETAIL_TABLE = "t_fi_doc_for_archiv_details"
TRANSFER_LOG_TABLE = "t_fi_doc_for_archiv_transfer_log"
UUID = ""                         # 由 send_sap_request 置为 ZOAID, 解析回写时复用

# 模块级缓存(值转换 / 成本要素 / 归档创建人)
_value_transfer_cache = None
_cost_element_cache = {}
_archive_creator_cache = {}

# 展示字段(查询 / 推送回查 复用)
DISPLAY = [
    {'field': 'company_code', 'description': '公司代码', "type": "varchar", "length": 255, "decimal": 0},
    {'field': 'year', 'description': '年度', "type": "year", "length": 4, "decimal": 0},
    {'field': 'period', 'description': '期间', "type": "varchar", "length": 2, "decimal": 0},
    {'field': 'document_category', 'description': '单据类别', "type": "varchar", "length": 255, "decimal": 0},
    {'field': 'accounting_document_type', 'description': '凭证类型', "type": "varchar", "length": 255, "decimal": 0},
    {'field': 'fi_document_number', 'description': '财务凭证编号', "type": "varchar", "length": 255, "decimal": 0},
    {'field': 'summary_unique_number', 'description': '汇总唯一号', "type": "varchar", "length": 255, "decimal": 0},
    {'field': 'archiv_doc_num', 'description': '归档凭证号', "type": "varchar", "length": 255, "decimal": 0},
    {'field': 'posting_status', 'description': '过账状态', "type": "varchar", "length": 255, "decimal": 0},
    {'field': 'external_sn', 'description': '外部凭证号', "type": "varchar", "length": 255, "decimal": 0},
    {'field': 'note', 'description': '详细信息', "type": "varchar", "length": 255, "decimal": 0},
]


# ---------- 入参校验 ----------
def _validate_params(company_code, year, period, document_category):
    """校验必填入参: company_code / year / period / document_category
    :return: (ok, msg)
    """
    missing = []
    if not company_code:
        missing.append("company_code(公司代码)")
    if not year:
        missing.append("year(年度)")
    if not period:
        missing.append("period(期间)")
    if not document_category:
        missing.append("document_category(单据类别)")
    if missing:
        return False, f"缺少必填参数: {'、'.join(missing)}"
    return True, ""


# ==================== 查询接口 ====================
def finish_transfer_rnd_sales_query():
    """完工转出与研发销售成功 查询接口

    前端两个 sheet(研发完工转出 RACT / 销售研发成本 RACD)共用本接口,
    _payload_.export_excel 为真时导出 Excel, 否则分页返回。
    """
    req = Request()
    res = Response()
    body = json.loads(req.body())
    print("===完工转出与研发销售成功 查询接口===")

    data = body.get("data") or {}
    company_code = data.get("company_code")
    year = data.get("year")
    period = data.get("period")
    document_category = data.get("document_category")

    # 入参校验, 失败带 type=E 返回前端
    ok, msg = _validate_params(company_code, year, period, document_category)
    if not ok:
        response = {"code": 500, "type": "E", "msg": msg}
        print(f"===完工转出与研发销售成功 查询接口=== 参数校验失败: {msg}")
        res.set_body(json.dumps(response))
        res.commit(True)
        return

    payload = body.get("_payload_", {})
    filter_info = payload.get("filter_info", {})
    sort_info = payload.get("sort_info", {})
    export_excel = payload.get("export_excel")

    code, msg, query_data, display = finish_transfer_rnd_sales_query_core(
        company_code, year, period, document_category)
    if code != 200:
        res.set_body(json.dumps({"code": code, "type": "E", "msg": msg}))
        res.commit(True)
        return

    if export_excel:
        stamp_suffix = datetime.now().strftime("%Y%m%d%H%M%S")
        excel_filename = f"完工转出与研发销售成功-{stamp_suffix}.xlsx"
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
                "page_size": page_size if page_size else len(query_data),  # 每页数据行数
                "page_num": page_num,  # 当前页
                "page_sum": total_pages,  # 总页数
                "data_sum": data_sum,  # 总数据行数
            },
            "rule": {
                "sort_info": sort_info,
                "filter_info": filter_info,
            },
            "display": display,
        }
        res.set_body(json.dumps(response))
        res.commit(True)


def finish_transfer_rnd_sales_query_core(company_code, year, period,
                                         document_category=DOCUMENT_CATEGORY_LIST, db=None, external_sn=False):
    """查询已过账的研发完工转出(RACT)/销售研发成本(RACD)会计凭证

    凭证来自 t_fi_integration_relation; 过账状态/归档凭证号/外部凭证号/详细信息
    来自 t_fi_doc_for_archiv_transfer_log, 按 公司代码+年度+汇总唯一号 关联。

    :param document_category: 单据类别, 字符串或列表, 默认 RACT/RACD 都查
    :param external_sn: True 时仅查 external_sn 为空(未推送)的凭证
    :return: (code, msg, data, display)
    """
    db = db or DbHelper()
    if not company_code:
        return 500, '未查询到公司代码', [], DISPLAY

    # document_category 统一成 list, 便于拼 IN
    if isinstance(document_category, str):
        document_category = [document_category]
    document_category_str = ",".join(f"'{c}'" for c in document_category)
    accounting_type_str = ",".join(f"'{c}'" for c in ACCOUNTING_DOCUMENT_TYPE_LIST)

    where_sql = f"""
    SELECT
        t1.`company_code`,
        t1.`year`,
        t1.`period`,
        t1.`document_category`,
        t1.`accounting_document_type`,
        t1.`fi_document_number`,
        t1.`summary_unique_number`,
        t2.`archiv_doc_num`,
        t2.`posting_status`,
        t2.`external_sn`,
        t2.`note`
    FROM `t_fi_integration_relation` AS t1
    LEFT JOIN `t_fi_doc_for_archiv_transfer_log` AS t2
        ON t1.`summary_unique_number` = t2.`summary_unique_number`
        AND t1.`company_code` = t2.`company_code`
        AND t1.`year` = t2.`year`
    WHERE t1.`company_code` = '{company_code}'
        AND t1.`year` = '{year}'
        AND t1.`period` = '{period}'
        AND t1.`document_category` IN ({document_category_str})
        AND t1.`accounting_document_type` IN ({accounting_type_str})
    """
    if external_sn:
        where_sql += " AND t2.`external_sn` = ''"
    print(where_sql)

    data = db.query_sql(where_sql)
    return 200, '成功', data, DISPLAY


# ==================== 推送接口 ====================
@ResetResponse(params=["company_code", "year", "period", "document_category"], excelName='完工转出与研发销售成功')
def finish_transfer_rnd_sales_push(company_code, year, period, document_category, **kwargs):
    """完工转出与研发销售成功 推送接口

    推送 external_sn 为空(未推送)的研发完工转出/销售研发成本凭证至 SAP,
    一个归档凭证只推送一次(按 archiv_doc_num+summary_unique_number 去重)。
    """
    return _push_core(company_code, year, period, document_category, filter_mode='external_sn')


def Test_finish_transfer_rnd_sales_push(company_code, year, period, document_category):
    """完工转出与研发销售成功 推送(测试入口): 只推送 posting_status='E'(过账失败) 的凭证"""
    return _push_core(company_code, year, period, document_category, filter_mode='posting_status_E')


def _push_core(company_code, year, period, document_category, filter_mode, user_id='0'):
    """推送核心

    :param filter_mode: 'external_sn'      -> 推未推送的(external_sn 为空)
                        'posting_status_E' -> 推过账失败的(posting_status='E')
    :return: ResponseData
    """
    # 入参校验, 失败带 type=E 返回前端
    ok, msg = _validate_params(company_code, year, period, document_category)
    if not ok:
        return ResponseData(500, msg, [], display=DISPLAY, type="E")

    db = DbHelper()
    if filter_mode == 'posting_status_E':
        code, msg, query_data, _ = finish_transfer_rnd_sales_query_core(
            company_code, year, period, document_category, db=db, external_sn=False)
        push_items = [item for item in query_data if item.get('posting_status') == 'E']
    else:
        code, msg, query_data, _ = finish_transfer_rnd_sales_query_core(
            company_code, year, period, document_category, db=db, external_sn=True)
        push_items = query_data


    print(msg)
    if code != 200:
        return ResponseData(code, msg, [], display=DISPLAY, type="E")

    # 查询/筛选为空 -> 无可推送数据, 带 type=E 返回前端
    if not push_items:
        _, _, data, _ = finish_transfer_rnd_sales_query_core(
            company_code, year, period, document_category, db=db, external_sn=False)
        print("无可推送数据")
        return ResponseData(200, "无可推送数据", data, display=DISPLAY, type="E")

    print(f"===完工转出与研发销售成功 推送=== filter_mode={filter_mode} 待推送条数={len(push_items)}")
    resp_code_list, fail_msg = _push_documents(user_id, company_code, push_items)

    # 回查最新状态(供前端刷新)
    _, _, data, _ = finish_transfer_rnd_sales_query_core(
        company_code, year, period, document_category, db=db, external_sn=False)

    if resp_code_list and any(c != 200 for c in resp_code_list):
        return ResponseData(206, fail_msg or '部分推送失败', data, display=DISPLAY, type="E")
    return ResponseData(200, '成功', data, display=DISPLAY, type="S")


def _push_documents(user_id, company_code, items):
    """按归档凭证(archiv_doc_num + summary_unique_number)去重后逐条推送至 SAP

    :return: (resp_code_list, fail_msg)
    """
    resp_code_list = []
    fail_msg = ''
    push_dict = {}

    for item in items:
        key = f"{item.get('archiv_doc_num')}|{item.get('summary_unique_number')}"
        if push_dict.get(key):
            continue
        push_dict[key] = item

        code, each_msg = _push_to_sap(user_id, company_code, item)
        print("push code, msg--------", code, each_msg)
        resp_code_list.append(code)
        if code != 200:
            fail_msg = each_msg
    return resp_code_list, fail_msg


def _push_to_sap(user_id, company_code, item):
    """单条归档凭证推送 SAP(本文件自实现, 走中间件 ACC_DOCUMENT_POST)

    查抬头/明细 -> 组装 head/items -> send_sap_request -> 解析 -> 回写 transfer_log。
    :return: (code, msg)  code=200 成功 / 206 失败
    """
    print("kais")
    db = DbHelper()
    archive_doc_num = item.get('archiv_doc_num') or ''
    summary_unique_number = item.get('summary_unique_number') or ''
    year = item.get('year') or ''

    try:
        head_data, detail_list, cost_element_dict, is_pass = _load_archiv_data(
            db, summary_unique_number, company_code, year, archive_doc_num)

        if is_pass:
            # 无明细(金额为0), 无需推送, 直接落库成功
            _writeback_transfer_log(db, user_id, year, company_code, summary_unique_number,
                                    external_sn="", posting_status="S", note="金额为0, 无需过账")
            return 200, ''

        sap_send_data = {
            "head": _build_sap_head(head_data),
            "items": _build_sap_items(detail_list, cost_element_dict),
        }
        sap_resp = send_sap_request(sap_send_data)
        if not sap_resp:
            raise ItfBizError("SAP接口返回空数据")

        type_txt, message_txt, resp_dto = _extract_sap_response(sap_resp, sap_send_data)
        _writeback_transfer_log(
            db, user_id, year,
            resp_dto.get("company_code") or company_code,
            resp_dto.get("summary_unique_number") or summary_unique_number,
            external_sn=resp_dto.get("external_sn", ""),
            posting_status=type_txt, note=message_txt)

        if type_txt == "S":
            return 200, ''
        _log_push_failure(company_code, archive_doc_num, message_txt, sap_send_data)
        return 206, f'归档凭证编号:{archive_doc_num} 推送至SAP失败: {message_txt}'
    except Exception as e:
        # 异常时务必把信息返回前端; 回写日志单独兜底, 避免二次抛出吞掉返回
        try:
            _writeback_transfer_log(db, user_id, year, company_code, summary_unique_number,
                                    external_sn="", posting_status="E", note=str(e))
        except Exception as log_e:
            print('失败回写transfer_log异常:', log_e)
        _log_push_failure(company_code, archive_doc_num, str(e), {})
        return 206, f'归档凭证编号:{archive_doc_num} 推送至SAP失败: {e}'


def _log_push_failure(company_code, archive_doc_num, message, payload):
    """推送失败落错误日志"""
    try:
        LoggerConfig.logToDB(PUSH_LOG_CODE, '', LogLevel.ERROR,
                             f'{PUSH_HELP_TEXT} 归档凭证{archive_doc_num}:{(message or "")[:100]}',
                             {'input': payload, 'output': ''}, company_code, company_code)
    except Exception as e:
        print('日志写入失败', e)


def _load_archiv_data(db, summary_unique_number, company_code, year, archiv_doc_num):
    """查归档凭证抬头+明细 -> 值转换 -> 取成本要素
    :return: (head_data, detail_list, cost_element_dict, is_pass)  is_pass=True 表示无明细
    """
    print("开始组装")
    head_data = _get_archiv_head(db, summary_unique_number, company_code, year, archiv_doc_num)
    if not head_data:
        raise ItfBizError("汇总凭证记录不存在")
    detail_list = _get_archiv_details(db, summary_unique_number, company_code, year)
    print("明细查询-----",detail_list)

    is_pass = not detail_list
    # 字段值转换(按 t_fi_post_erp_value_transfer 配置)
    for cfg in _get_value_transfer_data():
        fname, before, after = cfg.get("field_name"), cfg.get("before_value"), cfg.get("after_value")
        if head_data.get(fname) == before:
            head_data[fname] = after
        for j in detail_list:
            if j.get(fname) == before:
                j[fname] = after

    cost_element_dict = _get_cost_element_info(company_code)
    return head_data, detail_list, cost_element_dict, is_pass


def _build_sap_head(head_data):
    """组装 SAP 中间件(ACC_DOCUMENT_POST) 抬头"""
    fi_sum_doc_type = head_data.get('fi_sum_doc_type', '')
    creator = get_archive_creator(fi_sum_doc_type)
    if not creator:
        raise ItfBizError("未取到自动归档凭证默认创建人")
    return {
        "ZOAID": head_data.get("summary_unique_number"),       # [CHAR|100] 唯一ID
        "BUKRS": head_data.get("company_code"),                # [CHAR|4] 公司代码
        "GJAHR": head_data.get("year"),                        # [CHAR|4] 会计年度
        "BLART": head_data.get("fi_sum_doc_type", ''),         # [CHAR|2] 凭证类型
        "BLDAT": head_data.get("document_date"),               # [DATS|8] 凭证日期
        "BUDAT": head_data.get("posting_date"),                # [DATS|8] 过账日期
        "WAERS": head_data.get("transaction_currency"),        # [CHAR|5] 币种
        "KURSF": head_data.get("exchange_rate"),               # [DEC|9] 汇率
        "XBLNR": head_data.get("archiv_doc_num"),              # [CHAR|16] 参照
        "BKTXT": head_data.get("year", "") + head_data.get("period", "") + head_data.get("header_text", ""),
        # [CHAR|25] 凭证抬头文本
        "MONAT": head_data.get("period"),                      # 期间
        "USNAM": creator["archiv_creater"],                    # 创建人
        "accounting_document_type": accounting_document_type,
        "fi_sum_doc_type": head_data.get("fi_sum_doc_type", ''),
    }


def _build_sap_items(detail_list, cost_element_dict):
    """组装 SAP 中间件(ACC_DOCUMENT_POST) 明细行"""
    items = []
    for item in detail_list:
        amount_tc = float(item.get("dc_amount_tc", 0))
        amount_bc = float(item.get("dc_amount_bc", 0))
        val_ZUONR = (item.get("mat_doc_sn", "") + " " + item.get("mat_doc_items", "")) if item.get("fi_sum_doc_type") == "Z9" else ""
        KOSTL = item.get("cost_center", "")
        AUFNR = item.get("prodosn", "") or item.get("cost_business_object1", "")
        PROJK = item.get("wbs_elements", "")
        is_cost_elem = bool(cost_element_dict.get(item.get("accounting_subjects", "")))
        items.append({
            "ZOAITEM": item.get("summary_line"),
            "UMSKZ": "",
            "HKONT": item.get("accounting_subjects", ""),
            "KUNNR": item.get("customer_code", ""),
            "LIFNR": item.get("vendor_code", ""),
            "ANLN1": item.get("asset_code1", ""),
            "ANLN2": item.get("asset_code2", ""),
            "ANBWA": item.get("asset_business_type", ""),
            "XNEGP": "",
            "RSTGR": "",
            "WRBTR": str(round(amount_tc, 2)),
            "DMBTR": str(round(amount_bc, 2)),
            "FWBAS": 0,
            "KOSTL": KOSTL if is_cost_elem else "",
            "PRCTR": item.get("profit_center", ""),
            "AUFNR": AUFNR if is_cost_elem else "",
            "SGTXT": item.get("item_text", ""),
            "ZUONR": val_ZUONR,
            "MWSKZ": "",
            "MATNR": item.get("mat_code", ""),
            "VBUND": item.get("trade_partner_code", ""),
            "PROJK": PROJK if is_cost_elem else "",
            "VALUT": "",
            "ZTERM": item.get("payment_terms", ""),
            "ZFBDT": item.get("baseline_date", ""),
            "ZLSCH": "",
            "XREF1": "CB",
            "XREF2": "",
            "XREF3": "",
            "HBKID": "",
            "HKTID": "",
            "MENGE": item.get("basic_uom", 0),
            "MEINS": "" if not item.get("basic_qty", "") else item.get("basic_qty", ""),
            "KNDNR": item.get("customer_code", ""),
            "KDAUF": "",
            "KDPOS": "",
            "XMWST": "",
            "NETDT": "",
            "WBS_ELEMENT": item.get("wbs_elements", "") if is_cost_elem else "",
            "EBELN": "",
            "EBELP": "",
            "VBELN": item.get("so_sn", ""),
            "POSNR": item.get("so_items", ""),
            "KOART": "S",
            "FIPOS": "",
            "FISTL": "",
            "ZHTH": "", "ZHTHH": "", "ZFKJDH": "", "ZFKJDMC": "",
            "ZOAID_ORIGIN": "",
            "ZOAITEM_ORIGIN": "",
            "ZZFIELD01": "", "ZZFIELD02": "", "ZZFIELD03": "", "ZZFIELD04": "",
            "ZZFIELD05": "", "ZZFIELD06": "", "ZZFIELD07": "", "ZZFIELD08": "",
            "ZZFIELD09": "", "ZZFIELD10": "", "ZZFIELD11": "", "ZZFIELD12": "",
            "ZZFIELD13": "",
            "ZZFIELD14": item.get("mat_code", ""),
            "ZZFIELD15": "", "ZZFIELD16": "", "ZZFIELD17": "", "ZZFIELD18": "",
        })
    return items


def _extract_sap_response(sap_resp_data, sap_send_data):
    """解析 SAP 中间件返回 -> (type_txt, message_txt, resp_dto)"""
    sap_resp_data = sap_resp_data or {}
    sap_data = sap_resp_data.get("DATA") or {}
    sap_resp_items = sap_data.get("ITEMS") or []

    type_txt = sap_resp_data.get("TYPE", "E")
    message_txt = "凭证创建成功" if type_txt == "S" else sap_resp_data.get("MSG", "SAP接口调用失败")
    if type_txt != "S":
        type_txt = "E"

    external_sns = []
    for row in sap_resp_items:
        belnr = row.get("BELNR", "")
        if belnr:
            external_sns.append(belnr)

    resp_dto = {
        "summary_unique_number": UUID,
        "company_code": sap_data.get("BUKRS"),
        "fi_sum_doc_type": sap_data.get("BLART") or sap_send_data["head"].get("BLART", ""),
        "archiv_doc_num": sap_data.get("XBLNR") or sap_send_data["head"].get("XBLNR", ""),
        "external_sn": ",".join(external_sns),
        "posting_status": type_txt,
        "note": message_txt,
    }
    return type_txt, message_txt, resp_dto


def _writeback_transfer_log(db, user_id, year, company_code, summary_unique_number,
                            external_sn="", posting_status="E", note=""):
    """回写归档凭证传输关系表(只 UPDATE)"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = {
        "company_code": company_code,
        "year": year,
        "summary_unique_number": summary_unique_number,
        "external_sn": external_sn,
        "posting_status": posting_status,
        "update_id": user_id,
        "update_time": now,
        "note": note,
    }
    cond = (f" AND `company_code`='{company_code}' AND `year`='{year}'"
            f" AND `summary_unique_number`='{summary_unique_number}'")
    update_cols = ("external_sn", "posting_status", "update_id", "update_time", "note")
    update_db_record_by_cond(db, TRANSFER_LOG_TABLE, cond, update_cols, data)


def _get_archiv_head(db, summary_unique_number, company_code, year, archiv_doc_num):
    """查 t_fi_doc_for_archiv_head 抬头(单条)"""
    print('组装头部信息')
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
                     `posting_status`,`verify_status`
              FROM `{ARCHIV_HEAD_TABLE}` WHERE 1=1 {cond} ORDER BY `id` DESC LIMIT 1"""
    
    data = db.query_sql(sql)
    print("头部信息查询-----",data)
    return data[0] if data else {}


def _get_archiv_details(db, summary_unique_number, company_code, year):
    """查 t_fi_doc_for_archiv_details 明细(LEFT JOIN 抬头取 posting_date/exchange_rate)"""
    print("明细查询参数----",summary_unique_number, company_code, year)

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
                     t2.`posting_date`,t2.`exchange_rate`
              FROM `{ARCHIV_DETAIL_TABLE}` AS t1
              LEFT JOIN `{ARCHIV_HEAD_TABLE}` AS t2
              ON t1.`year` = t2.`year` AND t1.`company_code` = t2.`company_code`
              AND t1.`summary_unique_number` = t2.`summary_unique_number`
              WHERE 1=1 {cond} ORDER BY t1.`id` ASC"""
    return db.query_sql(sql)


def _get_value_transfer_data():
    """ERP 字段值转换配置(带缓存)"""
    global _value_transfer_cache
    if _value_transfer_cache is None:
        _value_transfer_cache = DbHelper().query_sql(
            "SELECT `field_name`,`before_value`,`after_value` FROM `t_fi_post_erp_value_transfer`")
    return _value_transfer_cache


def _get_cost_element_info(company_code):
    """公司代码对应的成本要素(带缓存), 决定成本中心/订单/WBS 是否填"""
    if company_code not in _cost_element_cache:
        rows = DbHelper().query_sql(
            f"SELECT `cost_element` FROM `t_os_company` LEFT JOIN `t_acd_cost_element` USING(`cost_area`) WHERE `company_code`='{company_code}'")
        _cost_element_cache[company_code] = {r.get("cost_element"): r for r in rows} if rows else {}
    return _cost_element_cache.get(company_code, {})


def get_archive_creator(fi_sum_doc_type):
    """归档凭证默认创建人(带缓存, 抬头 USNAM 用)"""
    if fi_sum_doc_type not in _archive_creator_cache:
        try:
            data = DbHelper().query_sql(
                f"SELECT `num_object`,`archiv_creater` FROM `t_fi_doc_for_archiv_creater_default`"
                f" WHERE `accounting_document_type`='{fi_sum_doc_type}' AND `num_object`='FISUM'")
        except Exception as e:
            print(f"查询t_fi_doc_for_archiv_creater_default失败: {e}")
            data = []
        _archive_creator_cache[fi_sum_doc_type] = data[0] if data else {}
    return _archive_creator_cache.get(fi_sum_doc_type, {})


# ==================== Test ====================
test_data = {
    "data": {
        "company_code": "RACQ",
        "year": "2026",
        "period": "06",
        "document_category": "RACD"
    }
}

if __name__ == '__main__':
    _d = test_data['data']
    re = Test_finish_transfer_rnd_sales_push(_d['company_code'], _d['year'], _d['period'], _d['document_category'])
    print(re)
