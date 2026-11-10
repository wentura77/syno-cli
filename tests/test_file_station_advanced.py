"""Тесты расширенных операций File Station: массивы путей, асинхронные задачи и шаринг."""

import json
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from syno_cli.client.base import BaseSynoClient
from syno_cli.client.file_station import SynoFileStationClient
from syno_cli.config import SynoSettings


def _parse_request_params(request: httpx.Request) -> dict[str, str]:
    """Вспомогательная функция для извлечения параметров GET и POST запросов."""
    params = dict(request.url.params)
    if request.method == "POST" and request.content:
        # Если это стандартный x-www-form-urlencoded
        body_str = request.content.decode("utf-8")
        if "=" in body_str:
            post_data = {k: v[0] for k, v in parse_qs(body_str).items()}
            params.update(post_data)
    return params


# ---------------------------------------------------------------------------
# 1. Тесты передачи путей в виде JSON-массивов (Delete / CopyMove)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_file_station_delete_path_json_array(tmp_path: Path) -> None:
    """Проверяет передачу параметра path в виде JSON-массива строк при удалении."""
    captured_params: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_params
        params = _parse_request_params(request)
        api = params.get("api", "")
        method = params.get("method", "")

        if api == "SYNO.API.Auth" and method == "login":
            return httpx.Response(200, json={"success": True, "data": {"sid": "test_sid"}})

        if api == "SYNO.FileStation.Delete" and method == "delete":
            captured_params = params
            return httpx.Response(200, json={"success": True, "data": {}})

        return httpx.Response(404)

    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")
    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    fs = SynoFileStationClient(base)

    try:
        await fs.delete_path("/volume1/data/obsolete_file.tar.gz")

        assert captured_params.get("api") == "SYNO.FileStation.Delete"
        assert captured_params.get("method") == "delete"
        assert captured_params.get("version") == "2"

        raw_path = captured_params.get("path", "")
        # path должен быть сериализован в JSON-массив: '["/volume1/data/obsolete_file.tar.gz"]'
        parsed_paths = json.loads(raw_path)
        assert isinstance(parsed_paths, list)
        assert parsed_paths == ["/volume1/data/obsolete_file.tar.gz"]
    finally:
        await base.close()


@pytest.mark.asyncio
async def test_file_station_copy_or_move_start_json_payload(tmp_path: Path) -> None:
    """Проверяет запуск операции перемещения с сериализацией массивов и флагов."""
    captured_params: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_params
        params = _parse_request_params(request)
        api = params.get("api", "")
        method = params.get("method", "")

        if api == "SYNO.API.Auth" and method == "login":
            return httpx.Response(200, json={"success": True, "data": {"sid": "test_sid"}})

        if api == "SYNO.FileStation.CopyMove" and method == "start":
            captured_params = params
            return httpx.Response(
                200,
                json={"success": True, "data": {"taskid": "async_task_12345"}},
            )

        return httpx.Response(404)

    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")
    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    fs = SynoFileStationClient(base)

    try:
        res = await fs.copy_or_move(
            src_path="/volume1/source/archive.zip",
            dest_folder_path="/volume2/dest_folder",
            remove_src=True,  # Режим перемещения (mv)
        )

        assert res.get("taskid") == "async_task_12345"
        assert captured_params.get("api") == "SYNO.FileStation.CopyMove"
        assert captured_params.get("method") == "start"
        assert captured_params.get("dest_folder_path") == "/volume2/dest_folder"
        assert captured_params.get("remove_src") in ("true", "True")
        assert captured_params.get("overwrite") in ("true", "True")

        parsed_paths = json.loads(captured_params.get("path", ""))
        assert parsed_paths == ["/volume1/source/archive.zip"]
    finally:
        await base.close()


# ---------------------------------------------------------------------------
# 2. Тесты асинхронных задач (CopyMove polling)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_file_station_wait_copy_move_polling(tmp_path: Path) -> None:
    """Проверяет цикл опроса асинхронной задачи до получения флага finished=True."""
    poll_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal poll_count
        params = _parse_request_params(request)
        api = params.get("api", "")
        method = params.get("method", "")

        if api == "SYNO.API.Auth" and method == "login":
            return httpx.Response(200, json={"success": True, "data": {"sid": "test_sid"}})

        if api == "SYNO.FileStation.CopyMove" and method == "status":
            poll_count += 1
            if poll_count == 1:
                return httpx.Response(
                    200,
                    json={
                        "success": True,
                        "data": {
                            "taskid": "task_99",
                            "finished": False,
                            "progress": 0.45,
                            "processed_size": 45000000,
                            "total": 100000000,
                        },
                    },
                )
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "taskid": "task_99",
                        "finished": True,
                        "progress": 1.0,
                        "processed_size": 100000000,
                        "total": 100000000,
                    },
                },
            )

        return httpx.Response(404)

    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")
    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    fs = SynoFileStationClient(base)

    try:
        final_status = await fs.wait_copy_move("task_99", poll_interval=0.01, timeout=2.0)
        assert poll_count == 2
        assert final_status.get("finished") is True
        assert final_status.get("progress") == 1.0
        assert final_status.get("taskid") == "task_99"
    finally:
        await base.close()


