# -*- coding: UTF-8 -*-
"""
@File    : ZZ_wip_variance_adjust_posting.py
@Author  : yang.zhang@dxdstech.com
@Date    : 2026/06/16
@explain : 在制差异调整过账

  调用方向:   秘火->SAP
  模块名称:   在制差异调整
  接口名称:   在制差异调整过账接口
  接口说明：  在制差异调整过账, 调SAP MIRO(ZBAPI_INCOMINGINVOICE_CREATE)生成发票凭证,
             并将发票号/年度/备注/过账状态回写至 t_co_manufacturing_adjust。
             业务: 调整差异 借:库存科目 贷:在制品调整差异。
"""
import json
import traceback
from datetime import datetime

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
from utils import query_db_records_by_cond, update_db_record_by_cond
from ZZEXT_SapRFC import SAPRFC

db = DbHelper()


# ---------- 固定值(按接口需求, 集中维护) ----------
# SAP接口编码 / RFC函数名
INTERFACE_CODE = "ZBAPI_INCOMINGINVOICE_CREATE"
INTERFACE_NAME = "在制差异调整过账接口"

# 抬头固定值
INVOICE_IND = "X"            # 发票标识
DOC_TYPE = "RE"              # 凭证类型
COMP_CODE = "RACQ"           # 公司代码
BUKRS = COMP_CODE            # SAP请求外层公司代码(=COMP_CODE)
CURRENCY = "CNY"             # 货币码
CURRENCY_ISO = "CNY"         # ISO货币码
# DIFF_INV = "51591"           # 出票方(虚拟供应商代码), 前端未传入时先用此测试值
DIFF_INV = "0000111702"           # 出票方(虚拟供应商代码), 前端未传入时先用此测试值

HEADER_ITEM_TEXT = ""        # 抬头项目文本

# 行项目固定值
GL_ACCOUNT = "4120070003"    # 在制品差异科目
TAX_CODE = "J0"              # 税码
GL_ITEM_NO = "000001"        # GL行发票凭证项目号(固定)
MAT_ITEM_NO = "000002"       # 物料行发票凭证项目号(固定)
QUANTITY = 1                 # 物料行数量(测试先写死为1, 多条时解开)
BASE_UOM = "EA"                # 基本计量单位(可选, 物料基本单位)
BASE_UOM_ISO = "EA"            # ISO计量单位(可选)

# sap_send_data 请求格式(ZBAPI_INCOMINGINVOICE_CREATE, 结构/表 分开):
#   {"HEADERDATA": 抬头dict, "GLACCOUNTDATA": [GL行dict], "MATERIALDATA": [物料行dict]}
# 注: pyrfc 经 SAPRFC.call(rfc_name, **params) 展开, 结构传 dict, 表传 list[dict]。


# ---------- 公共参数校验(posting / query 共用) ----------
def validate_wip_variance_params(data):
    """校验在制差异调整接口的公共参数(plant_code / year / period)

    两个入口(posting 过账、query 查询)共用同一套校验:
      - plant_code: 必填, 非空字符串
      - year:       必填, 4 位数字年度(兼容 int/str)
      - period:     必填, 1-12, 统一补零为 2 位(兼容 6 / "06")

    :param data: 请求里的 data 字典(即 body["data"])
    :return: (is_valid, message, params)
        is_valid: True / False
        message : 失败时的提示; 成功为 "校验通过"
        params  : 成功时的标准化参数
                  {"plant_code": str, "year": str(4位), "period": str(2位)};
                  失败时为 {}
    """
    if not isinstance(data, dict) or not data:
        return False, "请求数据(data)为空或格式错误", {}

    plant_code = data.get("plant_code")
    year = data.get("year")
    period = data.get("period")

    plant_code = plant_code.strip() if isinstance(plant_code, str) else plant_code
    year = str(year).strip() if year is not None else ""
    period = str(period).strip() if period is not None else ""

    # 1) 必填校验
    missing = []
    if not plant_code:
        missing.append("plant_code(工厂代码)")
    if not year:
        missing.append("year(年度)")
    if not period:
        missing.append("period(期间)")
    if missing:
        return False, f"缺少必填参数: {'、'.join(missing)}", {}

    # 2) 年度: 4 位数字
    if not (year.isdigit() and len(year) == 4):
        return False, f"年度(year)应为4位数字, 当前: {year!r}", {}

    # 3) 期间: 1-12, 标准化为 2 位(与库内 period 存储格式一致)
    if not period.isdigit():
        return False, f"期间(period)必须为数字, 当前: {period!r}", {}
    period_num = int(period)
    if period_num < 1 or period_num > 12:
        return False, f"期间(period)必须在1-12之间, 当前: {period}", {}
    period = f"{period_num:02d}"

    params = {
        "plant_code": str(plant_code),
        "year": year,
        "period": period,
    }
    return True, "校验通过", params


