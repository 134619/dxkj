"""
@File    : Z_post_emes_data.py
@Author  : kai.wang@dxdstech.com
@Date    : 2025/10/13
@explain : 执行eMES数据过账
"""
import time
import traceback
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import orjson as json
from DbHelper import DbHelper
from libenhance import Request, Response
from logger import LoggerConfig
from SystemHelper import EnvKeys, SystemHelper
from ToolsMethods import ResetResponse, ResponseData, ResponseStatusCode

material_map = {}
po_header_map = {}
zt52_map = {}
po_item_map = {}
quality_type_map = {}
po_component_map = {}
po_batch_binding_map = {}
initial_attribute_map = {}

FIELD_MAP = {
    'emes_post_status': 'eph.uf_post_status',
    'mat_code': 'epi.uf_mat_code',
    'uf_guid': 'eph.uf_guid',
    'company_code': 'eph.uf_company_code',
    'post_business_cate': 'eph.uf_bs_category',
    'movement_type': 'epi.uf_movement_type',
    'uf_posting_date': 'eph.uf_posting_date'
}
BUYOUT = '01'
OFFLINE = '03'
CANCEL_OFFLINE = '04'
OUTSOURCED_PROCESSING = '05'
POST_CODE_MAP = {
    BUYOUT: '1',
    OFFLINE: '4',
    CANCEL_OFFLINE: '4',
    OUTSOURCED_PROCESSING: '7'
}
POST_STATUS_MAP = {
    '1': '',
    '2': 'S',
    '3': 'E'
}
RECEIVING = 'R003'
BACKFLUSH = 'D005'

logger = LoggerConfig("Z_post_emes_data", isStream=True)
db = DbHelper()
sh = SystemHelper()
user_id = sh.getEnv(EnvKeys.user_id)


@ResetResponse(params=['emes_post_status', 'mat_code', 'uf_guid', 'company_code', 'post_business_cate',
                       'movement_type', 'uf_posting_date'], excelName='eMES过账数据明细')
def queryPostData(emes_post_status, mat_code, uf_guid, company_code, post_business_cate,
                  movement_type, uf_posting_date, **kwargs):
    if not emes_post_status:
        return ResponseData(ResponseStatusCode.Error, '过账状态必传', [])

    # 过账状态映射
    emes_post_status = [POST_STATUS_MAP[x] for x in emes_post_status]

    query_condition = 'WHERE 1=1'

    for param_name, db_field in FIELD_MAP.items():
        param_value = locals().get(param_name)
        if param_value and isinstance(param_value, list) and param_name != 'uf_posting_date':
            placeholder = ', '.join(repr(v) for v in param_value)
            query_condition += f' AND {db_field} in ({placeholder})'

        elif param_value and isinstance(param_value, str):
            query_condition += f' AND {db_field} = "{param_value}"'

        elif param_value and isinstance(param_value, list) and param_name == 'uf_posting_date':
            query_condition += f' AND {db_field} BETWEEN "{param_value[0]}" AND "{param_value[1]}"'

        elif param_value is not None and isinstance(param_value, bool):
            if not param_value:
                query_condition += f'AND {db_field} <> 1'

        elif param_value is not None and isinstance(param_value, int):
            query_condition += f' AND {db_field} = {param_value}'

    query_ret = query_post_data(query_condition)

    from GetColumnsInfo import get_columns_info

    display = get_columns_info(query_ret)

    return ResponseData(ResponseStatusCode.Success, '查询成功', query_ret, display=display)


def postEmesData():
    start_time = time.perf_counter()
    logger.printInfo("postEmesData开始: 统计耗时", {'当前时间戳': time.time()})

    req = Request()
    res = Response()

    body = json.loads(req.body())
    param = body.get('data', {})
    data = param.get('data', [])
    #过账执行
    res_dic = posting_execute(data)
    res.set_body(json.dumps(res_dic))
    res.commit(True)
    end_time = time.perf_counter()
    logger.printInfo("postEmesData结束: 统计耗时", {'总耗时': end_time - start_time, '当前时间戳': time.time()})


def posting_execute(data):
    if not data:
        return {"code": 400, "msg": '过账数据不能为空', "data": data}

    if 'S' in {item.get('uf_post_status', '') for item in data}:
        return {"code": 400, "msg": '过账成功不能再次过账', "data": data}

    bs_categories = {item['uf_bs_category'] for item in data if item.get('uf_bs_category')}
    unsupported = bs_categories - set(POST_CODE_MAP.keys())
    print(bs_categories,'bs_categories',set(POST_CODE_MAP.keys()),'set(POST_CODE_MAP.keys())')
    if unsupported:
        return {
            "code": 400,
            "msg": f"暂不支持以下业务类别过账: {', '.join(sorted(unsupported))}",
            "data": data
        }

    grouped = defaultdict(list)
    for item in data: grouped[item['uf_guid']].append(item)

    code = 200
    msg = '过账成功'
    all_processed = []
    for _, items in grouped.items():
        code, msg, processed = do_post(items)
        all_processed.extend(processed)
        if code != 200:
            code = 400
            msg = msg
    return {"code": code, "msg": msg, "data": all_processed}

def update_after_post(update_post):
    """
    过账后更新相关信息
    :param update_post
    :return:
    """
    groups = defaultdict(list)
    for item in update_post:
        groups[item['uf_guid']].append(item)
    print(groups,'groups=======')
    placeholder = ', '.join([repr(guid) for guid in groups])

    query_sql = f"""
    SELECT
        uf_guid,
        uf_bs_category,
        uf_vendor_short_name,
        uf_posting_date,
        uf_posting_time,
        uf_company_code,
        uf_remarks,
        uf_post_status,
        uf_message,
        uf_mat_doc_sn,
        uf_year
    FROM ut_emes_post_data_header
    WHERE uf_guid in ({placeholder})
    """
    query_header = db.query_sql(query_sql)
    print(query_header,'query_header=-=-=')
    update_list = []
    for item in query_header:
        guid = item['uf_guid']
        uf_post_status = groups[guid][0]['uf_post_status']
        if uf_post_status not in ('S', 'E'):
            continue
        message = groups[guid][0].get('uf_message', '')
        mat_doc_sn = groups[guid][0].get('uf_mat_doc_sn', '')
        year = groups[guid][0].get('uf_year', '')
        item['uf_post_status'] = uf_post_status
        if len(message) > 255:
            message = message[:255]
        item['uf_message'] = message
        item['uf_mat_doc_sn'] = mat_doc_sn
        # item['uf_year'] = f"NULLIF({repr(year)}, '')"
        item['uf_year'] = year if year and year.strip() else ""
        update_list.append(item)

    if update_list:
        print(update_list,'update_list-=-=-=')
        duplicate_key = ['uf_post_status', 'uf_message', 'uf_mat_doc_sn']
        rows = db.batchInsertToDB('ut_emes_post_data_header', update_list, DuplicateSQLKey=duplicate_key,
                                  isUpdate=True, user_id=user_id)
        db.dbCommit()
        logger.printInfo("过账后更新抬头表rows为", rows)


def check_batch_exists(mat_code, batch_sn):
    """
    判断批次号是否存在
    :return:
    """
    sql = f"SELECT EXISTS(SELECT 1 FROM t_batch_number WHERE mat_code = '{mat_code}' and batch_sn = '{batch_sn}') AS is_exists"
    ret = db.query_sql(sql)

    return ret[0]['is_exists']


def query_plant_code(po_sn, po_items):
    """
    获取工厂
    :param po_sn:
    :param po_items:
    :return:
    """
    sql = f"""
    select plant_code from t_po_item where po_sn = '{po_sn}' and po_items = {po_items}
    """
    ret = db.query_sql(sql)

    return ret[0]['plant_code']


def query_pur_group():
    """
    查询采购组
    :return:
    """
    sql = f"""
    SELECT m.uf_pur_group
    FROM t_system_user u
    JOIN ut_account_pur_group_map m ON u.account = m.uf_account
    WHERE u.id = {user_id}
    """
    ret = db.query_sql(sql)
    if not ret:
        return ''
    else:
        return ret[0]['uf_pur_group']


