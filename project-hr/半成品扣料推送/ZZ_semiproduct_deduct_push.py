# -*- coding: UTF-8 -*-
"""
@File    : ZZ_semiproduct_deduct_push.py
@Author  : yang.zhang@dxdstech.com
@Date    : 2026/06/22
@explain : 半成品扣料推送

  调用方向:   秘火->SAP
  模块名称:   半成品扣料推送(工单扣料)
  接口名称:   半成品扣料推送接口
  接口说明：  半成品扣料推送, 调 SAP 货物移动 RFC(ZRFC_MM_GNRTRANS_RACQ, MB1A),
             移动类型 261(正向发料)/262(反向冲销),
             并将物料凭证号/年度/状态/消息回写至 t_co_summary_result。
             
  源表:       t_co_summary_report(扣料明细)
  结果表:     t_co_summary_result(过账结果)
  中间表:     ZMES_MM_GOODSREC_MHXT (Oracle, 秘火先 INSERT PROCESS_FLG=5, 再调 RFC)

"""
import json
import traceback
from datetime import datetime

from DbHelper import DbHelper
from libenhance import Request, Response, get_cnf
from ToolsMethods import (
    GetExportData,
    Paginator,
    calc_time,
    create_table_alias,
    display_to_entozh,
    generate_raw_sql,
)
from utils import query_db_records_by_cond, update_db_record_by_cond
from ZZEXT_OracleHandle import OracleDB, get_schema

# from ZZEXT_SapRFC import SAPRFC

db = DbHelper()

# ---------- 固定值(按接口文档 v1.1, 集中维护) ----------
# SAP接口编码 / RFC函数名
INTERFACE_CODE = "ZRFC_MM_GNRTRANS_RACQ"
INTERFACE_NAME = "半成品扣料推送接口"

# MES与SAP接口编号 / 中间表
IP_NO = "MES_MM_004"
MID_TABLE = "ZMES_MM_GOODSREC_MHXT"            # Oracle 中间表(秘火先 INSERT, 再调 RFC)

PROCESS_FLG_INIT = "5"                    # 秘火写入中间表时的初始状态(SAP 成功置 2 / 失败置 D)
MANDT = get_cnf("rfc.client")             # SAP 集团号(=RFC client, 生产 801 / 测试 500)

# 中间表 ZMES_MM_GOODSREC_MHXT 列(按接口文档 v1.1)
# MID_TABLE_COLUMNS = [
#     "MANDT", "IP_NO", "IP_INDEX", "AUFNR", "ZCOUNT", "BWART", "WERKS", "MATNR",
#     "ERFMG", "ERFME", "CHARG", "ZUSER", "DATUM_B", "UZEIT_B", "ZDATE", "ZTIME",
#     "BUKRS", "USRID", "PROCESS_FLG", "LGORT",
# ]

MID_TABLE_COLUMNS = [
    "MANDT", "IP_NO", "IP_INDEX", "AUFNR", "ZCOUNT", "BWART", "WERKS", "MATNR",
    "ERFMG", "ERFME", "CHARG", "ZUSER", "ZDATE", "ZTIME", "BUKRS", "USRID", "PROCESS_FLG", "LGORT",
]



# BAPI 货物移动事务代码 / 公司代码 / 工厂 / 存储地点
GM_CODE = "11"                      # P_CODE.GM_CODE 固定值 03(MB1A)
BUKRS = "RACQ"                      # P_BUKRS 固定 RACQ
PLANT_DEFAULT = "RAC1"              # 工厂(文档固定值 RAC1)
STGE_LOC_DEFAULT = "0050"           # 存储地点(文档固定值 0050)
USRID = "MH"                        # 用户名(文档固定 MH)

# 移动类型(库存管理): 261 正向发料 / 262 反向冲销
MOVE_TYPE_POS = "261"
MOVE_TYPE_NEG = "262"

# 源表 / 结果表
SOURCE_TABLE = "t_co_summary_report"
RESULT_TABLE = "t_co_summary_result"

