"""Фасадный SDK-клиент Synology DSM для встраивания в сторонние приложения."""

from pathlib import Path
from types import TracebackType
from typing import Optional, Type

import httpx

from syno_cli.client.base import BaseSynoClient
from syno_cli.client.core import SynoCoreClient
from syno_cli.client.docker import SynoDockerClient
from syno_cli.client.download_station import SynoDownloadStationClient
from syno_cli.client.file_station import SynoFileStationClient
from syno_cli.client.vmm import SynoVmmClient
from syno_cli.config import SynoSettings


class SynoDSM:
    """Высокоуровневый фасадный клиент для интеграции с Synology DSM в Python.

    Предоставляет централизованный доступ ко всем модулям API и поддерживает
    асинхронный контекстный менеджер (`async with`).

    Example:
        ```python
        from syno_cli import SynoDSM

        async with SynoDSM(host="192.168.1.50", user="admin", password="password") as nas:
            # Получить статус
            status = await nas.core.get_system_info()
            # Список файлов
            files = await nas.files.list_dir("/docker")
            # Список контейнеров
            containers = await nas.docker.list_containers()
        ```
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        secure: bool = False,
        otp_code: Optional[str] = None,
        session_file: Optional[Path] = None,
        session_backend: str = "file",
        settings: Optional[SynoSettings] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        """Инициализирует фасадный клиент DSM.

        Параметры могут быть переданы явно либо загружены из существующего объекта SynoSettings.
        """
        if settings is not None:
            cfg = settings
        else:
            cfg_params: dict = {"secure": secure, "session_backend": session_backend}
            if host is not None:
                cfg_params["host"] = host
            if port is not None:
                cfg_params["port"] = port
            if user is not None:
                cfg_params["user"] = user
            if password is not None:
                cfg_params["password"] = password
            if otp_code is not None:
                cfg_params["otp_code"] = otp_code
            if session_file is not None:
                cfg_params["session_file"] = session_file

            cfg = SynoSettings(**cfg_params)
            cfg.load_secured_credentials()

        self.base: BaseSynoClient = BaseSynoClient(
            config=cfg,
            transport=transport,
            session_backend=session_backend,
        )

        # Фасадные подсистемы
        self.core = SynoCoreClient(self.base)
        self.files = SynoFileStationClient(self.base)
        self.docker = SynoDockerClient(self.base)
        self.downloads = SynoDownloadStationClient(self.base)
        self.vmm = SynoVmmClient(self.base)

    async def __aenter__(self) -> "SynoDSM":
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        await self.close()

    async def close(self) -> None:
        """Закрывает HTTP-соединение базового клиента."""
        await self.base.close()