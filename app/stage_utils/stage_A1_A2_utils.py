# ========= 抽取的通用工具 =========

from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from app import models, email_utils

import logger

# 统一把 CompanyInfo 转成 SMTP 配置
def smtp_from_company(c: "models.CompanyInfo") -> Dict[str, Any]:
    return {
        "host": c.smtp_host,
        "port": c.smtp_port,
        "username": c.smtp_username,
        "password": c.smtp_password,
        "from": c.smtp_from,
    }

# 按公司简称+类型拿公司（不存在就报错日志并返回 None）
def get_company_by_short(db: Session, short_name: str, company_type: str) -> Optional["models.CompanyInfo"]:
    company = (
        db.query(models.CompanyInfo)
        .filter(models.CompanyInfo.short_name == short_name,
                models.CompanyInfo.company_type == company_type)
        .first()
    )
    if not company:
        logger.error("未找到公司：short=%s, type=%s", short_name, company_type)
    return company

# 按公司名（可选限定类型）拿公司
def get_company_by_name(db: Session, company_name: str, company_type: Optional[str] = None) -> Optional["models.CompanyInfo"]:
    q = db.query(models.CompanyInfo).filter(models.CompanyInfo.company_name == company_name)
    if company_type:
        q = q.filter(models.CompanyInfo.company_type == company_type)
    company = q.first()
    if not company:
        logger.error("未找到公司：name=%s, type=%s", company_name, company_type or "*")
    return company

# 渲染“邀请/委托”邮件正文：把公司字段打包给模板
def render_invitation(
    *,
    project_name: str,
    template_name: str,
    buyer_name: Optional[str] = None,
    full_name: Optional[str] = None,      # 正文称呼
    signer_company: "models.CompanyInfo", # 落款公司（是谁发这封邮件）
) -> str:
    return email_utils.render_invitation_template_content(
        buyer_name=buyer_name,
        project_name=project_name,
        template_name=template_name,
        # 发送人落款信息（签名信息统一从 signer_company 带出）
        contact_person=signer_company.contact_person,
        company_name=signer_company.company_name,
        full_name=full_name or signer_company.contact_person,
        phone=signer_company.phone,
        email=signer_company.email,
        address=signer_company.address,
        english_address=signer_company.english_address,
        pingyin=getattr(signer_company, "pingyin", None),   # 与现有模板字段保持一致
        company_en=signer_company.company_en,
    )

# 组装通用 Celery 任务字典
def make_task(
    *,
    to_email: str,
    subject: str,
    content: str,
    smtp_config: Dict[str, Any],
    stage: str,
    followup_task_args: Optional[Dict[str, Any]] = None,
    followup_delay: Optional[int] = None,  # 注意：保持你原来的单位语义
) -> Dict[str, Any]:
    return {
        "to_email": to_email,
        "subject": subject,
        "content": content,
        "smtp_config": smtp_config,
        "stage": stage,
        "followup_task_args": followup_task_args,
        "followup_delay": followup_delay,
    }

# 规范化公司名（去掉不可见空白等）
def normalize_company_name(name: str) -> str:
    return name.replace("\xa0", "").strip()

# A2：使用 B 公司 SMTP，模板按 B 的短名切换
def make_a2_task_for_target_d(
    *,
    b_company: models.CompanyInfo,
    target_d: models.CompanyInfo,
    project_name: str,
    serial_number: str,       # 对应 F/L/P 号
    delay_minutes: int,       # 你原来是 randint(5, max_sending_time)
) -> Dict[str, Any]:
    template_name = f"A2_{b_company.short_name}.html"
    subject = email_utils.render_email_subject(
        stage="A2",
        company_short_name=b_company.short_name,
        project_name=project_name,
        serial_number=serial_number,
    )
    content = render_invitation(
        project_name=project_name,
        template_name=template_name,
        full_name=target_d.contact_person,  # A2 正文称呼对方
        signer_company=b_company,           # A2 由 B 公司发出，落款=B
    )
    return make_task(
        to_email=target_d.email,
        subject=subject,
        content=content,
        smtp_config=smtp_from_company(b_company),  # 用 B 的 SMTP
        stage="A2",
        followup_task_args=None,
        followup_delay=delay_minutes * 60,        # 沿用你原有：A2 followup_delay 用秒
    )

# A1：由 D 公司发，收件人固定是 B 公司
def make_a1_task_from_d_to_b(
    *,
    d_company: models.CompanyInfo,
    b_company: models.CompanyInfo,
    subject: str,
    template_name: str,
    buyer_name: str,
    project_name: str,
    a1_delay_minutes: int,             # 你原来是 1-5 分钟
    follow_a2_task: Dict[str, Any],    # A1 的 followup（即 A2）
) -> Dict[str, Any]:
    content = render_invitation(
        buyer_name=buyer_name,
        project_name=project_name,
        template_name=template_name,
        signer_company=d_company,            # A1 由 D 发出，落款=D
    )
    task = make_task(
        to_email=b_company.email,
        subject=subject,
        content=content,
        smtp_config=smtp_from_company(d_company),
        stage="A1",
        followup_task_args=follow_a2_task,
        followup_delay=a1_delay_minutes,     # 保持你原来的单位（不乘 60）
    )
    return task
