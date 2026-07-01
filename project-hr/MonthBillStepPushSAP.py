# -*- coding: UTF-8 -*-
"""
@File    : MonthBillStepPushSAP.py
@Author  : ying.chen@dxdstech.com
@Date    : 2026/1/8 16:42
@explain : 月结步骤
    7. 月结步骤4-1 -辅材费用调整过账推送至外部系统         513
    9. 月结步骤*5-1-外购外协实际成本过账                  501
    10. 月结步骤*5-3 外购外协存货实际成本过账推送外部系统    503
    12. 月结步骤*8-1-其他成本分摊过账推送外部系统          504
    14. 月结步骤*9-1-费用分配分摊过账推送外部系统          505
    18. 月结步骤12-1 -实际作业成本过账推送外部系统         506
    24. 月结步骤*17-1 -期末在制过账推送外部系统           507
    26. 月结步骤*18-1 -完工成本过账推送外部系统           509
    29. 月结步骤*18-1  完工成本过账                      508
    32. 月结步骤*23-2 非外购外协存货实际成本过账推送外部系统  511
    35. 月结步骤*23-1 非外购外协存货实际成本过账            510
    40. 月结步骤*27  制造费用成本中心检查                  527
"""

import functools
import json
import time
import traceback
from datetime import date, datetime
from decimal import Decimal, getcontext

from dateutil.relativedelta import relativedelta
from DbHelper import DbHelper
from libenhance import Request, Response, exec_operator
from logger import LoggerConfig, LogLevel
from ToolsMethods import (
    GetExportData,
    Paginator,
    calc_time,
    create_table_alias,
    display_to_entozh,
    filter_data,
    generate_raw_sql,
    sort_data,
)
from ZZEXT_MonthBillStepPushSAP import (
    ZZEXTActualCostPostPushSAP,
    ZZEXTAuxMatCostPostPushSAP,
    ZZEXTCompletionCostPostPushSAP,
    ZZEXTCostAllocPostPushSAP,
    ZZEXTNotOutsourceInventorPushSAP,
    ZZEXTOtherCostAllocPushSAP,
    ZZEXTOutsourceInventoryPushSAP,
    ZZEXTPeriodProcessPostPushSAP,
)

db_helper = DbHelper()
all_cost_center_group, all_cost_center_range = {}, {}
# 设置Decimal的精度
getcontext().prec = 20
keep_precise = Decimal('0.00000001')
log = LoggerConfig("MonthBillStepPushSAP", isStream=True)

outsource_types = {
    '01': 'cp',
    '02': 'cr',
    '03': 'wp',
}


class SuperEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(o, date):
            return o.strftime("%Y-%m-%d")
        elif isinstance(o, Decimal):
            return float(o.quantize(keep_precise))
        else:
            return json.JSONEncoder.default(self, o)


def aux_mat_cost_post_push_query(body, external_sn=True):
    """辅材费用调整过账推送至外部系统 查询"""
    prefix_filter = body.get('data') or {}
    prefix_filter, task_code, step = get_month_task_info(prefix_filter)
    payload = body.get('_payload_', {})
    filter_info = payload.get('filter_info', {})
    sort_info = payload.get('sort_info', {})

    company_code = ''
    if 'plant_code' in prefix_filter:
        plant_code = prefix_filter.pop('plant_code')
        company_code = get_company_by_plant(plant_code)

    db_helper = DbHelper()
    columns = '''fr.`id`,
                fr.`company_code`,
                fr.`year`,
                fr.`period`,
                fr.`associated_doc_type`,
                fr.`business_doc_sn`,
                fr.`fi_document_number`,
                fr.`summary_unique_number`,
                fr.`posting_date`,
                ft.`posting_status`,
                ft.`archiv_doc_num`,
                ft.`external_sn`,
                ft.`note` '''

    where_condition = ''
    if company_code and isinstance(company_code, str):
        where_condition = f" fr.`company_code` = '{company_code}' AND "

    query_sql = f'''
            SELECT
                {columns}
            FROM
                `t_fi_integration_relation` fr
            LEFT JOIN `t_fi_doc_for_archiv_transfer_log` ft ON ft.`company_code` = fr.`company_code` 
                AND ft.`year` = fr.`year` AND ft.`summary_unique_number` = fr.`summary_unique_number` 
            WHERE
                {where_condition} fr.`document_category` = 'MDOC' AND fr.`associated_doc_type` IN ('WP', 'MM') 
        '''

    re_columns = '''fr.`id`,
                fr.`company_code`,
                fr.`year`,
                fr.`period`,
                fr.`associated_doc_type`,
                fr.`business_doc_sn`,
                fr.`fi_document_number`,
                fr.`summary_unique_number`,
                fr.`posting_date`,
                ft.`posting_status`,
                ft.`archiv_doc_num`,
                ft.`external_sn`,
                ft.`note` '''

    re_query_sql = f'''
        ) UNION (
            SELECT
                {re_columns}
            FROM
                `t_fi_integration_relation` fr
            LEFT JOIN `t_fi_doc_for_archiv_transfer_log` ft ON ft.`company_code` = fr.`company_code` 
                AND ft.`year` = fr.`year` AND ft.`summary_unique_number` = fr.`summary_unique_number` 
            LEFT JOIN `t_fi_voucher_head` fh ON fh.`company_code` = fr.`company_code` and fh.`year` = fr.`year` and fr.`fi_document_number` = fh.`fi_document_number` and fh.`period` = fr.`period`
            WHERE
                {where_condition} fr.`document_category` = 'MDOC' AND fr.`associated_doc_type` IN ('WP', 'MM') AND fh.`reversal_document` != ''
        '''

    table_alias = create_table_alias(columns)
    where_sql, sort_sql = generate_raw_sql(prefix_filter, filter_info, sort_info, table_alias)
    if not external_sn:
        query_sql += " AND ft.`external_sn` = '' "
        if where_sql:
            where_sql = where_sql.replace('WHERE ', ' AND ')
            full_query_sql = query_sql + where_sql + sort_sql
        else:
            full_query_sql = query_sql + sort_sql
    else:
        query_sql += " AND fr.`fi_document_number` != '' "
        if where_sql:
            where_sql = where_sql.replace('WHERE ', ' AND ')
            full_query_sql = '( ' + query_sql + where_sql + re_query_sql + where_sql + ' ) ' + sort_sql
        else:
            full_query_sql = query_sql + sort_sql

    full_query_sql = full_query_sql.strip()
    print(full_query_sql)
    query_data = db_helper.query_sql(full_query_sql)

    display = [
        {"field": "company_code", "description": "公司代码"},
        {"field": "year", "description": "年度"},
        {"field": "period", "description": "期间"},
        {"field": "associated_doc_type", "description": "物料凭证类型"},
        {"field": "business_doc_sn", "description": "物料凭证编号"},
        {"field": "fi_document_number", "description": "财务凭证编号"},
        {"field": "archiv_doc_num", "description": "归档凭证号"},
        {"field": "posting_status", "description": "外部系统过账状态"},
        {"field": "external_sn", "description": "外部系统会计凭证号"},
        {"field": "note", "description": "状态信息"}
    ]

    return query_data, display


def AuxMatCostPostPushQuery():
    """辅材费用调整过账推送至外部系统 查询"""
    req = Request()
    res = Response()
    body = json.loads(req.body())
    payload = body.get('_payload_', {})
    filter_info = payload.get('filter_info', {})
    sort_info = payload.get('sort_info', {})
    export_excel = payload.get('export_excel')

    query_data, display = aux_mat_cost_post_push_query(body)
    if export_excel:
        timestamp = datetime.now()
        stamp_suffix = timestamp.strftime('%Y%m%d%H%M%S')
        excel_filename = f'辅材费用调整过账推送至外部系统-{stamp_suffix}.xlsx'
        format_data = [{'sheet1': query_data}]
        field_dict = display_to_entozh(display)
        GetExportData(format_data, excel_filename, field_dict)
    else:
        page_size = payload.get('page', {}).get('page_size', 0)
        page_num = payload.get('page', {}).get('page_num', 1)
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
                "data_sum": data_sum  # 总数据行数
            },
            "rule": {
                "sort_info": sort_info,
                "filter_info": filter_info
            },
            "display": display
        }

        res.set_body(json.dumps(response))
        res.commit(True)


@calc_time
def AuxMatCostPostPushSAP():
    """
    辅材费用调整过账推送至外部系统 按钮
    task_id 513
    """
    req = Request()
    res = Response()
    body = json.loads(req.body())
    user_id = req.header("user_id")
    prefix_filter = body.get('data') or {}
    plant_code = prefix_filter.get('plant_code')
    task_id = prefix_filter.get('task_id') or 513
    year = prefix_filter.get('year')
    period = prefix_filter.get('period')
    res_bus = AuxMatCostPostPushSAPCore(user_id, task_id, year, period, plant_code)
    res.set_body(json.dumps(res_bus))
    res.commit(True)


def AuxMatCostPostPushSAPCore(user_id, task_id, year, period, plant_code):
    """"513 core"""
    code, msg = 200, ''
    body = {"data": {"year": year, "period": period, "plant_code": plant_code}}
    start_time = time.time()
    query_data, _ = aux_mat_cost_post_push_query(body)
    print("aux_mat_cost_post_push_query1 end time:", time.time() - start_time)
    resp_code_list = []
    if query_data:
        for_start_time = time.time()
        push_dict = {}
        for item in query_data:
            if push_dict.get(f"{item.get('archiv_doc_num')}|{item.get('summary_unique_number')}"):
                continue
            else:
                push_dict[f"{item.get('archiv_doc_num')}|{item.get('summary_unique_number')}"] = item

            external_sn = item.get('external_sn') or ''
            if not external_sn:
                code, each_msg = ZZEXTAuxMatCostPostPushSAP(user_id, task_id, plant_code, item)
                resp_code_list.append(code)
                if code != 200:
                    msg = each_msg
        print("for end time:", time.time() - for_start_time)

    start_time = time.time()
    data, display = aux_mat_cost_post_push_query(body, external_sn=True)
    print("aux_mat_cost_post_push_query2 end time:", time.time() - start_time)
    update_flag = True
    if data:
        for item in data:
            posting_status = item.get('posting_status', '')
            posting_status = str(posting_status).strip()
            posting_status = posting_status.upper()
            if posting_status != 'S':
                print(item)
                update_flag = False
                break
    if update_flag:
        code, msg = 200, '成功'
    elif any(code != 200 for code in resp_code_list):
        code = 206
    else:
        code, msg = 200, '成功'
    return {"code": code, "msg": msg, "data": data, "display": display}


def get_month_task_info(data):
    task_code, step = '', ''
    if 'task_code' in data:
        task_code = data.pop('task_code')
    if 'step' in data:
        step = data.pop('step')
    valid_fields = ['year', 'period', 'plant_code']
    filter_condition = {field: data.get(field) for field in valid_fields}
    return filter_condition, task_code, step


def outsource_actual_post_query(body):
    """外购外协存货实际成本过账 查询"""
    prefix_filter = body.get('data') or {}
    prefix_filter, task_code, step = get_month_task_info(prefix_filter)
    post_type = body.get('post_type') or ''
    plant_code = body.get('plant_code', '') or prefix_filter.get('plant_code', '') or ''
    year = body.get('year', '') or prefix_filter.get('year', '') or ''
    period = body.get('period', '') or prefix_filter.get('period', '') or ''
    if post_type and isinstance(post_type, str):
        push_type_list = [post_type]
    else:
        push_type_list = ['01', '02']

    db_helper = DbHelper()
    cp_list, cr_list, cp_display, cr_display = [], [], [], []
    query_data = []
    display = [
        {"field": "ml_cal_type", "description": "存货计算类型"},
        {"field": "posting_type", "description": "过账类别"},
        {"field": "company_code", "description": "公司代码"},
        {"field": "company_description", "description": "公司描述"},
        {"field": "plant_code", "description": "工厂"},
        {"field": "plant_description", "description": "工厂名称"},
        {"field": "year", "description": "年度"},
        {"field": "period", "description": "期间"},
        {"field": "posting_status", "description": "过账状态"},
        {"field": "reversal_status", "description": "重置状态"},
        {"field": "fi_document_number", "description": "财务凭证编码"},
        {"field": "reversal_document", "description": "重置凭证编号"},
    ]

    for post_type in push_type_list:
        if post_type in ['01', '02']:
            columns = '''   t1.`id`,
                            CASE t1.`ml_cal_type` WHEN '01' THEN '01-外购外协' WHEN '02' THEN '02-非外购外协' ELSE t1.`ml_cal_type` END AS `ml_cal_type`,
                            CASE t1.`posting_type` WHEN '01' THEN '01-周期价格还原' WHEN '02' THEN '02-消耗重估过账' ELSE t1.`posting_type` END AS `posting_type`,
                            t1.`company_code`,
                            t3.`company_description`,
                            t1.`plant_code`,
                            t2.`plant_description`,
                            t1.`year`,
                            t1.`period`,
                            t1.`posting_status`,
                            t1.`reversal_status`,
                            t1.`fi_document_number`,
                            t1.`reversal_document` '''

            query_sql = f'''
                        SELECT
                            {columns}
                        FROM
                            `t_fi_actual_cost_log` AS t1
                        LEFT JOIN `t_os_plant` AS t2 ON t1.`plant_code` = t2.`plant_code`
                        LEFT JOIN `t_os_company` AS t3 ON t1.`company_code` = t3.`company_code`
                        WHERE
                          `ml_cal_type` = '01' AND `posting_type` = '{post_type}' 
                    '''

            if plant_code:
                query_sql += f" AND t1.`plant_code` = {repr(plant_code)} AND t1.`year` = {repr(year)} AND t1.`period` = {repr(period)} "

            table_alias = create_table_alias(columns)
            where_sql, sort_sql = generate_raw_sql(prefix_filter, {}, {}, table_alias)

            if not sort_sql:
                sort_sql = " ORDER BY `id` DESC LIMIT 1"
            if where_sql:
                where_sql = where_sql.replace('WHERE ', ' AND ')
                full_query_sql = query_sql + where_sql + sort_sql
            else:
                full_query_sql = query_sql + sort_sql
            full_query_sql = full_query_sql.replace('    ', ' ')
            print(full_query_sql)
            query_data = db_helper.query_sql(full_query_sql)
            if not query_data:
                plant_code = body.get('plant_code', '') or prefix_filter.get('plant_code', '') or ''
                posting_type = ''
                if post_type == '01':
                    posting_type = '01-周期价格还原'
                elif post_type == '02':
                    posting_type = '02-消耗重估过账'
                query_data = [
                    {
                        "id": 1,
                        "ml_cal_type": "01-外购外协",
                        "posting_type": posting_type,
                        "company_code": get_company_by_plant(plant_code),
                        "company_description": get_full_name_by_company_code(get_company_by_plant(plant_code)),
                        "plant_code": prefix_filter.get('plant_code'),
                        "plant_description": get_full_name_by_plant_code(plant_code),
                        "year": prefix_filter.get('year'),
                        "period": prefix_filter.get('period'),
                        "posting_status": "",
                        "reversal_status": "",
                        "fi_document_number": "",
                        "reversal_document": ""
                    }
                ]

        if post_type == '01':
            cp_list = query_data
            cp_display = display
        elif post_type == '02':
            cr_list = query_data
            cr_display = display

    res_data = {
        'cp': cp_list,
        'cr': cr_list,
    }

    total_display = {
        'cp': cp_display,
        'cr': cr_display,
    }

    return res_data, total_display


def OutsourceActualPostQuery():
    """外购外协实际成本过账"""
    req = Request()
    res = Response()
    body = json.loads(req.body())
    data, display = outsource_actual_post_query(body)

    res.set_body(json.dumps({"code": 200, "msg": '成功', "data": data, "display": display}))
    res.commit(True)


def OutsourceActualPostAccounting():
    """
        外购外协实际成本过账 过账按钮
        01 周期还原过账：cycle_accounting
        02 消耗重估过账：consume_accounting
        task_id 501
    """
    req = Request()
    res = Response()
    body = json.loads(req.body())
    payload = body.get('data') or {}
    post_type = body.get('post_type') or ''
    # 调用合并后的业务核心逻辑
    res_bus = OutsourceActualPostAccountingCore(payload.get('year'), payload.get('period'), payload.get('plant_code'),
                                                post_type)
    code = res_bus.get("code")
    msg = res_bus.get("msg")
    if 'post_type' in body:
        body.pop('post_type')
    total_data, total_display = outsource_actual_post_query(body)
    query_key = outsource_types.get(post_type) or ''
    data = total_data.get(query_key) or []
    for unique_key, query_data in total_data.items():
        if query_data:
            for item in query_data:
                posting_status = item.get('posting_status') or ''
                if posting_status.upper() != 'S':
                    print('posting_status', posting_status)
                    break
    display = total_display.get(query_key) or []
    res.set_body(json.dumps({"code": code, "msg": msg, "data": data, "display": display}))
    res.commit(True)


def OutsourceActualPostAccountingCore(year, period, plant_code, post_type=None):
    """
    外购外协实际成本过账核心逻辑 (501 执行)
    合并优化版
    """
    code, msg = 200, '成功'
    log_code = '030030013'
    post_types = [post_type] if post_type else ["01", "02"]
    type_map = {
        "01": ("01", "cycle_accounting", "周期还原过账"),
        "02": ("02", "consume_accounting", "消耗重估过账")
    }
    if not post_type:
        req_param = {
            'year': year,
            'period': period,
            'plant_code': plant_code,
        }
        res_data, _ = outsource_actual_post_query(req_param)
        cp_data = res_data.get('cp', [])
        cr_data = res_data.get('cr', [])
        # 过账的时候，如果已经生成财务凭证编码且没有被冲销，不需要过账
        if cp_data and (cp_data[0].get('fi_document_number') and not cp_data[0].get('reversal_document')):
            post_types.remove("01")

        if cr_data and (cr_data[0].get('fi_document_number') and not cr_data[0].get('reversal_document')):
            post_types.remove("02")

    print("post_types", post_types)

    db = DbHelper()
    for p_type in post_types:
        if p_type not in type_map:
            continue
        ml_type, op_name, label = type_map[p_type]
        output = {}
        in_data = {
            "ml_cal_type": "01",
            "posting_type": p_type,
            "plant_code": plant_code or '',
            "year": year or '',
            "period": period,
        }

        if op_name == 'cycle_accounting':
            if db.is_table_exist(f"t_co_actual_cost_calc_{plant_code}_{year}{period}"):
                if not db.query_sql(f"select `id` from `t_co_actual_cost_calc_{plant_code}_{year}{period}` limit 1"):
                    print("无数据")
                    continue
            else:
                print("无表")
                continue
        else:
            if db.is_table_exist(f"t_co_actual_cost_consume_{plant_code}_{year}{period}"):
                if not db.query_sql(f"select `id` from `t_co_actual_cost_consume_{plant_code}_{year}{period}` limit 1"):
                    print("无数据")
                    continue
            else:
                print("无表")
                continue

        log.printInfo(op_name, in_data)
        exec_operator(op_name, json.dumps(in_data), output)
        log.printInfo(op_name, output)
        resp_str = output.get('data') or ''

        if resp_str:
            resp = json.loads(resp_str, strict=False)
            curr_code = resp.get('code') or 0
            if curr_code != 200:
                # 记录失败信息并终止后续循环
                code = 206
                msg = resp.get('msg') or '执行失败'
                detail = {'input': in_data, 'output': resp}
                LoggerConfig.logToDB(log_code, '', LogLevel.ERROR, f'{label} {op_name}:{msg}', detail, plant_code)
                break
            else:
                code, msg = 200, '成功'
    return {"code": code, "msg": msg}


