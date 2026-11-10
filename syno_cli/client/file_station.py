"""Клиент управления файловой системой на томах хранилища через File Station API."""

import io
import json
from pathlib import Path
from typing import Any, Callable, Optional

import httpx

from syno_cli.client.base import BaseSynoClient
from syno_cli.constants import (
    DEFAULT_CONNECT_TIMEOUT_SEC,
    DEFAULT_TIMEOUT_SEC,
    UPLOAD_POOL_TIMEOUT_SEC,
    UPLOAD_WRITE_TIMEOUT_SEC,
)


class _ProgressFileReader(io.BufferedReader):
    """Потоковый ридер с методом .read() для httpx и вызовом прогресс-коллбэка."""

    def __init__(self, raw: io.RawIOBase, callback: Optional[Callable[[int], None]] = None) -> None:
        """Инициализирует потоковый ридер с обратным вызовом прогресса.

        Args:
            raw: Базовый бинарный поток файла.
            callback: Функция, принимающая количество прочитанных байт.
        """
        super().__init__(raw)
        self._callback = callback

    def read(self, size: Optional[int] = -1) -> bytes:
        """Читает блок байт из файла и уведомляет прогресс-коллбэк.

        Args:
            size: Размер читаемого блока.

        Returns:
            bytes: Прочитанные байты.
        """
        chunk = super().read(size)
        if chunk and self._callback:
            self._callback(len(chunk))
        return chunk


def _normalize_remote_path(path: str) -> str:
    """Нормализует путь в файловой системе Synology File Station.

    Args:
        path: Исходный путь.

    Returns:
        str: Нормализованный путь с ведущим слэшем.
    """
    clean = path.strip()
    if not clean.startswith("/"):
        clean = f"/{clean}"
    if clean != "/":
        clean = clean.rstrip("/")
    return clean


