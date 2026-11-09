"""CLI-команды работы с файлами и папками хранилища (File Station)."""

from pathlib import Path
from typing import Callable, Optional

import typer
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from syno_cli.commands.common import CommandResult, cli_command, console
from syno_cli.commands.completion import complete_remote_path
from syno_cli.facade import SynoDSM
from syno_cli.views.tables import render_files

files_app = typer.Typer(help="Управление файлами и папками на хранилище (File Station).")


def _create_transfer_progress(prefix_icon: str) -> Progress:
    """Создает сконфигурированный индикатор прогресса передачи файлов Rich.

    Args:
        prefix_icon: Текстовый префикс колонки имени файла.

    Returns:
        Progress: Экземпляр прогресс-бара.
    """
    return Progress(
        TextColumn(f"{prefix_icon} {{task.fields[filename]}}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    )


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
) -> CommandResult:
    """Отобразить список файлов и директорий с поддержкой сортировки.

    Args:
        path: Путь в File Station.
        sort: Поле сортировки.
        reverse: Обратный порядок сортировки.
        json_output: Флаг вывода в формате JSON.

    Returns:
        CommandResult: Список элементов и функция отрисовки.
    """
    _ = json_output
    async with SynoDSM() as nas:
        items = await nas.files.list_dir(path)
        return items, lambda d: render_files(d, path, sort_by=sort, reverse=reverse)


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
) -> CommandResult:
    """Создать новую директорию в хранилище File Station.

    Args:
        parent_path: Родительский путь в File Station.
        name: Имя создаваемой папки.
        json_output: Флаг вывода в формате JSON.

    Returns:
        CommandResult: Ответ DSM и колбэк подтверждения.
    """
    _ = json_output
    async with SynoDSM() as nas:
        res = await nas.files.mkdir(parent_path, name)
        return (
            res,
            lambda _: console.print(
                f"[bold green]✓ Папка '{parent_path.rstrip('/')}/{name}' создана[/bold green]"
            ),
        )


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
) -> CommandResult:
    """Загрузить локальный файл на сетевое хранилище Synology NAS.

    Args:
        local_file: Локальный путь к файлу.
        remote_dir: Целевой каталог на NAS.
        overwrite: Перезаписывать ли существующий файл.
        json_output: Флаг вывода в формате JSON.

    Returns:
        CommandResult: Ответ DSM и колбэк подтверждения.

    Raises:
        FileNotFoundError: Если локальный файл не найден.
    """
    resolved_local = local_file.expanduser()
    if not resolved_local.is_file():
        raise FileNotFoundError(f"Локальный файл не найден: {local_file}")

    total_size = resolved_local.stat().st_size
    progress: Optional[Progress] = None
    cb: Optional[Callable[[int], None]] = None

    if not json_output:
        progress = _create_transfer_progress("[bold blue]⬆")
        progress.start()
        task_id = progress.add_task("upload", filename=resolved_local.name, total=total_size)

        def _on_chunk(chunk_len: int) -> None:
            if progress is not None:
                progress.update(task_id, advance=chunk_len)

        cb = _on_chunk

    try:
        async with SynoDSM() as nas:
            res = await nas.files.upload_file(
                local_path=resolved_local,
                dest_folder_path=remote_dir,
                overwrite=overwrite,
                progress_callback=cb,
            )
    finally:
        if progress is not None:
            progress.stop()

    return (
        res,
        lambda _: console.print(
            f"[bold green]✓ Файл '{resolved_local.name}' успешно загружен в '{remote_dir}'[/bold green]"
        ),
    )


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
) -> CommandResult:
    """Скачать файл с Synology NAS на локальный компьютер.

    Args:
        remote_path: Путь к файлу на NAS.
        dest: Локальный путь назначения.
        json_output: Флаг вывода в формате JSON.

    Returns:
        CommandResult: Путь к сохраненному файлу и колбэк подтверждения.
    """
    filename = Path(remote_path.rstrip("/")).name
    progress: Optional[Progress] = None
    cb: Optional[Callable[[int, int], None]] = None

    if not json_output:
        progress = _create_transfer_progress("[bold cyan]⬇")
        progress.start()
        task_id = progress.add_task("download", filename=filename, total=None)

        def _on_progress(downloaded: int, total: int) -> None:
            if progress is not None:
                progress.update(task_id, completed=downloaded, total=total if total > 0 else None)

        cb = _on_progress

    try:
        async with SynoDSM() as nas:
            saved_path = await nas.files.download_file(
                remote_path=remote_path,
                local_dest_path=dest,
                progress_callback=cb,
            )
    finally:
        if progress is not None:
            progress.stop()

    return (
        {"saved_path": str(saved_path.resolve())},
        lambda _: console.print(
            f"[bold green]✓ Файл успешно сохранен:[/bold green] {saved_path.resolve()}"
        ),
    )


@files_app.command("rm")
@cli_command(spinner_message="Удаление объекта на NAS...")
async def files_rm(
    remote_path: str = typer.Argument(
        ...,
        autocompletion=complete_remote_path,
        help="Путь к удаляемому файлу или папке на NAS",
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Удалить файл или папку на хранилище Synology NAS.

    Args:
        remote_path: Путь к удаляемому объекту в File Station.
        json_output: Флаг вывода в формате JSON.

    Returns:
        CommandResult: Ответ DSM и колбэк подтверждения.
    """
    _ = json_output
    async with SynoDSM() as nas:
        res = await nas.files.delete_path(remote_path)
        return (
            res,
            lambda _: console.print(f"[bold red]✓ Удалено: {remote_path}[/bold red]"),
        )
