"""CLI-команды работы с файлами и папками хранилища (File Station)."""

import asyncio
from pathlib import Path
import typer

from syno_cli.client.base import BaseSynoClient
from syno_cli.client.file_station import SynoFileStationClient
from syno_cli.commands.completion import complete_remote_path
from syno_cli.views.tables import console, render_files

files_app = typer.Typer(help="Управление файлами и папками на хранилище (File Station).")


@files_app.command("ls")
def files_ls(
    path: str = typer.Argument(
        "/",
        autocompletion=complete_remote_path,
        help="Путь в File Station (например / или /docker)",
    ),
    sort: str = typer.Option(
        "mtime",
        "--sort",
        "-s",
        help="Поле сортировки: mtime (дата изменения), name, size, crtime (дата создания)",
    ),
    reverse: bool = typer.Option(
        True,
        "--reverse",
        "-r",
        help="Инвертировать порядок сортировки (по умолчанию: True, сначала свежие)",
    ),
) -> None:
    """Отобразить список файлов и директорий с поддержкой сортировки.

    Args:
        path: Путь к целевой директории в File Station.
        sort: Критерий сортировки (mtime, name, size, crtime).
        reverse: Инвертировать порядок сортировки.
    """
    async def _impl() -> None:
        """Асинхронно получить и вывести отсортированное содержимое каталога."""
        base = BaseSynoClient()
        try:
            fs = SynoFileStationClient(base)
            items = await fs.list_dir(path)
            render_files(items, path, sort_by=sort, reverse=reverse)
        finally:
            await base.close()

    asyncio.run(_impl())


@files_app.command("mkdir")
def files_mkdir(
    parent_path: str = typer.Argument(..., help="Родительский каталог"),
    name: str = typer.Argument(..., help="Имя новой папки"),
) -> None:
    """Создать новую директорию в хранилище File Station.

    Args:
        parent_path: Путь к родительскому каталогу.
        name: Имя создаваемой директории.
    """
    async def _impl() -> None:
        """Асинхронно создать директорию на томе."""
        base = BaseSynoClient()
        try:
            await SynoFileStationClient(base).mkdir(parent_path, name)
            console.print(f"[bold green]✓ Папка '{parent_path.rstrip('/')}/{name}' создана[/bold green]")
        finally:
            await base.close()

    asyncio.run(_impl())


@files_app.command("upload")
def files_upload(
    local_file: Path = typer.Argument(..., help="Путь к локальному файлу"),
    remote_dir: str = typer.Argument(..., help="Целевая папка на NAS"),
) -> None:
    """Загрузить локальный файл на сетевое хранилище Synology NAS.

    Args:
        local_file: Путь к файлу на локальном компьютере.
        remote_dir: Целевой каталог сохранения в File Station.
    """
    async def _impl() -> None:
        """Асинхронно загрузить файл через multipart-запрос."""
        base = BaseSynoClient()
        try:
            await SynoFileStationClient(base).upload_file(local_file, remote_dir)
            console.print(f"[bold green]✓ Файл '{local_file.name}' загружен в '{remote_dir}'[/bold green]")
        finally:
            await base.close()

    asyncio.run(_impl())


@files_app.command("rm")
def files_rm(
    remote_path: str = typer.Argument(..., help="Путь к удаляемому файлу или папке"),
) -> None:
    """Удалить файл или папку на хранилище Synology NAS.

    Args:
        remote_path: Полный путь к удаляемому объекту в File Station.
    """
    async def _impl() -> None:
        """Асинхронно удалить путь в File Station."""
        base = BaseSynoClient()
        try:
            await SynoFileStationClient(base).delete_path(remote_path)
            console.print(f"[bold red]✓ Удалено: {remote_path}[/bold red]")
        finally:
            await base.close()

    asyncio.run(_impl())
