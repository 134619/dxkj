#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@File    : Z_mainmaterial_basic_data.py
@explain : 物料主数据
"""
import copy
from datetime import date, datetime

from DbHelper import DbHelper
from DxBusinessDataConvertUtil import convert_material_unit_qty
from DxMaintainMaterialData import maintain_data


def save_mainmaterial_basic_data(payload, user_id):
    '''
    保存物料主数据
    '''
    db = DbHelper()
    code, msg = "S", "保存成功"

    query_data = db.query_sql('''SELECT id, mat_code FROM t_mmd_material_basic_data''')
    mat_code_list = [index['mat_code'] for index in query_data]

    data = payload.get("data")
    print("data", data)

    # try:
    for dz in data:

        # t_mmd_material_basic_data
        basic = dz.get("basic")
        mat_code = basic.get("mat_code")

        if mat_code not in mat_code_list:
            mode = "A"   # 新增

            print("走物料新增")

            mat_type1 = basic.get("mat_type1")
            mat_type2 = basic.get("mat_type2")
            mat_type3 = basic.get("mat_type3")
            mat_type4 = basic.get("mat_type4")
            basic_uom = basic.get("basic_uom")  # 基本单位
            remarks = basic.get("remarks")  # 备注
            basic["parallel_uom"] = ""
            old_mat_code = basic.get("old_mat_code").replace('\\', '\\\\').replace("'", "\\\'").replace('"', '\\\"')
            mat_description = basic.get("mat_description").replace('\\', '\\\\').replace("'", "\\\'").replace('"', '\\\"')

            query_sql_basic = f"SELECT process_code, mat_description, mat_type, mat_group, basic_uom " \
                              f"FROM t_mmd_material_basic_data WHERE mat_code = '{mat_code}'  "
            print("query_sql_basic--", query_sql_basic)
            query_data_basic = db.query_sql(query_sql_basic)
            if query_data_basic:  # query_data_basic 为空说明是新增 不用管   有数据说明是修改
                if not basic.get("process_code"):
                    basic["process_code"] = query_data_basic[0].get("process_code")

                if not basic.get("mat_description"):
                    basic["mat_description"] = query_data_basic[0].get("mat_description")

                if not basic.get("mat_type"):
                    basic["mat_type"] = query_data_basic[0].get("mat_type")

                if not basic.get("mat_group"):
                    basic["mat_group"] = query_data_basic[0].get("mat_group")

                if not basic.get("basic_uom"):
                    basic["basic_uom"] = query_data_basic[0].get("basic_uom")

            if "M" != mat_type1:
                if "C" == mat_type2:
                    mat_type = "Z004"
                else:
                    mat_type = "Z002"
            else:
                if "K" == mat_type4:
                    mat_type = "Z003"
                else:
                    mat_type = "Z001"

            print("mat_type", mat_type)
            basic["mat_type"] = mat_type

            mat_group = mat_type3
            basic["mat_group"] = mat_group
            if len(mat_description) >= 80:
                print("before", len(mat_description))
                mat_description = str(mat_description)[:80]
                print("after", mat_description)
                print("after", len(mat_description))

            basic["mat_description"] = mat_description
            basic["old_mat_code"] = old_mat_code

            # t_mmd_material_plant_data
            plant = dz.get("plant", [])
            plant1 = copy.deepcopy(plant)

            bulk_material = 0
            mat_consumption = ""  # 存入cost表中
            query_sql_mat_consumption = f"SELECT mat_consumption " \
                                        f"FROM t_mmd_material_group_consumption " \
                                        f"WHERE plant_code = '1000' AND mat_group = '{mat_group}' "
            print("mat_consumption_sql", query_sql_mat_consumption)
            query_data = db.query_sql(query_sql_mat_consumption)
            if query_data:
                mat_consumption = query_data[0].get("mat_consumption")
                if "2" == mat_consumption:
                    bulk_material = 1

            for index in plant:
                index["pur_group"] = "100"
                index["plant_code"] = "1000"  # 这边存两条值  一条工厂1000的  一条100N的
                index["bulk_material"] = bulk_material
                index["source_mark"] = 0
                index["deleted_mark"] = 0
                index["lock_flag"] = 0

            bulk_material1 = 0
            mat_consumption1 = ""  # 存入cost表中
            query_sql_mat_consumption1 = f"SELECT mat_consumption " \
                                         f"FROM t_mmd_material_group_consumption " \
                                         f"WHERE plant_code = '100N' AND mat_group = 'NS1' "
            print("query_sql_mat_consumption1", query_sql_mat_consumption1)
            query_data1 = db.query_sql(query_sql_mat_consumption1)
            if query_data1:
                mat_consumption1 = query_data1[0].get("mat_consumption")
                if "2" == mat_consumption1:
                    bulk_material1 = 1

            for index in plant1:
                index["pur_group"] = "100"
                index["plant_code"] = "100N"  # 客供料  这边存两条值  一条工厂1000的  一条100N的
                index["bulk_material"] = bulk_material1
                index["source_mark"] = 0
                index["pur_type"] = "F"
                index["deleted_mark"] = 0
                index["lock_flag"] = 0

            # t_mmd_material_cost_data
            cost = dz.get("cost", [])
            for index in cost:
                if not index.get("mat_code"):
                    index["mat_code"] = mat_code

            cost1 = copy.deepcopy(cost)

            for index in cost:
                index["plant_code"] = "1000"
                index["cost_uom"] = basic_uom
                index["plant_val_mark"] = 1
                index["version_val_mark"] = 0
                index["batch_val_mark"] = 0
                index["other_special_val_mark"] = 0
                index["outsource_val_mark"] = 0
                index["project_val_mark"] = 0
                index["stor_loc_val_mark"] = 0
                index["so_val_mark"] = 0
                index["co_currency"] = "CNY"
                index["basic_currency"] = "CNY"
                index["price_unit"] = 1
                index["cost_lot"] = 1
                index["mat_consumption"] = mat_consumption

                plan_cost_bc = index.get("plan_cost_bc")  # 计划价格
                plan_price_unit = index.get("plan_price_unit")  # 计划价格单位

                print("mat_code", mat_code)
                print("basic_uom", basic_uom)
                print("plan_price_unit", plan_price_unit)
                print("plan_cost_bc", plan_cost_bc)
                code_new, msg_new, qty_new = convert_material_unit_qty(mat_code, plan_price_unit, basic_uom,
                                                                       plan_cost_bc)
                print("code_new", code_new)
                print("msg_new", msg_new)
                print("qty_new", qty_new)

                index["plan_cost_bc"] = qty_new

                query_sql_cost = f"SELECT price_control " \
                                 f"FROM t_mmd_material_cost_data " \
                                 f"WHERE mat_code = '{mat_code}' AND plant_code = '1000'  "
                print("query_sql_cost--", query_sql_cost)
                query_data_cost = db.query_sql(query_sql_cost)
                if query_data_cost:  # query_data_basic 为空说明是新增 不用管   有数据说明是修改
                    if not index.get("price_control"):
                        index["price_control"] = query_data_cost[0].get("price_control")

            print("cost--", cost)

            for index_cost in cost1:
                index_cost["plant_code"] = "100N"
                index_cost["cost_uom"] = basic_uom
                index_cost["plant_val_mark"] = 1
                index_cost["version_val_mark"] = 0
                index_cost["batch_val_mark"] = 0
                index_cost["other_special_val_mark"] = 0
                index_cost["outsource_val_mark"] = 0
                index_cost["project_val_mark"] = 0
                index_cost["stor_loc_val_mark"] = 0
                index_cost["so_val_mark"] = 0
                index_cost["co_currency"] = "CNY"
                index_cost["basic_currency"] = "CNY"
                index_cost["price_unit"] = 1
                index_cost["cost_lot"] = 1
                index_cost["mat_consumption"] = mat_consumption1

                plan_cost_bc = index_cost.get("plan_cost_bc")  # 计划价格
                plan_price_unit = index_cost.get("plan_price_unit")  # 计划价格单位

                print("mat_code", mat_code)
                print("basic_uom", basic_uom)
                print("plan_price_unit", plan_price_unit)
                print("plan_cost_bc", plan_cost_bc)
                code_new1, msg_new1, qty_new1 = convert_material_unit_qty(mat_code, plan_price_unit, basic_uom,
                                                                          plan_cost_bc)
                print("code_new1", code_new1)
                print("msg_new1", msg_new1)
                print("qty_new1", qty_new1)

                index_cost["plan_cost_bc"] = qty_new1

                query_sql_cost1 = f"SELECT price_control " \
                                  f"FROM t_mmd_material_cost_data " \
                                  f"WHERE mat_code = '{mat_code}' AND plant_code = '100N'  "
                print("query_sql_cost1--", query_sql_cost1)
                query_data_cost1 = db.query_sql(query_sql_cost1)
                if query_data_cost1:  # query_data_basic 为空说明是新增 不用管   有数据说明是修改
                    if not index_cost.get("price_control"):
                        index_cost["price_control"] = query_data_cost1[0].get("price_control")

            print("cost1--", cost1)

            # sales = dz.get("sales") # 没有销售视图

            # t_mmd_material_financial_data
            financial = dz.get("financial", [])
            for index in financial:
                index["plant_code"] = "1000"
                index["deleted_mark"] = 0
                index["lock_flag"] = 0

                query_sql_financial = f"SELECT plant_val_class " \
                                      f"FROM t_mmd_material_financial_data " \
                                      f"WHERE mat_code = '{mat_code}' AND plant_code = '1000'  "
                print("query_sql_financial--", query_sql_financial)
                query_data_financial = db.query_sql(query_sql_financial)
                if query_data_financial:  # query_data_basic 为空说明是新增 不用管   有数据说明是修改
                    if not index.get("plant_val_class"):
                        index["plant_val_class"] = query_data_financial[0].get("plant_val_class")

            financial1 = copy.deepcopy(financial)
            for index_financial in financial1:
                index_financial["plant_code"] = "100N"
                index_financial["deleted_mark"] = 0
                index_financial["lock_flag"] = 0

                query_sql_financial1 = f"SELECT plant_val_class " \
                                       f"FROM t_mmd_material_financial_data " \
                                       f"WHERE mat_code = '{mat_code}' AND plant_code = '100N'  "
                print("query_sql_financial1--", query_sql_financial1)
                query_data_financial1 = db.query_sql(query_sql_financial1)
                if query_data_financial1:  # query_data_basic 为空说明是新增 不用管   有数据说明是修改
                    if not index_financial.get("plant_val_class"):
                        index_financial["plant_val_class"] = query_data_financial1[0].get("plant_val_class")

            print("financial1--", financial1)

            # t_mmd_uom_conversion
            uomconv = dz.get("uomconv", [])

            # t_mmd_material_field_details
            detail = dz.get("detail", [])  # 特性组
            detail_new = []
            for index in detail:
                mat_code = index.get("mat_code")
                field_code = index.get("field_code")
                field_value = index.get("field_value")
                if "wyse_centralizedsupply" == field_code:  # "是否集中供应"
                    field_code = "JZGY"
                elif "JH" == field_code:  # "是否临时键合"
                    if mat_group == "MWG":
                        field_value = "是"
                    else:
                        field_value = "否"
                elif "wyse_bom" == field_code:  # 是否BOM
                    field_code = "BOM"
                elif "wyse_lifetime" == field_code:  # "LifeTime"
                    field_code = "LT"
                elif "wyse_lifetimeunit" == field_code:  # "LifeTime单位"
                    field_code = "LTDW"
                elif "wyse_amorticount" == field_code:  # "Wafer Count"
                    field_code = "WC"
                elif "wyse_certification" == field_code:  # "wyse_certification"
                    field_code = "RZZT"

                if isinstance(field_value, str):
                    field_type = "varchar"
                    field_length = "255"
                elif isinstance(field_value, int):
                    field_type = "int"
                    field_length = "10"
                elif isinstance(field_value, float):
                    field_type = "decimal"
                    field_length = "16"
                elif isinstance(field_value, date):
                    field_type = "date"
                    field_length = "10"
                else:
                    field_type = "varchar"
                    field_length = "255"

                detail_dict = {
                    "property_group": "WY01",
                    # "property_description": "物料基本信息",
                    "field_code": str(field_code),
                    # "field_name": field_name,
                    "field_value": str(field_value),

                    "field_type": str(field_type),
                    "field_length": str(field_length),
                    "field_name": str(field_code),
                    "field_value_from": "",
                    "field_value_to": "",
                    "field_mark": "1",
                    # "field_type": "varchar",
                    # "field_length": 1,
                    # "required": 0,
                    # "field_decimal_places": 0,
                    # "field_mark": "1",  # 0 范围  1 单一值
                    "mat_code": mat_code
                }
                detail_new.append(detail_dict)

            sales = []
            memo = {"mat_code": mat_code, "long_text": remarks}
            print("mat_code", mat_code)
            print("mat_code_list", mat_code_list)

        else:
            mode = "B"   # 修改

            print("走物料修改")

            remarks = basic.get("remarks", "")  # 备注

            query_sql_basic = f"SELECT process_code, mat_description, mat_type, mat_group, basic_uom, parallel_uom " \
                              f"FROM t_mmd_material_basic_data WHERE mat_code = '{mat_code}'  "
            print("query_sql_basic--", query_sql_basic)
            query_data_basic = db.query_sql(query_sql_basic)
            if query_data_basic:  # query_data_basic 为空说明是新增 不用管   有数据说明是修改
                if not basic.get("process_code"):
                    basic["process_code"] = query_data_basic[0].get("process_code")

                if not basic.get("mat_description"):
                    basic["mat_description"] = query_data_basic[0].get("mat_description")

                if not basic.get("mat_type"):
                    basic["mat_type"] = query_data_basic[0].get("mat_type")

                if not basic.get("mat_group"):
                    basic["mat_group"] = query_data_basic[0].get("mat_group")

                if not basic.get("basic_uom"):
                    basic["basic_uom"] = query_data_basic[0].get("basic_uom")

                if not basic.get("parallel_uom"):
                    basic["parallel_uom"] = query_data_basic[0].get("parallel_uom")

            mat_group = basic.get("mat_group")
            basic_uom = basic.get("basic_uom")

            # t_mmd_material_plant_data
            plant = dz.get("plant", [])
            plant1 = copy.deepcopy(plant)

            for index in plant:
                index["plant_code"] = "1000"  # 这边存两条值  一条工厂1000的  一条100N的

            for index in plant1:
                index["plant_code"] = "100N"  # 客供料  这边存两条值  一条工厂1000的  一条100N的

            # t_mmd_material_cost_data
            cost = dz.get("cost", [])
            for index in cost:
                if not index.get("mat_code"):
                    index["mat_code"] = mat_code

            cost1 = copy.deepcopy(cost)

            for index in cost:
                index["plant_code"] = "1000"
                index["cost_uom"] = basic_uom
                index["plant_val_mark"] = 1
                index["price_unit"] = 1
                index["cost_lot"] = 1

                query_sql_cost = f"SELECT price_control " \
                                 f"FROM t_mmd_material_cost_data " \
                                 f"WHERE mat_code = '{mat_code}' AND plant_code = '1000'  "
                print("query_sql_cost--", query_sql_cost)
                query_data_cost = db.query_sql(query_sql_cost)
                if query_data_cost:  # query_data_basic 为空说明是新增 不用管   有数据说明是修改
                    if not index.get("price_control"):
                        index["price_control"] = query_data_cost[0].get("price_control")

            print("cost--", cost)

            for index_cost in cost1:
                index_cost["plant_code"] = "100N"
                index_cost["cost_uom"] = basic_uom
                index_cost["plant_val_mark"] = 1
                index_cost["price_unit"] = 1
                index_cost["cost_lot"] = 1

                query_sql_cost1 = f"SELECT price_control " \
                                  f"FROM t_mmd_material_cost_data " \
                                  f"WHERE mat_code = '{mat_code}' AND plant_code = '100N'  "
                print("query_sql_cost1--", query_sql_cost1)
                query_data_cost1 = db.query_sql(query_sql_cost1)
                if query_data_cost1:  # query_data_basic 为空说明是新增 不用管   有数据说明是修改
                    if not index_cost.get("price_control"):
                        index_cost["price_control"] = query_data_cost1[0].get("price_control")

            print("cost1--", cost1)

            # sales = dz.get("sales") # 没有销售视图

            # t_mmd_material_financial_data
            financial = dz.get("financial", [])
            for index in financial:
                index["plant_code"] = "1000"

                query_sql_financial = f"SELECT plant_val_class " \
                                      f"FROM t_mmd_material_financial_data " \
                                      f"WHERE mat_code = '{mat_code}' AND plant_code = '1000'  "
                print("query_sql_financial--", query_sql_financial)
                query_data_financial = db.query_sql(query_sql_financial)
                if query_data_financial:  # query_data_basic 为空说明是新增 不用管   有数据说明是修改
                    if not index.get("plant_val_class"):
                        index["plant_val_class"] = query_data_financial[0].get("plant_val_class")

            financial1 = copy.deepcopy(financial)
            for index_financial in financial1:
                index_financial["plant_code"] = "100N"

                query_sql_financial1 = f"SELECT plant_val_class " \
                                       f"FROM t_mmd_material_financial_data " \
                                       f"WHERE mat_code = '{mat_code}' AND plant_code = '100N'  "
                print("query_sql_financial1--", query_sql_financial1)
                query_data_financial1 = db.query_sql(query_sql_financial1)
                if query_data_financial1:  # query_data_basic 为空说明是新增 不用管   有数据说明是修改
                    if not index_financial.get("plant_val_class"):
                        index_financial["plant_val_class"] = query_data_financial1[0].get("plant_val_class")

            print("financial1--", financial1)

            # t_mmd_uom_conversion
            uomconv = dz.get("uomconv", [])

            # t_mmd_material_field_details
            detail = dz.get("detail", [])  # 特性组
            detail_new = []
            for index in detail:
                mat_code = index.get("mat_code")
                field_code = index.get("field_code")
                field_value = index.get("field_value")
                if "wyse_centralizedsupply" == field_code:  # "是否集中供应"
                    field_code = "JZGY"
                elif "JH" == field_code:  # "是否临时键合"
                    if mat_group == "MWG":
                        field_value = "是"
                    else:
                        field_value = "否"
                elif "wyse_bom" == field_code:  # 是否BOM
                    field_code = "BOM"
                elif "wyse_lifetime" == field_code:  # "LifeTime"
                    field_code = "LT"
                elif "wyse_lifetimeunit" == field_code:  # "LifeTime单位"
                    field_code = "LTDW"
                elif "wyse_amorticount" == field_code:  # "Wafer Count"
                    field_code = "WC"
                elif "wyse_certification" == field_code:  # "wyse_certification"
                    field_code = "RZZT"

                if isinstance(field_value, str):
                    field_type = "varchar"
                    field_length = "255"
                elif isinstance(field_value, int):
                    field_type = "int"
                    field_length = "10"
                elif isinstance(field_value, float):
                    field_type = "decimal"
                    field_length = "16"
                elif isinstance(field_value, date):
                    field_type = "date"
                    field_length = "10"
                else:
                    field_type = "varchar"
                    field_length = "255"

                detail_dict = {
                    "property_group": "WY01",
                    # "property_description": "物料基本信息",
                    "field_code": str(field_code),
                    # "field_name": field_name,
                    "field_value": str(field_value),

                    "field_type": str(field_type),
                    "field_length": str(field_length),
                    "field_name": str(field_code),
                    "field_value_from": "",
                    "field_value_to": "",
                    "field_mark": "1",
                    # "field_type": "varchar",
                    # "field_length": 1,
                    # "required": 0,
                    # "field_decimal_places": 0,
                    # "field_mark": "1",  # 0 范围  1 单一值
                    "mat_code": mat_code
                }
                detail_new.append(detail_dict)

            sales = []
            memo = {"mat_code": mat_code, "long_text": remarks}

        code_x, msg, error_list, mat_code = maintain_data(0, basic, plant, sales, financial, cost, uomconv, memo,
                                                          detail_new, mode, user_id, quality=[])
        print("code_x", code_x)
        print("msg", msg)
        print("error_list", error_list)
        print("mat_code", mat_code)
        if 200 == code_x:
            code1_x, msg, error_list1, mat_code1 = maintain_data(0, basic, plant1, sales, financial1, cost1, uomconv,
                                                                 memo,
                                                                 detail_new, "B", user_id, quality=[])
            print("code1_x", code1_x)
            print("msg1", msg)
            print("error_list1", error_list1)
            print("mat_code1", mat_code1)

            if 200 == code1_x:
                code = "S"
            else:
                code = "E"
                msg = str(error_list1)
        else:
            code = "E"
            msg = str(error_list)

        # if code == "S":
        #     code, msg = make_standard(basic, cost, plant, user_id, code, msg)

    return {"type": code, "message": msg}


def make_standard(basic, cost, plant, financial, user_id, code=200, msg=""):
    """
    basic: 基本视图, 单条字典
    cost: 成本视图, 多条数组
    plant: 工厂视图, 多条数组
    """
    import traceback

    from utils import ItfBizError
    dh = DbHelper()
    try:
        # 判断是否为客供料
        temp_data = dh.query_sql(f"""
        select value_update
        from t_mmd_material_type_range_limit
        where mat_type = '{basic["mat_type"]}'
        """)
        if temp_data:
            value_update = temp_data[0]
        else:
            raise ItfBizError(f"物料{basic['mat_code']}未取到物料类型{basic['mat_type']}的价值更新标识")

        if not value_update:
            print("客供料跳过标准成本", basic['mat_code'])
            return code, msg

        mat_code = basic["mat_code"]
        cost_dict = {f'{row["mat_code"]}-{row["plant_code"]}': row for row in cost}
        plant_dict = {f'{row["mat_code"]}-{row["plant_code"]}': row for row in plant}
        financial_dict = {f'{row["mat_code"]}-{row["plant_code"]}': row for row in financial}

        plant_cost_data = []
        std_header_data = []
        std_component = []
        std_item = []
        for key, cost_item in cost_dict.items():

            cost_area_data = dh.query_sql(f"""
            select cost_area, company_code, plant_code, co_currency, cost_version, basic_currency, t1.rate_type
            from t_os_company as t1
            left join t_os_company_plant_alloc using(company_code)
            left join t_os_controlling_area using(cost_area)
            left join t_bd_cost_version_setting using(cost_area)
            where plant_code = '{cost_item["plant_code"]}'
            """)
            if not cost_area_data:
                raise ItfBizError(f"物料{cost_item['mat_code']}工厂{cost_item['plant_code']}未取到成本管理组织")

            for cost_area_item in cost_area_data:
                plant_cost_item = copy.copy(cost_item)
                plant_cost_item.update(cost_area_item)
                plant_cost_data.append(plant_cost_item)

                plant_cost_item["create_id"] = user_id
                plant_cost_item["update_id"] = user_id
                plant_cost_item["plant_val_mark"] = 1
                plant_cost_item["exchange_rate"] = 1
                plant_cost_item["price_unit"] = 1
                plant_cost_item["basic_uom"] = basic["basic_uom"]
                plant_cost_item["plant_val_class"] = financial_dict.get(
                    f'{plant_cost_item["mat_code"]}-{plant_cost_item["plant_code"]}').get("plant_val_class", "")
                plant_cost_item["cost_date"] = cost_item["effective_start_date"]
                plant_cost_item["year"], plant_cost_item["period"], days = plant_cost_item["cost_date"].split("-")

                plant_cost_item["basic_unit_plan_cost_bc"] = plant_cost_item["plan_cost_bc"]
                plant_cost_item["plan_cost_bc"] = plant_cost_item["basic_unit_plan_cost_bc"] * plant_cost_item[
                    "plan_cost_rate"]

                plant_cost_item["standard_cost_bc"] = plant_cost_item.get("plan_cost_bc", 0)
                plant_cost_item["standard_cost_cc"] = plant_cost_item.get("plan_cost_bc", 0)

                temp_price_unit = 1
                if plant_cost_item["standard_cost_bc"] != 0 and plant_cost_item["standard_cost_bc"] < 0.001:
                    temp_price_unit = 100000
                elif plant_cost_item["standard_cost_bc"] != 0 and plant_cost_item["standard_cost_bc"] < 0.01:
                    temp_price_unit = 10000
                elif plant_cost_item["standard_cost_bc"] != 0 and plant_cost_item["standard_cost_bc"] < 0.1:
                    temp_price_unit = 1000
                elif plant_cost_item["standard_cost_bc"] != 0 and plant_cost_item["standard_cost_bc"] < 1:
                    temp_price_unit = 100

                plant_cost_item["price_unit"] = plant_cost_item["price_unit"] * temp_price_unit
                plant_cost_item["standard_cost_bc"] = plant_cost_item["standard_cost_bc"] * temp_price_unit
                plant_cost_item["standard_cost_cc"] = plant_cost_item["standard_cost_cc"] * temp_price_unit

                # 价格控制为V 无标准价 采购类型不为F 均跳过发布标准成本
                if cost_item.get("price_control", "") == "V" or not plant_cost_item[
                    "standard_cost_bc"] or not plant_dict.get(
                        f'{plant_cost_item["mat_code"]}-{plant_cost_item["plant_code"]}', {}).get("pur_type") != "F":
                    continue

                t_ccb_cost_calculate_allocation = dh.query_sql(
                    f"""select * from t_ccb_cost_calculate_allocation where cost_area = '{plant_cost_item["cost_area"]}'""")
                if t_ccb_cost_calculate_allocation:
                    cost_calculate_type_id = t_ccb_cost_calculate_allocation[0]["cost_calculate_type_id"]
                else:
                    cost_calculate_type_id = ""

                component_data = dh.query_sql(f"""
                select * from `t_co_cost_structure_component` 
                left join t_co_cost_structure using(cost_area, structure_id)
                where `cost_area` = '{plant_cost_item['cost_area']}' and if_actived = 1
                """)
                component_dict = {i["mat_cost_classify"]: i for i in component_data if i["mat_cost_classify"]}

                if not component_dict.get(plant_cost_item["mat_cost_classify"], {}):
                    raise ItfBizError(f"物料{mat_code}工厂{plant_cost_item['plant_code']}的物料成本分类未在秘火成本组件结构中维护")

                std_header = {
                    "cost_area": plant_cost_item["cost_area"],
                    "plant_code": plant_cost_item["plant_code"],
                    "company_code": plant_cost_item["company_code"],
                    "prd_mat_code": mat_code,
                    "mat_description": basic["description"],
                    "cost_version": plant_cost_item["cost_version"],
                    "plant_val_mark": 1,
                    "cost_uom": plant_cost_item["cost_uom"],
                    "basic_uom": plant_cost_item["basic_uom"],
                    "cost_calculate_type_id": cost_calculate_type_id,
                    "cost_amount": plant_cost_item["standard_cost_bc"],
                    "price_unit": plant_cost_item["price_unit"],
                    "cost_lot": plant_cost_item["price_unit"],
                    "currency": plant_cost_item["basic_currency"],
                    "effective_start_date": plant_cost_item["cost_date"],
                    "cost_date": plant_cost_item["cost_date"],
                    "post_date": plant_cost_item["cost_date"],
                    "effective_end_date": "9999-12-31",
                    "status": "A",
                    "transfer_mark": "S",
                    "error_msg": "计算成功",
                    "calc_mode": 1,
                    "cost_comp_prop2": component_dict.get(plant_cost_item["mat_cost_classify"], {}).get(
                        "cost_comp_prop2", ""),
                    "std_cost_code": plant_cost_item["year"] + plant_cost_item["period"] + "ERPINPUT" + plant_cost_item[
                        "plant_code"] + plant_cost_item["cost_date"] + mat_code,
                }

                std_header_data.append(std_header)

                for layer in [0, 1]:
                    component = {
                        "company_code": plant_cost_item["company_code"],
                        "plant_code": plant_cost_item["plant_code"],
                        "std_cost_code": std_header["std_cost_code"],
                        "cost_version": plant_cost_item["cost_version"],
                        "prd_mat_code": mat_code,
                        "cost_date": plant_cost_item["cost_date"],
                        "plant_val_mark": 1,
                        "cost_lot": plant_cost_item["price_unit"],
                        "cost_comp_grp1": component_dict.get(plant_cost_item["mat_cost_classify"], {}).get(
                            "cost_comp_grp1", ""),
                        "grp1_desc": component_dict.get(plant_cost_item["mat_cost_classify"], {}).get("grp1_desc", ""),
                        "cost_comp_grp2": component_dict.get(plant_cost_item["mat_cost_classify"], {}).get(
                            "cost_comp_grp2", ""),
                        "grp2_desc": component_dict.get(plant_cost_item["mat_cost_classify"], {}).get("grp2_desc", ""),
                        "cost_comp_id": component_dict.get(plant_cost_item["mat_cost_classify"], {}).get("cost_comp_id",
                                                                                                         ""),
                        "cost_comp_prop1": component_dict.get(plant_cost_item["mat_cost_classify"], {}).get(
                            "cost_comp_prop1", ""),
                        "cost_comp_prop2": component_dict.get(plant_cost_item["mat_cost_classify"], {}).get(
                            "cost_comp_prop2", ""),
                        "cost_origin": component_dict.get(plant_cost_item["mat_cost_classify"], {}).get("cost_origin",
                                                                                                        ""),
                        "total_cost_cc": plant_cost_item["standard_cost_cc"],
                        "total_cost_bc": plant_cost_item["standard_cost_bc"],
                        "standard_cost_cc": plant_cost_item["standard_cost_cc"],
                        "standard_cost_bc": plant_cost_item["standard_cost_bc"],
                        "calc_mode": 1,
                        "layer": layer,
                        "mat_cost_classify": plant_cost_item["mat_cost_classify"],
                        "price_unit": plant_cost_item["price_unit"]
                    }

                    item = {
                        "company_code": plant_cost_item["company_code"],
                        "plant_code": plant_cost_item["plant_code"],
                        "std_cost_code": std_header["std_cost_code"],
                        "cost_version": plant_cost_item["cost_version"],
                        "prd_mat_code": mat_code,
                        "cost_date": plant_cost_item["cost_date"],
                        "plant_val_mark": 1,
                        "cost_lot": plant_cost_item["price_unit"],
                        "sub_item": 1,
                        "cost_element": component_dict.get(plant_cost_item["mat_cost_classify"], {}).get("cost_element",
                                                                                                         ""),
                        "cost_comp_id": component_dict.get(plant_cost_item["mat_cost_classify"], {}).get("cost_comp_id",
                                                                                                         ""),
                        "cost_comp_text": component_dict.get(plant_cost_item["mat_cost_classify"], {}).get(
                            "cost_comp_text", ""),
                        "cost_comp_prop1": component_dict.get(plant_cost_item["mat_cost_classify"], {}).get(
                            "cost_comp_prop1", ""),
                        "cost_comp_prop2": component_dict.get(plant_cost_item["mat_cost_classify"], {}).get(
                            "cost_comp_prop2", ""),
                        "cost_origin": component_dict.get(plant_cost_item["mat_cost_classify"], {}).get("cost_origin",
                                                                                                        ""),
                        "standard_cost": plant_cost_item["standard_cost_bc"],
                        "currency_code": plant_cost_item["basic_currency"],
                        "price_unit": plant_cost_item["price_unit"],
                        "quantity": 1,
                        "mat_cost_classify": plant_cost_item["mat_cost_classify"],
                        "basic_uom": plant_cost_item["basic_uom"],
                        "cost_uom": plant_cost_item["cost_uom"],
                        "mat_code": mat_code,
                        "plant_val_class": plant_cost_item["plant_val_class"],
                        "calc_mode": 1,
                        "layer": layer,
                        "cost_level": 1,
                        "unit_plan_cost": plant_cost_item["standard_cost_bc"],
                        "bom_key": layer
                    }

                    std_component.append(component)
                    std_item.append(item)

                dh.exec_sql(f"""
                    update t_co_standard_cost_header
                    set status = "W", transfer_mark = ""
                    where plant_code = '{std_header["plant_code"]}'
                    and prd_mat_code = '{std_header["prd_mat_code"]}'
                    and effective_start_date = '{std_header["effective_start_date"]}'
                    and status = 'A'
                    and transfer_mark = 'S'
                """)

                status = dh.exec_sql(f"""
                    delete from t_co_standard_cost_header
                    where std_cost_code = '{std_header["std_cost_code"]}'
                """)
                if status:
                    dh.exec_sql(f"""
                        delete from t_co_standard_component
                        where std_cost_code = '{std_header["std_cost_code"]}'
                    """)

                    dh.exec_sql(f"""
                        delete from t_co_standard_cost_items
                        where std_cost_code = '{std_header["std_cost_code"]}'
                    """)

        status = dh.batchInsertToDB("t_mmd_material_plant_cost_data", plant_cost_data, user_id=user_id,
                                    DuplicateSQLKey=[list(plant_cost_data[0].keys())])
        if status == -1:
            raise ItfBizError("生成物料主数据工厂成本视图失败")
        status = dh.batchInsertToDB("t_co_standard_cost_header", std_header_data, user_id=user_id)
        if status == -1:
            raise ItfBizError("生成标准成本抬头失败")
        status = dh.batchInsertToDB("t_co_standard_component", std_component, user_id=user_id)
        if status == -1:
            raise ItfBizError("生成标准成本组件失败")
        status = dh.batchInsertToDB("t_co_standard_cost_items", std_item, user_id=user_id)
        if status == -1:
            raise ItfBizError("生成标准成本明细失败")

    except Exception as e:
        code = "E" if code != 200 else 500
        msg = f"生成标准成本失败: {e}"
        dh.dbRollback()
        print(f"异常信息: {str(e)}")
        print(f"堆栈跟踪:\n{traceback.format_exc()}")

    return code, msg