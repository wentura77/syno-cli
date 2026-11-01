"""Вспомогательные функции форматирования размеров данных, скоростей и статусов."""


def format_bytes(size_bytes: int | float) -> str:
    """
    Конвертирует количество байт в человекочитаемую строку (КБ, МБ, ГБ, ТБ).

    Args:
        size_bytes (int | float): Размер в байтах.

    Returns:
        str: Отформатированная строка (например, `1.50 GB`).
    """
    val = float(max(0, size_bytes))
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if val < 1024.0 or unit == "PB":
            return f"{val:.2f} {unit}" if unit != "B" else f"{int(val)} B"
        val /= 1024.0
    return f"{val:.2f} PB"


def format_speed(bytes_per_sec: int | float) -> str:
    """
    Форматирует скорость передачи данных в человекочитаемый вид.

    Args:
        bytes_per_sec (int | float): Скорость в байтах в секунду.

    Returns:
        str: Отформатированная скорость (например, `12.40 MB/s`).
    """
    return f"{format_bytes(bytes_per_sec)}/s"


def format_uptime(uptime_val: int | str) -> str:
    """
    Преобразует время непрерывной работы (секунды или строку `HH:MM:SS`) в дни, часы и минуты.

    Args:
        uptime_val (int | str): Количество секунд аптайма или строка вида `'571:13:45'`.

    Returns:
        str: Читаемая строка аптайма (например, `23д 19ч 13м`).
    """
    total_seconds = 0
    if isinstance(uptime_val, int):
        total_seconds = uptime_val
    elif isinstance(uptime_val, str):
        raw = uptime_val.strip()
        if ":" in raw:
            parts = raw.split(":")
            try:
                if len(parts) == 3:
                    h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
                    total_seconds = h * 3600 + m * 60 + s
                elif len(parts) == 2:
                    h, m = int(parts[0]), int(parts[1])
                    total_seconds = h * 3600 + m * 60
            except ValueError:
                return raw
        else:
            try:
                total_seconds = int(raw)
            except ValueError:
                return raw or "—"

    days, rem = divmod(max(0, total_seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days > 0:
        return f"{days}д {hours:02d}ч {minutes:02d}м"
    return f"{hours:02d}ч {minutes:02d}м"


def colorize_status(status: str) -> str:
    """
    Оборачивает строковый статус в цветовую разметку библиотеки Rich.

    Args:
        status (str): Исходный текст статуса (`running`, `stopped`, `normal`, `degraded` и т.д.).

    Returns:
        str: Строка с тегами цвета Rich.
    """
    st = status.lower().strip()
    if st in ("running", "up", "normal", "healthy", "finished", "seeding"):
        return f"[bold green]● {status}[/bold green]"
    if st in ("downloading", "paused", "waiting", "suspended"):
        return f"[bold yellow]◐ {status}[/bold yellow]"
    if st in ("stopped", "shutdown", "poweroff", "crashed", "degraded", "error"):
        return f"[bold red]○ {status}[/bold red]"
    return status