def query_post_data(query_condition):
    """
    查询过账数据
    :param query_condition: 查询条件
    :return:
    """
    # query_sql = f"""
    # SELECT
    #   eph.uf_message,
    #   eph.uf_mat_doc_sn,
    #   eph.uf_year,
    #   eph.uf_post_status,
    #   eph.uf_guid,
    #   epi.uf_line_id,
    #   eph.uf_bs_category,
    #   epi.uf_group_id,
    #   epi.uf_movement_type,
    #   epi.uf_plant_code,
    #   epi.uf_stor_loc_code,
    #   psl.stor_loc_desc,
    #   epi.uf_inventory_status,
    #   epi.uf_mat_code,
    #   mbd.mat_description,
    #   epi.uf_batch_sn,
    #   epi.uf_transaction_qty,
    #   epi.uf_parallel_qty,
    #   epi.uf_rcv_stor_loc_code,
    #   epi.uf_rcv_batch_sn,
    #   epi.uf_po_sn,
    #   epi.uf_po_items,
    #   epi.uf_plant_work_order,
    #   epi.uf_res_doc_sn,
    #   epi.uf_res_doc_sn,
    #   epi.uf_scarp_flag,
    #   epi.uf_scarp_qty,
    #   epi.uf_lot_no,
    #   epi.uf_ZT04,
    #   epi.uf_ZWAFERNO,
    #   epi.uf_wafer_id,
    #   epi.uf_auxiliary_material_batch_sn,
    #   epi.uf_ZT18,
    #   epi.uf_runcard,
    #   epi.uf_ZT07,
    #   epi.uf_box_no,
    #   epi.uf_production_date,
    #   epi.uf_ZT05,
    #   epi.uf_ZT20,
    #   epi.uf_ZT21,
    #   epi.uf_ZT35,
    #   epi.uf_ZT36,
    #   epi.uf_ZT37,
    #   epi.uf_ZT38,
    #   epi.uf_ZT06,
    #   epi.uf_ZT48,
    #   epi.uf_ZT49,
    #   epi.uf_ZT50,
    #   epi.uf_ZT51,
    #   epi.uf_ZT53,
    #   epi.uf_ZT14,
    #   epi.uf_ZT15,
    #   epi.uf_ZT54,
    #   epi.uf_ZT08,
    #   epi.uf_ZT09,
    #   epi.uf_joint_flag,
    #   epi.uf_joint_form_code,
    #   epi.uf_batch_closure_flag,
    #   epi.uf_target_plant_code,
    #   epi.uf_target_stor_loc_code,
    #   epi.uf_ZT17,
    #   epi.uf_reference1_item,
    #   epi.uf_unit_price_including_tax,
    #   epi.uf_ZT13,
    #   epi.uf_ZT26,
    #   epi.uf_extended_batch_attributes1,
    #   epi.uf_tracking_number,
    #   eph.uf_posting_date,
    #   eph.uf_company_code
    # FROM ut_emes_post_data_item AS epi
    # LEFT JOIN ut_emes_post_data_header AS eph ON eph.uf_guid = epi.uf_guid
    # LEFT JOIN t_os_plant_storage_location_alloc AS psl ON epi.uf_plant_code = psl.plant_code 
    # AND epi.uf_stor_loc_code = psl.stor_loc_code
    # LEFT JOIN t_mmd_material_basic_data AS mbd ON epi.uf_mat_code = mbd.mat_code
    # {query_condition}
    # ORDER BY eph.uf_posting_date, eph.uf_posting_time DESC
    # """
    query_sql = f"""
    SELECT
      eph.uf_message,
      eph.uf_mat_doc_sn,
      eph.uf_year,
      eph.uf_posting_status,
      eph.uf_guid,
      epi.uf_line_id,
      eph.uf_bs_category,
      epi.uf_group_id,
      epi.uf_movement_type,
      epi.uf_plant_code,
      epi.uf_stor_loc_code,
      psl.stor_loc_desc,
      epi.uf_inventory_status,
      epi.uf_mat_code,
      mbd.mat_description,
      epi.uf_batch_sn,
      epi.uf_transaction_qty,
      epi.uf_parallel_qty,
      epi.uf_rcv_stor_loc_code,
      epi.uf_rcv_batch_sn,
      epi.uf_po_sn,
      epi.uf_po_items,
      epi.uf_plant_work_order,
      epi.uf_res_doc_sn,
      epi.uf_res_doc_sn,
      epi.uf_scarp_flag,
      epi.uf_scarp_qty,
      epi.uf_lot_no,
      epi.uf_ZT04,
      epi.uf_ZWAFERNO,
      epi.uf_wafer_id,
      epi.uf_auxiliary_material_batch_sn,
      epi.uf_ZT18,
      epi.uf_runcard,
      epi.uf_ZT07,
      epi.uf_box_no,
      epi.uf_production_date,
      epi.uf_ZT05,
      epi.uf_ZT20,
      epi.uf_ZT21,
      epi.uf_ZT35,
      epi.uf_ZT36,
      epi.uf_ZT37,
      epi.uf_ZT38,
      epi.uf_ZT06,
      epi.uf_ZT48,
      epi.uf_ZT49,
      epi.uf_ZT50,
      epi.uf_ZT51,
      epi.uf_ZT53,
      epi.uf_ZT14,
      epi.uf_ZT15,
      epi.uf_ZT54,
      epi.uf_ZT08,
      epi.uf_ZT09,
      epi.uf_joint_flag,
      epi.uf_joint_form_code,
      epi.uf_batch_closure_flag,
      epi.uf_target_plant_code,
      epi.uf_target_stor_loc_code,
      epi.uf_ZT17,
      epi.uf_reference1_item,
      epi.uf_unit_price_including_tax,
      epi.uf_ZT13,
      epi.uf_ZT26,
      epi.uf_extended_batch_attributes1,
      epi.uf_tracking_number,
      eph.uf_posting_date,
      eph.uf_company_code
    FROM ut_delivery_post_Interface_data AS epi
    LEFT JOIN ut_delivery_post_Interface_data AS eph ON eph.uf_guid = epi.uf_guid
    LEFT JOIN t_os_plant_storage_location_alloc AS psl ON epi.uf_plant_code = psl.plant_code 
    AND epi.uf_stor_loc_code = psl.stor_loc_code
    LEFT JOIN t_mmd_material_basic_data AS mbd ON epi.uf_mat_code = mbd.mat_code
    {query_condition}
    ORDER BY eph.uf_posting_date, eph.uf_posting_time DESC
    """
    query_ret = db.query_sql(query_sql)
    print(query_sql)
    return query_ret

def do_D001_post(data_group):
    # 增加校验  101 收货下是否有 543 扣料,没有则需要自动补充
    # 并自动补充D001过账信息
    code, msg = check_group_item(data_group)
    if not code:
        return 400, msg, data_group
    # 增加 541 D001 外协发料过账
    # 生成541过账数据
    head_data = {
        "post_code": "4",
        "document_date": data_group[0].get('uf_posting_date'),
        "posting_date": data_group[0].get('uf_posting_date'),
    }

    item_data_list = []
    for i in data_group:
        if i.get('uf_movement_type') == 'D005':

            query_sql1 = f'''SELECT 
            rel_po_component_number,
            rel_po_comp_batch_num

            FROM t_po_component WHERE po_sn = '{i['uf_po_sn']}' 
            AND po_items = {i['uf_po_items']} 
            AND component_code = '{i.get('uf_mat_code')}' 
            AND batch_sn = '{i.get('uf_batch_sn')}'
            '''
            query_data1 = db.query_sql(query_sql1)

            if query_data1:
                rel_po_component_number = query_data1[0].get("rel_po_component_number")
                rel_po_comp_batch_num = query_data1[0].get("rel_po_comp_batch_num")
            else:
                return 400, f'{i.get("uf_mat_code")}扣料行未找到{i.get("uf_batch_sn")}批次的绑批信息', data_group
            # 准备添加过账数据
            item_data = {
                "line_id": 1,
                "group_id": i.get('uf_group_id', '1'),
                "movement_type": "D001",
                "transaction_currency": '',
                "parallel_uom": '',
                "plant_code": i.get('uf_plant_code', ''),
                "mat_code": i.get('uf_mat_code'),
                "batch_sn": i['uf_batch_sn'],
                "stor_loc_code": i.get('uf_stor_loc_code'),
                "special_inventory_status1": "",
                "special_inventory_status2": "",
                "inventory_status": i.get('uf_inventory_status'),
                "transaction_qty": i['uf_transaction_qty'],
                "transaction_uom": i['uf_basic_uom'],
                "parallel_qty": i['uf_allocated_parallel_qty'],
                "rel_po_sn": i['uf_po_sn'],
                "rel_po_items": i['uf_po_items'],
                "rel_po_component_number": rel_po_component_number,
                "rel_po_comp_batch_num": rel_po_comp_batch_num,
                "rcv_plant_code": i.get('uf_plant_code', ''),
                "rcv_stor_loc_code": "",
                "rcv_special_inventory_status1": "V",
                "rcv_special_inventory_status2": "",
                "rcv_inventory_status": i.get('uf_inventory_status'),
                "rcv_mat_code": i['uf_mat_code'],
                "rcv_batch_sn": i['uf_batch_sn'],
                "rcv_vendor_code": get_vendor_code(db, 'D005', i['uf_po_sn']),
                "batch_number": {},
                "rcv_batch_number": {}
            }
            item_data_list.append(item_data)
    print('增加 541 D001 外协发料过账', item_data_list)
    print('增加 541 D001 外协发料过账抬头', head_data)
    from DxInventoryPostData import post_data
    code, msg, error_list, mat_doc_sn, year = post_data(str(1), user_id, head_data, item_data_list)
    if code != 200:
        error_msg = 'D001过账测试运行失败' + msg + ','.join(error_list)
        return 400, error_msg, data_group
    else:
        code, msg, error_list, mat_doc_sn, year = post_data(str(0), user_id, head_data, item_data_list)

        if code != 200:
            error_msg = 'D001过账' + msg + ','.join(error_list)
            return 400, error_msg, data_group
    # D001过账完成继续之后的过账
    return 200, 'D001过账完成', data_group
