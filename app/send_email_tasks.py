import os
from dotenv import load_dotenv

import random 
from datetime import datetime, timedelta
from contextlib import contextmanager

from app import database, models, email_utils, excel_utils
from app.utils import get_dingtalk_access_token, create_yida_form_instance
from app.tasks import send_reply_email, send_reply_email_with_attachments, upload_file_to_sftp_task, send_email_with_followup
from app.utils import simplify_to_traditional

from celery import chain

import logging

logger = logging.getLogger(__name__)
load_dotenv()
now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

@contextmanager
def get_db_session():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


# BCD 项目类型发送邮件
def schedule_bid_conversation_BCD(
    b_company: models.CompanyInfo, 
    c_company: models.CompanyInfo, 
    d_company: models.CompanyInfo, 
    contract_number: str, # 合同号
    winning_amount: str,  # 中标金额
    winning_time: str,    # 中标时间
    contract_serial_number: str, #流水号
    project_name: str,
    tender_number: str,    # 招标编号
    purchase_department: str # 采购单位
):

    with get_db_session() as db:
        project_info = db.query(models.ProjectInfo).filter(models.ProjectInfo.project_name == project_name).first()
        
    b_smtp = {
        "host": b_company.smtp_host,
        "port": b_company.smtp_port,
        "username": b_company.smtp_username,
        "password": b_company.smtp_password,
        "from": b_company.smtp_from
    }

    c_smtp = {
        "host": c_company.smtp_host,
        "port": c_company.smtp_port,
        "username": c_company.smtp_username,
        "password": c_company.smtp_password,
        "from": c_company.smtp_from
    }

    d_smtp = {
        "host": d_company.smtp_host,
        "port": d_company.smtp_port,
        "username": d_company.smtp_username,
        "password": d_company.smtp_password,
        "from": d_company.smtp_from
    }

    b_email = b_company.email
    c_email = c_company.email
    d_email = d_company.email

    # 获取对应B公司的邮件模板
    b_email_subject_b3 = email_utils.render_email_subject(
        stage="B3", 
        company_short_name=b_company.short_name, 
        project_name=project_name, 
        serial_number=contract_serial_number,
        contract_number=contract_number,
        winning_amount=winning_amount,
        winning_time=winning_time,
        purchase_department=purchase_department,
        tender_number=tender_number
    )
    b_email_content_b3 = email_utils.render_invitation_template_content(
        project_name=project_name,
        serial_number=contract_serial_number,
        first_name=c_company.last_name,
        full_name=c_company.contact_person,
        winning_amount=winning_amount,
        contract_number=contract_number,
        template_name="B3_"+b_company.short_name+".html"
    )
    
    print("B3-B公司邮件主题：", b_email_subject_b3)
    
    # 第一封邮件：B ➝ C（立即）
    # task1 = send_reply_email.apply_async(
    #     args=[c_email, b_email_subject_b3, b_email_content_b3, b_smtp, 0, "B3", project_info.id],
    #     countdown=0  # 立即
    # )

    # 第二封邮件：C ➝ B 回复
    # 随机延迟 5–60 分钟
    c_email_subject_b4 = email_utils.render_email_subject(
        stage="B4", 
        company_short_name=c_company.short_name, 
        project_name=project_name, 
        serial_number=contract_serial_number,
        tender_number=tender_number,
        purchase_department=purchase_department,
        winning_amount=winning_amount,
        winning_time=winning_time,
        contract_number=contract_number
    )
    
    print("B4-C公司邮件主题：", c_email_subject_b4)
    
    c_email_content_b4 = email_utils.render_invitation_template_content(
        buyer_name=c_company.company_name, 
        project_name=project_name, 
        serial_number=contract_serial_number,
        first_name=b_company.last_name,
        winning_amount=winning_amount,
        contract_number=contract_number,
        template_name="B4_"+c_company.short_name+".html")
    
    # delay2 = random.randint(5, 60)
    # delay2 =  1
    # task2 = send_reply_email.apply_async(
    #     args=[b_email, c_email_subject_b4, c_email_content_b4, c_smtp, delay2, "B4", project_info.id],
    #     countdown=delay2 * 60  # 相对第一封
    # )

    # 第三封：B ➝ D（延迟第2封基础上 5–60分钟）
    b_email_subject_b5 = email_utils.render_email_subject(
        stage="B5", 
        company_short_name=b_company.short_name, 
        project_name=project_name, 
        serial_number=contract_serial_number,
        tender_number=contract_number,
        winning_amount=winning_amount,
        winning_time=winning_time
    )
    
    print("B5-B公司邮件主题：", b_email_subject_b5)
    logger.info("C公司名称：%s", c_company.company_name)
    
    b_email_content_b5 = email_utils.render_invitation_template_content(
        buyer_name=b_company.company_name, 
        first_name=d_company.last_name,
        full_name=d_company.contact_person,
        winning_amount=winning_amount,
        contract_number=contract_number,
        serial_number=contract_serial_number,
        project_name=project_name, 
        winning_time=winning_time,
        c_company_name=c_company.company_name,
        template_name="B5_"+b_company.short_name+".html"
    )

    # delay3 = delay2 + random.randint(5, 60)
    # delay3 = delay2 + 1
    # task3 = send_reply_email.apply_async(
    #     args=[d_email, b_email_subject_b5, b_email_content_b5, b_smtp, delay3, "B5", project_info.id],
    #     countdown=delay3 * 60
    # )


    # 第四封：D ➝ B（在第3封后延迟 5–60分钟）
    d_email_subject_b6 = email_utils.render_email_subject(
        stage="B6",
        company_short_name=d_company.short_name,
        project_name=simplify_to_traditional(project_name),
        serial_number=contract_serial_number,
        tender_number=tender_number,
        winning_amount=winning_amount,
        winning_time=winning_time,
        purchase_department=simplify_to_traditional(purchase_department),
        contract_number=contract_number
    )
    
    print("B6-D公司邮件主题：", d_email_subject_b6)
    
    d_email_content_b6 = email_utils.render_invitation_template_content(
        buyer_name=d_company.company_name, 
        first_name=b_company.last_name_traditional,
        full_name=b_company.contact_person, 
        winning_amount=winning_amount, 
        contract_number=contract_number,
        serial_number=contract_serial_number,
        project_name=project_name, 
        winning_time=winning_time,
        template_name="B6_"+d_company.short_name+".html"
    )
    # delay4 = delay3 + random.randint(5, 60)
    # delay4 = delay3 + 1
    # task4 = send_reply_email.apply_async(
    #     args=[b_email, d_email_subject_b6, d_email_content_b6, d_smtp, delay4, "B6", project_info.id],
    #     countdown=delay4 * 60
    # )

    # 最后一封邮件任务（无 follow-up）D - B
    task_b6 = {
        "to_email": b_company.email,
        "subject": d_email_subject_b6,
        "content": d_email_content_b6,
        "smtp_config": d_smtp,
        "stage": "B6",
        "project_id": project_info.id
    }

    # 第三封邮件 B ➝ D（成功后再发 B6）
    task_b5 = {
        "to_email": d_company.email,
        "subject": b_email_subject_b5,
        "content": b_email_content_b5,
        "smtp_config": b_smtp,
        "stage": "B5",
        "project_id": project_info.id,
        "followup_task_args": task_b6
    }

    # 第二封邮件 C ➝ B（成功后再发 B5）
    task_b4 = {
        "to_email": b_company.email,
        "subject": c_email_subject_b4,
        "content": c_email_content_b4,
        "smtp_config": c_smtp,
        "stage": "B4",
        "project_id": project_info.id,
        "followup_task_args": task_b5
    }

    # 第一封邮件 B ➝ C（成功后再发 B4）
    task_b3 = {
        "to_email": c_company.email,
        "subject": b_email_subject_b3,
        "content": b_email_content_b3,
        "smtp_config": b_smtp,
        "stage": "B3",
        "project_id": project_info.id,
        "followup_task_args": task_b4
    }

    send_email_with_followup.apply_async(kwargs=task_b3)

    return {"message": "email sent!"}


