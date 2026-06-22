#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@File    : ToolMethods.py
@Author  : ying.chen@dxdstech.com
@Date    : 2024/8/27 19:17
@explain : 公共方法 过滤、筛选、分页功能
"""
import enum
import inspect
import io
import json
import math
import os
import re
import time
import traceback
import zipfile
from datetime import datetime
from functools import reduce
from itertools import chain
from urllib.parse import quote

from dateutil.parser import parse
from DbHelper import DbHelper
from libenhance import Callback, Request, Response, SfException
from logger import LoggerConfig

db = DbHelper()

logger = LoggerConfig("ResponseSqlData", isStream=True)


def calc_time(func):
    """时间统计装饰器"""

    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        print(f"Function {func.__name__} took {round(end_time - start_time, 3)} seconds to execute.")
        return result

    return wrapper


OPERATORS = {
    'gte': '>=',
    'lte': '<=',
    'eq': '=',
    'neq': '!=',
    'in': 'LIKE',
    'nin': 'NOT LIKE',
}

AGGR_FUNCTIONS = ['count', 'avg', 'max', 'min', 'sum', 'concat', 'case', ' - ', ' + ', ' * ', ' \\ ']

EN_TO_ZH = {
    "id": "ID",
    "applicant_name": "申请人",
    "attachment_count": "关联附件",
    "batch_sn": "批次号",
    "batch_status": "批次状态",
    "component_descr": "组件描述",
    "cust_po_num": "客户订单号",
    "customer_descr": "客户描述",
    "cust_mat_code": "客户物料号",
    "cust_mat_desc": "客户物料描述",
    "deliver_uom": "交易单位",
    "delivery_uom": "交货单位",
    "ipn": "IPN编码",
    "ipn_desc": "IPN描述",
    "item_qty": "订单数量",
    "mat_descr": "物料描述",
    "mat_desc": "物料描述",
    "vendor_descr": "供应商描述",
    "vendor_name": "供应商描述",
    "po_type_descr": "订单类型描述",
    "mat_group_descr": "物料组描述",
    "mat_type_descr": "物料类型描述",
    "remain_item_qty": "剩余需求数量",
    "remain_pur_qty": "剩余采购数量",
    "re_deliver_qty": "未交货数量",
    "cur_deliver_qty": "本次交货数量",
    "usable_invntory_qty": "可用库存数量",
    "ed_code": "终端客户",
    "ed_name": "终端客户名称",
    "sp_code": "客户编码",
    "sp_name": "客户名称",
    "dp_code": "送达方",
    "dp_name": "送达方名称",
    "dp_addr": "送货地址",
    "dp_cont": "联系人",
    "dp_numb": "联系电话",
    "stoc_loc": "库存地点",
    "store_loc": "库存地点",
    "stoc_descr": "库存地点描述",
    "plant_name": "工厂描述",
    "plant_descr": "工厂描述",
    "plan_delivery_date": "计划交货日期",
    "packing_state": "拣配状态",
    "post_statu": "过账状态",
    "pr_type_descr": "采购申请类型描述",
    "pur_org_name": "采购组织描述",
    "pur_group_descr": "采购组描述",
    "create_name": "创建人",
    "update_name": "更新人",
    "create_id": "创建人",
    "updator": "更新人",
    "notes": "备注",
    "note": "备注",
    "note": "备注"
}


# 分页
def GetLimitData(source_data, page={}):
    """
    将数据分页处理
    :param source_data: 源数据
    :param page: 页码参数
    :return: 分页后的数据
    """
    page_num = page.get("page_num", 1)
    page_size = page.get("page_size", 0)
    if page_size != 0:
        # sum_count = len(source_data)
        sum_count = len(source_data) if isinstance(source_data, list) else source_data
        if isinstance(source_data, list):
            source_data = source_data[(int(page_num) - 1) * int(page_size): int(page_num) * int(page_size)]
        page_count = sum_count // int(page_size) + (sum_count % int(page_size) > 0)
        page = {"data_sum": sum_count, "page_num": int(page_num), "page_size": int(page_size), "page_sum": page_count}
    return source_data, page


def GetResponsePage(total_num, page={}):
    """
    获取返回的page
    :param total_num: 数据总数
    :param page: 页码参数
    :return: 分页后的数据
    """
    page_num = page.get("page_num", 1)
    page_size = page.get("page_size", 0)
    if page_size != 0:
        page_count = total_num // int(page_size) + (total_num % int(page_size) > 0)
        page = {"data_sum": total_num, "page_num": int(page_num), "page_size": int(page_size), "page_sum": page_count}
    return page


def read_zip_as_bytes(zip_path: str) -> bytes:
    """读取整个ZIP文件的二进制内容（含文件结构）"""
    try:
        with open(zip_path, 'rb') as f:
            return f.read()
    except FileNotFoundError:
        print(f"文件 {zip_path} 不存在")
        return b''


# 导出
def GetExportData(source_data, excel_file, en_to_zh, export_field=None, more_sheet=False):
    """
    将最终的数据生成excel文件流
    :param source_data: 要导入到文件的源数据 多个sheet页可以在数组中存放多个元素 [{"sheetname": data}]
    :param excel_file: 生成的文件名
    :param en_to_zh: 字段的中文字典  可以直接调用 GetEnToZh(source_data) 获取
    :return: 返回文件流
    """
    import pandas
    req = Request()
    res = Response()

    result = json.loads(req.apply_permission(json.dumps(source_data)))
    if result.get("code") != 200:
        print(result.get("code"))
        print(result.get("msg"))
        res.set_body(json.dumps({"code": result.get("code"), "msg": result.get("msg"), "data": []}))
        res.commit(True)
        return
    else:
        source_data = json.loads(result.get("data"))

    export_field = json.loads(req.body()).get("_payload_", {}).get("export_field", [])
    print("export_field>>>", export_field)
    new_data = []
    if export_field:
        for sheet in source_data:
            for sheet_name, data in sheet.items():
                sheet_data = []
                for item in data:
                    new_item = {}
                    for field in export_field:
                        if field in item:
                            new_item[field] = item[field]
                    sheet_data.append(new_item)
                new_data.append({sheet_name: sheet_data})
    else:
        for sheet in source_data:
            for sheet_name, data in sheet.items():
                sheet_data = []
                for item in data:
                    if more_sheet:
                        # 多个sheet页导出的情况下，display的格式为{'xxxx':[{},{}],'xxxx':[{},{}]}
                        sheet_data.append({field: item[field] for field in en_to_zh[sheet_name] if field in item})
                    else:
                        sheet_data.append({field: item[field] for field in en_to_zh if field in item})
                new_data.append({sheet_name: sheet_data})
    print("new_data>>>", new_data)
    source_data = new_data if new_data else source_data
    if len(source_data) == 1 and len(list(source_data[0].values())[0]) > 500000:
        sheet_name = list(source_data[0].keys())[0]
        source_data = list(source_data[0].values())[0]
        zip_filname = sheet_name.replace(".xlsx", ".zip")
        encoded_filename = quote(zip_filname)
        size = 500000
        with zipfile.ZipFile(zip_filname, 'w') as zipf:
            num = 1
            for i in range(0, len(source_data), size):
                filename = f'{sheet_name.split(".")[0]}{num}.xlsx'
                data = source_data[i:i + size]
                df = pandas.DataFrame(data)
                df.columns = [en_to_zh.get(item, '') for item in df.columns]
                excel_bytes = io.BytesIO()
                df.to_excel(excel_bytes, sheet_name=filename, index=False)
                excel_bytes.seek(0)
                data = excel_bytes.read()
                zipf.writestr(filename, data)
                num += 1

        byte_stream = read_zip_as_bytes(zip_filname)
        res.set_header("Content-Type", "application/zip")
    else:
        with pandas.ExcelWriter(excel_file, engine='xlsxwriter') as writer:
            for item in source_data:
                sheet_name = list(item.keys())[0]
                data = list(item.values())[0]
                if data:
                    df = pandas.DataFrame(data)
                    if more_sheet:
                        df.columns = [en_to_zh[sheet_name].get(item, '') for item in df.columns]
                    else:
                        df.columns = [en_to_zh.get(item, '') for item in df.columns]
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
        encoded_filename = quote(excel_file)
        with open(excel_file, 'rb') as file:
            byte_stream = file.read()
        if os.path.isfile(excel_file):
            os.system("rm -f {}".format(excel_file))
        res.set_header("Content-Type", "application/octet-stream")

    res.set_header("Content-Disposition", "attachment; filename*=UTF-8\'\'{}".format(encoded_filename))
    res.set_body(byte_stream)
    res.commit(True)


# display转entozh
def display_to_entozh(display):
    return {item["field"]: item["description"] for item in display}


# 获取字段对照
def GetEnToZh(table_list, source_data):
    """
    获取数据内字段的字段与中文字典
    :param table_list: 字段分布所在的表 ["table1","table2"...]
    :param source_data:  查询结果 [{"field1": "", "field2": ""},{},{}]
    :return: 查询结果中的字段的字段与中文字典  {"field1": "字段1", "field2": "字段2"...}
    """
    # lang_convert, field_desc = {}, {}
    # if source_data:
    #     field_list = list(source_data[0].keys())
    #     get_sql = f"""
    #     SELECT
    #         DISTINCT (column_name) AS column_name,
    #         column_comment AS column_comment
    #     FROM information_schema.COLUMNS
    #     WHERE table_name in ('{"','".join(table_list)}')
    #         AND column_name IN ('{"','".join(field_list)}')
    #     GROUP BY column_name
    #     """
    #     data = []
    #     data = db.query_sql(get_sql)
    #     for item in data:
    #         column_name = item["column_name"]
    #         column_comment = item["column_comment"]
    #         if "," in column_comment:
    #             column_comment = column_comment.split(",")[0]
    #         field_desc[column_name] = column_comment
    #
    #     for field in field_list:
    #         lang_convert[field] = field_desc.get(field) or EN_TO_ZH.get(field)
    #
    # return lang_convert
    lang_convert, field_desc = {}, {}
    if not source_data:
        return lang_convert

    field_list = list(source_data[0].keys())
    if not (table_list and field_list):
        return lang_convert

    if isinstance(table_list, list):
        table_columns_data = db.get_columns_by_table_multi(table_list)
        for table_name, column_details in table_columns_data.items():
            for column_detail in column_details:
                column_name = column_detail.get('name', '')
                column_comment = column_detail.get('comment', '')
                if column_name not in field_list:
                    continue
                # 注释含逗号时，取第一个部分（和原逻辑一致）
                if "," in column_comment:
                    column_comment = column_comment.split(",")[0]
                field_desc[column_name] = column_comment

    elif isinstance(table_list, str):
        column_details = db.get_columns_by_table(table_list)
        for column_detail in column_details:
            column_name = column_detail.get('name', '')
            column_comment = column_detail.get('comment', '')
            if column_name not in field_list:
                continue
            if "," in column_comment:
                column_comment = column_comment.split(",")[0]
            field_desc[column_name] = column_comment

    for field in field_list:
        lang_convert[field] = field_desc.get(field) or EN_TO_ZH.get(field)

    return lang_convert


