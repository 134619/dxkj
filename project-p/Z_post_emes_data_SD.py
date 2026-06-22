"""
@File    : Z_post_emes_data_SD.py
@Author  : jing.deng@dxdstech.com
@Date    : 2025/11/11
@explain : 执行eMES数据过账-SD模块 【交货单/调拨单过账】
"""
import copy
import json
import uuid
from datetime import datetime

from DbHelper import DbHelper
from DxInventoryPostData import post_data as post_inventory_data
from itf_delivery_post import delivery_post_main
from itf_dn_reversal_post import execute_reversal
from itf_ito_inner_company_reversal_post import execute_inner_company_reversal
from itf_ito_post import ito_post_main
from itf_return_delivery_post import return_delivery_post_main
from libenhance import Request, Response
from logger import LoggerConfig
from Z_generate_batch_sn import get_batch_sn_info

logger = LoggerConfig("Z_post_emes_data_SD", isStream=True)



from ToolsMethods import (
    GetDisplay,
    GetEnToZh,
    GetExportData,
    Paginator,
    calc_time,
    create_table_alias,
    display_to_entozh,
    generate_limit_sql,
    generate_raw_sql,
    get_total_count,
)
from Z_post_emes_data import POST_STATUS_MAP


def getdisplay(uf_bs_category):
    display = []
    if uf_bs_category == '29' or uf_bs_category == '31':
        display = [
            {"field": "type", "description": "执行结果", "type": "varchar", "length": 20, "decimal": 0},
            {"field": "msg", "description": "消息文本", "type": "varchar", "length": 200, "decimal": 0},
            {"field": "uf_guid", "description": "GUID", "type": "varchar"},
            {"field": "uf_bs_category", "description": "业务类别", "type": "varchar"},
            {"field": "uf_posting_date", "description": "过账日期", "type": "date"},
            {"field": "uf_tracking_number", "description": "快递单号", "type": "varchar"},
            {"field": "uf_dn_sn", "description": "交货单号", "type": "varchar"},
            {"field": "uf_picking_document", "description": "拣配单号", "type": "varchar"},
            {"field": "uf_filed_code1", "description": "预留字段1", "type": "varchar"},
            {"field": "uf_filed_code2", "description": "预留字段2", "type": "varchar"},
            {"field": "uf_filed_code3", "description": "预留字段3", "type": "varchar"},
            {"field": "lth_uf_mat_doc_sn", "description": "交货单过账凭证号", "type": "varchar"},
            {"field": "lth_uf_msg", "description": "交货单过账消息", "type": "varchar"},
            {"field": "lth_uf_reversal_mark", "description": "交货单冲销标识", "type": "varchar"},
            {"field": "uf_line_id", "description": "接口传入行", "type": "int"},
            {"field": "uf_dn_item", "description": "交货单行号", "type": "int"},
            {"field": "uf_batch_item", "description": "拣配单行号", "type": "int"},
            {"field": "uf_posting_time", "description": "过账时间", "type": "varchar"},
            {"field": "uf_mat_code", "description": "物料编码", "type": "varchar"},
            {"field": "uf_stor_loc_code", "description": "库存地点", "type": "varchar"},
            {"field": "uf_picked_qty", "description": "拣配数量", "type": "decimal"},
            {"field": "uf_picked_base_qty", "description": "拣配数量（基本单位）", "type": "decimal"},
            {"field": "uf_picked_parallel_qty", "description": "拣配数量（平行单位）", "type": "decimal"},
            {"field": "uf_batch_sn", "description": "批次号", "type": "varchar"},
            {"field": "uf_lot_no", "description": "制造批号", "type": "varchar"},
            {"field": "uf_ZT04", "description": "晶圆批次(Foundry Lot NO)", "type": "varchar"},
            {"field": "uf_wafer_id", "description": "制造序号", "type": "varchar"},
            {"field": "uf_ZT07", "description": "BIN", "type": "varchar"},
            {"field": "uf_ZT18", "description": "生产周", "type": "varchar"},
            {"field": "uf_runcard", "description": "Runcard", "type": "varchar"},
            {"field": "uf_box_no", "description": "箱号", "type": "varchar"},
            {"field": "uf_production_date", "description": "制造日期", "type": "date"},
            {"field": "uf_ZT05", "description": "CP程序", "type": "varchar"},
            {"field": "uf_ZT20", "description": "CP2程序", "type": "varchar"},
            {"field": "uf_ZT21", "description": "CP3程序", "type": "varchar"},
            {"field": "uf_ZT35", "description": "CP4程序", "type": "varchar"},
            {"field": "uf_ZT36", "description": "CP5程序", "type": "varchar"},
            {"field": "uf_ZT37", "description": "CP6程序", "type": "varchar"},
            {"field": "uf_ZT38", "description": "CP7程序", "type": "varchar"},
            {"field": "uf_ZT06", "description": "FT1程序", "type": "varchar"},
            {"field": "uf_ZT48", "description": "FT2程序", "type": "varchar"},
            {"field": "uf_ZT49", "description": "FT3程序", "type": "varchar"},
            {"field": "uf_ZT50", "description": "FT4程序", "type": "varchar"},
            {"field": "uf_ZT51", "description": "FT5程序", "type": "varchar"},
            {"field": "uf_ZT53", "description": "Bump厂", "type": "varchar"},
            {"field": "uf_ZT14", "description": "封装厂", "type": "varchar"},
            {"field": "uf_ZT15", "description": "测试厂（CP）", "type": "varchar"},
            {"field": "uf_ZT54", "description": "测试厂（FT）", "type": "varchar"},
            {"field": "uf_ZT08", "description": "封装形式", "type": "varchar"},
            {"field": "uf_ZT09", "description": "标签格式", "type": "varchar"},
            {"field": "uf_ZT17", "description": "条数", "type": "varchar"},
            {"field": "uf_doc_sn1", "description": "公司间调拨单据1", "type": "varchar"},
            {"field": "ito1_uf_po_sn", "description": "公司间调拨单据1采购订单号", "type": "varchar"},
            {"field": "ito1_uf_so_sn", "description": "公司间调拨单据1销售订单号", "type": "varchar"},
            {"field": "ito1_uf_dn_sn", "description": "公司间调拨单据1交货单号", "type": "varchar"},
            {"field": "ito1_uf_dn_doc", "description": "公司间调拨单据1交货单过账凭证", "type": "varchar"},
            {"field": "ito1_uf_picking_document", "description": "公司间调拨单据1交货拣配单号", "type": "varchar"},
            {"field": "ito1_uf_po_doc", "description": "公司间调拨单据1采购过账凭证", "type": "varchar"},
            {"field": "ito1_uf_year", "description": "公司间调拨单据1过账年度", "type": "varchar"},
            {"field": "ito1_uf_status", "description": "公司间调拨单据1状态", "type": "varchar"},
            {"field": "ito1_uf_msg", "description": "公司间调拨单据1消息", "type": "varchar"},
            {"field": "uf_doc_sn2", "description": "调拨单据2", "type": "varchar"},
            {"field": "ito2_uf_po_sn", "description": "公司间调拨单据2采购订单号", "type": "varchar"},
            {"field": "ito2_uf_so_sn", "description": "公司间调拨单据2销售订单号", "type": "varchar"},
            {"field": "ito2_uf_dn_sn", "description": "公司间调拨单据2交货单号", "type": "varchar"},
            {"field": "ito2_uf_dn_doc", "description": "公司间调拨单据2交货单过账凭证", "type": "varchar"},
            {"field": "ito2_uf_picking_document", "description": "公司间调拨单据2交货拣配单号", "type": "varchar"},
            {"field": "ito2_uf_po_doc", "description": "公司间调拨单据2采购过账凭证", "type": "varchar"},
            {"field": "ito2_uf_year", "description": "公司间调拨单据2过账年度", "type": "varchar"},
            {"field": "ito2_uf_status", "description": "公司间调拨单据2状态", "type": "varchar"},
            {"field": "ito2_uf_msg", "description": "公司间调拨单据2消息", "type": "varchar"},
        ]

    elif uf_bs_category == '37':
        display = [
            {"field": "type", "description": "执行结果", "type": "varchar", "length": 20, "decimal": 0},
            {"field": "msg", "description": "消息文本", "type": "varchar", "length": 200, "decimal": 0},
            {"field": "uf_guid", "description": "GUID", "type": "varchar"},
            {"field": "uf_bs_category", "description": "业务类别", "type": "varchar"},
            {"field": "uf_posting_date", "description": "过账日期", "type": "date"},
            {"field": "uf_tracking_number", "description": "快递单号", "type": "varchar"},
            {"field": "uf_ito_sn", "description": "调拨单号", "type": "varchar"},
            {"field": "uf_posting_time", "description": "过账时间", "type": "datetime"},
            {"field": "uf_filed_code1", "description": "预留字段1", "type": "varchar"},
            {"field": "uf_filed_code2", "description": "预留字段2", "type": "varchar"},
            {"field": "uf_filed_code3", "description": "预留字段3", "type": "varchar"},
            {"field": "lth_uf_mat_doc_sn", "description": "交货单过账凭证号", "type": "varchar"},
            {"field": "lth_uf_msg", "description": "交货单过账消息", "type": "varchar"},
            {"field": "lth_uf_reversal_mark", "description": "交货单冲销标识", "type": "varchar"},
            {"field": "uf_line_id", "description": "接口传入行", "type": "int"},
            {"field": "uf_ito_items", "description": "调拨单行号", "type": "int"},
            {"field": "uf_mat_code", "description": "物料编码", "type": "varchar"},
            {"field": "uf_stor_loc_code", "description": "库存地点", "type": "varchar"},
            {"field": "uf_qty", "description": "调拨数量", "type": "decimal"},
            {"field": "uf_batch_sn", "description": "批次号", "type": "varchar"},
            {"field": "uf_lot_no", "description": "制造批号", "type": "varchar"},
            {"field": "uf_ZT04", "description": "晶圆批次(Foundry Lot NO)", "type": "varchar"},
            {"field": "uf_wafer_id", "description": "制造序号", "type": "varchar"},
            {"field": "uf_ZT07", "description": "BIN", "type": "varchar"},
            {"field": "uf_ZT18", "description": "生产周", "type": "varchar"},
            {"field": "uf_runcard", "description": "Runcard", "type": "varchar"},
            {"field": "uf_box_no", "description": "箱号", "type": "varchar"},
            {"field": "uf_production_date", "description": "制造日期", "type": "date"},
            {"field": "uf_ZT05", "description": "CP程序", "type": "varchar"},
            {"field": "uf_ZT20", "description": "CP2程序", "type": "varchar"},
            {"field": "uf_ZT21", "description": "CP3程序", "type": "varchar"},
            {"field": "uf_ZT35", "description": "CP4程序", "type": "varchar"},
            {"field": "uf_ZT36", "description": "CP5程序", "type": "varchar"},
            {"field": "uf_ZT37", "description": "CP6程序", "type": "varchar"},
            {"field": "uf_ZT38", "description": "CP7程序", "type": "varchar"},
            {"field": "uf_ZT06", "description": "FT1程序", "type": "varchar"},
            {"field": "uf_ZT48", "description": "FT2程序", "type": "varchar"},
            {"field": "uf_ZT49", "description": "FT3程序", "type": "varchar"},
            {"field": "uf_ZT50", "description": "FT4程序", "type": "varchar"},
            {"field": "uf_ZT51", "description": "FT5程序", "type": "varchar"},
            {"field": "uf_ZT53", "description": "Bump厂", "type": "varchar"},
            {"field": "uf_ZT14", "description": "封装厂", "type": "varchar"},
            {"field": "uf_ZT15", "description": "测试厂（CP）", "type": "varchar"},
            {"field": "uf_ZT54", "description": "测试厂（FT）", "type": "varchar"},
            {"field": "uf_ZT08", "description": "封装形式", "type": "varchar"},
            {"field": "uf_ZT09", "description": "标签格式", "type": "varchar"},
            {"field": "uf_ZT17", "description": "条数", "type": "varchar"},
            {"field": "ito1_uf_po_sn", "description": "公司间调拨采购订单号", "type": "varchar"},
            {"field": "ito1_uf_so_sn", "description": "公司间调拨销售订单号", "type": "varchar"},
            {"field": "ito1_uf_dn_sn", "description": "公司间调拨交货单号", "type": "varchar"},
            {"field": "ito1_uf_dn_doc", "description": "公司间调拨交货单过账凭证", "type": "varchar"},
            {"field": "ito1_uf_picking_document", "description": "公司间调拨交货拣配单号", "type": "varchar"},
            {"field": "ito1_uf_po_doc", "description": "公司间调拨采购过账凭证", "type": "varchar"},
            {"field": "ito1_uf_year", "description": "公司间调拨过账年度", "type": "varchar"},
            {"field": "ito1_uf_status", "description": "公司间调拨状态", "type": "varchar"},
            {"field": "ito1_uf_msg", "description": "公司间调拨单消息", "type": "varchar"},
        ]

    elif uf_bs_category == '30' or uf_bs_category == '32' or uf_bs_category == '34':
        display = [
            {"field": "type", "description": "执行结果", "type": "varchar", "length": 20, "decimal": 0},
            {"field": "msg", "description": "消息文本", "type": "varchar", "length": 200, "decimal": 0},
            {"field": "uf_guid", "description": "GUID", "type": "varchar"},
            {"field": "uf_bs_category", "description": "业务类别", "type": "varchar"},
            {"field": "uf_posting_date", "description": "过账日期", "type": "date"},
            {"field": "uf_posting_time", "description": "过账时间", "type": "datetime"},
            {"field": "uf_dn_sn", "description": "销售交货单号", "type": "varchar"},
            {"field": "uf_mat_doc_sn", "description": "冲销销售交货单凭证", "type": "varchar"},
            {"field": "uf_sto_po_mat_doc_sn1", "description": "冲销公司间采购收货凭证1", "type": "varchar"},
            {"field": "uf_sto_dn_mat_doc_sn1", "description": "冲销公司间采购收货凭证1", "type": "varchar"},
            {"field": "uf_sto_po_mat_doc_sn2", "description": "冲销公司间采购收货凭证2", "type": "varchar"},
            {"field": "uf_sto_dn_mat_doc_sn2", "description": "冲销公司间采购收货凭证2", "type": "varchar"},
        ]

    elif uf_bs_category == '38':
        display = [
            {"field": "type", "description": "执行结果", "type": "varchar", "length": 20, "decimal": 0},
            {"field": "msg", "description": "消息文本", "type": "varchar", "length": 200, "decimal": 0},
            {"field": "uf_guid", "description": "GUID", "type": "varchar"},
            {"field": "uf_bs_category", "description": "业务类别", "type": "varchar"},
            {"field": "uf_posting_date", "description": "过账日期", "type": "date"},
            {"field": "uf_posting_time", "description": "过账时间", "type": "datetime"},
            {"field": "uf_ito_sn", "description": "调拨单号", "type": "varchar"},
            {"field": "uf_po_sn", "description": "调拨采购订单号", "type": "varchar"},
            {"field": "uf_so_sn", "description": "调拨销售订单号", "type": "varchar"},
            {"field": "uf_dn_sn", "description": "调拨销售交货单号", "type": "varchar"},
            {"field": "uf_picking_document", "description": "拣配单号", "type": "varchar"},
            {"field": "uf_dn_doc", "description": "调拨交货过账凭证", "type": "varchar"},
            {"field": "uf_po_doc", "description": "调拨采购过账凭证", "type": "varchar"},
            {"field": "uf_off_sto_po_doc", "description": "冲销公司间采购收货凭证", "type": "varchar"},
            {"field": "uf_off_sto_dn_doc", "description": "冲销公司间销售发货凭证", "type": "varchar"},
        ]
    else:
        display = [
            
            {"field": "type", "description": "执行结果", "type": "varchar", "length": 20, "decimal": 0},
            {"field": "msg", "description": "消息文本", "type": "varchar", "length": 200, "decimal": 0},
            {"field": "uf_dn_sn", "description": "交货单号", "type": "varchar", "length": 18, "decimal": 0},
            {"field": "uf_dn_item", "description": "交货单行号", "type": "tinyint", "length": 0, "decimal": 0},
            {"field": "uf_dn", "description": "交货", "type": "varchar", "length": 20, "decimal": 0},
            {"field": "uf_dn_project", "description": "交货项目", "type": "tinyint", "length": 0, "decimal": 0},
            {"field": "uf_batch_item_id", "description": "批次行id", "type": "tinyint", "length": 0, "decimal": 0},
            {"field": "uf_po_doc", "description": "采购凭证", "type": "varchar", "length": 20, "decimal": 0},
            {"field": "uf_po_doc_item", "description": "采购凭证项目", "type": "tinyint", "length": 0, "decimal": 0},
            {"field": "uf_guid", "description": "GUID", "type": "varchar", "length": 50, "decimal": 0},
            {"field": "uf_update_order_qty_flag", "description": "更新订单数量标记", "type": "tinyint", "length": 0, "decimal": 0},
            {"field": "uf_update_second_order_flag", "description": "更新二级订单标记", "type": "tinyint", "length": 0, "decimal": 0},
            {"field": "uf_picking_date", "description": "拣配日期", "type": "date", "length": 0, "decimal": 0},
            {"field": "uf_posting_date", "description": "过账日期", "type": "date", "length": 0, "decimal": 0},
            {"field": "uf_sales_doc", "description": "销售凭证", "type": "varchar", "length": 20, "decimal": 0},
            {"field": "uf_sales_doc_item", "description": "销售凭证项目", "type": "tinyint", "length": 0, "decimal": 0},
            {"field": "uf_order_qty", "description": "订单数量", "type": "decimal", "length": 16, "decimal": 3},
            {"field": "uf_sales_unit", "description": "销售单位", "type": "varchar", "length": 3, "decimal": 0},
            {"field": "uf_mat_code", "description": "物料编码", "type": "varchar", "length": 40, "decimal": 0},
            {"field": "uf_price_ref_mat", "description": "定价参考物料", "type": "varchar", "length": 40, "decimal": 0},
            {"field": "uf_stor_loc_code", "description": "库位", "type": "varchar", "length": 50, "decimal": 0},
            {"field": "uf_creation_date", "description": "创建日期", "type": "date", "length": 0, "decimal": 0},
            {"field": "uf_plant", "description": "工厂", "type": "varchar", "length": 6, "decimal": 0},
            {"field": "uf_storage_loc", "description": "存储地点", "type": "varchar", "length": 6, "decimal": 0},
            {"field": "uf_split_flag", "description": "订单拆批标识", "type": "tinyint", "length": 0, "decimal": 0},
            {"field": "uf_picked_qty", "description": "拣配数量", "type": "decimal", "length": 16, "decimal": 3},
            {"field": "uf_sales_unit2", "description": "销售单位2", "type": "varchar", "length": 3, "decimal": 0},
            {"field": "uf_qty", "description": "数量", "type": "decimal", "length": 16, "decimal": 3},
            {"field": "uf_base_unit", "description": "基本单位", "type": "varchar", "length": 3, "decimal": 0},
            {"field": "uf_batch", "description": "批次", "type": "varchar", "length": 20, "decimal": 0},
            {"field": "uf_order_type", "description": "订单类型", "type": "varchar", "length": 6, "decimal": 0},
            {"field": "uf_supplier", "description": "供应商", "type": "varchar", "length": 20, "decimal": 0},
            {"field": "uf_purch_org", "description": "采购组织", "type": "varchar", "length": 6, "decimal": 0},
            {"field": "uf_purch_group", "description": "采购组", "type": "varchar", "length": 6, "decimal": 0},
            {"field": "uf_company_code", "description": "公司代码", "type": "varchar", "length": 6, "decimal": 0},
            {"field": "uf_return_reason", "description": "退货原因", "type": "varchar", "length": 6, "decimal": 0},
            {"field": "uf_plant2", "description": "工厂2", "type": "varchar", "length": 6, "decimal": 0},
            {"field": "uf_storage_loc2", "description": "存储地点2", "type": "varchar", "length": 6, "decimal": 0},
            {"field": "uf_return_item", "description": "退货项目", "type": "varchar", "length": 6, "decimal": 0},
            {"field": "uf_valuation_type", "description": "评估类型", "type": "varchar", "length": 6, "decimal": 0},
            {"field": "uf_delivery_date", "description": "交货日期", "type": "date", "length": 0, "decimal": 0},
            {"field": "uf_tax_code", "description": "税码", "type": "varchar", "length": 3, "decimal": 0},
            {"field": "uf_condition_type", "description": "条件类型", "type": "varchar", "length": 6, "decimal": 0},
            {"field": "uf_amount", "description": "金额", "type": "decimal", "length": 16, "decimal": 2},
            {"field": "uf_amount2", "description": "金额2", "type": "decimal", "length": 16, "decimal": 2},
            {"field": "uf_currency", "description": "货币", "type": "varchar", "length": 3, "decimal": 0},
            {"field": "uf_pricing_unit", "description": "定价单位", "type": "varchar", "length": 3, "decimal": 0},
            {"field": "uf_second_order_modify", "description": "二级订单修改", "type": "tinyint", "length": 0, "decimal": 0},
            {"field": "uf_new_sales_order_item", "description": "新增销售订单行", "type": "tinyint", "length": 0, "decimal": 0},
            {"field": "uf_dn_sn2", "description": "交货单号", "type": "varchar", "length": 20, "decimal": 0},
            {"field": "uf_dn_item2_dup", "description": "交货单行号", "type": "tinyint", "length": 0, "decimal": 0},
            {"field": "uf_dn_picking", "description": "交货单拣配", "type": "varchar", "length": 20, "decimal": 0},
            {"field": "uf_dn_posting", "description": "交货单过账", "type": "varchar", "length": 20, "decimal": 0},
            {"field": "uf_company_po", "description": "公司间采购订单号", "type": "varchar", "length": 20, "decimal": 0},
            {"field": "uf_company_dn", "description": "公司间交货单号", "type": "varchar", "length": 20, "decimal": 0},
            {"field": "uf_company_dn_picking", "description": "公司间交货单拣配", "type": "varchar", "length": 20, "decimal": 0},
            {"field": "uf_company_dn_posting", "description": "公司间交货单过账", "type": "varchar", "length": 20, "decimal": 0},
            {"field": "uf_company_gr", "description": "公司间采购收货", "type": "varchar", "length": 20, "decimal": 0},
            {"field": "uf_posting_status", "description": "过账状态", "type": "varchar", "length": 2, "decimal": 0},
            {"field": "uf_error_msg", "description": "报错信息", "type": "varchar", "length": 200, "decimal": 0},
            {"field": "create_id", "description": "创建人", "type": "int", "length": 0, "decimal": 0},
            {"field": "create_time", "description": "创建时间", "type": "datetime", "length": 0, "decimal": 0},
            {"field": "update_id", "description": "更新人", "type": "int", "length": 0, "decimal": 0},
            {"field": "update_time", "description": "更改时间", "type": "datetime", "length": 0, "decimal": 0},
            {"field": "note", "description": "备注", "type": "varchar", "length": 255, "decimal": 0},
        ]
    return display


