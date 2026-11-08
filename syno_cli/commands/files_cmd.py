"""CLI-команды работы с файлами и папками хранилища (File Station)."""

from pathlib import Path
from typing import Any, Tuple

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
from syno_cli.commands.common import cli_command, console
from syno_cli.commands.completion import complete_remote_path
from syno_cli.views.tables import render_files

files_app = typer.Typer(help="Управление файлами и папками на хранилище (File Station).")


@files_app.command("ls")
@cli_command(spinner_message="Чтение каталога File Station...")
async def files_ls(
    path: str = typer.Argument(
        "/",
        autocompletion=complete_remote_path,
        help="Путь в File Station (например / или /docker)",
    ),
    sort: str = typer.Option(
        "mtime",
        "--sort",
        "-s",
        help="Поле сортировки: mtime, name, size, crtime",
    ),
    reverse: bool = typer.Option(
        True,
        "--reverse",
        "-r",
        help="Инвертировать порядок сортировки",
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> Tuple[Any, Any]:
    """Отобразить список файлов и директорий с поддержкой сортировки."""
    base = BaseSynoClient()
    try:
        fs = SynoFileStationClient(base)
        items = await fs.list_dir(path)
        return items, lambda d: render_files(d, path, sort_by=sort, reverse=reverse)
    finally:
        await base.close()


@files_app.command("mkdir")
@cli_command(spinner_message="Создание директории на NAS...")
async def files_mkdir(
    parent_path: str = typer.Argument(
        ...,
        autocompletion=complete_remote_path,
        help="Родительский каталог на NAS",
    ),
    name: str = typer.Argument(..., help="Имя новой папки"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> Tuple[Any, Any]:
    """Создать новую директорию в хранилище File Station."""
    base = BaseSynoClient()
    try:
        res = await SynoFileStationClient(base).mkdir(parent_path, name)
        return (
            res,
            lambda _: console.print(
                f"[bold green]✓ Папка '{parent_path.rstrip('/')}/{name}' создана[/bold green]"
            ),
        )
    finally:
        await base.close()


@files_app.command("upload")
@cli_command()
async def files_upload(
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
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> Tuple[Any, Any]:
    """Загрузить локальный файл на сетевое хранилище Synology NAS."""
    resolved_local = local_file.expanduser()
    if not resolved_local.is_file():
        raise FileNotFoundError(f"Локальный файл не найден: {local_file}")

    base = BaseSynoClient()
    try:
        total_size = resolved_local.stat().st_size
        cb = None

        if not json_output:
            progress = Progress(
                TextColumn("[bold blue]⬆ {task.fields[filename]}"),
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                console=console,
            )
            progress.start()
            task_id = progress.add_task("upload", filename=resolved_local.name, total=total_size)

            def _on_chunk(chunk_len: int) -> None:
                progress.update(task_id, advance=chunk_len)

            cb = _on_chunk

        res = await SynoFileStationClient(base).upload_file(
            local_path=resolved_local,
            dest_folder_path=remote_dir,
            overwrite=overwrite,
            progress_callback=cb,
        )

        if not json_output and "progress" in locals():
            progress.stop()

        return (
            res,
            lambda _: console.print(
                f"[bold green]✓ Файл '{resolved_local.name}' успешно загружен в '{remote_dir}'[/bold green]"
            ),
        )
    finally:
        await base.close()


@files_app.command("download")
@cli_command()
async def files_download(
    remote_path: str = typer.Argument(
        ...,
        autocompletion=complete_remote_path,
        help="Полный путь к файлу на NAS (например, /docker/compose.yml)",
    ),
    dest: Path = typer.Option(
        Path("."),
        "--dest",
        "-d",
        help="Локальная папка или файл назначения",
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> Tuple[Any, Any]:
    """Скачать файл с Synology NAS на локальный компьютер."""
    base = BaseSynoClient()
    try:
        fs = SynoFileStationClient(base)
        filename = Path(remote_path.rstrip("/")).name
        cb = None

        if not json_output:
            progress = Progress(
                TextColumn("[bold cyan]⬇ {task.fields[filename]}"),
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                console=console,
            )
            progress.start()
            task_id = progress.add_task("download", filename=filename, total=None)

            def _on_progress(downloaded: int, total: int) -> None:
                progress.update(task_id, completed=downloaded, total=total if total > 0 else None)

            cb = _on_progress

        saved_path = await fs.download_file(
            remote_path=remote_path,
            local_dest_path=dest,
            progress_callback=cb,
        )

        if not json_output and "progress" in locals():
            progress.stop()

        return (
            {"saved_path": str(saved_path.resolve())},
            lambda _: console.print(
                f"[bold green]✓ Файл успешно сохранен:[/bold green] {saved_path.resolve()}"
            ),
        )
    finally:
        await base.close()


@files_app.command("rm")
@cli_command(spinner_message="Удаление объекта на NAS...")
async def files_rm(
    remote_path: str = typer.Argument(
        ...,
        autocompletion=complete_remote_path,
        help="Путь к удаляемому файлу или папке на NAS",
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> Tuple[Any, Any]:
    """Удалить файл или папку на хранилище Synology NAS."""
    base = BaseSynoClient()
    try:
        res = await SynoFileStationClient(base).delete_path(remote_path)
        return (
            res,
            lambda _: console.print(f"[bold red]✓ Удалено: {remote_path}[/bold red]"),
        )
    finally:
        await base.close()
