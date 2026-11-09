"""Модульные тесты потоковой загрузки и скачивания в File Station."""

from pathlib import Path

import httpx
import pytest

from syno_cli.client.base import BaseSynoClient
from syno_cli.client.file_station import SynoFileStationClient
from syno_cli.config import SynoSettings
from syno_cli.exceptions import DsmApiError


@pytest.mark.asyncio
async def test_upload_file_streaming_callback(tmp_path: Path) -> None:
    """Проверяет потоковую отправку файла и срабатывание progress_callback."""
    test_file = tmp_path / "test_payload.bin"
    chunk_data = b"0" * 1024 * 64  # 64 KB
    test_file.write_bytes(chunk_data * 4)  # 256 KB

    bytes_read = 0

    def on_progress(chunk_size: int) -> None:
        nonlocal bytes_read
        bytes_read += chunk_size

    def handler(request: httpx.Request) -> httpx.Response:
        api = request.url.params.get("api")
        method = request.url.params.get("method")
        if api == "SYNO.API.Auth" and method == "login":
            return httpx.Response(200, json={"success": True, "data": {"sid": "stream_sid"}})
        if api == "SYNO.FileStation.Upload" and method == "upload":
            return httpx.Response(200, json={"success": True, "data": {"file": "uploaded"}})
        return httpx.Response(404)

    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")
    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    fs = SynoFileStationClient(base)

    try:
        res = await fs.upload_file(
            local_path=test_file,
            dest_folder_path="/docker",
            progress_callback=on_progress,
        )
        assert res.get("file") == "uploaded"
        assert bytes_read == test_file.stat().st_size
    finally:
        await base.close()


@pytest.mark.asyncio
async def test_download_file_streams_to_directory(tmp_path: Path) -> None:
    """Проверяет скачивание бинарного потока в целевую директорию."""
    target_dir = tmp_path / "downloads"
    target_dir.mkdir()

    file_content = b"Binary stream content data payload" * 100

    def handler(request: httpx.Request) -> httpx.Response:
        api = request.url.params.get("api")
        method = request.url.params.get("method")
        if api == "SYNO.API.Auth" and method == "login":
            return httpx.Response(200, json={"success": True, "data": {"sid": "stream_sid"}})
        if api == "SYNO.FileStation.Download" and method == "download":
            return httpx.Response(
                200,
                headers={"Content-Type": "application/octet-stream", "Content-Length": str(len(file_content))},
                content=file_content,
            )
        return httpx.Response(404)

    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")
    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    fs = SynoFileStationClient(base)

    try:
        saved_file = await fs.download_file("/volume1/data/archive.iso", target_dir)
        assert saved_file.exists()
        assert saved_file.name == "archive.iso"
        assert saved_file.read_bytes() == file_content
    finally:
        await base.close()


@pytest.mark.asyncio
async def test_download_file_server_json_error(tmp_path: Path) -> None:
    """Проверяет, что серверная JSON-ошибка при скачивании корректно возбуждает DsmApiError."""
    target_file = tmp_path / "output.bin"

    def handler(request: httpx.Request) -> httpx.Response:
        api = request.url.params.get("api")
        if api == "SYNO.API.Auth":
            return httpx.Response(200, json={"success": True, "data": {"sid": "stream_sid"}})
        if api == "SYNO.FileStation.Download":
            return httpx.Response(
                200,
                headers={"Content-Type": "application/json; charset=UTF-8"},
                json={"success": False, "error": {"code": 408}},
            )
        return httpx.Response(404)

    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")
    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    fs = SynoFileStationClient(base)

    try:
        with pytest.raises(DsmApiError) as exc_info:
            await fs.download_file("/volume1/data/missing.iso", target_file)
        assert exc_info.value.code == 408
        assert not target_file.exists()
    finally:
        await base.close()
