"""
@File    : itf_delivery_posting.py
@Author  : yang.zhang.dxdstech.com
@Date    : 2026/6/5 11:16
@explain : 发货过账
"""
import copy
import uuid
from datetime import datetime

from DbHelper import DbHelper  # type:ignore
from DxInventoryPostData import post_data
from logger import LoggerConfig  # type:ignore
from SalePostInterface import dnPostFunc  # type:ignore
from SalesPickInterface import inventoryPickUp  # type:ignore

db = DbHelper()

def delivery_posting(payload, user_id):
    """
    delivery_postinge接口的核心处理函数,接收标准结构的payload进行处理
    :param payload: 过账请求数据，支持两种格式：
                    1. 标准接口结构：{'guid': 'xxx', 'data': {'header': [...]}}
                    2. 文件传参格式：[{'mat_code': 'xxx', 'plant_code': 'xxx', ...}, ...]
    :param user_id: 操作用户ID
    :return: {'type': 'S/E', 'message': 'xxx', 'guid': 'xxx', 'mat_doc_sn': 'xxx'}
    """
    # ===================== 【文件传参 List → 标准接口结构】=====================
    if isinstance(payload, list):
        print(payload, '==== 这是文件传参，开始自动转换结构')
        # 按汇总号分组（同批次处理的单据放在一起）
        item_group = {}
        for index,item in enumerate(payload):
            item_group_key = "line" + str(index)
            if item_group_key not in item_group:
                item_group[item_group_key] = []
            item_group[item_group_key].append(item)
        # 生成最终标准结构
        converted_payloads = []
        for summary_no, items in item_group.items():
            guid = str(uuid.uuid4())
            processed_items = []
            line_id = 1
            for row in items:
                new_row = row.copy()
                new_row['line_id'] = line_id
                line_id += 1
                
                # 设置默认值
                # new_row.setdefault('movement_type', 'D008')
                new_row.setdefault('inventory_status', '0')
                new_row.setdefault('special_inventory_status1', '')
                
                # 数量处理
                if 'transaction_qty' in new_row:
                    new_row['transaction_qty'] = float(new_row['transaction_qty'])
                processed_items.append(new_row)
            new_data = {
                "guid": guid,
                "data": {
                    "header": [{
                        "summary_unique_number": summary_no,
                        "item": processed_items,
                        "delivery_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "uf_posting_date": datetime.now().strftime("%Y-%m-%d"),
                    }]
                }
            }
            converted_payloads.append(new_data)
        # 循环处理每个转换后的payload
        result_list = []
        for p in converted_payloads:
            res = delivery_posting(p, user_id)
            result_list.append(res)
        
        if len(result_list) == 1:
            return result_list[0]
        else:
            # 合并多个结果
            all_messages = [r.get('message', '') for r in result_list]
            has_error = any(r.get('type') == 'E' for r in result_list)
            guids = [r.get('guid', '') for r in result_list]
            mat_doc_sns = [r.get('mat_doc_sn', '') for r in result_list if r.get('mat_doc_sn')]
            return {
                "type": "E" if has_error else "S",
                "message": "; ".join(all_messages),
                "guid": ",".join(guids),
                "mat_doc_sn": ",".join(mat_doc_sns) if mat_doc_sns else ""
            }
    # ===================== 标准接口结构处理 =====================
    print(payload, '==== 这是标准接口结构，开始数据校验')
    guid = payload["guid"]
    data = payload.get("data")
    # 调用字段验证函数
    validate_result = validate_payload(data, guid)

    if validate_result.get('type') == 'E':
        return validate_result
    print("校验完毕")
    # 获取表头数据
    header = data["header"][0]
    # 构建过账参数
    doc_head, doc_items = build_post_params(header, user_id)
    print('过账参数构建完毕，开始过账')
    print("doc_head:", doc_head)
    print("doc_items:", doc_items)
    data = execute_post(doc_head, doc_items, guid, user_id)
    print('过账成功，返回：', data)

    if data.get('type') == 'E':
        return {
            "type": data.get('type'),
            "message": data.get('message'),
            "guid": data.get('guid')
        }
    else:
        return {
            "type": data.get('type'),
            "message": data.get('message'),
            "guid": data.get('guid')
        }