def OutsourceActualPostReversal():
    """
        外购外协实际成本过账 重置过账按钮
        01 周期还原冲销：cycle_reversal
        02 消耗重估冲销：consume_reversal
    """
    req = Request()
    res = Response()
    body = json.loads(req.body())
    payload = body.get('data') or {}
    post_type = body.get('post_type') or ''
    # 调用合并后的业务核心逻辑
    res_bus = OutsourceActualPostReversalCore(payload.get('year'), payload.get('period'), payload.get('plant_code'),
                                              post_type)
    code = res_bus.get("code")
    msg = res_bus.get("msg")
    if 'post_type' in body:
        body.pop('post_type')
    total_data, total_display = outsource_actual_post_query(body)
    query_key = outsource_types.get(post_type) or ''
    data = total_data.get(query_key) or []
    for unique_key, query_data in total_data.items():
        if query_data:
            for item in query_data:
                reversal_status = item.get('reversal_status') or ''
                if reversal_status.upper() != 'S':
                    print('reversal_status :', reversal_status)
                    break
    display = total_display.get(query_key) or []
    res.set_body(json.dumps({"code": code, "msg": msg, "data": data, "display": display}))
    res.commit(True)


def OutsourceActualPostReversalCore(year, period, plant_code, post_type=None):
    """
    外购外协实际成本过账重置逻辑 (501 重置)
    合并优化版：支持 01, 02 单独冲销或全部连跑
    """
    code, msg = 200, '成功'
    log_code = '030030013'
    post_types = [post_type] if post_type else ["01", "02"]
    type_map = {
        "01": ("01", "cycle_reversal", "周期还原冲销"),
        "02": ("01", "consume_reversal", "消耗重估冲销")
    }

    if not post_type:
        req_param = {
            'year': year,
            'period': period,
            'plant_code': plant_code,
        }
        res_data, _ = outsource_actual_post_query(req_param)
        cp_data = res_data.get('cp', [])
        cr_data = res_data.get('cr', [])
        # 重置的时候，如果没有生成财务凭证编码，不需要重置
        if cp_data and (not cp_data[0].get('fi_document_number') or cp_data[0].get('reversal_document')):
            post_types.remove("01")

        if cr_data and (not cr_data[0].get('fi_document_number') or cr_data[0].get('reversal_document')):
            post_types.remove("02")

    db = DbHelper()
    for p_type in post_types:
        if p_type not in type_map:
            continue
        ml_type, op_name, label = type_map[p_type]
        output = {}
        in_data = {
            "ml_cal_type": "01",
            "posting_type": p_type,
            "plant_code": plant_code or '',
            "year": year or '',
            "period": period,
        }

        if not db.query_sql(f"select `id` from `t_fi_actual_cost_log` where `year` = '{year}' and `period` = '{period}' and `plant_code` = '{plant_code}' limit 1"):
            continue

        log.printInfo(op_name, in_data)
        exec_operator(op_name, json.dumps(in_data), output)
        log.printInfo(op_name, output)
        resp_str = output.get('data') or ''
        if resp_str:
            resp = json.loads(resp_str, strict=False)
            curr_code = resp.get('code') or 0
            if curr_code != 200:
                code = 206
                # 清洗错误信息中的单引号，防止前端显示异常或日志存储问题
                msg = (resp.get('msg') or '重置失败').strip().replace("'", "")
                detail = {'input': in_data, 'output': resp}
                LoggerConfig.logToDB(log_code, '', LogLevel.ERROR, f'{label} {op_name}:{msg}', detail, plant_code)
                break
            else:
                code, msg = 200, '成功'
    return {"code": code, "msg": msg}


def OutsourceActualPostMenu():
    """外购外协实际成本过账 筛选、过滤、下载"""
    req = Request()
    res = Response()
    body = json.loads(req.body())
    payload = body.get('_payload_', {})
    filter_info = payload.get('filter_info', {})
    sort_info = payload.get('sort_info', {})
    export_excel = payload.get('export_excel')
    post_type = body.get('post_type')

    total_data, total_display = outsource_actual_post_query(body)
    query_key = outsource_types.get(post_type) or ''
    query_data = total_data.get(query_key) or []
    display = total_display.get(query_key) or []

    if query_data:
        if filter_info:
            query_data = filter_data(query_data, filter_info)  # 筛选过滤

        if sort_info:
            query_data = sort_data(query_data, sort_info)

    if export_excel:
        timestamp = datetime.now()
        stamp_suffix = timestamp.strftime('%Y%m%d%H%M%S')
        excel_filename = f'外购外协存货实际成本过账-{stamp_suffix}.xlsx'
        format_data = [{'sheet1': query_data}]
        field_dict = display_to_entozh(display)
        GetExportData(format_data, excel_filename, field_dict)
    else:
        res.set_body(json.dumps({"code": 200, "msg": "成功", "data": query_data, "display": display}))
        res.commit(True)


def outsource_inventory_query(body, external_sn=True):
    """外购外协存货实际成本过账推送外部系统查询"""
    prefix_filter = body.get('data') or {}
    prefix_filter, task_code, step = get_month_task_info(prefix_filter)
    post_type = body.get('post_type')
    if post_type and isinstance(post_type, str):
        push_type_list = [post_type]
    else:
        push_type_list = ['01', '02', '03']

    db_helper = DbHelper()
    cp_list, cr_list, wp_list = [], [], []
    cp_display, cr_display, wp_display = [], [], []
    query_data = []
    display = [
        {"field": "ml_cal_type", "description": "存货计算类型"},
        {"field": "posting_type", "description": "过账类别"},
        {"field": "company_code", "description": "公司代码"},
        {"field": "plant_code", "description": "工厂"},
        {"field": "year", "description": "年度"},
        {"field": "period", "description": "期间"},
        {"field": "fi_document_number", "description": "财务凭证编号"},
        {"field": "archiv_doc_num", "description": "归档凭证号"},
        {"field": "external_sn", "description": "外部系统会计凭证号"}
    ]

    for post_type in push_type_list:
        if post_type in ['01', '02']:
            columns = '''   fc.`id`,
                            CASE fc.`ml_cal_type` WHEN '01' THEN '01-外购外协' ELSE fc.`ml_cal_type` END AS `ml_cal_type`,
                            CASE fc.`posting_type` WHEN '01' THEN '01-周期价格还原' WHEN '02' THEN '02-消耗重估过账' ELSE fc.`posting_type` END AS `posting_type`,
                            fc.`company_code`,
                            fc.`plant_code`,
                            fc.`year`,
                            fc.`period`,
                            fc.`fi_document_number`,
                            fr.`summary_unique_number`,
                            ft.`archiv_doc_num`,
                            ft.`external_sn` '''

            re_columns = '''fc.`id`,
                            CASE fc.`ml_cal_type` WHEN '01' THEN '01-外购外协' ELSE fc.`ml_cal_type` END AS `ml_cal_type`,
                            CASE fc.`posting_type` WHEN '01' THEN '01-周期价格还原' WHEN '02' THEN '02-消耗重估过账' ELSE fc.`posting_type` END AS `posting_type`,
                            fc.`company_code`,
                            fc.`plant_code`,
                            fc.`year`,
                            fc.`period`,
                            fc.`reversal_document` AS `fi_document_number`,
                            fr.`summary_unique_number`,
                            ft.`archiv_doc_num`,
                            ft.`external_sn` '''

            query_sql = f'''
                        (SELECT
                            {columns}
                        FROM
                            `t_fi_actual_cost_log` fc
                            LEFT JOIN `t_fi_integration_relation` fr ON fc.`company_code` = fr.`company_code` 
                            AND fc.`year` = fr.`year` AND fc.`period` = fr.`period` AND fc.`fi_document_number` = fr.`fi_document_number`
                            LEFT JOIN `t_fi_doc_for_archiv_transfer_log` ft ON ft.`company_code` = fr.`company_code` 
                            AND ft.`year` = fr.`year` AND ft.`summary_unique_number` = fr.`summary_unique_number` 
                        WHERE
                          fc.`ml_cal_type` = '01' AND fc.`posting_type` = '{post_type}' AND fc.`fi_document_number` != '' 
                        '''
            re_query_sql = f'''
                    ) UNION (
                        SELECT
                            {re_columns}
                        FROM
                            `t_fi_actual_cost_log` fc
                            LEFT JOIN `t_fi_integration_relation` fr ON fc.`company_code` = fr.`company_code` 
                            AND fc.`year` = fr.`year` AND fc.`period` = fr.`period` AND fc.`reversal_document` = fr.`fi_document_number`
                            LEFT JOIN `t_fi_doc_for_archiv_transfer_log` ft ON ft.`company_code` = fr.`company_code` 
                            AND ft.`year` = fr.`year` AND ft.`summary_unique_number` = fr.`summary_unique_number` 
                        WHERE
                          fc.`ml_cal_type` = '01' AND fc.`posting_type` = '{post_type}' AND fc.`reversal_document` != '' 
                    '''
            if not external_sn:
                query_sql += " AND ft.`external_sn` = '' "
                re_query_sql += " AND ft.`external_sn` = '' "

            table_alias = create_table_alias(columns)
            where_sql, sort_sql = generate_raw_sql(prefix_filter, {}, {}, table_alias)

            if not sort_sql:
                sort_sql = ' ORDER BY `fi_document_number` '
            if where_sql:
                where_sql = where_sql.replace('WHERE ', ' AND ')
                full_query_sql = query_sql + where_sql + re_query_sql + where_sql + ' ) ' + sort_sql
            else:
                full_query_sql = query_sql + ' ) ' + sort_sql
            full_query_sql = full_query_sql.replace('    ', ' ')
            print(full_query_sql)
            query_data = db_helper.query_sql(full_query_sql)

        if post_type == '01':
            cp_list = query_data
            cp_display = display
        elif post_type == '02':
            cr_list = query_data
            cr_display = display
        elif post_type == '03':
            wp_list, wp_display = period_process_post_query(body, associated_doc_type="'WIP2', 'TZ01'", external_sn=True)
            wp_display.insert(0, {"field": "doc_type", "description": "单据类别"})
            # if wp_list:
            #     for item in wp_list:
            #         item['doc_type'] = 'WIP2-在制辅材'

    res_data = {
        'cp': cp_list,
        'cr': cr_list,
        'wp': wp_list,
    }

    total_display = {
        'cp': cp_display,
        'cr': cr_display,
        'wp': wp_display
    }

    return res_data, total_display


def OutsourceInventoryQuery():
    """外购外协存货实际成本过账推送外部系统查询"""
    req = Request()
    res = Response()
    body = json.loads(req.body())
    data, display = outsource_inventory_query(body, external_sn=True)

    res.set_body(json.dumps({"code": 200, "msg": '成功', "data": data, "display": display}))
    res.commit(True)


def OutsourceInventoryPushSAP():
    """外购外协存货实际成本过账推送外部系统 按钮"""
    req = Request()
    res = Response()
    body = json.loads(req.body())
    user_id = req.header("user_id")
    post_type = body.get('post_type')
    prefix_filter = body.get('data') or {}
    plant_code = prefix_filter.get('plant_code') or ''
    task_id = prefix_filter.get('task_id') or 503
    year = prefix_filter.get('year')
    period = prefix_filter.get('period')
    res_bus = OutsourceInventoryPushSAPCore(user_id, task_id, year, period, plant_code, post_type)
    code = res_bus.get("code")
    msg = res_bus.get("msg")
    if 'post_type' in body:
        body.pop('post_type')
    total_data, total_display = outsource_inventory_query(body, external_sn=True)
    query_key = outsource_types.get(post_type) or ''
    data = total_data.get(query_key) or []
    display = total_display.get(query_key) or []
    for unique_key, query_data in total_data.items():
        if query_data:
            for item in query_data:
                external_sn = item.get('external_sn') or ''
                if not external_sn:
                    print(item)
                    break
    if data:
        for item in data:
            external_sn = item.get('external_sn') or ''
            if not external_sn:
                print(item)
                break
    res.set_body(json.dumps({"code": code, "msg": msg, "data": data, "display": display}))
    res.commit(True)


def OutsourceInventoryPushSAPCore(user_id, task_id, year, period, plant_code, post_type=None):
    """ 503 core"""
    code, msg = 200, ''
    body = {"data": {"year": year, "period": period, "plant_code": plant_code}, "post_type": post_type}
    res_data, _ = outsource_inventory_query(body, external_sn=False)
    post_type_list = [post_type] if post_type else ["01", "02", "03"]
    for post_type in post_type_list:
        query_key = outsource_types.get(post_type) or ''
        query_data = res_data.get(query_key) or []
        resp_code_list = []
        if query_data:
            push_dict = {}
            for item in query_data:
                if push_dict.get(f"{item.get('archiv_doc_num')}|{item.get('summary_unique_number')}"):
                    continue
                else:
                    push_dict[f"{item.get('archiv_doc_num')}|{item.get('summary_unique_number')}"] = item
                external_sn = item.get('external_sn') or ''
                if not external_sn:
                    code, each_msg = ZZEXTOutsourceInventoryPushSAP(user_id, task_id, plant_code, item)
                    resp_code_list.append(code)
                    if code != 200:
                        msg = each_msg
                else:
                    print("已经存在 external_sn:", external_sn)
    return {"code": code, "msg": msg}


def OutsourceInventoryMenu():
    """外购外协存货实际成本过账 筛选、过滤、下载"""
    req = Request()
    res = Response()
    body = json.loads(req.body())
    payload = body.get('_payload_', {})
    filter_info = payload.get('filter_info', {})
    sort_info = payload.get('sort_info', {})
    export_excel = payload.get('export_excel')
    post_type = body.get('post_type')

    total_data, total_display = outsource_inventory_query(body, external_sn=True)
    query_key = outsource_types.get(post_type) or ''
    query_data = total_data.get(query_key) or []
    display = total_display.get(query_key) or []

    if query_data:
        if filter_info:
            query_data = filter_data(query_data, filter_info)  # 筛选过滤

        if sort_info:
            query_data = sort_data(query_data, sort_info)

    if export_excel:
        timestamp = datetime.now()
        stamp_suffix = timestamp.strftime('%Y%m%d%H%M%S')
        excel_filename = f'外购外协存货实际成本过账-{stamp_suffix}.xlsx'
        format_data = [{'sheet1': query_data}]
        field_dict = display_to_entozh(display)
        GetExportData(format_data, excel_filename, field_dict)
    else:
        res.set_body(json.dumps({"code": 200, "msg": "成功", "data": query_data, "display": display}))
        res.commit(True)


def other_cost_alloc_query(body, external_sn=True):
    """其他成本分摊过账 查询"""
    prefix_filter = body.get('data') or {}
    prefix_filter, task_code, step = get_month_task_info(prefix_filter)
    payload = body.get('_payload_', {})
    filter_info = payload.get('filter_info', {})
    sort_info = payload.get('sort_info', {})

    company_code = ''
    if 'plant_code' in prefix_filter:
        plant_code = prefix_filter.pop('plant_code')
        company_code = get_company_by_plant(plant_code)

    db_helper = DbHelper()
    columns = '''   fr.`id`,
                    fr.`company_code`,
                    fr.`year`,
                    fr.`period`,
                    fr.`document_category`,
                    fr.`business_doc_sn`,
                    fr.`fi_document_number`,
                    fr.`summary_unique_number`,
                    ft.`archiv_doc_num`,
                    ft.`posting_status`,
                    ft.`external_sn` '''

    query_sql = f'''
                SELECT
                    {columns}
                FROM
                    `t_fi_integration_relation` fr 
                    LEFT JOIN `t_fi_doc_for_archiv_transfer_log` ft ON ft.`company_code` = fr.`company_code` 
                    AND ft.`year` = fr.`year` AND ft.`summary_unique_number` = fr.`summary_unique_number` 
                    LEFT JOIN `t_fi_voucher_head` fh ON fr.`fi_document_number` = fh.`fi_document_number` and fh.`year` = fr.`year` and fh.`period` = fr.`period`
                WHERE
                  fr.`document_category` = 'COTR' AND fr.`associated_doc_type` IN ('COE', 'CAS')
            '''

    re_columns = '''fr.`id`,
                    fr.`company_code`,
                    fr.`year`,
                    fr.`period`,
                    fr.`document_category`,
                    fr.`business_doc_sn`,
                    fr.`fi_document_number`,
                    fr.`summary_unique_number`,
                    ft.`archiv_doc_num`,
                    ft.`posting_status`,
                    ft.`external_sn` '''

    re_query_sql = f'''
        ) UNION (
                SELECT
                    {re_columns}
                FROM
                    `t_fi_integration_relation` fr 
                    LEFT JOIN `t_fi_doc_for_archiv_transfer_log` ft ON ft.`company_code` = fr.`company_code` 
                    AND ft.`year` = fr.`year` AND ft.`summary_unique_number` = fr.`summary_unique_number` 
                    LEFT JOIN `t_fi_voucher_head` fh ON fr.`fi_document_number` = fh.`fi_document_number` and fh.`year` = fr.`year` and fh.`period` = fr.`period`
                WHERE
                  fr.`document_category` = 'COTR' AND fr.`associated_doc_type` IN ('COE', 'CAS') AND fh.`reversal_document` != ''
            '''

    if company_code and isinstance(company_code, str):
        query_sql += f" AND fr.`company_code` = '{company_code}' "
        re_query_sql += f" AND fr.`company_code` = '{company_code}' "

    table_alias = create_table_alias(columns)
    where_sql, sort_sql = generate_raw_sql(prefix_filter, filter_info, sort_info, table_alias)
    if not external_sn:
        query_sql += " AND ft.`external_sn` = '' "
        if where_sql:
            where_sql = where_sql.replace('WHERE ', ' AND ')
            full_query_sql = query_sql + where_sql + sort_sql
        else:
            full_query_sql = query_sql + sort_sql
    else:
        query_sql += " AND fr.`fi_document_number` != '' "
        if where_sql:
            where_sql = where_sql.replace('WHERE ', ' AND ')
            full_query_sql = '( ' + query_sql + where_sql + re_query_sql + where_sql + ' ) ' + sort_sql
        else:
            full_query_sql = query_sql + sort_sql

    full_query_sql = full_query_sql.strip()
    print(full_query_sql)
    query_data = db_helper.query_sql(full_query_sql)

    display = [
        {"field": "company_code", "description": "公司代码"},
        {"field": "year", "description": "年度"},
        {"field": "period", "description": "期间"},
        {"field": "document_category", "description": "CO凭证类型"},
        {"field": "business_doc_sn", "description": "CO凭证编号"},
        {"field": "fi_document_number", "description": "财务凭证编号"},
        {"field": "archiv_doc_num", "description": "归档凭证号"},
        {"field": "posting_status", "description": "外部系统过账状态"},
        {"field": "external_sn", "description": "外部系统会计凭证号"}
    ]

    return query_data, display


