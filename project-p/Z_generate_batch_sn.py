#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@File    ：Z_generate_batch_sn.py
@Author  ：xsz
@Date    ：2026/6/3 11:05 
@explain : 
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation

from DbHelper import DbHelper
from GenerateSerialNum import redis_handler, redis_lock
from ToolsMethods import ResetResponse, ResponseData


def _escape_sql_value(value):
    return str(value).replace("'", "''")


def _query_batch_sn_by_conditions(db, query_conditions):
    where_list = []
    for field, value in query_conditions.items():
        where_list.append(f"`{field}` = '{_escape_sql_value(value)}'")
    sql = f"select `batch_sn` from `t_batch_number` where {' and '.join(where_list)} limit 1"
    print("按条件查询批次号sql>>", sql)
    batch_sn_data = db.query_sql(sql)
    if batch_sn_data:
        batch_sn = batch_sn_data[0].get("batch_sn", "")
        print("按条件命中批次号>>", batch_sn)
        return batch_sn
    return ""


def _generate_uf_zt04_batch_sn(db, uf_ZT04, query_conditions=None):
    """
    逻辑：
    1. 按 uf_ZT04 维度加 Redis 锁，避免并发场景拿到相同流水号
    2. Redis 不存在计数器时，先从数据库中查询当前最大的批次流水号并初始化
    3. 使用 Redis 自增获取下一个流水号，并返回 uf_ZT04-3位补零格式的批次号

    注：当前方案允许保存失败后出现跳号，但可以避免并发重复号
    """
    redis_counter_key = f"batch_sn_counter:{uf_ZT04}"
    print("批次号redis计数器key>>", redis_counter_key)

    with redis_lock(f"batch_sn_init:{uf_ZT04}"):
        if query_conditions:
            batch_sn = _query_batch_sn_by_conditions(db, query_conditions)
            if batch_sn:
                print("锁内命中已存在批次号>>", batch_sn)
                return batch_sn

        counter_exists = redis_handler.redis_execute(f"EXISTS {redis_counter_key}")
        print("批次号redis计数器是否存在>>", counter_exists)

        if not int(counter_exists):
            max_serial_sql = f"""
                select max(cast(substring_index(`batch_sn`, '-', -1) as unsigned)) as `max_serial`
                from `t_batch_number`
                where `uf_ZT04` = '{uf_ZT04}'
                and `batch_sn` like '{uf_ZT04}-%'
            """
            print("查询uf_ZT04最大流水号sql>>", max_serial_sql)
            max_serial_data = db.query_sql(max_serial_sql)
            max_serial = max_serial_data[0].get("max_serial") if max_serial_data else 0
            if not max_serial:
                max_serial = 0
            print("数据库最大流水号>>", max_serial)

            redis_init_result = redis_handler.redis_string(f"SET {redis_counter_key} {int(max_serial)} EX 90000")
            print("初始化redis计数器结果>>", redis_init_result)

        next_serial = int(redis_handler.redis_execute(f"INCR {redis_counter_key}"))
        batch_sn = f"{uf_ZT04}-{next_serial:03d}"
        print("生成的新批次号>>", batch_sn)
        return batch_sn


def _get_or_create_batch_sn(db, uf_ZT04, query_conditions):
    batch_sn = _query_batch_sn_by_conditions(db, query_conditions)
    if batch_sn:
        return batch_sn
    return _generate_uf_zt04_batch_sn(db, uf_ZT04, query_conditions)


def _convert_to_decimal(value, field_name):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{field_name}格式不正确")


def _format_output_count(value):
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _split_wafer_ids(wafer_ids):
    wafer_id_list = [str(wafer_id).strip() for wafer_id in str(wafer_ids).split(",") if str(wafer_id).strip()]
    print("清洗后的wafer_id列表>>", wafer_id_list)
    if not wafer_id_list:
        raise ValueError("uf_ZWAFERNO不能为空")
    return wafer_id_list


