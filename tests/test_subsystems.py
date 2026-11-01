"""Тесты клиентов Docker, Virtual Machine Manager, File Station и Download Station."""

from pathlib import Path
from urllib.parse import parse_qs
import httpx
import pytest

from syno_cli.client.base import BaseSynoClient
from syno_cli.client.docker import SynoDockerClient
from syno_cli.client.download_station import SynoDownloadStationClient
from syno_cli.client.file_station import SynoFileStationClient
from syno_cli.client.vmm import SynoVmmClient
from syno_cli.config import SynoSettings


@pytest.mark.asyncio
async def test_docker_and_vmm_operations(tmp_path) -> None:
    """Проверяет операции pull/create в Docker и создание ВМ/импорт образа в VMM."""
    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")
    recorded_calls: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            form = {k: v[0] for k, v in parse_qs(request.content.decode("utf-8")).items()}
        else:
            form = dict(request.url.params)

        api = form.get("api") or request.url.params.get("api", "")
        method = form.get("method") or request.url.params.get("method", "")
        recorded_calls.append({"api": api, "method": method})

        if api == "SYNO.API.Auth":
            return httpx.Response(200, json={"success": True, "data": {"sid": "test_sid"}})
        if api == "SYNO.Docker.Image" and method == "pull_start":
            return httpx.Response(200, json={"success": True, "data": {"task_id": "pull_1"}})
        if api == "SYNO.Docker.Container" and method in ("create", "start"):
            return httpx.Response(200, json={"success": True, "data": {"name": "web"}})
        if api == "SYNO.Virtualization.API.Guest.Image" and method == "create":
            return httpx.Response(200, json={"success": True, "data": {"image_id": "img_1"}})
        if api == "SYNO.Virtualization.API.Guest" and method == "create":
            return httpx.Response(200, json={"success": True, "data": {"guest_id": "vm_1"}})

        return httpx.Response(200, json={"success": True, "data": {}})

    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    docker = SynoDockerClient(base)
    vmm = SynoVmmClient(base)

    try:
        pull_res = await docker.pull_image("nginx", "alpine")
        assert pull_res["task_id"] == "pull_1"

        await docker.create_container(
            name="web",
            image="nginx:alpine",
            ports=["8080:80"],
            volumes=["/docker/web:/usr/share/nginx/html"],
            env_vars=["ENV=prod"],
        )

        img_res = await vmm.import_image("ubuntu-iso", "/isos/ubuntu.iso", "iso")
        assert img_res["image_id"] == "img_1"

        vm_res = await vmm.create_guest(
            name="ubuntu-vm",
            vcpu_num=4,
            vram_size_mb=4096,
            storage_name="StoragePool1",
            iso_image_name="ubuntu-iso",
        )
        assert vm_res["guest_id"] == "vm_1"
    finally:
        await base.close()


@pytest.mark.asyncio
async def test_files_and_downloads(tmp_path) -> None:
    """Проверяет листинг/загрузку файлов в File Station и очередь Download Station."""
    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")
    sample_file: Path = tmp_path / "hello.txt"
    sample_file.write_text("Hello Synology!", encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        api = request.url.params.get("api")
        if not api and request.method == "POST":
            parsed = parse_qs(request.content.decode("utf-8", errors="ignore"))
            api = parsed.get("api", [""])[0]

        if api == "SYNO.API.Auth":
            return httpx.Response(200, json={"success": True, "data": {"sid": "sid_ok"}})
        if api == "SYNO.FileStation.List":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "files": [{"name": "hello.txt", "path": "/docker/hello.txt", "isdir": False}]
                    },
                },
            )
        if api == "SYNO.FileStation.Upload":
            return httpx.Response(200, json={"success": True, "data": {"blSkip": False}})
        if api == "SYNO.DownloadStation.Statistic":
            return httpx.Response(
                200,
                json={"success": True, "data": {"speed_download": 1048576, "speed_upload": 512000}},
            )
        if api == "SYNO.DownloadStation.Task":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "tasks": [
                            {
                                "id": "dbid_1",
                                "title": "ubuntu-26.04.iso",
                                "status": "downloading",
                                "size": 2097152,
                                "additional": {
                                    "transfer": {"size_downloaded": 1048576, "speed_download": 1048576}
                                },
                            }
                        ]
                    },
                },
            )
        return httpx.Response(200, json={"success": True, "data": {}})

    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    fs = SynoFileStationClient(base)
    ds = SynoDownloadStationClient(base)

    try:
        files = await fs.list_dir("/docker")
        assert len(files) == 1
        assert files[0]["name"] == "hello.txt"

        up = await fs.upload_file(sample_file, "/docker")
        assert up.get("blSkip") is False

        stats = await ds.get_statistic()
        assert stats["speed_download"] == 1048576

        tasks = await ds.list_tasks()
        assert len(tasks) == 1
        assert tasks[0]["title"] == "ubuntu-26.04.iso"
    finally:
        await base.close()
