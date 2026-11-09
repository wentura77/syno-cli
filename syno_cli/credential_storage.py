"""Модуль безопасного хранения логина и пароля пользователя Synology DSM.

Позволяет отказаться от хранения пароля открытым текстом в `.env`.
Поддерживает хранение:
1. В зашифрованном файле `credentials.enc` внутри пользовательской директории конфигурации
   (`platformdirs.user_config_dir`) с привязкой к аппаратному отпечатку ПК (Fernet AES-128-CBC).
2. В системной связке ключей ОС (`keyring`).
"""

import json
import logging
from pathlib import Path
from typing import Final, Optional

import keyring

from syno_cli.constants import SECURE_FILE_PERMISSIONS
from syno_cli.session_storage import get_host_cipher, is_keyring_available

logger = logging.getLogger(__name__)

KEYRING_AUTH_SERVICE: Final[str] = "syno_cli_auth"
KEYRING_AUTH_ACCOUNT: Final[str] = "dsm_credentials"


def save_credentials_to_file(username: str, password: str, file_path: Path) -> None:
    """Шифрует логин и пароль ключом текущей машины и сохраняет в файл конфигурации.

    Args:
        username: Имя пользователя Synology DSM.
        password: Пароль пользователя DSM.
        file_path: Путь к зашифрованному файлу учетных данных.
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    cipher = get_host_cipher()
    payload = json.dumps({"user": username, "password": password})
    encrypted = cipher.encrypt(payload.encode("utf-8")).decode("utf-8")
    file_path.write_text(encrypted, encoding="utf-8")
    file_path.chmod(SECURE_FILE_PERMISSIONS)


def load_credentials_from_file(file_path: Path) -> Optional[tuple[str, str]]:
    """Читает и расшифровывает логин и пароль из локального зашифрованного файла.

    Args:
        file_path: Путь к зашифрованному файлу учетных данных.

    Returns:
        Optional[tuple[str, str]]: Кортеж `(username, password)` или `None`.
    """
    if not file_path.exists():
        return None
    try:
        content = file_path.read_text(encoding="utf-8").strip()
        if not content:
            return None
        decrypted = get_host_cipher().decrypt(content.encode("utf-8")).decode("utf-8")
        parsed = json.loads(decrypted)
        if isinstance(parsed, dict):
            return str(parsed.get("user", "")), str(parsed.get("password", ""))
    except Exception as exc:
        logger.debug("Не удалось расшифровать файл учетных данных %s: %s", file_path, exc)
    return None


def save_credentials_to_keyring(username: str, password: str) -> None:
    """Сохраняет логин и пароль DSM в системную связку ключей ОС (`keyring`).

    Args:
        username: Имя пользователя DSM.
        password: Пароль пользователя DSM.
    """
    payload = json.dumps({"user": username, "password": password})
    keyring.set_password(KEYRING_AUTH_SERVICE, KEYRING_AUTH_ACCOUNT, payload)


def load_credentials_from_keyring() -> Optional[tuple[str, str]]:
    """Извлекает логин и пароль DSM из системной связки ключей ОС (`keyring`).

    Returns:
        Optional[tuple[str, str]]: Кортеж `(username, password)` или `None`.
    """
    try:
        raw = keyring.get_password(KEYRING_AUTH_SERVICE, KEYRING_AUTH_ACCOUNT)
        if not raw:
            return None
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return str(parsed.get("user", "")), str(parsed.get("password", ""))
    except Exception as exc:
        logger.debug("Ошибка чтения учетных данных из keyring: %s", exc)
    return None


def clear_stored_credentials(file_path: Path) -> None:
    """Удаляет сохраненные учетные данные как из системного `keyring`, так и из файла на диске.

    Args:
        file_path: Путь к зашифрованному файлу учетных данных для удаления.
    """
    try:
        keyring.delete_password(KEYRING_AUTH_SERVICE, KEYRING_AUTH_ACCOUNT)
    except Exception:
        pass

    try:
        file_path.unlink(missing_ok=True)
    except OSError:
        pass

def get_credentials(backend: str, file_path: Path) -> Optional[tuple[str, str]]:
    """Извлекает сохраненные учетные данные из выбранного защищенного бэкенда.

    Args:
        backend: Имя бэкенда хранения (`'auto'`, `'file'` или `'keyring'`).
        file_path: Путь к зашифрованному файлу учетных данных.

    Returns:
        Optional[tuple[str, str]]: Кортеж `(username, password)` или `None`.
    """
    mode = backend.strip().lower()
    if mode == "keyring":
        return load_credentials_from_keyring()
    if mode == "file":
        return load_credentials_from_file(file_path)

    if is_keyring_available():
        try:
            creds = load_credentials_from_keyring()
            if creds and creds[1]:
                return creds
        except Exception as exc:
            logger.debug("Сбой keyring в режиме auto, переключение на файл: %s", exc)

    return load_credentials_from_file(file_path)
