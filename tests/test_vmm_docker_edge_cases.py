"""Тестирование пограничных сценариев и отказоустойчивости подсистем VMM и Docker."""

import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest
from typer.testing import CliRunner

from syno_cli.client.base import BaseSynoClient
from syno_cli.client.docker import (
    _parse_env_variables,
    _parse_port_bindings,
    _parse_volume_bindings,
)
from syno_cli.client.vmm import SynoVmmClient
from syno_cli.commands.main import app
from syno_cli.config import SynoSettings
from syno_cli.constants import BYTES_IN_KB

runner = CliRunner()


# ---------------------------------------------------------------------------
# 1. Юнит-тесты парсинга параметров Docker
# ---------------------------------------------------------------------------


def test_docker_parse_port_bindings() -> None:
    """Проверяет парсинг валидных и игнорирование некорректных портов."""
    raw_ports = [
        "8080:80",
        "invalid_port",
        "443:443",
        "too:many:parts:80",
        "",
    ]
    bindings = _parse_port_bindings(raw_ports)
    assert len(bindings) == 2
    assert bindings[0] == {"host_port": 8080, "container_port": 80, "protocol": "tcp"}
    assert bindings[1] == {"host_port": 443, "container_port": 443, "protocol": "tcp"}


def test_docker_parse_volume_bindings() -> None:
    """Проверяет маппинг томов и отсеивание некорректных строк."""
    raw_volumes = [
        "/volume1/docker/app:/data",
        "/invalid/no/target",
        "/etc/localtime:/etc/localtime",
        "too:many:colons:/path",
    ]
    binds = _parse_volume_bindings(raw_volumes)
    assert len(binds) == 2
    assert binds[0] == {
        "host_volume_file": "/volume1/docker/app",
        "mount_point": "/data",
        "type": "bind",
    }
    assert binds[1] == {
        "host_volume_file": "/etc/localtime",
        "mount_point": "/etc/localtime",
        "type": "bind",
    }


def test_docker_parse_env_variables() -> None:
    """Проверяет парсинг переменных окружения со сложными значениями и без знака равенства."""
    raw_envs = [
        "TZ=Europe/Berlin",
        "EMPTY_VAL=",
        "NO_EQUALS_KEY",
        "CONN_STR=postgresql://user:pass@localhost:5432/db?ssl=true",
    ]
    parsed = _parse_env_variables(raw_envs)
    assert len(parsed) == 4
    assert parsed[0] == {"key": "TZ", "value": "Europe/Berlin"}
    assert parsed[1] == {"key": "EMPTY_VAL", "value": ""}
    assert parsed[2] == {"key": "NO_EQUALS_KEY", "value": ""}
    assert parsed[3] == {
        "key": "CONN_STR",
        "value": "postgresql://user:pass@localhost:5432/db?ssl=true",
    }


# ---------------------------------------------------------------------------
# 2. VMM: Валидация формируемых структур vdisks и vnics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vmm_create_guest_structures_validation(tmp_path: Path) -> None:
    """Проверяет формирование параметров дисков и сети (MAC, сеть, веса)."""
    captured_params: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_params

        # Извлекаем параметры как из URL query, так и из тела POST
        params = dict(request.url.params)
        if request.method == "POST" and request.content:
            post_data = {k: v[0] for k, v in parse_qs(request.content.decode("utf-8")).items()}
            params.update(post_data)

        api = params.get("api", "")
        method = params.get("method", "")

        if api == "SYNO.API.Auth" and method == "login":
            return httpx.Response(200, json={"success": True, "data": {"sid": "vmm_sid"}})

        # Ответы автообнаружения кластера
        if api == "SYNO.Virtualization.Host":
            return httpx.Response(
                200, json={"success": True, "data": {"hosts": [{"host_id": "h1", "host_name": "Host-01"}]}}
            )
        if api == "SYNO.Virtualization.Repo":
            return httpx.Response(
                200, json={"success": True, "data": {"repos": [{"repo_id": "r1", "repo_name": "Storage-Pool-1"}]}}
            )
        if api == "SYNO.Virtualization.Network":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "networks": [
                            {"network_id": "net-default-uuid", "network_name": "Default Network"}
                        ]
                    },
                },
            )

        if api == "SYNO.Virtualization.Guest" and method == "create":
            captured_params = params
            return httpx.Response(200, json={"success": True, "data": {"guest_id": "g-101"}})

        return httpx.Response(404)

    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")
    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    vmm = SynoVmmClient(base)

    try:
        await vmm.create_guest(
            name="srv-prod-01",
            vcpu_num=4,
            vram_size_mb=4096,
            disk_size_gb=50,
            network="Default Network",
            mac="02:11:32:2a:73:ac",
            cpu_passthrough=True,
            hyperv=True,
            cpu_weight=512,
            cpu_pin=2,
            autorun=True,
            sync_time=True,
            desc="Prod VM Server",
        )

        assert captured_params.get("name") == '"srv-prod-01"'
        assert captured_params.get("vcpu_num") == "4"
        assert captured_params.get("vram_size") == "4096"
        assert captured_params.get("cpu_weight") == "512"
        assert captured_params.get("cpu_pin_num") == "2"
        assert captured_params.get("cpu_passthru") == "true"
        assert captured_params.get("hyperv_enlighten") == "true"
        assert captured_params.get("autorun") == "1"
        assert captured_params.get("auto_sync_guest_time") == "true"

        # Десериализация vdisks
        vdisks = json.loads(captured_params["vdisks"])
        assert len(vdisks) == 1
        assert vdisks[0]["vdisk_size"] == 50
        assert vdisks[0]["fua"] is True

        # Десериализация vnics
        vnics = json.loads(captured_params["vnics"])
        assert len(vnics) == 1
        assert vnics[0]["network_id"] == "net-default-uuid"
        assert vnics[0]["mac"] == "02:11:32:2a:73:ac"
        assert vnics[0]["vnic_type"] == 1
    finally:
        await base.close()


