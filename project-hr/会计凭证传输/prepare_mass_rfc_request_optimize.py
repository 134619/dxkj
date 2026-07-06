# -*- coding: utf-8 -*-
"""
================================================================================
prepare_mass_rfc_request 优化方案与代码存档
================================================================================
对应原始文件: ZZ_voucher_push.py -> prepare_mass_rfc_request()
作用: 把多张待推凭证合并成一次 MASS 调用的 DATA_IN

本文件不是可独立运行脚本, 而是【优化方案 + 可直接替换的代码片段】存档,
方便后期读取、对照、移植回 ZZ_voucher_push.py。

--------------------------------------------------------------------------------
【诊断】真正慢的不是 Python for 循环, 而是循环里的数据库查询(N+1 问题)

原始循环结构:
    for doc in docs:                                  # N(凭证数, 可能上千)
        head_data   = get_fi_doc_for_archiv_head(...)       # ⚠ 每次 DB 往返
        detail_list = find_fi_doc_for_archiv_details(...)   # ⚠ 每次 DB 往返
        for cfg in value_transfer:                    # V(转换规则数)
            for j in detail_list:                     # D(单凭证明细数)
                ...

关键点:
  - get_fi_post_erp_value_transfer() / get_company_cost_element_info()
    都有缓存(lru_cache / 模块级 dict), 循环外只查一次 ✅
  - get_fi_doc_for_archiv_head / find_fi_doc_for_archiv_details
    【无缓存且在循环内逐张凭证调用】 → N 张凭证 = 2N 次网络往返 = 真正的瓶颈
  - 值转换 O(N·V·D), V/D 都小, Python 开销可忽略, 但顺手也能优化

--------------------------------------------------------------------------------
【优化策略】两档
  档1(决定性): 批量查询消除 N+1 —— 2N 次往返 → 2 次
  档2(锦上添花): 值转换循环预处理成映射字典, 每条记录只遍历一次

--------------------------------------------------------------------------------
【复杂度对比】
  +----------+-----------------------+----------------------------+
  |          | 优化前                | 优化后                     |
  +----------+-----------------------+----------------------------+
  | DB 往返  | 2N 次                 | 2 次(固定)                 |
  | 值转换   | O(N·V·D), detail扫V次 | O(N·V·D), 每detail扫1次    |
  | 实际耗时 | N=1000 时 DB 主导,几十秒 | 内存遍历, 几百毫秒级      |
  +----------+-----------------------+----------------------------+

一句话: 多层 for 里只要藏着数据库调用, 优化永远先打 DB(批量化), 再谈 Python 重写。

--------------------------------------------------------------------------------
【移植到 ZZ_voucher_push.py 时需要的依赖】(本文件未 import, 使用时确保作用域可见)
  常量/全局:
    ARCHIV_HEAD_TABLE, ARCHIV_DETAIL_TABLE  —— 表名常量
    FLAG_POST, accounting_document_type      —— RFC 标记常量
    db                                       —— 数据库句柄(含 .query_sql)
  函数:
    build_rfc_head(head_data)                —— 组装抬头字段
    build_rfc_items(detail_list, cost_elem)  —— 组装明细字段
================================================================================
"""


# =====================================================================
# 档1: 批量查询 —— 消除 N+1
# =====================================================================
def get_fi_doc_head_batch(suns, company_code, year, archiv_map=None):
    """批量查抬头, 返回 {sun: head(最新一条)}

    :param suns:        summary_unique_number 列表
    :param company_code:公司代码
    :param year:        年度
    :param archiv_map:  {sun: archiv_doc_num}, 同 sun 多归档凭证时二次过滤(可选)
    取代: ZZ_voucher_push.get_fi_doc_for_archiv_head() 在循环内的逐个调用
    """
    if not suns:
        return {}
    sun_list = ",".join(f"'{s}'" for s in suns)
    sql = f"""SELECT `id`,`company_code`,`fi_sum_doc_type`,`archiv_doc_num`,
                     `document_date`,`posting_date`,`year`,`period`,
                     `summary_unique_number`,`transaction_currency`,`basic_currency`,
                     `exchange_rate`,`header_text`,`sum_dr_amount_bc`,`sum_cr_amount_bc`,
                     `posting_status`,`verify_status`
              FROM `{ARCHIV_HEAD_TABLE}`
              WHERE `company_code`='{company_code}' AND `year`='{year}'
                AND `summary_unique_number` IN ({sun_list})
              ORDER BY `id` DESC"""
    rows = db.query_sql(sql) or []
    head_by_sun = {}
    for r in rows:                          # 已按 id DESC, setdefault 保留最新一条
        head_by_sun.setdefault(r.get("summary_unique_number"), r)
    return head_by_sun


