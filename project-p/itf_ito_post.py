"""
@File    : itf_ito_post.py
@Author  : jing.deng@dxdstech.com
@Date    : 2025/09/12 11:08
@explain : 公司间调拨单过账
"""
import copy
import sys
import uuid
from datetime import datetime

from DbHelper import DbHelper
from libenhance import Request, Response, SysHandler
from Z_generate_batch_sn import get_batch_sn_info


def completely_remove_module(module_name):
    """删除模块"""
    if module_name in globals():
        del globals()[module_name]
        print(f"从全局命名空间删除: {module_name}")
    # 2. 从 sys.modules 删除缓存
    if module_name in sys.modules:
        del sys.modules[module_name]
        print(f"从 sys.modules 删除: {module_name}")
    # 3. 强制垃圾回收
    import gc
    gc.collect()
    print(f"垃圾回收完成")
# ito_post(payload,user_id) 主程序

def up_log(dict_log, end_status):
    # 更新日志表
    update_log = []
    print(dict_log)
    
    status_log = 0
    update_status = 0
    db = DbHelper()
    ito_sn = dict_log['uf_ito_sn']
    guid = dict_log['uf_guid']
    # dict_log['uf_msg'] = dict_log['uf_msg'][0:250]
    ito_log = db.query_sql(
        "select * from ut_ito_post_step_log where uf_ito_sn = '{}' and uf_guid = '{}' ".format(ito_sn, guid))
    if ito_log:
        dict_log['id'] = ito_log[0]['id']
        update_status  = 1
    update_log.append(dict_log)
    if update_status == 0:
        status_log = db.batchInsertToDB('ut_ito_post_step_log', update_log)
        db.dbCommit()
    else:
        status_log = db.batchUpdateToDB('ut_ito_post_step_log', update_log)
        db.dbCommit()

    # end_status == 1 代表过账执行完成 所有步骤都走完了    
    if end_status == 1:
        sql = "update ut_ito_post_Interface_head set uf_posting_status  = 'S' where uf_guid = '{}'  ".format(guid)  
        db.exec_sql(sql)  
        db.dbCommit()


# 公司间采购订单入参处理
def po_param(ito_head, ito_item, ito_data,ito_price):

    error = ''
    db = DbHelper()
    head = ito_head[0]
    po_head = {}
    po_item = []
    # print("poito_data",ito_data)
    copy_ito_data = copy.deepcopy(ito_data)

    po_head['po_type'] = 'Z008'
    po_head['company_code'] = head['uf_to_company_code']
    po_head['purchase_organization'] = head['uf_purchase_organization']
    po_head['pur_group'] = head['uf_pur_group']
    po_head['vendor_code'] = head['uf_vendor_code']
    # po_head['contact_person'] =
    po_head['currency_code'] = head['uf_trade_currency']
    po_head['exchange_rate'] = head['uf_exchange_rate']
    # po_head['total_price_excluding_tax'] =
    # po_head['total_tax_amount'] =
    po_head['approval_status'] = 'E'
    po_head['statistics_item_1'] = head['uf_ito_sn']

    # 获取当前日期
    current_date = datetime.now().date()
    # 将日期格式化为 yyyy-mm-dd
    now_date = current_date.strftime('%Y-%m-%d')

    qty = 0
    dict_i = {}
    for row in ito_item:
        key = str(row['uf_ipn'])
        if key in dict_i:
            pass
        else:
            dict_i[key] = {}
            dict_i[key] = row

    dict_p = {}
    uf_cost_price_type = ''
    for row in ito_price:
        key = str(row['uf_ito_items']) + str(row['uf_ipn']) + str(row['uf_valuation_type'])
        if key in dict_i:
            pass
        else:
            dict_p[key] = {}
            dict_p[key] = row
        uf_cost_price_type  = row['uf_cost_price_type']
    # 按传进来的物料生成对应的采购订单行
    dict_m = {}
    mat_set = set()
    for each in copy_ito_data:
        each['uf_qty'] = float(each['uf_qty'])
        if each.get('uf_ipn','') != '':
            each['uf_mat_code'] = each['uf_ipn']
        mat_set.add(each['uf_mat_code'])

        batch_type_data = db.query_sql("select batch_type from t_batch_number where mat_code = '{}' and batch_sn = '{}' ".format(each['uf_mat_code'],each['uf_batch_sn']))
        batch_type = ''
        if batch_type_data:
            batch_type = batch_type_data[0]['batch_type']

        key = str(each['uf_mat_code']) + str(batch_type)

        keyd = str(each['uf_mat_code'])  

        if keyd in dict_i:
            each['uf_transaction_uom'] = dict_i[keyd]['uf_transaction_uom']
            each['uf_price_unit'] = dict_i[keyd]['uf_price_unit']
            each['uf_trading_price'] = dict_i[keyd]['uf_trading_price']
            each['uf_tax_code'] = dict_i[keyd]['uf_tax_code']
            each['uf_tax_rate'] = dict_i[keyd]['uf_tax_rate']

        key1 = str(each['uf_ito_items']) + str(each['uf_mat_code']) + str(batch_type)
        if uf_cost_price_type == 'B':
            key1 = str(each['uf_ito_items']) + str(each['uf_mat_code']) + ''

        each['statistics_item_1'] =  ''
        each['statistics_item_2'] = batch_type
        if key1 in dict_p:
            # if batch_type == dict_p[key1]['uf_valuation_type']:
            #     pass
            each['statistics_item_1'] = dict_p[key1]['uf_ito_items']
            # each['statistics_item_2'] = dict_p[key1]['uf_valuation_type']

            each['uf_price_unit'] = dict_p[key1]['uf_price_unit']
            each['uf_trading_price'] = dict_p[key1]['uf_standard_price']
            each['uf_transaction_float'] = dict_p[key1]['uf_transaction_float']
        else:
            error += f"采购订单创建无法匹配到调拨单价格" + str(each['uf_ito_items']) + '/' + str(each['uf_mat_code'])+ '/' + str(batch_type) + ','
        if key in dict_m:
            dict_m[key]['uf_qty'] += each['uf_qty']
            dict_m[key]['uf_parallel_qty'] += each['uf_parallel_qty']
            
        else:
            dict_m[key] = {}
            dict_m[key] = each
    # print(dict_i)

    # print('222',ito_price)

    mat_lst = list(mat_set)

    
    desc_data = db.query_sql(
        "select mat_code,mat_description,mat_group from t_mmd_material_basic_data where mat_code in ({})".format(
            ','.join([f"'{i}'" for i in mat_lst])))

    dic_des = {}
    for row in desc_data:
        key = str(row['mat_code'])
        if key in dic_des:
            pass
        else:
            dic_des[key] = ''
            dic_des[key] = row  

    po_items_num = 0
    for k, value in dict_m.items():
        print(dict_m,'dict_m-------')
        po_items_num += 10
        key1 = value['uf_mat_code']
        if key1 in dict_i:
            ito_row = dict_i[key1]
        # ito_row = ito_item[0]
        dict_item = {}
        dict_item['po_items'] = po_items_num
        dict_item['mat_code'] = value['uf_mat_code']
        if key in dic_des:
            dict_item['mat_description'] = dic_des[key]['mat_description']
            dict_item['mat_group'] = dic_des[key]['mat_group']
        dict_item['plant_code'] = head['uf_to_plant_code']
        dict_item['pur_item_cat'] = 'M'
        dict_item['account_allocation_category'] = ''
        

        dict_item['order_qty'] = value['uf_qty']
        dict_item['parallel_qty'] = value['uf_parallel_qty']
        dict_item['basic_qty'] = value['uf_qty']
        

        dict_item['pur_uom'] = value['uf_transaction_uom']
        dict_item['pricing_unit_of_measure'] = value['uf_transaction_uom']
        dict_item['price_unit'] = value['uf_price_unit']
        dict_item['first_delivery_date'] = now_date
        dict_item['last_delivery_date'] = now_date
        dict_item['first_batch_demand_date'] = now_date
        dict_item['last_batch_demand_date'] = now_date

        dict_item['statistics_item_1'] = value['statistics_item_1']
        dict_item['statistics_item_2'] = value['statistics_item_2']
        # dict_item['pricing_unit_quantity'] = 1
        dict_item['pricing_date'] = now_date

        dict_item['prices'] = [
            {"price_id": 1, "price_condition": "ZPI1",
             "amount": value['uf_trading_price'],
             "tax_code": value['uf_tax_code'],
             "tax_rate": value['uf_tax_rate'],
             "pricing_unit_of_measure": value['uf_transaction_uom'],
             "currency_code": head['uf_trade_currency'],
             "price_unit": value['uf_price_unit']},
            {"price_id": 2, "price_condition": "Z001",
             "amount": value.get('uf_transaction_float',0),
             "tax_code": value['uf_tax_code'],
             "tax_rate": value['uf_tax_rate'],
             "currency_code": head['uf_trade_currency'],
             "pricing_unit_of_measure": value['uf_transaction_uom'], "price_unit": value['uf_price_unit']}

        ]
        if head['uf_ito_type'] == 'ITO':
            dict_item['return_flag'] = 0
        elif head['uf_ito_type'] == 'RTO':
            dict_item['return_flag'] = 1
            po_head['remarks_1'] = '01'

        po_item.append(dict_item)
    po_data = {
        "po_head": po_head,
        "po_items": po_item
    }
    print("ito_data",ito_data)
    return po_data,error


