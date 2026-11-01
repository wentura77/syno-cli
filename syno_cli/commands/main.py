"""Корневая точка входа CLI-приложения `syno` на базе фреймворка Typer."""

import asyncio
from pathlib import Path
from typing import Optional
import typer

from syno_cli.client.base import BaseSynoClient
from syno_cli.client.core import SynoCoreClient
from syno_cli.client.docker import SynoDockerClient
from syno_cli.client.download_station import SynoDownloadStationClient
from syno_cli.client.file_station import SynoFileStationClient
from syno_cli.client.vmm import SynoVmmClient
from syno_cli.views.tables import (
    console,
    render_docker_containers,
    render_docker_images,
    render_downloads,
    render_files,
    render_storage_disks,
    render_system_status,
    render_vms,
)

app = typer.Typer(
    name="syno",
    help="Консольная утилита управления Synology NAS через официальный DSM Web API.",
    no_args_is_help=True,
)

docker_app = typer.Typer(help="Управление контейнерами, образами и проектами Docker.")
vm_app = typer.Typer(help="Управление виртуальными машинами и образами (Synology VMM).")
files_app = typer.Typer(help="Управление файлами и папками на хранилище (File Station).")
download_app = typer.Typer(help="Мониторинг и управление закачками (Download Station).")

app.add_typer(docker_app, name="docker")
app.add_typer(vm_app, name="vm")
app.add_typer(files_app, name="files")
app.add_typer(download_app, name="download")


# ------------------------------------------------------------------------------
# Системные команды (status, storage, reboot, shutdown)
# ------------------------------------------------------------------------------
@app.command("status")
def cmd_status() -> None:
    """Показать сводный статус Synology NAS (CPU, RAM, температура, аптайм)."""
    async def _impl() -> None:
        base = BaseSynoClient()
        try:
            core = SynoCoreClient(base)
            info = await core.get_system_info()
            util = await core.get_utilization()
            render_system_status(info, util)
        finally:
            await base.close()

    asyncio.run(_impl())


@app.command("storage")
def cmd_storage() -> None:
    """Показать состояние физических дисков, температуру и статус SMART."""
    async def _impl() -> None:
        base = BaseSynoClient()
        try:
            core = SynoCoreClient(base)
            data = await core.get_storage_info()
            render_storage_disks(data)
        finally:
            await base.close()

    asyncio.run(_impl())


# ------------------------------------------------------------------------------
# Команды Docker / Container Manager
# ------------------------------------------------------------------------------
@docker_app.command("ps")
def docker_ps() -> None:
    """Список всех контейнеров Docker и их статусов."""
    async def _impl() -> None:
        base = BaseSynoClient()
        try:
            docker = SynoDockerClient(base)
            containers = await docker.list_containers()
            render_docker_containers(containers)
        finally:
            await base.close()

    asyncio.run(_impl())


@docker_app.command("images")
def docker_images() -> None:
    """Список загруженных локальных Docker-образов."""
    async def _impl() -> None:
        base = BaseSynoClient()
        try:
            docker = SynoDockerClient(base)
            images = await docker.list_images()
            render_docker_images(images)
        finally:
            await base.close()

    asyncio.run(_impl())


@docker_app.command("pull")
def docker_pull(
    image: str = typer.Argument(..., help="Имя образа с тегом, например nginx:latest"),
) -> None:
    """Скачать (pull) новый Docker-образ из реестра на Synology NAS."""
    repo, tag = (image.split(":", 1) + ["latest"])[:2] if ":" in image else (image, "latest")

    async def _impl() -> None:
        base = BaseSynoClient()
        try:
            docker = SynoDockerClient(base)
            await docker.pull_image(repo, tag)
            console.print(f"[bold green]✓ Запущена загрузка образа {repo}:{tag}[/bold green]")
        finally:
            await base.close()

    asyncio.run(_impl())