# IP_INDEX 生成规则: HMH + YYYYMMDD + 5位流水
IPINDEX_PREFIX = "HMH"
IPINDEX_SEQ_WIDTH = 5




import pyrfc
from libenhance import get_cnf
from logger import LoggerConfig

usprint = LoggerConfig()


class SAPRFC:
    def __init__(self):
        # 从配置文件获取SAP连接参数
        ashost = get_cnf("rfc.ashost")
        sysnr = get_cnf("rfc.sysnr")
        client = get_cnf("rfc.client")
        user = get_cnf("rfc.user")
        passwd = get_cnf("rfc.passwd")
        lang = get_cnf("rfc.lang")  # 默认中文
        trace = get_cnf("rfc.trace")  # 默认不追踪

        try:
            self.connection = pyrfc.Connection(
                ashost=ashost,
                sysnr=sysnr,
                client=client,
                user=user,
                passwd=passwd,
                lang=lang,
                trace=trace
            )
            usprint.printInfo('SAPRFC', f"SAP连接成功: {ashost}, 系统编号: {sysnr}")
        except Exception as e:
            raise Exception(f"SAP RFC连接异常: {e}")

    def call(self, rfc_name, params=None):
        """
        调用RFC函数
        :param rfc_name: RFC函数名称
        :param params: 输入参数字典（可选）
        :return: 返回结果字典
        """
        try:
            if params:
                result = self.connection.call(rfc_name, **params)
            else:
                result = self.connection.call(rfc_name)

            usprint.printInfo('SAPRFC', f"调用 {rfc_name} 成功")
            return result

        except pyrfc.ABAPApplicationError as e:
            usprint.printInfo('SAPRFC', f"ABAP应用错误 - {rfc_name}: {e}")
            raise
        except pyrfc.CommunicationError as e:
            usprint.printInfo('SAPRFC', f"通信错误 - {rfc_name}: {e}")
            raise
        except pyrfc.LogonError as e:
            usprint.printInfo('SAPRFC', f"登录错误 - {rfc_name}: {e}")
            raise
        except Exception as e:
            usprint.printInfo('SAPRFC', f"调用 {rfc_name} 失败: {e}")
            raise

    def close(self):
        """关闭SAP连接"""
        try:
            if self.connection:
                self.connection.close()
                usprint.printInfo('SAPRFC', "SAP连接已关闭")
        except Exception as e:
            usprint.printInfo('SAPRFC', f"关闭连接异常: {e}")

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass







# ---------- 公共参数校验(posting / query 共用) ----------
def validate_deduct_params(data):
    """校验半成品扣料接口的公共参数(plant_code / year / period)

    :param data: 请求里的 data 字典(即 body["data"])
    :return: (is_valid, message, params)
        params 成功时为 {"plant_code", "year", "period"}; 失败为 {}
    """
    if not isinstance(data, dict) or not data:
        return False, "请求数据(data)为空或格式错误", {}

    plant_code = data.get("plant_code")
    year = data.get("year")
    period = data.get("period")

    plant_code = plant_code.strip() if isinstance(plant_code, str) else plant_code
    year = str(year).strip() if year is not None else ""
    period = str(period).strip() if period is not None else ""

    missing = []
    if not plant_code:
        missing.append("plant_code(工厂代码)")
    if not year:
        missing.append("year(年度)")
    if not period:
        missing.append("period(期间)")
    if missing:
        return False, f"缺少必填参数: {'、'.join(missing)}", {}

    if not (year.isdigit() and len(year) == 4):
        return False, f"年度(year)应为4位数字, 当前: {year!r}", {}

    if not period.isdigit():
        return False, f"期间(period)必须为数字, 当前: {period!r}", {}
    period_num = int(period)
    if period_num < 1 or period_num > 12:
        return False, f"期间(period)必须在1-12之间, 当前: {period}", {}
    period = f"{period_num:02d}"

    params = {"plant_code": str(plant_code), "year": year, "period": period}
    return True, "校验通过", params