# 公司间交货单入参处理
def dn_param(so_sn,stor_loc_code,uf_document_date, user_id):
    db = DbHelper()
    sql = """
     select
"" as message,
"" as execute_result,
"" as dn_sn,
"" as dn_item,
"" as credit_status,
sh.approval_status,
sh.credit_control_code,
CONCAT( sh.approval_status, "-", so_ste.so_approval_status_description ) AS approval_state,
si.so_sn,
si.so_items,
sh.company_code,
sh.sales_order_type,
st.sales_order_type_description,
cpn.company_description,
sh.distribution_channel_code,
cn.distribution_channel_description,
mmdb.prod_group,
pg.product_group_description as prod_group_name,
sh.remarks as sh_remarks,
sh.customer_code as sp_code,
sh.customer_code,
bpc.customer_description as sp_name,
bpc.customer_short_name as sp_short_name,
# dp.business_partner_code as dp_code,
sh.customer_code as dp_code,
dp.business_partner_name as dp_name,
dp.business_partner_addr as dp_addr,
dp.business_partner_short_name as dp_short_name,
dp.contact_person as dp_cont,
dp.contact_number as dp_numb,
ed.business_partner_code as ed_code,
ed.business_partner_name as ed_name,
ed.business_partner_short_name as ed_short_name,
si.mat_code,
si.mat_code as ipn,
si.mat_description,
sh.sales_org_code,
sh.customer_order,
org.sales_organization_description,
si.plant_code,
plt.plant_description,
si.order_qty,
si.sales_uom as transaction_uom,
si.quantity_of_delivery_order_created,
si.order_qty - si.quantity_of_delivery_order_created as undelivered_qty,
si.order_qty - si.quantity_of_delivery_order_created as planned_delivery_quantity,
"" as available_stock_quantity,
si.estimated_delivery_date,
"" as stor_loc_code,
"" as stor_loc_desc,
si.incoterms_code,
si.incoterm_position,
si.cust_mat_code,
si.cust_mat_code_description,
si.pod_related,
si.posted_pod_qty,
si.pod_status,
si.movement_type,
si.movement_type_it,
si.special_inventory_status1,
si.wbs_elements,
si.cost_center,
si.profit_center,
tdna.dn_type as dn_type,
si.related_to_delivery,
si.related_to_invoices,
si.sales_item_category,
IF(si.related_to_invoices = "C", "D", "A") as invocing_status,
"" as IPN_code,
"" as IPN_desc,
"" as basic_qty,
mmd.basic_uom,
"" as cost_quantity,
"" as dn_additional_list,
cost.cost_uom,
si.request_delivery_date,
si.request_delivery_date as PC_request_delivery_date,
sh.create_id,
sh.create_time,
"" as actual_plant,
si.partial_delivery_enabled,
si.related_to_qty,
si.parallel_uom,
si.parallel_qty,
si.parallel_qty as plan_delivery_qty_parallel_uom,
si.overdelivery_tolerance,
si.underdelivery_tolerance,
cs.unlimited_tolerance as unlimited_tolerance_flag
from
t_sales_order_header as sh
LEFT JOIN t_sales_order_item as si ON sh.so_sn = si.so_sn
left join t_dn_type_alloc as tdna on tdna.sales_order_type = sh.sales_order_type 
and tdna.sales_item_category = si.sales_item_category
and tdna.is_default = 1
LEFT JOIN t_so_type as st ON sh.sales_order_type = st.sales_order_type
LEFT JOIN t_bpc_customer_basic_data as bpc ON sh.customer_code = bpc.customer_code
LEFT JOIN t_documents_business_partner as dp ON si.so_sn = dp.doc_sn and si.so_items = dp.doc_items and dp.business_partner_type = 'DP'
LEFT JOIN t_documents_business_partner as ed ON si.so_sn = ed.doc_sn and si.so_items = ed.doc_items and ed.business_partner_type = 'EC'
LEFT JOIN t_os_distribution_channel as cn using(distribution_channel_code)
LEFT JOIN t_os_sales_org as org on sh.sales_org_code = org.sales_org_code
LEFT JOIN t_os_plant as plt on si.plant_code = plt.plant_code
LEFT JOIN t_os_company as cpn on sh.company_code = cpn.company_code
LEFT JOIN (select mat_code, basic_uom from t_mmd_material_basic_data) as mmd on si.mat_code = mmd.mat_code
LEFT JOIN (select mat_code, plant_code, cost_uom from t_mmd_material_cost_data) as cost on si.mat_code = cost.mat_code and si.plant_code = cost.plant_code
LEFT JOIN t_so_approval_status AS so_ste ON sh.approval_status = so_ste.so_approval_status
LEFT JOIN t_customer_sales_data as cs ON sh.customer_code = cs.customer_code and sh.sales_org_code = cs.sales_org_code
LEFT JOIN t_mmd_material_basic_data as mmdb ON si.mat_code = mmdb.mat_code
LEFT JOIN t_mmd_product_group as pg ON mmdb.prod_group = pg.prod_group
where sh.so_sn in ('{}')
group by si.so_sn, si.so_items
order by sh.create_time, si.so_items
""".format(so_sn)

    so_data = db.query_sql(sql)
    print('交货单查询结果', so_data)

    import pandas as pd
    from OperateSalesDeliveryNote import assemble_header_item
    df = pd.DataFrame(so_data)
    base_group_list = ['company_code', 'distribution_channel_code', 'sp_code',
                       'dp_code', 'dp_name', 'dp_cont', 'dp_numb']

    base_group_list.append('dn_type')
    grouped = df.groupby(base_group_list)

    group_dicts = {key: group.to_dict('records') for key, group in grouped}
    data = assemble_header_item(group_dicts, user_id, 2)
    print('交货单组装结果-----', data)
    for row in data:
        row['uf_is_update_order_qty'] = 0
        row['uf_is_merge_push_mail'] = 0
        row['PC_request_delivery_date'] = uf_document_date
        row['create_id'] = user_id
        row['uf_is_declare'] = 'N'
        
        for each in row['items']:
            each['uf_is_update_order_qty'] = 0
            each['uf_is_merge_push_mail'] = 0
            each['dn_additional_properties'] = ''
            each['uf_is_integer'] = ''
            each['ipn'] = each['mat_code']
            each['stor_loc_code'] = stor_loc_code
            each['create_id'] = user_id
            each['uf_is_declare'] = 'N'
            
    return data


# print(dn_param('5200000016','', 1))


def doc_param(po_sn, so_sn, ito_data, ito_head, ito_item,ito_price):
    msg = ''
    db = DbHelper()
    po_head = db.query_sql(f"select * from t_po_header where po_sn = '{po_sn}' ")
    po_item = db.query_sql(f"select * from t_po_item where po_sn = '{po_sn}' ")

    # 采购收货批次确定
    # from Z_generate_batch_number import generate_batch_number

    # 获取当前日期
    current_date = datetime.now().date()
    # 将日期格式化为 yyyy-mm-dd
    now_date = current_date.strftime('%Y-%m-%d')

    dic_po_head = po_head[0]
    head = {}
    item = []
    # 单据种类
    head['document_category'] = ''
    # 过账代码
    head['post_code'] = '1'
    # 凭证日期
    head['document_date'] = now_date
    # 过账日期
    head['posting_date'] = ito_data[0]['uf_posting_date']
    # 公司代码
    head['company_code'] = dic_po_head['company_code']
    head['remarks_1'] = ''

    uf_cost_price_type = ''
    for row in ito_price:
        uf_cost_price_type  = row['uf_cost_price_type']

    dict_m = {}
    mat_set = set()
    batch_wher = ''
    for row in ito_data:
        if row.get('uf_ipn','') != '':
            row['uf_mat_code'] = row['uf_ipn']
        
        batch_type_data = db.query_sql("select batch_type from t_batch_number where mat_code = '{}' and batch_sn = '{}' ".format(row['uf_mat_code'],row['uf_batch_sn']))
        batch_type = ''
        if batch_type_data:
            batch_type = batch_type_data[0]['batch_type']
        # if uf_cost_price_type == 'B':
        #     batch_type = ''
        row['batch_type'] = batch_type
        if ito_head[0]['uf_from_plant_code'] == '1100' and ito_head[0]['uf_to_plant_code'] == '1000':
            if batch_wher == '':
                batch_wher += f"""  ( mat_code = "{row['uf_mat_code']}" and batch_sn = "{row['uf_batch_sn']}" ) """
            else:
                pass    
                batch_wher += f""" or ( mat_code = "{row['uf_mat_code']}" and batch_sn = "{row['uf_batch_sn']}" ) """

        key = str(row['uf_mat_code']) + str(row['batch_type'])
        if key in dict_m:
            dict_m[key].append(row)
        else:
            dict_m[key] = []
            dict_m[key].append(row)

    # 获取收货批次---------
    dict_batch = {}  
    if batch_wher != '':
        pass
        sql_batch = f"""
        select * from t_batch_number
        where uf_ZT26  = '转口' and  ({batch_wher})
        """
        batch_data = db.query_sql(sql_batch) 
        batch_match = []
        for ele in batch_data:
            dict_match = {}
            dict_match = copy.deepcopy(ele)
            dict_match['uf_ZT26'] = ''
            dict_match["key"] = str(dict_match["mat_code"]) + str(dict_match["batch_sn"])
            del dict_match["batch_sn"]  
            del dict_match["create_id"] 
            del dict_match["update_id"] 
            del dict_match["create_time"] 
            del dict_match["update_time"] 
            del dict_match["id"] 
            batch_match.append(dict_match)

        print('匹配批次',batch_match)
        from Z_generate_batch_number import generate_batch_number
        return_code, return_msg, return_data = generate_batch_number(batch_match)
        if return_code != 200:
            msg = return_msg
            return head, item,msg
        dict_batch = {}  
        for row in return_data:
            key = row['key']
            if key in  dict_batch:
                pass
            else:
                dict_batch[key] = {}
                dict_batch[key] = row   
        print(return_data)          
    # 获取收货批次---------

    dic_ito = {}
    no_batch_sn = ''
    for row in ito_item:
        if row['uf_batch_sn'] == '':
            no_batch_sn = 'X'
            key = str(row['uf_ipn'])
        else:
            pass
            key = str(row['uf_ipn']) + str(row['uf_batch_sn'])
        if key in dic_ito:
            pass
        else:
            dic_ito[key] = {}
            dic_ito[key] = row
    print('sd=',dic_ito)
    print(dict_m)
    line = 0

    head333 = ito_head[0]
    movement_type = ''
    if head333['uf_ito_type'] == 'ITO':
        movement_type = 'R001'
    elif head333['uf_ito_type'] == 'RTO':
        movement_type = 'R002'
    
    for each in po_item:
        line += 1
        doc_item = {}
        doc_item['line_id'] = line
        doc_item['movement_type'] = movement_type
        doc_item['plant_code'] = each['plant_code']
        doc_item['special_inventory_status1'] = ''
        doc_item['special_inventory_status2'] = ''
        doc_item['inventory_status'] = '0'
        doc_item['mat_code'] = each['mat_code']

        doc_item['transaction_uom'] = each['pur_uom']
        doc_item['rel_po_sn'] = each['po_sn']
        doc_item['rel_po_items'] = each['po_items']

        doc_item['transaction_currency'] = ''
        doc_item['parallel_qty'] = 0
        doc_item['parallel_uom'] = ''
        doc_item['batch_number'] = {}
        doc_item['basic_qty'] = each['basic_qty']

        key1 = str(each['mat_code']) + str(each['statistics_item_2'])
        
        print(key1)
        if key1 in dict_m:
            for each_r in dict_m[key1]:
                key_batch = str(each['mat_code']) + str(each_r['uf_batch_sn'])
                doc_item['batch_sn'] = each_r['uf_batch_sn']
                if key_batch in dict_batch:
                    pass
                    doc_item['batch_sn'] = dict_batch[key_batch]['batch_sn']

                if no_batch_sn == '':
                    key = str(each_r['uf_mat_code']) + str(each_r['uf_batch_sn'])
                else:
                    key = str(each_r['uf_mat_code'])
                print('sd=',key)    
                if key in dic_ito:
                    doc_item['stor_loc_code'] = dic_ito[key]['uf_to_stor_loc_code']
                    doc_item['parallel_uom'] = dic_ito[key]['uf_parallel_uom']
                doc_item['transaction_qty'] = float(each_r['uf_qty'])
                doc_item['basic_qty'] = float(each_r['uf_qty'])
                doc_item['parallel_qty'] = float(each_r['uf_parallel_qty'])
                # doc_item['parallel_uom'] = each_r['uf_parallel_uom']
          
                temp_doc = copy.deepcopy(doc_item)
                item.append(temp_doc)
                # break
    # print(item)            
    return head, item,msg

