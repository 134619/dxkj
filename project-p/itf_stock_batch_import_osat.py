"""
@File    : itf_stock_batch_import_osat.py
@Author  : yang.zhang.dxdstech.com
@Date    : 2026/6/9
@explain : 库存调拨批导
"""
import copy
import uuid
from copy import deepcopy
from datetime import datetime

from DbHelper import DbHelper
from DxInventoryPostData import post_data

db = DbHelper()


def stock_batch_import_osat(payload, user_id):
    """
    stock_batch_import_osat接口的核心处理函数,接收标准结构的payload进行处理
    :param payload: 过账请求数据，支持两种格式：
                    1. 标准接口结构：{'zid': 'xxx', 'data': {'header': [...]}}
                    2. 文件传参格式：[{'mat_code': 'xxx', 'plant_code': 'xxx', ...}, ...]
    :param user_id: 操作用户ID
    :return: {'type': 'S/E', 'message': 'xxx', 'zid': 'xxx', 'mat_doc_sn': 'xxx', 'year': 'xxx'}
    """
    # ===================== 【文件传参 List → 标准接口结构】=====================
    if isinstance(payload, list):
        print(payload, '==== 这是文件传参，开始自动转换结构')
        # 按物料凭证唯一标识分组（相同zid生成一个物料凭证）
        item_group = {}
        for item in payload:
            zid_val = item.get('zid', 'DEFAULT')
            if zid_val not in item_group:
                item_group[zid_val] = []
            item_group[zid_val].append(item)
        # 生成最终标准结构
        converted_payloads = []
        for zid_val, items in item_group.items():
            posting_date = items[0].get('posting_date', datetime.now().strftime('%Y-%m-%d'))
            document_date = items[0].get('document_date', datetime.now().strftime('%Y-%m-%d'))
            summary_unique_number = items[0].get('summary_unique_number', '')
            processed_items = []
            line_id = 1
            for row in items:
                new_row = row.copy()
                new_row['line_id'] = line_id
                line_id += 1
                # 设置默认值
                new_row.setdefault('movement_type', 'T001')
                new_row.setdefault('inventory_status', '0')
                new_row.setdefault('special_inventory_status1', '')
                new_row.setdefault('rcv_inventory_status', '0')
                new_row.setdefault('rcv_special_inventory_status1', '')
                # 数量处理
                if 'transaction_qty' in new_row:
                    new_row['transaction_qty'] = float(new_row['transaction_qty'])
                if 'parallel_qty' in new_row:
                    new_row['parallel_qty'] = float(new_row['parallel_qty'])
                processed_items.append(new_row)
            new_data = {
                "zid": zid_val,
                "data": {
                    "header": [{
                        "posting_date": posting_date,
                        "document_date": document_date,
                        "summary_unique_number": summary_unique_number,
                        "item": processed_items
                    }]
                }
            }
            converted_payloads.append(new_data)
        # 循环处理每个转换后的payload
        result_list = []
        for p in converted_payloads:
            res = stock_batch_import_osat(p, user_id)
            result_list.append(res)
        if len(result_list) == 1:
            return result_list[0]
        else:
            # 合并多个结果
            all_messages = [r.get('message', '') for r in result_list]
            has_error = any(r.get('type') == 'E' for r in result_list)
            zids = [r.get('zid', '') for r in result_list]
            mat_doc_sns = [r.get('mat_doc_sn', '') for r in result_list if r.get('mat_doc_sn')]
            years = [r.get('year', '') for r in result_list if r.get('year')]
            return {
                "type": "E" if has_error else "S",
                "message": "; ".join(all_messages),
                "zid": ",".join(zids),
                "mat_doc_sn": ",".join(mat_doc_sns) if mat_doc_sns else "",
                "year": ",".join(years) if years else ""
            }

    # ===================== 标准接口结构处理 =====================
    print(payload, '==== 这是标准接口结构，开始数据校验')

    zid = payload.get("zid", str(uuid.uuid4()))
    data = payload.get("data")
    db = DbHelper()
    # 调用字段验证函数
    print("开始校验数据")
    validate_result = validate_payload(data, zid, db)
    if validate_result.get('type') == 'E':
        return validate_result
    # 库存匹配校验
    print("开始校验库存匹配：", data)
    print("开始校验库存匹配：", zid)
    inventory_check_result = check_inventory(data, zid, db)
    if inventory_check_result.get('type') == 'E':
        return inventory_check_result
    # 获取表头数据
    header = data["header"][0]
    # 构建过账参数
    print("开始构建过账参数")
    doc_head, doc_items = build_post_params(header, user_id)
    print('过账参数构建完毕，开始过账')
    print("doc_head:", doc_head)
    print("doc_items:", doc_items)
    result = execute_post(doc_head, doc_items, zid, user_id)
    print('过账完成，返回：', result)
    return {
        "type": result.get('type'),
        "message": result.get('message'),
        "guid": result.get('guid')
    }