def OtherCostAllocQuery():
    """其他成本分摊过账推送外部系统"""
    req = Request()
    res = Response()
    body = json.loads(req.body())

    payload = body.get('_payload_', {})
    filter_info = payload.get('filter_info', {})
    sort_info = payload.get('sort_info', {})
    export_excel = payload.get('export_excel')

    query_data, display = other_cost_alloc_query(body, external_sn=True)
    if export_excel:
        timestamp = datetime.now()
        stamp_suffix = timestamp.strftime('%Y%m%d%H%M%S')
        excel_filename = f'其他成本分摊过账推送外部系统-{stamp_suffix}.xlsx'
        format_data = [{'sheet1': query_data}]
        field_dict = display_to_entozh(display)
        GetExportData(format_data, excel_filename, field_dict)
    else:
        page_size = payload.get('page', {}).get('page_size', 0)
        page_num = payload.get('page', {}).get('page_num', 1)
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
                "data_sum": data_sum  # 总数据行数
            },
            "rule": {
                "sort_info": sort_info,
                "filter_info": filter_info
            },
            "display": display
        }

        res.set_body(json.dumps(response))
        res.commit(True)


def OtherCostAllocPushSAP():
    """
    其他成本分摊过账推送外部系统 按钮
    task_id 504
    """
    req = Request()
    res = Response()
    body = json.loads(req.body())
    user_id = req.header("user_id")
    prefix_filter = body.get('data') or {}
    plant_code = prefix_filter.get('plant_code') or ''
    task_id = prefix_filter.get('task_id') or 504
    year = prefix_filter.get('year')
    period = prefix_filter.get('period')
    res_bus = OtherCostAllocPushSAPCore(user_id, task_id, year, period, plant_code)
    res.set_body(json.dumps(res_bus))
    res.commit(True)


def OtherCostAllocPushSAPCore(user_id, task_id, year, period, plant_code):
    """ 504 core"""
    body = {"data": {"year": year, "period": period, "plant_code": plant_code}}
    code, msg = 200, ''
    query_data, display = other_cost_alloc_query(body, external_sn=False)
    resp_code_list = []
    if query_data:
        push_dict = {}
        for item in query_data:
            if push_dict.get(f"{item.get('archiv_doc_num')}|{item.get('summary_unique_number')}"):
                continue
            else:
                push_dict[f"{item.get('archiv_doc_num')}|{item.get('summary_unique_number')}"] = item

            external_sn = item.get('external_sn') or ''
            if not external_sn:
                code, each_msg = ZZEXTOtherCostAllocPushSAP(user_id, task_id, plant_code, item)
                resp_code_list.append(code)
                if code != 200:
                    msg = each_msg
    data, display = other_cost_alloc_query(body, external_sn=True)
    update_flag = True
    if data:
        for item in data:
            external_sn = item.get('external_sn') or ''
            if not external_sn:
                print(item)
                update_flag = False
                break
    if update_flag:
        code, msg = 200, '成功'
    elif any(code != 200 for code in resp_code_list):
        code = 206
    else:
        code, msg = 200, '成功'
    return {"code": code, "msg": msg, "data": data, "display": display}


def cost_alloc_post_query(body, external_sn=True):
    """费用分配分摊过账推送 查询"""
    prefix_filter = body.get('data') or {}
    prefix_filter, task_code, step = get_month_task_info(prefix_filter)
    payload = body.get('_payload_', {})
    filter_info = payload.get('filter_info', {})
    sort_info = payload.get('sort_info', {})

    company_code = ''
    if 'plant_code' in prefix_filter:
        plant_code = prefix_filter.pop('plant_code')
        company_code = get_company_by_plant(plant_code)

    db_helper = DbHelper()
    columns = '''   fr.`id`,
                    fr.`company_code`,
                    fr.`year`,
                    fr.`period`,
                    fr.`document_category`,
                    fr.`business_doc_sn`,
                    fr.`fi_document_number`,
                    fr.`summary_unique_number`,
                    ft.`archiv_doc_num`,
                    ft.`posting_status`,
                    ft.`external_sn`,
                    ft.`note`
                    '''

    query_sql = f'''
            SELECT
                {columns}
            FROM
                `t_fi_integration_relation` fr 
                LEFT JOIN `t_fi_doc_for_archiv_transfer_log` ft ON ft.`company_code` = fr.`company_code` 
                AND ft.`year` = fr.`year` AND ft.`summary_unique_number` = fr.`summary_unique_number` 
                LEFT JOIN `t_fi_voucher_head` fh on fr.`fi_document_number` = fh.`fi_document_number` and fh.`year` = fr.`year` and fh.`period` = fr.`period`
            WHERE
              fr.`document_category` = 'EMDC' AND fr.`associated_doc_type` = 'COT' 
        '''

    re_columns = '''fr.`id`,
                    fr.`company_code`,
                    fr.`year`,
                    fr.`period`,
                    fr.`document_category`,
                    fr.`business_doc_sn`,
                    fr.`fi_document_number`,
                    fr.`summary_unique_number`,
                    ft.`archiv_doc_num`,
                    ft.`posting_status`,
                    ft.`external_sn`,
                    ft.`note` '''

    re_query_sql = f'''
        ) UNION (
            SELECT
                {re_columns}
            FROM
                `t_fi_integration_relation` fr 
                LEFT JOIN `t_fi_doc_for_archiv_transfer_log` ft ON ft.`company_code` = fr.`company_code` 
                AND ft.`year` = fr.`year` AND ft.`summary_unique_number` = fr.`summary_unique_number` 
                LEFT JOIN `t_fi_voucher_head` fh on fr.`fi_document_number` = fh.`fi_document_number` and fh.`year` = fr.`year` and fh.`period` = fr.`period`
            WHERE
              fr.`document_category` = 'EMDC' AND fr.`associated_doc_type` = 'COT' AND fh.`reversal_document` != ''
        '''

    if company_code and isinstance(company_code, str):
        query_sql += f" AND fr.`company_code` = '{company_code}' "
        re_query_sql += f" AND fr.`company_code` = '{company_code}' "

    table_alias = create_table_alias(columns)
    where_sql, sort_sql = generate_raw_sql(prefix_filter, filter_info, sort_info, table_alias)
    if not external_sn:
        query_sql += " AND ft.`external_sn` = '' "
        if where_sql:
            where_sql = where_sql.replace('WHERE ', ' AND ')
            full_query_sql = query_sql + where_sql + sort_sql
        else:
            full_query_sql = query_sql + sort_sql
    else:
        query_sql += " AND fr.`fi_document_number` != '' "
        if where_sql:
            where_sql = where_sql.replace('WHERE ', ' AND ')
            full_query_sql = '( ' + query_sql + where_sql + re_query_sql + where_sql + ' ) ' + sort_sql
        else:
            full_query_sql = query_sql + re_query_sql + sort_sql

    full_query_sql = full_query_sql.strip()
    print(full_query_sql)
    query_data = db_helper.query_sql(full_query_sql)

    display = [
        {"field": "company_code", "description": "公司代码"},
        {"field": "year", "description": "年度"},
        {"field": "period", "description": "期间"},
        {"field": "document_category", "description": "CO凭证类型"},
        {"field": "business_doc_sn", "description": "CO凭证编号"},
        {"field": "fi_document_number", "description": "财务凭证编号"},
        {"field": "archiv_doc_num", "description": "归档凭证号"},
        {"field": "posting_status", "description": "外部系统过账状态"},
        {"field": "external_sn", "description": "外部系统会计凭证号"},
        {"field": "note", "description": "状态信息"}
    ]

    return query_data, display


def CostAllocPostQuery():
    """费用分配分摊过账推送外部系统"""
    req = Request()
    res = Response()
    body = json.loads(req.body())
    payload = body.get('_payload_', {})
    filter_info = payload.get('filter_info', {})
    sort_info = payload.get('sort_info', {})
    export_excel = payload.get('export_excel')

    query_data, display = cost_alloc_post_query(body, external_sn=True)
    if export_excel:
        timestamp = datetime.now()
        stamp_suffix = timestamp.strftime('%Y%m%d%H%M%S')
        excel_filename = f'费用分配分摊过账推送外部系统-{stamp_suffix}.xlsx'
        format_data = [{'sheet1': query_data}]
        field_dict = display_to_entozh(display)
        GetExportData(format_data, excel_filename, field_dict)
    else:
        page_size = payload.get('page', {}).get('page_size', 0)
        page_num = payload.get('page', {}).get('page_num', 1)
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
                "data_sum": data_sum  # 总数据行数
            },
            "rule": {
                "sort_info": sort_info,
                "filter_info": filter_info
            },
            "display": display
        }

        res.set_body(json.dumps(response))
        res.commit(True)


def CostAllocPostPushSAP():
    """
    费用分配分摊过账推送外部系统 按钮
    task_id 505
    """
    req = Request()
    res = Response()
    body = json.loads(req.body())
    user_id = req.header("user_id")
    prefix_filter = body.get('data') or {}
    plant_code = prefix_filter.get('plant_code') or ''
    task_id = prefix_filter.get('task_id') or 505
    year = prefix_filter.get('year')
    period = prefix_filter.get('period')
    res_bus = CostAllocPostPushSAPCore(user_id, task_id, year, period, plant_code)
    res.set_body(json.dumps(res_bus))
    res.commit(True)


def CostAllocPostPushSAPCore(user_id, task_id, year, period, plant_code):
    """505 core"""
    code, msg = 200, ''
    body = {"data": {"year": year, "period": period, "plant_code": plant_code}}
    query_data, display = cost_alloc_post_query(body, external_sn=False)
    resp_code_list = []
    if query_data:
        push_dict = {}
        for item in query_data:
            if push_dict.get(f"{item.get('archiv_doc_num')}|{item.get('summary_unique_number')}"):
                continue
            else:
                push_dict[f"{item.get('archiv_doc_num')}|{item.get('summary_unique_number')}"] = item

            external_sn = item.get('external_sn') or ''
            if not external_sn:
                code, each_msg = ZZEXTCostAllocPostPushSAP(user_id, task_id, plant_code, item)
                resp_code_list.append(code)
                if code != 200:
                    msg = each_msg
    data, display = cost_alloc_post_query(body, external_sn=True)
    update_flag = True
    if data:
        for item in data:
            external_sn = item.get('external_sn') or ''
            if not external_sn:
                print(item)
                update_flag = False
                break
    if update_flag:
        code, msg = 200, '成功'
    elif any(code != 200 for code in resp_code_list):
        code = 206
    else:
        code, msg = 200, '成功'
    return {"code": code, "msg": msg, "data": data, "display": display}


def actual_cost_post_query(body, external_sn=True):
    """实际作业成本过账推送 查询"""
    prefix_filter = body.get('data') or {}
    prefix_filter, task_code, step = get_month_task_info(prefix_filter)
    payload = body.get('_payload_', {})
    filter_info = payload.get('filter_info', {})
    sort_info = payload.get('sort_info', {})

    company_code = ''
    if 'plant_code' in prefix_filter:
        plant_code = prefix_filter.pop('plant_code')
        company_code = get_company_by_plant(plant_code)

    db_helper = DbHelper()
    columns = '''   fr.`id`,
                    fr.`company_code`,
                    fr.`year`,
                    fr.`period`,
                    fr.`document_category`,
                    fr.`business_doc_sn`,
                    fr.`fi_document_number`,
                    fr.`summary_unique_number`,
                    ft.`archiv_doc_num`,
                    ft.`posting_status`,
                    ft.`external_sn`,
                    ft.`note`
                    '''

    query_sql = f'''
                SELECT
                    {columns}
                FROM
                    `t_fi_integration_relation` fr 
                    LEFT JOIN `t_fi_doc_for_archiv_transfer_log` ft ON ft.`company_code` = fr.`company_code` 
                    AND ft.`year` = fr.`year` AND ft.`summary_unique_number` = fr.`summary_unique_number` 
                    LEFT JOIN `t_fi_voucher_head` fh ON fr.`fi_document_number` = fh.`fi_document_number` and fh.`year` = fr.`year` and fh.`period` = fr.`period`
                WHERE
                  fr.`document_category` = 'COTR' AND fr.`associated_doc_type` = 'COC' AND ft.`archiv_doc_num` != '' 
            '''

    re_columns = '''fr.`id`,
                    fr.`company_code`,
                    fr.`year`,
                    fr.`period`,
                    fr.`document_category`,
                    fr.`business_doc_sn`,
                    fr.`fi_document_number`,
                    fr.`summary_unique_number`,
                    ft.`archiv_doc_num`,
                    ft.`posting_status`,
                    ft.`external_sn`,
                    ft.`note` '''

    re_query_sql = f'''
            ) UNION (
                    SELECT
                        {re_columns}
                    FROM
                        `t_fi_integration_relation` fr 
                        LEFT JOIN `t_fi_doc_for_archiv_transfer_log` ft ON ft.`company_code` = fr.`company_code` 
                        AND ft.`year` = fr.`year` AND ft.`summary_unique_number` = fr.`summary_unique_number` 
                        LEFT JOIN `t_fi_voucher_head` fh ON fr.`fi_document_number` = fh.`fi_document_number` and fh.`year` = fr.`year` and fh.`period` = fr.`period`
                    WHERE
                      fr.`document_category` = 'COTR' AND fr.`associated_doc_type` = 'COC' AND ft.`archiv_doc_num` != '' AND fh.`reversal_document` != ''
                '''

    if company_code and isinstance(company_code, str):
        query_sql += f" AND fr.`company_code` = '{company_code}' "
        re_query_sql += f" AND fr.`company_code` = '{company_code}' "

    table_alias = create_table_alias(columns)
    where_sql, sort_sql = generate_raw_sql(prefix_filter, filter_info, sort_info, table_alias)
    if not external_sn:
        query_sql += " AND ft.`external_sn` = '' "
        if where_sql:
            where_sql = where_sql.replace('WHERE ', ' AND ')
            full_query_sql = query_sql + where_sql + sort_sql
        else:
            full_query_sql = query_sql + sort_sql
    else:
        query_sql += " AND fr.`fi_document_number` != '' "
        if where_sql:
            where_sql = where_sql.replace('WHERE ', ' AND ')
            full_query_sql = '( ' + query_sql + where_sql + re_query_sql + where_sql + ' ) ' + sort_sql
        else:
            full_query_sql = query_sql + re_query_sql + sort_sql

    full_query_sql = full_query_sql.strip()
    print(full_query_sql)
    query_data = db_helper.query_sql(full_query_sql)

    display = [
        {"field": "company_code", "description": "公司代码"},
        {"field": "year", "description": "年度"},
        {"field": "period", "description": "期间"},
        {"field": "document_category", "description": "CO凭证类型"},
        {"field": "business_doc_sn", "description": "CO凭证编号"},
        {"field": "fi_document_number", "description": "财务凭证编号"},
        {"field": "archiv_doc_num", "description": "归档凭证号"},
        {"field": "posting_status", "description": "外部系统过账状态"},
        {"field": "external_sn", "description": "外部系统会计凭证号"},
        {"field": "note", "description": "状态信息"}
    ]

    return query_data, display


def ActualCostPostQuery():
    """实际作业成本过账推送外部系统 查询"""
    req = Request()
    res = Response()
    body = json.loads(req.body())
    payload = body.get('_payload_', {})
    filter_info = payload.get('filter_info', {})
    sort_info = payload.get('sort_info', {})
    export_excel = payload.get('export_excel')

    query_data, display = actual_cost_post_query(body, external_sn=True)
    if export_excel:
        timestamp = datetime.now()
        stamp_suffix = timestamp.strftime('%Y%m%d%H%M%S')
        excel_filename = f'实际作业成本过账推送外部系统-{stamp_suffix}.xlsx'
        format_data = [{'sheet1': query_data}]
        field_dict = display_to_entozh(display)
        GetExportData(format_data, excel_filename, field_dict)
    else:
        page_size = payload.get('page', {}).get('page_size', 0)
        page_num = payload.get('page', {}).get('page_num', 1)
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
                "data_sum": data_sum  # 总数据行数
            },
            "rule": {
                "sort_info": sort_info,
                "filter_info": filter_info
            },
            "display": display
        }

        res.set_body(json.dumps(response))
        res.commit(True)


def ActualCostPostPushSAP():
    """
    实际作业成本过账推送外部系统 按钮
    task_id 506
    """
    req = Request()
    res = Response()
    body = json.loads(req.body())
    user_id = req.header("user_id")
    prefix_filter = body.get('data') or {}
    plant_code = prefix_filter.get('plant_code') or ''
    task_id = prefix_filter.get('task_id') or 506
    year = prefix_filter.get('year')
    period = prefix_filter.get('period')
    res_bus = ActualCostPostPushSAPCore(user_id, task_id, year, period, plant_code)
    res.set_body(json.dumps(res_bus))
    res.commit(True)


def ActualCostPostPushSAPCore(user_id, task_id, year, period, plant_code):
    """506 core"""
    code, msg = 200, ''
    body = {"data": {"year": year, "period": period, "plant_code": plant_code}}

    query_data, display = actual_cost_post_query(body, external_sn=False)

    resp_code_list = []
    if query_data:
        push_dict = {}
        for item in query_data:
            if push_dict.get(f"{item.get('archiv_doc_num')}|{item.get('summary_unique_number')}"):
                continue
            else:
                push_dict[f"{item.get('archiv_doc_num')}|{item.get('summary_unique_number')}"] = item

            external_sn = item.get('external_sn') or ''
            if not external_sn:
                code, each_msg = ZZEXTActualCostPostPushSAP(user_id, task_id, plant_code, item)
                resp_code_list.append(code)
                if code != 200:
                    msg = each_msg

    data, display = actual_cost_post_query(body, external_sn=True)
    update_flag = True
    if data:
        for item in data:
            external_sn = item.get('external_sn') or ''
            if not external_sn:
                print(item)
                update_flag = False
                break
    if update_flag:
        code, msg = 200, '成功'
    elif any(code != 200 for code in resp_code_list):
        code = 206
    else:
        code, msg = 200, '成功'
    return {"code": code, "msg": msg, "data": data, "display": display}


