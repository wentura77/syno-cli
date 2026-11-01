"""CLI-команды для безопасного управления логином, паролем и сессионным кэшем Synology NAS."""

from pathlib import Path
import typer

from syno_cli.config import USER_CACHE_DIR, USER_CONFIG_DIR, USER_CONFIG_FILE, settings
from syno_cli.credential_storage import (
    clear_stored_credentials,
    get_credentials,
    save_credentials_to_file,
    save_credentials_to_keyring,
)
from syno_cli.session_storage import get_session_storage
from syno_cli.views.tables import console

auth_app = typer.Typer(
    help="Безопасное шифрование и хранение учетных данных и сессии DSM (file / keyring)."
)


@auth_app.command("store")
def auth_store(
    username: str = typer.Option(
        "admin", "--user", "-u", prompt="Логин пользователя DSM", help="Имя пользователя DSM"
    ),
    password: str = typer.Option(
        ...,
        "--password",
        "-p",
        prompt="Пароль от Synology DSM",
        hide_input=True,
        confirmation_prompt=True,
        help="Пароль пользователя DSM (скрытый ввод)",
    ),
    backend: str = typer.Option(
        "file",
        "--backend",
        "-b",
        help="Бэкенд хранения: 'file' (шифрование с привязкой к ПК) или 'keyring' (связка ключей)",
    ),
) -> None:
    """Зашифровать и сохранить логин и пароль Synology DSM для текущего компьютера.

    Args:
        username: Имя пользователя для входа в DSM.
        password: Пароль пользователя (скрытый ввод).
        backend: Целевой бэкенд хранения (`'file'` или `'keyring'`).
    """
    target = backend.strip().lower()
    if target == "keyring":
        save_credentials_to_keyring(username, password)
        console.print(
            "[bold green]✓ Учетные данные успешно сохранены в системной связке ключей (keyring).[/bold green]"
        )
    else:
        cred_path = Path(settings.credentials_file)
        save_credentials_to_file(username, password, cred_path)
        console.print(
            f"[bold green]✓ Учетные данные зашифрованы с привязкой к текущему ПК и сохранены в:[/bold green] {cred_path}"
        )


@auth_app.command("clear")
def auth_clear() -> None:
    """Удалить все сохраненные пароли и очистить зашифрованный кэш сессии."""
    cred_path = Path(settings.credentials_file)
    clear_stored_credentials(cred_path)

    storage = get_session_storage(settings.session_backend, Path(settings.session_file))
    storage.clear()
    Path(settings.session_file).unlink(missing_ok=True)

    console.print(
        "[bold green]✓ Зашифрованные учетные данные и кэш сессии полностью удалены.[/bold green]"
    )


@auth_app.command("status")
def auth_status() -> None:
    """Отобразить пользовательские пути platformdirs и статус зашифрованных данных."""
    cred_path = Path(settings.credentials_file)
    session_path = Path(settings.session_file)
    has_creds = get_credentials(settings.session_backend, cred_path) is not None

    console.print(f"[bold cyan]Адрес NAS:[/bold cyan]            {settings.base_url}")
    console.print(f"[bold cyan]Пользователь:[/bold cyan]         {settings.user}")
    console.print(f"[bold cyan]Бэкенд безопасности:[/bold cyan]  {settings.session_backend}")
    console.print(f"[bold cyan]Папка конфигурации:[/bold cyan]   {USER_CONFIG_DIR}")
    console.print(f"[bold cyan]Конфиг-файл:[/bold cyan]          {USER_CONFIG_FILE} ({'существует' if USER_CONFIG_FILE.exists() else 'нет'})")
    console.print(f"[bold cyan]Файл учетных данных:[/bold cyan]  {cred_path} ({'существует' if cred_path.exists() else 'нет'})")
    console.print(f"[bold cyan]Папка кэша:[/bold cyan]           {USER_CACHE_DIR}")
    console.print(f"[bold cyan]Файл кэша сессии:[/bold cyan]     {session_path} ({'существует' if session_path.exists() else 'нет'})")
    console.print(
        f"[bold cyan]Пароль в хранилище:[/bold cyan]   "
        f"{'🟢 Загружен из защищенного хранилища' if has_creds else '⚪ Используется .env / дефолт'}"
    )
