"""CLI-команды просмотра системных журналов DSM."""

from typing import Any, Optional, Tuple

import typer

from syno_cli.client.base import BaseSynoClient
from syno_cli.client.logs import SynoLogsClient
from syno_cli.commands.common import cli_command
from syno_cli.views.tables import render_system_logs

logs_app = typer.Typer(help="Просмотр и фильтрация системных журналов DSM (Log Center).")


@logs_app.command("list")
@cli_command(spinner_message="Запрос системных логов DSM...")
async def logs_list(
    level: Optional[str] = typer.Option(
        None, "--level", "-l", help="Фильтр по критичности: info, warn, err"
    ),
    lines: int = typer.Option(50, "--lines", "-n", help="Количество строк журнала"),
    keyword: Optional[str] = typer.Option(None, "--query", "-q", help="Поиск по ключевому слову"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> Tuple[Any, Any]:
    """Вывести список последних событий системного журнала DSM."""
    base = BaseSynoClient()
    try:
        client = SynoLogsClient(base)
        logs = await client.list_logs(level=level, limit=lines, keyword=keyword)
        return logs, render_system_logs
    finally:
        await base.close()
