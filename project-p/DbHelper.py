#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import copy
import datetime
import hashlib
import inspect
import json
import re
import traceback
from enum import Enum
from typing import List

import sqlparse
from DxDateUtil import get_now_date_str
from libenhance import DbHandler, RedisHandler, SchemaHandler, SfException

dbErrorStatus = {
    -1000: "ER_UNKNOWN_ERROR",
    -1001: "ER_SERVER_SHUTDOWN",
    -1017: "ER_FILE_NOT_FOUND",
    -1022: "ER_DUP_KEY",
    -1062: "ER_DUP_ENTRY",
    -1064: "ER_PARSE_ERROR",
    -1065: "ER_EMPTY_QUERY",
    -1066: "ER_NONUNIQ_TABLE",
    -1205: "ER_LOCK_WAIT_TIMEOUT",
    -1213: "ER_LOCK_DEADLOCK",
    -1451: "ER_ROW_IS_REFERENCED",
    -1452: "ER_NO_REFERENCED_ROW",
    -1048: "SQL_ERROR",
    -1054: "SQL_ERROR",
    -1406: "SQL field length does not match ",
    -1364: "SQL ERROR: default value",
    -1402: "SQL field length does not match",
    -1146: "查询表不存在",
    # -1064: "查询sql语法错误",
    -1051: "删除表不存在错误状态码",
    # -1366: "字段类型不一致"
}


class SQLReplacer:
    """SQL函数替换"""

    def __init__(self, target_db='mysql'):
        self.target_db = target_db
        # 数据库函数映射
        self.SQL_KEYWORD_MAP = {
            'mysql': {
                'TO_DATE': 'DATE'
            }
        }

    def convert_sql(self, sql, target_db='mysql', extra_rules=None):
        """
        转换SQL关键字
        Args:
            sql: SQL语句
            target_db: 目标数据库
            extra_rules: 额外规则 {'OLD': 'new'}
        """
        from sqlparse.exceptions import SQLParseError

        try:
            result = sqlparse.format(sql, reindent=True, keyword_case='upper')
            rules = self.SQL_KEYWORD_MAP.get(target_db, {}).copy()
            if extra_rules:
                rules.update(extra_rules)

            for old, new in rules.items():
                result = re.sub(r'\b' + old + r'\b', new, result, flags=re.IGNORECASE)
        except SQLParseError as e:
            print(f"解析失败，SQL语句过于复杂: {e} 跳过格式化处理")
            result = sql
        return result


class DBException(SfException):
    def __init__(self, code: str, msg: str):
        self.code = str(code)
        self.msg = msg


def _generate_cache_key(sql: str) -> str:
    """生成缓存键"""
    normalized_sql = ' '.join(sql.strip().split())
    hash_key = hashlib.sha256(normalized_sql.encode()).hexdigest()
    return f"db_cache:{hash_key}"


def replace_outer_quotes(s):
    if s.startswith('"') and s.endswith('"'):
        return "'" + s[1:-1] + "'"
    return s


def fix_nullif_quotes(sql_string):
    pattern = r"'NULLIF\(\s*'[^']*'\s*,\s*'[^']*'\s*\)'"

    def replacer(match):
        # match.group(0) 是整个匹配，包括外层引号
        return match.group(0)[1:-1]  # 去掉首尾的单引号

    return re.sub(pattern, replacer, sql_string)


