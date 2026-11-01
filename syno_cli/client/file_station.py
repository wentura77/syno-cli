"""Клиент управления файловой системой на томах хранилища через File Station API."""

from pathlib import Path
from typing import Any
from syno_cli.client.base import BaseSynoClient


class SynoFileStationClient:
    """
    Клиент для работы с семейством интерфейсов `SYNO.FileStation.*`.

    Обеспечивает просмотр папок, создание каталогов, загрузку и скачивание файлов,
    перемещение/копирование/удаление и генерацию публичных ссылок обмена.
    """

    def __init__(self, base: BaseSynoClient) -> None:
        """
        Инициализирует клиент File Station.

        Args:
            base (BaseSynoClient): Экземпляр базового клиента DSM.
        """
        self.base = base

    async def list_shares(self) -> list[dict[str, Any]]:
        """
        Возвращает список корневых папок общего доступа (Shared Folders).

        Returns:
            list[dict[str, Any]]: Список общих папок с их путями и размерами.
        """
        data = await self.base.request(
            "SYNO.FileStation.List",
            "list_share",
            version=2,
            params={"additional": ["real_path", "size", "time"]},
        )
        return list(data.get("shares", []))

    async def list_dir(self, folder_path: str) -> list[dict[str, Any]]:
        """
        Возвращает список файлов и подпапок в указанной директории.

        Args:
            folder_path (str): Путь в File Station (например, `/docker` или `/video`).

        Returns:
            list[dict[str, Any]]: Список объектов файлов и директорий.
        """
        if folder_path == "/":
            return await self.list_shares()
        data = await self.base.request(
            "SYNO.FileStation.List",
            "list",
            version=2,
            params={
                "folder_path": folder_path,
                "additional": ["real_path", "size", "time", "perm"],
            },
        )
        return list(data.get("files", []))

    async def mkdir(self, folder_path: str, name: str) -> dict[str, Any]:
        """
        Создает новую папку внутри указанного каталога.

        Args:
            folder_path (str): Родительский путь в File Station.
            name (str): Имя новой директории.

        Returns:
            dict[str, Any]: Данные о созданной папке.
        """
        return await self.base.request(
            "SYNO.FileStation.CreateFolder",
            "create",
            version=2,
            params={"folder_path": [folder_path], "name": [name]},
            http_method="POST",
        )

    async def upload_file(
        self, local_path: Path, dest_folder_path: str, overwrite: bool = True
    ) -> dict[str, Any]:
        """
        Загружает локальный файл в целевую директорию на Synology NAS.

        Args:
            local_path (Path): Путь к локальному файлу на компьютере.
            dest_folder_path (str): Целевой каталог в File Station.
            overwrite (bool): Перезаписывать ли существующий файл.

        Returns:
            dict[str, Any]: Ответ сервера о завершении загрузки файла.
        """
        file_bytes = local_path.read_bytes()
        files = {"file": (local_path.name, file_bytes, "application/octet-stream")}
        params = {
            "path": dest_folder_path,
            "create_parents": "true",
            "overwrite": "true" if overwrite else "false",
        }
        return await self.base.request(
            "SYNO.FileStation.Upload",
            "upload",
            version=2,
            params=params,
            http_method="POST",
            files=files,
        )

    async def delete_path(self, path: str) -> dict[str, Any]:
        """
        Удаляет указанный файл или директорию на хранилище Synology.

        Args:
            path (str): Полный путь к удаляемому объекту в File Station.

        Returns:
            dict[str, Any]: Ответ сервера.
        """
        return await self.base.request(
            "SYNO.FileStation.Delete",
            "delete",
            version=2,
            params={"path": [path]},
            http_method="POST",
        )

    async def copy_or_move(
        self, src_path: str, dest_folder_path: str, remove_src: bool = False
    ) -> dict[str, Any]:
        """
        Запускает операцию копирования или перемещения файла/директории.

        Args:
            src_path (str): Исходный путь к файлу или папке.
            dest_folder_path (str): Целевая папка назначения.
            remove_src (bool): Если `True` — выполняет перемещение (`mv`), иначе копирование (`cp`).

        Returns:
            dict[str, Any]: Идентификатор задачи копирования/перемещения.
        """
        return await self.base.request(
            "SYNO.FileStation.CopyMove",
            "start",
            version=3,
            params={
                "path": [src_path],
                "dest_folder_path": dest_folder_path,
                "overwrite": True,
                "remove_src": remove_src,
            },
            http_method="POST",
        )

    async def create_sharing_link(
        self, path: str, password: str | None = None, date_expired: str | None = None
    ) -> dict[str, Any]:
        """
        Создает публичную ссылку для скачивания файла или папки.

        Args:
            path (str): Путь к файлу или директории в File Station.
            password (str | None): Пароль для защиты ссылки (опционально).
            date_expired (str | None): Дата истечения срока в формате `YYYY-MM-DD`.

        Returns:
            dict[str, Any]: Сгенерированная ссылка в списке `links`.
        """
        params: dict[str, Any] = {"path": [path]}
        if password:
            params["password"] = password
        if date_expired:
            params["date_expired"] = date_expired
        return await self.base.request(
            "SYNO.FileStation.Sharing",
            "create",
            version=3,
            params=params,
            http_method="POST",
        )
