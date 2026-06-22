"""
@File    : DxSalesDeliveryOrder.py
@Author  : kai.wang@dxdstech.com
@Date    : 2025/05/06 14:35
@explain : 销售交货单批量创建，批量修改封装
"""
import time
from typing import List, TypeVar

from DbHelper import DbHelper
from DxBusinessDataConvertUtil import convert_material_unit_qty
from GenerateSerialNum import generate_serial_num
from logger import LoggerConfig
from SystemHelper import EnvKeys, SystemHelper
from ToolsMethods import ResponseData, calc_time
from ZZEXT_OperateSalesDeliveryNote import edit_additional_fields, get_additional_fields
from ZZEXT_SalesDeliveryOrder import after_save, before_check, before_save

FLAG = 1

logger = LoggerConfig("DxSalesDeliveryOrder")
T = TypeVar('T')
db = DbHelper()

dn_type_range = []
external_number_map = {}
so_sn_range = []
so_sn_item_range = []
so_map = {}
customer_map = {}
partial_delivery_map = {}
incoterms_code_set = {}


def dn_fill_parameters(data):
    """
    填充非必传的参数
    """
    print("fill_parameters data", data)
    sales_order_header_dict = get_db_sales_order_header()
    dn_type_dict = get_db_dn_type()
    customer_basic_dict = get_db_customer_basic_data()
    customer_sales_dict = get_db_customer_sales_data()
    os_plant_dict = get_db_os_plant()
    os_plant_company_dict = get_db_os_plant_company()
    os_storage_location_dict = get_db_os_storage_location()
    material_basic_data_dict = get_db_mmd_material_basic_data()
    material_cost_data_dict = get_db_mmd_material_cost_data()

    for item in data:
        dn_type = item.get('dn_type')
        if not dn_type:
            return False, '交货单类型必输'
        items = item.get('items')
        if not items:
            return False, '行项目不能为空'
        so_sn = item.get("items")[0].get("so_sn")
        so_items = item.get("items")[0].get("so_items")
        if not item.get("company_code"):
            item["company_code"] = sales_order_header_dict.get(so_sn, {}).get("company_code", "")
        if not item.get("document_category"):
            item["document_category"] = dn_type_dict.get(item.get("dn_type"), {}).get("document_category")
        if not item.get("approval_method"):
            item["approval_method"] = dn_type_dict.get(item.get("dn_type"), {}).get("approval_method")
        if not item.get("approval_status"):
            item["approval_status"] = "E" if item["approval_method"] == "N" else "A"
        if not item.get("customer_code"):
            sales_org_code = item.get("items")[0].get("sales_org_code")
            customer_code = sales_order_header_dict.get(so_sn, {}).get("customer_code", "")
            if customer_code:
                if customer_basic_dict.get(customer_code, {}).get("shipping_freeze_flag") == 0:
                    return False, f"[{customer_code}]客户已打发货冻结标记,不可创建交货单"
                if customer_sales_dict.get((customer_code, sales_org_code), {}).get("shipping_freeze_flag") == 0:
                    return False, f"[{customer_code}]客户已打发货冻结标记,不可创建交货单"
                item["customer_code"] = customer_code
        sales_order_item = get_db_sales_order_item(so_sn, so_items)
        if not item.get("estimated_delivery_date"):
            item["estimated_delivery_date"] = sales_order_item.get("estimated_delivery_date")
        if not item.get("request_delivery_date"):
            item["request_delivery_date"] = sales_order_item.get("request_delivery_date")
        if not item.get("credit_control_code"):
            item["credit_control_code"] = sales_order_header_dict.get(so_sn, {}).get("credit_control_code", "")

        for so_item in item.get("items", []):
            so_sn = so_item.get("so_sn")
            so_items = so_item.get("so_items")
            sales_order_item = get_db_sales_order_item(so_sn, so_items)
            if not so_item.get("sales_org_code"):
                so_item["sales_org_code"] = sales_order_header_dict.get(so_sn, {}).get("sales_org_code", "")

            # if not so_item.get("distribution_channel_code"):
            so_item["distribution_channel_code"] = sales_order_header_dict.get(so_sn, {}).get(
                "distribution_channel_code", "")
            if not so_item.get("mat_code"):
                so_item["mat_code"] = sales_order_item.get("mat_code", "")
                so_item["mat_description"] = sales_order_item.get("mat_description", "")
            if so_item["ipn"]:
                if so_item["ipn"] not in material_basic_data_dict:
                    return False, f"""[{so_item["ipn"]}]等同物料编码不存在，请检查"""

            if not so_item.get("plant_code"):
                so_item["plant_code"] = sales_order_item.get("plant_code", "")
            else:
                if so_item["plant_code"] not in os_plant_dict:
                    return False, f"""[{so_item["plant_code"]}]工厂代码不存在，请检查"""

                if os_plant_company_dict.get((so_item["plant_code"], item.get("company_code"))) is None:
                    return False, f"""[{so_item["plant_code"]}]工厂代码与[{item.get("company_code")}]公司代码对应关系不存在，请检查"""

            if not so_item.get("cust_mat_code"):
                so_item["cust_mat_code"] = sales_order_item.get("cust_mat_code", "")
                so_item["cust_mat_code_description"] = sales_order_item.get("cust_mat_code_description", "")
            if so_item.get("stor_loc_code"):
                if os_storage_location_dict.get((so_item.get("plant_code"), so_item.get("stor_loc_code"))) is None:
                    return False, f"""[{so_item.get("plant_code")}]工厂代码与[{so_item.get("stor_loc_code")}]库存地点对应关系不存在，请检查"""

            if not so_item.get("picked_qty"):
                so_item["picked_qty"] = 0
            if not so_item.get("picked_base_qty"):
                so_item["picked_base_qty"] = 0
            if not so_item.get("picked_parallel_qty"):
                so_item["picked_parallel_qty"] = 0

            if not so_item.get("posted_quantity"):
                so_item["posted_quantity"] = 0
            if not so_item.get("posted_qty_base"):
                so_item["posted_qty_base"] = 0
            if not so_item.get("posted_qty_parallel"):
                so_item["posted_qty_parallel"] = 0

            if not so_item.get("posted_pod_qty"):
                so_item["posted_pod_qty"] = 0
            if not so_item.get("posted_pod_qty_base"):
                so_item["posted_pod_qty_base"] = 0
            if not so_item.get("posted_pod_qty_parallel"):
                so_item["posted_pod_qty_parallel"] = 0

            if not so_item.get("invoiced_quantity"):
                so_item["invoiced_quantity"] = 0

            if not so_item.get("related_to_delivery"):
                so_item["related_to_delivery"] = sales_order_item.get("related_to_delivery")

            if not so_item.get("packing_status"):
                if sales_order_item.get("related_to_delivery") == "A":
                    so_item["packing_status"] = "A"
                else:
                    so_item["packing_status"] = "D"

            if not so_item.get("related_to_delivery"):
                so_item["related_to_delivery"] = sales_order_item.get("related_to_delivery")

            so_item["posting_status"] = "A" if so_item["related_to_delivery"] == "A" else "D"
            if not so_item.get("pod_related"):
                so_item["pod_related"] = sales_order_item.get("pod_related")
            if not so_item.get("basic_uom"):
                so_item["basic_uom"] = material_basic_data_dict.get(so_item["mat_code"], {}).get("basic_uom", "")
            if not so_item.get("cost_uom"):
                so_item["cost_uom"] = material_cost_data_dict.get((so_item["mat_code"], so_item["plant_code"]), {}).get(
                    "cost_uom", "")
            if not so_item.get("parallel_uom"):
                so_item["parallel_uom"] = material_basic_data_dict.get(so_item["mat_code"], {}).get("parallel_uom", "")
            if not so_item.get("transaction_uom"):
                so_item["transaction_uom"] = sales_order_item.get("sales_uom")

            if not so_item.get("related_to_invoices"):
                so_item["related_to_invoices"] = sales_order_item.get("related_to_invoices")

            if not so_item.get("billing_status"):
                if so_item["related_to_invoices"] == "B":
                    so_item["billing_status"] = "A"
                else:
                    so_item["billing_status"] = "D"
            if not so_item.get("movement_type"):
                so_item["movement_type"] = sales_order_item.get("movement_type")
            if not so_item.get("movement_type_it"):
                so_item["movement_type_it"] = sales_order_item.get("movement_type_it")
            if not so_item.get("special_inventory_status1"):
                so_item["special_inventory_status1"] = sales_order_item.get("special_inventory_status1")

            if not so_item.get("wbs_elements"):
                so_item["wbs_elements"] = sales_order_item.get("wbs_elements")

            if not so_item.get("cost_center"):
                so_item["cost_center"] = sales_order_item.get("cost_center")

            if not so_item.get("profit_center"):
                so_item["profit_center"] = sales_order_item.get("profit_center")
            if not so_item.get("sales_item_category"):
                so_item["sales_item_category"] = sales_order_item.get("sales_item_category")

            if not so_item.get("incoterms_code"):
                so_item["incoterms_code"] = sales_order_item.get("incoterms_code")
            if not so_item.get("incoterm_position"):
                so_item["incoterm_position"] = sales_order_item.get("incoterm_position")

            if not so_item.get("sales_order_type"):
                so_item["sales_order_type"] = sales_order_header_dict.get(so_sn, {}).get("sales_order_type")

            # if not so_item.get("overdelivery_tolerance"):
            #     so_item["overdelivery_tolerance"] = sales_order_item.get("overdelivery_tolerance")
            # if not so_item.get("underdelivery_tolerance"):
            #     so_item["underdelivery_tolerance"] = sales_order_item.get("underdelivery_tolerance")

            if not so_item.get("dp_code"):
                return False, '送达方编码必输'

            if not so_item.get("dp_name"):
                so_item["dp_name"] = customer_basic_dict.get(so_item.get("dp_code"), {}).get("customer_description", "")

            if not so_item.get("dp_addr"):
                so_item["dp_addr"] = customer_basic_dict.get(so_item.get("dp_code"), {}).get("contact_address", "")
            if not so_item.get("dp_cont"):
                so_item["dp_cont"] = customer_basic_dict.get(so_item.get("dp_code"), {}).get("contact_person", "")
            if not so_item.get("dp_numb"):
                so_item["dp_numb"] = customer_basic_dict.get(so_item.get("dp_code"), {}).get("contact_number", "")
            # if not so_item.get("dp_short_name"):
            so_item["dp_short_name"] = customer_basic_dict.get(so_item.get("dp_code"), {}).get(
                "customer_short_name", "")
            if not so_item.get("postal_code"):
                so_item["dp_postal_code"] = customer_basic_dict.get(so_item.get("dp_code"), {}).get(
                    "postal_code", "")

            if not so_item.get("ed_code"):
                ed_code = sales_order_item.get("end_customer")
                so_item["ed_code"] = ed_code
                so_item["ed_name"] = customer_basic_dict.get(ed_code, {}).get(
                    "customer_description")
                so_item["ed_short_name"] = customer_basic_dict.get(ed_code, {}).get(
                    "customer_short_name")
                so_item["ed_postal_code"] = customer_basic_dict.get(ed_code, {}).get(
                    "postal_code", "")

            else:
                end_code = so_item["ed_code"]
                so_item["ed_name"] = customer_basic_dict.get(end_code, {}).get("customer_description","")
                so_item["ed_short_name"] = customer_basic_dict.get(end_code, {}).get(
                    "customer_short_name","")
                so_item["ed_postal_code"] = customer_basic_dict.get(end_code, {}).get(
                    "postal_code", "")


            print("查看so_item------", so_item)
            planned_delivery_quantity = so_item.get('planned_delivery_quantity')  # 计划交货数量
            if planned_delivery_quantity <= 0:
                return False, '计划交货数量必须大于0!'
            if not so_item.get("plan_delivery_qty_parallel_uom"):
                code, msg, qty = convert_material_unit_qty(so_item["mat_code"], so_item["transaction_uom"],
                                                           so_item["parallel_uom"], planned_delivery_quantity)
                if code == 200:
                    so_item["plan_delivery_qty_parallel_uom"] = qty
                else:
                    code, msg, qty = convert_material_unit_qty(so_item["mat_code"], so_item["basic_uom"],
                                                               so_item["parallel_uom"], planned_delivery_quantity)
                    if code == 200:
                        so_item["plan_delivery_qty_parallel_uom"] = qty
                    else:
                        so_item["plan_delivery_qty_parallel_uom"] = 0
            if not so_item.get("plan_delivery_qty_basic_uom"):
                code, msg, qty = convert_material_unit_qty(so_item["mat_code"], so_item["transaction_uom"],
                                                           so_item["basic_uom"], planned_delivery_quantity)
                if code == 200:
                    so_item["plan_delivery_qty_basic_uom"] = qty
                else:
                    code, msg, qty = convert_material_unit_qty(so_item["mat_code"], so_item["parallel_uom"],
                                                               so_item["basic_uom"], planned_delivery_quantity)
                    if code == 200:
                        so_item["plan_delivery_qty_basic_uom"] = qty
                    else:
                        so_item["plan_delivery_qty_basic_uom"] = 0
            if not so_item.get("undelivered_qty"):
                so_item["undelivered_qty"] = sales_order_item.get("order_qty", 0) - sales_order_item.get(
                    "quantity_of_delivery_order_created", 0)
            if not so_item.get("order_qty"):
                so_item["order_qty"] = sales_order_item.get("order_qty")
            if so_item.get("dn_additional_properties") is None:
                so_item["dn_additional_properties"] = []
            if not so_item.get("sp_code"):
                sales_org_code = so_item.get("sales_org_code")
                customer_code = sales_order_header_dict.get(so_sn, {}).get("customer_code", "")
                if customer_code:
                    if customer_basic_dict.get(customer_code, {}).get("shipping_freeze_flag") == 0:
                        return False, f"[{customer_code}]客户已打发货冻结标记,不可创建交货单"
                    if customer_sales_dict.get((customer_code, sales_org_code), {}).get("shipping_freeze_flag") == 0:
                        return False, f"[{customer_code}]客户已打发货冻结标记,不可创建交货单"
                    so_item["sp_code"] = customer_code
                    so_item["sp_name"] = customer_basic_dict.get(customer_code, {}).get("customer_description")
                    so_item["sp_short_name"] = customer_basic_dict.get(customer_code, {}).get("customer_short_name")
            else:
                so_item["sp_name"] = customer_basic_dict.get(so_item.get("sp_code"), {}).get("customer_description")
                so_item["sp_short_name"] = customer_basic_dict.get(so_item.get("sp_code"), {}).get(
                    "customer_short_name")

    return True, data


