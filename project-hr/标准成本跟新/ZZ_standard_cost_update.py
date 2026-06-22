# -*- coding: UTF-8 -*-
"""
@File    : ZZEXT_standard_cost_update.py
@Author  : yang.zhang@dxdstech.com
@Date    : 2026/06/18
@explain : 标准成本更新

  调用方向:   秘火->SAP
  模块名称:   标准成本更新
  接口名称:   标准成本更新接口
  接口说明：  标准成本更新, 调SAP (ZBAPI_MATVAL_PRICE_CHANGE)
             将标准成本数据推送至SAP进行更新,
             并将更新结果回写至 t_sap_mmd_standard_price。
"""
import traceback
from datetime import datetime

from DbHelper import DbHelper
from utils import query_db_records_by_cond, update_db_record_by_cond
from ZZEXT_SapRFC import SAPRFC

# ---------- 固定值(按接口需求) ----------
P_RELEASE = "X"            # 需要解冻物料时, 传X
VALUATION_VIEW = 0         # 评估视图, 固定传0(每种货币类型行都传0)
CURR_TYPES = ("10", "30")  # 10=公司代码货币, 30=集团公司记账货币; 需同时传两种

# SAP接口编码 / RFC函数名
INTERFACE_CODE = "ZBAPI_MATVAL_PRICE_CHANGE"
INTERFACE_NAME = "标准成本更新接口"

# 业务表
TABLE_NAME = "t_sap_mmd_standard_price"

db = DbHelper()


def standard_cost_update(payload, user_id):
    """入口函数: 标准成本更新(按 工厂/年度/期间 批量)

    流程: 查询待更新记录 -> 组装ZBAPI请求 -> 调SAP -> 解析 -> 回写业务表
    入参:
    :param user_id: 操作人ID
    :param payload: 请求参数, data 内含 plant_code/year/period, 可选 mat_code
    :return:
    {
        "type": "S/E",     # S-成功 E-失败
        "message": "string",
    }
    """
    print(f"===标准成本更新接口=== 处理开始... 参数: {payload}")

    data = payload.get("data") or payload

    # 参数校验
    err = check_params(data)
    if err:
        return {"type": "E", "message": err}

    plant_code = data.get("plant_code", "")
    year = data.get("year", "")
    period = data.get("period", "")

    # 查询待更新记录(未成功即推)
    records = get_standard_cost_update_list(plant_code, year, period, data.get("mat_code"))
    if not records:
        return {"type": "S", "message": "无可更新记录"}

    success_cnt = 0
    fail_msgs = []
    for record in records:
        mat_code = record.get("mat_code", "")
        try:
            # 组装并发送
            sap_send_data = prepare_price_change_request(record)
            sap_resp = send_price_change_request(sap_send_data)
            # 解析
            resp = extract_price_change_response(sap_resp)
            # 回写
            update_standard_price(record, resp, user_id)

            if resp.get("p_ret") == "2":
                success_cnt += 1
            else:
                fail_msgs.append(f"{mat_code}: {resp.get('p_msg') or 'SAP返回失败'}")
        except Exception as e:
            traceback.print_exc()
            fail_msgs.append(f"{mat_code}: {e}")
            # 异常时把该条置为失败
            update_standard_price(record, {
                "ml_doc_num": "",
                "p_msg": str(e),
                "p_ret": "3",
            }, user_id)

    total = len(records)
    if not fail_msgs:
        response = {"type": "S", "message": f"更新成功 {success_cnt} 条"}
    else:
        response = {
            "type": "E",
            "message": f"共 {total} 条, 成功 {success_cnt} 条, 失败 {len(fail_msgs)} 条; "
                       f"失败明细: {'; '.join(fail_msgs)}",
        }
    print(f"===标准成本更新接口=== 处理结束!!! 返回: {response}")
    return response


def standard_cost_update_for_api(payload, user_id):
    """postman调试入口(脚本调用使用 standard_cost_update)

    :param payload: 字典
    {
        "guid": "string",
        "data": {
            "plant_code": "string",   # 工厂代码
            "year": "string",         # 年度
            "period": "string",       # 期间
            "mat_code": "string"      # 物料编码(可选, 用于只更新指定物料)
        }
    }
    :param user_id: 用户ID
    :return: {"guid":"", "type":"S/E", "message":""}
    """
    data = payload.get("data")
    if not data or not isinstance(data, dict):
        return {"type": "E", "message": "请求数据为空"}

    response = standard_cost_update(payload, user_id)
    response["guid"] = payload.get("guid", "")
    return response


