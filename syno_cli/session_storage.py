"""Модуль безопасного хранения сессии DSM (sid и api_map) с привязкой к ID хоста или Keyring.

Предоставляет два защищенных бэкенда хранения сессионных данных Synology DSM:
1. `EncryptedFileStorage` — локальный файл в кэш-директории пользователя (`platformdirs.user_cache_dir`),
   зашифрованный симметричным алгоритмом Fernet (AES-128-CBC + HMAC-SHA256). Ключ шифрования
   динамически вычисляется на лету через `PBKDF2HMAC` (SHA-256, 100 000 итераций) на основе
   уникального идентификатора машины (`/etc/machine-id` в Linux или `IOPlatformUUID` в macOS)
   и имени текущего пользователя ОС. При копировании файла на другой компьютер расшифровать
   его невозможно.
2. `KeyringStorage` — системная связка ключей операционной системы (Secret Service / GNOME Keyring,
   macOS Keychain, Windows Credential Locker).
"""

import base64
import getpass
import json
import logging
import platform
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Final

import keyring
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from keyring.errors import KeyringError

from syno_cli.constants import (
    PBKDF2_ITERATIONS,
    PBKDF2_KEY_LENGTH,
    SECURE_FILE_PERMISSIONS,
)

logger = logging.getLogger(__name__)

_STATIC_SALT: Final[bytes] = b"syno-dsm-webapi-node-unique-salt-v1"
_LINUX_MACHINE_ID_PATHS: Final[tuple[str, ...]] = (
    "/etc/machine-id",
    "/var/lib/dbus/machine-id",
)
_INVALID_KEYRING_NAMES: Final[tuple[str, ...]] = ("fail", "null", "chainer")


def _read_linux_machine_id() -> str:
    """Читает уникальный идентификатор машины в ОС Linux.

    Returns:
        str: Содержимое machine-id или пустая строка.
    """
    for raw_path in _LINUX_MACHINE_ID_PATHS:
        path = Path(raw_path)
        if not path.exists():
            continue
        try:
            machine_id = path.read_text(encoding="utf-8").strip()
            if machine_id:
                return machine_id
        except OSError:
            continue
    return ""


def _read_darwin_platform_uuid() -> str:
    """Извлекает аппаратный IOPlatformUUID в macOS.

    Returns:
        str: Строка UUID или пустая строка.
    """
    try:
        output = subprocess.check_output(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            stderr=subprocess.DEVNULL,
        ).decode("utf-8")
    except (OSError, subprocess.SubprocessError):
        return ""

    for line in output.splitlines():
        if "IOPlatformUUID" in line:
            return line.split("=")[-1].replace('"', "").strip()
    return ""


def get_machine_fingerprint() -> bytes:
    """Формирует уникальный аппаратно-программный отпечаток текущей машины и пользователя.

    Returns:
        bytes: Байтовая строка уникального отпечатка вида `b"<machine_id>:<username>:<system>"`.
    """
    system = platform.system()
    machine_id = ""

    if system == "Linux":
        machine_id = _read_linux_machine_id()
    elif system == "Darwin":
        machine_id = _read_darwin_platform_uuid()

    if not machine_id:
        machine_id = f"{platform.node()}-{platform.machine()}"

    user = getpass.getuser()
    return f"{machine_id}:{user}:{system}".encode("utf-8")


