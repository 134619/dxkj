"""
@File    : itf_osat_transfer_post.py
@Author  : yang.zhang.dxdstech.com
@Date    : 2026/6/14
@explain : OSAT 调拨批导过账接口（T001）
           处理三类业务：OSAT厂之间(21) / OSAT厂到万佳中转仓(21) / 万佳中转仓到万佳库(40)
           前端负责多文件上传、激活Sheet解析、模板字段顺序校验与展示；。
"""
import uuid
from datetime import datetime

from DbHelper import DbHelper
from DxInventoryPostData import post_data
from Z_generate_batch_sn import get_batch_sn_info

# 业务类别白名单：21-OSAT间 / OSAT→万佳中转仓；40-万佳中转仓→万佳库
VALID_BS_CATEGORY = {"21", "40"}


def osat_transfer_post(payload, user_id):
    """
    OSAT 调拨批导接口核心处理函数，接收标准结构或文件传参 List。
    :param payload:
            1. 标准接口结构：{'guid': 'xxx', 'data': {'header': [...]}}
            2. 文件传参格式：[{'bs_category': '21', 'mat_code': 'xxx', 'plant_code': 'xxx', ...}, ...]
    :param user_id: 操作用户ID
    :return: {'type': 'S/E', 'message': 'xxx', 'guid': 'xxx', 'mat_doc_sn': 'xxx'}
    """
    # ===================== 【文件传参 List → 标准接口结构】=====================
    if isinstance(payload, list):
        print(payload, '==== 这是文件传参，开始自动转换结构')
        # 按 guid 分组：同一 guid（同一 Excel）= 一个物料凭证，整体成功或失败
        item_group = {}
        for item in payload:
            guid_val = item.get('guid', '') or str(uuid.uuid4())
            if guid_val not in item_group:
                item_group[guid_val] = []
            item_group[guid_val].append(item)

        converted_payloads = []
        for guid_val, items in item_group.items():
            posting_date = items[0].get('posting_date', datetime.now().strftime('%Y-%m-%d'))
            document_date = items[0].get('document_date', datetime.now().strftime('%Y-%m-%d'))
            summary_unique_number = items[0].get('summary_unique_number', '')
            bs_category = str(items[0].get('bs_category', '')).strip()

            processed_items = []
            line_id = 1
            for row in items:
                new_row = row.copy()
                # 行号：传入则用，否则按序号自动补
                if not new_row.get('line_id'):
                    new_row['line_id'] = line_id
                line_id += 1
                # 默认值
                new_row.setdefault('movement_type', '311')
                new_row.setdefault('inventory_status', '0')
                new_row.setdefault('special_inventory_status1', '')
                # 数量处理
                if 'transaction_qty' in new_row:
                    try:
                        new_row['transaction_qty'] = float(new_row['transaction_qty'])
                    except (ValueError, TypeError):
                        pass
                if 'parallel_qty' in new_row:
                    try:
                        new_row['parallel_qty'] = float(new_row['parallel_qty'])
                    except (ValueError, TypeError):
                        pass
                processed_items.append(new_row)

            new_data = {
                "guid": guid_val,
                "data": {
                    "header": [{
                        "posting_date": posting_date,
                        "document_date": document_date,
                        "summary_unique_number": summary_unique_number,
                        "bs_category": bs_category,
                        "item": processed_items
                    }]
                }
            }
            converted_payloads.append(new_data)

        # 逐组处理（每组独立过账）
        result_list = []
        for p in converted_payloads:
            res = osat_transfer_post(p, user_id)
            result_list.append(res)

        if len(result_list) == 1:
            return result_list[0]

        # 合并多组结果
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

    # 1. 必要性校验（关键字段必填 + 移动类型必须为 311）
    validate_result = validate_payload(data, guid, db)
    if validate_result.get('type') == 'E':
        return validate_result
    print("必要性校验完毕")

    # 2. 通用性校验（物料/工厂/库存地点/目标工厂/目标库存地点存在性）
    master_result = check_master_data(data, guid, db)
    if master_result.get('type') == 'E':
        return master_result
    print("主数据校验完毕")

    # 3. 批次匹配（校验可用库存或分配批次，确定 rcv_batch_sn）
    batch_result = resolve_batch(data, guid, db)
    if batch_result.get('type') == 'E':
        return batch_result
    print("批次匹配完毕")

    # 4. 构建过账参数（311 → T001）
    header = data["header"][0]
    doc_head, doc_items = build_post_params(header, user_id)
    print('过账参数构建完毕，开始过账')
    print("doc_head:", doc_head)
    print("doc_items:", doc_items)

    # 5. 执行过账（同 guid 整组提交，天然 all-or-nothing）
    return execute_post(doc_head, doc_items, guid, user_id)


