# -*- coding: UTF-8 -*-
"""
@File    : ZZ_standard_cost_update.py
@Author  : yang.zhang@dxdstech.com
@Date    : 2026/06/18
@explain : 标准成本更新

  调用方向:   秘火->SAP
  模块名称:   标准成本更新
  接口名称:   标准成本更新接口
  接口说明：  标准成本更新, 调SAP (ZBAPI_MATVAL_PRICE_CHANGE)
             将标准成本数据推送至SAP进行更新,
             并将更新结果回写至 t_sap_mmd_standard_price。

  收发方式参照 ZZ_wip_variance_adjust_posting.py:
    入口 Request().body() 取参, Response.set_body/commit 返回;
    返回体 {code, msg, data, display}, 查询支持 _payload_ 过滤/排序/分页/导出。
"""
import json
import traceback
from datetime import datetime

from DbHelper import DbHelper
from libenhance import Request, Response
from ToolsMethods import (
    GetExportData,
    Paginator,
    create_table_alias,
    display_to_entozh,
    generate_raw_sql,
)
from utils import query_db_records_by_cond, update_db_record_by_cond

# from ZZEXT_SapRFC import SAPRFC

# ---------- 固定值(按接口需求) ----------
P_RELEASE = "X"            # 需要解冻物料时, 传X
VALUATION_VIEW = "0"       # 评估视图(NUMC类型), 两种货币类型行都固定传"0"(文档示例 0, 0)
CURR_TYPES = ("10", "30")  # 10=公司代码货币, 30=集团公司记账货币; 需同时传两种

# SAP接口编码 / RFC函数名
INTERFACE_CODE = "ZBAPI_MATVAL_PRICE_CHANGE"
INTERFACE_NAME = "标准成本更新接口"

# 业务表
TABLE_NAME = "t_sap_mmd_standard_price"

db = DbHelper()



import pyrfc
from libenhance import get_cnf
from logger import LoggerConfig

usprint = LoggerConfig()


class SAPRFC:
    def __init__(self):
        # 从配置文件获取SAP连接参数
        ashost = get_cnf("rfc.ashost")
        sysnr = get_cnf("rfc.sysnr")
        client = get_cnf("rfc.client")
        user = get_cnf("rfc.user")
        passwd = get_cnf("rfc.passwd")
        lang = get_cnf("rfc.lang")  # 默认中文
        trace = get_cnf("rfc.trace")  # 默认不追踪

        try:
            self.connection = pyrfc.Connection(
                ashost=ashost,
                sysnr=sysnr,
                client=client,
                user=user,
                passwd=passwd,
                lang=lang,
                trace=trace
            )
            usprint.printInfo('SAPRFC', f"SAP连接成功: {ashost}, 系统编号: {sysnr}")
        except Exception as e:
            raise Exception(f"SAP RFC连接异常: {e}")

    def call(self, rfc_name, params=None):
        """
        调用RFC函数
        :param rfc_name: RFC函数名称
        :param params: 输入参数字典（可选）
        :return: 返回结果字典
        """
        try:
            if params:
                result = self.connection.call(rfc_name, **params)
            else:
                result = self.connection.call(rfc_name)

            usprint.printInfo('SAPRFC', f"调用 {rfc_name} 成功")
            return result

        except pyrfc.ABAPApplicationError as e:
            usprint.printInfo('SAPRFC', f"ABAP应用错误 - {rfc_name}: {e}")
            raise
        except pyrfc.CommunicationError as e:
            usprint.printInfo('SAPRFC', f"通信错误 - {rfc_name}: {e}")
            raise
        except pyrfc.LogonError as e:
            usprint.printInfo('SAPRFC', f"登录错误 - {rfc_name}: {e}")
            raise
        except Exception as e:
            usprint.printInfo('SAPRFC', f"调用 {rfc_name} 失败: {e}")
            raise

    def close(self):
        """关闭SAP连接"""
        try:
            if self.connection:
                self.connection.close()
                usprint.printInfo('SAPRFC', "SAP连接已关闭")
        except Exception as e:
            usprint.printInfo('SAPRFC', f"关闭连接异常: {e}")

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass





