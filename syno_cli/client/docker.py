"""Клиент управления пакетом Container Manager (Docker) через DSM Web API."""

from typing import Any, Optional

from syno_cli.client.base import BaseSynoClient


class SynoDockerClient:
    """
    Клиент для взаимодействия с интерфейсами `SYNO.Docker.*`.

    Обеспечивает управление контейнерами, локальными и удаленными образами,
    а также проектами Docker Compose (Container Manager в DSM 7.2+).
    """

    def __init__(self, base: BaseSynoClient) -> None:
        """
        Инициализирует Docker-клиент.

        Args:
            base (BaseSynoClient): Экземпляр базового клиента DSM.
        """
        self.base = base

    async def list_containers(self) -> list[dict[str, Any]]:
        """
        Возвращает список всех контейнеров и их текущее состояние.

        Returns:
            list[dict[str, Any]]: Список словарей с параметрами контейнеров.
        """
        data = await self.base.request(
            "SYNO.Docker.Container",
            "list",
            version=1,
            params={"limit": -1, "offset": 0},
        )
        return list(data.get("containers", []))

    async def start_container(self, name: str) -> dict[str, Any]:
        """
        Запускает остановленный контейнер по его имени.

        Args:
            name (str): Имя контейнера в Container Manager.

        Returns:
            dict[str, Any]: Результат запуска.
        """
        return await self.base.request(
            "SYNO.Docker.Container",
            "start",
            version=1,
            params={"name": name},
            http_method="POST",
        )

    async def stop_container(self, name: str) -> dict[str, Any]:
        """
        Останавливает работающий контейнер по его имени.

        Args:
            name (str): Имя контейнера.

        Returns:
            dict[str, Any]: Результат остановки.
        """
        return await self.base.request(
            "SYNO.Docker.Container",
            "stop",
            version=1,
            params={"name": name},
            http_method="POST",
        )

    async def restart_container(self, name: str) -> dict[str, Any]:
        """
        Перезапускает контейнер по его имени.

        Args:
            name (str): Имя контейнера.

        Returns:
            dict[str, Any]: Результат перезапуска.
        """
        return await self.base.request(
            "SYNO.Docker.Container",
            "restart",
            version=1,
            params={"name": name},
            http_method="POST",
        )

    async def list_images(self) -> list[dict[str, Any]]:
        """
        Возвращает список загруженных Docker-образов на NAS.

        Returns:
            list[dict[str, Any]]: Перечень образов с тегами и размерами.
        """
        data = await self.base.request(
            "SYNO.Docker.Image",
            "list",
            version=1,
            params={"limit": -1, "offset": 0},
        )
        return list(data.get("images", []))

    async def pull_image(self, repository: str, tag: str = "latest") -> dict[str, Any]:
        """
        Инициирует скачивание (pull) образа из Docker Registry на Synology NAS.

        Args:
            repository (str): Имя репозитория образа (например, `nginx` или `redis`).
            tag (str): Тег образа (по умолчанию `latest`).

        Returns:
            dict[str, Any]: Информация о запущенной задаче загрузки образа.
        """
        return await self.base.request(
            "SYNO.Docker.Image",
            "pull_start",
            version=1,
            params={"repository": repository, "tag": tag},
            http_method="POST",
        )

    async def delete_container(self, name: str, force: bool = False) -> dict[str, Any]:
        """Удаляет контейнер с Synology NAS."""
        clean_name = name.lstrip("/")
        params = {
            "name": f'"{clean_name}"',
            "force": "true" if force else "false",
        }
        data = await self.base.request(
            "SYNO.Docker.Container",
            "delete",
            version=1,
            params=params,
            http_method="POST",
        )
        return data if isinstance(data, dict) else {}

    async def get_container_stats(self, name: Optional[str] = None) -> list[dict[str, Any]]:
        """Запрашивает статистику утилизации ресурсов (CPU, RAM, сеть, диск) контейнерами."""
        params: dict[str, Any] = {}
        if name:
            params["name"] = name
        data = await self.base.request(
            "SYNO.Docker.Container.Resource",
            "get",
            version=1,
            params=params,
        )
        stats = data.get("resources", data.get("containers", []))
        if isinstance(stats, dict) and "cpu" in stats:
            return [{"name": name or "unknown", **stats}]
        return list(stats) if isinstance(stats, list) else []

    async def get_container_logs(self, name: str, tail: int = 100) -> list[str]:
        """Возвращает последние строки журнала событий (логов) контейнера.

        Использует SYNO.Docker.Container.Log с обязательными параметрами sort_dir и name.
        """
        clean_name = name.lstrip("/")
        params = {
            "name": f'"{clean_name}"',
            "limit": tail,
            "offset": 0,
            "sort_dir": '"DESC"',
        }

        data = await self.base.request(
            "SYNO.Docker.Container.Log",
            "get",
            version=1,
            params=params,
            http_method="POST",
        )
        logs = data.get("logs", [])
        if not isinstance(logs, list):
            return []

        res: list[str] = []
        for item in reversed(logs):
            if isinstance(item, dict):
                text = str(item.get("text") or item.get("log") or item.get("msg") or "").strip()
                stream_type = str(item.get("stream") or "stdout")
                res.append(f"[{stream_type}] {text}")
            else:
                res.append(str(item).strip())
        return res

    async def create_container(
        self,
        name: str,
        image: str,
        ports: Optional[list[str]] = None,
        volumes: Optional[list[str]] = None,
        env_vars: Optional[list[str]] = None,
        auto_start: bool = True,
    ) -> dict[str, Any]:
        """
        Создает и опционально запускает новый Docker-контейнер на Synology NAS.

        Args:
            name (str): Имя создаваемого контейнера.
            image (str): Образ с тегом (например, `nginx:latest`).
            ports (Optional[list[str]]): Список проброса портов вида `["8080:80"]`.
            volumes (Optional[list[str]]): Список монтируемых папок вида `["/docker/app:/data"]`.
            env_vars (Optional[list[str]]): Список переменных окружения вида `["TZ=Europe/Berlin"]`.
            auto_start (bool): Запустить ли контейнер сразу после создания.

        Returns:
            dict[str, Any]: Ответ DSM API с деталями созданного контейнера.
        """
        container_config: dict[str, Any] = {
            "name": name,
            "image": image,
            "is_auto_start": auto_start,
        }

        if ports:
            port_bindings = []
            for p in ports:
                parts = p.split(":")
                if len(parts) == 2:
                    port_bindings.append(
                        {
                            "host_port": int(parts[0]),
                            "container_port": int(parts[1]),
                            "protocol": "tcp",
                        }
                    )
            container_config["port_bindings"] = port_bindings

        if volumes:
            binds = []
            for v in volumes:
                parts = v.split(":")
                if len(parts) == 2:
                    binds.append(
                        {
                            "host_volume_file": parts[0],
                            "mount_point": parts[1],
                            "type": "bind",
                        }
                    )
            container_config["volume_bindings"] = binds

        if env_vars:
            container_config["env_variables"] = [
                {"key": e.split("=", 1)[0], "value": e.split("=", 1)[1] if "=" in e else ""}
                for e in env_vars
            ]

        data = await self.base.request(
            "SYNO.Docker.Container",
            "create",
            version=1,
            params=container_config,
            http_method="POST",
        )
        return data if isinstance(data, dict) else {}

    async def list_projects(self) -> list[dict[str, Any]]:
        """Получает список всех проектов Docker Compose."""
        data = await self.base.request(
            "SYNO.Docker.Project",
            "list",
            version=1,
            params={"limit": -1, "offset": 0},
        )
        return list(data.get("projects", []))

    async def build_or_start_project(
        self,
        name: str,
        compose_content: str,
        env_content: Optional[str] = None,
        share_path: Optional[str] = None,
    ) -> dict[str, Any]:
        """Создает или обновляет и запускает проект Docker Compose (up)."""
        params: dict[str, Any] = {
            "name": name,
            "content": compose_content,
        }
        if env_content:
            params["env_content"] = env_content
        if share_path:
            params["share_path"] = share_path

        data = await self.base.request(
            "SYNO.Docker.Project",
            "build",
            version=1,
            params=params,
            http_method="POST",
        )
        return data if isinstance(data, dict) else {}

    async def stop_project(self, name: str) -> dict[str, Any]:
        """Останавливает проект Docker Compose (down)."""
        data = await self.base.request(
            "SYNO.Docker.Project",
            "clean",
            version=1,
            params={"name": name},
            http_method="POST",
        )
        return data if isinstance(data, dict) else {}

    async def restart_project(self, name: str) -> dict[str, Any]:
        """Перезапускает проект Docker Compose."""
        data = await self.base.request(
            "SYNO.Docker.Project",
            "restart",
            version=1,
            params={"name": name},
            http_method="POST",
        )
        return data if isinstance(data, dict) else {}

    async def get_project_logs(self, name: str, tail: int = 100) -> list[str]:
        """Получает агрегированные логи проекта Docker Compose."""
        data = await self.base.request(
            "SYNO.Docker.Project",
            "get_log",
            version=1,
            params={"name": name, "limit": tail, "offset": 0},
        )
        logs = data.get("logs", [])
        if isinstance(logs, list):
            res: list[str] = []
            for item in logs:
                if isinstance(item, dict):
                    msg = str(item.get("log") or item.get("msg") or "").rstrip()
                    stream_type = str(item.get("stream") or "stdout")
                    res.append(f"[{stream_type}] {msg}")
                else:
                    res.append(str(item).rstrip())
            return res
        return []
