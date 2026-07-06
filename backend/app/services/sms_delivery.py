from __future__ import annotations


def sms_is_configured() -> bool:
    return False


def send_login_code_sms(phone_number: str, code: str) -> bool:
    return sms_is_configured()
