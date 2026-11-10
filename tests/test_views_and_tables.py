"""Модульные тесты слоя форматирования (formatters.py) и генераторов таблиц (tables.py)."""

from io import StringIO
from typing import Any
from unittest.mock import patch

import pytest
from rich.console import Console

from syno_cli.views.formatters import (
    _parse_colon_uptime,
    colorize_status,
    format_bytes,
    format_speed,
    format_uptime,
)
from syno_cli.views.tables import (
    _file_sort_key,
    detect_file_type,
    format_timestamp,
    render_docker_containers,
    render_docker_images,
    render_docker_logs,
    render_docker_projects,
    render_docker_stats,
    render_downloads,
    render_files,
    render_storage_disks,
    render_system_logs,
    render_system_status,
    render_vmm_guests,
    render_vmm_images,
)


def _capture_render(render_fn: Any, *args: Any, **kwargs: Any) -> str:
    """Перехватывает вывод функций рендеринга Rich в строковый буфер."""
    buf = StringIO()
    test_console = Console(file=buf, force_terminal=False, width=120)
    with patch("syno_cli.views.tables.console", test_console):
        render_fn(*args, **kwargs)
    return buf.getvalue()


@pytest.mark.parametrize(
    ("size_bytes", "expected"),
    [
        (-500, "0 B"),
        (0, "0 B"),
        (512, "512 B"),
        (1024, "1.00 KB"),
        (1536, "1.50 KB"),
        (1024**2, "1.00 MB"),
        (1024**3, "1.00 GB"),
        (1024**4, "1.00 TB"),
        (1024**5, "1.00 PB"),
        (1024**6, "1024.00 PB"),
    ],
)
def test_format_bytes_edge_cases(size_bytes: int | float, expected: str) -> None:
    """Проверяет конвертацию байтов во все единицы измерения вплоть до петабайт."""
    assert format_bytes(size_bytes) == expected


def test_format_speed() -> None:
    """Проверяет форматирование скорости передачи данных."""
    assert format_speed(0) == "0 B/s"
    assert format_speed(1024 * 1024 * 12.5) == "12.50 MB/s"


def test_parse_colon_uptime_valid_and_invalid() -> None:
    """Проверяет разбор строкового аптайма с двоеточиями и выброс ValueError."""
    assert _parse_colon_uptime("01:02:03") == 3723
    assert _parse_colon_uptime("02:30") == 9000

    with pytest.raises(ValueError, match="Unsupported time format"):
        _parse_colon_uptime("10:20:30:40")


@pytest.mark.parametrize(
    ("uptime_val", "expected"),
    [
        (0, "00ч 00м"),
        (-100, "00ч 00м"),
        (3661, "01ч 01м"),
        (90061, "1д 01ч 01м"),
        ("3661", "01ч 01м"),
        ("571:13:45", "23д 19ч 13м"),
        ("05:30", "05ч 30м"),
        ("", "—"),
        ("   ", "—"),
        ("not_a_time", "not_a_time"),
        ("aa:bb:cc", "aa:bb:cc"),
    ],
)
def test_format_uptime_variants(uptime_val: int | str, expected: str) -> None:
    """Проверяет форматирование аптайма из чисел, строк с двоеточиями и невалидных строк."""
    assert format_uptime(uptime_val) == expected


@pytest.mark.parametrize(
    ("status", "expected_marker"),
    [
        ("running", "[bold green]● running[/bold green]"),
        ("HEALTHY", "[bold green]● HEALTHY[/bold green]"),
        ("downloading", "[bold yellow]◐ downloading[/bold yellow]"),
        ("Paused", "[bold yellow]◐ Paused[/bold yellow]"),
        ("stopped", "[bold red]○ stopped[/bold red]"),
        ("degraded", "[bold red]○ degraded[/bold red]"),
        ("custom_unknown", "custom_unknown"),
    ],
)
def test_colorize_status(status: str, expected_marker: str) -> None:
    """Проверяет цветовую разметку Rich для зеленых, желтых, красных и неизвестных статусов."""
    assert colorize_status(status) == expected_marker


