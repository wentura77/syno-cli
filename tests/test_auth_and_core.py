"""Тесты аутентификации, перелогина при истечении сессии и системного статуса."""

import httpx
import pytest

from syno_cli.client.base import BaseSynoClient
from syno_cli.client.core import SynoCoreClient
from syno_cli.config import SynoSettings
from syno_cli.exceptions import DsmAuthError
from syno_cli.views.formatters import format_bytes, format_uptime


def test_formatters() -> None:
    """Проверяет форматирование байтов и аптайма."""
    assert format_bytes(0) == "0 B"
    assert format_bytes(1024) == "1.00 KB"
    assert format_bytes(1024 * 1024 * 5) == "5.00 MB"
    assert format_uptime(90060) == "1д 01ч 01м"


@pytest.mark.asyncio
async def test_login_and_auto_relogin(tmp_path) -> None:
    """Проверяет первичный логин, кэширование SID и автоперелогин при коде 119."""
    session_file = tmp_path / ".syno_session.json"
    cfg = SynoSettings(
        host="mock-nas",
        port=5000,
        user="admin",
        password="secret",
        session_file=session_file,
    )

    login_calls = 0
    sys_info_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal login_calls, sys_info_calls
        api = request.url.params.get("api")
        if api == "SYNO.API.Auth" and request.url.params.get("method") == "login":
            login_calls += 1
            return httpx.Response(
                200, json={"success": True, "data": {"sid": f"sid_token_{login_calls}"}}
            )

        if api == "SYNO.Core.System":
            sys_info_calls += 1
            # Первый вызов эмулирует протухшую сессию (код 119)
            if sys_info_calls == 1:
                return httpx.Response(200, json={"success": False, "error": {"code": 119}})
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {"model": "DS923+", "sys_temp": 42, "up_time": 3600},
                },
            )
        return httpx.Response(404)

    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    core = SynoCoreClient(base)
    try:
        info = await core.get_system_info()
        assert info["model"] == "DS923+"
        assert login_calls == 2
        assert base.sid == "sid_token_2"
        assert session_file.exists()
    finally:
        await base.close()


@pytest.mark.asyncio
async def test_login_invalid_credentials(tmp_path) -> None:
    """Проверяет выброс исключения DsmAuthError при коде ошибки 400."""
    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": False, "error": {"code": 400}})

    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(DsmAuthError) as exc_info:
            await base.login()
        assert exc_info.value.code == 400
    finally:
        await base.close()
