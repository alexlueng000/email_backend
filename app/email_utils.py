# app/email_utils.py
import os

from aiosmtplib import SMTP
import smtplib
import mimetypes
from email.message import EmailMessage

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

# from app.tasks import send_reply_email
from app import database, models

from jinja2 import Environment, FileSystemLoader, select_autoescape

from contextlib import contextmanager

@contextmanager
def get_db_session():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

def send_email(to, subject, body, smtp_config):
    print("✅ 执行同步 send_email 函数")
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
def send_email_with_attachments(to_email, subject, content, smtp_config, attachments):
    message = MIMEMultipart()
    message["From"] = smtp_config["from"]
    message["To"] = to_email
    message["Subject"] = subject

    # 添加正文
    message.attach(MIMEText(content, "html", "utf-8"))

    # 添加附件
    for file_path in attachments:
        try:
            with open(file_path, "rb") as f:
                part = MIMEApplication(f.read())
                part.add_header("Content-Disposition", "attachment", filename=os.path.basename(file_path))
                message.attach(part)
        except Exception as e:
            return False, f"附件读取失败: {file_path}，错误信息：{str(e)}"

    try:
        server = smtplib.SMTP_SSL(smtp_config["host"], smtp_config["port"])
        server.login(smtp_config["username"], smtp_config["password"])
        server.sendmail(smtp_config["from"], [to_email], message.as_string())
        server.quit()
        return True, ""
    except Exception as e:
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
    stage: str | None = None, 
    company_short_name: str | None = None, 
    project_name: str | None = None, 
    serial_number: str | None = None,
    contract_number: str | None = None,
    winning_amount: str | None = None,
    winning_time: str | None = None) -> str:
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
            company_name=subject.company_name,
            short_name=subject.short_name,
            project_name=project_name,
            serial_number=serial_number,
            tender_number=contract_number,
            contract_amount=winning_amount,
            winning_time=winning_time,
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
):

    print("template name000000000: ", template_name)
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    template_dir = os.path.join(base_dir, "app", "email_templates")
    print("template_dir: ", template_dir)

    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(['html', 'xml'])  # 自动转义 HTML
    )

    print("template_name: ", template_name)

    template = env.get_template(template_name)  # 例如 "bidding_invite.html"
    return template.render(
        buyer_name=buyer_name, 
        winning_time=winning_time,
        project_name=project_name,
        serial_number=serial_number,
        first_name=first_name,
        full_name=full_name,
        winning_amount=winning_amount,
        contract_number=contract_number)
    

    





