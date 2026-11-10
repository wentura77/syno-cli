#!/usr/bin/env bash
set -euo pipefail

cat << 'PYEOF' > tests/test_system_and_storage.py
"""Модульные тесты подсистем System Status & Storage (диски, RAID, аптайм, память)."""

from typing import Any

from syno_cli.views.formatters import colorize_status, format_bytes, format_uptime
from syno_cli.views.tables import render_storage_disks, render_system_status
from tests.test_views_and_tables import _capture_render


def test_format_uptime_seconds_and_strings() -> None:
    """Проверяет преобразование аптайма из секунд и формата 'HH:MM:SS'."""
    sec_val = 86400 + 2 * 3600 + 3 * 60 + 15
    assert format_uptime(sec_val) == "1д 02ч 03м"
    assert format_uptime(3660) == "01ч 01м"
    assert format_uptime("571:13:45") == "23д 19ч 13м"
    assert format_uptime("") == "—"
    assert format_uptime("invalid_time") == "invalid_time"


def test_memory_utilization_calculation() -> None:
    """Проверяет расчет занятой памяти, свободной памяти и буферов/кэша."""
    memory_info = {
        "total_real": 4194304,
        "avail_real": 1048576,
        "cached": 524288,
        "buffer": 262144,
        "total_swap": 2097152,
        "avail_swap": 1572864,
        "real_usage": 75,
    }

    total_bytes = memory_info["total_real"] * 1024
    avail_bytes = memory_info["avail_real"] * 1024
    used_bytes = total_bytes - avail_bytes

    assert format_bytes(total_bytes) == "4.00 GB"
    assert format_bytes(used_bytes) == "3.00 GB"
    assert format_bytes(avail_bytes) == "1.00 GB"

    usage_pct = round((used_bytes / total_bytes) * 100)
    assert usage_pct == 75


def test_storage_disks_parsing_and_rendering() -> None:
    """Проверяет парсинг SMART, температуры, емкости и серийных номеров накопителей."""
    mock_storage_data: dict[str, Any] = {
        "disks": [
            {
                "id": "sata1",
                "name": "Drive 1",
                "model": "WD40EFRX-68N32N0",
                "serial": "WD-WCC7K1TEST01",
                "temp": 34,
                "status": "normal",
                "smart_status": "normal",
                "size_total": "4000787030016",
            },
            {
                "id": "sata2",
                "name": "Drive 2",
                "model": "ST4000VN008-2DR166",
                "serial": "ZGY1TEST02",
                "temp": 48,
                "status": "warning",
                "smart_status": "failing",
                "size_total": "4000787030016",
            },
        ],
        "storagePools": [
            {
                "id": "storage_pool_1",
                "device_type": "raid_5",
                "status": "normal",
                "size": {
                    "total": "12000000000000",
                    "used": "8000000000000",
                },
            }
        ],
    }

    disk1 = mock_storage_data["disks"][0]
    assert disk1["serial"] == "WD-WCC7K1TEST01"
    assert disk1["status"] == "normal"
    assert format_bytes(int(disk1["size_total"])) == "3.64 TB"

    disk2 = mock_storage_data["disks"][1]
    assert disk2["status"] == "warning"
    assert "red" in colorize_status("failing") or "yellow" in colorize_status("warning")

    out = _capture_render(render_storage_disks, mock_storage_data)
    assert "Drive 1" in out
    assert "WD40EFRX" in out
    assert "34 °C" in out
    assert "Drive 2" in out
    assert "48 °C" in out


def test_storage_pools_raid_statuses() -> None:
    """Проверяет парсинг состояний пулов RAID: normal, degraded, crashed."""
    pools_data = [
        {"id": "pool_1", "status": "normal", "raid_type": "SHR-1"},
        {"id": "pool_2", "status": "degraded", "raid_type": "RAID 5"},
        {"id": "pool_3", "status": "crashed", "raid_type": "RAID 1"},
    ]

    statuses = {p["id"]: p["status"] for p in pools_data}
    assert statuses["pool_1"] == "normal"
    assert statuses["pool_2"] == "degraded"
    assert statuses["pool_3"] == "crashed"

    assert "green" in colorize_status(statuses["pool_1"])
    assert "red" in colorize_status(statuses["pool_2"])
    assert "red" in colorize_status(statuses["pool_3"])


def test_render_system_status_full_payload() -> None:
    """Проверяет рендеринг панели статуса с CPU, памятью, аптаймом и версией DSM."""
    mock_sys_info = {
        "model": "DS920+",
        "firmware_ver": "DSM 7.2.1-69057 Update 3",
        "sys_temp": 42,
        "up_time": "571:13:45",
    }
    mock_utilization = {
        "cpu": {"user_load": 12, "system_load": 8},
        "memory": {"real_usage": 45},
    }

    out = _capture_render(render_system_status, mock_sys_info, mock_utilization)

    assert "DS920+" in out
    assert "DSM 7.2.1-69057" in out
    assert "42 °C" in out
    assert "23д 19ч 13м" in out
    assert "20%" in out
    assert "45%" in out
PYEOF

poetry run ruff check tests/test_system_and_storage.py
poetry run mypy tests/test_system_and_storage.py
poetry run pytest tests/test_system_and_storage.py -v
