# app/main.py
import os
import re
import random 

from pathlib import Path
from datetime import datetime
from decimal import Decimal
from typing import TypeVar
from pydantic import BaseModel


from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi import Request
from sqlalchemy.orm import Session
from sqlalchemy import text

from app import email_utils, models, database, schemas, tasks, send_email_tasks, tasks
from app.utils import simplify_to_traditional
from app.log_config import setup_logger

from app.stage_utils.stage_A1_A2_utils import normalize_company_name, make_a1_task_from_d_to_b, make_a2_task_for_target_d, get_company_by_name, update_D_company_by_alias, get_company_by_short

from dotenv import load_dotenv
load_dotenv()

logger = setup_logger(__name__)

T = TypeVar('T', bound=BaseModel)

max_sending_time = 60

def strip_request_fields(req: T) -> T:
    """
    去除所有字符串字段两端的空白字符，包括普通空格、不间断空格（\xa0）和全角空格（\u3000）。
    适用于任意继承自 BaseModel 的 Pydantic 请求对象。
    """
    for field, value in req.__dict__.items():
        if isinstance(value, str):
            cleaned = re.sub(r'^[\s\u00A0\u3000]+|[\s\u00A0\u3000]+$', '', value)
            setattr(req, field, cleaned)
    return req

app = FastAPI()

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"❌ 未处理异常: {repr(exc)}")
    return JSONResponse(
        status_code=500,
        content={"message": "服务器内部错误"}
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    print("❌ 请求验证失败：")
    for error in exc.errors():
        print(error)
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()}
    )

models.Base.metadata.create_all(bind=database.engine)

# 将 ~/settlements 目录挂载为 /download 路由
settlement_dir = Path.home() / "settlements"
app.mount("/download", StaticFiles(directory=settlement_dir), name="download")

now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

@app.get("/ping-db")
def ping_db():
    try:
        with database.engine.connect() as conn:
            conn.execute(text("SELECT 1")) 
        return {"status": "success", "message": "pong ✅ 数据库连接成功"}
    except Exception as e:
        return {"status": "error", "message": "❌ 数据库连接失败", "detail": str(e)}

'''
1. 委托投标
第一封邮件：三家D公司给B公司发送邮件    
接收流水号：['PR202504001', '25LDF_001', 'HK-FRONT-25#001']
'''

"""
这个接口需要处理的事情：
1. 向project_info表中插入一条项目信息
2. 查询3家D公司的信息
3. 查询B公司的信息（如果没有呢？）
4. 3家D公司给B公司发送邮件
5. 保存发送记录，处理异常情况并更新project_info中的A1字段
6. 生成一个5-60之间的随机数x，在x分钟后由B向3个D公司发送A2邮件
7. 保存发送记录，处理异常情况并更新project_info中的A2字段
8. 将发送记录回传给宜搭 TODO

接收参数：
@serials_numbers: 流水号列表，例如 ['PR202504001', '25LDF_001', 'HK-FRONT-25#001'] （必有）
@purchase_department: 采购单位 （必有）
@b_company_name: B公司名称 （必有）
@project_name: 项目名称 （必有）
@bidding_code: 招标编号 （可能为空）
"""