def find_fi_doc_detail_batch(suns, company_code, year):
    """批量查明细, 返回 {sun: [detail, ...]}

    取代: ZZ_voucher_push.find_fi_doc_for_archiv_details() 在循环内的逐个调用
    注意: 索引 key 用 t1(明细表)的 summary_unique_number, 与原函数一致
    """
    if not suns:
        return {}
    sun_list = ",".join(f"'{s}'" for s in suns)
    sql = f"""SELECT t1.`id`,t1.`year`,t1.`company_code`,t1.`summary_unique_number`,
                     t1.`dc_amount_tc`,t1.`dc_amount_bc`,t1.`debit_credit_mark`,
                     t1.`mat_doc_sn`,t1.`mat_doc_items`,t1.`cost_center`,t1.`prodosn`,
                     t1.`cost_business_object1`,t1.`wbs_elements`,t1.`summary_line`,
                     t1.`accounting_subjects`,t1.`customer_code`,t1.`vendor_code`,
                     t1.`asset_code1`,t1.`asset_code2`,t1.`asset_business_type`,
                     t1.`profit_center`,t1.`item_text`,t1.`mat_code`,t1.`trade_partner_code`,
                     t1.`payment_terms`,t1.`baseline_date`,t1.`basic_uom`,t1.`basic_qty`,
                     t1.`so_sn`,t1.`so_items`,t1.`transaction_currency_amount`,
                     t2.`fi_sum_doc_type`,t2.`posting_date`,t2.`exchange_rate`
              FROM `{ARCHIV_DETAIL_TABLE}` AS t1
              LEFT JOIN `{ARCHIV_HEAD_TABLE}` AS t2
                ON t1.`year`=t2.`year` AND t1.`company_code`=t2.`company_code`
               AND t1.`summary_unique_number`=t2.`summary_unique_number`
              WHERE t1.`company_code`='{company_code}' AND t1.`year`='{year}'
                AND t1.`summary_unique_number` IN ({sun_list})
              ORDER BY t1.`id` ASC"""
    rows = db.query_sql(sql) or []
    detail_by_sun = {}
    for r in rows:
        detail_by_sun.setdefault(r.get("summary_unique_number"), []).append(r)
    return detail_by_sun


# =====================================================================
# 档2: 值转换循环预处理 —— 映射字典 + O(1) 查表
# =====================================================================
def build_value_transfer_rules(value_transfer):
    """把 t_fi_post_erp_value_transfer 配置预处理成 {field_name: {before_value: after_value}}

    原写法 for cfg: for detail 导致 detail_list 被完整扫描 V 次;
    改预处理后, 每条记录只遍历一次字段, before 用 dict key 做 O(1) 命中。
    """
    rules_by_field = {}
    for cfg in value_transfer:
        rules_by_field.setdefault(cfg.get("field_name"), {})[cfg.get("before_value")] = cfg.get("after_value")
    return rules_by_field


def apply_value_transfer(record, rules_by_field):
    """就地替换: record 里命中的 (字段, 原值) 按规则改成新值"""
    for fname, mapping in rules_by_field.items():
        cur = record.get(fname)
        if cur in mapping:                  # dict O(1), 比逐个 == 快
            record[fname] = mapping[cur]


