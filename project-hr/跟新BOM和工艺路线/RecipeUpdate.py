#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@File    : RecipeUpdate.py
@Author  : tao.chang@dxdstech.com
@Date    : 2024/10/22 10:43
@explain : 通过选择的工艺条件去更新BOM和工艺路线
"""
import json
from datetime import datetime

import pandas as pd
from DbHelper import DbHelper
from libenhance import Callback, Request
from logger import LoggerConfig
from SystemHelper import SystemHelper
from ToolsMethods import ResetResponse, ResponseData
from ZZEXT_RecipeUpdate import get_operation_header

logger = LoggerConfig("CreateBatchInvoice", isStream=True)


SUCCESS_STATUS = {
    1:'全部更新成功',
    2:'部分更新成功',
    3:'全部更新失败'
}

class BomAlloc:
    def __init__(self, plant_code, mat_code, bom_group, bom_group_counter, item_no, deleted_mark, locked_mark,
                 **kwargs):
        self.plant_code = plant_code
        self.mat_code = mat_code
        self.bom_group = bom_group
        self.bom_group_counter = bom_group_counter
        self.item_no = item_no
        self.deleted_mark = deleted_mark
        self.locked_mark = locked_mark
        # 遍历kwargs，将所有键值对设置为实例属性
        for key, value in kwargs.items():
            setattr(self, key, value)


class NewBomHeader():
    def __init__(self, bom_group, bom_group_counter, bom_type, bom_cat, bom_class, bom_status, basic_qty,
                 basic_uom, assembly_loss_rate, bom_description, bom_version_type, bom_version,
                 plant_code, remarks_1, remarks_2, effective_start_date,
                 effective_end_date, deleted_mark, locked_mark, routing_group, routing_group_serial_number, **kwargs):
        self.bom_group = bom_group
        self.bom_group_counter = bom_group_counter
        self.bom_type = bom_type
        self.bom_cat = bom_cat
        self.bom_class = bom_class
        self.bom_status = bom_status
        # self.bom_plan_group = bom_plan_group
        self.basic_qty = basic_qty
        self.basic_uom = basic_uom
        self.assembly_loss_rate = assembly_loss_rate
        self.bom_description = bom_description
        self.bom_version_type = bom_version_type
        self.bom_version = bom_version
        # self.prod_code = prod_code
        # self.related_vendor = related_vendor
        # self.sort_code = sort_code
        # self.tech_doc = tech_doc
        self.plant_code = plant_code
        self.remarks_1 = remarks_1
        self.remarks_2 = remarks_2
        self.effective_start_date = effective_start_date
        self.effective_end_date = effective_end_date
        self.deleted_mark = deleted_mark
        self.locked_mark = locked_mark
        self.routing_group = routing_group
        self.routing_group_serial_number = routing_group_serial_number
        # 遍历kwargs，将所有键值对设置为实例属性
        for key, value in kwargs.items():
            setattr(self, key, value)


class BomHeader():
    def __init__(self, bom_group, bom_group_counter, routing_group, routing_group_serial_number, basic_uom, **kwargs):
        self.bom_group = bom_group
        self.bom_group_counter = bom_group_counter
        self.routing_group = routing_group
        self.routing_group_serial_number = routing_group_serial_number
        self.basic_uom = basic_uom
        # 遍历kwargs，将所有键值对设置为实例属性
        for key, value in kwargs.items():
            setattr(self, key, value)


class BomItem():
    def __init__(self, bom_group, bom_group_counter, routing_group, routing_group_serial_number, **kwargs):
        self.bom_group = bom_group
        self.bom_group_counter = bom_group_counter
        self.routing_group = routing_group
        self.routing_group_serial_number = routing_group_serial_number
        # 遍历kwargs，将所有键值对设置为实例属性
        for key, value in kwargs.items():
            setattr(self, key, value)


class NewBomItem():
    def __init__(self, bom_group, bom_group_counter, effective_start_date, effective_end_date, recipe_id, recipe_code,
                 item_category, item_no, component_number, related_process, sub_group, ratio, component_code,
                 component_qty,
                 component_uom, cost_mark, remarks_1, create_id, **kwargs):
        self.bom_group = bom_group
        self.bom_group_counter = bom_group_counter
        self.effective_start_date = effective_start_date
        self.effective_end_date = effective_end_date
        self.recipe_id = recipe_id
        self.recipe_code = recipe_code
        self.item_category = item_category
        self.item_no = item_no
        self.component_number = component_number
        self.related_process = related_process
        self.sub_group = sub_group
        self.ratio = ratio
        self.component_code = component_code
        self.component_qty = component_qty
        self.component_uom = component_uom
        self.cost_mark = cost_mark
        self.remarks_1 = remarks_1
        self.create_id = create_id
        # 遍历kwargs，将所有键值对设置为实例属性
        for key, value in kwargs.items():
            setattr(self, key, value)


class Operation:
    def __init__(self, plant_code, routing_group, routing_group_serial_number, item_no, operation_number,
                 recipe_id, recipe_code, sub_recipe_id, work_center, wbs_elements=None, profit_center=None, **kwargs):
        self.plant_code = plant_code
        self.routing_group = routing_group
        self.routing_group_serial_number = routing_group_serial_number
        self.item_no = item_no
        self.operation_number = operation_number
        self.recipe_id = recipe_id
        self.recipe_code = recipe_code
        if sub_recipe_id != False:
            self.sub_recipe_id = sub_recipe_id
        self.work_center = work_center
        if wbs_elements:
            self.wbs_elements = wbs_elements
        if profit_center:
            self.profit_center = profit_center
        # self.effective_start_date = effective_start_date
        # self.effective_end_date = effective_end_date
        # 遍历kwargs，将所有键值对设置为实例属性
        for key, value in kwargs.items():
            setattr(self, key, value)


class OperationActReason:
    def __init__(self, routing_group, bom_group_counter, operation_number, act_reason_code, activity_quantity,
                 act_reason_unit_code, formula_code, **kwargs):
        self.routing_group = routing_group
        self.bom_group_counter = bom_group_counter
        self.operation_number = operation_number
        self.act_reason_code = act_reason_code
        self.act_reason_unit_code = act_reason_unit_code
        self.formula_code = formula_code
        self.activity_quantity = activity_quantity
        # 遍历kwargs，将所有键值对设置为实例属性
        for key, value in kwargs.items():
            setattr(self, key, value)


class ReturnData:
    def __init__(self, routing_group, routing_group_serial_number, execute_status, message_text, update_method, item_no,
                 operation_number, plant_code,
                 work_center, description, operation_description,
                 operation_qty,
                 operation_unit, recipe_code,
                 sub_recipe_code="", sun_gx_description="", **kwargs):
        self.routing_group = routing_group
        self.routing_group_serial_number = routing_group_serial_number
        self.execute_status = execute_status
        self.message_text = message_text
        self.update_method = update_method
        self.item_no = item_no
        self.operation_number = operation_number
        self.plant_code = plant_code
        self.work_center = work_center
        self.description = description
        self.operation_description = operation_description
        self.operation_qty = operation_qty
        self.operation_unit = operation_unit
        self.recipe_code = recipe_code
        self.sub_recipe_code = sub_recipe_code
        self.sun_gx_description = sun_gx_description
        # 遍历kwargs，将所有键值对设置为实例属性
        for key, value in kwargs.items():
            setattr(self, key, value)


@ResetResponse(params=["type", "condition", "plant_code", "work_center"])
def getDropDownList(type, condition, plant_code, work_center, **kwargs):
    """
    下拉框
    :param type:
    :param condition:
    :param plant_code:
    :param work_center:
    :return:
    """
    if type == "recipe":
        sql = f"""SELECT `recipe_id`, MAX(`recipe_code`) AS `recipe_code` from `t_eq_recipe_activity_header` WHERE `plant_code`="{plant_code}" and `work_center` = "{work_center}" and `valid_state`="1" GROUP BY `recipe_id` """
        db = DbHelper()
        data_ret = db.query_sql(sql)
        return ResponseData(200, "成功", data_ret)
    else:
        return ResponseData(400, f"不支持的类型[{type}]", [])


"""
根据表t_rgt_routing_operation中字段recipe_code从t_eq_recipe_activity_header找到N条数据，
如果只找出了一条，就不做处理
如果找出多条那就走以下逻辑

依次检查找出数据中的work_center如果和t_rgt_routing_operation表中的work_center相同的，则不复制该条数据，


如果筛选后的数据recipe_code和work_center与t_rgt_routing_operation表中的数据相同，也不复制这条数据


将筛选后的数据存入t_rgt_routing_operation

