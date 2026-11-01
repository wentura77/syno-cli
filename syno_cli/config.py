"""Модуль конфигурации подключения к Synology NAS."""

from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class SynoSettings(BaseSettings):
    """
    Конфигурация подключения к Synology DSM Web API.

    Загружает параметры из переменных окружения или локального файла `.env`.

    Attributes:
        host (str): IP-адрес или доменное имя Synology NAS.
        port (int): Порт DSM Web API (5000 для HTTP, 5001 для HTTPS).
        user (str): Имя пользователя DSM.
        password (str): Пароль пользователя DSM.
        secure (bool): Использовать ли HTTPS соединение.
        otp_code (Optional[str]): Одноразовый код 2FA (при необходимости).
        session_file (Path): Путь к файлу кэширования сессионного токена (sid).
    """

    host: str = "192.168.1.100"
    port: int = 5000
    user: str = "admin"
    password: str = "password"
    secure: bool = False
    otp_code: Optional[str] = None
    session_file: Path = Path(".syno_session.json")

    model_config = SettingsConfigDict(
        env_prefix="SYNO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def base_url(self) -> str:
        """
        Формирует базовый URL для обращения к DSM Web API.

        Returns:
            str: Строка вида `http(s)://<host>:<port>`.
        """
        scheme = "https" if self.secure else "http"
        return f"{scheme}://{self.host}:{self.port}"


settings = SynoSettings()
