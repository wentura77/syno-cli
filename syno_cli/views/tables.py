"""Генераторы консольных таблиц Rich для всех подсистем Synology NAS."""

from datetime import datetime
from pathlib import PurePosixPath
from typing import Any, Final, Optional

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

FILE_TYPE_ICONS: Final[dict[str, str]] = {
    ".mkv": "🎬 MKV",
    ".mp4": "🎬 MP4",
    ".avi": "🎬 AVI",
    ".mov": "🎬 MOV",
    ".webm": "🎬 WEBM",
    ".wmv": "🎬 WMV",
    ".m4v": "🎬 M4V",
    ".mp3": "🎵 MP3",
    ".flac": "🎵 FLAC",
    ".wav": "🎵 WAV",
    ".aac": "🎵 AAC",
    ".ogg": "🎵 OGG",
    ".jpg": "🖼️ JPG",
    ".jpeg": "🖼️ JPEG",
    ".png": "🖼️ PNG",
    ".gif": "🖼️ GIF",
    ".webp": "🖼️ WEBP",
    ".svg": "🖼️ SVG",
    ".zip": "📦 ZIP",
    ".rar": "📦 RAR",
    ".7z": "📦 7Z",
    ".tar": "📦 TAR",
    ".gz": "📦 GZ",
    ".iso": "💿 ISO",
    ".pdf": "📕 PDF",
    ".txt": "📄 TXT",
    ".doc": "📘 DOC",
    ".docx": "📘 DOCX",
    ".xls": "📊 XLS",
    ".xlsx": "📊 XLSX",
    ".torrent": "🧲 TORR",
    ".json": "⚙️ JSON",
    ".yaml": "⚙️ YAML",
    ".yml": "⚙️ YML",
    ".sh": "⚡ SH",
    ".py": "🐍 PY",
}


def format_timestamp(ts: Optional[int | float | str]) -> str:
    """Преобразует Unix-timestamp в читаемый формат даты и времени.

    Args:
        ts: Время в секундах (Unix epoch) или None.

    Returns:
        str: Отформатированная строка вида 'YYYY-MM-DD HH:MM' или '—'.
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
        str: Строка с иконкой и категорией/расширением.
    """
    if is_dir:
        return "📁 DIR"

    ext = PurePosixPath(name).suffix.lower()
    if not ext:
        return "📄 FILE"
    return FILE_TYPE_ICONS.get(ext, f"📄 {ext[1:].upper()[:4]}")


def _file_sort_key(item: dict[str, Any], sort_by: str) -> tuple[int, Any]:
    """Вычисляет ключ сортировки для элемента File Station.

    Args:
        item: Словарь метаданных файла или директории.
        sort_by: Поле сортировки ('name', 'size', 'mtime', 'crtime').

    Returns:
        tuple[int, Any]: Кортеж приоритета папки и значения поля.
    """
    is_dir = 0 if item.get("isdir", True) else 1
    additional = item.get("additional", {})
    time_info = additional.get("time", {})

    field = sort_by.lower()
    if field == "size":
        val: Any = int(additional.get("size", 0))
    elif field in ("mtime", "time", "date"):
        val = int(time_info.get("mtime", 0)) if isinstance(time_info, dict) else 0
    elif field in ("crtime", "created"):
        val = int(time_info.get("crtime", 0)) if isinstance(time_info, dict) else 0
    else:
        val = str(item.get("name", "")).lower()

    return is_dir, val


