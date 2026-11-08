"""CLI-команды управления виртуальными машинами и образами (Synology VMM)."""

from typing import Any, Optional, Tuple

import typer

from syno_cli.client.base import BaseSynoClient
from syno_cli.client.vmm import SynoVmmClient
from syno_cli.commands.common import cli_command, console
from syno_cli.views.tables import render_vms

vm_app = typer.Typer(help="Управление виртуальными машинами и образами (Synology VMM).")


@vm_app.command("list")
@cli_command(spinner_message="Запрос списка виртуальных машин VMM...")
async def vm_list(
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> Tuple[Any, Any]:
    """Вывести список виртуальных машин и их текущее состояние."""
    base = BaseSynoClient()
    try:
        vmm = SynoVmmClient(base)
        guests = await vmm.list_guests()
        return guests, render_vms
    finally:
        await base.close()


@vm_app.command("image-import")
@cli_command(spinner_message="Импорт образа в репозиторий VMM...")
async def vm_image_import(
    name: str = typer.Option(..., "--name", "-n", help="Имя образа в VMM"),
    path: str = typer.Option(..., "--path", "-p", help="Путь к ISO/OVA на NAS"),
    image_type: str = typer.Option("iso", "--type", "-t", help="Тип образа: iso, vdisk, ova"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> Tuple[Any, Any]:
    """Импортировать установочный образ (ISO/OVA) из хранилища NAS в VMM."""
    base = BaseSynoClient()
    try:
        vmm = SynoVmmClient(base)
        res = await vmm.import_image(image_name=name, ds_file_path=path, image_type=image_type)
        return (
            res,
            lambda _: console.print(
                f"[bold green]✓ Образ '{name}' ({image_type}) добавлен в VMM[/bold green]"
            ),
        )
    finally:
        await base.close()


@vm_app.command("create")
@cli_command(spinner_message="Создание виртуальной машины в VMM...")
async def vm_create(
    name: str = typer.Option(..., "--name", "-n", help="Имя виртуальной машины"),
    cpu: int = typer.Option(2, "--cpu", help="Количество ядер vCPU"),
    memory: int = typer.Option(2048, "--memory", "-m", help="Оперативная память в МБ"),
    storage: str = typer.Option("default_storage", "--storage", "-s", help="Имя хранилища VMM"),
    disk_gb: int = typer.Option(20, "--disk", "-d", help="Размер диска в ГБ"),
    iso: Optional[str] = typer.Option(None, "--iso", help="Имя ISO-образа для загрузки"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> Tuple[Any, Any]:
    """Создать новую виртуальную машину в Synology VMM."""
    base = BaseSynoClient()
    try:
        vmm = SynoVmmClient(base)
        res = await vmm.create_guest(
            name=name,
            vcpu_num=cpu,
            vram_size_mb=memory,
            storage_name=storage,
            disk_size_gb=disk_gb,
            iso_image_name=iso,
        )
        return (
            res,
            lambda _: console.print(
                f"[bold green]✓ Виртуальная машина '{name}' успешно создана[/bold green]"
            ),
        )
    finally:
        await base.close()


@vm_app.command("start")
@cli_command(spinner_message="Включение ВМ...")
async def vm_start(
    name: str = typer.Argument(..., help="Имя виртуальной машины"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> Tuple[Any, Any]:
    """Включить виртуальную машину."""
    base = BaseSynoClient()
    try:
        res = await SynoVmmClient(base).guest_power_action(name, "poweron")
        return (
            res,
            lambda _: console.print(f"[bold green]✓ ВМ '{name}' запущена[/bold green]"),
        )
    finally:
        await base.close()


@vm_app.command("stop")
@cli_command(spinner_message="Отправка сигнала выключения ВМ...")
async def vm_stop(
    name: str = typer.Argument(..., help="Имя виртуальной машины"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> Tuple[Any, Any]:
    """Мягко завершить работу виртуальной машины через ACPI shutdown."""
    base = BaseSynoClient()
    try:
        res = await SynoVmmClient(base).guest_power_action(name, "shutdown")
        return (
            res,
            lambda _: console.print(
                f"[bold yellow]✓ Отправлен сигнал выключения ВМ '{name}'[/bold yellow]"
            ),
        )
    finally:
        await base.close()
