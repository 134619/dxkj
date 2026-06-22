"""
@File    : OperateSalesDeliveryNote.py
@Author  ：kai.wang@dxdstech.com
@Date    ：2024/12/19 11:40
@explain : 销售交货单
"""
import copy
import json
import logging
import time
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from decimal import Decimal

from CommonDataSource import get_mmd_conv_to_uom
from CustLineOfCreditCalculate import calculate_credit_limit
from DbHelper import DbHelper
from DxSalesDeliveryOrder import (
    convert_material_unit_qty,
    dn_batch_create,
    dn_batch_create_API,
    get_db_os_storage_location,
    merge_property_field,
)
from GenerateSerialNum import generate_serial_num
from GetColumnsInfo import get_columns_info_by_tables
from libenhance import Request, Response
from SystemHelper import EnvKeys, LockAction, SystemHelper
from ToolsMethods import (
    GetDisplay,
    GetEnToZh,
    GetExportData,
    GetLimitData,
    Paginator,
    ResetResponse,
    ResponseData,
    ResponseStatusCode,
    calc_time,
    create_table_alias,
    display_to_entozh,
    filter_data,
    generate_raw_sql,
    sort_data,
)
from ZZEXT_OperateSalesDeliveryNote import edit_additional_fields, get_additional_fields

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s - Line: %(lineno)d')
logger = logging.getLogger(__name__)

db = DbHelper()
sh = SystemHelper()
user_id = sh.getEnv(EnvKeys.user_id)


# 页面控件属性参数初始化
def initialization():
    res = Response()
    table_list = [
        't_dn_header',
        't_dn_item',
        't_dn_additional_property',
        't_documents_business_partner',
        't_dn_additional_property'
    ]
    data = get_columns_info_by_tables(table_list)
    res.set_body(json.dumps({"code": 200, "msg": "查询成功", "data": data}))
    res.commit(True)


# 新的  重写BAPI接口，填其他参数
def singleCreate():
    """
    手工创建-合并创建销售交货单
    """
    res = Response()
    req = Request()
    body = json.loads(req.body())
    data = body.get('data')

    data, code, msg = check_credit_save(data, 0, 0)
    if code == 500:
        res.set_body(json.dumps({"code": code, "msg": msg, "data": ''}))
        return
    # 
    # verify_res, data = customer_check(data)
    # if not verify_res:
    #     for item in data:
    #         if item.get('message') != '':
    #             msg = item.get('message')
    #     res.set_body(json.dumps({"code": 400, "msg": msg, "data": data}))
    #     return
    ret = dn_batch_create_API(0, data,False,False,body)
    status = ret['status']
    msg = ret['data']
    if status == 0:
        res.set_body(json.dumps({"code": 200, "msg": '成功', "data": msg}))
        return
    elif status == 2:
        res.set_body(json.dumps({"code": 500, "msg": "请查看错误详情", "data": msg}))
    else:
        res.set_body(json.dumps({"code": 500, "msg": msg, "data": ''}))
        return

# def singleCreate():
#     """
#     手工创建-创建单一销售交货单
#     """
#     res = Response()
#     req = Request()
#     body = json.loads(req.body())
#     data = body.get('data')
#
#     data, code, msg = check_credit_save(data, 0, 0)
#
#     if code == 500:
#         res.set_body(json.dumps({"code": code, "msg": msg, "data": ''}))
#         return
#
#     verify_res, data = customer_check(data)
#     if not verify_res:
#         for item in data:
#             if item.get('message') != '':
#                 msg = item.get('message')
#         res.set_body(json.dumps({"code": 400, "msg": msg, "data": data}))
#         return
#
#     for item in data:
#         if not item.get("dp_code"):
#             item["dp_code"] = ""
#         if not item.get("dp_addr"):
#             item["dp_addr"] = ""
#         if not item.get("dp_numb"):
#             item["dp_numb"] = ""
#         if not item.get("pod_related"):
#             item["pod_related"] = ""
#         if not item.get("company_code"):
#             item["company_code"] = ""
#         if not item.get("sales_org_code"):
#             item["sales_org_code"] = ""
#         # if not item.get("distribution_channel_code"):
#         #     item["distribution_channel_code"] = ""
#         # if not item.get("prod_group"):
#         #     item["prod_group"] = ""
#
#     import pandas as pd
#
#     df = pd.DataFrame(data)
#     # grouped = df.groupby(['so_sn', 'dp_code', 'dp_addr', 'dp_numb', 'pod_related',
#     #                       'dn_type', 'company_code', 'sales_org_code',
#     #                       'distribution_channel_code', 'prod_group'])
#     grouped = df.groupby(['so_sn', 'dp_code', 'dp_addr', 'dp_numb', 'pod_related',
#                           'dn_type', 'company_code', 'sales_org_code'])
#
#     group_dicts = {key: group.to_dict('records') for key, group in grouped}
#     print("group_dicts>>>", group_dicts)
#     try:
#         data = assemble_header_item(group_dicts, user_id, 1)
#     except ValueError as e:
#         res.set_body(json.dumps({"code": 500, "msg": str(e), "data": []}))
#         return
#
#     # 屏幕增强 --整理客制化字段
#     # data = edit_additional_fields(user_id, body, data)
#
#     ret = dn_batch_create(0, data)
#     # ret = dn_batch_create_API(0, data,False,False,body)
#     status = ret['status']
#     msg = ret['data']
#     if status == 0:
#         res.set_body(json.dumps({"code": 200, "msg": '成功', "data": msg}))
#         return
#     else:
#         res.set_body(json.dumps({"code": 500, "msg": msg, "data": ''}))
#         return


# 旧的批量创建接口
# def batchCreate():
#     """
#     手工创建-合并创建销售交货单
#     """
#     res = Response()
#     req = Request()
#     body = json.loads(req.body())
#     data = body.get('data')
#     cust = body.get('cust')
#     mat = body.get('mat')
#
#     data, code, msg = check_credit_save(data, 0, 0)
#     if code == 500:
#         res.set_body(json.dumps({"code": code, "msg": msg, "data": ''}))
#         return
#
#     verify_res, data = customer_check(data)
#     if not verify_res:
#         for item in data:
#             if item.get('message') != '':
#                 msg = item.get('message')
#         res.set_body(json.dumps({"code": 400, "msg": msg, "data": data}))
#         return
#
#     import pandas as pd
#
#     df = pd.DataFrame(data)
#     # base_group_list = ['company_code', 'distribution_channel_code', 'prod_group', 'sp_code',
#     #                    'dp_code', 'dp_name', 'dp_cont', 'dp_numb']
#     base_group_list = ['company_code', 'distribution_channel_code', 'sp_code',
#                        'dp_code', 'dp_name', 'dp_cont', 'dp_numb']
#     if cust:
#         base_group_list.append('ed_code')
#     if mat:
#         base_group_list.append('mat_code')
#     base_group_list.append('dn_type')
#     grouped = df.groupby(base_group_list)
#     group_dicts = {key: group.to_dict('records') for key, group in grouped}
#
#     try:
#         data = assemble_header_item(group_dicts, user_id, 2)
#     except ValueError as e:
#         res.set_body(json.dumps({"code": 500, "msg": str(e), "data": ''}))
#         return
#
#     # 屏幕增强 --整理客制化字段
#     data = edit_additional_fields(user_id, body, data)
#
#     ret = dn_batch_create(0, data)
#     status = ret['status']
#     msg = ret['data']
#     if status == 0:
#         res.set_body(json.dumps({"code": 200, "msg": '成功', "data": msg}))
#         return
#     else:
#         res.set_body(json.dumps({"code": 500, "msg": msg, "data": ''}))
#         return


# 新的  重写BAPI接口，填其他参数
def batchCreate():
    """
    手工创建-合并创建销售交货单
    """
    res = Response()
    req = Request()
    body = json.loads(req.body())
    data = body.get('data')
    cust = body.get('cust')
    mat = body.get('mat')
    data, code, msg = check_credit_save(data, 0, 0)
    if code == 500:
        res.set_body(json.dumps({"code": code, "msg": msg, "data": ''}))
        return

    # verify_res, data = customer_check(data)
    # if not verify_res:
    #     for item in data:
    #         if item.get('message') != '':
    #             msg = item.get('message')
    #     res.set_body(json.dumps({"code": 400, "msg": msg, "data": data}))
    #     return
    ret = dn_batch_create_API(0, data, cust, mat, body)
    status = ret['status']
    msg = ret['data']
    if status == 0:
        res.set_body(json.dumps({"code": 200, "msg": '成功', "data": msg}))
        return
    elif status == 2:
        res.set_body(json.dumps({"code": 500, "msg": "请查看错误详情", "data": msg}))
    else:
        res.set_body(json.dumps({"code": 500, "msg": msg, "data": ''}))
        return


def check_create_params(data):
    """
    创建参数校验
    """
    for item in data:
        partial_delivery_enabled = item.get('partial_delivery_enabled', 0)
        order_qty = item.get('order_qty', 0.000)
        delivered_quantity = item.get('delivered_quantity', 0.000)
        dn_type = item.get('dn_type', '')
        dn_sn = item.get('dn_sn', '')
        dn_item = item.get('dn_item', 0)

        if not partial_delivery_enabled:
            if delivered_quantity < order_qty:
                item.update({'message': '选择的销售订单不允许分批交货', 'execute_result': '执行失败'})
                return False, '选择的销售订单不允许分批交货'

        re_deliver_qty = item.get('re_deliver_qty', 0)
        if delivered_quantity <= 0:
            item.update({'message': '计划交货数量必须大于0!', 'execute_result': '执行失败'})
            return False, '计划交货数量必须大于0!'
        if delivered_quantity > re_deliver_qty:
            item.update({'message': '计划交货数量不能大于未交货数量', 'execute_result': '执行失败'})
            return False, '计划交货数量不能大于未交货数量'

        try:
            serial_map = generate_serial_num('dn_type', dn_type, db)
        except Exception as e:
            raise ValueError(str(e))

        external_number = serial_map.get('external_number')
        if external_number == 1:
            if not dn_sn:
                return False, f'{dn_type}交货单类型号码段为外部给号，需要输入交货单号'
            if len(dn_sn) > 18:
                return False, '交货单号超过最大长度'
            if not dn_item:
                return False, f'{dn_type}交货单类型号码段为外部给号，需要输入交货单行号'

        else:
            item.update({'dn_sn': serial_map.get('serial_num', '')})

        item.update({'external_number': external_number})

    return True, ''


def assemble_header_item(data, user_id, flag):
    """
    组装交货单抬头和行项目
    """
    dn_order_list = []
    for infos, groups in data.items():
        if flag == 1:
            sales_org_code = infos[7]
            dn_type = infos[5]
            header = {'dn_type': dn_type}
            header.update({'company_code': infos[6]})
            distribution_channel_code = infos[-2]
            prod_group = infos[-1]
            customer_code = groups[0].get('customer_code', '')
            header.update({'customer_code': customer_code})
        elif flag == 2:
            sales_org_code = groups[0].get('sales_org_code', '')
            dn_type = infos[-1]
            header = {'dn_type': dn_type}
            header.update({'company_code': infos[0]})
            distribution_channel_code = infos[1]
            prod_group = infos[2]
            header.update({'customer_code': infos[3]})
        else:
            raise ValueError('参数不正确')

        approval_status, approval_method, cat_of_doc = get_approval_status(dn_type)
        header.update({'approval_status': approval_status})
        header.update({'approval_method': approval_method})
        header.update({'document_category': cat_of_doc})
        header.update({'packing_status': 'A'})
        header.update({'posting_status': 'A'})
        header.update({'pod_status': 'A'})
        header.update({'billing_status': 'A'})
        header.update({'create_id': user_id})
        header.update({'estimated_delivery_date': groups[0].get('estimated_delivery_date', '')})
        header.update({'request_delivery_date': groups[0].get('request_delivery_date', '')})
        header.update({'credit_control_code': groups[0].get('credit_control_code', '')})
        items = []
        header_additional_property = []
        for group in groups:
            item = {}
            header_additional_list = group.get('header_additional_property', [])
            so_sn = group.get('so_sn')
            so_items = group.get('so_items')
            item.update({'so_sn': so_sn})
            item.update({'sales_org_code': sales_org_code})
            item.update({'so_items': so_items})
            item.update({'customer_code': group.get('customer_code')})
            item.update({'dp_code': group.get('dp_code')})
            item.update({'dp_name': group.get('dp_name')})
            item.update({'dp_addr': group.get('dp_addr')})
            item.update({'dp_cont': group.get('dp_cont')})
            item.update({'dp_short_name': group.get('dp_short_name')})
            item.update({'dp_numb': group.get('dp_numb')})
            item.update({'ed_code': group.get('ed_code')})
            item.update({'ed_name': group.get('ed_name')})
            item.update({'partners': group.get('partners')})
            item.update({'ed_short_name': group.get('ed_short_name')})
            item.update({'sp_code': group.get('sp_code')})
            item.update({'sp_name': group.get('sp_name')})
            item.update({'sp_short_name': group.get('sp_short_name')})
            mat_code = group.get('mat_code')
            item.update({'mat_code': mat_code})
            item.update({'ipn': group.get('ipn')})
            plant_code = group.get('plant_code', '')
            item.update({'plant_code': plant_code})
            item.update({'cust_mat_code': group.get('cust_mat_code')})
            planned_delivery_quantity = group.get('planned_delivery_quantity')
            quantity_of_delivery_order_created = group.get('quantity_of_delivery_order_created')
            undelivered_qty = group.get('undelivered_qty')
            item.update({'planned_delivery_quantity': planned_delivery_quantity})  # 计划交货
            item.update({'quantity_of_delivery_order_created': quantity_of_delivery_order_created})  # 已交货
            item.update({'undelivered_qty': undelivered_qty})  # 未交货
            item.update({'available_stock_qty': group.get('available_stock_qty', 0.000)})
            item.update({'sales_item_category': group.get('sales_item_category')})
            item.update({'stor_loc_code': group.get('stor_loc_code')})
            item.update({'picked_qty': group.get('picked_qty', 0.000)})
            item.update({'posted_quantity': group.get('posted_qty', 0.000)})
            item.update({'posted_qty': group.get('posted_qty', 0.000)})
            item.update({'posting_status': 'A'})
            billing_status, pod_status = get_billing_status(so_sn, so_items)
            item.update({'billing_status': billing_status})
            item.update({'pod_related': group.get('pod_related')})
            item.update({'pod_status': pod_status})
            item.update({'POD_qty': group.get('POD_qty')})
            item.update({'movement_type': group.get('movement_type')})
            item.update({'movement_type_it': group.get('movement_type_it')})
            item.update({'special_inventory_status1': group.get('special_inventory_status1')})
            item.update({'wbs_elements': group.get('wbs_elements')})
            item.update({'cost_center': group.get('cost_center')})
            item.update({'profit_center': group.get('profit_center')})
            item.update({'related_to_invoices': group.get('related_to_invoices')})
            basic_uom = group.get('basic_uom')
            item.update({'basic_uom': basic_uom})
            cost_uom = group.get('cost_uom')
            item.update({'cost_uom': cost_uom})
            transaction_uom = group.get('transaction_uom', '')
            item.update({'transaction_uom': transaction_uom})
            item.update({'parallel_uom': group.get('parallel_uom')})
            item.update({'parallel_qty': group.get('parallel_qty')})
            item.update({'credit_status': group.get('credit_status')})
            item.update({'actual_plant': group.get('actual_plant')})
            item.update({'customer_abbreviation': group.get('customer_abbreviation')})
            item.update({'order_qty': group.get('order_qty')})
            item.update({'dn_additional_properties': group.get('dn_additional_properties')})
            item.update({'distribution_channel_code': distribution_channel_code})
            item.update({'prod_group': prod_group})
            item.update({'cust_mat_code_description': group.get('cust_mat_code_description', '')})
            item.update({'related_to_delivery': group.get('related_to_delivery', '')})
            item.update({'wbs_elements': group.get('wbs_elements', '')})
            item.update({'cost_center': group.get('cost_center', '')})
            item.update({'profit_center': group.get('profit_center', '')})
            item.update({'packing_status': group.get('packing_status', '')})
            items.append(item)
            header_additional_property.append(header_additional_list)
        header.update({'items': items, 'header_additional_property': header_additional_property[
            0] if header_additional_property else []})
        dn_order_list.append(header)

    return dn_order_list


def get_approval_status(dn_type):
    """
    获取审批方式，审批状态，单据类型
    """
    sql = f"select `approval_method`, `document_category` from `t_dn_type` where `dn_type`='{dn_type}'"
    res = db.query_sql(sql)

    if not res:
        approval_status, approval_method, cat_of_doc = '', '', ''
    else:
        cat_of_doc = res[0].get('document_category', '')
        approval_method = res[0].get('approval_method')
        if approval_method == 'N':
            approval_status = 'E'
        else:
            approval_status = 'A'

    return approval_status, approval_method, cat_of_doc


