#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@File    : TransferDiffPostAccounting.py
@Author  : tao.chang@dxdstech.com
@Date    : 2025/7/15 11:58
@explain : 月结任务-转投扣料差异调整过账-537
"""

try:
    import pyfiles.SysPathAdd
except ImportError:
    ...
from DbHelper import DbHelper
from logger import LoggerConfig
from SystemHelper import SystemHelper
from ToolsMethods import ResetResponse, ResponseData, generate_raw_sql
from TransferAccountingEngine import (
    TransHandelAccounting,
    TransHandelAccountingBatch,
    TransHandelReversal,
    TransHandelReversalBatch,
)

logger = LoggerConfig("TransferDiffPostAccounting", isStream=True)


def executeData(plant_code, year, period):
    """
    月结步骤执行
    @param plant_code:
    @param year:
    @param period:
    @param task_code:
    @param task_id:
    @param step:
    @return:
    """
    sh = SystemHelper()
    user_id = sh.getUserId()
    db = DbHelper()
    company_code_dict = getDBPlantCode()
    data = summaryReportDB(year, period, plant_code)
    if data:
        insertItem = []
        post_status = True
        TransHandelAccountingData = []
        for item in data:
            wbs_elements = item.get("wbs_elements", "")
            wbs_elements = wbs_elements.strip()
            new_item = {
                "document_category": item.get("document_category", "TZDC"),
                "summary_unique_number": item.get("summary_unique_number", ""),
                "summary_line": item.get("summary_line", ""),
                "data_type": item.get("data_type", ""),
                "year": item.get("year", ""),
                "period": item.get("period", ""),
                "plant_code": item.get("plant_code", ""),
                "company_code": company_code_dict.get(plant_code, ''),
                "prd_mat_code": item.get("prd_mat_code", ""),
                "prodosn": item.get("prodosn", ""),
                "cc_cost_center": item.get("cc_cost_center", ""),
                "wbs_elements": wbs_elements,
                "mat_code": item.get("mat_code", ""),
                "batch_sn": item.get("batch_sn", ""),
                "consump_qty": item.get("consump_qty", 0),
                "basic_uom": item.get("basic_uom", ""),
                "cost_qty": item.get("cost_qty", 0),
                "cost_uom": item.get("cost_uom", ""),
                "opening_actual_cost": item.get("amount",0),
                "post_date": item.get("summary_date", ""),
                "summary_date": item.get("summary_date", ""),
                "price_control": item.get("price_control", ""),
            }
            if item.get("price_control") == "S":
                material_price_unit = item.get("material_price_unit", 1) or 1
                mat_act_price = item.get("average_cost_bc") / material_price_unit
                new_item["mat_act_price"] = mat_act_price
                new_item["actual_cost"] = item.get("cost_qty") * mat_act_price
            else:
                new_item["mat_act_price"] = 0
                new_item["actual_cost"] = item.get("actual_cost", 0)
            if item.get("summary_unique_number") == "dc10bb01c6d97e60d8dc93f98d038e0a":
                print("new_item>>>>",new_item)
            diff_amount = item.get("amount", 0) - new_item.get("actual_cost", 0)
            new_item["diff_amount"] = diff_amount
            # 差异金额为0的不要显示和传输会计引擎
            if diff_amount:
                TransHandelAccountingData.append(new_item)
                if round(abs(diff_amount),2) < 0.01:
                    new_item["status"] = 3
                    new_item["associated_doc_sn"] = ""
                    new_item["post_account_msg"] = "差异金额无需过账"
                else:
                    TransHandelAccountingData.append(new_item)
            else:
                new_item["status"] = 3
                new_item["associated_doc_sn"] = ""
                new_item["post_account_msg"] = "差异金额无需过账"
            insertItem.append(new_item)
                # accountRet = TransHandelAccounting(new_item)
                # if accountRet.code == 200:
                #     new_item["status"] = 3
                #     new_item["associated_doc_sn"] = accountRet.data[0].get("associated_doc_sn", '')
                #     new_item["post_account_msg"] = accountRet.msg
                # else:
                #     post_status = False
                #     new_item["status"] = 2
                #     new_item["associated_doc_sn"] = ""
                #     new_item["post_account_msg"] = accountRet.msg

        try:
            accountRet = TransHandelAccountingBatch(TransHandelAccountingData)
            accountDataDict= {}
            for accountData in accountRet.data:
                accountDataDict[accountData.get("summary_unique_number")] = accountData
            for insert_item in insertItem:
                if accountDataDict.get(insert_item.get("summary_unique_number")):
                    accountDataItem = accountDataDict.get(insert_item.get("summary_unique_number"))
                    print("accountDataItem>>>", accountDataItem)
                    insert_item["status"] = 3 if accountDataItem.get("summary_code") == 200 else 2
                    insert_item["associated_doc_sn"] = accountDataItem.get("associated_doc_sn", '')
                    insert_item["post_account_msg"] = accountDataItem.get("ret_msg") or accountRet.msg
                else:
                    if insert_item.get("status") == 3:
                        continue
                    insert_item["status"] = 2
                    insert_item["associated_doc_sn"] = ""
                    insert_item["post_account_msg"] = accountRet.msg

            if accountRet.code != 200:
                post_status = False
                # for insert_item in insertItem:
                #     if accountDataDict.get(insert_item.get("summary_unique_number")):
                #         accountDataItem = accountDataDict.get(insert_item.get("summary_unique_number"))
                #         insert_item["status"] = 3 if accountDataItem.get("summary_code") == 200 else 2
                #         insert_item["associated_doc_sn"] = accountDataItem.get("associated_doc_sn", '')
                #         insert_item["post_account_msg"] = accountDataItem.get("ret_msg") or accountRet.msg
            # else:
            #     post_status = False
            # for insert_item in insertItem:
            #     if accountDataDict.get(insert_item.get("summary_unique_number")):
            #         accountDataItem = accountDataDict.get(insert_item.get("summary_unique_number"))
            #         insert_item["status"] = 3 if accountDataItem.get("summary_code") == 200 else 2
            #         insert_item["associated_doc_sn"] = accountDataItem.get("associated_doc_sn", '')
            #         insert_item["post_account_msg"] = accountDataItem.get("ret_msg") if accountDataItem.get("ret_msg") else accountRet.msg
            print("insertItem>>>", insertItem[:10])
            duplicate_fields = ['status', 'associated_doc_sn', 'post_account_msg',"mat_act_price","actual_cost"]
            db.batchInsertToDB("t_co_transfer_matcost_diff_post", insertItem, user_id=user_id,
                               DuplicateSQLKey=duplicate_fields)
        except Exception as e:
            logger.printInfo("executeData", str(e))
            post_status = False
        if not post_status:
            return ResponseData(400, "过账失败", [])
        if post_status:
            return ResponseData(200, "执行成功", [])
    else:
        return ResponseData(200, "执行成功", [])


@ResetResponse(params=["plant_code", "year", "period", "task_code", "task_id", "step"], _payload_=True)
def postRetry(plant_code, year, period, task_code, task_id, step, _payload_, **kwargs):
    """
    过账重试
    @param body:
    @return:
    """
    sh = SystemHelper()
    user_id = sh.getUserId()
    db = DbHelper()
    postStatus = True
    filter_info = _payload_.get("filter_info")
    if filter_info:
        table_alias = {
            "id": "rp",
            "summary_unique_number": "rp",
            "summary_line": "rp",
            "status": "rp",
            "associated_doc_sn": "rp",
            "post_account_msg": "rp",
            "reverse_account_msg": "rp",
            "data_type": "rp",
            "year": "rp",
            "period": "rp",
            "plant_code": "rp",
            "company_code": "rp",
            "prd_mat_code": "rp",
            "post_date": "rp",
            "prodosn": "rp",
            "cc_cost_center": "rp",
            "wbs_elements": "rp",
            "mat_code": "rp",
            "batch_sn": "rp",
            "consump_qty": "rp",
            "bas_unit_code": "rp",
            "cost_qty": "rp",
            "cost_uom": "rp",
            "actual_mat_price": "rp",
            "actual_cost": "rp",
            "opening_actual_cost": "rp",
            "diff_amount": "rp",
            "create_id": "rp",
            "create_time": "rp",
            "update_id": "rp",
            "update_time": "rp",
            "note": "rp",
            "mat_code_desc": "tmmbd1.description",
            "prd_mat_code_desc": "tmmbd.description",
            "cost_center_description": "tccc",
        }
        raw_where_sql, raw_sort_sql = generate_raw_sql({"plant_code": plant_code, "year": year, "period": period},
                                                       filter_info, {}, table_alias,alias_back_quote_mode=False)
        data = getDBPostResult(None, None, None, 2, raw_where_sql)
    else:
        data = getDBPostResult(year, period, plant_code, 2, None)
    insertItem = []
    TransHandelAccountingData = []
    for item in data:
        diff_amount = item.get('diff_amount', 0)
        # 差异金额为0的不要显示和传输会计引擎
        if diff_amount:
            if round(abs(diff_amount),2) < 0.01:
                item["status"] = 3
                item["associated_doc_sn"] = ""
                item["post_account_msg"] = "差异金额无需过账"
            else:
                TransHandelAccountingData.append(item)
        else:
            item["status"] = 3
            item["associated_doc_sn"] = ""
            item["post_account_msg"] = "差异金额无需过账"
            # accountRet = TransHandelAccounting(item)
            # if accountRet.code == 200:
            #     item["status"] = 3
            #     item["associated_doc_sn"] = accountRet.data[0].get("associated_doc_sn", '')
            #     item["post_account_msg"] = accountRet.msg
            # else:
            #     postStatus = False
            #     item["status"] = 2
            #     item["post_account_msg"] = accountRet.msg
        insertItem.append(item)
    DuplicateSQLKey = ["status", "associated_doc_sn", "post_account_msg"]
    try:
        accountRet = TransHandelAccountingBatch(TransHandelAccountingData)
        accountDataDict = {}
        for accountData in accountRet.data:
            accountDataDict[accountData.get("summary_unique_number")] = accountData

        for insert_item in insertItem:
            if accountDataDict.get(insert_item.get("summary_unique_number")):
                accountDataItem = accountDataDict.get(insert_item.get("summary_unique_number"))
                insert_item["status"] = 3 if accountDataItem.get("summary_code") == 200 else 2
                insert_item["associated_doc_sn"] = accountDataItem.get("associated_doc_sn", '')
                insert_item["post_account_msg"] = accountDataItem.get("ret_msg") or accountRet.msg
            else:
                if insert_item.get("status") == 3:
                    continue
                insert_item["status"] = 2
                insert_item["associated_doc_sn"] = ""
                insert_item["post_account_msg"] = accountRet.msg
        if accountRet.code != 200:
            postStatus = False
        # if accountRet.code == 200:
        #     for insert_item in insertItem:
        #         if accountDataDict.get(insert_item.get("summary_unique_number")):
        #             accountDataItem = accountDataDict.get(insert_item.get("summary_unique_number"))
        #             insert_item["status"] = 3
        #             insert_item["associated_doc_sn"] = accountDataItem.get("associated_doc_sn", '')
        #             insert_item["post_account_msg"] = accountDataItem.get("ret_msg") or accountRet.msg
        # else:
        #     for insert_item in insertItem:
        #         if accountDataDict.get(insert_item.get("summary_unique_number")):
        #             accountDataItem = accountDataDict.get(insert_item.get("summary_unique_number"))
        #             insert_item["status"] = 2
        #             insert_item["associated_doc_sn"] = ""
        #             insert_item["post_account_msg"] = accountDataItem.get("ret_msg") if accountDataItem.get(
        #                 "ret_msg") else accountRet.msg
        if insertItem:
            db.batchInsertToDB("t_co_transfer_matcost_diff_post", insertItem, user_id=user_id,
                               DuplicateSQLKey=DuplicateSQLKey)
    except Exception as e:
        logger.printInfo("postRetry", str(e))
        update_monthly_procedure(task_code, task_id, step, 3, db)
        return ResponseData(400, "重试过账失败", [])
    if postStatus:
        update_monthly_procedure(task_code, task_id, step, 4, db)
        return ResponseData(200, "执行成功", [])
    else:
        update_monthly_procedure(task_code, task_id, step, 3, db)
        return ResponseData(400, "重试过账失败", [])


@ResetResponse(params=["plant_code", "year", "period", "task_code", "step"], _payload_=True, pagination=True,
               excelName="转投扣料差异调整.xlsx")
def searchData(plant_code, year, period, task_code, step, _payload_, **kwargs):
    """
    查询接口
    @param plant_code:
    @param year:
    @param period:
    @param task_code:
    @param step:
    @return:
    """
    display = [
        {"field": "summary_unique_number", "description": "汇总唯一号"},
        {"field": "summary_line", "description": "汇总行"},
        {"field": "status", "description": "过账状态"},
        {"field": "associated_doc_sn", "description": "凭证号"},
        {"field": "post_account_msg", "description": "过账消息"},
        {"field": "reverse_account_msg", "description": "过账重置消息"},
        {"field": "data_type", "description": "数据类型"},
        {"field": "year", "description": "年度"},
        {"field": "period", "description": "期间"},
        {"field": "plant_code", "description": "工厂代码"},
        {"field": "company_code", "description": "公司代码"},
        {"field": "prd_mat_code", "description": "产品物料"},
        {"field": "post_date", "description": "过账日期"},
        {"field": "prodosn", "description": "生产订单编号"},
        {"field": "cc_cost_center", "description": "核算成本中心"},
        {"field": "wbs_elements", "description": "元素"},
        {"field": "mat_code", "description": "消耗物料"},
        {"field": "batch_sn", "description": "批次号"},
        {"field": "consump_qty", "description": "消耗数量"},
        {"field": "bas_unit_code", "description": "计量单位代码"},
        {"field": "cost_qty", "description": "成本单位数量"},
        {"field": "cost_uom", "description": "成本单位"},
        {"field": "mat_act_price", "description": "材料实际单价"},
        {"field": "actual_cost", "description": "实际成本"},
        {"field": "opening_actual_cost", "description": "期初实际成本"},
        {"field": "diff_amount", "description": "差异金额"},
        {"field": "create_id", "description": "创建人"},
        {"field": "create_time", "description": "创建时间"},
        {"field": "update_id", "description": "更改人"},
        {"field": "update_time", "description": "更改时间"},
    ]
    # 差异金额为0的不显示
    where_sql = " WHERE rp.`diff_amount` != 0 "
    data = getDBPostResult(year, period, plant_code, where_sql=where_sql)
    return ResponseData(200, "查询成功", data, display=display)


def reversalData(plant_code, year, period):
    """
    重置接口
    @param plant_code:
    @param year:
    @param period:
    @return:
    """

    sh = SystemHelper()
    user_id = sh.getUserId()
    db = DbHelper()
    # 先删除状态失败的数据
    clearDBPostResult(plant_code, year, period, 2, db=db)
    data = getDBPostResult(year, period, plant_code, 3, db=db)
    updateItem = []
    delete = []
    rev_success_summary_unique_number = []
    if data:
        new_post_data = []
        for item in data:
            item['wbs_elements'] = str(item.get('wbs_elements', '')).strip()
            if item.get("associated_doc_sn") == '':
                delete.append(item.get("id"))
            else:
                new_post_data.append(item)

        reversalRet = TransHandelReversalBatch(new_post_data)
        if reversalRet.code != 200:
            reversalRetDict = {}
            for reData in reversalRet.data:
                reversalRetDict[reData.get("summary_unique_number")] = reData
            for item in new_post_data:
                summary_unique_number = item.get('summary_unique_number', '')
                if summary_unique_number and summary_unique_number not in rev_success_summary_unique_number:
                    rev_success_summary_unique_number.append(summary_unique_number)
                if summary_unique_number in reversalRetDict:
                    if reversalRetDict[summary_unique_number]["ret_code"] == 200:
                        delete.append(item.get("id"))
                        continue
                    item["reverse_account_msg"] = reversalRetDict[summary_unique_number]["ret_msg"]
                else:
                    item["reverse_account_msg"] = ""
                updateItem.append(item)
        else:
            for item in new_post_data:
                delete.append(item.get("id"))
                summary_unique_number = item.get('summary_unique_number', '')
                if summary_unique_number and summary_unique_number not in rev_success_summary_unique_number:
                    rev_success_summary_unique_number.append(summary_unique_number)
    if delete:
        delete_sql = f""" DELETE FROM `t_co_transfer_matcost_diff_post` WHERE `id` IN ({",".join(map(str, delete))}) """
        db.exec_sql(delete_sql)
    print("updateItem>?>>",updateItem)
    print("rev_success_summary_unique_number>>>", rev_success_summary_unique_number)

    if updateItem:
        DuplicateSQLKey = ["reverse_account_msg"]
        db.batchInsertToDB("t_co_transfer_matcost_diff_post", updateItem, user_id=user_id,
                           DuplicateSQLKey=DuplicateSQLKey)

        return ResponseData(400, "重置失败", [])

    update_voucher_head(rev_success_summary_unique_number, db)
    return ResponseData(200, "执行成功", [])


@ResetResponse(params=["plant_code", "year", "period", "task_code", "task_id", "step"])
def reversalRetry(plant_code, year, period, task_code, task_id, step, **kwargs):
    """
    重置接口
    @param plant_code:
    @param year:
    @param period:
    @return:
    """
    sh = SystemHelper()
    user_id = sh.getUserId()
    db = DbHelper()
    # 先删除状态失败的数据
    clearDBPostResult(plant_code, year, period, 2, db=db)
    data = getDBPostResult(year, period, plant_code, 3, db=db)
    updateItem = []
    delete = []
    rev_success_summary_unique_number = []
    if data:
        new_post_data = []
        for item in data:
            if item.get("associated_doc_sn") == '':
                delete.append(item.get("id"))
            else:
                new_post_data.append(item)
        reversalRet = TransHandelReversalBatch(new_post_data)
        if reversalRet.code != 200:
            reversalRetDict = {}
            for reData in reversalRet.data:
                reversalRetDict[reData.get("summary_unique_number")] = reData
            for item in new_post_data:
                summary_unique_number = item.get('summary_unique_number', '')
                if summary_unique_number and summary_unique_number not in rev_success_summary_unique_number:
                    rev_success_summary_unique_number.append(summary_unique_number)
                if summary_unique_number in reversalRetDict:
                    if reversalRetDict[summary_unique_number]["ret_code"] == 200:
                        delete.append(item.get("id"))
                        continue
                    item["reverse_account_msg"] = reversalRetDict[summary_unique_number]["ret_msg"]
                else:
                    item["reverse_account_msg"] = ""
                updateItem.append(item)
        else:
            for item in new_post_data:
                delete.append(item.get("id"))
                summary_unique_number = item.get('summary_unique_number', '')
                if summary_unique_number and summary_unique_number not in rev_success_summary_unique_number:
                    rev_success_summary_unique_number.append(summary_unique_number)
        # for item in data:
        #     reversalRet = TransHandelReversal(item)
        #     if reversalRet.code != 200:
        #         item["reverse_account_msg"] = reversalRet.msg
        #         updateItem.append(item)
        #     else:
        #         delete.append(item.get("id"))
        #         summary_unique_number = item.get('summary_unique_number', '')
        #         if summary_unique_number and summary_unique_number not in rev_success_summary_unique_number:
        #             rev_success_summary_unique_number.append(summary_unique_number)

    if delete:
        db.exec_sql(f""" delete from `t_co_transfer_matcost_diff_post` where id in ({",".join(delete)}) """)

    if updateItem:
        DuplicateSQLKey = ["reverse_account_msg"]
        db.batchInsertToDB("t_co_transfer_matcost_diff_post", updateItem, user_id=user_id,
                           DuplicateSQLKey=DuplicateSQLKey)
        update_monthly_procedure(task_code, task_id, step, 3, db)
        return ResponseData(400, "重置失败", [])

    update_voucher_head(rev_success_summary_unique_number, db)

    update_monthly_procedure(task_code, task_id, step, 1, db)
    return ResponseData(200, "执行成功", [])


def getDBPostResult(year, period, plant_code, status=None, where_sql=None, db=None):
    """
    查询 t_co_transfer_matcost_diff_post 数据进行 展示和进行过账重试
    @param year:
    @param period:
    @param plant_code:
    @param status:
    @return:
    """
    if not db:
        db = DbHelper()
    sql = f'''
              SELECT 
                  rp.*,
                  sr.`summary_date`,
                  tmmbd1.`mat_description` as `mat_code_desc`,
                  tmmbd.`mat_description` as `prd_mat_code_desc`,
                  tccc.`cost_center_description`
               FROM `t_co_transfer_matcost_diff_post` rp 
               LEFT JOIN `t_co_summary_report` as sr on rp.`summary_unique_number` = sr.`summary_unique_number` AND rp.`summary_line` = sr.`summary_line`
               LEFT JOIN `t_mmd_material_basic_data` as tmmbd on rp.`prd_mat_code` = tmmbd.`mat_code` 
               LEFT JOIN `t_mmd_material_basic_data` as tmmbd1 on rp.`mat_code` = tmmbd1.`mat_code` 
               LEFT JOIN `t_coc_cost_center` as tccc on rp.`cc_cost_center` = tccc.`cost_center` 
      '''
    if where_sql:
        where_sql = where_sql.strip()
        where_sql += " AND rp.`data_type` in ('QC02','QC03','QC04') "
        # if year:
        #     where_sql += f""" AND rp.year='{year}' """
        #
        # if period:
        #     where_sql += f""" AND rp.period='{period}' """
        #
        # if plant_code:
        #     if isinstance(plant_code, list):
        #         where_sql += f""" AND rp.plant_code in ({",".join([repr(i) for i in plant_code])}) """
        #     else:
        #         where_sql += f""" AND rp.plant_code = "{plant_code}" """
    else:
        where_sql = " WHERE rp.`data_type` in ('QC02','QC03','QC04') "
    if year:
        where_sql += f""" AND rp.`year`='{year}' """

    if period:
        where_sql += f""" AND rp.`period`='{period}' """

    if plant_code:
        if isinstance(plant_code, list):
            where_sql += f""" AND rp.`plant_code` in ({",".join([repr(i) for i in plant_code])}) """
        else:
            where_sql += f""" AND rp.`plant_code` = '{plant_code}' """
    if status:
        where_sql += f""" AND rp.`status` = {status} """

    sql += where_sql
    logger.printInfo("sql", sql)
    ret = db.query_sql(sql)
    if ret:
        for item in ret:
            item['document_category'] = "TZDC"

    return ret


def clearDBPostResult(plant_code, year, period, status, db):
    sql = f""" delete from `t_co_transfer_matcost_diff_post` where `plant_code`='{plant_code}' and `year`='{year}' and `period`='{period}' and `status`={status} """
    db.exec_sql(sql)
    db.dbCommit()


def getDBPlantCode():
    db = DbHelper()
    sql = f""" select * from `t_os_company_plant_alloc` """
    ret = db.query_sql(sql)
    if ret:
        return {i.get("plant_code"): i.get("company_code") for i in ret}
    return {}


def summaryReportDB(year, period, plant_code):
    db = DbHelper()
    where_sql = " WHERE rp.data_type in ('QC02','QC03','QC04') "
    sql = f'''
            SELECT 
                rp.*,
                tmmcd.`price_control`,
                tmmcd.`price_unit` as `material_price_unit`,
                tcacc.`average_cost_bc`,
                tcsr.`amount` as `result_amount`
             FROM `t_co_summary_report` rp 
             LEFT JOIN `t_mmd_material_cost_data` as tmmcd on rp.`plant_code` = tmmcd.`plant_code` and rp.`mat_code` = tmmcd.`mat_code`
             LEFT JOIN `t_co_summary_result` as tcsr on tcsr.`summary_unique_number` = rp.`summary_unique_number` and tcsr.`summary_line` = rp.`summary_line`
             LEFT JOIN `t_co_actual_cost_calc_{plant_code}_{year}{period}` as tcacc on rp.`plant_code` = tcacc.`plant_code` and rp.`mat_code` = tcacc.`mat_code` and rp.`year` = tcsr.`year` and rp.`period` = tcsr.`period`
    '''
    if year:
        where_sql += f""" AND rp.`year`='{year}' """

    if period:
        where_sql += f""" AND rp.`period`='{period}' """

    if plant_code:
        if isinstance(plant_code, list):
            where_sql += f""" AND rp.`plant_code` in ({",".join([repr(i) for i in plant_code])}) """
        else:
            where_sql += f""" AND rp.`plant_code` = '{plant_code}' """

    sql += where_sql
    logger.printInfo("sql", sql)
    ret = db.query_sql(sql)
    if ret:
        for item in ret:
            item['document_category'] = "TZDC"

    return ret


def update_monthly_procedure(task_code, task_id, step, status, db):
    if not task_id:
        task_id = 537
    sql = f''' update `t_co_monthly_procedure` set `status`='{status}' where `task_code`='{task_code}' and `task_id`={task_id} and `step`='{step}' '''
    db.exec_sql(sql)
    db.dbCommit()


def update_voucher_head(summary_unique_number, db):
    where_sql = ''
    if summary_unique_number and isinstance(summary_unique_number, list):
        where_sql = " WHERE `summary_unique_number` IN ({}) ".format(', '.join(map(repr, summary_unique_number)))
    elif summary_unique_number and isinstance(summary_unique_number, str):
        where_sql = f" WHERE `summary_unique_number` = '{summary_unique_number}' "

    if summary_unique_number and where_sql:
        update_sql = f""" UPDATE `t_fi_voucher_head` SET `posting_status` = '' {where_sql} """
        print(update_sql)
        db.exec_sql(update_sql)
        db.dbCommit()

