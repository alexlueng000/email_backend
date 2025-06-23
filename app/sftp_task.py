# app/sftp_tasks.py
import os
import paramiko
from dotenv import load_dotenv
from celery import Celery

load_dotenv()

from app.main_celery import celery  # 根据你的项目结构调整导入

def ensure_remote_dir(sftp: paramiko.SFTPClient, remote_dir: str):
    dirs = remote_dir.strip("/").split("/")
    current = ""
    for d in dirs:
        current += f"/{d}"
        try:
            sftp.stat(current)
        except FileNotFoundError:
            sftp.mkdir(current)

@celery.task
def upload_file_to_sftp_task(local_file: str, remote_filename: str) -> bool:
    """
    异步上传文件到 SFTP，remote_filename 是文件名（会放在根目录或你定义的子目录中）
    """
    host = os.getenv("SFTP_HOST")
    port = int(os.getenv("SFTP_PORT", "22"))
    username = os.getenv("SFTP_USERNAME")
    password = os.getenv("SFTP_PASSWORD")

    remote_path = f"JZ/中港模式结算单/{remote_filename}"  # 你可以灵活改成传参

    try:
        transport = paramiko.Transport((host, port))
        transport.connect(username=username, password=password)
        print("✅ 连接成功")

        sftp = paramiko.SFTPClient.from_transport(transport)

        remote_dir = os.path.dirname(remote_path)
        ensure_remote_dir(sftp, remote_dir)

        sftp.put(local_file, remote_path)
        print(f"✅ 文件上传成功：{remote_path}")

        sftp.close()
        transport.close()
        return True

    except Exception as e:
        print("❌ 上传失败:", str(e))
        return False