def dn_batch_create(test_run: int, data: List[T]) -> T:
    """
    test_run: 0-正式运行 / 1-测试运行
    data:
    内部调用:
    [{'dn_type': 'XDD2',      // 交货单类型
    'company_code': '1060',  // 公司代码
    'customer_code': 'C_00000146_I', // 客户编码
    'approval_status': 'E',  // 审批状态
    'approval_method': 'N',  // 审批方法
    'document_category': 'SDLV', // 单据类别
    'packing_status': 'A',  // 拣配状态
    'posting_status': 'A',  // 过账状态
    'pod_status': 'A',      // pod状态
    'billing_status': 'A',  // 开票状态
    'estimated_delivery_date': '2025-03-06', // 预计交货日期
    'request_delivery_date': '2025-03-06', // 要求交货日期
    'credit_control_code': '', // 信贷控制节点
    'items': [{
    'so_sn': 'XDD030600044SO', // 销售订单号
    'sales_org_code': 'XDD1',  // 销售组织
    'order_qty': 100,           // 订单数量
    'so_items': 20,            // 销售订单行号
    'dp_code': 'C_00000146_I', // 送达方编码
    'dp_name': 'XDD146销售客户', // 送达方名称
    'dp_addr': 'XDD3',         // 送货地址
    'dp_cont': 'XDD1',         // 送货联系人
    'dp_short_name': 'XDD146', // 客户简称
    'dp_numb': 'XDD2',         // 送货联系电话
    'ed_code': '',             // 终端客户
    'ed_name': '',             // 终端客户名称
    'ed_short_name': '',       // 客户简称
    'sp_code': 'C_00000146_I', // 客户编码
    'sp_name': 'XDD146销售客户', // 客户名称
    'sp_short_name': 'XDD146',  // 客户简称
    'mat_code': 'XDD00002M',    // 物料编码
    'ipn': '',                  // IPN
    'plant_code': 'XDD1',       // 工厂代码
    'cust_mat_code': 'XDD146',  // 客户物料编码
    'incoterms_code': '11111',  // 国际贸易术语
    'incoterm_position': '23132',  // 国际贸易术语位置
    'planned_delivery_quantity': 1060,       // 计划交货数量
    'plan_delivery_qty_parallel_uom': 1060,       // 计划交货数量（平行单位）
    'plan_delivery_qty_basic_uom': 1060,       // 计划交货数量（基本单位）
    'sales_item_category': 'S0',       // 交货项目类别
    'stor_loc_code': '',       // 库存地点
    'picked_qty': 0.0,         // 已拣配数量
    'posted_quantity': 0.0,    // 已过账数量
    'posting_status': 'A',     // 过账状态
    'billing_status': 'A',    // 开票状态
    'pod_related': '1',       // POD标记
    'pod_status': 'A',        // POD状态
    'movement_type': 'D014',  // 移动类型
    'movement_type_it': '',   // POD移动类型
    'special_inventory_status1': '', // 特殊库存状态1
    'wbs_elements': '',       // WBS元素
    'cost_center': 'X1C',     // 成本中心
    'profit_center': 'LR001', // 利润中心
    'related_to_invoices': 'A', // 开票参考单据
    'basic_uom': 'EA', // 基本单位
    'cost_uom': 'EA',  // 成本单位
    'transaction_uom': 'EA', // 交易单位
    'parallel_uom': 'EA', // 平行单位
    'parallel_qty': 1060, // 已拣配数量（平行单位）
    'credit_status': 'F', // 信用状态
    'actual_plant': '', // 实际工厂
    'dn_additional_properties': [{'field_code': 'DD', 'field_value': ''}], // 行项目附加属性
    'distribution_channel_code': '', // 分销渠道
    'prod_group': '', // 产品组
    'cust_mat_code_description': 'XDD146X', // 客户物料描述
    'related_to_delivery': 'A', // 交货控制方式
    'packing_status': 'D'}],  // 拣配状态
    'header_additional_property': []}]  // 抬头附加属性

    :return:  status: 0成功 1失败
              data: 成功返回交货单号和行号以及销售订单号和行号, 失败返回报错信息
              {'status': 0, 'data': [{'dn_sn': 'XDD1983736', '111', 'dn_item': 10, 'so_sn': '3221TR', 'so_items': 10}]},
              {'status': 1, 'data': '销售订单号不存在'}
    """
    logger.printInfo("dn_batch_create data:", data)
    logger.printInfo("执行开始时间", start_time := time.time())
    # 检查前拓展
    code, msg, error_list, data = before_check(db, data, test_run)
    if code != 200:
        return {'status': 1, 'data': '{} {}'.format(msg, ','.join(error_list))}
    # 填充缺少参数和添加校验逻辑
    fillStatus, data = dn_fill_parameters(data)
    if not fillStatus:
        return {'status': 1, 'data': data}
    logger.printInfo("dn_fill_parameters data", data)

    flag, data = common_field_validate(data)
    if not flag:
        return {'status': 1, 'data': data}
    # 检查后拓展
    code, msg, error_list, data = before_save(db, data, test_run)
    if code != 200:
        return {'status': 1, 'data': '{} {}'.format(msg, ','.join(error_list))}
    logger.printInfo("检查完成时间", end_time := time.time())
    logger.printInfo("检查耗时", end_time - start_time)

    if test_run == 1:
        return {'status': 0, 'data': data}
    else:
        sh = SystemHelper()
        user_id = sh.getEnv(EnvKeys.user_id)

        sn_cat_map = {item.get('dn_sn'): item.get('document_category') for item in data}

        headers = []
        items = []
        header_additional_property = []
        dn_additional_properties = []
        for item in data:
            dn_items = item.get('items')
            for dn_item in dn_items:
                dn_additional_list = dn_item.get('dn_additional_properties', [])
                if dn_additional_list:
                    for dn_additional_item in dn_additional_list:
                        dn_additional_item.update({'dn_sn': dn_item.get('dn_sn'),
                                                   'dn_item': dn_item.get('dn_item')})
                dn_additional_properties.extend(dn_additional_list)
            items.extend(dn_items)
 
            headers.append(item)
            header_additional_list = item.get('header_additional_property')
            if header_additional_list:
                for header_additional_item in header_additional_list:
                    header_additional_item.update({'dn_sn': item.get('dn_sn'),
                                                   'dn_item': 0})
            header_additional_property.extend(header_additional_list)

        header_additional_property.extend(dn_additional_properties)
        [item.pop('id', 0) for item in header_additional_property]

        try:
            db.batchInsertToDB('t_dn_header', headers, user_id=user_id, printSql=True)
            db.batchInsertToDB('t_dn_item', items, user_id=user_id, printSql=True)

            header_additional_property = merge_property_field(header_additional_property)
            db.batchInsertToDB('t_dn_additional_property', header_additional_property, user_id=user_id, printSql=True)

            sn_item_list = []
            for item in items:
                dp_code = item.get('dp_code', '')
                dp_name = item.get('dp_name', '')
                dp_addr = item.get('dp_addr', '')
                dp_postal_code = item.get('dp_postal_code', '')
                dp_short_name = item.get('dp_short_name', '')
                sp_short_name = item.get('sp_short_name', '')
                ed_short_name = item.get('ed_short_name', '')
                ed_postal_code = item.get('ed_postal_code', '')
                dp_cont = item.get('dp_cont', '')
                dp_numb = item.get('dp_numb', '')
                sp_code = item.get('sp_code', '')
                sp_name = item.get('sp_name', '')
                ed_code = item.get('ed_code', '')
                ed_name = item.get('ed_name', '')

                document_category = sn_cat_map.get(item.get('dn_sn'))
                planned_delivery_quantity = item.get('planned_delivery_quantity')
                so_sn = item.get('so_sn')
                so_items = item.get('so_items')
                dn_sn = item.get('dn_sn')
                dn_item = item.get('dn_item')
                order_qty = item.get('order_qty')

                handle_sales_status(db, so_sn, so_items, planned_delivery_quantity)

                query_sales_qty = f"select `quantity_of_delivery_order_created` from `t_sales_order_item` where `so_sn`='{so_sn}' and `so_items`={so_items}"
                ret = db.query_sql(query_sales_qty)
                quantity_of_delivery_order_created = ret[0].get('quantity_of_delivery_order_created')
                # print("quantity_of_delivery_order_created？？？？", quantity_of_delivery_order_created)
                ture_undelivered_qty = order_qty - quantity_of_delivery_order_created

                dn_item_map = {'dn_sn': dn_sn, 'dn_item': dn_item, 'so_sn': so_sn,
                               'so_items': so_items, 'planned_delivery_quantity': planned_delivery_quantity,
                               'quantity_of_delivery_order_created': quantity_of_delivery_order_created,
                               'undelivered_qty': ture_undelivered_qty}
                sn_item_list.append(dn_item_map)

                # 单一创建的结构
                if item.get('partners'):
                    for partner in item['partners']:
                        business_partner_no = partner.get('business_partner_no', 0)
                        business_partner_type = partner.get('business_partner_type', '')
                        business_partner_code = partner.get('business_partner_code', '')
                        business_partner_name = partner.get('business_partner_name', '')
                        business_partner_addr = partner.get('business_partner_addr', '')
                        short_name = partner.get('short_name', '')
                        contact_person = partner.get('contact_person', '')
                        contact_number = partner.get('contact_number', '')
                        if business_partner_type == 'DP':
                            dp_code = partner.get('dp_code', '')
                            dp_name = partner.get('dp_name', '')
                            dp_addr = partner.get('dp_addr', '')
                            dp_cont = partner.get('dp_cont', '')
                            dp_numb = partner.get('dp_numb', '')
                            dp_short_name = partner.get('dp_short_name', '')
                            partner_sql = (
                                f"insert into `t_documents_business_partner`(`doc_sn`, `doc_items`, `business_partner_no`, `business_partner_type`, "
                                f"`business_partner_code`, `business_partner_name`, `business_partner_addr`, `business_partner_short_name`, `contact_person`, `contact_number`, "
                                f"`create_id`, `document_category`) values('{dn_sn}', {dn_item}, {business_partner_no}, '{business_partner_type}', "
                                f"'{dp_code}', '{dp_name}', '{dp_addr}', '{dp_short_name}', '{dp_cont}', '{dp_numb}', "
                                f"{user_id}, '{document_category}')")
                            db.exec_sql(partner_sql)
                        elif business_partner_type == 'EC':
                            ed_name = partner.get('ed_name', '')
                            ed_code = partner.get('ed_code', '')
                            ed_short_name = partner.get('ed_short_name', '')
                            if ed_name is None:
                                ed_name = ""
                            if ed_short_name is None:
                                ed_short_name = ""
                            partner_sql = (
                                f"insert into `t_documents_business_partner`(`doc_sn`, `doc_items`, `business_partner_no`, `business_partner_type`, "
                                f"`business_partner_code`, `business_partner_name`, `business_partner_short_name`, "
                                f"`create_id`, `document_category`) values('{dn_sn}', {dn_item}, {business_partner_no}, '{business_partner_type}', "
                                f"'{ed_code}', '{ed_name}', '{ed_short_name}', "
                                f"{user_id}, '{document_category}')")
                            db.exec_sql(partner_sql)
                        else:
                            partner_sql = (
                                f"insert into `t_documents_business_partner`(`doc_sn`, `doc_items`, `business_partner_no`, `business_partner_type`, "
                                f"`business_partner_code`, `business_partner_name`, `business_partner_short_name`, `contact_person`, `contact_number`, `business_partner_addr`, "
                                f"`create_id`, `document_category`) values('{dn_sn}', {dn_item}, {business_partner_no}, '{business_partner_type}', "
                                f"'{business_partner_code}', '{business_partner_name}', '{short_name}', '{contact_person}', '{contact_number}', '{business_partner_addr}', "
                                f"{user_id}, '{document_category}')")
                            db.exec_sql(partner_sql)

                else:
                    business_partner_no = 1

                    dp_sql = f"""
                             insert into `t_documents_business_partner`(`doc_sn`, `doc_items`, `business_partner_no`, `business_partner_type`, `business_partner_code`, 
                             `business_partner_name`, `business_partner_addr`, `business_partner_short_name`, `contact_person`, `contact_number`, `document_category`, `create_id`,`postal_code`) values('{dn_sn}', 
                             {dn_item}, {business_partner_no}, 'DP', '{dp_code}', '{dp_name}', '{dp_addr}', '{dp_short_name}',
                              '{dp_cont}', '{dp_numb}', '{document_category}', {user_id},'{dp_postal_code}')
                           """
                    db.exec_sql(dp_sql)

                    if ed_code:
                        if ed_name is None:
                            ed_name = ""
                        if ed_short_name is None:
                            ed_short_name = ""
                        business_partner_no += 1
                        ec_sql = (
                            f"insert into `t_documents_business_partner`(`doc_sn`, `doc_items`, `business_partner_no`, `business_partner_type`, "
                            f"`business_partner_code`, `business_partner_name`, `business_partner_short_name`, "
                            f"`document_category`, `create_id`) values('{dn_sn}', {dn_item}, {business_partner_no}, 'EC', "
                            f"'{ed_code}', '{ed_name}', '{ed_short_name}', '{document_category}', "
                            f"{user_id})")
                        db.exec_sql(ec_sql)

                    business_partner_no += 1
                    if sp_name is None:
                        sp_name = ""
                    if sp_short_name is None:
                        sp_short_name = ""
                    sp_sql = (
                        f"insert into `t_documents_business_partner`(`doc_sn`, `doc_items`, `business_partner_no`, `business_partner_type`, "
                        f"`business_partner_code`, `business_partner_name`, `business_partner_short_name`, "
                        f"`document_category`, `create_id`) values('{dn_sn}', {dn_item}, {business_partner_no}, 'SP', "
                        f"'{sp_code}', '{sp_name}', '{sp_short_name}', '{document_category}', "
                        f"{user_id})")
                    db.exec_sql(sp_sql)
            logger.printInfo("保存完成时间", save_end_time := time.time())
            logger.printInfo("校验时间", end_time - start_time)
            logger.printInfo("保存时间", save_end_time - end_time)
            # 保存完成后拓展
            code, msg, error_list, data = after_save(db, data, test_run)
            if code != 200:
                return {'status': 1, 'data': '{} {}'.format(msg, ','.join(error_list))}
            return {'status': 0, 'data': sn_item_list}

        except Exception as e:
            return {'status': 1, 'data': str(e)}


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