"""

@ResetResponse(params=["plant_code", "mat_code", "no_update"], excelName="Recipe数据")
def searchData(plant_code, mat_code, no_update, **kwargs):
    """
    查询Recipe主数据
    :param plant_code:
    :param mat_code:
    :return:
    """
    display = [
        {"field": "bom_msg", "description": "BOM更新状态"},
        {"field": "routing_msg", "description": "ROUTING更新状态"},
        {"field": "mat_code", "description": "物料编码"},
        {"field": "mat_description", "description": "物料描述"},
        {"field": "plant_code", "description": "工厂代码"},
        {"field": "routing_group", "description": "工艺路线组号"},
        {"field": "routing_group_serial_number", "description": "组计数器"},
        {"field": "routing_desc", "description": "工艺路线描述"},
        {"field": "routing_type", "description": "类型"},
        {"field": "routing_usage", "description": "用途"},
        {"field": "routing_status", "description": "状态"},
        {"field": "minimum_lot_size", "description": "从批量"},
        {"field": "maximum_lot_size", "description": "到批量"},
        {"field": "header_unit", "description": "单位"},
        {"field": "call_date", "description": "上次调用日期"},
        {"field": "num_of_used", "description": "调用次数"},
        {"field": "effective_start_date", "description": "有效开始日期"},
        {"field": "effective_end_date", "description": "有效截止日期"},
        {"field": "remarks_1", "description": "备注信息1"},
        {"field": "remarks_2", "description": "备注信息2"},
        {"field": "deleted_mark", "description": "删除标识"},
        {"field": "create_time", "description": "创建日期"},
        {"field": "user_name", "description": "创建者"},
    ]
    if no_update == "0":
        sql = f"""SELECT
                      `h`.`plant_code`,
                      `h`.`routing_group`,
                      `h`.`routing_group_serial_number`,
                      `h`.`routing_desc`,
                      `h`.`routing_type`,
                      `h`.`routing_usage`,
                      `h`.`routing_status`,
                      `h`.`minimum_lot_size`,
                      `h`.`maximum_lot_size`,
                      `h`.`header_unit`,
                      DATE_FORMAT(`h`.`call_date`, '%Y-%m-%d %H:%i:%s') AS `call_date`,
                      `h`.`num_of_used`,
                      DATE_FORMAT(`h`.`effective_start_date`, '%Y-%m-%d %H:%i:%s') AS `effective_start_date`,
                      DATE_FORMAT(`h`.`effective_end_date`, '%Y-%m-%d %H:%i:%s') AS `effective_end_date`,
                      `h`.`remarks_1`,
                      `h`.`remarks_2`,
                      `h`.`deleted_mark`,
                      DATE_FORMAT(`h`.`create_time`, '%Y-%m-%d %H:%i:%s') AS `create_time`,
                      `u`.`name` as user_name,
                      DATE_FORMAT(`h`.`update_time`, '%Y-%m-%d %H:%i:%s') AS `update_time`,
                      `a`.`mat_code`,
                      `b`.`mat_description`
                    FROM
                      `t_rgt_routing_header` `h`
                      Right JOIN `t_rgt_routing_allocation` `a` 
                          ON `h`.`routing_group` = `a`.`routing_group` 
                          AND `h`.`routing_group_serial_number` = `a`.`routing_group_serial_number`
                      LEFT JOIN `t_mmd_material_basic_data` `b` on `a`.`mat_code`=`b`.`mat_code`
                      LEFT JOIN `t_system_user` `u` on `u`.`id` = `h`.`create_id`
                    WHERE `h`.`plant_code`='{plant_code}' and `a`.`deleted_mark` != '1' and `h`.`deleted_mark` != 1
                """
        print(sql, 'sql----')
    else:
        sql = f"""SELECT
                              `h`.`plant_code`,
                              `h`.`routing_group`,
                              `h`.`routing_group_serial_number`,
                              `h`.`routing_desc`,
                              `h`.`routing_type`,
                              `h`.`routing_usage`,
                              `h`.`routing_status`,
                              `h`.`minimum_lot_size`,
                              `h`.`maximum_lot_size`,
                              `h`.`header_unit`,
                              DATE_FORMAT(`h`.`call_date`, '%Y-%m-%d %H:%i:%s') AS `call_date`,
                              `h`.`num_of_used`,
                              DATE_FORMAT(`h`.`effective_start_date`, '%Y-%m-%d %H:%i:%s') AS `effective_start_date`,
                              DATE_FORMAT(`h`.`effective_end_date`, '%Y-%m-%d %H:%i:%s') AS `effective_end_date`,
                              `h`.`remarks_1`,
                              `h`.`remarks_2`,
                              `h`.`deleted_mark`,
                              DATE_FORMAT(`h`.`create_time`, '%Y-%m-%d %H:%i:%s') AS `create_time`,
                              `u`.`name` as `user_name`,
                              DATE_FORMAT(`h`.`update_time`, '%Y-%m-%d %H:%i:%s') AS `update_time`,
                              `a`.`mat_code`,
                              `b`.`mat_description`
                            FROM
                              `t_rgt_routing_header` `h`
                              Right JOIN `t_rgt_routing_allocation` `a` 
                                  ON `h`.`routing_group` = `a`.`routing_group` 
                                  AND `h`.`routing_group_serial_number` = `a`.`routing_group_serial_number`
                              LEFT JOIN `t_mmd_material_basic_data` `b` on `a`.`mat_code`=`b`.`mat_code`
                              LEFT JOIN `t_system_user` `u` on `u`.`id` = `h`.`create_id`
                            WHERE `h`.`plant_code`='{plant_code}' and (`h`.`remarks_1` = '' or  `h`.`remarks_2` = '') and `a`.`deleted_mark` != 1 and `h`.`deleted_mark` != 1
                        """
        print(sql, 'sql====')

    if mat_code:
        if isinstance(mat_code, str):
            sql += f" AND `a`.`mat_code` = '{mat_code}'"
        if isinstance(mat_code, list):
            if len(mat_code) == 1:
                sql += f" AND `a`.`mat_code` = '{mat_code[0]}'"
            else:
                mat_code = [repr(i) for i in mat_code]
                sql += f" AND `a`.`mat_code` in ({','.join(mat_code)})"

    db = DbHelper()
    data_ret = db.query_sql(sql)

    return ResponseData(200, "成功", data_ret, display=display)


@ResetResponse(params=["type", "plant_code", "data"])
def updateData(type, plant_code, data, **kwargs):
    """
    执行更新数据
    :param type:
    :param plant_code:
    :param data:
    :return:
    """
    req = Request()
    user_id = req.header("user_id")
    if type == "BOM":
        # 检查数据
        cheak_list = []
        for i in data:
            if i.get("mat_code") not in cheak_list:
                cheak_list.append(i.get("mat_code"))
            else:
                return ResponseData(400, "同一物料编码仅能选择一条工艺路线更新BOM，请重新选择", [])
        ret = updateBOMSetupA(plant_code, data, user_id)
        return ret
    elif type == "Routing":
        # 按 recipe_code 在 t_eq_recipe_activity_header 命中多个 work_center 时, 先展开工序行
        expand_routing_operation_by_work_center(plant_code, data, user_id)
        ret = updateRouting(plant_code, data, user_id)
        return ret
    else:
        return ResponseData(400, "该类型不支持更新", [])

def expand_routing_operation_by_work_center(plant_code, data, user_id):
    """按 recipe_code 在 t_eq_recipe_activity_header 命中多个 work_center 时, 为每个新 work_center
    复制一条 t_rgt_routing_operation: 整行照抄原行, 只把 work_center 换成 header 命中的值;
    排除原工序本身的 work_center。新行 id 自增, item_no/operation_number 重新生成(唯一索引 IDX_t_rgt_routing_operation_uniqe_number 强制), 其余字段照抄原行。

    逻辑:
      1. 按 routing_group + routing_group_serial_number 在 t_rgt_routing_operation 找工序;
      2. 拿每条工序的 recipe_code 去 t_eq_recipe_activity_header 找 recipe_code 一致的数据(可能多条);
      3. 命中的 work_center 与该工序原 work_center 相同则不复制;
      4. 其余整行复制, 只改 work_center, 存入 t_rgt_routing_operation。
    """

    def _to_int(v):
        # operation_number 是 varchar, 安全转 int(空/非数字 -> 0); 数据库侧 CAST AS UNSIGNED 会报"无效的数据类型"
        try:
            return int(str(v).strip())
        except (ValueError, TypeError):
            return 0

    db = DbHelper()
    insert_list = []
    writeback_list = (
        []
    )  # (routing_group, routing_group_serial_number): 复制成功后反写 remarks=X

    for item in data:
        routing_group = item.get("routing_group")
        routing_group_serial_number = item.get("routing_group_serial_number")
        if routing_group is None or routing_group_serial_number is None:
            continue

        # 0. 先查 t_rgt_routing_header.remarks: ==X 表示该工序已复制过, 跳过; !=X 才执行复制
        chk = db.query_sql(
            f"""SELECT `remarks` FROM `t_rgt_routing_header`
                WHERE `routing_group`='{routing_group}'
                  AND `routing_group_serial_number`='{routing_group_serial_number}'
                LIMIT 1 """,
            isNewDB=True,
        )
        if chk and (chk[0].get("remarks") or "") == "X":
            continue

        # 1. 按 routing_group + routing_group_serial_number 找工序(整行取出, 复制时改 work_center + 序号)
        ops = db.query_sql(f"""SELECT * FROM `t_rgt_routing_operation`
                WHERE `plant_code`='{plant_code}'
                  AND `routing_group`='{routing_group}'
                  AND `routing_group_serial_number`='{routing_group_serial_number}'
                ORDER BY `item_no` ASC """)
        if not ops:
            continue

        # 当前最大序号(从已取出的 ops 计算, 复制行生成新 item_no/operation_number, 避免撞唯一索引):
        # operation_number 是 varchar, 数据库侧 CAST AS UNSIGNED 报"无效的数据类型", 改在 Python 里转 int
        max_item_no = max((op.get("item_no") or 0) for op in ops)
        max_op_no = max((_to_int(op.get("operation_number")) for op in ops), default=0)

        seq = 0
        for op in ops:
            recipe_code = op.get("recipe_code")
            if not recipe_code:
                continue
            # 2. 拿工序的 recipe_code 去 header 找一致的数据(可能多条 work_center)
            # [{'work_center': 'NZ1RC000'}, {'work_center': 'NZ1RC000'}, {'work_center': '99999'}, {'work_center': 'NZ1RC000'}, {'work_center': '99999'}, {'work_center': 'A2355'}]
            headers = db.query_sql(
                f"""SELECT `work_center` FROM `t_eq_recipe_activity_header`
                    WHERE `recipe_code`='{recipe_code}'
                      AND `plant_code`='{plant_code}'
                      AND `valid_state`='1' """
            )
            # 3. 先对命中的 work_center 去重(同一 work_center 多条 header 只复制一次), 再逐个处理
            for h_work_center in dict.fromkeys(h.get("work_center") for h in headers):
                # work_center 与当前工序相同则不复制该条
                if h_work_center == op.get("work_center"):
                    continue
                # 4. 整行复制: 改 work_center, 重新生成 item_no/operation_number(唯一索引强制); 其余字段照抄原行
                seq += 1
                new_op = {**op}
                new_op.pop("id", None)
                new_op["work_center"] = h_work_center
                new_op["item_no"] = max_item_no + seq
                new_op["operation_number"] = max_op_no + seq
                insert_list.append(new_op)

        # 该 routing 复制流程已执行, 标记待反写 remarks=X(执行成功后统一回写)
        writeback_list.append((routing_group, routing_group_serial_number))

    # 按 (recipe_code, work_center) 对 insert_list 去重: 不同工序命中相同 recipe_code 会产生重复组合, 只插一条
    seen = set()
    _deduped = []
    for row in insert_list:
        key = (row.get("recipe_code"), row.get("work_center"))
        if key in seen:
            continue
        seen.add(key)
        _deduped.append(row)
    insert_list = _deduped

    # 将筛选后的数据存入 t_rgt_routing_operation
    # 注: 该库不支持 INSERT ... ON DUPLICATE KEY UPDATE(报"无法在源表中获得一组稳定的行"),
    #     故不用 DuplicateSQLKey, 用普通 INSERT。
    if insert_list:
        db.batchInsertToDB(
            "t_rgt_routing_operation", insert_list, user_id=user_id, printSql=True
        )
        db.updateDBObj()
        print(
            f"expand_routing_operation_by_work_center 新增工序行数: {len(insert_list)}"
        )

    # 执行工序成功后, 反写 remarks=X 到 t_rgt_routing_header(标记已复制, 下次跳过)
    for rg, rgsn in writeback_list:
        try:
            db.exec_sql(
                f"""UPDATE `t_rgt_routing_header` SET `remarks`='X'
                    WHERE `routing_group`='{rg}' AND `routing_group_serial_number`='{rgsn}' """,
                isNewDB=True,
            )
            db.updateDBObj()
        except Exception as e:
            print(f"[expand] 反写 remarks=X 失败 rg={rg} rgsn={rgsn}: {e}")


@ResetResponse(params=["type", "plant_code", "routing_group", "routing_group_serial_number"],
               excelName="Recipe更新状态详细数据")
def searchUpdateStatus(type, plant_code, routing_group, routing_group_serial_number, **kwargs):
    """
    查询更新状态
    :param type:
    :param plant_code:
    :param routing_group:
    :param routing_group_serial_number:
    :return:
    """
    display = [
        {"field": "execute_status", "description": "执行状态"},
        {"field": "message_text", "description": "执行状态消息文本"},
        {"field": "operation_number", "description": "工序号"},
        {"field": "plant_code", "description": "工厂"},
        {"field": "work_center", "description": "工作中心"},
        {"field": "work_center_desc", "description": "工作中心描述"},
        {"field": "operation_description", "description": "工序描述"},
        {"field": "operation_qty", "description": "数量"},
        {"field": "operation_unit", "description": "单位"},
        {"field": "recipe_code", "description": "工艺条件码"},
        {"field": "sub_recipe_id", "description": "替代工艺条件编码"},
        {"field": "sub_recipe_code", "description": "替代工艺条件码"},
    ]
    if type in ["BOM", "Routing"]:
        ret = dbUpdateStatus(type, plant_code, routing_group, routing_group_serial_number)
        return ResponseData(200, "成功", ret, display=display)
    else:
        return ResponseData(400, "该类型不支持更新", [])


@ResetResponse(isSave=True)
def saveData(insert, update, delete, **kwargs):
    """
    更新operation 替代Recipe
    :param type:
    :param insert:
    :param update:
    :param delete:
    :return:
    """
    # if type == "BOM":
    logger.printInfo("update", update)
    if update:
        db = DbHelper()
        for i in update:
            if "id" in i:
                del i["id"]
        db.batchInsertToDB("t_rgt_routing_operation", dataList=update, DuplicateSQLKey=["sub_recipe_id"], printSql=True)
        db.updateDBObj()

    # elif type == "Routing":
    #     if update:
    #         db = DbHelper()
    #         db.batchInsertToDB("t_rgt_routing_operation", dataList=update, DuplicateSQLKey=["sub_recipe_id"])
    #         db.updateDBObj()
    return ResponseData(200, "成功", [], [])


@ResetResponse(params=[])
def autoUpdate(**kwargs):
    cbk = Callback()
    print(cbk.param())
    body = json.loads(cbk.param())
    plant_code = body.get("plant_code")
    print("开始自动执行：",plant_code)
    sql = f"""
                    SELECT
                         `h`.`plant_code`,
                         `h`.`routing_group`,
                         `h`.`routing_group_serial_number`,
                         `h`.`routing_desc`,
                         `h`.`routing_type`,
                         `h`.`routing_usage`,
                         `h`.`routing_status`,
                         `h`.`minimum_lot_size`,
                         `h`.`maximum_lot_size`,
                         `h`.`header_unit`,
                         DATE_FORMAT(`h`.`call_date`, '%Y-%m-%d %H:%i:%s') AS `call_date`,
                         `h`.`num_of_used`,
                         DATE_FORMAT(`h`.`effective_start_date`, '%Y-%m-%d %H:%i:%s') AS `effective_start_date`,
                         DATE_FORMAT(`h`.`effective_end_date`, '%Y-%m-%d %H:%i:%s') AS `effective_end_date`,
                         `h`.`remarks_1`,
                         `h`.`remarks_2`,
                         `h`.`deleted_mark`,
                         DATE_FORMAT(`h`.`create_time`, '%Y-%m-%d %H:%i:%s') AS `create_time`,
                         `u`.`name` as `user_name`,
                         DATE_FORMAT(`h`.`update_time`, '%Y-%m-%d %H:%i:%s') AS `update_time`,
                         `a`.`mat_code`,
                         `b`.`mat_description`
                       FROM
                       (
                       SELECT 
                            `routing_group`,
                            `routing_group_serial_number`,
                            `mat_code`,
                            `plant_code`
                        FROM (
                            SELECT 
                                `routing_group`, 
                                `routing_group_serial_number`, 
                                `mat_code`, 
                                `plant_code`,
                                RANK() OVER (PARTITION BY `plant_code`, `mat_code` ORDER BY `routing_group` DESC, `routing_group_serial_number` DESC) AS `rnk`
                            FROM 
                                `t_rgt_routing_allocation`
                            WHERE 
                                `plant_code` = '{plant_code}'
                        ) AS `bom_alloc_ranked`
                            WHERE 
                            `bom_alloc_ranked`.`rnk` = 1
                            ) as  `a`
                         LEFT JOIN `t_rgt_routing_header` `h` 
                             ON `h`.`routing_group` = `a`.`routing_group` 
                             AND `h`.`routing_group_serial_number` = `a`.`routing_group_serial_number`
                         LEFT JOIN `t_mmd_material_basic_data` `b` on `a`.`mat_code`=`b`.`mat_code`
                         LEFT JOIN `t_system_user` `u` on `u`.`id` = `h`.`create_id`
                       WHERE `h`.`plant_code`='{plant_code}' and (`h`.`remarks_1` = '' or  `h`.`remarks_2` = '')
                    """
    sh = SystemHelper()
    user_id = sh.getUserId()
    print("user_id：",user_id)
    db = DbHelper()
    data_ret = db.query_sql(sql)
    print("data_ret",len(data_ret))
    ret = updateBOMSetupA(plant_code, data_ret, user_id)
    if ret.code != 200:
        return ret
    ret = updateRouting(plant_code, data_ret, user_id)
    return ret


def updateBOMSetupA(plant_code, dataList, user_id):
    """
    更新BOM 步骤A
    :param plant_code:
    :param dataList:
    :return:
    """
    display = [
        {"field": "bom_msg", "description": "BOM更新状态"},
        {"field": "mat_code", "description": "物料编码"},
        {"field": "mat_description", "description": "物料描述"},
        {"field": "plant_code", "description": "工厂代码"},
        {"field": "routing_group", "description": "工艺路线组号"},
        {"field": "bom_group_counter", "description": "组计数器"},
    ]
    responseDataList = []
    db = DbHelper()
    routing_header_status_list = []
    print(dataList)
    for data in dataList:
        print(data)
        # 校验数据是否存在
        routing_group_serial_number = (t := data.get('routing_group_serial_number')) is not None and str(t) or data.get(
            'bom_group_counter')
        print(routing_group_serial_number, "routing_group_serial_number-=-=")
        clear_recipe_update_status(plant_code, data["routing_group"], routing_group_serial_number, "BOM")
        sql0 = f"""
              SELECT * from  `t_bom_alloc` WHERE `mat_code` = '{data['mat_code']}' AND `plant_code` = '{plant_code}'
        """
        print(routing_group_serial_number, "routing_group_serial_number-=-=")
        logger.printInfo("sql0", sql0)
        ret0 = db.query_sql(sql0)
        if not ret0:
            data["bom_msg"] = f"请维护物料编码{data['mat_code']}BOM主材数据！"
            data["bom_status"] = "E"
            responseDataList.append(data)
            continue
        sql1 = f"""
            SELECT
              `a`.`plant_code`,
              `a`.`bom_group`,
              `a`.`bom_group_counter`,
              `a`.`mat_code`,
              `h`.`routing_group`,
              `h`.`routing_group_serial_number`,
              `h`.`basic_qty`,
              `h`.`basic_uom`
            FROM
              `t_bom_alloc` `a`
              JOIN `t_bom_header` `h` ON `a`.`bom_group` = `h`.`bom_group`
              AND `a`.`bom_group_counter` = `h`.`bom_group_counter`
            WHERE `a`.`plant_code` = '{plant_code}'
            and `a`.`mat_code`= '{data["mat_code"]}'
            and `h`.`routing_group`={data["routing_group"]}
            and `h`.`routing_group_serial_number`={routing_group_serial_number};
        """
        ret1 = db.query_sql(sql1)
        logger.printInfo("ret1", ret1)
        print(sql1, 'sql1---')
        if ret1:
            # 执行步骤B
            for ret1Data in ret1:
                retReturnData = updateBOMItemSetupB(plant_code=plant_code, routing_group=data["routing_group"],
                                                    routing_group_serial_number=routing_group_serial_number,
                                                    bom_group=ret1Data["bom_group"],
                                                    bom_group_counter=ret1Data["bom_group_counter"],
                                                    header_basic_qty=float(ret1Data["basic_qty"]), user_id=user_id,
                                                    basic_uom=ret1Data["basic_uom"])
                if retReturnData.get("success"):

                    data["bom_msg"] = SUCCESS_STATUS.get(retReturnData.get("all_success_flag"),'未获取到更新信息')
                    data["bom_status"] = "S" if retReturnData.get("all_success_flag") == 1 else "W"
                    responseDataList.append(data)
                    db.batchInsertToDB("t_co_recipe_update_status", retReturnData.get("data"), isNewDB=True)
                    # db.updateDBObj()
                    routing_header_status_list.append({"plant_code": plant_code, "routing_group": data["routing_group"],
                                                       "routing_group_serial_number": routing_group_serial_number,
                                                       "remarks_1": "BOM"})

                else:
                    data["bom_msg"] = retReturnData.get("msg")
                    data["bom_status"] = "E"
                    responseDataList.append(data)
        else:
            sql2 = f"""
                        SELECT
                          `a`.`plant_code`,
                          `a`.`bom_group`,
                          `a`.`bom_group_counter`,
                          `a`.`mat_code`,
                          `a`.`item_no`,
