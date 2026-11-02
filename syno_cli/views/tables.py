"""Генераторы консольных таблиц Rich для всех подсистем Synology NAS."""

from datetime import datetime
from pathlib import PurePosixPath
from typing import Any, Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from syno_cli.views.formatters import (
    colorize_status,
    format_bytes,
    format_speed,
    format_uptime,
)

console = Console()


def format_timestamp(ts: Optional[int | float | str]) -> str:
    """Преобразует Unix-timestamp в читаемый формат даты и времени.

    Args:
        ts: Время в секундах (Unix epoch) или None.

    Returns:
        Отформатированная строка вида 'YYYY-MM-DD HH:MM' или '—'.
    """
    if not ts or ts == "—":
        return "—"
    try:
        val = int(ts)
        if val <= 0:
            return "—"
        return datetime.fromtimestamp(val).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError, OSError):
        return str(ts)


def detect_file_type(name: str, is_dir: bool) -> str:
    """Определяет категорию и тип объекта по его имени и расширению.

    Args:
        name: Имя файла или директории.
        is_dir: Флаг, является ли объект директорией.

    Returns:
        Строка с иконкой и категорией/расширением (например, '📁 DIR', '🎬 MKV').
    """
    if is_dir:
        return "📁 DIR"

    ext = PurePosixPath(name).suffix.lower()
    if not ext:
        return "📄 FILE"

    type_map = {
        # Видео
        ".mkv": "🎬 MKV",
        ".mp4": "🎬 MP4",
        ".avi": "🎬 AVI",
        ".mov": "🎬 MOV",
        ".wmv": "🎬 WMV",
        ".m4v": "🎬 M4V",
        # Музыка
        ".mp3": "🎵 MP3",
        ".flac": "🎵 FLAC",
        ".wav": "🎵 WAV",
        ".aac": "🎵 AAC",
        ".ogg": "🎵 OGG",
        # Картинки
        ".jpg": "🖼️ JPG",
        ".jpeg": "🖼️ JPEG",
        ".png": "🖼️ PNG",
        ".gif": "🖼️ GIF",
        ".webp": "🖼️ WEBP",
        ".svg": "🖼️ SVG",
        # Архивы / Образы
        ".zip": "📦 ZIP",
        ".rar": "📦 RAR",
        ".7z": "📦 7Z",
        ".tar": "📦 TAR",
        ".gz": "📦 GZ",
        ".iso": "💿 ISO",
        # Документы
        ".pdf": "📕 PDF",
        ".txt": "📄 TXT",
        ".doc": "📘 DOC",
        ".docx": "📘 DOCX",
        ".xls": "📊 XLS",
        ".xlsx": "📊 XLSX",
        # Торренты
        ".torrent": "🧲 TORR",
        # Конфиги / Скрипты
        ".json": "⚙️ JSON",
        ".yaml": "⚙️ YAML",
        ".yml": "⚙️ YML",
        ".sh": "⚡ SH",
        ".py": "🐍 PY",
    }

    return type_map.get(ext, f"📄 {ext[1:].upper()[:4]}")


def render_system_status(sys_info: dict[str, Any], util: dict[str, Any]) -> None:
    """Выводит сводную панель состояния Synology NAS."""
    model = sys_info.get("model", "Synology NAS")
    dsm_ver = sys_info.get("firmware_ver") or sys_info.get("version_string", "DSM")
    temp = sys_info.get("sys_temp", "—")
    uptime = format_uptime(sys_info.get("up_time", 0))

    cpu_data = util.get("cpu", {})
    cpu_load = int(cpu_data.get("user_load", 0)) + int(cpu_data.get("system_load", 0))
    mem_usage = util.get("memory", {}).get("real_usage", 0)

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Параметр", style="bold cyan")
    table.add_column("Значение")

    table.add_row("Модель устройства:", f"[bold white]{model}[/bold white]")
    table.add_row("Версия ОС:", dsm_ver)
    table.add_row("Время работы (Uptime):", uptime)
    table.add_row("Температура системы:", f"{temp} °C")
    table.add_row("Загрузка CPU:", f"{cpu_load}%")
    table.add_row("Использование RAM:", f"{mem_usage}%")

    console.print(Panel(table, title="[bold blue]Сводка состояния Synology NAS[/bold blue]", expand=False))