def get_vendor_code(db, uf_movement_type, uf_po_sn):
    if uf_movement_type == "D005":
        sql = f'SELECT vendor_code FROM t_po_header WHERE po_sn = "{uf_po_sn}"'
        data = db.query_sql(sql)
        if data:
            return data[0]['vendor_code']
    return ''
def do_post_single_group(data_group):
    """
    过账
    :param data_group
    :return:
    """
    total_start_time = time.perf_counter()

    uf_bs_category = data_group[0]['uf_bs_category']
    uf_posting_date = data_group[0]['uf_posting_date']
    uf_guid = data_group[0]['uf_guid']

    header = {
        'post_code': POST_CODE_MAP[uf_bs_category],
        'document_date': uf_posting_date,
        'posting_date': uf_posting_date,
        'summary_unique_number': uf_guid,
    }

    post_items = []
    line_id_counter = 0

    po_batch_binding_allocated = {}
    if uf_bs_category == OFFLINE or uf_bs_category == CANCEL_OFFLINE:
        header['ztype'] = 'E'
        for item in data_group:
            po_sn = item['uf_po_sn']
            po_items = item['uf_po_items']
            movement_type = item['uf_movement_type']
            is_receiving = (movement_type == RECEIVING)
            line_id = item['uf_line_id']
            post_item_map = {
                'uf_guid': uf_guid,
                'uf_line_id': line_id,
                'summary_unique_number': uf_guid,
                'line_id': line_id,
                'summary_line': line_id,
                'movement_type': movement_type,
                'plant_code': item['uf_plant_code'],
                'inventory_status': '0',
                'parent_id': 0,
                'quality_insp_order_mark': 0,
                'rel_document_year': '',
                'rel_document_no': '',
                'ref_document_mat': '',
                'pre_document_no': '',
                'pre_document_item': '',
                'pre_document_year': '',
                'special_inventory_status1': '' if uf_bs_category == OFFLINE else 'V',
                'special_inventory_status2': '',
                'rcv_special_inventory_status1': 'V' if uf_bs_category == OFFLINE else '',
                'transaction_amount': 0,
                'transaction_currency': '',
                'batch_closure_flag': '',
                'batch_closure_date': '',
                'prodosn': '',
                'prodo_component_number': 0,
                'rel_dn_sn': '',
                'rel_dn_item': 0,
                'picking_document': '',
                'batch_item': 0,
                'rel_procure_dn_sn': '',
                'rel_procure_dn_item': 0,
                'pod_related': '',
                'ro_sn': '',
                'ro_items': 0,
                'rel_so_sn': '',
                'rel_so_items': 0,
                'customer_code': '',
                'so_sn': '',
                'so_items': 0,
                'project_sn': '',
                'vendor_code': '' if uf_bs_category == OFFLINE else po_header_map.get(po_sn, {}).get('vendor_code', ''),
                'rcv_vendor_code': po_header_map.get(po_sn, {}).get('vendor_code', '') if uf_bs_category == OFFLINE else '',
                'po_sn': item['uf_po_sn'],
                'po_items': 0,
                'wbs_elements': '',
                'cost_center': '',
                'cost_business_object': '',
                'cost_business_object1': '',
                'profit_center': '',
                'accounting_subjects': '',
                'asset_code1': '',
                'asset_code2': '',
                'equipment_code': '',
                'express_delivery': '',
                'rcv_batch_number': {},
                'batch_number': {}
            }

            stor_loc_code = item['uf_stor_loc_code']
            post_item_map['stor_loc_code'] = stor_loc_code
            mat_code = item['uf_mat_code']
            post_item_map['mat_code'] = mat_code

            batch_sn = item['uf_batch_sn']
            if not batch_sn:
                auxiliary_material_batch_sn = item['uf_auxiliary_material_batch_sn']
                if not auxiliary_material_batch_sn:
                    msg = f'uf_line_id为{line_id}行的批次号和辅料批次号都为空'
                    return mark_group_as_error(data_group, msg)

                batch_sn = auxiliary_material_batch_sn
            post_item_map['batch_sn'] = batch_sn

            material_inner_map = material_map.get(mat_code, {})

            basic_uom = material_inner_map.get('basic_uom', '')
            post_item_map['basic_uom'] = basic_uom

            mat_group = material_inner_map.get('mat_group', '')
            if not mat_group:
                msg = f'uf_line_id为{line_id}行根据物料编码{mat_code}查不到物料组请检查'
                return mark_group_as_error(data_group, msg)

            parallel_uom = material_inner_map.get('parallel_uom', '')
            transaction_uom = basic_uom
            post_item_map['parallel_uom'] = parallel_uom
            post_item_map['transaction_uom'] = transaction_uom

            assign_quantities(post_item_map, item, parallel_uom)

            po_items = item['uf_po_items']
            post_item_map['rel_po_sn'] = po_sn
            post_item_map['rel_po_items'] = po_items
            post_item_map['po_sn'] = po_sn
            post_item_map['po_items'] = po_items
            post_item_map['rcv_plant_code'] = item['uf_plant_code']
            post_item_map['rcv_stor_loc_code'] = stor_loc_code
            post_item_map['rcv_special_inventory_status2'] = ''
            post_item_map['rcv_inventory_status'] = '0'
            post_item_map['rcv_mat_code'] = mat_code
            post_item_map['rcv_batch_sn'] = batch_sn
            post_item_map['rcv_po_sn'] = po_sn
            post_item_map['rcv_po_items'] = po_items

            if uf_bs_category == CANCEL_OFFLINE:
                post_item_map['po_sn'] = ''
                post_item_map['po_items'] = 0
                post_item_map['rel_po_sn'] = po_sn
                post_item_map['rel_po_items'] = po_items
                post_item_map['rcv_po_sn'] = po_sn
                post_item_map['rcv_po_items'] = po_items

            uf_runcard = item.get('uf_runcard', '')
            comp_key = (po_sn, po_items, mat_code)
            rel_po_component_number = po_component_map.get(comp_key, 0)
            bind_key = (po_sn, po_items, mat_code, batch_sn, uf_runcard)
            rel_po_batch_num_list = po_batch_binding_map.get(bind_key, [])
            print('bind_key:', bind_key, rel_po_batch_num_list)

            if movement_type not in ('R003', 'R012'):
                if not rel_po_batch_num_list:
                    msg = f'uf_line_id为{line_id}行非收货行的关联采购订单组件批次序号为0'
                    # 再根据配置查一遍
                    if initial_attribute_map:
                        runcard_config = initial_attribute_map['uf_field_value']
                        ret = query_batch_num(po_sn, po_items, mat_code, batch_sn, runcard_config)
                        if not ret:
                            return mark_group_as_error(data_group, msg)
                        rel_po_comp_batch_num = ret[0]['rel_po_comp_batch_num']
                    else:
                        return mark_group_as_error(data_group, msg)

            post_item_map['rel_po_component_number'] = rel_po_component_number
            if rel_po_batch_num_list and isinstance(rel_po_batch_num_list, list) and len(rel_po_batch_num_list) > 1:
                print(bind_key, rel_po_batch_num_list)
                if bind_key not in po_batch_binding_allocated:
                    po_batch_binding_allocated[bind_key] = rel_po_batch_num_list[0]
                    post_item_map['rel_po_comp_batch_num'] = rel_po_batch_num_list[0]
                else:
                    post_item_map['rel_po_comp_batch_num'] = rel_po_batch_num_list[1]
            elif rel_po_batch_num_list and isinstance(rel_po_batch_num_list, list) and len(rel_po_batch_num_list) == 1:
                post_item_map['rel_po_comp_batch_num'] = rel_po_batch_num_list[0]
            else:
                post_item_map['rel_po_comp_batch_num'] = rel_po_comp_batch_num
            post_items.append(post_item_map)


    elif uf_bs_category == OUTSOURCED_PROCESSING:

        # D001过账执行

        code, msg, data_group = do_D001_post(data_group)

        if code != 200:
            return mark_group_as_error(data_group, msg)

        header['ztype'] = 'F'

        # 联单标识存在

        if data_group[0].get('uf_joint_flag', ''):

            # 联单逻辑

            turnkey_data = []

            for item in data_group:

                po_sn = item['uf_po_sn']

                po_items = item['uf_po_items']

                joint_form_code = item['uf_joint_form_code']

                po_item_info = po_item_map.get((po_sn, po_items), {})

                uf_joint_form_code = po_item_info.get('uf_joint_form_code', '')

                if uf_joint_form_code != joint_form_code:

                    msg = '联单标识代码和采购订单行查出不一致'

                    return mark_group_as_error(data_group, msg)

                else:

                    turnkey_data.append(item)

            start_time = time.perf_counter()

            from Z_TurnkeyOrderLinkedMaterialProcess import (
                turnkey_order_linked_material,
            )

            turnkey_response = turnkey_order_linked_material(turnkey_data, 0, user_id)

            end_time = time.perf_counter()

            logger.printInfo("调turnkey订单收货耗时:", end_time - start_time)

            code = turnkey_response.get('code', 500)

            msg = turnkey_response.get('msg', '')

            if code != 200:

                return mark_group_as_error(data_group, msg)

            else:

                mat_doc_sn = turnkey_response.get('mat_doc_sn', '')

                year = turnkey_response.get('year', '')

                for item in data_group:
                    item['uf_mat_doc_sn'] = mat_doc_sn

                    item['uf_year'] = year

                    item['uf_post_status'] = 'S'

                    item['uf_message'] = '过账成功'

                return code, '过账成功', data_group


        # 联单标识不存在

        else:

            start_time = time.perf_counter()

            grouped_items = defaultdict(list)

            for item in data_group:
                line_id_counter += 1

                item['line_id'] = line_id_counter

                group_id = item.get('uf_group_id', '')

                grouped_items[group_id].append(item)

            main_line_id_of_group = {}

            for group_id, items in grouped_items.items():

                for item in items:

                    if item['uf_movement_type'] == RECEIVING:
                        parent_line_id = item['line_id']

                        main_line_id_of_group[group_id] = parent_line_id

                        break

            post_items = []

            comp_batch_flag = False

            for item in data_group:

                uf_line_id = item['uf_line_id']

                po_sn = item['uf_po_sn']

                po_items = item['uf_po_items']

                mat_code = item['uf_mat_code']

                movement_type = item['uf_movement_type']

                group_id = item.get('uf_group_id', '')

                is_receiving = (movement_type == RECEIVING)

                material_inner_map = material_map.get(mat_code, {})

                mat_group = material_inner_map.get('mat_group', '')

                if not mat_group:
                    msg = f'uf_line_id为{uf_line_id}行根据物料编码{mat_code}查不到物料组'

                    return mark_group_as_error(data_group, msg)

                po_header_inner_map = po_header_map.get(po_sn, {})

                vendor_code = po_header_inner_map.get('vendor_code', '')

                uf_quality_type = quality_type_map.get((uf_guid, uf_line_id), '')

                parallel_uom = material_inner_map.get('parallel_uom', '')

                post_item_map = {

                    'uf_guid': uf_guid,

                    'uf_line_id': uf_line_id,

                    'summary_line': uf_line_id,

                    'summary_unique_number': uf_guid,

                    'plant_code': item['uf_plant_code'],

                    'inventory_status': item['uf_inventory_status'],

                    'quality_insp_order_mark': 0,

                    'rel_document_year': '',

                    'rel_document_no': '',

                    'ref_document_mat': '',

                    'pre_document_no': '',

                    'pre_document_item': '',

                    'pre_document_year': '',

                    'special_inventory_status1': 'V' if movement_type == BACKFLUSH else '',

                    'special_inventory_status2': '',

                    'transaction_amount': 0,

                    'transaction_currency': '',

                    'batch_closure_flag': '',

                    'batch_closure_date': '',

                    'prodosn': '',

                    'prodo_component_number': 0,

                    'rel_dn_sn': '',

                    'rel_dn_item': 0,

                    'picking_document': '',

                    'batch_item': 0,

                    'rel_procure_dn_sn': '',

                    'rel_procure_dn_item': 0,

                    'pod_related': '',

                    'ro_sn': '',

                    'ro_items': 0,

                    'rel_so_sn': '',

                    'rel_so_items': 0,

                    'customer_code': '',

                    'so_sn': '',

                    'so_items': 0,

                    'project_sn': '',

                    'po_sn': '',

                    'po_items': 0,

                    'wbs_elements': '',

                    'cost_center': '',

                    'cost_business_object': '',

                    'cost_business_object1': '',

                    'profit_center': '',

                    'accounting_subjects': '',

                    'asset_code1': '',

                    'asset_code2': '',

                    'equipment_code': '',

                    'express_delivery': item['uf_tracking_number'],

                    'rcv_batch_number': {},

                    'batch_number': {},

                    'stor_loc_code': item['uf_stor_loc_code'],

                    'movement_type': movement_type,

                    'mat_code': mat_code,

                    'transaction_uom': material_inner_map.get('basic_uom', ''),

                    'parallel_uom': parallel_uom,

                    'uf_note1': item.get('uf_note1', ''),

                    'rel_po_sn': po_sn,

                    'rel_po_items': po_items,

                    'lot_no': item['uf_lot_no'],

                    'uf_ZT04': item['uf_ZT04'],

                    'wafer_id': item['uf_wafer_id'],

                    'uf_ZT07': item['uf_ZT07'],

                    'uf_ZT08': item['uf_ZT08'],

                    'uf_runcard': item['uf_runcard'],

                    'uf_box_no': item['uf_box_no'],

                    'production_date': item['uf_production_date'],

                    'uf_ZT09': item['uf_ZT09'],

                    'uf_ZT17': item['uf_ZT17'],

                    'batch_sn': '',

                    'rel_po_component_number': 0,

                    'rel_po_comp_batch_num': 0,

                }

                uf_batch_closure_flag = item['uf_batch_closure_flag']

                if uf_batch_closure_flag:

                    post_item_map['batch_closure_flag'] = 1

                    post_item_map['batch_closure_date'] = item.get('uf_posting_date', '')

                else:

                    post_item_map['batch_closure_flag'] = 0

                    post_item_map['batch_closure_date'] = ''

                assign_quantities(post_item_map, item, parallel_uom)

                if is_receiving:

                    # 1-30 新增判断取rel_po_comp_batch_num的逻辑

                    uf_pkg = material_inner_map.get('uf_pkg', '')

                    if mat_group == '2001' and 'COF' in uf_pkg:
                        comp_batch_flag = True

                    uf_posting_date = item.get('uf_posting_date', '')

                    uf_ZT57 = po_header_inner_map.get('uf_ZT57', '')

                    wo_type = po_header_inner_map.get('wo_type', '')

                    batch_number = {

                        'receive_date': uf_posting_date,

                        'lot_no': item.get('uf_lot_no', ''),

                        'uf_ZT04': item.get('uf_ZT04', ''),

                        'wafer_id': item.get('uf_wafer_id', ''),

                        'uf_ZT07': item.get('uf_ZT07', ''),

                        'uf_ZT18': item.get('uf_ZT18', ''),

                        'uf_runcard': item.get('uf_runcard', ''),

                        'uf_box_no': item.get('uf_box_no', ''),

                        'production_date': item.get('uf_production_date', ''),

                        'uf_ZT05': item.get('uf_ZT05', ''),

                        'uf_ZT20': item.get('uf_ZT20', ''),

                        'uf_ZT21': item.get('uf_ZT21', ''),

                        'uf_ZT35': item.get('uf_ZT35', ''),

                        'uf_ZT36': item.get('uf_ZT36', ''),

                        'uf_ZT37': item.get('uf_ZT37', ''),

                        'uf_ZT38': item.get('uf_ZT38', ''),

                        'uf_ZT06': item.get('uf_ZT06', ''),

                        'uf_ZT48': item.get('uf_ZT48', ''),

                        'uf_ZT49': item.get('uf_ZT49', ''),

                        'uf_ZT50': item.get('uf_ZT50', ''),

                        'uf_ZT51': item.get('uf_ZT51', ''),

                        'uf_ZT53': item.get('uf_ZT53', ''),

                        'uf_ZT14': item.get('uf_ZT14', ''),

                        'uf_ZT15': item.get('uf_ZT15', ''),

                        'uf_ZT54': item.get('uf_ZT54', ''),

                        'uf_ZT08': item.get('uf_ZT08', ''),

                        'uf_ZT09': item.get('uf_ZT09', ''),

                        'uf_ZT17': item.get('uf_ZT17', ''),

                        'uf_ZT57': uf_ZT57,

                        'uf_ZT52': '',

                        'uf_ZT10': '',

                        'uf_quality_type': uf_quality_type,

                        'batch_type': wo_type

                    }

                    if mat_group == '2002':

                        batch_number['uf_ZT59'] = po_sn

                    elif mat_group == '2003':

                        batch_number['uf_ZT60'] = po_sn

                    elif mat_group in ('1002', '1004'):

                        batch_number['uf_ZT55'] = po_sn

                    elif mat_group == '1003':

                        batch_number['uf_ZT56'] = po_sn

                    elif mat_group == '2001':

                        batch_number['uf_ZT25'] = po_sn

                    uf_thinning_thickness = material_inner_map.get('uf_thinning_thickness', '')

                    batch_number['uf_ZT11'] = uf_thinning_thickness

                    uf_bumping_mask = zt52_map.get((mat_code, vendor_code), '')

                    batch_number['uf_ZT52'] = uf_bumping_mask

                    post_item_map['batch_number'] = batch_number

                    post_item_map['batch_sn'] = item.get('uf_batch_sn', '')

                    if mat_group == '1002':

                        post_item_map.update({

                            'uf_ZT05': item['uf_ZT05'],

                            'uf_ZT20': item['uf_ZT20'],

                            'uf_ZT21': item['uf_ZT21'],

                            'uf_ZT35': item['uf_ZT35'],

                            'uf_ZT36': item['uf_ZT36'],

                            'uf_ZT37': item['uf_ZT37'],

                            'uf_ZT38': item['uf_ZT38'],

                        })

                        post_item_map['uf_ZT15'] = po_header_inner_map.get('vendor_short_name', '')

                    elif mat_group == '2002':

                        post_item_map.update({

                            'uf_ZT06': item['uf_ZT06'],

                            'uf_ZT48': item['uf_ZT48'],

                            'uf_ZT49': item['uf_ZT49'],

                            'uf_ZT50': item['uf_ZT50'],

                            'uf_ZT51': item['uf_ZT51'],

                        })

                        post_item_map['uf_ZT54'] = po_header_inner_map.get('vendor_short_name', '')

                        post_item_map['uf_ZT59'] = po_sn

                        post_item_map['transaction_qty'] = item['uf_parallel_qty']

                        post_item_map['parallel_qty'] = 0

                    elif mat_group == '1003':

                        post_item_map['uf_ZT53'] = po_header_inner_map.get('vendor_short_name', '')

                    elif mat_group == '2001':

                        post_item_map['uf_ZT14'] = po_header_inner_map.get('vendor_short_name', '')

                    elif mat_group == '2003':

                        post_item_map['uf_ZT60'] = po_sn

                    post_item_map['vendor_code'] = ''

                    post_item_map['parent_id'] = 0


                else:

                    post_item_map['parent_id'] = main_line_id_of_group.get(group_id, 0)

                    post_item_map['vendor_code'] = vendor_code

                    batch_sn = item['uf_batch_sn'] or item.get('uf_auxiliary_material_batch_sn', '')

                    post_item_map['batch_sn'] = batch_sn

                    comp_key = (po_sn, po_items, mat_code)

                    rel_po_component_number = po_component_map.get(comp_key, 0)

                    uf_runcard = item.get('uf_runcard', '')

                    bind_key = (po_sn, po_items, mat_code, item.get('uf_batch_sn', ''), uf_runcard)

                    if comp_batch_flag:

                        rel_po_batch_num_list = po_batch_binding_map.get(bind_key, [])

                        if not rel_po_batch_num_list:

                            msg = f'uf_line_id为{uf_line_id}行非收货行的关联采购订单组件批次序号为0'

                            if initial_attribute_map:

                                runcard_config = initial_attribute_map['uf_field_value']

                                ret = query_batch_num(po_sn, po_items, mat_code, batch_sn, runcard_config)

                                if not ret:
                                    return mark_group_as_error(data_group, msg)

                                rel_po_comp_batch_num = ret[0]['rel_po_comp_batch_num']

                            else:

                                return mark_group_as_error(data_group, msg)

                    else:

                        sql = f"""

                        select rel_po_comp_batch_num from t_po_batch_binding where po_sn='{po_sn}' and 

                        po_items={po_items} and component_code='{mat_code}' and batch_sn='{batch_sn}'

                        ORDER BY po_sn, po_items, rel_po_component_number, rel_po_comp_batch_num

                        """

                        ret = db.query_sql(sql)

                        if not ret:
                            msg = f'uf_line_id为{uf_line_id}行非收货行的关联采购订单组件批次序号为0'

                            return mark_group_as_error(data_group, msg)

                        rel_po_comp_batch_num = ret[0]['rel_po_comp_batch_num']

                        rel_po_batch_num_list = [item.get('rel_po_comp_batch_num') for item in ret]

                    post_item_map['rel_po_component_number'] = rel_po_component_number

                    if rel_po_batch_num_list and isinstance(rel_po_batch_num_list, list) and len(
                            rel_po_batch_num_list) > 1:

                        print(bind_key, rel_po_batch_num_list)

                        if bind_key not in po_batch_binding_allocated:

                            po_batch_binding_allocated[bind_key] = rel_po_batch_num_list[0]

                            post_item_map['rel_po_comp_batch_num'] = rel_po_batch_num_list[0]

                        else:

                            post_item_map['rel_po_comp_batch_num'] = rel_po_batch_num_list[1]

                    elif rel_po_batch_num_list and isinstance(rel_po_batch_num_list, list) and len(

                            rel_po_batch_num_list) == 1:

                        post_item_map['rel_po_comp_batch_num'] = rel_po_batch_num_list[0]

                    else:

                        post_item_map['rel_po_comp_batch_num'] = rel_po_comp_batch_num

                post_item_map['line_id'] = item['line_id']

                post_items.append(post_item_map)

            end_time = time.perf_counter()

            logger.printInfo("外协循环耗时日志:", end_time - start_time)

    elif uf_bs_category == BUYOUT:
        header['ztype'] = 'F'
        for item in data_group:
            uf_line_id = item['uf_line_id']
            item_map = {
                'uf_guid': uf_guid,
                'uf_line_id': uf_line_id,
                'summary_line': uf_line_id,
                'summary_unique_number': uf_guid,
                'line_id': uf_line_id,
                'movement_type': item['uf_movement_type'],
                'stor_loc_code': item['uf_stor_loc_code'],
                'inventory_status': '0',
                'parent_id': 0,
                'quality_insp_order_mark': 0,
                'rel_document_year': '',
                'rel_document_no': '',
                'ref_document_mat': '',
                'pre_document_no': '',
                'pre_document_item': '',
                'pre_document_year': '',
                'special_inventory_status1': '',
                'special_inventory_status2': '',
                'transaction_amount': 0,
                'transaction_currency': '',
                'batch_closure_flag': '',
                'batch_closure_date': '',
                'prodosn': '',
                'prodo_component_number': 0,
                'rel_dn_sn': '',
                'rel_dn_item': 0,
                'picking_document': '',
                'batch_item': 0,
                'rel_procure_dn_sn': '',
                'rel_procure_dn_item': 0,
                'pod_related': '',
                'ro_sn': '',
                'ro_items': 0,
                'rel_so_sn': '',
                'rel_so_items': 0,
                'customer_code': '',
                'so_sn': '',
                'so_items': 0,
                'project_sn': '',
                'vendor_code': '',
                'po_sn': item['uf_po_sn'],
                'po_items': 0,
                'wbs_elements': '',
                'cost_center': '',
                'cost_business_object': '',
                'cost_business_object1': '',
                'profit_center': '',
                'accounting_subjects': '',
                'asset_code1': '',
                'asset_code2': '',
                'equipment_code': '',
                'express_delivery': item['uf_tracking_number']
            }

            mat_code = item['uf_mat_code']
            plant_code = item['uf_plant_code']
            item_map['plant_code'] = plant_code
            item_map['mat_code'] = mat_code
            po_sn = item['uf_po_sn']
            po_items = item['uf_po_items']
            item_map['rel_po_sn'] = po_sn
            item_map['rel_po_items'] = po_items
            item_map['receive_date'] = item['uf_posting_date']
            wo_type = po_header_map.get(po_sn, {}).get('wo_type', '')
            item_map['wo_type'] = wo_type
            item_map['reference1_item'] = item['uf_reference1_item']
            item_map['uf_ZT13'] = item['uf_ZT13']
            item_map['extended_batch_attributes1'] = item['uf_extended_batch_attributes1']
            item_map['uf_ZT26'] = item['uf_ZT26']
            item_map['uf_ZT04'] = item['uf_ZT04']
            item_map['wafer_id'] = item['uf_wafer_id']
            item_map['vendor_batch'] = item['uf_auxiliary_material_batch_sn']

            # 批次号
            item_map['batch_sn'] = item['uf_batch_sn']

            po_item_info = po_item_map.get((po_sn, po_items), {})
            transaction_uom = po_item_info.get('pur_uom', '')
            item_map['transaction_uom'] = transaction_uom

            material_inner_map = material_map.get(mat_code, {})
            parallel_uom = material_inner_map.get('parallel_uom', '')
            item_map['parallel_uom'] = parallel_uom

            uf_quality_type = quality_type_map.get((uf_guid, uf_line_id), '')

            mat_group = material_inner_map.get('mat_group', '')
            if not mat_group:
                msg = f'uf_line_id为{uf_line_id}行根据物料编码{mat_code}查不到物料组'
                return mark_group_as_error(data_group, msg)

            assign_quantities(item_map, item, parallel_uom)

            batch_map = {
                'lot_no': item['uf_lot_no'],
                'receive_date': item['uf_posting_date'],
                'batch_type': wo_type,
                'uf_ZT13': item['uf_ZT13'],
                'extended_batch_attributes1': item['uf_extended_batch_attributes1'],
                'uf_ZT26': item['uf_ZT26'],
                'uf_ZT04': item['uf_ZT04'],
                'wafer_id': item['uf_wafer_id'],
                'vendor_batch': item['uf_auxiliary_material_batch_sn'],
                'uf_quality_type': uf_quality_type
            }
            item_map['batch_number'] = batch_map

            post_items.append(item_map)

    else:
        return 400, '暂不支持改业务类型的过账', data_group

    total_end_time = time.perf_counter()
    logger.printInfo("调用bapi前总耗时:", total_end_time - total_start_time)

    start_time = time.perf_counter()

    ito_duplicate = ['uf_step', 'uf_mat_doc_sn', 'uf_year', 'uf_ito_sn', 'uf_status', 'uf_message']

    item = data_group[0]
    po_sn = item['uf_po_sn']
    po_items = item['uf_po_items']
    plant_code_from = query_plant_code(po_sn, po_items)
    target_plant_code = item['uf_target_plant_code']

    # 先查ut_step_log_for_ito_by_purchase_receipt表
    step_log_sql = f"""
    SELECT 
        uf_step, uf_ito_sn, uf_mat_doc_sn, uf_year
    FROM 
        ut_step_log_for_ito_by_purchase_receipt 
    WHERE uf_guid = '{uf_guid}'
    """
    ret = db.query_sql(step_log_sql)
    if ret:
        mat_doc_sn = ret[0]['uf_mat_doc_sn']
        year = ret[0]['uf_year']
        step = ret[0]['uf_step']
        ito_sn = ret[0]['uf_ito_sn']

        insert_map = {'uf_guid': uf_guid, 'uf_mat_doc_sn': mat_doc_sn, 'uf_year': year}

        if step == 1:
            # 步骤1表示创建调拨单失败，重新创建
            code, msg, ito_sn = do_ito_create(plant_code_from, target_plant_code, data_group, insert_map,
                                              ito_duplicate)
            if code != 200:
                mark_group_as_error(data_group, msg)
                return 400, msg, data_group
        elif step > 2:
            return 400, f'调拨单{ito_sn}已经过账成功，请检查', data_group

        # 调拨单过账
        post_code, msg = do_ito_post(ito_sn, insert_map, ito_duplicate)
        if post_code != 200:
            mark_group_as_error(data_group, msg)
            return 400, msg, data_group

        for item in data_group:
            item['uf_post_status'] = 'S'
            item['uf_message'] = '过账成功'
            item['uf_year'] = year
            item['uf_mat_doc_sn'] = mat_doc_sn

        return 200, '过账成功', data_group

    else:
        # 没有记录走正常流程
        from DxInventoryPostData import post_data

        code, msg, error_list, mat_doc_sn, year = post_data("0", user_id, header, post_items)
        end_time = time.perf_counter()
        logger.printInfo("调用过账bapi耗时:", end_time - start_time)
        logger.printInfo("调用DxInventoryPostData-post_data return", {
            'code': code, 'msg': msg, 'error_list': error_list,
            'mat_doc_sn': mat_doc_sn, 'year': year
        })

        if code == 200:
            for item in data_group:
                item['uf_mat_doc_sn'] = mat_doc_sn
                item['uf_year'] = year
                item['uf_post_status'] = 'S'
                item['uf_message'] = '过账成功'

            if uf_bs_category == CANCEL_OFFLINE:
                movement_type = data_group[0]['uf_movement_type']
                if movement_type == 'D003':
                    posting_date = data_group[0].get('uf_posting_date', '')
                    company_code = data_group[0].get('uf_company_code', '')
                    po_sn = data_group[0].get('uf_po_sn', '')
                    po_items = data_group[0].get('uf_po_items', 0)
                    uf_runcard = data_group[0].get('uf_runcard', '')
                    if posting_date and company_code:
                        year = posting_date[:4]
                        period = posting_date[5:7]
                        change_batch_occupy_flag(company_code, year, period, po_sn, po_items, uf_runcard)

            elif uf_bs_category == BUYOUT:
                # 公司间调拨处理
                if plant_code_from != target_plant_code:
                    if target_plant_code:
                        insert_map = {'uf_guid': uf_guid, 'uf_mat_doc_sn': mat_doc_sn, 'uf_year': year}

                        # 创建调拨单
                        code, msg, ito_sn = do_ito_create(plant_code_from, target_plant_code, data_group, insert_map,
                                                          ito_duplicate)
                        if code != 200:
                            return mark_group_as_error(data_group, msg)

                        # 调拨单过账
                        post_code, msg = do_ito_post(ito_sn, insert_map, ito_duplicate)
                        if post_code != 200:
                            return mark_group_as_error(data_group, msg)

            return code, '过账成功', data_group
        else:
            for item in data_group:
                item['uf_post_status'] = 'E'
                item['uf_year'] = ''
                item['uf_mat_doc_sn'] = ''
                item['uf_message'] = error_list[0] if error_list else msg
            return code, error_list[0] if error_list else msg, data_group