def get_billing_status(so_sn, so_items):
    """
    获取开票状态和pod状态
    """
    sql = f"""
    SELECT
        `related_to_invoices`, 
        `related_to_delivery`, 
        `pod_related`
    FROM `t_sales_order_item` 
    WHERE `so_sn`='{so_sn}' and `so_items`={so_items}
    """
    res = db.query_sql(sql)

    if not res:
        billing_status = ''
        pod_status = ''
    else:
        billing_status = res[0].get('billing_status')
        related_to_delivery = res[0].get('related_to_delivery')
        pod_related = res[0].get('pod_related')

        if billing_status == 'C':
            billing_status = 'D'
        else:
            billing_status = 'A'

        if related_to_delivery == 'A' and pod_related == 1:
            pod_status = 'A'
        else:
            pod_status = 'D'

    return billing_status, pod_status


def batchUpdateDN():
    """
    批量修改交货单
    """
    resp = Response()
    req = Request()
    body = json.loads(req.body())
    data = body.get('data')
    if not data:
        resp.set_body(json.dumps({"code": 400, "msg": '参数不能为空', "data": ''}))
        return
    for item in data:
        item['message'] = "操作成功"
        if not item.get('dn_sn') or not item.get('dn_item'):
            resp.set_body(json.dumps({"code": 400, "msg": f'交货单号[dn_sn]和交货单行号[dn_item]必输', "data": ''}))
            return
        if not item.get('planned_delivery_quantity'):
            resp.set_body(json.dumps({"code": 400, "msg": f'计划交货数量必输', "data": ''}))
            return
        if not item.get('dp_code'):
            resp.set_body(json.dumps({"code": 400, "msg": f'送达方必填', "data": ''}))
            return

    items_to_check = [
        (item['dn_sn'], item['dn_item'])
        for item in data
    ]

    is_error = False
    row_map = {}

    if items_to_check:
        placeholders = ', '.join([f"('{item[0]}', {item[1]})" for item in items_to_check])
        sql = f"""
            SELECT
                i.`dn_sn`,
                i.`dn_item`,
                i.`so_sn`,
                i.`so_items`,
                i.`packing_status`,
                i.`picked_qty`,
                i.`planned_delivery_quantity`,
                i.`deleted_mark`,
                i.`mat_code`,
                i.`transaction_uom`,
                i.`parallel_uom`,
                i.`basic_uom`,
                tsoi.`order_qty`,
                tsoi.`plant_code`,
                tsoi.`quantity_of_delivery_order_created`,
                s.`document_modify_enabled_flag`
            FROM `t_dn_item` i
            LEFT JOIN `t_dn_header` h ON i.`dn_sn` = h.`dn_sn`
            LEFT JOIN `t_dn_approval_status` s ON h.`approval_status` = s.`dn_approval_status`
            LEFT JOIN `t_sales_order_item` tsoi ON tsoi.`so_sn` = i.`so_sn` and tsoi.`so_items` = i.`so_items`
            WHERE (i.`dn_sn`, i.`dn_item`) IN ({placeholders})
        """
        rows = db.query_sql(sql)
        row_map = {(r['dn_sn'], r['dn_item']): r for r in rows}
    # 填充缺少的参数
    for item in data:
        db_data = row_map.get((item['dn_sn'], item['dn_item']))
        item["picked_qty"] = db_data.get("picked_qty")
        item["so_sn"] = db_data.get("so_sn")
        item["so_items"] = db_data.get("so_items")
        item["order_qty"] = db_data.get("order_qty")
        item["quantity_of_delivery_order_created"] = db_data.get("quantity_of_delivery_order_created")
        item["before_planned_delivery_quantity"] = db_data.get("planned_delivery_quantity")
        item["undelivered_qty"] = item["order_qty"] - item["quantity_of_delivery_order_created"]
        item["deleted_mark"] = item.get("deleted_mark", 0)
        item["mat_code"] = item.get("mat_code", "")
        item["parallel_uom"] = db_data.get("parallel_uom", "")
        item["transaction_uom"] = db_data.get("transaction_uom", "")
        item["basic_uom"] = db_data.get("basic_uom", "")
        item["plant_code"] = db_data.get("plant_code", "")
        planned_delivery_quantity = item.get("planned_delivery_quantity")
        print("item>>>",item)
        if not item.get("plan_delivery_qty_parallel_uom"):
            code, msg, qty = convert_material_unit_qty(item["mat_code"], item["transaction_uom"],
                                                       item["parallel_uom"], planned_delivery_quantity)
            print("msg1>>>",msg)
            if code == 200:
                item["plan_delivery_qty_parallel_uom"] = qty
            else:
                code, msg, qty = convert_material_unit_qty(item["mat_code"], item["basic_uom"],
                                                           item["parallel_uom"], planned_delivery_quantity)
                print("msg2>>>", msg)
                if code == 200:
                    item["plan_delivery_qty_parallel_uom"] = qty
                else:
                    item["plan_delivery_qty_parallel_uom"] = 0
        if not item.get("plan_delivery_qty_basic_uom"):
            code, msg, qty = convert_material_unit_qty(item["mat_code"], item["transaction_uom"],
                                                       item["basic_uom"], planned_delivery_quantity)
            if code == 200:
                item["plan_delivery_qty_basic_uom"] = qty
            else:
                code, msg, qty = convert_material_unit_qty(item["mat_code"], item["parallel_uom"],
                                                           item["basic_uom"], planned_delivery_quantity)
                if code == 200:
                    item["plan_delivery_qty_basic_uom"] = qty
                else:
                    item["plan_delivery_qty_basic_uom"] = 0

    grouped_items = defaultdict(list)
    for item in data:
        so_sn = item.get("so_sn")
        so_items = item.get("so_items")
        if so_sn and so_items is not None:
            grouped_items[(so_sn, so_items)].append(item)
        else:
            item.update({
                'message': '缺少销售订单号或行号，无法校验交货总量',
                'execute_result': '操作失败'
            })

    allowed_data = []

    for (so_sn, so_items), items in grouped_items.items():
        order_qty = items[0].get('order_qty', 0)

        total_original_created = 0  # quantity_of_delivery_order_created
        total_before_plan = 0  # before_planned_delivery_quantity
        total_after_plan = 0  # after_planned_delivery_quantity
        valid_items = []
        group_has_error = False
        group_message = ''
        print("items>>>",items)
        for item in items:
            dn_sn = item.get('dn_sn')
            dn_item = item.get('dn_item')
            deleted_mark = item.get('deleted_mark', 0)
            after_planned_delivery_quantity = item.get('planned_delivery_quantity', 0)
            quantity_of_delivery_order_created = item.get('quantity_of_delivery_order_created', 0)
            picked_qty = item.get('picked_qty', 0)
            if item.get('stor_loc_code'):
                os_storage_location_dict = get_db_os_storage_location()
                if os_storage_location_dict.get((item.get("plant_code"), item.get("stor_loc_code"))) is None:
                    message = f"""[{item.get("plant_code")}]工厂代码与[{item.get("stor_loc_code")}]库存地点对应关系不存在，请检查"""
                    item.update({
                        'message': message,
                        'execute_result': '操作失败'
                    })
                    group_has_error = True
                    continue

            if dn_sn and dn_item is not None:
                key = (dn_sn, dn_item)
                if key not in row_map:
                    message = '交货单行不存在'
                else:
                    r = row_map[key]
                    if r['document_modify_enabled_flag'] == 0:
                        message = '交货单不可被修改'
                    elif deleted_mark == 1 and r['packing_status'] != 'A':
                        message = f"{dn_sn}交货单{dn_item}行已拣配，不允许执行删除操作！"
                    elif after_planned_delivery_quantity <= 0:
                        message = '计划交货数量必须大于0!'
                    elif after_planned_delivery_quantity < picked_qty:
                        message = '计划交货数量不可小于已拣配数量'
                    else:
                        # 暂时不校验总量，先收集数值
                        total_original_created += quantity_of_delivery_order_created
                        total_before_plan += r['planned_delivery_quantity']
                        total_after_plan += after_planned_delivery_quantity
                        valid_items.append(item)
                        continue

            else:
                message = '缺少交货单号或行号'

            # 如果有行级错误，标记整个分组失败
            if message:
                item.update({
                    'message': message,
                    'execute_result': '操作失败'
                })
                group_has_error = True

        # 如果分组中已有行级错误，跳过总量校验（因为部分已失败）
        if group_has_error:
            continue

        # 总量校验：调整后的累计交货量不能超过订单量
        print("total_original_created>>>", total_original_created)
        print("total_before_plan>>>", total_before_plan)
        print("total_after_plan>>>", total_after_plan)
        print("order_qty>>>", order_qty)
        adjusted_total = total_original_created - total_before_plan + total_after_plan
        if adjusted_total > order_qty:
            # is_error=True
            group_message = f"销售订单 {so_sn} 行 {so_items} 的累计交货数量 ({adjusted_total}) 超过订单数量 ({order_qty})"

        if group_message:
            for item in items:
                item.update({
                    'message': group_message,
                    'execute_result': '操作失败'
                })
            # resp.set_body(json.dumps({"code": 400, "msg": "执行失败，请查看详细信息", "data": items}))
            # return
        else:
            allowed_data.extend(valid_items)
    print("allowed_data>>>", allowed_data)
    if allowed_data:
        allowed_data, code, msg = check_credit_save(allowed_data, 1, 0)
        if code == 500:
            resp.set_body(json.dumps({"code": code, "msg": msg, "data": data}))
            return

        current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        all_dn_item_updates = []
        dn_item_keys = [
            'dn_sn', 'dn_item', 'planned_delivery_quantity'
        ]
        dp_code_set = {item.get('dp_code', '') for item in allowed_data}
        dp_code_placeholder = ', '.join([f"'{dp_code}'" for dp_code in dp_code_set])
        cu_bpc_sql = f"select `customer_code`, `contact_address`, `contact_person`,`contact_number`,`customer_short_name`,`customer_description`,`customer_short_name`,`postal_code` from `t_bpc_customer_basic_data` where `customer_code` in ({dp_code_placeholder})"
        cu_bpc_data = db.query_sql(cu_bpc_sql)
        cu_bpc_map = {item['customer_code']: item for item in cu_bpc_data}
        for item in allowed_data:
            if item.get("dp_code"):
                if not item.get("dp_name"):
                    item["dp_name"] = cu_bpc_map.get(item.get("dp_code"), {}).get("customer_description")
                if not item.get("dp_addr"):
                    item["dp_addr"] = cu_bpc_map.get(item.get("dp_code"), {}).get("contact_address")
                if not item.get("dp_cont"):
                    item["dp_cont"] = cu_bpc_map.get(item.get("dp_code"), {}).get("contact_person")
                if not item.get("dp_numb"):
                    item["dp_numb"] = cu_bpc_map.get(item.get("dp_code"), {}).get("contact_number")
                if not item.get("dp_short_name"):
                    item["dp_short_name"] = cu_bpc_map.get(item.get("dp_code"), {}).get("customer_short_name")
                if not item.get("postal_code"):
                    item["postal_code"] = cu_bpc_map.get(item.get("dp_code"), {}).get("postal_code")
            new_item = {
                'dn_sn': item['dn_sn'],
                'dn_item': item['dn_item'],
                'planned_delivery_quantity': item.get('planned_delivery_quantity', 0)
            }
            if item.get("stor_loc_code"):
                new_item["stor_loc_code"] = item.get("stor_loc_code")
                dn_item_keys.append("stor_loc_code")

            if item.get("plant_code"):
                new_item["plant_code"] = item.get("plant_code")
                dn_item_keys.append("plant_code")

            if item.get("note"):
                new_item["note"] = item.get("note")
                dn_item_keys.append("note")

            if item.get("deleted_mark") != None or item.get("deleted_mark") != "":
                new_item["deleted_mark"] = item.get("deleted_mark")
                dn_item_keys.append("deleted_mark")
            if item.get("plan_delivery_qty_parallel_uom") != None:
                new_item["plan_delivery_qty_parallel_uom"] = item.get("plan_delivery_qty_parallel_uom")
                dn_item_keys.append("plan_delivery_qty_parallel_uom")
            if item.get("plan_delivery_qty_basic_uom") != None:
                new_item["plan_delivery_qty_basic_uom"] = item.get("plan_delivery_qty_basic_uom")
                dn_item_keys.append("plan_delivery_qty_basic_uom")
            all_dn_item_updates.append(new_item)

        if all_dn_item_updates:
            db.batchInsertToDB(
                "t_dn_item",
                all_dn_item_updates,
                user_id=user_id,
                isUpdate=True,
                DuplicateSQLKey=dn_item_keys,
                printSql=True
            )

        partner_list = []
        dn_additional_props = []
        partner_keys = [
            'doc_sn', 'doc_items', 'business_partner_no',
            'business_partner_code', 'business_partner_name',
            'business_partner_addr', 'contact_person', 'contact_number', 'business_partner_short_name'
        ]
        for item in allowed_data:
            dn_sn = item['dn_sn']
            dn_item = item['dn_item']

            query_partner_sql = f"""
                                SELECT `business_partner_type`, `business_partner_no`,`document_category`
                                FROM `t_documents_business_partner`
                                WHERE `doc_sn` = '{dn_sn}'
                                AND `doc_items` = {dn_item}
                                """
            businesses = db.query_sql(query_partner_sql)
            for business in businesses:
                bp_type = business['business_partner_type']
                bp_no = business['business_partner_no']
                document_category = business['document_category']
                partner = {
                    'doc_sn': dn_sn,
                    'doc_items': dn_item,
                    'business_partner_no': bp_no,
                    'document_category': document_category,
                }
                update_flag = False
                if bp_type == 'DP':
                    if item.get('dp_name'):
                        update_flag = True
                        partner["business_partner_name"] = item.get('dp_name', "")
                        partner["update_id"] = item.get('user_id', "")
                        partner_keys.append("business_partner_name")
                        if "update_id" not in partner_keys:
                            partner_keys.append("update_id")

                    if item.get('dp_code'):
                        update_flag = True

                        partner["business_partner_code"] = item.get('dp_code', "")
                        partner["update_id"] = item.get('user_id', "")
                        partner_keys.append("business_partner_code")
                        if "update_id" not in partner_keys:
                            partner_keys.append("update_id")
                    if item.get('dp_addr'):
                        update_flag = True

                        partner["business_partner_addr"] = item.get('dp_addr', "")
                        partner["update_id"] = item.get('user_id', "")
                        partner_keys.append("business_partner_addr")
                        if "update_id" not in partner_keys:
                            partner_keys.append("update_id")
                    if item.get('dp_cont'):
                        update_flag = True

                        partner["contact_person"] = item.get('dp_cont', "")
                        partner["update_id"] = item.get('user_id', "")
                        partner_keys.append("contact_person")
                        if "update_id" not in partner_keys:
                            partner_keys.append("update_id")

                    if item.get('dp_numb'):
                        update_flag = True

                        partner["contact_number"] = item.get('dp_numb', "")
                        partner["update_id"] = item.get('user_id', "")
                        partner_keys.append("contact_number")
                        if "update_id" not in partner_keys:
                            partner_keys.append("update_id")
                    if item.get('dp_short_name'):
                        update_flag = True
                        partner["business_partner_short_name"] = item.get('dp_short_name', "")
                        partner["update_id"] = item.get('user_id', "")
                        partner_keys.append("business_partner_short_name")
                        if "update_id" not in partner_keys:
                            partner_keys.append("update_id")
                    if item.get('postal_code'):
                        update_flag = True
                        partner["postal_code"] = item.get('postal_code', "")
                        partner["update_id"] = item.get('user_id', "")
                        partner_keys.append("postal_code")
                        if "update_id" not in partner_keys:
                            partner_keys.append("update_id")

                elif bp_type == 'EC':
                    if item.get('ed_code'):
                        update_flag = True

                        partner.update({
                            'business_partner_code': item.get('ed_code', ""),
                            'update_id': user_id,
                        })
                        partner_keys.append("business_partner_code")
                        if "update_id" not in partner_keys:
                            partner_keys.append("update_id")

                    if item.get('ed_name'):
                        update_flag = True

                        partner.update({
                            'business_partner_name': item.get('ed_name', ""),
                            'update_id': user_id,

                        })
                        partner_keys.append("business_partner_name")
                        if "update_id" not in partner_keys:
                            partner_keys.append("update_id")

                elif bp_type == 'SP':
                    if item.get('sp_code'):
                        update_flag = True

                        partner.update({
                            'business_partner_code': item.get('sp_code', ""),
                            'update_id': user_id,

                        })
                        partner_keys.append("business_partner_code")
                        if "update_id" not in partner_keys:
                            partner_keys.append("update_id")

                    if item.get('sp_name'):
                        update_flag = True

                        partner.update({
                            'business_partner_name': item.get('sp_name', ""),
                            'update_id': user_id,

                        })
                        partner_keys.append("business_partner_name")
                        if "update_id" not in partner_keys:
                            partner_keys.append("update_id")

                    # if item.get('short_name'):
                    #     update_flag = True
                    #     partner.update({
                    #         'business_partner_short_name': item.get('short_name', ""),
                    #         'update_id': user_id,
                    #     })
                    #     partner_keys.append("business_partner_short_name")
                    #     if "update_id" not in partner_keys:
                    #         partner_keys.append("update_id")

                partner_list.append(partner)
                if update_flag:
                    db.batchInsertToDB(
                        "t_documents_business_partner",
                        [partner],
                        user_id=user_id,
                        isUpdate=True,
                        DuplicateSQLKey=partner_keys,
                        printSql=True
                    )

            dn_additional_properties = item.get('dn_additional_properties') or []
            dn_additional_props.extend(dn_additional_properties)

        # if partner_list:
        #     db.batchInsertToDB(
        #         "t_documents_business_partner",
        #         partner_list,
        #         user_id=user_id,
        #         isUpdate=True,
        #         DuplicateSQLKey=partner_keys,
        #         printSql=True
        #     )

        if dn_additional_props:
            dn_additional_props = merge_property_field(dn_additional_props)
            dn_additional_keys = [
                'dn_sn', 'dn_item', 'field_code', 'field_value',
                'field_value_from', 'field_value_to',
                'field_value_int', 'field_value_int_from', 'field_value_int_to',
                'field_value_date', 'field_value_date_from', 'field_value_date_to',
                'field_value_time', 'field_value_time_from', 'field_value_time_to',
                'field_value_decimal', 'field_value_decimal_from', 'field_value_decimal_to'
            ]
            db.batchInsertToDB(
                't_dn_additional_property',
                dn_additional_props,
                user_id=user_id,
                isUpdate=True,
                DuplicateSQLKey=dn_additional_keys,
                printSql=True
            )

        so_keys = set()
        for item in allowed_data:
            if item.get('so_sn') and item.get('so_items') is not None:
                so_keys.add((item['so_sn'], item['so_items']))

        # if so_keys:
        #     placeholders = ', '.join([f"('{item[0]}', {item[1]})" for item in so_keys])
        #     update_so_sql = f"""
        #         UPDATE `t_sales_order_item` t1
        #         SET `quantity_of_delivery_order_created` = (
        #             SELECT COALESCE(SUM(`planned_delivery_quantity`), 0)
        #             FROM `t_dn_item` t2
        #             WHERE t2.`so_sn` = t1.`so_sn`
        #               AND t2.`so_items` = t1.`so_items`
        #               AND t2.`deleted_mark` = 0
        #         ),
        #         `update_id` = {user_id},
        #         `update_time` = '{current_time_str}'
        #         WHERE (t1.`so_sn`, t1.`so_items`) IN ({placeholders})
        #     """
        #     db.exec_sql(update_so_sql, printSql=True)

        dn_set = set()

        for item in allowed_data:
            dn_sn = item['dn_sn']
            dn_item = item['dn_item']
            so_sn = item['so_sn']
            so_items = item['so_items']
            key = (dn_sn, dn_item)

            original_row = row_map.get(key)
            if not original_row:
                continue

            old_deleted = original_row['deleted_mark']
            new_deleted = item['deleted_mark']
            qty = item.get('planned_delivery_quantity', 0)
            if old_deleted == 0 and new_deleted == 1:
                # 删除
                try:
                    handle_sales_status(db, so_sn, so_items, delivery_qty=qty, operator=-1)
                    item['execute_result'] = '操作成功'

                    dn_set.add(dn_sn)
                except Exception as e:
                    db.dbRollback()
                    logger.error(f"handle_sales_status (delete) failed: {e}")
                    item.update({'message': f"状态处理异常: {str(e)}", 'execute_result': '操作失败'})

            elif old_deleted == 1 and new_deleted == 0:
                # 取消删除
                if qty > item.get('undelivered_qty', 0):
                    db.dbRollback()
                    group_message = f"累计交货数量超过订单数量"
                    item.update({'message': group_message, 'execute_result': '操作失败'})
                    continue
                try:
                    handle_sales_status(db, so_sn, so_items, delivery_qty=qty, operator=1)
                    item['execute_result'] = '操作成功'

                    dn_set.add(dn_sn)
                except Exception as e:
                    db.dbRollback()
                    logger.error(f"handle_sales_status (undelete) failed: {e}")
                    item.update({'message': f"状态处理异常: {str(e)}", 'execute_result': '操作失败'})

            else:
                quantity_of_delivery_order_created = item.get("quantity_of_delivery_order_created")
                before_planned_delivery_quantity = item.get('before_planned_delivery_quantity', 0)
                qty = quantity_of_delivery_order_created - before_planned_delivery_quantity + qty
                # 状态未变（0→0 或 1→1)
                print(">>>>>>quantity_of_delivery_order_created", quantity_of_delivery_order_created)
                print(">>>>>>before_planned_delivery_quantity", before_planned_delivery_quantity)
                print(">>>>>>qty", qty)
                handle_sales_status(db, so_sn, so_items, delivery_qty=qty, operator=0)
                item['execute_result'] = '操作成功'

            for dn_sn in dn_set:
                sync_dn_header_deleted_mark(dn_sn, current_time_str)
    # print("data>>>",data)
    resp.set_body(json.dumps({
        "code": 400 if is_error else 200,
        "msg": "执行失败，请查看详细信息" if is_error else "成功",
        "data": data
    }))
    return


