#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@File    ：SummaryCertificate.py
@Date    ：2025/2/24
@explain : CDGM-01 gmgd 会计引擎 汇总凭证传输 接口
"""
import json
import time

from DbHelper import DbHelper
from libenhance import Request, Response, exec_operator, get_cnf
from OracleDB import OracleDB


def getSummaryCertificate(company_code: str, year: str, archiv_doc_num: str):
    """
    :param
    company_code   公司代码
    year  年度
    archiv_doc_num 归档凭证编号
    :return:
    返回参数	summary_unique_number	汇总唯一号		CHAR
    返回参数	TYPE	消息类型		CHAR	12			返回状态，成功S,失败E
    返回参数	MESSAGE	消息文本		CHAR	220
    返回参数	external_sn	    EBS凭证号
    返回参数	company_code	公司代码
    返回参数	posting_status	过账状态
    """
    # company_code    公司代码
    # year            年度
    # archiv_doc_num  归档凭证编号
    db = DbHelper()
    exp_columns = '''
                    'NEW' AS STATUS,
                    t1.summary_unique_number as REFERENCE1,  
                    t2.summary_unique_number as REFERENCE6,  
                    t1.company_code as SEGMENT1,
                    t1.posting_date as ACCOUNTING_DATE,
                    t1.posting_status,
                    t1.transaction_currency as CURRENCY_CODE,
                    NOW() as DATE_CREATED,
                    1090 as CREATED_BY,
                    'A' as ACTUAL_FLAG,
                    'CDGM_记帐凭证' as USER_JE_CATEGORY_NAME,
                    'MHGL' as USER_JE_SOURCE_NAME,
                    CASE
                        WHEN t1.exchange_rate=1.0 THEN NULL
                        ELSE t1.exchange_rate
                    END AS CURRENCY_CONVERSION_RATE,
                    t1.archiv_doc_num as REFERENCE5, 
                    t1.header_text as REFERENCE2,
                    t2.accounting_subjects as SEGMENT3,

                    CASE
                        WHEN t2.debit_credit_mark='Dr' THEN t2.amount_tc
                        ELSE NULL
                    END AS ENTERED_DR,

                    CASE
                        WHEN t2.debit_credit_mark='Cr' THEN t2.amount_tc
                        ELSE NULL
                    END AS ENTERED_CR,

                    CASE
                        WHEN t2.debit_credit_mark='Dr' THEN t2.amount_bc
                        ELSE NULL
                    END AS ACCOUNTED_DR,

                    CASE
                        WHEN t2.debit_credit_mark='Cr' THEN t2.amount_bc
                        ELSE NULL
                    END AS ACCOUNTED_CR,    

                    IFNULL( t2.cost_center, 0 ) AS SEGMENT2,
                    t2.prodosn AS REFERENCE21,
                    t2.item_text AS REFERENCE10,
                    IFNULL( t2.wbs_elements, '0' ) AS SEGMENT6,
                    IFNULL( t2.customization_field1, '0' ) AS SEGMENT7,
                    IFNULL( t2.customization_field2, '0' ) AS SEGMENT4,
                    IFNULL( t2.customization_field3, '0' ) AS SEGMENT5,
                    IFNULL( t2.customization_field4, '0' ) AS SEGMENT8,
                    DATE_FORMAT(t1.posting_date, '%Y-%m') AS PERIOD_NAME
 '''

    # t_fi_doc_for_archiv_head/t_fi_doc_for_archiv_details
    columns = exp_columns.strip()
    query_sql = '''
                SELECT {}
                FROM
                    t_fi_doc_for_archiv_head as t1
                LEFT JOIN t_fi_doc_for_archiv_details AS t2 
                ON t1.archiv_doc_num = t2.archiv_doc_num 
                and t1.company_code = t2.company_code 
                and t1.year = t2.year
                and t1.summary_unique_number = t2.summary_unique_number

                where 1=1
                '''.format(columns)

    summary_unique_number = ''
    external_sn = []
    posting_status = ''
    if company_code:
        query_sql += " and t1.company_code = {}".format(repr(company_code))
    if year:
        query_sql += " and t1.year = {}".format(repr(year))
    if archiv_doc_num:
        query_sql += " and t1.archiv_doc_num = {}".format(repr(archiv_doc_num))

    summaryCertificateData = []
    summaryCertificateData = db.query_sql(query_sql)

    print(summaryCertificateData)

    # OracleDB 连接
    Oracledb = OracleDB()

    if summaryCertificateData:

        summary_unique_number = summaryCertificateData[0].get('REFERENCE1', '')

        external_sn = []
        posting_status = summaryCertificateData[0].get('posting_status', '')
        # 插入ebs 数据库表   gl_interface

        # """
        #  insert all
        #  into oracle_table ( id, code ) values( 1 , '1' )
        #  into oracle_table ( id, code ) values( 2 , '2' )
        #  into oracle_table ( id, code ) values( 3 , '3' )
        #  into oracle_table ( id, code ) values( 4 , '4' )
        #  select 1 from dual
        # """

        col_ls = ['STATUS', 'REFERENCE1','REFERENCE6', 'SEGMENT1', 'ACCOUNTING_DATE', 'CURRENCY_CODE', 'DATE_CREATED', 'CREATED_BY',
                  'ACTUAL_FLAG', 'USER_JE_CATEGORY_NAME', 'USER_JE_SOURCE_NAME',
                  'CURRENCY_CONVERSION_RATE', 'REFERENCE5', 'REFERENCE2',
                  'SEGMENT3', 'ENTERED_DR',
                  'ENTERED_CR', 'ACCOUNTED_DR', 'ACCOUNTED_CR', 'SEGMENT2', 'REFERENCE21', 'REFERENCE10',
                  'SEGMENT6', 'SEGMENT7', 'SEGMENT4', 'SEGMENT5', 'SEGMENT8', 'PERIOD_NAME']
        # 'SEGMENT7', 'SEGMENT4', 'SEGMENT5', 'SEGMENT8',

        insert_sql = """
        insert all 
        """

        for item in summaryCertificateData:
            item.pop('posting_status')
            for i, j in item.items():

                if i in ['ENTERED_DR', 'ENTERED_CR', 'ACCOUNTED_DR', 'ACCOUNTED_CR']:
                    item[i] = float(j)
                elif i in ['ACCOUNTING_DATE', 'DATE_CREATED']:
                    item[i] = f"TO_DATE('{j}', 'SYYYY-MM-DD HH24:MI:SS')"
                elif i == 'CURRENCY_CONVERSION_RATE' and j == 0.0:
                    item[i] = 'NUll'
                elif i in ['SEGMENT4','SEGMENT5','SEGMENT6','SEGMENT7','SEGMENT8'] and j=='':

                    item[i] = repr('0')
                else:
                    item[i] = repr(j)

            # item = [i for i in item]
            # TO_DATE('2015-12-25 00:00:00', 'SYYYY-MM-DD HH24:MI:SS')
            # INSERT INTO gl_interface (STATUS,ACCOUNTING_DATE,CURRENCY_CODE,DATE_CREATED,CREATED_BY,ACTUAL_FLAG,USER_JE_CATEGORY_NAME,USER_JE_SOURCE_NAME) VALUES ('NEW',TO_DATE('2021-01-02', 'SYYYY-MM-DD'),1,TO_DATE('2021-01-02', 'SYYYY-MM-DD'),'11111',1,2,3)

            insert_sql += " into gl_interface ( {} ) values( {} )  ".format(','.join(col_ls), ','.join(item.values()))

        #     t1.summary_unique_number as REFERENCE1,
        #     t1.company_code as SEGMENT1,
        #     t1.posting_date as ACCOUNTING_DATE,
        # t1.archiv_doc_num as REFERENCE5,
        delete_sql = """
                DELETE
                FROM gl_interface
                WHERE  REFERENCE5 = {} AND SEGMENT1 = {} AND TO_CHAR(TO_DATE(PERIOD_NAME, 'YYYY-MM'), 'YYYY') = {} AND STATUS = 'NEW'
                """.format(repr(archiv_doc_num),repr(company_code),repr(year))

        print(delete_sql)
        Oracledb.execute(delete_sql)


        insert_sql += " select 1 from dual"
        print(insert_sql)
        row_count = Oracledb.execute(insert_sql)
        if row_count > 0:
            procedure_name = """
            cux_mh_if_pkg.submit_gl_request
            """
            out_params = {
                "x_return_status": str,  # 输出参数：返回状态
                "x_msg_count": int,  # 输出参数：消息数量
                "x_msg_data": str  # 输出参数：消息内容
            }
            status, count, msg_data = toEBS(Oracledb, procedure_name, out_params=out_params)
            print(status)
            print(count)
            print(msg_data)

            if status and status == 'S':
                # 调用成功，成功存储
                TYPE = status
                MESSAGE = '存储过程调用成功,凭证生成成功'
                external_sn=  msg_data.replace('..','').split('PZNUM:')
                external_sn.remove('')
            elif status and status == 'E':
                # 调用成功，存储失败
                TYPE = status
                MESSAGE = '存储过程调用成功,凭证生成失败'
                #STATUS_DESCRIPTION
                STATUS_sql = """
                select STATUS_DESCRIPTION
                from gl_interface
                WHERE  REFERENCE5 = {} AND SEGMENT1 = {} AND TO_CHAR(TO_DATE(PERIOD_NAME, 'YYYY-MM'), 'YYYY') = {} AND STATUS_DESCRIPTION IS NOT NULL
                """.format(repr(archiv_doc_num),repr(company_code),repr(year))

                STATUS_DESCRIPTION_data = Oracledb.query(STATUS_sql)

                if STATUS_DESCRIPTION_data:

                    #[{'STATUS_DESCRIPTION': '您违反了GL-6401主营业务成本科目规则！'}]
                    MESSAGE+=':'
                    for i, j in enumerate(STATUS_DESCRIPTION_data):
                        MESSAGE += "{}.{}".format(i + 1, j.get('STATUS_DESCRIPTION'))
            else:
                # 调用失败
                TYPE = "S"
                MESSAGE = '存储过程调用失败'

            return summary_unique_number, TYPE, MESSAGE, external_sn, company_code, posting_status
        else:
            TYPE = 'E'
            MESSAGE = '未查询到相关凭证数据'

            return summary_unique_number, TYPE, MESSAGE, external_sn, company_code, posting_status
    else:

        TYPE = 'E'
        MESSAGE = '未查询到相关凭证数据'
        return summary_unique_number, TYPE, MESSAGE, external_sn, company_code, posting_status


def toEBS(Oracledb, procedure_name, in_params=None, out_params=None):
    # 定义输入参数和输出参数
    # procedure_name = "cux_mh_if_pkg.submit_gl_request"

    # 调用存储过程
    result = Oracledb.call_procedure(procedure_name, in_params=in_params, out_params=out_params)

    print(result)
    # 打印结果
    if result:
        return result["x_return_status"], result["x_msg_count"], result["x_msg_data"]
    else:

        return None, None, None