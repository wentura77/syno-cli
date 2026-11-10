"""Модульные тесты фолбэков API, стриминга и нетипичных сценариев клиентских модулей."""

from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from syno_cli.client.base import BaseSynoClient
from syno_cli.client.core import SynoCoreClient
from syno_cli.client.download_station import SynoDownloadStationClient
from syno_cli.client.file_station import SynoFileStationClient
from syno_cli.client.logs import SynoLogsClient
from syno_cli.config import SynoSettings
from syno_cli.constants import DSM_ERR_API_NOT_EXISTS
from syno_cli.exceptions import DsmApiError

# ---------------------------------------------------------------------------
# 1. BaseSynoClient: logout, текстовый stream_download и авто-reauth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_base_client_logout_clears_session(tmp_path: Path) -> None:
    """Проверяет отправку запроса logout и полную очистку сессии на диске."""
    session_file = tmp_path / "logout_session.json"
    logout_called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal logout_called
        api = request.url.params.get("api")
        method = request.url.params.get("method")
        if api == "SYNO.API.Auth" and method == "login":
            return httpx.Response(200, json={"success": True, "data": {"sid": "active_sid"}})
        if api == "SYNO.API.Auth" and method == "logout":
            logout_called = True
            return httpx.Response(200, json={"success": True})
        return httpx.Response(404)

    cfg = SynoSettings(host="mock-nas", session_file=session_file)
    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    try:
        await base.login()
        assert base.sid == "active_sid"
        assert session_file.exists()

        await base.logout()
        assert logout_called is True
        assert base.sid is None
        assert not session_file.exists()
    finally:
        await base.close()


@pytest.mark.asyncio
async def test_stream_download_plain_text_success(tmp_path: Path) -> None:
    """Проверяет сохранение обычного текстового файла при content-type text/plain."""
    target_file = tmp_path / "notes.txt"
    text_payload = "Line 1: system log text\nLine 2: regular status"

    def handler(request: httpx.Request) -> httpx.Response:
        api = request.url.params.get("api")
        method = request.url.params.get("method")
        if api == "SYNO.API.Auth":
            return httpx.Response(200, json={"success": True, "data": {"sid": "stream_sid"}})
        if api == "SYNO.FileStation.Download" and method == "download":
            return httpx.Response(
                200,
                headers={"Content-Type": "text/plain; charset=utf-8"},
                text=text_payload,
            )
        return httpx.Response(404)

    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")
    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    try:
        res = await base.stream_download(
            api_name="SYNO.FileStation.Download",
            method="download",
            params={"path": "/volume1/notes.txt"},
            target_file=target_file,
        )
        assert res.exists()
        assert res.read_text(encoding="utf-8") == text_payload
    finally:
        await base.close()


@pytest.mark.asyncio
async def test_stream_download_reauth_on_session_expired(tmp_path: Path) -> None:
    """Проверяет автоматический перелогин при получении JSON-ошибки 119 в потоке."""
    target_file = tmp_path / "reauth_file.bin"
    download_attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal download_attempts
        api = request.url.params.get("api")
        method = request.url.params.get("method")

        if api == "SYNO.API.Auth":
            return httpx.Response(200, json={"success": True, "data": {"sid": f"sid_{download_attempts}"}})

        if api == "SYNO.FileStation.Download" and method == "download":
            download_attempts += 1
            if download_attempts == 1:
                # Первый ответ — JSON-ошибка протухшей сессии
                return httpx.Response(
                    200,
                    headers={"Content-Type": "application/json"},
                    json={"success": False, "error": {"code": 119}},
                )
            return httpx.Response(
                200,
                headers={"Content-Type": "application/octet-stream"},
                content=b"fresh_download_content",
            )
        return httpx.Response(404)

    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")
    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    try:
        res = await base.stream_download(
            api_name="SYNO.FileStation.Download",
            method="download",
            params={"path": "/volume1/file.bin"},
            target_file=target_file,
            retry_auth=True,
        )
        assert download_attempts == 2
        assert res.read_bytes() == b"fresh_download_content"
    finally:
        await base.close()


