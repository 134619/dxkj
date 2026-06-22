# -*- coding: utf-8 -*-
import copy
import json
import traceback
from datetime import datetime

from DbHelper import DbHelper
from itf_cof_cutoff_downline import cof_cutoff_downline
from itf_create_purchase_order_manually import create_purchase_order_manually
from itf_delivery_post import delivery_post
from itf_department_picking_requisition_creation import Save_picking
from itf_device_borrow_log import DeviceBorrowLogSync
from itf_dn_reversal_post import dn_reversal_post
from itf_down_attach_url import Downloa_attach
from itf_ds_loss import ds_loss
from itf_elivery_order_creation_status_extraction import get_status
from itf_emes_goods_issue_data import save_emes_goods_issue_data
from itf_emes_goods_transfer_data import save_emes_goods_transfer_data
from itf_emes_offline_data import emes_push_mh_offline_data
from itf_emes_wanjia_goods_transfer_data import save_emes_wanjia_goods_transfer_data
from itf_intercompany_float_sync import intercompany_float_sync
from itf_ito_inner_company_reversal_post import ito_inner_company_reversal
from itf_ito_post import ito_post
from itf_material_symbol_update import material_symbol_update
from itf_online_retest_data_synchronization import SynchronizationRetestData
from itf_outsourcing_receipt import Save_outsourcing_receipt
from itf_power_on_log import PowerOnLogSync
from itf_production import QueryProduction, Save_production
from itf_purchase_order_update import update_po_item_price
from itf_purchase_price_status_update import purchase_price_status_update
from itf_purchase_receipt import purchase_receipt
from itf_query_purchase_order import query_purchase_order
from itf_rate_sync_handler import CurrencyRateSync
from itf_rcv_bom import rcv_bom
from itf_rcv_craft import rcv_craft
from itf_rcv_customer import rcv_customer
from itf_rcv_mat import rcv_mat
from itf_rcv_vendor import rcv_vendor

# from itf_test_sk01 import test_interface as sk01
from itf_receiveOAPurchasePriceData import save_data as OAPurchasePriceDataSave
from itf_return_delivery_post import return_delivery_post
from itf_sales_order_create import sales_order_create
from itf_sales_order_update import sales_order_update
from itf_SAP_std_cost_extrac import itf_SAP_std_cost_extrac
from itf_stor_batch_hold import stor_batch_hold
from itf_supplier_machine_reconciliation import SupplierMachineReconciliationSync
from itf_supplier_quotations import SupplierQuotationsSync
from itf_supplier_reconciliation import SupplierReconciliationSync
from itf_test_interface import test_interface
from itf_test_script import TestScriptSync
from itf_up_scrap_apply_status import up_scrap_apply_status
from itf_update_gross_die import update_gross_die
from itf_update_purchase_order_price import update_purchase_order_price
from itf_wafer_cp_processing_fee_push import Save_wafer_cp
from itf_wbs_sync_handler import WBSSync
from libenhance import Request, Response, SysHandler, get_cnf
from logger import LoggerConfig
from SapInteractionLog import createSapLog
from SimpleJSONPath import SimpleJSONPath

log = LoggerConfig("ExtendHandler", isStream=True)