def sync_dn_header_deleted_mark(dn_sn, current_time_str):
    sql_check = f"""
                SELECT 1
                FROM `t_dn_item`
                WHERE `dn_sn` = '{dn_sn}'
                AND `deleted_mark` = 0 LIMIT 1
                """
    has_undeleted = db.query_sql(sql_check)

    new_header_deleted_mark = 0 if has_undeleted else 1

    # 更新 header删除标识
    update_sql = f"""
                 UPDATE `t_dn_header`
                 SET `deleted_mark` = {new_header_deleted_mark},
                     `update_id` = {user_id},
                     `update_time` = '{current_time_str}'
                 WHERE `dn_sn` = '{dn_sn}'
                 """
    db.exec_sql(update_sql)


@ResetResponse(params=['so_sn'])
def getItemsBySoSn(so_sn):
    """
    获取销售订单行项目号
    """
    sql = f"select `so_items` from `t_sales_order_item` where `so_sn`='{so_sn}'"
    items = db.query_sql(sql)

    if items:
        items = [item.get('so_items') for item in items]

    return ResponseData(ResponseStatusCode.Success, '成功', items)


@ResetResponse(params=['so_sn'])
def getDnType(so_sn):
    """
    获取交货单类型默认值
    """
    if not so_sn:
        return ResponseData(ResponseStatusCode.Error, '销售订单号必传', '')

    else:
        alloc_default = {}
        query_sales_sql = f"select `sales_order_type` from `t_sales_order_header` where `so_sn`='{so_sn}'"
        doc_type = db.query_sql(query_sales_sql)
        if doc_type:
            doc_type = doc_type[0]['sales_order_type']
            alloc_sql = f"select * from `t_dn_type_alloc` where `sales_order_type`='{doc_type}'"
            alloc = db.query_sql(alloc_sql)
            if alloc:
                alloc_map = [item for item in alloc if item.get('is_default') == 1]
                if alloc_map:
                    alloc_map = alloc_map[0]
                else:
                    alloc_map = alloc[0]
                alloc_default.update({'dn_type': alloc_map.get('dn_type')})

    return ResponseData(ResponseStatusCode.Success, '成功', alloc_default)


@ResetResponse(params=['so_sn'])
def getRelatedDnType(so_sn):
    """
    交货单下拉
    """
    if not so_sn:
        return ResponseData(ResponseStatusCode.Error, '销售订单号必传', '')
    else:
        alloc = []
        query_sales_sql = f"select `sales_order_type` from `t_sales_order_header` where `so_sn`='{so_sn}'"
        doc_type_data = db.query_sql(query_sales_sql)
        if doc_type_data:
            doc_type = doc_type_data[0]['sales_order_type']
            alloc_sql = f"""
             select distinct t1.`dn_type`, t2.`dn_type_description` from `t_dn_type_alloc` t1 
            left join `t_dn_type` t2 on t1.`dn_type`=t2.`dn_type` where `sales_order_type`='{doc_type}'
            """
            alloc = db.query_sql(alloc_sql)

    return ResponseData(ResponseStatusCode.Success, '成功', alloc)


def singleCreateQuery():
    """
    单一创建查询
    """
    resp = Response()
    req = Request()
    all_data = json.loads(req.body())
    body = all_data.get("data")
    payload = all_data.get("_payload_", {})
    sort_info = payload.get("sort_info", [])
    filter_info = payload.get("filter_info", {})
    so_sn = body.get('so_sn')
    begin_item = body.get('begin_item')
    end_item = body.get('end_item')
    dn_type = body.get('dn_type')

    display = [
        {'field': 'message', 'description': '消息号'},
        {'field': 'dn_sn', 'description': '交货单号'},
        {'field': 'dn_item', 'description': '交货单行号'},
        {'field': 'doc_type', 'description': '销售订单类型'},
        {'field': 'doc_type_desc', 'description': '销售订单类型描述'},
        {'field': 'item_qty', 'description': '订单数量'},
        {'field': 'delivery_qty', 'description': '已交货数量'},
        {'field': 're_deliver_qty', 'description': '未交货数量'},
        {'field': 'delivered_quantity', 'description': '计划交货数量'},
        {'field': 'available_stock_qty', 'description': '可用库存数量'},
        {'field': 'parallel_qty', 'description': '平行数量'},
        {'field': 'parallel_uom', 'description': '平行单位'},
        {'field': 'sales_item_category', 'description': '交货项目类别'},
        {'field': 'packing_status', 'description': '拣配状态'},
        {'field': 'picked_qty', 'description': '已拣配数量'},
        {'field': 'posted_quantity', 'description': '已过账数量'},
        {'field': 'posted_qty_base', 'description': '已过账数量(基本单位)'},
        {'field': 'posted_qty_parallel', 'description': '已过账数量(平行单位)'},
        {'field': 'pod_related', 'description': 'POD标记'},
        {'field': 'POD_qty', 'description': 'POD数量'},
        {'field': 'posted_pod_qty', 'description': '已POD过账数量'},
        {'field': 'posted_pod_qty_base', 'description': '已POD过账数量(基本单位)'},
        {'field': 'posted_pod_qty_parallel', 'description': '已POD过账数量(平行单位)'},
        {'field': 'unposted_pod_qty', 'description': '未POD过账数量'},
        {'field': 'movement_type', 'description': '移动类型'},
        {'field': 'movement_type_it', 'description': 'POD移动类型'},
        {'field': 'special_inventory_status1', 'description': '特殊库存状态1'},
        {'field': 'wbs_elements', 'description': 'WBS元素'},
        {'field': 'cost_center', 'description': '成本中心'},
        {'field': 'profit_center', 'description': '利润中心'},
        {'field': 'related_to_qty', 'description': '开票参考单据'},
        {'field': 'basic_quantity', 'description': '基本数量'},
        {'field': 'basic_uom', 'description': '基本单位'},
        {'field': 'cost_quantity', 'description': '成本数量'},
        {'field': 'cost_uom', 'description': '成本单位'},
        {'field': 'parallel_uom', 'description': '平行单位'},
        {'field': 'parallel_qty', 'description': '平行数量'},
        {'field': 'approval_method', 'description': '审批方式'},
        {'field': 'actual_plant', 'description': '实际出货工厂代码'}
    ]

    if not all([so_sn, begin_item, end_item, dn_type]):
        resp.set_body(json.dumps({"code": 400, "msg": "缺少必填参数", "data": '', "display": display,
                                  "rule": {"filter_info": payload.get("filter_info", {}),
                                           "sort_info": payload.get("sort_info", [])}}))
        return

    if end_item < begin_item:
        resp.set_body(json.dumps({"code": 400, "msg": "行号结束值大于起始值，请检查!", "data": '', "display": display,
                                  "rule": {"filter_info": payload.get("filter_info", {}),
                                           "sort_info": payload.get("sort_info", [])}}))
        return

    def get_query(filed_list):
        query = ""
        for filed in filed_list:
            if body.get(filed):
                if filed == "so_sn":
                    query += " AND `{}`='{}'".format(filed, body.get(filed))
                elif filed == "begin_item":
                    query += " AND `{}` >= {}".format('so_items', body.get(filed))
                elif filed == "end_item":
                    query += " AND `{}` <= {}".format('so_items', body.get(filed))
                else:
                    pass
        return query

    header_field = f"""
            '' as `dn_sn`,
            sh.`company_code`, 
            cpn.`full_name` as `company_name`,
            sh.`sales_org_code`, 
            org.`full_name` as `sales_org_code_name`,
            `distribution_channel_code`, 
            cn.`distribution_channel_name`,
            sh.`prod_group`, 
            pg.`description` as `prod_group_name`,
            dt.`cat_of_doc`,
            sh.`so_sn`,
            sh.`approval_status`,
            dt.`approval_method`,
            CASE 
            WHEN 'N' THEN 'E'
            ELSE 'A'
            END AS `dn_approval_state`,
            CONCAT(CONCAT(sh.`approval_status`, "-"), so_ste.`description` ) AS `approval_state`,
            sh.`customer_code`,
            bpc.`full_name` as `customer_full_name`, 
            bpc.`short_name` as `customer_short_name`,  
            sh.`credit_status`,
            sh.`deleted_mark`,
            0 as `create_id`,
            "" as `create_time`, 
            sh.`credit_control_code`
        """

    header_query_sql = f"""
        select 
            {header_field}
        from 
            `t_sales_order_header` as sh 
            LEFT JOIN `t_mmd_product_group` as pg ON sh.`prod_group` = pg.`prod_group`
            LEFT JOIN `t_os_distribution_channel` as cn using(`distribution_channel_code`)
            LEFT JOIN `t_os_sales_org` as org on sh.`sales_org_code` = org.`sales_org_code`
            LEFT JOIN `t_os_company` as cpn on sh.`company_code` = cpn.`company_code`
            LEFT JOIN `t_so_approval_status` AS so_ste ON sh.`approval_status` = so_ste.`so_approval_status`
            LEFT JOIN `t_dn_type` as dt on dt.`dn_type`='{dn_type}'
            LEFT JOIN `t_bpc_customer_basic_data` as bpc ON sh.`customer_code` = bpc.`customer_code`
        where 
            IFNULL(sh.`deleted_mark`, 0) != 1 
        order by sh.`create_time`
        """

    sql = f"""
        select * from ({header_query_sql}) as t1 where 1=1 and `so_sn`='{so_sn}'
        """

    header_data = db.query_sql(sql)

    res = {}
    if header_data:
        header = header_data[0]
        res['header'] = header

        # 附加属性
        so_query_sql = (
            f"select t1.`id`, t1.`field_code`, t1.`field_value`, t2.`field_name` from `t_so_additional_property` t1 "
            f"LEFT JOIN `t_ap_property_field` t2 on t1.`field_code`=t2.`field_code` "
            f"where t1.`so_sn`='{so_sn}' and t1.`so_items`=0")

        so_res = db.query_sql(so_query_sql)

        group_query_sql = (
            f"select `property_group` from `t_ap_property_group_alloc` where `alloc_type`='dn_type' and `alloc_object`='{dn_type}' and "
            f"`alloc_level`='dn_header' ")
        group_res = db.query_sql(group_query_sql)
        if group_res:
            property_group = group_res[0].get('property_group')
        else:
            property_group = ''

        if property_group:
            field_sql = f"""
               select t1.`id`, t2.`field_code`, '' as `field_value`, t3.`field_name` from `t_ap_property_group_alloc` t1 left join 
               `t_ap_property_field_alloc` t2 on t1.`property_group`=t2.`property_group`
               left join `t_ap_property_field` t3 on t2.`field_code`=t3.`field_code` where t1.`property_group`='{property_group}'
             """
            field_res = db.query_sql(field_sql)
        else:
            field_res = []

        for item in field_res:
            if item.get('field_code') not in [each.get('field_code') for each in so_res]:
                so_res.append(item)

        header.update({'header_additional_property': so_res})

        item_field = f"""
                si.`id`,
                '' as `dn_sn`,
                '' as `dn_item`,
                sh.`doc_type`,
                st.`description` as `doc_type_desc`,
                si.`so_sn`,
                si.`so_items`,
                si.`mat_code`, 
                das.`change_order`, 
                si.`description` as `mat_descr`, 
                '' as `IPN_code`,
                '' as `IPN_desc`, 
                si.`plant_code`, 
                plt.`plant_description` as `plant_name`,
                si.`cust_mat_code`,
                si.`related_to_invoices`,
                si.`cust_mat_code_description`,
                '' as `picked_qty`,
                '' as `posted_quantity`,
                si.`order_qty` as `item_qty`,
                si.`sales_uom`,
                si.`plan_delivery_date`,
                si.`request_delivery_date`,
                si.`delivery_qty`,
                si.`order_qty` - si.`delivery_qty` as `re_deliver_qty`,
                si.`order_qty` - si.`delivery_qty` as `delivered_quantity`,
                si.`sales_item_category`,
                '' as `inventory_location`,
                '' as `packing_date`,
                '' as `posted_qty_base`,
                '' as `posted_qty_parallel`,
                'A' as `posting_status`,
                IF(si.`related_to_invoices` = "C", "D", "A") as `billing_status`,
                si.`pod_related`,
                si.`POD_qty`,
                si.`pod_status`,
                '' as `posted_pod_qty`,
                '' as `posted_pod_qty_base`,
                '' as `posted_pod_qty_parallel`,
                '' as `unposted_pod_qty`,
                si.`movement_type`,
                si.`movement_type_it`,
                si.`special_inventory_status1`,
                si.`wbs_elements`,
                dt.`cat_of_doc`, 
                si.`cost_center`,
                si.`profit_center`,
                si.`related_to_qty`,
                '' as `basic_quantity`,
                mmd.`basic_uom`,
                '' as `cost_quantity`,
                cost.`cost_uom`,
                si.`parallel_uom`,
                si.`parallel_qty`,
                dt.`approval_method`,
                si.`credit_status`,
                0 as `available_stock_qty`,
                cs.`overdelivery_tolerance`,
                cs.`underdelivery_tolerance`,
                cs.`unlimited_tolerance` as `unlimited_tolerance_flag`,
                si.`partial_delivery_enabled`,
                si.`deleted_mark`,
                '' as `actual_plant`
            """

        item_query_sql = f"""
            select 
                {item_field}
            from 
                `t_sales_order_header` as sh 
                LEFT JOIN `t_sales_order_item` as si ON sh.`so_sn` = si.`so_sn` 
                LEFT JOIN `t_so_type` as st ON sh.`doc_type` = st.`doc_type`
                LEFT JOIN `t_dn_approval_status` AS das ON sh.`approval_status` = das.`dn_approval_status`
                LEFT JOIN `t_dn_type` as dt on dt.`dn_type`='{dn_type}'
                LEFT JOIN `t_os_plant` as plt on si.`plant_code` = plt.`plant_code`
                LEFT JOIN (select `mat_code`, `basic_uom` from `t_mmd_material_basic_data`) as mmd on si.`mat_code` = mmd.`mat_code`
                LEFT JOIN (select `mat_code`, `plant_code`, `cost_uom` from `t_mmd_material_cost_data`) as cost on si.`mat_code` = cost.`mat_code` and si.`plant_code` = cost.`plant_code`
                LEFT JOIN `t_customer_sales_data` as cs ON sh.`customer_code` = cs.`customer_code` and sh.`sales_org_code` = cs.`sales_org_code`
            where 
                IFNULL(sh.`deleted_mark`, 0) != 1 
            order by sh.`create_time`
            """

        sql = f"""
            select * from ({item_query_sql}) as t1 where 1=1 {get_query(list(body.keys()))}
            """
        item_data = db.query_sql(sql)

        for item in item_data:
            so_sn = item.get('so_sn')
            so_items = item.get('so_items')
            mat_code = item.get('mat_code')
            delivery_qty = item.get('delivery_qty')
            sales_uom = item.get('sales_uom')
            basic_uom = item.get('basic_uom')
            cost_uom = item.get('cost_uom')
            plant_code = item.get('plant_code')
            item['packing_status'] = query_packing_status(mat_code, plant_code)
            _, basic_qty = get_mmd_conv_to_uom(mat_code, delivery_qty, sales_uom, basic_uom)
            _, cost_quantity = get_mmd_conv_to_uom(mat_code, basic_qty, basic_uom, cost_uom)
            item['basic_quantity'] = basic_qty
            item['cost_quantity'] = cost_quantity

            # 业务伙伴
            query_sql = f"""
                        select 
                bp.`id`,
                bp.`business_partner_no`, 
                bp.`business_partner_type`,
                bpr.`business_partner_type_name`,
                bp.`business_partner_code`,
                bp.`business_partner_name`,
                bp.`business_partner_addr`,
                bp.`short_name`, 
                bp.`contact_person`,
                bp.`contact_number`
                from
                    `t_sales_order_header` as sh
                    LEFT JOIN `t_sales_order_item` si on sh.`so_sn`=si.`so_sn`
                    LEFT JOIN `t_documents_business_partner` as bp ON si.`so_sn` = bp.`doc_sn` and si.`so_items`=bp.`doc_items` 
                    LEFT JOIN `t_business_partner_type` bpr on bp.`business_partner_type`=bpr.`business_partner_type`
                where si.`so_sn`='{so_sn}' and si.`so_items`={so_items};
                """
            partners = db.query_sql(query_sql)

            item.update({'partners': partners})

            # 附加属性
            so_query_sql = (
                f"select t1.`id`, t1.`field_code`, t1.`field_value`, t2.`field_name` from `t_so_additional_property` t1 LEFT JOIN `t_ap_property_field` t2 "
                f"on t1.`field_code`=t2.`field_code` where `so_sn`='{so_sn}' and `so_items`={so_items}")
            so_res = db.query_sql(so_query_sql)

            group_query_sql = (
                f"select `property_group` from `t_ap_property_group_alloc` where `alloc_type`='dn_type' and `alloc_object`='{dn_type}' and "
                f"`alloc_level`='dn_item' ")
            group_res = db.query_sql(group_query_sql)

            if group_res:
                property_group = group_res[0].get('property_group')
            else:
                property_group = ''

            if property_group:
                field_sql = f"""
                   select t1.`id`, t2.`filed_code`, '' as `field_value`, t3.`field_name`  from `t_ap_property_group_alloc` t1 left join
                   `t_ap_property_field_alloc` t2 on t1.`property_group`=t2.`property_group`
                   left join `t_ap_property_field` t3 on t2.`field_code`=t3.`field_code` where t1.`property_group`='{property_group}'
                 """
                field_res = db.query_sql(field_sql)
            else:
                field_res = []

            for field in field_res:
                if field.get('field_code') not in [each.get('field_code') for each in so_res]:
                    so_res.append(field)

            item.update({'dn_additional_properties': so_res})

        res.update({'items': item_data})

        if sort_info:
            res = sort_data(res, sort_info)
        if filter_info:
            res = filter_data(res, filter_info)

        if not payload.get("export_excel"):
            res, page = GetLimitData(res, payload.get("page", {}))
            resp.set_body(json.dumps({"code": 200, "msg": "ok", "data": res, "display": display, "page": page,
                                      "rule": {"filter_info": payload.get("filter_info", {}),
                                               "sort_info": payload.get("sort_info", [])}}))
            resp.commit(True)
        else:
            GetExportData([{"单一创建交货单查询信息汇总": res}], "单一创建交货单查询信息汇总.xlsx",
                          display_to_entozh(display))