--                           `a`.`deleted_mark`,
--                           `a`.`locked_mark`,
                          `h`.`routing_group`,
                          `h`.`routing_group_serial_number`,
                          `h`.`bom_type`,
                          `h`.`bom_cat`,
                          `h`.`bom_class`,
                          `h`.`bom_status`,
--                           `h`.`bom_plan_group`,
                          `h`.`basic_qty`,
                          `h`.`basic_uom`,
                          `h`.`assembly_loss_rate`,
                          `h`.`bom_description`,
                          `h`.`bom_version_type`,
                          `h`.`bom_version`,
--                           `h`.`prod_code`,
--                           `h`.`related_vendor`,
--                           `h`.`sort_code`,
--                           `h`.`tech_doc`,
                          `h`.`plant_code`,
                          `h`.`remarks_1`,
                          `h`.`remarks_2`,
                          `h`.`effective_start_date`,
                          `h`.`effective_end_date`,
                          `h`.`deleted_mark`,
                          `h`.`lock_flag`
                        FROM
                          `t_bom_alloc` `a`
                          JOIN `t_bom_header` `h` ON `a`.`bom_group` = `h`.`bom_group` 
                          AND `a`.`bom_group_counter` = `h`.`bom_group_counter` 
                        WHERE
                          `a`.`plant_code` = '{plant_code}' 
                          AND `a`.`mat_code` = '{data["mat_code"]}' 
                          AND `h`.`routing_group` != {data["routing_group"]} 
                          AND `h`.`routing_group_serial_number` != {routing_group_serial_number}
                          AND `a`.`bom_group` = ( SELECT MAX( `bom_group` ) FROM `t_bom_alloc` WHERE `plant_code` = '{plant_code}' AND `mat_code` = '{data["mat_code"]}' ) 
                        ORDER BY
                          `a`.`bom_group_counter` DESC 
                          LIMIT 1;
                    """
            print(sql2, 'sql2')
            ret2 = db.query_sql(sql2)
            logger.printInfo("ret2", ret2)
            if ret2:
                retData = ret2[0]
                print(retData, 'retData-=-=-=')
                if not retData["routing_group"] and not retData["routing_group"]:
                    # 执行步骤B
                    retReturnData = updateBOMItemSetupB(plant_code=plant_code, routing_group=data["routing_group"],
                                                        routing_group_serial_number=routing_group_serial_number,
                                                        bom_group=retData["bom_group"],
                                                        bom_group_counter=retData["bom_group_counter"],
                                                        header_basic_qty=float(retData["basic_qty"]), user_id=user_id,
                                                        basic_uom=retData["basic_uom"])
                    logger.printInfo("retReturnData", retReturnData)
                    if retReturnData.get("success"):
                        data["bom_msg"] = SUCCESS_STATUS.get(retReturnData.get("all_success_flag"), '未获取到更新信息')
                        data["bom_status"] = "S" if retReturnData.get("all_success_flag") == 1 else "W"
                        responseDataList.append(data)
                        db.batchInsertToDB("t_co_recipe_update_status", retReturnData.get("data"), isNewDB=True,
                                           printSql=True)
                        # db.updateDBObj()
                        routing_header_status_list.append(
                            {"plant_code": plant_code, "routing_group": data["routing_group"],
                             "routing_group_serial_number": routing_group_serial_number, "remarks_1": "BOM"})

                    else:
                        data["bom_msg"] = retReturnData.get("msg")
                        data["bom_status"] = "E"
                        responseDataList.append(data)
                else:
                    new_group_counter = retData["bom_group_counter"] + 1
                    bomAllocObj = BomAlloc(plant_code=plant_code, mat_code=retData["mat_code"],
                                           bom_group=retData["bom_group"],
                                           bom_group_counter=new_group_counter, item_no=retData["item_no"],
                                           deleted_mark=retData["deleted_mark"], locked_mark=retData["lock_flag"])
                    db.batchInsertToDB("t_bom_alloc", [bomAllocObj.__dict__], printSql=True)
                    db.updateDBObj()

                    newBomHeaderObj = NewBomHeader(bom_group=retData["bom_group"], bom_group_counter=new_group_counter,
                                                   bom_type=retData["bom_type"], bom_cat=retData["bom_cat"],
                                                   bom_class=retData["bom_class"],
                                                   bom_status=retData["bom_status"],
                                                   basic_qty=retData["basic_qty"], basic_uom=retData["basic_uom"],
                                                   assembly_loss_rate=retData["assembly_loss_rate"],
                                                   bom_description=retData["bom_description"],
                                                   bom_version=retData["bom_version"],
                                                   bom_version_type=retData["bom_version_type"],
                                                   # prod_code=retData["prod_code"],
                                                   # related_vendor=retData["related_vendor"],
                                                   # sort_code=retData["sort_code"],
                                                   # tech_doc=retData["tech_doc"],
                                                   plant_code=plant_code,
                                                   remarks_1=retData["remarks_1"],
                                                   remarks_2=retData["remarks_2"],
                                                   effective_start_date=retData["effective_start_date"],
                                                   effective_end_date=retData["effective_end_date"],
                                                   deleted_mark=retData["deleted_mark"],
                                                   locked_mark=retData["lock_flag"], routing_group="",
                                                   routing_group_serial_number="")
                    db.batchInsertToDB("t_bom_header", [newBomHeaderObj.__dict__], printSql=True)
                    db.updateDBObj()

                    # sql4 = f""" SELECT
                    #               *
                    #             FROM
                    #               t_bom_item
                    #             WHERE
                    #               plant_code = "{plant_code}"
                    #               AND bom_group = {retData["bom_group"]}
                    #               AND bom_group_counter = {new_group_counter}
                    #                """
                    sql4 = f""" SELECT
                                  * 
                                FROM
                                  `t_bom_item` 
                                WHERE
                                    `bom_group` = {retData["bom_group"]} 
                                  AND `bom_group_counter` = {new_group_counter}
                                   """
                    print(sql4)
                    ret4 = db.query_sql(sql4)
                    newBomItemList = []
                    for dataItem in ret4:
                        newBomItem = NewBomItem(
                            bom_group=dataItem["bom_group"],
                            bom_group_counter=new_group_counter,
                            effective_start_date=dataItem["effective_start_date"],
                            effective_end_date=dataItem["effective_end_date"],
                            recipe_id=dataItem["recipe_id"],
                            recipe_code=dataItem["recipe_code"],
                            item_category=dataItem.get("bom_item_category") or dataItem.get("item_category"),
                            related_process=dataItem["related_process"],
                            sub_group=dataItem["sub_group"],
                            ratio=dataItem["ratio"],
                            component_code=dataItem["component_code"],
                            component_qty=dataItem["component_qty"],
                            component_uom=dataItem["component_uom"],
                            cost_mark=dataItem["cost_mark"],
                            remarks_1=dataItem["remarks_1"],
                            item_no=dataItem["item_no"],
                            component_number=dataItem["component_number"], create_id=user_id, update_id=user_id)
                        newBomItemList.append(newBomItem.__dict__)

                    db.batchInsertToDB("t_bom_item", newBomItemList, batch_size=50, printSql=True)
                    db.updateDBObj()

                    # 执行步骤B
                    retReturnData = updateBOMItemSetupB(plant_code=plant_code, routing_group=data["routing_group"],
                                                        routing_group_serial_number=routing_group_serial_number,
                                                        bom_group=retData["bom_group"],
                                                        bom_group_counter=new_group_counter,
                                                        header_basic_qty=float(retData["basic_qty"]), user_id=user_id,
                                                        basic_uom=retData["basic_uom"])
                    if retReturnData.get("success"):
                        data["bom_msg"] = SUCCESS_STATUS.get(retReturnData.get("all_success_flag"), '未获取到更新信息')
                        data["bom_status"] = "S" if retReturnData.get("all_success_flag") == 1 else "W"
                        responseDataList.append(data)
                        db.batchInsertToDB("t_co_recipe_update_status", retReturnData.get("data"), isNewDB=True,
                                           printSql=True)
                        # db.updateDBObj()
                        routing_header_status_list.append(
                            {"plant_code": plant_code, "routing_group": data["routing_group"],
                             "routing_group_serial_number": routing_group_serial_number, "remarks_1": "BOM"})

                    else:
                        data["bom_msg"] = retReturnData.get("msg")
                        data["bom_status"] = "E"
                        responseDataList.append(data)
            else:
                ...
    update_routing_header_status(routing_header_status_list, DuplicateSQLKey=["remarks_1"])
    print("responseDataList>>>", responseDataList)
    return ResponseData(200, "成功", responseDataList, display)