def validate_payload(data, zid, db):
    """
    根据字段需求验证payload数据
    """
    # 检查表头
    header = data.get("header", [])
    if not header:
        return {"type": "E", "message": "抬头数据不能为空", "zid": zid}
    for header_data in header:
        # 过账日期 - 必填
        posting_date = header_data.get("posting_date", "").strip()
        if not posting_date:
            return {"type": "E", "message": "过账日期不能为空", "zid": zid}
        # 凭证日期 - 必填
        document_date = header_data.get("document_date", "").strip()
        if not document_date:
            return {"type": "E", "message": "凭证日期不能为空", "zid": zid}
        # 汇总号 - 长度限制
        summary_unique_number = header_data.get("summary_unique_number", "").strip()
        if len(summary_unique_number) > 64:
            return {"type": "E", "message": "汇总号长度不能超过64位", "zid": zid}
        # 检查行项目
        items = header_data.get("item", [])
        if not items:
            return {"type": "E", "message": "行项目数据不能为空", "zid": zid}
        for index, item in enumerate(items, 1):
            item_error_prefix = f"行项目[{index}]"
            # 库存状态 - 有效值检查
            plant_code = item.get("CompanyCode", "")
            if not plant_code:
                return {"type": "E", "message": f"{item_error_prefix}工厂代码不能为空", "zid": zid}

            inventory_status = item.get("inventory_status", "0").strip()
            valid_inv_status = ["0", "1", "2", "T"]
            if inventory_status not in valid_inv_status:
                return {"type": "E", "message": f"{item_error_prefix}库存状态值无效，有效值: 0/1/2/T", "zid": zid}
            # 特殊库存状态 - 有效值检查
            special_inventory_status1 = item.get("special_inventory_status1", "").strip()
            valid_special_status = ["", "C", "V", "P", "T", "SC", "S", "CC"]
            if special_inventory_status1 not in valid_special_status:
                return {"type": "E", "message": f"{item_error_prefix}特殊库存状态值无效", "zid": zid}
            # 接收库存状态 - 有效值检查
            rcv_inventory_status = item.get("rcv_inventory_status", "0").strip()
            if rcv_inventory_status not in valid_inv_status:
                return {"type": "E", "message": f"{item_error_prefix}接收库存状态值无效，有效值: 0/1/2/T", "zid": zid}
            # 接收特殊库存状态 - 有效值检查
            rcv_special_inventory_status1 = item.get("rcv_special_inventory_status1", "").strip()
            if rcv_special_inventory_status1 not in valid_special_status:
                return {"type": "E", "message": f"{item_error_prefix}接收特殊库存状态值无效", "zid": zid}
    # 验证通过
    return {"type": "S", "message": "字段验证通过", "zid": zid}