# 获取display
def GetDisplay(table_list, source_data, is_all=True,other_field_name = {}):
    """
    获取数据内字段的完整 display
    :param table_list: 字段分布所在的表名列表 ["table1", "table2"] 或单表名 "table1"
    :param source_data: 查询结果列表 [{"field1": "val"}, ...]
    :return: 带有清洗后 type/length/decimal 等属性的 display 列表
    """
    display, field_list, field_details = [], [], {}
    exclude_fields = ['id', 'create_id', 'create_time', 'update_id', 'update_time', 'note', 'create_name',
                      'update_name']
    # 1. 提取查询结果中的字段名顺序
    if source_data and isinstance(source_data, list) and len(source_data) > 0:
        raw_fields = list(source_data[0].keys())
        if not is_all:
            field_list = [f for f in raw_fields if f not in exclude_fields]
        else:
            field_list = raw_fields
    if not field_list:
        return []
    # 2. 获取数据库表定义元数据
    db_data = {}
    if isinstance(table_list, list):
        db_data = db.get_columns_by_table_multi(table_list)
    elif isinstance(table_list, str):
        db_data = {table_list: db.get_columns_by_table(table_list)}

    # 3. 建立字段属性的映射索引
    for t_name, columns in db_data.items():
        for col in columns:
            name = col.get('name')
            # 只要是在查询结果 field_list 里的字段，就记录其属性
            if name in field_list:
                # 处理注释：取第一部分
                comment = col.get('comment') or ''
                if "," in comment:
                    comment = comment.split(",")[0]

                # --- 类型清洗逻辑 ---
                raw_type = str(col.get('type', 'varchar')).lower()

                # 1. 去掉括号及其内容，例如 "varchar(32)" -> "varchar"
                if "(" in raw_type:
                    raw_type = raw_type.split("(")[0]

                # 2. 类型转换：bigint -> int
                final_type = 'int' if 'bigint' in raw_type else raw_type

                field_details[name] = {
                    "field": name,
                    "description": comment or EN_TO_ZH.get(name) or name,
                    "type": final_type,
                    "length": col.get('length') or col.get('precision') or 0,
                    "decimal": col.get('scale') or col.get('decimal') or 0,
                    "readOnly": False,
                    "required": False
                }

    # 4. 完全基于 field_list 的顺序构建最终结果
    for field in field_list:
        if field in field_details:
            display.append(field_details[field])
        else:
            # 针对计算字段或未匹配到的字段提供保底配置
            display.append({
                "field": field,
                "description": other_field_name.get(field) or "未知字段",
                "type": "varchar",
                "length": 0,
                "decimal": 0,
                "readOnly": False,
                "required": False
            })
    return display


# 获取display
def GetAllDisplay(table_name):
    """
    获取数据表字段的display
    :param table_name: 数据表
    :return: 查询结果中的字段的display [{"field": field1, "description": 字段1},{"field": field2, "description": 字段2},{}...]
    """
    data, display = [], []
    if table_name:
        data = db.get_columns_by_table(table_name)
        for item in data:
            name = item.get('name', '')
            comment = item.get('comment', '')
            if "," in comment:
                comment = comment.split(",")[0]
            display.append({"field": name, "description": comment or EN_TO_ZH.get(name)})

    return display


# 获取display更多字段版
def GetDisplayMoreField(table_name, is_all=False, filter_list=None):
    """
    获取数据表字段的display
    :param table_name: 数据表
    :return: 查询结果中的字段的display 返回前端需要的所有display字段
    """
    if table_name:
        display = []
        table_data = db.get_table_by_name(table_name)
        for table_name, item in table_data.get("columns", {}).items():

            if not is_all and item['name'] in ['id', 'create_id', 'create_time', 'update_id', 'update_time', 'note']:
                continue
            if filter_list and item['name'] not in filter_list:
                continue
            if item['name'].startswith('reserved'):
                continue

            if item["type"].startswith("decimal"):
                item["scale"] = int(item["type"].split(',')[1].rstrip(')'))

            if item["type"] == "bigint":
                item["type"] = "int"

            display.append({
                "field": item['name'],
                "description": item['comment'] or EN_TO_ZH.get(item['name']) or "未知字段",
                "type": item['type'].split("(")[0],
                "length": item['length'] or item['precision'],
                "decimal": item['scale'] or 0,
                "readOnly": False,
                "required": False
            })
        return display

    return []


def is_contain_chinese(text):
    if isinstance(text, str):
        return bool(re.search('[\u4e00-\u9fff]', text))
    else:
        return False