def _split_wafer_count(wafer_ids, count):
    wafer_id_list = _split_wafer_ids(wafer_ids)
    total_count = _convert_to_decimal(count, "count")
    if total_count <= 0:
        raise ValueError("count必须大于0")

    wafer_id_list_size = len(wafer_id_list)
    remain_count = total_count % wafer_id_list_size
    print("wafer数量>>", wafer_id_list_size, "总数量>>", total_count, "均分余数>>", remain_count)
    if remain_count != 0:
        raise ValueError(
            f"uf_ZWAFERNO({wafer_ids})的片号数量为{wafer_id_list_size}, "
            f"总数量为{_format_output_count(total_count)}, 数量无法平均分配"
        )

    each_count = total_count / wafer_id_list_size
    print("每个wafer_id分摊数量>>", each_count)
    return wafer_id_list, each_count


def _merge_batch_sn_pick_result(batch_sn_info_list):
    result = []
    result_index_map = {}
    for batch_sn_info in batch_sn_info_list:
        batch_sn = batch_sn_info.get("batch_sn", "")
        if not batch_sn:
            print("待合并批次号为空，跳过>>", batch_sn_info)
            continue

        item_count = _convert_to_decimal(batch_sn_info.get("count", 0), "count")
        if batch_sn not in result_index_map:
            result_index_map[batch_sn] = len(result)
            result.append({
                "batch_sn": batch_sn,
                "count": _format_output_count(item_count)
            })
        else:
            result_index = result_index_map[batch_sn]
            old_count = _convert_to_decimal(result[result_index].get("count", 0), "count")
            result[result_index]["count"] = _format_output_count(old_count + item_count)
        print("当前合并后的批次结果>>", result)

    print("最终合并后的批次结果>>", result)
    return result


def _build_wafer_batch_sn_result(db, uf_ZT04, wafer_ids, count):
    """
    逻辑：
    1. 先清洗 uf_ZWAFERNO，按逗号拆分并去掉空白片号
    2. 校验总数量是否能按 wafer_id 数量平均分配，不能均分直接报错
    3. 再按 wafer_id 逐个查询或生成批次号，并回填每个 wafer_id 的分摊数量
    """
    wafer_id_list, each_count = _split_wafer_count(wafer_ids, count)
    result = []
    for wafer_id in wafer_id_list:
        # 按 wafer_id 作为唯一条件逐个生成/复用批次号，保证一片对应一个批次号
        query_conditions = {
            "uf_ZT04": uf_ZT04,
            "wafer_id": wafer_id
        }
        batch_sn = _get_or_create_batch_sn(db, uf_ZT04, query_conditions)
        result.append({
            "wafer_id": wafer_id,
            "batch_sn": batch_sn,
            "count": _format_output_count(each_count)
        })
        print("当前wafer_id生成结果>>", result[-1])

    print("最终wafer批次号生成结果>>", result)
    return result


def _get_wafer_batch_sn_pick_info(db, mat_code, uf_ZT04, wafer_ids, count):
    # 逻辑：
    # 1. uf_ZWAFERNO 为空时保持原逻辑，只按 uf_ZT04 查询
    # 2. uf_ZWAFERNO 为单值时按单个 wafer_id 查询
    # 3. uf_ZWAFERNO 为多值时按逗号拆分，并将总数量平均分到每个 wafer_id
    # 4. 每个 wafer_id 独立查询库存批次，最后按 batch_sn 合并返回
    query_conditions = {}
    if uf_ZT04:
        query_conditions["uf_ZT04"] = uf_ZT04

    wafer_ids_str = str(wafer_ids).strip()
    if not wafer_ids_str:
        print("当前物料组查询条件>>", query_conditions)
        return _get_batch_sn_pick_info(db, mat_code, query_conditions, count)

    if "," not in wafer_ids_str:
        query_conditions["wafer_id"] = wafer_ids_str
        print("当前物料组查询条件>>", query_conditions)
        return _get_batch_sn_pick_info(db, mat_code, query_conditions, count)

    wafer_id_list, each_count = _split_wafer_count(wafer_ids_str, count)
    each_count = _format_output_count(each_count)
    result = []
    for wafer_id in wafer_id_list:
        split_query_conditions = dict(query_conditions)
        split_query_conditions["wafer_id"] = wafer_id
        print("拆分后的wafer查询条件>>", split_query_conditions, "分摊数量>>", each_count)
        msg, batch_sn_info = _get_batch_sn_pick_info(db, mat_code, split_query_conditions, each_count)
        if msg:
            msg = f"wafer_id[{wafer_id}]查询失败: {msg}"
            print("拆分wafer_id查询失败>>", msg)
            return msg, []
        result.extend(batch_sn_info)
        print("拆分wafer_id当前累计结果>>", result)

    return "", _merge_batch_sn_pick_result(result)


