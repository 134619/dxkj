"""
@File    : utils.py
@Author  : tianzhao.li@dxdstech.com
@Date    : 2026/01/07
@explain : 工具
"""


def clean_quotes_in_dict(input_dict):
    """
    处理字典中的字符串值，移除字符串中的引号
    :param input_dict: 输入字典
    :return: 处理后的新字典
    """
    result = {}
    for key, value in input_dict.items():
        if isinstance(value, str):
            # 移除单引号和双引号
            cleaned_value = value.replace("'", "\\\'").replace('"', '\\\"')
            result[key] = cleaned_value
        else:
            result[key] = value
    return result


def get_db_id_by_cond(db, table_name, cond=''):
    """
    根据条件查询id
    :param db: 数据库连接, DBHelper实例
    :param table_name: string 表名
    :param cond: string 查询条件,格式: AND 字段名=值 AND 字段名=值 ...
    :return id: int 记录ID, None: 没有查询到
    """
    if not cond:
        return None
    sql = f'SELECT `id` FROM `{table_name}` WHERE 1 = 1 {cond};'
    print(f"[{table_name}] {sql}")
    data = db.query_sql(sql)
    if len(data) > 0:
        return int(str(data[0].get('id')))
    else:
        return None


def get_db_record_by_cond(db, table_name, cond='', cols='*'):
    """
    根据条件查询记录
    :param db: 数据库连接, DBHelper实例
    :param table_name: string 表名
    :param cond: string 查询条件,格式: AND 字段名=值 AND 字段名=值 ...
    :param cols: string 字段名列表, 如: 'id,name,age'
    :return id: int 记录ID, None: 没有查询到
    """
    if not cond:
        return None
    if cols == "*":
        sql = f'SELECT * FROM `{table_name}` WHERE 1 =1  {cond};'
    else:
        sql = f'SELECT `{cols}` FROM `{table_name}` WHERE 1 =1  {cond};'
    print(f"[{table_name}] {sql}")
    data = db.query_sql(sql)
    if len(data) > 0:
        return data[0]
    else:
        return None


def query_db_records_by_cond(db, table_name, cond='', cols='*'):
    """
    根据条件查询记录列表
    :param db: 数据库连接, DBHelper实例
    :param table_name: string 表名
    :param cond: string 查询条件,格式: AND 字段名=值 AND 字段名=值 ...
    :param cols: string 字段名列表, 如: 'id,name,age'
    :return id: int 记录ID, None: 没有查询到
    """
    if not cond:
        return None
    if cols == "*":
        sql = f'SELECT * FROM `{table_name}` WHERE 1 =1  {cond};'
    else:
        if '`' in cols:
            sql = f'SELECT {cols} FROM `{table_name}` WHERE 1 =1  {cond};'
        else:
            sql = f'SELECT `{cols}` FROM `{table_name}` WHERE 1 =1  {cond};'
    print(f"[{table_name}] {sql}")
    data = db.query_sql(sql)
    return data


def insert_db_records(db, table_name, cols, data_list):
    """
    创建数据库记录, 批量插入
    :param db: 数据库连接, DBHelper实例
    :param table_name: string 表名
    :param cols: tuple 字段名列表, 如: ('id', 'name', 'age')
    :param data_list: list[dict] 数据列表, 未传字段默认值为'', 如: [{'id': 1, 'name': '张三', 'age': 20}, {'id': 2, 'name': '李四', 'age': 25}]
    """
    rows = []
    for data in data_list:
        data = clean_quotes_in_dict(data)
        colums = tuple([f"""'{data.get(col) if data.get(col) is not None else ""}'""" for col in cols])
        rows.append(f"({','.join(colums)})")
    sql = f"INSERT INTO `{table_name}` (`{'`,`'.join(cols)}`) VALUES {','.join(rows)};"
    print(f"[{table_name}] {sql}")
    status = db.exec_sql(sql)
    if status == -1:
        raise Exception(f'创建{table_name}记录失败')
    return len(data_list)


def update_db_record_by_id(db, table_name, id, cols, data):
    """
    根据id更新数据库记录
    :param db: 数据库连接, DBHelper实例
    :param table_name: string 表名
    :param id: int 记录ID
    :param cols: tuple 字段名列表, 如: ('name', 'age')
    :param data: dict 字段值字典, 如: {'name': '张三', 'age': 20}, 未传字段不更新
    """
    if not id:
        raise Exception('id不能为空')

    data = clean_quotes_in_dict(data)
    # 只更data中存在的字段, 传空字符串''也会更新
    update_cols = [f"`{col}`='{str(data.get(col))}'" for col in cols if data.get(col) is not None]
    sql = f"UPDATE `{table_name}` SET {','.join(update_cols)} WHERE `id` = {id};"
    print(f"[{table_name}] {sql}")
    status = db.exec_sql(sql)
    if status == -1:
        raise Exception(f'更新{table_name}记录{id}失败')


