"""Хелперы динамического автодополнения путей Synology NAS в шелле."""

import asyncio
from typing import Any

from syno_cli.facade import SynoDSM


def _split_incomplete_path(incomplete: str) -> tuple[str, str]:
    """Разделяет вводимый путь на родительский каталог и префикс файла.

    Args:
        incomplete: Текущая строка ввода.

    Returns:
        tuple[str, str]: Кортеж `(parent_dir, prefix)`.
    """
    if not incomplete or incomplete == "/":
        return "/", ""
    if "/" in incomplete:
        parent, prefix = incomplete.rsplit("/", 1)
        return parent or "/", prefix
    return "/", incomplete


def _build_suggestion_path(parent_dir: str, name: str, is_dir: bool) -> str:
    """Формирует полный путь подсказки автодополнения.

    Args:
        parent_dir: Родительский каталог.
        name: Имя найденного элемента.
        is_dir: Является ли элемент директорией.

    Returns:
        str: Полный путь для автодополнения.
    """
    base_path = f"/{name}" if parent_dir == "/" else f"{parent_dir.rstrip('/')}/{name}"
    return f"{base_path}/" if is_dir else base_path


def complete_remote_path(ctx: Any, args: Any, incomplete: str) -> list[str]:
    """Динамически запрашивает пути с Synology NAS для автодополнения по Tab.

    Args:
        ctx: Контекст выполнения Click/Typer.
        args: Список ранее введенных аргументов.
        incomplete: Текущий префикс пути, введенный пользователем.

    Returns:
        list[str]: Список подходящих путей на NAS.
    """
    _ = ctx, args
    parent_dir, prefix = _split_incomplete_path(incomplete)
    prefix_lower = prefix.lower()

    async def _fetch() -> list[str]:
        async with SynoDSM() as nas:
            items = await nas.files.list_dir(parent_dir)
            return [
                _build_suggestion_path(parent_dir, str(item.get("name", "")), bool(item.get("isdir", False)))
                for item in items
                if str(item.get("name", "")).lower().startswith(prefix_lower)
            ]

    try:
        return asyncio.run(_fetch())
    except Exception:
        return []


def complete_container_names(ctx: Any, args: Any, incomplete: str) -> list[str]:
    """Динамически запрашивает имена Docker-контейнеров с Synology NAS для Tab-дополнения."""
    _ = ctx, args
    prefix_lower = incomplete.lower().lstrip("/")

    async def _fetch() -> list[str]:
        async with SynoDSM() as nas:
            containers = await nas.docker.list_containers()
            names: list[str] = []
            for c in containers:
                raw_name = str(c.get("name", "")).lstrip("/")
                if raw_name and raw_name.lower().startswith(prefix_lower):
                    names.append(raw_name)
            return sorted(names)

    try:
        return asyncio.run(_fetch())
    except Exception:
        return []
