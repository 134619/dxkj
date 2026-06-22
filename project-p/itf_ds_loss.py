'''
@File    : itf_ds_loss.py
@Author  : kshang@chiponeic.com
@Date    : 2025/09/19
@explain : eMES -> 秘火 切割损耗
'''

import uuid
from copy import deepcopy
from datetime import datetime

from DbHelper import DbHelper
from Z_generate_batch_sn import get_batch_sn_info

db = DbHelper()

format_msg = {
    "GUID": "E4548916-2A1C-4F27-B29C-543B7AB9A445",
    "ZYWLB": "",
    "BU_SORT1": "MOUNTEK-ME",
    "BUDAT": "2025-11-27",
    "CPUTM": "16:52:17",
    "BUKRS": "",
    "ZBZ": "",
    "ITEM": [
        {
            "ZEILE": "1",
            "GROUP_ID": "",
            "EBELN": "",
            "EBELP": "",
            "MATNR": "C8N013WAA-C",
            "WERKS": "1000",
            "LGORT": "A028",
            "INSMK": "",
            "CHARG": "2511260055",
            "ZFLCHARG": "",
            "ZJP": "",
            "ZFCB": "",
            "ZFCBT": "",
            "SCRAP": "",
            "BWART": "",
            "ZLOTQTY": "",
            "MENGE": "5.000",
            "SCRAPQTY": "",
            "ZLOT": "DAB015",
            "ZT04": "FAK036.7",
            "ZWAFERNO": "14",
            "ZT07": "",
            "ZT18": "",
            "ZT66": "",
            "ZT67": "",
            "HSDAT": "",
            "ZT62": "",
            "BWTAR": "",
            "ZT65": "",
            "ZT05": "",
            "ZT20": "",
            "ZT21": "",
            "ZT35": "",
            "ZT36": "",
            "ZT37": "",
            "ZT38": "",
            "ZT06": "",
            "ZT48": "",
            "ZT49": "",
            "ZT50": "",
            "ZT51": "",
            "ZT53": "",
            "ZT14": "",
            "ZT15": "",
            "ZT54": "",
            "ZFZXS": "",
            "BQGS": "",
            "ZTS": ""
        }
    ]
}

payload = {
    'guid':'3876818B-5911-4D02-B979-3A0EBB46B4B0',
    'uf_posting_date':'2026-01-08',
    'uf_posting_time':'15:54:27',
    'uf_remarks':' ',
    'uf_vendor_short_name':'USC-JS',
    'item': [
        {
            'uf_lot_no': 'D88411',
            'uf_mat_code': 'C1A014ZB-P',
            'uf_parallel_qty': '3.000',
            'uf_plant_code': '1000',
            'uf_stor_loc_code': 'A028',
            'uf_wafer_id': '02',
            'uf_ZT04':'FFH510.1',
            "uf_vendor_batch": "ACED01.01"
        }
    ]
}

