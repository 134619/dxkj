#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@File    : itf_emes_wanjia_goods_transfer_data.py
@Author  : wenkai.zhang@dxdstech.com
@Date    : 2025/12/05
@explain : 万佳仓库调拨入库过账接口——ZMM_INT_119
"""
import copy
import datetime
import uuid
from functools import lru_cache

from CommonDataSource import uom_conv
from DbHelper import DbHelper
from DxInventoryPostData import post_data  # type:ignore库存过账
from DXReservation import reservationSave
from Z_DxBatchInventoryOccupationQuery import get_batch_inventory_Occupation
from Z_generate_batch_number import generate_batch_number

db = DbHelper()

# 接收eMES的数据做预留
# 将EMES的数据存储到自建表
# 后续由计划任务每2小时读取进行过账

"""
{
        "guid": "A20251119-001",
        "data": {
            "header": [
                {
                    "guid": "A20251119-001",//必填
                    "bs_category": "40",//必填
                    "vendor_short_name": "",
                    "posting_date": "2025-11-17",//必填
                    "posting_time": "12:48:10",//必填
                    "company_code": "1000",//必填
                    "remarks": "",
                    "item": [
                        {
                            "line_id": 1,
                            "movement_type": "T001",//必填
                            "uf_transaction":04,  #默认
                            "plant_code": "1000",//必填
                            "stor_loc_code": "A001",
                            "inventory_status": "0",//必填
                            "mat_code": "C8N1066PN-AANN-AANNNNN-A",//必填
                            "batch_sn": "",
                            "transaction_qty": 0,
                            "parallel_qty": 200,//必填
                            "rcv_stor_loc_code": "",
                            "express_delivery": "SF001",//必填
                            "lot_no": "clot1",//必填
                            "uf_ZT04": "",
                            "wafer_id": "",
                            "uf_ZT18": "",//必填
                            "runcard": "",
                            "uf_ZT07": "",
                            "box_no": "",//必填
                            "production_date": "",
                            "test_program":"",
                            "uf_ZT53": "",
                            "uf_ZT14": "",
                            "uf_ZT15": "",
                            "uf_ZT54": "",//上面4个字段至少有一个字段传非空值
                            "uf_ZT08": "",
                            "uf_ZT09": "",
                            "uf_ZT59": "",
                            "uf_ZT60": "",
                            "uf_ZT25": "",
                            "uf_ZT55": "",
                            "uf_ZT56": ""//上面5个字段至少有一个字段传非空值
                        }
                    ]
                }
            ]
        }
    }