def get_batch_sn(row,box_mark,ito_sn):
    # 批次匹配逻辑
    db = DbHelper()
    uf_ZT05 = ''
    if row['uf_ZT05'] != '':
        sql = """
        select mat_group  from t_mmd_material_basic_data where mat_code = '{}'
        """.format(row['uf_mat_code'])
        data = db.query_sql(sql)
        if data:
            if data[0]["mat_group"] == '1002':
                uf_ZT05 = 'uf_ZT55'
            if data[0]["mat_group"] == '1003':
                uf_ZT05 = 'uf_ZT56'
            if data[0]["mat_group"] == '1004':
                uf_ZT05 = 'uf_ZT55'
            if data[0]["mat_group"] == '2001':
                uf_ZT05 = 'uf_ZT25'
            if data[0]["mat_group"] == '2002':
                uf_ZT05 = 'uf_ZT59'
            if data[0]["mat_group"] == '2003':
                uf_ZT05 = 'uf_ZT60'
    where_sql = " (a.uf_quality_type = '' or a.uf_quality_type = 'run' ) and  a.mat_code = '{}' ".format(row['uf_mat_code'])

    po_mat = " and a.component_code = '{}' ".format(row['uf_mat_code'])
    dn_mat = " and  a.mat_code = '{}' ".format(row['uf_mat_code'])
    res_mat = "  and mat_code = '{}' ".format(row['uf_mat_code'])
    ito_mat = " and  t.uf_ipn = '{}' ".format(row['uf_mat_code'])

    field_lst = ["uf_runcard","uf_box_no","uf_lot_no","uf_ZT07","uf_ZT18","uf_stor_loc_code"] 
    if box_mark == 'X':
        field_lst = ["uf_runcard","uf_lot_no","uf_ZT07","uf_ZT18","uf_stor_loc_code"]
    #     field_lst = ["uf_production_date","uf_runcard","uf_lot_no","uf_wafer_id","uf_ZT04",
    # "uf_ZT07","uf_ZT18","uf_stor_loc_code"]
    # ["uf_production_date","uf_runcard","uf_box_no","uf_lot_no","uf_wafer_id","uf_ZT04","uf_ZT05","uf_ZT06",
    # "uf_ZT07","uf_ZT08","uf_ZT09","uf_ZT14","uf_ZT15","uf_ZT17","uf_ZT18","uf_ZT20","uf_ZT21","uf_ZT35","uf_ZT36","uf_ZT37",
    # "uf_ZT38","uf_ZT48","uf_ZT49","uf_ZT50","uf_ZT51","uf_ZT53","uf_ZT54","uf_stor_loc_code"]  
    for key,value in row.items():
        if key in field_lst:
            field = key
            if key == 'uf_production_date':
                field = 'receive_date'
            if key == 'uf_ZT05':
                if uf_ZT05 != '':
                    field = uf_ZT05
                else:
                    continue    
            if key == 'uf_lot_no':
                field = 'lot_no'
            if key == 'uf_wafer_id':
                field = 'wafer_id'
            if key == 'uf_stor_loc_code':
                field = 't1.stor_loc_code'
            if value != '':
                pass    
                where_sql += f" and  {field} = '{value}' "
    sql = f"""
    select a.batch_sn,a.mat_code,
     t1.basic_uom,
    t1.basic_qty,
    t1.cost_uom,
    t1.cost_qty,
    t1.parallel_uom,
    t1.parallel_qty,
    po.allocated_qty,
    po.allocated_parallel_qty,

    dn.picked_base_qty,
    dn.picked_parallel_qty,
    
    res.basic_qty as res_qty,
    res.parallel_qty as res_parallel_qty,

    ito.ito_qty,
    ito.ito_parallel_qty,

    a.receive_date
      from t_batch_number as a
    left join ( SELECT 
                V.id,V.mat_code,V.plant_code,V.year,V.period, 
                V.stor_loc_code,V.batch_sn,V.basic_uom,V.basic_qty,V.cost_uom, 							
                V.cost_qty,V.special_inventory_status1,V.special_inventory_status2,
                V.so_sn,V.so_items,V.vendor_code,V.customer_code,V.wbs_elements,V.po_sn,V.po_items, 				  
				V.create_id,V.update_id,V.create_time,V.update_time,note,V.parallel_uom,V.parallel_qty,V.inventory_status
                FROM t_inventory_batch_data AS V 
		        INNER JOIN (SELECT year,period,plant_code FROM t_bd_material_period as c
                JOIN t_os_company_plant_alloc as c1 on c.company_code = c1.company_code
                where c.period_key = 'ML' AND c.period_status = 1 ) AS V1
		        ON V.plant_code = V1.plant_code and V.year = V1.year
		        and V.period = V1.period where V.inventory_status = 0 and  V.special_inventory_status2 != 'T' ) as t1
                on a.mat_code = t1.mat_code
                and  a.batch_sn = t1.batch_sn 

        left join (select a.component_code,a.plant_code,a.stor_loc_code,a.batch_sn,
                sum(a.allocated_qty  - a.deducted_quantity_base) as allocated_qty,
                sum(a.allocated_parallel_qty  - a.deducted_quantity_parallel) as allocated_parallel_qty
                from t_po_batch_binding  as a
                LEFT JOIN t_po_item as b on a.po_sn  = b.po_sn and a.po_items = b.po_items
                where a.batch_occupy_flag = 1 and a.issuing_flag != 1 and a.deleted_mark != 1 and b.deleted_mark != 1 {po_mat}
                GROUP BY  a.component_code,a.plant_code,a.stor_loc_code,a.batch_sn) as po
        on t1.mat_code = po.component_code 
        and t1.plant_code = po.plant_code 
        and t1.stor_loc_code = po.stor_loc_code 
        and t1.batch_sn = po.batch_sn 
        
  left join (select a.mat_code,if(a.actual_plant != '',a.actual_plant,d.plant_code) as  actual_plant,if(a.actual_stor != '',a.actual_stor,a.stor_loc_code ) as actual_stor,a.batch_sn,
    sum(a.picked_base_qty) as picked_base_qty,
    sum(a.picked_parallel_qty) as picked_parallel_qty 
    from t_dn_inventory_alloc as a 
    left join t_dn_item as d on d.dn_sn = a.dn_sn and d.dn_item = a.dn_item
    JOIN t_dn_header as h on a.dn_sn = h.dn_sn
    JOIN t_dn_type as t on h.dn_type = t.dn_type
    where t.batch_occupy_flag = 1 and h.posting_status = 'A' {dn_mat}
    GROUP BY  mat_code,actual_plant,actual_stor,batch_sn) as dn
  on t1.mat_code = dn.mat_code 
  and t1.plant_code = dn.actual_plant 
  and t1.stor_loc_code = dn.actual_stor 
  and t1.batch_sn = dn.batch_sn 

        left join (select mat_code,plant_code,stor_loc_code,batch_sn,
                sum( basic_qty - issued_qty_base_uom ) as basic_qty, 
                sum( parallel_qty - issued_qty_parallel_uom ) as parallel_qty 
                from t_res_item  
                where batch_occupy_flag = 1 and close_flag = 0 and deleted_mark = 0 {res_mat}
                GROUP BY  mat_code,plant_code,stor_loc_code,batch_sn) as res
        on t1.mat_code = res.mat_code 
        and t1.plant_code = res.plant_code 
        and t1.stor_loc_code = res.stor_loc_code 
        and t1.batch_sn = res.batch_sn 

        left join (
        select  t.uf_ipn as mat_code,h.uf_from_plant_code as plant_code ,t.uf_from_stor_loc_code as stor_loc_code,uf_batch_sn as batch_sn,
            sum(t.uf_transaction_qty) as ito_qty,
            sum(t.uf_parallel_qty) as ito_parallel_qty  
            from ut_intercompany_transaction_order_item as t
            left join ut_Intercompany_transaction_order_head as h on h.uf_ito_sn = t.uf_ito_sn
            left join ut_ito_post_step_log as l on l.uf_ito_sn = t.uf_ito_sn and l.uf_reversal_mark = 0
            where uf_batch_sn != '' and t.uf_deleted_mark != 1 and l.uf_guid IS NULL {ito_mat} and t.uf_ito_sn != '{ito_sn}'
            group by  t.uf_ipn,h.uf_from_plant_code ,t.uf_from_stor_loc_code,uf_batch_sn
        ) as ito 
        on t1.mat_code = ito.mat_code 
        and t1.plant_code = ito.plant_code 
        and t1.stor_loc_code = ito.stor_loc_code 
        and t1.batch_sn = ito.batch_sn 
    where {where_sql} order by receive_date asc , a.batch_sn asc
    """
    
    data = db.query_sql(sql)
    print(sql,data)
    for i in data:
        i['basic_qty'] = i['basic_qty'] - (i['allocated_qty'] + i['picked_base_qty'] +  i['res_qty']  +  i['ito_qty'])
        i['parallel_qty'] = i['parallel_qty'] - (i['allocated_parallel_qty'] + i['picked_parallel_qty'] +  i['res_parallel_qty']   +  i['ito_parallel_qty'] )
    print(data,'data======')
    output = []
    output = [ i for i in data if i['basic_qty'] > 0 ]
    print(len(output),output)
    return output