def assemble_header_item(data, user_id, flag):
    """
    组装交货单抬头和行项目
    """
    dn_order_list = []
    print("assemble_header_item data>>>",data)
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
        header.update({'dn_sn': groups[0].get('dn_sn', '')})
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
            dn_sn = group.get('dn_sn')
            dn_item = group.get('dn_item')
            item.update({'dn_sn': dn_sn})
            item.update({'dn_item': dn_item})
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
            item.update({'prod_group': group.get('prod_group')})
            item.update({'cust_mat_code_description': group.get('cust_mat_code_description', '')})
            item.update({'related_to_delivery': group.get('related_to_delivery', '')})
            item.update({'wbs_elements': group.get('wbs_elements', '')})
            item.update({'cost_center': group.get('cost_center', '')})
            item.update({'profit_center': group.get('profit_center', '')})
            item.update({'packing_status': group.get('packing_status', '')})
            item.update({'sales_order_type': group.get('sales_order_type', '')})
            item.update({'plan_delivery_qty_parallel_uom': group.get('plan_delivery_qty_parallel_uom', 0)})
            item.update({'plan_delivery_qty_basic_uom': group.get('plan_delivery_qty_basic_uom', 0)})
            items.append(item)
            header_additional_property.append(header_additional_list)
        header.update({'items': items, 'header_additional_property': header_additional_property[
            0] if header_additional_property else []})
        dn_order_list.append(header)

    return dn_order_list