"""


# 默认入库-供应商简称
SUPPLIER_TO_STORAGE = {
    "LEADYO": "T001",
    "HISEMI_SZ": "T002",
    "SIYOTEK": "C003",
    "JSE": "C004",
    "JSE-BJ": "C012",
    "CHIPONE_CP": "A093",
    "ATEC-SH": "C005",
    "ATEC": "C006",
    "V-TEST": "T003",
    "V-TEST-NJ": "C010",
    "V-TEST-WX": "A039",
    "MFTK": "A027",
    "FORCE-TEST": "T008",
    "SZLD": "Z005",
    "CHIPMOS": "A004",
    "CHIPMORE": "A003",
    "CHIPMORE_H": "A084",
    "USC-HF": "A011",
    "USC-JS": "A071",
    "TFME-XM": "A061",
    "JSNEPES": "A079",
    "KSATXD": "A080",
    "HTJS": "A083",
    "HTNJ": "A048",
    "JSI": "A092",
    "JCET": "A024",
    "JSCC": "A047",
    "JCAP": "A069",
    "ANST": "A018",
    "SIPLP": "A025",
    "GREATEK": "A022",
    "SFA": "A015",
    "LINGSEN": "A016",
    "TFME": "A005",
    "ASECL": "A090",
    "AMKOR": "A001",
    "FOREHOPE": "A019",
    "MOUNTEK-ME": "A067",
    "HFTF": "A006",
    "TSHT": "A020",
    "JSSISEMI": "A060",
    "SHKJ": "A075",
    "JSYXMC": "A049",
    "ZJYXM": "A076",
    "HISEMI_CZ": "A046",
    "HYYJ": "A091",
    "HTXA": "A043",
    "HTKS": "A073",
    "SZJY": "A033",
    "ATSH": "A070",
    "MOUNTEK": "A028",
    "NTTF": "A074",
}


ZMMT001_MAPPING = {
    "1000": "1000",
    "5000": "5000",
    "ABLE": "A081",
    "AE CARGO": "L009",
    "AMKOR": "A001",
    "AMKORSG": "A008",
    "ANST": "A018",
    "ASECL": "A090",
    "ATEC": "C006",
    "ATEC-SH": "C005",
    "ATSH": "A070",
    "BCD": "W021",
    "BJHY": "Z022",
    "BJJY": "Z024",
    "BJPT": "T013",
    "BONRDA": "Z039",
    "CANSEMI": "W019",
    "CARSEM": "A057",
    "CATI": "Z001",
    "CCID": "T014",
    "CHIPBOND": "A002",
    "CHIPFILM": "Z025",
    "CHIPINFOS": "T006",
    "CHIPMORE": "A003",
    "CHIPMORE_H": "A084",
    "CHIPMOS": "A004",
    "CHIPONE_CP": "A093",
    "CORE KJ": "Z033",
    "CORESSOL": "A056",
    "COSMOS_SD": "A037",
    "COSMOS_SZ": "A036",
    "CSMC": "W022",
    "CSMC-F2": "W023",
    "CTRON": "Z052",
    "D.I.T": "L007",
    "DHL": "L003",
    "DHY-SZ": "A051",
    "DONGBU": "W001",
    "EMVANGO-BJ": "Z032",
    "ENLARGE": "Z010",
    "FLEXCEED": "Z018",
    "FORCE-TEST": "T008",
    "FOREHOPE": "A019",
    "FTD": "Z007",
    "FXY_HZ": "Z051",
    "GF": "W031",
    "GF-SG": "W020",
    "GRAINIE": "Z048",
    "GREATEK": "A022",
    "GZTC": "A085",
    "HANA": "A017",
    "HARDENT": "A055",
    "HFTF": "A006",
    "HHGRACE": "W002",
    "HISEMI_CZ": "A046",
    "HISEMI_SZ": "T002",
    "HJTC": "W003",
    "HK AIR": "L016",
    "HOPEFLY-SH": "Z041",
    "HPBJ": "A064",
    "HTJS": "A083",
    "HTKS": "A073",
    "HTNJ": "A048",
    "HTXA": "A043",
    "HUIKEN-SZ": "Z047",
    "HYYJ": "A091",
    "ICAT": "A031",
    "IST-SH": "Z028",
    "IST_TW": "Z026",
    "ITS": "A023",
    "IVT": "Z006",
    "JCAP": "A069",
    "JCET": "A024",
    "JCET-SQ": "A078",
    "JCTIC": "Z053",
    "JCTM": "A099",
    "JCYN": "A098",
    "JMC": "Z002",
    "JSCC": "A047",
    "JSE": "C004",
    "JSI": "A092",
    "JSJD": "A010",
    "JSJST": "T005",
    "JSNEPES": "A079",
    "JSSISEMI": "A060",
    "JSYD": "A009",
    "JSYXMC": "A049",
    "JTEC": "Z044",
    "KEY-F": "W005",
    "KINGDOM": "Z011",
    "KJET": "A097",
    "KSATXD": "A080",
    "KUAYUE": "L004",
    "KYEC": "A007",
    "LBS": "A014",
    "LEADER": "Z043",
    "LEADER-HK": "Z045",
    "LEADYO": "T001",
    "LG INNOTEK": "Z015",
    "LINGSEN": "A016",
    "LIPPXIN-DP": "A038",
    "M31": "A054",
    "MA-TEK(SH)": "Z029",
    "MA-TEK(TW)": "Z030",
    "MAOJET": "A053",
    "MAXONE": "Z009",
    "MDK": "A072",
    "MFTK": "A027",
    "MICROTECH": "C001",
    "MINGCHANG": "Z055",
    "MMK": "Z036",
    "MOUNTEK": "A028",
    "MOUNTEK-ME": "A067",
    "MPI": "Z003",
    "MSEC": "C007",
    "NEXCHIP": "W016",
    "NHH": "A059",
    "NJXB": "A034",
    "NTTF": "A074",
    "NTTK": "A077",
    "OKINS": "C009",
    "PDMC": "M002",
    "PDMCX": "M003",
    "PFJ": "C002",
    "POWERCHIP": "W004",
    "PPT": "C011",
    "PROBE-L": "Z042",
    "PROBELOGIC": "Z014",
    "PSMC": "T007",
    "PUYA": "Z016",
    "RMT_ZZ": "A029",
    "RUICHIPS": "A089",
    "RUNPENG": "W033",
    "S.C.G-SZ": "L005",
    "SCG": "L010",
    "SCG_RMA": "R001",
    "SDBTW": "A066",
    "SEA-AIR": "L011",
    "SF": "L008",
    "SFA": "A015",
    "SHJF": "Z038",
    "SHKJ": "A075",
    "SHMXW": "Z040",
    "SICHANG": "A062",
    "SIGNETICS": "A012",
    "SILEXCEED": "T004",
    "SILTERRA": "W018",
    "SINAOAIR": "L006",
    "SINOTRANS": "L012",
    "SIPLP": "A025",
    "SIYOTEK": "C003",
    "SK": "W026",
    "SMARTGIANT": "A082",
    "SMAT": "A068",
    "SMBC-BJ": "W030",
    "SMC-SZ": "A032",
    "SMIC": "W024",
    "SMIC-BJ": "W008",
    "SMIC-SH": "W009",
    "SMIC-SZ": "W025",
    "SMIC-TJ": "W010",
    "SMNC-BJ": "W029",
    "SPILSZ": "A044",
    "SPILTW": "A065",
    "STEMCO": "Z004",
    "SUNTECH": "A050",
    "SZFM": "A063",
    "SZGLM": "Z037",
    "SZJR": "Z019",
    "SZJY": "A033",
    "SZKWT": "Z050",
    "SZLD": "Z005",
    "SZQDY": "Z049",
    "SZQHKC": "Z054",
    "SZQP": "A035",
    "SZTS": "Z013",
    "TCE": "M001",
    "TFME": "A005",
    "TFME-XM": "A061",
    "TJJM": "Z035",
    "TOWARD": "Z017",
    "TOWARD_TW": "Z020",
    "TSHT": "A020",
    "TSMC": "W011",
    "UMC": "W012",
    "UMC_CPO": "W015",
    "UNC": "A021",
    "USC": "W017",
    "USC-HF": "A011",
    "USC-JS": "A071",
    "V-TEST": "T003",
    "V-TEST-NJ": "C010",
    "V-TEST-WX": "A039",
    "VENCT": "Z056",
    "VESP-TECH": "Z031",
    "VIS": "W013",
    "VIS-SG": "W014",
    "W-ITS-HK1": "L025",
    "WINSUN": "Z027",
    "WLCSP": "A045",
    "WTK": "W006",
    "WTMEC": "Z012",
    "WXAW": "Z008",
    "WXXS": "Z021",
    "W_CHIP-HK1": "L014",
    "W_CHIP-SZ3": "L015",
    "W_CHIP-SZ5": "L001",
    "W_CHIP-ZH1": "L031",
    "W_ITS-HK1": "L025",
    "W_ITS-SCG": "L026",
    "W_ITS-SZ3": "L027",
    "W_ITS-SZ5": "L023",
    "W_ITS-ZH1": "L030",
    "W_RMA-HK1": "R002",
    "W_RMA-SZ3": "R003",
    "W_RMA-SZ5": "R004",
    "W_RMA-ZH1": "R058",
    "W_SP-HK1": "L022",
    "W_SP-SCG": "L019",
    "W_SP-SZ3": "L020",
    "W_SP-SZ5": "L021",
    "W_SP-ZH1": "L029",
    "XTX": "A087",
    "XZDY": "Z023",
    "YAO-SHUO": "Z046",
    "YCXF": "A058",
    "YDME": "W034",
    "YTEC": "C008",
    "Z-LUCKY": "A052",
    "ZENSEMI-2": "W032",
    "ZJCT": "Z034",
    "ZJYXM": "A076",
    "健天": "W028",
    "晨沛": "A088",
    "润科汇": "T009",
    "立创": "A094",
    "莹火": "A086",
    "视睿讯": "A096",
}


def get_supplier_storage_location(supplier_name, location_type='issue'):
    """根据供应商名称获取仓库位置"""
    supplier_name = supplier_name.upper() if supplier_name else ""
    if not supplier_name:
        return ""
    # 直接字典查找，大小写不敏感（统一转大写）
    return SUPPLIER_TO_STORAGE.get(supplier_name.upper(), "")


def get_receive_storage_from_zmmt001(supplier_name):
    """根据供应商名称获取接收仓库位置"""
    supplier_name = supplier_name.upper() if supplier_name else ""
    if not supplier_name:
        return ""
    return ZMMT001_MAPPING.get(supplier_name.upper(), "")


# 批次分配状态管理器
class BatchAllocationManager:
    """管理批次分配状态的全局类"""

    # 类变量，所有实例共享
    _global_batch_state = {}  # 格式: {mat_code_batch_sn_stor_loc: {'available_qty': x, 'remaining_qty': y}}
    _allocation_history = []  # 记录分配历史

    @classmethod
    def reset(cls):
        """重置批次状态（每次新请求时调用）"""
        cls._global_batch_state = {}
        cls._allocation_history = []

    @classmethod
    def update_batch_state(cls, mat_code, batch_sn, stor_loc_code, available_qty, remaining_qty):
        """更新批次状态"""
        batch_key = f"{mat_code}_{batch_sn}_{stor_loc_code}"
        cls._global_batch_state[batch_key] = {
            'available_qty': available_qty,
            'remaining_qty': remaining_qty
        }

    @classmethod
    def get_batch_state(cls, mat_code, batch_sn, stor_loc_code):
        """获取批次状态"""
        batch_key = f"{mat_code}_{batch_sn}_{stor_loc_code}"
        return cls._global_batch_state.get(batch_key)

    @classmethod
    def filter_available_batches(cls, mat_code, batch_sns, stor_loc_code, available_batches):
        """根据全局状态过滤可用批次"""
        filtered_batches = []
        for batch in available_batches:
            batch_sn = batch['batch_sn']
            state = cls.get_batch_state(mat_code, batch_sn, stor_loc_code)

            if state:
                # 如果批次在全局状态中，使用全局状态的数量
                if state['available_qty'] > 0 or state['remaining_qty'] > 0:
                    filtered_batch = batch.copy()
                    filtered_batch['available_qty'] = state['available_qty']
                    filtered_batch['remaining_qty'] = state['remaining_qty']
                    filtered_batches.append(filtered_batch)
                    print(f"批次 {batch_sn} 使用全局状态: 可用数量={state['available_qty']}")
                else:
                    print(f"批次 {batch_sn} 已在全局状态中标记为用完，跳过")
            else:
                # 批次不在全局状态中，直接使用
                filtered_batches.append(batch)

        return filtered_batches

    @classmethod
    def record_allocation(cls, allocation_result):
        """记录分配历史"""
        if isinstance(allocation_result, tuple) and allocation_result[0]:
            for alloc in allocation_result[1]:
                cls._allocation_history.append(alloc)

    @classmethod
    def get_allocation_history(cls):
        """获取分配历史"""
        return cls._allocation_history


def convert_quantity_fields_to_float(data):
    """将数量字段转换为浮点数并保留两位小数"""
    for header in data.get('header', []):
        for item in header.get('item', []):
            # 转换 transaction_qty
            if 'transaction_qty' in item:
                if item['transaction_qty'] == '' or item['transaction_qty'] is None:
                    item['transaction_qty'] = 0.0
                else:
                    try:
                        # 转换为浮点数并保留两位小数
                        item['transaction_qty'] = float(item['transaction_qty'])
                    except (ValueError, TypeError):
                        item['transaction_qty'] = 0.0

            # 转换 parallel_qty
            if 'parallel_qty' in item:
                if item['parallel_qty'] == '' or item['parallel_qty'] is None:
                    item['parallel_qty'] = 0.0
                else:
                    try:
                        # 转换为浮点数并保留两位小数
                        item['parallel_qty'] = float(item['parallel_qty'])
                    except (ValueError, TypeError):
                        item['parallel_qty'] = 0.0

            print(
                f"转换后 - line_id: {item.get('line_id')}, transaction_qty: {item.get('transaction_qty')}, parallel_qty: {item.get('parallel_qty')}")



def convert_export_rows_to_payload(rows, user_id):
    if not rows:
        return {}

    # 生成全局唯一 guid（汇总号 XBLNR1）
    global_guid = str(uuid.uuid4())

    first_row = rows[0]
    ship_date = first_row.get("production_date", "")
    if ship_date:
        try:
            posting_date = ship_date.split()[0]  # "2026-05-08"
            posting_time = ship_date             # "2026-05-08 00:00:00"
        except:
            posting_date = datetime.date.today().strftime("%Y-%m-%d")
            posting_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    else:
        posting_date = datetime.date.today().strftime("%Y-%m-%d")
        posting_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    company_code = first_row.get("CompanyCode", "1000")
    vendor_short_name = first_row.get("发出仓位名称", "")   # VETXT
    rcv_vendor_short_name = first_row.get("接收仓位名称", "") # VETXT2

    items = []
    for idx, row in enumerate(rows, start=1):
        # 基础数量
        parallel_qty = float(row.get("ChipQty", 0))
        # 交易数量（片数）默认为0，物料组为1开头时后续会调整
        transaction_qty = 0.0

        # 获取发出库存地点：若已传则直接使用，否则根据发出方供应商匹配
        stor_loc = row.get("发出仓位代码", "")
        if not stor_loc and vendor_short_name:
            stor_loc = get_supplier_storage_location(vendor_short_name, 'issue')

        # 获取接收库存地点：若已传则直接使用，否则根据接收方供应商匹配
        rcv_stor_loc = row.get("接收仓位代码", "")
        if not rcv_stor_loc and rcv_vendor_short_name:
            rcv_stor_loc = get_receive_storage_from_zmmt001(rcv_vendor_short_name)

        item = {
            "line_id": idx,
            "movement_type": "T001",                 # 规则：BWART默认311，转换为T001
            "plant_code": row.get("CompanyCode", "1000"),
            "stor_loc_code": stor_loc,
            "inventory_status": "0",                  # 固定非限制
            "mat_code": row.get("IPN", ""),
            "batch_sn": "",
            "transaction_qty": transaction_qty,
            "parallel_qty": parallel_qty,
            "rcv_stor_loc_code": rcv_stor_loc,
            "rcv_plant_code": row.get("CompanyCode", "1000"),  # 接收工厂默认同发出工厂
            "rcv_mat_code": row.get("IPN", ""),                # 接收物料默认同发出物料
            "rcv_batch_sn": "",                                 # 接收批次后续生成
            "express_delivery": row.get("实际物流单号", ""),
            "lot_no": row.get("LotNumber", ""),                 # chiponeLot
            "uf_ZT04": row.get("WaferLotNO", ""),               # FountryLot
            "wafer_id": row.get("WwaferId", ""),
            "uf_ZT18": row.get("DateCode", ""),                 # 生产周
            "runcard": row.get("OSATRuncard", ""),
            "uf_ZT07": row.get("bin别", ""),                    # BIN
            "box_no": row.get("箱号", ""),
            "production_date": row.get("production_date", "").split()[0] if row.get("production_date") else "",
            "test_program": row.get("测试程序", ""),
            "uf_ZT53": "",      # BUMP厂
            "uf_ZT14": row.get("封装厂", ""),
            "uf_ZT15": row.get("测试厂", ""),
            "uf_ZT54": "",      # 测试厂(FT)
            "uf_ZT08": row.get("封装形式", ""),
            "uf_ZT09": "",
            "uf_ZT59": "",
            "uf_ZT60": "",
            "uf_ZT25": "",
            "uf_ZT55": "",
            "uf_ZT56": "",
            # 扩展字段（规则中要求EPN，但原表没有对应列，可先存入uf_epn，如无则忽略）
            "uf_epn": row.get("EPN", ""),
        }
        # 如果库存地点仍然为空，后续校验会报错；但为了健壮性，可设置一个默认值（根据业务决定）
        items.append(item)

    header = {
        "guid": global_guid,
        "bs_category": "40",           # 业务类别固定40
        "vendor_short_name": vendor_short_name,
        "posting_date": posting_date,
        "posting_time": posting_time,
        "company_code": company_code,
        "remarks": "",
        "item": items
    }

    payload = {
        "guid": global_guid,
        "data": {
            "header": [header]
        }
    }
    return payload


def save_emes_wanjia_goods_transfer_data(payload, user_id):
    db = DbHelper()
    error_list = []
    type = ''
    message = ''
    now = datetime.datetime.now()
    if isinstance(payload, list):
        payload = convert_export_rows_to_payload(payload, user_id)

    data = payload["data"]

    # 重置批次管理器状态
    BatchAllocationManager.reset()

    # 首先转换数量字段为浮点数
    convert_quantity_fields_to_float(data)
    # 验证基础字段
    code, msg, header_mapped = validate_fields(payload)
    if code != 200:
        # error_list.append(msg)
        return {
            "guid": payload.get("guid", ""),
            "type": "E",
            "message": f"字段长度校验失败：{msg}"
        }

    # 标记是否已创建预留单
    has_created_reservation = False
    created_reservations = []  # 记录已创建的预留单

    # 检查数据抬头并处理批次分配
    for index, each in enumerate(data['header']):
        # guid检查
        if each['guid'] == '':
            error_list.append("第{}条数据中guid必填".format(index))
            continue

        # 业务类别检查
        if each.get('bs_category', '') == '':
            error_list.append("guid {} 中业务类别必填".format(each['guid']))
        elif each['bs_category'] not in ['40']:
            error_list.append("guid {} 中业务类别不存在".format(each['guid']))

        # 过账日期检查
        if each.get('posting_date', '') == '':
            error_list.append("guid {} 中过账日期必填".format(each['guid']))

        # 过账时间检查
        if each.get('posting_time', '') == '':
            error_list.append("guid {} 中过账时间必填".format(each['guid']))

        # 公司主体检查
        if each.get('company_code', '') == '':
            error_list.append("guid {} 中公司代码必填".format(each['guid']))
        else:
            if not check_company_code_exist(each['company_code']):
                error_list.append("guid {} 中公司代码{}不存在".format(each['guid'], each['company_code']))

        # 第一步：先处理批次分配
        batch_group = {}
        all_new_items = []
        # 标记当前header的批次分配是否失败
        current_header_batch_failed = False
        for index2, each2 in enumerate(each['item']):
            if each2['line_id'] == 0:
                error_list.append("guid {} 中line_id必填".format(each['guid']))
                current_header_batch_failed = True
                all_new_items.append(each2)
                continue

            # 基础字段检查
            item_errors = validate_item_fields(each, each2, index, index2)
            error_list.extend(item_errors)
            if item_errors:
                print('3333333')
                all_new_items.append(each2)
                current_header_batch_failed = True
                continue
            print(each2.get('batch_sn'), '222222')
            current_batch_sn = each2.get('batch_sn', '').strip()
            print(f"当前item批次号: {current_batch_sn} , line_id: {each2['line_id']}")
            # 将无批次号的行按属性分组
            if not current_batch_sn:
                print("66666666")
                attr_key = get_batch_attribute_key(each2)
                print(attr_key, 'attr_key')
                mat_code = each2['mat_code']
                if mat_code not in batch_group:
                    batch_group[mat_code] = {}
                if attr_key not in batch_group[mat_code]:
                    batch_group[mat_code][attr_key] = []
                batch_group[mat_code][attr_key].append((index2, each2))
            else:
                print("66666666")
                # 已经有批次号的item直接保留
                all_new_items.append(each2)
        # 如果基础校验失败，直接跳过批次分配
        if current_header_batch_failed:
            each['item'] = all_new_items
            error_list.append(f"guid {each['guid']} 基础数据校验失败，跳过批次分配")
            continue
        # 执行批次分配
        batch_allocation_failed = False  # 新增：标记批次分配是否失败
        print('11111111', batch_group.items())
        for mat_code, attr_groups in batch_group.items():
            for attr_key, items in attr_groups.items():
                print(f"处理物料 {mat_code}，属性组: {attr_key}")
                batches = query_batches_by_attributes(mat_code, items[0][1])
                print(batches, 'batches')
                if not batches:
                    error_list.append(
                        f"line_id: {each2['line_id']},物料{mat_code}未找到匹配批次，属性: {attr_key[:64]}....")
                    batch_allocation_failed = True  # 标记失败
                    for idx, item in items:
                        all_new_items.append(item)
                    continue

                # 获取可用批次（原始库存查询）
                raw_available_batches = get_available_batches(mat_code, batches, items[0][1]['stor_loc_code'])

                # 使用批次管理器过滤批次（考虑之前的分配）
                available_batches = BatchAllocationManager.filter_available_batches(
                    mat_code, batches, items[0][1]['stor_loc_code'], raw_available_batches
                )

                if not available_batches:
                    error_list.append(
                        f"line_id: {each2['line_id']}物料{mat_code}匹配批次无可用库存，属性: {attr_key[:64]}....")
                    batch_allocation_failed = True  # 标记失败
                    for idx, item in items:
                        all_new_items.append(item)
                    continue

                allocation_result = allocate_batches_to_items(items, available_batches)
                print(allocation_result, 'allocation_result')
                if isinstance(allocation_result, str):
                    error_list.append(allocation_result)
                    batch_allocation_failed = True  # 标记失败
                    for idx, item in items:
                        all_new_items.append(item)
                    continue
                print("------------------------------------")
                print("Allocation Result:", allocation_result[1])

                # 更新批次管理器状态
                if isinstance(allocation_result, tuple) and allocation_result[0]:
                    BatchAllocationManager.record_allocation(allocation_result)
                    # 更新批次状态
                    for alloc in allocation_result[1]:
                        for batch_alloc in alloc.get('all_allocations', []):
                            batch_sn = batch_alloc['batch_sn']
                            # 查找批次在available_batches中的剩余数量
                            remaining_qty = 0
                            for batch in available_batches:
                                if batch['batch_sn'] == batch_sn:
                                    remaining_qty = batch.get('available_qty', 0)
                                    break

                            # 更新全局状态
                            BatchAllocationManager.update_batch_state(
                                mat_code,
                                batch_sn,
                                items[0][1]['stor_loc_code'],
                                remaining_qty,
                                0
                            )
                            print(f"更新全局批次状态: {batch_sn} 剩余可用 {remaining_qty}")

                new_items = []

                # 构建原始 item 查找表（通过 line_id）
                original_item_lookup = {item['line_id']: item for _, item in items}

                # 遍历每个需要分配的行
                for alloc in allocation_result[1]:
                    line_id = alloc['line_id']
                    all_allocations = alloc.get('all_allocations', [])

                    if not all_allocations:
                        error_list.append(f"guid {each['guid']} line_id {line_id} 分配结果为空")
                        continue

                    # 获取原始模板
                    if line_id not in original_item_lookup:
                        error_list.append(f"guid {each['guid']} line_id {line_id} 在原始数据中不存在")
                        continue
                    template_item = original_item_lookup[line_id]
                    print(template_item, 'template_item')
                    # 为 all_allocations 中的每一个批次创建一行
                    print(all_allocations, 'all_allocations')
                    for batch_alloc in all_allocations:
                        new_item = copy.deepcopy(template_item)
                        new_item['batch_sn'] = batch_alloc['batch_sn']
                        mat_info = get_material_info(mat_code)
                        # 如果 transaction_qty 也要同步转换
                        if mat_info.get('mat_group', '').startswith('1'):
                            new_item['transaction_qty'] = batch_alloc['allocated_qty']
                            new_item['parallel_qty'] = batch_alloc['allocated_parallel_qty']
                        else:
                            new_item['parallel_qty'] = batch_alloc['allocated_qty']
                            new_item['transaction_qty'] = 0
                        all_new_items.append(new_item)
                        # 可选：标记子行
                        # new_item['sub_line_id'] = f"{line_id}-{len([i for i in new_items if i['line_id']==line_id])+1}"
                        # new_items.append(new_item)

                # ✅ 完全替换原 item 列表
                each['item'] = all_new_items
                print(each['item'], '111111')
                print("✅ 拆分完成，新 items 数量:", len(all_new_items))
                for i, item in enumerate(each['item']):
                    print(
                        f"  [{i + 1}] line_id={item['line_id']}, batch={item['batch_sn']}, qty={item['parallel_qty']}")
                print("------------------------------------")

        # 检查是否有错误，如果有错误则不创建预留单
        if error_list:
            type = 'E'
            message = f"存在错误,请检查:{','.join(error_list)}"
            return {
                "type": type,
                "message": message
            }

        if batch_allocation_failed:
            continue

        # 第二步：处理预留单创建
        reservation_requests = []
        print('==========1', each['item'])
        for index2, each2 in enumerate(each['item']):
            if each2['line_id'] == 0:
                continue

            # 预留检查 - 如果没有预留单号，需要创建预留单
            if each2.get('res_doc_sn', '') == '':
                # 获取物料信息
                mat_info = get_material_info(each2.get('mat_code', ''))
                if not mat_info:
                    error_list.append(f"未找到物料代码 {each2.get('mat_code', '')} 的信息")
                    continue

                basic_uom = mat_info.get("basic_uom")
                parallel_uom = mat_info.get("parallel_uom")
                mat_group = mat_info.get("mat_group")

                # 单位转换
                quantity_field = 'transaction_qty' if mat_group.startswith('1') else 'parallel_qty'
                quantity = each2.get(quantity_field, 0)
                # 当物料编码的物料组为1开头时，取交易数量（颗数）parallel_qty，非1开头时为0
                if mat_group.startswith('1'):
                    parallel_qty = each2.get('parallel_qty', 0)
                else:
                    parallel_qty = 0

                code, msg, rcv_batch_sn, test_proc_result = get_rcv_batch_sn(each2.get('mat_code', ''),
                                                                             each2.get('batch_sn', ''),
                                                                             each2.get('box_no', ''))
                if code != 200:
                    error_list.append(f"获取接收批次号失败：{msg}")
                    continue

                # 收集预留单请求
                reservation_requests.append({
                    'header_index': index,
                    'item_index': index2,
                    'guid': each['guid'],
                    'line_id': each2['line_id'],
                    'plant_code': each2.get('plant_code', ''),
                    'mat_code': each2.get('mat_code', ''),
                    'batch_sn': each2.get('batch_sn', ''),  # 使用已分配的批次号
                    'transaction_qty': quantity,
                    'basic_uom': basic_uom,
                    'parallel_uom': parallel_uom,
                    'stor_loc_code': each2.get('stor_loc_code', ''),
                    'rcv_plant_code': each2.get('plant_code', ''),
                    'rcv_stor_loc_code': each2.get('rcv_stor_loc_code', ''),
                    'rcv_batch_sn': rcv_batch_sn,
                    'rcv_mat_code': each2.get('mat_code', ''),
                    "basic_qty": quantity,
                    "parallel_qty": parallel_qty
                })

        # 批量创建预留单 - 如果有错误，不创建预留单
        print('==-', reservation_requests)
        if reservation_requests:
            if error_list:
                # 如果有错误，不创建预留单
                print("存在错误，跳过预留单创建")
                type = 'E'
                message = f"存在错误,请检查:{','.join(error_list)}"
                return {
                    "type": type,
                    "message": message
                }
            else:
                # 没有错误，创建预留单
                success = create_reservations(reservation_requests, data, user_id, db, error_list, created_reservations)
                if success:
                    has_created_reservation = True
                else:
                    # 如果创建预留单失败，标记已创建的预留单为删除
                    mark_reservations_as_deleted(created_reservations, db)
                    type = 'E'
                    message = f"预留单创建失败:{','.join(error_list)}"
                    return {
                        "type": type,
                        "message": message
                    }

        # 创建预留单后检查错误
        if error_list:
            # 创建预留单后出现错误，标记已创建的预留单为删除
            if has_created_reservation:
                mark_reservations_as_deleted(created_reservations, db)
            type = 'E'
            message = f"存在错误,请检查:{','.join(error_list)}"
            return {
                "type": type,
                "message": message
            }

        # 第三步：验证预留单相关数据
        for index2, each2 in enumerate(each['item']):
            if each2['line_id'] == 0:
                continue

            # 验证预留单相关字段
            reservation_errors = validate_reservation_fields(each, each2, index, index2, db)
            if reservation_errors:
                error_list.extend(reservation_errors)
                # 有错误时标记已创建的预留单为删除
                if has_created_reservation:
                    mark_reservations_as_deleted(created_reservations, db)
                type = 'E'
                message = f"存在错误,请检查:{','.join(error_list)}"
                return {
                    "type": type,
                    "message": message
                }

        # 第四步：数量汇总和库存检查
        res_doc_quantity_map = {}
        for index2, each2 in enumerate(each['item']):
            # 汇总同一调拨通知单号的数量
            if each2.get('res_doc_sn', '') and each2.get('res_doc_items', ''):
                res_doc_key = f"{each2['res_doc_sn']}_{each2['res_doc_items']}"
                if res_doc_key not in res_doc_quantity_map:
                    res_doc_quantity_map[res_doc_key] = {
                        'transaction_qty': 0,
                        'parallel_qty': 0,
                        'mat_code': each2['mat_code']
                    }
                res_doc_quantity_map[res_doc_key]['transaction_qty'] += each2.get('transaction_qty', 0)
                res_doc_quantity_map[res_doc_key]['parallel_qty'] += each2.get('parallel_qty', 0)

            # 批次库存检查
            if each2.get('batch_sn', '') != '':
                transaction_qty = each2.get('transaction_qty', 0)
                parallel_qty = each2.get('parallel_qty', 0)
                if transaction_qty > 0 or parallel_qty > 0:
                    available_qty_error = check_batch_available_quantity(
                        each2['mat_code'],
                        each2['batch_sn'],
                        each2['stor_loc_code'],
                        transaction_qty,
                        parallel_qty
                    )
                    if available_qty_error:
                        error_list.append(f"guid {each['guid']} 中line_id{each2['line_id']} {available_qty_error}")
                        # 有错误时标记已创建的预留单为删除
                        if has_created_reservation:
                            mark_reservations_as_deleted(created_reservations, db)
                        type = 'E'
                        message = f"存在错误,请检查:{','.join(error_list)}"
                        return {
                            "type": type,
                            "message": message
                        }

        # 调拨通知单号数量校验
        for res_doc_key, quantities in res_doc_quantity_map.items():
            res_doc_sn, res_doc_items = res_doc_key.split('_')
            quantity_error = check_res_doc_available_quantity(
                res_doc_sn,
                int(res_doc_items),
                quantities['transaction_qty'],
                quantities['parallel_qty'],
                quantities['mat_code']
            )
            if quantity_error:
                error_list.append(f"guid {each['guid']} 中发货通知单{res_doc_sn}行{res_doc_items} {quantity_error}")
                # 有错误时标记已创建的预留单为删除
                if has_created_reservation:
                    mark_reservations_as_deleted(created_reservations, db)
                type = 'E'
                message = f"存在错误,请检查:{','.join(error_list)}"
                return {
                    "type": type,
                    "message": message
                }

    # 最终处理 - 所有验证通过，保存数据
    if error_list:
        # 如果最终还有错误，标记已创建的预留单为删除
        if has_created_reservation:
            mark_reservations_as_deleted(created_reservations, db)
        type = 'E'
        message = f"存在错误,请检查:{','.join(error_list)}"
    else:
        # 所有验证通过，保存数据
        # 注意：这里需要获取rcv_batch_sn
        rcv_batch_sn = ""
        if created_reservations and data['header'] and data['header'][0]['item']:
            # 尝试获取rcv_batch_sn
            first_item = data['header'][0]['item'][0]
            code, msg, rcv_batch_sn, test_proc_result = get_rcv_batch_sn(
                first_item.get('mat_code', ''),
                first_item.get('batch_sn', ''),
                first_item.get('box_no', '')
            )
            if code != 200:
                # 获取rcv_batch_sn失败，标记已创建的预留单为删除
                if has_created_reservation:
                    mark_reservations_as_deleted(created_reservations, db)
                type = 'E'
                message = f"获取接收批次号失败：{msg}"
                return {
                    "type": type,
                    "message": message
                }

        type, message = save_data(payload, data, rcv_batch_sn, user_id, created_reservations)
        # 如果保存数据失败，标记已创建的预留单为删除
        if type == 'E' and has_created_reservation:
            mark_reservations_as_deleted(created_reservations, db)

    return {
        "type": type,
        "message": message
    }


def mark_reservations_as_deleted(created_reservations, db):
    """标记预留单为删除状态"""
    if not created_reservations:
        return

    print("标记已创建的预留单为删除状态")
    for reservation in created_reservations:
        res_doc_sn = reservation.get('res_doc_sn', '')
        res_doc_items = reservation.get('res_doc_items', '')
        if res_doc_sn and res_doc_items:
            deleted_mark_sql = f"""
                UPDATE t_res_item 
                SET 
                    deleted_mark = '1'
                WHERE 
                    res_doc_sn = '{res_doc_sn}'
                    and res_doc_items = '{res_doc_items}'
            """
            try:
                db.exec_sql(deleted_mark_sql)
                print(f"预留单 {res_doc_sn} 行 {res_doc_items} 已标记为删除")
            except Exception as e:
                print(f"标记预留单为删除状态失败: {e}")
    db.dbCommit()


def get_rcv_batch_sn(mat_code, batch_sn, box_no):
    test_proc_sql = f"""
        SELECT 
            production_date,
            maturity_date,
            vendor_code,
            vendor_batch,
            receive_date,
            lot_no,
            wafer_id,
            packing_seal_date,
            packing_id,
            batch_type,
            lot_type_description,
            cp_vendor,
            bin,
            grade1,
            grade2,
            grade3,
            extended_batch_date1,
            extended_batch_date2,
            extended_batch_date3,
            extended_batch_attributes1,
            extended_batch_attributes2,
            extended_batch_attributes3,
            uf_ZT04,
            uf_ZT05,
            uf_ZT20,
            uf_ZT21,
            uf_ZT35,
            uf_ZT06,
            uf_ZT48,
            uf_ZT49,
            uf_ZT07,
            uf_ZT08,
            uf_ZT53,
            uf_ZT14,
            uf_ZT15,
            uf_ZT54,
            uf_ZT18,
            uf_ZT55,
            uf_ZT56,
            uf_ZT25,
            uf_sap_batch,
            uf_ZT36,
            uf_ZT37,
            uf_ZT38,
            uf_ZT50,
            uf_ZT51,
            uf_ZT09,
            uf_ZT10,
            uf_ZT11,
            uf_ZT12,
            uf_ZT13,
            uf_ZT52,
            uf_ZT17,
            uf_ZT22,
            uf_ZT23,
            uf_ZT24,
            uf_ZT57,
            uf_ZT26,
            uf_ZT58,
            uf_ZT40,
            uf_ZT41,
            uf_ZT42,
            uf_ZT43,
            uf_ZT44,
            uf_ZT45,
            uf_ZT30,
            uf_ZT31,
            uf_ZT32,
            uf_ZT33,
            uf_ZT34,
            uf_runcard,
            uf_ZT59,
            uf_electroplating_date,
            uf_original_box_no,
            uf_quality_type,
            uf_ds_flag
        FROM t_batch_number
        WHERE mat_code = '{mat_code}' AND batch_sn = '{batch_sn}'
    """
    test_proc_result = db.query_sql(test_proc_sql)
    print(test_proc_result)
    for item in test_proc_result:
        item['mat_code'] = mat_code
        item['uf_box_no'] = box_no
        item['uf_ZT60'] = 'uf_ZT60'
    print(test_proc_result)
    code, msg, data_list = generate_batch_number(test_proc_result)
    print(code, msg, data_list)
    for item_data_list in data_list:
        rcv_batch_sn = item_data_list.get('batch_sn', '')
    return code, msg, rcv_batch_sn, test_proc_result


def validate_item_fields(header, item, header_index, item_index):
    """验证物料行基础字段"""
    errors = []

    # 移动类型检查
    if item.get('movement_type', '') == '':
        errors.append("guid {} 中line_id{} 移动类型必填".format(header['guid'], item['line_id']))
    elif not check_movement_type_exist(item['movement_type']):
        errors.append(
            "guid {} 中line_id{} 移动类型{}不存在".format(header['guid'], item['line_id'], item['movement_type']))

    # 工厂检查
    if item.get('plant_code', '') == '':
        errors.append("guid {} 中line_id{} 工厂必填".format(header['guid'], item['line_id']))
    elif not check_plant_code_exist(item['plant_code']):
        errors.append("guid {} 中line_id{} 工厂{}不存在".format(header['guid'], item['line_id'], item['plant_code']))
    else:
        # 库存地点检查
        # if item.get('stor_loc_code', '') == '':
        #     errors.append("guid {} 中line_id{}  库存地点必填".format(header['guid'], item['line_id']))
        if item.get('stor_loc_code', '') != '':
            if not check_stor_loc_code_exist(item['plant_code'], item['stor_loc_code']):
                errors.append("guid {} 中line_id{} 工厂{}下库存地点{}不存在".format(
                    header['guid'], item['line_id'], item['plant_code'], item['stor_loc_code']))
        # 接收库存地点检查
        # if item.get('rcv_stor_loc_code', '') == '':
        #     errors.append("guid {} 中line_id{}  接收库存地点必填".format(header['guid'], item['line_id']))
        if item.get('rcv_stor_loc_code', '') != '':
            if not check_stor_loc_code_exist(item['plant_code'], item['rcv_stor_loc_code']):
                errors.append("guid {} 中line_id{} 工厂{}下接收库存地点{}不存在".format(
                    header['guid'], item['line_id'], item['plant_code'], item['rcv_stor_loc_code']))

        # 物料检查
        if item.get('mat_code', '') == '':
            errors.append("guid {} 中line_id{} 物料编码必填".format(header['guid'], item['line_id']))
        elif not check_mat_code_exist(item['mat_code'], item['plant_code']):
            errors.append("guid {} 中line_id{} 物料{}对应工厂{}不存在".format(
                header['guid'], item['line_id'], item['mat_code'], item['plant_code']))

    # 库存状态检查
    if item.get('inventory_status', '') == '':
        errors.append("guid {} 中line_id{} 库存状态必填".format(header['guid'], item['line_id']))
    elif not check_inventory_status_exist(item['inventory_status']):
        errors.append(
            "guid {} 中line_id{} 库存状态{}不存在".format(header['guid'], item['line_id'], item['inventory_status']))

    # 数量检查
    if item.get('transaction_qty', 0) < 0:
        errors.append("guid {} 中line_id{} 交易数量必须大于0".format(header['guid'], item['line_id']))
    if item.get('parallel_qty', 0) < 0:
        errors.append("guid {} 中line_id{} 平行数量必须大于0".format(header['guid'], item['line_id']))

    # chipone Lot检查
    if item.get('lot_no', '') == '':
        errors.append("guid {} 中line_id{} chipone Lot必填".format(header['guid'], item['line_id']))

    # 生产周检查
    # if item.get('uf_ZT18', '') == '':
    #     errors.append("guid {} 中line_id{} 生产周必填".format(header['guid'], item['line_id']))
    # bin
    # if item.get('uf_ZT07', '') == '':
    #     errors.append("guid {} 中line_id{} bin必填".format(header['guid'], item['line_id']))
    # 箱号检查
    if item.get('box_no', '') == '':
        errors.append("guid {} 中line_id{} 箱号必填".format(header['guid'], item['line_id']))
    # 测试程序检查
    # if item.get('test_program', '') == '':
    #     errors.append("guid {} 中line_id{} 测试程序必填".format(header['guid'], item['line_id']))
    #   uf_ZT53-BUMP厂、uf_ZT14-封装厂、uf_ZT15-测试厂(CP)、uf_ZT54-测试厂(FT)4个字段至少有一个字段传非空值
    # if item.get('uf_ZT53', '') == '' and item.get('uf_ZT14', '') == '' and item.get('uf_ZT15', '') == '' and item.get(
    #         'uf_ZT54', '') == '':
    #     errors.append(
    #         "guid {} 中line_id{} 至少有一个字段uf_ZT53-BUMP厂、uf_ZT14-封装厂、uf_ZT15-测试厂(CP)、uf_ZT54-测试厂(FT)4个字段传非空值".format(
    #             header['guid'], item['line_id']))
    # uf_ZT59-FT订单号、uf_ZT60-PK订单号、uf_ZT25-封装订单号、uf_ZT55-CP订单号、uf_ZT56-BUMP订单号5个字段至少有一个字段传非空值
    # if item.get('uf_ZT59', '') == '' and item.get('uf_ZT60', '') == '' and item.get('uf_ZT25', '') == '' and item.get(
    #         'uf_ZT55', '') == '' and item.get('uf_ZT56', '') == '':
    #     errors.append(
    #         "guid {} 中line_id{} 至少有一个字段uf_ZT59-FT订单号、uf_ZT60-PK订单号、uf_ZT25-封装订单号、uf_ZT55-CP订单号、uf_ZT56-BUMP订单号5个字段传非空值".format(
    #             header['guid'], item['line_id']))

    return errors


def validate_cost_center_and_wbs(header, item, header_index, item_index):
    """验证成本中心和WBS元素"""
    errors = []

    if item.get('cost_center') == '' or item.get('wbs_elements') == '':
        errors.append(
            "guid {} 中line_id{} 调拨通知单号为空时成本中心和WBS元素需要填写".format(header['guid'], item['line_id']))
        return errors

    if not check_cost_center_exist(header['company_code'], item['cost_center']):
        errors.append(
            "guid {} 中line_id{} 成本中心{}不存在".format(header['guid'], item['line_id'], item['cost_center']))

    if not check_wbs_elements_exist(header['company_code'], item['wbs_elements']):
        errors.append(
            "guid {} 中line_id{} WBS元素{}不存在".format(header['guid'], item['line_id'], item['wbs_elements']))

    return errors


def get_material_info(mat_code):
    """获取物料信息"""
    db = DbHelper()
    mat_info_sql = f"""
        SELECT basic_uom, parallel_uom, mat_group 
        FROM t_mmd_material_basic_data 
        WHERE mat_code = '{mat_code}'
    """
    mat_info_result = db.query_sql(mat_info_sql)
    return mat_info_result[0] if mat_info_result else None


def create_reservations(reservation_requests, data, user_id, db, error_list, created_reservations):
    """批量创建预留单"""
    reservation_items = []
    item_counter = 10

    for req in reservation_requests:
        reservation_items.append({
            "movement_type": "T001",
            "res_doc_items": str(item_counter),
            "plant_code": req['plant_code'],
            "mat_code": req['mat_code'],
            "batch_sn": req['batch_sn'],  # 使用已分配的批次号
            "rcv_plant_code": req['rcv_plant_code'],
            "rcv_mat_code": req['rcv_mat_code'],
            "rcv_batch_sn": req['rcv_batch_sn'],
            "rcv_stor_loc_code": req['rcv_stor_loc_code'],
            "transaction_qty": req['transaction_qty'],
            "transaction_uom": req['basic_uom'],
            "basic_qty": req['basic_qty'],
            "basic_uom": req['basic_uom'],
            "parallel_qty": req['parallel_qty'],
            "parallel_uom": req['parallel_uom'],
            "stor_loc_code": req['stor_loc_code'],
            "issuing_enabled_flag": "1",
            "project_sn": "",
            "batch_occupy_flag": "1",
            "reference2_item": "",
            "reference3_item": ""
        })
        item_counter += 10

    reservation_data = [{
        "movement_type": "T001",
        "demand_date": datetime.datetime.now().strftime('%Y-%m-%d'),
        "plant_code": reservation_requests[0]['plant_code'],
        "item": reservation_items,
        "_tag_": "insert"
    }]

    result = reservationSave(reservation_data, user_id, db=db)

    if result.get('code') != 200:
        error_list.append(result.get('msg').replace('\n', ''))
        return False
    else:
        # 获取预留单号并更新物料行
        res_doc_sn_ls = result.get('data', [])
        current_req_index = 0

        for res_doc_sn in res_doc_sn_ls:
            res_doc_sn_sql = f"""
            SELECT res_doc_sn, res_doc_items
                FROM t_res_item
                WHERE res_doc_sn = '{res_doc_sn}'
            """
            res_doc_sn_data = db.query_sql(res_doc_sn_sql)

            for res_item in res_doc_sn_data:
                if current_req_index < len(reservation_requests):
                    req = reservation_requests[current_req_index]
                    data['header'][req['header_index']]['item'][req['item_index']]['res_doc_sn'] = res_doc_sn
                    data['header'][req['header_index']]['item'][req['item_index']]['res_doc_items'] = res_item[
                        'res_doc_items']

                    # 记录已创建的预留单
                    created_reservations.append({
                        'res_doc_sn': res_doc_sn,
                        'res_doc_items': res_item['res_doc_items']
                    })

                    current_req_index += 1

        return True


def validate_reservation_fields(header, item, header_index, item_index, db):
    """验证预留单相关字段"""
    errors = []

    # 对于已有预留单号的项，检查成本中心和WBS元素
    if item.get('res_doc_sn', '') != '':
        if item.get('cost_center') and not check_cost_center_exist(header['company_code'], item['cost_center']):
            errors.append(
                "guid {} 中line_id{} 成本中心{}不存在".format(header['guid'], item['line_id'], item['cost_center']))
        if item.get('wbs_elements') and not check_wbs_elements_exist(header['company_code'], item['wbs_elements']):
            errors.append(
                "guid {} 中line_id{} WBS元素{}不存在".format(header['guid'], item['line_id'], item['wbs_elements']))

    # 校验工厂数据一致性
    if item.get('res_doc_sn', '') and item.get('res_doc_items', ''):
        plant_code = item.get('plant_code', '')
        sql = """
            SELECT plant_code FROM t_res_header 
            WHERE res_doc_sn = '{}' LIMIT 1
        """.format(item['res_doc_sn'])
        plant_code_data = db.query_sql(sql)
        if plant_code_data and plant_code_data[0]['plant_code'] != plant_code:
            errors.append("guid {} 中line_id{} 传入工厂{}与发货通知单的工厂{}不同，请检查".format(
                header['guid'], item['line_id'], plant_code, plant_code_data[0]['plant_code']))

    # 发货通知单存在性检查
    if item.get('res_doc_sn', '') != '' and item.get('res_doc_items', 0) != 0:
        db.dbCommit()
        if not check_res_doc_exist(item['res_doc_sn'], item['res_doc_items']):
            errors.append("guid {} 中line_id{} 调拨通知单号{} {}行不存在".format(
                header['guid'], item['line_id'], item['res_doc_sn'], item['res_doc_items']))

    return errors


# 原有的辅助函数保持不变
def get_batch_attribute_key(item):
    """生成批次属性的唯一标识键"""
    attributes = [
        'lot_no', 'uf_ZT04', 'wafer_id', 'uf_ZT18', 'runcard', 'uf_ZT07',
        'production_date', 'uf_ZT53', 'uf_ZT14', 'uf_ZT15',
        'uf_ZT54', 'uf_ZT08', 'uf_ZT09', 'uf_ZT59', 'uf_ZT60', 'uf_ZT25', 'uf_ZT55', 'uf_ZT56'
    ]
    key_parts = []
    for attr in attributes:
        value = item.get(attr) or ''
        key_parts.append(f"{attr}:{value}")
    return "|".join(key_parts)


# def query_batches_by_attributes(mat_code, item):
#     """根据属性查询批次号"""
#     db = DbHelper()
#     attr_mapping = {
#         'lot_no': 'lot_no',
#         'uf_ZT04': 'uf_ZT04',
#         'wafer_id': 'wafer_id',
#         'uf_ZT18': 'uf_ZT18',
#         'runcard': 'uf_runcard',
#         'uf_ZT07': 'uf_ZT07',
#         'production_date': 'production_date',
#         'uf_ZT53': 'uf_ZT53',
#         'uf_ZT14': 'uf_ZT14',
#         'uf_ZT15': 'uf_ZT15',
#         'uf_ZT54': 'uf_ZT54',
#         'uf_ZT08': 'uf_ZT08',
#         'uf_ZT09': 'uf_ZT09',
#         'uf_ZT59': 'uf_ZT59',
#         'uf_ZT60': 'uf_ZT60',
#         'uf_ZT25': 'uf_ZT25',
#         'uf_ZT55': 'uf_ZT55',
#         'uf_ZT56': 'uf_ZT56'
#     }

#     # 构建查询条件 - 只查询非空的属性
#     where_clauses = [f"b.mat_code = '{mat_code}'"]
#     for item_attr, db_attr in attr_mapping.items():
#         value = item.get(item_attr)
#         if value is not None and value != '':
#             where_clauses.append(f"b.{db_attr} = '{value}'")

#     sql = f"""
#         SELECT DISTINCT b.batch_sn
#         FROM t_batch_number b
#         LEFT JOIN t_batch_additional_property p ON b.batch_sn = p.batch_sn AND b.mat_code = p.mat_code
#         WHERE {' AND '.join(where_clauses)}
#     """
#     print(f"查询批次SQL: {sql}")
#     data = db.query_sql(sql)
#     batch_sns = [row['batch_sn'] for row in data] if data else []
#     print(f"查询到的批次号: {batch_sns}")
#     return batch_sns