def tureSingelCreate():
    """
    单一创建的保存
    """
    res = Response()
    req = Request()
    body = json.loads(req.body())
    data = body.get('data')
    copy_param = deepcopy(data)

    if not data:
        res.set_body(json.dumps({"code": 400, "msg": '创建数据不能为空', "data": ''}))
        return

    header = data.get('header')

    so_sn = header.get('so_sn', '')
    credit_control_code = query_credit_control_code(so_sn)
    header['credit_control_code'] = credit_control_code

    sp_code = header.get('customer_code', '')
    sp_name = header.get('customer_full_name', '')
    sp_short_name = header.get('customer_short_name', '')

    dn_type = header.get('dn_type')
    items = data.get('items')
    merged_data = []
    for item in items:
        item.update({'dn_type': dn_type})
        merged_item = {**header, **item}
        partners = item.get('partners', [])

        max_role_num = max([item.get('business_partner_no', 1) for item in partners])
        for partner in partners:
            if partner['business_partner_type'] == 'DP':
                partner['dp_code'] = partner.get('business_partner_code', '')
                partner['dp_name'] = partner.get('business_partner_name', '')
                partner['dp_addr'] = partner.get('business_partner_addr', '')
                partner['dp_cont'] = partner.get('contact_person', '')
                partner['dp_numb'] = partner.get('contact_number', '')
                partner['dp_short_name'] = partner.get('short_name', '')
            elif partner['business_partner_type'] == 'EC':
                partner['ed_code'] = partner.get('business_partner_code', '')
                partner['ed_name'] = partner.get('business_partner_name', '')
                partner['ed_short_name'] = partner.get('short_name', '')

            merged_item.update(partner)

        partners.append(
            {'business_partner_type': 'SP', 'business_partner_code': sp_code, 'business_partner_name': sp_name,
             'short_name': sp_short_name, 'business_partner_no': max_role_num + 1})

        merged_data.append(merged_item)

    is_pass, msg = check_create_params(merged_data)
    if not is_pass:
        res.set_body(json.dumps({"code": 400, "msg": msg, "data": ''}))
        return

    import pandas as pd

    df = pd.DataFrame(merged_data)
    grouped = df.groupby(['so_sn', 'dp_code', 'dp_addr', 'dp_numb', 'pod_related',
                          'dn_type', 'company_code', 'sales_org_code',
                          'distribution_channel_code', 'prod_group'])

    group_dicts = {key: group.to_dict('records') for key, group in grouped}

    try:
        data = assemble_header_item(group_dicts, user_id, 1)
    except ValueError as e:
        res.set_body(json.dumps({"code": 500, "msg": str(e), "data": []}))
        return

    # 屏幕增强 --整理客制化字段
    data = edit_additional_fields(user_id, body, data)

    req = dn_batch_create(0, data)
    status = req['status']
    msg = req['data']
    if status == 0:
        # 更新部分字段返回
        header = copy_param.get('header')
        current_date = datetime.today()
        current_date_str = current_date.strftime("%Y-%m-%d")
        header.update({'create_id': user_id, 'create_time': current_date_str})
        user_name = get_user_name(user_id)
        header.update({'create_id': user_name})
        items = copy_param.get('items')
        msg_map = {(item.get('so_sn'), item.get('so_items')): item for item in msg}
        for item in items:
            if (item.get('so_sn'), item.get('so_items')) in msg_map:
                item.update(msg_map[item.get('so_sn'), item.get('so_items')])
        res.set_body(json.dumps({"code": 200, "msg": '成功', "data": copy_param}))
        return
    else:
        res.set_body(json.dumps({"code": 500, "msg": msg, "data": []}))
        return


def get_user_name(user_id):
    sql = f"select `name` from `t_system_user` where `id`={user_id}"
    ret = db.query_sql(sql)

    if ret:
        ret = ret[0].get('name')

    return ret


@ResetResponse(params=['key_word'])
def queryDnSnByFuzzy(key_word):
    """
    模糊查询交货订单号
    """
    if not key_word:
        sql = "select `dn_sn` from `t_dn_header` where `dn_sn` <> ''"
    else:
        sql = f"select `dn_sn` from `t_dn_header` where `dn_sn` like '%{key_word}%'"

    res = db.query_sql(sql)

    if res:
        res = [item.get('dn_sn') for item in res]

    return ResponseData(ResponseStatusCode.Success, '成功', res)


