"""Модульные тесты сервисного фасада SynoDSM и управления жизненным циклом сессии."""

from pathlib import Path

import httpx
import pytest

from syno_cli.client.core import SynoCoreClient
from syno_cli.client.docker import SynoDockerClient
from syno_cli.client.download_station import SynoDownloadStationClient
from syno_cli.client.file_station import SynoFileStationClient
from syno_cli.client.logs import SynoLogsClient
from syno_cli.client.vmm import SynoVmmClient
from syno_cli.config import SynoSettings
from syno_cli.facade import SynoDSM


@pytest.mark.asyncio
async def test_syno_dsm_context_manager_lifecycle(tmp_path: Path) -> None:
    """Проверяет инициализацию подсистем и закрытие соединений в контекстном менеджере."""
    session_file = tmp_path / ".syno_session.json"

    def mock_handler(request: httpx.Request) -> httpx.Response:
        api = request.url.params.get("api")
        method = request.url.params.get("method")

        if api == "SYNO.API.Auth" and method == "login":
            return httpx.Response(
                200, json={"success": True, "data": {"sid": "mock_facade_sid"}}
            )

        if api == "SYNO.Core.System" and method == "info":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "model": "DS923+",
                        "firmware_ver": "DSM 7.2.1-69057",
                        "sys_temp": 40,
                        "up_time": 7200,
                    },
                },
            )

        if api == "SYNO.Core.SyslogClient.Log" and method == "list":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "items": [
                            {
                                "time": "2026-11-09 12:00:00",
                                "level": "info",
                                "user": "SYSTEM",
                                "descr": "Service started successfully",
                            }
                        ]
                    },
                },
            )

        return httpx.Response(200, json={"success": True, "data": {}})

    transport = httpx.MockTransport(mock_handler)

    async with SynoDSM(
        host="mock-nas.local",
        port=5001,
        user="admin",
        password="secret_password",
        secure=True,
        session_file=session_file,
        session_backend="file",
        transport=transport,
    ) as nas:
        # 1. Проверка типов смонтированных подсистем
        assert isinstance(nas.core, SynoCoreClient)
        assert isinstance(nas.files, SynoFileStationClient)
        assert isinstance(nas.docker, SynoDockerClient)
        assert isinstance(nas.downloads, SynoDownloadStationClient)
        assert isinstance(nas.logs, SynoLogsClient)
        assert isinstance(nas.vmm, SynoVmmClient)

        # 2. Вызовы методов через фасад
        info = await nas.core.get_system_info()
        assert info["model"] == "DS923+"

        status_alias = await nas.core.get_system_status()
        assert status_alias["firmware_ver"] == "DSM 7.2.1-69057"

        logs = await nas.logs.list_logs(limit=5)
        assert len(logs) == 1
        assert logs[0]["descr"] == "Service started successfully"

        assert not nas.base.client.is_closed

    # 3. Проверка автоматического закрытия HTTP-клиента при выходе из блока async with
    assert nas.base.client.is_closed


@pytest.mark.asyncio
async def test_syno_dsm_predefined_settings_injection(tmp_path: Path) -> None:
    """Проверяет передачу готового объекта SynoSettings в фасад."""
    session_file = tmp_path / "custom_session.json"
    custom_cfg = SynoSettings(
        host="10.0.0.5",
        port=5000,
        user="custom_operator",
        password="operator_pass",
        secure=False,
        session_file=session_file,
        session_backend="file",
    )

    def dummy_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "data": {"sid": "dummy_sid"}})

    nas = SynoDSM(settings=custom_cfg, transport=httpx.MockTransport(dummy_handler))
    try:
        assert nas.base.config.host == "10.0.0.5"
        assert nas.base.config.port == 5000
        assert nas.base.config.user == "custom_operator"
        assert nas.base.config.secure is False
        assert nas.base.config.session_file == session_file
    finally:
        await nas.close()
    assert nas.base.client.is_closed


@pytest.mark.asyncio
async def test_syno_dsm_network_timeout(tmp_path: Path) -> None:
    """Проверяет перехват таймаутов запроса и корректное закрытие клиента в контексте."""
    session_file = tmp_path / "timeout_session.json"

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("Connection timed out", request=request)

    transport = httpx.MockTransport(timeout_handler)

    with pytest.raises(httpx.TimeoutException):
        async with SynoDSM(
            host="timeout-nas.local",
            session_file=session_file,
            session_backend="file",
            transport=transport,
        ) as nas:
            await nas.core.get_system_info()

    # Клиент должен быть закрыт даже при возникновении таймаута
    assert nas.base.client.is_closed


@pytest.mark.asyncio
async def test_syno_dsm_connection_error(tmp_path: Path) -> None:
    """Проверяет поведение фасада при сбое соединения (Connection Refused)."""
    session_file = tmp_path / "conn_err_session.json"

    def error_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused by peer", request=request)

    transport = httpx.MockTransport(error_handler)

    with pytest.raises(httpx.RequestError) as exc_info:
        async with SynoDSM(
            host="unreachable-nas.local",
            session_file=session_file,
            session_backend="file",
            transport=transport,
        ) as nas:
            await nas.docker.list_containers()

    assert "Connection refused" in str(exc_info.value)
    assert nas.base.client.is_closed


@pytest.mark.asyncio
async def test_syno_dsm_socket_os_error_and_reauth_failure(tmp_path: Path) -> None:
    """Проверяет разрыв соединения (OSError), очистку сессии и выброс DsmApiError."""
    from syno_cli.constants import DSM_ERR_INVALID_SESSION
    from syno_cli.exceptions import DsmApiError

    session_file = tmp_path / "oserr_session.json"
    login_count = 0

    def socket_break_handler(request: httpx.Request) -> httpx.Response:
        nonlocal login_count
        api = request.url.params.get("api")
        method = request.url.params.get("method")

        if api == "SYNO.API.Auth" and method == "login":
            login_count += 1
            return httpx.Response(200, json={"success": True, "data": {"sid": f"sid_{login_count}"}})

        # Эмулируем внезапный разрыв TCP-соединения сервером NAS
        raise OSError("Connection reset by peer")

    transport = httpx.MockTransport(socket_break_handler)

    with pytest.raises(DsmApiError) as exc_info:
        async with SynoDSM(
            host="broken-pipe-nas.local",
            session_file=session_file,
            session_backend="file",
            transport=transport,
        ) as nas:
            await nas.files.list_shares()

    # Проверяем, что была попытка повторного входа, сформирован код ошибки 119 и сессия очищена
    assert exc_info.value.code == DSM_ERR_INVALID_SESSION
    assert "раззорвал соединение" in str(exc_info.value).lower() or "connection reset" in str(exc_info.value).lower()
    assert nas.base.client.is_closed