# ---------- 公共参数校验(posting / query 共用) ----------
def validate_standard_cost_params(data):
    """校验标准成本更新接口的公共参数(plant_code / year / period), mat_code 可选

    :param data: 请求里的 data 字典(即 body["data"])
    :return: (is_valid, message, params)
        params 成功时含 {"plant_code","year","period","mat_code"}; 失败为 {}
    """
    if not isinstance(data, dict) or not data:
        return False, "请求数据(data)为空或格式错误", {}

    plant_code = data.get("plant_code")
    year = data.get("year")
    period = data.get("period")

    plant_code = plant_code.strip() if isinstance(plant_code, str) else plant_code
    year = str(year).strip() if year is not None else ""
    period = str(period).strip() if period is not None else ""

    missing = []
    if not plant_code:
        missing.append("plant_code(工厂代码)")
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

    mat_code = data.get("mat_code")
    mat_code = mat_code.strip() if isinstance(mat_code, str) else (mat_code or "")

    params = {"plant_code": str(plant_code), "year": year, "period": period, "mat_code": str(mat_code)}
    return True, "校验通过", params


# 标准成本更新 按钮
def standard_cost_update():
    """标准成本更新接口 按钮"""
    print("===标准成本更新接口===")
    req = Request()
    res = Response()
    body = json.loads(req.body())
    print("body---", body)
    user_id = req.header("user_id")

    payload = body.get("data") or {}
    task_id = payload.get("task_id")  # 仅日志关联用, 缺省为 None

    # 公共参数校验, 失败直接返回
    ok, msg, params = validate_standard_cost_params(payload)
    if not ok:
        response = {"code": 500, "type": "E", "msg": msg}
        print(f"===标准成本更新接口=== 参数校验失败: {msg}")
        res.set_body(json.dumps(response))
        res.commit(True)
        return

    res_bus = standard_cost_update_core(
        user_id, task_id, params["year"], params["period"], params["plant_code"], params.get("mat_code")
    )
    print(f"===标准成本更新接口=== 处理结束!!! 返回: {res_bus}")
    res.set_body(json.dumps(res_bus))
    res.commit(True)


def standard_cost_update_core(user_id, task_id, year, period, plant_code, mat_code=None):
    """标准成本更新 核心逻辑(606 core)
    ZBAPI_MATVAL_PRICE_CHANGE 的 MATERIAL/VALUATIONAREA 均为标量参数, 单次只改一个物料,
    故逐条调用、回写, 最后回查最新状态。
    :return: {"code", "msg", "data", "display"}
    """
    code, msg = 200, "无可更新记录"
    body = {"data": {"year": year, "period": period, "plant_code": plant_code, "mat_code": mat_code or ""}}
    print(f"===标准成本更新 core=== user_id={user_id} task_id={task_id} "
          f"plant_code={plant_code} {year}-{period} mat_code={mat_code or ''}")

    # 查询待更新记录(posting_status != 'S')
    records = get_standard_cost_update_list(plant_code, year, period, mat_code)
    print("待更新记录--", records)

    # 暂不按 物料+工厂 分组
    # # 按 物料+工厂 分组: 同一物料的多条价格记录合并到一次调用(MATERIAL 为标量, 单次一个物料)
    # groups = {}
    # for record in records:
    #     key = (record.get("mat_code", ""), record.get("plant_code", ""))
    #     groups.setdefault(key, []).append(record)

    # 一次性推送: 所有记录合并到一次调用(PRICES 含全部价格行; MATERIAL/VALUATIONAREA 取首条, 需为同一物料)
    total = len(records)
    if total:
        try:
            sap_send_data = prepare_price_change_request(records)
            print("----------------", sap_send_data)
            sap_resp = send_price_change_request(sap_send_data)
            # 解析(整批共用一个返回结果)
            resp = extract_price_change_response(sap_resp)
            # 逐条回写
            for record in records:
                update_standard_price(record, resp, user_id)
            if str(resp.get("p_ret")) == "2":
                code, msg = 200, f"更新成功 {total} 条"
            else:
                code = 206
                msg = f"更新失败 {total} 条; {resp.get('p_msg') or 'SAP返回失败'}"
        except Exception as e:
            traceback.print_exc()
            code = 206
            msg = f"更新异常 {total} 条; {e}"
            # 异常时把整批置为失败
            fail_resp = {
                "ml_doc_num": "",
                "p_msg": str(e),
                "p_ret": "3",
            }
            for record in records:
                update_standard_price(record, fail_resp, user_id)

    # 回查最终状态(供前端刷新表格)
    data, display = standard_cost_update_query_data(body)
    return {"code": code, "msg": msg, "data": data, "display": display}


