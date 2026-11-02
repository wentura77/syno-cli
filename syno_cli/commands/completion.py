"""Хелперы динамического автодополнения путей Synology NAS в шелле."""

import asyncio
from typing import List
from syno_cli.client.base import BaseSynoClient
from syno_cli.client.file_station import SynoFileStationClient


def complete_remote_path(ctx, args, incomplete: str) -> List[str]:
    """Динамически запрашивает пути с Synology NAS для автодополнения по Tab.

    Args:
        ctx: Контекст выполнения Click/Typer.
        args: Список ранее введенных аргументов.
        incomplete: Текущий префикс пути, введенный пользователем.

    Returns:
        Список подходящих путей на NAS.
    """
    async def _fetch() -> List[str]:
        base = BaseSynoClient()
        try:
            fs = SynoFileStationClient(base)

            if not incomplete or incomplete == "/":
                parent_dir = "/"
                prefix = ""
            elif "/" in incomplete:
                parent_dir = incomplete.rsplit("/", 1)[0] or "/"
                prefix = incomplete.rsplit("/", 1)[1]
            else:
                parent_dir = "/"
                prefix = incomplete

            items = await fs.list_dir(parent_dir)
            suggestions: List[str] = []

            for item in items:
                name = str(item.get("name", ""))
                if name.lower().startswith(prefix.lower()):
                    is_dir = item.get("isdir", False)
                    if parent_dir == "/":
                        full_path = f"/{name}"
                    else:
                        full_path = f"{parent_dir.rstrip('/')}/{name}"

                    if is_dir:
                        full_path += "/"
                    suggestions.append(full_path)

            return suggestions
        except Exception:
            return []
        finally:
            await base.close()

    try:
        return asyncio.run(_fetch())
    except Exception:
        return []