#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
    @File    : Z_posting_date_verify.py
    @Author  : yuan.cao@dxdstech.com
    @Date    : 2026-01-02 15:28
    @explain : 过账日期校验 文件
"""

import traceback

try:
    from DxCompanyPeriodUtil import (
        check_material_period,  # type:ignore 函数签名: check_material_period(company_code, posting_date) -> tuple[int, str]
    )
except:
    traceback.print_exc()


def verify_material_period(item:dict[str,str]|None,errors:list = [],company_codes:list = [],posting_dates:list = [],) -> str:
    """
        ### 🔮 校验物料过账期间

        :param item: 请求行
        :param errors: 错误列表 【引用操作 不反回】
        :param company_codes: 公司代码 item.key 默认取 company_code / uf_company_code 值
        :param posting_dates: 过账日期 item.key 默认取 posting_date / uf_posting_date 值
    """
    if isinstance(company_codes,str|int):
        company_codes = [company_codes]
    if isinstance(posting_dates,str|int):
        posting_dates = [posting_dates]
    company_code = item_getter(item,*company_codes,"company_code","uf_company_code")
    posting_date = item_getter(item,*posting_dates,"posting_date","uf_posting_date")
    code , msg = check_material_period(company_code, posting_date)
    if code != 200:
        errors.append(msg)
        return msg
    return ""

def item_getter(item,*args):
    """
        ### 👺 item 迭代getter 
    """
    if not args :
        raise Exception("item_getter 方法至少传递一个任意参数")
    value = item.get(args[0],"")
    if args[1:] and not value:
        return item_getter(item,*args[1:]) 
    
    return value

if __name__ == '__main__':
    d = {"a" : 1, "b" : 2}
    print(item_getter(d,"x","y","b"))
    print(item_getter(d,"x","y","s"))
    print(item_getter(d,"x"))
    print(item_getter(d ))
