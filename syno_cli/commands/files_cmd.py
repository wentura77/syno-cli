"""CLI-команды работы с файлами и папками хранилища (File Station)."""

import asyncio
from pathlib import Path

import typer
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

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
    parent_path: str = typer.Argument(
        ...,
        autocompletion=complete_remote_path,
        help="Родительский каталог на NAS",
    ),
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
            console.print(
                f"[bold green]✓ Папка '{parent_path.rstrip('/')}/{name}' создана[/bold green]"
            )
        finally:
            await base.close()

    asyncio.run(_impl())


@files_app.command("upload")
def files_upload(
    local_file: Path = typer.Argument(..., help="Путь к локальному файлу на компьютере"),
    remote_dir: str = typer.Argument(
        ...,
        autocompletion=complete_remote_path,
        help="Целевая папка на NAS (например, /docker или /video/Films)",
    ),
    overwrite: bool = typer.Option(
        True,
        "--overwrite/--no-overwrite",
        help="Перезаписывать существующий файл в целевой папке",
    ),
) -> None:
    """Загрузить локальный файл на сетевое хранилище Synology NAS.

    Args:
        local_file: Путь к файлу на локальном компьютере.
        remote_dir: Целевой каталог сохранения в File Station.
        overwrite: Флаг перезаписи файла.
    """
    resolved_local = local_file.expanduser()
    if not resolved_local.is_file():
        console.print(f"[bold red]✗ Локальный файл не найден:[/bold red] {local_file}")
        raise typer.Exit(code=1)

    async def _impl() -> None:
        """Асинхронно загрузить файл через потоковый поток с индикатором прогресса."""
        base = BaseSynoClient()
        try:
            total_size = resolved_local.stat().st_size
            with Progress(
                TextColumn("[bold blue]⬆ {task.fields[filename]}"),
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                task_id = progress.add_task(
                    "upload", filename=resolved_local.name, total=total_size
                )

                def _on_chunk(chunk_len: int) -> None:
                    progress.update(task_id, advance=chunk_len)

                await SynoFileStationClient(base).upload_file(
                    local_path=resolved_local,
                    dest_folder_path=remote_dir,
                    overwrite=overwrite,
                    progress_callback=_on_chunk,
                )

            console.print(
                f"[bold green]✓ Файл '{resolved_local.name}' успешно загружен в '{remote_dir}'[/bold green]"
            )
        finally:
            await base.close()

    asyncio.run(_impl())


@files_app.command("download")
def files_download(
    remote_path: str = typer.Argument(
        ...,
        autocompletion=complete_remote_path,
        help="Полный путь к файлу на NAS (например, /docker/compose.yml)",
    ),
    dest: Path = typer.Option(
        Path("."),
        "--dest",
        "-d",
        help="Локальная папка или файл назначения (по умолчанию: текущая папка)",
    ),
) -> None:
    """Скачать файл с Synology NAS на локальный компьютер.

    Args:
        remote_path: Путь к файлу на сетевом хранилище в File Station.
        dest: Локальный путь сохранения файла.
    """

    async def _impl() -> None:
        """Асинхронно скачать файл с отображением прогресс-бара."""
        base = BaseSynoClient()
        try:
            fs = SynoFileStationClient(base)
            filename = Path(remote_path.rstrip("/")).name
            with Progress(
                TextColumn("[bold cyan]⬇ {task.fields[filename]}"),
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                task_id = progress.add_task("download", filename=filename, total=None)

                def _on_progress(downloaded: int, total: int) -> None:
                    progress.update(
                        task_id,
                        completed=downloaded,
                        total=total if total > 0 else None,
                    )

                saved_path = await fs.download_file(
                    remote_path=remote_path,
                    local_dest_path=dest,
                    progress_callback=_on_progress,
                )

            console.print(
                f"[bold green]✓ Файл успешно сохранен:[/bold green] {saved_path.resolve()}"
            )
        finally:
            await base.close()

    asyncio.run(_impl())


@files_app.command("rm")
def files_rm(
    remote_path: str = typer.Argument(
        ...,
        autocompletion=complete_remote_path,
        help="Путь к удаляемому файлу или папке на NAS",
    ),
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