# 半成品扣料推送 按钮
@calc_time
def semiproduct_deduct_push():
    """半成品扣料推送接口 按钮
    task_id 603
    """
    print("===半成品扣料推送接口===")
    req = Request()
    res = Response()
    body = json.loads(req.body())
    print("body---", body)
    user_id = req.header("user_id")

    payload = body.get("data") or {}
    task_id = payload.get("task_id") or 603

    # 公共参数校验, 失败直接返回
    ok, msg, params = validate_deduct_params(payload)
    if not ok:
        response = {"code": 500, "type": "E", "msg": msg}
        print(f"===半成品扣料推送接口=== 参数校验失败: {msg}")
        res.set_body(json.dumps(response))
        res.commit(True)
        return
  
    res_bus = semiproduct_deduct_push_core(
        user_id, task_id, params["year"], params["period"], params["plant_code"]
    )
    print(f"===半成品扣料推送接口=== 处理结束!!! 返回: {res_bus}")
    res.set_body(json.dumps(res_bus))
    res.commit(True)


@calc_time
def semiproduct_deduct_push_core(user_id, task_id, year, period, plant_code):
    """半成品扣料推送 核心逻辑(604 core)
    查待推送扣料记录, 一次性合并调 SAP 货物移动 RFC, 回写结果, 回查最新状态。
    :return: {"code", "msg", "data", "display"}
    """
    code, msg = 200, "无可推送记录"
    body = {"data": {"year": year, "period": period, "plant_code": plant_code}}
    print(f"===半成品扣料推送 core=== user_id={user_id} task_id={task_id} "
          f"plant_code={plant_code} {year}-{period}")

    # 查询待推送记录
    records = get_pending_list(plant_code, year, period)
    print("待推送记录--", records)
    # 按 id 去重
    push_dict = {}
    unique_records = []
    for record in records:
        record_id = record.get("id")
        if record_id and not push_dict.get(record_id):
            push_dict[record_id] = record
            unique_records.append(record)
    # 正向(261)必须先于反向(262)传送, 同向按 id(创建先后)升序
    unique_records.sort(key=lambda r: (str(r.get("movement_type")) == MOVE_TYPE_NEG, r.get("id") or 0))

    print("去重后记录--", unique_records)
    record_cnt = len(unique_records)
    # ===== 一次性全推送: 先 INSERT Oracle 中间表, 再一次调 RFC =====
    if record_cnt:
        ip_index = generate_ipindex()
        try:
            # 1) 先把扣料明细写入 SAP 中间表 ZMES_MM_GOODSREC_MHXT(PROCESS_FLG=5)
            insert_mid_table(unique_records, ip_index)
            # 1.5) INSERT 后回查开始/结束 时间字段(DATUM_B/DATUM_E/UZEIT_B/UZEIT_E)
            query_mid_table_times(ip_index)
            # 2) 用同一个 IP_INDEX 调 SAP 货物移动 RFC
            sap_send_data = prepare_gm_request(unique_records, ip_index)
            sap_resp = send_gm_request(sap_send_data)
            resp = extract_gm_response(sap_resp)
            stat = str(resp.get("stat"))
            # 整批共用一个物料凭证号, 逐条回写
            update_summary_result(unique_records, resp)
            if stat == "2":
                code, msg = 200, f"推送成功 {record_cnt} 条"
            else:
                code = 206
                ret_msg = resp.get("msg") or "SAP返回失败"
                msg = f"推送失败 {record_cnt} 条; {ret_msg}"
        except Exception as e:
            traceback.print_exc()
            code = 206
            msg = f"推送异常 {record_cnt} 条; {e}"
            # 异常时把整批置为失败
            fail_resp = {"mat_doc": "", "doc_year": "", "msg": str(e), "stat": "D"}
            update_summary_result(unique_records, fail_resp)
    # 回查最终状态(供前端刷新表格)
    data, display = semiproduct_deduct_query_data(body)
    return {"code": code, "msg": msg, "data": data, "display": display}