@docker_app.command("run")
def docker_run(
    name: str = typer.Option(..., "--name", "-n", help="Имя создаваемого контейнера"),
    image: str = typer.Option(..., "--image", "-i", help="Образ (например, redis:alpine)"),
    port: Optional[list[str]] = typer.Option(None, "--port", "-p", help="Проброс портов HOST:CONT"),
    volume: Optional[list[str]] = typer.Option(None, "--volume", "-v", help="Тома /host:/cont"),
    env: Optional[list[str]] = typer.Option(None, "--env", "-e", help="Переменные KEY=VAL"),
) -> None:
    """Создать и запустить новый Docker-контейнер на Synology NAS."""
    async def _impl() -> None:
        base = BaseSynoClient()
        try:
            docker = SynoDockerClient(base)
            await docker.create_container(
                name=name,
                image=image,
                ports=port,
                volumes=volume,
                env_vars=env,
                auto_start=True,
            )
            console.print(f"[bold green]✓ Контейнер '{name}' ({image}) создан и запущен[/bold green]")
        finally:
            await base.close()

    asyncio.run(_impl())


@docker_app.command("start")
def docker_start(name: str = typer.Argument(..., help="Имя контейнера")) -> None:
    """Запустить остановленный контейнер."""
    async def _impl() -> None:
        base = BaseSynoClient()
        try:
            await SynoDockerClient(base).start_container(name)
            console.print(f"[bold green]✓ Контейнер '{name}' запущен[/bold green]")
        finally:
            await base.close()

    asyncio.run(_impl())


@docker_app.command("stop")
def docker_stop(name: str = typer.Argument(..., help="Имя контейнера")) -> None:
    """Остановить работающий контейнер."""
    async def _impl() -> None:
        base = BaseSynoClient()
        try:
            await SynoDockerClient(base).stop_container(name)
            console.print(f"[bold yellow]✓ Контейнер '{name}' остановлен[/bold yellow]")
        finally:
            await base.close()

    asyncio.run(_impl())


# ------------------------------------------------------------------------------
# Команды Virtual Machine Manager (VMM)
# ------------------------------------------------------------------------------
@vm_app.command("list")
def vm_list() -> None:
    """Вывести список виртуальных машин и их текущее состояние."""
    async def _impl() -> None:
        base = BaseSynoClient()
        try:
            vmm = SynoVmmClient(base)
            guests = await vmm.list_guests()
            render_vms(guests)
        finally:
            await base.close()

    asyncio.run(_impl())


@vm_app.command("image-import")
def vm_image_import(
    name: str = typer.Option(..., "--name", "-n", help="Имя образа в VMM"),
    path: str = typer.Option(..., "--path", "-p", help="Путь к ISO/OVA на NAS (например /isos/ubuntu.iso)"),
    image_type: str = typer.Option("iso", "--type", "-t", help="Тип образа: iso, vdisk, ova"),
) -> None:
    """Импортировать установочный образ (ISO/OVA) из хранилища NAS в VMM."""
    async def _impl() -> None:
        base = BaseSynoClient()
        try:
            vmm = SynoVmmClient(base)
            await vmm.import_image(image_name=name, ds_file_path=path, image_type=image_type)
            console.print(f"[bold green]✓ Образ '{name}' ({image_type}) добавлен в VMM[/bold green]")
        finally:
            await base.close()

    asyncio.run(_impl())


@vm_app.command("create")
def vm_create(
    name: str = typer.Option(..., "--name", "-n", help="Имя виртуальной машины"),
    cpu: int = typer.Option(2, "--cpu", help="Количество ядер vCPU"),
    memory: int = typer.Option(2048, "--memory", "-m", help="Оперативная память в МБ"),
    storage: str = typer.Option("default_storage", "--storage", "-s", help="Имя хранилища VMM"),
    disk_gb: int = typer.Option(20, "--disk", "-d", help="Размер диска в ГБ"),
    iso: Optional[str] = typer.Option(None, "--iso", help="Имя ISO-образа для загрузки"),
) -> None:
    """Создать новую виртуальную машину в Synology VMM."""
    async def _impl() -> None:
        base = BaseSynoClient()
        try:
            vmm = SynoVmmClient(base)
            await vmm.create_guest(
                name=name,
                vcpu_num=cpu,
                vram_size_mb=memory,
                storage_name=storage,
                disk_size_gb=disk_gb,
                iso_image_name=iso,
            )
            console.print(f"[bold green]✓ Виртуальная машина '{name}' успешно создана[/bold green]")
        finally:
            await base.close()

    asyncio.run(_impl())