# 推送到RFC接口: wip_variance_adjust_posting
@calc_time
def wip_variance_adjust_posting():
    """在制差异调整过账接口 按钮
    task_id 602
    """
    print("===在制差异调整过账接口===")
    req = Request()
    res = Response()
    body = json.loads(req.body())
    print("body---", body)
    user_id = req.header("user_id")

    payload = body.get("data") or {}
    task_id = payload.get("task_id") or 602

    # 公共参数校验, 失败直接返回
    ok, msg, params = validate_wip_variance_params(payload)
    if not ok:
        response = {"code": 500, "type": "E", "msg": msg}
        print(f"===在制差异调整过账接口=== 参数校验失败: {msg}")
        res.set_body(json.dumps(response))
        res.commit(True)
        return
    # 校验通过, 调推送rfc逻辑
    res_bus = wip_variance_adjust_posting_core(
        user_id, task_id, params["year"], params["period"], params["plant_code"]
    )
    print(f"===在制差异调整过账接口=== 处理结束!!! 返回: {res_bus}")
    res.set_body(json.dumps(res_bus))
    res.commit(True)


@calc_time
def wip_variance_adjust_posting_core(user_id, task_id, year, period, plant_code):
    """在制差异调整过账 核心逻辑(602 core)

    查待过账记录(posting_status != '2')逐条调 SAP MIRO 过账并回写结果,
    最后回查最新状态返回(供前端刷新表格)。

    :param user_id:    操作人ID(预留: 审计/日志)
    :param task_id:    任务ID(预留: 日志关联)
    :param year:       年度
    :param period:     期间
    :param plant_code: 工厂代码
    :return: {"code", "msg", "data", "display"}
    """
    code, msg = 200, "无可过账记录"
    body = {"data": {"year": year, "period": period, "plant_code": plant_code}}
    print(f"===在制差异调整过账 core=== user_id={user_id} task_id={task_id} "
          f"plant_code={plant_code} {year}-{period}")

    # 查询待过账记录(posting_status != '2')
    records = get_wip_variance_adjust_list(plant_code, year, period)
    print("待过账记录--", records)

    # 按 id 去重, 避免同一记录重复推送
    push_dict = {}
    unique_records = []
    for record in records:
        record_id = record.get("id")
        if record_id and not push_dict.get(record_id):
            push_dict[record_id] = record
            unique_records.append(record)

    record_cnt = len(unique_records)

    # ===== 一次性全推送: 所有待过账记录合并成一张 MIRO 发票凭证, 一次 RFC 调用 =====
    if record_cnt:
        try:
            sap_send_data = prepare_miro_batch_request(unique_records)
            # 调用SAPRFC, 推送到RFC接口
            sap_resp = send_miro_request(sap_send_data)
            # 解析SAPRFC返回结果
            resp = extract_miro_response(sap_resp)
            p_ret = str(resp.get("p_ret"))

            # 整批共用一个发票号, 逐条回写发票号/年度/备注/过账状态
            for record in unique_records:
                update_manufacturing_adjust(record, resp)

            if p_ret == "2":
                code, msg = 200, f"过账成功 {record_cnt} 条"
            else:
                code = 206
                p_msg = resp.get("p_msg") or "SAP返回失败"
                msg = f"过账失败 {record_cnt} 条; {p_msg}"
        except Exception as e:
            traceback.print_exc()
            code = 206
            msg = f"过账异常 {record_cnt} 条; {e}"
            # 异常时把整批置为失败
            fail_resp = {
                "invoice_doc_number": "",
                "fiscal_year": "",
                "p_msg": str(e),
                "p_ret": "3",
            }
            for record in unique_records:
                update_manufacturing_adjust(record, fail_resp)
    # 回查最终状态(供前端刷新表格)
    data, display = wip_variance_adjust_query_data(body)

    return {"code": code, "msg": msg, "data": data, "display": display}


