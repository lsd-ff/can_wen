from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.core.config import get_settings


settings = get_settings()


def smtp_is_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_username and settings.smtp_password)


def send_login_code_email(email: str, code: str) -> bool:
    if not smtp_is_configured():
        return False

    message = EmailMessage()
    message["Subject"] = "CanW 登录验证码"
    message["From"] = settings.smtp_from_email or settings.smtp_username
    message["To"] = email
    message.set_content(f"你的 CanW 登录验证码是：{code}\n\n验证码 5 分钟内有效。")

    if settings.smtp_use_ssl:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as smtp:
            smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)

    return True