# ---------------------------------------------------------------------------
# 2. SynoCoreClient: reboot, shutdown и get_storage_info
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_core_client_power_and_storage(tmp_path: Path) -> None:
    """Проверяет отправку POST-запросов на reboot, shutdown и чтение данных хранилища."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params: dict[str, Any]
        if request.method == "POST":
            params = {k: v[0] for k, v in parse_qs(request.content.decode("utf-8")).items()}
        else:
            params = dict(request.url.params)

        api = params.get("api", "")
        method = params.get("method", "")

        if api == "SYNO.API.Auth":
            return httpx.Response(200, json={"success": True, "data": {"sid": "core_sid"}})

        if api == "SYNO.Core.System" and method in ("reboot", "shutdown"):
            calls.append(method)
            return httpx.Response(200, json={"success": True, "data": {}})

        if api == "SYNO.Storage.CGI.Storage" and method == "load_info":
            return httpx.Response(
                200,
                json={"success": True, "data": {"disks": [{"name": "Drive 1"}], "volumes": []}},
            )
        return httpx.Response(404)

    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")
    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    core = SynoCoreClient(base)
    try:
        await core.reboot()
        await core.shutdown()
        storage = await core.get_storage_info()

        assert calls == ["reboot", "shutdown"]
        assert "disks" in storage
        assert storage["disks"][0]["name"] == "Drive 1"
    finally:
        await base.close()


# ---------------------------------------------------------------------------
# 3. SynoFileStationClient: copy_or_move, sharing link, upload в памяти
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_file_station_copy_move_and_sharing(tmp_path: Path) -> None:
    """Проверяет режимы copy_or_move (cp/mv) и генерацию публичной ссылки доступа."""
    captured_copymove: dict[str, Any] = {}
    captured_sharing: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_copymove, captured_sharing
        params: dict[str, Any]
        if request.method == "POST":
            params = {k: v[0] for k, v in parse_qs(request.content.decode("utf-8")).items()}
        else:
            params = dict(request.url.params)

        api = params.get("api", "")
        method = params.get("method", "")

        if api == "SYNO.API.Auth":
            return httpx.Response(200, json={"success": True, "data": {"sid": "fs_sid"}})

        if api == "SYNO.FileStation.CopyMove" and method == "start":
            captured_copymove = params
            return httpx.Response(200, json={"success": True, "data": {"taskid": "async_task_99"}})

        if api == "SYNO.FileStation.Sharing" and method == "create":
            captured_sharing = params
            return httpx.Response(
                200,
                json={"success": True, "data": {"links": [{"url": "https://gofile.me/abc"}]}},
            )
        return httpx.Response(404)

    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")
    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    fs = SynoFileStationClient(base)
    try:
        # Копирование
        await fs.copy_or_move("/volume1/src.txt", "/volume1/dest", remove_src=False)
        assert captured_copymove.get("remove_src") == "false"

        # Перемещение
        await fs.copy_or_move("/volume1/src.txt", "/volume1/dest", remove_src=True)
        assert captured_copymove.get("remove_src") == "true"

        # Публичная ссылка
        link_res = await fs.create_sharing_link(
            path="/volume1/photo.jpg", password="PinCode123", date_expired="2026-12-31"
        )
        assert captured_sharing.get("password") == "PinCode123"
        assert captured_sharing.get("date_expired") == "2026-12-31"
        assert link_res["links"][0]["url"] == "https://gofile.me/abc"
    finally:
        await base.close()


@pytest.mark.asyncio
async def test_file_station_upload_from_memory_stream(tmp_path: Path) -> None:
    """Проверяет загрузку файла из байтового потока (content_stream) без чтения с диска."""
    uploaded_content = b""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal uploaded_content
        api = request.url.params.get("api")
        method = request.url.params.get("method")

        if api == "SYNO.API.Auth":
            return httpx.Response(200, json={"success": True, "data": {"sid": "fs_sid"}})

        if api == "SYNO.FileStation.Upload" and method == "upload":
            uploaded_content = request.content
            return httpx.Response(200, json={"success": True, "data": {"file": "in_memory.bin"}})
        return httpx.Response(404)

    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")
    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    fs = SynoFileStationClient(base)
    try:
        payload = b"raw_in_memory_bytes_without_file"
        res = await fs.upload_file(
            local_path=Path("dummy_name.bin"),
            dest_folder_path="/docker",
            content_stream=payload,
        )
        assert res.get("file") == "in_memory.bin"
        assert payload in uploaded_content
    finally:
        await base.close()


# ---------------------------------------------------------------------------
# 4. Download Station: fallback статистики и проверка установленного пакета
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_station_statistic_fallback_calculation(tmp_path: Path) -> None:
    """Проверяет фолбэк расчета скоростей через list_tasks при ошибке Statistic (код 102)."""
    def handler(request: httpx.Request) -> httpx.Response:
        api = request.url.params.get("api")
        method = request.url.params.get("method")

        if api == "SYNO.API.Auth":
            return httpx.Response(200, json={"success": True, "data": {"sid": "ds_sid"}})

        # Метод getinfo недоступен
        if api == "SYNO.DownloadStation.Statistic":
            return httpx.Response(200, json={"success": False, "error": {"code": 102}})

        # Возвращаем задачи для ручного суммирования
        if api == "SYNO.DownloadStation.Task" and method == "list":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "tasks": [
                            {"additional": {"transfer": {"speed_download": 300, "speed_upload": 100}}},
                            {"additional": {"transfer": {"speed_download": 700, "speed_upload": 50}}},
                        ]
                    },
                },
            )
        return httpx.Response(404)

    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")
    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    ds = SynoDownloadStationClient(base)
    try:
        stats = await ds.get_statistic()
        assert stats["speed_download"] == 1000
        assert stats["speed_upload"] == 150
    finally:
        await base.close()


@pytest.mark.asyncio
async def test_download_station_not_installed_raises(tmp_path: Path) -> None:
    """Проверяет выброс ошибки 102, если пакет Download Station отсутствует в api_map."""
    def handler(request: httpx.Request) -> httpx.Response:
        api = request.url.params.get("api")
        if api == "SYNO.API.Auth":
            return httpx.Response(200, json={"success": True, "data": {"sid": "ds_sid"}})
        if api == "SYNO.API.Info":
            # Возвращаем api_map без ключей SYNO.DownloadStation
            return httpx.Response(
                200,
                json={"success": True, "data": {"SYNO.Core.System": {"path": "entry.cgi"}}},
            )
        return httpx.Response(404)

    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")
    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    ds = SynoDownloadStationClient(base)
    try:
        await base.discover_apis()
        with pytest.raises(DsmApiError) as exc_info:
            await ds.list_tasks()
        assert exc_info.value.code == DSM_ERR_API_NOT_EXISTS
        assert "не установлен" in str(exc_info.value).lower()
    finally:
        await base.close()


# ---------------------------------------------------------------------------
# 5. SynoLogsClient: fallback на SYNO.Core.SyslogClient.Setting.Log
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logs_client_fallback_to_setting_log(tmp_path: Path) -> None:
    """Проверяет переключение на Setting.Log при сбое основного эндпоинта журналов."""
    primary_failed = False
    secondary_succeeded = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal primary_failed, secondary_succeeded
        api = request.url.params.get("api")
        method = request.url.params.get("method")

        if api == "SYNO.API.Auth":
            return httpx.Response(200, json={"success": True, "data": {"sid": "log_sid"}})

        if api == "SYNO.Core.SyslogClient.Log" and method == "list":
            primary_failed = True
            return httpx.Response(200, json={"success": False, "error": {"code": 102}})

        if api == "SYNO.Core.SyslogClient.Setting.Log" and method == "list":
            secondary_succeeded = True
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "items": [
                            {"time": "2026-11-10", "level": "warn", "user": "root", "descr": "Fallback Log"}
                        ]
                    },
                },
            )
        return httpx.Response(404)

    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")
    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    logs_client = SynoLogsClient(base)
    try:
        logs = await logs_client.list_logs(limit=1)
        assert primary_failed is True
        assert secondary_succeeded is True
        assert len(logs) == 1
        assert logs[0]["descr"] == "Fallback Log"
    finally:
        await base.close()