def ito_post(payload, user_id):
    """
    :param payload:
           结构如下:
           {'payload': 'data': [{'uf_ito_sn': '123444', 'uf_ito_items': '','posting_date':'',
                                'posting_time':'','sf':'',
                                'stor_loc_code':'','qty':11,'mat_code':"",'batch_sn':''},
           {}]

    :return:
           结构如下: {'type':'','message':''}
    """
    # ===================== 【新增：文件传参 List → 标准接口结构】=====================
    if isinstance(payload, list):
        print(payload, '==== 这是文件传参，开始自动转换结构')
        # 按 uf_ito_sn 分组
        item_group = {}
        for item in payload:
            ito_sn = item.get('uf_ito_sn', '')
            if not ito_sn:
                continue
            if ito_sn not in item_group:
                item_group[ito_sn] = []
            item_group[ito_sn].append(item)

        # 生成最终标准结构
        converted_payloads = []
        for ito_sn, items in item_group.items():
            # 每个交货单生成独立 GUID
            guid = str(uuid.uuid4())
            now = datetime.now()
            posting_date = ""
            posting_time = ""
            processed_items = []
            # 行号从 1 开始自增
            line_id = 1
            for row in items:
                # 复制一份，避免修改原数据
                new_row = row.copy()
                new_row['uf_batch_sn'] = ''
                new_row['uf_ZT05'] = ''
                # 1. 生成自增 line_id
                new_row['line_id'] = line_id
                line_id += 1
                # 2. 处理 uf_mat_code：使用 uf_ipn 的值
                new_row['uf_mat_code'] = new_row.get('uf_ipn', '')
                # 自动取 chip_qty 或 wafer_qty
                chip_qty = str(new_row.get('uf_chip_qty', '')).strip()
                wafer_qty = str(new_row.get('uf_wafer_qty', '')).strip()
                has_chip = bool(chip_qty)
                has_wafer = bool(wafer_qty)
                posting_date = new_row.get('uf_posting_date', '')
                if posting_date:
                    posting_date = posting_date[:10]
                posting_time = new_row.get('uf_posting_date', '')
                
                # ============== 错误带上 uf_ito_sn + uf_ito_items ==============
                item_no = new_row.get('uf_ito_items', '未知行')
                sn = new_row.get('uf_ito_sn', '未知单号')
                
                if not has_chip and not has_wafer:
                    return {
                        "type": "E",
                        "message": f"调拨单[{sn}] 行项目[{item_no}]：Chip Qty 和 Wafer Qty 不能同时为空"
                    }
                
                if has_chip and has_wafer:
                    return {
                        "type": "E",
                        "message": f"调拨单[{sn}] 行项目[{item_no}]：Chip Qty 和 Wafer Qty 不能同时有值"
                    }
                if chip_qty:
                    new_row['uf_qty'] = float(chip_qty)
                elif wafer_qty:
                    new_row['uf_qty'] = float(wafer_qty)
                else:
                    new_row['uf_qty'] = 0.0

                processed_items.append(new_row)
            new_data = {
                "guid": guid,
                "data": {
                    "header": [
                        {
                            "item": processed_items,
                            "uf_bs_category": "37",        # 固定值
                            "uf_guid": guid,
                            "uf_ito_sn": ito_sn,
                            "uf_posting_date": posting_date,
                            "uf_posting_time": posting_time,
                            "uf_tracking_number": ""
                        }
                    ]
                }
            }
            converted_payloads.append(new_data)
        print(converted_payloads,'converted_payloads===---')
        
        # ===================== 循环处理每个转换后的payload =====================
        result_list = []
        for p in converted_payloads:
            res = ito_post(p, user_id)
            result_list.append(res)
        print(result_list,'result_list========')
        
        if len(result_list) == 1:
            return result_list[0]
        else:
            # 合并多个结果
            all_messages = [r.get('message', '') for r in result_list]
            has_error = any(r.get('type') == 'E' for r in result_list)
            guids = [r.get('guid', '') for r in result_list]
            return {
                "type": "E" if has_error else "S",
                "message": "; ".join(all_messages),
                "guid": ",".join(guids)
            }
    print(payload,'payload======')
    
    # ===================== 原有逻辑：所有错误都带上 uf_ito_sn =====================
    guid = payload["guid"]
    data = payload.get("data")
    print(data, 'data====0')
    db = DbHelper()

    if data.get("header", '') == '':
        return {"type": "E", "message": '传入结构不存在header', "guid": guid}
    
    head = data.get("header")
    print(head, 'head====1')
    dict_head = head[0]
    print(dict_head, 'dict_head====1')
    
    # 提前取出单号，所有错误都带上
    uf_ito_sn = dict_head.get('uf_ito_sn', '未知单号')

    if dict_head.get('item', []) == []:
        return {
            "type": "E",
            "message": f"调拨单[{uf_ito_sn}]：传入结构不存在item调拨明细",
            "guid": guid
        }

    if uf_ito_sn == '':
        return {
            "type": "E",
            "message": f"调拨单[{uf_ito_sn}]：调拨单号不能传空",
            "guid": guid
        }

    if dict_head.get('uf_posting_date', '') == '':
        return {
            "type": "E",
            "message": f"调拨单[{uf_ito_sn}]：过账日期不能传空",
            "guid": guid
        }

    item = dict_head['item']
    print(item, 'item====2')
    
    for row in item:
        print(row,'row====3')
        item_no = row.get('uf_ito_items', '未知行')  # 行号
        row['uf_qty'] = float(row['uf_qty'])
        row['uf_ito_sn'] = uf_ito_sn
        row['uf_guid'] = dict_head['uf_guid']
        row['uf_line_id'] = row['line_id']
        row['uf_bs_category'] = dict_head['uf_bs_category']
        print(row,'row====4')
        
        # ============== 所有字段校验都带上 单号+行号 ==============
        if row.get('uf_stor_loc_code', '') == '':
            return {
                "type": "E",
                "message": f"调拨单[{uf_ito_sn}] 行[{item_no}]：库存地点不能传空",
                "guid": guid
            }
        if row.get('uf_mat_code', '') == '':
            return {
                "type": "E",
                "message": f"调拨单[{uf_ito_sn}] 行[{item_no}]：物料不能传空",
                "guid": guid
            }
        if row.get('uf_qty', 0) == 0:
            return {
                "type": "E",
                "message": f"调拨单[{uf_ito_sn}] 行[{item_no}]：调拨数量不能传0",
                "guid": guid
            }

    
    posting_date = dict_head.get('uf_posting_date', '')
    
    # com_data = db.query_sql(
    #     f""" select uf_from_company_code,uf_to_company_code from ut_Intercompany_transaction_order_head where uf_ito_sn = '{uf_ito_sn}' """)
    # print(com_data,f"""select uf_from_company_code,uf_to_company_code from ut_Intercompany_transaction_order_head where uf_ito_sn = '{uf_ito_sn}'""")
    
    f_company_code = ''
    t_company_code = ''
    # 新版检验直接从ut_delivery_post_Interface_data表中取数据


    # 销售公司代码 
    t_company_data = db.query_sql(
        f""" select company_code,so_sn from t_po_header where po_sn = '{uf_ito_sn}' """)

    if len(t_company_data) == 0:
        return {"type": "E", "message": f"调拨单[{uf_ito_sn}]：未找到对应销售订单", "guid": guid}
    t_company_code = t_company_data[0]['company_code']
    so_sn = t_company_data[0]['so_sn']


    # 采购公司代码 
    f_company_data = db.query_sql(
        f""" select company_code from t_sales_order_header where so_sn = '{so_sn}' """)
    if len(f_company_data) == 0:
        return {"type": "E", "message": f"调拨单[{uf_ito_sn}]：未找到对应采购订单", "guid": guid}
    f_company_code = f_company_data[0]['company_code']

    from DxCompanyPeriodUtil import check_material_period

    code, msg = check_material_period(f_company_code, posting_date)
    if code == 500:
        return {
            "type": "E",
            "message": f"调拨单[{uf_ito_sn}]：销售方公司代码{f_company_code}账期{posting_date}未开",
            "guid": guid
        }
    code, msg = check_material_period(t_company_code, posting_date)
    if code == 500:
        return {
            "type": "E",
            "message": f"调拨单[{uf_ito_sn}]：采购方公司代码{t_company_code}账期{posting_date}未开",
            "guid": guid
        }

    dict_head['uf_guid'] = guid
    sql = f"""
    SELECT b.uf_ito_sn,b.uf_ito_items,sum(uf_qty) as uf_qty FROM ut_ito_post_Interface_head as a
    LEFT JOIN ut_ito_post_Interface_data as b
    on a.uf_guid = b.uf_guid 
    where a.uf_reversal_mark != 1 
    and b.uf_ito_sn  = '{uf_ito_sn}'
    group by b.uf_ito_sn,b.uf_ito_items   
    """
    Interface_data = db.query_sql(sql)
    print(sql)
    
    ito_item = db.query_sql(
        """select * from ut_intercompany_transaction_order_item  where uf_ito_sn = '{}' """.format(uf_ito_sn))

    # post_data = db.query_sql(
    #     """select * from ut_ito_post_step_log  where uf_ito_sn = '{}' and uf_reversal_mark != 1 """.format(uf_ito_sn))

    dici_now = {}
    for i in item:
        key = str(i['uf_ito_items'])
        dici_now[key] = dici_now.get(key, 0) + i['uf_qty']

    # 可调拨数量
    dict_i = {}
    for i in ito_item:
        key = str(i['uf_ito_items'])
        dict_i[key] = i.get('uf_transaction_qty', 0)

    # 已调拨数量
    dict_y = {}
    for i in Interface_data:
        key = str(i['uf_ito_items'])
        dict_y[key] = i.get('uf_qty', 0)

    error = ''
    msg = ''
    if error == 'x':
        print(msg,guid,'------------------------')
        response = {
            "type": "E",
            "message": msg,
            "guid": guid
        }
        return response
    else:
        msg_lst = ''
        item_temp = []
        dict_inv = {}
        output = []
        uf_batch_line = 0
        
        field_attr_data = db.query_sql(f""" SELECT 
            MAX(CASE WHEN uf_field_code = 'wafer_id' THEN uf_field_value END) AS wafer_id,
            MAX(CASE WHEN uf_field_code = 'uf_runcard' THEN uf_field_value END) AS uf_runcard,
            MAX(CASE WHEN uf_field_code = 'uf_ZT07' THEN uf_field_value END) AS uf_ZT07,
            MAX(CASE WHEN uf_field_code = 'uf_ZT18' THEN uf_field_value END) AS uf_ZT18,
            MAX(CASE WHEN uf_field_code = 'uf_box_no' THEN uf_field_value END) AS uf_box_no
            FROM ut_initial_attribute_field
            where uf_field_code  in ('wafer_id','uf_runcard','uf_box_no') """)
        
        wafer_id = ''
        uf_runcard = ''
        uf_box_no = ''
        uf_ZT07 = ''
        uf_ZT18 = ''
        
        if field_attr_data:
            wafer_id = field_attr_data[0]['wafer_id']
            uf_runcard = field_attr_data[0]['uf_runcard']
            uf_box_no = field_attr_data[0]['uf_box_no']
            uf_ZT18 = field_attr_data[0]['uf_ZT18']
            uf_ZT07 = field_attr_data[0]['uf_ZT07']
        # ===================== 【修改点：替换批次查询逻辑】=====================
        # 收集需要查询批次的行
        rows_need_batch = []
        for idx, row in enumerate(item):
            if row.get('uf_batch_sn', '') == '':
                rows_need_batch.append({
                    'index': idx,
                    'row': row
                })
        
        # 如果有需要查询批次的行，批量调用新接口
        if rows_need_batch:
            # 构建批量查询的 datalist
            datalist = []
            for need in rows_need_batch:
                row = need['row']
                item_no = row.get('uf_ito_items', '未知行')
                
                # 构建查询参数
                query_data = {
                    "mat_code": row.get('uf_mat_code', ''),
                    "count": float(row.get('uf_qty', 0)),
                    "uf_ZT04": row.get('uf_ZT04', ''),
                    "wafer_id": wafer_id,
                    "uf_ZT18": uf_ZT18,
                    "receive_date": row.get('receive_date', ''),
                    "uf_runcard": uf_runcard,
                    "uf_box_no": uf_box_no,
                    "uf_electroplating_date": row.get('uf_electroplating_date', '')
                }
                # 过滤空值，只传有值的字段
                query_data = {k: v for k, v in query_data.items() if v}
                datalist.append(query_data)
            
            # 调用新的批量批次查询接口
            batch_msg, batch_result = get_batch_sn_info(db, datalist)
            if batch_msg:
                # 批量查询整体失败
                return {
                    "type": "E",
                    "message": f"调拨单[{uf_ito_sn}]：批次查询失败 - {batch_msg}",
                    "guid": guid
                }
            
            # 处理每条数据的批次查询结果
            for need, query_result in zip(rows_need_batch, batch_result):
                idx = need['index']
                row = need['row']
                item_no = row.get('uf_ito_items', '未知行')
                
                batch_sn_info = query_result.get('batch_sn_info', [])
                batch_sn_info_msg = query_result.get('batch_sn_info_msg', '')
                
                if batch_sn_info_msg:
                    # 单条批次查询失败
                    msg_lst += f"调拨单[{uf_ito_sn}] 行[{item_no}]：{batch_sn_info_msg}；"
                    continue
                
                if not batch_sn_info:
                    msg_lst += f"调拨单[{uf_ito_sn}] 行[{item_no}]：匹配不到批次；"
                    continue
                
                # 如果有批次信息，按批次拆分数量
                qty = float(row['uf_qty'])
                for batch_item in batch_sn_info:
                    if qty <= 0:
                        break
                    batch_sn = batch_item.get('batch_sn', '')
                    batch_count = batch_item.get('count', 0)
                    
                    if batch_count <= 0:
                        continue
                    
                    if batch_count >= qty:
                        # 当前批次足够
                        output_d = copy.deepcopy(row)
                        output_d['uf_batch_sn'] = batch_sn
                        output_d['uf_qty'] = qty
                        uf_batch_line += 1
                        output_d['uf_batch_line'] = uf_batch_line
                        output.append(output_d)
                        qty = 0
                    else:
                        # 当前批次不足，继续下一个批次
                        output_d = copy.deepcopy(row)
                        output_d['uf_batch_sn'] = batch_sn
                        output_d['uf_qty'] = batch_count
                        uf_batch_line += 1
                        output_d['uf_batch_line'] = uf_batch_line
                        output.append(output_d)
                        qty -= batch_count
                
                if qty > 0:
                    msg_lst += f"调拨单[{uf_ito_sn}] 行[{item_no}]：批次库存数量短缺 {qty}；"
        
        # 处理已有批次号的行（不需要查询批次）
        for row in item:
            if row.get('uf_batch_sn', '') != '':
                output_d = copy.deepcopy(row)
                output.append(output_d)

        item = [i for i in output if i["uf_qty"] != 0]
        if msg_lst != '':
            return {
                "type": "E",
                "message": msg_lst,
                "guid": guid
            }
        
        for each in head:
            each['uf_guid'] = guid
        ito_sn = item[0]['uf_ito_sn']
        ito_data = []
        ito_pick = {}
        if ito_sn:
            pick_sql = """
            select * from ut_intercompany_transaction_order_item
        where uf_ito_sn  = '{}'  and uf_deleted_mark != 1  and uf_batch_sn != ''
            """.format(ito_sn)
            ito_data = db.query_sql(pick_sql)
            for i in ito_data:
                pass
                key = str(i['uf_ito_sn']) 
                if key in ito_pick:
                    ito_pick[key].append(i)
                else:
                    ito_pick[key] = []
                    ito_pick[key].append(i)
        prarm_item = []
        key = str(ito_sn)
        if key in ito_pick:
            pass
            for row in ito_pick[key]:
                dict_temp=row.copy()
                dict_temp['uf_posting_date'] = head[0]['uf_posting_date']
                dict_temp['uf_tracking_number'] = head[0]['uf_tracking_number']
                dict_temp['uf_stor_loc_code'] = dict_temp['uf_from_stor_loc_code']
                dict_temp['uf_qty'] = dict_temp['uf_transaction_qty']
                # temp['mat_code'] = temp['uf_mat_code']
                dict_temp['uf_mat_code'] = dict_temp['uf_ipn']
                dict_temp['batch_sn'] = dict_temp['uf_batch_sn']
                dict_temp['uf_batch_sn'] = dict_temp['uf_batch_sn']
                prarm_item.append(dict_temp)
        else:
            prarm_item = item
        ret = ito_post_main(prarm_item, guid, user_id)
        type_status = ret.get("type","")
        message = ret.get("message","")
        if type_status == 'E':
            return {
                "type": "E",
                "message": f"调拨单[{uf_ito_sn}]：{message}",
            }
    # 最终统一返回格式
    return {
        "type": "S",
        "message": "过账成功",
        "guid": guid
    }