def check_inventory(data, zid, db):
    """
    库存匹配校验逻辑
    1. 匹配批次时，匹配未占用库存的批次
    2. 集创特殊逻辑：物料组为1002/1003/1004时特殊处理
    3. 批次有值时检查可用库存
    """
    header = data.get("header", [])
    if not header:
        return {"type": "E", "message": "抬头数据不能为空", "zid": zid}
    
    for header_data in header:
        items = header_data.get("item")
        print("items:", items)
        for index, item in enumerate(items, 1):
            item_error_prefix = f"行项目[{index}]"
            mat_code = item.get("mat_code", "").strip()
            plant_code = item.get("plant_code", "").strip()
            uf_stor_loc_code = item.get("uf_stor_loc_code", "").strip()
            batch_sn = item.get("batch_sn", "").strip()
            inventory_status = item.get("inventory_status", "0").strip()
            special_inventory_status1 = item.get("special_inventory_status1", "").strip()
            transaction_qty = float(item.get("transaction_qty", 0))
            parallel_qty = float(item.get("parallel_qty", 0))
            # 获取物料组信息
            mat_group = get_material_group(mat_code, db)
            if batch_sn:
                # 当模板批次有值时，根据物料+批次查询可用库存
                available_qty, available_parallel_qty = get_available_inventory(
                    mat_code, batch_sn, plant_code, uf_stor_loc_code, 
                    inventory_status, special_inventory_status1, db
                )
                if available_qty <= 0:
                    return {"type": "E", "message": f"{item_error_prefix}该批次[{batch_sn}]未查询到可用库存", "zid": zid}
                # 集创特殊逻辑判断
                print("mat_group:", mat_group)
                if mat_group in ["1002", "1003", "1004"]:
                    # 交易数量（片数）与库存的基本数量对比
                    # 平行数量（颗数）与库存的平行数量对比
                    if transaction_qty > available_qty:
                        return {"type": "E", 
                                "message": f"{item_error_prefix}批次[{batch_sn}]可用库存基本数量[{available_qty}]不足，交易数量[{transaction_qty}]超出", 
                                "zid": zid}
                    if parallel_qty > available_parallel_qty:
                        return {"type": "E", 
                                "message": f"{item_error_prefix}批次[{batch_sn}]可用库存平行数量[{available_parallel_qty}]不足，平行数量[{parallel_qty}]超出", 
                                "zid": zid}
    return {"type": "S", "message": "库存校验通过", "zid": zid}


def get_material_group(mat_code, db):
    """
    获取物料组
    """
    query_sql = "SELECT mat_group FROM t_mmd_material_basic_data WHERE mat_code = {}".format(repr(mat_code))
    result = db.query_sql(query_sql)
    if result:
        return result[0].get('mat_group', '')
    return ''


def get_available_inventory(mat_code, batch_sn, plant_code, uf_stor_loc_code, 
                           inventory_status, special_inventory_status1, db):
    """
    查询指定批次的可用库存（排除占用库存）
    :return: (basic_qty, parallel_qty)
    """
    query_sql = """
        SELECT basic_qty, parallel_qty 
        FROM t_im_inventory 
        WHERE mat_code = {} 
          AND batch_sn = {} 
          AND plant_code = {} 
          AND uf_stor_loc_code = {} 
          AND inventory_status = {} 
          AND special_inventory_status1 = {}
          AND occupy_flag = '0'  -- 未占用库存
    """.format(repr(mat_code), repr(batch_sn), repr(plant_code), 
               repr(uf_stor_loc_code), repr(inventory_status), repr(special_inventory_status1))
    
    result = db.query_sql(query_sql)
    if result:
        return result[0].get('basic_qty', 0), result[0].get('parallel_qty', 0)
    return 0, 0


def get_available_batches(mat_code, plant_code, uf_stor_loc_code,
                         inventory_status, special_inventory_status1, db):
    """
    查询未占用库存的批次列表
    """
    query_sql = """
        SELECT batch_sn, basic_qty, parallel_qty 
        FROM t_im_inventory 
        WHERE mat_code = {} 
          AND plant_code = {} 
          AND stor_loc_code = {} 
          AND inventory_status = {} 
          AND special_inventory_status1 = {}
          AND occupy_flag = '0'  -- 未占用库存
          AND basic_qty > 0
    """.format(repr(mat_code), repr(plant_code), repr(uf_stor_loc_code), 
               repr(inventory_status), repr(special_inventory_status1))
    
    return db.query_sql(query_sql)