@pytest.mark.asyncio
async def test_file_station_wait_copy_move_timeout(tmp_path: Path) -> None:
    """Проверяет возбуждение TimeoutError при зависании асинхронной задачи."""

    def handler(request: httpx.Request) -> httpx.Response:
        params = _parse_request_params(request)
        if params.get("api") == "SYNO.API.Auth":
            return httpx.Response(200, json={"success": True, "data": {"sid": "test_sid"}})

        if params.get("api") == "SYNO.FileStation.CopyMove":
            return httpx.Response(
                200,
                json={"success": True, "data": {"finished": False, "progress": 0.1}},
            )
        return httpx.Response(404)

    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")
    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    fs = SynoFileStationClient(base)

    try:
        with pytest.raises(TimeoutError, match="Превышен таймаут ожидания"):
            await fs.wait_copy_move("stalled_task", poll_interval=0.01, timeout=0.03)
    finally:
        await base.close()


# ---------------------------------------------------------------------------
# 3. Тесты создания публичных ссылок обмена (Sharing)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_file_station_create_sharing_link_full_options(tmp_path: Path) -> None:
    """Проверяет вызов SYNO.FileStation.Sharing:create с паролем и датой истечения."""
    captured_params: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_params
        params = _parse_request_params(request)
        api = params.get("api", "")
        method = params.get("method", "")

        if api == "SYNO.API.Auth" and method == "login":
            return httpx.Response(200, json={"success": True, "data": {"sid": "test_sid"}})

        if api == "SYNO.FileStation.Sharing" and method == "create":
            captured_params = params
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "links": [
                            {
                                "id": "sharing_id_abc123",
                                "url": "https://gofile.me/6XYZ/abc123",
                                "date_expired": "2026-12-31",
                                "has_password": True,
                            }
                        ]
                    },
                },
            )

        return httpx.Response(404)

    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")
    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    fs = SynoFileStationClient(base)

    try:
        result = await fs.create_sharing_link(
            path="/volume1/public/presentation.pdf",
            password="SecurePass2026!",
            date_expired="2026-12-31",
        )

        assert captured_params.get("api") == "SYNO.FileStation.Sharing"
        assert captured_params.get("method") == "create"
        assert captured_params.get("password") == "SecurePass2026!"
        assert captured_params.get("date_expired") == "2026-12-31"

        raw_path = captured_params.get("path", "")
        parsed_paths = json.loads(raw_path)
        assert parsed_paths == ["/volume1/public/presentation.pdf"]

        links = result.get("links", [])
        assert len(links) == 1
        assert links[0]["url"] == "https://gofile.me/6XYZ/abc123"
        assert links[0]["has_password"] is True
    finally:
        await base.close()


@pytest.mark.asyncio
async def test_file_station_create_sharing_link_minimal(tmp_path: Path) -> None:
    """Проверяет создание ссылки без пароля и ограничения срока действия."""
    captured_params: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_params
        params = _parse_request_params(request)
        if params.get("api") == "SYNO.API.Auth":
            return httpx.Response(200, json={"success": True, "data": {"sid": "test_sid"}})

        if params.get("api") == "SYNO.FileStation.Sharing":
            captured_params = params
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {"links": [{"url": "https://gofile.me/6XYZ/simple"}]},
                },
            )
        return httpx.Response(404)

    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")
    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    fs = SynoFileStationClient(base)

    try:
        result = await fs.create_sharing_link("/volume1/public/open_doc.txt")
        assert "password" not in captured_params
        assert "date_expired" not in captured_params
        assert json.loads(captured_params["path"]) == ["/volume1/public/open_doc.txt"]
        assert result["links"][0]["url"] == "https://gofile.me/6XYZ/simple"
    finally:
        await base.close()