def do_post(data):
    """
    取消多线程，分组串行过账
    """
    global material_map, po_header_map, zt52_map, po_item_map, quality_type_map, po_component_map, po_batch_binding_map, initial_attribute_map

    mat_codes = set()
    po_sns = set()
    po_pairs = set()
    guid_line_pairs = set()
    mat_po_pairs = set()

    waited_gen_batch_nums = []

    for item in data:
        mat_code = item['uf_mat_code']
        po_sn = item['uf_po_sn']
        po_items = item['uf_po_items']
        guid = item['uf_guid']
        line_id = item['uf_line_id']
        mat_codes.add(mat_code)
        po_sns.add(po_sn)
        po_pairs.add((po_sn, po_items))

        uf_bs_category = item['uf_bs_category']
        should_generate = False

        if uf_bs_category == OUTSOURCED_PROCESSING:
            guid_line_pairs.add((guid, line_id))
            mat_po_pairs.add((mat_code, po_sn))

            if not item.get('uf_joint_flag', ''):
                uf_movement_type = item['uf_movement_type']
                if uf_movement_type == RECEIVING:
                    waited_gen_batch_nums.append(item)
        elif uf_bs_category == BUYOUT:
            should_generate = True

        if should_generate:
            waited_gen_batch_nums.append(item)

    # 提前处理批次号和lot_no
    if waited_gen_batch_nums:
        flag, new_gen_batch_nums = process_batch_number(waited_gen_batch_nums)
        if not flag:
            return 400, new_gen_batch_nums, data
        else:
            update_map = {(item['uf_guid'], item['uf_line_id']): item for item in new_gen_batch_nums}
            for item in data:
                uf_guid, uf_line_id = item['uf_guid'], item['uf_line_id']
                uni_key = (uf_guid, uf_line_id)
                if uni_key in update_map:
                    item.update({'uf_batch_sn': update_map.get(uni_key, {}).get('uf_batch_sn', '')})
                    lot_no = update_map.get(uni_key, {}).get('uf_lot_no', '')
                    item.update({'uf_lot_no': lot_no})

    material_map = {}
    start_time = time.perf_counter()
    if mat_codes:
        mat_list = ','.join(f"'{c}'" for c in mat_codes)
        sql = f"SELECT mat_code, basic_uom, parallel_uom, uf_thinning_thickness, mat_group, uf_pkg FROM t_mmd_material_basic_data WHERE mat_code IN ({mat_list})"
        for row in db.query_sql(sql):
            material_map[row['mat_code']] = row

    po_header_map = {}
    if po_sns:
        po_list = ','.join(f"'{s}'" for s in po_sns)
        sql = f"SELECT h.po_sn, h.vendor_code, h.wo_type, h.uf_ZT57, vbd.vendor_short_name FROM t_po_header h JOIN t_bpv_vendor_basic_data vbd ON h.vendor_code=vbd.vendor_code WHERE po_sn IN ({po_list})"
        print(sql,'======')
        for row in db.query_sql(sql):
            po_header_map[row['po_sn']] = row

    zt52_map = {}
    if mat_po_pairs:
        print(mat_po_pairs,'--------')
        placeholders = ', '.join([f"('{item[0]}', '{po_header_map[item[1]]['vendor_code']}')" for item in mat_po_pairs])
        if placeholders:
            sql = f"SELECT uf_mat_code, uf_vendor_code, uf_bumping_mask FROM ut_mat_craft WHERE (uf_mat_code, uf_vendor_code) in ({placeholders}) AND uf_status = 'E'"
            for row in db.query_sql(sql):
                zt52_map[(row['uf_mat_code'], row['uf_vendor_code'])] = row['uf_bumping_mask']

    po_item_map = {}
    if po_pairs:
        placeholders = ', '.join([f"('{item[0]}', {item[1]})" for item in po_pairs])
        if placeholders:
            sql = f"SELECT po_sn, po_items, pur_uom, uf_joint_form_code FROM t_po_item WHERE (po_sn, po_items) IN ({placeholders})"
            for row in db.query_sql(sql):
                po_item_map[(row['po_sn'], row['po_items'])] = row

    quality_type_map = {}
    if guid_line_pairs:
        placeholders = ', '.join([f"('{item[0]}', {item[1]})" for item in guid_line_pairs])
        if placeholders:
            sql = f"SELECT uf_guid, uf_line_id, uf_quality_type FROM ut_emes_post_data_item WHERE (uf_guid, uf_line_id) in ({placeholders})"
            for row in db.query_sql(sql):
                quality_type_map[(row['uf_guid'], row['uf_line_id'])] = row['uf_quality_type']

    po_component_map = {}
    component_keys = set()
    for item in data:
        if item['uf_movement_type'] != RECEIVING or item['uf_bs_category'] in (OFFLINE, CANCEL_OFFLINE):
            component_keys.add((item['uf_po_sn'], item['uf_po_items'], item['uf_mat_code']))
    if component_keys:
        placeholders = ', '.join(f"('{item[0]}', {item[1]}, '{item[2]}')" for item in component_keys)
        if placeholders:
            sql = f"SELECT po_sn, po_items, component_code, rel_po_component_number FROM t_po_component WHERE (po_sn, po_items, component_code) in ({placeholders})"
            for row in db.query_sql(sql):
                po_component_map[(row['po_sn'], row['po_items'], row['component_code'])] = row['rel_po_component_number']

    po_batch_binding_map = {}
    binding_keys = []
    for item in data:
        runcard = item.get('uf_runcard', '')
        if item['uf_movement_type'] != RECEIVING or item['uf_bs_category'] in (OFFLINE, CANCEL_OFFLINE):
            key = (item['uf_po_sn'], item['uf_po_items'], item['uf_mat_code'], item.get('uf_batch_sn', '') if item.get('uf_batch_sn', '') else item.get('uf_auxiliary_material_batch_sn', ''), runcard)
            binding_keys.append(key)
    if binding_keys:
        placeholders = ', '.join(f"('{item[0]}', {item[1]}, '{item[2]}', '{item[3]}', '{item[4]}')" for item in binding_keys)
        if placeholders:
            sql = f"""SELECT po_sn, po_items, component_code, batch_sn, uf_runcard, rel_po_comp_batch_num 
                      FROM t_po_batch_binding WHERE (po_sn, po_items, component_code, batch_sn, uf_runcard) IN ({placeholders}) 
                      ORDER BY po_sn, po_items, rel_po_component_number, rel_po_comp_batch_num
                      """
            for row in db.query_sql(sql):
                key = (row['po_sn'], row['po_items'], row['component_code'], row['batch_sn'], row['uf_runcard'])
                rel_po_comp_batch_num = row['rel_po_comp_batch_num']
                if key not in po_batch_binding_map:
                    po_batch_binding_map[key] = [rel_po_comp_batch_num]
                else:
                    po_batch_binding_map[key].append(rel_po_comp_batch_num)

    # 产品写死查配置表
    sql = f"SELECT uf_field_value FROM ut_initial_attribute_field WHERE uf_field_code='uf_runcard'"
    ret = db.query_sql(sql)
    if ret:
        initial_attribute_map = ret[0]

    end_time = time.perf_counter()
    logger.printInfo("过账查询耗时:", end_time - start_time)

    groups = defaultdict(list)
    for item in data:
        groups[item['uf_guid']].append(item)

    if len(groups) == 1:
        group_data = list(groups.values())[0]
        code , _ , processed_data = do_post_single_group(group_data)

        update_after_post(processed_data)

        return code, '过账成功' if code == 200 else '过账失败, 请查看明细', processed_data

    all_results = []
    final_data = []
    max_workers = min(len(groups) + 4, 30)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_guid = {
            executor.submit(do_post_single_group, group_data): guid
            for guid, group_data in groups.items()
        }

        for future in as_completed(future_to_guid):
            try:
                code, msg, updated_group = future.result()
                all_results.append((code, msg))
                final_data.extend(updated_group)
            except Exception as e:
                guid = future_to_guid[future]
                logger.printInfo(f"guid {guid} 过账时报错:", str(e))
                traceback.print_exc()

                for item in groups[guid]:
                    item['uf_post_status'] = 'E'
                final_data.extend(groups[guid])
                all_results.append((500, str(e)))

    update_after_post(final_data)

    success = all(code == 200 for code, _ in all_results)
    if success:
        return 200, '过账成功', final_data
    else:
        return 400, '过账失败, 请查看明细', final_data