# ---------------------------------------------------------------------------
# 3. VMM: Проверка Fallback с SYNO.Virtualization.Guest на API.Guest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vmm_fallback_to_legacy_api_guest(tmp_path: Path) -> None:
    """Проверяет вызов SYNO.Virtualization.API.Guest при недоступности основного эндпоинта."""
    primary_called = False
    legacy_payload: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal primary_called, legacy_payload

        # Извлекаем параметры как из URL query, так и из тела POST
        params = dict(request.url.params)
        if request.method == "POST" and request.content:
            post_data = {k: v[0] for k, v in parse_qs(request.content.decode("utf-8")).items()}
            params.update(post_data)

        api = params.get("api", "")
        method = params.get("method", "")

        if api == "SYNO.API.Auth" and method == "login":
            return httpx.Response(200, json={"success": True, "data": {"sid": "vmm_sid"}})

        # Кластер возвращает пустые списки
        if api in ("SYNO.Virtualization.Host", "SYNO.Virtualization.Repo", "SYNO.Virtualization.Network"):
            return httpx.Response(200, json={"success": True, "data": {}})

        # Сбой основного эндпоинта (например, 102 API Not Found)
        if api == "SYNO.Virtualization.Guest" and method == "create":
            primary_called = True
            return httpx.Response(200, json={"success": False, "error": {"code": 102}})

        # Фолбэк-эндпоинт
        if api == "SYNO.Virtualization.API.Guest" and method == "create":
            legacy_payload = params
            return httpx.Response(200, json={"success": True, "data": {"guest_id": "legacy_vmm_01"}})

        return httpx.Response(404)

    cfg = SynoSettings(host="mock-nas", session_file=tmp_path / ".session.json")
    base = BaseSynoClient(config=cfg, transport=httpx.MockTransport(handler))
    vmm = SynoVmmClient(base)

    try:
        res = await vmm.create_guest(
            name="legacy-vm",
            vcpu_num=2,
            vram_size_mb=2048,
            disk_size_gb=30,
            storage_name="vol1_repo",
            iso_image_name="debian.iso",
        )

        assert primary_called is True
        assert res.get("guest_id") == "legacy_vmm_01"
        assert legacy_payload.get("guest_name") == "legacy-vm"
        assert legacy_payload.get("vcpu_num") == "2"
        assert legacy_payload.get("storage_name") == "vol1_repo"

        # В legacy API размер диска передается в байтах
        expected_bytes = 30 * int(BYTES_IN_KB**3)
        vdisks = json.loads(legacy_payload.get("vdisks", "[]"))
        assert vdisks[0]["vdisk_size"] == expected_bytes

        iso_images = json.loads(legacy_payload.get("iso_images", "[]"))
        assert iso_images == ["debian.iso", "unmounted"]
    finally:
        await base.close()


# ---------------------------------------------------------------------------
# 4. Docker Compose: Обработка отсутствующего файла docker-compose.yml
# ---------------------------------------------------------------------------


def test_compose_up_missing_file_raises_error(tmp_path: Path) -> None:
    """Проверяет выброс FileNotFoundError и завершение процесса при отсутствии compose-файла."""
    missing_file = tmp_path / "non_existent_docker_compose.yml"

    result = runner.invoke(app, ["docker", "compose", "up", "test-stack", str(missing_file)])

    assert result.exit_code != 0
    assert "Файл compose не найден" in result.stderr or "FileNotFoundError" in result.stderr
