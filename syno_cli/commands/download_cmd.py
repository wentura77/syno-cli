"""CLI-команды мониторинга и управления закачками (Download Station)."""

import asyncio
from typing import Optional
import typer

from syno_cli.client.base import BaseSynoClient
from syno_cli.client.download_station import SynoDownloadStationClient
from syno_cli.views.tables import console, render_downloads

download_app = typer.Typer(help="Мониторинг и управление закачками (Download Station).")


@download_app.command("list")
def download_list() -> None:
    """Отобразить суммарную скорость и текущий список задач Download Station."""
    async def _impl() -> None:
        """Асинхронно получить статистику и перечень задач закачки."""
        base = BaseSynoClient()
        try:
            ds = SynoDownloadStationClient(base)
            stats = await ds.get_statistic()
            tasks = await ds.list_tasks()
            render_downloads(tasks, stats)
        finally:
            await base.close()

    asyncio.run(_impl())


@download_app.command("add")
def download_add(
    uri: str = typer.Argument(..., help="URL, Magnet-ссылка или путь к файлу"),
    dest: Optional[str] = typer.Option(None, "--dest", "-d", help="Целевая папка скачивания"),
) -> None:
    """Добавить новую задачу скачивания в очередь Download Station.

    Args:
        uri: Сетевая ссылка (HTTP/FTP/Magnet) или путь к локальному `.torrent`-файлу.
        dest: Опциональная папка назначения на NAS.
    """
    async def _impl() -> None:
        """Асинхронно добавить задачу скачивания."""
        base = BaseSynoClient()
        try:
            await SynoDownloadStationClient(base).add_task(uri, destination=dest)
            console.print(f"[bold green]✓ Задача скачивания добавлена: {uri}[/bold green]")
        finally:
            await base.close()

    asyncio.run(_impl())


@download_app.command("delete")
def download_delete(
    task_id: str = typer.Argument(..., help="ID задачи (например, dbid_1)"),
    force: bool = typer.Option(False, "--force", "-f", help="Принудительно завершить и удалить/переместить данные"),
) -> None:
    """Удалить задачу из очереди Download Station.

    Args:
        task_id: Идентификатор удаляемой задачи в DSM.
        force: Принудительно завершить процесс скачивания и очистить данные.
    """
    async def _impl() -> None:
        """Асинхронно удалить задачу из списка."""
        base = BaseSynoClient()
        try:
            await SynoDownloadStationClient(base).delete_task(task_id, force_complete=force)
            console.print(f"[bold red]✓ Задача '{task_id}' удалена[/bold red]")
        finally:
            await base.close()

    asyncio.run(_impl())


@download_app.command("pause")
def download_pause(task_id: str = typer.Argument(..., help="ID задачи (например dbid_1)")) -> None:
    """Приостановить выполнение задачи скачивания.

    Args:
        task_id: Идентификатор задачи в Download Station.
    """
    async def _impl() -> None:
        """Асинхронно поставить задачу скачивания на паузу."""
        base = BaseSynoClient()
        try:
            await SynoDownloadStationClient(base).pause_task(task_id)
            console.print(f"[bold yellow]✓ Задача '{task_id}' приостановлена[/bold yellow]")
        finally:
            await base.close()

    asyncio.run(_impl())


@download_app.command("resume")
def download_resume(task_id: str = typer.Argument(..., help="ID задачи (например dbid_1)")) -> None:
    """Возобновить приостановленную задачу скачивания.

    Args:
        task_id: Идентификатор задачи в Download Station.
    """
    async def _impl() -> None:
        """Асинхронно возобновить задачу скачивания."""
        base = BaseSynoClient()
        try:
            await SynoDownloadStationClient(base).resume_task(task_id)
            console.print(f"[bold green]✓ Задача '{task_id}' возобновлена[/bold green]")
        finally:
            await base.close()

    asyncio.run(_impl())