def checkMustParams(data):
    global so_sn_item_range
    customer_basic_dict = get_db_customer_basic_data()
    for so_item in data:
        if not so_item.get("dn_type"):
            return False, ResponseData(400, "交货单类型必输", data)
        if not so_item.get("so_sn") or not so_item.get("so_items"):
            return False, ResponseData(400, "销售订单号和销售订单行号必输", data)
        if not so_sn_item_range:
            query_so_sn = f"""
            select `so_sn`,`so_items` from `t_sales_order_item`
            """
            so_sn_item_range = db.query_sql(query_so_sn)
            so_sn_item_range = [(item.get("so_sn"), item.get("so_items")) for item in so_sn_item_range]
        if (so_item.get("so_sn"), so_item['so_items']) not in so_sn_item_range:
            return False, ResponseData(400, "输入的销售订单号,行号不存在", data)
        if not so_item.get("dp_code"):
            return False, ResponseData(400, "送达方编码必输", data)
        else:
            if not so_item.get("dp_name"):
                so_item["dp_name"] = customer_basic_dict.get(so_item.get("dp_code"), {}).get("customer_description", "")
            if not so_item.get("dp_addr"):
                so_item["dp_addr"] = customer_basic_dict.get(so_item.get("dp_code"), {}).get("contact_address", "")
            if not so_item.get("dp_cont"):
                so_item["dp_cont"] = customer_basic_dict.get(so_item.get("dp_code"), {}).get("contact_person", "")
            if not so_item.get("dp_numb"):
                so_item["dp_numb"] = customer_basic_dict.get(so_item.get("dp_code"), {}).get("contact_number", "")
            if not so_item.get("dp_short_name"):
                so_item["dp_short_name"] = customer_basic_dict.get(so_item.get("dp_code"), {}).get(
                    "customer_short_name", "")
        if not so_item.get("planned_delivery_quantity"):
            return False, ResponseData(400, "计划交货数量必输", data)
    return True, ResponseData(200, "成功", data)


def fillGroupParams(data):
    db = DbHelper()
    for item in data:
        sql = f"""
            select 
                tsoh.`company_code`,
                tsoh.`distribution_channel_code`,
                tsoh.`sales_order_type`,
                tsoh.`customer_code`,
                tsoi.`end_customer`,
                tsoi.`incoterms_code`,
                tsoi.`incoterm_position`,
                tsoi.`sales_item_category`,
                tsoi.`mat_code`,
                tmmbd.`prod_group`
                
            from `t_sales_order_item` as tsoi
            left join `t_sales_order_header` as tsoh on tsoi.`so_sn` = tsoh.`so_sn`
            left join `t_mmd_material_basic_data` as tmmbd on tsoi.`mat_code` = tmmbd.`mat_code`
            where tsoi.`so_sn` = '{item.get("so_sn")}' and  tsoi.`so_items` = '{item.get("so_items")}'
        """
        ret = db.query_sql(sql)
        if ret:
            item["company_code"] = ret[0].get("company_code", "")
            item["distribution_channel_code"] = ret[0].get("distribution_channel_code", "")
            item["sp_code"] = ret[0].get("customer_code", "")
            item["ed_code"] = ret[0].get("end_customer", "")
            item["mat_code"] = ret[0].get("mat_code", "")
            item["incoterms_code"] = ret[0].get("incoterms_code", "")
            item["incoterm_position"] = ret[0].get("incoterm_position", "")
            item["sales_item_category"] = ret[0].get("sales_item_category", "")
            item["sales_order_type"] = ret[0].get("sales_order_type", "")
            item["prod_group"] = ret[0].get("prod_group", "")
    return data