# 每个接口在这里维护  key: interface_code, value: 数组(方法名, 描述)
INTERFACE_HANDLERS = {
    "test_interface": (test_interface, "测试用接口"),
    "ZSD_INT_003": (purchase_price_status_update, "更新价格主数据审批状态"),
    "ZMM_INT_015": (create_purchase_order_manually, "采购订单创建接口"),
    "ZMM_INT_010": (update_po_item_price, "采购订单更新接口"),
    "ZMM_INT_016": (Save_production, "产销计划创建接口"),
    "ZMM_INT_018": (Save_production, "产销计划修改接口"),
    "ZMM_INT_017": (QueryProduction, "产销计划查询接口"),
    "ZPU_HW_002": (query_purchase_order, "查询采购订单接口"),
    "ZMM_INT_020": (Save_wafer_cp, "CP加工费推送接口"),
    "ZMM_INT_011": (SynchronizationRetestData, "在线复测数据同步接口"),
    "ZMM_INT_005": (TestScriptSync, "秘火测试程序更新同步接口"),
    "ZMM_INT_004": (SupplierQuotationsSync, "秘火供应商报价同步接口"),
    "ZMM_INT_006": (PowerOnLogSync, "秘火当期开机明细同步接口"),
    "ZMM_INT_007": (DeviceBorrowLogSync, "秘火当期借机明细同步接口"),
    "ZMM_INT_008": (SupplierMachineReconciliationSync, "秘火供应商机台对账单同步接口"),
    "ZMM_INT_009": (SupplierReconciliationSync, "秘火供应商加工费对账单同步接口"),
    "ZMM_INT_019": (update_purchase_order_price, "秘火晶圆附加费用推送接口"),
    "ZMM_INT_022": (save_emes_goods_issue_data, "秘火发货过账接口（产生预留单）"),
    "ZMM_INT_023": (save_emes_goods_transfer_data, "秘火调拨过账接口"),
    "ZSD_INT_007": (delivery_post, "秘火发货过账接口（销售）"),
    # "ZSD_INT_655": (sk01, "SAP寄售发货同步秘火"),
    "ZSD_INT_002": (OAPurchasePriceDataSave, "秘火价格主数据创建接口"),
    "ZSD_INT_012": (ito_post, "秘火公司间调拨过账接口"),
    "ZMM_INT_027": (stor_batch_hold, "秘火库存hold接口"),
    "ZMM_INT_024": (up_scrap_apply_status, "报废申请状态更新接口"),
    "ZSD_INT_301": (sales_order_create, "SAP销售订单&交货单创建接口"),
    "ZMM_INT_014": (purchase_receipt, "秘火外购收货接口"),
    "ZMM_INT_012": (emes_push_mh_offline_data, "秘火下线接口"),
    "ZSD_INT_300": (get_status, "交货单创建状态提取接口"),
    "ZMM_INT_021": (Save_picking, "秘火部门领料申请单创建接口"),
    "ZMM_INT_028": (material_symbol_update, "秘火EOL物料状态更新接口"),
    "ZMM_INT_106": (itf_SAP_std_cost_extrac, "SAP标准成本提取接口"),
    "ZSD_INT_305": (intercompany_float_sync, "秘火公司间浮点同步接口"),
    "ZSD_INT_302": (sales_order_update, "SAP销售订单&交货单修改接口"),
    "ZMM_INT_013": (Save_outsourcing_receipt, "秘火外协入库接口"),
    "ZMM_INT_029": (update_gross_die, "更新goss die数量"),
    "ZMM_INT_026": (ds_loss, "切割损耗"),
    "ZSD_INT_008": (dn_reversal_post, "交货单冲销过账"),
    "ZSD_INT_014": (CurrencyRateSync, "秘火汇率同步接口"),
    "ZSD_INT_015": (WBSSync, "秘火WBS同步接口"),
    "ZSD_INT_016": (Downloa_attach, "附件下载（销售）"),
    "ZMM_INT_030": (rcv_craft, "秘火接收PLM工艺信息"),
    "ZMM_INT_118": (cof_cutoff_downline, "COF切割下线接口"),
    "ZSD_INT_009": (return_delivery_post, "秘火退货过账接口（销售）"),
    "ZMM_INT_001": (rcv_mat, "秘火接收SAP物料主数据"),
    "ZMM_INT_002": (rcv_bom, "秘火接收SAPBOM主数据"),
    "ZMM_INT_003": (rcv_vendor, "秘火接收SAP供应商主数据"),
    "ZSD_INT_001": (rcv_customer, "秘火接收SAP客户主数据"),
    "ZSD_INT_013": (ito_inner_company_reversal, "秘火冲销公司间过账"),
    "ZMM_INT_119": (save_emes_wanjia_goods_transfer_data, "万佳仓库调拨入库过账接口")
}

#对应接口的客制化字段及路径
#例: "ZSD_INT_003": ('data[].OALCBH','data[].price_condition_code'),
INTERFACE_JSONPATH = {
    "test_interface": ('guid',),
}