def singleUpdateQuery():
    """
    单一维护查询
    """
    resp = Response()
    req = Request()
    all_data = json.loads(req.body())
    body = all_data.get("data")
    payload = all_data.get("_payload_", {})
    sort_info = payload.get("sort_info", [])
    filter_info = payload.get("filter_info", {})
    dn_sn = body.get('dn_sn')

    if not dn_sn:
        resp.set_body(json.dumps({"code": 400, "msg": '交货订单号必传', "data": ''}))
        return

    display = [
        {'field': 'message', 'description': '消息号'},
        {'field': 'dn_sn', 'description': '交货单号'},
        {'field': 'dn_item', 'description': '交货单行号'},
        {'field': 'doc_type', 'description': '销售订单类型'},
        {'field': 'doc_type_desc', 'description': '销售订单类型描述'},
        {'field': 'item_qty', 'description': '订单数量'},
        {'field': 'delivered_qty', 'description': '已交货数量'},
        {'field': 'undelivered_qty', 'description': '未交货数量'},
        {'field': 'delivery_qty', 'description': '计划交货数量'},
        {'field': 'dn_item_cat', 'description': '交货项目类别'},
        {'field': 'packing_status', 'description': '拣配状态'},
        {'field': 'picked_qty', 'description': '已拣配数量'},
        {'field': 'posted_quantity', 'description': '已过账数量'},
        {'field': 'posted_qty_base', 'description': '已过账数量(基本单位)'},
        {'field': 'posted_qty_parallel', 'description': '已过账数量(平行单位)'},
        {'field': 'pod_related', 'description': 'POD标记'},
        {'field': 'POD_qty', 'description': 'POD数量'},
        {'field': 'posted_pod_qty', 'description': '已POD过账数量'},
        {'field': 'posted_pod_qty_base', 'description': '已POD过账数量(基本单位)'},
        {'field': 'posted_pod_qty_parallel', 'description': '已POD过账数量(平行单位)'},
        {'field': 'unposted_pod_qty', 'description': '未POD过账数量'},
        {'field': 'movement_type', 'description': '移动类型'},
        {'field': 'movement_type_it', 'description': 'POD移动类型'},
        {'field': 'special_inventory_status1', 'description': '特殊库存状态1'},
        {'field': 'wbs_elements', 'description': 'WBS元素'},
        {'field': 'cost_center', 'description': '成本中心'},
        {'field': 'profit_center', 'description': '利润中心'},
        {'field': 'related_to_invoices', 'description': '开票参考单据'},
        {'field': 'basic_qty', 'description': '基本数量'},
        {'field': 'basic_uom', 'description': '基本单位'},
        {'field': 'cost_quantity', 'description': '成本数量'},
        {'field': 'cost_uom', 'description': '成本单位'},
        {'field': 'parallel_uom', 'description': '平行单位'},
        {'field': 'parallel_qty', 'description': '平行数量'},
        {'field': 'approval_method', 'description': '审批方式'},
        {'field': 'actual_plant', 'description': '实际出货工厂代码'}
    ]

    def get_query(filed_list):
        query = ""
        for filed in filed_list:
            if body.get(filed):
                if filed == "dn_sn":
                    query += " AND `{}`='{}'".format(filed, body.get(filed))
                else:
                    pass
        return query

    header_field = f"""
            dh.`dn_type`,
            dh.`dn_sn`,
            dh.`company_code`, 
            dh.`credit_control_code`, 
            cpn.`full_name` as `company_name`,
            dh.`sales_org_code`, 
            org.`full_name` as `sales_org_code_name`,
            `distribution_channel_code`, 
            cn.`distribution_channel_name`,
            dh.`prod_group`, 
            pg.`description` as `prod_group_name`,
            dh.`document_category`,
            dh.`approval_status`,
            CONCAT(CONCAT(dh.`approval_status`, "-"), so_ste.`description` ) AS `approval_state`,
            dh.`deleted_mark`,
            dh.`create_id`,
            dh.`create_time`
        """

    header_query_sql = f"""
        select 
            {header_field}
        from 
            `t_dn_header` as dh
            LEFT JOIN `t_mmd_product_group` as pg ON dh.`prod_group` = pg.`prod_group`
            LEFT JOIN `t_os_distribution_channel` as cn using(`distribution_channel_code`)
            LEFT JOIN `t_os_sales_org` as org on dh.`sales_org_code` = org.`sales_org_code`
            LEFT JOIN `t_os_company` as cpn on dh.`company_code` = cpn.`company_code`
            LEFT JOIN `t_so_approval_status` AS so_ste ON dh.`approval_status` = so_ste.`so_approval_status`
        where 
            IFNULL(dh.`deleted_mark`, 0) != 1 
        order by dh.`create_time`
        """

    sql = f"""
        select * from ({header_query_sql}) as t1 where 1=1 and `dn_sn`='{dn_sn}'
        """

    header_data = db.query_sql(sql)

    res = {}
    if header_data:
        header = header_data[0]
        res['header'] = header

        # 附加属性
        so_query_sql = (
            f"select t1.`id`, t1.`field_code`, t1.`field_value`, t2.`field_name` from `t_dn_additional_property` t1 LEFT JOIN "
            f"`t_ap_property_field` t2 on t1.`field_code` = t2.`field_code` "
            f"where `dn_sn`='{dn_sn}' and `dn_item`=0")
        so_res = db.query_sql(so_query_sql)

        header.update({'header_additional_property': so_res})

        item_field = f"""
                MAX(di.`id`)                        AS `id`,
               di.`dn_sn`,
               di.`dn_item`,
               MAX(st.`doc_type`)                  AS `doc_type`,
               MAX(st.`description`)               as `doc_type_desc`,
               MAX(di.`so_sn`)                     AS `so_sn`,
               MAX(di.`so_items`)                  AS `so_items`,
               MAX(di.`mat_code`)                  AS `mat_code`,
               MAX(das.`change_order`)             AS `change_order`,
               MAX(bd.`description`)               as `mat_descr`,
               MAX(di.`ipn`)                       as `IPN_code`,
               MAX(bd.`description`)               as `IPN_desc`,
               MAX(di.`plant_code`)                AS `plant_code`,
               MAX(plt.`plant_description`)        as `plant_name`,
               MAX(di.`cust_mat_code`)             AS `cust_mat_code`,
               MAX(di.`related_to_invoices`)       AS `related_to_invoices`,
               MAX(cm.`cust_mat_code_description`) AS `cust_mat_code_description`,
               MAX(di.`picked_qty`)                AS `picked_qty`,
               MAX(di.`posted_quantity`)           AS `posted_quantity`,
               MAX(si.`order_qty`)                 as `item_qty`,
               MAX(di.`sales_uom`)                 AS `sales_uom`,
               MAX(di.`plan_delivery_date`)        AS `plan_delivery_date`,
               MAX(di.`request_delivery_date`)     AS `request_delivery_date`,
               MAX(di.`delivery_qty`)              AS `delivery_qty`,
               MAX(di.`dn_item_cat`)               AS `dn_item_cat`,
               MAX(di.`stor_loc_code`)             AS `stor_loc_code`,
               MAX(di.`packing_date`)              AS `packing_date`,
               MAX(di.`packing_status`)            AS `packing_status`,
               MAX(di.`posted_qty_base`)           AS `posted_qty_base`,
               MAX(di.`posted_qty_parallel`)       AS `posted_qty_parallel`,
               MAX(di.`posting_status`)            AS `posting_status`,
               MAX(di.`billing_status`)            AS `billing_status`,
               MAX(di.`pod_related`)               AS `pod_related`,
               MAX(di.`POD_qty`)                   AS `POD_qty`,
               MAX(di.`pod_status`)                AS `pod_status`,
               MAX(di.`posted_pod_qty`)            AS `posted_pod_qty`,
               MAX(di.`posted_pod_qty_base`)       AS `posted_pod_qty_base`,
               MAX(di.`posted_pod_qty_parallel`)   AS `posted_pod_qty_parallel`,
               MAX(di.`unposted_pod_qty`)          AS `unposted_pod_qty`,
               MAX(di.`movement_type`)             AS `movement_type`,
               MAX(di.`movement_type_it`)          AS `movement_type_it`,
               MAX(di.`special_inventory_status1`) AS `special_inventory_status1`,
               MAX(di.`wbs_elements`)              AS `wbs_elements`,
               MAX(di.`cost_center`)               AS `cost_center`,
               MAX(di.`profit_center`)             AS `profit_center`,
               MAX(di.`basic_qty`)                 AS `basic_qty`,
               MAX(di.`basic_uom`)                 AS `basic_uom`,
               MAX(di.`cost_quantity`)             AS `cost_quantity`,
               MAX(di.`cost_uom`)                  AS `cost_uom`,
               MAX(di.`parallel_uom`)              AS `parallel_uom`,
               MAX(di.`parallel_qty`)              AS `parallel_qty`,
               MAX(dt.`approval_method`)           AS `approval_method`,
               MAX(di.`credit_status`)             AS `credit_status`,
               MAX(cs.`overdelivery_tolerance`)    AS `overdelivery_tolerance`,
               MAX(cs.`underdelivery_tolerance`)   AS `underdelivery_tolerance`,
               MAX(cs.`unlimited_tolerance`)       AS `unlimited_tolerance`,
               MAX(di.`deleted_mark`)              AS `deleted_mark`,
               MAX(di.`actual_plant`)              AS `actual_plant`
            """

        item_query_sql = f"""
            select 
                {item_field}
            from 
                `t_dn_header` as dh
                LEFT JOIN `t_dn_item` as di ON dh.`dn_sn` = di.`dn_sn` 
                LEFT JOIN `t_dndoc_association` AS da ON ( da.`dn_sn` = dh.`dn_sn` AND da.`dn_item` = di.`dn_item` AND da.`associated_document_type` = 'SO' )
                LEFT JOIN `t_sales_order_header` AS sh ON sh.`so_sn` = da.`associated_document`
                LEFT JOIN `t_mmd_material_basic_data` as bd on di.`mat_code`=bd.`mat_code`
                LEFT JOIN `t_dn_approval_status` AS das ON dh.`approval_status` = das.`dn_approval_status`
                LEFT JOIN `t_cust_mat_master_data` as cm on di.`cust_mat_code`=cm.`cust_mat_code`
                LEFT JOIN `t_dn_type` AS dt ON dt.`dn_type` = dh.`dn_type`
                LEFT JOIN `t_so_type` AS st ON di.`doc_type` = st.`doc_type`
                LEFT JOIN `t_sales_order_item` AS si ON di.`so_sn` = si.`so_sn` and di.`so_items` = si.`so_items`
                LEFT JOIN `t_os_plant` as plt on dh.`plant_code` = plt.`plant_code`
                LEFT JOIN (select `mat_code`, `basic_uom` from `t_mmd_material_basic_data`) as mmd on di.`mat_code` = mmd.`mat_code`
                LEFT JOIN (select `mat_code`, `plant_code`, `cost_uom` from `t_mmd_material_cost_data`) as cost on di.`mat_code` = cost.`mat_code` and di.`plant_code` = cost.`plant_code`
                LEFT JOIN `t_customer_sales_data` as cs ON sh.`customer_code` = cs.`customer_code` and sh.`sales_org_code` = cs.`sales_org_code`
            where 
                IFNULL(dh.`deleted_mark`, 0) != 1 
            group by di.`dn_sn`, di.`dn_item` 
            order by dh.`create_time`
            """

        sql = f"""
            select * from ({item_query_sql}) as t1 where 1=1 {get_query(list(body.keys()))}
            """

        item_data = db.query_sql(sql)

        for item in item_data:
            dn_item = item.get('dn_item')

            so_sn = item.get('so_sn')
            so_items = item.get('so_items')

            # 计算已交货数量和未交货数量
            query_sql = f"""
            SELECT 
               (si.`quantity_of_delivery_order_created` - 
                    COALESCE(SUM(CASE WHEN di.`packing_status` = 'A' THEN di.`delivery_qty` ELSE 0 END), 0)
                ) AS `delivered_qty`,
                si.`order_qty` - (si.`delivery_qty` - 
                    COALESCE(SUM(CASE WHEN di.`packing_status` = 'A' THEN di.`delivery_qty` ELSE 0 END), 0)
                ) AS `undelivered_qty`
            FROM 
                `t_sales_order_item` AS si
            LEFT JOIN 
                `t_dn_item` AS di
                ON si.`so_sn` = di.`so_sn`
                AND si.`so_items` = di.`so_items`
            WHERE 
                di.`dn_sn` = '{dn_sn}'
                AND di.`dn_item` = {dn_item}
                AND si.`so_sn` = '{so_sn}'
                AND si.`so_items` = {so_items};
             """
            ret = db.query_sql(query_sql)
            delivered_qty = ret[0].get('delivered_qty')
            undelivered_qty = ret[0].get('undelivered_qty')

            item.update({'delivered_qty': delivered_qty, 'undelivered_qty': undelivered_qty})

            # 业务伙伴
            query_sql = f"""
                        select 
                bp.`business_partner_no`,
                bp.`business_partner_type`,
                bpr.`business_partner_type_name`,
                bp.`business_partner_code`,
                bp.`business_partner_name`,
                bp.`business_partner_addr`,
                bp.`short_name`, 
                bp.`contact_person`,
                bp.`contact_number`
                from
                    `t_dn_header` dh 
                    LEFT JOIN `t_dn_item` di on dh.`dn_sn`=di.`dn_sn`
                    LEFT JOIN `t_documents_business_partner` as bp ON di.`dn_sn` = bp.`doc_sn` and di.`dn_item`=bp.`doc_items` 
                    LEFT JOIN `t_business_partner_type` as bpr on bp.`business_partner_type`=bpr.`business_partner_type`
                where di.`dn_sn`='{dn_sn}' and di.`dn_item`={dn_item}
                """
            partners = db.query_sql(query_sql)

            item.update({'partners': partners})

            # 附加属性
            so_query_sql = (
                f"select t1.`id`, t1.`field_code`, t1.`field_value`, t2.`field_name` from `t_dn_additional_property` t1 LEFT JOIN `t_ap_property_field` t2 "
                f"on t1.`field_code`=t2.`field_code` where `dn_sn`='{dn_sn}' and `dn_item`={dn_item}")
            so_res = db.query_sql(so_query_sql)

            item.update({'dn_additional_properties': so_res, 'message': ''})

        res.update({'items': item_data})

        if sort_info:
            res = sort_data(res, sort_info)
        if filter_info:
            res = filter_data(res, filter_info)

        # 屏幕增强 --查询客制化字段
        res, display = get_additional_fields(user_id, body, res, display)

        if not payload.get("export_excel"):
            res, page = GetLimitData(res, payload.get("page", {}))
            resp.set_body(json.dumps({"code": 200, "msg": "ok", "data": res, "display": display, "page": page,
                                      "rule": {"filter_info": payload.get("filter_info", {}),
                                               "sort_info": payload.get("sort_info", [])}}))
            resp.commit(True)
        else:
            GetExportData([{"单一维护交货单查询信息汇总": res}], "单一维护交货单查询信息汇总.xlsx",
                          display_to_entozh(display))

    else:
        resp.set_body(json.dumps({"code": 200, "msg": "ok", "data": res, "display": display}))
        return


def singleUpdateSave():
    """
    单一维护保存
    """
    res = Response()
    req = Request()
    body = json.loads(req.body())
    data = body.get('data')

    header = data.get('header', {})
    items = data.get('items', [])
    merged_data = []
    for item in items:
        merged_item = {**header, **item}
        merged_data.append(merged_item)

    for item in merged_data:
        dn_sn = item.get('dn_sn')
        query_status_sql = f"select `approval_status` from `t_dn_header` where `dn_sn`='{dn_sn}'"
        approval_status = db.query_sql(query_status_sql)
        approval_status = approval_status[0].get('approval_status')
        query_pass_sql = f"select `change_order` from `t_dn_approval_status` where `dn_approval_status`='{approval_status}'"
        change_order = db.query_sql(query_pass_sql)
        if change_order[0].get('change_order') == 0:
            item.update({'message': '交货单不可被修改'})

    # 先处理删除逻辑
    deleted_item_list = [item.get('id') for item in merged_data if
                         int(item.get('deleted_mark')) == 1 and item.get('message') != '交货单不可被修改']
    deleted_item_placeholders = ','.join([f"{item}" for item in deleted_item_list])

    data_map = {item['id']: item for item in merged_data}

    if deleted_item_placeholders:
        sql = f"select `id`, `dn_sn`, `dn_item`, `packing_status` from `t_dn_item` where `id` in({deleted_item_placeholders})"
        res = db.query_sql(sql)
        for item in res:
            for key, value in item.items():
                if key == 'packing_status':
                    if value != 'A':
                        item_id = item.get('id')
                        item_map = data_map.get(item_id)
                        item_map.update(
                            {'message': f"{item.get('dn_sn')}交货单{item.get('dn_item')}行已拣配，不允许执行删除操作！"})

        allowed_delete_list = [(item.get('id'), item.get('dn_sn'), item.get('dn_item')) for item in merged_data if
                               item.get('message') != '交货单不可被修改' and '已拣配' not in item.get('message', '')]

        if allowed_delete_list:

            update_item_placeholders = ','.join([f"({item[0]}, 1)" for item in allowed_delete_list])
            update_sql = ("insert into `t_dn_item`(`id`, `deleted_mark`) values{} "
                          "ON DUPLICATE KEY UPDATE "
                          "`id`=values(`id`),"
                          "`deleted_mark`=values(`deleted_mark`)".format(update_item_placeholders))
            db.exec_sql(update_sql)

            for each in allowed_delete_list:
                item_id = each[0]
                dn_sn = each[1]
                dn_item = each[2]
                query_sql = f"select `deleted_mark` from `t_dn_item` where `dn_sn`='{dn_sn}'"
                delete_mark = db.query_sql(query_sql)
                mark_list = [item.get('deleted_mark') for item in delete_mark]
                update_header = True
                for mark in mark_list:
                    if mark == 0:
                        update_header = False
                        break

                if update_header:
                    update_sql = f"update `t_dn_header` set `deleted_mark`=1 where `dn_sn`='{dn_sn}'"
                    db.exec_sql(update_sql)

                sql = f"select `so_sn`, `so_items`, `planned_delivery_quantity` from `t_dn_item` where `dn_sn`='{dn_sn}' and `dn_item`={dn_item}"
                delivery_qty_res = db.query_sql(sql)
                planned_delivery_quantity = delivery_qty_res[0].get('planned_delivery_quantity')
                so_sn = delivery_qty_res[0].get('so_sn')
                so_items = delivery_qty_res[0].get('so_items')

                data_map.get(item_id).update({'message': '操作成功'})

                try:
                    handle_sales_status(db, so_sn, so_items, planned_delivery_quantity * -1)
                except Exception as e:
                    logger.error(e)
                    data_map.get(item_id).update({'message': str(e)})

        res.set_body(json.dumps({"code": 200, "msg": '成功', "data": data}))
        return

    else:
        allowed_data = [item for item in merged_data if item.get('message') != '交货单不可被修改']

        for item in allowed_data:
            item_id = item.get('id')
            planned_delivery_quantity = item.get('planned_delivery_quantity')
            undelivered_qty = item.get('undelivered_qty')
            pod_qty = item.get('POD_qty')

            if planned_delivery_quantity <= 0:
                data_map.get(item_id).update({'message': '计划交货数量必须大于0！'})

            if planned_delivery_quantity > undelivered_qty:
                data_map.get(item_id).update({'message': '本次计划交货数量不可大于未交货数量，请检查！'})

            if planned_delivery_quantity < pod_qty:
                data_map.get(item_id).update({'message': '交货单数量修改小于已确认交付数量，不允许此操作！'})

        # 批量更新逻辑
        partner_list = []
        dn_additional_props = []
        dn_item_list = []
        so_item_list = []

        allowed_data = [item for item in merged_data if
                        item.get('message') != '交货单不可被修改' and '数量' not in item.get('message', '')]
        if allowed_data:
            for item in allowed_data:
                item.update({'message': '操作成功'})
                dn_sn = item.get('dn_sn')
                dn_item = item.get('dn_item')
                dn_additional_properties = item.get('dn_additional_properties')
                header_additional_property = item.get('header_additional_property')
                dn_additional_props.extend(dn_additional_properties)
                dn_additional_props.extend(header_additional_property)
                for add_prop in dn_additional_props:
                    add_prop.update({'dn_sn': dn_sn, 'dn_item': dn_item})

                ipn = item.get('IPN_code', '')
                stor_loc_code = item.get('stor_loc_code', '')
                plant_code = item.get('plant_code', '')
                plan_delivery_date = item.get('plan_delivery_date', '')
                planned_delivery_quantity = item.get('planned_delivery_quantity')

                dn_item_map = {'dn_sn': dn_sn, 'dn_item': dn_item,
                               'planned_delivery_quantity': planned_delivery_quantity,
                               'ipn': ipn, 'stor_loc_code': stor_loc_code, 'plant_code': plant_code,
                               'plan_delivery_date':
                                   plan_delivery_date}
                dn_item_list.append(dn_item_map)

                so_sn = item.get('so_sn')
                so_items = item.get('so_items')
                so_item = {'so_sn': so_sn, 'so_items': so_items}
                so_item_list.append(so_item)

                # 业务伙伴
                businesses = item.get('partners', [])
                for business in businesses:
                    business.update({'doc_sn': dn_sn, 'doc_items': dn_item})
                    partner_list.append(business)

            partner_duplicate_keys = ['doc_sn', 'doc_items', 'business_partner_no', 'business_partner_type',
                                      'business_partner_code', 'business_partner_name',
                                      'business_partner_addr', 'business_partner_short_name', 'contact_person',
                                      'contact_number']
            dn_item_duplicate_keys = ['dn_sn', 'dn_item', 'ipn', 'planned_delivery_quantity', 'stor_loc_code',
                                      'plant_code', 'plan_delivery_date']
            dn_additional_duplicate_keys = ['id', 'dn_sn', 'dn_item', 'field_code', 'field_value']

            if partner_list:
                db.batchInsertToDB("t_documents_business_partner", partner_list, user_id=user_id, isUpdate=True,
                                   DuplicateSQLKey=partner_duplicate_keys)
            if dn_additional_props:
                db.batchInsertToDB('t_dn_additional_property', dn_additional_props, user_id=user_id, isUpdate=True,
                                   DuplicateSQLKey=dn_additional_duplicate_keys)

            # t_dn_item
            if dn_item_list:
                db.batchInsertToDB("t_dn_item", dn_item_list, user_id=user_id, isUpdate=True,
                                   DuplicateSQLKey=dn_item_duplicate_keys)
            # t_sales_order_item
            if so_item_list:
                so_item = [(item.get('so_sn'), item.get('so_items')) for item in so_item_list]
                so_item_placeholders = ",".join([f"('{so_sn}', {so_items})" for so_sn, so_items in so_item])
                update_sql = (
                    f"update `t_sales_order_item` t1 set `quantity_of_delivery_order_created`=(select sum(`planned_delivery_quantity`) from "
                    f"`t_dn_item` t2 where t2.`so_sn`=t1.`so_sn` and t2.`so_items`=t1.`so_items`) where "
                    f"(t1.`so_sn`, t1.`so_items`) in({so_item_placeholders})")
                db.exec_sql(update_sql)

            for item in allowed_data:
                so_sn = item.get('so_sn')
                so_items = item.get('so_items')
                try:
                    handle_sales_status(db, so_sn, so_items)
                except Exception as e:
                    logger.error(e)
                    item.update({'message': str(e)})

        res.set_body(json.dumps({"code": 200, "msg": '成功', "data": merged_data}))
        return


