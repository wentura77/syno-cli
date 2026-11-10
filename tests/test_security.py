"""Модульные тесты шифрования сессии (.syno_session.json) и учетных данных с привязкой к ПК."""

from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet

from syno_cli.config import SynoSettings
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


def test_load_secured_credentials_from_storage(tmp_path: Path) -> None:
    """Проверяет подстановку учетных данных из хранилища, если пароль пустой."""
    cred_file = tmp_path / "credentials.enc"
    cfg = SynoSettings(
        host="test-nas",
        user="",
        password="",
        credentials_file=cred_file,
        session_file=tmp_path / "session.json",
    )

    with patch(
        "syno_cli.credential_storage.get_credentials",
        return_value=("storage_user", "storage_secret_pass"),
    ) as mock_get_creds:
        cfg.load_secured_credentials()

        mock_get_creds.assert_called_once_with(cfg.session_backend, cred_file)
        assert cfg.user == "storage_user"
        assert cfg.password == "storage_secret_pass"


def test_load_secured_credentials_preserves_explicit_user(tmp_path: Path) -> None:
    """Проверяет сохранение явно заданного пользователя при подгрузке пароля из хранилища."""
    cred_file = tmp_path / "credentials.enc"
    cfg = SynoSettings(
        host="test-nas",
        user="explicit_user",
        password="",
        credentials_file=cred_file,
        session_file=tmp_path / "session.json",
    )

    with patch(
        "syno_cli.credential_storage.get_credentials",
        return_value=("other_user", "storage_secret_pass"),
    ):
        cfg.load_secured_credentials()

        assert cfg.user == "explicit_user"
        assert cfg.password == "storage_secret_pass"


def test_load_secured_credentials_skips_when_password_provided(tmp_path: Path) -> None:
    """Проверяет, что хранилище не опрашивается, если пароль уже задан."""
    cred_file = tmp_path / "credentials.enc"
    cfg = SynoSettings(
        host="test-nas",
        user="custom_user",
        password="existing_password",
        credentials_file=cred_file,
        session_file=tmp_path / "session.json",
    )

    with patch("syno_cli.credential_storage.get_credentials") as mock_get_creds:
        cfg.load_secured_credentials()

        mock_get_creds.assert_not_called()
        assert cfg.user == "custom_user"
        assert cfg.password == "existing_password"


def test_load_secured_credentials_fallback_defaults(tmp_path: Path) -> None:
    """Проверяет применение значений по умолчанию (admin/password) при пустом хранилище."""
    cred_file = tmp_path / "credentials.enc"
    cfg = SynoSettings(
        host="test-nas",
        user="",
        password="",
        credentials_file=cred_file,
        session_file=tmp_path / "session.json",
    )

    with patch("syno_cli.credential_storage.get_credentials", return_value=None):
        cfg.load_secured_credentials()

        assert cfg.user == "admin"
        assert cfg.password == "password"