def _query_batch_sns_for_info(db, mat_code, query_conditions):
    where_list = [f"`mat_code` = '{_escape_sql_value(mat_code)}'"]
    for field, value in query_conditions.items():
        where_list.append(f"`{field}` = '{_escape_sql_value(value)}'")
    sql = (
        f"select `batch_sn`, `receive_date` "
        f"from `t_batch_number` "
        f"where {' and '.join(where_list)} "
        f"order by `receive_date` asc, `batch_sn` asc"
    )
    print("查询匹配批次号sql>>", sql)
    batch_sns = db.query_sql(sql)
    print("查询匹配批次号结果>>", batch_sns)
    return batch_sns


def _allocate_inventory_batches(inventory_data, required_count):
    """
    逻辑：
    1. 按已经排好优先级的批次顺序遍历库存数据，优先取最早 receive_date 的批次号
    2. 同一批次号下再按 create_time 从旧到新逐条扣减需求量
    3. 每次从当前库存明细扣减剩余需求量，并按 batch_sn 聚合本次实际需要领取的数量
    4. 需求量满足后立即停止；若库存不足，则返回已分配部分并打印缺口
    """
    required_count = _convert_to_decimal(required_count, "count")
    if required_count <= 0:
        raise ValueError("count必须大于0")

    print("开始分配库存，需求数量>>", required_count)
    result = []
    result_index_map = {}
    remain_count = required_count
    for inventory_item in inventory_data:
        if remain_count <= 0:
            break

        batch_sn = inventory_item.get("batch_sn", "")
        basic_qty = _convert_to_decimal(inventory_item.get("basic_qty", 0), "basic_qty")
        print("当前遍历库存批次>>", inventory_item)
        if not batch_sn or basic_qty <= 0:
            print("当前库存批次无效，跳过>>", inventory_item)
            continue

        pick_count = basic_qty if basic_qty <= remain_count else remain_count
        if batch_sn not in result_index_map:
            result_index_map[batch_sn] = len(result)
            result.append({
                "batch_sn": batch_sn,
                "count": _format_output_count(pick_count)
            })
        else:
            result_index = result_index_map[batch_sn]
            old_count = _convert_to_decimal(result[result_index].get("count", 0), "count")
            result[result_index]["count"] = _format_output_count(old_count + pick_count)
        remain_count -= pick_count
        print("当前库存明细分配后结果>>", result, "剩余需求量>>", remain_count)

    if remain_count > 0:
        available_count = required_count - remain_count
        shortage_msg = (
            f"库存不足，需求数量为{_format_output_count(required_count)}，"
            f"可用库存数量为{_format_output_count(available_count)}"
        )
        print("库存不足，尚未满足的需求数量>>", remain_count)
        print("库存不足返回信息>>", shortage_msg)
        return shortage_msg, []
    print("最终批次分配结果>>", result)
    return '', result


def _get_batch_sn_pick_info(db, mat_code, query_conditions, count):
    # 逻辑：
    # 1. 先按 t_batch_number.receive_date 正序查出批次号顺序，最早批次优先
    # 2. 再查询库存表明细，并在同一批次号内按 create_time 从旧到新排序
    # 3. 最后按批次号优先级顺序依次扣减需求数量，不够再取下一个批次号
    # 4. 返回结果按 batch_sn 聚合，避免同一批次号重复返回多条
    batch_sns = _query_batch_sns_for_info(db, mat_code, query_conditions)
    if not batch_sns:
        print("未查询到匹配的批次号")
        return f"在表t_batch_number中，未查询到符合条件的批次号,当前物料号为：{mat_code},其他条件为：{query_conditions}", []
    batch_sn_list = [item.get("batch_sn") for item in batch_sns if item.get("batch_sn")]
    if not batch_sn_list:
        print("批次号结果为空")
        return "未查询到匹配的批次号", []
    print("按receive_date排序后的批次号列表>>", batch_sn_list)

    in_sql = ",".join([f"'{_escape_sql_value(batch_sn)}'" for batch_sn in batch_sn_list])
    sql = (
        f"select `batch_sn`, `basic_qty`, `create_time` "
        f"from `t_inventory_batch_data` "
        f"where `mat_code` = '{_escape_sql_value(mat_code)}' "
        f"and `basic_qty` > 0 "
        f"and `batch_sn` in ({in_sql})"
    )
    print("查询库存批次数据sql>>", sql)
    inventory_data = db.query_sql(sql)
    print("查询库存批次数据结果>>", inventory_data)
    if not inventory_data:
        print("未查询到可用库存批次")
        return _allocate_inventory_batches([], count)

    batch_sn_sort_map = {batch_sn: index for index, batch_sn in enumerate(batch_sn_list)}
    inventory_data = sorted(
        inventory_data,
        key=lambda item: (
            batch_sn_sort_map.get(item.get("batch_sn", ""), len(batch_sn_sort_map)),
            item.get("create_time") or "9999-12-31 23:59:59"
        )
    )
    print("按批次号优先级排序后的库存数据>>", inventory_data)
    return _allocate_inventory_batches(inventory_data, count)


