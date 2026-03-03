import os
from dotenv import load_dotenv

import random 
from datetime import datetime, timedelta
from contextlib import contextmanager

from app import database, models, email_utils, excel_utils
from app.tasks import send_reply_email, upload_file_to_sftp_task, send_email_with_followup_delay, send_reply_email_with_attachments_delay
from app.utils import simplify_to_traditional
from app.email_utils import MAIL_ACCOUNTS

from celery import chain

import logging

logger = logging.getLogger(__name__)
load_dotenv()

now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

max_sending_time = 60

@contextmanager
def get_db_session():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

def schedule_bid_conversation_BCD(
    project_info: models.ProjectInfo,
    b_company: models.CompanyInfo, 
    c_company: models.CompanyInfo, 
    d_company: models.CompanyInfo, 
    contract_number: str,  # 合同号
    winning_amount: str,   # 中标金额
    winning_time: str,     # 中标时间
    contract_serial_number: str,  # 流水号
    project_name: str,
    tender_number: str,    # 招标编号
    purchase_department: str  # 采购单位
):
    """
    调度 BCD 项目类型的邮件对话链：B3 → B4 → B5 → B6
    如果 D 公司是 PR，则根据项目 current_plss_email 确定是否加抄送人。
    """

    # === 判断抄送人逻辑（仅对 PR 生效） ===
    cc_list = []
    if d_company.short_name == "PR":
        if project_info.current_plss_email in ("A", "B"):
            cc_list = [email_utils.MAIL_ACCOUNTS["C"]["email"]]
    logger.info("PR 抄送人: %s", cc_list if cc_list else "无")

    # === SMTP 配置 ===
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

    # === D SMTP 配置 ===
    if d_company.short_name == "PR":

        acc = email_utils.MAIL_ACCOUNTS.get(project_info.current_plss_email)
        if not acc:
            raise KeyError(f"MAIL_ACCOUNTS 中不存在别名：{project_info.current_plss_email}")

        d_smtp = {
            "host": acc["smtp_host"],
            "port": acc["smtp_port"],
            "username": acc["username"],
            "password": acc["password"],
            "from": acc["from"]
        }
    else:
        d_smtp = {
            "host": d_company.smtp_host,
            "port": d_company.smtp_port,
            "username": d_company.smtp_username,
            "password": d_company.smtp_password,
            "from": d_company.smtp_from
        }

    # === B3：B ➝ C ===
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
        template_name="B3_" + b_company.short_name + ".html",
        # 发送人落款信息
        contact_person=b_company.contact_person,
        company_name=b_company.company_name,
        phone=b_company.phone,
        email=b_company.email,
        address=b_company.address,
        english_address=b_company.english_address,
        pingyin=b_company.pingyin,
        company_en=b_company.company_en,
    )
    logger.info("B3-B公司邮件主题：%s", b_email_subject_b3)

    # === B4：C ➝ B ===
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
    c_email_content_b4 = email_utils.render_invitation_template_content(
        buyer_name=c_company.company_name, 
        project_name=project_name, 
        serial_number=contract_serial_number,
        first_name=b_company.last_name,
        winning_amount=winning_amount,
        contract_number=contract_number,
        template_name="B4_" + c_company.short_name + ".html",
        # 发送人落款信息
        contact_person=c_company.contact_person,
        company_name=c_company.company_name,
        phone=c_company.phone,
        email=c_company.email,
        address=c_company.address,
        english_address=c_company.english_address,
        pingyin=c_company.pingyin,
        company_en=c_company.company_en,
    )
    logger.info("B4-C公司邮件主题：%s", c_email_subject_b4)

    # === B5：B ➝ D ===
    b_email_subject_b5 = email_utils.render_email_subject(
        stage="B5", 
        company_short_name=b_company.short_name, 
        project_name=project_name, 
        serial_number=contract_serial_number,
        tender_number=tender_number,
        winning_amount=winning_amount,
        winning_time=winning_time
    )
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
        template_name="B5_" + b_company.short_name + ".html",
        # 发送人落款信息
        contact_person=b_company.contact_person,
        company_name=b_company.company_name,
        phone=b_company.phone,
        email=b_company.email,
        address=b_company.address,
        english_address=b_company.english_address,
        pingyin=b_company.pingyin,
        company_en=b_company.company_en,
    )
    logger.info("B5-B公司邮件主题：%s", b_email_subject_b5)

    # === B6：D ➝ B ===
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
        buyer_name=d_company.company_name, 
        first_name=b_company.last_name_traditional,
        full_name=b_company.contact_person, 
        winning_amount=winning_amount, 
        contract_number=contract_number,
        serial_number=contract_serial_number,
        project_name=project_name, 
        winning_time=winning_time,
        template_name="B6_" + d_company.short_name + ".html",
        # 发送人落款信息
        contact_person=d_company.contact_person,
        company_name=d_company.company_name,
        phone=d_company.phone,
        email=d_company.email,
        address=d_company.address,
        english_address=d_company.english_address,
        pingyin=d_company.pingyin,
        company_en=d_company.company_en,
    )
    logger.info("B6-D公司邮件主题：%s", d_email_subject_b6)

    # === 构造任务链 ===
    delay_b6 = random.randint(5, max_sending_time) * 60
    task_b6 = {
        "to_email": b_company.email,
        "subject": d_email_subject_b6,
        "content": d_email_content_b6,
        "smtp_config": d_smtp,
        "stage": "B6",
        "followup_task_args": None,
        "followup_delay": delay_b6
    }
    if cc_list:
        task_b6["cc"] = cc_list

    delay_b5 = random.randint(5, max_sending_time) * 60
    task_b5 = {
        "to_email": d_smtp["from"],
        "subject": b_email_subject_b5,
        "content": b_email_content_b5,
        "smtp_config": b_smtp,
        "stage": "B5",
        "followup_task_args": task_b6,
        "followup_delay": delay_b5
    }
    if cc_list:
        task_b5["cc"] = cc_list

    delay_b4 = random.randint(5, max_sending_time) * 60
    task_b4 = {
        "to_email": b_company.email,
        "subject": c_email_subject_b4,
        "content": c_email_content_b4,
        "smtp_config": c_smtp,
        "stage": "B4",
        "followup_task_args": task_b5,
        "followup_delay": delay_b4
    }

    delay_b3 = random.randint(5, max_sending_time) * 60
    task_b3 = {
        "to_email": c_company.email,
        "subject": b_email_subject_b3,
        "content": b_email_content_b3,
        "smtp_config": b_smtp,
        "stage": "B3",
        "followup_task_args": task_b4,
        "followup_delay": delay_b3
    }

    logger.info(f"[B3] 💌 调度链准备完成，目标：{c_company.email}")

    # === 调度起点 (B3) ===
    send_email_with_followup_delay.apply_async(
        kwargs=task_b3,
        countdown=0
    )

    return {"message": "BCD email chain scheduled"}


