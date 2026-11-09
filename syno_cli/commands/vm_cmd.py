"""CLI-команды управления Virtual Machine Manager (VMM) в Synology DSM."""

from typing import Optional

import typer

from syno_cli.commands.common import CommandResult, cli_command, console
from syno_cli.constants import (
    DEFAULT_VMM_CPU_WEIGHT,
    DEFAULT_VMM_DISK_GB,
    DEFAULT_VMM_RAM_MB,
)
from syno_cli.facade import SynoDSM
from syno_cli.views.tables import render_vmm_guests, render_vmm_images

vm_app = typer.Typer(help="Управление виртуальными машинами, ISO-образами и снимками VMM.")


@vm_app.command("list")
@cli_command(spinner_message="Запрос списка виртуальных машин...")
async def vm_list(
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Вывести список всех виртуальных машин в кластере VMM и их статусы.

    Args:
        json_output: Флаг сериализации результата в формат JSON.

    Returns:
        CommandResult: Кортеж из списка виртуальных машин и функции рендеринга таблицы.
    """
    _ = json_output
    async with SynoDSM() as nas:
        guests = await nas.vmm.list_guests()
        return guests, render_vmm_guests


@vm_app.command("images")
@cli_command(spinner_message="Запрос образов VMM...")
async def vm_images(
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Вывести список зарегистрированных ISO-образов и шаблонов дисков в VMM.

    Args:
        json_output: Флаг сериализации результата в формат JSON.

    Returns:
        CommandResult: Кортеж из списка образов и функции рендеринга таблицы.
    """
    _ = json_output
    async with SynoDSM() as nas:
        images = await nas.vmm.list_images()
        return images, render_vmm_images


@vm_app.command("image-import")
@cli_command(spinner_message="Импорт образа в хранилище VMM...")
async def vm_image_import(
    name: str = typer.Argument(..., help="Имя регистрируемого образа в VMM"),
    path: str = typer.Argument(
        ..., help="Путь к файлу на томе NAS, например /volume1/iso/ubuntu.iso"
    ),
    image_type: str = typer.Option("iso", "--type", "-t", help="Тип образа (iso, vdisk, ova)"),
    storage: Optional[list[str]] = typer.Option(None, "--storage", "-s", help="Имя хранилища VMM"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Импортировать установочный ISO-образ или файл диска в репозиторий VMM.

    Args:
        name: Название регистрируемого образа.
        path: Путь к исходному файлу на томе Synology NAS.
        image_type: Формат файла образа (iso, vdisk, ova).
        storage: Список хранилищ VMM для размещения образа.
        json_output: Флаг сериализации результата в формат JSON.

    Returns:
        CommandResult: Кортеж из ответа DSM и колбэка подтверждения создания.
    """
    _ = json_output
    async with SynoDSM() as nas:
        result = await nas.vmm.import_image(
            image_name=name,
            ds_file_path=path,
            image_type=image_type,
            storage_names=storage,
        )
        return (
            result,
            lambda _: console.print(
                f"[bold green]✓ Образ '{name}' успешно зарегистрирован в VMM[/bold green]"
            ),
        )


@vm_app.command("create")
@cli_command(spinner_message="Создание виртуальной машины в VMM...")
async def vm_create(
    name: str = typer.Option(..., "--name", "-n", help="Имя виртуальной машины"),
    cpu: int = typer.Option(1, "--cpu", "-c", help="Количество vCPU ядер"),
    memory: int = typer.Option(DEFAULT_VMM_RAM_MB, "--memory", "-m", help="Объем памяти RAM (МБ)"),
    storage: Optional[str] = typer.Option(None, "--storage", "-s", help="Хранилище VMM (Repo)"),
    disk: int = typer.Option(
        DEFAULT_VMM_DISK_GB, "--disk", "-d", help="Размер системного диска (ГБ)"
    ),
    iso: Optional[str] = typer.Option(None, "--iso", help="Путь или имя ISO-образа"),
    start: bool = typer.Option(False, "--start", help="Запустить ВМ сразу после создания"),
    autorun: bool = typer.Option(False, "--autorun", help="Автозапуск ВМ при включении NAS"),
    sync_time: bool = typer.Option(
        True, "--sync-time/--no-sync-time", help="Синхронизация времени с хостом"
    ),
    windows: bool = typer.Option(False, "--windows/--linux", help="Тип профиля гостевой ОС"),
    desc: str = typer.Option("", "--desc", help="Описание или примечание к ВМ"),
    network: Optional[str] = typer.Option(None, "--network", help="Имя или ID виртуальной сети"),
    mac: Optional[str] = typer.Option(
        None, "--mac", help="Статический MAC-адрес (например 02:11:32:xx:xx:xx)"
    ),
    cpu_passthrough: bool = typer.Option(
        True,
        "--cpu-passthrough/--no-cpu-passthrough",
        help="Проброс инструкций хост-процессора",
    ),
    hyperv: bool = typer.Option(True, "--hyperv/--no-hyperv", help="Включение оптимизаций Hyper-V"),
    cpu_weight: int = typer.Option(
        DEFAULT_VMM_CPU_WEIGHT, "--cpu-weight", help="Приоритет процессорного времени"
    ),
    cpu_pin: int = typer.Option(
        0, "--cpu-pin", help="Привязка к физическим ядрам CPU (0 — выключено)"
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Создает виртуальную машину в Virtual Machine Manager с расширенной конфигурацией.

    Args:
        name: Название виртуальной машины.
        cpu: Выделенное количество ядер процессора (vCPU).
        memory: Выделяемая оперативная память в мегабайтах.
        storage: Название пула хранения VMM.
        disk: Емкость основного виртуального диска в ГБ.
        iso: Расположение ISO-образа для первичной загрузки.
        start: Флаг немедленного запуска после создания.
        autorun: Флаг автозапуска при рестарте хранилища NAS.
        sync_time: Флаг постоянной синхронизации времени с DSM.
        windows: Оптимизировать параметры окружения под ОС Windows.
        desc: Текстовое описание и назначение инстанса.
        network: Название виртуальной сети VMM.
        mac: Аппаратный MAC-адрес для гостевого сетевого интерфейса.
        cpu_passthrough: Включение прямого проброса модели хостового CPU.
        hyperv: Активация enlightenments для гостевых ОС.
        cpu_weight: Приоритет в очереди планировщика процессорного времени.
        cpu_pin: Привязка потоков гостя к ядрам хоста.
        json_output: Вывести ли результат в виде неформатированного JSON.

    Returns:
        CommandResult: Кортеж из словаря ответа DSM и колбэка форматированного вывода.
    """
    _ = json_output
    async with SynoDSM() as nas:
        result = await nas.vmm.create_guest(
            name=name,
            vcpu_num=cpu,
            vram_size_mb=memory,
            storage_name=storage,
            disk_size_gb=disk,
            iso_image_name=iso,
            auto_start=start,
            autorun=autorun,
            sync_time=sync_time,
            is_windows=windows,
            desc=desc,
            network=network,
            mac=mac,
            cpu_passthrough=cpu_passthrough,
            hyperv=hyperv,
            cpu_weight=cpu_weight,
            cpu_pin=cpu_pin,
        )
        return (
            result,
            lambda _: console.print(
                f"[bold green]✓ Виртуальная машина '{name}' успешно создана[/bold green]"
            ),
        )


@vm_app.command("start")
@cli_command(spinner_message="Запуск виртуальной машины...")
async def vm_start(
    name: str = typer.Argument(..., help="Имя виртуальной машины"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Запустить виртуальную машину (poweron).

    Args:
        name: Название запускаемой ВМ.
        json_output: Флаг вывода в JSON.

    Returns:
        CommandResult: Результат операции и функция вывода сообщения.
    """
    _ = json_output
    async with SynoDSM() as nas:
        result = await nas.vmm.guest_power_action(name, "poweron")
        return (
            result,
            lambda _: console.print(
                f"[bold green]✓ Виртуальная машина '{name}' запущена[/bold green]"
            ),
        )


@vm_app.command("stop")
@cli_command(spinner_message="Остановка виртуальной машины...")
async def vm_stop(
    name: str = typer.Argument(..., help="Имя виртуальной машины"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Принудительное выключение по питанию (poweroff)"
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Остановить виртуальную машину штатно (shutdown) или принудительно (poweroff).

    Args:
        name: Название останавливаемой ВМ.
        force: Флаг принудительного отключения питания.
        json_output: Флаг вывода в JSON.

    Returns:
        CommandResult: Результат операции и функция вывода сообщения.
    """
    _ = json_output
    action = "poweroff" if force else "shutdown"
    async with SynoDSM() as nas:
        result = await nas.vmm.guest_power_action(name, action)
        return (
            result,
            lambda _: console.print(
                f"[bold yellow]✓ Виртуальная машина '{name}' остановлена ({action})[/bold yellow]"
            ),
        )


@vm_app.command("restart")
@cli_command(spinner_message="Перезагрузка виртуальной машины...")
async def vm_restart(
    name: str = typer.Argument(..., help="Имя виртуальной машины"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Перезапустить виртуальную машину (restart).

    Args:
        name: Название перезагружаемой ВМ.
        json_output: Флаг вывода в JSON.

    Returns:
        CommandResult: Результат операции и функция вывода сообщения.
    """
    _ = json_output
    async with SynoDSM() as nas:
        result = await nas.vmm.guest_power_action(name, "restart")
        return (
            result,
            lambda _: console.print(
                f"[bold green]✓ Виртуальная машина '{name}' перезапущена[/bold green]"
            ),
        )


@vm_app.command("snapshot")
@cli_command(spinner_message="Создание снимка состояния ВМ...")
async def vm_snapshot(
    name: str = typer.Argument(..., help="Имя виртуальной машины"),
    desc: str = typer.Option("", "--desc", "-d", help="Описание или примечание к снимку"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Создать моментальный снимок (snapshot) состояния виртуальной машины.

    Args:
        name: Название виртуальной машины.
        desc: Текстовое описание снимка.
        json_output: Флаг вывода в JSON.

    Returns:
        CommandResult: Результат операции и функция вывода сообщения.
    """
    _ = json_output
    async with SynoDSM() as nas:
        result = await nas.vmm.create_snapshot(name, description=desc)
        return (
            result,
            lambda _: console.print(
                f"[bold green]✓ Снимок для '{name}' успешно создан[/bold green]"
            ),
        )