# 在制差异调整 查询接口
@calc_time
def wip_variance_adjust_query():
    """在制差异调整查询接口
    支持 _payload_ 里的 filter_info / sort_info / page / export_excel; 默认按 update_time 倒序, 每页 100 条
    :return:
    {
        "code": 200,
        "msg": "成功",
        "data": [ {...}, ... ],          # 当前页数据(默认按 update_time 倒序)
        "page": { "page_size", "page_num", "page_sum", "data_sum" },
        "rule": { "sort_info", "filter_info" },
        "display": [ {"field", "description"}, ... ]
    }
    """
    print("===在制差异调整查询接口===")
    req = Request()
    res = Response()
    body = json.loads(req.body())
    print("body----", body)


    # 公共参数校验(plant_code/year/period), 失败直接返回
    ok, msg, params = validate_wip_variance_params(body.get("data") or {})
    if not ok:
        response = {"code": 500, "type": "E", "msg": msg}
        print(f"===在制差异调整查询接口=== 参数校验失败: {msg}")
        res.set_body(json.dumps(response))
        res.commit(True)
        return

    # 用标准化参数回写 data, 保证查询条件与过账一致
    # body["data"] = {**(body.get("data") or {}), **params}

    payload = body.get('_payload_', {})
    filter_info = payload.get('filter_info', {})
    sort_info = payload.get('sort_info', {})
    export_excel = payload.get('export_excel')

    query_data, display = wip_variance_adjust_query_data(body)

    if export_excel:
        stamp_suffix = datetime.now().strftime('%Y%m%d%H%M%S')
        excel_filename = f'在制差异调整-{stamp_suffix}.xlsx'
        format_data = [{'sheet1': query_data}]
        field_dict = display_to_entozh(display)
        GetExportData(format_data, excel_filename, field_dict)
    else:
        page_size = payload.get('page', {}).get('page_size') or 100   # 默认每页 100 条
        page_num = payload.get('page', {}).get('page_num', 1)
        paginator = Paginator(query_data, page_size)
        page_items = paginator.get_page(page_num)
        total_pages = paginator.total_pages
        data_sum = len(query_data)

        response = {
            "code": 200,
            "msg": "成功",
            "data": page_items,              # 当前页数据(默认按 update_time 倒序)
            "page": {
                "page_size": page_size,      # 每页数据行数
                "page_num": page_num,         # 当前页
                "page_sum": total_pages,      # 总页数
                "data_sum": data_sum          # 总数据行数
            },
            "rule": {
                "sort_info": sort_info,
                "filter_info": filter_info
            },
            "display": display
        }
        print(f"===在制差异调整查询接口=== 处理结束!!! 返回: {response}")
        res.set_body(json.dumps(response))
        res.commit(True)



