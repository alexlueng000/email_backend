# app/main.py
import os
import re

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

from app import email_utils, models, database, schemas, tasks, send_email_tasks
from app.utils import get_dingtalk_access_token, create_yida_form_instance, simplify_to_traditional
from app.log_config import setup_logger

from dotenv import load_dotenv
load_dotenv()

logger = setup_logger(__name__)

T = TypeVar('T', bound=BaseModel)

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
async def receive_bidding_register(req: schemas.BiddingRegisterRequest, db: Session = Depends(database.get_db)):

    logger.info("1委托投标登记|请求参数：%s", req.model_dump())

    req = strip_request_fields(req)

    # 新增一条项目信息
    project_info = models.ProjectInfo(
        project_name=req.project_name,
        contract_number="",
        tender_number=req.bidding_code, # 招标编号
        project_type="",
        # project_stage="A",
        p_serial_number=req.p_serial_number,
        l_serial_number=req.l_serial_number,
        f_serial_number=req.f_serial_number,
        purchaser=req.purchase_department,
        company_b_name=req.b_company_name,
        company_c_name="",
        company_d_name="",
        a1=False,
        a2=False,
        b3=False,
        b4=False,
        b5=False, 
        b6=False,
        c7=False,
        c8=False,
        c9=False,
        c10=False
    )
    db.add(project_info)
    db.commit()
    db.refresh(project_info) # 获取插入后的主键ID

    # 获取插入后的主键ID, 用于后续邮件记录
    project_id = project_info.id

    # 查询三家D公司
    d_companies = (
        db.query(models.CompanyInfo)
        .filter(models.CompanyInfo.company_type == "D")
        .limit(3)
        .all()
    )

    if not d_companies:
        logger.error("没有找到 D 公司")
        return {"message": "没有找到 D 公司"}

    # B公司邮箱
    company_name = req.b_company_name.replace('\xa0', '').strip()
    logger.info("B公司名称：%s", company_name)
    b_company_info = (
        db.query(models.CompanyInfo)
        .filter(models.CompanyInfo.company_name == company_name)
        .first()
    )

    if not b_company_info: 
        logger.error("没有找到 B 公司")
        return {"message": "没有找到 B 公司"}

    logger.info("B公司信息：%s", b_company_info)
        
    # 三家D公司给B公司发送A1邮件
    for company in d_companies:

        # print("D公司信息：", company.company_name, company.short_name)
        
        # 领先
        if company.short_name == "LF":
            subject = f" { simplify_to_traditional(req.project_name) }- 投標委託 | { simplify_to_traditional(req.purchase_department) }| { req.l_serial_number }"
            template_name = "A1_LF.html"

            smtp_config = {
                "host": company.smtp_host,
                "port": company.smtp_port,
                "username": company.smtp_username,
                "password": company.smtp_password,
                "from": company.smtp_from
            }

            #TODO 每个公司有不同的发送模板 
            content = email_utils.render_invitation_template_content(
                buyer_name=simplify_to_traditional(req.purchase_department),
                project_name=simplify_to_traditional(req.project_name),
                template_name=template_name
            )
            # print("LF公司邮件内容：", content)  
            success, error = email_utils.send_email_in_main(to=b_company_info.email, subject=subject, body=content, smtp_config=smtp_config)
            
            # 保存发送记录
            record = models.EmailRecord(
                to=b_company_info.email,
                subject=subject,
                body=content,
                status="success" if success else "failed",
                error_message=error if not success else None,
                project_id=project_id,
                task_id="",
                stage="A1",
                actual_sending_time=datetime.now()
            )
            db.add(record)
            db.commit()
            db.refresh(record)

            # 更新宜搭表单实例
            create_yida_form_instance(
                app_type=os.getenv("APP_TYPE"),
                system_token=os.getenv("SYSTEM_TOKEN"),
                access_token=get_dingtalk_access_token(),
                user_id=os.getenv("USER_ID"),
                form_uuid=os.getenv("FORM_UUID"),
                form_data={
                    "textField_m8sdofy7": b_company_info.company_name,
                    "textField_m8sdofy8": company.company_name,
                    "textfield_G00FCbMy": subject,
                    "editorField_m8sdofy9": content,
                    "radioField_manpa6yh": "发送成功",
                    "textField_mbyq9ksm": now_str,
                    "textField_mbyq9ksn": now_str,
                    "textField_mc8eps0i": "A1"
                }
            )
            
        # 弗劳恩
        elif company.short_name == "FR":
            subject = f"【誠邀合作】{ simplify_to_traditional(req.project_name) }投標{req.f_serial_number}"
            print("FR公司邮件主题：", subject)
            template_name = "A1_FR.html"
            smtp_config = {
                "host": company.smtp_host,
                "port": company.smtp_port,
                "username": company.smtp_username,
                "password": company.smtp_password,
                "from": company.smtp_from
            }
            
            content = email_utils.render_invitation_template_content(
                buyer_name=simplify_to_traditional(req.purchase_department),
                project_name=simplify_to_traditional(req.project_name),
                template_name=template_name
            )
            # print("FR公司邮件内容：", content)
            try:
                success, error = email_utils.send_email_in_main(to=b_company_info.email, subject=subject, body=content, smtp_config=smtp_config)

            except Exception as e:
                print("FR公司邮件发送失败：", e)
            
            # 保存发送记录
            record = models.EmailRecord(
                to=b_company_info.email,
                subject=subject,
                body=content,
                status="success" if success else "failed",
                error_message=error if not success else None,
                project_id=project_id,
                stage="A1",
                actual_sending_time=datetime.now()
            )
            db.add(record)
            db.commit()
            db.refresh(record)

            create_yida_form_instance(
                access_token=get_dingtalk_access_token(),
                user_id=os.getenv("USER_ID"),
                app_type=os.getenv("APP_TYPE"),
                system_token=os.getenv("SYSTEM_TOKEN"),
                form_uuid=os.getenv("FORM_UUID"),
                form_data={
                    "textField_m8sdofy7": b_company_info.company_name,
                    "textField_m8sdofy8": company.company_name,
                    "textfield_G00FCbMy": subject,
                    "editorField_m8sdofy9": content,
                    "radioField_manpa6yh": "发送成功",
                    "textField_mbyq9ksm": now_str,
                    "textField_mbyq9ksn": now_str,
                    "textField_mc8eps0i": "A1"
                }
            )
        # 普利赛斯
        else:
            subject = f"{ simplify_to_traditional(req.project_name) }投標委託{ req.p_serial_number }"
            print("普利赛斯公司邮件主题：", subject)
            template_name = "A1_PRESICE.html"
            smtp_config = {
                "host": company.smtp_host,
                "port": company.smtp_port,
                "username": company.smtp_username,
                "password": company.smtp_password,
                "from": company.smtp_from
            }
            
            content = email_utils.render_invitation_template_content(
                buyer_name=simplify_to_traditional(req.purchase_department),
                project_name=simplify_to_traditional(req.project_name),
                template_name=template_name
            )
            # print("普利赛斯公司邮件内容：", content)
            success, error = email_utils.send_email_in_main(to=b_company_info.email, subject=subject, body=content, smtp_config=smtp_config)
            # 保存发送记录
            record = models.EmailRecord(
                to=b_company_info.email,
                subject=subject,
                # body=content,
                status="success" if success else "failed",
                error_message=error if not success else None,
                task_id="",
                project_id=project_id,
                stage="A1",
                actual_sending_time=datetime.now()
            )
            db.add(record)
            db.commit()
            db.refresh(record)

            create_yida_form_instance(
                access_token=get_dingtalk_access_token(),
                user_id=os.getenv("USER_ID"),
                app_type=os.getenv("APP_TYPE"),
                system_token=os.getenv("SYSTEM_TOKEN"),
                form_uuid=os.getenv("FORM_UUID"),
                form_data={
                    "textField_m8sdofy7": b_company_info.company_name,
                    "textField_m8sdofy8": company.company_name,
                    "textfield_G00FCbMy": subject,
                    "editorField_m8sdofy9": content,
                    "radioField_manpa6yh": "发送成功",
                    "textField_mbyq9ksm": now_str,
                    "textField_mbyq9ksn": now_str,
                    "textField_mc8eps0i": "A1"
                }
            )

    # 定时任务：5-60分钟后由 B公司 给3家公司回复邮件
    # random_numbers = utils.generate_random_number()

    b_smtp = {
        "host": b_company_info.smtp_host,
        "port": b_company_info.smtp_port,
        "username": b_company_info.smtp_username,
        "password": b_company_info.smtp_password,
        "from": b_company_info.smtp_from
    }

    template_name = "A2_" + b_company_info.short_name + ".html"

    # # JZ 测试，后替换为实际的B公司
    for company in d_companies:

        A2_subject = ''

        if company.short_name == "FR":

            A2_subject = email_utils.render_email_subject(
                stage="A2", 
                company_short_name=b_company_info.short_name, 
                project_name=req.project_name,
                serial_number=req.f_serial_number
            )
            
        elif company.short_name == "LF":
            A2_subject = email_utils.render_email_subject(
                stage="A2", 
                company_short_name=b_company_info.short_name, 
                project_name=req.project_name,
                serial_number=req.l_serial_number
            )
            
        
        else:
            A2_subject = email_utils.render_email_subject(
                stage="A2", 
                company_short_name=b_company_info.short_name, 
                project_name=req.project_name,
                serial_number=req.p_serial_number
            )
            
        content = email_utils.render_invitation_template_content(
            # purchase_department=req.purchase_department,
            project_name=req.project_name,
            template_name=template_name,
            full_name=company.contact_person,
        )
            
        result = tasks.send_reply_email.apply_async(
            args=[company.email, A2_subject, content, b_smtp, 1 * 60, "A2", project_id],
            countdown=1 * 60  
        )
        # 保存发送记录
        record = models.EmailRecord(
            to=company.email,
            subject=A2_subject,
            body=content,
            status="pending", 
            task_id=result.task_id,
            project_id=project_id,
            stage="A2"
        )
        db.add(record)
        db.commit()
        db.refresh(record)
    # 更新project_info表中的a1状态为1
    project_info.a1 = True
    db.commit()

    return {"message": "邮件已成功发送给 B 公司"}



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
                elif project.project_type == 'BD':
                    send_email_tasks.schedule_bid_conversation_BD(
                        b_company=b_company,
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
    logger.info("D公司名称：%s", c_company_name)
    logger.info("C公司名称：%s", d_company_name)
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
            b_company=b_company,
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
    if req.three_fourth is None  or (isinstance(req.third_party_fee, str) and req.third_party_fee.strip() == ""):
        return {"message": "三方/四方货款（RMB）没有值，不发送邮件"}

    # 如果 service_fee 为空或是空字符串
    if req.import_service_fee is None or (isinstance(req.import_service_fee, str) and req.import_service_fee.strip() == ""):
        return {"message": "C进口服务费（RMB）没有值，不发送邮件"}

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
        logger.info("没有找到C公司，不发送邮件，合同号为: %s", req.contract_number)
        # 说明是BD项目
        pass 


    # 回传的下载链接
    BC_download_url = ""
    BD_download_url = ""

    if project_information.project_type == 'BCD':
        result = send_email_tasks.schedule_settlement_BCD(
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