class DbHelper:
    _instance = None

    def __init__(self):
        self.db = DbHandler()
        self._redis_cache = RedisHandler()
        self._local_cache = {}
        self.schema = SchemaHandler()

    def get_table_columns(self, table_name, ignore_columns=None):
        '''
        此方法不再维护，慎用！！！！！！
        '''

        return self.get_columns_by_table(table_name)

    def build_insert_statement(self, db, table_name, columns):
        '''
        此方法不再维护，慎用！！！！！！
        '''
        placeholders = ', '.join(['%s'] * len(columns))
        return f"INSERT INTO `{table_name}` ({', '.join(columns)}) VALUES ({placeholders});"

    def insert_data(self, db=None, table_name='', data_list=None, ignore_columns=None, **kwargs):
        """
        此方法不再维护，慎用！！！！！！
        插入数据
        :param table_name: 表名
        :param db: db对象
        :param table_name: 表名
        :param data_list: 要插入的数据字典列表，其中字典对象 键为列名，值为对应列的值
        :param ignore_columns: 忽略字段
        """
        try:
            columns_info = self.get_table_columns(table_name, ignore_columns)
            columns = [col_info['name'] for col_info in columns_info]

            fields_value_list = []
            for record in data_list:
                single_record = []
                for col_info in columns_info:
                    if col_info['type'] in ['double', 'float', 'int', 'decimal', 'bigint', 'tinyint']:
                        field_value = record.get(col_info['name'], 0) or 0
                        field_value = str(field_value)
                    elif col_info['type'] in ['datetime', 'date', 'time']:
                        field_value = record.get(col_info['name'])
                        if field_value:
                            field_value = repr(field_value)
                        else:
                            field_value = 'NULL'
                    else:
                        field_value = record.get(col_info['name'], '') or ''
                        field_value = repr(field_value)
                    single_record.append(field_value)
                record_str = ','.join(single_record)
                fields_value_list.append(record_str)

            data_string = ', '.join(f"({vals})" for vals in fields_value_list)  # 兼容业务的拼sql方式
            insert_template = f"INSERT INTO `{table_name}` ({', '.join(columns)}) VALUES {data_string};"
            print("insert_template:", insert_template)

            if not db:
                db = self.db
            if isinstance(db, DbHandler):
                status = db.execute(insert_template, logflg=kwargs.get("logflg", True))
                return status
            elif isinstance(db, DbHelper):
                status = db.batchInsertToDB(table_name, data_list, ignore=ignore_columns, **kwargs)
                return status
        except Exception as e:
            print(f"Error inserting data: {e}")

    def update_data(self, db=None, table_name='', data_dict=None, where_clause='', **kwargs):
        """
        此方法不再维护，慎用！！！！！！
        更新数据
        :param table_name: 表名
        :param db: db对象
        :param data_dict: 要更新的数据字典
        :param where_clause: WHERE子句的条件字符串，例如 "id=123"
        """
        try:
            if not data_dict:
                return -1
            columns_info = self.get_table_columns(table_name)
            columns = list(data_dict.keys())
            for col_info in columns_info:
                if col_info['type'] in ['double', 'float', 'int', 'decimal', 'bigint', 'tinyint']:
                    if col_info['name'] in data_dict:
                        field_value = data_dict.get(col_info['name'], 0) or 0
                        data_dict[col_info['name']] = field_value
                elif col_info['type'] in ['datetime', 'date', 'time']:
                    if col_info['name'] in data_dict:
                        field_value = data_dict.get(col_info['name'])
                        if not field_value:
                            del data_dict[col_info['name']]

            set_clause = ', '.join([f"{col} = {repr(data_dict.get(col)) or ''}" for col in columns])
            update_sql = f"UPDATE `{table_name}` SET {set_clause} WHERE {where_clause};"
            if not db:
                db = self.db
            if isinstance(db, DbHandler):
                status = db.execute(update_sql, logflg=kwargs.get("logflg", True))
                return status
        except Exception as e:
            print(f"Error updating data: {e}")

    def delete_data(self, table_name, where_clause):
        """
        此方法不再维护，慎用！！！！！！
        删除数据
        :param table_name: 表名
        :param where_clause: WHERE子句的条件字符串，例如 "id=123"
        """
        query = f"DELETE FROM `{table_name}` WHERE {where_clause};"
        self.db.execute(query)

    def select_data(self, db, table_name, columns='*', where_clause=None, order_by=None, limit=None):
        """
        此方法不再维护，慎用！！！！！！
        查询数据
        :param table_name: 表名
        :param columns: 要查询的列名，逗号分隔的字符串，默认为 "*"
        :param where_clause: WHERE子句的条件字符串，可选
        :param order_by: ORDER BY子句，可选
        :param limit: LIMIT限制数量，可选
        :return: 查询结果列表
        """

        if isinstance(columns, list):
            columns = ', '.join([f'`{i}`' for i in columns])

        if isinstance(columns, str):
            columns = ', '.join([f'`{i}`' for i in columns.strip().split(',')])

        query_parts = [f"SELECT {columns} FROM `{table_name}`"]
        if where_clause:
            query_parts.append(f"WHERE {where_clause}")
        if order_by:
            query_parts.append(f"ORDER BY {order_by}")
        if limit is not None:
            query_parts.append(f"LIMIT {limit}")
        query = ' '.join(query_parts)
        if isinstance(db, DbHelper):
            print(f"select_data query:{query}")
            result_container = db.query_sql(query)
        else:
            result_container = []
            print(f"select_data query:{query}")
            db.query(query, result_container)
        return result_container

    def batchInsertToDB(self, tableName, dataList, batchSize=10000, ignore=[], DuplicateSQL=None, DuplicateSQLKey=[],
                        isNewDB=False, *args, **kwargs):
        """
        :param tableName: table name
        :param dataList: [{"key":"value"}....]
        :param batchSize: int
        :param ignore: [str]
        :param DuplicateSQL: str
        :param DuplicateSQLKey: [key]
        :param isNewDB: 是否实例化新的DB对象 失败不影响之前的操作
        :return:
        """
        if isNewDB:
            db = DbHandler()
        else:
            db = self.db
        if not dataList:
            return

        data = self.get_columns_by_table(tableName)
        dataColumnDict = {dataDict.get("name"): dataDict.get("type") for dataDict in data}
        sort_mapping = {dataDict.get("name"): dataDict.get("position") for dataDict in data}
        status = None
        while dataList:
            batch = dataList[:batchSize]
            dataList = dataList[batchSize:]
            keys = batch[0].keys()
            newKeys = set(keys) - set(ignore)
            dbKeys = dataColumnDict.keys()
            insertKeys = sorted(list(newKeys & set(dbKeys)), key=lambda x: sort_mapping[x])
            # print("batch>>>",batch)
            if DuplicateSQL or DuplicateSQLKey:
                insertKeys = list(set(insertKeys) - {"id"})

            # 补充未传入创建时间的新增数据
            if "create_time" in insertKeys and "create_time" not in keys:
                insertKeys.remove("create_time")
            else:
                timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                for i in batch:
                    i["create_time"] = timestamp if not i.get("create_time") else i["create_time"]

            if kwargs.get("user_id") is not None:
                if "creator" in dbKeys and "creator" not in insertKeys:
                    insertKeys.append("creator")
                elif "create_id" in dbKeys and "create_id" not in insertKeys:
                    insertKeys.append("create_id")
                if DuplicateSQLKey:
                    if "updater" in dbKeys and "updater" not in insertKeys:
                        insertKeys.append("updater")
                        if "updater" not in DuplicateSQLKey:
                            DuplicateSQLKey.append("updater")
                    elif "update_id" in dbKeys and "update_id" not in insertKeys:
                        insertKeys.append("update_id")
                        if "update_id" not in DuplicateSQLKey:
                            DuplicateSQLKey.append("update_id")

                    if "update_time" in dbKeys and "update_time" not in insertKeys:
                        insertKeys.append("update_time")
                        if "update_time" not in DuplicateSQLKey:
                            DuplicateSQLKey.append("update_time")
                else:
                    if kwargs.get("isUpdate"):
                        if "updater" in dbKeys and "updater" not in insertKeys:
                            insertKeys.append("updater")
                            if "creator" not in insertKeys:
                                insertKeys.remove("creator")
                        elif "update_id" in dbKeys and "update_id" not in insertKeys:
                            insertKeys.append("update_id")
                            if "create_id" in insertKeys:
                                insertKeys.remove("create_id")

                        if "update_time" in dbKeys and "update_time" not in insertKeys:
                            insertKeys.append("update_time")
                            if "update_time" not in DuplicateSQLKey:
                                DuplicateSQLKey.append("update_time")

            columns = ", ".join([f'`{field}`' for field in insertKeys])
            values = []
            for item in batch:
                insertV = []
                for key in insertKeys:
                    if key in ignore:
                        item.pop(key, None)

                    if key in ["creator", "create_id", "updater", "update_id", "update_time"]:
                        if item.get(key):
                            if key == "update_time":
                                insertV.append(f"TIMESTAMP {item.get(key)}")
                            else:
                                insertV.append(item.get(key))
                        else:
                            if key == "update_time":
                                insertV.append(f"TIMESTAMP {get_now_date_str()}")
                            else:
                                insertV.append(f"{kwargs.get('user_id', '0')}")
                        continue

                    if "char" in dataColumnDict.get(key, ""):
                        # print("item>>>",item)
                        if item.get(key) is not None:
                            # value = str(item.get(key, "")).replace("'", "\\\'").replace('"', '\\\"')
                            value = str(item.get(key, "")).replace("'", "''").replace("\\", "\\\\")
                            value = replace_outer_quotes(value)
                            insertV.append(f'{value}')
                        else:
                            insertV.append("")
                    elif ("datetime" in dataColumnDict.get(key, "") or "date" in dataColumnDict.get(key, "")
                          or "time" in dataColumnDict.get(key, "") or "year" in dataColumnDict.get(key, "")):
                        if item.get(key) != "":
                            if len(item.get(key))>10:
                                insertV.append(f"TIMESTAMP {item.get(key)}")
                            else:
                                insertV.append(f"{item.get(key)}")
                        else:
                            insertV.append(f"NULL")
                    else:
                        if item.get(key) != None:
                            if ("double" in dataColumnDict.get(key, "") or "decimal" in dataColumnDict.get(key, "")
                                    or "float" in dataColumnDict.get(key, "")):
                                if isinstance(item.get(key), int) or isinstance(item.get(key), float):
                                    insertV.append(item.get(key))
                                elif isinstance(item.get(key), str) and len(item.get(key)) > 0:
                                    try:
                                        insertV.append(float(item.get(key)))
                                    except Exception as e:
                                        insertV.append(0)
                                else:
                                    insertV.append(0)
                            elif "int" in dataColumnDict.get(key, "") or "bit" in dataColumnDict.get(key, ""):
                                if isinstance(item.get(key), int) or isinstance(item.get(key), float):
                                    insertV.append(int(item.get(key)))
                                elif isinstance(item.get(key), str) and len(item.get(key)) > 0:
                                    insertV.append(int(float(item.get(key))))
                                else:
                                    insertV.append(0)
                            else:
                                insertV.append(f"{item.get(key)}")
                        else:
                            insertV.append(0)
                if len(insertV) == 1:
                    # values.append(str(tuple(insertV)).replace(",", "").replace("\\\'", "'"))
                    str_v = "("
                    for i in insertV:
                        if str(i).startswith("TIMESTAMP"):
                            ret = str(i).replace("TIMESTAMP", "").strip()
                            str_v += f"TIMESTAMP '{str(ret)}'"
                        else:

                            str_v += f"{str(i)}" if str(i) == 'NULL' else f"'{str(i)}'"
                    str_v += ")"
                    values.append(str_v)
                else:
                    # values.append(str(tuple(insertV)).replace("\\\'", "'"))
                    num = len(insertV)
                    str_v = "("
                    for j, i in enumerate(insertV):
                        if j == num - 1:
                            if str(i).startswith("NULLIF"):
                                str_v += f"{str(i)}"
                            else:
                                if str(i).startswith("TIMESTAMP"):
                                    ret = str(i).replace("TIMESTAMP", "").strip()
                                    str_v += f"TIMESTAMP '{str(ret)}'"
                                else:
                                    str_v += f"{str(i)}" if str(i) == 'NULL' else f"'{str(i)}'"
                        else:
                            if str(i).startswith("NULLIF"):
                                str_v += f"{str(i)}" + ","
                            else:
                                if str(i).startswith("TIMESTAMP"):
                                    ret = str(i).replace("TIMESTAMP", "").strip()
                                    str_v += f"TIMESTAMP '{str(ret)}'" + ","
                                else:
                                    str_v += f"{str(i)}," if str(i) == 'NULL' else f"'{str(i)}',"
                    str_v += ")"
                    values.append(str_v)
            # values = [re.sub(r'"(NULLIF\(.*?\))"', r'\1', value) for value in values]
            values = [fix_nullif_quotes(value) for value in values]
            sql = f'''INSERT INTO `{tableName}` ({columns}) VALUES {','.join(values)}'''
            if DuplicateSQL:
                sql += DuplicateSQL
            elif DuplicateSQLKey:
                dsql = ''' ON DUPLICATE KEY UPDATE '''
                for key in DuplicateSQLKey:
                    if "`" in key:
                        dsql += f" {key} = VALUES({key}),"
                    else:
                        dsql += f" `{key}` = VALUES(`{key}`),"
                sql += dsql.strip(",")
            if kwargs.get("printSql"):
                print("batchInsertToDB sql:", sql)
            status = db.execute(sql, logflg=kwargs.get("logflg", True))
            if status in dbErrorStatus:
                raise SfException(str(status), [tableName])
            else:
                if status < 0:
                    raise SfException(str(status), [])
        return status

    def batchUpdateToDB(self, tableName, dataList, batch_size=10000, requiredFields=[], ignore=[], isNewDB=False,
                        isUpdateTiem=True,
                        **kwargs):
        """
        :param tableName: table name
        :param dataList: [{"id":1,"key":"value"}....]
        :param batch_size: int
        :return:
        """
        if isNewDB:
            db = DbHandler()
        else:
            db = self.db
        if not dataList:
            return
        data_dict = {}
        ids = []
        status = None

        data = self.get_columns_by_table(tableName)
        dataColumnDict = {dataDict.get("name"): dataDict.get("type") for dataDict in data}
        print("dataColumnDict>>>>", dataColumnDict)
        dbKeys = dataColumnDict.keys()
        while dataList:
            batch = copy.deepcopy(dataList[:batch_size])
            dataList = dataList[batch_size:]
            idk = "id"
            keys = batch[0].keys()
            newKeys = set(keys) - set(ignore)
            insertKeys = list(newKeys & set(dbKeys))
            for d in batch:
                if kwargs.get("UNIQUE_KEY"):
                    ids.append(d[kwargs.get("UNIQUE_KEY")])
                    idk = kwargs.get("UNIQUE_KEY")
                else:
                    ids.append(d.get("id"))
                if kwargs.get("user_id"):
                    if "update_id" in dbKeys:
                        d.update({"update_id": kwargs.get("user_id")})
                    elif "updater" in dbKeys:
                        d.update({"updater": kwargs.get("user_id")})
                if isUpdateTiem:
                    if "update_time" in dbKeys:
                        d.update({"update_time": get_now_date_str()})
                print("d>>>", d)
                for k, v in d.items():
                    if k in ["id", "_tag_"]:
                        continue
                    if k in ignore:
                        continue
                    if k == kwargs.get("UNIQUE_KEY"):
                        continue
                    if k not in insertKeys:
                        if k in ["update_id", "updater", "update_time"]:
                            ...
                        else:
                            continue
                    if requiredFields:
                        if k in requiredFields:
                            if data_dict.get(k):
                                data_dict.get(k).append({idk: d.get(idk), "value": v})
                            else:
                                data_dict.update({k: [{idk: d.get(idk), "value": v}]})
                    else:
                        if data_dict.get(k):
                            data_dict.get(k).append({idk: d.get(idk), "value": v})
                        else:
                            data_dict.update({k: [{idk: d.get(idk), "value": v}]})
            sql = ""
            for k, v in data_dict.items():
                if sql:
                    sql += ","
                sql += f" `{k}` = CASE "
                for d in v:
                    if "date" in dataColumnDict.get(k, "") or "time" in dataColumnDict.get(k, "") or "year" in dataColumnDict.get(k, ""):
                        if d.get("value"):
                            if "time" in dataColumnDict.get(k, ""):
                                nv = f""" TIMESTAMP {repr(d.get("value"))}"""
                            elif "date" in dataColumnDict.get(k, ""):
                                nv = f""" DATE {repr(d.get("value"))}"""
                            else:
                                nv = f""" {repr(d.get("value"))}"""
                        else:
                            nv = re.sub(r"'(NULLIF\(.*?\))'", r'\1', f"""NULLIF({repr(d.get("value"))}, '') """)
                        sql += f''' WHEN `{idk}` = '{d.get(idk)}' THEN {nv} '''
                    elif "char" in dataColumnDict.get(k, ""):
                        # nv = str(d.get("value")).replace("'", "\\\'").replace('"', '\\\"')
                        nv = str(d.get("value")).replace("'", "''")
                        sql += f''' WHEN `{idk}` = '{d.get(idk)}' THEN '{nv}' '''
                    elif "int" in dataColumnDict.get(k, "") or "bit" in dataColumnDict.get(k, "") or "number" in dataColumnDict.get(k, ""):
                        if not d.get("value"):
                            d["value"] = 0
                        sql += f''' WHEN `{idk}` = '{d.get(idk)}' THEN {int(d.get("value"))} '''
                    elif "float" in dataColumnDict.get(k, ""):
                        if not d.get("value"):
                            d["value"] = 0
                        sql += f''' WHEN `{idk}` = '{d.get(idk)}' THEN {float(d.get("value"))} '''
                    else:
                        sql += f''' WHEN `{idk}` = '{d.get(idk)}' THEN '{d.get("value")}' '''
                sql += f" ELSE `{k}` END "
            idsstr = str(tuple(ids))
            if len(ids) == 1:
                idsstr = idsstr.replace(",", "")
            updateSql = f"""UPDATE `{tableName}` SET {sql} WHERE `{idk}` IN {idsstr};"""
            if kwargs.get("printSql"):
                print("batchUpdateToDB sql:", updateSql)
            status = db.execute(updateSql, logflg=kwargs.get("logflg", True))
            if status in dbErrorStatus:
                raise SfException(str(status), [tableName])
            else:
                if status < 0:
                    raise SfException(str(status), [])

        return status

    def batchDeleteToDB(self, tableName, ids: List[str], **kwargs):
        ids = ",".join(ids)
        query = f"DELETE FROM `{tableName}` WHERE `id` in ({ids});"
        status = self.db.execute(query, logflg=kwargs.get("logflg", True))
        if status in dbErrorStatus:
            raise SfException(str(status), [tableName])
        else:
            if status < 0:
                raise SfException(str(status), [])
        return status

    def get_table_field(self, table):

        column_details = self.get_columns_by_table(table)
        data = []
        for column_detail in column_details:
            column_name = column_detail.get('name', '')
            column_comment = column_detail.get('comment', '')
            column_type = column_detail.get('type', '')
            column_length = column_detail.get('length', '')
            data.append({"column_name": column_name, "column_comment": column_comment, "column_type": column_type,
                         "column_length": column_length})
        return data

    def get_query(self, body, field_list):
        query = ""
        for filed in field_list:
            value = body.get(filed)
            if value and type(value) == str:
                query += f" AND {filed} = '{value}'"
            elif value and (type(value) == int or type(value) == float):
                query += f" AND {filed} = {value}"
            elif value and type(value) == list:
                if type(value[0]) == int:
                    query += f""" AND {filed} in ('{",".join([str(i) for i in value])}')"""
                else:
                    query += f""" AND {filed} in ('{"','".join(value)}')"""
        return query

    def query_sql(self, sql, isNewDB=False, use_cache=False, **kwargs):
        """
        :param sql: sql语句
        :param isNewDB: 使用新db对象
        :param use_cache: 是否使用缓存
        """
        ret = []
        sql_r = SQLReplacer()
        sql = sql_r.convert_sql(sql, target_db=self.get_db_type())

        if kwargs.get("printSql"):
            print("query_sql:", sql)
        if use_cache and not isNewDB:
            cache_ret, cache_key = self._get_cache(sql)
            if cache_ret is None:
                status = self.db.query(sql, ret)
                if status in dbErrorStatus:
                    current_method_name = inspect.currentframe().f_code.co_name
                    traceback_str = traceback.format_exc()
                    print(f"程序执行异常：{current_method_name}-{traceback_str}")
                    raise SfException(str(status), [])
                else:
                    if status < 0:
                        raise SfException(str(status), [])
                if use_cache:
                    # 写入缓存
                    self._redis_cache.redis_execute(f"SET {cache_key} {json.dumps(ret)} EX 1")
                    self._local_cache[cache_key] = ret
            else:
                ret = cache_ret
        else:
            if isNewDB:
                db = DbHandler()
                status = db.query(sql, ret)
                if status in dbErrorStatus:
                    current_method_name = inspect.currentframe().f_code.co_name
                    traceback_str = traceback.format_exc()
                    print(f"程序执行异常：{current_method_name}-{traceback_str}")
                    raise SfException(str(status), [])

            else:
                status = self.db.query(sql, ret)
                if status in dbErrorStatus:
                    current_method_name = inspect.currentframe().f_code.co_name
                    traceback_str = traceback.format_exc()
                    print(f"程序执行异常：{current_method_name}-{traceback_str}")
                    raise SfException(str(status), [])
                else:
                    if status < 0:
                        current_method_name = inspect.currentframe().f_code.co_name
                        traceback_str = traceback.format_exc()
                        print(f"程序执行异常：{current_method_name}-{traceback_str}")
                        raise SfException(str(status), [])

        return ret

    def exec_sql(self, sql, isNewDB=False, **kwargs):
        sql_r = SQLReplacer()
        sql = sql_r.convert_sql(sql, target_db=self.get_db_type())
        if kwargs.get("printSql"):
            print("query_sql:", sql)
        if isNewDB:
            db = DbHandler()
            status = db.execute(sql, logflg=kwargs.get("logflg", True))
            if status in dbErrorStatus:
                raise SfException(str(status), [])

        else:
            status = self.db.execute(sql, logflg=kwargs.get("logflg", True))
            if status in dbErrorStatus:
                raise SfException(str(status), [])
            else:
                if status < 0:
                    raise SfException(str(status), [])
        return status

    def query_concurrently(self, sql_list):
        result = self.db.query_concurrently(sql_list)
        return result

    def updateDBObj(self):
        self.db = DbHandler()

    def dbCommit(self):
        self.db.commit()

    def dbRollback(self):
        self.db.rollback()

    def createby(self, new_table, basic_table):
        status = self.db.createby(new_table, basic_table)
        if status in dbErrorStatus:
            raise SfException(str(status), [])
        else:
            if status < 0:
                raise SfException(str(status), [])
        return status

    @staticmethod
    def get_order_limit(payload):
        sort_info = payload.get("sort_info", [])
        page = payload.get("page", {})
        if sort_info:
            order_by = [f"{order.get('name')} {order.get('sort') == 'asc'}" for order in sort_info]
            order_by_sql = ",".join(order_by)
        else:
            order_by_sql = ""
        if page and page.get('page_size', 0):
            limit_sql = f"LIMIT {(page.get('page_num') - 1) * page.get('page_size')},{page.get('page_size')}"
        else:
            limit_sql = ""
        return order_by_sql, limit_sql

    def _get_cache(self, sql, force_refresh=False):
        """
        :param sql: SQL语句
        :param force_refresh: 是否强制刷新缓存
        """
        cache_key = _generate_cache_key(sql)

        # 先检查内存缓存(请求级别)
        if not force_refresh and cache_key in self._local_cache:
            return self._local_cache[cache_key], cache_key

        # 检查Redis缓存
        if not force_refresh:
            exist = self._redis_cache.redis_execute(f"EXISTS {cache_key}")
            if int(exist):
                cached = self._redis_cache.redis_execute(f"GET {cache_key}")
                if cached is not None:
                    result = json.loads(cached)
                    self._local_cache[cache_key] = result  # 填充内存缓存
                    return result, cache_key

        return None, cache_key

    def get_db_type(self):
        return self.schema.get_db_type()

    # def formatModelColumn(self, column):
    #     if "varchar" in column.type.lower():
    #         field_type = "varchar"
    #     else:
    #         field_type = column.type.lower()
    #     field_length = column.length or column.precision
    #     field_scale = column.scale if column.precision else 0
    #     field_comment = column.comment
    #     field_name = column.name
    #     position = column.position
    #     scale = column.scale
    #     nullable = column.nullable
    #     default_value = column.default_value
    #     return {
    #         "name": field_name,
    #         "comment": field_comment,
    #         "type": field_type,
    #         "length": field_length,
    #         "decimal": field_scale,
    #         "scale": scale,
    #         "nullable": nullable,
    #         "default_value": default_value,
    #         "position": position
    #     }
    #
    # def formatModelIndex(self, indexObj):
    #     return {"name":indexObj.name,"type":indexObj.type,"columns":indexObj.columns}
    #
    # def formatModelTable(self, tableObj):
    #     tableData = {"name": tableObj.name, "comment": tableObj.comment}
    #     print("tableData",tableData)
    #     columns = []
    #     indexes = []
    #     for column in tableObj.columns.values():
    #         columns.append(self.formatModelColumn(column))
    #
    #     for column in tableObj.indexes:
    #         columns.append(self.formatModelIndex(column))
    #     tableData["columns"] = columns
    #     tableData["indexes"] = indexes
    #     return indexes

    def is_table_exist(self, table_name):
        """
        校验表是否存在
        :param table_name: 表名
        """
        return self.schema.is_table_exist(table_name)

    def is_tables_exist(self, table_names: []):
        """
        校验表是否存在
        :param table_name: 表名 ["",""]
        """
        return self.schema.is_tables_exist(table_names)

    def get_columns_by_table(self, table_name):
        """
        通过表名获取字段信息
        :param table_name: 表名
        """
        data_list = self.schema.get_columns_by_table(table_name)
        return data_list

    def get_tables_like(self, prefix, mid="", suffix=""):
        """
        模糊匹配表名会返回表里字段的信息
        :param prefix:
        :param mid:
        :param suffix:
        """
        return self.schema.get_tables_like(prefix, mid, suffix)

    def get_tables_like_only_name(self, prefix, mid="", suffix=""):
        """
        模糊匹配表名只会返回表名
        :param prefix:
        :param mid:
        :param suffix:
        """
        return self.schema.get_tables_like_only_name(prefix, mid, suffix)

    def get_tables_like_only_name_desc(self, prefix, mid="", suffix=""):
        """
        模糊查询表名与描述信息，参数为空则忽略
        :param prefix:
        :param mid:
        :param suffix:
        """
        return self.schema.get_tables_like_only_name_desc(prefix, mid, suffix)

    def get_table_by_name(self, table_name):
        """
        根据表名查询表完整信息
        :param table_name:
        """
        data = self.schema.get_table_by_name(table_name)
        return data

    def get_indexes_by_table(self, table_name):
        """
        根据表名查询表索引信息
        :param table_name:
        """
        return self.schema.get_indexes_by_table(table_name)

    def get_column_by_name(self, table_name, col_name):
        """
        //根据表名查询表列信息
        :param table_name:
        :param col_name:
        """
        return self.schema.get_column_by_name(table_name, col_name)

    def get_table_keys(self, table_name):
        """
        //根据表名查询表唯一key
        :param table_name:
        """
        return self.schema.get_table_keys(table_name)

    def get_table_primary(self, table_name):
        """
         //根据表名查询表主建
        :param table_name:
        """
        return self.schema.get_table_primary(table_name)

    def get_table_by_name_multi(self, table_names):
        """
        //根据表名查询表完整信息（多表名）
        :param table_names: [ table_name1, table_name2, ...]
        """
        return self.schema.get_table_by_name_multi(table_names)

    def get_indexes_by_table_multi(self, table_names):
        """
        //根据表名查询表索引信息（多表名）
        :param table_names: [ table_name1, table_name2, ...]
        """
        return self.schema.get_indexes_by_table_multi(table_names)

    def get_columns_by_table_multi(self, table_names):
        """
        //根据表名查询表列信息（多表名）
        :param table_names: [ table_name1, table_name2, ...]
        """
        return self.schema.get_columns_by_table_multi(table_names)

    def get_table_keys_multi(self, table_names):
        """
        //根据表名查询表唯一key（多表名）
        :param table_names: [ table_name1, table_name2, ...]
        """
        return self.schema.get_table_keys_multi(table_names)

    def get_table_primary_multi(self, table_names):
        """
        //根据表名查询表主建（多表名）
        :param table_names: [ table_name1, table_name2, ...]
        """
        return self.schema.get_table_primary_multi(table_names)

    def get_column_by_colname_multi(self, col_names):
        """
        //根据列名查询列信息（多列名）
        :param col_names: [ col_name1, col_name2, ...]
        """
        return self.schema.get_column_by_colname_multi(col_names)