para_mapping = {
    'guid': 'GUID',                     # 唯一标识符
    'uf_bs_category': 'ZYWLB',          # 业务类别
    'uf_vendor_short_name': 'BU_SORT1', # 供应商简称
    'uf_posting_date': 'BUDAT',         # 过账日期
    'uf_posting_time': 'CPUTM',         # 过账时间
    'uf_company_code': 'BUKRS',         # 公司代码
    'uf_remarks': 'ZBZ',                # 备注

    # 行项目标识码与组标识码
    'uf_group_id': 'GROUP_ID',      # 行项目标识码（行号）
    'uf_line_id': 'ZEILE',    # 组标识码

    # 采购订单信息
    'uf_po_sn': 'EBELN',         # 采购订单号
    'uf_po_items': 'EBELP',      # 采购订单行号

    # 物料与工厂
    'uf_mat_code': 'MATNR',      # 物料编码
    'uf_plant_code': 'WERKS',    # 工厂代码
    'uf_stor_loc_code': 'LGORT', # 库存地点

    # 库存状态与批次
    'uf_inventory_status': 'INSMK',   # 库存状态
    'uf_batch_sn': 'CHARG',           # 批次
    'uf_auxiliary_material_batch_sn': 'ZFLCHARG',  # 辅料批次
    'uf_batch_closure_flag': 'ZJP',   # 结批标识
    'uf_joint_flag': 'ZFCB',          # 联单标识
    'uf_joint_form_code': 'ZFCBT',    # 联单标识代码
    'uf_scarp_flag': 'SCRAP',         # SCRAP标识

    # 移动类型与数量
    'uf_movement_type': 'BWART',      # 移动类型
    'uf_transaction_qty': 'ZLOTQTY',  # 交易数量（片数）
    'uf_parallel_qty': 'MENGE',       # 平行数量（颗数）
    'uf_scarp_qty': 'SCRAPQTY',       # SCRAP数量

    # Lot 相关
    'uf_lot_no': 'ZLOT',              # chipone Lot
    'uf_ZT04': 'ZT04',                # Fountry Lot
    'uf_wafer_id': 'ZWAFERNO',        # 晶圆片号

    # 其他SAP扩展字段
    'uf_ZT07': 'ZT07',                # BIN
    'uf_ZT18': 'ZT18',                # 生产周
    'uf_runcard': 'ZT66',             # Runcard
    'uf_box_no': 'ZT67',              # 箱号
    'uf_production_date': 'HSDAT',    # 制造日期
    'uf_vendor_batch': 'ZT62',        # 供应商批次
    'uf_batch_type': 'BWTAR',         # 批次类型
    'uf_quality_type': 'ZT65',        # 品质类型

    # 程序与工厂信息
    'uf_ZT05': 'ZT05',                # CP程序
    'uf_ZT20': 'ZT20',                # CP2程序
    'uf_ZT21': 'ZT21',                # CP3程序
    'uf_ZT35': 'ZT35',                # CP4程序
    'uf_ZT36': 'ZT36',                # CP5程序
    'uf_ZT37': 'ZT37',                # CP6程序
    'uf_ZT38': 'ZT38',                # CP7程序
    'uf_ZT06': 'ZT06',                # FT程序
    'uf_ZT48': 'ZT48',                # FT2程序
    'uf_ZT49': 'ZT49',                # FT3程序
    'uf_ZT50': 'ZT50',                # FT4程序
    'uf_ZT51': 'ZT51',                # FT5程序
    'uf_ZT53': 'ZT53',                # BUMP厂
    'uf_ZT14': 'ZT14',                # 封装厂
    'uf_ZT15': 'ZT15',                # 测试厂(CP)
    'uf_ZT54': 'ZT54',                # 测试厂(FT)

    # 封装与标签
    'uf_ZT08': 'ZFZXS',               # 封装形式
    'uf_ZT09': 'BQGS',                # 标签格式（报文使用BQGS）
    'uf_ZT17': 'ZTS',                 # 条数

}