def validate_payload(data, guid):
    """
    根据字段需求验证payload数据
    """
    # 检查表头
    header = data.get("header", [])
    if not header:
        return {"type": "E", "message": "抬头数据不能为空", "guid": guid}

    print('---------------header',header)
    for header_data in header:
        # 过账日期 - 必填
        posting_date = header_data.get("uf_posting_date", "").strip()
        if not posting_date:
            return {"type": "E", "message": "过账日期不能为空", "guid": guid}
        # 汇总号 - 长度限制
        summary_unique_number = header_data.get("summary_unique_number", "").strip()
        if len(summary_unique_number) > 64:
            return {"type": "E", "message": "汇总号长度不能超过64位", "guid": guid}
        # 检查行项目
        items = header_data.get("item", [])
        if not items:
            return {"type": "E", "message": "行项目数据不能为空", "guid": guid}
        for index, item in enumerate(items, 1):
            item_error_prefix = f"行项目[{index}]"
            # 物料 - 必填
            uf_mat_code = item.get("uf_ipn", "").strip()
            if not uf_mat_code:
                return {"type": "E", "message": f"{item_error_prefix}物料不能为空", "guid": guid}
            # 交易数量 - 必填，必须大于0
            transaction_qty = item.get("uf_chip_qty", 0)
            try:
                transaction_qty = float(transaction_qty)
                if transaction_qty <= 0:
                    return {"type": "E", "message": f"{item_error_prefix}交易数量必须大于0", "guid": guid}
            except ValueError:
                return {"type": "E", "message": f"{item_error_prefix}交易数量必须为数字", "guid": guid}

    return {"type": "S", "message": "字段验证通过", "guid": guid}

def build_post_params(header, user_id):
    """
    构建库存过账参数
    """
    db = DbHelper()

    document_date = header.get("uf_document_date")
    posting_date = header.get("uf_posting_date")

    if document_date is None:
        document_date = datetime.now().strftime("%Y-%m-%d")
    if posting_date is None:
        posting_date = datetime.now().strftime("%Y-%m-%d")




    doc_head = {
        "document_category": "",           # 单据种类
        "post_code": "3",                  # 过账代码：3=发料
        "document_date": document_date,
        "posting_date": posting_date,
        "summary_unique_number": header.get("summary_unique_number"),
        "vendor_dn": header.get("vendor_dn"),
        "company_code": '',                # 从工厂获取公司代码
        "remarks_1": "发货过账"
    }

    print("document_date:", document_date)
    print("posting_date:", posting_date)

    # 构建行项目参数
    doc_items = []
    line_id = 0

    for item in header.get("item", []):

        line_id += 1
        # 获取物料基本信息
        mat_code = item['uf_ipn']  # 物料代码
        batch_sn = item.get("uf_batch_sn", "")  # 批次号


        # 公司代码
        company_data = db.query_sql(
        f""" select company_code from t_dn_header where dn_sn = '{item['uf_ito_sn']}' """)
        plant_code = company_data[0]['company_code']

        query_mat_sql = "SELECT basic_uom, parallel_uom,basic_uom FROM t_mmd_material_basic_data WHERE mat_code = {} ".format(repr(mat_code))
        mat_info = db.query_sql(query_mat_sql)
        basic_uom = mat_info[0]['basic_uom'] if mat_info else item['transaction_uom']
        parallel_uom = mat_info[0]['parallel_uom'] if mat_info else ''
        print("获取物料基本信息成功：",mat_info)

        # # 获取工厂对应的公司代码
        # query_plant_sql = "SELECT company_code FROM t_os_company_plant_alloc WHERE plant_code = {} ".format(repr(plant_code))
        # plant_info = db.query_sql(query_plant_sql)
        # if plant_info:
        #     doc_head['company_code'] = plant_info[0]['company_code']
        # print("获取工厂对应的公司代码成功：",plant_info)


        if not item.get("uf_chip_qty"):
            uf_parallel_qty = 0
        else:
            uf_parallel_qty = float(item["uf_chip_qty"])
        print("uf_parallel_qty:",uf_parallel_qty)

        # 构建批次信息
        batch_number, batch_sn = build_batch_number(mat_code, batch_sn, db)
        # 添加动态批次属性 item 字段
        print("构建批次信息成功:",batch_number, batch_sn)
        doc_item = {
            "line_id": line_id,
            "movement_type": item.get("uf_movement_type", "D008"),
            "plant_code": plant_code,
            "stor_loc_code": item["uf_stor_loc_code"],
            "mat_code": mat_code,
            "batch_sn": batch_sn,
            "inventory_status": item.get("inventory_status", "0"),
            "special_inventory_status1": item.get("uf_special_inventory_status1", ""),
            "special_inventory_status2": "",
            "transaction_qty": uf_parallel_qty,  # 交易数量
            "transaction_uom": basic_uom,   # 交易单位
            "basic_qty": uf_parallel_qty,  # 默认等于交易数量
            "parallel_uom": item.get("uf_parallel_uom", parallel_uom), # 平行单位
            "wbs_elements": item.get("uf_wbs_elements", ""),
            "project_sn": item.get("uf_project_sn", ""),
            "vendor_code": item.get("uf_vendor_code", ""),
            "create_id": user_id,
            "batch_number": batch_number,
        }
        doc_items.append(doc_item)

    print("过账数据构建成功:", doc_head, doc_items)
    return doc_head, doc_items

