# app/schemas.py
from datetime import datetime

from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional, List



class CompanyCreate(BaseModel):
    company_name: str
    company_type: Optional[str] = None
    company_alias: Optional[str] = None
    contact_person: Optional[str] = None
    last_name: Optional[str] = None
    last_name_tc: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    address_en: Optional[str] = None

class CompanyInfoOut(CompanyCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)


class ProjectInfoOut(BaseModel):
    id: int
    project_name: Optional[str]
    contract_number: Optional[str]
    tender_number: Optional[str]
    project_type: Optional[str]
    p_serial_number: Optional[str]
    l_serial_number: Optional[str]
    f_serial_number: Optional[str]
    purchaser: Optional[str]
    company_b_name: Optional[str]
    company_c_name: Optional[str]
    company_d_name: Optional[str]
    a1: Optional[bool]
    a2: Optional[bool]
    b3: Optional[bool]
    b4: Optional[bool]
    b5: Optional[bool]
    b6: Optional[bool]
    c7: Optional[bool]
    c8: Optional[bool]
    c9: Optional[bool]
    c10: Optional[bool]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)



# EmailSubjectOut

class EmailSubjectOut(BaseModel):
    id: int  # 主键，自增，通常由数据库生成
    stage: str  # 阶段，如 first, reply 等
    company_name: str  # 公司全名
    short_name: str  # 公司简称
    subject: str  # 可用于 Python 格式化的文本
    created_at: datetime  # 创建时间，由数据库默认生成

    model_config = ConfigDict(from_attributes=True)

'''
Step 1
委托投标登记请求：采购单位，项目名称，流水号，招标编号, B公司名称
'''
class BiddingRegisterRequest(BaseModel):
    purchase_department: str # 采购单位
    b_company_name: str # B公司名称
    project_name: str # 项目名称
    l_serial_number: str # L流水号
    p_serial_number: str # P流水号
    f_serial_number: str # F流水号
    bidding_code: Optional[str] = None # 招标编号


''' 
Step 2
项目中标信息
# 接收参数：
#     1. 项目名称
#     2. L流水号，P流水号，F流水号
#     3. 招标编号
#     4. 合同号
'''
class ProjectWinningInfoRequest(BaseModel):
    project_name: str # 项目名称
    l_serial_number: str # L流水号
    p_serial_number: str # P流水号
    f_serial_number: str # F流水号
    bidding_code: str # 招标编号
    contract_number: str # 合同号


''' 
Step 3
合同审批
    1. 项目名称
    2. L流水号，P流水号，F流水号
    3. 合同号
    4. B公司-中标商
    5. C公司 C=列表-合同类型（货款收付控制---不含供应商两方采购合同）中，合同类型=三方/四方合同，且收付控制=付的付款方
    6. D公司 D=列表-合同类型（货款收付控制---不含供应商两方采购合同）中，合同类型=三方/四方合同，且收付控制=付的付款方
    7. 合同类型
'''
class ContractAuditRequest(BaseModel):
    project_name: str # 项目名称
    l_serial_number: str # L流水号
    p_serial_number: str # P流水号
    f_serial_number: str # F流水号
    contract_number: str # 合同号
    contract_serial_number: str # 合同流水号
    company_b_name: str # B公司-中标商
    company_c_name: str # C公司
    company_d_name: str # D公司
    contract_type: str # 合同类型


class SettlementRequest(BaseModel):
    project_name: str # 项目名称
    l_serial_number: str # L流水号
    p_serial_number: str # P流水号
    f_serial_number: str # F流水号
    contract_number: str # 合同号
    contract_serial_number: str # 合同流水号
    company_b_name: str # B公司-中标商
    company_c_name: str # C公司
    company_d_name: str # D公司
    contract_type: str # 合同类型