def get_company_by_plant(plant_code):
    """根据工厂代码获取公司代码"""

    query_sql = "SELECT `company_code`, `plant_code` FROM `t_os_company_plant_alloc` "
    if plant_code:
        query_sql += " WHERE `plant_code` = {}".format(repr(plant_code))

    result_data = db_helper.query_sql(query_sql)
    company_code = result_data[0].get('company_code') if result_data else ''

    return company_code


def get_full_name_by_company_code(company_code):
    """根据公司代码获取公司描述"""

    query_sql = "SELECT `company_code`, `company_description` FROM `t_os_company` "
    if company_code:
        query_sql += " WHERE `company_code` = {}".format(repr(company_code))

    result_data = db_helper.query_sql(query_sql)
    plant_description = result_data[0].get('company_description') if result_data else ''
    return plant_description


def get_full_name_by_plant_code(plant_code):
    """根据工厂代码获取工厂描述"""
    plant_description = ''

    query_sql = "SELECT `plant_code`, `plant_description` FROM `t_os_plant` "
    if plant_code:
        query_sql += " WHERE `plant_code` = {}".format(repr(plant_code))

    result_data = db_helper.query_sql(query_sql)
    if result_data:
        plant_description = result_data[0].get('plant_description') or ''
    return plant_description


def period_process_post_query(body, associated_doc_type, external_sn=True):
    """期末在制过账推送 查询"""
    prefix_filter = body.get('data') or {}
    prefix_filter, task_code, step = get_month_task_info(prefix_filter)

    company_code = ''
    if 'plant_code' in prefix_filter:
        plant_code = prefix_filter.pop('plant_code')
        company_code = get_company_by_plant(plant_code)

    db_helper = DbHelper()

    if associated_doc_type and 'WIP1' in str(associated_doc_type):
        document_category = 'WIDC'
    else:
        document_category = 'WSDC'

    unique_number_sql = f'''
                SELECT DISTINCT
                    `business_doc_sn`,
                    `associated_doc_type`
                FROM
                    `t_fi_integration_relation` 
                WHERE
                    `document_category` in ('{document_category}', 'TZDC') AND `associated_doc_type` in ({associated_doc_type}) AND `business_doc_sn` != '' 
            '''

    where_sql, sort_sql = generate_raw_sql(prefix_filter, {}, {}, {})
    if where_sql:
        where_sql = where_sql.replace('WHERE ', ' AND ')
        year = prefix_filter.get('year')
        period = prefix_filter.get('period')
        if period and str(period) == '12':
            next_month_filter = {
                'year': str(int(year) + 1),
                'period': '01'
            }
            next_where_sql, _ = generate_raw_sql(next_month_filter, {}, {}, {})
            first_where_sql = where_sql.strip().strip('AND')
            next_where_sql = next_where_sql.strip().strip('WHERE')
            unique_number_sql += f" AND ( ( {first_where_sql} ) OR ( {next_where_sql} ) ) "
        else:
            unique_number_sql += where_sql
    if company_code and isinstance(company_code, str):
        unique_number_sql += f" AND `company_code` = '{company_code}' "

    print(unique_number_sql)
    unique_number_data = db_helper.query_sql(unique_number_sql)
    bus_doc_sn_list = [item.get('business_doc_sn') or '' for item in unique_number_data]
    document_type_dict = {i["business_doc_sn"]: i["associated_doc_type"] for i in unique_number_data}

    last_business_doc_sns = []
    if bus_doc_sn_list:
        if period and str(period) == '12':
            next_year = str(int(year) + 1)
            next_month = '01'
        else:
            next_year = str(year)
            next_month = str(int(period) + 1).zfill(2)

        sql = f'''
                SELECT
                    `id`,
                    `company_code`,
                    `year`,
                    `period`,
                    `business_doc_sn`,
                    `fi_document_number`,
                    `summary_unique_number`
                FROM
                    `t_fi_integration_relation`
                WHERE `year` = {repr(next_year)} AND `period` = {repr(next_month)}
            '''

        if isinstance(bus_doc_sn_list, list):
            sql += " AND `business_doc_sn` IN ({}) ".format(', '.join(map(repr, bus_doc_sn_list)))
        else:
            sql += f" AND `business_doc_sn` = {repr(bus_doc_sn_list)} "

        print(sql)
        check_data = db_helper.query_sql(sql)
        second_business_doc_sns = [item.get('fi_document_number', '') for item in check_data if item.get('fi_document_number')]
        second_business_doc_sns = list(set(second_business_doc_sns))
        if second_business_doc_sns:
            next_sql = f'''
                    SELECT
                        `id`,
                        `company_code`,
                        `year`,
                        `period`,
                        `business_doc_sn`,
                        `fi_document_number`,
                        `summary_unique_number`
                    FROM
                        `t_fi_integration_relation`
                    WHERE `year` = {repr(next_year)} AND `period` = {repr(next_month)}
                '''

            if isinstance(second_business_doc_sns, list):
                next_sql += " AND `business_doc_sn` IN ({}) ".format(', '.join(map(repr, second_business_doc_sns)))
            else:
                next_sql += f" AND `business_doc_sn` = {repr(second_business_doc_sns)} "

            print(next_sql)
            next_data = db_helper.query_sql(next_sql)
            last_business_doc_sns = [item.get('business_doc_sn', '') for item in next_data if
                                     item.get('business_doc_sn')]
            last_business_doc_sns = list(set(last_business_doc_sns))

    bus_doc_sn_list += last_business_doc_sns
    bus_doc_sn_list = list(set(bus_doc_sn_list))

    query_data, res_data, result, wp_dict = [], [], [], {}
    if bus_doc_sn_list:
        columns = '''
                    fr.`id`,
                    fr.`company_code`,
                    fr.`year`,
                    fr.`period`,
                    fr.`business_doc_sn`,
                    fr.`fi_document_number`,
                    fr.`summary_unique_number`,
                    fr.`posting_date`,
                    ft.`archiv_doc_num`,
                    ft.`external_sn` '''

        query_sql = f'''
                SELECT
                    {columns}
                FROM
                    `t_fi_integration_relation` fr
                LEFT JOIN `t_fi_doc_for_archiv_transfer_log` ft ON ft.`company_code` = fr.`company_code` 
                    AND ft.`year` = fr.`year` AND ft.`summary_unique_number` = fr.`summary_unique_number`
                WHERE 1 
            '''

        if not external_sn:
            query_sql += " AND ft.`external_sn` = '' "

        if bus_doc_sn_list and isinstance(bus_doc_sn_list, list):
            query_sql += " AND fr.`business_doc_sn` IN ({}) ".format(', '.join(map(repr, bus_doc_sn_list)).strip(','))

        print(query_sql)
        query_data = db_helper.query_sql(query_sql)
        for item in query_data:
            year = prefix_filter.get('year') or ''
            period = prefix_filter.get('period') or ''
            posting_date = item.get('posting_date') or ''

            this_month = datetime(year=int(year), month=int(period), day=1)
            next_month_first = this_month + relativedelta(months=1)
            this_month_last = next_month_first + relativedelta(days=-1)
            next_month_first = next_month_first.strftime('%Y-%m-%d')
            this_month_last = this_month_last.strftime('%Y-%m-%d')
            if posting_date == this_month_last or posting_date == next_month_first:
                # print('posting_date =', posting_date, 'this_month_last = ', this_month_last,
                #       'next_month_first = ', next_month_first)

                if associated_doc_type == "'WIP2', 'TZ01'":
                    item["doc_type"] = "WIP2-在制辅材" if document_type_dict[
                                                              item["business_doc_sn"]] == "WIP2" else "TZ01-扣料差异"

                result.append(item)

    display = [
        {"field": "company_code", "description": "公司代码"},
        {"field": "year", "description": "年度"},
        {"field": "period", "description": "期间"},
        {"field": "business_doc_sn", "description": "汇总唯一号"},
        {"field": "fi_document_number", "description": "财务凭证编号"},
        {"field": "archiv_doc_num", "description": "归档凭证号"},
        {"field": "posting_date", "description": "过账日期"},
        {"field": "external_sn", "description": "外部系统凭证号编号"}
    ]

    return result, display


def PeriodProcessPostQuery():
    """期末在制过账推送 查询"""
    req = Request()
    res = Response()
    body = json.loads(req.body())
    payload = body.get('_payload_', {})
    filter_info = payload.get('filter_info', {})
    sort_info = payload.get('sort_info', {})
    export_excel = payload.get('export_excel')

    query_data, display = period_process_post_query(body, associated_doc_type=" 'WIP1' ", external_sn=True)
    if query_data:
        if filter_info:
            query_data = filter_data(query_data, filter_info)  # 筛选过滤
        if sort_info:
            query_data = sort_data(query_data, sort_info)
    if export_excel:
        timestamp = datetime.now()
        stamp_suffix = timestamp.strftime('%Y%m%d%H%M%S')
        excel_filename = f'期末在制过账推送外部系统-{stamp_suffix}.xlsx'
        format_data = [{'sheet1': query_data}]
        field_dict = display_to_entozh(display)
        GetExportData(format_data, excel_filename, field_dict)
    else:
        page_size = payload.get('page', {}).get('page_size', 0)
        page_num = payload.get('page', {}).get('page_num', 1)
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
                "data_sum": data_sum  # 总数据行数
            },
            "rule": {
                "sort_info": sort_info,
                "filter_info": filter_info
            },
            "display": display
        }

        res.set_body(json.dumps(response))
        res.commit(True)


def next_period(year, period):
    if period < 1 or period > 12:
        raise ValueError("期间必须在1到12之间")
    next_month = period + 1

    next_year = year
    if next_month > 12:
        next_year = year + 1
        next_month = 1

    return str(next_year), str(next_month).zfill(2)


def lot_list_post_query(body):
    """在制LOT清单同步外部系统 查询"""
    prefix_filter = body.get('data') or {}
    year = prefix_filter.get('year')
    period = prefix_filter.get('period')
    plant_code = prefix_filter.get('plant_code')
    next_year, next_month = next_period(int(year), int(period))

    db_helper = DbHelper()
    query_sql = "SELECT * FROM `t_co_wip_list_sync_result` WHERE 1 "
    count_sql = "SELECT count(1) AS `push_num` FROM `t_co_manufacturing_mes_quantity` WHERE 1 "
    if plant_code:
        query_sql += " AND `plant_code` = {} ".format(repr(plant_code))
        count_sql += " AND `plant_code` = {} ".format(repr(plant_code))
    if next_year:
        query_sql += " AND `year` = {} ".format(repr(year))
        count_sql += " AND `year` = {} ".format(repr(next_year))
    if next_month:
        query_sql += " AND `period` = {} ".format(repr(period))
        count_sql += " AND `period` = {} ".format(repr(next_month))

    print(query_sql)
    query_data = db_helper.query_sql(query_sql)
    res_data = query_data
    if not query_data:
        query_data = db_helper.query_sql(count_sql)
        push_num = query_data[0].get('push_num') if query_data else 0
        res_data = [
            {
                'company_code': get_company_by_plant(plant_code),
                'plant_code': plant_code,
                'year': year,
                'period': period,
                'push_num': push_num,
                'push_status': '',
            }
        ]

    display = [
        {"field": "company_code", "description": "公司代码"},
        {"field": "plant_code", "description": "工厂代码"},
        {"field": "year", "description": "年度"},
        {"field": "period", "description": "期间"},
        {"field": "push_num", "description": "推送条目数"},
        {"field": "push_status", "description": "推送状态 S:成功 E:失败"}
    ]

    return res_data, display


def LotListPostQuery():
    """在制LOT清单同步外部系统 查询"""
    req = Request()
    res = Response()
    body = json.loads(req.body())
    payload = body.get('_payload_', {})
    filter_info = payload.get('filter_info', {})
    sort_info = payload.get('sort_info', {})
    export_excel = payload.get('export_excel')

    query_data, display = lot_list_post_query(body)
    if query_data:
        if filter_info:
            query_data = filter_data(query_data, filter_info)  # 筛选过滤
        if sort_info:
            query_data = sort_data(query_data, sort_info)
    if export_excel:
        timestamp = datetime.now()
        stamp_suffix = timestamp.strftime('%Y%m%d%H%M%S')
        excel_filename = f'在制LOT清单同步外部系统-{stamp_suffix}.xlsx'
        format_data = [{'sheet1': query_data}]
        field_dict = display_to_entozh(display)
        GetExportData(format_data, excel_filename, field_dict)
    else:
        page_size = payload.get('page', {}).get('page_size', 0)
        page_num = payload.get('page', {}).get('page_num', 1)
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
                "data_sum": data_sum  # 总数据行数
            },
            "rule": {
                "sort_info": sort_info,
                "filter_info": filter_info
            },
            "display": display
        }

        res.set_body(json.dumps(response))
        res.commit(True)


def LotListPushSAP():
    """在制LOT清单同步外部系统"""
    import datetime as dt
    update_time = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    req = Request()
    res = Response()
    body = json.loads(req.body())
    user_id = req.header("user_id")

    prefix_filter = body.get('data') or {}
    year = prefix_filter.get('year')
    period = prefix_filter.get('period')
    plant_code = prefix_filter.get('plant_code')
    company_code = get_company_by_plant(plant_code)
    next_year, next_month = next_period(int(year), int(period))
    res_data = [company_code, plant_code, year, period]

    code, msg = 200, '推送成功'
    count_sql = "SELECT count(1) AS `push_num` FROM `t_co_manufacturing_mes_quantity` WHERE 1 = 1 "
    if plant_code:
        count_sql += " AND `plant_code` = {} ".format(repr(plant_code))
    if next_year:
        count_sql += " AND `year` = {} ".format(repr(next_year))
    if next_month:
        count_sql += " AND `period` = {} ".format(repr(next_month))

    db_helper = DbHelper()
    query_data, resp_data = [], {}
    query_data = db_helper.query_sql(count_sql)
    push_num = query_data[0].get('push_num') if query_data else 0

    try:
        from LotIdStateSync import send_lotid_sap
        print('send_lotid_sap:', plant_code, year, period)
        code, msg, resp_data = send_lotid_sap(plant_code, year, period)
        print('code:', code, 'msg:', msg, 'resp_data:', resp_data)
        if code == 200:
            push_status = 'S'
        else:
            push_status = 'E'
            # msg = '推送失败'

        res_data.append(push_num)
        res_data.append(push_status)
        res_data.append(user_id)
        res_data.append(user_id)
        res_data.append(str(msg)[:250])

        values_str = ', '.join(map(repr, res_data))
        insert_sql = f"""
          INSERT INTO `t_co_wip_list_sync_result`(`company_code`, `plant_code`, `year`, `period`, `push_num`, `push_status`, `create_id`, `update_id`, `note`)
          values ({values_str})
          ON DUPLICATE KEY UPDATE
          `push_num` = {push_num},
          `push_status` = '{push_status}',
          `update_id` = {user_id},
          `update_time` = '{update_time}'
        """
        print(insert_sql)
        status = db_helper.exec_sql(insert_sql)
        if status < 0:
            code = 500
            msg = '更新推送结果失败'
    except Exception as e:
        print(str(e))
        code = 500
        msg = '更新推送结果失败'

    res.set_body(json.dumps({"code": code, "msg": msg, "data": resp_data}))
    res.commit(True)


def PeriodProcessPostPushSAP():
    """
    期末在制过账推送外部系统 按钮
    task_id 507
    """
    req = Request()
    res = Response()
    body = json.loads(req.body())
    user_id = req.header("user_id")
    prefix_filter = body.get('data') or {}
    plant_code = prefix_filter.get('plant_code') or ''
    task_id = prefix_filter.get('task_id') or 507
    year = prefix_filter.get('year')
    period = prefix_filter.get('period')
    res_bus = PeriodProcessPostPushSAPCore(user_id, task_id, year, period, plant_code)
    res.set_body(json.dumps(res_bus))
    res.commit(True)


def PeriodProcessPostPushSAPCore(user_id, task_id, year, period, plant_code):
    """"507 core"""
    code, msg = 200, ''
    body = {"data": {"year": year, "period": period, "plant_code": plant_code}}
    query_data, display = period_process_post_query(body, associated_doc_type=" 'WIP1' ", external_sn=False)
    resp_code_list = []
    if query_data:
        push_dict = {}
        for item in query_data:
            if push_dict.get(f"{item.get('archiv_doc_num')}|{item.get('summary_unique_number')}"):
                continue
            else:
                push_dict[f"{item.get('archiv_doc_num')}|{item.get('summary_unique_number')}"] = item

            external_sn = item.get('external_sn') or ''
            if not external_sn:
                code, each_msg = ZZEXTPeriodProcessPostPushSAP(user_id, task_id, plant_code, item)
                resp_code_list.append(code)
                if code != 200:
                    msg = each_msg

    data, display = period_process_post_query(body, associated_doc_type=" 'WIP1' ", external_sn=True)
    update_flag = True
    if data:
        for item in data:
            external_sn = item.get('external_sn') or ''
            if not external_sn:
                print(item)
                update_flag = False
                break
    if update_flag:
        code, msg = 200, '成功'
    elif any(code != 200 for code in resp_code_list):
        code = 206
    else:
        code, msg = 200, '成功'
    return {"code": code, "msg": msg, "data": data, "display": display}