def render_storage_disks(storage_data: dict[str, Any]) -> None:
    """
    Рендерит таблицу физических накопителей и их SMART/температурных показателей.

    Args:
        storage_data (dict[str, Any]): Ответ метода `load_info` из `SYNO.Storage.CGI.Storage`.
    """
    table = Table(title="Физические диски и накопители")
    table.add_column("Диск", style="bold cyan")
    table.add_column("Модель")
    table.add_column("Объем", justify="right")
    table.add_column("Темп.", justify="right")
    table.add_column("SMART / Статус")

    for disk in storage_data.get("disks", []):
        name = disk.get("name", disk.get("id", "—"))
        model = disk.get("model", "—").strip()
        size_b = int(disk.get("size_total", 0))
        temp = disk.get("temp", "—")
        status = disk.get("status", "normal")
        table.add_row(
            name,
            model,
            format_bytes(size_b),
            f"{temp} °C" if temp != "—" else "—",
            colorize_status(status),
        )
    console.print(table)


def render_docker_containers(containers: list[dict[str, Any]]) -> None:
    """
    Выводит таблицу контейнеров Docker / Container Manager.

    Args:
        containers (list[dict[str, Any]]): Список контейнеров из `SYNO.Docker.Container`.
    """
    table = Table(title="Контейнеры Docker (Container Manager)")
    table.add_column("Имя контейнера", style="bold cyan")
    table.add_column("Образ")
    table.add_column("Статус")
    table.add_column("CPU %", justify="right")
    table.add_column("Память", justify="right")

    for c in containers:
        name = c.get("name", "—")
        image = c.get("image", "—")
        status = c.get("status", "unknown")
        cpu = f"{c.get('cpu_priority', 0)}%"
        mem = format_bytes(int(c.get("memory", 0)))
        table.add_row(name, image, colorize_status(status), cpu, mem)

    console.print(table)


def render_docker_images(images: list[dict[str, Any]]) -> None:
    """
    Выводит таблицу локальных Docker-образов на NAS.

    Args:
        images (list[dict[str, Any]]): Список образов из `SYNO.Docker.Image`.
    """
    table = Table(title="Локальные образы Docker")
    table.add_column("Репозиторий", style="bold cyan")
    table.add_column("Теги")
    table.add_column("Размер", justify="right")

    for img in images:
        repo = img.get("repository", "—")
        tags = ", ".join(img.get("tags", ["latest"]))
        size = format_bytes(int(img.get("size", 0)))
        table.add_row(repo, tags, size)

    console.print(table)


def render_vms(guests: list[dict[str, Any]]) -> None:
    """
    Выводит таблицу виртуальных машин из Virtual Machine Manager (VMM).

    Args:
        guests (list[dict[str, Any]]): Список гостевых машин из `SYNO.Virtualization.API.Guest`.
    """
    table = Table(title="Виртуальные машины (Synology VMM)")
    table.add_column("Имя ВМ", style="bold cyan")
    table.add_column("ID")
    table.add_column("Статус")
    table.add_column("vCPU", justify="right")
    table.add_column("RAM", justify="right")

    for g in guests:
        name = g.get("guest_name", "—")
        gid = g.get("guest_id", "—")
        status = g.get("status", "unknown")
        vcpu = str(g.get("vcpu_num", "—"))
        vram_mb = int(g.get("vram_size", 0))
        table.add_row(
            name,
            gid,
            colorize_status(status),
            vcpu,
            f"{vram_mb} MB",
        )
    console.print(table)


