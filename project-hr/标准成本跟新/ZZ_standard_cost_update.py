# -*- coding: UTF-8 -*-
"""
@File    : ZZ_standard_cost_update.py
@Author  : yang.zhang@dxdstech.com
@Date    : 2026/06/18
@explain : 标准成本更新

  调用方向:   秘火->SAP
  模块名称:   标准成本更新
  接口名称:   标准成本更新接口
  接口说明：  标准成本更新, 调SAP (ZBAPI_MATVAL_PRICE_CHANGE)
             将标准成本数据推送至SAP进行更新,
             并将更新结果回写至 t_sap_mmd_standard_price。
    返回体 {code, msg, data, display}, _payload_ 过滤/排序/分页/导出。
"""
import json
import traceback
from datetime import datetime

from DbHelper import DbHelper
from libenhance import Request, Response
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
from ZZEXT_SapRFC import SAPRFC

usprint = LoggerConfig()


class StandardCostUpdate:
    # ---------- 固定值(按接口需求, 集中维护) ----------
    # SAP接口编码 / RFC函数名
    INTERFACE_CODE = "ZBAPI_MATVAL_PRICE_CHANGE"
    INTERFACE_NAME = "标准成本更新接口"

    P_RELEASE = "X"            # 需要解冻物料时, 传X
    VALUATION_VIEW = "0"       # 评估视图(NUMC类型), 两种货币类型行都固定传"0"(文档示例 0, 0)
    CURR_TYPES = ("10", "30")  # 10=公司代码货币, 30=集团公司记账货币; 需同时传两种

    # 业务表
    TABLE_NAME = "t_sap_mmd_standard_price"
    FINANCIAL_TABLE = "t_mmd_material_financial_data"   # 物料财务数据(含 plant_val_class 评估类, 按 mat_code+plant_code 关联)

    def __init__(self):
        self.db = DbHelper()

    # ==================== 公共入口(按钮) ====================
    def push(self, body, user_id=None):
        """标准成本更新接口: 传入 body, 返回 {code,msg,data,display}。

        :param body: 请求体(dict; 传 JSON 字串会自动 json.loads)。
        :param user_id: 操作人 id(优先取传入值, 缺省回退 body["user_id"]; 仅用于回写 update_id)。
        :return: 成功/失败 {"code","msg","data","display"};
                 参数校验失败返回 {"code":500,"type":"E","msg":..}。
        """
        print("===标准成本更新接口===")
        if isinstance(body, str):
            body = json.loads(body)
        payload = body
        user_id = user_id if user_id not in (None, "") else payload.get("user_id")
        task_id = payload.get("task_id")  # 仅日志关联用, 缺省为 None

        # 公共参数校验, 失败直接返回
        ok, msg, params = self._validate_standard_cost_params(payload)
        if not ok:
            print(f"===标准成本更新接口=== 参数校验失败: {msg}")
            return {"code": 500, "type": "E", "msg": msg}

        res_bus = self._push_core(
            user_id, task_id, params["year"], params["period"], params["plant_code"],
            params.get("mat_code"), params.get("plant_val_class"),
        )
        print(f"===标准成本更新接口=== 处理结束!!! 返回: {res_bus}")
        return res_bus


    def query(self, body):
        """标准成本更新查询接口: 传入 body, 返回 {code,msg,data,page,rule,display}。

        支持 _payload_ 里的 filter_info / sort_info / page / export_excel。
        :param body: 请求体(dict; 传 JSON 字串会自动 json.loads)。
        :return: 分页结果 dict; 参数校验失败返回 {"code":500,"type":"E","msg":..};
                 export_excel 时触发文件下载并返回 None。
        """
        print("===标准成本更新查询接口===")
        if isinstance(body, str):
            body = json.loads(body)

        # 公共参数校验(plant_code/year/period), 失败直接返回
        ok, msg, _ = self._validate_standard_cost_params(body.get("data") or {})
        if not ok:
            print(f"===标准成本更新查询接口=== 参数校验失败: {msg}")
            return {"code": 500, "type": "E", "msg": msg}

        payload = body.get("_payload_", {})
        filter_info = payload.get("filter_info", {})
        sort_info = payload.get("sort_info", {})
        export_excel = payload.get("export_excel")

        query_data, display = self._query_data(body)
        if export_excel:
            stamp_suffix = datetime.now().strftime("%Y%m%d%H%M%S")
            excel_filename = f"标准成本更新-{stamp_suffix}.xlsx"
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
        print(f"===标准成本更新查询接口=== 处理结束!!! 返回: {response}")
        return response

    # ==================== 公共参数校验(posting / query 共用) ====================
    def _validate_standard_cost_params(self, data):
        """校验标准成本更新接口的公共参数(plant_code / year / period)
        mat_code / plant_val_class 可选, 统一归一成 list[str](空则 [])。

        :param data: 请求里的 data 字典(即 body["data"])
        :return: (is_valid, message, params)
            params 成功时含 {"plant_code","year","period","mat_code","plant_val_class"}; 失败为 {}
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

        # mat_code / plant_val_class: 前端按多选传列表(也可能传单值/空), 统一归一成 list[str](去空)
        mat_code = self._normalize_list_param(data.get("mat_code"))
        plant_val_class = self._normalize_list_param(data.get("plant_val_class"))

        params = {
            "plant_code": str(plant_code),
            "year": year,
            "period": period,
            "mat_code": mat_code,                 # list[str], 空则 []
            "plant_val_class": plant_val_class,   # list[str], 空则 []
        }
        return True, "校验通过", params

    # ==================== 推送核心 ====================
    def _push_core(self, user_id, task_id, year, period, plant_code, mat_code=None, plant_val_class=None):
        """标准成本更新 核心逻辑(606 core)
        ZBAPI_MATVAL_PRICE_CHANGE 的 MATERIAL/VALUATIONAREA 均为标量参数, 单次只改一个物料,
        故逐条调用、回写, 最后回查最新状态。
        :param mat_code: list[str] 物料多选(空则不限); :param plant_val_class: list[str] 评估类多选(空则不限)。
        :return: {"code", "msg", "data", "display"}
        """
        print(f"===标准成本更新 core=== user_id={user_id} task_id={task_id} "
              f"plant_code={plant_code} {year}-{period} mat_code={mat_code} plant_val_class={plant_val_class}")
        code, msg = 200, "无可更新记录"
        # 回查只按 plant/year/period 刷新(回查SQL不兼容列表值, 故 mat_code 传空)
        body = {"data": {"year": year, "period": period, "plant_code": plant_code, "mat_code": ""}}

        # 查询待更新记录(posting_status != 'S')
        records = self._get_update_list(plant_code, year, period, mat_code, plant_val_class)
        print("待更新记录--", records)

        # 逐条推送: MATERIAL/VALUATIONAREA 为标量(单次只改一个物料), 故每条记录单独调一次 RFC,
        # 各自组装/发送/解析/回写, 单条失败不影响其余。
        total = len(records)
        if total:
            succ, fail_msgs = 0, []
            for record in records:
                mat = record.get("mat_code", "")
                try:
                    sap_send_data = self._prepare_price_change_request([record])   # 单条记录 -> 一次调用
                    print("----------------", sap_send_data)
                    sap_resp = self._send_price_change_request(sap_send_data)
                    resp = self._extract_price_change_response(sap_resp)
                    self._update_standard_price(record, resp, user_id)
                    if str(resp.get("p_ret")) == "2":
                        succ += 1
                    else:
                        fail_msgs.append(f"{mat}: {resp.get('p_msg') or 'SAP返回失败'}")
                except Exception as e:
                    traceback.print_exc()
                    # 该条异常单独置失败, 继续下一条
                    self._update_standard_price(record, {"ml_doc_num": "", "p_msg": str(e), "p_ret": "3"}, user_id)
                    fail_msgs.append(f"{mat}: {e}")

            fail = total - succ
            if fail == 0:
                code, msg = 200, f"更新成功 {succ} 条"
            else:
                detail = "; ".join(fail_msgs[:5]) + (" ..." if len(fail_msgs) > 5 else "")
                code, msg = 206, f"更新成功 {succ}/{total} 条; 失败: {detail}"

        # 回查最终状态(供前端刷新表格)
        data, display = self._query_data(body)
        return {"code": code, "msg": msg, "data": data, "display": display}

    # ==================== 查询 ====================
    def _query_data(self, body):
        """查 t_sap_mmd_standard_price 标准成本明细
        :return: (query_data, display)
        """
        data_filter = body.get("data") or {}
        payload = body.get("_payload_", {})
        filter_info = payload.get("filter_info", {})
        sort_info = payload.get("sort_info", {})

        # 前置筛选: 工厂/年度/期间/物料/过账状态/标准成本编码
        prefix_filter = {}
        for field in ("plant_code", "year", "period", "mat_code", "posting_status", "std_cost_code"):
            val = data_filter.get(field)
            if val not in (None, ""):
                prefix_filter[field] = val

        columns = '''`id`,
                    `company_code`,
                    `plant_code`,
                    `year`,
                    `period`,
                    `std_cost_code`,
                    `calc_mode`,
                    `effective_start_date`,
                    `effective_end_date`,
                    `posting_date`,
                    `mat_code`,
                    `standard_cost_bc`,
                    `basic_currency`,
                    `price_unit`,
                    `basic_uom`,
                    `posting_status`,
                    `price_doc_sn`,
                    `note`,
                    `update_id`,
                    `update_time`'''

        query_sql = f'''
                SELECT
                    {columns}
                FROM
                    `{self.TABLE_NAME}`
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
            {"field": "std_cost_code", "description": "标准成本编码"},
            {"field": "company_code", "description": "公司代码"},
            {"field": "plant_code", "description": "工厂代码"},
            {"field": "year", "description": "年度"},
            {"field": "period", "description": "期间"},
            {"field": "calc_mode", "description": "计算模式"},
            {"field": "effective_start_date", "description": "生效开始日期"},
            {"field": "effective_end_date", "description": "生效结束日期"},
            {"field": "posting_date", "description": "过账日期"},
            {"field": "mat_code", "description": "物料编码"},
            {"field": "standard_cost_bc", "description": "单位标准成本(本位币)"},
            {"field": "basic_currency", "description": "本位币"},
            {"field": "price_unit", "description": "价格单位"},
            {"field": "basic_uom", "description": "基本单位"},
            {"field": "posting_status", "description": "过账状态"},
            {"field": "price_doc_sn", "description": "价格更改凭证号"},
            {"field": "note", "description": "备注"},
            {"field": "update_time", "description": "更新时间"},
        ]

        return query_data, display

    # ==================== SAP 价格变更 查询待更新/组装/发送/解析/回写 ====================
    def _get_update_list(self, plant_code, year, period, mat_code=None, plant_val_class=None):
        """查询待更新的标准成本记录(posting_status != 'S')
        mat_code / plant_val_class 支持列表多选(空则不过滤); plant_val_class(评估类)在物料财务表,
        按 mat_code+plant_code 用子查询关联过滤。
        :return: list[dict]
        """
        cond = (
            f" AND `plant_code`='{plant_code}'"
            f" AND `year`='{year}'"
            f" AND `period`='{period}'"
            f" AND `posting_status` != 'S'"
        )
        # mat_code: 列表 -> IN; 单值经归一仍是 IN; 空 -> 不过滤
        mat_codes = self._normalize_list_param(mat_code)
        if mat_codes:
            cond += " AND `mat_code` IN ({})".format(",".join(f"'{m}'" for m in mat_codes))
        # plant_val_class(评估类): 列在 t_mmd_material_financial_data, 用子查询按 mat_code+plant_code 关联
        val_classes = self._normalize_list_param(plant_val_class)
        if val_classes:
            in_cls = ",".join(f"'{c}'" for c in val_classes)
            cond += (
                f" AND `mat_code` IN ("
                f"SELECT `mat_code` FROM `{self.FINANCIAL_TABLE}`"
                f" WHERE `plant_code`='{plant_code}' AND `plant_val_class` IN ({in_cls})"
                f")"
            )
        cond += " ORDER BY `id` ASC"
        cols = (
            "`id`,`std_cost_code`,`mat_code`,`plant_code`,"
            "`standard_cost_bc`,`basic_currency`,`price_unit`"
        )
        return query_db_records_by_cond(self.db, self.TABLE_NAME, cond, cols)

    def _prepare_price_change_request(self, records):
        """组装 ZBAPI_MATVAL_PRICE_CHANGE 请求数据(单物料, 多价格行)

        MATERIAL/VALUATIONAREA 为标量参数(单次一个物料), records 须为同一物料(同 mat_code+plant_code)。
        PRICES 为价格行 list, 每条记录展开两行(货币类型 10=公司代码货币 / 30=集团记账货币),
        每行字段为标量: VALUATION_VIEW / CURR_TYPE / PRICE / CURRENCY / PRICE_UNIT。
        秘火侧仅有本位币(basic_currency)与单位标准成本(standard_cost_bc),
        故两种货币类型暂传相同的价格/货币(若集团币不同需在此扩展)。

        :param records: 同一物料的价格记录列表
        :return: dict 顶层标量字段 + PRICES 表(list, 每记录两行 10/30)
        """
        if not records:
            return {}

        first = records[0]
        prices = []
        for record in records:
            price = round(self._parse_amount(record.get("standard_cost_bc")), 2)  # 单位标准成本, 保留2位小数推SAP
            currency = record.get("basic_currency", "") or ""
            price_unit = self._parse_amount(record.get("price_unit"))
            # price_unit = record.get("basic_uom") or "EA"
            print("------------------1111")
            for curr_type in self.CURR_TYPES:  # ("10", "30")
                prices.append({
                    "VALUATION_VIEW": self.VALUATION_VIEW,  # 评估视图(NUMC), 固定"0"
                    "CURR_TYPE": curr_type,                 # 10=公司代码货币, 30=集团记账货币
                    "PRICE": price,                         # 单位标准成本(本位币)
                    "CURRENCY": currency,                   # 货币码(本位币)
                    "PRICE_UNIT": price_unit,               # 价格单位
                })

        return {
            "MATERIAL": first.get("mat_code", ""),         # 物料编码(标量)
            "VALUATIONAREA": first.get("plant_code", ""),  # 估价范围=工厂代码(标量)
            "P_RELEASE": self.P_RELEASE,                   # 需要解冻物料时传X
            "PRICES": prices,                              # 价格明细表(每记录两行 10/30)
        }

    def _send_price_change_request(self, sap_send_data):
        """发送 ZBAPI_MATVAL_PRICE_CHANGE 请求"""
        sap_resp = SAPRFC().call(self.INTERFACE_CODE, sap_send_data)
        print(f"===标准成本更新请求返回结果===: {sap_resp}")
        return sap_resp

    def _extract_price_change_response(self, sap_resp):
        """解析SAP返回数据
        响应字段位置:
          P_RET(2成功/3失败) / P_MSG(详情)        -> 顶层单参数
          ML_DOC_NUM(价格更改凭证号) / ML_DOC_YEAR -> 输出结构行 PRICECHANGEDOCUMENT
        :return: dict {p_ret, p_msg, ml_doc_num, ml_doc_year}
        """
        sap_resp = sap_resp or {}
        data = sap_resp.get("DATA") or {}
        price_doc = sap_resp.get("PRICECHANGEDOCUMENT") or {}   # 输出结构行

        def pick(*keys, default=""):
            for k in keys:
                for src in (sap_resp, price_doc, data):
                    val = src.get(k)
                    if val not in (None, ""):
                        return val
            return default

        return {
            "p_ret": str(pick("P_RET", default="3")),   # 2:成功 3:失败
            "p_msg": pick("P_MSG"),                     # 更新详情
            "ml_doc_num": pick("ML_DOC_NUM"),           # 价格更改凭证号
            "ml_doc_year": pick("ML_DOC_YEAR"),         # 库存年度
        }

    def _update_standard_price(self, record, resp, user_id=None):
        """回写 t_sap_mmd_standard_price: 价格更改凭证号/备注/过账状态/操作人
        posting_status: P_RET '2'->'S'(成功), 其余->'E'(失败), 与表既有约定一致;
        update_id: 操作人(来自 user_id), 为空则不更新该列。
        注: ML_DOC_YEAR 仅记录不入库, 避免覆盖作为查询键的期间年度(year)
        """
        record_id = record.get("id")
        if not record_id:
            return
        cond = f" AND `id`={record_id}"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data = {
            "posting_status": self._map_posting_status(resp.get("p_ret", "3")),
            "price_doc_sn": resp.get("ml_doc_num", ""),
            "note": (resp.get("p_msg", "") or "")[:65535],
            "update_id": user_id if user_id not in (None, "") else None,
            "update_time": now,
        }
        cols = ("posting_status", "price_doc_sn", "note", "update_id", "update_time")
        update_db_record_by_cond(self.db, self.TABLE_NAME, cond, cols, data)




    @staticmethod
    def _map_posting_status(p_ret):
        """P_RET -> posting_status: '2'->'S'(成功), 其余->'E'(失败)"""
        return "S" if str(p_ret) == "2" else "E"

    # ==================== 工具 ====================
    @staticmethod
    def _parse_amount(value):
        """金额/单位转float, 空值当0"""
        try:
            return float(value) if value not in (None, "") else 0.0
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _normalize_list_param(value):
        """把请求参数归一成 list   兼容前端多选
        """
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            return [str(v).strip() for v in value if str(v).strip() != ""]
        s = str(value).strip()
        return [s] if s else []


@calc_time
def standard_cost_update(body):
    """标准成本更新接口 按钮(框架 HTTP 入口)
    其他文件可直接 StandardCostUpdate().push(body, user_id) 拿 {code,msg,data,..}。
    """
    req = Request()
    res = Response()
    body = json.loads(req.body())
    print("body---", body)
    user_id = req.header("user_id")
    result = StandardCostUpdate().push(body, user_id)
    res.set_body(json.dumps(result))
    res.commit(True)


@calc_time
def standard_cost_update_query(body):
    """标准成本更新查询接口(框架 HTTP 入口)"""
    req = Request()
    res = Response()
    body = json.loads(req.body())
    print("body----", body)
    result = StandardCostUpdate().query(body)
    res.set_body(json.dumps(result))
    res.commit(True)


body = {'year': '2026', 'period': '07', 'plant_code': 'RAC1', 'mat_code': [], 'plant_val_class': [], 'user_id': '1008'}


@calc_time
def Text_standard_cost_update():
    """标准成本更新接口 测试(直接走 class 入口, body 为模块级扁平字典)"""
    print("===标准成本更新接口 测试===")
    res_bus = StandardCostUpdate().push(body, body.get("user_id"))
    print(f"===标准成本更新接口 测试=== 处理结束!!! 返回: {res_bus}")
    return res_bus


if __name__ == "__main__":
    Text_standard_cost_update()