# 半成品扣料 查询接口
@calc_time
def semiproduct_deduct_query():
    """半成品扣料查询接口
    支持 _payload_ 里的 filter_info / sort_info / page / export_excel
    """
    print("===半成品扣料查询接口===")
    req = Request()
    res = Response()
    body = json.loads(req.body())
    print("body----", body)

    # 公共参数校验(plant_code/year/period), 失败直接返回
    ok, msg, _ = validate_deduct_params(body.get("data") or {})
    if not ok:
        response = {"code": 500, "type": "E", "msg": msg}
        print(f"===半成品扣料查询接口=== 参数校验失败: {msg}")
        res.set_body(json.dumps(response))
        res.commit(True)
        return

    payload = body.get("_payload_", {})
    filter_info = payload.get("filter_info", {})
    sort_info = payload.get("sort_info", {})
    export_excel = payload.get("export_excel")

    query_data, display = semiproduct_deduct_query_data(body)
    if export_excel:
        stamp_suffix = datetime.now().strftime("%Y%m%d%H%M%S")
        excel_filename = f"半成品扣料-{stamp_suffix}.xlsx"
        format_data = [{"sheet1": query_data}]
        field_dict = display_to_entozh(display)
        GetExportData(format_data, excel_filename, field_dict)
    else:
        page_size = payload.get("page", {}).get("page_size", 0)
        page_num = payload.get("page", {}).get("page_num", 1)
        paginator = Paginator(query_data, page_size)
        page_items = paginator.get_page(page_num)
        total_pages = paginator.total_pages
        data_sum = len(query_data)

        response = {
            "code": 200,
            "msg": "成功",
            "data": page_items,
            "page": {
                "page_size": page_size if page_size else len(query_data),
                "page_num": page_num,
                "page_sum": total_pages,
                "data_sum": data_sum,
            },
            "rule": {"sort_info": sort_info, "filter_info": filter_info},
            "display": display,
        }
        print(f"===半成品扣料查询接口=== 处理结束!!! 返回: {response}")
        res.set_body(json.dumps(response))
        res.commit(True)


# 半成品扣料 查询核心逻辑(查询接口/导出/推送回查复用)
def semiproduct_deduct_query_data(body):
    """查 t_co_summary_report 半成品扣料明细
    :return: (query_data, display)
    """
    data_filter = body.get("data") or {}
    payload = body.get("_payload_", {})
    filter_info = payload.get("filter_info", {})
    sort_info = payload.get("sort_info", {})

    # 前置筛选: 工厂/年度/期间/移动类型/物料编码
    prefix_filter = {}
    for field in ("plant_code", "year", "period", "movement_type", "mat_code"):
        val = data_filter.get(field)
        if val not in (None, ""):
            prefix_filter[field] = val

    columns = '''`id`,
                `prodosn`,
                `summary_line`,
                `movement_type`,
                `plant_code`,
                `mat_code`,
                `consump_qty`,
                `basic_uom`,
                `batch_sn`,
                `stor_loc_code`,
                `special_inventory_status`,
                `summary_date`,
                `cost_center`,
                `cost_element`,
                `create_id`,
                `create_time`'''

    query_sql = f'''
            SELECT
                {columns}
            FROM
                `{SOURCE_TABLE}`
            WHERE 1=1
        '''

    table_alias = create_table_alias(columns)
    where_sql, sort_sql = generate_raw_sql(prefix_filter, filter_info, sort_info, table_alias)
    if not sort_sql:
        sort_sql = " ORDER BY `id` ASC"
    if where_sql:
        where_sql = where_sql.replace("WHERE ", " AND ")
        full_query_sql = query_sql + where_sql + sort_sql
    else:
        full_query_sql = query_sql + sort_sql
    full_query_sql = full_query_sql.replace("    ", " ").strip()
    print(full_query_sql)
    query_data = db.query_sql(full_query_sql)

    display = [
        {"field": "prodosn", "description": "生产订单号"},
        {"field": "summary_line", "description": "汇总行号"},
        {"field": "movement_type", "description": "移动类型"},
        {"field": "plant_code", "description": "工厂代码"},
        {"field": "mat_code", "description": "物料编码"},
        {"field": "consump_qty", "description": "消耗数量"},
        {"field": "basic_uom", "description": "基本单位"},
        {"field": "batch_sn", "description": "批次号"},
        {"field": "stor_loc_code", "description": "库存地点"},
        {"field": "special_inventory_status", "description": "特殊库存状态"},
        {"field": "summary_date", "description": "数据汇总日期"},
        {"field": "cost_center", "description": "成本中心"},
        {"field": "cost_element", "description": "成本要素"},
    ]

    return query_data, display


