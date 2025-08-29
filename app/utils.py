# utils.py 各种工具函数
import os
import random
import json
import time
from datetime import datetime

import requests

from dotenv import load_dotenv
import logging
from opencc import OpenCC
import paramiko

load_dotenv()

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOKEN_FILE = os.path.join(BASE_DIR, "dingtalk_token.json")

logger = logging.getLogger(__name__)

now_str = datetime.now().strftime("%Y-%m-%d %H:%M")


# 生成3个5-60之间的随机数
def generate_random_number() -> list[int]:
    return [random.randint(5, 60) for _ in range(3)]


# 宜搭get access token
def get_dingtalk_access_token() -> str:
    # 尝试读取已有 token
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            data = json.load(f)
            if time.time() < data.get("expires_at", 0):
                print("✅ 使用缓存的 accessToken")
                return data["access_token"]

    # 缓存不存在或已过期，重新获取
    url = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "appKey": os.getenv("DINGTALK_APP_KEY"),
        "appSecret": os.getenv("DINGTALK_APP_SECRET")
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        res_data = response.json()
        access_token = res_data.get("accessToken")
        expire_in = res_data.get("expireIn", 7200)  # 默认 2 小时

        if access_token:
            print("✅ 成功获取新的 accessToken")
            with open(TOKEN_FILE, "w") as f:
                json.dump({
                    "access_token": access_token,
                    "expires_at": time.time() + expire_in - 60  # 提前 1 分钟过期
                }, f)
            return access_token
        else:
            print("⚠️ 获取失败，响应内容：", res_data)
            return None
    except requests.exceptions.RequestException as e:
        print("❌ 请求失败：", e)
        return None

# 更新宜搭邮件管理表单实例
def create_yida_form_instance(
    access_token: str,
    app_type: str,
    system_token: str,
    user_id: str,
    form_uuid: str,
    form_data: dict,
) -> dict:
    url = "https://api.dingtalk.com/v2.0/yida/forms/instances"
    headers = {
        "Content-Type": "application/json",
        "x-acs-dingtalk-access-token": access_token
    }

    payload = {
        "appType": app_type,
        "systemToken": system_token,
        "userId": user_id,
        "formUuid": form_uuid,
        "formDataJson": json.dumps(form_data, ensure_ascii=False),
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        data = response.json()

        # 判断是否成功（钉钉返回的业务字段）
        if response.status_code == 200 and data.get("result"):
            logger.info("✅ 表单创建成功，ID：%s", data["result"])
            return {"success": True, "formInstanceId": data["result"]}
        else:
            logger.error("⚠️ 表单创建失败，响应内容：%s", data)
            return {"success": False, "detail": data}

    except requests.exceptions.RequestException as e:
        logger.error("❌ 网络请求失败：%s", e)
        return {"success": False, "error": str(e)}


def update_project_info_company_D(contract_number: str, company_d_name: str) -> str:
    """
    access_token: x-acs-dingtalk-access-token
    system_token: 宜搭应用的 System Token（不是钉钉 appSecret）
    form_uuid:    FORM-xxxxx（宜搭表单UUID）
    user_id_type: "userId" | "openId" | "unionId"
    """

    access_token = get_dingtalk_access_token()

    headers = {
        "x-acs-dingtalk-access-token": access_token,
        "Content-Type": "application/json"
    }

    search_conditions = [{
        "key": "textField_ky9zhf07",
        "value": contract_number,
        "type": "TEXT",
        "operator": "eq",
        "componentName": "TextField"
        }]

    formDataJson = "{\"textField_mew98rlz\":[{\"value\":\"" + company_d_name + "\"}]}"

    body = {
        "appType": "APP_R55Z1QDKMB0VILUQRNJA",             # 固定为 APP（宜搭应用）
        "systemToken": "6Q866L81UPU4TY6NBOTYZBB28OUC3K1N7EM9LG91",  # 宜搭 System Token
        "formUuid": "FORM-TP866D91MJO5MFN08AMJGA8H52ZV3HPX6XRALD1",
        "dataCreateFrom": 0,          # 可选：0=全部；1=我创建；2=我参与
        "userId": "571848422",           # 这里换成有权限访问该宜搭应用/表单的用户
        "searchCondition": json.dumps(search_conditions, ensure_ascii=False),
        "formDataJson": formDataJson
     }

    try:
        resp = requests.post("https://api.dingtalk.com/v2.0/yida/forms/instances/insertOrUpdate", headers=headers, data=json.dumps(body))
        logger.info("✅ 回写项目信息表单，D公司更新成功，ID：%s", resp.json()["result"])
        return "更新表单成功"
    except requests.HTTPError as e:
        logger.error(f"❌ HTTP错误：{e}，响应：{getattr(e.response, 'text', '')}")
    except Exception as e:
        logger.error(f"❌ 请求失败：{e}")
    return "更新表单失败"



def simplify_to_traditional(text: str) -> str:
    """
    将简体中文转换为繁体中文。
    
    参数：
        text (str): 简体中文字符串。
        
    返回：
        str: 转换后的繁体中文字符串。
    """
    cc = OpenCC('s2t')  # s2t 表示 Simplified to Traditional
    return cc.convert(text)


def upload_file_to_sftp(local_file: str, filename: str) -> bool:
    """
    上传文件到 SFTP，连接配置从 .env 文件读取。
    
    参数：
        local_file (str): 本地文件路径
    
    返回：
        bool: 成功为 True，失败为 False
    """
    # 从环境变量读取配置
    host = os.getenv("SFTP_HOST")
    port = int(os.getenv("SFTP_PORT", "22"))
    username = os.getenv("SFTP_USERNAME")
    password = os.getenv("SFTP_PASSWORD")
    remote_path = os.getenv("REMOTE_PATH")

    print("📂 上传文件：", local_file)
    print("📁 目标路径：", remote_path + filename)

    try:
        transport = paramiko.Transport((host, port))
        transport.connect(username=username, password=password)
        print("✅ 连接成功")

        sftp = paramiko.SFTPClient.from_transport(transport)

        sftp.put(local_file, remote_path + filename)

        print("✅ 文件上传成功")
        sftp.close()
        transport.close()
        return True

    except Exception as e:
        print("❌ 上传失败:", str(e))
        return False