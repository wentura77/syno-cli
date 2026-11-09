"""Тесты фолбэка хранилищ учетных данных и CLI-команд управления аутентификацией."""

from pathlib import Path
from unittest.mock import patch

from keyring.errors import KeyringError
from typer.testing import CliRunner

from syno_cli.commands.main import app
from syno_cli.constants import ExitCode
from syno_cli.credential_storage import (
    get_credentials,
    load_credentials_from_file,
    save_credentials_to_file,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# 1. Тестирование Keyring Fallback на EncryptedFileStorage
# ---------------------------------------------------------------------------


def test_keyring_fallback_on_headless_environment(tmp_path: Path) -> None:
    """Проверяет переход на EncryptedFileStorage, если keyring недоступен в системе."""
    cred_file = tmp_path / "credentials.enc"
    save_credentials_to_file("backup_user", "SecurePass2026!", cred_file)

    # Эмулируем окружение без SecretService / D-Bus (is_keyring_available -> False)
    with patch("syno_cli.credential_storage.is_keyring_available", return_value=False):
        creds = get_credentials(backend="auto", file_path=cred_file)
        assert creds is not None
        assert creds == ("backup_user", "SecurePass2026!")


def test_keyring_fallback_on_exception(tmp_path: Path) -> None:
    """Проверяет фолбэк на локальный файл при возникновении KeyringError."""
    cred_file = tmp_path / "credentials.enc"
    save_credentials_to_file("operator", "OpSecret!789", cred_file)

    with (
        patch("syno_cli.credential_storage.is_keyring_available", return_value=True),
        patch(
            "syno_cli.credential_storage.load_credentials_from_keyring",
            side_effect=KeyringError("D-Bus service not responding"),
        ),
    ):
        creds = get_credentials(backend="auto", file_path=cred_file)
        assert creds == ("operator", "OpSecret!789")


def test_keyring_fallback_when_empty_record(tmp_path: Path) -> None:
    """Проверяет фолбэк на файл, если запись в keyring пуста или пароль отсутствует."""
    cred_file = tmp_path / "credentials.enc"
    save_credentials_to_file("admin_local", "LocalSecret!123", cred_file)

    with (
        patch("syno_cli.credential_storage.is_keyring_available", return_value=True),
        patch("syno_cli.credential_storage.load_credentials_from_keyring", return_value=None),
    ):
        creds = get_credentials(backend="auto", file_path=cred_file)
        assert creds == ("admin_local", "LocalSecret!123")


# ---------------------------------------------------------------------------
# 2. Тестирование CLI-команд syno auth (store, status, clear)
# ---------------------------------------------------------------------------


def test_cli_auth_store_file_backend(tmp_path: Path) -> None:
    """Проверяет команду 'syno auth store --backend file' и создание зашифрованного файла."""
    cred_file = tmp_path / "cli_creds.enc"

    with patch("syno_cli.commands.auth_cmd.settings") as mock_settings:
        mock_settings.credentials_file = cred_file

        result = runner.invoke(
            app,
            [
                "auth",
                "store",
                "--user",
                "syno_admin",
                "--password",
                "CmdPassword!2026",
                "--backend",
                "file",
            ],
        )

        assert result.exit_code == ExitCode.SUCCESS
        assert "Учетные данные зашифрованы" in result.stdout
        assert cred_file.exists()

        # Проверка расшифровки сохраненного файла
        loaded = load_credentials_from_file(cred_file)
        assert loaded == ("syno_admin", "CmdPassword!2026")


def test_cli_auth_status_display(tmp_path: Path) -> None:
    """Проверяет вывод путей конфигурации и кэша в команде 'syno auth status'."""
    cred_file = tmp_path / "status_creds.enc"
    session_file = tmp_path / "session.json"
    save_credentials_to_file("status_user", "StatusPass!1", cred_file)

    with patch("syno_cli.commands.auth_cmd.settings") as mock_settings:
        mock_settings.base_url = "https://192.168.1.50:5001"
        mock_settings.user = "status_user"
        mock_settings.session_backend = "file"
        mock_settings.credentials_file = cred_file
        mock_settings.session_file = session_file

        result = runner.invoke(app, ["auth", "status"])
        assert result.exit_code == ExitCode.SUCCESS
        assert "Адрес NAS:" in result.stdout
        assert "192.168.1.50:5001" in result.stdout
        assert "Загружен из защищенного хранилища" in result.stdout


def test_cli_auth_clear_removes_artifacts(tmp_path: Path) -> None:
    """Проверяет удаление зашифрованных файлов учетных данных и кэша сессии через 'syno auth clear'."""
    cred_file = tmp_path / "to_delete.enc"
    session_file = tmp_path / "session_to_delete.json"
    save_credentials_to_file("cleanup_user", "Pass!999", cred_file)
    session_file.write_text('{"sid": "old_sid"}', encoding="utf-8")

    assert cred_file.exists()
    assert session_file.exists()

    with patch("syno_cli.commands.auth_cmd.settings") as mock_settings:
        mock_settings.credentials_file = cred_file
        mock_settings.session_file = session_file
        mock_settings.session_backend = "file"

        result = runner.invoke(app, ["auth", "clear"])
        assert result.exit_code == ExitCode.SUCCESS
        assert "полностью удалены" in result.stdout
        assert not cred_file.exists()
        assert not session_file.exists()