@app.post("/receive_bidding_register")
async def receive_bidding_register(
    req: schemas.BiddingRegisterRequest,
    db: Session = Depends(database.get_db)
):
    logger.info("1委托投标登记|请求参数：%s", req.model_dump())

    # 1) 随机延迟
    LF_A1_delay = random.randint(0, 1)
    FR_A1_delay = random.randint(0, 1)
    PR_A1_delay = random.randint(0, 1)

    # 清洗请求
    req = strip_request_fields(req)

    # 2) 确定本项目邮箱别名 (A/B/C)
    current_plss = email_utils.get_last_plss_email()
    logger.info("(2) 确定本项目邮箱别名 (A/B/C): %s", current_plss)

    # 3) 新增项目
    project_info = models.ProjectInfo(
        project_name=req.project_name,
        contract_number="",
        tender_number=req.bidding_code,
        project_type="",
        p_serial_number=req.p_serial_number,
        l_serial_number=req.l_serial_number,
        f_serial_number=req.f_serial_number,
        purchaser=req.purchase_department,
        company_b_name=req.b_company_name,
        company_c_name="",
        company_d_name="",
        a1=False, a2=False, b3=False, b4=False, b5=False, b6=False,
        c7=False, c8=False, c9=False, c10=False,
        current_plss_email=current_plss
    )
    db.add(project_info)
    db.commit()
    db.refresh(project_info)

    # 4) 通知邮件
    tasks.send_notification_email_task(
        "委托投标登记", "已有项目委托投标登记，邮件正在发出，预估半天后发送完毕。", "739266989@qq.com"
    )
    tasks.send_notification_email_task(
        "委托投标登记", "已有项目委托投标登记，邮件正在发出，预估半天后发送完毕。", "494762262@qq.com"
    )

    # 5) 查询公司信息
    b_name = normalize_company_name(req.b_company_name)
    logger.info("B公司名称：%s", b_name)
    b_company = get_company_by_name(db, b_name)
    if not b_company:
        return {"message": " B公司不在数据库中，无法发送邮件"}

    lf_company = get_company_by_short(db, "LF", "D")
    fr_company = get_company_by_short(db, "FR", "D")

    # 更新D公司邮箱信息 
    pr_company = update_D_company_by_alias(db, current_plss)

    # 6) A2 任务
    delay_FR_A2 = random.randint(0, max_sending_time)
    delay_LF_A2 = random.randint(0, max_sending_time)
    delay_PR_A2 = random.randint(0, max_sending_time)

    task_FR_A2 = make_a2_task_for_target_d(
        b_company=b_company, target_d=fr_company,
        project_name=req.project_name, serial_number=req.f_serial_number,
        delay_minutes=delay_FR_A2,
    )
    task_LF_A2 = make_a2_task_for_target_d(
        b_company=b_company, target_d=lf_company,
        project_name=req.project_name, serial_number=req.l_serial_number,
        delay_minutes=delay_LF_A2,
    )
    task_PR_A2 = make_a2_task_for_target_d(
        b_company=b_company, target_d=pr_company,
        project_name=req.project_name, serial_number=req.p_serial_number,
        delay_minutes=delay_PR_A2,
    )

    # === 根据项目邮箱别名确定 PR 抄送人 ===
    cc_list = []
    if project_info.current_plss_email in ("A", "B"):
        cc_list = [email_utils.MAIL_ACCOUNTS["C"]["email"]]
    logger.info("PR 邮件抄送人: %s", cc_list if cc_list else "无")

    if cc_list:
        task_PR_A2["cc"] = cc_list

    # 7) A1 任务
    # LF
    lf_subject = f"{simplify_to_traditional(req.project_name)}- 投標委託 | {simplify_to_traditional(req.purchase_department)}| {req.l_serial_number}"
    task_LF_A1 = make_a1_task_from_d_to_b(
        d_company=lf_company, b_company=b_company,
        subject=lf_subject, template_name="A1_LF.html",
        buyer_name=simplify_to_traditional(req.purchase_department),
        project_name=simplify_to_traditional(req.project_name),
        a1_delay_minutes=LF_A1_delay, follow_a2_task=task_LF_A2,
    )
    tasks.send_email_with_followup_delay.apply_async(kwargs=task_LF_A1, countdown=LF_A1_delay * 60)

    # FR
    fr_subject = f"【誠邀合作】{simplify_to_traditional(req.project_name)}投標{req.f_serial_number}"
    task_FR_A1 = make_a1_task_from_d_to_b(
        d_company=fr_company, b_company=b_company,
        subject=fr_subject, template_name="A1_FR.html",
        buyer_name=simplify_to_traditional(req.purchase_department),
        project_name=simplify_to_traditional(req.project_name),
        a1_delay_minutes=FR_A1_delay, follow_a2_task=task_FR_A2,
    )
    tasks.send_email_with_followup_delay.apply_async(kwargs=task_FR_A1, countdown=FR_A1_delay * 60)

    # PR
    pr_subject = f"{simplify_to_traditional(req.project_name)}投標委託{req.p_serial_number}"
    task_PR_A1 = make_a1_task_from_d_to_b(
        d_company=pr_company, b_company=b_company,
        subject=pr_subject, template_name="A1_PRESICE.html",
        buyer_name=simplify_to_traditional(req.purchase_department),
        project_name=simplify_to_traditional(req.project_name),
        a1_delay_minutes=PR_A1_delay, follow_a2_task=task_PR_A2,
    )
    if cc_list:
        task_PR_A1["cc"] = cc_list

    tasks.send_email_with_followup_delay.apply_async(kwargs=task_PR_A1, countdown=PR_A1_delay * 60)

    # 8) 日志
    logger.info("A1邮件调度延迟（分钟）: LF=%s, FR=%s, PR=%s", LF_A1_delay, FR_A1_delay, PR_A1_delay)
    logger.info("A2邮件后续延迟（分钟）: LF=%s, FR=%s, PR=%s", delay_LF_A2, delay_FR_A2, delay_PR_A2)

    return {"message": "委托投标登记成功"}

