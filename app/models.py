from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, TIMESTAMP, DECIMAL, Date, ForeignKey, func
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, timezone

Base = declarative_base()

class EmailRecord(Base):
    __tablename__ = "emails_records"

    id = Column(Integer, primary_key=True, index=True)
    to = Column(String(255), nullable=False)
    subject = Column(String(255))
    body = Column(Text)
    status = Column(String(20), default="pending")  # pending / success / failed
    task_id = Column(String(100))  # ✅ 新增字段，用于记录 Celery 任务ID
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    error_message = Column(Text, nullable=True)
    project_id = Column(Integer)
    stage = Column(String(12))  
    actual_sending_time = Column(DateTime, nullable=True)
    

class CompanyInfo(Base):
    __tablename__ = "company_info"

    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String(255), nullable=False)       # 公司全称
    company_type = Column(String(100))                       # 公司类型
    short_name = Column(String(100))                         # 简称
    contact_person = Column(String(100))                     # 联系人
    last_name = Column(String(100))                          # 姓氏
    last_name_traditional = Column(String(100))              # 姓氏繁体
    phone = Column(String(100))                             # 电话
    email = Column(String(255))                              # 邮箱
    address = Column(String(255))                            # 中文地址
    english_address = Column(String(255))                    # 英文地址
    smtp_host = Column(String(255))                          # SMTP 服务器
    smtp_port = Column(Integer)                              # SMTP 端口
    smtp_username = Column(String(255))                      # SMTP 用户名
    smtp_password = Column(String(255))                      # SMTP 密码
    smtp_from = Column(String(255))                          # SMTP 发件人
    pingyin = Column(String(255))
    company_en = Column(String(255)) # 公司英文名


class ProjectInfo(Base):
    __tablename__ = "project_info"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_name = Column(String(255))
    contract_number = Column(String(100))
    tender_number = Column(String(100)) # 招标编号
    serial_number = Column(String(100)) # 流水号
    project_type = Column(String(100))  # BCD, CCD, BD
    # project_stage = Column(String(12)) # A, B, C
    p_serial_number = Column(String(100))
    l_serial_number = Column(String(100))
    f_serial_number = Column(String(100))
    purchaser = Column(String(255))
    company_b_name = Column(String(255))
    company_c_name = Column(String(255))
    company_d_name = Column(String(255))
    a1 = Column(Boolean)
    a2 = Column(Boolean)
    b3 = Column(Boolean)
    b4 = Column(Boolean)
    b5 = Column(Boolean)
    b6 = Column(Boolean)
    c7 = Column(Boolean)
    c8 = Column(Boolean)
    c9 = Column(Boolean)
    c10 = Column(Boolean)
    created_at = Column(TIMESTAMP, default=datetime.now(timezone.utc)) # UTC时间

    fee_details = relationship("ProjectFeeDetails", back_populates="project", uselist=False, cascade="all, delete")

# 邮件标题表
class EmailSubject(Base):

    __tablename__ = "email_subject"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    stage = Column(String(12))
    company_name = Column(String(255))
    short_name = Column(String(100))
    subject = Column(String(255))
    created_at = Column(TIMESTAMP, default=datetime.now(timezone.utc))
    # UTC时间
    subject = Column(String(255))
    created_at = Column(TIMESTAMP, default=datetime.now(timezone.utc))
    # UTC时间


# 项目费用明细表
class ProjectFeeDetails(Base):
    __tablename__ = "project_fee_details"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 外键：关联项目表
    project_id = Column(Integer, ForeignKey("project_info.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False, unique=True)

    # 中标信息
    winning_time = Column(Date, nullable=True)                      # 中标时间
    winning_amount = Column(DECIMAL(15, 2), nullable=True)          # 中标金额

    # 各类费用
    three_fourth_amount = Column(DECIMAL(15, 2), nullable=True)     # 三方/四方货款
    import_service_fee = Column(DECIMAL(15, 2), nullable=True)      # 进口服务费
    third_party_fee = Column(DECIMAL(15, 2), nullable=True)         # 第三方费用
    settlement_service_fee = Column(DECIMAL(15, 2), nullable=True)  # 费用结算服务费
    bidding_service_fee = Column(DECIMAL(15, 2), nullable=True)     # 中标服务费
    document_purchase_fee = Column(DECIMAL(15, 2), nullable=True)   # 购买标书费
    tender_service_fee = Column(DECIMAL(15, 2), nullable=True)      # 投标服务费

    # 是否发送过结算单
    is_sent = Column(Boolean, default=False, nullable=False)

    # 时间戳
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # 可选：反向关系（如果你在 ProjectInfo 模型中定义了 relationship）
    project = relationship("ProjectInfo", back_populates="fee_details")