def get_pinyin(item):
    from pypinyin import Style, pinyin
    return ''.join(chain.from_iterable(pinyin(item, style=Style.NORMAL)))


def robust_chinese_sort_key(item, field_name):
    """
    健壮的中文排序键函数
    处理各种数据类型和边界情况
    """
    # 1. 获取字段值
    value = item.get(field_name)

    # 2. 转换为安全的字符串
    if value is None:
        safe_str = ''
    elif isinstance(value, (int, float)):
        # 数字类型直接转为字符串
        safe_str = str(value)
    elif isinstance(value, str):
        safe_str = value
    else:
        # 其他类型尝试转换
        try:
            safe_str = str(value)
        except Exception:
            safe_str = ''

    # 3. 处理空字符串
    if not safe_str:
        return ''

    # 4. 判断是否包含中文
    try:
        # 先检查 is_contain_chinese 是否存在且可调用
        if callable(is_contain_chinese):
            has_chinese = is_contain_chinese(safe_str)
        else:
            # 如果函数不存在，使用简单判断
            has_chinese = any('\u4e00' <= char <= '\u9fff' for char in safe_str)
    except Exception:
        # 如果判断函数报错，假设不包含中文
        has_chinese = False

    # 5. 根据是否包含中文返回相应的键值
    if has_chinese:
        try:
            # 尝试获取拼音
            if callable(get_pinyin):
                pinyin_result = get_pinyin(safe_str)
                # 确保返回的是字符串
                return str(pinyin_result) if pinyin_result is not None else safe_str
            else:
                return safe_str
        except Exception:
            # 拼音转换失败，返回原字符串
            return safe_str
    else:
        return safe_str


def sort_data(data, sort_info):
    """
    对数据字段进行排序
    :param data: 数据[{},{},{},......]
    :param sort_info:  [
            {
                "name": "字段名称",
                "sort": "asc" //asc（升序）、desc（降序）
            },.......
        ]
    :return:排序后得到的数据
    """
    int_field_names = ['so_items', 'priority_code']
    for sort_item in sort_info[::-1]:
        name = sort_item['name']
        sort_order = sort_item['sort']
        # data.sort(key=lambda x: x.get(name))
        # data.sort(key=lambda x: (x.get(name) is None, x.get(name)))

        if name in int_field_names:
            data.sort(key=lambda x: int(x.get(name) or 0))
        else:
            data.sort(key=lambda x: robust_chinese_sort_key(x, name))

        if sort_order == 'desc':
            data.reverse()

    return data


@calc_time
def filter_data(data, filter_info):
    """
    对数据进行组件筛选
    :param data: 表数据[{},{},{}.....]
    :param filter_info: {
            "condition": "or", //and（所有）、or（任一）
            "content": [
                {
                    "name": "字段名称",
                    "rule": "gte", //eq(等于)、neq（不等于）、gte（大于等于）、lte（小于等于）、in（包含）、nin（不包含）
                    "value": "筛选值"
                }....
            ]
        }
    :return:筛选以后得到的数据
    """
    condition = filter_info.get('condition', 'and')
    content = filter_info.get('content', [])
    if not content:
        return data

    filtered_data = []
    for item in data:
        if condition == 'and':
            # 默认所有条件都满足
            is_match = True
            for filter_item in content:
                is_match &= apply_filter(item, filter_item)
                # 如果已经有一个条件不满足，就可以跳出循环了

                if not is_match:
                    break
            if is_match:
                filtered_data.append(item)
        elif condition == 'or':
            # 默认没有条件满足
            is_match = False
            for filter_item in content:
                is_match |= apply_filter(item, filter_item)
                # 如果已经有一个条件满足，就可以跳出循环了
                if is_match:
                    break
            if is_match:
                filtered_data.append(item)
    return filtered_data


def apply_filter(item, filter_item):
    field_name = filter_item.get('name')
    rule = filter_item.get('rule')
    value = filter_item.get('value')
    field_value = item.get(field_name)
    if not isinstance(field_value, str) and isinstance(value, str):
        if isinstance(field_value, float):
            field_value = str(field_value).rstrip('0').rstrip('.')
        else:
            field_value = str(field_value)
    if rule == 'eq':
        return field_value == value
    elif rule == 'neq':
        return field_value != value
    elif rule in ['gte', 'lte']:
        try:
            field_value = float(field_value)
            value = float(value)
            if rule == 'gte':
                return field_value >= value
            else:
                return field_value <= value
        except ValueError:
            return False
    elif rule in ['in', 'nin']:
        if rule == 'in':
            return str(value) in str(field_value)
        if rule == 'nin':
            return str(value) not in str(field_value)
    else:
        return False


@calc_time
def pandas_filter_data(data, filter_info):
    """

    :param data: [{},{},{},......]
    :param filter_info: {
        "condition":"and"
        "content":[
        {"name":"age","rule":"gt","value":"10"} // 找age>10 的
        ]
    }
    :return:
    """
    if not data:
        return data
    import pandas as pd
    df = pd.DataFrame(data)
    condition_type = filter_info.get('condition', 'and')
    content = filter_info.get('content', [])
    conditions = []
    if not content:
        return data
    if not data:
        return data
    for filter_item in content:
        name = filter_item.get('name')
        rule = filter_item.get('rule')
        value = filter_item.get('value')
        if name not in data[0]:
            continue
        if isinstance(data[0].get(name), int):
            if value and isinstance(value, str) and value.strip():
                value = int(value)
        if isinstance(data[0].get(name), float):
            if value and isinstance(value, str) and value.strip():
                value = float(value)
        if rule == 'gt':
            condition = df[name] > value
        elif rule == 'gte':
            condition = df[name] >= value
        elif rule == 'lt':
            condition = df[name] < value
        elif rule == 'lte':
            condition = df[name] <= value
        # elif rule == 'eq':
        elif rule == 'eq' or rule == 'empty':
            condition = df[name] == value
        elif rule == 'neq':
            condition = df[name] != value
        elif rule == 'in':
            # condition = df[name].isin(value)
            df[name] = df[name].fillna("").astype(str)
            condition = df[name].str.contains(str(value))
        elif rule == 'not in':
            # condition = ~df[name].isin(value)
            df[name] = df[name].fillna("").astype(str)
            condition = ~df[name].str.contains(str(value))
        elif rule == 'nin':
            # condition = ~df[name].isin(value)
            df[name] = df[name].fillna("").astype(str)
            condition = ~df[name].str.contains(str(value))
        conditions.append(condition)
    if not conditions:
        return data
    if condition_type == 'or':
        combined_condition = reduce(lambda x, y: x | y, conditions)
    else:
        combined_condition = reduce(lambda x, y: x & y, conditions)
    filtered_df = df[combined_condition]
    filtered_df = filtered_df.fillna(value='')
    return filtered_df.to_dict(orient='records')


@calc_time
def pandas_sort_data(data, sort_info, reverse=False):
    """
    对数据字段进行排序
    :param data: 数据[{},{},{},......]
    :param sort_info:  [
            {
                "name": "字段名称",
                "sort": "asc" //asc（升序）、desc（降序）
            },.......
        ]
    :return:排序后得到的数据
    """
    if not data:
        return data
    import pandas as pd
    df = pd.DataFrame(data)
    by = []
    ascending = []
    # for sort_item in sort_info[::-1]:
    if reverse:
        sort_info = sort_info[::-1]
    for sort_item in sort_info:
        name = sort_item['name']
        sort_order = sort_item['sort']
        by.append(name)
        ascending.append(sort_order == 'asc')
    sorted_df = df.sort_values(by=by, ascending=ascending)
    sorted_df = sorted_df.fillna(value='')
    return sorted_df.to_dict(orient='records')


class InvalidPage(Exception):
    pass


class PageNotAnInteger(InvalidPage):
    pass


class EmptyPage(InvalidPage):
    pass


