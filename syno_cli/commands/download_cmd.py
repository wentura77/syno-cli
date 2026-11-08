"""CLI-команды мониторинга и управления закачками (Download Station)."""

from typing import Any, Optional, Tuple

import typer

from syno_cli.client.base import BaseSynoClient
from syno_cli.client.download_station import SynoDownloadStationClient
from syno_cli.commands.common import cli_command, console
from syno_cli.views.tables import render_downloads

download_app = typer.Typer(help="Мониторинг и управление закачками (Download Station).")


@download_app.command("list")
@cli_command(spinner_message="Опрос очереди задач Download Station...")
async def download_list(
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> Tuple[Any, Any]:
    """Отобразить суммарную скорость и текущий список задач Download Station."""
    base = BaseSynoClient()
    try:
        ds = SynoDownloadStationClient(base)
        stats = await ds.get_statistic()
        tasks = await ds.list_tasks()
        return {"tasks": tasks, "stats": stats}, lambda d: render_downloads(d["tasks"], d["stats"])
    finally:
        await base.close()


@download_app.command("add")
@cli_command(spinner_message="Добавление задачи скачивания...")
async def download_add(
    uri: str = typer.Argument(..., help="URL, Magnet-ссылка или путь к файлу"),
    dest: Optional[str] = typer.Option(None, "--dest", "-d", help="Целевая папка скачивания"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> Tuple[Any, Any]:
    """Добавить новую задачу скачивания в очередь Download Station."""
    base = BaseSynoClient()
    try:
        res = await SynoDownloadStationClient(base).add_task(uri, destination=dest)
        return (
            res,
            lambda _: console.print(
                f"[bold green]✓ Задача скачивания добавлена: {uri}[/bold green]"
            ),
        )
    finally:
        await base.close()


@download_app.command("delete")
@cli_command(spinner_message="Удаление задачи из Download Station...")
async def download_delete(
    task_id: str = typer.Argument(..., help="ID задачи (например, dbid_1)"),
    force: bool = typer.Option(False, "--force", "-f", help="Принудительно удалить"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> Tuple[Any, Any]:
    """Удалить задачу из очереди Download Station."""
    base = BaseSynoClient()
    try:
        res = await SynoDownloadStationClient(base).delete_task(task_id, force_complete=force)
        return (
            res,
            lambda _: console.print(f"[bold red]✓ Задача '{task_id}' удалена[/bold red]"),
        )
    finally:
        await base.close()


@download_app.command("pause")
@cli_command(spinner_message="Приостановка задачи скачивания...")
async def download_pause(
    task_id: str = typer.Argument(..., help="ID задачи (например dbid_1)"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> Tuple[Any, Any]:
    """Приостановить выполнение задачи скачивания."""
    base = BaseSynoClient()
    try:
        res = await SynoDownloadStationClient(base).pause_task(task_id)
        return (
            res,
            lambda _: console.print(
                f"[bold yellow]✓ Задача '{task_id}' приостановлена[/bold yellow]"
            ),
        )
    finally:
        await base.close()


@download_app.command("resume")
@cli_command(spinner_message="Возобновление задачи скачивания...")
async def download_resume(
    task_id: str = typer.Argument(..., help="ID задачи (например dbid_1)"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> Tuple[Any, Any]:
    """Возобновить приостановленную задачу скачивания."""
    base = BaseSynoClient()
    try:
        res = await SynoDownloadStationClient(base).resume_task(task_id)
        return (
            res,
            lambda _: console.print(f"[bold green]✓ Задача '{task_id}' возобновлена[/bold green]"),
        )
    finally:
        await base.close()