def query_batches_by_attributes(mat_code, item):
    """根据属性查询批次号"""
    db = DbHelper()
    attr_mapping = {
        'lot_no': 'lot_no'
    }

    def build_where_clauses(item_dict):
        """构建查询条件 - 只查询非空的属性"""
        where_clauses = [f"b.mat_code = '{mat_code}'"]
        for item_attr, db_attr in attr_mapping.items():
            value = item_dict.get(item_attr)
            if value is not None and value != '':
                where_clauses.append(f"b.{db_attr} = '{value}'")
        return where_clauses

    def execute_query(where_clauses):
        """执行查询并返回批次号列表"""
        sql = f"""
            SELECT DISTINCT b.batch_sn 
            FROM t_batch_number b
            LEFT JOIN t_batch_additional_property p ON b.batch_sn = p.batch_sn AND b.mat_code = p.mat_code
            WHERE {' AND '.join(where_clauses)}
        """
        print(f"查询批次SQL: {sql}")
        data = db.query_sql(sql)
        batch_sns = [row['batch_sn'] for row in data] if data else []
        print(f"查询到的批次号: {batch_sns}")
        return batch_sns

    # 第一次查询
    where_clauses = build_where_clauses(item)
    batch_sns = execute_query(where_clauses)

    # 如果第一次查询没有找到批次，进行第二次查询
    if not batch_sns:
        print("第一次查询未找到批次，开始第二次查询...")

        # 查询备用属性值
        backup_sql = "SELECT uf_field_code, uf_field_value FROM ut_initial_attribute_field"
        backup_data = db.query_sql(backup_sql)

        if backup_data:
            # 构建备用属性字典（按数据库字段名存储）
            backup_values = {}
            for row in backup_data:
                field_code = row['uf_field_code']
                field_value = row['uf_field_value']
                # if field_value:  # 只收集有值的字段  //wdl 空配置设置有效
                backup_values[field_code] = field_value

            print(f"获取到的备用属性值: {backup_values}")

            # 创建新的查询项，完全使用备用值覆盖批次属性
            new_item = item.copy()

            # 覆盖批次相关的属性
            for item_attr, db_attr in attr_mapping.items():
                # 条件：1.备用表里有这个字段的值 2.原始item里这个属性本身有有效值
                if db_attr in backup_values and item.get(item_attr) not in [None, '']:
                    new_item[item_attr] = backup_values[db_attr]

            print(f"第二次查询使用的属性: {new_item}")

            # 执行第二次查询
            where_clauses = build_where_clauses(new_item)
            batch_sns = execute_query(where_clauses)

    return batch_sns


