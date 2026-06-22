#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@File    : SalePostInterface.py
@Author  : tao.chang@dxdstech.com
@Date    : 2025/4/11 15:42
@explain : 文件说明
"""
import threading
import time
import traceback

try:
    import pyfiles.SysPathAdd
except ImportError:
    ...
from DbHelper import DbHelper
from DxBusinessDataConvertUtil import (
    convert_material_unit_qty_new as convert_material_unit_qty,
)
from DxDateUtil import get_now_date_str

# from DxInventoryPostData import postFunc
from DxInventoryReverseData import reverse_data
from DxPostByDate import postFunc
from logger import LoggerConfig
from SystemHelper import SystemHelper
from ToolsMethods import ResponseData, ResponseStatusCode, calc_time
from ZZEXT_SalePostInterface import ZZEXT_opt_item

logger = LoggerConfig("SalePostInterface", isStream=False)

test_run = "0"  # 1测试 0 正式


class CodeTimer:
    def __init__(self, name=""):
        self.name = name
        self.start = None
        self.elapsed = None

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.elapsed = time.perf_counter() - self.start
        from datetime import datetime
        print(
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} [上下文] {self.name} 线程：{threading.current_thread().ident}, 耗时: {self.elapsed:.6f}秒")


class PostHead:

    def __init__(self, post_code, document_date, posting_date, exchange_rate="", summary_unique_number="",
                 vendor_dn="", remarks_1="", remarks_2="", auto_created_mark="", picking_document="", ztype=""):
        """
        :param post_code:过账代码
        :param exchange_rate:交易汇率
        :param document_date:凭证日期
        :param posting_date:过账日期
        :param summary_unique_number:汇总号
        :param vendor_dn:供应商交货单
        :param remarks_1:备注信息1
        :param remarks_2:备注信息2
        """
        self.post_code = post_code
        self.exchange_rate = exchange_rate
        self.document_date = document_date
        self.posting_date = posting_date
        self.summary_unique_number = summary_unique_number
        self.vendor_dn = vendor_dn
        self.remarks_1 = remarks_1
        self.remarks_2 = remarks_2
        self.auto_created_mark = auto_created_mark
        self.picking_document = picking_document
        self.ztype = ztype


class PostItem:

    def __init__(self, up_prod_mater_mark="", line_id="", parent_id="", movement_type="", plant_code="",
                 stor_loc_code="", special_inventory_status1="", special_inventory_status2="",
                 inventory_status="", mat_code="", batch_sn="", transaction_qty="", transaction_uom="",
                 basic_qty="", basic_uom="", batch_qty="", batch_uom="", parallel_qty="", parallel_uom="",
                 transaction_amount="", transaction_currency="", rel_po_sn="", rel_po_items="", item_sn="", sn="",
                 batch_closure_flag="", batch_closure_date="", prodo_component_number="",
                 rel_dn_sn="", rel_dn_item="", ro_sn="", ro_items="", rel_so_sn="", rel_so_items="",
                 customer_code="", so_sn="", so_items="", project_sn="", vendor_code="", po_sn="", po_items="",
                 prod_order="", wbs_elements="", cost_center="", cost_business_object="",
                 cost_business_object1="", profit_center="", accounting_subjects="", asset_card="", sub_assets="",
                 equipment_id="", express_delivery="", reference1_item="", reference2_item="",
                 reference3_item="", summary_item_sn="", rcv_plant_code="", rcv_stor_loc_code="",
                 rcv_special_inventory_status1="", rcv_special_inventory_status2="", rcv_inventory_status="",
                 rcv_mat_code="", rcv_customer_code="", rcv_so_sn="", rcv_so_items="", rcv_project_sn="",
                 rcv_vendor_code="", rcv_po_sn="", rcv_po_items="", rcv_batch_sn="", proof_flag="", rcv_proof_flag="",
                 batch_number={}, rcv_batch_number={}, auto_created_mark="", picking_document="", dn_sn="", dn_item="",
                 batch_item=0, pod_related=0):
        """
        :param up_prod_mater_mark:是否更新主材
        :param line_id:物料凭证行唯一标识
        :param parent_id:凭证行关联唯一标识
        :param movement_type:移动类型
        :param plant_code:工厂代码
        :param pod_related:pod标记
        :param stor_loc_code:库存地点编码
        :param special_inventory_status1:特殊库存状态1
        :param special_inventory_status2:特殊库存状态2
        :param inventory_status:库存状态
        :param mat_code:物料编码
        :param batch_sn:批次号
        :param transaction_qty:交易数量
        :param transaction_uom:交易单位
        :param basic_qty:基本数量
        :param basic_uom:基本单位
        :param parallel_qty:平行数量
        :param parallel_uom:平行单位
        :param transaction_amount:交易金额
        :param transaction_currency:交易货币
        :param rel_po_sn:关联采购订单
        :param rel_po_items:关联采购订单行
        :param item_sn:关联采购订单行项目序号
        :param sn:关联采购订单行序号
        :param batch_closure_flag:结批标识
        :param batch_closure_date:结批日期
        # :param rel_prod_order:关联生产订单 删除
        :param prodo_component_number:关联生产订单组件序号
        :param rel_dn_sn:关联交货单
        :param rel_dn_item:关联交货单行
        :param ro_sn:关联预留
        :param ro_items:关联预留行
        :param rel_so_sn:关联销售订单
        :param rel_so_items:关联销售订单行
        :param customer_code:客户编码
        :param so_sn:销售订单编号
        :param so_items:销售订单行号
        :param project_sn:项目编号
        :param vendor_code:供应商编码
        :param po_sn:采购订单编号
        :param po_items:采购订单行号
        :param prod_order:生产订单号
        :param wbs_elements:WBS元素
        :param cost_center:成本中心
        :param cost_business_object:成本事项
        :param cost_business_object1:成本事项1
        :param profit_center:利润中心
        :param accounting_subjects:会计科目
        :param asset_card:资产卡片
        :param sub_assets:子资产
        :param equipment_id:设备ID
        :param express_delivery:快递单号
        :param reference1_item:行参考信息1
        :param reference2_item:行参考信息2
        :param reference3_item:行参考信息3
        :param summary_item_sn:汇总行
        :param rcv_plant_code:接收工厂代码
        :param rcv_stor_loc_code:接收库存地点
        :param rcv_special_inventory_status1:接收特殊库存状态1
        :param rcv_special_inventory_status2:接收特殊库存状态2
        :param rcv_inventory_status:接收库存状态
        :param rcv_mat_code:接收物料编码
        :param rcv_customer_code:接收客户编码
        :param rcv_so_sn:接收销售订单编号
        :param rcv_so_items:接收销售订单行号
        :param rcv_project_sn:接收项目编号
        :param rcv_vendor_code:接收供应商编码
        :param rcv_po_sn:接收采购订单编号
        :param rcv_po_items:接收采购订单行号
        """
        self.up_prod_mater_mark = up_prod_mater_mark
        self.line_id = line_id
        self.parent_id = parent_id
        self.movement_type = movement_type
        self.plant_code = plant_code
        self.stor_loc_code = stor_loc_code
        self.special_inventory_status1 = special_inventory_status1
        self.special_inventory_status2 = special_inventory_status2
        self.inventory_status = inventory_status
        self.mat_code = mat_code
        self.batch_sn = batch_sn
        self.transaction_qty = transaction_qty
        self.transaction_uom = transaction_uom
        self.basic_qty = basic_qty
        self.basic_uom = basic_uom
        self.batch_qty = batch_qty
        self.batch_uom = batch_uom
        self.parallel_qty = parallel_qty
        self.parallel_uom = parallel_uom
        self.transaction_amount = transaction_amount
        self.transaction_currency = transaction_currency
        self.rel_po_sn = rel_po_sn
        self.rel_po_items = rel_po_items
        self.item_sn = item_sn
        self.sn = sn
        self.batch_closure_flag = batch_closure_flag
        self.batch_closure_date = batch_closure_date
        # self.rel_prod_order = rel_prod_order
        self.prodo_component_number = prodo_component_number
        self.rel_dn_sn = rel_dn_sn
        self.rel_dn_item = rel_dn_item
        self.ro_sn = ro_sn
        self.ro_items = ro_items
        self.rel_so_sn = rel_so_sn
        self.rel_so_items = rel_so_items
        self.customer_code = customer_code
        self.so_sn = so_sn
        self.so_items = so_items
        self.project_sn = project_sn
        self.vendor_code = vendor_code
        self.po_sn = po_sn
        self.po_items = po_items
        self.prod_order = prod_order
        self.wbs_elements = wbs_elements
        self.cost_center = cost_center
        self.cost_business_object = cost_business_object
        self.cost_business_object1 = cost_business_object1
        self.profit_center = profit_center
        self.accounting_subjects = accounting_subjects
        self.asset_card = asset_card
        self.sub_assets = sub_assets
        self.equipment_id = equipment_id
        self.express_delivery = express_delivery
        self.reference1_item = reference1_item
        self.reference2_item = reference2_item
        self.reference3_item = reference3_item
        self.summary_item_sn = summary_item_sn
        self.rcv_plant_code = rcv_plant_code
        self.rcv_stor_loc_code = rcv_stor_loc_code
        self.rcv_special_inventory_status1 = rcv_special_inventory_status1
        self.rcv_special_inventory_status2 = rcv_special_inventory_status2
        self.rcv_inventory_status = rcv_inventory_status
        self.rcv_mat_code = rcv_mat_code
        self.rcv_customer_code = rcv_customer_code
        self.rcv_so_sn = rcv_so_sn
        self.rcv_so_items = rcv_so_items
        self.rcv_project_sn = rcv_project_sn
        self.rcv_vendor_code = rcv_vendor_code
        self.rcv_po_sn = rcv_po_sn
        self.rcv_po_items = rcv_po_items
        self.rcv_batch_sn = rcv_batch_sn
        self.proof_flag = proof_flag
        self.rcv_proof_flag = rcv_proof_flag
        self.batch_number = batch_number
        self.rcv_batch_number = rcv_batch_number
        self.auto_created_mark = auto_created_mark
        self.picking_document = picking_document
        self.dn_sn = dn_sn
        self.dn_item = dn_item
        self.batch_item = batch_item
        self.pod_related = pod_related


def get_pi_invoice_item_view():
    view = ""
    db = DbHelper()
    t_md_datas = db.get_tables_like_only_name("t_md_item", "", "")
    data = [each for each in t_md_datas if each != "t_md_item"]
    if data:
        for each in data:
            view += """
                SELECT *
                FROM `{}`
                UNION ALL
            """.format(each)
        view = view.rsplit('UNION ALL', 1)[0]
    if not view:
        return """
            SELECT * FROM `t_md_item`
            WHERE 1 = 0
        """

    return view


def dnPostFuncAPI(data):
    md_item_sql = get_pi_invoice_item_view()
    exit_picking_document = []
    new_data = []
    for item in data:
        if item.get("picking_document") in exit_picking_document:
            continue
        exit_picking_document.append(item.get("picking_document"))
        columns = '''
                           MAX(`alloc`.`id`) as `id`,
                           MAX(`header`.`dn_type`) as `dn_type`,
                           MAX(`header`.`estimated_delivery_date`) as `estimated_delivery_date`,
                           MAX(`header`.`company_code`) as `company_code`,
                           MAX(`dt`.`dn_type_description`) as `dn_type_description`,
                           MAX(`item`.`dn_sn`) AS `rel_dn_sn`,
                           MAX(`item`.`dn_item`) AS `rel_dn_item`,
                           MAX(`item`.`so_sn`) AS `rel_so_sn`,
                           MAX(`item`.`so_items`) AS `rel_so_items`,
                           MAX((CASE WHEN `item`.`pod_related` = 1 THEN `item`.`movement_type_it` ELSE `item`.`movement_type` END )) AS `movement_type`,
                           MAX(`item`.`pod_status`) as `pod_status`,
                           MAX(`item`.`pod_related`) as `pod_related`,
                           MAX(`md`.`mat_doc_sn`) as `mat_doc_sn`,
                           MAX(`md`.`mat_doc_items`) as `mat_doc_items`,
                           MAX(`partner`.`business_partner_code`) AS `dn_customer_code`,
                           MAX(`partner`.`business_partner_name`) AS `dn_customer_name`,
                           MAX(( CASE WHEN `item`.`special_inventory_status1` IN ('CC', 'C') THEN `partner`.`business_partner_code` ELSE '' END )) AS `customer_code`,
                           MAX(( CASE WHEN `item`.`special_inventory_status1` IN ('CC', 'C') THEN `partner`.`business_partner_name` ELSE '' END )) AS `customer_name`,
                           MAX(`partner2`.`business_partner_code`) AS `destination_customer_code`,
                           MAX(`partner2`.`business_partner_name`) AS `destination_customer_name`,
                           MAX(`partner2`.`business_partner_addr`) as `business_partner_addr`,
                           MAX(`partner2`.`contact_person`) as `contact_person`,
                           MAX(`partner2`.`contact_number`) as `contact_number`,
                           MAX(`sales`.`customer_order`) as `customer_order`,
                           MAX(`item`.`create_id`) as `create_id`,
                           MAX(`t_system_user`.`name`) AS `create_name`,
                           MAX(`item`.`create_time`) as `create_time`,
                           MAX(`item`.`so_sn`) AS `so_sn`,
                           MAX(`item`.`so_items`) AS `so_items`,
                           MAX(`alloc`.`mat_code`) as `mat_code`,
                           MAX(`material`.`mat_description`) AS `mat_descr`,
                           MAX(`item`.`planned_delivery_quantity`) as `planned_delivery_quantity`,
                           MAX(`alloc`.`external_mat_code`) as `external_mat_code`,
                           MAX(`alloc`.`picking_document`) as `picking_document`,
                           MAX(`mt`.`mat_description`) AS `external_mat_descr`,
                           MAX(`item`.`cust_mat_code`) as `cust_mat_code`,
                           MAX(`cmmd`.`cust_mat_code_description`) AS `cust_mat_code_description`,
                           MAX(CONCAT(CONCAT( `item`.`packing_status`, ' '), `t_so_status_record`.`status_description` )) AS `packing_status`,
                           MAX(CONCAT(CONCAT( `alloc`.`posting_status`, ' '), `t_so_status_record2`.`status_description` )) AS `posting_status`,
                           MAX(CONCAT(CONCAT( `header`.`pod_status`, ' '), `t_so_status_record3`.`status_description` )) AS `pod_status`,
                           MAX(CONCAT(CONCAT( `header`.`billing_status`, ' '), `t_so_status_record4`.`status_description` )) AS `billing_status`,
                           MAX(`item`.`plant_code`) as `plant_code`,
                           MAX(`t_os_plant`.`plant_description`) AS `plant_name`,
                           MAX(( CASE WHEN `item`.`pod_related` = 1 THEN `mv1`.`post_code` ELSE `mv`.`post_code` END )) AS `post_code`,
                           CURRENT_DATE AS `document_date`,
                           CURRENT_DATE AS `posting_date`,
                           MAX(`alloc`.`batch_sn`) as `batch_sn`,
                           MAX(`alloc`.`picked_qty`) AS `transaction_qty`,
                           MAX(`alloc`.`picked_qty`) AS `alloc_picked_qty`,
                           MAX(`alloc`.`picked_base_qty`) as `picked_base_qty`,
                           MAX(`alloc`.`picked_parallel_qty`) as `picked_parallel_qty`,
                           MAX(`alloc`.`stor_loc_code`) AS `alloc_stor_loc_code`,
                           MAX(`alloc`.`transaction_uom`) as `transaction_uom`,
                           MAX(`alloc`.`parallel_uom`) as `parallel_uom`,
                           MAX(`alloc`.`basic_uom`) as `basic_uom`,
                           MAX(`alloc`.`batch_item`) as `batch_item`,
                           MAX(`sales_item`.`intercompany_purchase_order_number`) as `intercompany_purchase_order_number`,
                           MAX(`sales_item`.`intercompany_purchase_order_item_serial_number`) as `intercompany_purchase_order_item_serial_number`,
                           MAX(`alloc`.`stor_loc_code`) as `stor_loc_code`,
                           MAX(`tosal`.`stor_loc_desc`) as `stor_loc_desc`,
                           MAX(( CASE WHEN `material_cost`.`cost_uom` != '' THEN `material_cost`.`cost_uom` ELSE `material`.`basic_uom` END )) AS `batch_uom`,
                           MAX(0) AS `basic_qty`,
                           MAX(`item`.`special_inventory_status1`) as `special_inventory_status1`,
                           '' AS `special_inventory_status2`,
                           MAX(( CASE WHEN `item`.`pod_related` = 1 THEN 'T' ELSE '' END )) AS `rcv_special_inventory_status2`,
                           MAX(`item`.`wbs_elements`) as `wbs_elements`,
                           MAX(`item`.`cost_center`) as `cost_center`,
                           MAX(`item`.`profit_center`) as `profit_center`,
                           MAX(`item`.`cost_business_object`) as `cost_business_object`,
                           MAX(`item`.`cost_business_object1`) as `cost_business_object1`,
                           MAX(`item`.`cost_uom`) as `cost_uom`,
                           MAX('') AS `rcv_vendor_code`,
                           MAX(`cat`.`rcv_special_inventory_status1`) as `rcv_special_inventory_status1`,
                           MAX(( CASE WHEN `cat`.`rcv_special_inventory_status1` != '' OR ( CASE WHEN `item`.`pod_related` = 1 THEN 'T' ELSE '' END ) != '' THEN `alloc`.`mat_code` ELSE '' END  )) AS `rcv_mat_code`,
                           MAX(( CASE WHEN `cat`.`rcv_special_inventory_status1` != '' OR ( CASE WHEN `item`.`pod_related` = 1 THEN 'T' ELSE '' END ) != '' THEN `alloc`.`batch_sn` ELSE '' END )) AS `rcv_batch_sn`,
                           MAX(( CASE WHEN `cat`.`rcv_special_inventory_status1` = 'CC' THEN `partner`.`business_partner_code` ELSE '' END )) AS `rcv_customer_code`,
                           MAX(( CASE WHEN `cat`.`rcv_special_inventory_status1` = 'S' THEN `item`.`so_sn` ELSE '' END )) AS `rcv_so_sn`,
                           MAX(( CASE WHEN `cat`.`rcv_special_inventory_status1` = 'S' THEN `item`.`so_items` ELSE 0 END )) AS `rcv_so_items`,
                           MAX(( CASE WHEN `cat`.`rcv_special_inventory_status1` != '' OR ( CASE WHEN `item`.`pod_related` = 1 THEN 'T' ELSE '' END ) != '' THEN `item`.`plant_code` ELSE '' END )) AS `rcv_plant_code`,
                           MAX(( CASE WHEN `cat`.`rcv_special_inventory_status1` != '' OR ( CASE WHEN `item`.`pod_related` = 1 THEN 'T' ELSE '' END ) != '' THEN `alloc`.`stor_loc_code` ELSE '' END ))  AS `rcv_stor_loc_code`
                   '''

        query_sql = '''
                       WITH
                       `md_item_new` AS(
                           {}
                       )
                       SELECT {}
                       FROM
                           `t_dn_inventory_alloc` AS `alloc`
                           LEFT JOIN `t_dn_item` AS `item`  ON `item`.`dn_sn` = `alloc`.`dn_sn` AND `item`.`dn_item` = `alloc`.`dn_item`
                           LEFT JOIN `t_ao_sd_item_category` AS `cat` ON `item`.`sales_item_category` = `cat`.`sales_item_category`
                           LEFT JOIN `t_dn_header` AS `header` ON `header`.`dn_sn` = `item`.`dn_sn`
                           LEFT JOIN `md_item_new` AS `md` ON `alloc`.`picking_document` = `md`.`picking_document` AND `item`.`dn_sn` = `md`.`rel_dn_sn` AND `item`.`dn_item` = `md`.`rel_dn_item` AND `md`.`reversal_mark` != 1 AND `md`.`reversed_mark` != 1
                           LEFT JOIN `t_documents_business_partner` AS `partner` ON `item`.`dn_sn` = `partner`.`doc_sn` AND `partner`.`business_partner_type` = 'SP' AND `partner`.`document_category` = 'SDLV'
                           LEFT JOIN `t_documents_business_partner` AS `partner2` ON `item`.`dn_sn` = `partner2`.`doc_sn` AND `partner2`.`business_partner_type` = 'DP'
                           LEFT JOIN `t_sales_order_header` AS `sales` ON `sales`.`so_sn` = `item`.`so_sn`
                           LEFT JOIN `t_sales_order_item` AS `sales_item` ON `sales_item`.`so_sn` = `item`.`so_sn` AND `sales_item`.`so_items` = `item`.`so_items`
                           LEFT JOIN `t_os_plant` AS `t_os_plant` ON `t_os_plant`.`plant_code` = `item`.`plant_code`
                           LEFT JOIN `t_system_user` AS `t_system_user` ON `item`.`create_id` = `t_system_user`.`id`
                           LEFT JOIN `t_so_status_record` AS `t_so_status_record` ON `t_so_status_record`.`state_value` = `header`.`packing_status` AND `t_so_status_record`.`field` = 'packing_status'
                           LEFT JOIN `t_so_status_record` AS `t_so_status_record2` ON `t_so_status_record2`.`state_value` = `header`.`posting_status` AND `t_so_status_record2`.`field` = 'posting_status'
                           LEFT JOIN `t_so_status_record` AS `t_so_status_record3` ON `t_so_status_record3`.`state_value` = `header`.`pod_status` AND `t_so_status_record3`.`field` = 'pod_status'
                           LEFT JOIN `t_so_status_record` AS `t_so_status_record4` ON `t_so_status_record4`.`state_value` = `header`.`billing_status` AND `t_so_status_record4`.`field` = 'billing_status'
                           LEFT JOIN `t_os_plant_storage_location_alloc` AS `tosal` ON `tosal`.`plant_code` = `item`.`plant_code` AND `tosal`.`stor_loc_code` = `alloc`.`stor_loc_code`
                           LEFT JOIN `t_mmd_material_cost_data` AS `material_cost` ON `item`.`mat_code` = `material_cost`.`mat_code` AND `item`.`plant_code` = `material_cost`.`plant_code`
                           LEFT JOIN `t_mmd_material_basic_data` AS `material` ON `alloc`.`mat_code` = `material`.`mat_code`
                           LEFT JOIN `t_mmd_material_basic_data` AS `mt` ON `alloc`.`external_mat_code` = `mt`.`mat_code`
                           LEFT JOIN (SELECT DISTINCT `cust_mat_code`, `cust_mat_code_description` FROM `t_cust_mat_master_data`) AS `cmmd` ON `item`.`cust_mat_code` = `cmmd`.`cust_mat_code`
                           LEFT JOIN `t_movement_type` AS `mv` ON `item`.`movement_type` = `mv`.`movement_type`
                           LEFT JOIN `t_movement_type` AS `mv1` ON `item`.`movement_type_it` = `mv1`.`movement_type`
                           LEFT JOIN `t_dn_type` AS `dt` ON `dt`.`dn_type` = `header`.`dn_type`
                       WHERE
                           `alloc`.`posting_status` = 'A'
                       '''.format(md_item_sql, columns)
        query_sql += f""" and `alloc`.`picking_document` = '{item.get('picking_document')}' """
        db = DbHelper()
        group_sql = " group by `alloc`.`id` "
        query_sql += group_sql
        ret = db.query_sql(query_sql, printSql=True)
        if ret:
            for i in ret:
                i["posting_date"] = item.get("posting_date")
                i["express_delivery"] = item.get("express_delivery", "")
            new_data.extend(ret)
    if not new_data:
        return ResponseData(203, "没有查询到符合数据的数据，请检查", data=data)
    print("new_data>?>>>", len(new_data))
    print("new_data>?>>>", new_data)
    return dnPostFunc(new_data)


@calc_time
def dnPostFunc(data):
    retData = []
    sh = SystemHelper()
    user_id = sh.getUserId()
    postStatus = True
    overCreditStatus = False
    # print("data", data)
    try:
        postData = {}
        dn_line_id = {}
        line_id = 1
        insert_relationship_data = []
        # 用来保存已经查询过的picking_document
        picking_document_exits = set()
        for item in data:
            if not item.get("picking_document"):
                postStatus = False
                item["message"] = "拣配单号必输"
                retData.append(item)
                continue
            if not item.get("posting_date"):
                postStatus = False
                item["message"] = "过账日期必输"
                retData.append(item)
                continue
            picking_document_code = item.get("picking_document", "")
            if picking_document_code in picking_document_exits:
                continue
            else:
                picking_document_exits.add(picking_document_code)
            # logger.printInfo("DnPosing item", item)

            # logger.printInfo("postHead>>>", postHead.__dict__)

            inventory_alloc_data = get_inventory_alloc(item.get("picking_document"))
            print("inventory_alloc_data>>>>", len(inventory_alloc_data))
            print("inventory_alloc_data>>>>", inventory_alloc_data)
            if not inventory_alloc_data:
                return ResponseData(ResponseStatusCode.Error,
                                    f"""拣配单：{item.get("picking_document")} 拣配单行号：{item.get("batch_item")} 没有批次数据""",
                                    [])

            for new_item in inventory_alloc_data:
                # 这里进行信贷检查
                credit_control_code = new_item.get("credit_control_code")
                credit_status = new_item.get("credit_status")
                if credit_control_code != "D":
                    if credit_status == "C" or credit_status == "E":
                        postStatus = False
                        item["message"] = f"拣配单信用状态为{credit_status},过账失败，请检查"
                        retData.append(item)
                        continue
                else:
                    if str(new_item.get("credit_activated_flag")) == "1":
                        if credit_status == "C":
                            postStatus = False
                            item["message"] = f"拣配单信用状态为{credit_status}超额为批准,过账失败，请检查"
                            retData.append(item)
                            continue
                        else:
                            from CustLineOfCreditCalculate import getCustomerCreditData
                            from SalesPickInterface import get_credit_management
                            # 客户信用余额
                            customerCredit = getCustomerCreditData(new_item.get("customer_code"),
                                                                   get_credit_management(
                                                                       new_item.get("sales_org_code")),
                                                                   new_item.get("company_code"), )
                            occupancy_limits = customerCredit.get("occupancy_limits", 0)
                            credit_limit = customerCredit.get("credit_limit", 0)
                            if occupancy_limits > credit_limit:
                                postStatus = False
                                overCreditStatus = True
                                item[
                                    "message"] = f"""{new_item.get("customer_code")}客户信用额度为{credit_limit}，已使用信用额度为{occupancy_limits}，信用已超额是否提交审批"""
                                retData.append(item)
                                continue

                postHead = PostHead(post_code=new_item.get("post_code"), document_date=get_now_date_str("%Y-%m-%d"),
                                    posting_date=item.get("posting_date"),
                                    auto_created_mark="",
                                    picking_document=item.get("picking_document"),
                                    ztype="B"
                                    )
                if new_item.get("cost_uom") == new_item.get("basic_uom"):
                    batch_qty = new_item.get("picked_base_qty")
                elif new_item.get("cost_uom") == new_item.get("parallel_uom"):
                    batch_qty = new_item.get("picked_parallel_qty")
                else:
                    code, msg, qty = convert_material_unit_qty(new_item.get("mat_code"), new_item["basic_uom"],
                                                               new_item["cost_uom"],
                                                               new_item["picked_base_qty"])
                    if code == 200:
                        batch_qty = qty
                    else:
                        code, msg, qty = convert_material_unit_qty(new_item.get("mat_code"),
                                                                   new_item.get("parallel_uom"),
                                                                   new_item["cost_uom"],
                                                                   new_item["picked_parallel_qty"])
                        if code == 200:
                            batch_qty = qty
                        else:
                            return ResponseData(ResponseStatusCode.Error, msg, [])
                rel_dn_sn = new_item.get("rel_dn_sn")
                rel_dn_item = new_item.get("rel_dn_item")
                rel_so_sn = new_item.get("rel_so_sn")
                rel_so_items = new_item.get("rel_so_items")
                rcv_plant_code = new_item.get("plant_code")
                rcv_stor_loc_code = new_item.get("stor_loc_code")
                rcv_special_inventory_status1 = new_item.get("rcv_special_inventory_status1")
                rcv_special_inventory_status2 = new_item.get("rcv_special_inventory_status2")
                rcv_mat_code = new_item.get("mat_code")
                if rcv_special_inventory_status1 == "CC":
                    rcv_customer_code = new_item.get("customer_code")
                else:
                    rcv_customer_code = ""
                rcv_so_sn = new_item.get("so_sn")
                rcv_so_items = new_item.get("so_items")
                rcv_project_sn = item.get("rcv_project_sn")
                rcv_inventory_status = "0"
                rcv_batch_sn = new_item.get("batch_sn")
                rcv_proof_flag = new_item.get("pod_related")
                postItem = PostItem(rel_dn_sn=rel_dn_sn,
                                    rel_dn_item=rel_dn_item,
                                    rel_so_sn=rel_so_sn,
                                    rel_so_items=rel_so_items,
                                    customer_code=new_item.get("customer_code"),
                                    mat_code=new_item.get("mat_code"),
                                    inventory_status="0",
                                    parallel_uom=new_item.get("parallel_uom"),
                                    parallel_qty=new_item.get("picked_parallel_qty"),
                                    transaction_uom=new_item.get("transaction_uom"),
                                    transaction_qty=new_item.get("transaction_qty"),
                                    plant_code=new_item.get("plant_code"),
                                    stor_loc_code=new_item.get("stor_loc_code"),
                                    express_delivery=item.get("express_delivery", ""),
                                    special_inventory_status1=new_item.get("special_inventory_status1", ""),
                                    special_inventory_status2='',
                                    movement_type=new_item.get("movement_type"),
                                    wbs_elements=new_item.get("wbs_elements"),
                                    cost_center=new_item.get("cost_center"),
                                    profit_center=new_item.get("profit_center"),
                                    basic_qty=new_item.get("picked_base_qty"),
                                    basic_uom=new_item.get("basic_uom"),
                                    batch_qty=batch_qty,
                                    batch_uom=new_item.get("cost_uom"),
                                    batch_sn=new_item.get("batch_sn"),
                                    rcv_plant_code=rcv_plant_code,
                                    rcv_stor_loc_code=rcv_stor_loc_code,
                                    rcv_special_inventory_status1=rcv_special_inventory_status1,
                                    rcv_special_inventory_status2=rcv_special_inventory_status2,
                                    rcv_mat_code=rcv_mat_code,
                                    rcv_customer_code=rcv_customer_code,
                                    rcv_so_sn=rcv_so_sn,
                                    rcv_so_items=rcv_so_items,
                                    rcv_project_sn=rcv_project_sn,
                                    rcv_inventory_status=rcv_inventory_status,
                                    rcv_batch_sn=rcv_batch_sn,
                                    proof_flag=new_item.get("pod_related"),
                                    rcv_proof_flag=rcv_proof_flag,
                                    pod_related=new_item.get("pod_related"),
                                    auto_created_mark="",
                                    picking_document=item.get("picking_document"),
                                    batch_item=new_item.get("batch_item"),
                                    dn_sn=new_item.get("dn_sn", ""),
                                    dn_item=new_item.get("dn_item", ""),
                                    cost_business_object=new_item.get("cost_business_object"),
                                    cost_business_object1=new_item.get("cost_business_object1")
                                    )

                if new_item.get("picking_document") in postData:
                    dn_line_id[new_item.get("picking_document")] += 1
                    postItem.line_id = dn_line_id.get(new_item.get("picking_document"))
                    postData[new_item.get("picking_document")]["items"].append(postItem.__dict__)
                else:
                    postItem.line_id = line_id
                    dn_line_id[new_item.get("picking_document")] = line_id
                    postData[new_item.get("picking_document")] = {}
                    postData[new_item.get("picking_document")]["header"] = postHead.__dict__
                    postData[new_item.get("picking_document")]["items"] = [postItem.__dict__]
                # print("postItem>>>", postItem.__dict__)
        logger.printInfo("postData>>>", postData)
        for k, idata in postData.items():
            # logger.printInfo("idata", idata)
            start_time = time.time()
            code, msg, error_list, mat_doc_sn, year = postFunc(test_run, user_id, idata["header"], idata["items"])
            print(f"postFunc end time:{time.time() - start_time}")
            if code == 200:
                with CodeTimer("auto_created_mark post"):
                    if str(idata.get("header").get("auto_created_mark")) == "1":
                        new_header = PostHead(post_code=1, document_date=get_now_date_str(),
                                              posting_date=idata["header"].get("posting_date"),
                                              ztype="B")
                        new_items = []
                        material_data = get_material_plant_data()

                        for index, item in enumerate(idata["items"]):
                            po_data = get_po_data_by_dn_sn(item.get("dn_sn"), item.get("dn_item"))

                            postItem = PostItem(
                                mat_code=po_data.get("mat_code"),
                                batch_sn=item.get("batch_sn"),
                                line_id=str(index + 1),
                                stor_loc_code=po_data.get("stor_loc_code") or material_data.get(
                                    (po_data.get("plant_code"), po_data.get("mat_code"))),
                                inventory_status="1",
                                transaction_qty=item.get("transaction_qty"),
                                basic_qty=item.get("basic_qty"),
                                parallel_qty=item.get("parallel_qty"),
                                project_sn=item.get("in_stor_move"),
                                movement_type=po_data.get("in_stor_move"),
                                rel_po_sn=po_data.get("po_sn"),
                                rel_po_items=po_data.get("po_items"),
                                rel_dn_sn=item.get("dn_sn"),
                                rel_dn_item=item.get("dn_item"),
                                rel_so_sn=po_data.get("so_sn"),
                                rel_so_items=po_data.get("so_items"),
                            )
                            new_items.append(postItem.__dict__)
                        code, msg, error_list, mat_doc_sn, year = postFunc(test_run, user_id, new_header, new_items)
                        if code != 200:
                            return ResponseData(ResponseStatusCode.Error, msg, [])

                for item in data:
                    if item["picking_document"] == k:
                        item["message"] = "过账成功"
                        item["mat_doc_sn"] = mat_doc_sn
                        retData.append(item)
                        if item.get("auto_created_mark") == 1:
                            md_data = get_md_item_data(item.get("picking_document"), item.get("batch_item", ""),
                                                       mat_doc_sn, item.get("estimated_delivery_date"),
                                                       item.get("company_code"))
                            po_data = get_po_data_by_dn_sn(item.get("dn_sn"), item.get("dn_item"))
                            md_data1 = get_md_item_data(po_data.get("po_sn"), po_data.get("po_item", ""),
                                                        mat_doc_sn, item.get("estimated_delivery_date"),
                                                        item.get("company_code"))

                            insert_relationship_data.append(
                                {
                                    "picking_document": item.get("picking_document", ""),
                                    "batch_item": item.get("batch_item", ""),
                                    "doc_sn": item.get("mat_doc_sn", ""),
                                    "doc_items": md_data.get("mat_doc_items", ""),
                                    "po_sn": po_data.get("po_sn", ""),
                                    "po_items": po_data.get("po_items", ""),
                                    "mat_doc_sn": mat_doc_sn,
                                    "mat_doc_items": md_data1.get("mat_doc_items", ""),
                                }
                            )

            else:
                postStatus = False
                if error_list:
                    msg = ",".join(error_list)
                for item in data:
                    if item["picking_document"] == k:
                        item["message"] = msg
                        retData.append(item)


        if insert_relationship_data:
            DuplicateSQLKey = ["doc_sn", "doc_items", "po_sn", "po_items",
                               "mat_doc_sn", "mat_doc_items"]
            insert_picking_company_posting_relationship(insert_relationship_data, DuplicateSQLKey)

    except Exception as e:
        traceback_str = traceback.format_exc()
        print(traceback_str)
        return ResponseData(ResponseStatusCode.Error, "程序错误：" + str(e), data=retData)
    # logger.printInfo("retData", retData)
    if overCreditStatus:
        return ResponseData(203, "有信用超额的数据请查看详细信息", data=retData)
    else:
        return ResponseData(ResponseStatusCode.Success if postStatus else ResponseStatusCode.Error,
                            "成功" if postStatus else "请查看详细信息", data=retData)


def dnReversalFuncAPI(data):
    md_item_sql = get_pi_invoice_item_view()
    exit_picking_document = []
    new_data = []
    for item in data:
        if item.get("picking_document") in exit_picking_document:
            continue
        exit_picking_document.append(item.get("picking_document"))
        columns = '''
                           MAX(`alloc`.`id`) as `id`,
                           MAX(`header`.`dn_type`) as `dn_type`,
                           MAX(`header`.`estimated_delivery_date`) as `estimated_delivery_date`,
                           MAX(`header`.`company_code`) as `company_code`,
                           MAX(`dt`.`dn_type_description`) as `dn_type_description`,
                           MAX(`item`.`dn_sn`) AS `rel_dn_sn`,
                           MAX(`item`.`dn_item`) AS `rel_dn_item`,
                           MAX(`item`.`so_sn`) AS `rel_so_sn`,
                           MAX(`item`.`so_items`) AS `rel_so_items`,
                           MAX(( CASE WHEN `item`.`pod_related` = 1 THEN `item`.`movement_type_it` ELSE `item`.`movement_type` END )) AS `movement_type`,
                           MAX(`alloc`.`pod_status`) as `pod_status`,
                           MAX(`item`.`pod_related`) as `pod_related`,
                           MAX(`md`.`mat_doc_sn`) as `mat_doc_sn`,
                           MAX(`md`.`mat_doc_items`) as `mat_doc_items`,
                           MAX(`md`.`year`) as `year`,
                           MAX(`md`.`express_delivery`) as `express_delivery`,
                           MAX(`md`.`auto_mark`) AS `auto_mark`,
                           MAX(`header`.`posting_date`) as `posting_date`,
                           MAX(`partner`.`business_partner_code`) AS `dn_customer_code`,
                           MAX(`partner`.`business_partner_name`) AS `dn_customer_name`,
                           MAX(( CASE WHEN `item`.`special_inventory_status1` IN ('CC', 'C') THEN `partner`.`business_partner_code` ELSE '' END )) AS `customer_code`,
                           MAX(( CASE WHEN `item`.`special_inventory_status1` IN ('CC', 'C') THEN `partner`.`business_partner_name` ELSE '' END )) AS `customer_name`,
                           MAX(`partner2`.`business_partner_code`) AS `destination_customer_code`,
                           MAX(`partner2`.`business_partner_name`) AS `destination_customer_name`,
                           MAX(`partner2`.`business_partner_addr`) as `business_partner_addr`,
                           MAX(`partner2`.`contact_person`) as `contact_person`,
                           MAX(`partner2`.`contact_number`) as `contact_number`,
                           MAX(`sales`.`customer_order`) as `customer_order`,
                           MAX(`item`.`create_id`) as `create_id`,
                           MAX(`t_system_user`.`name`) AS `create_name`,
                           MAX(`item`.`create_time`) as `create_time`,
                           MAX(`item`.`so_sn`) AS `so_sn`,
                           MAX(`item`.`so_items`) as `so_items`,
                           MAX(`alloc`.`mat_code`) as `mat_code`,
                           MAX(`material`.`mat_description`) AS `mat_descr`,
                           MAX(`item`.`planned_delivery_quantity`) as `planned_delivery_quantity`,
                           MAX(`alloc`.`external_mat_code`) as `external_mat_code`,
                           MAX(`alloc`.`picking_document`) as `picking_document`,
                           MAX(`mt`.`mat_description`) AS `external_mat_descr`,
                           MAX(`item`.`cust_mat_code`) as `cust_mat_code`,
                           MAX(`cmmd`.`cust_mat_code_description`) AS `cust_mat_code_description`,
                           MAX(CONCAT(CONCAT( `item`.`packing_status`, ' '), `t_so_status_record`.`status_description` )) AS `packing_status`,
                           MAX(CONCAT(CONCAT( `alloc`.`posting_status`, ' '), `t_so_status_record2`.`status_description` )) AS `posting_status`,
                           MAX(CONCAT(CONCAT( `header`.`pod_status`, ' '), `t_so_status_record3`.`status_description` )) AS `pod_status`,
                           MAX(CONCAT(CONCAT( `header`.`billing_status`, ' '), `t_so_status_record4`.`status_description` )) AS `billing_status`,
                           MAX(`item`.`plant_code`) as `plant_code`,
                           MAX(`t_os_plant`.`plant_description`) AS `plant_name`,
                           MAX(`mv`.`post_code`) AS `post_code`,
                           CURRENT_DATE AS `document_date`,
                           MAX(( CASE WHEN `header`.`packing_status` = 'C' AND (`header`.`posting_status` = 'A' OR `header`.`posting_status` = 'B')  THEN CURRENT_DATE ELSE `header`.`posting_date` END )) AS `posting_date`,
                           MAX(`alloc`.`picked_qty`) AS `transaction_qty`,
                           MAX(`alloc`.`picked_qty`) AS `alloc_picked_qty`,
                           MAX(`alloc`.`batch_sn`) as `batch_sn`,
                           MAX(`alloc`.`picked_base_qty`) as `picked_base_qty`,
                           MAX(`alloc`.`picked_parallel_qty`) as `picked_parallel_qty`,
                           MAX(`alloc`.`transaction_uom`) as `transaction_uom`,
                           MAX(`alloc`.`basic_uom`) as `basic_uom`,
                           MAX(`alloc`.`parallel_uom`) as `parallel_uom`,
                           MAX(`alloc`.`batch_item`) as `batch_item`,
                           MAX(`sales_item`.`intercompany_purchase_order_number`) as `intercompany_purchase_order_number`,
                           MAX(`sales_item`.`intercompany_purchase_order_item_serial_number`) as `intercompany_purchase_order_item_serial_number`,
                           MAX(`alloc`.`stor_loc_code`) as `stor_loc_code`,
                           MAX(`tosal`.`stor_loc_desc`) as `stor_loc_desc`,
                           MAX(( CASE WHEN `material_cost`.`cost_uom` != '' THEN `material_cost`.`cost_uom` ELSE `material`.`basic_uom` END )) AS `batch_uom`,
                           MAX(0) AS `basic_qty`,
                           MAX(`item`.`special_inventory_status1`) as `special_inventory_status1`,
                           MAX('') AS `special_inventory_status2`,
                           MAX(( CASE WHEN `item`.`pod_related` = 1 THEN 'T' ELSE '' END )) AS `rcv_special_inventory_status2`,
                           MAX(`item`.`wbs_elements`) as `wbs_elements`,
                           MAX(`item`.`cost_center`) as `cost_center`,
                           MAX(`item`.`profit_center`) as `profit_center`,
                           MAX(`item`.`cost_uom`) as `cost_uom`,
                           MAX('') AS `rcv_vendor_code`,
                           MAX(( CASE WHEN `item`.`pod_related` = 1 THEN `item`.`plant_code` ELSE '' END )) AS `rcv_plant_code`,
                           MAX(( CASE WHEN `item`.`pod_related` = 1 THEN `alloc`.`stor_loc_code` ELSE '' END )) AS `rcv_stor_loc_code`,
                           MAX(( CASE WHEN `item`.`pod_related` = 1 THEN `item`.`special_inventory_status1` ELSE '' END )) AS `rcv_special_inventory_status1`,
                           MAX(( CASE WHEN `item`.`pod_related` = 1 THEN `item`.`mat_code` ELSE '' END )) AS `rcv_mat_code`,
                           MAX(( CASE WHEN `item`.`pod_related` = 1 THEN `alloc`.`batch_sn` ELSE '' END )) AS `rcv_batch_sn`,
                           MAX(( CASE WHEN `item`.`pod_related` = 1 AND `item`.`special_inventory_status1` = 'CC' THEN `partner`.`business_partner_code` ELSE '' END )) AS `rcv_customer_code`,
                           MAX(( CASE WHEN `item`.`pod_related` = 1 AND `item`.`special_inventory_status1` = 'S' THEN `item`.`so_sn` ELSE '' END )) AS `rcv_so_sn`,
                           MAX(( CASE WHEN `item`.`pod_related` = 1 AND `item`.`special_inventory_status1` = 'S' THEN `item`.`so_items` ELSE 0 END )) AS `rcv_so_items`
                           '''
        query_sql = '''
                       WITH
                       `md_item_new` AS(
                           {}
                       )
                       SELECT {}
                       FROM
                           `t_dn_inventory_alloc` AS `alloc`
                           LEFT JOIN `t_dn_item` AS `item`  ON `item`.`dn_sn` = `alloc`.`dn_sn` AND `item`.`dn_item` = `alloc`.`dn_item`
                           LEFT JOIN `t_dn_header` AS `header` ON `header`.`dn_sn` = `item`.`dn_sn`
                           LEFT JOIN `md_item_new` AS `md` ON `alloc`.`picking_document` = `md`.`picking_document` AND `item`.`dn_sn` = `md`.`rel_dn_sn` AND `item`.`dn_item` = `md`.`rel_dn_item` AND `md`.`reversal_mark` != 1 AND `md`.`reversed_mark` != 1
                           LEFT JOIN `t_documents_business_partner` AS `partner` ON `item`.`dn_sn` = `partner`.`doc_sn` AND `partner`.`business_partner_type` = 'SP' AND `partner`.`document_category` = 'SDLV'
                           LEFT JOIN `t_documents_business_partner` AS `partner2` ON `item`.`dn_sn` = `partner2`.`doc_sn` AND `partner2`.`business_partner_type` = 'DP'
                           LEFT JOIN `t_sales_order_header` AS `sales` ON `sales`.`so_sn` = `item`.`so_sn`
                           LEFT JOIN `t_sales_order_item` AS `sales_item` ON `sales_item`.`so_sn` = `item`.`so_sn` AND `sales_item`.`so_items` = `item`.`so_items`
                           LEFT JOIN `t_os_plant` AS `t_os_plant` ON `t_os_plant`.`plant_code` = `item`.`plant_code`
                           LEFT JOIN `t_system_user` AS `t_system_user` ON `item`.`create_id` = `t_system_user`.`id`
                           LEFT JOIN `t_so_status_record` AS `t_so_status_record` ON `t_so_status_record`.`state_value` = `header`.`packing_status` AND `t_so_status_record`.`field` = 'packing_status'
                           LEFT JOIN `t_so_status_record` AS `t_so_status_record2` ON `t_so_status_record2`.`state_value` = `header`.`posting_status` AND `t_so_status_record2`.`field` = 'posting_status'
                           LEFT JOIN `t_so_status_record` AS `t_so_status_record3` ON `t_so_status_record3`.`state_value` = `header`.`pod_status` AND `t_so_status_record3`.`field` = 'pod_status'
                           LEFT JOIN `t_so_status_record` AS `t_so_status_record4` ON `t_so_status_record4`.`state_value` = `header`.`billing_status` AND `t_so_status_record4`.`field` = 'billing_status'
                           LEFT JOIN `t_os_plant_storage_location_alloc` AS `tosal` ON `tosal`.`plant_code` = `item`.`plant_code` AND `tosal`.`stor_loc_code` = `alloc`.`stor_loc_code`
                           LEFT JOIN `t_mmd_material_cost_data` AS `material_cost` ON `item`.`mat_code` = `material_cost`.`mat_code` AND `item`.`plant_code` = `material_cost`.`plant_code`
                           LEFT JOIN `t_mmd_material_basic_data` AS `material` ON `alloc`.`mat_code` = `material`.`mat_code`
                           LEFT JOIN `t_mmd_material_basic_data` AS `mt` ON `alloc`.`external_mat_code` = `mt`.`mat_code`
                           LEFT JOIN `t_cust_mat_master_data` AS `cmmd` ON `item`.`cust_mat_code` = `cmmd`.`cust_mat_code`
                           LEFT JOIN `t_movement_type` AS `mv` ON `item`.`movement_type` = `mv`.`movement_type`
                           LEFT JOIN `t_dn_type` AS `dt` ON `dt`.`dn_type` = `header`.`dn_type`
                       WHERE
                           `alloc`.`posting_status` = 'C'
                           AND `alloc`.`pod_status` IN ('A', 'D')
                       '''.format(md_item_sql, columns)
        where_sql = f"""  and `alloc`.`picking_document` = '{item.get('picking_document')}' """
        group_sql = " group by `alloc`.`id` "
        query_sql += where_sql + group_sql
        db = DbHelper()
        ret = db.query_sql(query_sql, printSql=True)
        if ret:
            for i in ret:
                i["posting_date"] = item.get("posting_date")
                i["reversal_date"] = item.get("reversal_date")
            #     i["express_delivery"] = item.get("express_delivery", "")
            new_data.extend(ret)
    if not new_data:
        return ResponseData(203, "没有查询到符合数据的数据，请检查", data=data)
    return dnReversalFunc(new_data)


def dnReversalFunc(data):
    salesOrderItem = {}
    salesOrderList = []
    retData = []
    sh = SystemHelper()
    user_id = sh.getUserId()
    returnStatus = True
    try:
        insert_relationship_data = []
        exits_mat_doc_sn = {}
        for item in data:
            dn_doc_sn = item.get("mat_doc_sn", "")
            if dn_doc_sn in exits_mat_doc_sn:
                pod_rever_dic = exits_mat_doc_sn[dn_doc_sn]
                item["message"] = pod_rever_dic["message"]
                item["reversal_document"] = pod_rever_dic["reversal_document"]
                retData.append(item)
                continue
            postHead = {
                "mat_doc_sn": item.get("mat_doc_sn"),
                "year": item.get("year"),
                "posting_date": item.get("reversal_date"),
                "summary_unique_number": "",
            }
            # postItem = [item.get("mat_doc_items")]
            postItem = []
            logger.printInfo("postHead", postHead)
            logger.printInfo("postItem", postItem)

            # error_list = []
            # 先走增强校验-sap开票状态校验
            code, msg, error_list = ZZEXT_opt_item(
                **{**locals(), "user_id": user_id, "item": item, "func_name": "dnReversalFunc"})
            if code == 200:
                code, msg, error_list, mat_doc_sn, year = reverse_data(user_id, postHead, postItem)

            if code == 200:
                if str(item.get("auto_created_mark")) == "1":
                    md_data = get_md_item_data(item.get("picking_document"), item.get("batch_item", ""), mat_doc_sn,
                                               item.get("estimated_delivery_date"), item.get("company_code"))
                    reversal_data = get_md_reversal_data(item.get("dn_sn"), item.get("dn_item"))
                    postHead = {
                        "mat_doc_sn": reversal_data.get("mat_doc_sn"),
                        "year": item.get("reversal_date").split("-")[0],
                        "posting_date": item.get("reversal_date"),
                        "summary_unique_number": "",
                    }

                    postItem = []
                    code, msg, error_list, reversal_mat_document_sn, year = reverse_data(user_id, postHead, postItem)
                    md_data1 = get_md_item_data(item.get("picking_document"), item.get("batch_item", ""),
                                                reversal_mat_document_sn, item.get("estimated_delivery_date"),
                                                item.get("company_code"))
                    insert_relationship_data.append(
                        {
                            "picking_document": item.get("picking_document", ""),
                            "batch_item": item.get("batch_item", ""),
                            "reversal_document": mat_doc_sn,
                            "reversal_document_item": md_data.get("mat_doc_items"),
                            "po_sn": item.get("po_sn", ""),
                            "po_items": item.get("po_items", ""),
                            "reversal_mat_document_sn": reversal_mat_document_sn,
                            "reversal_mat_document_item": md_data1.get("mat_doc_items", ""),
                        })

                item["message"] = "冲销成功"
                item["reversal_document"] = mat_doc_sn
                exits_mat_doc_sn[dn_doc_sn] = {
                    "message": item.get("message", ""),
                    "reversal_document": item.get("reversal_document", "")
                }
                retData.append(item)

            else:
                returnStatus = False
                if error_list:
                    msg = ",".join(error_list)
                    item["message"] = msg
                else:
                    if msg:
                        item["message"] = msg
                    else:
                        item["message"] = "冲销失败"
                retData.append(item)
        for key, value in salesOrderItem.items():
            so_sn, so_item = key
            salesOrderList.append({"so_sn": so_sn, "so_item": so_item, "post_qty": value})

        # updatePosingDataStatus("reset", post_type="dn", heardData=insertHeade, itemData=insertItem,
        #                        salesData=salesOrderList)
        if insert_relationship_data:
            DuplicateSQLKey = ["reversal_document", "reversal_document_item", "reversal_mat_document_sn",
                               "reversal_mat_document_item"]
            insert_picking_company_posting_relationship(insert_relationship_data, DuplicateSQLKey)
    except Exception as e:
        traceback_str = traceback.format_exc()
        print("traceback_str>?>>>", traceback_str)
        return ResponseData(ResponseStatusCode.Error, "程序错误：" + str(e), data=retData)
    return ResponseData(ResponseStatusCode.Success if returnStatus else ResponseStatusCode.Error,
                        "成功" if returnStatus else "请查看详细消息", retData)


def PODPostFuncAPI(data):
    md_item_sql = get_pi_invoice_item_view()
    exit_picking_document = []
    new_data = []
    for item in data:
        if item.get("picking_document") in exit_picking_document:
            continue
        exit_picking_document.append(item.get("picking_document"))
        columns = '''
                           MAX(`alloc`.`id`) as `id`,
                           MAX(`header`.`posting_date`) as `posting_date`,
                           MAX(`item`.`dn_sn`) as `dn_sn`,
                           MAX(`item`.`dn_item`) as `dn_item`,
                           MAX(`item`.`so_items`) as `so_items`,
                           MAX(`item`.`pod_related`) as `pod_related`,
                           MAX(`item`.`posted_pod_qty`) as `posted_pod_qty`,
                           MAX(`item`.`basic_qty`) as `basic_qty`,
                           MAX(`item`.`basic_uom`) as `basic_uom`,
                           MAX(`item`.`cost_uom`) as `cost_uom`,
                           MAX(`item`.`create_time`) as `create_time`,
                           MAX(`item`.`planned_delivery_quantity`) as `planned_delivery_quantity`,
                           MAX(`item`.`cust_mat_code`) as `cust_mat_code`,
                           MAX(`item`.`plant_code`) as `plant_code`,
                           MAX(`item`.`movement_type`) as `movement_type`,
                           MAX(`item`.`movement_type_it`) as `movement_type_it`,
                           MAX(`item`.`wbs_elements`) as `wbs_elements`,
                           MAX(`item`.`cost_center`) as `cost_center`,
                           MAX(`item`.`profit_center`) as `profit_center`,
                           MAX(`item`.`special_inventory_status1`) as `special_inventory_status1`,
                           MAX(`item`.`cost_business_object`) as `cost_business_object`,
                           MAX(`item`.`cost_business_object1`) as `cost_business_object1`,
                           MAX(`md`.`mat_doc_sn`) as `mat_doc_sn`,
                           MAX(`md`.`mat_doc_items`) as `mat_doc_items`,
                           MAX(`alloc`.`mat_code`) as `mat_code`,
                           MAX(`alloc`.`stor_loc_code`) as `stor_loc_code`,
                           MAX(`tosol`.`stor_loc_desc`) as `stor_loc_desc`,
                           MAX(`alloc`.`external_mat_code`) as `external_mat_code`,
                           MAX(`alloc`.`batch_sn`) as `batch_sn`,
                           MAX(`alloc`.`picking_document`) as `picking_document`,
                           MAX(`alloc`.`picked_base_qty`) as `picked_base_qty`,
                           MAX(`alloc`.`picked_parallel_qty`) as `picked_parallel_qty`,
                           MAX(`alloc`.`transaction_uom`) as `transaction_uom`,
                           MAX(`alloc`.`parallel_uom`) as `parallel_uom`,
                           MAX(`alloc`.`basic_uom`) as `basic_uom`,
                           MAX(`alloc`.`batch_item`) as `batch_item`,
                           MAX(`partner2`.`business_partner_addr`) as `business_partner_addr`,
                           MAX(`partner2`.`contact_person`) as `contact_person`,
                           MAX(`partner2`.`contact_number`) as `contact_number`,
                           MAX(`sales`.`customer_order`) as `customer_order`,
                           MAX(`sales_item`.`intercompany_purchase_order_number`) as `intercompany_purchase_order_number`,
                           MAX(`sales_item`.`intercompany_purchase_order_item_serial_number`) as `intercompany_purchase_order_item_serial_number`,
                           MAX(`item`.`so_sn`) as `so_sn`,
                           MAX(`cmmd`.`cust_mat_code_description`) as `cust_mat_code_description`,
                           MAX(`alloc`.`picked_qty`) AS `transaction_qty`,
                           MAX(`partner`.`business_partner_code`) AS `dn_customer_code`,
                           MAX(`partner`.`business_partner_name`) AS `dn_customer_name`,
                           MAX(`partner2`.`business_partner_code`) AS `destination_customer_code`,
                           MAX(`partner2`.`business_partner_name`) AS `destination_customer_name`,
                           MAX(`t_system_user`.`name`) AS `create_name`,
                           MAX(`material`.`mat_description`) AS `mat_descr`,
                           MAX(`mt`.`mat_description`) AS `external_mat_descr`,
                           MAX(`header`.`billing_status`) AS `header_billing_status`,
                           MAX(`header`.`estimated_delivery_date`) as `estimated_delivery_date`,
                           MAX(`t_os_plant`.`plant_description`) AS `plant_name`,
                           MAX(`mv`.`post_code`) AS `post_code`,
                           MAX(`header`.`packing_status`) AS `header_packing_status`,
                           MAX(`header`.`pod_status`) AS `header_pod_status`,
                           MAX(`header`.`posting_status`) AS `header_posting_status`,
                           MAX(( CASE WHEN `item`.`special_inventory_status1` = 'CC' THEN `partner`.`business_partner_code` ELSE '' END )) AS `customer_code`,
                           MAX(( CASE WHEN `item`.`special_inventory_status1` = 'CC' THEN `partner`.`business_partner_name` ELSE '' END )) AS `customer_name`,
                           MAX(concat( `item`.`packing_status`, ' ', `t_so_status_record`.`status_description` )) AS `packing_status`,
                           MAX(concat( `header`.`posting_status`, ' ', `t_so_status_record2`.`status_description` )) AS `posting_status`,
                           MAX(concat( `header`.`pod_status`, ' ', `t_so_status_record3`.`status_description` )) AS `pod_status`,
                           MAX(concat( `header`.`billing_status`, ' ', `t_so_status_record4`.`status_description` )) AS `billing_status`,
                           MAX(( CASE WHEN `material_cost`.`cost_uom` != '' THEN `material_cost`.`cost_uom` ELSE `material`.`basic_uom` END )) AS `batch_uom`,
                           MAX(( CASE WHEN `item`.`special_inventory_status1` = 'S' THEN `item`.`so_sn` ELSE '' END )) AS `post_so_sn`,
                           MAX(( CASE WHEN `item`.`special_inventory_status1` = 'S' THEN `item`.`so_items` ELSE '' END )) AS `post_so_items`,
                           MAX(( CASE WHEN `item`.`pod_related` = 1 THEN 'T' ELSE '' END )) AS `special_inventory_status2`,
                           MAX(( CASE WHEN `item`.`pod_related` = 1 THEN 'T' ELSE '' END )) AS `rcv_special_inventory_status2`,
                           MAX(0) AS `basic_qty`,
                           MAX(CURRENT_DATE) AS `document_date`,
                           MAX('') AS `rcv_vendor_code`,
                           MAX('') AS `rcv_plant_code`,
                           MAX('') AS `rcv_stor_loc_code`,
                           MAX('') AS `rcv_special_inventory_status1`,
                           MAX('') AS `rcv_mat_code`,
                           MAX('') AS `rcv_batch_sn`,
                           MAX('') AS `rcv_customer_code`,
                           MAX('') AS `rcv_so_sn`,
                           MAX('') AS `rcv_so_items`,
                           MAX('') AS `rcv_project_sn`,
                           MAX(`item`.`create_id`) as `create_id` 
                           '''
        query_sql = '''
                       WITH
                           `md_item_new` AS(
                               {}
                       )
                       SELECT {}
                       FROM
                           `t_dn_item` AS `item`
                           LEFT JOIN `t_dn_header` AS `header` ON `header`.`dn_sn` = `item`.`dn_sn`
                           LEFT JOIN `t_dn_inventory_alloc` AS `alloc` ON `item`.`dn_sn` = `alloc`.`dn_sn` AND `item`.`dn_item` = `alloc`.`dn_item`
                           LEFT JOIN `md_item_new` AS `md` ON `alloc`.`picking_document` = `md`.`picking_document` AND  `item`.`dn_sn` = `md`.`rel_dn_sn` AND `item`.`dn_item` = `md`.`rel_dn_item`
                           LEFT JOIN `t_documents_business_partner` AS `partner` ON `item`.`dn_sn` = `partner`.`doc_sn` AND `partner`.`business_partner_type`  = 'SP' AND `partner`.`document_category` = 'SDLV'
                           LEFT JOIN `t_documents_business_partner` AS `partner2` ON `item`.`dn_sn` = `partner2`.`doc_sn` AND `partner2`.`business_partner_type` = 'DP'
                           LEFT JOIN `t_sales_order_header` AS `sales` ON `sales`.`so_sn` = `item`.`so_sn`
                           LEFT JOIN `t_sales_order_item` AS `sales_item` ON `sales_item`.`so_sn` = `item`.`so_sn` and `sales_item`.`so_items` = `item`.`so_items`
                           LEFT JOIN `t_os_plant` ON `t_os_plant`.`plant_code` = `item`.`plant_code`
                           LEFT JOIN `t_system_user` ON `item`.`create_id` = `t_system_user`.`id`
                           LEFT JOIN `t_so_status_record` ON `t_so_status_record`.`state_value` = `header`.`packing_status` AND `t_so_status_record`.`field` = 'packing_status'
                           LEFT JOIN `t_so_status_record` AS `t_so_status_record2` ON `t_so_status_record2`.`state_value` = `header`.`posting_status` AND `t_so_status_record2`.`field` = 'posting_status'
                           LEFT JOIN `t_so_status_record` AS `t_so_status_record3` ON `t_so_status_record3`.`state_value` = `header`.`pod_status` AND `t_so_status_record3`.`field` = 'pod_status'
                           LEFT JOIN `t_so_status_record` AS `t_so_status_record4` ON `t_so_status_record4`.`state_value` = `header`.`billing_status` AND `t_so_status_record4`.`field` = 'billing_status'
                           LEFT JOIN `t_os_plant_storage_location_alloc` AS `tosol` ON `tosol`.`plant_code` = `item`.`plant_code` AND `tosol`.`stor_loc_code` = `alloc`.`stor_loc_code`
                           LEFT JOIN `t_mmd_material_cost_data` AS `material_cost` ON `item`.`mat_code` = `material_cost`.`mat_code`
                           LEFT JOIN `t_mmd_material_basic_data` AS `material` ON `alloc`.`mat_code` = `material`.`mat_code`
                           LEFT JOIN `t_mmd_material_basic_data` AS `mt` ON `alloc`.`external_mat_code` = `mt`.`mat_code`
                           LEFT JOIN `t_movement_type` AS `mv` ON `item`.`movement_type` = `mv`.`movement_type`
                           LEFT JOIN `t_cust_mat_master_data` as `cmmd` ON `item`.`cust_mat_code` = `cmmd`.`cust_mat_code`
                       WHERE
                           1 = 1
                           AND `alloc`.`posting_status` = 'C'
                           AND `alloc`.`pod_status` = 'A'
                       '''.format(md_item_sql, columns)
        where_sql = f"""  and `alloc`.`picking_document` = '{item.get('picking_document')}' """
        group_sql = " group by `alloc`.`id`"
        query_sql += where_sql + group_sql
        db = DbHelper()
        ret = db.query_sql(query_sql)
        if ret:
            for i in ret:
                i["posting_date"] = item.get("confirm_delivery_date")
                i["confirm_delivery_date"] = item.get("confirm_delivery_date")
            new_data.extend(ret)
    if not new_data:
        return ResponseData(203, "没有查询到符合数据的数据，请检查", data=data)
    return PODPostFunc(new_data)


def PODPostFunc(data):
    retData = []
    sh = SystemHelper()
    user_id = sh.getUserId()
    returnStatus = True
    overCreditStatus = False
    # print("PODPostFunc data1", data)
    try:
        postData = {}
        dn_line_id = {}
        line_id = 1
        picking_document_exits = set()
        for item in data:
            if not item.get("picking_document"):
                returnStatus = False
                item["message"] = "拣配单号必输"
                retData.append(item)
                continue
            if not item.get("posting_date"):
                returnStatus = False
                item["message"] = "过账日期必输"
                retData.append(item)
                continue
            picking_document_code = item.get("picking_document", "")
            if picking_document_code in picking_document_exits:
                continue
            else:
                picking_document_exits.add(picking_document_code)
            # logger.printInfo("item", item)
            # postHead = PostHead(post_code=item.get("post_code"), document_date=get_now_date_str(),
            #                     posting_date=item.get("confirm_delivery_date"),
            #                     auto_created_mark=item.get("auto_created_mark"),
            #                     picking_document=item.get("picking_document"),
            #                     ztype="B"
            #                     )
            inventory_alloc_data = get_inventory_alloc(item.get("picking_document"))
            if not inventory_alloc_data:
                return ResponseData(ResponseStatusCode.Error,
                                    f"""拣配单：{item.get("picking_document")} 拣配单行号：{item.get("batch_item")} 没有批次数据""",
                                    [])
            for new_item in inventory_alloc_data:
                # 这里进行信贷检查
                credit_control_code = new_item.get("credit_control_code")
                credit_status = new_item.get("credit_status")
                if credit_control_code != "D":
                    if credit_status == "C" or credit_status == "E":
                        returnStatus = False
                        item["message"] = f"拣配单信用状态为{credit_status},过账失败，请检查"
                        retData.append(item)
                        continue
                else:
                    if str(new_item.get("credit_activated_flag")) == "1":
                        if credit_status == "C":
                            returnStatus = False
                            item["message"] = f"拣配单信用状态为{credit_status}超额为批准,过账失败，请检查"
                            retData.append(item)
                            continue
                        else:
                            from CustLineOfCreditCalculate import getCustomerCreditData
                            from SalesPickInterface import get_credit_management
                            # 客户信用余额
                            customerCredit = getCustomerCreditData(new_item.get("customer_code"),
                                                                   get_credit_management(
                                                                       new_item.get("sales_org_code")),
                                                                   new_item.get("company_code"), )
                            occupancy_limits = customerCredit.get("occupancy_limits", 0)
                            credit_limit = customerCredit.get("credit_limit", 0)
                            if occupancy_limits > credit_limit:
                                returnStatus = False
                                overCreditStatus = True
                                item[
                                    "message"] = f"""{new_item.get("customer_code")}客户信用额度为{credit_limit}，已使用信用额度为{occupancy_limits}，信用已超额是否提交审批"""
                                retData.append(item)
                                continue
                postHead = PostHead(post_code=new_item.get("post_code_pod"), document_date=get_now_date_str("%Y-%m-%d"),
                                    posting_date=item.get("posting_date"),
                                    auto_created_mark="",
                                    picking_document=item.get("picking_document"),
                                    ztype="B"
                                    )
                if new_item.get("cost_uom") == new_item.get("basic_uom"):
                    batch_qty = new_item.get("picked_base_qty")
                elif new_item.get("cost_uom") == new_item.get("parallel_uom"):
                    batch_qty = new_item.get("picked_parallel_qty")
                else:
                    code, msg, qty = convert_material_unit_qty(new_item.get("mat_code"), new_item["basic_uom"],
                                                               new_item["cost_uom"],
                                                               new_item["picked_base_qty"])
                    if code == 200:
                        batch_qty = qty
                    else:
                        code, msg, qty = convert_material_unit_qty(new_item.get("mat_code"),
                                                                   new_item["parallel_uom"],
                                                                   new_item["cost_uom"],
                                                                   new_item["picked_parallel_qty"])
                        if code == 200:
                            batch_qty = qty
                        else:
                            return ResponseData(ResponseStatusCode.Error, msg, [])
                rcv_plant_code = ""
                rcv_stor_loc_code = ""
                rcv_special_inventory_status1 = ""
                rcv_special_inventory_status2 = ""
                rcv_mat_code = ""
                rcv_customer_code = ""
                rcv_so_sn = ""
                rcv_so_items = ""
                rcv_project_sn = ""
                rcv_inventory_status = "0"
                rcv_batch_sn = ""
                rcv_proof_flag = ""
                postItem = PostItem(rel_dn_sn=item.get("dn_sn"),
                                    rel_dn_item=new_item.get("rel_dn_item"),
                                    customer_code=item.get("customer_code"),
                                    rel_so_sn=item.get("so_sn"),
                                    rel_so_items=new_item.get("rel_so_items"),
                                    mat_code=new_item.get("mat_code"),
                                    transaction_uom=new_item.get("transaction_uom"),
                                    transaction_qty=new_item.get("transaction_qty"),
                                    plant_code=new_item.get("plant_code"),
                                    stor_loc_code=new_item.get("stor_loc_code"),
                                    inventory_status="0",
                                    batch_sn=new_item.get("batch_sn"),
                                    express_delivery=item.get("express_delivery"),
                                    special_inventory_status1=new_item.get("special_inventory_status1", ""),
                                    special_inventory_status2=item.get("special_inventory_status2", ""),
                                    movement_type=item.get("movement_type"),
                                    wbs_elements=new_item.get("wbs_elements"),
                                    cost_center=new_item.get("cost_center"),
                                    profit_center=new_item.get("profit_center"),
                                    project_sn=item.get("project_sn"),
                                    basic_qty=new_item.get("picked_base_qty"),
                                    basic_uom=new_item.get("basic_uom"),
                                    batch_qty=batch_qty,
                                    batch_uom=new_item.get("cost_uom"),
                                    parallel_qty=new_item.get("picked_parallel_qty"),
                                    parallel_uom=new_item.get("parallel_uom"),
                                    cost_business_object=item.get("cost_business_object"),
                                    cost_business_object1=item.get("cost_business_object1"),
                                    rcv_plant_code=rcv_plant_code,
                                    rcv_stor_loc_code=rcv_stor_loc_code,
                                    rcv_special_inventory_status1=rcv_special_inventory_status1,
                                    rcv_special_inventory_status2=rcv_special_inventory_status2,
                                    rcv_mat_code=rcv_mat_code,
                                    rcv_customer_code=rcv_customer_code,
                                    rcv_so_sn=rcv_so_sn,
                                    rcv_so_items=rcv_so_items,
                                    rcv_project_sn=rcv_project_sn,
                                    rcv_inventory_status=rcv_inventory_status,
                                    rcv_batch_sn=rcv_batch_sn,
                                    proof_flag=new_item.get("pod_related"),
                                    rcv_proof_flag=rcv_proof_flag,
                                    pod_related=new_item.get("pod_related", 0),
                                    picking_document=item.get("picking_document"),
                                    batch_item=new_item.get("batch_item"),
                                    )

                if new_item.get("picking_document") in postData:
                    dn_line_id[new_item.get("picking_document")] += 1
                    postItem.line_id = dn_line_id.get(new_item.get("picking_document"))
                    postData[new_item.get("picking_document")]["items"].append(postItem.__dict__)
                else:
                    postItem.line_id = line_id
                    dn_line_id[new_item.get("picking_document")] = line_id
                    postData[new_item.get("picking_document")] = {}
                    postData[new_item.get("picking_document")]["header"] = postHead.__dict__
                    postData[new_item.get("picking_document")]["items"] = [postItem.__dict__]
        for k, idata in postData.items():
            # logger.printInfo("idata", idata)
            start_time = time.time()
            code, msg, error_list, mat_doc_sn, year = postFunc(test_run, user_id, idata["header"], idata["items"],
                                                               typer="pod")
            print("postFunc end time:", time.time() - start_time)
            if code == 200:
                # insertHeade.append({"dn_sn": item.get("dn_sn"), "dn_item": item.get("dn_item"), "post_status": "C"})
                # insertItem.append(
                #     {"rel_dn_sn": item.get("dn_sn"), "rel_dn_item": item.get("dn_item"),
                #      "posted_pod_qty": item.get("unposted_pod_qty")})
                # if salesOrderItem.get((item.get("so_sn"), item.get("so_item"))):
                #     salesOrderItem[(item.get("so_sn"), item.get("so_item"))] += postItem.transaction_qty
                # else:
                #     salesOrderItem[(item.get("so_sn"), item.get("so_item"))] = postItem.transaction_qty
                for item in data:
                    if item["picking_document"] == k:
                        item["message"] = "过账成功"
                        item["pod_doc_sn"] = mat_doc_sn
                        retData.append(item)
            else:
                returnStatus = False
                if error_list:
                    msg = ",".join(error_list)
                for item in data:
                    if item["picking_document"] == k:
                        item["message"] = msg
                        retData.append(item)
        # for key, value in salesOrderItem.items():
        #     so_sn, so_item = key
        #     salesOrderList.append({"so_sn": so_sn, "so_item": so_item, "post_qty": value})
        # updatePosingDataStatus("post", post_type="pod", heardData=insertHeade, itemData=insertItem,
        #                        salesData=salesOrderList)
    except Exception as e:
        return ResponseData(ResponseStatusCode.Error, "程序错误：" + str(e), data=retData)
    if overCreditStatus:
        return ResponseData(203, "有信用超额的数据请查看详细信息", data=retData)

    else:
        return ResponseData(ResponseStatusCode.Success if returnStatus else ResponseStatusCode.Error,
                            "成功" if returnStatus else "请查看详细消息", retData)


def PODReversalFuncAPI(data):
    logger.printInfo("PODReversalFuncAPI>>>data", data)
    md_item_sql = get_pi_invoice_item_view()
    exit_picking_document = []
    new_data = []
    for item in data:
        if item.get("picking_document") in exit_picking_document:
            continue
        exit_picking_document.append(item.get("picking_document"))
        columns = '''
                           MAX(`alloc`.`id`) as `id`,
                           MAX(`header`.`posting_date`) as `posting_date`,
                           MAX(`item`.`dn_sn`) as `dn_sn`,
                           MAX(`item`.`dn_item`) as `dn_item`,
                           MAX(`item`.`pod_related`) as `pod_related`,
                           MAX(`item`.`posted_pod_qty`) as `posted_pod_qty`,
                           MAX(`item`.`basic_qty`) as `basic_qty`,
                           MAX(`item`.`basic_uom`) as `basic_uom`,
                           MAX(`item`.`cost_uom`) as `cost_uom`,
                           MAX(`item`.`create_time`) as `create_time`,
                           MAX(`item`.`planned_delivery_quantity`) as `planned_delivery_quantity`,
                           MAX(`item`.`cust_mat_code`) as `cust_mat_code`,
                           MAX(`item`.`movement_type`) as `movement_type`,
                           MAX(`item`.`plant_code`) as `plant_code`,
                           MAX(`item`.`movement_type_it`) as `movement_type_it`,
                           MAX(`item`.`wbs_elements`) as `wbs_elements`,
                           MAX(`item`.`cost_center`) as `cost_center`,
                           MAX(`item`.`profit_center`) as `profit_center`,
                           MAX(`item`.`special_inventory_status1`) as `special_inventory_status1`,
                           MAX(`md`.`mat_doc_sn`) as `mat_doc_sn`,
                           MAX(`md`.`year`) as `year`,
                           MAX(`alloc`.`mat_code`) as `mat_code`,
                           MAX(`alloc`.`stor_loc_code`) as `stor_loc_code`,
                           MAX(`tosol`.`stor_loc_desc`) as `stor_loc_desc`,
                           MAX(`alloc`.`external_mat_code`) as `external_mat_code`,
                           MAX(`alloc`.`picking_document`) as `picking_document`,
                           MAX(`alloc`.`batch_sn`) as `batch_sn`,
                           MAX(`alloc`.`picked_base_qty`) as `picked_base_qty`,
                           MAX(`alloc`.`picked_parallel_qty`) as `picked_parallel_qty`,
                           MAX(`alloc`.`transaction_uom`) as `transaction_uom`,
                           MAX(`alloc`.`basic_uom`) as `basic_uom`,
                           MAX(`alloc`.`parallel_uom`) as `parallel_uom`,
                           MAX(`alloc`.`batch_item`) as `batch_item`,
                           MAX(`partner2`.`business_partner_addr`) as `business_partner_addr`,
                           MAX(`partner2`.`contact_person`) as `contact_person`,
                           MAX(`partner2`.`contact_number`) as `contact_number`,
                           MAX(`sales`.`customer_order`) as `customer_order`,
                           MAX(`header`.`estimated_delivery_date`) as `estimated_delivery_date`,
                           MAX(`sales_item`.`intercompany_purchase_order_number`) as `intercompany_purchase_order_number`,
                           MAX(`sales_item`.`intercompany_purchase_order_item_serial_number`) as `intercompany_purchase_order_item_serial_number`,
                           MAX(`cmmd`.`cust_mat_code_description`) as `cust_mat_code_description`,
                           MAX(`item`.`so_sn`) as `display_so_sn`,
                           MAX(`item`.`so_items`) as `display_so_items`,
                           MAX(`md`.`mat_doc_sn`) as `pod_doc_sn`,
                           MAX(`md`.`mat_doc_items`) as `pod_doc_items`,
                           MAX(`md`.`auto_mark`) as `auto_mark`,
                           MAX(`alloc`.`picked_qty`) AS `transaction_qty`,
                           MAX(`alloc`.`picked_qty`) as `alloc_picked_qty`,
                           MAX(`partner`.`business_partner_code`) AS `dn_customer_code`,
                           MAX(`partner`.`business_partner_name`) AS `dn_customer_name`,
                           MAX(`partner2`.`business_partner_code`) AS `destination_customer_code`,
                           MAX(`partner2`.`business_partner_name`) AS `destination_customer_name`,
                           MAX(`t_system_user`.`name`) AS `create_name`,
                           MAX(`material`.`mat_description`) AS `mat_descr`,
                           MAX(`mt`.`mat_description`) AS `external_mat_descr`,
                           MAX(`t_os_plant`.`plant_description`) AS `plant_name`,
                           MAX(`mv`.`post_code`) AS `post_code`,
                           MAX(( CASE WHEN `item`.`special_inventory_status1` = 'CC' THEN `partner`.`business_partner_code` ELSE '' END )) AS `customer_code`,
                           MAX(( CASE WHEN `item`.`special_inventory_status1` = 'CC' THEN `partner`.`business_partner_name` ELSE '' END )) AS `customer_name`,
                           MAX(concat( `item`.`packing_status`, ' ', `t_so_status_record`.`status_description` )) AS `packing_status`,
                           MAX(concat( `header`.`posting_status`, ' ', `t_so_status_record2`.`status_description` )) AS `posting_status`,
                           MAX(concat( `header`.`pod_status`, ' ', `t_so_status_record3`.`status_description` )) AS `pod_status`,
                           MAX(concat( `header`.`billing_status`, ' ', `t_so_status_record4`.`status_description` )) AS `billing_status`,
                           MAX(( CASE WHEN `material_cost`.`cost_uom` != '' THEN `material_cost`.`cost_uom` ELSE `material`.`basic_uom` END )) AS `batch_uom`,
                           MAX(( CASE WHEN `item`.`special_inventory_status1` = 'S' THEN `item`.`so_sn` ELSE '' END )) AS `so_sn`,
                           MAX(( CASE WHEN `item`.`special_inventory_status1` = 'S' THEN `item`.`so_items` ELSE '' END )) AS `so_items`,
                           MAX(( CASE WHEN `item`.`pod_related` = 1 THEN 'T' ELSE '' END )) AS `special_inventory_status2`,
                           MAX(( CASE WHEN `item`.`pod_related` = 1 THEN 'T' ELSE '' END )) AS `rcv_special_inventory_status2`,
                           MAX(CURRENT_DATE) AS `document_date`,
                           MAX(0) AS `basic_qty`,
                           MAX('') AS `rcv_vendor_code`,
                           MAX('') AS `rcv_plant_code`,
                           MAX('') AS `rcv_stor_loc_code`,
                           MAX('') AS `rcv_special_inventory_status1`,
                           MAX('') AS `rcv_mat_code`,
                           MAX('') AS `rcv_batch_sn`,
                           MAX('') AS `rcv_customer_code`,
                           MAX('') AS `rcv_so_sn`,
                           MAX(0) AS `rcv_so_items`,
                           MAX('') AS `rcv_project_sn`,
                           MAX(`item`.`create_id`) as `create_id`
                           '''
        query_sql = '''
                       WITH
                       `md_item_new` AS(
                           {}
                       )
                       SELECT {}
                       FROM
                           `t_dn_item` AS `item`
                           LEFT JOIN `t_dn_header` AS `header` ON `header`.`dn_sn` = `item`.`dn_sn`
                           LEFT JOIN `t_dn_inventory_alloc` AS `alloc` ON `item`.`dn_sn` = `alloc`.`dn_sn` AND `item`.`dn_item` = `alloc`.`dn_item`
                           LEFT JOIN `md_item_new` AS `md` ON `alloc`.`picking_document` = `md`.`picking_document` AND  `item`.`dn_sn` = `md`.`rel_dn_sn` AND `item`.`dn_item` = `md`.`rel_dn_item` and `md`.`special_inventory_status2`='T' and `md`.`auto_mark`=0
                           LEFT JOIN `t_md_header` as `mh` on `md`.`mat_doc_sn` = `mh`.`mat_doc_sn`
                           LEFT JOIN `t_documents_business_partner` AS `partner` ON `item`.`dn_sn` = `partner`.`doc_sn` AND `partner`.`business_partner_type` = 'SP' AND `partner`.`document_category` = 'SDLV'
                           LEFT JOIN `t_documents_business_partner` AS `partner2` ON `item`.`dn_sn` = `partner2`.`doc_sn` AND `partner2`.`business_partner_type` = 'DP'
                           LEFT JOIN `t_sales_order_header` AS `sales` ON `sales`.`so_sn` = `item`.`so_sn`
                           LEFT JOIN `t_sales_order_item` AS `sales_item` ON `sales_item`.`so_sn` = `item`.`so_sn` and `sales_item`.`so_items` = `item`.`so_items`
                           LEFT JOIN `t_os_plant` ON `t_os_plant`.`plant_code` = `item`.`plant_code`
                           LEFT JOIN `t_system_user` ON `item`.`create_id` = `t_system_user`.`id`
                           LEFT JOIN `t_so_status_record` ON `t_so_status_record`.`state_value` = `header`.`packing_status` AND `t_so_status_record`.`field` = 'packing_status'
                           LEFT JOIN `t_so_status_record` AS `t_so_status_record2` ON `t_so_status_record2`.`state_value` = `header`.`posting_status` AND `t_so_status_record2`.`field` = 'posting_status'
                           LEFT JOIN `t_so_status_record` AS `t_so_status_record3` ON `t_so_status_record3`.`state_value` = `header`.`pod_status` AND `t_so_status_record3`.`field` = 'pod_status'
                           LEFT JOIN `t_so_status_record` AS `t_so_status_record4` ON `t_so_status_record4`.`state_value` = `header`.`billing_status` AND `t_so_status_record4`.`field` = 'billing_status'
                           LEFT JOIN `t_os_plant_storage_location_alloc` AS `tosol` ON `tosol`.`stor_loc_code` = `alloc`.`stor_loc_code`
                           LEFT JOIN `t_mmd_material_cost_data` AS `material_cost` ON `item`.`mat_code` = `material_cost`.`mat_code`
                           LEFT JOIN `t_mmd_material_basic_data` AS `material` ON `alloc`.`mat_code` = `material`.`mat_code`
                           LEFT JOIN `t_mmd_material_basic_data` AS `mt` ON `alloc`.`external_mat_code` = `mt`.`mat_code`
                           LEFT JOIN `t_movement_type` AS `mv` ON `item`.`movement_type` = `mv`.`movement_type`
                           LEFT JOIN `t_cust_mat_master_data` as `cmmd` ON `item`.`cust_mat_code` = `cmmd`.`cust_mat_code`
                       WHERE
                           `md`.`pod_related` = 1
                           AND (`md`.`reversal_mark` != 1 or `md`.`reversal_mark` is NULL)
                           AND (`md`.`reversed_mark` != 1 or `md`.`reversed_mark` is NULL)
                           AND (`md`.`auto_mark` != 1 or `md`.`auto_mark` is NULL)
                           AND `alloc`.`posting_status` = 'C' AND `alloc`.`pod_status`='C' AND (`header`.`billing_status` = 'A' or `header`.`billing_status` = 'D')
                       '''.format(md_item_sql, columns)
        where_sql = f"""  and `alloc`.`picking_document` = '{item.get('picking_document')}' """
        group_sql = " group by `alloc`.`id`"
        query_sql += where_sql + group_sql
        db = DbHelper()
        ret = db.query_sql(query_sql, printSql=True)
        if ret:
            # for i in ret:
            #     i["posting_date"] = item.get("posting_date")
            #     i["express_delivery"] = item.get("express_delivery", "")
            for i in ret:
                i["reversal_date"] = item["reversal_date"]
            new_data.extend(ret)
    if not new_data:
        return ResponseData(203, "没有查询到符合数据的数据，请检查", data=data)
    return PODReversalFunc(new_data)


def PODReversalFunc(data):
    """
    data:list
    """
    logger.printInfo("PODReversalFunc data>>>", data)
    salesOrderItem = {}
    salesOrderList = []
    retData = []
    sh = SystemHelper()
    user_id = sh.getUserId()
    returnStatus = True
    try:
        exits_mat_doc_sn = {}
        for item in data:
            pod_doc_sn = item.get("pod_doc_sn", "")
            if pod_doc_sn in exits_mat_doc_sn:
                pod_rever_dic = exits_mat_doc_sn[pod_doc_sn]
                item["message"] = pod_rever_dic["message"]
                item["reversal_document"] = pod_rever_dic["reversal_document"]
                retData.append(item)
                continue

            postHead = {
                "mat_doc_sn": pod_doc_sn,
                "year": item.get("year"),
                "posting_date": item.get("reversal_date"),
                "summary_unique_number": "",
            }
            # postItem = [item.get("pod_doc_items")]
            postItem = []
            # logger.printInfo("postHead", postHead)
            # logger.printInfo("postItem", postItem)

            # error_list = []
            # 先走增强校验-sap开票状态校验
            code, msg, error_list = ZZEXT_opt_item(
                **{**locals(), "user_id": user_id, "item": item, "func_name": "PODReversalFunc"})
            if code == 200:
                code, msg, error_list, mat_doc_sn, year = reverse_data(user_id, postHead, postItem)

            if code == 200:
                # insertHeade.append({"dn_sn": item.get("dn_sn"), "dn_item": item.get("dn_item")})
                # insertItem.append(
                #     {"rel_dn_sn": item.get("dn_sn"), "rel_dn_item": item.get("dn_item"),
                #      "posted_pod_qty": item.get("planned_pod_qty")})
                # if salesOrderItem.get((item.get("so_sn"), item.get("so_item"))):
                #     salesOrderItem[(item.get("so_sn"), item.get("so_item"))] += postItem.transaction_qty
                # else:
                #     salesOrderItem[(item.get("so_sn"), item.get("so_item"))] = postItem.transaction_qty
                # alloc_list.append(str(tuple([item.get("dn_sn"), item.get("dn_item")])))
                item["message"] = "冲销成功"
                item["reversal_document"] = mat_doc_sn

            else:
                returnStatus = False
                if error_list:
                    msg = ",".join(error_list)
                    item["message"] = msg
                else:
                    if msg:
                        item["message"] = msg
                    else:
                        item["message"] = "冲销失败"
            retData.append(item)
            exits_mat_doc_sn[pod_doc_sn] = {
                "message": item.get("message", ""),
                "reversal_document": item.get("reversal_document", "")
            }
        for key, value in salesOrderItem.items():
            so_sn, so_item = key
            salesOrderList.append({"so_sn": so_sn, "so_item": so_item, "post_qty": value})

        # updatePosingDataStatus("reset", post_type="pod", heardData=insertHeade, itemData=insertItem,
        #                        salesData=salesOrderList)

    except Exception as e:
        print("e>>>>", e)
        error_msg = traceback.format_exc()
        print("错误详情：", error_msg)
        return ResponseData(ResponseStatusCode.Error, "程序错误：" + str(e), data=retData)
    return ResponseData(ResponseStatusCode.Success if returnStatus else ResponseStatusCode.Error,
                        "成功" if returnStatus else "请查看详细消息", retData)


@calc_time
def insert_picking_company_posting_relationship(data, DuplicateSQLKey):
    db = DbHelper()
    # DuplicateSQLKey = ["batch_item", "doc_sn", "doc_items", "reversal_document",
    #                    "reversal_document_item", "po_sn", "po_items", "mat_doc_sn", "mat_doc_items",
    #                    "reversal_mat_document_sn", "reversal_mat_document_item"]
    status = db.batchInsertToDB("t_picking_company_posting_relationship", data, DuplicateSQLKey=DuplicateSQLKey,
                                printSql=True)
    return status


def get_picking_company_posting_relationship_db(data, DuplicateSQLKey):
    db = DbHelper()
    # DuplicateSQLKey = ["batch_item", "doc_sn", "doc_items", "reversal_document",
    #                    "reversal_document_item", "po_sn", "po_items", "mat_doc_sn", "mat_doc_items",
    #                    "reversal_mat_document_sn", "reversal_mat_document_item"]
    status = db.batchInsertToDB("t_picking_company_posting_relationship", data, DuplicateSQLKey=DuplicateSQLKey,
                                printSql=True)
    return status


@calc_time
def get_po_data_by_dn_sn(dn_sn, dn_item):
    sql = f"""
        select 
            tdi.`dn_sn`,
            tdi.`dn_item`,
            tph.`currency_code`,
            tpt.`in_stor_move`,
            tdi.`so_sn`,
            tdi.`so_items`,
            tpi.* 
        from `t_dn_item` as tdi 
        left join `t_sales_order_item` as tsoi on tdi.`so_sn` = tsoi.`so_sn` and tdi.`so_items` = tsoi.`so_items`
        left join `t_po_item` as tpi on tsoi.`intercompany_purchase_order_number`=tpi.`po_sn` and tsoi.`intercompany_purchase_order_item_serial_number` = tpi.`po_items`
        left join `t_po_header` as tph on tph.`po_sn`=tpi.`po_sn`
        left join `t_po_type` as tpt on tph.`po_type`=tpt.`po_type`
        where tdi.`dn_sn`='{dn_sn}' and tdi.`dn_item`={dn_item}
    """
    db = DbHelper()
    ret = db.query_sql(sql)
    if ret:
        return ret[0]
    else:
        return {}


def get_material_plant_data():
    sql = """ select * from `t_mmd_material_plant_data`"""
    db = DbHelper()
    data = db.query_sql(sql)
    return {(i.get("plant_code"), i.get("mat_code")): i for i in data}


@calc_time
def get_md_item_data(picking_document, picking_document_item, mat_doc_sn, estimated_delivery_date, company_code):
    if not estimated_delivery_date or not company_code:
        return {}

    year, month = estimated_delivery_date[0:4], estimated_delivery_date[5:7]

    table_name = f"t_md_item_{company_code}_{year}{month}"
    sql = f"""
        select * from `{table_name}` as tmi 
        where tmi.`picking_document` = '{picking_document}' and tmi.`picking_document_item` = {picking_document_item} and tmi.`mat_doc_sn` = {mat_doc_sn}""
    """

    db = DbHelper()
    data = db.query_sql(sql)
    if data:
        return data[0]
    else:
        return {}


def get_md_reversal_data(dn_sn, dn_item):
    sql = f"""
        select 
            tdi.`dn_sn`,
            tdi.`dn_item`,
            tph.`currency_code`,
            tpt.`in_stor_move`,
            tdi.`so_sn`,
            tdi.`so_items`,
            tmi.`mat_doc_sn`,
            tpi.*
        from `t_dn_item` as tdi 
        left join `t_sales_order_item` as tsoi on tdi.`so_sn` = tsoi.`so_sn` and tdi.`so_items` = tsoi.`so_items`
        left join `t_po_item` as tpi on tsoi.`intercompany_purchase_order_number`=tpi.`po_sn` and tsoi.`intercompany_purchase_order_item_serial_number` = tpi.`po_items`
        left join `t_po_header` as tph on tph.`po_sn`=tpi.`po_sn`
        left join `t_po_type` as tpt on tph.`po_type`=tpt.`po_type`
        left join `t_md_item` as tmi on tmi.`rel_po_sn`=tpi.`po_sn` and tmi.`rel_po_items` = tpi.`po_items`
        left join `t_md_header` as tmh on tmh.`mat_doc_sn`=tmi.`mat_doc_sn` 
        where tdi.`dn_sn`='{dn_sn}' and tdi.`dn_item`={dn_item} and tmi.`reversal_mark`=0 and tmi.`reversed_mark` = 0 and tmh.`post_code`='1'
    """
    db = DbHelper()
    data = db.query_sql(sql)
    if data:
        return data[0]
    else:
        return {}


@calc_time
def get_inventory_alloc(picking_document, dn_sn=None, dn_item=None, batch_item=None):
    sql = f""" SELECT 
                tdia.*,
                tdia.`picked_qty` as `transaction_qty`,
                td.`plant_code` AS `plant_code`,
                td.`special_inventory_status1` AS `special_inventory_status1`,
                td.`pod_related` AS `pod_related`,
                CASE
                   WHEN td.`pod_related` = 1 THEN td.`movement_type_it`
                   ELSE td.`movement_type`
                END AS `movement_type`,
                td.`dn_sn` AS `rel_dn_sn`,
                td.`dn_sn` AS `dn_sn`,
                td.`dn_item` AS `rel_dn_item`,
                td.`dn_item` AS `dn_item`,
                td.`so_sn` AS `so_sn`,
                td.`so_sn` AS `rel_so_sn`,
                td.`so_items` AS `so_items`,
                td.`so_items` AS `rel_so_items`,
                CASE
                   WHEN td.`special_inventory_status1` = 'S' THEN  td.`so_sn`
                   ELSE ''
                END AS `so_sn`,
                CASE
                   WHEN td.`special_inventory_status1` = 'S' THEN  td.`so_items`
                   ELSE 0
                END AS `so_items`,
                td.`wbs_elements` AS `wbs_elements`,
                td.`cost_center` AS `cost_center`,
                td.`cost_business_object1` AS `cost_business_object1`,
                td.`cost_business_object` AS `cost_business_object`,
                td.`profit_center` AS `profit_center`,
                CASE
                   WHEN td.`pod_related` = 1 THEN 'T'
                   ELSE ''
                END AS `rcv_special_inventory_status2`,
                cat.`rcv_special_inventory_status1` AS `rcv_special_inventory_status1`,
                cat.`credit_activated_flag` AS `credit_activated_flag`,
                COALESCE(mt0.`post_code`, mt1.`post_code`) AS `post_code`,
                mt2.`post_code` AS `post_code_pod`,
                td.`transaction_uom` AS `transaction_uom`,
                td.`basic_uom` AS `basic_uom`,
                td.`cost_uom` AS `cost_uom`,
                td.`parallel_uom` AS `parallel_uom`,
                td.`sales_org_code` AS `sales_org_code`,
                tdia.`picked_base_qty` AS `picked_base_qty`,
                tdia.`picked_parallel_qty` AS `picked_parallel_qty`,
                tdh.`company_code` AS `company_code`,
                tdh.`customer_code` AS `customer_code`
                -- IF(td.special_inventory_status1 = 'CC', tdbp.business_partner_code, '') AS customer_code
            FROM `t_dn_inventory_alloc` AS tdia 
            LEFT JOIN `t_dn_item` AS td  ON tdia.`dn_sn` = td.`dn_sn` AND tdia.`dn_item` = td.`dn_item`
            LEFT JOIN `t_dn_header` AS tdh  ON tdh.`dn_sn` = td.`dn_sn` 
            LEFT JOIN `t_ao_sd_item_category` AS cat ON td.`sales_item_category` = cat.`sales_item_category`
            LEFT JOIN `t_movement_type` as mt0 ON mt0.`movement_type` = td.`movement_type` AND td.`pod_related` = 0
            LEFT JOIN `t_movement_type` as mt2 ON mt2.`movement_type` = td.`movement_type`
            LEFT JOIN `t_movement_type` as mt1 ON mt1.`movement_type` = td.`movement_type_it` AND td.`pod_related` = 1
            LEFT JOIN `t_documents_business_partner` as tdbp ON tdbp.`doc_sn` = td.`movement_type_it` AND tdbp.`business_partner_type` = 'SP' and tdbp.`document_category`='SDLV'
            WHERE tdia.`picking_document` = '{picking_document}'
        """
    # 2026/04/01修改 注释 group by tdia.`id`
    # GROUP BY tdia.`id`  -- 明确指定表别名
    db = DbHelper()
    # print("==============拣配单号查询==============")
    # print(sql)
    # print("=======================================")
    data = db.query_sql(sql)
    # for each in data:
    #     each["transaction_qty"] = each["picked_qty"]
    if data:
        return data
    else:
        return []
