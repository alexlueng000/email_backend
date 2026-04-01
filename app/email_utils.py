# app/email_utils.py
import os
from datetime import datetime
from typing import Optional, Union, Iterable, List

import smtplib
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

# from app.tasks import send_reply_email
from app import database, models
from app.utils import get_dingtalk_access_token, create_yida_form_instance

from sqlalchemy import desc, nullslast
from jinja2 import Environment, FileSystemLoader, select_autoescape

from contextlib import contextmanager

import logging

logger = logging.getLogger(__name__)

@contextmanager
def get_db_session():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# settings_mail.py
MAIL_ACCOUNTS = {
    "B": {
        "alias": "B",
        "email": "xu.p@001precise.com",
        "smtp_host": "smtphz.qiye.163.com",
        "smtp_port": 465,
        "username": "xu.p@001precise.com",
        "password": "FPRZYgLRVcUQ81W8",
        "from": "xu.p@001precise.com",
        "active": True,
    },
    "A": {
        "alias": "A",
        "email": "infotech@001precise.com",
        "smtp_host": "smtphz.qiye.163.com",
        "smtp_port": 465,
        "username": "infotech@001precise.com",
        "password": "62tfX4Lk9pHWKCp4",
        "from": "infotech@001precise.com",
        "active": True,
    },
    "C": {
        "alias": "C",
        "email": "huang.bh@001precise.com",
        "smtp_host": "smtphz.qiye.163.com",
        "smtp_port": 465,
        "username": "huang.bh@001precise.com",
        "password": "tqax4ABWarc3WrAp",
        "from": "huang.bh@001precise.com",
        "active": True,
    },
    "D": {
        "alias": "D",
        "email": "ouy@001precise.com",
        "smtp_host": "smtphz.qiye.163.com",
        "smtp_port": 465,
        "username": "ouy@001precise.com",
        "password": "3#G6g3#FHU3CHmgj",
        "from": "ouy@001precise.com",
        "active": True,
    },
}

# 如果上一个是A，那就返回B；如果是B，就返回C；否则返回A
def get_last_plss_email() -> str:
    with get_db_session() as db:
        last_project = (
            db.query(models.ProjectInfo)
            .filter(models.ProjectInfo.current_plss_email.isnot(None))
            .order_by(
                models.ProjectInfo.created_at.desc(),  # 先按时间倒序
                models.ProjectInfo.id.desc(),          # 时间相同再按自增ID倒序
            )
            .first()
        )

        prev_alias = getattr(last_project, "current_plss_email", None)
        print("上一个PLSS邮箱别名:", prev_alias)

        if prev_alias == "A":
            return "B"
        elif prev_alias == "B":
            return "C"
        else:
            return "A"

def _normalize_cc(cc: Optional[Union[str, Iterable[str]]]) -> List[str]:
    """
    将 cc 归一化为字符串列表：
    - None -> []
    - 'a@x.com,b@x.com' / 'a@x.com; b@x.com' -> ['a@x.com','b@x.com']
    - ['a@x.com', 'b@x.com'] -> ['a@x.com','b@x.com']
    - 自动去空格与过滤空串
    """
    if cc is None:
        return []
    if isinstance(cc, str):
        # 支持逗号或分号分隔
        parts = [p.strip() for p in cc.replace(";", ",").split(",")]
        return [p for p in parts if p]
    try:
        return [str(p).strip() for p in cc if str(p).strip()]
    except TypeError:
        # 不是可迭代：当作单一字符串
        s = str(cc).strip()
        return [s] if s else []