def query(body):
    db = DbHelper()
    use_limit_sql = body.get("use_limit_sql", False)
    param = body.get("_payload_", {})
    prefix_filter = body.get("data", {})
    filter_info = param.get("filter_info", {})
    sort_info = param.get("sort_info", {})
    head = {}
    uf_bs_category = prefix_filter.get('uf_bs_category')
    posting_status = prefix_filter.get('posting_status', [])
    uf_posting_date = prefix_filter.get('uf_posting_date', [])

    if posting_status:
        del prefix_filter['posting_status']

    if uf_bs_category in ('30', '32', '34', '38'):
        uf_posting_status = [POST_STATUS_MAP[x] for x in posting_status]
        prefix_filter['uf_posting_status'] = uf_posting_status

    columns_query = """
    h.uf_guid,
    h.uf_bs_category,
    h.uf_posting_date,
    h.uf_dn_sn,
    h.uf_ito_sn
    """
    table_alias = create_table_alias(columns_query)
    where_sql, sort_sql = generate_raw_sql(
        prefix_filter, filter_info, sort_info, table_alias
    )

    query_sql = ''
    if uf_bs_category == '29' or uf_bs_category == '31':
        # 交货单接口数据
        query_sql = f"""
                select 
                h.*,
                h.uf_bs_category as a,
                t.*,
                -- t.uf_filed_code1 as uft_filed_code1,
                -- t.uf_filed_code2 as uft_filed_code2,
                -- t.uf_filed_code3 as uft_filed_code3,
                lth.uf_mat_doc_sn as lth_uf_mat_doc_sn,
                lth.uf_msg as lth_uf_msg,
                lth.id as lthid,
                lth.uf_reversal_mark as lth_uf_reversal_mark,
                lth.uf_posting_date as lth_uf_posting_date,
                lt.uf_doc_sn1,
                lt.uf_doc_sn2,
                ito1.uf_ito_sn as ito1_uf_ito_sn,
                ito1.uf_po_sn as ito1_uf_po_sn,
                ito1.uf_so_sn as ito1_uf_so_sn,
                ito1.uf_dn_sn as ito1_uf_dn_sn,
                ito1.uf_dn_doc as ito1_uf_dn_doc,
                ito1.uf_picking_document as ito1_uf_picking_document,
                ito1.uf_po_doc as ito1_uf_po_doc,
                ito1.uf_year as ito1_uf_year,
                ito1.uf_status as ito1_uf_status,
                ito1.uf_msg as ito1_uf_msg,
                ito2.uf_ito_sn as ito2_uf_ito_sn,
                ito2.uf_po_sn as ito2_uf_po_sn,
                ito2.uf_so_sn as ito2_uf_so_sn,
                ito2.uf_dn_sn as ito2_uf_dn_sn,
                ito2.uf_dn_doc as ito2_uf_dn_doc,
                ito2.uf_picking_document as ito2_uf_picking_document,
                ito2.uf_po_doc as ito2_uf_po_doc,
                ito2.uf_year as ito2_uf_year,
                ito2.uf_status as ito2_uf_status,
                ito2.uf_msg as ito2_uf_msg
                from 
                ut_delivery_post_Interface_head as h
                left join ut_delivery_post_Interface_data as t
                on h.uf_guid = t.uf_guid
                left join ut_delivery_post_step_log as lth 
                on lth.uf_guid = t.uf_guid 
                left join ut_delivery_post_step_log_item as lt 
                on lt.uf_guid = t.uf_guid 
                -- and  lt.uf_line_id = t.uf_line_id 
                left join ut_ito_post_step_log as ito1 
                on  lt.uf_doc_sn1 = ito1.uf_ito_sn 
                    and ito1.uf_ito_sn  != ''
                left join ut_ito_post_step_log as ito2
                on  lt.uf_doc_sn2 = ito2.uf_ito_sn  
                    and ito2.uf_ito_sn  != ''
                {where_sql}
                 """

    elif uf_bs_category == '37':
        # 调拨单接口数据
        query_sql = f"""
                select 
                h.*,
                h.uf_bs_category as a,
                t.*,
                ito1.uf_ito_sn as ito1_uf_ito_sn,
                ito1.uf_po_sn as ito1_uf_po_sn,
                ito1.uf_so_sn as ito1_uf_so_sn,
                ito1.uf_dn_sn as ito1_uf_dn_sn,
                ito1.uf_dn_doc as ito1_uf_dn_doc,
                ito1.uf_picking_document as ito1_uf_picking_document,
                ito1.uf_po_doc as ito1_uf_po_doc,
                ito1.uf_year as ito1_uf_year,
                ito1.uf_status as ito1_uf_status,
                ito1.uf_msg as ito1_uf_msg
                from 
                ut_ito_post_Interface_head as h
                left join ut_ito_post_Interface_data as t
                on h.uf_guid = t.uf_guid
                left join ut_ito_post_step_log as ito1 
                on   h.uf_guid = ito1.uf_guid  
                {where_sql}
                 """

    elif uf_bs_category == '30' or uf_bs_category == '32' or uf_bs_category == '34':
        query_sql = f"""
        SELECT
            h.uf_guid,
            h.uf_bs_category,
            h.uf_posting_date,
            h.uf_posting_time,
            h.uf_dn_sn,
            l.uf_mat_doc_sn,
            l.uf_sto_po_mat_doc_sn1,
            l.uf_sto_dn_mat_doc_sn1,
            l.uf_sto_po_mat_doc_sn2,
            l.uf_sto_dn_mat_doc_sn2
        FROM
            ut_delivery_post_Interface_head AS h 
        LEFT JOIN ut_dn_reversal_process_log AS l ON h.uf_guid = l.uf_guid
        {where_sql}
        """

    elif uf_bs_category == '38':
        query_sql = f"""
        SELECT
            h.uf_guid,
            h.uf_bs_category,
            h.uf_ito_sn,
            h.uf_posting_date,
            h.uf_posting_time,
            l.uf_po_sn,
            l.uf_so_sn,
            l.uf_dn_sn,
            l.uf_picking_document,
            l.uf_dn_doc,
            l.uf_po_doc,
            '' as uf_off_sto_po_doc,
            '' as uf_off_sto_dn_doc
        FROM ut_ito_post_Interface_head AS h
        JOIN ut_ito_post_step_log AS l ON (h.uf_ito_sn = l.uf_ito_sn AND l.uf_status = 'C' AND l.uf_reversal_mark = 0)
        {where_sql}
        """
    else:
        query_sql = """
        SELECT 
        uf_dn_sn,
        uf_dn_item,
        uf_dn,
        uf_dn_project,
        uf_batch_item_id,
        uf_po_doc,
        uf_po_doc_item,
        uf_guid,
        uf_update_order_qty_flag,
        uf_update_second_order_flag,
        uf_picking_date,
        uf_posting_date,
        uf_sales_doc,
        uf_sales_doc_item,
        uf_order_qty,
        uf_sales_unit,
        uf_mat_code,
        uf_price_ref_mat,
        uf_stor_loc_code,
        uf_creation_date,
        uf_plant,
        uf_storage_loc,
        uf_split_flag,
        uf_picked_qty,
        uf_sales_unit2,
        uf_qty,
        uf_base_unit,
        uf_batch,
        uf_order_type,
        uf_supplier,
        uf_purch_org,
        uf_purch_group,
        uf_company_code,
        uf_return_reason,
        uf_plant2,
        uf_storage_loc2,
        uf_return_item,
        uf_valuation_type,
        uf_delivery_date,
        uf_tax_code,
        uf_condition_type,
        uf_amount,
        uf_amount2,
        uf_currency,
        uf_pricing_unit,
        uf_second_order_modify,
        uf_new_sales_order_item,
        uf_dn_sn2,
        uf_dn_item2_dup,
        uf_dn_picking,
        uf_dn_posting,
        uf_company_po,
        uf_company_dn,
        uf_company_dn_picking,
        uf_company_dn_posting,
        uf_company_gr,
        uf_posting_status,
        uf_error_msg,
        create_id,
        create_time,
        update_id,
        update_time
        FROM ut_delivery_post_Interface_data
        WHERE 1=1
        """
        # 处理过账状态过滤（支持多状态）
        if posting_status and isinstance(posting_status, list) and len(posting_status) > 0:
            status_mapping = {
                '1': None,  # 未过账
                '2': "S",  # 过账成功
                '3': "E"  # 过账失败
            }
            # 分离空状态和非空状态
            has_empty_status = False
            status_values = []
            for status in posting_status:
                mapped_value = status_mapping.get(str(status))
                if mapped_value is None:
                    has_empty_status = True
                elif mapped_value:
                    status_values.append(f"'{mapped_value}'")
            # 构建状态条件
            status_conditions = []
            if has_empty_status:
                status_conditions.append("(uf_posting_status IS NULL OR uf_posting_status = '')")
            if status_values:
                status_conditions.append(f"uf_posting_status IN ({','.join(status_values)})")
            if status_conditions:
                query_sql += " AND (" + " OR ".join(status_conditions) + ")"
        # 处理日期范围过滤
        if uf_posting_date and isinstance(uf_posting_date, list) and len(uf_posting_date) >= 2:
            start_date = uf_posting_date[0]
            end_date = uf_posting_date[1]
            if start_date:
                query_sql += f" AND uf_posting_date >= '{start_date}'"
            if end_date:
                query_sql += f" AND uf_posting_date <= '{end_date}'"
        
    print(query_sql)

    query_sql = query_sql.replace("    ", " ")

    page_size = param.get("page", {}).get("page_size")
    page_num = param.get("page", {}).get("page_num")
    if use_limit_sql:
        data_sum = get_total_count(query_sql)
        limit_sql = generate_limit_sql(page_size, page_num)
        last_query_sql = query_sql + limit_sql
        query_data = db.query_sql(last_query_sql)
        page_size = page_size if page_size else data_sum
        if page_size:
            total_pages = data_sum // page_size + (1 if data_sum % page_size > 0 else 0)
        else:
            total_pages = 0
    else:
        query_data = db.query_sql(query_sql)
        paginator = Paginator(query_data, page_size)
        total_pages = paginator.total_pages
        data_sum = len(query_data)

    if uf_bs_category == '37':
        for each in query_data:
            each['uf_bs_category'] = each['a']

        if '3' not in posting_status:
            query_data = [i for i in query_data if i['ito1_uf_po_doc'] != '' or i['ito1_uf_po_sn'] == '']
        if '2' not in posting_status:
            query_data = [i for i in query_data if i['ito1_uf_po_doc'] == '']
        if '1' not in posting_status:
            query_data = [i for i in query_data if i['ito1_uf_po_sn'] != '']

    elif uf_bs_category == '29':
        for each in query_data:
            each['uf_bs_category'] = each['a']

        if '3' not in posting_status:
            query_data = [i for i in query_data if i['lth_uf_mat_doc_sn'] != '' or i['lthid'] == 0]
        if '2' not in posting_status:
            query_data = [i for i in query_data if i['lth_uf_mat_doc_sn'] == '']
        if '1' not in posting_status:
            query_data = [i for i in query_data if i['lthid'] != 0]

    page = {
        "page_size": page_size if page_size else len(query_data),  # 每页数据行数
        "page_num": page_num,  # 当前页
        "page_sum": total_pages,  # 总页数
        "data_sum": data_sum,  # 总数据行数
    }

    display = getdisplay(uf_bs_category)
    print('display-----', display)
    print('query_data-----', query_data)
    print('page-----', page) 
    print('filter_info-----', filter_info)
    print('sort_info-----', sort_info)
    print('head-----', head)
    return query_data, head, page, filter_info, sort_info, display