def updateBOMItemSetupB(plant_code, routing_group, routing_group_serial_number, bom_group, bom_group_counter,
                        header_basic_qty, user_id, basic_uom):
    """
    更新BOM 步骤B
    :param plant_code:
    :param routing_group:
    :param routing_group_serial_number:
    :param bom_group:
    :param bom_group_counter:
    :param header_basic_qty:
    :return:
    """
    clearBomItem(bom_group, bom_group_counter)
    newResponseData = []
    bomHeaderDict = {}
    db = DbHelper()
    matching_fields = get_recipe_matching_fields_db(plant_code)
    if not matching_fields:
        return {"success": False, "msg": f"请维护工厂{plant_code}工艺条件匹配表！"}
    failed_cont = 0
    sql = f"""SELECT
                m.`plant_code`,
                m.`work_center`,
                wc.`work_center_desc`,
                m.`recipe_id`,
                m.`recipe_code`,
--                 m.`module_id`,
                m.`item_no`,
                m.`equipment_id`,
--                 m.`capacode`,
--                 m.`chamber`,
                m.`sub_recipe_id`,
                m.`operation_number`,
                m.`operation_description`,
                m.`operation_qty`,
                m.`operation_unit`
              FROM
                `t_rgt_routing_operation` m
                LEFT JOIN `t_co_work_center_main_data` wc on m.`work_center`=wc.`work_center` and m.`plant_code`=wc.`plant_code`
                where m.`plant_code` = '{plant_code}' and m.`routing_group`='{routing_group}' 
                and m.`routing_group_serial_number`='{routing_group_serial_number}' """
    logger.printInfo("operationRet-sql", sql)
    operationRet = db.query_sql(sql)
    logger.printInfo("operationRet", operationRet)
    logger.printInfo("matching_fields", matching_fields)
    if operationRet:
        for operation in operationRet:
            nodata_flag = False
            recipe_header = {}
            update_operation_flag = False
            for index, fileds in enumerate(matching_fields):
                whereSql = "Where 1=1 "
                for i in fileds:
                    if i == "recipe_code":
                        value = operation[i].replace("\\", "\\\\")
                    else:
                        value = operation[i]
                    whereSql += f"and `h`.`{i}`='{value}' "
                operation_header_sql = f"""
                                        SELECT
                                             `h`.`plant_code`,
                                             `h`.`work_center`,
                                             wc.`work_center_desc`,
                                             `h`.`recipe_id`,
                                             `h`.`perbaseline`,
                                             `h`.`basic_uom`,
                                             `h`.`bom_flag`,
                                             `h`.`recipe_code`,
                                             `h`.`effective_start_date`
                                           FROM
                                              `t_eq_recipe_activity_header` `h` 
                                            LEFT JOIN `t_co_work_center_main_data` wc on `h`.`work_center`=wc.`work_center` and `h`.`plant_code`=wc.`plant_code`
                                            {whereSql} and `h`.`valid_state`='1' 
                                        """
                logger.printInfo("operation_header_sql", operation_header_sql)
                recipe_header_ret = db.query_sql(operation_header_sql)
                logger.printInfo("recipe_header_ret", recipe_header_ret)
                if recipe_header_ret:
                    recipe_header = recipe_header_ret[0]
                    nodata_flag = False
                    if index != 0:
                        update_operation_flag = True
                    break
                else:
                    nodata_flag = True
                    continue
            logger.printInfo("nodata_flag", nodata_flag)
            if nodata_flag:
                recipe_header_ret = get_operation_header(db,operation)
                logger.printInfo("recipe_header_ret", recipe_header_ret)
                if recipe_header_ret:
                    recipe_header = recipe_header_ret[0]
                    update_operation_flag = True
                else:
                    sub_recipe_sql = f"""
                         SELECT
                             `h`.`plant_code`,
                             `h`.`work_center`,
                             wc.`work_center_desc`,
                             `h`.`recipe_id`,
                             `h`.`perbaseline`,
                             `h`.`basic_uom`,
                             `h`.`bom_flag`,
                             `h`.`recipe_code`,
                             `h`.`effective_start_date`
                           FROM
                              `t_eq_recipe_activity_header` `h` 
                            LEFT JOIN `t_co_work_center_main_data` wc on `h`.`work_center`=wc.`work_center` and `h`.`plant_code`=wc.`plant_code`
                            where `h`.`recipe_id`='{operation.get('sub_recipe_id')}' and `h`.`plant_code`='{operation["plant_code"]}' and `h`.`valid_state`='1' 
                    """
                    sub_recipe_ret = db.query_sql(sub_recipe_sql)
                    if sub_recipe_ret:
                        recipe_header = sub_recipe_ret[0]
                        update_operation_flag = True
                    else:
                        recipe_header = {}
            logger.printInfo("recipe_header>>>", recipe_header)
            logger.printInfo("operation", operation)
            logger.printInfo("update_operation_flag", update_operation_flag)
            if update_operation_flag:
                if operation.get("sub_recipe_id"):
                    sub_recipe_id = False
                    DuplicateSQLKey = ["recipe_id", "recipe_code"]
                else:
                    sub_recipe_id = recipe_header.get("recipe_id", "") if recipe_header else operation.get("recipe_id")
                    DuplicateSQLKey = ["recipe_id", "recipe_code", "sub_recipe_id"]
                operationObj = Operation(plant_code=plant_code, routing_group=routing_group,
                                         routing_group_serial_number=routing_group_serial_number,
                                         item_no=operation["item_no"],
                                         operation_number=operation["operation_number"],
                                         recipe_id="",
                                         recipe_code=operation["recipe_code"],
                                         sub_recipe_id=sub_recipe_id,
                                         work_center=recipe_header.get("work_center", ""))
                updateOperation(operationObj.__dict__, DuplicateSQLKey)
            else:
                operationObj = Operation(plant_code=plant_code, routing_group=routing_group,
                                         routing_group_serial_number=routing_group_serial_number,
                                         item_no=operation["item_no"],
                                         operation_number=operation["operation_number"],
                                         recipe_id=recipe_header["recipe_id"] if recipe_header else operation[
                                             "recipe_id"],
                                         recipe_code=operation["recipe_code"],
                                         sub_recipe_id=False,
                                         work_center=operation.get("work_center", ""))
                updateOperation(operationObj.__dict__, ["recipe_id", "recipe_code"])

            if not recipe_header and operation.get("sub_recipe_id") == "":
                failed_cont +=1
                # 新增逻辑也找不到数据的情况下
                retObj = ReturnData(routing_group=routing_group,
                                    routing_group_serial_number=routing_group_serial_number,
                                    execute_status="E",
                                    message_text=f"""请维护工艺条件{operation["recipe_code"]}主数据！""",
                                    update_method="BOM",
                                    item_no=operation["item_no"],
                                    operation_number=operation["operation_number"],
                                    plant_code=plant_code,
                                    work_center=operation["work_center"],
                                    description=operation["work_center_desc"],
                                    operation_description=operation["operation_description"],
                                    operation_qty=operation["operation_qty"],
                                    operation_unit=operation["operation_unit"],
                                    recipe_code=operation["recipe_code"])
                newResponseData.append(retObj.__dict__)
                continue

            # nodata_flag = False
            # logger.printInfo("recipe_header", recipe_header)
            recipe_id = recipe_header.get("recipe_id")
            logger.printInfo("recipe_id", recipe_id)
            if recipe_id:
                item_sql = f"""
                                SELECT 
                                  `i`.`sub_group` ,
                                  `i`.`percent`,
                                  `i`.`mat_code`,
                                  `i`.`cost_qty`,
                                  `i`.`cost_uom`,
                                  `i`.`component_qty_by_basic_uom`,
                                  `i`.`basic_uom` as `item_basic_uom`,
                                  `i`.`cost_mark`,
                                  `i`.`note`, 
                                  `h`.`perbaseline`,
                                  `h`.`basic_uom`,
                                  `h`.`recipe_id`,
                                  `h`.`bom_flag`,
                                  `h`.`recipe_code`,
                                  `h`.`effective_start_date`,
                                  `h`.`perbaseline`
                                FROM
                                  `t_eq_recipe_bom_items` `i`
                                  INNER JOIN `t_eq_recipe_activity_header` `h` ON `i`.`plant_code` = `h`.`plant_code` 
                                  AND `i`.`recipe_id` = `h`.`recipe_id` 
                                WHERE
                                  `h`.`plant_code` = '{plant_code}' 
                                  AND `i`.`recipe_id` = '{recipe_id}' and `h`.`valid_state`='1' 
                                """
            else:
                sub_recipe_id = operation["sub_recipe_id"]
                logger.printInfo("sub_recipe_id", sub_recipe_id)
                if not sub_recipe_id:
                    failed_cont += 1
                    retObj = ReturnData(routing_group=routing_group,
                                        routing_group_serial_number=routing_group_serial_number,
                                        execute_status="E",
                                        message_text="维护工艺条件主数据",
                                        update_method="BOM",
                                        item_no=operation["item_no"],
                                        operation_number=operation["operation_number"],
                                        plant_code=plant_code,
                                        work_center=recipe_header["work_center"],
                                        description=recipe_header["work_center_desc"],
                                        operation_description=operation["operation_description"],
                                        operation_qty=operation["operation_qty"],
                                        operation_unit=operation["operation_unit"],
                                        recipe_code=operation["recipe_code"])
                    newResponseData.append(retObj.__dict__)
                    continue
                item_sql = f"""
                                   SELECT
                                      `i`.`sub_group`,
                                      `i`.`percent`,
                                      `i`.`mat_code`,
                                      `i`.`cost_qty`,
                                      `i`.`cost_uom`,
                                      `i`.`component_qty_by_basic_uom`,
                                      `i`.`basic_uom` as `item_basic_uom`,
                                      `i`.`cost_mark`,
                                      `i`.`note`,
                                      `h`.`perbaseline`,
                                      `h`.`basic_uom`,
                                      `h`.`recipe_id`,
                                      `h`.`recipe_code`,
                                      `h`.`bom_flag`,
                                      `h`.`effective_start_date`,
                                      `h`.`perbaseline` 
                                    FROM
                                      `t_eq_recipe_bom_items` as `i` 
                                      INNER JOIN `t_eq_recipe_activity_header` as `h` ON `i`.`plant_code` = `h`.`plant_code` 
                                      AND `i`.`recipe_id` = `h`.`recipe_id` 
                                    WHERE
                                      `h`.`plant_code` = '{plant_code}' 
                                      AND `i`.`recipe_id` = '{sub_recipe_id}'
                               """
            recipe_item_list = db.query_sql(item_sql)
            logger.printInfo("item_sql", item_sql)
            logger.printInfo("recipe_item_list", recipe_item_list)
            if recipe_item_list:
                newBomItemList = []
                for recipe in recipe_item_list:
                    if recipe.get("bom_flag") == "1":
                        logger.printInfo("getBomItemMaxNo(bom_group, bom_group_counter)",
                                         getBomItemMaxNo(bom_group, bom_group_counter))
                        newBomItem = NewBomItem(bom_group=bom_group,
                                                bom_group_counter=bom_group_counter,
                                                effective_start_date=recipe.get("effective_start_date"),
                                                effective_end_date="9999-12-31",
                                                recipe_id=recipe.get("recipe_id"),
                                                recipe_code=recipe.get("recipe_code"),
                                                # 根据产品设计代码写死-[bom_item_category="L"]
                                                item_category="L",
                                                related_process=operation.get("operation_number"),
                                                sub_group=recipe.get("sub_group"),
                                                ratio=recipe.get("percent"),
                                                component_code=recipe.get("mat_code"),
                                                component_qty=recipe.get(
                                                    "cost_qty") / recipe.get("perbaseline",
                                                                             1) * header_basic_qty,
                                                component_uom=recipe.get("cost_uom"),
                                                cost_mark=recipe.get("cost_mark"),
                                                remarks_1=recipe.get("note"),
                                                item_no=getBomItemMaxNo(bom_group, bom_group_counter),
                                                component_number=getBomItemMaxSn(bom_group, bom_group_counter),
                                                create_id=user_id, update_id=user_id
                                                )
                        logger.printInfo("newBomItem.__dict__", newBomItem.__dict__)
                        newBomItemList.append(newBomItem.__dict__)
                        db.batchInsertToDB("t_bom_item", newBomItemList,
                                           DuplicateSQLKey=["bom_group", "bom_group_counter", "sub_group", "item_no",
                                                            "component_number", "component_code"], isNewDB=True,
                                           printSql=True)
                        db.updateDBObj()

                        bomHeader = BomHeader(bom_group=bom_group, bom_group_counter=bom_group_counter,
                                              routing_group=routing_group,
                                              routing_group_serial_number=routing_group_serial_number,
                                              basic_uom=basic_uom)
                        bomHeaderDict[f"{bom_group}-{bom_group_counter}"]=bomHeader.__dict__
                    else:
                        ...

                retObj = ReturnData(routing_group=routing_group,
                                    routing_group_serial_number=routing_group_serial_number,
                                    execute_status="S",
                                    message_text="成功",
                                    update_method="BOM",
                                    item_no=operation["item_no"],
                                    operation_number=operation["operation_number"],
                                    plant_code=plant_code,
                                    work_center=recipe_header.get("work_center"),
                                    description=recipe_header.get("work_center_desc"),
                                    operation_description=operation["operation_description"],
                                    operation_qty=operation["operation_qty"],
                                    operation_unit=operation["operation_unit"],
                                    recipe_code=operation["recipe_code"])
                newResponseData.append(retObj.__dict__)
            else:
                if recipe_header:
                    if str(recipe_header.get("bom_flag")) != "0":
                        status_str = f"成功"
                        retObj = ReturnData(routing_group=routing_group,
                                            routing_group_serial_number=routing_group_serial_number,
                                            execute_status="S",
                                            message_text=status_str,
                                            update_method="BOM",
                                            item_no=operation["item_no"],
                                            operation_number=operation["operation_number"],
                                            plant_code=plant_code,
                                            work_center=recipe_header.get("work_center"),
                                            description=recipe_header.get("work_center_desc"),
                                            operation_description=operation["operation_description"],
                                            operation_qty=operation["operation_qty"],
                                            operation_unit=operation["operation_unit"],
                                            recipe_code=operation["recipe_code"])
                        newResponseData.append(retObj.__dict__)
                    else:
                        failed_cont += 1
                        status_str = f"维护{operation['recipe_code']}"
                        retObj = ReturnData(routing_group=routing_group,
                                            routing_group_serial_number=routing_group_serial_number,
                                            execute_status="E",
                                            message_text=status_str,
                                            update_method="BOM",
                                            item_no=operation["item_no"],
                                            operation_number=operation["operation_number"],
                                            plant_code=plant_code,
                                            work_center=recipe_header.get("work_center"),
                                            description=recipe_header.get("work_center_desc"),
                                            operation_description=operation["operation_description"],
                                            operation_qty=operation["operation_qty"],
                                            operation_unit=operation["operation_unit"],
                                            recipe_code=operation["recipe_code"])
                        newResponseData.append(retObj.__dict__)
                else:
                    failed_cont += 1
                    status_str = f"维护{operation['recipe_code']}"
                    retObj = ReturnData(routing_group=routing_group,
                                        routing_group_serial_number=routing_group_serial_number,
                                        execute_status="E",
                                        message_text=status_str,
                                        update_method="BOM",
                                        item_no=operation["item_no"],
                                        operation_number=operation["operation_number"],
                                        plant_code=plant_code,
                                        work_center=recipe_header.get("work_center"),
                                        description=recipe_header.get("work_center_desc"),
                                        operation_description=operation["operation_description"],
                                        operation_qty=operation["operation_qty"],
                                        operation_unit=operation["operation_unit"],
                                        recipe_code=operation["recipe_code"])
                    newResponseData.append(retObj.__dict__)
        logger.printInfo("bomHeaderDict", bomHeaderDict)
        if bomHeaderDict:
            db.batchInsertToDB("t_bom_header", list(bomHeaderDict.values()),
                               DuplicateSQLKey=["routing_group_serial_number", "routing_group", "basic_uom"],
                               isNewDB=True, printSql=True)
            db.updateDBObj()
        if failed_cont:
            if failed_cont == len(operationRet):
                success_flag = 3
            else:
                success_flag = 2
        else:
            success_flag = 1
        return {"success": True, "all_success_flag": success_flag, "data": newResponseData}
    else:
        return {"success": False, "msg": f"请维护工艺路线工序数据"}

    # for fileds in matching_fields:
    #     onsql = ""
    #     for i in fileds:
    #         onsql += f"m.{i} = a.{i} and "
    #     onsql = onsql.strip("and ")
    #     sql = f"""SELECT
    #                  m.work_center,
    #                  wc.work_center_desc,
    #                  m.recipe_code,
    #                  m.module_id,
    #                  m.item_no,
    #                  m.equipment_id,
    #                  m.capacode,
    #                  m.chamber,
    #                  m.sub_recipe_id,
    #                  m.operation_number,
    #                  m.operation_description,
    #                  m.operation_qty,
    #                  m.operation_unit,
    #                  a.plant_code,
    #                  a.recipe_id,
    #                  a.perbaseline,
    #                  a.basic_uom,
    #                  a.recipe_code
    #                FROM
    #                  t_rgt_routing_operation m
    #                  LEFT JOIN t_eq_recipe_activity_header `a` ON {onsql}
    #                  LEFT JOIN t_co_work_center_main_data wc on a.work_center=wc.work_center
    #                  where m.plant_code = "{plant_code}" and m.routing_group="{routing_group}"
    #                  and m.bom_group_counter="{routing_group_serial_number}" """
    #     operation_ret = db.query_sql(sql)
    #     if operation_ret:
    #         for operation in operation_ret:
    #             recipe_id = operation["recipe_id"]
    #             if recipe_id:
    #                 item_sql = f"""
    #                     SELECT
    #                       i.sub_group ,
    #                       i.alternative_mat_rate ,
    #                       i.mat_code,
    #                       i.cost_qty,
    #                       i.cost_uom,
    #                       i.cost_mark,
    #                       i.general_notes,
    #                       h.perbaseline,
    #                       h.basic_uom,
    #                       h.recipe_id,
    #                       h.recipe_code,
    #                     FROM
    #                       t_eq_recipe_bom_items i
    #                       LEFT JOIN t_eq_recipe_activity_header `h` ON i.plant_code = h.plant_code
    #                       AND i.recipe_id = h.recipe_id
    #                     WHERE
    #                       i.plant_code = "{plant_code}"
    #                       AND h.recipe_id = {recipe_id}
    #                 """
    #             else:
    #                 sub_recipe_id = operation["sub_recipe_id"]
    #                 if not sub_recipe_id:
    #                     success_flag = False
    #                     retObj = ReturnData(routing_group=routing_group, bom_group_counter=routing_group_serial_number,
    #                                         execute_status=f"E-维护工艺条件主数据", update_method="BOM",
    #                                         item_no=operation["item_no"],
    #                                         operation_number=operation["operation_number"],
    #                                         plant_code=plant_code,
    #                                         work_center=operation["work_center"],
    #                                         description=operation["work_center_desc"],
    #                                         operation_description=operation["operation_description"],
    #                                         operation_qty=operation["operation_qty"],
    #                                         operation_unit=operation["operation_unit"],
    #                                         recipe_code=operation["recipe_code"])
    #                     newResponseData.append(retObj.__dict__)
    #                     continue
    #                 item_sql = f"""
    #                    SELECT
    #                       i.sub_group,
    #                       i.alternative_mat_rate,
    #                       i.mat_code,
    #                       i.cost_qty,
    #                       i.cost_uom,
    #                       i.cost_mark,
    #                       i.general_notes,
    #                       h.perbaseline,
    #                       h.basic_uom,
    #                       h.recipe_id,
    #                       h.recipe_code,
    #                       h.effective_start_date
    #                     FROM
    #                       t_eq_recipe_bom_items i
    #                       LEFT JOIN t_eq_recipe_activity_header `h` ON i.plant_code = h.plant_code
    #                       AND i.recipe_id = h.recipe_id
    #                     WHERE
    #                       i.plant_code = "{plant_code}"
    #                       AND h.recipe_id = {sub_recipe_id}
    #                """
    #             recipe_item_list = db.query_sql(item_sql)
    #             if recipe_item_list:
    #                 newBomItemList = []
    #                 for recipe in recipe_item_list:
    #                     newBomItem = NewBomItem(bom_group=bom_group,
    #                                             bom_group_counter=bom_group_counter,
    #                                             effective_start_date=recipe.get(
    #                                                 "effective_start_date"),
    #                                             effective_end_date="9999-12-31",
    #                                             recipe_id=recipe.get("recipe_id"),
    #                                             recipe_code=recipe.get("recipe_code"),
    #                                             bom_item_category="L",
    #                                             related_process=operation.get("operation_number"),
    #                                             sub_group=recipe.get("sub_group"),
    #                                             ratio=recipe.get("alternative_mat_rate"),
    #                                             component_code=recipe.get("mat_code"),
    #                                             component_qty=operation.get("perbaseline", 0) * header_basic_qty,
    #                                             component_uom=recipe.get("cost_uom"),
    #                                             cost_mark=recipe.get("cost_mark"),
    #                                             remarks_1=recipe.get("general_notes"),
    #                                             item_no=getBomItemMaxNo(bom_group, bom_group_counter),
    #                                             component_number=getBomItemMaxSn(bom_group, bom_group_counter),
    #                                             )
    #                     newBomItemList.append(newBomItem.__dict__)
    #                     db.batchInsertToDB("t_bom_item", newBomItemList)
    #
    #                     bomHeader = BomHeader(bom_group=bom_group, bom_group_counter=bom_group_counter,
    #                                           routing_group=routing_group, routing_group_serial_number=routing_group_serial_number)
    #                     bomHeaderList.append(bomHeader.__dict__)
    #
    #                 retObj = ReturnData(routing_group=routing_group, bom_group_counter=routing_group_serial_number,
    #                                     execute_status="S-成功", update_method="BOM", item_no=operation["item_no"],
    #                                     operation_number=operation["operation_number"],
    #                                     plant_code=plant_code,
    #                                     work_center=operation["work_center"],
    #                                     description=operation["work_center_desc"],
    #                                     operation_description=operation["operation_description"],
    #                                     operation_qty=operation["operation_qty"],
    #                                     operation_unit=operation["operation_unit"],
    #                                     recipe_code=operation["recipe_code"])
    #                 newResponseData.append(retObj.__dict__)
    #             else:
    #                 success_flag = False
    #                 retObj = ReturnData(routing_group=routing_group, bom_group_counter=routing_group_serial_number,
    #                                     execute_status=f"E-维护工艺条件{operation['recipe_code']}主数据", update_method="BOM",
    #                                     item_no=operation["item_no"],
    #                                     operation_number=operation["operation_number"],
    #                                     plant_code=plant_code,
    #                                     work_center=operation["work_center"],
    #                                     description=operation["work_center_desc"],
    #                                     operation_description=operation["operation_description"],
    #                                     operation_qty=operation["operation_qty"],
    #                                     operation_unit=operation["operation_unit"],
    #                                     recipe_code=operation["recipe_code"])
    #                 newResponseData.append(retObj.__dict__)
    #         if bomHeaderList:
    #             db.batchInsertToDB("t_bom_header", bomHeaderList)
    #         return {"success": True, "all_success_flag": success_flag, "data": newResponseData}
    #     else:
    #         nodata_flag = True
    #
    # if nodata_flag:
    #     return {"success": False, "msg": f"维护工艺路线工序数据"}


