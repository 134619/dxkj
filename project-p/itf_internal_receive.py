"""
@File    : itf_internal_receive.py
@Author  : yang.zhang.dxdstech.com
@Date    : 2026/6/5 11:16
@explain : 内部领用批导接口
"""
import copy
import uuid
from datetime import datetime

from DbHelper import DbHelper
from DxInventoryPostData import post_data
from Z_generate_batch_sn import get_batch_sn_info


def internal_receive(payload, user_id):
    """
    internal_receive接口的核心处理函数,接收标准结构的payload进行处理
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
            posting_date = items[0].get('posting_date', datetime.now().strftime('%Y-%m-%d'))
            document_date = items[0].get('document_date', datetime.now().strftime('%Y-%m-%d'))
            
            processed_items = []
            line_id = 1
            for row in items:
                new_row = row.copy()
                new_row['line_id'] = line_id
                line_id += 1
                
                # 设置默认值
                new_row.setdefault('movement_type', 'D008')
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
                        "posting_date": posting_date,
                        "document_date": document_date,
                        "summary_unique_number": summary_no,
                        "item": processed_items
                    }]
                }
            }
            converted_payloads.append(new_data)
        
        # 循环处理每个转换后的payload
        result_list = []
        for p in converted_payloads:
            res = internal_receive(p, user_id)
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
    db = DbHelper()
    # 调用字段验证函数
    validate_result = validate_payload(data, guid, db)

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
    #     return {
    #     "type": "S",
    #     "message": f"过账成功，物料凭证号: {mat_doc_sn}",
    #     "guid": guid,
    #     "mat_doc_sn": mat_doc_sn,
    #     "year": year
    # }
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



def validate_payload(data, guid, db):
    """
    根据字段需求验证payload数据
    """
    # 检查表头
    header = data.get("header", [])
    if not header:
        return {"type": "E", "message": "抬头数据不能为空", "guid": guid}
    

    for header_data in header:
        # 过账日期 - 必填
        posting_date = header_data.get("posting_date", "").strip()
        if not posting_date:
            return {"type": "E", "message": "过账日期不能为空", "guid": guid}
        
        # 凭证日期 - 必填
        document_date = header_data.get("document_date", "").strip()
        if not document_date:
            return {"type": "E", "message": "凭证日期不能为空", "guid": guid}
        
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
            uf_mat_code = item.get("uf_mat_code", "").strip()
            if not uf_mat_code:
                return {"type": "E", "message": f"{item_error_prefix}物料不能为空", "guid": guid}
            
            # 工厂 - 必填
            uf_plant_code = item.get("uf_plant_code", "").strip()
            if not uf_plant_code:
                return {"type": "E", "message": f"{item_error_prefix}工厂不能为空", "guid": guid}
            
            # 库存地点 - 必填
            uf_stor_loc_code = item.get("uf_stor_loc_code", "").strip()
            if not uf_stor_loc_code:
                return {"type": "E", "message": f"{item_error_prefix}库存地点不能为空", "guid": guid}
            
            # 批次 - 必填
            uf_batch_sn = item.get("uf_batch_sn", "").strip()
            if not uf_batch_sn:
                return {"type": "E", "message": f"{item_error_prefix}批次不能为空", "guid": guid}
            
            # 交易数量 - 必填，必须大于0
            transaction_qty = item.get("transaction_qty", 0)
            try:
                transaction_qty = float(transaction_qty)
                if transaction_qty <= 0:
                    return {"type": "E", "message": f"{item_error_prefix}交易数量必须大于0", "guid": guid}
            except ValueError:
                return {"type": "E", "message": f"{item_error_prefix}交易数量必须为数字", "guid": guid}
            
            # 交易单位 - 必填
            uf_transaction_uom = item.get("uf_transaction_uom", "").strip()
            if not uf_transaction_uom:
                return {"type": "E", "message": f"{item_error_prefix}交易单位不能为空", "guid": guid}
            
            # 成本中心 - 必填
            uf_cost_center = item.get("uf_cost_center", "").strip()
            if not uf_cost_center:
                return {"type": "E", "message": f"{item_error_prefix}成本中心不能为空", "guid": guid}
            
            # 库存状态 - 有效值检查
            inventory_status = item.get("inventory_status", "0").strip()
            valid_inv_status = ["0", "1", "2", "T"]
            if inventory_status not in valid_inv_status:
                return {"type": "E", "message": f"{item_error_prefix}库存状态值无效，有效值: 0/1/2/T", "guid": guid}
            
            # 特殊库存状态 - 有效值检查
            uf_special_inventory_status1 = item.get("uf_special_inventory_status1", "").strip()
            valid_special_status = ["", "C", "V", "P", "T", "SC", "S", "CC"]
            if uf_special_inventory_status1 not in valid_special_status:
                return {"type": "E", "message": f"{item_error_prefix}特殊库存状态值无效", "guid": guid}
  
            # movement_type = header_data.get("movement_type", "").strip()
            # if not movement_type:
            #     header_data.setdefault('movement_type', 'D008')

            # # 批次 - 必填
            # batch_sn_info = ''
            # batch_sn = header_data.get("batch_sn", "").strip()
            # if not batch_sn:
            #     # 主动去获取批次号
            #     datalist = [{'mat_code':mat_code,'count':transaction_qty}]
            #     msg, result = get_batch_sn_info(db, datalist)
            #     if len(result) > 0:
            #         batch_sn_info = result[0]["batch_sn_info"][0].get("batch_sn")
            #     else:
            #         return {"type": "E", "message": f"批次不能为空,{msg}", "guid": guid}
    # 验证通过
    return {"type": "S", "message": "字段验证通过", "guid": guid}


def build_post_params(header, user_id):
    """
    构建库存过账参数
    """
    db = DbHelper()
    # 构建表头参数
    doc_head = {
        "document_category": "",           # 单据种类（内部领用为空）
        "post_code": "3",                  # 过账代码：3=发料
        "document_date": header.get("document_date"),
        "posting_date": header.get("posting_date"),
        "summary_unique_number": header.get("summary_unique_number"),
        "vendor_dn": header.get("vendor_dn"),
        "company_code": "",                # 从工厂获取公司代码
        "remarks_1": "内部领用批导"
    }
    # 构建行项目参数
    doc_items = []
    line_id = 0
    for item in header.get("item", []):
        line_id += 1
        # 获取物料基本信息
        query_mat_sql = "SELECT basic_uom, parallel_uom FROM t_mmd_material_basic_data WHERE mat_code = {} ".format(repr(item['uf_mat_code']))
        mat_info = db.query_sql(query_mat_sql)
        basic_uom = mat_info[0]['basic_uom'] if mat_info else item['transaction_uom']
        parallel_uom = mat_info[0]['parallel_uom'] if mat_info else ''
        print("获取物料基本信息成功：",mat_info)

        # 获取工厂对应的公司代码
        query_plant_sql = "SELECT company_code FROM t_os_company_plant_alloc WHERE plant_code = {} ".format(repr(item['uf_plant_code']))
        plant_info = db.query_sql(query_plant_sql)
        if plant_info:
            doc_head['company_code'] = plant_info[0]['company_code']
        print("获取工厂对应的公司代码成功：",plant_info)

        if not item.get("uf_parallel_qty"):
            uf_parallel_qty = 0
        else:
            uf_parallel_qty = float(item["uf_parallel_qty"])
        print("uf_parallel_qty:",uf_parallel_qty)

        # 构建批次信息
        batch_number = build_batch_number(item["uf_mat_code"], item["uf_batch_sn"], db)
        print("构建批次信息成功:",batch_number)
        doc_item = {
            "line_id": line_id,
            "movement_type": item.get("uf_movement_type", "D008"),
            "plant_code": item["uf_plant_code"],
            "stor_loc_code": item["uf_stor_loc_code"],
            "mat_code": item["uf_mat_code"],
            "batch_sn": item["uf_batch_sn"],
            "inventory_status": item.get("inventory_status", "0"),
            "special_inventory_status1": item.get("uf_special_inventory_status1", ""),
            "special_inventory_status2": "",
            "transaction_qty": float(item["transaction_qty"]),
            "transaction_uom": item["uf_transaction_uom"],
            "basic_qty": float(item["transaction_qty"]),  # 默认等于交易数量
            "basic_uom": basic_uom,
            "parallel_qty": uf_parallel_qty,
            "parallel_uom": item.get("uf_parallel_uom", parallel_uom),
            "cost_center": item["uf_cost_center"],
            "wbs_elements": item.get("uf_wbs_elements", ""),
            "project_sn": item.get("uf_project_sn", ""),
            "vendor_code": item.get("uf_vendor_code", ""),
            "create_id": user_id,
            "batch_number": batch_number
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
    if not batch_sn:
        return {}
    # 先从数据库查询批次信息
    query_sql = "SELECT * FROM t_batch_number WHERE mat_code = {} AND batch_sn = {}".format(repr(mat_code), repr(batch_sn))
    batch_data = db.query_sql(query_sql)
    print("查询批次信息:",batch_data)
    if batch_data:
        # 使用数据库查询结果
        batch_number = batch_data[0]
    else:
        # 使用默认模板
        batch_number = initialization_batch_number(db)
        batch_number['mat_code'] = mat_code
        batch_number['batch_sn'] = batch_sn
    return batch_number