def dn_batch_create_API(test_run: int, data: List[T], cust, mat, body) -> T:
    """
    test_run: 0-正式运行 / 1-测试运行
    data:
    内部调用:
    [{'dn_type': 'XDD2',      // 交货单类型
    'company_code': '1060',  // 公司代码
    'customer_code': 'C_00000146_I', // 客户编码
    'approval_status': 'E',  // 审批状态
    'approval_method': 'N',  // 审批方法
    'document_category': 'SDLV', // 单据类别
    'packing_status': 'A',  // 拣配状态
    'posting_status': 'A',  // 过账状态
    'pod_status': 'A',      // pod状态
    'billing_status': 'A',  // 开票状态
    'estimated_delivery_date': '2025-03-06', // 预计交货日期
    'request_delivery_date': '2025-03-06', // 要求交货日期
    'credit_control_code': '', // 信贷控制节点
    'items': [{
    'so_sn': 'XDD030600044SO', // 销售订单号
    'sales_org_code': 'XDD1',  // 销售组织
    'order_qty': 100,           // 订单数量
    'so_items': 20,            // 销售订单行号
    'dp_code': 'C_00000146_I', // 送达方编码
    'dp_name': 'XDD146销售客户', // 送达方名称
    'dp_addr': 'XDD3',         // 送货地址
    'dp_cont': 'XDD1',         // 送货联系人
    'dp_short_name': 'XDD146', // 客户简称
    'dp_numb': 'XDD2',         // 送货联系电话
    'ed_code': '',             // 终端客户
    'ed_name': '',             // 终端客户名称
    'ed_short_name': '',       // 客户简称
    'sp_code': 'C_00000146_I', // 客户编码
    'sp_name': 'XDD146销售客户', // 客户名称
    'sp_short_name': 'XDD146',  // 客户简称
    'mat_code': 'XDD00002M',    // 物料编码
    'ipn': '',                  // IPN
    'plant_code': 'XDD1',       // 工厂代码
    'cust_mat_code': 'XDD146',  // 客户物料编码
    'incoterms_code': '11111',  // 国际贸易术语
    'incoterm_position': '23132',  // 国际贸易术语位置
    'planned_delivery_quantity': 1060,       // 计划交货数量
    'plan_delivery_qty_parallel_uom': 1060,       // 计划交货数量（平行单位）
    'plan_delivery_qty_basic_uom': 1060,       // 计划交货数量（基本单位）
    'sales_item_category': 'S0',       // 交货项目类别
    'stor_loc_code': '',       // 库存地点
    'picked_qty': 0.0,         // 已拣配数量
    'posted_quantity': 0.0,    // 已过账数量
    'posting_status': 'A',     // 过账状态
    'billing_status': 'A',    // 开票状态
    'pod_related': '1',       // POD标记
    'pod_status': 'A',        // POD状态
    'movement_type': 'D014',  // 移动类型
    'movement_type_it': '',   // POD移动类型
    'special_inventory_status1': '', // 特殊库存状态1
    'wbs_elements': '',       // WBS元素
    'cost_center': 'X1C',     // 成本中心
    'profit_center': 'LR001', // 利润中心
    'related_to_invoices': 'A', // 开票参考单据
    'basic_uom': 'EA', // 基本单位
    'cost_uom': 'EA',  // 成本单位
    'transaction_uom': 'EA', // 交易单位
    'parallel_uom': 'EA', // 平行单位
    'parallel_qty': 1060, // 已拣配数量（平行单位）
    'credit_status': 'F', // 信用状态
    'actual_plant': '', // 实际工厂
    'dn_additional_properties': [{'field_code': 'DD', 'field_value': ''}], // 行项目附加属性
    'distribution_channel_code': '', // 分销渠道
    'prod_group': '', // 产品组
    'cust_mat_code_description': 'XDD146X', // 客户物料描述
    'related_to_delivery': 'A', // 交货控制方式
    'packing_status': 'D'}],  // 拣配状态
    'header_additional_property': []}]  // 抬头附加属性

    :return:  status: 0成功 1失败
              data: 成功返回交货单号和行号以及销售订单号和行号, 失败返回报错信息
              {'status': 0, 'data': [{'dn_sn': 'XDD1983736', '111', 'dn_item': 10, 'so_sn': '3221TR', 'so_items': 10}]},
              {'status': 1, 'data': '销售订单号不存在'}
    """
    sh = SystemHelper()
    user_id = sh.getEnv(EnvKeys.user_id)
    logger.printInfo("dn_batch_create data:", data)
    logger.printInfo("执行开始时间", start_time := time.time())
    status, ret = checkMustParams(data)
    if not status:
        return {'status': 1, 'data': ret.msg}
    # 将分组字段填充完全
    data = fillGroupParams(data)
    print("data>>>>>>>>>", data)
    import pandas as pd

    df = pd.DataFrame(data)
    # base_group_list = ['company_code', 'distribution_channel_code', 'prod_group', 'sp_code',
    #                    'dp_code', 'dp_name', 'dp_cont', 'dp_numb']
    base_group_list = ['company_code', 'distribution_channel_code', 'sp_code',
                       'dp_code', 'dp_name', 'dp_cont', 'dp_numb']
    if cust:
        base_group_list.append('ed_code')
    if mat:
        base_group_list.append('mat_code')
    base_group_list.append('dn_type')
    grouped = df.groupby(base_group_list)
    group_dicts = {key: group.to_dict('records') for key, group in grouped}

    try:
        data = assemble_header_item(group_dicts, user_id, 2)
    except ValueError as e:
        # res.set_body(json.dumps({"code": 500, "msg": str(e), "data": ''}))
        # return
        return {'status': 1, 'data': str(e)}

    # 屏幕增强 --整理客制化字段
    data = edit_additional_fields(user_id, body, data)

    # 填充缺少参数和添加校验逻辑
    fillStatus, data = dn_fill_parameters(data)
    if not fillStatus:
        return {'status': 1, 'data': data}
    logger.printInfo("dn_fill_parameters data", data)
    # 检查前拓展
    code, msg, error_list, data = before_check(db, data, test_run)
    if code != 200:
        return {'status': 1, 'data': '{} {}'.format(msg, ','.join(error_list))}

    flag, data = common_field_validate(data)
    if not flag:
        return {'status': 1, 'data': data}
    # 检查后拓展
    code, msg, error_list, data = before_save(db, data, test_run)
    if code != 200:
        return {'status': 1, 'data': '{} {}'.format(msg, ','.join(error_list))}
    logger.printInfo("检查完成时间", end_time := time.time())
    logger.printInfo("检查耗时", end_time - start_time)

    if test_run == 1:
        return {'status': 0, 'data': data}
    else:
        sh = SystemHelper()
        user_id = sh.getEnv(EnvKeys.user_id)

        sn_cat_map = {item.get('dn_sn'): item.get('document_category') for item in data}

        headers = []
        items = []
        header_additional_property = []
        dn_additional_properties = []
        for item in data:
            dn_items = item.get('items')
            for dn_item in dn_items:
                dn_additional_list = dn_item.get('dn_additional_properties', [])
                print("dn_additional_properties", dn_additional_properties)
                print("dn_additional_list", dn_additional_list)
                if dn_additional_list:
                    for dn_additional_item in dn_additional_list:
                        dn_additional_item.update({'dn_sn': dn_item.get('dn_sn'),
                                                   'dn_item': dn_item.get('dn_item')})
                dn_additional_properties.extend(dn_additional_list)
            items.extend(dn_items)
            # item.pop('items')
            headers.append(item)
            header_additional_list = item.get('header_additional_property')
            if header_additional_list:
                for header_additional_item in header_additional_list:
                    header_additional_item.update({'dn_sn': item.get('dn_sn'),
                                                   'dn_item': 0})
            header_additional_property.extend(header_additional_list)

        header_additional_property.extend(dn_additional_properties)
        [item.pop('id', 0) for item in header_additional_property]

        try:
            db.batchInsertToDB('t_dn_header', headers, user_id=user_id, printSql=True)
            db.batchInsertToDB('t_dn_item', items, user_id=user_id, printSql=True)

            header_additional_property = merge_property_field(header_additional_property)
            db.batchInsertToDB('t_dn_additional_property', header_additional_property, user_id=user_id, printSql=True)

            sn_item_list = []
            for item in items:
                dp_code = item.get('dp_code', '')
                dp_name = item.get('dp_name', '')
                dp_addr = item.get('dp_addr', '')
                dp_postal_code = item.get('dp_postal_code', '')
                dp_short_name = item.get('dp_short_name', '')
                sp_short_name = item.get('sp_short_name', '')
                ed_short_name = item.get('ed_short_name', '')
                ed_postal_code = item.get('ed_postal_code', '')
                dp_cont = item.get('dp_cont', '')
                dp_numb = item.get('dp_numb', '')
                sp_code = item.get('sp_code', '')
                sp_name = item.get('sp_name', '')
                ed_code = item.get('ed_code', '')
                ed_name = item.get('ed_name', '')

                document_category = sn_cat_map.get(item.get('dn_sn'))
                planned_delivery_quantity = item.get('planned_delivery_quantity')
                so_sn = item.get('so_sn')
                so_items = item.get('so_items')
                dn_sn = item.get('dn_sn')
                dn_item = item.get('dn_item')
                order_qty = item.get('order_qty')

                handle_sales_status(db, so_sn, so_items, planned_delivery_quantity)

                query_sales_qty = f"select `quantity_of_delivery_order_created` from `t_sales_order_item` where `so_sn`='{so_sn}' and `so_items`={so_items}"
                ret = db.query_sql(query_sales_qty)
                quantity_of_delivery_order_created = ret[0].get('quantity_of_delivery_order_created')
                print("quantity_of_delivery_order_created？？？？", quantity_of_delivery_order_created)
                ture_undelivered_qty = order_qty - quantity_of_delivery_order_created

                dn_item_map = {'dn_sn': dn_sn, 'dn_item': dn_item, 'so_sn': so_sn,
                               'so_items': so_items, 'planned_delivery_quantity': planned_delivery_quantity,
                               'quantity_of_delivery_order_created': quantity_of_delivery_order_created,
                               'undelivered_qty': ture_undelivered_qty}
                sn_item_list.append(dn_item_map)

                # 单一创建的结构
                if item.get('partners'):
                    for partner in item['partners']:
                        business_partner_no = partner.get('business_partner_no', 0)
                        business_partner_type = partner.get('business_partner_type', '')
                        business_partner_code = partner.get('business_partner_code', '')
                        business_partner_name = partner.get('business_partner_name', '')
                        business_partner_addr = partner.get('business_partner_addr', '')
                        short_name = partner.get('short_name', '')
                        contact_person = partner.get('contact_person', '')
                        contact_number = partner.get('contact_number', '')
                        if business_partner_type == 'DP':
                            dp_code = partner.get('dp_code', '')
                            dp_name = partner.get('dp_name', '')
                            dp_addr = partner.get('dp_addr', '')
                            dp_cont = partner.get('dp_cont', '')
                            dp_numb = partner.get('dp_numb', '')
                            dp_short_name = partner.get('dp_short_name', '')
                            partner_sql = (
                                f"insert into `t_documents_business_partner`(`doc_sn`, `doc_items`, `business_partner_no`, `business_partner_type`, "
                                f"`business_partner_code`, `business_partner_name`, `business_partner_addr`, `business_partner_short_name`, `contact_person`, `contact_number`, "
                                f"`create_id`, `document_category`) values('{dn_sn}', {dn_item}, {business_partner_no}, '{business_partner_type}', "
                                f"'{dp_code}', '{dp_name}', '{dp_addr}', '{dp_short_name}', '{dp_cont}', '{dp_numb}', "
                                f"{user_id}, '{document_category}')")
                            db.exec_sql(partner_sql)
                        elif business_partner_type == 'EC':
                            ed_name = partner.get('ed_name', '')
                            ed_code = partner.get('ed_code', '')
                            ed_short_name = partner.get('ed_short_name', '')
                            if ed_name is None:
                                ed_name = ""
                            if ed_short_name is None:
                                ed_short_name = ""
                            partner_sql = (
                                f"insert into `t_documents_business_partner`(`doc_sn`, `doc_items`, `business_partner_no`, `business_partner_type`, "
                                f"`business_partner_code`, `business_partner_name`, `business_partner_short_name`, "
                                f"`create_id`, `document_category`) values('{dn_sn}', {dn_item}, {business_partner_no}, '{business_partner_type}', "
                                f"'{ed_code}', '{ed_name}', '{ed_short_name}', "
                                f"{user_id}, '{document_category}')")
                            db.exec_sql(partner_sql)
                        else:
                            partner_sql = (
                                f"insert into `t_documents_business_partner`(`doc_sn`, `doc_items`, `business_partner_no`, `business_partner_type`, "
                                f"`business_partner_code`, `business_partner_name`, `business_partner_short_name`, `contact_person`, `contact_number`, `business_partner_addr`, "
                                f"`create_id`, `document_category`) values('{dn_sn}', {dn_item}, {business_partner_no}, '{business_partner_type}', "
                                f"'{business_partner_code}', '{business_partner_name}', '{short_name}', '{contact_person}', '{contact_number}', '{business_partner_addr}', "
                                f"{user_id}, '{document_category}')")
                            db.exec_sql(partner_sql)

                else:
                    business_partner_no = 1

                    dp_sql = f"""
                             insert into `t_documents_business_partner`(`doc_sn`, `doc_items`, `business_partner_no`, `business_partner_type`, `business_partner_code`, 
                             `business_partner_name`, `business_partner_addr`, `business_partner_short_name`, `contact_person`, `contact_number`, `document_category`, `create_id`,`postal_code`) values('{dn_sn}', 
                             {dn_item}, {business_partner_no}, 'DP', '{dp_code}', '{dp_name}', '{dp_addr}', '{dp_short_name}',
                              '{dp_cont}', '{dp_numb}', '{document_category}', {user_id},'{dp_postal_code}')
                           """
                    db.exec_sql(dp_sql)

                    if ed_code:
                        business_partner_no += 1
                        if ed_name is None:
                            ed_name = ""
                        if ed_short_name is None:
                            ed_short_name = ""
                        ec_sql = (
                            f"insert into `t_documents_business_partner`(`doc_sn`, `doc_items`, `business_partner_no`, `business_partner_type`, "
                            f"`business_partner_code`, `business_partner_name`, `business_partner_short_name`, "
                            f"`document_category`, `create_id`) values('{dn_sn}', {dn_item}, {business_partner_no}, 'EC', "
                            f"'{ed_code}', '{ed_name}', '{ed_short_name}', '{document_category}', "
                            f"{user_id})")
                        db.exec_sql(ec_sql)

                    business_partner_no += 1
                    sp_sql = (
                        f"insert into `t_documents_business_partner`(`doc_sn`, `doc_items`, `business_partner_no`, `business_partner_type`, "
                        f"`business_partner_code`, `business_partner_name`, `business_partner_short_name`, "
                        f"`document_category`, `create_id`) values('{dn_sn}', {dn_item}, {business_partner_no}, 'SP', "
                        f"'{sp_code}', '{sp_name}', '{sp_short_name}', '{document_category}', "
                        f"{user_id})")
                    db.exec_sql(sp_sql)
            logger.printInfo("保存完成时间", save_end_time := time.time())
            logger.printInfo("校验时间", end_time - start_time)
            logger.printInfo("保存时间", save_end_time - end_time)
            # 保存完成后拓展
            code, msg, error_list, data = after_save(db, data, test_run)
            if code != 200:
                return {'status': 1, 'data': '{} {}'.format(msg, ','.join(error_list))}
            return {'status': 0, 'data': sn_item_list}

        except Exception as e:
            return {'status': 1, 'data': str(e)}


