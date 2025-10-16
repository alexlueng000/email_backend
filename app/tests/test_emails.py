# test_mail.py
import smtplib
import socket
import ssl
from email.message import EmailMessage
from typing import Dict, Any

from app.email_utils import MAIL_ACCOUNTS  # 你给的配置

def _tls_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx

def _build_msg(sender: str, to: str, subject: str, html: str, text_fallback: str = None) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    # 纯文本回退（可选）
    if text_fallback:
        msg.set_content(text_fallback)
        msg.add_alternative(html, subtype="html")
    else:
        # 只发 HTML 也可以
        msg.set_content("Your email client does not support HTML.")
        msg.add_alternative(html, subtype="html")
    return msg

def _login_and_send_via_587(host: str, user: str, app_pass: str, msg: EmailMessage):
    with smtplib.SMTP(host, 587, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls(context=_tls_ctx())
        smtp.ehlo()
        smtp.login(user, app_pass)
        smtp.send_message(msg)

def _login_and_send_via_465(host: str, user: str, app_pass: str, msg: EmailMessage):
    with smtplib.SMTP_SSL(host=host, port=465, timeout=30, context=_tls_ctx()) as smtp:
        smtp.ehlo()
        smtp.login(user, app_pass)
        smtp.send_message(msg)

def send_test_email(alias: str, to: str, subject: str = "邮件连通性测试", html_body: str = None) -> None:
    """
    从 settings_mail.MAIL_ACCOUNTS 读取别名(A/B/C)的发信账号，发送一封测试邮件。
    优先 587+STARTTLS，失败时回退 465/SMTPS。
    """
    acc: Dict[str, Any] = MAIL_ACCOUNTS.get(alias)
    if not acc:
        raise KeyError(f"别名 {alias} 不存在于 MAIL_ACCOUNTS。")

    host = acc.get("smtp_host")
    port = int(acc.get("smtp_port") or 465)  # 仅用于日志；真正走 587/465 的函数里写死
    user = acc.get("username") or acc.get("email")
    pwd  = acc.get("password")
    sender = acc.get("from") or user

    print("host", host)
    print("port", port)
    print("user", user)
    print("pwd", pwd)
    print("sender", sender)

    if not all([host, user, pwd, sender]):
        raise ValueError(f"别名 {alias} 的发信配置缺少必要字段（需要 smtp_host/username/password/from）。")

    if not html_body:
        html_body = f"""
        <html><body>
            <p>别名 <b>{alias}</b> 的测试邮件。</p>
            <p>发件人：{sender}<br/>SMTP：{host}（优先 587+STARTTLS，失败回退 465/SMTPS）</p>
        </body></html>
        """

    msg = _build_msg(sender, to, subject, html_body, text_fallback="这是一封连通性测试邮件。")

    # 简易可读日志（不打印密码）
    print(f"[MAIL] alias={alias} from={sender} -> to={to} host={host} plan=587->465")

    # 首选 587（更抗网络、合规度高）
    try:
        _login_and_send_via_587(host, user, pwd, msg)
        print("[MAIL] ✅ 587+STARTTLS 发送成功")
        return
    except Exception as e1:
        print(f"[MAIL] ⚠️ 587 失败：{repr(e1)}，尝试 465/SMTPS ...")

    # 回退 465（某些网络也很稳定）
    try:
        _login_and_send_via_465(host, user, pwd, msg)
        print("[MAIL] ✅ 465/SMTPS 发送成功")
        return
    except Exception as e2:
        raise RuntimeError(f"[MAIL] ❌ 两种通道均失败：587→{repr(e1)}；465→{repr(e2)}")

if __name__ == "__main__":
    # 示例：用别名 A 发一封到你自己的邮箱
    send_test_email(
        alias="A",
        to="494762262@qq.com",
        subject="【连通性测试】A 通道",
    )