def render_system_status(sys_info: dict[str, Any], util: dict[str, Any]) -> None:
    """Выводит сводную панель состояния Synology NAS.

    Args:
        sys_info: Данные `SYNO.Core.System`.
        util: Данные `SYNO.Core.System.Utilization`.
    """
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
    table.add_row("Версия ОС:", str(dsm_ver))
    table.add_row("Время работы (Uptime):", uptime)
    table.add_row("Температура системы:", f"{temp} °C")
    table.add_row("Загрузка CPU:", f"{cpu_load}%")
    table.add_row("Использование RAM:", f"{mem_usage}%")

    console.print(
        Panel(table, title="[bold blue]Сводка состояния Synology NAS[/bold blue]", expand=False)
    )


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
        name = str(disk.get("name", disk.get("id", "—")))
        model = str(disk.get("model", "—")).strip()
        size_b = int(disk.get("size_total", 0))
        temp = disk.get("temp", "—")
        status = str(disk.get("status", "normal"))
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

    for item in containers:
        name = str(item.get("name", "—"))
        image = str(item.get("image", "—"))
        status = str(item.get("status", "unknown"))
        cpu = f"{item.get('cpu_priority', 0)}%"
        mem = format_bytes(int(item.get("memory", 0)))
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
        repo = str(img.get("repository", "—"))
        tags = ", ".join(img.get("tags", ["latest"]))
        size = format_bytes(int(img.get("size", 0)))
        table.add_row(repo, tags, size)

    console.print(table)


def render_vmm_guests(guests: list[dict[str, Any]]) -> None:
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

    for guest in guests:
        name = str(guest.get("guest_name", "—"))
        gid = str(guest.get("guest_id", "—"))
        status = str(guest.get("status", "unknown"))
        vcpu = str(guest.get("vcpu_num", "—"))
        vram_mb = int(guest.get("vram_size", 0))
        table.add_row(name, gid, colorize_status(status), vcpu, f"{vram_mb} MB")
    console.print(table)


render_vms = render_vmm_guests


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
    sorted_items = sorted(items, key=lambda x: _file_sort_key(x, sort_by), reverse=reverse)
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
        is_dir = bool(item.get("isdir", True))
        name = str(item.get("name", "—"))
        path = str(item.get("path", "—"))

        additional = item.get("additional", {})
        size = int(additional.get("size", 0))
        size_str = "—" if is_dir else format_bytes(size)

        time_info = additional.get("time", {})
        mtime = time_info.get("mtime") if isinstance(time_info, dict) else None
        crtime = time_info.get("crtime") if isinstance(time_info, dict) else None

        table.add_row(
            detect_file_type(name, is_dir),
            name,
            size_str,
            format_timestamp(mtime),
            format_timestamp(crtime),
            path,
        )

    console.print(table)


def render_downloads(
    tasks: list[dict[str, Any]], stats: Optional[dict[str, Any]] = None
) -> None:
    """
    Выводит сводку скоростей и таблицу активных задач в Download Station.

    Args:
        tasks: Список задач скачивания.
        stats: Словарь общей статистики скоростей.
    """
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

    for task in tasks:
        tid = str(task.get("id", "—"))
        title = str(task.get("title", "—"))
        status = str(task.get("status", "unknown"))
        size = int(task.get("size", 0))

        additional = task.get("additional", {})
        destination = str(additional.get("detail", {}).get("destination", "—"))
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


def render_docker_stats(stats: list[dict[str, Any]]) -> None:
    """
    Отрисовывает таблицу утилизации ресурсов Docker-контейнерами в реальном времени.

    Args:
        stats: Список метрик контейнеров.
    """
    if not stats:
        console.print("[dim]Нет активных метрик контейнеров Docker.[/dim]")
        return

    table = Table(title="Docker: Мониторинг утилизации ресурсов", header_style="bold magenta")
    table.add_column("Контейнер", style="bold white")
    table.add_column("CPU %", justify="right")
    table.add_column("RAM Память", justify="right")
    table.add_column("Сеть (RX / TX)", justify="right")
    table.add_column("Диск I/O (R / W)", justify="right")

    for item in stats:
        name = str(item.get("name", item.get("container_name", "—")))
        cpu = item.get("cpu", item.get("cpu_percent", 0.0))
        cpu_str = f"{cpu:.2f}%" if isinstance(cpu, (int, float)) else str(cpu)

        mem_usage = item.get("memory", item.get("memory_usage", 0))
        mem_str = (
            format_bytes(int(mem_usage)) if isinstance(mem_usage, (int, float)) else str(mem_usage)
        )

        rx = format_bytes(int(item.get("network_rx_bytes", item.get("net_rx", 0))))
        tx = format_bytes(int(item.get("network_tx_bytes", item.get("net_tx", 0))))
        r_io = format_bytes(int(item.get("io_read_bytes", item.get("io_read", 0))))
        w_io = format_bytes(int(item.get("io_write_bytes", item.get("io_write", 0))))

        table.add_row(name, cpu_str, mem_str, f"{rx} / {tx}", f"{r_io} / {w_io}")

    console.print(table)


