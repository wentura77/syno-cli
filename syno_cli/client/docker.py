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
        port_bindings = []
        for p in ports or []:
            if ":" in p:
                host_p, cont_p = p.split(":", 1)
                port_bindings.append(
                    {
                        "host_port": str(host_p),
                        "container_port": str(cont_p),
                        "type": "tcp",
                    }
                )

        volume_bindings = []
        for v in volumes or []:
            if ":" in v:
                host_v, mount_v = v.split(":", 1)
                volume_bindings.append(
                    {
                        "host_volume_file": host_v,
                        "mount_point": mount_v,
                        "type": "rw",
                    }
                )

        env_list = []
        for e in env_vars or []:
            if "=" in e:
                k, val = e.split("=", 1)
                env_list.append({"key": k, "value": val})

        profile = {
            "name": name,
            "image": image,
            "port_bindings": port_bindings,
            "volume_bindings": volume_bindings,
            "env_variables": env_list,
        }

        created = await self.base.request(
            "SYNO.Docker.Container",
            "create",
            version=1,
            params={"profile": profile},
            http_method="POST",
        )
        if auto_start:
            await self.start_container(name)
        return created

    async def list_projects(self) -> list[dict[str, Any]]:
        """
        Возвращает список проектов Docker Compose в Container Manager (DSM 7.2+).

        Returns:
            list[dict[str, Any]]: Список Compose-проектов.
        """
        data = await self.base.request("SYNO.Docker.Project", "list", version=1)
        if isinstance(data, dict) and "projects" in data:
            return list(data["projects"])
        if isinstance(data, dict):
            return list(data.values())
        return []

    async def start_project(self, project_id: str) -> dict[str, Any]:
        """
        Запускает проект Docker Compose по его идентификатору или имени.

        Args:
            project_id (str): Идентификатор или имя проекта.

        Returns:
            dict[str, Any]: Ответ API.
        """
        return await self.base.request(
            "SYNO.Docker.Project",
            "start",
            version=1,
            params={"id": project_id},
            http_method="POST",
        )

    async def stop_project(self, project_id: str) -> dict[str, Any]:
        """
        Останавливает проект Docker Compose по его идентификатору или имени.

        Args:
            project_id (str): Идентификатор или имя проекта.

        Returns:
            dict[str, Any]: Ответ API.
        """
        return await self.base.request(
            "SYNO.Docker.Project",
            "stop",
            version=1,
            params={"id": project_id},
            http_method="POST",
        )