def build_post_params(header, user_id):
    """
    构建库存过账参数（转投业务，过账代码4）
    """
    db = DbHelper()
    # 构建表头参数
    doc_head = {
        "document_category": "",           # 单据种类（转投为空）
        "post_code": "4",                  # 过账代码：4=转投
        "document_date": header.get("document_date"),
        "posting_date": header.get("posting_date"),
        "summary_unique_number": header.get("summary_unique_number"),
        "company_code": "",                # 从工厂获取公司代码
        "remarks_1": "库存转投批导",
    }
    # 构建行项目参数
    
    itemes = header.get("item")[0]
    mat_code = itemes.get("uf_ipn", "")
    plant_code = itemes.get("CompanyCode", "")
    print("plant_code:", plant_code)
    print("mat_code:", mat_code)

    doc_items = []
    line_id = 0

    basic_uom,parallel_uom,parallel_qty_val = '', '', 0

    for item in header.get("item", []):
        line_id += 1
        # 获取物料基本信息
        query_mat_sql = "SELECT basic_uom, parallel_uom FROM t_mmd_material_basic_data WHERE mat_code = {} ".format(repr(mat_code))
        mat_info = db.query_sql(query_mat_sql)
        print("mat_info:", mat_info)
        if mat_info:
            print("获取物料基本信息成功：", mat_info)
            basic_uom = mat_info[0]['basic_uom'] if mat_info else item['transaction_uom']
            parallel_uom = mat_info[0]['parallel_uom'] if mat_info else ''

        # 获取工厂对应的公司代码
        query_plant_sql = "SELECT company_code FROM t_os_company_plant_alloc WHERE plant_code = {} ".format(repr(plant_code))
        plant_info = db.query_sql(query_plant_sql)
        print("plant_info:", plant_info)
        if plant_info:
            print("获取工厂对应的公司代码成功：", plant_info)
            doc_head['company_code'] = plant_info[0]['company_code']
            parallel_qty_val = float(item.get("parallel_qty", 0))

        # 请检查行标识1平行数量不能为0; 
        # 行标识1平行数量不能为0; 
        # 行标识1批次编码必输
        print("parallel_qty,parallel_uom:", parallel_qty_val, item.get("parallel_uom", parallel_uom))
        # 构建批次信息
        batch_number, batch_sn = build_batch_number(mat_code, item.get("batch_sn", ""), db)
        print("构建批次信息成功:", batch_number)
        print("batch_sn:", batch_sn)
        # mat_code, plant_code, batch_sn, debit_credit_mark, dict_mat_code, dict_mat_batch, batch_number
        doc_item = {
            "line_id": line_id,
            "movement_type": item.get("movement_type", "T001"),
            "plant_code": plant_code,
            "stor_loc_code": item["uf_stor_loc_code"],
            "mat_code": mat_code,
            "batch_sn": batch_sn,
            "inventory_status": item.get("inventory_status", "0"),
            "special_inventory_status1": item.get("special_inventory_status1", ""),
            "special_inventory_status2": "",
            "basic_uom": basic_uom,
            # "parallel_qty": parallel_qty_val,
            "parallel_qty": int(1),
            "parallel_uom": item.get("parallel_uom", parallel_uom),
            "vendor_code": item.get("vendor_code", ""),
            "create_id": user_id,
            "batch_number": batch_number,
            ## 可能需要修改
            "transaction_qty": float(item["ChipQty"]),
            "transaction_uom": item.get("transaction_uom","EA"),
            # 接收方信息
            "rcv_mat_code": mat_code,
            "rcv_plant_code": plant_code,
            ## 这四个字段，不太确定
            "rcv_stor_loc_code": item.get("rcv_stor_loc_code", ""),

            # "rcv_batch_sn": plant_info[0]['company_code'],
            "rcv_batch_sn": batch_sn,
            "rcv_batch_number": {},

            "rcv_inventory_status": item.get("rcv_inventory_status", "0"),
            "rcv_special_inventory_status1": item.get("rcv_special_inventory_status1", ""),
            "rcv_special_inventory_status2": item.get("rcv_special_inventory_status2", ""),
            "rcv_vendor_code": item.get("rcv_vendor_code", ""),
            "basic_qty": float(item["ChipQty"]),  # 默认等于交易数量
        }
        doc_items.append(doc_item)

    doc_head['batch_sn'] = batch_sn
    print("过账数据构建成功:", doc_head, doc_items)
    return doc_head, doc_items



