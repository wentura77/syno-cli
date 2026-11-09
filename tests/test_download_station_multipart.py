"""Тесты многокомпонентной загрузки .torrent в Download Station и фолбэка API."""

import json
from pathlib import Path

import httpx
import pytest

from syno_cli.client.base import BaseSynoClient
from syno_cli.client.download_station import (
    SynoDownloadStationClient,
    normalize_destination,
)
from syno_cli.config import SynoSettings

# ---------------------------------------------------------------------------
# 1. Тестирование функции нормализации путей destination
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw_destination", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("downloads", "downloads"),
        ("/downloads/", "downloads"),
        ("///volume1//downloads///torrents///", "volume1/downloads/torrents"),
        (r"volume1\downloads\torrents\\", "volume1/downloads/torrents"),
        (r"\\volume1//downloads\\sub///", "volume1/downloads/sub"),
    ],
)
def test_normalize_destination_cases(raw_destination: str | None, expected: str | None) -> None:
    """Проверяет удаление ведущих/замыкающих слэшей и схлопывание повторов."""
    assert normalize_destination(raw_destination) == expected


# ---------------------------------------------------------------------------
# 2. Загрузка через DownloadStation2: проверка передачи _sid в URL и Cookie
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_station2_multipart_transfers_sid_and_cookie(tmp_path: Path) -> None:
    """Проверяет отправку _sid в параметрах запроса и заголовке Cookie для обхода ошибки 119."""
    torrent_file = tmp_path / "linux_distro.torrent"
    torrent_content = b"d8:announce35:udp://tracker.openbittorrent.com:80e"
    torrent_file.write_bytes(torrent_content)

    captured_url_sid = ""
    captured_cookie_header = ""
    captured_form_destination = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_url_sid, captured_cookie_header, captured_form_destination

        api = request.url.params.get("api")
        method = request.url.params.get("method")

        if api == "SYNO.API.Auth" and method == "login":
            return httpx.Response(200, json={"success": True, "data": {"sid": "ds2_secure_sid"}})

        # Подтверждаем поддержку DownloadStation2 в api_map
        if api == "SYNO.API.Info":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "SYNO.DownloadStation2.Task": {
                            "path": "entry.cgi",
                            "minVersion": 1,
                            "maxVersion": 2,
                        }
                    },
                },
            )

        if api == "SYNO.DownloadStation2.Task" and method == "create":
            captured_url_sid = request.url.params.get("_sid", "")
            captured_cookie_header = request.headers.get("Cookie", "")
            if b'name="destination"' in request.content:
                # Извлекаем значение destination из multipart payload
                parts = request.content.split(b'name="destination"\r\n\r\n')
                if len(parts) > 1:
                    raw_val = parts[1].split(b"\r\n")[0].decode("utf-8")
                    captured_form_destination = json.loads(raw_val)

            return httpx.Response(200, json={"success": True, "data": {"task_id": "ds2_task_01"}})

        return httpx.Response(404)

    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")
    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    client = SynoDownloadStationClient(base)

    try:
        res = await client.add_task(
            uri=str(torrent_file),
            destination="///volume1//downloads///iso///",
        )
        assert res.get("task_id") == "ds2_task_01"
        assert captured_url_sid == "ds2_secure_sid"
        assert captured_cookie_header == "id=ds2_secure_sid"
        assert captured_form_destination == "volume1/downloads/iso"
    finally:
        await base.close()


# ---------------------------------------------------------------------------
# 3. Двухфазный Fallback: отказ DownloadStation2 -> переключение на Task v1
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_station_fallback_from_v2_to_v1(tmp_path: Path) -> None:
    """Проверяет переключение на классический SYNO.DownloadStation.Task при сбое версии 2."""
    torrent_file = tmp_path / "sample.torrent"
    torrent_file.write_bytes(b"sample_torrent_stream_data")

    v2_attempted = False
    v1_succeeded = False
    v1_destination = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal v2_attempted, v1_succeeded, v1_destination

        api = request.url.params.get("api")
        method = request.url.params.get("method")

        if api == "SYNO.API.Auth":
            return httpx.Response(200, json={"success": True, "data": {"sid": "fallback_sid"}})

        if api == "SYNO.API.Info":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "SYNO.DownloadStation2.Task": {"path": "entry.cgi", "maxVersion": 2},
                        "SYNO.DownloadStation.Task": {"path": "entry.cgi", "maxVersion": 1},
                    },
                },
            )

        # Эмулируем ошибку API v2 (например, 102 API Not Found или устаревшая версия)
        if api == "SYNO.DownloadStation2.Task" and method == "create":
            v2_attempted = True
            return httpx.Response(200, json={"success": False, "error": {"code": 102}})

        # Запрос к классическому интерфейсу v1 должен пройти успешно
        if api == "SYNO.DownloadStation.Task" and method == "create":
            v1_succeeded = True
            if b'name="destination"' in request.content:
                parts = request.content.split(b'name="destination"\r\n\r\n')
                if len(parts) > 1:
                    v1_destination = parts[1].split(b"\r\n")[0].decode("utf-8")
            return httpx.Response(200, json={"success": True, "data": {"task_id": "legacy_v1_task"}})

        return httpx.Response(404)

    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")
    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    client = SynoDownloadStationClient(base)

    try:
        res = await client.add_task(
            uri=str(torrent_file),
            destination=r"\\volume1\downloads\torrents\\",
        )
        assert v2_attempted is True
        assert v1_succeeded is True
        assert res.get("task_id") == "legacy_v1_task"
        assert v1_destination == "volume1/downloads/torrents"
    finally:
        await base.close()
