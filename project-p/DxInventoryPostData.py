"""
@File    : DxInventoryPostData.py
@Author  : dongliang.wang@dxdstech.com
@Date    : 2025/8/8 10:31
@explain : 物料凭证过账BAPI
"""

import time
from decimal import ROUND_HALF_UP, Decimal, getcontext

import orjson as json
from DbHelper import DbHelper
from DxBusinessDataConvertUtil import get_exchange_rate
from DxCompanyPeriodUtil import check_material_period
from production_order_status import production_order_status_update
from SystemHelper import EnvKeys, LockAction, SystemHelper
from ToolsMethods import (
    ResetResponse,
    ResponseData,
    ResponseStatusCode,
    audit_summary_splicing,  # type:ignore
    calc_time,
)
from ZZEXT_DxInventoryPostData import after_save, before_check, before_save

"""
主方法：post_data  库存过账
"""

@ResetResponse(
    params=["test_run", "userid", "head", "detail"])
def test(test_run, userid, head, detail):
    print("test_run>", test_run)
    print("userid>", userid)
    print("head>>", head)
    print("detail>>", detail)
    post_data(test_run, userid, head, detail)


def post_data(test_run, user_id, head, item):
    """
    库存过账
    :param test_run: 0-正式运行 / 1-测试运行
    :param head: 凭证抬头字典
            document_category:单据种类
            post_code:过账代码   1-采购收货  2-生产收货   3-发料    4-调拨   5-其他收货   6-交货   7-外协收货
            exchange_rate:交易汇率
            document_date:凭证日期
            posting_date:过账日期
            summary_unique_number:汇总号
            company_code:公司代码
            vendor_dn:供应商交货单
            remarks_1:备注信息1
            remarks_2:备注信息2
            reserved1: 预留字段1
            reserved2: 预留字段2
            reserved3: 预留字段3
            reserved4: 预留字段4
            reserved5: 预留字段5
            reserved6: 预留字段6
            reserved7: 预留字段7
            reserved8: 预留字段8
            reserved9: 预留字段9
            reserved10: 预留字段10
            ztype: 业务类型
    :param item: 凭证行项目列表
            quality_insp_order_mark:质检过账标识
            up_prod_mater_mark:是否更新主材
            line_id:物料凭证行唯一标识
            parent_id:凭证行关联唯一标识
            movement_type:移动类型
            movement_reason:移动原因
            plant_code:工厂代码
            stor_loc_code:库存地点编码
            special_inventory_status1:特殊库存状态1
            special_inventory_status2:特殊库存状态2
            inventory_status:库存状态
            mat_code:物料编码
            batch_sn:批次号
            transaction_qty:交易数量
            transaction_uom:交易单位
            cost_qty:成本数量
            cost_uom:成本单位
            basic_qty:基本数量
            basic_uom:基本单位
            parallel_qty:平行数量
            parallel_uom:平行单位
            transaction_amount:交易金额
            transaction_currency:交易货币
            rel_po_sn:关联采购订单
            rel_po_items:关联采购订单行
            rel_po_component_number:关联采购订单行项目序号
            rel_po_comp_batch_num:关联采购订单行序号
            batch_closure_flag:结批标识
            batch_closure_date:结批日期
            prodo_component_number:生产订单组件序号
            rel_dn_sn:关联交货单
            rel_dn_item:关联交货单行
            picking_document:拣配单号
            batch_item:拣配单行号
            rel_procure_dn_sn:关联采购交货单
            rel_procure_dn_item:关联采购交货单行
            pod_related:POD标记
            ro_sn:关联预留
            ro_items:关联预留行
            rel_so_sn:关联销售订单
            rel_so_items:关联销售订单行
            customer_code:客户编码
            so_sn:销售订单编号
            so_items:销售订单行号
            project_sn:项目编号
            vendor_code:供应商编码
            po_sn:采购订单编号
            po_items:采购订单行号
            prodosn:生产订单号
            inv_transfer_order_no:库存调拨单
            wbs_elements:WBS元素
            cost_center:成本中心
            cost_business_object:成本事项
            cost_business_object1:成本事项1
            profit_center:利润中心
            accounting_subjects:会计科目
            asset_code1:资产卡片
            asset_code2:子资产
            equipment_code:设备ID
            express_delivery:快递单号
            reference1_item:行参考信息1
            reference2_item:行参考信息2
            reference3_item:行参考信息3
            rel_document_year:参考凭证年度
            rel_document_no:参考凭证号
            ref_document_mat:参考凭证行号
            pre_document_year:前序物料凭证年度
            pre_document_no:前序物料凭证
            pre_document_item:前序物料凭证行
            summary_line:汇总行
            receipt_completed_flag:收货完成标记
            rcv_plant_code:接收工厂代码
            rcv_stor_loc_code:接收库存地点
            rcv_special_inventory_status1:接收特殊库存状态1
            rcv_special_inventory_status2:接收特殊库存状态2
            rcv_inventory_status:接收库存状态
            rcv_mat_code:接收物料编码
            rcv_batch_sn:接收批次号
            rcv_customer_code:接收客户编码
            rcv_so_sn:接收销售订单编号
            rcv_so_items:接收销售订单行号
            rcv_project_sn:接收项目编号
            rcv_vendor_code:接收供应商编码
            rcv_po_sn:接收采购订单编号
            rcv_po_items:接收采购订单行号
            reserved1: 预留字段1
            reserved2: 预留字段2
            reserved3: 预留字段3
            reserved4: 预留字段4
            reserved5: 预留字段5
            reserved6: 预留字段6
            reserved7: 预留字段7
            reserved8: 预留字段8
            reserved9: 预留字段9
            reserved10: 预留字段10
            rcv_reserved1: 预留字段1
            rcv_reserved2: 预留字段2
            rcv_reserved3: 预留字段3
            rcv_reserved4: 预留字段4
            rcv_reserved5: 预留字段5
            rcv_reserved6: 预留字段6
            rcv_reserved7: 预留字段7
            rcv_reserved8: 预留字段8
            rcv_reserved9: 预留字段9
            rcv_reserved10: 预留字段10
            batch_number:{}  批次信息
                production_date:生产日期
                maturity_date:到期日期
                vendor_code:供应商
                vendor_batch:供应商批次
                receive_date:收货日期
                lot_no:Lot No
                wafer_id:Wafer ID
                mfg_date_wafer:MFG Date_WAFER
                vendor_lot_no:Vendor LotNo
                mfg_date_assy:MFG Date_ASSY
                packing_seal_date:Packing Seal Date
                date_code:Date Code
                packing_id:Packing ID
                bin_grade:Bin Grade
                grade:Grade
                batch_type:LotType
                receive_data:receive data
                cp_vendor:cp供应商
                bin:BIN
                grade1:等级1
                grade2:等级2
                grade3:等级3
                extended_batch_date1:附加日期1
                extended_batch_date2:附加日期2
                extended_batch_date3:附加日期3
                extended_batch_attributes1:附加属性1
                extended_batch_attributes2:附加属性2
                extended_batch_attributes3:附加属性3
                item:[] 动态批次属性
                        field_code
                        field_name
                        field_type
                        field_mark
                        field_value
                        field_value_from
                        field_value_to
                        field_format
                        required
                        field_length
                        decimal_length

            rcv_batch_number:{}  接收批次信息
                production_date:生产日期
                maturity_date:到期日期
                vendor_code:供应商
                vendor_batch:供应商批次
                receive_date:收货日期
                lot_no:Lot No
                wafer_id:Wafer ID
                mfg_date_wafer:MFG Date_WAFER
                vendor_lot_no:Vendor LotNo
                mfg_date_assy:MFG Date_ASSY
                packing_seal_date:Packing Seal Date
                date_code:Date Code
                packing_id:Packing ID
                bin_grade:Bin Grade
                grade:Grade
                batch_type:LotType
                receive_data:receive data
                cp_vendor:cp供应商
                bin:BIN
                grade1:等级1
                grade2:等级2
                grade3:等级3
                extended_batch_date1:附加日期1
                extended_batch_date2:附加日期2
                extended_batch_date3:附加日期3
                extended_batch_attributes1:附加属性1
                extended_batch_attributes2:附加属性2
                extended_batch_attributes3:附加属性3
                item:[] 动态批次属性
                        field_code
                        field_name
                        field_type
                        field_mark
                        field_value
                        field_value_from
                        field_value_to
                        field_format
                        required
                        field_length
                        decimal_length
    :return code: 状态码
    :return msg: 消息
    :return error_list: 错误明细
    :return mat_doc_sn: 物料凭证号
    :return year: 年度
    """

    python_begin = time.time()
    db = DbHelper()

    code = 200
    msg = ""
    error_list = []

    md_header = {}
    md_item = []
    md_price = []

    mat_doc_sn = ""
    year = ""

    if head["post_code"] not in ("1", "2", "3", "4", "5", "6", "7"):
        code = 500
        error_list.append("请输入正确的过账代码")

    if head["document_date"] == "":
        code = 500
        error_list.append("请输入凭证日期")

    if head["posting_date"] == "":
        code = 500
        error_list.append("请输入过账日期")

    plant_group = []
    # 查找公司代码
    for each in item:
        plant_group.append(each["plant_code"])
        mat_code = each.get("mat_code")
        print("plant_code---mat_code----",each["plant_code"],each.get("mat_code"),each.get("batch_sn"))
        query_sql = """
            SELECT `shelf_life_enabled`, `shelf_life_days`
            FROM `t_mmd_material_basic_data`
            WHERE `mat_code` = '{}'
        """.format(mat_code)
        material_data = db.query_sql(query_sql)
        if material_data:
            material = material_data[0]
            shelf_life_enabled = material["shelf_life_enabled"]
            if shelf_life_enabled == 1:
                has_empty_date = not each.get("batch_number", {}).get("production_date")
                if has_empty_date:

                    code = 500
                    error_list.append(f"物料{mat_code}行数据请输入制造日期")
    company_code = get_plant_of_company(plant_group, db)
    if company_code == "":
        code = 500
        error_list.append("公司代码不一致,请分开收货")
    elif company_code == "X":
        code = 500
        error_list.append("找不到该工厂所属公司")
    else:
        if head["posting_date"]:
            # 检查账期
            code, msg = check_material_period(company_code, head["posting_date"])
            if code != 200:
                code = 500
                error_list.append(msg)

    if error_list:
        code = 500
        msg = "存在错误,请检查"
        return code, msg, error_list, mat_doc_sn, year

    print("入参数打印")
    print(json.dumps(item))

    batch_begin = time.time()
    # 补充批次属性
    item = fill_batch_attribute(item, db)
    print("批次填充耗时： ", time.time() - batch_begin)
    r = update_batch_number(item, material_data)
    print("00000update_batch_number", r)

    # 保存时获取利润中心逻辑
    # print("user_id>", user_id)
    print("head>>", head)
    print("item>>", item)
    item, msg = get_profit_center(item, db, company_code)
    if msg:
        code = 500
        return code, msg, error_list, mat_doc_sn, year
    # print("item>>", item)

    if head["post_code"] == "1":
        begin = time.time()
        code, msg, error_list, md_header, md_item, md_price = check_data_postcode1(user_id, head, item, db)
        # 2026.4.22日增加更新批次状态码
        mat_code_to_batch_status = get_batch_status_mark(md_item, db)
        md_item = updata_batch_status_mark(md_item, mat_code_to_batch_status)
        print(f'正式过账前的md_item--------------------{md_item}')
        print("check_data_postcode1耗时： ", time.time() - begin)
        if code == 200:
            # 增强 --保存前
            code, msg, error_list, md_header, md_item, md_price = before_save(user_id, head, item, md_header, md_item,
                                                                              md_price)
            if test_run == "0":
                # 正式过账
                code, msg, error_list, mat_doc_sn, year = post_data_postcode1(user_id, md_header, md_item, md_price, db)
                if code == 200:
                    # 增强 -- 保存后
                    code, msg, error_list, md_header, md_item, md_price = after_save(user_id, head, item, md_header,
                                                                                     md_item, md_price)

    if head["post_code"] == "2":
        begin = time.time()
        code, msg, error_list, md_header, md_item, md_price = check_data_postcode2(user_id, head, item, db)
        print("check_data_postcode2耗时： ", time.time() - begin)
        if code == 200:
            # 增强 --保存前
            code, msg, error_list, md_header, md_item, md_price = before_save(user_id, head, item, md_header, md_item,
                                                                              md_price)
            if test_run == "0":
                # 正式过账
                code, msg, error_list, mat_doc_sn, year = post_data_postcode2(user_id, md_header, md_item, md_price, db)
                if code == 200:
                    # 增强 -- 保存后
                    code, msg, error_list, md_header, md_item, md_price = after_save(user_id, head, item, md_header,
                                                                                     md_item, md_price)
                    seen_prodosn = set()
                    seen_dlv_prodosn = set()  # 单独记录已处理 DLV 的订单

                    for item in md_item:
                        prodosn = item.get("prodosn", "")

                        if prodosn and prodosn not in seen_prodosn:
                            seen_prodosn.add(prodosn)
                            print(prodosn)
                            status_update_ls = [(prodosn, 'GR', 1)]
                            result, msg = production_order_status_update(status_update_ls)
                            if not result:
                                return code, msg, error_list, mat_doc_sn, year

                        receipt_completed_flag = item.get("receipt_completed_flag", "")
                        if prodosn and receipt_completed_flag == 1 and prodosn not in seen_dlv_prodosn:
                            seen_dlv_prodosn.add(prodosn)
                            status_update_ls = [(prodosn, 'DLV', 1)]
                            result, msg = production_order_status_update(status_update_ls)
                            if not result:
                                return code, msg, error_list, mat_doc_sn, year

    if head["post_code"] == "3":
        print("进入check_data_postcode3耗时： ")

        begin = time.time()
        code, msg, error_list, md_header, md_item, md_price = check_data_postcode3(user_id, head, item, db)
        print("check_data_postcode3耗时： ", time.time() - begin)
        if code == 200:
            # 增强 --保存前
            code, msg, error_list, md_header, md_item, md_price = before_save(user_id, head, item, md_header, md_item,
                                                                              md_price)
            if test_run == "0":
                code, msg, error_list, mat_doc_sn, year = post_data_postcode3(user_id, md_header, md_item, md_price, db)
                if code == 200:
                    # 增强 -- 保存后
                    code, msg, error_list, md_header, md_item, md_price = after_save(user_id, head, item, md_header,
                                                                                     md_item, md_price)
                    seen = set()
                    for item in md_item:
                        prodosn = item.get("prodosn", "")
                        if prodosn and prodosn not in seen:
                            seen.add(prodosn)
                            print(prodosn)
                            if prodosn:
                                status_update_ls = [(prodosn, 'GI', 1)]
                                result, msg = production_order_status_update(status_update_ls)
                                if not result:
                                    return code, msg, error_list, mat_doc_sn, year

    if head["post_code"] == "4":
        begin = time.time()
        code, msg, error_list, md_header, md_item, md_price = check_data_postcode4(user_id, head, item, db)
        print("check_data_postcode4耗时： ", time.time() - begin)
        if code == 200:
            # 增强 --保存前
            code, msg, error_list, md_header, md_item, md_price = before_save(user_id, head, item, md_header, md_item,
                                                                              md_price)
            if test_run == "0":
                # 正式过账
                code, msg, error_list, mat_doc_sn, year = post_data_postcode4(user_id, md_header, md_item, md_price, db)
                if code == 200:
                    # 增强 -- 保存后
                    code, msg, error_list, md_header, md_item, md_price = after_save(user_id, head, item, md_header,
                                                                                     md_item, md_price)

    if head["post_code"] == "5":
        begin = time.time()
        code, msg, error_list, md_header, md_item, md_price = check_data_postcode5(user_id, head, item, db)
        print("check_data_postcode5耗时： ", time.time() - begin)
        if code == 200:
            # 增强 --保存前
            code, msg, error_list, md_header, md_item, md_price = before_save(user_id, head, item, md_header, md_item,
                                                                              md_price)
            if test_run == "0":
                # 正式过账
                code, msg, error_list, mat_doc_sn, year = post_data_postcode5(user_id, md_header, md_item, md_price, db)
                if code == 200:
                    # 增强 -- 保存后
                    code, msg, error_list, md_header, md_item, md_price = after_save(user_id, head, item, md_header,
                                                                                     md_item, md_price)

    if head["post_code"] == "6":
        begin = time.time()
        code, msg, error_list, md_header, md_item, md_price = check_data_postcode6(user_id, head, item, db)
        print("check_data_postcode6耗时： ", time.time() - begin)
        if code == 200:
            # 增强 --保存前
            code, msg, error_list, md_header, md_item, md_price = before_save(user_id, head, item, md_header, md_item,
                                                                              md_price)
            if test_run == "0":
                # 正式过账
                code, msg, error_list, mat_doc_sn, year = post_data_postcode6(user_id, md_header, md_item, md_price, db)
                if code == 200:
                    # 增强 -- 保存后
                    code, msg, error_list, md_header, md_item, md_price = after_save(user_id, head, item, md_header,
                                                                                     md_item, md_price)

    if head["post_code"] == "7":
        begin = time.time()
        code, msg, error_list, md_header, md_item, md_price = check_data_postcode7(user_id, head, item, db)
        print("check_data_postcode7耗时： ", time.time() - begin)
        if code == 200:
            # 增强 --保存前
            code, msg, error_list, md_header, md_item, md_price = before_save(user_id, head, item, md_header, md_item,
                                                                              md_price)
            if test_run == "0":
                # 正式过账
                code, msg, error_list, mat_doc_sn, year = post_data_postcode7(user_id, md_header, md_item, md_price, db)
                if code == 200:
                    # 增强 -- 保存后
                    code, msg, error_list, md_header, md_item, md_price = after_save(user_id, head, item, md_header,
                                                                                     md_item, md_price)
    print("过账总耗时", time.time() - python_begin)
    return code, msg, error_list, mat_doc_sn, year


def update_batch_number(item_list, material_data):
    dh = DbHelper()
    # 遍历处理每一条数据
    for item in item_list:
        batch_number = item["batch_number"]
        production_date = batch_number.get("production_date")
        maturity_date = batch_number.get("maturity_date")

        shelf_life_days = 0

        if maturity_date and production_date:
            # 日期相减，得到天数，更新 shelf_life_days
            calc_days_sql = """
                SELECT DATEDIFF('{}', '{}') AS `shelf_life_days`
            """.format(maturity_date, production_date)
            calc_data = dh.query_sql(calc_days_sql)
            shelf_life_days = calc_data[0]["shelf_life_days"]

        # 如果 maturity_date 为空，需要查询物料基础表
        if not maturity_date and production_date:
            if material_data:
                material = material_data[0]
                shelf_life_enabled = material["shelf_life_enabled"]
                shelf_life_days = material["shelf_life_days"]

                if shelf_life_enabled != 1:
                    maturity_date = "9999-12-31"
                else:
                    # 生产日期 + 保质期天数
                    calc_sql = """
                        SELECT DATE_ADD('{}', INTERVAL {} DAY) AS `maturity_date`
                    """.format(production_date, shelf_life_days)
                    calc_data = dh.query_sql(calc_sql)
                    maturity_date = calc_data[0]["maturity_date"]
            else:
                # 查不到数据默认给最大值
                maturity_date = "9999-12-31"
        else:
            continue
        batch_number['production_date'] = production_date
        batch_number['maturity_date'] = maturity_date
        batch_number['shelf_life_days'] = shelf_life_days




def fill_batch_attribute(item, db):
    # 判断行项目是否由批次号，如果由则判断结构batch_number是否存在值，如果不存在，则填充
    mat_code = []
    batch_sn = []

    for each in item:
        if each.get('batch_sn', '') != '':
            mat_code.append(each['mat_code'])
            batch_sn.append(each['batch_sn'])

        if each.get('rcv_batch_sn', '') != '':
            mat_code.append(each['rcv_mat_code'])
            batch_sn.append(each['rcv_batch_sn'])

    # 当不存在的批次场合，获取批次结构
    batch_object = initialization("t_batch_number", db)
    print(f'batch_object-----------------{batch_object}')
    # 获取批次属性
    dict_batch_number = get_batch_attribute_mult(mat_code, batch_sn, db)
    print(f'dict_batch_number--------------------{dict_batch_number}')
    for each in item:
        if each.get('batch_sn', '') != '':
            key = each['mat_code'] + each['batch_sn']
            if dict_batch_number.get(key):
                batch_number = dict_batch_number[key][0]
                each['batch_number'] = replace_batch_number(batch_number, each['batch_number'])
            else:
                batch_number = batch_object.copy()
                batch_number['mat_code'] = each['mat_code']
                batch_number['batch_sn'] = each['batch_sn']
                each['batch_number'] = replace_batch_number(batch_number, each['batch_number'])

        if each.get('rcv_batch_sn', '') != '':
            key = each['rcv_mat_code'] + each['rcv_batch_sn']
            if dict_batch_number.get(key):
                batch_number = dict_batch_number[key][0]
                each['rcv_batch_number'] = replace_batch_number(batch_number, each['rcv_batch_number'])
            else:
                batch_number = batch_object.copy()
                batch_number['mat_code'] = each['rcv_mat_code']
                batch_number['batch_sn'] = each['rcv_batch_sn']
                each['rcv_batch_number'] = replace_batch_number(batch_number, each['rcv_batch_number'])

    return item


def replace_batch_number(old_batch_number, new_batch_number):
    # 如果传入的批次属性存在值则替换旧的
    for key, value in new_batch_number.items():
        if value:
            old_batch_number[key] = value

    return old_batch_number


def get_batch_attribute_mult(mat_code, batch_sn, db):
    dict_batch_number = {}

    mat_code = list(set(mat_code))
    batch_sn = list(set(batch_sn))

    if mat_code and batch_sn:
        batch_begin = time.time()
        query_sql = """
            SELECT
                *
            FROM
                `t_batch_number`
            WHERE
                `mat_code` in ('{}')
            AND
                `batch_sn` in ('{}')
        """.format("','".join(mat_code), "','".join(batch_sn))
        batch_data = db.query_sql(query_sql)

        print("获取批次属性耗时： ", time.time() - batch_begin)

        join_option = ""
        for i in batch_sn:
            join_option += "bp.`batch_sn` = '{}' or ".format(i)

        join_option = join_option.rstrip(" or ")
        join_option = "(" + join_option + ")"

        batch_begin = time.time()
        # # 获取批次特性值
        # query_sql = """
        #         SELECT
        #             mmbd.mat_code,
        #             bp.batch_sn,
        #             pf.field_code,
        #             pf.field_name,
        #             pf.field_type,
        #             IF(pf.single_value = 0, '0', '1') AS field_mark,
        #             IF(pf.single_value = 1, CASE
        #                                         WHEN pf.field_type = 'varchar' THEN bp.field_value
        #                                         WHEN pf.field_type = 'int' THEN bp.field_value_int
        #                                         WHEN pf.field_type = 'date' THEN bp.field_value_date
        #                                         WHEN pf.field_type = 'time' THEN bp.field_value_time
        #                                         WHEN pf.field_type = 'decimal' THEN bp.field_value_decimal
        #                                         ELSE bp.field_value
        #                                     END, '') AS field_value,
        #             IF(pf.range_value = 1, CASE
        #                                         WHEN pf.field_type = 'varchar' THEN bp.field_value_from
        #                                         WHEN pf.field_type = 'int' THEN bp.field_value_int_from
        #                                         WHEN pf.field_type = 'date' THEN bp.field_value_date_from
        #                                         WHEN pf.field_type = 'time' THEN bp.field_value_time_from
        #                                         WHEN pf.field_type = 'decimal' THEN bp.field_value_decimal_from
        #                                         ELSE bp.field_value_from
        #                                     END, '') AS field_value_from,
        #
        #             IF(pf.range_value = 1, CASE
        #                                         WHEN pf.field_type = 'varchar' THEN bp.field_value_to
        #                                         WHEN pf.field_type = 'int' THEN bp.field_value_int_to
        #                                         WHEN pf.field_type = 'date' THEN bp.field_value_date_to
        #                                         WHEN pf.field_type = 'time' THEN bp.field_value_time_to
        #                                         WHEN pf.field_type = 'decimal' THEN bp.field_value_decimal_to
        #                                         ELSE bp.field_value_to
        #                                     END, '') AS field_value_to,
        #             pf.field_class,
        #             pf.required,
        #             pf.field_length,
        #             pf.field_decimal_places
        #         FROM
        #             t_ap_property_field AS pf
        #             JOIN t_ap_property_field_alloc AS pfa ON pfa.field_code = pf.field_code
        #             JOIN t_ap_property_group_alloc AS pga ON pga.property_group = pfa.property_group
        #             AND pga.alloc_level = 'batch'
        #             AND pga.alloc_object_type = 'bat-mat_type'
        #             JOIN t_mmd_material_basic_data AS mmbd ON mmbd.mat_type = pga.alloc_object
        #             LEFT JOIN t_batch_additional_property AS bp ON bp.mat_code = mmbd.mat_code
        #             AND {}
        #             AND bp.field_code = pf.field_code
        #         WHERE
        #             mmbd.mat_code in ('{}') UNION ALL
        #         SELECT
        #             mmbd.mat_code,
        #             bp.batch_sn,
        #             pf.field_code,
        #             pf.field_name,
        #             pf.field_type,
        #             IF(pf.single_value = 0, '0', '1') AS field_mark,
        #             IF(pf.single_value = 1, CASE
        #                                         WHEN pf.field_type = 'varchar' THEN bp.field_value
        #                                         WHEN pf.field_type = 'int' THEN bp.field_value_int
        #                                         WHEN pf.field_type = 'date' THEN bp.field_value_date
        #                                         WHEN pf.field_type = 'time' THEN bp.field_value_time
        #                                         WHEN pf.field_type = 'decimal' THEN bp.field_value_decimal
        #                                         ELSE bp.field_value
        #                                     END, '') AS field_value,
        #             IF(pf.range_value = 1, CASE
        #                                         WHEN pf.field_type = 'varchar' THEN bp.field_value_from
        #                                         WHEN pf.field_type = 'int' THEN bp.field_value_int_from
        #                                         WHEN pf.field_type = 'date' THEN bp.field_value_date_from
        #                                         WHEN pf.field_type = 'time' THEN bp.field_value_time_from
        #                                         WHEN pf.field_type = 'decimal' THEN bp.field_value_decimal_from
        #                                         ELSE bp.field_value_from
        #                                     END, '') AS field_value_from,
        #
        #             IF(pf.range_value = 1, CASE
        #                                         WHEN pf.field_type = 'varchar' THEN bp.field_value_to
        #                                         WHEN pf.field_type = 'int' THEN bp.field_value_int_to
        #                                         WHEN pf.field_type = 'date' THEN bp.field_value_date_to
        #                                         WHEN pf.field_type = 'time' THEN bp.field_value_time_to
        #                                         WHEN pf.field_type = 'decimal' THEN bp.field_value_decimal_to
        #                                         ELSE bp.field_value_to
        #                                     END, '') AS field_value_to,
        #             pf.field_class,
        #             pf.required,
        #             pf.field_length,
        #             pf.field_decimal_places
        #         FROM
        #             t_ap_property_field AS pf
        #             JOIN t_ap_property_field_alloc AS pfa ON pfa.field_code = pf.field_code
        #             JOIN t_ap_property_group_alloc AS pga ON pga.property_group = pfa.property_group
        #             AND pga.alloc_level = 'batch'
        #             AND pga.alloc_object_type = 'bat-mat_group'
        #             JOIN t_mmd_material_basic_data AS mmbd ON mmbd.mat_group = pga.alloc_object
        #             LEFT JOIN t_batch_additional_property AS bp ON bp.mat_code = mmbd.mat_code
        #             AND {}
        #             AND bp.field_code = pf.field_code
        #         WHERE
        #             mmbd.mat_code in ('{}')
        #
        # """.format(join_option, "','".join(mat_code), join_option, "','".join(mat_code))

        # 获取批次特性值
        query_sql = """
            SELECT
                mmbd.`mat_code`,
                bp.`batch_sn`,
                pf.`field_code`,
                MAX(pf.`field_name`),
                MAX(pf.`field_type`),
                MAX(IF(pf.`single_value` = 0, '0', '1')) AS `field_mark`,
                MAX(IF(pf.`single_value` = 1,
                    CASE pf.`field_type`
                        WHEN 'varchar' THEN CAST(bp.`field_value` AS CHAR)
                        WHEN 'int' THEN CAST(bp.`field_value_int` AS CHAR)
                        WHEN 'date' THEN CAST(bp.`field_value_date` AS CHAR)
                        WHEN 'time' THEN CAST(bp.`field_value_time` AS CHAR)
                        WHEN 'decimal' THEN CAST(bp.`field_value_decimal` AS CHAR)
                        ELSE CAST(bp.`field_value` AS CHAR)
                    END, '')) AS `field_value`,
                MAX(IF(pf.`range_value` = 1,
                    CASE pf.`field_type`
                        WHEN 'varchar' THEN CAST(bp.`field_value_from` AS CHAR)
                        WHEN 'int' THEN CAST(bp.`field_value_int_from` AS CHAR)
                        WHEN 'date' THEN CAST(bp.`field_value_date_from` AS CHAR)
                        WHEN 'time' THEN CAST(bp.`field_value_time_from` AS CHAR)
                        WHEN 'decimal' THEN CAST(bp.`field_value_decimal_from` AS CHAR)
                        ELSE CAST(bp.`field_value_from` AS CHAR)
                    END, '')) AS `field_value_from`,
                MAX(IF(pf.`range_value` = 1,
                    CASE pf.`field_type`
                        WHEN 'varchar' THEN CAST(bp.`field_value_to` AS CHAR)
                        WHEN 'int' THEN CAST(bp.`field_value_int_to` AS CHAR)
                        WHEN 'date' THEN CAST(bp.`field_value_date_to` AS CHAR)
                        WHEN 'time' THEN CAST(bp.`field_value_time_to` AS CHAR)
                        WHEN 'decimal' THEN CAST(bp.`field_value_decimal_to` AS CHAR)
                        ELSE CAST(bp.`field_value_to` AS CHAR)
                    END, '')) AS `field_value_to`,
                MAX(pf.`field_class`),
                MAX(pf.`required`),
                MAX(pf.`field_length`),
                MAX(pf.`field_decimal_places`)
            FROM `t_ap_property_field` AS pf
            JOIN `t_ap_property_field_alloc` AS pfa ON pfa.`field_code` = pf.`field_code`
            JOIN `t_ap_property_group_alloc` AS pga ON pga.`property_group` = pfa.`property_group`
                AND pga.`alloc_level` = 'batch'
                AND pga.`alloc_object_type` IN ('bat-mat_type', 'bat-mat_group')
            JOIN `t_mmd_material_basic_data` AS mmbd ON (
                (pga.`alloc_object_type` = 'bat-mat_type' AND mmbd.`mat_type` = pga.`alloc_object`)
                OR (pga.`alloc_object_type` = 'bat-mat_group' AND mmbd.`mat_group` = pga.`alloc_object`)
            )
            LEFT JOIN `t_batch_additional_property` AS bp ON bp.`mat_code` = mmbd.`mat_code`
                AND {}
                AND bp.`field_code` = pf.`field_code`
            WHERE mmbd.`mat_code` IN ('{}')
            GROUP BY mmbd.`mat_code`, bp.`batch_sn`, pf.`field_code`  -- 去重
            ORDER BY mmbd.`mat_code`, pf.`field_code`
        """.format(join_option, "','".join(mat_code))

        attribute_data = db.query_sql(query_sql)
        print("获取批次特性耗时： ", time.time() - batch_begin)

        dict_attribute_data = {}
        for each in attribute_data:
            key = each['mat_code'] + each['batch_sn']
            if key not in dict_attribute_data:
                dict_attribute_data[key] = []
                dict_attribute_data[key].append(each)
            else:
                dict_attribute_data[key].append(each)

        for each in batch_data:
            key = each['mat_code'] + each['batch_sn']
            each['item'] = []

            if dict_attribute_data.get(key):
                each['item'] = dict_attribute_data[key]

        for each in batch_data:
            key = each['mat_code'] + each['batch_sn']
            if key not in dict_batch_number:
                dict_batch_number[key] = []
                dict_batch_number[key].append(each)
            else:
                dict_batch_number[key].append(each)
    return dict_batch_number


# def get_batch_attribute(mat_code, batch_sn, db):
#     batch_number = {}
#     if mat_code and batch_sn:
#         query_sql = """
#             SELECT
#                 *
#             FROM
#                 `t_batch_number`
#             WHERE
#                 `mat_code` = '{}'
#             AND
#                 `batch_sn` = '{}'
#         """.format(mat_code, batch_sn)
#         data = db.query_sql(query_sql)
#         if data:
#             batch_number = data[0]
#
#         # 获取批次特性值
#         query_sql = """
#             SELECT
#                 z.field_code,
#                 z.field_name,
#                 z.field_type,
#                 z.field_mark,
#                 z.field_value,
#                 z.field_value_from,
#                 z.field_value_to,
#                 z.field_class,
#                 z.required,
#                 z.field_length,
#                 z.field_decimal_places
#             FROM
#                 (
#                 SELECT
#                     pf.field_code,
#                     pf.field_name,
#                     pf.field_type,
#                     IF(pf.single_value = 0, '0', '1') AS field_mark,
#                     IF(pf.single_value = 1, CASE
#                                                 WHEN pf.field_type = 'varchar' THEN bp.field_value
#                                                 WHEN pf.field_type = 'int' THEN bp.field_value_int
#                                                 WHEN pf.field_type = 'date' THEN bp.field_value_date
#                                                 WHEN pf.field_type = 'time' THEN bp.field_value_time
#                                                 WHEN pf.field_type = 'decimal' THEN bp.field_value_decimal
#                                                 ELSE bp.field_value
#                                             END, '') AS field_value,
#                     IF(pf.range_value = 1, CASE
#                                                 WHEN pf.field_type = 'varchar' THEN bp.field_value_from
#                                                 WHEN pf.field_type = 'int' THEN bp.field_value_int_from
#                                                 WHEN pf.field_type = 'date' THEN bp.field_value_date_from
#                                                 WHEN pf.field_type = 'time' THEN bp.field_value_time_from
#                                                 WHEN pf.field_type = 'decimal' THEN bp.field_value_decimal_from
#                                                 ELSE bp.field_value_from
#                                             END, '') AS field_value_from,
#
#                     IF(pf.range_value = 1, CASE
#                                                 WHEN pf.field_type = 'varchar' THEN bp.field_value_to
#                                                 WHEN pf.field_type = 'int' THEN bp.field_value_int_to
#                                                 WHEN pf.field_type = 'date' THEN bp.field_value_date_to
#                                                 WHEN pf.field_type = 'time' THEN bp.field_value_time_to
#                                                 WHEN pf.field_type = 'decimal' THEN bp.field_value_decimal_to
#                                                 ELSE bp.field_value_to
#                                             END, '') AS field_value_to,
#                     pf.field_class,
#                     pf.required,
#                     pf.field_length,
#                     pf.field_decimal_places
#                 FROM
#                     t_ap_property_field AS pf
#                     JOIN t_ap_property_field_alloc AS pfa ON pfa.field_code = pf.field_code
#                     JOIN t_ap_property_group_alloc AS pga ON pga.property_group = pfa.property_group
#                     AND pga.alloc_level = 'batch'
#                     AND pga.alloc_object_type = 'bat-mat_type'
#                     JOIN t_mmd_material_basic_data AS mmbd ON mmbd.mat_type = pga.alloc_object
#                     LEFT JOIN t_batch_additional_property AS bp ON bp.mat_code = mmbd.mat_code
#                     AND bp.batch_sn = '{}'
#                     AND bp.field_code = pf.field_code
#                 WHERE
#                     mmbd.mat_code = '{}' UNION ALL
#                 SELECT
#                     pf.field_code,
#                     pf.field_name,
#                     pf.field_type,
#                     IF(pf.single_value = 0, '0', '1') AS field_mark,
#                     IF(pf.single_value = 1, CASE
#                                                 WHEN pf.field_type = 'varchar' THEN bp.field_value
#                                                 WHEN pf.field_type = 'int' THEN bp.field_value_int
#                                                 WHEN pf.field_type = 'date' THEN bp.field_value_date
#                                                 WHEN pf.field_type = 'time' THEN bp.field_value_time
#                                                 WHEN pf.field_type = 'decimal' THEN bp.field_value_decimal
#                                                 ELSE bp.field_value
#                                             END, '') AS field_value,
#                     IF(pf.range_value = 1, CASE
#                                                 WHEN pf.field_type = 'varchar' THEN bp.field_value_from
#                                                 WHEN pf.field_type = 'int' THEN bp.field_value_int_from
#                                                 WHEN pf.field_type = 'date' THEN bp.field_value_date_from
#                                                 WHEN pf.field_type = 'time' THEN bp.field_value_time_from
#                                                 WHEN pf.field_type = 'decimal' THEN bp.field_value_decimal_from
#                                                 ELSE bp.field_value_from
#                                             END, '') AS field_value_from,
#
#                     IF(pf.range_value = 1, CASE
#                                                 WHEN pf.field_type = 'varchar' THEN bp.field_value_to
#                                                 WHEN pf.field_type = 'int' THEN bp.field_value_int_to
#                                                 WHEN pf.field_type = 'date' THEN bp.field_value_date_to
#                                                 WHEN pf.field_type = 'time' THEN bp.field_value_time_to
#                                                 WHEN pf.field_type = 'decimal' THEN bp.field_value_decimal_to
#                                                 ELSE bp.field_value_to
#                                             END, '') AS field_value_to,
#                     pf.field_class,
#                     pf.required,
#                     pf.field_length,
#                     pf.field_decimal_places
#                 FROM
#                     t_ap_property_field AS pf
#                     JOIN t_ap_property_field_alloc AS pfa ON pfa.field_code = pf.field_code
#                     JOIN t_ap_property_group_alloc AS pga ON pga.property_group = pfa.property_group
#                     AND pga.alloc_level = 'batch'
#                     AND pga.alloc_object_type = 'bat-mat_group'
#                     JOIN t_mmd_material_basic_data AS mmbd ON mmbd.mat_group = pga.alloc_object
#                     LEFT JOIN t_batch_additional_property AS bp ON bp.mat_code = mmbd.mat_code
#                     AND bp.batch_sn = '{}'
#                     AND bp.field_code = pf.field_code
#                 WHERE
#                     mmbd.mat_code = '{}'
#                 ) AS z
#         """.format(batch_sn, mat_code, batch_sn, mat_code)
#         data = db.query_sql(query_sql)
#         if data:
#             batch_number['item'] = data
#
#     return batch_number


# 正式过账代码2
def post_data_postcode2(user_id, md_header, md_item, md_price, db):
    code = 0
    msg = ""
    mat_doc_sn = ""
    year = ""
    error_list = []

    try:
        mat_code = md_item[0]["mat_code"]
        batch_sn = md_item[0]["batch_sn"]
        lock_key = f"LOCK_{mat_code}_{batch_sn}"
    except:
        lock_key = f"LOCK_USER_{user_id}"

    try:
        # 加锁
        code, msg = lock_data(md_item, LockAction.lock, lock_key)
        if code != 200:
            error_list.append(msg)
            raise Exception(msg)

        # 调用会计引擎
        input = json.dumps([{"header": md_header, "items": md_item, "details": md_price}])
        sh = SystemHelper()
        print(input)

        c_begin = time.time()
        output = json.loads(sh.execOperator("OnConsumeMat", input)["data"])
        print("调用C耗时： ", time.time() - c_begin)
        print(output)

        if output["result"] == 0:
            if "data" in output:
                code = 200
                msg = "执行成功"
                if output["data"][0]["status"] == "E":
                    code = 500
                    msg = output["data"][0]["msg"]
                else:
                    mat_doc_sn = output["data"][0]["mat_doc_sn"]
                    year = output["data"][0]["year"]
                    msg = "过账成功,物料凭证:{} 年度{}".format(mat_doc_sn, year)
            else:
                code = 500
                msg = output.get("msg", "会计引擎异常")
        else:
            code = 500
            msg = output["msg"]

    except Exception as e:
        if not error_list:
            error_list.append(str(e))
        code = 500
        msg = "存在错误,请检查"

    finally:
        lock_data(md_item, LockAction.unlock, lock_key)

    return code, msg, error_list, mat_doc_sn, year


# 检查过账代码2的参数
def check_data_postcode2(user_id, head, item, db):
    code = 200
    msg = ""
    error_list = []

    # 增强 -- 检验前
    code, msg, error_list, head, item = before_check(user_id, head, item)
    if code != 200:
        return code, msg, error_list, [], [], []

    dict_movement_type = {}
    movement_type = []
    plant_code = []
    plant_code_data = []
    dict_plant_storage = {}
    movement_special_inventory_status1 = []
    movement_special_inventory_status2 = []
    mat_code = []
    dict_mat_code = {}
    dict_mat_code_cost = {}
    po_sn = []
    dict_po_header = {}
    dict_po_item = {}
    prodosn = []
    dict_prodosn_data = {}
    dn_sn = []
    dict_dn_sn_header = {}
    dict_dn_sn_item = {}
    picking_document = []
    dict_picking_document = {}
    procure_dn_sn = []
    dict_procure_dn_sn_data = {}
    ro_sn = []
    dict_ro_sn_data = {}
    so_sn = []
    dict_so_sn_data = {}
    customer_code = []
    dict_customer_code_data = {}
    vendor_code = []
    dict_vendor_code_data = {}
    cost_center = []
    dict_cost_center_data = {}
    cost_business_object = []
    dict_cost_business_object_data = {}
    profit_center = []
    dict_profit_center_data = {}
    equipment_code = []
    dict_equipment_code_data = {}
    dict_company = {}
    dict_relation = {}
    dict_relation2 = {}
    dict_movement_label1 = {}
    dict_movement_label2 = {}
    dict_movement_label3 = {}
    dict_mat_batch = {}
    batch = []
    dict_mat_insp = {}
    dict_price_data = {}
    dict_inventory_status = {}
    inv_transfer_order_no = []
    dict_inv_transfer_order = {}
    dict_inv_transfer_order_item = {}

    # 性能优化
    for each in item:
        # 移动类型
        if each.get("movement_type", "") != "":
            movement_type.append(each['movement_type'])
        # 工厂
        if each.get("plant_code", "") != "":
            plant_code.append(each['plant_code'])

        # 物料编码
        if each.get("mat_code", "") != "":
            mat_code.append(each['mat_code'])

        # 采购订单
        if each.get("rel_po_sn", '') != '':
            po_sn.append(each['rel_po_sn'])
        if each.get('po_sn', '') != '':
            po_sn.append(each['po_sn'])

        # 生产订单
        if each.get('prodosn', '') != '':
            prodosn.append(each['prodosn'])

        # 交货单
        if each.get('rel_dn_sn', '') != '':
            dn_sn.append(each['rel_dn_sn'])

        # 拣配单
        if each.get('picking_document', '') != '':
            picking_document.append(each['picking_document'])

        # 采购交货单
        if each.get('rel_procure_dn_sn', '') != '':
            procure_dn_sn.append(each['rel_procure_dn_sn'])

        # 预留
        if each.get('ro_sn', '') != '':
            ro_sn.append(each['ro_sn'])

        # 销售订单
        if each.get('rel_so_sn', '') != '':
            so_sn.append(each['rel_so_sn'])
        if each.get('so_sn', '') != '':
            so_sn.append(each['so_sn'])

        # 客户
        if each.get('customer_code', '') != '':
            customer_code.append(each['customer_code'])

        # 供应商
        if each.get('vendor_code', '') != '':
            vendor_code.append(each['vendor_code'])

        # 成本中心
        if each.get('cost_center', '') != '':
            cost_center.append(each['cost_center'])

        # 成本事项
        if each.get('cost_business_object', '') != '':
            cost_business_object.append(each['cost_business_object'])
        if each.get('cost_business_object1', '') != '':
            cost_business_object.append(each['cost_business_object1'])

        # 利润中心
        if each.get('profit_center', '') != '':
            profit_center.append(each['profit_center'])

        # 设备
        if each.get('equipment_code', '') != '':
            equipment_code.append(each['equipment_code'])

        # 批次
        if each.get('batch_sn', '') != '':
            batch.append(each['batch_sn'])

        # 库存调拨单
        if each.get("inv_transfer_order_no", "") != '':
            inv_transfer_order_no.append(each['inv_transfer_order_no'])

    data_begin = time.time()

    # 获取移动类型属性
    dict_movement_type = get_movement_type_info(movement_type, db)
    # 获取工厂
    plant_code_data = get_plant_code_data(plant_code, db)
    # 获取工厂对应库存地点
    dict_plant_storage = get_plant_storage(plant_code, db)
    # 获取移动类型对应特殊库存状态
    movement_special_inventory_status1, movement_special_inventory_status2, dict_relation, dict_relation2 = get_movement_special_inventory_status(
        movement_type, db)
    # 获取物料主数据信息
    dict_mat_code = get_mat_code_info(mat_code, plant_code, db)
    # 获取物料成本视图
    dict_mat_code_cost = get_mat_code_cost_info(mat_code, plant_code, db)
    # 获取物料单位换算关系
    dict_mat_uom_convert = get_mat_uom_convert(mat_code, db)
    # 获取采购订单抬头信息
    dict_po_header = get_po_header(po_sn, db)
    # 获取采购订单行项目信息
    dict_po_item = get_po_item(po_sn, db)
    # 获取生产订单
    dict_prodosn_data = get_prodosn_data(prodosn, db)
    # 获取交货单抬头信息
    dict_dn_sn_header = get_dn_header(dn_sn, db)
    # 获取交货单行项目信息
    dict_dn_sn_item = get_dn_sn_item(dn_sn, db)
    # 获取拣配单信息
    dict_picking_document = get_picking_document_info(picking_document, db)
    # 获取采购交货单信息
    dict_procure_dn_sn_data = get_procure_dn_sn_info(procure_dn_sn, db)
    # 获取预留单信息
    dict_ro_sn_data = get_ro_sn_info(ro_sn, db)
    # 获取销售订单信息
    dict_so_sn_data = get_so_sn_info(so_sn, db)
    # 获取客户信息
    dict_customer_code_data = get_customer_code_info(customer_code, db)
    # 获取供应商信息
    dict_vendor_code_data = get_vendor_code_info(vendor_code, db)
    # 获取成本中心
    dict_cost_center_data = get_cost_center_info(cost_center, db)
    # 获取成本事项
    dict_cost_business_object_data = get_cost_business_object_info(cost_business_object, db)
    # 利润中心
    dict_profit_center_data = get_profit_center_info(profit_center, db)
    # 获取设备主数据信息
    dict_equipment_code_data = get_equipment_code_info(equipment_code, db)
    # 按工厂获取公司信息
    dict_company = get_company_info_by_plant(plant_code, db)
    # 获取移动类型配置信息
    dict_movement_label1, dict_movement_label2, dict_movement_label3 = get_movement_label_info(movement_type, db)
    # 获取物料批次信息
    dict_mat_batch = get_mat_code_and_batch(mat_code, batch, db)
    # 获取物料质检信息
    dict_mat_insp = get_mat_insp_info(mat_code, plant_code, db)
    # 获取采购订单价格明细
    dict_price_data = get_po_price_data(po_sn, db)
    # 获取库存状态
    dict_inventory_status = get_all_inventory_status(db)
    # 获取库存调拨单
    dict_inv_transfer_order = get_inv_transfer_order(inv_transfer_order_no, db)
    # 获取库存调拨单行
    dict_inv_transfer_order_item = get_inv_transfer_order_item(inv_transfer_order_no, db)

    print("取值耗时: ", time.time() - data_begin)

    for each in item:
        # 必输校验
        # 行唯一标识校验
        if each.get("line_id", "") == "":
            error_list.append("行唯一标识必输")
            continue
        # 移动类型校验
        if each.get("movement_type", "") == "":
            error_list.append("行标识{}移动类型必输".format(each["line_id"]))
        # 交易数量
        if Decimal(each.get("transaction_qty", 0)) <= 0:
            error_list.append("行标识{}交易数量必须大于0".format(each["line_id"]))
        # 交易单位
        if each.get("transaction_uom", "") == "":
            error_list.append("行标识{}交易单位必输".format(each["line_id"]))
        # # 基本数量
        # if each.get("basic_qty", 0) == 0:
        #     error_list.append("行标识{}基本数量必输".format(each["line_id"]))
        # # 基本单位
        # if each.get("basic_uom", "") == "":
        #     error_list.append("行标识{}基本单位必输".format(each["line_id"]))
        # # 平行单位
        # if each.get("parallel_uom", "") == "":
        #     error_list.append("行标识{}平行单位必输".format(each["line_id"]))
        # # 平行数量
        # if each.get("parallel_uom", "") == each.get("basic_uom", ""):
        #     each["parallel_qty"] = each["basic_qty"]
        # else:
        #     if each.get("basic_qty", 0) == 0:
        #         each["parallel_qty"] = 0
        #     else:
        #         if each.get("parallel_qty", 0) == 0:
        #             error_list.append("行标识{}平行数量必输".format(each["line_id"]))
        # if each.get("parallel_uom", "") != "":
        #     if each.get("parallel_qty", 0) == 0:
        #         error_list.append("行标识{}平行数量必输".format(each["line_id"]))
        # 生产订单
        if each.get("prodosn", "") == "":
            error_list.append("行标识{}生产订单必输".format(each["line_id"]))
        # 工厂代码
        if each.get("plant_code", "") == "":
            error_list.append("行标识{}工厂代码必输".format(each["line_id"]))
        # 库存状态
        if each.get("inventory_status", "") == "" and each.get("mat_code", "") != "":
            error_list.append("行标识{}库存状态必输".format(each["line_id"]))
        # 库存地点
        if each.get("mat_code", "") != "" and each["special_inventory_status1"] != 'V':
            if each["stor_loc_code"] == "":
                error_list.append("行标识{}库存地点必输".format(each["line_id"]))
        # 存在性校验
        if not error_list:
            # 移动类型校验
            if dict_movement_type.get(each["movement_type"]) is None:
                error_list.append("行标识{}移动类型{}不存在".format(each["line_id"], each["movement_type"]))
            else:
                if dict_movement_type[each['movement_type']][0]['post_code'] != head["post_code"]:
                    error_list.append("行标识{}移动类型{}不适用过账码{}".format(each["line_id"], each["movement_type"],
                                                                                head["post_code"]))
            # 工厂代码校验
            if each["plant_code"] not in plant_code_data:
                error_list.append("行标识{}工厂代码{}不存在".format(each["line_id"], each["plant_code"]))
            # 库存地点校验
            if each.get("stor_loc_code", "") != "":
                # if not check_if_stor_loc_code_exists(each["stor_loc_code"]):
                #     error_list.append("行标识{}库存地点{}不存在".format(each["line_id"], each["stor_loc_code"]))
                # else:
                if dict_plant_storage.get(each["plant_code"] + each["stor_loc_code"]) is None:
                    error_list.append(
                        "行标识{}在工厂{}下库存地点{}未分配".format(each["line_id"], each["plant_code"],
                                                                    each["stor_loc_code"]))
            # 特殊库存状态1校验
            if each.get("special_inventory_status1", "") != "":
                if each["movement_type"] + each["special_inventory_status1"] not in movement_special_inventory_status1:
                    error_list.append(
                        "行标识{}在移动类型{}下特殊库存标识1{}未分配".format(each["line_id"], each["movement_type"],
                                                                             each["special_inventory_status1"]))
            # 库存状态
            if each.get("inventory_status", "") != "":
                if dict_inventory_status.get(each["inventory_status"]) is None:
                    error_list.append("行标识{}库存状态{}不存在".format(each["line_id"], each["inventory_status"]))
            # 物料状态检查
            if each.get("mat_code", "") != "":
                key = each["mat_code"] + each["plant_code"]
                if dict_mat_code.get(key) is None:
                    error_list.append("行标识{}物料编码{}在工厂{}不存在".format(each["line_id"], each["mat_code"], each["plant_code"]))
                else:
                    mat_info = dict_mat_code[key][0]
                    if mat_info.get('deleted_mark', 0) == 1 or mat_info.get('lock_flag', 0) == 1:
                        error_list.append("行标识{}物料编码{}已删除或锁定".format(each["line_id"], each["mat_code"]))
                    elif mat_info.get('value_update', 0) == 1:
                        if dict_mat_code_cost.get(key) is None:
                            error_list.append("行标识{}物料编码{}成本视图未扩".format(each["line_id"], each["mat_code"]))
            # 采购订单状态检查
            if each.get("rel_po_sn", "") != "":
                msg = check_po_status(each["rel_po_sn"], dict_po_header)
                if msg != "":
                    error_list.append("行标识{}{}".format(each["line_id"], msg))
                else:
                    # 采购订单行检查
                    msg = check_po_item_status(head["post_code"], each["rel_po_sn"], each["rel_po_items"], dict_po_item)
                if msg != "":
                    error_list.append("行标识{}{}".format(each["line_id"], msg))
                # if each.get("rel_po_component_number", 0) != 0:
                #     # 采购订单行的序号检查
                #     if check_if_po_component_exists(each["rel_po_sn"], each["rel_po_items"],
                #                                     each["rel_po_component_number"]):
                #         error_list.append(
                #             "行标识{}关联采购订单{}行{}项目序号{}不存在".format(each["line_id"], each["rel_po_sn"],
                #                                                                 each["rel_po_items"],
                #                                                                 each["rel_po_component_number"]))
                # if each.get("rel_po_comp_batch_num", 0) != 0:
                #     # 采购订单库存绑定表检查
                #     if check_if_po_batch_binding_exists(each["rel_po_sn"], each["rel_po_items"],
                #                                         each["rel_po_component_number"],
                #                                         each["rel_po_comp_batch_num"]):
                #         error_list.append("行标识{}关联采购订单{}行{}项目序号{}绑定序号{}不存在".format(each["line_id"],
                #                                                                                         each[
                #                                                                                             "rel_po_sn"],
                #                                                                                         each[
                #                                                                                             "rel_po_items"],
                #                                                                                         each[
                #                                                                                             "rel_po_component_number"],
                #                                                                                         each[
                #                                                                                             "rel_po_comp_batch_num"]))
            if each.get("prodosn", "") != "":
                # 生产订单检查
                if dict_prodosn_data.get(each["prodosn"]) is None:
                    error_list.append("行标识{}生产订单{}不存在或已删除".format(each["line_id"], each["prodosn"]))
            if each.get("rel_dn_sn", "") != "":
                # 关联交货单检查
                if dict_dn_sn_header.get(each["rel_dn_sn"]) is None:
                    error_list.append("行标识{}关联交货单{}不存在".format(each["line_id"], each["rel_dn_sn"]))
                elif dict_dn_sn_item.get(each["rel_dn_sn"] + str(each.get("rel_dn_item", 0))) is None:
                    error_list.append("行标识{}关联交货单{}行号{}不存在".format(each["line_id"], each["rel_dn_sn"],
                                                                                each.get("rel_dn_item", 0)))
            if each.get("picking_document", "") != "":
                # 拣配单号检查
                if dict_picking_document.get(each["picking_document"] + str(each.get("batch_item", 0))) is None:
                    error_list.append("行标识{}拣配单号{}不存在".format(each["line_id"], each["picking_document"]))

            if each.get("rel_procure_dn_sn", "") != "":

                if dict_procure_dn_sn_data.get(
                        each["rel_procure_dn_sn"] + str(each.get("rel_procure_dn_item", 0))) is None:
                    error_list.append(
                        "行标识{}关联交货单{}行号{}不存在".format(each["line_id"], each["rel_procure_dn_sn"],
                                                                  each.get("rel_procure_dn_item", 0)))
            if each.get("ro_sn", "") != "":

                if dict_ro_sn_data.get(each["ro_sn"] + str(each.get("ro_items", 0))) is None:
                    error_list.append("行标识{}关联预留单{}行号{}不存在".format(each["line_id"], each["ro_sn"],
                                                                                each.get("ro_items", 0)))
            if each.get("rel_so_sn", "") != "":

                if dict_so_sn_data.get(each["rel_so_sn"] + str(each.get("rel_so_items", 0))) is None:
                    error_list.append("行标识{}关联销售订单{}行号{}不存在".format(each["line_id"], each["rel_so_sn"],
                                                                                  each.get("rel_so_items", "")))

            if each.get("inv_transfer_order_no", "") != "":
                # 库存调拨单
                if dict_inv_transfer_order.get(each["inv_transfer_order_no"]) is None:
                    error_list.append(
                        "行标识{}库存调拨单{}不存在".format(each["line_id"], each["inv_transfer_order_no"]))
                elif dict_inv_transfer_order_item.get(
                        each["inv_transfer_order_no"] + str(each.get("inv_transfer_order_items", 0))) is None:
                    error_list.append(
                        "行标识{}库存调拨单{}行号{}不存在".format(each["line_id"], each["inv_transfer_order_no"],
                                                                  each.get("inv_transfer_order_items", 0)))

            if each.get("special_inventory_status1", "") == "C" or each.get("special_inventory_status1", "") == "CC":
                # 客户检查
                if each.get("customer_code", "") == "":
                    error_list.append("行标识{}客户编码必输".format(each["line_id"]))
                else:
                    if dict_customer_code_data.get(each["customer_code"]) is None:
                        error_list.append("行标识{}客户编码{}不存在".format(each["line_id"], each["customer_code"]))
            else:
                each["customer_code"] = ""

            if each.get("special_inventory_status1", "") == "S":
                # 销售订单检查
                if each.get("so_sn", "") == "" or each.get("so_items", "") == "":
                    error_list.append("行标识{}销售订单信息必输".format(each["line_id"]))
                else:
                    if dict_so_sn_data.get(each.get("so_sn", "") + str(each.get("so_items", 0))) is None:
                        error_list.append("行标识{}销售订单{}行号{}不存在".format(each["line_id"], each["rel_so_sn"],
                                                                                  each.get("rel_so_items", "")))
            else:
                each["so_sn"] = ""
                each["so_items"] = 0

            if each.get("special_inventory_status1", "") == "P":
                # 项目编码检查
                if each.get("project_sn", "") == "":
                    error_list.append("行标识{}项目编码必输".format(each["line_id"]))
                    # 项目编码检查待定-----
            else:
                each["project_sn"] = ""

            if each.get("special_inventory_status1", "") == "V" or each.get("special_inventory_status1", "") == "SC":
                # 供应商编码检查
                if each.get("vendor_code", "") == "":
                    error_list.append("行标识{}供应商编码必输".format(each["line_id"]))
                else:
                    if dict_vendor_code_data.get(each["vendor_code"]) is None:
                        error_list.append("行标识{}供应商编码{}不存在".format(each["line_id"], each["vendor_code"]))

                if each["special_inventory_status1"] == "V":
                    if each.get("po_sn", "") != "":
                        # 采购订单检查
                        # if check_if_po_header_exists(each["po_sn"]):
                        #     error_list.append("行标识{}采购订单{}不存在".format(each["line_id"], each["po_sn"]))
                        # else:
                        if dict_po_item.get(each["po_sn"] + str(each.get("po_items", 0))) is None:
                            error_list.append(
                                "行标识{}采购订单{}行号{}不存在".format(each["line_id"], each["rel_so_sn"],
                                                                        each.get("rel_so_items", "")))
                else:
                    each["po_sn"] = ""
                    each["po_items"] = 0
            else:
                each["vendor_code"] = ""
                each["po_sn"] = ""
                each["po_items"] = 0

            if each.get("cost_center", "") != "":
                # 成本中心检查
                if dict_cost_center_data.get(each["cost_center"] + each["plant_code"]) is None:
                    error_list.append(
                        "行标识{}成本中心{}在工厂{}对应的公司代码不存在".format(each["line_id"], each["cost_center"],
                                                                                each["plant_code"]))
            if each.get("cost_business_object", "") != "":
                # 成本事项检查
                if dict_cost_business_object_data.get(each["cost_business_object"] + each["plant_code"]) is None:
                    error_list.append(
                        "行标识{}成本事项{}在工厂{}对应的公司代码不存在".format(each["line_id"],
                                                                                each["cost_business_object"],
                                                                                each["plant_code"]))
            if each.get("cost_business_object1", "") != "":
                # 成本事项2检查
                if dict_cost_business_object_data.get(each["cost_business_object1"] + each["plant_code"]) is None:
                    error_list.append(
                        "行标识{}成本事项1{}在工厂{}对应的公司代码不存在".format(each["line_id"],
                                                                                 each["cost_business_object1"],
                                                                                 each["plant_code"]))
            if each.get("profit_center", "") != "":
                # 利润中心检查
                if dict_profit_center_data.get(each["profit_center"] + each["plant_code"]) is None:
                    error_list.append(
                        "行标识{}利润中心{}在工厂{}对应的公司代码不存在".format(each["line_id"], each["profit_center"],
                                                                                each["plant_code"]))
            if each.get("equipment_code", "") != "":
                # 设备ID检查
                if dict_equipment_code_data.get(each["equipment_code"]) is None:
                    error_list.append("行标识{}设备ID{}不存在".format(each["line_id"], each["equipment_code"]))

            if each.get("transaction_currency", "") == "":
                each["transaction_currency"] = get_company_basic_currency(each['plant_code'], dict_company)

    md_header = initialization("t_md_header", db)
    md_item = []
    md_price = []

    # 生成凭证数据
    if not error_list:
        # 单据种类
        md_header["document_category"] = "MDOC"
        # 物料凭证
        md_header["mat_doc_sn"] = ""
        # 年度
        md_header["year"] = head["posting_date"][:4]
        # 过账代码
        md_header["post_code"] = head["post_code"]
        # 凭证日期
        md_header["document_date"] = head["document_date"]
        # 过账日期
        md_header["posting_date"] = head["posting_date"]

        # 汇总唯一号
        md_header["summary_unique_number"] = head.get("summary_unique_number", "")
        # 备注信息1
        md_header["remarks_1"] = head.get("remarks_1", "")
        # 备注信息2
        md_header["remarks_2"] = head.get("remarks_2", "")
        # 供应商交货单
        md_header["vendor_dn"] = head.get("vendor_dn", "")

        # 预留字段
        md_header["reserved1"] = head.get("reserved1", "")
        md_header["reserved2"] = head.get("reserved2", "")
        md_header["reserved3"] = head.get("reserved3", "")
        md_header["reserved4"] = head.get("reserved4", "")
        md_header["reserved5"] = head.get("reserved5", "")
        md_header["reserved6"] = head.get("reserved6", "")
        md_header["reserved7"] = head.get("reserved7", "")
        md_header["reserved8"] = head.get("reserved8", "")
        md_header["reserved9"] = head.get("reserved9", "")
        md_header["reserved10"] = head.get("reserved10", "")

        # 物料凭证类型
        md_header["material_document_type"] = ""

        # 交易汇率 公司代码 信息
        md_header["company_code"], md_header["exchange_rate"] = get_company_info(item[0]["plant_code"],
                                                                                 item[0]["transaction_currency"],
                                                                                 dict_company)

        if head.get('exchange_rate', 0) != 0:
            md_header["exchange_rate"] = head['exchange_rate']

        md_header["create_id"] = user_id
        md_header["update_id"] = user_id

        md_header["ztype"] = head.get('ztype', '')

        if md_header["exchange_rate"] == 0:
            error_list.append("未获取到汇率")

        line_tmp = initialization("t_md_item", db)
        price_tmp = initialization("t_md_price_details", db)

        item_no = 0
        # 行项目设置
        for each in item:
            line = line_tmp.copy()
            price = price_tmp.copy()

            item_no += 1
            # 物料凭证
            line["mat_doc_sn"] = md_header["mat_doc_sn"]
            # 年度
            line["year"] = md_header["year"]
            # 物料凭证信息行号
            line["mat_doc_items"] = item_no
            # 物料凭证行唯一标识
            line["line_id"] = each["line_id"]
            # 凭证行参考唯一标识
            line["parent_id"] = each.get("parent_id", 0)
            # 参考凭证行
            line["ref_item_serial_no"] = 0
            # 自动创建标识
            line["auto_mark"] = 0
            # 移动类型
            line["movement_type"] = each["movement_type"]
            # 物料凭证类型 借贷标识  收发标识  科目修改 业务单据种类
            line, material_document_type, prod_order_mark, wbs_elements_mark, cost_business_object_mark, asset_code1_mark = get_movement_attribute(
                line, line["movement_type"], dict_movement_type)
            if md_header["material_document_type"] == "":
                md_header["material_document_type"] = material_document_type
            if line["debit_credit_mark"] == "":
                error_list.append(
                    "行标识{}未能根据移动类型{}取到借贷标识".format(each["line_id"], each["movement_type"]))
            if line["receipt_consume_mark"] == "":
                error_list.append(
                    "行标识{}未能根据移动类型{}取到收发标识".format(each["line_id"], each["movement_type"]))
            if prod_order_mark == 1:
                if each.get("prodosn", "") == "":
                    error_list.append("行标识{}生产订单必填".format(each["line_id"]))
            if wbs_elements_mark == 1:
                if each.get("wbs_elements", "") == "":
                    error_list.append("行标识{}WBS必填".format(each["line_id"]))
            if cost_business_object_mark == 1:
                if each.get("cost_center", "") == "" and each.get("cost_business_object", "") == "" and each.get(
                        "cost_business_object1", "") == "":
                    error_list.append("行标识{}成本中心/成本事项/成本事项1必填一个".format(each["line_id"]))
            if asset_code1_mark == 1:
                if each.get("asset_code1", "") == "":
                    error_list.append("行标识{}资产卡片必填".format(each["line_id"]))
            # 特殊库存状态1
            line["special_inventory_status1"] = each.get("special_inventory_status1", "")
            # 特殊库存状态2
            line["special_inventory_status2"] = each.get("special_inventory_status2", "")
            # 库存状态
            line["inventory_status"] = get_inventory_status(each["movement_type"], each.get("inventory_status", ""),
                                                            dict_movement_type)
            # 事件类型 物料成本特殊评估标识
            line["transaction_type_code"], line["mat_special_val_mark"] = get_transaction_type_code(
                each["movement_type"], each["plant_code"], each["mat_code"], each.get("rel_po_sn", ""),
                each.get("rel_po_items", 0),
                line["special_inventory_status1"], line["special_inventory_status2"], dict_relation, dict_po_item,
                dict_mat_code)
            if line["transaction_type_code"] == "":
                error_list.append("行标识{}未能根据移动类型{}和采购订单{}信息取到事件类型".format(each["line_id"],
                                                                                                  each["movement_type"],
                                                                                                  each.get("rel_po_sn",
                                                                                                           "")))
            # 工厂代码
            line["plant_code"] = each["plant_code"]
            # 公司代码
            line["company_code"] = md_header["company_code"]
            # 结算公司代码
            line["settle_company_code"] = get_settle_company_code(each["plant_code"], dict_company)
            # 物料编码
            line["mat_code"] = each.get("mat_code", "")
            # 库存地点
            if line["mat_code"] == "" or line["special_inventory_status1"] == "V":
                line["stor_loc_code"] = ""
            else:
                line["stor_loc_code"] = each.get("stor_loc_code", "")
            # 批次号
            line["batch_sn"] = each.get("batch_sn", "")
            # 交易数量
            line["transaction_qty"] = each["transaction_qty"]
            # 交易单位
            line["transaction_uom"] = each["transaction_uom"]
            # 带借贷标识的交易数量
            if line["debit_credit_mark"] == "Cr":
                line["transaction_qty_dc_mark"] = line["transaction_qty"] * -1
            else:
                line["transaction_qty_dc_mark"] = line["transaction_qty"]

            # 基本单位/成本单位/价格控制/评估类/物料组
            line = get_material_uom(line["mat_code"], line["plant_code"], dict_mat_code, line)
            #
            # # 平行数量
            # line["parallel_qty"] = each["parallel_qty"]
            # 平行单位
            line["parallel_uom"] = each.get("parallel_uom", "")

            # 计算基本数量和成本数量
            line = get_other_qty_by_unit(each, line, head['post_code'],
                                         dict_movement_type[each['movement_type']][0]['allow_zero_base_qty'],
                                         dict_movement_type[each['movement_type']][0]['allow_zero_parallel_qty'],
                                         dict_mat_uom_convert)

            if dict_movement_type[each['movement_type']][0]['allow_zero_base_qty'] == 0:
                if line["basic_qty"] <= 0:
                    error_list.append("行标识{}基本数量不能为0".format(each["line_id"]))

            if dict_movement_type[each['movement_type']][0]['allow_zero_parallel_qty'] == 0:
                if line["parallel_qty"] <= 0 and line["parallel_uom"]:
                    error_list.append("行标识{}平行数量不能为0".format(each["line_id"]))

            # 带借贷标识的基本数量
            if line["debit_credit_mark"] == "Cr":
                line["basic_qty_dc_mark"] = line["basic_qty"] * -1
            else:
                line["basic_qty_dc_mark"] = line["basic_qty"]

            # 带借贷标识的成本数量
            if line["debit_credit_mark"] == "Cr":
                line["cost_qty_dc_mark"] = line["cost_qty"] * -1
            else:
                line["cost_qty_dc_mark"] = line["cost_qty"]

            # 带借贷标识的平行数量
            if line["debit_credit_mark"] == "Cr":
                line["parallel_qty_dc_mark"] = line["parallel_qty"] * -1
            else:
                line["parallel_qty_dc_mark"] = line["parallel_qty"]
            # 定价单位 定价单位数量 交易金额 交易货币 采购订单供应商
            line = get_po_qty_amount_info(line, each.get("rel_po_sn", ""), each.get("rel_po_items", 0), dict_po_header,
                                          dict_po_item)
            # 交易货币
            if each.get("transaction_currency", "") == "":
                line["transaction_currency"] = get_company_basic_currency(line['plant_code'], dict_company)
            else:
                line["transaction_currency"] = each["transaction_currency"]
            # 消耗记账 对象标识 价值更新 数量更新
            line = get_movement_label(line, each.get("rel_po_sn", ""), each.get("rel_po_items", 0), dict_movement_type,
                                      dict_mat_code,
                                      dict_po_item, dict_movement_label1, dict_movement_label2, dict_movement_label3)
            if line["consumption_posting_label"] == "":
                error_list.append("行标识{}消耗记账标识不能为空".format(each["line_id"]))
            if line["item_indicator"] == "":
                error_list.append("行标识{}对象标识不能为空".format(each["line_id"]))
            if line["value_update"] == "":
                error_list.append("行标识{}价值更新不能为空".format(each["line_id"]))

            # 关联采购订单
            line["rel_po_sn"] = each.get("rel_po_sn", "")
            # 关联采购订单行
            line["rel_po_items"] = each.get("rel_po_items", 0)
            # 关联采购订单行项目序号
            line["rel_po_component_number"] = each.get("rel_po_component_number", 0)
            # 关联采购订单行序号
            line["rel_po_comp_batch_num"] = each.get("rel_po_comp_batch_num", 0)
            # 关联生产订单组件序号
            line["prodo_component_number"] = each.get("prodo_component_number", '')
            # 生产订单
            line["prodosn"] = each.get("prodosn", "")
            # 生产订单校验
            if dict_prodosn_data.get(line["prodosn"]):
                status_update_ls = [(line["prodosn"], 'GR', 1)]
                result, msg = production_order_status_update(status_update_ls, check_mode=1)
                if not result:
                    error_list.append(msg)
                if dict_prodosn_data[line["prodosn"]][0]['receipt_completed_flag'] == 1:
                    status_update_ls = [(prodosn, 'DLV', 1)]
                    result, msg = production_order_status_update(status_update_ls, check_mode=1)
                    if not result:
                        error_list.append(msg)
                if dict_prodosn_data[line["prodosn"]][0]['receipt_completed_flag'] == 1 and line[
                    'debit_credit_mark'] == 'Dr':
                    error_list.append("行标识{}生产订单已完全收货".format(each["line_id"]), line["prodosn"])
            # 关联交货单
            line["rel_dn_sn"] = each.get("rel_dn_sn", "")
            # 关联交货单行号
            line["rel_dn_item"] = each.get("rel_dn_item", 0)
            # 拣配单号
            line["picking_document"] = each.get("picking_document", "")
            # 批次行号
            line["batch_item"] = each.get("batch_item", 0)
            # 关联预留单
            line["ro_sn"] = each.get("ro_sn", "")
            # 关联预留单行
            line["ro_items"] = each.get("ro_items", 0)
            # 关联销售订单
            line["rel_so_sn"] = each.get("rel_so_sn", "")
            # 关联销售订单行项目
            line["rel_so_items"] = each.get("rel_so_items", 0)
            # 关联单据种类 关联单据号 关联行号 原始单据类型 原始单据号 原始单据行号
            line = get_associated_order(md_header, line)
            # 客户编码
            line["customer_code"] = each.get("customer_code", "")
            # 销售订单
            line["so_sn"] = each.get("so_sn", "")
            # 销售订单行项目
            line["so_items"] = each.get("so_items", 0)
            # 库存调拨单
            line['inv_transfer_order_no'] = each.get("inv_transfer_order_no", '')
            # 库存调拨单行
            line['inv_transfer_order_items'] = each.get("inv_transfer_order_items", 0)
            # 项目编号
            line["project_sn"] = each.get("project_sn", "")
            # 供应商编码
            line["vendor_code"] = each.get("vendor_code", "")
            # 采购订单
            line["po_sn"] = each.get("po_sn", "")
            # 采购订单行项目
            line["po_items"] = each.get("po_items", 0)
            # WBS元素
            line["wbs_elements"] = each.get("wbs_elements", "")
            # 成本中心
            line["cost_center"] = each.get("cost_center", "")
            # 成本事项
            line["cost_business_object"] = each.get("cost_business_object", "")
            # 成本事项1
            line["cost_business_object1"] = each.get("cost_business_object1", "")
            # 利润中心
            line["profit_center"] = each.get("profit_center", "")
            # 会计科目
            line["accounting_subjects"] = each.get("accounting_subjects", "")
            # 资产卡片
            line["asset_code1"] = each.get("asset_code1", "")
            # 子资产
            line["asset_code2"] = each.get("asset_code2", "")
            # 设备ID
            line["equipment_code"] = each.get("equipment_code", "")
            # 快递单号
            line["express_delivery"] = each.get("express_delivery", "")
            # 行参考信息1
            line["reference1_item"] = each.get("reference1_item", "")
            # 行参考信息2
            line["reference2_item"] = each.get("reference2_item", "")
            # 行参考信息3
            line["reference3_item"] = each.get("reference3_item", "")
            # 汇总行
            line["summary_line"] = each.get("summary_line", 0)
            # 批次编码校验
            if each.get("mat_code", "") != "":
                line["batch_sn"], each['batch_number'], msg = check_batch_required(line["mat_code"], line["plant_code"],
                                                                                   line["batch_sn"],
                                                                                   line["debit_credit_mark"],
                                                                                   dict_mat_code, dict_mat_batch,
                                                                                   each.get('batch_number', {}),
                                                                                   dict_movement_type[
                                                                                       line['movement_type']][0],
                                                                                       user_id=user_id
                                                                                       )
                if msg != "":
                    error_list.append("行标识{}{}".format(each["line_id"], msg))

            # 交易前移动平均价（成本货币）/ 交易前移动平均价（本位币）
            # ---待补充
            # 采购项目类别 / 科目分配类别 / 采购订单数量 / 采购订单单位 / 免费标记 / 返工标记 / 返工类型 / 加工工序
            line = get_po_item_other_info(line, line["rel_po_sn"], line["rel_po_items"], dict_po_item)

            # 质检过账标识 / 质量检验单标识
            line["quality_insp_post_mark"] = each.get("quality_insp_post_mark", 0)
            line["quality_insp_order_mark"], msg = get_quality_inspection_mark(line["mat_code"], line["plant_code"],
                                                                               line["inventory_status"],
                                                                               line["movement_type"],
                                                                               line["debit_credit_mark"],
                                                                               line["quality_insp_post_mark"],
                                                                               dict_mat_code, dict_movement_type,
                                                                               dict_mat_insp)
            if msg != "":
                error_list.append("行标识{}{}".format(each["line_id"], msg))

            # 结批标识
            line["batch_closure_flag"] = each.get("batch_closure_flag", 0)
            # 结批日期
            line["batch_closure_date"] = each.get("batch_closure_date", "")
            # 收货完成标记
            line["receipt_completed_flag"] = each.get("receipt_completed_flag", 0)

            # 移动原因
            line["movement_reason"] = each.get("movement_reason", "")

            # 参考凭证年度
            line["rel_document_year"] = each.get("rel_document_year", "")
            # 参考凭证号
            line["rel_document_no"] = each.get("rel_document_no", "")
            # 参考凭证行号
            line["ref_document_mat"] = each.get("ref_document_mat", 0)
            # 前序物料凭证年度
            line["pre_document_year"] = each.get("pre_document_year", "")
            # 前序物料凭证
            line["pre_document_no"] = each.get("pre_document_no", "")
            # 前序物料凭证行号
            line["pre_document_item"] = each.get("pre_document_item", 0)

            # 预留字段
            line["reserved1"] = each.get("reserved1", "")
            line["reserved2"] = each.get("reserved2", "")
            line["reserved3"] = each.get("reserved3", "")
            line["reserved4"] = each.get("reserved4", "")
            line["reserved5"] = each.get("reserved5", "")
            line["reserved6"] = each.get("reserved6", "")
            line["reserved7"] = each.get("reserved7", "")
            line["reserved8"] = each.get("reserved8", "")
            line["reserved9"] = each.get("reserved9", "")
            line["reserved10"] = each.get("reserved10", "")

            # 批次属性
            # batch_number = {}
            # line["batch_number"] = {}
            #
            # batch_number["production_date"] = each["batch_number"].get("production_date", "")
            # batch_number["maturity_date"] = each["batch_number"].get("maturity_date", "")
            # batch_number["vendor_code"] = each["batch_number"].get("vendor_code", "")
            # batch_number["vendor_batch"] = each["batch_number"].get("vendor_batch", "")
            # batch_number["receive_date"] = each["batch_number"].get("receive_date", "")
            # batch_number["lot_no"] = each["batch_number"].get("lot_no", "")
            # batch_number["wafer_id"] = each["batch_number"].get("wafer_id", "")
            # batch_number["mfg_date_wafer"] = each["batch_number"].get("mfg_date_wafer", "")
            # batch_number["vendor_lot_no"] = each["batch_number"].get("vendor_lot_no", "")
            # batch_number["mfg_date_assy"] = each["batch_number"].get("mfg_date_assy", "")
            # batch_number["packing_seal_date"] = each["batch_number"].get("packing_seal_date", "")
            # batch_number["date_code"] = each["batch_number"].get("date_code", "")
            # batch_number["packing_id"] = each["batch_number"].get("packing_id", "")
            # batch_number["bin_grade"] = each["batch_number"].get("bin_grade", "")
            # batch_number["grade"] = each["batch_number"].get("grade", "")
            # batch_number["batch_type"] = each["batch_number"].get("batch_type", "")
            # batch_number["receive_data"] = each["batch_number"].get("receive_data", "")
            # batch_number["cp_vendor"] = each["batch_number"].get("cp_vendor", "")
            # batch_number["bin"] = each["batch_number"].get("bin", "")
            # batch_number["grade1"] = each["batch_number"].get("grade1", "")
            # batch_number["grade2"] = each["batch_number"].get("grade2", "")
            # batch_number["grade3"] = each["batch_number"].get("grade3", "")
            # batch_number["extended_batch_date1"] = each["batch_number"].get("extended_batch_date1", "")
            # batch_number["extended_batch_date2"] = each["batch_number"].get("extended_batch_date2", "")
            # batch_number["extended_batch_date3"] = each["batch_number"].get("extended_batch_date3", "")
            # batch_number["extended_batch_attributes1"] = each["batch_number"].get("extended_batch_attributes1", "")
            # batch_number["extended_batch_attributes2"] = each["batch_number"].get("extended_batch_attributes2", "")
            # batch_number["extended_batch_attributes3"] = each["batch_number"].get("extended_batch_attributes3", "")
            # batch_number["item"] = edit_batch_attribute(each["batch_number"].get("item", []))
            # batch_number["create_id"] = user_id
            # batch_number["update_id"] = user_id
            line["batch_number"] = each.get('batch_number', {})
            line["batch_number"]["create_id"] = user_id
            line["batch_number"]["update_id"] = user_id

            line["create_id"] = user_id
            line["update_id"] = user_id

            md_item.append(line.copy())

            # 价格明细表
            # 物料凭证
            price["mat_doc_sn"] = md_header["mat_doc_sn"]
            # 年度
            price["year"] = md_header["year"]
            # 物料凭证信息行号
            price["mat_doc_items"] = item_no
            md_price = get_po_price(md_price, line, price, user_id, dict_price_data)
    if not error_list:
        # 库存校验
        inventory_begin = time.time()
        msg_list = get_inventory_qty(md_item, md_header["posting_date"], dict_plant_storage, db)
        print("库存校验耗时：", time.time() - inventory_begin)
        if msg_list:
            error_list.extend(msg_list)

    if error_list:
        code = 500
        msg = "存在错误,请检查"
    else:
        code = 200
        msg = "检查无误"

        # 批次继承
        md_item = batch_inherit2(md_item, dict_prodosn_data, db)
    return code, msg, error_list, md_header, md_item, md_price


def batch_inherit2(item, dict_prodosn_data, db):
    movement_type = []
    for each in item:
        movement_type.append(each['movement_type'])
    # 获取批次策略信息
    query_sql = """
        SELECT
            a.`batch_inheritance_type`,
            a.`movement_type`,
            a.`prodo_type`,
            b.`field_code`,
            b.`multiple_data_rule`,
            b.`priority_code`,
            b.`is_update`
        FROM
            `t_batch_inheritance_strategy_alloc` as a 
        JOIN
            `t_batch_inheritance_strategy` as b
        ON
            a.`batch_inheritance_strategy` = b.`batch_inheritance_strategy`
        WHERE
            a.`movement_type` in ('{}')
        AND
            a.`activation_flag` = 1
    """.format("','".join(movement_type))
    data = db.query_sql(query_sql)

    if not data:
        return item

    # 按采购订单类型+移动类型分组
    dict_batch_config = {}
    for each in data:
        key = each["prodo_type"] + each["movement_type"]
        if key not in dict_batch_config:
            dict_batch_config[key] = []
            dict_batch_config[key].append(each)
        else:
            dict_batch_config[key].append(each)

    prodosn = []
    for each in item:
        if each['prodosn']:
            prodosn.append(each['prodosn'])

    dict_prod_component = get_prodosn_component(prodosn, db)

    mat_code = []
    batch_sn = []
    for key in dict_prod_component:
        for each in dict_prod_component[key]:
            if each['batch_sn']:
                mat_code.append(each['mat_code'])
                batch_sn.append(each['batch_sn'])

    # 获取批次属性
    dict_batch_number = get_batch_attribute_mult(mat_code, batch_sn, db)

    for each in item:
        if each['batch_sn']:
            batch_attr = []
            if dict_prod_component.get(each['prodosn']):
                for i in dict_prod_component[each['prodosn']]:
                    key = i['mat_code'] + i['batch_sn']
                    batch_attr = dict_batch_number[key]

                key = str(dict_prodosn_data[each['prodosn']][0]['prodo_type']) + each['movement_type']
                each['batch_number'] = set_batch_number_attribute(dict_batch_config, key, batch_attr,
                                                                  each['batch_number'])

    return item


def get_prodosn_component(prodosn, db):
    query_sql = """
        SELECT
            `prodosn`,
            `item_no`,
            `prodo_component_number`,
            `mat_code`,
            `batch_sn`,
            `main_material_mark`
        FROM
            `t_pro_order_component`
        WHERE
            `prodosn` in ('{}')
        AND
            `main_material_mark` = 1
        """.format("','".join(prodosn))
    data = db.query_sql(query_sql)

    dict_prod_component = {}
    for each in data:
        key = each["prodosn"]
        if key not in dict_prod_component:
            dict_prod_component[key] = []
            dict_prod_component[key].append(each)
        else:
            dict_prod_component[key].append(each)

    return dict_prod_component


# 正式过账代码6
def post_data_postcode6(user_id, md_header, md_item, md_price, db):
    code = 0
    msg = ""
    mat_doc_sn = ""
    year = ""
    error_list = []

    try:
        mat_code = md_item[0]["mat_code"]
        batch_sn = md_item[0]["batch_sn"]
        lock_key = f"LOCK_{mat_code}_{batch_sn}"
    except:
        lock_key = f"LOCK_USER_{user_id}"

    try:
        # 加库存锁
        code, msg = lock_data(md_item, LockAction.lock, lock_key)
        if code != 200:
            error_list.append(msg)
            raise Exception(msg)

        # 调用会计引擎
        input = json.dumps([{"header": md_header, "items": md_item, "details": md_price}])
        print(input)
        sh = SystemHelper()

        c_begin = time.time()
        output = json.loads(sh.execOperator("OnConsumeMat", input)["data"])
        print("调用C耗时： ", time.time() - c_begin)
        print(output)

        if output["result"] == 0:
            if "data" in output:
                code = 200
                msg = "执行成功"
                if output["data"][0]["status"] == "E":
                    code = 500
                    msg = output["data"][0]["msg"]
                else:
                    mat_doc_sn = output["data"][0]["mat_doc_sn"]
                    year = output["data"][0]["year"]
                    msg = "过账成功,物料凭证:{} 年度{}".format(mat_doc_sn, year)
            else:
                code = 500
                msg = output.get("msg", "会计引擎异常")
        else:
            code = 500
            msg = output["msg"]

    except Exception as e:
        if not error_list:
            error_list.append(str(e))
        code = 500
        msg = "存在错误,请检查"

    finally:
        lock_data(md_item, LockAction.unlock, lock_key)

    return code, msg, error_list, mat_doc_sn, year


# 检查过账代码6的参数
def check_data_postcode6(user_id, head, item, db):
    code = 200
    msg = ""
    error_list = []

    # 增强 -- 检验前
    code, msg, error_list, head, item = before_check(user_id, head, item)
    if code != 200:
        return code, msg, error_list, [], [], []

    dict_movement_type = {}
    movement_type = []
    plant_code = []
    plant_code_data = []
    dict_plant_storage = {}
    movement_special_inventory_status1 = []
    movement_special_inventory_status2 = []
    mat_code = []
    dict_mat_code = {}
    dict_mat_code_cost = {}
    po_sn = []
    dict_po_header = {}
    dict_po_item = {}
    prodosn = []
    dict_prodosn_data = {}
    dn_sn = []
    dict_dn_sn_header = {}
    dict_dn_sn_item = {}
    picking_document = []
    dict_picking_document = {}
    procure_dn_sn = []
    dict_procure_dn_sn_data = {}
    ro_sn = []
    dict_ro_sn_data = {}
    so_sn = []
    dict_so_sn_data = {}
    customer_code = []
    dict_customer_code_data = {}
    vendor_code = []
    dict_vendor_code_data = {}
    cost_center = []
    dict_cost_center_data = {}
    cost_business_object = []
    dict_cost_business_object_data = {}
    profit_center = []
    dict_profit_center_data = {}
    equipment_code = []
    dict_equipment_code_data = {}
    dict_company = {}
    dict_relation = {}
    dict_relation2 = {}
    dict_movement_label1 = {}
    dict_movement_label2 = {}
    dict_movement_label3 = {}
    dict_mat_batch = {}
    batch = []
    dict_mat_insp = {}
    dict_price_data = {}
    dict_inventory_status = {}
    inv_transfer_order_no = []
    dict_inv_transfer_order = {}
    dict_inv_transfer_order_item = {}

    # 性能优化
    for each in item:
        # 移动类型
        if each.get("movement_type", "") != "":
            movement_type.append(each['movement_type'])
        # 工厂
        if each.get("plant_code", "") != "":
            plant_code.append(each['plant_code'])

        # 物料编码
        if each.get("mat_code", "") != "":
            mat_code.append(each['mat_code'])

        # 采购订单
        if each.get("rel_po_sn", '') != '':
            po_sn.append(each['rel_po_sn'])
        if each.get('po_sn', '') != '':
            po_sn.append(each['po_sn'])

        # 生产订单
        if each.get('prodosn', '') != '':
            prodosn.append(each['prodosn'])

        # 交货单
        if each.get('rel_dn_sn', '') != '':
            dn_sn.append(each['rel_dn_sn'])

        # 拣配单
        if each.get('picking_document', '') != '':
            picking_document.append(each['picking_document'])

        # 采购交货单
        if each.get('rel_procure_dn_sn', '') != '':
            procure_dn_sn.append(each['rel_procure_dn_sn'])

        # 预留
        if each.get('ro_sn', '') != '':
            ro_sn.append(each['ro_sn'])

        # 销售订单
        if each.get('rel_so_sn', '') != '':
            so_sn.append(each['rel_so_sn'])
        if each.get('so_sn', '') != '':
            so_sn.append(each['so_sn'])

        # 客户
        if each.get('customer_code', '') != '':
            customer_code.append(each['customer_code'])

        # 供应商
        if each.get('vendor_code', '') != '':
            vendor_code.append(each['vendor_code'])

        # 成本中心
        if each.get('cost_center', '') != '':
            cost_center.append(each['cost_center'])

        # 成本事项
        if each.get('cost_business_object', '') != '':
            cost_business_object.append(each['cost_business_object'])
        if each.get('cost_business_object1', '') != '':
            cost_business_object.append(each['cost_business_object1'])

        # 利润中心
        if each.get('profit_center', '') != '':
            profit_center.append(each['profit_center'])

        # 设备
        if each.get('equipment_code', '') != '':
            equipment_code.append(each['equipment_code'])

        # 批次
        if each.get('batch_sn', '') != '':
            batch.append(each['batch_sn'])
        # 库存调拨单
        if each.get("inv_transfer_order_no", "") != '':
            inv_transfer_order_no.append(each['inv_transfer_order_no'])

    data_begin = time.time()
    # 获取移动类型属性
    dict_movement_type = get_movement_type_info(movement_type, db)
    # 获取工厂
    plant_code_data = get_plant_code_data(plant_code, db)
    # 获取工厂对应库存地点
    dict_plant_storage = get_plant_storage(plant_code, db)
    # 获取移动类型对应特殊库存状态
    movement_special_inventory_status1, movement_special_inventory_status2, dict_relation, dict_relation2 = get_movement_special_inventory_status(
        movement_type, db)
    # 获取物料主数据信息
    dict_mat_code = get_mat_code_info(mat_code, plant_code, db)
    # 获取物料成本视图
    dict_mat_code_cost = get_mat_code_cost_info(mat_code, plant_code, db)
    # 获取物料单位换算关系
    dict_mat_uom_convert = get_mat_uom_convert(mat_code, db)
    # 获取采购订单抬头信息
    dict_po_header = get_po_header(po_sn, db)
    # 获取采购订单行项目信息
    dict_po_item = get_po_item(po_sn, db)
    # 获取生产订单
    dict_prodosn_data = get_prodosn_data(prodosn, db)
    # 获取交货单抬头信息
    dict_dn_sn_header = get_dn_header(dn_sn, db)
    # 获取交货单行项目信息
    dict_dn_sn_item = get_dn_sn_item(dn_sn, db)
    # 获取拣配单信息
    dict_picking_document = get_picking_document_info(picking_document, db)
    # 获取采购交货单信息
    # dict_procure_dn_sn_data = get_procure_dn_sn_info(procure_dn_sn, db)
    # 获取预留单信息
    dict_ro_sn_data = get_ro_sn_info(ro_sn, db)
    # 获取销售订单信息
    dict_so_sn_data = get_so_sn_info(so_sn, db)
    # 获取客户信息
    dict_customer_code_data = get_customer_code_info(customer_code, db)
    # 获取供应商信息
    dict_vendor_code_data = get_vendor_code_info(vendor_code, db)
    # 获取成本中心
    dict_cost_center_data = get_cost_center_info(cost_center, db)
    # 获取成本事项
    dict_cost_business_object_data = get_cost_business_object_info(cost_business_object, db)
    # 利润中心
    dict_profit_center_data = get_profit_center_info(profit_center, db)
    # 获取设备主数据信息
    dict_equipment_code_data = get_equipment_code_info(equipment_code, db)
    # 按工厂获取公司信息
    dict_company = get_company_info_by_plant(plant_code, db)
    # 获取移动类型配置信息
    dict_movement_label1, dict_movement_label2, dict_movement_label3 = get_movement_label_info(movement_type, db)
    # 获取物料批次信息
    dict_mat_batch = get_mat_code_and_batch(mat_code, batch, db)
    # 获取物料质检信息
    dict_mat_insp = get_mat_insp_info(mat_code, plant_code, db)
    # 获取采购订单价格明细
    # dict_price_data = get_po_price_data(po_sn, db)
    # 获取库存状态
    dict_inventory_status = get_all_inventory_status(db)
    # 获取库存调拨单
    dict_inv_transfer_order = get_inv_transfer_order(inv_transfer_order_no, db)
    # 获取库存调拨单行
    dict_inv_transfer_order_item = get_inv_transfer_order_item(inv_transfer_order_no, db)

    print("取值耗时: ", time.time() - data_begin)
    for each in item:
        # 必输校验
        # 行唯一标识校验
        if each.get("line_id", "") == "":
            error_list.append("行唯一标识必输")
            continue

        # 移动类型校验
        if each.get("movement_type", "") == "":
            error_list.append("行标识{}移动类型必输".format(each["line_id"]))
        # 交易数量
        if Decimal(each.get("transaction_qty", 0)) <= 0:
            error_list.append("行标识{}交易数量必须大于0".format(each["line_id"]))

        # 交易单位
        if each.get("transaction_uom", "") == "":
            error_list.append("行标识{}交易单位必输".format(each["line_id"]))
        # # 基本数量
        # if each.get("basic_qty", 0) == 0:
        #     error_list.append("行标识{}基本数量必输".format(each["line_id"]))
        # # 基本单位
        # if each.get("basic_uom", "") == "":
        #     error_list.append("行标识{}基本单位必输".format(each["line_id"]))
        # # 平行单位
        # if each.get("parallel_uom", "") == "":
        #     error_list.append("行标识{}平行单位必输".format(each["line_id"]))
        # # 平行数量
        # if each.get("parallel_uom", "") == each.get("basic_uom", ""):
        #     each["parallel_qty"] = each["basic_qty"]
        # else:
        #     if each.get("basic_qty", 0) == 0:
        #         each["parallel_qty"] = 0
        #     else:
        #         if each.get("parallel_qty", 0) == 0:
        #             error_list.append("行标识{}平行数量必输".format(each["line_id"]))
        # if each.get("parallel_uom", "") != "":
        #     if each.get("parallel_qty", 0) == 0:
        #         error_list.append("行标识{}平行数量必输".format(each["line_id"]))
        # 关联交货单
        if each.get("rel_dn_sn", "") == "":
            error_list.append("行标识{}关联交货单必输".format(each["line_id"]))
        # 关联交货单行号
        if each.get("rel_dn_item", "") == "":
            error_list.append("行标识{}关联交货单行号必输".format(each["line_id"]))
        # 拣配单号
        if each.get("picking_document", "") == "":
            error_list.append("行标识{}拣配单号必输".format(each["line_id"]))
        # 批次行号
        if each.get("batch_item", 0) == 0:
            error_list.append("行标识{}批次行号必输".format(each["line_id"]))
        # 工厂代码
        if each.get("plant_code", "") == "":
            error_list.append("行标识{}工厂代码必输".format(each["line_id"]))
        # 库存地点
        if each.get("mat_code", "") != "" and each["special_inventory_status1"] != 'V':
            if each["stor_loc_code"] == "":
                error_list.append("行标识{}库存地点必输".format(each["line_id"]))

        # # 特殊库存状态1
        # if each["special_inventory_status1"] == "":
        #     error_list.append("行标识{}特殊库存状态1必输".format(each["line_id"]))
        # # 特殊库存状态1
        # if each["special_inventory_status1"] == "":
        #     error_list.append("行标识{}特殊库存状态1必输".format(each["line_id"]))
        # 库存状态
        if each.get("inventory_status", "") == "" and each.get("mat_code", "") != "":
            error_list.append("行标识{}库存状态必输".format(each["line_id"]))

        # 存在性校验
        if not error_list:
            # 移动类型校验
            if dict_movement_type.get(each["movement_type"]) is None:
                error_list.append("行标识{}移动类型{}不存在".format(each["line_id"], each["movement_type"]))
            else:
                if dict_movement_type[each['movement_type']][0]['post_code'] != head["post_code"]:
                    error_list.append("行标识{}移动类型{}不适用过账码{}".format(each["line_id"], each["movement_type"],
                                                                                head["post_code"]))
            # 工厂代码校验
            if each["plant_code"] not in plant_code_data:
                error_list.append("行标识{}工厂代码{}不存在".format(each["line_id"], each["plant_code"]))
            # 库存地点校验
            if each.get("stor_loc_code", "") != "":
                # if not check_if_stor_loc_code_exists(each["stor_loc_code"]):
                #     error_list.append("行标识{}库存地点{}不存在".format(each["line_id"], each["stor_loc_code"]))
                # else:
                if dict_plant_storage.get(each["plant_code"] + each["stor_loc_code"]) is None:
                    error_list.append(
                        "行标识{}在工厂{}下库存地点{}未分配".format(each["line_id"], each["plant_code"],
                                                                    each["stor_loc_code"]))
            # 特殊库存状态1校验
            if each.get("special_inventory_status1", "") != "":
                if each["movement_type"] + each["special_inventory_status1"] not in movement_special_inventory_status1:
                    error_list.append(
                        "行标识{}在移动类型{}下特殊库存标识1{}未分配".format(each["line_id"], each["movement_type"],
                                                                             each["special_inventory_status1"]))
            # 库存状态
            if each.get("inventory_status", "") != "":
                if dict_inventory_status.get(each["inventory_status"]) is None:
                    error_list.append("行标识{}库存状态{}不存在".format(each["line_id"], each["inventory_status"]))
            # 物料状态检查
            if each.get("mat_code", "") != "":
                key = each["mat_code"] + each["plant_code"]
                if dict_mat_code.get(key) is None:
                    error_list.append("行标识{}物料编码{}在工厂{}不存在".format(each["line_id"], each["mat_code"], each["plant_code"]))
                else:
                    mat_info = dict_mat_code[key][0]
                    if mat_info.get('deleted_mark', 0) == 1 or mat_info.get('lock_flag', 0) == 1:
                        error_list.append("行标识{}物料编码{}已删除或锁定".format(each["line_id"], each["mat_code"]))
                    elif mat_info.get('value_update', 0) == 1:
                        if dict_mat_code_cost.get(key) is None:
                            error_list.append("行标识{}物料编码{}成本视图未扩".format(each["line_id"], each["mat_code"]))
            # 采购订单状态检查
            if each.get("rel_po_sn", "") != "":
                msg = check_po_status(each["rel_po_sn"], dict_po_header)
                if msg != "":
                    error_list.append("行标识{}{}".format(each["line_id"], msg))
                else:
                    # 采购订单行检查
                    msg = check_po_item_status(head["post_code"], each["rel_po_sn"], each["rel_po_items"], dict_po_item)
                if msg != "":
                    error_list.append("行标识{}{}".format(each["line_id"], msg))
            # 暂时注释 # DJ
            # if each.get("rel_po_component_number", 0) != 0:
            #     # 采购订单行的序号检查
            #     if check_if_po_component_exists(each["rel_po_sn"], each["rel_po_items"], each["rel_po_component_number"]):
            #         error_list.append(
            #             "行标识{}关联采购订单{}行{}项目序号{}不存在".format(each["line_id"], each["rel_po_sn"],
            #                                                                 each["rel_po_items"], each["rel_po_component_number"]))
            # if each.get("rel_po_comp_batch_num", 0) != 0:
            #     # 采购订单库存绑定表检查
            #     if check_if_po_batch_binding_exists(each["rel_po_sn"], each["rel_po_items"], each["rel_po_component_number"],
            #                                         each["rel_po_comp_batch_num"]):
            #         error_list.append("行标识{}关联采购订单{}行{}项目序号{}绑定序号{}不存在".format(each["line_id"],
            #                                                                                         each["rel_po_sn"],
            #                                                                                         each[
            #                                                                                             "rel_po_items"],
            #                                                                                         each["rel_po_component_number"],
            #                                                                                         each["rel_po_comp_batch_num"]))

            if each.get("prodosn", "") != "":
                # 生产订单检查
                if dict_prodosn_data.get(each["prodosn"]) is None:
                    error_list.append("行标识{}生产订单{}不存在".format(each["line_id"], each["prodosn"]))
            if each.get("rel_dn_sn", "") != "":
                # 关联交货单检查
                if dict_dn_sn_header.get(each["rel_dn_sn"]) is None:
                    error_list.append("行标识{}关联交货单{}不存在".format(each["line_id"], each["rel_dn_sn"]))
                elif dict_dn_sn_item.get(each["rel_dn_sn"] + str(each.get("rel_dn_item", 0))) is None:
                    error_list.append("行标识{}关联交货单{}行号{}不存在".format(each["line_id"], each["rel_dn_sn"],
                                                                                each.get("rel_dn_item", 0)))
            if each.get("picking_document", "") != "":
                # 拣配单号检查
                if dict_picking_document.get(each["picking_document"] + str(each.get("batch_item", 0))) is None:
                    error_list.append("行标识{}拣配单号{}不存在".format(each["line_id"], each["picking_document"]))
            if each.get("inv_transfer_order_no", "") != "":
                # 库存调拨单
                if dict_inv_transfer_order.get(each["inv_transfer_order_no"]) is None:
                    error_list.append(
                        "行标识{}库存调拨单{}不存在".format(each["line_id"], each["inv_transfer_order_no"]))
                elif dict_inv_transfer_order_item.get(
                        each["inv_transfer_order_no"] + str(each.get("inv_transfer_order_items", 0))) is None:
                    error_list.append(
                        "行标识{}库存调拨单{}行号{}不存在".format(each["line_id"], each["inv_transfer_order_no"],
                                                                  each.get("inv_transfer_order_items", 0)))

            if each.get("ro_sn", "") != "":

                if dict_ro_sn_data.get(each["ro_sn"] + str(each.get("ro_items", 0))) is None:
                    error_list.append("行标识{}关联预留单{}行号{}不存在".format(each["line_id"], each["ro_sn"],
                                                                                each.get("ro_items", 0)))
            if each.get("rel_so_sn", "") != "":

                if dict_so_sn_data.get(each["rel_so_sn"] + str(each.get("rel_so_items", 0))) is None:
                    error_list.append("行标识{}关联销售订单{}行号{}不存在".format(each["line_id"], each["rel_so_sn"],
                                                                                  each.get("rel_so_items", 0)))
            if each.get("special_inventory_status1", "") == "C" or each.get("special_inventory_status1", "") == "CC":
                # 客户检查
                if each.get("customer_code", "") == "":
                    error_list.append("行标识{}客户编码必输".format(each["line_id"]))
                else:
                    if dict_customer_code_data.get(each["customer_code"]) is None:
                        error_list.append("行标识{}客户编码{}不存在".format(each["line_id"], each["customer_code"]))
            else:
                each["customer_code"] = ""

            if each.get("special_inventory_status1", "") == "S":
                # 销售订单检查
                if each.get("so_sn", "") == "" or each.get("so_items", "") == "":
                    error_list.append("行标识{}销售订单信息必输".format(each["line_id"]))
                else:
                    if dict_so_sn_data.get(each.get("so_sn", "") + str(each.get("so_items", 0))) is None:
                        error_list.append("行标识{}销售订单{}行号{}不存在".format(each["line_id"], each["rel_so_sn"],
                                                                                  each.get("rel_so_items", 0)))
            else:
                each["so_sn"] = ""
                each["so_items"] = 0

            if each.get("special_inventory_status1", "") == "P":
                # 项目编码检查
                if each.get("project_sn", "") == "":
                    error_list.append("行标识{}项目编码必输".format(each["line_id"]))
                    # 项目编码检查待定-----
            else:
                each["project_sn"] = ""

            if each.get("special_inventory_status1", "") == "V" or each.get("special_inventory_status1", "") == "SC":
                # 供应商编码检查
                if each.get("vendor_code", "") == "":
                    error_list.append("行标识{}供应商编码必输".format(each["line_id"]))
                else:
                    if dict_vendor_code_data.get(each["vendor_code"]) is None:
                        error_list.append("行标识{}供应商编码{}不存在".format(each["line_id"], each["vendor_code"]))

                if each["special_inventory_status1"] == "V":
                    if each.get("po_sn", "") != "":
                        # 采购订单检查
                        if dict_po_header.get(each["po_sn"]) is None:
                            error_list.append("行标识{}采购订单{}不存在".format(each["line_id"], each["po_sn"]))
                        else:
                            if dict_po_item.get(each["po_sn"] + str(each.get("po_items", 0))) is None:
                                error_list.append(
                                    "行标识{}采购订单{}行号{}不存在".format(each["line_id"], each["po_sn"],
                                                                            each.get("po_items", 0)))
                else:
                    each["po_sn"] = ""
                    each["po_items"] = 0
            else:
                each["vendor_code"] = ""
                each["po_sn"] = ""
                each["po_items"] = 0

            if each.get("cost_center", "") != "":
                # 成本中心检查
                if dict_cost_center_data.get(each["cost_center"] + each["plant_code"]) is None:
                    error_list.append(
                        "行标识{}成本中心{}在工厂{}对应的公司代码不存在".format(each["line_id"], each["cost_center"],
                                                                                each["plant_code"]))
            if each.get("cost_business_object", "") != "":
                # 成本事项检查
                if dict_cost_business_object_data.get(each["cost_business_object"] + each["plant_code"]) is None:
                    error_list.append(
                        "行标识{}成本事项{}在工厂{}对应的公司代码不存在".format(each["line_id"],
                                                                                each["cost_business_object"],
                                                                                each["plant_code"]))
            if each.get("cost_business_object1", "") != "":
                # 成本事项2检查
                if dict_cost_business_object_data.get(each["cost_business_object1"] + each["plant_code"]) is None:
                    error_list.append(
                        "行标识{}成本事项1{}在工厂{}对应的公司代码不存在".format(each["line_id"],
                                                                                 each["cost_business_object1"],
                                                                                 each["plant_code"]))
            if each.get("profit_center", "") != "":
                # 利润中心检查
                if dict_profit_center_data.get(each["profit_center"] + each["plant_code"]) is None:
                    error_list.append(
                        "行标识{}利润中心{}在工厂{}对应的公司代码不存在".format(each["line_id"], each["profit_center"],
                                                                                each["plant_code"]))
            if each.get("equipment_code", "") != "":
                # 设备ID检查
                if dict_equipment_code_data.get(each["equipment_code"]) is None:
                    error_list.append("行标识{}设备ID{}不存在".format(each["line_id"], each["equipment_code"]))

            if check_rel_dn_status('6', each["picking_document"], each["batch_item"],
                                   each.get("special_inventory_status2", ""), dict_picking_document):
                error_list.append("行标识{}拣配单号{}不允许过账".format(each["line_id"], each["picking_document"]))

            if each.get("transaction_currency", "") == "":
                each["transaction_currency"] = get_company_basic_currency(each['plant_code'], dict_company)

    md_header = initialization("t_md_header", db)
    md_item = []
    md_price = []

    # 生成凭证数据
    if not error_list:
        # 单据种类
        md_header["document_category"] = "MDOC"
        # 物料凭证
        md_header["mat_doc_sn"] = ""
        # 年度
        md_header["year"] = head["posting_date"][:4]
        # 过账代码
        md_header["post_code"] = head["post_code"]
        # 凭证日期
        md_header["document_date"] = head["document_date"]
        # 过账日期
        md_header["posting_date"] = head["posting_date"]
        # 汇总唯一号
        md_header["summary_unique_number"] = head.get("summary_unique_number", "")
        # 备注信息1
        md_header["remarks_1"] = head.get("remarks_1", "")
        # 备注信息2
        md_header["remarks_2"] = head.get("remarks_2", "")
        # 供应商交货单
        md_header["vendor_dn"] = head.get("vendor_dn", "")
        # 物料凭证类型
        md_header["material_document_type"] = ""
        # 交易汇率 公司代码 信息
        md_header["company_code"], md_header["exchange_rate"] = get_company_info(item[0]["plant_code"],
                                                                                 item[0]["transaction_currency"],
                                                                                 dict_company)

        if head.get('exchange_rate', 0) != 0:
            md_header["exchange_rate"] = head['exchange_rate']

        # 预留字段
        md_header["reserved1"] = head.get("reserved1", "")
        md_header["reserved2"] = head.get("reserved2", "")
        md_header["reserved3"] = head.get("reserved3", "")
        md_header["reserved4"] = head.get("reserved4", "")
        md_header["reserved5"] = head.get("reserved5", "")
        md_header["reserved6"] = head.get("reserved6", "")
        md_header["reserved7"] = head.get("reserved7", "")
        md_header["reserved8"] = head.get("reserved8", "")
        md_header["reserved9"] = head.get("reserved9", "")
        md_header["reserved10"] = head.get("reserved10", "")

        md_header["create_id"] = user_id
        md_header["update_id"] = user_id

        md_header["ztype"] = head.get('ztype', '')

        if md_header["exchange_rate"] == 0:
            error_list.append("未获取到汇率")

        line_tmp = initialization("t_md_item", db)
        item_no = 0

        # 行项目设置
        for each in item:

            line = line_tmp.copy()

            item_no += 1
            # 物料凭证
            line["mat_doc_sn"] = md_header["mat_doc_sn"]
            # 年度
            line["year"] = md_header["year"]
            # 物料凭证信息行号
            line["mat_doc_items"] = item_no
            # 物料凭证行唯一标识
            line["line_id"] = each["line_id"]
            # 凭证行参考唯一标识
            line["parent_id"] = each.get("parent_id", 0)
            # 参考凭证行
            line["ref_item_serial_no"] = 0
            # 自动创建标识
            line["auto_mark"] = 0
            # 移动类型
            line["movement_type"] = each["movement_type"]

            # 物料凭证类型 借贷标识  收发标识  科目修改 业务单据种类
            line, material_document_type, prod_order_mark, wbs_elements_mark, cost_business_object_mark, asset_code1_mark = get_movement_attribute(
                line, line["movement_type"], dict_movement_type)
            if md_header["material_document_type"] == "":
                md_header["material_document_type"] = material_document_type
            if line["debit_credit_mark"] == "":
                error_list.append(
                    "行标识{}未能根据移动类型{}取到借贷标识".format(each["line_id"], each["movement_type"]))
            if line["receipt_consume_mark"] == "":
                error_list.append(
                    "行标识{}未能根据移动类型{}取到收发标识".format(each["line_id"], each["movement_type"]))
            if prod_order_mark == 1:
                if each.get("prodosn", "") == "":
                    error_list.append("行标识{}生产订单必填".format(each["line_id"]))
            if wbs_elements_mark == 1:
                if each.get("wbs_elements", "") == "":
                    error_list.append("行标识{}WBS必填".format(each["line_id"]))
            if cost_business_object_mark == 1:
                if each.get("cost_center", "") == "" and each.get("cost_business_object", "") == "" and each.get(
                        "cost_business_object1", "") == "":
                    error_list.append("行标识{}成本中心/成本事项/成本事项1必填一个".format(each["line_id"]))
            if asset_code1_mark == 1:
                if each.get("asset_code1", "") == "":
                    error_list.append("行标识{}资产卡片必填".format(each["line_id"]))
            # 特殊库存状态1
            line["special_inventory_status1"] = each.get("special_inventory_status1", "")
            # 特殊库存状态2
            line["special_inventory_status2"] = each.get("special_inventory_status2", "")
            # 库存状态
            line["inventory_status"] = get_inventory_status(each["movement_type"], each.get("inventory_status", ""),
                                                            dict_movement_type)
            # 事件类型 物料成本特殊评估标识
            line["transaction_type_code"], line["mat_special_val_mark"] = get_transaction_type_code(
                each["movement_type"], each["plant_code"], each["mat_code"], each.get("rel_po_sn", ""),
                each.get("rel_po_items", 0),
                line["special_inventory_status1"], line["special_inventory_status2"], dict_relation, dict_po_item,
                dict_mat_code)
            if line["transaction_type_code"] == "":
                error_list.append("行标识{}未能根据移动类型{}和采购订单{}信息取到事件类型".format(each["line_id"],
                                                                                                  each["movement_type"],
                                                                                                  each.get("rel_po_sn",
                                                                                                           "")))
            # 工厂代码
            line["plant_code"] = each["plant_code"]
            # 公司代码
            line["company_code"] = md_header["company_code"]
            # 结算公司代码
            line["settle_company_code"] = get_settle_company_code(each["plant_code"], dict_company)
            # 物料编码
            line["mat_code"] = each.get("mat_code", "")
            # 库存地点
            if line["mat_code"] == "" or line["special_inventory_status1"] == "V":
                line["stor_loc_code"] = ""
            else:
                line["stor_loc_code"] = each.get("stor_loc_code", "")
            # 批次号

            line["batch_sn"] = each.get("batch_sn", "")
            # 交易数量
            line["transaction_qty"] = each["transaction_qty"]
            # 交易单位
            line["transaction_uom"] = each["transaction_uom"]
            # 带借贷标识的交易数量
            if line["debit_credit_mark"] == "Cr":
                line["transaction_qty_dc_mark"] = line["transaction_qty"] * -1
            else:
                line["transaction_qty_dc_mark"] = line["transaction_qty"]

            # 基本单位/成本单位/价格控制/评估类/物料组
            line = get_material_uom(line["mat_code"], line["plant_code"], dict_mat_code, line)

            # # 平行数量
            # line["parallel_qty"] = each["parallel_qty"]
            # 平行单位
            line["parallel_uom"] = each.get("parallel_uom", "")

            # 计算基本数量和成本数量
            line = get_other_qty_by_unit(each, line, head['post_code'],
                                         dict_movement_type[each['movement_type']][0]['allow_zero_base_qty'],
                                         dict_movement_type[each['movement_type']][0]['allow_zero_parallel_qty'],
                                         dict_mat_uom_convert)

            if dict_movement_type[each['movement_type']][0]['allow_zero_base_qty'] == 0:
                if line["basic_qty"] <= 0:
                    error_list.append("行标识{}基本数量不能为0".format(each["line_id"]))

            if dict_movement_type[each['movement_type']][0]['allow_zero_parallel_qty'] == 0:
                if line["parallel_qty"] <= 0 and line["parallel_uom"]:
                    error_list.append("行标识{}平行数量不能为0".format(each["line_id"]))

            # 带借贷标识的基本数量
            if line["debit_credit_mark"] == "Cr":
                line["basic_qty_dc_mark"] = line["basic_qty"] * -1
            else:
                line["basic_qty_dc_mark"] = line["basic_qty"]

            # 带借贷标识的成本数量
            if line["debit_credit_mark"] == "Cr":
                line["cost_qty_dc_mark"] = line["cost_qty"] * -1
            else:
                line["cost_qty_dc_mark"] = line["cost_qty"]

            # 带借贷标识的平行数量
            if line["debit_credit_mark"] == "Cr":
                line["parallel_qty_dc_mark"] = line["parallel_qty"] * -1
            else:
                line["parallel_qty_dc_mark"] = line["parallel_qty"]
            # 定价单位 定价单位数量 交易金额 交易货币 采购订单供应商
            line = get_po_qty_amount_info(line, each.get("rel_po_sn", ""), each.get("rel_po_items", 0), dict_po_header,
                                          dict_po_item)
            # 交易货币

            if each.get("transaction_currency", "") == "":
                line["transaction_currency"] = get_company_basic_currency(line["plant_code"], dict_company)
            else:
                line["transaction_currency"] = each["transaction_currency"]
            # 消耗记账 对象标识 价值更新 数量更新
            line = get_movement_label(line, each.get("rel_po_sn", ""), each.get("rel_po_items", 0), dict_movement_type,
                                      dict_mat_code,
                                      dict_po_item, dict_movement_label1, dict_movement_label2, dict_movement_label3)
            if line["consumption_posting_label"] == "":
                error_list.append("行标识{}消耗记账标识不能为空".format(each["line_id"]))
            if line["item_indicator"] == "":
                error_list.append("行标识{}对象标识不能为空".format(each["line_id"]))
            if line["value_update"] == "":
                error_list.append("行标识{}价值更新不能为空".format(each["line_id"]))
            # 关联采购订单
            line["rel_po_sn"] = each.get("rel_po_sn", "")
            # 关联采购订单行
            line["rel_po_items"] = each.get("rel_po_items", 0)
            # 关联采购订单行项目序号
            line["rel_po_component_number"] = each.get("rel_po_component_number", 0)
            # 关联采购订单行序号
            line["rel_po_comp_batch_num"] = each.get("rel_po_comp_batch_num", 0)
            # 关联生产订单组件序号
            line["prodo_component_number"] = each.get("prodo_component_number", '')
            # 生产订单
            line["prodosn"] = each.get("prodosn", "")
            # 关联交货单
            line["rel_dn_sn"] = each.get("rel_dn_sn", "")
            # 关联交货单行号
            line["rel_dn_item"] = each.get("rel_dn_item", 0)
            # 拣配单号
            line["picking_document"] = each.get("picking_document", "")
            # 批次行号
            line["batch_item"] = each.get("batch_item", 0)
            # 关联预留单
            line["ro_sn"] = each.get("ro_sn", "")
            # 关联预留单行
            line["ro_items"] = each.get("ro_items", 0)
            # 关联销售订单
            line["rel_so_sn"] = each.get("rel_so_sn", "")
            # 关联销售订单行项目
            line["rel_so_items"] = each.get("rel_so_items", 0)
            # 关联单据种类 关联单据号 关联行号 原始单据类型 原始单据号 原始单据行号
            line = get_associated_order(md_header, line)
            # 客户编码
            line["customer_code"] = each.get("customer_code", "")
            # 销售订单
            line["so_sn"] = each.get("so_sn", "")
            # 销售订单行项目
            line["so_items"] = each.get("so_items", 0)
            # 库存调拨单
            line['inv_transfer_order_no'] = each.get("inv_transfer_order_no", '')
            # 库存调拨单行
            line['inv_transfer_order_items'] = each.get("inv_transfer_order_items", 0)
            # 项目编号
            line["project_sn"] = each.get("project_sn", "")
            # 供应商编码
            line["vendor_code"] = each.get("vendor_code", "")
            # 采购订单
            line["po_sn"] = each.get("po_sn", "")
            # 采购订单行项目
            line["po_items"] = each.get("po_items", 0)
            # WBS元素
            line["wbs_elements"] = each.get("wbs_elements", "")
            # 成本中心
            line["cost_center"] = each.get("cost_center", "")
            # 成本事项
            line["cost_business_object"] = each.get("cost_business_object", "")
            # 成本事项1
            line["cost_business_object1"] = each.get("cost_business_object1", "")
            # 利润中心
            line["profit_center"] = each.get("profit_center", "")
            # 会计科目
            line["accounting_subjects"] = each.get("accounting_subjects", "")
            # 资产卡片
            line["asset_code1"] = each.get("asset_code1", "")
            # 子资产
            line["asset_code2"] = each.get("asset_code2", "")
            # 设备ID
            line["equipment_code"] = each.get("equipment_code", "")
            # 快递单号
            line["express_delivery"] = each.get("express_delivery", "")
            # 行参考信息1
            line["reference1_item"] = each.get("reference1_item", "")
            # 行参考信息2
            line["reference2_item"] = each.get("reference2_item", "")
            # 行参考信息3
            line["reference3_item"] = each.get("reference3_item", "")
            # 汇总行
            line["summary_line"] = each.get("summary_line", 0)
            line["pod_related"] = each.get("pod_related", 0)

            # 批次编码校验
            if each.get("mat_code", "") != "":
                line["batch_sn"], each['batch_number'], msg = check_batch_required(line["mat_code"], line["plant_code"],
                                                                                   line["batch_sn"],
                                                                                   line["debit_credit_mark"],
                                                                                   dict_mat_code, dict_mat_batch,
                                                                                   each.get('batch_number', {}),
                                                                                   dict_movement_type[
                                                                                       line['movement_type']][0],
                                                                                       user_id=user_id)
                if msg != "":
                    error_list.append("行标识{}{}".format(each["line_id"], msg))

            # 交易前移动平均价（成本货币）/ 交易前移动平均价（本位币）
            # ---待补充

            # 质检过账标识 / 质量检验单标识
            line["quality_insp_post_mark"] = each.get("quality_insp_post_mark", 0)
            line["quality_insp_order_mark"], msg = get_quality_inspection_mark(line["mat_code"], line["plant_code"],
                                                                               line["inventory_status"],
                                                                               line["movement_type"],
                                                                               line["debit_credit_mark"],
                                                                               line["quality_insp_post_mark"],
                                                                               dict_mat_code, dict_movement_type,
                                                                               dict_mat_insp)
            if msg != "":
                error_list.append("行标识{}{}".format(each["line_id"], msg))

            # 结批标识
            line["batch_closure_flag"] = each.get("batch_closure_flag", 0)
            # 结批日期
            line["batch_closure_date"] = each.get("batch_closure_date", "")
            # 收货完成标记
            line["receipt_completed_flag"] = each.get("receipt_completed_flag", 0)

            # 移动原因
            line["movement_reason"] = each.get("movement_reason", "")

            # 参考凭证年度
            line["rel_document_year"] = each.get("rel_document_year", "")
            # 参考凭证号
            line["rel_document_no"] = each.get("rel_document_no", "")
            line["ref_document_mat"] = each.get("ref_document_mat", 0)
            # 前序物料凭证年度
            line["pre_document_year"] = each.get("pre_document_year", "")
            # 前序物料凭证
            line["pre_document_no"] = each.get("pre_document_no", "")
            # 前序物料凭证行号
            line["pre_document_item"] = each.get("pre_document_item", 0)

            # 预留字段
            line["reserved1"] = each.get("reserved1", "")
            line["reserved2"] = each.get("reserved2", "")
            line["reserved3"] = each.get("reserved3", "")
            line["reserved4"] = each.get("reserved4", "")
            line["reserved5"] = each.get("reserved5", "")
            line["reserved6"] = each.get("reserved6", "")
            line["reserved7"] = each.get("reserved7", "")
            line["reserved8"] = each.get("reserved8", "")
            line["reserved9"] = each.get("reserved9", "")
            line["reserved10"] = each.get("reserved10", "")

            # 批次属性
            # DJ 不需要传批次属性
            # batch_number = {}
            # line["batch_number"] = {}

            # batch_number["production_date"] = each["batch_number"].get("production_date", "")
            # batch_number["maturity_date"] = each["batch_number"].get("maturity_date", "")
            # batch_number["vendor_code"] = each["batch_number"].get("vendor_code", "")
            # batch_number["vendor_batch"] = each["batch_number"].get("vendor_batch", "")
            # batch_number["receive_date"] = each["batch_number"].get("receive_date", "")
            # batch_number["lot_no"] = each["batch_number"].get("lot_no", "")
            # batch_number["wafer_id"] = each["batch_number"].get("wafer_id", "")
            # batch_number["mfg_date_wafer"] = each["batch_number"].get("mfg_date_wafer", "")
            # batch_number["vendor_lot_no"] = each["batch_number"].get("vendor_lot_no", "")
            # batch_number["mfg_date_assy"] = each["batch_number"].get("mfg_date_assy", "")
            # batch_number["packing_seal_date"] = each["batch_number"].get("packing_seal_date", "")
            # batch_number["date_code"] = each["batch_number"].get("date_code", "")
            # batch_number["packing_id"] = each["batch_number"].get("packing_id", "")
            # batch_number["bin_grade"] = each["batch_number"].get("bin_grade", "")
            # batch_number["grade"] = each["batch_number"].get("grade", "")
            # batch_number["batch_type"] = each["batch_number"].get("batch_type", "")
            # batch_number["receive_data"] = each["batch_number"].get("receive_data", "")
            # batch_number["cp_vendor"] = each["batch_number"].get("cp_vendor", "")
            # batch_number["bin"] = each["batch_number"].get("bin", "")
            # batch_number["grade1"] = each["batch_number"].get("grade1", "")
            # batch_number["grade2"] = each["batch_number"].get("grade2", "")
            # batch_number["grade3"] = each["batch_number"].get("grade3", "")
            # batch_number["extended_batch_date1"] = each["batch_number"].get("extended_batch_date1", "")
            # batch_number["extended_batch_date2"] = each["batch_number"].get("extended_batch_date2", "")
            # batch_number["extended_batch_date3"] = each["batch_number"].get("extended_batch_date3", "")
            # batch_number["extended_batch_attributes1"] = each["batch_number"].get("extended_batch_attributes1", "")
            # batch_number["extended_batch_attributes2"] = each["batch_number"].get("extended_batch_attributes2", "")
            # batch_number["extended_batch_attributes3"] = each["batch_number"].get("extended_batch_attributes3", "")
            # batch_number["item"] = edit_batch_attribute(each["batch_number"].get("item", []))
            # batch_number["create_id"] = user_id
            # batch_number["update_id"] = user_id
            # line["batch_number"] = batch_number

            line["batch_number"] = each.get('batch_number', {})
            line["batch_number"]["create_id"] = user_id
            line["batch_number"]["update_id"] = user_id

            line["create_id"] = user_id
            line["update_id"] = user_id

            md_item.append(line.copy())
    if not error_list:
        # 库存校验
        inventory_begin = time.time()
        msg_list = get_inventory_qty(md_item, md_header["posting_date"], dict_plant_storage, db)
        print("库存校验耗时：", time.time() - inventory_begin)
        if msg_list:
            error_list.extend(msg_list)

    if error_list:
        code = 500
        msg = "存在错误,请检查"
    else:
        code = 200
        msg = "检查无误"

    return code, msg, error_list, md_header, md_item, md_price


def check_rel_dn_status(post_code, picking_document, batch_item, special_inventory_status2, dict_picking_document):
    # query_sql = """
    #     SELECT
    #         posting_status,
    #         pod_status,
    #         billing_status
    #     FROM
    #         t_dn_inventory_alloc
    #     WHERE
    #         picking_document = '{}'
    #     and batch_item = '{}'
    #     LIMIT 1
    # """.format(picking_document, batch_item)

    if dict_picking_document.get(picking_document + str(batch_item)):
        if post_code == '6':
            if special_inventory_status2 == "":
                if not (dict_picking_document[picking_document + str(batch_item)][0]["posting_status"] == "A"
                        and dict_picking_document[picking_document + str(batch_item)][0]["pod_status"] == "D"
                        and (dict_picking_document[picking_document + str(batch_item)][0]["billing_status"] == "A"
                             or dict_picking_document[picking_document + str(batch_item)][0]["billing_status"] == "D")):
                    return True
            if special_inventory_status2 == "T":
                if not (dict_picking_document[picking_document + str(batch_item)][0]["posting_status"] == "C"
                        and dict_picking_document[picking_document + str(batch_item)][0]["pod_status"] == "A"
                        and (dict_picking_document[picking_document + str(batch_item)][0]["billing_status"] == "A"
                             or dict_picking_document[picking_document + str(batch_item)][0]["billing_status"] == "D")):
                    return True
        if post_code == '4':
            if special_inventory_status2 == "T":
                if not (dict_picking_document[picking_document + str(batch_item)][0]["posting_status"] == "A"
                        and dict_picking_document[picking_document + str(batch_item)][0]["pod_status"] == "A"
                        and (dict_picking_document[picking_document + str(batch_item)][0]["billing_status"] == "A"
                             or dict_picking_document[picking_document + str(batch_item)][0]["billing_status"] == "D")):
                    return True
    return False


# 正式过账代码5
def post_data_postcode5(user_id, md_header, md_item, md_price, db):
    code = 0
    msg = ""
    mat_doc_sn = ""
    year = ""
    error_list = []

    try:
        mat_code = md_item[0]["mat_code"]
        batch_sn = md_item[0]["batch_sn"]
        lock_key = f"LOCK_{mat_code}_{batch_sn}"
    except:
        lock_key = f"LOCK_USER_{user_id}"

    try:
        # 加锁
        code, msg = lock_data(md_item, LockAction.lock, lock_key)
        if code != 200:
            error_list.append(msg)
            raise Exception(msg)

        # 调用会计引擎
        input = json.dumps([{"header": md_header, "items": md_item, "details": md_price}])
        print(input)
        sh = SystemHelper()

        c_begin = time.time()
        output = json.loads(sh.execOperator("OnConsumeMat", input)["data"])
        print("调用C耗时： ", time.time() - c_begin)
        print(output)

        if output["result"] == 0:
            if "data" in output:
                code = 200
                msg = "执行成功"
                if output["data"][0]["status"] == "E":
                    code = 500
                    msg = output["data"][0]["msg"]
                else:
                    mat_doc_sn = output["data"][0]["mat_doc_sn"]
                    year = output["data"][0]["year"]
                    msg = "过账成功,物料凭证:{} 年度{}".format(mat_doc_sn, year)
            else:
                code = 500
                msg = output.get("msg", "会计引擎异常")
        else:
            code = 500
            msg = output["msg"]

    except Exception as e:
        if not error_list:
            error_list.append(str(e))
        code = 500
        msg = "存在错误,请检查"

    finally:
        lock_data(md_item, LockAction.unlock, lock_key)

    return code, msg, error_list, mat_doc_sn, year


# 检查过账代码5的参数
def check_data_postcode5(user_id, head, item, db):
    code = 200
    msg = ""
    error_list = []

    # 增强 -- 检验前
    code, msg, error_list, head, item = before_check(user_id, head, item)
    if code != 200:
        return code, msg, error_list, [], [], []

    dict_movement_type = {}
    movement_type = []
    plant_code = []
    plant_code_data = []
    dict_plant_storage = {}
    movement_special_inventory_status1 = []
    movement_special_inventory_status2 = []
    mat_code = []
    dict_mat_code = {}
    dict_mat_code_cost = {}
    po_sn = []
    dict_po_header = {}
    dict_po_item = {}
    prodosn = []
    dict_prodosn_data = {}
    dn_sn = []
    dict_dn_sn_header = {}
    dict_dn_sn_item = {}
    picking_document = []
    dict_picking_document = {}
    procure_dn_sn = []
    dict_procure_dn_sn_data = {}
    ro_sn = []
    dict_ro_sn_data = {}
    so_sn = []
    dict_so_sn_data = {}
    customer_code = []
    dict_customer_code_data = {}
    vendor_code = []
    dict_vendor_code_data = {}
    cost_center = []
    dict_cost_center_data = []
    cost_business_object = []
    dict_cost_business_object_data = {}
    profit_center = []
    dict_profit_center_data = {}
    equipment_code = []
    dict_equipment_code_data = {}
    dict_company = {}
    dict_relation = {}
    dict_relation2 = {}
    dict_movement_label1 = {}
    dict_movement_label2 = {}
    dict_movement_label3 = {}
    dict_mat_batch = {}
    batch = []
    dict_mat_insp = {}
    dict_price_data = {}
    dict_inventory_status = {}
    inv_transfer_order_no = []
    dict_inv_transfer_order = {}
    dict_inv_transfer_order_item = {}

    # 性能优化
    for each in item:
        # 移动类型
        if each.get("movement_type", "") != "":
            movement_type.append(each['movement_type'])
        # 工厂
        if each.get("plant_code", "") != "":
            plant_code.append(each['plant_code'])

        # 物料编码
        if each.get("mat_code", "") != "":
            mat_code.append(each['mat_code'])

        # 采购订单
        if each.get("rel_po_sn", '') != '':
            po_sn.append(each['rel_po_sn'])
        if each.get('po_sn', '') != '':
            po_sn.append(each['po_sn'])

        # 生产订单
        if each.get('prodosn', '') != '':
            prodosn.append(each['prodosn'])

        # 交货单
        if each.get('rel_dn_sn', '') != '':
            dn_sn.append(each['rel_dn_sn'])

        # 拣配单
        if each.get('picking_document', '') != '':
            picking_document.append(each['picking_document'])

        # 采购交货单
        if each.get('rel_procure_dn_sn', '') != '':
            procure_dn_sn.append(each['rel_procure_dn_sn'])

        # 预留
        if each.get('ro_sn', '') != '':
            ro_sn.append(each['ro_sn'])

        # 销售订单
        if each.get('rel_so_sn', '') != '':
            so_sn.append(each['rel_so_sn'])
        if each.get('so_sn', '') != '':
            so_sn.append(each['so_sn'])

        # 客户
        if each.get('customer_code', '') != '':
            customer_code.append(each['customer_code'])

        # 供应商
        if each.get('vendor_code', '') != '':
            vendor_code.append(each['vendor_code'])

        # 成本中心
        if each.get('cost_center', '') != '':
            cost_center.append(each['cost_center'])

        # 成本事项
        if each.get('cost_business_object', '') != '':
            cost_business_object.append(each['cost_business_object'])
        if each.get('cost_business_object1', '') != '':
            cost_business_object.append(each['cost_business_object1'])

        # 利润中心
        if each.get('profit_center', '') != '':
            profit_center.append(each['profit_center'])

        # 设备
        if each.get('equipment_code', '') != '':
            equipment_code.append(each['equipment_code'])

        # 批次
        if each.get('batch_sn', '') != '':
            batch.append(each['batch_sn'])
        # 库存调拨单
        if each.get("inv_transfer_order_no", "") != '':
            inv_transfer_order_no.append(each['inv_transfer_order_no'])

    data_begin = time.time()

    # 获取移动类型属性
    dict_movement_type = get_movement_type_info(movement_type, db)
    # 获取工厂
    plant_code_data = get_plant_code_data(plant_code, db)
    # 获取工厂对应库存地点
    dict_plant_storage = get_plant_storage(plant_code, db)
    # 获取移动类型对应特殊库存状态
    movement_special_inventory_status1, movement_special_inventory_status2, dict_relation, dict_relation2 = get_movement_special_inventory_status(
        movement_type, db)
    # 获取物料主数据信息
    dict_mat_code = get_mat_code_info(mat_code, plant_code, db)
    # 获取物料成本视图
    dict_mat_code_cost = get_mat_code_cost_info(mat_code, plant_code, db)
    # 获取物料单位换算关系
    dict_mat_uom_convert = get_mat_uom_convert(mat_code, db)
    # 获取采购订单抬头信息
    dict_po_header = get_po_header(po_sn, db)
    # 获取采购订单行项目信息
    dict_po_item = get_po_item(po_sn, db)
    # 获取批次组件表
    dict_po_component = get_po_component(po_sn, db)
    # 获取采购订单批次绑定表
    dict_po_binding = get_po_batch_binding(po_sn, db)
    # 获取生产订单
    dict_prodosn_data = get_prodosn_data(prodosn, db)
    # 获取交货单抬头信息
    dict_dn_sn_header = get_dn_header(dn_sn, db)
    # 获取交货单行项目信息
    dict_dn_sn_item = get_dn_sn_item(dn_sn, db)
    # 获取拣配单信息
    dict_picking_document = get_picking_document_info(picking_document, db)
    # 获取采购交货单信息
    # dict_procure_dn_sn_data = get_procure_dn_sn_info(procure_dn_sn, db)
    # 获取预留单信息
    dict_ro_sn_data = get_ro_sn_info(ro_sn, db)
    # 获取销售订单信息
    dict_so_sn_data = get_so_sn_info(so_sn, db)
    # 获取客户信息
    dict_customer_code_data = get_customer_code_info(customer_code, db)
    # 获取供应商信息
    dict_vendor_code_data = get_vendor_code_info(vendor_code, db)
    # 获取成本中心
    dict_cost_center_data = get_cost_center_info(cost_center, db)
    # 获取成本事项
    dict_cost_business_object_data = get_cost_business_object_info(cost_business_object, db)
    # 利润中心
    dict_profit_center_data = get_profit_center_info(profit_center, db)
    # 获取设备主数据信息
    dict_equipment_code_data = get_equipment_code_info(equipment_code, db)
    # 按工厂获取公司信息
    dict_company = get_company_info_by_plant(plant_code, db)
    # 获取移动类型配置信息
    dict_movement_label1, dict_movement_label2, dict_movement_label3 = get_movement_label_info(movement_type, db)
    # 获取物料批次信息
    dict_mat_batch = get_mat_code_and_batch(mat_code, batch, db)
    # 获取物料质检信息
    dict_mat_insp = get_mat_insp_info(mat_code, plant_code, db)
    # 获取采购订单价格明细
    # dict_price_data = get_po_price_data(po_sn, db)
    # 获取库存状态
    dict_inventory_status = get_all_inventory_status(db)
    # 获取库存调拨单
    dict_inv_transfer_order = get_inv_transfer_order(inv_transfer_order_no, db)
    # 获取库存调拨单行
    dict_inv_transfer_order_item = get_inv_transfer_order_item(inv_transfer_order_no, db)

    print("取值耗时: ", time.time() - data_begin)
    for each in item:
        # 必输校验
        # 行唯一标识校验
        if each.get("line_id", "") == "":
            error_list.append("行唯一标识必输")
            continue
        # 移动类型校验
        if each.get("movement_type", "") == "":
            error_list.append("行标识{}移动类型必输".format(each["line_id"]))
        # 交易数量
        if Decimal(each.get("transaction_qty", 0)) <= 0:
            if dict_movement_type.get(each.get('movement_type', '')):
                if dict_movement_type[each['movement_type']][0]['allow_zero_base_qty'] == 0:
                    error_list.append("行标识{}交易数量必须大于0".format(each["line_id"]))
        # 交易单位
        if each.get("transaction_uom", "") == "":
            error_list.append("行标识{}交易单位必输".format(each["line_id"]))
        # # 基本数量
        # if each.get("basic_qty", 0) == 0:
        #     error_list.append("行标识{}基本数量必输".format(each["line_id"]))
        # # 基本单位
        # if each.get("basic_uom", "") == "":
        #     error_list.append("行标识{}基本单位必输".format(each["line_id"]))
        # # 平行单位
        # if each.get("parallel_uom", "") == "":
        #     error_list.append("行标识{}平行单位必输".format(each["line_id"]))
        # # 平行数量
        # if each.get("parallel_uom", "") == each.get("basic_uom", ""):
        #     each["parallel_qty"] = each["basic_qty"]
        # else:
        #     if each.get("basic_qty", 0) == 0:
        #         each["parallel_qty"] = 0
        #     else:
        #         if each.get("parallel_qty", 0) == 0:
        #             error_list.append("行标识{}平行数量必输".format(each["line_id"]))
        # if each.get("parallel_uom", "") != "":
        #     if each.get("parallel_qty", 0) == 0:
        #         if dict_movement_type.get(each.get('movement_type', '')):
        #             if dict_movement_type[each['movement_type']][0]['allow_zero_parallel_qty'] != 0:
        #                 error_list.append("行标识{}平行数量必输".format(each["line_id"]))
        # # 关联采购订单
        # if each.get("rel_po_sn", "") == "":
        #     error_list.append("行标识{}关联采购订单必输".format(each["line_id"]))
        # # 关联采购订单行号
        # if each.get("rel_po_items", "") == "":
        #     error_list.append("行标识{}关联采购订单行号必输".format(each["line_id"]))
        # 工厂代码
        if each.get("plant_code", "") == "":
            error_list.append("行标识{}工厂代码必输".format(each["line_id"]))
        # 库存地点
        if each.get("mat_code", "") != "" and each["special_inventory_status1"] != 'V':
            if each["stor_loc_code"] == "":
                error_list.append("行标识{}库存地点必输".format(each["line_id"]))

        # # 特殊库存状态1
        # if each["special_inventory_status1"] == "":
        #     error_list.append("行标识{}特殊库存状态1必输".format(each["line_id"]))
        # # 特殊库存状态1
        # if each["special_inventory_status1"] == "":
        #     error_list.append("行标识{}特殊库存状态1必输".format(each["line_id"]))
        # 库存状态
        if each.get("inventory_status", "") == "" and each.get("mat_code", "") != "":
            error_list.append("行标识{}库存状态必输".format(each["line_id"]))

        # 存在性校验
        if not error_list:
            # 移动类型校验
            if dict_movement_type.get(each["movement_type"]) is None:
                error_list.append("行标识{}移动类型{}不存在".format(each["line_id"], each["movement_type"]))
            else:
                if dict_movement_type[each['movement_type']][0]['post_code'] != head["post_code"]:
                    error_list.append("行标识{}移动类型{}不适用过账码{}".format(each["line_id"], each["movement_type"],
                                                                                head["post_code"]))
            # 工厂代码校验
            if each["plant_code"] not in plant_code_data:
                error_list.append("行标识{}工厂代码{}不存在".format(each["line_id"], each["plant_code"]))
            # 库存地点校验
            if each.get("stor_loc_code", "") != "":
                # if not check_if_stor_loc_code_exists(each["stor_loc_code"]):
                #     error_list.append("行标识{}库存地点{}不存在".format(each["line_id"], each["stor_loc_code"]))
                # else:
                if dict_plant_storage.get(each["plant_code"] + each["stor_loc_code"]) is None:
                    error_list.append(
                        "行标识{}在工厂{}下库存地点{}未分配".format(each["line_id"], each["plant_code"],
                                                                    each["stor_loc_code"]))
            # 特殊库存状态1校验
            if each.get("special_inventory_status1", "") != "":
                if each["movement_type"] + each["special_inventory_status1"] not in movement_special_inventory_status1:
                    error_list.append(
                        "行标识{}在移动类型{}下特殊库存标识1{}未分配".format(each["line_id"], each["movement_type"],
                                                                             each["special_inventory_status1"]))
            # 库存状态
            if each.get("inventory_status", "") != "":
                if dict_inventory_status.get(each["inventory_status"]) is None:
                    error_list.append("行标识{}库存状态{}不存在".format(each["line_id"], each["inventory_status"]))
            # 物料状态检查
            # 物料状态检查
            if each.get("mat_code", "") != "":
                key = each["mat_code"] + each["plant_code"]
                if dict_mat_code.get(key) is None:
                    error_list.append("行标识{}物料编码{}在工厂{}不存在".format(each["line_id"], each["mat_code"], each["plant_code"]))
                else:
                    mat_info = dict_mat_code[key][0]
                    if mat_info.get('deleted_mark', 0) == 1 or mat_info.get('lock_flag', 0) == 1:
                        error_list.append("行标识{}物料编码{}已删除或锁定".format(each["line_id"], each["mat_code"]))
                    elif mat_info.get('value_update', 0) == 1:
                        if dict_mat_code_cost.get(key) is None:
                            error_list.append("行标识{}物料编码{}成本视图未扩".format(each["line_id"], each["mat_code"]))
            # 采购订单状态检查
            if each.get("rel_po_sn", "") != "":
                msg = check_po_status(each["rel_po_sn"], dict_po_header)
                if msg != "":
                    error_list.append("行标识{}{}".format(each["line_id"], msg))
                else:
                    # 采购订单行检查
                    msg = check_po_item_status(head["post_code"], each["rel_po_sn"], each["rel_po_items"], dict_po_item)
                if msg != "":
                    error_list.append("行标识{}{}".format(each["line_id"], msg))
            if each.get("rel_po_component_number", 0) != 0:
                # 采购订单行的序号检查
                if check_if_po_component_exists(each["rel_po_sn"], each["rel_po_items"],
                                                each["rel_po_component_number"], dict_po_component):
                    error_list.append(
                        "行标识{}关联采购订单{}行{}项目序号{}不存在".format(each["line_id"], each["rel_po_sn"],
                                                                            each["rel_po_items"],
                                                                            each["rel_po_component_number"]))
            if each.get("rel_po_comp_batch_num", 0) != 0:
                # 采购订单库存绑定表检查
                if check_if_po_batch_binding_exists(each["rel_po_sn"], each["rel_po_items"],
                                                    each["rel_po_component_number"],
                                                    each["rel_po_comp_batch_num"], dict_po_binding):
                    error_list.append("行标识{}关联采购订单{}行{}项目序号{}绑定序号{}不存在".format(each["line_id"],
                                                                                                    each["rel_po_sn"],
                                                                                                    each[
                                                                                                        "rel_po_items"],
                                                                                                    each[
                                                                                                        "rel_po_component_number"],
                                                                                                    each[
                                                                                                        "rel_po_comp_batch_num"]))
            if each.get("prodosn", "") != "":
                # 生产订单检查
                if dict_prodosn_data.get(each["prodosn"]) is None:
                    error_list.append("行标识{}生产订单{}不存在".format(each["line_id"], each["prodosn"]))
            if each.get("rel_dn_sn", "") != "":
                # 关联交货单检查
                if dict_dn_sn_header.get(each["rel_dn_sn"]) is None:
                    error_list.append("行标识{}关联交货单{}不存在".format(each["line_id"], each["rel_dn_sn"]))
                elif dict_dn_sn_item.get(each["rel_dn_sn"] + str(each.get("rel_dn_item", 0))) is None:
                    error_list.append("行标识{}关联交货单{}行号{}不存在".format(each["line_id"], each["rel_dn_sn"],
                                                                                each.get("rel_dn_item", 0)))
            if each.get("picking_document", "") != "":
                # 拣配单号检查
                if dict_picking_document.get(each["picking_document"] + str(each.get("batch_item", 0))) is None:
                    error_list.append("行标识{}拣配单号{}不存在".format(each["line_id"], each["picking_document"]))
            if each.get("inv_transfer_order_no", "") != "":
                # 库存调拨单
                if dict_inv_transfer_order.get(each["inv_transfer_order_no"]) is None:
                    error_list.append(
                        "行标识{}库存调拨单{}不存在".format(each["line_id"], each["inv_transfer_order_no"]))
                elif dict_inv_transfer_order_item.get(
                        each["inv_transfer_order_no"] + str(each.get("inv_transfer_order_items", 0))) is None:
                    error_list.append(
                        "行标识{}库存调拨单{}行号{}不存在".format(each["line_id"], each["inv_transfer_order_no"],
                                                                  each.get("inv_transfer_order_items", 0)))
            if each.get("ro_sn", "") != "":

                if dict_ro_sn_data.get(each["ro_sn"] + str(each.get("ro_items", 0))) is None:
                    error_list.append("行标识{}关联预留单{}行号{}不存在".format(each["line_id"], each["ro_sn"],
                                                                                each.get("ro_items", 0)))
            if each.get("rel_so_sn", "") != "":

                if dict_so_sn_data.get(each["rel_so_sn"] + str(each.get("rel_so_items", 0))) is None:
                    error_list.append("行标识{}关联销售订单{}行号{}不存在".format(each["line_id"], each["rel_so_sn"],
                                                                                  each.get("rel_so_items", 0)))
            if each.get("special_inventory_status1", "") == "C" or each.get("special_inventory_status1", "") == "CC":
                # 客户检查
                if each.get("customer_code", "") == "":
                    error_list.append("行标识{}客户编码必输".format(each["line_id"]))
                else:
                    if dict_customer_code_data.get(each["customer_code"]) is None:
                        error_list.append("行标识{}客户编码{}不存在".format(each["line_id"], each["customer_code"]))
            else:
                each["customer_code"] = ""

            if each.get("special_inventory_status1", "") == "S":
                # 销售订单检查
                if each.get("so_sn", "") == "" or each.get("so_items", "") == "":
                    error_list.append("行标识{}销售订单信息必输".format(each["line_id"]))
                else:
                    if dict_so_sn_data.get(each.get("so_sn", "") + str(each.get("so_items", 0))) is None:
                        error_list.append("行标识{}销售订单{}行号{}不存在".format(each["line_id"], each["rel_so_sn"],
                                                                                  each.get("rel_so_items", 0)))
            else:
                each["so_sn"] = ""
                each["so_items"] = 0

            if each.get("special_inventory_status1", "") == "P":
                # 项目编码检查
                if each.get("project_sn", "") == "":
                    error_list.append("行标识{}项目编码必输".format(each["line_id"]))
                    # 项目编码检查待定-----
            else:
                each["project_sn"] = ""

            if each.get("special_inventory_status1", "") == "V" or each.get("special_inventory_status1", "") == "SC":
                # 供应商编码检查
                if each.get("vendor_code", "") == "":
                    error_list.append("行标识{}供应商编码必输".format(each["line_id"]))
                else:
                    if dict_vendor_code_data.get(each["vendor_code"]) is None:
                        error_list.append("行标识{}供应商编码{}不存在".format(each["line_id"], each["vendor_code"]))

                if each["special_inventory_status1"] == "V":
                    if each.get("po_sn", "") != "":
                        # 采购订单检查
                        if dict_po_header.get(each["po_sn"]) is None:
                            error_list.append("行标识{}采购订单{}不存在".format(each["line_id"], each["po_sn"]))
                        else:
                            if dict_po_item.get(each["po_sn"] + str(each.get("po_items", 0))) is None:
                                error_list.append(
                                    "行标识{}采购订单{}行号{}不存在".format(each["line_id"], each["po_sn"],
                                                                            each.get("po_items", 0)))
                else:
                    each["po_sn"] = ""
                    each["po_items"] = 0
            else:
                each["vendor_code"] = ""
                each["po_sn"] = ""
                each["po_items"] = 0

            if each.get("cost_center", "") != "":
                # 成本中心检查
                if dict_cost_center_data.get(each["cost_center"] + each["plant_code"]) is None:
                    error_list.append(
                        "行标识{}成本中心{}在工厂{}对应的公司代码不存在".format(each["line_id"], each["cost_center"],
                                                                                each["plant_code"]))
            if each.get("cost_business_object", "") != "":
                # 成本事项检查
                if dict_cost_business_object_data.get(each["cost_business_object"] + each["plant_code"]) is None:
                    error_list.append(
                        "行标识{}成本事项{}在工厂{}对应的公司代码不存在".format(each["line_id"],
                                                                                each["cost_business_object"],
                                                                                each["plant_code"]))
            if each.get("cost_business_object1", "") != "":
                # 成本事项1检查
                if dict_cost_business_object_data.get(each["cost_business_object1"] + each["plant_code"]) is None:
                    error_list.append(
                        "行标识{}成本事项1{}在工厂{}对应的公司代码不存在".format(each["line_id"],
                                                                                 each["cost_business_object1"],
                                                                                 each["plant_code"]))
            if each.get("profit_center", "") != "":
                # 利润中心检查
                if dict_profit_center_data.get(each["profit_center"] + each["plant_code"]) is None:
                    error_list.append(
                        "行标识{}利润中心{}在工厂{}对应的公司代码不存在".format(each["line_id"], each["profit_center"],
                                                                                each["plant_code"]))
            if each.get("equipment_code", "") != "":
                # 设备ID检查
                if dict_equipment_code_data.get(each["equipment_code"]) is None:
                    error_list.append("行标识{}设备ID{}不存在".format(each["line_id"], each["equipment_code"]))

            if each.get("transaction_currency", "") == "":
                each["transaction_currency"] = get_company_basic_currency(each['plant_code'], dict_company)

    md_header = initialization("t_md_header", db)
    md_item = []
    md_price = []

    # 生成凭证数据
    if not error_list:
        # 单据种类
        md_header["document_category"] = "MDOC"
        # 物料凭证
        md_header["mat_doc_sn"] = ""
        # 年度
        md_header["year"] = head["posting_date"][:4]
        # 过账代码
        md_header["post_code"] = head["post_code"]
        # 凭证日期
        md_header["document_date"] = head["document_date"]
        # 过账日期
        md_header["posting_date"] = head["posting_date"]

        # 汇总唯一号
        md_header["summary_unique_number"] = head.get("summary_unique_number", "")
        # 备注信息1
        md_header["remarks_1"] = head.get("remarks_1", "")
        # 备注信息2
        md_header["remarks_2"] = head.get("remarks_2", "")
        # 供应商交货单
        md_header["vendor_dn"] = head.get("vendor_dn", "")
        # 物料凭证类型
        md_header["material_document_type"] = ""
        # 交易汇率 公司代码 信息
        md_header["company_code"], md_header["exchange_rate"] = get_company_info(item[0]["plant_code"],
                                                                                 item[0]["transaction_currency"],
                                                                                 dict_company)

        if head.get('exchange_rate', 0) != 0:
            md_header["exchange_rate"] = head['exchange_rate']

        # 预留字段
        md_header["reserved1"] = head.get("reserved1", "")
        md_header["reserved2"] = head.get("reserved2", "")
        md_header["reserved3"] = head.get("reserved3", "")
        md_header["reserved4"] = head.get("reserved4", "")
        md_header["reserved5"] = head.get("reserved5", "")
        md_header["reserved6"] = head.get("reserved6", "")
        md_header["reserved7"] = head.get("reserved7", "")
        md_header["reserved8"] = head.get("reserved8", "")
        md_header["reserved9"] = head.get("reserved9", "")
        md_header["reserved10"] = head.get("reserved10", "")

        md_header["create_id"] = user_id
        md_header["update_id"] = user_id

        md_header["ztype"] = head.get('ztype', '')

        if md_header["exchange_rate"] == 0:
            error_list.append("未获取到汇率")

        line_tmp = initialization("t_md_item", db)

        item_no = 0
        # 行项目设置
        for each in item:

            line = line_tmp.copy()

            item_no += 1
            # 物料凭证
            line["mat_doc_sn"] = md_header["mat_doc_sn"]
            # 年度
            line["year"] = md_header["year"]
            # 物料凭证信息行号
            line["mat_doc_items"] = item_no
            # 物料凭证行唯一标识
            line["line_id"] = each["line_id"]
            # 凭证行参考唯一标识
            line["parent_id"] = each.get("parent_id", 0)
            # 参考凭证行
            line["ref_item_serial_no"] = 0
            # 自动创建标识
            line["auto_mark"] = 0
            # 移动类型
            line["movement_type"] = each["movement_type"]
            # 物料凭证类型 借贷标识  收发标识  科目修改 业务单据种类
            line, material_document_type, prod_order_mark, wbs_elements_mark, cost_business_object_mark, asset_code1_mark = get_movement_attribute(
                line, line["movement_type"], dict_movement_type)
            if md_header["material_document_type"] == "":
                md_header["material_document_type"] = material_document_type
            if line["debit_credit_mark"] == "":
                error_list.append(
                    "行标识{}未能根据移动类型{}取到借贷标识".format(each["line_id"], each["movement_type"]))
            if line["receipt_consume_mark"] == "":
                error_list.append(
                    "行标识{}未能根据移动类型{}取到收发标识".format(each["line_id"], each["movement_type"]))
            if prod_order_mark == 1:
                if each.get("prodosn", "") == "":
                    error_list.append("行标识{}生产订单必填".format(each["line_id"]))
            if wbs_elements_mark == 1:
                if each.get("wbs_elements", "") == "":
                    error_list.append("行标识{}WBS必填".format(each["line_id"]))
            if cost_business_object_mark == 1:
                if each.get("cost_center", "") == "" and each.get("cost_business_object", "") == "" and each.get(
                        "cost_business_object1", "") == "":
                    error_list.append("行标识{}成本中心/成本事项/成本事项1必填一个".format(each["line_id"]))
            if asset_code1_mark == 1:
                if each.get("asset_code1", "") == "":
                    error_list.append("行标识{}资产卡片必填".format(each["line_id"]))
            # 特殊库存状态1
            line["special_inventory_status1"] = each.get("special_inventory_status1", "")
            # 特殊库存状态2
            line["special_inventory_status2"] = each.get("special_inventory_status2", "")
            # 库存状态
            line["inventory_status"] = get_inventory_status(each["movement_type"], each.get("inventory_status", ""),
                                                            dict_movement_type)
            # 事件类型 物料成本特殊评估标识
            line["transaction_type_code"], line["mat_special_val_mark"] = get_transaction_type_code(
                each["movement_type"], each["plant_code"], each["mat_code"], each.get("rel_po_sn", ""),
                each.get("rel_po_items", 0),
                line["special_inventory_status1"], line["special_inventory_status2"], dict_relation, dict_po_item,
                dict_mat_code)
            if line["transaction_type_code"] == "":
                error_list.append("行标识{}未能根据移动类型{}和采购订单{}信息取到事件类型".format(each["line_id"],
                                                                                                  each["movement_type"],
                                                                                                  each.get("rel_po_sn",
                                                                                                           "")))
            # 工厂代码
            line["plant_code"] = each["plant_code"]
            # 公司代码
            line["company_code"] = md_header["company_code"]
            # 结算公司代码
            line["settle_company_code"] = get_settle_company_code(each["plant_code"], dict_company)
            # 物料编码
            line["mat_code"] = each.get("mat_code", "")
            # 库存地点
            if line["mat_code"] == "" or line["special_inventory_status1"] == "V":
                line["stor_loc_code"] = ""
            else:
                line["stor_loc_code"] = each.get("stor_loc_code", "")
            # 批次号
            line["batch_sn"] = each.get("batch_sn", "")
            # 交易数量
            line["transaction_qty"] = each["transaction_qty"]
            # 交易单位
            line["transaction_uom"] = each["transaction_uom"]
            # 带借贷标识的交易数量
            if line["debit_credit_mark"] == "Cr":
                line["transaction_qty_dc_mark"] = line["transaction_qty"] * -1
            else:
                line["transaction_qty_dc_mark"] = line["transaction_qty"]

            # 基本单位/成本单位/价格控制/评估类/物料组
            line = get_material_uom(line["mat_code"], line["plant_code"], dict_mat_code, line)

            # # 平行数量
            # line["parallel_qty"] = each["parallel_qty"]
            # 平行单位
            line["parallel_uom"] = each.get("parallel_uom", "")

            # 计算基本数量和成本数量
            line = get_other_qty_by_unit(each, line, head['post_code'],
                                         dict_movement_type[each['movement_type']][0]['allow_zero_base_qty'],
                                         dict_movement_type[each['movement_type']][0]['allow_zero_parallel_qty'],
                                         dict_mat_uom_convert)

            if dict_movement_type[each['movement_type']][0]['allow_zero_base_qty'] == 0:
                if line["basic_qty"] <= 0:
                    error_list.append("行标识{}基本数量不能为0".format(each["line_id"]))

            if dict_movement_type[each['movement_type']][0]['allow_zero_parallel_qty'] == 0:
                if line["parallel_qty"] <= 0 and line["parallel_uom"]:
                    error_list.append("行标识{}平行数量不能为0".format(each["line_id"]))

            # 带借贷标识的基本数量
            if line["debit_credit_mark"] == "Cr":
                line["basic_qty_dc_mark"] = line["basic_qty"] * -1
            else:
                line["basic_qty_dc_mark"] = line["basic_qty"]

            # 带借贷标识的成本数量
            if line["debit_credit_mark"] == "Cr":
                line["cost_qty_dc_mark"] = line["cost_qty"] * -1
            else:
                line["cost_qty_dc_mark"] = line["cost_qty"]

            # 带借贷标识的平行数量
            if line["debit_credit_mark"] == "Cr":
                line["parallel_qty_dc_mark"] = line["parallel_qty"] * -1
            else:
                line["parallel_qty_dc_mark"] = line["parallel_qty"]
            # 定价单位 定价单位数量 交易金额 交易货币 采购订单供应商
            line = get_po_qty_amount_info(line, each.get("rel_po_sn", ""), each.get("rel_po_items", 0), dict_po_header,
                                          dict_po_item)
            if not each.get("rel_po_sn"):
                # 交易金额
                line["transaction_amount"] = each.get("transaction_amount", 0)
            # 交易货币
            if each.get("transaction_currency", "") == "":
                line["transaction_currency"] = get_company_basic_currency(line["plant_code"], dict_company)
            else:
                line["transaction_currency"] = each["transaction_currency"]
            # 消耗记账 对象标识 价值更新 数量更新
            line = get_movement_label(line, each.get("rel_po_sn", ""), each.get("rel_po_items", 0), dict_movement_type,
                                      dict_mat_code,
                                      dict_po_item, dict_movement_label1, dict_movement_label2, dict_movement_label3)
            if line["consumption_posting_label"] == "":
                error_list.append("行标识{}消耗记账标识不能为空".format(each["line_id"]))
            if line["item_indicator"] == "":
                error_list.append("行标识{}对象标识不能为空".format(each["line_id"]))
            if line["value_update"] == "":
                error_list.append("行标识{}价值更新不能为空".format(each["line_id"]))
            # 关联采购订单
            line["rel_po_sn"] = each.get("rel_po_sn", "")
            # 关联采购订单行
            line["rel_po_items"] = each.get("rel_po_items", 0)
            # 关联采购订单行项目序号
            line["rel_po_component_number"] = each.get("rel_po_component_number", 0)
            # 关联采购订单行序号
            line["rel_po_comp_batch_num"] = each.get("rel_po_comp_batch_num", 0)
            # 关联生产订单组件序号
            line["prodo_component_number"] = each.get("prodo_component_number", '')
            # 生产订单
            line["prodosn"] = each.get("prodosn", "")
            # 关联交货单
            line["rel_dn_sn"] = each.get("rel_dn_sn", "")
            # 关联交货单行号
            line["rel_dn_item"] = each.get("rel_dn_item", 0)
            # 拣配单号
            line["picking_document"] = each.get("picking_document", "")
            # 批次行号
            line["batch_item"] = each.get("batch_item", 0)
            # 关联预留单
            line["ro_sn"] = each.get("ro_sn", "")
            # 关联预留单行
            line["ro_items"] = each.get("ro_items", 0)
            # 关联销售订单
            line["rel_so_sn"] = each.get("rel_so_sn", "")
            # 关联销售订单行项目
            line["rel_so_items"] = each.get("rel_so_items", 0)
            # 关联单据种类 关联单据号 关联行号 原始单据类型 原始单据号 原始单据行号
            line = get_associated_order(md_header, line)
            # 客户编码
            line["customer_code"] = each.get("customer_code", "")
            # 销售订单
            line["so_sn"] = each.get("so_sn", "")
            # 销售订单行项目
            line["so_items"] = each.get("so_items", 0)
            # 库存调拨单
            line['inv_transfer_order_no'] = each.get("inv_transfer_order_no", '')
            # 库存调拨单行
            line['inv_transfer_order_items'] = each.get("inv_transfer_order_items", 0)
            # 项目编号
            line["project_sn"] = each.get("project_sn", "")
            # 供应商编码
            line["vendor_code"] = each.get("vendor_code", "")
            # 采购订单
            line["po_sn"] = each.get("po_sn", "")
            # 采购订单行项目
            line["po_items"] = each.get("po_items", 0)
            # WBS元素
            line["wbs_elements"] = each.get("wbs_elements", "")
            # 成本中心
            line["cost_center"] = each.get("cost_center", "")
            # 成本事项
            line["cost_business_object"] = each.get("cost_business_object", "")
            # 成本事项1
            line["cost_business_object1"] = each.get("cost_business_object1", "")
            # 利润中心
            line["profit_center"] = each.get("profit_center", "")
            # 会计科目
            line["accounting_subjects"] = each.get("accounting_subjects", "")
            # 资产卡片
            line["asset_code1"] = each.get("asset_code1", "")
            # 子资产
            line["asset_code2"] = each.get("asset_code2", "")
            # 设备ID
            line["equipment_code"] = each.get("equipment_code", "")
            # 快递单号
            line["express_delivery"] = each.get("express_delivery", "")
            # 行参考信息1
            line["reference1_item"] = each.get("reference1_item", "")
            # 行参考信息2
            line["reference2_item"] = each.get("reference2_item", "")
            # 行参考信息3
            line["reference3_item"] = each.get("reference3_item", "")
            # 汇总行
            line["summary_line"] = each.get("summary_line", 0)
            # 批次编码校验
            if each.get("mat_code", "") != "":
                line["batch_sn"], each['batch_number'], msg = check_batch_required(line["mat_code"], line["plant_code"],
                                                                                   line["batch_sn"],
                                                                                   line["debit_credit_mark"],
                                                                                   dict_mat_code, dict_mat_batch,
                                                                                   each.get('batch_number', {}),
                                                                                   dict_movement_type[
                                                                                       line['movement_type']][0],
                                                                                       user_id=user_id)
                if msg != "":
                    error_list.append("行标识{}{}".format(each["line_id"], msg))

            # 交易前移动平均价（成本货币）/ 交易前移动平均价（本位币）
            # ---待补充

            # 质检过账标识 / 质量检验单标识
            line["quality_insp_post_mark"] = each.get("quality_insp_post_mark", 0)
            line["quality_insp_order_mark"], msg = get_quality_inspection_mark(line["mat_code"], line["plant_code"],
                                                                               line["inventory_status"],
                                                                               line["movement_type"],
                                                                               line["debit_credit_mark"],
                                                                               line["quality_insp_post_mark"],
                                                                               dict_mat_code, dict_movement_type,
                                                                               dict_mat_insp)
            if msg != "":
                error_list.append("行标识{}{}".format(each["line_id"], msg))

            # 结批标识
            line["batch_closure_flag"] = each.get("batch_closure_flag", 0)
            # 结批日期
            line["batch_closure_date"] = each.get("batch_closure_date", "")
            # 收货完成标记
            line["receipt_completed_flag"] = each.get("receipt_completed_flag", 0)

            # 移动原因
            line["movement_reason"] = each.get("movement_reason", "")

            # 参考凭证年度
            line["rel_document_year"] = each.get("rel_document_year", "")
            # 参考凭证号
            line["rel_document_no"] = each.get("rel_document_no", "")
            # 参考凭证行号
            line["ref_document_mat"] = each.get("ref_document_mat", 0)
            # 前序物料凭证年度
            line["pre_document_year"] = each.get("pre_document_year", "")
            # 前序物料凭证
            line["pre_document_no"] = each.get("pre_document_no", "")
            # 前序物料凭证行号
            line["pre_document_item"] = each.get("pre_document_item", 0)

            # 预留字段
            line["reserved1"] = each.get("reserved1", "")
            line["reserved2"] = each.get("reserved2", "")
            line["reserved3"] = each.get("reserved3", "")
            line["reserved4"] = each.get("reserved4", "")
            line["reserved5"] = each.get("reserved5", "")
            line["reserved6"] = each.get("reserved6", "")
            line["reserved7"] = each.get("reserved7", "")
            line["reserved8"] = each.get("reserved8", "")
            line["reserved9"] = each.get("reserved9", "")
            line["reserved10"] = each.get("reserved10", "")

            # 批次属性
            # batch_number = {}
            # line["batch_number"] = {}
            #
            # batch_number["production_date"] = each["batch_number"].get("production_date", "")
            # batch_number["maturity_date"] = each["batch_number"].get("maturity_date", "")
            # batch_number["vendor_code"] = each["batch_number"].get("vendor_code", "")
            # batch_number["vendor_batch"] = each["batch_number"].get("vendor_batch", "")
            # batch_number["receive_date"] = each["batch_number"].get("receive_date", "")
            # batch_number["lot_no"] = each["batch_number"].get("lot_no", "")
            # batch_number["wafer_id"] = each["batch_number"].get("wafer_id", "")
            # batch_number["mfg_date_wafer"] = each["batch_number"].get("mfg_date_wafer", "")
            # batch_number["vendor_lot_no"] = each["batch_number"].get("vendor_lot_no", "")
            # batch_number["mfg_date_assy"] = each["batch_number"].get("mfg_date_assy", "")
            # batch_number["packing_seal_date"] = each["batch_number"].get("packing_seal_date", "")
            # batch_number["date_code"] = each["batch_number"].get("date_code", "")
            # batch_number["packing_id"] = each["batch_number"].get("packing_id", "")
            # batch_number["bin_grade"] = each["batch_number"].get("bin_grade", "")
            # batch_number["grade"] = each["batch_number"].get("grade", "")
            # batch_number["batch_type"] = each["batch_number"].get("batch_type", "")
            # batch_number["receive_data"] = each["batch_number"].get("receive_data", "")
            # batch_number["cp_vendor"] = each["batch_number"].get("cp_vendor", "")
            # batch_number["bin"] = each["batch_number"].get("bin", "")
            # batch_number["grade1"] = each["batch_number"].get("grade1", "")
            # batch_number["grade2"] = each["batch_number"].get("grade2", "")
            # batch_number["grade3"] = each["batch_number"].get("grade3", "")
            # batch_number["extended_batch_date1"] = each["batch_number"].get("extended_batch_date1", "")
            # batch_number["extended_batch_date2"] = each["batch_number"].get("extended_batch_date2", "")
            # batch_number["extended_batch_date3"] = each["batch_number"].get("extended_batch_date3", "")
            # batch_number["extended_batch_attributes1"] = each["batch_number"].get("extended_batch_attributes1", "")
            # batch_number["extended_batch_attributes2"] = each["batch_number"].get("extended_batch_attributes2", "")
            # batch_number["extended_batch_attributes3"] = each["batch_number"].get("extended_batch_attributes3", "")
            # batch_number["item"] = edit_batch_attribute(each["batch_number"].get("item", []))
            # batch_number["create_id"] = user_id
            # batch_number["update_id"] = user_id
            # line["batch_number"] = batch_number

            line["batch_number"] = each.get('batch_number', {})
            line["batch_number"]["create_id"] = user_id
            line["batch_number"]["update_id"] = user_id

            line["create_id"] = user_id
            line["update_id"] = user_id

            md_item.append(line.copy())

    if not error_list:
        # 库存校验
        msg_list = get_inventory_qty(md_item, md_header["posting_date"], dict_plant_storage, db)
        if msg_list:
            error_list.extend(msg_list)

    if error_list:
        code = 500
        msg = "存在错误,请检查"
    else:
        code = 200
        msg = "检查无误"

    return code, msg, error_list, md_header, md_item, md_price


# 正式过账代码3
def post_data_postcode3(user_id, md_header, md_item, md_price, db):
    code = 0
    msg = ""
    mat_doc_sn = ""
    year = ""
    error_list = []

    try:
        mat_code = md_item[0]["mat_code"]
        batch_sn = md_item[0]["batch_sn"]
        lock_key = f"LOCK_{mat_code}_{batch_sn}"
    except:
        lock_key = f"LOCK_USER_{user_id}"

    try:
        # 加锁
        code, msg = lock_data(md_item, LockAction.lock, lock_key)
        if code != 200:
            error_list.append(msg)
            raise Exception(msg)

        # 调用会计引擎
        input = json.dumps([{"header": md_header, "items": md_item, "details": md_price}])
        print(input)
        sh = SystemHelper()

        c_begin = time.time()
        output = json.loads(sh.execOperator("OnConsumeMat", input)["data"])
        print("调用C耗时： ", time.time() - c_begin)
        print(output)

        if output["result"] == 0:
            if "data" in output:
                code = 200
                msg = "执行成功"
                if output["data"][0]["status"] == "E":
                    code = 500
                    msg = output["data"][0]["msg"]
                else:
                    mat_doc_sn = output["data"][0]["mat_doc_sn"]
                    year = output["data"][0]["year"]
                    msg = "过账成功,物料凭证:{} 年度{}".format(mat_doc_sn, year)
            else:
                code = 500
                msg = output.get("msg", "会计引擎异常")
        else:
            code = 500
            msg = output["msg"]

    except Exception as e:
        if not error_list:
            error_list.append(str(e))
        code = 500
        msg = "存在错误,请检查"

    finally:
        lock_data(md_item, LockAction.unlock, lock_key)

    return code, msg, error_list, mat_doc_sn, year

# 检查过账代码3的参数
def check_data_postcode3(user_id, head, item, db):
    code = 200
    msg = ""
    error_list = []

    # 增强 -- 检验前
    code, msg, error_list, head, item = before_check(user_id, head, item)
    if code != 200:
        return code, msg, error_list, [], [], []

    dict_movement_type = {}
    movement_type = []
    plant_code = []
    plant_code_data = []
    dict_plant_storage = {}
    movement_special_inventory_status1 = []
    movement_special_inventory_status2 = []
    mat_code = []
    dict_mat_code = {}
    dict_mat_code_cost = {}
    po_sn = []
    dict_po_header = {}
    dict_po_item = {}
    prodosn = []
    dict_prodosn_data = {}
    dict_prodosn_component_data = {}
    dn_sn = []
    dict_dn_sn_header = {}
    dict_dn_sn_item = {}
    picking_document = []
    dict_picking_document = {}
    procure_dn_sn = []
    dict_procure_dn_sn_data = {}
    ro_sn = []
    dict_ro_sn_data = {}
    so_sn = []
    dict_so_sn_data = {}
    customer_code = []
    dict_customer_code_data = {}
    vendor_code = []
    dict_vendor_code_data = {}
    cost_center = []
    dict_cost_center_data = {}
    cost_business_object = []
    dict_cost_business_object_data = {}
    profit_center = []
    dict_profit_center_data = {}
    equipment_code = []
    dict_equipment_code_data = {}
    dict_company = {}
    dict_relation = {}
    dict_relation2 = {}
    dict_movement_label1 = {}
    dict_movement_label2 = {}
    dict_movement_label3 = {}
    dict_mat_batch = {}
    batch = []
    dict_mat_insp = {}
    dict_price_data = {}
    dict_inventory_status = {}
    inv_transfer_order_no = []
    dict_inv_transfer_order = {}
    dict_inv_transfer_order_item = {}

    # 性能优化
    for each in item:
        # 移动类型
        if each.get("movement_type", "") != "":
            movement_type.append(each['movement_type'])
        # 工厂
        if each.get("plant_code", "") != "":
            plant_code.append(each['plant_code'])

        # 物料编码
        if each.get("mat_code", "") != "":
            mat_code.append(each['mat_code'])

        # 采购订单
        if each.get("rel_po_sn", '') != '':
            po_sn.append(each['rel_po_sn'])
        if each.get('po_sn', '') != '':
            po_sn.append(each['po_sn'])

        # 生产订单
        if each.get('prodosn', '') != '':
            prodosn.append(each['prodosn'])

        # 交货单
        if each.get('rel_dn_sn', '') != '':
            dn_sn.append(each['rel_dn_sn'])

        # 拣配单
        if each.get('picking_document', '') != '':
            picking_document.append(each['picking_document'])

        # 采购交货单
        if each.get('rel_procure_dn_sn', '') != '':
            procure_dn_sn.append(each['rel_procure_dn_sn'])

        # 预留
        if each.get('ro_sn', '') != '':
            ro_sn.append(each['ro_sn'])

        # 销售订单
        if each.get('rel_so_sn', '') != '':
            so_sn.append(each['rel_so_sn'])
        if each.get('so_sn', '') != '':
            so_sn.append(each['so_sn'])

        # 客户
        if each.get('customer_code', '') != '':
            customer_code.append(each['customer_code'])

        # 供应商
        if each.get('vendor_code', '') != '':
            vendor_code.append(each['vendor_code'])

        # 成本中心
        if each.get('cost_center', '') != '':
            cost_center.append(each['cost_center'])

        # 成本事项
        if each.get('cost_business_object', '') != '':
            cost_business_object.append(each['cost_business_object'])
        if each.get('cost_business_object1', '') != '':
            cost_business_object.append(each['cost_business_object1'])

        # 利润中心
        if each.get('profit_center', '') != '':
            profit_center.append(each['profit_center'])

        # 设备
        if each.get('equipment_code', '') != '':
            equipment_code.append(each['equipment_code'])

        # 批次
        if each.get('batch_sn', '') != '':
            batch.append(each['batch_sn'])
        # 库存调拨单
        if each.get("inv_transfer_order_no", "") != '':
            inv_transfer_order_no.append(each['inv_transfer_order_no'])

    data_begin = time.time()

    # 获取移动类型属性
    dict_movement_type = get_movement_type_info(movement_type, db)
    # 获取工厂
    plant_code_data = get_plant_code_data(plant_code, db)
    # 获取工厂对应库存地点
    dict_plant_storage = get_plant_storage(plant_code, db)
    # 获取移动类型对应特殊库存状态
    movement_special_inventory_status1, movement_special_inventory_status2, dict_relation, dict_relation2 = get_movement_special_inventory_status(
        movement_type, db)
    # 获取物料主数据信息
    dict_mat_code = get_mat_code_info(mat_code, plant_code, db)
    # 获取物料成本视图
    dict_mat_code_cost = get_mat_code_cost_info(mat_code, plant_code, db)
    # 获取物料单位换算关系
    dict_mat_uom_convert = get_mat_uom_convert(mat_code, db)
    # 获取采购订单抬头信息
    dict_po_header = get_po_header(po_sn, db)
    # 获取采购订单行项目信息
    dict_po_item = get_po_item(po_sn, db)
    # 获取批次组件表
    dict_po_component = get_po_component(po_sn, db)
    # 获取采购订单批次绑定表
    dict_po_binding = get_po_batch_binding(po_sn, db)
    # 获取生产订单
    dict_prodosn_data = get_prodosn_data(prodosn, db)
    # 获取生产订单组件信息
    dict_prodosn_component_data = get_prodosn_component_data(prodosn, db)
    # 获取交货单抬头信息
    dict_dn_sn_header = get_dn_header(dn_sn, db)
    # 获取交货单行项目信息
    dict_dn_sn_item = get_dn_sn_item(dn_sn, db)
    # 获取拣配单信息
    dict_picking_document = get_picking_document_info(picking_document, db)
    # 获取采购交货单信息
    # dict_procure_dn_sn_data = get_procure_dn_sn_info(procure_dn_sn, db)
    # 获取预留单信息
    dict_ro_sn_data = get_ro_sn_info(ro_sn, db)
    # 获取销售订单信息
    dict_so_sn_data = get_so_sn_info(so_sn, db)
    # 获取客户信息
    dict_customer_code_data = get_customer_code_info(customer_code, db)
    # 获取供应商信息
    dict_vendor_code_data = get_vendor_code_info(vendor_code, db)
    # 获取成本中心
    dict_cost_center_data = get_cost_center_info(cost_center, db)
    # 获取成本事项
    dict_cost_business_object_data = get_cost_business_object_info(cost_business_object, db)
    # 利润中心
    dict_profit_center_data = get_profit_center_info(profit_center, db)
    # 获取设备主数据信息
    dict_equipment_code_data = get_equipment_code_info(equipment_code, db)
    # 按工厂获取公司信息
    dict_company = get_company_info_by_plant(plant_code, db)
    # 获取移动类型配置信息
    dict_movement_label1, dict_movement_label2, dict_movement_label3 = get_movement_label_info(movement_type, db)
    # 获取物料批次信息
    dict_mat_batch = get_mat_code_and_batch(mat_code, batch, db)
    # 获取物料质检信息
    dict_mat_insp = get_mat_insp_info(mat_code, plant_code, db)
    # 获取采购订单价格明细
    dict_price_data = get_po_price_data(po_sn, db)
    # 获取库存状态
    dict_inventory_status = get_all_inventory_status(db)
    # 获取库存调拨单
    dict_inv_transfer_order = get_inv_transfer_order(inv_transfer_order_no, db)
    # 获取库存调拨单行
    dict_inv_transfer_order_item = get_inv_transfer_order_item(inv_transfer_order_no, db)

    print("取值耗时: ", time.time() - data_begin)
    for each in item:
        # 必输校验
        # 行唯一标识校验
        if each.get("line_id", "") == "":
            error_list.append("行唯一标识必输")
            continue
        # 移动类型校验
        if each.get("movement_type", "") == "":
            error_list.append("行标识{}移动类型必输".format(each["line_id"]))
        # 交易数量
        if Decimal(each.get("transaction_qty", 0)) <= 0:
            if dict_movement_type.get(each.get('movement_type', '')):
                if dict_movement_type[each['movement_type']][0]['allow_zero_base_qty'] == 0:
                    error_list.append("行标识{}交易数量必须大于0".format(each["line_id"]))
        # 交易单位
        if each.get("transaction_uom", "") == "":
            error_list.append("行标识{}交易单位必输".format(each["line_id"]))

        # 工厂代码
        if each.get("plant_code", "") == "":
            error_list.append("行标识{}工厂代码必输".format(each["line_id"]))

        # 库存状态
        if each.get("inventory_status", "") == "" and each.get("mat_code", "") != "":
            error_list.append("行标识{}库存状态必输".format(each["line_id"]))
        # 库存地点
        if each.get("mat_code", "") != "" and each["special_inventory_status1"] != 'V':
            if each["stor_loc_code"] == "":
                error_list.append("行标识{}库存地点必输".format(each["line_id"]))
        # 存在性校验
        if not error_list:
            # 移动类型校验
            if dict_movement_type.get(each["movement_type"]) is None:
                error_list.append("行标识{}移动类型{}不存在".format(each["line_id"], each["movement_type"]))
            else:
                if dict_movement_type[each['movement_type']][0]['post_code'] != head["post_code"]:
                    error_list.append("行标识{}移动类型{}不适用过账码{}".format(each["line_id"], each["movement_type"],
                                                                                head["post_code"]))
            # 工厂代码校验
            if each["plant_code"] not in plant_code_data:
                error_list.append("行标识{}工厂代码{}不存在".format(each["line_id"], each["plant_code"]))
            # 库存地点校验
            if each.get("stor_loc_code", "") != "":
                # if not check_if_stor_loc_code_exists(each["stor_loc_code"]):
                #     error_list.append("行标识{}库存地点{}不存在".format(each["line_id"], each["stor_loc_code"]))
                # else:
                if dict_plant_storage.get(each["plant_code"] + each["stor_loc_code"]) is None:
                    error_list.append(
                        "行标识{}在工厂{}下库存地点{}未分配".format(each["line_id"], each["plant_code"],
                                                                    each["stor_loc_code"]))
            # 特殊库存状态1校验
            if each.get("special_inventory_status1", "") != "":
                if each["movement_type"] + each["special_inventory_status1"] not in movement_special_inventory_status1:
                    error_list.append(
                        "行标识{}在移动类型{}下特殊库存标识1{}未分配".format(each["line_id"], each["movement_type"],
                                                                             each["special_inventory_status1"]))
            # 库存状态
            if each.get("inventory_status", "") != "":
                if dict_inventory_status.get(each["inventory_status"]) is None:
                    error_list.append("行标识{}库存状态{}不存在".format(each["line_id"], each["inventory_status"]))
            # 物料状态检查
            if each.get("mat_code", "") != "":
                key = each["mat_code"] + each["plant_code"]
                if dict_mat_code.get(key) is None:
                    error_list.append("行标识{}物料编码{}在工厂{}不存在".format(each["line_id"], each["mat_code"], each["plant_code"]))
                else:
                    mat_info = dict_mat_code[key][0]
                    if mat_info.get('deleted_mark', 0) == 1 or mat_info.get('lock_flag', 0) == 1:
                        error_list.append("行标识{}物料编码{}已删除或锁定".format(each["line_id"], each["mat_code"]))
                    elif mat_info.get('value_update', 0) == 1:
                        if dict_mat_code_cost.get(key) is None:
                            error_list.append("行标识{}物料编码{}成本视图未扩".format(each["line_id"], each["mat_code"]))
            # 采购订单状态检查
            if each.get("rel_po_sn", "") != "":
                msg = check_po_status(each["rel_po_sn"], dict_po_header)
                if msg != "":
                    error_list.append("行标识{}{}".format(each["line_id"], msg))
                else:
                    # 采购订单行检查
                    msg = check_po_item_status(head["post_code"], each["rel_po_sn"], each["rel_po_items"], dict_po_item)
                if msg != "":
                    error_list.append("行标识{}{}".format(each["line_id"], msg))
            if each.get("rel_po_component_number", 0) != 0:
                # 采购订单行的序号检查
                if check_if_po_component_exists(each["rel_po_sn"], each["rel_po_items"],
                                                each["rel_po_component_number"], dict_po_component):
                    error_list.append(
                        "行标识{}关联采购订单{}行{}项目序号{}不存在".format(each["line_id"], each["rel_po_sn"],
                                                                            each["rel_po_items"],
                                                                            each["rel_po_component_number"]))
            if each.get("rel_po_comp_batch_num", 0) != 0:
                # 采购订单库存绑定表检查
                if check_if_po_batch_binding_exists(each["rel_po_sn"], each["rel_po_items"],
                                                    each["rel_po_component_number"],
                                                    each["rel_po_comp_batch_num"], dict_po_binding):
                    error_list.append("行标识{}关联采购订单{}行{}项目序号{}绑定序号{}不存在".format(each["line_id"],
                                                                                                    each["rel_po_sn"],
                                                                                                    each[
                                                                                                        "rel_po_items"],
                                                                                                    each[
                                                                                                        "rel_po_component_number"],
                                                                                                    each[
                                                                                                        "rel_po_comp_batch_num"]))
            if each.get("prodosn", "") != "":
                # 生产订单检查
                if dict_prodosn_data.get(each["prodosn"]) is None:
                    error_list.append("行标识{}生产订单{}不存在".format(each["line_id"], each["prodosn"]))
            if each.get("inv_transfer_order_no", "") != "":
                # 库存调拨单
                if dict_inv_transfer_order.get(each["inv_transfer_order_no"]) is None:
                    error_list.append(
                        "行标识{}库存调拨单{}不存在".format(each["line_id"], each["inv_transfer_order_no"]))
                elif dict_inv_transfer_order_item.get(
                        each["inv_transfer_order_no"] + str(each.get("inv_transfer_order_items", 0))) is None:
                    error_list.append(
                        "行标识{}库存调拨单{}行号{}不存在".format(each["line_id"], each["inv_transfer_order_no"],
                                                                  each.get("inv_transfer_order_items", 0)))
            if each.get("rel_dn_sn", "") != "":
                # 关联交货单检查
                if dict_dn_sn_header.get(each["rel_dn_sn"]) is None:
                    error_list.append("行标识{}关联交货单{}不存在".format(each["line_id"], each["rel_dn_sn"]))
                elif dict_dn_sn_item.get(each["rel_dn_sn"] + str(each.get("rel_dn_item", 0))) is None:
                    error_list.append("行标识{}关联交货单{}行号{}不存在".format(each["line_id"], each["rel_dn_sn"],
                                                                                each.get("rel_dn_item", 0)))
            if each.get("picking_document", "") != "":
                # 拣配单号检查
                if dict_picking_document.get(each["picking_document"] + str(each.get("batch_item", 0))) is None:
                    error_list.append("行标识{}拣配单号{}不存在".format(each["line_id"], each["picking_document"]))
            if each.get("ro_sn", "") != "":

                if dict_ro_sn_data.get(each["ro_sn"] + str(each.get("ro_items", 0))) is None:
                    error_list.append("行标识{}关联预留单{}行号{}不存在".format(each["line_id"], each["ro_sn"],
                                                                                each.get("ro_items", 0)))
            if each.get("rel_so_sn", "") != "":

                if dict_so_sn_data.get(each["rel_so_sn"] + str(each.get("rel_so_items", 0))) is None:
                    error_list.append("行标识{}关联销售订单{}行号{}不存在".format(each["line_id"], each["rel_so_sn"],
                                                                                  each.get("rel_so_items", "")))
            if each.get("special_inventory_status1", "") == "C" or each.get("special_inventory_status1", "") == "CC":
                # 客户检查
                if each.get("customer_code", "") == "":
                    error_list.append("行标识{}客户编码必输".format(each["line_id"]))
                else:
                    if dict_customer_code_data.get(each["customer_code"]) is None:
                        error_list.append("行标识{}客户编码{}不存在".format(each["line_id"], each["customer_code"]))
            else:
                each["customer_code"] = ""

            if each.get("special_inventory_status1", "") == "S":
                # 销售订单检查
                if each.get("so_sn", "") == "" or each.get("so_items", "") == "":
                    error_list.append("行标识{}销售订单信息必输".format(each["line_id"]))
                else:
                    if dict_so_sn_data.get(each.get("so_sn", "") + str(each.get("so_items", 0))) is None:
                        error_list.append("行标识{}销售订单{}行号{}不存在".format(each["line_id"], each["rel_so_sn"],
                                                                                  each.get("rel_so_items", "")))
            else:
                each["so_sn"] = ""
                each["so_items"] = 0

            if each.get("special_inventory_status1", "") == "P":
                # 项目编码检查
                if each.get("project_sn", "") == "":
                    error_list.append("行标识{}项目编码必输".format(each["line_id"]))
                    # 项目编码检查待定-----
            else:
                each["project_sn"] = ""

            if each.get("special_inventory_status1", "") == "V" or each.get("special_inventory_status1", "") == "SC":
                # 供应商编码检查
                if each.get("vendor_code", "") == "":
                    error_list.append("行标识{}供应商编码必输".format(each["line_id"]))
                else:
                    if dict_vendor_code_data.get(each["vendor_code"]) is None:
                        error_list.append("行标识{}供应商编码{}不存在".format(each["line_id"], each["vendor_code"]))

                if each["special_inventory_status1"] == "V":
                    if each.get("po_sn", "") != "":
                        # 采购订单检查
                        if dict_po_header.get(each["po_sn"]) is None:
                            error_list.append("行标识{}采购订单{}不存在".format(each["line_id"], each["po_sn"]))
                        else:
                            if dict_po_item.get(each["po_sn"] + str(each.get("po_items", 0))) is None:
                                error_list.append(
                                    "行标识{}采购订单{}行号{}不存在".format(each["line_id"], each["rel_so_sn"],
                                                                            each.get("rel_so_items", "")))
                else:
                    each["po_sn"] = ""
                    each["po_items"] = 0
            else:
                each["vendor_code"] = ""
                each["po_sn"] = ""
                each["po_items"] = 0

            if each.get("cost_center", "") != "":
                # 成本中心检查
                if dict_cost_center_data.get(each["cost_center"] + each["plant_code"]) is None:
                    error_list.append(
                        "行标识{}成本中心{}在工厂{}对应的公司代码不存在".format(each["line_id"], each["cost_center"],
                                                                                each["plant_code"]))
            if each.get("cost_business_object", "") != "":
                # 成本事项检查
                if dict_cost_business_object_data.get(each["cost_business_object"] + each["plant_code"]) is None:
                    error_list.append(
                        "行标识{}成本事项{}在工厂{}对应的公司代码不存在".format(each["line_id"],
                                                                                each["cost_business_object"],
                                                                                each["plant_code"]))
            if each.get("cost_business_object1", "") != "":
                # 成本事项1检查
                if dict_cost_business_object_data.get(each["cost_business_object1"] + each["plant_code"]) is None:
                    error_list.append(
                        "行标识{}成本事项1{}在工厂{}对应的公司代码不存在".format(each["line_id"],
                                                                                 each["cost_business_object1"],
                                                                                 each["plant_code"]))
            if each.get("profit_center", "") != "":
                # 利润中心检查
                if dict_profit_center_data.get(each["profit_center"] + each["plant_code"]) is None:
                    error_list.append(
                        "行标识{}利润中心{}在工厂{}对应的公司代码不存在".format(each["line_id"], each["profit_center"],
                                                                                each["plant_code"]))
            if each.get("equipment_code", "") != "":
                # 设备ID检查
                if dict_equipment_code_data.get(each["equipment_code"]) is None:
                    error_list.append("行标识{}设备ID{}不存在".format(each["line_id"], each["equipment_code"]))

            if each.get("transaction_currency", "") == "":
                each["transaction_currency"] = get_company_basic_currency(each['plant_code'], dict_company)

    print("item校验成功！！！")

    md_header = initialization("t_md_header", db)
    md_item = []
    md_price = []


    print("head： 11111111", head)
    # 生成凭证数据
    if not error_list:
        # 单据种类
        md_header["document_category"] = "MDOC"
        # 物料凭证
        md_header["mat_doc_sn"] = ""
        # 年度
        md_header["year"] = head["posting_date"][:4]
        # 过账代码
        md_header["post_code"] = head["post_code"]
        # 凭证日期
        md_header["document_date"] = head["document_date"]
        # 过账日期
        md_header["posting_date"] = head["posting_date"]

        # 汇总唯一号
        md_header["summary_unique_number"] = head.get("summary_unique_number", "")
        # 备注信息1
        md_header["remarks_1"] = head.get("remarks_1", "")
        # 备注信息2
        md_header["remarks_2"] = head.get("remarks_2", "")
        # 供应商交货单
        md_header["vendor_dn"] = head.get("vendor_dn", "")
        # 物料凭证类型
        md_header["material_document_type"] = ""
        # 交易汇率 公司代码 信息
        md_header["company_code"], md_header["exchange_rate"] = get_company_info(item[0]["plant_code"],
                                                                                 item[0]["transaction_currency"],
                                                                                 dict_company)

        if head.get('exchange_rate', 0) != 0:
            md_header["exchange_rate"] = head['exchange_rate']

        # 预留字段
        md_header["reserved1"] = head.get("reserved1", "")
        md_header["reserved2"] = head.get("reserved2", "")
        md_header["reserved3"] = head.get("reserved3", "")
        md_header["reserved4"] = head.get("reserved4", "")
        md_header["reserved5"] = head.get("reserved5", "")
        md_header["reserved6"] = head.get("reserved6", "")
        md_header["reserved7"] = head.get("reserved7", "")
        md_header["reserved8"] = head.get("reserved8", "")
        md_header["reserved9"] = head.get("reserved9", "")
        md_header["reserved10"] = head.get("reserved10", "")

        md_header["create_id"] = user_id
        md_header["update_id"] = user_id

        md_header["ztype"] = head.get('ztype', '')

        if md_header["exchange_rate"] == 0:
            error_list.append("未获取到汇率")

        line_tmp = initialization("t_md_item", db)
        price_tmp = initialization("t_md_price_details", db)

        item_no = 0
        # 行项目设置
        for each in item:

            line = line_tmp.copy()
            price = price_tmp.copy()

            item_no += 1
            # 物料凭证
            line["mat_doc_sn"] = md_header["mat_doc_sn"]
            # 年度
            line["year"] = md_header["year"]
            # 物料凭证信息行号
            line["mat_doc_items"] = item_no
            # 物料凭证行唯一标识
            line["line_id"] = each["line_id"]
            # 凭证行参考唯一标识
            line["parent_id"] = each.get("parent_id", 0)
            # 参考凭证行
            line["ref_item_serial_no"] = 0
            # 自动创建标识
            line["auto_mark"] = 0
            # 移动类型
            line["movement_type"] = each["movement_type"]
            # 物料凭证类型 借贷标识  收发标识  科目修改 业务单据种类
            line, material_document_type, prod_order_mark, wbs_elements_mark, cost_business_object_mark, asset_code1_mark = get_movement_attribute(
                line, line["movement_type"], dict_movement_type)
            if md_header["material_document_type"] == "":
                md_header["material_document_type"] = material_document_type
            if line["debit_credit_mark"] == "":
                error_list.append(
                    "行标识{}未能根据移动类型{}取到借贷标识".format(each["line_id"], each["movement_type"]))
            if line["receipt_consume_mark"] == "":
                error_list.append(
                    "行标识{}未能根据移动类型{}取到收发标识".format(each["line_id"], each["movement_type"]))
            if prod_order_mark == 1:
                if each.get("prodosn", "") == "":
                    error_list.append("行标识{}生产订单必填".format(each["line_id"]))
                else:
                    status_update_ls = [(each.get("prodosn", ""), 'GI', 1)]
                    result, msg = production_order_status_update(status_update_ls,check_mode = 1)
                    if not result:
                        error_list.append(msg)
            if wbs_elements_mark == 1:
                if each.get("wbs_elements", "") == "":
                    error_list.append("行标识{}WBS必填".format(each["line_id"]))
            if cost_business_object_mark == 1:
                if each.get("cost_center", "") == "" and each.get("cost_business_object", "") == "" and each.get(
                        "cost_business_object1", "") == "":
                    error_list.append("行标识{}成本中心/成本事项/成本事项1必填一个".format(each["line_id"]))
            if asset_code1_mark == 1:
                if each.get("asset_code1", "") == "":
                    error_list.append("行标识{}资产卡片必填".format(each["line_id"]))
            # 特殊库存状态1
            line["special_inventory_status1"] = each.get("special_inventory_status1", "")
            # 特殊库存状态2
            line["special_inventory_status2"] = each.get("special_inventory_status2", "")
            # 库存状态
            line["inventory_status"] = get_inventory_status(each["movement_type"], each.get("inventory_status", ""),
                                                            dict_movement_type)
            # 事件类型 物料成本特殊评估标识
            line["transaction_type_code"], line["mat_special_val_mark"] = get_transaction_type_code(
                each["movement_type"], each["plant_code"], each["mat_code"], each.get("rel_po_sn", ""),
                each.get("rel_po_items", 0),
                line.get("special_inventory_status1", ""), line.get("special_inventory_status2", ""), dict_relation,
                dict_po_item,
                dict_mat_code)
            if line["transaction_type_code"] == "":
                error_list.append("行标识{}未能根据移动类型{}和采购订单{}信息取到事件类型".format(each["line_id"],
                                                                                                  each["movement_type"],
                                                                                                  each.get("rel_po_sn",
                                                                                                           "")))
            # 工厂代码
            line["plant_code"] = each["plant_code"]
            # 公司代码
            line["company_code"] = md_header["company_code"]

            # 结算公司代码
            line["settle_company_code"] = get_settle_company_code(each["plant_code"], dict_company)
            # 物料编码
            line["mat_code"] = each.get("mat_code", "")
            # 库存地点
            if line["mat_code"] == "" or line["special_inventory_status1"] == "V":
                line["stor_loc_code"] = ""
            else:
                line["stor_loc_code"] = each.get("stor_loc_code", "")
            # 批次号
            line["batch_sn"] = each.get("batch_sn", "")
            # 交易数量
            line["transaction_qty"] = each["transaction_qty"]
            # 交易单位
            line["transaction_uom"] = each["transaction_uom"]
            # 带借贷标识的交易数量
            if line["debit_credit_mark"] == "Cr":
                line["transaction_qty_dc_mark"] = line["transaction_qty"] * -1
            else:
                line["transaction_qty_dc_mark"] = line["transaction_qty"]

            # 基本单位/成本单位/价格控制/评估类/物料组
            line = get_material_uom(line["mat_code"], line["plant_code"], dict_mat_code, line)

            # # 平行数量
            # line["parallel_qty"] = each["parallel_qty"]
            # 平行单位
            line["parallel_uom"] = each.get("parallel_uom", "")

            # 计算基本数量和成本数量
            line = get_other_qty_by_unit(each, line, head['post_code'],
                                         dict_movement_type[each['movement_type']][0]['allow_zero_base_qty'],
                                         dict_movement_type[each['movement_type']][0]['allow_zero_parallel_qty'],
                                         dict_mat_uom_convert)

            if dict_movement_type[each['movement_type']][0]['allow_zero_base_qty'] == 0:
                if line["basic_qty"] <= 0:
                    error_list.append("行标识{}基本数量不能为0".format(each["line_id"]))

            if dict_movement_type[each['movement_type']][0]['allow_zero_parallel_qty'] == 0:
                if line["parallel_qty"] <= 0 and line["parallel_uom"]:
                    error_list.append("行标识{}平行数量不能为0".format(each["line_id"]))

            # 带借贷标识的基本数量
            if line["debit_credit_mark"] == "Cr":
                line["basic_qty_dc_mark"] = line["basic_qty"] * -1
            else:
                line["basic_qty_dc_mark"] = line["basic_qty"]

            # 带借贷标识的成本数量
            if line["debit_credit_mark"] == "Cr":
                line["cost_qty_dc_mark"] = line["cost_qty"] * -1
            else:
                line["cost_qty_dc_mark"] = line["cost_qty"]

            # 带借贷标识的平行数量
            if line["debit_credit_mark"] == "Cr":
                line["parallel_qty_dc_mark"] = line["parallel_qty"] * -1
            else:
                line["parallel_qty_dc_mark"] = line["parallel_qty"]
            # 定价单位 定价单位数量 交易金额 交易货币 采购订单供应商
            line = get_po_qty_amount_info(line, each.get("rel_po_sn", ""), each.get("rel_po_items", 0), dict_po_header,
                                          dict_po_item)
            # 交易货币
            if each.get("transaction_currency", "") == "":
                line["transaction_currency"] = get_company_basic_currency(each['plant_code'], dict_company)
            else:
                line["transaction_currency"] = each["transaction_currency"]
            # 消耗记账 对象标识 价值更新 数量更新
            line = get_movement_label(line, each.get("rel_po_sn", ""), each.get("rel_po_items", 0), dict_movement_type,
                                      dict_mat_code,
                                      dict_po_item, dict_movement_label1, dict_movement_label2, dict_movement_label3)
            if line["consumption_posting_label"] == "":
                error_list.append("行标识{}消耗记账标识不能为空".format(each["line_id"]))
            if line["item_indicator"] == "":
                error_list.append("行标识{}对象标识不能为空".format(each["line_id"]))
            if line["value_update"] == "":
                error_list.append("行标识{}价值更新不能为空".format(each["line_id"]))
            # 关联采购订单
            line["rel_po_sn"] = each.get("rel_po_sn", "")
            # 关联采购订单行
            line["rel_po_items"] = each.get("rel_po_items", 0)
            # 关联采购订单行项目序号
            line["rel_po_component_number"] = each.get("rel_po_component_number", 0)
            # 关联采购订单行序号
            line["rel_po_comp_batch_num"] = each.get("rel_po_comp_batch_num", 0)
            # 关联生产订单组件序号
            line["prodo_component_number"] = each.get("prodo_component_number", '')
            # 生产订单
            line["prodosn"] = each.get("prodosn", "")
            # 生产订单组件检查
            line['prodo_component_number'] = each.get('prodo_component_number', '')
            if line['prodo_component_number'] != 0:
                key = line["prodosn"] + str(line['prodo_component_number'])
                if dict_prodosn_component_data.get(key):
                    if dict_prodosn_component_data[key][0]['issuing_completed_flag'] == 1 and line[
                        'debit_credit_mark'] == 'Cr':
                        error_list.append("行标识{}生产订单{}组件序号{}不允许发料".format(each["line_id"],
                                                                                          line["prodosn"], str(
                                line['prodo_component_number'])))
            # 关联交货单
            line["rel_dn_sn"] = each.get("rel_dn_sn", "")
            # 关联交货单行号
            line["rel_dn_item"] = each.get("rel_dn_item", 0)
            # 拣配单号
            line["picking_document"] = each.get("picking_document", "")
            # 批次行号
            line["batch_item"] = each.get("batch_item", 0)
            # 关联预留单
            line["ro_sn"] = each.get("ro_sn", "")
            # 关联预留单行
            line["ro_items"] = each.get("ro_items", 0)
            # 关联销售订单
            line["rel_so_sn"] = each.get("rel_so_sn", "")
            # 关联销售订单行项目
            line["rel_so_items"] = each.get("rel_so_items", 0)
            # 关联单据种类 关联单据号 关联行号 原始单据类型 原始单据号 原始单据行号
            line = get_associated_order(md_header, line)
            # 客户编码
            line["customer_code"] = each.get("customer_code", "")
            # 销售订单
            line["so_sn"] = each.get("so_sn", "")
            # 销售订单行项目
            line["so_items"] = each.get("so_items", 0)
            # 库存调拨单
            line['inv_transfer_order_no'] = each.get("inv_transfer_order_no", '')
            # 库存调拨单行
            line['inv_transfer_order_items'] = each.get("inv_transfer_order_items", 0)
            # 项目编号
            line["project_sn"] = each.get("project_sn", "")
            # 供应商编码
            line["vendor_code"] = each.get("vendor_code", "")
            # 采购订单
            line["po_sn"] = each.get("po_sn", "")
            # 采购订单行项目
            line["po_items"] = each.get("po_items", 0)
            # WBS元素
            line["wbs_elements"] = each.get("wbs_elements", "")
            # 成本中心
            line["cost_center"] = each.get("cost_center", "")
            # 成本事项
            line["cost_business_object"] = each.get("cost_business_object", "")
            # 成本事项1
            line["cost_business_object1"] = each.get("cost_business_object1", "")
            # 利润中心
            line["profit_center"] = each.get("profit_center", "")
            # 会计科目
            line["accounting_subjects"] = each.get("accounting_subjects", "")
            # 资产卡片
            line["asset_code1"] = each.get("asset_code1", "")
            # 子资产
            line["asset_code2"] = each.get("asset_code2", "")
            # 设备ID
            line["equipment_code"] = each.get("equipment_code", "")
            # 快递单号
            line["express_delivery"] = each.get("express_delivery", "")
            # 行参考信息1
            line["reference1_item"] = each.get("reference1_item", "")
            # 行参考信息2
            line["reference2_item"] = each.get("reference2_item", "")
            # 行参考信息3
            line["reference3_item"] = each.get("reference3_item", "")
            # 汇总行
            line["summary_line"] = each.get("summary_line", 0)
            # 批次编码校验
            if each.get("mat_code", "") != "":
                line["batch_sn"], each['batch_number'], msg = check_batch_required(line["mat_code"], line["plant_code"],
                                                                                   line["batch_sn"],
                                                                                   line["debit_credit_mark"],
                                                                                   dict_mat_code, dict_mat_batch,
                                                                                   each.get('batch_number', {}),
                                                                                   dict_movement_type[
                                                                                       line['movement_type']][0],
                                                                                       user_id=user_id)
                if msg != "":
                    error_list.append("行标识{}{}".format(each["line_id"], msg))

            # 交易前移动平均价（成本货币）/ 交易前移动平均价（本位币）
            # ---待补充
            # 采购项目类别 / 科目分配类别 / 采购订单数量 / 采购订单单位 / 免费标记 / 返工标记 / 返工类型 / 加工工序
            line = get_po_item_other_info(line, line["rel_po_sn"], line["rel_po_items"], dict_po_item)

            # 质检过账标识 / 质量检验单标识
            line["quality_insp_post_mark"] = each.get("quality_insp_post_mark", 0)
            line["quality_insp_order_mark"], msg = get_quality_inspection_mark(line["mat_code"], line["plant_code"],
                                                                               line["inventory_status"],
                                                                               line["movement_type"],
                                                                               line["debit_credit_mark"],
                                                                               line["quality_insp_post_mark"],
                                                                               dict_mat_code, dict_movement_type,
                                                                               dict_mat_insp)
            if msg != "":
                error_list.append("行标识{}{}".format(each["line_id"], msg))

            # 结批标识
            line["batch_closure_flag"] = each.get("batch_closure_flag", 0)
            # 结批日期
            line["batch_closure_date"] = each.get("batch_closure_date", "")
            # 收货完成标记
            line["receipt_completed_flag"] = each.get("receipt_completed_flag", 0)

            # 移动原因
            line["movement_reason"] = each.get("movement_reason", "")

            # 参考凭证年度
            line["rel_document_year"] = each.get("rel_document_year", "")
            # 参考凭证号
            line["rel_document_no"] = each.get("rel_document_no", "")
            # 参考凭证行号
            line["ref_document_mat"] = each.get("ref_document_mat", 0)
            # 前序物料凭证年度
            line["pre_document_year"] = each.get("pre_document_year", "")
            # 前序物料凭证
            line["pre_document_no"] = each.get("pre_document_no", "")
            # 前序物料凭证行号
            line["pre_document_item"] = each.get("pre_document_item", 0)

            # 预留字段
            line["reserved1"] = each.get("reserved1", "")
            line["reserved2"] = each.get("reserved2", "")
            line["reserved3"] = each.get("reserved3", "")
            line["reserved4"] = each.get("reserved4", "")
            line["reserved5"] = each.get("reserved5", "")
            line["reserved6"] = each.get("reserved6", "")
            line["reserved7"] = each.get("reserved7", "")
            line["reserved8"] = each.get("reserved8", "")
            line["reserved9"] = each.get("reserved9", "")
            line["reserved10"] = each.get("reserved10", "")

            line["batch_number"] = each.get('batch_number', {})
            line["batch_number"]["create_id"] = user_id
            line["batch_number"]["update_id"] = user_id

            line["create_id"] = user_id
            line["update_id"] = user_id

            md_item.append(line.copy())

            # 价格明细表
            # 物料凭证
            price["mat_doc_sn"] = md_header["mat_doc_sn"]
            # 年度
            price["year"] = md_header["year"]
            # 物料凭证信息行号
            price["mat_doc_items"] = item_no
            md_price = get_po_price(md_price, line, price, user_id, dict_price_data)

    print("生成凭证数据成功！！！")

    if not error_list:
        # 库存校验
        msg_list = get_inventory_qty(md_item, md_header["posting_date"], dict_plant_storage, db)
        if msg_list:
            error_list.extend(msg_list)

    if error_list:
        code = 500
        msg = "存在错误,请检查"
    else:
        code = 200
        msg = "检查无误"

    return code, msg, error_list, md_header, md_item, md_price


# 正式过账代码7
def post_data_postcode7(user_id, md_header, md_item, md_price, db):
    code = 0
    msg = ""
    mat_doc_sn = ""
    year = ""
    error_list = []

    try:
        mat_code = md_item[0]["mat_code"]
        batch_sn = md_item[0]["batch_sn"]
        lock_key = f"LOCK_{mat_code}_{batch_sn}"
    except:
        lock_key = f"LOCK_USER_{user_id}"

    try:
        # 加锁
        code, msg = lock_data(md_item, LockAction.lock, lock_key)
        if code != 200:
            error_list.append(msg)
            raise Exception("加锁失败：" + msg)

        # 调用会计引擎
        input = json.dumps([{"header": md_header, "items": md_item, "details": md_price}])
        sh = SystemHelper()
        output = json.loads(sh.execOperator("OnConsumeMat", input)["data"])

        if output["result"] == 0:
            if "data" in output:
                code = 200
                if output["data"][0]["status"] == "E":
                    code = 500
                    msg = output["data"][0]["msg"]
                else:
                    mat_doc_sn = output["data"][0]["mat_doc_sn"]
                    year = output["data"][0]["year"]
                    msg = "过账成功,物料凭证:{} 年度{}".format(mat_doc_sn, year)
            else:
                code = 500
                msg = output.get("msg", "会计引擎异常")
        else:
            code = 500
            msg = output["msg"]

    except Exception as e:
        if not error_list:
            error_list.append(str(e))
        code = 500
        msg = "存在错误,请检查"

    finally:
        lock_data(md_item, LockAction.unlock, lock_key)

    return code, msg, error_list, mat_doc_sn, year


# 检查过账代码7的参数
def check_data_postcode7(user_id, head, item, db):
    from datetime import datetime
    code = 200
    msg = ""
    error_list = []

    # 增强 -- 检验前
    code, msg, error_list, head, item = before_check(user_id, head, item)
    if code != 200:
        return code, msg, error_list, [], [], []

    dict_movement_type = {}
    movement_type = []
    plant_code = []
    plant_code_data = []
    dict_plant_storage = {}
    movement_special_inventory_status1 = []
    movement_special_inventory_status2 = []
    mat_code = []
    dict_mat_code = {}
    dict_mat_code_cost = {}
    po_sn = []
    dict_po_header = {}
    dict_po_item = {}
    prodosn = []
    dict_prodosn_data = {}
    dn_sn = []
    dict_dn_sn_header = {}
    dict_dn_sn_item = {}
    picking_document = []
    dict_picking_document = {}
    procure_dn_sn = []
    dict_procure_dn_sn_data = {}
    ro_sn = []
    dict_ro_sn_data = {}
    so_sn = []
    dict_so_sn_data = {}
    customer_code = []
    dict_customer_code_data = {}
    vendor_code = []
    dict_vendor_code_data = {}
    cost_center = []
    dict_cost_center_data = {}
    cost_business_object = []
    dict_cost_business_object_data = {}
    profit_center = []
    dict_profit_center_data = {}
    equipment_code = []
    dict_equipment_code_data = {}
    dict_company = {}
    dict_relation = {}
    dict_relation2 = {}
    dict_movement_label1 = {}
    dict_movement_label2 = {}
    dict_movement_label3 = {}
    dict_mat_batch = {}
    batch = []
    dict_mat_insp = {}
    dict_price_data = {}
    mat_doc_sn = []
    mat_year = []
    dict_inventory_status = {}
    inv_transfer_order_no = []
    dict_inv_transfer_order = {}
    dict_inv_transfer_order_item = {}

    # 性能优化
    for each in item:
        # 移动类型
        if each.get("movement_type", "") != "":
            movement_type.append(each['movement_type'])
        # 工厂
        if each.get("plant_code", "") != "":
            plant_code.append(each['plant_code'])

        # 物料编码
        if each.get("mat_code", "") != "":
            mat_code.append(each['mat_code'])

        # 采购订单
        if each.get("rel_po_sn", '') != '':
            po_sn.append(each['rel_po_sn'])
        if each.get('po_sn', '') != '':
            po_sn.append(each['po_sn'])

        # 生产订单
        if each.get('prodosn', '') != '':
            prodosn.append(each['prodosn'])

        # 交货单
        if each.get('rel_dn_sn', '') != '':
            dn_sn.append(each['rel_dn_sn'])

        # 拣配单
        if each.get('picking_document', '') != '':
            picking_document.append(each['picking_document'])

        # 采购交货单
        if each.get('rel_procure_dn_sn', '') != '':
            procure_dn_sn.append(each['rel_procure_dn_sn'])

        # 预留
        if each.get('ro_sn', '') != '':
            ro_sn.append(each['ro_sn'])

        # 销售订单
        if each.get('rel_so_sn', '') != '':
            so_sn.append(each['rel_so_sn'])
        if each.get('so_sn', '') != '':
            so_sn.append(each['so_sn'])

        # 客户
        if each.get('customer_code', '') != '':
            customer_code.append(each['customer_code'])

        # 供应商
        if each.get('vendor_code', '') != '':
            vendor_code.append(each['vendor_code'])

        # 成本中心
        if each.get('cost_center', '') != '':
            cost_center.append(each['cost_center'])

        # 成本事项
        if each.get('cost_business_object', '') != '':
            cost_business_object.append(each['cost_business_object'])
        if each.get('cost_business_object1', '') != '':
            cost_business_object.append(each['cost_business_object1'])

        # 利润中心
        if each.get('profit_center', '') != '':
            profit_center.append(each['profit_center'])

        # 设备
        if each.get('equipment_code', '') != '':
            equipment_code.append(each['equipment_code'])

        # 批次
        if each.get('batch_sn', '') != '':
            batch.append(each['batch_sn'])

        # 物料凭证
        if each.get('rel_document_no', '') != '':
            mat_doc_sn.append(each['rel_document_no'])
        # 物料凭证年度
        if each.get('rel_document_year', '') != '':
            mat_year.append(each['rel_document_year'])
        # 库存调拨单
        if each.get("inv_transfer_order_no", "") != '':
            inv_transfer_order_no.append(each['inv_transfer_order_no'])

    data_begin = time.time()
    # 获取移动类型属性
    dict_movement_type = get_movement_type_info(movement_type, db)
    # 获取工厂
    plant_code_data = get_plant_code_data(plant_code, db)
    # 获取工厂对应库存地点
    dict_plant_storage = get_plant_storage(plant_code, db)
    # 获取移动类型对应特殊库存状态
    movement_special_inventory_status1, movement_special_inventory_status2, dict_relation, dict_relation2 = get_movement_special_inventory_status(
        movement_type, db)
    # 获取物料主数据信息
    dict_mat_code = get_mat_code_info(mat_code, plant_code, db)
    # 获取物料成本视图
    dict_mat_code_cost = get_mat_code_cost_info(mat_code, plant_code, db)
    # 获取物料单位换算关系
    dict_mat_uom_convert = get_mat_uom_convert(mat_code, db)
    # 获取采购订单抬头信息
    dict_po_header = get_po_header(po_sn, db)
    # 获取采购订单行项目信息
    dict_po_item = get_po_item(po_sn, db)
    # 获取批次组件表
    dict_po_component = get_po_component(po_sn, db)
    # 获取采购订单批次绑定表
    dict_po_binding = get_po_batch_binding(po_sn, db)
    # 获取物料评估组
    dict_valgroup_value = get_valgroup_value(po_sn, db)
    # 获取生产订单
    dict_prodosn_data = get_prodosn_data(prodosn, db)
    # 获取交货单抬头信息
    dict_dn_sn_header = get_dn_header(dn_sn, db)
    # 获取交货单行项目信息
    dict_dn_sn_item = get_dn_sn_item(dn_sn, db)
    # 获取拣配单信息
    dict_picking_document = get_picking_document_info(picking_document, db)
    # 获取采购交货单信息
    # dict_procure_dn_sn_data = get_procure_dn_sn_info(procure_dn_sn, db)
    # 获取预留单信息
    dict_ro_sn_data = get_ro_sn_info(ro_sn, db)
    # 获取销售订单信息
    dict_so_sn_data = get_so_sn_info(so_sn, db)
    # 获取客户信息
    dict_customer_code_data = get_customer_code_info(customer_code, db)
    # 获取供应商信息
    dict_vendor_code_data = get_vendor_code_info(vendor_code, db)
    # 获取成本中心
    dict_cost_center_data = get_cost_center_info(cost_center, db)
    # 获取成本事项
    dict_cost_business_object_data = get_cost_business_object_info(cost_business_object, db)
    # 利润中心
    dict_profit_center_data = get_profit_center_info(profit_center, db)
    # 获取设备主数据信息
    dict_equipment_code_data = get_equipment_code_info(equipment_code, db)
    # 按工厂获取公司信息
    dict_company = get_company_info_by_plant(plant_code, db)
    # 获取移动类型配置信息
    dict_movement_label1, dict_movement_label2, dict_movement_label3 = get_movement_label_info(movement_type, db)
    # 获取物料批次信息
    dict_mat_batch = get_mat_code_and_batch(mat_code, batch, db)
    # 获取物料质检信息
    dict_mat_insp = get_mat_insp_info(mat_code, plant_code, db)
    # 获取采购订单价格明细
    dict_price_data = get_po_price_data(po_sn, db)
    # 获取物料凭证行信息
    dict_md_info, dict_md_info1, dict_md_info2, dict_pi_invoice_info = get_md_item(mat_doc_sn, mat_year, db)
    # 获取库存状态
    dict_inventory_status = get_all_inventory_status(db)
    # 获取库存调拨单
    dict_inv_transfer_order = get_inv_transfer_order(inv_transfer_order_no, db)
    # 获取库存调拨单行
    dict_inv_transfer_order_item = get_inv_transfer_order_item(inv_transfer_order_no, db)

    print("取值耗时: ", time.time() - data_begin)

    for each in item:
        # 必输校验
        # 行唯一标识校验
        if each.get("line_id", "") == "":
            error_list.append("行唯一标识必输")
            continue
        # 移动类型校验
        if each.get("movement_type", "") == "":
            error_list.append("行标识{}移动类型必输".format(each["line_id"]))
        # 物料编码
        if each.get("mat_code", "") == "":
            error_list.append("行标识{}物料编码必输".format(each["line_id"]))
        # 交易数量
        if Decimal(each.get("transaction_qty", 0)) <= 0:
            if dict_movement_type.get(each.get('movement_type', '')):
                if dict_movement_type[each['movement_type']][0]['allow_zero_base_qty'] == 0:
                    error_list.append("行标识{}交易数量必须大于0".format(each["line_id"]))
        # 交易单位
        if each.get("transaction_uom", "") == "":
            error_list.append("行标识{}交易单位必输".format(each["line_id"]))
        # # 基本数量
        # if each.get("basic_qty", 0) == 0:
        #     error_list.append("行标识{}基本数量必输".format(each["line_id"]))
        # # 基本单位
        # if each.get("basic_uom", "") == "":
        #     error_list.append("行标识{}基本单位必输".format(each["line_id"]))
        # # 平行单位
        # if each.get("parallel_uom", "") == "":
        #     error_list.append("行标识{}平行单位必输".format(each["line_id"]))
        # # 平行数量
        # if each.get("parallel_uom", "") == each.get("basic_uom", ""):
        #     each["parallel_qty"] = each["basic_qty"]
        # else:
        #     if each.get("basic_qty", 0) == 0:
        #         each["parallel_qty"] = 0
        #     else:
        #         if each.get("parallel_qty", 0) == 0:
        #             error_list.append("行标识{}平行数量必输".format(each["line_id"]))
        # if each.get("parallel_uom", "") != "":
        #     if each.get("parallel_qty", 0) == 0:
        #         if dict_movement_type.get(each.get('movement_type', '')):
        #             if dict_movement_type[each['movement_type']][0]['allow_zero_parallel_qty'] != 0:
        #                 error_list.append("行标识{}平行数量必输".format(each["line_id"]))

        # # 特殊库存状态1
        # if each["special_inventory_status1"] == "":
        #     error_list.append("行标识{}特殊库存状态1必输".format(each["line_id"]))
        # # 特殊库存状态1
        # if each["special_inventory_status1"] == "":
        #     error_list.append("行标识{}特殊库存状态1必输".format(each["line_id"]))
        # 库存状态
        if each.get("inventory_status", "") == "" and each.get("mat_code", "") != "":
            error_list.append("行标识{}库存状态必输".format(each["line_id"]))

        # 库存地点
        if each.get("mat_code", "") != "" and each["special_inventory_status1"] != 'V':
            if each["stor_loc_code"] == "":
                error_list.append("行标识{}库存地点必输".format(each["line_id"]))

        # 存在性校验
        if not error_list:
            # 移动类型校验
            if dict_movement_type.get(each["movement_type"]) is None:
                error_list.append("行标识{}移动类型{}不存在".format(each["line_id"], each["movement_type"]))
            else:
                if dict_movement_type[each['movement_type']][0]['post_code'] != head["post_code"]:
                    error_list.append("行标识{}移动类型{}不适用过账码{}".format(each["line_id"], each["movement_type"],
                                                                                head["post_code"]))
            # 工厂代码校验
            if each["plant_code"] not in plant_code_data:
                error_list.append("行标识{}工厂代码{}不存在".format(each["line_id"], each["plant_code"]))
            # 库存地点校验
            if each.get("stor_loc_code", "") != "":
                # if not check_if_stor_loc_code_exists(each["stor_loc_code"]):
                #     error_list.append("行标识{}库存地点{}不存在".format(each["line_id"], each["stor_loc_code"]))
                # else:
                if dict_plant_storage.get(each["plant_code"] + each["stor_loc_code"]) is None:
                    error_list.append(
                        "行标识{}在工厂{}下库存地点{}未分配".format(each["line_id"], each["plant_code"],
                                                                    each["stor_loc_code"]))
            # 特殊库存状态1校验
            if each.get("special_inventory_status1", "") != "":
                if each["movement_type"] + each["special_inventory_status1"] not in movement_special_inventory_status1:
                    error_list.append(
                        "行标识{}在移动类型{}下特殊库存标识1{}未分配".format(each["line_id"], each["movement_type"],
                                                                             each["special_inventory_status1"]))
            # 库存状态
            if each.get("inventory_status", "") != "":
                if dict_inventory_status.get(each["inventory_status"]) is None:
                    error_list.append("行标识{}库存状态{}不存在".format(each["line_id"], each["inventory_status"]))

            # 物料状态检查
            if each.get("mat_code", "") != "":
                key = each["mat_code"] + each["plant_code"]
                if dict_mat_code.get(key) is None:
                    error_list.append("行标识{}物料编码{}在工厂{}不存在".format(each["line_id"], each["mat_code"], each["plant_code"]))
                else:
                    mat_info = dict_mat_code[key][0]
                    if mat_info.get('deleted_mark', 0) == 1 or mat_info.get('lock_flag', 0) == 1:
                        error_list.append("行标识{}物料编码{}已删除或锁定".format(each["line_id"], each["mat_code"]))
                    elif mat_info.get('value_update', 0) == 1:
                        if dict_mat_code_cost.get(key) is None:
                            error_list.append("行标识{}物料编码{}成本视图未扩".format(each["line_id"], each["mat_code"]))
            # 采购订单状态检查
            msg = check_po_status(each["rel_po_sn"], dict_po_header)
            if msg != "":
                error_list.append("行标识{}{}".format(each["line_id"], msg))
            else:
                # 采购订单行检查
                msg = check_po_item_status(head["post_code"], each["rel_po_sn"], each["rel_po_items"], dict_po_item)
            if msg != "":
                error_list.append("行标识{}{}".format(each["line_id"], msg))
            if each.get("rel_po_component_number", 0) != 0:
                # 采购订单行的序号检查
                if check_if_po_component_exists(each["rel_po_sn"], each["rel_po_items"],
                                                each["rel_po_component_number"], dict_po_component):
                    error_list.append(
                        "行标识{}关联采购订单{}行{}项目序号{}不存在".format(each["line_id"], each["rel_po_sn"],
                                                                            each["rel_po_items"],
                                                                            each["rel_po_component_number"]))
            if each.get("rel_po_comp_batch_num", 0) != 0:
                # 采购订单库存绑定表检查
                if check_if_po_batch_binding_exists(each["rel_po_sn"], each["rel_po_items"],
                                                    each["rel_po_component_number"],
                                                    each["rel_po_comp_batch_num"], dict_po_binding):
                    error_list.append("行标识{}关联采购订单{}行{}项目序号{}绑定序号{}不存在".format(each["line_id"],
                                                                                                    each["rel_po_sn"],
                                                                                                    each[
                                                                                                        "rel_po_items"],
                                                                                                    each[
                                                                                                        "rel_po_component_number"],
                                                                                                    each[
                                                                                                        "rel_po_comp_batch_num"]))
            # 母行物料与采购订单检查
            if each.get("parent_id", 0) == 0:
                if check_if_valgroup_value_exist(each["rel_po_sn"], each["rel_po_items"], each["mat_code"],
                                                 each["plant_code"], dict_valgroup_value):
                    error_list.append("行标识{}未找到组评估物料,禁止修改物料".format(each["line_id"]))
            if each.get("prodosn", "") != "":
                # 生产订单检查
                if dict_prodosn_data.get(each["prodosn"]) is None:
                    error_list.append("行标识{}生产订单{}不存在".format(each["line_id"], each["prodosn"]))
            if each.get("special_inventory_status2", "") == "T":
                # 关联交货单
                if each.get("rel_dn_sn", "") == "" or each.get("rel_dn_item", "") == "":
                    error_list.append("行标识{}关联交货单必输".format(each["line_id"]))
            if each.get("rel_dn_sn", "") != "":
                # 关联交货单检查
                if dict_dn_sn_header.get(each["rel_dn_sn"]) is None:
                    error_list.append("行标识{}关联交货单{}不存在".format(each["line_id"], each["rel_dn_sn"]))
                elif dict_dn_sn_item.get(each["rel_dn_sn"] + str(each.get("rel_dn_item", 0))) is None:
                    error_list.append("行标识{}关联交货单{}行号{}不存在".format(each["line_id"], each["rel_dn_sn"],
                                                                                each.get("rel_dn_item", 0)))
            if each.get("picking_document", "") != "":
                # 拣配单号检查
                if dict_picking_document.get(each["picking_document"], each.get("batch_item", 0)) is None:
                    error_list.append("行标识{}拣配单号{}不存在".format(each["line_id"], each["picking_document"]))

            if each.get("inv_transfer_order_no", "") != "":
                # 库存调拨单
                if dict_inv_transfer_order.get(each["inv_transfer_order_no"]) is None:
                    error_list.append(
                        "行标识{}库存调拨单{}不存在".format(each["line_id"], each["inv_transfer_order_no"]))
                elif dict_inv_transfer_order_item.get(
                        each["inv_transfer_order_no"] + str(each.get("inv_transfer_order_items", 0))) is None:
                    error_list.append(
                        "行标识{}库存调拨单{}行号{}不存在".format(each["line_id"], each["inv_transfer_order_no"],
                                                                  each.get("inv_transfer_order_items", 0)))

            if each.get("ro_sn", "") != "":
                if dict_ro_sn_data.get(each["ro_sn"] + str(each.get("ro_items", 0))) is None:
                    error_list.append("行标识{}关联预留单{}行号{}不存在".format(each["line_id"], each["ro_sn"],
                                                                                each.get("ro_items", 0)))
            if each.get("rel_so_sn", "") != "":

                if dict_so_sn_data.get(each["rel_so_sn"] + str(each.get("rel_so_items", 0))) is None:
                    error_list.append("行标识{}关联销售订单{}行号{}不存在".format(each["line_id"], each["rel_so_sn"],
                                                                                  each.get("rel_so_items", 0)))
            if each.get("special_inventory_status1", "") == "C" or each.get("special_inventory_status1", "") == "CC":
                # 客户检查
                if each.get("customer_code", "") == "":
                    error_list.append("行标识{}客户编码必输".format(each["line_id"]))
                else:
                    if dict_customer_code_data.get(each["customer_code"]) is None:
                        error_list.append("行标识{}客户编码{}不存在".format(each["line_id"], each["customer_code"]))
            else:
                each["customer_code"] = ""

            if each.get("special_inventory_status1", "") == "S":
                # 销售订单检查
                if each.get("so_sn", "") == "" or each.get("so_items", "") == "":
                    error_list.append("行标识{}销售订单信息必输".format(each["line_id"]))
                else:
                    if dict_so_sn_data.get(each.get("so_sn", "") + str(each.get("so_items", 0))) is None:
                        error_list.append("行标识{}销售订单{}行号{}不存在".format(each["line_id"], each["so_sn"],
                                                                                  each.get("so_items", 0)))
            else:
                each["so_sn"] = ""
                each["so_items"] = 0

            if each.get("special_inventory_status1", "") == "P":
                # 项目编码检查
                if each.get("project_sn", "") == "":
                    error_list.append("行标识{}项目编码必输".format(each["line_id"]))
                    # 项目编码检查待定-----
            else:
                each["project_sn"] = ""

            if each.get("special_inventory_status1", "") == "V" or each.get("special_inventory_status1", "") == "SC":
                # 供应商编码检查
                if each.get("vendor_code", "") == "":
                    error_list.append("行标识{}供应商编码必输".format(each["line_id"]))
                else:
                    if dict_vendor_code_data.get(each["vendor_code"]) is None:
                        error_list.append("行标识{}供应商编码{}不存在".format(each["line_id"], each["vendor_code"]))

                if each["special_inventory_status1"] == "V":
                    if each.get("po_sn", "") != "":
                        # 采购订单检查
                        if dict_po_header.get(each["po_sn"]) is None:
                            error_list.append("行标识{}采购订单{}不存在".format(each["line_id"], each["po_sn"]))
                        else:
                            if dict_po_item.get(each["po_sn"] + str(each.get("po_items", 0))) is None:
                                error_list.append(
                                    "行标识{}采购订单{}行号{}不存在".format(each["line_id"], each["po_sn"],
                                                                            each.get("po_items", 0)))
                else:
                    each["po_sn"] = ""
                    each["po_items"] = 0
            else:
                each["vendor_code"] = ""
                each["po_sn"] = ""
                each["po_items"] = 0

            if each.get("cost_center", "") != "":
                # 成本中心检查
                if dict_cost_center_data.get(each["cost_center"] + each["plant_code"]) is None:
                    error_list.append(
                        "行标识{}成本中心{}在工厂{}对应的公司代码不存在".format(each["line_id"], each["cost_center"],
                                                                                each["plant_code"]))
            if each.get("cost_business_object", "") != "":
                # 成本事项检查
                if dict_cost_business_object_data.get(each["cost_business_object"] + each["plant_code"]) is None:
                    error_list.append(
                        "行标识{}成本事项{}在工厂{}对应的公司代码不存在".format(each["line_id"],
                                                                                each["cost_business_object"],
                                                                                each["plant_code"]))
            if each.get("cost_business_object1", "") != "":
                # 成本事项1检查
                if dict_cost_business_object_data.get(each["cost_business_object1"] + each["plant_code"]) is None:
                    error_list.append(
                        "行标识{}成本事项1{}在工厂{}对应的公司代码不存在".format(each["line_id"],
                                                                                 each["cost_business_object1"],
                                                                                 each["plant_code"]))
            if each.get("profit_center", "") != "":
                # 利润中心检查
                if dict_profit_center_data.get(each["profit_center"] + each["plant_code"]) is None:
                    error_list.append(
                        "行标识{}利润中心{}在工厂{}对应的公司代码不存在".format(each["line_id"], each["profit_center"],
                                                                                each["plant_code"]))
            if each.get("equipment_code", "") != "":
                # 设备ID检查
                if dict_equipment_code_data.get(each["equipment_code"]) is None:
                    error_list.append("行标识{}设备ID{}不存在".format(each["line_id"], each["equipment_code"]))

            # 交易货币
            if each.get("transaction_currency", "") == "":
                if dict_po_header.get(each.get('rel_po_sn')):
                    each["transaction_currency"] = dict_po_header[each.get('rel_po_sn')][0]['currency_code']

            # 检查当前母行是否有对应子行
            if each.get('parent_id', 0) == 0:
                exist = 0
                for child in item:
                    if child['parent_id'] == each['line_id']:
                        exist = 1
                        pass
                if exist == 0:
                    error_list.append(
                        "行标识{}未找到对应的子行".format(each["line_id"]))

    md_header = initialization("t_md_header", db)
    md_item = []
    md_price = []

    # 生成凭证数据
    if not error_list:
        # 单据种类
        md_header["document_category"] = "MDOC"
        # 物料凭证
        md_header["mat_doc_sn"] = ""
        # 年度
        md_header["year"] = head["posting_date"][:4]
        # 过账代码
        md_header["post_code"] = head["post_code"]
        # 凭证日期
        md_header["document_date"] = head["document_date"]
        # 过账日期
        md_header["posting_date"] = head["posting_date"]

        # 汇总唯一号
        md_header["summary_unique_number"] = head.get("summary_unique_number", "")
        # 备注信息1
        md_header["remarks_1"] = head.get("remarks_1", "")
        # 备注信息2
        md_header["remarks_2"] = head.get("remarks_2", "")
        # 供应商交货单
        md_header["vendor_dn"] = head.get("vendor_dn", "")
        # 物料凭证类型
        md_header["material_document_type"] = ""
        # 交易汇率 公司代码 信息
        md_header["company_code"], md_header["exchange_rate"] = get_company_info(item[0]["plant_code"],
                                                                                 item[0]["transaction_currency"],
                                                                                 dict_company)

        if head.get('exchange_rate', 0) != 0:
            md_header["exchange_rate"] = head['exchange_rate']

        # 预留字段
        md_header["reserved1"] = head.get("reserved1", "")
        md_header["reserved2"] = head.get("reserved2", "")
        md_header["reserved3"] = head.get("reserved3", "")
        md_header["reserved4"] = head.get("reserved4", "")
        md_header["reserved5"] = head.get("reserved5", "")
        md_header["reserved6"] = head.get("reserved6", "")
        md_header["reserved7"] = head.get("reserved7", "")
        md_header["reserved8"] = head.get("reserved8", "")
        md_header["reserved9"] = head.get("reserved9", "")
        md_header["reserved10"] = head.get("reserved10", "")

        md_header["create_id"] = user_id
        md_header["update_id"] = user_id

        md_header["ztype"] = head.get('ztype', '')

        if md_header["exchange_rate"] == 0:
            error_list.append("未获取到汇率")

        line_tmp = initialization("t_md_item", db)
        price_tmp = initialization("t_md_price_details", db)

        item_no = 0
        # 行项目设置
        for each in item:
            line = line_tmp.copy()
            price = price_tmp.copy()

            item_no += 1
            # 物料凭证
            line["mat_doc_sn"] = md_header["mat_doc_sn"]
            # 年度
            line["year"] = md_header["year"]
            # 物料凭证信息行号
            line["mat_doc_items"] = item_no
            # 物料凭证行唯一标识
            line["line_id"] = each["line_id"]
            # 凭证行参考唯一标识
            line["parent_id"] = each.get("parent_id", 0)
            # 参考凭证行
            line["ref_item_serial_no"] = line["parent_id"]
            # 自动创建标识
            line["auto_mark"] = 0
            # 移动类型
            line["movement_type"] = each["movement_type"]
            # 物料凭证类型 借贷标识  收发标识  科目修改 业务单据种类
            line, material_document_type, prod_order_mark, wbs_elements_mark, cost_business_object_mark, asset_code1_mark = get_movement_attribute(
                line, line["movement_type"], dict_movement_type)
            if md_header["material_document_type"] == "":
                md_header["material_document_type"] = material_document_type
            if line["debit_credit_mark"] == "":
                error_list.append(
                    "行标识{}未能根据移动类型{}取到借贷标识".format(each["line_id"], each["movement_type"]))
            if line["receipt_consume_mark"] == "":
                error_list.append(
                    "行标识{}未能根据移动类型{}取到收发标识".format(each["line_id"], each["movement_type"]))
            if prod_order_mark == 1:
                if each.get("prodosn", "") == "":
                    error_list.append("行标识{}生产订单必填".format(each["line_id"]))
            if wbs_elements_mark == 1:
                if each.get("wbs_elements", "") == "":
                    error_list.append("行标识{}WBS必填".format(each["line_id"]))
            if cost_business_object_mark == 1:
                if each.get("cost_center", "") == "" and each.get("cost_business_object", "") == "" and each.get(
                        "cost_business_object1", "") == "":
                    error_list.append("行标识{}成本中心/成本事项/成本事项1必填一个".format(each["line_id"]))
            if asset_code1_mark == 1:
                if each.get("asset_code1", "") == "":
                    error_list.append("行标识{}资产卡片必填".format(each["line_id"]))
            # 特殊库存状态1
            line["special_inventory_status1"] = each.get("special_inventory_status1", "")
            # 特殊库存状态2
            line["special_inventory_status2"] = each.get("special_inventory_status2", "")
            # 库存状态
            line["inventory_status"] = get_inventory_status(each["movement_type"], each.get("inventory_status", ""),
                                                            dict_movement_type)
            # 事件类型 物料成本特殊评估标识
            line["transaction_type_code"], line["mat_special_val_mark"] = get_transaction_type_code(
                each["movement_type"], each["plant_code"], each["mat_code"], each.get("rel_po_sn", ""),
                each.get("rel_po_items", 0),
                line["special_inventory_status1"], line["special_inventory_status2"], dict_relation, dict_po_item,
                dict_mat_code)
            if line["transaction_type_code"] == "":
                error_list.append("行标识{}未能根据移动类型{}和采购订单{}信息取到事件类型".format(each["line_id"],
                                                                                                  each["movement_type"],
                                                                                                  each.get("rel_po_sn",
                                                                                                           "")))
            # 工厂代码
            line["plant_code"] = each["plant_code"]
            # 公司代码
            line["company_code"] = md_header["company_code"]
            # 结算公司代码
            line["settle_company_code"] = get_settle_company_code(each["plant_code"], dict_company)
            # 物料编码
            line["mat_code"] = each.get("mat_code", "")
            # 库存地点
            if line["mat_code"] == "" or line["special_inventory_status1"] == "V":
                line["stor_loc_code"] = ""
            else:
                line["stor_loc_code"] = each.get("stor_loc_code", "")
            # 批次号
            line["batch_sn"] = each.get("batch_sn", "")
            # 交易数量
            line["transaction_qty"] = each["transaction_qty"]
            # 交易单位
            line["transaction_uom"] = each["transaction_uom"]
            # 带借贷标识的交易数量
            if line["debit_credit_mark"] == "Cr":
                line["transaction_qty_dc_mark"] = line["transaction_qty"] * -1
            else:
                line["transaction_qty_dc_mark"] = line["transaction_qty"]

            # 基本单位/成本单位/价格控制/评估类/物料组
            line = get_material_uom(line["mat_code"], line["plant_code"], dict_mat_code, line)

            # # 平行数量
            # line["parallel_qty"] = each["parallel_qty"]
            # 平行单位
            line["parallel_uom"] = each.get("parallel_uom", "")

            # 计算基本数量和成本数量
            line = get_other_qty_by_unit(each, line, head['post_code'],
                                         dict_movement_type[each['movement_type']][0]['allow_zero_base_qty'],
                                         dict_movement_type[each['movement_type']][0]['allow_zero_parallel_qty'],
                                         dict_mat_uom_convert)

            if dict_movement_type[each['movement_type']][0]['allow_zero_base_qty'] == 0:
                if line["basic_qty"] <= 0:
                    error_list.append("行标识{}基本数量不能为0".format(each["line_id"]))

            if dict_movement_type[each['movement_type']][0]['allow_zero_parallel_qty'] == 0:
                if line["parallel_qty"] <= 0 and line["parallel_uom"]:
                    error_list.append("行标识{}平行数量不能为0".format(each["line_id"]))

            # 带借贷标识的基本数量
            if line["debit_credit_mark"] == "Cr":
                line["basic_qty_dc_mark"] = line["basic_qty"] * -1
            else:
                line["basic_qty_dc_mark"] = line["basic_qty"]

            # 带借贷标识的成本数量
            if line["debit_credit_mark"] == "Cr":
                line["cost_qty_dc_mark"] = line["cost_qty"] * -1
            else:
                line["cost_qty_dc_mark"] = line["cost_qty"]

            # 带借贷标识的平行数量
            if line["debit_credit_mark"] == "Cr":
                line["parallel_qty_dc_mark"] = line["parallel_qty"] * -1
            else:
                line["parallel_qty_dc_mark"] = line["parallel_qty"]

            # 交易货币
            line["transaction_amount"] = each.get("transaction_amount", 0)
            # 交易货币
            if each.get("transaction_currency", "") == "":
                line["transaction_currency"] = get_company_basic_currency(line["plant_code"], dict_company)
            else:
                line["transaction_currency"] = each["transaction_currency"]
            # 定价单位 定价单位数量 交易金额 交易货币 采购订单供应商
            if line['parent_id'] == 0:
                line = get_po_qty_amount_info(line, each.get("rel_po_sn", ""), each.get("rel_po_items", 0),
                                              dict_po_header,
                                              dict_po_item)
            # 消耗记账 对象标识 价值更新 数量更新
            line = get_movement_label(line, each.get("rel_po_sn", ""), each.get("rel_po_items", 0), dict_movement_type,
                                      dict_mat_code,
                                      dict_po_item, dict_movement_label1, dict_movement_label2, dict_movement_label3)
            if line["consumption_posting_label"] == "":
                error_list.append("行标识{}消耗记账标识不能为空".format(each["line_id"]))
            if line["item_indicator"] == "":
                error_list.append("行标识{}对象标识不能为空".format(each["line_id"]))
            if line["value_update"] == "":
                error_list.append("行标识{}价值更新不能为空".format(each["line_id"]))
            # 关联采购订单
            line["rel_po_sn"] = each.get("rel_po_sn", "")
            # 关联采购订单行
            line["rel_po_items"] = each.get("rel_po_items", 0)
            # 关联采购订单行项目序号
            line["rel_po_component_number"] = each.get("rel_po_component_number", 0)
            # 关联采购订单行序号
            line["rel_po_comp_batch_num"] = each.get("rel_po_comp_batch_num", 0)
            # 关联生产订单组件序号
            line["prodo_component_number"] = each.get("prodo_component_number", '')
            # 生产订单
            line["prodosn"] = each.get("prodosn", "")
            # 关联交货单
            line["rel_dn_sn"] = each.get("rel_dn_sn", "")
            # 关联交货单行号
            line["rel_dn_item"] = each.get("rel_dn_item", 0)
            # 拣配单号
            line["picking_document"] = each.get("picking_document", "")
            # 批次行号
            line["batch_item"] = each.get("batch_item", 0)
            # 关联预留单
            line["ro_sn"] = each.get("ro_sn", "")
            # 关联预留单行
            line["ro_items"] = each.get("ro_items", 0)
            # 关联销售订单
            line["rel_so_sn"] = each.get("rel_so_sn", "")
            # 关联销售订单行项目
            line["rel_so_items"] = each.get("rel_so_items", 0)
            # 关联单据种类 关联单据号 关联行号 原始单据类型 原始单据号 原始单据行号
            line = get_associated_order(md_header, line)
            # 客户编码
            line["customer_code"] = each.get("customer_code", "")
            # 销售订单
            line["so_sn"] = each.get("so_sn", "")
            # 销售订单行项目
            line["so_items"] = each.get("so_items", 0)
            # 库存调拨单
            line['inv_transfer_order_no'] = each.get("inv_transfer_order_no", '')
            # 库存调拨单行
            line['inv_transfer_order_items'] = each.get("inv_transfer_order_items", 0)
            # 项目编号
            line["project_sn"] = each.get("project_sn", "")
            # 供应商编码
            line["vendor_code"] = each.get("vendor_code", "")
            # 采购订单
            line["po_sn"] = each.get("po_sn", "")
            # 采购订单行项目
            line["po_items"] = each.get("po_items", 0)
            # WBS元素
            line["wbs_elements"] = each.get("wbs_elements", "")
            # 成本中心
            line["cost_center"] = each.get("cost_center", "")
            # 成本事项
            line["cost_business_object"] = each.get("cost_business_object", "")
            # 成本事项1
            line["cost_business_object1"] = each.get("cost_business_object1", "")
            # 利润中心
            line["profit_center"] = each.get("profit_center", "")
            # 会计科目
            line["accounting_subjects"] = each.get("accounting_subjects", "")
            # 资产卡片
            line["asset_code1"] = each.get("asset_code1", "")
            # 子资产
            line["asset_code2"] = each.get("asset_code2", "")
            # 设备ID
            line["equipment_code"] = each.get("equipment_code", "")
            # 快递单号
            line["express_delivery"] = each.get("express_delivery", "")
            # 行参考信息1
            line["reference1_item"] = each.get("reference1_item", "")
            # 行参考信息2
            line["reference2_item"] = each.get("reference2_item", "")
            # 行参考信息3
            line["reference3_item"] = each.get("reference3_item", "")
            # 汇总行
            line["summary_line"] = each.get("summary_line", 0)
            # 批次编码校验
            if each.get("mat_code", "") != "":
                line["batch_sn"], each['batch_number'], msg = check_batch_required(line["mat_code"], line["plant_code"],
                                                                                   line["batch_sn"],
                                                                                   line["debit_credit_mark"],
                                                                                   dict_mat_code, dict_mat_batch,
                                                                                   each.get('batch_number', {}),
                                                                                   dict_movement_type[
                                                                                       line['movement_type']][0],
                                                                                       user_id=user_id)
                if msg != "":
                    error_list.append("行标识{}{}".format(each["line_id"], msg))

            # 交易前移动平均价（成本货币）/ 交易前移动平均价（本位币）
            # ---待补充
            # 采购项目类别 / 科目分配类别 / 采购订单数量 / 采购订单单位 / 免费标记 / 返工标记 / 返工类型 / 加工工序
            if line['parent_id'] == 0:
                line = get_po_item_other_info(line, line["rel_po_sn"], line["rel_po_items"], dict_po_item)

            # 质检过账标识 / 质量检验单标识
            line["quality_insp_post_mark"] = each.get("quality_insp_post_mark", 0)
            line["quality_insp_order_mark"], msg = get_quality_inspection_mark(line["mat_code"], line["plant_code"],
                                                                               line["inventory_status"],
                                                                               line["movement_type"],
                                                                               line["debit_credit_mark"],
                                                                               line["quality_insp_post_mark"],
                                                                               dict_mat_code, dict_movement_type,
                                                                               dict_mat_insp)
            if msg != "":
                error_list.append("行标识{}{}".format(each["line_id"], msg))

            # 结批标识
            line["batch_closure_flag"] = each.get("batch_closure_flag", 0)
            if line["batch_closure_flag"] == 0:
                line["batch_closure_flag"] = get_batch_closure_flag(line["rel_po_sn"], line["rel_po_items"],
                                                                    line["rel_po_component_number"],
                                                                    line["rel_po_comp_batch_num"], line["basic_qty"],
                                                                    dict_po_binding)
            # 结批日期
            line["batch_closure_date"] = each.get("batch_closure_date", "")
            if line["batch_closure_date"] == "":
                if line["batch_closure_flag"] == 1:
                    line["batch_closure_date"] = datetime.now().strftime("%Y-%m-%d")

            # 收货完成标记
            line["receipt_completed_flag"] = each.get("receipt_completed_flag", 0)

            # 移动原因
            line["movement_reason"] = each.get("movement_reason", "")

            # 参考凭证年度
            line["rel_document_year"] = each.get("rel_document_year", "")
            # 参考凭证号
            line["rel_document_no"] = each.get("rel_document_no", "")
            # 参考凭证行号
            line["ref_document_mat"] = each.get("ref_document_mat", 0)
            # 前序物料凭证年度
            line["pre_document_year"] = each.get("pre_document_year", "")
            # 前序物料凭证
            line["pre_document_no"] = each.get("pre_document_no", "")
            # 前序物料凭证行号
            line["pre_document_item"] = each.get("pre_document_item", 0)

            # 交易数量检查
            msg = check_if_overcharge(line["rel_po_sn"], line["rel_po_items"], line, item, dict_md_info1, dict_md_info2,
                                      dict_pi_invoice_info, dict_po_item)
            if msg:
                error_list.append(msg)

            # 预留字段
            line["reserved1"] = each.get("reserved1", "")
            line["reserved2"] = each.get("reserved2", "")
            line["reserved3"] = each.get("reserved3", "")
            line["reserved4"] = each.get("reserved4", "")
            line["reserved5"] = each.get("reserved5", "")
            line["reserved6"] = each.get("reserved6", "")
            line["reserved7"] = each.get("reserved7", "")
            line["reserved8"] = each.get("reserved8", "")
            line["reserved9"] = each.get("reserved9", "")
            line["reserved10"] = each.get("reserved10", "")

            # 批次属性
            # batch_number = {}
            # line["batch_number"] = {}
            #
            # batch_number["production_date"] = each["batch_number"].get("production_date", "")
            # batch_number["maturity_date"] = each["batch_number"].get("maturity_date", "")
            # batch_number["vendor_code"] = each["batch_number"].get("vendor_code", "")
            # batch_number["vendor_batch"] = each["batch_number"].get("vendor_batch", "")
            # batch_number["receive_date"] = each["batch_number"].get("receive_date", "")
            # batch_number["lot_no"] = each["batch_number"].get("lot_no", "")
            # batch_number["wafer_id"] = each["batch_number"].get("wafer_id", "")
            # batch_number["mfg_date_wafer"] = each["batch_number"].get("mfg_date_wafer", "")
            # batch_number["vendor_lot_no"] = each["batch_number"].get("vendor_lot_no", "")
            # batch_number["mfg_date_assy"] = each["batch_number"].get("mfg_date_assy", "")
            # batch_number["packing_seal_date"] = each["batch_number"].get("packing_seal_date", "")
            # batch_number["date_code"] = each["batch_number"].get("date_code", "")
            # batch_number["packing_id"] = each["batch_number"].get("packing_id", "")
            # batch_number["bin_grade"] = each["batch_number"].get("bin_grade", "")
            # batch_number["grade"] = each["batch_number"].get("grade", "")
            # batch_number["batch_type"] = each["batch_number"].get("batch_type", "")
            # batch_number["receive_data"] = each["batch_number"].get("receive_data", "")
            # batch_number["cp_vendor"] = each["batch_number"].get("cp_vendor", "")
            # batch_number["bin"] = each["batch_number"].get("bin", "")
            # batch_number["grade1"] = each["batch_number"].get("grade1", "")
            # batch_number["grade2"] = each["batch_number"].get("grade2", "")
            # batch_number["grade3"] = each["batch_number"].get("grade3", "")
            # batch_number["extended_batch_date1"] = each["batch_number"].get("extended_batch_date1", "")
            # batch_number["extended_batch_date2"] = each["batch_number"].get("extended_batch_date2", "")
            # batch_number["extended_batch_date3"] = each["batch_number"].get("extended_batch_date3", "")
            # batch_number["extended_batch_attributes1"] = each["batch_number"].get("extended_batch_attributes1", "")
            # batch_number["extended_batch_attributes2"] = each["batch_number"].get("extended_batch_attributes2", "")
            # batch_number["extended_batch_attributes3"] = each["batch_number"].get("extended_batch_attributes3", "")
            # batch_number["item"] = edit_batch_attribute(each["batch_number"].get("item", []))
            # batch_number["create_id"] = user_id
            # batch_number["update_id"] = user_id
            # line["batch_number"] = batch_number

            line["batch_number"] = each.get('batch_number', {})
            line["batch_number"]["create_id"] = user_id
            line["batch_number"]["update_id"] = user_id

            line["create_id"] = user_id
            line["update_id"] = user_id

            md_item.append(line.copy())

            # 价格明细表
            # 物料凭证
            price["mat_doc_sn"] = md_header["mat_doc_sn"]
            # 年度
            price["year"] = md_header["year"]
            # 物料凭证信息行号
            price["mat_doc_items"] = item_no
            md_price = get_po_price(md_price, line, price, user_id, dict_price_data)

    if not error_list:
        # 库存校验
        msg_list = get_inventory_qty(md_item, md_header["posting_date"], dict_plant_storage, db)
        print(f'msg_list库存校验-------{msg_list}')
        if msg_list:
            error_list.extend(msg_list)

    if error_list:
        code = 500
        msg = "存在错误,请检查"
    else:
        code = 200
        msg = "检查无误"

        batch_begin = time.time()
        # 批次继承
        md_item = batch_inherit7(md_item, dict_po_header, db)
        print("批次继承耗时：", time.time() - batch_begin)

    return code, msg, error_list, md_header, md_item, md_price


def batch_inherit7(item, dict_po_header, db):
    print("=" * 80)
    print("【进入函数】batch_inherit7 批次继承策略处理")
    print(f"传入的 item 数量：{len(item)}")
    print(f"传入的采购订单头字典：{dict_po_header}")

    movement_type = []
    for each in item:
        movement_type.append(each['movement_type'])
    print(f"\n【提取移动类型】movement_type = {movement_type}")

    # 获取批次策略信息
    print("\n【开始拼接批次策略查询SQL】")
    query_sql = """
        SELECT
            a.`batch_inheritance_type`,
            a.`movement_type`,
            a.`po_type`,
            b.`field_code`,
            b.`multiple_data_rule`,
            b.`priority_code`,
            b.`is_update`
        FROM
            `t_batch_inheritance_strategy_alloc` as a 
        JOIN
            `t_batch_inheritance_strategy` as b
        ON
            a.`batch_inheritance_strategy` = b.`batch_inheritance_strategy`
        WHERE
            a.`movement_type` in ('{}')
        AND
            a.`activation_flag` = 1
    """.format("','".join(movement_type))
    print(f"执行的SQL：\n{query_sql}")

    data = db.query_sql(query_sql)
    print(f"\n【SQL查询结果】获取到批次策略数据条数：{len(data) if data else 0}")
    print(f"批次策略原始数据：{data}")

    if not data:
        print("\n【无批次策略配置】直接返回原始 item")
        print("=" * 80)
        return item

    # 按采购订单类型+移动类型分组
    print("\n【开始按 po_type + movement_type 分组】")
    dict_batch_config = {}
    for each in data:
        key = each["po_type"] + each["movement_type"]
        if key not in dict_batch_config:
            dict_batch_config[key] = []
            dict_batch_config[key].append(each)
        else:
            dict_batch_config[key].append(each)
    print(f"分组后的批次策略配置 dict_batch_config 键：{list(dict_batch_config.keys())}")
    print(f"完整配置字典：{dict_batch_config}")

    po_sn = []
    mat_code = []
    batch_sn = []

    dict_item = {}
    print("\n【遍历 item 提取关键字段并构建 dict_item 分组】")
    for idx, each in enumerate(item):
        print(f"\n--- 处理第 {idx+1} 个 item ---")
        print(f"当前 item 信息：po_sn={each['rel_po_sn']}, batch_sn={each['batch_sn']}, mat_code={each['mat_code']}")

        if each['rel_po_sn']:
            po_sn.append(each['rel_po_sn'])
        if each['batch_sn']:
            mat_code.append(each['mat_code'])
            batch_sn.append(each['batch_sn'])

        key = each['rel_po_sn'] + str(each['rel_po_items']) + str(each['rel_po_component_number'])
        print(f"构建 dict_item 分组 key：{key}")

        if key not in dict_item:
            dict_item[key] = []
            dict_item[key].append(each)
        else:
            dict_item[key].append(each)

    print(f"\n【提取结果】po_sn={po_sn}")
    print(f"mat_code={mat_code}")
    print(f"batch_sn={batch_sn}")
    print(f"构建完成的 dict_item 分组数量：{len(dict_item)}")
    print(f"dict_item 所有key：{list(dict_item.keys())}")

    print("\n【调用 get_po_component2 获取采购订单组件】")
    dict_po_component = get_po_component2(po_sn, db)
    print(f"get_po_component2 返回结果数量：{len(dict_po_component)}")
    print(f"订单组件字典：{dict_po_component}")

    print("\n【调用 get_batch_attribute_mult 获取批次属性】")
    dict_batch_number = get_batch_attribute_mult(mat_code, batch_sn, db)
    print(f"get_batch_attribute_mult 返回批次属性数量：{len(dict_batch_number)}")
    print(f"批次属性字典：{dict_batch_number}")

    print("\n" + "="*50)
    print("【开始遍历：找到父行 → 计算批次 → 赋值给子行】")

    # ====================== 核心修复开始 ======================
    # 1. 先遍历找到父行，计算出应该继承的批次属性
    parent_batch_map = {}  # key: 父行line_id, value: 计算好的batch_number
    parent_movement_map = {}  # 保存父行的movement_type

    for each in item:
        if each['parent_id'] == 0:
            print(f"\n✅ 找到父行 line_id={each['line_id']}，开始计算继承批次")
            batch_attr = []
            key = each["rel_po_sn"] + str(each["rel_po_items"])

            po_component = []
            if dict_po_component.get(key, []):
                for c in dict_po_component[key]:
                    # 这里也帮你去掉了主材限制，确保能拿到数据
                    # if c['main_material_mark'] == 1:
                    po_component.append(c)
            print(f"筛选出【主材】组件数量：{len(po_component)}")
            print(f"主材组件：{po_component}")

            # 收集批次属性
            for i in po_component:
                key = i['po_sn'] + str(i['po_items']) + str(i['rel_po_component_number'])
                if dict_item.get(key):
                    for j in dict_item[key]:
                        k = j['mat_code'] + j['batch_sn']
                        if k in dict_batch_number:
                            batch_attr += dict_batch_number[k]

            print(f"父行计算完成 → 批次属性：{batch_attr}")

            # 匹配策略并生成最终批次
            po_type = dict_po_header[each['rel_po_sn']][0]['po_type']
            config_key = str(po_type) + each['movement_type']
            new_batch = set_batch_number_attribute(dict_batch_config, config_key, batch_attr, each['batch_number'])

            # 保存：父行ID → 计算好的批次号
            parent_batch_map[each['line_id']] = new_batch
            parent_movement_map[each['line_id']] = each['movement_type']
            print(f"✅ 父行 {each['line_id']} 计算完成，待赋值给子行")

    # 2. 遍历子行，把父行的批次号赋值给子行
    print("\n" + "-"*50)
    print("【开始给子行赋值批次号】")
    for each in item:
        if each['parent_id'] != 0:
            parent_id = each['parent_id']
            if parent_id in parent_batch_map:
                print(f"\n🎯 子行 line_id={each['line_id']} 找到父行 {parent_id}")
                print(f"赋值前 batch_number: {each['batch_number']}")
                # 把子行的batch_number替换成父行计算好的
                each['batch_number'] = parent_batch_map[parent_id]
                print(f"✅ 赋值后 batch_number: {each['batch_number']}")
            else:
                print(f"\n⚠️ 子行 line_id={each['line_id']} 未找到父行配置")
    # ====================== 核心修复结束 ======================

    print("\n" + "="*80)
    print("【函数执行完成】批次已正确赋值给子行")
    print(f"返回 item 数量：{len(item)}")
    print("="*80)
    return item

def set_batch_number_attribute(dict_batch_config, key, batch_attr, batch_number):
    if dict_batch_config.get(key):
        for each in dict_batch_config[key]:

            for key, value in batch_number.items():
                if key != 'item':
                    # 批次继承时，进行属性替换
                    if each['priority_code'] == '2' or (each['priority_code'] == '1' and not value):
                        if key == each['field_code']:
                            merge_values = []
                            for attr in batch_attr:
                                # 处理规则
                                if value == "":
                                    value = attr[key]
                                    continue
                                # 按最大值
                                if each['multiple_data_rule'] == '1':
                                    if value <= attr[key]:
                                        value = attr[key]
                                # 按最小值
                                if each['multiple_data_rule'] == '2':
                                    if value >= attr[key]:
                                        value = attr[key]
                                # 合并
                                if each['multiple_data_rule'] == '3' and each['priority_code'] != '2':
                                    if value:
                                        value += ',{}'.format(attr[key])
                                    else:
                                        value = attr[key]
                                # 优先级为2多数据源处理规则为3不合并以继承批次为准
                                if each['multiple_data_rule'] == '3' and each['priority_code'] == '2':
                                    val = attr[key]
                                    if val:  # 过滤空值
                                        merge_values.append(str(val))
                                # 且
                                if each['multiple_data_rule'] == '4':
                                    if value == 1 and attr[key] == 1:
                                        value = 1
                                    else:
                                        value = 0
                                # 或
                                if each['multiple_data_rule'] == '5':
                                    if value == 1 or attr[key] == 1:
                                        value = 1
                                    else:
                                        value = 0
                            # 合并的场合去重
                            if each['multiple_data_rule'] == '3' and each['priority_code'] == '2':
                                # 去重 + 拼接
                                value = ','.join(dict.fromkeys(merge_values))

                            # 合并的场合去重（非优先级2）
                            if each['multiple_data_rule'] == '3' and each['priority_code'] != '2':
                                value = ','.join(dict.fromkeys(value.split(',')))

                            batch_number[key] = value

                else:
                    for i in batch_number['item']:
                        if i['field_code'] == each['field_code']:
                            if each['priority_code'] == '2' or (each['priority_code'] == '1' and not i['field_value']):
                                if i['field_type'] == 'decimal' or i['field_type'] == 'date' or i[
                                    'field_type'] == 'time' or i['field_type'] == 'int':
                                    for attr in batch_attr:
                                        # 处理规则
                                        for j in attr['item']:
                                            if j['field_code'] == i['field_code']:
                                                if i['field_value'] == "":
                                                    if i['field_mark'] == '1':
                                                        i['field_value'] = j['field_value']
                                                        continue
                                                    else:
                                                        i['field_value_from'] = j['field_value_from']
                                                        i['field_value_to'] = j['field_value_to']
                                                        continue
                                                # 按最大值
                                                if each['multiple_data_rule'] == '1':
                                                    if i['field_mark'] == '1':
                                                        if i['field_value'] <= j['field_value']:
                                                            i['field_value'] = j['field_value']
                                                    else:
                                                        if i['field_value_from'] <= j['field_value_from']:
                                                            i['field_value_from'] = j['field_value_from']
                                                        if i['field_value_to'] <= j['field_value_to']:
                                                            i['field_value_to'] = j['field_value_to']
                                                # 按最小值
                                                if each['multiple_data_rule'] == '2':
                                                    if i['field_mark'] == '1':
                                                        if i['field_value'] >= j['field_value']:
                                                            i['field_value'] = j['field_value']
                                                    else:
                                                        if i['field_value_from'] >= j['field_value_from']:
                                                            i['field_value_from'] = j['field_value_from']
                                                        if i['field_value_to'] >= j['field_value_to']:
                                                            i['field_value_to'] = j['field_value_to']

    return batch_number


def get_po_component(po_sn, db):
    query_sql = """
        SELECT
            `po_sn`,
            `po_items`,
            `rel_po_component_number`,
            `component_code` as `mat_code`,
            `main_material_mark`
        FROM
            `t_po_component`
        WHERE
            `po_sn` in ('{}')
    """.format("','".join(po_sn))
    data = db.query_sql(query_sql)

    dict_po_component = {}
    for each in data:
        key = each["po_sn"] + str(each["po_items"]) + str(each["rel_po_component_number"])
        if key not in dict_po_component:
            dict_po_component[key] = []
            dict_po_component[key].append(each)
        else:
            dict_po_component[key].append(each)

    return dict_po_component


def get_po_component2(po_sn, db):
    query_sql = """
        SELECT
            `po_sn`,
            `po_items`,
            `rel_po_component_number`,
            `component_code` as `mat_code`,
            `main_material_mark`
        FROM
            `t_po_component`
        WHERE
            `po_sn` in ('{}')
    """.format("','".join(po_sn))
    data = db.query_sql(query_sql)

    dict_po_component = {}
    for each in data:
        key = each["po_sn"] + str(each["po_items"])
        if key not in dict_po_component:
            dict_po_component[key] = []
            dict_po_component[key].append(each)
        else:
            dict_po_component[key].append(each)

    return dict_po_component


def get_batch_closure_flag(po_sn, po_items, rel_po_component_number, rel_po_comp_batch_num, basic_qty, dict_po_binding):
    # 采购订单组件批次表t_po_batch_binding中的组件消耗数量（基本单位）等于已分配数量，则更新结批标识closure_flag为1
    # query_sql = """
    #     SELECT
    #         allocated_qty,
    #         deducted_quantity_base
    #     FROM
    #         t_po_batch_binding
    #     WHERE
    #         po_sn = '{}'
    #     AND po_items = '{}'
    #     AND rel_po_component_number = '{}'
    #     AND rel_po_comp_batch_num = '{}'
    #     LIMIT 1
    # """.format(po_sn, po_items, rel_po_component_number, rel_po_comp_batch_num)
    # data = db.query_sql(query_sql)

    key = po_sn + str(po_items) + str(rel_po_component_number) + str(rel_po_comp_batch_num)
    if dict_po_binding.get(key):
        item = dict_po_binding[key][0]
        if item["allocated_qty"] == item["deducted_quantity_base"] + basic_qty:
            return 1
    return 0


# 校验组评估物料
def check_if_valgroup_value_exist(po_sn, po_items, mat_code, plant_code, dict_valgroup_value):
    # 判断物料编码是否和采购订单行项目物料一致
    # 不一致则判断采购订单行项目物料编码是否存在组评估物料,不存在报错
    # query_sql = """
    #     SELECT
    #         i.mat_code,
    #         c.valgroup_value
    #     FROM
    #         t_po_item AS i
    #         JOIN t_mmd_material_cost_data AS c ON c.mat_code = i.mat_code
    #     WHERE
    #         i.po_sn = '{}'
    #     AND i.po_items = '{}'
    #     AND c.plant_code = '{}'
    #     LIMIT 1
    # """.format(po_sn, po_items, plant_code)
    # data = db.query_sql(query_sql)
    key = po_sn + str(po_items) + plant_code
    if dict_valgroup_value.get(key):
        item = dict_valgroup_value[key][0]
        if item["mat_code"] == mat_code:
            return False
        else:
            if item["valgroup_value"] != "":
                return False
            else:
                return True

    return False


# 正式过账代码4
def post_data_postcode4(user_id, md_header, md_item, md_price, db):
    code = 0
    msg = ""
    mat_doc_sn = ""
    year = ""
    error_list = []

    try:
        mat_code = md_item[0]["mat_code"]
        batch_sn = md_item[0]["batch_sn"]
        lock_key = f"LOCK_{mat_code}_{batch_sn}"
    except:
        lock_key = f"LOCK_USER_{user_id}"
    try:
        # 锁库存
        code, msg = lock_data(md_item, LockAction.lock, lock_key)
        if code != 200:
            error_list.append(msg)
            raise Exception(msg)

        # 调用c物料凭证会计引擎接口
        input = json.dumps([{"header": md_header, "items": md_item, "details": md_price}])
        print(input)
        sh = SystemHelper()

        c_begin = time.time()
        output = json.loads(sh.execOperator("OnConsumeMat", input)["data"])
        print("调用C耗时： ", time.time() - c_begin)

        print(output)
        if output["result"] == 0:
            if "data" in output:
                code = 200
                msg = "执行成功"
                if output["data"][0]["status"] == "E":
                    code = 500
                    msg = output["data"][0]["msg"]
                else:
                    code = 200
                    msg = output["data"][0]["msg"]
                    mat_doc_sn = output["data"][0]["mat_doc_sn"]
                    year = output["data"][0]["year"]
                    msg = "过账成功,物料凭证:{} 年度{}".format(mat_doc_sn, year)
            else:
                code = 500
                msg = output.get("msg", "会计引擎异常")
        else:
            code = 500
            msg = output["msg"]

    except Exception as e:
        if not error_list:
            error_list.append(str(e))
        code = 500
        msg = "存在错误,请检查"

    finally:

        code1, msg1 = lock_data(md_item, LockAction.unlock, lock_key)

    return code, msg, error_list, mat_doc_sn, year


# 检查过账代码4的参数
def check_data_postcode4(user_id, head, item, db):
    code = 200
    msg = ""
    error_list = []

    # 增强 -- 检验前
    code, msg, error_list, head, item = before_check(user_id, head, item)
    if code != 200:
        return code, msg, error_list, [], [], []

    dict_movement_type = {}
    movement_type = []
    plant_code = []
    plant_code_data = []
    dict_plant_storage = {}
    movement_special_inventory_status1 = []
    movement_special_inventory_status2 = []
    mat_code = []
    dict_mat_code = {}
    dict_mat_code_cost = {}
    po_sn = []
    dict_po_header = {}
    dict_po_item = {}
    dict_po_binding = {}
    prodosn = []
    dict_prodosn_data = {}
    dn_sn = []
    dict_dn_sn_header = {}
    dict_dn_sn_item = {}
    picking_document = []
    dict_picking_document = {}
    procure_dn_sn = []
    dict_procure_dn_sn_data = {}
    ro_sn = []
    dict_ro_sn_data = {}
    so_sn = []
    dict_so_sn_data = {}
    customer_code = []
    dict_customer_code_data = {}
    vendor_code = []
    dict_vendor_code_data = {}
    cost_center = []
    dict_cost_center_data = {}
    cost_business_object = []
    dict_cost_business_object_data = {}
    profit_center = []
    dict_profit_center_data = {}
    equipment_code = []
    dict_equipment_code_data = {}
    dict_company = {}
    dict_relation = {}
    dict_relation2 = {}
    dict_movement_label1 = {}
    dict_movement_label2 = {}
    dict_movement_label3 = {}
    dict_mat_batch = {}
    batch = []
    dict_mat_insp = {}
    dict_price_data = {}
    dict_inventory_status = {}
    inv_transfer_order_no = []
    dict_inv_transfer_order = {}
    dict_inv_transfer_order_item = {}

    # 性能优化
    for each in item:
        # 移动类型
        if each.get("movement_type", "") != "":
            movement_type.append(each['movement_type'])
        # 工厂
        if each.get("plant_code", "") != "":
            plant_code.append(each['plant_code'])

        # 物料编码
        if each.get("mat_code", "") != "":
            mat_code.append(each['mat_code'])

        # 采购订单
        if each.get("rel_po_sn", '') != '':
            po_sn.append(each['rel_po_sn'])
        if each.get('po_sn', '') != '':
            po_sn.append(each['po_sn'])

        # 生产订单
        if each.get('prodosn', '') != '':
            prodosn.append(each['prodosn'])

        # 交货单
        if each.get('rel_dn_sn', '') != '':
            dn_sn.append(each['rel_dn_sn'])

        # 拣配单
        if each.get('picking_document', '') != '':
            picking_document.append(each['picking_document'])

        # 采购交货单
        if each.get('rel_procure_dn_sn', '') != '':
            procure_dn_sn.append(each['rel_procure_dn_sn'])

        # 预留
        if each.get('ro_sn', '') != '':
            ro_sn.append(each['ro_sn'])

        # 销售订单
        if each.get('rel_so_sn', '') != '':
            so_sn.append(each['rel_so_sn'])
        if each.get('so_sn', '') != '':
            so_sn.append(each['so_sn'])

        # 客户
        if each.get('customer_code', '') != '':
            customer_code.append(each['customer_code'])

        # 供应商
        if each.get('vendor_code', '') != '':
            vendor_code.append(each['vendor_code'])

        # 成本中心
        if each.get('cost_center', '') != '':
            cost_center.append(each['cost_center'])

        # 成本事项
        if each.get('cost_business_object', '') != '':
            cost_business_object.append(each['cost_business_object'])
        if each.get('cost_business_object1', '') != '':
            cost_business_object.append(each['cost_business_object1'])

        # 利润中心
        if each.get('profit_center', '') != '':
            profit_center.append(each['profit_center'])

        # 设备
        if each.get('equipment_code', '') != '':
            equipment_code.append(each['equipment_code'])

        # 批次
        if each.get('batch_sn', '') != '':
            batch.append(each['batch_sn'])

        # 接收物料
        if each.get("rcv_mat_code", "") != "":
            mat_code.append(each['rcv_mat_code'])

        # 接收批次
        if each.get("rcv_batch_sn", "") != "":
            batch.append(each['rcv_batch_sn'])

        # 接收工厂
        if each.get("rcv_plant_code", "") != "":
            plant_code.append(each['rcv_plant_code'])

        # 接收客户
        if each.get('rcv_customer_code', '') != '':
            customer_code.append(each['rcv_customer_code'])

        # 接收供应商
        if each.get('rcv_vendor_code', '') != '':
            vendor_code.append(each['rcv_vendor_code'])

        # 接收销售订单
        if each.get('rcv_so_sn', '') != '':
            so_sn.append(each['rcv_so_sn'])

        # 接收采购订单
        if each.get("rcv_po_sn", '') != '':
            po_sn.append(each['rcv_po_sn'])

        # 库存调拨单
        if each.get("inv_transfer_order_no", "") != '':
            inv_transfer_order_no.append(each['inv_transfer_order_no'])

    data_begin = time.time()

    # 获取移动类型属性
    dict_movement_type = get_movement_type_info(movement_type, db)
    # 获取工厂
    plant_code_data = get_plant_code_data(plant_code, db)
    # 获取工厂对应库存地点
    dict_plant_storage = get_plant_storage(plant_code, db)
    # 获取移动类型对应特殊库存状态
    movement_special_inventory_status1, movement_special_inventory_status2, dict_relation, dict_relation2 = get_movement_special_inventory_status(
        movement_type, db)
    # 获取物料主数据信息
    dict_mat_code = get_mat_code_info(mat_code, plant_code, db)
    # 获取物料成本视图
    dict_mat_code_cost = get_mat_code_cost_info(mat_code, plant_code, db)
    # 获取物料单位换算关系
    dict_mat_uom_convert = get_mat_uom_convert(mat_code, db)
    # 获取采购订单抬头信息
    dict_po_header = get_po_header(po_sn, db)
    # 获取采购订单行项目信息
    dict_po_item = get_po_item(po_sn, db)
    # 获取批次组件表
    dict_po_component = get_po_component(po_sn, db)
    # 获取采购订单批次绑定表
    dict_po_binding = get_po_batch_binding(po_sn, db)
    # 获取生产订单
    dict_prodosn_data = get_prodosn_data(prodosn, db)
    # 获取交货单抬头信息
    dict_dn_sn_header = get_dn_header(dn_sn, db)
    # 获取交货单行项目信息
    dict_dn_sn_item = get_dn_sn_item(dn_sn, db)
    # 获取拣配单信息
    dict_picking_document = get_picking_document_info(picking_document, db)
    # 获取采购交货单信息
    # dict_procure_dn_sn_data = get_procure_dn_sn_info(procure_dn_sn, db)
    # 获取预留单信息
    dict_ro_sn_data = get_ro_sn_info(ro_sn, db)
    # 获取销售订单信息
    dict_so_sn_data = get_so_sn_info(so_sn, db)
    # 获取客户信息
    dict_customer_code_data = get_customer_code_info(customer_code, db)
    # 获取供应商信息
    dict_vendor_code_data = get_vendor_code_info(vendor_code, db)
    # 获取成本中心
    dict_cost_center_data = get_cost_center_info(cost_center, db)
    # 获取成本事项
    dict_cost_business_object_data = get_cost_business_object_info(cost_business_object, db)
    # 利润中心
    dict_profit_center_data = get_profit_center_info(profit_center, db)
    # 获取设备主数据信息
    dict_equipment_code_data = get_equipment_code_info(equipment_code, db)
    # 按工厂获取公司信息
    dict_company = get_company_info_by_plant(plant_code, db)
    # 获取移动类型配置信息
    dict_movement_label1, dict_movement_label2, dict_movement_label3 = get_movement_label_info(movement_type, db)
    # 获取物料批次信息
    dict_mat_batch = get_mat_code_and_batch(mat_code, batch, db)
    # 获取物料质检信息
    dict_mat_insp = get_mat_insp_info(mat_code, plant_code, db)
    # 获取采购订单价格明细
    # dict_price_data = get_po_price_data(po_sn, db)
    # 获取库存状态
    dict_inventory_status = get_all_inventory_status(db)
    # 获取库存调拨单
    dict_inv_transfer_order = get_inv_transfer_order(inv_transfer_order_no, db)
    # 获取库存调拨单行
    dict_inv_transfer_order_item = get_inv_transfer_order_item(inv_transfer_order_no, db)

    print("取值耗时: ", time.time() - data_begin)

    check_begin = time.time()
    for each in item:
        # 必输校验
        # 行唯一标识校验
        if each.get("line_id", "") == "":
            error_list.append("行唯一标识必输")
            continue
        # 移动类型校验
        if each.get("movement_type", "") == "":
            error_list.append("行标识{}移动类型必输".format(each["line_id"]))
        # 物料编码
        if each.get("mat_code", "") == "":
            error_list.append("行标识{}物料编码必输".format(each["line_id"]))
        # 交易数量
        if Decimal(each.get("transaction_qty", 0)) <= 0:
            if dict_movement_type.get(each.get('movement_type', '')):
                if dict_movement_type[each['movement_type']][0]['allow_zero_base_qty'] == 0:
                    error_list.append("行标识{}交易数量必须大于0".format(each["line_id"]))
        # 交易单位
        if each.get("transaction_uom", "") == "":
            error_list.append("行标识{}交易单位必输".format(each["line_id"]))
        # 工厂代码
        if each.get("plant_code", "") == "":
            error_list.append("行标识{}工厂代码必输".format(each["line_id"]))
        # 接收工厂代码
        if each.get("rcv_plant_code", "") == "":
            error_list.append("行标识{}接收工厂代码必输".format(each["line_id"]))
        # 接收库存地点
        if each.get("rcv_stor_loc_code", "") == "":
            each["rcv_stor_loc_code"] = each.get("stor_loc_code", "")
        # 接收物料编码
        if each.get("rcv_mat_code", "") == "":
            error_list.append("行标识{}接收物料编码必输".format(each["line_id"]))
        # 库存状态
        if each.get("inventory_status", "") == "" and each.get("mat_code", "") != "":
            error_list.append("行标识{}库存状态必输".format(each["line_id"]))
        # 库存地点
        if each.get("mat_code", "") != "" and each["special_inventory_status1"] != 'V':
            if each["stor_loc_code"] == "":
                error_list.append("行标识{}库存地点必输".format(each["line_id"]))

        # 接收库存状态
        if each.get("rcv_inventory_status", "") == "":
            error_list.append("行标识{}接收库存状态必输".format(each["line_id"]))

        # 检查库存调拨单行是否允许货物移动
        if each.get('inv_transfer_order_no', '') and each.get('inv_transfer_order_items', 0):
            key = each['inv_transfer_order_no'] + str(each['inv_transfer_order_items'])
            inv_item = dict_inv_transfer_order_item.get(key)
            if inv_item and inv_item[0].get('issuing_enabled_flag', 0) != 1:
                error_list.append("行标识{}调拨单{}行{}不允许货物移动".format(
                    each['line_id'],
                    each['inv_transfer_order_no'],
                    each['inv_transfer_order_items']
                ))
                continue

        # 存在性校验
        if not error_list:
            # 移动类型校验
            if dict_movement_type.get(each["movement_type"]) is None:
                error_list.append("行标识{}移动类型{}不存在".format(each["line_id"], each["movement_type"]))
            else:
                if dict_movement_type[each['movement_type']][0]['post_code'] != head["post_code"]:
                    error_list.append("行标识{}移动类型{}不适用过账码{}".format(each["line_id"], each["movement_type"],
                                                                                head["post_code"]))
            # 工厂代码校验
            if each["plant_code"] not in plant_code_data:
                error_list.append("行标识{}工厂代码{}不存在".format(each["line_id"], each["plant_code"]))
            if each["rcv_plant_code"] not in plant_code_data:
                error_list.append("行标识{}接收工厂代码{}不存在".format(each["line_id"], each["rcv_plant_code"]))
            # 库存地点校验
            if each.get("stor_loc_code", "") != "":
                # if not check_if_stor_loc_code_exists(each["stor_loc_code"]):
                #     error_list.append("行标识{}库存地点{}不存在".format(each["line_id"], each["stor_loc_code"]))
                # else:
                if dict_plant_storage.get(each["plant_code"] + each["stor_loc_code"]) is None:
                    error_list.append(
                        "行标识{}在工厂{}下库存地点{}未分配".format(each["line_id"], each["plant_code"],
                                                                    each["stor_loc_code"]))
            if each.get("rcv_stor_loc_code", "") != "":
                # if not check_if_stor_loc_code_exists(each["stor_loc_code"]):
                #     error_list.append("行标识{}库存地点{}不存在".format(each["line_id"], each["stor_loc_code"]))
                # else:
                if dict_plant_storage.get(each["rcv_plant_code"] + each["rcv_stor_loc_code"]) is None:
                    error_list.append(
                        "行标识{}在接收工厂{}下接收库存地点{}未分配".format(each["line_id"], each["rcv_plant_code"],
                                                                            each["rcv_stor_loc_code"]))
            # 特殊库存状态1校验
            if each.get("special_inventory_status1", "") != "":
                if each["movement_type"] + each["special_inventory_status1"] not in movement_special_inventory_status1:
                    error_list.append(
                        "行标识{}在移动类型{}下特殊库存标识1{}未分配".format(each["line_id"], each["movement_type"],
                                                                             each["special_inventory_status1"]))
            # 特殊库存状态2校验
            if each.get("special_inventory_status2", "") != "":
                if each["movement_type"] + each["special_inventory_status2"] not in movement_special_inventory_status2:
                    error_list.append(
                        "行标识{}在移动类型{}下特殊库存标识2{}未分配".format(each["line_id"], each["movement_type"],
                                                                             each["special_inventory_status2"]))
            # 库存状态
            if each.get("inventory_status", "") != "":
                if dict_inventory_status.get(each["inventory_status"]) is None:
                    error_list.append("行标识{}库存状态{}不存在".format(each["line_id"], each["inventory_status"]))
            if each.get("rcv_inventory_status", "") != "":
                if not check_if_inventory_status_exists(each["rcv_inventory_status"],db):
                    error_list.append(
                        "行标识{}接收库存状态{}不存在".format(each["line_id"], each["rcv_inventory_status"]))
            # 物料状态检查
            if each.get("mat_code", "") != "":
                key = each["mat_code"] + each["plant_code"]
                if dict_mat_code.get(key) is None:
                    error_list.append("行标识{}物料编码{}在工厂{}不存在".format(each["line_id"], each["mat_code"], each["plant_code"]))
                else:
                    mat_info = dict_mat_code[key][0]
                    if mat_info.get('deleted_mark', 0) == 1 or mat_info.get('lock_flag', 0) == 1:
                        error_list.append("行标识{}物料编码{}已删除或锁定".format(each["line_id"], each["mat_code"]))
                    elif mat_info.get('value_update', 0) == 1:
                        if dict_mat_code_cost.get(key) is None:
                            error_list.append("行标识{}物料编码{}成本视图未扩".format(each["line_id"], each["mat_code"]))

            if each.get("rcv_mat_code", "") != "":
                key = each["rcv_mat_code"] + each["rcv_plant_code"]
                if dict_mat_code.get(key) is None:
                    error_list.append(
                        "行标识{}接收物料编码{}在工厂{}不存在".format(each["line_id"], each["rcv_mat_code"], each["rcv_plant_code"]))
                else:
                    mat_info = dict_mat_code[key][0]
                    if mat_info.get('deleted_mark', 0) == 1 or mat_info.get('lock_flag', 0) == 1:
                        error_list.append(
                            "行标识{}接收物料编码{}已删除或锁定".format(each["line_id"], each["rcv_mat_code"]))
                    elif mat_info.get('value_update', 0) == 1:
                        if dict_mat_code_cost.get(key) is None:
                            error_list.append(
                                "行标识{}接收物料编码{}成本视图未扩".format(each["line_id"], each["rcv_mat_code"]))

            # # 采购订单状态检查
            # msg = check_po_status(each["rel_po_sn"])
            # if msg != "":
            #     error_list.append("行标识{}{}".format(each["line_id"]), msg)
            # else:
            #     # 采购订单行检查
            #     msg = check_po_item_status(each["rel_po_sn"], each["rel_po_items"])
            # if msg != "":
            #     error_list.append("行标识{}{}".format(each["line_id"]), msg)

            if each.get("rel_po_component_number", 0) != 0:
                # 采购订单行的序号检查
                if check_if_po_component_exists(each["rel_po_sn"], each["rel_po_items"],
                                                each["rel_po_component_number"], dict_po_component):
                    error_list.append(
                        "行标识{}关联采购订单{}行{}项目序号{}不存在".format(each["line_id"], each["rel_po_sn"],
                                                                            each["rel_po_items"],
                                                                            each["rel_po_component_number"]))
            if each.get("rel_po_comp_batch_num", 0) != 0:
                # 采购订单库存绑定表检查
                if check_if_po_batch_binding_exists(each["rel_po_sn"], each["rel_po_items"],
                                                    each["rel_po_component_number"],
                                                    each["rel_po_comp_batch_num"], dict_po_binding):
                    error_list.append("行标识{}关联采购订单{}行{}项目序号{}绑定序号{}不存在".format(each["line_id"],
                                                                                                    each["rel_po_sn"],
                                                                                                    each[
                                                                                                        "rel_po_items"],
                                                                                                    each[
                                                                                                        "rel_po_component_number"],
                                                                                                    each[
                                                                                                        "rel_po_comp_batch_num"]))
                else:
                    # 批次检查
                    key = each["rel_po_sn"] + str(each['rel_po_items']) + str(each["rel_po_component_number"]) + str(
                        each['rel_po_comp_batch_num'])
                    if dict_po_binding[key][0]['batch_sn'] != each['batch_sn']:
                        error_list.append("行标识{}采购订单批次绑定表的批次禁止修改".format(each['line_id']))
                    if dict_po_binding[key][0]['allocated_qty'] != each['transaction_qty']:
                        error_list.append(
                            "行标识{}采购订单批次绑定表的数量禁止修改,不支持部分扣料".format(each['line_id']))
            if each.get("prodosn", "") != "":
                # 生产订单检查
                if dict_prodosn_data.get(each["prodosn"]) is None:
                    error_list.append("行标识{}生产订单{}不存在".format(each["line_id"], each["prodosn"]))
            if each.get("rcv_special_inventory_status2", "") == "T":
                # 关联交货单
                if each.get("picking_document", "") == "" or each.get("rel_dn_item", "") == "":
                    error_list.append("行标识{}拣配单号必输".format(each["line_id"]))
                else:
                    # 拣配单号检查
                    if dict_picking_document.get(each["picking_document"] + str(each.get("batch_item", 0))) is None:
                        error_list.append("行标识{}拣配单号{}不存在".format(each["line_id"], each["picking_document"]))

            if each.get("rel_dn_sn", "") != "":
                # 关联交货单检查
                if dict_dn_sn_header.get(each["rel_dn_sn"]) is None:
                    error_list.append("行标识{}关联交货单{}不存在".format(each["line_id"], each["rel_dn_sn"]))
                elif dict_dn_sn_item.get(each["rel_dn_sn"] + str(each.get("rel_dn_item", 0))) is None:
                    error_list.append("行标识{}关联交货单{}行号{}不存在".format(each["line_id"], each["rel_dn_sn"],
                                                                                each.get("rel_dn_item", 0)))
            if each.get("inv_transfer_order_no", "") != "":
                # 库存调拨单
                if dict_inv_transfer_order.get(each["inv_transfer_order_no"]) is None:
                    error_list.append(
                        "行标识{}库存调拨单{}不存在".format(each["line_id"], each["inv_transfer_order_no"]))
                elif dict_inv_transfer_order_item.get(
                        each["inv_transfer_order_no"] + str(each.get("inv_transfer_order_items", 0))) is None:
                    error_list.append(
                        "行标识{}库存调拨单{}行号{}不存在".format(each["line_id"], each["inv_transfer_order_no"],
                                                                  each.get("inv_transfer_order_items", 0)))
            if each.get("ro_sn", "") != "":

                if dict_ro_sn_data.get(each["ro_sn"] + str(each.get("ro_items", 0))) is None:
                    error_list.append("行标识{}关联预留单{}行号{}不存在".format(each["line_id"], each["ro_sn"],
                                                                                each.get("ro_items", 0)))
            if each.get("rel_so_sn", "") != "":

                if dict_so_sn_data.get(each["rel_so_sn"] + str(each.get("rel_so_items", 0))) is None:
                    error_list.append("行标识{}关联销售订单{}行号{}不存在".format(each["line_id"], each["rel_so_sn"],
                                                                                  each.get("rel_so_items", "")))
            if each.get("special_inventory_status1", "") == "C" or each.get("special_inventory_status1", "") == "CC":
                # 客户检查
                if each.get("customer_code", "") == "":
                    error_list.append("行标识{}客户编码必输".format(each["line_id"]))
                else:
                    if dict_customer_code_data.get(each["customer_code"]) is None:
                        error_list.append("行标识{}客户编码{}不存在".format(each["line_id"], each["customer_code"]))
            else:
                each["customer_code"] = ""

            if each.get("special_inventory_status1", "") == "S":
                # 销售订单检查
                if each.get("so_sn", "") == "" or each.get("so_items", 0) == 0:
                    error_list.append("行标识{}销售订单信息必输".format(each["line_id"]))
                else:
                    if dict_so_sn_data.get(each.get("so_sn", "") + str(each.get("so_items", 0))) is None:
                        error_list.append("行标识{}销售订单{}行号{}不存在".format(each["line_id"], each["rel_so_sn"],
                                                                                  each.get("rel_so_items", 0)))
            else:
                each["so_sn"] = ""
                each["so_items"] = 0

            if each.get("special_inventory_status1", "") == "P":
                # 项目编码检查
                if each.get("project_sn", "") == "":
                    error_list.append("行标识{}项目编码必输".format(each["line_id"]))
                    # 项目编码检查待定-----
            else:
                each["project_sn"] = ""

            if each.get("special_inventory_status1", "") == "V" or each.get("special_inventory_status1", "") == "SC":
                # 供应商编码检查
                if each.get("vendor_code", "") == "":
                    error_list.append("行标识{}供应商编码必输".format(each["line_id"]))
                else:
                    if dict_vendor_code_data.get(each["vendor_code"]) is None:
                        error_list.append("行标识{}供应商编码{}不存在".format(each["line_id"], each["vendor_code"]))

                if each["special_inventory_status1"] == "V":
                    if each.get("po_sn", "") != "":
                        # 采购订单检查
                        if dict_po_header.get(each["po_sn"]) is None:
                            error_list.append("行标识{}采购订单{}不存在".format(each["line_id"], each["po_sn"]))
                        else:
                            if dict_po_item.get(each["po_sn"] + str(each.get("po_items", 0))) is None:
                                error_list.append(
                                    "行标识{}采购订单{}行号{}不存在".format(each["line_id"], each["po_sn"],
                                                                            each.get("po_items", 0)))
                else:
                    each["po_sn"] = ""
                    each["po_items"] = 0
            else:
                each["vendor_code"] = ""
                each["po_sn"] = ""
                each["po_items"] = 0

            if each.get("rcv_special_inventory_status1", "") == "C" or each.get("rcv_special_inventory_status1",
                                                                                "") == "CC":
                # 客户检查
                if each.get("rcv_customer_code", "") == "":
                    error_list.append("行标识{}接收客户编码必输".format(each["line_id"]))
                else:
                    if dict_customer_code_data.get(each["rcv_customer_code"]) is None:
                        error_list.append(
                            "行标识{}接收客户编码{}不存在".format(each["line_id"], each["rcv_customer_code"]))
            else:
                each["rcv_customer_code"] = ""

            if each.get("rcv_special_inventory_status1", "") == "S":
                # 销售订单检查
                if each.get("rcv_so_sn", "") == "" or each.get("rcv_so_items", 0) == 0:
                    error_list.append("行标识{}接收销售订单信息必输".format(each["line_id"]))
                else:
                    if dict_so_sn_data.get(each.get("rcv_so_sn", "") + str(each.get("rcv_so_items", 0))) is None:
                        error_list.append(
                            "行标识{}接收销售订单{}行号{}不存在".format(each["line_id"], each["rcv_so_sn"],
                                                                        each.get("rcv_so_items", 0)))
            else:
                each["rcv_so_sn"] = ""
                each["rcv_so_items"] = 0

            if each.get("rcv_special_inventory_status1", "") == "P":
                # 项目编码检查
                if each.get("rcv_project_sn", "") == "":
                    error_list.append("行标识{}接收项目编码必输".format(each["line_id"]))
                    # 项目编码检查待定-----
            else:
                each["rcv_project_sn"] = ""

            if each.get("rcv_special_inventory_status1", "") == "V" or each.get("rcv_special_inventory_status1",
                                                                                "") == "SC":
                # 供应商编码检查
                if each.get("rcv_vendor_code", "") == "":
                    error_list.append("行标识{}接收供应商编码必输".format(each["line_id"]))
                else:
                    if dict_vendor_code_data.get(each["rcv_vendor_code"]) is None:
                        error_list.append(
                            "行标识{}接收供应商编码{}不存在".format(each["line_id"], each["rcv_vendor_code"]))

                if each["rcv_special_inventory_status1"] == "V":
                    if each.get("rcv_po_sn", "") != "":
                        # 采购订单检查
                        if dict_po_header.get(each["rcv_po_sn"]) is None:
                            error_list.append("行标识{}接收采购订单{}不存在".format(each["line_id"], each["rcv_po_sn"]))
                        else:
                            if dict_po_item.get(each["rcv_po_sn"] + str(each.get("rcv_po_items", 0))) is None:
                                error_list.append(
                                    "行标识{}接收采购订单{}行号{}不存在".format(each["line_id"], each["rcv_po_sn"],
                                                                                each.get("rcv_po_items", 0)))
                else:
                    each["rcv_po_sn"] = ""
                    each["rcv_po_items"] = 0
            else:
                each["rcv_vendor_code"] = ""
                each["rcv_po_sn"] = ""
                each["rcv_po_items"] = 0

            if each.get("cost_center", "") != "":
                # 成本中心检查
                if dict_cost_center_data.get(each["cost_center"] + each["plant_code"]) is None:
                    error_list.append(
                        "行标识{}成本中心{}在工厂{}对应的公司代码不存在".format(each["line_id"], each["cost_center"],
                                                                                each["plant_code"]))
            if each.get("cost_business_object", "") != "":
                # 成本事项检查
                if dict_cost_business_object_data.get(each["cost_business_object"] + each["plant_code"]) is None:
                    error_list.append(
                        "行标识{}成本事项{}在工厂{}对应的公司代码不存在".format(each["line_id"],
                                                                                each["cost_business_object"],
                                                                                each["plant_code"]))
            if each.get("cost_business_object1", "") != "":
                # 成本事项1检查
                if dict_cost_business_object_data.get(each["cost_business_object1"] + each["plant_code"]) is None:
                    error_list.append("行标识{}成本事项2{}在工厂{}对应的公司代码不存在".format(each["line_id"], each[
                        "cost_business_object1"], each["plant_code"]))
            if each.get("profit_center", "") != "":
                # 利润中心检查
                if dict_profit_center_data.get(each["profit_center"] + each["plant_code"]) is None:
                    error_list.append(
                        "行标识{}利润中心{}在工厂{}对应的公司代码不存在".format(each["line_id"], each["profit_center"],
                                                                                each["plant_code"]))
            if each.get("equipment_code", "") != "":
                # 设备ID检查
                if dict_equipment_code_data.get(each["equipment_code"]) is None:
                    error_list.append("行标识{}设备ID{}不存在".format(each["line_id"], each["equipment_code"]))
            if each.get("picking_document", "") != "":
                if check_rel_dn_status('4', each["picking_document"], each.get("batch_item", 0),
                                       each.get("rcv_special_inventory_status2", ""), dict_picking_document):
                    error_list.append("行标识{}拣配单号{}不允许过账".format(each["line_id"], each["picking_document"]))

            if each.get("transaction_currency", "") == "":
                each["transaction_currency"] = get_company_basic_currency(each['plant_code'], dict_company)

    print("校验耗时: ", time.time() - check_begin)

    md_header = initialization("t_md_header", db)
    md_item = []
    md_price = []

    # 生成凭证数据
    if not error_list:
        # 单据种类
        md_header["document_category"] = "MDOC"
        # 物料凭证
        md_header["mat_doc_sn"] = ""
        # 年度
        md_header["year"] = head["posting_date"][:4]
        # 过账代码
        md_header["post_code"] = head["post_code"]
        # 凭证日期
        md_header["document_date"] = head["document_date"]
        # 过账日期
        md_header["posting_date"] = head["posting_date"]

        # 汇总唯一号
        md_header["summary_unique_number"] = head.get("summary_unique_number", "")
        # 备注信息1
        md_header["remarks_1"] = head.get("remarks_1", "")
        # 备注信息2
        md_header["remarks_2"] = head.get("remarks_2", "")
        # 供应商交货单
        md_header["vendor_dn"] = head.get("vendor_dn", "")

        # 预留字段
        md_header["reserved1"] = head.get("reserved1", "")
        md_header["reserved2"] = head.get("reserved2", "")
        md_header["reserved3"] = head.get("reserved3", "")
        md_header["reserved4"] = head.get("reserved4", "")
        md_header["reserved5"] = head.get("reserved5", "")
        md_header["reserved6"] = head.get("reserved6", "")
        md_header["reserved7"] = head.get("reserved7", "")
        md_header["reserved8"] = head.get("reserved8", "")
        md_header["reserved9"] = head.get("reserved9", "")
        md_header["reserved10"] = head.get("reserved10", "")

        # 物料凭证类型
        md_header["material_document_type"] = ""
        # 交易汇率 公司代码 信息
        md_header["company_code"], md_header["exchange_rate"] = get_company_info(item[0]["plant_code"],
                                                                                 item[0]["transaction_currency"],
                                                                                 dict_company)

        if head.get('exchange_rate', 0) != 0:
            md_header["exchange_rate"] = head['exchange_rate']

        md_header["create_id"] = user_id
        md_header["update_id"] = user_id

        md_header["ztype"] = head.get('ztype', '')

        if md_header["exchange_rate"] == 0:
            error_list.append("未获取到汇率")

        line_tmp = initialization("t_md_item", db)

        item_no = 0
        # 行项目设置
        for each in item:

            line = line_tmp.copy()

            item_no += 1
            # 物料凭证
            line["mat_doc_sn"] = md_header["mat_doc_sn"]
            # 年度
            line["year"] = md_header["year"]
            # 物料凭证信息行号
            line["mat_doc_items"] = item_no
            # 物料凭证行唯一标识
            line["line_id"] = item_no
            # 凭证行参考唯一标识
            line["parent_id"] = each.get("parent_id", 0)
            # 参考凭证行
            line["ref_item_serial_no"] = 0
            # 自动创建标识
            line["auto_mark"] = 0
            # 移动类型
            line["movement_type"] = each["movement_type"]
            # POD标识
            line['pod_related'] = each.get('pod_related', 0)
            # 物料凭证类型 借贷标识  收发标识  科目修改 业务单据种类
            line, material_document_type, prod_order_mark, wbs_elements_mark, cost_business_object_mark, asset_code1_mark = get_movement_attribute(
                line, line["movement_type"], dict_movement_type)
            if md_header["material_document_type"] == "":
                md_header["material_document_type"] = material_document_type
            if line["debit_credit_mark"] == "":
                error_list.append(
                    "行标识{}未能根据移动类型{}取到借贷标识".format(each["line_id"], each["movement_type"]))
            if line["receipt_consume_mark"] == "":
                error_list.append(
                    "行标识{}未能根据移动类型{}取到收发标识".format(each["line_id"], each["movement_type"]))
            if prod_order_mark == 1:
                if each.get("prodosn", "") == "":
                    error_list.append("行标识{}生产订单必填".format(each["line_id"]))
            if wbs_elements_mark == 1:
                if each.get("wbs_elements", "") == "":
                    error_list.append("行标识{}WBS必填".format(each["line_id"]))
            if cost_business_object_mark == 1:
                if each.get("cost_center", "") == "" and each.get("cost_business_object", "") == "" and each.get(
                        "cost_business_object1", "") == "":
                    error_list.append("行标识{}成本中心/成本事项/成本事项1必填一个".format(each["line_id"]))
            if asset_code1_mark == 1:
                if each.get("asset_code1", "") == "":
                    error_list.append("行标识{}资产卡片必填".format(each["line_id"]))
            # 特殊库存状态1
            line["special_inventory_status1"] = each.get("special_inventory_status1", "")
            # 特殊库存状态2
            line["special_inventory_status2"] = each.get("special_inventory_status2", "")
            # 库存状态
            inventory_status, reference_movement_in_flag, reference_credit_mark, inventory_transfer_type, ref_inventory_status = get_movement_type_4(
                each["movement_type"], dict_movement_type)
            if inventory_status != "":
                line["inventory_status"] = inventory_status
            else:
                line["inventory_status"] = each.get("inventory_status", "")
            # 事件类型
            each['debit_credit_mark'] = line["debit_credit_mark"]
            line["transaction_type_code"] = get_transaction_type_code4(each, 1, dict_po_item, dict_relation2,
                                                                       dict_mat_code)
            # 物料成本特殊评估标识
            line["mat_special_val_mark"] = get_material_special_val_mark(each["mat_code"], each["plant_code"],
                                                                         each.get("special_inventory_status1", ""),
                                                                         dict_mat_code)

            if line["transaction_type_code"] == "":
                error_list.append("行标识{}未能根据移动类型{}和采购订单{}信息取到事件类型".format(each["line_id"],
                                                                                                  each["movement_type"],
                                                                                                  each.get("rel_po_sn",
                                                                                                           "")))
            # 工厂代码
            line["plant_code"] = each["plant_code"]
            # 公司代码
            line["company_code"] = md_header["company_code"]
            # 结算公司代码
            line["settle_company_code"] = get_settle_company_code(each["plant_code"], dict_company)
            # 物料编码
            line["mat_code"] = each.get("mat_code", "")
            # 库存地点
            if line["mat_code"] == "" or line["special_inventory_status1"] == "V":
                line["stor_loc_code"] = ""
            else:
                line["stor_loc_code"] = each.get("stor_loc_code", "")
            # 批次号
            line["batch_sn"] = each.get("batch_sn", "")

            # 交易数量
            line["transaction_qty"] = each["transaction_qty"]
            # 交易单位
            line["transaction_uom"] = each["transaction_uom"]
            # 带借贷标识的交易数量
            if line["debit_credit_mark"] == "Cr":
                line["transaction_qty_dc_mark"] = line["transaction_qty"] * -1
            else:
                line["transaction_qty_dc_mark"] = line["transaction_qty"]

            # 基本单位/成本单位/价格控制/评估类/物料组
            line = get_material_uom(line["mat_code"], line["plant_code"], dict_mat_code, line)

            # # 平行数量
            # line["parallel_qty"] = each["parallel_qty"]
            # 平行单位
            line["parallel_uom"] = each.get("parallel_uom", "")

            # 计算基本数量和成本数量
            line = get_other_qty_by_unit(each, line, head['post_code'],
                                         dict_movement_type[each['movement_type']][0]['allow_zero_base_qty'],
                                         dict_movement_type[each['movement_type']][0]['allow_zero_parallel_qty'],
                                         dict_mat_uom_convert)

            if dict_movement_type[each['movement_type']][0]['allow_zero_base_qty'] == 0:
                if line["basic_qty"] <= 0:
                    error_list.append("行标识{}基本数量不能为0".format(each["line_id"]))

            if dict_movement_type[each['movement_type']][0]['allow_zero_parallel_qty'] == 0:
                if line["parallel_qty"] <= 0 and line["parallel_uom"]:
                    error_list.append("行标识{}平行数量不能为0".format(each["line_id"]))

            # 带借贷标识的基本数量
            if line["debit_credit_mark"] == "Cr":
                line["basic_qty_dc_mark"] = line["basic_qty"] * -1
            else:
                line["basic_qty_dc_mark"] = line["basic_qty"]

            # 带借贷标识的成本数量
            if line["debit_credit_mark"] == "Cr":
                line["cost_qty_dc_mark"] = line["cost_qty"] * -1
            else:
                line["cost_qty_dc_mark"] = line["cost_qty"]

            # 带借贷标识的平行数量
            if line["debit_credit_mark"] == "Cr":
                line["parallel_qty_dc_mark"] = line["parallel_qty"] * -1
            else:
                line["parallel_qty_dc_mark"] = line["parallel_qty"]

            # 交易货币
            line["transaction_amount"] = each.get("transaction_amount", 0)
            # 交易货币
            if each.get("transaction_currency", "") == "":
                line["transaction_currency"] = get_company_basic_currency(line["plant_code"], dict_company)
            else:
                line["transaction_currency"] = each["transaction_currency"]
            # 消耗记账 对象标识 价值更新 数量更新
            line = get_movement_label(line, each.get("rel_po_sn", ""), each.get("rel_po_items", 0), dict_movement_type,
                                      dict_mat_code,
                                      dict_po_item, dict_movement_label1, dict_movement_label2, dict_movement_label3)
            if line["consumption_posting_label"] == "":
                error_list.append("行标识{}消耗记账标识不能为空".format(each["line_id"]))
            if line["item_indicator"] == "":
                error_list.append("行标识{}对象标识不能为空".format(each["line_id"]))
            if line["value_update"] == "":
                error_list.append("行标识{}价值更新不能为空".format(each["line_id"]))
            # 关联采购订单
            line["rel_po_sn"] = each.get("rel_po_sn", "")
            # 关联采购订单行
            line["rel_po_items"] = each.get("rel_po_items", 0)
            # 关联采购订单行项目序号
            line["rel_po_component_number"] = each.get("rel_po_component_number", 0)
            # 关联采购订单行序号
            line["rel_po_comp_batch_num"] = each.get("rel_po_comp_batch_num", 0)
            # 关联生产订单组件序号
            line["prodo_component_number"] = each.get("prodo_component_number", '')
            # 生产订单
            line["prodosn"] = each.get("prodosn", "")
            # 关联交货单
            line["rel_dn_sn"] = each.get("rel_dn_sn", "")
            # 关联交货单行号
            line["rel_dn_item"] = each.get("rel_dn_item", 0)
            # 拣配单号
            line["picking_document"] = each.get("picking_document", "")
            # 批次行号
            line["batch_item"] = each.get("batch_item", 0)
            # 关联预留单
            line["ro_sn"] = each.get("ro_sn", "")
            # 关联预留单行
            line["ro_items"] = each.get("ro_items", 0)
            # 关联销售订单
            line["rel_so_sn"] = each.get("rel_so_sn", "")
            # 关联销售订单行项目
            line["rel_so_items"] = each.get("rel_so_items", 0)
            # 关联单据种类 关联单据号 关联行号 原始单据类型 原始单据号 原始单据行号
            line = get_associated_order(md_header, line)
            # 客户编码
            line["customer_code"] = each.get("customer_code", "")
            # 销售订单
            line["so_sn"] = each.get("so_sn", "")
            # 销售订单行项目
            line["so_items"] = each.get("so_items", 0)
            # 库存调拨单
            line['inv_transfer_order_no'] = each.get("inv_transfer_order_no", '')
            # 库存调拨单行
            line['inv_transfer_order_items'] = each.get("inv_transfer_order_items", 0)
            # 项目编号
            line["project_sn"] = each.get("project_sn", "")
            # 供应商编码
            line["vendor_code"] = each.get("vendor_code", "")
            # 采购订单
            line["po_sn"] = each.get("po_sn", "")
            # 采购订单行项目
            line["po_items"] = each.get("po_items", 0)
            # WBS元素
            line["wbs_elements"] = each.get("wbs_elements", "")
            # 成本中心
            line["cost_center"] = each.get("cost_center", "")
            # 成本事项
            line["cost_business_object"] = each.get("cost_business_object", "")
            # 成本事项1
            line["cost_business_object1"] = each.get("cost_business_object1", "")
            # 利润中心
            line["profit_center"] = each.get("profit_center", "")
            # 会计科目
            line["accounting_subjects"] = each.get("accounting_subjects", "")
            # 资产卡片
            line["asset_code1"] = each.get("asset_code1", "")
            # 子资产
            line["asset_code2"] = each.get("asset_code2", "")
            # 设备ID
            line["equipment_code"] = each.get("equipment_code", "")
            # 快递单号
            line["express_delivery"] = each.get("express_delivery", "")
            # 行参考信息1
            line["reference1_item"] = each.get("reference1_item", "")
            # 行参考信息2
            line["reference2_item"] = each.get("reference2_item", "")
            # 行参考信息3
            line["reference3_item"] = each.get("reference3_item", "")
            # 汇总行
            line["summary_line"] = each.get("summary_line", 0)
            # 批次编码校验
            print("line---------------:", line)
            if each.get("mat_code", "") != "":
                line["batch_sn"], each["batch_number"], msg = check_batch_required4(line["mat_code"],
                                                                                    line["plant_code"],
                                                                                    line["batch_sn"],
                                                                                    line["debit_credit_mark"],
                                                                                    dict_mat_code, dict_mat_batch,
                                                                                    each.get("batch_number", {}),
                                                                                    dict_movement_type[
                                                                                        line['movement_type']][0]
                                                                                        )
                if msg != "":
                    error_list.append("行标识{}{}".format(each["line_id"], msg))
            # 交易前移动平均价（成本货币）/ 交易前移动平均价（本位币）
            # ---待补充

            # 质检过账标识 / 质量检验单标识
            line["quality_insp_post_mark"] = each.get("quality_insp_post_mark", 0)
            line["quality_insp_order_mark"], msg = get_quality_inspection_mark(line["mat_code"], line["plant_code"],
                                                                               line["inventory_status"],
                                                                               line["movement_type"],
                                                                               line["debit_credit_mark"],
                                                                               line["quality_insp_post_mark"],
                                                                               dict_mat_code, dict_movement_type,
                                                                               dict_mat_insp)
            if msg != "":
                error_list.append("行标识{}{}".format(each["line_id"], msg))

            # 结批标识
            line["batch_closure_flag"] = each.get("batch_closure_flag", 0)
            # 结批日期
            line["batch_closure_date"] = each.get("batch_closure_date", "")
            # 收货完成标记
            line["receipt_completed_flag"] = each.get("receipt_completed_flag", 0)

            # 移动原因
            line["movement_reason"] = each.get("movement_reason", "")

            # 参考凭证年度
            line["rel_document_year"] = each.get("rel_document_year", "")
            # 参考凭证号
            line["rel_document_no"] = each.get("rel_document_no", "")
            # 参考凭证行号
            line["ref_document_mat"] = each.get("ref_document_mat", 0)

            # 预留字段
            line["reserved1"] = each.get("reserved1", "")
            line["reserved2"] = each.get("reserved2", "")
            line["reserved3"] = each.get("reserved3", "")
            line["reserved4"] = each.get("reserved4", "")
            line["reserved5"] = each.get("reserved5", "")
            line["reserved6"] = each.get("reserved6", "")
            line["reserved7"] = each.get("reserved7", "")
            line["reserved8"] = each.get("reserved8", "")
            line["reserved9"] = each.get("reserved9", "")
            line["reserved10"] = each.get("reserved10", "")

            # 批次属性
            # batch_number = {}
            # line["batch_number"] = {}
            #
            # batch_number["production_date"] = each["batch_number"].get("production_date", "")
            # batch_number["maturity_date"] = each["batch_number"].get("maturity_date", "")
            # batch_number["vendor_code"] = each["batch_number"].get("vendor_code", "")
            # batch_number["vendor_batch"] = each["batch_number"].get("vendor_batch", "")
            # batch_number["receive_date"] = each["batch_number"].get("receive_date", "")
            # batch_number["lot_no"] = each["batch_number"].get("lot_no", "")
            # batch_number["wafer_id"] = each["batch_number"].get("wafer_id", "")
            # batch_number["mfg_date_wafer"] = each["batch_number"].get("mfg_date_wafer", "")
            # batch_number["vendor_lot_no"] = each["batch_number"].get("vendor_lot_no", "")
            # batch_number["mfg_date_assy"] = each["batch_number"].get("mfg_date_assy", "")
            # batch_number["packing_seal_date"] = each["batch_number"].get("packing_seal_date", "")
            # batch_number["date_code"] = each["batch_number"].get("date_code", "")
            # batch_number["packing_id"] = each["batch_number"].get("packing_id", "")
            # batch_number["bin_grade"] = each["batch_number"].get("bin_grade", "")
            # batch_number["grade"] = each["batch_number"].get("grade", "")
            # batch_number["batch_type"] = each["batch_number"].get("batch_type", "")
            # batch_number["receive_data"] = each["batch_number"].get("receive_data", "")
            # batch_number["cp_vendor"] = each["batch_number"].get("cp_vendor", "")
            # batch_number["bin"] = each["batch_number"].get("bin", "")
            # batch_number["grade1"] = each["batch_number"].get("grade1", "")
            # batch_number["grade2"] = each["batch_number"].get("grade2", "")
            # batch_number["grade3"] = each["batch_number"].get("grade3", "")
            # batch_number["extended_batch_date1"] = each["batch_number"].get("extended_batch_date1", "")
            # batch_number["extended_batch_date2"] = each["batch_number"].get("extended_batch_date2", "")
            # batch_number["extended_batch_date3"] = each["batch_number"].get("extended_batch_date3", "")
            # batch_number["extended_batch_attributes1"] = each["batch_number"].get("extended_batch_attributes1", "")
            # batch_number["extended_batch_attributes2"] = each["batch_number"].get("extended_batch_attributes2", "")
            # batch_number["extended_batch_attributes3"] = each["batch_number"].get("extended_batch_attributes3", "")
            # batch_number["item"] = edit_batch_attribute(each["batch_number"].get("item", []))
            # batch_number["create_id"] = user_id
            # batch_number["update_id"] = user_id
            # line["batch_number"] = batch_number

            line["batch_number"] = each.get('batch_number', {})
            line["batch_number"]["create_id"] = user_id
            line["batch_number"]["update_id"] = user_id

            line["create_id"] = user_id
            line["update_id"] = user_id

            md_item.append(line.copy())

            line2 = line.copy()
            # 调拨行
            item_no += 1
            # 物料凭证
            line2["mat_doc_sn"] = md_header["mat_doc_sn"]
            # 年度
            line2["year"] = md_header["year"]
            # 物料凭证信息行号
            line2["mat_doc_items"] = item_no
            # 物料凭证行唯一标识
            line2["line_id"] = item_no
            # 凭证行参考唯一标识
            line2["parent_id"] = each.get("parent_id", 0)
            # 参考凭证行
            line2["ref_item_serial_no"] = line["mat_doc_items"]
            # 自动创建标识
            line2["auto_mark"] = 1
            # POD标识
            line2['pod_related'] = each.get('pod_related', 0)
            # 移动类型
            # line2["movement_type"] = get_ref_movement_type(each["movement_type"])
            line2["movement_type"] = each["movement_type"]

            if line2["movement_type"] == "":
                error_list.append(
                    "行标识{}未能根据移动类型{}取到参考移动类型".format(each["line_id"], each["movement_type"]))
            else:
                # 物料凭证类型 借贷标识  收发标识  科目修改 业务单据种类
                line2, material_document_type, prod_order_mark, wbs_elements_mark, cost_business_object_mark, asset_code1_mark = get_movement_attribute(
                    line2, line2["movement_type"], dict_movement_type)

                if line2["debit_credit_mark"] == "":
                    error_list.append(
                        "行标识{}未能根据移动类型{}取到借贷标识".format(each["line_id"], line2["movement_type"]))
                if line2["receipt_consume_mark"] == "":
                    error_list.append(
                        "行标识{}未能根据移动类型{}取到收发标识".format(each["line_id"], line2["movement_type"]))
                # 物料成本特殊评估标识
                line2["mat_special_val_mark"] = get_material_special_val_mark(each["mat_code"], each["plant_code"],
                                                                              each.get("special_inventory_status1", ""),
                                                                              dict_mat_code)

                if prod_order_mark == 1:
                    if each.get("prodosn", "") == "":
                        error_list.append("行标识{}生产订单必填".format(each["line_id"]))
                if wbs_elements_mark == 1:
                    if each.get("wbs_elements", "") == "":
                        error_list.append("行标识{}WBS必填".format(each["line_id"]))
                if cost_business_object_mark == 1:
                    if each.get("cost_center", "") == "" and each.get("cost_business_object", "") == "" and each.get(
                            "cost_business_object1", "") == "":
                        error_list.append("行标识{}成本中心/成本事项/成本事项1必填一个".format(each["line_id"]))
                if asset_code1_mark == 1:
                    if each.get("asset_code1", "") == "":
                        error_list.append("行标识{}资产卡片必填".format(each["line_id"]))
                # 特殊库存状态1校验
                if each.get("rcv_special_inventory_status1", "") != "":
                    if line2["movement_type"] + each[
                        "rcv_special_inventory_status1"] not in movement_special_inventory_status1:
                        error_list.append(
                            "行标识{}在移动类型{}下特殊库存标识1{}未分配".format(each["line_id"],
                                                                                 line2["movement_type"],
                                                                                 each.get(
                                                                                     "rcv_special_inventory_status1",
                                                                                     "")))
                # 特殊库存状态2校验
                if each.get("rcv_special_inventory_status2", "") != "":
                    if line2["movement_type"] + each[
                        "rcv_special_inventory_status2"] not in movement_special_inventory_status2:
                        error_list.append(
                            "行标识{}在移动类型{}下特殊库存标识2{}未分配".format(each["line_id"],
                                                                                 line2["movement_type"],
                                                                                 each.get(
                                                                                     "rcv_special_inventory_status2",
                                                                                     "")))
            # 特殊库存状态1
            line2["special_inventory_status1"] = each.get("rcv_special_inventory_status1", "")
            # 特殊库存状态2
            line2["special_inventory_status2"] = each.get("rcv_special_inventory_status2", "")
            # 库存状态
            inventory_status, reference_movement_in_flag, reference_credit_mark, inventory_transfer_type, ref_inventory_status = get_movement_type_4(
                line2["movement_type"], dict_movement_type)
            if ref_inventory_status != "":
                line2["inventory_status"] = ref_inventory_status
            else:
                line2["inventory_status"] = each.get("rcv_inventory_status", "")
            # 借贷标识
            line2["debit_credit_mark"] = reference_credit_mark
            # 收发标识
            line2["receipt_consume_mark"] = reference_movement_in_flag

            # 工厂代码
            if inventory_transfer_type == "2":
                line2["plant_code"] = each.get("rcv_plant_code", "")
                line2["batch_sn"] = each.get("rcv_batch_sn", "")
                line2["stor_loc_code"] = each.get("rcv_stor_loc_code", "")
            # 物料编码
            if inventory_transfer_type == "3":
                line2["mat_code"] = each.get("rcv_mat_code", "")
                line2["batch_sn"] = each.get("rcv_batch_sn", "")
                line2["stor_loc_code"] = each.get("rcv_stor_loc_code", "")

            # 批次号
            if inventory_transfer_type == "4" or inventory_transfer_type == "1":
                line2["batch_sn"] = each.get("rcv_batch_sn", "")
                line2["stor_loc_code"] = each.get("rcv_stor_loc_code", "")

            # 公司代码
            line2["company_code"] = md_header["company_code"]
            # 结算公司代码
            line2["settle_company_code"] = get_settle_company_code(line2["plant_code"], dict_company)

            # 事件类型
            each['debit_credit_mark'] = line2["debit_credit_mark"]
            line2["transaction_type_code"] = get_transaction_type_code4(each, 0, dict_po_item, dict_relation2,
                                                                        dict_mat_code)
            if line2["transaction_type_code"] == "":
                error_list.append("行标识{}未能根据移动类型{}和采购订单{}信息取到事件类型".format(each["line_id"],
                                                                                                  line2[
                                                                                                      "movement_type"],
                                                                                                  each.get("rel_po_sn",
                                                                                                           "")))

            if line2["company_code"] != line2["settle_company_code"]:
                error_list.append("行标识{}接收工厂所属公司不一致".format(each["line_id"]))

            if check_material_price_control(line["mat_code"], line["plant_code"], line2["mat_code"],
                                            line2["plant_code"], dict_mat_code_cost):
                error_list.append("行标识{}物料的价格控制不一致".format(each["line_id"]))

            if dict_mat_code[each['mat_code'] + each['plant_code']][0]["basic_uom"] != \
                    dict_mat_code[each['rcv_mat_code'] + each['rcv_plant_code']][0]["basic_uom"]:
                error_list.append("行标识{}发送和接收的物料基本单位不一致".format(each["line_id"]))

            # 库存地点
            if line2["mat_code"] == "" or line2["special_inventory_status1"] == "V":
                line2["stor_loc_code"] = ""
            else:
                line2["stor_loc_code"] = each.get("rcv_stor_loc_code", "")

            # else:
            #     line2["batch_sn"] = each.get("batch_sn", "")
            # 交易数量
            line2["transaction_qty"] = each["transaction_qty"]
            # 交易单位
            line2["transaction_uom"] = each["transaction_uom"]
            # 带借贷标识的交易数量
            if line2["debit_credit_mark"] == "Cr":
                line2["transaction_qty_dc_mark"] = line2["transaction_qty"] * -1
            else:
                line2["transaction_qty_dc_mark"] = line2["transaction_qty"]

            # 基本单位/成本单位/价格控制/评估类/物料组
            line2 = get_material_uom(line["mat_code"], line["plant_code"], dict_mat_code, line2)

            # 计算基本数量和成本数量
            line2 = get_other_qty_by_unit(each, line2, head['post_code'],
                                          dict_movement_type[each['movement_type']][0]['allow_zero_base_qty'],
                                          dict_movement_type[each['movement_type']][0]['allow_zero_parallel_qty'],
                                          dict_mat_uom_convert)

            if dict_movement_type[each['movement_type']][0]['allow_zero_base_qty'] == 0:
                if line2["basic_qty"] <= 0:
                    error_list.append("行标识{}基本数量不能为0".format(each["line_id"]))

            if dict_movement_type[each['movement_type']][0]['allow_zero_parallel_qty'] == 0:
                if line2["parallel_qty"] <= 0 and line2["parallel_uom"]:
                    error_list.append("行标识{}平行数量不能为0".format(each["line_id"]))

            # 带借贷标识的基本数量
            if line2["debit_credit_mark"] == "Cr":
                line2["basic_qty_dc_mark"] = line2["basic_qty"] * -1
            else:
                line2["basic_qty_dc_mark"] = line2["basic_qty"]

            # 带借贷标识的成本数量
            if line2["debit_credit_mark"] == "Cr":
                line2["cost_qty_dc_mark"] = line2["cost_qty"] * -1
            else:
                line2["cost_qty_dc_mark"] = line2["cost_qty"]

            # 带借贷标识的平行数量
            if line2["debit_credit_mark"] == "Cr":
                line2["parallel_qty_dc_mark"] = line2["parallel_qty"] * -1
            else:
                line2["parallel_qty_dc_mark"] = line2["parallel_qty"]
            # 交易货币
            line2["transaction_amount"] = each.get("transaction_amount", 0)
            # 交易货币
            if each.get("transaction_currency", "") == "":
                line2["transaction_currency"] = get_company_basic_currency(line2["plant_code"], dict_company)
            else:
                line2["transaction_currency"] = each["transaction_currency"]
            # # 消耗记账 对象标识 价值更新 数量更新
            # line2 = get_movement_label(line2, each["rel_po_sn"], each["rel_po_items"], md_header["post_code"])
            # 关联采购订单
            line2["rel_po_sn"] = each.get("rel_po_sn", "")
            # 关联采购订单行
            line2["rel_po_items"] = each.get("rel_po_items", 0)
            # 关联采购订单行项目序号
            line2["rel_po_component_number"] = each.get("rel_po_component_number", 0)
            # 关联采购订单行序号
            line2["rel_po_comp_batch_num"] = each.get("rel_po_comp_batch_num", 0)
            # 关联生产订单组件序号
            line2["prodo_component_number"] = each.get("prodo_component_number", '')
            # 生产订单
            line2["prodosn"] = each.get("prodosn", "")
            # 关联交货单
            line2["rel_dn_sn"] = each.get("rel_dn_sn", "")
            # 关联交货单行号
            line2["rel_dn_item"] = each.get("rel_dn_item", 0)
            # 拣配单号
            line2["picking_document"] = each.get("picking_document", "")
            # 批次行号
            line2["batch_item"] = each.get("batch_item", 0)
            # 关联预留单
            line2["ro_sn"] = each.get("ro_sn", "")
            # 关联销售订单
            line2["rel_so_sn"] = each.get("rel_so_sn", "")
            # 关联销售订单行项目
            line2["rel_so_items"] = each.get("rel_so_items", 0)

            # 接收销售订单
            line2["so_sn"] = each.get("rcv_so_sn", "")
            # 接收销售订单行项目
            line2["so_items"] = each.get("rcv_so_items", 0)

            # 关联单据种类 关联单据号 关联行号 原始单据类型 原始单据号 原始单据行号
            line2 = get_associated_order(md_header, line2)
            # 客户编码
            line2["customer_code"] = each.get("rcv_customer_code", "")
            # # 销售订单
            # line2["so_sn"] = each.get("so_sn", "")
            # # 销售订单行项目
            # line2["so_items"] = each.get("so_items", "")
            # 库存调拨单
            line2['inv_transfer_order_no'] = each.get("inv_transfer_order_no", '')
            # 库存调拨单行
            line2['inv_transfer_order_items'] = each.get("inv_transfer_order_items", 0)

            # 项目编号
            line2["project_sn"] = each.get("project_sn", "")
            # 供应商编码
            line2["vendor_code"] = each.get("rcv_vendor_code", "")
            # 采购订单
            line2["po_sn"] = each.get("po_sn", "")
            # 采购订单行项目
            line2["po_items"] = each.get("po_items", 0)
            # WBS元素
            line2["wbs_elements"] = each.get("wbs_elements", "")
            # 成本中心
            line2["cost_center"] = each.get("cost_center", "")
            # 成本事项
            line2["cost_business_object"] = each.get("cost_business_object", "")
            # 成本事项1
            line2["cost_business_object1"] = each.get("cost_business_object1", "")
            # 利润中心
            line2["profit_center"] = each.get("profit_center", "")
            # 会计科目
            line2["accounting_subjects"] = each.get("accounting_subjects", "")
            # 资产卡片
            line2["asset_code1"] = each.get("asset_code1", "")
            # 子资产
            line2["asset_code2"] = each.get("asset_code2", "")
            # 设备ID
            line2["equipment_code"] = each.get("equipment_code", "")
            # 快递单号
            line2["express_delivery"] = each.get("express_delivery", "")
            # 行参考信息1
            line2["reference1_item"] = each.get("reference1_item", "")
            # 行参考信息2
            line2["reference2_item"] = each.get("reference2_item", "")
            # 行参考信息3
            line2["reference3_item"] = each.get("reference3_item", "")
            # 汇总行
            line2["summary_line"] = each.get("summary_line", 0)
            # 批次编码校验
            print('line2--------', line2)
            if each.get("mat_code", "") != "":
                line2["batch_sn"], each['rcv_batch_number'], msg = check_batch_required4(line2["mat_code"],
                                                                                         line2["plant_code"],
                                                                                         line2["batch_sn"],
                                                                                         line["debit_credit_mark"],
                                                                                         dict_mat_code, dict_mat_batch,
                                                                                         each.get('rcv_batch_number',
                                                                                                  {}),
                                                                                         dict_movement_type[
                                                                                             line2['movement_type']][0])
                if msg != "":
                    error_list.append("行标识{}{}".format(each["line_id"], msg))

            # 交易前移动平均价（成本货币）/ 交易前移动平均价（本位币）
            # ---待补充
            # 结批标识
            line2["batch_closure_flag"] = each.get("batch_closure_flag", 0)
            # 结批日期
            line2["batch_closure_date"] = each.get("batch_closure_date", "")
            # 收货完成标记
            line2["receipt_completed_flag"] = each.get("receipt_completed_flag", 0)

            # 参考凭证年度
            line2["rel_document_year"] = each.get("rel_document_year", "")
            # 参考凭证号
            line2["rel_document_no"] = each.get("rel_document_no", "")
            # 参考凭证行号
            line2["ref_document_mat"] = each.get("ref_document_mat", 0)
            # 前序物料凭证年度
            line2["pre_document_year"] = each.get("pre_document_year", "")
            # 前序物料凭证
            line2["pre_document_no"] = each.get("pre_document_no", "")
            # 前序物料凭证行号
            line2["pre_document_item"] = each.get("pre_document_item", 0)

            # 预留字段
            line2["reserved1"] = each.get("rcv_reserved1", "")
            line2["reserved2"] = each.get("rcv_reserved2", "")
            line2["reserved3"] = each.get("rcv_reserved3", "")
            line2["reserved4"] = each.get("rcv_reserved4", "")
            line2["reserved5"] = each.get("rcv_reserved5", "")
            line2["reserved6"] = each.get("rcv_reserved6", "")
            line2["reserved7"] = each.get("rcv_reserved7", "")
            line2["reserved8"] = each.get("rcv_reserved8", "")
            line2["reserved9"] = each.get("rcv_reserved9", "")
            line2["reserved10"] = each.get("rcv_reserved10", "")

            # 批次属性
            # batch_number = {}
            # line2["batch_number"] = {}
            #
            # batch_number["production_date"] = each["rcv_batch_number"].get("production_date", "")
            # batch_number["maturity_date"] = each["rcv_batch_number"].get("maturity_date", "")
            # batch_number["vendor_code"] = each["rcv_batch_number"].get("vendor_code", "")
            # batch_number["vendor_batch"] = each["rcv_batch_number"].get("vendor_batch", "")
            # batch_number["receive_date"] = each["rcv_batch_number"].get("receive_date", "")
            # batch_number["lot_no"] = each["rcv_batch_number"].get("lot_no", "")
            # batch_number["wafer_id"] = each["rcv_batch_number"].get("wafer_id", "")
            # batch_number["mfg_date_wafer"] = each["rcv_batch_number"].get("mfg_date_wafer", "")
            # batch_number["vendor_lot_no"] = each["rcv_batch_number"].get("vendor_lot_no", "")
            # batch_number["mfg_date_assy"] = each["rcv_batch_number"].get("mfg_date_assy", "")
            # batch_number["packing_seal_date"] = each["rcv_batch_number"].get("packing_seal_date", "")
            # batch_number["date_code"] = each["rcv_batch_number"].get("date_code", "")
            # batch_number["packing_id"] = each["rcv_batch_number"].get("packing_id", "")
            # batch_number["bin_grade"] = each["rcv_batch_number"].get("bin_grade", "")
            # batch_number["grade"] = each["rcv_batch_number"].get("grade", "")
            # batch_number["batch_type"] = each["rcv_batch_number"].get("batch_type", "")
            # batch_number["receive_data"] = each["rcv_batch_number"].get("receive_data", "")
            # batch_number["cp_vendor"] = each["rcv_batch_number"].get("cp_vendor", "")
            # batch_number["bin"] = each["rcv_batch_number"].get("bin", "")
            # batch_number["grade1"] = each["rcv_batch_number"].get("grade1", "")
            # batch_number["grade2"] = each["rcv_batch_number"].get("grade2", "")
            # batch_number["grade3"] = each["rcv_batch_number"].get("grade3", "")
            # batch_number["extended_batch_date1"] = each["rcv_batch_number"].get("extended_batch_date1", "")
            # batch_number["extended_batch_date2"] = each["rcv_batch_number"].get("extended_batch_date2", "")
            # batch_number["extended_batch_date3"] = each["rcv_batch_number"].get("extended_batch_date3", "")
            # batch_number["extended_batch_attributes1"] = each["rcv_batch_number"].get("extended_batch_attributes1", "")
            # batch_number["extended_batch_attributes2"] = each["rcv_batch_number"].get("extended_batch_attributes2", "")
            # batch_number["extended_batch_attributes3"] = each["rcv_batch_number"].get("extended_batch_attributes3", "")
            # batch_number["item"] = edit_batch_attribute(each["rcv_batch_number"].get("item", []))
            # batch_number["create_id"] = user_id
            # batch_number["update_id"] = user_id
            # line2["batch_number"] = batch_number

            line2["batch_number"] = each.get('rcv_batch_number', {})
            line2["batch_number"]["create_id"] = user_id
            line2["batch_number"]["update_id"] = user_id

            line2["create_id"] = user_id
            line2["update_id"] = user_id

            md_item.append(line2.copy())

    if not error_list:
        # 库存校验
        inventory_begin = time.time()

        msg_list = get_inventory_qty(md_item, md_header["posting_date"], dict_plant_storage, db)
        print("库存校验耗时：", time.time() - inventory_begin)
        if msg_list:
            error_list.extend(msg_list)

    if error_list:
        code = 500
        msg = "存在错误,请检查"
    else:
        code = 200
        msg = "检查无误"
        batch_begin = time.time()
        # 批次继承
        md_item = batch_inherit4(md_item, db)
        print("批次继承耗时：", time.time() - batch_begin)
    return code, msg, error_list, md_header, md_item, md_price


def batch_inherit4(item, db):
    movement_type = []
    for each in item:
        movement_type.append(each['movement_type'])
    # 获取批次策略信息
    query_sql = """
        SELECT
            a.`batch_inheritance_type`,
            a.`movement_type`,
            a.`po_type`,
            b.`field_code`,
            b.`multiple_data_rule`,
            b.`priority_code`,
            b.`is_update`
        FROM
            `t_batch_inheritance_strategy_alloc` as a 
        JOIN
            `t_batch_inheritance_strategy` as b
        ON
            a.`batch_inheritance_strategy` = b.`batch_inheritance_strategy`
        WHERE
            a.`movement_type` in ('{}')
        AND
            a.`activation_flag` = 1
        AND
            a.`po_type` = ''
        AND
            a.`prodo_type` = ''
    """.format("','".join(movement_type))
    data = db.query_sql(query_sql)

    if not data:
        return item

    # 按采购订单类型+移动类型分组
    dict_batch_config = {}
    for each in data:
        key = each["movement_type"]
        if key not in dict_batch_config:
            dict_batch_config[key] = []
            dict_batch_config[key].append(each)
        else:
            dict_batch_config[key].append(each)

    mat_code = []
    batch_sn = []

    dict_item = {}
    for each in item:
        if each['batch_sn']:
            mat_code.append(each['mat_code'])
            batch_sn.append(each['batch_sn'])

            key = each['mat_doc_items']

            if key not in dict_item:
                dict_item[key] = []
                dict_item[key].append(each)
            else:
                dict_item[key].append(each)

    # 获取批次属性
    dict_batch_number = get_batch_attribute_mult(mat_code, batch_sn, db)

    for each in item:
        if each['auto_mark'] == 1:
            batch_attr = []

            # 有批次时走继承
            if each['batch_sn']:
                if dict_item.get(each['ref_item_serial_no']):
                    j = dict_item[each['ref_item_serial_no']][0]
                    if j['batch_sn']:
                        key = j['mat_code'] + j['batch_sn']

                        batch_attr = dict_batch_number[key]

                        key = str(each['movement_type'])
                        each['batch_number'] = set_batch_number_attribute(dict_batch_config, key, batch_attr,
                                                                          each['batch_number'])
                # for j in item:
                #     if each['ref_item_serial_no'] == j['mat_doc_items']:
                #         if j['batch_sn']:
                #             key = j['mat_code'] + j['batch_sn']
                #
                #             batch_attr = dict_batch_number[key]
                #
                #             key = str(each['movement_type'])
                #             each['batch_number'] = set_batch_number_attribute(dict_batch_config, key, batch_attr,
                #                                                               each['batch_number'])
                #             break

    return item


def check_material_price_control(mat_code, plant_code, rcv_mat_code, rcv_plant_code, dict_mat_code_cost):
    if mat_code == "":
        return False

    if rcv_mat_code == "":
        return False

    price_control = ""
    rcv_price_control = ""

    # query_sql = """
    #     SELECT
    #         price_control
    #     FROM
    #         t_mmd_material_cost_data
    #     WHERE
    #         mat_code = '{}'
    #     AND plant_code = '{}'
    #     LIMIT 1
    # """.format(mat_code, plant_code)
    # data = db.query_sql(query_sql)
    key = mat_code + plant_code
    if dict_mat_code_cost.get(key):
        item = dict_mat_code_cost[key][0]
        price_control = item["price_control"]

    # query_sql = """
    #     SELECT
    #         price_control
    #     FROM
    #         t_mmd_material_cost_data
    #     WHERE
    #         mat_code = '{}'
    #     AND plant_code = '{}'
    #     LIMIT 1
    # """.format(rcv_mat_code, rcv_plant_code)
    # data = db.query_sql(query_sql)
    key = rcv_mat_code + rcv_plant_code
    if dict_mat_code_cost.get(key):
        item = dict_mat_code_cost[key][0]
        rcv_price_control = item["price_control"]

    if price_control == rcv_price_control:
        return False

    return True


# 调拨使用 获取移动类型属性
def get_movement_type_4(movement_type, dict_movement_type):
    # query_sql = """
    #     SELECT
    #         inventory_status,
    #         reference_movement_in_flag,
    #         reference_credit_mark,
    #         inventory_transfer_type,
    #         reference_inventory_status
    #     FROM
    #         t_movement_type
    #     WHERE
    #         movement_type = '{}'
    #     LIMIT 1
    # """.format(movement_type)
    # data = db.query_sql(query_sql)
    if dict_movement_type.get(movement_type):
        return dict_movement_type[movement_type][0]["inventory_status"], dict_movement_type[movement_type][0][
            "reference_movement_in_flag"], dict_movement_type[movement_type][0]["reference_credit_mark"], \
            dict_movement_type[movement_type][0]["inventory_transfer_type"], dict_movement_type[movement_type][0][
            "reference_inventory_status"]
    return '', '', '', ''


# 获取公司本位币
def get_company_basic_currency(plant_code, dict_company):
    # query_sql = """
    #     SELECT
    #         basic_currency
    #     FROM
    #         t_os_company
    #     WHERE
    #         company_code = '{}'
    #     LIMIT 1
    # """.format(company_code)
    # data = db.query_sql(query_sql)
    if dict_company.get(plant_code):
        return dict_company[plant_code][0]["basic_currency"]
    return ''


# 获取移动类型对应的参考移动类型
def get_ref_movement_type(movement_type, db):
    query_sql = """
        SELECT
            `ref_movement_type` 
        FROM
            `t_movement_type` 
        WHERE
            `movement_type` = '{}' 
        LIMIT 1
    """.format(movement_type)
    data = db.query_sql(query_sql)
    if data:
        return data[0]["ref_movement_type"]

    return ""



# 正式过账代码1
import json
import time


# 正式过账代码1
def post_data_postcode1(user_id, md_header, md_item, md_price, db):
    # ========== 初始化变量 ==========
    code = 0
    msg = ""
    mat_doc_sn = ""
    year = ""
    error_list = []

    print("=" * 80)
    print("[post_data_postcode1] 函数开始执行")
    print("[入参] user_id:", user_id)
    print("[入参] md_header:", repr(md_header))
    print("[入参] md_item:", repr(md_item))
    print("[入参] md_price:", repr(md_price))
    print("[入参] db:", db)
    print("=" * 80)

    # ========== 生成锁 KEY ==========
    try:
        print("[锁KEY] 尝试从 md_item 中获取 mat_code、batch_sn")
        mat_code = md_item[0]["mat_code"]
        batch_sn = md_item[0]["batch_sn"]
        # 用户id 物料编码  批次号
        lock_key = f"LOCK_{mat_code}_{batch_sn}"
        print("[锁KEY] 生成物料+批次锁:", lock_key)
    except Exception as lock_key_err:
        print("[锁KEY] 获取 mat_code/batch_sn 失败，异常信息:", str(lock_key_err))
        lock_key = f"LOCK_USER_{user_id}"
        print("[锁KEY] 降级使用用户锁:", lock_key)

    # ========== 主业务逻辑 ==========
    try:
        print("\n[库存锁] 开始执行加锁操作")
        # 锁库存
        code, msg = lock_data(md_item, LockAction.lock, lock_key)
        print("[库存锁] 加锁返回 code=", code, "msg=", msg)

        if code != 200:
            error_list.append(msg)
            print("[库存锁] 加锁失败，错误信息已加入 error_list:", error_list)
            raise Exception(msg)

        print("[库存锁] 加锁成功，开始调用 C 物料凭证会计引擎接口")

        # 调用c物料凭证会计引擎接口
        input_data = json.dumps([{"header": md_header, "items": md_item, "details": md_price}])
        print("\n[C引擎] 入参JSON:", input_data)

        sh = SystemHelper()
        c_begin = time.time()

        print("[C引擎] 开始调用 execOperator -> OnConsumeMat")
        result_map = sh.execOperator("OnConsumeMat", input_data)
        print("[C引擎] 原始返回结果:", result_map)

        output = json.loads(result_map["data"])
        c_cost_time = round(time.time() - c_begin, 4)
        print("[C引擎] 调用耗时：", c_cost_time, "秒")
        print("[C引擎] 解析后 output:", output)

        # ========== 解析 C 引擎返回结果 ==========
        print("\n[结果解析] 开始解析 C 引擎返回值")
        if output["result"] == 0:
            print("[结果解析] output.result == 0，接口调用成功")
            if "data" in output:
                print("[结果解析] output 中存在 data 字段")
                c_data = output["data"][0]
                print("[结果解析] 第一条数据详情:", c_data)

                if c_data["status"] == "E":
                    code = 500
                    msg = c_data["msg"]
                    print("[结果解析] C 引擎返回错误状态 E，错误信息:", msg)
                else:
                    code = 200
                    mat_doc_sn = c_data["mat_doc_sn"]
                    year = c_data["year"]
                    msg = "过账成功,物料凭证:{} 年度{}".format(mat_doc_sn, year)
                    print("[结果解析] 过账成功！凭证号=", mat_doc_sn, "年度=", year)
            else:
                code = 500
                msg = output.get("msg", "会计引擎异常：返回 data 为空")
                print("[结果解析] output 中无 data 字段，错误信息:", msg)
        else:
            code = 500
            msg = output["msg"]
            print("[结果解析] output.result != 0，业务失败，错误信息:", msg)

    # ========== 异常捕获 ==========
    except Exception as e:
        print("\n" + "!" * 50)
        print("[主逻辑异常] 捕获到异常:", str(e))
        print("[异常类型]", type(e).__name__)
        if not error_list:
            error_list.append(str(e))
            print("[异常处理] 错误信息加入 error_list:", error_list)
        code = 500
        msg = "存在错误,请检查"
        print("[异常处理] 设置 code=500, msg=", msg)
        print("!" * 50)

    # ========== 最终解锁（必执行） ==========
    finally:
        print("\n" + "-" * 60)
        print("[最终执行] 进入 finally 块，执行解锁操作")
        # ================= 无论如何都解锁（最关键） =================
        unlock_code, unlock_msg = lock_data(md_item, LockAction.unlock, lock_key)
        print("[解锁结果] lock_key=", lock_key)
        print("[解锁结果] code=", unlock_code, "msg=", unlock_msg)
        print("-" * 60)

    # ========== 函数返回 ==========
    print("\n" + "=" * 80)
    print("[post_data_postcode1] 函数执行完毕，准备返回")
    print("[返回结果] code:", code)
    print("[返回结果] msg:", msg)
    print("[返回结果] error_list:", error_list)
    print("[返回结果] mat_doc_sn:", mat_doc_sn)
    print("[返回结果] year:", year)
    print("=" * 80)

    return code, msg, error_list, mat_doc_sn, year



def lock_data(md_item, action, index_value):
    code = 200
    msg = ""
    data = []
    dict_data = {}
    if action == LockAction.lock:
        for each in md_item:
            key = (each["mat_code"] + each["plant_code"] + each["stor_loc_code"] + each["batch_sn"] + each[
                "inventory_status"] +
                   each["special_inventory_status1"] + each["special_inventory_status2"] + each["so_sn"] + str(
                        each["so_items"]) +
                   each["vendor_code"] + each["customer_code"] + each["project_sn"] + each["po_sn"] + str(
                        each["po_items"]))

            if key not in dict_data:
                dict_data[key] = []
                dict_data[key].append(each)
            else:
                dict_data[key].append(each)

        if not dict_data:
            return 200, ""

        for key in dict_data:
            data.append(
                {
                    "table_name": "t_inventory_batch_data",
                    "description": "库存明细表",
                    "key": key,
                    "index_value": index_value
                }
            )
    else:
        data.append(
            {
                "table_name": "t_inventory_batch_data",
                "description": "库存明细表",
                "key": '',
                "index_value": index_value
            }
        )

    sh = SystemHelper()
    for i in range(3):
        output = sh.doLock(action, data)

        if output["status"] == 200:
            code = 200
            msg = ""
            break
        elif output["status"] == 503:
            code = 600
            # result = json.loads(output["data"])
            line = dict_data[output["detail"][0]['key']]
            msg = "当前物料{}工厂{}库存地点{}批次{}被用户".format(line[0]["mat_code"], line[0]["plant_code"],
                                                                  line[0]["stor_loc_code"], line[0]["batch_sn"]) + \
                  output["detail"][0]["user_name"] + "锁定"
        else:
            code = 500
            msg = '数据加锁异常,请联系管理员'

    return code, msg


def get_movement_type_info(movement_type, db):
    if not movement_type:
        return {}

    movement_type = list(set(movement_type))

    query_sql = """
        SELECT
	        `movement_type`,
            `inventory_status`,
            `reference_movement_in_flag`,
            `reference_credit_mark`,
            `inventory_transfer_type`,
            `reference_inventory_status`,
            `ref_movement_type`,
            `quality_insp_order_mark`,
            `inspection_type`,
            `activation_flag`,
            `purchase_return_mark`,
            `debit_credit_mark`,
            `qty_update_flag`,
            `receipt_consume_mark`,
            `account_modify_code`,
            `business_doc_type`,
            `material_document_type`,
            `prod_order_mark`,
            `wbs_elements_mark`,
            `cost_business_object_mark`,
            `asset_related_flag`,
            `allow_zero_base_qty`,
            `allow_zero_parallel_qty`,
            `post_code`
        FROM
            `t_movement_type` 

    """.format("','".join(movement_type))

    data = db.query_sql(query_sql)
    # 将表的数据按KEY值做字典
    dict_movement_type = {}
    for each in data:
        key = each["movement_type"]
        if key not in dict_movement_type:
            dict_movement_type[key] = []
            dict_movement_type[key].append(each)
        else:
            dict_movement_type[key].append(each)

    del data
    return dict_movement_type

def get_profit_center(items, db, company_code):
    for i in items:
        if i.get("profit_center"):
            continue
        po_sn = i.get("po_sn", '') # 采购订单号
        if po_sn:
            sql = f""" select * from `t_po_item` where po_sn = {po_sn}"""
            t_po_item_data = db.query_sql(sql)
            print("t_po_item_data>>", t_po_item_data)

            if t_po_item_data:
                item = t_po_item_data[0]
                plant_code = item.get('plant_code', "")  # 工厂代码
                mat_code = item.get('mat_code', "")  # 物料编码
                pur_item_cat = item.get("pur_item_cat", '') # 采购项目类别
                prodosn = item.get('prodosn', "")  # 生产订单号
                so_sn = item.get("so_sn", "")  # 销售订单号
                so_items = item.get("so_items", "")  # 销售订单行号
                wbs_elements = item.get('wbs_elements', "")  # WBS元素
                cost_business_object = item.get('cost_business_object', "")  # 成本事项
                cost_center = item.get('cost_center', "")  # 成本中心
                account_allocation_category = item.get('account_allocation_category', "")  # 科目分配类别
                asset_code1 = item.get('asset_code1', "")  # 资产号
                asset_code2 = item.get('asset_code2', "")  # 子资产序号

                if pur_item_cat != "L":
                    profit_center = item.get("profit_center", '')
                    if not profit_center and pur_item_cat:
                        sql = f"""select `profit_center` from `t_mmd_material_financial_data` where `mat_code` = '{mat_code}' and `plant_code` = '{plant_code}'"""
                        t_mmd_material_financial_data = db.query_sql(sql)
                        if t_mmd_material_financial_data and t_mmd_material_financial_data[0].get('profit_center'):
                            i['profit_center'] = t_mmd_material_financial_data[0].get('profit_center')

                    elif prodosn:
                        filter_sql = f"""SELECT `profit_center` FROM `t_co_production_order` WHERE `prodosn` ='{prodosn}' """
                        print("项目采购类别为空,生产订单有值：sql>>", filter_sql)
                        data = db.query_sql(filter_sql)
                        print("项目采购类别为空,生产订单有值：data>>", data)
                        if data and data[0].get('profit_center'):
                            i['profit_center'] = data[0].get('profit_center')
                        # return po_data, "项目采购类别为空,生产订单有值"
                    elif so_sn:
                        filter_sql = f"""SELECT `profit_center` FROM `t_sales_order_item` WHERE `po_sn` ='{so_sn}' and `so_items` = '{so_items}'"""
                        print("项目采购类别为空,销售有值：sql>>", filter_sql)
                        data = db.query_sql(filter_sql)
                        print("项目采购类别为空,销售有值：data>>", data)
                        if data and data[0].get('profit_center'):
                            i['profit_center'] = data[0].get('profit_center')
                        print("项目采购类别为空,销售有值")
                        # return po_data, "项目采购类别为空,销售有值"
                    elif wbs_elements:
                        filter_sql = f"""SELECT `settle_type_flag`,`profit_center` FROM `t_co_wbs_element` WHERE `wbs_elements` ='{wbs_elements}' """
                        print("项目采购类别为空,wbs元素有值：sql>>", filter_sql)
                        data = db.query_sql(filter_sql)
                        print("项目采购类别为空,wbs元素有值：data>>", data)
                        if data and str(data[0].get('wbs_elements')) == "1":
                            i['profit_center'] = data[0].get('profit_center')
                        print("项目采购类别为空,wbs元素有值", filter_sql)
                    elif cost_business_object:
                        filter_sql = f"""select `t1`.`profit_center`
                                        from `t_co_cost_event` `t1` 
                                        left join `t_bd_cost_event_type` `t2` on `t1`.`cost_business_type`  = `t2`.`cost_business_type` and `t2`.`internal_sort` = '1'
                                        where `t1`.`cost_business_object` = '{cost_business_object}'"""
                        print("项目采购类别为空,成本事项1", filter_sql)
                        data = db.query_sql(filter_sql)
                        print("项目采购类别为空,成本事项1：data>>", data)
                        if data and data[0].get('profit_center'):
                            i['profit_center'] = data[0].get('profit_center')
                    elif cost_center and account_allocation_category:
                        filter_sql = f"""SELECT `profit_center` FROM `t_coc_cost_center` WHERE `cost_center` ='{cost_center}' """
                        print("项目采购类别为空,成本中心有值：sql>>>>", filter_sql)
                        data = db.query_sql(filter_sql)
                        print("项目采购类别为空,成本中心data>>>", filter_sql)
                        if data and data[0].get('profit_center'):
                            i['profit_center'] = data[0].get('profit_center')

                    if account_allocation_category and asset_code1:
                        filter_sql = f"""SELECT `profit_center` FROM `t_fi_asset_time_dependent_allocations` 
                                                    WHERE  `asset_code1` = '{asset_code1}' AND `asset_code2` = '{asset_code2}' 
                                                    ORDER BY `date_beginning_validity` DESC
                                                    LIMIT 1 """
                        print("采购项目类别为空，固定资产有值;sql>>>>", filter_sql)
                        data = db.query_sql(filter_sql)
                        if data:
                            i['profit_center'] = data[0]['profit_center']
                elif pur_item_cat == "L":
                    filter_sql = f"""SELECT `profit_center` FROM `t_mmd_material_financial_data` WHERE `plant_code` =  '{plant_code}' AND `mat_code` = '{mat_code}';"""
                    print("sql>>>", filter_sql)
                    data = db.query_sql(filter_sql)
                    print("data>>>", data)
                    data = data[0] if data else {}
                    print(1111, data.get('profit_center'))
                    if data.get('profit_center', ""):
                        i['profit_center'] = data[0].get('profit_center')
        elif not po_sn:
            plant_code = i.get('plant_code', "")  # 工厂代码
            mat_code = i.get('mat_code', "")  # 物料编码
            prodosn = i.get('prodosn', "")  # 生产订单号
            so_sn = i.get("so_sn", "")  # 销售订单号
            so_items = i.get("so_items", "")  # 销售订单行号
            wbs_elements = i.get('wbs_elements', "")  # WBS元素
            cost_business_object = i.get('cost_business_object', "")  # 成本事项
            cost_center = i.get('cost_center', "")  # 成本中心
            account_allocation_category = i.get('account_allocation_category', "")  # 科目分配类别
            if prodosn:
                filter_sql = f"""SELECT `profit_center` FROM `t_co_production_order` WHERE `prodosn` ='{prodosn}' """
                print("项目采购类别为空,生产订单有值：sql>>", filter_sql)
                data = db.query_sql(filter_sql)
                print("项目采购类别为空,生产订单有值：data>>", data)
                if data and data[0].get('profit_center'):
                    i['profit_center'] = data[0].get('profit_center')
                # return po_data, "项目采购类别为空,生产订单有值"
            elif so_sn:
                filter_sql = f"""SELECT `profit_center` FROM `t_sales_order_item` WHERE `po_sn` ='{so_sn}' and `so_items` = '{so_items}'"""
                print("项目采购类别为空,销售有值：sql>>", filter_sql)
                data = db.query_sql(filter_sql)
                print("项目采购类别为空,销售有值：data>>", data)
                if data and data[0].get('profit_center'):
                    i['profit_center'] = data[0].get('profit_center')
                print("项目采购类别为空,销售有值")
                # return po_data, "项目采购类别为空,销售有值"
            elif wbs_elements:
                filter_sql = f"""SELECT `settle_type_flag`,`profit_center` FROM `t_co_wbs_element` WHERE `wbs_elements` ='{wbs_elements}' """
                print("项目采购类别为空,wbs元素有值：sql>>", filter_sql)
                data = db.query_sql(filter_sql)
                print("项目采购类别为空,wbs元素有值：data>>", data)
                if data and str(data[0].get('wbs_elements')) == "1":
                    i['profit_center'] = data[0].get('profit_center')
                print("项目采购类别为空,wbs元素有值", filter_sql)
            elif cost_business_object:
                filter_sql = f"""select `t1`.`profit_center`
                                from `t_co_cost_event` `t1` 
                                left join `t_bd_cost_event_type` `t2` on `t1`.`cost_business_type`  = `t2`.`cost_business_type` and `t2`.`internal_sort` = '1'
                                where `t1`.`cost_business_object` = '{cost_business_object}'"""
                print("项目采购类别为空,成本事项1", filter_sql)
                data = db.query_sql(filter_sql)
                print("项目采购类别为空,成本事项1：data>>", data)
                if data and data[0].get('profit_center'):
                    i['profit_center'] = data[0].get('profit_center')
            elif cost_center and account_allocation_category:
                filter_sql = f"""SELECT `profit_center` FROM `t_coc_cost_center` WHERE `cost_center` ='{cost_center}' """
                print("项目采购类别为空,成本中心有值：sql>>>>", filter_sql)
                data = db.query_sql(filter_sql)
                print("项目采购类别为空,成本中心data>>>", filter_sql)
                if data and data[0].get('profit_center'):
                    i['profit_center'] = data[0].get('profit_center')

            if (not any([po_sn, prodosn, cost_center, cost_business_object, wbs_elements, so_sn])) and mat_code:
                sql = f"""select `profit_center` from `t_mmd_material_financial_data` where `mat_code` = '{mat_code}' and `plant_code` = '{plant_code}'"""
                print("六个条件为空，物料编码有值：sql>>>>", sql)
                t_mmd_material_financial_data = db.query_sql(sql)
                print("六个条件为空，物料编码有值：data>>>>", t_mmd_material_financial_data)
                if t_mmd_material_financial_data and t_mmd_material_financial_data[0].get('profit_center'):
                    i['profit_center'] = t_mmd_material_financial_data[0].get('profit_center')


        item_profit_center = i.get("profit_center", '')
        if not item_profit_center:
            print("没有找到利润中心")
            filter_sql = f"""SELECT `profit_center_account_flag` FROM `t_profit_center_account_activation` 
                                        WHERE `company_code` ='{company_code}' """
            print("项目采购类别为空,没有利润中心>>sql>>", filter_sql)
            data = db.query_sql(filter_sql)
            print("项目采购类别为空,没有利润中心>>sql>>", data)
            if data and data[0].get('profit_center_account_flag') == 1:
                return items, "利润中心核算激活，必须输入利润中心"
    return items, ""


def get_plant_code_data(plant_code, db):
    if not plant_code:
        return []

    plant_code = list(set(plant_code))

    query_sql = """
        select `plant_code`
        from `t_os_plant`
        where `plant_code` in ('{}')
    """.format("','".join(plant_code))
    data = db.query_sql(query_sql)

    plant_data = []
    for each in data:
        plant_data.append(each['plant_code'])

    return plant_data


def get_plant_storage(plant_code, db):
    if not plant_code:
        return {}

    plant_code = list(set(plant_code))

    query_sql = """
        SELECT
            `plant_code`,
            `stor_loc_code`,
            `negative_inventory_allow`
        FROM
            `t_os_plant_storage_location_alloc`
        WHERE
            `plant_code` in ('{}')
    """.format("','".join(plant_code))
    data = db.query_sql(query_sql)

    dict_plant_storage = {}

    for each in data:
        key = each["plant_code"] + each['stor_loc_code']
        if key not in dict_plant_storage:
            dict_plant_storage[key] = []
            dict_plant_storage[key].append(each)
        else:
            dict_plant_storage[key].append(each)

    return dict_plant_storage


def get_movement_special_inventory_status(movement_type, db):
    if not movement_type:
        return [], [], {}, {}

    query_sql = """
        SELECT
            `movement_type`,
            `special_inventory_status1`,
            `special_inventory_status2`,
            `pur_item_cat`,
            `account_allocation_category`,
            `mat_special_val_mark`,
            `debit_credit_mark`,
            `transaction_type_code`
        FROM
            `t_Inventory_movement_relationship`

    """.format("','".join(movement_type))
    data = db.query_sql(query_sql)

    movement_special_inventory_status1 = []
    movement_special_inventory_status2 = []
    dict_relation = {}
    dict_relation2 = {}
    for each in data:
        movement_special_inventory_status1.append(each['movement_type'] + each['special_inventory_status1'])
        movement_special_inventory_status2.append(each['movement_type'] + each['special_inventory_status2'])
        key = each["movement_type"] + each['pur_item_cat'] + each['account_allocation_category'] + each[
            'special_inventory_status1'] + each['special_inventory_status2'] + each['mat_special_val_mark']
        if key not in dict_relation:
            dict_relation[key] = []
            dict_relation[key].append(each)
        else:
            dict_relation[key].append(each)
        key = each["movement_type"] + each['pur_item_cat'] + each['account_allocation_category'] + each[
            'special_inventory_status1'] + each['special_inventory_status2'] + each['mat_special_val_mark'] + each[
                  'debit_credit_mark']
        if key not in dict_relation2:
            dict_relation2[key] = []
            dict_relation2[key].append(each)
        else:
            dict_relation2[key].append(each)

    return movement_special_inventory_status1, movement_special_inventory_status2, dict_relation, dict_relation2


def get_mat_code_info(mat_code, plant_code, db):
    if not mat_code and not plant_code:
        return {}

    mat_code = list(set(mat_code))
    plant_code = list(set(plant_code))

    query_sql = """
        SELECT
            b.`mat_code`,
            p.`plant_code`,
            b.`basic_uom`,
            t.`qty_update_flag`,
            t.`value_update`,
            p.`batch_mark`,
            p.`quality_inspection_mark`,
            p.`deleted_mark`,
            p.`lock_flag`,
            c.`cost_uom`,
            c.`project_val_mark`,
            c.`so_val_mark`,
            c.`outsource_val_mark`,
            c.`other_special_val_mark`,
            b.`mat_group`,
            c.`price_control`,
            f.`plant_val_class`
        FROM
            `t_mmd_material_basic_data` as b
        JOIN
            `t_mmd_material_plant_data` as p
        ON 
            b.`mat_code` = p.`mat_code`
        LEFT JOIN
            `t_mmd_material_cost_data` as c
        ON 
            b.`mat_code` = c.`mat_code`
        AND 
            p.`plant_code` = c.`plant_code`
        LEFT JOIN
            `t_mmd_material_financial_data` as f
        ON 
            b.`mat_code` = f.`mat_code`
        AND 
            p.`plant_code` = f.`plant_code`
        JOIN 
            `t_mmd_material_type_range_limit` AS t 
        ON 
            t.`mat_type` = b.`mat_type`
        AND t.`plant_code` = p.`plant_code`
        WHERE
            b.`mat_code` in ('{}')
        AND p.`plant_code` in ('{}')
    """.format("','".join(mat_code), "','".join(plant_code))
    data = db.query_sql(query_sql)
    dict_mat_code = {}

    for each in data:
        key = each["mat_code"] + each['plant_code']
        if key not in dict_mat_code:
            dict_mat_code[key] = []
            dict_mat_code[key].append(each)
        else:
            dict_mat_code[key].append(each)

    return dict_mat_code


def get_mat_uom_convert(mat_code, db):
    if not mat_code:
        return {}

    mat_code = list(set(mat_code))

    query_sql = """
        SELECT
            `mat_code`,
            `primary_uom`,
            `primary_uom_qty`,
            `secondary_uom`,
            `secondary_uom_qty`
        FROM
            `t_mmd_uom_conversion` 
        WHERE
            `mat_code` in ('{}') 
    """.format("','".join(mat_code))
    data = db.query_sql(query_sql)

    dict_mat_uom_convert = {}

    for each in data:
        key = each["mat_code"] + each['primary_uom'] + each['secondary_uom']
        if key not in dict_mat_uom_convert:
            dict_mat_uom_convert[key] = []
            dict_mat_uom_convert[key].append(each)
        else:
            dict_mat_uom_convert[key].append(each)

    return dict_mat_uom_convert


def get_mat_code_cost_info(mat_code, plant_code, db):
    if not mat_code and not plant_code:
        return {}

    mat_code = list(set(mat_code))
    plant_code = list(set(plant_code))

    query_sql = """
        SELECT
            `mat_code`,
            `plant_code`,
            `cost_uom`,
            `project_val_mark`,
            `so_val_mark`,
            `outsource_val_mark`,
            `other_special_val_mark`,
            `price_control`
        FROM
            `t_mmd_material_cost_data`
        WHERE
            `mat_code` in ('{}')
        AND `plant_code` in ('{}')
        AND `deleted_mark` = 0
        and `lock_flag` = 0
    """.format("','".join(mat_code), "','".join(plant_code))
    data = db.query_sql(query_sql)
    dict_mat_cost_code = {}

    for each in data:
        key = each["mat_code"] + each['plant_code']
        if key not in dict_mat_cost_code:
            dict_mat_cost_code[key] = []
            dict_mat_cost_code[key].append(each)
        else:
            dict_mat_cost_code[key].append(each)

    return dict_mat_cost_code


def get_pre_md_item(mat_doc_sn, year, db):
    if not mat_doc_sn:
        return {}

    year = [str(x) for x in year]
    query_sql = """
        SELECT
            distinct 
            `company_code`,
            `posting_date`
        FROM
            `t_md_header`
        WHERE
            `mat_doc_sn` in ('{}')
        AND
            `year` in ('{}')
        AND
            `post_code` = '1'
    """.format("','".join(mat_doc_sn), "','".join(year))
    header = db.query_sql(query_sql)

    # 存储所有子查询的列表
    sub_queries1 = []

    query_sql1 = ''

    for each in header:
        name = 't_md_item_' + str(each['company_code']) + '_' + str(each['posting_date'][:4]) + str(
            each['posting_date'][5:7])

        sub_query = """
            select 
                `year`,
                `mat_doc_sn`,
                `mat_doc_items`,
                sum(`transaction_qty`) as `transaction_qty`
            from `{}`
            where `mat_doc_sn` in ('{}')
            and `year` in ('{}')
            and `reversal_mark` = 0
            and `reversed_mark` = 0
            group by `year`,
                        `mat_doc_sn`,
                        `mat_doc_items`
        """.format(name, "','".join(mat_doc_sn), "','".join(year))

        sub_queries1.append(sub_query)

    # 使用 UNION ALL 连接所有子查询，并确保没有多余的 UNION ALL
    if sub_queries1:
        query_sql1 = " UNION ALL ".join(sub_queries1)

    dict_md_info = {}

    if query_sql1:
        data = db.query_sql(query_sql1)

        for each in data:
            key = each['mat_doc_sn'] + str(each["year"]) + str(each['mat_doc_items'])
            if key not in dict_md_info:
                dict_md_info[key] = []
                dict_md_info[key].append(each)
            else:
                dict_md_info[key].append(each)

    return dict_md_info


def get_md_item(mat_doc_sn, year, db):
    if not mat_doc_sn:
        return [], {}, {}, {}

    year = [str(x) for x in year]
    query_sql = """
        SELECT
            distinct 
            `company_code`,
            `posting_date`
        FROM
            `t_md_header`
        WHERE
            `mat_doc_sn` in ('{}')
        AND
            `year` in ('{}')
        AND
            `post_code` = '1'
    """.format("','".join(mat_doc_sn), "','".join(year))
    header = db.query_sql(query_sql)

    # 存储所有子查询的列表
    sub_queries1 = []
    sub_queries2 = []
    sub_queries3 = []
    sub_queries4 = []
    query_sql1 = ''
    query_sql2 = ''
    query_sql3 = ''
    query_sql4 = ''

    for each in header:
        name = 't_md_item_' + str(each['company_code']) + '_' + str(each['posting_date'][:4]) + str(
            each['posting_date'][5:7])

        sub_query = """
            select 
                `year`,
                `mat_doc_sn`,
                `mat_doc_items`
            from `{}`
            where `mat_doc_sn` in ('{}')
            and `year` in ('{}')
            and `debit_credit_mark` = 'Dr'
        """.format(name, "','".join(mat_doc_sn), "','".join(year))

        sub_queries1.append(sub_query)

        sub_query = """
            select 
                `year`,
                `mat_doc_sn`,
                `mat_doc_items`,
                sum( `transaction_qty` ) AS `transaction_qty`,
                sum( `cost_qty` ) AS `cost_qty`,
                sum( `basic_qty` ) AS `basic_qty`,
                sum( `parallel_qty` ) AS `parallel_qty` 
            from `{}`
            where `mat_doc_sn` in ('{}')
            and `year` in ('{}')
            and `reversed_mark` = 0
            and `reversal_mark` = 0
            and `debit_credit_mark` = 'Dr'
            group by `year`,
                    `mat_doc_sn`,
                    `mat_doc_items`
        """.format(name, "','".join(mat_doc_sn), "','".join(year))
        sub_queries2.append(sub_query)

    # 使用 UNION ALL 连接所有子查询，并确保没有多余的 UNION ALL
    if sub_queries1:
        query_sql1 = " UNION ALL ".join(sub_queries1)
    if sub_queries2:
        query_sql2 = " UNION ALL ".join(sub_queries2)

    dict_md_info = {}

    if query_sql1:
        data = db.query_sql(query_sql1)

        for each in data:
            key = str(each["year"]) + each['mat_doc_sn'] + str(each['mat_doc_items'])
            if key not in dict_md_info:
                dict_md_info[key] = []
                dict_md_info[key].append(each)
            else:
                dict_md_info[key].append(each)

    dict_md_info1 = {}
    if query_sql2:
        data = db.query_sql(query_sql2)

        for each in data:
            key = str(each["year"]) + each['mat_doc_sn'] + str(each['mat_doc_items'])
            if key not in dict_md_info1:
                dict_md_info1[key] = []
                dict_md_info1[key].append(each)
            else:
                dict_md_info1[key].append(each)

    table = db.get_tables_like_only_name('t_md_item_', '', '')
    for each in table:
        sub_query = """
            select 
                `rel_document_year`,
                `rel_document_no`,
                `ref_document_mat`,
                sum( `transaction_qty` ) AS `transaction_qty`,
                sum( `cost_qty` ) AS `cost_qty`,
                sum( `basic_qty` ) AS `basic_qty`,
                sum( `parallel_qty` ) AS `parallel_qty` 
            from `{}`
            where `rel_document_no` in ('{}')
            and `rel_document_year` in ('{}')
            and `reversed_mark` = 0
            and `reversal_mark` = 0
            and `debit_credit_mark` = 'Cr'
            group by `rel_document_year`,
                    `rel_document_no`,
                    `ref_document_mat`
        """.format(each, "','".join(mat_doc_sn), "','".join(year))
        sub_queries3.append(sub_query)

    if sub_queries3:
        query_sql3 = " UNION ALL ".join(sub_queries3)

    dict_md_info2 = {}
    if query_sql3:
        data = db.query_sql(query_sql3)

        for each in data:
            key = str(each["rel_document_year"]) + each['rel_document_no'] + str(each['ref_document_mat'])
            if key not in dict_md_info2:
                dict_md_info2[key] = []
                dict_md_info2[key].append(each)
            else:
                dict_md_info2[key].append(each)

    table = db.get_tables_like_only_name('t_pi_invoice_item_', '', '')
    for each in table:
        sub_query = """
            select
                i.`mat_doc_year`,
                i.`mat_doc_sn`,
                i.`mat_doc_items`,
                sum( `order_qty` ) AS `transaction_qty`,
                sum( `cost_qty` ) AS `cost_qty`,
                sum( `basic_qty` ) AS `basic_qty`,
                sum( `parallel_qty` ) AS `parallel_qty`
            from `{}` as i
            join `t_pi_invoice_header` as h on h.`invoice_doc_sn` = i.`invoice_doc_sn`
            and h.`pi_doc_year` = i.`pi_doc_year`
            where i.`mat_doc_year` in ('{}')
            and i.`mat_doc_sn` in ('{}')
            and h.`reversal_mark` = 0
            and h.`reversed_mark` = 0
            group by i.`mat_doc_year`,
                    i.`mat_doc_sn`,
                    i.`mat_doc_items`
        """.format(each, "','".join(year), "','".join(mat_doc_sn))
        sub_queries4.append(sub_query)

    if sub_queries4:
        query_sql4 = " UNION ALL ".join(sub_queries4)

    dict_pi_invoice_info = {}
    if query_sql4:
        data = db.query_sql(query_sql4)

        for each in data:
            key = str(each["mat_doc_year"]) + each['mat_doc_sn'] + str(each['mat_doc_items'])
            if key not in dict_pi_invoice_info:
                dict_pi_invoice_info[key] = []
                dict_pi_invoice_info[key].append(each)
            else:
                dict_pi_invoice_info[key].append(each)

    return dict_md_info, dict_md_info1, dict_md_info2, dict_pi_invoice_info


def get_po_header(po_sn, db):
    if not po_sn:
        return {}

    po_sn = list(set(po_sn))

    query_sql = """
        SELECT
            `po_sn`,
            `approval_status`,
            `deleted_mark`,
            `lock_flag`,
            `currency_code`,
            `vendor_code`,
            `po_type`
        FROM
            `t_po_header`
        WHERE
            `po_sn` in ('{}')
    """.format("','".join(po_sn))
    data = db.query_sql(query_sql)

    dict_po_header = {}

    for each in data:
        key = each["po_sn"]
        if key not in dict_po_header:
            dict_po_header[key] = []
            dict_po_header[key].append(each)
        else:
            dict_po_header[key].append(each)

    return dict_po_header


def get_po_item(po_sn, db):
    if not po_sn:
        return {}

    po_sn = list(set(po_sn))

    query_sql = """
        SELECT
            `po_sn`,
            `po_items`,
            `pur_item_cat`,
            `receipt_completed_flag`,
            `deleted_mark`,
            `lock_flag`,
            `pricing_unit_of_measure`,
            `free_mark`,
            `return_flag`,
            `unit_price_excluding_tax`,
            `account_allocation_category`,
            `unlimited_tolerance`,
            `underdelivery_tolerance`,
            `overdelivery_tolerance`,
            `order_qty`,
            `received_pur_qty`,
            `pur_uom`,
            0 as `rework_mark`,
            `rework_type`,
            `sequence_number`,
            `first_storage_completely_valued`,
            `price_unit`
        FROM
            `t_po_item`
        WHERE
            `po_sn` in ('{}')
    """.format("','".join(po_sn))
    data = db.query_sql(query_sql)

    dict_po_item = {}

    for each in data:
        key = each["po_sn"] + str(each['po_items'])
        if key not in dict_po_item:
            dict_po_item[key] = []
            dict_po_item[key].append(each)
        else:
            dict_po_item[key].append(each)

    return dict_po_item


def get_valgroup_value(po_sn, db):
    if not po_sn:
        return {}

    query_sql = """
        SELECT
            i.`po_sn`,
            i.`po_items`,
            c.`plant_code`,
            i.`mat_code`,
            c.`valgroup_value` 
        FROM
            `t_po_item` AS i
            JOIN `t_mmd_material_cost_data` AS c ON c.`mat_code` = i.`mat_code` 
        WHERE
            i.`po_sn` in ('{}')
    """.format("','".join(po_sn))
    data = db.query_sql(query_sql)

    dict_valgroup_value = {}

    for each in data:
        key = each["po_sn"] + str(each['po_items']) + each['plant_code']
        if key not in dict_valgroup_value:
            dict_valgroup_value[key] = []
            dict_valgroup_value[key].append(each)
        else:
            dict_valgroup_value[key].append(each)

    return dict_valgroup_value


def get_po_batch_binding(po_sn, db):
    if not po_sn:
        return {}

    query_sql = """
        SELECT
            `po_sn`,
            `po_items`,
            `rel_po_component_number`,
            `rel_po_comp_batch_num`,
            `allocated_qty`,
            `deducted_quantity_base`,
            `batch_sn`
        FROM
            `t_po_batch_binding`
        WHERE
            `po_sn` in ('{}')
    """.format("','".join(po_sn))
    data = db.query_sql(query_sql)

    dict_po_binding = {}

    for each in data:
        key = each["po_sn"] + str(each['po_items']) + str(each['rel_po_component_number']) + str(
            each['rel_po_comp_batch_num'])
        if key not in dict_po_binding:
            dict_po_binding[key] = []
            dict_po_binding[key].append(each)
        else:
            dict_po_binding[key].append(each)

    return dict_po_binding


def get_prodosn_data(prodosn, db):
    if not prodosn:
        return {}

    prodosn = list(set(prodosn))

    query_sql = """
        SELECT
            `prodosn`,
            `receipt_completed_flag`,
            `prodo_type`
        FROM
            `t_co_production_order` 
        WHERE
            `prodosn` in ('{}')
        AND `deleted_mark` != 1
        AND `lock_flag` != 1
    """.format("','".join(prodosn))
    data = db.query_sql(query_sql)

    dict_prodosn_data = {}
    for each in data:
        key = each['prodosn']
        if key not in dict_prodosn_data:
            dict_prodosn_data[key] = []
            dict_prodosn_data[key].append(each)
        else:
            dict_prodosn_data[key].append(each)

    return dict_prodosn_data


def get_prodosn_component_data(prodosn, db):
    if not prodosn:
        return {}

    query_sql = """
        SELECT
            `prodosn`,
            `item_no`,
            `issuing_completed_flag`
        FROM
            `t_pro_order_component` 
        WHERE
            `prodosn` in ('{}')
        AND `deleted_mark` != 1
    """.format("','".join(prodosn))
    data = db.query_sql(query_sql)

    dict_prodosn_component_data = {}
    for each in data:
        key = each['prodosn'] + str(each['item_no'])
        if key not in dict_prodosn_component_data:
            dict_prodosn_component_data[key] = []
            dict_prodosn_component_data[key].append(each)
        else:
            dict_prodosn_component_data[key].append(each)

    return dict_prodosn_component_data


def get_dn_header(dn_sn, db):
    if not dn_sn:
        return {}

    dn_sn = list(set(dn_sn))

    query_sql = """
        SELECT
            `dn_sn`,
            `posting_status`,
            `pod_status`,
            `billing_status`
        FROM
            `t_dn_header` 
        WHERE
            `dn_sn` in ('{}')
        AND `deleted_mark` = 0 
        AND `lock_flag` = 0 
    """.format("','".join(dn_sn))
    data = db.query_sql(query_sql)

    dict_dn_sn_header = {}

    for each in data:
        key = each["dn_sn"]
        if key not in dict_dn_sn_header:
            dict_dn_sn_header[key] = []
            dict_dn_sn_header[key].append(each)
        else:
            dict_dn_sn_header[key].append(each)

    return dict_dn_sn_header


def get_dn_sn_item(dn_sn, db):
    if not dn_sn:
        return []

    dn_sn = list(set(dn_sn))

    query_sql = """
        SELECT
            `dn_sn`,
            `dn_item`
        FROM
            `t_dn_item` 
        WHERE
            `dn_sn` in ('{}')
    """.format("','".join(dn_sn))
    data = db.query_sql(query_sql)

    dict_dn_sn_item = {}
    for each in data:
        key = each['dn_sn'] + str(each['dn_item'])
        if key not in dict_dn_sn_item:
            dict_dn_sn_item[key] = []
            dict_dn_sn_item[key].append(each)
        else:
            dict_dn_sn_item[key].append(each)

    return dict_dn_sn_item


def get_picking_document_info(picking_document, db):
    if not picking_document:
        return {}

    picking_document = list(set(picking_document))

    query_sql = """
        SELECT
            `picking_document`,
            `batch_item`,
            `posting_status`,
            `pod_status`,
            `billing_status` 
        FROM
            `t_dn_inventory_alloc`
        WHERE
            `picking_document` in ('{}')
    """.format("','".join(picking_document))
    data = db.query_sql(query_sql)

    dict_picking_document = {}

    for each in data:
        key = each['picking_document'] + str(each['batch_item'])
        if key not in dict_picking_document:
            dict_picking_document[key] = []
            dict_picking_document[key].append(each)
        else:
            dict_picking_document[key].append(each)

    return dict_picking_document


def get_procure_dn_sn_info(procure_dn_sn, db):
    if not procure_dn_sn:
        return []

    procure_dn_sn = list(set(procure_dn_sn))

    query_sql = """
        SELECT
            h.`pr_dn_sn`,
            i.`dn_item`
        FROM
            `t_dn_procure_header` as h
        JOIN
            `t_dn_procure_item` as i
        ON h.`pr_dn_sn` = i.`pr_dn_sn`
        WHERE
            h.`pr_dn_sn` in ('{}')
    """.format("','".join(procure_dn_sn))
    data = db.query_sql(query_sql)

    dict_procure_dn_sn_data = {}
    for each in data:
        key = each['pr_dn_sn'] + str(each['dn_item'])
        if key not in dict_procure_dn_sn_data:
            dict_procure_dn_sn_data[key] = []
            dict_procure_dn_sn_data[key].append(each)
        else:
            dict_procure_dn_sn_data[key].append(each)

    return dict_procure_dn_sn_data


def get_ro_sn_info(ro_sn, db):
    if not ro_sn:
        return []

    ro_sn = list(set(ro_sn))

    query_sql = """
        SELECT
            h.`res_doc_sn`,
            i.`res_doc_items`
        FROM
            `t_res_header` as h
        JOIN
            `t_res_item` as i
        ON h.`res_doc_sn` = i.`res_doc_sn`
        WHERE
            h.`res_doc_sn` in ('{}')
    """.format("','".join(ro_sn))
    data = db.query_sql(query_sql)

    dict_ro_sn_data = {}
    for each in data:
        key = each['res_doc_sn'] + str(each['res_doc_items'])
        if key not in dict_ro_sn_data:
            dict_ro_sn_data[key] = []
            dict_ro_sn_data[key].append(each)
        else:
            dict_ro_sn_data[key].append(each)

    return dict_ro_sn_data


def get_so_sn_info(so_sn, db):
    if not so_sn:
        return []

    so_sn = list(set(so_sn))

    query_sql = """
        SELECT
            h.`so_sn`,
            i.`so_items`
        FROM
            `t_sales_order_header` as h
        JOIN
            `t_sales_order_item` as i
        ON h.`so_sn` = i.`so_sn`
        WHERE
            h.`so_sn` in ('{}')
    """.format("','".join(so_sn))
    data = db.query_sql(query_sql)

    dict_so_sn_data = {}
    for each in data:
        key = each['so_sn'] + str(each['so_items'])
        if key not in dict_so_sn_data:
            dict_so_sn_data[key] = []
            dict_so_sn_data[key].append(each)
        else:
            dict_so_sn_data[key].append(each)

    return dict_so_sn_data


def get_customer_code_info(customer_code, db):
    if not customer_code:
        return []

    customer_code = list(set(customer_code))

    query_sql = """
        SELECT
            `customer_code`
        FROM
            `t_bpc_customer_basic_data`
        WHERE
            `customer_code` in ('{}')
    """.format("','".join(customer_code))
    data = db.query_sql(query_sql)

    dict_customer_code_data = {}
    for each in data:
        key = each['customer_code']
        if key not in dict_customer_code_data:
            dict_customer_code_data[key] = []
            dict_customer_code_data[key].append(each)
        else:
            dict_customer_code_data[key].append(each)

    return dict_customer_code_data


def get_vendor_code_info(vendor_code, db):
    if not vendor_code:
        return []

    vendor_code = list(set(vendor_code))

    query_sql = """
        SELECT
            `vendor_code`
        FROM
            `t_bpv_vendor_basic_data`
        WHERE
            `vendor_code` in ('{}')
    """.format("','".join(vendor_code))
    data = db.query_sql(query_sql)

    dict_vendor_code_data = {}
    for each in data:
        key = each['vendor_code']
        if key not in dict_vendor_code_data:
            dict_vendor_code_data[key] = []
            dict_vendor_code_data[key].append(each)
        else:
            dict_vendor_code_data[key].append(each)

    return dict_vendor_code_data


def get_cost_center_info(cost_center, db):
    if not cost_center:
        return []

    cost_center = list(set(cost_center))

    query_sql = """
        SELECT
            c.`cost_center`,
            p.`plant_code`
        FROM
            `t_coc_cost_center` AS c
        JOIN
            `t_os_company_plant_alloc` AS p
        ON
            p.`company_code` = c.`company_code` 
        WHERE
            c.`cost_center` in ('{}')
    """.format("','".join(cost_center))
    data = db.query_sql(query_sql)

    dict_cost_center_data = {}
    for each in data:
        key = each['cost_center'] + each['plant_code']
        if key not in dict_cost_center_data:
            dict_cost_center_data[key] = []
            dict_cost_center_data[key].append(each)
        else:
            dict_cost_center_data[key].append(each)

    return dict_cost_center_data


def get_cost_business_object_info(cost_business_object, db):
    if not cost_business_object:
        return []

    cost_business_object = list(set(cost_business_object))

    query_sql = """
        SELECT
            c.`cost_business_object`,
            p.`plant_code`
        FROM
            `t_co_cost_event` AS c
        JOIN
            `t_os_company_plant_alloc` AS p
        ON
            p.`company_code` = c.`company_code` 
        WHERE
            c.`cost_business_object` in ('{}')
    """.format("','".join(cost_business_object))
    data = db.query_sql(query_sql)

    dict_cost_business_object_data = {}
    for each in data:
        key = each['cost_business_object'] + each['plant_code']
        if key not in dict_cost_business_object_data:
            dict_cost_business_object_data[key] = []
            dict_cost_business_object_data[key].append(each)
        else:
            dict_cost_business_object_data[key].append(each)

    return dict_cost_business_object_data


def get_profit_center_info(profit_center, db):
    if not profit_center:
        return []

    profit_center = list(set(profit_center))

    query_sql = """
        SELECT
            p.`profit_center`,
            cp.`plant_code`
        FROM
            `t_os_profit_center` as p
        JOIN
            `t_os_profit_center_company_allocation` as c
        ON
            p.`profit_center` = c.`profit_center`
        JOIN
            `t_os_company_plant_alloc` as cp
        ON
            cp.`company_code` = c.`company_code`
        WHERE
            p.`profit_center` in ('{}')
    """.format("','".join(profit_center))
    data = db.query_sql(query_sql)

    dict_profit_center_data = {}
    for each in data:
        key = each['profit_center'] + each['plant_code']
        if key not in dict_profit_center_data:
            dict_profit_center_data[key] = []
            dict_profit_center_data[key].append(each)
        else:
            dict_profit_center_data[key].append(each)
    return dict_profit_center_data


def get_equipment_code_info(equipment_code, db):
    if not equipment_code:
        return []

    equipment_code = list(set(equipment_code))

    query_sql = """
        SELECT
            `equipment_code`
        FROM
            `t_eq_equipment`
        WHERE
            `equipment_code` in ('{}')
    """.format("','".join(equipment_code))
    data = db.query_sql(query_sql)

    dict_equipment_code_data = {}
    for each in data:
        key = each['equipment_code']
        if key not in dict_equipment_code_data:
            dict_equipment_code_data[key] = []
            dict_equipment_code_data[key].append(each)
        else:
            dict_equipment_code_data[key].append(each)

    return dict_equipment_code_data


def get_company_info_by_plant(plant_code, db):
    if not plant_code:
        return {}

    plant_code = list(set(plant_code))

    query_sql = """
        SELECT
            p.`plant_code`,
            c.`company_code`,
            c.`basic_currency`,
            c.`rate_type` 
        FROM
            `t_os_company` AS c
            JOIN `t_os_company_plant_alloc` AS p ON p.`company_code` = c.`company_code` 
        WHERE
            p.`plant_code` in ('{}')
    """.format("','".join(plant_code))
    data = db.query_sql(query_sql)

    dict_company = {}

    for each in data:
        key = each['plant_code']
        if key not in dict_company:
            dict_company[key] = []
            dict_company[key].append(each)
        else:
            dict_company[key].append(each)

    return dict_company


def get_movement_label_info(movement_type, db):
    if not movement_type:
        return {}, {}, {}

    query_sql = """
        SELECT
            u.`consumption_posting_label`,
            u.`item_indicator`,
            u.`value_update`,
            u.`qty_update_flag`,
            u.`pur_item_cat`,
            u.`account_allocation_category`,
            u.`movement_type`,
            u.`material_value_update`
        FROM
            `t_material_movement_update_label` AS u

    """.format("','".join(movement_type))
    data = db.query_sql(query_sql)

    dict_movement_label1 = {}
    dict_movement_label2 = {}
    dict_movement_label3 = {}

    for each in data:
        key1 = each['pur_item_cat'] + each['account_allocation_category'] + each['movement_type'] + each[
            'material_value_update']
        if key1 not in dict_movement_label1:
            dict_movement_label1[key1] = []
            dict_movement_label1[key1].append(each)
        else:
            dict_movement_label1[key1].append(each)

        key2 = each['pur_item_cat'] + each['account_allocation_category'] + each['material_value_update']
        if key2 not in dict_movement_label2:
            dict_movement_label2[key2] = []
            dict_movement_label2[key2].append(each)
        else:
            dict_movement_label2[key2].append(each)

        key3 = each['pur_item_cat'] + each['account_allocation_category'] + each['material_value_update']
        if key3 not in dict_movement_label3:
            dict_movement_label3[key3] = []
            dict_movement_label3[key3].append(each)
        else:
            dict_movement_label3[key3].append(each)

    # query_sql = """
    #     SELECT
    #         u.consumption_posting_label,
    #         u.item_indicator,
    #         u.value_update,
    #         u.qty_update_flag,
    #         u.pur_item_cat,
    #         u.account_allocation_category,
    #         u.movement_type,
    #         u.material_value_update
    #     FROM
    #         t_material_movement_update_label AS u
    #     WHERE
    #         u.movement_type = ''
    # """
    # data = []
    # data = db.query_sql(query_sql)

    # dict_movement_label2 = {}
    #
    # for each in data:
    #     key = each['pur_item_cat'] + each['account_allocation_category'] + each['material_value_update']
    #     if key not in dict_movement_label2:
    #         dict_movement_label2[key] = []
    #         dict_movement_label2[key].append(each)
    #     else:
    #         dict_movement_label2[key].append(each)

    # query_sql = """
    #     SELECT
    #         u.consumption_posting_label,
    #         u.item_indicator,
    #         u.value_update,
    #         u.qty_update_flag,
    #         u.pur_item_cat,
    #         u.account_allocation_category,
    #         u.movement_type,
    #         u.material_value_update
    #     FROM
    #         t_material_movement_update_label AS u
    # """
    # data = []
    # data = db.query_sql(query_sql)

    # dict_movement_label3 = {}
    #
    # for each in data:
    #     key = each['pur_item_cat'] + each['account_allocation_category'] + each['material_value_update']
    #     if key not in dict_movement_label3:
    #         dict_movement_label3[key] = []
    #         dict_movement_label3[key].append(each)
    #     else:
    #         dict_movement_label3[key].append(each)

    return dict_movement_label1, dict_movement_label2, dict_movement_label3


def get_mat_code_and_batch(mat_code, batch, db):
    if not mat_code and not batch:
        return []

    mat_code = list(set(mat_code))

    query_sql = """
        SELECT
            `mat_code`,
            `batch_sn`,
            `batch_status_mark`
        FROM
            `t_batch_number`
        WHERE
            `mat_code` in ('{}')
    """.format("','".join(mat_code))
    data = db.query_sql(query_sql)

    dict_mat_batch = {}
    for each in data:
        key = each['mat_code'] + each['batch_sn']
        if key not in dict_mat_batch:
            dict_mat_batch[key] = []
            dict_mat_batch[key].append(each)
        else:
            dict_mat_batch[key].append(each)

    return dict_mat_batch


def get_inv_transfer_order_item(inv_transfer_order_no, db):
    if not inv_transfer_order_no:
        return {}

    dict_inv_transfer_order_item = {}

    inv_transfer_order_no = list(set(inv_transfer_order_no))

    query_sql = """
        SELECT  `inv_transfer_order_no`,
                `inv_transfer_order_items`,
                `issuing_enabled_flag`
        FROM    `t_inventory_transfer_item`
        WHERE   `inv_transfer_order_no` IN ('{}')
    """.format("','".join(inv_transfer_order_no))

    data = db.query_sql(query_sql)

    for each in data:
        key = each['inv_transfer_order_no'] + str(each['inv_transfer_order_items'])
        if key not in dict_inv_transfer_order_item:
            dict_inv_transfer_order_item[key] = []
            dict_inv_transfer_order_item[key].append(each)
        else:
            dict_inv_transfer_order_item[key].append(each)

    return dict_inv_transfer_order_item


def get_inv_transfer_order(inv_transfer_order_no, db):
    if not inv_transfer_order_no:
        return {}

    dict_inv_transfer_order = {}

    inv_transfer_order_no = list(set(inv_transfer_order_no))

    query_sql = """
        SELECT  `inv_transfer_order_no`
        FROM    `t_inventory_transfer_header`
        WHERE   `inv_transfer_order_no` IN ('{}')
    """.format("','".join(inv_transfer_order_no))

    data = db.query_sql(query_sql)

    for each in data:
        key = each['inv_transfer_order_no']
        if key not in dict_inv_transfer_order:
            dict_inv_transfer_order[key] = []
            dict_inv_transfer_order[key].append(each)
        else:
            dict_inv_transfer_order[key].append(each)

    return dict_inv_transfer_order


def get_mat_insp_info(mat_code, plant_code, db):
    if not mat_code and not plant_code:
        return []

    mat_code = list(set(mat_code))
    plant_code = list(set(plant_code))

    query_sql = """
        SELECT
            `mat_code`,
            `plant_code`,
            `inspection_type`
        FROM
            `t_mmd_material_quality_Inspection_data`
        WHERE
            `mat_code` in ('{}')
        AND `plant_code` in ('{}')
        AND `activation_flag` = 1
    """.format("','".join(mat_code), "','".join(plant_code))
    data = db.query_sql(query_sql)

    dict_mat_insp = {}
    for each in data:
        key = each['mat_code'] + each['plant_code'] + each['inspection_type']
        if key not in dict_mat_insp:
            dict_mat_insp[key] = []
            dict_mat_insp[key].append(each)
        else:
            dict_mat_insp[key].append(each)

    return dict_mat_insp


def get_all_inventory_status(db):
    dict_inventory_status = {}

    query_sql = """
        SELECT  `inventory_status`,
                `inventory_status_description`
        FROM    `t_inventory_status`
    """
    data = db.query_sql(query_sql)

    dict_inventory_status = {}
    for each in data:
        key = each['inventory_status']
        if key not in dict_inventory_status:
            dict_inventory_status[key] = []
            dict_inventory_status[key].append(each)
        else:
            dict_inventory_status[key].append(each)

    return dict_inventory_status


def get_po_price_data(po_sn, db):
    if not po_sn:
        return {}

    po_sn = list(set(po_sn))

    query_sql = """
        SELECT
            p.*,
            i.`first_storage_completely_valued`,
            h.`vendor_code` as `vendor_code2`
        FROM
            `t_po_price_data` AS p
        JOIN `t_po_item` AS i 
        ON p.`po_sn` = i.`po_sn` 
        AND p.`po_items` = i.`po_items` 
        JOIN `t_po_header` as h
        ON h.`po_sn` = p.`po_sn`
        WHERE
            p.`po_sn` in ('{}')
    """.format("','".join(po_sn))
    data = []
    data = db.query_sql(query_sql)

    dict_price_data = {}

    for each in data:
        key = each['po_sn'] + str(each['po_items'])
        if key not in dict_price_data:
            dict_price_data[key] = []
            dict_price_data[key].append(each)
        else:
            dict_price_data[key].append(each)

    return dict_price_data


# 检查过账代码1的参数
def check_data_postcode1(user_id, head, item, db):
    code = 200
    msg = ""
    error_list = []

    # 增强 -- 检验前
    code, msg, error_list, head, item = before_check(user_id, head, item)
    if code != 200:
        return code, msg, error_list, [], [], []

    dict_movement_type = {}
    movement_type = []
    plant_code = []
    plant_code_data = []
    dict_plant_storage = {}
    movement_special_inventory_status1 = []
    movement_special_inventory_status2 = []
    mat_code = []
    dict_mat_code = {}
    dict_mat_code_cost = {}
    po_sn = []
    dict_po_header = {}
    dict_po_item = {}
    prodosn = []
    dict_prodosn_data = {}
    dn_sn = []
    dict_dn_sn_header = {}
    dict_dn_sn_item = {}
    picking_document = []
    dict_picking_document = {}
    procure_dn_sn = []
    dict_procure_dn_sn_data = {}
    ro_sn = []
    dict_ro_sn_data = {}
    so_sn = []
    dict_so_sn_data = {}
    customer_code = []
    dict_customer_code_data = {}
    vendor_code = []
    dict_vendor_code_data = {}
    cost_center = []
    dict_cost_center_data = {}
    cost_business_object = []
    dict_cost_business_object_data = {}
    profit_center = []
    dict_profit_center_data = {}
    equipment_code = []
    dict_equipment_code_data = {}
    dict_company = {}
    dict_relation = {}
    dict_relation2 = {}
    dict_movement_label1 = {}
    dict_movement_label2 = {}
    dict_movement_label3 = {}
    dict_mat_batch = {}
    batch = []
    dict_mat_insp = {}
    dict_price_data = {}
    mat_doc_sn = []
    mat_year = []
    dict_inventory_status = {}
    inv_transfer_order_no = []
    dict_inv_transfer_order = {}
    dict_inv_transfer_order_item = {}
    pre_mat_doc_sn = []
    pre_mat_year = []
    dict_pre_md = {}

    # 性能优化
    for each in item:
        # 移动类型
        if each.get("movement_type", "") != "":
            movement_type.append(each['movement_type'])
        # 工厂
        if each.get("plant_code", "") != "":
            plant_code.append(each['plant_code'])

        # 物料编码
        if each.get("mat_code", "") != "":
            mat_code.append(each['mat_code'])

        # 采购订单
        if each.get("rel_po_sn", '') != '':
            po_sn.append(each['rel_po_sn'])
        if each.get('po_sn', '') != '':
            po_sn.append(each['po_sn'])

        # 生产订单
        if each.get('prodosn', '') != '':
            prodosn.append(each['prodosn'])

        # 交货单
        if each.get('rel_dn_sn', '') != '':
            dn_sn.append(each['rel_dn_sn'])
        # 拣配单
        if each.get('picking_document', '') != '':
            picking_document.append(each['picking_document'])

        # 采购交货单
        if each.get('rel_procure_dn_sn', '') != '':
            procure_dn_sn.append(each['rel_procure_dn_sn'])

        # 预留
        if each.get('ro_sn', '') != '':
            ro_sn.append(each['ro_sn'])

        # 销售订单
        if each.get('rel_so_sn', '') != '':
            so_sn.append(each['rel_so_sn'])
        if each.get('so_sn', '') != '':
            so_sn.append(each['so_sn'])

        # 客户
        if each.get('customer_code', '') != '':
            customer_code.append(each['customer_code'])

        # 供应商
        if each.get('vendor_code', '') != '':
            vendor_code.append(each['vendor_code'])

        # 成本中心
        if each.get('cost_center', '') != '':
            cost_center.append(each['cost_center'])

        # 成本事项
        if each.get('cost_business_object', '') != '':
            cost_business_object.append(each['cost_business_object'])
        if each.get('cost_business_object1', '') != '':
            cost_business_object.append(each['cost_business_object1'])

        # 利润中心
        if each.get('profit_center', '') != '':
            profit_center.append(each['profit_center'])

        # 设备
        if each.get('equipment_code', '') != '':
            equipment_code.append(each['equipment_code'])

        # 批次
        if each.get('batch_sn', '') != '':
            batch.append(each['batch_sn'])

        # 物料凭证
        if each.get('rel_document_no', '') != '':
            mat_doc_sn.append(each['rel_document_no'])
        # 物料凭证年度
        if each.get('rel_document_year', '') != '':
            mat_year.append(each['rel_document_year'])

        # 库存调拨单
        if each.get("inv_transfer_order_no", "") != '':
            inv_transfer_order_no.append(each['inv_transfer_order_no'])

        # 前序物料凭证
        if each.get('pre_document_no', '') != '':
            pre_mat_doc_sn.append(each['pre_document_no'])
        # 前序物料凭证年度
        if each.get('pre_document_year', '') != '':
            pre_mat_year.append(each['pre_document_year'])

    data_begin = time.time()

    # 获取移动类型属性
    dict_movement_type = get_movement_type_info(movement_type, db)
    # 获取工厂
    plant_code_data = get_plant_code_data(plant_code, db)
    # 获取工厂对应库存地点
    dict_plant_storage = get_plant_storage(plant_code, db)
    # 获取移动类型对应特殊库存状态
    movement_special_inventory_status1, movement_special_inventory_status2, dict_relation, dict_relation2 = get_movement_special_inventory_status(
        movement_type, db)
    # 获取物料主数据信息
    dict_mat_code = get_mat_code_info(mat_code, plant_code, db)
    # 获取物料成本视图
    dict_mat_code_cost = get_mat_code_cost_info(mat_code, plant_code, db)
    # 获取物料单位换算关系
    dict_mat_uom_convert = get_mat_uom_convert(mat_code, db)
    # 获取物料凭证行信息
    dict_md_info, dict_md_info1, dict_md_info2, dict_pi_invoice_info = get_md_item(mat_doc_sn, mat_year, db)
    # 获取采购订单抬头信息
    dict_po_header = get_po_header(po_sn, db)
    # 获取采购订单行项目信息
    dict_po_item = get_po_item(po_sn, db)
    # 获取生产订单
    dict_prodosn_data = get_prodosn_data(prodosn, db)
    # 获取交货单抬头信息
    dict_dn_sn_header = get_dn_header(dn_sn, db)
    # 获取交货单行项目信息
    dict_dn_sn_item = get_dn_sn_item(dn_sn, db)
    # 获取拣配单信息
    dict_picking_document = get_picking_document_info(picking_document, db)
    # 获取采购交货单信息
    dict_procure_dn_sn_data = get_procure_dn_sn_info(procure_dn_sn, db)
    # 获取预留单信息
    dict_ro_sn_data = get_ro_sn_info(ro_sn, db)
    # 获取销售订单信息
    dict_so_sn_data = get_so_sn_info(so_sn, db)
    # 获取客户信息
    dict_customer_code_data = get_customer_code_info(customer_code, db)
    # 获取供应商信息
    dict_vendor_code_data = get_vendor_code_info(vendor_code, db)
    # 获取成本中心
    dict_cost_center_data = get_cost_center_info(cost_center, db)
    # 获取成本事项
    dict_cost_business_object_data = get_cost_business_object_info(cost_business_object, db)
    # 利润中心
    dict_profit_center_data = get_profit_center_info(profit_center, db)
    # 获取设备主数据信息
    dict_equipment_code_data = get_equipment_code_info(equipment_code, db)
    # 按工厂获取公司信息
    dict_company = get_company_info_by_plant(plant_code, db)
    # 获取移动类型配置信息
    dict_movement_label1, dict_movement_label2, dict_movement_label3 = get_movement_label_info(movement_type, db)
    # 获取物料批次信息
    dict_mat_batch = get_mat_code_and_batch(mat_code, batch, db)
    print(f'dict_mat_batch--------------------{dict_mat_batch}')
    # 获取物料质检信息
    dict_mat_insp = get_mat_insp_info(mat_code, plant_code, db)
    # 获取采购订单价格明细
    dict_price_data = get_po_price_data(po_sn, db)
    # 获取库存状态
    dict_inventory_status = get_all_inventory_status(db)
    # 获取库存调拨单
    dict_inv_transfer_order = get_inv_transfer_order(inv_transfer_order_no, db)
    # 获取库存调拨单行
    dict_inv_transfer_order_item = get_inv_transfer_order_item(inv_transfer_order_no, db)
    # 获取前序物料凭证信息
    dict_pre_md = get_pre_md_item(pre_mat_doc_sn, pre_mat_year, db)

    print("取值耗时: ", time.time() - data_begin)

    for each in item:
        # 必输校验
        # 行唯一标识校验
        if each.get("line_id", "") == "":
            error_list.append("行唯一标识必输")
            continue
        # 移动类型校验
        if each.get("movement_type", "") == "":
            error_list.append("行标识{}移动类型必输".format(each["line_id"]))
        # 交易数量
        if Decimal(each.get("transaction_qty", 0)) <= 0:
            error_list.append("行标识{}交易数量必须大于0".format(each["line_id"]))
        # 交易单位
        if each.get("transaction_uom", "") == "":
            error_list.append("行标识{}交易单位必输".format(each["line_id"]))
        # # 基本数量
        # if each.get("basic_qty", 0) == 0:
        #     error_list.append("行标识{}基本数量必输".format(each["line_id"]))
        # # 基本单位
        # if each.get("basic_uom", "") == "":
        #     error_list.append("行标识{}基本单位必输".format(each["line_id"]))
        # # 平行单位
        # if each.get("parallel_uom", "") == "":
        #     error_list.append("行标识{}平行单位必输".format(each["line_id"]))
        # # 平行数量
        # if each.get("parallel_uom", "") == each.get("basic_uom", ""):
        #     each["parallel_qty"] = each["basic_qty"]
        # else:
        #     if each.get("basic_qty", 0) == 0:
        #         each["parallel_qty"] = 0
        #     else:
        #         if each.get("parallel_qty", 0) == 0:
        #             error_list.append("行标识{}平行数量必输".format(each["line_id"]))
        # if each.get("parallel_uom", "") != "":
        #     if each.get("parallel_qty", 0) == 0:
        #         error_list.append("行标识{}平行数量必输".format(each["line_id"]))

        # 关联采购订单
        if each.get("rel_po_sn", "") == "":
            error_list.append("行标识{}关联采购订单必输".format(each["line_id"]))
        # 关联采购订单行号
        if each.get("rel_po_items", 0) == 0:
            error_list.append("行标识{}关联采购订单行号必输".format(each["line_id"]))
        # 工厂代码
        if each.get("plant_code", "") == "":
            error_list.append("行标识{}工厂代码必输".format(each["line_id"]))
        # 库存地点
        if each.get("mat_code", "") != "" and each["special_inventory_status1"] != 'V':
            if each["stor_loc_code"] == "":
                error_list.append("行标识{}库存地点必输".format(each["line_id"]))
        # 库存状态
        if each.get("inventory_status", "") == "" and each.get("mat_code", "") != "":
            error_list.append("行标识{}库存状态必输".format(each["line_id"]))

        # # 特殊库存状态1
        # if each["special_inventory_status1"] == "":
        #     error_list.append("行标识{}特殊库存状态1必输".format(each["line_id"]))
        # # 特殊库存状态1
        # if each["special_inventory_status1"] == "":
        #     error_list.append("行标识{}特殊库存状态1必输".format(each["line_id"]))

        # 存在性校验
        if not error_list:
            # 移动类型校验
            if dict_movement_type.get(each['movement_type']) is None:
                error_list.append("行标识{}移动类型{}不存在".format(each["line_id"], each["movement_type"]))
            else:
                if dict_movement_type[each['movement_type']][0]['post_code'] != head["post_code"]:
                    error_list.append("行标识{}移动类型{}不适用过账码{}".format(each["line_id"], each["movement_type"],
                                                                                head["post_code"]))
            # 工厂代码校验
            if each['plant_code'] not in plant_code_data:
                error_list.append("行标识{}工厂代码{}不存在".format(each["line_id"], each["plant_code"]))
            # 库存地点校验
            if each.get("stor_loc_code", "") != "":

                if dict_plant_storage.get(each["plant_code"] + each["stor_loc_code"]) is None:
                    error_list.append(
                        "行标识{}在工厂{}下库存地点{}未分配".format(each["line_id"], each["plant_code"],
                                                                    each["stor_loc_code"]))
            # 特殊库存状态1校验
            if each.get("special_inventory_status1", "") != "":

                if (each["movement_type"] + each[
                    "special_inventory_status1"]) not in movement_special_inventory_status1:
                    error_list.append(
                        "行标识{}在移动类型{}下特殊库存标识1{}未分配".format(each["line_id"], each["movement_type"],
                                                                             each["special_inventory_status1"]))
            # 库存状态
            if each.get("inventory_status", "") != "":
                if dict_inventory_status.get(each["inventory_status"]) is None:
                    error_list.append("行标识{}库存状态{}不存在".format(each["line_id"], each["inventory_status"]))
            # 物料状态检查
            if each.get("mat_code", "") != "":
                key = each["mat_code"] + each["plant_code"]
                if dict_mat_code.get(key) is None:
                    error_list.append("行标识{}物料编码{}在工厂{}不存在".format(each["line_id"], each["mat_code"], each["plant_code"]))
                else:
                    mat_info = dict_mat_code[key][0]
                    if mat_info.get('deleted_mark', 0) == 1 or mat_info.get('lock_flag', 0) == 1:
                        error_list.append("行标识{}物料编码{}已删除或锁定".format(each["line_id"], each["mat_code"]))
                    elif mat_info.get('value_update', 0) == 1:
                        if dict_mat_code_cost.get(key) is None:
                            error_list.append("行标识{}物料编码{}成本视图未扩".format(each["line_id"], each["mat_code"]))
            # 采购订单状态检查
            # msg = check_po_status(each["rel_po_sn"])
            msg = check_po_status(each["rel_po_sn"], dict_po_header)
            if msg != "":
                error_list.append("行标识{}{}".format(each["line_id"], msg))
            else:
                # 采购订单行检查
                msg = check_po_item_status(head["post_code"], each["rel_po_sn"], each["rel_po_items"], dict_po_item)
                if msg != "":
                    error_list.append("行标识{}{}".format(each["line_id"], msg))

            # 校验采购订单何移动类型
            msg = check_po_and_movement(each, dict_movement_type, dict_po_item, dict_md_info)
            if msg != "":
                error_list.append("行标识{}{}".format(each["line_id"], msg))
            # 华微确认注释1 不需要校验组件 跟批次
            # if each.get("rel_po_component_number", 0) != 0:
            #     # 采购订单行的序号检查
            #     if check_if_po_component_exists(each["rel_po_sn"], each["rel_po_items"], each["rel_po_component_number"]):
            #         error_list.append(
            #             "行标识{}关联采购订单{}行{}项目序号{}不存在".format(each["line_id"], each["rel_po_sn"],
            #                                                                 each["rel_po_items"], each["rel_po_component_number"]))
            # if each.get("rel_po_comp_batch_num", 0) != 0:
            #     # 采购订单库存绑定表检查
            #     if check_if_po_batch_binding_exists(each["rel_po_sn"], each["rel_po_items"], each["rel_po_component_number"],
            #                                         each["rel_po_comp_batch_num"]):
            #         error_list.append("行标识{}关联采购订单{}行{}项目序号{}绑定序号{}不存在".format(each["line_id"],
            #                                                                                         each["rel_po_sn"],
            #                                                                                         each[
            #                                                                                             "rel_po_items"],
            #                                                                                         each["rel_po_component_number"],
            #                                                                                         each["rel_po_comp_batch_num"]))
            if each.get("prodosn", "") != "":
                # 生产订单检查
                if dict_prodosn_data.get(each["prodosn"]) is None:
                    error_list.append("行标识{}生产订单{}不存在".format(each["line_id"], each["prodosn"]))
            if each.get("rel_dn_sn", "") != "":
                # 关联交货单检查
                if dict_dn_sn_header.get(each["rel_dn_sn"]) is None:
                    error_list.append("行标识{}关联交货单{}不存在".format(each["line_id"], each["rel_dn_sn"]))
                elif dict_dn_sn_item.get(each["rel_dn_sn"] + str(each.get("rel_dn_item", 0))) is None:
                    error_list.append("行标识{}关联交货单{}行号{}不存在".format(each["line_id"], each["rel_dn_sn"],
                                                                                each.get("rel_dn_item", 0)))
            if each.get("picking_document", "") != "":
                # 拣配单号检查
                if dict_picking_document.get(each["picking_document"] + str(each.get("batch_item", 0))) is None:
                    error_list.append("行标识{}拣配单号{}不存在".format(each["line_id"], each["picking_document"]))

            if each.get("rel_procure_dn_sn", "") != "":

                if dict_procure_dn_sn_data.get(
                        each["rel_procure_dn_sn"] + str(each.get("rel_procure_dn_item", 0))) is None:
                    error_list.append(
                        "行标识{}关联交货单{}行号{}不存在".format(each["line_id"], each["rel_procure_dn_sn"],
                                                                  each.get("rel_procure_dn_item", 0)))
            if each.get("inv_transfer_order_no", "") != "":
                # 库存调拨单
                if dict_inv_transfer_order.get(each["inv_transfer_order_no"]) is None:
                    error_list.append(
                        "行标识{}库存调拨单{}不存在".format(each["line_id"], each["inv_transfer_order_no"]))
                elif dict_inv_transfer_order_item.get(
                        each["inv_transfer_order_no"] + str(each.get("inv_transfer_order_items", 0))) is None:
                    error_list.append(
                        "行标识{}库存调拨单{}行号{}不存在".format(each["line_id"], each["inv_transfer_order_no"],
                                                                  each.get("inv_transfer_order_items", 0)))

            if each.get("ro_sn", "") != "":
                if dict_ro_sn_data.get(each["ro_sn"] + str(each.get("ro_items", 0))) is None:
                    error_list.append("行标识{}关联预留单{}行号{}不存在".format(each["line_id"], each["ro_sn"],
                                                                                each.get("ro_items", 0)))
            if each.get("rel_so_sn", "") != "":

                if dict_so_sn_data.get(each["rel_so_sn"] + str(each.get("rel_so_items", 0))) is None:
                    error_list.append("行标识{}关联销售订单{}行号{}不存在".format(each["line_id"], each["rel_so_sn"],
                                                                                  each.get("rel_so_items", "")))
            if each.get("special_inventory_status1", "") == "C" or each.get("special_inventory_status1", "") == "CC":
                # 客户检查
                if each.get("customer_code", "") == "":
                    error_list.append("行标识{}客户编码必输".format(each["line_id"]))
                else:
                    if dict_customer_code_data.get(each["customer_code"]) is None:
                        error_list.append("行标识{}客户编码{}不存在".format(each["line_id"], each["customer_code"]))
            else:
                each["customer_code"] = ""

            if each.get("special_inventory_status1", "") == "S":
                # 销售订单检查
                if each.get("so_sn", "") == "" or each.get("so_items", "") == "":
                    error_list.append("行标识{}销售订单信息必输".format(each["line_id"]))
                else:
                    if dict_so_sn_data.get(each.get("so_sn", "") + each.get("so_items", 0)) is None:
                        error_list.append("行标识{}销售订单{}行号{}不存在".format(each["line_id"], each["rel_so_sn"],
                                                                                  each.get("rel_so_items", "")))
            else:
                each["so_sn"] = ""
                each["so_items"] = 0

            if each.get("special_inventory_status1", "") == "P":
                # 项目编码检查
                if each.get("project_sn", "") == "":
                    error_list.append("行标识{}项目编码必输".format(each["line_id"]))
                    # 项目编码检查待定-----
            else:
                each["project_sn"] = ""

            if each.get("special_inventory_status1", "") == "V" or each.get("special_inventory_status1", "") == "SC":
                # 供应商编码检查
                if each.get("vendor_code", "") == "":
                    error_list.append("行标识{}供应商编码必输".format(each["line_id"]))
                else:
                    if dict_vendor_code_data.get(each["vendor_code"]) is None:
                        error_list.append("行标识{}供应商编码{}不存在".format(each["line_id"], each["vendor_code"]))

                if each["special_inventory_status1"] == "V":
                    if each.get("po_sn", "") != "":
                        # 采购订单检查
                        if check_if_po_header_exists(each["po_sn"], db):
                            error_list.append("行标识{}采购订单{}不存在".format(each["line_id"], each["po_sn"]))
                        else:
                            if dict_po_item.get(each["po_sn"] + str(each.get("po_items", 0))) is None:
                                error_list.append(
                                    "行标识{}采购订单{}行号{}不存在".format(each["line_id"], each["rel_so_sn"],
                                                                            each.get("rel_so_items", "")))
                else:
                    each["po_sn"] = ""
                    each["po_items"] = 0
            else:
                each["vendor_code"] = ""
                each["po_sn"] = ""
                each["po_items"] = 0

            if each.get("cost_center", "") != "":
                # 成本中心检查
                if dict_cost_center_data.get(each["cost_center"] + each["plant_code"]) is None:
                    error_list.append(
                        "行标识{}成本中心{}在工厂{}对应的公司代码不存在".format(each["line_id"], each["cost_center"],
                                                                                each["plant_code"]))
            if each.get("cost_business_object", "") != "":
                # 成本事项检查
                if dict_cost_business_object_data.get(each["cost_business_object"] + each["plant_code"]) is None:
                    error_list.append(
                        "行标识{}成本事项{}在工厂{}对应的公司代码不存在".format(each["line_id"],
                                                                                each["cost_business_object"],
                                                                                each["plant_code"]))
            if each.get("cost_business_object1", "") != "":
                # 成本事项1检查
                if dict_cost_business_object_data.get(each["cost_business_object1"] + each["plant_code"]) is None:
                    error_list.append(
                        "行标识{}成本事项2{}在工厂{}对应的公司代码不存在".format(each["line_id"],
                                                                                 each["cost_business_object1"],
                                                                                 each["plant_code"]))
            if each.get("profit_center", "") != "":
                # 利润中心检查
                if dict_profit_center_data.get(each["profit_center"] + each["plant_code"]) is None:
                    error_list.append(
                        "行标识{}利润中心{}在工厂{}对应的公司代码不存在".format(each["line_id"], each["profit_center"],
                                                                                each["plant_code"]))
            if each.get("equipment_code", "") != "":
                # 设备ID检查
                if dict_equipment_code_data.get(each["equipment_code"]) is None:
                    error_list.append("行标识{}设备ID{}不存在".format(each["line_id"], each["equipment_code"]))

            # 交易货币
            if each.get("transaction_currency", "") == "":
                if dict_po_header.get(each.get('rel_po_sn')):
                    each["transaction_currency"] = dict_po_header[each.get('rel_po_sn')][0]['currency_code']

            # 前序物料凭证检查
            if each.get('pre_document_no', ''):
                key = each['pre_document_no'] + each.get('pre_document_year', '') + str(
                    each.get('pre_document_item', 0))
                if dict_pre_md.get(key):
                    if each.get('transaction_qty', 0) > dict_pre_md[key][0]['transaction_qty']:
                        error_list.append(
                            "行标识{}交易数量不能大于前序物料凭证{}年度{}的数量{}".format(each["line_id"],
                                                                                          each["pre_document_no"],
                                                                                          each["pre_document_year"],
                                                                                          dict_pre_md[key][0][
                                                                                              'transaction_qty']))
                else:
                    error_list.append(
                        "行标识{}前序物料凭证{}年度{}不存在或已冲销".format(each["line_id"], each["pre_document_no"],
                                                                            each["pre_document_year"]))

    md_header = initialization("t_md_header", db)
    md_item = []
    md_price = []

    # 生成凭证数据
    if not error_list:
        # 单据种类
        md_header["document_category"] = "MDOC"
        # 物料凭证
        md_header["mat_doc_sn"] = ""
        # 年度
        md_header["year"] = head["posting_date"][:4]
        # 过账代码
        md_header["post_code"] = head["post_code"]
        # 凭证日期
        md_header["document_date"] = head["document_date"]
        # 过账日期
        md_header["posting_date"] = head["posting_date"]

        # 汇总唯一号
        md_header["summary_unique_number"] = head.get("summary_unique_number", "")
        # 备注信息1
        md_header["remarks_1"] = head.get("remarks_1", "")
        # 备注信息2
        md_header["remarks_2"] = head.get("remarks_2", "")
        # 供应商交货单
        md_header["vendor_dn"] = head.get("vendor_dn", "")
        # 预留字段
        md_header["reserved1"] = head.get("reserved1", "")
        md_header["reserved2"] = head.get("reserved2", "")
        md_header["reserved3"] = head.get("reserved3", "")
        md_header["reserved4"] = head.get("reserved4", "")
        md_header["reserved5"] = head.get("reserved5", "")
        md_header["reserved6"] = head.get("reserved6", "")
        md_header["reserved7"] = head.get("reserved7", "")
        md_header["reserved8"] = head.get("reserved8", "")
        md_header["reserved9"] = head.get("reserved9", "")
        md_header["reserved10"] = head.get("reserved10", "")
        # 物料凭证类型
        md_header["material_document_type"] = ""

        # 交易汇率 公司代码 信息
        md_header["company_code"], md_header["exchange_rate"] = get_company_info(item[0]["plant_code"],
                                                                                 item[0]["transaction_currency"],
                                                                                 dict_company)

        if head.get('exchange_rate', 0) != 0:
            md_header["exchange_rate"] = head['exchange_rate']

        md_header["create_id"] = user_id
        md_header["update_id"] = user_id

        md_header["ztype"] = head.get('ztype', '')

        if md_header["exchange_rate"] == 0:
            error_list.append("未获取到汇率")

        line_tmp = initialization("t_md_item", db)
        price_tmp = initialization("t_md_price_details", db)

        item_no = 0
        # 行项目设置
        for each in item:
            line = line_tmp.copy()
            price = price_tmp.copy()

            item_no += 1
            # 物料凭证
            line["mat_doc_sn"] = md_header["mat_doc_sn"]
            # 年度
            line["year"] = md_header["year"]
            # 物料凭证信息行号
            line["mat_doc_items"] = item_no
            # 物料凭证行唯一标识
            line["line_id"] = each["line_id"]
            # 凭证行参考唯一标识
            line["parent_id"] = each.get("parent_id", 0)
            # 参考凭证行
            line["ref_item_serial_no"] = 0
            # 自动创建标识
            line["auto_mark"] = 0
            # 移动类型
            line["movement_type"] = each["movement_type"]
            # 物料凭证类型 借贷标识  收发标识  科目修改 业务单据种类
            line, material_document_type, prod_order_mark, wbs_elements_mark, cost_business_object_mark, asset_code1_mark = get_movement_attribute(
                line, line["movement_type"], dict_movement_type)
            if md_header["material_document_type"] == "":
                md_header["material_document_type"] = material_document_type
            if line["debit_credit_mark"] == "":
                error_list.append(
                    "行标识{}未能根据移动类型{}取到借贷标识".format(each["line_id"], each["movement_type"]))
            if line["receipt_consume_mark"] == "":
                error_list.append(
                    "行标识{}未能根据移动类型{}取到收发标识".format(each["line_id"], each["movement_type"]))
            if prod_order_mark == 1:
                if each.get("prodosn", "") == "":
                    error_list.append("行标识{}生产订单必填".format(each["line_id"]))
            if wbs_elements_mark == 1:
                if each.get("wbs_elements", "") == "":
                    error_list.append("行标识{}WBS必填".format(each["line_id"]))
            if cost_business_object_mark == 1:
                if each.get("cost_center", "") == "" and each.get("cost_business_object", "") == "" and each.get(
                        "cost_business_object1", "") == "":
                    error_list.append("行标识{}成本中心/成本事项/成本事项1必填一个".format(each["line_id"]))
            if asset_code1_mark == 1:
                if each.get("asset_code1", "") == "":
                    error_list.append("行标识{}资产卡片必填".format(each["line_id"]))
            # 特殊库存状态1
            line["special_inventory_status1"] = each.get("special_inventory_status1", "")
            # 特殊库存状态2
            line["special_inventory_status2"] = each.get("special_inventory_status2", "")
            # 库存状态
            line["inventory_status"] = get_inventory_status(each["movement_type"], each.get("inventory_status", ""),
                                                            dict_movement_type)
            # 事件类型 物料成本特殊评估标识
            line["transaction_type_code"], line["mat_special_val_mark"] = get_transaction_type_code(
                each["movement_type"], each["plant_code"], each["mat_code"], each.get("rel_po_sn", ""),
                each.get("rel_po_items", 0),
                line["special_inventory_status1"], line["special_inventory_status2"], dict_relation, dict_po_item,
                dict_mat_code)
            if line["transaction_type_code"] == "":
                error_list.append("行标识{}未能根据移动类型{}和采购订单{}信息取到事件类型".format(each["line_id"],
                                                                                                  each["movement_type"],
                                                                                                  each.get("rel_po_sn",
                                                                                                           "")))
            # 工厂代码
            line["plant_code"] = each["plant_code"]
            # 公司代码
            line["company_code"] = md_header["company_code"]
            # 结算公司代码
            line["settle_company_code"] = get_settle_company_code(each["plant_code"], dict_company)
            # 物料编码
            line["mat_code"] = each.get("mat_code", "")
            # 库存地点
            if line["mat_code"] == "" or line["special_inventory_status1"] == "V":
                line["stor_loc_code"] = ""
            else:
                line["stor_loc_code"] = each.get("stor_loc_code", "")
            # 批次号
            line["batch_sn"] = each.get("batch_sn", "")
            # 交易数量
            line["transaction_qty"] = each["transaction_qty"]
            # 交易单位
            line["transaction_uom"] = each["transaction_uom"]
            # 带借贷标识的交易数量
            if line["debit_credit_mark"] == "Cr":
                line["transaction_qty_dc_mark"] = line["transaction_qty"] * -1
            else:
                line["transaction_qty_dc_mark"] = line["transaction_qty"]

            # 基本单位/成本单位/价格控制/评估类/物料组
            line = get_material_uom(line["mat_code"], line["plant_code"], dict_mat_code, line)

            # # 平行数量
            # line["parallel_qty"] = each["parallel_qty"]
            # 平行单位
            line["parallel_uom"] = each.get("parallel_uom", "")

            # 计算基本数量和成本数量
            line = get_other_qty_by_unit(each, line, head['post_code'],
                                         dict_movement_type[each['movement_type']][0]['allow_zero_base_qty'],
                                         dict_movement_type[each['movement_type']][0]['allow_zero_parallel_qty'],
                                         dict_mat_uom_convert)

            if dict_movement_type[each['movement_type']][0]['allow_zero_base_qty'] == 0:
                if line["basic_qty"] <= 0:
                    error_list.append("行标识{}基本数量不能为0".format(each["line_id"]))

            if dict_movement_type[each['movement_type']][0]['allow_zero_parallel_qty'] == 0:
                if line["parallel_qty"] <= 0 and line["parallel_uom"]:
                    error_list.append("行标识{}平行数量不能为0".format(each["line_id"]))

            # 带借贷标识的基本数量
            if line["debit_credit_mark"] == "Cr":
                line["basic_qty_dc_mark"] = line["basic_qty"] * -1
            else:
                line["basic_qty_dc_mark"] = line["basic_qty"]

            # 带借贷标识的成本数量
            if line["debit_credit_mark"] == "Cr":
                line["cost_qty_dc_mark"] = line["cost_qty"] * -1
            else:
                line["cost_qty_dc_mark"] = line["cost_qty"]

            # 带借贷标识的平行数量
            if line["debit_credit_mark"] == "Cr":
                line["parallel_qty_dc_mark"] = line["parallel_qty"] * -1
            else:
                line["parallel_qty_dc_mark"] = line["parallel_qty"]
            # 定价单位 定价单位数量 交易金额 交易货币 采购订单供应商
            line = get_po_qty_amount_info(line, each.get("rel_po_sn", ""), each.get("rel_po_items", 0), dict_po_header,
                                          dict_po_item)
            # 消耗记账 对象标识 价值更新 数量更新
            line = get_movement_label(line, each.get("rel_po_sn", ""), each.get("rel_po_items", 0), dict_movement_type,
                                      dict_mat_code,
                                      dict_po_item, dict_movement_label1, dict_movement_label2, dict_movement_label3)
            if line["consumption_posting_label"] == "":
                error_list.append("行标识{}消耗记账标识不能为空".format(each["line_id"]))
            if line["item_indicator"] == "":
                error_list.append("行标识{}对象标识不能为空".format(each["line_id"]))
            if line["value_update"] == "":
                error_list.append("行标识{}价值更新不能为空".format(each["line_id"]))
            # 关联采购订单
            line["rel_po_sn"] = each.get("rel_po_sn", "")
            # 关联采购订单行
            line["rel_po_items"] = each.get("rel_po_items", 0)
            # 关联采购订单行项目序号
            line["rel_po_component_number"] = each.get("rel_po_component_number", 0)
            # 关联采购订单行序号
            line["rel_po_comp_batch_num"] = each.get("rel_po_comp_batch_num", 0)
            # 关联生产订单组件序号
            line["prodo_component_number"] = each.get("prodo_component_number", '')
            # 生产订单
            line["prodosn"] = each.get("prodosn", "")
            # 关联交货单
            line["rel_dn_sn"] = each.get("rel_dn_sn", "")
            # 关联交货单行号
            line["rel_dn_item"] = each.get("rel_dn_item", 0)
            # 拣配单号
            line["picking_document"] = each.get("picking_document", "")
            # 批次行号
            line["batch_item"] = each.get("batch_item", 0)
            # 关联预留单
            line["ro_sn"] = each.get("ro_sn", "")
            # 关联预留单行
            line["ro_items"] = each.get("ro_items", 0)
            # 关联销售订单
            line["rel_so_sn"] = each.get("rel_so_sn", "")
            # 关联销售订单行项目
            line["rel_so_items"] = each.get("rel_so_items", 0)
            # 关联单据种类 关联单据号 关联行号 原始单据类型 原始单据号 原始单据行号
            line = get_associated_order(md_header, line)
            # 客户编码
            line["customer_code"] = each.get("customer_code", "")
            # 销售订单
            line["so_sn"] = each.get("so_sn", "")
            # 销售订单行项目
            line["so_items"] = each.get("so_items", 0)
            # 库存调拨单
            line['inv_transfer_order_no'] = each.get("inv_transfer_order_no", '')
            # 库存调拨单行
            line['inv_transfer_order_items'] = each.get("inv_transfer_order_items", 0)
            # 项目编号
            line["project_sn"] = each.get("project_sn", "")
            # 供应商编码
            line["vendor_code"] = each.get("vendor_code", "")
            # 采购订单
            line["po_sn"] = each.get("po_sn", "")
            # 采购订单行项目
            line["po_items"] = each.get("po_items", 0)
            # WBS元素
            line["wbs_elements"] = each.get("wbs_elements", "")
            # 成本中心
            line["cost_center"] = each.get("cost_center", "")
            # 成本事项
            line["cost_business_object"] = each.get("cost_business_object", "")
            # 成本事项1
            line["cost_business_object1"] = each.get("cost_business_object1", "")
            # 利润中心
            line["profit_center"] = each.get("profit_center", "")
            # 会计科目
            line["accounting_subjects"] = each.get("accounting_subjects", "")
            # 资产卡片
            line["asset_code1"] = each.get("asset_code1", "")
            # 子资产
            line["asset_code2"] = each.get("asset_code2", "")
            # 设备ID
            line["equipment_code"] = each.get("equipment_code", "")
            # 快递单号
            line["express_delivery"] = each.get("express_delivery", "")
            # 行参考信息1
            line["reference1_item"] = each.get("reference1_item", "")
            # 行参考信息2
            line["reference2_item"] = each.get("reference2_item", "")
            # 行参考信息3
            line["reference3_item"] = each.get("reference3_item", "")
            # 汇总行
            line["summary_line"] = each.get("summary_line", 0)
            # 批次编码校验
            if each.get("mat_code", "") != "":
                line["batch_sn"], each['batch_number'], msg = check_batch_required(line["mat_code"], line["plant_code"],
                                                                                   line["batch_sn"],
                                                                                   line["debit_credit_mark"],
                                                                                   dict_mat_code, dict_mat_batch,
                                                                                   each.get('batch_number', {}),
                                                                                   dict_movement_type[
                                                                                       line['movement_type']][0],
                                                                                       user_id=user_id
                                                                                       )
                if msg != "":
                    error_list.append("行标识{}{}".format(each["line_id"], msg))

            # 交易前移动平均价（成本货币）/ 交易前移动平均价（本位币）
            # ---待补充
            # 采购项目类别 / 科目分配类别 / 采购订单数量 / 采购订单单位 / 免费标记 / 返工标记 / 返工类型 / 加工工序
            line = get_po_item_other_info(line, line["rel_po_sn"], line["rel_po_items"], dict_po_item)

            # 质检过账标识 / 质量检验单标识
            line["quality_insp_post_mark"] = each.get("quality_insp_post_mark", 0)
            line["quality_insp_order_mark"], msg = get_quality_inspection_mark(line["mat_code"], line["plant_code"],
                                                                               line["inventory_status"],
                                                                               line["movement_type"],
                                                                               line["debit_credit_mark"],
                                                                               line["quality_insp_post_mark"],
                                                                               dict_mat_code,
                                                                               dict_movement_type,
                                                                               dict_mat_insp)
            if msg != "":
                error_list.append("行标识{}{}".format(each["line_id"], msg))

            # 结批标识
            line["batch_closure_flag"] = each.get("batch_closure_flag", 0)
            # 结批日期
            line["batch_closure_date"] = each.get("batch_closure_date", "")
            # 收货完成标记
            line["receipt_completed_flag"] = each.get("receipt_completed_flag", 0)

            # 移动原因
            line["movement_reason"] = each.get("movement_reason", "")

            # 参考凭证年度
            line["rel_document_year"] = each.get("rel_document_year", "")
            # 参考凭证号
            line["rel_document_no"] = each.get("rel_document_no", "")
            # 参考凭证行号
            line["ref_document_mat"] = each.get("ref_document_mat", 0)
            # 前序物料凭证年度
            line["pre_document_year"] = each.get("pre_document_year", "")
            # 前序物料凭证
            line["pre_document_no"] = each.get("pre_document_no", "")
            # 前序物料凭证行号
            line["pre_document_item"] = each.get("pre_document_item", 0)

            # 交易数量检查
            msg = check_if_overcharge(line["rel_po_sn"], line["rel_po_items"], line, item, dict_md_info1, dict_md_info2,
                                      dict_pi_invoice_info, dict_po_item)
            if msg:
                error_list.append(msg)
            # 预留字段
            line["reserved1"] = each.get("reserved1", "")
            line["reserved2"] = each.get("reserved2", "")
            line["reserved3"] = each.get("reserved3", "")
            line["reserved4"] = each.get("reserved4", "")
            line["reserved5"] = each.get("reserved5", "")
            line["reserved6"] = each.get("reserved6", "")
            line["reserved7"] = each.get("reserved7", "")
            line["reserved8"] = each.get("reserved8", "")
            line["reserved9"] = each.get("reserved9", "")
            line["reserved10"] = each.get("reserved10", "")

            # 批次属性
            # batch_number = {}
            # line["batch_number"] = {}
            #
            # batch_number["production_date"] = each["batch_number"].get("production_date", "")
            # batch_number["maturity_date"] = each["batch_number"].get("maturity_date", "")
            # batch_number["vendor_code"] = each["batch_number"].get("vendor_code", "")
            # batch_number["vendor_batch"] = each["batch_number"].get("vendor_batch", "")
            # batch_number["receive_date"] = each["batch_number"].get("receive_date", "")
            # batch_number["lot_no"] = each["batch_number"].get("lot_no", "")
            # batch_number["wafer_id"] = each["batch_number"].get("wafer_id", "")
            # batch_number["mfg_date_wafer"] = each["batch_number"].get("mfg_date_wafer", "")
            # batch_number["vendor_lot_no"] = each["batch_number"].get("vendor_lot_no", "")
            # batch_number["mfg_date_assy"] = each["batch_number"].get("mfg_date_assy", "")
            # batch_number["packing_seal_date"] = each["batch_number"].get("packing_seal_date", "")
            # batch_number["date_code"] = each["batch_number"].get("date_code", "")
            # batch_number["packing_id"] = each["batch_number"].get("packing_id", "")
            # batch_number["bin_grade"] = each["batch_number"].get("bin_grade", "")
            # batch_number["grade"] = each["batch_number"].get("grade", "")
            # batch_number["batch_type"] = each["batch_number"].get("batch_type", "")
            # batch_number["receive_data"] = each["batch_number"].get("receive_data", "")
            # batch_number["cp_vendor"] = each["batch_number"].get("cp_vendor", "")
            # batch_number["bin"] = each["batch_number"].get("bin", "")
            # batch_number["grade1"] = each["batch_number"].get("grade1", "")
            # batch_number["grade2"] = each["batch_number"].get("grade2", "")
            # batch_number["grade3"] = each["batch_number"].get("grade3", "")
            # batch_number["extended_batch_date1"] = each["batch_number"].get("extended_batch_date1", "")
            # batch_number["extended_batch_date2"] = each["batch_number"].get("extended_batch_date2", "")
            # batch_number["extended_batch_date3"] = each["batch_number"].get("extended_batch_date3", "")
            # batch_number["extended_batch_attributes1"] = each["batch_number"].get("extended_batch_attributes1", "")
            # batch_number["extended_batch_attributes2"] = each["batch_number"].get("extended_batch_attributes2", "")
            # batch_number["extended_batch_attributes3"] = each["batch_number"].get("extended_batch_attributes3", "")
            # batch_number["item"] = edit_batch_attribute(each["batch_number"].get("item", []))
            # batch_number["create_id"] = user_id
            # batch_number["update_id"] = user_id
            # line["batch_number"] = batch_number

            line["batch_number"] = each.get('batch_number', {})
            line["batch_number"]["create_id"] = user_id
            line["batch_number"]["update_id"] = user_id

            line["create_id"] = user_id
            line["update_id"] = user_id

            md_item.append(line.copy())

            # 价格明细表
            # 物料凭证
            price["mat_doc_sn"] = md_header["mat_doc_sn"]
            # 年度
            price["year"] = md_header["year"]
            # 物料凭证信息行号
            price["mat_doc_items"] = item_no
            md_price = get_po_price(md_price, line, price, user_id, dict_price_data)

    if not error_list:
        # 库存校验
        msg_list = get_inventory_qty(md_item, md_header["posting_date"], dict_plant_storage, db)
        if msg_list:
            error_list.extend(msg_list)

    if error_list:
        code = 500
        msg = "存在错误,请检查"
    else:
        code = 200
        msg = "检查无误"

    return code, msg, error_list, md_header, md_item, md_price


def edit_batch_attribute(item):
    data = []
    # field_code,
    # field_name,
    # field_type,
    # field_mark,
    # field_value,
    # field_value_from,
    # field_value_to,
    # field_format,
    # required,
    # field_length,
    # decimal_length

    # 按照数据类型进行拆分字段
    for each in item:
        if each["field_mark"] == "1":
            if each["field_type"] == "varchar":
                each["field_value"] = each["field_value"]
            elif each["field_type"] == "int":
                each["field_value_int"] = each["field_value"]
            elif each["field_type"] == "date":
                each["field_value_date"] = each["field_value"]
            elif each["field_type"] == "time":
                each["field_value_time"] = each["field_value"]
            elif each["field_type"] == "decimal":
                each["field_value_decimal"] = each["field_value"]
            else:
                each["field_value"] = each["field_value"]
        else:
            if each["field_type"] == "varchar":
                each["field_value_from"] = each["field_value_from"]
                each["field_value_to"] = each["field_value_to"]
            elif each["field_type"] == "int":
                each["field_value_int_from"] = each["field_value_from"]
                each["field_value_int_to"] = each["field_value_to"]
            elif each["field_type"] == "date":
                each["field_value_date_from"] = each["field_value_from"]
                each["field_value_date_to"] = each["field_value_to"]
            elif each["field_type"] == "time":
                each["field_value_time_from"] = each["field_value_from"]
                each["field_value_time_to"] = each["field_value_to"]
            elif each["field_type"] == "decimal":
                each["field_value_decimal_from"] = each["field_value_from"]
                each["field_value_decimal_to"] = each["field_value_to"]
            else:
                each["field_value_from"] = each["field_value_from"]
                each["field_value_to"] = each["field_value_to"]
        data.append(each)

    return data


def get_quality_inspection_mark(mat_code, plant_code, inventory_status, movement_type, debit_credit_mark,
                                quality_insp_post_mark, dict_mat_code, dict_movement_type, dict_mat_insp):
    msg = ""

    quality_inspection_mark = 0
    quality_insp_order_mark = 0

    inspection_type = ''

    # # 获取物料主数据质检库存标记
    # query_sql = """
    #     SELECT
    #         quality_inspection_mark
    #     FROM
    #         t_mmd_material_plant_data
    #     WHERE
    #         mat_code = '{}'
    #     AND plant_code = '{}'
    #     LIMIT 1
    # """.format(mat_code, plant_code)
    # data = []
    # data = db.query_sql(query_sql)
    # if dict_mat_code.get(mat_code + plant_code):
    #     quality_inspection_mark = dict_mat_code[mat_code + plant_code][0]["quality_inspection_mark"]

    # if quality_inspection_mark == 1 and debit_credit_mark == "Cr" and inventory_status == "1":
    if debit_credit_mark == "Cr" and inventory_status == "1":
        if dict_movement_type.get(movement_type):
            # quality_insp_order_mark = data[0]["quality_insp_order_mark"]
            # if dict_movement_type[movement_type][0]['activation_flag'] == 1:
            if dict_movement_type[movement_type][0]['quality_insp_order_mark'] == 1:
                inspection_type = dict_movement_type[movement_type][0]["inspection_type"]

        key = mat_code + plant_code + inspection_type

        if dict_mat_insp.get(key):
            if quality_insp_post_mark != 1:
                msg = "该物料激活质量检验，请使用质检决策过账"

    # if quality_inspection_mark == 1 and debit_credit_mark == "Dr" and inventory_status == "1":
    if debit_credit_mark == "Dr" and inventory_status == "1":
        # # 获取移动类型质检过账标识
        # query_sql = """
        #     SELECT
        #         quality_insp_order_mark,
        #         inspection_type
        #     FROM
        #         t_movement_type
        #     WHERE
        #         movement_type = '{}'
        #     AND activation_flag = 1
        #     LIMIT 1
        # """.format(movement_type)
        # data = []
        # data = db.query_sql(query_sql)
        if dict_movement_type.get(movement_type):
            # quality_insp_order_mark = data[0]["quality_insp_order_mark"]
            # if dict_movement_type[movement_type][0]['activation_flag'] == 1:
            if dict_movement_type[movement_type][0]['quality_insp_order_mark'] == 1:
                inspection_type = dict_movement_type[movement_type][0]["inspection_type"]

        # # 物料主数据检验类型（激活）=移动类型检验类型
        # query_sql = """
        #     SELECT
        #         id
        #     FROM
        #         t_mmd_material_quality_Inspection_data
        #     WHERE
        #         mat_code = '{}'
        #     AND plant_code = '{}'
        #     AND inspection_type = '{}'
        #     AND activation_flag = 1
        #     LIMIT 1
        # """.format(mat_code, plant_code, inspection_type)
        # data = []
        # data = db.query_sql(query_sql)

        key = mat_code + plant_code + inspection_type

        if dict_mat_insp.get(key):
            quality_insp_order_mark = 1
        else:
            # msg = "该物料激活质量检验，请维护物料主数据的检验类型，检查移动类型质检配置"
            quality_insp_order_mark = 0

    return quality_insp_order_mark, msg


def get_inventory_status(movement_type, inventory_status, dict_movement_type):
    # query_sql = """
    #     select inventory_status
    #     from t_movement_type
    #     where movement_type = '{}'
    #     limit 1
    # """.format(movement_type)
    # data = []
    # data = db.query_sql(query_sql)

    if dict_movement_type.get(movement_type):
        if dict_movement_type[movement_type][0]["inventory_status"] != "":
            inventory_status = dict_movement_type[movement_type][0]["inventory_status"]

    return inventory_status


def check_po_and_movement(line, dict_movement_type, dict_po_item, dict_md_info):
    msg = ""
    # query_sql = """
    #     SELECT
    #         po_sn,
    #         po_items,
    #         return_flag
    #     FROM
    #         t_po_item
    #     WHERE
    #         po_sn = '{}'
    #     AND po_items = {}
    #     LIMIT 1
    # """.format(line["rel_po_sn"], line["rel_po_items"])
    # po = []
    # po = db.query_sql(query_sql)
    #
    # query_sql = """
    #     SELECT
    #         movement_type,
    #         purchase_return_mark,
    #         debit_credit_mark
    #     FROM
    #         t_movement_type
    #     WHERE
    #         movement_type = '{}'
    #     LIMIT 1
    # """.format(line["movement_type"])
    # move = []
    # move = db.query_sql(query_sql)

    if dict_po_item.get(line["rel_po_sn"] + str(line["rel_po_items"])) and dict_movement_type.get(
            line["movement_type"]):
        if ((dict_po_item[line["rel_po_sn"] + str(line["rel_po_items"])][0]["return_flag"] == 1 and
             dict_movement_type[line["movement_type"]][0]["purchase_return_mark"] == 1)
                or (dict_po_item[line["rel_po_sn"] + str(line["rel_po_items"])][0]["return_flag"] == 0 and
                    dict_movement_type[line["movement_type"]][0]["purchase_return_mark"] == 0)):
            pass
        else:
            msg = "移动类型与采购订单类型不匹配"

        if dict_po_item[line["rel_po_sn"] + str(line["rel_po_items"])][0]["return_flag"] == 0 and \
                dict_movement_type[line["movement_type"]][0]["debit_credit_mark"] == "Cr" and \
                dict_movement_type[line["movement_type"]][0]["purchase_return_mark"] == 0:
            if line["rel_document_no"] != "":
                # query_sql = """
                #     SELECT
                #         year,
                #         mat_doc_sn,
                #         posting_date,
                #         company_code
                #     FROM
                #         t_md_header
                #     WHERE
                #         year = '{}'
                #     AND
                #         mat_doc_sn = '{}'
                #     LIMIT 1
                # """.format(line["rel_document_year"], line["rel_document_no"])
                # data = []
                # data = db.query_sql(query_sql)
                # if data:
                #     table = 't_md_item_' + str(data[0]['company_code']) + '_' + str(
                #         data[0]['posting_date'][:4]) + '_' + str(data[0]['posting_date'][5:7])
                #     query_sql = """
                #         SELECT
                #             i.id
                #         FROM
                #             {} AS i
                #             JOIN t_md_header AS h ON i.mat_doc_sn = h.mat_doc_sn
                #             AND i.year = h.year
                #         WHERE
                #             h.post_code = '1'
                #             AND i.debit_credit_mark = 'Dr'
                #             AND i.year = '{}'
                #             AND i.mat_doc_sn = '{}'
                #             AND i.mat_doc_items = {}
                #         LIMIT 1
                #     """.format(table, line.get("rel_document_year", ""), line.get("rel_document_no", ""),
                #                line.get("ref_document_mat", 0))
                #     data = db.query_sql(query_sql)
                key = str(line.get("rel_document_year", "")) + line["rel_document_no"] + str(
                    line.get("ref_document_mat", 0))
                if dict_md_info.get(key) is None:
                    msg = "参考凭证号不存在"
            else:
                msg = "参考凭证号必输"
    return msg


# 获取采购订单行信息
def get_po_item_other_info(line, po_sn, po_items, dict_po_item):
    # 采购项目类别
    line["pur_item_cat"] = ""
    # 科目分配类别
    line["account_allocation_category"] = ""
    # 采购订单数量
    line["po_qty"] = 0
    # 采购订单单位
    line["pur_uom"] = ""
    # 免费标记
    line["free_mark"] = 0
    # 返工标记
    line["rework_mark"] = 0
    # 返工类型
    line["rework_type"] = ""
    # 加工工序
    line["sequence_number"] = 0

    # query_sql = """
    #     SELECT
    #         po_sn,
    #         po_items,
    #         pur_item_cat,
    #         account_allocation_category,
    #         order_qty,
    #         pur_uom,
    #         free_mark,
    #         rework_mark,
    #         rework_type,
    #         sequence_number
    #     FROM
    #         t_po_item
    #     WHERE
    #         po_sn = '{}'
    #     AND po_items = '{}'
    #     LIMIT 1
    # """.format(po_sn, po_items)
    # data = db.query_sql(query_sql)

    if dict_po_item.get(po_sn + str(po_items)):
        # 采购项目类别
        line["pur_item_cat"] = dict_po_item[po_sn + str(po_items)][0]["pur_item_cat"]
        # 科目分配类别
        line["account_allocation_category"] = dict_po_item[po_sn + str(po_items)][0]["account_allocation_category"]
        # 采购订单数量
        line["po_qty"] = dict_po_item[po_sn + str(po_items)][0]["order_qty"]
        # 采购订单单位
        line["pur_uom"] = dict_po_item[po_sn + str(po_items)][0]["pur_uom"]
        # 免费标记
        line["free_mark"] = dict_po_item[po_sn + str(po_items)][0]["free_mark"]
        # 返工标记
        line["rework_mark"] = dict_po_item[po_sn + str(po_items)][0]["rework_mark"]
        # 返工类型
        line["rework_type"] = dict_po_item[po_sn + str(po_items)][0]["rework_type"]
        # 加工工序
        line["sequence_number"] = dict_po_item[po_sn + str(po_items)][0]["sequence_number"]

    return line


# 库存校验
def get_inventory_qty(md_item, posting_date, dict_plant_storage, db):
    dict_data = {}

    mat_code = []
    plant_code = []

    for each in md_item:
        # 数量更新为0的 不参与校验
        if each['qty_update_flag'] == 0:
            continue
        # 负库存不参与校验
        key = each["plant_code"] + each["stor_loc_code"]
        if dict_plant_storage.get(key):
            if dict_plant_storage[key][0]['negative_inventory_allow'] == 1 and each['price_control'] != 'V':
                continue

        if each["debit_credit_mark"] != "Cr":
            continue

        key = (each["mat_code"] + each["plant_code"] + each["stor_loc_code"] + each["batch_sn"] + each[
            "inventory_status"] +
               each["special_inventory_status1"] + each["special_inventory_status2"] + each["so_sn"] + str(
                    each["so_items"]) +
               each["vendor_code"] + each["customer_code"] + each["project_sn"] + each["po_sn"] + str(each["po_items"]))

        if key not in dict_data:
            dict_data[key] = []
            dict_data[key].append(each)
        else:
            dict_data[key].append(each)

        # 工厂
        if each.get("plant_code", "") != "":
            plant_code.append(each['plant_code'])

        # 物料编码
        if each.get("mat_code", "") != "":
            mat_code.append(each['mat_code'])

    # # 交易前库存数量-基本单位
    # line["inv_qty_before_post"] = 0
    # # 交易前库存数量-成本单位
    # line["inv_co_qty_before_post"] = 0
    # # 交易前库存数量-平行单位
    # line["inv_parallel_qty_before_post"] = 0

    year = posting_date[:4]
    period = posting_date[5:7]

    msg_list = []

    mat_code = list(set(mat_code))
    plant_code = list(set(plant_code))

    query_sql = """
        SELECT `year`,
            `period`,
            `mat_code`,
            `plant_code`,
            `stor_loc_code`,
            `batch_sn`,
            `inventory_status`,
            `special_inventory_status1`,
            `special_inventory_status2`,
            `so_sn`,
            `so_items`,
            `vendor_code`,
            `customer_code`,
            `wbs_elements`,
            `po_sn`,
            `po_items`,
            `basic_qty`
        FROM
            `t_inventory_batch_data` 
        WHERE
            `mat_code` in ('{}')
        AND `plant_code` in ('{}')
        and `year` = '{}'
        and `period` = '{}'
    """.format("','".join(mat_code), "','".join(plant_code), year, period)

    data = db.query_sql(query_sql)

    dict_inventory = {}
    for each in data:
        key = (each["mat_code"] + each["plant_code"] + each["stor_loc_code"] + each["batch_sn"] + each[
            "inventory_status"] +
               each["special_inventory_status1"] + each["special_inventory_status2"] + each["so_sn"] + str(
                    each["so_items"]) +
               each["vendor_code"] + each["customer_code"] + each["wbs_elements"] + each["po_sn"] + str(
                    each["po_items"]))

        if key not in dict_inventory:
            dict_inventory[key] = []
            dict_inventory[key].append(each)
        else:
            dict_inventory[key].append(each)
    # print(f'dict_inventory---------{dict_inventory}')
    # print(f'dict_data---------{dict_data}')
    for key in dict_data:
        msg = ''
        if dict_inventory.get(key):
            # 库存数量
            inventory_qty = dict_inventory[key][0]['basic_qty']
            for each in dict_data[key]:
                inventory_qty += each['basic_qty_dc_mark']
                inventory_qty = round(inventory_qty, 3)
                if inventory_qty < 0:
                    msg = "当前物料{}工厂{}库存地点{}批次{}短缺{}".format(each["mat_code"], each["plant_code"],
                                                                          each["stor_loc_code"], each["batch_sn"],
                                                                          inventory_qty)
        else:
            print(f'执行这---------')
            msg = "当前物料{}工厂{}库存地点{}批次{}短缺{}".format(dict_data[key][0]["mat_code"],
                                                                  dict_data[key][0]["plant_code"],
                                                                  dict_data[key][0]["stor_loc_code"],
                                                                  dict_data[key][0]["batch_sn"],
                                                                  dict_data[key][0]["basic_qty"])
        if msg:
            msg_list.append(msg)

    return msg_list


# 获取采购订单价格明细信息
def get_po_price(md_price, line, price, user_id, dict_price_data):
    # query_sql = """
    #     SELECT
    #         p.*,
    #         i.first_storage_completely_valued
    #     FROM
    #         t_po_price_data AS p
    #     JOIN t_po_item AS i
    #     ON p.po_sn = i.po_sn
    #     AND p.po_items = i.po_items
    #     WHERE
    #         p.po_sn = '{}'
    #     AND p.po_items = '{}'
    # """.format(line["rel_po_sn"], line["rel_po_items"])
    # data = db.query_sql(query_sql)

    if dict_price_data.get(line["rel_po_sn"] + str(line["rel_po_items"])):
        price_id = 0
        for each in dict_price_data[line["rel_po_sn"] + str(line["rel_po_items"])]:
            price_id += 1

            # 价格明细行
            price["price_id"] = price_id
            # 采购订单号
            price["po_sn"] = each["po_sn"]
            # 采购订单行号
            price["po_items"] = each["po_items"]
            # 价格条件分类
            price["price_condition_category"] = each["price_condition_category"]
            # 价格条件
            price["price_condition"] = each["price_condition"]
            # 价格计算类型
            price["price_calculation_type"] = each["price_calculation_type"]
            # 税码
            price["tax_code"] = each["tax_code"]
            # 税率
            price["tax_rate"] = each["tax_rate"]
            # 不含税单价
            price["unit_price_excluding_tax"] = each["unit_price_excluding_tax"]
            # 含税单价
            price["unit_price_including_tax"] = each["unit_price_including_tax"]
            # 不含税总价/净价
            #  line["pricing_unit_quantity"] 取出的值有的是int类型，有的是str类型，都强转成float类型
            price["total_price_excluding_tax"] = round(
                each["unit_price_excluding_tax"] * float(line["pricing_unit_quantity"]) / each[
                    "price_unit"], 2)
            # 单位税额
            # price["tax_amount"] = each["tax_amount"]
            price["tax_amount"] = round(price["total_price_excluding_tax"] * price["tax_rate"] / 100, 2)
            # 含税总价
            price["total_price_including_tax"] = round(price["total_price_excluding_tax"] + price["tax_amount"], 2)
            # 首批入库完全计价
            price["first_storage_completely_valued"] = each["first_storage_completely_valued"]
            # 交易货币
            price["transaction_currency"] = each["currency_code"]
            # 供应商
            if each["vendor_code"] != "":
                price["vendor_code"] = each["vendor_code"]
            else:
                price["vendor_code"] = each["vendor_code2"]
            # 价格单位
            price["price_unit"] = each["price_unit"]
            # 定价单位
            price["pricing_unit_of_measure"] = each["pricing_unit_of_measure"]
            # 定价单位数量
            price["pricing_unit_quantity"] = line["pricing_unit_quantity"]
            price["create_id"] = user_id
            price["update_id"] = user_id
            md_price.append(price.copy())

    return md_price


# 检查采购订单
def check_if_po_header_exists(po_sn, db):
    query_sql = """
        SELECT
            `id` 
        FROM
            `t_po_header`
        WHERE
            `po_sn` = '{}'
        LIMIT 1
    """.format(po_sn)
    data = db.query_sql(query_sql)

    if data:
        return False

    return True


# 关联单据种类/关联单据号/关联行号/原始单据类型/原始单据号/原始单据行号
def get_associated_order(md_header, line):
    # 关联单据种类
    line["associated_document_type"] = ""
    # 关联单据号
    line["associated_document"] = ""
    # 关联行号
    line["associated_document_items"] = 0
    # 原始单据类型
    line["origin_document_category"] = ""
    # 原始单据号
    line["origin_document"] = ""
    # 原始单据行号
    line["origin_document_items"] = 0

    if (md_header["post_code"] == "1" or md_header["post_code"] == "7") and line.get("rel_dn_sn", "") == "":
        line["associated_document_type"] = "PUR"
        line["associated_document"] = line.get("rel_po_sn", "")
        line["associated_document_items"] = line.get("rel_po_items", 0)
        line["origin_document_category"] = "PUR"
        line["origin_document"] = line.get("rel_po_sn", "")
        line["origin_document_items"] = line.get("rel_po_items", 0)
    elif (md_header["post_code"] == "1" or md_header["post_code"] == "7") and line.get("rel_dn_sn", "") != "":
        line["associated_document_type"] = "DLV"
        line["associated_document"] = line.get("rel_dn_sn", "")
        line["associated_document_items"] = line.get("rel_dn_item", 0)
        line["origin_document_category"] = "PUR"
        line["origin_document"] = line.get("rel_po_sn", "")
        line["origin_document_items"] = line.get("rel_po_items", 0)
    elif md_header["post_code"] == "2":
        line["associated_document_type"] = "PROD"
        line["associated_document"] = line.get("prodosn", "")
        line["associated_document_items"] = line.get("prodo_component_number", '')
        line["origin_document_category"] = "PROD"
        line["origin_document"] = line.get("prodosn", "")
        line["origin_document_items"] = line.get("prodo_component_number", '')
    elif md_header["post_code"] == "3" and line.get("prodosn", "") != "" and line.get("ro_sn", "") != "":
        line["associated_document_type"] = "RES"
        line["associated_document"] = line.get("ro_sn", "")
        line["associated_document_items"] = line.get("ro_items", 0)
        line["origin_document_category"] = "PROD"
        line["origin_document"] = line.get("prodosn", "")
        line["origin_document_items"] = line.get("prodo_component_number", '')
    elif md_header["post_code"] == "3" and line.get("prodosn", "") != "" and line.get("ro_sn", "") == "":
        line["associated_document_type"] = "PROD"
        line["associated_document"] = line.get("prodosn", "")
        line["associated_document_items"] = line.get("prodo_component_number", '')
        line["origin_document_category"] = "PROD"
        line["origin_document"] = line.get("prodosn", "")
        line["origin_document_items"] = line.get("prodo_component_number", '')
    elif md_header["post_code"] == "3" and line.get("prodosn", "") == "" and line.get("ro_sn", "") != "":
        line["associated_document_type"] = "RES"
        line["associated_document"] = line.get("ro_sn", "")
        line["associated_document_items"] = line.get("ro_items", 0)
        line["origin_document_category"] = "RES"
        line["origin_document"] = line.get("ro_sn", "")
        line["origin_document_items"] = line.get("ro_items", 0)
    elif md_header["post_code"] == "4" and line.get("ro_sn", "") != "":
        line["associated_document_type"] = "RES"
        line["associated_document"] = line.get("ro_sn", "")
        line["associated_document_items"] = line.get("ro_items", 0)
        line["origin_document_category"] = "RES"
        line["origin_document"] = line.get("ro_sn", "")
        line["origin_document_items"] = line.get("ro_items", 0)
    elif md_header["post_code"] == "6":
        line["associated_document_type"] = "DLV"
        line["associated_document"] = line.get("rel_dn_sn", "")
        line["associated_document_items"] = line.get("rel_dn_item", 0)
        line["origin_document_category"] = "SAL"
        line["origin_document"] = line.get("rel_so_sn", "")
        line["origin_document_items"] = line.get("rel_so_items", 0)

    return line


# 采购订单行项目批次绑定存在性检查
def check_if_po_batch_binding_exists(po_sn, po_items, rel_po_component_number, rel_po_comp_batch_num, dict_po_binding):
    # query_sql = """
    #     SELECT
    #         id
    #     FROM
    #         t_po_batch_binding
    #     WHERE
    #         po_sn = '{}'
    #     AND po_items = '{}'
    #     AND rel_po_component_number = '{}'
    #     AND rel_po_comp_batch_num = '{}'
    #     LIMIT 1
    # """.format(po_sn, po_items, rel_po_component_number, rel_po_comp_batch_num)
    # data = db.query_sql(query_sql)
    key = po_sn + str(po_items) + str(rel_po_component_number) + str(rel_po_comp_batch_num)
    if dict_po_binding.get(key):
        return False

    return True


# 采购订单组件存在检查
def check_if_po_component_exists(po_sn, po_items, rel_po_component_number, dict_po_component):
    # query_sql = """
    #     SELECT
    #         id
    #     FROM
    #         t_po_component
    #     WHERE
    #         po_sn = '{}'
    #     AND po_items = '{}'
    #     AND rel_po_component_number = '{}'
    #     LIMIT 1
    # """.format(po_sn, po_items, rel_po_component_number)
    # data = db.query_sql(query_sql)
    key = po_sn + str(po_items) + str(rel_po_component_number)
    if dict_po_component.get(key):
        return False

    return True


# 消耗记账 对象标识 价值更新 数量更新
def get_movement_label(line, po_sn, po_items, dict_movement_type, dict_mat_code, dict_po_item, dict_movement_label1,
                       dict_movement_label2, dict_movement_label3):
    # 消耗记账
    line["consumption_posting_label"] = ""
    # 对象标识
    line["item_indicator"] = ""
    # 价值更新
    line["value_update"] = 0
    # 数量更新
    line["qty_update_flag"] = 0
    qty_update1 = 0
    qty_update2 = 0
    qty_update3 = 0
    qty_update4 = 0

    msg = ''

    pur_item_cat = ""
    account_allocation_category = ""

    # query_sql = """
    #     SELECT
    #         qty_update_flag
    #     FROM
    #         t_movement_type
    #     WHERE
    #         movement_type = '{}'
    #     LIMIT 1
    # """.format(line["movement_type"])
    # data = db.query_sql(query_sql)
    if dict_movement_type.get(line["movement_type"]):
        qty_update1 = int(dict_movement_type[line["movement_type"]][0]["qty_update_flag"])

    # query_sql = """
    #     SELECT
    #         pur_item_cat,
    #         account_allocation_category
    #     FROM
    #         t_po_item
    #     WHERE
    #         po_sn = '{}'
    #     AND po_items = '{}'
    #     LIMIT 1
    # """.format(po_sn, po_items)
    # data = db.query_sql(query_sql)
    if dict_po_item.get(po_sn + str(po_items)):
        pur_item_cat = dict_po_item[po_sn + str(po_items)][0]["pur_item_cat"]
        account_allocation_category = dict_po_item[po_sn + str(po_items)][0]["account_allocation_category"]

    material_value_update = '0'

    # query_sql = """
    #     SELECT
    #         qty_update_flag,
    #         value_update
    #     FROM t_mmd_material_basic_data AS m
    #     JOIN t_mmd_material_type_range_limit AS t ON t.mat_type = m.mat_type
    #     WHERE
    #         t.plant_code = '{}'
    #     AND m.mat_code = '{}'
    #     LIMIT 1
    # """.format(line["plant_code"], line["mat_code"])
    # data = []
    # data = db.query_sql(query_sql)
    if dict_mat_code.get(line["mat_code"] + line["plant_code"]):
        material_value_update = dict_mat_code[line["mat_code"] + line["plant_code"]][0]["value_update"]
        qty_update2 = int(dict_mat_code[line["mat_code"] + line["plant_code"]][0]["qty_update_flag"])

    # query_sql = """
    #     SELECT
    #         u.consumption_posting_label,
    #         u.item_indicator,
    #         u.value_update,
    #         u.qty_update_flag
    #     FROM
    #         t_material_movement_update_label AS u
    #     WHERE
    #         u.pur_item_cat = '{}'
    #     AND u.account_allocation_category = '{}'
    #     AND  u.movement_type = '{}'
    #     AND u.material_value_update = '{}'
    #     LIMIT 1
    # """.format(pur_item_cat, account_allocation_category, line["movement_type"], material_value_update)
    # data = db.query_sql(query_sql)

    key1 = pur_item_cat + account_allocation_category + line["movement_type"] + str(material_value_update)
    key2 = pur_item_cat + account_allocation_category + str(material_value_update)
    key3 = pur_item_cat + account_allocation_category + str(material_value_update)
    if dict_movement_label1.get(key1):
        line["consumption_posting_label"] = dict_movement_label1[key1][0]["consumption_posting_label"]
        line["item_indicator"] = dict_movement_label1[key1][0]["item_indicator"]
        line["value_update"] = dict_movement_label1[key1][0]["value_update"]
        qty_update3 = int(dict_movement_label1[key1][0]["qty_update_flag"])
    # elif dict_movement_label2.get(key2):
    #     line["consumption_posting_label"] = dict_movement_label2[key2][0]["consumption_posting_label"]
    #     line["item_indicator"] = dict_movement_label2[key2][0]["item_indicator"]
    #     line["value_update"] = dict_movement_label2[key2][0]["value_update"]
    #     qty_update3 = int(dict_movement_label2[key2][0]["qty_update_flag"])
    # elif dict_movement_label3.get(key3):
    #     line["consumption_posting_label"] = dict_movement_label3[key3][0]["consumption_posting_label"]
    #     line["item_indicator"] = dict_movement_label3[key3][0]["item_indicator"]
    #     line["value_update"] = dict_movement_label3[key3][0]["value_update"]
    #     qty_update3 = int(dict_movement_label3[key3][0]["qty_update_flag"])
    #     query_sql = """
    #     SELECT
    #         u.consumption_posting_label,
    #         u.item_indicator,
    #         u.value_update,
    #         u.qty_update_flag
    #     FROM
    #         t_material_movement_update_label AS u
    #     WHERE
    #         u.pur_item_cat = '{}'
    #     AND u.account_allocation_category = '{}'
    #     AND  u.movement_type = ''
    #     AND u.material_value_update = '{}'
    #     LIMIT 1
    # """.format(pur_item_cat, account_allocation_category, material_value_update)
    #     data = db.query_sql(query_sql)
    #
    # if not data:
    #     query_sql = """
    #         SELECT
    #             u.consumption_posting_label,
    #             u.item_indicator,
    #             u.value_update,
    #             u.qty_update_flag
    #         FROM
    #             t_material_movement_update_label AS u
    #         WHERE
    #             u.pur_item_cat = '{}'
    #         AND u.account_allocation_category = '{}'
    #         AND u.material_value_update = '{}'
    #         LIMIT 1
    #     """.format(pur_item_cat, account_allocation_category, material_value_update)
    #     data = db.query_sql(query_sql)

    # if data:
    #     line["consumption_posting_label"] = data[0]["consumption_posting_label"]
    #     line["item_indicator"] = data[0]["item_indicator"]
    #     line["value_update"] = data[0]["value_update"]
    #     qty_update3 = int(data[0]["qty_update_flag"])

    if line["mat_code"] != "":
        qty_update4 = 1

    if qty_update1 == 0 or qty_update2 == 0 or qty_update3 == 0 or qty_update4 == 0:
        line["qty_update_flag"] = 0
    else:
        line["qty_update_flag"] = 1

    return line


# 获取采购订单数量金额等信息
def get_po_qty_amount_info(line, po_sn, po_items, dict_po_header, dict_po_item):
    # 定价单位
    line["pricing_unit_of_measure"] = ""
    # 定价单位数量
    line["pricing_unit_quantity"] = 0
    # 交易金额
    line["transaction_amount"] = 0
    # 交易货币
    line["transaction_currency"] = ""
    # 采购订单供应商
    line["po_vendor"] = ""

    # query_sql = """
    #     SELECT
    #         i.pricing_unit_of_measure,
    #         i.free_mark,
    #         i.unit_price_excluding_tax,
    #         h.currency_code,
    #         h.vendor_code
    #     FROM
    #         t_po_item AS i
    #         JOIN t_po_header AS h ON h.po_sn = i.po_sn
    #     WHERE
    #         i.po_sn = '{}'
    #     AND i.po_items = '{}'
    #     LIMIT 1
    # """.format(po_sn, po_items)
    # data = db.query_sql(query_sql)

    if dict_po_item.get(po_sn + str(po_items)):
        # 对比交易单位
        if dict_po_item[po_sn + str(po_items)][0]["pricing_unit_of_measure"] == line["transaction_uom"]:
            line["pricing_unit_of_measure"] = dict_po_item[po_sn + str(po_items)][0]["pricing_unit_of_measure"]
            line["pricing_unit_quantity"] = line["transaction_qty"]
        # 对比基本单位
        elif dict_po_item[po_sn + str(po_items)][0]["pricing_unit_of_measure"] == line["basic_uom"]:
            line["pricing_unit_of_measure"] = dict_po_item[po_sn + str(po_items)][0]["pricing_unit_of_measure"]
            line["pricing_unit_quantity"] = line["basic_qty"]
        # 对比平行单位
        elif dict_po_item[po_sn + str(po_items)][0]["pricing_unit_of_measure"] == line["parallel_uom"]:
            line["pricing_unit_of_measure"] = dict_po_item[po_sn + str(po_items)][0]["pricing_unit_of_measure"]
            line["pricing_unit_quantity"] = line["parallel_qty"]

        # 交易金额
        if dict_po_item[po_sn + str(po_items)][0]["free_mark"] == 1:
            line["transaction_amount"] = 0
        else:
            line["transaction_amount"] = round(line["pricing_unit_quantity"] * dict_po_item[po_sn + str(po_items)][0][
                "unit_price_excluding_tax"] / dict_po_item[po_sn + str(po_items)][0]['price_unit'], 2)
        line["transaction_currency"] = dict_po_header[po_sn][0]["currency_code"]
        line["po_vendor"] = dict_po_header[po_sn][0]["vendor_code"]
    return line


# 获取结算公司代码
def get_settle_company_code(plant_code, dict_company):
    # query_sql = """
    #     SELECT
    #         company_code
    #     FROM
    #         t_os_company_plant_alloc
    #     WHERE
    #         plant_code = '{}'
    # """.format(plant_code)
    # data = db.query_sql(query_sql)

    if dict_company.get(plant_code):
        return dict_company[plant_code][0]["company_code"]
    return ""


# 调拨使用-
def get_transaction_type_code4(line, from_mark, dict_po_item, dict_relation2, dict_mat_code):
    pur_item_cat = ''
    account_allocation_category = ''
    data = []
    if line.get('rel_po_sn', '') != '':
        # query_sql = """
        #     SELECT
        #         pur_item_cat,
        #         account_allocation_category
        #     FROM t_po_item
        #     WHERE po_sn = '{}'
        #     AND po_items = '{}'
        #     LIMIT 1
        # """.format(line["rel_po_sn"], line["rel_po_items"])
        # data = db.query_sql(query_sql)
        if dict_po_item.get(line["rel_po_sn"] + str(line["rel_po_items"])):
            pur_item_cat = dict_po_item[line["rel_po_sn"] + str(line["rel_po_items"])][0]["pur_item_cat"]
            account_allocation_category = dict_po_item[line["rel_po_sn"] + str(line["rel_po_items"])][0][
                "account_allocation_category"]

    special_inventory_status1 = ""
    special_inventory_status2 = ""

    mat_special_val_mark = ''
    if from_mark == 1:
        special_inventory_status1 = line["special_inventory_status1"]
        special_inventory_status2 = line["special_inventory_status2"]
        mat_special_val_mark = get_material_special_val_mark(line["mat_code"], line["plant_code"],
                                                             line["special_inventory_status1"], dict_mat_code)
        if mat_special_val_mark == "":
            mat_special_val_mark = get_material_special_val_mark(line["rcv_mat_code"], line["rcv_plant_code"],
                                                                 line["special_inventory_status1"], dict_mat_code)
    else:
        special_inventory_status1 = line["rcv_special_inventory_status1"]
        special_inventory_status2 = line["rcv_special_inventory_status2"]
        mat_special_val_mark = get_material_special_val_mark(line["rcv_mat_code"], line["rcv_plant_code"],
                                                             line["rcv_special_inventory_status1"], dict_mat_code)
        if mat_special_val_mark == "":
            mat_special_val_mark = get_material_special_val_mark(line["mat_code"], line["plant_code"],
                                                                 line["special_inventory_status1"], dict_mat_code)
    # data = []
    # query_sql = """
    #     SELECT
    #         transaction_type_code
    #     FROM
    #         t_Inventory_movement_relationship
    #     WHERE
    #         movement_type = '{}'
    #     AND pur_item_cat = '{}'
    #     AND account_allocation_category = '{}'
    #     AND special_inventory_status1 = '{}'
    #     AND special_inventory_status2 = '{}'
    #     AND mat_special_val_mark = '{}'
    #     and debit_credit_mark = '{}'
    #     LIMIT 1
    # """.format(line["movement_type"], pur_item_cat, account_allocation_category, special_inventory_status1,
    #            special_inventory_status2, mat_special_val_mark, line["debit_credit_mark"])
    # data = db.query_sql(query_sql)

    key = line[
              "movement_type"] + pur_item_cat + account_allocation_category + special_inventory_status1 + special_inventory_status2 + str(
        mat_special_val_mark) + line["debit_credit_mark"]
    if dict_relation2.get(key):
        return dict_relation2[key][0]["transaction_type_code"]

    return ""


# 获取物料评估标识
def get_material_special_val_mark(mat_code, plant_code, special_inventory_status1, dict_mat_code):
    # query_sql = """
    #     SELECT
    #         m.project_val_mark,
    #         m.so_val_mark,
    #         m.outsource_val_mark,
    #         m.other_special_val_mark
    #     FROM
    #         t_mmd_material_cost_data AS m
    #     WHERE
    #         m.mat_code = '{}'
    #     AND m.plant_code = '{}'
    #     LIMIT 1
    # """.format(mat_code, plant_code)
    # data = db.query_sql(query_sql)

    mat_special_val_mark = ""

    if dict_mat_code.get(mat_code + plant_code):
        if special_inventory_status1 == "P":
            if dict_mat_code[mat_code + plant_code][0]["project_val_mark"] == 1:
                mat_special_val_mark = "P"
        if special_inventory_status1 == "S":
            if dict_mat_code[mat_code + plant_code][0]["so_val_mark"] == 1:
                mat_special_val_mark = "S"
        if special_inventory_status1 == "V":
            if dict_mat_code[mat_code + plant_code][0]["outsource_val_mark"] == 1:
                mat_special_val_mark = "P"
        if special_inventory_status1 == "":
            mat_special_val_mark = ""

    return mat_special_val_mark


# 获取事件类型 物料成本评估标识
def get_transaction_type_code(movement_type, mat_code, plant_code, po_sn, po_items, special_inventory_status1,
                              special_inventory_status2, dict_relation, dict_po_item, dict_mat_code):
    pur_item_cat = ""
    account_allocation_category = ""

    # query_sql = """
    #     SELECT
    #         pur_item_cat,
    #         account_allocation_category
    #     FROM
    #         t_po_item
    #     WHERE
    #         po_sn = '{}'
    #     AND po_items = '{}'
    #     LIMIT 1
    # """.format(po_sn, po_items)
    # data = db.query_sql(query_sql)
    if dict_po_item.get(po_sn + str(po_items)):
        pur_item_cat = dict_po_item[po_sn + str(po_items)][0]["pur_item_cat"]
        account_allocation_category = dict_po_item[po_sn + str(po_items)][0]["account_allocation_category"]

    # query_sql = """
    #     SELECT
    #         project_val_mark,
    #         so_val_mark,
    #         outsource_val_mark,
    #         other_special_val_mark
    #     FROM
    #         t_mmd_material_cost_data
    #     WHERE
    #         mat_code = '{}'
    #     AND plant_code = '{}'
    #         LIMIT 1
    # """.format(mat_code, plant_code)
    # data = db.query_sql(query_sql)

    mat_special_val_mark = ""

    if dict_mat_code.get(mat_code + plant_code):
        if special_inventory_status1 == "P":
            if dict_mat_code[mat_code + plant_code][0]["project_val_mark"] == 1:
                mat_special_val_mark = "P"
        if special_inventory_status1 == "S":
            if dict_mat_code[mat_code + plant_code][0]["so_val_mark"] == 1:
                mat_special_val_mark = "S"
        if special_inventory_status1 == "V":
            if dict_mat_code[mat_code + plant_code][0]["outsource_val_mark"] == 1:
                mat_special_val_mark = "P"
        if special_inventory_status1 == "":
            mat_special_val_mark = ""

    key = movement_type + pur_item_cat + account_allocation_category + special_inventory_status1 + special_inventory_status2 + mat_special_val_mark
    # query_sql = """
    #     SELECT
    #         transaction_type_code
    #     FROM
    #         t_Inventory_movement_relationship
    #     WHERE
    #         movement_type = '{}'
    #     AND pur_item_cat = '{}'
    #     AND account_allocation_category = '{}'
    #     AND special_inventory_status1 = '{}'
    #     AND special_inventory_status2 = '{}'
    #     AND mat_special_val_mark = '{}'
    #     LIMIT 1
    # """.format(movement_type, pur_item_cat, account_allocation_category, special_inventory_status1,
    #            special_inventory_status2, mat_special_val_mark)
    # data = db.query_sql(query_sql)
    if dict_relation.get(key):
        return dict_relation[key][0]["transaction_type_code"], mat_special_val_mark

    return "", mat_special_val_mark


# 获取借贷标识和收发标识/科目修改/业务单据种类
def get_movement_attribute(line, movement_type, dict_movement_type):
    # 借贷标识
    line["debit_credit_mark"] = ""
    # 收发标识
    line["receipt_consume_mark"] = ""
    # 科目修改
    line["account_modify_code"] = ""
    # 业务单据种类
    line["business_doc_type"] = ""
    # 物料凭证类型
    material_document_type = ""
    # 订单必填标记
    prod_order_mark = 0
    # wbs必填标记
    wbs_elements_mark = 0
    # 成本事项必填标记
    cost_business_object_mark = 0
    # 资产必填标记
    asset_code1_mark = 0

    # query_sql = """
    #     SELECT
    #         debit_credit_mark,
    #         receipt_consume_mark,
    #         account_modify_code,
    #         business_doc_type,
    #         material_document_type,
    #         prod_order_mark,
    #         wbs_elements_mark,
    #         cost_business_object_mark,
    #         asset_related_flag
    #     FROM
    #         t_movement_type
    #     WHERE
    #         movement_type = '{}'
    # """.format(movement_type)
    #
    # data = db.query_sql(query_sql)

    if dict_movement_type.get(movement_type):
        line["debit_credit_mark"] = dict_movement_type[movement_type][0]["debit_credit_mark"]
        line["receipt_consume_mark"] = dict_movement_type[movement_type][0]["receipt_consume_mark"]
        line["account_modify_code"] = dict_movement_type[movement_type][0]["account_modify_code"]
        line["business_doc_type"] = dict_movement_type[movement_type][0]["business_doc_type"]
        line["document_update_flag"] = dict_movement_type[movement_type][0]["qty_update_flag"]
        prod_order_mark = dict_movement_type[movement_type][0]["prod_order_mark"]
        wbs_elements_mark = dict_movement_type[movement_type][0]["wbs_elements_mark"]
        cost_business_object_mark = dict_movement_type[movement_type][0]["cost_business_object_mark"]
        asset_code1_mark = dict_movement_type[movement_type][0]["asset_related_flag"]
        material_document_type = dict_movement_type[movement_type][0]["material_document_type"]

    return line, material_document_type, prod_order_mark, wbs_elements_mark, cost_business_object_mark, asset_code1_mark


# 按工厂查公司及汇率
def get_company_info(plant_code, transaction_currency, dict_company):
    company_code = ""
    rate = 0

    if dict_company.get(plant_code):
        if transaction_currency == "":
            transaction_currency = dict_company[plant_code][0]["basic_currency"]

        code, msg, rate = get_exchange_rate(dict_company[plant_code][0]["rate_type"], "", transaction_currency,
                                            dict_company[plant_code][0]["basic_currency"])
        company_code = dict_company[plant_code][0]["company_code"]

    return company_code, rate


def check_if_overcharge(po_sn, po_items, line, item, dict_md_info1, dict_md_info2, dict_pi_invoice_info, dict_po_item):
    # 退货校验
    if line["debit_credit_mark"] == "Cr" and line["rel_document_no"] != "":
        return_qty = 0
        invoice_qty = 0
        transaction_qty = 0

        # query_sql = """
        #     SELECT
        #         year,
        #         mat_doc_sn,
        #         posting_date,
        #         company_code
        #     FROM
        #         t_md_header
        #     WHERE
        #         year = '{}'
        #     AND
        #         mat_doc_sn = '{}'
        #     LIMIT 1
        # """.format(line["rel_document_year"], line["rel_document_no"])
        # data = []
        # data = db.query_sql(query_sql)
        # if data:
        #     table = 't_md_item_' + str(data[0]['company_code']) + '_' + str(data[0]['posting_date'][:4]) + '_' + str(
        #         data[0]['posting_date'][5:7])
        #     # 交易数量
        #     query_sql = """
        #         SELECT
        #             sum( transaction_qty ) AS transaction_qty,
        #             sum( cost_qty ) AS cost_qty,
        #             sum( basic_qty ) AS basic_qty,
        #             sum( parallel_qty ) AS parallel_qty
        #         FROM
        #             {} AS t
        #             JOIN t_md_header AS h ON h.year = t.year and h.mat_doc_sn = t.mat_doc_sn
        #             AND h.post_code = '1'
        #         WHERE t.year = '{}'
        #             AND t.mat_doc_sn = '{}'
        #             AND t.mat_doc_items = '{}'
        #             AND t.reversed_mark = 0
        #             AND t.reversal_mark = 0
        #             AND t.debit_credit_mark = 'Dr'
        #     """.format(table, line["rel_document_year"], line["rel_document_no"], line["ref_document_mat"])
        #     md_data = db.query_sql(query_sql)
        #     if md_data:
        #         transaction_qty = md_data[0]["transaction_qty"]
        #
        #
        #     # 获取已退货数
        #     query_sql = """
        #         SELECT
        #             sum( transaction_qty ) AS transaction_qty,
        #             sum( cost_qty ) AS cost_qty,
        #             sum( basic_qty ) AS basic_qty,
        #             sum( parallel_qty ) AS parallel_qty
        #         FROM
        #             {} AS t
        #             JOIN t_md_header AS h ON h.year = t.year and h.mat_doc_sn = t.mat_doc_sn
        #             AND h.post_code = '1'
        #         WHERE t.rel_document_year = '{}'
        #             AND t.rel_document_no = '{}'
        #             AND t.ref_document_mat = '{}'
        #             AND t.reversed_mark = 0
        #             AND t.reversal_mark = 0
        #             AND t.debit_credit_mark = 'Cr'
        #     """.format(table, line["rel_document_year"], line["rel_document_no"], line["ref_document_mat"])
        #     return_data = db.query_sql(query_sql)
        #     if return_data:
        #         return_qty = return_data[0]["transaction_qty"]
        #     # 获取发票数
        #     invoice_item_table = get_pi_invoice_item_view(db)
        #     query_sql = """
        #             select
        #                 sum( order_qty ) AS transaction_qty,
        #                 sum( cost_qty ) AS cost_qty,
        #                 sum( basic_qty ) AS basic_qty,
        #                 sum( parallel_qty ) AS parallel_qty
        #             from {} as i
        #             join t_pi_invoice_header as h on h.invoice_doc_sn = i.invoice_doc_sn
        #             and h.pi_doc_year = i.pi_doc_year
        #             where i.mat_doc_year = '{}'
        #             and i.mat_doc_sn = '{}'
        #             and i.mat_doc_items = '{}'
        #             and h.reversal_mark = 0
        #             and h.reversed_mark = 0
        #     """.format(invoice_item_table, line["rel_document_year"], line["rel_document_no"], line["ref_document_mat"])
        #     invoice_data = db.query_sql(query_sql)
        #     if invoice_data:
        #         invoice_qty = invoice_data[0]["transaction_qty"]

        key = str(line["rel_document_year"]) + line["rel_document_no"] + str(line["ref_document_mat"])
        # 交易数量
        if dict_md_info1.get(key):
            transaction_qty = dict_md_info1[key][0]['transaction_qty']
        # 已退货数
        if dict_md_info2.get(key):
            return_qty = dict_md_info2[key][0]['transaction_qty']
        # 发票数量
        if dict_pi_invoice_info.get(key):
            invoice_qty = dict_pi_invoice_info[key][0]['transaction_qty']

        if return_qty + line["transaction_qty"] > transaction_qty - invoice_qty:
            return "行标识{}交易数量超出可退货数量，可退货数量=凭证收货数量-已发票校验数量".format(line["line_id"])
    else:
        # 收货校验
        # query_sql = """
        #     SELECT
        #         receipt_completed_flag,
        #         unlimited_tolerance,
        #         underdelivery_tolerance,
        #         overdelivery_tolerance,
        #         order_qty,
        #         received_pur_qty
        #     FROM
        #         t_po_item
        #     WHERE
        #         po_sn = '{}'
        #     AND po_items = '{}'
        #         LIMIT 1
        # """.format(po_sn, po_items)
        # data = db.query_sql(query_sql)
        key = po_sn + str(po_items)
        if dict_po_item.get(key):
            k = dict_po_item[key][0]
            # 收货未完成
            if k["receipt_completed_flag"] != 1:
                # 无限收货不校验
                if k["unlimited_tolerance"] != 1:
                    transaction_qty = 0
                    for each in item:
                        if each["rel_po_sn"] == po_sn and each["rel_po_items"] == po_items and each.get('parent_id',
                                                                                                        0) == 0:
                            transaction_qty += each["transaction_qty"]
                    # 本次交易数量 + 已收货数量 > 订单数量*（1+超量容差） 则报错
                    if transaction_qty + k["received_pur_qty"] > k["order_qty"] * (
                            1 + k["overdelivery_tolerance"] / 100):
                        return "行标识{}采购订单{}行项目{}超量收货".format(line["line_id"], line["rel_po_sn"],
                                                                           line["rel_po_items"])

    return ''


def check_po_item_status(post_code, po_sn, po_items, dict_po_item):
    if dict_po_item.get(po_sn + str(po_items)) is None:
        return "采购订单{}行项目{}不存在".format(po_sn, po_items)
    else:
        if dict_po_item[po_sn + str(po_items)][0]["pur_item_cat"] == "L" and post_code == '1':
            return "外协订单{}请使用外协收货".format(po_sn)
        if dict_po_item[po_sn + str(po_items)][0]["receipt_completed_flag"] == 1:
            return "当前采购订单{}行项目{}已完成收货".format(po_sn, po_items)
        if dict_po_item[po_sn + str(po_items)][0]["deleted_mark"] == 1:
            return "当前采购订单{}行项目{}已删除".format(po_sn, po_items)
        if dict_po_item[po_sn + str(po_items)][0]["lock_flag"] == 1:
            return "当前采购订单{}行项目{}已锁定".format(po_sn, po_items)
    return ""
    # query_sql = """
    #     SELECT
    #         pur_item_cat,
    #         receipt_completed_flag,
    #         deleted_mark,
    #         lock_flag
    #     FROM
    #         t_po_item
    #     WHERE
    #         po_sn = '{}'
    #     AND po_items = '{}'
    #         LIMIT 1
    # """.format(po_sn, po_items)
    # data = db.query_sql(query_sql)
    #
    # if data:
    #     if data[0]["pur_item_cat"] == "L":
    #         return "外协订单{}请使用外协收货".format(po_sn)
    #     if data[0]["receipt_completed_flag"] == "1":
    #         return "当前采购订单{}行项目{}已完成收货".format(po_sn, po_items)
    #     if data[0]["deleted_mark"] == "1":
    #         return "当前采购订单{}行项目{}已删除".format(po_sn, po_items)
    #     if data[0]["lock_flag"] == "1":
    #         return "当前采购订单{}行项目{}已锁定".format(po_sn, po_items)
    # else:
    #     return "采购订单{}行项目{}不存在".format(po_sn, po_items)
    #
    # return ""


def check_po_status(po_sn, dict_po_header):
    if dict_po_header.get(po_sn) is None:
        return "采购订单{}不存在".format(po_sn)
    else:
        if dict_po_header[po_sn][0]['deleted_mark'] == 1:
            return "采购订单{}已删除".format(po_sn)
        if dict_po_header[po_sn][0]['lock_flag'] == 1:
            return "采购订单{}已锁定".format(po_sn)
        if dict_po_header[po_sn][0]['approval_status'] != 'D' and dict_po_header[po_sn][0]['approval_status'] != 'E':
            return "采购订单{}未审批".format(po_sn)
    return ""

    # query_sql = """
    #     SELECT
    #         approval_status,
    #         deleted_mark,
    #         lock_flag
    #     FROM
    #         t_po_header
    #     WHERE
    #         po_sn = '{}'
    #         LIMIT 1
    # """.format(po_sn)
    # data = db.query_sql(query_sql)
    #
    #
    # if data:
    #     if data[0]["deleted_mark"] == "1":
    #         return "采购订单{}已删除".format(po_sn)
    #     if data[0]["lock_flag"] == "1":
    #         return "采购订单{}已锁定".format(po_sn)
    #     if data[0]["approval_status"] != "D" and data[0]["approval_status"] != "E":
    #         return "采购订单{}未审批".format(po_sn)
    # else:
    #     return "采购订单{}不存在".format(po_sn)
    #
    # return ""


def check_batch_required4(mat_code, plant_code, batch_sn, debit_credit_mark, dict_mat_code, dict_mat_batch,
                          batch_number, dict_movement_type):
    # query_sql = """
    #     select batch_mark
    #     from t_mmd_material_plant_data
    #     where mat_code = '{}'
    #     and plant_code = '{}'
    #     and deleted_mark = '0'
    #     and lock_flag = '0'
    #     limit 1
    # """.format(mat_code, plant_code)
    # data = []
    # data = db.query_sql(query_sql)
    print("plant_code,,,batch_sn:",plant_code,batch_sn)
    if dict_mat_code.get(mat_code + plant_code):
        if dict_mat_code[mat_code + plant_code][0]["batch_mark"] == 1:
            if batch_sn == "":
                return batch_sn, batch_number, "批次编码必输"
            else:
                # 批次存在性校验
                if check_if_batch_sn_exists(mat_code, batch_sn, dict_mat_batch):
                    if dict_mat_batch[mat_code + batch_sn][0]['batch_status_mark'] == 2 and dict_movement_type[
                        'activation_flag'] == 1:
                        return batch_sn, batch_number, "批次编码{}为限制状态,禁止过账".format(batch_sn)
                    return batch_sn, batch_number, ""
                else:
                    if debit_credit_mark == "Cr":
                        return batch_sn, batch_number, "批次编码{}不存在".format(batch_sn)
                    else:
                        return batch_sn, batch_number, ""
        else:
            return "", {}, ""
    return "", {}, ""


def check_batch_required(mat_code, plant_code, batch_sn, debit_credit_mark, dict_mat_code, dict_mat_batch,
                         batch_number, dict_movement_type, user_id=None):
    # query_sql = """
    #     select batch_mark
    #     from t_mmd_material_plant_data
    #     where mat_code = '{}'
    #     and plant_code = '{}'
    #     and deleted_mark = '0'
    #     and lock_flag = '0'
    #     limit 1
    # """.format(mat_code, plant_code)
    # data = []
    # data = db.query_sql(query_sql)
    if dict_mat_code.get(mat_code + plant_code):
        if dict_mat_code[mat_code + plant_code][0]["batch_mark"] == 1:
            if batch_sn == "":
                if debit_credit_mark == "Cr":
                    return batch_sn, batch_number, "批次编码必输"
                else:
                    # 创建批次
                    from DXBatchDataSave import CreateBatchData
                    code, msg, batch_sn = CreateBatchData(mat_code, user_id)
                    if code == 200:
                        return batch_sn, batch_number, ""
                    else:
                        return "", batch_number, msg
                return "", batch_number, ""
            else:
                # 批次存在性校验
                if check_if_batch_sn_exists(mat_code, batch_sn, dict_mat_batch):
                    if dict_mat_batch[mat_code + batch_sn][0]['batch_status_mark'] == 2 and dict_movement_type[
                        'activation_flag'] == 1:
                        return batch_sn, batch_number, "批次编码{}为限制状态,禁止过账".format(batch_sn)
                    return batch_sn, batch_number, ""
                else:
                    if debit_credit_mark == "Cr":
                        return batch_sn, batch_number, "批次编码{}不存在".format(batch_sn)
                    else:
                        return batch_sn, batch_number, ""
        else:
            return "", {}, ""

    return "", {}, ""


# 批次存在性校验
def check_if_batch_sn_exists(mat_code, batch_sn, dict_mat_batch):
    # query_sql = """
    #     select id
    #     from t_batch_number
    #     where mat_code = '{}'
    #     and batch_sn = '{}'
    #     limit 1
    # """.format(mat_code, batch_sn)
    # data = db.query_sql(query_sql)
    if dict_mat_batch.get(mat_code + batch_sn):
        return True

    return False


# def check_if_inventory_status_exists(inventory_status):
#     if inventory_status == "0":
#         return True

#     if inventory_status == "1":
#         return True

#     if inventory_status == "2":
#         return True

#     return False
def check_if_inventory_status_exists(inventory_status, db):

    sql = f"SELECT `inventory_status` FROM `t_inventory_status` WHERE `inventory_status` = '{inventory_status}'"
    print(sql)
    result = db.query_sql(sql)
    return len(result) > 0


def get_plant_of_company(plantGroup, db):
    query_sql = """
        SELECT DISTINCT
            `company_code` 
        FROM
            `t_os_company_plant_alloc` 
        WHERE
            `plant_code` IN ('{}')
    """.format("','".join(plantGroup))
    data = db.query_sql(query_sql)

    if len(data) > 1:
        return ''

    if not data:
        return 'X'
    return data[0]["company_code"]


def get_material_uom(mat_code, plant_code, dict_mat_code, line):
    # query_sql = """
    #     SELECT b.basic_uom,
    #            c.cost_uom
    #     FROM
    #         t_mmd_material_basic_data as b
    #     LEFT JOIN t_mmd_material_cost_data as c
    #     on b.mat_code = c.mat_code
    #     WHERE
    #         b.mat_code = '{}'
    #     AND c.plant_code = '{}'
    # """.format(mat_code, plant_code)
    # data = db.query_sql(query_sql)

    if dict_mat_code.get(mat_code + plant_code):
        line["basic_uom"] = dict_mat_code[mat_code + plant_code][0]["basic_uom"]
        line["cost_uom"] = dict_mat_code[mat_code + plant_code][0]["cost_uom"]
        line["mat_group"] = dict_mat_code[mat_code + plant_code][0]["mat_group"]
        line["plant_val_class"] = dict_mat_code[mat_code + plant_code][0]["plant_val_class"]
        line["price_control"] = dict_mat_code[mat_code + plant_code][0]["price_control"]

    return line


def get_other_qty_by_unit(each, item, post_code, allow_zero_base_qty, allow_zero_parallel_qty, dict_mat_uom_convert):
    code = 0
    qty = 0

    item['basic_qty'] = each.get('basic_qty', 0)

    if item['parallel_uom'] == item["transaction_uom"]:
        if item['basic_qty'] == 0:
            if post_code == '3' or post_code == '5' or post_code == '7':
                if allow_zero_base_qty == 0:
                    # 按交易单位获取基本数量
                    code, msg, qty = convert_material_unit_qty(item["mat_code"], item["transaction_uom"],
                                                               item["basic_uom"], item["transaction_qty"],
                                                               dict_mat_uom_convert)
                    if code == 200:
                        item["basic_qty"] = qty

            else:
                # 按交易单位获取基本数量
                code, msg, qty = convert_material_unit_qty(item["mat_code"], item["transaction_uom"],
                                                           item["basic_uom"], item["transaction_qty"],
                                                           dict_mat_uom_convert)
                if code == 200:
                    item["basic_qty"] = qty

    else:
        # 按交易单位获取基本数量
        code, msg, qty = convert_material_unit_qty(item["mat_code"], item["transaction_uom"], item["basic_uom"],
                                                   item["transaction_qty"], dict_mat_uom_convert)
        if code == 200:
            item["basic_qty"] = qty

    # 获取平行数量
    item['parallel_qty'] = each.get('parallel_qty', 0)

    if each.get('parallel_uom'):
        if each['parallel_uom'] != item["transaction_uom"]:
            if item["parallel_qty"] == 0:
                if post_code == '3' or post_code == '5' or post_code == '7':
                    if allow_zero_parallel_qty == 0:
                        # 按基本单位获取平行数量
                        code, msg, qty = convert_material_unit_qty(item["mat_code"], item["basic_uom"],
                                                                   item["parallel_uom"],
                                                                   item["basic_qty"], dict_mat_uom_convert)
                        if code == 200:
                            item["parallel_qty"] = qty

                # else:
                #     # 按基本单位获取平行数量
                #     code, msg, qty = convert_material_unit_qty(item["mat_code"], item["basic_uom"],
                #                                                item["parallel_uom"],
                #                                                item["basic_qty"])
                #     if code == 200:
                #         item["parallel_qty"] = qty
        else:
            # 按交易单位获取平行数量
            code, msg, qty = convert_material_unit_qty(item["mat_code"], item["transaction_uom"], item["parallel_uom"],
                                                       item["transaction_qty"], dict_mat_uom_convert)
            if code == 200:
                item["parallel_qty"] = qty

    if item['cost_uom'] == item['basic_qty']:
        item['cost_qty'] = item['basic_qty']
    elif item['cost_uom'] == item['parallel_uom']:
        item['cost_qty'] = item['parallel_qty']
    else:
        # 按基本单位和成本单位获取转换关系数量
        code, msg, qty = convert_material_unit_qty(item["mat_code"], item["basic_uom"], item["cost_uom"],
                                                   item["basic_qty"], dict_mat_uom_convert)
        if code == 200:
            item["cost_qty"] = qty
        else:
            # 按平行单位和成本单位获取转换关系数量
            code, msg, qty = convert_material_unit_qty(item["mat_code"], item["parallel_uom"], item["cost_uom"],
                                                       item["parallel_qty"], dict_mat_uom_convert)
            if code == 200:
                item["cost_qty"] = qty

    return item


def convert_material_unit_qty(mat_code, primary_uom, secondary_uom, primary_uom_qty, dict_mat_uom_convert):
    """
    根据物料单位换算关系计算数量-主单位和辅单位调换位置进行查找转换关系
    :param mat_code: 物料编码
    :param primary_uom: 主单位
    :param secondary_uom: 辅单位
    :param primary_uom_qty: 主单位数量
    :return code: 状态码
    :return msg: 消息
    :retuan qty: 换算结果数量
    """
    code = 200
    msg = ""
    qty = 0
    if isinstance(primary_uom_qty, str):
        primary_uom_qty = float(primary_uom_qty)
    if primary_uom == "":
        code = 500
        msg = "请输入主单位primary_uom"
        return code, msg, qty
    if secondary_uom == "":
        code = 500
        msg = "请输入辅单位"
        return code, msg, qty

    if primary_uom == secondary_uom:
        qty = primary_uom_qty
        return code, msg, qty

    # dh = DbHelper()
    # query_sql = """
    #     SELECT
    #         mat_code,
    #         primary_uom,
    #         primary_uom_qty,
    #         secondary_uom,
    #         secondary_uom_qty
    #     FROM
    #         t_mmd_uom_conversion
    #     WHERE
    #         mat_code = '{}'
    #     AND primary_uom = '{}'
    #     AND secondary_uom = '{}'
    #     LIMIT 1
    # """.format(mat_code, primary_uom, secondary_uom)
    # print("query_sql", query_sql)
    # data = dh.query_sql(query_sql)

    key = mat_code + primary_uom + secondary_uom

    if dict_mat_uom_convert.get(key):
        item = dict_mat_uom_convert[key][0]
        # 设置 Decimal 上下文，提高精度
        getcontext().prec = 20  # 设置更高的精度
        getcontext().rounding = ROUND_HALF_UP  # 设置舍入模式

        x = Decimal(str(primary_uom_qty))
        y = Decimal(str(item["primary_uom_qty"]))
        z = Decimal(str(item["secondary_uom_qty"]))

        # 分步计算，便于调试
        division_result = x / y
        multiplication_result = division_result * z
        quantized_result = multiplication_result.quantize(Decimal('0.001'))
        qty = float(quantized_result)

    else:
        # query_sql = """
        #     SELECT
        #         mat_code,
        #         primary_uom,
        #         primary_uom_qty,
        #         secondary_uom,
        #         secondary_uom_qty
        #     FROM
        #         t_mmd_uom_conversion
        #     WHERE
        #         mat_code = '{}'
        #     AND secondary_uom = '{}'
        #     AND primary_uom = '{}'
        #     LIMIT 1
        # """.format(mat_code, primary_uom, secondary_uom)
        # data = dh.query_sql(query_sql)

        key = mat_code + secondary_uom + primary_uom
        if dict_mat_uom_convert.get(key):
            item = dict_mat_uom_convert[key][0]
            qty = float((Decimal(str(primary_uom_qty)) * Decimal(str(item["primary_uom_qty"])) / Decimal(
                str(item["secondary_uom_qty"]))))
        else:
            code = 500
            msg = "未找到该物料的转换关系"

    qty = round(qty, 3)

    return code, msg, qty


def initialization(object_name, db):
    table = db.get_columns_by_table(object_name)
    data = {}
    for each in table:
        if each['name'] != 'create_time' and each['name'] != 'update_time':
            if 'decimal' in each["type"] or 'double' in each["type"] or 'int' in each['type']:
                data[each["name"]] = 0
            else:
                data[each["name"]] = each["default_value"]

    return data


def get_batch_status_mark(item, db):
    mat_code = [i['mat_code'] for i in item if i['mat_code']]
    if not mat_code:
        return []

    mat_code = list(set(mat_code))

    mat_code_to_batch_status = {}
    sql = """
        SELECT
            t.`mat_code`,
            t.`mat_type`,
            tb.`batch_status_mark`
            FROM
                `t_mmd_material_basic_data` as t
            LEFT JOIN
                `t_mmd_material_type` as tb
            ON t.`mat_type` = tb.`mat_type`
        WHERE
            `mat_code` in ('{}')
    """.format("','".join(mat_code))

    sql_data = db.query_sql(sql)

    for each in sql_data:
        mat_code_to_batch_status[each['mat_code']] = each['batch_status_mark']

    return mat_code_to_batch_status


def updata_batch_status_mark(md_item, mat_code_to_batch_status):
    print(f'mat_code_to_batch_status------------------{mat_code_to_batch_status}')
    for item in md_item:
        if not mat_code_to_batch_status:
            continue
        mat_code = item["mat_code"]
        item['batch_number']['batch_status_mark'] = mat_code_to_batch_status.get(mat_code, 0)
    return md_item