def deliveryInterfaceQuery():
    print('进入接口')
    logger.printInfo("进入接口", {})
    """交货单/调拨单接口数据查询"""
    res = Response()
    req = Request()
    body = json.loads(req.body())
    code,msg = 0,''
    head = {}
    data = []
    page = {}
    sort_info = {}
    filter_info = {}
    display = []
    prefix_filter = body.get("data", {})
    uf_bs_category = prefix_filter.get('uf_bs_category')
    print('body-----', body)
    print('-------------',body.get('target_script'))
    if uf_bs_category not in ("29","31","37","30","32","34","38"):
        msg = '无符合条件数据'
        code = 500
    if body.get('target_script') == 'Z_post_emes_data_SD':
        msg = '成功'
        code = 200
        data, head, page, filter_info, sort_info, display = query(body)
    response = {
        "code": code,
        "msg": msg,
        "head": head,
        "data": data,
        "page": page,
        "rule": {"sort_info": sort_info, "filter_info": filter_info},
        "display": display
    }
    print('response-----', response)
    param = body.get("_payload_", {})
    if not param.get("export_excel"):
        res.set_body(json.dumps(response))
    else:
        format_data = [{"sheet1": data}]
        GetExportData(format_data, "接口数据查询结果.xlsx", display_to_entozh(display))



