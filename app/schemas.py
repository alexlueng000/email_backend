# app/schemas.py
from datetime import datetime

from pydantic import BaseModel, EmailStr, ConfigDict, validator     
from typing import Optional, List, Union



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
    winning_amount: float # 中标金额
    winning_time: datetime  # 毫秒时间戳将被转为 datetime

    @validator("winning_time", pre=True)
    def parse_millisecond_timestamp(cls, v):
        try:
            ts = float(v)
            if ts > 1e12:  # 判断是否为毫秒级时间戳
                ts /= 1000
            return datetime.fromtimestamp(ts)
        except Exception:
            raise ValueError("winning_time 必须是有效的毫秒时间戳")


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

class ContractItem(BaseModel):
    numberField_l7ps2caa: Optional[str]
    radioField_lfafvypp: Optional[str]
    selectField_la4orihe: Optional[str]
    selectField_l7ps2ca3: Optional[str]
    numberField_leqpuqk4: Optional[str]
    selectField_l7ps2ca8: Optional[str]
    numberField_l7ps2ca9: Optional[str]
    selectField_l7ps2ca7: Optional[str]
    selectField_l7ps2ca6: Optional[str]
    numberField_lfafvypq: Optional[str]
    selectField_l7ps2ca5: Optional[str]




class ContractAuditRequest(BaseModel):
    project_name: str  # 项目名称
    l_serial_number: str  # L流水号
    p_serial_number: str  # P流水号
    f_serial_number: str  # F流水号
    contract_number: str  # 合同号
    contract_serial_number: str  # 合同流水号
    company_b_name: str  # B公司-中标商
    company_c_name: str  # C公司
    company_d_name: str  # D公司
    winning_amount: float  # 中标金额
    # winning_time: str  # 中标时间
    contracts: List[ContractItem]  # 合同数组

    # @validator("winning_time", pre=True)
    # def parse_millisecond_timestamp(cls, v):
    #     try:
    #         ts = float(v)
    #         if ts > 1e12:  # 判断是否为毫秒级时间戳
    #             ts /= 1000
    #         return datetime.fromtimestamp(ts)
    #     except Exception:
    #         raise ValueError("winning_time 必须是有效的毫秒时间戳")



# 结算
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
    amount: Union[str, float]
    three_fourth: Union[str, float]
    import_service_fee: Union[str, float]
    third_party_fee: Union[str, float]
    service_fee: Union[str, float]
    win_bidding_fee: Union[str, float]
    bidding_document_fee: Union[str, float]
    bidding_service_fee: Union[str, float]


    