# 标准成本更新 查询接口
def standard_cost_update_query():
    """标准成本更新查询接口
    支持 _payload_ 里的 filter_info / sort_info / page / export_excel
    """
    print("===标准成本更新查询接口===")
    req = Request()
    res = Response()
    body = json.loads(req.body())
    print("body----", body)

    # 公共参数校验(plant_code/year/period), 失败直接返回
    ok, msg, _ = validate_standard_cost_params(body.get("data") or {})
    if not ok:
        response = {"code": 500, "type": "E", "msg": msg}
        print(f"===标准成本更新查询接口=== 参数校验失败: {msg}")
        res.set_body(json.dumps(response))
        res.commit(True)
        return

    payload = body.get("_payload_", {})
    filter_info = payload.get("filter_info", {})
    sort_info = payload.get("sort_info", {})
    export_excel = payload.get("export_excel")

    query_data, display = standard_cost_update_query_data(body)
    if export_excel:
        stamp_suffix = datetime.now().strftime("%Y%m%d%H%M%S")
        excel_filename = f"标准成本更新-{stamp_suffix}.xlsx"
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
        print(f"===标准成本更新查询接口=== 处理结束!!! 返回: {response}")
        res.set_body(json.dumps(response))
        res.commit(True)


# 标准成本更新 查询核心逻辑(查询接口/导出/更新回查复用)
def standard_cost_update_query_data(body):
    """查 t_sap_mmd_standard_price 标准成本明细
    :return: (query_data, display)
    """
    data_filter = body.get("data") or {}
    payload = body.get("_payload_", {})
    filter_info = payload.get("filter_info", {})
    sort_info = payload.get("sort_info", {})

    # 前置筛选: 工厂/年度/期间/物料/过账状态/标准成本编码
    prefix_filter = {}
    for field in ("plant_code", "year", "period", "mat_code", "posting_status", "std_cost_code"):
        val = data_filter.get(field)
        if val not in (None, ""):
            prefix_filter[field] = val

    columns = '''`id`,
                `company_code`,
                `plant_code`,
                `year`,
                `period`,
                `std_cost_code`,
                `calc_mode`,
                `effective_start_date`,
                `effective_end_date`,
                `posting_date`,
                `mat_code`,
                `standard_cost_bc`,
                `basic_currency`,
                `price_unit`,
                `basic_uom`,
                `posting_status`,
                `price_doc_sn`,
                `note`,
                `update_id`,
                `update_time`'''

    query_sql = f'''
            SELECT
                {columns}
            FROM
                `{TABLE_NAME}`
            WHERE 1=1
        '''

    table_alias = create_table_alias(columns)
    where_sql, sort_sql = generate_raw_sql(prefix_filter, filter_info, sort_info, table_alias)
    if not sort_sql:
        sort_sql = " ORDER BY `id` ASC"
    if where_sql:
        where_sql = where_sql.replace("WHERE ", " AND ")
        full_query_sql = query_sql + where_sql + sort_sql
    else:
        full_query_sql = query_sql + sort_sql

    full_query_sql = full_query_sql.replace("    ", " ").strip()
    print(full_query_sql)
    query_data = db.query_sql(full_query_sql)

    display = [
        {"field": "std_cost_code", "description": "标准成本编码"},
        {"field": "company_code", "description": "公司代码"},
        {"field": "plant_code", "description": "工厂代码"},
        {"field": "year", "description": "年度"},
        {"field": "period", "description": "期间"},
        {"field": "calc_mode", "description": "计算模式"},
        {"field": "effective_start_date", "description": "生效开始日期"},
        {"field": "effective_end_date", "description": "生效结束日期"},
        {"field": "posting_date", "description": "过账日期"},
        {"field": "mat_code", "description": "物料编码"},
        {"field": "standard_cost_bc", "description": "单位标准成本(本位币)"},
        {"field": "basic_currency", "description": "本位币"},
        {"field": "price_unit", "description": "价格单位"},
        {"field": "basic_uom", "description": "基本单位"},
        {"field": "posting_status", "description": "过账状态"},
        {"field": "price_doc_sn", "description": "价格更改凭证号"},
        {"field": "note", "description": "备注"},
        {"field": "update_time", "description": "更新时间"},
    ]

    return query_data, display


