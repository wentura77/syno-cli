"""Вспомогательные функции форматирования размеров данных, скоростей и статусов."""

from typing import Final

from syno_cli.constants import (
    BYTES_IN_KB,
    SECONDS_IN_DAY,
    SECONDS_IN_HOUR,
    SECONDS_IN_MINUTE,
)

_SIZE_UNITS: Final[tuple[str, ...]] = ("B", "KB", "MB", "GB", "TB", "PB")
_GREEN_STATUSES: Final[frozenset[str]] = frozenset(
    {"running", "up", "normal", "healthy", "finished", "seeding", "ready"}
)
_YELLOW_STATUSES: Final[frozenset[str]] = frozenset(
    {"downloading", "paused", "waiting", "suspended", "starting"}
)
_RED_STATUSES: Final[frozenset[str]] = frozenset(
    {"stopped", "shutdown", "poweroff", "crashed", "degraded", "error"}
)


def format_bytes(size_bytes: int | float) -> str:
    """
    Конвертирует количество байт в человекочитаемую строку (КБ, МБ, ГБ, ТБ).

    Args:
        size_bytes: Размер в байтах.

    Returns:
        str: Отформатированная строка (например, `1.50 GB`).
    """
    val = float(max(0, size_bytes))
    for unit in _SIZE_UNITS:
        if val < BYTES_IN_KB or unit == "PB":
            return f"{val:.2f} {unit}" if unit != "B" else f"{int(val)} B"
        val /= BYTES_IN_KB
    return f"{val:.2f} PB"


def format_speed(bytes_per_sec: int | float) -> str:
    """Форматирует скорость передачи данных в человекочитаемый вид.

    Args:
        bytes_per_sec: Скорость в байтах в секунду.

    Returns:
        str: Отформатированная скорость (например, `12.40 MB/s`).
    """
    return f"{format_bytes(bytes_per_sec)}/s"


def _parse_colon_uptime(raw: str) -> int:
    """
    Парсит строку времени формата `HH:MM:SS` или `HH:MM` в секунды.

    Args:
        raw: Строка с разделителями двоеточия.

    Returns:
        int: Количество секунд.

    Raises:
        ValueError: Если формат некорректен.
    """
    parts = [int(p) for p in raw.split(":")]
    if len(parts) == 3:
        return parts[0] * SECONDS_IN_HOUR + parts[1] * SECONDS_IN_MINUTE + parts[2]
    if len(parts) == 2:
        return parts[0] * SECONDS_IN_HOUR + parts[1] * SECONDS_IN_MINUTE
    raise ValueError(f"Unsupported time format: {raw}")


def format_uptime(uptime_val: int | str) -> str:
    """
    Преобразует время непрерывной работы в дни, часы и минуты.

    Args:
        uptime_val: Количество секунд аптайма или строка вида `'571:13:45'`.

    Returns:
        str: Читаемая строка аптайма (например, `23д 19ч 13м`).
    """
    if isinstance(uptime_val, int):
        total_seconds = uptime_val
    else:
        raw = uptime_val.strip()
        if not raw:
            return "—"
        try:
            total_seconds = _parse_colon_uptime(raw) if ":" in raw else int(raw)
        except ValueError:
            return raw

    days, rem = divmod(max(0, total_seconds), SECONDS_IN_DAY)
    hours, rem = divmod(rem, SECONDS_IN_HOUR)
    minutes, _ = divmod(rem, SECONDS_IN_MINUTE)
    if days > 0:
        return f"{days}д {hours:02d}ч {minutes:02d}м"
    return f"{hours:02d}ч {minutes:02d}м"


def colorize_status(status: str) -> str:
    """
    Оборачивает строковый статус в цветовую разметку библиотеки Rich.

    Args:
        status: Исходный текст статуса (`running`, `stopped`, `normal` и т.д.).

    Returns:
        str: Строка с тегами цвета Rich.
    """
    st = status.lower().strip()
    if st in _GREEN_STATUSES:
        return f"[bold green]● {status}[/bold green]"
    if st in _YELLOW_STATUSES:
        return f"[bold yellow]◐ {status}[/bold yellow]"
    if st in _RED_STATUSES:
        return f"[bold red]○ {status}[/bold red]"
    return status