class Paginator:
    """分页类"""

    def __init__(self, items, per_page=0):
        self.items = items
        self.per_page = per_page if per_page else len(self.items)
        self.total_pages = self.num_pages()

    def get_page(self, page_num):
        """Return a valid page, even if the page argument isn't a number or isn't in range."""
        try:
            number = self.validate_number(page_num)
        except PageNotAnInteger:
            number = 1
        except EmptyPage:
            number = self.total_pages

        start_idx = (number - 1) * self.per_page
        end_idx = start_idx + self.per_page
        return self.items[start_idx:end_idx]

    def num_pages(self):
        if not self.per_page:
            return 0
        elif not len(self.items):
            return 0
        else:
            return len(self.items) // self.per_page + (1 if len(self.items) % self.per_page > 0 else 0)

    def validate_number(self, number):
        """Validate the given 1-based page number."""
        try:
            if isinstance(number, float) and not number.is_integer():
                raise ValueError
            number = int(number)
        except (TypeError, ValueError):
            raise PageNotAnInteger("invalid_page")
        if number < 1:
            raise EmptyPage("min_page")
        if number > self.total_pages:
            raise EmptyPage("no_results")
        return number


def check_date_format(date_str):
    formatted_time = ''

    try:
        datetime_format = parse(date_str)
        formatted_time = datetime_format.strftime("%Y-%m-%d %H:%M:%S")
        is_valid = True
    except ValueError:
        is_valid = False
    except Exception as e:
        print(e)
        is_valid = False

    return is_valid, formatted_time


def generate_raw_sql(prefix_filter, filter_info, sort_info, table_alias, alias_back_quote_mode=True):
    """
    Generate WHERE HAVING and SORT SQL 如果有聚合函数生成字段，会生成 HAVING 子句，拼接到 sort sql前面
    :param prefix_filter: 前端参数里 data 前置筛选字典
    :param filter_info: _payload_ 前端参数里 filter_info 筛选信息字典
    :param sort_info: _payload_ 前端参数里 sort_info 排序信息字典
    :param table_alias: 通过表字段构造的字段到表别名的字典
    :param alias_back_quote_mode: 表别名是否加反引号（默认True：加，保持原有逻辑；传False：表别名不加反引号）
    :return: raw_where_sql, raw_sort_sql
    """
    raw_where_sql, raw_having_sql, raw_sort_sql = '', '', ''
    where_prefix_list, having_parts, where_info_list = [], [], []
    condition = ' ' + filter_info.get('condition', '') + ' '

    if alias_back_quote_mode:
        alias_back_quote_mode = table_alias.get('back_quote', True)  # 兼容原有代码, 自动判断表别名是否带反引号
        print(alias_back_quote_mode)

    if prefix_filter and isinstance(prefix_filter, dict):
        for field_name, field_value in prefix_filter.items():
            if not field_value or (field_name == 'mode' and isinstance(field_value, str)):
                continue
            alias_name = table_alias.get(field_name)
            # print('alias_name:', alias_name)

            if alias_name:
                if '.' not in alias_name:
                    # 表别名是否加反引号由 alias_back_quote_mode 控制
                    alias_part = f'`{alias_name}`' if alias_back_quote_mode else alias_name
                    field_name = alias_part + '.' + f'`{field_name}`'
                else:
                    if 'if' in alias_name or 'substring' in alias_name:
                        field_name = alias_name
                    else:
                        alias_table = alias_name.split('.')[0]
                        field_name = alias_name.split('.')[-1]
                        # 表别名是否加反引号由 alias_back_quote_mode 控制
                        alias_part = f'`{alias_table}`' if alias_back_quote_mode else alias_table
                        if "`" in field_name:
                            field_name = alias_part + '.' + f'{field_name}'
                        else:
                            field_name = alias_part + '.' + f'`{field_name}`'
            else:
                field_name = f'`{field_name}`'

            if field_value and isinstance(field_value, (int, float)):
                where_prefix_part = '{} = {}'.format(field_name, field_value)
                where_prefix_list.append(where_prefix_part)
            elif field_value and isinstance(field_value, str):
                where_prefix_part = '{} = {}'.format(field_name, repr(field_value))
                where_prefix_list.append(where_prefix_part)
            elif field_value and isinstance(field_value, list):
                has_wildcard = any('*' in str(v) for v in field_value if isinstance(v, str))

                if has_wildcard:
                    cond_parts = []
                    for val in field_value:
                        if not isinstance(val, str):
                            val = str(val)
                        safe_val = val.replace("'", "''")
                        if '*' in val:
                            pattern = safe_val.replace('*', '%')
                            cond_parts.append(f"{field_name} LIKE '{pattern}'")
                        else:
                            cond_parts.append(f"{field_name} = '{safe_val}'")
                    where_prefix_part = '(' + ' OR '.join(cond_parts) + ')'
                else:
                    where_prefix_part = '{} in ({})'.format(field_name, ', '.join(map(repr, field_value)).strip(','))
                if field_name in ['forecast_plan_date']:  # 日期字段不是日期区间筛选
                    where_prefix_list.append(where_prefix_part)
                    continue
                if "`" in field_name:
                    endswith_str = "date`"
                    endswith_time_str = "time`"
                else:
                    endswith_str = "date"
                    endswith_time_str = "time"
                if (field_name.endswith(endswith_str) or field_name.endswith(endswith_time_str)) and len(
                        field_value) == 2:
                    start_date_valid, start_time = check_date_format(field_value[0])
                    end_time = str(field_value[1])
                    if end_time and len(end_time) == 10:
                        end_time += " 23:59:59"
                    end_date_valid, end_time = check_date_format(end_time)
                    if start_date_valid and end_date_valid:
                        if 'date' in field_name and 'time' in field_name:
                            where_prefix_part = '{} BETWEEN TIMESTAMP {} AND TIMESTAMP {}'.format(field_name, repr(field_value[0]),
                                                                              repr(field_value[1]))
                        else:
                            where_prefix_part = '{} BETWEEN TIMESTAMP {} AND  TIMESTAMP {}'.format(field_name, repr(start_time),
                                                                              repr(end_time))
                where_prefix_list.append(where_prefix_part)
        if where_prefix_list:
            raw_where_sql = ' AND '.join(where_prefix_list) + ' AND '

    if filter_info and isinstance(filter_info, dict):
        for item in filter_info.get('content', []):
            if not item:
                continue
            having_field = False
            name = item.get('name')
            rule = item.get('rule')
            field_value = item.get('value')
            alias_name = table_alias.get(name)

            if rule in ['in', 'nin']:
                field_value = '%' + str(field_value) + '%'

            if alias_name:
                if '(' in alias_name or ')' in alias_name:
                    for agg_function in AGGR_FUNCTIONS:
                        if agg_function in alias_name.lower():
                            having_field = True
                            break
                elif '.' not in alias_name:
                    if alias_back_quote_mode:
                        name = f'`{alias_name}`' + '.' + f'`{name}`'
                    else:
                        name = f'{alias_name}' + '.' + f'`{name}`'
                else:
                    name = alias_name
            else:
                name = f'`{name}`'

            where_part = '{} {} {}'.format(name, OPERATORS.get(rule), repr(field_value))
            if having_field:
                having_parts.append(where_part)
            else:
                where_info_list.append(where_part)

    if where_info_list and condition:
        raw_where_sql += condition.join(where_info_list)
    if raw_where_sql:
        raw_where_sql = 'WHERE ' + raw_where_sql
        raw_where_sql = raw_where_sql.rstrip().rstrip('AND')
    if having_parts and condition:
        raw_having_sql = condition.join(having_parts)
        raw_having_sql = 'HAVING ' + raw_having_sql

    if sort_info and isinstance(sort_info, list):
        sort_info_list = []
        for item in sort_info:
            if item:
                name = item.get('name', '')
                if '.' in name:
                    alias_name = name.split('.')[0]
                    field_name = name.split('.')[-1]
                    # 排序部分：表别名是否加反引号由 alias_back_quote_mode 控制
                    alias_part = f'`{alias_name}`' if alias_back_quote_mode else alias_name
                    name = alias_part + '.' + f'`{field_name}`' + item.get('sort', '')
                else:
                    name = f'`{name}`' + item.get('sort', '')
                sort_info_list.append(name)

        if sort_info_list:
            raw_sort_sql = ' ORDER BY ' + ', '.join(sort_info_list)
            if raw_sort_sql and 'update_name' in raw_sort_sql:
                raw_sort_sql = raw_sort_sql.replace('update_name', 'CONVERT(`update_name` USING gbk)')
            if raw_sort_sql and 'create_name' in raw_sort_sql:
                raw_sort_sql = raw_sort_sql.replace('create_name', 'CONVERT(`create_name` USING gbk)')

    if raw_having_sql:
        raw_sort_sql = raw_having_sql + raw_sort_sql

    raw_where_sql = raw_where_sql.replace('``', '`')
    raw_sort_sql = raw_sort_sql.replace('``', '`')
    return raw_where_sql, raw_sort_sql