def send_email(
    to: str,
    subject: str,
    body: str,
    smtp_config: dict,
    stage: str,
    cc: Optional[Union[str, Iterable[str]]] = None,  # ← 新增：可选抄送
):
    print("✅ 执行同步 send_email 函数")
    message = EmailMessage()
    message["From"] = smtp_config["from"]
    message["To"] = to
    message["Subject"] = subject
    message.add_alternative(body, subtype="html")

    # 规范化 cc，并写入头
    def _normalize_cc(cc_val) -> list[str]:
        if cc_val is None:
            return []
        if isinstance(cc_val, str):
            parts = [p.strip() for p in cc_val.replace(";", ",").split(",")]
            return [p for p in parts if p]
        try:
            return [str(p).strip() for p in cc_val if str(p).strip()]
        except TypeError:
            s = str(cc_val).strip()
            return [s] if s else []

    cc_list = _normalize_cc(cc)
    if cc_list:
        message["Cc"] = ", ".join(cc_list)

    # DB 查询保持不变（注意：这里只记录 From 与 To 的公司信息；如需记录 CC，可在表单中追加一项文本字段）
    with get_db_session() as db:
        from_company = db.query(models.CompanyInfo).filter(models.CompanyInfo.email == smtp_config["from"]).first()
        to_company = db.query(models.CompanyInfo).filter(models.CompanyInfo.email == to).first()

    try:
        logger.info("📧 开始建立 SMTP 连接")
        logger.info("host", smtp_config["host"])
        logger.info("port", smtp_config["port"])
        logger.info("username", smtp_config["username"])
        logger.info("password", smtp_config["password"])
        logger.info("from", smtp_config["from"])
        logger.info("to", to)
        logger.info("subject", subject)
        print("body", body)
        print("cc", cc)
        with smtplib.SMTP_SSL(smtp_config["host"], smtp_config["port"], timeout=30) as smtp:
            logger.info("📧 登录 SMTP...")
            logger.info("📧 登录 SMTP...username: %s, password: %s", smtp_config["username"], smtp_config["password"])
            smtp.login(smtp_config["username"], smtp_config["password"])
            logger.info("📧 登录成功，开始发送邮件...")
            # send_message 若未提供 to_addrs，会自动使用消息头中的 To/Cc/Bcc
            smtp.send_message(message)

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        logger.info("✅ #########发送邮件成功，时间：%s; cc=%s", now_str, cc_list if cc_list else "[]")

        # 如果你希望把 CC 也落到钉钉表单，可以加一个字段（文本拼接）
        cc_text = ", ".join(cc_list) if cc_list else ""

        create_yida_form_instance(
            access_token=get_dingtalk_access_token(),
            user_id=os.getenv("USER_ID"),
            app_type=os.getenv("APP_TYPE"),
            system_token=os.getenv("SYSTEM_TOKEN"),
            form_uuid=os.getenv("FORM_UUID"),
            form_data={
                "textField_m8sdofy7": getattr(to_company, "company_name", to),
                "textField_m8sdofy8": getattr(from_company, "company_name", smtp_config["from"]),
                "textfield_G00FCbMy": subject,
                "editorField_m8sdofy9": body,
                "radioField_manpa6yh": "发送成功",
                "textField_mbyq9ksm": now_str,
                "textField_mbyq9ksn": now_str,
                "textField_mc8eps0i": stage,
                # 如需展示 CC，可在钉钉表单里新增一个文本字段并替换成真实字段ID
                # "textField_cc_list": cc_text,
            }
        )

        return True, ""
    except Exception as e:
        logger.exception("❌ send_email 执行失败，异常如下：")
        return False, str(e)


def send_email_in_main(to: str, subject: str, body: str, smtp_config: dict):
    message = EmailMessage()
    message["From"] = smtp_config["from"]
    message["To"] = to
    message["Subject"] = subject
    message.add_alternative(body, subtype="html")

    try:
        with smtplib.SMTP_SSL(smtp_config["host"], smtp_config["port"]) as smtp:
            smtp.login(smtp_config["username"], smtp_config["password"])
            smtp.send_message(message)

            return True, ""
    except Exception as e:
        return False, str(e)


# 发送带附件的邮件

