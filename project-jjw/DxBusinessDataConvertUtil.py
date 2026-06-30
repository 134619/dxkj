#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@File    : DxBusinessDataConvertUtil.py
@Author  : tao.chang@dxdstech.com
@Date    : 2024/11/01 16:28
@explain : 业务数据转换工具
"""
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, getcontext

from DbHelper import DbHelper
from logger import LoggerConfig

logger = LoggerConfig("DxBusinessDataConvertUtil", isStream=True)


def get_exchange_rate(rate_type, date, currency_from, currency_to):
    """
    根据两个货币获取汇率
    :param rate_type: 汇率类型
    :param date: 日期
    :param currency_from: 货币1
    :param currency_to: 货币2
    :return code: 状态码
    :return msg: 消息
    :retuan rate: 汇率
    """

    code = 200
    msg = ""
    rate = 0

    if rate_type == "":
        code = 500
        msg = "请输入汇率类型"

        return code, msg, rate
    if date == "":
        date = datetime.now().strftime("%Y-%m-%d")

    if currency_from == "" or currency_to == "":
        code = 500
        msg = "请输入转换货币"

        return code, msg, rate

    if currency_from == currency_to:
        rate = 1
    else:
        due_date = ""
        due_rate = 0
        reverse_date = ""
        reverse_rate = 0

        dh = DbHelper()
        #  正向查找汇率
        query_sql = """
            SELECT
                `rate_from`,
                `rate_to`,
                `currency_unit_from`,
                `currency_unit_to`,
                `effective_start_date`
            FROM
                `t_bd_currency_rate_setting` 
            WHERE
                `rate_type` = '{}' 
                AND `currency_from` = '{}' 
                AND `currency_to` = '{}' 
            ORDER BY
                ABS(CAST(`effective_start_date` AS DATE) - CAST('{}' AS DATE))
                LIMIT 1
        """.format(rate_type, currency_from, currency_to, date)
        data = dh.query_sql(query_sql)
        if data:
            # “到比例”×“到货币单位”÷“从比例”÷“从货币单位”
            due_rate = data[0]["rate_to"] * data[0]["currency_unit_to"] / data[0]["rate_from"] / data[0][
                "currency_unit_from"]
            due_date = data[0]["effective_start_date"]

        query_sql = """
            SELECT
                `rate_from`,
                `rate_to`,
                `currency_unit_from`,
                `currency_unit_to`,
                `effective_start_date`
            FROM
                `t_bd_currency_rate_setting` 
            WHERE
                `rate_type` = '{}' 
                AND `currency_from` = '{}' 
                AND `currency_to` = '{}' 
            ORDER BY
                ABS(CAST(`effective_start_date` AS DATE) - CAST('{}' AS DATE))
                LIMIT 1
        """.format(rate_type, currency_to, currency_from, date)
        data = dh.query_sql(query_sql)
        if data:
            # “从比例”*“从货币单位”÷“到比例”÷“到货币单位”
            reverse_rate = data[0]["rate_from"] * data[0]["currency_unit_from"] / data[0]["rate_to"] / data[0][
                "currency_unit_to"]
            reverse_date = data[0]["effective_start_date"]

        if due_date >= reverse_date:
            rate = due_rate
        else:
            rate = reverse_rate

    return code, msg, round(rate, 6)


def convert_material_unit_qty(mat_code, primary_uom, secondary_uom, primary_uom_qty):
    """
    根据物料单位换算关系计算数量-主单位和辅单位调换位置进行查找转换关系
    :param mat_code: 物料编码
    :param primary_uom: 主单位
    :param secondary_uom: 辅单位
    :param primary_uom_qty: 主单位数量
    :return code: 状态码
    :return msg: 消息
    :retuan qty: 换算结果数量
    """
    code = 200
    msg = ""
    qty = 0
    if isinstance(primary_uom_qty, str):
        primary_uom_qty = float(primary_uom_qty)
    if primary_uom == "":
        code = 500
        msg = "请输入主单位primary_uom"
        return code, msg, qty
    if secondary_uom == "":
        code = 500
        msg = "请输入辅单位"
        return code, msg, qty

    if primary_uom == secondary_uom:
        qty = primary_uom_qty
        return code, msg, qty

    dh = DbHelper()
    query_sql = """
        SELECT
            `mat_code`,
            `primary_uom`,
            `primary_uom_qty`,
            `secondary_uom`,
            `secondary_uom_qty` 
        FROM
            `t_mmd_uom_conversion` 
        WHERE
            `mat_code` = '{}' 
        AND `primary_uom` = '{}' 
        AND `secondary_uom` = '{}'
        LIMIT 1
    """.format(mat_code, primary_uom, secondary_uom)
    print("query_sql", query_sql)
    data = dh.query_sql(query_sql)
    if data:
        # 设置 Decimal 上下文，提高精度
        getcontext().prec = 20  # 设置更高的精度
        getcontext().rounding = ROUND_HALF_UP  # 设置舍入模式

        x = Decimal(str(primary_uom_qty))
        y = Decimal(str(data[0]["primary_uom_qty"]))
        z = Decimal(str(data[0]["secondary_uom_qty"]))

        print("==================计算数据打印======================")
        print("x:", x)
        print("y:", y)
        print("z:", z)
        print("===================================================")

        # 分步计算，便于调试
        division_result = x / y
        multiplication_result = division_result * z
        quantized_result = multiplication_result.quantize(Decimal('0.001'))
        qty = float(quantized_result)
    # if data:
    #     print("==================计算数据打印======================")
    #     print("data", data)
    #     print("primary_uom_qty:",primary_uom_qty)
    #     print("===================================================")
    #     qty = float((Decimal(str(primary_uom_qty)) / Decimal(str(data[0]["primary_uom_qty"])) * Decimal(str(data[0]["secondary_uom_qty"]))).quantize(Decimal('0.001')))
    else:
        query_sql = """
            SELECT
                `mat_code`,
                `primary_uom`,
                `primary_uom_qty`,
                `secondary_uom`,
                `secondary_uom_qty` 
            FROM
                `t_mmd_uom_conversion` 
            WHERE
                `mat_code` = '{}' 
            AND `secondary_uom` = '{}' 
            AND `primary_uom` = '{}'
            LIMIT 1
        """.format(mat_code, primary_uom, secondary_uom)
        data = dh.query_sql(query_sql)
        if data:
            print(data)
            print(primary_uom_qty)
            print(data[0]["primary_uom_qty"])
            print(data[0]["secondary_uom_qty"])
            print(Decimal(str(primary_uom_qty)))
            print(Decimal(str(data[0]["primary_uom_qty"])))
            print(Decimal(str(data[0]["secondary_uom_qty"])))
            qty = float((Decimal(str(primary_uom_qty)) * Decimal(str(data[0]["primary_uom_qty"])) / Decimal(
                str(data[0]["secondary_uom_qty"]))))
        else:
            code = 500
            msg = "未找到该物料的转换关系"
    print("code", code)
    print("msg", msg)
    print("qty", qty)
    return code, msg, qty


def convert_material_unit_qty_new(mat_code, primary_uom, secondary_uom, primary_uom_qty):
    """
    根据物料单位换算关系计算数量-主单位或辅单位 满足任意一条转换关系
    :param mat_code: 物料编码
    :param primary_uom: 主单位
    :param secondary_uom: 辅单位
    :param primary_uom_qty: 主单位数量
    :return code: 状态码
    :return msg: 消息
    :retuan qty: 换算结果数量
    """
    code = 200
    msg = ""
    qty = 0
    if isinstance(primary_uom_qty, str):
        primary_uom_qty = float(primary_uom_qty)

    # 如果主单位和辅助单位一致,不进行运算,直接返回
    if primary_uom == secondary_uom:
        qty = primary_uom_qty
        return code, msg, qty

    dh = DbHelper()
    query_sql = """
        SELECT
            `mat_code`,
            `primary_uom`,
            `primary_uom_qty`,
            `secondary_uom`,
            `secondary_uom_qty` 
        FROM
            `t_mmd_uom_conversion` 
        WHERE
            `mat_code` = '{}' 
        AND (`primary_uom` = '{}' OR `secondary_uom` = '{}') 
        LIMIT 1
    """.format(mat_code, primary_uom, secondary_uom)
    print("query_sql", query_sql)
    data = dh.query_sql(query_sql)
    if data:
        print("data", data)
        qty = primary_uom_qty / data[0]["primary_uom_qty"] * data[0]["secondary_uom_qty"]
    else:
        code = 500
        msg = "未找到该物料的转换关系"
    print("code", code)
    print("msg", msg)
    print("qty", qty)
    return code, msg, qty