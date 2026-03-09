
# app/tasks.py
# 处理B公司回复邮件的任务
import os 
import random
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.message import EmailMessage
import traceback
from typing import List, Optional, Union, Iterable

import paramiko

from celery import Celery, Task
from celery.exceptions import MaxRetriesExceededError
from app import email_utils, models

import logging

from dotenv import load_dotenv
load_dotenv()

# 配置日志输出到控制台和文件
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # 控制台输出
        logging.FileHandler('logs/celery_tasks.log', encoding='utf-8')  # 文件输出
    ]
)

logger = logging.getLogger(__name__)

celery = Celery( 
    "syjz_emails",
    broker="redis://localhost:6379/0",      # Redis 作为 broker
    backend="redis://localhost:6379/0"      # 可用于任务结果存储（可选）
)

class EmailSendFailed(Exception):
    """自定义异常：表示邮件逻辑上发送失败"""
    pass


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
    followup_task_args: dict | None = None,
    followup_delay: int = 0,
    cc: Optional[Union[str, Iterable[str]]] = None, 
):
    from app import database
    db = database.SessionLocal()

    try:
        logger.info(f"[{stage}] 🚀 发送邮件任务开始，to={to_email}")
        cc_list = _normalize_cc(cc)
        logger.info(f"[{stage}] 🚀 发送邮件任务开始，to={to_email}, cc={cc_list or '[]'}")
        
        success, error = email_utils.send_email(to_email, subject, content, smtp_config, stage, cc=cc_list)
        scheduled_time = datetime.now()

        if not success:
            logger.warning(f"[{stage}] ❌ 邮件发送失败，将重试：{error}")
            raise EmailSendFailed(error)

        # 如果成功且有后续任务，调度之
        if followup_task_args:
            # 从 followup_task_args 中提取自己的 delay，不用 A1 的
            next_delay = followup_task_args.pop("followup_delay", 60)
            logger.info(
                f"[{stage}] 🕐 调度 followup 任务（下一阶段 {followup_task_args.get('stage')}），延迟 {next_delay} 秒"
            )
            send_email_with_followup_delay.apply_async(
                kwargs=followup_task_args,
                countdown=next_delay
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


@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def send_reply_email_with_attachments_delay(
    self,
    to_email: str,
    subject: str,
    content: str,
    smtp_config: dict,
    attachments: list[str] | None = None,
    stage: str = "",
    project_id: int = 0,
    followup_task_args: dict | None = None,
    followup_delay: int = 0,
    cc: Optional[Union[str, Iterable[str]]] = None,
):
    from app import database
    db = database.SessionLocal()

    # 获取当前重试次数
    retry_count = self.request.retries
    task_id = self.request.id

    try:
        logger.info("=" * 60)
        logger.info(f"[{stage}] 📋 ========== 任务开始 ==========")
        logger.info(f"[{stage}] 📋 Task ID: {task_id}")
        logger.info(f"[{stage}] 📋 收件人: {to_email}")
        logger.info(f"[{stage}] 📋 主题: {subject[:50]}..." if len(subject) > 50 else f"[{stage}] 📋 主题: {subject}")
        logger.info(f"[{stage}] 📋 附件数: {len(attachments) if attachments else 0}")
        logger.info(f"[{stage}] 📋 重试次数: {retry_count}/3")
        if followup_task_args:
            logger.info(f"[{stage}] 📋 后续任务: {followup_task_args.get('stage')}, 延迟: {followup_delay}秒")
            logger.info(f"[{stage}] 📋 followup_task_args包含的键: {list(followup_task_args.keys())}")
        logger.info("=" * 60)

        logger.info(f"[{stage}] 📧 开始发送邮件...")
        success, error = email_utils.send_email_with_attachments(
            to_email, subject, content, smtp_config, attachments, stage, cc=cc
        )

        if not success:
            logger.warning(f"[{stage}] ❌ 带附件邮件发送失败，将重试：{error}")
            logger.warning(f"[{stage}] 🔄 准备进行第 {retry_count + 1} 次重试...")
            raise EmailSendFailed(error)

        logger.info(f"[{stage}] ✅ SMTP 邮件发送成功！")
        logger.info(f"[{stage}] ✅ 钉钉表单创建成功！")

        # 调度后续任务（若有）
        if followup_task_args:
            logger.info(f"[{stage}] 🔍 检测到后续任务，准备调度...")
            logger.info(f"[{stage}] 🔍 followup_task_args类型: {type(followup_task_args)}")
            logger.info(f"[{stage}] 🔍 followup_task_args内容: {followup_task_args}")

            next_stage = followup_task_args.get('stage')
            next_to = followup_task_args.get('to_email')

            logger.info(f"[{stage}] 🔍 准备pop followup_delay...")
            logger.info(f"[{stage}] 🔍 pop前的keys: {list(followup_task_args.keys())}")
            next_delay = followup_task_args.pop("followup_delay", 60)
            logger.info(f"[{stage}] 🔍 pop后的keys: {list(followup_task_args.keys())}")
            logger.info(f"[{stage}] 🔍 获取到的next_delay: {next_delay}")

            logger.info("=" * 60)
            logger.info(f"[{stage}] 📤 ========== 调度后续任务 ==========")
            logger.info(f"[{stage}] 📤 下一阶段: {next_stage}")
            logger.info(f"[{stage}] 📤 目标收件人: {next_to}")
            logger.info(f"[{stage}] 📤 延迟时间: {next_delay} 秒 ({next_delay // 60} 分钟)")
            logger.info(f"[{stage}] 📤 调度参数: {list(followup_task_args.keys())}")
            logger.info("=" * 60)

            try:
                logger.info(f"[{stage}] 🚀 开始调用apply_async...")
                result = send_reply_email_with_attachments_delay.apply_async(
                    kwargs=followup_task_args,
                    countdown=next_delay
                )
                logger.info(f"[{stage}] ✅ 后续任务 {next_stage} 调度成功！Task ID: {result.id}")
            except Exception as e:
                logger.error(f"[{stage}] ❌ 调度后续任务失败：{e}")
                logger.exception(f"[{stage}] 详细错误信息：")
                logger.error(f"[{stage}] ⚠️ 注意：后续任务调度失败，但当前任务将继续完成")
        else:
            logger.info(f"[{stage}] ℹ️ 无后续任务，流程结束")

        logger.info("=" * 60)
        logger.info(f"[{stage}] ✅✅✅ 带附件邮件任务全部完成 ✅✅✅")
        logger.info("=" * 60)
        return {"success": True, "error": ""}

    except EmailSendFailed as e:
        db.rollback()
        logger.warning("=" * 60)
        logger.warning(f"[{stage}] ❌ ========== 邮件逻辑失败 ==========")
        logger.warning(f"[{stage}] ❌ Task ID: {task_id}")
        logger.warning(f"[{stage}] ❌ 错误信息: {e}")
        logger.warning(f"[{stage}] 🔄 当前重试次数: {retry_count}/3")
        logger.warning("=" * 60)
        try:
            logger.warning(f"[{stage}] 🔄 触发重试...")
            raise self.retry(exc=e)
        except MaxRetriesExceededError:
            logger.error("=" * 60)
            logger.error(f"[{stage}] ❌❌❌ 达到最大重试次数（逻辑失败）❌❌❌")
            logger.error(f"[{stage}] ❌ Task ID: {task_id}")
            logger.error(f"[{stage}] ❌ 最终错误: {e}")
            logger.error("=" * 60)
            return {"success": False, "error": str(e)}

    except Exception as e:
        db.rollback()
        logger.error("=" * 60)
        logger.error(f"[{stage}] ❌ ========== 系统异常 ==========")
        logger.error(f"[{stage}] ❌ Task ID: {task_id}")
        logger.error(f"[{stage}] ❌ 异常类型: {type(e).__name__}")
        logger.error(f"[{stage}] ❌ 异常信息: {e}")
        logger.exception(f"[{stage}] 完整堆栈:")
        logger.error("=" * 60)
        try:
            logger.error(f"[{stage}] 🔄 触发重试...")
            raise self.retry(exc=e)
        except MaxRetriesExceededError:
            logger.error(f"[{stage}] ❌❌❌ 达到最大重试次数（系统异常）❌❌❌")
            logger.error(f"[{stage}] ❌ 最终错误: {e}")
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

    remote_path = f"财务部/中港模式结算单/{filename}"  # 你可以灵活改成传参

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


@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def send_notification_email_task(self, stage: str, body: str, to: str) -> tuple[bool, str]:
    
    """
    发送通知邮件（网易163邮箱示例）
    """
    message = EmailMessage()
    message["From"] = "peterlcylove@163.com"
    message["To"] = to
    message["Subject"] = stage
    message.add_alternative(body, subtype="html")

    smtp_config = {
        "host": "smtp.163.com",
        "port": 465,  # 465 用 SSL
        "username": "peterlcylove@163.com",
        "password": "FFSKF6Z39NFDx2WD",  # 163 邮箱授权码
    }

    try:
        # 465 端口用 SMTP_SSL
        with smtplib.SMTP_SSL(smtp_config["host"], smtp_config["port"]) as smtp:
            smtp.login(smtp_config["username"], smtp_config["password"])
            smtp.send_message(message)
            return True, "发送成功"

    except Exception as e:
        # 输出完整错误堆栈，方便排查
        err_detail = traceback.format_exc()
        return False, f"{type(e).__name__}: {e}\n{err_detail}"
