# ========= 抽取的通用工具 =========

from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from app import models, email_utils

from app.log_config import setup_logger

logger = setup_logger(__name__)

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

from typing import Optional
from sqlalchemy.orm import Session
from app import models, email_utils

from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app import models, email_utils

def update_D_company_by_alias(db: Session, alias: str) -> models.CompanyInfo:
    # 1) 选中要更新的 D 公司（你现在逻辑写死 PR，如需按 alias 选择可改 filter）
    company = (
        db.query(models.CompanyInfo)
        .filter(
            models.CompanyInfo.short_name == "PR",
            models.CompanyInfo.company_type == "D",
        )
        .first()
    )
    if not company:
        raise ValueError("未找到符合条件的 D 公司（short_name='PR', company_type='D'）。")

    # 2) 取发信账号配置（按别名 A/B/C）
    acc = email_utils.MAIL_ACCOUNTS.get(alias)
    if not acc:
        raise KeyError(f"MAIL_ACCOUNTS 中不存在别名：{alias}")

    # 3) 兼容老/新键名读取
    def getf(d, *keys, default=None):
        for k in keys:
            if k in d and d[k] not in (None, ""):
                return d[k]
        return default

    new_values = {
        "email": getf(acc, "email"),
        "smtp_host": getf(acc, "smtp_host", "host"),
        "smtp_port": int(getf(acc, "smtp_port", "port", default=465)),
        "smtp_username": getf(acc, "smtp_username", "username"),
        "smtp_password": getf(acc, "smtp_password", "password"),
        "smtp_from": getf(acc, "smtp_from", "from")
                    or getf(acc, "smtp_username", "username"),
    }

    # 4) 基本校验
    missing = [k for k, v in new_values.items() if not v]
    if missing:
        raise ValueError(f"别名 {alias} 的发信配置缺失字段：{', '.join(missing)}")

    # 5) 仅在值变化时赋值，减少无谓 UPDATE
    for k, v in new_values.items():
        if getattr(company, k, None) != v:
            setattr(company, k, v)

    # 6) 事务提交（失败回滚）
    try:
        db.flush()       # 先 flush 让 ORM 检查列是否存在/类型是否匹配
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    # 7) 刷新得到数据库中的最新值
    db.refresh(company)

    # 8) 打印脱敏信息（勿打印密码）
    print("D公司已更新（脱敏）=>", {
        "id": company.id,
        "short_name": company.short_name,
        "smtp_host": company.smtp_host,
        "smtp_port": company.smtp_port,
        "smtp_username": company.smtp_username,
        "smtp_from": company.smtp_from,
        # "smtp_password": "******"
    })

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