def generate_limit_sql(page_size, page_number):
    """通过LIMIT和OFFSET子句来实现后端分页"""
    raw_limit_sql = ''
    try:
        if isinstance(page_number, float) and not page_number.is_integer():
            raise ValueError
        page_number = int(page_number)
        offset = (page_number - 1) * page_size
    except Exception as e:
        offset = ''
        print(e)

    try:
        if isinstance(page_size, float) and not page_size.is_integer():
            raise ValueError
        page_size = int(page_size)
        limit = page_size
    except Exception as e:
        limit = ''
        print(e)

    if limit:
        raw_limit_sql += f" LIMIT {limit} "
    if offset:
        raw_limit_sql += f" OFFSET {offset} "

    return raw_limit_sql


def get_total_count(query_sql):
    """查询数据总条数"""
    result_data, total_count = [], 0
    query_count_sql = """
        SELECT
            count( 1 ) as `total_count`
        FROM
            (
            {}
            ) AS t1
    """.format(query_sql)

    try:
        result_data = db.query_sql(query_count_sql)
    except Exception as e:
        print(e)
    if result_data:
        count_info = result_data[0]
        total_count = count_info.get('total_count')

    return total_count


def create_table_alias(columns):
    """生成字段到表别名的映射字典"""
    table_alias = {'back_quote': False}

    # 内部辅助函数：去除 MAX, MIN, AVG, SUM 等聚合函数
    def clean_agg_functions(text):
        # 匹配 MAX(content) 并提取 content，支持嵌套括号的简单处理
        # 这里用正则替换掉常见的聚合函数前缀和对应的末尾括号
        # 也可以根据需求增加 SUM|AVG|MIN|COUNT
        pattern = r'^(?:MAX|MIN|AVG|SUM|COUNT)\s*\((.*)\)$'
        text = text.strip()
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return text

    if '\n' in columns:
        field_names = [line.strip() for line in columns.splitlines() if line.strip()]
    else:
        field_names = [item.strip() for item in columns.split(',') if item.strip()]

    for field_name in field_names:
        field_name = field_name.strip().rstrip(',')
        try:
            if ' as ' in field_name.lower():
                # 处理有 AS 别名的情况: MAX(`di`.`id`) AS `id`
                parts = re.split(r'\s+as\s+', field_name, flags=re.IGNORECASE)
                raw_expression = parts[0].strip()  # 例如: MAX(`di`.`id`)
                alias_field = parts[1].strip().replace('`', '')  # 例如: id

                # 去掉聚合函数
                clean_expression = clean_agg_functions(raw_expression)

                # 如果去掉 MAX 后依然有表别名引用（如 `di`.`id`）
                table_alias[alias_field] = clean_expression

                # 标记是否需要反引号

                if '.' in clean_expression:
                    parts = clean_expression.split('.')
                    alias = parts[0].strip().replace('`', '')
                    field = parts[-1].strip().replace('`', '')
                    if '`' in alias:
                        table_alias['back_quote'] = True

            elif '.' in field_name:
                # 处理没有 AS 但有点号的情况: `di`.`id`
                clean_expression = clean_agg_functions(field_name)
                if '.' in clean_expression:
                    parts = clean_expression.split('.')
                    alias = parts[0].strip().replace('`', '')
                    field = parts[-1].strip().replace('`', '')
                    table_alias[field] = alias
                    if '`' in alias:
                        table_alias['back_quote'] = True
        except Exception as e:
            print(f'Error processing field: {field_name} | {e}')

    return table_alias


def convert_np_types(obj):
    import numpy as np
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: convert_np_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_np_types(i) for i in obj]
    else:
        return obj


def replaceTemplate(template, data):
    import re
    # 匹配 {} 内的占位符
    pattern = r"\{(\w+)\}"

    # 查找所有占位符
    placeholders = re.findall(pattern, template)

    # 替换占位符为 data 中的值
    for placeholder in placeholders:
        if placeholder in data:
            template = template.replace(f"{{{placeholder}}}", str(data[placeholder]))

    return template


