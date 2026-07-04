# -*- coding: UTF-8 -*-
"""
@File    : ZZ_semiproduct_deduct_push_class.py
@Author  : yang.zhang@dxdstech.com
@Date    : 2026/07/01
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
from logger import LoggerConfig
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
from ZZEXT_SapRFC import SAPRFC

usprint = LoggerConfig()


class SemiproductDeductPush:
    # ---------- 固定值(集中维护) ----------
    # SAP接口编码 / RFC函数名
    INTERFACE_CODE = "ZRFC_MM_GNRTRANS_RACQ"
    INTERFACE_NAME = "半成品扣料推送接口"

    # MES与SAP接口编号 / 中间表
    IP_NO = "MES_MM_004"
    MID_TABLE = "ZMES_MM_GOODSREC_MHXT"            # Oracle 中间表(秘火先 INSERT, 再调 RFC)

    PROCESS_FLG_INIT = "5"                    # 秘火写入中间表时的初始状态(SAP 成功置 2 / 失败置 D)
    MANDT = get_cnf("rfc.client")             # SAP 集团号(=RFC client, 生产 801 / 测试 500)

    # 中间表数据
    MID_TABLE_COLUMNS = [
        "MANDT", "IP_NO", "IP_INDEX", "AUFNR", "ZCOUNT", "BWART", "WERKS", "MATNR",
        "ERFMG", "ERFME", "CHARG", "ZUSER", "ZDATE", "ZTIME", "BUKRS", "USRID", "PROCESS_FLG", "LGORT",
    ]

    # BAPI 货物移动事务代码 / 公司代码 / 工厂 / 存储地点
    GM_CODE = "11"                      # P_CODE.GM_CODE 固定值(MB1A)
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

    def __init__(self):
        self.db = DbHelper()
        self.movement_type = ""   # 本次推送移动类型(_push_core 赋值, _insert_mid_table/_build_gm_item 读取)

    # ==================== 公共入口(按钮) ====================
    def push(self, body):
        """半成品扣料推送接口: 传入 body, 返回 {code,msg,data,display}

        :param body: 请求体(dict; 传 JSON 字串会自动 json.loads)
        :param user_id: 操作人 id(仅用于日志, 默认 0)
        :return: 成功/失败 {"code","msg","data","display"};
                 参数校验失败返回 {"code":500,"msg":..,"data":None}
        """
        print("===半成品扣料推送接口===")
        if isinstance(body, str):
            body = json.loads(body)
        payload = body
        task_id = payload.get("task_id") or 603

        # 公共参数校验, 失败直接返回
        ok, msg, params = self._validate_deduct_params(payload)
        if not ok:
            print(f"===半成品扣料推送接口=== 参数校验失败: {msg}")
            return {"code": 500, "msg": msg, "data": None}

        # body 为扁平结构, summary_unique_number/summary_type 指定本次推送的汇总单
        # (缺省时退化为按 plant/year/period 推全部待推)
        summary_unique_number = payload.get("summary_unique_number") or ""
        summary_type = payload.get("summary_type")
        movement_type = payload.get("movement_type")

        res_bus = self._push_core(
            "0", task_id, params["year"], params["period"], params["plant_code"],
            summary_unique_number=summary_unique_number, summary_type=summary_type,
            movement_type=movement_type,
        )
        print(f"===半成品扣料推送接口=== 处理结束!!! 返回: {res_bus}")
        return res_bus

    def query(self, body):
        """半成品扣料查询接口: 传入 body, 返回 {code,msg,data,page,rule,display}

        支持 _payload_ 里的 filter_info / sort_info / page / export_excel
        :param body: 请求体(dict; 传 JSON 字串会自动 json.loads)
        :param user_id: 操作人 id(仅用于日志, 默认 0)
        :return: 分页结果 dict; 参数校验失败返回 {"code":500,"msg":..,"data":None};
                 export_excel 时触发文件下载并返回 None
        """
        print("===半成品扣料查询接口===")
        if isinstance(body, str):
            body = json.loads(body)
        # 公共参数校验(plant_code/year/period), 失败直接返回
        ok, msg, _ = self._validate_deduct_params(body.get("data") or {})
        if not ok:
            print(f"===半成品扣料查询接口=== 参数校验失败: {msg}")
            return {"code": 500, "msg": msg, "data": None}

        payload = body.get("_payload_", {})
        filter_info = payload.get("filter_info", {})
        sort_info = payload.get("sort_info", {})
        export_excel = payload.get("export_excel")

        query_data, display = self._query_data(body)
        if export_excel:
            stamp_suffix = datetime.now().strftime("%Y%m%d%H%M%S")
            excel_filename = f"半成品扣料-{stamp_suffix}.xlsx"
            format_data = [{"sheet1": query_data}]
            field_dict = display_to_entozh(display)
            GetExportData(format_data, excel_filename, field_dict)
            return None   # 已触发文件下载, 不再返回 JSON

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
        return response

    # ==================== 公共参数校验(posting / query 共用) ====================
    def _validate_deduct_params(self, data):
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

    # ==================== 推送核心 ====================
    def _push_core(self, user_id, task_id, year, period, plant_code,
                   summary_unique_number="", summary_type=None, movement_type=None):
        """半成品扣料推送 核心逻辑(604 core)
        查待推送扣料记录, 一次性合并调 SAP 货物移动 RFC, 回写结果, 回查最新状态

        :param summary_unique_number: 指定推送某张汇总单; 空则按 plant/year/period 推全部待推。
        :param summary_type: 配套的汇总类型(与 summary_unique_number 组成唯一键)。
        :param movement_type: 移动类型(261正向发料/262反向冲销), 决定本次可推送的过账状态。
        :return: {"code", "msg", "data", "display"}
        """
        code, msg = 500, "无可推送记录"
        body = {"data": {"year": year, "period": period, "plant_code": plant_code}}
        print(f"===半成品扣料推送 core=== user_id={user_id} task_id={task_id} "
              f"plant_code={plant_code} {year}-{period}")
        # 本次推送的移动类型(来自请求, 整批共用), 供 _insert_mid_table / _build_gm_item 传 SAP
        self.movement_type = str(movement_type or "").strip()

        # 查询待推送记录
        records = self._get_pending_list(plant_code, year, period, summary_unique_number, summary_type, movement_type)
        # 按 id 去重
        push_dict = {}
        unique_records = []
        for record in records:
            record_id = record.get("id")
            if record_id and not push_dict.get(record_id):
                push_dict[record_id] = record
                unique_records.append(record)
        # 正向(261)必须先于反向(262)传送, 同向按 id(创建先后)升序
        unique_records.sort(key=lambda r: (str(r.get("movement_type")) == self.MOVE_TYPE_NEG, r.get("id") or 0))
        record_cnt = len(unique_records)
        # ===== 一次性全推送: 先 INSERT Oracle 中间表, 再一次调 RFC =====
        if record_cnt:
            ip_index = self._generate_ipindex()
            try:
                # 1) 先把扣料明细写入 SAP 中间表 ZMES_MM_GOODSREC_MHXT(PROCESS_FLG=5)
                self._insert_mid_table(unique_records, ip_index)
                # 2) 用同一个 IP_INDEX 调 SAP 货物移动 RFC
                sap_send_data = self._prepare_gm_request(unique_records, ip_index)
                sap_resp = self._send_gm_request(sap_send_data)
                resp = self._extract_gm_response(sap_resp)
                stat = str(resp.get("stat"))
                # 整批共用一个物料凭证号, 回写结果表 + 源表(成功存3/失败存2)
                self._update_summary_result(unique_records, resp, year)
                if stat == "2":
                    code, msg = 200, f"推送成功 {record_cnt} 条"
                else:
                    code = 500
                    ret_msg = resp.get("msg") or "SAP返回失败"
                    msg = f"推送失败 {record_cnt} 条; {ret_msg}"
            except Exception as e:
                traceback.print_exc()
                code = 500
                msg = f"推送异常 {record_cnt} 条; {e}"
                # 异常时把整批置为失败
                fail_resp = {"mat_doc": "", "doc_year": "", "msg": str(e), "stat": "D"}
                self._update_summary_result(unique_records, fail_resp, year)
        # 回查最终状态(供前端刷新表格)
        data, display = self._query_data(body)
        return {"code": code, "msg": msg, "data": data, "display": display}

    # ==================== 查询 ====================
    def _query_data(self, body):
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
                    `{self.SOURCE_TABLE}`
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
        query_data = self.db.query_sql(full_query_sql)

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

    def _get_pending_list(self, plant_code, year, period, summary_unique_number="", summary_type=None, movement_type=None):
        """查询待推送的半成品扣料记录
                  按 t_co_summary_report 的 plant/year/period 取, 并按请求传入的 movement_type 区分可推送的过账状态:
                    movement_type=261(正向发料): posting_status IN ('1','2') 待推/失败可重推;
                    movement_type=262(反向冲销): posting_status='3' 只能冲销已过账成功的记录;
                    其它/未传:                 退化为 posting_status != '3'。
                  若传 summary_unique_number(可配 summary_type) 则只取该汇总单的明细。
        :return: list[dict]
        """
        cond = (
            f" AND `plant_code`='{plant_code}'"
            f" AND `year`='{year}'"
            f" AND `period`='{period}'"
        )
        # 按请求传入的 movement_type 决定可推送的过账状态(posting_status):
        #   261(正向发料) -> IN ('1','2'): 待推/失败可重推;
        #   262(反向冲销) -> = '3': 只能冲销正向已过账成功的记录;
        #   其它/未传     -> != '3': 兜底。
        mtype = str(movement_type) if movement_type not in (None, "") else ""
        if mtype == self.MOVE_TYPE_POS:
            cond += " AND `posting_status` IN ('1','2')"
        elif mtype == self.MOVE_TYPE_NEG:
            cond += " AND `posting_status`='3'"
        else:
            cond += " AND `posting_status`!='3'"
        if summary_unique_number:
            cond += f" AND `summary_unique_number`='{summary_unique_number}'"
        if summary_type not in (None, ""):
            cond += f" AND `summary_type`='{summary_type}'"
        cond += " ORDER BY `id` ASC"
        cols = (
            "`id`,`prodosn`,`summary_type`,`summary_unique_number`,`summary_line`,"
            "`movement_type`,`plant_code`,`mat_code`,"
            "`consump_qty`,`basic_uom`,`batch_sn`,`stor_loc_code`,"
            "`special_inventory_status`,`summary_date`"
        )
        data = query_db_records_by_cond(self.db, self.SOURCE_TABLE, cond, cols)
        return data

    # ==================== SAP 货物移动 组装/发送/解析/回写 ====================
    def _prepare_gm_request(self, records, ip_index):
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

        head_fields = self._build_gm_header(records)
        item_table = [self._build_gm_item(record, idx) for idx, record in enumerate(records, start=1)]

        sap_send_data = {
            "P_HEADER": head_fields,
            "P_CODE": {"GM_CODE": self.GM_CODE},
            "P_IPINDEX": ip_index,
            "P_BUKRS": self.BUKRS,
            "P_ITEM": item_table,
        }
        return sap_send_data

    def _insert_mid_table(self, records, ip_index):
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
        table = "{s}.{t}".format(s=schema, t=self.MID_TABLE) if schema else self.MID_TABLE
        oracle = OracleDB()
        try:
            now = datetime.now()
            datum, uzeit = now.strftime("%Y%m%d"), now.strftime("%H%M%S")
            # 远程表(dblink)不支持 INSERT ALL, 逐行单条 INSERT
            row_count = 0
            for idx, record in enumerate(records, start=1):
                row = {
                    "MANDT": self.MANDT or "",
                    "IP_NO": self.IP_NO,
                    "IP_INDEX": ip_index,
                    "AUFNR": record.get("prodosn", ""),
                    # 文档: ZCOUNT ← summary_line(与返回 P_WLPZ.ZEILE 同源); 缺失才用序号兜底
                    "ZCOUNT": record.get("summary_line") if record.get("summary_line") not in (None, "") else idx,
                    "BWART": self.movement_type,
                    "WERKS": record.get("plant_code", "") or self.PLANT_DEFAULT,
                    "MATNR": record.get("mat_code", ""),
                    "ERFMG": self._parse_amount(record.get("consump_qty")),
                    "ERFME": record.get("basic_uom", ""),
                    "CHARG": record.get("batch_sn", ""),
                    "ZUSER": record.get("create_id", ""),
                    "ZDATE": datum,
                    "ZTIME": uzeit,
                    "BUKRS": self.BUKRS,
                    "USRID": self.USRID,
                    "PROCESS_FLG": self.PROCESS_FLG_INIT,
                    "LGORT": self.STGE_LOC_DEFAULT,
                }
                vals = []
                for col in self.MID_TABLE_COLUMNS:
                    v = row[col]
                    if col in ("ERFMG", "ZCOUNT"):
                        vals.append(str(v))                       # 数值列: 裸数字字面量
                    else:
                        vals.append(repr(str(v)) if v not in (None, "") else "NULL")
                insert_sql = "insert into {t} ({cols}) values ({v})".format(
                    t=table, cols=",".join(self.MID_TABLE_COLUMNS), v=",".join(vals))
                n = oracle.execute(insert_sql)
                if not n:
                    raise Exception("中间表 {tbl} 写入失败(ip_index={ip}, 第{idx}行)".format(
                        tbl=self.MID_TABLE, ip=ip_index, idx=idx))
                row_count += n
            if not row_count:
                raise Exception("中间表 {tbl} 写入失败(ip_index={ip})".format(tbl=self.MID_TABLE, ip=ip_index))
            print("中间表 {tbl} 写入成功(ip_index={ip}, 影响行数={n})".format(
                tbl=self.MID_TABLE, ip=ip_index, n=row_count))
            return row_count
        finally:
            oracle.close()

    def _build_gm_header(self, records):
        """组装抬头 P_HEADER: 记账日期/凭证日期取首条 summary_date, 抬头文本"""
        first = records[0] or {}
        posting_date = self._to_ymd(first.get("summary_date")) or datetime.now().strftime("%Y%m%d")
        return {
            "PSTNG_DATE": posting_date,                 # 记账日期 YYYYMMDD
            "DOC_DATE": posting_date,                   # 凭证日期 YYYYMMDD
            "HEADER_TXT": f"半成品扣料{posting_date}",   # 抬头文本(<=25)
        }

    def _build_gm_item(self, record, idx):
        """组装 P_ITEM 行(半成品: 含 ORDERID 生产订单号)

        MOVE_TYPE 取本次请求传入的 movement_type(self.movement_type, 整批共用)。
        """
        move_type = self.movement_type
        return {
            "MATERIAL": str(record.get("mat_code", "") or ""),        # 物料编码
            "PLANT": str(record.get("plant_code", "") or self.PLANT_DEFAULT),  # 工厂(文档固定 RAC1)
            "STGE_LOC": str(record.get("stor_loc_code", "") or self.STGE_LOC_DEFAULT),  # 库存地点
            "BATCH": str(record.get("batch_sn", "") or ""),           # 批次
            "MOVE_TYPE": move_type,                                    # 移动类型 261/262
            "STCK_TYPE": str(record.get("special_inventory_status", "") or ""),  # 库存类型
            "ENTRY_QNT": self._parse_amount(record.get("consump_qty")),    # 数量
            "ENTRY_UOM": str(record.get("basic_uom", "") or ""),      # 单位
            "ORDERID": str(record.get("prodosn", "") or ""),          # 订单编号(SAP工单号)
        }

    def _generate_ipindex(self):
        """生成 IP_INDEX: HMH + YYMMDD + 5位流水(共14位)

           格式: HMH(3) + 年2(YY) + 月2(MM) + 日2(DD) + 流水5 = 14 位(中间表 IP_INDEX 列宽 14)。
           唯一性: HMH 前缀区分系统, 避免与其他系统 IP_INDEX 冲突; 流水号保证同日内不重复。
           流水号需全局唯一, 正式应取中间表最大流水+1 或独立序列;
                   这里先用时间戳末5位兜底, 仅供联调。
        """
        now = datetime.now()
        seq = str(int(now.timestamp()) % (10 ** self.IPINDEX_SEQ_WIDTH)).zfill(self.IPINDEX_SEQ_WIDTH)
        return f"{self.IPINDEX_PREFIX}{now.strftime('%y%m%d')}{seq}"

    def _send_gm_request(self, sap_send_data):
        """调用 SAPRFC 推送 ZRFC_MM_GNRTRANS_RACQ"""
        sap_resp = SAPRFC().call(self.INTERFACE_CODE, sap_send_data)
        return sap_resp

    def _extract_gm_response(self, sap_resp):
        """解析 Sap 返回(物料凭证/年度/状态/消息 + P_WLPZ 逐行明细)

        :return: dict {mat_doc, doc_year, stat, msg, p_wlpz}
                 mat_doc: 物料凭证号(取自 P_WLPZ 首行 MBLNR, 写入 associated_doc_sn);
                 p_wlpz : 逐行明细列表(每行含 MBLNR/DMBTR 等, 与推送行序一一对应);
                 stat   : '2' 成功 / 'D' 失败。
        """
        print("货物移动RFC返回结果---", sap_resp)
        sap_resp = sap_resp or {}
        p_return = sap_resp.get("P_RETURN") or {}
        p_doc = sap_resp.get("P_DOC") or {}
        p_wlpz = sap_resp.get("P_WLPZ") or []

        def pick(*keys, default=""):
            for k in keys:
                for src in (sap_resp, p_return, p_doc):
                    val = src.get(k)
                    if val is not None and val != "":
                        return val
            return default

        # 物料凭证号: 优先取 P_WLPZ 首行 MBLNR(=associated_doc_sn), 否则退到 MAT_DOC
        mblnr = str((p_wlpz[0].get("MBLNR") if p_wlpz else "") or "")
        if not mblnr:
            mblnr = str(pick("MAT_DOC", "MAT_DO", "MATDOC"))

        return {
            "mat_doc": mblnr,                       # 物料凭证号(=MBLNR)
            "doc_year": pick("DOC_YEAR"),           # 物料凭证年度
            "stat": str(pick("STAT", default="D")), # 2 成功 / D 失败
            "msg": pick("MSG"),                     # 操作信息
            "p_wlpz": p_wlpz,                       # 逐行明细(每行 MBLNR/DMBTR 等)
        }

    def _update_summary_result(self, records, resp, year=""):
        """回写结果表 + 源表: 物料凭证号(MBLNR)/金额(DMBTR)/年度/状态/消息
        状态映射: SAP 成功(stat='2') -> 表里存 3; 失败(stat='D'等) -> 表里存 2。
        两张表共用同一映射(由 _map_posting_status 统一换算):
        无需在调用方再单独处理。
        """
        if not records:
            return
        mat_doc = resp.get("mat_doc", "")
        doc_year = resp.get("doc_year", "")
        stat = resp.get("stat", "D")
        store_status = self._map_posting_status(stat)   # 成功->3 / 失败->2
        msg = (resp.get("msg", "") or "")[:65535]
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 源表 t_co_summary_report: 按主键 id 批量更新过账状态(成功3 / 失败2)
        ids = [str(r.get("id")) for r in records if r.get("id") is not None and str(r.get("id")) != ""]
        if ids:
            src_cond = " AND `id` IN ({})".format(",".join(ids))
            update_db_record_by_cond(self.db, self.SOURCE_TABLE, src_cond, ("posting_status",),
                                     {"posting_status": store_status})

        p_wlpz = resp.get("p_wlpz") or []
        update_cols = ("associated_doc_sn", "amount", "year", "status", "post_account_msg", "update_time")
        for idx, record in enumerate(records):
            # 结果表唯一键 (summary_type, summary_unique_number, summary_line); prodosn 不可用作定位键。
            summary_type = str(record.get("summary_type", "") or "")
            summary_unique_number = str(record.get("summary_unique_number", "") or "")
            summary_line = record.get("summary_line", "")
            if not summary_type or not summary_unique_number:
                continue
            key_cond = (
                f" AND `summary_type`='{summary_type}'"
                f" AND `summary_unique_number`='{summary_unique_number}'"
                f" AND `summary_line`='{summary_line}'"
            )
            wlpz = p_wlpz[idx] if idx < len(p_wlpz) else {}
            row_data = {
                "associated_doc_sn": str(wlpz.get("MBLNR") or mat_doc),  # 本行物料凭证号(缺失用批级兜底)
                "amount": self._parse_amount(wlpz.get("DMBTR")),         # 本行本币金额
                "year": doc_year or year,                                # 物料凭证年度优先, 缺失退到会计年度
                "status": store_status,
                "post_account_msg": msg,
                "update_time": now_str,
            }
            update_db_record_by_cond(self.db, self.RESULT_TABLE, key_cond, update_cols, row_data)

        self.db.dbCommit()

    @staticmethod
    def _map_posting_status(stat):
        """SAP 返回状态 -> 表里存的过账状态: 成功('2') 存 3, 失败('D'/其它) 存 2"""
        return "3" if str(stat) == "2" else "2"

    # ==================== 工具 ====================
    @staticmethod
    def _parse_amount(value):
        """数值转 float, 空值当 0"""
        try:
            return float(value) if value not in (None, "") else 0.0
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
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

@calc_time
def semiproduct_deduct_push(body):
    req = Request()
    res = Response()
    body = json.loads(req.body())
    result = SemiproductDeductPush().push(body)
    res.set_body(json.dumps(result))
    res.commit(True)



@calc_time
def semiproduct_deduct_query(body):
    req = Request()
    res = Response()
    body = json.loads(req.body())
    result = SemiproductDeductPush().query(body)
    if result is not None:   # export_excel 时 query 已直接触发文件下载, 不再写 JSON
        res.set_body(json.dumps(result))
        res.commit(True)


body = {'summary_unique_number': 'f0186d008156762431e8fb995a99a64e','movement_type':'261','summary_type': 11, 'plant_code': 'RAC1', 'period': '07', 'path': '', 'year': '2026'}


@calc_time
def Text_semiproduct_deduct_push():
    """半成品扣料推送接口 测试(直接走 class 入口, body 为模块级扁平字典)"""
    print("===半成品扣料推送接口 测试===")
    res_bus = SemiproductDeductPush().push(body)
    print(f"===半成品扣料推送接口 测试=== 处理结束!!! 返回: {res_bus}")
    return res_bus



if __name__ == "__main__":
    Text_semiproduct_deduct_push()