# CCD 项目类型发送邮件
# 仅有BD公司之间发送两封邮件
# 特殊B5模板
def schedule_bid_conversation_CCD(
    project_info: models.ProjectInfo,
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

    # with get_db_session() as db:
    #     project_info = db.query(models.ProjectInfo).filter(models.ProjectInfo.project_name == project_name).first()
    # === 判断抄送人逻辑（仅对 PR 生效） ===
    cc_list = []
    if d_company.short_name == "PR":
        if project_info.current_plss_email in ("A", "B"):
            cc_list = [email_utils.MAIL_ACCOUNTS["C"]["email"]]
    logger.info("PR 抄送人: %s", cc_list if cc_list else "无")


    b_smtp = {
        "host": b_company.smtp_host,
        "port": b_company.smtp_port,
        "username": b_company.smtp_username,
        "password": b_company.smtp_password,
        "from": b_company.smtp_from
    }


    # === D SMTP 配置 ===
    if d_company.short_name == "PR":

        acc = email_utils.MAIL_ACCOUNTS.get(project_info.current_plss_email)
        if not acc:
            raise KeyError(f"MAIL_ACCOUNTS 中不存在别名：{project_info.current_plss_email}")

        # 3) 兼容老/新键名读取
        def getf(d, *keys, default=None):
            for k in keys:
                if k in d and d[k] not in (None, ""):
                    return d[k]
            return default

        d_smtp = {
            "host": acc["smtp_host"],
            "port": acc["smtp_port"],
            "username": acc["username"],
            "password": acc["password"],
            "from": acc["from"]
        }
    else:
        d_smtp = {
            "host": d_company.smtp_host,
            "port": d_company.smtp_port,
            "username": d_company.smtp_username,
            "password": d_company.smtp_password,
            "from": d_company.smtp_from
        }

    # C公司的特殊B5邮件模板
    c_email_subject_b5 = email_utils.render_email_subject(
        stage="B5", 
        company_short_name=b_company.short_name, 
        project_name=project_name, 
        serial_number=contract_serial_number,
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
        full_name=d_company.contact_person,
        winning_amount=winning_amount,
        contract_number=contract_number,
        # c_company_name=c_company.company_name,
        winning_time=winning_time,
        template_name="B5_"+b_company.short_name+"_SPEC.html",
        # 发送人落款信息
        contact_person=b_company.contact_person,
        company_name=b_company.company_name,
        phone=b_company.phone,
        email=b_company.email,
        address=b_company.address,
        english_address=b_company.english_address,
        pingyin=b_company.pingyin,
        company_en=b_company.company_en,
    )
    
    logger.info("CCD B5-C公司邮件主题：%s", c_email_subject_b5)
    
    # 第一封邮件：B ➝ D（立即）
    # task1 = send_reply_email.apply_async(
    #     args=[d_email, c_email_subject_b5, c_email_content_b5, b_smtp],
    #     countdown=0  # 立即
    # )

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
        template_name="B6_"+d_company.short_name+".html",
        # 发送人落款信息
        contact_person=d_company.contact_person,
        company_name=d_company.company_name,
        phone=d_company.phone,
        email=d_company.email,
        address=d_company.address,
        english_address=d_company.english_address,
        pingyin=d_company.pingyin,
        company_en=d_company.company_en,
    )
    # delay = random.randint(5, 60)
    # delay = 1
    # task2 = send_reply_email.apply_async(
    #     args=[b_email, d_email_subject_b6, d_email_content_b6, d_smtp],
    #     countdown=delay * 60
    # )

    # 生成随机延迟时间（5 ~ 60 分钟）
    delay_b6 = random.randint(5, max_sending_time) * 60

    # 第二封邮件：D ➝ B（由 B5 成功后触发）
    task_b6 = {
        "to_email": b_company.email,
        "subject": d_email_subject_b6,
        "content": d_email_content_b6,
        "smtp_config": d_smtp,
        "stage": "B6",
        # "project_id": project_info.id,
        "followup_task_args": None,
        "followup_delay": delay_b6  # 无后续任务
    }
    if cc_list:
        task_b6["cc"] = cc_list
    logger.info(f"[B6] 💌 邮件准备完毕，将在 B5 成功后延迟 {delay_b6 // 60} 分钟发送，目标：{b_company.email}")

    # 第一封邮件：B ➝ D（成功后调度 B6）
    task_b5 = {
        "to_email": d_smtp["from"],
        "subject": c_email_subject_b5,
        "content": c_email_content_b5,
        "smtp_config": b_smtp,
        "stage": "B5",
        # "project_id": project_info.id,
        "followup_task_args": task_b6,
        "followup_delay": delay_b6
    }
    logger.info(f"[B5] 🚀 邮件已调度，发送对象：{d_company.email}，发送成功后将调度 B6")

    # 调度 B5 邮件立即执行（或你也可以加入前置 delay）
    send_email_with_followup_delay.apply_async(
        kwargs=task_b5,
        countdown=0
    )

    return {
        "message": "email sent!"
    }