def process_batch_number(data):
    """
    批量生成批次号
    """
    check_keys = []
    for item in data:
        batch_sn = item.get('uf_batch_sn')
        if batch_sn and batch_sn.strip() != '':
            check_keys.append((item['uf_mat_code'], batch_sn.strip()))

    existing_keys = set()
    if check_keys:
        unique_keys = list(set(check_keys))
        rows = ', '.join(f"('{k[0]}', '{k[1]}')" for k in unique_keys)
        sql_check = f"""
            SELECT mat_code, batch_sn
            FROM t_batch_number
            WHERE (mat_code, batch_sn) IN ({rows})
        """
        existing = db.query_sql(sql_check)
        existing_keys = {(row['mat_code'], row['batch_sn']) for row in existing}

    to_generate_raw = []
    final_results = []

    for item in data:
        batch_sn = item.get('uf_batch_sn')
        mat_code = item['uf_mat_code']

        if batch_sn and batch_sn.strip() != '':
            key = (mat_code, batch_sn.strip())
            if key in existing_keys:
                final_results.append(item)
                continue

        to_generate_raw.append(item)

    if to_generate_raw:
        queried_items = query_batch_info(to_generate_raw)
        print(f"调生成批次数据为: {queried_items}")


        from Z_generate_batch_sn import create_batch_sns
        start_time = time.perf_counter()
        try:
            generated_numbers = create_batch_sns(db, queried_items)
        except Exception as e:
            msg = '批次生成失败请检查: ' + str(e)
            return False, msg
        end_time = time.perf_counter()
        logger.printInfo("批量生成批次号耗时:", end_time - start_time)
        for g in generated_numbers:
            final_results.append({
                'uf_guid': g['uf_guid'],
                'uf_line_id': g['uf_line_id'],
                'uf_batch_sn': g['batch_sn'],
                'uf_lot_no': g['lot_no']
            })

    return True, final_results