# ---------- SAP 货物移动 组装/发送/解析/回写 ----------
def get_pending_list(plant_code, year, period):
    """查询待推送的半成品扣料记录
              目前按 t_co_summary_report 的 plant/year/period + 移动类型261/262 取,
              并以结果表 status != '2' 作为待推送。
    :return: list[dict]
    """
    cond = (
        f" AND `plant_code`='{plant_code}'"
        f" AND `year`='{year}'"
        f" AND `period`='{period}'"
        f" AND `movement_type` IN ('{MOVE_TYPE_POS}', '{MOVE_TYPE_NEG}')"
        f" ORDER BY `id` ASC"
    )
    cols = (
        "`id`,`prodosn`,`summary_line`,`movement_type`,`plant_code`,`mat_code`,"
        "`consump_qty`,`basic_uom`,`batch_sn`,`stor_loc_code`,"
        "`special_inventory_status`,`summary_date`"
    )
    # cond = (
    #     f" AND `plant_code`='{plant_code}'"
    #     f" AND `year`='{year}'"
    #     f" AND `period`='{period}'"
    #     f" ORDER BY `id` ASC"
    # )
    # cols = (
    #     "`id`,`prodosn`,`summary_line`,`plant_code`,`mat_code`,"
    #     "`consump_qty`,`basic_uom`,`batch_sn`,`stor_loc_code`,"
    #     "`special_inventory_status`,`summary_date`"
    # )
    data = query_db_records_by_cond(db, SOURCE_TABLE, cond, cols)
    print("查询待推送半成品扣料记录--", data)
    return data


def prepare_gm_request(records, ip_index):
    """组装 SAP 货物移动请求(ZRFC_MM_GNRTRANS_RACQ)

    入参(按文档):
      P_HEADER  : 抬头 {PSTNG_DATE, DOC_DATE, HEADER_TXT}
      P_CODE    : {GM_CODE: '03'}
      P_IPINDEX : 序列编码(与中间表 INSERT 共用同一个)
      P_BUKRS   : 'RACQ'
      P_ITEM    : 行项目表(每条记录一行)
    """
    if not records:
        return {}

    head_fields = build_gm_header(records)
    item_table = [build_gm_item(record, idx) for idx, record in enumerate(records, start=1)]

    sap_send_data = {
        "P_HEADER": head_fields,
        "P_CODE": {"GM_CODE": GM_CODE},
        "P_IPINDEX": ip_index,
        "P_BUKRS": BUKRS,
        "P_ITEM": item_table,
    }
    print("组装SAP 货物移动请求数据完成---", sap_send_data)
    return sap_send_data