def get_host_cipher() -> Fernet:
    """Генерирует экземпляр шифратора Fernet с ключом, привязанным к текущему компьютеру.

    Returns:
        Fernet: Инициализированный объект для шифрования и дешифрования.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=PBKDF2_KEY_LENGTH,
        salt=_STATIC_SALT,
        iterations=PBKDF2_ITERATIONS,
    )
    key = base64.urlsafe_b64encode(kdf.derive(get_machine_fingerprint()))
    return Fernet(key)


class BaseSessionStorage(ABC):
    """Абстрактный базовый класс бэкенда хранения сессии."""

    @abstractmethod
    def load(self) -> dict[str, Any]:
        """Загружает и возвращает словарь сессии (`sid` и `api_map`) из хранилища.

        Returns:
            dict[str, Any]: Словарь с данными сессии или пустой словарь.
        """

    @abstractmethod
    def save(self, session_data: dict[str, Any]) -> None:
        """Сохраняет переданный словарь сессии в защищенное хранилище.

        Args:
            session_data: Словарь с ключами `sid` и `api_map`.
        """

    @abstractmethod
    def clear(self) -> None:
        """Полностью удаляет сохраненные сессионные данные из хранилища."""


class EncryptedFileStorage(BaseSessionStorage):
    """Файловое хранилище сессии с шифрованием Fernet и привязкой к хосту."""

    def __init__(self, file_path: Path) -> None:
        """Инициализирует файловое хранилище сессии.

        Args:
            file_path: Путь к файлу хранения сессии.
        """
        self.file_path: Path = file_path

    def _decode_content(self, content: str) -> dict[str, Any]:
        """Расшифровывает или парсит содержимое файла сессии.

        Args:
            content: Необработанная строка из файла сессии.

        Returns:
            dict[str, Any]: Распарсенный словарь сессии.
        """
        cipher = get_host_cipher()
        try:
            decrypted = cipher.decrypt(content.encode("utf-8")).decode("utf-8")
            parsed = json.loads(decrypted)
            return dict(parsed) if isinstance(parsed, dict) else {}
        except InvalidToken:
            if content.startswith("{"):
                parsed_plain = json.loads(content)
                if isinstance(parsed_plain, dict):
                    return dict(parsed_plain)
            raise

    def load(self) -> dict[str, Any]:
        """Читает и расшифровывает данные сессии с диска.

        Returns:
            dict[str, Any]: Словарь расшифрованной сессии или пустой словарь.
        """
        if not self.file_path.exists():
            return {}

        try:
            content = self.file_path.read_text(encoding="utf-8").strip()
            if not content:
                return {}
            return self._decode_content(content)
        except InvalidToken:
            logger.warning("Не удалось расшифровать сессию (файл перенесен с другого ПК).")
            self.clear()
            return {}
        except Exception as exc:
            logger.debug("Ошибка чтения файла сессии %s: %s", self.file_path, exc)
            self.clear()
            return {}

    def save(self, session_data: dict[str, Any]) -> None:
        """Шифрует данные сессии ключом текущей машины и записывает в файл с правами 0600.

        Args:
            session_data: Словарь с данными сессии (`sid`, `api_map`).
        """
        if not session_data:
            return
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            cipher = get_host_cipher()
            raw_json = json.dumps(session_data, indent=2)
            encrypted = cipher.encrypt(raw_json.encode("utf-8")).decode("utf-8")
            self.file_path.write_text(encrypted, encoding="utf-8")
            self.file_path.chmod(SECURE_FILE_PERMISSIONS)
        except Exception as exc:
            logger.warning("Не удалось сохранить зашифрованный файл сессии: %s", exc)

    def clear(self) -> None:
        """Удаляет файл кэша сессии с диска."""
        try:
            self.file_path.unlink(missing_ok=True)
        except OSError:
            pass


class KeyringStorage(BaseSessionStorage):
    """Хранилище сессии в системной связке ключей ОС."""

    def __init__(self, service_name: str = "syno_cli", session_key: str = "dsm_session") -> None:
        """Инициализирует хранилище в системном keyring.

        Args:
            service_name: Имя сервиса в связке ключей.
            session_key: Ключ записи сессии.
        """
        self.service_name = service_name
        self.session_key = session_key

    def load(self) -> dict[str, Any]:
        """Извлекает JSON с данными сессии из системного хранилища паролей.

        Returns:
            dict[str, Any]: Словарь сессии или пустой словарь.
        """
        try:
            data = keyring.get_password(self.service_name, self.session_key)
            if not data:
                return {}
            parsed = json.loads(data)
            return dict(parsed) if isinstance(parsed, dict) else {}
        except Exception as exc:
            logger.debug("Не удалось загрузить сессию из keyring: %s", exc)
            return {}

    def save(self, session_data: dict[str, Any]) -> None:
        """Сохраняет данные сессии в системную связку ключей.

        Args:
            session_data: Словарь с данными сессии.

        Raises:
            KeyringError: Если системная служба ключей недоступна.
        """
        if not session_data:
            return
        try:
            raw_json = json.dumps(session_data)
            keyring.set_password(self.service_name, self.session_key, raw_json)
        except Exception as exc:
            logger.warning("Ошибка записи сессии в системный keyring: %s", exc)
            raise KeyringError(f"Не удалось сохранить сессию в keyring: {exc}") from exc

    def clear(self) -> None:
        """Удаляет запись сессии из системной связки ключей."""
        try:
            keyring.delete_password(self.service_name, self.session_key)
        except Exception:
            pass


def is_keyring_available() -> bool:
    """Проверяет наличие рабочего системного бэкенда keyring в ОС.

    Returns:
        bool: True, если системная связка ключей активна.
    """
    try:
        kr_name = keyring.get_keyring().__class__.__name__.lower()
        return not any(invalid in kr_name for invalid in _INVALID_KEYRING_NAMES)
    except Exception:
        return False


def get_session_storage(
    backend: str,
    file_path: Path,
    service_name: str = "syno_cli",
) -> BaseSessionStorage:
    """Фабричная функция выбора и инициализации бэкенда хранения сессии.

    Args:
        backend: Выбранный режим хранения (`'auto'`, `'file'` или `'keyring'`).
        file_path: Путь к файлу кэша для файлового бэкенда.
        service_name: Имя сервиса для системной связки ключей.

    Returns:
        BaseSessionStorage: Экземпляр `KeyringStorage` или `EncryptedFileStorage`.
    """
    backend_norm = backend.strip().lower()
    if backend_norm == "keyring":
        return KeyringStorage(service_name=service_name)
    if backend_norm == "file":
        return EncryptedFileStorage(file_path)

    if is_keyring_available():
        return KeyringStorage(service_name=service_name)
    return EncryptedFileStorage(file_path)