# BD 项目类型发送邮件
def schedule_bid_conversation_BD(
    project_info: models.ProjectInfo,
    b_company: models.CompanyInfo, 
    c_company_name: str,
    d_company: models.CompanyInfo,
    contract_serial_number: str,
    winning_amount: str,
    winning_time: str,
    contract_number: str,
    project_name: str,
    purchase_department: str,
    tender_number: str
):

    cc_list = []
    if d_company.short_name == "PR":
        if project_info.current_plss_email in ("A", "B"):
            cc_list = [email_utils.MAIL_ACCOUNTS["C"]["email"]]
    logger.info("PR 抄送人: %s", cc_list if cc_list else "无")

    b_smtp = {
        "host": b_company.smtp_host,
        "port": b_company.smtp_port,
        "username": b_company.smtp_username,
        "password": b_company.smtp_password,
        "from": b_company.smtp_from
    }

    # === D SMTP 配置 ===
    if d_company.short_name == "PR":

        acc = email_utils.MAIL_ACCOUNTS.get(project_info.current_plss_email)
        if not acc:
            raise KeyError(f"MAIL_ACCOUNTS 中不存在别名：{project_info.current_plss_email}")

        d_smtp = {
            "host": acc["smtp_host"],
            "port": acc["smtp_port"],
            "username": acc["username"],
            "password": acc["password"],
            "from": acc["from"]
        }
        print("PR 公司SMTP配置：", d_smtp)
    else:
        d_smtp = {
            "host": d_company.smtp_host,
            "port": d_company.smtp_port,
            "username": d_company.smtp_username,
            "password": d_company.smtp_password,
            "from": d_company.smtp_from
        }
        print("非PR 公司SMTP配置：", d_smtp)

    

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
        c_company_name=c_company_name,
        buyer_name=b_company.company_name,
        project_name=project_name,
        serial_number=contract_serial_number,
        first_name=d_company.last_name,
        full_name=d_company.contact_person,
        winning_amount=winning_amount,
        contract_number=contract_number,
        winning_time=winning_time,
        template_name="B5_"+b_company.short_name+".html",
        # 发送人落款信息
        contact_person=b_company.contact_person,
        company_name=b_company.company_name,
        phone=b_company.phone,
        email=b_company.email,
        address=b_company.address,
        english_address=b_company.english_address,
        pingyin=b_company.pingyin,
        company_en=b_company.company_en,
    )
    # 第一封邮件：B ➝ D
    # task1 = send_reply_email.apply_async(
    #     args=[d_email, b_email_subject_b5, b_email_content_b5, b_smtp],
    #     countdown=0  # 立即
    # )

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
        first_name=b_company.last_name_traditional,
        full_name=b_company.contact_person,
        winning_amount=winning_amount,
        contract_number=contract_number,
        winning_time=winning_time,
        template_name="B6_"+d_company.short_name+".html",
        # 发送人落款信息
        contact_person=d_company.contact_person,
        company_name=d_company.company_name,
        phone=d_company.phone,
        email=d_company.email,
        address=d_company.address,
        english_address=d_company.english_address,
        pingyin=d_company.pingyin,
        company_en=d_company.company_en,
    )

    # 生成 B6 邮件发送的延迟时间（单位：秒）
    delay_b6 = random.randint(5, max_sending_time) * 60

    # 第二封邮件：D ➝ B（将在 B5 成功后延迟 delay_b6 秒发送）
    task_b6 = {
        "to_email": b_company.email,
        "subject": d_email_subject_b6,
        "content": d_email_content_b6,
        "smtp_config": d_smtp,
        "stage": "B6",
        "followup_task_args": None,
        "followup_delay": delay_b6  # 无下一级任务
    }
    logger.info(f"[B6] 💌 准备完毕，目标: {b_company.email}，将在 B5 成功后延迟 {delay_b6 // 60} 分钟发送")
    if cc_list:
        task_b6["cc"] = cc_list

    # 生成 B5 邮件发送的延迟时间（单位：秒）
    delay_b5 = random.randint(5, max_sending_time) * 60
    # 第一封邮件：B ➝ D
    task_b5 = {
        "to_email": d_smtp["from"],
        "subject": b_email_subject_b5,
        "content": b_email_content_b5,
        "smtp_config": b_smtp,
        "stage": "B5",
        # "project_id": project_info.id,  
        "followup_task_args": task_b6,
        "followup_delay": delay_b5
    }
    logger.info(f"[B5] 🚀 调度中，目标: {d_company.email}，成功后将调度 B6")

    # 调度 B5，立即执行
    send_email_with_followup_delay.apply_async(
        kwargs=task_b5,
        countdown=0
    )

    return {
        "message": "email sent!"
    }



