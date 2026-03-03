import os
import posixpath
import paramiko
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def test_sftp_put():
    host = os.getenv("SFTP_HOST")
    port = int(os.getenv("SFTP_PORT", "22"))
    username = os.getenv("SFTP_USER")
    password = os.getenv("SFTP_PASS")
    remote_base = (os.getenv("REMOTE_PATH") or "").strip().strip("/")

    assert host and username and password, "Missing env: SFTP_HOST/SFTP_USER/SFTP_PASS"

    # 1) 本地造一个测试文件

    local_file = r"E:\\code_projects\\syjz_emails\\backend\\note.md"

    filename = f"note_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

    # 2) 远端路径：用 posixpath，别用 Windows 的反斜杠
    if remote_base:
        remote_path = posixpath.join("/", remote_base, filename)
    else:
        remote_path = posixpath.join("/", filename)

    print(f"host={host} port={port} user={username}")
    print(f"local={local_file}")
    print(f"remote={remote_path}")

    transport = paramiko.Transport((host, port))
    try:
        transport.connect(username=username, password=password)
        # 如果这里报错，说明 SSH 认证都没成功

        try:
            sftp = paramiko.SFTPClient.from_transport(transport)
        except Exception as e:
            raise RuntimeError(
                "SSH 已连上，但 SFTP 子系统打开失败。"
                "请去群晖启用 SFTP（不是只启用 SSH）。原始错误: "
                + repr(e)
            )

        try:
            sftp.put(str(local_file), remote_path)
            print("UPLOAD OK")
        finally:
            sftp.close()
    finally:
        transport.close()

if __name__ == "__main__":
    test_sftp_put()
