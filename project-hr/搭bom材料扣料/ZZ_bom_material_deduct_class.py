# -*- coding: UTF-8 -*-

"""
@File    : ZZ_bom_material_deduct_class.py
@Author  : yang.zhang@dxdstech.com
@Date    : 2026/07/01
@explain : 搭BOM材料扣料

调用方向:   秘火->SAP
模块名称:   搭BOM材料扣料(成本中心领用)
接口名称:   搭BOM材料扣料接口
接口说明：  搭BOM材料扣料, 调 SAP 货物移动 RFC(ZRFC_MM_GNRTRANS_RACQ, MB1A),
            移动类型 201/Y01(正向领用)/202/Y02(反向冲销),
            并将物料凭证号/年度/状态/消息回写至 t_co_summary_result。
源表:       t_co_summary_report(扣料明细)
结果表:     t_co_summary_result(过账结果)
中间表:     ZMES_MM_GNRTRANS_MHXT (Oracle, 秘火先 INSERT PROCESS_FLG=5, 再调 RFC)
"""


import json
import traceback
from datetime import datetime

import pyrfc
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



class BomMaterialDeduct:


    # ---------- 固定值(按接口文档 v1.1, 集中维护) ----------
    # SAP接口编码 / RFC函数名
    INTERFACE_CODE = "ZRFC_MM_GNRTRANS_RACQ"
    INTERFACE_NAME = "搭BOM材料扣料接口"

    # MES与SAP接口编号 / 中间表
    IP_NO = "MES_MM_011"
    MID_TABLE = "ZMES_MM_GNRTRANS_MHXT"            # Oracle 中间表(秘火先 INSERT, 再调 RFC)
    PROCESS_FLG_INIT = "5"                    # 秘火写入中间表时的初始状态(SAP 成功置 2 / 失败置 D)
    MANDT = get_cnf("rfc.client")             # SAP 集团号(=RFC client, 生产 801 / 测试 500)

    # 中间表 ZMES_MM_GNRTRANS_MHXT 列(按接口文档 v1.1, 成本中心领用: 无 AUFNR, 含 INSMK/SAKTO/ZTEXT3/BUDAT)
    MID_TABLE_COLUMNS = [
        "MANDT", "IP_NO", "IP_INDEX", "ZCOUNT", "MATNR", "WERKS", "BWART",
        "INSMK", "ERFMG", "ERFME", "S_LGORT", "S_CHARG",
        "ZDATE", "ZTIME", "BUKRS", "USRID", "PROCESS_FLG",
        "ZTEXT3", "BUDAT",
    ]

    # BAPI 货物移动事务代码 / 公司代码 / 工厂
    # GM_CODE = "03"                      # P_CODE.GM_CODE 固定值 03(MB1A)
    GM_CODE = "11"                      # 在润工作上沟通过，
    BUKRS = "RACQ"                      # P_BUKRS 固定 RACQ
    PLANT_DEFAULT = "RAC1"              # 工厂(文档固定值 RAC1)
    USRID = "MH"                        # 用户名(文档固定 MH)

    # 移动类型: 201/Y01 正向领用 / 202/Y02 反向冲销
    MOVE_TYPE_POS_LIST = ("201", "Y01")
    MOVE_TYPE_NEG_LIST = ("202", "Y02")
    MOVE_TYPE_ALL = MOVE_TYPE_POS_LIST + MOVE_TYPE_NEG_LIST
    MOVE_TYPE_POS = "201"               # 缺失时兜底

    # 源表 / 结果表
    SOURCE_TABLE = "t_co_summary_report"
    RESULT_TABLE = "t_co_summary_result"

    # IP_INDEX 生成规则: HMH + YYMMDD + 5位流水(共14位)
    IPINDEX_PREFIX = "HMH"
    IPINDEX_SEQ_WIDTH = 5

    def __init__(self):
        self.db = DbHelper()

    # ==================== 公共入口(按钮) ====================
    def push(self, body):
        """搭BOM材料扣料接口: 传入 body, 返回 {code,msg,data,display}。

        :param body: 请求体(dict; 传 JSON 字串会自动 json.loads)。
        :param user_id: 操作人 id(仅用于日志, 默认 0)。
        :return: 成功/失败 {"code","msg","data","display"};
                 参数校验失败返回 {"code":500,"msg":..,"data":None}。
        """
        print("===搭BOM材料扣料接口===")
        if isinstance(body, str):
            body = json.loads(body)
        payload = body
        # 公共参数校验, 失败直接返回
        ok, msg, params = self._validate_deduct_params(payload)
        if not ok:
            print(f"===搭BOM材料扣料接口=== 参数校验失败: {msg}")
            return {"code": 500, "msg": msg, "data": None}

        # body 为扁平结构, summary_unique_number/summary_type 指定本次推送的汇总单
        # (缺省时退化为按 plant/year/period 推全部待推)
        summary_unique_number = payload.get("summary_unique_number") or ""
        summary_type = payload.get("summary_type")

        res_bus = self._push_core(params["year"], params["period"], params["plant_code"],
                                  summary_unique_number=summary_unique_number,
                                  summary_type=summary_type)
        print(f"===搭BOM材料扣料接口=== 处理结束!!! 返回: {res_bus}")
        return res_bus



    def query(self, body):
        """搭BOM材料扣料查询接口: 传入 body, 返回 {code,msg,data,page,rule,display}。

        支持 _payload_ 里的 filter_info / sort_info / page / export_excel。
        :param body: 请求体(dict; 传 JSON 字串会自动 json.loads)。
        :return: 分页结果 dict; 参数校验失败返回 {"code":500,"msg":..,"data":None};
                 export_excel 时触发文件下载并返回 None。
        """
        print("===搭BOM材料扣料查询接口===")
        if isinstance(body, str):
            body = json.loads(body)

        # 公共参数校验(plant_code/year/period), 失败直接返回
        ok, msg, _ = self._validate_deduct_params(body.get("data") or {})
        if not ok:
            print(f"===搭BOM材料扣料查询接口=== 参数校验失败: {msg}")
            return {"code": 500, "msg": msg, "data": None}

        payload = body.get("_payload_", {})
        filter_info = payload.get("filter_info", {})
        sort_info = payload.get("sort_info", {})
        export_excel = payload.get("export_excel")

        query_data, display = self._query_data(body)
        if export_excel:
            stamp_suffix = datetime.now().strftime("%Y%m%d%H%M%S")
            excel_filename = f"搭BOM材料扣料-{stamp_suffix}.xlsx"
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
        print(f"===搭BOM材料扣料查询接口=== 处理结束!!! 返回: {response}")
        return response

    # ==================== 公共参数校验(posting / query 共用) ====================
    def _validate_deduct_params(self, data):
        """校验搭BOM材料扣料接口的公共参数(plant_code / year / period)

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
    def _push_core(self, year, period, plant_code, summary_unique_number="", summary_type=None):
        """搭BOM材料扣料 核心逻辑(605 core)
        查待推送扣料记录, 一次性合并调 SAP 货物移动 RFC, 回写结果, 回查最新状态。

        :param summary_unique_number: 指定推送某张汇总单; 空则按 plant/year/period 推全部待推。
        :param summary_type: 配套的汇总类型(与 summary_unique_number 组成唯一键)。
        :return: {"code", "msg", "data", "display"}
        """
        code, msg = 200, "无可推送记录"
        body = {"data": {"year": year, "period": period, "plant_code": plant_code}}
        # 查询待推送记录
        records = self._get_pending_list(plant_code, year, period, summary_unique_number, summary_type)
        print("待推送记录--", records)
        # 按 id 去重
        push_dict = {}
        unique_records = []
        for record in records:
            record_id = record.get("id")
            if record_id and not push_dict.get(record_id):
                push_dict[record_id] = record
                unique_records.append(record)
        # 文档要求: 正向(201/Y01)必须先于反向(202/Y02)传送, 同向按 id(创建先后)升序
        unique_records.sort(key=lambda r: (str(r.get("movement_type")) in self.MOVE_TYPE_NEG_LIST, r.get("id") or 0))
        record_cnt = len(unique_records)
        # ===== 一次性全推送: 先 INSERT Oracle 中间表, 再一次调 RFC =====
        if record_cnt:
            ip_index = self._generate_ipindex()
            try:
                # 1) 先把扣料明细写入 SAP 中间表 ZMES_MM_GNRTRANS_MHXT(PROCESS_FLG=5)
                self._insert_mid_table(unique_records, ip_index)
                # 2) 用同一个 IP_INDEX 调 SAP 货物移动 RFC
                sap_send_data = self._prepare_gm_request(unique_records, ip_index)
                sap_resp = self._send_gm_request(sap_send_data)
                resp = self._extract_gm_response(sap_resp)
                stat = str(resp.get("stat"))
                # 整批共用一个物料凭证号, 回写结果表 + 源表(成功存3/失败存2)
                self._update_summary_result(unique_records, resp)
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
                self._update_summary_result(unique_records, fail_resp)
        # 回查最终状态(供前端刷新表格)
        data, display = self._query_data(body)
        return {"code": code, "msg": msg, "data": data, "display": display}



    # ==================== 查询 ====================
    def _query_data(self, body):
        """查 t_co_summary_report 搭BOM材料扣料明细
        :return: (query_data, display)
        """
        data_filter = body.get("data") or {}
        payload = body.get("_payload_", {})
        filter_info = payload.get("filter_info", {})
        sort_info = payload.get("sort_info", {})

        # 前置筛选: 工厂/年度/期间/移动类型/物料编码/成本中心
        prefix_filter = {}
        for field in ("plant_code", "year", "period", "movement_type", "mat_code", "cost_center"):
            val = data_filter.get(field)
            if val not in (None, ""):
                prefix_filter[field] = val

        columns = '''`id`,
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
        print(full_query_sql)
        query_data = self.db.query_sql(full_query_sql)

        display = [
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

    # ==================== SAP 货物移动 组装/发送/解析/回写 ====================
    def _get_pending_list(self, plant_code, year, period, summary_unique_number="", summary_type=None):
        """查询待推送的搭BOM材料扣料记录
                  按 t_co_summary_report 的 plant/year/period 取(不再按 movement_type 过滤;
                  movement_type 随 body 传, 仅推送 SAP 时用), 并以 posting_status != '3' 作为待推送
                  (成功存3, 不再重复推; 失败存2仍可重推)。
                  若传 summary_unique_number(可配 summary_type) 则只取该汇总单的明细。
        :return: list[dict]
        """
        cond = (
            f" AND `plant_code`='{plant_code}'"
            f" AND `year`='{year}'"
            f" AND `period`='{period}'"
            f" AND `posting_status`!='3'"
        )
        if summary_unique_number:
            cond += f" AND `summary_unique_number`='{summary_unique_number}'"
        if summary_type not in (None, ""):
            cond += f" AND `summary_type`='{summary_type}'"
        cond += " ORDER BY `id` ASC"
        cols = (
            "`id`,`summary_line`,`movement_type`,`plant_code`,`mat_code`,"
            "`consump_qty`,`basic_uom`,`batch_sn`,`stor_loc_code`,"
            "`special_inventory_status`,`summary_date`,`cost_center`,`cost_element`"
        )
        data = query_db_records_by_cond(self.db, self.SOURCE_TABLE, cond, cols)
        print("查询待推送搭BOM材料扣料记录--", data)
        return data

    def _prepare_gm_request(self, records, ip_index):
        """组装 SAP 货物移动请求(ZRFC_MM_GNRTRANS_RACQ)

        入参(按文档):
          P_HEADER  : 抬头 {PSTNG_DATE, DOC_DATE, HEADER_TXT}
          P_CODE    : {GM_CODE: '03'}
          P_IPINDEX : 序列编码(与中间表 INSERT 共用同一个)
          P_BUKRS   : 'RACQ'
          P_ITEM    : 行项目表(每条记录一行, 含 COSTCENTER/GL_ACCOUNT)
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
        print("组装SAP 货物移动请求数据完成---", sap_send_data)
        return sap_send_data

    def _insert_mid_table(self, records, ip_index):
        """把扣料明细写入 Oracle 中间表 ZMES_MM_GNRTRANS_MHXT(PROCESS_FLG=5)

        一批记录共用同一个 IP_INDEX, 用 ZCOUNT(1..N) 区分行项目。
        通过 ZZEXT_OracleHandle(OracleDB) 操作中间库, 连接与 schema 均走 zjk.* 配置。
        说明: IP_INDEX 每次推送都新生成(generate_ipindex, 时间戳唯一), 不与历史记录冲突,
              故无需 DELETE 旧记录(Oracle 账号无删除权限); 失败遗留的 PROCESS_FLG=5 行
              不会被新 IP_INDEX 命中, 不影响重推。
        :return: 受影响行数; 写入失败抛异常。
        """
        schema = get_schema()
        # 远程中间表引用方式
        #   1) schema 前缀:     table = "{s}.{t}".format(s=schema, t=MID_TABLE)   ← 当前
        #   2) 裸名(走同义词):  table = MID_TABLE
        #   3) dblink:          table = "{t}@{s}".format(t=MID_TABLE, s=schema)
        table = "{s}.{t}".format(s=schema, t=self.MID_TABLE) if schema else self.MID_TABLE
        oracle = OracleDB()
        try:
            now = datetime.now()
            datum, uzeit = now.strftime("%Y%m%d"), now.strftime("%H%M%S")

            # 中间表是远程表(经 dblink/网关), INSERT ALL...SELECT 与 DDL 都不被支持(ORA-02021),
            # 故改为逐行单条 INSERT INTO ... VALUES。
            row_count = 0
            for idx, record in enumerate(records, start=1):
                row = {
                    "MANDT": self.MANDT or "",
                    "IP_NO": self.IP_NO,
                    "IP_INDEX": ip_index,
                    # 文档: ZCOUNT ← summary_line; 缺失才用序号兜底
                    "ZCOUNT": record.get("summary_line") if record.get("summary_line") not in (None, "") else idx,
                    "MATNR": record.get("mat_code", ""),
                    "WERKS": record.get("plant_code", "") or self.PLANT_DEFAULT,
                    "BWART": str(record.get("movement_type") or "").strip() or self.MOVE_TYPE_POS,
                    "INSMK": record.get("special_inventory_status", ""),               # 库存类型(质检2/非限制F/冻结3)
                    "ERFMG": self._parse_amount(record.get("consump_qty")),
                    "ERFME": record.get("basic_uom", ""),
                    "S_LGORT": record.get("stor_loc_code", ""),
                    "S_CHARG": record.get("batch_sn", ""),
                    "ZDATE": datum,                                                     # 系统当前日期
                    "ZTIME": uzeit,                                                     # 系统当前时间
                    "BUKRS": self.BUKRS,
                    "USRID": self.USRID,
                    "PROCESS_FLG": self.PROCESS_FLG_INIT,
                    "ZTEXT3": record.get("cost_center", ""),                           # 成本中心(必填)
                    # "SAKTO": record.get("cost_element", ""),                           # 总账科目/成本要素
                    "BUDAT": self._to_ymd(record.get("summary_date")) or datum,         # 过账日期(汇总日期)
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
            "HEADER_TXT": f"搭BOM扣料{posting_date}",   # 抬头文本(<=25)
        }

    def _build_gm_item(self, record, idx):
        """组装 P_ITEM 行(搭BOM: 含 COSTCENTER 成本中心 + GL_ACCOUNT 成本要素, 无 ORDERID)
        MOVE_TYPE 取记录 movement_type(201/202/Y01/Y02); 缺失按正向 201 兜底。
        """
        move_type = str(record.get("movement_type") or "").strip() or self.MOVE_TYPE_POS
        return {
            "MATERIAL": str(record.get("mat_code", "") or ""),        # 物料编码
            "PLANT": str(record.get("plant_code", "") or self.PLANT_DEFAULT),  # 工厂(文档固定 RAC1)
            "STGE_LOC": str(record.get("stor_loc_code", "") or ""),   # 库存地点(无固定值)
            "BATCH": str(record.get("batch_sn", "") or ""),           # 批次
            "MOVE_TYPE": move_type,                                    # 移动类型 201/202/Y01/Y02
            "STCK_TYPE": str(record.get("special_inventory_status", "") or ""),  # 库存类型
            # "MOVE_REAS": "",                                           # 移动原因(空)
            "ENTRY_QNT": self._parse_amount(record.get("consump_qty")),    # 数量
            "ENTRY_UOM": str(record.get("basic_uom", "") or ""),      # 单位
            "COSTCENTER": str(record.get("cost_center", "") or ""),   # 成本中心
            "GL_ACCOUNT": str(record.get("cost_element", "") or ""),  # 总账科目/成本要素
        }

    def _generate_ipindex(self):
        """生成 IP_INDEX: HMH + YY + MM + DD + 5位流水(共14位)
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
        print(f"===货物移动RFC返回结果===: {sap_resp}")
        return sap_resp

    def _extract_gm_response(self, sap_resp):
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

    def _update_summary_result(self, records, resp):
        """回写结果表 + 源表: 物料凭证号/年度/状态/消息

        状态映射(新逻辑): SAP 成功(stat='2') -> 表里存 3; 失败(stat='D'等) -> 表里存 2。
        两张表共用同一映射(由 _map_posting_status 统一换算):
          t_co_summary_result.status         (按 summary_line 逐条更新)
          t_co_summary_report.posting_status (按 id 批量更新)

        本函数在 成功响应 / 失败响应 / 异常 三个路径都被调用, 故源表也会随之更新,
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

        # 结果表 t_co_summary_result: 按 summary_line 逐条更新
        for record in records:
            summary_line = record.get("summary_line", "")
            cond = f" AND `summary_line`='{summary_line}'"
            data = {
                "associated_doc_sn": mat_doc,
                "year": doc_year,
                "status": store_status,
                "post_account_msg": msg,
                "update_time": now_str,
            }
            cols = ("associated_doc_sn", "year", "status", "post_account_msg", "update_time")
            update_db_record_by_cond(self.db, self.RESULT_TABLE, cond, cols, data)
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
def bom_material_deduct_push(body):
    """搭BOM材料扣料接口 按钮(框架 HTTP 入口)
    其他文件可直接 BomMaterialDeduct().push(body) 拿 {code,msg,data,..}。
    """
    req = Request()
    res = Response()
    body = json.loads(req.body())
    result = BomMaterialDeduct().push(body)
    res.set_body(json.dumps(result))
    res.commit(True)


@calc_time
def bom_material_deduct_query(body):
    """搭BOM材料扣料查询接口(框架 HTTP 入口)"""
    req = Request()
    res = Response()
    body = json.loads(req.body())
    result = BomMaterialDeduct().query(body)
    res.set_body(json.dumps(result))
    res.commit(True)




body = {'summary_unique_number': '00f2f6c87dc03297f36ce2e201d95947','summary_type': 11, 'plant_code': 'RAC1', 'period': '07', 'path': '', 'year': '2026'}



@calc_time
def Text_bom_material_deduct_push():
    """搭BOM材料扣料推送接口 测试(直接走 class 入口, body 为模块级扁平字典)"""
    print("===搭BOM材料扣料推送接口 测试===")
    res_bus = BomMaterialDeduct().push(body)
    print(f"===搭BOM材料扣料推送接口 测试=== 处理结束!!! 返回: {res_bus}")
    return res_bus


if __name__ == "__main__":
    Text_bom_material_deduct_push()
