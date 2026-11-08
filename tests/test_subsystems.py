"""Тесты для специализированных подсистем: Docker, VMM, Download Station."""

from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from syno_cli.client.base import BaseSynoClient
from syno_cli.client.docker import SynoDockerClient
from syno_cli.client.download_station import SynoDownloadStationClient
from syno_cli.client.logs import SynoLogsClient
from syno_cli.client.vmm import SynoVmmClient
from syno_cli.config import SynoSettings


@pytest.mark.asyncio
async def test_docker_and_vmm_operations(tmp_path: Path) -> None:
    """Проверяет базовые и расширенные операции Docker и VMM."""
    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")
    recorded_calls: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        form: dict[str, Any] = {}
        if request.method == "POST":
            form = {k: v[0] for k, v in parse_qs(request.content.decode("utf-8")).items()}
        else:
            form = dict(request.url.params)

        api = form.get("api") or request.url.params.get("api", "")
        method = form.get("method") or request.url.params.get("method", "")
        recorded_calls.append({"api": api, "method": method, "form": form})

        if api == "SYNO.API.Auth":
            return httpx.Response(200, json={"success": True, "data": {"sid": "test_sid"}})

        # Docker: Image
        if api == "SYNO.Docker.Image" and method in ("pull_start", "pull"):
            return httpx.Response(200, json={"success": True, "data": {"task_id": "pull_1"}})
        if api == "SYNO.Docker.Image" and method == "list":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {"images": [{"repository": "nginx", "tag": "latest"}]},
                },
            )

        # Docker: Container
        if api == "SYNO.Docker.Container" and method in (
            "create",
            "start",
            "stop",
            "restart",
            "pause",
            "unpause",
        ):
            return httpx.Response(200, json={"success": True, "data": {"name": "web"}})
        if api == "SYNO.Docker.Container" and method == "delete":
            name_param = form.get("name", "")
            force_param = form.get("force", "")
            if name_param.startswith('"') and force_param in ("true", "false"):
                return httpx.Response(200, json={"success": True, "data": {}})
            return httpx.Response(200, json={"success": False, "error": {"code": 114}})

        # Docker: Resource (stats)
        if api == "SYNO.Docker.Container.Resource" and method == "get":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "resources": [
                            {
                                "name": "web",
                                "cpu": 12.5,
                                "memory": 104857600,
                                "network_rx_bytes": 1024,
                                "network_tx_bytes": 2048,
                            }
                        ]
                    },
                },
            )

        # Docker: Logs
        if api == "SYNO.Docker.Container.Log" and method == "get":
            if form.get("sort_dir") == '"DESC"':
                return httpx.Response(
                    200,
                    json={
                        "success": True,
                        "data": {
                            "logs": [
                                {"text": "Log line 2", "stream": "stdout"},
                                {"text": "Log line 1", "stream": "stderr"},
                            ]
                        },
                    },
                )
            return httpx.Response(200, json={"success": False, "error": {"code": 117}})

        # Docker: Compose Projects
        if api == "SYNO.Docker.Project" and method == "list":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "projects": [
                            {"name": "stack1", "status": "running", "services": ["app", "db"]}
                        ]
                    },
                },
            )
        if api == "SYNO.Docker.Project" and method in ("build", "clean", "restart"):
            return httpx.Response(200, json={"success": True, "data": {}})
        if api == "SYNO.Docker.Project" and method == "get_log":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {"logs": [{"log": "compose log line", "stream": "stdout"}]},
                },
            )

        # VMM: Image & Guest
        if api == "SYNO.Virtualization.API.Guest.Image" and method in ("create", "import"):
            return httpx.Response(200, json={"success": True, "data": {"image_id": "img_1"}})
        if api == "SYNO.Virtualization.API.Guest" and method == "create":
            return httpx.Response(200, json={"success": True, "data": {"guest_id": "vm_1"}})

        return httpx.Response(200, json={"success": True, "data": {}})

    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    docker = SynoDockerClient(base)
    vmm = SynoVmmClient(base)

    try:
        # 1. Docker Images pull
        pull_res = await docker.pull_image("nginx", "alpine")
        assert pull_res.get("task_id") == "pull_1"

        # 2. Docker Container Create
        c_res = await docker.create_container("web", "nginx:alpine")
        assert c_res.get("name") == "web"

        # 3. Docker Stats
        stats = await docker.get_container_stats("web")
        assert len(stats) == 1
        assert stats[0]["name"] == "web"
        assert stats[0]["cpu"] == 12.5

        # 4. Docker Logs (проверяем переворот DESC в естественный порядок)
        logs = await docker.get_container_logs("web", tail=10)
        assert len(logs) == 2
        assert logs[0] == "[stderr] Log line 1"
        assert logs[1] == "[stdout] Log line 2"

        # 5. Docker Delete (rm)
        del_res = await docker.delete_container("web", force=True)
        assert isinstance(del_res, dict)

        # 6. Docker Compose Projects
        projects = await docker.list_projects()
        assert len(projects) == 1
        assert projects[0]["name"] == "stack1"

        build_res = await docker.build_or_start_project("stack1", "services: {}")
        assert isinstance(build_res, dict)

        comp_logs = await docker.get_project_logs("stack1", tail=10)
        assert len(comp_logs) == 1
        assert "[stdout] compose log line" in comp_logs[0]

        # 7. VMM operations
        img_res = await vmm.import_image("ubuntu.iso", "/volume1/iso/ubuntu.iso")
        assert isinstance(img_res, dict)

        vm_res = await vmm.create_guest(
            "test-vm", vcpu_num=2, vram_size_mb=2048, storage_name="default"
        )
        assert isinstance(vm_res, dict)
    finally:
        await base.close()


