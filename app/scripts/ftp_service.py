import paramiko

sftp_host = "szsyjz.vicp.io"       # 如 szsyjz.vicp.io
sftp_port = 10035                      # 如果你通过 FRP 映射的是其他端口，比如 10022，就写对应端口
sftp_user = "adm"       # 注意是 SSH 用户，通常是 admin 或你创建的用户
sftp_pass = "Szsyjz159123"
local_file = '/settlements/test1.txt'        # 本地要上传的文件
remote_path = "JZ/中港模式结算单/test.txt"  # 群晖上目标路径，注意要有写权限

# === 上传逻辑 ===
try:
    transport = paramiko.Transport((sftp_host, sftp_port))
    transport.connect(username=sftp_user, password=sftp_pass)
    print("✅ 连接成功")
    sftp = paramiko.SFTPClient.from_transport(transport)

    print("local file: ", local_file)
    print("remote path: ", remote_path)

    sftp.put(local_file, remote_path)

    print("✅ 文件上传成功")
    sftp.close()
    transport.close()

except Exception as e:
    print("❌ 上传失败:", str(e))