def render_files(
    items: list[dict[str, Any]],
    current_path: str,
    sort_by: str = "mtime",
    reverse: bool = True,
) -> None:
    """Выводит содержимое директории File Station с поддержкой категорий и сортировки.

    Args:
        items: Список файлов и папок, полученных от DSM Web API.
        current_path: Отображаемый путь к текущему каталогу.
        sort_by: Поле сортировки ('name', 'size', 'mtime', 'crtime').
        reverse: Инвертировать порядок сортировки (по убыванию).
    """
    def _sort_key(item: dict[str, Any]) -> tuple[int, Any]:
        is_dir = 0 if item.get("isdir", True) else 1
        additional = item.get("additional", {})
        time_info = additional.get("time", {})

        field = sort_by.lower()
        if field == "size":
            val = int(additional.get("size", 0))
        elif field in ("mtime", "time", "date"):
            val = int(time_info.get("mtime", 0)) if isinstance(time_info, dict) else 0
        elif field in ("crtime", "created"):
            val = int(time_info.get("crtime", 0)) if isinstance(time_info, dict) else 0
        else:
            val = str(item.get("name", "")).lower()

        return (is_dir, val)

    sorted_items = sorted(items, key=_sort_key, reverse=reverse)

    if not sorted_items:
        console.print(f"[dim]📁 Каталог '{current_path}' пуст.[/dim]")
        return

    sort_title = f" (сортировка: {sort_by}{', убыв.' if reverse else ''})"
    table = Table(title=f"Содержимое каталога: {current_path}{sort_title}")
    table.add_column("Тип", width=9)
    table.add_column("Имя", style="bold white")
    table.add_column("Размер", justify="right")
    table.add_column("Изменен", style="cyan", no_wrap=True)
    table.add_column("Создан", style="dim", no_wrap=True)
    table.add_column("Путь", style="dim")

    for item in sorted_items:
        is_dir = item.get("isdir", True)
        name = item.get("name", "—")
        icon_type = detect_file_type(name, is_dir)
        path = item.get("path", "—")

        additional = item.get("additional", {})
        size = int(additional.get("size", 0))
        size_str = "—" if is_dir else format_bytes(size)

        time_info = additional.get("time", {})
        mtime = time_info.get("mtime") if isinstance(time_info, dict) else None
        crtime = time_info.get("crtime") if isinstance(time_info, dict) else None

        table.add_row(
            icon_type,
            name,
            size_str,
            format_timestamp(mtime),
            format_timestamp(crtime),
            path,
        )

    console.print(table)


def render_downloads(tasks: list[dict[str, Any]], stats: dict[str, Any] | None = None) -> None:
    """Выводит сводку скоростей, директорию сохранения и таблицу активных задач в Download Station."""
    if stats:
        dl_speed = format_speed(int(stats.get("speed_download", 0)))
        ul_speed = format_speed(int(stats.get("speed_upload", 0)))
        console.print(
            Panel(
                f"⬇ Скачивание: [bold green]{dl_speed}[/bold green]   |   "
                f"⬆ Отдача: [bold cyan]{ul_speed}[/bold cyan]   |   "
                f"Всего задач: [bold white]{len(tasks)}[/bold white]",
                title="[bold blue]Статус Download Station[/bold blue]",
                expand=False,
            )
        )

    table = Table(title="Задачи Download Station")
    table.add_column("ID", style="bold cyan")
    table.add_column("Имя файла / Задачи")
    table.add_column("Директория", style="dim")
    table.add_column("Статус")
    table.add_column("Размер", justify="right")
    table.add_column("Прогресс", justify="right")
    table.add_column("Скорость ⬇", justify="right")

    for t in tasks:
        tid = t.get("id", "—")
        title = t.get("title", "—")
        status = t.get("status", "unknown")
        size = int(t.get("size", 0))

        additional = t.get("additional", {})
        detail = additional.get("detail", {})
        destination = detail.get("destination", "—")

        transfer = additional.get("transfer", {})
        downloaded = int(transfer.get("size_downloaded", 0))
        speed_dl = int(transfer.get("speed_download", 0))
        pct = f"{(downloaded / size * 100):.1f}%" if size > 0 else "0.0%"

        table.add_row(
            tid,
            title,
            destination,
            colorize_status(status),
            format_bytes(size),
            pct,
            format_speed(speed_dl),
        )
    console.print(table)
