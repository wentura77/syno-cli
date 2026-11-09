"""Тестирование двухфакторной аутентификации (OTP/2FA) и бэкендов хранения."""

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from syno_cli.client.base import BaseSynoClient
from syno_cli.config import SynoSettings
from syno_cli.credential_storage import get_credentials, save_credentials_to_file
from syno_cli.exceptions import DsmAuthError


@pytest.mark.asyncio
async def test_auth_login_with_otp(tmp_path: Path) -> None:
    """Проверяет передачу 2FA OTP-кода в запросе авторизации."""
    sent_otp = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal sent_otp
        api = request.url.params.get("api")
        method = request.url.params.get("method")
        if api == "SYNO.API.Auth" and method == "login":
            sent_otp = request.url.params.get("otp_code")
            if sent_otp == "123456":
                return httpx.Response(200, json={"success": True, "data": {"sid": "2fa_session_ok"}})
            return httpx.Response(200, json={"success": False, "error": {"code": 404}})
        return httpx.Response(404)

    cfg = SynoSettings(
        host="mock-nas",
        user="admin",
        password="secure_password",
        otp_code="123456",
        session_file=tmp_path / ".session.json",
    )
    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    try:
        sid = await base.login()
        assert sid == "2fa_session_ok"
        assert sent_otp == "123456"
    finally:
        await base.close()


@pytest.mark.asyncio
async def test_auth_login_invalid_otp_raises(tmp_path: Path) -> None:
    """Проверяет выброс ошибки 404 при неверном одноразовом коде 2FA."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": False, "error": {"code": 404}})

    cfg = SynoSettings(
        host="mock-nas",
        user="admin",
        password="secure_password",
        otp_code="000000",
        session_file=tmp_path / ".session.json",
    )
    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(DsmAuthError) as exc_info:
            await base.login()
        assert exc_info.value.code == 404
    finally:
        await base.close()


def test_credential_storage_fallback_to_file(tmp_path: Path) -> None:
    """Проверяет фолбэк с системного keyring на EncryptedFileStorage при режиме 'auto'."""
    cred_file = tmp_path / "credentials.enc"
    save_credentials_to_file("syno_user", "encrypted_pass", cred_file)

    # Эмулируем отсутствие доступного системного keyring
    with patch("syno_cli.credential_storage.is_keyring_available", return_value=False):
        creds = get_credentials("auto", cred_file)
        assert creds == ("syno_user", "encrypted_pass")
