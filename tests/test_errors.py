"""Login/account error translation tests."""
from __future__ import annotations

import base64
import json
import tempfile
import unittest

from vtuberhub_bot.accounts import AccountManager, token_expiry
from vtuberhub_bot.errors import AccountError, describe_account_error, login_error_message


class ErrorTests(unittest.TestCase):
    def test_wrong_password(self) -> None:
        exc = RuntimeError(
            'POST /api/auth/login -> 401: '
            '{"message":"INVALID_CREDENTIALS","requiresCaptcha":false}'
        )
        msg = login_error_message("demo", exc)
        self.assertIn("Sai username hoặc mật khẩu", msg)
        self.assertIn("demo", msg)

    def test_banned(self) -> None:
        exc = RuntimeError(
            'POST /api/auth/login -> 401: '
            '{"message":"Your account has been banned from the system."}'
        )
        self.assertIn("bị cấm", login_error_message("demo", exc))

    def test_not_found(self) -> None:
        exc = RuntimeError(
            'POST /api/auth/login -> 404: {"message":"USER_NOT_FOUND"}'
        )
        self.assertIn("không tồn tại", login_error_message("demo", exc))

    def test_captcha(self) -> None:
        exc = RuntimeError(
            'POST /api/auth/login -> 403: '
            '{"message":"CAPTCHA_REQUIRED","requiresCaptcha":true}'
        )
        self.assertIn("captcha", login_error_message("demo", exc))

    def test_rate_limit(self) -> None:
        exc = RuntimeError(
            'POST /api/auth/login -> 429: {"message":"Too many requests"}'
        )
        self.assertIn("Quá nhiều", login_error_message("demo", exc))

    def test_server_error(self) -> None:
        exc = RuntimeError(
            'POST /api/auth/login -> 500: {"message":"Internal error"}'
        )
        self.assertIn("Server", login_error_message("demo", exc))

    def test_network(self) -> None:
        exc = RuntimeError("POST /api/auth/login failed without response")
        self.assertIn("Không kết nối", login_error_message("demo", exc))

    def test_describe(self) -> None:
        self.assertEqual(describe_account_error(AccountError("abc")), "abc")

    def test_token_expiry(self) -> None:
        payload = base64.urlsafe_b64encode(
            json.dumps({"exp": 1893456000}).encode()
        ).decode().rstrip("=")
        token = f"eyJhbGciOiJIUzI1NiJ9.{payload}.sig"
        expiry = token_expiry(token)
        self.assertIsNotNone(expiry)
        self.assertEqual(expiry.year, 2030)

    def test_empty_token_login(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = AccountManager(state_dir=tmp, seed_env=False)
            with self.assertRaises(AccountError):
                manager.login_with_token("")


if __name__ == "__main__":
    unittest.main()