'''
# BCD 项目类型发送结算单
# 1. 发送C-B间结算单
# 2. 上一封邮件发出5-60分钟后，发送B-D间结算单
# 3. 上一封邮件发出5-60分钟后，B-D间结算单确认
# 4. 上一封邮件发出5-60分钟后，C-D间结算单确认

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
    project_info: models.ProjectInfo,
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
):

    cc_list = []
    if d_company.short_name == "PR":
        if project_info.current_plss_email in ("A", "B"):
            cc_list = [email_utils.MAIL_ACCOUNTS["C"]["email"]]
    logger.info("PR 抄送人: %s", cc_list if cc_list else "无")


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

    # === D SMTP 配置 ===
    if d_company.short_name == "PR":

        acc = email_utils.MAIL_ACCOUNTS.get(project_info.current_plss_email)
        if not acc:
            raise KeyError(f"MAIL_ACCOUNTS 中不存在别名：{project_info.current_plss_email}")

        d_smtp = {
            "host": acc["smtp_host"],
            "port": acc["smtp_port"],
            "username": acc["username"],
            "password": acc["password"],
            "from": acc["from"]
        }
    else:
        d_smtp = {
            "host": d_company.smtp_host,
            "port": d_company.smtp_port,
            "username": d_company.smtp_username,
            "password": d_company.smtp_password,
            "from": d_company.smtp_from
        }



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
        template_name="C7_"+c_company.short_name+".html",
        # 发送人落款信息
        contact_person=c_company.contact_person,
        company_name=c_company.company_name,
        phone=c_company.phone,
        email=c_company.email,
        address=c_company.address,
        english_address=c_company.english_address,
        pingyin=c_company.pingyin,
        company_en=c_company.company_en,
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
            ('C进口服务费', import_service_fee),
            ("第三方费用", third_party_fee),
            ("费用结算服务费", service_fee),
        ],
        head_company_name=b_company.company_name,
        bottom_company_name=c_company.company_name
    )

    CB_email_attachment_path = excel_utils.generate_email_settlement_excel(
        filename="结算单.xlsx",
        prefix="CB",
        received_amount=amount,
        receivable_items=[
            ("三方/四方货款", three_fourth),
            ('C进口服务费', import_service_fee),
            ("第三方费用", third_party_fee),
            ("费用结算服务费", service_fee),
        ],
        head_company_name=b_company.company_name,
        bottom_company_name=c_company.company_name
    )

    logger.info("CB_settlement_path&&&: %s", CB_settlement_path)
    logger.info("CB_email_attachment_path&&&: %s", CB_email_attachment_path)
    #TODO 1. FTP将生成的文件回传到归档服务器
    
    upload_file_to_sftp_task.delay("~/settlements/"+BC_filename, BC_filename)

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
        template_name="C8_"+b_company.short_name+".html",
        # 发送人落款信息
        contact_person=b_company.contact_person,
        company_name=b_company.company_name,
        phone=b_company.phone,
        email=b_company.email,
        address=b_company.address,
        english_address=b_company.english_address,
        pingyin=b_company.pingyin,
        company_en=b_company.company_en,
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
            ('C进口服务费', import_service_fee),
            ("第三方费用", third_party_fee),
            ("费用结算服务费", service_fee),
            ("中标服务费", win_bidding_fee),
            ("购买标书费", bidding_document_fee),
            ("投标服务费", bidding_service_fee)
        ],
        head_company_name=d_company.company_name,
        bottom_company_name=b_company.company_name
    )

    BD_email_attachment_path = excel_utils.generate_email_settlement_excel(
        filename="结算单.xlsx",
        prefix="BD",
        received_amount=amount,
        receivable_items=[
            ("三方/四方货款", three_fourth),
            ('C进口服务费', import_service_fee),
            ("第三方费用", third_party_fee),
            ("费用结算服务费", service_fee),
            ("中标服务费", win_bidding_fee),
            ("购买标书费", bidding_document_fee),
            ("投标服务费", bidding_service_fee)
        ],
        head_company_name=d_company.company_name,
        bottom_company_name=b_company.company_name
    )

    logger.info("BD_settlement_path&&&: %s", BD_settlement_path)
    logger.info("BD_email_attachment_path&&&: %s", BD_email_attachment_path)

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
        first_name=b_company.last_name_traditional,
        serial_number=contract_serial_number,
        contract_number=contract_number,
        winning_amount=str(amount),
        winning_time=winning_time,
        template_name="C9_"+d_company.short_name+".html",
        # 发送人落款信息
        contact_person=d_company.contact_person,
        company_name=d_company.company_name,
        phone=d_company.phone,
        email=d_company.email,
        address=d_company.address,
        english_address=d_company.english_address,
        pingyin=d_company.pingyin,
        company_en=d_company.company_en,
    )

    # 第四封邮件：B ➝ C
    # 随机延迟 5–60 分钟发出B-C间结算单确认
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
        template_name="C10_"+b_company.short_name+".html",
        # 发送人落款信息
        contact_person=b_company.contact_person,
        company_name=b_company.company_name,
        phone=b_company.phone,
        email=b_company.email,
        address=b_company.address,
        english_address=b_company.english_address,
        pingyin=b_company.pingyin,
        company_en=b_company.company_en,
    )

    # 最后一封邮件任务 C10：B ➝ C（无 follow up）
    delay_c10 = random.randint(5, max_sending_time) * 60
    task_c10 = {
        "to_email": c_company.email,
        "subject": b_email_subject_c10,
        "content": b_email_content_c10,
        "smtp_config": b_smtp,
        "stage": "C10",
        # "project_id": project_info.id,
        "attachments": [],
        "followup_task_args": None,
        "followup_delay": delay_c10
    }
    logger.info(f"[C10] 💌 准备完毕，目标：{c_company.email}，将在 C9 成功后延迟 {delay_c10 // 60} 分钟发送")

    # C9：D ➝ B（成功后调度 C10）
    delay_c9 = random.randint(5, max_sending_time) * 60
    task_c9 = {
        "to_email": b_company.email,
        "subject": d_email_subject_c9,
        "content": d_email_content_c9,
        "smtp_config": d_smtp,
        "stage": "C9",
        # "project_id": project_info.id,
        "attachments": [],
        "followup_task_args": task_c10,
        "followup_delay": delay_c9
    }

    if cc_list:
        task_c9["cc"] = cc_list
    logger.info(f"[C9] 💌 准备完毕，目标：{b_company.email}，成功后将在 {delay_c9 // 60} 分钟后调度 C10")

    # C8：B ➝ D（成功后调度 C9）
    delay_c8 = random.randint(5, max_sending_time) * 60
    task_c8 = {
        "to_email": d_smtp["from"],
        "subject": b_email_subject_c8,
        "content": b_email_content_c8,
        "smtp_config": b_smtp,
        "stage": "C8",
        # "project_id": project_info.id,
        "attachments": [BD_email_attachment_path],
        "followup_task_args": task_c9,
        "followup_delay": delay_c8
    }
    logger.info(f"[C8] 💌 准备完毕，目标：{d_company.email}，成功后将在 {delay_c8 // 60} 分钟后调度 C9")

    # C7：C ➝ B（入口任务，成功后调度 C8）
    delay_c7 = random.randint(5, max_sending_time) * 60
    task_c7 = {
        "to_email": b_company.email,
        "subject": c_email_subject_c7,
        "content": c_email_content_c7,
        "smtp_config": c_smtp,
        "stage": "C7",
        # "project_id": project_info.id,
        "attachments": [CB_email_attachment_path],
        "followup_task_args": task_c8,
        "followup_delay": delay_c7
    }
    logger.info(f"[C7] 🚀 开始调度，目标：{b_company.email}，成功后将在 {delay_c7 // 60} 分钟后调度 C8")

    # 启动入口任务 C7
    send_reply_email_with_attachments_delay.apply_async(
        kwargs=task_c7,
        countdown=0
    )
    

    return {
        "BC_download_url": BC_download_url,
        "BD_download_url": BD_download_url,
        "tasks": [
            task_c10,
            task_c9,
            task_c8,
            task_c7
        ]
    }
    

# CCD 项目类型发送结算单
# BD之间发送结算单
def schedule_settlement_CCD_BD(
    project_info: models.ProjectInfo,
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

    cc_list = []
    if d_company.short_name == "PR":
        if project_info.current_plss_email in ("A", "B"):
            cc_list = [email_utils.MAIL_ACCOUNTS["C"]["email"]]
    logger.info("PR 抄送人: %s", cc_list if cc_list else "无")

    b_email = b_company.email
    d_email = d_company.email

    b_smtp = {
        "host": b_company.smtp_host,
        "port": b_company.smtp_port,
        "username": b_company.smtp_username,
        "password": b_company.smtp_password,
        "from": b_company.smtp_from
    }

    # === D SMTP 配置 ===
    if d_company.short_name == "PR":

        acc = email_utils.MAIL_ACCOUNTS.get(project_info.current_plss_email)
        if not acc:
            raise KeyError(f"MAIL_ACCOUNTS 中不存在别名：{project_info.current_plss_email}")

        d_smtp = {
            "host": acc["smtp_host"],
            "port": acc["smtp_port"],
            "username": acc["username"],
            "password": acc["password"],
            "from": acc["from"]
        }
    else:
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
        full_name=d_company.contact_person,
        serial_number=contract_serial_number,
        contract_number=contract_number,
        winning_amount=str(amount),
        winning_time=winning_time,
        template_name="C8_"+b_company.short_name+".html",
        # 发送人落款信息
        contact_person=b_company.contact_person,
        company_name=b_company.company_name,
        phone=b_company.phone,
        email=b_company.email,
        address=b_company.address,
        english_address=b_company.english_address,
        pingyin=b_company.pingyin,
        company_en=b_company.company_en,
    )

    BD_filename = ""

    # filename
    if project_type == "BD":
        BD_filename = f"{contract_number}_{contract_serial_number}_BD模式_BD结算单.xlsx"
    elif project_type == "CCD":
        BD_filename = f"{contract_number}_{contract_serial_number}_CCD模式_BD结算单.xlsx"

    # 生成B-D结算单
    BD_settlement_path = excel_utils.generate_common_settlement_excel(
        filename=BD_filename,  
        stage="C8",
        project_type="BD",
        received_amount=amount,
        receivable_items=[
            ("三方/四方货款", three_fourth),
            ('C进口服务费', import_service_fee),
            ("第三方费用", third_party_fee),
            ("费用结算服务费", service_fee),
            ("中标服务费", win_bidding_fee),
            ("购买标书费", bidding_document_fee),
            ("投标服务费", bidding_service_fee)
        ],
        head_company_name=d_company.company_name,
        bottom_company_name=b_company.company_name
    )

    BD_email_attachment_path = excel_utils.generate_email_settlement_excel(
        filename="结算单.xlsx",
        prefix="BD",
        received_amount=amount,
        receivable_items=[
            ("三方/四方货款", three_fourth),
            ('C进口服务费', import_service_fee),
            ("第三方费用", third_party_fee),
            ("费用结算服务费", service_fee),
            ("中标服务费", win_bidding_fee),
            ("购买标书费", bidding_document_fee),
            ("投标服务费", bidding_service_fee)
        ],
        head_company_name=d_company.company_name,
        bottom_company_name=b_company.company_name
    )

    logger.info("BD_settlement_path&&&: %s", BD_settlement_path)
    logger.info("BD_email_attachment_path&&&: %s", BD_email_attachment_path)


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
        full_name=b_company.contact_person,
        serial_number=contract_serial_number,
        contract_number=contract_number,
        winning_amount=str(amount),
        winning_time=winning_time,
        template_name="C9_"+d_company.short_name+".html",
        # 发送人落款信息
        contact_person=d_company.contact_person,
        company_name=d_company.company_name,
        phone=d_company.phone,
        email=d_company.email,
        address=d_company.address,
        english_address=d_company.english_address,
        pingyin=d_company.pingyin,
        company_en=d_company.company_en,
    )

    # 第二封邮件：D ➝ B（由 C8 成功后调度）
    delay_c9 = random.randint(5, max_sending_time) * 60
    task_c9 = {
        "to_email": b_email,
        "subject": d_email_subject_c9,
        "content": d_email_content_c9,
        "smtp_config": d_smtp,
        "stage": "C9",
        # "project_id": project_info.id,
        "attachments": [],
        "followup_task_args": None,
        "followup_delay": delay_c9
    }
    if cc_list:
        task_c9["cc"] = cc_list
    logger.info(f"[C9] 💌 准备完毕，目标：{b_email}，将在 C8 成功后延迟 {delay_c9 // 60} 分钟发送")

    # 第一封邮件：B ➝ D（启动任务）
    delay_c8 = random.randint(5, max_sending_time) * 60
    task_c8 = {
        "to_email": d_smtp["from"],
        "subject": b_email_subject_c8,
        "content": b_email_content_c8,
        "smtp_config": b_smtp,
        "stage": "C8",
        # "project_id": project_info.id,
        "attachments": [BD_email_attachment_path],
        "followup_task_args": task_c9,
        "followup_delay": delay_c8
    }
    logger.info(f"[C8] 🚀 调度任务，目标：{d_email}，成功后将在 {delay_c9 // 60} 分钟后发送 C9")

    # 执行任务 C8（立即）
    logger.info(f"[C8] 📋 准备调用apply_async，task_c8参数: {list(task_c8.keys())}")
    logger.info(f"[C8] 📋 task_c8['followup_task_args']的keys: {list(task_c8['followup_task_args'].keys()) if task_c8.get('followup_task_args') else 'None'}")

    send_reply_email_with_attachments_delay.apply_async(
        kwargs=task_c8,
        countdown=0
    )

    logger.info(f"[C8] ✅ apply_async调用完成")


    return {
        "message": f"已发送BD结算单，合同号为：{contract_serial_number}",
        "BD_download_url": BD_settlement_path
    }