def get_available_batches(mat_code, batch_sns, stor_loc_code):
    """获取非占用的批次库存"""
    db = DbHelper()
    if not batch_sns:
        return []

    # 获取物料信息
    mat_info_sql = f"""
        SELECT mat_group 
        FROM t_mmd_material_basic_data 
        WHERE mat_code = '{mat_code}'
    """
    mat_info_result = db.query_sql(mat_info_sql)
    mat_group = mat_info_result[0].get('mat_group') if mat_info_result else ''

    # 构建批次库存查询数据
    mat_code_result = {"data": {"mat_code": [mat_code], "batch_sn": batch_sns, "stor_loc_code": [stor_loc_code]}}
    result_data, detail = get_batch_inventory_Occupation(mat_code_result.get("data", ""))
    print(result_data, 'result_data')

    # 修复SQL语句：正确处理列表类型的batch_sns
    if isinstance(batch_sns, list):
        batch_sns_str = "','".join(batch_sns)
    else:
        batch_sns_str = str(batch_sns)

    sql = f"""
        SELECT 
            res_doc_sn,
            batch_sn, 
            mat_code,
            (basic_qty - issued_qty_base_uom) as allocated_qty, 
            (parallel_qty - issued_qty_parallel_uom) as allocated_parallel_qty 
        FROM t_res_item 
        WHERE mat_code = '{mat_code}' 
            AND batch_sn IN ('{batch_sns_str}')
            AND batch_occupy_flag = 1 
            AND close_flag = 0
            AND deleted_mark = 0
    """

    print(sql, 'sql')

    try:
        batch_occupy_flag_data = db.query_sql(sql)
        print(f"查询结果: {batch_occupy_flag_data}")
    except Exception as e:
        print(f"SQL查询错误: {e}")
        batch_occupy_flag_data = []

    batch_occupy_flag_dict = {
        item['batch_sn']: {
            'allocated_qty': item['allocated_qty'],
            'allocated_parallel_qty': item['allocated_parallel_qty']
        }
        for item in batch_occupy_flag_data
    }

    # 修复：检查result_data而不是未定义的result
    if not result_data or len(result_data) == 0:
        return []

    inventory_list = result_data  # 使用result_data而不是result
    available_batches = []

    # 按批次号汇总可用库存
    batch_inventory_map = {}
    for inv in inventory_list:
        if inv.get('mat_code') == mat_code and inv.get('batch_sn') in batch_sns:
            batch_sn = inv.get('batch_sn')

            # 从库存数据中获取分配数量（如果是负数则设为0）
            inv_allocated_qty = max(inv.get('allocated_qty', 0), 0)
            inv_allocated_parallel_qty = max(inv.get('allocated_parallel_qty', 0), 0)

            # 计算预留单总分配数量
            total_res_allocated_qty = 0
            total_res_allocated_parallel_qty = 0

            # 修复：检查batch_occupy_flag_dict中是否有该批次
            if batch_sn in batch_occupy_flag_dict:
                batch_occupy_data = batch_occupy_flag_dict[batch_sn]
                total_res_allocated_qty = batch_occupy_data.get('allocated_qty', 0)
                total_res_allocated_parallel_qty = batch_occupy_data.get('allocated_parallel_qty', 0)

            # 计算最终的分配数量（库存分配数量 - 预留单分配数量）
            final_allocated_qty = abs(round(float(total_res_allocated_qty), 2) - round(float(inv_allocated_qty), 2))
            final_allocated_parallel_qty = abs(
                round(float(total_res_allocated_parallel_qty), 2) - round(float(inv_allocated_parallel_qty), 2))
            print(final_allocated_qty, final_allocated_parallel_qty, 'final_allocated_qty,final_allocated_parallel_qty')
            # 确保最终分配数量不为负数
            final_allocated_qty = max(final_allocated_qty, 0)
            final_allocated_parallel_qty = max(final_allocated_parallel_qty, 0)

            # 根据物料组选择可用数量字段
            if mat_group and mat_group.startswith('1'):
                # 物料组以1开头：使用基本数量相关的可用字段
                print(final_allocated_qty, final_allocated_parallel_qty, '-------')
                print(inv.get('available_qty', 0), inv.get('available_parallel_qty', 0), '12312312')
                available_qty = abs(
                    round(float(final_allocated_qty), 2) - round(float(max(inv.get('available_qty', 0), 0)), 2))
                available_parallel_qty = abs(round(float(final_allocated_parallel_qty), 2) - round(
                    float(max(inv.get('available_parallel_qty', 0), 0)), 2))
                print(f"1开头的物料组{available_qty}, {available_parallel_qty}")
            else:
                # 其他物料组：使用平行数量相关的可用字段
                available_qty = abs(
                    round(float(final_allocated_qty), 2) - round(float(max(inv.get('available_qty', 0), 0)), 2))
                available_parallel_qty = 0

            # 如果可用数量为负数，则默认为0
            available_qty = max(available_qty, 0)
            available_parallel_qty = max(available_parallel_qty, 0)

            print(f"批次 {batch_sn}: mat_group={mat_group}, "
                  f"库存分配: {inv_allocated_qty}/{inv_allocated_parallel_qty}, "
                  f"预留分配: {total_res_allocated_qty}/{total_res_allocated_parallel_qty}, "
                  f"最终分配: {final_allocated_qty}/{final_allocated_parallel_qty}, "
                  f"可用数量: {available_qty}/{available_parallel_qty}")

            if batch_sn not in batch_inventory_map:
                batch_inventory_map[batch_sn] = {
                    "available_qty": available_qty,
                    "available_parallel_qty": available_parallel_qty
                }
            else:
                batch_inventory_map[batch_sn]["available_qty"] += available_qty
                batch_inventory_map[batch_sn]["available_parallel_qty"] += available_parallel_qty

    # 构建可用批次列表
    for batch_sn, batch_data in batch_inventory_map.items():
        available_qty = batch_data["available_qty"]
        available_parallel_qty = batch_data["available_parallel_qty"]
        print(f"批次1 {batch_sn} 最终可用: {available_qty}, {available_parallel_qty}")
        # 再次确保汇总后的数量不为负数
        available_qty = max(available_qty, 0)
        available_parallel_qty = max(available_parallel_qty, 0)

        print(f"批次2 {batch_sn} 最终可用: {available_qty}, {available_parallel_qty}")

        if available_qty > 0 or available_parallel_qty > 0:
            # 为每个批次创建可用批次对象
            available_batch = {
                'batch_sn': batch_sn,
                'available_qty': available_qty,
                'remaining_qty': available_parallel_qty
            }
            available_batches.append(available_batch)

    # 按批次号升序排列
    available_batches.sort(key=lambda x: x['batch_sn'])
    print(f"可用批次库存: {available_batches}")
    return available_batches