@pytest.mark.parametrize(
    ("ts", "expected"),
    [
        (None, "—"),
        ("", "—"),
        ("—", "—"),
        (0, "—"),
        (-50, "—"),
        ("invalid_ts", "invalid_ts"),
    ],
)
def test_format_timestamp_edge_cases(ts: int | float | str | None, expected: str) -> None:
    """Проверяет граничные случаи форматирования временных меток Unix."""
    assert format_timestamp(ts) == expected


def test_format_timestamp_valid() -> None:
    """Проверяет корректное преобразование положительного Unix-timestamp."""
    rendered = format_timestamp(1700000000)
    assert len(rendered) == 16
    assert rendered.startswith("2023-11-")


@pytest.mark.parametrize(
    ("name", "is_dir", "expected"),
    [
        ("docker", True, "📁 DIR"),
        ("movie.mkv", False, "🎬 MKV"),
        ("archive.tar.gz", False, "📦 GZ"),
        ("script.py", False, "🐍 PY"),
        ("ubuntu.iso", False, "💿 ISO"),
        ("README", False, "📄 FILE"),
        ("data.unknownext", False, "📄 UNKN"),
    ],
)
def test_detect_file_type(name: str, is_dir: bool, expected: str) -> None:
    """Проверяет определение иконки и типа файла по флагу папки и расширению."""
    assert detect_file_type(name, is_dir) == expected


def test_file_sort_key_modes() -> None:
    """Проверяет ключи сортировки элементов File Station по имени, размеру и датам."""
    folder_item = {
        "name": "B_Folder",
        "isdir": True,
        "additional": {"size": 0, "time": {"mtime": 100, "crtime": 50}},
    }
    file_item = {
        "name": "A_File.txt",
        "isdir": False,
        "additional": {"size": 2048, "time": {"mtime": 500, "crtime": 400}},
    }

    assert _file_sort_key(folder_item, "name") == (0, "b_folder")
    assert _file_sort_key(file_item, "name") == (1, "a_file.txt")
    assert _file_sort_key(file_item, "size") == (1, 2048)
    assert _file_sort_key(file_item, "mtime") == (1, 500)
    assert _file_sort_key(file_item, "crtime") == (1, 400)


def test_render_system_status_and_storage() -> None:
    """Проверяет отрисовку сводной панели статуса NAS и таблицы дисков."""
    sys_info = {"model": "DS923+", "firmware_ver": "DSM 7.2.2", "sys_temp": 38, "up_time": 7200}
    util = {"cpu": {"user_load": 12, "system_load": 8}, "memory": {"real_usage": 45}}

    out_status = _capture_render(render_system_status, sys_info, util)
    assert "DS923+" in out_status
    assert "DSM 7.2.2" in out_status
    assert "20%" in out_status
    assert "45%" in out_status

    storage_data = {
        "disks": [
            {
                "name": "Drive 1",
                "model": "WD40EFZX",
                "size_total": 1024**4,
                "temp": 34,
                "status": "normal",
            }
        ]
    }
    out_storage = _capture_render(render_storage_disks, storage_data)
    assert "Drive 1" in out_storage
    assert "WD40EFZX" in out_storage
    assert "1.00 TB" in out_storage


def test_render_files_empty_and_populated() -> None:
    """Проверяет рендеринг пустого и заполненного каталога File Station."""
    out_empty = _capture_render(render_files, [], "/volume1/empty")
    assert "пуст" in out_empty

    items = [
        {
            "name": "compose.yaml",
            "path": "/docker/compose.yaml",
            "isdir": False,
            "additional": {"size": 1024, "time": {"mtime": 1700000000, "crtime": 1700000000}},
        },
        {
            "name": "appdata",
            "path": "/docker/appdata",
            "isdir": True,
            "additional": {"size": 0, "time": {}},
        },
    ]
    out_files = _capture_render(render_files, items, "/docker", sort_by="name", reverse=False)
    assert "compose.yaml" in out_files
    assert "appdata" in out_files
    assert "1.00 KB" in out_files


