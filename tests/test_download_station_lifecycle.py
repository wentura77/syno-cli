"""Тесты жизненного цикла задач Download Station (пакетные операции, частичные ошибки и статистика)."""

from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from syno_cli.client.base import BaseSynoClient
from syno_cli.client.download_station import SynoDownloadStationClient
from syno_cli.config import SynoSettings


def _parse_request_params(request: httpx.Request) -> dict[str, str]:
    """Извлекает параметры запроса из query и multipart/form-urlencoded тела."""
    params: dict[str, str] = {k: v for k, v in request.url.params.items()}
    if request.content:
        try:
            body = request.content.decode("utf-8", errors="ignore")
            parsed = parse_qs(body)
            for k, vals in parsed.items():
                if vals:
                    params[k] = vals[0]
        except Exception:
            pass
    return params


# ---------------------------------------------------------------------------
# 1. Пакетное управление состоянием задач (pause, resume, delete)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_station_batch_pause_and_resume(tmp_path: Path) -> None:
    """Проверяет передачу нескольких ID задач через запятую при паузе и возобновлении."""
    captured_pause_id = ""
    captured_resume_id = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_pause_id, captured_resume_id
        params = _parse_request_params(request)
        api = params.get("api", "")
        method = params.get("method", "")

        if api == "SYNO.API.Auth":
            return httpx.Response(200, json={"success": True, "data": {"sid": "test_sid"}})

        if api == "SYNO.API.Info":
            return httpx.Response(200, json={"success": True, "data": {}})

        if api == "SYNO.DownloadStation.Task" and method == "pause":
            captured_pause_id = params.get("id", "")
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": [
                        {"error": 0, "id": "dbid_1"},
                        {"error": 0, "id": "dbid_2"},
                    ],
                },
            )

        if api == "SYNO.DownloadStation.Task" and method == "resume":
            captured_resume_id = params.get("id", "")
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": [
                        {"error": 0, "id": "dbid_1"},
                        {"error": 0, "id": "dbid_2"},
                    ],
                },
            )

        return httpx.Response(404)

    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")
    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    ds = SynoDownloadStationClient(base)

    try:
        pause_res = await ds.pause_task(["dbid_1", "dbid_2"])
        assert captured_pause_id == "dbid_1,dbid_2"
        # Если базовый клиент вернул список или пустой словарь при десериализации
        if isinstance(pause_res, list):
            assert len(pause_res) == 2
        else:
            assert pause_res is not None

        resume_res = await ds.resume_task(["dbid_1", "dbid_2"])
        assert captured_resume_id == "dbid_1,dbid_2"
        if isinstance(resume_res, list):
            assert len(resume_res) == 2
        else:
            assert resume_res is not None
    finally:
        await base.close()


@pytest.mark.asyncio
async def test_download_station_delete_partial_errors(tmp_path: Path) -> None:
    """Проверяет обработку ответа с частичными ошибками при удалении списка задач."""
    captured_delete_params: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_delete_params
        params = _parse_request_params(request)
        api = params.get("api", "")
        method = params.get("method", "")

        if api == "SYNO.API.Auth":
            return httpx.Response(200, json={"success": True, "data": {"sid": "test_sid"}})

        if api == "SYNO.API.Info":
            return httpx.Response(200, json={"success": True, "data": {}})

        if api == "SYNO.DownloadStation.Task" and method == "delete":
            captured_delete_params = params
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": [
                        {"error": 0, "id": "dbid_1"},
                        {"error": 100, "id": "dbid_missing_999"},
                    ],
                },
            )

        return httpx.Response(404)

    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")
    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    ds = SynoDownloadStationClient(base)

    try:
        delete_res = await ds.delete_task(["dbid_1", "dbid_missing_999"], force_complete=True)

        assert captured_delete_params.get("id") == "dbid_1,dbid_missing_999"
        assert captured_delete_params.get("force_complete") in ("true", "True")

        if isinstance(delete_res, list):
            assert len(delete_res) == 2
            success_item = next(item for item in delete_res if item.get("id") == "dbid_1")
            error_item = next(item for item in delete_res if item.get("id") == "dbid_missing_999")
            assert success_item.get("error") == 0
            assert error_item.get("error") == 100
        else:
            assert delete_res is not None
    finally:
        await base.close()


# ---------------------------------------------------------------------------
# 2. Получение агрегированной статистики скоростей
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_station_get_statistic_direct_api(tmp_path: Path) -> None:
    """Проверяет прямой опрос SYNO.DownloadStation.Statistic."""

    def handler(request: httpx.Request) -> httpx.Response:
        params = _parse_request_params(request)
        api = params.get("api", "")
        method = params.get("method", "")

        if api == "SYNO.API.Auth":
            return httpx.Response(200, json={"success": True, "data": {"sid": "test_sid"}})

        if api == "SYNO.API.Info":
            return httpx.Response(200, json={"success": True, "data": {}})

        if api == "SYNO.DownloadStation.Statistic" and method == "getinfo":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "speed_download": 10485760,
                        "speed_upload": 2097152,
                        "emule_speed_download": 0,
                        "emule_speed_upload": 0,
                    },
                },
            )

        return httpx.Response(404)

    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")
    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    ds = SynoDownloadStationClient(base)

    try:
        stats = await ds.get_statistic()
        assert stats["speed_download"] == 10485760
        assert stats["speed_upload"] == 2097152
    finally:
        await base.close()


@pytest.mark.asyncio
async def test_download_station_get_statistic_fallback_aggregation(tmp_path: Path) -> None:
    """Проверяет суммирование скоростей по списку задач при сбое интерфейса Statistic (код 102)."""

    def handler(request: httpx.Request) -> httpx.Response:
        params = _parse_request_params(request)
        api = params.get("api", "")
        method = params.get("method", "")

        if api == "SYNO.API.Auth":
            return httpx.Response(200, json={"success": True, "data": {"sid": "test_sid"}})

        if api == "SYNO.API.Info":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "SYNO.DownloadStation.Task": {"path": "entry.cgi", "maxVersion": 1}
                    },
                },
            )

        if api == "SYNO.DownloadStation.Statistic":
            return httpx.Response(200, json={"success": False, "error": {"code": 102}})

        if api == "SYNO.DownloadStation.Task" and method == "list":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "tasks": [
                            {
                                "id": "task_1",
                                "title": "Ubuntu ISO",
                                "additional": {
                                    "transfer": {
                                        "speed_download": 4000000,
                                        "speed_upload": 500000,
                                    }
                                },
                            },
                            {
                                "id": "task_2",
                                "title": "Debian ISO",
                                "additional": {
                                    "transfer": {
                                        "speed_download": 6000000,
                                        "speed_upload": 700000,
                                    }
                                },
                            },
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
        assert stats["speed_download"] == 10000000
        assert stats["speed_upload"] == 1200000
    finally:
        await base.close()