def dn_batch_update(test_run: int, data: List[T]) -> T:
    """
    批量维护
    test_run: 0-正式运行 / 1-测试运行
    data结构同创建
    return: 每个对象里会有校验的message信息
    """
    # 校验前
    code, msg, error_list, data = before_check(db, data, test_run)
    if code != 200:
        return '{} {}'.format(msg, ','.join(error_list))

    # 填充缺少参数和添加校验逻辑
    fillStatus, data = dn_fill_parameters(data)
    if not fillStatus:
        return data
    logger.printInfo("dn_fill_parameters data", data)
    flag, message = common_field_validate(data, isupdate=True)
    if not flag:
        return message

    # 校验后
    code, msg, error_list, data = before_save(db, data, test_run)
    if code != 200:
        return '{} {}'.format(msg, ','.join(error_list))

    for dn_item in data:
        items = _dn_batch_update(test_run, dn_item.get("items"))
        dn_item["items"] = items

    code, msg, error_list, data = after_save(db, data, test_run)
    if code != 200:
        return '{} {}'.format(msg, ','.join(error_list))
    return data


def _dn_batch_update(test_run: int, data: List[T]) -> T:
    for item in data:
        dn_sn = item.get('dn_sn')
        query_status_sql = f"select `approval_status` from `t_dn_header` where `dn_sn`='{dn_sn}'"
        approval_status = db.query_sql(query_status_sql)
        approval_status = approval_status[0].get('approval_status')
        query_pass_sql = f"select `document_modify_enabled_flag` from `t_dn_approval_status` where `dn_approval_status`='{approval_status}'"
        change_order = db.query_sql(query_pass_sql)
        if change_order[0].get('document_modify_enabled_flag') == 0:
            item.update({'message': '交货单不可被修改', 'execute_result': '操作失败'})

    # 先处理删除逻辑
    deleted_item_list = [item.get('id') for item in data if
                         int(item.get('deleted_mark')) == 1 and item.get('message') != '交货单不可被修改']
    deleted_item_placeholders = ','.join([f"{item}" for item in deleted_item_list])

    undeleted_item_list = [item.get('id') for item in data if
                           int(item.get('deleted_mark')) == 0 and
                           item.get('message') != '交货单不可被修改' and item.get('_tag_') == 'delete']
    undeleted_item_placeholders = ','.join([f"{item}" for item in undeleted_item_list])

    data_map = {item['id']: item for item in data}

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
                            {'message': f"{item.get('dn_sn')}交货单{item.get('dn_item')}行已拣配，不允许执行删除操作！",
                             'execute_result': '操作失败'})

        allowed_delete_list = [(item.get('id'), item.get('dn_sn'), item.get('dn_item')) for item in data if
                               item.get('message') != '交货单不可被修改' and '已拣配' not in item.get('message')]

        if allowed_delete_list:

            if test_run == 0:
                update_item_placeholders = ','.join([f"({item[0]}, 1)" for item in allowed_delete_list])
                update_sql = ("insert into `t_dn_item` (`id`, `deleted_mark`) values{} "
                              "ON DUPLICATE KEY UPDATE "
                              "`id`=values(`id`),"
                              "`deleted_mark`=values(`deleted_mark`)".format(update_item_placeholders))
                db.exec_sql(update_sql)

                for each in allowed_delete_list:
                    item_id = f"{each[1]}-{each[2]}"
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
                    delivery_qty = delivery_qty_res[0].get('planned_delivery_quantity')
                    so_sn = delivery_qty_res[0].get('so_sn')
                    so_items = delivery_qty_res[0].get('so_items')

                    data_map.get(item_id).update({'execute_result': '操作成功'})

                    try:
                        handle_sales_status(db, so_sn, so_items, delivery_qty, -1)
                    except Exception as e:
                        data_map.get(item_id).update({'message': str(e), 'execute_result': '操作失败'})


    elif undeleted_item_placeholders:

        allowed_undelete_list = [(item.get('id'), item.get('dn_sn'), item.get('dn_item')) for item in data if
                                 item.get('message') != '交货单不可被修改']

        if test_run == 0:
            if allowed_undelete_list:

                update_item_placeholders = ','.join([f"({item[0]}, 0)" for item in allowed_undelete_list])
                update_sql = ("insert into `t_dn_item` (`id`, `deleted_mark`) values{} "
                              "ON DUPLICATE KEY UPDATE "
                              "`id`=values(id),"
                              "`deleted_mark`=values(deleted_mark)".format(update_item_placeholders))
                db.exec_sql(update_sql)

                for each in allowed_undelete_list:
                    item_id = f"{each[1]}-{each[2]}"
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
                    delivery_qty = delivery_qty_res[0].get('planned_delivery_quantity')
                    so_sn = delivery_qty_res[0].get('so_sn')
                    so_items = delivery_qty_res[0].get('so_items')

                    update_sql = f"update `t_sales_order_item` set `quantity_of_delivery_order_created`=`quantity_of_delivery_order_created`+{delivery_qty} where `so_sn`='{so_sn}' and `so_items`={so_items}"
                    db.exec_sql(update_sql)

                    data_map.get(item_id).update({'execute_result': '操作成功'})

    else:
        allowed_data = [item for item in data if item.get('message') != '交货单不可被修改']
        print("allowed_data>>>>", allowed_data)
        for item in allowed_data:
            item_id = f"{item.get('dn_sn')}-{item.get('dn_item')}"
            # cur_deliver_qty = item.get('cur_deliver_qty')
            cur_deliver_qty = item.get('cur_deliver_qty') or item.get('planned_delivery_quantity')
            # re_deliver_qty = item.get('re_deliver_qty')
            re_deliver_qty = item.get('re_deliver_qty') or item.get('undelivered_qty')
            pod_qty = item.get('posted_pod_qty')
            print("cur_deliver_qty>>>", cur_deliver_qty)
            print("re_deliver_qty>>>", re_deliver_qty)

            if cur_deliver_qty <= 0:
                data_map.get(item_id).update({'message': '计划交货数量必须大于0！', 'execute_result': '操作失败'})

            if cur_deliver_qty > re_deliver_qty:
                data_map.get(item_id).update(
                    {'message': '本次计划交货数量不可大于未交货数量，请检查！', 'execute_result': '操作失败'})

            if cur_deliver_qty < pod_qty:
                data_map.get(item_id).update(
                    {'message': '交货单数量修改小于已确认交付数量，不允许此操作！', 'execute_result': '操作失败'})
        print("allowed_data>>>>1", allowed_data)
        # 批量更新逻辑
        partner_list = []
        dn_additional_props = []
        dn_item_list = []
        so_item_list = []

        if test_run == 0:
            sh = SystemHelper()
            user_id = sh.getEnv(EnvKeys.user_id)
            allowed_data = [item for item in data if
                            item.get('message', "") != '交货单不可被修改' and '数量' not in item.get('message', "")]
            if allowed_data:
                for item in allowed_data:
                    item.update({'execute_result': '操作成功'})
                    dn_sn = item.get('dn_sn')
                    dn_item = item.get('dn_item')
                    stor_loc_code = item.get('stor_loc_code', '')
                    ipn = item.get('ipn', '')
                    plant_code = item.get('plant_code', '')
                    cur_deliver_qty = item.get('cur_deliver_qty') or item.get('planned_delivery_quantity')  # 计划交货数量

                    dn_additional_properties = item.get('dn_additional_properties')
                    for add_pro in dn_additional_properties:
                        props_map = {}
                        field_code = add_pro.get('field_code', '')
                        field_value = add_pro.get('field_value', '')
                        props_map.update(
                            {'dn_sn': dn_sn, 'dn_item': dn_item, 'field_code': field_code, 'field_value': field_value})
                        dn_additional_props.append(props_map)

                    dn_item_map = {'dn_sn': dn_sn, 'dn_item': dn_item, 'planned_delivery_quantity': cur_deliver_qty,
                                   'ipn': ipn, 'stor_loc_code': stor_loc_code,
                                   'plant_code': plant_code}
                    dn_item_list.append(dn_item_map)

                    so_sn = item.get('so_sn')
                    so_items = item.get('so_items')
                    so_item = {'so_sn': so_sn, 'so_items': so_items}
                    so_item_list.append(so_item)

                    query_partner_sql = (
                        f"""select `business_partner_type`, `business_partner_no` from `t_documents_business_partner` where `doc_sn`='{dn_sn}' and 
                        `doc_items`={dn_item} """)
                    businesses = db.query_sql(query_partner_sql)
                    for business in businesses:
                        business_partner_no = business.get('business_partner_no')
                        if business.get('business_partner_type') == 'DP':
                            business_partner_name = item.get('dp_name')
                            business_partner_code = item.get('dp_code')
                            business_partner_addr = item.get('dp_addr')
                            contact_person = item.get('dp_cont')
                            contact_number = item.get('dp_numb')
                            partner = {'doc_sn': dn_sn, 'doc_items': dn_item,
                                       'business_partner_no': business_partner_no,
                                       'business_partner_name': business_partner_name,
                                       'business_partner_code': business_partner_code,
                                       'business_partner_addr': business_partner_addr, 'contact_person': contact_person,
                                       'contact_number': contact_number}

                        elif business.get('business_partner_type') == 'EC':
                            business_partner_code = item.get('ed_code')
                            business_partner_name = item.get('ed_name')
                            partner = {'doc_sn': dn_sn, 'doc_items': dn_item,
                                       'business_partner_no': business_partner_no,
                                       'business_partner_code': business_partner_code,
                                       'business_partner_name': business_partner_name}
                        elif business.get('business_partner_type') == 'SP':
                            business_partner_code = item.get('sp_code')
                            business_partner_name = item.get('sp_name')
                            short_name = item.get('short_name')
                            partner = {'doc_sn': dn_sn, 'doc_items': dn_item,
                                       'business_partner_no': business_partner_no,
                                       'business_partner_code': business_partner_code,
                                       'business_partner_name': business_partner_name,
                                       'short_name': short_name}

                        else:
                            partner = {}
                        partner_list.append(partner)

                partner_duplicate_keys = ['doc_sn', 'doc_items', 'business_partner_no', 'business_partner_code',
                                          'business_partner_name',
                                          'business_partner_addr', 'contact_person', 'contact_number']
                dn_item_duplicate_keys = ['dn_sn', 'dn_item', 'planned_delivery_quantity', 'stor_loc_code',
                                          'plant_code']
                dn_additional_duplicate_keys = ['dn_sn', 'dn_item', 'field_code', 'field_value']

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
                        item.update({'message': str(e), 'execute_result': '操作失败'})
    return data


