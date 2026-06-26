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




# false	1515	3	2026-03-31	7d3aadc62ab618fc83454e6a2346b177	1	2			SFDA01		2026	03						SFP-D0001	P000000002	SFR-D0006		0	0.376	BOT	ML	0.00	0.376	0.000000000000000	0			"存在错误,请检查 计划订单P000000002为已创建状态不可更新为已发料"				43	2026-04-27 14:30:47	43	2026-04-27 14:30:47	
# false	1516	3	2026-03-31	0d7e6bd21317fea695540441b91cb3f2	1	2			SFDA01		2026	03						SFP-D0001	P000000002	SFR-D0010		0	1.224	EA	EA	0.00	1.224	0.000000000000000	0			"存在错误,请检查 计划订单P000000002为已创建状态不可更新为已发料"				43	2026-04-27 14:30:49	43	2026-04-27 14:30:49	
# false	1517	3	2026-03-31	a42ab35032983232730bc125742e492c	1	2			SFDA01		2026	03						SFP-D0001	P000000002	SFR-D0007		0	0.301	EA	EA	0.00	0.301	0.000000000000000	0			"存在错误,请检查 计划订单P000000002为已创建状态不可更新为已发料"				43	2026-04-27 14:30:50	43	2026-04-27 14:30:50	
# false	1518	3	2026-03-31	3cc46479584e49052853f4192dfb70f0	1	2			SFDA01		2026	03						SFP-D0001	P000000002	SFR-D0015		0	1.224	EA	EA	0.00	1.224	0.000000000000000	0			"存在错误,请检查 计划订单P000000002为已创建状态不可更新为已发料"				43	2026-04-27 14:30:50	43	2026-04-27 14:30:50	
# false	1519	3	2026-03-31	b388f65ea8084677fab756c20a8132d3	1	2			SFDA01		2026	03						SFP-D0001	P000000002	SFR-D0010		0	0.301	EA	EA	0.00	0.301	0.000000000000000	0			"存在错误,请检查 计划订单P000000002为已创建状态不可更新为已发料"				43	2026-04-27 14:30:52	43	2026-04-27 14:30:52	
# false	1520	3	2026-03-31	529118539c6e57567957695d19de7b46	1	2			SFDA01		2026	03						SFP-D0001	P000000002	SFR-D0015		0	0.376	EA	EA	0.00	0.376	0.000000000000000	0			"存在错误,请检查 计划订单P000000002为已创建状态不可更新为已发料"				43	2026-04-27 14:30:52	43	2026-04-27 14:30:52	
# false	1521	3	2026-03-31	c3fcb31549a39682f9ec91144240d9e2	1	2			SFDA01		2026	03						SFP-D0001	P000000002	SFR-D0004		0	0.376	BOT	ML	0.00	0.376	0.000000000000000	0			"存在错误,请检查 计划订单P000000002为已创建状态不可更新为已发料"				43	2026-04-27 14:30:53	43	2026-04-27 14:30:53	
# false	1522	3	2026-03-31	b82e7d0d1cd8e9b24e37b27679dc1338	1	2			SFDA01		2026	03						SFP-D0001	P000000002	SFR-D0015		0	0.301	EA	EA	0.00	0.301	0.000000000000000	0			"存在错误,请检查 计划订单P000000002为已创建状态不可更新为已发料"				43	2026-04-27 14:30:56	43	2026-04-27 14:30:56	
# false	1523	3	2026-03-31	626d5c4a8c2d6a8133218df8748f5c4b	1	2			SFDA01		2026	03						SFP-D0001	P000000002	SFR-D0006		0	0.301	BOT	ML	0.00	0.301	0.000000000000000	0			"存在错误,请检查 计划订单P000000002为已创建状态不可更新为已发料"				43	2026-04-27 14:30:57	43	2026-04-27 14:30:57	
# false	1524	3	2026-03-31	769024e55169945c4ad521089a3c8026	1	2			SFDA01		2026	03						SFP-D0005	P000000008	SFR-D0004		0	0.025	BOT	ML	0.00	0.025	0.000000000000000	0			"存在错误,请检查 计划订单P000000008为已创建状态不可更新为已发料"				43	2026-04-27 14:30:57	43	2026-04-27 14:30:57	
# false	1525	3	2026-03-31	d90230dc59788d67ccd588901761251f	1	2			SFDA01		2026	03						SFP-D0005	P000000008	SFR-D0004		0	0.050	BOT	ML	0.00	0.050	0.000000000000000	0			"存在错误,请检查 计划订单P000000008为已创建状态不可更新为已发料"				43	2026-04-27 14:31:00	43	2026-04-27 14:31:00	
# false	1526	3	2026-03-31	dd5c63492a0a583d406ec36d21f578ad	1	2			SFDA01		2026	03						SFP-D0001	P000000002	SFR-D0015		0	0.250	EA	EA	0.00	0.250	0.000000000000000	0			"存在错误,请检查 计划订单P000000002为已创建状态不可更新为已发料"				43	2026-04-27 14:31:02	43	2026-04-27 14:31:02	



