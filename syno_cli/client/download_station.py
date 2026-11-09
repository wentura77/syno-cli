"""Клиент мониторинга и управления задачами закачки в Download Station."""

import json
import re
from pathlib import Path
from typing import Any, Optional

from syno_cli.client.base import BaseSynoClient
from syno_cli.constants import DSM_ERR_API_NOT_EXISTS
from syno_cli.exceptions import DsmApiError


def normalize_destination(destination: Optional[str]) -> Optional[str]:
    """Нормализует относительный путь назначения для Download Station (без ведущих слэшей).

    Args:
        destination: Сырая строка пути назначения.

    Returns:
        Optional[str]: Очищенный путь или None.
    """
    if not destination:
        return None
    normalized = destination.replace("\\", "/").strip("/ ")
    normalized = re.sub(r"/+", "/", normalized)
    return normalized or None


class SynoDownloadStationClient:
    """Клиент для взаимодействия с интерфейсами `SYNO.DownloadStation.*` и `SYNO.DownloadStation2.*`."""

    def __init__(self, base: BaseSynoClient) -> None:
        """Инициализирует клиент Download Station.

        Args:
            base: Экземпляр базового клиента DSM.
        """
        self.base = base

    async def list_tasks(self) -> list[dict[str, Any]]:
        """Получает список всех задач загрузки с детальной информацией о прогрессе.

        Returns:
            list[dict[str, Any]]: Список задач скачивания.

        Raises:
            DsmApiError: Если пакет Download Station не установлен.
        """
        await self.base.ensure_authenticated()

        if self.base.api_map:
            has_ds = any(k.startswith("SYNO.DownloadStation") for k in self.base.api_map)
            if not has_ds:
                raise DsmApiError(
                    code=DSM_ERR_API_NOT_EXISTS,
                    api_name="DownloadStation",
                    details="Пакет 'Download Station' не установлен или остановлен в DSM",
                )

        if (
            "SYNO.DownloadStation2.Task" in self.base.api_map
            and "SYNO.DownloadStation.Task" not in self.base.api_map
        ):
            data = await self.base.request(
                "SYNO.DownloadStation2.Task",
                "list",
                params={"additional": ["detail", "transfer"]},
            )
            return list(data.get("task", data.get("tasks", [])))

        data = await self.base.request(
            "SYNO.DownloadStation.Task",
            "list",
            version=1,
            params={"additional": "detail,transfer"},
        )
        return list(data.get("tasks", []))

    async def get_statistic(self) -> dict[str, Any]:
        """Возвращает агрегированную статистику скоростей Download Station.

        Returns:
            dict[str, Any]: Словарь с ключами `speed_download` и `speed_upload`.
        """
        try:
            return await self.base.request("SYNO.DownloadStation.Statistic", "getinfo", version=1)
        except DsmApiError as exc:
            if exc.code != DSM_ERR_API_NOT_EXISTS:
                raise
            tasks = await self.list_tasks()
            dl = sum(
                int(t.get("additional", {}).get("transfer", {}).get("speed_download", 0))
                for t in tasks
            )
            ul = sum(
                int(t.get("additional", {}).get("transfer", {}).get("speed_upload", 0))
                for t in tasks
            )
            return {"speed_download": dl, "speed_upload": ul}

    async def add_task(self, uri: str, destination: Optional[str] = None) -> dict[str, Any]:
        """Добавляет новую задачу на скачивание по URL, magnet-ссылке или локальному торрент-файлу.

        Args:
            uri: Ссылка (HTTP/Magnet), путь к локальному `.torrent` или путь на томе NAS.
            destination: Целевая папка сохранения на NAS.

        Returns:
            dict[str, Any]: Ответ сервера о создании задачи.
        """
        await self.base.ensure_authenticated()
        clean_dest = normalize_destination(destination)

        local_file = Path(uri).expanduser()
        if local_file.is_file():
            return await self._add_local_file_task(local_file, clean_dest)

        if uri.startswith("/") and "SYNO.DownloadStation2.Task" in self.base.api_map:
            params_v2: dict[str, Any] = {
                "type": "file",
                "file": [uri],
                "create_list": False,
            }
            if clean_dest:
                params_v2["destination"] = clean_dest
            return await self.base.request(
                "SYNO.DownloadStation2.Task",
                "create",
                version=2,
                params=params_v2,
                http_method="POST",
            )

        params: dict[str, Any] = {"uri": uri}
        if clean_dest:
            params["destination"] = clean_dest

        return await self.base.request(
            "SYNO.DownloadStation.Task",
            "create",
            version=1,
            params=params,
            http_method="POST",
        )

    async def _add_local_file_task(
        self, file_path: Path, clean_dest: Optional[str] = None
    ) -> dict[str, Any]:
        """Загружает локальный `.torrent` или `.nzb` файл через базовый клиент.

        Args:
            file_path: Путь к локальному файлу.
            clean_dest: Нормализованный путь назначения.

        Returns:
            dict[str, Any]: Ответ сервера.
        """
        file_bytes = file_path.read_bytes()

        if "SYNO.DownloadStation2.Task" in self.base.api_map:
            _, ver = self.base.resolve_endpoint("SYNO.DownloadStation2.Task", 2)
            form_v2 = {
                "type": '"file"',
                "file": '["torrent"]',
                "create_list": "false",
                "destination": json.dumps(clean_dest or ""),
            }
            try:
                return await self.base.request(
                    "SYNO.DownloadStation2.Task",
                    "create",
                    version=ver,
                    params=form_v2,
                    http_method="POST",
                    files={"torrent": (file_path.name, file_bytes, "application/x-bittorrent")},
                )
            except DsmApiError:
                if "SYNO.DownloadStation.Task" not in self.base.api_map:
                    raise

        _, ver_v1 = self.base.resolve_endpoint("SYNO.DownloadStation.Task", 2)
        form_v1: dict[str, Any] = {"destination": clean_dest} if clean_dest else {}
        return await self.base.request(
            "SYNO.DownloadStation.Task",
            "create",
            version=min(ver_v1, 3),
            params=form_v1,
            http_method="POST",
            files={"file": (file_path.name, file_bytes, "application/x-bittorrent")},
        )

    async def pause_task(self, task_id: str) -> dict[str, Any]:
        """Приостанавливает выполнение задачи скачивания.

        Args:
            task_id: Идентификатор задачи.

        Returns:
            dict[str, Any]: Ответ сервера.
        """
        return await self.base.request(
            "SYNO.DownloadStation.Task",
            "pause",
            version=1,
            params={"id": task_id},
            http_method="POST",
        )

    async def resume_task(self, task_id: str) -> dict[str, Any]:
        """Возобновляет приостановленную задачу скачивания.

        Args:
            task_id: Идентификатор задачи.

        Returns:
            dict[str, Any]: Ответ сервера.
        """
        return await self.base.request(
            "SYNO.DownloadStation.Task",
            "resume",
            version=1,
            params={"id": task_id},
            http_method="POST",
        )

    async def delete_task(self, task_id: str, force_complete: bool = False) -> dict[str, Any]:
        """Удаляет задачу из списка Download Station.

        Args:
            task_id: Идентификатор задачи.
            force_complete: Принудительно завершить и удалить задачу.

        Returns:
            dict[str, Any]: Ответ сервера.
        """
        return await self.base.request(
            "SYNO.DownloadStation.Task",
            "delete",
            version=1,
            params={"id": task_id, "force_complete": force_complete},
            http_method="POST",
        )