def ds_loss(payload, user_id):
    guid = str(uuid.uuid4())
    print('payloadpayload:', payload,'payloadpayload')
    data = payload.get('data', '')
    itemes = payload.get('item', '')

    # ---校验重复发送
    md_head = db.query_sql(f"""SELECT mat_doc_sn,
                                      year,
                                      summary_unique_number
                                 FROM t_md_header
                                 WHERE summary_unique_number = "{guid}" """)
    if len(md_head) != 0:
        ret = {'type': 'E', 'message': '重复抛送,此GUID已成功过账'}
        return ret

    # ---主料：
    # ---1、根据IPN+Foundry_lot+Wafer_ID，找秘火批次号+修正SAP批次号
    # ---2、并校验库存数量
    itemes, ret = trans_check_wafer(payload, itemes)
    if len(ret) != 0:
        return ret

    # ---辅料：
    # ---1、通过IPN+供应商批次，取批次库存
    # ---2、校验批次库存，并拆行
    itemes, ret = trans_check_sip(payload, itemes)
    if len(ret) != 0:
        return ret

    # ---BAPI准备
    post_items = []
    ut_items = []
    count = 0
    for inv_item in itemes:
        # -------BAPI行项目
        post_item = {}
        count += 1
        post_item['line_id'] = count
        post_item['mat_code'] = inv_item.get('uf_mat_code', '')
        post_item['stor_loc_code'] = inv_item.get('uf_stor_loc_code', '')
        post_item['inventory_status'] = '0'
        post_item['batch_sn'] = inv_item.get('uf_batch_sn', '')
        plant_code = inv_item.get('uf_plant_code', '') or inv_item.get('uf_stor_loc_code', '')
        post_item['plant_code'] = plant_code

        mat_info = db.query_sql(f"""
            SELECT parallel_uom FROM t_mmd_material_basic_data
            WHERE mat_code = '{inv_item["uf_mat_code"]}' LIMIT 1
        """)
        has_parallel = mat_info[0]['parallel_uom'] if mat_info else False

        post_item['movement_type'] = 'M003'

        if has_parallel:
            # 有平行单位：扣减颗数（平行数量）
            post_item['transaction_qty'] = inv_item.get('uf_parallel_qty', '')
            post_item['transaction_uom'] = 'EA'
            post_item['basic_qty'] = 0
            post_item['basic_uom'] = 'PC'
            post_item['parallel_qty'] = inv_item.get('uf_parallel_qty', '')
            post_item['parallel_uom'] = 'EA'
        else:
            # 无平行单位：扣减片数（基本数量）
            post_item['transaction_qty'] = inv_item.get('uf_parallel_qty', '')
            post_item['transaction_uom'] = 'PC'
            post_item['basic_qty'] = inv_item.get('uf_parallel_qty', '')
            post_item['basic_uom'] = 'PC'
            post_item['parallel_qty'] = 0
            post_item['parallel_uom'] = ''

        post_item['transaction_currency'] = 'CNY'
        post_item['inventory_status'] = '0'
        post_item['special_inventory_status1'] = ''
        post_item['rel_po_sn'] = ''
        post_item['rel_po_items'] = ''
        post_item['batch_number'] = {}
        post_items.append(post_item)

        # -------存行项目日志表
        ut_item = {}
        ut_item['uf_guid'] = guid
        ut_item['uf_line_id'] = post_item.get('line_id', '')
        ut_item['uf_group_id'] = ''
        ut_item['uf_res_doc_sn'] = ''
        ut_item['uf_res_doc_items'] = ''
        ut_item['uf_movement_type'] = post_item.get('movement_type', '')
        ut_item['uf_plant_code'] = post_item.get('plant_code', '')
        ut_item['uf_stor_loc_code'] = post_item.get('stor_loc_code', '')
        ut_item['uf_inventory_status'] = post_item.get('inventory_status', '')
        ut_item['uf_mat_code'] = post_item.get('mat_code', '')
        ut_item['uf_batch_sn'] = post_item.get('batch_sn', '')
        ut_item['uf_transaction_qty'] = post_item.get('transaction_qty', '')
        ut_item['uf_parallel_qty'] = post_item.get('parallel_qty', '')
        ut_item['uf_rcv_stor_loc_code'] = ''
        ut_item['uf_rcv_batch_sn'] = ''
        ut_item['uf_po_sn'] = ''
        ut_item['uf_po_items'] = ''
        ut_item['uf_plant_work_order'] = ''
        ut_item['uf_lot_no'] = inv_item.get('uf_lot_no', '')
        ut_item['uf_ZT04'] = inv_item.get('ZT04', '')
        ut_item['uf_wafer_id'] = inv_item.get('uf_wafer_id', '')
        ut_item['uf_auxiliary_material_batch_sn'] = ''
        ut_item['uf_ZT18'] = ''
        ut_item['uf_runcard'] = ''
        ut_item['uf_ZT07'] = ''
        ut_item['uf_box_no'] = ''
        ut_item['uf_production_date'] = ''
        ut_item['uf_scarp_flag'] = ''
        ut_item['uf_scarp_qty'] = ''
        ut_item['uf_ZT05'] = ''
        ut_item['uf_ZT20'] = ''
        ut_item['uf_ZT21'] = ''
        ut_item['uf_ZT35'] = ''
        ut_item['uf_ZT36'] = ''
        ut_item['uf_ZT37'] = ''
        ut_item['uf_ZT38'] = ''
        ut_item['uf_ZT06'] = ''
        ut_item['uf_ZT48'] = ''
        ut_item['uf_ZT49'] = ''
        ut_item['uf_ZT50'] = ''
        ut_item['uf_ZT51'] = ''
        ut_item['uf_ZT53'] = ''
        ut_item['uf_ZT14'] = ''
        ut_item['uf_ZT15'] = ''
        ut_item['uf_ZT54'] = ''
        ut_item['uf_ZT08'] = ''
        ut_item['uf_ZT09'] = ''
        ut_item['uf_joint_flag'] = ''
        ut_item['uf_joint_form_code'] = ''
        ut_item['uf_batch_closure_flag'] = ''
        ut_item['uf_target_plant_code'] = ''
        ut_item['uf_target_stor_loc_code'] = ''
        ut_item['uf_ZT17'] = ''
        ut_item['uf_reference1_item'] = ''
        ut_item['uf_unit_price_including_tax'] = ''
        ut_item['uf_ZT13'] = ''
        ut_item['uf_ZT26'] = ''
        ut_item['uf_extended_batch_attributes1'] = ''
        ut_item['uf_cost_center'] = ''
        ut_item['uf_wbs_elements'] = ''
        ut_item['uf_vendor_batch'] = inv_item.get('uf_vendor_batch', '')
        ut_item['uf_electroplating_date'] = ''
        ut_item['uf_batch_type'] = ''
        ut_item['uf_quality_type'] = ''
        ut_item['uf_tracking_number'] = ''
        ut_items.append(ut_item)

        # -------BAPI抬头
        post_head = {}
        post_head['post_code'] = '5'
        post_head['document_date'] = payload.get('uf_posting_date', '')
        post_head['posting_date'] = payload.get('uf_posting_date', '')
        post_head['summary_unique_number'] = payload.get('guid', '')
        post_head['company_code'] = plant_code

    # ---调BAPI
    from DxInventoryPostData import post_data
    code, msg, error_list, mat_doc_sn, year = post_data('0', user_id, post_head, post_items)
    if code == 200:
        msg = '过账成功，物料凭证号：' + mat_doc_sn
        ret = {'type': 'S', 'message': msg}
        # -------存抬头日志表
        ut_heads = []
        ut_head = {}
        ut_head['uf_guid'] = guid
        ut_head['uf_bs_category'] = '13'
        ut_head['uf_vendor_short_name'] = payload.get('uf_vendor_short_name', '')
        ut_head['uf_posting_date'] = payload.get('uf_posting_date', '')
        ut_head['uf_posting_time'] = payload.get('uf_posting_date', '') + ' ' + payload.get('uf_posting_time', '')
        ut_head['uf_company_code'] = post_head.get('company_code', '')
        ut_head['uf_remarks'] = payload.get('uf_remarks', '')
        ut_head['uf_post_status'] = 'S'
        ut_head['uf_message'] = '成功'
        ut_head['uf_mat_doc_sn'] = mat_doc_sn
        ut_head['uf_year'] = year
        ut_heads.append(ut_head)
        # db.batchInsertToDB('ut_emes_post_data_header', ut_heads)
        # # -------存行项目日志表
        # db.batchInsertToDB('ut_emes_post_data_item', ut_items)
    else:
        error_list = str(error_list)
        msg = msg + error_list
        ret = {'type': 'E', 'message': msg}
    return ret


