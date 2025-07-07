
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

class EmailSendFailed(Exception):
    """自定义异常：表示邮件逻辑上发送失败"""
    pass


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
def send_reply_email(self, to_email: str, subject: str, content: str, smtp_config: dict, delay: int, stage: str, project_id: int):
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
    followup_delay_min: int = 300,
    followup_delay_max: int = 3600
):
    from app import database
    db = database.SessionLocal()

    try:
        logger.info(f"[{stage}] 🚀 发送邮件任务开始，to={to_email}")
        
        success, error = email_utils.send_email(to_email, subject, content, smtp_config, stage)
        scheduled_time = datetime.now()

        # 保存发送记录
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

        if not success:
            logger.warning(f"[{stage}] ❌ 邮件发送失败，将重试：{error}")
            raise EmailSendFailed(error)

        # 如果成功且有后续任务，调度之
        if followup_task_args:
            delay = random.randint(followup_delay_min, followup_delay_max)
            logger.info(f"[{stage}] 🕐 调度 followup 任务，延迟 {delay} 秒")
            send_email_with_followup.apply_async(
                kwargs=followup_task_args,
                # countdown=delay
                countdown=1*60
            )

        logger.info(f"[{stage}] ✅ 邮件发送任务成功完成")
    except EmailSendFailed as e:
        db.rollback()
        try:
            logger.warning(f"[{stage}] 重试中（逻辑失败）：{e}")
            raise self.retry(exc=e)
        except MaxRetriesExceededError:
            logger.error(f"[{stage}] 达到最大重试次数（逻辑失败）：{e}")
    except Exception as e:
        db.rollback()
        logger.exception(f"[{stage}] ❌ 邮件任务异常，将重试：{e}")
        try:
            raise self.retry(exc=e)
        except MaxRetriesExceededError:
            logger.error(f"[{stage}] 达到最大重试次数（系统异常）：{e}")
    finally:
        db.close()


@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def send_email_with_followup_delay(
    self,
    to_email: str,
    subject: str,
    content: str,
    smtp_config: dict,
    stage: str,
    project_id: int,
    followup_task_args: dict | None = None,
    followup_delay: int = 0
):
    from app import database
    db = database.SessionLocal()

    try:
        logger.info(f"[{stage}] 🚀 发送邮件任务开始，to={to_email}")
        
        success, error = email_utils.send_email(to_email, subject, content, smtp_config, stage)
        scheduled_time = datetime.now()

        # 保存发送记录
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

        if not success:
            logger.warning(f"[{stage}] ❌ 邮件发送失败，将重试：{error}")
            raise EmailSendFailed(error)

        # 如果成功且有后续任务，调度之
        if followup_task_args:
            # delay = random.randint(followup_delay_min, followup_delay_max)
            logger.info(f"[{stage}] 🕐 调度 followup 任务，延迟 {followup_delay} 秒")
            send_email_with_followup.apply_async(
                kwargs=followup_task_args,
                # countdown=delay
                countdown=followup_delay
            )

        logger.info(f"[{stage}] ✅ 邮件发送任务成功完成")
    except EmailSendFailed as e:
        db.rollback()
        try:
            logger.warning(f"[{stage}] 重试中（逻辑失败）：{e}")
            raise self.retry(exc=e)
        except MaxRetriesExceededError:
            logger.error(f"[{stage}] 达到最大重试次数（逻辑失败）：{e}")
    except Exception as e:
        db.rollback()
        logger.exception(f"[{stage}] ❌ 邮件任务异常，将重试：{e}")
        try:
            raise self.retry(exc=e)
        except MaxRetriesExceededError:
            logger.error(f"[{stage}] 达到最大重试次数（系统异常）：{e}")
    finally:
        db.close()


@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def send_reply_email_with_attachments(
    self,
    to_email: str,
    subject: str,
    content: str,
    smtp_config: dict,
    attachments: list[str] | None = None,
    # delay: int = 0,
    stage: str = "",
    project_id: int = 0,
    followup_task_args: dict | None = None,
    followup_delay_min: int = 300,
    followup_delay_max: int = 3600
):
    from app import database
    db = database.SessionLocal()
    # scheduled_time = datetime.now() + timedelta(seconds=delay)

    try:
        logger.info(f"[{stage}] 📎 开始发送带附件邮件，to={to_email}, 附件数={len(attachments) if attachments else 0}")

        success, error = email_utils.send_email_with_attachments(
            to_email, subject, content, smtp_config, attachments, stage
        )

        # 保存记录
        record = models.EmailRecord(
            to=to_email,
            subject=subject,
            body=content,
            status="success" if success else "failed",
            error_message=error if not success else None,
            actual_sending_time=datetime.now(),
            stage=stage,
            project_id=project_id
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        if not success:
            logger.warning(f"[{stage}] ❌ 带附件邮件发送失败，将重试：{error}")
            raise EmailSendFailed(error)

        # 派发后续任务
        if followup_task_args:
            followup_delay = random.randint(followup_delay_min, followup_delay_max)
            logger.info(f"[{stage}] 🕐 调度 followup 任务，延迟 {followup_delay} 秒")
            send_reply_email_with_attachments.apply_async(
                kwargs=followup_task_args,
                # countdown=followup_delay
                countdown=1*60
            )

        logger.info(f"[{stage}] ✅ 带附件邮件任务完成")
        return {"success": True, "error": ""}

    except EmailSendFailed as e:
        db.rollback()
        logger.warning(f"[{stage}] 📧 邮件逻辑失败，准备 retry：{e}")
        try:
            raise self.retry(exc=e)
        except MaxRetriesExceededError:
            logger.error(f"[{stage}] 📧 达到最大重试次数（逻辑失败）: {e}")
            return {"success": False, "error": str(e)}

    except Exception as e:
        db.rollback()
        logger.exception(f"[{stage}] ❌ 系统异常，将重试：")
        try:
            raise self.retry(exc=e)
        except MaxRetriesExceededError:
            logger.error(f"[{stage}] ❌ 达到最大重试次数（系统异常）: {e}")
            return {"success": False, "error": str(e)}

    finally:
        db.close()


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