# 构建rcv_batch_number
def build_rcv_batch_number(mat_code, batch_sn, db):
    """
    构建接收方批次号
    :param mat_code: 物料编码
    :param batch_sn: 批次号
    :param db: 数据库连接
    :return: 接收方批次号
    """
    print("build_rcv_batch_number:", mat_code, batch_sn)

    # 先从数据库查询批次信息
    print("查询批次信息:", mat_code, batch_sn)
    query_sql = "SELECT * FROM t_batch_number WHERE mat_code = {} AND batch_sn = {}".format(repr(mat_code), repr(batch_sn))
    batch_data = db.query_sql(query_sql)
    print("查询批次信息:", batch_data)
    if batch_data:
        # 使用数据库查询结果
        batch_number = batch_data[0]
    else:
        # 使用默认模板
        batch_number = initialization_batch_number(db)
        batch_number['mat_code'] = mat_code
        batch_number['batch_sn'] = batch_sn
    return batch_number




def execute_post(doc_head, doc_items, zid, user_id):
    """
    执行库存过账
    调用库存过账接口
    """
    print('过账传入:', doc_head, doc_items)
    code, msg, error_list, mat_doc_sn, year = post_data('0', user_id, doc_head, doc_items)
    print('过账返回:', code, msg, error_list, mat_doc_sn, year)
    if code == 200 and mat_doc_sn:
        return {
            "type": "S",
            "message": f"过账成功，物料凭证号: {mat_doc_sn}",
            "zid": zid,
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
            "zid": zid
            }

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
    if batch_data:
        # 使用数据库查询结果
        batch_number = batch_data[0]
    else:
        # 使用默认模板
        batch_number = initialization_batch_number(db)
        batch_number['mat_code'] = mat_code
        batch_number['batch_sn'] = batch_sn
    return batch_number, batch_sn


def get_batch_sn_info(mat_code, db):
    """
    获取批次号信息
    """
    query_sql = "SELECT batch_sn FROM t_batch_number WHERE mat_code = {}".format(repr(mat_code))
    batch_data = db.query_sql(query_sql)
    return batch_data[0]


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
    print("查询批次号结构:", table)
    data = {}
    for each in table:
        if each["data_type"] in ('decimal', 'double', 'tinyint', 'int'):
            data[each["field_name"]] = 0
        else:
            data[each["field_name"]] = each["default_value"] if each["default_value"] else ''
    print("初始化批次号结构:", data)
    return data