def ito_post_main(ito_data, guid, user_id):
    print('itopostinput',ito_data, guid, user_id)
    # ito_data =  payload.get("data")
    ito_sn = ito_data[0]['uf_ito_sn']
    posting_date = ito_data[0]['uf_posting_date'] 
    uf_stor_loc_code = ito_data[0]['uf_stor_loc_code']

    db = DbHelper()
    # 获取调拨单数据
    # ito_head = db.query_sql(
    #     "select * from ut_Intercompany_transaction_order_head where uf_ito_sn = '{}' ".format(ito_sn))
    
    
    # 新版检验直接从ut_delivery_post_Interface_data表中取数据
    # ito_head = db.query_sql(
    #     "select * from ut_delivery_post_Interface_data where uf_dn_sn = '{}' ".format(ito_sn))
    # print('ito_head',ito_head)
    # if len(ito_head) == 0:
        # return {"type": "E", "message": f"调拨单[{ito_sn}]：未找到调拨单数据", "guid": guid}
    
    # ito_item = db.query_sql("""select a.*,b.mat_group from ut_intercompany_transaction_order_item as a
    #     left join t_mmd_material_basic_data as b on a.uf_mat_code = b.mat_code where a.uf_ito_sn = '{}' """.format(ito_sn))
    # ito_item = db.query_sql("""select a.*,b.mat_group from ut_delivery_post_Interface_data as a
    #     left join t_mmd_material_basic_data as b on a.uf_mat_code = b.mat_code where a.uf_dn_sn = '{}' """.format(ito_sn))
    # print('ito_item',ito_item)

    # ito_price = db.query_sql("""select * from ut_intercompany_transaction_order_price  where uf_ito_sn = '{}' """.format(ito_sn))
    # print('ito_price',ito_price)

    ito_log = db.query_sql(
        "select * from ut_ito_post_step_log where uf_ito_sn = '{}' and uf_guid = '{}' ".format(ito_sn, guid))
   
    ito_item =[{"uf_ito_items":uuid.uuid4(),"uf_parallel_qty":ito_data[0]['uf_chip_qty']}]

    # print('ito_price',ito_price)
    uf_document_date = posting_date

    step = 0
    update_status = 0
    if ito_log:
        # update_status = 1
        # 查看日志表，当前调拨单号执行进度
        dict_log = ito_log[0]
        if dict_log['uf_po_doc'] != '':
            step = 100
        if dict_log['uf_po_doc'] == '':
            step = 50
        if dict_log['uf_dn_doc'] == '':
            step = 40
        if dict_log['uf_picking_document'] == '':
            step = 30
        if dict_log['uf_dn_sn'] == '':
            step = 20
        if dict_log['uf_so_sn'] == '':
            step = 10
        if dict_log['uf_po_sn'] == '':
            step = 0
    else:
        dict_log = {}
        dict_log['uf_ito_sn'] = ito_sn
        dict_log['uf_guid'] = guid
        dict_log['uf_status'] = 'A'

    code = 500
    print(ito_log)
    print(step)
    if step == 100:
        code = 500
        msg = '该调拨已完成，不允许再次操作'
        # return code, msg, dict_log
        return {
        # "guid": guid,
        "type": 'E',
        "message": msg
    }

    msg = ''
    code = 0
    if step == 0:
        print('采购订单收货------22----', dict_log)
        ret = db.query_sql(
        "select po_sn,so_sn from t_po_header where po_sn = '{}' ".format(ito_sn))
        for item in ret:
            po_sn = item.get('po_sn','')
            so_sn = item.get('so_sn','')
            if po_sn != '' and so_sn != '':
                step = 20
                dict_log['uf_po_sn'] = po_sn
                dict_log['uf_so_sn'] = so_sn
                dict_log['uf_status'] = 'B'
                up_log(dict_log, update_status)
            else:
                dict_log['uf_po_sn'] == po_sn
                code = 500
                msg = '未找到对应销售订单'
    if step == 20:
        from DxSalesDeliveryOrder import db as sdo_db
        from DxSalesDeliveryOrder import dn_batch_create
        # 创建交货单
        dn_data = dn_param(dict_log['uf_so_sn'],uf_stor_loc_code,uf_document_date, user_id)

        # 给交货数量赋值，现在交货数量根据数据传入定义
        for dn in dn_data:
            for item in dn.get('items', []):
                item['planned_delivery_quantity'] = float(ito_data[0]['uf_chip_qty'])
                item['undelivered_qty'] = float(ito_data[0]['uf_chip_qty'])
        print('dn_data---------------',dn_data)

        ret = dn_batch_create(0, dn_data)

        sdo_db.dbCommit()
        print(ret,'ret-dn_batch_create-----------------')
        if ret['status'] == 0:
            dn_ret = ret['data']
            dn_sn = dn_ret[0]['dn_sn']
            if dn_sn != '':
                step = 30
                dict_log['uf_dn_sn'] = dn_sn
                up_log(dict_log, update_status)
            else:
                code = 500
                msg = '未生成对应交货单订单'
        else:
            code = 500
            msg = ret['data']
        # completely_remove_module('DxSalesDeliveryOrder')
    if step == 30:
        pass
        from SalesPickInterface import inventoryPickUp
        # 交货单拣配
        pickup_batch = pick_param(ito_data, dict_log['uf_dn_sn'],ito_item,posting_date, user_id)
        print('拣配入参', pickup_batch)
        code = 0
        res_list = []
        message = ''
        if len(pickup_batch) <= 0:
            code = 500
            message = '拣配数据获取出错'
        else:
            pass    
        # return
            code, message, res_list, _ = inventoryPickUp(pickup_batch, user_id,pickup_batch, test_run=1)
            print("res_list", code, message, res_list)

        if code == 200:
            # picking_document = 'S'
            dict_log['uf_picking_document'] = 's'

            sql_pick = f"""
            select picking_document  from t_dn_inventory_alloc
            where 1 = 1 and dn_sn = "{dict_log['uf_dn_sn']}"
        """
            dbp =DbHelper()

            pick_numdata = dbp.query_sql(sql_pick)
            print('获取拣配单号',pick_numdata)
            if pick_numdata:
                dict_log['uf_picking_document'] = pick_numdata[0]['picking_document']
            up_log(dict_log, update_status)
            step = 40
        else:
            if code == 206 and type(res_list) == list:
                for i in res_list:
                    message += i.get("message")
            code = 500
            
            msg = message

    print(step)
    if step == 40:
        # 交货单过账
        from SalePostInterface import dnPostFunc
        dn_sn = dict_log['uf_dn_sn']
        pram_data = GetDnPostQuery(dn_sn,posting_date)
        print('交货单过账传入', type(pram_data), pram_data)
        response = dnPostFunc(pram_data).__dict__
        print('交货单过账返回', type(response), response)
        if response['code'] == 200:
            pass
            mat_doc_sn = "S"
            if response:
                # print('==-',response['data'][0])
                mat_doc_sn = response['data'][0].get('mat_doc_sn','S')
            # 步骤日志更新数据
            dict_log['uf_dn_doc'] = mat_doc_sn
            up_log(dict_log, update_status)
            step = 50
        else:
            code = 500
            message = response['data'][0]['message']
            msg = message
        # completely_remove_module('SalePostInterface')
    if step == 50:
        # 采购订单收货
        from DxInventoryPostData import post_data

        print('采购订单收货-------', dict_log)
        po_sn = dict_log['uf_po_sn']
        so_sn = dict_log['uf_so_sn']
        # print('采购单号1', po_sn, so_sn, ito_data, ito_item)

        # 原构建数据构建失败，因为取消了一些表，然后传入数据变化较大
        # doc_head, doc_item, error_msg = doc_param(po_sn, so_sn, ito_data, ito_head, ito_item,ito_price=None)


        # 用我自己构建数据的方法进行构建
        # 1 构建数据：
        doc_head, doc_item = build_post_params(header, user_id)
        
        print('构建过账数据', doc_head, doc_item)

        print('过账传入', doc_head, doc_item)
        code, msg, error_list, mat_doc_sn, year = post_data('0', user_id, doc_head, doc_item)
        print('过账返回', code, msg, error_list, mat_doc_sn, year)
        if mat_doc_sn != '':
            # 步骤日志更新数据
            dict_log['uf_po_doc'] = mat_doc_sn
            dict_log['uf_year'] = ito_data[0]['uf_posting_date'][0:4]
            dict_log['uf_status'] = 'C'
            up_log(dict_log, 1)
            step = 100
        else:
            msg = msg + ','.join([ f"{i}" for i in error_list])

    dict_log['uf_msg'] = msg


    # 更新日志表
    print('日志log', dict_log)
    up_log(dict_log, update_status)
    ev_type = 'S'
    ev_msg = '已处理完成'
    if code == 500:
        ev_type = 'E'
        ev_msg = msg
    # guid = payload["guid"]
    return {
        # "guid": guid,
        "type": ev_type,
        "message": ev_msg
    }