def batchQueryDn():
    """
    批量查询
    """
    res = Response()
    req = Request()
    body = json.loads(req.body())
    param = body.get('_payload_', {})
    prefix_filter = body.get('data', {})
    prefix_filter = convert_filter_field(prefix_filter)
    filter_info = param.get('filter_info', {})
    sort_info = param.get('sort_info', {})
    export_excel = param.get('export_excel')

    exp_columns = ('''
                MAX(di.`id`)                                                                    AS `id`,
               MAX(dh.`dn_type`)                                                               AS `dn_type`,
               MAX(dt.`dn_type_description`)                                                   AS `dn_type_description`,
               di.`dn_sn`,
               di.`dn_item`,
               MAX(sd.`sales_order_type`)                                                      AS `sales_order_type`,
               MAX(st.`sales_order_type_description`)                                          AS `sales_order_type_description`,
               MAX(si.`so_sn`)                                                                 AS `so_sn`,
               MAX(si.`so_items`)                                                              AS `so_items`,
               MAX(das.`document_modify_enabled_flag`)                                         AS `document_modify_enabled_flag`,
               CONCAT(CONCAT(dh.`approval_status`, '-'), das.`dn_approval_status_description`) AS `approval_state`,
               MAX(dh.`company_code`)                                                          AS `company_code`,
               MAX(oc.`company_description`)                                                   as `company_desc`,
               MAX(sd.`sales_org_code`)                                                        AS `sales_org_code`,
               MAX(toso.`sales_organization_description`)                                      AS `sales_organization_description`,
               MAX(sd.`distribution_channel_code`)                                             AS `distribution_channel_code`,
               MAX(dc.`distribution_channel_description`)                                      AS `distribution_channel_description`,
               MAX(sd.`prod_group`)                                                            AS `prod_group`,
               MAX(mpg.`product_group_description`)                                            AS `product_group_description`,
               MAX(dh.`document_category`)                                                     AS `document_category`,
               MAX(dh.`approval_status`)                                                       AS `approval_status`,
               MAX(sp.`business_partner_code`)                                                 as `sp_code`,
               MAX(sp.`business_partner_name`)                                                 as `sp_name`,
               MAX(sp.`business_partner_short_name`)                                           AS `business_partner_short_name`,
               MAX(dp.`business_partner_code`)                                                 as `dp_code`,
               MAX(dp.`business_partner_name`)                                                 as `dp_name`,
               MAX(dp.`business_partner_addr`)                                                 as `dp_addr`,
               MAX(dp.`contact_person`)                                                        as `dp_cont`,
               MAX(dp.`contact_number`)                                                        as `dp_numb`,
               MAX(ed.`business_partner_code`)                                                 as `ed_code`,
               MAX(ed.`business_partner_name`)                                                 as `ed_name`,
               MAX(di.`mat_code`)                                                              AS mat_code,
               MAX(mbd.`mat_description`)                                                      AS `mat_description`,
               MAX(di.`ipn`)                                                                   AS `ipn`,
               MAX(mbd1.`mat_description`)                                                     AS `ipn_desc`,
               MAX(di.`plant_code`)                                                            AS `plant_code`,
               MAX(op.`plant_description`)                                                     AS `plant_description`,
               MAX(di.`cust_mat_code`)                                                         AS `cust_mat_code`,
               MAX(cmmd.`cust_mat_code_description`)                                           AS `cust_mat_code_description`,
               MAX(si.`order_qty`)                                                             AS `order_qty`,
               MAX(si.`sales_uom`)                                                             AS `sales_uom`,
               MAX(dh.`estimated_delivery_date`)                                               AS `estimated_delivery_date`,
               MAX(dh.`request_delivery_date`)                                                 AS `request_delivery_date`,
               MAX(si.`quantity_of_delivery_order_created`)                                    AS `quantity_of_delivery_order_created`,
               MAX(si.`order_qty` - si.`quantity_of_delivery_order_created`)                   as `undelivered_qty`,
               MAX(di.`planned_delivery_quantity`)                                             AS `planned_delivery_quantity`,
               MAX(di.`stor_loc_code`)                                                         AS `stor_loc_code`,
               MAX(dh.`packing_date`)                                                          AS `packing_date`,
               MAX(di.`packing_status`)                                                        AS `packing_status`,
               MAX(di.`posting_status`)                                                        AS `posting_status`,
               MAX(di.`billing_status`)                                                        AS `billing_status`,
               MAX(di.`picked_qty`)                                                            AS `picked_qty`,
               MAX(di.`posted_quantity`)                                                       AS `posted_quantity`,
               MAX(di.`posted_quantity`)                                                       AS `posted_quantity`,
               MAX(di.`posted_qty_base`)                                                       AS `posted_qty_base`,
               MAX(di.`posted_qty_parallel`)                                                   AS `posted_qty_parallel`,
               MAX(di.`pod_related`)                                                           AS `pod_related`,
               MAX(di.`pod_status`)                                                            AS `pod_status`,
               MAX(di.`posted_pod_qty`)                                                        AS `posted_pod_qty`,
               MAX(di.`posted_pod_qty_base`)                                                   AS `posted_pod_qty_base`,
               MAX(di.`posted_pod_qty_parallel`)                                               AS `posted_pod_qty_parallel`,
               MAX(di.`movement_type`)                                                         AS `movement_type`,
               MAX(di.`movement_type_it`)                                                      AS `movement_type_it`,
               MAX(di.`special_inventory_status1`)                                             AS `special_inventory_status1`,
               MAX(di.`wbs_elements`)                                                          AS `wbs_elements`,
               MAX(di.`cost_center`)                                                           AS `cost_center`,
               MAX(di.`profit_center`)                                                         AS `profit_center`,
               MAX(di.`related_to_invoices`)                                                   AS `related_to_invoices`,
               MAX(di.`parallel_uom`)                                                          AS `parallel_uom`,
               MAX(di.`basic_qty`)                                                             AS `basic_qty`,
               MAX(di.`basic_uom`)                                                             AS `basic_uom`,
               MAX(di.`cost_uom`)                                                              AS `cost_uom`,
               MAX(dh.`approval_method`)                                                       AS `approval_method`,
               MAX(di.`credit_status`)                                                         AS `credit_status`,
               MAX(di.`deleted_mark`)                                                          AS `deleted_mark`,
               MAX(di.`lock_flag`)                                                             AS `lock_flag`,
               MAX(di.`actual_plant`)                                                          AS `actual_plant`,
               MAX(di.`sales_item_category`)                                                   AS `sales_item_category`,
               MAX(dh.`create_id`)                                                             AS `create_id`,
               MAX(dh.`create_time`)                                                           AS `create_time`,
               MAX(sd.`customer_order`)                                                        AS `customer_order`
                     ''')

    query_columns = '''
               MAX(dh.`id`)                                                                AS `hid`,
               MAX(u1.`name`)                                                              AS `create_name`
                '''

    if export_excel:
        columns = exp_columns
    else:
        columns = exp_columns.strip() + ',' + query_columns

    query_sql = '''
            SELECT {}
            FROM
                `t_dn_header` AS dh
                LEFT JOIN `t_dn_item` AS di ON dh.`dn_sn` = di.`dn_sn`
                LEFT JOIN `t_mmd_material_basic_data` AS mbd ON mbd.`mat_code` = di.`mat_code`
                LEFT JOIN `t_mmd_material_basic_data` AS mbd1 ON mbd1.`mat_code` = di.`ipn`
                LEFT JOIN `t_dn_approval_status` AS das ON dh.`approval_status` = das.`dn_approval_status`
                LEFT JOIN `t_dn_type` AS dt ON dh.`dn_type` = dt.`dn_type`
                LEFT JOIN `t_documents_business_partner` AS sp ON di.`dn_sn` = sp.`doc_sn` AND sp.`business_partner_type` = 'SP' AND sp.`document_category` = 'SDLV'
                LEFT JOIN `t_documents_business_partner` AS dp ON di.`dn_sn` = dp.`doc_sn` AND dp.`business_partner_type` = 'DP' AND dp.`document_category` = 'SDLV'
                LEFT JOIN `t_documents_business_partner` AS ed ON di.`dn_sn` = ed.`doc_sn` AND di.`dn_item` = ed.`doc_items` AND ed.`business_partner_type` = 'EC' AND ed.`document_category` = 'SDLV'
                LEFT JOIN `t_os_plant` AS op ON di.`plant_code` = op.`plant_code`
                LEFT JOIN `t_system_user` AS u1 ON dh.`create_id` = u1.`id`
                LEFT JOIN `t_so_status_record` AS ss1 ON ( ss1.`field` = 'packing_status' AND di.`packing_status` = ss1.`state_value` )
                LEFT JOIN `t_so_status_record` AS ss2 ON ( ss2.`field` = 'posting_status' AND dh.`posting_status` = ss2.`state_value` )
                LEFT JOIN `t_sales_order_item` AS si on di.`so_sn`=si.`so_sn` AND di.`so_items` = si.`so_items`
                LEFT JOIN `t_sales_order_header` AS sd on sd.`so_sn`=si.`so_sn`
                LEFT JOIN `t_os_sales_org` AS toso ON toso.`sales_org_code` = sd.`sales_org_code`
                LEFT JOIN `t_so_type` AS st on sd.`sales_order_type` = st.`sales_order_type` 
                LEFT JOIN `t_os_company` AS oc on dh.`company_code` = oc.`company_code`
                LEFT JOIN `t_os_distribution_channel` AS dc on sd.`distribution_channel_code` = dc.`distribution_channel_code`
                LEFT JOIN `t_cust_mat_master_data` AS cmmd ON cmmd.`cust_mat_code` = di.`cust_mat_code`
                LEFT JOIN `t_mmd_product_group` AS mpg on mpg.`prod_group` = sd.`prod_group`
            WHERE
                1 = 1
                AND di.`dn_sn` is not NULL
                AND (dh.`auto_mark` IS NULL OR dh.`auto_mark` != '1')
            '''.format(columns)
    # 自动创建标识为"1"的交货单不可查询到
    table_alias = create_table_alias(columns)
    where_sql, sort_sql = generate_raw_sql(prefix_filter, {}, sort_info, table_alias)
    group_sql = " GROUP BY di.`dn_sn` , di.`dn_item` "
    if where_sql and 'WHERE' in where_sql:
        where_sql = where_sql.replace('WHERE', 'AND')

    if not sort_sql:
        sort_sql = ' ORDER BY dh.`create_time` ASC, di.`dn_sn` ASC, di.`dn_item` ASC '
        query_sql += ' ' + where_sql + ' ' + group_sql + sort_sql
    else:
        query_sql += ' ' + where_sql + group_sql
    query_sql = query_sql.replace('    ', ' ')

    display = [
        {"description": "交货单类型", "field": "dn_type"},
        {"description": "交货单类型描述", "field": "dn_type_description"},
        {"description": "交货单号", "field": "dn_sn"},
        {"description": "交货单行", "field": "dn_item"},
        {"description": "销售订单类型", "field": "sales_order_type"},
        {"description": "销售订单类型描述", "field": "sales_order_type_description"},
        {"description": "销售订单号", "field": "so_sn"},
        {"description": "销售订单行号", "field": "so_items"},
        {"description": "客户订单号", "field": "customer_order"},
        {"description": "交货单项目类别", "field": "sales_item_category"},
        {"description": "公司代码", "field": "company_code"},
        {"description": "公司描述", "field": "company_desc"},
        {"description": "销售组织", "field": "sales_org_code"},
        {"description": "销售组织描述", "field": "sales_organization_description"},
        {"description": "分销渠道", "field": "distribution_channel_code"},
        {"description": "分销渠道描述", "field": "distribution_channel_description"},
        {"description": "产品组", "field": "prod_group"},
        {"description": "产品组描述", "field": "product_group_description"},
        {"description": "单据类别", "field": "document_category"},
        {"description": "审批状态", "field": "approval_status"},
        {"description": "客户编码", "field": "sp_code"},
        {"description": "客户名称", "field": "sp_name"},
        {"description": "客户缩写", "field": "business_partner_short_name"},
        {"description": "送达方", "field": "dp_code"},
        {"description": "送达方描述", "field": "dp_name"},
        {"description": "送货地址", "field": "dp_addr"},
        {"description": "送货联系人", "field": "dp_cont"},
        {"description": "送货联系电话", "field": "dp_numb"},
        {"description": "终端客户", "field": "ed_code"},
        {"description": "终端客户描述", "field": "ed_name"},
        {"description": "物料编码", "field": "mat_code"},
        {"description": "物料描述", "field": "mat_description"},
        {"description": "交货工厂代码", "field": "plant_code"},
        {"description": "交货工厂描述", "field": "plant_description"},
        {"description": "客户物料编码", "field": "cust_mat_code"},
        {"description": "客户物料描述", "field": "cust_mat_code_description"},
        {"description": "订单数量", "field": "order_qty"},
        {"description": "销售单位", "field": "sales_uom"},
        {"description": "计划交货日期", "field": "estimated_delivery_date"},
        {"description": "要求交货日期", "field": "request_delivery_date"},
        {"description": "已交货数量", "field": "quantity_of_delivery_order_created"},
        {"description": "未交货数量", "field": "undelivered_qty"},
        {"description": "计划交货数量", "field": "planned_delivery_quantity"},
        {"description": "可用库存数量", "field": "available_stock_qty"},
        {"description": "库存地点", "field": "stor_loc_code"},
        {"description": "拣配日期", "field": "packing_date"},
        {"description": "拣配状态", "field": "packing_status"},
        {"description": "过账状态", "field": "posting_status"},
        {"description": "开票状态", "field": "billing_status"},
        {"description": "已拣配数量", "field": "picked_qty"},
        {"description": "已过账数量", "field": "posted_quantity"},
        {"description": "已过账数量（基本单位）", "field": "posted_qty_base"},
        {"description": "已过账数量（平行单位）", "field": "posted_qty_parallel"},
        {"description": "POD标记", "field": "pod_related"},
        {"description": "POD状态", "field": "pod_status"},
        {"description": "已POD过账数量", "field": "posted_pod_qty"},
        {"description": "已POD过账数量（基本单位）", "field": "posted_pod_qty_base"},
        {"description": "已POD过账数量（平行单位）", "field": "posted_pod_qty_parallel"},
        {"description": "移动类型", "field": "movement_type"},
        {"description": "POD移动类型", "field": "movement_type_it"},
        {"description": "特殊库存状态1", "field": "special_inventory_status1"},
        {"description": "WBS元素", "field": "wbs_elements"},
        {"description": "成本中心", "field": "cost_center"},
        {"description": "利润中心", "field": "profit_center"},
        {"description": "开票参考单据", "field": "related_to_invoices"},
        {"description": "平行单位", "field": "parallel_uom"},
        {"description": "基本数量", "field": "basic_qty"},
        {"description": "基本单位", "field": "basic_uom"},
        {"description": "成本单位", "field": "cost_uom"},
        {"description": "审批方式", "field": "approval_method"},
        {"description": "信用状态", "field": "credit_status"},
        {"description": "删除标记", "field": "deleted_mark"},
        {"description": "锁定标记", "field": "lock_flag"},
        {"description": "创建人", "field": "create_name"},
        {"description": "创建日期", "field": "create_time"}
    ]
    print(query_sql)
    query_data = db.query_sql(query_sql)
    if query_data:
        field_names = [item.get('field') for item in display]
        property_info, property_display, property_info_save = query_additional_property()

        for record in query_data:
            dn_sn = record['dn_sn']
            dn_item = record['dn_item']
            unique_key = str(dn_sn) + '|' + str(dn_item)
            dn_property = property_info.get(unique_key) or {}
            dn_property_save = property_info_save.get(unique_key) or {}
            record["dn_additional_properties"] = []
            if dn_property:
                record.update({key: value.get('field_value') for key, value in dn_property.items()})
                record["dn_additional_properties"] = dn_property_save
                for field_code in dn_property.keys():
                    if field_code not in field_names:
                        field_names.append(field_code)
                        field_display = property_display.get(field_code)
                        display.append(field_display)

            sp_partners = record.get("sp_partner")
            dp_partners = record.get("dp_partner")
            record["sp_partner_list"] = []
            record["dp_partner_list"] = []
            if sp_partners:
                if "|" in sp_partners:
                    sp_partner_list = sp_partners.split('|')
                    record["sp_partner_list"].append({"sp_code": sp_partner_list[0], "sp_name": sp_partner_list[1]})
            if dp_partners:
                if "|" in dp_partners:
                    dp_partner_list = dp_partners.split('|')
                    record["dp_partner_list"].append({"dp_code": dp_partner_list[0], "dp_name": dp_partner_list[1]})

        if sort_info:
            query_data = sort_data(query_data, sort_info)
        if filter_info:
            query_data = filter_data(query_data, filter_info)  # 筛选过滤

    # 屏幕增强 --查询客制化字段
    query_data, display = get_additional_fields(user_id, body, query_data, display)

    if export_excel:
        timestamp = time.time()
        excel_filename = '维护交货单-{}.xlsx'.format(int(timestamp))
        format_data = [{'sheet1': query_data}]
        field_dict = display_to_entozh(display)
        GetExportData(format_data, excel_filename, field_dict)
    else:
        page_size = param.get('page', {}).get('page_size', 0)
        page_num = param.get('page', {}).get('page_num', 1)
        paginator = Paginator(query_data, page_size)
        page_items = paginator.get_page(page_num)
        total_pages = paginator.total_pages
        data_sum = len(query_data)

        if page_items:
            for item in page_items:
                use_ipn = item.get('use_ipn')
                mat_code = item.get('mat_code')
                if use_ipn and mat_code and use_ipn == 'B':
                    ipn_list = get_mat_by_external_code(mat_code)
                    item['ipn_list'] = ipn_list

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