def completion_cost_post_query(body):
    """完工成本过账 查询"""
    prefix_filter = body.get('data') or {}
    prefix_filter, task_code, step = get_month_task_info(prefix_filter)
    payload = body.get('_payload_', {})
    filter_info = payload.get('filter_info', {})
    sort_info = payload.get('sort_info', {})

    db_helper = DbHelper()
    columns = '''   t1.`id`,
                    CASE t1.`posting_type` WHEN '03' THEN '03-完工结算过账' ELSE t1.`posting_type` END AS `posting_type`,
                    t1.`company_code`,
                    t3.`company_description`,
                    t1.`plant_code`,
                    t2.`plant_description`,
                    t1.`year`,
                    t1.`period`,
                    t1.`posting_status`,
                    t1.`reversal_status`,
                    t1.`fi_document_number`,
                    t1.`reversal_document` '''

    query_sql = f'''
            SELECT
                {columns}
            FROM
                `t_fi_completion_log` AS t1
            LEFT JOIN `t_os_plant` AS t2 ON t1.`plant_code` = t2.`plant_code`
            LEFT JOIN `t_os_company` AS t3 ON t1.`company_code` = t3.`company_code`
            WHERE 1 
        '''

    table_alias = create_table_alias(columns)
    where_sql, sort_sql = generate_raw_sql(prefix_filter, filter_info, sort_info, table_alias)

    if not sort_sql:
        sort_sql = " ORDER BY `id` DESC LIMIT 1 "
    if where_sql:
        where_sql = where_sql.replace('WHERE ', ' AND ')
        query_sql += where_sql + sort_sql
    else:
        query_sql += sort_sql
    query_sql = query_sql.replace('    ', ' ')
    print(query_sql)
    query_data = db_helper.query_sql(query_sql)
    if not query_data:
        plant_code = prefix_filter.get('plant_code')
        query_data = [
            {
                "id": 1,
                "posting_type": "03-完工结算过账",
                "company_code": get_company_by_plant(plant_code),
                "company_description": get_full_name_by_company_code(get_company_by_plant(plant_code)),
                "plant_code": prefix_filter.get('plant_code'),
                "plant_description": get_full_name_by_plant_code(plant_code),
                "year": prefix_filter.get('year'),
                "period": prefix_filter.get('period'),
                "posting_status": "",
                "reversal_status": "",
                "fi_document_number": "",
                "reversal_document": ""
            }
        ]

    display = [
        {"field": "posting_type", "description": "过账类别"},
        {"field": "company_code", "description": "公司代码"},
        {"field": "company_description", "description": "公司描述"},
        {"field": "plant_code", "description": "工厂"},
        {"field": "plant_description", "description": "工厂名称"},
        {"field": "year", "description": "年度"},
        {"field": "period", "description": "期间"},
        {"field": "posting_status", "description": "过账状态"},
        {"field": "reversal_status", "description": "重置状态"},
        {"field": "fi_document_number", "description": "财务凭证编码"},
        {"field": "reversal_document", "description": "重置凭证编号"},
    ]

    return query_data, display


def completion_cost_post_push_query(body, external_sn=True):
    """完工成本过账推送外部系统 查询"""
    prefix_filter = body.get('data') or {}
    prefix_filter, task_code, step = get_month_task_info(prefix_filter)
    payload = body.get('_payload_', {})
    filter_info = payload.get('filter_info', {})
    sort_info = payload.get('sort_info', {})

    company_code = ''
    if 'plant_code' in prefix_filter:
        plant_code = prefix_filter.pop('plant_code')
        company_code = get_company_by_plant(plant_code)

    db_helper = DbHelper()
    columns = '''
                fr.`id`,
                fr.`company_code`,
                tc.`company_description`,
                fr.`year`,
                fr.`period`,
                fr.`associated_doc_type`,
                fr.`business_doc_sn`,
                fr.`fi_document_number`,
                fr.`summary_unique_number`,
                fr.`posting_date`,
                fr.`posting_status`,
                ft.`archiv_doc_num`,
                ft.`external_sn` '''

    query_sql = f'''
            SELECT
                {columns}
            FROM
                `t_fi_integration_relation` fr
            LEFT JOIN `t_fi_doc_for_archiv_transfer_log` ft ON ft.`company_code` = fr.`company_code` 
                AND ft.`year` = fr.`year` AND ft.`summary_unique_number` = fr.`summary_unique_number` 
            LEFT JOIN `t_fi_voucher_head` fh ON fr.`fi_document_number` = fh.`fi_document_number` and fh.`year` = fr.`year` and fh.`period` = fr.`period`
            LEFT JOIN `t_os_company` AS tc ON fr.`company_code` = tc.`company_code`
            WHERE
                fr.`document_category` = 'CCDC' AND fr.`associated_doc_type`  = 'CCDC'
        '''

    re_columns = '''
                fr.`id`,
                fr.`company_code`,
                tc.`company_description`,
                fr.`year`,
                fr.`period`,
                fr.`associated_doc_type`,
                fr.`business_doc_sn`,
                fr.`fi_document_number`,
                fr.`summary_unique_number`,
                fr.`posting_date`,
                fr.`posting_status`,
                ft.`archiv_doc_num`,
                ft.`external_sn` '''

    re_query_sql = f'''
        ) UNION (
                SELECT
                    {re_columns}
                FROM
                    `t_fi_integration_relation` fr
                LEFT JOIN `t_fi_doc_for_archiv_transfer_log` ft ON ft.`company_code` = fr.`company_code` 
                    AND ft.`year` = fr.`year` AND ft.`summary_unique_number` = fr.`summary_unique_number` 
                LEFT JOIN `t_fi_voucher_head` fh ON fr.`fi_document_number` = fh.`fi_document_number` and fh.`year` = fr.`year` and fh.`period` = fr.`period`
                LEFT JOIN `t_os_company` AS tc ON fr.`company_code` = tc.`company_code`
                WHERE
                    fr.`document_category` = 'CCDC' AND fr.`associated_doc_type`  = 'CCDC' AND fh.`reversal_document` != ''
            '''

    if company_code and isinstance(company_code, str):
        query_sql += f" AND fr.`company_code` = '{company_code}' "
        re_query_sql += f" AND fr.`company_code` = '{company_code}' "

    table_alias = create_table_alias(columns)
    where_sql, sort_sql = generate_raw_sql(prefix_filter, filter_info, sort_info, table_alias)
    if not external_sn:
        query_sql += " AND ft.`external_sn` = '' "
        if where_sql:
            where_sql = where_sql.replace('WHERE ', ' AND ')
            full_query_sql = query_sql + where_sql + sort_sql
        else:
            full_query_sql = query_sql + sort_sql
    else:
        query_sql += " AND fr.`fi_document_number` != '' "
        if where_sql:
            where_sql = where_sql.replace('WHERE ', ' AND ')
            full_query_sql = '( ' + query_sql + where_sql + re_query_sql + where_sql + ' ) ' + sort_sql
        else:
            full_query_sql = query_sql + re_query_sql + sort_sql

    full_query_sql = full_query_sql.strip()
    print(full_query_sql)
    query_data = db_helper.query_sql(full_query_sql)

    display = [
        {"field": "company_code", "description": "公司代码"},
        {"field": "company_description", "description": "公司描述"},
        {"field": "year", "description": "年度"},
        {"field": "period", "description": "期间"},
        {"field": "associated_doc_type", "description": "CO凭证类型"},
        {"field": "business_doc_sn", "description": "CO凭证编号"},
        {"field": "fi_document_number", "description": "财务凭证编号"},
        {"field": "archiv_doc_num", "description": "归档凭证号"},
        {"field": "posting_status", "description": "外部系统过账状态"},
        {"field": "external_sn", "description": "外部系统会计凭证号"}
    ]

    return query_data, display


def CompletionCostPostQuery():
    """完工成本过账 查询"""
    req = Request()
    res = Response()
    body = json.loads(req.body())
    payload = body.get('_payload_', {})
    filter_info = payload.get('filter_info', {})
    sort_info = payload.get('sort_info', {})
    export_excel = payload.get('export_excel')

    query_data, display = completion_cost_post_query(body)
    if export_excel:
        timestamp = datetime.now()
        stamp_suffix = timestamp.strftime('%Y%m%d%H%M%S')
        excel_filename = f'完工成本过账-{stamp_suffix}.xlsx'
        format_data = [{'sheet1': query_data}]
        field_dict = display_to_entozh(display)
        GetExportData(format_data, excel_filename, field_dict)
    else:
        page_size = payload.get('page', {}).get('page_size', 0)
        page_num = payload.get('page', {}).get('page_num', 1)
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
                "data_sum": data_sum  # 总数据行数
            },
            "rule": {
                "sort_info": sort_info,
                "filter_info": filter_info
            },
            "display": display
        }

        res.set_body(json.dumps(response))
        res.commit(True)


def CompletionCostPostAccounting():
    """
        完工成本过账 过账按钮
        完工过账：complate_accounting
        task_id 508
    """
    req = Request()
    res = Response()
    body = json.loads(req.body())
    payload = body.get('data') or {}
    year = payload.get('year')
    period = payload.get('period')
    plant_code = payload.get('plant_code')
    res_bus = CompletionCostPostAccountingCore(year, period, plant_code)
    code = res_bus.get("code")
    msg = res_bus.get("msg")

    data, display = completion_cost_post_query(body)
    if data:
        for item in data:
            posting_status = item.get('posting_status') or ''
            if posting_status.upper() != 'S':
                print(item)
                break
    res.set_body(json.dumps({"code": code, "msg": msg, "data": data, "display": display}))
    res.commit(True)


def CompletionCostPostAccountingCore(year, period, plant_code):
    code, msg = 200, '成功'
    log_code = '030030040'
    output = {}
    in_data = {
        "posting_type": '03',  # 过账类别
        "plant_code": plant_code or '',  # 工厂
        "year": year or '',  # 过账年度
        "period": period or '',  # 期间
    }
    input_data = json.dumps(in_data)
    exec_operator('complate_accounting', input_data, output)
    resp_str = output.get('data') or ''
    if resp_str:
        resp = json.loads(resp_str, strict=False)
        code = resp.get('code') or 0
        print('resp code:', code)
        if code == 200:
            msg = '成功'
        else:
            code = 206
            msg = resp.get('msg') or ''
            detail = {
                'input': in_data,
                'output': resp,
            }
            LoggerConfig.logToDB(log_code, '', LogLevel.ERROR, f'完工成本过账 complate_accounting:{msg}', detail, plant_code)
    return {"code": code, "msg": msg}


def CompletionCostPostReversal():
    """
        完工成本过账 重置按钮
        完工冲销：complate_reversal
        task_id 508
    """
    req = Request()
    res = Response()
    body = json.loads(req.body())
    payload = body.get('data') or {}
    year = payload.get('year')
    period = payload.get('period')
    plant_code = payload.get('plant_code')
    res_bus = CompletionCostPostReversalCore(year, period, plant_code)
    code = res_bus.get("code")
    msg = res_bus.get("msg")
    data, display = completion_cost_post_query(body)
    if data:
        for item in data:
            reversal_status = item.get('reversal_status') or ''
            if reversal_status.upper() != 'S':
                print(item)
                break
    res.set_body(json.dumps({"code": code, "msg": msg, "data": data, "display": display}))
    res.commit(True)


def CompletionCostPostReversalCore(year, period, plant_code):
    code, msg = 200, '成功'
    log_code = '030030040'
    output = {}
    in_data = {
        "posting_type": '03',  # 过账类别
        "plant_code": plant_code or '',  # 工厂
        "year": year or '',  # 过账年度
        "period": period or '',  # 期间
    }
    input_data = json.dumps(in_data)
    exec_operator('complate_reversal', input_data, output)
    resp_str = output.get('data') or ''
    if resp_str:
        resp = json.loads(resp_str, strict=False)
        code = resp.get('code') or 0
        print('resp code:', code)
        if code == 200:
            msg = '成功'
        else:
            code = 206
            msg = resp.get('msg') or ''
            detail = {
                'input': in_data,
                'output': resp,
            }
            LoggerConfig.logToDB(log_code, '', LogLevel.ERROR, f'完工成本过账重置 complate_reversal:{msg}', detail, plant_code)
    return {"code": code, "msg": msg}


def CompletionCostPostPushQuery():
    """完工成本过账推送外部系统 查询"""
    req = Request()
    res = Response()
    body = json.loads(req.body())
    payload = body.get('_payload_', {})
    filter_info = payload.get('filter_info', {})
    sort_info = payload.get('sort_info', {})
    export_excel = payload.get('export_excel')

    query_data, display = completion_cost_post_push_query(body, external_sn=True)
    if export_excel:
        timestamp = datetime.now()
        stamp_suffix = timestamp.strftime('%Y%m%d%H%M%S')
        excel_filename = f'完工成本过账推送外部系统-{stamp_suffix}.xlsx'
        format_data = [{'sheet1': query_data}]
        field_dict = display_to_entozh(display)
        GetExportData(format_data, excel_filename, field_dict)
    else:
        page_size = payload.get('page', {}).get('page_size', 0)
        page_num = payload.get('page', {}).get('page_num', 1)
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
                "data_sum": data_sum  # 总数据行数
            },
            "rule": {
                "sort_info": sort_info,
                "filter_info": filter_info
            },
            "display": display
        }

        res.set_body(json.dumps(response))
        res.commit(True)


def CompletionCostPostPushSAP():
    """
    完工成本过账推送外部系统 按钮
    task_id 509
    """
    req = Request()
    res = Response()
    body = json.loads(req.body())
    user_id = req.header("user_id")

    payload = body.get('data') or {}
    plant_code = payload.get('plant_code') or ''
    task_id = payload.get('task_id') or 509
    year = payload.get('year')
    period = payload.get('period')
    res_bus = CompletionCostPostPushSAPCore(user_id, task_id, year, period, plant_code)
    res.set_body(json.dumps(res_bus))
    res.commit(True)


def CompletionCostPostPushSAPCore(user_id, task_id, year, period, plant_code):
    """509 core"""
    code, msg = 200, ''
    body = {"data": {"year": year, "period": period, "plant_code": plant_code}}
    query_data, display = completion_cost_post_push_query(body, external_sn=False)
    resp_code_list = []
    if query_data:
        push_dict = {}
        for item in query_data:
            if push_dict.get(f"{item.get('archiv_doc_num')}|{item.get('summary_unique_number')}"):
                continue
            else:
                push_dict[f"{item.get('archiv_doc_num')}|{item.get('summary_unique_number')}"] = item

            external_sn = item.get('external_sn') or ''
            if not external_sn:
                code, each_msg = ZZEXTCompletionCostPostPushSAP(user_id, task_id, plant_code, item)
                resp_code_list.append(code)
                if code != 200:
                    msg = each_msg
    data, display = completion_cost_post_push_query(body, external_sn=True)
    update_flag = True
    if data:
        for item in data:
            external_sn = item.get('external_sn') or ''
            if not external_sn:
                print(item)
                update_flag = False
                break
    if update_flag:
        code, msg = 200, '成功'
    elif any(code != 200 for code in resp_code_list):
        code = 206
    else:
        code, msg = 200, '成功'
    return {"code": code, "msg": msg, "data": data, "display": display}


def not_outsource_inventory_query(body):
    """非外购外协存货实际成本过账  查询"""
    prefix_filter = body.get('data') or {}
    prefix_filter, task_code, step = get_month_task_info(prefix_filter)
    post_type = body.get('post_type') or ''
    if post_type and isinstance(post_type, str):
        push_type_list = [post_type]
    else:
        push_type_list = ['01', '02']

    cp_list, cr_list, cp_display, cr_display = [], [], [], []
    query_data = []
    db_helper = DbHelper()
    display = [
        {"field": "ml_cal_type", "description": "存货计算类型"},
        {"field": "posting_type", "description": "过账类别"},
        {"field": "company_code", "description": "公司代码"},
        {"field": "company_description", "description": "公司描述"},
        {"field": "plant_code", "description": "工厂"},
        {"field": "plant_description", "description": "工厂名称"},
        {"field": "year", "description": "年度"},
        {"field": "period", "description": "期间"},
        {"field": "posting_status", "description": "过账状态"},
        {"field": "reversal_status", "description": "重置状态"},
        {"field": "fi_document_number", "description": "财务凭证编码"},
        {"field": "reversal_document", "description": "重置凭证编号"},
    ]

    for post_type in push_type_list:
        if post_type in ['01', '02']:
            columns = '''   t1.`id`,
                            CASE t1.`ml_cal_type` WHEN '01' THEN '01-外购外协' WHEN '02' THEN '02-非外购外协' ELSE t1.`ml_cal_type` END AS `ml_cal_type`,
                            CASE t1.`posting_type` WHEN '01' THEN '01-周期价格还原' WHEN '02' THEN '02-消耗重估过账' ELSE t1.`posting_type` END AS `posting_type`,
                            t1.`company_code`,
                            t3.`company_description`,
                            t1.`plant_code`,
                            t2.`plant_description`,
                            t1.`year`,
                            t1.`period`,
                            t1.`posting_status`,
                            t1.`reversal_status`,
                            t1.`fi_document_number`,
                            t1.`reversal_document` '''

            query_sql = f'''
                        SELECT
                            {columns}
                        FROM
                            `t_fi_actual_cost_log` AS t1
                        LEFT JOIN `t_os_plant` AS t2 ON t1.`plant_code` = t2.`plant_code`
                        LEFT JOIN `t_os_company` AS t3 ON t1.`company_code` = t3.`company_code`
                        WHERE
                          `ml_cal_type` = '02' AND `posting_type` = '{post_type}'
                    '''

            table_alias = create_table_alias(columns)
            where_sql, sort_sql = generate_raw_sql(prefix_filter, {}, {}, table_alias)

            if not sort_sql:
                sort_sql = " ORDER BY `id` DESC LIMIT 1"
            if where_sql:
                where_sql = where_sql.replace('WHERE ', ' AND ')
                full_query_sql = query_sql + where_sql + sort_sql
            else:
                full_query_sql = query_sql + sort_sql
            full_query_sql = full_query_sql.replace('    ', ' ')
            print(full_query_sql)

            query_data = db_helper.query_sql(full_query_sql)
            if not query_data:
                plant_code = prefix_filter.get('plant_code')
                posting_type = ''
                if post_type == '01':
                    posting_type = '01-周期价格还原'
                elif post_type == '02':
                    posting_type = '02-消耗重估过账'

                query_data = [
                    {
                        "id": 1,
                        "ml_cal_type": "02-非外购外协",
                        "posting_type": posting_type,
                        "company_code": get_company_by_plant(plant_code),
                        "company_description": get_full_name_by_company_code(get_company_by_plant(plant_code)),
                        "plant_code": prefix_filter.get('plant_code'),
                        "plant_description": get_full_name_by_plant_code(plant_code),
                        "year": prefix_filter.get('year'),
                        "period": prefix_filter.get('period'),
                        "posting_status": "",
                        "reversal_status": "",
                        "fi_document_number": "",
                        "reversal_document": ""
                    }
                ]

        if post_type == '01':
            cp_list = query_data
            cp_display = display
        elif post_type == '02':
            cr_list = query_data
            cr_display = display

    res_data = {
        'cp': cp_list,
        'cr': cr_list,
    }

    total_display = {
        'cp': cp_display,
        'cr': cr_display,
    }

    return res_data, total_display


def NotOutsourceInventoryQuery():
    """非外购外协存货实际成本过账推送外部系统"""
    req = Request()
    res = Response()
    body = json.loads(req.body())
    data, display = not_outsource_inventory_query(body)

    res.set_body(json.dumps({"code": 200, "msg": '成功', "data": data, "display": display}))
    res.commit(True)