def validate_payload(data, guid, db):
    """
    必要性校验：关键字段必填 + 业务类别合法 + 移动类型必须为 311。
    """
    header = data.get("header", [])
    if not header:
        return {"type": "E", "message": "抬头数据不能为空", "guid": guid}

    for header_data in header:
        # 过账日期必填
        posting_date = str(header_data.get("posting_date", "")).strip()
        if not posting_date:
            return {"type": "E", "message": "过账日期不能为空", "guid": guid}

        # 业务类别必填 + 合法
        bs_category = str(header_data.get("bs_category", "")).strip()
        if not bs_category:
            return {"type": "E", "message": "业务类别不能为空", "guid": guid}
        if bs_category not in VALID_BS_CATEGORY:
            return {"type": "E", "message": f"业务类别[{bs_category}]无效，有效值: 21/40", "guid": guid}

        # 行项目非空
        items = header_data.get("item", [])
        if not items:
            return {"type": "E", "message": "行项目数据不能为空", "guid": guid}

        for index, item in enumerate(items, 1):
            prefix = f"行项目[{index}]"

            # 关键字段必填（业务类别/GUID/过账日期在抬头层已校验，此处校验行级字段）
            po_sn = str(item.get("po_sn", "")).strip()
            if not po_sn:
                return {"type": "E", "message": f"{prefix}采购订单号不能为空", "guid": guid}

            if not item.get("line_id"):
                return {"type": "E", "message": f"{prefix}行号不能为空", "guid": guid}

            mat_code = str(item.get("mat_code", "")).strip()
            if not mat_code:
                return {"type": "E", "message": f"{prefix}物料编码不能为空", "guid": guid}

            # 交易数量：必填、数字、大于0
            transaction_qty = item.get("transaction_qty", 0)
            try:
                transaction_qty = float(transaction_qty)
                if transaction_qty <= 0:
                    return {"type": "E", "message": f"{prefix}交易数量必须大于0", "guid": guid}
            except (ValueError, TypeError):
                return {"type": "E", "message": f"{prefix}交易数量必须为数字", "guid": guid}

            # 移动类型：必填且必须为 311
            movement_type = str(item.get("movement_type", "")).strip()
            if not movement_type:
                return {"type": "E", "message": f"{prefix}移动类型不能为空", "guid": guid}
            if movement_type != "311":
                return {"type": "E", "message": f"{prefix}移动类型必须为311，当前为[{movement_type}]", "guid": guid}

            # 库存地点必填（本期不做 VETEXT 查找，要求必传）
            if not str(item.get("stor_loc_code", "")).strip():
                return {"type": "E", "message": f"{prefix}库存地点不能为空", "guid": guid}

    return {"type": "S", "message": "字段验证通过", "guid": guid}


def check_master_data(data, guid, db):
    """
    通用性校验：物料 / 工厂 / 库存地点 / 目标工厂 / 目标库存地点 是否存在。
    """
    for header_data in data.get("header", []):
        items = header_data.get("item", [])
        for index, item in enumerate(items, 1):
            prefix = f"行项目[{index}]"
            mat_code = str(item.get("mat_code", "")).strip()
            plant_code = str(item.get("plant_code", "")).strip()
            stor_loc_code = str(item.get("stor_loc_code", "")).strip()
            target_plant_code = str(item.get("target_plant_code", "")).strip()
            target_stor_loc_code = str(item.get("target_stor_loc_code", "")).strip()

            # 工厂必填（后续存在性校验前提）
            if not plant_code:
                return {"type": "E", "message": f"{prefix}工厂代码不能为空", "guid": guid}

            # 物料存在
            if not db.query_sql("SELECT mat_code FROM t_mmd_material_basic_data WHERE mat_code = {}".format(repr(mat_code))):
                return {"type": "E", "message": f"{prefix}物料[{mat_code}]不存在", "guid": guid}

            # 工厂存在（t_os_company_plant_alloc）
            if not db.query_sql("SELECT company_code FROM t_os_company_plant_alloc WHERE plant_code = {}".format(repr(plant_code))):
                return {"type": "E", "message": f"{prefix}工厂[{plant_code}]不存在", "guid": guid}

            # 源库存地点存在（t_os_plant_storage_location_alloc）
            if not db.query_sql(
                "SELECT id FROM t_os_plant_storage_location_alloc WHERE plant_code = {} AND stor_loc_code = {}".format(
                    repr(plant_code), repr(stor_loc_code))):
                return {"type": "E", "message": f"{prefix}工厂[{plant_code}]下库存地点[{stor_loc_code}]不存在", "guid": guid}

            # 目标工厂必填 + 存在
            if not target_plant_code:
                return {"type": "E", "message": f"{prefix}目标工厂代码不能为空", "guid": guid}
            if not db.query_sql("SELECT company_code FROM t_os_company_plant_alloc WHERE plant_code = {}".format(repr(target_plant_code))):
                return {"type": "E", "message": f"{prefix}目标工厂[{target_plant_code}]不存在", "guid": guid}

            # 目标库存地点必填 + 存在
            if not target_stor_loc_code:
                return {"type": "E", "message": f"{prefix}目标库存地点不能为空", "guid": guid}
            if not db.query_sql(
                "SELECT id FROM t_os_plant_storage_location_alloc WHERE plant_code = {} AND stor_loc_code = {}".format(
                    repr(target_plant_code), repr(target_stor_loc_code))):
                return {"type": "E", "message": f"{prefix}目标工厂[{target_plant_code}]下目标库存地点[{target_stor_loc_code}]不存在", "guid": guid}

    return {"type": "S", "message": "主数据校验通过", "guid": guid}