def convert_filter_field(filter_info, fields_mapping=None):
    """页面前端筛选字段名和数据库字段名不一致，转换成数据库字段名"""
    convert_fields = {
        'customer_code': 'sp_code',  # 客户编码
        'dn_order': 'rel_dn_sn',  # 交货单号
        'sale_order': 'associated_document',  # 销售单号
        'create_id': 'create_id',  # 创建者
        'planned_delivery_date': 'plan_delivery_date',  # 计划交货日期
    }
    if fields_mapping:
        convert_fields.update(fields_mapping)
    if filter_info:
        for key, value in convert_fields.items():
            if key in filter_info:
                filter_info[value] = filter_info.pop(key)

    return filter_info


def get_additional_property():
    """交货单 附加属性-t_dn_additional_property """
    filter_sql = '''
                 SELECT dp.`dn_sn`, \
                        dp.`dn_item`, \
                        dp.`field_code`, \
                        pf.`field_name`, \
                        dp.`field_value`
                 FROM `t_dn_additional_property` dp \
                          LEFT JOIN `t_ap_property_field` pf ON dp.`field_code` = pf.`field_code` \
                 '''

    property_display, property_info = {}, {}
    query_data = db.query_sql(filter_sql)
    if query_data:
        for item in query_data:
            dn_sn = item.get('dn_sn')
            dn_item = item.get('dn_item')
            field_code = item.get('field_code') or ''
            field_name = item.get('field_name') or field_code or ''
            field_value = item.get('field_value')
            unique_key = str(dn_sn) + '-' + str(dn_item)
            if unique_key in property_info:
                property_info[unique_key][field_code] = field_value
            else:
                property_info[unique_key] = {field_code: field_value}
            property_display[field_code] = {"description": field_name, "field": field_code}

    return property_info, property_display


def get_mat_by_external_code(mat_code):
    filter_sql = "SELECT * FROM `t_mmd_material_basic_data` WHERE 1 = 1 "
    if mat_code:
        filter_sql += " AND `external_mat_code` = {} ".format(repr(mat_code))
    filter_sql += " AND IFNULL(`deleted_mark`,0) != 1 and IFNULL(`locked_mark`,0) != 1 "

    mat_data = db.query_sql(filter_sql)
    return mat_data


@calc_time
def handle_sales_status(db, so_sn, so_items, delivery_qty=None, operator=1):
    """
    处理销售订单抬头和行项目的交货单创建状态和总体状态的更新
    operator -1,1,0: -1减,1加，0更新
    """
    update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if delivery_qty:
        if operator == 0:
            update_qty_sql = f"""
                         update `t_sales_order_item` set
                         `quantity_of_delivery_order_created` = {delivery_qty},
                         `update_id`={user_id}, `update_time`='{update_time}' where `so_sn`='{so_sn}' and `so_items`={so_items}
                        """
        else:
            delivery_qty = delivery_qty * operator
            update_qty_sql = f"""
             update `t_sales_order_item` set
             `quantity_of_delivery_order_created` = `quantity_of_delivery_order_created` + {delivery_qty},
             `update_id`={user_id}, `update_time`='{update_time}' where `so_sn`='{so_sn}' and `so_items`={so_items}
            """
        db.exec_sql(update_qty_sql)
        print(f"更新销售订单行项目数量sql--{update_qty_sql}")

    query_sql = f"""
     select `quantity_of_delivery_order_created`, `order_qty`, `underdelivery_tolerance`, `related_to_delivery`, `related_to_invoices` from `t_sales_order_item` 
    where `so_sn`='{so_sn}' and `so_items`={so_items}
    """
    data = db.query_sql(query_sql)

    delivery_qty = data[0]['quantity_of_delivery_order_created']
    order_qty = data[0]['order_qty']
    underdelivery_tolerance = data[0]['underdelivery_tolerance']
    related_to_delivery = data[0]['related_to_delivery']
    related_to_invoices = data[0]['related_to_invoices']

    if delivery_qty == 0:
        delivery_status = 'A'
    elif order_qty * (1 - underdelivery_tolerance / 100) > delivery_qty > 0:
        delivery_status = 'B'
    else:
        delivery_status = 'C'

    if related_to_delivery == 'A' or (related_to_delivery == 'B' and related_to_invoices == 'B'):
        if delivery_status == 'A':
            overall_status = 'A'
        else:
            overall_status = 'B'
    elif related_to_delivery == 'B' and related_to_invoices == 'C':
        overall_status = delivery_status
    else:
        raise ValueError("总体状态更新错误，交货单创建失败")

    update_item_sql = f"""
     UPDATE `t_sales_order_item` set `delivery_status`='{delivery_status}', `overall_status`='{overall_status}', `update_id`={user_id},
    `update_time`='{update_time}' where `so_sn`='{so_sn}' and `so_items`={so_items}
    """
    db.exec_sql(update_item_sql)
    print(f"更新销售订单行项目状态sql--{update_item_sql}")

    query_sql = f"""
     select `delivery_status`, `overall_status` from `t_sales_order_item` where `so_sn`='{so_sn}'
    """
    data = db.query_sql(query_sql)

    delivery_status_list = [item.get('delivery_status') for item in data if item.get('delivery_status') != 'D']
    overall_status = [item.get('overall_status') for item in data]

    if set(delivery_status_list) == {'A'}:
        delivery_status = 'A'
    elif set(delivery_status_list) == {'C'}:
        delivery_status = 'C'
    else:
        delivery_status = 'B'

    if set(overall_status) == {'A'}:
        overall_status = 'A'
    elif set(overall_status) == {'C'}:
        overall_status = 'C'
    else:
        overall_status = 'B'

    update_header_sql = f"""
     UPDATE `t_sales_order_header` set `delivery_status`='{delivery_status}', `overall_status`='{overall_status}', 
    `update_id`={user_id}, `update_time`='{update_time}' where `so_sn`='{so_sn}'
    """
    db.exec_sql(update_header_sql)
    print(f"更新销售订单抬头状态sql--{update_header_sql}")

    return


@calc_time
@ResetResponse(params=["lock_data"])
def addLockForSalesDN(lock_data):
    """
    交货单加锁
    """
    sh = SystemHelper()
    dn_header = []
    dn_items = []
    header_set = set()

    batch = True
    # 区分维护和单一维护数据结构的不同
    if isinstance(lock_data, dict):
        dn_sn = lock_data.get('dn_sn')
        sql = f"""
         select * from `t_dn_item` where `dn_sn`='{dn_sn}'
        """
        data = db.query_sql(sql)
        batch = False
    else:
        data = lock_data

    if not data:
        return ResponseData(ResponseStatusCode.Success, "没有可加锁的数据", lock_data)

    for dn in data:
        dn.update({'execute_result': ""})
        dn.pop('user_name', '')
        dn.pop('uid', 0)
        dn_sn = dn.get('dn_sn')
        dn_item = dn.get('dn_item')
        if not dn_sn or not dn_item:
            continue

        dn_header_map = {'table_name': 't_dn_header', 'description': '交货单抬头'}
        dn_item_map = {'table_name': 't_dn_item', 'description': '交货单行项目'}

        if dn_sn not in header_set:
            header_set.add(dn_sn)
            dn_header_map.update({'key': dn_sn})
            dn_header.append(dn_header_map)

        dn_item_map.update({'key': dn_sn + str(dn_item)})
        dn_items.append(dn_item_map)

    dn_header.extend(dn_items)

    logger.info(f"加锁数据是---{dn_header}")

    ret = sh.doLock(LockAction.lock, lockData=dn_header)
    logger.info(f"加锁返回--{ret}")
    if ret:
        if ret.get("status") == 200:
            return ResponseData(ResponseStatusCode.Success, "加锁成功", lock_data)
        else:
            if batch:
                import pandas as pd
                detail_df = pd.DataFrame(ret.get("detail", []))
                logging.info(f'detail_df-----{detail_df}')
                data_df = pd.DataFrame(lock_data)
                logging.info(f'data_df-----{data_df}')
                merged_df = data_df.merge(detail_df, left_on="dn_sn", right_on="key", how="left")
                logger.info(f'merged_df-----{merged_df}')
                merged_df["message"] = merged_df["user_name"].apply(
                    lambda x: f"数据已被{x}锁定" if pd.notna(x) else None)
                merged_df = merged_df.fillna('')
                ret = merged_df.to_dict(orient="records")
                return ResponseData(ResponseStatusCode.LOCKED, '存在错误，详情请查看表格明细', ret)
            return ResponseData(ResponseStatusCode.LOCKED,
                                f""" 当前数据正在被用户{ret["detail"][0]["user_name"]} 处理中""", lock_data)
    else:
        return ResponseData(ResponseStatusCode.Error, "锁操作失败", lock_data)



def addLockForSalesDNV1(lock_data):
    """
    业务逻辑交货单加锁
    返回：(is_success: bool, handle_data: list/dict)
    自动给每条数据赋值 current_locked / message
    """
    sh = SystemHelper()
    dn_header = []
    dn_items = []
    header_set = set()

    batch = True
    if isinstance(lock_data, dict):
        dn_sn = lock_data.get('dn_sn')
        sql = f"""
         select * from `t_dn_item` where `dn_sn`='{dn_sn}'
        """
        data = db.query_sql(sql)
        batch = False
    else:
        data = lock_data

    if not data:
        if isinstance(lock_data, dict):
            lock_data["current_locked"] = 1
            lock_data["message"] = ""
        else:
            for item in lock_data:
                item["current_locked"] = 1
                item["message"] = ""
        return True, lock_data

    for dn in data:
        dn.update({'execute_result': ""})
        dn.pop('user_name', '')
        dn.pop('uid', 0)
        dn_sn = dn.get('dn_sn')
        dn_item = dn.get('dn_item')
        if not dn_sn or not dn_item:
            continue

        dn_header_map = {'table_name': 't_dn_header', 'description': '交货单抬头'}
        dn_item_map = {'table_name': 't_dn_item', 'description': '交货单行项目'}

        if dn_sn not in header_set:
            header_set.add(dn_sn)
            dn_header_map.update({'key': dn_sn})
            dn_header.append(dn_header_map)

        dn_item_map.update({'key': dn_sn + str(dn_item)})
        dn_items.append(dn_item_map)

    dn_header.extend(dn_items)
    logger.info(f"加锁数据是---{dn_header}")

    ret = sh.doLock(LockAction.lock, lockData=dn_header)
    logger.info(f"加锁返回--{ret}")

    # 默认全部置为可编辑
    if isinstance(lock_data, dict):
        lock_data["current_locked"] = 1
        lock_data["message"] = ""
    else:
        for item in lock_data:
            item["current_locked"] = 1
            item["message"] = ""

    if not ret:
        # 锁接口无返回
        if isinstance(lock_data, dict):
            lock_data["current_locked"] = 0
            lock_data["message"] = "锁操作失败"
        else:
            for item in lock_data:
                item["current_locked"] = 0
                item["message"] = "锁操作失败"
        return False, lock_data

    if ret.get("status") == 200:
        return True, lock_data

    # 有部分被锁定
    detail_dict = {d["key"]: d for d in ret.get("detail", [])}

    if batch:
        import pandas as pd
        data_df = pd.DataFrame(lock_data)

        def row_lock_set(row):
            key = row.get("dn_sn", "")
            lock_info = detail_dict.get(key)
            if not lock_info:
                row["current_locked"] = 1
                row["message"] = ""
                return row

            uname = lock_info.get("user_name", "")
            # 自己锁=1，别人锁=0
            if uname == row.get("user_name", ""):
                row["current_locked"] = 1
                row["message"] = ""
            else:
                row["current_locked"] = 0
                row["message"] = f"数据已被{uname}锁定"
            return row

        data_df = data_df.apply(row_lock_set, axis=1)
        handle_data = data_df.to_dict(orient="records")
        # 判断是否全部成功
        all_ok = all(item.get("current_locked") == 1 for item in handle_data)
        return all_ok, handle_data
    else:
        # 单条数据
        detail_list = ret.get("detail", [])
        if detail_list:
            uname = detail_list[0].get("user_name", "")
            if uname == lock_data.get("user_name", ""):
                lock_data["current_locked"] = 1
                lock_data["message"] = ""
                return True, lock_data
            else:
                lock_data["current_locked"] = 0
                lock_data["message"] = f"当前数据正在被用户{uname}处理中"
                return False, lock_data
        return True, lock_data


@calc_time
@ResetResponse(params=["unlock_data"])
def releaseLockForSalesDN(unlock_data):
    """
    交货单释放锁
    """
    sh = SystemHelper()
    dn_header = []
    dn_items = []
    header_set = set()

    # 区分维护和单一维护数据结构的不同
    if isinstance(unlock_data, dict):
        dn_sn = unlock_data.get('dn_sn')
        sql = f"""
         select * from `t_dn_item` where `dn_sn`='{dn_sn}'
        """
        data = db.query_sql(sql)
    else:
        data = unlock_data

    if not data:
        return ResponseData(ResponseStatusCode.Error, "没有可释放锁的数据", unlock_data)

    for dn in data:
        dn_sn = dn.get('dn_sn')
        dn_item = dn.get('dn_item')
        if not dn_sn or not dn_item:
            continue

        dn_header_map = {'table_name': 't_dn_header', 'description': '交货单抬头'}
        dn_item_map = {'table_name': 't_dn_item', 'description': '交货单行项目'}

        if dn_sn not in header_set:
            header_set.add(dn_sn)
            dn_header_map.update({'key': dn_sn})
            dn_header.append(dn_header_map)

        dn_item_map.update({'key': dn_sn + str(dn_item)})
        dn_items.append(dn_item_map)

    dn_header.extend(dn_items)

    ret = sh.doLock(LockAction.unlock, lockData=dn_header)
    logger.info(f"释放锁返回--{ret}")
    if ret:
        if ret.get("status") == 200:
            return ResponseData(ResponseStatusCode.Success, "释放锁成功", unlock_data)
        else:
            return ResponseData(ResponseStatusCode.LOCKED,
                                f""" 当前数据正在被用户{ret["detail"][0]["user_name"]} 处理中""", unlock_data)
    else:
        return ResponseData(ResponseStatusCode.Error, "锁操作失败", unlock_data)


def add_screen_control(data, dn_type_name='dn_type'):
    """
    添加表单数据屏幕格式-只抛出是否必填
    """
    dn_types = list(set([item[dn_type_name] for item in data if item[dn_type_name]]))
    if dn_types:
        dn_types_placeholder = ', '.join([f"'{dn}'" for dn in dn_types])
        screen_type_sql = f"""
         select `dn_type`, `screen_type` from `t_dn_type` where `dn_type` in({dn_types_placeholder}) and `screen_type` != ''
        """
        screen_data = db.query_sql(screen_type_sql)

        if not screen_data:
            return data

        type_screen_map = {screen['dn_type']: screen['screen_type'] for screen in screen_data}
        screen_type_set = set(type_screen_map.values())
        screen_type_placeholder = ', '.join([f"'{screen_type}'" for screen_type in screen_type_set])

        # 根据产品设计代码写死-[屏幕配置表里销售交货单的业务类型写死为SDLV]
        field_sql = f"""
         select `screen_type`, `field_name`, `required` from `t_screen_control_configuration` where `business_type`='SDLV' and `screen_type` in ({screen_type_placeholder})
        """
        field_data = db.query_sql(field_sql)

        for dn_type, screen_type in type_screen_map.items():
            fields = []
            for field in field_data:
                if field['screen_type'] == screen_type:
                    fields.append(field)

            type_screen_map.update({dn_type: fields})

        for item in data:
            dn_type = item[dn_type_name]
            screen = type_screen_map.get(dn_type)
            item['screen'] = screen

    return data


