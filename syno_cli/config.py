"""Модуль конфигурации подключения к Synology NAS с поддержкой platformdirs и шифрования."""

from pathlib import Path
from typing import Literal, Optional
from platformdirs import user_cache_dir, user_config_dir
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME: str = "syno-cli"

USER_CONFIG_DIR: Path = Path(user_config_dir(APP_NAME))
USER_CONFIG_FILE: Path = USER_CONFIG_DIR / "config.env"
DEFAULT_CREDENTIALS_FILE: Path = USER_CONFIG_DIR / "credentials.enc"
LOCAL_ENV_FILE: Path = Path(".env")

USER_CACHE_DIR: Path = Path(user_cache_dir(APP_NAME))
DEFAULT_SESSION_FILE: Path = USER_CACHE_DIR / ".syno_session.json"


class SynoSettings(BaseSettings):
    """Конфигурация подключения и безопасности для Synology DSM Web API.

    Загружает параметры в следующем порядке приоритета:
    1. Переменные окружения (`SYNO_*`).
    2. Локальный файл `.env` в текущей папке.
    3. Пользовательский конфиг в `user_config_dir("syno-cli") / "config.env"`
       (например, `~/.config/syno-cli/config.env`).
    4. Зашифрованное хранилище учетных данных (`keyring` или `credentials.enc`).

    Attributes:
        host: IP-адрес или доменное имя Synology NAS.
        port: Порт DSM Web API (5000 для HTTP, 5001 для HTTPS).
        user: Имя пользователя DSM.
        password: Пароль пользователя DSM.
        secure: Использовать ли HTTPS соединение.
        otp_code: Одноразовый код 2FA (при необходимости).
        session_backend: Бэкенд хранения сессии и пароля (`'auto'`, `'file'` или `'keyring'`).
        session_file: Путь к зашифрованному файлу сессии в пользовательском кэше (`user_cache_dir`).
        credentials_file: Путь к зашифрованному файлу логина и пароля в `user_config_dir`.
    """

    host: str = "192.168.1.100"
    port: int = 5000
    user: str = ""
    password: str = ""
    secure: bool = False
    otp_code: Optional[str] = None

    session_backend: Literal["auto", "keyring", "file"] = "file"
    session_file: Path = DEFAULT_SESSION_FILE
    credentials_file: Path = DEFAULT_CREDENTIALS_FILE

    model_config = SettingsConfigDict(
        env_prefix="SYNO_",
        env_file=(USER_CONFIG_FILE, LOCAL_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def base_url(self) -> str:
        """Формирует базовый URL для обращения к DSM Web API.

        Returns:
            str: Строка вида `http(s)://<host>:<port>`.
        """
        scheme = "https" if self.secure else "http"
        return f"{scheme}://{self.host}:{self.port}"

    def load_secured_credentials(self) -> None:
        """Подгружает расшифрованные логин и пароль из хранилища, если они не заданы в `.env`."""
        if not self.password:
            from syno_cli.credential_storage import get_credentials

            creds = get_credentials(self.session_backend, Path(self.credentials_file))
            if creds:
                if not self.user and creds[0]:
                    self.user = creds[0]
                if creds[1]:
                    self.password = creds[1]

        if not self.user:
            self.user = "admin"
        if not self.password:
            self.password = "password"


settings = SynoSettings()
settings.load_secured_credentials()
