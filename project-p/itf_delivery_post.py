"""
@File    : itf_delivery_post.py
@Author  : jing.deng@dxdstech.com
@Date    : 2025/08/27 15:08
@explain : 秘火发货过账接口（销售）

  两阶段架构:
    阶段① delivery_post(payload, user_id)  —— 前端入口:校验 / 行号匹配 / 批次匹配 / 单位换算 / 落接口表(不碰 SAP)
    阶段② eMes_push_data()                  —— 定时任务:扫接口表(uf_posting_status != 'S')逐 guid
                                               调 delivery_post_main 真正过账(状态机: 公司间调拨ITO → 拣配 → 发货过账)

  注: 本次为可读性重构, 行为与重构前完全一致(含原有逻辑, 未做任何 bug 修复)。
"""
import copy
from decimal import Decimal, getcontext

from DbHelper import DbHelper  # type:ignore
from logger import LoggerConfig  # type:ignore
from SalePostInterface import dnPostFunc  # type:ignore
from SalesPickInterface import inventoryPickUp  # type:ignore

# 设置Decimal的精度
getcontext().prec = 20
keep_precise = Decimal('0.00000000')

log = LoggerConfig('itf_delivery_post')

db = DbHelper()


# ============================ 1. 批次匹配 ============================

def _build_batch_available_sql(row, box_mark, dn_sn, db):
    """构造"批次可用库存"查询 SQL(原 get_batch_sn 内联 SQL, 逐字符保留)。

    可用量 = t_inventory_batch_data(仅开放 ML 账期) 减去四类占用:
      po(t_po_batch_binding 已分配) / dn(t_dn_inventory_alloc 已拣配) /
      res(t_res_item 预留) / ito(ut_intercompany_transaction_order 公司间调拨)。
    """
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
    where_sql = " (a.uf_quality_type = '' or a.uf_quality_type = 'run' ) and a.mat_code = '{}' ".format(
        row['uf_mat_code'])
    po_mat = " and a.component_code = '{}' ".format(row['uf_mat_code'])
    dn_mat = " and  a.mat_code = '{}' ".format(row['uf_mat_code'])
    res_mat = "  and mat_code = '{}' ".format(row['uf_mat_code'])
    ito_mat = " and  t.uf_ipn = '{}' ".format(row['uf_mat_code'])
    field_lst = ["uf_runcard", "uf_box_no", "uf_lot_no", "uf_ZT07", "uf_ZT18", "uf_stor_loc_code"]
    if box_mark == 'X':
        field_lst = ["uf_runcard", "uf_lot_no", "uf_ZT07", "uf_ZT18", "uf_stor_loc_code"]

    for key, value in row.items():
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
    a.lot_no,
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
    where t.batch_occupy_flag = 1 and h.posting_status = 'A' {dn_mat} and a.dn_sn != {dn_sn}
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
            where uf_batch_sn != '' and t.uf_deleted_mark != 1 and l.uf_guid IS NULL {ito_mat}
            group by  t.uf_ipn,h.uf_from_plant_code ,t.uf_from_stor_loc_code,uf_batch_sn
        ) as ito
        on t1.mat_code = ito.mat_code
        and t1.plant_code = ito.plant_code
        and t1.stor_loc_code = ito.stor_loc_code
        and t1.batch_sn = ito.batch_sn

    where {where_sql} order by receive_date asc
    """
    return sql


def get_batch_sn(row, box_mark, dn_sn):
    """批次匹配:按可用库存(basic_qty - 各类占用)取可用>0 的批次, FIFO(receive_date 升序)。

    注意: 下方算术在四类占用任一为 NULL 时会抛 TypeError(原逻辑, 未改)。
    """
    # 批次匹配逻辑
    db = DbHelper()
    sql = _build_batch_available_sql(row, box_mark, dn_sn, db)
    data = db.query_sql(sql)
    print(sql)
    for i in data:
        i['basic_qty'] = i['basic_qty'] - (i['allocated_qty'] + i['picked_base_qty'] + i['res_qty'] + i['ito_qty'])
        i['parallel_qty'] = i['parallel_qty'] - (
                    i['allocated_parallel_qty'] + i['picked_parallel_qty'] + i['res_parallel_qty'] + i[
                'ito_parallel_qty'])
    output = []
    output = [i for i in data if i['basic_qty'] > 0]
    print(len(output))
    return output


# ============================ 2. 交货单明细查询 & 数量更新 ============================

def _build_dn_detail_sql(dn_sn):
    """构造交货单明细查询SQL(原 update_dn_qty 内联, 逐字符保留)。"""
    return f"""
    SELECT 
                  dh.dn_type,                         -- 交货单类型
                  dh.request_delivery_date,           -- 要求交货日期
                  dh.request_delivery_date PC_request_delivery_date,      -- PC要求交货日期
                  dh.uf_is_declare,                   -- 是否报关     1       t_dn_header
                  dh.uf_shipping_method,              -- 发货方式     1       t_dn_header    
                  dh.uf_transfer_address_Roundabout,  -- 中转地址（绕园） 1   t_dn_header
                  dh.create_time,                     -- 创建时间
                  dh.uf_is_send_delivery,             -- 是否更新订单数量
                  dh.uf_is_update_order_qty,          -- 是否更新订单数量 1   t_dn_header
                  dh.uf_is_merge_push_mail,           -- 是否合并推送     1   t_dn_header
                  dh.customer_code ,                  -- 客户编码   
                  dh.customer_code as sp_code,        -- 客户编码   
                  dh.approval_status,
                  dh.create_id dh_crt_id,             -- 创建人
                  dh.create_time dn_sn_crt_tm,        -- 创建日期
                  di.id, 
                  di.uf_min_delivery_qty,          -- 最小交货数量
                  di.dn_sn,                        -- 交货单号                
                  di.dn_item,                      -- 交货单行
                  di.mat_code,                     -- EPN
                  di.cust_mat_code,                -- CPN
                  di.cust_mat_code_description,    -- 客户物料描述
                  di.ipn,                          -- IPN          1   t_dn_item
                  di.incoterms_code,               -- 国际贸易术语
                  di.plant_code,                   -- 工厂代码
                  di.stor_loc_code,                -- 库存地点
                  di.packing_status,               -- 拣配状态
                  di.posting_status,               -- 过账状态
                  di.uf_email_remarks,             -- 邮件备注         1 t_dn_item
                  di.actual_plant,                 -- 实际发货工厂    1   t_dn_item
                  di.uf_actual_stor,               -- 实际发货库存地点 1   t_dn_item
                  di.uf_is_integer,                -- 是否出整数       1   t_dn_item
                  di.deleted_mark, 
                  di.lock_flag, 
                  di.planned_delivery_quantity,    -- 交货单数量
                  si.order_qty,                    -- 订单数量
                  si.quantity_of_delivery_order_created,-- 已创建交货单数量
                  si.order_qty - si.quantity_of_delivery_order_created AS undelivered_qty, -- 未创建交货单数量
                  si.uf_sap_first_order,           -- SAP一级订单号
                  si.uf_sap_first_order_items,     -- SAP一级订单行号 
                  si.uf_sap_secondary_order,       -- SAP二级订单号
                  si.uf_sap_secondary_order_items, -- SAP二级订单行号
                  si.so_sn,                        -- 销售订单号
                  si.so_items,                     -- 销售订单行号
                  si.sales_uom,                    -- 销售单位
                  si.uf_remarks,                      -- 销售订单文本-行
                  si.uf_bin_judgment_symbol,  	    -- BIN别判断符号
                  si.uf_bin,                          -- BIN别       
                  si.uf_wafer_version,                -- 晶圆版本        
                  si.uf_customer_project_id,  	    -- 客户项目ID
                  si.uf_pack_factory_judgment_symbol, -- 封装厂判断符号
                  si.uf_pack_factory, 	            -- 封装厂
                  si.uf_test_factory_judgment_symbol, -- 测试厂判断符号
                  si.uf_test_factory, 	            -- 测试厂
                  si.uf_test_program_version, 	    -- 测试程序版本
                  si.uf_customer_po_no customer_order,-- 客户参考
                  si.uf_d_c,  	                    -- D/C
                  sh.remarks,                         -- 销售订单文本-抬头
                  sh.uf_logist_time_require,          -- 物流时效要求 
                  sh.uf_sap_creater,                  -- SAP二级订单创建人
                  sh.credit_control_code, 
                  dp.business_partner_code    ship_to_party,              -- ship-to party
                  dp.business_partner_name    ship_to_party_name,         -- ship-to party name         
                  dp.contact_number           ship_to_party_telephone,    -- ship-to party telephone
                  dp.business_partner_addr    ship_to_party_address,      -- ship-to party address
                  dp.contact_person           ship_to_contact_person,     -- ship_to_contact_person
                  mbd.prod_group,                     -- 产品组
                  di.create_id,
                  di.create_id as update_id,
                  mbd.uf_package_type                 -- 封装形式 
               FROM
                  t_dn_header                                     dh 
               JOIN t_dn_item                                      di   ON di.dn_sn = dh.dn_sn
               LEFT JOIN t_sales_order_item                        si   on si.so_sn = di.so_sn 
                                                                     AND si.so_items = di.so_items
               LEFT JOIN t_sales_order_header                      sh   on sh.so_sn = si.so_sn
               LEFT JOIN t_documents_business_partner              dp   ON dp.doc_sn =  si.so_sn
                                                                     and dp.doc_items = si.so_items
                                                                     AND dp.business_partner_type = 'DP' 
                                                                     AND dp.document_category = 'SAL'
               LEFT JOIN t_mmd_material_basic_data                mbd  ON mbd.mat_code = di.mat_code
               where 
               dh.auto_mark != '1' 
   and dh.dn_sn = '{dn_sn}'

   """

def _merge_update_dn_qty(data, update_dn_item):
    """把传入的过账数量合并到交货单明细(原 dict_i 逻辑)。返回 (up_data, user_id)。"""
    dict_i = {}
    up_data = []
    user_id = 0
    for i in data:
        user_id = i['create_id']
        key = str(i['dn_sn']) + str(i['dn_item'])
        if key not in dict_i:
            dict_i[key] = {}
            dict_i[key] = i
    for row in update_dn_item:
        key = str(row['uf_dn_sn']) + str(row['uf_dn_item'])
        if key in dict_i:
            dict_i[key]['planned_delivery_quantity'] = row['planned_delivery_quantity']
            up_data.append(dict_i[key])
    return up_data, user_id


def update_dn_qty(update_dn_item):
    """更新交货单数量:查明细 → 合并过账数量 → 调 _batchUpdateDN。"""
    dn_sn = update_dn_item[0]['uf_dn_sn']
    from Z_DeliveryBatchMaintanence import _batchUpdateDN

    sql = _build_dn_detail_sql(dn_sn)
    db = DbHelper()
    data = db.query_sql(sql)
    up_data, user_id = _merge_update_dn_qty(data, update_dn_item)
    if up_data:
        code, msg, data = _batchUpdateDN(db, up_data, user_id)
        print("交货单数量更新结果", code, msg)

# ============================ 3. 接口落表(入口①) ============================

def _validate_delivery_head(data, guid):
    """抬头校验: header 存在 + dn_sn/过账日期非空。成功返回 (None, head, dict_head); 失败返回 (error_dict, None, None)。"""
    if data.get("header", '') == '':
        return {"guid": guid, "type": 'E', "message": '传入结构不存在header'}, None, None
    head = data.get("header")
    print('head-----', head)
    head[0]['uf_posting_time'] = head[0]['delivery_time']
    dict_head = head[0]
    if dict_head.get('uf_dn_sn', '') == '':
        return {"guid": guid, "type": 'E', "message": '交货单号不能传空'}, None, None
    if dict_head.get('uf_posting_date', '') == '':
        return {"guid": guid, "type": 'E', "message": '过账日期不能传空'}, None, None
    return None, head, dict_head


def _check_dn_company_period(dn_sn, posting_date, guid, db):
    """查交货单公司代码 + 账期校验。返回 error_dict 或 None。"""
    com_data = db.query_sql(f""" select company_code from t_dn_header where dn_sn = '{dn_sn}' """)
    company_code = ''
    if com_data:
        print(com_data)
        company_code = com_data[0]['company_code']
    else:
        return {"guid": guid, "type": 'E', "message": f"交货单号{dn_sn}未找到"}
    from DxCompanyPeriodUtil import check_material_period  # type:ignore
    _code, _msg = check_material_period(company_code, posting_date)  # 🎯 2026年1月2日 账期校验修正
    if _code != 200:
        return {"guid": guid, "type": 'E', "message": f"公司代码{company_code}账期{posting_date}未开"}
    return None


def _picking_document_early_return(head, item, dict_head, dn_sn, guid):
    """拣配单号已存在时的早返回: 填公共字段 → 查重 → 落表。返回响应 dict。"""
    for row in item:
        row['uf_bs_category'] = dict_head['uf_bs_category']
        row['uf_posting_date'] = dict_head['uf_posting_date']
        row['uf_tracking_number'] = dict_head['uf_tracking_number']
        row['virtual_tracking_number'] = dict_head['virtual_tracking_number']
        row['uf_dn_sn'] = dict_head['uf_dn_sn']
        row['uf_guid'] = dict_head['uf_guid']
    # uf_reversal_guid 是冲销标识，如果该单据的上次执行未被冲销 就不可再次执行过账
    sql = f"""
    select * from ut_delivery_post_Interface_head
    where uf_bs_category = '29' and uf_dn_sn = '{dn_sn}' and  uf_reversal_mark  != 1
    """
    db = DbHelper()
    # 获取调拨单数据
    Interface_data = db.query_sql(sql)
    type1 = ''
    msg1 = ''
    if Interface_data:
        return {"guid": guid, "type": 'E', "message": str(dn_sn) + '该单据已存在发送记录'}
    else:
        status_1 = 0
        status_1 = db.batchInsertToDB('ut_delivery_post_Interface_head', head)
        print("接口传入表h数量更新", status_1)
        status_2 = 0
        status_2 = db.batchInsertToDB('ut_delivery_post_Interface_data', item)
        print("接口传入表t数量更新", status_2)
        print(item)
        if status_1 >= 0 and status_2 >= 0:
            type1 = 'S'
            msg1 = str(dn_sn) + '数据已接收'
        return {"guid": guid, "type": type1, "message": msg1}


def _match_dn_lines(item, dn_sn, db):
    """行号匹配: 把传入行按 dn_item 计划数量拆分。返回 (posnr_data, lv_error)。"""
    # ----------- 行号匹配逻辑
    dn_data = db.query_sql(
        f""" select dn_item,ipn,planned_delivery_quantity from t_dn_item where dn_sn = '{dn_sn}' and deleted_mark != 1 """)
    lv_error = ''
    posnr_data = []
    for row in item:
        row['uf_dn_item2'] = row['Dn_Item2']
        row['uf_dn_sn'] = dn_sn
        row['uf_dn_item'] = 0
        qty = float(row['uf_picked_qty'])
        for each in dn_data:

            if str(each['dn_item']) not in row.get("uf_dn_item2", ''):
                continue
            dict_temp = {}
            if each['planned_delivery_quantity'] <= 0:
                continue
            if row['uf_mat_code'] in each['ipn'] or row['uf_mat_code'] == each['ipn']:
                if qty <= each['planned_delivery_quantity']:
                    each['planned_delivery_quantity'] = each['planned_delivery_quantity'] - qty

                    row['uf_dn_item'] = each['dn_item']

                    dict_temp = copy.deepcopy(row)
                    dict_temp['uf_picked_qty'] = qty
                    # dict_temp['uf_picked_qty'] = row['planned_delivery_quantity']
                    posnr_data.append(dict_temp)
                    qty = 0
                else:

                    qty = qty - each['planned_delivery_quantity']

                    row['uf_dn_item'] = each['dn_item']

                    dict_temp = copy.deepcopy(row)
                    dict_temp['uf_picked_qty'] = copy.deepcopy(each['planned_delivery_quantity'])
                    posnr_data.append(dict_temp)
                    each['planned_delivery_quantity'] = 0

            if qty == 0:
                break

        if qty != 0:
            lv_error = '交货单号' + str(dn_sn) + f"行{row['uf_line_id']}" + '匹配行号出错'
    return posnr_data, lv_error
    # ----------- 行号匹配逻辑


def _load_initial_attributes(db):
    """查初始属性字段(结果当前未被使用, 保留原查询与副作用)。"""
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
    return wafer_id, uf_runcard, uf_box_no, uf_ZT07, uf_ZT18


def _match_batches_for_items(item, db):
    """批次匹配: uf_batch_sn 为空时调 create_batch_sn 分配(含原逻辑, 未修 bug)。返回 (output, msg_lst)。"""
    msg_lst = ''
    output = []
    for each in item:
        # ------批次匹配逻辑
        if each['uf_batch_sn'] == '':
            from Z_generate_batch_sn import create_batch_sn
            new_batch_sn = create_batch_sn(db, each)
            if new_batch_sn == '':
                output_d = copy.deepcopy(each)

                output_d['uf_batch_sn'] = new_batch_sn
                output.append(output_d)
            else:
                msg_lst += "行项目：" + str(each['uf_dn_item']) + '/' + str(each['uf_line_id']) + "匹配不到批次"

            output_d = copy.deepcopy(each)
            output.append(output_d)
    return output, msg_lst


def _fill_row_common_fields(row, dict_head):
    """行公共字段回填 + 空数量补 0。"""
    row['uf_bs_category'] = dict_head['uf_bs_category']
    row['uf_posting_date'] = dict_head['uf_posting_date']
    row['uf_tracking_number'] = dict_head['uf_tracking_number']
    row['virtual_tracking_number'] = dict_head['virtual_tracking_number']
    row['uf_dn_sn'] = dict_head['uf_dn_sn']
    row['uf_guid'] = dict_head['uf_guid']
    # row['uf_line_id'] = row['line_id']
    if row.get("uf_picked_base_qty", '') == '':
        row['uf_picked_base_qty'] = 0
    if row.get("uf_picked_parallel_qty", '') == '':
        row['uf_picked_parallel_qty'] = 0


def _convert_row_uom_and_record(row, dict_head, db, qty_dict, delete_set):
    """数量单位换算 + 过账数量记录。就地改 row / qty_dict / delete_set。"""
    from DxBusinessDataConvertUtil import convert_material_unit_qty_new  # type:ignore
    # ------- 数量单位换算逻辑
    dn_sn = dict_head['uf_dn_sn']
    dn_item = row['uf_dn_item']
    uom_data = db.query_sql(
        f""" select id,dn_sn,dn_item,planned_delivery_quantity,transaction_uom,parallel_uom ,basic_uom from t_dn_item where dn_sn = '{dn_sn}' and dn_item  = '{dn_item}' """)
    delete_set.add(f"(uf_dn_sn = '{dn_sn}' and uf_dn_item  = '{dn_item}')")
    print('单位', uom_data)
    if uom_data:
        # 单位换算处理
        transaction_uom = uom_data[0]['transaction_uom']
        parallel_uom = uom_data[0]['parallel_uom']
        basic_uom = uom_data[0]['basic_uom']
        if row['uf_picked_base_qty'] == 0 and basic_uom != '' and transaction_uom != '':
            code, msg, qty = convert_material_unit_qty_new(row['uf_mat_code'], transaction_uom, basic_uom,
                                                           row['uf_picked_qty'])
            row['uf_picked_base_qty'] = qty

        if row['uf_picked_parallel_qty'] == 0 and parallel_uom != '' and transaction_uom != '':
            code, msg, qty = convert_material_unit_qty_new(row['uf_mat_code'], transaction_uom, parallel_uom,
                                                           row['uf_picked_qty'])
            row['uf_picked_parallel_qty'] = qty
        # 过账数量记录
        key_i = str(dn_sn) + str(dn_item)
        if key_i in qty_dict:
            qty_dict[key_i]['uf_interface_qty'] += float(row['uf_picked_qty'])
        else:
            qty_dict[key_i] = {}
            qty_dict[key_i]['uf_dn_sn'] = dn_sn
            qty_dict[key_i]['uf_dn_item'] = dn_item
            qty_dict[key_i]['uf_posting_date'] = dict_head['uf_posting_date']
            qty_dict[key_i]['dn_item_id'] = uom_data[0]['id']
            qty_dict[key_i]['uf_planned_delivery_quantity'] = uom_data[0]['planned_delivery_quantity']
            qty_dict[key_i]['uf_interface_qty'] = float(row['uf_picked_qty'])


def _persist_delivery_interface(head, item, qty_dict, delete_set, dn_sn, guid):
    """落接口表: 查重 → 写 head/item → 清旧数量 → 写数量关系 → 更新交货单数量。返回响应 dict。"""
    sql = f"""
    select * from ut_delivery_post_Interface_head
    where uf_bs_category = '29' and uf_dn_sn = '{dn_sn}' and  uf_reversal_mark  != 1
    """
    db = DbHelper()
    # 获取调拨单数据
    Interface_data = db.query_sql(sql)

    data = db.query_sql(
        f"select * from ut_delivery_post_step_log where uf_dn_sn = '{dn_sn}' and  uf_reversal_mark  != 1")

    type1 = ''
    msg1 = ''
    if Interface_data:
        return {
            "guid": guid,
            "type": 'E',
            "message": str(dn_sn) + '该单据已存在发送记录'
        }
    else:
        # ut_ito_post_Interface_head
        qty_data = []
        update_dn_item = []
        print(qty_dict)
        for index, value in qty_dict.items():
            dict_u = {}
            dict_u['uf_dn_sn'] = value['uf_dn_sn']
            dict_u['uf_dn_item'] = value['uf_dn_item']
            dict_u['planned_delivery_quantity'] = float(value['uf_interface_qty'])
            update_dn_item.append(dict_u)

            value['uf_quantity_difference'] = float(value['uf_planned_delivery_quantity']) - float(
                value['uf_interface_qty'])
            # del.value['dn_item_id']
            qty_data.append(value)

        status_1 = 0
        status_1 = db.batchInsertToDB('ut_delivery_post_Interface_head', head)
        print("接口传入表h数量更新", status_1)
        status_2 = 0
        status_2 = db.batchInsertToDB('ut_delivery_post_Interface_data', item)
        print("接口传入表t数量更新", status_2)
        print(item)

        if delete_set:
            deteleSQL = "delete  from  ut_delivery_interface_qty where {}".format(' or '.join([i for i in delete_set]))
            print(deteleSQL)
            status = db.exec_sql(deteleSQL)
        status_3 = db.batchInsertToDB('ut_delivery_interface_qty', qty_data)
        print("接口传入数量关系更新", status_2)
        if update_dn_item:
            # status_u = db.batchUpdateToDB('t_dn_item', update_dn_item)
            update_dn_qty(update_dn_item)
            # print("dn_item表数量更新",status_u)

        if status_1 >= 0 and status_2 >= 0:
            type1 = 'S'
            msg1 = str(dn_sn) + '数据已接收'

    return {
        "guid": guid,
        "type": type1,
        "message": msg1
    }


def delivery_post(payload, user_id):
    """入口①: 前端发货过账落表(不碰 SAP)。校验 → 行号匹配 → 批次匹配 → 单位换算 → 写接口表。"""
    print(payload)
    """
    :param payload:
           结构如下:
           {'payload': {
        "guid":"{{$string.uuid}}",
        "data": {
            "header": [
                {
                    "uf_guid": "{{$string.uuid}}",
                    "uf_bs_category": "",
                    "uf_dn_sn": "",
                    "uf_posting_date": "2025-09-04",
                    "uf_picking_document":"",
                    "uf_tracking_number": "",
                    "delivery_time":"",

                    "virtual_tracking_number":"",
                    "filed_code1":"",
                    "filed_code2":"",
                    "filed_code3":"",



                    "item": [
                        {
                            "uf_line_id": 1,
                            "uf_dn_item": 1,
                            "uf_batch_item":0
                            "uf_stor_loc_code": "A001",
                            "uf_picked_qty": 11,
                            "uf_picked_base_qty": 11,
                            "uf_picked_parallel_qty": 11,
                            "uf_batch_sn": "2509010001",
                            "uf_mat_code": "2509010001",
                            "uf_lot_no": "",
                            "uf_ZT04": "",
                            "uf_wafer_id": "",
                            "uf_ZT07": "",
                            "uf_ZT18": "",
                            "uf_runcard": "",
                            "uf_box_no": "",
                            "uf_production_date": "",
                            "uf_ZT05": "",
                            "uf_ZT20": "",
                            "uf_ZT21": "",
                            "uf_ZT35": "",
                            "uf_ZT36": "",
                            "uf_ZT37": "",
                            "uf_ZT38": "",
                            "uf_ZT06": "",
                            "uf_ZT48": "",
                            "uf_ZT49": "",
                            "uf_ZT50": "",
                            "uf_ZT51": "",
                            "uf_ZT53": "",
                            "uf_ZT14": "",
                            "uf_ZT15": "",
                            "uf_ZT54": "",
                            "uf_ZT08": "",
                            "uf_ZT09": "",
                            "uf_ZT17": "",
                            "filed_code1":"",
                            "filed_code2":"",
                            "filed_code3":""
                        }

                    ]
                }
            ]
        }
    }}

    :return:
           结构如下:
           {'code':'','msg':''}
    """

    print('payload-----', payload)
    guid = payload["guid"]
    data = payload.get("data")

    # 1. 抬头校验
    err, head, dict_head = _validate_delivery_head(data, guid)
    if err:
        return err
    # 账期检查
    dn_sn = dict_head.get('uf_dn_sn', '')
    posting_date = dict_head.get('uf_posting_date', '')
    uf_tracking_number = dict_head.get('uf_tracking_number', '')

    db = DbHelper()

    # 2. 公司代码 + 账期校验
    err = _check_dn_company_period(dn_sn, posting_date, guid, db)
    if err:
        return err

    from DxBusinessDataConvertUtil import convert_material_unit_qty_new  # type:ignore

    item = dict_head['item']

    dict_head['uf_guid'] = guid
    dict_head['uf_virtual_tracking_number'] = dict_head['virtual_tracking_number']

    # 3. 拣配单号已存在时不进行下面步骤: 早返回落表
    if dict_head['uf_picking_document'] != '':
        return _picking_document_early_return(head, item, dict_head, dn_sn, guid)

    # 4. 行号匹配逻辑
    item, lv_error = _match_dn_lines(item, dn_sn, db)
    if lv_error != '':
        return {
            "guid": guid,
            "type": 'E',
            "message": lv_error
        }
    # ----------- 行号匹配逻辑

    qty_dict = {}
    msg_lst = ''

    # 5. 初始属性字段(结果当前未使用, 保留原查询)
    _load_initial_attributes(db)

    # 6. 批次匹配逻辑
    output, msg_lst = _match_batches_for_items(item, db)
    if msg_lst != '':
        print(msg_lst)
        return {
            "guid": guid,
            "type": 'E',
            "message": msg_lst
        }
    item = output
    # print('item',item)

    # 7. 公共字段 + 单位换算 + 数量记录
    delete_set = set()
    for row in item:
        _fill_row_common_fields(row, dict_head)
        _convert_row_uom_and_record(row, dict_head, db, qty_dict, delete_set)

    if msg_lst != '':
        return {
            "guid": guid,
            "type": 'E',
            "message": msg_lst
        }

    # 8. 落表
    return _persist_delivery_interface(head, item, qty_dict, delete_set, dn_sn, guid)



# =========================== 4. 步骤日志 ===========================


def uplogdata(log_dict, update_type):
    # 更新日志表
    update_log = []
    sql = "select id from ut_delivery_post_step_log where uf_guid = '{}' and uf_dn_sn = '{}' ".format(
        log_dict['uf_guid'], log_dict['uf_dn_sn'])
    data = db.query_sql(sql)
    if data:
        log_dict['id'] = data[0]['id']
    update_log.append(log_dict)
    if update_type == 1:
        sql = "update ut_delivery_post_Interface_head set uf_posting_status  = 'S' where uf_guid = '{}'  ".format(
            log_dict['uf_guid'])
        db.exec_sql(sql)


def uplogdata2(log_dict, update_status):
    # 更新日志表
    update_log = []
    status_log = 0
    update_status = 0
    sql = "select id from ut_delivery_post_step_log_item where uf_guid = '{}' and uf_line_id = '{}' ".format(
        log_dict['uf_guid'], log_dict['uf_line_id'])
    data = db.query_sql(sql)
    if data:
        update_status = 1
        log_dict['id'] = data[0]['id']
    update_log.append(log_dict)
    if update_status == 0:
        status_log = db.batchInsertToDB('ut_delivery_post_step_log_item', update_log)
        db.dbCommit()
    else:
        status_log = db.batchUpdateToDB('ut_delivery_post_step_log_item', update_log)
        db.dbCommit()



# ============================ 5. 过账主流程(入口②) 状态机 ============================

def _build_step_log_sql(guid):
    """构造 SQL(原 delivery_post_main 内联, 逐字符保留)。"""
    return f"""
        select *
        from ut_delivery_post_step_log as a 
        where 1 = 1 and a.uf_guid = '{guid}'
    """
def _build_step_log_item_sql(guid):
    """构造 SQL(原 delivery_post_main 内联, 逐字符保留)。"""
    return f"""
        select 
        * 
        from ut_delivery_post_step_log_item
        where 1 = 1 and uf_guid = '{guid}'
    """
def _build_posting_check_sql(item_condition_part):
    """构造 SQL(原 delivery_post_main 内联, 逐字符保留)。"""
    return f"""
        select 
            a.dn_sn,
        a.dn_item,
        a.plant_code,
        a.stor_loc_code,
        a.transaction_uom,
        a.actual_plant as dn_actual_plant,
        a.uf_actual_stor as  dn_actual_stor,
        b.actual_plant,
        b.actual_stor,
        b.uf_actual_plant2,
        b.uf_actual_stor2,
        b.picking_document,
        b.batch_item,
        c.uf_is_merge_push_mail,  
        a.uf_is_integer,
        a.packing_status,
        a.mat_code,
        a.parallel_uom,
        a.basic_uom,
        a.basic_qty,
        a.create_id,
        b.mat_code as ipn,
        a.mat_code as epn,
        ua.uf_pur_group  asprod_group,
        ua2.uf_pur_group  as dn_prod_group,
        a.planned_delivery_quantity
        from  t_dn_item  as a
        left join t_dn_inventory_alloc as b
        on a.dn_sn = b.dn_sn 
        and a.dn_item = b.dn_item 
        left join t_system_user as u1 on u1.id = b.create_id
        left join ut_user_pur_group_relationship as ua on ua.uf_account = u1.account 
        left join t_system_user as u2 on u2.id = a.create_id
        left join ut_user_pur_group_relationship as ua2 on ua2.uf_account = u2.account 
        
        left join t_dn_header as c on c.dn_sn = a.dn_sn
        where 1=1 {item_condition_part}
    """

def delivery_post_main(do_sn_items, posting_date, uf_tracking_number, guid, user_id):
    """入口②: 过账主流程(状态机)。

    step: 0/11=待拣配, 12=直接过账, 99=已过账(拒绝重复)。
    流程: 行项分类(是否需公司间调拨ITO) → 创建/执行ITO → 拣配 → 发货过账(dnPostFunc)。
    注: 上下文加载与 classify 循环耦合较紧, 保持内联; 仅 SQL 抽到 builder。

    :param payload:
           结构如下:
           {'payload': 'data': [{'posting_date': '123444', 'dn_sn': '','dn_item':'',
                                'picking_document':'','batch_item':'',
                                'stor_loc_code':'','picked_qty':11,'picked_base_qty':11,'batch_sn':''},
           {}]

    :return:
           结构如下:
           {'code':'','msg':''}
    """

    # guid = payload["guid"]
    ev_type = ''
    ev_msg = ''
    update_status = 0
    virtual_tracking_number = do_sn_items[0]['virtual_tracking_number']

    # do_sn_items = payload.get("data")

    item_condition_part = ''
    if do_sn_items:
        item_condition_part += build_query(do_sn_items, 'a')
    else:
        return {
            "guid": guid,
            "type": "E",
            "message": '请传输需要过账的数据'
        }
    dn_sn = do_sn_items[0]['uf_dn_sn']
    sql_log = _build_step_log_sql(guid)

    sql_log2 = _build_step_log_item_sql(guid)

    sql = _build_posting_check_sql(item_condition_part)

    db = DbHelper()
    check_data = db.query_sql(sql)
    print(sql)

    log_data = db.query_sql(sql_log)
    log_data2 = db.query_sql(sql_log2)

    dict_h = {}
    dict_pack = {}
    for each in check_data:
        user_id = each['create_id']
        key = str(each['dn_sn']) + str(each['dn_item']) + str(each['batch_item'])
        if key in dict_h:
            dict_h[key].append(each)
        else:
            dict_h[key] = []
            dict_h[key].append(each)

    dict_log = {}
    for each in log_data:
        key = str(each['uf_dn_sn']) + str(each['uf_dn_item']) + str(each['uf_batch_sn'])
        if key in dict_log:
            dict_log[key] = each
        else:
            dict_log[key] = {}
            dict_log[key] = each

    step = 0
    log_dict = {}
    log_dict['uf_guid'] = guid
    log_dict['uf_dn_sn'] = dn_sn
    log_dict['uf_dn_item'] = 0
    log_dict['uf_batch_sn'] = ''
    log_dict['uf_stor_loc_code'] = ''
    log_dict['uf_picked_qty'] = 0
    log_dict['uf_ex_type'] = ''
    log_dict['uf_sto_po_sn'] = ''
    log_dict['uf_sto_so_sn'] = ''
    log_dict['uf_sto_dn_sn'] = ''
    log_dict['uf_sto_po_doc'] = ''
    log_dict['uf_sto_dn_doc'] = ''
    log_dict['uf_picking_document'] = ''
    log_dict['uf_mat_doc_sn'] = ''
    if log_data:
        log_dict = log_data[0]
        print(log_data)
        if log_data[0]['uf_mat_doc_sn'] != '':
            step = 99
        # if log_data[0]['uf_ex_type'] == '拣配过账':
        if log_data[0]['uf_picking_document'] != '':
            # step = 11 需要先执行拣配
            step = 12
        if log_data[0]['uf_ex_type'] == '过账':
            # step = 12 直接执行过账
            step = 12

    if step == 99:
        return {
            "guid": guid,
            "type": "E",
            "message": '该单据已存在过账记录，不允许重复过账'
        }

    dic_log2 = {}
    for row in log_data2:
        key = str(row['uf_line_id'])
        if key in dic_log2:
            pass
        else:
            dic_log2[key] = {}
            dic_log2[key] = row

    print('==-', do_sn_items)
    print('单据状态', dict_h)
    pick_batch = []
    pick_batch_row = {}
    dic_ito = {}
    # 先判断每行是否需要调拨，是否拣配完成 ，都达成的情况下整单过账
    for row in do_sn_items:
        key11 = '1'
        key_ito1 = '1'
        key = str(row['uf_dn_sn']) + str(row['uf_dn_item']) + str(row['uf_batch_item'])
        if key in dict_h:
            for row_c in dict_h[key]:
                pick_batch_row = {}
                pick_batch_row['dn_sn'] = row_c['dn_sn']
                pick_batch_row['dn_item'] = row_c['dn_item']
                pick_batch_row['plant_code'] = row_c['plant_code']
                pick_batch_row['stor_loc_code'] = row_c['stor_loc_code']
                pick_batch_row['actual_plant'] = row_c['actual_plant']
                pick_batch_row['actual_stor'] = row_c['actual_stor']
                pick_batch_row['mat_code'] = row['uf_mat_code']
                pick_batch_row['external_mat_code'] = row_c['mat_code']

                pick_batch_row['parallel_uom'] = row_c['parallel_uom']
                pick_batch_row['basic_uom'] = row_c['basic_uom']
                pick_batch_row['basic_qty'] = row_c['basic_qty']
                pick_batch_row['planned_delivery_quantity'] = row_c['planned_delivery_quantity']

                pick_batch_row['picked_parallel_qty'] = row.get('uf_picked_parallel_qty', 0)

                pick_batch_row['packing_date'] = posting_date
                pick_batch_row['picked_qty'] = row['uf_picked_qty']
                pick_batch_row['picked_base_qty'] = row['uf_picked_base_qty']
                pick_batch_row['batch_sn'] = row['uf_batch_sn']
                pick_batch.append(pick_batch_row)

                ito_status1 = 0
                ito_status2 = 0

                if key11 in dic_log2:
                    # 判断是否存在预留单号 或者 拣配单号
                    if dic_log2[key11]['uf_doc_sn1'] != '':
                        ito_status1 = 1
                    if dic_log2[key11]['uf_doc_sn2'] != '':
                        ito_status2 = 1
                print(dic_log2)
                print(ito_status2, ito_status1)
                if row_c.get('packing_status', '') == 'A' and row_c.get('dn_actual_plant', '') == row_c.get(
                        'plant_code', ''):
                    # 步骤日志更新数据
                    if step == 0:
                        log_dict['uf_ex_type'] = '拣配过账'

                    continue
                # 1.拣配状态 = 'A' and actual_plant != ''
                if row_c.get('packing_status', '') == 'A' and row_c.get('dn_actual_plant', '') != row_c.get(
                        'plant_code', ''):
                    if ito_status1 == 1:
                        continue
                    param_ito = {
                        "from_plant": row_c.get('dn_actual_plant', ''),
                        "to_plant": row_c.get('plant_code', ''),
                        "from_stor": row_c.get('dn_actual_stor', ''),
                        "to_stor": row_c.get('stor_loc_code', ''),
                        "transaction_uom": row_c.get('transaction_uom', ''),
                        "transaction_qty": row['uf_picked_qty'],
                        "batch_sn": row['uf_batch_sn'],
                        "mat_code": row['uf_mat_code'],
                        "external_mat_code": row_c.get('mat_code', ''),
                        "pur_group": row_c.get('dn_prod_group', ''),
                        "dn_sn": row_c['dn_sn'],
                        "dn_item": row_c['dn_item'],

                        "uf_parallel_qty": row.get('uf_picked_parallel_qty', 0),
                        "uf_base_aty": row.get('uf_picked_qty', 0),
                        "posting_date": posting_date,
                        "user_id": user_id
                    }
                    if key_ito1 in dic_ito:
                        dic_ito[key_ito1]['A'].append(param_ito)
                    else:
                        dic_ito[key_ito1] = {}
                        dic_ito[key_ito1]['A'] = []
                        dic_ito[key_ito1]['A'].append(param_ito)

                    continue
                if row_c.get('packing_status', '') != 'A':

                    if row_c.get('uf_actual_plant2', '') != '' and row_c.get('uf_actual_stor2', '') != '' and row_c.get(
                            'uf_actual_plant2', '') != row_c.get('actual_plant', '') and ito_status2 == 0:
                        # 存在实际发货工厂且与发货工厂不同 执行公司间调拨
                        param_ito = {
                            "from_plant": row_c.get('uf_actual_plant2', ''),
                            "to_plant": row_c.get('actual_plant', ''),
                            "from_stor": row_c.get('uf_actual_stor2', ''),
                            "to_stor": row_c.get('actual_stor', ''),
                            "transaction_uom": row_c.get('transaction_uom', ''),
                            "transaction_qty": row['uf_picked_qty'],
                            "batch_sn": row['uf_batch_sn'],
                            "mat_code": row_c.get('ipn', ''),
                            "external_mat_code": row_c.get('external_mat_code', ''),
                            "pur_group": row_c.get('prod_group', ''),
                            "dn_sn": row_c['dn_sn'],
                            "dn_item": row_c['dn_item'],
                            "uf_parallel_qty": row.get('uf_picked_parallel_qty', 0),
                            "uf_base_aty": row.get('uf_picked_qty', 0),
                            "posting_date": posting_date,
                            "user_id": user_id
                        }
                        if key_ito1 in dic_ito:
                            dic_ito[key_ito1]['B'].append(param_ito)
                        else:
                            dic_ito[key_ito1] = {}
                            dic_ito[key_ito1]['B'] = []
                            dic_ito[key_ito1]['B'].append(param_ito)


                    if row_c.get('actual_plant', '') != '' and row_c.get('actual_stor', '') != '' and row_c.get(
                            'plant_code', '') != row_c.get('actual_plant', '') and ito_status1 == 0:
                        # 存在实际发货工厂且与发货工厂不同 执行公司间调拨
                        param_ito = {
                            "from_plant": row_c.get('actual_plant', ''),
                            "to_plant": row_c.get('plant_code', ''),
                            "from_stor": row_c.get('actual_stor', ''),
                            "to_stor": row_c.get('stor_loc_code', ''),
                            "transaction_uom": row_c.get('transaction_uom', ''),
                            "transaction_qty": row['uf_picked_qty'],
                            "batch_sn": row['uf_batch_sn'],
                            "mat_code": row_c.get('ipn', ''),
                            "external_mat_code": row_c.get('external_mat_code', ''),
                            "pur_group": row_c.get('prod_group', ''),
                            "dn_sn": row_c['dn_sn'],
                            "dn_item": row_c['dn_item'],
                            "uf_parallel_qty": row.get('uf_picked_parallel_qty', 0),
                            "uf_base_aty": row.get('uf_picked_qty', 0),
                            "posting_date": posting_date,
                            "user_id": user_id
                        }
                        # print(param_ito)
                        if key_ito1 in dic_ito:
                            dic_ito[key_ito1]['A'].append(param_ito)
                        else:
                            dic_ito[key_ito1] = {}
                            dic_ito[key_ito1]['A'] = []
                            dic_ito[key_ito1]['A'].append(param_ito)

                    if row_c.get('actual_plant', '') == '' and row_c.get('uf_actual_plant2', '') == '':
                        # 下一步执行过账
                        step = 12
                        log_dict['uf_ex_type'] = '过账'

                        break
                    # 步骤日志更新数据
                    if step == 0:
                        step = 12
                        log_dict['uf_ex_type'] = '过账'
                        break

    # 判断是否存在调拨单 存在则需要校验是否调拨 调拨完才能拣配
    print('step', step, pick_batch)

    if (step == 11 or step == 0) and pick_batch == []:
        return {
            "guid": guid,
            "type": "E",
            "message": '该单据无法被拣配'
        }

    for key, value in dic_ito.items():
        row_log = {}
        row_log['uf_guid'] = guid
        row_log['uf_line_id'] = key
        if value.get('A', []) != []:
            pass
            code, msg, uf_ito_sn = ito_param(value['A'])

            # row_log['uf_doc_sn1'] =
            if uf_ito_sn:
                row_log['uf_doc_sn1'] = uf_ito_sn
            else:
                return {
                    "guid": guid,
                    "type": "E",
                    "message": '调拨单创建失败' + msg
                }

            row_log['uf_ex_type'] = '调拨单号'
            uplogdata2(row_log, 0)
            log_data2.append(row_log)

        if value.get('B', []) != []:
            pass
            code, msg, uf_ito_sn = ito_param(value['B'])

            # row_log['uf_doc_sn1'] =
            if uf_ito_sn:
                row_log['uf_doc_sn2'] = uf_ito_sn
            else:
                return {
                    "guid": guid,
                    "type": "E",
                    "message": '调拨单创建失败' + msg
                }

            row_log['uf_ex_type'] = '调拨单号'
            uplogdata2(row_log, 0)
            log_data2.append(row_log)

    sql_log2 = _build_step_log_item_sql(guid)
    db1 = DbHelper()

    log_data2 = db1.query_sql(sql_log2)

    if log_data2:
        print('公司间调拨===========================================')
        lv_error = ''
        from Z_TransferOrderCreate import post as ito_post  # type:ignore
        print(log_data2)
        for row in log_data2:
            if row.get('uf_doc_sn1', '') != '' and row.get('uf_status1', '') != 'S':
                code, msg = ito_post(row['uf_doc_sn1'], user_id)
                if code == 200:
                    row['uf_status1'] = 'S'
                    uplogdata2(row, 1)
                else:
                    row['uf_status1'] = 'E'
                    row['uf_msg'] = msg
                    uplogdata2(row, 1)
                    lv_error = 'X'
            if row.get('uf_doc_sn2', '') != '' and row.get('uf_status2', '') != 'S':
                code, msg = ito_post(row['uf_doc_sn2'], user_id)
                if code == 200:
                    row['uf_status2'] = 'S'
                    uplogdata2(row, 1)
                else:
                    row['uf_status2'] = 'E'
                    row['uf_msg'] = msg
                    uplogdata2(row, 1)
                    lv_error = 'X'
        if lv_error == 'X':
            return {
                "guid": guid,
                "type": "E",
                "message": '公司间调拨失败' + msg
            }
        print('公司间调拨-----------------------------------')

    if pick_batch and (step == 11 or step == 0):
        print('执行拣配')
        # 拣配列表不为空 进行拣配
        code, msg, picking_document = SaveInventoryPickUp(pick_batch, user_id)
        print(code, msg, picking_document)
        if code == 200:
            # 步骤日志更新数据
            log_dict['uf_picking_document'] = 'S'
            sql_pick = f"""
            select picking_document  from t_dn_inventory_alloc
            where 1 = 1 and dn_sn = '{dn_sn}'
        """
            dbp = DbHelper()

            pick_numdata = dbp.query_sql(sql_pick)
            print('获取拣配单号', pick_numdata)
            if pick_numdata:
                log_dict['uf_picking_document'] = pick_numdata[0]['picking_document']
            uplogdata(log_dict, 0)
            step = 12
        else:
            code = 500
            ev_msg = '拣配失败' + msg
            ev_type = 'E'
            log_dict['uf_msg'] = ev_msg
            uplogdata(log_dict, 0)

    print("过账前", step)
    # 过账处理
    if step == 12:
        print('执行过账')
        pram_data = GetDnPostQuery(dn_sn, posting_date, uf_tracking_number)
        print("过账查询的拣配数据", pram_data)
        if pram_data == []:
            ev_msg = '未获取到过账数据'
            ev_type = 'E'
            log_dict['uf_msg'] = "过账失败：" + ev_msg
        else:
            pass
            # {code: 400, msg: "请查看详细信息", data: [{"message":"","mat_doc_sn":""}], display: {}, page: {}, rule: {}}
            response = dnPostFunc(pram_data).__dict__
            print(response)
            if response['code'] == 200:
                mat_doc_sn = response['data'][0]['mat_doc_sn']
                # 步骤日志更新数据
                log_dict['uf_mat_doc_sn'] = mat_doc_sn
                year = posting_date[0:4]
                log_dict['uf_year'] = year
                ev_msg = '过账成功，凭证号：' + str(mat_doc_sn)
                log_dict['uf_msg'] = ev_msg
                ev_type = 'S'
                uplogdata(log_dict, 1)
                if mat_doc_sn != '':
                    db1 = DbHelper()
                    sql = f"update  t_md_header set uf_note5 = '{virtual_tracking_number}' where mat_doc_sn = '{mat_doc_sn}' and year = '{year}' "
                    status = db.exec_sql(sql)
                    print(status, sql)
            else:
                message = response['data'][0]['message']
                ev_msg = message
                ev_type = 'E'
                log_dict['uf_msg'] = "过账失败：" + message
                uplogdata(log_dict, 0)
    return {
        "guid": guid,
        "type": ev_type,
        "message": ev_msg
    }


# =========================== 7. 查询 / 工具 ===========================


def build_query(conditions, table_name):
    parts = []
    for cond in conditions:
        sn = cond['uf_dn_sn']
        items = cond['uf_dn_item']
        if items:
            # item_list = ','.join(map(str, items))
            parts.append(f"({table_name}.dn_item = '{items}' and {table_name}.dn_sn = '{sn}' )")

        parts.append(f"({table_name}.dn_sn = '{sn}')")
    return 'AND ' + " OR ".join(parts)


# 拣配 执行
def SaveInventoryPickUp(pickup_batch, user_id):
    picking_document = ''
    code, msg, res_list, _ = inventoryPickUp(pickup_batch, user_id, pickup_batch, test_run=1)
    print("res_list", code, msg, res_list)
    if code == 200:
        picking_document = 'S'
    else:
        msg = res_list[0]['message']

    return code, msg, picking_document


# -------======================公司间调拨
def ito_param(data_ito):
    # """
    # body = {
    # from_plant,
    # to_plant,
    # from_stor,
    # to_stor,
    # uf_ipn,
    # transaction_uom
    # transaction_qty
    # batch_sn
    # mat_code
    # pur_group

    # }

    # """
    from Z_TransferOrderCreate import ito_save  # type:ignore

    item = []
    line_id = 0
    for body in data_ito:
        line_id += 1
        pass
        head = {}
        head['uf_ito_type'] = 'ITO'
        head['uf_from_plant_code'] = body["from_plant"]
        head['uf_to_plant_code'] = body["to_plant"]
        head['uf_pur_group'] = body["pur_group"]
        head['uf_ito_method'] = 'B'
        head['uf_is_in_kind'] = 0
        head['uf_document_date'] = body["posting_date"]

        dict_item = {}
        dict_item['uf_from_stor_loc_code'] = body["from_stor"]
        dict_item['uf_to_stor_loc_code'] = body["to_stor"]
        dict_item['uf_is_integer'] = 0
        dict_item['uf_batch_sn'] = body["batch_sn"]
        dict_item['uf_transaction_qty'] = body["transaction_qty"]
        dict_item['uf_ipn'] = body["mat_code"]
        dict_item['uf_mat_code'] = body["external_mat_code"]

        dict_item['uf_dn_sn'] = body["dn_sn"]
        dict_item['uf_dn_item'] = body["dn_item"]

        dict_item['uf_parallel_qty'] = body["uf_parallel_qty"]
        dict_item['uf_base_aty'] = body["uf_base_aty"]

        dict_item['uf_ito_items'] = line_id

        if body["external_mat_code"] == '':
            dict_item['uf_mat_code'] = body["mat_code"]
        dict_item['uf_transaction_uom'] = body["transaction_uom"]
        item.append(dict_item)
    code, msg, uf_ito_sn = ito_save(head, item, body['user_id'])
    print(code, msg, uf_ito_sn)
    return code, msg, uf_ito_sn


# ===========================================交货单过账 部分
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
# =========================== 8. 单位换算 ===========================


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



# ============================ 9. 过账参数查询 ============================

_DN_POST_COLUMNS = '''
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

def _build_dn_post_sql(dn_sn):
    """构造交货单过账查询SQL(原 GetDnPostQuery 内联, 逐字符保留)。"""
    return '''
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
                alloc.posting_status = 'A'
                # AND header.packing_status = 'C'
                # AND (header.posting_status = 'A' or header.posting_status = 'B')
                # AND item.deleted_mark != "1" AND item.lock_flag != "1"
                AND item.dn_sn in ('{}') 
                group by item.dn_sn,
item.dn_item 
            '''.format(_DN_POST_COLUMNS, dn_sn)

def GetDnPostQuery(dn_sn, posting_date, uf_tracking_number):
    """交货单过账需要参数获取查询"""
    query_sql = _build_dn_post_sql(dn_sn)

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
    if query_data:

        field_names = [item.get('field') for item in display]
        property_info, property_display = get_additional_property()
        # cover_uom_list = get_cover_uom_db()

        for record in query_data:
            record['posting_date'] = posting_date
            record['express_delivery'] = uf_tracking_number

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
                        display.append(field_display)  # type:ignore

            if record.get('special_inventory_status1', '') != 'S':
                del record['so_sn']
                del record['so_items']

            mat_code = record.get('mat_code')
            plant_code = record.get('plant_code')
            transaction_uom = record.get('transaction_uom')
            transaction_qty = record.get('transaction_qty')
            record['basic_qty'] = get_basic_qty(mat_code, plant_code, transaction_uom, transaction_qty)

    return query_data


# ===========================================交货单过账 部分


# =========================== 6. 定时任务(后台推送 EMES) ===========================


def eMes_push_data():
    '''
    纯后台推送  定时任务  EMES
    '''
    # cbk = Callback()
    # body = json.loads(cbk.param())
    # po_sn = body.get("po_sn", "")  # 采购订单号

    db_helper = DbHelper()
    result = {}

    user_id = 11

    head_sql = "SELECT * FROM ut_delivery_post_Interface_head WHERE uf_posting_status  != 'S' and uf_reversal_mark  = '' and uf_bs_category = '29' order by uf_posting_time "
    head_data = db_helper.query_sql(head_sql)

    item_sql = """
        SELECT t.* FROM ut_delivery_post_Interface_head as h
        left join ut_delivery_post_Interface_data as t
        on h.uf_guid = t.uf_guid
        WHERE h.uf_posting_status  != 'S' and h.uf_reversal_mark  = '' order by uf_posting_time 
    """
    item_data = db_helper.query_sql(item_sql)

    dict_item = {}
    picksn_lst = []
    for i in item_data:
        key = i['uf_guid']
        # if i.get('uf_picking_document','') != '':
        #     picksn_lst.append(i['uf_picking_document'])

        if key in dict_item:
            dict_item[key].append(i)
        else:
            dict_item[key] = []
            dict_item[key].append(i)

    picksn_lst = [i['uf_picking_document'] for i in head_data if i['uf_picking_document'] != '']

    pick_data = []
    dick_pick = {}
    if picksn_lst:
        pick_sql = """
        select * from t_dn_inventory_alloc where picking_document  in ({})
        """.format(','.join([f"'{i}'" for i in picksn_lst]))
        pick_data = db_helper.query_sql(pick_sql)
        for i in pick_data:
            pass
            key = str(i['dn_sn'])
            if key in dick_pick:
                dick_pick[key].append(i)
            else:
                dick_pick[key] = []
                dick_pick[key].append(i)

    if head_data:
        for each in head_data:
            key_guid = each['uf_guid']

            posting_date = each['uf_posting_date']
            uf_tracking_number = each['uf_tracking_number']
            prarm_item = []

            if key_guid in dict_item:
                key = str(each['uf_dn_sn'])
                if key in dick_pick:
                    pass
                    for row in dick_pick[key]:
                        dict_temp = copy.deepcopy(dict_item[key_guid][0])

                        dict_temp['uf_dn_item'] = row['dn_item']
                        dict_temp['uf_picking_document'] = row['picking_document']
                        dict_temp['uf_batch_item'] = row['batch_item']
                        dict_temp['uf_mat_code'] = row['mat_code']
                        dict_temp['uf_stor_loc_code'] = row['stor_loc_code']
                        dict_temp['uf_picked_qty'] = row['picked_qty']
                        dict_temp['uf_picked_base_qty'] = row['picked_base_qty']
                        dict_temp['uf_picked_parallel_qty'] = row['picked_parallel_qty']
                        dict_temp['uf_batch_sn'] = row['batch_sn']
                        dict_temp['virtual_tracking_number'] = each['uf_virtual_tracking_number']
                        prarm_item.append(dict_temp)
                else:
                    for row in dict_item[key_guid]:
                        row['virtual_tracking_number'] = each['uf_virtual_tracking_number']
                        prarm_item.append(row)
            #
            print('job开始执行')
            print(key_guid)
            print(dict_item)
            ret = delivery_post_main(prarm_item, posting_date, uf_tracking_number, key_guid, user_id)
            print(ret)
            print('job开始执行wangc')