def allocate_batches_to_items(items, available_batches):
    """将批次按数量智能分配给物料行，优先匹配预留单批次"""
    db = DbHelper()

    # 计算总需求 - 根据物料组使用不同的数量字段
    total_demand = 0
    total_parallel_demand = 0

    for idx, item in items:
        mat_info = get_material_info(item['mat_code'])
        if mat_info and mat_info.get('mat_group', '').startswith('1'):
            # 物料组以1开头：使用transaction_qty进行分配计算
            total_demand += item.get('transaction_qty', 0)
            total_parallel_demand += item.get('parallel_qty', 0)
        else:
            # 其他物料组：使用parallel_qty进行分配计算
            total_demand += item.get('parallel_qty', 0)
            total_parallel_demand += item.get('parallel_qty', 0)

    # 计算总可用库存
    total_available = 0
    total_parallel_available = 0

    for batch in available_batches:
        mat_info = get_material_info(items[0][1]['mat_code']) if items else None
        if mat_info and mat_info.get('mat_group', '').startswith('1'):
            # 物料组以1开头：对比基本数量和平行数量
            total_available += batch['available_qty']
            total_parallel_available += batch['remaining_qty']
        else:
            # 其他物料组：只对比基本数量
            total_available += batch['available_qty']

    print(f"分配批次 - 总需求: {total_demand}, 总可用: {total_available}")
    print(f"平行需求: {total_parallel_demand}, 平行可用: {total_parallel_available}")

    # 根据物料组进行库存检查
    mat_info = get_material_info(items[0][1]['mat_code']) if items else None
    if mat_info and mat_info.get('mat_group', '').startswith('1'):
        # 物料组以1开头：需要同时检查基本数量和平行数量
        if total_demand > total_available:
            return f"总需求{total_demand}超过总可用库存{total_available}"
        if total_parallel_demand > total_parallel_available:
            return f"总平行需求{total_parallel_demand}超过总平行可用库存{total_parallel_available}"
    else:
        # 其他物料组：只检查基本数量
        if total_demand > total_available:
            return f"总需求{total_demand}超过总可用库存{total_available}"

    # 深拷贝可用批次，避免修改原数据
    batches_to_allocate = [batch.copy() for batch in available_batches]

    # 按批次号排序（确保分配顺序一致）
    batches_to_allocate.sort(key=lambda x: x['batch_sn'])

    print(f"批次排序（按批次号）:")
    for batch in batches_to_allocate:
        print(
            f"  批次 {batch['batch_sn']}: 可用数量 {batch['available_qty']}, 平行数量 {batch.get('remaining_qty', 0)}")

    # 分配批次给每个物料行
    allocation_results = []  # 记录分配结果

    for idx, item_tuple in items:
        item = item_tuple  # 原始数据项
        # 根据物料组判断使用哪个数量字段进行分配
        mat_info = get_material_info(item['mat_code'])
        if mat_info and mat_info.get('mat_group', '').startswith('1'):
            # 物料组以1开头：需要同时分配基本数量和平行数量
            remaining_demand = item.get('transaction_qty', 0)
            remaining_parallel_demand = item.get('parallel_qty', 0)
            allocation_quantity_field = 'transaction_qty'
            original_transaction_qty = item.get('transaction_qty', 0)
            original_parallel_qty = item.get('parallel_qty', 0)
        else:
            # 其他物料组：使用parallel_qty进行分配
            remaining_demand = item.get('parallel_qty', 0)
            remaining_parallel_demand = 0  # 非1开头物料组不检查平行数量
            allocation_quantity_field = 'parallel_qty'
            original_transaction_qty = item.get('transaction_qty', 0)
            original_parallel_qty = item.get('parallel_qty', 0)

        if remaining_demand <= 0:
            continue

        print(
            f"开始分配行 {item['line_id']}, 需求数量: {remaining_demand}, 平行需求: {remaining_parallel_demand}, 分配数量字段: {allocation_quantity_field}")
        print(f"  原始数量 - transaction_qty: {original_transaction_qty}, parallel_qty: {original_parallel_qty}")

        temp_allocations = []  # 临时记录分配情况

        # 按批次顺序分配，充分利用每个批次的剩余数量
        for batch in batches_to_allocate:
            if remaining_demand <= 0:
                break

            if batch['available_qty'] > 0:
                # 计算这个批次能分配的数量
                allocate_qty = min(batch['available_qty'], remaining_demand)

                if mat_info and mat_info.get('mat_group', '').startswith('1'):
                    # 物料组1开头：需要同时分配基本数量和平行数量
                    # 计算平行数量的分配比例
                    ratio = allocate_qty / remaining_demand if remaining_demand > 0 else 0
                    allocate_parallel_qty = min(batch['remaining_qty'], remaining_parallel_demand * ratio)

                    temp_allocations.append({
                        'batch_sn': batch['batch_sn'],
                        'allocated_qty': allocate_qty,
                        'allocated_parallel_qty': allocate_parallel_qty
                    })
                    batch['available_qty'] -= allocate_qty
                    batch['remaining_qty'] -= allocate_parallel_qty
                    remaining_demand -= allocate_qty
                    remaining_parallel_demand -= allocate_parallel_qty
                else:
                    # 其他物料组：只分配基本数量
                    temp_allocations.append({
                        'batch_sn': batch['batch_sn'],
                        'allocated_qty': allocate_qty,
                        'allocated_parallel_qty': 0
                    })
                    batch['available_qty'] -= allocate_qty
                    remaining_demand -= allocate_qty

                print(
                    f"  使用批次 {batch['batch_sn']}, 分配数量: {allocate_qty}, 平行数量: {allocate_parallel_qty if mat_info and mat_info.get('mat_group', '').startswith('1') else 0}, 剩余需求: {remaining_demand}")

        # 检查是否完全分配
        if remaining_demand > 0:
            return f"line_id {item['line_id']} 分配失败，仍需{remaining_demand}数量"

        # 应用分配结果到实际物料行
        if temp_allocations:
            # 关键：更新原始数据中的批次号，但保持所有数量字段不变
            main_allocation = max(temp_allocations, key=lambda x: x['allocated_qty'])

            # 更新原始数据 - 只更新批次号，保持所有数量不变
            item['batch_sn'] = main_allocation['batch_sn']
            # 重要：不修改任何数量字段，保持原始值

            # 记录分配结果
            allocation_results.append({
                'line_id': item['line_id'],
                'batch_sn': main_allocation['batch_sn'],
                'allocated_qty': main_allocation['allocated_qty'],
                'allocated_parallel_qty': main_allocation.get('allocated_parallel_qty', 0),
                'original_transaction_qty': original_transaction_qty,
                'original_parallel_qty': original_parallel_qty,
                'allocation_quantity_field': allocation_quantity_field,
                'all_allocations': temp_allocations
            })

            print(f"  最终分配: 批次 {main_allocation['batch_sn']} 给行 {item['line_id']}")
            print(f"    分配数量: {main_allocation['allocated_qty']} (基于 {allocation_quantity_field})")
            if mat_info and mat_info.get('mat_group', '').startswith('1'):
                print(f"    分配平行数量: {main_allocation.get('allocated_parallel_qty', 0)}")
            print(f"    保持数量 - transaction_qty: {original_transaction_qty}, parallel_qty: {original_parallel_qty}")

            # 记录其他批次的分配信息
            if len(temp_allocations) > 1:
                other_allocations = [alloc for alloc in temp_allocations if
                                     alloc['batch_sn'] != main_allocation['batch_sn']]
                for other in other_allocations:
                    print(
                        f"  辅助分配: 批次 {other['batch_sn']}, 数量: {other['allocated_qty']}, 平行数量: {other.get('allocated_parallel_qty', 0)}")

    # 更新批次剩余数量到原始available_batches
    for allocated_batch in batches_to_allocate:
        for original_batch in available_batches:
            if original_batch['batch_sn'] == allocated_batch['batch_sn']:
                original_batch['available_qty'] = allocated_batch['available_qty']
                original_batch['remaining_qty'] = allocated_batch['remaining_qty']
                break

    print(
        f"批次分配完成，剩余批次库存: {[(b['batch_sn'], b['available_qty'], b['remaining_qty']) for b in available_batches]}")
    print(f"分配结果: {allocation_results}")

    return True, allocation_results


# 以下为原有函数，保持不变
def check_company_code_exist(company_code):
    db = DbHelper()
    query_sql = """
        SELECT id FROM t_os_company WHERE company_code = '{}' LIMIT 1
    """.format(company_code)
    data = db.query_sql(query_sql)
    return bool(data)


def check_res_doc_exist(res_doc_sn, res_doc_items):
    db = DbHelper()
    db.dbCommit()
    query_sql = """
        SELECT id FROM t_res_item 
        WHERE res_doc_sn = '{}' AND res_doc_items = {} LIMIT 1
    """.format(res_doc_sn, res_doc_items)
    print(query_sql, 'query_sql')
    data = db.query_sql(query_sql)
    return bool(data)


def check_movement_type_exist(movement_type):
    db = DbHelper()
    query_sql = """
        SELECT id FROM t_movement_type WHERE movement_type = '{}' LIMIT 1
    """.format(movement_type)
    data = db.query_sql(query_sql)
    return bool(data)


def check_plant_code_exist(plant_code):
    db = DbHelper()
    query_sql = """
        SELECT id FROM t_os_plant WHERE plant_code = '{}' LIMIT 1
    """.format(plant_code)
    data = db.query_sql(query_sql)
    return bool(data)


def check_stor_loc_code_exist(plant_code, stor_loc_code):
    db = DbHelper()
    query_sql = """
        SELECT id FROM t_os_plant_storage_location_alloc 
        WHERE plant_code = '{}' AND stor_loc_code = '{}' LIMIT 1
    """.format(plant_code, stor_loc_code)
    data = db.query_sql(query_sql)
    return bool(data)