# ---------- SAP 价格变更 查询待更新/组装/发送/解析/回写 ----------
def get_standard_cost_update_list(plant_code, year, period, mat_code=None):
    """查询待更新的标准成本记录(posting_status != 'S')
    :return: list[dict]
    """
    cond = (
        f" AND `plant_code`='{plant_code}'"
        f" AND `year`='{year}'"
        f" AND `period`='{period}'"
        f" AND `posting_status` != 'S'"
    )
    if mat_code:
        cond += f" AND `mat_code`='{mat_code}'"
    cond += " ORDER BY `id` ASC"
    cols = (
        "`id`,`std_cost_code`,`mat_code`,`plant_code`,"
        "`standard_cost_bc`,`basic_currency`,`price_unit`"
    )
    return query_db_records_by_cond(db, TABLE_NAME, cond, cols)


def prepare_price_change_request(records):
    """组装 ZBAPI_MATVAL_PRICE_CHANGE 请求数据(单物料, 多价格行)

    MATERIAL/VALUATIONAREA 为标量参数(单次一个物料), records 须为同一物料(同 mat_code+plant_code)。
    PRICES 为价格行 list, 每条记录展开两行(货币类型 10=公司代码货币 / 30=集团记账货币),
    每行字段为标量: VALUATION_VIEW / CURR_TYPE / PRICE / CURRENCY / PRICE_UNIT。
    秘火侧仅有本位币(basic_currency)与单位标准成本(standard_cost_bc),
    故两种货币类型暂传相同的价格/货币(若集团币不同需在此扩展)。

    :param records: 同一物料的价格记录列表
    :return: dict 顶层标量字段 + PRICES 表(list, 每记录两行 10/30)
    """
    if not records:
        return {}

    first = records[0]
    prices = []
    for record in records:
        price = _parse_amount(record.get("standard_cost_bc"))
        currency = record.get("basic_currency", "") or ""
        price_unit = _parse_amount(record.get("price_unit")) or 1
        for curr_type in CURR_TYPES:  # ("10", "30")
            prices.append({
                "VALUATION_VIEW": "0",        # 评估视图(NUMC), 固定"0"
                "CURR_TYPE": curr_type,       # 10=公司代码货币, 30=集团记账货币
                "PRICE": price,               # 单位标准成本(本位币)
                "CURRENCY": currency,         # 货币码(本位币)
                "PRICE_UNIT": price_unit,     # 价格单位
            })

    return {
        "MATERIAL": first.get("mat_code", ""),         # 物料编码(标量)
        "VALUATIONAREA": first.get("plant_code", ""),  # 估价范围=工厂代码(标量)
        "P_RELEASE": P_RELEASE,                        # 需要解冻物料时传X
        "PRICES": prices,                              # 价格明细表(每记录两行 10/30)
    }


def send_price_change_request(sap_send_data):
    """发送 ZBAPI_MATVAL_PRICE_CHANGE 请求"""
    sap_resp = SAPRFC().call(INTERFACE_CODE, sap_send_data)
    print(f"===标准成本更新请求返回结果===: {sap_resp}")
    return sap_resp


def extract_price_change_response(sap_resp):
    """解析SAP返回数据

    响应字段位置:
      P_RET(2成功/3失败) / P_MSG(详情)        -> 顶层单参数
      ML_DOC_NUM(价格更改凭证号) / ML_DOC_YEAR -> 输出结构行 PRICECHANGEDOCUMENT
    :return: dict {p_ret, p_msg, ml_doc_num, ml_doc_year}
    """
    sap_resp = sap_resp or {}
    data = sap_resp.get("DATA") or {}
    price_doc = sap_resp.get("PRICECHANGEDOCUMENT") or {}   # 输出结构行

    def pick(*keys, default=""):
        for k in keys:
            for src in (sap_resp, price_doc, data):
                val = src.get(k)
                if val not in (None, ""):
                    return val
        return default

    return {
        "p_ret": str(pick("P_RET", default="3")),   # 2:成功 3:失败
        "p_msg": pick("P_MSG"),                     # 更新详情
        "ml_doc_num": pick("ML_DOC_NUM"),           # 价格更改凭证号
        "ml_doc_year": pick("ML_DOC_YEAR"),         # 库存年度
    }


