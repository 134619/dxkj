#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@File    : SalesPickInterface.py
@Author  : tao.chang@dxdstech.com
@Date    : 2025/4/8 18:14
@explain : 拣配相关接口
"""
import time
from datetime import datetime

try:
    import pyfiles.SysPathAdd
except ImportError:
    ...
from DbHelper import DbHelper
from DxBusinessDataConvertUtil import convert_material_unit_qty
from FrameworkContractInterface import (
    get_coding_domain,
    get_serial_code,
    rollback_serial_code,
)
from logger import LoggerConfig
from ToolsMethods import ResetResponse, ResponseData, ResponseStatusCode, calc_time

logger = LoggerConfig("SalesPickInterface", isStream=True)


class DnAlloc:
    def __init__(self, id, picking_document, dn_sn, dn_item, batch_item, mat_code, stor_loc_code,
                 batch_sn, picked_qty, picked_base_qty, picked_parallel_qty, parallel_uom, basic_uom,
                 transaction_uom, posting_status, pod_status, billing_status,
                 packing_date, status, create_id, update_id, actual_plant, actual_stor, external_mat_code,
                 credit_control_code, credit_status):
        self.id = id
        self.picking_document = picking_document
        self.dn_sn = dn_sn
        self.dn_item = dn_item
        self.batch_item = batch_item
        self.mat_code = mat_code
        self.stor_loc_code = stor_loc_code
        self.batch_sn = batch_sn
        self.picked_qty = picked_qty
        self.picked_base_qty = picked_base_qty
        self.packing_date = packing_date
        self.picked_parallel_qty = picked_parallel_qty
        self.parallel_uom = parallel_uom
        self.basic_uom = basic_uom
        self.transaction_uom = transaction_uom
        self.posting_status = posting_status
        self.pod_status = pod_status
        self.billing_status = billing_status
        self.status = status
        self.create_id = create_id
        self.update_id = update_id
        self.actual_plant = actual_plant
        self.actual_stor = actual_stor
        self.external_mat_code = external_mat_code
        self.credit_control_code = credit_control_code
        self.credit_status = credit_status


@ResetResponse(params=["type"])
def getStatusRecord(type, **kwargs):
    db = DbHelper()
    sql = f""" select * from `t_so_status_record` """
    if type:
        sql += f" where `field` = '{type}'"
    ret = db.query_sql(sql)
    return ResponseData(ResponseStatusCode.Success, "成功", ret)


def get_all_inventory(mat_code=None, plant_code=None, stor_loc_code=None):
    where_sql = " WHERE 1=1 "
    if mat_code:
        if isinstance(mat_code, list):
            where_sql += f" AND `mat_code` in ({','.join([repr(i) for i in mat_code])})"
        else:
            where_sql += f" AND `mat_code`='{mat_code}'"
    if plant_code:
        if isinstance(plant_code, list):
            where_sql += f" AND `plant_code` in ({','.join([repr(i) for i in plant_code])})"
        else:
            where_sql += f" AND `plant_code`='{plant_code}'"
    if stor_loc_code:
        if isinstance(stor_loc_code, list):
            where_sql += f" AND `stor_loc_code` in ({','.join([repr(i) for i in stor_loc_code])})"
        else:
            where_sql += f" AND `stor_code`='{stor_loc_code}'"
    db = DbHelper()
    base_sql = f'SELECT * FROM `t_inventory_batch_data` {where_sql}'
    print("base_sql:", base_sql)
    data = db.query_sql(base_sql)

    return data


def gen_field_name_code_dict():
    name_code_dict = {}
    base_sql = '''
        SELECT
            `field_code`,
            `field_name`
        FROM
            `t_ap_property_field`
        WHERE
            1 = 1
    '''
    db = DbHelper()
    field_list = db.query_sql(base_sql)

    for item in field_list:
        field_code = item.get('field_code')
        field_name = item.get('field_name')
        if field_code and field_name:
            if field_name not in name_code_dict:
                name_code_dict[field_name] = field_code

    return name_code_dict


def get_dn_item_db_1():
    db = DbHelper()
    ret = db.query_sql("""
        SELECT `tdm`.`dn_sn`,`tdm`.`dn_item`,`tdm`.`mat_code`,`tdm`.`basic_uom`,`tdm`.`plant_code`,`tdh`.`dn_type`,`tdt`.`use_ipn`
         FROM `t_dn_item` as `tdm` 
         left join `t_dn_header` as `tdh` on `tdm`.`dn_sn` = `tdh`.`dn_sn`
         left join `t_dn_type` as `tdt` on `tdt`.`dn_type` = `tdh`.`dn_type`
     """)
    return {
        (i.get("dn_sn"), i.get("dn_item")): {"mat_code": i.get("mat_code"), "basic_uom": i.get("basic_uom"),
                                             "transaction_uom": i.get("transaction_uom"), "dn_type": i.get("dn_type"),
                                             "plant_code": i.get("plant_code")}
        for i in ret}


def get_dn_item_db(dn_data_list):
    db = DbHelper()
    sql = """
        SELECT `tdm`.`dn_sn`,
        `tdm`.`dn_item`,
        `tdm`.`mat_code`,
        `tdm`.`basic_uom`,
        `tdm`.`plant_code`,
        `tdm`.`sales_item_category`,
        `tdh`.`dn_type`,
        `tdh`.`credit_control_code`,
        `tdh`.`company_code`,
        `tdt`.`use_ipn`,
        `tdm`.`basic_qty`,
        `tdm`.`planned_delivery_quantity`,
        `tdm`.`picked_qty`,
        `tdm`.`parallel_uom`,
        `tdm`.`transaction_uom`,
        `tdm`.`basic_uom`,
        `tdm`.`related_to_delivery`,
        `tdm`.`pod_related`,
        `tdm`.`credit_status`,
        `tdm`.`sales_org_code`,
        `tcs`.`credit_status_description`,
        `tasic`.`credit_activated_flag`,
        `tasic`.`shipping_returns`,
        `tdm`.`related_to_invoices`
         FROM `t_dn_item` as `tdm` 
         left join `t_dn_header` as `tdh` on `tdm`.`dn_sn` = `tdh`.`dn_sn`
         left join `t_dn_type` as `tdt` on `tdt`.`dn_type` = `tdh`.`dn_type`
         left join `t_credit_status` as `tcs` on `tcs`.`credit_status` = `tdm`.`credit_status`
         left join `t_ao_sd_item_category` as `tasic` on `tasic`.`sales_item_category` = `tdm`.`sales_item_category`
     """
    where_sql = ""
    if dn_data_list:
        for i in dn_data_list:
            if not where_sql:
                if i["dn_sn"] and i["dn_item"]:
                    where_sql += f""" where (`tdm`.`dn_sn` = '{i["dn_sn"]}' and `tdm`.`dn_item` = {i["dn_item"]}) """
            else:
                if i["dn_sn"] and i["dn_item"]:
                    where_sql += f""" or (`tdm`.`dn_sn` = '{i["dn_sn"]}' and `tdm`.`dn_item` = {i["dn_item"]}) """
    if where_sql:
        sql += where_sql
    ret = db.query_sql(sql)
    return {(i.get("dn_sn"), i.get("dn_item")): i for i in ret}


def get_dn_item_db_dict(dn_sn, dn_item):
    db = DbHelper()
    ret = db.query_sql(f"""
        SELECT `tdm`.`dn_sn`,`tdm`.`dn_item`,`tdm`.`mat_code`,`tdm`.`basic_uom`,`tdm`.`plant_code`,`tdh`.`dn_type`,`tdt`.`use_ipn`
         FROM `t_dn_item` as `tdm` 
         left join `t_dn_header` as `tdh` on `tdm`.`dn_sn` = `tdh`.`dn_sn`
         left join `t_dn_type` as `tdt` on `tdt`.`dn_type` = `tdh`.`dn_type`
         where `tdm`.`dn_sn` = "{dn_sn}" and `tdm`.`dn_item` = "{dn_item}"
     """)
    if ret:
        return ret[0]
    else:
        return {}


def get_t_batch_number1(batch_sn_data_list):
    db = DbHelper()
    sql = f"""
        select * from `t_batch_number`
    """
    where_sql = ""
    if batch_sn_data_list:
        for i in batch_sn_data_list:
            if not where_sql:
                where_sql += f""" where (`batch_sn` = '{i["batch_sn"]}' and  `mat_code` = '{i["mat_code"]}' ) """
            else:
                where_sql += f""" or (`batch_sn` = '{i["batch_sn"]}' and `mat_code` = '{i["mat_code"]}' ) """
    if where_sql:
        sql += where_sql
    ret = db.query_sql(sql)
    # print("get_t_batch_number sql>>", sql)
    return {(i.get("mat_code"), i.get("batch_sn")): i for i in ret}


def get_t_batch_number(batch_sn_data_list):
    db = DbHelper()
    sql = f"""
        select `mat_code`,`batch_sn` from `t_batch_number`
    """
    where_sql = ""
    if batch_sn_data_list:
        batch_sn_data_dict = {}
        for i in batch_sn_data_list:
            if batch_sn_data_dict.get(i["mat_code"]):
                if i["batch_sn"]:
                    batch_sn_data_dict[i.get("mat_code")].append(repr(i["batch_sn"]))
            else:
                if i["batch_sn"]:
                    batch_sn_data_dict[i.get("mat_code")] = [repr(i["batch_sn"])]
        for k, sns in batch_sn_data_dict.items():
            if not where_sql:
                where_sql += f""" where (`batch_sn` in ({','.join(sns)}) and  `mat_code` = '{k}') """
            else:
                where_sql += f""" or (`batch_sn` in ({','.join(sns)}) and  `mat_code` = '{k}')"""

            # if not where_sql:
            #     where_sql += f""" where (`batch_sn` = '{i["batch_sn"]}' and  `mat_code` = '{i["mat_code"]}' ) """
            # else:
            #     where_sql += f""" or (`batch_sn` = '{i["batch_sn"]}' and `mat_code` = '{i["mat_code"]}' ) """
    if where_sql:
        sql += where_sql
    ret = db.query_sql(sql)
    # print("get_t_batch_number sql>>", sql)
    return {(i.get("mat_code"), i.get("batch_sn")): i for i in ret}


def get_t_batch_number_1():
    db = DbHelper()
    sql = f"""
        select * from `t_batch_number`
    """
    ret = db.query_sql(sql)
    return {(i.get("mat_code"), i.get("batch_sn")): i for i in ret}


def get_t_batch_number_dict(mat_code, batch_sn):
    db = DbHelper()
    sql = f"""
        select * from `t_batch_number`
        where `mat_code` = "{mat_code}" and `batch_sn` = "{batch_sn}"
    """
    ret = db.query_sql(sql)
    if ret:
        return ret[0]
    else:
        return {}


def gen_inventory_dict(mat_code=None, plant_code=None, stor_loc_code=None):
    inventory_dict = {}
    all_inventory = get_all_inventory(mat_code=mat_code, plant_code=plant_code, stor_loc_code=stor_loc_code)
    for it in all_inventory:
        if it.get('special_inventory_status2') != '':
            continue
        it_key = it.get('mat_code') + '-' + it.get('plant_code') + '-' + it.get('stor_loc_code')
        it_batch_sn = it.get('batch_sn')
        if it_key not in inventory_dict:
            inventory_dict[it_key] = {it_batch_sn: it}
        else:
            if it_batch_sn not in inventory_dict.get(it_key):
                inventory_dict[it_key][it_batch_sn] = it
            elif (it.get('year', '0000') + it.get('period', '01') >
                  inventory_dict[it_key][it_batch_sn].get('year', '0000') + inventory_dict[it_key][it_batch_sn].get(
                        'period', '00')):
                inventory_dict[it_key][it_batch_sn] = it
    return inventory_dict


def query_mat_code():
    db = DbHelper()
    # 物料基础数据  t_mmd_material_basic_data
    query_mat_code_sql = '''
    SELECT
        `mat_code`,
        `mat_description`,
        `external_mat_code`
    FROM
        `t_mmd_material_basic_data`;
    '''
    data = db.query_sql(query_mat_code_sql)
    return {i.get("mat_code"): i for i in data}


def get_os_plant_storage_location_alloc_db():
    db = DbHelper()
    ret = db.query_sql("SELECT `plant_code`,`stor_loc_code` FROM `t_os_plant_storage_location_alloc`")
    return {(i.get("plant_code"), i.get("stor_loc_code")): i for i in ret}


def get_batch_sn_by_attr(attr_dict):
    db = DbHelper()
    first_part_sql = 'SELECT `batch_sn`,count(`batch_sn`) AS `bs_count` FROM ( '
    middle_part = ''
    for code, value in attr_dict.items():
        middle_part += 'SELECT DISTINCT `batch_sn` FROM `t_batch_additional_property` WHERE 1=1 AND `field_code`={} AND \
        `field_value`={} UNION ALL '.format(repr(code), repr(value))
    middle_part = middle_part.rstrip('UNION ALL ')
    end_part_sql = ' ) AS `rt` GROUP BY `rt`.`batch_sn` HAVING `bs_count` > {};'.format(len(attr_dict) - 1)
    query_batch_sn_sql = first_part_sql + middle_part + end_part_sql
    res_data = db.query_sql(query_batch_sn_sql)
    return res_data


# 根据物料描述匹配物料编码
@calc_time
def query_mat_code_by_desc(mat_desc):
    db = DbHelper()
    # 物料基础数据  t_mmd_material_basic_data
    query_mat_code_sql = '''
    SELECT
        `mat_code` 
    FROM
        `t_mmd_material_basic_data` 
    WHERE
        `description` = {};
    '''.format(repr(mat_desc))

    data = db.query_sql(query_mat_code_sql)
    return data


def getBasicQtyByDN(dn, dn_item):
    db = DbHelper()
    sql = f"""SELECT `dn_sn`,`dn_item`,`basic_qty`,`planned_delivery_quantity`,`picked_qty`,`parallel_uom`,`transaction_uom`,`basic_uom`,
    `related_to_delivery`,`pod_related`,`related_to_invoices` from `t_dn_item` WHERE `dn_sn`="{dn}" and `dn_item`="{dn_item}" """
    res = db.query_sql(sql)
    if res:
        return res[0]
    else:
        return {}


@calc_time
def getDataDnitemStats(pickup_batch_list):
    db = DbHelper()
    sql = "select `dn_sn`,`dn_item`,`mat_code`,`packing_status` from `t_dn_item`"
    where_sql = ""
    cache_query_key = {}
    if pickup_batch_list:
        for i in pickup_batch_list:
            key = (i["dn_sn"], i["dn_item"], i["mat_code"])
            if key in cache_query_key:
                continue
            if not where_sql:
                where_sql += f""" where (`dn_sn` = '{i["dn_sn"]}' and `dn_item` = {i["dn_item"]} and `mat_code` = '{i["mat_code"]}') """
            else:
                where_sql += f""" or (`dn_sn` = '{i["dn_sn"]}' and `dn_item` = {i["dn_item"]} and `mat_code` = '{i["mat_code"]}') """
            cache_query_key[key] = 1
    if where_sql:
        sql += where_sql
    ret = db.query_sql(sql)
    return {(i.get("dn_sn"), i.get("dn_item"), i.get("mat_code")): i.get("packing_status") for i in ret}


# @calc_time
def numeric_conversion(pickup_batch):
    # 当用户有输入单位和价格的时候,使用用户传入的单位与价格,否则使用查询到的单位和价格
    # 因为要查询其他数据,所以此处必须保留
    # basicItem = getBasicQtyByDN(pickup_batch.get("dn_sn"), pickup_batch.get("dn_item"))
    global dn_item_set
    # print("dn_item_set>>>>",dn_item_set)
    if dn_item_set:
        basicItem = dn_item_set.get((pickup_batch.get("dn_sn"), int(pickup_batch.get("dn_item"))), {})
    else:
        basicItem = getBasicQtyByDN(pickup_batch.get("dn_sn"), pickup_batch.get("dn_item"))

    # print("basicItem?>>>>",basicItem)
    # 先获取价格单位
    transaction_uom = pickup_batch.get("delivery_uom") or pickup_batch.get("transaction_uom")
    basic_uom = pickup_batch.get("basic_uom")
    parallel_uom = pickup_batch.get("parallel_uom")
    if not transaction_uom:
        transaction_uom = basicItem.get("transaction_uom")
    if not basic_uom:
        basic_uom = basicItem.get("basic_uom")
    if not parallel_uom:
        parallel_uom = basicItem.get("parallel_uom")

    # 获取数量
    pick_qty = pickup_batch.get('picked_qty') or pickup_batch.get('picking_qty')
    planned_delivery_quantity = pickup_batch.get('planned_delivery_quantity', 0)
    picked_parallel_qty = pickup_batch.get('picked_parallel_qty', 0)
    if pick_qty is None:
        pick_qty = planned_delivery_quantity

    if isinstance(pick_qty, str):
        if not pick_qty:
            pick_qty = 0
        else:
            pick_qty = float(pick_qty)

    # 获取基本单位数量
    picked_base_qty = pickup_batch.get("picked_base_qty", "")
    # print("======================================")
    # print("基本单位数量:", picked_base_qty)
    # print(picked_base_qty == "")
    if picked_base_qty == "":
        if basic_uom:
            """需要重新计算"""
            if transaction_uom == basic_uom:
                picked_base_qty = pick_qty
            else:
                code, msg, picked_base_qty = convert_material_unit_qty(pickup_batch["mat_code"], transaction_uom,
                                                                       basic_uom,
                                                                       float(pick_qty))
                if code == 500:
                    if not picked_parallel_qty:
                        return {"code": 400, "msg": "拣配基本数量计算失败:未找到对应单位转换关系"}
                    code, msg, picked_base_qty = convert_material_unit_qty(pickup_batch["mat_code"], basic_uom,
                                                                           parallel_uom,
                                                                           float(picked_parallel_qty))
                    if code == 500:
                        picked_base_qty = 0

        else:
            picked_base_qty = 0
    # 获取平行单位数量
    picked_parallel_qty = pickup_batch.get('picked_parallel_qty', "")
    # print("平行单位单位数量:", picked_parallel_qty)

    # print(picked_parallel_qty == "")
    # print("======================================")
    if picked_parallel_qty == "":
        if parallel_uom:
            if transaction_uom == parallel_uom:
                picked_parallel_qty = pick_qty
            else:
                code, msg, picked_parallel_qty = convert_material_unit_qty(pickup_batch["mat_code"], transaction_uom,
                                                                           parallel_uom,
                                                                           float(pick_qty))
                if code == 500:
                    if not picked_base_qty:
                        return {"code": 400, "msg": "拣配平行数量计算失败:未找到对应单位转换关系"}
                    code, msg, picked_parallel_qty = convert_material_unit_qty(pickup_batch["mat_code"], basic_uom,
                                                                               parallel_uom,
                                                                               float(picked_base_qty))
                    if code == 500:
                        picked_parallel_qty = 0
        else:
            picked_parallel_qty = 0

    # print("basicItem:", basicItem)
    remaining_planned_delivery_quantity = basicItem.get("planned_delivery_quantity", 0) - basicItem.get("picked_qty", 0)
    if basicItem.get("related_to_delivery") == "A":
        posting_status = "A"
    else:
        posting_status = "D"

    if str(basicItem.get("pod_related")) == "1" and basicItem.get("related_to_delivery") == "A":
        pod_status = "A"
    else:
        pod_status = "D"

    if str(basicItem.get("related_to_invoices")) == "D":
        billing_status = "A"
    else:
        billing_status = "D"
    # return pick_qty, basic_qty, alloc_bs_qty, alloc_bt_qty, planned_delivery_quantity, parallel_qty, alloc_basic_qty, picked_base_qty, parallel_uom
    return {"code": 200, "transaction_uom": transaction_uom, "basic_uom": basic_uom, "parallel_uom": parallel_uom,
            "pick_qty": pick_qty,
            "picked_base_qty": picked_base_qty, "picked_parallel_qty": picked_parallel_qty,
            "planned_delivery_quantity": basicItem.get("planned_delivery_quantity", 0),
            "posting_status": posting_status,
            "pod_status": pod_status,
            "billing_status": billing_status,
            "remaining_planned_delivery_quantity": remaining_planned_delivery_quantity}


def numeric_conversion_dynamics(pickup_batch):
    pick_qty = pickup_batch.get('picked_qty')
    planned_delivery_quantity = pickup_batch.get('planned_delivery_quantity', 0)
    picked_parallel_qty = pickup_batch.get('picked_parallel_qty', 0)
    basicItem = getBasicQtyByDN(pickup_batch.get("dn_sn"), pickup_batch.get("dn_item"))

    if pick_qty is None:
        pick_qty = planned_delivery_quantity

    if isinstance(pick_qty, str):
        if not pick_qty:
            pick_qty = 0
        else:
            pick_qty = float(pick_qty)
    transaction_uom = basicItem.get("transaction_uom")
    basic_uom = basicItem.get("basic_uom")
    parallel_uom = basicItem.get("parallel_uom")
    # 拣配数量是可修改的，所以是动态的
    basicItem["picked_qty"] = pick_qty
    if transaction_uom == basic_uom:
        picked_base_qty = pick_qty
    else:
        code, msg, picked_base_qty = convert_material_unit_qty(pickup_batch["mat_code"], transaction_uom, basic_uom,
                                                               float(pick_qty))
        if code == 500:
            if not picked_parallel_qty:
                return {"code": 400, "msg": msg}
            code, msg, picked_base_qty = convert_material_unit_qty(pickup_batch["mat_code"], basic_uom, parallel_uom,
                                                                   float(picked_parallel_qty))
            if code == 500:
                picked_base_qty = 0
    if transaction_uom == parallel_uom:
        picked_parallel_qty = pick_qty
    else:
        code, msg, picked_parallel_qty = convert_material_unit_qty(pickup_batch["mat_code"], transaction_uom,
                                                                   parallel_uom,
                                                                   float(pick_qty))  # 交易单位 ，平行单位
        if code == 500:
            if not picked_base_qty:
                return {"code": 400, "msg": msg}
            code, msg, picked_parallel_qty = convert_material_unit_qty(pickup_batch["mat_code"], basic_uom,
                                                                       parallel_uom,
                                                                       float(picked_base_qty))
            if code == 500:
                picked_parallel_qty = 0

    remaining_planned_delivery_quantity = basicItem.get("planned_delivery_quantity") - basicItem.get("picked_qty")
    if basicItem.get("related_to_delivery") == "A":
        posting_status = "A"
    else:
        posting_status = "D"

    if str(basicItem.get("pod_related")) == "1" and basicItem.get("related_to_delivery") == "A":
        pod_status = "A"
    else:
        pod_status = "D"

    if str(basicItem.get("related_to_invoices")) == "D":
        billing_status = "A"
    else:
        billing_status = "D"
    # return pick_qty, basic_qty, alloc_bs_qty, alloc_bt_qty, planned_delivery_quantity, parallel_qty, alloc_basic_qty, picked_base_qty, parallel_uom
    return {"code": 200, "transaction_uom": transaction_uom, "basic_uom": basic_uom, "parallel_uom": parallel_uom,
            "pick_qty": pick_qty,
            "picked_base_qty": picked_base_qty, "picked_parallel_qty": picked_parallel_qty,
            "planned_delivery_quantity": basicItem.get("planned_delivery_quantity"),
            "posting_status": posting_status,
            "pod_status": pod_status,
            "billing_status": billing_status,
            "remaining_planned_delivery_quantity": remaining_planned_delivery_quantity}


@calc_time
def get_cust_balance_calc_formula(credit_management):
    db = DbHelper()
    sql = f""" select 
                    tccd.`cust_balance_calc_formula`
                from `t_credit_management_defining` as tccd
                where  tccd.`credit_management` = '{credit_management}' """
    ret = db.query_sql(sql)
    if ret:
        return ret[0].get("cust_balance_calc_formula", "")
    else:
        return ""


@calc_time
def get_credit_management(sales_org_code):
    db = DbHelper()
    sql = f""" select 
                    tccd.`credit_management`
                from `t_alloc_credit_management` as tccd
                where  tccd.`sales_org_code` = '{sales_org_code}' """
    ret = db.query_sql(sql)
    if ret:
        return ret[0].get("credit_management", "")
    else:
        return ""


def get_customer_credit(customer_code, sales_org_code):
    db = DbHelper()
    sql = f""" select 
                    tccd.`credit_limit`
                from `t_customer_credit_data` as tccd
                left join `t_alloc_credit_management` as tacm on tccd.`credit_management` = tacm.`credit_management` and tacm.`sales_org_code` ='{sales_org_code}'
                where  tccd.`customer_code` = '{customer_code}' """
    ret = db.query_sql(sql)
    if ret:
        return ret[0].get("credit_limit", 0)
    else:
        return 0


dn_item_set = {}


# 批量导入数据校验
@calc_time
def format_check(origin_data, required_data, replace_name_reversal, over_picking=False):
    requiredStatus = True
    isPass = True
    message = '校验成功'
    is_over_creditBalance = False
    if not origin_data:
        isPass = False
        message = '上传文件为空'

    for one_data in origin_data:
        message = ""
        for required_p in required_data:                
            if not one_data.get(required_p):
                requiredStatus = False
                message += f"{required_p}是必填参数;"
        if message:
            one_data['exec_result'] = "执行失败"
            one_data["message"] = message
    if not requiredStatus:
        return origin_data, requiredStatus, {}, is_over_creditBalance

    inventory_dict = gen_inventory_dict()
    field_name_code_start_time = time.time()
    name_code_dict = gen_field_name_code_dict()
    print("field_name_code end>>", time.time() - field_name_code_start_time)
    dn_data_list = [{"dn_sn": i.get("dn_sn"), "dn_item": i.get("dn_item"), "mat_code": i.get("mat_code"),
                     "batch_sn": i.get("batch_sn")} for i in origin_data]
    # batch_sn_data_list = [{"mat_code":i.get("mat_code"),"batch_sn":i.get("batch_sn")} for i in origin_data]
    # basic_counter, batch_counter = dict(), dict()
    # 42.38760542869568
    global dn_item_set
    get_dn_item_db_start_time = time.time()
    dn_item_set = get_dn_item_db(dn_data_list)
    print("get_dn_item_db_time end>>", time.time() - get_dn_item_db_start_time)
    # 69.88239979743958
    batch_number_set_start_time = time.time()
    batch_number_set = get_t_batch_number(dn_data_list)
    print("batch_number_set end>>", time.time() - batch_number_set_start_time)
    plant_storage_location_set_start_time = time.time()
    plant_storage_location_set = get_os_plant_storage_location_alloc_db()
    print("plant_storage_location_set_end>>", time.time() - plant_storage_location_set_start_time)
    query_mat_code_start_time = time.time()
    mat_code_dict = query_mat_code()
    print("query_mat_code_start_time end>>", time.time() - query_mat_code_start_time)
    # 21.257415533065796
    # sd_item_cat_db_start_time = time.time()
    # sd_item_cat_db_dict = get_sd_item_cat_db_dict(dn_data_list)
    # print("sd_item_cat_db end>>", time.time() - sd_item_cat_db_start_time)
    pickup_batch_dict = {}
    start_time_for = time.time()
    for one_data in origin_data:
        query_key = str(one_data.get('dn_sn', '')) + str(one_data.get('dn_item', ''))
        if query_key not in pickup_batch_dict:
            pickup_batch_dict[query_key] = [one_data]
        else:
            pickup_batch_dict[query_key].append(one_data)
        dn_sn = one_data.get('dn_sn')
        if one_data.get('dn_item'):
            dn_item = int(one_data.get('dn_item'))
        else:
            dn_item = one_data.get('dn_item')

        # sd_item_cat_dict = get_sd_item_cat_db(dn_sn, dn_item)
        sd_item_cat_dict = dn_item_set.get((dn_sn, dn_item), {})
        if not sd_item_cat_dict:
            isPass = False
            message = f"交货单号[{dn_sn}]交货单行号[{dn_item}]不存在"
            one_data['message'] = one_data.get('message', '') + message
            one_data['exec_result'] = "执行失败"
            continue
        # dn_item_set = get_dn_item_db_dict(dn_sn,dn_item)
        if not one_data.get('basic_unit'):
            one_data['basic_unit'] = ''
        if not one_data.get('batch_unit'):
            one_data['batch_unit'] = ''
        if not one_data.get('basic_qty'):
            one_data['basic_qty'] = 0
        one_data['message'] = ""
        required_status = True
        # print("one_data:", one_data)
        # print("required_data:", required_data)
        # print("replace_name_reversal:", replace_name_reversal)

        # required_data_for = time.time()
        # print("required_data>>>", required_data)
        # print("one_data>>>", one_data)
        for key in required_data:
            if key in one_data:
                value = one_data[key]
                # print("key>>>", key)
                if not value and value != 0:
                    required_status = False
                    isPass = False
                    if replace_name_reversal:
                        message = f'{replace_name_reversal.get(key)} 是必填字段'
                    else:
                        message = f'{key} 是必填字段'
                    one_data['message'] = one_data.get('message', '') + message
                    one_data['exec_result'] = "执行失败"
                    continue
            else:
                required_status = False
                isPass = False
                if replace_name_reversal:
                    message = f'{replace_name_reversal.get(key)} 是必填字段'
                else:
                    message = f'{key} 是必填字段'
                one_data['message'] = one_data.get('message', '') + message
                one_data['exec_result'] = "执行失败"
                continue

        so_sn_ = one_data.get("so_sn", "")
        so_items_ = one_data.get("so_items", 0)
        dn_sn_ = one_data.get("dn_sn", "")
        dn_item_ = one_data.get("dn_item", 0)
        picking_qty_ = one_data.get("picking_qty", 0)
        picked_qty_ = one_data.get("picked_qty", picking_qty_)
        mat_code_ = one_data.get("mat_code", "")
        batch_sn_ = one_data.get("batch_sn", "")
        is_valid, err_msg = get_dn_item(so_sn_, so_items_, dn_sn_, dn_item_, picked_qty_, mat_code_, batch_sn_)
        if not is_valid:
            one_data['message'] = one_data.get('message', '') + err_msg
            return origin_data, is_valid, pickup_batch_dict, is_over_creditBalance

        print("required_status><>>", required_status)
        if not required_status:
            continue
        #
        credit_control_code = dn_item_set.get((dn_sn, dn_item)).get("credit_control_code")
        credit_status = dn_item_set.get((dn_sn, dn_item)).get("credit_status")
        credit_status_description = dn_item_set.get((dn_sn, dn_item)).get("credit_status_description")
        credit_activated_flag = dn_item_set.get((dn_sn, dn_item)).get("credit_activated_flag")
        sales_org_code = dn_item_set.get((dn_sn, dn_item)).get("sales_org_code")
        one_data['credit_control_code'] = credit_control_code
        if credit_control_code != "C":
            if credit_status in ["C", "E"]:
                isPass = False
                message = f'{dn_sn},信用状态为[{credit_status_description}]拣配失败请检查'
                one_data['message'] = message
                one_data['exec_result'] = "执行失败"
                continue
            else:
                one_data['credit_status'] = "F"
        else:
            if str(credit_activated_flag) == "1":
                from CustLineOfCreditCalculate import getCustomerCreditData
                # 客户信用余额
                customerCredit = getCustomerCreditData(one_data.get("customer_code"),
                                                       get_credit_management(sales_org_code),
                                                       sd_item_cat_dict.get("company_code"))
                print(">>>>>customerCredit", customerCredit)
                occupancy_limits = customerCredit.get("occupancy_limits", 0)
                credit_limit = customerCredit.get("credit_limit", 0)
                print(">>>>>occupancy_limits", occupancy_limits)
                print(">>>>>credit_limit", credit_limit)
                if occupancy_limits > credit_limit:
                    if over_picking:
                        one_data['credit_status'] = "C"
                    else:
                        isPass = False
                        message = f'{one_data.get("customer_code")}信用额度为[{credit_limit}]已使用信用额度为[{occupancy_limits}],信用额度已超额'
                        one_data['message'] = message
                        one_data['exec_result'] = "执行失败"
                        is_over_creditBalance = True
                        continue
            else:
                one_data['credit_status'] = "F"

        sys_use_ipn = dn_item_set.get((dn_sn, dn_item)).get("use_ipn")
        sys_mat_code = dn_item_set.get((dn_sn, dn_item)).get("mat_code")
        sys_plant_code = dn_item_set.get((dn_sn, dn_item)).get("plant_code")
        # print("sys_use_ipn>>>>",sys_use_ipn)
        # sys_use_ipn = dn_item_set.get("use_ipn")
        # sys_mat_code = dn_item_set.get("mat_code")
        # sys_plant_code = dn_item_set.get("plant_code")
        if sys_use_ipn == "C":
            if not one_data.get("external_mat_code"):
                isPass = False
                message = '启用等同物料标识,外部编码必输'
                one_data['message'] = message
                one_data['exec_result'] = "执行失败"
                continue

            # mat_code = one_data.get("mat_code")
            # if mat_code not in mat_code_dict:
            #     isPass = False
            #     message = f'{one_data.get("mat_code")}:外部编码关系不存在'
            #     one_data['message'] = message
            #     one_data['exec_result'] = "执行失败"
            #     continue
            #
            # external_mat_code = mat_code_dict.get(mat_code).get("external_mat_code")
            # if one_data.get("external_mat_code") != external_mat_code:
            #     isPass = False
            #     message = '外部编码关系不存在'
            #     one_data['message'] = message
            #     one_data['exec_result'] = "执行失败"
            #     continue
            if one_data.get("external_mat_code") != sys_mat_code:
                isPass = False
                message = f'外部物料编码在{dn_sn}交货单上不存在'
                one_data['message'] = message
                one_data['exec_result'] = "执行失败"
                continue

        if not dn_sn or not dn_item:
            isPass = False
            message = '交货单号或者行号为空'
            one_data['message'] = message
            one_data['exec_result'] = "执行失败"
            continue

        # dn_item_list = []
        # query_dn_item_sql = 'SELECT * FROM `t_dn_item` WHERE 1 = 1 AND `dn_sn` = {} AND `dn_item` = {}'.format(
        #     repr(dn_sn), repr(dn_item))
        if (dn_sn, dn_item) not in dn_item_set:
            # if not dn_item_set:
            isPass = False
            message = '交货单号、行号在系统中不存在'
            one_data['message'] = message
            one_data['exec_result'] = "执行失败"
            continue
        if one_data.get("external_mat_code"):
            mat_code = one_data.get('external_mat_code')
        else:
            mat_code = one_data.get('mat_code')
        # logger.printInfo("mat_code", mat_code)
        mat_desc = one_data.get('mat_desc')
        # plant_code = one_data.get('plant_code', '')
        # store_loc = one_data.get('stor_loc_code')

        # sys_mat_code_list = []
        # for each_dn_item in dn_item_list:
        #     sys_mat_code = each_dn_item.get('mat_code')
        #     sys_mat_code_list.append(sys_mat_code)
        if not mat_code and mat_desc:
            query_mat_ret = query_mat_code_by_desc(mat_desc)
            if not query_mat_ret:
                isPass = False
                message = '物料编码为空，物料描述未匹配到系统中物料编码'
                one_data['message'] = message
                one_data['exec_result'] = "执行失败"
                continue
            else:
                mat_ret = query_mat_ret[0]
                if mat_ret and isinstance(mat_ret, dict):
                    one_data['mat_code'] = mat_ret.get('mat_code')
                    mat_code = one_data['mat_code']
        #  填写的物料号与交货单号+行号的对应关系是否正确
        if mat_code and mat_code != sys_mat_code:
            isPass = False
            message = f'填写的物料号与交货单号+行号的对应关系不正确'
            one_data['message'] = message
            one_data['exec_result'] = "执行失败"
            continue
        print("sys_plant_code>>>", sys_plant_code)
        print("""one_data.get("stor_loc_code")""", one_data.get("stor_loc_code"))
        if (
                sys_plant_code,
                one_data.get("stor_loc_code") or one_data.get("stor_loc")) not in plant_storage_location_set:
            isPass = False
            message = f'库存地点：{one_data.get("stor_loc_code") or one_data.get("stor_loc")}与交货单工厂{sys_plant_code}分配关系不存在;'
            one_data['message'] = message
            one_data['exec_result'] = "执行失败"
            continue

        batch_sn = one_data.get('batch_sn')
        mat_code = one_data.get('mat_code', '')
        eq_mat_code = one_data.get('eq_mat_code', '')
        store_loc = one_data.get("stor_loc_code") or one_data.get("stor_loc")
        if not batch_sn:
            batch_attr_fields = one_data.keys() & name_code_dict.keys()
            query_batch_attr = {}
            # 若用户在模板中只填写批次特性，则需要根据批次特性匹配系统批次号
            for attr_field in batch_attr_fields:
                field_code = name_code_dict.get(attr_field)
                if one_data.get(attr_field):
                    query_batch_attr[field_code] = one_data.get(attr_field)

            if query_batch_attr:
                query_batch_ret = get_batch_sn_by_attr(query_batch_attr)
                if not query_batch_ret:
                    isPass = False
                    message = '批次号为空，根据批次特性未匹配到系统批次号'
                    one_data['message'] = message
                    one_data['exec_result'] = "执行失败"
                    continue
                else:
                    result = query_batch_ret[0]
                    if result and isinstance(result, dict):
                        batch_sn = result.get('batch_sn')
                        one_data['batch_sn'] = batch_sn
        # 如模板中填写了批次号，检查工厂+库存地点下该物料是否存在该批次号
        batch_sn_valid = False
        if sd_item_cat_dict.get("shipping_returns") == "1":
            if mat_code and sys_plant_code and store_loc and batch_sn:
                it_key = mat_code + '-' + sys_plant_code + '-' + store_loc
                # print("it_key", it_key)
                # print("inventory_dict", inventory_dict)
                if it_key and it_key in inventory_dict:
                    invent = inventory_dict.get(it_key)
                    if invent and isinstance(invent, dict):
                        in_batch_sn = invent.get(batch_sn)
                        if in_batch_sn:
                            batch_sn_valid = True
                            # one_data['basic_unit'] = in_batch_sn.get('basic_uom')
                            # one_data['batch_unit'] = in_batch_sn.get('batch_uom')
                            # one_data['basic_qty'] = in_batch_sn.get('basic_qty')
                        else:
                            isPass = False
                            message = f'批号[{batch_sn}]没有获取到详细数据'
                            one_data['message'] = message
                            one_data['exec_result'] = "执行失败"
                            continue
                else:
                    isPass = False
                    message = f'物料[{mat_code}]对应的批次[{batch_sn}]不存在'
                    one_data['message'] = message
                    one_data['exec_result'] = "执行失败"
                    continue
        # if sd_item_cat_dict.get("shipping_returns") == "1":
        #     continue
        elif sd_item_cat_dict.get("shipping_returns") == "2":
            if not batch_sn:
                isPass = False
                message = f'批号必填'
                one_data['message'] = message
                one_data['exec_result'] = "执行失败"
                continue
            if batch_number_set.get((mat_code, batch_sn)) is None:
                isPass = False
                message = f'{mat_code}物料不存在{batch_sn}批次，请检查'
                one_data['message'] = message
                one_data['exec_result'] = "执行失败"
                continue
        else:
            isPass = False
            message = f't_ao_sd_item_category 表未找到{sd_item_cat_dict.get("sales_item_category")}项目类别'
            one_data['message'] = message
            one_data['exec_result'] = "执行失败"
            continue

        # if eq_mat_code and plant_code and store_loc and batch_sn:
        #     it_key = eq_mat_code + '-' + plant_code + '-' + store_loc
        #     if it_key and it_key in inventory_dict:
        #         invent = inventory_dict.get(it_key)
        #         if invent and isinstance(invent, dict):
        #             in_batch_sn = invent.get(batch_sn)
        #             if in_batch_sn:
        #                 batch_sn_valid = True
        #                 # one_data['basic_unit'] = in_batch_sn.get('basic_uom')
        #                 # one_data['batch_unit'] = in_batch_sn.get('batch_uom')
        #                 # one_data['basic_qty'] = in_batch_sn.get('basic_qty')
        #             else:
        #                 isPass = False
        #                 message = f'批号[{eq_mat_code}]没有获取到详细数据'
        #                 one_data['message'] = message
        #                 continue
        #     else:
        #         isPass = False
        #         message = f'等同物料[{eq_mat_code]不存在'
        #         one_data['message'] = message
        #         continue

        # if not one_data.get('basic_unit'):
        #     one_data['basic_unit'] = ''
        # if not one_data.get('batch_unit'):
        #     one_data['batch_unit'] = ''
        # if not one_data.get('basic_qty'):
        #     one_data['basic_qty'] = 0

        if not batch_sn_valid and not one_data.get('batch_sn'):
            isPass = False
            message = '工厂+库存地点下该物料未匹配到该批次号'
            one_data['message'] = message
            one_data['exec_result'] = "执行失败"
            continue

        # query_dn_item = dn_item_set.get((dn_sn,dn_item)).get("mat_code")
        # sales_uom = dn_item_set.get((dn_sn, dn_item)).get("transaction_uom")
        # try:
        #     planned_delivery_quantity = one_data.get('planned_delivery_quantity', 0)
        #     planned_delivery_quantity = Decimal(planned_delivery_quantity)
        # except Exception:
        #     isPass = False
        #     message = '交货数量 请填写数字类型'
        #     one_data['message'] = message
        #     continue
        #
        # try:
        #     alloc_bs_qty = one_data.get('alloc_bs_qty', 0)
        #     alloc_bs_qty = Decimal(alloc_bs_qty)
        # except Exception:
        #     isPass = False
        #     message = '分配基本数量 请填写数字类型'
        #     one_data['message'] = message
        #     continue
        #
        # try:
        #     alloc_bt_qty = one_data.get('alloc_bt_qty', 0)
        #     alloc_bt_qty = Decimal(alloc_bt_qty)
        # except Exception:
        #     isPass = False
        #     message = '分配批次数量 请填写数字类型'
        #     one_data['message'] = message
        #     continue
        #
        # count_key = dn_sn + str(dn_item)
        # # 根据 物料编码 查询物料主数据的 基本单位 和 成本单位
        # mat_info_list = query_mat_unit_by_code(mat_code, plant_code)
        # mat_info = mat_info_list[0]
        # if sales_uom and sales_uom == mat_info.get('basic_uom'):
        #     if count_key not in basic_counter:
        #         basic_counter[count_key] = Decimal(alloc_bs_qty)
        #     else:
        #         basic_counter[count_key] += Decimal(alloc_bs_qty)
        #     total_alloc_bs_qty = basic_counter.get(count_key)
        #     if total_alloc_bs_qty and total_alloc_bs_qty > Decimal(planned_delivery_quantity):
        #         isPass = False
        #         message = '交货单号+行对应的"分配基本数量"之和不能大于交货数量'
        #         one_data['message'] = message
        #         continue
        #
        # elif sales_uom and sales_uom == mat_info.get('cost_uom'):
        #     if count_key not in batch_counter:
        #         batch_counter[count_key] = Decimal(alloc_bt_qty)
        #     else:
        #         batch_counter[count_key] += Decimal(alloc_bt_qty)
        #     total_alloc_bt_qty = batch_counter.get(count_key)
        #     if total_alloc_bt_qty and total_alloc_bt_qty > Decimal(planned_delivery_quantity):
        #         isPass = False
        #         message = '交货单号+行对应的"分配批次数量"之和不能大于交货数量'
        #         one_data['message'] = message
        #         continue
        unpick_qty = one_data.get("unpick_qty")
        if unpick_qty:
            picking_qty = one_data.get("picking_qty")
            picked_qty = one_data.get("picked_qty")
            if picking_qty:
                if float(picking_qty) > unpick_qty:
                    isPass = False
                    one_data['message'] = "拣配数量不能大于未拣配数量"
                    one_data['exec_result'] = "执行失败"
            elif picked_qty:
                if float(picked_qty) > unpick_qty:
                    isPass = False
                    one_data['message'] = "拣配数量不能大于未拣配数量"
                    one_data['exec_result'] = "执行失败"
        if one_data.get("message") == "":
            one_data["message"] = message
            one_data['exec_result'] = "执行成功"
    print("end_time_for>>", time.time() - start_time_for)
    return origin_data, isPass, pickup_batch_dict, is_over_creditBalance


@calc_time
def format_check1(origin_data, required_data, replace_name_reversal):
    if not origin_data:
        return origin_data, False, {}

    isPass = True
    message = '校验成功'

    # 1. 预计算和批量获取
    start_time = time.time()

    # 批量获取所有必要数据
    name_code_dict = gen_field_name_code_dict()
    print(f"field_name_code end>> {time.time() - start_time}")

    # 预提取关键字段，减少循环中的get调用
    dn_data_list = []
    for i in origin_data:
        dn_data_list.append({
            "dn_sn": i.get("dn_sn"),
            "dn_item": i.get("dn_item"),
            "mat_code": i.get("mat_code"),
            "batch_sn": i.get("batch_sn")
        })

    # 批量获取所有数据
    fetch_tasks = [
        ("dn_item_set", get_dn_item_db, dn_data_list),
        ("batch_number_set", get_t_batch_number, dn_data_list),
        ("plant_storage_location_set", get_os_plant_storage_location_alloc_db, None),
        ("mat_code_dict", query_mat_code, None),
        ("sd_item_cat_db_dict", get_sd_item_cat_db_dict, dn_data_list)
    ]

    data_cache = {}
    for name, func, args in fetch_tasks:
        task_start = time.time()
        if args:
            data_cache[name] = func(args) if args is not None else func()
        else:
            data_cache[name] = func()
        print(f"{name} end>> {time.time() - task_start}")

    # 2. 预计算查找表
    dn_item_set = data_cache['dn_item_set']
    batch_number_set = data_cache['batch_number_set']
    plant_storage_location_set = data_cache['plant_storage_location_set']
    mat_code_dict = data_cache['mat_code_dict']
    sd_item_cat_db_dict = data_cache['sd_item_cat_db_dict']

    # 3. 优化数据结构查找
    name_code_keys = set(name_code_dict.keys())
    required_keys = set(required_data)
    replace_name_map = replace_name_reversal or {}

    # 4. 预构建工厂-库存地点查找表
    plant_loc_set = set()
    for plant, loc in plant_storage_location_set:
        plant_loc_set.add((plant, loc))

    # 5. 预构建物料-批次查找表
    batch_mat_set = set()
    for mat_code, batch_sn in batch_number_set:
        batch_mat_set.add((mat_code, batch_sn))

    # 6. 预构建DN项查找表
    dn_item_info = {}
    for key, value in dn_item_set.items():
        dn_item_info[key] = value

    # 7. 主处理循环优化
    pickup_batch_dict = {}

    start_time_for = time.time()

    for one_data in origin_data:
        # 初始化字段
        basic_unit = one_data.get('basic_unit', '')
        batch_unit = one_data.get('batch_unit', '')
        basic_qty = one_data.get('basic_qty', '')

        if not basic_unit:
            one_data['basic_unit'] = ''
        if not batch_unit:
            one_data['batch_unit'] = ''
        if not basic_qty:
            one_data['basic_qty'] = ''

        one_data['message'] = ""

        # 构建pickup_batch_dict键
        dn_sn = one_data.get('dn_sn', '')
        dn_item_str = one_data.get('dn_item', '')
        query_key = f"{dn_sn}{dn_item_str}"

        if query_key not in pickup_batch_dict:
            pickup_batch_dict[query_key] = [one_data]
        else:
            pickup_batch_dict[query_key].append(one_data)

        # 转换dn_item为整数
        try:
            dn_item = int(dn_item_str) if dn_item_str else 0
        except ValueError:
            dn_item = 0

        # 获取SD项目类别
        sd_item_cat_dict = sd_item_cat_db_dict.get((dn_sn, dn_item), {})

        # 1. 必填字段检查
        required_failed = False
        for key in required_keys:
            if key in one_data:
                value = one_data.get(key)
                if value is None or (isinstance(value, str) and not value.strip()):
                    field_name = replace_name_map.get(key, key)
                    error_msg = f'{field_name} 是必填字段'
                    one_data['message'] = one_data.get('message', '') + error_msg
                    one_data['exec_result'] = "执行失败"
                    isPass = False
                    required_failed = True
                    continue

        if required_failed:
            continue

        # 2. DN项存在性检查
        if not dn_sn or not dn_item:
            error_msg = '交货单号或者行号为空'
            one_data['message'] = error_msg
            one_data['exec_result'] = "执行失败"
            isPass = False
            continue

        dn_key = (dn_sn, dn_item)
        if dn_key not in dn_item_info:
            error_msg = '交货单号、行号在系统中不存在'
            one_data['message'] = error_msg
            one_data['exec_result'] = "执行失败"
            isPass = False
            continue

        # 3. 获取系统信息
        sys_info = dn_item_info[dn_key]
        sys_use_ipn = sys_info.get("use_ipn", "")
        sys_mat_code = sys_info.get("mat_code", "")
        sys_plant_code = sys_info.get("plant_code", "")

        # 4. 等同物料检查
        if sys_use_ipn == "C":
            external_mat_code = one_data.get("external_mat_code")
            if not external_mat_code:
                error_msg = '启用等同物料标识,外部编码必输'
                one_data['message'] = error_msg
                one_data['exec_result'] = "执行失败"
                isPass = False
                continue

            mat_code = one_data.get("mat_code")
            mat_info = mat_code_dict.get(mat_code) if mat_code else None

            if not mat_info:
                error_msg = f'{mat_code}:外部编码关系不存在'
                one_data['message'] = error_msg
                one_data['exec_result'] = "执行失败"
                isPass = False
                continue

            db_external_mat_code = mat_info.get("external_mat_code")
            if external_mat_code != db_external_mat_code:
                error_msg = '外部编码关系不存在'
                one_data['message'] = error_msg
                one_data['exec_result'] = "执行失败"
                isPass = False
                continue

            if external_mat_code != sys_mat_code:
                error_msg = f'外部物料编码在{dn_sn}交货单上不存在'
                one_data['message'] = error_msg
                one_data['exec_result'] = "执行失败"
                isPass = False
                continue

        # 5. 物料编码处理
        mat_code = one_data.get("external_mat_code") or one_data.get('mat_code')
        mat_desc = one_data.get('mat_desc')

        if not mat_code and mat_desc:
            query_mat_ret = query_mat_code_by_desc(mat_desc)
            if not query_mat_ret:
                error_msg = '物料编码为空，物料描述未匹配到系统中物料编码'
                one_data['message'] = error_msg
                one_data['exec_result'] = "执行失败"
                isPass = False
                continue
            else:
                mat_ret = query_mat_ret[0]
                if mat_ret and isinstance(mat_ret, dict):
                    one_data['mat_code'] = mat_ret.get('mat_code')
                    mat_code = one_data['mat_code']

        # 6. 物料编码匹配检查
        if mat_code and mat_code != sys_mat_code:
            error_msg = '填写的物料号与交货单号+行号的对应关系不正确'
            one_data['message'] = error_msg
            one_data['exec_result'] = "执行失败"
            isPass = False
            continue

        # 7. 工厂-库存地点检查
        stor_loc = one_data.get("stor_loc_code") or one_data.get("stor_loc")
        if (sys_plant_code, stor_loc) not in plant_loc_set:
            error_msg = f'库存地点：{stor_loc}与交货单工厂{sys_plant_code}分配关系不存在'
            one_data['message'] = error_msg
            one_data['exec_result'] = "执行失败"
            isPass = False
            continue

        # 8. 批次号处理
        batch_sn = one_data.get('batch_sn')
        if not batch_sn:
            # 使用集合交集提高效率
            data_keys = set(one_data.keys())
            batch_attr_fields = data_keys.intersection(name_code_keys)

            if batch_attr_fields:
                query_batch_attr = {}
                for attr_field in batch_attr_fields:
                    field_code = name_code_dict.get(attr_field)
                    attr_value = one_data.get(attr_field)
                    if attr_value:
                        query_batch_attr[field_code] = attr_value

                if query_batch_attr:
                    query_batch_ret = get_batch_sn_by_attr(query_batch_attr)
                    if not query_batch_ret:
                        error_msg = '批次号为空，根据批次特性未匹配到系统批次号'
                        one_data['message'] = error_msg
                        one_data['exec_result'] = "执行失败"
                        isPass = False
                        continue
                    else:
                        result = query_batch_ret[0]
                        if result and isinstance(result, dict):
                            batch_sn = result.get('batch_sn')
                            one_data['batch_sn'] = batch_sn

        # 9. 根据shipping_returns处理
        shipping_returns = sd_item_cat_dict.get("shipping_returns", "")

        if shipping_returns == "1":
            # 直接继续后续检查
            pass
        elif shipping_returns == "2":
            if not batch_sn:
                error_msg = '批号必填'
                one_data['message'] = error_msg
                one_data['exec_result'] = "执行失败"
                isPass = False
                continue

            if mat_code and (mat_code, batch_sn) not in batch_mat_set:
                error_msg = f'{mat_code}物料不存在{batch_sn}批次，请检查'
                one_data['message'] = error_msg
                one_data['exec_result'] = "执行失败"
                isPass = False
                continue
        else:
            sales_item_category = sd_item_cat_dict.get("sales_item_category", "未知")
            error_msg = f't_ao_sd_item_category 表未找到{sales_item_category}项目类别'
            one_data['message'] = error_msg
            one_data['exec_result'] = "执行失败"
            isPass = False
            continue

        # 10. 拣配数量检查
        unpick_qty = one_data.get("unpick_qty")
        if unpick_qty:
            picking_qty = one_data.get("picking_qty")
            picked_qty = one_data.get("picked_qty")

            if picking_qty and picking_qty > unpick_qty:
                error_msg = "拣配数量不能大于未拣配数量"
                one_data['message'] = error_msg
                one_data['exec_result'] = "执行失败"
                isPass = False
                continue
            elif picked_qty and picked_qty > unpick_qty:
                error_msg = "拣配数量不能大于未拣配数量"
                one_data['message'] = error_msg
                one_data['exec_result'] = "执行失败"
                isPass = False
                continue

        # 11. 所有检查通过
        if not one_data.get('message'):
            one_data['message'] = message
            one_data['exec_result'] = "执行成功"

    print(f"end_time_for>> {time.time() - start_time_for}")

    return origin_data, isPass, pickup_batch_dict


# 填充接口缺少的参数
def fill_params(item):
    sql = f""" select `transaction_uom`,`basic_uom`,`cost_uom`,`parallel_uom`,`planned_delivery_quantity`,`picked_qty` from `t_dn_item` where `dn_sn` = '{item.get("dn_sn")}' and `dn_item` = {item.get("dn_item")} """
    db = DbHelper()
    ret = db.query_sql(sql)
    if ret:
        basic_uom = ret[0].get("basic_uom")
        parallel_uom = ret[0].get("parallel_uom")
        transaction_uom = ret[0].get("transaction_uom")
        unpick_qty = ret[0].get("planned_delivery_quantity") - ret[0].get("picked_qty")
        item["basic_uom"] = basic_uom
        item["parallel_uom"] = parallel_uom
        item["transaction_uom"] = transaction_uom
        item["delivery_uom"] = transaction_uom
        picked_qty = float(item["picked_qty"])

        if transaction_uom == basic_uom:
            picked_base_qty = picked_qty
        else:
            code, msg, picked_base_qty = convert_material_unit_qty(item["mat_code"], transaction_uom,
                                                                   basic_uom,
                                                                   picked_qty)
            if code == 500:
                code, msg, picked_base_qty = convert_material_unit_qty(item["mat_code"], basic_uom,
                                                                       parallel_uom,
                                                                       float(picked_qty))
                if code == 500:
                    picked_base_qty = 0
        if transaction_uom == parallel_uom:
            picked_parallel_qty = picked_qty
        else:
            code, msg, picked_parallel_qty = convert_material_unit_qty(item["mat_code"], transaction_uom,
                                                                       parallel_uom,
                                                                       picked_qty)
            if code == 500:
                code, msg, picked_parallel_qty = convert_material_unit_qty(item["mat_code"], basic_uom,
                                                                           parallel_uom,
                                                                           float(picked_qty))
                if code == 500:
                    picked_parallel_qty = 0
        item["unpick_qty"] = unpick_qty
        item["picked_base_qty"] = picked_base_qty
        item["picked_parallel_qty"] = picked_parallel_qty
    return item


def get_dn_item(so_sn, so_item, dn_sn, dn_item, picked_qty, mat_code, batch_sn):
    db = DbHelper()
    print("so_sn, dn_sn, dn_item, picked_qty, mat_code, batch_sn",so_sn, dn_sn, dn_item, picked_qty, mat_code, batch_sn)
    # 1. 查询销售项目类别
    dn_item_sql = f"SELECT `sales_item_category` FROM `t_dn_item` WHERE `dn_sn`='{dn_sn}' AND `dn_item`='{dn_item}'"
    dn_item_data = db.query_sql(dn_item_sql)
    if not dn_item_data:
        return True, "未查询到订单行信息"

    sales_item_category = dn_item_data[0]['sales_item_category']

    # 2. 查询是否需要批次退货数量校验
    flag_sql = f"SELECT `return_batch_quantity_validation_flag` FROM `t_ao_sd_item_category` WHERE `sales_item_category`='{sales_item_category}'"
    item_category_data = db.query_sql(flag_sql)
    if not item_category_data or str(item_category_data[0]['return_batch_quantity_validation_flag']) != "1":
        return True, "无需进行批次退货数量校验"
    print("1" * 50)
    # 3. 需要校验 → 查询库存分配的已拣货/已退货数量
    # ===================== 查询销售订单 =====================
    sales_order_item_sql = f"""
        SELECT `rel_document_no`, `ref_document_mat`
        FROM `t_sales_order_item` 
        WHERE `so_sn` = '{so_sn}'
        AND `so_items` = {so_item}
    """
    sales_order_item_data = db.query_sql(sales_order_item_sql)
    if not sales_order_item_data:
        return 206, f"销售订单不存在 so_sn={so_sn}"
    print("2" * 50)
    rel_document_no = sales_order_item_data[0]['rel_document_no']
    ref_document_mat = sales_order_item_data[0]['ref_document_mat']

    # ===================== 查询交货单 =====================
    dn_item_sql = f"""
        SELECT `dn_sn`, `dn_item`
        FROM `t_dn_item` 
        WHERE `so_sn` = '{rel_document_no}'
        AND `so_items` = '{ref_document_mat}'
    """
    dn_item_data = db.query_sql(dn_item_sql)
    if not dn_item_data:
        return 206, f"交货单行不存在 so_sn={rel_document_no}, dn_item={ref_document_mat}"
    print("3" * 50)
    dn_sn = dn_item_data[0]["dn_sn"]
    dn_item = dn_item_data[0]["dn_item"]

    # ===================== 查询库存分配（按 packing_date 升序） =====================
    sql_get_inventory = f"""
        SELECT `returned_quantity`, `picked_qty`, `picking_document`
        FROM `t_dn_inventory_alloc` 
        WHERE `dn_sn` = '{dn_sn}'
        AND `dn_item` = {dn_item}
        AND `mat_code` = '{mat_code}'
        AND `batch_sn` = '{batch_sn}'
        ORDER BY `packing_date` ASC
    """
    inventory_alloc_data = db.query_sql(sql_get_inventory)
    if not inventory_alloc_data:
        return True, "无库存分配数据，无需校验"
    print("4" * 50)
    # 4. 累计数量
    pickend_total = 0
    returned_total = 0
    for item in inventory_alloc_data:
        pickend_total += item.get("picked_qty", 0)
        returned_total += item.get("retuened_quantity", 0)  

    # 5. 校验：可退货数量 = 已拣货 - 已退货
    available_return_qty = pickend_total - returned_total
    if picked_qty > available_return_qty:
        return False, f"{batch_sn}批次累计退货数量不可大于原出货数量"
    print("5" * 50)
    return True, "退货数量校验通过"



def update_returned_quantity(db_helper, so_items, operation_type=None):
    """
    退货数量更新：t_dn_inventory_alloc
    业务规则：
    1. 修改后已退货数量 = 修改前已退货数量 - 修改前退货拣配数量 + 修改后退货拣配数量
    2. 新建：修改前=0，新=本次拣配数量
    3. 修改：修改前=旧拣配数量，新=本次拣配数量
    4. 删除：修改前=旧拣配数量，新=0
    5. 分摊逻辑：按物料+批次，按拣配日期升序，优先扣减最早的拣配单，直到扣完
    """
    for item in so_items:
        mat_code = item.get("mat_code", "")
        batch_sn = item.get("batch_sn", "")
        new_order_qty = item.get("picked_qty", 0)  # 本次数量
        so_sn = item.get("so_sn", "")
        so_item = item.get("so_items", "")
        picking_document = item.get("picking_document", "")

        # ===================== 查询销售订单 =====================
        sales_order_item_sql = f"""
            SELECT `rel_document_no`, `ref_document_mat`
            FROM `t_sales_order_item` 
            WHERE `so_sn` = '{so_sn}'
            AND `so_items` = {so_item}
        """
        sales_order_item_data = db_helper.query_sql(sales_order_item_sql)
        if not sales_order_item_data:
            return 206, f"销售订单不存在 so_sn={so_sn}"
        
        rel_document_no = sales_order_item_data[0]['rel_document_no']
        ref_document_mat = sales_order_item_data[0]['ref_document_mat']

        # ===================== 查询交货单 =====================
        dn_item_sql = f"""
            SELECT `dn_sn`, `dn_item`
            FROM `t_dn_item` 
            WHERE `so_sn` = '{rel_document_no}'
            AND `so_items` = '{ref_document_mat}'
        """
        dn_item_data = db_helper.query_sql(dn_item_sql)
        if not dn_item_data:
            return 206, f"交货单行不存在 so_sn={rel_document_no}, dn_item={ref_document_mat}"
        
        dn_sn = dn_item_data[0]["dn_sn"]
        dn_item = dn_item_data[0]["dn_item"]

        # ===================== 查询库存分配（按 packing_date 升序） =====================
        sql_get_inventory = f"""
            SELECT `returned_quantity`, `picked_qty`, `picking_document`
            FROM `t_dn_inventory_alloc` 
            WHERE `dn_sn` = '{dn_sn}'
            AND `dn_item` = '{dn_item}'
            AND `mat_code` = '{mat_code}'
            AND `batch_sn` = '{batch_sn}'
            ORDER BY `packing_date` ASC
        """
        inventory_result = db_helper.query_sql(sql_get_inventory)
        if not inventory_result:
            return 206, f"无库存分配数据 dn_sn={dn_sn}, dn_item={dn_item}"

        # 累计当前总已退货数量
        current_returned_qty = 0
        for ir in inventory_result:
            current_returned_qty += ir.get("returned_quantity", 0)

        # ===================== 计算目标总退货数 =====================
        new_returned_qty = 0
        old_order_qty = 0

        if operation_type == "delete":
            new_returned_qty = current_returned_qty - new_order_qty

        elif operation_type == "update":
            if picking_document:
                sql = f"select `picked_qty` from `t_dn_inventory_alloc` where `picking_document`='{picking_document}'"
                picking_data = db_helper.query_sql(sql)
                if picking_data:
                    old_order_qty = picking_data[0]['picked_qty']
            new_returned_qty = current_returned_qty - old_order_qty + new_order_qty

        elif operation_type == "create":
            new_returned_qty = current_returned_qty + new_order_qty

        # 负数校验
        if new_returned_qty < 0:
            return 206, f"退货数量不能为负数：{new_returned_qty}"

        # ===================== 核心逻辑：重置 + 从头填充 =====================
        remaining = new_returned_qty

        # 第一步：先把所有行的退货数量重置为 0
        # for i in inventory_result:
        #     pick_doc = i["picking_document"]
        sql_reset = f"""
            UPDATE t_dn_inventory_alloc
            SET returned_quantity = 0
            WHERE `dn_sn` = '{dn_sn}'
            AND `dn_item` = '{dn_item}'
            AND `mat_code` = '{mat_code}'
            AND `batch_sn` = '{batch_sn}'
        """
        db_helper.exec_sql(sql_reset)

        # 第二步：按升序顺序填充目标退货数量
        for i in inventory_result:
            if remaining <= 0:
                break

            picked_qty = i["picked_qty"]
            pick_doc = i["picking_document"]

            # 这一行最多能填多少
            fill = min(remaining, picked_qty)

            # 更新
            sql_update = f"""
                UPDATE t_dn_inventory_alloc
                SET returned_quantity = {fill}
                WHERE picking_document = '{pick_doc}'
                AND dn_item = '{dn_item}'
            """
            db_helper.exec_sql(sql_update)

            # 扣减剩余数量
            remaining -= fill

        # 检查是否填超了
        if remaining > 0:
            return 206, f"库存可退货数量不足，剩余未填：{remaining}"

    return 200, "退货数量更新成功"






@calc_time
def inventoryPickUp(pickup_batch_data, user_id, pickup_data=None, test_run=0, replace_name_reversal={},
                    over_picking=False):
    """
    pickup_batch_data:
    [
       {
        "dn_sn":str, # 交货单号
         "dn_item":str, # 交货单行号
         "mat_code":str, # 物料编码
         "planned_delivery_quantity":int, # 计划交货数量
         "stor_loc_code":str, # 库存地点
         "eq_mat_code":int, # 等同物料编码
         "basic_qty":int, # 基本数量
         "basic_unit":str, # 基本单位
         "batch_unit":str, # 成本单位
         "batch_sn":str, # 批次号
         "unpick_qty":int, # 未拣配数量
         "picking_qty":int, # 拣配数量
         "picked_qty":int,# 已拣配数量
         "customer_code":"", #customer_code1 客户编码
    }
    ]
    user_id: 用户id
    test_run:1/正式运行 0 /测试运行
    """
    print("pickup_batch_data", pickup_batch_data)
    if not pickup_data:
        pickup_data_map = {}
    else:
        pickup_data_map = {}
        for each in pickup_data:
            key_tuple = (each["dn_sn"], str(each["dn_item"]))
            pickup_data_map[key_tuple] = each["packing_date"]
    for each1 in pickup_batch_data:
        if each1.get("packing_date"):
            key_tuple = (each1.get("dn_sn"), str(each1.get("dn_item")))
            pickup_data_map[key_tuple] = each1["packing_date"]
    print("pickup_data_map>>>>>>", pickup_data_map)
    delete_pickup_batch_list = []
    pickup_batch_list = []
    for item in pickup_batch_data:
        if item.get("delete") == 1:
            delete_pickup_batch_list.append(item)
        else:
            if "external_mat_code" not in item:
                item["external_mat_code"] = item.get("eq_mat_code", "")
            if item.get("dn_sn") and item.get("dn_item") and item.get("mat_code")and item.get("picked_qty"):
                item = fill_params(item)
            pickup_batch_list.append(item)
    if not pickup_batch_list:
        return 400, "请检查文件数据为空", [], []

    if pickup_batch_list:
        required_data = ["dn_sn", "dn_item", "mat_code", "stor_loc_code", "batch_sn"]
        # 5月28日需求 4286 销售退货-校验逻辑完善 前端需要开发了打开注释
        # required_data = ["so_sn", "so_items", "dn_sn", "dn_item", "mat_code", "stor_loc_code", "batch_sn"]
        current_time = datetime.now()
        formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S")
        # res_list = []
        pickup_batch_list, isPass, pickup_batch_dict, is_over_creditBalance = format_check(pickup_batch_list,
                                                                                           required_data=required_data,
                                                                                           replace_name_reversal=replace_name_reversal,
                                                                                           over_picking=over_picking)
        
        if is_over_creditBalance:
            pickup_batch_list.extend(delete_pickup_batch_list)
            return 203, "拣配校验失败,信用已超额", pickup_batch_list, []

        if not isPass:
            pickup_batch_list.extend(delete_pickup_batch_list)
            return 400, "拣配校验失败", pickup_batch_list, []

        is_all_fail, is_all_success = False, False

        packingStatusDict = getDataDnitemStats(pickup_batch_list)
        # print("pickup_batch_dict:", pickup_batch_dict)
        picking_document_dict = {}
        # db = DbHelper()
        # exec_status = {}
        exec_status = []
        print("exec_status>>>1", exec_status)
        pickup_batch_dict_start = time.time()

        for query_key, pickup_values in pickup_batch_dict.items():
            index, sum_picked_qty, planned_delivery_quantity = 1, 0.0, 0.0
            alloc_records = []
            status = 1
            pickup_values_start = time.time()
            is_fail = False
            for pickup_batch in pickup_values:
                # try:
                dn_item = pickup_batch.get('dn_item')
                # pick_qty, basic_qty, alloc_bs_qty, alloc_bt_qty, planned_delivery_quantity, parallel_qty, alloc_basic_qty, picked_base_qty, parallel_uom = numeric_conversion(pickup_batch)
                conversion_ret = numeric_conversion(pickup_batch)
                print("conversion_ret>>>", conversion_ret)
                if conversion_ret.get("code") == 400:
                    pickup_batch['message'] = conversion_ret.get("msg", "")
                    is_fail = True
                    status = 0
                    # exec_status[query_key] = status
                    exec_status.append(status)
                    break
                pick_qty = conversion_ret.get("pick_qty")  # 拣配数量
                picked_base_qty = conversion_ret.get("picked_base_qty")
                picked_parallel_qty = conversion_ret.get("picked_parallel_qty")
                parallel_uom = conversion_ret.get("parallel_uom")
                transaction_uom = conversion_ret.get("transaction_uom")
                basic_uom = conversion_ret.get("basic_unit") or conversion_ret.get("basic_uom")
                remaining_planned_delivery_quantity = conversion_ret.get("remaining_planned_delivery_quantity")
                planned_delivery_quantity = float(conversion_ret.get("planned_delivery_quantity", 0))
                key_date_tuple = (pickup_batch.get('dn_sn', ""), str(dn_item))
                print("""pickup_data_map.get(key_date_tuple, formatted_time) >?>>>""",
                      pickup_data_map.get(key_date_tuple))
                dn_it_alloc_item = {
                    "id": pickup_batch.get('id'),
                    "dn_sn": pickup_batch.get('dn_sn'),  # 交货单号
                    "dn_item": str(dn_item),  # 交货单行号
                    "batch_item": str(dn_item) + str(index) + "0",  # 批次行号
                    "stor_loc_code": pickup_batch.get('stor_loc_code'),  # 库存地点
                    "actual_plant": pickup_batch.get('actual_plant', ""),  # 实际出货工厂
                    "actual_stor": pickup_batch.get('actual_stor', ""),  #
                    "batch_sn": pickup_batch.get('batch_sn'),  # 批次号
                    "mat_code": pickup_batch.get('mat_code'),  # 物料编码
                    "external_mat_code": pickup_batch.get('external_mat_code'),  # 外部物料编码
                    "eq_mat_code": pickup_batch.get('eq_mat_code'),  # 等同物料编码
                    "picked_qty": pick_qty,  # 拣配数量
                    "picked_base_qty": picked_base_qty,  #
                    # "planned_delivery_quantity":planned_delivery_quantity ,  #
                    # "POD_qty": pickup_batch.get('POD_qty', 0.0),
                    "packing_date": pickup_data_map.get(key_date_tuple, formatted_time) or formatted_time,  # 拣配日期
                    "create_id": user_id,
                    "update_id": user_id,
                    "create_time": formatted_time,
                    "update_time": formatted_time,
                    "picked_parallel_qty": picked_parallel_qty,
                    "parallel_uom": parallel_uom,
                    "basic_uom": basic_uom,
                    "transaction_uom": transaction_uom,
                    "posting_status": conversion_ret.get("posting_status"),
                    "pod_status": conversion_ret.get("pod_status"),
                    "billing_status": conversion_ret.get("billing_status"),
                    "credit_control_code": pickup_batch.get('credit_control_code'),
                    "credit_status": pickup_batch.get('credit_status'),
                }
                # 计算已拣配数量（基本单位）- picked_base_qty  平行数量- parallel_qty 平行单位 parallel_uom

                # if not pick_qty and alloc_bs_qty:
                #     qty += alloc_bs_qty
                # else:
                sum_picked_qty += pick_qty

                # print('qty: {} planned_delivery_quantity: {} basic_qty: {}'.format(qty, planned_delivery_quantity, basic_qty))
                # print('sum_picked_qty: {} remaining_planned_delivery_quantity: {}'.format(sum_picked_qty, remaining_planned_delivery_quantity))
                if sum_picked_qty > remaining_planned_delivery_quantity:
                    print("拣配数量不可大于交货数量，请检查！")
                    pickup_batch['message'] = "拣配数量不可大于交货数量，请检查！"
                    pickup_batch['exec_result'] = "执行失败"
                    is_fail = True
                    status = 0
                    # exec_status[query_key] = status
                    exec_status.append(status)
                    break

                # elif pick_qty > basic_qty or alloc_bs_qty > basic_qty:
                #     pickup_batch['message'] = "拣配数量大于批次数量，请检查！"
                #     is_fail = True
                #     break
                if packingStatusDict.get((dn_it_alloc_item.get('dn_sn'), dn_it_alloc_item.get('dn_item'),
                                          dn_it_alloc_item.get('mat_code'))) == "C":
                    print("存在已完全拣配项目，不允许再次确认拣配！")
                    pickup_batch['message'] = "存在已完全拣配项目，不允许再次确认拣配！"
                    pickup_batch['exec_result'] = "执行失败"
                    is_fail = True
                    status = 0
                    # exec_status[query_key] = status
                    exec_status.append(status)
                    break
                # else:
                #     pickup_batch['message'] = "存在已完全拣配项目，不允许再次确认拣配！"
                index += 1
                alloc_records.append(dn_it_alloc_item)
            print("pickup_values_end", time.time() - pickup_values_start)
            # except Exception as e:
            #     is_fail = True
            #     is_success = False
            #     print(str(e))
            #     continue
            # print("alloc_records:", alloc_records)
            if not is_fail:
                insert_inventory_alloc_start = time.time()
                if alloc_records and test_run == 1:
                    # 交货单库存分配 数据保存  [交货单编号+行号: 对应拣配的批次绑定在一起]
                    result, result_data, picking_document_dict = insert_inventory_alloc(alloc_records, formatted_time,
                                                                                        planned_delivery_quantity,
                                                                                        picking_document_dict)
                    print("result:", result)
                    print("result_data:", result_data)
                    print("picking_document_dict:", picking_document_dict)
                    if not result:
                        is_fail = True
                        result_dict = {}
                        # 为 result_data 创建索引
                        for ndata in alloc_records:
                            if not ndata.get("id"):
                                # 为没有id的数据创建复合键索引
                                key = (ndata.get("dn_sn"), ndata.get("dn_item"),
                                       ndata.get("mat_code"), ndata.get("batch_sn"))
                                # 存储整个数据对象，方便后续使用
                                result_dict[key] = ndata
                            else:
                                # 有id的数据按dn_sn索引，注意同一个dn_sn可能有多个结果
                                dn_sn = ndata.get("dn_sn")
                                if dn_sn not in result_dict:
                                    result_dict[dn_sn] = []
                                result_dict[dn_sn].append(ndata)
                        for pdata in pickup_batch_list:
                            if not pdata.get("id"):
                                # 为没有id的数据查找匹配
                                key = (pdata.get("dn_sn"), pdata.get("dn_item"),
                                       pdata.get("mat_code"), pdata.get("batch_sn"))
                                if key in result_dict:
                                    ndata = result_dict[key]
                                    pdata["exec_result"] = "执行失败"
                                    pdata["message"] = result_data
                                    pdata["picking_document"] = ndata.get("picking_document", "")
                            else:
                                dn_sn = pdata.get("dn_sn")
                                if dn_sn in result_dict:
                                    # 可能有多个匹配，取第一个
                                    ndata_list = result_dict[dn_sn]
                                    if isinstance(ndata_list, list) and len(ndata_list) > 0:
                                        ndata = ndata_list[0]  # 取第一个匹配项
                                        pdata["exec_result"] = "执行失败"
                                        pdata["message"] = result_data
                                        pdata["picking_document"] = ndata.get("picking_document", "")
                        exec_status.append(0)
                        continue
                    else:
                        is_success = True
                        print(">>>>result_data", result_data)
                        print(">>>>pickup_batch_list", pickup_batch_list)
                        result_dict = {}
                        # 为 result_data 创建索引
                        for ndata in result_data:
                            if not ndata.get("id"):
                                # 为没有id的数据创建复合键索引
                                key = (ndata.get("dn_sn"), ndata.get("dn_item"),
                                       ndata.get("mat_code"), ndata.get("batch_sn"))
                                # 存储整个数据对象，方便后续使用
                                result_dict[key] = ndata
                            else:
                                # 有id的数据按dn_sn索引，注意同一个dn_sn可能有多个结果
                                dn_sn = ndata.get("dn_sn")
                                if dn_sn not in result_dict:
                                    result_dict[dn_sn] = []
                                result_dict[dn_sn].append(ndata)
                        # 遍历 pickup_batch_list 并更新
                        for pdata in pickup_batch_list:
                            if not pdata.get("id"):
                                # 为没有id的数据查找匹配
                                key = (pdata.get("dn_sn"), pdata.get("dn_item"),
                                       pdata.get("mat_code"), pdata.get("batch_sn"))
                                if key in result_dict:
                                    ndata = result_dict[key]
                                    pdata["exec_result"] = "执行成功"
                                    pdata["message"] = "拣配成功"
                                    pdata["picking_document"] = ndata["picking_document"]
                            else:
                                # 为有id的数据查找匹配
                                dn_sn = pdata.get("dn_sn")
                                if dn_sn in result_dict:
                                    # 可能有多个匹配，取第一个
                                    ndata_list = result_dict[dn_sn]
                                    if isinstance(ndata_list, list) and len(ndata_list) > 0:
                                        ndata = ndata_list[0]  # 取第一个匹配项
                                        pdata["exec_result"] = "执行成功"
                                        pdata["message"] = "拣配成功"
                                        pdata["picking_document"] = ndata["picking_document"]

                print("insert_inventory_alloc_end", time.time() - insert_inventory_alloc_start)
            else:
                result_dict = {}
                for ndata in alloc_records:
                    if not ndata.get("id"):
                        # 为没有id的数据创建复合键索引
                        key = (ndata.get("dn_sn"), ndata.get("dn_item"),
                               ndata.get("mat_code"), ndata.get("batch_sn"))
                        # 存储整个数据对象，方便后续使用
                        result_dict[key] = ndata
                    else:
                        # 有id的数据按dn_sn索引，注意同一个dn_sn可能有多个结果
                        dn_sn = ndata.get("dn_sn")
                        if dn_sn not in result_dict:
                            result_dict[dn_sn] = []
                        result_dict[dn_sn].append(ndata)
                for pdata in pickup_batch_list:
                    if not pdata.get("id"):
                        # 为没有id的数据查找匹配
                        key = (pdata.get("dn_sn"), pdata.get("dn_item"),
                               pdata.get("mat_code"), pdata.get("batch_sn"))
                        if key in result_dict:
                            ndata = result_dict[key]
                            pdata["exec_result"] = "执行失败"
                            pdata["message"] = ndata.get("message", "")
                            pdata["picking_document"] = ndata.get("picking_document", "")
                    else:
                        dn_sn = pdata.get("dn_sn")
                        if dn_sn in result_dict:
                            # 可能有多个匹配，取第一个
                            ndata_list = result_dict[dn_sn]
                            if isinstance(ndata_list, list) and len(ndata_list) > 0:
                                ndata = ndata_list[0]  # 取第一个匹配项
                                pdata["exec_result"] = "执行失败"
                                pdata["message"] = ndata.get("message", "")
                                pdata["picking_document"] = ndata.get("picking_document", "")
            # else:
            #     is_success = True
            # exec_status[query_key] = status
            exec_status.append(status)
        print("pickup_batch_dict_end", time.time() - pickup_batch_dict_start)
        # for query_key, pickup_values in pickup_batch_dict.items():
        #     res_list.extend(list(pickup_values))
        print("exec_status>>>2", exec_status)
        if all(exec_status):
            code = 200
            msg = "确认拣配成功" if test_run == 1 else "拣配校验成功"
        elif any(exec_status):
            code = 206
            msg = "确认拣配部分成功" if test_run == 1 else "拣配校验失败"
        else:
            code = 406
            msg = "确认拣配全部失败" if test_run == 1 else "拣配校验失败"

        return code, msg, pickup_batch_list, []

    if delete_pickup_batch_list:
        delete_sql = """"""
        for data in delete_pickup_batch_list:
            if not delete_sql:
                delete_sql += f""" DELETE FROM `t_dn_inventory_alloc` WHERE (`picking_document` = "{data.get("picking_document")}" AND `dn_sn` = '{data.get("dn_sn")}' AND `dn_item` = '{data.get("dn_item")}' AND `batch_item` = '{data.get("batch_item")}' AND `mat_code` = '{data.get("mat_code")}') """
            else:
                delete_sql += f""" OR (`picking_document` = "{data.get("picking_document")}" AND `dn_sn` = '{data.get("dn_sn")}' AND `dn_item` = '{data.get("dn_item")}' AND `batch_item` = '{data.get("batch_item")}' AND `mat_code` = '{data.get("mat_code")}') """

        db = DbHelper()
        status = db.exec_sql(delete_sql)
        if status != -1:
            code = 200
            msg = "保存成功"
        else:
            code = 400
            msg = "保存失败"
        return code, msg, delete_pickup_batch_list, []


def inventoryPickUpYynamics(pickup_batch_data, user_id, test_run=0, replace_name_reversal={}):
    # 数据都是单条，[{}]
    delete_pickup_batch_list = []
    pickup_batch_list = []
    for item in pickup_batch_data:
        if item.get("delete") == 1:
            delete_pickup_batch_list.append(item)
        else:
            if "external_mat_code" not in item:
                item["external_mat_code"] = item.get("eq_mat_code", "")
            pickup_batch_list.append(item)

    if pickup_batch_list:
        required_data = ["dn_sn", "dn_item", "mat_code", "planned_delivery_quantity", "stor_loc_code", "batch_sn"]
        # 5月28日需求 4286 销售退货-校验逻辑完善 前端需要开发了打开注释
        # required_data = ["so_sn", "so_items", "dn_sn", "dn_item", "mat_code", "planned_delivery_quantity", "stor_loc_code", "batch_sn"]
        current_time = datetime.now()
        formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S")
        # pickup_batch_dict = {}
        res_list = []
        pickup_batch_list, isPass, pickup_batch_dict, _ = format_check(pickup_batch_list, required_data=required_data,
                                                                       replace_name_reversal=replace_name_reversal)
        if not isPass:
            return 400, "拣配校验失败", pickup_batch_list, []

        # 5月28日需求 4286 销售退货-校验逻辑完善 前端需要开发了打开注释
        # code, err_msg = update_returned_quantity(DbHelper(), pickup_batch_list, "update")
        # if code != 200:
        #     return 400, err_msg, pickup_batch_list, []

        # 交货单编号 行号 聚合到一起处理   [交货单编号 行号: 可能对应多个拣配批次]
        # for item in pickup_batch_list:
        #     query_key = str(item.get('dn_sn', '')) + str(item.get('dn_item', ''))
        #     if query_key not in pickup_batch_dict:
        #         pickup_batch_dict[query_key] = [item]
        #     else:
        #         pickup_batch_dict[query_key].append(item)

        is_fail, is_success = False, False

        packingStatusDict = getDataDnitemStats([])
        db = DbHelper()
        for query_key, pickup_values in pickup_batch_dict.items():
            index, sum_picked_qty, planned_delivery_quantity = 1, 0.0, 0.0
            alloc_records = []
            for pickup_batch in pickup_values:
                # try:
                dn_item = pickup_batch.get('dn_item')
                # pick_qty, basic_qty, alloc_bs_qty, alloc_bt_qty, planned_delivery_quantity, parallel_qty, alloc_basic_qty, picked_base_qty, parallel_uom = numeric_conversion(pickup_batch)
                conversion_ret = numeric_conversion_dynamics(pickup_batch)
                if conversion_ret.get("code") == 400:
                    pickup_batch['message'] = conversion_ret.get("msg", "")
                    is_fail = True
                    break
                pick_qty = conversion_ret.get("pick_qty")
                picked_base_qty = conversion_ret.get("picked_base_qty")
                picked_parallel_qty = conversion_ret.get("picked_parallel_qty")
                parallel_uom = conversion_ret.get("parallel_uom")
                basic_uom = conversion_ret.get("basic_uom")
                transaction_uom = conversion_ret.get("transaction_uom")
                remaining_planned_delivery_quantity = conversion_ret.get("remaining_planned_delivery_quantity")
                planned_delivery_quantity = float(conversion_ret.get("planned_delivery_quantity"))
                dn_it_alloc_item = {
                    "dn_sn": pickup_batch.get('dn_sn'),  # 交货单号
                    "dn_item": str(dn_item),  # 交货单行号
                    # "batch_item": str(dn_item) + str(index) + "0",  # 批次行号
                    "stor_loc_code": pickup_batch.get('stor_loc_code'),  # 库存地点
                    "batch_sn": pickup_batch.get('batch_sn'),  # 批次号
                    "mat_code": pickup_batch.get('mat_code'),  # 物料编码
                    "eq_mat_code": pickup_batch.get('eq_mat_code'),  # 等同物料编码
                    "picked_qty": pickup_batch.get('picked_qty'),  # 拣配数量
                    "picked_base_qty": pickup_batch.get('picked_base_qty'),  #
                    "picking_document": pickup_batch.get('picking_document'),  # j拣配单号
                    "batch_item": pickup_batch.get('batch_item'),  # j拣配单行号
                    # "planned_delivery_quantity":planned_delivery_quantity ,  #
                    # "POD_qty": pickup_batch.get('POD_qty', 0.0),
                    "packing_date": formatted_time,  # 拣配日期
                    "create_id": user_id,
                    "update_id": user_id,
                    "create_time": formatted_time,
                    "update_time": formatted_time,
                    "picked_parallel_qty": pickup_batch.get('picked_parallel_qty'),
                    "parallel_uom": parallel_uom,
                    "basic_uom": basic_uom,
                    "transaction_uom": transaction_uom,
                    "posting_status": conversion_ret.get("posting_status"),
                    "pod_status": conversion_ret.get("pod_status"),
                    "billing_status": conversion_ret.get("billing_status"),
                    "id": pickup_batch.get('id'),
                    "all_picked_qty": pickup_batch.get('all_picked_qty'),  # 数据库中原本数量-页面修改数量得出的值 。拣配
                    "all_picked_parallel_qty": pickup_batch.get('all_picked_parallel_qty'),  # 数据库中原本数量-页面修改数量得出的值。拣配
                    "all_picked_base_qty": pickup_batch.get('all_picked_base_qty'),  # 数据库中原本数量-页面修改数量得出的值。拣配
                }

                sum_picked_qty += pick_qty

                # if sum_picked_qty > remaining_planned_delivery_quantity:
                #     pickup_batch['message'] = "拣配数量不可大于交货数量，请检查！"
                #     is_fail = True
                #     break

                if packingStatusDict.get((dn_it_alloc_item.get('dn_sn'), dn_it_alloc_item.get('dn_item'),
                                          dn_it_alloc_item.get('mat_code'))) == "C":
                    pickup_batch['message'] = "存在已完全拣配项目，不允许再次确认拣配！"
                    is_fail = True
                    break
                # else:
                #     pickup_batch['message'] = "存在已完全拣配项目，不允许再次确认拣配！"
                index += 1
                alloc_records.append(dn_it_alloc_item)
            # print("alloc_records:", alloc_records)
            if alloc_records and test_run == 1:
                # 交货单库存分配 数据保存  [交货单编号+行号: 对应拣配的批次绑定在一起]
                result, result_data, _ = insert_inventory_alloc(alloc_records, formatted_time,
                                                                planned_delivery_quantity,
                                                                update=True)
                # print('result=====', result)
                # print('result_data=====', result_data)
                # if not result_data:
                #     # 这个方法是单条进行可以这么用
                #     alloc_records[0]['message'] = result_data
                # else:
                #     alloc_records = result_data
                # for item in alloc_records:
                # item['message'] = result_data if not result_data else '校验成功'
                if not result:
                    is_fail = True
                else:
                    is_success = True
                    if not result_data:
                        pickup_batch_dict['message'] = result_data
                    else:
                        res_list.extend(result_data)

            else:
                is_success = True
        # print('pickup_batch_dict', pickup_batch_dict)
        for query_key, pickup_values in pickup_batch_dict.items():
            res_list.extend(list(pickup_values))
        # print("status:", is_fail, is_success)
        if not is_fail and is_success:
            code = 200
            msg = "确认拣配成功" if test_run == 1 else "拣配校验成功"
        elif is_fail and is_success:
            code = 206
            msg = "确认拣配部分成功" if test_run == 1 else "拣配校验失败"
        else:
            code = 406
            msg = "确认拣配全部失败" if test_run == 1 else "拣配校验失败"
        return code, msg, res_list, []
    if delete_pickup_batch_list:
        # 调用时一条一条调用的，只会存在一条数据，[{}]
        db = DbHelper()
        data = delete_pickup_batch_list[0]
        # 修改交货单行项目的已拣配数据 picked_qty，已拣配数据（基本单位） picked_base_qty，已拣配数据（平行单位） picked_parallel_qty，
        # 计算方式：t_dn_item中的拣配数据-t_dn_inventory_alloc中的已修改拣配数量，+0(这个0为文档写明的修改后拣配数量)
        update_sql = '''
            UPDATE `t_dn_item` 
            SET `picked_qty` = `picked_qty` - {},
                `picked_base_qty` = `picked_base_qty` - {},
                `picked_parallel_qty` = `picked_parallel_qty` - {}
            WHERE `dn_sn` = '{}' AND `dn_item` = '{}'
        '''.format(
            data.get("picked_qty"),
            data.get("picked_base_qty"),
            data.get("picked_parallel_qty"),
            data.get("dn_sn"),
            data.get("dn_item")
        )
        up_status = db.exec_sql(update_sql)
        dl_status, case_status = -1, -1
        # print('up_status', up_status, update_sql)
        if up_status > 0:
            # 还需修改状态
            case_sql = f'''
                UPDATE `t_dn_item` 
                SET 
                    `packing_status` = CASE
                        WHEN `picked_qty` = 0 THEN 'A'
                        WHEN `picked_qty` < `planned_delivery_quantity` THEN 'B'
                        WHEN `picked_qty` = `planned_delivery_quantity` THEN 'C'
                        ELSE `packing_status`  -- 注意这里应该是 ELSE packing_status 而不是 billing_status
                    END,
                    `update_id` = {user_id}
                WHERE 
                    `dn_sn` = '{data.get("dn_sn")}' 
                    AND `dn_item` = '{data.get("dn_item")}'
            '''
            case_status = db.exec_sql(case_sql)

            # 5月28日需求 4286 销售退货-校验逻辑完善 前端需要开发了打开注释
            # code, err_msg = update_returned_quantity(db, pickup_batch_list, "delete")
            # if code != 200:
            #     return 400, err_msg, delete_pickup_batch_list, []

            # 进行删除减配单子
            delete_sql = f""" DELETE FROM `t_dn_inventory_alloc` WHERE `dn_sn` = '{data.get("dn_sn")}' AND `dn_item` = '{data.get("dn_item")}' AND `batch_item` = '{data.get("batch_item")}' AND `mat_code` = '{data.get("mat_code")}' """
            dl_status = db.exec_sql(delete_sql)
            # print('dl_status', dl_status, delete_sql)
            # print('case_status', case_status, case_sql)
        if up_status > 0 or dl_status > 0 or case_status > 0:
            code = 200
            msg = "保存成功"
        else:
            code = 400
            msg = "保存失败"
        return code, msg, delete_pickup_batch_list, []


@calc_time
def insert_inventory_alloc(pick_up_list, current_time, planned_delivery_quantity, picking_document_dict={},
                           update=False):
    logger.printInfo("update", update)
    # 每次新建一个db对象,用来进行独立回滚
    db = DbHelper()
    # picked_qty, alloc_bs_qty, alloc_bt_qty = 0, 0, 0
    picked_qty = 0
    picked_base_qty = 0
    picked_parallel_qty = 0
    dn_sn = pick_up_list[0].get('dn_sn')
    dn_item = pick_up_list[0].get('dn_item')
    packing_date = current_time
    for pick_up in pick_up_list:
        picked_qty += float(pick_up.get('picked_qty', 0)) or 0
        picked_base_qty += float(pick_up.get('picked_base_qty', 0)) or 0
        picked_parallel_qty += float(pick_up.get('picked_parallel_qty', 0)) or 0
        packing_date = pick_up.get("packing_date", current_time)
        # alloc_bs_qty += pick_up.get('alloc_qty', 0) or 0

    # if not picked_qty and alloc_bs_qty:
    #     picked_qty = alloc_bs_qty

    is_a = False
    is_b = False
    is_c = False

    # 多个批次是否完全拣配完成
    # qty = planned_delivery_quantity - picked_qty
    # if -0.00001 < qty < 0.00001:
    #     is_c = True
    #     packing_status = 'C'
    #     # 更新 交货单行项目的交货数量=拣配数量之和，并更新 交货单行项目 - 拣配状态=C 全部拣配
    #     # update_dn_item_sql = ("UPDATE `t_dn_item` SET initial_planned_delivery_quantity = planned_delivery_quantity, packing_status = {}, "
    #     if update:
    #         update_dn_item_sql = ("UPDATE `t_dn_item` SET picked_qty={},packing_status = {}, "
    #                               "packing_date = {},picked_base_qty = {},picked_parallel_qty = {} WHERE dn_sn = {} AND dn_item = {};").format(
    #             repr(picked_qty), repr(packing_status), repr(current_time), repr(picked_base_qty), picked_parallel_qty,
    #             repr(dn_sn),
    #             repr(dn_item))
    #     else:
    #         update_dn_item_sql = ("UPDATE `t_dn_item` SET picked_qty=picked_qty+{}, packing_status = {}, "
    #                               "packing_date = {}, picked_base_qty = picked_base_qty+{},picked_parallel_qty = picked_parallel_qty+{} WHERE dn_sn = {} AND dn_item = {};").format(
    #             repr(picked_qty), repr(packing_status), repr(current_time), repr(picked_base_qty), picked_parallel_qty,
    #             repr(dn_sn),
    #             repr(dn_item))
    # else:
    #     is_b = True
    #     packing_status = 'B'
    #     # 按交货单行判断：匹配的批次拣配数量之和"小于等于"交货单行的交货数量，则允许确认拣配，并修改交货单的交货数量="拣配数量之和"
    #     # 需要记录创建交货单时的交货数量 [initial_planned_delivery_quantity]，已保证库管员修改拣配结果时，数量不可大于创建交货单时的交货数量
    #     # update_dn_item_sql = ("UPDATE `t_dn_item` SET initial_planned_delivery_quantity = {}, planned_delivery_quantity = {}, "
    #     #                       "packing_status = {}, packing_date = {} WHERE dn_sn = {} AND dn_item = {};").format(
    #     #     repr(planned_delivery_quantity), repr(pick_qty), repr(packing_status), repr(current_time), repr(dn_sn), repr(dn_item))
    #     if update:
    #         update_dn_item_sql = ("UPDATE `t_dn_item` SET planned_delivery_quantity = {},picked_qty = {}, "
    #                               "packing_status = {}, packing_date = {},picked_base_qty = {} ,picked_parallel_qty = {} WHERE dn_sn = {} AND dn_item = {};").format(
    #             repr(planned_delivery_quantity), repr(picked_qty), repr(packing_status), repr(current_time), repr(picked_base_qty),
    #             picked_parallel_qty, repr(dn_sn),
    #             repr(dn_item))
    #     else:
    #         update_dn_item_sql = ("UPDATE `t_dn_item` SET planned_delivery_quantity = {},picked_qty = picked_qty+{}, "
    #                               "packing_status = {}, packing_date = {},picked_base_qty = picked_base_qty+{} ,picked_parallel_qty = picked_parallel_qty+{} WHERE dn_sn = {} AND dn_item = {};").format(
    #             repr(planned_delivery_quantity), repr(picked_qty), repr(packing_status), repr(current_time), repr(picked_base_qty),
    #             picked_parallel_qty, repr(dn_sn),
    #             repr(dn_item))
    if update:
        # update_dn_item_sql = ("UPDATE `t_dn_item` SET planned_delivery_quantity = {},picked_qty = {}, "
        #                       "packing_date = {},picked_base_qty = {} ,picked_parallel_qty = {} WHERE dn_sn = {} AND dn_item = {};").format(
        #     repr(planned_delivery_quantity), repr(picked_qty), repr(current_time), repr(picked_base_qty),
        #     picked_parallel_qty, repr(dn_sn),
        #     repr(dn_item))
        # 满足update等于TRUE的情况下，数据是一条一条的
        update_dn_item_sql = (
            "UPDATE `t_dn_item` SET `planned_delivery_quantity` = '{}',`picked_qty` = `picked_qty`-{}+{}, "
            "`packing_date` = {},`picked_base_qty` = `picked_base_qty`-{}+{} ,`picked_parallel_qty` = `picked_base_qty` - {} + {} WHERE `dn_sn` = {} AND `dn_item` = {};").format(
            repr(planned_delivery_quantity), repr(pick_up_list[0]['all_picked_qty']),
            repr(pick_up_list[0]['picked_qty']),
            repr(packing_date),
            repr(pick_up_list[0]['all_picked_base_qty']), repr(pick_up_list[0]['picked_base_qty']),
            repr(pick_up_list[0]['all_picked_parallel_qty']), repr(pick_up_list[0]['picked_parallel_qty']), repr(dn_sn),
            repr(dn_item))
    else:
        update_dn_item_sql = ("UPDATE `t_dn_item` SET `planned_delivery_quantity` = {},`picked_qty` = `picked_qty`+{}, "
                              "`packing_date` = {},`picked_base_qty` = `picked_base_qty`+{} ,`picked_parallel_qty` = `picked_parallel_qty`+{} WHERE `dn_sn` = {} AND `dn_item` = {};").format(
            repr(planned_delivery_quantity), repr(picked_qty), repr(packing_date), repr(picked_base_qty),
            picked_parallel_qty, repr(dn_sn),
            repr(dn_item))

    # print(update_dn_item_sql)
    update_status = db.exec_sql(update_dn_item_sql)
    if update_status < 0:
        msg = "交货单行项目 记录更新失败！"
        db.dbRollback()
        return False, msg, {}

    update_dn_item_status_sql = f"""
            UPDATE `t_dn_item` 
            SET `packing_status` = CASE
                WHEN `picked_qty` = 0 THEN 'A'
                WHEN `picked_qty` < `planned_delivery_quantity` THEN 'B'
                WHEN `picked_qty` = `planned_delivery_quantity` THEN 'C'
                ELSE `packing_status`  -- 保留现有状态，如果没有匹配的条件
            END
            where `dn_sn` = '{dn_sn}' and `dn_item` = '{dn_item}'
     """
    update_status = db.exec_sql(update_dn_item_status_sql)
    if update_status < 0:
        msg = "交货单行项目状态更新失败！"
        db.dbRollback()
        return False, msg, {}

    cond = ''
    if dn_sn:
        cond += " AND `dn_sn` = {}".format(repr(dn_sn))
    if dn_item:
        cond += " AND `dn_item` = {}".format(repr(dn_item))
    # 查询 交货单库存分配 t_dn_inventory_alloc
    if update:
        # base_sql = 'SELECT * FROM `t_dn_inventory_alloc` WHERE 1 = 1 '
        # get_dn_it_alloc_sql = base_sql + cond
        # alloc_list = db.query_sql(get_dn_it_alloc_sql)
        # for alloc in alloc_list:
        #     is_f = False
        #     for pick_up in pick_up_list:
        #         if pick_up.get('dn_sn') == alloc.get('dn_sn') and pick_up.get('dn_item') == alloc.get('dn_item') and \
        #                 pick_up.get('batch_sn') == alloc.get('batch_sn'):
        #             pick_up['id'] = alloc.get('id')
        #             pick_up['create_id'] = alloc.get('create_id')
        #             pick_up['create_time'] = alloc.get('create_time')
        #             is_f = True
        #             break

        # if not is_f:
        batch_sn = pick_up_list[0].get('batch_sn')
        picking_document = pick_up_list[0].get('picking_document')
        batch_item = pick_up_list[0].get('batch_item')
        delete_cond = ''
        if dn_sn:
            delete_cond += " AND `dn_sn` = {}".format(repr(dn_sn))
        if dn_item:
            delete_cond += " AND `dn_item` = {}".format(repr(dn_item))
        # if batch_sn:
        #     delete_cond += " AND `batch_sn` = {}".format(repr(batch_sn))
        if picking_document:
            delete_cond += " AND `picking_document` = {}".format(repr(picking_document))
        if batch_item:
            delete_cond += " AND `batch_item` = {}".format(repr(batch_item))

        if delete_cond:
            base_delete_sql = 'DELETE FROM `t_dn_inventory_alloc` WHERE 1 = 1 '
            delete_alloc_sql = base_delete_sql + delete_cond
            # print(delete_alloc_sql)
            delete_status = db.exec_sql(delete_alloc_sql)
            if not delete_status:
                msg = "交货单库存分配 记录删除失败！"
                db.dbRollback()
                return False, msg, {}

    # 一旦有一个行拣配状态设置为B，那么需要检查header中的状态。当前交货单还有其他行为B或A，则更新为B。
    # 如果当前行的状态为C同时其他所有的行也为C则抬头状态也设置为C。
    query_dn_item_sql = 'SELECT `dn_sn`,`dn_item`,`packing_status` FROM `t_dn_item` WHERE 1 = 1 AND `dn_sn` = {}'.format(
        repr(dn_sn))
    dn_item_list = db.query_sql(query_dn_item_sql)
    for each in dn_item_list:
        if each.get('dn_sn') == dn_sn and each.get('dn_item') == dn_item:
            continue
        if each.get('packing_status') == "B":
            is_b = True
        elif each.get('packing_status') == "C":
            is_c = True
        elif each.get('packing_status') == "A":
            is_a = True

    if is_b or is_a:
        packing_status = 'B'
    elif is_c and not is_b and not is_a:
        packing_status = 'C'
    else:
        packing_status = 'A'

    # 由于同一个拣配单号 不同行号 在做拣配更新时会出现事务锁问题

    # update_dn_header_sql = "UPDATE `t_dn_header` SET packing_status = {}, packing_date = {} WHERE dn_sn = {};".format(
    #     repr(packing_status), repr(current_time), repr(dn_sn))
    # print(update_dn_header_sql)
    # update_status = db.exec_sql(update_dn_header_sql)
    # # update_status Affected rows: 0 1 相同的dn_sn sql可能相同
    # if update_status < 0:
    #     msg = "交货单抬头 记录更新失败！"
    #     db.dbRollback()
    #     return False, msg, {}

    allocList = []
    domain_list = []
    # 拣配单号
    # if not picking_document_dict:
    #     picking_document_dict = {}
    # 交货单库存分配 新增记录
    for each in pick_up_list:
        alloc_id = each.get('id')
        dn_sn = each.get('dn_sn')
        dn_item = each.get('dn_item')
        batch_item = each.get('batch_item')
        stor_loc_code = each.get('stor_loc_code')
        batch_sn = each.get('batch_sn')

        alloc_qty = each.get('alloc_qty')
        mat_code = each.get('mat_code') or ''
        alloc_batch_qty = each.get('alloc_batch_qty')
        pick_qty = each.get('picked_qty')
        pod_qty = each.get('POD_qty')

        packing_date = each.get('packing_date')
        create_id = each.get('create_id')
        update_id = each.get('update_id')
        create_time = each.get('create_time')
        update_time = each.get('update_time')
        if update:
            # print("=====================================")
            # print("进入update..........")
            # print("=====================================")
            each["picking_document"] = pick_up_list[0].get('picking_document')
        else:
            print("=====================================")
            print("插入..........................")
            print("dn_sn:", dn_sn)
            print("each:", each)

            if picking_document_dict.get(dn_sn):
                print("无需生成...........")
                print("dn_sn获取到的数据内容:", picking_document_dict.get(dn_sn))
                each["picking_document"] = picking_document_dict.get(dn_sn)
            else:
                print("开始生成..........")
                sales_invoice_sn, domain_list = makePackingNo(domain_list)
                print("生成的拣配单号:", sales_invoice_sn)
                if isinstance(sales_invoice_sn, ResponseData):
                    db.dbRollback()
                    return False, sales_invoice_sn.msg, picking_document_dict
                # sales_invoice_sn, domain_list = makePackingNo(domain_list)
                each["picking_document"] = sales_invoice_sn
                picking_document_dict[dn_sn] = sales_invoice_sn
            # print("=====================================")
        allocList.append(
            DnAlloc(id=alloc_id, picking_document=each["picking_document"], dn_sn=dn_sn, dn_item=dn_item,
                    batch_item=batch_item,
                    mat_code=mat_code,
                    stor_loc_code=stor_loc_code, batch_sn=batch_sn, picked_qty=pick_qty,
                    packing_date=packing_date, picked_parallel_qty=each.get("picked_parallel_qty"),
                    parallel_uom=each.get("parallel_uom"), picked_base_qty=each.get("picked_base_qty"),
                    basic_uom=each.get("basic_uom"), transaction_uom=each.get("transaction_uom"),
                    posting_status=each.get("posting_status"), pod_status=each.get("pod_status"),
                    billing_status=each.get("billing_status"), external_mat_code=each.get("external_mat_code", ""),
                    status="", create_id=create_id,
                    update_id=update_id, actual_plant=each.get("actual_plant"),
                    actual_stor=each.get("actual_stor"),
                    credit_control_code=each.get("credit_control_code"),
                    credit_status=each.get("credit_status"),
                    ).__dict__)
    # print("allocList:", allocList)
    DuplicateSQLKey = ["picked_qty", "batch_sn", "credit_control_code", "credit_status"]
    insert_status = db.batchInsertToDB(tableName="t_dn_inventory_alloc", dataList=allocList,
                                       DuplicateSQLKey=DuplicateSQLKey, ignore=["id"])
    # print('insert_status', insert_status)
    if insert_status < 0:
        msg = "交货单库存分配 新增记录失败！"
        rollback_serial_code(domain_list)
        db.dbRollback()
        return False, msg, picking_document_dict
    db.dbCommit()
    return True, pick_up_list, picking_document_dict


def makePackingNo(domain_list=[]):
    coding_domain = get_coding_domain(None, alloc_object="pick_doc")
    sales_invoice_sn, coding_domain, current_number = get_serial_code(coding_domain)
    if sales_invoice_sn is None and coding_domain is None:
        return ResponseData(ResponseStatusCode.Error, "拣配单号生成失败", data=[]), domain_list
    if coding_domain and current_number:
        domain_list.append((coding_domain, current_number))
    return sales_invoice_sn, domain_list


def get_pick_temp_batch_attr():
    db = DbHelper()
    sql = f""" 
            SELECT
              `tptba`.`batch_attr`
            FROM
              `t_pick_temp_batch_attr` AS `tptba`
    """
    ret = db.query_sql(sql)
    if ret:
        return [i.get("batch_attr") for i in ret]
    else:
        return []


def get_t_ap_property_field():
    db = DbHelper()
    sql = f""" 
            SELECT
              `tapf`.`field_code`,
              `tapf`.`field_name` 
            FROM `t_ap_property_field` AS `tapf` 
    """
    ret = db.query_sql(sql)
    return {i.get("field_code"): i.get("field_name") for i in ret}


def get_table_filed(table_name):
    db = DbHelper()
    # data = db.query_sql("SELECT DATABASE()")
    # database = data[0]["DATABASE()"]
    # print("database",database)
    # 2. 查询表字段信息
    get_sql = f"""
    SELECT 
        `column_name`, 
        `column_comment` 
    FROM 
        `information_schema`.`COLUMNS`
    WHERE 
        `TABLE_SCHEMA` = 'sf_dev_v4_app' 
        AND `table_name` = '{table_name}'
        AND `column_name` NOT IN ('id','create_time','update_time') 
    ORDER BY 
        `ordinal_position`
    """
    logger.printInfo("get_sql", get_sql)
    ret = db.query_sql(get_sql, printSql=True)
    logger.printInfo("ret", ret)
    return {i.get("column_name"): i.get("column_comment") for i in ret}


def get_sd_item_cat_db(dn_sn, dn_item):
    db = DbHelper()
    sql = f""" 
        SELECT
          `tdi`.`sales_item_category`,
          `tasic`.`shipping_returns`
        FROM
          `t_dn_item` AS `tdi`
          LEFT JOIN `t_ao_sd_item_category` as `tasic` on `tdi`.`sales_item_category` = `tasic`.`sales_item_category`
          WHERE `tdi`.`dn_sn` = "{dn_sn}" and `tdi`.`dn_item` = "{dn_item}"
    """
    ret = db.query_sql(sql)
    if ret:
        return ret[0]
    else:
        return {}


@calc_time
def get_sd_item_cat_db_dict(dn_data_list):
    db = DbHelper()
    sql = f""" 
        SELECT
          `tdi`.`dn_sn`,
          `tdi`.`dn_item`,
          `tdi`.`sales_item_category`,
          `tasic`.`shipping_returns`
        FROM
          `t_dn_item` AS `tdi`
          LEFT JOIN `t_ao_sd_item_category` as `tasic` on `tdi`.`sales_item_category` = `tasic`.`sales_item_category`
    """
    where_sql = ""
    if dn_data_list:
        for i in dn_data_list:
            if not where_sql:
                where_sql += f""" where (`tdi`.`dn_sn` = '{i["dn_sn"]}' and `tdi`.`dn_item` = {i["dn_item"]}) """
            else:
                where_sql += f""" or (`tdi`.`dn_sn` = '{i["dn_sn"]}' and `tdi`.`dn_item` = {i["dn_item"]}) """
    if where_sql:
        sql += where_sql
    ret = db.query_sql(sql)
    if ret:
        return {(i.get("dn_sn"), i.get("dn_item")): i for i in ret}
    else:
        return {}