def create_batch_sns(db, data_list):

    """
    data_list: [
                {
                    "mat_code": "物料编码(必填)",
                    "uf_ZT04": "供应商批次号(必填)",
                    "wafer_id": "制造序号(选填)",
                    "uf_ZT18": "生产周(选填)",
                    "uf_runcard": "Runcard(选填)",
                    "uf_box_no": "箱号(选填)",
                    "uf_electroplating_date": "电镀日期(选填)"

                    # "uf_quality_type": "品质类型(选填)",
                    # "uf_ZT25": "封装订单号(选填)",
                    # "uf_ZT18": "生产周(选填)",
                    # "receive_date": "收货日期(选填)",
                    # "uf_ZT04": "晶圆批次(Foundry Lot NO)(选填)",
                    # "uf_ZT59": "FT订单号(选填)",
                    # "uf_ZT07": "BIN(选填)",
                    # "uf_ZT60": "PK订单号(选填)",
                    # "vendor_batch": "供应商批次(选填)",
                }
            ]
    """
    if not data_list:
        return []
    for data in data_list:
        batch_sn_result = create_batch_sn(db, data)
        if isinstance(batch_sn_result, list):
            data["batch_sn_info"] = batch_sn_result
            batch_sn_list = [item.get("batch_sn", "") for item in batch_sn_result if item.get("batch_sn", "")]
            data["batch_sn"] = ",".join(batch_sn_list)
        else:
            data["batch_sn"] = batch_sn_result

    return data_list

@ResetResponse(params=['data'])
def test(data):
    db = DbHelper()
    result = create_batch_sn(db, data)
    return ResponseData(200, "成功", result)

@ResetResponse(params=['data_list'])
def test1(data_list):
    db = DbHelper()
    result = create_batch_sns(db, data_list)
    return ResponseData(200, "成功", result)

@ResetResponse(params=['datalist'])
def test2(datalist):
    db = DbHelper()
    msg, result = get_batch_sn_info(db, datalist)
    if msg and not result:
        return ResponseData(400, "失败", msg)
    return ResponseData(200, "成功", result)