def render_docker_logs(logs: list[str]) -> None:
    """
    Отображает строки журнала событий Docker-контейнера.

    Args:
        logs: Список отформатированных строк журнала.
    """
    if not logs:
        console.print("[dim]Логи контейнера пусты.[/dim]")
        return
    for line in logs:
        console.print(line)


def render_docker_projects(projects: list[dict[str, Any]]) -> None:
    """
    Отрисовывает таблицу проектов Docker Compose.

    Args:
        projects: Список проектов из `SYNO.Docker.Project`.
    """
    if not projects:
        console.print("[dim]Нет созданных проектов Docker Compose.[/dim]")
        return

    table = Table(title="Docker Compose: Проекты", header_style="bold magenta")
    table.add_column("Имя проекта", style="bold white")
    table.add_column("Статус", justify="center")
    table.add_column("Сервисы (контейнеры)", justify="center")
    table.add_column("Путь / Папка", style="cyan")

    for proj in projects:
        name = str(proj.get("name", "—"))
        status_raw = str(proj.get("status", "")).lower()
        if status_raw in ("running", "active", "up"):
            status = "[bold green]Запущен[/bold green]"
        elif status_raw in ("stopped", "inactive", "down"):
            status = "[bold red]Остановлен[/bold red]"
        else:
            status = f"[yellow]{status_raw or '—'}[/yellow]"

        services_count = len(proj.get("services", proj.get("containers", [])))
        path_str = str(proj.get("path", proj.get("share_path", "—")))
        table.add_row(name, status, str(services_count), path_str)

    console.print(table)


def render_system_logs(logs: list[dict[str, Any]]) -> None:
    """
    Отображает таблицу системного журнала событий DSM.

    Args:
        logs: Список записей системного журнала.
    """
    if not logs:
        console.print("[dim]Записей в системном журнале не найдено.[/dim]")
        return

    table = Table(title="Системный журнал событий DSM", header_style="bold magenta")
    table.add_column("Время", style="cyan", no_wrap=True)
    table.add_column("Уровень", justify="center")
    table.add_column("Пользователь", style="bold white")
    table.add_column("Событие / Описание", style="white")

    for item in logs:
        time_str = str(item.get("time", item.get("date", "—")))
        lvl_raw = str(item.get("level", "info")).lower()

        if lvl_raw in ("err", "error", "critical"):
            level_fmt = "[bold red]ERROR[/bold red]"
        elif lvl_raw in ("warn", "warning"):
            level_fmt = "[bold yellow]WARN[/bold yellow]"
        else:
            level_fmt = "[green]INFO[/green]"

        user = str(item.get("user", item.get("who", "SYSTEM")))
        desc = str(item.get("descr", item.get("msg", item.get("text", "—")))).strip()
        table.add_row(time_str, level_fmt, user, desc)

    console.print(table)


def render_vmm_images(images: list[dict[str, Any]]) -> None:
    """
    Выводит таблицу образов и шаблонов дисков в Synology VMM.

    Args:
        images: Список образов VMM.
    """
    if not images:
        console.print("[dim]В репозитории VMM нет зарегистрированных образов.[/dim]")
        return

    table = Table(title="Образы и шаблоны Virtual Machine Manager", header_style="bold magenta")
    table.add_column("Имя образа", style="bold cyan")
    table.add_column("ID", style="dim")
    table.add_column("Тип", justify="center")
    table.add_column("Статус", justify="center")
    table.add_column("Размер", justify="right")

    for img in images:
        name = str(img.get("image_name", img.get("name", "—")))
        img_id = str(img.get("image_id", img.get("id", "—")))
        img_type = str(img.get("type", "iso")).upper()
        status = colorize_status(str(img.get("status", "ready")))
        size = format_bytes(int(img.get("size", 0)))
        table.add_row(name, img_id, img_type, status, size)

    console.print(table)