# === 项目中标信息 ===
# 更新项目中标信息的合同号，招标编号
# 接收参数：
#     1. 项目名称
#     2. L流水号，P流水号，F流水号
#     3. 招标编号
#     4. 合同号
@app.post("/project_bidding_winning_information")
async def project_bidding_winning_information(req: schemas.ProjectWinningInfoRequest, db: Session = Depends(database.get_db)):

    logger.info("2项目中标信息|请求参数：%s", req.model_dump())
    
    project_information = db.query(models.ProjectInfo).filter_by(p_serial_number=req.p_serial_number, l_serial_number=req.l_serial_number, f_serial_number=req.f_serial_number).first()
    
    if not project_information:
        logger.error("2项目中标信息|没有找到项目信息，流水号为：%s，%s，%s", req.l_serial_number, req.p_serial_number, req.f_serial_number)
        return {"message": "没有找到项目信息"}

    project_information.contract_number = req.contract_number
    project_information.tender_number = req.bidding_code
    project_information.company_b_name = req.actual_winning_company

    # 3. 尝试将中标金额转换为 Decimal
    try:
        winning_amount = Decimal(req.winning_amount)
    except:
        raise HTTPException(status_code=400, detail="中标金额格式错误，应为数字")
    
    # 5. 创建并插入中标费用详情记录
    fee_detail = models.ProjectFeeDetails(
        project_id=project_information.id,
        winning_time=req.winning_time,
        winning_amount=winning_amount
    )
    db.add(fee_detail)
    db.commit()
    db.refresh(fee_detail)
    
    return {"message": "项目中标信息更新成功"}

