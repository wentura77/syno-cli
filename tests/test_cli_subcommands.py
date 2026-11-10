"""Тестирование CLI-подкоманд (files, docker, download, vm, storage) и обработчика ошибок."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from pydantic import BaseModel
from typer.testing import CliRunner

from syno_cli.commands.main import app
from syno_cli.constants import ExitCode

runner = CliRunner()


# ---------------------------------------------------------------------------
# 1. Централизованный диспетчер ошибок и флаг --json
# ---------------------------------------------------------------------------


class _SampleModel(BaseModel):
    required_num: int


def test_cli_error_dispatcher_validation_error() -> None:
    """Проверяет возврат ExitCode.VALIDATION_ERROR (3) при ошибках схемы Pydantic."""
    with patch("syno_cli.commands.system_cmd.SynoDSM") as mock_dsm:
        instance = mock_dsm.return_value.__aenter__.return_value

        async def _raise_val_err() -> None:
            _SampleModel.model_validate({"required_num": "not_an_int"})

        instance.core.get_system_info = AsyncMock(side_effect=_raise_val_err)

        result = runner.invoke(app, ["status", "--json"])
        assert result.exit_code == ExitCode.VALIDATION_ERROR
        err_json = json.loads(result.stderr)
        assert err_json["error"] == "ValidationError"


def test_cli_error_dispatcher_unexpected_error_modes() -> None:
    """Проверяет возврат ExitCode.UNEXPECTED_ERROR (5) в обычном режиме и в JSON."""
    with patch("syno_cli.commands.system_cmd.SynoDSM") as mock_dsm:
        instance = mock_dsm.return_value.__aenter__.return_value
        instance.core.get_system_info = AsyncMock(side_effect=RuntimeError("Fatal core breakdown"))

        # 1. Режим без --json (вывод в stderr через Rich)
        res_rich = runner.invoke(app, ["status"])
        assert res_rich.exit_code == ExitCode.UNEXPECTED_ERROR
        assert "Непредвиденный сбой" in res_rich.stderr

        # 2. Режим c --json (валидный JSON в stderr)
        res_json = runner.invoke(app, ["status", "--json"])
        assert res_json.exit_code == ExitCode.UNEXPECTED_ERROR
        payload = json.loads(res_json.stderr)
        assert payload["error"] == "UnexpectedError"
        assert "Fatal core breakdown" in payload["detail"]


# ---------------------------------------------------------------------------
# 2. Команды File Station (ls, mkdir, rm, upload, download)
# ---------------------------------------------------------------------------


def test_cli_files_ls_and_mkdir_and_rm() -> None:
    """Проверяет команды files ls, mkdir и rm."""
    mock_items = [
        {"name": "file.bin", "isdir": False, "additional": {"size": 100, "time": {}}},
        {"name": "folder", "isdir": True, "additional": {"size": 0, "time": {}}},
    ]

    with patch("syno_cli.commands.files_cmd.SynoDSM") as mock_dsm:
        inst = mock_dsm.return_value.__aenter__.return_value
        inst.files.list_dir = AsyncMock(return_value=mock_items)
        inst.files.mkdir = AsyncMock(return_value={"created": True})
        inst.files.delete_path = AsyncMock(return_value={"deleted": True})

        # ls --json
        res_ls = runner.invoke(app, ["files", "ls", "/volume1/data", "--sort", "size", "--json"])
        assert res_ls.exit_code == ExitCode.SUCCESS
        assert len(json.loads(res_ls.stdout)) == 2

        # mkdir
        res_mkdir = runner.invoke(app, ["files", "mkdir", "/volume1/data", "backup_dir"])
        assert res_mkdir.exit_code == ExitCode.SUCCESS
        assert "создана" in res_mkdir.stdout

        # rm
        res_rm = runner.invoke(app, ["files", "rm", "/volume1/data/old.tar"])
        assert res_rm.exit_code == ExitCode.SUCCESS
        assert "Удалено" in res_rm.stdout


def test_cli_files_upload_missing_file_raises(tmp_path: Path) -> None:
    """Проверяет возврат ExitCode.NETWORK_ERROR при отсутствии локального файла."""
    missing = tmp_path / "absent_file.iso"
    result = runner.invoke(app, ["files", "upload", str(missing), "/volume1/dest"])
    assert result.exit_code == ExitCode.NETWORK_ERROR
    assert "Локальный файл не найден" in result.stderr


def test_cli_files_download(tmp_path: Path) -> None:
    """Проверяет команду files download."""
    dest_dir = tmp_path / "downloads"
    dest_dir.mkdir()
    fake_saved = dest_dir / "target.zip"

    with patch("syno_cli.commands.files_cmd.SynoDSM") as mock_dsm:
        inst = mock_dsm.return_value.__aenter__.return_value
        inst.files.download_file = AsyncMock(return_value=fake_saved)

        result = runner.invoke(
            app,
            ["files", "download", "/volume1/target.zip", "--dest", str(dest_dir), "--json"],
        )
        assert result.exit_code == ExitCode.SUCCESS
        data = json.loads(result.stdout)
        assert "saved_path" in data


# ---------------------------------------------------------------------------
# 3. Команды Container Manager (Docker & Compose)
# ---------------------------------------------------------------------------


def test_cli_docker_ps_stats_and_pull() -> None:
    """Проверяет docker ps, docker stats и разбор тегов в docker pull."""
    with patch("syno_cli.commands.docker_cmd.SynoDSM") as mock_dsm:
        inst = mock_dsm.return_value.__aenter__.return_value
        inst.docker.list_containers = AsyncMock(return_value=[{"name": "c1", "status": "running"}])
        inst.docker.get_container_stats = AsyncMock(return_value=[{"name": "c1", "cpu": 5.0}])
        inst.docker.pull_image = AsyncMock(return_value={"job_id": 123})

        # ps
        res_ps = runner.invoke(app, ["docker", "ps", "--json"])
        assert res_ps.exit_code == ExitCode.SUCCESS
        assert json.loads(res_ps.stdout)[0]["name"] == "c1"

        # stats
        res_stats = runner.invoke(app, ["docker", "stats", "c1", "--json"])
        assert res_stats.exit_code == ExitCode.SUCCESS
        assert json.loads(res_stats.stdout)[0]["cpu"] == 5.0

        # pull с неявным тегом latest
        res_pull1 = runner.invoke(app, ["docker", "pull", "nginx"])
        assert res_pull1.exit_code == ExitCode.SUCCESS
        inst.docker.pull_image.assert_awaited_with("nginx", "latest")

        # pull с явным тегом
        res_pull2 = runner.invoke(app, ["docker", "pull", "redis:7.2-alpine"])
        assert res_pull2.exit_code == ExitCode.SUCCESS
        inst.docker.pull_image.assert_awaited_with("redis", "7.2-alpine")


def test_cli_docker_run_and_lifecycle() -> None:
    """Проверяет запуск, остановку, рестарт, удаление контейнеров и парсинг флагов run."""
    with patch("syno_cli.commands.docker_cmd.SynoDSM") as mock_dsm:
        inst = mock_dsm.return_value.__aenter__.return_value
        inst.docker.create_container = AsyncMock(return_value={"id": "new_id"})
        inst.docker.start_container = AsyncMock(return_value={"success": True})
        inst.docker.stop_container = AsyncMock(return_value={"success": True})
        inst.docker.restart_container = AsyncMock(return_value={"success": True})
        inst.docker.delete_container = AsyncMock(return_value={"success": True})

        # run
        res_run = runner.invoke(
            app,
            [
                "docker", "run",
                "-n", "web",
                "-i", "nginx:alpine",
                "-p", "8080:80",
                "-v", "/vol/html:/usr/share/nginx/html",
                "-e", "ENV=prod",
            ],
        )
        assert res_run.exit_code == ExitCode.SUCCESS
        inst.docker.create_container.assert_awaited_with(
            name="web",
            image="nginx:alpine",
            ports=["8080:80"],
            volumes=["/vol/html:/usr/share/nginx/html"],
            env_vars=["ENV=prod"],
            auto_start=True,
        )

        # start / stop / restart / rm
        assert runner.invoke(app, ["docker", "start", "web"]).exit_code == ExitCode.SUCCESS
        assert runner.invoke(app, ["docker", "stop", "web"]).exit_code == ExitCode.SUCCESS
        assert runner.invoke(app, ["docker", "restart", "web"]).exit_code == ExitCode.SUCCESS

        res_rm = runner.invoke(app, ["docker", "rm", "web", "--force"])
        assert res_rm.exit_code == ExitCode.SUCCESS
        inst.docker.delete_container.assert_awaited_with("web", force=True)


def test_cli_docker_compose_lifecycle(tmp_path: Path) -> None:
    """Проверяет команды управления проектами Docker Compose (list, down, restart, logs)."""
    with patch("syno_cli.commands.docker_cmd.SynoDSM") as mock_dsm:
        inst = mock_dsm.return_value.__aenter__.return_value
        inst.docker.list_projects = AsyncMock(return_value=[{"name": "app_stack", "status": "running"}])
        inst.docker.stop_project = AsyncMock(return_value={"success": True})
        inst.docker.restart_project = AsyncMock(return_value={"success": True})
        inst.docker.get_project_logs = AsyncMock(return_value=["[app] Started"])

        # list
        res_list = runner.invoke(app, ["docker", "compose", "list", "--json"])
        assert res_list.exit_code == ExitCode.SUCCESS
        assert json.loads(res_list.stdout)[0]["name"] == "app_stack"

        # down / restart / logs
        assert runner.invoke(app, ["docker", "compose", "down", "app_stack"]).exit_code == ExitCode.SUCCESS
        assert runner.invoke(app, ["docker", "compose", "restart", "app_stack"]).exit_code == ExitCode.SUCCESS

        res_logs = runner.invoke(app, ["docker", "compose", "logs", "app_stack", "--lines", "10", "--json"])
        assert res_logs.exit_code == ExitCode.SUCCESS
        assert json.loads(res_logs.stdout) == ["[app] Started"]


# ---------------------------------------------------------------------------
# 4. Команды Download Station (list, add, pause, resume, delete)
# ---------------------------------------------------------------------------


def test_cli_download_commands() -> None:
    """Проверяет весь жизненный цикл задач Download Station в CLI."""
    with patch("syno_cli.commands.download_cmd.SynoDSM") as mock_dsm:
        inst = mock_dsm.return_value.__aenter__.return_value
        inst.downloads.get_statistic = AsyncMock(return_value={"speed_download": 500, "speed_upload": 100})
        inst.downloads.list_tasks = AsyncMock(return_value=[{"id": "t1", "title": "test.iso"}])
        inst.downloads.add_task = AsyncMock(return_value={"task_id": "t2"})
        inst.downloads.pause_task = AsyncMock(return_value={"success": True})
        inst.downloads.resume_task = AsyncMock(return_value={"success": True})
        inst.downloads.delete_task = AsyncMock(return_value={"success": True})

        # list
        res_list = runner.invoke(app, ["download", "list", "--json"])
        assert res_list.exit_code == ExitCode.SUCCESS
        data = json.loads(res_list.stdout)
        assert data["stats"]["speed_download"] == 500
        assert data["tasks"][0]["id"] == "t1"

        # add
        res_add = runner.invoke(app, ["download", "add", "magnet:?xt=urn:btih:123", "--dest", "downloads/torrents"])
        assert res_add.exit_code == ExitCode.SUCCESS
        inst.downloads.add_task.assert_awaited_with("magnet:?xt=urn:btih:123", destination="downloads/torrents")

        # pause / resume / delete
        assert runner.invoke(app, ["download", "pause", "t1"]).exit_code == ExitCode.SUCCESS
        assert runner.invoke(app, ["download", "resume", "t1"]).exit_code == ExitCode.SUCCESS

        res_del = runner.invoke(app, ["download", "delete", "t1", "--force"])
        assert res_del.exit_code == ExitCode.SUCCESS
        inst.downloads.delete_task.assert_awaited_with("t1", force_complete=True)


# ---------------------------------------------------------------------------
# 5. Команды VMM и Storage (vm, storage)
# ---------------------------------------------------------------------------


def test_cli_vm_lifecycle() -> None:
    """Проверяет команды управления виртуальными машинами и образами VMM."""
    with patch("syno_cli.commands.vm_cmd.SynoDSM") as mock_dsm:
        inst = mock_dsm.return_value.__aenter__.return_value
        inst.vmm.list_guests = AsyncMock(return_value=[{"guest_name": "srv1"}])
        inst.vmm.list_images = AsyncMock(return_value=[{"image_name": "deb12.iso"}])
        inst.vmm.import_image = AsyncMock(return_value={"image_id": "img1"})
        inst.vmm.guest_power_action = AsyncMock(return_value={"success": True})
        inst.vmm.create_snapshot = AsyncMock(return_value={"snapshot_id": "s1"})

        # list / images
        assert runner.invoke(app, ["vm", "list", "--json"]).exit_code == ExitCode.SUCCESS
        assert runner.invoke(app, ["vm", "images", "--json"]).exit_code == ExitCode.SUCCESS

        # image-import
        res_imp = runner.invoke(app, ["vm", "image-import", "ubuntu", "/volume1/iso/u.iso", "--type", "iso"])
        assert res_imp.exit_code == ExitCode.SUCCESS
        inst.vmm.import_image.assert_awaited_with(
            image_name="ubuntu", ds_file_path="/volume1/iso/u.iso", image_type="iso", storage_names=None
        )

        # power actions: start, stop (shutdown), stop --force (poweroff), restart
        assert runner.invoke(app, ["vm", "start", "srv1"]).exit_code == ExitCode.SUCCESS
        inst.vmm.guest_power_action.assert_awaited_with("srv1", "poweron")

        assert runner.invoke(app, ["vm", "stop", "srv1"]).exit_code == ExitCode.SUCCESS
        inst.vmm.guest_power_action.assert_awaited_with("srv1", "shutdown")

        assert runner.invoke(app, ["vm", "stop", "srv1", "--force"]).exit_code == ExitCode.SUCCESS
        inst.vmm.guest_power_action.assert_awaited_with("srv1", "poweroff")

        assert runner.invoke(app, ["vm", "restart", "srv1"]).exit_code == ExitCode.SUCCESS
        inst.vmm.guest_power_action.assert_awaited_with("srv1", "restart")

        # snapshot
        res_snap = runner.invoke(app, ["vm", "snapshot", "srv1", "--desc", "Before update"])
        assert res_snap.exit_code == ExitCode.SUCCESS
        inst.vmm.create_snapshot.assert_awaited_with("srv1", description="Before update")


def test_cli_storage_disks() -> None:
    """Проверяет команду syno storage."""
    mock_storage = {"disks": [{"name": "Drive 1", "temp": 35}]}
    with patch("syno_cli.commands.system_cmd.SynoDSM") as mock_dsm:
        inst = mock_dsm.return_value.__aenter__.return_value
        inst.core.get_storage_info = AsyncMock(return_value=mock_storage)

        result = runner.invoke(app, ["storage", "--json"])
        assert result.exit_code == ExitCode.SUCCESS
        data = json.loads(result.stdout)
        assert data["disks"][0]["temp"] == 35


def test_cli_docker_inspect_json() -> None:
    """Проверяет команду 'syno docker inspect <name> --json' на валидность JSON и код выхода 0."""
    mock_inspect_data = {
        "profile": {
            "name": "my-container",
            "image": "redis:alpine",
            "memory_limit": 134217728,
            "port_bindings": [{"container_port": 6379, "host_port": 6379, "type": "tcp"}],
        },
        "details": {
            "Name": "/my-container",
            "State": {"Status": "running"},
            "NetworkSettings": {
                "Networks": {
                    "bridge": {
                        "IPAddress": "172.17.0.3",
                        "MacAddress": "02:42:ac:11:00:03",
                    }
                }
            },
        },
    }

    with patch("syno_cli.commands.docker_cmd.SynoDSM") as mock_dsm:
        instance = mock_dsm.return_value.__aenter__.return_value
        instance.docker.inspect_container = AsyncMock(return_value=mock_inspect_data)

        result = runner.invoke(app, ["docker", "inspect", "my-container", "--json"])

        assert result.exit_code == ExitCode.SUCCESS
        instance.docker.inspect_container.assert_awaited_once_with("my-container")

        payload = json.loads(result.stdout)
        assert payload["profile"]["name"] == "my-container"
        assert payload["details"]["State"]["Status"] == "running"
        assert payload["details"]["NetworkSettings"]["Networks"]["bridge"]["IPAddress"] == "172.17.0.3"
