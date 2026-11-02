"""Команды системного мониторинга и состояния дисков Synology NAS."""

import asyncio
import typer

from syno_cli.client.base import BaseSynoClient
from syno_cli.client.core import SynoCoreClient
from syno_cli.views.tables import render_storage_disks, render_system_status

system_app = typer.Typer(help="Системный мониторинг и состояние накопителей.")


def register_system_commands(app: typer.Typer) -> None:
    """Зарегистрировать системные команды напрямую в корневое приложение CLI.

    Args:
        app: Корневой экземпляр Typer-приложения.
    """

    @app.command("status")
    def cmd_status() -> None:
        """Показать сводный статус Synology NAS (CPU, RAM, температура, аптайм)."""
        async def _impl() -> None:
            """Асинхронно запросить и отрендерить системный статус."""
            base = BaseSynoClient()
            try:
                core = SynoCoreClient(base)
                info = await core.get_system_info()
                util = await core.get_utilization()
                render_system_status(info, util)
            finally:
                await base.close()

        asyncio.run(_impl())

    @app.command("storage")
    def cmd_storage() -> None:
        """Показать состояние физических дисков, температуру и статус SMART."""
        async def _impl() -> None:
            """Асинхронно запросить и вывести состояние накопителей."""
            base = BaseSynoClient()
            try:
                core = SynoCoreClient(base)
                data = await core.get_storage_info()
                render_storage_disks(data)
            finally:
                await base.close()

        asyncio.run(_impl())
