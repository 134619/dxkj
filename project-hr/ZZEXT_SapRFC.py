#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
@File    : ZZEXT_SapRFC.py
@Author  : dongliang.wang@dxdstech.com
@Date    : 2026/06/02 11:35
@explain : SAP RFC 调用模块封装
"""
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


# 使用示例
if __name__ == "__main__":
    # 测试RFC调用
    sap = SAPRFC()
    DATA = {
        "BUKRS": "RACQ",
        "DATA_IN": [
            {
                "EMSDOC": "",
                "DOC_TYPE": "SA",
                "COMP_CODE": "RACC",
                "FISC_YEAR": "2026",
                "DOC_DATE": "20260617",
                "PSTNG_DATE": "20260617",
                "FIS_PERIOD": "06",
                "HEADER_TXT": "202606移动平均月结汇总",
                "REF_DOC_NO": "MI2026061MIRO001",
                "CURRENCY": "CNY",
                "TYPE": "EA",
            }
        ]
    }

    result = sap.call('ZRFC_MH_DOC_POST_MASS',DATA)
    print(result)


    sap.close()