def check_inventory_status_exist(inventory_status):
    return inventory_status in ['0', '1', '2']


def check_mat_code_exist(mat_code, plant_code):
    db = DbHelper()
    query_sql = """
        SELECT b.id FROM t_mmd_material_basic_data as b
        JOIN t_mmd_material_plant_data as p ON b.mat_code = p.mat_code
        WHERE b.mat_code = '{}' AND b.deleted_mark = 0 AND b.lock_flag = 0
        AND p.plant_code = '{}' AND p.deleted_mark = 0 AND p.lock_flag = 0
        LIMIT 1
    """.format(mat_code, plant_code)
    data = db.query_sql(query_sql)
    return bool(data)


def check_batch_sn_exist(mat_code, batch_sn):
    db = DbHelper()
    query_sql = """
        SELECT id FROM t_batch_number 
        WHERE mat_code = '{}' AND batch_sn = '{}' LIMIT 1
    """.format(mat_code, batch_sn)
    data = db.query_sql(query_sql)
    return bool(data)


def check_cost_center_exist(company_code, cost_center):
    db = DbHelper()
    query_sql = """
        SELECT id FROM t_coc_cost_center 
        WHERE company_code = '{}' AND cost_center = '{}' LIMIT 1
    """.format(company_code, cost_center)
    data = db.query_sql(query_sql)
    return bool(data)


def check_wbs_elements_exist(company_code, wbs_elements):
    db = DbHelper()
    query_sql = """
        SELECT id FROM t_co_wbs_element 
        WHERE company_code = '{}' AND wbs_elements = '{}'
    """.format(company_code, wbs_elements)
    data = db.query_sql(query_sql)
    return bool(data)


def save_data(payload, data, rcv_batch_sn, user_id, created_reservations):
    db = DbHelper()
    type = ''
    message = ''
    now = datetime.datetime.now()
    insert_header_sql = ""
    insert_item_sql = ""
    print(data, "data")

    header_values = []
    item_values = []

    for each in data['header']:
        # 构建 header 值列表
        header_values.append("""
            ('{}','{}','{}','{}','{}','{}',{},{})
        """.format(each['guid'], each['bs_category'], each['vendor_short_name'],
                   each['posting_date'], each['posting_time'], each['company_code'],
                   user_id, user_id).strip())

        for each2 in each['item']:
            # 处理 production_date：有值就加引号，无则 NULL
            prod_date = each2.get('production_date')
            if prod_date:
                formatted_prod_date = f"'{prod_date}'"  # 输出: '2023-01-01'
            else:
                formatted_prod_date = 'NULL'
            each2['res_doc_items'] = each2['res_doc_items'] if each2.get('res_doc_items', '') else 0
            item_values.append(f"""
              ('{each["guid"]}',{each2["line_id"]},'{each2.get("group_id", 0)}','{each2["res_doc_sn"]}',
              {each2["res_doc_items"]},'{each2["movement_type"]}','{each2["plant_code"]}',
              '{each2["stor_loc_code"]}','{each2["inventory_status"]}','{each2["mat_code"]}',
              '{each2["batch_sn"]}',{each2["transaction_qty"]},{each2["parallel_qty"]},'{each2["rcv_stor_loc_code"]}','{rcv_batch_sn}','{each2["express_delivery"]}',
              '{each2["lot_no"]}','{each2["uf_ZT04"]}','{each2["wafer_id"]}','{each2["uf_ZT18"]}',
              '{each2["runcard"]}','{each2["uf_ZT07"]}','{each2["box_no"]}',{formatted_prod_date},
              '{each2["uf_ZT53"]}','{each2["uf_ZT14"]}','{each2["uf_ZT15"]}','{each2["uf_ZT54"]}',
              '{each2["uf_ZT08"]}','{each2["uf_ZT09"]}', '{each2.get("test_program", "")}',
              '{each2.get("uf_ZT59", "")}', '{each2.get("uf_ZT60", "")}',
              '{each2.get("uf_ZT25", "")}', '{each2.get("uf_ZT55", "")}', '{each2.get("uf_ZT56", "")}',
              {user_id},{user_id})
          """.replace('\n', ' ').strip())

    # 只有当有数据时才执行插入
    if header_values:
        insert_header_sql = ",".join(header_values)
        insert_sql = """
            INSERT INTO ut_emes_post_data_header(
                uf_guid, uf_bs_category, uf_vendor_short_name, uf_posting_date, 
                uf_posting_time, uf_company_code, create_id, update_id
            )
            VALUES {}
            ON DUPLICATE KEY UPDATE
                uf_bs_category = VALUES(uf_bs_category),
                uf_vendor_short_name = VALUES(uf_vendor_short_name),
                uf_posting_date = VALUES(uf_posting_date),
                uf_posting_time = VALUES(uf_posting_time),
                uf_company_code = VALUES(uf_company_code),
                create_id = VALUES(create_id),
                update_id = VALUES(update_id)
        """.format(insert_header_sql)

        print("执行的 Header SQL:", insert_sql)  # 调试用
        db.exec_sql(insert_sql)

    if item_values:
        insert_item_sql = ",".join(item_values)
        insert_sql = """
            INSERT INTO ut_emes_post_data_item(
                uf_guid, uf_line_id, uf_group_id, uf_res_doc_sn,
                uf_res_doc_items, uf_movement_type, uf_plant_code, uf_stor_loc_code, uf_inventory_status,
                uf_mat_code, uf_batch_sn, uf_transaction_qty, uf_parallel_qty,uf_rcv_stor_loc_code,uf_rcv_batch_sn, uf_tracking_number, uf_lot_no, uf_ZT04, uf_wafer_id,
                uf_ZT18, uf_runcard, uf_ZT07, uf_box_no, uf_production_date,
                uf_ZT53, uf_ZT14, uf_ZT15, uf_ZT54, uf_ZT08, uf_ZT09,uf_test_program,
                uf_ZT59, uf_ZT60, uf_ZT25, uf_ZT55, uf_ZT56,
                create_id, update_id
            )
            VALUES {}
            ON DUPLICATE KEY UPDATE
                uf_group_id = VALUES(uf_group_id),
                uf_res_doc_sn = VALUES(uf_res_doc_sn),
                uf_res_doc_items = VALUES(uf_res_doc_items),
                uf_movement_type = VALUES(uf_movement_type),
                uf_plant_code = VALUES(uf_plant_code),
                uf_stor_loc_code = VALUES(uf_stor_loc_code),
                uf_inventory_status = VALUES(uf_inventory_status),
                uf_mat_code = VALUES(uf_mat_code),
                uf_batch_sn = VALUES(uf_batch_sn),
                uf_transaction_qty = VALUES(uf_transaction_qty),
                uf_parallel_qty = VALUES(uf_parallel_qty),
                uf_tracking_number = VALUES(uf_tracking_number),
                uf_lot_no = VALUES(uf_lot_no),
                uf_ZT04 = VALUES(uf_ZT04),
                uf_wafer_id = VALUES(uf_wafer_id),
                uf_ZT18 = VALUES(uf_ZT18),
                uf_runcard = VALUES(uf_runcard),
                uf_ZT07 = VALUES(uf_ZT07),
                uf_box_no = VALUES(uf_box_no),
                uf_production_date = VALUES(uf_production_date),
                uf_ZT53 = VALUES(uf_ZT53),
                uf_ZT14 = VALUES(uf_ZT14),
                uf_ZT15 = VALUES(uf_ZT15),
                uf_ZT54 = VALUES(uf_ZT54),
                uf_ZT08 = VALUES(uf_ZT08),
                uf_ZT09 = VALUES(uf_ZT09),
                uf_test_program = VALUES(uf_test_program),
                uf_ZT59 = VALUES(uf_ZT59),
                uf_ZT60 = VALUES(uf_ZT60),
                uf_ZT25 = VALUES(uf_ZT25),
                uf_ZT55 = VALUES(uf_ZT55),
                uf_ZT56 = VALUES(uf_ZT56),
                create_id = VALUES(create_id),
                update_id = VALUES(update_id)
        """.format(insert_item_sql)

        print("执行的 Item SQL:", insert_sql)  # 调试用
        db.exec_sql(insert_sql)
    print("当前时间3：", now)
    type = 'S'
    message = '保存成功'
    db.dbCommit()
    type, message = save_sync_data(payload, data, rcv_batch_sn, user_id, created_reservations)

    return type, message


def get_res_item(each2):
    db = DbHelper()
    res_item_sql = f"""
                SELECT reference1_item, reference2_item, reference3_item
                FROM t_res_item
                WHERE res_doc_sn = '{each2.get('res_doc_sn', '')}' AND res_doc_items = {each2.get('res_doc_items', 0)}
            """
    res_item_result = db.query_sql(res_item_sql)
    if not res_item_result:
        reference1_item = ""
        reference2_item = ""
        reference3_item = ""
    else:
        reference1_item = res_item_result[0].get("reference1_item")
        reference2_item = res_item_result[0].get("reference2_item")
        reference3_item = res_item_result[0].get("reference3_item")
    res_doc_items_sql = f"""
    SELECT res_doc_items,batch_sn
        FROM t_res_item
        WHERE reference2_item = '{reference2_item}' AND reference3_item = '{reference3_item}'
    """
    res_doc_items_result = db.query_sql(res_doc_items_sql)
    if reference2_item == "" and reference3_item == "":
        res_doc_sn_sql = f"""
                        SELECT res_doc_sn, res_doc_items
                            FROM t_res_item
                            WHERE res_doc_sn = '{each2.get('res_doc_sn', '')}'
                        """
        res_doc_items_result = db.query_sql(res_doc_sn_sql)

    return res_doc_items_result


def save_sync_data(payload, data, rcv_batch_sn, user_id, created_reservations):
    db.dbCommit()
    type = ''
    message = ''
    line_counter = 1
    mat_doc_sn = ''
    now = datetime.datetime.now()
    res_doc_item_list = []
    item_post_data = []
    line_counter = 1
    res_doc_items = []
    for each in data['header']:
        for each2 in each['item']:
            res_doc_items_lst = []
            res_doc_items_lst.append(each2.get('res_doc_items', ''))
            res_doc_sn = each2.get('res_doc_sn', '')

            # 获取物料信息
            mat_info_sql = f"""
                SELECT basic_uom, parallel_uom, mat_group 
                FROM t_mmd_material_basic_data 
                WHERE mat_code = '{each2.get('mat_code', '')}'
            """
            mat_info_result = db.query_sql(mat_info_sql)

            if not mat_info_result:
                # 过账失败时标记预留单为删除状态
                mark_reservations_as_deleted(created_reservations, db)
                return "E", f"未找到物料代码 {each2.get('mat_code', '')} 的信息"

            basic_uom = mat_info_result[0].get("basic_uom")
            parallel_uom = mat_info_result[0].get("parallel_uom")
            mat_group = mat_info_result[0].get("mat_group")
            # 当物料编码的物料组为1开头时，取交易数量（片数），非1开头时取交易数量（颗数）
            if mat_group.startswith("1"):
                transaction_qty = each2.get('transaction_qty', 0)
                parallel_qty = each2.get('parallel_qty', 0)
            else:
                transaction_qty = each2.get('parallel_qty', 0)
                parallel_qty = 0
            code, msg, rcv_batch_sn, test_proc_result = get_rcv_batch_sn(each2.get('mat_code', ''),
                                                                         each2.get('batch_sn', ''),
                                                                         each2.get('box_no', ''))
            if code != 200:
                # 获取rcv_batch_sn失败，标记预留单为删除状态
                mark_reservations_as_deleted(created_reservations, db)
                return "E", f"获取接收批次号失败：{msg}"

            post_item = {
                "up_prod_mater_mark": "",
                "movement_type": "T001",
                "line_id": int(line_counter),
                "parent_id": "",
                "quality_insp_order_mark": "",
                "mat_code": each2.get('mat_code'),
                "batch_sn": each2.get('batch_sn'),
                "plant_code": each2.get('plant_code'),
                "stor_loc_code": each2.get('stor_loc_code'),
                "inventory_status": each2.get('inventory_status'),
                "transaction_qty": transaction_qty,
                "transaction_uom": basic_uom,
                "parallel_qty": parallel_qty,
                "parallel_uom": parallel_uom,
                "ro_sn": each2.get('res_doc_sn', ''),
                "ro_items": each2.get('res_doc_items', ''),
                "express_delivery": each2.get('express_delivery'),
                "reference1_item": "",
                "reference2_item": "",
                "reference3_item": "",

                "rcv_plant_code": each2.get('plant_code'),
                "rcv_stor_loc_code": each2.get('rcv_stor_loc_code'),
                "rcv_mat_code": each2.get('mat_code'),
                "rcv_batch_sn": rcv_batch_sn,
                "rcv_inventory_status": each2.get('inventory_status'),
                "rcv_special_inventory_status1": '',
                "rcv_special_inventory_status2": '',

                "special_inventory_status1": "",
                "special_inventory_status2": "",
                "rel_po_sn": "",
                "rel_po_items": "",
                "rel_po_component_number": 0,
                "rel_po_comp_batch_num": 0,
                "prodosn": "",
                "prodo_component_number": "",
                "rel_dn_sn": "",
                "rel_dn_item": "",
                "picking_document": "",
                "batch_item": "",
                "rel_procure_dn_sn": "",
                "rel_procure_dn_item": "",
                "pod_related": "",
                "rel_so_sn": "",
                "rel_so_items": "",
                "customer_code": "",
                "so_sn": "",
                "so_items": "",
                "project_sn": "",
                "vendor_code": "",
                "po_sn": "",
                "po_items": "",
                "wbs_elements": "",
                "cost_center": "",
                "cost_business_object": "",
                "cost_business_object1": "",
                "profit_center": "",
                "accounting_subjects": "",
                "asset_code1": "",
                "asset_code2": "",
                "equipment_code": "",
                "summary_line": "",
                "batch_number": test_proc_result[0],
                "rcv_batch_number": test_proc_result[0]
            }
            item_post_data.append(post_item)
            line_counter += 1

        head_post_data = {
            "document_category": "RES",
            "post_code": "4",
            "exchange_rate": "",
            "summary_unique_number": each['guid'],
            "vendor_dn": "",
            "document_date": datetime.datetime.now().strftime("%Y-%m-%d"),
            "posting_date": datetime.datetime.now().strftime("%Y-%m-%d"),
            "remarks_1": "",
            "remarks_2": "",
            "items": item_post_data
        }
        print(head_post_data, 'head_post_data')
        code, msg, error_list, mat_doc_sn, year = post_data(
            "0", user_id, head_post_data, item_post_data
        )
        if code != 200:
            # 过账失败时标记预留单为删除状态
            mark_reservations_as_deleted(created_reservations, db)
            type = 'E'
            message = f"过账失败:{msg}{','.join(error_list)}"
            return type, message
        print(data, '1231323')
        skip_update = True
        for item in item_post_data:
            ro_sn_sql = f"""
                select uf_res_doc_sn FROM ut_emes_post_data_item where uf_res_doc_sn = '{item.get('ro_sn')}' and uf_res_doc_items = '{item.get('ro_items')}'
            """
            print(ro_sn_sql, 'ro_sn_sql')
            ro_sn_result = db.query_sql(ro_sn_sql)
            uf_res_doc_sn = ro_sn_result[0].get("uf_res_doc_sn") if ro_sn_result else ""
            print(uf_res_doc_sn, 'uf_res_doc_sn')
            if uf_res_doc_sn != "":
                skip_update = False
                break

    print('-----------------------------------')
    type, message = update_emes_internal_receipt_data(payload, data, user_id, mat_doc_sn, year)
    if type != 'S':
        # 更新失败时标记预留单为删除状态
        mark_reservations_as_deleted(created_reservations, db)
        type = 'E'
        message = '更新抬头表失败'
        return type, message
    print("当前时间4：", now)
    type = 'S'
    message = '过账成功' + mat_doc_sn
    print('过账成功' + mat_doc_sn)
    return type, message