@vm_app.command("start")
def vm_start(name: str = typer.Argument(..., help="Имя виртуальной машины")) -> None:
    """Включить виртуальную машину."""
    async def _impl() -> None:
        base = BaseSynoClient()
        try:
            await SynoVmmClient(base).guest_power_action(name, "poweron")
            console.print(f"[bold green]✓ ВМ '{name}' запущена[/bold green]")
        finally:
            await base.close()

    asyncio.run(_impl())


@vm_app.command("stop")
def vm_stop(name: str = typer.Argument(..., help="Имя виртуальной машины")) -> None:
    """Мягко выключить виртуальную машину (ACPI shutdown)."""
    async def _impl() -> None:
        base = BaseSynoClient()
        try:
            await SynoVmmClient(base).guest_power_action(name, "shutdown")
            console.print(f"[bold yellow]✓ Отправлен сигнал выключения ВМ '{name}'[/bold yellow]")
        finally:
            await base.close()

    asyncio.run(_impl())


# ------------------------------------------------------------------------------
# Команды File Station
# ------------------------------------------------------------------------------
@files_app.command("ls")
def files_ls(
    path: str = typer.Argument("/", help="Путь в File Station (например / или /docker)"),
) -> None:
    """Показать список файлов и папок в указанной директории хранилища."""
    async def _impl() -> None:
        base = BaseSynoClient()
        try:
            fs = SynoFileStationClient(base)
            items = await fs.list_dir(path)
            render_files(items, path)
        finally:
            await base.close()

    asyncio.run(_impl())


@files_app.command("mkdir")
def files_mkdir(
    parent_path: str = typer.Argument(..., help="Родительский каталог"),
    name: str = typer.Argument(..., help="Имя новой папки"),
) -> None:
    """Создать новую директорию на томе хранилища."""
    async def _impl() -> None:
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
    """Загрузить локальный файл на хранилище Synology NAS."""
    async def _impl() -> None:
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
    """Удалить файл или папку на хранилище Synology NAS."""
    async def _impl() -> None:
        base = BaseSynoClient()
        try:
            await SynoFileStationClient(base).delete_path(remote_path)
            console.print(f"[bold red]✓ Удалено: {remote_path}[/bold red]")
        finally:
            await base.close()

    asyncio.run(_impl())


# ------------------------------------------------------------------------------
# Команды Download Station
# ------------------------------------------------------------------------------
@download_app.command("list")
def download_list() -> None:
    """Показать скорость закачек и список всех задач в Download Station."""
    async def _impl() -> None:
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
    """Добавить новую задачу скачивания в Download Station."""
    async def _impl() -> None:
        base = BaseSynoClient()
        try:
            await SynoDownloadStationClient(base).add_task(uri, destination=dest)
            console.print(f"[bold green]✓ Задача скачивания добавлена: {uri}[/bold green]")
        finally:
            await base.close()

    asyncio.run(_impl())


@download_app.command("pause")
def download_pause(task_id: str = typer.Argument(..., help="ID задачи (например dbid_1)")) -> None:
    """Поставить задачу скачивания на паузу."""
    async def _impl() -> None:
        base = BaseSynoClient()
        try:
            await SynoDownloadStationClient(base).pause_task(task_id)
            console.print(f"[bold yellow]✓ Задача '{task_id}' приостановлена[/bold yellow]")
        finally:
            await base.close()

    asyncio.run(_impl())


@download_app.command("resume")
def download_resume(task_id: str = typer.Argument(..., help="ID задачи (например dbid_1)")) -> None:
    """Возобновить скачивание задачи."""
    async def _impl() -> None:
        base = BaseSynoClient()
        try:
            await SynoDownloadStationClient(base).resume_task(task_id)
            console.print(f"[bold green]✓ Задача '{task_id}' возобновлена[/bold green]")
        finally:
            await base.close()

    asyncio.run(_impl())


def run() -> None:
    """Точка входа для консольного скрипта Poetry (`syno`)."""
    app()


if __name__ == "__main__":
    run()
