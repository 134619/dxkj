"""
@File    : ZZEXT_MonthlyTaskExecute.py
@Author  : tianzhao.li@dxdstech.com
@Date    : 2026/01/07
@explain : 月结二开
"""
import json

from ActualCostPushSAP import (
    ActualCompPushFunc,
    ActualCostPushFunc,
    CalcData,
    PaGsDetailsPushFunc,
)
from AuxiliaryMaterialAllocation import AuxAmtAlloc, AuxAmtAllocReset
from AuxiliaryMaterialSummary import ExecCostingShareDetail
from BusinessDataSynchronizationExecute import BdscExecuteMonthly, BdscResetting
from CostSettlementWIPCalculation import (
    CostSettlementWIPCalculation,
    CostSettlementWIPCalculationReset,
)
from DbHelper import DbHelper
from InventoryBalancePosting import (
    execPostingCore,
    resetPostingCore,
    setupMonthlyClearAdhust,
)
from InventoryDiffAllocation import clearDataDiff
from InventoryVoucherProcessCostAccounting import MonthlyHandle
from libenhance import SysHandler
from MaterialCostLevelCalculation import mat_cost_level_monthly
from MonthBillStepPushSAP import (
    ActualCostPostPushSAPCore,
    AuxMatCostPostPushSAPCore,
    CompletionCostPostAccountingCore,
    CompletionCostPostPushSAPCore,
    CompletionCostPostReversalCore,
    CostAllocPostPushSAPCore,
    NotOutsourceInventorPushSAPCore,
    NotOutsourceInventoryAccountingCore,
    NotOutsourceInventoryReversalCore,
    OtherCostAllocPushSAPCore,
    OutsourceActualPostAccountingCore,
    OutsourceActualPostReversalCore,
    OutsourceInventoryPushSAPCore,
    PeriodProcessPostPushSAPCore,
    cost_center_check_task,
    delete_cost_center_result,
)
from RdCostDiffCalc import rd_cost_diff_calc, re_push_rd, reset_rd
from TransferDiffPostAccounting import executeData, reversalData
from WorkshopInventoryAIMonthly import (
    WorkshopInventoryAIresetting,
    workshopInventoryAIMonthly,
)
from ZZITF_ManufactureDetails_Sync import get_manufacture_details_data

#--------------------#
from ZZITF_ManufactureOverhead_Sync import get_manufacture_overhead_data

#--------------------#

# 界面加载时禁用重置按钮
special_tasks2 = [528]

# 界面加载时禁用重置和执行按钮
disable_tasks = [520]

# 界面加载时 出错状态下允许继续执行的月结步骤
allow_edit_in_error = [116, 528, 501, 502, 503, 504, 505, 506, 507, 508, 509, 510, 511, 513, 536, 539, 547]

# 重新推送
re_push = [529]


# -----------------执行仅跳转----------------
special_tasks = [
    531, 532, 535
]
# -----------------------------------------


# -----------------重置仅改状态--------------
reset_complation_task = [
    531, 532, 542
]
# -----------------------------------------


# -----------------执行拦截-----------------
exec_task = [
    116, 512, 516, 527, 599,
    517, 529, 126, 536, 537,
    539, 547, 590, 591, 592,
    593, 594, 595, 596, 533,
    519, 501, 502, 503, 504,
    505, 506, 507, 508, 509,
    510, 511, 513, 124, 548
]
# -----------------------------------------


# -----------------重置拦截-----------------
reset_task = [
    116, 502, 503, 504, 505,
    506, 507, 508, 509, 511,
    512, 513, 516, 517, 518,
    527, 598, 599, 597, 212,
    533, 519, 535, 536, 537,
    539, 540, 590, 591, 592,
    593, 594, 595, 596, 501,
    124, 548, 547
]
# -----------------------------------------


def update_monthly_procedure(task_code, task_id, step, status):
    db = DbHelper()
    db.exec_sql(f''' update `t_co_monthly_procedure` set `status`={status} where `task_code`='{task_code}' and `task_id`={task_id} and `step`='{step}'; ''')
    db.dbCommit()