def update_standard_price(record, resp, user_id):
    """回写 t_sap_mmd_standard_price: 价格更改凭证号/备注/过账状态
    posting_status: P_RET '2'->'S'(成功), 其余->'E'(失败), 与表既有约定一致
    注: ML_DOC_YEAR 仅记录不入库, 避免覆盖作为查询键的期间年度(year)
    """
    record_id = record.get("id")
    if not record_id:
        return
    cond = f" AND `id`={record_id}"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = {
        "posting_status": _map_posting_status(resp.get("p_ret", "3")),
        "price_doc_sn": resp.get("ml_doc_num", ""),
        "note": resp.get("p_msg", ""),
        "update_id": user_id,
        "update_time": now,
    }
    cols = ("posting_status", "price_doc_sn", "note", "update_id", "update_time")
    update_db_record_by_cond(db, TABLE_NAME, cond, cols, data)


def _map_posting_status(p_ret):
    """P_RET -> posting_status: '2'->'S'(成功), 其余->'E'(失败)"""
    return "S" if str(p_ret) == "2" else "E"


def _parse_amount(value):
    """金额/单位转float, 空值当0"""
    try:
        return float(value) if value not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


Text_semiproduct_deduct_push_payload = {'data': {'id': 24, 'task_code': '1780905368759', 
'step': '09-00', 'task_id': 602, 'up_task_id': 0, 
'step_name': '在制差异调整过账', 'status': '1', 'excute_user': '', 
'operator_time': '', 'create_id': 1004, 'create_time': '2026-06-18 16:01:29', 
'update_id': 1004, 'update_time': '2026-06-18 16:01:29', 'note': '', 
'order_num': 9, 'action_type': '', 'progress': '0/0', 'percent': '0%', 
'plant_code': 'RAC1', 'description': '润安模拟月结', 'year': '2026', 
'period': '06', 'cost_area': 'CRM', 'cost_version': '0', 'version_description': '核算版本', 
'task_info': [{'company_code': 'RACQ', 'plant_code': ['RAC0', 'RAC1']}], 'company_code_list': [{'value': 'RACQ', 'description': '华润润安公司', 'label': 'RACQ 华润润安公司'}], 'plant_code_list': [{'value': 'RAC0', 'description': '华润润安无价值工厂', 'label': 'RAC0 华润润安无价值工厂'}, {'value': 'RAC1', 'description': '华润润安有价值工厂', 'label': 'RAC1 华润润安有价值工厂'}], 'label': '1780905368759 润安模拟月结', 'value': '1780905368759', 'company_code': 'RACQ', 'company_code_desc': '华润润安公司', 'task_code_desc': '润安模拟月结', 'condition': {'task_code': '1780905368759', 'description': '润安模拟月结', 'year': '2026', 'period': '06', 'cost_area': 'CRM', 'cost_area_description': '润安成本管理组织', 'cost_version': '0', 'version_description': '核算版本', 'status': '1', 'task_info': [{'company_code': 'RACQ', 'plant_code': ['RAC0', 'RAC1']}], 'company_code_list': [{'value': 'RACQ', 'description': '华润润安公司', 'label': 'RACQ 华润润安公司'}], 'plant_code_list': [{'value': 'RAC0', 'description': '华润润安无价值工厂', 'label': 'RAC0 华润润安无价值工厂'}, {'value': 'RAC1', 'description': '华润润安有价值工厂', 'label': 'RAC1 华润润安有价值工厂'}], 'label': '1780905368759 润安模拟月结', 'value': '1780905368759', 'company_code': 'RACQ', 'company_code_desc': '华润润安公司', 'plant_code': 'RAC0', 'task_code_desc': '润安模拟月结'}, 'type': 'query'}}


def Text_standard_cost_update():
    """标准成本更新接口 按钮 测试"""
    user_id = "test_user"

    payload = Text_semiproduct_deduct_push_payload.get("data") or {}
    task_id = payload.get("task_id")  # 仅日志关联用, 缺省为 None

    # 公共参数校验, 失败直接返回
    ok, msg, params = validate_standard_cost_params(payload)
    if not ok:
        print(f"===标准成本更新接口=== 参数校验失败: {msg}")
        return
    res_bus = standard_cost_update_core(
        user_id, task_id, params["year"], params["period"], params["plant_code"], params.get("mat_code")
    )
    print(f"===标准成本更新接口=== 处理结束!!! 返回: {res_bus}")
    return

if __name__ == "__main__":


    Text_standard_cost_update()