# CCD 项目类型发送邮件
# 仅有BD公司之间发送两封邮件
# 特殊B5模板
def schedule_bid_conversation_CCD(
    b_company: models.CompanyInfo, 
    d_company: models.CompanyInfo, 
    contract_serial_number: str,
    winning_amount: str,
    winning_time: str,
    contract_number: str,
    project_name: str,
    purchase_department: str, 
    tender_number: str
):


    b_smtp = {
        "host": b_company.smtp_host,
        "port": b_company.smtp_port,
        "username": b_company.smtp_username,
        "password": b_company.smtp_password,
        "from": b_company.smtp_from
    }


    d_smtp = {
        "host": d_company.smtp_host,
        "port": d_company.smtp_port,
        "username": d_company.smtp_username,
        "password": d_company.smtp_password,
        "from": d_company.smtp_from
    }
    b_email = b_company.email
    d_email = d_company.email

    # C公司的特殊B5邮件模板
    c_email_subject_b5 = email_utils.render_email_subject(
        stage="B5", 
        company_short_name=b_company.short_name, 
        project_name=project_name, 
        contract_serial_number=contract_serial_number,
        tender_number=tender_number,
        purchase_department=purchase_department,
        winning_amount=winning_amount,
        winning_time=winning_time,
        contract_number=contract_number,
        # c_company_name=c_company.company_name
    )
    c_email_content_b5 = email_utils.render_invitation_template_content(
        buyer_name=b_company.company_name,
        project_name=project_name,
        serial_number=contract_serial_number,
        first_name=d_company.last_name,
        winning_amount=winning_amount,
        contract_number=contract_number,
        # c_company_name=c_company.company_name,
        template_name="B5_"+b_company.short_name+"_SPEC.html"
    )
    
    print("CCB B5-C公司邮件主题：", c_email_subject_b5)
    
    # 第一封邮件：B ➝ D（立即）
    task1 = send_reply_email.apply_async(
        args=[d_email, c_email_subject_b5, c_email_content_b5, b_smtp],
        countdown=0  # 立即
    )

    create_yida_form_instance(
        access_token=get_dingtalk_access_token(),
        user_id=os.getenv("USER_ID"),
        app_type=os.getenv("APP_TYPE"),
        system_token=os.getenv("SYSTEM_TOKEN"),
        form_uuid=os.getenv("FORM_UUID"),
        form_data={
            "textField_m8sdofy7": b_company.company_name,
            "textField_m8sdofy8": d_company.company_name,
            "textfield_G00FCbMy": c_email_subject_b5,
            "editorField_m8sdofy9": c_email_content_b5,
            "radioField_manpa6yh": "发送成功",
            "textField_mbyq9ksm": now_str,
            "textField_mbyq9ksn": now_str,
        }
    )

    # 第二封邮件：D ➝ B（随机延迟 5–60 分钟）
    # 随机延迟 5–60 分钟
    d_email_subject_b6 = email_utils.render_email_subject(
        stage="B6",
        company_short_name=d_company.short_name,
        project_name=simplify_to_traditional(project_name),
        serial_number=contract_serial_number,
        contract_number=contract_number,
        winning_amount=winning_amount,
        winning_time=winning_time,
        purchase_department=simplify_to_traditional(purchase_department),
        tender_number=tender_number
    )
    d_email_content_b6 = email_utils.render_invitation_template_content(
        buyer_name=d_company.company_name, 
        first_name=b_company.last_name_traditional,
        winning_amount=winning_amount,
        contract_number=contract_number,
        serial_number=contract_serial_number,
        project_name=project_name, 
        winning_time=winning_time,
        template_name="B6_"+d_company.short_name+".html"
    )
    # delay = random.randint(5, 60)
    delay = 1
    task2 = send_reply_email.apply_async(
        args=[b_email, d_email_subject_b6, d_email_content_b6, d_smtp],
        countdown=delay * 60
    )

    now = datetime.now()
    actual_send_time_str = (now + timedelta(minutes=delay)).strftime("%Y-%m-%d %H:%M")

    return {
        "tasks": [
            {"step": "B ➝ D", "task_id": task1.id, "delay_min": 0},
            {"step": "D ➝ B", "task_id": task2.id, "delay_min": delay},
        ]
    }