def post_data():
    res = Response()
    req = Request()
    body = json.loads(req.body())
    print('入参', body)
    user_id = req.header("user_id")
    data = body.get("data")
    # 传入多个交货单/调拨单数据，根据uf_dn_sn分组

    # 走完自己的过账逻辑
    converted_payloads = convert_and_process_file_payload(data,user_id)
    key_list = list(converted_payloads.keys())

    result_data = []
    for index,item in enumerate(data):
        print('item-----', index,item)
        if str((index + 1)) in key_list:
            type = converted_payloads[str(index +1)].get('type')
            if type == 'E':
                item['type'] = 'E'
                item['msg'] = converted_payloads[str(index +1)].get('message')
            else:
                item['type'] = 'S'
                item['msg'] = "过账成功"
        result_data.append(item)

    print('result_data-----', result_data)
    res.set_body(json.dumps({"code": 200, "msg": "过账完成", "data": result_data}))
    res.commit(True)


    # if converted_payloads['type'] == 'E':
    #     res.set_body(json.dumps({"code": 500, "msg": converted_payloads['message'],"data":result_data}))
    #     res.commit(True)

    # else:
    #     res.set_body(json.dumps({"code": 200, "msg": converted_payloads['message'], "data": result_data}))
    #     res.commit(True)



# 检查过账前数据是否符合要求
def check_converted_payloads(item):
    # ============== 错误带上 uf_ito_sn + uf_ito_items ==============
    item_no = item.get('uf_ito_items', '未知行')
    sn = item.get('uf_ito_sn', '未知单号')
    # 检查参数 物料编码uf_mat_code/交货单号uf_dn_sn/交货行号uf_dn_item/公司编码uf_plant/仓库位置uf_storage_loc
    if not item.get('uf_mat_code', ''):
        return {
            "type": "E",
            "message": f"调拨单[{sn}] 行项目[{item_no}]：物料编码不能为空"
        }
    if not item.get('uf_dn_sn', ''):
        return {
            "type": "E",
            "message": f"调拨单[{sn}] 行项目[{item_no}]：交货单号不能为空"
        }
    if not item.get('uf_dn_item', ''):
        return {
            "type": "E",
            "message": f"调拨单[{sn}] 行项目[{item_no}]：交货行号不能为空"
        }
    if not item.get('uf_plant', ''):
        return {
            "type": "E",
            "message": f"调拨单[{sn}] 行项目[{item_no}]：公司编码不能为空"
        }
    if not item.get('uf_storage_loc', ''):
        return {
            "type": "E",
            "message": f"调拨单[{sn}] 行项目[{item_no}]：仓库位置不能为空"
        }

    # 检查是否已过账
    if item.get('uf_posting_status') == 'S':
        return {
            "type": "E",
            "message": "数据已过账，不能重复过账"
        }
    return {
        "type": "S",
        "message": "数据符合要求"
    }