# 配置执行逻辑
def exec_func(db, task_id, body, user_id, task_code):
    year = body.get("year") or ''
    period = body.get("period") or ''
    cost_area = body.get("cost_area") or ''
    cost_version = body.get("cost_version") or ''
    price_mark = body.get("price_mark") or ''
    step = body.get("step") or ''
    task_info = body.get("task_info")

    msg = ""
    commit_status = False
    status = 4
    res = {"code": 200, "msg": "", "data": []}

    update_monthly_procedure(task_code, task_id, step, 2)

    try:

        for info in task_info:
            company_code = info.get("company_code", "")
            plant_code = info.get("plant_code", [])

            if task_id == 547:
                # 辅材按金额分摊
                res = AuxAmtAlloc(plant_code, year, period, company_code, cost_version)

            elif task_id == 126:
                # 成本等级计算
                res = mat_cost_level_monthly(year, period, plant_code, company_code, user_id)
            
            elif task_id == 116:
                # 制造费用抽取
                res = get_manufacture_overhead_data(year, period, company_code)
                if res['code'] == 200:
                    res = get_manufacture_details_data(year, period, company_code)

            for plant_code in info.get("plant_code", []):

                print(f"执行: {company_code}公司 {plant_code}工厂")

                if task_id == 512:
                    # 辅材费用转生产成本计算
                    res = ExecCostingShareDetail(year, period, plant_code)

                elif task_id == 516:
                    # 车间辅材盘盈盘亏计算
                    res = workshopInventoryAIMonthly(year, period, plant_code, user_id)

                elif task_id == 527:
                    # 制造费用成本中心检查
                    res = cost_center_check_task(year, period, plant_code, user_id,price_mark)

                elif task_id == 529:
                    # 制造费用拆分
                    res = rd_cost_diff_calc(cost_area, year, period, company_code, cost_version, price_mark)

                elif task_id == 536:
                    # 实际作业成本过账
                    sh = SysHandler()
                    params = {
                        "year": year,
                        "period": period,
                        "plant_code": plant_code,
                        "task_code": task_code,
                        "task_id": task_id,
                        "step": step,
                        "user_id": user_id,
                    }
                    json_params = json.dumps(params)
                    sh.async_call('ActualCostPostOpt', 'async_actual_cost_post', json_params)
                    res = {"code": 300, "msg": "", "data": []}

                elif task_id == 537:
                    # 转投扣料差异调整过账
                    res = executeData(plant_code, year, period)

                elif task_id == 124:
                    # 业务数据同步执行、费用同步转投分摊
                    res = BdscExecuteMonthly(year, period, company_code, user_id)
                    commit_status = True

                elif task_id == 533:
                    # 盘点凭证工序级成本核算数据同步
                    res = MonthlyHandle(year, period, plant_code, user_id)

                elif task_id == 519:
                    # 实际成本组件计算推送
                    CalcData(plant_code, year, period, user_id)
                    ActualCostPushFunc(plant_code, year, period, user_id)
                    ActualCompPushFunc(plant_code, year, period, user_id)
                    PaGsDetailsPushFunc(plant_code, year, period, user_id)

                elif task_id == 501:
                    res = OutsourceActualPostAccountingCore(year, period, plant_code)

                elif task_id == 502:
                    res = execPostingCore(year, period, plant_code)

                elif task_id == 503:
                    res = OutsourceInventoryPushSAPCore(user_id, task_id,year, period, plant_code)

                elif task_id == 504:
                    res = OtherCostAllocPushSAPCore(user_id, task_id,year, period, plant_code)

                elif task_id == 505:
                    res = CostAllocPostPushSAPCore(user_id, task_id,year, period, plant_code)

                elif task_id == 506:
                    res = ActualCostPostPushSAPCore(user_id, task_id,year, period, plant_code)

                elif task_id == 507:
                    res = PeriodProcessPostPushSAPCore(user_id, task_id,year, period, plant_code)

                elif task_id == 508:
                    res = CompletionCostPostAccountingCore(year,period,plant_code)

                elif task_id == 509:
                    res = CompletionCostPostPushSAPCore(user_id, task_id,year, period, plant_code)

                elif task_id == 510:
                    res = NotOutsourceInventoryAccountingCore(year,period,plant_code)

                elif task_id == 511:
                    res = NotOutsourceInventorPushSAPCore(user_id, task_id, year, period, plant_code)

                elif task_id == 513:
                    res = AuxMatCostPostPushSAPCore(user_id, task_id, year, period, plant_code)

                elif task_id == 548:
                    res = CostSettlementWIPCalculation(user_id, task_id, year, period, plant_code)

                elif task_id in [517, 599, 590, 591, 592, 593, 594, 595, 596]:
                    # 无程序
                    pass

                print(f"结果: {res}")

                if commit_status == False:
                    if res["code"] == 200:
                        status = 4
                    elif res["code"] == 300:
                        status = 2
                    else:
                        status = 3
                        print(f"公司{company_code}  工厂{plant_code}失败")
                        msg += f"公司{company_code} 工厂{plant_code}: {res.get('msg', '')} \n"

        if commit_status == False:
            update_monthly_procedure(task_code, task_id, step, status)

    except Exception as e:
        update_monthly_procedure(task_code, task_id, step, 3)
        raise e

    return commit_status, msg