def post_scheduled_task():
    """
    过账-定时任务
    :return:
    """
    # query_condition = f"WHERE eph.uf_post_status != 'S' AND eph.uf_bs_category in ('{BUYOUT}', '{OFFLINE}', '{CANCEL_OFFLINE}', '{OUTSOURCED_PROCESSING}')"""
    
    query_condition = f"WHERE (eph.uf_posting_status = '' OR eph.uf_posting_status IS NULL) AND eph.uf_bs_category in ('{BUYOUT}', '{OFFLINE}', '{CANCEL_OFFLINE}', '{OUTSOURCED_PROCESSING}')"""
    query_data = query_post_data(query_condition)
    if query_data:
        grouped = defaultdict(list)
        for item in query_data:
            guid = item['uf_guid']
            grouped[guid].append(item)

        for guid, items in grouped.items():
            code, _, processed = do_post(items)
            if code == 200:
                msg = '过账成功'
                mat_doc_sn = processed[0].get('uf_mat_doc_sn', '')
            else:
                msg = processed[0].get('uf_message', '')
                mat_doc_sn = ''
            logger.printInfo(f"定时任务执行guid为{guid}过账结果", {'code': code, 'msg': msg, 'mat_doc_sn': mat_doc_sn})
    else:
        logger.printInfo('定时任务未查到到可执行过账数据', [])