# 在制差异调整 查询核心逻辑(查询接口/导出/过账回查复用)
def wip_variance_adjust_query_data(body):
    """在制差异调整 查询核心逻辑
    :param body: 请求体字典
    :return: (query_data, display)
    """
    data_filter = body.get('data') or {}
    payload = body.get('_payload_', {})
    filter_info = payload.get('filter_info', {})
    sort_info = payload.get('sort_info', {})

    # 前置筛选(任务级固定条件): 工厂/年度/期间/过账状态/产品物料编码
    prefix_filter = {}
    for field in ('plant_code', 'year', 'period', 'posting_status', 'prd_mat_code'):
        val = data_filter.get(field)
        if val not in (None, ''):
            prefix_filter[field] = val

    columns = '''`id`,
                `summary_type`,
                `summary_unique_number`,
                `summary_date`,
                `summary_line`,
                `posting_status`,
                `plant_code`,
                `year`,
                `period`,
                `prd_mat_code`,
                `wip_calc_object`,
                `prodosn`,
                `prodo_type`,
                `cost_collector`,
                `wip_comp_code`,
                `eop_wip_amount`,
                `eop_comp_wip_amount`,
                `cop_wip_amount`,
                `cop_comp_wip_amount`,
                `eop_sap_wip_amount`,
                `eop_sap_comp_wip_amount`,
                `amount_diff`,
                `comp_amount_diff`,
                `order_adjust`,
                `wip_cost_element`,
                `fi_document_number`,
                `cc_cost_center`,
                `wbs_elements`,
                `document_category`,
                `cost_version`,
                `create_id`,
                `create_time`,
                `update_id`,
                `update_time`,
                `note`'''

    query_sql = f'''
            SELECT
                {columns}
            FROM
                `t_co_manufacturing_adjust`
            WHERE 1=1
        '''

    table_alias = create_table_alias(columns)
    where_sql, sort_sql = generate_raw_sql(prefix_filter, filter_info, sort_info, table_alias)
    if not sort_sql:
        # 默认按更新时间倒序(最新过账的在前), id 倒序兜底
        sort_sql = ' ORDER BY `update_time` DESC, `id` DESC'
    if where_sql:
        where_sql = where_sql.replace('WHERE ', ' AND ')
        full_query_sql = query_sql + where_sql + sort_sql
    else:
        full_query_sql = query_sql + sort_sql

    full_query_sql = full_query_sql.replace('    ', ' ').strip()
    print(full_query_sql)
    query_data = db.query_sql(full_query_sql)

    display = [
        {"field": "summary_type", "description": "汇总类型"},
        {"field": "summary_unique_number", "description": "汇总唯一号"},
        {"field": "summary_date", "description": "汇总日期"},
        {"field": "summary_line", "description": "汇总行"},
        {"field": "plant_code", "description": "工厂代码"},
        {"field": "year", "description": "年度"},
        {"field": "period", "description": "期间"},
        {"field": "prd_mat_code", "description": "产品物料编码"},
        {"field": "wip_calc_object", "description": "在制计算对象"},
        {"field": "prodosn", "description": "生产订单"},
        {"field": "prodo_type", "description": "订单类型"},
        {"field": "cost_collector", "description": "成本收集器"},
        {"field": "wip_comp_code", "description": "在制组件代码"},
        {"field": "eop_wip_amount", "description": "期末在制金额"},
        {"field": "eop_comp_wip_amount", "description": "期末完工在制金额"},
        {"field": "cop_wip_amount", "description": "本期在制金额"},
        {"field": "cop_comp_wip_amount", "description": "本期完工在制金额"},
        {"field": "eop_sap_wip_amount", "description": "期末SAP在制金额"},
        {"field": "eop_sap_comp_wip_amount", "description": "期末SAP完工在制金额"},
        {"field": "amount_diff", "description": "金额差异"},
        {"field": "comp_amount_diff", "description": "完工金额差异"},
        {"field": "order_adjust", "description": "订单调整"},
        {"field": "wip_cost_element", "description": "在制成本要素"},
        {"field": "fi_document_number", "description": "财务凭证号"},
        {"field": "cc_cost_center", "description": "成本中心"},
        {"field": "wbs_elements", "description": "WBS元素"},
        {"field": "document_category", "description": "单据类别"},
        {"field": "cost_version", "description": "成本版本"},
        {"field": "posting_status", "description": "过账状态"},
        {"field": "note", "description": "备注"},
    ]

    return query_data, display




def get_wip_variance_adjust_list(plant_code, year, period):
    """查询待过账的在制差异调整记录(posting_status != '2')
    :return: list[dict]
    """
    cond = (
        f" AND `plant_code`='{plant_code}'"
        f" AND `year`='{year}'"
        f" AND `period`='{period}'"
        f" AND `posting_status` != '2'"
        f" ORDER BY `id` ASC"
    )

    cols = "`id`,`summary_unique_number`,`summary_line`,`summary_date`,`prd_mat_code`,`plant_code`,`year`,`amount_diff`,`posting_status`,`comp_amount_diff`"
    data = query_db_records_by_cond(db, "t_co_manufacturing_adjust", cond, cols)
    print("查询待过账的在制差异调整记录--",data)
    return data