# BD 项目类型发送邮件
def schedule_bid_conversation_BD(
    b_company: models.CompanyInfo, 
    d_company: models.CompanyInfo,
    contract_serial_number: str,
    winning_amount: str,
    winning_time: str,
    contract_number: str,
    project_name: str,
    purchase_department: str,
    tender_number: str
):

    b_smtp = {
        "host": b_company.smtp_host,
        "port": b_company.smtp_port,
        "username": b_company.smtp_username,
        "password": b_company.smtp_password,
        "from": b_company.smtp_from
    }

    d_smtp = {
        "host": d_company.smtp_host,
        "port": d_company.smtp_port,
        "username": d_company.smtp_username,
        "password": d_company.smtp_password,
        "from": d_company.smtp_from
    }

    b_email = b_company.email
    d_email = d_company.email

    # 获取对应B公司的邮件模板
    b_email_subject_b5 = email_utils.render_email_subject(
        stage="B5", 
        company_short_name=b_company.short_name, 
        project_name=project_name, 
        serial_number=contract_serial_number,
        contract_number=contract_number,
        winning_amount=winning_amount,
        winning_time=winning_time,
        purchase_department=purchase_department,
        tender_number=tender_number
    )
    b_email_content_b5 = email_utils.render_invitation_template_content(
        buyer_name=b_company.company_name,
        project_name=project_name,
        serial_number=contract_serial_number,
        first_name=d_company.last_name,
        winning_amount=winning_amount,
        contract_number=contract_number,
        template_name="B5_"+b_company.short_name+".html"
    )
    # 第一封邮件：B ➝ D
    task1 = send_reply_email.apply_async(
        args=[d_email, b_email_subject_b5, b_email_content_b5, b_smtp],
        countdown=0  # 立即
    )

    create_yida_form_instance(
        access_token=get_dingtalk_access_token(),
        user_id=os.getenv("USER_ID"),
        app_type=os.getenv("APP_TYPE"),
        system_token=os.getenv("SYSTEM_TOKEN"),
        form_uuid=os.getenv("FORM_UUID"),
        form_data={
            "textField_m8sdofy7": b_company.company_name,
            "textField_m8sdofy8": d_company.company_name,
            "textfield_G00FCbMy": b_email_subject_b5,
            "editorField_m8sdofy9": b_email_content_b5,
            "radioField_manpa6yh": "发送成功",
            "textField_mbyq9ksm": now_str,
            "textField_mbyq9ksn": now_str,
        }
    )
    # 随机延迟 5–60 分钟
    d_email_subject_b6 = email_utils.render_email_subject(
        stage="B6", 
        company_short_name=d_company.short_name, 
        project_name=simplify_to_traditional(project_name), 
        serial_number=contract_serial_number,
        tender_number=tender_number,
        winning_amount=winning_amount,
        winning_time=winning_time,
        purchase_department=simplify_to_traditional(purchase_department),
        contract_number=contract_number
    )
    d_email_content_b6 = email_utils.render_invitation_template_content(
        project_name=project_name,
        serial_number=contract_serial_number,
        first_name=b_company.last_name,
        winning_amount=winning_amount,
        contract_number=contract_number,
        template_name="B6_"+d_company.short_name+".html"
    )
    # delay = random.randint(5, 60)
    delay = 1
    task2 = send_reply_email.apply_async(
        args=[b_email, d_email_subject_b6, d_email_content_b6, d_smtp],
        countdown=delay * 60  # 相对第一封
    )

    return {
        "tasks": [
            {"step": "B ➝ D", "task_id": task1.id, "delay_min": 0},
            {"step": "D ➝ B", "task_id": task2.id, "delay_min": delay},
        ]
    }