@pytest.mark.asyncio
async def test_download_station_destination_normalization(tmp_path: Path) -> None:
    """Проверяет нормализацию пути destination при добавлении задачи Download Station."""
    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")
    sent_destinations: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        form = (
            {k: v[0] for k, v in parse_qs(request.content.decode("utf-8")).items()}
            if request.method == "POST"
            else dict(request.url.params)
        )
        api = form.get("api") or request.url.params.get("api", "")
        method = form.get("method") or request.url.params.get("method", "")

        if api == "SYNO.API.Auth":
            return httpx.Response(200, json={"success": True, "data": {"sid": "test_sid"}})

        if api == "SYNO.DownloadStation.Task" and method == "create":
            sent_destinations.append(form.get("destination", ""))
            return httpx.Response(200, json={"success": True, "data": {}})

        return httpx.Response(200, json={"success": True, "data": {}})

    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    ds = SynoDownloadStationClient(base)

    try:
        # Обратный слэш на конце
        await ds.add_task("http://example.com/file1.iso", destination="video/Films\\")
        # Прямой слэш на конце и ведущий слэш
        await ds.add_task("http://example.com/file2.iso", destination="/video/Films/")

        assert len(sent_destinations) == 2
        assert sent_destinations[0] == "video/Films"
        assert sent_destinations[1] == "video/Films"
    finally:
        await base.close()


@pytest.mark.asyncio
async def test_syslog_operations(tmp_path: Path) -> None:
    """Проверяет получение системных журналов через SynoLogsClient."""
    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        api = params.get("api", "")
        if request.method == "POST":
            from urllib.parse import parse_qs

            form = {k: v[0] for k, v in parse_qs(request.content.decode("utf-8")).items()}
            api = form.get("api") or api

        if api == "SYNO.API.Auth":
            return httpx.Response(200, json={"success": True, "data": {"sid": "test_sid"}})

        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "items": [
                        {
                            "time": "2026-11-08 19:30:00",
                            "level": "warn",
                            "user": "admin",
                            "descr": "System booted up from abnormal power shutdown",
                        }
                    ]
                },
            },
        )

    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    logs_client = SynoLogsClient(base)
    try:
        logs = await logs_client.list_logs(level="warn", limit=10)
        assert len(logs) == 1
        assert logs[0]["user"] == "admin"
        assert logs[0]["level"] == "warn"
    finally:
        await base.close()