def pick_param(ito_data, dn_sn, ito_item,posting_date, user_id,ito_price=None):
    db = DbHelper()
    sql = f"""
        select 
        a.dn_sn,
        a.dn_item,
        a.plant_code,
        a.stor_loc_code,
        b.actual_plant,
        b.actual_stor,

        b.picking_document,
        b.batch_item,
        a.actual_plant,
        c.uf_is_merge_push_mail,  
        a.uf_is_integer,
        a.packing_status,
        a.mat_code,
        a.parallel_uom,
        a.basic_uom,
        a.basic_qty,
        pi.statistics_item_1,
        pi.statistics_item_2,
        a.planned_delivery_quantity
        from  t_dn_item  as a
        left join t_dn_inventory_alloc as b
        on a.dn_sn = b.dn_sn 
        and a.dn_item = b.dn_item 
        join t_dn_header as c on c.dn_sn = a.dn_sn
        join t_po_header as ph
        on ph.so_sn = a.so_sn
        join t_po_item as pi
        on pi.po_sn = ph.po_sn  
        and pi.inter_company_so_items = a.so_items
        where a.dn_sn =  '{dn_sn}'
    """
    dn_data = db.query_sql(sql)
    print('拣配前查询数据结果', dn_data,'dn_data查询结果')
    print("ito_data",ito_data)
    dict_i = {}
    for row in ito_item:
        key = str(row['uf_ito_items'])
        if key in dict_i:
            pass
        else:
            dict_i[key] = {}
            dict_i[key] = row

    dict_m = {}
    for row in ito_data:
        key1 = str(row['uf_ito_items'])
        if key1 in dict_i:
            row['epn'] = dict_i[key1]['uf_mat_code']

        if row.get('uf_ipn','') != '':
            row['uf_mat_code'] = row.get('uf_ipn','')

        batch_type_data = db.query_sql("select batch_type from t_batch_number where mat_code = '{}' and batch_sn = '{}' ".format(row['uf_mat_code'],row['uf_batch_sn']))
        batch_type = ''
        if batch_type_data:
            batch_type = batch_type_data[0]['batch_type']
        # if uf_cost_price_type == 'B':
        #     batch_type = ''
        row['batch_type'] = batch_type
        key = str(row['uf_mat_code']) + str(row['batch_type'])

        # key = str(row['uf_mat_code'])
        if key in dict_m:
            dict_m[key].append(row)
        else:
            dict_m[key] = []
            dict_m[key].append(row)

    pick_batch = []
    pick_batch_row = {}
    for row_c in dn_data:
        pass
        pick_batch_row['dn_sn'] = row_c['dn_sn']
        pick_batch_row['dn_item'] = row_c['dn_item']
        pick_batch_row['plant_code'] = row_c['plant_code']
        pick_batch_row['stor_loc_code'] = row_c['stor_loc_code']
        pick_batch_row['actual_plant'] = row_c['actual_plant']
        pick_batch_row['actual_stor'] = row_c['actual_stor']
        pick_batch_row['mat_code'] = row_c['mat_code']

        # pick_batch_row['mat_code'] = row['uf_mat_code']
        pick_batch_row['packing_date'] = posting_date

        pick_batch_row['parallel_uom'] = row_c['parallel_uom']
        pick_batch_row['basic_uom'] = row_c['basic_uom']
        pick_batch_row['basic_qty'] = row_c['basic_qty']
        pick_batch_row['planned_delivery_quantity'] = row_c['planned_delivery_quantity']

        key = str(row_c['mat_code']) + str(row_c['statistics_item_2'])
        if key in dict_m:
            for each in dict_m[key]:
                print('each11111111',each)
                pick_batch_row['stor_loc_code'] = each['uf_stor_loc_code']
                pick_batch_row['picked_qty'] = float(each['uf_qty'])
                pick_batch_row['picked_base_qty'] =float(each['uf_qty'])
                # pick_batch_row['picked_parallel_qty'] =float(each['uf_parallel_qty'])
                # 直接传来的数据
                pick_batch_row['picked_parallel_qty'] = float(each['uf_chip_qty'])

                pick_batch_row['batch_sn'] = each['uf_batch_sn']
                pick_batch_row['external_mat_code'] = row_c['mat_code']
                temp = pick_batch_row.copy()
                pick_batch.append(temp)
    return pick_batch

def get_additional_property():
    """交货单 附加属性-t_dn_additional_property """
    filter_sql = '''
        SELECT
            dp.dn_sn,
            dp.dn_item,
            dp.field_code,
            pf.field_name,
            dp.field_value
        FROM
            t_dn_additional_property dp
            LEFT JOIN t_ap_property_field pf ON dp.field_code = pf.field_code
    '''
    query_data, property_display, property_info = [], {}, {}
    db = DbHelper()
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

# 获取单位 根据主副单位转换数量
def get_basic_uom(mat_code):
    db = DbHelper()
    basic_uom, basic_uom_data = '', []
    query_basic_sql = "SELECT basic_uom FROM t_mmd_material_basic_data WHERE mat_code = {} ".format(repr(mat_code))
    basic_uom_data = db.query_sql(query_basic_sql)
    if basic_uom_data:
        basic_uom = basic_uom_data[0].get('basic_uom')

    return basic_uom

def get_prod_uom(mat_code, plant_code):
    cond_sql, prod_uom, prod_uom_data = '', '', []
    if mat_code:
        cond_sql += " AND mat_code = {} ".format(repr(mat_code))
    if plant_code:
        cond_sql += " AND plant_code = {} ".format(repr(plant_code))

    query_prod_sql = "SELECT prod_uom FROM t_mmd_material_plant_data WHERE 1 = 1 "
    query_prod_sql += cond_sql
    db = DbHelper()
    prod_uom_data = db.query_sql(query_prod_sql)
    if prod_uom_data:
        prod_uom = prod_uom_data[0].get('prod_uom')

    return prod_uom

def get_primary_conv(basic_uom, prod_uom, mat_code):
    cond_sql, primary_uom_qty, secondary_uom_qty, uom_conv_data = '', 0, 0, []
    if mat_code:
        cond_sql += " AND mat_code = {} ".format(repr(mat_code))
    if basic_uom and prod_uom:
        cond_sql += " AND primary_uom IN ({}, {})".format(repr(basic_uom), repr(prod_uom))
        cond_sql += " AND secondary_uom IN ({}, {})".format(repr(prod_uom), repr(basic_uom))

    conv_filter_sql = """
                    SELECT
                        primary_uom,
                        primary_uom_qty,
                        secondary_uom,
                        secondary_uom_qty
                    FROM
                        t_mmd_uom_conversion
                    WHERE  1 = 1
                """
    conv_filter_sql += cond_sql
    db = DbHelper()
    uom_conv_data = db.query_sql(conv_filter_sql)
    if uom_conv_data:
        primary_uom = uom_conv_data[0].get('primary_uom')
        secondary_uom = uom_conv_data[0].get('secondary_uom')
        primary_uom_qty = uom_conv_data[0].get('primary_uom_qty')
        secondary_uom_qty = uom_conv_data[0].get('secondary_uom_qty')
        if primary_uom == prod_uom and secondary_uom == basic_uom:
            primary_uom_qty, secondary_uom_qty = secondary_uom_qty, primary_uom_qty

    return primary_uom_qty, secondary_uom_qty

def get_larger_conv(basic_uom, prod_uom):
    cond_sql, primary_uom_qty, secondary_uom_qty, uom_conv_data = '', 0, 0, []
    if basic_uom and prod_uom:
        cond_sql += " AND primary_uom = {} ".format(repr(prod_uom))
        cond_sql += " AND secondary_uom = {} ".format(repr(basic_uom))

    conv_filter_sql = """
                    SELECT
                        primary_uom,
                        primary_uom_qty,
                        secondary_uom,
                        secondary_uom_qty
                    FROM
                        t_mmd_uom_conversion
                    WHERE 1 = 1
                """
    conv_filter_sql += cond_sql
    db = DbHelper()
    uom_conv_data = db.query_sql(conv_filter_sql)
    if uom_conv_data:
        primary_uom_qty = uom_conv_data[0].get('primary_uom_qty')
        secondary_uom_qty = uom_conv_data[0].get('secondary_uom_qty')

    return primary_uom_qty, secondary_uom_qty

def get_basic_qty(mat_code, plant_code, prod_uom, order_qty):
    """通过单位转换获取基本数量"""
    basic_uom = get_basic_uom(mat_code)
    if basic_uom and prod_uom and basic_uom == prod_uom:
        return order_qty
    if not prod_uom:
        prod_uom = get_prod_uom(mat_code, plant_code)

    if basic_uom and prod_uom:
        primary_uom_qty, secondary_uom_qty = get_primary_conv(basic_uom, prod_uom, mat_code)
        if primary_uom_qty and secondary_uom_qty:
            calc_qty = float(order_qty) * float(primary_uom_qty) / float(secondary_uom_qty)
            # calc_qty = float(calc_qty.quantize(keep_precise))
            return calc_qty
        else:
            primary_uom_qty, secondary_uom_qty = get_larger_conv(basic_uom, prod_uom)
            if primary_uom_qty and secondary_uom_qty:
                calc_qty = Decimal(order_qty) * Decimal(primary_uom_qty) / Decimal(secondary_uom_qty)
                calc_qty = float(calc_qty.quantize(keep_precise))
                return calc_qty

    return order_qty