def standard_cost_update_query(payload, user_id):
    """标准成本更新 查询接口

    入参:
    :param payload: 请求参数, data 内含 plant_code/year/period,
                    可选 mat_code/posting_status/std_cost_code
    :return:
    {
        "type": "S/E",     # S-成功 E-失败
        "message": "string",
        "data": [ {...}, ... ],
    }
    """
    print(f"===标准成本更新查询接口=== 参数: {payload}")
    data = payload.get("data") or payload
    plant_code = data.get("plant_code", "")
    year = data.get("year", "")
    period = data.get("period", "")
    mat_code = data.get("mat_code", "")
    posting_status = data.get("posting_status", "")
    std_cost_code = data.get("std_cost_code", "")

    cond = ""
    if plant_code:
        cond += f" AND `plant_code`='{plant_code}'"
    if year:
        cond += f" AND `year`='{year}'"
    if period:
        cond += f" AND `period`='{period}'"
    if mat_code:
        cond += f" AND `mat_code`='{mat_code}'"
    if posting_status:
        cond += f" AND `posting_status`='{posting_status}'"
    if std_cost_code:
        cond += f" AND `std_cost_code`='{std_cost_code}'"
    if not cond:
        return {"type": "E", "message": "请至少指定查询条件(plant_code/year/period)", "data": []}
    cond += " ORDER BY `id` ASC"

    # 显式指定列名(禁止使用*), 字段加反引号
    cols = (
        "`id`,`company_code`,`plant_code`,`year`,`period`,`std_cost_code`,"
        "`calc_mode`,`effective_start_date`,`effective_end_date`,`posting_date`,"
        "`mat_code`,`standard_cost_bc`,`basic_currency`,`price_unit`,`basic_uom`,"
        "`posting_status`,`price_doc_sn`,`note`,`update_id`,`update_time`"
    )

    try:
        records = query_db_records_by_cond(db, TABLE_NAME, cond, cols)
        response = {"type": "S", "message": f"查询成功, 共 {len(records)} 条", "data": records}
    except Exception as e:
        traceback.print_exc()
        response = {"type": "E", "message": str(e), "data": []}
    print(f"===标准成本更新查询接口=== 处理结束!!! 返回: {response}")
    return response


def check_params(data):
    """
    检查参数是否完整
    :param data: 请求参数(data体)
    :return: 错误信息(为空表示校验通过)
    """
    plant_code = data.get("plant_code", "")
    year = data.get("year", "")
    period = data.get("period", "")
    if not plant_code:
        return "缺少工厂代码(plant_code)"
    if not year:
        return "缺少年度(year)"
    if not period:
        return "缺少期间(period)"
    return ""


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
    # 显式指定列名(禁止使用*), 字段加反引号
    cols = (
        "`id`,`std_cost_code`,`mat_code`,`plant_code`,"
        "`standard_cost_bc`,`basic_currency`,`price_unit`"
    )
    return query_db_records_by_cond(db, TABLE_NAME, cond, cols)


def prepare_price_change_request(record):
    """组装 ZBAPI_MATVAL_PRICE_CHANGE 请求数据

    价格明细(PRICECHANGE)需同时传两种货币类型:
      10=公司代码货币, 30=集团公司记账货币
    秘火侧仅有本位币(basic_currency)与单位标准成本(standard_cost_bc),
    故两种货币类型行暂传相同的价格/货币(若集团币不同需在此扩展)。
    :return: dict 顶层扁平结构 + PRICECHANGE 表(两行)
    """
    price = _parse_amount(record.get("standard_cost_bc"))
    currency = record.get("basic_currency", "") or ""
    price_unit = _parse_amount(record.get("price_unit")) or 1

    price_change_rows = []
    for curr_type in CURR_TYPES:
        price_change_rows.append({
            "VALUATION_VIEW": VALUATION_VIEW,        # 评估视图 固定0
            "CURR_TYPE": curr_type,                  # 10/30
            "PRICE": price,                          # 单位标准成本(本位币)
            "CURRENCY": currency,                    # 货币码(本位币)
            "CURRENCY_ISO": currency,                # ISO货币码(本位币即ISO)
            "PRICE_UNIT": price_unit,                # 价格单位
        })

    return {
        "MATERIAL": record.get("mat_code", ""),         # 物料编码
        "VALUATIONAREA": record.get("plant_code", ""),  # 估价范围=工厂代码
        "P_RELEASE": P_RELEASE,                         # 需要解冻物料时传X
        "PRICECHANGE": price_change_rows,               # 价格变更明细(两行)
    }


def send_price_change_request(sap_send_data):
    """发送 ZBAPI_MATVAL_PRICE_CHANGE 请求"""
    sap_resp = SAPRFC().call(INTERFACE_CODE, sap_send_data)
    print(f"===标准成本更新请求返回结果===: {sap_resp}")
    return sap_resp


def extract_price_change_response(sap_resp):
    """解析SAP返回数据

    响应字段(顶层, 缺失回退 DATA):
      P_RET(2成功/3失败) P_MSG(详情) ML_DOC_NUM(价格更改凭证号) ML_DOC_YEAR(库存年度)
    :return: dict {p_ret, p_msg, ml_doc_num, ml_doc_year}
    """
    sap_resp = sap_resp or {}
    data = sap_resp.get("DATA") or {}

    def pick(*keys, default=""):
        for k in keys:
            val = sap_resp.get(k)
            if val is None or val == "":
                val = data.get(k)
            if val is not None and val != "":
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