def NotOutsourceInventoryAccounting():
    """
        非外购外协存货实际成本过账 过账按钮
        01 周期还原过账：cycle_accounting
        02 消耗重估过账：consume_accounting
        task_id 510
    """
    req = Request()
    res = Response()
    body = json.loads(req.body())
    payload = body.get('data') or {}
    post_type = body.get('post_type') or ''
    res_bus = NotOutsourceInventoryAccountingCore(payload.get('year'), payload.get('period'), payload.get('plant_code'),
                                                  post_type)
    code = res_bus.get("code")
    msg = res_bus.get("msg")
    if 'post_type' in body:
        body.pop('post_type')
    total_data, total_display = not_outsource_inventory_query(body)
    query_key = outsource_types.get(post_type) or ''
    data = total_data.get(query_key) or []
    for unique_key, query_data in total_data.items():
        if query_data:
            for item in query_data:
                posting_status = item.get('posting_status') or ''
                print('posting_status', posting_status)
                if posting_status.upper() != 'S':
                    break
    display = total_display.get(query_key) or []
    res.set_body(json.dumps({"code": code, "msg": msg, "data": data, "display": display}))
    res.commit(True)


def NotOutsourceInventoryAccountingCore(year, period, plant_code, post_type=None):
    code, msg = 200, '成功'
    log_code = '030030046'
    post_types = [post_type] if post_type else ["01", "02"]
    type_map = {
        "01": ("01", "cycle_accounting", "周期还原过账"),
        "02": ("02", "consume_accounting", "消耗重估过账")
    }

    if not post_type:
        req_param = {"data": {"year": year, "period": period, "plant_code": plant_code}, "post_type": post_type}
        res_data, _ = not_outsource_inventory_query(req_param)
        cp_data = res_data.get('cp', [])
        cr_data = res_data.get('cr', [])
        # 过账的时候，如果已经生成财务凭证编码且没有被冲销，不需要过账
        if cp_data and (cp_data[0].get('fi_document_number') and not cp_data[0].get('reversal_document')):
            post_types.remove("01")

        if cr_data and (cr_data[0].get('fi_document_number') and not cr_data[0].get('reversal_document')):
            post_types.remove("02")

    for p_type in post_types:
        if p_type not in type_map:
            continue
        ml_type, op_name, label = type_map[p_type]
        output = {}
        in_data = {
            "ml_cal_type": "02",
            "posting_type": p_type,
            "plant_code": plant_code or '',
            "year": year or '',
            "period": period,
        }
        exec_operator(op_name, json.dumps(in_data), output)
        resp_str = output.get('data') or ''

        if resp_str:
            resp = json.loads(resp_str, strict=False)
            curr_code = resp.get('code') or 0
            if curr_code != 200:
                # 记录失败信息并终止后续循环
                code = 206
                msg = resp.get('msg') or '执行失败'
                detail = {'input': in_data, 'output': resp}
                LoggerConfig.logToDB(log_code, '', LogLevel.ERROR, f'{label} {op_name}:{msg}', detail, plant_code)
                break
            else:
                code, msg = 200, '成功'
    return {"code": code, "msg": msg}


def NotOutsourceInventoryReversal():
    """
        非外购外协存货实际成本过账 重置过账按钮
        01 周期还原冲销：cycle_reversal
        02 消耗重估冲销：consume_reversal
    """
    req = Request()
    res = Response()
    body = json.loads(req.body())
    payload = body.get('data') or {}
    post_type = body.get('post_type') or ''
    res_bus = NotOutsourceInventoryReversalCore(payload.get('year'), payload.get('period'), payload.get('plant_code'),
                                                post_type)
    code = res_bus.get("code")
    msg = res_bus.get("msg")
    if 'post_type' in body:
        body.pop('post_type')
    total_data, total_display = not_outsource_inventory_query(body)
    query_key = outsource_types.get(post_type) or ''
    data = total_data.get(query_key) or []
    for unique_key, query_data in total_data.items():
        if query_data:
            for item in query_data:
                reversal_status = item.get('reversal_status') or ''
                print('reversal_status :', reversal_status)
                if reversal_status.upper() != 'S':
                    break
    display = total_display.get(query_key) or []
    res.set_body(json.dumps({"code": code, "msg": msg, "data": data, "display": display}))
    res.commit(True)


def NotOutsourceInventoryReversalCore(year, period, plant_code, post_type=None):
    code, msg = 200, '成功'
    log_code = '030030046'
    post_types = [post_type] if post_type else ["01", "02"]
    type_map = {
        "01": ("01", "cycle_accounting", "周期还原冲销"),
        "02": ("02", "consume_accounting", "消耗重估冲销")
    }

    if not post_type:
        req_param = {
            'year': year,
            'period': period,
            'plant_code': plant_code,
        }
        res_data, _ = not_outsource_inventory_query(req_param)
        cp_data = res_data.get('cp', [])
        cr_data = res_data.get('cr', [])
        # 重置的时候，如果没有生成财务凭证编码，不需要重置
        if cp_data and (not cp_data[0].get('fi_document_number') or cp_data[0].get('reversal_document')):
            post_types.remove("01")

        if cr_data and (not cr_data[0].get('fi_document_number') or cr_data[0].get('reversal_document')):
            post_types.remove("02")

    for p_type in post_types:
        if p_type not in type_map:
            continue
        ml_type, op_name, label = type_map[p_type]
        output = {}
        in_data = {
            "ml_cal_type": "02",
            "posting_type": p_type,
            "plant_code": plant_code or '',
            "year": year or '',
            "period": period,
        }
        exec_operator(op_name, json.dumps(in_data), output)
        resp_str = output.get('data') or ''
        if resp_str:
            resp = json.loads(resp_str, strict=False)
            curr_code = resp.get('code') or 0
            if curr_code != 200:
                # 记录失败信息并终止后续循环
                code = 206
                msg = resp.get('msg') or '执行失败'
                detail = {'input': in_data, 'output': resp}
                LoggerConfig.logToDB(log_code, '', LogLevel.ERROR, f'{label} {op_name}:{msg}', detail, plant_code)
                break
            else:
                code, msg = 200, '成功'
    return {"code": code, "msg": msg}


def not_outsource_inventory_push_query(body, external_sn=True):
    """非外购外协存货实际成本过账推送外部系统  查询"""
    prefix_filter = body.get('data') or {}
    prefix_filter, task_code, step = get_month_task_info(prefix_filter)
    post_type = body.get('post_type')
    if post_type and isinstance(post_type, str):
        push_type_list = [post_type]
    else:
        push_type_list = ['01', '02', '03']

    cp_list, cr_list, wp_list = [], [], []
    cp_display, cr_display, wp_display = [], [], []
    query_data = []
    db_helper = DbHelper()

    display = [
        {"field": "ml_cal_type", "description": "存货计算类型"},
        {"field": "posting_type", "description": "过账类别"},
        {"field": "company_code", "description": "公司代码"},
        {"field": "company_description", "description": "公司描述"},
        {"field": "plant_code", "description": "工厂"},
        {"field": "plant_description", "description": "工厂名称"},
        {"field": "year", "description": "年度"},
        {"field": "period", "description": "期间"},
        {"field": "fi_document_number", "description": "财务凭证编号"},
        {"field": "archiv_doc_num", "description": "归档凭证号"},
        {"field": "external_sn", "description": "外部系统会计凭证号"}
    ]

    for post_type in push_type_list:
        print(post_type)
        if post_type in ['01', '02']:
            columns = '''   fc.`id`,
                            CASE fc.`ml_cal_type` WHEN '01' THEN '01-外购外协' WHEN '02' THEN '02-非外购外协' ELSE fc.`ml_cal_type` END AS `ml_cal_type`,
                            CASE fc.`posting_type` WHEN '01' THEN '01-周期价格还原' WHEN '02' THEN '02-消耗重估过账' ELSE fc.`posting_type` END AS `posting_type`,
                            fc.`company_code`,
                            tc.`company_description`,
                            fc.`plant_code`,
                            tp.`plant_description`,
                            fc.`year`,
                            fc.`period`,
                            fc.`fi_document_number`,
                            fr.`summary_unique_number`,
                            ft.`archiv_doc_num`,
                            ft.`external_sn` '''

            re_columns = '''fc.`id`,
                            CASE fc.`ml_cal_type` WHEN '01' THEN '01-外购外协' WHEN '02' THEN '02-非外购外协' ELSE fc.`ml_cal_type` END AS `ml_cal_type`,
                            CASE fc.`posting_type` WHEN '01' THEN '01-周期价格还原' WHEN '02' THEN '02-消耗重估过账' ELSE fc.`posting_type` END AS `posting_type`,
                            fc.`company_code`,
                            tc.`company_description`,
                            fc.`plant_code`,
                            tp.`plant_description`,
                            fc.`year`,
                            fc.`period`,
                            fc.`reversal_document` AS `fi_document_number`,
                            fr.`summary_unique_number`,
                            ft.`archiv_doc_num`,
                            ft.`external_sn` '''

            query_sql = f'''
                            (SELECT
                                {columns}
                            FROM
                                `t_fi_actual_cost_log` fc
                                LEFT JOIN `t_fi_integration_relation` fr ON fc.`company_code` = fr.`company_code` 
                                AND fc.`year` = fr.`year` AND fc.`period` = fr.`period` AND fc.`fi_document_number` = fr.`fi_document_number`
                                LEFT JOIN `t_fi_doc_for_archiv_transfer_log` ft ON ft.`company_code` = fr.`company_code` 
                                AND ft.`year` = fr.`year` AND ft.`summary_unique_number` = fr.`summary_unique_number`
                                LEFT JOIN `t_os_company` AS tc ON fc.`company_code` = tc.`company_code` 
                                LEFT JOIN `t_os_plant` AS tp ON fc.`plant_code` = tp.`plant_code`
                            WHERE
                              fc.`ml_cal_type` = '02' AND fc.`posting_type` = '{post_type}' AND fc.`fi_document_number` != '' 
                            '''
            re_query_sql = f'''
                        ) UNION (
                            SELECT
                                {re_columns}
                            FROM
                                `t_fi_actual_cost_log` fc
                                LEFT JOIN `t_fi_integration_relation` fr ON fc.`company_code` = fr.`company_code` 
                                AND fc.`year` = fr.`year` AND fc.`period` = fr.`period` AND fc.`reversal_document` = fr.`fi_document_number`
                                LEFT JOIN `t_fi_doc_for_archiv_transfer_log` ft ON ft.`company_code` = fr.`company_code` 
                                AND ft.`year` = fr.`year` AND ft.`summary_unique_number` = fr.`summary_unique_number` 
                                LEFT JOIN `t_os_company` AS tc ON fc.`company_code` = tc.`company_code`
                                LEFT JOIN `t_os_plant` AS tp ON fc.`plant_code` = tp.`plant_code`
                            WHERE
                              fc.`ml_cal_type` = '02' AND fc.`posting_type` = '{post_type}' AND fc.`reversal_document` != '' 
                        '''
            if not external_sn:
                query_sql += " AND ft.`external_sn` = '' "
                re_query_sql += " AND ft.`external_sn` = '' "

            table_alias = create_table_alias(columns)
            where_sql, sort_sql = generate_raw_sql(prefix_filter, {}, {}, table_alias)

            if not sort_sql:
                sort_sql = ' ORDER BY `fi_document_number` '
            if where_sql:
                where_sql = where_sql.replace('WHERE ', ' AND ')
                full_query_sql = query_sql + where_sql + re_query_sql + where_sql + ' ) ' + sort_sql
            else:
                full_query_sql = query_sql + ' ) ' + sort_sql
            full_query_sql = full_query_sql.replace('    ', ' ')
            print(full_query_sql)
            query_data = db_helper.query_sql(full_query_sql)

        elif post_type == '03':
            company_code = ''
            if 'plant_code' in prefix_filter:
                plant_code = prefix_filter.pop('plant_code')
                company_code = get_company_by_plant(plant_code)

            columns = '''
                            fr.`id`,
                            fr.`company_code`,
                            tc.`company_description`,
                            fr.`year`,
                            fr.`period`,
                            fr.`associated_doc_type`,
                            fr.`business_doc_sn`,
                            fr.`fi_document_number`,
                            fr.`summary_unique_number`,
                            fr.`posting_date`,
                            ft.`posting_status`,
                            ft.`archiv_doc_num`,
                            ft.`external_sn`,
                            ft.`note`
                            '''

            query_sql = f'''
                        SELECT
                            {columns}
                        FROM
                            `t_fi_integration_relation` fr
                        LEFT JOIN `t_fi_doc_for_archiv_transfer_log` ft ON ft.`company_code` = fr.`company_code` 
                            AND ft.`year` = fr.`year` AND ft.`summary_unique_number` = fr.`summary_unique_number` 
                        LEFT JOIN `t_os_company` AS tc ON fr.`company_code` = tc.`company_code`
                        WHERE
                            fr.`document_category` = 'MDOC' AND fr.`associated_doc_type`  = 'MD'
                    '''

            if company_code and isinstance(company_code, str):
                query_sql += f" AND fr.`company_code` = '{company_code}' "
            if not external_sn:
                query_sql += " AND ft.`external_sn` = '' "

            table_alias = create_table_alias(columns)
            where_sql, sort_sql = generate_raw_sql(prefix_filter, {}, {}, table_alias)
            if where_sql:
                where_sql = where_sql.replace('WHERE ', ' AND ')
                query_sql += where_sql + sort_sql
            else:
                query_sql += sort_sql
            query_sql = query_sql.replace('    ', ' ')
            print(query_sql)
            query_data = db_helper.query_sql(query_sql)

            display = [
                {"field": "company_code", "description": "公司代码"},
                {"field": "company_description", "description": "公司描述"},
                {"field": "year", "description": "年度"},
                {"field": "period", "description": "期间"},
                {"field": "associated_doc_type", "description": "物料凭证类型"},
                {"field": "business_doc_sn", "description": "物料凭证编号"},
                {"field": "fi_document_number", "description": "财务凭证编号"},
                {"field": "archiv_doc_num", "description": "归档凭证号"},
                {"field": "posting_status", "description": "外部系统过账状态"},
                {"field": "external_sn", "description": "外部系统会计凭证号"},
                {"field": "note", "description": "状态信息"}
            ]

        if post_type == '01':
            cp_list = query_data
            cp_display = display
        elif post_type == '02':
            cr_list = query_data
            cr_display = display
        elif post_type == '03':
            wp_list = query_data
            wp_display = display

    res_data = {
        'cp': cp_list,
        'cr': cr_list,
        'wp': wp_list,
    }

    total_display = {
        'cp': cp_display,
        'cr': cr_display,
        'wp': wp_display
    }

    return res_data, total_display


def NotOutsourceInventoryPushQuery():
    """非外购外协存货实际成本过账推送外部系统"""
    req = Request()
    res = Response()
    body = json.loads(req.body())
    data, display = not_outsource_inventory_push_query(body, external_sn=True)

    res.set_body(json.dumps({"code": 200, "msg": '成功', "data": data, "display": display}))
    res.commit(True)


def NotOutsourceInventorPushSAP():
    """
    非外购外协存货实际成本过账推送外部系统 按钮
    task_id 511
    """
    req = Request()
    res = Response()
    body = json.loads(req.body())
    user_id = req.header("user_id")
    post_type = body.get('post_type') or ''
    prefix_filter = body.get('data') or {}
    plant_code = prefix_filter.get('plant_code') or ''
    task_id = prefix_filter.get('task_id') or 511
    year = prefix_filter.get('year')
    period = prefix_filter.get('period')
    res_bus = NotOutsourceInventorPushSAPCore(user_id, task_id, year, period, plant_code, post_type)
    code = res_bus.get("code")
    msg = res_bus.get("msg")
    if 'post_type' in body:
        body.pop('post_type')
    total_data, total_display = not_outsource_inventory_push_query(body, external_sn=True)
    query_key = outsource_types.get(post_type) or ''
    data = total_data.get(query_key) or []
    display = total_display.get(query_key) or []
    for unique_key, query_data in total_data.items():
        if query_data:
            for item in query_data:
                external_sn = item.get('external_sn') or ''
                if not external_sn:
                    print(item)
                    break
    # 本次点击的推送sap按钮数据
    if data:
        for item in data:
            external_sn = item.get('external_sn') or ''
            if not external_sn:
                print(item)
                break
    res.set_body(json.dumps({"code": code, "msg": msg, "data": data, "display": display}))
    res.commit(True)


def NotOutsourceInventorPushSAPCore(user_id, task_id, year, period, plant_code, post_type=None):
    """ 511 core"""
    code, msg = 200, ''
    body = {"data": {"year": year, "period": period, "plant_code": plant_code}, "post_type": post_type}
    res_data, _ = outsource_inventory_query(body, external_sn=False)
    post_type_list = [post_type] if post_type else ["01", "02", "03"]
    for post_type in post_type_list:
        query_key = outsource_types.get(post_type) or ''
        query_data = res_data.get(query_key) or []
        resp_code_list = []
        if query_data:
            push_dict = {}
            for item in query_data:
                if push_dict.get(f"{item.get('archiv_doc_num')}|{item.get('summary_unique_number')}"):
                    continue
                else:
                    push_dict[f"{item.get('archiv_doc_num')}|{item.get('summary_unique_number')}"] = item
                external_sn = item.get('external_sn') or ''
                if not external_sn:
                    code, each_msg = ZZEXTNotOutsourceInventorPushSAP(user_id, task_id, plant_code, item)
                    resp_code_list.append(code)
                    if code != 200:
                        msg = each_msg
    return {"code": code, "msg": msg}


def NotOutsourceInventoryMenu():
    """非外购外协存货实际成本过账推送外部系统 筛选、过滤、下载"""
    req = Request()
    res = Response()
    body = json.loads(req.body())
    payload = body.get('_payload_', {})
    filter_info = payload.get('filter_info', {})
    sort_info = payload.get('sort_info', {})
    export_excel = payload.get('export_excel')
    post_type = body.get('post_type')

    total_data, total_display = not_outsource_inventory_push_query(body, external_sn=True)
    query_key = outsource_types.get(post_type) or ''
    query_data = total_data.get(query_key) or []
    display = total_display.get(query_key) or []

    if query_data:
        if filter_info:
            query_data = filter_data(query_data, filter_info)  # 筛选过滤

        if sort_info:
            query_data = sort_data(query_data, sort_info)

    if export_excel:
        timestamp = datetime.now()
        stamp_suffix = timestamp.strftime('%Y%m%d%H%M%S')
        excel_filename = f'非外购外协存货实际成本过账推送外部系统-{stamp_suffix}.xlsx'
        format_data = [{'sheet1': query_data}]
        field_dict = display_to_entozh(display)
        GetExportData(format_data, excel_filename, field_dict)
    else:
        res.set_body(json.dumps({"code": 200, "msg": "成功", "data": query_data, "display": display}))
        res.commit(True)