def query_batch_info(data):
    guids = [(item['uf_guid'], item['uf_line_id']) for item in data]
    guids_placeholder = ', '.join([f"('{item[0]}', {item[1]})" for item in guids])

    sql = f"""
    SELECT
        i.uf_guid,
        i.uf_line_id,
        h.uf_bs_category,
        i.uf_movement_type,
        i.uf_mat_code,
        i.uf_po_sn,
        i.uf_lot_no,
        i.uf_ZT18,
        h.uf_posting_date,
        i.uf_box_no,
        i.uf_ZT07,
        i.uf_runcard,
        i.uf_batch_type,
        i.uf_quality_type,
        i.uf_wafer_id,
        i.uf_ZT04,
        i.uf_ZWAFERNO,
        i.uf_vendor_batch,
        i.uf_electroplating_date,
        i.uf_ZT06,
        i.uf_ZT48,
        i.uf_ZT49,
        i.uf_ZT50,
        i.uf_ZT51,
        mbd.mat_group,
        i.uf_ZT26
    FROM ut_emes_post_data_item i
    LEFT JOIN ut_emes_post_data_header h on i.uf_guid = h.uf_guid
    LEFT JOIN t_mmd_material_basic_data mbd on mbd.mat_code = i.uf_mat_code
    WHERE (i.uf_guid, i.uf_line_id) IN ({guids_placeholder})
    """
    rets = db.query_sql(sql)
    batch_list = []

    for ret in rets:
        po_sn = ret['uf_po_sn']
        lot_no = ret['uf_lot_no']
        uf_ZT18 = ret['uf_ZT18']
        posting_date = ret['uf_posting_date']
        uf_box_no = ret['uf_box_no']
        uf_ZT07 = ret['uf_ZT07']
        uf_runcard = ret['uf_runcard']
        batch_type = ret['uf_batch_type']
        uf_quality_type = ret['uf_quality_type']
        wafer_id = ret['uf_wafer_id']
        mat_code = ret['uf_mat_code']
        ZWAFERNO = ret['uf_ZWAFERNO']
        zt_04 = ret['uf_ZT04']
        vendor_batch = ret['uf_vendor_batch']
        electroplating_date = ret['uf_electroplating_date']
        zt_06 = ret['uf_ZT06']
        zt_48 = ret['uf_ZT48']
        zt_49 = ret['uf_ZT49']
        zt_50 = ret['uf_ZT50']
        zt_51 = ret['uf_ZT51']
        zt_26 = ret['uf_ZT26']

        new_batch = {'uf_guid': ret['uf_guid'],  'uf_line_id': ret['uf_line_id'], 'lot_no': lot_no,
                     'uf_ZT18': uf_ZT18, 'receive_date': posting_date, 'uf_box_no': uf_box_no,
                     'uf_ZT07': uf_ZT07, 'uf_runcard': uf_runcard, 'batch_type': batch_type,
                     'uf_quality_type': uf_quality_type, 'wafer_id': wafer_id, 'mat_code': mat_code,'uf_ZWAFERNO':ZWAFERNO, 'uf_ZT04': zt_04,
                     'po_sn': po_sn, 'vendor_batch': vendor_batch, 'uf_electroplating_date': electroplating_date,
                     'uf_ZT06': zt_06, 'uf_ZT48': zt_48, 'uf_ZT49': zt_49, 'uf_ZT50': zt_50, 'uf_ZT51': zt_51,
                     'uf_ZT26': zt_26}

        category = ret['uf_bs_category']

        if category == OUTSOURCED_PROCESSING:
            uf_movement_type = ret['uf_movement_type']
            mat_group = ret['mat_group']
            if uf_movement_type == RECEIVING:
                if mat_group == '2003':
                    new_batch.update({'uf_ZT60': po_sn})
                elif mat_group == '2002':
                    new_batch.update({'uf_ZT59': po_sn})
                elif mat_group == '2001':
                    new_batch.update({'uf_ZT25': po_sn})

        batch_list.append(new_batch)

    return batch_list


