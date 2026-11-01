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

from abc import ABC, abstractmethod
import base64
import getpass
import json
import logging
from pathlib import Path
import platform
import subprocess
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import keyring
from keyring.errors import KeyringError

logger = logging.getLogger(__name__)

_STATIC_SALT: bytes = b"syno-dsm-webapi-node-unique-salt-v1"
KEYRING_SERVICE_NAME: str = "syno_cli"
KEYRING_SESSION_KEY: str = "dsm_session"


def get_machine_fingerprint() -> bytes:
    """Формирует уникальный аппаратно-программный отпечаток текущей машины и пользователя.

    Returns:
        bytes: Байтовая строка уникального отпечатка вида `b"<machine_id>:<username>:<system>"`.
    """
    system = platform.system()
    machine_id = ""

    if system == "Linux":
        for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            p = Path(path)
            if p.exists():
                try:
                    machine_id = p.read_text(encoding="utf-8").strip()
                    if machine_id:
                        break
                except Exception:
                    pass
    elif system == "Darwin":
        try:
            out = subprocess.check_output(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                stderr=subprocess.DEVNULL,
            ).decode("utf-8")
            for line in out.splitlines():
                if "IOPlatformUUID" in line:
                    machine_id = line.split("=")[-1].replace('"', "").strip()
                    break
        except Exception:
            pass

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
        length=32,
        salt=_STATIC_SALT,
        iterations=100_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(get_machine_fingerprint()))
    return Fernet(key)


class BaseSessionStorage(ABC):
    """Абстрактный базовый класс для всех бэкендов хранения сессии Synology DSM."""

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
    """Файловое хранилище сессии с шифрованием Fernet и привязкой к хосту.

    Сохраняет JSON-представление сессии (`sid` и `api_map`) в зашифрованный файл
    с правами доступа `0600` (только для владельца).

    Attributes:
        file_path: Путь к файлу зашифрованного кэша сессии.
    """

    def __init__(self, file_path: Path) -> None:
        """Инициализирует файловое хранилище сессии.

        Args:
            file_path: Путь к файлу хранения сессии.
        """
        self.file_path: Path = file_path

    def load(self) -> dict[str, Any]:
        """Читает и расшифровывает данные сессии с диска.

        Если файл был сохранен в старом открытом JSON-формате, корректно читает его.
        При несовпадении ключа машины (файл скопирован с другого ПК) очищает кэш.

        Returns:
            dict[str, Any]: Словарь расшифрованной сессии или пустой словарь.
        """
        if not self.file_path.exists():
            return {}
        try:
            content = self.file_path.read_text(encoding="utf-8").strip()
            if not content:
                return {}
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
            self.file_path.chmod(0o600)
        except Exception as exc:
            logger.warning("Не удалось сохранить зашифрованный файл сессии: %s", exc)

    def clear(self) -> None:
        """Удаляет файл кэша сессии с диска."""
        if self.file_path.exists():
            try:
                self.file_path.unlink()
            except Exception:
                pass


class KeyringStorage(BaseSessionStorage):
    """Хранилище сессии в системной связке ключей ОС (`keyring`)."""

    def load(self) -> dict[str, Any]:
        """Извлекает JSON с данными сессии из системного хранилища паролей.

        Returns:
            dict[str, Any]: Словарь сессии или пустой словарь.
        """
        try:
            data = keyring.get_password(KEYRING_SERVICE_NAME, KEYRING_SESSION_KEY)
            if data:
                parsed = json.loads(data)
                if isinstance(parsed, dict):
                    return dict(parsed)
        except Exception as exc:
            logger.debug("Не удалось загрузить сессию из системного keyring: %s", exc)
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
            keyring.set_password(KEYRING_SERVICE_NAME, KEYRING_SESSION_KEY, raw_json)
        except Exception as exc:
            logger.warning("Ошибка записи сессии в системный keyring: %s", exc)
            raise KeyringError(f"Не удалось сохранить сессию в keyring: {exc}") from exc

    def clear(self) -> None:
        """Удаляет запись сессии из системной связки ключей."""
        try:
            keyring.delete_password(KEYRING_SERVICE_NAME, KEYRING_SESSION_KEY)
        except Exception:
            pass


def get_session_storage(backend: str, file_path: Path) -> BaseSessionStorage:
    """Фабричная функция выбора и инициализации бэкенда хранения сессии.

    Args:
        backend: Выбранный режим хранения (`'auto'`, `'file'` или `'keyring'`).
        file_path: Путь к файлу кэша для файлового бэкенда.

    Returns:
        BaseSessionStorage: Экземпляр `KeyringStorage` или `EncryptedFileStorage`.
    """
    backend_norm = backend.strip().lower()
    if backend_norm == "keyring":
        return KeyringStorage()
    if backend_norm == "file":
        return EncryptedFileStorage(file_path)

    try:
        kr = keyring.get_keyring()
        kr_name = kr.__class__.__name__.lower()
        if "fail" not in kr_name and "null" not in kr_name and "chainer" not in kr_name:
            return KeyringStorage()
    except Exception:
        pass

    return EncryptedFileStorage(file_path)
