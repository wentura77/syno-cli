"""Команды системного мониторинга и состояния дисков Synology NAS."""

from typing import Any, Tuple

import typer

from syno_cli.client.base import BaseSynoClient
from syno_cli.client.core import SynoCoreClient
from syno_cli.commands.common import cli_command
from syno_cli.views.tables import render_storage_disks, render_system_status

system_app = typer.Typer(help="Системный мониторинг и состояние накопителей.")


def register_system_commands(app: typer.Typer) -> None:
    """Зарегистрировать системные команды напрямую в корневое приложение CLI.

    Args:
        app: Корневой экземпляр Typer-приложения.
    """

    @app.command("status")
    @cli_command(spinner_message="Опрос состояния Synology NAS...")
    async def cmd_status(
        json_output: bool = typer.Option(
            False, "--json", "-j", help="Вывод в формате JSON (для CI/скриптов)"
        ),
    ) -> Tuple[Any, Any]:
        """Показать сводный статус Synology NAS (CPU, RAM, температура, аптайм)."""
        base = BaseSynoClient()
        try:
            core = SynoCoreClient(base)
            info = await core.get_system_info()
            util = await core.get_utilization()
            return {"info": info, "utilization": util}, lambda d: render_system_status(
                d["info"], d["utilization"]
            )
        finally:
            await base.close()

    @app.command("storage")
    @cli_command(spinner_message="Запрос данных дисковой подсистемы и SMART...")
    async def cmd_storage(
        json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
    ) -> Tuple[Any, Any]:
        """Показать состояние физических дисков, температуру и статус SMART."""
        base = BaseSynoClient()
        try:
            core = SynoCoreClient(base)
            data = await core.get_storage_info()
            return data, render_storage_disks
        finally:
            await base.close()
