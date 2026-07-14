"""
手工录入财务封装方法增强
预留方法名及参数禁止调整！！！
before_check
before_save
after_save
"""


# BAPI校验前调用,可用于设置默认值或其他校验-
def before_check(user_id, head, item):
    code = 200
    msg = ''
    error_list = []

    # 此处增加逻辑
    # ...


    # 固定返回参数,禁止调整
    return code, msg, error_list, head, item


# BAPI校验完调用,可用于调整参数或其他校验
def before_save(user_id, fi_head, fi_item):
    code = 200
    msg = ''
    error_list = []

    # 此处增加逻辑
    # ...

    # 固定返回参数,禁止调整
    return code, msg, error_list,   fi_head, fi_item


# BAPI保存完之后再调用,可用于触发其他二开保存或第三方接口
# 注意：该增强不影响正常业务逻辑的存储,如需在该方法中报错需要慎重考虑业务流程！！！
def after_save(user_id, fi_head, fi_item):
    code = 200
    msg = ''
    error_list = []

    # 此处增加逻辑
    # ...

    # 固定返回参数,禁止调整
    return code, msg, error_list, fi_head, fi_item
