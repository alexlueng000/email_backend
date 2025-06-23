
# app/tasks.py
# 处理B公司回复邮件的任务

import time
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText

from celery import Celery
from sqlalchemy.orm import Session
from app import email_utils, models, database


celery = Celery(
    "syjz_emails",
    broker="redis://localhost:6379/0",      # Redis 作为 broker
    backend="redis://localhost:6379/0"      # 可用于任务结果存储（可选）
)


def send_sync_email(to_email, subject, content, smtp_config):
    msg = MIMEText(content, "html", "utf-8")
    msg["From"] = smtp_config["from"]
    msg["To"] = to_email
    msg["Subject"] = subject

    try:
        server = smtplib.SMTP_SSL(smtp_config["host"], smtp_config["port"])
        server.login(smtp_config["username"], smtp_config["password"])
        server.sendmail(smtp_config["from"], [to_email], msg.as_string())
        server.quit()
        return True, ""
    except Exception as e:
        return False, str(e)


@celery.task
def send_reply_email(to_email: str, subject: str, content: str, smtp_config: dict, delay: int, stage: str, project_id: int):
    from app import database
    db = database.SessionLocal()

    # 当前时间 + delay 秒 = 实际发送时间
    scheduled_time = datetime.now() + timedelta(seconds=delay)
    try:
        print("send_reply_email$$$$$$$$$$$$$$$$$")
        success, error = email_utils.send_email(to_email, subject, content, smtp_config, stage)
    except Exception as e:
        success = False
        error = str(e)
        print(f"[邮件发送异常] to={to_email}, subject={subject}, error={error}")
    
    # 需要更新这个邮件发送记录
    record = models.EmailRecord(
        to=to_email,
        subject=subject,
        body=content,
        status="success" if success else "failed",
        error_message=error if not success else None,
        actual_sending_time=scheduled_time,
        stage=stage,
        project_id=project_id
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"success": success, "error": error}



@celery.task
def send_reply_email_with_attachments(
    to_email: str, 
    subject: str, 
    content: str, 
    smtp_config: dict, 
    attachments: list[str], 
    delay: int, 
    stage: str, 
    project_id: int
    ):
    from app import database
    db = database.SessionLocal()

    # 当前时间 + delay 秒 = 实际发送时间
    scheduled_time = datetime.now() + timedelta(seconds=delay)

    success, error = email_utils.send_email_with_attachments(to_email, subject, content, smtp_config, attachments, stage)
    
    # 需要更新这个邮件发送记录
    record = models.EmailRecord(
        to=to_email,
        subject=subject,
        body=content,
        status="success" if success else "failed",
        error_message=error if not success else None,
        actual_sending_time=scheduled_time,
        stage=stage,
        project_id=project_id
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"success": success, "error": error}