def insert_mid_table(records, ip_index):
    """把扣料明细写入 Oracle 中间表 ZMES_MM_GOODSREC_MHXT(PROCESS_FLG=5)

    一批记录共用同一个 IP_INDEX, 用 ZCOUNT(1..N) 区分行项目。
    通过 ZZEXT_OracleHandle(OracleDB) 操作中间库, 连接与 schema 均走 oracle.* 配置。
    说明: IP_INDEX 每次推送都新生成(generate_ipindex, 时间戳唯一), 不与历史记录冲突,
          故无需 DELETE 旧记录(Oracle 账号无删除权限); 失败遗留的 PROCESS_FLG=5 行
          不会被新 IP_INDEX 命中, 不影响重推。
    :return: 受影响行数; 写入失败抛异常。
    """
    schema = get_schema()
    # 远程中间表引用方式(按实际报错切换):
    #   1) schema 前缀:     table = "{s}.{t}".format(s=schema, t=MID_TABLE)   ← 当前
    #   2) 裸名(走同义词):  table = MID_TABLE
    #   3) dblink:          table = "{t}@{s}".format(t=MID_TABLE, s=schema)
    table = "{s}.{t}".format(s=schema, t=MID_TABLE) if schema else MID_TABLE
    oracle = OracleDB()
    try:
        now = datetime.now()
        datum, uzeit = now.strftime("%Y%m%d"), now.strftime("%H%M%S")

        # 中间表是远程表(经 dblink/网关), INSERT ALL...SELECT 与 DDL 都不被支持(ORA-02021),
        # 故改为逐行单条 INSERT INTO ... VALUES。
        row_count = 0
        for idx, record in enumerate(records, start=1):
            row = {
                "MANDT": MANDT or "",
                "IP_NO": IP_NO,
                "IP_INDEX": ip_index,
                "AUFNR": record.get("prodosn", ""),
                # 文档: ZCOUNT ← summary_line(与返回 P_WLPZ.ZEILE 同源); 缺失才用序号兜底
                "ZCOUNT": record.get("summary_line") if record.get("summary_line") not in (None, "") else idx,
                "BWART": str(record.get("movement_type") or "").strip() or MOVE_TYPE_POS,
                "WERKS": record.get("plant_code", "") or PLANT_DEFAULT,
                "MATNR": record.get("mat_code", ""),
                "ERFMG": _parse_amount(record.get("consump_qty")),
                "ERFME": record.get("basic_uom", ""),
                "CHARG": record.get("batch_sn", ""),
                "ZUSER": record.get("create_id", ""),
                # "DATUM_B": datum,
                # "UZEIT_B": uzeit,
                "ZDATE": datum,
                "ZTIME": uzeit,
                "BUKRS": BUKRS,
                "USRID": USRID,
                "PROCESS_FLG": PROCESS_FLG_INIT,
                "LGORT": STGE_LOC_DEFAULT,
            }
            vals = []
            for col in MID_TABLE_COLUMNS:
                v = row[col]
                if col in ("ERFMG", "ZCOUNT"):
                    vals.append(str(v))                       # 数值列: 裸数字字面量
                else:
                    vals.append(repr(str(v)) if v not in (None, "") else "NULL")
            
            # owner = oracle.query("SELECT owner FROM all_tables WHERE table_name = 'ZMES_MM_GOODSREC_MHXT'")
            # print("owner----", owner)
            print('vals-------',vals)
            insert_sql = "insert into {t} ({cols}) values ({v})".format(
                t=table, cols=",".join(MID_TABLE_COLUMNS), v=",".join(vals))

            # print("执行sql命令", insert_sql)
            n = oracle.execute(insert_sql)
            print("n-------",n)
            if not n:
                raise Exception("中间表 {tbl} 写入失败(ip_index={ip}, 第{idx}行)".format(
                    tbl=MID_TABLE, ip=ip_index, idx=idx))
            row_count += n
        if not row_count:
            raise Exception("中间表 {tbl} 写入失败(ip_index={ip})".format(tbl=MID_TABLE, ip=ip_index))
        print("中间表 {tbl} 写入成功(ip_index={ip}, 影响行数={n})".format(tbl=MID_TABLE, ip=ip_index, n=row_count))
        return row_count
    finally:
        oracle.close()