def GetDnPostQuery(dn_sn,posting_date):
    """交货单过账需要参数获取查询"""
    if 1 == 1:
        columns = '''
                    alloc.id,
                    header.dn_type,
                    header.estimated_delivery_date,
                    dt.dn_type_description,
                    item.dn_sn AS rel_dn_sn,
                    item.dn_item AS rel_dn_item,
                    item.so_sn AS rel_so_sn,
                    item.so_items AS rel_so_items,
                    ( CASE WHEN item.pod_related = '1' THEN item.movement_type_it ELSE item.movement_type END ) AS movement_type,
                    # item.POD_qty,
                    item.pod_status,
                    item.pod_related,
                    md.mat_doc_sn,
                    md.mat_doc_items,
                    partner.business_partner_code AS dn_customer_code,
                    partner.business_partner_name AS dn_customer_name,
                    ( CASE WHEN item.special_inventory_status1 IN ('CC', 'C') THEN partner.business_partner_code ELSE '' END ) AS customer_code,
                    ( CASE WHEN item.special_inventory_status1 IN ('CC', 'C') THEN partner.business_partner_name ELSE '' END ) AS customer_name,
                    partner2.business_partner_code AS destination_customer_code,
                    partner2.business_partner_name AS destination_customer_name,
                    partner2.business_partner_addr,
                    partner2.contact_person,
                    partner2.contact_number,
                    sales.customer_order,
                    -- sales.auto_created_mark,
                    item.create_id,
                    t_system_user.NAME AS create_name,
                    item.create_time,
                    item.so_sn as so_sn,
                    item.so_items as so_items,
                    alloc.mat_code,
                    material.mat_description AS mat_descr,
                    item.planned_delivery_quantity,
                    alloc.external_mat_code,
                    alloc.picking_document,
                    mt.mat_description AS external_mat_descr,
                    item.cust_mat_code,
                    cmmd.cust_mat_code_description as cust_mat_code_description,
                    concat( header.packing_status, ' ', t_so_status_record.status_description ) AS packing_status,
                    concat( header.posting_status, ' ', t_so_status_record2.status_description ) AS posting_status,
                    concat( header.pod_status, ' ', t_so_status_record3.status_description ) AS pod_status,
                    concat( header.billing_status, ' ', t_so_status_record4.status_description ) AS billing_status,
                    item.plant_code,
                    t_os_plant.plant_description AS plant_name,
                    ( CASE WHEN item.pod_related = '1' THEN mv1.post_code ELSE mv.post_code END ) AS post_code,
                    CURDATE() AS document_date,
                    CURDATE() AS posting_date,
                    alloc.batch_sn,
                    -- alloc.alloc_qty AS transaction_qty,
                    alloc.picked_qty AS transaction_qty,
                    alloc.picked_qty as alloc_picked_qty,
                    alloc.picked_base_qty,
                    alloc.picked_parallel_qty,
                    -- alloc.alloc_batch_qty,
                    -- alloc.alloc_qty,
                    -- alloc.parallel_qty as alloc_parallel_qty,
                    -- alloc.parallel_uom as alloc_parallel_uom,
                    alloc.stor_loc_code as alloc_stor_loc_code,
                    alloc.transaction_uom,
                    -- item.transaction_uom,
                    alloc.parallel_uom,
                    -- item.parallel_uom,
                    alloc.basic_uom,
                    alloc.batch_item,
                    sales_item.intercompany_purchase_order_number,
                    sales_item.intercompany_purchase_order_item_serial_number,
                    -- item.picked_parallel_qty,
                    alloc.stor_loc_code,
                    tosl.stor_loc_desc,
                    ( CASE WHEN material_cost.cost_uom != '' THEN material_cost.cost_uom ELSE material.basic_uom END ) AS batch_uom,
                    0 AS basic_qty,
                    -- material.basic_uom,
                    item.special_inventory_status1,
                    "" AS special_inventory_status2,
                    ( CASE WHEN item.pod_related = '1' THEN 'T' ELSE '' END ) AS rcv_special_inventory_status2,
                    item.wbs_elements,
                    item.cost_center,
                    item.profit_center,
                    item.cost_business_object,
                    item.cost_business_object1,
                    item.cost_uom,
                    '' AS rcv_vendor_code,
                    cat.rcv_special_inventory_status1,
                    ( CASE WHEN cat.rcv_special_inventory_status1 != '' or ( CASE WHEN item.pod_related = '1' THEN 'T' ELSE '' END ) != '' THEN alloc.mat_code else '' END  ) AS rcv_mat_code,
                    ( CASE WHEN cat.rcv_special_inventory_status1 != '' or ( CASE WHEN item.pod_related = '1' THEN 'T' ELSE '' END ) != '' THEN alloc.batch_sn ELSE '' END ) AS rcv_batch_sn,
                    ( CASE WHEN cat.rcv_special_inventory_status1 = 'CC' THEN partner.business_partner_code ELSE '' END ) AS rcv_customer_code,
                    ( CASE WHEN cat.rcv_special_inventory_status1 = 'S' THEN item.so_sn ELSE '' END ) AS rcv_so_sn,
                    ( CASE WHEN cat.rcv_special_inventory_status1 = 'S' THEN item.so_items ELSE '' END ) AS rcv_so_items,
                    ( CASE WHEN cat.rcv_special_inventory_status1 != '' or ( CASE WHEN item.pod_related = '1' THEN 'T' ELSE '' END ) != '' THEN item.plant_code ELSE '' END ) AS rcv_plant_code,
                    ( CASE WHEN cat.rcv_special_inventory_status1 != '' or ( CASE WHEN item.pod_related = '1' THEN 'T' ELSE '' END ) != '' THEN alloc.stor_loc_code ELSE '' END ) AS rcv_stor_loc_code
                    '''

        query_sql = '''
                SELECT {}
                FROM
                    t_dn_inventory_alloc AS alloc
                    LEFT JOIN t_dn_item AS item  ON item.dn_sn = alloc.dn_sn AND item.dn_item = alloc.dn_item
                    LEFT JOIN t_ao_sd_item_category AS cat ON item.sales_item_category = cat.sales_item_category
                    LEFT JOIN t_dn_header AS header ON header.dn_sn = item.dn_sn
                    LEFT JOIN t_md_item AS md ON item.dn_sn = md.rel_dn_sn AND item.dn_item = md.rel_dn_item AND md.reversal_mark != '1' AND md.reversed_mark != '1'
                    LEFT JOIN t_documents_business_partner AS partner ON item.dn_sn = partner.doc_sn AND partner.business_partner_type = 'SP' AND partner.document_category = 'SDLV'
                    LEFT JOIN t_documents_business_partner AS partner2 ON item.dn_sn = partner2.doc_sn AND partner2.business_partner_type = 'DP'
                    LEFT JOIN t_sales_order_header AS sales ON sales.so_sn = item.so_sn
                    LEFT JOIN t_sales_order_item AS sales_item ON sales_item.so_sn = item.so_sn and sales_item.so_items = item.so_items
                    LEFT JOIN t_os_plant ON t_os_plant.plant_code = item.plant_code
                    LEFT JOIN t_system_user ON item.create_id = t_system_user.id
                    LEFT JOIN t_so_status_record ON t_so_status_record.state_value = header.packing_status AND t_so_status_record.field = 'packing_status'
                    LEFT JOIN t_so_status_record AS t_so_status_record2 ON t_so_status_record2.state_value = header.posting_status AND t_so_status_record2.field = 'posting_status'
                    LEFT JOIN t_so_status_record AS t_so_status_record3 ON t_so_status_record3.state_value = header.pod_status AND t_so_status_record3.field = 'pod_status'
                    LEFT JOIN t_so_status_record AS t_so_status_record4 ON t_so_status_record4.state_value = header.billing_status AND t_so_status_record4.field = 'billing_status'
                    LEFT JOIN t_os_plant_storage_location_alloc AS tosl ON tosl.plant_code = item.plant_code AND tosl.stor_loc_code = alloc.stor_loc_code
                    LEFT JOIN t_mmd_material_cost_data AS material_cost ON item.mat_code = material_cost.mat_code AND item.plant_code = material_cost.plant_code
                    LEFT JOIN t_mmd_material_basic_data AS material ON alloc.mat_code = material.mat_code
                    LEFT JOIN t_mmd_material_basic_data AS mt ON alloc.external_mat_code = mt.mat_code
                    LEFT JOIN t_cust_mat_master_data as cmmd ON item.cust_mat_code = cmmd.cust_mat_code
                    LEFT JOIN t_movement_type AS mv ON item.movement_type = mv.movement_type
                    LEFT JOIN t_movement_type AS mv1 ON item.movement_type_it = mv1.movement_type
                    LEFT JOIN t_dn_type AS dt ON dt.dn_type = header.dn_type
                WHERE

                    item.dn_sn in ('{}') 
                    group by item.dn_sn,
item.dn_item 
                '''.format(columns, dn_sn)

        # alloc.posting_status = 'A'
        # AND header.packing_status = 'C'
        # AND (header.posting_status = 'A' or header.posting_status = 'B')
        # AND item.deleted_mark != "1" AND item.lock_flag != "1"

    query_sql = query_sql.replace('    ', ' ')

    display = [
        {"description": "消息", "field": "message"}]

    display.extend([
        {"description": "快递单号", "field": "express_delivery"},
        {"description": "过账日期", "field": "posting_date"},
        {"description": "拣配单号", "field": "picking_document"},
        {"description": "凭证日期", "field": "document_date"},
        {"description": "交货单号", "field": "rel_dn_sn"},
        {"description": "交货单行号", "field": "rel_dn_item"},
        {"description": "交货单类型", "field": "dn_type"},
        {"description": "交货单类型描述", "field": "dn_type_description"},
        {"description": "物料凭证号", "field": "mat_doc_sn"},
        {"description": "客户编码", "field": "dn_customer_code"},
        {"description": "客户名称", "field": "dn_customer_name"},
        {"description": "送达方", "field": "destination_customer_code"},
        {"description": "送达方描述", "field": "destination_customer_name"},
        {"description": "送货地址", "field": "business_partner_addr"},
        {"description": "送货联系人", "field": "contact_person"},
        {"description": "联系电话", "field": "contact_number"},
        {"description": "客户订单号", "field": "customer_order"},
        {"description": "销售订单号", "field": "so_sn"},
        {"description": "销售订单行号", "field": "so_items"},
        {"description": "物料编码", "field": "mat_code"},
        {"description": "物料描述", "field": "mat_descr"},
        {"description": "成本单位", "field": "cost_uom"},
        {"description": "订单数量", "field": "quantity_of_delivery_order_created"},
        {"description": "销售单位", "field": "sales_uom"},
        {"description": "拣配数量（交易单位）", "field": "alloc_picked_qty"},
        {"description": "拣配数量（基本单位）", "field": "picked_base_qty"},
        {"description": "拣配数量（平行单位）", "field": "picked_parallel_qty"},
        {"description": "交易单位", "field": "transaction_uom"},
        {"description": "基本单位", "field": "basic_uom"},
        {"description": "平行单位", "field": "parallel_uom"},
        {"description": "外部编码", "field": "external_mat_code"},
        {"description": "外部编码描述", "field": "external_mat_descr"},
        {"description": "库存地点", "field": "stor_loc_code"},
        {"description": "库存地点描述", "field": "stor_loc_desc"},
        {"description": "客户物料编码", "field": "cust_mat_code"},
        {"description": "客户物料描述", "field": "cust_mat_code_description"},
        {"description": "拣配状态", "field": "packing_status"},
        {"description": "过账状态", "field": "posting_status"},
        {"description": "POD标记", "field": "pod_related"},
        {"description": "POD数量", "field": "POD_qty"},
        {"description": "POD状态", "field": "pod_status"},
        {"description": "移动类型", "field": "movement_type"},
        {"description": "特殊库存状态1", "field": "special_inventory_status1"},
        {"description": "计划交货日期", "field": "estimated_delivery_date"},
        {"description": "交货工厂", "field": "plant_code"},
        {"description": "交货工厂名称", "field": "plant_name"},
        {"description": "WBS元素", "field": "wbs_elements"},
        {"description": "成本中心", "field": "cost_center"},
        {"description": "利润中心", "field": "profit_center"},
        {"description": "项目编号", "field": "rcv_project_sn"},
        {"description": "成本数量", "field": "batch_qty"},
        {"description": "成本单位", "field": "batch_uom"},
        {"description": "基本数量", "field": "batch_qty"},
        {"description": "创建者", "field": "create_name"},
        {"description": "创建日期", "field": "create_time"}
    ])

    db = DbHelper()
    query_data = db.query_sql(query_sql)
    print(query_sql)
    print('交货单过账参数查询结果', query_data)
    if query_data:

        field_names = [item.get('field') for item in display]
        property_info, property_display = get_additional_property()
        # cover_uom_list = get_cover_uom_db()

        for record in query_data:
            record['posting_date'] = posting_date
            dn_sn = record.get('rel_dn_sn') or record.get('dn_sn')
            dn_item = record.get('rel_dn_item') or record.get('dn_item')
            unique_key = str(dn_sn) + '-' + str(dn_item)
            dn_property = property_info.get(unique_key) or {}
            if dn_property:
                record.update(dn_property)
                for field_code in dn_property.keys():
                    if field_code not in field_names:
                        field_names.append(field_code)
                        field_display = property_display.get(field_code)
                        display.append(field_display)

            mat_code = record.get('mat_code')
            plant_code = record.get('plant_code')
            transaction_uom = record.get('transaction_uom')
            transaction_qty = record.get('transaction_qty')
            record['basic_qty'] = get_basic_qty(mat_code, plant_code, transaction_uom, transaction_qty)
            
    return query_data

