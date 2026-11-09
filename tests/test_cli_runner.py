"""Тестирование CLI-команд через Typer CliRunner, проверка JSON-вывода и кодов возврата."""

import json
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from syno_cli.commands.main import app
from syno_cli.constants import ExitCode
from syno_cli.exceptions import DsmApiError, DsmAuthError

runner = CliRunner()


def test_cli_system_status_json() -> None:
    """Проверяет команду 'syno status --json' на валидность JSON и код выхода 0."""
    mock_info = {"model": "DS923+", "firmware_ver": "DSM 7.2", "sys_temp": 40, "up_time": 1000}
    mock_util = {"cpu": {"user_load": 10, "system_load": 5}, "memory": {"real_usage": 25}}

    with (
        patch("syno_cli.commands.system_cmd.SynoDSM") as mock_dsm,
    ):
        instance = mock_dsm.return_value.__aenter__.return_value
        instance.core.get_system_info = AsyncMock(return_value=mock_info)
        instance.core.get_utilization = AsyncMock(return_value=mock_util)

        result = runner.invoke(app, ["status", "--json"])
        assert result.exit_code == ExitCode.SUCCESS

        data = json.loads(result.stdout)
        assert data["info"]["model"] == "DS923+"
        assert data["utilization"]["cpu"]["user_load"] == 10


def test_cli_logs_list_json() -> None:
    """Проверяет команду 'syno logs list --json'."""
    mock_logs = [
        {"time": "2026-11-09 10:00:00", "level": "warn", "user": "admin", "descr": "Test event"}
    ]

    with patch("syno_cli.commands.logs_cmd.SynoDSM") as mock_dsm:
        instance = mock_dsm.return_value.__aenter__.return_value
        instance.logs.list_logs = AsyncMock(return_value=mock_logs)

        result = runner.invoke(app, ["logs", "list", "--json", "--lines", "1"])
        assert result.exit_code == ExitCode.SUCCESS

        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert data[0]["descr"] == "Test event"


def test_cli_error_dispatcher_auth_error() -> None:
    """Проверяет завершение процесса с кодом 1 при DsmAuthError."""
    with patch("syno_cli.commands.system_cmd.SynoDSM") as mock_dsm:
        instance = mock_dsm.return_value.__aenter__.return_value
        instance.core.get_system_info = AsyncMock(
            side_effect=DsmAuthError(code=400, api_name="SYNO.API.Auth")
        )

        result = runner.invoke(app, ["status", "--json"])
        assert result.exit_code == ExitCode.AUTH_ERROR
        assert "AuthError" in result.stderr


def test_cli_error_dispatcher_api_error() -> None:
    """Проверяет завершение процесса с кодом 2 при DsmApiError."""
    with patch("syno_cli.commands.system_cmd.SynoDSM") as mock_dsm:
        instance = mock_dsm.return_value.__aenter__.return_value
        instance.core.get_system_info = AsyncMock(
            side_effect=DsmApiError(code=102, api_name="SYNO.Core.System")
        )

        result = runner.invoke(app, ["status", "--json"])
        assert result.exit_code == ExitCode.API_ERROR
        assert "DsmApiError" in result.stderr


def test_cli_error_dispatcher_network_error() -> None:
    """Проверяет завершение процесса с кодом 4 при сетевом сбое (OSError)."""
    with patch("syno_cli.commands.system_cmd.SynoDSM") as mock_dsm:
        instance = mock_dsm.return_value.__aenter__.return_value
        instance.core.get_system_info = AsyncMock(side_effect=OSError("Network unreachable"))

        result = runner.invoke(app, ["status", "--json"])
        assert result.exit_code == ExitCode.NETWORK_ERROR
        assert "NetworkError" in result.stderr