"""
合同审批流程通过后，确认是否要发送邮件
发送条件：
    1. 带有L流水号，P流水号，F流水号

这个函数要做的事情：
    1. 判断是否首次调用这个接口（D公司修改后会重新触发）
    2. 判断项目类型：BCD, CCD, BC, BD
    3. 发送邮件
    4. 保存发送记录
    5. 返回信息给宜搭

这个接口接收的参数：
    1. 项目名称
    2. L流水号，P流水号，F流水号
    3. 合同号
    4. 合同流水号
    5. B公司-中标商
    6. C公司 C=列表-合同类型（货款收付控制---不含供应商两方采购合同）中，合同类型=三方/四方合同，且收付控制=付的付款方
    7. D公司 D=列表-合同类型（货款收付控制---不含供应商两方采购合同）中，合同类型=三方/四方合同，且收付控制=付的付款方
    8. 合同类型 contract_type
"""
@app.post("/contract_audit")
async def contract_audit(req: schemas.ContractAuditRequest, db: Session = Depends(database.get_db)):

    logger.info("3合同审核|请求参数: %s", req.model_dump())
    
    # 判断是否包含“三方/四方合同”  且 收付控制（selectField_l7ps2ca5） == "付"
    has_target_contract_type = any(
    contract.selectField_l7ps2ca3 == "三方/四方合同" and contract.selectField_l7ps2ca5 == "付"
    for contract in req.contracts
)

    if not has_target_contract_type:
        logger.info("没有找到三方/四方合同且收付控制=付的合同，不发送邮件，合同号为%s", req.contract_number)
        return {"message": "没有找到三方/四方合同且收付控制=付的合同，不发送邮件"}
    
    # 如果没有L流水号，P流水号，F流水号，说明不是委托投标登记项目，不发送邮件
    if not req.l_serial_number or not req.p_serial_number or not req.f_serial_number:
        logger.info("没有L流水号，P流水号，F流水号，不发送邮件，合同号为%s", req.contract_number)
        return {"message": "没有L流水号，P流水号，F流水号，不发送邮件"}

    
    # 项目信息
    project = db.query(models.ProjectInfo).filter(
        models.ProjectInfo.contract_number == req.contract_number
    ).first()

    if not project:
        logger.info("没有找到项目信息，不发送邮件")
        return {"message": "没有找到项目信息，不发送邮件"}

    # 保存旧的C公司和D公司名称，用于判断CD值是否互换
    old_c_company_name = project.company_c_name
    old_d_company_name = project.company_d_name


    # C公司名字是有三方/四方合同的 selectField_l7ps2ca6 的值
    c_company_name = next(
        (contract.selectField_l7ps2ca6 for contract in req.contracts if contract.selectField_l7ps2ca3 == "三方/四方合同"),
        None
    )
    # 更新project_info表中的C公司信息
    project.company_c_name = c_company_name

    
    # D公司名字是 selectField_l7ps2ca7 的值
    d_company_name = next(
        (contract.selectField_l7ps2ca7 for contract in req.contracts if contract.selectField_l7ps2ca3 == "三方/四方合同"),
        None
    )
    # 更新project_info表中的D公司信息
    project.company_d_name = d_company_name


    # 项目流水号是根据D公司的值来确认的
    d_company = db.query(models.CompanyInfo).filter(
        models.CompanyInfo.company_name == d_company_name
    ).first()

    

    actual_serial_number = ''

    if d_company.short_name == 'FR': 
        actual_serial_number = project.f_serial_number
    elif d_company.short_name == 'LF':
        actual_serial_number = project.l_serial_number
    else:
        actual_serial_number = project.p_serial_number
    project.serial_number = actual_serial_number
    db.add(project)
    db.commit()
    db.refresh(project)


    # 从project_fee_details表中获取中标金额，中标时间
    fee_details = db.query(models.ProjectFeeDetails).filter(
        models.ProjectFeeDetails.project_id == project.id
    ).first()
    winning_amount = fee_details.winning_amount if fee_details else None
    winning_time = fee_details.winning_time if fee_details else None

    logger.info("获取到的中标金额为%s，中标时间为%s", winning_amount, winning_time)


    if project.project_type: # 说明之前已经判断过了项目类型，是D公司信息有修改的情况
        if old_d_company_name != d_company_name:
            # D值有修改时再次触发发邮件（如从领先修改为PLSS），但是为CD值互换的时候不触发
            if old_c_company_name == d_company_name and old_d_company_name == c_company_name:
                logger.info("CD值互换的时候不触发发邮件，CD公司名称分别为%s和%s", old_c_company_name, old_d_company_name)
                return {"message": "CD值互换的时候不触发发邮件"}
            else:
                logger.info("D公司信息有修改，再次触发发邮件，D公司名称分别为%s", d_company_name)
                
 
                # 再次触发发邮件
                b_company = db.query(models.CompanyInfo).filter(
                    models.CompanyInfo.company_name == project.company_b_name
                ).first()
                c_company = db.query(models.CompanyInfo).filter(
                    models.CompanyInfo.company_name == c_company_name
                ).first()
                d_company = db.query(models.CompanyInfo).filter(
                    models.CompanyInfo.company_name == d_company_name
                ).first()

                if project.project_type == 'BCD':
                    send_email_tasks.schedule_bid_conversation_BCD(
                        project_info=project,
                        b_company=b_company,
                        c_company=c_company,
                        d_company=d_company,
                        contract_serial_number=actual_serial_number,
                        project_name=project.project_name,
                        winning_amount=winning_amount,
                        winning_time=winning_time,
                        contract_number=project.contract_number,
                        purchase_department=project.purchaser,
                        tender_number=project.tender_number
                    )
                elif project.project_type == 'CCD':
                    send_email_tasks.schedule_bid_conversation_CCD(
                        project_info=project,
                        b_company=b_company,
                        # c_company=c_company,
                        d_company=d_company,
                        contract_serial_number=actual_serial_number,
                        project_name=project.project_name,
                        winning_amount=winning_amount,
                        winning_time=winning_time,
                        contract_number=project.contract_number,
                        purchase_department=project.purchaser,
                        tender_number=project.tender_number
                    )
                elif project.project_type == 'BD':
                    send_email_tasks.schedule_bid_conversation_BD(
                        b_company=b_company,
                        c_company_name=c_company_name,
                        d_company=d_company,
                        contract_serial_number=actual_serial_number,
                        project_name=project.project_name,
                        winning_amount=winning_amount,
                        winning_time=winning_time,
                        contract_number=project.contract_number,
                        purchase_department=project.purchaser,
                        tender_number=project.tender_number
                    )
                return {
                    "message": f"D值修改，再次触发合同审批阶段邮件发送，合同号为{req.contract_number}",
                    "project_type": project.project_type
                }
        else:
            logger.info("D值没有修改，已经发送过邮件，不再触发发邮件，合同号：%s", project.contract_number)
            return {"message": "D值没有修改，已经发送过邮件，不再触发发邮件"}

    # 项目类型
    project_type = ''           
    # 确定B、C、D公司是否内部公司，B、D公司是内部公司才发送邮件
    logger.info("B公司名称：%s", project.company_b_name)
    # logger.info("B gongsi mingcheng: %s", )
    logger.info("C公司名称：%s", c_company_name)
    logger.info("D公司名称：%s", d_company_name)
    b_company = db.query(models.CompanyInfo).filter(
        models.CompanyInfo.company_name == project.company_b_name, models.CompanyInfo.company_type == 'B'
    ).first()
    # 如果找到了B公司，说明是内部公司
    if not b_company:
        return {"message": "没有找到B公司，不发送邮件"}
    d_company = db.query(models.CompanyInfo).filter(models.CompanyInfo.company_name == d_company_name, models.CompanyInfo.company_type == 'D').first()
    # 如果找到了D公司，说明是内部公司
    if not d_company:
        return {"message": "没有找到D公司，不发送邮件"}

    c_company = db.query(models.CompanyInfo).filter(models.CompanyInfo.company_name == c_company_name, models.CompanyInfo.company_type == 'C').first()
    # 如果找到了C公司，说明是内部公司，如果没有找到，说明是外部公司

    logger.info("@@@@@@@@@@@@@@C公司名称：%s", c_company_name)

    if not c_company:
        project_type = 'BD'
    # 如果B公司和C公司是同一家公司，说明是CCD项目
    elif b_company.company_name == c_company.company_name:
        project_type = 'CCD'
    else:
        project_type = 'BCD'

    # 更新project_info表中的项目类型
    project = db.query(models.ProjectInfo).filter(models.ProjectInfo.contract_number == req.contract_number).first()
    if project:
        project.project_type = project_type
        db.add(project)
        db.commit()
        db.refresh(project)

    # 发送邮件

    # BCD 类型项目
    if project_type == 'BCD':
        logger.info("BCD 类型项目: %s", project.project_name)
        send_email_tasks.schedule_bid_conversation_BCD(
            project_info=project,
            b_company=b_company,
            c_company=c_company,
            d_company=d_company,
            contract_serial_number=project.serial_number,
            project_name=project.project_name,
            winning_amount=winning_amount,
            winning_time=winning_time,
            contract_number=project.contract_number,
            purchase_department=project.purchaser,
            tender_number=project.tender_number
        )
    # CCD 类型项目
    elif project_type == 'CCD':
        logger.info("CCD 类型项目: %s", project.project_name)
        send_email_tasks.schedule_bid_conversation_CCD(
            project_info=project,
            b_company=b_company,
            # c_company=c_company,
            d_company=d_company,
            contract_serial_number=project.serial_number,
            project_name=project.project_name,
            winning_amount=winning_amount,
            winning_time=winning_time,
            contract_number=project.contract_number,
            purchase_department=project.purchaser,
            tender_number=project.tender_number
        )
    # BD 类型项目
    else:
        logger.info("BD 类型项目: %s", project.project_name)
        send_email_tasks.schedule_bid_conversation_BD(
            project_info=project,
            b_company=b_company,
            c_company_name=c_company_name,
            d_company=d_company,
            contract_serial_number=project.serial_number,
            project_name=project.project_name,
            winning_amount=winning_amount,
            winning_time=winning_time,
            contract_number=project.contract_number,
            purchase_department=project.purchaser,
            tender_number=project.tender_number
        )
    
    logger.info("合同审批阶段邮件已成功发送，合同号为%s", project.contract_number)


    #TODO 返回邮件实际发送时间
    return {
        "message": f"合同审批阶段邮件已成功发送，合同号为{project.contract_number}",
        "project_type": project_type
    }
    
    