def check_res_doc_available_quantity(res_doc_sn, res_doc_items, transaction_qty, parallel_qty, mat_code):
    db = DbHelper()
    db.dbCommit()

    # 获取物料信息
    mat_info_sql = f"""
        SELECT basic_uom, parallel_uom, mat_group 
        FROM t_mmd_material_basic_data 
        WHERE mat_code = '{mat_code}'
    """
    mat_info_result = db.query_sql(mat_info_sql)
    if not mat_info_result:
        return f"未找到物料代码 {mat_code} 的信息"

    mat_info = mat_info_result[0]
    basic_uom = mat_info.get("basic_uom")
    parallel_uom = mat_info.get("parallel_uom")
    mat_group = mat_info.get("mat_group")
    print(mat_group, mat_info_sql, 'mat_info_sql')

    # 查询发货通知单信息
    query_sql = """
        SELECT basic_qty, issued_qty_base_uom, 
               parallel_qty as res_parallel_qty, issued_qty_parallel_uom
        FROM t_res_item
        WHERE res_doc_sn = '{}' AND res_doc_items = {} LIMIT 1
    """.format(res_doc_sn, res_doc_items)
    print(query_sql, 'query_sql')
    data = db.query_sql(query_sql)
    print(data, 'data1111')
    if not data:
        return "发货通知单不存在"

    res_data = data[0]
    error_messages = []

    # 根据物料组判断对比逻辑
    if mat_group.startswith("1"):
        # 物料组以1开头：交易数量（片数）与基本数量对比，平行数量（颗数）与平行数量对比
        available_basic_qty = res_data['basic_qty'] - res_data['issued_qty_base_uom']
        available_parallel_qty = res_data['res_parallel_qty'] - res_data['issued_qty_parallel_uom']

        if transaction_qty > available_basic_qty:
            error_messages.append(
                f"本次传入的交易数量{transaction_qty} + 已过账数量{res_data['issued_qty_base_uom']} = "
                f"{transaction_qty + res_data['issued_qty_base_uom']} 超出发货通知单可过账基本数量{res_data['basic_qty']}"
            )

        if parallel_qty > available_parallel_qty:
            error_messages.append(
                f"本次传入的平行数量{parallel_qty} + 已过账数量{res_data['issued_qty_parallel_uom']} = "
                f"{parallel_qty + res_data['issued_qty_parallel_uom']} 超出发货通知单可过账平行数量{res_data['res_parallel_qty']}"
            )
    else:
        # 物料组非1开头：平行数量（颗数）与基本数量对比，交易数量不做对比
        available_basic_qty = res_data['basic_qty'] - res_data['issued_qty_base_uom']

        if parallel_qty > available_basic_qty:
            error_messages.append(
                f"本次传入的平行数量{parallel_qty} + 已过账数量{res_data['issued_qty_base_uom']} = "
                f"{parallel_qty + res_data['issued_qty_base_uom']} 超出发货通知单可过账基本数量{res_data['basic_qty']}"
            )

    return "; ".join(error_messages) if error_messages else None


def check_batch_available_quantity(mat_code, batch_sn, stor_loc_code, transaction_qty, parallel_qty):
    # 获取物料信息
    db = DbHelper()
    mat_info_sql = f"""
        SELECT basic_uom, parallel_uom, mat_group 
        FROM t_mmd_material_basic_data 
        WHERE mat_code = '{mat_code}'
    """
    mat_info_result = db.query_sql(mat_info_sql)
    if not mat_info_result:
        return f"未找到物料代码 {mat_code} 的信息"

    mat_info = mat_info_result[0]
    mat_group = mat_info.get("mat_group")

    mat_code_result = {"data": {"mat_code": [mat_code], "batch_sn": [batch_sn], "stor_loc_code": [stor_loc_code]}}
    print(mat_code_result, 'mat_code_result')
    result = get_batch_inventory_Occupation(mat_code_result.get("data", ""))
    print(result, 'result')
    if not isinstance(result, tuple) or len(result) == 0:
        print("库存查询返回数据格式异常")
        return "库存查询返回数据格式异常"

    inventory_list = result[0]
    print(inventory_list, 'inventory_list')
    filtered_inventory = [
        item for item in inventory_list
        if item.get('mat_code') == mat_code and item.get('batch_sn') == batch_sn
    ]
    print(filtered_inventory, 'filtered_inventory')

    if not filtered_inventory:
        print("未找到对应的库存记录")
        return "未找到对应的库存记录"

    total_available_basic_qty = 0
    total_available_parallel_qty = 0

    for inventory in filtered_inventory:
        basic_qty = inventory.get('basic_qty', 0)
        available_parallel_qty = inventory.get('available_parallel_qty', 0)
        available_qty = inventory.get('available_qty', 0)
        parallel_qty_inv = inventory.get('parallel_qty', 0)
        occupied_parallel_qty = inventory.get('occupied_parallel_qty', 0)
        print(basic_qty, parallel_qty_inv, occupied_parallel_qty, 'parallel_qty_inv,occupied_parallel_qty')
        # available_parallel_qty = inventory.get('available_parallel_qty', 0)
        # total_available_basic_qty += (basic_qty - available_parallel_qty-available_qty)
        # total_available_parallel_qty += (parallel_qty_inv - occupied_parallel_qty-available_parallel_qty)
    print(available_qty, available_parallel_qty,
          'available_qty, available_parallel_qty')

    error_messages = []

    # 根据物料组判断对比逻辑
    if mat_group.startswith("1"):
        # 物料组以1开头：交易数量（片数）与基本数量对比，平行数量（颗数）与平行数量对比
        if transaction_qty > basic_qty:
            error_messages.append(
                f"该批次对应的可用库存基本数量不足，需要{transaction_qty}，可用{basic_qty}"
            )

        if parallel_qty > parallel_qty_inv:
            error_messages.append(
                f"该批次对应的可用库存平行数量不足，需要{parallel_qty}，可用{parallel_qty_inv}"
            )
    else:
        # 物料组非1开头：平行数量（颗数）与基本数量对比，交易数量不做对比
        if transaction_qty > basic_qty:
            error_messages.append(
                f"该批次对应的可用库存基本数量不足，需要{transaction_qty}，可用{basic_qty}"
            )

    return "; ".join(error_messages) if error_messages else None


# 更新内部领用批次分配表
def update_emes_internal_receipt_data(payload, data, user_id, mat_doc_sn, year):
    db = DbHelper()
    error_list = []
    type = ''
    message = ''
    uf_sn = 1
    res_doc_item_list = []
    for index, each in enumerate(data['header']):
        for index2, each2 in enumerate(each['item']):
            res_item_sql = f"""
                            SELECT 
                            reference2_item,
                            reference3_item,
                            mat_code,
                            batch_sn,
                            plant_code,
                            stor_loc_code,
                            basic_qty,
                            parallel_qty
                            FROM t_res_item
                            WHERE res_doc_sn = '{each2.get('res_doc_sn', '')}' AND res_doc_items = '{each2.get('res_doc_items', '')}'
                        """
            res_item_result = db.query_sql(res_item_sql)
            if not res_item_result:
                reference2_item = ""
                reference3_item = ""
                mat_code = ""
                batch_sn = ""
                plant_code = ""
                stor_loc_code = ""
                basic_qty = 0
                parallel_qty = 0
            else:
                reference2_item = res_item_result[0].get("reference2_item")
                reference3_item = res_item_result[0].get("reference3_item")
                mat_code = res_item_result[0].get("mat_code")
                batch_sn = res_item_result[0].get("batch_sn")
                plant_code = res_item_result[0].get("plant_code")
                stor_loc_code = res_item_result[0].get("stor_loc_code")
                basic_qty = res_item_result[0].get("basic_qty")
                parallel_qty = res_item_result[0].get("parallel_qty")
            external_mat_code_sql = f"""
            SELECT DISTINCT external_mat_code FROM t_mmd_material_basic_data where mat_code = '{each2.get('mat_code', '')}'
            """
            external_mat_code_result = db.query_sql(external_mat_code_sql)
            if not external_mat_code_result:
                external_mat_code = ""
            else:
                external_mat_code = external_mat_code_result[0].get("external_mat_code")
            # 获取配送地址
            shipping_address_sql = f"""
                SELECT uf_push_mark 
                FROM ut_transfer_order_notification_item 
                WHERE uf_reservation_no = '{each2.get('res_doc_sn', '')}' 
                    AND uf_reservation_item = '{each2.get('res_doc_items', '')}'
            """
            shipping_address_result = db.query_sql(shipping_address_sql)
            uf_push_mark = shipping_address_result[0].get("uf_push_mark") if shipping_address_result else 0
            mat_info = get_material_info(each2.get('mat_code', ''))
            # 如果 transaction_qty 也要同步转换
            if mat_info.get('mat_group', '').startswith('1'):
                uf_allocated_qty = each2.get('transaction_qty', '')
                uf_allocate_parallel_qty = each2.get('parallel_qty', '')
            else:
                uf_allocated_qty = each2.get('parallel_qty', '')
                uf_allocate_parallel_qty = 0
            # 根据reference2_item和reference3_item获取最大uf_sn
            max_sn_sql = f"""
                SELECT MAX(uf_sn) as max_sn
                FROM ut_transfer_order_notification_item 
                WHERE uf_reservation_no = '{each2.get('res_doc_sn', '')}' 
                    AND uf_reservation_item = '{each2.get('res_doc_items', '')}'
            """
            max_sn_result = db.query_sql(max_sn_sql)

            if max_sn_result and max_sn_result[0].get("max_sn") is not None:
                uf_sn = max_sn_result[0].get("max_sn") + 1
            else:
                uf_sn = 1

            # 检查是否已存在相同 uf_mat_doc_sn 和 uf_doc_year 的记录
            check_existing_sql = f"""
                SELECT uf_mat_doc_sn,uf_doc_year
                FROM ut_transfer_order_notification_item 
                WHERE 
                    uf_reservation_no = '{each2.get('res_doc_sn', '')}' 
                    AND uf_reservation_item = '{each2.get('res_doc_items', '')}'
            """
            print(check_existing_sql, 'check_existing_sql')
            existing_result = db.query_sql(check_existing_sql)
            existing_count = existing_result[0].get("uf_mat_doc_sn", "") if existing_result else ""
            print(existing_count, 'existing_count')
            if existing_count == "":
                del_sql = f"""
                    DELETE FROM
                ut_transfer_order_notification_item
                WHERE
                uf_reservation_no = '{each2.get('res_doc_sn', '')}' 
                    AND uf_reservation_item = '{each2.get('res_doc_items', '')}'
                """
                print(del_sql)
                status = db.exec_sql(del_sql)
                # 根据reference2_item和reference3_item获取最大uf_sn
                max_sn_sql = f"""
                    SELECT MAX(uf_sn) as max_sn
                    FROM ut_transfer_order_notification_item 
                    WHERE uf_reservation_no = '{each2.get('res_doc_sn', '')}' 
                    AND uf_reservation_item = '{each2.get('res_doc_items', '')}'
                """
                max_sn_result = db.query_sql(max_sn_sql)

                if max_sn_result and max_sn_result[0].get("max_sn") is not None:
                    uf_sn = max_sn_result[0].get("max_sn") + 1
                else:
                    uf_sn = 1
                # 记录已存在，执行UPDATE
                # update_sql = f"""
                #     INSERT INTO ut_transfer_order_notification_item (
                #         uf_reservation_no, uf_reservation_item, uf_sn,
                #         uf_mat_code, uf_batch_sn,
                #         uf_basic_qty,uf_parallel_qty, uf_from_stor_code,
                #         uf_to_stor_code,uf_deleted_mark, uf_push_mark,
                #         uf_express_delivery, uf_mat_doc_sn,
                #         uf_doc_year, update_id, create_id
                #     ) VALUES (
                #         '{each2.get('res_doc_sn', '')}', '{each2.get('res_doc_items', '')}', {uf_sn},
                #         '{each2.get('mat_code', '')}', '{each2.get('batch_sn', '')}',
                #         '{uf_allocated_qty}', '{uf_allocate_parallel_qty}', '{each2.get('stor_loc_code', '')}',
                #         '{each2.get('rcv_stor_loc_code', '')}', '0', '{uf_push_mark}', '{each2.get('express_delivery', '')}',
                #         '{mat_doc_sn}', '{year}', '{user_id}', '{user_id}'
                #     )
                # """
                # print(update_sql)
                # db.exec_sql(update_sql)
                print(f"更新记录: uf_mat_doc_sn={mat_doc_sn}, uf_doc_year={year}")
                update_header_sql = f"""
                    UPDATE ut_emes_post_data_header 
                                SET 
                                    uf_post_status = 'S',
                                    uf_mat_doc_sn = '{mat_doc_sn}',
                                    uf_year = '{year}',
                                    update_id = {user_id}
                                WHERE 
                                    uf_guid = '{each['guid']}'
                """
                print(update_header_sql)
                db.exec_sql(update_header_sql)
            else:
                # # 构建UPSERT语句（MySQL语法）
                # upsert_sql = f"""
                #     INSERT INTO ut_transfer_order_notification_item (
                #         uf_reservation_no, uf_reservation_item, uf_sn,
                #         uf_mat_code, uf_batch_sn,
                #         uf_basic_qty,uf_parallel_qty, uf_from_stor_code,
                #         uf_to_stor_code,uf_deleted_mark, uf_push_mark,
                #         uf_express_delivery, uf_mat_doc_sn,
                #         uf_doc_year, update_id, create_id
                #     ) VALUES (
                #         '{each2.get('res_doc_sn', '')}', '{each2.get('res_doc_items', '')}', {uf_sn},
                #         '{each2.get('mat_code', '')}', '{each2.get('batch_sn', '')}',
                #         '{uf_allocated_qty}', '{uf_allocate_parallel_qty}', '{each2.get('stor_loc_code', '')}',
                #         '{each2.get('rcv_stor_loc_code', '')}', '0', '{uf_push_mark}', '{each2.get('express_delivery', '')}',
                #         '{mat_doc_sn}', '{year}', '{user_id}', '{user_id}'
                #     )
                #         """
                # print(upsert_sql)
                # db.exec_sql(upsert_sql)
                uf_sn += 1
                update_header_sql = f"""
                    UPDATE ut_emes_post_data_header 
                                SET 
                                    uf_post_status = 'S',
                                    uf_mat_doc_sn = '{mat_doc_sn}',
                                    uf_year = '{year}',
                                    update_id = {user_id}
                                WHERE 
                                    uf_guid = '{each['guid']}'
                """
                print(update_header_sql)
                db.exec_sql(update_header_sql)
    type = 'S'
    message = '更新内部领用批次分配表成功'
    return type, message