# BCD 项目类型发送结算单
# 1. 发送C-B间结算单
# 2. 上一封邮件发出5-60分钟后，发送B-D间结算单
# 3. 上一封邮件发出5-60分钟后，B-D间结算单确认
# 4. 上一封邮件发出5-60分钟后，C-D间结算单确认

'''
    amount: str # 收款金额
    three_fourth: str # 三方/四方货款
    import_service_fee: str # C进口服务费
    third_party_fee: str # 第三方费用
    service_fee: str # 费用结算服务费
    win_bidding_fee: str # 中标服务费
    bidding_document_fee: str # 购买标书费
    bidding_service_fee: str # 投标服务费
'''

def schedule_settlement_BCD(
    b_company: models.CompanyInfo,
    c_company: models.CompanyInfo,
    d_company: models.CompanyInfo,
    contract_number: str, # 合同号
    contract_serial_number: str, # 流水号
    project_name: str,
    amount: float,  # 收款金额（总额）
    three_fourth: float,  # 三方/四方货款
    import_service_fee: float,  # C公司进口服务费
    third_party_fee: float,  # 第三方费用
    service_fee: float,  # 费用结算服务费
    win_bidding_fee: float,  # 中标服务费
    bidding_document_fee: float,  # 标书费
    bidding_service_fee: float,  # 投标服务费
    winning_time: str, # 中标时间
    purchase_department: str, # 购买部门
    tender_number: str # 招标编号
) -> tuple[str, str]:

    b_smtp = {
        "host": b_company.smtp_host,
        "port": b_company.smtp_port,
        "username": b_company.smtp_username,
        "password": b_company.smtp_password,
        "from": b_company.smtp_from
    }

    c_smtp = {
        "host": c_company.smtp_host,
        "port": c_company.smtp_port,
        "username": c_company.smtp_username,
        "password": c_company.smtp_password,
        "from": c_company.smtp_from
    }

    d_smtp = {
        "host": d_company.smtp_host,
        "port": d_company.smtp_port,
        "username": d_company.smtp_username,
        "password": d_company.smtp_password,
        "from": d_company.smtp_from
    }

    b_email = b_company.email
    c_email = c_company.email
    d_email = d_company.email


    # 获取对应C公司的邮件模板
    c_email_subject_c7 = email_utils.render_email_subject(
        stage="C7", 
        company_short_name=c_company.short_name, 
        project_name=project_name, 
        serial_number=contract_serial_number,
        tender_number=tender_number,
        winning_amount=str(amount),
        winning_time=winning_time,
        purchase_department=purchase_department,
        contract_number=contract_number
    )
    logger.info("c_email_subject_c7:%s, %s ", contract_serial_number, c_email_subject_c7)
    c_email_content_c7 = email_utils.render_invitation_template_content(
        buyer_name=b_company.company_name, 
        project_name=project_name, 
        serial_number=contract_serial_number,
        first_name=b_company.last_name,
        winning_amount=str(amount),
        contract_number=contract_number,
        template_name="C7_"+c_company.short_name+".html"
    )

    # 生成C->B结算单
    # 文件名：项目号-流水号-BCD模式-BC结算单.xlsx
    BC_filename = f"{contract_number}_{contract_serial_number}_BCD模式_BC结算单.xlsx"

    BC_download_url = f"http://103.30.78.107:8000/download/{BC_filename}"

    CB_settlement_path = excel_utils.generate_common_settlement_excel(
        filename=BC_filename,  # 可根据项目名称动态命名
        stage="C7",
        project_type="BCD",
        received_amount=amount,
        receivable_items=[
            ("三方/四方货款", three_fourth),
            ('进口服务费', import_service_fee),
            ("第三方费用", third_party_fee),
            ("费用结算服务费", service_fee),
        ],
        head_company_name=b_company.company_name,
        bottom_company_name=c_company.company_name
    )
    logger.info("CB_settlement_path&&&: %s", CB_settlement_path)
    #TODO 1. FTP将生成的文件回传到归档服务器
    
    upload_file_to_sftp_task.delay("~/settlements/"+BC_filename, BC_filename)

    # 第一封邮件：C ➝ B
    task1 = send_reply_email_with_attachments.apply_async(
        args=[b_email, c_email_subject_c7, c_email_content_c7, c_smtp, [CB_settlement_path], 0, "C7", 1], # TODO 换成真实的附件路径
        countdown=0  # 立即
    )

    # 第二封邮件：B ➝ D
    # 随机延迟 5–60 分钟发出B-D间结算单
    b_email_subject_c8 = email_utils.render_email_subject(
        stage="C8", 
        company_short_name=b_company.short_name, 
        project_name=project_name, 
        tender_number=tender_number,
        serial_number=contract_serial_number,
        contract_number=contract_number,
        winning_amount=str(amount),
        winning_time=winning_time,
        purchase_department=purchase_department
    )
    print("b_email_subject_c8: ", b_email_subject_c8)
    b_email_content_c8 = email_utils.render_invitation_template_content(
        buyer_name=d_company.company_name, 
        project_name=project_name, 
        first_name=d_company.last_name,
        full_name=d_company.contact_person,
        serial_number=contract_serial_number,
        contract_number=contract_number,
        winning_amount=str(amount),
        winning_time=winning_time,
        c_company_name=c_company.company_name,
        template_name="C8_"+b_company.short_name+".html"
    )

    BD_filename = f"{contract_number}_{contract_serial_number}_BCD模式_BD结算单.xlsx"

    BD_download_url = f"http://103.30.78.107:8000/download/{BD_filename}"

    # 生成B-D结算单
    BD_settlement_path = excel_utils.generate_common_settlement_excel(
        filename=BD_filename,  # 可根据项目名称动态命名
        stage="C8",
        project_type="BCD",
        received_amount=amount,
        receivable_items=[
            ("三方/四方货款", three_fourth),
            ('进口服务费', import_service_fee),
            ("第三方费用", third_party_fee),
            ("费用结算服务费", service_fee),
            ("中标服务费", win_bidding_fee),
            ("标书费", bidding_document_fee),
            ("投标服务费", bidding_service_fee)
        ],
        head_company_name=d_company.company_name,
        bottom_company_name=b_company.company_name
    )
    logger.info("BD_settlement_path&&&: %s", BD_settlement_path)
    # delay1 = random.randint(5, 60)
    delay1 = 1
    task2 = send_reply_email_with_attachments.apply_async(
        args=[d_email, b_email_subject_c8, b_email_content_c8, b_smtp, [BD_settlement_path], delay1, "C8", 1],
        countdown=delay1 * 60  # 相对第一封
    )

    upload_file_to_sftp_task.delay("~/settlements/"+BD_filename, BD_filename)


    # 第三封邮件：D ➝ B
    # 随机延迟 5–60 分钟发出D-B间结算单确认
    d_email_subject_c9 = email_utils.render_email_subject(
        stage="C9", 
        company_short_name=d_company.short_name, 
        project_name=simplify_to_traditional(project_name), 
        serial_number=contract_serial_number, 
        tender_number=tender_number, 
        winning_amount=str(amount), 
        winning_time=winning_time,
        purchase_department=simplify_to_traditional(purchase_department),
        contract_number=contract_number
    )
    logger.info("d_email_subject_c9: %s", d_email_subject_c9)
    d_email_content_c9 = email_utils.render_invitation_template_content(
        buyer_name="", 
        project_name=simplify_to_traditional(project_name), 
        first_name=b_company.last_name,
        serial_number=contract_serial_number,
        contract_number=contract_number,
        winning_amount=str(amount),
        winning_time=winning_time,
        template_name="C9_"+d_company.short_name+".html"
    )
    delay2 = delay1 + 1
    task3 = send_reply_email.apply_async(
        args=[b_email, d_email_subject_c9, d_email_content_c9, d_smtp, delay2, "C9", 1],
        countdown=delay2 * 60  # 相对第一封
    )


    # 第四封邮件：B ➝ D
    # 随机延迟 5–60 分钟发出B-D间结算单确认
    b_email_subject_c10 = email_utils.render_email_subject(
        stage="C10", 
        company_short_name=b_company.short_name, 
        project_name=project_name, 
        serial_number=contract_serial_number, 
        contract_number=contract_number, 
        winning_amount=str(amount), 
        winning_time=winning_time,
        purchase_department=purchase_department,
        tender_number=tender_number
    )
    logger.info("b_email_subject_c10: %s", b_email_subject_c10)
    b_email_content_c10 = email_utils.render_invitation_template_content(
        buyer_name="", 
        project_name=project_name, 
        first_name=c_company.last_name,
        serial_number=contract_serial_number,
        contract_number=contract_number,
        winning_amount=str(amount),
        winning_time=winning_time,
        template_name="C10_"+b_company.short_name+".html"
    )
    delay3 = delay2 + 1
    task4 = send_reply_email.apply_async(
        args=[d_email, b_email_subject_c10, b_email_content_c10, b_smtp, delay3, "C10", 1],
        countdown=delay3 * 60  # 相对第一封
    )

    return {
        "BC_download_url": BC_download_url,
        "BD_download_url": BD_download_url
    }
    