# 结算流程后发送邮件
# 顺序：
# 1. 发送C-B间结算单
# 2. 发送B-D间结算单
# 3. B-D间结算单确认
# 4. C-D间结算单确认

# @参数
# project_type: str, 项目类型
# project_name: str, 项目名称
# l_serial_number: str, L流水号
# p_serial_number: str, P流水号
# f_serial_number: str, F流水号
# contract_number: str, 合同号
# b_company_name: str, B公司名称
# c_company_name: str, C公司名称
# d_company_name: str, D公司名称
# 还有很多金额

@app.post("/settlement")
def settlement(
    req: schemas.SettlementRequest, db: Session = Depends(database.get_db)):

    logger.info("4结算|请求参数：%s", req.model_dump())


    project_information = db.query(models.ProjectInfo).filter_by(contract_number=req.contract_number).first()
    if not project_information:
        logger.info("没有找到项目信息，不发送邮件，合同号为: %s", req.contract_number)
        return {"message": "没有找到项目信息"}

    # 已经发送过结算单的，不用再发送
    is_sent = project_information.fee_details.is_sent
    if is_sent:
        return {"message": "已经发送过结算单，不用再发送"}

    # 如果 third_party_fee 为空或是空字符串
    if req.three_fourth is None  or (isinstance(req.three_fourth, str) and req.three_fourth.strip() == ""):
        return {"message": "三方/四方货款（RMB）没有值，不发送邮件"}

    # 如果 service_fee 为空或是空字符串
    # if req.import_service_fee is None or (isinstance(req.import_service_fee, str) and req.import_service_fee.strip() == ""):
    #     return {"message": "C进口服务费（RMB）没有值，不发送邮件"}

    def clean_decimal(val):
        return 0 if val == "" else float(val)

    # 中标时间 
    winning_time = project_information.fee_details.winning_time if project_information.fee_details else None

    # 更新 project_fee_details 表
    fee = project_information.fee_details
    fee.three_fourth_amount = clean_decimal(req.three_fourth)
    fee.import_service_fee = clean_decimal(req.import_service_fee)
    fee.third_party_fee = clean_decimal(req.third_party_fee)
    fee.settlement_service_fee = clean_decimal(req.service_fee)
    fee.bidding_service_fee = clean_decimal(req.win_bidding_fee)
    fee.document_purchase_fee = clean_decimal(req.bidding_document_fee)
    fee.tender_service_fee = clean_decimal(req.bidding_service_fee)
    db.add(fee)
    db.commit()
    db.refresh(fee)

    b_company = db.query(models.CompanyInfo).filter_by(company_name=project_information.company_b_name).first()
    if not b_company:
        logger.info("没有找到B公司，不发送邮件，合同号为: %s", req.contract_number)
        return {"message": "没有找到B公司"}

    d_company = db.query(models.CompanyInfo).filter_by(company_name=project_information.company_d_name).first()
    if not d_company:
        logger.info("没有找到D公司，不发送邮件，合同号为: %s", req.contract_number)
        return {"message": "没有找到D公司"}

    c_company = db.query(models.CompanyInfo).filter_by(company_name=project_information.company_c_name).first()
    if not c_company:
        logger.info("没有找到C公司，说明是BD项目，合同号为: %s", req.contract_number)
        # 说明是BD项目
        pass 


    # 回传的下载链接
    BC_download_url = ""
    BD_download_url = ""

    if project_information.project_type == 'BCD':
        result = send_email_tasks.schedule_settlement_BCD(
            project_info=project_information,
            b_company=b_company,
            c_company=c_company,
            d_company=d_company,
            contract_number=project_information.contract_number,
            contract_serial_number=project_information.serial_number,
            project_name=project_information.project_name,
            amount=req.amount,
            three_fourth=req.three_fourth,
            import_service_fee=req.import_service_fee,
            third_party_fee=req.third_party_fee,
            service_fee=req.service_fee,
            win_bidding_fee=req.win_bidding_fee,
            bidding_document_fee=req.bidding_document_fee,
            bidding_service_fee=req.bidding_service_fee,
            winning_time=winning_time,
            purchase_department=project_information.purchaser,
            tender_number=project_information.tender_number
        )
        BC_download_url = result["BC_download_url"]
        BD_download_url = result["BD_download_url"]
    else:
        result = send_email_tasks.schedule_settlement_CCD_BD(
            project_info=project_information,
            b_company=b_company,
            c_company=c_company,
            d_company=d_company,
            contract_number=project_information.contract_number,
            contract_serial_number=project_information.serial_number,
            project_name=project_information.project_name,
            amount=req.amount,
            three_fourth=req.three_fourth,
            import_service_fee=req.import_service_fee,
            third_party_fee=req.third_party_fee,
            service_fee=req.service_fee,
            win_bidding_fee=req.win_bidding_fee,
            bidding_document_fee=req.bidding_document_fee,
            bidding_service_fee=req.bidding_service_fee,
            winning_time=winning_time,
            project_type=project_information.project_type,
            purchase_department=project_information.purchaser,
            tender_number=project_information.tender_number
        )
        # BC_download_url = result["BC_download_url"]
        BD_download_url = result["BD_download_url"]

    logger.info("BC_download_url: %s, BD_download_url: %s", BC_download_url, BD_download_url)

    # 更新project_fee_details表中的is_sent字段
    fee = project_information.fee_details
    fee.is_sent = True
    db.add(fee)
    db.commit()
    db.refresh(fee)

    return {
        "message": f"结算邮件已成功发送，合同号为{req.contract_number}",
        "BC_download_url": BC_download_url,
        "BD_download_url": BD_download_url
    }