def trans_check_sip(head, items):
    # ---校验供应商批次必填
    items2 = []
    for item in items:
        if item['sfzl'] == 0:
            items2.append(item)
            vendor_batch = item.get('uf_vendor_batch', '')
            if len(vendor_batch) == 0:
                ret = {'type': 'E', 'message': '辅料行的供应商批次为空'}
                return items2, ret

    # ---通过IPN+供应商批次，取批次库存
    if len(items2) != 0:
        cond_plant = ','.join(list(set([repr(item['uf_plant_code']) for item in items2])))
        cond_stor_loc = ','.join(list(set([repr(item['uf_stor_loc_code']) for item in items2])))
        cond_mat_code = ','.join(list(set([repr(item['uf_mat_code']) for item in items2])))
        cond_vendor_batch = ','.join(list(set([repr(item['uf_vendor_batch']) for item in items2])))

        year = head.get('uf_posting_date', '')[:4]
        month = head.get('uf_posting_date', '')[5:7]

        inv_data = db.query_sql(f"""SELECT t_inventory_batch_data.mat_code,
                                           t_inventory_batch_data.plant_code,
                                           t_inventory_batch_data.stor_loc_code,
                                           t_inventory_batch_data.batch_sn,
                                           t_inventory_batch_data.basic_qty,
                                           t_batch_number.vendor_batch
                                      FROM t_inventory_batch_data
                                      INNER JOIN t_batch_number USING(mat_code,batch_sn)
                                      WHERE t_inventory_batch_data.mat_code in ({cond_mat_code})
                                        AND t_inventory_batch_data.plant_code in ({cond_plant})
                                        AND t_inventory_batch_data.year = "{year}"
                                        AND t_inventory_batch_data.period = "{month}"
                                        AND t_inventory_batch_data.stor_loc_code in ({cond_stor_loc})
                                        AND t_inventory_batch_data.inventory_status = '0'
                                        AND t_inventory_batch_data.special_inventory_status1 = ''
                                        AND t_inventory_batch_data.special_inventory_status2 = ''
                                        AND t_batch_number.vendor_batch in ({cond_vendor_batch})  """)
        print((f"""SELECT t_inventory_batch_data.mat_code,
                                           t_inventory_batch_data.plant_code,
                                           t_inventory_batch_data.stor_loc_code,
                                           t_inventory_batch_data.batch_sn,
                                           t_inventory_batch_data.basic_qty,
                                           t_batch_number.vendor_batch
                                      FROM t_inventory_batch_data
                                      INNER JOIN t_batch_number USING(mat_code,batch_sn)
                                      WHERE t_inventory_batch_data.mat_code in ({cond_mat_code})
                                        AND t_inventory_batch_data.plant_code in ({cond_plant})
                                        AND t_inventory_batch_data.year = "{year}"
                                        AND t_inventory_batch_data.period = "{month}"
                                        AND t_inventory_batch_data.stor_loc_code in ({cond_stor_loc})
                                        AND t_inventory_batch_data.inventory_status = '0'
                                        AND t_inventory_batch_data.special_inventory_status1 = ''
                                        AND t_inventory_batch_data.special_inventory_status2 = ''
                                        AND t_batch_number.vendor_batch in ({cond_vendor_batch})  """))
        print("inv_datainv_datainv_data",inv_data,'\n\n')

    # ---对比批次库存，拆行
    items2 = []
    for item in items:
        if item['sfzl'] == 1:
            items2.append(item)
        else:
            for inv in inv_data:
                if item.get('uf_plant_code', '') == inv.get('plant_code', '') and \
                        item.get('uf_stor_loc_code', '') == inv.get('stor_loc_code', '') and \
                        item.get('uf_mat_code', '') == inv.get('mat_code', '') and \
                        item.get('uf_vendor_batch', '') == inv.get('vendor_batch', '') and \
                        item.get('uf_parallel_qty', '') > 0 and \
                        inv.get('basic_qty', '') > 0:
                    if item.get('uf_parallel_qty', '') <= inv.get('basic_qty', ''):
                        item2 = deepcopy(item)
                        item2['uf_batch_sn'] = inv.get('batch_sn', '')
                        items2.append(item2)

                        inv['basic_qty'] = inv['basic_qty'] - item.get('uf_parallel_qty', '')
                        item['uf_parallel_qty'] = 0
                    else:
                        item2 = deepcopy(item)
                        item2['uf_parallel_qty'] = inv.get('basic_qty', '')
                        item2['uf_batch_sn'] = inv.get('batch_sn', '')
                        items2.append(item2)

                        item['uf_parallel_qty'] = item['uf_parallel_qty'] - inv.get('basic_qty', '')
                        inv['basic_qty'] = 0

            if item.get('uf_parallel_qty', '') > 0:
                ret = {'type': 'E', 'message': '库存数量不足'}
                return items2, ret
    ret = {}
    return items2, ret