def resolve_batch(data, guid, db):
    """
    批次匹配：batch_sn 有值则校验可用库存；无值则调用 get_batch_sn_info 分配。
    接收批次 rcv_batch_sn 默认等于源批次（调拨同批次流转）。
    """
    for header_data in data.get("header", []):
        items = header_data.get("item", [])
        for index, item in enumerate(items, 1):
            prefix = f"行项目[{index}]"
            mat_code = str(item.get("mat_code", "")).strip()
            plant_code = str(item.get("plant_code", "")).strip()
            stor_loc_code = str(item.get("stor_loc_code", "")).strip()
            batch_sn = str(item.get("batch_sn", "")).strip()
            inventory_status = str(item.get("inventory_status", "0")).strip()
            special_inventory_status1 = str(item.get("special_inventory_status1", "")).strip()
            transaction_qty = float(item.get("transaction_qty", 0))

            if batch_sn:
                # 校验该批次可用库存
                available_qty = get_available_inventory(
                    mat_code, batch_sn, plant_code, stor_loc_code,
                    inventory_status, special_inventory_status1, db)
                if available_qty <= 0:
                    return {"type": "E", "message": f"{prefix}批次[{batch_sn}]未查询到可用库存", "guid": guid}
                if transaction_qty > available_qty:
                    return {"type": "E",
                            "message": f"{prefix}批次[{batch_sn}]可用库存[{available_qty}]不足，交易数量[{transaction_qty}]超出",
                            "guid": guid}
                # 接收批次 = 源批次
                item["rcv_batch_sn"] = batch_sn
            else:
                # 未传批次 → 按物料属性分配可用批次
                datalist = [{"mat_code": mat_code, "count": transaction_qty}]
                msg, result = get_batch_sn_info(db, datalist)
                if msg:
                    return {"type": "E", "message": f"{prefix}批次分配失败：{msg}", "guid": guid}
                if not result or not result[0].get("batch_sn_info"):
                    return {"type": "E", "message": f"{prefix}未匹配到可用批次", "guid": guid}
                allocated_batch = result[0]["batch_sn_info"][0].get("batch_sn", "")
                if not allocated_batch:
                    return {"type": "E", "message": f"{prefix}未匹配到可用批次", "guid": guid}
                item["batch_sn"] = allocated_batch
                item["rcv_batch_sn"] = allocated_batch

    return {"type": "S", "message": "批次匹配通过", "guid": guid}


def get_available_inventory(mat_code, batch_sn, plant_code, stor_loc_code,
                            inventory_status, special_inventory_status1, db):
    """
    查询指定批次的可用库存（仅未占用）。
    :return: 可用基本数量 basic_qty（无记录返回 0）
    """
    query_sql = """
        SELECT basic_qty
        FROM t_im_inventory
        WHERE mat_code = {}
          AND batch_sn = {}
          AND plant_code = {}
          AND stor_loc_code = {}
          AND inventory_status = {}
          AND special_inventory_status1 = {}
          AND occupy_flag = '0'
    """.format(repr(mat_code), repr(batch_sn), repr(plant_code), repr(stor_loc_code),
               repr(inventory_status), repr(special_inventory_status1))
    result = db.query_sql(query_sql)
    if result:
        return float(result[0].get('basic_qty', 0) or 0)
    return 0


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


def execute_post(doc_head, doc_items, guid, user_id):
    """
    执行库存过账（整组提交，任一行失败则整组失败）。
    """
    print('过账传入：', doc_head, doc_items)
    try:
        code, msg, error_list, mat_doc_sn, year = post_data('0', user_id, doc_head, doc_items)
        print('过账返回：', code, msg, error_list, mat_doc_sn, year)
        if code == 200 and mat_doc_sn:
            return {
                "type": "S",
                "message": f"过账成功，物料凭证号: {mat_doc_sn}",
                "guid": guid,
                "mat_doc_sn": mat_doc_sn,
                "year": year
            }
        else:
            error_msg = msg or ""
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