def convert_and_process_file_payload(payload,user_id):
    item_group = {}
    for item in payload:
        ito_sn = item.get('uf_dn_sn', '')
        if not ito_sn:
            continue
        if ito_sn not in item_group:
            item_group[ito_sn] = []
        item_group[ito_sn].append(item)

    # 生成最终标准结构
    converted_payloads = []
    print("items:---",item_group)
    line_id = 1
    for ito_sn, items in item_group.items():
        # 每个交货单生成独立 GUID
        guid = str(uuid.uuid4())
        posting_date = ""
        posting_time = ""
        processed_items = []
        # 行号从 1 开始自增
        print("items:---",items)
        for row in items:
            # 复制一份，避免修改原数据
            new_row = row.copy()
            # 1. 生成自增 line_id
            new_row['line_id'] = line_id
            line_id += 1
            processed_items.append(new_row)
        new_data = {
            "guid": guid,
            "data": {
                "header": [
                    {
                        "item": processed_items,
                        "uf_bs_category": "29",        # 固定值
                        "uf_guid": guid,
                        "uf_ito_sn": ito_sn,
                        "uf_posting_date": posting_date,
                        "uf_posting_time": posting_time,
                        "uf_tracking_number": ""
                    }
                ]
            }
        }
        converted_payloads.append(new_data)


    print('最终converted_payloads===---', converted_payloads)
    # ===================== 循环处理每个转换后的payload =====================
    if len(converted_payloads) <= 0 :
        return {
            "code": 500,
            "type": "E",
            "message": "没有符合条件数据"
        }
    ret = {}
    for c_pay in converted_payloads:
        # 构建前先查询数据库，判断是否已过账等
        check_result = check_converted_payloads(c_pay.get('data').get("header")[0].get("item")[0])
        if check_result['type'] == 'E':
            print('数据有误-------------------',check_result.get('message',''))
        else:
            # 构建过账数据
            check_result = post_data_execute(c_pay.get('data'), user_id)
            print('post_result-----------', check_result)
            if check_result['type'] == 'E':
                print('过账失败-------------------',check_result.get('message',''))
        print('c_pay-----------', c_pay)
        print('post_result-----------', check_result)
        line_id = c_pay['data']['header'][0]['item'][0]['line_id']
        ret[str(line_id)] = check_result
    print('ret-----------', ret)
    return ret



def post_data_execute(data, user_id):
    ret = build_post_params(data, user_id)
    doc_head = ret['data']['doc_head']
    doc_items = ret['data']['doc_items']
        # 调用过账接口
    post_result = execute_post(doc_head, doc_items, data.get('guid',''), user_id)

    if post_result['type'] == 'E':
        return post_result
    else:
        item = data.get("header")[0].get("item")[0]
        print('item-----------', item)
        # 更新数据库，数据uf_posting_status为已过账
        db = DbHelper()
        updateSql = f"""
        update ut_delivery_post_Interface_data
        set uf_posting_status = 'S'
        where uf_dn_sn = '{item.get('uf_dn_sn','')}' and uf_dn_item = '{item.get('uf_dn_item','')}'
        """
        status = db.exec_sql(updateSql, True)
        print('C底层返回的status', status)
        return {
            "type": "S",
        }



