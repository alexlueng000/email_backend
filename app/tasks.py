
# app/tasks.py
# 处理B公司回复邮件的任务
import os 
import random
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText


import paramiko

from celery import Celery, Task
from celery.exceptions import MaxRetriesExceededError
from app import email_utils, models

import logging

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

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


@celery.task(bind=True, max_retries=3, default_retry_delay=60)
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
    
    try:
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
    finally:
        db.close()
    return {"success": success, "error": error}


@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def send_email_with_followup(
    self,
    to_email: str,
    subject: str,
    content: str,
    smtp_config: dict,
    stage: str,
    project_id: int,
    followup_task_args: dict | None = None,
    followup_delay_min: int = 300,   # 最小延迟（单位秒）= 5 分钟
    followup_delay_max: int = 3600   # 最大延迟 = 60 分钟
):
    from app import database
    db = database.SessionLocal()
    try:
        # 1. 发送邮件
        success, error = email_utils.send_email(to_email, subject, content, smtp_config, stage)
        scheduled_time = datetime.now()
        
        # 2. 保存记录
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

        # 3. 如成功，调度后续任务（如果有）
        if success and followup_task_args:
            delay = random.randint(followup_delay_min, followup_delay_max)
            send_email_with_followup.apply_async(
                kwargs=followup_task_args,
                countdown=1*60
            )
    except Exception as e:
        db.rollback()
        logger.error(f"[{stage}] 邮件发送失败: {e}")
        try:
            self.retry(exc=e)
        except MaxRetriesExceededError:
            logger.error(f"[{stage}] 达到最大重试次数")
    finally:
        db.close()



@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def send_reply_email_with_attachments(
    self,
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

    scheduled_time = datetime.now() + timedelta(seconds=delay)

    try:
        success, error = email_utils.send_email_with_attachments(
            to_email, subject, content, smtp_config, attachments, stage
        )

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
    except Exception as e:
        # 如果邮件发送或数据库操作失败，也返回失败信息
        success = False
        error = str(e)
        print(f"[邮件发送异常] to={to_email}, subject={subject}, error={error}")
    finally:
        db.close()  # ✅ 无论如何都关闭连接

    return {"success": success, "error": error}


def ensure_remote_dir(sftp: paramiko.SFTPClient, remote_dir: str):
    dirs = remote_dir.strip("/").split("/")
    current = ""
    for d in dirs:
        current += f"/{d}"
        try:
            sftp.stat(current)
        except FileNotFoundError:
            sftp.mkdir(current)

@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def upload_file_to_sftp_task(self, local_file: str, filename: str) -> bool:
    """
    异步上传文件到 SFTP，remote_filename 是文件名（会放在根目录或你定义的子目录中）
    """
    host = os.getenv("SFTP_HOST")
    port = int(os.getenv("SFTP_PORT", "22"))
    username = os.getenv("SFTP_USER")
    password = os.getenv("SFTP_PASS")
    REMOTE_PATH = os.getenv("REMOTE_PATH")

    remote_path = f"JZ/中港模式结算单/{filename}"  # 你可以灵活改成传参

    local_file_path = os.path.expanduser(local_file)

    print("📂 上传文件：", local_file_path)
    print("📁 目标路径：", REMOTE_PATH + filename)

    try:
        transport = paramiko.Transport((host, port))
        transport.connect(username=username, password=password)
        print("✅ 连接成功")

        sftp = paramiko.SFTPClient.from_transport(transport)

        sftp.put(local_file_path, remote_path)
        print(f"✅ 文件上传成功：{remote_path}")

        sftp.close()
        transport.close()
        return True

    except Exception as e:
        print("❌ 上传失败:", str(e))
        return False