def updateRouting(plant_code, dataList, user_id):
    """
    更新工艺路线
    :param plant_code:
    :param dataList:
    :return:
    """
    wbs_profit_center_dict = get_wbs_profit_center()

    display = [
        {"field": "routing_msg", "description": "ROUTING更新状态"},
        {"field": "mat_code", "description": "物料编码"},
        {"field": "mat_description", "description": "物料描述"},
        {"field": "plant_code", "description": "工厂代码"},
        {"field": "routing_group", "description": "工艺路线组号"},
        {"field": "bom_group_counter", "description": "组计数器"},
    ]
    db = DbHelper()
    matching_fields = get_recipe_matching_fields_db(plant_code)
    responseDataList = []
    logger.printInfo("dataList", dataList)
    routing_header_status_list = []
    if matching_fields:

        for group_data in dataList:
            # 是否全部更新标识

            failed_count = 0
            newResponseData = []
            routing_group = group_data["routing_group"]
            routing_group_serial_number = group_data["routing_group_serial_number"]
            # 更新之前清除上一次更新的状态表
            clear_recipe_update_status(plant_code, routing_group, routing_group_serial_number, "Routing")
            routing_operation_sql = f"""SELECT
                          m.`plant_code`,
                          m.`work_center`,
                          wc.`work_center_desc`,
                          m.`recipe_id`,
                          m.`recipe_code`,
--                           m.`module_id`,
                          m.`equipment_id`,
--                           m.`capacode`,
--                           m.`chamber`,
                          m.`sub_recipe_id`,
                          m.`operation_qty`,
                          m.`operation_unit`,
                          m.`operation_number`,
                          m.`operation_description`,
                          m.`item_no`,
                          m.`effective_start_date`,
                          m.`effective_end_date`
                        FROM
                          `t_rgt_routing_operation` m
                          LEFT JOIN `t_co_work_center_main_data` wc on m.`work_center`=wc.`work_center` and m.`plant_code`=wc.`plant_code`
                        WHERE
                          m.`plant_code` = '{plant_code}' 
                          AND m.`routing_group` = '{routing_group}' 
                          AND m.`routing_group_serial_number` = '{routing_group_serial_number}'
                                        """
            routing_operation_ret = db.query_sql(routing_operation_sql)
            logger.printInfo("routing_operation_ret", routing_operation_ret)
            # clear_act_reason(routing_group, routing_group_serial_number)
            if routing_operation_ret:

                for operation in routing_operation_ret:
                    nodata_flag = False
                    activity_header = {}
                    update_operation_flag = False
                    # 是否第一个优先级找到数据
                    index_find_flag = True
                    for index, fileds in enumerate(matching_fields):
                        whereSql = "Where 1=1 "
                        for i in fileds:
                            if i == "recipe_code":
                                value = operation[i].replace("\\","\\\\")
                            else:
                                value = operation[i]
                            whereSql += f"and `h`.`{i}`='{value}' "
                        activity_header_sql = f"""
                                        SELECT
                                             `h`.`plant_code`,
                                             `h`.`work_center`,
                                             wc.`work_center_desc`,
                                             `h`.`recipe_id`,
                                             `h`.`perbaseline`,
                                             `h`.`basic_qty`,
                                             `h`.`basic_uom`,
                                             `h`.`recipe_code`,
                                             `h`.`activity_flag`
                                           FROM
                                              `t_eq_recipe_activity_header` `h` 
                                            LEFT JOIN `t_co_work_center_main_data` wc on `h`.`work_center`=wc.`work_center` and `h`.`plant_code`=wc.`plant_code`
                                            {whereSql} and `h`.`valid_state`='1' 
                                            """
                        print("activity_header_sql>>>",activity_header_sql)
                        activity_header_ret = db.query_sql(activity_header_sql)
                        if activity_header_ret:
                            nodata_flag = False
                            activity_header = activity_header_ret[0]
                            if index != 0:
                                index_find_flag = False
                                update_operation_flag = True
                            break
                        else:
                            nodata_flag = True
                            continue
                    logger.printInfo("nodata_flag", nodata_flag)
                    if nodata_flag:
                        activity_header_ret = get_operation_header(db,operation)
                        logger.printInfo("activity_header_ret", activity_header_ret)
                        if activity_header_ret:
                            index_find_flag = False
                            activity_header = activity_header_ret[0]
                            update_operation_flag = True
                        else:
                            activity_header = {}
                    logger.printInfo("activity_header", activity_header)
                    if not activity_header and operation.get("sub_recipe_id") == "":
                        failed_count += 1
                        # 新增逻辑也找不到数据的情况下
                        retObj = ReturnData(routing_group=routing_group,
                                            routing_group_serial_number=routing_group_serial_number,
                                            execute_status="E",
                                            message_text=f"""维护工艺条件{operation["recipe_code"]}数据！""",
                                            update_method="Routing",
                                            item_no=operation["item_no"],
                                            operation_number=operation["operation_number"],
                                            plant_code=plant_code,
                                            work_center=operation["work_center"],
                                            description=operation["work_center_desc"],
                                            operation_description=operation["operation_description"],
                                            operation_qty=operation["operation_qty"],
                                            operation_unit=operation["operation_unit"],
                                            recipe_code=operation["recipe_code"])
                        newResponseData.append(retObj.__dict__)
                        continue
                    logger.printInfo("update_operation_flag", update_operation_flag)
                    if update_operation_flag:
                        operationObj = Operation(plant_code=plant_code, routing_group=routing_group,
                                                 routing_group_serial_number=routing_group_serial_number,
                                                 item_no=operation["item_no"],
                                                 operation_number=operation["operation_number"],
                                                 recipe_id=operation["recipe_id"],
                                                 recipe_code=operation["recipe_code"],
                                                 sub_recipe_id="" if operation.get(
                                                     "recipe_id") else activity_header.get("recipe_id", ""),
                                                 work_center=activity_header.get("work_center"),
                                                 wbs_elements=wbs_profit_center_dict.get(
                                                     (group_data.get("plant_code"), group_data.get("mat_code")),
                                                     {}).get("wbs_elements"),
                                                 profit_center=wbs_profit_center_dict.get(
                                                     (group_data.get("plant_code"), group_data.get("mat_code")),
                                                     {}).get("profit_center")

                                                 )
                        operationObjDit = operationObj.__dict__
                        operationObjDit.update({"update_id": user_id})
                        # updateOperation(operationObjDit,
                        #                 DuplicateSQLKey=["recipe_id", "recipe_code", "work_center",
                        #                                  "wbs_elements", "profit_center", "update_id"])
                    else:
                        operationObj = Operation(plant_code=plant_code, routing_group=routing_group,
                                                 routing_group_serial_number=routing_group_serial_number,
                                                 item_no=operation["item_no"],
                                                 operation_number=operation["operation_number"],
                                                 recipe_id=operation.get("recipe_id"),
                                                 recipe_code=operation["recipe_code"],
                                                 sub_recipe_id=False,
                                                 work_center=operation.get("work_center"),
                                                 wbs_elements=wbs_profit_center_dict.get(
                                                     (group_data.get("plant_code"), group_data.get("mat_code")),
                                                     {}).get("wbs_elements"),
                                                 profit_center=wbs_profit_center_dict.get(
                                                     (group_data.get("plant_code"), group_data.get("mat_code")),
                                                     {}).get("profit_center")
                                                 )
                        operationObjDit = operationObj.__dict__
                        operationObjDit.update({"update_id": user_id})
                        # updateOperation(operationObjDit,
                        #                 DuplicateSQLKey=["recipe_id", "recipe_code", "work_center",
                        #                                  "wbs_elements", "profit_center", "update_id"])

                    if activity_header and activity_header.get("activity_flag") != '1':
                        retObj = ReturnData(routing_group=routing_group,
                                            routing_group_serial_number=routing_group_serial_number,
                                            execute_status="S",
                                            message_text="成功",
                                            update_method="Routing",
                                            item_no=operation["item_no"],
                                            operation_number=operation["operation_number"],
                                            plant_code=plant_code,
                                            work_center=activity_header.get("work_center"),
                                            description=activity_header.get("work_center_desc"),
                                            operation_description=operation["operation_description"],
                                            operation_qty=operation["operation_qty"],
                                            operation_unit=operation["operation_unit"],
                                            recipe_code=operation["recipe_code"])
                        newResponseData.append(retObj.__dict__)
                        continue
                    updateRet, update_all_status = updateOperationActReason(plant_code, routing_group,
                                                                            routing_group_serial_number,
                                                                            activity_header.get("recipe_id"),
                                                                            operation["sub_recipe_id"],
                                                                            operation, index_find_flag)
                    newResponseData.extend(updateRet)
                    if not update_all_status:
                        failed_count += 1


                if failed_count:

                    if failed_count == len(routing_operation_ret):
                        update_all_flag = 3
                    else:
                        update_all_flag = 2

                else:
                    update_all_flag = 1

                group_data.update({"routing_msg": SUCCESS_STATUS.get(update_all_flag,'未获取成功信息')})
                group_data.update({"execute_status": "S" if update_all_flag == 1 else "W"})
                responseDataList.append(group_data)
                update_status = db.batchInsertToDB("t_co_recipe_update_status", newResponseData, batch_size=10,
                                                   isNewDB=True, printSql=True)
                db.updateDBObj()
                routing_header_status_list.append({"plant_code": plant_code, "routing_group": routing_group,
                                                   "routing_group_serial_number": routing_group_serial_number,
                                                   "remarks_2": "Routing"})

                count = 1
                while update_status == -1 and count <= 5:
                    count += 1
                    update_status = db.batchInsertToDB("t_co_recipe_update_status", newResponseData,
                                                       batch_size=10, isNewDB=True, printSql=True)
                    # db.updateDBObj()

                main_data_flag = not newResponseData
                if main_data_flag:
                    group_data.update({"routing_msg": "工艺条件无法匹配主数据"})
                    group_data.update({"execute_status": "E"})
                    responseDataList.append(group_data)
            else:
                group_data.update({"routing_msg": "无匹配数据"})
                group_data.update({"execute_status": "E"})
                responseDataList.append(group_data)
        update_routing_header_status(routing_header_status_list, DuplicateSQLKey=["remarks_2"])
        print("responseDataList>>>", responseDataList)
        return ResponseData(200, "执行成功", responseDataList, display=display)

        #     for fileds in matching_fields:
        #         onsql = ""
        #         for i in fileds:
        #             onsql += f"m.{i} = a.{i} and "
        #         onsql = onsql.strip("and ")
        #         sql = f"""SELECT
        #                       m.work_center,
        #                       m.recipe_id,
        #                       m.recipe_code,
        #                       m.module_id,
        #                       m.equipment_id,
        #                       m.capacode,
        #                       m.chamber,
        #                       m.sub_recipe_id,
        #                       m.operation_qty,
        #                       m.operation_unit,
        #                       m.operation_number,
        #                       m.operation_description,
        #                       m.item_no,
        #                       a.basic_qty,
        #                       a.work_center as header_work_center,
        #                       a.effective_start_date,
        #                       m.effective_end_date,
        #                       wc.work_center_desc as wc_desc
        #                     FROM
        #                       t_rgt_routing_operation m
        #                     LEFT JOIN t_eq_recipe_activity_header a
        #                     on {onsql}
        #                     LEFT JOIN t_co_work_center_main_data wc on a.work_center=wc.work_center
        #                     WHERE
        #                       m.plant_code = "{plant_code}"
        #                       AND m.routing_group = "{routing_group}"
        #                       AND m.routing_group_serial_number = "{routing_group_serial_number}"
        #                     """
        #         ret = db.query_sql(sql)
        #         if ret:
        #             for data in ret:
        #                 operationObj = Operation(plant_code, routing_group, routing_group_serial_number, data["item_no"],
        #                                          data["operation_number"],
        #                                          data["recipe_id"], data["header_work_center"],
        #                                          effective_start_date=data["effective_start_date"],
        #                                          effective_end_date=data["effective_end_date"])
        #                 updateOperation(operationObj.__dict__)
        #
        #                 if activity_header.get((plant_code, data["recipe_id"])) != '1':
        #                     retObj = ReturnData(routing_group=routing_group, routing_group_serial_number=routing_group_serial_number,
        #                                         execute_status="S-成功", update_method="Routing", item_no=data["item_no"],
        #                                         operation_number=data["operation_number"],
        #                                         plant_code=plant_code,
        #                                         work_center=data["header_work_center"], description=data["wc_desc"],
        #                                         operation_description=data["operation_description"],
        #                                         operation_qty=data["operation_qty"],
        #                                         operation_unit=data["operation_unit"], recipe_code=data["recipe_code"])
        #                     newResponseData.append(retObj.__dict__)
        #                     continue
        #                 updateRet, update_all_status = updateOperationActReason(plant_code, routing_group,
        #                                                                         routing_group_serial_number,
        #                                                                         data["recipe_id"],
        #                                                                         data["sub_recipe_id"],
        #                                                                         data)
        #                 newResponseData.extend(updateRet)
        #                 if update_all_status == False:
        #                     update_all_flag = False
        #             break
        #
        #     responseDataList.append({f"{routing_group}_{routing_group_serial_number}": newResponseData,
        #                              "execute_status": "全部更新成功" if update_all_flag else "部分更新成功"})
        #     update_status = db.batchInsertToDB("t_co_recipe_update_status", newResponseData, batch_size=10,
        #                                        isNewDB=True)
        #     count = 1
        #     while update_status == -1 and count <= 5:
        #         count += 1
        #         update_status = db.batchInsertToDB("t_co_recipe_update_status", newResponseData, batch_size=10,
        #                                            isNewDB=True)
        #     main_data_flag = not newResponseData
        # if main_data_flag:
        #     return ResponseData(400, "工艺条件XX无法匹配主数据", responseDataList,
        #                         display=display)
        # else:
        #     return ResponseData(200, "执行成功", responseDataList, display=display)
    else:
        return ResponseData(400, "请配置工艺条件匹配表t_eq_recipe_matching_fields", [], display=display)