def common_field_validate(data, isupdate=False):
    """
    :param data:待校验数据
    基础校验
    """
    global dn_type_range, external_number_map, so_sn_range, \
        so_map, customer_map, partial_delivery_map, incoterms_code_set

    cache_dn_sn_item = []
    for dn in data:
        dn_type = dn.get('dn_type')
        if not dn_type:
            return False, '交货单类型必输'
        if not dn_type_range:
            query_dn_type = "select `dn_type` from `t_dn_type_alloc`"
            dn_type_range = db.query_sql(query_dn_type)
            dn_type_range = [item['dn_type'] for item in dn_type_range]
        if dn_type not in dn_type_range:
            return False, '交货单类型不存在'
        else:

            if dn_type not in external_number_map:
                query_external_number = f"""
                 select d.`external_number` from `t_gi_coding_domain_alloc` a left join `t_gi_coding_domain` d 
                on a.`coding_domain`=d.`coding_domain` where a.`alloc_object`='dn_type' and a.`object_code`='{dn_type}'
                """
                external_numbers = db.query_sql(query_external_number)
                if not external_numbers:
                    return False, f'该类型[{dn_type}]没有分配编码域,请检查配置!'
                external_number = external_numbers[0]['external_number']
                external_number_map.update({dn_type: external_number})

            else:
                external_number = external_number_map.get(dn_type)

            if external_number == 1:
                dn_sn = dn.get('dn_sn')
                if not dn_sn:
                    return False, f'{dn_type}交货单类型号码段为外部给号，需要输入交货单号'
                if len(dn_sn) > 18:
                    return False, '交货单号超过最大长度'
            else:
                dn_sn = dn.get('dn_sn')
                if dn_sn:
                    return False, f'{dn_type}交货单类型号码段为内部给号，不可输入'
                if not isupdate:
                    try:
                        serial_map = generate_serial_num('dn_type', dn_type, db)
                        dn_sn = serial_map.get('serial_num', '')
                        dn.update({'dn_sn': dn_sn})
                    except Exception as e:
                        return False, str(e)
                else:
                    dn_sn = dn.get('dn_sn')

        items = dn.get('items')
        if not items:
            return False, '行项目不能为空'

        item_number = 0
        for item in items:
            external_number = external_number_map.get(dn_type)
            if dn_type:
                query_dn_type = f"""select `dn_type` from `t_dn_type_alloc` where `sales_order_type` ='{item.get("sales_order_type")}' and `sales_item_category` = '{item.get("sales_item_category")}' and `dn_type` = '{dn_type}' """
                dn_type_alloc = db.query_sql(query_dn_type)
                if not dn_type_alloc:
                    return False, f'交货单类型[{dn_type}]与销售订单类型[{item.get("sales_order_type")}],项目类别[{item.get("sales_item_category")}]对应关系不存在'
            if external_number == 1:
                dn_item = item.get('dn_item')
                if not dn_item:
                    return False, f'{dn_type}交货单类型号码段为外部给号，需要输入交货单行号'
            else:
                if not isupdate:
                    item_number += 10
                    item.update({'dn_item': item_number, 'dn_sn': dn_sn})
            if (item.get("dn_sn"), item.get("dn_item")) in cache_dn_sn_item:
                return False, f'交货单号和交货单行号重复'
            cache_dn_sn_item.append((item.get("dn_sn"), item.get("dn_item")))
            so_sn = item.get('so_sn')
            if not so_sn:
                return False, '销售订单号必输'
            if not so_sn_range:
                query_so_sn = f"""
                select `so_sn` from `t_sales_order_header`
                """
                so_sn_range = db.query_sql(query_so_sn)
                so_sn_range = [item['so_sn'] for item in so_sn_range]
            if so_sn not in so_sn_range:
                return False, '输入的销售订单号不存在'
            incoterms_code = item.get('incoterms_code')

            if incoterms_code:
                if not incoterms_code_set:
                    query_incoterms = f"""
                    SELECT `incoterms_code` FROM `t_incoterms`
                    """
                    incoterms_code_res = db.query_sql(query_incoterms)

                    incoterms_code_set = {i["incoterms_code"] for i in incoterms_code_res}
                    if incoterms_code not in incoterms_code_set:
                        return False, '国际贸易术语不存在，请检查'

            so_items = item.get('so_items')
            if not so_items:
                return False, '销售订单行号必输'
            if so_sn not in so_map:
                query_so_items = f"""
                 select `so_items` from `t_sales_order_item` where `so_sn`='{so_sn}'
                """
                so_item_range = db.query_sql(query_so_items)
                so_items_res = [item['so_items'] for item in so_item_range]
                so_map.update({so_sn: so_items_res})
            else:
                so_items_res = so_map[so_sn]
            so_items = int(so_items)
            if so_items not in so_items_res:
                return False, '输入的销售订单行号不存在'

            partial_delivery_enabled = item.get('partial_delivery_enabled')
            if partial_delivery_enabled is None:
                if (so_sn, so_items) not in partial_delivery_map:
                    query_partial_delivery = f"""
                     select `so_sn`, `so_items`, `partial_delivery_enabled` from `t_sales_order_item` 
                    where `so_sn`='{so_sn}' and `so_items`={so_items}
                    """
                    partial_enabled_res = db.query_sql(query_partial_delivery)
                    partial_delivery_enabled = partial_enabled_res[0]['partial_delivery_enabled']
                    partial_delivery_map.update({(partial_enabled_res[0]['so_sn'], partial_enabled_res[0]['so_items']):
                                                     partial_delivery_enabled})
                else:
                    partial_delivery_enabled = partial_delivery_map.get((so_sn, so_items))

            planned_delivery_quantity = item.get('planned_delivery_quantity')  # 计划交货数量
            # if not undelivered_qty:
            undelivered_qty = item.get('undelivered_qty')  # 未交货数量
            # print("planned_delivery_quantity>>>>>",planned_delivery_quantity)
            # print("undelivered_qty>>>>>",undelivered_qty)
            if not partial_delivery_enabled:
                if planned_delivery_quantity < undelivered_qty:
                    return False, '选择的销售订单不允许分批交货'
            if planned_delivery_quantity <= 0:
                return False, '计划交货数量必须大于0!'
            if planned_delivery_quantity > undelivered_qty:
                return False, '计划交货数量不能大于未交货数量'

            dp_code = item.get('dp_code')
            if not dp_code:
                return False, '客户编码必输'
            if not customer_map:
                query_customer = f"""
                 select `customer_code`, `deleted_mark`, `shipping_freeze_flag` from `t_bpc_customer_basic_data`
                """
                customer_res = db.query_sql(query_customer)
                customer_map = {customer['customer_code']: (customer['deleted_mark'], customer['shipping_freeze_flag'])
                                for customer in customer_res}
            if dp_code not in customer_map:
                return False, '客户编码不存在，请检查'
            else:
                flags = customer_map[dp_code]
                if FLAG in flags:
                    return False, '客户编码已打删除标记或发货冻结标记不允许创建和修改'

    return True, data


