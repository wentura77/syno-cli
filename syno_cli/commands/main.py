"""Корневая точка входа CLI-приложения `syno` на базе фреймворка Typer."""

import typer

from syno_cli.commands.auth_cmd import auth_app
from syno_cli.commands.docker_cmd import docker_app
from syno_cli.commands.download_cmd import download_app
from syno_cli.commands.files_cmd import files_app
from syno_cli.commands.system_cmd import register_system_commands
from syno_cli.commands.vm_cmd import vm_app

app = typer.Typer(
    name="syno",
    help="Консольная утилита управления Synology NAS через официальный DSM Web API.",
    no_args_is_help=True,
)

# Корневые команды: status, storage
register_system_commands(app)

# Подгруппы команд
app.add_typer(auth_app, name="auth")
app.add_typer(docker_app, name="docker")
app.add_typer(vm_app, name="vm")
app.add_typer(files_app, name="files")
app.add_typer(download_app, name="download")


def run() -> None:
    """Запустить консольное CLI-приложение `syno`."""
    app()


if __name__ == "__main__":
    run()
