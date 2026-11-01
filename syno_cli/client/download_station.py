"""Клиент мониторинга и управления задачами закачки в Download Station."""

import json
from pathlib import Path
from typing import Any, Optional
from syno_cli.client.base import BaseSynoClient
from syno_cli.exceptions import DsmApiError


class SynoDownloadStationClient:
    """
    Клиент для взаимодействия с интерфейсами `SYNO.DownloadStation.*` и `SYNO.DownloadStation2.*`.

    Поддерживает добавление URL/Magnet-ссылок, прямую загрузку локальных `.torrent`-файлов
    с компьютера и добавление файлов, уже находящихся на томах NAS.
    """

    def __init__(self, base: BaseSynoClient) -> None:
        self.base = base

    async def _ensure_ready(self) -> None:
        """Гарантирует наличие активной сессии `sid` и карты API `api_map`."""
        if not self.base.api_map:
            try:
                await self.base.discover_apis()
            except Exception:
                pass
        if not self.base.sid:
            await self.base.login()

    async def list_tasks(self) -> list[dict[str, Any]]:
        """Получает список всех задач загрузки с детальной информацией о прогрессе."""
        await self._ensure_ready()

        if self.base.api_map:
            has_ds = any(k.startswith("SYNO.DownloadStation") for k in self.base.api_map)
            if not has_ds:
                raise DsmApiError(
                    code=102,
                    api_name="DownloadStation",
                    details="Пакет 'Download Station' не установлен или остановлен в Центре пакетов DSM",
                )

        if "SYNO.DownloadStation2.Task" in self.base.api_map and "SYNO.DownloadStation.Task" not in self.base.api_map:
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
        """Возвращает агрегированную статистику скоростей Download Station."""
        try:
            return await self.base.request("SYNO.DownloadStation.Statistic", "getinfo", version=1)
        except DsmApiError as exc:
            if exc.code != 102:
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
        """
        Добавляет новую задачу на скачивание:
        1. Если `uri` — существующий локальный файл на ПК (например, `my.torrent`),
           загружает его на NAS по multipart/form-data.
        2. Если `uri` — URL, magnet-ссылка или путь на самом NAS, передает его через API.
        """
        await self._ensure_ready()

        # В Download Station путь destination НЕ должен начинаться со слэша '/'
        clean_dest = destination.lstrip("/") if destination else None

        local_file = Path(uri).expanduser()
        if local_file.is_file():
            return await self._add_local_file_task(local_file, clean_dest)

        # Если передан путь к файлу, уже лежащему на самом NAS (например, /video/my.torrent)
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

        # Стандартное добавление по URL / Magnet
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
        self, file_path: Path, clean_dest: Optional[str] = None, retry_auth: bool = True
    ) -> dict[str, Any]:
        """
        Загружает локальный `.torrent` или `.nzb` файл с компьютера в Download Station.
        Передает `_sid` в URL query-параметрах и Cookie, чтобы парсер multipart в DSM
        не отклонял запрос с кодом 119.
        """
        await self._ensure_ready()
        file_bytes = file_path.read_bytes()

        # Способ 1: SYNO.DownloadStation2.Task (DSM 7.x)
        if "SYNO.DownloadStation2.Task" in self.base.api_map:
            cgi_path, ver = self.base._resolve_cgi_and_version("SYNO.DownloadStation2.Task", 2)

            # ВАЖНО: _sid передается в URL (params) и cookies, иначе multipart-парсер DSM выдает ошибку 119
            query_params = {"_sid": str(self.base.sid)}
            cookies = {"id": str(self.base.sid)}

            form_data: dict[str, str] = {
                "api": "SYNO.DownloadStation2.Task",
                "version": str(ver),
                "method": "create",
                "type": '"file"',
                "file": '["torrent"]',
                "create_list": "false",
                "destination": json.dumps(clean_dest or ""),
            }
            files = {"torrent": (file_path.name, file_bytes, "application/x-bittorrent")}

            resp = await self.base.client.post(
                cgi_path,
                params=query_params,
                data=form_data,
                files=files,
                cookies=cookies,
            )
            resp.raise_for_status()
            body = resp.json()

            if body.get("success"):
                return body.get("data", {})

            code = body.get("error", {}).get("code", 100)
            if code in (105, 106, 107, 119) and retry_auth:
                self.base._clear_session()
                await self.base.login()
                return await self._add_local_file_task(file_path, clean_dest, retry_auth=False)

            # Если SYNO.DownloadStation2.Task вернул ошибку параметров, пробуем SYNO.DownloadStation.Task v1..3
            if "SYNO.DownloadStation.Task" not in self.base.api_map:
                raise DsmApiError(code=code, api_name="SYNO.DownloadStation2.Task")

        # Способ 2: Классический SYNO.DownloadStation.Task (через DownloadStation/task.cgi)
        cgi_v1, ver_v1 = self.base._resolve_cgi_and_version("SYNO.DownloadStation.Task", 2)
        query_v1 = {"_sid": str(self.base.sid)}
        cookies_v1 = {"id": str(self.base.sid)}
        form_v1: dict[str, str] = {
            "api": "SYNO.DownloadStation.Task",
            "version": str(min(ver_v1, 3)),
            "method": "create",
        }
        if clean_dest:
            form_v1["destination"] = clean_dest

        files_v1 = {"file": (file_path.name, file_bytes, "application/x-bittorrent")}
        resp_v1 = await self.base.client.post(
            cgi_v1,
            params=query_v1,
            data=form_v1,
            files=files_v1,
            cookies=cookies_v1,
        )
        resp_v1.raise_for_status()
        body_v1 = resp_v1.json()

        if not body_v1.get("success"):
            code_v1 = body_v1.get("error", {}).get("code", 100)
            if code_v1 in (105, 106, 107, 119) and retry_auth:
                self.base._clear_session()
                await self.base.login()
                return await self._add_local_file_task(file_path, clean_dest, retry_auth=False)
            raise DsmApiError(code=code_v1, api_name="SYNO.DownloadStation.Task")

        return body_v1.get("data", {})

    async def pause_task(self, task_id: str) -> dict[str, Any]:
        """Приостанавливает выполнение задачи скачивания."""
        return await self.base.request(
            "SYNO.DownloadStation.Task",
            "pause",
            version=1,
            params={"id": task_id},
            http_method="POST",
        )

    async def resume_task(self, task_id: str) -> dict[str, Any]:
        """Возобновляет приостановленную задачу скачивания."""
        return await self.base.request(
            "SYNO.DownloadStation.Task",
            "resume",
            version=1,
            params={"id": task_id},
            http_method="POST",
        )

    async def delete_task(self, task_id: str, force_complete: bool = False) -> dict[str, Any]:
        """Удаляет задачу из списка Download Station."""
        return await self.base.request(
            "SYNO.DownloadStation.Task",
            "delete",
            version=1,
            params={"id": task_id, "force_complete": force_complete},
            http_method="POST",
        )