# === 统一的接口处理器, 这个方法不用动了 ===
def interface_handler(interface_code, payload, user_id):
    response = {"type": "E", "message": "未知错误"}
    message_type = "E"
    message_text = "系统异常"
    try:
        handler = INTERFACE_HANDLERS.get(interface_code)

        if not handler:
            response = {"type": "E", "message": "接口名不正确"}
        else:
            handler = handler[0]
            response = handler(payload, user_id)

        if type(response) == dict:
            message_type = response.get("type", '')
            message_text = response.get("message", '')
        else:
            message_type, message_text = 'S', '成功'

    except Exception as e:
        print(f"异常类型: {type(e).__name__}")
        print(f"异常信息: {str(e)}")
        print(f"堆栈跟踪:\n{traceback.format_exc()}")
        response = {"type": "E", "message": "系统异常"}
        message_type = "E"
        message_text = "系统异常"

    return response, message_type, message_text


def httpServerHandler():
    filtering_interface()
    res = Response()
    req = Request()

    log.printInfo("入参", req.body())

    sys = SysHandler()
    db = DbHelper()
    body = json.loads(req.body())
    interface_code = body["interface_code"]
    user_id = req.header("user_id") or sys.get_env("user_id") or 0
    payload = body["payload"]
    log_data = copy.deepcopy(payload)

    GUID = log_data.get("guid")
    if not GUID:
        res.set_body(json.dumps({"type": "E", "message": "无法获取GUID"}))
        res.commit(True)
        return
    else:
        if db.query_sql(f"select GUID from t_sap_process where GUID = '{GUID}' and message_type = 'S' "):
            res.set_body(json.dumps({"type": "E", "message": "GUID重复,请重新生成再发送"}))
            res.commit(True)
            return

    start_timestamp = int(datetime.timestamp(datetime.now()))

    response, message_type, message_text = interface_handler(interface_code, payload, user_id)


    end_timestamp = int(datetime.timestamp(datetime.now()))
    time_difference = end_timestamp - start_timestamp

    if type(response) == tuple:
        if INTERFACE_HANDLERS.get(interface_code) and type(response[-1]) == bytes:
            createSapLog([{
                "GUID": log_data["guid"],
                "interface_code": interface_code,
                "interface_name": INTERFACE_HANDLERS.get(interface_code)[-1],
                "interface_data": json.dumps([log_data]),
                "interface_returns_data": response[0],
                "message_type": message_type,
                "message_text": message_text,
                "start_timestamp": start_timestamp,
                "end_timestamp": end_timestamp,
                "time_difference": time_difference,
                "synchronizatio_user": 0
            }])

        res.set_header("Content-Disposition", "attachment; filename*=UTF-8\'\'{}".format(response[0]))
        res.set_header("Content-Type", "application/octet-stream")
        res.set_body(response[-1])
        res.commit(True)
    else:
        # 组织日志参数
        if INTERFACE_HANDLERS.get(interface_code):
            log_info = {
                "GUID": log_data["guid"],
                "interface_code": interface_code,
                "interface_name": INTERFACE_HANDLERS.get(interface_code)[-1],
                "interface_data": json.dumps([log_data]),
                "interface_returns_data": json.dumps([response]),
                "message_type": message_type,
                "message_text": message_text,
                "start_timestamp": start_timestamp,
                "end_timestamp": end_timestamp,
                "time_difference": time_difference,
                "synchronizatio_user": 0
            }
            for index,path_info in enumerate(INTERFACE_JSONPATH.get(interface_code,tuple())):
                if SimpleJSONPath.exists(log_data,path_info):

                    result = SimpleJSONPath.query(log_data,path_info)
                    if isinstance(result, list):
                        result = ','.join(result)
                else:
                    result = ''
                    log.printInfo('json路径匹配错误', 'Warning: {} 路径不存在请确认'.format(path_info))
                log_info['customization_field{}'.format(index + 1)] = result

            createSapLog([log_info])

        res.set_body(json.dumps(response))
        res.commit(True)


def filtering_interface():
    global INTERFACE_HANDLERS
    shielded_interface = get_cnf('shielded_interface').split(',') or []
    if shielded_interface:

        if 'all' in shielded_interface:
            INTERFACE_HANDLERS = {}
        else:
            INTERFACE_HANDLERS = {k: v for k, v in INTERFACE_HANDLERS.items() if k not in shielded_interface}