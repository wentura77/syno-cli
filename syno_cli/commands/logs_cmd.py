"""CLI-команды просмотра системных журналов DSM."""

from typing import Optional

import typer

from syno_cli.commands.common import CommandResult, cli_command
from syno_cli.constants import DEFAULT_LOG_LINES
from syno_cli.facade import SynoDSM
from syno_cli.views.tables import render_system_logs

logs_app = typer.Typer(help="Просмотр и фильтрация системных журналов DSM (Log Center).")


@logs_app.command("list")
@cli_command(spinner_message="Запрос системных логов DSM...")
async def logs_list(
    level: Optional[str] = typer.Option(
        None, "--level", "-l", help="Фильтр по критичности: info, warn, err"
    ),
    lines: int = typer.Option(
        DEFAULT_LOG_LINES, "--lines", "-n", help="Количество строк журнала"
    ),
    keyword: Optional[str] = typer.Option(None, "--query", "-q", help="Поиск по ключевому слову"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Вывести список последних событий системного журнала DSM.

    Args:
        level: Уровень критичности записей (`info`, `warn`, `err`).
        lines: Максимальное количество запрашиваемых записей.
        keyword: Подстрока для фильтрации событий.
        json_output: Флаг вывода результата в формате JSON.

    Returns:
        CommandResult: Список записей журнала и функция отрисовки таблицы.
    """
    _ = json_output
    async with SynoDSM() as nas:
        logs = await nas.logs.list_logs(level=level, limit=lines, keyword=keyword)
        return logs, render_system_logs