def sd_post_data_execute(data, user_id, dict_head=None):
    db = DbHelper()
    uf_bs_category = ''
    guid_set = set()
    for row in data:
        uf_bs_category = row.get('uf_bs_category','')
        if not uf_bs_category:
            continue
        guid_set.add(row.get('uf_guid',''))
    lst_guid = list(guid_set)
    if uf_bs_category == '29':
        dn_header_sql = """
        select
        `dn_sn`,
        `process_order_number`
        from
        `t_dn_header`
        """
        dn_header_data = db.query_sql(dn_header_sql)

        dn_header_data_dic = {i['dn_sn']: i['process_order_number'] for i in dn_header_data}
        dn_header_data_rev_dic = {i['process_order_number']: i['dn_sn'] for i in dn_header_data}

        for element in lst_guid:
            sql_item = f"""
            select * from ut_delivery_post_Interface_data 
            where uf_guid = '{element}'
                """
            data_item = db.query_sql(sql_item)
            print('接口调用入参',data_item)
            posting_date = data_item[0]['uf_posting_date']

            uf_tracking_number = ''
            # 根据接口传的交货单号 = t_dn_header - dn_sn作为销售交货单号；
            # 若找不到，则根据接口传的交货单号 = t_dn_header - process_order_number，取对应的dn_sn作为销售交货单号。
            uf_dn_sn = data_item[0]['uf_dn_sn']
            if uf_dn_sn:
                if uf_dn_sn not in dn_header_data_dic.keys():

                    if uf_dn_sn in dn_header_data_rev_dic.keys():

                        uf_dn_sn = dn_header_data_rev_dic[uf_dn_sn]
            picksn_lst = [ i['uf_picking_document'] for i in data_item if i['uf_picking_document'] != '']

            pick_data = []
            dick_pick = {}
            if picksn_lst:
                pick_sql = """
                select * from t_dn_inventory_alloc where picking_document  in ({})
                """.format(','.join([ f"'{i}'" for i in picksn_lst ]))
                pick_data = db.query_sql(pick_sql)
                for i in pick_data:
                    key = str(i['dn_sn'])
                    if key in dick_pick:
                        dick_pick[key].append(i)
                    else:
                        dick_pick[key] = []
                        dick_pick[key].append(i)
            prarm_item = []
            if pick_data:
                key = str(data_item[0]['uf_dn_sn'])
                if key in dick_pick:
                    for row in dick_pick[key]:
                        dict_temp = copy.deepcopy(data_item[0])
                        dict_temp['uf_dn_item'] = row['dn_item']
                        dict_temp['uf_picking_document'] = row['picking_document']
                        dict_temp['uf_batch_item'] = row['batch_item']
                        dict_temp['uf_mat_code'] = row['mat_code']
                        dict_temp['uf_stor_loc_code'] = row['stor_loc_code']
                        dict_temp['uf_picked_qty'] = row['picked_qty']
                        dict_temp['uf_picked_base_qty'] = row['picked_base_qty']
                        dict_temp['uf_picked_parallel_qty'] = row['picked_parallel_qty']
                        dict_temp['uf_batch_sn'] = row['batch_sn']
                        dict_temp['virtual_tracking_number'] = ''
                        prarm_item.append(dict_temp)
                    data_item = prarm_item
            else:               
                for row in data_item:
                    row['virtual_tracking_number'] = ''


            for row in data_item:
                row['virtual_tracking_number'] = ''
                row['uf_dn_sn'] = uf_dn_sn
            print('接口调用入参',data_item, posting_date, uf_tracking_number, element, user_id)
            ret = delivery_post_main(data_item, posting_date, uf_tracking_number, element, user_id)
            return_data = []
            if ret['type'] == 'S':
                sql = f"""
                select 
                h.uf_guid,
                t.uf_line_id,
                t.uf_batch_line,
                lth.uf_mat_doc_sn as lth_uf_mat_doc_sn,
                lth.uf_msg as lth_uf_msg,
                lth.id as lthid,
                lth.uf_reversal_mark as lth_uf_reversal_mark,
                lth.uf_posting_date as lth_uf_posting_date,
                lt.uf_doc_sn1,
                lt.uf_doc_sn2,
                ito1.uf_ito_sn as ito1_uf_ito_sn,
                ito1.uf_po_sn as ito1_uf_po_sn,
                ito1.uf_so_sn as ito1_uf_so_sn,
                ito1.uf_dn_sn as ito1_uf_dn_sn,
                ito1.uf_dn_doc as ito1_uf_dn_doc,
                ito1.uf_picking_document as ito1_uf_picking_document,
                ito1.uf_po_doc as ito1_uf_po_doc,
                ito1.uf_year as ito1_uf_year,
                ito1.uf_status as ito1_uf_status,
                ito1.uf_msg as ito1_uf_msg,
                ito2.uf_ito_sn as ito2_uf_ito_sn,
                ito2.uf_po_sn as ito2_uf_po_sn,
                ito2.uf_so_sn as ito2_uf_so_sn,
                ito2.uf_dn_sn as ito2_uf_dn_sn,
                ito2.uf_dn_doc as ito2_uf_dn_doc,
                ito2.uf_picking_document as ito2_uf_picking_document,
                ito2.uf_po_doc as ito2_uf_po_doc,
                ito2.uf_year as ito2_uf_year,
                ito2.uf_status as ito2_uf_status,
                ito2.uf_msg as ito2_uf_msg
                from 
                ut_delivery_post_Interface_head as h
                left join ut_delivery_post_Interface_data as t
                on h.uf_guid = t.uf_guid
                left join ut_delivery_post_step_log as lth 
                on lth.uf_guid = t.uf_guid 
                left join ut_delivery_post_step_log_item as lt 
                on lt.uf_guid = t.uf_guid 
                and  lt.uf_line_id = t.uf_line_id 
                left join ut_ito_post_step_log as ito1 
                on  lt.uf_doc_sn1 = ito1.uf_ito_sn 
                    and ito1.uf_ito_sn  != ''
                left join ut_ito_post_step_log as ito2
                on  lt.uf_doc_sn2 = ito2.uf_ito_sn  
                    and ito2.uf_ito_sn  != ''
                WHERE h.uf_guid = '{element}'
                """
                return_data = db.query_sql(sql)
            for row in data:
                for i in return_data:
                    if row['uf_guid'] == element and row['uf_line_id'] == i['uf_line_id'] and row['uf_batch_line'] == i['uf_batch_line']:
                        row['lth_uf_mat_doc_sn'] = i['lth_uf_mat_doc_sn']
                        row['lth_uf_msg'] = i['lth_uf_msg']
                        row['ito1_uf_ito_sn'] = i['ito1_uf_ito_sn']
                        row['ito1_uf_msg'] = i['ito1_uf_msg']
                        row['ito2_uf_ito_sn'] = i['ito2_uf_ito_sn']
                        row['ito2_uf_msg'] = i['ito2_uf_msg']
                if row['uf_guid'] == element:
                    row['type'] = ret['type']
                    row['msg'] = ret['message']
                else:
                    continue
    elif uf_bs_category == '31':

        for element in lst_guid:
            sql_head = f"""
            select * from ut_delivery_post_Interface_head 
            where uf_guid = '{element}'
                """
            data_head = db.query_sql(sql_head)
            sql_item = f"""
            select * from ut_delivery_post_Interface_data 
            where uf_guid = '{element}'
                """
            data_item = db.query_sql(sql_item)

            posting_date = data_head[0]['uf_posting_date']
            uf_tracking_number = data_head[0]['uf_tracking_number']
            for row in data_item:
                row['virtual_tracking_number'] = data_head[0]['uf_virtual_tracking_number']
            # ret = delivery_post_main(data_item, posting_date, uf_tracking_number, element, user_id)
            ret = return_delivery_post_main(data_item,posting_date,uf_tracking_number,element, user_id)
            return_data = []
            if ret['type'] == 'S':
                sql = f"""
                select 
                h.uf_guid,
                t.uf_line_id,
                t.uf_batch_line,
                lth.uf_mat_doc_sn as lth_uf_mat_doc_sn,
                lth.uf_msg as lth_uf_msg,
                lth.id as lthid,
                lth.uf_reversal_mark as lth_uf_reversal_mark,
                lth.uf_posting_date as lth_uf_posting_date,
                lt.uf_doc_sn1,
                lt.uf_doc_sn2,
                ito1.uf_ito_sn as ito1_uf_ito_sn,
                ito1.uf_po_sn as ito1_uf_po_sn,
                ito1.uf_so_sn as ito1_uf_so_sn,
                ito1.uf_dn_sn as ito1_uf_dn_sn,
                ito1.uf_dn_doc as ito1_uf_dn_doc,
                ito1.uf_picking_document as ito1_uf_picking_document,
                ito1.uf_po_doc as ito1_uf_po_doc,
                ito1.uf_year as ito1_uf_year,
                ito1.uf_status as ito1_uf_status,
                ito1.uf_msg as ito1_uf_msg,
                ito2.uf_ito_sn as ito2_uf_ito_sn,
                ito2.uf_po_sn as ito2_uf_po_sn,
                ito2.uf_so_sn as ito2_uf_so_sn,
                ito2.uf_dn_sn as ito2_uf_dn_sn,
                ito2.uf_dn_doc as ito2_uf_dn_doc,
                ito2.uf_picking_document as ito2_uf_picking_document,
                ito2.uf_po_doc as ito2_uf_po_doc,
                ito2.uf_year as ito2_uf_year,
                ito2.uf_status as ito2_uf_status,
                ito2.uf_msg as ito2_uf_msg
                from 
                ut_delivery_post_Interface_head as h
                left join ut_delivery_post_Interface_data as t
                on h.uf_guid = t.uf_guid
                left join ut_delivery_post_step_log as lth 
                on lth.uf_guid = t.uf_guid 
                left join ut_delivery_post_step_log_item as lt 
                on lt.uf_guid = t.uf_guid 
                and  lt.uf_line_id = t.uf_line_id 
                left join ut_ito_post_step_log as ito1 
                on  lt.uf_doc_sn1 = ito1.uf_ito_sn 
                    and ito1.uf_ito_sn  != ''
                left join ut_ito_post_step_log as ito2
                on  lt.uf_doc_sn2 = ito2.uf_ito_sn  
                    and ito2.uf_ito_sn  != ''
                WHERE h.uf_guid = '{element}'
                """
                return_data = db.query_sql(sql)
            for row in data:
                for i in return_data:
                    if row['uf_guid'] == element and row['uf_line_id'] == i['uf_line_id'] and row['uf_batch_line'] == i['uf_batch_line']:
                        row['lth_uf_mat_doc_sn'] = i['lth_uf_mat_doc_sn']
                        row['lth_uf_msg'] = i['lth_uf_msg']
                        row['ito1_uf_ito_sn'] = i['ito1_uf_ito_sn']
                        row['ito1_uf_msg'] = i['ito1_uf_msg']
                        row['ito2_uf_ito_sn'] = i['ito2_uf_ito_sn']
                        row['ito2_uf_msg'] = i['ito2_uf_msg']
                if row['uf_guid'] == element:
                    row['type'] = ret['type']
                    row['msg'] = ret['message']
                else:
                    continue
    elif uf_bs_category == '37':
        for element in lst_guid:
            sql_item = f"""
            select * from ut_ito_post_Interface_data 
            where uf_guid = '{element}'
                """
            data_item = db.query_sql(sql_item)

            sql_h = f"""
            select * from ut_ito_post_Interface_head  
            where uf_guid = '{element}'
                """
            data_head = db.query_sql(sql_h)

            ito_sn = data_item[0]['uf_ito_sn']

            ito_data = []
            ito_pick = {}
            if ito_sn:
                pick_sql = """
                select * from ut_intercompany_transaction_order_item
            where uf_ito_sn  = '{}'  and uf_deleted_mark != 1  and uf_batch_sn != ''
                """.format(ito_sn)
                ito_data = db.query_sql(pick_sql)
                for i in ito_data:
                    key = str(i['uf_ito_sn'])
                    if key in ito_pick:
                        ito_pick[key].append(i)
                    else:
                        ito_pick[key] = []
                        ito_pick[key].append(i)
            prarm_item = []
            key = str(ito_sn)
            if key in ito_pick:
                for row in ito_pick[key]:
                    dict_temp=row.copy()
                    print(dict_temp,'dict_temp----')
                    dict_temp['uf_posting_date'] = data_head[0]['uf_posting_date']
                    dict_temp['uf_tracking_number'] = data_head[0]['uf_tracking_number']
                    dict_temp['uf_stor_loc_code'] = dict_temp['uf_from_stor_loc_code']
                    dict_temp['uf_qty'] = dict_temp['uf_transaction_qty']
                    # temp['mat_code'] = temp['uf_mat_code']
                    dict_temp['uf_mat_code'] = dict_temp['uf_ipn']
                    dict_temp['batch_sn'] = dict_temp['uf_batch_sn']
                    dict_temp['uf_batch_sn'] = dict_temp['uf_batch_sn']
                    prarm_item.append(dict_temp)
            else:
                prarm_item = data_item
            ret = ito_post_main(prarm_item, element, user_id)
            return_data = []
            if ret['type'] == 'S':
                sql = f"""
                select 
                h.uf_guid,
                t.uf_line_id,
                t.uf_batch_line,
                ito1.uf_ito_sn as ito1_uf_ito_sn,
                ito1.uf_po_sn as ito1_uf_po_sn,
                ito1.uf_so_sn as ito1_uf_so_sn,
                ito1.uf_dn_sn as ito1_uf_dn_sn,
                ito1.uf_dn_doc as ito1_uf_dn_doc,
                ito1.uf_picking_document as ito1_uf_picking_document,
                ito1.uf_po_doc as ito1_uf_po_doc,
                ito1.uf_year as ito1_uf_year,
                ito1.uf_status as ito1_uf_status,
                ito1.uf_msg as ito1_uf_msg
                from 
                ut_ito_post_Interface_head as h
                left join ut_ito_post_Interface_data as t
                on h.uf_guid = t.uf_guid
                left join ut_ito_post_step_log as ito1 
                on   h.uf_guid = ito1.uf_guid  
                WHERE h.uf_guid = '{element}'
                """
                return_data = db.query_sql(sql)
            for row in data:
                for i in return_data:
                    if row['uf_guid'] == element and row['uf_line_id'] == i['uf_line_id'] and row['uf_batch_line'] == i['uf_batch_line']:
                        row['ito1_uf_po_doc'] = i['ito1_uf_po_doc']
                        row['ito1_uf_msg'] = i['ito1_uf_msg']
                if row['uf_guid'] == element:
                    row['type'] = ret['type']
                    row['msg'] = ret['message']
                else:
                    continue
    elif uf_bs_category in ('30', '32', '34'):
        for item in data:
            guid = item['uf_guid']
            dn_sn = item['uf_dn_sn']
            posting_date = item['uf_posting_date']
            flag, msg = execute_reversal(dn_sn, posting_date)
            if not flag:
                item['type'] = '操作失败'
                item['msg'] = msg
            else:
                item['type'] = '操作成功'
                item['msg'] = ''
                sql = f"""
                SELECT
                    uf_mat_doc_sn,
                    uf_sto_po_mat_doc_sn1,
                    uf_sto_po_mat_doc_sn2,
                    uf_sto_dn_mat_doc_sn1,
                    uf_sto_dn_mat_doc_sn2
                FROM
                    ut_dn_reversal_process_log
                WHERE uf_guid = '{guid}'
                """
                ret = db.query_sql(sql, isNewDB=True)
                uf_mat_doc_sn = ret[0]['uf_mat_doc_sn']
                uf_sto_po_mat_doc_sn1 = ret[0]['uf_sto_po_mat_doc_sn1']
                uf_sto_po_mat_doc_sn2 = ret[0]['uf_sto_po_mat_doc_sn2']
                uf_sto_dn_mat_doc_sn1 = ret[0]['uf_sto_dn_mat_doc_sn1']
                uf_sto_dn_mat_doc_sn2 = ret[0]['uf_sto_dn_mat_doc_sn2']

                item['uf_mat_doc_sn'] = uf_mat_doc_sn
                item['uf_sto_po_mat_doc_sn1'] = uf_sto_po_mat_doc_sn1
                item['uf_sto_po_mat_doc_sn2'] = uf_sto_po_mat_doc_sn2
                item['uf_sto_dn_mat_doc_sn1'] = uf_sto_dn_mat_doc_sn1
                item['uf_sto_dn_mat_doc_sn2'] = uf_sto_dn_mat_doc_sn2
    elif uf_bs_category == '38':
        for item in data:
            ito_sn = item['uf_ito_sn']
            uf_po_sn = item['uf_po_sn']
            posting_date = item['uf_posting_date']

            flag, msg = execute_inner_company_reversal(ito_sn, uf_po_sn, posting_date)
            if not flag:
                item['type'] = '操作失败'
                item['msg'] = msg
            else:
                item['type'] = '操作成功'
                item['msg'] = ''

                sql = f"""
                SELECT
                    uf_off_sto_dn_doc,
                    uf_off_sto_po_doc
                FROM
                    ut_write_off_transfer_instructions_company
                WHERE
                    uf_ito_sn = '{ito_sn}' AND uf_sto_po_sn = '{uf_po_sn}'
                """
                ret = db.query_sql(sql, isNewDB=True)

                item['uf_off_sto_dn_doc'] = ret[0]['uf_off_sto_dn_doc']
                item['uf_off_sto_po_doc'] = ret[0]['uf_off_sto_po_doc']