def create_batch_sn(db, data):
    """
        {
            "count": 数量(必填),
            "mat_code": "物料编码(必填)",
            "uf_ZT04": "供应商批次号(必填)",
            "wafer_id": "制造序号(选填)",
            "uf_ZT18": "生产周(选填)",
            "uf_runcard": "Runcard(选填)",
            "uf_box_no": "箱号(选填)",
            "uf_electroplating_date": "电镀日期(选填)"

            # "uf_quality_type": "品质类型(选填)",
            # "uf_ZT25": "封装订单号(选填)",
            # "uf_ZT18": "生产周(选填)",
            # "receive_date": "收货日期(选填)",
            # "uf_ZT04": "晶圆批次(Foundry Lot NO)(选填)",
            # "uf_ZT59": "FT订单号(选填)",
            # "uf_ZT07": "BIN(选填)",
            # "uf_ZT60": "PK订单号(选填)",
            # "vendor_batch": "供应商批次(选填)",
        }


    返回结果：
        [
            {
                "wafer_id": "05",
                "batch_sn": "HATW29.1-005",
                "count": 100
            },
            {
                "wafer_id": "06",
                "batch_sn": "HATW29.1-006",
                "count": 100
            }
        ]
    """


    # 逻辑：
    # 1. 先根据物料编码获取物料组
    # 2. 不同物料组按各自的唯一条件查询是否已有批次号
    # 3. 已存在则直接返回已有批次号
    # 4. 不存在则基于 uf_ZT04 通过 Redis 计数器生成新的批次号
    mat_code = data.get("mat_code")
    if not mat_code:
        raise ValueError("请填写物料编码")

    mat_info = db.query_sql(f"""select `mat_group`, `prod_group`, `process_code`  from `t_mmd_material_basic_data` where `mat_code` = '{mat_code}'""")
    if not mat_info:
        raise ValueError("物料编码不存在")
    print("mat_info>>", mat_info)
    mat_group = mat_info[0].get("mat_group")
    print("mat_group>>", mat_group)
    if mat_group in ["1001", "1002", "1003", "1004", "3002", "3003", "3004"]:
        uf_ZT04 = data.get("uf_ZT04", '') # lot_no
        wafer_ids = data.get("uf_ZWAFERNO", '')
        count = data.get("count")  # 数量
        if not uf_ZT04 or not wafer_ids or not count:
            raise ValueError("请填写制造批号、制造序号和数量")
        return _build_wafer_batch_sn_result(db, uf_ZT04, wafer_ids, count)

    elif mat_group in ["2001", "2002", "2003", "2011"]:
        uf_ZT04 = data.get("uf_ZT04", '') # lot_no
        uf_ZT18 = data.get("uf_ZT18", '') # Date code
        receive_date = datetime.now().strftime("%Y-%m-%d")
        print("当前收货日期>>", receive_date)
        if not uf_ZT04 or not uf_ZT18:
            raise ValueError("uf_ZT04和uf_ZT18不能为空")
        if mat_group == "2001":
            process_code = mat_info[0].get("process_code", '')
            if process_code == 'Z07':
                # 颗粒度多一个 runcard
                uf_runcard = data.get("uf_runcard", '')
                if not uf_runcard:
                    raise ValueError("请填写uf_runcard")
                # 查询条件为 uf_ZT04 + uf_ZT18 + receive_date + uf_runcard
                query_conditions = {
                    "uf_ZT04": uf_ZT04,
                    "uf_ZT18": uf_ZT18,
                    "receive_date": receive_date,
                    "uf_runcard": uf_runcard
                }
                return _get_or_create_batch_sn(db, uf_ZT04, query_conditions)

        elif mat_group == "2003":
            uf_box_no = data.get("uf_box_no", '') # 箱号
            if not uf_box_no:
                raise ValueError("请填写uf_box_no")
            # 查询条件为 uf_ZT04 + uf_ZT18 + receive_date + uf_box_no
            query_conditions = {
                "uf_ZT04": uf_ZT04,
                "uf_ZT18": uf_ZT18,
                "receive_date": receive_date,
                "uf_box_no": uf_box_no
            }
            return _get_or_create_batch_sn(db, uf_ZT04, query_conditions)
        else:
            # 查询条件为 uf_ZT04 + uf_ZT18 + receive_date
            query_conditions = {
                "uf_ZT04": uf_ZT04,
                "uf_ZT18": uf_ZT18,
                "receive_date": receive_date
            }
            return _get_or_create_batch_sn(db, uf_ZT04, query_conditions)

        query_conditions = {
            "uf_ZT04": uf_ZT04,
            "uf_ZT18": uf_ZT18,
            "receive_date": receive_date
        }
        return _get_or_create_batch_sn(db, uf_ZT04, query_conditions)

    elif mat_group in ["3001", "3006", "3007", "3008", "3099", "4001"]:
        uf_ZT04 = data.get("uf_ZT04", '') # lot_no
        if not uf_ZT04:
            raise ValueError("请填写uf_ZT04")
        receive_date = datetime.now().strftime("%Y-%m-%d")
        print("当前收货日期>>", receive_date)
        # 查询条件为 receive_date  但批次号依旧为 uf_ZT04-流水号
        query_conditions = {
            "receive_date": receive_date
        }
        return _get_or_create_batch_sn(db, uf_ZT04, query_conditions)

    elif mat_group == "3005":
        uf_ZT04 = data.get("uf_ZT04", '') # 供应商批次号
        uf_electroplating_date = data.get("uf_electroplating_date", '') # 电镀日期
        if not uf_ZT04 or not uf_electroplating_date:
            raise ValueError("请填写供应商批次号和电镀日期")
        # 查询条件为 uf_ZT04 + uf_electroplating_date
        query_conditions = {
            "uf_ZT04": uf_ZT04,
            "uf_electroplating_date": uf_electroplating_date
        }
        return _get_or_create_batch_sn(db, uf_ZT04, query_conditions)

    else:
        raise ValueError("请填写正确的物料编码")


