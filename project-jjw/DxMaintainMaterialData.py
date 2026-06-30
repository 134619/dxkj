#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@File    : DxMaintainMaterialData.py
@Author  : dongliang.wang@dxdstech.com
@Date    : 2024/10/8 10:35
@explain : 数据管理-物料数据
"""
import re
import traceback
from datetime import datetime
from typing import DefaultDict

import pandas as pd
from DbHelper import DbHelper  # type:ignore
from GenerateSerialNum import generate_serial_num  # type:ignore
from libenhance import exec_operator  # type:ignore
from logger import LoggerConfig
from ZZEXT_DxMaintainMaterialData import (  # type:ignore
    after_save,
    before_check,
    before_save,
)

a = '- a -'
u = 'asdf'
s = '456789'
usprint = LoggerConfig('')

dh = DbHelper()
TEST = False



def maintain_data(test_run, basic, plant, sales, financial, cost, uomconv, memo, detail, mode, user_id, quality=[],
                  db=None, **kwargs):
    """
        物料主数据维护
        :param test_run: 0-正式运行 / 1-测试运行
        :param basic: 基本视图  对象
            mat_code        物料编码
            description     物料描述
            old_mat_code    旧物料编码
            old_description 旧物料描述
            basic_uom       基本单位
            parallel_uom    平行单位
            parallel_uom_mark   平行单位标记
            mat_type    物料类型
            mat_group   物料组
            mat_group_2 二级物料组
            prod_group  产品组
            prod_group_2    二级产品组
            mat_status      物料状态
            deleted_mark    删除标记
            locked_mark     锁定标识
            priority_code        优先级
            capacity_dimension  产能维度
            external_mat_code   外部编码
            net_weight      净重
            gross_weight    毛重
            weight_uom      重量单位
            volume      体积
            volume_uom  体积单位
            sub_group   替代组（工厂视图字段）
            process_code    制程
            low_level_code  低阶码
            remarks     备注信息
            eol_mark ??（全局未用到）
            retest_yield  复测良率（工厂视图字段）
            shelf_life_enabled     启用保质期管理
            shelf_life_days     保质期天数
            note    备注
        :param plant: 工厂视图  列表
            列表item 对象
                mat_code    物料编码
                plant_code  工厂代码
                batch_mark  批次管理
                granularity_uom     批次颗粒度单位
                pur_group   采购组
                pur_uom     采购单位
                pur_uom_2   第二采购单位
                prod_uom    生产单位
                source_mark     货源管理
                quality_inspection_mark     质检库存标记
                plan_group  计划组
                sub_group   替代组
                lot_size    LOT类型
                lot_uom     批量单位
                max_lot     最大批量数量
                min_lot     最小批量数量
                mpq         最小包装数量
                safety_type     安全库存类型
                safety_stock    安全库存
                reorder_point   再订货点数量
                pur_type        采购类型
                dely_period     采购提前期
                prod_period     生产周期
                trans_period    运输时间
                insp_period     检验时间
                waiting_time    等待时间
                assembly_loss_rate  装配损耗率
                yield     组件损耗率
                deleted_mark    删除标记
                locked_mark     锁定标识
                special_pur_type    特殊采购类型
                stor_loc_code   库存地点
                stor_loc_code2  发料库存地点
                ven_mat_code    供应商物料编码
                fixed_vendor    指定供应商
                bulk_material   散装物料标记
                if_centralized_supply  集中供应标记
                mrp_type    MRP类型
                planning_strategy   计划策略
                forward_supply_days     向前供给天数
                planning_material_mode  计划物料模式
                planning_material_code  计划物料编码
                source_of_demand    需求来源
                production_manager  生产管理员
                backflush_flag  反冲标记
                retest_yield    复测良率
                note    备注

        :param sales: 销售视图  列表
            列表item 对象
                mat_code        物料编码
                sales_org_code  销售组织
                deleted_mark    删除标记
                locked_mark     锁定标识
                min_order_qty   最小订货量
                min_delivery_qty    最小交货量
                default_plant   默认交货工厂
                sales_uom       销售单位
                sales_uom_2     第二销售单位
                item_category_group     项目类别组
                mat_price_group         销售价格组
                note    备注

        :param financial: 财务视图  列表
            列表item 对象
                mat_code    物料编码
                plant_code  工厂代码
                profit_center   利润中心
                deleted_mark    删除标记
                locked_mark     锁定标识
                mat_acc_group   物料销售科目组
                mat_sales_tax_code  物料销售税码
                plant_val_class     评估类
                note    备注

        :param cost: 成本视图   列表
            列表item 对象
                mat_code        物料编码
                plant_code      工厂代码
                cost_uom        成本单位
                plant_val_mark      工厂物料评估标识
                version_val_mark    版本评估标识
                batch_val_mark      批次评估标识
                other_special_val_mark  其他特殊评估标识
                outsource_val_mark      外协加工采购评估标识
                project_val_mark        项目评估标识
                stor_loc_val_mark       库存地点评估标识
                so_val_mark         销售订单评估标识
                valgroup_value      评估组选择值
                mat_cost_classify   物料成本分类
                co_currency         成本货币
                plan_cost_bc        计划价格
                plan_cost_rate      计划价格汇率
                effective_start_date        生效日期
                basic_currency      本位币
                price_control       价格控制
                price_unit          价格单位 -> 价格批量
                cost_lot         成本核算批量数量
                std_pur_type        标准成本计算类型
                special_pur_cc      成本采购类型
                deleted_mark        删除标记
                locked_mark         锁定标识
                mat_consumption     生产消耗方式
                pir_version     评估版本
                banch_key       评估批次
                plan_cost_currency  计划价格币种
                wbs_elements        WBS元素
                note        备注
                plan_cost_cc ?? （全局未用到）

        :param uomconv: 单位转换    列表
            列表item 对象
                index       行索引
                mat_code    物料编码
                primary_uom 主单位
                primary_uom_qty 主单位值
                secondary_uom   辅单位
                secondary_uom_qty   辅单位值
                equal   "="（展示符号 未存表）
                note    备注

        :param memo: 长文本备注  （对象）
            mat_code    物料编码
            long_text        说明

        :param detail: 属性   列表
            列表item 对象
                mat_code    物料编码
                property_group  特性组
                field_type      字段类型
                field_length    字段长度
                required    必填标识
                decimal_length  精度
                field_mark  单一值标识
                field_name  字段名称
                field_code  字段代码
                field_value 字段（属性值）值
                field_value_from    字段值（属性值）从
                field_value_to      字段值（属性值）到
                以下字段值按照 单一值标识和字段类型 从字段值、属性值从、属性值到 拆分映射到数据表字段
                （
                    field_value_from    char字段值从
                    field_value_to      char字段值到
                    field_value_int     int字段值
                    field_value_int_from    int字段值从
                    field_value_int_to      int字段值到
                    field_value_date        date字段值
                    field_value_date_from   date字段值从
                    field_value_date_to     date字段值到
                    field_value_time        time字段值
                    field_value_time_from   time字段值从
                    field_value_time_to     time字段值到
                    field_value_decimal     decimal字段值
                    field_value_decimal_from    decimal字段值从
                    field_value_decimal_to      decimal字段值到
                ）
                property_description 特性组描述（展示使用 未存表）
                _key_   行key
                note    备注

        :param quality: 工厂视图下 质量检验表格 列表
            列表item 对象
                mat_code    物料编码
                plant_code  工厂代码
                inspection_type 检验类型
                activation_flag 激活标记
                update_id   更新人
                note        备注

        :param mode: A-新建  B-扩展

        :return code: 状态码
        :return msg: 消息
        :return error_list: 错误明细
        :return mat_code: 物料编码
    """
    global TEST
    TEST = kwargs.get("TEST", False)
    TEST and usprint.printInfo("test_run", test_run)
    TEST and usprint.printInfo("basic", basic)
    TEST and usprint.printInfo("plant", plant)
    TEST and usprint.printInfo("sales", sales)
    TEST and usprint.printInfo("financial", financial)
    TEST and usprint.printInfo("cost", cost)
    TEST and usprint.printInfo("uomconv", uomconv)
    TEST and usprint.printInfo("memo", memo)
    TEST and usprint.printInfo("detail", detail)
    TEST and usprint.printInfo("mode", mode)
    TEST and usprint.printInfo("user_id", user_id)
    TEST and usprint.printInfo("quality", quality)

    global dh
    if db is not None:
        dh = db
    code = 200
    msg = ""
    error_list = []
    mat_code = ""
    uom = []
    code, msg, error_list, basic, plant, sales, financial, cost, uomconv, memo, detail, mode, quality \
        = before_check(dh, user_id, basic, plant, sales, financial, cost, uomconv, memo, detail, mode, quality)
    if code != 200:
        return code, msg, error_list, mat_code

    error_list = checkBasicView(basic, error_list, mode)
    error_list = checkFieldDetail(detail, error_list)
    error_list, uom = checkPlantView(plant, error_list, basic["basic_uom"], uom, mode=mode, basic=basic)
    error_list = checkFinancialView(financial, error_list, mode=mode, control=kwargs.get("control", []))
    error_list, cost, uom = checkCostView(cost, error_list, basic["basic_uom"], basic["parallel_uom"], uom, mode=mode)
    error_list, uom = checkSalesView(sales, error_list, uom, mode=mode)
    error_list = checkUomConv(uomconv, error_list, basic, uom, mode)
    if quality:
        error_list = checkQualityInspec(quality, error_list)
    if error_list:
        code = 500
        msg = "存在错误请检查"
    else:
        if test_run == 0:
            code, msg, error_list, basic, plant, sales, financial, cost, uomconv, memo, detail, mode, quality \
                = before_save(dh, user_id, basic, plant, sales, financial, cost, uomconv, memo, detail, mode, quality)
            if code != 200:
                return code, msg, error_list, mat_code
            try:
                mat_code = saveAllData(mode, user_id, basic, plant, financial, cost, sales, uomconv, memo, detail,
                                       quality)
            except Exception as e:
                usprint.printInfo(a,f"maintain_data 保存失败{e}")
                traceback.print_exc()
                raise Exception(e)
                # ValueError 当前类型未分配编码域，请检查
                return 500, str(e), [{"msg": str(e)}], ""
            code, msg, error_list, basic, plant, sales, financial, cost, uomconv, memo, detail, mode, quality \
                = after_save(dh, user_id, mat_code, basic, plant, sales, financial, cost, uomconv, memo, detail, mode,
                             quality)
            if code != 200:
                return code, msg, error_list, mat_code

            exec_operator("material", "", {})
            if code == 200:
                msg = "保存成功"
        else:
            if code == 200:
                msg = "测试运行成功"

    return code, msg, error_list, mat_code


# 换算关系
def add_uom_conv(uomconv, basic, mat_code, mode):
    """
        为 uomconv 添加一条 1 基本单位 = 1 基本单位换算关系

        :param uomconv: 换算关系列表
        :param basic: 基本视图
        :param mat_code: 物料编码
        :param mode: 运行模式 A-创建  B-更新
        :param external_number: 是否外部编号 1 外部给号 (创建的时候 basic mat_code 为空) 0 内部给号

        :return: None 引用赋值-参数引用操作不返回
    """
    _uomconv = []

    flag = True
    if mode == "A":
        for i in uomconv:
            if (mat_code == i["mat_code"] or not i["mat_code"]) and i["primary_uom"] == basic["basic_uom"] \
                    and i["secondary_uom"] == basic["basic_uom"]:
                # raise Exception("已存在 主单位基本换算关系=辅单位基本换算关系")
                flag = False
                break

        if flag:
            # 后添加
            _uomconv.append({
                "index": -1,
                "mat_code": mat_code,
                # 主单位
                "primary_uom": basic["basic_uom"],
                # 主单位数量
                "primary_uom_qty": 1,
                # 辅单位
                "secondary_uom": basic["basic_uom"],
                # 辅单位数量
                "secondary_uom_qty": 1,
                # =
                "equal": "=",
                # 备注
                "note": ""
            })
        TEST and usprint.printInfo(a,f"添加换算关系 uomconv : {uomconv}")
        TEST and usprint.printInfo(a,f"添加换算关系 _uomconv : {_uomconv}")
        # raise Exception("TEST")
    return _uomconv


inspection_types = []


# checkQualityInspec 数据格式校验函数
def verify(row):
    global inspection_types
    error = []
    for col, value in row.items():
        try:
            match col:
                # 校验类型
                case "inspection_type":
                    # 选填 阈值校验
                    if value:
                        if not inspection_types:
                            inspection_types = list(map(lambda x: x["inspection_type"], dh.query_sql(
                                """SELECT `inspection_type` FROM `t_inspection_type`""")))
                        if value not in inspection_types:
                            error.append(f"检验类型不存在")
                # 激活标志
                case "activation_flag":
                    if value and str(value) not in ["0", "1"]:
                        error.append(f"激活标志错误")
                # 备注说明
                case "note":
                    if len(value) > 255:
                        error.append(f"备注说明长度不能超过255位")
        except KeyError as e:
            traceback.print_exc()
            error.append(f"缺少{e}字段")
    return {"msg": "；".join(error), "view": "plant", "index": row["_key_"]}


# checkQualityInspec 数据唯一性校验函数
def unique(mat, plant, insert, update):
    subset = ["plant_code", "inspection_type", "mat_code"]
    database_data = []
    # 一层校验
    t = pd.DataFrame(insert + update)
    TEST and usprint.printInfo(a,t[["plant_code", "inspection_type", "mat_code"]])
    t = t[t.duplicated(subset=subset)]
    TEST and usprint.printInfo(a,t[["plant_code", "inspection_type", "mat_code"]])
    if not t.empty:
        return t
    # 二层数据库校验
    if (insert + update):
        # 有物料 可能创建新插入，也可能
        if mat:
            sql = f"""
                SELECT 
                    `id`,`mat_code`,`plant_code`,`inspection_type` 
                FROM  `t_mmd_material_quality_Inspection_data` 
                WHERE (`mat_code`,`plant_code`,`inspection_type`) in ({
            ','.join([
                f"('{i['mat_code']}','{i['plant_code']}','{i['inspection_type']}')"
                for i in insert + update
            ])
            })
            """
            database_data = DbHelper().query_sql(sql)
        # 物料后端生成一次校验通过（上传数据无冲突） 那么跟后端一定不冲突 直接返回空df对象
        else:
            return pd.DataFrame([])
    pd_datebase = pd.DataFrame(database_data)
    pd_update = pd.DataFrame(update)
    # 更新拼接
    pd_combin = pd.concat([pd_datebase, pd_update])
    # 这里有问题 当 update id 全相同时 会丢掉部分数据
    pd_combin = pd_combin.drop_duplicates(subset=["id"], keep="last")

    # 插入拼接
    pd_insert = pd.DataFrame(insert)
    pd_combin = pd.concat([pd_combin, pd_insert])
    # 校验 唯一键冲突保存冲突最后一条数据

    duplicated = pd_combin.duplicated(subset=subset, keep="last")
    TEST and usprint.printInfo(a,pd_combin)

    return pd_combin[duplicated]


# 工厂视图-保存质量检验校验
def checkQualityInspec(quality, error: list, mat_code="", plant_code=[]):
    delete, update, insert = [], [], []
    for data in quality:
        if data.get("_tag_") == "insert":
            insert.append(data)
        elif data.get("_tag_") == "update":
            update.append(data)
        elif data.get("_tag_") == "delete":
            delete.append(data)
    try:
        if (save := insert + update):
            # 获取工厂代码和物料代码
            plant_code = list(set(map(lambda x: x["plant_code"], save)))
            mat_code = save[0]["mat_code"]
            # if not mat_code:
            #     raise Exception("在校验质量校验表格数据时未传递物料")
            if not plant_code:
                raise Exception("在校验质量校验表格数据时未传递工厂代码")
        # 数据字段格式校验
        if save:
            # pandas行校验
            pd_data = pd.DataFrame(save)
            pd_data["error"] = pd_data.apply(lambda x: verify(x), axis=1)
            if not (result := pd_data[pd_data["error"].apply(lambda x: x["msg"] != "")]).empty:
                # 格式错误回传错误数据 错误信息在error中
                error.extend(result["error"].tolist())
            # 唯一性校验
            pd_unique = unique(mat_code, plant_code, insert, update)
            TEST and usprint.printInfo(a,type(pd_unique))
            TEST and usprint.printInfo("=======", pd_unique[["plant_code", "inspection_type", "mat_code"]])
            TEST and usprint.printInfo(a,not pd_unique.empty)
            if not pd_unique.empty:
                error.append({"msg": "质量检验表存在唯一键重复", "view": "plant", "index": 0})
    except KeyError as e:
        traceback.print_exc()
        error.append({"msg": f"缺少{e}字段", "view": "plant", "index": 0})
    return error


def checkBasicView(basic, error, mode):
    code = 0
    msg = ""

    # 判断物料类型是否属于外部给号
    code, msg, isExternal = isExternalNumber(basic["mat_type"])
    if code == 500:
        error.append({"msg": msg, "view": "basic", "index": basic.get("index", 0)})
    else:
        if isExternal != "":
            # 如果是外部编码,物料不能为空
            if basic["mat_code"] == "":
                error.append(
                    {"msg": "当前物料类型为外部编码,请输入物料", "view": "basic", "index": basic.get("index", 0)})
            else:
                # 物料存在性校验 新建就是A 批导存在B情况 （upload_type 为批导中的，mode是手工创建中的）
                if basic.get("upload_type", mode) == "A" and (querydata := dh.query_sql(
                        f"""SELECT `mat_code` FROM `t_mmd_material_basic_data` WHERE `mat_code` = '{basic['mat_code']}'""")):
                    error.append({"msg": "物料已存在", "view": "basic", "index": basic.get("index", 0)})
    # 制程阈值校验
    if (process_code := basic.get("process_code", "")):
        t = dh.query_sql(f"SELECT 1 FROM `t_process` WHERE `process_code` = '{process_code}' LIMIT 1")
        if not t:
            error.append({"msg": "制程不存在", "view": "basic", "index": basic.get("index", 0)})

    if basic.get("mat_description", "") == "":
        error.append({"msg": "物料描述必输", "view": "basic", "index": basic.get("index", 0)})

    if basic.get("mat_type", "") == "":
        error.append({"msg": "物料类型必输", "view": "basic", "index": basic.get("index", 0)})

    if basic.get("mat_group", "") == "":
        error.append({"msg": "物料组必输", "view": "basic", "index": basic.get("index", 0)})

    if basic.get("basic_uom", "") == "":
        error.append({"msg": "基本单位必输", "view": "basic", "index": basic.get("index", 0)})
    else:
        # 基本单位校验
        code, msg = checkUom(basic["basic_uom"], "基本信息中基本单位")
        if code == 500:
            error.append({"msg": msg, "view": "basic", "index": basic.get("index", 0)})

    # 平行单位标记校验
    if basic.get("parallel_uom_mark", 0) == 1:
        code, msg = checkParallelUomMark(basic["mat_type"])
        if code == 500:
            error.append({"msg": msg, "view": "basic", "index": basic.get("index", 0)})

    # 平行单位校验
    if basic.get("parallel_uom", "") != "":
        if basic.get("parallel_uom_mark", 0) == 0:
            error.append(
                {"msg": "平行单位标记未勾选,禁止输入平行单位", "view": "basic", "index": basic.get("index", 0)})
        else:
            code, msg = checkUom(basic["parallel_uom"], "基本信息中平行单位")
            if code == 500:
                error.append({"msg": msg, "view": "basic", "index": basic.get("index", 0)})
            else:
                if basic["parallel_uom"] == basic["basic_uom"]:
                    error.append({"msg": "平行单位不能等于基本单位", "view": "basic", "index": basic.get("index", 0)})
    else:
        if basic.get("parallel_uom_mark", 0) == 1:
            error.append({"msg": "基本信息中平行单位必填", "view": "basic", "index": basic.get("index", 0)})

    # 物料组校验
    if basic.get("mat_group", "") != "":
        code, msg = checkMatGroup(basic["mat_type"], basic["mat_group"])
        if code == 500:
            error.append({"msg": msg, "view": "basic", "index": basic.get("index", 0)})

    # 二级物料组校验
    if basic.get("mat_group_2", "") != "":
        code, msg = checkMatGroup2(basic["mat_group_2"])
        if code == 500:
            error.append({"msg": msg, "view": "basic", "index": basic.get("index", 0)})

    # 产品组校验
    if basic.get("prod_group", "") != "":
        code, msg = checkProdGroup(basic["prod_group"])
        if code == 500:
            error.append({"msg": msg, "view": "basic", "index": basic.get("index", 0)})

    # 二级产品组校验
    if basic.get("prod_group_2", "") != "":
        code, msg = checkProdGroup2(basic["prod_group_2"])
        if code == 500:
            error.append({"msg": msg, "view": "basic", "index": basic.get("index", 0)})

    # 外部编码校验 2025年11月26日 取消外部编码阈值校验
    # if False and basic.get("external_mat_code", "") != "":
    #     code, msg = checkMaterial(basic["external_mat_code"], "基本信息中外部编码")
    #     if code == 500:
    #         error.append({"msg": msg, "view": "basic", "index": basic.get("index",0)})

    # 重量单位校验
    if basic.get("weight_uom", "") != "":
        code, msg = checkUom(basic["weight_uom"], "基本信息中重量单位")
        if code == 500:
            error.append({"msg": msg, "view": "basic", "index": basic.get("index", 0)})

    # 体积单位校验
    if basic.get("volume_uom", "") != "":
        code, msg = checkUom(basic["volume_uom"], "基本信息中体积单位")
        if code == 500:
            error.append({"msg": msg, "view": "basic", "index": basic.get("index", 0)})

    # 启用保质期管理 保质期天数必输
    if basic.get('shelf_life_enabled', 0) == 1 and basic.get('shelf_life_days', 0) == 0:
        code = 500
        msg = '启用保质期管理保质期天数必输'
        error.append({"msg": msg, "view": "plant", "index": basic.get("index", 0)})
    return error


def checkFieldDetail(detail, error):
    code = 0
    msg = ""
    for index, each in enumerate(detail):
        try:
            # 判断重复
            index2 = 0
            for each2 in detail:
                if index == index2:
                    continue
                if each['mat_code'] == each2['mat_code'] and each['property_group'] == each2['property_group'] and each[
                    'field_code'] == each2['field_code']:
                    msg = each["field_name"] + "存在重复数据"
                    error.append({"msg": msg, "view": "detail", "index": each.get("index", index)})
                index2 += 1

            type = each["field_type"]
            length = each["field_length"]
            # decimal = each["decimal"]
            value = str(each.get("field_value", ""))

            if value != "":
                if type == "int" or type == "decimal":
                    v = str(value).replace(".", "")
                    if not v.isdigit():
                        if type == "int":
                            msg = each["field_name"] + "应为整数"
                        else:
                            msg = each["field_name"] + "应为小数"
                        error.append({"msg": msg, "view": "detail", "index": each.get("index", index)})
                if type == "date":
                    if not is_date(value):
                        msg = each["field_name"] + "应为日期格式YYYY-MM-DD"
                        error.append({"msg": msg, "view": "detail", "index": each.get("index", index)})
                if "." in value:
                    if len(value.split(".")[0]) + len(value.split(".")[1]) > int(length):
                        msg = each["field_name"] + "长度超过" + str(length)
                        error.append({"msg": msg, "view": "detail", "index": each.get("index", index)})
                    # if len(value.split(".")[1]) > int(decimal):
                    #   msg = each["field_name"] + "小数点长度超过" + str(decimal)
                    #   error.append({"msg":msg})
                else:
                    # if len(value) > int(length) - int(decimal):
                    if len(value) > int(length):
                        msg = each["field_name"] + "长度超过" + str(length)
                        error.append({"msg": msg, "view": "detail", "index": each.get("index", index)})
            else:
                if type == "int" or type == "decimal":
                    each['field_value'] = 0

            value = str(each.get("field_value_from", ""))

            if value != "":
                if type == "int" or type == "decimal":
                    v = value.replace(".", "")
                    if not v.isdigit():
                        if type == "int":
                            msg = each["field_name"] + "应为整数"
                        else:
                            msg = each["field_name"] + "应为小数"
                        error.append({"msg": msg, "view": "detail", "index": each.get("index", index)})
                if type == "date":
                    if not is_date(value):
                        msg = each["field_name"] + "应为日期格式YYYY-MM-DD"
                        error.append({"msg": msg, "view": "detail", "index": each.get("index", index)})
                if "." in value:
                    if len(value.split(".")[0]) + len(value.split(".")[1]) > int(length):
                        msg = each["field_name"] + "长度超过" + str(length)
                        error.append({"msg": msg, "view": "detail", "index": each.get("index", index)})
                    # if len(value.split(".")[1]) > int(decimal):
                    #   msg = each["field_name"] + "小数点长度超过" + str(decimal)
                    #   error.append({"msg":msg})
                else:
                    # if len(value) > int(length) - int(decimal):
                    if len(value) > int(length):
                        msg = each["field_name"] + "长度超过" + str(length)
                        error.append({"msg": msg, "view": "detail", "index": each.get("index", index)})
            else:
                if type == "int" or type == "decimal":
                    each['field_value_from'] = 0

            value = str(each.get("field_value_to", ""))

            if value != "":
                if type == "int" or type == "decimal":
                    v = value.replace(".", "")
                    if not v.isdigit():
                        if type == "int":
                            msg = each["field_name"] + "应为整数"
                        else:
                            msg = each["field_name"] + "应为小数"
                        error.append({"msg": msg, "view": "detail", "index": each.get("index", index)})
                if type == "date":
                    if not is_date(value):
                        msg = each["field_name"] + "应为日期格式YYYY-MM-DD"
                        error.append({"msg": msg, "view": "detail", "index": each.get("index", index)})
                if "." in value:
                    if len(value.split(".")[0]) + len(value.split(".")[1]) > int(length):
                        msg = each["field_name"] + "长度超过" + str(length)
                        error.append({"msg": msg, "view": "detail", "index": each.get("index", index)})
                    # if len(value.split(".")[1]) > int(decimal):
                    #   msg = each["field_name"] + "小数点长度超过" + str(decimal)
                    #   error.append({"msg":msg})
                else:
                    # if len(value) > int(length) - int(decimal):
                    if len(value) > int(length):
                        msg = each["field_name"] + "长度超过" + str(length)
                        error.append({"msg": msg, "view": "detail", "index": each.get("index", index)})
            else:
                if type == "int" or type == "decimal":
                    each['field_value_to'] = 0

        except KeyError as e:
            traceback.print_exc()
            error.append({"msg": f"缺少{e}字段", "view": "detail", "index": each.get("index", index)})

    return error


def checkPlantView(plant, error, basic_uom, uom, **kwargs):
    code = 0
    msg = ""
    basic = kwargs.get("basic", {})
    # mode = kwargs.get("mode")
    for index, each in enumerate(plant):
        try:
            # 工厂校验
            code, msg = checkPlantCode(each["plant_code"])
            if code == 500:
                error.append({"msg": msg, "view": "plant", "index": each.get("index", index)})

            # # 批导扩充校验
            # if mode == "B":
            #     # 物料加工厂一定不存在，物料一定存在基本视图中
            #     if not dh.query_sql(f"""SELECT mat_code FROM t_mmd_material_basic_data WHERE mat_code = '{each['mat_code']}' limit 1""") :
            #         error.append({"msg": "扩充物料不存在", "view": "plant", "index": each.get("index",index)})
            #     elif dh.query_sql(f""" SELECT plant_code FROM t_mmd_material_plant_data WHERE plant_code = '{each['plant_code']}' AND mat_code = '{each['mat_code']}' limit 1 """):
            #         error.append({"msg": "扩充工厂已存在", "view": "plant", "index": each.get("index",index)})
            # 批次颗粒度单位
            if each.get("granularity_uom", "") != "":
                if each.get("batch_mark", 0) == 0:
                    error.append({"msg": "未启用批次管理不允许填写批次颗粒度单位", "view": "plant",
                                  "index": each.get("index", index)})
                else:
                    if each.get("granularity_uom", None) != basic_uom:
                        error.append(
                            {"msg": "批次颗粒度单位不等于基本单位", "view": "plant", "index": each.get("index", index)})
            # else:
            #     if each.get("batch_mark", 0) == 1:
            #         error.append({"msg": "已启用批次管理,批次颗粒度单位必输", "view": "plant", "index": each.get("index",index)})

            # 采购类型校验 pur_type
            # 拿着 基本视图的 mat_type 物料类型  + 工厂代码 查表 t_mmd_material_type_range_limit  value_update 价值更新标识 = 0 则pur_type为 F
            mat_type = basic.get("mat_type", "")
            plant_code = each.get("plant_code", "")
            sql = f"""
                SELECT `value_update` 
                FROM `t_mmd_material_type_range_limit` 
                WHERE `mat_type` = '{mat_type}' AND `plant_code` = '{plant_code}' 
            """
            _data = dh.query_sql(sql)
            if not _data:
                error.append({"msg": "该工厂未启用价值更新", "view": "plant", "index": each.get("index", index)})
            elif (str(_data[0]["value_update"]) == "0" and each.get("pur_type", "") != "F"):
                error.append(
                    {"msg": "价值更新标识配置为0时，采购类型应为F", "view": "plant", "index": each.get("index", index)})

            # 采购组校验
            # if each.get("pur_group", "") == "":
            #     error.append({"msg": "采购组必输", "view": "plant", "index": each.get("index",index)})
            if each.get("pur_group", "") != "":
                code, msg = checkPurGroup(each["pur_group"])
                if code == 500:
                    error.append({"msg": msg, "view": "plant", "index": each.get("index", index)})

            # 采购单位校验
            if each.get("pur_uom", "") != "":
                code, msg = checkUom(each["pur_uom"], "工厂数据中采购单位")
                if code == 500:
                    error.append({"msg": msg, "view": "plant", "index": each.get("index", index)})
                else:
                    uom.append((each["pur_uom"], each.get("index", index), "basic"))

            # 第二采购单位校验
            if each.get("pur_uom_2", "") != "":
                code, msg = checkUom(each["pur_uom_2"], "工厂数据中第二采购单位")
                if code == 500:
                    error.append({"msg": msg, "view": "plant", "index": each.get("index", index)})
                else:
                    uom.append((each["pur_uom_2"], each.get("index", index), "basic"))

            # 生产单位校验
            if each.get("prod_uom", "") != "":
                code, msg = checkUom(each["prod_uom"], "工厂数据中生产单位")
                if code == 500:
                    error.append({"msg": msg, "view": "plant", "index": each.get("index", index)})
                else:
                    uom.append((each["prod_uom"], each.get("index", index), "basic"))

            # 计划校验
            if each.get("plan_group", ""):
                code, msg = checkPlanGroup(each["plan_group"])
                if code == 500:
                    error.append({"msg": msg, "view": "plant", "index": each.get("index", index)})

            # 批量大小类型校验
            if each.get("lot_size", ""):
                code, msg = checkLotType(each["lot_size"])
                if code == 500:
                    error.append({"msg": msg, "view": "plant", "index": each.get("index", index)})

            # 批量单位校验
            if each.get("lot_uom", "") != "":
                code, msg = checkUom(each["lot_uom"], "工厂数据中批量单位")
                if code == 500:
                    error.append({"msg": msg, "view": "plant", "index": each.get("index", index)})
                else:
                    uom.append((each["lot_uom"], each.get("index", index), "basic"))

            # 收货库存地点校验
            if each.get("stor_loc_code", "") != "":
                code, msg = checkStorLocCode(each["plant_code"], each["stor_loc_code"], "工厂数据中收货库存地点")
                if code == 500:
                    error.append({"msg": msg, "view": "plant", "index": each.get("index", index)})

            # 发料库存地点校验
            if each.get("stor_loc_code2", "") != "":
                code, msg = checkStorLocCode(each["plant_code"], each["stor_loc_code2"], "工厂数据中发料库存地点")
                if code == 500:
                    error.append({"msg": msg, "view": "plant", "index": each.get("index", index)})

            # 安全库存类型校验
            if each.get("safety_type", "") != "":
                code, msg = checkSafetyType(each["safety_type"])
                if code == 500:
                    error.append({"msg": msg, "view": "plant", "index": each.get("index", index)})

            # 指定供应商校验
            if each.get("fixed_vendor", "") != "":
                code, msg = checkFixedVendor(each["fixed_vendor"])
                if code == 500:
                    error.append({"msg": msg, "view": "plant", "index": each.get("index", index)})

        except KeyError as e:
            traceback.print_exc()
            error.append({"msg": f"缺少{e}字段", "view": "plant", "index": each.get("index", index)})

    return error, uom


def checkFinancialView(financial, error, **kwargs):
    code = 0
    msg = ""
    # mode = kwargs.get("mode")
    control = kwargs.get("control", [])
    
    # 检查利润中心是否在屏幕控制中显示
    profit_center_display = False
    for ctrl in control:
        if ctrl.get("field_name") == "profit_center":
            # display=1 且 hide=0 时才显示
            if ctrl.get("display") == 1 and ctrl.get("hide") == 0:
                profit_center_display = True
            break
    
    for index, each in enumerate(financial):
        try:
            # 工厂校验
            code, msg = checkPlantCode(each["plant_code"])
            if code == 500:
                error.append({"msg": msg, "view": "finance", "index": each.get("index", index)})

            # # 批导扩充校验
            # if mode == "B":
            #     # 物料加工厂一定不存在，物料一定存在基本视图中
            #     if not dh.query_sql(f"""SELECT mat_code FROM t_mmd_material_basic_data WHERE mat_code = '{each['mat_code']}' limit 1""") :
            #         error.append({"msg": "扩充物料不存在", "view": "finance", "index": each.get("index",index)})
            #     elif dh.query_sql(f""" SELECT plant_code FROM t_mmd_material_financial_data WHERE plant_code = '{each['plant_code']}' AND mat_code = '{each['mat_code']}' limit 1 """):
            #         error.append({"msg": "扩充工厂已存在", "view": "finance", "index": each.get("index",index)})

            if each.get("plant_val_class", "") == "":
                error.append({"msg": "评估类必输", "view": "finance", "index": each.get("index", index)})

            # 物料销售税码校验
            if each.get("mat_sales_tax_code", "") != "":
                code, msg = checkMatSalesTaxCode(each["mat_sales_tax_code"])
                if code == 500:
                    error.append({"msg": msg, "view": "finance", "index": each.get("index", index)})
            
            
            # 利润中心校验 - 根据屏幕控制判断是否必填
            if profit_center_display:
                # 屏幕显示利润中心输入框，则必填
                if each.get("profit_center", "") != "":
                    code, msg = checkProfitCenter(each["plant_code"], each["profit_center"])
                    if code == 500:
                        error.append({"msg": msg, "view": "finance", "index": each.get("index", index)})
                else:
                    error.append({"msg": "未填写利润中心", "view": "finance", "index": each.get("index", index)})
            else:
                # 屏幕不显示利润中心输入框，则允许为空，但如果填了需要校验合法性
                if each.get("profit_center", "") != "":
                    code, msg = checkProfitCenter(each["plant_code"], each["profit_center"])
                    if code == 500:
                        error.append({"msg": msg, "view": "finance", "index": each.get("index", index)})
        except KeyError as e:
            traceback.print_exc()
            error.append({"msg": f"缺少{e}字段", "view": "finance", "index": each.get("index", index)})

    return error


def checkCostView(cost, error, basic_uom, parallel_uom, uom, **kwargs):
    code = 0
    msg = ""

    # mode = kwargs.get("mode")
    # 价格控制模式 按公司保持一致 ： 通过工厂找公司 公司下面所有工厂统一。公司新建数据不要求（根据第一条数据进行保存），扩建数据要跟第一条数据保持一致
    # 工厂下的价格控制模式
    plant_to_pCtrl = {}
    # 工厂对应公司
    try:
        plant_to_company = {
            str(i["plant_code"]): str(i["company_code"])
            for i in dh.query_sql(f"""SELECT DISTINCT `company_code`,`plant_code` FROM `t_os_company_plant_alloc`;""")
        }
    except KeyError as e:
        error.append({"msg": f"缺少{e}字段", "view": "cost", "index": 0})
    for index, each in enumerate(cost):
        try:
            # 工厂校验
            code, msg = checkPlantCode(each["plant_code"])
            if code == 500:
                error.append({"msg": msg, "view": "cost", "index": each.get("index", index)})

            # # 批导扩充校验
            # if mode == "B":
            #     # 物料加工厂一定不存在，物料一定存在基本视图中
            #     if not dh.query_sql(f"""SELECT mat_code FROM t_mmd_material_basic_data WHERE mat_code = '{each['mat_code']}' limit 1""") :
            #         error.append({"msg": "扩充物料不存在", "view": "cost", "index": each.get("index",index)})
            #     elif dh.query_sql(f""" SELECT plant_code FROM t_mmd_material_cost_data WHERE plant_code = '{each['plant_code']}' AND mat_code = '{each['mat_code']}' limit 1 """):
            #         error.append({"msg": "扩充工厂已存在", "view": "cost", "index": each.get("index",index)})

            # 获取控制模式 按公司保持一致
            company = ""
            # 最终的key 为公司 + 物料 (key+物料多余了)  因为同一个基本视图下的校验物料一致
            if code == 200 and (company := plant_to_company.get(each["plant_code"], "")) and not plant_to_pCtrl.get(
                    company + each["mat_code"], ""):
                # 查询价格模式
                data = dh.query_sql(f"""
                                WITH `plants_company` AS (
                                    SELECT 
                                        `tmmcd`.`price_control`,
                                        `tmmcd`.`mat_code`,
                                        `tmmcd`.`plant_code`,
                                        `tocpa`.`company_code`  
                                    FROM `t_mmd_material_cost_data` `tmmcd`
                                    LEFT JOIN `t_os_company_plant_alloc` `tocpa` ON `tocpa`.`plant_code` = `tmmcd`.`plant_code`
                                ),`company_codes` AS (
                                    SELECT 
                                        `company_code` 
                                    FROM `t_os_company_plant_alloc` 
                                    WHERE `plant_code` = '{each["plant_code"]}'
                                )
                                SELECT 
                                    `price_control`,`mat_code`,`plant_code`,`company_code` 
                                FROM `plants_company`
                                WHERE `mat_code` = '{each["mat_code"]}'
                                      AND `company_code` IN (SELECT `company_code` FROM `company_codes`) limit 1
                            """)
                # # 已经存在按照存在的第一条价格控制模式来做参照
                # if data:
                #     # 查询到该公司的该物料价格控制模式
                #     plant_to_pCtrl[data[0]["company_code"]+each["mat_code"]] = data[0]["price_control"]
                # else:
                #     # 没有找到该公司的该物料价格控制模式
                #     plant_to_pCtrl[company+each["mat_code"]] = each["price_control"]
                plant_to_pCtrl[company + each["mat_code"]] = data
            # 校验价格控制模式
            # if (company := plant_to_company.get(each["plant_code"],"")):
            if not each["price_control"]:
                error.append({"msg": "价格控制模式必填", "view": "cost", "index": each.get("index", index)})
            # 上边计算出来的公司存在
            elif company and len(plant_to_pCtrl[company + each["mat_code"]]) > 1:
                perv = plant_to_pCtrl[company + each["mat_code"]][0]["price_control"]
                if each["price_control"] != perv:
                    error.append({"msg": "价格控制模式不一致", "view": "cost", "index": each.get("index", index)})

            if (cost_lot := str(each.get("cost_lot", 0))):
                try:
                    if not bool(re.match(r'^[0-9]+(\.0+)?$', cost_lot)) or float(cost_lot) <= 0:
                        error.append({"msg": "成本核算批量数量必须为整数且大于0", "view": "cost",
                                      "index": each.get("index", index)})
                except Exception as e:
                    traceback.print_exc()
                    error.append(
                        {"msg": "成本核算批量数量必须为整数且大于0", "view": "cost", "index": each.get("index", index)})
            else:
                error.append({"msg": "成本核算批量数量必填", "view": "cost", "index": each.get("index", index)})

            if (price_unit := str(each.get("price_unit", 0))):
                try:
                    if not bool(re.match(r'^[0-9]+(\.0+)?$', price_unit)) or float(price_unit) <= 0:
                        error.append(
                            {"msg": "价格批量必须为整数且大于0", "view": "cost", "index": each.get("index", index)})
                except Exception as e:
                    traceback.print_exc()
                    error.append(
                        {"msg": "价格批量必须为整数且大于0", "view": "cost", "index": each.get("index", index)})
            else:
                error.append({"msg": "价格批量必填", "view": "cost", "index": each.get("index", index)})

            try:
                if float(cost_lot) < float(price_unit):
                    error.append({"msg": "成本核算批量数量必须大于等于价格批量", "view": "cost",
                                  "index": each.get("index", index)})
            except Exception as e:
                traceback.print_exc()
                error.append({"msg": "价格批量必须大于等于成本核算批量数量，且两字段均为大于0整数", "view": "cost",
                              "index": each.get("index", index)})
            if not error:
                each["cost_lot"] = int(float(cost_lot))
                each["price_unit"] = int(float(price_unit))

            if each.get("plant_val_mark", 0) == 0:
                error.append({"msg": "工厂物料评估标识必填", "view": "cost", "index": each.get("index", index)})

            # if each.get("plan_cost_currency", "") == "":
            #     error.append({"msg": "计划价格币种必填", "view": "cost", "index": each.get("index",index)})
            if len(str(each.get("plan_cost_currency", ""))) > 3:
                error.append({"msg": "计划价格币种长度不能超过3位", "view": "cost", "index": each.get("index", index)})

            # if plan_cost_bc is None:
            #     error.append({"msg": "计划价格必填", "view": "cost", "index": each.get("index",index)})
            # else:
            plan_cost_bc = each.get("plan_cost_bc", None)
            if plan_cost_bc:
                try:
                    plan_cost_bc = float(plan_cost_bc)
                    if plan_cost_bc < 0:
                        error.append(
                            {"msg": "计划价格必须大于等于0", "view": "cost", "index": each.get("index", index)})
                except ValueError:
                    traceback.print_exc()
                    error.append({"msg": "计划价格必须为数字", "view": "cost", "index": each.get("index", index)})
            # 成本计量单位校验
            if each.get("cost_uom", "") != "":
                code, msg = checkUom(each["cost_uom"], "成本数据中成本计量单位")
                if code == 500:
                    error.append({"msg": msg, "view": "cost", "index": each.get("index", index)})
                else:
                    if each["cost_uom"] != basic_uom and each["cost_uom"] != parallel_uom:
                        error.append({"msg": "成本单位不等于基本单位或平行单位", "view": "cost",
                                      "index": each.get("index", index)})
                    else:
                        uom.append((each["cost_uom"], each.get("index", index), "basic"))
            else:
                error.append({"msg": "成本单位必填", "view": "cost", "index": each.get("index", index)})

            # 组评估物料校验
            if each.get("valgroup_value", "") != "":
                code, msg = checkMaterial(each["valgroup_value"], "成本数据中组评估物料")
                if code == 500:
                    error.append({"msg": msg, "view": "cost", "index": each.get("index", index)})
                else:
                    code, msg = checkAllMaterialUnit(each["valgroup_value"], each["plant_code"], each["cost_uom"],
                                                     basic_uom)
                    if code == 500:
                        error.append({"msg": msg, "view": "cost", "index": each.get("index", index)})
            # 物料成本分类校验
            if each.get("mat_cost_classify", "") != "":
                code, msg = checkMatCostClassify(each["plant_code"], each["mat_cost_classify"])
                if code == 500:
                    error.append({"msg": msg, "view": "cost", "index": each.get("index", index)})

            # 成本管理组织货币校验
            code, msg, each["co_currency"] = checkCoCurrency(each["plant_code"])
            if code == 500:
                error.append({"msg": msg, "view": "cost", "index": each.get("index", index)})

            # 本位币校验
            code, msg, each["basic_currency"] = checkCurrency(each["plant_code"])
            if code == 500:
                error.append({"msg": msg, "view": "cost", "index": each.get("index", index)})
            # WBS元素校验
            if each.get("wbs_elements", "") != "":
                code, msg = checkWBSelement(each["wbs_elements"], each["plant_code"])
                if code == 500:
                    error.append({"msg": msg, "view": "cost", "index": each.get("index", index)})
        except KeyError as e:
            traceback.print_exc()
            error.append({"msg": f"缺少{e}字段", "view": "cost", "index": each.get("index", index)})
        except ValueError as e:
            traceback.print_exc()
            error.append({"msg": f"字段值类型错误{e}", "view": "cost", "index": each.get("index", index)})

    return error, cost, uom


def checkSalesView(sales, error, uom, **kwargs):
    code = 0
    msg = ""
    # mode = kwargs.get("mode")
    for index, each in enumerate(sales):
        try:
            # 销售组织校验
            code, msg = checkSalesCode(each["sales_org_code"])
            if code == 500:
                error.append({"msg": msg, "view": "sales", "index": each.get("index", index)})

            # # 销售组织扩充校验
            # if mode == "B":
            #     # 物料加工厂一定不存在，物料一定存在基本视图中
            #     if not dh.query_sql(f"""SELECT mat_code FROM t_mmd_material_basic_data WHERE mat_code = '{each['mat_code']}' limit 1""") :
            #         error.append({"msg": "扩充物料不存在", "view": "sales", "index": each.get("index",index)})
            #     elif dh.query_sql(f""" SELECT sales_org_code FROM t_mmd_material_sales_data WHERE sales_org_code = '{each['sales_org_code']}' AND mat_code = '{each['mat_code']}' limit 1 """):
            #         error.append({"msg": "扩充销售组织已存在", "view": "sales", "index": each.get("index",index)})

            # 默认交货工厂校验
            if each.get("default_plant", "") != "":
                code, msg = checkPlantCode(each["default_plant"])
                if code == 500:
                    error.append(
                        {"msg": "销售数据中默认交货工厂不存在", "view": "sales", "index": each.get("index", index)})
            else:
                error.append({"msg": "默认交货工厂必填", "view": "sales", "index": each.get("index", index)})

            # 销售单位校验
            if each.get("sales_uom", "") != "":
                code, msg = checkUom(each["sales_uom"], "销售数据中销售单位")
                if code == 500:
                    error.append({"msg": msg, "view": "sales", "index": each.get("index", index)})
                else:
                    uom.append((each["sales_uom"], each.get("index", index), "basic"))

            # 第二销售单位校验
            if each.get("sales_uom_2", "") != "":
                code, msg = checkUom(each["sales_uom_2"], "销售数据中第二销售单位")
                if code == 500:
                    error.append({"msg": msg, "view": "sales", "index": each.get("index", index)})
                else:
                    uom.append((each["sales_uom_2"], each.get("index", index), "basic"))

            # 项目类别组校验
            if each.get("item_category_group", "") != "":
                code, msg = checkItemCatGroup(each["item_category_group"])
                if code == 500:
                    error.append({"msg": msg, "view": "sales", "index": each.get("index", index)})
            else:
                error.append({"msg": "项目类别组必填", "view": "sales", "index": each.get("index", index)})
        except KeyError as e:
            traceback.print_exc()
            error.append({"msg": f"缺少{e}字段", "view": "sales", "index": each.get("index", index)})

    return error, uom


def checkUomConv(uomconv, error, basic, uom, mode):
    code = 0
    msg = ""
    basic_uom = basic["basic_uom"]
    parallel_uom = basic["parallel_uom"]
    sql = f"""
        SELECT 
            `mat_code`,`primary_uom` ,
            `secondary_uom`,`primary_uom_qty`, 
            `secondary_uom_qty`  
        FROM  `t_mmd_uom_conversion`
        WHERE `mat_code` = '{basic.get("mat_code", "")}'
    """
    # 扩展模式 未传 uomconv 则在库中取
    if mode == "B" and not uomconv:
        uomconv = dh.query_sql(sql)
    for index, each in enumerate(uomconv):
        try:
            # 主单位校验
            if each.get("primary_uom", "") != "":
                code, msg = checkUom(each["primary_uom"], "换算单位中主单位")
                if code == 500:
                    error.append({"msg": msg, "view": "uomconv", "index": each.get("index", index)})
            else:
                error.append({"msg": "主单位必填", "view": "uomconv", "index": each.get("index", index)})

            # 辅单位校验
            if each.get("secondary_uom", "") != "":
                code, msg = checkUom(each["secondary_uom"], "换算单位中辅单位")
                if code == 500:
                    error.append({"msg": msg, "view": "uomconv", "index": each.get("index", index)})
            else:
                error.append({"msg": "辅单位必填", "view": "uomconv", "index": each.get("index", index)})

            if each.get("primary_uom_qty", 0) == 0:
                error.append({"msg": "主单位数量必填", "view": "uomconv", "index": each.get("index", index)})

            if each.get("secondary_uom_qty", 0) == 0:
                error.append({"msg": "辅单位数量必填", "view": "uomconv", "index": each.get("index", index)})
        except KeyError as e:
            traceback.print_exc()
            error.append({"msg": f"缺少{e}字段", "view": "uomconv", "index": each.get("index", index)})

    # 判断基本单位和平行单位是否存在换算关系
    if parallel_uom != "" and basic_uom != parallel_uom:
        exist = 0
        for index, each in enumerate(uomconv):
            try:
                if ((each["primary_uom"] == basic_uom and each["secondary_uom"] == parallel_uom)
                        or (each["secondary_uom"] == basic_uom and each["primary_uom"] == parallel_uom)):
                    exist = 1
            except KeyError as e:
                traceback.print_exc()
                error.append({"msg": f"缺少{e}字段", "view": "uomconv", "index": each.get("index", index)})
        if exist == 0:
            error.append(
                {"msg": "基本单位{}和平行单位{}未维护换算关系".format(basic_uom, parallel_uom), "view": "basic",
                 "index": 0})

    uom = list(set(uom))

    for unit, index, view in uom:
        if unit != basic_uom and unit != parallel_uom:
            exist = 0
            for index, each in enumerate(uomconv):
                try:
                    if (((each["primary_uom"] == basic_uom or each["primary_uom"] == parallel_uom) and each[
                        "secondary_uom"] == unit)
                            or ((each["secondary_uom"] == basic_uom or each["secondary_uom"] == parallel_uom) and each[
                                "primary_uom"] == unit)):
                        exist = 1
                except KeyError as e:
                    traceback.print_exc()
                    error.append({"msg": f"缺少{e}字段", "view": "uomconv", "index": each.get("index", index)})
            if exist == 0:
                # if parallel_uom == "":
                #     error.append({"msg": "基本单位{}和单位{}未维护换算关系".format(basic_uom, unit), "view": view, "index": index})
                # else:
                #     error.append({"msg": "基本单位{}或平行单位{}和单位{}未维护换算关系".format(basic_uom, parallel_uom, unit), "view": view, "index": index})
                error.append(
                    {"msg": "基本单位{}和单位{}未维护换算关系".format(basic_uom, unit), "view": view, "index": index})
    return error


def date_judge(v):
    time_pattern = r'^\d{2}:\d{2}:\d{2}$'
    if re.match(time_pattern, v):
        try:
            datetime.strptime(v, '%H:%M:%S')  # 尝试将字符串转换为时间对象
            return True
        except ValueError:
            return False
    date_pattern = r'^\d{4}-\d{2}-\d{2}$'
    if re.match(date_pattern, v):
        try:
            datetime.strptime(v, '%Y-%m-%d')  # 尝试将字符串转换为日期对象
            return True
        except ValueError:
            return False
    return False


# 获取默认值的SQL
def get_default_data(type_, value):
    match type_:
        case "int" | "decimal":
            if not value:
                return 0
        case "time" | "date":
            if not value or not date_judge(value):
                return "NULL"
    return value


def saveAllData(mode, user_id, basic, plant, financial, cost, sales, uomconv, memo, detail, quality, **kwargs):
    basic_values = ""
    plant_values = ""
    financial_values = ""
    cost_values = ""
    sales_values = ""
    uomconv_values = ""
    detail_values = ""

    basic_data = []
    plant_data = []
    financial_data = []
    cost_data = []
    sales_data = []
    uomconv_data = []
    detail_data = []

    mat_code = ""

    if mode == "A":
        ret = generate_serial_num("mmd_material_type", basic["mat_type"], dh)
        if ret["external_number"] != 1:
            mat_code = ret["serial_num"]
        else:
            mat_code = basic["mat_code"]
    else:
        mat_code = basic["mat_code"]
    # 添加换算关系
    _uomconv = add_uom_conv(uomconv, basic, mat_code, mode)

    basic_line = {
        'mat_code': mat_code,
        'mat_description': basic['mat_description'],
        'mat_type': basic['mat_type'],
        'basic_uom': basic['basic_uom'],
        'parallel_uom': basic.get('parallel_uom', ''),
        'parallel_uom_mark': basic.get('parallel_uom_mark', 0),
        'mat_group': basic.get('mat_group', ''),
        'mat_group_2': basic.get('mat_group_2', ''),
        'old_mat_code': basic.get('old_mat_code', ''),
        'old_description': basic.get('old_description', ''),
        'prod_group': basic.get('prod_group', ''),
        'mat_status': basic.get('mat_status', ''),
        'deleted_mark': basic.get('deleted_mark', 0),
        'lock_flag': basic.get('lock_flag', 0),
        'external_mat_code': basic.get('external_mat_code', ''),
        'net_weight': basic.get('net_weight', 0),
        'gross_weight': basic.get('gross_weight', 0),
        'weight_uom': basic.get('weight_uom', ''),
        'volume': basic.get('volume', 0),
        'volume_uom': basic.get('volume_uom', ''),
        'priority_code': basic.get('priority_code', ''),
        'capacity_dimension': basic.get('capacity_dimension', ''),
        'process_code': basic.get('process_code', ''),
        'remarks': basic.get('remarks', ''),
        'shelf_life_enabled': basic.get('shelf_life_enabled', 0),
        'shelf_life_days': basic.get('shelf_life_days', 0),
        'create_id': basic.get('create_id', user_id),
        'update_id': user_id
    }
    basic_data = []
    basic_data.append(basic_line)

    for item in plant:
        if basic["mat_code"] == item["mat_code"]:
            plant_line = {
                'mat_code': mat_code,
                'plant_code': item['plant_code'],
                'batch_mark': item.get('batch_mark', 0),
                'granularity_uom': item.get('granularity_uom', ''),
                'pur_group': item.get('pur_group', ''),
                'pur_uom': item.get('pur_uom', ''),
                'pur_uom_2': item.get('pur_uom_2', ''),
                'prod_uom': item.get('prod_uom', ''),
                'source_mark': item.get('source_mark', 0),
                'plan_group': item.get('plan_group', ''),
                'sub_group': item.get('sub_group', ''),
                'lot_size': item.get('lot_size', ''),
                'lot_uom': item.get('lot_uom', ''),
                'stor_loc_code': item.get('stor_loc_code', ''),
                'stor_loc_code2': item.get('stor_loc_code2', ''),
                'max_lot': item.get('max_lot', 0),
                'min_lot': item.get('min_lot', 0),
                'mpq': item.get('mpq', 0),
                'safety_type': item.get('safety_type', ''),
                'safety_stock_quantity': item.get('safety_stock_quantity', 0),
                'reorder_point': item.get('reorder_point', 0),
                'pur_type': item.get('pur_type', ''),
                'dely_period': item.get('dely_period', 0),
                'prod_period': item.get('prod_period', 0),
                'trans_period': item.get('trans_period', 0),
                'insp_period': item.get('insp_period', 0),
                'waiting_time': item.get('waiting_time', 0),
                'assembly_loss_rate': item.get('assembly_loss_rate', 0),
                'yield': item.get('yield', 0),
                'deleted_mark': item.get('deleted_mark', 0),
                'lock_flag': item.get('lock_flag', 0),
                'ven_mat_code': item.get('ven_mat_code', ''),
                'fixed_vendor': item.get('fixed_vendor', ''),
                'bulk_material': item.get('bulk_material', 0),
                'if_centralized_supply': item.get('if_centralized_supply', 0),
                'mrp_type': item.get('mrp_type', ''),
                'planning_strategy': item.get('planning_strategy', ''),
                'forward_supply_days': item.get('forward_supply_days', 0),
                'planning_material_mode': item.get('planning_material_mode', ''),
                'planning_material_code': item.get('planning_material_code', ''),
                'source_of_demand': item.get('source_of_demand', ''),
                'production_manager': item.get('production_manager', ''),
                'quality_inspection_mark': item.get('quality_inspection_mark', 0),
                'retest_yield': item.get('retest_yield', 0),
                'create_id': item.get('create_id', user_id),
                'update_id': user_id
            }
            plant_data.append(plant_line)

    for item in financial:
        if basic["mat_code"] == item["mat_code"]:
            financial_line = {
                'mat_code': mat_code,
                'plant_code': item['plant_code'],
                'profit_center': item.get('profit_center', ''),
                'deleted_mark': item.get('deleted_mark', 0),
                'lock_flag': item.get('lock_flag', 0),
                'mat_acc_group': item.get('mat_acc_group', ''),
                'mat_sales_tax_code': item.get('mat_sales_tax_code', ''),
                'plant_val_class': item.get('plant_val_class', ''),
                'create_id': item.get('create_id', user_id),
                'update_id': user_id
            }
            financial_data.append(financial_line)

    for item in cost:
        if basic["mat_code"] == item["mat_code"]:
            cost_line = {
                'mat_code': mat_code,
                'plant_code': item['plant_code'],
                'cost_uom': item.get('cost_uom', ''),
                'plant_val_mark': item.get('plant_val_mark', 0),
                'version_val_mark': item.get('version_val_mark', 0),
                'batch_val_mark': item.get('batch_val_mark', 0),
                'other_special_val_mark': item.get('other_special_val_mark', 0),
                'outsource_val_mark': item.get('outsource_val_mark', 0),
                'project_val_mark': item.get('project_val_mark', 0),
                'stor_loc_val_mark': item.get('stor_loc_val_mark', 0),
                'so_val_mark': item.get('so_val_mark', 0),
                'valgroup_value': item.get('valgroup_value', ''),
                'mat_cost_classify': item.get('mat_cost_classify', ''),
                'co_currency': item.get('co_currency', ''),
                'plan_cost_bc': item.get('plan_cost_bc', 0),
                'plan_cost_rate': item.get('plan_cost_rate', 0),
                'plan_cost_currency': item.get('plan_cost_currency', ''),
                'effective_start_date': item.get('effective_start_date', ''),
                'basic_currency': item.get('basic_currency', ''),
                'price_control': item.get('price_control', ''),
                'price_unit': item.get('price_unit', 0),
                'cost_lot': item.get('cost_lot', 0),
                'special_pur_cc': item.get('special_pur_cc', ''),
                'deleted_mark': item.get('deleted_mark', 0),
                'lock_flag': item.get('lock_flag', 0),
                'mat_consumption': item.get('mat_consumption', ''),
                'pir_version': item.get('pir_version', ''),
                'banch_key': item.get('banch_key', ''),
                'wbs_elements': item.get('wbs_elements', ''),
                'cost_mark': item.get('cost_mark', 0),
                'create_id': item.get('create_id', user_id),
                'update_id': user_id
            }
            cost_data.append(cost_line)

    for item in sales:
        if basic["mat_code"] == item["mat_code"]:
            sales_line = {
                'mat_code': mat_code,
                'sales_org_code': item['sales_org_code'],
                'deleted_mark': item.get('deleted_mark', 0),
                'lock_flag': item.get('lock_flag', 0),
                'min_order_qty': item.get('min_order_qty', 0),
                'min_delivery_qty': item.get('min_delivery_qty', 0),
                'default_plant': item.get('default_plant', ''),
                'sales_uom': item.get('sales_uom', ''),
                'sales_uom_2': item.get('sales_uom_2', ''),
                'item_category_group': item.get('item_category_group', ''),
                'mat_price_group': item.get('mat_price_group', ''),
                'create_id': item.get('create_id', user_id),
                'update_id': user_id
            }
            sales_data.append(sales_line)
    delete_uomconv = []
    for item in uomconv:
        if basic["mat_code"] == item["mat_code"]:
            if item.get("_tag_") == "delete":
                delete_uomconv.append(str(item["id"]))
                continue
            uomconv_line = {
                'mat_code': mat_code,
                'primary_uom': item.get('primary_uom', ''),
                'primary_uom_qty': item.get('primary_uom_qty', 0),
                'secondary_uom': item.get('secondary_uom', ''),
                'secondary_uom_qty': item.get('secondary_uom_qty', 0),
                'create_id': item.get('create_id', user_id),
                'update_id': user_id
            }
            uomconv_data.append(uomconv_line)

    # 自动维护 1 : 1 单位换算关系
    for item in _uomconv:
        uomconv_line = {
            'mat_code': mat_code,
            'primary_uom': item.get('primary_uom', ''),
            'primary_uom_qty': item.get('primary_uom_qty', 0),
            'secondary_uom': item.get('secondary_uom', ''),
            'secondary_uom_qty': item.get('secondary_uom_qty', 0),
            'create_id': item.get('create_id', user_id),
            'update_id': user_id
        }
        uomconv_data.append(uomconv_line)

    for item in detail:
        if basic["mat_code"] == item["mat_code"]:
            detail_line = {}
            if item.get("field_type", "varchar") == "varchar":
                detail_line = {
                    'mat_code': mat_code,
                    'property_group': item.get('property_group', ''),
                    'field_code': item.get('field_code', ''),
                    'field_value': item.get('field_value', ''),
                    'field_value_from': item.get('field_value_from', ''),
                    'field_value_to': item.get('field_value_to', ''),
                    'field_value_int': 0,
                    'field_value_int_from': 0,
                    'field_value_int_to': 0,
                    'field_value_date': '',
                    'field_value_date_from': '',
                    'field_value_date_to': '',
                    'field_value_time': '',
                    'field_value_time_from': '',
                    'field_value_time_to': '',
                    'field_value_decimal': 0,
                    'field_value_decimal_from': 0,
                    'field_value_decimal_to': 0,
                    'create_id': item.get('create_id', user_id),
                    'update_id': user_id
                }
            if item.get("field_type", "varchar") == "int":
                detail_line = {
                    'mat_code': mat_code,
                    'property_group': item.get('property_group', ''),
                    'field_code': item.get('field_code', ''),
                    'field_value': '',
                    'field_value_from': '',
                    'field_value_to': '',
                    'field_value_int': item.get('field_value', 0),
                    'field_value_int_from': item.get('field_value_from', 0),
                    'field_value_int_to': item.get('field_value_to', 0),
                    'field_value_date': '',
                    'field_value_date_from': '',
                    'field_value_date_to': '',
                    'field_value_time': '',
                    'field_value_time_from': '',
                    'field_value_time_to': '',
                    'field_value_decimal': 0,
                    'field_value_decimal_from': 0,
                    'field_value_decimal_to': 0,
                    'create_id': item.get('create_id', user_id),
                    'update_id': user_id
                }
            if item.get("field_type", "varchar") == "date":
                detail_line = {
                    'mat_code': mat_code,
                    'property_group': item.get('property_group', ''),
                    'field_code': item.get('field_code', ''),
                    'field_value': '',
                    'field_value_from': '',
                    'field_value_to': '',
                    'field_value_int': 0,
                    'field_value_int_from': 0,
                    'field_value_int_to': 0,
                    'field_value_date': item.get('field_value', ''),
                    'field_value_date_from': item.get('field_value_from', ''),
                    'field_value_date_to': item.get('field_value_to', ''),
                    'field_value_time': '',
                    'field_value_time_from': '',
                    'field_value_time_to': '',
                    'field_value_decimal': 0,
                    'field_value_decimal_from': 0,
                    'field_value_decimal_to': 0,
                    'create_id': item.get('create_id', user_id),
                    'update_id': user_id
                }
            if item.get("field_type", "varchar") == "time":
                detail_line = {
                    'mat_code': mat_code,
                    'property_group': item.get('property_group', ''),
                    'field_code': item.get('field_code', ''),
                    'field_value': '',
                    'field_value_from': '',
                    'field_value_to': '',
                    'field_value_int': 0,
                    'field_value_int_from': 0,
                    'field_value_int_to': 0,
                    'field_value_date': '',
                    'field_value_date_from': '',
                    'field_value_date_to': '',
                    'field_value_time': item.get('field_value', ''),
                    'field_value_time_from': item.get('field_value_from', ''),
                    'field_value_time_to': item.get('field_value_to', ''),
                    'field_value_decimal': 0,
                    'field_value_decimal_from': 0,
                    'field_value_decimal_to': 0,
                    'create_id': item.get('create_id', user_id),
                    'update_id': user_id
                }
            if item.get("field_type", "varchar") == "decimal":
                detail_line = {
                    'mat_code': mat_code,
                    'property_group': item.get('property_group', ''),
                    'field_code': item.get('field_code', ''),
                    'field_value': '',
                    'field_value_from': '',
                    'field_value_to': '',
                    'field_value_int': 0,
                    'field_value_int_from': 0,
                    'field_value_int_to': 0,
                    'field_value_date': '',
                    'field_value_date_from': '',
                    'field_value_date_to': '',
                    'field_value_time': '',
                    'field_value_time_from': '',
                    'field_value_time_to': '',
                    'field_value_decimal': item.get('field_value', 0),
                    'field_value_decimal_from': item.get('field_value_from', 0),
                    'field_value_decimal_to': item.get('field_value_to', 0),
                    'create_id': item.get('create_id', user_id),
                    'update_id': user_id
                }
            detail_data.append(detail_line)

    # 质量检测表
    insert, update, delete = [], [], []
    for data in quality:
        if data.get("_tag_") == "insert":
            insert.append(data)
        elif data.get("_tag_") == "update":
            update.append(data)
        elif data.get("_tag_") == "delete":
            delete.append(data)
    if delete:
        sql = f"""DELETE FROM `t_mmd_material_quality_Inspection_data` WHERE (`mat_code`,`plant_code`,`inspection_type`) in ({','.join(["('{}','{}','{}')".format(str(i['mat_code']), str(i['plant_code']), str(i['inspection_type'])) for i in delete])}) """
        code = dh.exec_sql(sql)
        TEST and usprint.printInfo(code, sql)
    if update:
        # note = CASE id
        # {" ".join([f" WHEN {i['id']} THEN '{str(i['note'])}' " for i in update])}
        # END,
        sql = f"""
            UPDATE `t_mmd_material_quality_Inspection_data`  SET 
            `inspection_type` = CASE `id` 
                {" ".join([f" WHEN {i['id']} THEN '{str(i['inspection_type'])}' " for i in update])}
            END,
            `activation_flag` = CASE `id` 
                {" ".join([f" WHEN {i['id']} THEN {i['activation_flag'] if str(i['activation_flag']) in ['0', '1'] else '0'} " for i in update])}
            END,
            `update_id` = {user_id}   
            WHERE `id` IN ({','.join([str(i['id']) for i in update])})
        """
        code = dh.exec_sql(sql)
        TEST and usprint.printInfo(code, sql)
    if insert:
        sql = f"""
            INSERT INTO `t_mmd_material_quality_Inspection_data`(`mat_code`,`plant_code`,`inspection_type`,`activation_flag`,`create_id`,`update_id`) 
            VALUES {",".join([f"('{mat_code}','{i['plant_code']}','{i['inspection_type']}',{i['activation_flag']},{user_id},{user_id})" for i in insert])}
        """
        code = dh.exec_sql(sql)
        TEST and usprint.printInfo(code, sql)

    if basic_data:
        DuplicateSQLKey = [
            'mat_description',
            'mat_type',
            'basic_uom',
            'parallel_uom',
            'parallel_uom_mark',
            'mat_group',
            'mat_group_2',
            'old_mat_code',
            'old_description',
            'prod_group',
            'prod_group_2',
            'mat_status',
            'deleted_mark',
            'lock_flag',
            'external_mat_code',
            'net_weight',
            'gross_weight',
            'weight_uom',
            'volume',
            'volume_uom',
            'priority_code',
            'capacity_dimension',
            'process_code',
            'remarks',
            'shelf_life_enabled',
            'shelf_life_days',
            'create_id',
            'update_id'
        ]
        dh.batchInsertToDB('t_mmd_material_basic_data', basic_data, DuplicateSQLKey=DuplicateSQLKey)

    if plant_data:
        DuplicateSQLKey = [
            'batch_mark',
            'granularity_uom',
            'pur_group',
            'pur_uom',
            'pur_uom_2',
            'prod_uom',
            'source_mark',
            'plan_group',
            'sub_group',
            'lot_size',
            'lot_uom',
            'stor_loc_code',
            'stor_loc_code2',
            'max_lot',
            'min_lot',
            'mpq',
            'safety_type',
            'safety_stock_quantity',
            'reorder_point',
            'pur_type',
            'special_pur_type',
            'dely_period',
            'prod_period',
            'trans_period',
            'insp_period',
            'waiting_time',
            'assembly_loss_rate',
            'yield',
            'deleted_mark',
            'lock_flag',
            'ven_mat_code',
            'fixed_vendor',
            'bulk_material',
            'if_centralized_supply',
            'mrp_type',
            'planning_strategy',
            'forward_supply_days',
            'planning_material_mode',
            'planning_material_code',
            'source_of_demand',
            'production_manager',
            'quality_inspection_mark',
            'retest_yield',
            'create_id',
            'update_id'
        ]
        dh.batchInsertToDB('t_mmd_material_plant_data', plant_data, DuplicateSQLKey=DuplicateSQLKey)

    if financial_data != "":
        DuplicateSQLKey = [
            'profit_center',
            'deleted_mark',
            'lock_flag',
            'mat_acc_group',
            'mat_sales_tax_code',
            'plant_val_class',
            'create_id',
            'update_id'
        ]
        dh.batchInsertToDB('t_mmd_material_financial_data', financial_data, DuplicateSQLKey=DuplicateSQLKey)

    if cost_data:
        DuplicateSQLKey = [
            'cost_uom',
            'plant_val_mark',
            'version_val_mark',
            'batch_val_mark',
            'other_special_val_mark',
            'outsource_val_mark',
            'project_val_mark',
            'stor_loc_val_mark',
            'so_val_mark',
            'valgroup_value',
            'mat_cost_classify',
            'co_currency',
            'plan_cost_bc',
            'plan_cost_rate',
            'plan_cost_currency',
            'effective_start_date',
            'basic_currency',
            'price_control',
            'price_unit',
            'cost_lot',
            'special_pur_cc',
            'deleted_mark',
            'lock_flag',
            'mat_consumption',
            'pir_version',
            'banch_key',
            'wbs_elements',
            'cost_mark',
            'create_id',
            'update_id'
        ]
        dh.batchInsertToDB('t_mmd_material_cost_data', cost_data, DuplicateSQLKey=DuplicateSQLKey)

    if sales_data:
        DuplicateSQLKey = [
            'deleted_mark',
            'lock_flag',
            'min_order_qty',
            'min_delivery_qty',
            'default_plant',
            'sales_uom',
            'sales_uom_2',
            'item_category_group',
            'mat_price_group',
            'create_id',
            'update_id'
        ]
        dh.batchInsertToDB('t_mmd_material_sales_data', sales_data, DuplicateSQLKey=DuplicateSQLKey)
    usprint.printInfo("delete_uomconv>>>>",delete_uomconv)
    if delete_uomconv:
        dh.batchDeleteToDB('t_mmd_uom_conversion', delete_uomconv)

    if uomconv_data:
        usprint.printInfo("uomconv_data>>>",uomconv_data)
        DuplicateSQLKey = [
            'primary_uom_qty',
            'secondary_uom_qty',
            'create_id',
            'update_id'
        ]
        dh.batchInsertToDB('t_mmd_uom_conversion', uomconv_data, DuplicateSQLKey=DuplicateSQLKey)

    if memo["long_text"] != "":
        memo_data = [
            {
                'mat_code': mat_code,
                'long_text': memo["long_text"],
                'create_id': user_id,
                'update_id': user_id
            }
        ]
        dh.batchInsertToDB('t_mmd_material_memo', memo_data, DuplicateSQLKey=['long_text', 'create_id', 'update_id'])

    if detail_data:
        DuplicateSQLKey = [
            'field_value',
            'field_value_from',
            'field_value_to',
            'field_value_int',
            'field_value_int_from',
            'field_value_int_to',
            'field_value_date',
            'field_value_date_from',
            'field_value_date_to',
            'field_value_time',
            'field_value_time_from',
            'field_value_time_to',
            'field_value_decimal',
            'field_value_decimal_from',
            'field_value_decimal_to',
            'create_id',
            'update_id'
        ]
        dh.batchInsertToDB('t_mmd_material_field_details', detail_data, DuplicateSQLKey=DuplicateSQLKey)

    return mat_code


def isExternalNumber(mat_type):
    code = 0
    msg = ""
    isExternal = ""

    querySQL = """
        select DISTINCT
            `external_number`
        from `t_gi_coding_domain` as `a`
        join `t_gi_coding_domain_alloc` as `b`
            on `a`.`coding_domain` = `b`.`coding_domain`
        where `b`.`object_code` = '{}'
        and `b`.`alloc_object` = 'mmd_material_type'
    """.format(mat_type)

    data = []
    data = dh.query_sql(querySQL)
    if not data:
        msg = "物料类型" + str(mat_type) + "未配置编码规则"
        code = 500
    else:
        if data[0]["external_number"] == 0:
            isExternal = ""
        else:
            isExternal = "X"
        code = 200
        msg = "查询成功"

    return code, msg, isExternal


def checkUom(uom, text):
    code = 0
    msg = ""

    querySQL = """
        select DISTINCT
            `unit_of_measure`
        from `t_mmd_uom`
        where `unit_of_measure` = '{}'
    """.format(uom)

    data = []
    data = dh.query_sql(querySQL)
    if not data:
        msg = text + str(uom) + "不存在"
        code = 500
    else:
        code = 200
        msg = "查询成功"

    return code, msg


def checkMatGroup(mat_type, mat_group):
    code = 0
    msg = ""

    data = []
    data = dh.query_sql(
        "select distinct `mat_group`,`material_group_description` from `t_mmd_material_group` where `mat_group` = '{}'".format(
            mat_group))
    if not data:
        msg = "基本信息中物料组" + str(mat_group) + "不存在"
        code = 500
    else:
        code = 200
        msg = "查询成功"

    return code, msg


def checkMatGroup2(mat_group_2):
    code = 0
    msg = ""

    querySQL = """
        select DISTINCT
            `mat_group_2`
        from `t_mmd_material_group_2`
        where `mat_group_2` = '{}'
    """.format(mat_group_2)

    data = []
    data = dh.query_sql(querySQL)
    if not data:
        msg = "基本信息中二级物料组" + str(mat_group_2) + "不存在"
        code = 500
    else:
        code = 200
        msg = "查询成功"

    return code, msg


def checkProdGroup(prod_group):
    code = 0
    msg = ""

    querySQL = """
        select DISTINCT
            `prod_group`
        from `t_mmd_product_group`
        where `prod_group` = '{}'
    """.format(prod_group)

    data = []
    data = dh.query_sql(querySQL)
    if not data:
        msg = "基本信息中产品组" + str(prod_group) + "不存在"
        code = 500
    else:
        code = 200
        msg = "查询成功"

    return code, msg


def checkProdGroup2(prod_group_2):
    code = 0
    msg = ""

    querySQL = """
        select DISTINCT
            `prod_group_2`
        from `t_mmd_product_group_2`
        where `prod_group_2` = '{}'
    """.format(prod_group_2)

    data = []
    data = dh.query_sql(querySQL)
    if not data:
        msg = "基本信息中二级产品组" + str(prod_group_2) + "不存在"
        code = 500
    else:
        code = 200
        msg = "查询成功"

    return code, msg


def checkMaterial(mat_code, text):
    code = 0
    msg = ""

    querySQL = """
        select DISTINCT
            `mat_code`
        from `t_mmd_material_basic_data`
        where `mat_code` = '{}'
    """.format(mat_code)

    data = []
    data = dh.query_sql(querySQL)
    if not data:
        msg = text + str(mat_code) + "不存在"
        code = 500
    else:
        code = 200
        msg = "查询成功"

    return code, msg


def is_date(s):
    try:
        datetime.strptime(s, '%Y-%m-%d')  # 格式为年月
        return True
    except ValueError:
        return False


def checkPlantCode(plant_code):
    code = 0
    msg = ""

    querySQL = """
        select DISTINCT
            `plant_code`
        from `t_os_plant`
        where `plant_code` = '{}'
    """.format(plant_code)

    data = []
    data = dh.query_sql(querySQL)
    if not data:
        msg = "工厂" + str(plant_code) + "不存在"
        code = 500
    else:
        code = 200
        msg = "查询成功"

    return code, msg


def checkPurGroup(pur_group):
    code = 0
    msg = ""

    querySQL = """
        select DISTINCT
            `pur_group`
        from `t_os_pur_group`
        where `pur_group` = '{}'
    """.format(pur_group)

    data = []
    data = dh.query_sql(querySQL)
    if not data:
        msg = "工厂数据中采购组" + str(pur_group) + "不存在"
        code = 500
    else:
        code = 200
        msg = "查询成功"

    return code, msg


def checkPlanGroup(plan_group):
    code = 0
    msg = ""

    querySQL = """
        select DISTINCT
            `plan_group`
        from `t_mmd_planning_group`
        where `plan_group` = '{}'
    """.format(plan_group)

    data = []
    data = dh.query_sql(querySQL)
    if not data:
        msg = "工厂数据中计划组" + str(plan_group) + "不存在"
        code = 500
    else:
        code = 200
        msg = "查询成功"

    return code, msg


def checkLotType(lot_size):
    code = 0
    msg = ""

    querySQL = """
        select DISTINCT
               `lot_size`
        from `t_mmd_lot_size_type`
        where `lot_size` = '{}'
    """.format(lot_size)

    data = []
    data = dh.query_sql(querySQL)
    if not data:
        msg = "工厂数据中批量大小类型" + str(lot_size) + "不存在"
        code = 500
    else:
        code = 200
        msg = "查询成功"

    return code, msg


def checkStorLocCode(plant_code, stor_loc_code, text):
    code = 0
    msg = ""

    querySQL = """
        select DISTINCT
            `plant_code`,
            `stor_loc_code`
        from `t_os_plant_storage_location_alloc`
        where `plant_code` = '{}'
        and `stor_loc_code` = '{}'
    """.format(plant_code, stor_loc_code)

    data = []
    data = dh.query_sql(querySQL)
    if not data:
        msg = text + str(stor_loc_code) + "在工厂" + str(plant_code) + "中不存在"
        code = 500
    else:
        code = 200
        msg = "查询成功"

    return code, msg


def checkSafetyType(safety_type):
    code = 0
    msg = ""

    querySQL = """
        select DISTINCT
               `safety_type`
        from `t_mmd_safety_stock_type`
        where `safety_type` = '{}'
    """.format(safety_type)

    data = []
    data = dh.query_sql(querySQL)
    if not data:
        msg = "工厂数据中安全库存类型" + str(safety_type) + "不存在"
        code = 500
    else:
        code = 200
        msg = "查询成功"

    return code, msg


def checkFixedVendor(fixed_vendor):
    code = 0
    msg = ""

    querySQL = """
        select DISTINCT
            `vendor_code`
        from `t_bpv_vendor_basic_data`
        where `vendor_code` = '{}'
    """.format(fixed_vendor)

    data = []
    data = dh.query_sql(querySQL)
    if not data:
        msg = "工厂数据中指定供应商" + str(fixed_vendor) + "不存在"
        code = 500
    else:
        code = 200
        msg = "查询成功"

    return code, msg


def checkMatSalesTaxCode(tax_code):
    code = 0
    msg = ""

    querySQL = """
        select DISTINCT
            `tax_code`
        from `t_tax_code`
        where `tax_code` = '{}'
    """.format(tax_code)

    data = []
    data = dh.query_sql(querySQL)
    if not data:
        msg = "财务数据中物料销售税码" + str(tax_code) + "不存在"
        code = 500
    else:
        code = 200
        msg = "查询成功"

    return code, msg


def checkProfitCenter(plant_code, profit_center):
    querySQL = """
      select 
        `p`.`profit_center`,
        `p`.`pro_center_description` 
      from `t_os_profit_center` as `p`
      join `t_os_profit_center_company_allocation` as `c` on `p`.`profit_center` = `c`.`profit_center`
      join `t_os_company_plant_alloc` as `cp` on `cp`.`company_code` = `c`.`company_code`
      where `cp`.`plant_code` = '{}' and `p`.`profit_center` = '{}'
      group by `p`.`profit_center`, `p`.`pro_center_description`
      order by `p`.`profit_center`
    """.format(plant_code, profit_center)

    data = dh.query_sql(querySQL)
    if data:
        return 200, '查询成功'

    return 500, '利润中心{}在工厂{}下不存在'.format(profit_center, plant_code)


def checkAllMaterialUnit(mat_code, plant_code, cost_uom, basic_uom):
    querySQL = """
        SELECT
            `c`.`mat_code`,
            `c`.`cost_uom`,
            `b`.`basic_uom` 
        FROM
            `t_mmd_material_cost_data` AS `c`
            JOIN `t_mmd_material_basic_data` AS `b` ON `b`.`mat_code` = `c`.`mat_code` 
        WHERE
            `c`.`plant_code` = '{}' 
            AND `c`.`valgroup_value` = '{}' 
            AND ( `c`.`cost_uom` != '{}' OR `b`.`basic_uom` != '{}' ) 
            LIMIT 1
    """.format(plant_code, mat_code, cost_uom, basic_uom)

    data = []
    data = dh.query_sql(querySQL)

    if data:
        return 500, "物料编码{}组评估物料{}基本单位或成本单位与系统已有物料不一致！".format(data[0]["mat_code"],
                                                                                           mat_code)
    else:
        return 200, ''


def checkMatCostClassify(plant_code, mat_cost_classify):
    code = 0
    msg = ""

    querySQL = """
        select DISTINCT
            `mat_cost_classify`,
            `cost_classify_descrip`
        from `t_mmd_material_cost_classify`
        where `plant_code` = '{}'
            and `mat_cost_classify` = '{}'
    """.format(plant_code, mat_cost_classify)

    data = []
    data = dh.query_sql(querySQL)

    if not data:
        msg = "成本数据中物料成本分类" + str(mat_cost_classify) + "不存在"
        code = 500
    else:
        code = 200
        msg = "查询成功"

    return code, msg


def checkCoCurrency(plant_code):
    code = 0
    msg = ""
    co_currency = ""

    querySQL = """
        select DISTINCT
            `a`.`co_currency`
        from `t_os_controlling_area` as `a`
        join `t_os_company` as `c`
        on `a`.`cost_area` = `c`.`cost_area`
        join `t_os_company_plant_alloc` as `p`
        on `c`.`company_code` = `p`.`company_code`
        where `p`.`plant_code` = '{}'
    """.format(plant_code)

    data = []
    data = dh.query_sql(querySQL)
    if not data:
        msg = "成本数据中成本管理组织货币未找到"
        code = 500
    else:
        code = 200
        msg = "查询成功"
        co_currency = data[0]["co_currency"]

    return code, msg, co_currency


def checkCurrency(plant_code):
    code = 0
    msg = ""
    basic_currency = ""

    querySQL = """
        SELECT
            `c`.`basic_currency` 
        FROM
            `t_os_company` AS `c`
            JOIN `t_os_company_plant_alloc` AS `a` ON `a`.`company_code` = `c`.`company_code` 
        WHERE
            `a`.`plant_code` = '{}' 
        LIMIT 1
    """.format(plant_code)

    data = []
    data = dh.query_sql(querySQL)
    if not data:
        msg = "未获取到本位币"
        code = 500
    else:
        code = 200
        msg = "查询成功"
        basic_currency = data[0]["basic_currency"]

    return code, msg, basic_currency


def checkWBSelement(wbs_elements, plant_code):
    querySQL = """
        SELECT
            `w`.`wbs_elements`,
            `w`.`wbs_description` 
        FROM
            `t_co_wbs_element` AS `w`
            JOIN `t_os_company_plant_alloc` AS `p` ON `p`.`company_code` = `w`.`company_code`
            JOIN `t_os_company` AS `c` ON `c`.`company_code` = `p`.`company_code` 
            AND `c`.`cost_area` = `w`.`cost_area` 
        WHERE
            `p`.`plant_code` = '{}'
        AND `w`.`wbs_elements` = '{}'
    """.format(plant_code, wbs_elements)

    data = []
    data = dh.query_sql(querySQL)

    if data:
        return 200, ''

    return 500, "WBS元素{}不存在".format(wbs_elements)


def checkSalesCode(sales_org_code):
    code = 0
    msg = ""

    querySQL = """
        select DISTINCT
               `sales_org_code`
        from `t_os_sales_org`
        where `sales_org_code` = '{}'
    """.format(sales_org_code)

    data = []
    data = dh.query_sql(querySQL)
    if not data:
        msg = "销售组织" + str(sales_org_code) + "不存在"
        code = 500
    else:
        code = 200
        msg = "查询成功"

    return code, msg


def checkItemCatGroup(sd_item_cat):
    code = 0
    msg = ""

    querySQL = """
        select DISTINCT
            `item_category_group` as `sd_item_cat`
        from `t_os_item_category_group`
        where `item_category_group` = '{}'
    """.format(sd_item_cat)

    data = []
    data = dh.query_sql(querySQL)
    if not data:
        msg = "销售数据中项目类别组" + str(sd_item_cat) + "不存在"
        code = 500
    else:
        code = 200
        msg = "查询成功"

    return code, msg


# 弃用
def getMatCode(mat_type):
    data = []
    querySQL = """
        select DISTINCT
            `d`.`prefix`, 
            `d`.`joiner`, 
            `d`.`suffix`, 
            `d`.`sequence_number`, 
            `d`.`current_number`, 
            `d`.`date_format`,
            `d`.`coding_domain`
        from `t_gi_coding_domain` as `d`
        join `t_gi_coding_domain_alloc` as `a`
        on `a`.`coding_domain` = `d`.`coding_domain`
        where `a`.`object_code` = '{}'
        and `a`.`alloc_object` = 'mmd_material_type'
    """.format(mat_type)
    data = dh.query_sql(querySQL)
    prefix = data[0]["prefix"]
    joiner = data[0]["joiner"]
    suffix = data[0]["suffix"]
    serial_code = data[0]["sequence_number"]
    date_format = data[0]["date_format"]
    current_number = data[0]["current_number"] + 1
    coding_domain = data[0]["coding_domain"]
    time = ""
    if date_format != "":
        y_count = date_format.count('Y')
        if y_count == 4:
            date_format = re.sub(r'Y+', '%Y', date_format)
        elif y_count == 2:
            date_format = re.sub(r'Y+', '%y', date_format)
        date_format = re.sub(r'M+', '%m', date_format)
        date_format = re.sub(r'D+', '%d', date_format)
        date_format = re.sub(r'W+', '%W', date_format)
        time = datetime.now().strftime(date_format)

    update_query = "UPDATE `t_gi_coding_domain` SET `current_number` = {} WHERE `coding_domain` = '{}'".format(
        current_number, coding_domain)
    dh.exec_sql(update_query)
    if time != "":
        return "{}{}{}{}{:0{}d}{}{}".format(prefix, joiner, time, joiner, current_number, serial_code, joiner, suffix)
    else:
        return "{}{}{:0{}d}{}{}".format(prefix, joiner, current_number, serial_code, joiner, suffix)


def checkParallelUomMark(mat_type):
    code = 200
    msg = ""

    query_sql = """
        SELECT
            `id` 
        FROM
            `t_mmd_material_type`
        WHERE
            `mat_type` = '{}' 
            AND `parallel_uom_mark` = 1 
        LIMIT 1
    """.format(mat_type)
    data = []
    data = dh.query_sql(query_sql)
    if not data:
        code = 500
        msg = "该物料类型的平行单位标记未启用"

    return code, msg