def CostCenterCheckConfigQuery():
    """制造成本中心类型配置表 查询"""
    res = Response()
    req = Request()
    body = json.loads(req.body())
    param = body.get('_payload_') or {}
    prefix_filter = body.get('data') or {}
    filter_info = param.get('filter_info') or {}
    sort_info = param.get('sort_info') or {}
    export_excel = param.get('export_excel')

    query_data = []
    db_helper = DbHelper()
    exp_columns = '''
                    t1.`id`,
                    t1.`cost_center_type`,
                    t1.`cost_center_type_description`,
                    t1.`expense_type`,
                    t1.`expense_type_description`,
                    u1.`name` AS `create_name`,
                    t1.`create_time`,
                    u2.`name` AS `update_name`,
                    t1.`update_time`,
                    t1.`note` '''

    query_columns = '''
                    t1.`create_id`,
                    t1.`update_id` 
                    '''

    if export_excel:
        columns = exp_columns
    else:
        columns = exp_columns.strip() + ',' + query_columns

    query_sql = '''
                SELECT {}
                FROM
                    `t_cost_center_check` t1
                    LEFT JOIN `t_system_user` AS u1 ON t1.`create_id` = u1.`id`
                    LEFT JOIN `t_system_user` AS u2 ON t1.`update_id` = u2.`id`
                '''.format(columns)

    table_alias = create_table_alias(columns)
    where_sql, sort_sql = generate_raw_sql(prefix_filter, filter_info, sort_info, table_alias)
    query_sql += where_sql + sort_sql
    query_sql = query_sql.replace('    ', ' ')

    page_size = param.get('page', {}).get('page_size', 0)
    page_num = param.get('page', {}).get('page_num', 1)
    query_data = db_helper.query_sql(query_sql)
    paginator = Paginator(query_data, page_size)
    page_items = paginator.get_page(page_num)
    total_pages = paginator.total_pages
    data_sum = len(query_data)

    display = [
        {"field": "cost_center_type", "description": "成本中心类型"},
        {"field": "cost_center_type_description", "description": "成本中心类型描述"},
        {"field": "expense_type", "description": "费用类型"},
        {"field": "expense_type_description", "description": "费用类型描述"},
        {"field": "create_name", "description": "创建人"},
        {"field": "create_time", "description": "创建时间"},
        {"field": "update_name", "description": "更新人"},
        {"field": "update_time", "description": "更新时间"},
        {"field": "note", "description": "备注"}
    ]

    if export_excel:
        timestamp = datetime.now()
        stamp_suffix = timestamp.strftime('%Y%m%d%H%M%S')
        excel_filename = f'制造成本中心类型配置-{stamp_suffix}.xlsx'
        format_data = [{'sheet1': query_data}]
        field_dict = display_to_entozh(display)
        GetExportData(format_data, excel_filename, field_dict)
    else:
        response = {
            "code": 200,
            "msg": "成功",
            "data": page_items,
            "page": {
                "page_size": page_size if page_size else len(query_data),  # 每页数据行数
                "page_num": page_num,  # 当前页
                "page_sum": total_pages,  # 总页数
                "data_sum": data_sum  # 总数据行数
            },
            "rule": {
                "sort_info": sort_info,
                "filter_info": filter_info
            },
            "display": display
        }

        res.set_body(json.dumps(response, cls=SuperEncoder))
        res.commit(True)


def SaveCostCenterCheckConfig():
    """制造成本中心类型配置表 保存"""
    import datetime as dt
    update_time = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    res = Response()
    req = Request()
    body = json.loads(req.body())
    user_id = req.header("user_id")
    data = body.get("data")
    msg = '保存成功'
    for row_num, item in enumerate(data, start=1):
        tag = item.get("_tag_", "")
        row_id = item.get("id")
        cost_center_type = item.get("cost_center_type") or ''
        cost_center_type_description = item.get("cost_center_type_description") or ''
        expense_type = item.get("expense_type") or ''
        expense_type_description = item.get("expense_type_description") or ''
        note = item.get("note") or ''
        if not row_id and tag in ["update", "delete"]:
            continue
        if tag == "delete":
            delete_sql = f'DELETE FROM `t_cost_center_check` WHERE `id` = {row_id}'
            if db_helper.exec_sql(delete_sql) < 0:
                res_body = json.dumps({"code": 206, "msg": f"删除制造成本中心类型配置表 第{row_num}行失败!"})
                res.set_body(res_body)
                res.commit(True)
                return
            else:
                msg = '删除成功'
        elif tag == "insert":
            insert_sql = f"""
                INSERT INTO `t_cost_center_check` (`cost_center_type`, `cost_center_type_description`, `expense_type`, `expense_type_description`, `create_id`, `update_id`, `note` ) VALUES
                ('{cost_center_type}', '{cost_center_type_description}', '{expense_type}', '{expense_type_description}', {user_id}, {user_id}, '{note}'); """
            if db_helper.exec_sql(insert_sql) < 0:
                res_body = json.dumps({"code": 206, "msg": f"新增制造成本中心类型配置表 第{row_num}行失败!"})
                res.set_body(res_body)
                res.commit(True)
                return
        elif tag == "update":
            cost_center_type = item.get("cost_center_type") or ''
            cost_center_type_description = item.get("cost_center_type_description") or ''
            expense_type = item.get("expense_type") or ''
            expense_type_description = item.get("expense_type_description") or ''
            note = item.get("note") or ''
            update_sql = f"""
                        UPDATE `t_cost_center_check` 
                        SET `cost_center_type` = '{cost_center_type}',
                            `cost_center_type_description` = '{cost_center_type_description}',
                            `expense_type` = '{expense_type}',
                            `expense_type_description` = '{expense_type_description}',
                            `note` = '{note}',
                            `update_id` = {user_id},
                            `update_time` = '{update_time}'
                        WHERE
                            `id` = {row_id};
                        """
            if db_helper.exec_sql(update_sql) < 0:
                res_body = json.dumps({"code": 206, "msg": f"修改制造成本中心类型配置表 第{row_num}行失败!"})
                res.set_body(res_body)
                res.commit(True)
                return

    res.set_body(json.dumps({"code": 200, "msg": msg, "data": ""}))
    res.commit(True)


def get_all_group_range():
    """关联t_co_assemble-group_id，获取group_from和group_to范围内的所有编码作为成本中心"""
    global all_cost_center_group, all_cost_center_range

    query_sql = '''
        SELECT
            `group_code`,
            `origin_field` AS `group_field`,
            `group_from`,
            `group_to`
        FROM
            `t_co_assemble`
        WHERE `origin_field` in ('cost_center', 'group_id')
    '''
    result_data = db_helper.query_sql(query_sql)
    # print('get_all_group_range :', result_data)
    for item in result_data:
        group_field = item.get('group_field') or ''
        group_id = item.get('group_code') or ''
        group_range = {
            'group_field': item.get('group_field') or '',
            'group_from': item.get('group_from') or '',
            'group_to': item.get('group_to') or ''
        }
        if group_field == 'cost_center':
            if group_id not in all_cost_center_range:
                all_cost_center_range[group_id] = [group_range]
            else:
                all_cost_center_range[group_id].append(group_range)
        elif group_field == 'group_id':
            if group_id not in all_cost_center_group:
                all_cost_center_group[group_id] = [group_range]
            else:
                all_cost_center_group[group_id].append(group_range)


def get_group_range_by_id(group_id):
    """根据 group_id 获取t_co_assemble 中 group_from和group_to范围内的所有编码作为成本中心进行数据匹配"""

    the_group_range = []
    if group_id in all_cost_center_range:
        group_ranges = all_cost_center_range[group_id]
        for group_range in group_ranges:
            from_group_id = group_range['group_from']
            to_group_id = group_range['group_to']
            group_field = group_range['group_field']
            if group_field == 'group_id':
                if from_group_id in all_cost_center_group:
                    from_cost_center_range = all_cost_center_group.get(from_group_id)
                    the_group_range += from_cost_center_range
                if to_group_id in all_cost_center_group:
                    to_cost_center_range = all_cost_center_group.get(to_group_id)
                    the_group_range += to_cost_center_range
            else:
                the_group_range += group_ranges

    if group_id in all_cost_center_group:
        cost_center_range = all_cost_center_group.get(group_id)
        the_group_range += cost_center_range

    return the_group_range


def get_assignment_rule_info():
    """
        分配规则清单明细获取
        从t_ea_assignment_weight_item2表获取assignment_objects or assignment_objects2费用分配方和receiving_objects费用接收方、
        assignment_rule_id分配规则、rule_id_item分配规则项, 从t_ea_assignment_weight_header获得rule_id_description
    """

    query_sql = '''
        SELECT
            ai.`assignment_objects`,
            ai.`assignment_objects2`,
            ai.`assignment_objects_type`,
            ai.`assignment_objects_type2`,
            ai.`receiving_objects`,
            ai.`receiving_objects_type`,
            ai.`assignment_rule_id`,
            ah.`rule_id_description`,
            ai.`rule_id_item`
        FROM
            `t_ea_assignment_weight_item2` ai
        LEFT JOIN `t_ea_assignment_weight_header` ah ON ai.`assignment_rule_id` = ah.`assignment_rule_id`
    '''
    result_data = db_helper.query_sql(query_sql)
    assign_object_list, receiving_object_list = [], []
    assign_objects_info, receiving_objects_info, assign_object_group, receiving_object_group = {}, {}, {}, {}

    get_all_group_range()  # 获取所有的group范围
    for item in result_data:
        assignment_objects = item.get('assignment_objects') or ''
        assignment_objects2 = item.get('assignment_objects2') or ''
        assignment_objects_type = item.get('assignment_objects_type') or ''
        assignment_objects_type2 = item.get('assignment_objects_type2') or ''
        receiving_objects = item.get('receiving_objects') or ''
        receiving_objects_type = item.get('receiving_objects_type') or ''
        if assignment_objects_type == 'C01':
            if '|' in assignment_objects:
                assignment_object = assignment_objects.split('|')[0]
                assign_object_list.append(assignment_object)
                assign_objects_info[assignment_object] = item
        elif assignment_objects_type == 'C06':
            if '|' in assignment_objects:
                assignment_group_id = assignment_objects.split('|')[0]
                # 表里格式为CG01|CG01，关联t_co_assemble-group_id,获取group_from和group_to范围内的所有编码作为成本中心进行数据匹配
                cost_center_group = get_group_range_by_id(assignment_group_id)
                assign_object_group[assignment_group_id] = cost_center_group
                assign_objects_info[assignment_group_id] = item

        if assignment_objects_type2 == 'C01':
            if '|' in assignment_objects2:
                assignment_object2 = assignment_objects2.split('|')[0]
                assign_object_list.append(assignment_object2)
                assign_objects_info[assignment_object2] = item
        elif assignment_objects_type2 == 'C06':
            if '|' in assignment_objects2:
                assignment_group_id = assignment_objects2.split('|')[0]
                cost_center_group = get_group_range_by_id(assignment_group_id)
                assign_object_group[assignment_group_id] = cost_center_group
                assign_objects_info[assignment_group_id] = item

        if receiving_objects_type == 'C01':
            if '|' in receiving_objects:
                receiving_object = receiving_objects.split('|')[0]
                receiving_object_list.append(receiving_object)
                receiving_objects_info[receiving_object] = item
        elif receiving_objects_type == 'C06':
            if '|' in receiving_objects:
                receiving_group_id = receiving_objects.split('|')[0]
                cost_center_group = get_group_range_by_id(receiving_group_id)
                receiving_object_group[receiving_group_id] = cost_center_group
                receiving_objects_info[receiving_group_id] = item

    cost_center_info = {
        'assign_object_list': assign_object_list,
        'assign_objects': assign_objects_info,
        'assign_object_group': assign_object_group,
        'receiving_object_list': receiving_object_list,
        'receiving_objects': receiving_objects_info,
        'receiving_object_group': receiving_object_group,
    }

    return cost_center_info


def get_cost_work_center_info():
    """
    制造成本中心划分：根据制造成本中心清单从t_co_work_center_main_data获取work_center, 如果可以获取到 work_center,
    则标记为费用接收方, 否则标记为费用分配方
    """

    query_sql = '''
        SELECT
            `cost_center`,
            `work_center`
        FROM
            `t_co_work_center_main_data`
    '''
    result_data, cost_work_center_info = [], {}
    result_data = db_helper.query_sql(query_sql)
    for item in result_data:
        cost_center = item.get('cost_center') or ''
        work_center = item.get('work_center') or ''
        if cost_center and work_center:
            cost_work_center_info[cost_center] = work_center

    return cost_work_center_info


def get_dynamic_table_names(table_name):
    """
    动态获取以 xxx前缀表的名字
    :return:
    """

    all_table = db_helper.get_tables_like_only_name(table_name, '', '')

    return all_table


def get_amount_summary(cost_center_list, year, period, company_code, price_mark):
    """
    待分配金额 汇总, document_detail_table_name_公司代码_年度期间 分区表 status=3 并且price_mark=04所有的amount_dc_mark汇总
    :param cost_center_list: 分配方标记=0和接收方标记=0的所有成本中心列表
    :param year: 年度
    :param period: 期间
    :param company_code: 公式代码, 通过工厂转换t_os_company_plant_alloc获取
    :return:
    """
    result_data, cost_center_info = [], {}
    if not cost_center_list:
        return cost_center_info
    document_detail_table_name = ''
    if price_mark == "01":
        document_detail_table_name = "t_co_document_detail_plan"
    elif price_mark == "04":
        document_detail_table_name = "t_co_document_detail_acture"
    where_sql = ''
    if year:
        where_sql += f' AND rd.`year` = {repr(year)} '
    if period:
        where_sql += f' AND rd.`period` = {repr(period)} '
    if company_code:
        where_sql += f' AND rd.`company_code` = {repr(company_code)} '
    if cost_center_list:
        cost_center_range = ', '.join(map(repr, cost_center_list)).strip(',')
        where_sql += f' AND rd.`cost_center` IN ({cost_center_range})  '

    sql_list = []
    table_names = get_dynamic_table_names(f'{document_detail_table_name}_')
    for table_name in table_names:
        query_sql = f'''
                SELECT
                    rd.`cost_center`,
                    rd.`expense_type`,
                    rd.`amount_dc_mark`
                FROM
                    `{table_name}` rd
                LEFT JOIN `t_cost_center_check` cc ON cc.`expense_type` = rd.`expense_type`
                WHERE rd.`status` = '3' and rd.`price_mark` = '04' {where_sql}
            '''
        sql_list.append(query_sql)

    if sql_list:
        union_query_sql = ' UNION ALL '.join(sql_list)
        print(union_query_sql)
        result_data = db_helper.query_sql(union_query_sql)
        for item in result_data:
            cost_center = item.get('cost_center') or ''
            amount_dc_mark = item.get('amount_dc_mark') or 0
            if cost_center not in cost_center_info:
                cost_center_info[cost_center] = amount_dc_mark
            else:
                cost_center_info[cost_center] += amount_dc_mark

    print(cost_center_info)
    return cost_center_info


def cost_center_data_process(query_data, year, period):
    """成本中心字段处理"""
    if not query_data:
        return query_data

    query_data = [dict(t) for t in {tuple(d.items()) for d in query_data}]  # 去重
    cost_work_center_info = get_cost_work_center_info()  # 制造成本中心划分
    assignment_rule_info = get_assignment_rule_info()
    # print('cost_work_center_info:', json.dumps(cost_work_center_info, indent=4))
    # print('assignment_rule_info:', json.dumps(assignment_rule_info, indent=4))
    assign_object_list = assignment_rule_info.get('assign_object_list')
    assign_objects = assignment_rule_info.get('assign_objects')
    assign_object_group = assignment_rule_info.get('assign_object_group')
    receiving_object_list = assignment_rule_info.get('receiving_object_list')
    receiving_objects = assignment_rule_info.get('receiving_objects')
    receiving_object_group = assignment_rule_info.get('receiving_object_group')

    # 制造成本中心划分
    for row in query_data:
        row['year'] = year
        row['period'] = period
        cost_center = row.get('cost_center') or ''
        work_center = cost_work_center_info.get(cost_center) or ''
        # print('cost_center:', cost_center, 'work_center:', work_center)
        row['unallocated_amount'] = 0
        if work_center:
            # row['mark'] = '费用接收方'
            row['receiving_objects_mark'] = '0'
            if cost_center in receiving_object_list:
                row['receiving_objects_mark'] = '1'
                this_cost_center_info = receiving_objects.get(cost_center) or {}
                assignment_rule_id = this_cost_center_info.get('assignment_rule_id') or ''
                rule_id_item = this_cost_center_info.get('rule_id_item') or ''
                rule_id_description = this_cost_center_info.get('rule_id_description') or ''
                row['assignment_rule_id'] = assignment_rule_id
                row['rule_id_item'] = rule_id_item
                row['rule_id_description'] = rule_id_description
            else:
                find_in_group = False
                for group_id, group_ranges in receiving_object_group.items():
                    for each_group in group_ranges:
                        group_from = each_group.get('group_from') or ''
                        group_to = each_group.get('group_to') or ''
                        if group_from <= cost_center <= group_to:
                            row['receiving_objects_mark'] = '1'
                            this_cost_center_info = receiving_objects.get(group_id) or {}
                            assignment_rule_id = this_cost_center_info.get('assignment_rule_id') or ''
                            rule_id_item = this_cost_center_info.get('rule_id_item') or ''
                            rule_id_description = this_cost_center_info.get('rule_id_description') or ''
                            row['assignment_rule_id'] = assignment_rule_id
                            row['rule_id_item'] = rule_id_item
                            row['rule_id_description'] = rule_id_description
                            find_in_group = True
                            break
                    if find_in_group:
                        break
        else:
            # row['mark'] = '费用分配方'
            row['assignment_objects_mark'] = '0'
            if cost_center in assign_object_list:
                row['assignment_objects_mark'] = '1'
                this_cost_center_info = assign_objects.get(cost_center) or {}
                assignment_rule_id = this_cost_center_info.get('assignment_rule_id') or ''
                rule_id_item = this_cost_center_info.get('rule_id_item') or ''
                rule_id_description = this_cost_center_info.get('rule_id_description') or ''
                row['assignment_rule_id'] = assignment_rule_id
                row['rule_id_item'] = rule_id_item
                row['rule_id_description'] = rule_id_description
            else:
                find_in_group = False
                for group_id, group_ranges in assign_object_group.items():
                    for each_group in group_ranges:
                        group_from = each_group.get('group_from') or ''
                        group_to = each_group.get('group_to') or ''
                        if group_from <= cost_center <= group_to:
                            row['assignment_objects_mark'] = '1'
                            this_cost_center_info = assign_objects.get(group_id) or {}
                            assignment_rule_id = this_cost_center_info.get('assignment_rule_id') or ''
                            rule_id_item = this_cost_center_info.get('rule_id_item') or ''
                            rule_id_description = this_cost_center_info.get('rule_id_description') or ''
                            row['assignment_rule_id'] = assignment_rule_id
                            row['rule_id_item'] = rule_id_item
                            row['rule_id_description'] = rule_id_description
                            find_in_group = True
                            break
                    if find_in_group:
                        break

    return query_data


