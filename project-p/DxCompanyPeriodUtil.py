# -*- coding: utf-8 -*-
"""
@File    : DxCompanyPeriodUtil.py
@Author  : dongliang.wang@dxdstech.com
@Date    : 2025/8/8 10:31
@explain : 业务辅助类-账期检查
"""
from DbHelper import DbHelper


# 校验物料账期
def check_material_period(company_code, posting_date):
    """
    校验物料账期
    :param company_code: 公司代码
    :param posting_date: 过账日期
    :param currency_from: 货币1
    :param currency_to: 货币2
    :return code: 状态
    :return msg: 消息
    """
    code = 200
    msg = ''
    year = posting_date[:4]
    period = posting_date[5:7]
    query_sql = """
        select `id`
        from `t_bd_material_period`
        where `company_code` = '{}'
        and `period_key` = 'ML'
        and `year` = '{}'
        and ( `period` = '{}'
        and `period_status` = '1' )
        or  ( `past_period` = '{}'
        and `previous_period_accounting_flag` = '1' )
    """.format(company_code, year, period, period)
    dh = DbHelper()
    data = dh.query_sql(query_sql)
    if data:
        pass
    else:
        code = 500
        msg = '该公司代码{}物料账期未开'.format(company_code)
    return code, msg


def check_fi_doc_period(company_code, posting_date):
    """
    校验财务账期
    :param company_code: 公司代码
    :param posting_date: 过账日期
    :return True: 账期已开
    :return False: 账期未开
    """

    year = posting_date[:4]
    period = posting_date[5:7]
    yearmonth = year + period
    query_sql = """
        select `id`
        from `t_fi_account_period`
        where `company_code` = '{}' and
        (( '{}' BETWEEN CONCAT(`year1_from`,IF(LENGTH(`period1_from`) = 2,`period1_from`,CONCAT('0',`period1_from`))) and CONCAT(`year1_to`,IF(LENGTH(`period1_to`) = 2,`period1_to`,CONCAT('0',`period1_to`))))
        or 
        ( '{}' BETWEEN CONCAT(`year2_from`,IF(LENGTH(`period2_from`) = 2,`period2_from`,CONCAT('0',`period2_from`))) and CONCAT(`year2_to`,IF(LENGTH(`period2_to`) = 2,`period2_to`,CONCAT('0',`period2_to`)))) )
    """.format(company_code, yearmonth, yearmonth)
    dh = DbHelper()
    data = dh.query_sql(query_sql)
    if data:
        return True
    else:
        return False