def eMes_push_data():

    '''
    纯后台推送  定时任务  EMES
    '''
    # cbk = Callback()
    # body = json.loads(cbk.param())
    # po_sn = body.get("po_sn", "")  # 采购订单号

    db_helper = DbHelper()
    result = {}
    sysh = SysHandler()
    req = Request()
    user_id = req.header("user_id") or sysh.get_env("user_id") or 0

    head_sql = "SELECT * FROM ut_ito_post_Interface_head WHERE uf_posting_status   != 'S' and uf_reversal_mark   = '' order by uf_posting_time  "
    head_data = db_helper.query_sql(head_sql)

    item_sql = """
        SELECT t.* FROM ut_ito_post_Interface_head as h
        left join ut_ito_post_Interface_data as t
        on h.uf_guid = t.uf_guid
        WHERE h.uf_posting_status  != 'S' and h.uf_reversal_mark  = '' order by uf_posting_time 
    """
    item_data = db_helper.query_sql(item_sql)

    dict_item = {}
    for i in item_data:
        key = i['uf_guid']
        if key in dict_item:
            dict_item[key].append(i)
        else:
            dict_item[key] = []
            dict_item[key].append(i)


    ito_lst = [ i['uf_ito_sn'] for i in head_data if i['uf_ito_sn'] != '']

    ito_data = []
    ito_pick = {}
    if ito_lst:
        pick_sql = """
        select * from ut_intercompany_transaction_order_item
    where uf_ito_sn in ({})  and uf_deleted_mark != 1  and uf_batch_sn != ''
        """.format(','.join([ f"'{i}'" for i in ito_lst ]))
        ito_data = db_helper.query_sql(pick_sql)
        for i in ito_data:
            pass
            key = str(i['uf_ito_sn']) 
            if key in ito_pick:
                ito_pick[key].append(i)
            else:
                ito_pick[key] = []
                ito_pick[key].append(i)
    
    if head_data:
        for each in head_data:
            key_guid = each['uf_guid']

            posting_date =  each['uf_posting_date']
            uf_tracking_number = each['uf_tracking_number']
            prarm_item = []

            print('==-',each,dict_item)
            if key_guid in dict_item:
                key = str(each['uf_ito_sn'])
                if key in ito_pick:

                    pass
                    for row in ito_pick[key]:


                        dict_temp=row.copy()
                        dict_temp['uf_posting_date'] = posting_date
                        dict_temp['uf_tracking_number'] = uf_tracking_number
                        dict_temp['uf_stor_loc_code'] = dict_temp['uf_from_stor_loc_code']
                        dict_temp['uf_qty'] = dict_temp['uf_transaction_qty']
                        # temp['mat_code'] = temp['uf_mat_code']
                        dict_temp['uf_mat_code'] = dict_temp['uf_ipn']
                        dict_temp['batch_sn'] = dict_temp['uf_batch_sn']
                        dict_temp['uf_batch_sn'] = dict_temp['uf_batch_sn']
                        prarm_item.append(dict_temp)

                        # dict_temp = copy.deepcopy(dict_item[key_guid][0])

                else:
                    pass

                    for row in dict_item[key_guid]:
                        prarm_item.append(row)
            print('job开始执行')
            ret = ito_post_main(prarm_item, key_guid, user_id)
            print(ret)
 
            print('job开始执行wangc')




def build_post_params(header, user_id):
    """
    构建库存过账参数（调拨业务，post_code=4，movement_type 311→T001）。
    """
    db = DbHelper()
    doc_head = {
        "document_category": "",            # 单据种类（调拨为空）
        "post_code": "4",                   # 过账代码：4=调拨
        "document_date": header.get("document_date"),
        "posting_date": header.get("posting_date"),
        "summary_unique_number": header.get("summary_unique_number", ""),
        "company_code": "",                 # 由工厂获取
        "remarks_1": "OSAT调拨批导",
    }

    doc_items = []
    line_id = 0
    for item in header.get("item", []):
        line_id += 1
        mat_code = str(item.get("mat_code", "")).strip()
        plant_code = str(item.get("plant_code", "")).strip()

        # 物料基本信息（基本单位、平行单位）
        mat_info = db.query_sql(
            "SELECT basic_uom, parallel_uom FROM t_mmd_material_basic_data WHERE mat_code = {}".format(repr(mat_code)))
        basic_uom = mat_info[0]['basic_uom'] if mat_info else item.get('transaction_uom', 'EA')
        parallel_uom = mat_info[0]['parallel_uom'] if mat_info else ''
        print("获取物料基本信息成功：", mat_info)

        # 工厂对应的公司代码
        plant_info = db.query_sql(
            "SELECT company_code FROM t_os_company_plant_alloc WHERE plant_code = {}".format(repr(plant_code)))
        if plant_info:
            doc_head['company_code'] = plant_info[0]['company_code']
        print("获取工厂对应的公司代码成功：", plant_info)

        # 平行数量
        parallel_qty = float(item.get("parallel_qty", 0)) if item.get("parallel_qty") else 0

        # 批次信息
        batch_sn = str(item.get("batch_sn", "")).strip()
        batch_number = build_batch_number(mat_code, batch_sn, db)
        print("构建批次信息成功：", batch_number)

        transaction_qty = float(item.get("transaction_qty", 0))

        doc_item = {
            "line_id": item.get("line_id", line_id),
            "movement_type": "T001",        # 311 自动转换为 T001
            "plant_code": plant_code,
            "stor_loc_code": item.get("stor_loc_code", ""),
            "mat_code": mat_code,
            "batch_sn": batch_sn,
            "inventory_status": item.get("inventory_status", "0"),
            "special_inventory_status1": item.get("special_inventory_status1", ""),
            "special_inventory_status2": "",
            "transaction_qty": transaction_qty,
            "transaction_uom": item.get("transaction_uom", basic_uom),
            "basic_qty": transaction_qty,   # 默认等于交易数量
            "basic_uom": basic_uom,
            "parallel_qty": parallel_qty,
            "parallel_uom": item.get("parallel_uom", parallel_uom),
            "po_sn": item.get("po_sn", ""),         # 采购订单号透传
            "create_id": user_id,
            "batch_number": batch_number,
            # ===== 接收方信息 =====
            "rcv_mat_code": mat_code,                                   # 接收物料默认等于源物料
            "rcv_plant_code": item.get("target_plant_code", ""),       # 目标工厂
            "rcv_stor_loc_code": item.get("target_stor_loc_code", ""), # 目标库存地点
            "rcv_batch_sn": item.get("rcv_batch_sn", batch_sn),        # 接收批次默认等于源批次
            "rcv_batch_number": {},
            "rcv_inventory_status": item.get("inventory_status", "0"),
            "rcv_special_inventory_status1": item.get("special_inventory_status1", ""),
            "rcv_special_inventory_status2": "",
        }
        doc_items.append(doc_item)

    print("过账数据构建成功：", doc_head, doc_items)
    return doc_head, doc_items



def build_batch_number(mat_code, batch_sn, db):
    """
    构建批次信息：优先取 t_batch_number 已有记录，无则用默认模板。
    """
    if not batch_sn:
        return {}
    query_sql = "SELECT * FROM t_batch_number WHERE mat_code = {} AND batch_sn = {}".format(repr(mat_code), repr(batch_sn))
    batch_data = db.query_sql(query_sql)
    print("查询批次信息：", batch_data)
    if batch_data:
        return batch_data[0]
    # 默认模板
    batch_number = initialization_batch_number(db)
    batch_number['mat_code'] = mat_code
    batch_number['batch_sn'] = batch_sn
    return batch_number


def initialization_batch_number(db):
    """
    获取批次号结构模板（从 t_batch_number 表结构生成默认值字典）。
    """
    query_sql = """
        SELECT column_name AS field_name, column_default as default_value, data_type as data_type
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND table_name = 't_batch_number'
          AND column_name NOT IN ('id', 'create_id', 'update_id', 'create_time', 'update_time', 'note')
        ORDER BY ordinal_position
    """
    table = db.query_sql(query_sql)
    print("查询批次号结构：", table)
    data = {}
    for each in table:
        if each["data_type"] in ('decimal', 'double', 'tinyint', 'int'):
            data[each["field_name"]] = 0
        else:
            data[each["field_name"]] = each["default_value"] if each["default_value"] else ''
    print("初始化批次号结构：", data)
    return data