def dbUpdateStatus(type, plant_code, routing_group, routing_group_serial_number):
    db = DbHelper()
    sql = f""" select `tcrus`.*,`tcwcmd`.`work_center_desc` from `t_co_recipe_update_status` as `tcrus` 
                left join `t_co_work_center_main_data` as `tcwcmd` on `tcrus`.`work_center` = `tcwcmd`.`work_center` and `tcrus`.`plant_code` = `tcwcmd`.`plant_code`
                where `tcrus`.`plant_code` = '{plant_code}' 
                and `tcrus`.`routing_group` = '{routing_group}' 
                and `tcrus`.`routing_group_serial_number` = '{routing_group_serial_number}' 
                and `tcrus`.`update_method` = '{type}'
     """
    return db.query_sql(sql, printSql=True)


def get_recipe_matching_fields_db(plant_code):
    db = DbHelper()
    ret = db.query_sql(
        f"select `plant_code`,`field_name`,`priority_code` from `t_eq_recipe_matching_fields` where `plant_code`='{plant_code}' order by `priority_code` asc ")
    if ret:
        df = pd.DataFrame(ret)
        # 按 'plant_code' 和 'priority_code' 分组，并将 'field_name' 按顺序合并为列表
        ret = df.groupby(['plant_code', 'priority_code'])['field_name'].apply(list).tolist()
    return ret