def change_batch_occupy_flag(company_code, year, period, po_sn, po_items, uf_runcard):

    table = f't_md_item_{company_code}_{year}{period}'
    sql = f"""
    SELECT
        mat_code,
        batch_sn
    FROM
        {table}
    WHERE rel_po_sn = '{po_sn}' and rel_po_items = {po_items} and debit_credit_mark = 'Dr'
    """
    ret = db.query_sql(sql)

    if not ret:
        logger.printInfo("change_batch_occupy_flag query no res", sql)
        return False, f'查询物料凭证表{table}无数据'

    placeholder = ', '.join(
        f"('{item['mat_code']}', '{item['batch_sn']}')"
        for item in ret
    )

    update_sql = f"""
    UPDATE t_po_batch_binding 
    SET batch_occupy_flag = 0, update_id = {user_id} 
    WHERE 
        po_sn = '{po_sn}' 
        AND po_items = {po_items} 
        AND uf_runcard = '{uf_runcard}'
        AND (component_code, batch_sn) IN ({placeholder})
    """
    rows = db.exec_sql(update_sql)
    logger.printInfo("update batch_occupy_flag rows", rows)
    db.dbCommit()

    return True, ''


def assign_quantities(
    post_item_map: dict,
    item: dict,
    parallel_uom: str
) -> None:
    if parallel_uom:
        post_item_map['transaction_qty'] = item['uf_transaction_qty']
        post_item_map['parallel_qty'] = item['uf_parallel_qty']
    else:
        post_item_map['transaction_qty'] = item['uf_parallel_qty']
        post_item_map['parallel_qty'] = 0


def do_ito_post(uf_ito_sn, insert_map, ito_duplicate):
    from Z_TransferOrderCreate import post
    post_code, post_msg = post(uf_ito_sn, user_id)

    insert_map.update({'uf_ito_sn': uf_ito_sn, 'uf_message': post_msg})

    if post_code != 200:
        insert_map.update({'uf_step': 2, 'uf_status': 'E', 'uf_message': post_msg})
    else:
        insert_map.update({'uf_step': 6, 'uf_status': 'S', 'uf_message': post_msg})

    db.batchInsertToDB('ut_step_log_for_ito_by_purchase_receipt', [insert_map],
                       DuplicateSQLKey=ito_duplicate, isUpdate=True, user_id=user_id)

    return post_code, '调拨单过账失败:' + post_msg if post_code != 200 else ''


def do_ito_create(plant_code_from, target_plant_code, data_group, insert_map, ito_duplicate):
    uf_pur_group = query_pur_group()
    inter_company_transfer_header = ({
        'uf_from_plant_code': plant_code_from,
        'uf_to_plant_code': target_plant_code,
        'uf_pur_group': uf_pur_group,
        'uf_is_in_kind': 0,
        'uf_ito_method': 'A',
        'uf_ito_type': 'ITO'
    })

    inter_company_transfer_items = []

    line_no = 0
    for item in data_group:
        line_no += 1
        inter_company_transfer_item = {
            'uf_ito_items': line_no,
            'uf_ipn': item['uf_mat_code'],
            'uf_mat_code': item['uf_mat_code'],
            'uf_transaction_qty': item['uf_transaction_qty'],
            'uf_transaction_uom': po_item_map.get((item['uf_po_sn'], item['uf_po_items']), {}).get('pur_uom'),
            'uf_from_stor_loc_code': item['uf_stor_loc_code'],
            'uf_to_stor_loc_code': item['uf_target_stor_loc_code'],
            'uf_is_integer': 0,
            'uf_batch_sn': item['uf_batch_sn'],
            'uf_parallel_qty': item['uf_parallel_qty']
        }

        inter_company_transfer_items.append(inter_company_transfer_item)

    start_time = time.perf_counter()

    from Z_TransferOrderCreate import ito_save

    inter_code, inter_msg, uf_ito_sn = ito_save(inter_company_transfer_header,
                                                inter_company_transfer_items, user_id)
    end_time = time.perf_counter()
    logger.printInfo("调公司间调拨创建耗时:", end_time - start_time)
    logger.printInfo("调用生成公司间调拨单 return",
                     {'code': inter_code, 'msg': inter_msg, 'uf_ito_sn': uf_ito_sn})

    if inter_code != 200:
        insert_map.update({'uf_step': 1, 'uf_message': inter_msg, 'uf_status': 'E'})

        db.batchInsertToDB('ut_step_log_for_ito_by_purchase_receipt', [insert_map],
                       DuplicateSQLKey=ito_duplicate, isUpdate=True, user_id=user_id)

    return inter_code, inter_msg, uf_ito_sn


def query_batch_num(po_sn, po_items, component_code, batch_sn, uf_runcard):
    sql = f"""
    SELECT rel_po_comp_batch_num FROM t_po_batch_binding WHERE po_sn = '{po_sn}' AND 
    po_items = {po_items} AND component_code = '{component_code}' AND batch_sn = '{batch_sn}' AND
    uf_runcard = '{uf_runcard}'
    """
    ret = db.query_sql(sql)

    print(sql, ret)
    return ret


def mark_group_as_error(data_group, msg):
    """
    将整个 data_group 标记为错误状态
    """
    for post_item in data_group:
        post_item['uf_post_status'] = 'E'
        post_item['uf_message'] = msg
        post_item['uf_mat_doc_sn'] = ''
        post_item['uf_year'] = ''
    return 400, msg, data_group


def getMovement_type():
    '''
    获取移动类型类别
    '''
    res = Response()

    db_helper = DbHelper()

    query_data, movement_type_list = [], []

    query_sql = '''
                    SELECT movement_type, description FROM t_movement_type
                '''
    query_data = db_helper.query_sql(query_sql)
    if query_data:
        movement_type_list = [{"value": index['movement_type'], "label": index['description']} for index in query_data]

    res.set_body(json.dumps({"code": 200, "msg": "查询成功", "data": movement_type_list}))
    res.commit(True)