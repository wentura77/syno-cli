"""CLI-команды мониторинга и управления закачками (Download Station)."""

from typing import Optional

import typer

from syno_cli.commands.common import CommandResult, cli_command, console
from syno_cli.facade import SynoDSM
from syno_cli.views.tables import render_downloads

download_app = typer.Typer(help="Мониторинг и управление закачками (Download Station).")


@download_app.command("list")
@cli_command(spinner_message="Опрос очереди задач Download Station...")
async def download_list(
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Отобразить суммарную скорость и текущий список задач Download Station.

    Args:
        json_output: Флаг вывода в формате JSON.

    Returns:
        CommandResult: Задачи со статистикой и функция отрисовки.
    """
    _ = json_output
    async with SynoDSM() as nas:
        stats = await nas.downloads.get_statistic()
        tasks = await nas.downloads.list_tasks()
        return {"tasks": tasks, "stats": stats}, lambda d: render_downloads(d["tasks"], d["stats"])


@download_app.command("add")
@cli_command(spinner_message="Добавление задачи скачивания...")
async def download_add(
    uri: str = typer.Argument(..., help="URL, Magnet-ссылка или путь к файлу"),
    dest: Optional[str] = typer.Option(None, "--dest", "-d", help="Целевая папка скачивания"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Добавить новую задачу скачивания в очередь Download Station.

    Args:
        uri: Ссылка или путь к торрент-файлу.
        dest: Целевая директория сохранения.
        json_output: Флаг вывода в формате JSON.

    Returns:
        CommandResult: Ответ DSM и колбэк подтверждения.
    """
    _ = json_output
    async with SynoDSM() as nas:
        res = await nas.downloads.add_task(uri, destination=dest)
        return (
            res,
            lambda _: console.print(
                f"[bold green]✓ Задача скачивания добавлена: {uri}[/bold green]"
            ),
        )


@download_app.command("delete")
@cli_command(spinner_message="Удаление задачи из Download Station...")
async def download_delete(
    task_id: str = typer.Argument(..., help="ID задачи (например, dbid_1)"),
    force: bool = typer.Option(False, "--force", "-f", help="Принудительно удалить"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Удалить задачу из очереди Download Station.

    Args:
        task_id: Идентификатор задачи.
        force: Принудительное завершение.
        json_output: Флаг вывода в формате JSON.

    Returns:
        CommandResult: Ответ DSM и колбэк подтверждения.
    """
    _ = json_output
    async with SynoDSM() as nas:
        res = await nas.downloads.delete_task(task_id, force_complete=force)
        return (
            res,
            lambda _: console.print(f"[bold red]✓ Задача '{task_id}' удалена[/bold red]"),
        )


@download_app.command("pause")
@cli_command(spinner_message="Приостановка задачи скачивания...")
async def download_pause(
    task_id: str = typer.Argument(..., help="ID задачи (например dbid_1)"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Приостановить выполнение задачи скачивания.

    Args:
        task_id: Идентификатор задачи.
        json_output: Флаг вывода в формате JSON.

    Returns:
        CommandResult: Ответ DSM и колбэк подтверждения.
    """
    _ = json_output
    async with SynoDSM() as nas:
        res = await nas.downloads.pause_task(task_id)
        return (
            res,
            lambda _: console.print(
                f"[bold yellow]✓ Задача '{task_id}' приостановлена[/bold yellow]"
            ),
        )


@download_app.command("resume")
@cli_command(spinner_message="Возобновление задачи скачивания...")
async def download_resume(
    task_id: str = typer.Argument(..., help="ID задачи (например dbid_1)"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Возобновить приостановленную задачу скачивания.

    Args:
        task_id: Идентификатор задачи.
        json_output: Флаг вывода в формате JSON.

    Returns:
        CommandResult: Ответ DSM и колбэк подтверждения.
    """
    _ = json_output
    async with SynoDSM() as nas:
        res = await nas.downloads.resume_task(task_id)
        return (
            res,
            lambda _: console.print(f"[bold green]✓ Задача '{task_id}' возобновлена[/bold green]"),
        )