# 配置重置逻辑
def reset_func(db, task_id, body, user_id, task_code, step):
    year = body.get("year") or ''
    period = body.get("period") or ''
    cost_area = body.get("cost_area") or ''
    cost_version = body.get("cost_version") or ''
    price_mark = body.get("price_mark") or ''
    task_info = body.get("task_info", [])
    updateStepStatus = True

    commit_status = False
    status = 1
    res = {"code": 200, "msg": "", "data": []}

    try:

        for info in task_info:
            company_code = info.get("company_code", "")
            plant_code = info.get("plant_code", [])

            if task_id == 547:
                # 辅材按金额分摊
                res = AuxAmtAllocReset(plant_code, year, period, company_code, cost_version)

            for plant_code in info.get("plant_code", []):

                print(f"重置: {company_code}公司 {plant_code}工厂")

                if task_id == 516:
                    # 车间辅材盘盈盘亏计算
                    res = WorkshopInventoryAIresetting(year, period, plant_code, user_id)

                elif task_id == 527:
                    # 制造费用成本中心检查
                    res = delete_cost_center_result(year, period, plant_code, user_id)

                elif task_id == 212:
                    # 清除 盘点差异分摊数据
                    res = clearDataDiff(plant_code, year, period)
                    commit_status = True

                elif task_id == 512:
                    # 线边仓辅材在制重置清除数据
                    setupMonthlyClearAdhust()
                    res = {"code": 200, "msg": "", "data": []}

                elif task_id == 529:
                    # 制造费用拆分
                    res = reset_rd(cost_area, year, period, company_code, cost_version, price_mark)

                elif task_id == 519:

                    db.exec_sql(f"""update `t_sap_pa_gs_details` set `posting_status` = 'N' where `year` = '{year}' and `period` = '{period}' and `plant_code` = '{plant_code}' """)
                    db.exec_sql(f"""update `t_sap_mmd_comp_cost` set `posting_status` = 'N' where `year` = '{year}' and `period` = '{period}' and `plant_code` = '{plant_code}' """)

                elif task_id == 536:
                    # 实际作业成本过账重置
                    sh = SysHandler()
                    params = {
                        "year": year,
                        "period": period,
                        "plant_code": plant_code,
                        "task_code": task_code,
                        "task_id": task_id,
                        "step": step,
                        "user_id": user_id,
                    }
                    json_params = json.dumps(params)
                    sh.async_call('ActualCostPostOpt', 'async_actual_cost_reverse', json_params)
                    res = {"code": 300, "msg": "", "data": []}
                    updateStepStatus = False

                elif task_id == 537:
                    # 转投扣料差异调整过账重置
                    updateStepStatus = False
                    res = reversalData(plant_code, year, period)

                elif task_id == 124:
                    # 业务数据同步执行、费用同步转投分摊重置
                    updateStepStatus = False
                    res = BdscResetting(year, period, company_code, user_id)
                    commit_status = True

                elif task_id == 501:
                    res = OutsourceActualPostReversalCore(year, period, plant_code)

                elif task_id == 502:
                    res = resetPostingCore(year, period, plant_code)

                elif task_id == 508:
                    res = CompletionCostPostReversalCore(year,period,plant_code)

                elif task_id == 510:
                    res = NotOutsourceInventoryReversalCore(year,period,plant_code)

                elif task_id == 548:
                    res =  CostSettlementWIPCalculationReset(user_id, task_id, year, period, plant_code)


                print(f"结果: {res}")

                if commit_status == False:
                    if res["code"] == 200:
                        status = 1
                    elif res["code"] == 300:
                        status = 2
                    else:
                        status = 3
                        print(f"公司{company_code}  工厂{plant_code}失败")

        if commit_status == False:
            update_monthly_procedure(task_code, task_id, step, status)

    except Exception as e:
        update_monthly_procedure(task_code, task_id, step, 3)
        raise e

    return commit_status


def re_push_func(db, task_id, body, user_id, task_code, step):
    year = body.get("year") or ''
    period = body.get("period") or ''
    cost_area = body.get("cost_area") or ''
    company_code = body.get("company_code") or ''
    cost_version = body.get("cost_version") or ''
    price_mark = body.get("price_mark") or ''

    if task_id == 529:
        # 制造费用拆分
        re_push_rd(cost_area, year, period, company_code, cost_version, price_mark)