def ResetResponse(**decorator_kwargs):
    """
    :param decorator_kwargs:
        params: ["id","name"] 获取 {"data":{"id":"","name":""}}
        _payload_: 如果为 True 方法上必须使用 payload 接收
        sheetNames: 导出文件多 Sheet 配置 [{"sheet_name":"数据对应的 key"}]
        excelName: 导出文件名
        pagination: 是否分页
        isSave: 是否是增删改的统一操作 如果为 True 方法上必须使用 insert,update,delete 接收
        allParams: 接受所有的参数
        keepAccuracy: float 类型保留20位小数
        floatToZero: float 小数位大于10 默认趋近于0 设置 0 keepAccuracy 和 floatToZero 只能允许一个为True
        sort_reverse: 排序设置优先级
    :return:
    """

    def decorator(func):
        def wrapper():
            params = decorator_kwargs.get("params", [])
            _payload_ = decorator_kwargs.get("_payload_", False)
            sheetNames = decorator_kwargs.get("sheetNames", [])
            excelName = decorator_kwargs.get("excelName", None)
            pagination = decorator_kwargs.get("pagination", False)
            isSave = decorator_kwargs.get("isSave", False)
            allParams = decorator_kwargs.get("allParams", False)
            keepAccuracy = decorator_kwargs.get("keepAccuracy", False)
            floatToZero = decorator_kwargs.get("floatToZero", False)
            reqHeader = decorator_kwargs.get("reqHeader", False)
            user_id = decorator_kwargs.get("user_id", False)
            sort_reverse = decorator_kwargs.get("sort_reverse", False)
            try:
                req = Request()
                body = json.loads(req.body())
                all_data = body.get("data", {})
                if isSave and isinstance(all_data, list):
                    insertData = []
                    updateData = []
                    deleteData = []
                    for data in all_data:
                        if data.get("_tag_") == "insert":
                            insertData.append(data)
                        elif data.get("_tag_") == "update":
                            updateData.append(data)
                        elif data.get("_tag_") == "delete":
                            deleteData.append(data)
                    kwargs = {"insert": insertData, "update": updateData, "delete": deleteData,
                              "user_id": req.header("user_id")}
                    if allParams:
                        kwargs.update(body)
                    # print("kwargs", kwargs)
                else:
                    # kwargs = {i: all_data.get(i) for i in params}
                    kwargs = all_data
                    for i in params:
                        if i not in kwargs:
                            kwargs.update({i: all_data.get(i)})
                payload = body.get("_payload_", {})
                if _payload_:
                    kwargs.update({"_payload_": body.get("_payload_", {})})
                if reqHeader:
                    kwargs.update({"reqHeader": req.header()})
                if user_id:
                    kwargs.update({"user_id": req.header("user_id")})
                result = func(**kwargs)
                if result:
                    if isinstance(result, ResponseData):
                        result = result.__dict__

                    if payload:
                        rule = result.get("rule", {})
                        result_data = result.get("data")
                        sort_info = payload.get("sort_info", [])
                        filter_info = payload.get("filter_info", {})
                        page = payload.get("page", {})
                        if filter_info:
                            rule["filter_info"] = filter_info
                            # result_data = filter_data(result_data, filter_info)
                            result_data = pandas_filter_data(result_data, filter_info)
                        if sort_info:
                            rule["sort_info"] = sort_info
                            # result_data = sort_data(result_data, sort_info)
                            result_data = pandas_sort_data(result_data, sort_info, sort_reverse)
                        if pagination and not (body.get("_payload_", {}).get("export_excel") and excelName):
                            result_data, result_page = GetLimitData(result_data, page)
                            result["page"] = result_page
                        result["data"] = result_data
                        result["rule"] = rule
                    if body.get("_payload_", {}).get("export_excel") and excelName:
                        excelName = replaceTemplate(excelName, all_data)
                        if len(excelName) > 31:
                            excelName = excelName[:28] + "..."
                        if keepAccuracy and not floatToZero:
                            import pandas as pd
                            df = pd.DataFrame(result["data"])
                            df = df.applymap(lambda x: f"{x:.20f}" if isinstance(x, (float,)) and x != 0 else x)
                            df = df.fillna("")
                            result["data"] = df.to_dict("records")

                        if floatToZero and not keepAccuracy:
                            import pandas as pd
                            df = pd.DataFrame(result["data"])
                            df = df.applymap(
                                lambda x: 0 if isinstance(x, (float,)) and math.isclose(x, 0, abs_tol=1e-5) else x)
                            df = df.fillna("")
                            result["data"] = df.to_dict("records")

                        if len(sheetNames) == 0:
                            GetExportData([{f"{excelName}": result.get("data")}], f"{excelName}.xlsx",
                                          display_to_entozh(result.get("display")),
                                          export_field=body.get("_payload_", {}).get("export_field", []))
                        elif len(sheetNames) == 1:
                            sheet_name = sheetNames[0]
                            GetExportData([{f"{sheet_name}": result.get("data")}], f"{excelName}.xlsx",
                                          display_to_entozh(result.get("display")),
                                          export_field=body.get("_payload_", {}).get("export_field", []))
                        elif len(sheetNames) > 1:
                            excel_data = []
                            zh_name = {}
                            for sheet_name in sheetNames:
                                if isinstance(result.get("data"), dict):
                                    excel_data.append({f"{sheet_name}": result.get("data").get(sheet_name)})
                                else:
                                    excel_data.append({f"{sheet_name}": result.get("data")})
                                zh_name.update({sheet_name: display_to_entozh(result.get("display").get(sheet_name))})
                            GetExportData(excel_data, f"{excelName}.xlsx", zh_name, more_sheet=True)  # 多sheet页的多穿一个参数
                    else:
                        if keepAccuracy and not floatToZero:
                            import pandas as pd
                            df = pd.DataFrame(result["data"])
                            df = df.applymap(lambda x: f"{x:.20f}" if isinstance(x, (float,)) and x != 0 else x)
                            df = df.fillna("")
                            result["data"] = df.to_dict("records")

                        if floatToZero and not keepAccuracy:
                            import pandas as pd
                            df = pd.DataFrame(result["data"])
                            df = df.applymap(
                                lambda x: 0 if isinstance(x, (float,)) and math.isclose(x, 0, abs_tol=1e-5) else x)
                            df = df.fillna("")
                            result["data"] = df.to_dict("records")
                        res = Response()
                        res.set_body(json.dumps(convert_np_types(result)))
                        res.commit(True)
            except Exception as e:
                # current_method_name = inspect.currentframe().f_code.co_name
                # traceback_str = traceback.format_exc()
                # print(f"程序执行异常：{traceback_str}")
                # res = Response()
                # res.set_body(json.dumps({"code": 500, "msg": str(traceback_str), "data": []}))
                # res.commit(True)
                # return None
                raise e
            return result

        return wrapper

    return decorator


def ResetCallbackResponse(**decorator_kwargs):
    def decorator(func):
        def wrapper():
            cbk = Callback()
            try:
                body = json.loads(cbk.param())
                kwargs = {"body": body}
                result = func(**kwargs)
                if result:
                    if isinstance(result, ResponseData):
                        result = result.__dict__
                    cbk.set_result(json.dumps(result, ensure_ascii=False))
                cbk.commit(True)
                return result
            except Exception as e:
                current_method_name = inspect.currentframe().f_code.co_name
                traceback_str = traceback.format_exc()
                print(f"程序出现异常：{traceback_str}")
                cbk.set_result(json.dumps({"code": 500, "msg": str(traceback_str), "data": []}, ensure_ascii=False))
                cbk.commit(True)
                return None

        return wrapper

    return decorator


def CommiteGitResponse(**decorator_kwargs):
    def decorator(func):
        def wrapper():
            params = decorator_kwargs.get("params", [])
            req = Request()
            body = json.loads(req.body())
            all_data = body
            kwargs = {i: all_data.get(i) for i in params}
            kwargs.update({"user_id": req.header("user_id")})
            res = Response()
            func(**kwargs)
            res.set_body(res.body())
            res.commit(True)
            return res

        return wrapper

    return decorator


class ResponseStatusCode(enum.Enum):
    Success = 200
    Error = 400
    LOCKED = 600


class ResponseData():
    """
    {"code": 200, "msg": "ok", "data": left_result_data, "display": displayFiled,
            "page": left_result_page, "rule": {"filter_info": filter_info, "sort_info": sort_info}}
    """

    def __init__(self, code, msg, data, display=[], page={}, rule={}, **kwargs):
        if isinstance(code, ResponseStatusCode):
            code = code.value
        self.code = code
        self.msg = msg
        self.data = data
        self.display = display
        self.page = page
        self.rule = rule
        for key, value in kwargs.items():
            setattr(self, key, value)


def generate_unique_id():
    # unique_id = uuid.uuid4()
    import uuid
    unique_id = uuid.uuid5(uuid.NAMESPACE_DNS, str(time.time()))
    return unique_id.hex


class SqlResponseData(ResponseData):

    def __init__(self, sql, display, payload):
        logger.printInfo("ResponseSqlData Sql", sql)
        try:
            countData = self.execCountSql(sql)
            data = self.execDataSql(sql, payload)
            _, result_page = GetLimitData(int(countData.get("count", 0)), payload.get("page", {}))

            super().__init__(200, "成功", data, display, result_page)
        except Exception as e:
            super().__init__(400, str(e), [], display)

    def execCountSql(self, sql):
        db = DbHelper()
        countData = []
        countSql = f'''
                            WITH result_t AS({sql}) SELECT count(1) as `count` FROM result_t
                          '''
        countData = db.query_sql(countSql)
        if countData:
            countData = countData[0]
        else:
            countData = {}
        return countData

    def execDataSql(self, sql, payload):
        db = DbHelper()
        _, limit_sql = DbHelper.get_order_limit(payload)
        data = []
        dataSql = f'''
                WITH result_t AS({sql}) SELECT * FROM result_t {limit_sql}
        '''
        data = db.query_sql(dataSql)
        return data


def ensureSuccessSql(**decorator_kwargs):
    def decorator(func):
        def wrapper(*args, **kwargs):
            status = func(*args, **kwargs)
            count = decorator_kwargs.get("count", 3)
            while not status and count > 0:
                status = func(*args, **kwargs)
                if status:
                    print("update ok")
                    break
                count -= 1
                time.sleep(0.2)
            return status

        return wrapper

    return decorator