# =====================================================================
# 改造后的主函数(可直接替换原 prepare_mass_rfc_request)
# =====================================================================
def prepare_mass_rfc_request_optimized(docs, company_code):
    """把多张待推凭证合并成一次 MASS 调用的 DATA_IN(优化版)

    与原函数签名/返回值完全一致, 可直接替换:
      return: (rfc_data, pushed_list, pass_list, row_sun_map)
        rfc_data     = {"BUKRS", "FLAG", "DATA_IN": [行...]}
        pushed_list  = [{"sun", "company_code", "year", "archiv_doc_num"}]
        pass_list    = [{"sun", "company_code", "year"}]
        row_sun_map  = [sun, ...]
    """
    data_in, pushed_list, pass_list, row_sun_map = [], [], [], []

    cost_element_dict = get_company_cost_element_info(company_code)
    value_transfer    = get_fi_post_erp_value_transfer()
    rules_by_field    = build_value_transfer_rules(value_transfer)   # 档2: 一次性预处理

    # 档1: 批量查询, 消除 N+1(2N 次往返 → 2 次)
    suns        = [d.get("summary_unique_number") for d in docs]
    year        = (docs[0].get("year") if docs else "")
    archiv_map  = {d.get("summary_unique_number"): d.get("archiv_doc_num") for d in docs}
    head_by_sun   = get_fi_doc_head_batch(suns, company_code, year, archiv_map)
    detail_by_sun = find_fi_doc_detail_batch(suns, company_code, year)

    # 纯内存遍历, 循环内不再有任何 DB 调用
    for doc in docs:
        sun           = doc.get("summary_unique_number")
        year          = doc.get("year")
        archiv_doc_num = doc.get("archiv_doc_num")

        head_data = head_by_sun.get(sun)
        if not head_data:
            print(f"汇总凭证记录不存在, 跳过: sun={sun}")
            continue
        detail_list = detail_by_sun.get(sun, [])

        # 值转换(档2)
        apply_value_transfer(head_data, rules_by_field)
        for j in detail_list:
            apply_value_transfer(j, rules_by_field)

        # 无明细(金额为0): 直接落成功
        if not detail_list:
            pass_list.append({"sun": sun, "company_code": company_code, "year": year})
            continue

        # 抬头 + 行项目; EMSDOC 区分不同凭证, 不带 IP_INDEX
        head_fields = build_rfc_head(head_data)
        for item in build_rfc_items(detail_list, cost_element_dict):
            data_in.append({**head_fields, **item})
            row_sun_map.append(str(sun))
        pushed_list.append({"sun": sun, "company_code": company_code,
                            "year": year, "archiv_doc_num": archiv_doc_num})

    rfc_data = {"BUKRS": company_code, "FLAG": FLAG_POST, "DATA_IN": data_in}
    print(f"组装MASS请求数据完成--- BUKRS={company_code} FLAG={FLAG_POST} DATA_IN行数={len(data_in)}")
    return rfc_data, pushed_list, pass_list, row_sun_map


# =====================================================================
# 【使用说明】
# =====================================================================
# 1) 移植回 ZZ_voucher_push.py 时:
#    - 新增 get_fi_doc_head_batch / find_fi_doc_detail_batch
#    - 新增 build_value_transfer_rules / apply_value_transfer
#    - 用 prepare_mass_rfc_request_optimized 替换(或改名替换)原函数
#    - 原 get_fi_doc_for_archiv_head / find_fi_doc_for_archiv_details 可保留(单条场景仍用得上)
#
# 2) 注意事项:
#    - 批量查询用 IN, 若同一 sun 能匹配多张归档凭证, 应改用 (sun, archiv_doc_num)
#      复合 key, 或在循环里按 archiv_doc_num 二次过滤(archiv_map 已备好)。
#    - SQL 沿用现有 f-string 拼接风格; sun 来自库内查询结果, 风险可控。
#      如需更安全可改参数化查询。
#    - build_rfc_head / build_rfc_items / _to_ymd / 表名常量 均沿用原模块, 无需改动。