def prepare_miro_request(record):
    """组装 SAP MIRO 请求数据(ZBAPI_INCOMINGINVOICE_CREATE)

    按 RFC 入参结构组织(结构/表 分开, 勿扁平到 DATA_IN):
      - HEADERDATA    : 抬头结构(dict)
      - GLACCOUNTDATA : GL行表(list[dict]), 在制品差异科目
      - MATERIALDATA  : 物料行表(list[dict]), 库存科目
    """
    head_fields = build_miro_header_fields(record)
    gl_fields = build_miro_glaccount_fields(record)
    mat_fields = build_miro_material_fields(record)

    sap_send_data = {
        "HEADERDATA": head_fields,
        "GLACCOUNTDATA": [gl_fields],
        "MATERIALDATA": [mat_fields],
    }
    print("组装SAP 请求数据完成---", sap_send_data)
    return sap_send_data


def prepare_miro_batch_request(records):
    """组装 批量 SAP MIRO 请求数据: 所有记录合并到一张发票凭证一次性推送

    一个 HEADERDATA(抬头取第一条记录, 批量共用) + 多个 GL 行 + 多个 物料行。
    INVOICE_DOC_ITEM 全凭证内连续唯一: 第 i 条记录 GL=2i-1, 物料=2i。
    """
    if not records:
        return {}

    # 抬头批量共用一个, 取第一条记录的汇总日期/汇总唯一号
    head_fields = build_miro_header_fields(records[0])

    glaccount_data = []
    material_data = []
    for idx, record in enumerate(records, start=1):
        gl_item_no = f"{2 * idx - 1:06d}"   # 000001, 000003, 000005 ...
        mat_item_no = f"{2 * idx:06d}"      # 000002, 000004, 000006 ...

        gl = build_miro_glaccount_fields(record)
        gl["INVOICE_DOC_ITEM"] = gl_item_no
        glaccount_data.append(gl)

        mat = build_miro_material_fields(record)
        mat["INVOICE_DOC_ITEM"] = mat_item_no
        material_data.append(mat)

    sap_send_data = {
        "HEADERDATA": head_fields,
        "GLACCOUNTDATA": glaccount_data,
        "MATERIALDATA": material_data,
    }
    print("组装SAP 批量请求数据完成---", sap_send_data)
    return sap_send_data


def build_miro_header_fields(record):
    """组装抬头字段(HEADERDATA 结构)"""
    summary_date = record.get("summary_date")
    # 凭证日期: 数据汇总日期(YYYYMMDD); 缺失则用今天
    doc_date = _to_ymd(summary_date) or datetime.now().strftime("%Y%m%d")
    pstng_date = datetime.now().strftime("%Y%m%d")  # 记账日期=系统当前日期
    summary_unique_number = record.get("summary_unique_number", "")

    return {
        "INVOICE_IND": INVOICE_IND,          # 发票标识 X
        "DOC_TYPE": DOC_TYPE,                # 凭证类型 RE
        "COMP_CODE": COMP_CODE,              # 公司代码 RACQ
        "PSTNG_DATE": pstng_date,            # 记账日期=系统当前日期
        "DOC_DATE": doc_date,                # 凭证日期=数据汇总日期
        "REF_DOC_NO": str(summary_unique_number)[:16],   # 参考号(可选, 便于追溯)
        "ITEM_TEXT": HEADER_ITEM_TEXT,       # 抬头项目文本(可选)
        "HEADER_TXT": str(summary_unique_number)[:25],   # 抬头文本(可选)
        "CURRENCY": CURRENCY,                # 货币码 CNY
        "CURRENCY_ISO": CURRENCY_ISO,        # ISO货币码 CNY
        "DIFF_INV": DIFF_INV,                # 出票方 51591
    }


