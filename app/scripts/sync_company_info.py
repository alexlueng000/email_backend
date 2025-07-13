"""

1. 读取company_info表中的所有wc公司信息，写到宜搭中
2. 接收宜搭传过来的公司信息，更新到company_info表中

"""
import os

from app import database, models
from app.utils import get_dingtalk_access_token,create_yida_form_instance

from dotenv import load_dotenv


load_dotenv()

def sync_company_info():
    
    # 1. 读取company_info表中的所有公司信息，写到宜搭中
    db = database.SessionLocal()
    company_infos = db.query(models.CompanyInfo).all()

    # 打印公司信息
    print("✅ 打印公司信息")
    for company_info in company_infos:
        print(company_info.company_name)

    for company_info in company_infos:
        create_yida_form_instance(
            access_token=get_dingtalk_access_token(),
            user_id=os.getenv("USER_ID"),
            app_type=os.getenv("COMPANY_INFO_APP_TYPE"),
            system_token=os.getenv("COMPANY_INFO_SYSTEM_TOKEN"),
            form_uuid=os.getenv("COMPANY_INFO_FORM_UUID"),
            form_data={
                "selectField_md18jaro": company_info.company_type, # 公司类型
                "textField_md18jark": company_info.company_name, # 公司名称
                "textField_md18jary": company_info.short_name, # 公司简称
                "textField_md18jarz": company_info.contact_person, # 联系人
                "textField_md18jas0": company_info.last_name, # 姓
                "textField_md18jas1": company_info.last_name_traditional, # 繁体
                "textField_md18jase": company_info.phone, # 电话
                "textField_md18jasf": company_info.email, # 邮箱
                "textField_md18jash": company_info.address, # 地址
                "textField_md18jasj": company_info.english_address, # 英文地址
            }
        )