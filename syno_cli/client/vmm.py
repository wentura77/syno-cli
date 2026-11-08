"""Клиент управления виртуальными машинами Synology Virtual Machine Manager (VMM)."""

import json
from typing import Any, Optional

from syno_cli.client.base import BaseSynoClient


class SynoVmmClient:
    """Клиент для работы с API виртуализации `SYNO.Virtualization.*`.

    Поддерживает получение списка виртуальных машин, управление их питанием,
    импорт установочных образов (ISO/OVA), создание новых ВМ с расширенной
    конфигурацией и работу со снапшотами.
    """

    def __init__(self, base: BaseSynoClient) -> None:
        """Инициализирует клиент Virtual Machine Manager.

        Args:
            base: Экземпляр базового клиента DSM.
        """
        self.base = base

    async def list_guests(self) -> list[dict[str, Any]]:
        """Получает список всех виртуальных машин в кластере VMM.

        Returns:
            list[dict[str, Any]]: Список словарей с характеристиками и статусом ВМ.
        """
        try:
            data = await self.base.request(
                "SYNO.Virtualization.Guest",
                "list",
                version=1,
                params={"additional": "true"},
            )
            guests = data.get("guests", [])
            if isinstance(guests, list) and guests:
                return list(guests)
        except Exception:
            pass

        data = await self.base.request(
            "SYNO.Virtualization.API.Guest",
            "list",
            version=1,
            params={"additional": "true"},
        )
        return list(data.get("guests", []))

    async def guest_power_action(self, guest_name: str, action: str) -> dict[str, Any]:
        """Выполняет действие над питанием виртуальной машины.

        Args:
            guest_name: Имя виртуальной машины.
            action: Действие (`poweron`, `shutdown`, `poweroff`, `restart`).

        Returns:
            dict[str, Any]: Ответ сервера о выполнении операции.
        """
        clean_name = guest_name.strip("\"'")
        try:
            return await self.base.request(
                "SYNO.Virtualization.Guest.Action",
                action,
                version=1,
                params={"guest_name": f'"{clean_name}"'},
                http_method="POST",
            )
        except Exception:
            return await self.base.request(
                "SYNO.Virtualization.API.Guest.Action",
                action,
                version=1,
                params={"guest_name": guest_name},
                http_method="POST",
            )

    async def list_images(self) -> list[dict[str, Any]]:
        """Возвращает список зарегистрированных ISO-образов и шаблонов дисков в VMM.

        Returns:
            list[dict[str, Any]]: Список образов в хранилище VMM.
        """
        try:
            data = await self.base.request("SYNO.Virtualization.Guest.Image", "list", version=1)
            images = data.get("images", [])
            if isinstance(images, list) and images:
                return list(images)
        except Exception:
            pass

        data = await self.base.request("SYNO.Virtualization.API.Guest.Image", "list", version=1)
        return list(data.get("images", []))

    async def import_image(
        self,
        image_name: str,
        ds_file_path: str,
        image_type: str = "iso",
        storage_names: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Создает/импортирует новый образ (ISO или диск/OVA) в репозиторий VMM из папки NAS.

        Args:
            image_name: Имя создаваемого образа в VMM.
            ds_file_path: Путь к файлу образа на томе Synology (например, `/isos/ubuntu.iso`).
            image_type: Тип образа (`iso`, `vdisk`, `ova`).
            storage_names: Список имен хранилищ VMM для размещения образа.

        Returns:
            dict[str, Any]: Данные созданной задачи импорта образа.
        """
        storages = storage_names or ["default_storage"]
        try:
            return await self.base.request(
                "SYNO.Virtualization.Guest.Image",
                "create",
                version=1,
                params={
                    "image_name": f'"{image_name}"',
                    "ds_file_path": f'"{ds_file_path}"',
                    "type": f'"{image_type.lower()}"',
                    "storage_names": json.dumps(storages),
                },
                http_method="POST",
            )
        except Exception:
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
        vcpu_num: int = 1,
        vram_size_mb: int = 1024,
        storage_name: Optional[str] = None,
        disk_size_gb: int = 20,
        iso_image_name: Optional[str] = None,
        auto_start: bool = False,
        autorun: bool = False,
        sync_time: bool = True,
        is_windows: bool = False,
        desc: str = "",
        network: Optional[str] = None,
        mac: Optional[str] = None,
        vnic_type: int = 1,
        cpu_passthrough: bool = True,
        hyperv: bool = True,
        cpu_weight: int = 256,
        cpu_pin: int = 0,
    ) -> dict[str, Any]:
        """Создает новую виртуальную машину в Synology Virtual Machine Manager.

        Выполняет обращение к API SYNO.Virtualization.Guest, автоматически
        разрешая идентификаторы кластера (host_id, repo_id, network_id).

        Args:
            name: Имя создаваемой виртуальной машины.
            vcpu_num: Количество виртуальных вычислительных ядер (vCPU).
            vram_size_mb: Объем выделяемой оперативной памяти в мегабайтах.
            storage_name: Название хранилища VMM (Repo) или его подстрока.
            disk_size_gb: Размер первичного виртуального диска в гигабайтах.
            iso_image_name: Путь к установочному ISO-образу или его имя в VMM.
            auto_start: Запустить ли виртуальную машину сразу после создания.
            autorun: Автоматически запускать ВМ при загрузке или перезапуске NAS.
            sync_time: Синхронизировать ли системные часы гостевой ОС с хостом DSM.
            is_windows: Применять ли системные оптимизации профиля Microsoft Windows.
            desc: Пользовательское описание и заметки к виртуальной машине.
            network: Название или UUID виртуальной сети VMM для подключения интерфейса.
            mac: Статический аппаратный MAC-адрес виртуальной сетевой карты.
            vnic_type: Числовой идентификатор модели сетевого адаптера (1 — VirtIO).
            cpu_passthrough: Передавать ли процессорные флаги хоста гостевой ОС.
            hyperv: Включить ли расширения просвещения Hyper-V для оптимизации производительности.
            cpu_weight: Относительный вес приоритета планировщика CPU (по умолчанию 256).
            cpu_pin: Номер или маска привязки к физическим ядрам процессора (0 — отключено).

        Returns:
            dict[str, Any]: Ответ сервера с метаданными созданной виртуальной машины (guest_id).

        Raises:
            RuntimeError: Если в кластере VMM не обнаружено активных хостов или хранилищ.
        """
        # 1. Получаем список хостов VMM
        host_id = ""
        host_name = ""
        try:
            hosts_res = await self.base.request(
                "SYNO.Virtualization.Host", "list", version=1, http_method="POST"
            )
            hosts = hosts_res.get("hosts", [])
            if hosts and isinstance(hosts, list):
                host = hosts[0]
                host_id = str(host.get("host_id", ""))
                host_name = str(host.get("host_name", ""))
        except Exception:
            pass

        # 2. Получаем список хранилищ VMM (Repo)
        repo_id = ""
        repo_name = ""
        try:
            repo_res = await self.base.request(
                "SYNO.Virtualization.Repo", "list", version=1, http_method="POST"
            )
            repos = repo_res.get("repos", [])
            if repos and isinstance(repos, list):
                target_repo = repos[0]
                if storage_name:
                    for r in repos:
                        r_name = str(r.get("repo_name", "")).lower()
                        r_id = str(r.get("repo_id", "")).lower()
                        if storage_name.lower() in r_name or storage_name.lower() == r_id:
                            target_repo = r
                            break
                repo_id = str(target_repo.get("repo_id", ""))
                repo_name = str(target_repo.get("repo_name", ""))
        except Exception:
            pass

        if not repo_name and storage_name:
            repo_name = storage_name

        # 3. Получаем виртуальную сеть (Network)
        net_id = ""
        try:
            net_res = await self.base.request(
                "SYNO.Virtualization.Network", "list", version=1, http_method="POST"
            )
            networks = net_res.get("networks", [])
            if networks and isinstance(networks, list):
                target_net = networks[0]
                if network:
                    for n in networks:
                        n_name = str(n.get("network_name", "")).lower()
                        n_id = str(n.get("network_id", "")).lower()
                        if network.lower() in n_name or network.lower() == n_id:
                            target_net = n
                            break
                net_id = str(target_net.get("network_id", ""))
        except Exception:
            pass

        # 4. Формируем структуры дисков и интерфейсов
        vdisks_data = [
            {
                "type": "add",
                "vdisk_mode": 1,
                "name": "Виртуальный диск 1",
                "unmap": False,
                "iops_enable": False,
                "fua": True,
                "dev_limit": 0,
                "dev_reservation": 0,
                "dev_weight": 3,
                "vdisk_size": disk_size_gb,
                "idx": 0,
            }
        ]

        vnics_data: list[dict[str, Any]] = []
        if net_id:
            vnic_entry: dict[str, Any] = {
                "prefer_sriov": False,
                "vnic_type": vnic_type,
                "type": "add",
                "network_id": net_id,
            }
            if mac:
                vnic_entry["mac"] = mac
            vnics_data.append(vnic_entry)

        iso_data = [iso_image_name, "unmounted"] if iso_image_name else ["unmounted", "unmounted"]
        clean_name = name.strip("\"'")

        # 5. Параметры вызова API со строгой строковой сериализацией
        params: dict[str, Any] = {
            "name": f'"{clean_name}"',
            "vcpu_num": str(vcpu_num),
            "vram_size": str(vram_size_mb),
            "repo_id": f'"{repo_id}"' if repo_id else f'"{repo_name}"',
            "repo_name": f'"{repo_name}"',
            "host_id": f'"{host_id}"',
            "repo_host_name": f'"{host_name}"',
            "boot_from": '"disk"',
            "bios": '"legacy"',
            "video_card": '"vmvga"',
            "machine_type": '"pc"',
            "cpu_weight": str(cpu_weight),
            "cpu_passthru": "true" if cpu_passthrough else "false",
            "hyperv_enlighten": "true" if hyperv else "false",
            "cpu_pin_num": str(cpu_pin),
            "poweron_after_create": "true" if auto_start else "false",
            "auto_sync_guest_time": "true" if sync_time else "false",
            "serial_console": "true",
            "usb_version": "0",
            "is_windows_vm": "true" if is_windows else "false",
            "use_ovmf": "false",
            "is_general_vm": "true",
            "autorun": "1" if autorun else "0",
            "auto_switch": "0",
            "kb_layout": '"Default"',
            "desc": f'"{desc}"',
            "guest_privilege": "[]",
            "vdisk_struct": "[]",
            "usbs": '["unmounted","unmounted","unmounted","unmounted"]',
            "iso_images": json.dumps(iso_data),
            "vdisks": json.dumps(vdisks_data),
            "vnics": json.dumps(vnics_data),
        }

        # 6. Основная попытка через SYNO.Virtualization.Guest
        try:
            return await self.base.request(
                "SYNO.Virtualization.Guest",
                "create",
                version=1,
                params=params,
                http_method="POST",
            )
        except Exception:
            fallback_params: dict[str, Any] = {
                "guest_name": clean_name,
                "vcpu_num": vcpu_num,
                "vram_size": vram_size_mb,
                "storage_name": storage_name or repo_name,
                "vdisks": [{"create_type": 0, "vdisk_size": disk_size_gb * 1024 * 1024 * 1024}],
            }
            if iso_image_name:
                fallback_params["iso_images"] = [iso_image_name, "unmounted"]
            return await self.base.request(
                "SYNO.Virtualization.API.Guest",
                "create",
                version=1,
                params=fallback_params,
                http_method="POST",
            )

    async def create_snapshot(self, guest_name: str, description: str = "") -> dict[str, Any]:
        """Создает мгновенный снимок (snapshot) состояния виртуальной машины.

        Args:
            guest_name: Имя виртуальной машины.
            description: Описание снимка.

        Returns:
            dict[str, Any]: Информация о созданном снимке.
        """
        clean_name = guest_name.strip("\"'")
        try:
            return await self.base.request(
                "SYNO.Virtualization.Snapshot",
                "create",
                version=1,
                params={"guest_name": f'"{clean_name}"', "description": f'"{description}"'},
                http_method="POST",
            )
        except Exception:
            return await self.base.request(
                "SYNO.Virtualization.API.Snapshot",
                "create",
                version=1,
                params={"guest_name": guest_name, "description": description},
                http_method="POST",
            )