def execute_post(doc_head, doc_items, guid, user_id):
    """
    执行库存过账
    """
    print('过账传入:', doc_head, doc_items)
    
    try:
        # 调用库存过账接口
        # 参数说明：
        #   user_id: 操作用户ID
        #   head: 表头数据
        #   items: 行项目数据
        code, msg, error_list, mat_doc_sn, year = post_data('0', user_id, doc_head, doc_items)
        
        print('过账返回:', code, msg, error_list, mat_doc_sn, year)
        if code == 200 and mat_doc_sn:
            return {
                "type": "S",
                "message": f"过账成功，物料凭证号: {mat_doc_sn}",
                "guid": guid,
                "mat_doc_sn": mat_doc_sn,
                "year": year
            }
        else:
            error_msg = msg
            if error_list:
                error_msg += "; ".join([str(e) for e in error_list])
            return {
                "type": "E",
                "message": f"过账失败: {error_msg}",
                "guid": guid
            }
    except Exception as e:
        return {
            "type": "E",
            "message": f"过账异常: {str(e)}",
            "guid": guid
        }
    
def get_batch_attribute_mult(mat_code_list, batch_sn_list, db):

    """
    批量获取批次属性信息
    :param mat_code_list: 物料编码列表
    :param batch_sn_list: 批次号列表
    :param db: 数据库连接
    :return: {"mat_code+batch_sn": [批次属性字典列表]}
    """

    dict_batch_number = {}
    if not mat_code_list or not batch_sn_list:
        return dict_batch_number
    mat_code_list = list(set(mat_code_list))
    batch_sn_list = list(set(batch_sn_list))
    
    # 查询批次基本属性
    query_sql = """
        SELECT * FROM t_batch_number 
        WHERE mat_code in ('{}') AND batch_sn in ('{}')
    """.format("','".join(mat_code_list), "','".join(batch_sn_list))
    batch_data = db.query_sql(query_sql)
    
    # 构建字典
    for item in batch_data:
        key = item['mat_code'] + item['batch_sn']
        if key not in dict_batch_number:
            dict_batch_number[key] = []
        dict_batch_number[key].append(item)
    
    return dict_batch_number

def initialization_batch_number(db):
    """
    获取批次号结构模板（从数据库表结构）
    :param db: 数据库连接
    :return: 批次号默认结构字典
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
    print("查询批次号结构:",table)
    data = {}
    for each in table:
        if each["data_type"] in ('decimal', 'double', 'tinyint', 'int'):
            data[each["field_name"]] = 0
        else:
            data[each["field_name"]] = each["default_value"] if each["default_value"] else ''
    print("初始化批次号结构:",data)
    return data

def build_batch_number(mat_code, batch_sn, db):
    """
    构建批次信息
    :param mat_code: 物料编码
    :param batch_sn: 批次号
    :param db: 数据库连接
    :return: 批次信息字典
    """
    print("build_batch_number:", mat_code, batch_sn)
    
    # 如果批次号为空，生成批次号
    if not batch_sn:
        batch_sn = get_batch_sn_info(mat_code,db)
        batch_sn = batch_sn.get("batch_sn")
    if not batch_sn or not mat_code:
        return {}
    # 先从数据库查询批次信息
    print("查询批次信息:", mat_code, batch_sn)
    query_sql = "SELECT * FROM t_batch_number WHERE mat_code = {} AND batch_sn = {}".format(repr(mat_code), repr(batch_sn))
    batch_data = db.query_sql(query_sql)
    print("查询批次信息:", batch_data)
    # 使用数据库查询结果
    batch_number = batch_data[0]
    return batch_number, batch_sn

def get_batch_sn_info(mat_code, db):
    """
    获取批次号信息
    """
    query_sql = "SELECT batch_sn FROM t_batch_number WHERE mat_code = {}".format(repr(mat_code))
    batch_data = db.query_sql(query_sql)
    print("查询批次号batch_data:", batch_data)
    return batch_data[0]

def delivery_posting_main(do_sn_items, posting_date, uf_tracking_number, guid, user_id):
    """
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
    sql_log = f"""
    select *
    from ut_delivery_post_step_log as a 
    where 1 = 1 and a.uf_guid = '{guid}'
"""

    sql_log2 = f"""
    select 
    * 
    from ut_delivery_post_step_log_item
    where 1 = 1 and uf_guid = '{guid}'
    """

    sql = f"""
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
        if log_data[0]['uf_ex_type'] == '调拨减配过账':
            pass
        if log_data[0]['uf_ex_type'] == '公司间调拨减配过账':
            pass

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
                        pass
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

    sql_log2 = f"""
    select 
    * 
    from ut_delivery_post_step_log_item
    where 1 = 1 and uf_guid = '{guid}'
    """
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


def GetDnPostQuery(dn_sn, posting_date, uf_tracking_number):
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
                    alloc.posting_status = 'A'
                    # AND header.packing_status = 'C'
                    # AND (header.posting_status = 'A' or header.posting_status = 'B')
                    # AND item.deleted_mark != "1" AND item.lock_flag != "1"
                    AND item.dn_sn in ('{}') 
                    group by item.dn_sn,
item.dn_item 
                '''.format(columns, dn_sn)

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