def query_mid_table_times(ip_index):
    """INSERT 后回查中间表 ZMES_MM_GOODSREC_MHXT 的开始/结束 日期时间四字段

       DATUM_B/UZEIT_B = 开始日期/时间; DATUM_E/UZEIT_E = 结束日期/时间。
       用于核对入库后这四个字段的实际取值(秘火写入 / SAP 回写 / 触发器填充)。
    :return: list[dict], 每行含 DATUM_B/DATUM_E/UZEIT_B/UZEIT_E。
    """
    schema = get_schema()
    table = "{s}.{t}".format(s=schema, t=MID_TABLE) if schema else MID_TABLE
    sql = (
        "SELECT DATUM_B, DATUM_E, UZEIT_B, UZEIT_E, ZDATE, ZTIME,UPDATE_DATE, UPDATE_TIME"
        " FROM {t}"
        " WHERE IP_INDEX = '{ip}'"
        " ORDER BY ZCOUNT"
    ).format(t=table, ip=ip_index)
    oracle = OracleDB()
    try:
        # Oracle 数据库当前时间(便于和时间字段对比时区/写入时刻)
        now_row = oracle.query(
            "SELECT TO_CHAR(SYSDATE, 'YYYY-MM-DD HH24:MI:SS') AS NOW FROM DUAL"
        )
        print("===Oracle 当前时间=== {n}".format(n=now_row))
        rows = oracle.query(sql)
        print("===中间表时间字段回查(ip_index={ip})=== {r}".format(ip=ip_index, r=rows))
        return rows
    finally:
        oracle.close()


def build_gm_header(records):
    """组装抬头 P_HEADER: 记账日期/凭证日期取首条 summary_date, 抬头文本"""
    first = records[0] or {}
    posting_date = _to_ymd(first.get("summary_date")) or datetime.now().strftime("%Y%m%d")
    return {
        "PSTNG_DATE": posting_date,                 # 记账日期 YYYYMMDD
        "DOC_DATE": posting_date,                   # 凭证日期 YYYYMMDD
        "HEADER_TXT": f"半成品扣料{posting_date}",   # 抬头文本(<=25)
    }


def build_gm_item(record, idx):
    """组装 P_ITEM 行(半成品: 含 ORDERID 生产订单号)

    MOVE_TYPE 取记录 movement_type(261/262); 缺失按正向 261 兜底。
    """
    move_type = str(record.get("movement_type") or "").strip() or MOVE_TYPE_POS
    return {
        "MATERIAL": str(record.get("mat_code", "") or ""),        # 物料编码
        "PLANT": str(record.get("plant_code", "") or PLANT_DEFAULT),  # 工厂(文档固定 RAC1)
        "STGE_LOC": str(record.get("stor_loc_code", "") or STGE_LOC_DEFAULT),  # 库存地点
        "BATCH": str(record.get("batch_sn", "") or ""),           # 批次
        "MOVE_TYPE": move_type,                                    # 移动类型 261/262
        "STCK_TYPE": str(record.get("special_inventory_status", "") or ""),  # 库存类型
        # "MOVE_REAS": "",                                           # 移动原因(空)
        "ENTRY_QNT": _parse_amount(record.get("consump_qty")),    # 数量
        "ENTRY_UOM": str(record.get("basic_uom", "") or ""),      # 单位
        "ORDERID": str(record.get("prodosn", "") or ""),          # 订单编号(SAP工单号)
    }


def generate_ipindex():
    """生成 IP_INDEX: HMH + YYMMDD + 5位流水(共14位)

       格式: HMH(3) + 年2(YY) + 月2(MM) + 日2(DD) + 流水5 = 14 位(中间表 IP_INDEX 列宽 14)。
       唯一性: HMH 前缀区分系统, 避免与其他系统 IP_INDEX 冲突; 流水号保证同日内不重复。
       流水号需全局唯一, 正式应取中间表最大流水+1 或独立序列;
               这里先用时间戳末5位兜底, 仅供联调。
    """
    now = datetime.now()
    seq = str(int(now.timestamp()) % (10 ** IPINDEX_SEQ_WIDTH)).zfill(IPINDEX_SEQ_WIDTH)
    return f"{IPINDEX_PREFIX}{now.strftime('%y%m%d')}{seq}"

