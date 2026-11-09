"""Фасадный SDK-клиент Synology DSM для встраивания в сторонние приложения и CLI."""

from pathlib import Path
from types import TracebackType
from typing import Any, Optional, Type

import httpx

from syno_cli.client.base import BaseSynoClient
from syno_cli.client.core import SynoCoreClient
from syno_cli.client.docker import SynoDockerClient
from syno_cli.client.download_station import SynoDownloadStationClient
from syno_cli.client.file_station import SynoFileStationClient
from syno_cli.client.logs import SynoLogsClient
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
        secure: Optional[bool] = None,
        otp_code: Optional[str] = None,
        session_file: Optional[Path] = None,
        session_backend: Optional[str] = None,
        settings: Optional[SynoSettings] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        """Инициализирует фасадный клиент DSM.

        Args:
            host: IP-адрес или доменное имя Synology NAS.
            port: Порт DSM Web API (по умолчанию 5001).
            user: Имя пользователя DSM.
            password: Пароль пользователя DSM.
            secure: Использовать ли HTTPS (по умолчанию берется из настроек).
            otp_code: Одноразовый код 2FA.
            session_file: Путь к файлу кэша сессии.
            session_backend: Бэкенд хранения сессии (`'file'`, `'keyring'`, `'auto'`).
            settings: Готовый экземпляр `SynoSettings`.
            transport: Кастомный HTTP-транспорт для тестирования.
        """
        if settings is not None:
            cfg = settings
        else:
            overrides: dict[str, Any] = {
                k: v
                for k, v in {
                    "host": host,
                    "port": port,
                    "user": user,
                    "password": password,
                    "secure": secure,
                    "otp_code": otp_code,
                    "session_file": session_file,
                    "session_backend": session_backend,
                }.items()
                if v is not None
            }
            cfg = SynoSettings(**overrides)
            cfg.load_secured_credentials()

        self.base = BaseSynoClient(
            config=cfg,
            transport=transport,
            session_backend=session_backend,
        )

        self.core = SynoCoreClient(self.base)
        self.files = SynoFileStationClient(self.base)
        self.docker = SynoDockerClient(self.base)
        self.downloads = SynoDownloadStationClient(self.base)
        self.logs = SynoLogsClient(self.base)
        self.vmm = SynoVmmClient(self.base)

    async def __aenter__(self) -> "SynoDSM":
        """Вход в асинхронный контекстный менеджер.

        Returns:
            SynoDSM: Текущий экземпляр фасада.
        """
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """Выход из асинхронного контекстного менеджера с закрытием сокетов."""
        await self.close()

    async def close(self) -> None:
        """Закрывает HTTP-соединение базового клиента."""
        await self.base.close()
