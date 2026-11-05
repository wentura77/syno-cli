"""Клиент управления виртуальными машинами Synology Virtual Machine Manager (VMM)."""

from typing import Any

from syno_cli.client.base import BaseSynoClient


class SynoVmmClient:
    """
    Клиент для работы с API виртуализации `SYNO.Virtualization.API.*`.

    Поддерживает получение списка виртуальных машин, управление их питанием,
    импорт установочных образов (ISO/OVA), создание новых ВМ и работу со снапшотами.
    """

    def __init__(self, base: BaseSynoClient) -> None:
        """
        Инициализирует клиент Virtual Machine Manager.

        Args:
            base (BaseSynoClient): Экземпляр базового клиента DSM.
        """
        self.base = base

    async def list_guests(self) -> list[dict[str, Any]]:
        """
        Получает список всех виртуальных машин в кластере VMM.

        Returns:
            list[dict[str, Any]]: Список словарей с характеристиками и статусом ВМ.
        """
        data = await self.base.request(
            "SYNO.Virtualization.API.Guest",
            "list",
            version=1,
            params={"additional": True},
        )
        return list(data.get("guests", []))

    async def guest_power_action(self, guest_name: str, action: str) -> dict[str, Any]:
        """
        Выполняет действие над питанием виртуальной машины.

        Args:
            guest_name (str): Имя виртуальной машины.
            action (str): Действие (`poweron`, `shutdown`, `poweroff`, `restart`).

        Returns:
            dict[str, Any]: Ответ сервера о выполнении операции.
        """
        return await self.base.request(
            "SYNO.Virtualization.API.Guest.Action",
            action,
            version=1,
            params={"guest_name": guest_name},
            http_method="POST",
        )

    async def list_images(self) -> list[dict[str, Any]]:
        """
        Возвращает список зарегистрированных ISO-образов и шаблонов дисков в VMM.

        Returns:
            list[dict[str, Any]]: Список образов в хранилище VMM.
        """
        data = await self.base.request("SYNO.Virtualization.API.Guest.Image", "list", version=1)
        return list(data.get("images", []))

    async def import_image(
        self,
        image_name: str,
        ds_file_path: str,
        image_type: str = "iso",
        storage_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Создает/импортирует новый образ (ISO или диск/OVA) в репозиторий VMM из папки NAS.

        Args:
            image_name (str): Имя создаваемого образа в VMM.
            ds_file_path (str): Путь к файлу образа на томе Synology (например, `/isos/ubuntu.iso`).
            image_type (str): Тип образа (`iso`, `vdisk`, `ova`).
            storage_names (list[str] | None): Список имен хранилищ VMM для размещения образа.

        Returns:
            dict[str, Any]: Данные созданной задачи импорта образа.
        """
        storages = storage_names or ["default_storage"]
        return await self.base.request(
            "SYNO.Virtualization.API.Guest.Image",
            "create",
            version=1,
            params={
                "image_name": image_name,
                "ds_file_path": ds_file_path,
                "type": image_type.lower(),
                "storage_names": storages,
            },
            http_method="POST",
        )

    async def create_guest(
        self,
        name: str,
        vcpu_num: int,
        vram_size_mb: int,
        storage_name: str,
        disk_size_gb: int = 20,
        iso_image_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Создает новую виртуальную машину в Synology VMM.

        Args:
            name (str): Имя создаваемой виртуальной машины.
            vcpu_num (int): Количество виртуальных ядер CPU.
            vram_size_mb (int): Объем оперативной памяти в мегабайтах.
            storage_name (str): Имя пула хранения VMM.
            disk_size_gb (int): Размер создаваемого виртуального диска в ГБ.
            iso_image_name (str | None): Имя ISO-образа для монтирования в CD-ROM.

        Returns:
            dict[str, Any]: Данные о созданной виртуальной машине.
        """
        vdisks = [{"create_type": 0, "vdisk_size": disk_size_gb * 1024 * 1024 * 1024}]
        params: dict[str, Any] = {
            "guest_name": name,
            "vcpu_num": vcpu_num,
            "vram_size": vram_size_mb,
            "storage_name": storage_name,
            "vdisks": vdisks,
        }
        if iso_image_name:
            params["iso_images"] = [iso_image_name, "unmounted"]

        return await self.base.request(
            "SYNO.Virtualization.API.Guest",
            "create",
            version=1,
            params=params,
            http_method="POST",
        )

    async def create_snapshot(self, guest_name: str, description: str = "") -> dict[str, Any]:
        """
        Создает мгновенный снимок (snapshot) состояния виртуальной машины.

        Args:
            guest_name (str): Имя виртуальной машины.
            description (str): Описание снимка.

        Returns:
            dict[str, Any]: Информация о созданном снимке.
        """
        return await self.base.request(
            "SYNO.Virtualization.API.Snapshot",
            "create",
            version=1,
            params={"guest_name": guest_name, "description": description},
            http_method="POST",
        )