def checkRequestParams(**decorator_kwargs):
    def decorator(func):
        def wrapper(*args, **kwargs):
            requiredParams = decorator_kwargs.get("requiredParams", [])
            req = Request()
            body = json.loads(req.body())
            requestData = body.get("data", {})
            for param in requiredParams:
                if not requestData.get(param):
                    resData = ResponseData("500", f"{param} 是必填参数", [])
                    res = Response()
                    res.set_body(json.dumps(resData.__dict__, ensure_ascii=False))
                    res.commit(True)
                    return resData
            status = func(*args, **kwargs)
            return status

        return wrapper

    return decorator


class PayloadParser:
    """解析_payload_"""

    def __init__(self, payload):
        self.filter_info = payload.get('filter_info', {})
        self.sort_info = payload.get('sort_info', {})
        self.page_info = payload.get('page', {})
        self.rule = {
            "sort_info": self.sort_info,
            "filter_info": self.filter_info
        }

    # 获取排序sql语句
    def generate_order_by_clause(self):
        """获取排序sql"""
        if not self.sort_info:
            return ""  # 如果没有排序信息，返回空字符串
        # 使用列表解析生成 "字段名 排序方式" 格式的部分
        order_by_parts = [f"`{col['name']}` {col['sort'].upper()}" for col in self.sort_info]
        # 将部分连接成完整的 ORDER BY 子句
        return "ORDER BY " + ", ".join(order_by_parts)

    # 获取条件sql语句
    def generate_where_clause(self):
        """获取查询SQL"""
        if not self.filter_info or not self.filter_info.get("content"):
            return ""  # 如果没有过滤信息，返回空字符串
        condition = self.filter_info.get("condition", "and").upper()  # 默认使用 AND
        content = self.filter_info.get("content", [])
        # 定义规则映射
        rule_map = {
            "eq": "=",
            "neq": "!=",
            "gte": ">=",
            "lte": "<=",
            "in": "LIKE",
            "nin": "NOT LIKE"
        }
        # 构造每个过滤条件
        conditions = []
        for item in content:
            field = item["name"]
            rule = rule_map.get(item["rule"])
            value = item["value"]
            # 根据规则生成条件
            if rule in ["LIKE", "NOT LIKE"]:
                # LIKE 和 NOT LIKE 的值必须是字符串或列表，生成模糊匹配
                if isinstance(value, str):
                    conditions.append(f"`{field}` {rule} '%{value}%'")
                elif isinstance(value, list):
                    # 列表内的值生成 OR 条件
                    sub_conditions = [f"`{field}` {rule} '%{v}%'" for v in value]
                    conditions.append(f"({' OR '.join(sub_conditions)})")
                else:
                    raise ValueError(f"Rule '{rule}' requires a string or a list value.")
            else:
                # 其他规则（=, !=, >=, <=）
                if isinstance(value, str) and not value.isdigit():  # 如果是字符串且非数字，需加引号
                    value = f"'{value}'"
                conditions.append(f"`{field}` {rule} {value}")
        # 拼接条件
        where_clause = "WHERE " + f' {condition} '.join(conditions)
        return where_clause

    # 获取分页信息
    def generate_page(self, table_name, where_clause=None):
        """获取分页信息"""
        # 获取 page_size 和 page_num，确保有默认值
        page_size = self.page_info.get("page_size", None)  # 默认每页 10 行
        if page_size is None:
            return None, self.page_info
        page_num = self.page_info.get("page_num", 1)  # 默认从第 1 页开始
        # 如果 page_num 为 0，重置为 1
        if page_num <= 0:
            page_num = 1
        # 判断 page_size 是否是正整数
        if not isinstance(page_size, int) or page_size <= 0:
            return None, self.page_info
        # 构造数据总量的查询 SQL
        count_sql = f"SELECT `id` FROM `{table_name}`"
        if where_clause:
            count_sql += " WHERE " + where_clause
        # 获取数据表里面的数据总量
        data_sum = get_total_count(count_sql)
        # 计算总页数
        total_pages = data_sum // page_size + (1 if data_sum % page_size > 0 else 0)
        # 防止 page_num 超过 total_pages
        if page_num >= total_pages:
            page_num = total_pages  # 更新 page_num，确保它不超过最大页数
        # 计算 offset
        offset = (page_num - 1) * page_size
        # 构造 LIMIT SQL
        limit_sql = f"LIMIT {page_size} OFFSET {offset}"
        # 构造分页信息
        page = {
            "page_size": page_size,  # 每页数据行数
            "page_num": page_num,  # 当前页
            "page_sum": total_pages,  # 总页数
            "data_sum": data_sum  # 总数据行数
        }
        return limit_sql, page

    def build_sql(self, table_name):
        sort_sql = self.generate_order_by_clause()
        where_sql = self.generate_where_clause()
        limit_sql, page = self.generate_page(table_name, where_sql)
        query_parts = []
        if where_sql:
            query_parts.append(where_sql)
        if sort_sql:
            query_parts.append(sort_sql)
        if limit_sql:
            query_parts.append(limit_sql)
        return " ".join(query_parts)

    @staticmethod
    def query_sql(table, fields):
        """
            动态生成美观的 SQL 查询语句
            :param table: 表名（字符串）
            :param fields: 需要查询的字段列表（列表）
            :return: SQL 查询语句（字符串）
        """
        # 动态拼接字段
        field_sql = ",\n    ".join([f"t1.`{field}`" for field in fields])
        # 拼接完整的字段部分
        columns = f"""
            t1.`id`,
            {field_sql},
            t1.`create_id`,
            t1.`create_time`,
            t1.`update_id`,
            t1.`update_time`,
            t1.`note`,
            u1.`name` AS `create_name`,
            u2.`name` AS `update_name`
            """
        # 拼接 SQL 查询语句
        query_sql = f"""
            SELECT 
                {columns}
            FROM
                `{table}` AS t1
            LEFT JOIN 
                `t_system_user` AS u1 
                ON t1.`create_id` = u1.`id`
            LEFT JOIN 
                `t_system_user` AS u2 
                ON t1.`update_id` = u2.`id`;
            """
        return query_sql.strip()

    @staticmethod
    def check_primary_key(insert, update, columns):
        """
        :param insert: 待插入数据
        :param update: 待更新数据
        :param columns:
        """
        pass


def get_dynamic_table_names(base_name, plant_code, year, period, company_code=None):
    """
    @base_name: 表名前缀 t_cc_ducument_details_vp 分区表：t_cc_ducument_details_vp_1001_202502
    动态获取以 xxx前缀表的名字
    :return:
    """
    table_data = []
    if not base_name:
        return table_data

    db_helper = DbHelper()
    all_table = db_helper.get_tables_like_only_name(base_name, '', '')
    if not plant_code and company_code:
        plant_sql = f"SELECT `plant_code` FROM `t_os_company_plant_alloc` WHERE `company_code` = '{company_code}'"
        plant_code = db_helper.query_sql(plant_sql)

    if plant_code and isinstance(plant_code, (str, int)):
        dynamic_tables = [table_name for table_name in all_table if table_name and f'_{plant_code}' in table_name]
    elif plant_code and isinstance(plant_code, list):
        dynamic_tables = []
        for plant in plant_code:
            dynamic_tables += [table_name for table_name in all_table if table_name and f'_{plant}' in table_name]
    else:
        dynamic_tables = all_table

    if year and isinstance(year, (str, int)):
        dynamic_year_tables = [table_name for table_name in dynamic_tables if table_name and f'_{year}' in table_name]
    elif year and isinstance(year, list):
        dynamic_year_tables = []
        for each_year in year:
            dynamic_year_tables += [table_name for table_name in dynamic_tables if
                                    table_name and f'_{each_year}' in table_name]
    else:
        dynamic_year_tables = dynamic_tables

    dynamic_period_tables = []
    if period and isinstance(period, (str, int)):
        dynamic_period_tables = [table_name for table_name in dynamic_year_tables if
                                 table_name and table_name.endswith(str(period))]
    elif period and isinstance(period, list):
        for each_period in period:
            dynamic_period_tables += [table_name for table_name in dynamic_year_tables if
                                      table_name and table_name.endswith(str(each_period))]
    else:
        dynamic_period_tables = dynamic_year_tables

    print(base_name, plant_code, year, period, company_code)
    print(all_table)

    return dynamic_period_tables