def trans_check_wafer(head, items):
    # ---分出主料/辅料（保持不变）
    for item in items:
        qty_str = item.get('uf_parallel_qty')
        item['uf_parallel_qty'] = float(qty_str)
        item_mat_code = item.get('uf_mat_code', '')
        mat_data = db.query_sql(f"""SELECT mat_code
                                      FROM t_mmd_material_basic_data
                                      WHERE mat_code = "{item_mat_code}"
                                        AND mat_group LIKE '100%'
                                        AND uf_aux_wafer = 0 """)
        if len(mat_data) != 0:
            item['sfzl'] = 1
        else:
            item['sfzl'] = 0

    # ---主料：使用 get_batch_sn_info 分配批次并拆行
    new_items = []
    for item in items:
        if item['sfzl'] == 1:
            # 如果已有批次号，直接保留（原逻辑：若已有批次号则不重新查询）
            if item.get('uf_batch_sn', ''):
                new_items.append(item)
                continue

            # 构造批次查询请求
            batch_req = {
                'mat_code': item.get('uf_mat_code', ''),
                'count': str(int(item.get('uf_parallel_qty', 0))),  # get_batch_sn_info 期望 count 为字符串
                'uf_ZT04': item.get('ZT04', ''),
                'uf_wafer_id': item.get('uf_wafer_id', ''),
                'uf_ZT18': item.get('uf_ZT18', ''),
                'uf_storage_date': head.get('uf_posting_date', ''),  # 用抬头过账日期作为入库日期
                'uf_runcard': item.get('uf_runcard', ''),
                'uf_box_no': item.get('uf_box_no', ''),
                'uf_electroplating_date': item.get('uf_electroplating_date', '')
            }
            # 调用统一批次分配接口
            msg, batch_results = get_batch_sn_info(db, [batch_req])
            if msg:
                return items, {'type': 'E', 'message': f'批次分配失败: {msg}'}

            # 处理分配结果
            for result in batch_results:
                # 如果某条数据有错误信息，直接返回
                if result.get('batch_sn_info_msg'):
                    return items, {'type': 'E', 'message': result['batch_sn_info_msg']}
                # 遍历每个分配到的批次
                for bi in result.get('batch_sn_info', []):
                    new_item = deepcopy(item)
                    new_item['uf_batch_sn'] = bi['batch_sn']
                    new_item['uf_parallel_qty'] = float(bi['count'])
                    new_items.append(new_item)
        else:
            # 辅料行直接保留
            new_items.append(item)

    return new_items, {}


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





def process_ds_loss(incoming_list, user_id):
    if not incoming_list:
        return {'type': 'E', 'message': '无导入数据'}

    # 生成唯一GUID
    guid = str(uuid.uuid4())

    # 从第一个数据行提取过账日期和时间
    first_row = incoming_list[0]
    posting_datetime_str = first_row.get('uf_posting_date', '')
    if posting_datetime_str:
        parts = posting_datetime_str.strip().split()
        posting_date = parts[0] if len(parts) > 0 else ''
        posting_time = parts[1] if len(parts) > 1 else '00:00:00'
    else:
        posting_date = ''
        posting_time = '00:00:00'

    payload = {
        'guid': guid,
        'uf_posting_date': posting_date,
        'uf_posting_time': posting_time,
        'uf_remarks': '',
        'uf_vendor_short_name': '',  # 可根据业务补充
        'item': incoming_list
    }

    import json
    print(json.dumps(payload, indent=4, ensure_ascii=False))

    return ds_loss(payload, user_id)



# 使用示例
# if __name__ == "__main__":
#     # 模拟传入报文
#
#     result = process_ds_loss(format_msg, user_id=111)
#
#     print("result",result,'\n')