def test_render_docker_tables_empty_and_populated() -> None:
    """Проверяет отрисовку таблиц контейнеров, образов, статистики, логов и проектов Docker."""
    out_containers = _capture_render(
        render_docker_containers,
        [{"name": "redis", "image": "redis:alpine", "status": "running", "cpu_priority": 5, "memory": 1048576}],
    )
    assert "redis:alpine" in out_containers

    out_images = _capture_render(
        render_docker_images,
        [{"repository": "nginx", "tags": ["latest", "1.27"], "size": 52428800}],
    )
    assert "nginx" in out_images
    assert "50.00 MB" in out_images

    assert "Нет активных метрик" in _capture_render(render_docker_stats, [])
    out_stats = _capture_render(
        render_docker_stats,
        [{"name": "redis", "cpu": 1.25, "memory": 2097152, "net_rx": 1024, "net_tx": 2048}],
    )
    assert "1.25%" in out_stats
    assert "2.00 MB" in out_stats

    assert "пусты" in _capture_render(render_docker_logs, [])
    assert "[stdout] Ready" in _capture_render(render_docker_logs, ["[stdout] Ready"])

    assert "Нет созданных проектов" in _capture_render(render_docker_projects, [])
    out_projects = _capture_render(
        render_docker_projects,
        [
            {"name": "stack_up", "status": "running", "services": [1, 2], "path": "/docker/s1"},
            {"name": "stack_down", "status": "stopped", "services": [], "path": "/docker/s2"},
            {"name": "stack_other", "status": "building", "services": [1], "path": "/docker/s3"},
        ],
    )
    assert "stack_up" in out_projects
    assert "Запущен" in out_projects
    assert "Остановлен" in out_projects


def test_render_downloads_and_logs_and_vmm() -> None:
    """Проверяет рендеринг Download Station, системных журналов DSM и таблиц VMM."""
    tasks = [
        {
            "id": "dbid_1",
            "title": "ubuntu.iso",
            "status": "downloading",
            "size": 1000,
            "additional": {
                "detail": {"destination": "downloads/iso"},
                "transfer": {"size_downloaded": 500, "speed_download": 1024},
            },
        }
    ]
    out_dl = _capture_render(
        render_downloads, tasks, {"speed_download": 1024, "speed_upload": 512}
    )
    assert "ubuntu.iso" in out_dl
    assert "50.0%" in out_dl

    assert "не найдено" in _capture_render(render_system_logs, [])
    out_logs = _capture_render(
        render_system_logs,
        [
            {"time": "2026-11-10", "level": "err", "user": "admin", "descr": "Disk error"},
            {"time": "2026-11-10", "level": "warn", "user": "SYSTEM", "descr": "High load"},
            {"time": "2026-11-10", "level": "info", "user": "admin", "descr": "Login ok"},
        ],
    )
    assert "ERROR" in out_logs
    assert "WARN" in out_logs
    assert "INFO" in out_logs

    out_guests = _capture_render(
        render_vmm_guests,
        [{"guest_name": "win11", "guest_id": "vm-1", "status": "running", "vcpu_num": 4, "vram_size": 4096}],
    )
    assert "win11" in out_guests
    assert "4096 MB" in out_guests

    assert "нет зарегистрированных образов" in _capture_render(render_vmm_images, [])
    out_vmm_imgs = _capture_render(
        render_vmm_images,
        [{"image_name": "debian12", "image_id": "img-1", "type": "iso", "status": "ready", "size": 1048576}],
    )
    assert "debian12" in out_vmm_imgs
    assert "ISO" in out_vmm_imgs
