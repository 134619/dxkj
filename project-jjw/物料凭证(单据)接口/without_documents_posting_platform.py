#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@File    : without_documents_posting_platform.py
@Author  : chengye.lu@dxdstech.com
@Date    : 2026/4/15 20:42
@explain :
"""
import copy
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from DbHelper import DbHelper
from DxInventoryReverseData import reverse_data
from DxWithoutDocInventoryPost import post_data
from logger import LoggerConfig
from ToolsMethods import ResetResponse, ResponseData, ResponseStatusCode, calc_time

logger = LoggerConfig("without_documents_posting_platform", isStream=True)


class CompareOperator(Enum):
    """比较运算符"""
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    LT = "lt"
    GE = "ge"
    LE = "le"
    BETWEEN = "between"
    IN = "in"


class LengthOperator(Enum):
    """长度比较运算符"""
    EQ = "eq"  # 长度等于
    NE = "ne"  # 长度不等于
    GT = "gt"  # 长度大于
    LT = "lt"  # 长度小于
    GE = "ge"  # 长度大于等于
    LE = "le"  # 长度小于等于
    BETWEEN = "between"  # 长度在区间内
    IN = "in"  # 长度在列表中


@dataclass
class DynamicThreshold:
    """动态阈值配置"""
    depends_on: str  # 依赖的字段名
    mapping: Union[Dict[Any, Dict], Callable[[Any], Dict]]
    default_threshold: Optional[Dict] = None


@dataclass
class LengthValidation:
    """长度校验配置"""
    enabled: bool = False
    operator: Optional[LengthOperator] = None
    value: Optional[int] = None  # 用于 EQ, NE, GT, LT, GE, LE
    min_length: Optional[int] = None  # 用于 BETWEEN
    max_length: Optional[int] = None  # 用于 BETWEEN
    allowed_lengths: Optional[List[int]] = None  # 用于 IN
    error_msg: Optional[str] = None  # 自定义错误消息

    # 动态长度校验（根据其他字段的值）
    dynamic_length: Optional[DynamicThreshold] = None

    # 是否校验空字符串（默认不校验空字符串）
    skip_empty: bool = True


@dataclass
class ValidationRule:
    """校验规则"""
    field: str
    required: bool = False
    required_func: Optional[Callable[[Any, tuple], tuple[bool,str]]] = None
    required_func_depend: Optional[Any] = None
    field_type: Optional[type] = None

    default_value_func: Optional[Callable[[Any, Any], Any]] = None
    depend_str: Optional[Any] = None

    # 长度校验
    length: Optional[LengthValidation] = None

    # 静态阈值校验
    threshold_enabled: bool = False
    operator: Optional[CompareOperator] = None
    value: Optional[Any] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    allowed_values: Optional[List] = None
    threshold_enabled_msg: Optional[str] = None

    # 动态阈值校验
    dynamic_threshold: Optional[DynamicThreshold] = None

    # 跨字段依赖校验
    cross_field_validator: Optional[Callable[[Dict], Tuple[bool, str]]] = None

    # 正则表达式校验
    pattern: Optional[str] = None
    pattern_error_msg: Optional[str] = None

    # 自定义校验
    custom_validator: Optional[Callable[[Any, tuple], Tuple[bool, str]]] = None
    custom_validator_depend_on: Optional[list] = None
    custom_error_msg: Optional[str] = None


@dataclass
class ValidationResult:
    """校验结果"""
    index: int
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    type_errors: List[str] = field(default_factory=list)
    data: Optional[Dict] = None


class DynamicListValidator:
    def __init__(self, rules: List[ValidationRule], stop_on_first_error: bool = False):
        self.rules = {rule.field: rule for rule in rules}
        self.stop_on_first_error = stop_on_first_error
        self.results: List[ValidationResult] = []

    def validate(self, data_list: Union[List[Dict], str]) -> Tuple[bool, List[ValidationResult], int, int]:
        """校验列表中的所有元素"""
        pass_count = 0
        all_count = len(data_list)
        if isinstance(data_list, str):
            try:
                data_list = json.loads(data_list)
            except json.JSONDecodeError as e:
                result = ValidationResult(index=-1, is_valid=False, type_errors=[f"JSON解析失败: {str(e)}"])

                return False, [result], all_count, pass_count

        if not isinstance(data_list, list):
            result = ValidationResult(index=-1, is_valid=False, type_errors=["数据必须是列表类型"])
            return False, [result], all_count, pass_count
        self.results = []
        all_valid = True





        for idx, item in enumerate(data_list):
            if not isinstance(item, dict):
                result = ValidationResult(
                    index=idx,
                    is_valid=False,
                    type_errors=[f"索引 {idx} 的元素必须是字典类型"]
                )
                self.results.append(result)
                all_valid = False
                if self.stop_on_first_error:
                    return False, self.results, all_count, pass_count
                continue
            result = self._validate_item(idx, item)
            self.results.append(result)

            if not result.is_valid:
                all_valid = False

                if self.stop_on_first_error:
                    return False, self.results, all_count, pass_count
            else:
                pass_count += 1

        return all_valid, self.results, all_count, pass_count

    def _validate_item(self, index: int, data: Dict) -> ValidationResult:
        """校验单个元素"""
        result = ValidationResult(index=index, is_valid=True, data=data)

        # 高优先级校验
        if self.rules.get('Outer_verif_rule'):
            if self.rules.get('Outer_verif_rule').cross_field_validator:
                is_valid, error_msg = self.rules.get('Outer_verif_rule').cross_field_validator(data)
                if not is_valid:
                    result.is_valid = False
                    result.errors.append('高优先级校验失败:{}'.format(error_msg))

        # 校验每个字段
        for field, rule in self.rules.items():
            value = data.get(field)
            if rule.default_value_func and rule.depend_str:
                data[field] = rule.default_value_func(data.get(rule.depend_str, ''), value)
                value = data[field]
            errors = self._validate_field(field, rule, value, data)
            if errors:
                result.errors.extend([f"字段 '{field}': {err}" for err in errors])
                result.is_valid = False
        # 跨字段校验
        for field, rule in self.rules.items():
            if rule.cross_field_validator and field != 'Outer_verif_rule':
                is_valid, error_msg = rule.cross_field_validator(data)
                if not is_valid:
                    result.is_valid = False
                    result.errors.append(f"跨字段校验 '{field}': {error_msg}")
        if not result.is_valid:
            data['document_status'] = 3
            data['message_text'] = ','.join(result.errors)
        else:
            data['document_status'] = 2
            data['message_text'] = '校验成功'
        return result

    def _validate_field(self, field: str, rule: ValidationRule, value: Any, full_data: Dict) -> List[str]:
        """单字段校验"""
        errors = []
        required_error = None
        #可变必填校验处理
        if rule.required_func:

            rule.required, required_error = rule.required_func(value,*tuple(
                [full_data[i] for i in rule.required_func_depend] if rule.required_func_depend else []))
        # 必填校验
        if rule.required and not value:
            errors.append(required_error or f"{field}是必填字段")
            return errors

        if not value :
            return errors
        # 类型校验
        if rule.field_type and not isinstance(value, rule.field_type if rule.field_type != float else (int, float)):
            print('value:', value)
            print('rule.field_type:', rule.field_type)
            errors.append(f"类型错误，期望: {rule.field_type.__name__}，实际: {type(value).__name__}")
            return errors
        # 长度校验
        if rule.length and rule.length.enabled:
            length_errors = self._validate_length(field, value, rule.length, full_data)
            errors.extend(length_errors)
            # 如果长度校验失败，可以选择继续或停止
            if length_errors and self.stop_on_first_error:
                return errors
        # 正则校验
        if rule.pattern:
            if not re.match(rule.pattern, str(value)):
                msg = rule.pattern_error_msg or f"格式不符合要求（正则: {rule.pattern}）"
                errors.append(msg)
            if errors and self.stop_on_first_error:
                return errors
        # 自定义校验
        if rule.custom_validator:
            try:
                check_res = rule.custom_validator(value, *tuple(
                    [full_data[i] for i in rule.custom_validator_depend_on] if rule.custom_validator_depend_on else []))
                if not check_res[0]:
                    msg = rule.custom_error_msg or check_res[1]
                    errors.append(msg)
            except Exception as e:
                errors.append(f"自定义校验执行错误: {str(e)}")
            if errors and self.stop_on_first_error:
                return errors
        # 优先使用动态阈值
        if rule.dynamic_threshold:
            threshold_config = self._get_dynamic_threshold(rule.dynamic_threshold, full_data)
            if threshold_config:
                threshold_errors = self._validate_threshold(field, value, threshold_config)
                errors.extend(threshold_errors)
                return errors
        # 静态阈值校验
        if rule.threshold_enabled and rule.operator:
            threshold_errors = self._validate_static_threshold(field, value, rule)
            errors.extend(threshold_errors)
        return errors

    def _validate_length(self, field: str, value: Any, length_config: LengthValidation, full_data: Dict) -> List[str]:
        """校验长度"""
        errors = []

        # 获取值的长度
        length = self._get_length(value)
        if length is None:
            errors.append(f"无法获取长度，类型: {type(value).__name__}")
            return errors

        # 跳过空值校验
        if length_config.skip_empty and length == 0:
            return errors

        # 优先使用动态长度配置
        if length_config.dynamic_length:
            dynamic_config = self._get_dynamic_threshold(length_config.dynamic_length, full_data)
            if dynamic_config:
                return self._validate_length_by_config(field, length, dynamic_config, length_config.error_msg)

        # 使用静态长度配置
        return self._validate_length_by_config(field, length, {
            'operator': length_config.operator,
            'value': length_config.value,
            'min_length': length_config.min_length,
            'max_length': length_config.max_length,
            'allowed_lengths': length_config.allowed_lengths
        }, length_config.error_msg)

    def _get_length(self, value: Any) -> Optional[int]:
        """获取值的长度"""
        if isinstance(value, str):
            return len(value)
        elif isinstance(value, (list, tuple, set)):
            return len(value)
        elif isinstance(value, dict):
            return len(value)
        elif hasattr(value, '__len__'):
            return len(value)
        else:
            return None

    def _validate_length_by_config(self, field: str, length: int, config: Dict, custom_msg: Optional[str]) -> List[str]:
        """根据配置校验长度"""
        errors = []
        operator = config.get('operator')

        if operator == LengthOperator.EQ:
            expected = config.get('value')
            if length != expected:
                msg = custom_msg or f"长度应该等于 {expected}，实际: {length}"
                errors.append(msg)

        elif operator == LengthOperator.NE:
            expected = config.get('value')
            if length == expected:
                msg = custom_msg or f"长度不应该等于 {expected}"
                errors.append(msg)

        elif operator == LengthOperator.GT:
            expected = config.get('value')
            if not (length > expected):
                msg = custom_msg or f"长度应该大于 {expected}，实际: {length}"
                errors.append(msg)

        elif operator == LengthOperator.LT:
            expected = config.get('value')
            if not (length < expected):
                msg = custom_msg or f"长度应该小于 {expected}，实际: {length}"
                errors.append(msg)

        elif operator == LengthOperator.GE:
            expected = config.get('value')
            if not (length >= expected):
                msg = custom_msg or f"长度应该大于等于 {expected}，实际: {length}"
                errors.append(msg)

        elif operator == LengthOperator.LE:
            expected = config.get('value')
            if not (length <= expected):
                msg = custom_msg or f"长度应该小于等于 {expected}，实际: {length}"
                errors.append(msg)

        elif operator == LengthOperator.BETWEEN:
            min_len = config.get('min_length')
            max_len = config.get('max_length')
            if not (min_len <= length <= max_len):
                msg = custom_msg or f"长度应该在 [{min_len}, {max_len}] 区间内，实际: {length}"
                errors.append(msg)

        elif operator == LengthOperator.IN:
            allowed = config.get('allowed_lengths', [])
            if length not in allowed:
                msg = custom_msg or f"长度应该是 {allowed} 中的值，实际: {length}"
                errors.append(msg)

        return errors

    def _get_dynamic_threshold(self, dynamic: DynamicThreshold, data: Dict) -> Optional[Dict]:
        """根据依赖字段获取动态阈值配置"""
        if dynamic.depends_on not in data:
            return dynamic.default_threshold

        depend_value = data[dynamic.depends_on]

        if callable(dynamic.mapping):
            try:
                return dynamic.mapping(depend_value)
            except Exception:
                return dynamic.default_threshold

        if isinstance(dynamic.mapping, dict):
            return dynamic.mapping.get(depend_value, dynamic.default_threshold)

        return dynamic.default_threshold

    def _validate_static_threshold(self, field: str, value: Any, rule: ValidationRule) -> List[str]:
        """校验静态阈值"""
        errors = []

        if rule.operator != CompareOperator.IN:
            if not isinstance(value, (int, float)):
                errors.append(f"阈值校验要求数值类型")
                return errors

        config = {
            'operator': rule.operator,
            'value': rule.value,
            'min_value': rule.min_value,
            'max_value': rule.max_value,
            'allowed_values': rule.allowed_values,
            'error_msg': rule.threshold_enabled_msg
        }

        return self._validate_threshold(field, value, config)

    def _validate_threshold(self, field: str, value: Any, config: Dict) -> List[str]:
        """执行阈值校验"""
        errors = []
        operator = config.get('operator')

        if operator == CompareOperator.EQ:
            if value != config.get('value'):
                errors.append(f"应该等于 {config.get('value')}，实际: {value}")

        elif operator == CompareOperator.NE:
            if value == config.get('value'):
                errors.append(f"不应该等于 {config.get('value')}")

        elif operator == CompareOperator.GT:
            if not (value > config.get('value')):
                errors.append(f"应该大于 {config.get('value')}，实际: {value}")

        elif operator == CompareOperator.LT:
            if not (value < config.get('value')):
                errors.append(f"应该小于 {config.get('value')}，实际: {value}")

        elif operator == CompareOperator.GE:
            if not (value >= config.get('value')):
                errors.append(f"应该大于等于 {config.get('value')}，实际: {value}")

        elif operator == CompareOperator.LE:
            if not (value <= config.get('value')):
                errors.append(f"应该小于等于 {config.get('value')}，实际: {value}")

        elif operator == CompareOperator.BETWEEN:
            min_val = config.get('min_value')
            max_val = config.get('max_value')
            if not (min_val <= value <= max_val):
                errors.append(f"应该在 [{min_val}, {max_val}] 区间内，实际: {value}")

        elif operator == CompareOperator.IN:
            allowed = config.get('allowed_values', [])
            error_msg = config.get('error_msg')
            if value not in allowed:
                errors.append(error_msg or f"应该是 {allowed} 中的值，实际: {value}")

        return errors

    def get_valid_items(self) -> List[Dict]:
        return [r.data for r in self.results if r.is_valid and r.data is not None]

    def get_invalid_items(self) -> List[Tuple[int, Dict, List[str]]]:
        return [(r.index, r.data, r.errors) for r in self.results if not r.is_valid]

    def get_summary(self) -> Dict:
        total = len(self.results)
        valid_count = sum(1 for r in self.results if r.is_valid)
        return {
            "total": total,
            "valid": valid_count,
            "invalid": total - valid_count,
            "pass_rate": f"{(valid_count / total * 100):.2f}%" if total > 0 else "N/A"
        }


class Cache_Class:

    def __init__(self, db=None):
        if db:
            self.db = db
        else:
            self.db = DbHelper()

        self.integration_rule = None

        # 若物料主数据检验类型激活（任一），且借贷标识为Cr,且库存状态=1，则判断质检过账标识是否为1
        self.COMPANY = None
        self.MOVEMENT_TYPE = None
        self.PLANT_CODE = None
        self.COMPANY_CODE = None
        self.PLANT_STORAGE = None
        self.SPE_INV_STATUS = None
        self.INV_STATUS = None
        self.MAT_CODE = None
        self.INV_BATCH = None
        self.MMD_UOM = None
        self.PUR_ITEM_CAT = None
        self.ACC_ALLOC_CAT = None
        # t_mmd_material_quality_Inspection_data
        self.MAT_QUALITY_FLAG = None
        self.DOC_STATUS_PASS = None
        #no_supply_chain_document_flag
        self.NO_SUPPLY_FLAG_COMP = None
        self.EXTERNAL_MD_PRICE = None
        self.MAT_GROUP = None


    def get_mat_group(self):
        if self.MAT_GROUP is None:
            tmp_data = self.db.query_sql(
                " select `mat_group` from `t_mmd_material_group` ")
            self.MAT_GROUP = [i['mat_group'] for i in tmp_data]
        return self.MAT_GROUP or []



    def get_md_price_data(self):
        if self.EXTERNAL_MD_PRICE is None:
            tmp_data = self.db.query_sql(
                " select `external_sys_unique_doc_sn`,`external_sys_unique_doc_items` from `t_external_sys_md_price_data` ")
            self.EXTERNAL_MD_PRICE = [(i['external_sys_unique_doc_sn'],i['external_sys_unique_doc_items']) for i in tmp_data]
        return self.EXTERNAL_MD_PRICE or []

    def check_md_price_data(self,data):
        tmp_data = self.get_md_price_data()
        movement_data = self.get_movement_type()
        external_sys_unique_doc_sn = data.get('external_sys_unique_doc_sn','无外部系统单号')
        external_sys_unique_doc_items = data.get('external_sys_unique_doc_items','无外部系统单行号')
        rel_po_sn = data.get('rel_po_sn')
        free_mark = data.get('free_mark',0)
        movement_type = data.get('movement_type','')
        receipt_consume_mark = None
        if movement_type:
            receipt_consume_mark = movement_data.get(movement_type, [None, None, None,None])[2]

        pass_flag = False
        error_msg = '错误：关联采购订单号存在,且非免费,收发标识为R,物料凭证价格数据必传'
        if rel_po_sn and free_mark == 0 and receipt_consume_mark == 'R':
            if (external_sys_unique_doc_sn,external_sys_unique_doc_items) in tmp_data:
                pass_flag = True
        else:
            pass_flag = True

        return pass_flag, error_msg


    def get_no_supply_chain_document_flag(self):
        if self.NO_SUPPLY_FLAG_COMP is None:
            movement_type_data = self.db.query_sql(
                " select `company_code` from `t_fi_integration_rule` WHERE `no_supply_chain_document_flag` = 1 ")

            self.NO_SUPPLY_FLAG_COMP = [i['company_code'] for i in movement_type_data]
        return self.NO_SUPPLY_FLAG_COMP or []


    def get_movement_type(self):
        if not self.MOVEMENT_TYPE:
            movement_type_data = self.db.query_sql(
                " select `movement_type`,`inventory_status`,`debit_credit_mark`,`receipt_consume_mark`,`post_code` from `t_movement_type`")
            temp_dic = defaultdict(list)
            for item in movement_type_data:
                temp_dic[item['movement_type']] = [item['inventory_status'], item['debit_credit_mark'], item['receipt_consume_mark'],
                                                   item['post_code']]
            self.MOVEMENT_TYPE = dict(temp_dic)
        return self.MOVEMENT_TYPE or {}

    def get_mat_quality_info(self):
        if not self.MAT_QUALITY_FLAG:
            mat_quality_info = self.db.query_sql(
                " select `mat_code`,`plant_code` from `t_mmd_material_quality_Inspection_data` where `activation_flag` = 1")
            temp_dic = defaultdict(list)
            for item in mat_quality_info:
                temp_dic[item['plant_code']].append(item['mat_code'])
            self.MAT_QUALITY_FLAG = dict(temp_dic)
        return self.MAT_QUALITY_FLAG or {}

    def check_mat_quality(self, value, *args):

        print(args)
        tmp_data = self.get_mat_quality_info()
        # 若物料主数据检验类型激活（任一）t_mmd_material_quality_Inspection_data物料号有数据
        # 且激活标记 = 1，且借贷标识为Cr, 且库存状态 = 1，则判断质检过账标识是否为1，如果不是则报错
        # （借贷标识和库存状态根据移动类型取t_movement_type）
        get_movement = self.get_movement_type()
        plant_code = args[0]
        mat_code = args[1]
        movement_code = args[2]
        movement_info = get_movement.get(movement_code, [None, None, None])
        pass_flag = False
        error_msg = '物料激活标记为1 借贷标识为C 库存状态 为 1 质检过账标识字段必须为1'
        if mat_code and mat_code in tmp_data.get(plant_code, []) and movement_info[1] == 'Cr' and movement_info[-1] == '1':
            if value == 1:
                pass_flag = True
        else:
            pass_flag = True

        return pass_flag, error_msg

    def get_inventory_status_daf(self, value, daf):
        tmp_data = self.get_movement_type()
        return tmp_data.get(value, [None, None, None])[0] or daf

    def get_basic_currency_daf(self, value, daf):
        tmp_data = self.get_company_code()
        return daf or tmp_data.get(value, '')

    # 若未传值，则默认根据公司代码取本位币os_company-basic_currency
    def get_plant_code(self):
        if not self.PLANT_CODE:
            tmp_data = self.db.query_sql(
                " select `plant_code` from `t_os_plant` group by `plant_code`")
            self.PLANT_CODE = [i['plant_code'] for i in tmp_data]
        return self.PLANT_CODE or []

    def check_plant_code(self, value, *args):
        tmp_data = self.get_plant_code()
        pass_flag = False
        if value in tmp_data:
            pass_flag = True
        return pass_flag

    def get_company_code(self):
        if not self.COMPANY_CODE:
            query_data = self.db.query_sql(
                " select `company_code`,`basic_currency` from `t_os_company`")

            temp_dic = defaultdict()
            for item in query_data:
                temp_dic[item['company_code']] = item['basic_currency']
            self.COMPANY_CODE = dict(temp_dic)
        return self.COMPANY_CODE or {}

    def check_company_code(self, value, *args):
        tmp_data = self.get_company_code()
        pass_flag = False
        if value in tmp_data.keys():
            pass_flag = True
        return pass_flag

    # 阈值校验，在t_os_plant_storage_location_alloc表中plant_code=工厂代码对应的stor_loc_code库存地点是否存在
    def get_plant_storage(self):
        if not self.PLANT_STORAGE:
            query_data = self.db.query_sql(
                " select `plant_code`,`stor_loc_code` from `t_os_plant_storage_location_alloc`")
            temp_dic = defaultdict(list)
            for item in query_data:
                temp_dic[item['plant_code']].append(item['stor_loc_code'])
            self.PLANT_STORAGE = dict(temp_dic)
        return self.PLANT_STORAGE or {}

    def check_plant_storage(self, value, *args):
        tmp_data = self.get_plant_storage()
        pass_flag = False
        plant = args[0]
        error_msg = f'库存地点 {value} 不在 工厂{plant} 下'
        if value in tmp_data.get(plant,[]):
            pass_flag = True
        return pass_flag, error_msg

    def get_special_inventory_status(self):
        if not self.SPE_INV_STATUS:
            tmp_data = self.db.query_sql(
                " select `special_inventory_status` from `t_special_inventory_status`")
            self.SPE_INV_STATUS = [i['special_inventory_status'] for i in tmp_data]
        return self.SPE_INV_STATUS or []

    def check_special_inventory_status(self, value, *args):
        tmp_data = self.get_special_inventory_status()
        pass_flag = False
        if value in tmp_data:
            pass_flag = True
        return pass_flag

    def get_inventory_status(self):
        if not self.INV_STATUS:
            tmp_data = self.db.query_sql(
                " select `inventory_status` from `t_inventory_status`")
            self.INV_STATUS = [i['inventory_status'] for i in tmp_data]
        return self.INV_STATUS or []

    def check_inventory_status(self, value, *args):
        tmp_data = self.get_inventory_status()
        pass_flag = False
        if value in tmp_data:
            pass_flag = True
        return pass_flag

    def get_mat_code(self):
        if not self.MAT_CODE:
            query_data = self.db.query_sql(
                " select `mat_code`,`basic_uom` from `t_mmd_material_basic_data`")

            temp_dic = defaultdict()
            for item in query_data:
                temp_dic[item['mat_code']] = item['basic_uom']
            self.MAT_CODE = dict(temp_dic)
        return self.MAT_CODE or {}

    def check_mat_code(self, value, *args):

        #get_mat_code
        tmp_data = self.get_mat_code()
        pass_flag = True
        if value and value not in tmp_data.keys():
            pass_flag = False
        return pass_flag

    def get_inventory_batch(self):
        if not self.INV_BATCH:
            # 根据物料编码 + 工厂代码 + 库存地点 + 批次号在t_inventory_batch_data表中是否存在
            query_data = self.db.query_sql(
                " select `mat_code`,`plant_code`,`stor_loc_code`,`batch_sn` from `t_inventory_batch_data`")
            self.INV_BATCH = [(i['mat_code'], i['plant_code'], i['stor_loc_code'], i['batch_sn']) for i in query_data]
        return self.INV_BATCH or []

    def check_inventory_batch(self, value, *args):
        tmp_data = self.get_inventory_batch()
        pass_flag = True
        error_msg = '物料编码 + 工厂代码 + 库存地点 + 批次号 不存在于库存表中'
        if args[0] and args not in tmp_data:
            pass_flag = False
        return pass_flag, error_msg

    def get_mmd_uom(self):
        if not self.MMD_UOM:
            query_data = self.db.query_sql(
                " select `unit_of_measure` from `t_mmd_uom`")
            self.MMD_UOM = [i['unit_of_measure'] for i in query_data]
        return self.MMD_UOM or []

    def check_mmd_uom(self, value, *args):
        tmp_data = self.get_mmd_uom()
        pass_flag = False
        if value in tmp_data:
            pass_flag = True
        error_msg = ''
        return pass_flag, error_msg

    def check_basic_uom(self, value, *args):
        tmp_data = self.get_mat_code()
        mat_code = args[0]
        pass_flag = True
        if mat_code and value != tmp_data.get(mat_code):
            pass_flag = False
        error_msg = f'物料{mat_code} 基本单位不为 {value}'
        return pass_flag, error_msg

    def get_document_status(self):
        if not self.DOC_STATUS_PASS:
            query_data = self.db.query_sql(
                " select `external_sys_unique_doc_sn` from `t_external_sys_md_item` where `document_status` = 4 and `mat_doc_sn` != '' group by `external_sys_unique_doc_sn`")
            self.DOC_STATUS_PASS = [i['external_sys_unique_doc_sn'] for i in query_data]
        return self.DOC_STATUS_PASS or []

    def check_document_status(self, value, *args):
        tmp_data = self.get_document_status()
        pass_flag = True
        if value in tmp_data:
            pass_flag = False
        error_msg = f'{value} 已存在过账成功的物料凭证，请对此数据重置后再重新获取'
        return pass_flag, error_msg

    def check_basic_currency(self, value, *args):
        tmp_data = self.get_company_code()
        pass_flag = False
        if value == tmp_data.get(args[0]):
            pass_flag = True
        error_msg = f'公司{args[0]} 本位币不为 {value}'
        return pass_flag, error_msg

    # 过账代码为1或7时，需要填写
    # 直接写入，校验在t_ao_pur_item_category-pur_item_cat中是否存在
    def get_pur_item_cat(self):
        if not self.PUR_ITEM_CAT:
            query_data = self.db.query_sql(
                " select `pur_item_cat` from `t_ao_pur_item_category`")
            self.PUR_ITEM_CAT = [i['pur_item_cat'] for i in query_data]
        return self.PUR_ITEM_CAT or []

    def check_pur_item_cat(self, value, *args):
        movement_info = self.get_movement_type()
        if movement_info.get(args[0], [None, None])[-1] in ['1', '7'] and value:
            tmp_data = self.get_pur_item_cat()
            pass_flag = False
            if value in tmp_data:
                pass_flag = True

        else:
            pass_flag = True
        error_msg = f'过账代码为{movement_info.get(args[0], [None, None])[-1]} pur_item_cat {value} 不在系统中'
        return pass_flag, error_msg


    def check_price_bt(self, value, *args):

        rel_po_sn = args[0]
        error_msg = f'关联采购订单存在 价格数据必需存在'
        if rel_po_sn:
            required = True
        else:
            required = False


        return required, error_msg


    def check_pur_item_cat_bt(self, value, *args):
        movement_info = self.get_movement_type()
        if movement_info.get(args[0], [None, None])[-1] in ['1', '7']:
            required = True
        else:
            required = False
        error_msg = f'过账代码为{movement_info.get(args[0], [None, None])[-1]} pur_item_cat 必填'
        return required, error_msg
    def check_account_allocation_category_bt(self, value, *args):
        movement_info = self.get_movement_type()
        if movement_info.get(args[0], [None, None])[-1] in ['1', '7']:
            required = True
        else:
            required = False
        error_msg = f'过账代码为{movement_info.get(args[0], [None, None])[-1]} account_allocation_category 必填'
        return required, error_msg
    # 过账代码为1或7时，需要填写
    # 直接写入，校验在t_ao_account_assignment_category - account_allocation_category是否存在
    def get_account_allocation_category(self):
        if not self.ACC_ALLOC_CAT:
            query_data = self.db.query_sql(
                " select `account_allocation_category` from `t_ao_account_assignment_category`")
            self.ACC_ALLOC_CAT = [i['account_allocation_category'] for i in query_data]
        return self.ACC_ALLOC_CAT or []

    def check_account_allocation_category(self, value, *args):
        movement_info = self.get_movement_type()
        if movement_info.get(args[0], [None, None])[-1] in ['1', '7'] and value:
            tmp_data = self.get_account_allocation_category()
            pass_flag = False
            if value in tmp_data:
                pass_flag = True
        else:
            pass_flag = True
        error_msg = f'过账代码为{movement_info.get(args[0], [None, None])[-1]} account_allocation_category {value} 不在系统中'
        return pass_flag, error_msg


# 外部系统数据存储
def external_system_save(doc_data):
    # 外部系统数据传入并存储
    db = DbHelper()

    all_count, pass_count, insert_header_data, insert_items_data, items_data, msg = external_system_check(doc_data,
                                                                                                          db=db)

    if not msg:
        external_sys_unique_doc_sn_ls = [i['external_sys_unique_doc_sn'] for i in insert_header_data]
        db.exec_sql("""
        DELETE FROM `t_external_sys_md_header` WHERE `external_sys_unique_doc_sn` in ({})

        """.format(','.join([repr(i) for i in external_sys_unique_doc_sn_ls])))

        db.exec_sql("""
        DELETE FROM `t_external_sys_md_item` WHERE `external_sys_unique_doc_sn` in ({})
        """.format(','.join([repr(i) for i in external_sys_unique_doc_sn_ls])))

        db.batchInsertToDB('t_external_sys_md_header', insert_header_data)
        db.batchInsertToDB('t_external_sys_md_item', insert_items_data)
    return all_count, pass_count, items_data, msg
    #


def external_system_check(doc_data, db=None):
    if db is None:
        db = DbHelper()
    cache_cls = Cache_Class(db=db)
    header_rules = [
        ValidationRule(field="external_sys_unique_doc_sn", required=True, field_type=str, length=LengthValidation(
            enabled=True,
            operator=LengthOperator.LE,
            value=50,
            error_msg="外部系统唯一凭证号长度不可大于50"
        ),
                       custom_validator=cache_cls.check_document_status,
                       ),
        ValidationRule(field="exchange_rate", required=False, field_type=float),
        ValidationRule(field="document_date", required=True, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.EQ,
                           value=10,
                           error_msg="凭证日期格式错误"
                       )),
        ValidationRule(field="posting_date", required=True, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.EQ,
                           value=10,
                           error_msg="过账日期格式错误"
                       )),
        ValidationRule(field="reversal_mark", required=True, field_type=int,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.EQ,
                           value=1,
                           error_msg="reversal_mark 请传入 0/1",

                       ),
                       threshold_enabled=True, operator=CompareOperator.IN,
                       allowed_values=[0, 1],
                       threshold_enabled_msg="{}请输入0/1".format('reversal_mark')
                       ),
        ValidationRule(field="company_code", required=True, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=6,
                           error_msg="公司代码长度超过6"
                       ),
                       threshold_enabled=True, operator=CompareOperator.IN,
                       allowed_values=cache_cls.get_no_supply_chain_document_flag(),
                       threshold_enabled_msg="{} 无供应链单据标识不为1 请检查".format('公司代码')
                       ),
        ValidationRule(field="summary_unique_number", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=64,
                           error_msg="summary_unique_number长度超过64"
                       )),
        ValidationRule(field="vendor_dn", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=20,
                           error_msg="{}长度超过{}".format('vendor_dn', 20)
                       )),
        ValidationRule(field="remarks_1", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=20,
                           error_msg="{}长度超过{}".format('remarks_1', 20)
                       )),
        ValidationRule(field="remarks_2", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=20,
                           error_msg="{}长度超过{}".format('remarks_2', 20)
                       )),
        ValidationRule(field="reserved1", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=255,
                           error_msg="{}长度超过{}".format('reserved1', 255)
                       )),
        ValidationRule(field="reserved2", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=255,
                           error_msg="{}长度超过{}".format('reserved2', 255)
                       )),
        ValidationRule(field="reserved3", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=255,
                           error_msg="{}长度超过{}".format('reserved3', 255)
                       )),
        ValidationRule(field="reserved4", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=30,
                           error_msg="{}长度超过{}".format('reserved4', 30)
                       )),
        ValidationRule(field="reserved5", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=30,
                           error_msg="{}长度超过{}".format('reserved5', 30)
                       )),
        ValidationRule(field="reserved6", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=30,
                           error_msg="{}长度超过{}".format('reserved6', 30)
                       )),
        ValidationRule(field="reserved7", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=30,
                           error_msg="{}长度超过{}".format('reserved7', 30)
                       )),
        ValidationRule(field="reserved8", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=30,
                           error_msg="{}长度超过{}".format('reserved8', 30)
                       )),
        ValidationRule(field="reserved9", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=30,
                           error_msg="{}长度超过{}".format('reserved9', 30)
                       )),
        ValidationRule(field="reserved10", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=30,
                           error_msg="{}长度超过{}".format('reserved10', 30)
                       )),
        ValidationRule(field="reversal_reason", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=32,
                           error_msg="{}长度超过{}".format('reversal_reason', 32)
                       )),
        ValidationRule(field="reversal_remark", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=255,
                           error_msg="{}长度超过{}".format('reversal_remark', 255)
                       )),
        ValidationRule(field="external_sys_document_create_date", required=True, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.EQ,
                           value=10,
                           error_msg="{}格式不正确".format('external_sys_document_create_date')
                       ))
    ]
    item_rules = [

        ValidationRule(field="external_sys_unique_doc_sn", required=True, field_type=str, length=LengthValidation(
            enabled=True,
            operator=LengthOperator.LE,
            value=50,
            error_msg="外部系统唯一凭证号长度不可大于50"
        ),
                       ),
        ValidationRule(field="external_sys_unique_doc_items", required=True, field_type=int),
        ValidationRule(field="line_id", required=True, field_type=int),
        ValidationRule(field="parent_id", required=False, field_type=int),

        ValidationRule(field="quality_insp_post_mark", required=False, field_type=int,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.EQ,
                           value=1,
                           error_msg="quality_insp_post_mark 请输入 0/1"
                       ),
                       threshold_enabled=True, operator=CompareOperator.IN,
                       allowed_values=[0, 1],
                       threshold_enabled_msg="{}请输入0/1".format('quality_insp_post_mark')
                       ),

        ValidationRule(field="rev_doc_year", required=False, field_type=int,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.EQ,
                           value=4,
                           error_msg="rev_doc_year 长度为 4"
                       )),
        ValidationRule(field="rev_doc_sn", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=18,
                           error_msg="{}长度超过{}".format('rev_doc_sn', 18)
                       )),
        ValidationRule(field="rev_doc_items", required=False, field_type=int,
                       ),

        ValidationRule(field="movement_type", required=True, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=6,
                           error_msg="{}长度超过{}".format('movement_type', 6)
                       )
                       ),
        ValidationRule(field="plant_code", required=True, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=6,
                           error_msg="{}长度超过{}".format('plant_code', 6)
                       )
                       ),
        ValidationRule(field="company_code", required=True, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=6,
                           error_msg="{}长度超过{}".format('company_code', 6)
                       )
                       ),

        ValidationRule(field="stor_loc_code", required=True, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=50,
                           error_msg="{}长度超过{}".format('stor_loc_code', 50)
                       )
                       ),

        ValidationRule(field="special_inventory_status1", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=2,
                           error_msg="{}长度超过{}".format('special_inventory_status1', 2)
                       )
                       # 在t_special_inventory_status-special_inventory_status表中是否存在
                       ),

        ValidationRule(field="special_inventory_status2", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=2,
                           error_msg="{}长度超过{}".format('special_inventory_status2', 2)
                       )
                       ),

        ValidationRule(field="inventory_status", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=2,
                           error_msg="{}长度超过{}".format('inventory_status', 4)
                       )
                       ),
        ValidationRule(field="mat_code", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=40,
                           error_msg="{}长度超过{}".format('mat_code', 40)
                       )
                       # t_mmd_material_basic_data-mat_code
                       ),

        ValidationRule(field="mat_group", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=6,
                           error_msg="{}长度超过{}".format('mat_group', 6)
                       )
                       # t_mmd_material_basic_data-mat_code
                       ),

        ValidationRule(field="batch_sn", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=40,
                           error_msg="{}长度超过{}".format('mat_code', 40)
                       )
                       # 根据物料编码+工厂代码+库存地点+批次号在t_inventory_batch_data表中是否存在
                       ),

        ValidationRule(field="transaction_qty", required=True, field_type=float
                       ),

        ValidationRule(field="transaction_uom", required=True, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=4,
                           error_msg="{}长度超过{}".format('transaction_uom', 4)
                       )
                       ),
        ValidationRule(field="basic_qty", required=False, field_type=float
                       ),
        ValidationRule(field="basic_uom", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=4,
                           error_msg="{}长度超过{}".format('basic_uom', 4)
                       )
                       ),

        ValidationRule(field="parallel_qty", required=False, field_type=float),
        ValidationRule(field="pricing_unit_quantity", required=True, field_type=float),

        ValidationRule(field="pricing_unit_of_measure", required=True, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=4,
                           error_msg="{}长度超过{}".format('pricing_unit_of_measure', 4)
                       )

                       ),

        ValidationRule(field="transaction_amount", required=False, field_type=float
                       ),
        ValidationRule(field="transaction_currency", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=3,
                           error_msg="{}长度超过{}".format('transaction_currency', 3)
                       ),
                       default_value_func=cache_cls.get_basic_currency_daf,
                       depend_str='company_code'
                       # 若未传值，则默认根据公司代码取本位币os_company-basic_currency

                       ),

        ValidationRule(field="rel_po_sn", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=18,
                           error_msg="{}长度超过{}".format('rel_po_sn', 18)
                       )
                       ),
        ValidationRule(field="rel_po_items", required=False, field_type=int,
                       ),
        ValidationRule(field="rel_po_component_number", required=False, field_type=int),
        ValidationRule(field="rel_po_comp_batch_num", required=False, field_type=int),

        ValidationRule(field="receipt_completed_flag", required=False, field_type=int,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=1,
                           error_msg="{}请输入0/1".format('receipt_completed_flag')
                       ),
                       threshold_enabled=True, operator=CompareOperator.IN,
                       allowed_values=[0, 1],
                       threshold_enabled_msg="{}请输入0/1".format('receipt_completed_flag')
                       ),

        ValidationRule(field="batch_closure_flag", required=False, field_type=int,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=1,
                           error_msg="{}请输入0/1".format('batch_closure_flag')
                       ),
                       threshold_enabled=True, operator=CompareOperator.IN,
                       allowed_values=[0, 1],
                       threshold_enabled_msg="{}请输入0/1".format('batch_closure_flag')
                       ),

        ValidationRule(field="batch_closure_date", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.EQ,
                           value=10,
                           error_msg="{}输入 日期格式YYYY-mm-dd".format('batch_closure_date')
                       )
                       ),
        ValidationRule(field="prodosn", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=32,
                           error_msg="{}长度超过{}".format('prodosn', 32)
                       )
                       ),
        ValidationRule(field="prodo_component_number", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=6,
                           error_msg="{}长度超过{}".format('prodo_component_number', 6)
                       )
                       ),
        ValidationRule(field="rel_dn_sn", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=18,
                           error_msg="{}长度超过{}".format('rel_dn_sn', 18)
                       )
                       ),
        ValidationRule(field="rel_dn_item", required=False, field_type=int),

        ValidationRule(field="rel_procure_dn_sn", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=18,
                           error_msg="{}长度超过{}".format('rel_procure_dn_sn', 18)
                       )
                       ),
        ValidationRule(field="rel_procure_dn_item", required=False, field_type=int
                       ),

        ValidationRule(field="pod_related", required=False, field_type=int,
                       threshold_enabled=True, operator=CompareOperator.IN,
                       allowed_values=[0, 1]
                       , threshold_enabled_msg='pod_related 请输入 0/1'

                       ),

        ValidationRule(field="ro_sn", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=18,
                           error_msg="{}长度超过{}".format('ro_sn', 18)
                       )
                       ),
        ValidationRule(field="ro_items", required=False, field_type=int
                       ),

        ValidationRule(field="inv_transfer_order_no", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=40,
                           error_msg="{}长度超过{}".format('inv_transfer_order_no', 40)
                       )
                       ),
        ValidationRule(field="inv_transfer_order_items", required=False, field_type=int
                       ),

        ValidationRule(field="rel_so_sn", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=18,
                           error_msg="{}长度超过{}".format('rel_so_sn', 18)
                       )
                       ),
        ValidationRule(field="rel_so_items", required=False, field_type=int
                       ),

        ValidationRule(field="po_vendor", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=20,
                           error_msg="{}长度超过{}".format('po_vendor', 20)
                       )
                       ),
        ValidationRule(field="associated_customer", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=20,
                           error_msg="{}长度超过{}".format('associated_customer', 20)
                       )
                       ),
        ValidationRule(field="customer_code", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=20,
                           error_msg="{}长度超过{}".format('customer_code', 20)
                       )
                       ),
        ValidationRule(field="so_sn", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=18,
                           error_msg="{}长度超过{}".format('so_sn', 18)
                       )
                       ),
        ValidationRule(field="so_items", required=False, field_type=int
                       ),

        ValidationRule(field="project_sn", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=32,
                           error_msg="{}长度超过{}".format('project_sn', 32)
                       )
                       ),
        ValidationRule(field="vendor_code", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=20,
                           error_msg="{}长度超过{}".format('vendor_code', 20)
                       )
                       ),
        ValidationRule(field="po_sn", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=18,
                           error_msg="{}长度超过{}".format('po_sn', 18)
                       )
                       ),

        ValidationRule(field="po_items", required=False, field_type=int
                       ),

        ValidationRule(field="wbs_elements", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=32,
                           error_msg="{}长度超过{}".format('wbs_elements', 32)
                       )
                       ),
        ValidationRule(field="cost_center", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=18,
                           error_msg="{}长度超过{}".format('cost_center', 18)
                       )
                       ),
        ValidationRule(field="cost_business_object", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=32,
                           error_msg="{}长度超过{}".format('cost_business_object', 32)
                       )
                       ),

        ValidationRule(field="cost_business_object1", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=32,
                           error_msg="{}长度超过{}".format('cost_business_object1', 32)
                       )
                       ),
        ValidationRule(field="profit_center", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=12,
                           error_msg="{}长度超过{}".format('profit_center', 12)
                       )
                       ),
        ValidationRule(field="accounting_subjects", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=20,
                           error_msg="{}长度超过{}".format('accounting_subjects', 20)
                       )
                       ),
        ValidationRule(field="asset_code1", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=12,
                           error_msg="{}长度超过{}".format('asset_code1', 12)
                       )
                       ),
        ValidationRule(field="asset_code2", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=4,
                           error_msg="{}长度超过{}".format('asset_code2', 4)
                       )
                       ),
        ValidationRule(field="movement_reason", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=6,
                           error_msg="{}长度超过{}".format('movement_reason', 6)
                       )
                       ),
        ValidationRule(field="equipment_code", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=50,
                           error_msg="{}长度超过{}".format('equipment_code', 50)
                       )
                       ),

        ValidationRule(field="express_delivery", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=50,
                           error_msg="{}长度超过{}".format('express_delivery', 50)
                       )
                       ),
        ValidationRule(field="pur_item_cat", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=2,
                           error_msg="{}长度超过{}".format('pur_item_cat', 2)
                       )
                       ),

        ValidationRule(field="account_allocation_category", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=2,
                           error_msg="{}长度超过{}".format('account_allocation_category', 2)
                       )
                       ),

        ValidationRule(field="po_qty", required=False, field_type=float
                       ),

        ValidationRule(field="pur_uom", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=4,
                           error_msg="{}长度超过{}".format('pur_uom', 4)
                       )
                       ),

        ValidationRule(field="free_mark", required=False, field_type=int,
                       threshold_enabled=True, operator=CompareOperator.IN,
                       allowed_values=[0, 1]
                       , threshold_enabled_msg='free_mark 请输入 0/1'
                       ),
        ValidationRule(field="rework_mark", required=False, field_type=int,
                       threshold_enabled=True, operator=CompareOperator.IN,
                       allowed_values=[0, 1]
                       , threshold_enabled_msg='rework_mark 请输入 0/1'
                       ),

        ValidationRule(field="rework_type", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=2,
                           error_msg="{}长度超过{}".format('rework_type', 2)
                       )
                       ),

        # --    `rework_type`  VARCHAR(2) NOT NULL DEFAULT '' COMMENT '加工工序',

        ValidationRule(field="reference1_item", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=255,
                           error_msg="{}长度超过{}".format('reference1_item', 255)
                       )
                       ),

        ValidationRule(field="reference2_item", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=255,
                           error_msg="{}长度超过{}".format('reference2_item', 255)
                       )
                       ),

        ValidationRule(field="reference3_item", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=255,
                           error_msg="{}长度超过{}".format('reference3_item', 255)
                       )
                       ),
        ValidationRule(field="summary_line", required=False, field_type=int
                       ),

        ValidationRule(field="rcv_plant_code", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=6,
                           error_msg="{}长度超过{}".format('rcv_plant_code', 6)
                       )
                       ),

        ValidationRule(field="rcv_stor_loc_code", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=50,
                           error_msg="{}长度超过{}".format('rcv_stor_loc_code', 50)
                       )
                       ),
        ValidationRule(field="rcv_special_inventory_status1", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=2,
                           error_msg="{}长度超过{}".format('rcv_special_inventory_status1', 2)
                       )
                       ),

        ValidationRule(field="rcv_special_inventory_status2", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=2,
                           error_msg="{}长度超过{}".format('rcv_special_inventory_status2', 2)
                       )
                       ),

        ValidationRule(field="rcv_inventory_status", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=4,
                           error_msg="{}长度超过{}".format('rcv_inventory_status', 4)
                       ),
                       default_value_func=cache_cls.get_inventory_status_daf,
                       depend_str='movement_type'
                       ),

        ValidationRule(field="rcv_mat_code", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=40,
                           error_msg="{}长度超过{}".format('rcv_mat_code', 40)
                       )
                       ),

        ValidationRule(field="rcv_batch_sn", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=32,
                           error_msg="{}长度超过{}".format('rcv_batch_sn', 32)
                       )
                       ),

        ValidationRule(field="rcv_customer_code", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=20,
                           error_msg="{}长度超过{}".format('rcv_customer_code', 20)
                       )
                       ),

        ValidationRule(field="rcv_so_sn", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=20,
                           error_msg="{}长度超过{}".format('rcv_so_sn', 20)
                       )
                       ),

        ValidationRule(field="rcv_so_sn", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=18,
                           error_msg="{}长度超过{}".format('rcv_so_sn', 18)
                       )
                       ),
        ValidationRule(field="rcv_so_items", required=False, field_type=int),

        ValidationRule(field="rcv_project_sn", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=32,
                           error_msg="{}长度超过{}".format('rcv_project_sn', 32)
                       )
                       ),
        ValidationRule(field="rcv_vendor_code", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=20,
                           error_msg="{}长度超过{}".format('rcv_vendor_code', 20)
                       )
                       ),
        ValidationRule(field="rcv_po_sn", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=18,
                           error_msg="{}长度超过{}".format('rcv_po_sn', 18)
                       )
                       ),

        ValidationRule(field="rcv_po_items", required=False, field_type=int
                       ),

        ValidationRule(field="reserved1", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=255,
                           error_msg="{}长度超过{}".format('reserved1', 255)
                       )
                       ),
        ValidationRule(field="reserved2", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=255,
                           error_msg="{}长度超过{}".format('reserved2', 255)
                       )
                       ),
        ValidationRule(field="reserved3", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=255,
                           error_msg="{}长度超过{}".format('reserved3', 255)
                       )
                       ),
        ValidationRule(field="reserved4", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=30,
                           error_msg="{}长度超过{}".format('reserved4', 30)
                       )
                       ),
        ValidationRule(field="reserved5", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=30,
                           error_msg="{}长度超过{}".format('reserved5', 30)
                       )
                       ),
        ValidationRule(field="reserved6", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=30,
                           error_msg="{}长度超过{}".format('reserved6', 30)
                       )
                       ),
        ValidationRule(field="reserved7", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=30,
                           error_msg="{}长度超过{}".format('reserved7', 30)
                       )
                       ),
        ValidationRule(field="reserved8", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=30,
                           error_msg="{}长度超过{}".format('reserved8', 30)
                       )
                       ),
        ValidationRule(field="reserved9", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=30,
                           error_msg="{}长度超过{}".format('reserved9', 30)
                       )
                       ),
        ValidationRule(field="reserved10", required=False, field_type=str,
                       length=LengthValidation(
                           enabled=True,
                           operator=LengthOperator.LE,
                           value=30,
                           error_msg="{}长度超过{}".format('reserved10', 30)
                       )
                       )
        ,
        ValidationRule(field="price",
                       required_func=cache_cls.check_price_bt,
                       required_func_depend=['rel_po_sn'],
                       field_type=list
                       )

    ]
    header_validator = DynamicListValidator(header_rules)
    item_validator = DynamicListValidator(item_rules)

    is_valid, results, all_count, pass_count = header_validator.validate(doc_data)
    if len(results) == 1 and isinstance(results[0], ValidationResult):
        return 0, 0, [], [], [], results[0].__dict__.get('errors', [None])[0]
    items_data = []
    all_count = 0
    pass_count = 0
    insert_header_data = []
    insert_items_data = []
    for doc_item in doc_data:
        items_data = copy.deepcopy(doc_item['item'])
        message_text = doc_item['message_text']
        doc_item.pop('item')
        doc_item.pop('message_text')

        if doc_item['document_status'] == 2:
            item_is_valid, item_results, item_all_count, item_pass_count = item_validator.validate(items_data)

            if len(item_results) == 1 and isinstance(item_results[0], ValidationResult):
                return 0, 0, [], [], [], item_results[0].__dict__.get('errors', [None])[0]

            if item_is_valid:
                insert_header_data.append(doc_item)
                insert_items_data.extend(items_data)
        else:

            item_all_count = len(items_data)
            item_pass_count = 0

        for i in items_data:
            i.update(doc_item)
            i['message_text'] = message_text + i['message_text']
        all_count += item_all_count
        pass_count += item_pass_count
    return all_count, pass_count, insert_header_data, insert_items_data, items_data, ''


# 同步脚本调用
def dynamic_call(module_path, function_name, *args, **kwargs):
    """
    动态调用跨文件方法
    Args:
        module_path: 模块路径，如 'modules.math_ops' 或 './modules/math_ops.py'
        function_name: 函数名
        *args: 位置参数
        **kwargs: 关键字参数
    Returns:
        函数执行结果
    """
    import importlib
    try:
        if module_path.endswith('.py'):
            module_path = module_path.replace('/', '.').replace('\\', '.').replace('.py', '')
        # 动态导入模块
        module = importlib.import_module(module_path)
        # 获取函数
        if hasattr(module, function_name):
            func = getattr(module, function_name)
            return func(*args, **kwargs)
        else:
            raise AttributeError(f"模块 {module_path} 中没有找到函数 {function_name}")

    except ImportError as e:
        print(f"导入模块失败: {e}")
        return f"导入模块失败: {e}"
    except Exception as e:
        print(f"调用失败: {e}")
        return f"调用失败: {e}"


# 数据同步接口
@ResetResponse()
def posting_platform_data_synchronization(**kwargs):
    from BaseConfig import get_config
    script_name = get_config("without_doc_posting_platform.script_name")
    script_func = get_config("without_doc_posting_platform.script_func")

    if not (script_name and script_func):
        return ResponseData(ResponseStatusCode.Error, '未能获取到 无单据物料凭证过账平台 同步接口方法配置请检查', [])

    document_create_date = kwargs.get('document_create_date')
    company_code = kwargs.get('company_code')
    dynamic_call_res = dynamic_call(script_name, script_func, document_create_date=document_create_date,
                                    company_code=company_code)
    if isinstance(dynamic_call_res, str):
        return ResponseData(ResponseStatusCode.Error, dynamic_call_res, [])

    if isinstance(dynamic_call_res, tuple):
        if dynamic_call_res[0] == 200:

            data = dynamic_call_res[-1]

            all_count, pass_count, items_data, msg = external_system_save(data)

            if msg:
                return ResponseData(ResponseStatusCode.Error,
                                    msg,
                                    items_data)

            return ResponseData(ResponseStatusCode.Success,
                                "完成",
                                items_data,count_msg = f"执行结果:同步数据{all_count}条，成功{pass_count}条，失败{all_count - pass_count}条")
        else:
            return ResponseData(ResponseStatusCode.Error, f"失败：{dynamic_call_res[1]}", dynamic_call_res[-1])


# 过账平台数据获取
def get_posting_platform_document(document_create_date:list[str], company_code:list|str, document_status:int|list,mat_doc_sn:str|list, db:DbHelper|None=None):
    if db is None:
        db = DbHelper()
    sql = """
    select
    smi.`message_text`,
    smd.`external_sys_unique_doc_sn`,
    smd.`external_sys_document_create_date`,
    smd.`exchange_rate`,
    smd.`document_date`,
    smd.`posting_date`,
    smd.`reversal_mark`,
    smd.`company_code`,
    smd.`summary_unique_number`,
    smd.`vendor_dn`,
    smd.`remarks_1`,
    smd.`remarks_2`,
    smd.`reserved1` as `h_reserved1`,
    smd.`reserved2` as `h_reserved2`,
    smd.`reserved3` as `h_reserved3`,
    smd.`reserved4` as `h_reserved4`,
    smd.`reserved5` as `h_reserved5`,
    smd.`reserved6` as `h_reserved6`,
    smd.`reserved7` as `h_reserved7`,
    smd.`reserved8` as `h_reserved8`,
    smd.`reserved9` as `h_reserved9`,
    smd.`reserved10` as `h_reserved10`,
    smd.`reversal_reason`,
    smd.`reversal_remark`,
    smd.`external_sys_document_create_date`,

    smi.*
    from
    `t_external_sys_md_header` as smd
    left join `t_external_sys_md_item` as smi on smd.`external_sys_unique_doc_sn` = smi.`external_sys_unique_doc_sn`

    where 1=1

    """
    if document_create_date:
        sql += f" and smd.`external_sys_document_create_date` between '{document_create_date[0]}' and '{document_create_date[1]}'"

    if company_code:
        if isinstance(company_code,list):
            sql += f" and smd.`company_code`  in ({','.join([repr(i) for i in company_code])} )"
        else:
            sql += f" and smd.`company_code` = {repr(company_code)} "

    if document_status:
        if isinstance(document_status, list):
            sql += f" and smi.`document_status` in ({','.join(document_status)})"
        else:
            sql += f" and smi.`document_status` = {document_status}"
    if mat_doc_sn:
        if isinstance(mat_doc_sn, list):
            sql += f" and smi.`mat_doc_sn` in ({','.join([repr(i) for i in mat_doc_sn])})"
        else:
            sql += f" and smi.`mat_doc_sn` = {repr(mat_doc_sn)}"

    external_sys_md_data = db.query_sql(sql,printSql=True)

    return external_sys_md_data


@ResetResponse(params=["document_create_date", "company_code", "document_status","mat_doc_sn"], excelName="过账平台数据校验")
def posting_platform_query(document_create_date:list[str], company_code:list|str, document_status:int,mat_doc_sn) -> ResponseData:
    db = DbHelper()
    external_sys_md_data = get_posting_platform_document(document_create_date, company_code, document_status,mat_doc_sn, db=db)
    from ToolsMethods import GetDisplay
    other_field = {
        "h_reserved1": "预留字段1",
        "h_reserved2": "预留字段2",
        "h_reserved3": "预留字段3",
        "h_reserved4": "预留字段4",
        "h_reserved5": "预留字段5",
        "h_reserved6": "预留字段6",
        "h_reserved7": "预留字段7",
        "h_reserved8": "预留字段8",
        "h_reserved9": "预留字段9",
        "h_reserved10": "预留字段10"
    }
    display = GetDisplay(['t_external_sys_md_header','t_external_sys_md_item'],external_sys_md_data,other_field_name = other_field)

    return ResponseData(ResponseStatusCode.Success, f"成功", external_sys_md_data,display=display)


# 过帐平台检查执行
@ResetResponse(params=["external_sys_md_data"], excelName="过账平台数据校验")
def posting_platform_check_exe(external_sys_md_data):

    is_valid, results, all_count, pass_count = posting_platform_check(external_sys_md_data)

    type_errors = [','.join(i.type_errors )for i in results if i.type_errors]

    if not type_errors:
        # 更新数据
        reply_writing_external_sys_md_item(external_sys_md_data)
        return ResponseData(ResponseStatusCode.Success,
                            "完成",
                            external_sys_md_data,count_msg =f"执行结果:执行数据{all_count}条，成功{pass_count}条，失败{all_count - pass_count}条")
    else:

        return ResponseData(500,
                            f"执行报错: {','.join(type_errors)}",
                            external_sys_md_data)

# 过账平台校验
def posting_platform_check(doc_data):
    cache_cls = Cache_Class()
    header_rules = [
        ValidationRule(field="company_code",
                       threshold_enabled=True, operator=CompareOperator.IN,
                       allowed_values=cache_cls.get_company_code(),
                       threshold_enabled_msg='公司代码不在系统中',
                       ),
    ]
    item_rules = [
        ValidationRule(field="Outer_verif_rule",
                       cross_field_validator=cache_cls.check_md_price_data
                       ),

        ValidationRule(field="quality_insp_post_mark", required=False, field_type=int,

                       threshold_enabled=True, operator=CompareOperator.IN,
                       allowed_values=[0, 1],
                       threshold_enabled_msg="{}请输入0/1".format('quality_insp_post_mark')
                       , custom_validator=cache_cls.check_mat_quality,
                       custom_validator_depend_on=['plant_code', 'mat_code', 'movement_type']  # !!!!!!待补充校验
                       ),

        ValidationRule(field="movement_type",
                       threshold_enabled=True, operator=CompareOperator.IN,
                       allowed_values=list(cache_cls.get_movement_type().keys()),  # t_movement_type-movement_type
                       threshold_enabled_msg='移动类型不在系统中'
                       ),
        ValidationRule(field="plant_code",
                       threshold_enabled=True, operator=CompareOperator.IN,
                       allowed_values=cache_cls.get_plant_code()  # t_os_plant-plant_code
                       , threshold_enabled_msg='工厂代码不在系统中'
                       ),
        ValidationRule(field="company_code",
                       threshold_enabled=True, operator=CompareOperator.IN,
                       allowed_values=cache_cls.get_company_code()  # t_os_company-company_code
                       , threshold_enabled_msg='公司代码不在系统中'
                       ),

        ValidationRule(field="stor_loc_code",
                       custom_validator=cache_cls.check_plant_storage,
                       custom_validator_depend_on=['plant_code']
                       ),

        ValidationRule(field="special_inventory_status1",
                       threshold_enabled=True, operator=CompareOperator.IN,
                       allowed_values=cache_cls.get_special_inventory_status()
                       , threshold_enabled_msg='特殊库存状态不在系统中'
                       # 在t_special_inventory_status-special_inventory_status表中是否存在
                       ),

        ValidationRule(field="inventory_status",
                       default_value_func=cache_cls.get_inventory_status_daf,
                       depend_str='movement_type',
                       threshold_enabled=True, operator=CompareOperator.IN,
                       allowed_values=cache_cls.get_inventory_status()
                       , threshold_enabled_msg='库存状态不在系统中'
                       # 1、检查移动类型的库存状态有值，则取移动类型对应的库存状态，不可更改
                       # 2、若无则可以外部输入
                       # 3、阈值校验，在t_inventory_status-inventory_status表中是否存在
                       ),
        ValidationRule(field="mat_code", required=False,
                       threshold_enabled=True, operator=CompareOperator.IN,
                       allowed_values=list(cache_cls.get_mat_code().keys())
                       , threshold_enabled_msg='物料不在系统中'
                       # t_mmd_material_basic_data-mat_code
                       ),
        # ValidationRule(field="mat_group", required=False, field_type=str,
        #                threshold_enabled=True, operator=CompareOperator.IN,
        #                allowed_values=list(cache_cls.get_mat_group())
        #                , threshold_enabled_msg='物料不在系统中'
        #                ),

        ValidationRule(field="batch_sn", required=False, field_type=str,

                       # custom_validator=cache_cls.check_inventory_batch,
                       # custom_validator_depend_on=['mat_code', 'plant_code', 'stor_loc_code', 'batch_sn'],
                       # 根据物料编码+工厂代码+库存地点+批次号在t_inventory_batch_data表中是否存在
                       ),

        ValidationRule(field="transaction_uom", required=True, field_type=str,

                       threshold_enabled=True, operator=CompareOperator.IN,
                       allowed_values=cache_cls.get_mmd_uom()  # 阈值校验，在t_mmd_uom-unit_of_measure表中是否存在
                       , threshold_enabled_msg='transaction_uom交易单位不在系统中'
                       ),

        ValidationRule(field="basic_uom", required=False, field_type=str,

                       custom_validator=cache_cls.check_basic_uom,
                       custom_validator_depend_on=['mat_code']  # check_basic_uom阈值校验，在t_mmd_uom-unit_of_measure表中是否存在
                       ),
        ValidationRule(field="pricing_unit_quantity", required=True, field_type=float),
        ValidationRule(field="pricing_unit_of_measure", required=True, field_type=str,

                       threshold_enabled=True, operator=CompareOperator.IN,
                       allowed_values=cache_cls.get_mmd_uom()  # 阈值校验，在t_mmd_uom - unit_of_measure表中是否存在
                       , threshold_enabled_msg='pricing_unit_of_measure 单位不在系统中'

                       ),

        ValidationRule(field="transaction_currency", required=False, field_type=str,

                       default_value_func=cache_cls.get_basic_currency_daf,
                       depend_str='company_code'
                       # 若未传值，则默认根据公司代码取本位币os_company-basic_currency

                       ),

        ValidationRule(field="receipt_completed_flag", required=False, field_type=int,

                       threshold_enabled=True, operator=CompareOperator.IN,
                       allowed_values=[0, 1],
                       threshold_enabled_msg="{}请输入0/1".format('receipt_completed_flag')
                       ),

        ValidationRule(field="pod_related", required=False, field_type=int,
                       threshold_enabled=True, operator=CompareOperator.IN,
                       allowed_values=[0, 1]
                       , threshold_enabled_msg='pod_related 请输入 0/1'
                       ),

        ValidationRule(field="pur_item_cat",
                       # required_func=cache_cls.check_pur_item_cat_bt,
                       # required_func_depend=['movement_type'],
                       required=False, field_type=str,
                       # threshold_enabled=True, operator=CompareOperator.IN,
                       # allowed_values=cache_cls.get_pur_item_cat(),  # 过账代码为1或7时，需要填写直接写入，校验在t_ao_pur_item_category-pur_item_cat中是否存在
                       custom_validator=cache_cls.check_pur_item_cat,
                       custom_validator_depend_on=['movement_type']
                       # check_basic_uom阈值校验，在t_mmd_uom-unit_of_measure表中是否存在
                       ),

        ValidationRule(field="account_allocation_category",
                       # required_func=cache_cls.check_account_allocation_category_bt,
                       # required_func_depend=['movement_type'],
                       required=False, field_type=str,
                       custom_validator=cache_cls.check_account_allocation_category,
                       custom_validator_depend_on=['movement_type']
                       # 过账代码为1或7时，需要填写
                       # 直接写入，校验在t_ao_account_assignment_category-account_allocation_category是否存在
                       ),

        ValidationRule(field="po_qty", required=False, field_type=float
                       ),

        ValidationRule(field="free_mark", required=False, field_type=int,
                       threshold_enabled=True, operator=CompareOperator.IN,
                       allowed_values=[0, 1]
                       , threshold_enabled_msg='free_mark 请输入 0/1'
                       ),
        ValidationRule(field="rework_mark", required=False, field_type=int,
                       threshold_enabled=True, operator=CompareOperator.IN,
                       allowed_values=[0, 1]
                       , threshold_enabled_msg='rework_mark 请输入 0/1'
                       ),

        # --    `rework_type`  VARCHAR(2) NOT NULL DEFAULT '' COMMENT '加工工序',

        ValidationRule(field="rcv_plant_code", required=False, field_type=str,

                       threshold_enabled=True, operator=CompareOperator.IN,
                       allowed_values=cache_cls.get_plant_code()  # 阈值校验，在t_os_plant-plant_code表中是否存在
                       , threshold_enabled_msg='rcv_plant_code 接收工厂代码不在系统中'
                       ),

        ValidationRule(field="rcv_stor_loc_code", required=False, field_type=str,

                       custom_validator=cache_cls.check_plant_storage,
                       custom_validator_depend_on=['plant_code']
                       # 阈值校验，在t_os_plant_storage_location_alloc表中plant_code=工厂代码对应的stor_loc_code库存地点是否存在
                       ),
        ValidationRule(field="rcv_special_inventory_status1", required=False, field_type=str,

                       threshold_enabled=True, operator=CompareOperator.IN,
                       allowed_values=cache_cls.get_special_inventory_status()
                       , threshold_enabled_msg='rcv_special_inventory_status1 接收特殊库存状态不在系统中'
                       # 阈值校验，在t_special_inventory_status-special_inventory_status表中是否存在
                       ),

        ValidationRule(field="rcv_inventory_status", required=False, field_type=str,

                       default_value_func=cache_cls.get_inventory_status_daf,
                       depend_str='movement_type',
                       threshold_enabled=True, operator=CompareOperator.IN,
                       allowed_values=cache_cls.get_inventory_status()
                       , threshold_enabled_msg='rcv_inventory_status 接收库存状态不在系统中'
                       # 1、检查移动类型的库存状态有值，则取移动类型对应的库存状态，不可更改
                       # 2、若无则可以外部输入
                       # 3、阈值校验，在t_inventory_status-inventory_status表中是否存在
                       ),

        ValidationRule(field="rcv_mat_code", required=False, field_type=str,

                       threshold_enabled=True, operator=CompareOperator.IN,
                       allowed_values=list(cache_cls.get_mat_code().keys())
                       , threshold_enabled_msg='rcv_mat_code 接收物料不在系统中'
                       # 阈值校验，在t_mmd_material_basic_data-mat_code表中是否存在
                       ),

        ValidationRule(field="rcv_batch_sn", required=False, field_type=str,

                       # custom_validator=cache_cls.check_inventory_batch,
                       # custom_validator_depend_on=['mat_code', 'plant_code', 'stor_loc_code', 'batch_sn'],
                       # 根据物料编码+工厂代码+库存地点+批次号在t_inventory_batch_data表中是否存在
                       ),

    ]
    doc_data_validator = DynamicListValidator(header_rules + item_rules)
    is_valid, results, all_count, pass_count = doc_data_validator.validate(doc_data)

    type_errors = [','.join(i.errors) for i in results if i.errors]
    print(is_valid)
    print(type_errors)
    print(all_count)
    print(pass_count)
    return is_valid, results, all_count, pass_count


# 检查执行重置
@ResetResponse(params=["external_sys_md_data"])
def posting_platform_check_reset(external_sys_md_data):
    external_sys_unique_doc_sn_ls = []
    for i in external_sys_md_data:
        i['message_text'] = '成功'
        external_sys_unique_doc_sn_ls.append(repr(i['external_sys_unique_doc_sn']))

    sql = """
    UPDATE `t_external_sys_md_item` 
    SET `document_status` = 1, 
        `message_text` = '' 
    WHERE `external_sys_unique_doc_sn` in ({});
    """.format(','.join(external_sys_unique_doc_sn_ls))
    db = DbHelper()
    db.exec_sql(sql)
    all_count = len(external_sys_md_data)
    pass_count = len(external_sys_md_data)
    return ResponseData(ResponseStatusCode.Success,
                        "重置成功",
                        external_sys_md_data,count_msg =f"重置成功:执行数据{all_count}条，成功{pass_count}条，失败{0}条")

# 数据过账执行
@ResetResponse(params=["external_sys_md_data"])
def platform_posting(external_sys_md_data):
    # posting
    from SystemHelper import EnvKeys, SystemHelper
    sh = SystemHelper()
    user_id = sh.getEnv(EnvKeys.user_id)
    if external_sys_md_data:

        sql = """
                    SELECT
        	        `movement_type`,
                    `post_code`
                FROM
                    `t_movement_type` 
            """
        db = DbHelper()
        movement_type_info = db.query_sql(sql)
        movement_type_dic = {i['movement_type']: i['post_code'] for i in movement_type_info}
        external_sys_md_data = [{**i, 'post_code': movement_type_dic.get(i['movement_type'])} for i in
                                external_sys_md_data]
        post_fanl_data = sql_primeval_data(external_sys_md_data,
                                           ['external_sys_unique_doc_sn', 'post_code', 'exchange_rate',
                                            'document_date', 'posting_date',
                                            'reversal_mark',
                                            'company_code',
                                            'summary_unique_number',
                                            'vendor_dn',
                                            'remarks_1',
                                            'remarks_2',
                                            'h_reserved1',
                                            'h_reserved2',
                                            'h_reserved3',
                                            'h_reserved4',
                                            'h_reserved5',
                                            'h_reserved6',
                                            'h_reserved7',
                                            'h_reserved8',
                                            'h_reserved9',
                                            'h_reserved10',
                                            'reversal_reason',
                                            'reversal_remark',
                                            'external_sys_document_create_date'
                                            ]
                                           , 'plant_code',['external_sys_unique_doc_sn'])

        test_data = []
        test_run_check = True
        all_count, test_pass_count, pass_count = 0, 0, 0
        for item_res in post_fanl_data:
            # post_code: 过账代码
            # exchange_rate: 交易汇率
            # document_date: 凭证日期
            # posting_date: 过账日期
            # summary_unique_number: 汇总号
            # vendor_dn: 供应商交货单
            # remarks_1: 备注信息1
            # remarks_2: 备注信息2
            print(item_res)
            print(item_res['field'])
            all_count += len(item_res['field'])
            post_code, post_msg, post_error_list, mat_doc_sn, year = post_data('1', user_id, item_res,
                                                                               item_res['field'])
            print(post_code)
            print(post_msg)
            print(post_error_list)
            if post_code == 500:
                for i in item_res['detail']:
                    i['message_text'] = post_msg
                    i['message_text'] += ','.join(list(set(post_error_list)))
                code = 500
                msg = "失败"
                test_run_check = False
            else:
                test_pass_count += 1
                for i in item_res['detail']:
                    i['message_text'] = post_msg
                    i['mat_doc_sn'] = mat_doc_sn
            test_data += item_res['detail']

        fanil_data = []
        if test_run_check:
            code = 200
            msg = "过账成功"
            for item_res in post_fanl_data:

                # post_code: 过账代码
                # exchange_rate: 交易汇率
                # document_date: 凭证日期
                # posting_date: 过账日期
                # summary_unique_number: 汇总号
                # vendor_dn: 供应商交货单
                # remarks_1: 备注信息1
                # remarks_2: 备注信息2
                print(item_res)
                print(item_res['field'])
                post_code, post_msg, post_error_list, mat_doc_sn, year = post_data('0', user_id, item_res,
                                                                                   item_res['field'])

                if post_code == 500:
                    for i in item_res['detail']:
                        i['message_text'] = post_msg
                        i['message_text'] += ','.join(post_error_list)
                        i['document_status'] = 5
                    code = 500
                    msg = "过账失败"
                else:
                    pass_count += 1
                    for i in item_res['detail']:
                        i['message_text'] = mat_doc_sn
                        i['mat_doc_sn'] = mat_doc_sn
                        i['document_status'] = 4
                fanil_data += item_res['detail']
                # 过账结束 反写数据回表中
                reply_writing_external_sys_md_item(fanil_data)

            return ResponseData(code,
                                '过账执行完成',
                                fanil_data,count_msg =f'过账执行完成 共 {all_count}条,通过{pass_count}条,未通过{all_count - pass_count}条')
        else:

            return ResponseData(500,
                                '测试运行未通过',
                                test_data,count_msg =f'测试运行未通过校验 总共 {all_count}条,通过{test_pass_count}条,未通过{all_count - test_pass_count}条')

    return ResponseData(ResponseStatusCode.Error, f"无过账数据", external_sys_md_data)


def sql_primeval_data(primeval_data, key_ls, field_key, field_ls=[]):
    final_data = {}

    if primeval_data:
        field_ls = [i for i in primeval_data[0].keys() if i not in [x for x in key_ls if x not in field_ls]]

    rel_po_sn_item = {}
    for row in primeval_data:
        final_data_key = '_'.join([str(row[i]) for i in key_ls])
        sn_key = '_'.join([str(row[i]) for i in ['rel_po_sn', 'rel_po_items']])
        if final_data_key not in final_data:
            final_data[final_data_key] = {i.strip('h_') if i.startswith('h_') else i : row[i]  for i in key_ls}
            final_data[final_data_key]['field'] = []
            final_data[final_data_key]['detail'] = []

        if row[field_key]:
            s_dic = {i: row[i] for i in field_ls}
            line_id = len(final_data[final_data_key]['field']) + 1
            s_dic['line_id'] = line_id
            row['line_id'] = line_id
            final_data[final_data_key]['field'].append(s_dic)

            if sn_key != '_' and row.get('parent_id', '') == 0:
                rel_po_sn_item[sn_key] = line_id

    final_data = {}
    for row in primeval_data:
        final_data_key = '_'.join([str(row[i]) for i in key_ls])
        if final_data_key not in final_data:
            final_data[final_data_key] = {i.strip('h_') if i.startswith('h_') else i : row[i]  for i in key_ls}
            final_data[final_data_key]['field'] = []
            final_data[final_data_key]['detail'] = []

        if row[field_key]:

            # if row.get('parent_id', 0) == 1:
            #     row['parent_id'] = rel_po_sn_item[f"{row.get('rel_po_sn','')}_{row.get('rel_po_items','')}"]
            s_dic = {i: row[i] for i in field_ls}
            final_data[final_data_key]['field'].append(s_dic)
            final_data[final_data_key]['detail'].append(row)

    return list(final_data.values())


# 数据过账冲销
@ResetResponse(params=['external_sys_md_data'])
def posting_platform_reversal(external_sys_md_data):
    # reversal

    if external_sys_md_data:
        user_id = 0
        reverse_data_ls = external_sys_md_data
        all_count, pass_count = len(reverse_data_ls), 0
        groups = defaultdict(list)
        for idx, item in enumerate(reverse_data_ls):
            re_mat_doc_sn = item.get('mat_doc_sn')
            groups[re_mat_doc_sn].append((idx, item))

        for group_value, items in groups.items():
            posting_date = items[0][1].get('posting_date')
            mat_doc_year = posting_date[:4]
            code, msg, error_list, mat_doc_sn, year = reversal_md_doc(user_id, group_value, mat_doc_year, posting_date)
            document_status = 4
            if code != 200:
                msg = f'冲销失败:{msg}'

            else:
                pass_count += len(items)
                msg = f'冲销成功:{msg}'
                document_status = 2
            for idx, item in items:
                reverse_data_ls[idx]['message_text'] = msg + ','.join(error_list)
                reverse_data_ls[idx]['document_status'] = document_status
                if document_status == 2:
                    reverse_data_ls[idx]['mat_doc_sn'] = ''
            reply_writing_external_sys_md_item(reverse_data_ls)
        return ResponseData(200, "冲销执行完成",
                            reverse_data_ls,count_msg = f"冲销执行完成：总共 {all_count}条,通过{pass_count}条,未通过{all_count - pass_count}条")
    else:
        return ResponseData(ResponseStatusCode.Error, f"无数据，请检查", external_sys_md_data)



def reversal_md_doc(user_id, re_mat_doc_sn, mat_doc_year, posting_date):
    # 库存冲销
    # :param head: 凭证抬头 字典
    #         mat_doc_sn:物料凭证编码
    #         year:年度
    #         posting_date:过账日期
    #         summary_unique_number:汇总唯一号
    #         remarks_1:备注信息1
    #         remarks_2:备注信息2
    # :param item_no：凭证行项目编号 列表
    #         [1,2,3]
    # :return code: 状态码
    # :return msg: 消息
    # :return error_list: 错误明细
    # :return mat_doc_sn: 物料凭证号
    # :return year: 年度
    head = {
        'mat_doc_sn': re_mat_doc_sn,
        'year': mat_doc_year,
        'posting_date': posting_date,
    }

    code, msg, error_list, mat_doc_sn, year = reverse_data(user_id, head, [])
    return code, msg, error_list, mat_doc_sn, year


def reply_writing_external_sys_md_item(data):
    db = DbHelper()
    data = [{**i,'message_text':i.get('message_text','')[:255]} for i in data]
    status = db.batchUpdateToDB('t_external_sys_md_item', data,
                                DuplicateSQLKey=['message_text', 'document_status', 'mat_doc_sn'])

    if status < 0:
        raise ValueError('t_external_sys_md_item表回写失败')


@ResetResponse()
def mat_doc_sn_dropdown():
    db = DbHelper()
    sql = """
    select
    `mat_doc_sn`
    from
    `t_external_sys_md_item`
    where `document_status` = 4
    """
    data = db.query_sql(sql)
    return ResponseData(200, "成功", data)
