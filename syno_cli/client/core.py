"""Клиент мониторинга системных ресурсов, хранилища и питания Synology DSM."""

from typing import Any

from syno_cli.client.base import BaseSynoClient


class SynoCoreClient:
    """
    Клиент для работы с системными интерфейсами `SYNO.Core.*` и `SYNO.Storage.*`.

    Позволяет получать информацию о системе, загрузке CPU/RAM, состоянии RAID-пулов,
    физических дисков и управлять питанием NAS.
    """

    def __init__(self, base: BaseSynoClient) -> None:
        """
        Инициализирует клиент системного мониторинга.

        Args:
            base (BaseSynoClient): Экземпляр базового клиента DSM.
        """
        self.base = base

    async def get_system_info(self) -> dict[str, Any]:
        """
        Получает общую информацию об устройстве (модель, версия DSM, температура, аптайм).

        Returns:
            dict[str, Any]: Словарь с системными характеристиками NAS.
        """
        return await self.base.request("SYNO.Core.System", "info", version=1)

    async def get_utilization(self) -> dict[str, Any]:
        """
        Получает текущие показатели загрузки CPU, использования памяти и сети.

        Returns:
            dict[str, Any]: Метрики утилизации ресурсов (`cpu`, `memory`, `network`).
        """
        return await self.base.request("SYNO.Core.System.Utilization", "get", version=1)

    async def get_storage_info(self) -> dict[str, Any]:
        """
        Запрашивает состояние дисковой подсистемы: томов, пулов хранения и физических дисков.

        Returns:
            dict[str, Any]: Структура с полями `disks`, `storagePools` и `volumes`.
        """
        return await self.base.request("SYNO.Storage.CGI.Storage", "load_info", version=1)

    async def reboot(self) -> dict[str, Any]:
        """
        Отправляет команду безопасной перезагрузки Synology NAS.

        Returns:
            dict[str, Any]: Ответ сервера о запуске перезагрузки.
        """
        return await self.base.request("SYNO.Core.System", "reboot", version=1, http_method="POST")

    async def shutdown(self) -> dict[str, Any]:
        """
        Отправляет команду безопасного выключения Synology NAS.

        Returns:
            dict[str, Any]: Ответ сервера о запуске завершения работы.
        """
        return await self.base.request(
            "SYNO.Core.System", "shutdown", version=1, http_method="POST"
        )
