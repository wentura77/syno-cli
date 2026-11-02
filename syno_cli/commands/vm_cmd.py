"""CLI-команды управления виртуальными машинами и образами (Synology VMM)."""

import asyncio
from typing import Optional
import typer

from syno_cli.client.base import BaseSynoClient
from syno_cli.client.vmm import SynoVmmClient
from syno_cli.views.tables import console, render_vms

vm_app = typer.Typer(help="Управление виртуальными машинами и образами (Synology VMM).")


@vm_app.command("list")
def vm_list() -> None:
    """Вывести список виртуальных машин и их текущее состояние."""
    async def _impl() -> None:
        """Асинхронно получить и отобразить список виртуальных машин."""
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
    """Импортировать установочный образ (ISO/OVA) из хранилища NAS в VMM.

    Args:
        name: Имя регистрируемого образа в репозитории VMM.
        path: Полный путь к файлу на томе Synology.
        image_type: Формат импортируемого файла (iso, vdisk, ova).
    """
    async def _impl() -> None:
        """Асинхронно импортировать образ диска или ISO."""
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
    """Создать новую виртуальную машину в Synology VMM.

    Args:
        name: Имя создаваемой виртуальной машины.
        cpu: Количество выделяемых ядер vCPU.
        memory: Объем оперативной памяти в мегабайтах.
        storage: Имя целевого пула хранения VMM.
        disk_gb: Размер системного виртуального диска в гигабайтах.
        iso: Опциональное имя зарегистрированного ISO для загрузки.
    """
    async def _impl() -> None:
        """Асинхронно отправить запрос создания виртуальной машины."""
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
    """Включить виртуальную машину.

    Args:
        name: Имя целевой виртуальной машины.
    """
    async def _impl() -> None:
        """Асинхронно отправить сигнал включения ВМ."""
        base = BaseSynoClient()
        try:
            await SynoVmmClient(base).guest_power_action(name, "poweron")
            console.print(f"[bold green]✓ ВМ '{name}' запущена[/bold green]")
        finally:
            await base.close()

    asyncio.run(_impl())


@vm_app.command("stop")
def vm_stop(name: str = typer.Argument(..., help="Имя виртуальной машины")) -> None:
    """Мягко завершить работу виртуальной машины через ACPI shutdown.

    Args:
        name: Имя целевой виртуальной машины.
    """
    async def _impl() -> None:
        """Асинхронно отправить сигнал мягкого завершения работы ВМ."""
        base = BaseSynoClient()
        try:
            await SynoVmmClient(base).guest_power_action(name, "shutdown")
            console.print(f"[bold yellow]✓ Отправлен сигнал выключения ВМ '{name}'[/bold yellow]")
        finally:
            await base.close()

    asyncio.run(_impl())
