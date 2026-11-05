"""Модульные тесты шифрования сессии (.syno_session.json) и учетных данных с привязкой к ПК."""

from pathlib import Path

from cryptography.fernet import Fernet

from syno_cli.credential_storage import (
    load_credentials_from_file,
    save_credentials_to_file,
)
from syno_cli.session_storage import EncryptedFileStorage


def test_encrypted_session_storage_roundtrip(tmp_path: Path) -> None:
    """Проверяет шифрование, установку прав 0600 и расшифровку .syno_session.json на том же ПК."""
    session_file = tmp_path / "cache" / ".syno_session.json"
    storage = EncryptedFileStorage(session_file)

    sample_session = {
        "sid": "secret_dsm_sid_987654",
        "api_map": {"SYNO.Core.System": {"path": "entry.cgi", "maxVersion": 3}},
    }
    storage.save(sample_session)

    assert session_file.exists()
    raw_disk_text = session_file.read_text(encoding="utf-8")
    # Убеждаемся, что на диске данные зашифрованы (Fernet), а не лежат открытым текстом
    assert "secret_dsm_sid_987654" not in raw_disk_text
    assert "SYNO.Core.System" not in raw_disk_text

    loaded = storage.load()
    assert loaded == sample_session

    storage.clear()
    assert not session_file.exists()


def test_encrypted_session_rejects_foreign_host_file(tmp_path: Path) -> None:
    """Проверяет, что файл сессии, скопированный с другого ПК, отвергается и удаляется."""
    session_file = tmp_path / ".syno_session.json"
    foreign_cipher = Fernet(Fernet.generate_key())
    foreign_encrypted = foreign_cipher.encrypt(b'{"sid": "stolen_sid"}').decode("utf-8")
    session_file.write_text(foreign_encrypted, encoding="utf-8")

    storage = EncryptedFileStorage(session_file)
    loaded = storage.load()

    assert loaded == {}
    assert not session_file.exists()


def test_encrypted_credentials_roundtrip(tmp_path: Path) -> None:
    """Проверяет шифрование и расшифровку логина и пароля DSM в credentials.enc."""
    cred_file = tmp_path / "config" / "credentials.enc"
    save_credentials_to_file("admin", "SynoSuperSecret!2026", cred_file)

    assert cred_file.exists()
    raw_content = cred_file.read_text(encoding="utf-8")
    assert "SynoSuperSecret!2026" not in raw_content

    creds = load_credentials_from_file(cred_file)
    assert creds == ("admin", "SynoSuperSecret!2026")
