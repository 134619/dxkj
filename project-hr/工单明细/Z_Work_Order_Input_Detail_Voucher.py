#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@File    : Z_Work_Order_Input_Detail_Voucher.py
@Author  : chengye.lu@dxdstech.com
@Date    : 2026/6/8 11:13 
@explain : 
"""
import json
from decimal import Decimal

from DbHelper import DbHelper
from logger import LoggerConfig
from SystemHelper import EnvKeys, SystemHelper
from ToolsMethods import ResetResponse, ResponseData, ResponseStatusCode, calc_time
from ZZEXT_MonthBillStepPushSAP import ZZEXTPostPushSAP

logger = LoggerConfig("Z_Work_Order_Input_Detail_Voucher", isStream=True)


# 新增标准月结任务task_id
# 月结步骤中 成本投入凭证 点击过账 只生成凭证不传输
# 1 获取所用投入凭证 在界面展示
# 获取所有工单投入明细，工单投入明细包括材料成本分摊、费用分摊、作业成本、其他消耗。按凭证类别汇总展示。
# 2点击推送，调用会计凭证推送接口，推送会计凭证
# 详细逻辑
# 按查询参数，工厂代码、年度、期间，单据类别（document_category）=EMDC/FIDC，在表t_fi_integration_relation中过滤
# 公司代码：表中的company_code；
# 年度：表中year；
# 期间：表中period；
# 凭证类型：过滤：表中accounting_document_type=COE0/COT0/COC0的数据
#
# CO凭证编号：表中business_doc_sn
# FI凭证类型  accounting_document_type
# 财务凭证编号：基于行的公司代码、年度、期间、单据类别=EMDC/FIDC在表t_fi_integration_relation中获取fi_document_number
# 归档凭证号：基于行的公司代码、年度、期间、财务凭证编号在表t_fi_integration_relation中获取汇总唯一号summary_unique_number，
# 基于公司代码、年度、汇总唯一号在表fi_doc_for_archiv_transfer_log中获取archiv_doc_num
# 过账状态：基于行的公司代码、年度、财务凭证编号在表t_fi_integration_relation中获取汇总唯一号summary_unique_number，
# 基于公司代码、年度、汇总唯一号在表fi_doc_for_archiv_transfer_log中获取posting_status
# 外部凭证号：基于行的公司代码、年度、财务凭证编号在表t_fi_integration_relation中获取汇总唯一号summary_unique_number，
# 基于公司代码、年度、汇总唯一号在表fi_doc_for_archiv_transfer_log中获取external_sn
#  
# 点击推送按钮：
# 基于界面中的公司代码、年度、期间、归档凭证号，过滤【归档凭证传输关系表】中，
# SAP凭证编号为空，将其在【归档凭证抬头表】&【归档凭证行项目表】推送至【会计凭证过账接口】，
# 推送给SAP系统，SAP生成财务凭证后返回结果，更新至【归档凭证传输关系表】，并执行界面刷新，更新界面的SAP凭证号的信息，注意是一个归档凭证对应多个SAP凭证，需自己增加行数显示。出现新的查询结果；
class SafeQueryBuilder:
    # allowed_columns
    # allowed_tables
    def __init__(self, table_name: list,join_file_name: list, allowed_columns_dic :dict[str:list[str]], allowed_tables=None):
        """
        table_name    ['t_fi_integration_relation', 'fi_doc_for_archiv_transfer_log',]
        join_file_name    [['summary_unique_number']]
        allowed_columns_dic    {'t_fi_integration_relation':["company_code","year","period","document_category","business_doc_sn","accounting_document_type",
                              "fi_document_number","summary_unique_number"],'fi_doc_for_archiv_transfer_log':['archiv_doc_num','posting_status','external_sn']}
        """
        if table_name and allowed_tables and all( i not in allowed_tables for i in table_name ) :
            raise ValueError(f"Invalid table: {table_name}")
        if len(table_name) > 1 > len(table_name) - len(join_file_name):
            raise ValueError(f"Invalid join_file_name count: {len(join_file_name)}")
        self.table_name = table_name
        self.join_file_name = join_file_name
        self.allowed_columns_dic = allowed_columns_dic

        if len(table_name) == 1:
            self.allowed_columns = [f"`{i}`" for i in allowed_columns_dic.get(table_name[0], [])]
        else:
            self.allowed_columns =  [f"t{table_name.index(key)+1}.`{item}`" for key, values, in allowed_columns_dic.items() for item in values]

        self.conditions = []
        self.params = []

    def where(self, column, operator, value):
        if '.' in column:
            alias, column = column.split('.')
            self.join_file_name.append([alias])
        else:
            alias = None
        alias_column = f"{alias}.`{column}`" if alias else f"`{column}`"
        if alias_column and alias_column not in self.allowed_columns:
            raise ValueError(f"Invalid column: {column}")
        operators = ['=', '>', '<', '>=', '<=', 'LIKE', 'IN', 'NOT LIKE', 'NOT IN', 'BETWEEN']
        if operator not in operators:
            raise ValueError(f"Invalid operator: {operator}")
        if operator in ['=', '>', '<', '>=', '<=', 'LIKE']:
            if isinstance(value, str):
                value = value.replace("'", "''")
                self.conditions.append(f" {alias_column} {operator} {repr(value)}")
            elif isinstance(value, (int, float, Decimal)):
                self.conditions.append(f" {alias_column} {operator} {value}")
        elif operator in ['IN', 'NOT IN']:
            if isinstance(value, (list, tuple)):
                self.conditions.append(f" {alias_column} {operator} ({','.join(map(lambda x: repr(x), value))})")
            else:
                raise ValueError(f"Invalid value type for IN operator: {type(value)}")
        elif operator == 'BETWEEN':
            if isinstance(value, (tuple, list)) and len(value) == 2:
                self.conditions.append(f"{alias_column} {operator} {repr(value[0])} AND {repr(value[1])}")
            else:
                raise ValueError(f"Invalid value type for BETWEEN operator: {type(value)}")
        return self

    def build(self):
        #组建查询sql
        table_num = len(self.table_name)
        sql_build_ls = []
        for index in range(table_num):
            if index == 0:
                if table_num>1:
                    item_sql = f"SELECT {','.join(self.allowed_columns)} FROM `{self.table_name[0]}` AS t1"
                else:
                    item_sql = f"SELECT {','.join(self.allowed_columns)} FROM `{self.table_name[0]}`"
            else:
                item_sql = f" LEFT JOIN {self.table_name[index]} AS t{index+1} ON {' and '.join([ f't{index}.`{i}` = t{index+1}.`{i}`' for i in self.join_file_name[index-1]])}"
            sql_build_ls.append(item_sql)

        sql = '\n'.join(sql_build_ls)

        if self.conditions:
            sql += " WHERE " + " AND ".join(self.conditions)
        return sql

def get_company_by_plant(plant_code,db=None):
    """根据工厂代码获取公司代码"""
    if db is None:
        db = DbHelper()
    query_sql = "SELECT `company_code`, `plant_code` FROM `t_os_company_plant_alloc` "
    if plant_code:
        query_sql += " WHERE `plant_code` = {}".format(repr(plant_code))

    result_data = db.query_sql(query_sql)
    company_code = result_data[0].get('company_code') if result_data else ''

    return company_code


@ResetResponse(params=["plant_code","year","period","user_id"], excelName='投入凭证')
def get_work_order_input_detail_voucher(plant_code, year, period,**kwargs):
    code,msg,data,display = work_order_input_detail_query(plant_code, year, period)

    return ResponseData(code,msg, data,display=display)



def work_order_input_detail_query(plant_code, year, period,document_category = None,db = None,external_sn=False):
    # 1 获取所有投入凭证 在界面展示
    # 获取所有工单投入明细，工单投入明细包括材料成本分摊、费用分摊、作业成本、其他消耗。按凭证类别汇总展示。
    db = db or DbHelper()
    document_category = document_category or ['EMDC','FIDC']
    company_code = get_company_by_plant(plant_code,db=db)

    if company_code:


        builder = SafeQueryBuilder(['t_fi_integration_relation', 't_fi_doc_for_archiv_transfer_log', ],
                                   [['summary_unique_number']], allowed_columns_dic=
                                   {'t_fi_integration_relation': ["company_code", "year", "period", "document_category",
                                                                  "business_doc_sn", "accounting_document_type","posting_date",
                                                                  "fi_document_number", "summary_unique_number"],
                                    't_fi_doc_for_archiv_transfer_log': ['archiv_doc_num', 'posting_status',
                                                                         'external_sn']})
        builder.where('t1.company_code', '=', company_code)
        builder.where('t1.year', '=', year)
        builder.where('t1.period', '=', period)
        builder.where('t1.document_category', 'IN', document_category)
        builder.where('t1.accounting_document_type', 'IN', ['COE0', 'COT0', 'COC0'])


        if external_sn:
            builder.where('t2.external_sn', '=', '')
        # else:
        #     # AND(
        #     #     -- 条件1：FI凭证号不为空
        #     # fr.
        #     # `fi_document_number` != ''
        #     # OR
        #     # - - 条件2：存在冲销凭证
        #     # fh.
        #     # `reversal_document` != ''
        #     # )
        #     pass

        where_sql = builder.build()
        print(where_sql)
        data = db.query_sql(where_sql)
        code = 200
        msg = '成功'
    else:

        code = 500
        msg = '未查询到工厂对应的公司'
        data = []

    display = [
        {'field': 'company_code', 'description': '公司代码', "type": "varchar", "length": 255, "decimal": 0},
        {'field': 'year', 'description': '年度', "type": "year", "length": 4, "decimal": 0},
        {'field': 'period', 'description': '期间', "type": "varchar", "length": 2, "decimal": 0},
        {'field': 'posting_date', 'description': '过账日期', "type": "varchar", "length": 2, "decimal": 0},
        {'field': 'document_category', 'description': '单据类别', "type": "varchar", "length": 255, "decimal": 0},
        {'field': 'business_doc_sn', 'description': '凭证编码', "type": "varchar", "length": 255, "decimal": 0},
        {'field': 'accounting_document_type', 'description': '凭证类型', "type": "varchar", "length": 255, "decimal": 0},
        {'field': 'fi_document_number', 'description': '财务凭证编号', "type": "varchar", "length": 255, "decimal": 0},
        {'field': 'summary_unique_number', 'description': '汇总唯一号', "type": "varchar", "length": 255, "decimal": 0},
        {'field': 'archiv_doc_num', 'description': '归档凭证号', "type": "varchar", "length": 255, "decimal": 0},
        {'field': 'posting_status', 'description': '过账状态', "type": "varchar", "length": 255, "decimal": 0},
        {'field': 'external_sn', 'description': '外部凭证号', "type": "varchar", "length": 255, "decimal": 0},
    ]
    return code,msg,data,display

@ResetResponse(params=["plant_code","year","period","user_id"], excelName='投入凭证')
def push_work_order_input_detail_voucher(plant_code, year, period,user_id):

    # 点击推送按钮：
    # 基于界面中的公司代码、年度、期间、归档凭证号，过滤【归档凭证传输关系表】中，
    # SAP凭证编号为空，将其在【归档凭证抬头表】&【归档凭证行项目表】推送至【会计凭证过账接口】，
    # 推送给SAP系统，SAP生成财务凭证后返回结果，更新至【归档凭证传输关系表】，并执行界面刷新，更新界面的SAP凭证号的信息，注意是一个归档凭证对应多个SAP凭证，需自己增加行数显示。出现新的查询结果；
    db = DbHelper()
    code,msg,query_data,display = work_order_input_detail_query(plant_code, year, period, db = db,external_sn=True)

    if code == 200:
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
                    task_id = 601
                    log_code = '03003E0001'
                    help_text = '工单投入明细凭证推送SAP'
                    code, each_msg = ZZEXTPostPushSAP(user_id, task_id, plant_code, item, log_code, help_text)

                    resp_code_list.append(code)
                    if code != 200:
                        msg = each_msg

        _,_,data,display = work_order_input_detail_query(plant_code, year, period, db = db, external_sn=False)
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
        return ResponseData(code, msg, data, display=display)
    else:
        return ResponseData(code, msg, [], display=display)