def save_center_data_check_log(query_data, year, period, company_code, user_id, price_mark, res=None):
    """
    筛选出所有分配方标记=0和接收方标记=0的成本中心, 待分配金额汇总,
    :param query_data: 筛选分配方标记=0和接收方标记=0的所有成本中心
    :param year: 年度
    :param period: 期间
    :param company_code: 公式代码
    :param user_id: 用户id
    :param res:
    :return:
    """
    save_result = False
    if query_data:
        un_alloc_cost_centers = []
        for row in query_data:
            cost_center = row.get('cost_center')
            assignment_mark = row.get('assignment_objects_mark')
            receiving_mark = row.get('receiving_objects_mark')
            if assignment_mark != '1' and receiving_mark != '1':
                un_alloc_cost_centers.append(cost_center)

        unallocated_amount_info = get_amount_summary(un_alloc_cost_centers, year, period, company_code, price_mark)
        for row in query_data:
            cost_center = row.get('cost_center')
            assignment_mark = row.get('assignment_objects_mark')
            receiving_mark = row.get('receiving_objects_mark')
            if assignment_mark != '1' and receiving_mark != '1':
                unallocated_amount = unallocated_amount_info.get(cost_center) or 0
                row['unallocated_amount'] = unallocated_amount
        save_result = save_cost_center_check(query_data, user_id, res)
    else:
        save_result = True

    return save_result


def cost_center_check_task_query(year, period, plant_code):
    """
    制造费用成本中心检查查询, 获取制造成本中心清单
    :param year: 月结任务 年度
    :param period: 月结任务 期间
    :param plant_code: 月结任务 工厂代码
    :return:
    """
    company_code, where_sql = '', ''
    if plant_code:
        company_code = get_company_by_plant(plant_code)
        if company_code and isinstance(company_code, str):
            where_sql += f" AND t1.`company_code` = '{company_code}' "

    if year and period:
        construct_date = f'{year}-{period}-01'
        where_sql += f' AND t1.`effective_start_date` <= {repr(construct_date)} and t1.`effective_end_date` >= {repr(construct_date)}'

    columns = '''   t1.`id`,
                    t1.`company_code`,
                    t1.`cost_center`,
                    t1.`cost_center_status`,
                    t1.`cost_center_description`
                    '''

    query_sql = f'''
            SELECT
                {columns}
            FROM
                `t_coc_cost_center` t1
            JOIN `t_cost_center_check` t2 ON t1.`cost_center_type` = t2.`cost_center_type` AND t1.`expense_type` = t2.`expense_type`
            WHERE 1 
        '''

    if where_sql:
        where_sql = where_sql.replace('WHERE ', ' AND ')
        query_sql += where_sql

    query_sql = query_sql.replace('    ', ' ')
    query_data = db_helper.query_sql(query_sql)
    print(query_sql)

    return query_data, company_code


def delete_old_check_result(year, period, company_code):
    deleted_mark = True
    if not year or not period or not company_code:
        return deleted_mark

    delete_sql = " DELETE FROM `t_cost_center_check_log` "
    where_sql = f" WHERE `year` = '{year}' AND `period` = '{period}' AND `company_code` = '{company_code}' "
    delete_sql += where_sql
    db_helper.exec_sql(delete_sql)

    return deleted_mark


def save_cost_center_check(data, user_id, res=None):
    """制造费用成本中心检查 保存"""

    insert_result = True
    insert_header_sql = '''
        INSERT INTO `t_cost_center_check_log` (`year`, `period`, `company_code`, `cost_center`, `cost_center_description`, 
        `assignment_objects_mark`, `receiving_objects_mark`, `assignment_mark`, `cost_center_status`, 
        `assignment_rule_id`, `rule_id_description`, `rule_id_item`, `unallocated_amount`,`create_id`, `update_id`, `note` ) VALUES 
        '''

    batch_insert_sql = insert_header_sql.strip()
    year, period, company_code = '', '', ''
    for row_num, record in enumerate(data, start=1):
        year = record.get('year') or ''
        period = record.get('period') or ''
        company_code = record.get('company_code') or ''
        cost_center = record.get('cost_center') or ''
        cost_center_description = record.get('cost_center_description') or ''
        assignment_objects_mark = record.get('assignment_objects_mark') or ''
        receiving_objects_mark = record.get('receiving_objects_mark') or ''
        assignment_mark = record.get('assignment_mark') or ''
        cost_center_status = record.get('cost_center_status') or ''
        assignment_rule_id = record.get('assignment_rule_id') or ''
        rule_id_description = record.get('rule_id_description') or ''
        rule_id_item = record.get('rule_id_item') or ''
        unallocated_amount = record.get('unallocated_amount') or 0
        note = record.get('note') or ''
        insert_item = (
            f"('{year}', '{period}', '{company_code}', '{cost_center}', '{cost_center_description}', '{assignment_objects_mark}', "
            f"'{receiving_objects_mark}', '{assignment_mark}', '{cost_center_status}', '{assignment_rule_id}', '{rule_id_description}', '{rule_id_item}', {unallocated_amount}, {user_id}, {user_id}, '{note}'), ")
        batch_insert_sql += insert_item + '\n'

    try:
        if batch_insert_sql != insert_header_sql.strip():
            delete_old_check_result(year, period, company_code)
            batch_insert_sql = batch_insert_sql.strip().rstrip(', ') + ' ; '
            if db_helper.exec_sql(batch_insert_sql) < 0:
                if res:
                    res_body = json.dumps({"code": 206, "msg": f"新增制造费用成本中心检查结果失败!"})
                    res.set_body(res_body)
                    res.commit(True)
                    return
                insert_result = False
    except Exception as e:
        print(str(e))
        insert_result = False

    return insert_result


def retry_on_true(max_attempts=3):
    """
    装饰器：当函数返回True时终止，否则重试最多max_attempts次
    参数:
        max_attempts (int): 最大尝试次数，默认为3
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result = None
            for attempt in range(max_attempts):
                result = func(*args, **kwargs)
                if result:  # 如果函数返回True则终止循环
                    print(f"在第 {attempt + 1} 次尝试成功")
                    return result

            print(f"经过 {max_attempts} 次尝试仍未成功")
            return result  # 返回最后一次结果

        return wrapper

    return decorator


# 应用装饰器
@retry_on_true(max_attempts=3)
def update_task_state(task_code, step, task_id, status):
    """更改本次任务的运行状态
    步骤状态 1.未开始 2.进行中 3.出错 4.成功  int 类型
    """
    result = True
    try:
        if task_id and task_code and step:
            db_helper = DbHelper()  # 使用函数内DbHandler, 保证内部提交
            update_status_sql = "UPDATE `t_co_monthly_procedure` SET `status` = {} WHERE `task_id` = {} AND `task_code` = '{}' AND `step` = '{}' ;".format(
                status, task_id, task_code, step)
            update_status = db_helper.exec_sql(update_status_sql)
            if update_status and update_status < 0:
                result = False
            else:
                result = True
    except Exception as e:
        print(str(e))
        result = False

    return result


def cost_center_check_task(year, period, plant_code, user_id, price_mark):
    """制造费用成本中心检查 方法"""

    try:
        data, company_code = cost_center_check_task_query(year, period, plant_code)
        data = cost_center_data_process(data, year, period)
        save_result = save_center_data_check_log(data, year, period, company_code, user_id, price_mark)
        if not save_result:
            return {"code": 400, "msg": f""}

        else:
            return {"code": 200, "msg": f"success"}
    except Exception as e:
        print(str(e))
        log_code = '030031016'
        detail = {
            'input': {
                'year': year,
                'period': period,
                'plant_code': plant_code,
                'user_id': user_id
            },
            'output': '',
        }
        LoggerConfig.logToDB(log_code, '', LogLevel.ERROR, f'制造费用成本中心检查:{str(e)}',
                             detail, plant_code)
        return {"code": 400, "msg": f"制造费用成本中心检查:{str(e)}"}


def delete_cost_center_result(year, period, plant_code, task_id):
    """
    点击重置时，将状态变为未开始，t_cost_center_check_log该表相应年度、期间、公司代码对应的数据删除
    :param year: 月结任务 年度
    :param period: 月结任务 期间
    :param plant_code: 月结任务 工厂代码
    :param task_code: 月结任务
    :param task_id: 任务id
    :param step: 当前月结任务的月结步骤
    :param user_id: 用户id
    :return:
    """
    if task_id == 527:
        if not year or not period or not plant_code:
            print('年月、工厂代码 三者不能为空')
            return
        delete_sql = " DELETE FROM `t_cost_center_check_log` "
        where_sql = f" WHERE `year` = '{year}' AND `period` = '{period}' "
        company_code = get_company_by_plant(plant_code)
        if company_code and isinstance(company_code, str):
            where_sql += f" AND `company_code` = '{company_code}' "

        if not year or not period or not company_code:
            print('年月、公司代码 三者不能为空')
        else:
            db_helper.exec_sql(delete_sql)


def filter_by_group_range(total_group_range, cost_center):
    """根据筛选条件得筛选范围，判断 cost_center 是否符合筛选条件"""
    valid = False
    if not total_group_range:
        return True
    for group in total_group_range:
        group_from = group.get('group_from')
        group_to = group.get('group_to')
        if group_from and group_to:
            if group_from <= cost_center <= group_to:
                valid = True
                break

    return valid


def get_cost_center_task_info(data):
    task_code, step = '', ''
    if 'task_code' in data:
        task_code = data.pop('task_code')
    if 'step' in data:
        step = data.pop('step')

    valid_fields = ['year', 'period', 'company_code', 'cost_center', 'cost_center_group']
    filter_condition = {field: data.get(field) for field in valid_fields}

    return filter_condition, task_code, step


def CostCenterCheckAllocatedQuery():
    """制造费用成本中心检查结果 查询"""
    res = Response()
    req = Request()
    body = json.loads(req.body())
    prefix_filter = body.get('data', {})
    prefix_filter, task_code, step = get_cost_center_task_info(prefix_filter)

    param = body.get('_payload_', {})
    filter_info = param.get('filter_info', {})
    sort_info = param.get('sort_info', {})
    export_excel = param.get('export_excel')
    company_code = prefix_filter.get('company_code') or ''
    if 'plant_code' in prefix_filter:
        plant_code = prefix_filter.pop('plant_code')
        if not company_code:
            company_code = get_company_by_plant(plant_code)

    total_group_range = []
    get_all_group_range()  # 获取所有的group范围
    if 'cost_center_group' in prefix_filter:
        cost_center_group = prefix_filter.pop('cost_center_group')
        if cost_center_group:
            for each_group_id in cost_center_group:
                total_group_range += get_group_range_by_id(each_group_id)
    # print('total_group_range :', total_group_range)

    columns = '''
                t1.`year`,
                t1.`period`,
                t1.`company_code`,
                t1.`cost_center`,
                t1.`cost_center_description`,
                t1.`assignment_objects_mark`,
                t1.`receiving_objects_mark`,
                t1.`assignment_mark`,
                t1.`cost_center_status`,
                t1.`assignment_rule_id`,
                t1.`rule_id_description`,
                t1.`rule_id_item`,
                t1.`unallocated_amount`
            '''

    query_sql = f'''
                SELECT 
                    {columns}
                FROM
                    `t_cost_center_check_log` t1
                '''

    table_alias = create_table_alias(columns)
    where_sql, sort_sql = generate_raw_sql(prefix_filter, filter_info, sort_info, table_alias)
    if company_code and isinstance(company_code, str) and 'company_code' not in where_sql:
        where_sql += f" AND t1.`company_code` = '{company_code}' "
    query_sql += where_sql + sort_sql
    query_sql = query_sql.replace('    ', ' ')
    print(query_sql)
    query_data = db_helper.query_sql(query_sql)
    allocated_data, unallocated_data = [], []
    if query_data:
        for item in query_data:
            cost_center = item.get('cost_center')
            result = filter_by_group_range(total_group_range, cost_center)
            if result:
                assignment_mark = item.get('assignment_objects_mark')
                receiving_mark = item.get('receiving_objects_mark')
                cost_center_status = item.get('cost_center_status')
                if assignment_mark == '1' or receiving_mark == '1':
                    alloc_category = ''
                    if assignment_mark == '1':
                        alloc_category = '分配方'
                    elif receiving_mark == '1':
                        alloc_category = '接收方'
                    allocated_item = {
                        'assignment_rule_id': item.get('assignment_rule_id'),
                        'rule_id_description': item.get('rule_id_description'),
                        'rule_id_item': item.get('rule_id_item'),
                        'cost_center': cost_center,
                        'cost_desc': item.get("cost_center_description"),
                        'allocate_category': alloc_category,
                        'is_frozen': '冻结' if cost_center_status == '3' else '正常',
                        'message': '成本中心状态为冻结，影响费用分配' if cost_center_status == '3' else '正常',
                    }
                    allocated_data.append(allocated_item)

    if allocated_data:
        if filter_info:
            allocated_data = filter_data(allocated_data, filter_info)
        if sort_info:
            allocated_data = sort_data(allocated_data, sort_info)

    display = [
        {"field": "assignment_rule_id", "description": "分配规则"},
        {"field": "rule_id_description", "description": "分配规则描述"},
        {"field": "rule_id_item", "description": "分配项规则"},
        {"field": "cost_center", "description": "成本中心"},
        {"field": "cost_desc", "description": "成本中心描述"},
        {"field": "allocate_category", "description": "分配归属"},
        {"field": "is_frozen", "description": "是否冻结"},
        {"field": "message", "description": "提醒信息"},
    ]

    if export_excel:
        timestamp = datetime.now()
        stamp_suffix = timestamp.strftime('%Y%m%d%H%M%S')
        excel_filename = f'已分配成本中心结果-{stamp_suffix}.xlsx'
        format_data = [{'allocated': allocated_data}]
        field_dict = display_to_entozh(display)
        GetExportData(format_data, excel_filename, field_dict)
    else:
        response = {
            "code": 200,
            "msg": "成功",
            "data": allocated_data,
            "display": display
        }

        res.set_body(json.dumps(response, cls=SuperEncoder))
        res.commit(True)


def CostCenterCheckUnallocatedQuery():
    """制造费用成本中心检查结果 查询"""
    res = Response()
    req = Request()
    body = json.loads(req.body())
    prefix_filter = body.get('data', {})
    prefix_filter, task_code, step = get_cost_center_task_info(prefix_filter)

    param = body.get('_payload_', {})
    filter_info = param.get('filter_info', {})
    sort_info = param.get('sort_info', {})
    export_excel = param.get('export_excel')
    company_code = prefix_filter.get('company_code') or ''
    if 'plant_code' in prefix_filter:
        plant_code = prefix_filter.pop('plant_code')
        if not company_code:
            company_code = get_company_by_plant(plant_code)

    total_group_range = []
    get_all_group_range()  # 获取所有的group范围
    if 'cost_center_group' in prefix_filter:
        cost_center_group = prefix_filter.pop('cost_center_group')
        if cost_center_group:
            for each_group_id in cost_center_group:
                total_group_range += get_group_range_by_id(each_group_id)

    print('total_group_range :', total_group_range)
    columns = '''
                t1.`year`,
                t1.`period`,
                t1.`company_code`,
                t1.`cost_center`,
                t1.`cost_center_description`,
                t1.`assignment_objects_mark`,
                t1.`receiving_objects_mark`,
                t1.`assignment_mark`,
                t1.`cost_center_status`,
                t1.`assignment_rule_id`,
                t1.`rule_id_description`,
                t1.`rule_id_item`,
                t1.`unallocated_amount` '''

    query_sql = f'''
                SELECT 
                    {columns}
                FROM
                    `t_cost_center_check_log` t1
                '''

    table_alias = create_table_alias(columns)
    where_sql, sort_sql = generate_raw_sql(prefix_filter, filter_info, sort_info, table_alias)
    if company_code and isinstance(company_code, str) and 'company_code' not in where_sql:
        where_sql += f" AND t1.`company_code` = '{company_code}' "
    query_sql += where_sql + sort_sql
    query_sql = query_sql.replace('    ', ' ')
    print(query_sql)
    query_data = db_helper.query_sql(query_sql)
    allocated_data, unallocated_data = [], []
    if query_data:
        for item in query_data:
            cost_center = item.get('cost_center')
            result = filter_by_group_range(total_group_range, cost_center)
            if result:
                assignment_mark = item.get('assignment_objects_mark')
                receiving_mark = item.get('receiving_objects_mark')

                if assignment_mark == '0' or receiving_mark == '0':
                    alloc_category = ''
                    if assignment_mark == '0':
                        alloc_category = '分配方'
                    elif receiving_mark == '0':
                        alloc_category = '接收方'
                    unallocated_item = {
                        'cost_center': item.get('cost_center'),
                        'cost_desc': item.get("cost_center_description"),
                        'allocate_category': alloc_category,
                        'unallocated_amount': item.get('unallocated_amount'),
                    }
                    unallocated_data.append(unallocated_item)

    if unallocated_data:
        if filter_info:
            unallocated_data = filter_data(unallocated_data, filter_info)
        if sort_info:
            unallocated_data = sort_data(unallocated_data, sort_info)

    display = [
        {"field": "cost_center", "description": "成本中心"},
        {"field": "cost_desc", "description": "成本中心描述"},
        {"field": "allocate_category", "description": "分配归属"},
        {"field": "unallocated_amount", "description": "待分配金额"}
    ]

    if export_excel:
        timestamp = datetime.now()
        stamp_suffix = timestamp.strftime('%Y%m%d%H%M%S')
        excel_filename = f'未分配成本中心-{stamp_suffix}.xlsx'
        format_data = [{'unallocated': unallocated_data, }]
        field_dict = display_to_entozh(display)
        GetExportData(format_data, excel_filename, field_dict)
    else:
        response = {
            "code": 200,
            "msg": "成功",
            "data": unallocated_data,
            "display": display
        }

        res.set_body(json.dumps(response, cls=SuperEncoder))
        res.commit(True)
