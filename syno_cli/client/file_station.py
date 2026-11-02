"""Клиент управления файловой системой на томах хранилища через File Station API."""

import io
import json
from pathlib import Path
from typing import Any, Callable, Optional
import httpx

from syno_cli.client.base import BaseSynoClient
from syno_cli.exceptions import DsmApiError, DsmAuthError


class _ProgressFileReader(io.BufferedReader):
    """Потоковый ридер с методом .read() для httpx и вызовом прогресс-коллбэка."""

    def __init__(self, raw: io.RawIOBase, callback: Optional[Callable[[int], None]] = None) -> None:
        super().__init__(raw)
        self._callback = callback

    def read(self, size: Optional[int] = -1) -> bytes:
        chunk = super().read(size)
        if chunk and self._callback:
            self._callback(len(chunk))
        return chunk


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
        """
        Возвращает список файлов и подпапок в указанной директории.

        Args:
            folder_path (str): Путь в File Station (например, `/docker` или `/video`).

        Returns:
            list[dict[str, Any]]: Список объектов файлов и директорий с метаданными.
        """
        clean_path = folder_path.strip()
        if clean_path != "/":
            clean_path = clean_path.rstrip("/")

        if not clean_path or clean_path == "/":
            return await self.list_shares()

        data = await self.base.request(
            "SYNO.FileStation.List",
            "list",
            version=2,
            params={
                "folder_path": clean_path,
                "additional": ["real_path", "size", "time", "perm"],
            },
        )
        return list(data.get("files", []))

    async def mkdir(self, folder_path: str, name: str) -> dict[str, Any]:
        """
        Создает новую папку внутри указанного каталога.

        Args:
            folder_path: Родительский путь в File Station.
            name: Имя новой директории.

        Returns:
            dict[str, Any]: Данные о созданной папке.
        """
        clean_parent = folder_path.rstrip("/") if folder_path != "/" else "/"
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
        retry_auth: bool = True,
    ) -> dict[str, Any]:
        """Загружает локальный файл в целевую директорию на Synology NAS.

        Поддерживает потоковую загрузку больших файлов (ISO 8+ GB) без переполнения памяти.

        Args:
            local_path: Путь к локальному файлу на компьютере.
            dest_folder_path: Целевой каталог в File Station.
            overwrite: Перезаписывать ли существующий файл.
            content_stream: Опциональные байты файла в памяти.
            progress_callback: Функция обратного вызова для передачи прогресса по байтам.
            retry_auth: Разрешить повторную аутентификацию при истечении сессии.

        Returns:
            dict[str, Any]: Ответ сервера о завершении загрузки.
        """
        if not self.base.sid:
            await self.base.login()
        elif not self.base.api_map:
            try:
                await self.base.discover_apis()
            except Exception:
                pass

        clean_dest = dest_folder_path.strip()
        if not clean_dest.startswith("/"):
            clean_dest = f"/{clean_dest}"
        if clean_dest != "/":
            clean_dest = clean_dest.rstrip("/")

        cgi_path, max_ver = self.base._resolve_cgi_and_version("SYNO.FileStation.Upload", 2)
        use_ver = min(max_ver, 3) if "SYNO.FileStation.Upload" in self.base.api_map else 2

        query_params = {
            "api": "SYNO.FileStation.Upload",
            "version": str(use_ver),
            "method": "upload",
            "_sid": str(self.base.sid),
        }
        headers = {"Cookie": f"id={self.base.sid}"}
        overwrite_val = "true" if overwrite else "false"

        upload_timeout = httpx.Timeout(connect=20.0, read=120.0, write=3600.0, pool=30.0)

        # Поддерживаем как байты в памяти (для тестов), так и потоковый ридер с диска
        if content_stream is not None:
            file_obj: Any = io.BytesIO(content_stream)
        elif progress_callback:
            file_obj = _ProgressFileReader(io.FileIO(local_path, "rb"), progress_callback)
        else:
            file_obj = open(local_path, "rb")

        form_data = {
            "path": clean_dest,
            "create_parents": "true",
            "overwrite": overwrite_val,
        }
        file_payload = {"file": (local_path.name, file_obj, "application/octet-stream")}

        try:
            resp = await self.base.client.post(
                cgi_path,
                params=query_params,
                data=form_data,
                files=file_payload,
                headers=headers,
                timeout=upload_timeout,
            )
        except OSError as exc:
            if retry_auth:
                self.base._clear_session()
                await self.base.login()
                return await self.upload_file(
                    local_path=local_path,
                    dest_folder_path=dest_folder_path,
                    overwrite=overwrite,
                    content_stream=content_stream,
                    progress_callback=progress_callback,
                    retry_auth=False,
                )
            raise DsmApiError(
                code=119,
                api_name="SYNO.FileStation.Upload",
                details=f"Сервер NAS разорвал соединение ({exc}). Проверьте папку '{clean_dest}'.",
            ) from exc
        finally:
            if hasattr(file_obj, "close"):
                file_obj.close()

        resp.raise_for_status()
        body = resp.json()

        if not body.get("success"):
            code = body.get("error", {}).get("code", 100)
            if code in (105, 106, 107, 119) and retry_auth:
                self.base._clear_session()
                await self.base.login()
                return await self.upload_file(
                    local_path=local_path,
                    dest_folder_path=dest_folder_path,
                    overwrite=overwrite,
                    content_stream=content_stream,
                    progress_callback=progress_callback,
                    retry_auth=False,
                )
            if code in (400, 401, 402, 403, 404):
                raise DsmAuthError(code=code, api_name="SYNO.FileStation.Upload")
            raise DsmApiError(code=code, api_name="SYNO.FileStation.Upload")

        return body.get("data", {})

    async def download_file(
        self,
        remote_path: str,
        local_dest_path: Path,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        retry_auth: bool = True,
    ) -> Path:
        """Скачивает файл с сетевого хранилища Synology NAS на локальный компьютер."""
        if not self.base.sid:
            await self.base.login()
        elif not self.base.api_map:
            try:
                await self.base.discover_apis()
            except Exception:
                pass

        clean_remote = remote_path.strip()
        if not clean_remote.startswith("/"):
            clean_remote = f"/{clean_remote}"
        if clean_remote != "/":
            clean_remote = clean_remote.rstrip("/")

        cgi_path, ver = self.base._resolve_cgi_and_version("SYNO.FileStation.Download", 2)
        params = {
            "api": "SYNO.FileStation.Download",
            "version": str(ver),
            "method": "download",
            "path": json.dumps([clean_remote]) if ver >= 2 else clean_remote,
            "mode": '"download"' if ver >= 2 else "download",
            "_sid": str(self.base.sid),
        }
        headers = {"Cookie": f"id={self.base.sid}"}

        dest = local_dest_path.expanduser()
        if dest.is_dir():
            target_file = dest / Path(clean_remote).name
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            target_file = dest

        async with self.base.client.stream("GET", cgi_path, params=params, headers=headers) as resp:
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "").lower()

            if "application/json" in content_type or "text/plain" in content_type:
                raw_bytes = await resp.aread()
                try:
                    body = json.loads(raw_bytes.decode("utf-8"))
                    if not body.get("success", True):
                        code = body.get("error", {}).get("code", 100)
                        if code in (105, 106, 107, 119) and retry_auth:
                            self.base._clear_session()
                            await self.base.login()
                            return await self.download_file(
                                remote_path=remote_path,
                                local_dest_path=local_dest_path,
                                progress_callback=progress_callback,
                                retry_auth=False,
                            )
                        raise DsmApiError(code=code, api_name="SYNO.FileStation.Download")
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass

                target_file.write_bytes(raw_bytes)
                if progress_callback:
                    progress_callback(len(raw_bytes), len(raw_bytes))
                return target_file

            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            with open(target_file, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total)

        return target_file

    async def delete_path(self, path: str) -> dict[str, Any]:
        """
        Удаляет указанный файл или директорию на хранилище Synology.

        Args:
            path (str): Полный путь к удаляемому объекту в File Station.

        Returns:
            dict[str, Any]: Ответ сервера.
        """
        clean_path = path.rstrip("/") if path != "/" else "/"
        return await self.base.request(
            "SYNO.FileStation.Delete",
            "delete",
            version=2,
            params={"path": [clean_path]},
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
        clean_src = src_path.rstrip("/") if src_path != "/" else "/"
        clean_dest = dest_folder_path.rstrip("/") if dest_folder_path != "/" else "/"
        return await self.base.request(
            "SYNO.FileStation.CopyMove",
            "start",
            version=3,
            params={
                "path": [clean_src],
                "dest_folder_path": clean_dest,
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
        clean_path = path.rstrip("/") if path != "/" else "/"
        params: dict[str, Any] = {"path": [clean_path]}
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