def build_miro_glaccount_fields(record):
    """组装 GL行字段(在制品差异科目)
    DB_CR_IND: 差额正数->S(借), 差额负数->H(贷)
    """
    amount = _parse_amount(record.get("amount_diff"))
    db_cr_ind = "S" if amount >= 0 else "H"

    return {
        "INVOICE_DOC_ITEM": GL_ITEM_NO,      # 发票凭证项目 000001(固定)
        "GL_ACCOUNT": GL_ACCOUNT,            # 在制品差异科目 4120070003
        "ITEM_AMOUNT": amount,               # 凭证货币金额
        "DB_CR_IND": db_cr_ind,              # 借/贷标识
        "COMP_CODE": COMP_CODE,              # 公司代码 RACQ(必填)
        "TAX_CODE": TAX_CODE,                # 税码 J0
    }


def build_miro_material_fields(record):
    """组装 物料行字段(库存科目)
    ITEM_AMOUNT 取 comp_amount_diff(完工金额差异, 与 GL 行的 amount_diff 区分);
    DB_CR_IND: 差额正数->H(贷), 差额负数->S(借)   (与GL相反, 保持借贷平衡)
    """
    print("record--------", record)
    print("comp_amount_diff--------", record.get("comp_amount_diff"))
    amount = _parse_amount(record.get("comp_amount_diff"))
    db_cr_ind = "H" if amount >= 0 else "S"

    return {
        "INVOICE_DOC_ITEM": MAT_ITEM_NO,     # 发票凭证项目 000002(固定)
        "MATERIAL": record.get("prd_mat_code", ""),  # 物料号
        "VAL_AREA": record.get("plant_code", ""),    # 估价范围=工厂代码
        "DB_CR_IND": db_cr_ind,              # 借/贷标识(与GL相反)
        "ITEM_AMOUNT": amount,               # 凭证货币金额(=完工金额差异)
        "QUANTITY": str(QUANTITY),                # 数量 1
        "BASE_UOM": BASE_UOM,                # 基本计量单位(可选, 物料基本单位)
        "BASE_UOM_ISO": BASE_UOM_ISO,        # ISO计量单位(可选)
        "TAX_CODE": TAX_CODE,                # 税码 J0
    }


def send_miro_request(sap_send_data):
    """发送SAP MIRO请求 """
    # 现在直接调用ZZEXT_SapRFC 推送到RFC系统
    sap_resp = SAPRFC().call(INTERFACE_CODE, sap_send_data)
    print(f"===MIRO请求返回结果===: {sap_resp}")
    return sap_resp


def extract_miro_response(sap_resp):
    """解析SAP返回数据

    :return: dict {type, message, invoice_doc_number, fiscal_year, p_ret, p_msg}
    """
    print("MIRO请求返回结果---",sap_resp)
    sap_resp = sap_resp or {}
    data = sap_resp.get("DATA") or {}

    # 业务字段: 优先顶层, 缺失回退 DATA
    def pick(*keys, default=""):
        for k in keys:
            val = sap_resp.get(k)
            if val is None or val == "":
                val = data.get(k)
            if val is not None and val != "":
                return val
        return default

    p_ret = str(pick("P_RET", default="3"))
    return {
        "type": sap_resp.get("TYPE", "E"),
        "message": sap_resp.get("MSG") or data.get("MSG") or "",
        "invoice_doc_number": pick("INVOICEDOCNUMBER"),
        "fiscal_year": pick("FISCALYEAR"),
        "p_ret": p_ret,        # 2:成功 3:失败
        "p_msg": pick("P_MSG"),
    }

def update_manufacturing_adjust(record, resp):
    """回写 t_co_manufacturing_adjust: 发票号/年度/备注/过账状态/更新时间"""
    record_id = record.get("id")
    if not record_id:
        return
    cond = f" AND `id`={record_id}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if resp.get("p_ret") == "2":
        data = {
            "fi_document_number": resp.get("invoice_doc_number", ""),
            "year": resp.get("fiscal_year", ""),
            "note": resp.get("p_msg", ""),
            "posting_status": resp.get("p_ret"),
            "update_time": now_str,
        }
        cols = ("fi_document_number", "year", "note", "posting_status", "update_time")

    # 失败的话sap年度会返回0000，失败就不跟跟新年份了
    else:
        data = {
            "fi_document_number": resp.get("invoice_doc_number", ""),
            "note": resp.get("p_msg", ""),
            "posting_status": resp.get("p_ret", "3"),
            "update_time": now_str,
        }
        cols = ("fi_document_number", "note", "posting_status", "update_time")

    print("回写数据库数据---",data)
    update_db_record_by_cond(db, "t_co_manufacturing_adjust", cond, cols, data)