def validate_fields(data: dict):
    """字段格式校验 - 适配多层数据结构"""
    errors = []

    # 抬头规则 - 将 posting_time 改为 datetime 类型
    header_rules = {
        "guid": ("varchar", 64, True, "GUID"),
        "bs_category": ("varchar", 64, True, "业务类别"),
        "vendor_short_name": ("varchar", 20, False, "供应商简称"),
        "posting_date": ("date", 0, True, "过账日期"),
        "posting_time": ("datetime", 0, True, "过账时间"),  # 改为 datetime 类型
        "company_code": ("varchar", 6, True, "公司代码")
    }

    # 行规则 - 保持不变
    item_rules = {
        "line_id": ("int", 0, True, "Line_ID"),
        "group_id": ("varchar", 64, False, "Group_ID"),
        "movement_type": ("varchar", 6, True, "移动类型"),
        "plant_code": ("varchar", 6, True, "工厂代码"),
        "stor_loc_code": ("varchar", 50, False, "库存地点"),
        "inventory_status": ("varchar", 4, True, "库存状态"),
        "mat_code": ("varchar", 40, True, "物料编码"),
        "batch_sn": ("varchar", 80, False, "批次号"),
        "transaction_qty": ("decimal", (16, 3), False, "交易数量（片数）"),
        "parallel_qty": ("decimal", (16, 3), True, "平行数量（颗数）"),
        "rcv_stor_loc_code": ("varchar", 50, False, "接收库存地点"),
        "express_delivery": ("varchar", 50, False, "运单号"),
        "lot_no": ("varchar", 10, True, "chipone Lot"),
        "uf_ZT04": ("varchar", 10, False, "Fountry Lot"),
        "wafer_id": ("varchar", 80, False, "Wafer ID"),
        "uf_ZT18": ("varchar", 10, False, "生产周"),
        "runcard": ("varchar", 40, False, "Runcard"),
        "uf_ZT07": ("varchar", 10, False, "BIN"),
        "box_no": ("varchar", 70, True, "箱号"),
        "production_date": ("date", 0, False, "制造日期"),
        "test_program": ("varchar", 70, False, "测试程序"),
        "uf_ZT53": ("varchar", 20, False, "BUMP厂"),
        "uf_ZT14": ("varchar", 20, False, "封装厂"),
        "uf_ZT15": ("varchar", 20, False, "测试厂(CP)"),
        "uf_ZT54": ("varchar", 20, False, "测试厂(FT)"),
        "uf_ZT08": ("varchar", 70, False, "封装形式"),
        "uf_ZT09": ("varchar", 70, False, "标签格式"),
        "uf_ZT59": ("varchar", 20, False, "FT订单号"),
        "uf_ZT60": ("varchar", 20, False, "PK订单号"),
        "uf_ZT25": ("varchar", 20, False, "封装订单号"),
        "uf_ZT55": ("varchar", 20, False, "CP订单号"),
        "uf_ZT56": ("varchar", 20, False, "BUMP订单号")
    }

    # ========== 处理多层数据结构 ==========
    # 如果存在 data.header 结构，则提取实际数据
    actual_data = data
    if "data" in data and "header" in data["data"]:
        headers = data["data"]["header"]
        if headers and isinstance(headers, list) and len(headers) > 0:
            actual_data = headers[0]
        else:
            return 400, "数据格式错误：header 数据为空", []

    # ========== 抬头字段校验 ==========
    header_errors = []
    header_mapped = {}

    # 检查数据结构
    if not isinstance(actual_data, dict):
        return 400, "数据格式错误：应为字典格式", []

    for field, (ftype, limit, required, desc) in header_rules.items():
        val = actual_data.get(field)

        # 必填校验
        if required and (val is None or val == ""):
            header_errors.append(f"{desc} 为必填字段")
            continue

        # 非必填且没传，设置默认值
        if val in (None, ""):
            if ftype in ("tinyint", "smallint", "mediumint", "int", "integer", "bigint"):
                header_mapped[f"uf_{field}"] = 0
            elif ftype in ("decimal", "numeric", "float", "double"):
                header_mapped[f"uf_{field}"] = 0.0
            elif ftype == "datetime":
                header_mapped[f"uf_{field}"] = None  # 或使用 datetime 的最小值
            else:
                header_mapped[f"uf_{field}"] = ""
            continue

        # 类型校验
        validation_passed = True
        if ftype == "varchar":
            if len(str(val)) > limit:
                header_errors.append(f"{desc} 超过最大长度 {limit}")
                validation_passed = False

        elif ftype == "date":
            try:
                if isinstance(val, str):
                    datetime.datetime.strptime(val, "%Y-%m-%d")
                elif isinstance(val, datetime.datetime):
                    val = val.strftime("%Y-%m-%d")
                else:
                    header_errors.append(f"{desc} 必须为日期(YYYY-MM-DD)")
                    validation_passed = False
            except Exception:
                header_errors.append(f"{desc} 必须为日期(YYYY-MM-DD)")
                validation_passed = False

        elif ftype == "datetime":  # 新增 datetime 类型校验
            try:
                if isinstance(val, str):
                    # 尝试多种常见的时间格式
                    formats = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
                               "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M"]
                    parsed = None
                    for fmt in formats:
                        try:
                            parsed = datetime.datetime.strptime(val, fmt)
                            break
                        except ValueError:
                            continue

                    if not parsed:
                        header_errors.append(f"{desc} 必须为日期时间格式(如: YYYY-MM-DD HH:MM:SS)")
                        validation_passed = False
                    else:
                        val = parsed.strftime("%Y-%m-%d %H:%M:%S")
                elif isinstance(val, datetime.datetime):
                    val = val.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    header_errors.append(f"{desc} 必须为日期时间格式")
                    validation_passed = False
            except Exception:
                header_errors.append(f"{desc} 必须为日期时间格式(如: YYYY-MM-DD HH:MM:SS)")
                validation_passed = False

        elif ftype in ("int", "bigint"):
            try:
                int(val)
                val = int(val)
            except (ValueError, TypeError):
                header_errors.append(f"{desc} 必须为整数")
                validation_passed = False

        # 只有验证通过才存储值
        if validation_passed:
            header_mapped[f"uf_{field}"] = val

    if header_errors:
        header_error_msg = (
                f"业务类别 {actual_data.get('bs_category', '')} 过账日期：{actual_data.get('posting_date', '')} "
                + ", ".join(header_errors)
        )
        errors.append(header_error_msg)

    # ========== item 内字段校验 ==========
    items = actual_data.get("item", [])
    item_mapped = []

    if not isinstance(items, list):
        return 400, "item 字段应为列表格式", []

    for idx, row in enumerate(items, start=1):
        if not isinstance(row, dict):
            errors.append(f"第{idx}行数据格式错误：应为字典格式")
            continue

        line_id = row.get("line_id", f"第{idx}行")
        items_errors = []
        mapped_row = {}

        for field, (ftype, limit, required, desc) in item_rules.items():
            val = row.get(field)

            # 必填校验
            if required and (val is None or val == ""):
                items_errors.append(f"{desc} 为必填字段")
                continue

            # 非必填且没传，设置默认值
            if val in (None, ""):
                if ftype in ("tinyint", "smallint", "mediumint", "int", "integer", "bigint"):
                    mapped_row[f"uf_{field}"] = 0
                elif ftype in ("decimal", "numeric", "float", "double"):
                    mapped_row[f"uf_{field}"] = 0.0
                else:
                    mapped_row[f"uf_{field}"] = ""
                continue

            # 类型校验（保持不变）
            validation_passed = True
            if ftype == "varchar":
                if len(str(val)) > limit:
                    items_errors.append(f"{desc} 超过最大长度 {limit}")
                    validation_passed = False

            elif ftype == "decimal":
                try:
                    s = str(val).strip()
                    is_negative = s.startswith('-')
                    s_clean = s.lstrip('-')

                    if "." in s_clean:
                        int_part, dec_part = s_clean.split(".")
                    else:
                        int_part, dec_part = s_clean, ""

                    if len(int_part) > (limit[0] - limit[1]):
                        items_errors.append(f"{desc} 整数位超过 {limit[0] - limit[1]}")
                        validation_passed = False

                    if len(dec_part) > limit[1]:
                        items_errors.append(f"{desc} 小数位超过 {limit[1]}")
                        validation_passed = False

                    float(val)
                except Exception:
                    items_errors.append(
                        f"{desc} 格式错误，应为 decimal({limit[0]},{limit[1]})"
                    )
                    validation_passed = False

            elif ftype in ("int", "bigint"):
                try:
                    int(val)
                    val = int(val)
                except (ValueError, TypeError):
                    items_errors.append(f"{desc} 必须为整数")
                    validation_passed = False

            elif ftype == "date":
                try:
                    if isinstance(val, str):
                        datetime.datetime.strptime(val, "%Y-%m-%d")
                    elif isinstance(val, datetime.datetime):
                        val = val.strftime("%Y-%m-%d")
                    else:
                        items_errors.append(f"{desc} 必须为日期(YYYY-MM-DD)")
                        validation_passed = False
                except Exception:
                    items_errors.append(f"{desc} 必须为日期(YYYY-MM-DD)")
                    validation_passed = False

            # 只有验证通过才存储值
            if validation_passed:
                mapped_row[f"uf_{field}"] = val

        item_mapped.append(mapped_row)
        if items_errors:
            items_err_msg = f"行号{line_id} " + ", ".join(items_errors)
            if not header_errors:
                items_err_msg = f"业务类别 {actual_data.get('bs_category', '')} " + items_err_msg
            errors.append(items_err_msg)

    header_mapped["item"] = item_mapped

    if errors:
        msg = "; ".join(errors)
        if len(msg) > 200:
            msg = msg[:200] + "......"
        return 400, msg, []
    return 200, "校验通过", header_mapped


if __name__ == '__main__':
    # 模拟请求体
    req_body = {
        "guid": "CA596362-8F85-413A-B20C-3948DD2CAA4D",
        "data": {
            "header": [
                {
                    "bs_category": "21",
                    "company_code": "1000",
                    "guid": "CA596362-8F85-413A-B20C-3948DD2CAA4D",
                    "item": [
                        {
                            "batch_sn": "",
                            "box_no": "PK20251124000007",
                            "express_delivery": "",
                            "inventory_status": "0",
                            "line_id": "1",
                            "lot_no": "E30960AA",
                            "mat_code": "C7B1039PN-AANN-AANNNNN",
                            "movement_type": "T001",
                            "parallel_qty": "24741.000",
                            "plant_code": "1000",
                            "production_date": "",
                            "rcv_stor_loc_code": "L001",
                            "runcard": "",
                            "stor_loc_code": "A067",
                            "test_program": "T_242_C7B1039PN-AANN-AANNNNN_C7B005WAA-QSOP24L-TR4S_V01_FT",
                            "transaction_qty": "0",
                            "uf_ZT04": "",
                            "uf_ZT07": "BIN1",
                            "uf_ZT08": "SSOP24_0.635",
                            "uf_ZT09": "",
                            "uf_ZT14": "Mountek-ME",
                            "uf_ZT15": "",
                            "uf_ZT18": "2421",
                            "uf_ZT25": "",
                            "uf_ZT53": "",
                            "uf_ZT54": "景尚",
                            "uf_ZT55": "",
                            "uf_ZT56": "",
                            "uf_ZT59": "",
                            "uf_ZT60": "",
                            "wafer_id": ""
                        },
                        {
                            "batch_sn": "",
                            "box_no": "PK20251124000003",
                            "express_delivery": "",
                            "inventory_status": "0",
                            "line_id": "2",
                            "lot_no": "D89120AA",
                            "mat_code": "ICND3018PN-AA-AA-GANN",
                            "movement_type": "T001",
                            "parallel_qty": "3857.000",
                            "plant_code": "1000",
                            "production_date": "",
                            "rcv_stor_loc_code": "L001",
                            "runcard": "",
                            "stor_loc_code": "A067",
                            "test_program": "T_242_ICND3018PN-AA-AA-GANN_ICND3018WAA-QSOP24L-TR4S_V02A_FT",
                            "transaction_qty": "0",
                            "uf_ZT04": "",
                            "uf_ZT07": "BIN1",
                            "uf_ZT08": "SSOP24_0.635",
                            "uf_ZT09": "",
                            "uf_ZT14": "Mountek-ME",
                            "uf_ZT15": "",
                            "uf_ZT18": "2511",
                            "uf_ZT25": "",
                            "uf_ZT53": "",
                            "uf_ZT54": "景尚",
                            "uf_ZT55": "",
                            "uf_ZT56": "",
                            "uf_ZT59": "",
                            "uf_ZT60": "",
                            "wafer_id": ""
                        }
                    ],
                    "posting_date": "2025-11-24",
                    "posting_time": "2025-11-24 14:37:06",
                    "remarks": "",
                    "vendor_short_name": "Mountek-ME"
                }
            ]
        }
    }

    # code, msg, header_mapped = validate_fields(req_body)
    # print(code, msg, header_mapped)
    response = save_emes_wanjia_goods_transfer_data(req_body, 12)
    print(response)