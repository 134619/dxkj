"""
@File    : itf_delivery_posting.py
@Author  : yang.zhang.dxdstech.com
@Date    : 2026/6/5 11:16
@explain : 发货过账
"""
import copy
import uuid
from datetime import datetime
from decimal import Decimal, getcontext

from DbHelper import DbHelper  # type:ignore
from SalePostInterface import dnPostFunc  # type:ignore
from SalesPickInterface import inventoryPickUp  # type:ignore
from Z_generate_batch_sn import get_batch_sn_info  # 导入批次查询方法

# 设置Decimal的精度
getcontext().prec = 20
keep_precise = Decimal('0.00000000')
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
    # ===================== 【过账逻辑：与 Z_post_emes_data_SD 中 uf_bs_category='29' 一致】=====================
    # 批次解析(get_batch_sn_info) → delivery_posting_main(调拨→拣配→dnPostFunc过账)
    result = post_via_delivery_main(header, guid, user_id)
    print('过账完成，返回：', result)
    return {
        "type": result.get('type'),
        "message": result.get('message'),
        "guid": result.get('guid', guid)
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



def post_via_delivery_main(header, guid, user_id):
    """
    与 Z_post_emes_data_SD 中 uf_bs_category='29' 一致的过账流程：
    批次解析(get_batch_sn_info) → delivery_posting_main(调拨→拣配→dnPostFunc过账)，并更新物料凭证备注
    :param header: 标准接口表头 {'summary_unique_number':..., 'item':[...], 'uf_posting_date':...}
    :param guid: 单据GUID
    :param user_id: 操作用户ID
    :return: {'type': 'S/E', 'message': 'xxx', 'guid': 'xxx'}
    """
    db = DbHelper()

    posting_date = header.get("uf_posting_date") or datetime.now().strftime("%Y-%m-%d")
    uf_tracking_number = header.get("uf_tracking_number", "")

    # dn_sn -> process_order_number 反查映射（与 SD 文件保持一致）
    dn_header_data = db.query_sql("select `dn_sn`, `process_order_number` from `t_dn_header`")
    dn_header_data_rev_dic = {i['process_order_number']: i['dn_sn'] for i in dn_header_data}

    data_item_all = []
    for item in header.get("item", []):
        mat_code = item.get("uf_ipn", "") or item.get("uf_mat_code", "")
        batch_sn = item.get("uf_batch_sn", "")
        uf_dn_sn = item.get("uf_ito_sn", "") or item.get("uf_dn_sn", "")
        uf_dn = item.get("uf_dn", "")
        uf_dn_item = item.get("uf_ito_item", 0) or item.get("uf_dn_item", 0) or item.get("uf_dn_project", 0)
        plant_code = item.get("uf_plant_code", "") or item.get("uf_plant", "")
        stor_loc_code = item.get("uf_stor_loc_code", "")
        qty = float(item.get("uf_chip_qty", 0) or item.get("uf_qty", 0) or item.get("uf_transaction_qty", 0) or 0)

        # 若未直接传入 dn_sn，尝试通过 process_order_number 反查
        if not uf_dn and uf_dn_sn and uf_dn_sn in dn_header_data_rev_dic:
            uf_dn = dn_header_data_rev_dic[uf_dn_sn]

        # 获取公司代码
        company_code = item.get("uf_company_code", "")
        if not company_code and plant_code:
            company_info = db.query_sql(
                "select `company_code` from `t_os_company_plant_alloc` where `plant_code` = '{}'".format(plant_code))
            if company_info:
                company_code = company_info[0]['company_code']
        if not company_code and uf_dn_sn:
            header_info = db.query_sql(
                "select `company_code` from `t_dn_header` where `dn_sn` = '{}'".format(uf_dn_sn))
            if header_info:
                company_code = header_info[0]['company_code']

        # 获取物料单位信息
        mat_info = db.query_sql(
            "SELECT basic_uom, parallel_uom FROM t_mmd_material_basic_data WHERE mat_code = {}".format(repr(mat_code)))
        basic_uom = mat_info[0]['basic_uom'] if mat_info else item.get('transaction_uom', '')
        parallel_uom = mat_info[0]['parallel_uom'] if mat_info else ''

        # ===================== 【调用 get_batch_sn_info 获取批次库存】=====================
        batch_query_data = {
            "company_code": company_code,
            "mat_code": mat_code,
            "count": qty,
            "uf_ZT04": item.get("uf_lot_no", ""),
            "uf_ZWAFERNO": item.get("uf_wafer_id", ""),
            "uf_ZT18": item.get("uf_date_code", ""),
            "receive_date": item.get("uf_receive_date", ""),
            "uf_runcard": item.get("uf_runcard", ""),
            "uf_box_no": item.get("uf_box_no", ""),
            "uf_electroplating_date": item.get("uf_electroplating_date", "")
        }
        batch_query_data = {k: v for k, v in batch_query_data.items() if v}

        try:
            msg, batch_sn_info_list = get_batch_sn_info(db, [batch_query_data])
            print("批次查询结果:", msg, batch_sn_info_list)
        except Exception as e:
            return {
                "guid": guid,
                "type": "E",
                "message": f"批次查询异常: {str(e)}"
            }

        # 解析批次查询结果
        batch_result_list = []
        if batch_sn_info_list and len(batch_sn_info_list) > 0:
            batch_result = batch_sn_info_list[0]
            batch_sn_info = batch_result.get("batch_sn_info", [])
            if batch_sn_info:
                for batch_item in batch_sn_info:
                    batch_result_list.append({
                        "batch_sn": batch_item.get("batch_sn", ""),
                        "count": batch_item.get("count", 0)
                    })
            elif batch_sn:
                batch_result_list.append({"batch_sn": batch_sn, "count": qty})
        elif batch_sn:
            batch_result_list.append({"batch_sn": batch_sn, "count": qty})

        if not batch_result_list:
            return {
                "guid": guid,
                "type": "E",
                "message": f"物料 {mat_code} 未匹配上批次"
            }

        # ===================== 【按批次拆分行项目，构建 delivery_posting_main 入参】=====================
        for batch_info in batch_result_list:
            current_batch_sn = batch_info.get("batch_sn", "")
            current_count = float(batch_info.get("count", 0) or 0)
            if current_count <= 0 or not current_batch_sn:
                continue
            row = copy.deepcopy(item)
            row['uf_dn_sn'] = uf_dn or uf_dn_sn
            row['uf_dn'] = uf_dn
            row['uf_dn_item'] = uf_dn_item
            row['uf_dn_project'] = uf_dn_item
            row['uf_mat_code'] = mat_code
            row['uf_plant_code'] = plant_code
            row['uf_plant'] = plant_code
            row['uf_stor_loc_code'] = stor_loc_code
            row['uf_batch_sn'] = current_batch_sn
            row['uf_batch_item'] = item.get("uf_batch_item_id", 0) or item.get("uf_batch_item", 0)
            row['uf_qty'] = current_count
            row['uf_basic_qty'] = current_count
            row['uf_transaction_qty'] = current_count
            row['uf_picked_qty'] = current_count
            row['uf_picked_base_qty'] = current_count
            row['uf_picked_parallel_qty'] = item.get("uf_picked_parallel_qty", 0)
            row['uf_basic_unit'] = basic_uom
            row['uf_sales_unit2'] = item.get("uf_parallel_uom", parallel_uom)
            row['virtual_tracking_number'] = uf_tracking_number
            row['dn_actual_plant'] = item.get("dn_actual_plant", "1000")
            row['dn_actual_stor'] = item.get("dn_actual_stor", "A01")
            data_item_all.append(row)

    if not data_item_all:
        return {
            "guid": guid,
            "type": "E",
            "message": "未获取到可过账的行项目数据"
        }

    print('过账调用入参:', data_item_all, posting_date, uf_tracking_number, guid, user_id)
    # 调用与 uf_bs_category='29' 相同的完整业务流程：调拨→拣配→dnPostFunc过账，并更新物料凭证备注
    ret = delivery_posting_main(data_item_all, posting_date, uf_tracking_number, guid, user_id)
    return ret

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
        return {}, ""
    # 先从数据库查询批次信息
    print("查询批次信息:", mat_code, batch_sn)
    query_sql = "SELECT * FROM t_batch_number WHERE mat_code = {} AND batch_sn = {}".format(repr(mat_code), repr(batch_sn))
    batch_data = db.query_sql(query_sql)
    print("查询批次信息:", batch_data)
    # 使用数据库查询结果
    batch_number = batch_data[0] if batch_data else {}
    return batch_number, batch_sn

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


# -------======================公司间调拨
def ito_param(data_ito):



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
    code,msg,uf_ito_sn  = ito_save(head,item,body['user_id'])
    print(code,msg,uf_ito_sn )
    return code,msg,uf_ito_sn



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