def send_email_with_attachments(
    to_email: str,
    subject: str,
    content: str,
    smtp_config: dict,
    attachments: list[str],
    stage: str,
    cc: Optional[Union[str, Iterable[str]]] = None,  # ← 新增
):
    message = MIMEMultipart()
    message["From"] = smtp_config["from"]
    message["To"] = to_email
    message["Subject"] = subject

    cc_list = _normalize_cc(cc)
    if cc_list:
        message["Cc"] = ", ".join(cc_list)

    # 添加正文
    message.attach(MIMEText(content, "html", "utf-8"))

    with get_db_session() as db:
        from_company = db.query(models.CompanyInfo).filter(models.CompanyInfo.email == smtp_config["from"]).first()
        to_company = db.query(models.CompanyInfo).filter(models.CompanyInfo.email == to_email).first()

    # 添加附件
    if not attachments:
        logger.warning("📎 未提供任何附件，跳过附件处理")
    else:
        for file_path in attachments:
            try:
                with open(file_path, "rb") as f:
                    part = MIMEApplication(f.read())
                    part.add_header("Content-Disposition", "attachment", filename=os.path.basename(file_path))
                    message.attach(part)
            except Exception as e:
                return False, f"附件读取失败: {file_path}，错误信息：{str(e)}"

    try:
        logger.info("📧 开始建立 SMTP 连接")
        with smtplib.SMTP_SSL(smtp_config["host"], smtp_config["port"], timeout=30) as server:
            server.login(smtp_config["username"], smtp_config["password"])
            # 收件人列表必须包含 To + Cc
            recipients = [to_email] + cc_list
            server.sendmail(smtp_config["from"], recipients, message.as_string())

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        logger.info("✅ #########发送邮件成功，时间：%s, 抄送=%s", now_str, cc_list if cc_list else "[]")

        create_yida_form_instance(
            access_token=get_dingtalk_access_token(),
            user_id=os.getenv("USER_ID"),
            app_type=os.getenv("APP_TYPE"),
            system_token=os.getenv("SYSTEM_TOKEN"),
            form_uuid=os.getenv("FORM_UUID"),
            form_data={
                "textField_m8sdofy7": getattr(to_company, "company_name", to_email),
                "textField_m8sdofy8": getattr(from_company, "company_name", smtp_config["from"]),
                "textfield_G00FCbMy": subject,
                "editorField_m8sdofy9": content,
                "radioField_manpa6yh": "发送成功",
                "textField_mbyq9ksm": now_str,
                "textField_mbyq9ksn": now_str,
                "textField_mc8eps0i": stage,
                # 如需记录抄送人，可加一个字段： "textField_cc": ", ".join(cc_list)
            }
        )

        return True, ""
    except Exception as e:
        logger.exception("❌ send_email_with_attachments 执行失败")
        return False, str(e)


# 获取对应公司邮件发送标题
# 1. 邮件阶段
# 2. 公司简称
# 3. 项目名称
# 4. 对应公司流水号
# 5. 中标金额
# 6. 具体合同号
# 7. 中标时间
def render_email_subject(
    stage: str | None = None,  # 阶段
    company_short_name: str | None = None, # 公司简称
    project_name: str | None = None, # 项目名称
    serial_number: str | None = None, # 流水号
    contract_number: str | None = None, # 具体合同号
    winning_amount: str | None = None, # 中标金额
    winning_time: str | None = None, # 中标时间
    tender_number: str | None = None, # 招标编号
    purchase_department: str | None = None # 采购单位
) -> str: # 中标时间
    # 从数据库中获取标题模板
    
    with get_db_session() as db:
        subject = db.query(models.EmailSubject).filter(
            models.EmailSubject.stage == stage,
            models.EmailSubject.short_name == company_short_name,
            # models.EmailSubject.project_name == project_name,
        ).first()

        if not subject:
            return f"{stage}_{company_short_name}_{project_name}"
        
        return subject.subject.format(
            company_name=subject.company_name or "",
            short_name=subject.short_name or "",
            project_name=project_name or "",
            serial_number=serial_number or "",
            contract_number=contract_number or "",
            contract_amount=winning_amount or "",
            winning_time=winning_time or "",
            tender_number=tender_number or "", 
            purchase_department=purchase_department or ""
        )



# 获取对应公司邮件模板并渲染内容
# 可能需要的参数：
# project_name 项目名称
# serial_number 流水号
# first_name 公司负责人姓氏
# winning_amount 中标金额
# contract_number 具体合同编号
# buyer_name 中标商名称
# winning_time 中标时间

def render_invitation_template_content(
    buyer_name: str | None = None,
    project_name: str | None = None,
    serial_number: str | None = None,
    first_name: str | None = None,
    full_name: str | None = None,
    winning_amount: str | None = None,
    contract_number: str | None = None,
    winning_time: str | None = None,
    template_name: str | None = None,
    c_company_name: str | None = None,
    company_name: str | None = None,
    contact_person: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    address: str | None = None,
    english_address: str | None = None,
    pingyin: str | None = None,
    company_en: str | None = None,
):
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    template_dir = os.path.join(base_dir, "app", "email_templates")

    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(['html', 'xml'])  # 自动转义 HTML
    )

    template = env.get_template(template_name)  # 例如 "bidding_invite.html"
    return template.render(
        buyer_name=buyer_name, 
        winning_time=winning_time,
        project_name=project_name,
        serial_number=serial_number,
        first_name=first_name,
        full_name=full_name,
        winning_amount=winning_amount,
        contract_number=contract_number,
        c_company_name=c_company_name,
        company_name=company_name,
        contact_person=contact_person,
        phone=phone,
        email=email,
        address=address,
        english_address=english_address,
        pingyin=pingyin,
        company_en=company_en,
    )
    

    