# 审计底稿汇总
def audit_summary_splicing(list_old: list, list_new: list, summary_flag_list: list, summary_condition_list: list):
    """
        按指定字段分组，对指定数值字段累加合并
        参数:
            list_old: 需要合并的数据1
            list_new: 需要合并的数据2
            summary_flag_list: 需要汇总的字段名列表（必传，非空）
            summary_condition_list: 分组的字段名列表（必传，非空）
        例子
            list_old = [
                {'category': 'A', 'amount': 100, 'count': 2},
                {'category': 'B', 'amount': 200, 'count': 3}
            ]
            list_new = [
                {'category': ' A ', 'amount': 200, 'count': 1},  # 与A同分组（去空格后匹配）
                {'category': 'C', 'amount': 150, 'count': 5}     # 新分组
            ]
            summary_flag_list = ['amount', 'count']
            summary_condition_list = ['category']
        结果
            [
                {'category': 'A', 'amount': 300.0, 'count': 3.0},  # A的amount=100+200，count=2+1
                {'category': 'B', 'amount': 200, 'count': 3},      # 无匹配新数据，不变
                {'category': 'C', 'amount': 150.0, 'count': 5.0}   # 新增分组
            ]
        特殊情况处理：
        - 若list_old为空：直接将list_new的所有数据添加到list_old并返回；
        - 若list_new为空：直接返回原list_old（不做任何修改）；
        - 若两者都为空：返回空列表。
    """

    # print('list_old==========', list_old)
    # print('list_new==========', list_new)
    # print('summary_flag_list==========', summary_flag_list)
    # print('summary_condition_list==========', summary_condition_list)

    def get_group_key(item, group_fields):
        """根据分组字段名提取值，生成分组键（处理空格和字段缺失问题）"""
        group_values = []
        for field in group_fields:
            if field in item:
                # 对字符串类型值去除首尾空格，确保匹配准确性
                value = item[field].strip() if isinstance(item[field], str) else item[field]
                group_values.append(value)
            else:
                # 字段不存在时用None作为键的一部分
                group_values.append(None)
        return tuple(group_values)

    # 构建分组映射
    group_map = {}
    for idx, item in enumerate(list_old):
        group_key = get_group_key(item, summary_condition_list)
        group_map[group_key] = idx

    # 处理新数据
    for new_item in list_new:
        new_key = get_group_key(new_item, summary_condition_list)

        if new_key in group_map:
            old_idx = group_map[new_key]
            old_item = list_old[old_idx]

            # 只处理在旧项或新项中存在的字段
            for field in summary_flag_list:
                # 检查字段是否存在于任一数据项中
                if field in old_item or field in new_item:
                    try:
                        old_val = float(old_item[field]) if (
                                field in old_item and old_item[field] is not None) else 0.0
                        new_val = float(new_item[field]) if (
                                field in new_item and new_item[field] is not None) else 0.0
                        old_item[field] = round(old_val + new_val, 2)
                    except (ValueError, TypeError) as e:
                        print(f"汇总字段 {field} 时出错: {e}")
        else:
            # 新增分组
            list_old.append(new_item.copy())
            group_map[new_key] = len(list_old) - 1

    # 确保所有记录具有一致的字段结构
    # 首先收集所有可能的字段
    all_fields = set()
    for item in list_old:
        all_fields.update(item.keys())

    # 然后确保每条记录都包含所有字段，缺失的字段设为None
    for item in list_old:
        for field in all_fields:
            if field not in item:
                item[field] = 0

    # print(list_old)
    return list_old


def get_where(filed_name, sql_condition):
    """
    获取where条件
    """
    all_where = ""

    include_condition = [item for item in sql_condition if '*' in item]
    exclude_condition = [item for item in sql_condition if '*' not in item]

    condition1 = ', '.join(map(repr, tuple(exclude_condition))).strip(',')

    like_conditions = [
        f"{filed_name} LIKE '{item.replace('*', '%')}'"
        for item in include_condition
        if '*' in item
    ]
    condition2 = " OR ".join(like_conditions)

    if include_condition and not exclude_condition:
        all_where = f"{condition2}"
    elif not include_condition and exclude_condition:
        all_where = f"{filed_name} IN ({condition1})"
    elif include_condition and exclude_condition:
        all_where = f"{filed_name} IN ({condition1}) OR {condition2}"

    return all_where


# 获取全部表名和表描述
def down_get_tables_like_only_name_desc():
    data = db.get_tables_like_only_name_desc('')
    temp_list = []
    for table_name, table_comment in data.items():
        if not table_comment.strip():
            label = table_name
        else:
            label = f"{table_name} {table_comment}"
        temp_list.append({
            'value': table_name,
            'description': table_comment,
            'label': label
        })
    unique_dict = {(item['value'], item['description'], item['label']): item for item in temp_list}
    final_result = list(unique_dict.values())
    return final_result


#分表查询功能
def get_sub_table(table_name, first_field :str|list ='', second_field_1 :str|list='', second_field_2 :str|list='', year_period_tp: tuple[str, str]=tuple(), key=None):
    """
    入参：
    table_name 表名
    first_field 第一分表字段
    second_field_1 第二分表字段的第一部分
    second_field_2 第二分表字段的第二部分
    year_period_tp 期间元组 获取区间内所有分表
    """
    db = DbHelper()
    table_name = table_name.strip('_') + '_'
    table_name_ls = []

    if isinstance(first_field, str):
        first_field_ls = [first_field]
    else:
        first_field_ls = first_field
    second_field_ls = []
    if year_period_tp:
        from dateutil import parser
        second_field_start = parser.parse(year_period_tp[0], fuzzy=True).strftime('%Y%m')
        second_field_end = parser.parse(year_period_tp[1], fuzzy=True).strftime('%Y%m')
        second_field_ls = get_month_range(second_field_start,second_field_end)
    else:
        second_field_ls.append(second_field_1+second_field_2)


    for first_field_str in first_field_ls:
        for second_field_str in second_field_ls:
            table_data = db.get_tables_like_only_name(table_name, first_field_str, second_field_str)
            if table_data:
                table_name_ls.extend(table_data)
    print(table_name_ls)

    table_sql = ""
    if table_name_ls:
        if key:
            col_sql = ','.join([f'`{i}`' for i in key])
        else:
            col_sql = '*'
        union_table_ls = []
        for table_name in table_name_ls:
            table_sql = """
            SELECT {} FROM `{}`
            """.format(col_sql, table_name)
            union_table_ls.append(table_sql)

        table_sql = """
         UNION ALL 
        """.join(union_table_ls)

        response = {
            "code": 200,
            "msg": "成功",
            "table_sql": table_sql
        }
    else:
        return {
            "code": 500,
            "msg": f"未查询到符合条件的{table_name}分表",
            "table_sql": table_sql
        }
    return response


def get_month_range(start_ym: str, end_ym: str) -> list:
    """
    获取两个年月之间的所有年月组合
    Args:
        start_ym: 开始年月，格式 YYYYMM，如 '202401'
        end_ym: 结束年月，格式 YYYYMM，如 '202412'
    Returns:
        年月列表，如 ['202401', '202402', ...]
    """
    from dateutil.relativedelta import relativedelta
    start_date = datetime.strptime(start_ym, '%Y%m')
    end_date = datetime.strptime(end_ym, '%Y%m')

    result = []
    current = start_date
    while current <= end_date:
        result.append(current.strftime('%Y%m'))
        current += relativedelta(months=1)

    return result