def customer_check(data):
    """
    客户编码校验
    """
    is_pass = True

    customer_code_set = {item.get('sp_code', '') for item in data}
    dp_code_set = {item.get('dp_code', '') for item in data}
    customer_code_placeholder = ', '.join([f"'{customer_code}'" for customer_code in customer_code_set])
    dp_code_placeholder = ', '.join([f"'{dp_code}'" for dp_code in dp_code_set])

    customer_sales_org_set = {(item.get('sp_code', ''), item.get('sales_org_code', '')) for item in data}
    customer_sales_org_placeholder = ",".join(
        [f"('{customer}', '{sales}')" for customer, sales in customer_sales_org_set])

    dp_sales_org_set = {(item.get('dp_code', ''), item.get('sales_org_code', '')) for item in data}
    dp_sales_org_placeholder = ",".join([f"('{dp}', '{sales}')" for dp, sales in dp_sales_org_set])

    cu_bpc_sql = f"select `customer_code`, `shipping_freeze_flag`, `deleted_mark` from `t_bpc_customer_basic_data` where `customer_code` in ({customer_code_placeholder})"
    cu_bpc_data = db.query_sql(cu_bpc_sql)
    cu_bpc_map = {item['customer_code']: item for item in cu_bpc_data}

    dp_bpc_sql = f"select `customer_code`, `shipping_freeze_flag`, `deleted_mark` from `t_bpc_customer_basic_data` where `customer_code` in ({dp_code_placeholder})"
    dp_bpc_data = db.query_sql(dp_bpc_sql)
    dp_bpc_map = {item['customer_code']: item for item in dp_bpc_data}

    cu_sales_sql = f"select `customer_code`, `sales_org_code`, `shipping_freeze_flag` from `t_customer_sales_data` where (`customer_code`, `sales_org_code`) in ({customer_sales_org_placeholder})"
    cu_sales_data = db.query_sql(cu_sales_sql)
    cu_sales_map = {(item['customer_code'], item['sales_org_code']): item for item in cu_sales_data}

    dp_sales_sql = f"select `customer_code`, `sales_org_code`, `shipping_freeze_flag` from `t_customer_sales_data` where (`customer_code`, `sales_org_code`) in ({dp_sales_org_placeholder})"
    dp_sales_data = db.query_sql(dp_sales_sql)
    dp_sales_map = {(item['customer_code'], item['sales_org_code']): item for item in dp_sales_data}

    for item in data:
        customer_code = item.get('sp_code', '')
        dp_code = item.get('dp_code', '')
        sales_org_code = item.get('sales_org_code', '')

        if cu_bpc_map.get(customer_code, {}).get('shipping_freeze_flag') == '1' or cu_sales_map.get(
                (customer_code, sales_org_code), {}).get('shipping_freeze_flag') == '1':
            item.update(
                {'message': f'{customer_code}客户已打发货冻结标记, 不可创建交货单', 'execute_result': '操作失败'})
            is_pass = False
            continue

        if dp_bpc_map.get(dp_code, {}).get('shipping_freeze_flag') == '1' or dp_sales_map.get((dp_code, sales_org_code),
                                                                                              {}).get(
            'shipping_freeze_flag') == '1':
            item.update({'message': f'{dp_code}客户已打发货冻结标记, 不可创建交货单', 'execute_result': '操作失败'})
            is_pass = False
            continue

        if cu_bpc_map.get(customer_code, {}).get('deleted_mark') == '1':
            item.update({'message': f'{customer_code}客户编码已打删除标记, 不允许创建订单, 请检查',
                         'execute_result': '操作失败'})
            is_pass = False
            continue

        if dp_bpc_map.get(dp_code, {}).get('deleted_mark') == '1':
            item.update(
                {'message': f'{dp_code}客户编码已打删除标记, 不允许创建订单, 请检查', 'execute_result': '操作失败'})
            is_pass = False

    return is_pass, data


def creditCheck():
    """
    批量信用控制检查
    """
    res = Response()
    req = Request()
    body = json.loads(req.body())
    data = body.get('data')
    action = body.get('action')  # 创建还是更新
    print(action)
    # 是否弹窗标识
    flag = 0
    data, code, msg = check_credit_save(data, action, 1)
    if code == 500:
        res.set_body(json.dumps({"code": code, "msg": msg, "data": data, 'flag': flag}))
        return
    error_msgs = [item for item in data if item.get('message')]
    print(error_msgs)
    if error_msgs:
        flag = 1
        msg = '客户信用额度已超额，是否确认保存订单'

    res.set_body(json.dumps({"code": 200, "msg": msg, "data": data, 'flag': flag}))
    return


def check_credit_save(data, action, is_msg):
    """
    批量信用检查和更新credit_status状态
    """
    code = 200
    msg = ''
    for item in data:
        print(item.get('credit_control_code', ''))
        if item.get('credit_control_code', '') == 'B':
            sales_item_category = item.get('sales_item_category', '')
            active_sql = f"""
             select `credit_activated_flag` from `t_ao_sd_item_category` where `sales_item_category`='{sales_item_category}'
            """
            active_data = db.query_sql(active_sql)
            if active_data:
                if active_data[0]['credit_activated_flag'] in ['1',1]:
                    # 需要进行信用检查
                    sales_org_code = item.get('sales_org_code', '')
                    query_management_sql = f"""
                     select `credit_management` from `t_alloc_credit_management` where `sales_org_code`='{sales_org_code}'
                    """
                    management_data = db.query_sql(query_management_sql)
                    if management_data:
                        customer_code = item['sp_code']
                        credit_management = management_data[0]['credit_management']
                        limit_sql = f"""
                         select `control_limit`, `order_limit` from `t_customer_credit_data` where `customer_code`='{customer_code}' and `credit_management`='{credit_management}'
                        """
                        limit_data = db.query_sql(limit_sql)
                        if limit_data:
                            control_limit = limit_data[0]['control_limit']
                            order_limit = limit_data[0]['order_limit']

                            calculate_limit_res = calculate_credit_limit([credit_management], [customer_code],
                                                                         company_code=item.get("company_code"))

                            occupied_limit = calculate_limit_res[0].get('total')
                            print("calculate_limit_res>>>>", calculate_limit_res)
                            print("occupied_limit>>>>", occupied_limit)

                            if order_limit == 1:
                                calculate_limit = occupied_limit
                            elif order_limit == 0:
                                so_sn = item.get('so_sn', '')
                                so_items = item.get('so_items', 0)
                                tax_sql = f"select `unit_price_including_tax` from `t_sales_order_item` where `so_sn`='{so_sn}' and `so_items`={so_items}"
                                tax_data = db.query_sql(tax_sql)
                                tax = tax_data[0]['unit_price_including_tax']

                                if action == 0:
                                    # 新建
                                    delivery_qty = item.get('planned_delivery_quantity', 0)
                                    calculate_limit = occupied_limit + Decimal(str(delivery_qty * tax))
                                else:
                                    # 维护
                                    after_delivery_qty = item.get('planned_delivery_quantity', 0)
                                    dn_sn = item.get('dn_sn', '')
                                    dn_item = item.get('dn_item', 0)
                                    dn_item_sql = f"""
                                     select `planned_delivery_quantity` as `old_delivery_qty`, `posted_quantity` from `t_dn_item` where `dn_sn`='{dn_sn}' and `dn_item`={dn_item}
                                    """
                                    dn_data = db.query_sql(dn_item_sql)
                                    old_delivery_qty = dn_data[0]['old_delivery_qty']
                                    posted_quantity = dn_data[0]['posted_quantity']
                                    calculate_limit = occupied_limit + Decimal(
                                        str((after_delivery_qty - posted_quantity) * tax)) - Decimal(
                                        str((old_delivery_qty - posted_quantity) * tax))
                            else:
                                raise ValueError("实际占用额度-订单值不合法请检查!")

                            if calculate_limit > control_limit:
                                if is_msg == 1:
                                    item[
                                        'message'] = f"{customer_code}客户信用额度为{control_limit},已使用信用额度为{calculate_limit},信用已超额,是否保存交货单"
                                    item['execute_result'] = '操作失败'
                                item['credit_status'] = 'C'
                            else:
                                item['credit_status'] = 'B'
                        else:
                            code = 500
                            msg = f'未找到{customer_code}客户在{credit_management}信用组织下的信用控制额度'
                            item['message'] = msg
                            item['execute_result'] = '操作失败'
                    else:
                        code = 500
                        msg = '信贷控制节点=B, 未找到销售组织对应的销售组织'
                        item['message'] = msg
                        item['execute_result'] = '操作失败'

                else:
                    item['credit_status'] = 'F'
        else:
            item['credit_status'] = 'F'

    return data, code, msg


def query_packing_status(mat_code, plant_code):
    """
    查询拣配状态
    """
    sql = f"""
     select `batch_mark` from `t_mmd_material_plant_data` where `mat_code`='{mat_code}' and `plant_code`='{plant_code}'
    """
    data = db.query_sql(sql)

    packing_status = 'D'
    if data:
        batch_mark = data[0]['batch_mark']
        if batch_mark == 1:
            packing_status = 'A'

    return packing_status


def singleCreditCheck():
    """
    单个信用控制检查
    """
    res = Response()
    req = Request()
    body = json.loads(req.body())
    data = body.get('data')
    action = body.get('action')  # 创建还是更新

    msg = 'OK'
    code = 200
    flag = False

    header = data['header']
    so_sn = header.get('so_sn', '')
    credit_control_code = query_credit_control_code(so_sn)
    sales_org_code = header.get('sales_org_code', '')
    customer_code = header.get('customer_code', '')

    items = data.get('items', [])

    if credit_control_code == 'B':
        for item in items:
            sales_item_category = item.get('sales_item_category', '')
            active_sql = f"""
             select `credit_activated_flag` from `t_ao_sd_item_category` where `sales_item_category`='{sales_item_category}'
            """
            active_data = db.query_sql(active_sql)
            if active_data:
                if active_data[0]['credit_activated_flag'] == '1':
                    # 需要进行信用检查
                    query_management_sql = f"""
                     select `credit_management` from `t_alloc_credit_management` where `sales_org_code`='{sales_org_code}'
                    """
                    management_data = db.query_sql(query_management_sql)
                    if management_data:
                        credit_management = management_data[0]['credit_management']
                        limit_sql = f"""
                         select `control_limit`, `order_limit` from `t_customer_credit_data` where `customer_code`='{customer_code}' and `credit_management`='{credit_management}'
                        """
                        limit_data = db.query_sql(limit_sql)
                        if limit_data:
                            control_limit = limit_data[0]['control_limit']
                            order_limit = limit_data[0]['order_limit']

                            calculate_limit_res = calculate_credit_limit([credit_management], [customer_code],
                                                                         company_code=item.get("company_code"))
                            occupied_limit = calculate_limit_res[0].get('total')

                            if order_limit == 1:
                                calculate_limit = occupied_limit
                            elif order_limit == 0:
                                so_sn = item.get('so_sn', '')
                                so_items = item.get('so_items', 0)
                                tax_sql = f"select `unit_price_including_tax` from `t_sales_order_item` where `so_sn`='{so_sn}' and `so_items`={so_items}"
                                tax_data = db.query_sql(tax_sql)
                                tax = tax_data[0]['unit_price_including_tax']

                                if action == 0:
                                    # 新建
                                    delivery_qty = item.get('delivered_quantity', 0)
                                    calculate_limit = occupied_limit + Decimal(str(delivery_qty * tax))
                                else:
                                    # 维护
                                    after_delivery_qty = item.get('delivery_qty', 0)
                                    dn_sn = item.get('dn_sn', '')
                                    dn_item = item.get('dn_item', 0)
                                    dn_item_sql = f"""
                                     select `planned_delivery_quantity` as `old_delivery_qty`, `posted_quantity` from `t_dn_item` where `dn_sn`='{dn_sn}' and `dn_item`={dn_item}
                                    """
                                    dn_data = db.query_sql(dn_item_sql)
                                    old_delivery_qty = dn_data[0]['old_delivery_qty']
                                    posted_quantity = dn_data[0]['posted_quantity']
                                    calculate_limit = occupied_limit + Decimal(
                                        str((after_delivery_qty - posted_quantity) * tax)) - Decimal(
                                        str((old_delivery_qty - posted_quantity) * tax))
                            else:
                                raise ValueError("实际占用额度-订单值不合法请检查!")

                            if calculate_limit > control_limit:
                                item[
                                    'message'] = f"{customer_code}客户信用额度为{control_limit},已使用信用额度为{calculate_limit},信用已超额,是否保存交货单"
                                item['execute_result'] = '操作失败'
                                item['credit_status'] = 'C'
                                msg = '客户信用额度已超额，是否确认保存订单'
                                flag = True
                                code = 400
                            else:
                                item['credit_status'] = 'B'
                        else:
                            code = 500
                            msg = f'未找到{customer_code}客户在{credit_management}信用组织下的信用控制额度'
                            item['message'] = msg
                            item['execute_result'] = '操作失败'
                    else:
                        code = 500
                        msg = '信贷控制节点=B, 未找到销售组织对应的销售组织'
                        item['message'] = msg
                        item['execute_result'] = '操作失败'

                else:
                    item['credit_status'] = 'F'
    else:
        for item in items:
            item['credit_status'] = 'F'

    res.set_body(json.dumps({"code": code, "msg": msg, "data": data, 'flag': flag}))
    return


def query_credit_control_code(so_sn):
    """
    查询信贷控制节点
    """
    credit_control_code = ''
    sql = f"""
     select `credit_control_code` from `t_sales_order_header` where `so_sn`='{so_sn}'
    """
    data = db.query_sql(sql)

    if data:
        credit_control_code = data[0]['credit_control_code']

    return credit_control_code


def query_additional_property():
    """
    批量维护时获取附加属性
    """
    query_sql = f"""
    SELECT
        ap.`dn_sn`,
        ap.`dn_item`,
        pf.`field_code`,
        pf.`field_name`,
        pf.`field_type`,
        pf.`single_value` AS `field_mark`,
    CASE
        WHEN pf.`single_value` = 1 AND pf.`field_type` = 'varchar' THEN ap.`field_value`
        WHEN pf.`single_value` = 1 AND pf.`field_type` = 'int' THEN ap.`field_value_int`
        WHEN pf.`single_value` = 1 AND pf.`field_type` = 'date' THEN ap.`field_value_date`
        WHEN pf.`single_value` = 1 AND pf.`field_type` = 'time' THEN ap.`field_value_time`
        WHEN pf.`single_value` = 1 AND pf.`field_type` = 'decimal' THEN ap.`field_value_decimal`
        ELSE ap.`field_value`
        END AS `field_value`,
    CASE
        WHEN pf.`single_value` = 0 AND pf.`field_type` = 'varchar' THEN ap.`field_value_from`
        WHEN pf.`single_value` = 0 AND pf.`field_type` = 'int' THEN ap.`field_value_int_from`
        WHEN pf.`single_value` = 0 AND pf.`field_type` = 'date' THEN ap.`field_value_date_from`
        WHEN pf.`single_value` = 0 AND pf.`field_type` = 'time' THEN ap.`field_value_time_from`
        WHEN pf.`single_value` = 0 AND pf.`field_type` = 'decimal' THEN ap.`field_value_decimal_from`
        ELSE ap.`field_value_from`
        END AS `field_value_from`,
    CASE
        WHEN pf.`single_value` = 0 AND pf.`field_type` = 'varchar' THEN ap.`field_value_to`
        WHEN pf.`single_value` = 0 AND pf.`field_type` = 'int' THEN ap.`field_value_int_to`
        WHEN pf.`single_value` = 0 AND pf.`field_type` = 'date' THEN ap.`field_value_date_to`
        WHEN pf.`single_value` = 0 AND pf.`field_type` = 'time' THEN ap.`field_value_time_to`
        WHEN pf.`single_value` = 0 AND pf.`field_type` = 'decimal' THEN ap.`field_value_decimal_to`
        ELSE ap.`field_value_to`
        END AS `field_value_to`,
        pf.`required`,
        pf.`field_length`,
        pf.`field_decimal_places`
    FROM
        `t_dn_additional_property` ap
    JOIN
        `t_ap_property_field` pf ON pf.`field_code` = ap.`field_code`
    """
    property_info, property_display, property_info_save = {}, {}, {}
    query_data = db.query_sql(query_sql)

    if query_data:
        for item in query_data:
            dn_sn = item.get('dn_sn')
            dn_item = item.get('dn_item')
            field_code = item.get('field_code') or ''
            field_name = item.get('field_name') or field_code or ''
            field_mark = item.get('field_mark')
            field_value = item.get('field_value') or ''
            field_value_from = item.get('field_value_from') or ''
            field_value_to = item.get('field_value_to') or ''
            field_type = item.get('field_type')
            unique_key = str(dn_sn) + '|' + str(dn_item)

            if field_mark == 1:
                if unique_key not in property_info_save:
                    property_info_save[unique_key] = []
                property_info_save[unique_key].append(item)

                if unique_key in property_info:
                    property_info[unique_key][field_code] = {'field_value': field_value,
                                                             'field_type': field_type}
                else:
                    property_info[unique_key] = {field_code: {'field_value': field_value,
                                                              'field_type': field_type}}

                property_display[field_code] = {"description": field_name, "field": field_code}
            else:
                item_copy = copy.copy(item)
                if unique_key not in property_info:
                    property_info[unique_key] = {}

                if unique_key not in property_info_save:
                    property_info_save[unique_key] = []

                item.update({'field_code': field_code + '_from'})
                item_copy.update({'field_code': field_code + '_to'})
                property_info_save[unique_key].append(item)
                property_info_save[unique_key].append(item_copy)

                if unique_key in property_info:
                    property_info[unique_key][field_code + "_from"] = {'field_value': field_value_from,
                                                                       'field_type': field_type}
                    property_info[unique_key][field_code + "_to"] = {'field_value': field_value_to,
                                                                     'field_type': field_type}
                else:
                    property_info[unique_key] = {field_code + "_from": {'field_value': field_value_from,
                                                                        'field_type': field_type},
                                                 field_code + "_to": {'field_value': field_value_to,
                                                                      'field_type': field_type}}
                property_display[field_code + '_from'] = {"description": field_name + '从',
                                                          "field": field_code + "_from"}
                property_display[field_code + '_to'] = {"description": field_name + '到',
                                                        "field": field_code + "_to"}

    return property_info, property_display, property_info_save