def execute_post(doc_head, doc_items, guid, user_id):
    """
    执行库存过账
    """
    print('过账传入:', doc_head, doc_items)
    try:
        # 调用库存过账接口
        code, msg, error_list, mat_doc_sn, year = post_inventory_data('0', user_id, doc_head, doc_items)
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

# def build_post_params(header, user_id):
#     """
#     构建库存过账参数
#     """
#     db = DbHelper()
#     document_date = header.get("uf_document_date")
#     posting_date = header.get("uf_posting_date")
#     if document_date is None:
#         document_date = datetime.now().strftime("%Y-%m-%d")
#     if posting_date is None:
#         posting_date = datetime.now().strftime("%Y-%m-%d")
#     # 构建表头参数
#     doc_head = {
#         "document_category": "",           # 单据种类
#         "post_code": "3",                  # 过账代码：3=收料
#         "document_date": document_date,
#         "posting_date": posting_date,
#         "summary_unique_number": header.get("summary_unique_number",''),
#         "vendor_dn": header.get("vendor_dn",''),
#         "company_code": "",                # 从工厂获取公司代码
#         "remarks_1": "发货过账"
#     }
#     # 构建行项目参数
#     doc_items = []
#     line_id = 0
#     uf_guid = ""
#     header = header.get("header")[0]
#     for item in header.get("item"):
#         print("item----:",item)
#         line_id += 1
#         # 获取物料基本信息
#         mat_code = item.get("uf_mat_code")  # 物料代码
#         batch_sn = item.get("uf_batch_sn", "")  # 批次号
#         # 工厂公司代码一样，可以通用
#         plant_code = item.get("uf_plant")
#         uf_guid = item.get("uf_guid", "")
#         print("uf_guid:",uf_guid,mat_code,batch_sn,plant_code)


#         query_mat_sql = "SELECT basic_uom, parallel_uom,basic_uom FROM t_mmd_material_basic_data WHERE mat_code = {} ".format(repr(mat_code))
#         mat_info = db.query_sql(query_mat_sql)
#         basic_uom = mat_info[0]['basic_uom'] if mat_info else item['transaction_uom']
#         parallel_uom = mat_info[0]['parallel_uom'] if mat_info else ''
#         print("获取物料基本信息成功：",mat_info)

#         # 获取工厂对应的公司代码
#         query_plant_sql = "SELECT company_code FROM t_os_company_plant_alloc WHERE plant_code = {} ".format(repr(plant_code))
#         plant_info = db.query_sql(query_plant_sql)
#         if plant_info:
#             doc_head['company_code'] = plant_info[0]['company_code']
#         print("获取工厂对应的公司代码成功：",plant_info)


#         if not item.get("uf_picked_qty"):
#             uf_parallel_qty = 0
#         else:
#             uf_parallel_qty = float(item["uf_picked_qty"])

#         print("uf_parallel_qty:",uf_parallel_qty)
#         # 构建批次信息
#         batch_number, batch_sn = build_batch_number(mat_code,uf_parallel_qty, batch_sn, db)
#         # 添加动态批次属性 item 字段
#         print("构建批次信息成功:",batch_number, batch_sn)
#         doc_item = {
#             "line_id": line_id,
#             "movement_type": item.get("uf_movement_type", "D008"),
#             "plant_code": plant_code,
#             "stor_loc_code": item["uf_storage_loc"],
#             "mat_code": mat_code,
#             "batch_sn": batch_sn,
#             "inventory_status": item.get("inventory_status", "0"),
#             "special_inventory_status1": item.get("uf_special_inventory_status1", ""),
#             "special_inventory_status2": "",
#             "transaction_qty": uf_parallel_qty,  # 交易数量
#             "transaction_uom": basic_uom,   # 交易单位
#             "basic_qty": uf_parallel_qty,  # 默认等于交易数量
#             "parallel_uom": item.get("uf_parallel_uom", parallel_uom), # 平行单位
#             "wbs_elements": item.get("uf_wbs_elements", ""),
#             "project_sn": item.get("uf_project_sn", ""),
#             "vendor_code": item.get("uf_vendor_code", ""),
#             "create_id": user_id,
#             "batch_number": batch_number,
#         }
#         doc_items.append(doc_item)
#     print("过账数据构建成功:", doc_head, doc_items)
#     return {
#                 "type": "S",
#                 "message": "构建过账数据成功",
#                 "guid": uf_guid,
#                 "data": {"doc_head":doc_head, "doc_items": doc_items}
#             }

# def build_post_params(header, user_id):
#     """
#     构建库存过账参数 - 多批次拆分成多行
#     """
#     db = DbHelper()
#     document_date = header.get("uf_document_date")
#     posting_date = header.get("uf_posting_date")
#     if document_date is None:
#         document_date = datetime.now().strftime("%Y-%m-%d")
#     if posting_date is None:
#         posting_date = datetime.now().strftime("%Y-%m-%d")
    
#     doc_head = {
#         "document_category": "",
#         "post_code": "3",
#         "document_date": document_date,
#         "posting_date": posting_date,
#         "summary_unique_number": header.get("summary_unique_number", ''),
#         "vendor_dn": header.get("vendor_dn", ''),
#         "company_code": "",
#         "remarks_1": "发货过账"
#     }
    
#     doc_items = []
#     line_id = 0
#     uf_guid = ""
#     header = header.get("header")[0]
#     print(header.get("item"),'header.get("item")')
#     for item in header.get("item"):
#         mat_code = item.get("uf_mat_code")
#         batch_sn = item.get("uf_batch_sn", "")
#         plant_code = item.get("uf_plant")
#         uf_guid = item.get("uf_guid", "")
        
#         query_mat_sql = "SELECT basic_uom, parallel_uom FROM t_mmd_material_basic_data WHERE mat_code = {} ".format(repr(mat_code))
#         mat_info = db.query_sql(query_mat_sql)
#         basic_uom = mat_info[0]['basic_uom'] if mat_info else item.get('transaction_uom', 'EA')
#         parallel_uom = mat_info[0]['parallel_uom'] if mat_info else ''
        
#         query_plant_sql = "SELECT company_code FROM t_os_company_plant_alloc WHERE plant_code = {} ".format(repr(plant_code))
#         plant_info = db.query_sql(query_plant_sql)
#         if plant_info:
#             doc_head['company_code'] = plant_info[0]['company_code']
        
#         if not item.get("uf_picked_qty"):
#             uf_parallel_qty = 0
#         else:
#             uf_parallel_qty = float(item["uf_picked_qty"])
        
#         # 获取批次分配信息
#         batch_data_list, batch_sn_str = build_batch_number(mat_code, uf_parallel_qty, batch_sn, db)
        
#         # batch_data_list 可能是列表（多批次）或单个字典
#         if isinstance(batch_data_list, list):
#             batch_list = batch_data_list
#         else:
#             # 如果是单个字典，包装成列表
#             batch_list = [batch_data_list]
        
#         # 为每个批次创建独立的行项目
#         for batch_data in batch_list:
#             line_id += 1
            
#             # 获取当前批次的数量
#             if 'count' in batch_data:
#                 # 从分配结果中获取数量
#                 batch_qty = float(batch_data.get('count', 0))
#             else:
#                 # 如果是单个批次，使用总数量
#                 batch_qty = uf_parallel_qty
            
#             if batch_qty <= 0:
#                 continue
            
#             # 获取批次详细信息（从 batch_number 表查询）
#             batch_detail = batch_data
#             if 'id' not in batch_detail:
#                 # 如果不是完整的批次信息，需要查询
#                 query_batch_sql = "SELECT * FROM t_batch_number WHERE mat_code = {} AND batch_sn = {}".format(
#                     repr(mat_code), repr(batch_data.get('batch_sn', ''))
#                 )
#                 batch_detail_list = db.query_sql(query_batch_sql)
#                 batch_detail = batch_detail_list[0] if batch_detail_list else batch_data
            
#             doc_item = {
#                 "line_id": line_id,
#                 "movement_type": item.get("uf_movement_type", "D008"),
#                 "plant_code": plant_code,
#                 "stor_loc_code": item["uf_storage_loc"],
#                 "mat_code": mat_code,
#                 "batch_sn": batch_detail.get("batch_sn", ""),  # 单个批次号，不是逗号拼接
#                 "inventory_status": item.get("inventory_status", "0"),
#                 "special_inventory_status1": item.get("uf_special_inventory_status1", ""),
#                 "special_inventory_status2": "",
#                 "transaction_qty": batch_qty,  # 当前批次的数量
#                 "transaction_uom": basic_uom,
#                 "basic_qty": batch_qty,
#                 "parallel_uom": item.get("uf_parallel_uom", parallel_uom),
#                 "wbs_elements": item.get("uf_wbs_elements", ""),
#                 "project_sn": item.get("uf_project_sn", ""),
#                 "vendor_code": item.get("uf_vendor_code", ""),
#                 "create_id": user_id,
#                 "batch_number": batch_detail,  # 单个批次的详细信息（字典）
#             }
#             doc_items.append(doc_item)
    
#     if not doc_items:
#         return {
#             "type": "E",
#             "message": "没有有效的批次数据",
#             "guid": uf_guid
#         }
    
#     return {
#         "type": "S",
#         "message": "构建过账数据成功",
#         "guid": uf_guid,
#         "data": {"doc_head": doc_head, "doc_items": doc_items}
#     }

