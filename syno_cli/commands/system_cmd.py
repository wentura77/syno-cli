"""Команды системного мониторинга и состояния дисков Synology NAS."""

import typer

from syno_cli.commands.common import CommandResult, cli_command
from syno_cli.facade import SynoDSM
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
    ) -> CommandResult:
        """Показать сводный статус Synology NAS (CPU, RAM, температура, аптайм).

        Args:
            json_output: Флаг вывода в формате JSON.

        Returns:
            CommandResult: Словарь системных метрик и функция рендеринга панели.
        """
        _ = json_output
        async with SynoDSM() as nas:
            info = await nas.core.get_system_info()
            util = await nas.core.get_utilization()
            return {"info": info, "utilization": util}, lambda d: render_system_status(
                d["info"], d["utilization"]
            )

    @app.command("storage")
    @cli_command(spinner_message="Запрос данных дисковой подсистемы и SMART...")
    async def cmd_storage(
        json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
    ) -> CommandResult:
        """Показать состояние физических дисков, температуру и статус SMART.

        Args:
            json_output: Флаг вывода в формате JSON.

        Returns:
            CommandResult: Данные о накопителях и функция рендеринга таблицы.
        """
        _ = json_output
        async with SynoDSM() as nas:
            data = await nas.core.get_storage_info()
            return data, render_storage_disks