def updateOperationActReason(plant_code, routing_group, routing_group_serial_number, recipe_id, sub_recipe_id, data,
                             index_find_flag):
    print("updateOperationActReason")
    logger.printInfo("index_find_flag", index_find_flag)
    logger.printInfo("routing_group", routing_group)
    logger.printInfo("routing_group_serial_number", routing_group_serial_number)
    logger.printInfo("recipe_id", recipe_id)
    logger.printInfo("sub_recipe_id", sub_recipe_id)
    logger.printInfo("data", data)
    update_all_flag = True
    returnObj = []
    db = DbHelper()
    if recipe_id:
        sql = f"""
                SELECT
                  `h`.`activity_flag`,
                  `h`.`recipe_id`,
                  `h`.`plant_code`,
                  `h`.`basic_qty`,
                  `h`.`work_center`,
                  wc.`work_center_desc`,
                  it.* 
                FROM
                  `t_eq_recipe_activity_header` `h`
                  LEFT JOIN `t_eq_recipe_activity_items` it ON it.`recipe_id` = `h`.`recipe_id` 
                  AND it.`plant_code` = `h`.`plant_code` 
                  LEFT JOIN `t_co_work_center_main_data` wc on `h`.`work_center`=wc.`work_center`
                WHERE
                  `h`.`recipe_id` = '{recipe_id}' 
                  AND `h`.`plant_code` = '{plant_code}'  and `h`.`valid_state`='1' 
        """
    else:
        sql = f"""
                SELECT
                  `h`.`activity_flag`,
                  `h`.`recipe_id`,
                  `h`.`plant_code`,
                  `h`.`basic_qty`,
                  `h`.`work_center`,
                  wc.`work_center_desc`,
                  it.*
                FROM
                  `t_eq_recipe_activity_header` `h`
                  LEFT JOIN `t_eq_recipe_activity_items` it ON it.`recipe_id` = `h`.`recipe_id` 
                  AND it.`plant_code` = `h`.`plant_code` 
                  LEFT JOIN `t_co_work_center_main_data` wc on `h`.`work_center`=wc.`work_center`
                WHERE
                  `h`.`recipe_id` = '{sub_recipe_id}' 
                  AND `h`.`plant_code` = '{plant_code}'  and `h`.`valid_state`='1' 
                """
    data_ret = db.query_sql(sql)
    if data_ret:
        # clear_act_reason(routing_group, routing_group_serial_number)
        operationActReason = {}
        work_center = data_ret[0]['work_center']
        work_center_desc = data_ret[0]['work_center_desc']
        for index, act_reason_data in enumerate(data_ret):
            if act_reason_data.get('activity_flag') == '1':
                noi = index + 1
                if not operationActReason:
                    operationActReason.update({
                        "routing_group": routing_group,
                        "routing_group_serial_number": routing_group_serial_number,
                        "item_no": data.get("item_no"),
                        "operation_number": data.get("operation_number"),
                        "plant_code": data.get("plant_code")
                    })
                    # clear_operation_act_reason(operationActReason)
                operationActReason.update({
                    f"act_reason_code{noi}": act_reason_data["act_reason_code"],
                    f"act_reason_qty{noi}": act_reason_data["activity_qty"] / act_reason_data.get("basic_qty") * data[
                        "operation_qty"],
                    f"act_reason_uom{noi}": act_reason_data["act_reason_unit_code"],
                }
                )
                # DuplicateSQLKey.append(f"act_reason_code{noi}")
                # DuplicateSQLKey.append(f"act_reason_qty{noi}")
                # DuplicateSQLKey.append(f"act_reason_uom{noi}")
                # operationActReason = OperationActReason(routing_group=routing_group,
                #                                         routing_group_serial_number=routing_group_serial_number,
                #                                         operation_number=data["operation_number"],
                #                                         act_reason_code=act_reason_data["act_reason_code"],
                #                                         activity_quantity=act_reason_data["activity_qty"] / activity_header[
                #                                             "basic_qty"] * data["operation_qty"],
                #                                         act_reason_unit_code=act_reason_data[
                #                                             "act_reason_unit_code"],
                #                                         formula_code="")
                # db.batchInsertToDB("t_rgt_routing_operation_act_reason",
                #                    dataList=[operationActReason.__dict__], isNewDB=True,printSql=True)
                # db.updateDBObj()

        if operationActReason:
            # 清除其他不存在的动因字段数据
            DuplicateSQLKey = [
                "act_reason_code1", "act_reason_qty1", "act_reason_uom1",
                "act_reason_code2", "act_reason_qty2", "act_reason_uom2",
                "act_reason_code3", "act_reason_qty3", "act_reason_uom3",
                "act_reason_code4", "act_reason_qty4", "act_reason_uom4",
                "act_reason_code5", "act_reason_qty5", "act_reason_uom5",
                "act_reason_code6", "act_reason_qty6", "act_reason_uom6",
            ]
            for k in DuplicateSQLKey:
                if k not in operationActReason:
                    if k.startswith("act_reason_code") or k.startswith("act_reason_uom"):
                        operationActReason[k] = ""
                    if k.startswith("act_reason_qty"):
                        operationActReason[k] = 0
            if index_find_flag:
                operationActReason["recipe_id"] = recipe_id
                DuplicateSQLKey.append("recipe_id")
            else:
                operationActReason["sub_recipe_id"] = recipe_id
                DuplicateSQLKey.append("sub_recipe_id")

            updateOperation(operationActReason, DuplicateSQLKey=DuplicateSQLKey)
            retObj = ReturnData(routing_group=routing_group, routing_group_serial_number=routing_group_serial_number,
                                execute_status="S",
                                message_text="成功",
                                update_method="Routing",
                                item_no=data["item_no"],
                                operation_number=data["operation_number"], plant_code=data["plant_code"],
                                work_center=work_center,
                                description=work_center_desc,
                                operation_description=data["operation_description"],
                                operation_qty=data["operation_qty"],
                                operation_unit=data["operation_unit"], recipe_code=data["recipe_code"])
            returnObj.append(retObj.__dict__)
        else:
            retObj = ReturnData(routing_group=routing_group, routing_group_serial_number=routing_group_serial_number,
                                execute_status="S",
                                message_text="处理成功-没有动因更新",
                                update_method="Routing",
                                item_no=data["item_no"],
                                operation_number=data["operation_number"], plant_code=data["plant_code"],
                                work_center=work_center,
                                description=work_center_desc,
                                operation_description=data["operation_description"],
                                operation_qty=data["operation_qty"],
                                operation_unit=data["operation_unit"], recipe_code=data["recipe_code"])
            returnObj.append(retObj.__dict__)
    else:
        if data["sub_recipe_id"]:
            return updateOperationActReason(plant_code, routing_group, routing_group_serial_number, None,
                                            data["sub_recipe_id"],
                                            data, index_find_flag)
        retObj = ReturnData(routing_group=routing_group, routing_group_serial_number=routing_group_serial_number,
                            execute_status="E",
                            message_text="找不到工艺条件主数据",
                            update_method="Routing",
                            item_no=data["item_no"],
                            operation_number=data["operation_number"], plant_code=data["plant_code"],
                            work_center="", description="",
                            operation_description=data["operation_description"],
                            operation_qty=data["operation_qty"],
                            operation_unit=data["operation_unit"], recipe_code=data["recipe_code"])
        returnObj.append(retObj.__dict__)
        update_all_flag = False
    return returnObj, update_all_flag