def build_post_params(header, user_id):
    """
    构建库存过账参数 - 多批次拆分成多行，每个批次使用自己的工厂和库存地点
    """
    db = DbHelper()
    document_date = header.get("uf_document_date")
    posting_date = header.get("uf_posting_date")
    if document_date is None:
        document_date = datetime.now().strftime("%Y-%m-%d")
    if posting_date is None:
        posting_date = datetime.now().strftime("%Y-%m-%d")
    
    doc_head = {
        "document_category": "",
        "post_code": "3",
        "document_date": document_date,
        "posting_date": posting_date,
        "summary_unique_number": header.get("summary_unique_number", ''),
        "vendor_dn": header.get("vendor_dn", ''),
        "company_code": "",
        "remarks_1": "发货过账"
    }
    
    doc_items = []
    line_id = 0
    uf_guid = ""
    header = header.get("header")[0]
    print(header.get("item"), 'header.get("item")')
    
    for item in header.get("item"):
        mat_code = item.get("uf_mat_code")
        batch_sn = item.get("uf_batch_sn", "")
        # 注意：这里不再直接使用传入的 plant_code 和 stor_loc_code
        plant_code = item.get("uf_plant")
        # stor_loc_code = item.get("uf_storage_loc")
        uf_guid = item.get("uf_guid", "")
        
        query_mat_sql = "SELECT basic_uom, parallel_uom FROM t_mmd_material_basic_data WHERE mat_code = {} ".format(repr(mat_code))
        mat_info = db.query_sql(query_mat_sql)
        basic_uom = mat_info[0]['basic_uom'] if mat_info else item.get('transaction_uom', 'EA')
        parallel_uom = mat_info[0]['parallel_uom'] if mat_info else ''
        
        if not item.get("uf_picked_qty"):
            uf_parallel_qty = 0
        else:
            uf_parallel_qty = float(item["uf_picked_qty"])
        line_company_code = ""
        if plant_code:
            query_plant_sql = "SELECT company_code FROM t_os_company_plant_alloc WHERE plant_code = {} ".format(repr(plant_code))
            plant_info = db.query_sql(query_plant_sql)
            if plant_info:
                line_company_code = plant_info[0]["company_code"]
                # 赋值给单据头（无值才覆盖）
                if not doc_head['company_code']:
                    doc_head['company_code'] = line_company_code
        # 获取批次分配信息（传入库存地点用于筛选，但不强制使用）
        batch_data_list, batch_sn_str = build_batch_number(mat_code, uf_parallel_qty,line_company_code, batch_sn, db)
        
        if isinstance(batch_data_list, list):
            batch_list = batch_data_list
        else:
            batch_list = [batch_data_list]
        
        # 为每个批次创建独立的行项目
        for batch_data in batch_list:
            line_id += 1
            
            batch_qty = float(batch_data.get('count', 0))
            if batch_qty <= 0:
                continue
            
            # ========== 关键修改：根据批次号查询实际的工厂和库存地点 ==========
            batch_sn_value = batch_data.get('batch_sn', '')
            
            # 1. 先从 t_inventory_batch_data 获取该批次的库存地点
            query_inv_sql = """
                SELECT plant_code, stor_loc_code, basic_qty 
                FROM t_inventory_batch_data 
                WHERE mat_code = {} AND batch_sn = {} AND basic_qty > 0
            """.format(repr(mat_code), repr(batch_sn_value))
            inv_data = db.query_sql(query_inv_sql)
            
            if not inv_data:
                # 如果查不到库存，报错
                return {
                    "type": "E",
                    "message": f"物料{mat_code}批次{batch_sn_value}无可用库存",
                    "guid": uf_guid
                }
            
            # 取第一条库存记录（如果有多个库存地点，可能需要进一步处理）
            actual_plant_code = inv_data[0]['plant_code']
            actual_stor_loc_code = inv_data[0]['stor_loc_code']
            
            print(f"批次 {batch_sn_value} 实际工厂: {actual_plant_code}, 实际库存地点: {actual_stor_loc_code}")
            
            # 2. 获取工厂对应的公司代码
            query_plant_sql = "SELECT company_code FROM t_os_company_plant_alloc WHERE plant_code = {} ".format(repr(actual_plant_code))
            plant_info = db.query_sql(query_plant_sql)
            if plant_info and not doc_head['company_code']:
                doc_head['company_code'] = plant_info[0]['company_code']
            
            # 3. 获取批次详细信息（从 t_batch_number 表）
            batch_detail = batch_data
            if 'id' not in batch_detail:
                query_batch_sql = "SELECT * FROM t_batch_number WHERE mat_code = {} AND batch_sn = {}".format(
                    repr(mat_code), repr(batch_sn_value)
                )
                batch_detail_list = db.query_sql(query_batch_sql)
                batch_detail = batch_detail_list[0] if batch_detail_list else batch_data
            
            # 4. 构建行项目（使用实际的工厂和库存地点）
            doc_item = {
                "line_id": line_id,
                "movement_type": item.get("uf_movement_type", "D008"),
                "plant_code": actual_plant_code,              # 使用实际工厂
                "stor_loc_code": actual_stor_loc_code,        # 使用实际库存地点
                "mat_code": mat_code,
                "batch_sn": batch_sn_value,
                "inventory_status": item.get("inventory_status", "0"),
                "special_inventory_status1": item.get("uf_special_inventory_status1", ""),
                "special_inventory_status2": "",
                "transaction_qty": batch_qty,
                "transaction_uom": basic_uom,
                "basic_qty": batch_qty,
                "parallel_uom": item.get("uf_parallel_uom", parallel_uom),
                "wbs_elements": item.get("uf_wbs_elements", ""),
                "project_sn": item.get("uf_project_sn", ""),
                "vendor_code": item.get("uf_vendor_code", ""),
                "create_id": user_id,
                "batch_number": batch_detail,
            }
            doc_items.append(doc_item)
    
    if not doc_items:
        return {
            "type": "E",
            "message": "没有有效的批次数据",
            "guid": uf_guid
        }
    
    return {
        "type": "S",
        "message": "构建过账数据成功",
        "guid": uf_guid,
        "data": {"doc_head": doc_head, "doc_items": doc_items}
    }

# def build_batch_number(mat_code,uf_parallel_qty, batch_sn, db):
#     """
#     构建批次信息
#     :param mat_code: 物料编码
#     :param batch_sn: 批次号
#     :param db: 数据库连接
#     :return: 批次信息字典
#     """
#     # 如果批次号为空，调用 get_batch_sn_info 生成/获取批次号
#     if not batch_sn:
#         # 适配 get_batch_sn_info 入参：datalist 是列表套字典
#         req_data = [{
#             "mat_code": mat_code,
#             "count": uf_parallel_qty
#         }]
#         # get_batch_sn_info 返回 (msg, result_list)
#         msg, batch_result_list = get_batch_sn_info(db, req_data)
#         if msg or not batch_result_list:
#             raise ValueError(f"获取批次号失败: {msg}")
#         print("batch_result_list>>", batch_result_list)
#         # 取出单条结果 + 批次号
#         single_data = batch_result_list[0]
#         batch_sn_info = single_data.get("batch_sn_info", [])
#         if not batch_sn_info:
#             raise ValueError("未生成/查询到有效批次号")
        
#         batch_sn = batch_sn_info[0].get("batch_sn", "")
#         if not batch_sn:
#             raise ValueError("批次号为空")

#     # 优化：使用参数化查询，杜绝SQL注入
#     print("查询批次信息:", mat_code, batch_sn)
#     query_sql = "SELECT * FROM t_batch_number WHERE mat_code = {} AND batch_sn = {}".format(repr(mat_code), repr(batch_sn))
#     batch_data = db.query_sql(query_sql)
#     print("查询批次信息:", batch_data)
#     # 使用数据库查询结果
#     batch_number = batch_data[0]
#     return batch_number, batch_sn

def build_batch_number(mat_code, uf_parallel_qty,line_company_code, batch_sn, db):
    """
    构建批次信息，返回批次分配列表和批次号字符串
    :return: (batch_data_list, batch_sn_str)
        batch_data_list: 包含每个批次及其数量的列表
        batch_sn_str: 逗号拼接的批次号字符串
    """
    if not batch_sn:
        req_data = [{
            "mat_code": mat_code,
            "count": uf_parallel_qty,
            "company_code":line_company_code
        }]
        print(req_data,'req_data')
        msg, batch_result_list = get_batch_sn_info(db, req_data)
        if msg or not batch_result_list:
            raise ValueError(f"获取批次号失败: {msg}")
        
        single_data = batch_result_list[0]
        batch_sn_info = single_data.get("batch_sn_info", [])
        if not batch_sn_info:
            raise ValueError("未生成/查询到有效批次号")
        
        # 提取批次号列表和数量信息
        batch_list = []
        batch_sn_list = []
        for item in batch_sn_info:
            batch_sn_list.append(item["batch_sn"])
            # 查询批次详细信息
            query_sql = f"SELECT * FROM t_batch_number WHERE mat_code = {repr(mat_code)} AND batch_sn = {repr(item['batch_sn'])}"
            batch_data = db.query_sql(query_sql)
            if batch_data:
                batch_detail = batch_data[0]
                batch_detail['count'] = item.get('count', 0)
                batch_list.append(batch_detail)
            else:
                # 如果查不到，至少保留批次号和数量
                batch_list.append({
                    'batch_sn': item['batch_sn'],
                    'count': item.get('count', 0),
                    'mat_code': mat_code
                })
        
        batch_sn_str = ",".join(batch_sn_list)
        return batch_list, batch_sn_str
    else:
        # 外部传入单个批次号
        batch_sn_str = batch_sn
        query_sql = f"SELECT * FROM t_batch_number WHERE mat_code = {repr(mat_code)} AND batch_sn = {repr(batch_sn)}"
        batch_data = db.query_sql(query_sql)
        if not batch_data:
            raise ValueError(f"表t_batch_number未查询到物料{mat_code}下批次{batch_sn}数据")
        batch_data[0]['count'] = uf_parallel_qty
        return [batch_data[0]], batch_sn_str



# 物料获取批次
def get_bs_category():
    res = Response()
    db = DbHelper()
    req = Request()
    body = json.loads(req.body())

    data = [{
        "uf_bs_category": "29"
    },
        {
            "uf_bs_category": "37"
        }]

    res.set_body(json.dumps({"code": 200, "msg": "查询成功", "data": data}))
    res.commit(True)


# 物料获取批次
def get_post_status():
    res = Response()
    db = DbHelper()
    req = Request()
    body = json.loads(req.body())

    data = [{
        "posting_status": "A"
    },
        {
            "posting_status": "B"
        },
        {
            "posting_status": "C"
        }]

    res.set_body(json.dumps({"code": 200, "msg": "查询成功", "data": data}))
    res.commit(True)