def _get_single_batch_sn_info(db, data):
    """
        "data" : {
                    "mat_code":"物料号，必传",
                    "count":"需求数量，必填",

                    "uf_ZT04": "供应商批次号(选填)",
                    # "wafer_id": "制造序号(选填)",
                    "uf_ZWAFERNO": "制造序号(选填)",
                    "uf_ZT18": "生产周(选填)",
                    "receive_date":"入库日期(选填)"
                    "uf_runcard": "Runcard(选填)",
                    "uf_box_no": "箱号(选填)",
                    "uf_electroplating_date": "电镀日期(选填)"
                }



        返回结果：
            msg, result = get_batch_sn_info(db, data)

            msg 为空  成功， 数据为result
                 result: [
                            {
                                "batch_sn": "026060200150",
                                "count": 30
                            }
                        ]
            msg 不为空，msg为报错信息， result为[]
    """
    # 逻辑：
    # 1. 先根据物料编码获取物料组，并复用 create_batch_sn 中相同的批次唯一条件
    # 2. 先到 t_batch_number 中查出符合条件的批次号集合
    # 3. 再到 t_inventory_batch_data 中按批次优先级和 create_time 升序查询正库存批次
    # 4. 最后按规则逐个批次扣减需求数量，返回每个批次本次实际需要取的 count
    mat_code = data.get("mat_code")
    count = data.get("count")
    if not mat_code or not count:
        raise ValueError("mat_code, count不能为空")

    print("入参>>>data:",data)
    mat_info = db.query_sql(
        f"""select `mat_group`, `prod_group`, `process_code`  from `t_mmd_material_basic_data` where `mat_code` = '{mat_code}'""")
    if not mat_info:
        raise ValueError("物料编码不存在")
    print("mat_info>>", mat_info)
    mat_group = mat_info[0].get("mat_group")
    print("mat_group>>", mat_group)
    if mat_group in ["1001", "1002", "1003", "1004", "3002", "3003", "3004"]:
        uf_ZT04 = data.get("uf_ZT04", '')  # lot_no
        wafer_id = data.get("uf_ZWAFERNO", '')
        return _get_wafer_batch_sn_pick_info(db, mat_code, uf_ZT04, wafer_id, count)

    elif mat_group in ["2001", "2002", "2003", "2011"]:
        uf_ZT04 = data.get("uf_ZT04", '')  # lot_no
        uf_ZT18 = data.get("uf_ZT18", '')  # Date code
        receive_date = data.get("receive_date", '')  # 入库日期
        print("查询使用的入库日期>>", receive_date)

        if mat_group == "2001":
            process_code = mat_info[0].get("process_code", '')
            if process_code == 'Z07':
                # 颗粒度多一个 runcard
                uf_runcard = data.get("uf_runcard", '')
                query_conditions = {}
                if uf_ZT04:
                    query_conditions["uf_ZT04"] = uf_ZT04
                if uf_ZT18:
                    query_conditions["uf_ZT18"] = uf_ZT18
                if receive_date:
                    query_conditions["receive_date"] = receive_date
                if uf_runcard:
                    query_conditions["uf_runcard"] = uf_runcard
                print("当前物料组查询条件>>", query_conditions)
                return _get_batch_sn_pick_info(db, mat_code, query_conditions, count)

        elif mat_group == "2003":
            uf_box_no = data.get("uf_box_no", '')  # 箱号
            query_conditions = {}
            if uf_ZT04:
                query_conditions["uf_ZT04"] = uf_ZT04
            if uf_ZT18:
                query_conditions["uf_ZT18"] = uf_ZT18
            if receive_date:
                query_conditions["receive_date"] = receive_date
            if uf_box_no:
                query_conditions["uf_box_no"] = uf_box_no
            print("当前物料组查询条件>>", query_conditions)
            return _get_batch_sn_pick_info(db, mat_code, query_conditions, count)

        else:
            # 查询条件为 uf_ZT04 + uf_ZT18 + receive_date
            query_conditions = {}
            if uf_ZT04:
                query_conditions["uf_ZT04"] = uf_ZT04
            if uf_ZT18:
                query_conditions["uf_ZT18"] = uf_ZT18
            if receive_date:
                query_conditions["receive_date"] = receive_date
            print("当前物料组查询条件>>", query_conditions)
            return _get_batch_sn_pick_info(db, mat_code, query_conditions, count)

        query_conditions = {}
        if uf_ZT04:
            query_conditions["uf_ZT04"] = uf_ZT04
        if uf_ZT18:
            query_conditions["uf_ZT18"] = uf_ZT18
        if receive_date:
            query_conditions["receive_date"] = receive_date
        print("当前物料组查询条件>>", query_conditions)
        return _get_batch_sn_pick_info(db, mat_code, query_conditions, count)

    elif mat_group in ["3001", "3006", "3007", "3008", "3099", "4001"]:
        uf_ZT04 = data.get("uf_ZT04", '')  # lot_no
        receive_date = data.get("receive_date", '')  # 入库日期
        print("查询使用的入库日期>>", receive_date)
        # 查询条件为 receive_date  但批次号依旧为 uf_ZT04-流水号
        query_conditions = {}
        if receive_date:
            query_conditions["receive_date"] = receive_date
        print("当前物料组查询条件>>", query_conditions)
        return _get_batch_sn_pick_info(db, mat_code, query_conditions, count)
    elif mat_group == "3005":
        uf_ZT04 = data.get("uf_ZT04", '')  # 供应商批次号
        uf_electroplating_date = data.get("uf_electroplating_date", '')  # 电镀日期
        query_conditions = {}
        if uf_ZT04:
            query_conditions["uf_ZT04"] = uf_ZT04
        if uf_electroplating_date:
            query_conditions["uf_electroplating_date"] = uf_electroplating_date
        print("当前物料组查询条件>>", query_conditions)
        return _get_batch_sn_pick_info(db, mat_code, query_conditions, count)

    else:
        raise ValueError("请填写正确的物料编码")