def _parse_amount(value):
    """金额转float, 空值当0"""
    try:
        return float(value) if value not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def _to_ymd(date_value):
    """把日期值格式化为 YYYYMMDD, 失败返回空串"""
    if not date_value:

        return ""
    # 兼容 datetime / 字符串
    if isinstance(date_value, datetime):
        return date_value.strftime("%Y%m%d")
    try:
        text = str(date_value).replace("-", "").replace("/", "").replace(":", "").strip()
        return text[:8]
    except Exception:
        return ""



Text_semiproduct_deduct_push_payload = {'data': {'id': 24, 'task_code': '1780905368759', 
'step': '09-00', 'task_id': 602, 'up_task_id': 0, 
'step_name': '在制差异调整过账', 'status': '1', 'excute_user': '', 
'operator_time': '', 'create_id': 1004, 'create_time': '2026-06-18 16:01:29', 
'update_id': 1004, 'update_time': '2026-06-18 16:01:29', 'note': '', 
'order_num': 9, 'action_type': '', 'progress': '0/0', 'percent': '0%', 
'plant_code': 'RAC1', 'description': '润安模拟月结', 'year': '2026', 
'period': '06', 'cost_area': 'CRM', 'cost_version': '0', 'version_description': '核算版本', 

'task_info': [{'company_code': 'RACQ', 'plant_code': ['RAC0', 'RAC1']}], 'company_code_list': [{'value': 'RACQ', 'description': '华润润安公司', 'label': 'RACQ 华润润安公司'}], 'plant_code_list': [{'value': 'RAC0', 'description': '华润润安无价值工厂', 'label': 'RAC0 华润润安无价值工厂'}, {'value': 'RAC1', 'description': '华润润安有价值工厂', 'label': 'RAC1 华润润安有价值工厂'}], 'label': '1780905368759 润安模拟月结', 'value': '1780905368759', 'company_code': 'RACQ', 'company_code_desc': '华润润安公司', 'task_code_desc': '润安模拟月结', 'condition': {'task_code': '1780905368759', 'description': '润安模拟月结', 'year': '2026', 'period': '06', 'cost_area': 'CRM', 'cost_area_description': '润安成本管理组织', 'cost_version': '0', 'version_description': '核算版本', 'status': '1', 'task_info': [{'company_code': 'RACQ', 'plant_code': ['RAC0', 'RAC1']}], 'company_code_list': [{'value': 'RACQ', 'description': '华润润安公司', 'label': 'RACQ 华润润安公司'}], 'plant_code_list': [{'value': 'RAC0', 'description': '华润润安无价值工厂', 'label': 'RAC0 华润润安无价值工厂'}, {'value': 'RAC1', 'description': '华润润安有价值工厂', 'label': 'RAC1 华润润安有价值工厂'}], 'label': '1780905368759 润安模拟月结', 'value': '1780905368759', 'company_code': 'RACQ', 'company_code_desc': '华润润安公司', 'plant_code': 'RAC0', 'task_code_desc': '润安模拟月结'}, 'type': 'query'}}


@calc_time
def Text_semiproduct_deduct_push():
    """半成品扣料推送接口 测试
    task_id 603
    """
    user_id = 'testuser'
    payload = Text_semiproduct_deduct_push_payload.get("data") or {}
    task_id = payload.get("task_id") or 603

    # 公共参数校验, 失败直接返回
    ok, msg, params = validate_wip_variance_params(payload)
    # if not ok:
    #     print(f"===半成品扣料推送接口=== 参数校验失败: {msg}")
    #     return
    res_bus = wip_variance_adjust_posting_core(
        user_id, task_id, params["year"], params["period"], params["plant_code"]
    )
    print(f"===半成品扣料推送接口=== 处理结束!!! 返回: {res_bus}")
    return res_bus


if __name__ == "__main__":
    Text_semiproduct_deduct_push()