def send_gm_request(sap_send_data):
    """调用 SAPRFC 推送 ZRFC_MM_GNRTRANS_RACQ"""
    sap_resp = SAPRFC().call(INTERFACE_CODE, sap_send_data)
    print(f"===货物移动RFC返回结果===: {sap_resp}")
    return sap_resp


def extract_gm_response(sap_resp):
    """解析 SAP 返回 P_RETURN(物料凭证/年度/状态/消息)

    :return: dict {mat_doc, doc_year, stat, msg}
             stat: '2' 成功 / 'D' 失败
    """
    print("货物移动RFC返回结果---", sap_resp)
    sap_resp = sap_resp or {}
    p_return = sap_resp.get("P_RETURN") or {}

    def pick(*keys, default=""):
        for k in keys:
            val = sap_resp.get(k)
            if val is None or val == "":
                val = p_return.get(k)
            if val is not None and val != "":
                return val
        return default

    return {
        "mat_doc": pick("MAT_DO", "MATDOC"),    # 物料凭证编号
        "doc_year": pick("DOC_YEAR"),           # 物料凭证年度
        "stat": str(pick("STAT", default="D")), # 2 成功 / D 失败
        "msg": pick("MSG"),                     # 操作信息
    }


def update_summary_result(records, resp):
    """回写 t_co_summary_result: 物料凭证号/年度/状态/消息
     result 表的关联键与字段以实际表结构为准,
              目前按 (prodosn + summary_line) 更新, 字段用文档映射。
    """
    if not records:
        return
    mat_doc = resp.get("mat_doc", "")
    doc_year = resp.get("doc_year", "")
    stat = resp.get("stat", "D")
    msg = (resp.get("msg", "") or "")[:65535]
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for record in records:
        prodosn = record.get("prodosn", "")
        summary_line = record.get("summary_line", "")
        if not prodosn:
            continue
        cond = f" AND `prodosn`='{prodosn}' AND `summary_line`='{summary_line}'"
        data = {
            "associated_doc_sn": mat_doc,
            "year": doc_year,
            "status": stat,
            "post_account_msg": msg,
            "update_time": now_str,
        }
        cols = ("associated_doc_sn", "year", "status", "post_account_msg", "update_time")
        update_db_record_by_cond(db, RESULT_TABLE, cond, cols, data)
    db.dbCommit()


# ---------- 工具 ----------
def _parse_amount(value):
    """数值转 float, 空值当 0"""
    try:
        return float(value) if value not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0 


def _to_ymd(date_value):
    """日期格式化为 YYYYMMDD, 失败返回空串"""
    if not date_value:
        return ""
    if isinstance(date_value, datetime):
        return date_value.strftime("%Y%m%d")
    try:
        text = str(date_value).replace("-", "").replace("/", "").replace(":", "").strip()
        return text[:8]
    except Exception:
        return ""
    



# ==================== Test ====================
Text_semiproduct_deduct_push_payload = {
    "_payload_": {
        "sort_info": [],
        "filter_info": {},
        "group_info": [],
        "statistic_info": [],
        "page": {"page_size": 0, "page_num": 1},
        "export_excel": "false"
    },
    "data": {
        "plant_code": "RAC1",
        "year": "2026",
        "period": "06",
        "task_id": 605
    }
}




@calc_time
def Text_semiproduct_deduct_push():
    """半成品扣料推送接口 测试
    task_id 603
    """
    print("===半成品扣料推送接口===")
    user_id = 'testuser'
    payload = Text_semiproduct_deduct_push_payload.get("data") or {}
    task_id = payload.get("task_id") or 603

    # 公共参数校验, 失败直接返回
    ok, msg, params = validate_deduct_params(payload)
    if not ok:
        print(f"===半成品扣料推送接口=== 参数校验失败: {msg}")
        return
    res_bus = semiproduct_deduct_push_core(
        user_id, task_id, params["year"], params["period"], params["plant_code"]
    )
    print(f"===半成品扣料推送接口=== 处理结束!!! 返回: {res_bus}")
    return res_bus

if __name__ == "__main__":
    Text_semiproduct_deduct_push()