# CCD 项目类型发送结算单
# BD之间发送结算单
def schedule_settlement_CCD_BD(
    b_company: models.CompanyInfo,
    c_company: models.CompanyInfo,
    d_company: models.CompanyInfo,
    contract_number: str, # 合同号
    contract_serial_number: str, # 流水号
    project_name: str,
    amount: float,  # 收款金额（总额）
    three_fourth: float,  # 三方/四方货款
    import_service_fee: float,  # C公司进口服务费
    third_party_fee: float,  # 第三方费用
    service_fee: float,  # 费用结算服务费
    win_bidding_fee: float,  # 中标服务费
    bidding_document_fee: float,  # 标书费
    bidding_service_fee: float,  # 投标服务费
    winning_time: str,
    project_type: str, # BD/CCD
    purchase_department: str, # 购买部门
    tender_number: str # 招标编号
):

    b_email = b_company.email
    d_email = d_company.email

    b_smtp = {
        "host": b_company.smtp_host,
        "port": b_company.smtp_port,
        "username": b_company.smtp_username,
        "password": b_company.smtp_password,
        "from": b_company.smtp_from
    }

    d_smtp = {
        "host": d_company.smtp_host,
        "port": d_company.smtp_port,
        "username": d_company.smtp_username,
        "password": d_company.smtp_password,
        "from": d_company.smtp_from
    }

    # 第一封邮件：B ➝ D
    # 随机延迟 5–60 分钟发出B-D间结算单
    b_email_subject_c8 = email_utils.render_email_subject(
        stage="C8", 
        company_short_name=b_company.short_name, 
        project_name=project_name, 
        serial_number=contract_serial_number,
        contract_number=contract_number,
        winning_amount=str(amount),
        winning_time=winning_time,
        purchase_department=purchase_department,
        tender_number=tender_number
    )
    print("b_email_subject_c8: ", b_email_subject_c8)
    b_email_content_c8 = email_utils.render_invitation_template_content(
        buyer_name="", 
        project_name=project_name, 
        first_name=d_company.last_name,
        serial_number=contract_serial_number,
        contract_number=contract_number,
        winning_amount=str(amount),
        winning_time=winning_time,
        template_name="C8_"+b_company.short_name+".html"
    )

    BD_filename = ""

    # filename
    if project_type == "BD":
        BD_filename = f"{contract_number}_{contract_serial_number}_BD模式_BD结算单.xlsx"
    elif project_type == "CCD":
        BD_filename = f"{contract_number}_{contract_serial_number}_CCD模式_BD结算单.xlsx"

    # 生成B-D结算单
    BD_settlement_path, BD_download_url = excel_utils.generate_common_settlement_excel(
        filename=BD_filename,  
        stage="C8",
        project_type="BD",
        received_amount=amount,
        receivable_items=[
            ("三方/四方货款", three_fourth),
            ('进口服务费', import_service_fee),
            ("第三方费用", third_party_fee),
            ("费用结算服务费", service_fee),
            ("中标服务费", win_bidding_fee),
            ("标书费", bidding_document_fee),
            ("投标服务费", bidding_service_fee)
        ],
        head_company_name=b_company.company_name,
        bottom_company_name=d_company.company_name
    )

    # delay1 = random.randint(5, 60)
    delay1 = 1
    task2 = send_reply_email_with_attachments.apply_async(
        args=[d_email, b_email_subject_c8, b_email_content_c8, b_smtp, [BD_settlement_path], delay1, "C8", 1], # TODO 换成真实的附件路径
        countdown=0 # 立即
    )

    upload_file_to_sftp_task.delay("~/settlements/"+BD_filename, BD_filename)


    # 第二封邮件：D ➝ B
    # 随机延迟 5–60 分钟发出D-B间结算单确认
    d_email_subject_c9 = email_utils.render_email_subject(
        stage="C9", 
        company_short_name=d_company.short_name, 
        project_name=simplify_to_traditional(project_name), 
        serial_number=contract_serial_number, 
        tender_number=tender_number, 
        winning_amount=str(amount), 
        winning_time=winning_time,
        purchase_department=simplify_to_traditional(purchase_department),
        contract_number=contract_number
    )
    logger.info("d_email_subject_c9: %s", d_email_subject_c9)
    d_email_content_c9 = email_utils.render_invitation_template_content(
        buyer_name="", 
        project_name=simplify_to_traditional(project_name), 
        first_name=b_company.last_name,
        serial_number=contract_serial_number,
        contract_number=contract_number,
        winning_amount=str(amount),
        winning_time=winning_time,
        template_name="C9_"+d_company.short_name+".html"
    )
    delay2 = delay1 + 1
    task3 = send_reply_email.apply_async(
        args=[b_email, d_email_subject_c9, d_email_content_c9, d_smtp, delay2, "C9", 1],
        countdown=delay2 * 60  # 相对第一封
    )


    return {
        "message": f"已发送BD结算单，合同号为：{contract_serial_number}",
        "BD_download_url": BD_download_url
    }