@calc_time
def handle_sales_status(db, so_sn, so_items, delivery_qty=None, operator=1, old_delivery_qty=0):
    """
    处理销售订单抬头和行项目的交货单创建状态和总体状态的更新
    """
    if delivery_qty:
        delivery_qty = delivery_qty * operator
        update_qty_sql = f"""
         update `t_sales_order_item` set `quantity_of_delivery_order_created` = `quantity_of_delivery_order_created` + {delivery_qty} - {old_delivery_qty} where `so_sn`='{so_sn}' and `so_items`={so_items}
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
     UPDATE `t_sales_order_item` set `delivery_status`='{delivery_status}', `overall_status`='{overall_status}' 
    where `so_sn`='{so_sn}' and `so_items`={so_items}
    """
    db.exec_sql(update_item_sql)

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
     UPDATE `t_sales_order_header` set `delivery_status`='{delivery_status}', `overall_status`='{overall_status}' 
    where `so_sn`='{so_sn}'
    """
    db.exec_sql(update_header_sql)

    return


def merge_property_field(data):
    """
    合并交货单特性字段
    """
    range_fields = {}

    for item in list(data):
        if item.get('field_mark', 0) == 0:
            dn_sn = item.get('dn_sn', '')
            dn_item = item.get('dn_item', '')
            field_code = item.get('field_code', '')
            base_code = field_code.removesuffix('_from').removesuffix('_to')
            field_type = item.get('field_type', '')
            field_value = item.get('field_value', '')

            unique_key = (dn_sn, dn_item, base_code)

            if unique_key not in range_fields:
                range_fields[unique_key] = {
                    'dn_sn': dn_sn,
                    'dn_item': dn_item,
                    'field_code': base_code,
                    'field_type': field_type,
                    'field_value': '',
                    'field_value_from': '',
                    'field_value_to': '',
                    'field_value_int': 0,
                    'field_value_int_from': 0,
                    'field_value_int_to': 0,
                    'field_value_date': '',
                    'field_value_date_from': '',
                    'field_value_date_to': '',
                    'field_value_time': '',
                    'field_value_time_from': '',
                    'field_value_time_to': '',
                    'field_value_decimal': 0.000000,
                    'field_value_decimal_from': 0.000000,
                    'field_value_decimal_to': 0.000000
                }

            if field_code.endswith('_from'):
                suffix = 'from'
            else:
                suffix = 'to'

            value_key = f'field_value_{field_type}_{suffix}' if field_type in ['int', 'date', 'time',
                                                                               'decimal'] else f'field_value_{suffix}'
            range_fields[unique_key][value_key] = field_value

            data.remove(item)

    data.extend(range_fields.values())

    for item in data:
        if item.get('field_mark', 0) != 0:
            field_type = item.get('field_type', '')
            field_value = item.get('field_value', '')

            if field_type in ['int', 'date', 'time', 'decimal']:
                value_key = f'field_value_{field_type}'
            else:
                value_key = 'field_value'

            item[value_key] = field_value

    return data


def get_db_sales_order_header():
    db = DbHelper()
    sql = "select * from `t_sales_order_header`"
    data = db.query_sql(sql)
    return {i.get("so_sn"): i for i in data}


def get_db_sales_order_item(so_sn, so_items):
    db = DbHelper()
    sql = f"""
    select tsoi.*,tmmbd.`mat_description`  from `t_sales_order_item` as tsoi 
    left join `t_mmd_material_basic_data` as tmmbd on tsoi.`mat_code` = tmmbd.`mat_code`
     where tsoi.`so_sn`='{so_sn}' and tsoi.`so_items`='{so_items}'
    """
    data = db.query_sql(sql)
    if data:
        return data[0]
    else:
        return {}


def get_db_dn_type():
    db = DbHelper()
    sql = "select * from `t_dn_type`"
    data = db.query_sql(sql)
    return {i.get("dn_type"): i for i in data}


def get_db_customer_basic_data():
    db = DbHelper()
    query_customer = f"""
                     select `customer_code`, `deleted_mark`, `shipping_freeze_flag`,
                     `customer_description`,`contact_address`,`contact_person`,`contact_number`,`customer_short_name`,
                     `postal_code`
                     from `t_bpc_customer_basic_data`
                    """
    data = db.query_sql(query_customer)
    return {i.get("customer_code"): i for i in data}


def get_db_customer_sales_data():
    db = DbHelper()
    query_customer = f"""
                     select `customer_code`,`sales_org_code`, `deleted_mark`, `shipping_freeze_flag` from `t_customer_sales_data`
                    """
    data = db.query_sql(query_customer)
    return {(i.get("customer_code"), i.get("sales_org_code")): i for i in data}


def get_db_os_plant():
    db = DbHelper()
    query_customer = f"""
                     select * from `t_os_plant` 
                    """
    data = db.query_sql(query_customer)
    return {i.get("plant_code"): i for i in data}


def get_db_os_plant_company():
    db = DbHelper()
    query_customer = f"""
                     select * from `t_os_plant` as `top` left join `t_os_company_plant_alloc` as `tocpa` on `top`.`plant_code` = `tocpa`.`plant_code` 
                    """
    data = db.query_sql(query_customer)
    return {(i.get("plant_code"), i.get("company_code")): i for i in data}


def get_db_os_storage_location():
    db = DbHelper()
    query_customer = f"""
                     select * from `t_os_plant_storage_location_alloc`
                    """
    data = db.query_sql(query_customer)
    return {(i.get("plant_code"), i.get("stor_loc_code")): i for i in data}


def get_db_mmd_material_basic_data():
    db = DbHelper()
    query_customer = f"""
                     select * from `t_mmd_material_basic_data`
                    """
    data = db.query_sql(query_customer)
    return {i.get("mat_code"): i for i in data}


def get_db_mmd_material_cost_data():
    db = DbHelper()
    query_customer = f"""
                     select * from `t_mmd_material_cost_data`
                    """
    data = db.query_sql(query_customer)
    return {(i.get("mat_code"), i.get("plant_code")): i for i in data}
