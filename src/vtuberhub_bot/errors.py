"""Account/login error translation."""
from __future__ import annotations

import json
import re
from typing import Any


class AccountError(RuntimeError):
    pass


def parse_api_error(exc: BaseException) -> tuple[int | None, str, dict[str, Any]]:
    """Extract HTTP status + message from a Client RuntimeError."""
    text = str(exc or "")
    status: int | None = None
    body_text = text
    match = re.search(r"->\s*(\d{3}):\s*(.*)", text, re.S)
    if match:
        status = int(match.group(1))
        body_text = match.group(2)
    body: dict[str, Any] = {}
    try:
        parsed = json.loads(body_text)
        if isinstance(parsed, dict):
            body = parsed
    except Exception:
        pass
    message = body.get("message") or body.get("error") or body_text or text
    if isinstance(message, list):
        message = "; ".join(str(item) for item in message)
    return status, str(message), body


def login_error_message(username: str, exc: BaseException) -> str:
    status, message, body = parse_api_error(exc)
    user = username or "?"
    code = message.upper()
    raw = str(exc).lower()
    if "banned" in code.lower() or "banned" in raw:
        return f"Tài khoản `{user}` đã bị cấm. Liên hệ admin."
    if "user_not_found" in code.lower() or "deleted" in code.lower():
        return f"Tài khoản `{user}` không tồn tại hoặc đã bị xóa."
    if "inactive" in code.lower() or "pending" in code.lower() or "not_active" in code.lower():
        return f"Tài khoản `{user}` chưa kích hoạt hoặc đang bị vô hiệu hóa."
    if "captcha" in code.lower() or body.get("requiresCaptcha"):
        return (
            f"Tài khoản `{user}` cần xác minh captcha. "
            "Đăng nhập trên web trước rồi thử lại."
        )
    if (
        "invalid_credentials" in code.lower()
        or "invalid user credentials" in code.lower()
        or "wrong password" in code.lower()
        or status == 401
    ):
        return (
            f"Sai username hoặc mật khẩu cho `{user}` "
            f"(hoặc tài khoản không tồn tại). "
            f"Dùng `/login {user} <password>` để thử lại."
        )
    if status == 429 or "too many" in code.lower() or "throttl" in code.lower():
        return f"Quá nhiều lần thử cho `{user}`. Thử lại sau ít phút."
    if status == 400:
        return f"Dữ liệu đăng nhập không hợp lệ cho `{user}`: {message[:200]}"
    if status and status >= 500:
        return "Server VTuberHub đang lỗi. Thử lại sau."
    if "failed without response" in raw or "network" in raw or "connection" in raw:
        return "Không kết nối được server VTuberHub. Kiểm tra mạng rồi thử lại."
    if "token" in code.lower() and ("expired" in code.lower() or "invalid" in code.lower()):
        return (
            f"Phiên đăng nhập của `{user}` đã hết hạn. "
            f"Dùng `/login {user} <password>`."
        )
    return f"Đăng nhập `{user}` thất bại: {message[:200]}"


def describe_account_error(exc: BaseException) -> str:
    if isinstance(exc, AccountError):
        return str(exc)
    status, message, body = parse_api_error(exc)
    code = message.upper()
    raw = str(exc).lower()
    if "banned" in code.lower() or "banned" in raw:
        return "Tài khoản đã bị cấm."
    if "user_not_found" in code.lower() or "deleted" in code.lower():
        return "Tài khoản không tồn tại hoặc đã bị xóa."
    if "invalid_credentials" in code.lower() or status == 401:
        return "Phiên đăng nhập hết hạn hoặc sai mật khẩu; dùng /login."
    if status == 429:
        return "Quá nhiều lần thử; thử lại sau."
    if status and status >= 500:
        return "Server đang lỗi; thử lại sau."
    if "failed without response" in raw or "network" in raw:
        return "Không kết nối được server."
    return f"Lỗi API: {message[:200]}"
