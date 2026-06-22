#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@File    : ZZEXT_MonthBillStepPushSAP.py
@Author  : ying.chen@dxdstech.com
@Date    : 2025/7/14 14:20
@explain : 推送SAP前的数据处理操作扩展
"""
import random
import time
from datetime import datetime

from logger import LoggerConfig, LogLevel
from ToolsMethods import filter_data, sort_data
from ZZEXT_send_fi_archiv_doc_to_sap import send_fi_archiv_doc


def process_resp_result(resp, archive_doc_num, payload, log_code, text_info, plant_code, company_code):
    resp_type = resp.get('type')
    message = resp.get('message')
    message = message.strip().strip("'")
    code, msg = 200, ''
    if resp_type != 'S':
        try:
            code = 206
            msg = f' 归档凭证编号:{archive_doc_num} 推送至SAP失败: {message}'
            message = message[:100]
            detail = {
                'input': payload,
                'output': '',
            }
            LoggerConfig.logToDB(log_code, '', LogLevel.ERROR, f'{text_info}:{message}', detail,
                                 plant_code, company_code)
        except Exception as e:
            print(str(e))
            print('日志写入失败')

    return code, msg


def ZZEXTAuxMatCostPostPushSAP(user_id, task_id, plant_code, item):
    """
    辅材费用调整过账推送至SAP 按钮
    task_id 513
    """
    log_code = '030030009'
    help_text = '辅材费用调整过账推送至SAP'
    archive_doc_num = item.get('archiv_doc_num') or ''
    company_code = item.get('company_code') or ''

    time_timestamp = str(datetime.now().timestamp()).split(".")[0]
    random_number = str(random.randint(00000, 99999))
    guid = "AuxMatCostPostPushSAP" + time_timestamp + random_number

    payload = {
        "guid": guid,
        "data": {
            "summary_unique_number": item.get('summary_unique_number') or '',  # 汇总唯一号
            "company_code": company_code,  # 公司代码
            "year": item.get('year') or '',  # 过账年度
            "archiv_doc_num": archive_doc_num,  # 归档凭证编号
        }
    }
    start_time = time.time()
    resp = send_fi_archiv_doc(payload, user_id, task_id, plant_code)
    print("send_fi_archiv_doc_to_sap end time:", time.time() - start_time)
    code, each_msg = process_resp_result(resp, archive_doc_num, payload, log_code, help_text, plant_code, company_code)
    print("process end time:", time.time() - start_time)

    return code, each_msg


def ZZEXTOutsourceInventoryPushSAP(user_id, task_id, plant_code, item):
    """
    外购外协存货实际成本过账推送SAP 扩展
    task_id 503
    """
    log_code = '030030015'
    help_text = '外购外协存货实际成本过账推送SAP'
    archive_doc_num = item.get('archiv_doc_num') or ''
    company_code = item.get('company_code') or ''

    time_timestamp = str(datetime.now().timestamp()).split(".")[0]
    random_number = str(random.randint(00000, 99999))
    guid = "OutsourceInventoryPushSAP" + time_timestamp + random_number

    payload = {
        "guid": guid,
        "data": {
            "summary_unique_number": item.get('summary_unique_number') or '',  # 汇总唯一号
            "company_code": company_code,  # 公司代码
            "year": item.get('year') or '',  # 过账年度
            "archiv_doc_num": archive_doc_num,  # 归档凭证编号
        }
    }
    start_time = time.time()
    resp = send_fi_archiv_doc(payload, user_id, task_id, plant_code)
    print("send_fi_archiv_doc_to_sap end time:", time.time() - start_time)
    code, each_msg = process_resp_result(resp, archive_doc_num, payload, log_code, help_text, plant_code, company_code)
    print("process end time:", time.time() - start_time)

    return code, each_msg


def ZZEXTOtherCostAllocPushSAP(user_id, task_id, plant_code, item):
    """
    其他成本分摊过账推送SAP 扩展
    task_id 504
    """
    log_code = '030030030'
    help_text = '其他成本分摊过账推送SAP'
    archive_doc_num = item.get('archiv_doc_num') or ''
    company_code = item.get('company_code') or ''

    time_timestamp = str(datetime.now().timestamp()).split(".")[0]
    random_number = str(random.randint(00000, 99999))
    guid = "OtherCostAllocPushSAP" + time_timestamp + random_number
    payload = {
        "guid": guid,
        "data": {
            "summary_unique_number": item.get('summary_unique_number') or '',  # 汇总唯一号
            "company_code": company_code,  # 公司代码
            "year": item.get('year') or '',  # 过账年度
            "archiv_doc_num": archive_doc_num,  # 归档凭证编号
        }
    }
    start_time = time.time()
    resp = send_fi_archiv_doc(payload, user_id, task_id, plant_code)
    print("send_fi_archiv_doc_to_sap end time:", time.time() - start_time)
    code, each_msg = process_resp_result(resp, archive_doc_num, payload, log_code, help_text, plant_code, company_code)
    print("process end time:", time.time() - start_time)

    return code, each_msg


def ZZEXTCostAllocPostPushSAP(user_id, task_id, plant_code, item):
    """
    费用分配分摊过账推送SAP 扩展
    task_id 505
    """
    log_code = '030030022'
    help_text = '辅材费用调整过账推送至SAP'

    archive_doc_num = item.get('archiv_doc_num') or ''
    company_code = item.get('company_code') or ''

    time_timestamp = str(datetime.now().timestamp()).split(".")[0]
    random_number = str(random.randint(00000, 99999))
    guid = "CostAllocPostPushSAP" + time_timestamp + random_number
    payload = {
        "guid": guid,
        "data": {
            "summary_unique_number": item.get('summary_unique_number') or '',  # 汇总唯一号
            "company_code": company_code,  # 公司代码
            "year": item.get('year') or '',  # 过账年度
            "archiv_doc_num": archive_doc_num,  # 归档凭证编号
        }
    }
    start_time = time.time()
    resp = send_fi_archiv_doc(payload, user_id, task_id, plant_code)
    print("send_fi_archiv_doc_to_sap end time:", time.time() - start_time)
    code, each_msg = process_resp_result(resp, archive_doc_num, payload, log_code, help_text, plant_code, company_code)
    print("process end time:", time.time() - start_time)

    return code, each_msg


def ZZEXTActualCostPostPushSAP(user_id, task_id, plant_code, item):
    """
    实际作业成本过账推送SAP 扩展
    task_id 506
    """
    log_code = '030030027'
    help_text = '实际作业成本过账推送SAP'

    archive_doc_num = item.get('archiv_doc_num') or ''
    company_code = item.get('company_code') or ''

    time_timestamp = str(datetime.now().timestamp()).split(".")[0]
    random_number = str(random.randint(00000, 99999))
    guid = "ActualCostPostPushSAP" + time_timestamp + random_number
    payload = {
        "guid": guid,
        "data": {
            "company_code": company_code,  # 公司代码
            "year": item.get('year') or '',  # 过账年度
            "archiv_doc_num": archive_doc_num,  # 归档凭证编号
            "summary_unique_number": item.get('summary_unique_number') or '',  # 汇总唯一号
        }
    }
    start_time = time.time()
    resp = send_fi_archiv_doc(payload, user_id, task_id, plant_code)
    print("send_fi_archiv_doc_to_sap end time:", time.time() - start_time)
    code, each_msg = process_resp_result(resp, archive_doc_num, payload, log_code, help_text, plant_code, company_code)
    print("process end time:", time.time() - start_time)

    return code, each_msg


def ZZEXTPeriodProcessPostPushSAP(user_id, task_id, plant_code, item):
    """
    期末在制过账推送SAP 扩展
    task_id 507
    """
    log_code = '030030039'
    help_text = '期末在制过账推送SAP'

    archive_doc_num = item.get('archiv_doc_num') or ''
    company_code = item.get('company_code') or ''

    time_timestamp = str(datetime.now().timestamp()).split(".")[0]
    random_number = str(random.randint(00000, 99999))
    guid = "PeriodProcessPostPushSAP" + time_timestamp + random_number
    payload = {
        "guid": guid,
        "data": {
            "summary_unique_number": item.get('summary_unique_number') or '',  # 汇总唯一号
            "company_code": company_code,  # 公司代码
            "year": item.get('year') or '',  # 过账年度
            "archiv_doc_num": archive_doc_num,  # 归档凭证编号
        }
    }
    start_time = time.time()
    resp = send_fi_archiv_doc(payload, user_id, task_id, plant_code)
    print("send_fi_archiv_doc_to_sap end time:", time.time() - start_time)
    code, each_msg = process_resp_result(resp, archive_doc_num, payload, log_code, help_text, plant_code, company_code)
    print("process end time:", time.time() - start_time)

    return code, each_msg


def ZZEXTCompletionCostPostPushSAP(user_id, task_id, plant_code, item):
    """
    完工成本过账推送SAP 扩展
    task_id 509
    """
    log_code = '030030041'
    help_text = '完工成本过账推送SAP'

    archive_doc_num = item.get('archiv_doc_num') or ''
    company_code = item.get('company_code') or ''

    time_timestamp = str(datetime.now().timestamp()).split(".")[0]
    random_number = str(random.randint(00000, 99999))
    guid = "CompletionCostPostPushSAP" + time_timestamp + random_number
    payload = {
        "guid": guid,
        "data": {
            "summary_unique_number": item.get('summary_unique_number') or '',  # 汇总唯一号
            "company_code": item.get('company_code') or '',  # 公司代码
            "year": item.get('year') or '',  # 过账年度
            "archiv_doc_num": archive_doc_num,  # 归档凭证编号
        }
    }
    start_time = time.time()
    resp = send_fi_archiv_doc(payload, user_id, task_id, plant_code)
    print("send_fi_archiv_doc_to_sap end time:", time.time() - start_time)
    code, each_msg = process_resp_result(resp, archive_doc_num, payload, log_code, help_text, plant_code, company_code)
    print("process end time:", time.time() - start_time)

    return code, each_msg


def ZZEXTNotOutsourceInventorPushSAP(user_id, task_id, plant_code, item):
    """
    非外购外协存货实际成本过账推送SAP 扩展
    task_id 511
    """
    log_code = '030030047'
    help_text = '非外购外协存货实际成本过账推送SAP'

    archive_doc_num = item.get('archiv_doc_num') or ''
    company_code = item.get('company_code') or ''

    time_timestamp = str(datetime.now().timestamp()).split(".")[0]
    random_number = str(random.randint(00000, 99999))
    guid = "NotOutsourceInventorPushSAP" + time_timestamp + random_number
    payload = {
        "guid": guid,
        "data": {
            "summary_unique_number": item.get('summary_unique_number') or '',  # 汇总唯一号
            "company_code": company_code,  # 公司代码
            "year": item.get('year') or '',  # 过账年度
            "archiv_doc_num": archive_doc_num,  # 归档凭证编号
        }
    }
    start_time = time.time()
    resp = send_fi_archiv_doc(payload, user_id, task_id, plant_code)
    print("send_fi_archiv_doc_to_sap end time:", time.time() - start_time)
    code, each_msg = process_resp_result(resp, archive_doc_num, payload, log_code, help_text, plant_code, company_code)
    print("process end time:", time.time() - start_time)

    return code, each_msg


def get_month_task_info(data):
    task_code, step = '', ''
    if 'task_code' in data:
        task_code = data.pop('task_code')
    if 'step' in data:
        step = data.pop('step')

    valid_fields = ['year', 'period', 'plant_code']
    filter_condition = {field: data.get(field) for field in valid_fields}

    return filter_condition, task_code, step


def ZZEXT_aux_mat_cost_post_push_query(db, body):
    """ERP->秘火调拨辅材凭证生成 查询"""
    prefix_filter = body.get('data') or {}
    prefix_filter, task_code, step = get_month_task_info(prefix_filter)
    payload = body.get('_payload_', {})
    filter_info = payload.get('filter_info', {})
    sort_info = payload.get('sort_info', {})
    year = prefix_filter.get('year')
    period = prefix_filter.get('period')
    plant_code = prefix_filter.get('plant_code')

    query_sql = f"""
            SELECT
                t1.`id`,
                t1.`uf_year`,
                t1.`uf_period`,
                t1.`uf_company_code`,
                t1.`uf_associated_doc_sn`,
                t1.`uf_fi_document_number`,
                t1.`uf_posting_date`,
                t2.`summary_unique_number`,
                t3.`posting_status`,
                t3.`archiv_doc_num`,
                t3.`external_sn`
            FROM
                `ut_auxiliary_manufacture_consume_detail` t1
            LEFT JOIN `t_fi_integration_relation` t2 ON t1.`uf_year` = t2.`year` AND t1.`uf_period` = t2.`period` AND t1.`uf_company_code` = t2.`company_code` AND t1.`uf_fi_document_number` = t2.`fi_document_number`
            LEFT JOIN `t_fi_doc_for_archiv_transfer_log` t3 ON t1.`uf_year` = t3.`year` AND t1.`uf_company_code` = t3.`company_code` AND t2.`summary_unique_number` = t3.`summary_unique_number`
            WHERE
               t1.`uf_year` = '{year}' AND t1.`uf_period` = '{period}' AND t1.`uf_plant_code` = '{plant_code}' 
            """

    print(query_sql)
    query_data = db.query_sql(query_sql)
    res_data = []
    if query_data:
        for item in query_data:
            formal_item = {}
            for field_name, field_value in item.items():
                if field_name and str(field_name).startswith('uf_'):
                    field_name = str(field_name)[3:]
                formal_item[field_name] = field_value
            res_data.append(formal_item)

        if filter_info:
            res_data = filter_data(res_data, filter_info)  # 筛选过滤

        if sort_info:
            res_data = sort_data(res_data, sort_info)

    print('res_data:', res_data)
    return res_data