def update_db_record_by_cond(db, table_name, cond, cols, data):
    """
    根据id更新数据库记录
    :param db: 数据库连接, DBHelper实例
    :param table_name: string 表名
    :param cond: string 查询条件,格式: AND 字段名=值 AND 字段名=值 ...
    :param cols: tuple 字段名列表, 如: ('name', 'age')
    :param data: dict 字段值字典, 如: {'name': '张三', 'age': 20}, 未传字段不更新
    """
    if not cond:
        raise Exception('cond不能为空')

    data = clean_quotes_in_dict(data)
    # 只更data中存在的字段, 传空字符串''也会更新
    update_cols = [f"`{col}`='{str(data.get(col))}'" for col in cols if data.get(col) is not None]
    sql = f"UPDATE `{table_name}` SET {','.join(update_cols)}  WHERE 1  =1  {cond};"
    print(f"[{table_name}] {sql}")
    status = db.exec_sql(sql)
    if status == 0:
        print(f'更新{table_name}记录{cond}成功, 但没有匹配到任何记录')
        return status
    if status == -1:
        raise Exception(f'更新{table_name}记录{cond}失败')


def upsert_db_record_on_duplicate_key(db, table_name, insert_cols, update_cols, data):
    """
    根据唯一索引更新或插入数据库记录
    :param db: 数据库连接, DBHelper实例
    :param table_name: string 表名
    :param insert_cols: tuple 插入字段名列表, 如: ('id', 'name', 'age')
    :param update_cols: tuple 更新字段名列表, 如: ('name', 'age')
    :param data: dict 字段值字典, 如: {'id': 1, 'name': '张三', 'age': 20}, 未传字段不更新
    """
    data = clean_quotes_in_dict(data)
    insert_cols = [col for col in insert_cols if data.get(col)]
    insert_values = [f"'{data.get(col)}'" for col in insert_cols if data.get(col)]
    insert_sql = f"INSERT INTO `{table_name}` (`{'`,`'.join(insert_cols)}`) VALUES ({','.join(insert_values)})"
    update_cols = [f"`{col}`='{str(data.get(col))}'" for col in update_cols]
    update_sql = f"UPDATE {','.join(update_cols)}"
    sql = insert_sql + " ON DUPLICATE KEY " + update_sql
    print(f"[{table_name}] {sql}")
    status = db.exec_sql(sql)
    if status == -1:
        raise Exception(f'更新{table_name}记录{id}失败')


# 接口业务处理错误类
class ItfBizError(Exception):
    """
    接口业务处理错误类
    - 可以对外返回具体错误信息
    """

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)

    def __repr__(self):
        return f"ItfBizError({self.value})"

    def to_json(self):
        return {'error': str(self)}  # 错误信息


def call_sap_rest_api(json_body, req_header=None, req_method='POST', timeout=(10, 30)):
    """
    调用SAP REST API
    :param json_body: dict 请求参数
    :param req_header: dict 请求头
    :param req_method: string 请求方法, POST/GET/PUT/DELETE
    :param timeout: tuple 超时时间
    :return: dict 响应内容 JSON格式
    """
    import requests
    from requests.auth import HTTPBasicAuth
    sap_api_url = "http://10.96.14.43:50000/RESTAdapter/po/ext001"
    sap_basic_auth = {
        "username": "btc-po",
        "password": "Sap.20230603"
    }
    headers = {
        "Content-Type": "application/json"
    }

    # basic auth认证
    auth = HTTPBasicAuth(sap_basic_auth.get('username'), sap_basic_auth.get('password'))
    # 补齐header
    if req_header:
        headers.update(req_header)

    try:
        response = requests.post(sap_api_url, headers=headers, json=json_body, auth=auth, timeout=timeout)
        if response.status_code != 200:
            raise Exception(f"调用SAP接口失败, 响应状态码{response.status_code}")
        resp_data = response.json()
        print(
            f"调用SAP接口成功, 请求地址:{sap_api_url}, 请求头:{headers}, 请求方法:{req_method}, 请求参数:{json_body}, 响应内容:{response}")
        return resp_data
    except Exception as e:
        print(
            f"调用SAP接口异常, 请求地址:{sap_api_url}, 请求头:{headers}, 请求方法:{req_method}, 请求参数:{json_body}, 异常信息:{e}")
        raise Exception(f"调用SAP接口失败:{str(e)}")