# BD 项目类型发送结算单
def schedule_settlement_BD(b_company_name: str, d_company_name: str):
    b_company = db.query(models.CompanyInfo).filter(models.CompanyInfo.company_name == b_company_name).first()
    d_company = db.query(models.CompanyInfo).filter(models.CompanyInfo.company_name == d_company_name).first()

    b_email = b_company.email
    d_email = d_company.email
    
    b_smtp = {
        "host": b_company.smtp_host,
        "port": b_company.smtp_port,
        "username": b_company.smtp_username,
        "password": b_company.smtp_password,
        "from": b_company.smtp_from
    }
    d_smtp = {
        "host": d_company.smtp_host,
        "port": d_company.smtp_port,
        "username": d_company.smtp_username,
        "password": d_company.smtp_password,
        "from": d_company.smtp_from
    }

    # 获取对应B公司的邮件模板
    b_email_subject_b1 = render_email_subject("B1", b_company.short_name, project_name, b_company.serial_number)
    b_email_content_b1 = render_invitation_template_content(b_company_name, project_name, "b1_"+b_company.short_name+".txt")
    
    # 第一封邮件：B ➝ D
    task1 = send_reply_email.apply_async(
        args=[d_email, b_email_subject_b1, b_email_content_b1, b_smtp],
        countdown=0  # 立即
    )
    
    # 随机延迟 5–60 分钟
    d_email_subject_d1 = render_email_subject("D1", d_company.short_name, project_name, d_company.serial_number)
    d_email_content_d1 = render_invitation_template_content(d_company_name, project_name, "d1_"+d_company.short_name+".txt")
    delay1 = random.randint(5, 60)
    task2 = send_reply_email.apply_async(
        args=[b_email, d_email_subject_d1, d_email_content_d1, d_smtp],
        countdown=delay1 * 60  # 相对第一封
    )
    
    return {
        "tasks": [
            {"step": "B ➝ D", "task_id": task1.id, "delay_min": 0},
            {"step": "D ➝ B", "task_id": task2.id, "delay_min": delay1},
        ]
    }
            