class SynoFileStationClient:
    """Клиент для работы с семейством интерфейсов `SYNO.FileStation.*`."""

    def __init__(self, base: BaseSynoClient) -> None:
        """Инициализирует клиент File Station.

        Args:
            base: Экземпляр базового клиента DSM.
        """
        self.base = base

    async def list_shares(self) -> list[dict[str, Any]]:
        """Возвращает список корневых папок общего доступа (Shared Folders).

        Returns:
            list[dict[str, Any]]: Список общих папок с их путями, размерами и временем.
        """
        data = await self.base.request(
            "SYNO.FileStation.List",
            "list_share",
            version=2,
            params={"additional": ["real_path", "size", "time"]},
        )
        return list(data.get("shares", []))

    async def list_dir(self, folder_path: str) -> list[dict[str, Any]]:
        """Возвращает список файлов и подпапок в указанной директории.

        Args:
            folder_path: Путь в File Station (например, `/docker` или `/video`).

        Returns:
            list[dict[str, Any]]: Список объектов файлов и директорий с метаданными.
        """
        clean_path = folder_path.strip()
        if not clean_path or clean_path == "/":
            return await self.list_shares()

        data = await self.base.request(
            "SYNO.FileStation.List",
            "list",
            version=2,
            params={
                "folder_path": _normalize_remote_path(clean_path),
                "additional": ["real_path", "size", "time", "perm"],
            },
        )
        return list(data.get("files", []))

    async def mkdir(self, folder_path: str, name: str) -> dict[str, Any]:
        """Создает новую папку внутри указанного каталога.

        Args:
            folder_path: Родительский путь в File Station.
            name: Имя новой директории.

        Returns:
            dict[str, Any]: Данные о созданной папке.
        """
        clean_parent = _normalize_remote_path(folder_path)
        return await self.base.request(
            "SYNO.FileStation.CreateFolder",
            "create",
            version=2,
            params={"folder_path": [clean_parent], "name": [name]},
            http_method="POST",
        )

    async def upload_file(
        self,
        local_path: Path,
        dest_folder_path: str,
        overwrite: bool = True,
        content_stream: Optional[bytes] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> dict[str, Any]:
        """Загружает локальный файл в целевую директорию на Synology NAS.

        Args:
            local_path: Путь к локальному файлу на компьютере.
            dest_folder_path: Целевой каталог в File Station.
            overwrite: Перезаписывать ли существующий файл.
            content_stream: Опциональные байты файла в памяти (для тестирования).
            progress_callback: Функция обратного вызова для передачи прогресса по байтам.

        Returns:
            dict[str, Any]: Ответ сервера о завершении загрузки.
        """
        await self.base.ensure_authenticated()
        clean_dest = _normalize_remote_path(dest_folder_path)
        _, max_ver = self.base.resolve_endpoint("SYNO.FileStation.Upload", 2)
        use_ver = min(max_ver, 3) if "SYNO.FileStation.Upload" in self.base.api_map else 2

        upload_timeout = httpx.Timeout(
            connect=DEFAULT_CONNECT_TIMEOUT_SEC,
            read=DEFAULT_TIMEOUT_SEC,
            write=UPLOAD_WRITE_TIMEOUT_SEC,
            pool=UPLOAD_POOL_TIMEOUT_SEC,
        )

        form_params: dict[str, Any] = {
            "path": clean_dest,
            "create_parents": "true",
            "overwrite": "true" if overwrite else "false",
        }

        if content_stream is not None:
            file_obj: Any = io.BytesIO(content_stream)
        elif progress_callback:
            file_obj = _ProgressFileReader(io.FileIO(local_path, "rb"), progress_callback)
        else:
            file_obj = open(local_path, "rb")

        try:
            return await self.base.request(
                "SYNO.FileStation.Upload",
                "upload",
                version=use_ver,
                params=form_params,
                http_method="POST",
                files={"file": (local_path.name, file_obj, "application/octet-stream")},
                timeout=upload_timeout,
            )
        finally:
            if hasattr(file_obj, "close"):
                file_obj.close()

    async def download_file(
        self,
        remote_path: str,
        local_dest_path: Path,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Path:
        """Скачивает файл с сетевого хранилища Synology NAS на локальный компьютер.

        Args:
            remote_path: Полный путь к файлу в File Station.
            local_dest_path: Локальный путь к файлу или папке назначения.
            progress_callback: Коллбэк прогресса `(downloaded_bytes, total_bytes)`.

        Returns:
            Path: Путь к сохраненному локальному файлу.
        """
        await self.base.ensure_authenticated()
        clean_remote = _normalize_remote_path(remote_path)
        _, ver = self.base.resolve_endpoint("SYNO.FileStation.Download", 2)

        dest = local_dest_path.expanduser()
        if dest.is_dir():
            target_file = dest / Path(clean_remote).name
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            target_file = dest

        dl_params = {
            "path": json.dumps([clean_remote]) if ver >= 2 else clean_remote,
            "mode": '"download"' if ver >= 2 else "download",
        }
        return await self.base.stream_download(
            api_name="SYNO.FileStation.Download",
            method="download",
            params=dl_params,
            target_file=target_file,
            default_version=2,
            progress_callback=progress_callback,
        )

    async def delete_path(self, path: str) -> dict[str, Any]:
        """Удаляет указанный файл или директорию на хранилище Synology.

        Args:
            path: Полный путь к удаляемому объекту в File Station.

        Returns:
            dict[str, Any]: Ответ сервера.
        """
        return await self.base.request(
            "SYNO.FileStation.Delete",
            "delete",
            version=2,
            params={"path": [_normalize_remote_path(path)]},
            http_method="POST",
        )

    async def copy_or_move(
        self, src_path: str, dest_folder_path: str, remove_src: bool = False
    ) -> dict[str, Any]:
        """Запускает операцию копирования или перемещения файла/директории.

        Args:
            src_path: Исходный путь к файлу или папке.
            dest_folder_path: Целевая папка назначения.
            remove_src: Если `True` — выполняет перемещение (`mv`), иначе копирование (`cp`).

        Returns:
            dict[str, Any]: Идентификатор задачи копирования/перемещения.
        """
        return await self.base.request(
            "SYNO.FileStation.CopyMove",
            "start",
            version=3,
            params={
                "path": [_normalize_remote_path(src_path)],
                "dest_folder_path": _normalize_remote_path(dest_folder_path),
                "overwrite": True,
                "remove_src": remove_src,
            },
            http_method="POST",
        )

    async def create_sharing_link(
        self,
        path: str,
        password: Optional[str] = None,
        date_expired: Optional[str] = None,
    ) -> dict[str, Any]:
        """Создает публичную ссылку для скачивания файла или папки.

        Args:
            path: Путь к файлу или директории в File Station.
            password: Пароль для защиты ссылки (опционально).
            date_expired: Дата истечения срока в формате `YYYY-MM-DD`.

        Returns:
            dict[str, Any]: Сгенерированная ссылка в списке `links`.
        """
        params: dict[str, Any] = {"path": [_normalize_remote_path(path)]}
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

    async def get_copy_move_status(self, taskid: str) -> dict[str, Any]:
        """Запрашивает статус выполнения асинхронной задачи копирования или перемещения.

        Args:
            taskid: Идентификатор задачи, полученный при вызове `copy_or_move`.

        Returns:
            dict[str, Any]: Словарь с состоянием задачи (finished, progress, processed_size и др.).
        """
        return await self.base.request(
            "SYNO.FileStation.CopyMove",
            "status",
            version=3,
            params={"taskid": f'"{taskid}"'},
            http_method="GET",
        )

    async def wait_copy_move(
        self,
        taskid: str,
        poll_interval: float = 0.5,
        timeout: float = 60.0,
    ) -> dict[str, Any]:
        """Ожидает завершения асинхронной задачи копирования или перемещения.

        Args:
            taskid: Идентификатор задачи.
            poll_interval: Интервал опроса статуса в секундах.
            timeout: Максимальное время ожидания завершения задачи в секундах.

        Returns:
            dict[str, Any]: Финальное состояние задачи.

        Raises:
            TimeoutError: Если операция не завершилась за отведенное время.
            DsmApiError: Если статус задачи сообщает об ошибке выполнения.
        """
        import asyncio
        import time

        start_time = time.monotonic()
        while True:
            status = await self.get_copy_move_status(taskid)
            if status.get("finished", False):
                return status
            if time.monotonic() - start_time > timeout:
                raise TimeoutError(f"Превышен таймаут ожидания задачи CopyMove {taskid}")
            await asyncio.sleep(poll_interval)