def get_batch_sn_info(db, datalist):
    """
        "datalist" : [
            {
                "mat_code":"物料号，必传",
                "count":"需求数量，必填"

                "uf_ZT04": "供应商批次号(选填)",
                # "wafer_id": "制造序号(选填)",
                "uf_ZWAFERNO": "制造序号(选填)",
                "uf_ZT18": "生产周(选填)",
                "receive_date":"入库日期(选填)"
                "uf_runcard": "Runcard(选填)",
                "uf_box_no": "箱号(选填)",
                "uf_electroplating_date": "电镀日期(选填)"
            }
        ]

        返回结果：
            msg, result = get_batch_sn_info(db, datalist)

            msg 为空  成功， 数据为result
                 result: [
                            {
                                "mat_code": "xxx",
                                "count": 30,
                                "batch_sn_info": [
                                    {
                                        "batch_sn": "026060200150",
                                        "count": 30
                                    }
                                ],
                                "batch_sn_info_msg": ""
                            }
                        ]
            msg 不为空，msg为批量入参错误， result为[]
    """
    # 逻辑：
    # 1. 批量遍历 datalist，逐条复用原有单条批次查询逻辑
    # 2. 每条数据都回填 batch_sn_info 和 batch_sn_info_msg，避免单条失败影响整批结果
    # 3. 只有批量入参本身不合法时，才返回总错误信息
    if not isinstance(datalist, list) or not datalist:
        return "datalist不能为空", []

    result_list = []
    for index, data in enumerate(datalist):
        print("批量查询当前索引>>", index, "当前数据>>", data)
        if not isinstance(data, dict):
            result_list.append({
                "batch_sn_info": [],
                "batch_sn_info_msg": "单条数据格式必须为对象"
            })
            continue

        try:
            msg, batch_sn_info = _get_single_batch_sn_info(db, data)
        except Exception as e:
            print("单条批次查询异常>>", e)
            msg = str(e)
            batch_sn_info = []

        data["batch_sn_info"] = batch_sn_info
        data["batch_sn_info_msg"] = msg
        print("单条数据回填结果>>", data)
        result_list.append(data)

    return "", result_list