def clear_act_reason(routing_group, routing_group_serial_number):
    db = DbHelper()
    sql = f""" DELETE
                FROM
                  `t_rgt_routing_operation_act_reason` 
                WHERE
                  `routing_group` = '{routing_group}' 
                  AND `routing_group_serial_number` = '{routing_group_serial_number}' """
    db.exec_sql(sql, isNewDB=True)
    db.updateDBObj()


def clear_recipe_update_status(plant_code, routing_group, routing_group_serial_number, update_method):
    db = DbHelper()
    sql = f""" DELETE
                FROM
                  `t_co_recipe_update_status` 
                WHERE
                  `routing_group` = '{routing_group}' 
                  AND `routing_group_serial_number` = '{routing_group_serial_number}' 
                  and `update_method` = '{update_method}' 
                  and `plant_code` = '{plant_code}' """
    db.exec_sql(sql, isNewDB=True)
    db.updateDBObj()


def get_activity_header_db():
    db = DbHelper()
    sql = f"""select * from `t_eq_recipe_activity_header` where `h`.`valid_state`='1' """
    ret = db.query_sql(sql)
    return {(i.get("plant_code"), i.get("recipe_id")): i.get("activity_flag") for i in ret}


def updateOperation(operationObj, DuplicateSQLKey=["recipe_id", "recipe_code", "sub_recipe_id"]):
    print("DuplicateSQLKey", DuplicateSQLKey)
    db = DbHelper()
    db.batchInsertToDB("t_rgt_routing_operation", [operationObj],
                       DuplicateSQLKey=DuplicateSQLKey, isNewDB=True, printSql=True)
    db.updateDBObj()
    # db.dbCommit()


def clearBomItem(bom_group, routing_group_serial_number):
    db = DbHelper()
    del_sql = f"""delete from `t_bom_item` where `bom_group`={bom_group} and `bom_group_counter`={routing_group_serial_number} 
                    and (`recipe_code` !=null or `recipe_code`!='') """
    db.exec_sql(del_sql, isNewDB=True)
    db.updateDBObj()


def getBomItemMaxNo(bom_group, routing_group_serial_number):
    db = DbHelper()
    sql = f"""SELECT COALESCE(MAX(`item_no`), 0) AS `max_item_no`
                    FROM `t_bom_item`
                    WHERE `bom_group` = {bom_group} AND `bom_group_counter` = {routing_group_serial_number};
                    """
    ret = db.query_sql(sql)
    if ret:
        return ret[0].get("max_item_no") + 1
    else:
        return 1


def getBomItemMaxSn(bom_group, routing_group_serial_number):
    db = DbHelper()
    sql = f"""SELECT COALESCE(MAX(`component_number`), 0) AS `max_component_number`
                    FROM `t_bom_item`
                    WHERE `bom_group` = {bom_group} AND `bom_group_counter` = {routing_group_serial_number};"""
    ret = db.query_sql(sql)
    if ret:
        return ret[0].get("max_component_number") + 1
    else:
        return 1


def update_routing_header_status(data=[], DuplicateSQLKey=[]):
    db = DbHelper()
    if data:
        db.batchInsertToDB("t_rgt_routing_header", data,
                           DuplicateSQLKey=DuplicateSQLKey, isNewDB=True)
        db.updateDBObj()

def get_wbs_profit_center():
    db = DbHelper()
    sql = f""" select
                `tmmcd`.`mat_code`,
                `tmmcd`.`plant_code`,
                `tmmcd`.`wbs_elements`, 
                `tmmfd`.`profit_center` 
                from `t_mmd_material_cost_data` as `tmmcd` 
                left join `t_mmd_material_financial_data` as `tmmfd` on `tmmcd`.`mat_code`=`tmmfd`.`mat_code` and `tmmcd`.`plant_code`=`tmmfd`.`plant_code`
                """
    ret = db.query_sql(sql, isNewDB=True)
    return {(i.get("plant_code"), i.get("mat_code")): i for i in ret}


if __name__ == '__main__':
    # ret = updateRouting("1001", [{
    #     "mat_code": "TPMC000001",
    #     "routing_group": 7,
    #     "routing_group_serial_number": 2
    # }])
    # ret = updateBOMSetupA("1001", [{
    #     "mat_code": "TPMC000001",
    #     "routing_group": 7,
    #     "routing_group_serial_number": 2
    # }])
    # ret = updateBOMSetupA("1001", [{
    #     "mat_code": "TPMC000002",
    #     "routing_group": 1047,
    #     "routing_group_serial_number": 2
    # }])
    ret = updateBOMSetupA("1000", [{
        "mat_code": "TPMC000002",
        "routing_group": 1047,
        "routing_group_serial_number": 2
    }])

    # ret = updateRouting("1000", [{
    #     "mat_code": "TPMC000002",
    #     "routing_group": 1047,
    #     "routing_group_serial_number": 2
    # }])
    logger.printInfo(ret.__dict__)
