"""CLI-команды управления Docker и Container Manager в Synology DSM."""

from pathlib import Path
from typing import Optional

import typer

from syno_cli.commands.common import CommandResult, cli_command, console
from syno_cli.constants import DEFAULT_DOCKER_LOG_TAIL
from syno_cli.facade import SynoDSM
from syno_cli.views.tables import (
    render_docker_containers,
    render_docker_images,
    render_docker_logs,
    render_docker_projects,
    render_docker_stats,
)

docker_app = typer.Typer(help="Управление контейнерами, образами и ресурсами Docker.")


@docker_app.command("ps")
@cli_command(spinner_message="Получение списка контейнеров Docker...")
async def docker_ps(
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Вывести список всех контейнеров Docker и их текущие статусы.

    Args:
        json_output: Флаг вывода в формате JSON.

    Returns:
        CommandResult: Список контейнеров и функция отрисовки.
    """
    _ = json_output
    async with SynoDSM() as nas:
        containers = await nas.docker.list_containers()
        return containers, render_docker_containers


@docker_app.command("stats")
@cli_command(spinner_message="Опрос утилизации ресурсов контейнерами...")
async def docker_stats(
    name: Optional[str] = typer.Argument(None, help="Имя конкретного контейнера (опционально)"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Отобразить утилизацию CPU, RAM, диска и сети контейнерами в реальном времени.

    Args:
        name: Имя контейнера (опционально).
        json_output: Флаг вывода в формате JSON.

    Returns:
        CommandResult: Список метрик и функция отрисовки.
    """
    _ = json_output
    async with SynoDSM() as nas:
        stats = await nas.docker.get_container_stats(name)
        return stats, render_docker_stats


@docker_app.command("logs")
@cli_command(spinner_message="Запрос логов контейнера...")
async def docker_logs(
    name: str = typer.Argument(..., help="Имя контейнера для чтения логов"),
    lines: int = typer.Option(
        DEFAULT_DOCKER_LOG_TAIL, "--lines", "-n", help="Количество выводимых строк журнала"
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Вывести последние строки журнала событий (логов) контейнера.

    Args:
        name: Имя контейнера.
        lines: Количество последних строк.
        json_output: Флаг вывода в формате JSON.

    Returns:
        CommandResult: Строки лога и функция отрисовки.
    """
    _ = json_output
    async with SynoDSM() as nas:
        logs = await nas.docker.get_container_logs(name=name, tail=lines)
        return logs, render_docker_logs


@docker_app.command("images")
@cli_command(spinner_message="Запрос локальных образов Docker...")
async def docker_images(
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Вывести список загруженных локальных Docker-образов.

    Args:
        json_output: Флаг вывода в формате JSON.

    Returns:
        CommandResult: Список образов и функция отрисовки.
    """
    _ = json_output
    async with SynoDSM() as nas:
        images = await nas.docker.list_images()
        return images, render_docker_images


@docker_app.command("pull")
@cli_command(spinner_message="Отправка запроса на загрузку образа...")
async def docker_pull(
    image: str = typer.Argument(..., help="Имя образа с тегом, например nginx:latest"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Загрузить (pull) указанный Docker-образ из реестра на Synology NAS.

    Args:
        image: Имя образа с тегом.
        json_output: Флаг вывода в формате JSON.

    Returns:
        CommandResult: Ответ DSM и колбэк подтверждения.
    """
    _ = json_output
    repo, tag = (image.split(":", 1) + ["latest"])[:2] if ":" in image else (image, "latest")
    async with SynoDSM() as nas:
        result = await nas.docker.pull_image(repo, tag)
        return (
            result,
            lambda _: console.print(
                f"[bold green]✓ Запущена загрузка образа {repo}:{tag}[/bold green]"
            ),
        )


@docker_app.command("run")
@cli_command(spinner_message="Создание и запуск контейнера...")
async def docker_run(
    name: str = typer.Option(..., "--name", "-n", help="Имя создаваемого контейнера"),
    image: str = typer.Option(..., "--image", "-i", help="Образ (например, redis:alpine)"),
    port: Optional[list[str]] = typer.Option(None, "--port", "-p", help="Проброс портов HOST:CONT"),
    volume: Optional[list[str]] = typer.Option(None, "--volume", "-v", help="Тома /host:/cont"),
    env: Optional[list[str]] = typer.Option(None, "--env", "-e", help="Переменные KEY=VAL"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Создать и запустить новый Docker-контейнер на Synology NAS.

    Args:
        name: Имя контейнера.
        image: Образ Docker.
        port: Проброс портов.
        volume: Монтируемые тома.
        env: Переменные окружения.
        json_output: Флаг вывода в формате JSON.

    Returns:
        CommandResult: Ответ DSM и колбэк подтверждения.
    """
    _ = json_output
    async with SynoDSM() as nas:
        result = await nas.docker.create_container(
            name=name,
            image=image,
            ports=port,
            volumes=volume,
            env_vars=env,
            auto_start=True,
        )
        return (
            result,
            lambda _: console.print(
                f"[bold green]✓ Контейнер '{name}' ({image}) создан и запущен[/bold green]"
            ),
        )


@docker_app.command("start")
@cli_command(spinner_message="Запуск контейнера...")
async def docker_start(
    name: str = typer.Argument(..., help="Имя контейнера"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Запустить остановленный Docker-контейнер.

    Args:
        name: Имя контейнера.
        json_output: Флаг вывода в формате JSON.

    Returns:
        CommandResult: Ответ DSM и колбэк подтверждения.
    """
    _ = json_output
    async with SynoDSM() as nas:
        result = await nas.docker.start_container(name)
        return (
            result,
            lambda _: console.print(f"[bold green]✓ Контейнер '{name}' запущен[/bold green]"),
        )


@docker_app.command("stop")
@cli_command(spinner_message="Остановка контейнера...")
async def docker_stop(
    name: str = typer.Argument(..., help="Имя контейнера"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Остановить работающий Docker-контейнер.

    Args:
        name: Имя контейнера.
        json_output: Флаг вывода в формате JSON.

    Returns:
        CommandResult: Ответ DSM и колбэк подтверждения.
    """
    _ = json_output
    async with SynoDSM() as nas:
        result = await nas.docker.stop_container(name)
        return (
            result,
            lambda _: console.print(f"[bold yellow]✓ Контейнер '{name}' остановлен[/bold yellow]"),
        )


@docker_app.command("restart")
@cli_command(spinner_message="Перезапуск контейнера...")
async def docker_restart(
    name: str = typer.Argument(..., help="Имя контейнера"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Перезапустить работающий или остановленный Docker-контейнер.

    Args:
        name: Имя контейнера.
        json_output: Флаг вывода в формате JSON.

    Returns:
        CommandResult: Ответ DSM и колбэк подтверждения.
    """
    _ = json_output
    async with SynoDSM() as nas:
        result = await nas.docker.restart_container(name)
        return (
            result,
            lambda _: console.print(f"[bold green]✓ Контейнер '{name}' перезапущен[/bold green]"),
        )


@docker_app.command("rm")
@cli_command(spinner_message="Удаление контейнера...")
async def docker_rm(
    name: str = typer.Argument(..., help="Имя удаляемого контейнера"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Принудительно удалить работающий контейнер"
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Удалить контейнер с Synology NAS.

    Args:
        name: Имя контейнера.
        force: Принудительное удаление.
        json_output: Флаг вывода в формате JSON.

    Returns:
        CommandResult: Ответ DSM и колбэк подтверждения.
    """
    _ = json_output
    async with SynoDSM() as nas:
        result = await nas.docker.delete_container(name, force=force)
        return (
            result,
            lambda _: console.print(f"[bold red]✓ Контейнер '{name}' удален[/bold red]"),
        )


compose_app = typer.Typer(help="Управление мультиконтейнерными проектами Docker Compose.")
docker_app.add_typer(compose_app, name="compose")


@compose_app.command("list")
@cli_command(spinner_message="Запрос проектов Docker Compose...")
async def compose_list(
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Вывести список всех проектов Docker Compose.

    Args:
        json_output: Флаг вывода в формате JSON.

    Returns:
        CommandResult: Список проектов и функция отрисовки.
    """
    _ = json_output
    async with SynoDSM() as nas:
        projects = await nas.docker.list_projects()
        return projects, render_docker_projects


@compose_app.command("up")
@cli_command(spinner_message="Сборка и развертывание проекта Docker Compose...")
async def compose_up(
    name: str = typer.Argument(..., help="Имя проекта Compose"),
    file_path: Path = typer.Argument(..., help="Локальный путь к docker-compose.yml"),
    env_file: Optional[Path] = typer.Option(None, "--env-file", "-e", help="Путь к файлу .env"),
    share_path: Optional[str] = typer.Option(None, "--path", "-p", help="Целевой путь на томе NAS"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Развернуть или обновить проект Docker Compose (up).

    Args:
        name: Имя проекта.
        file_path: Путь к файлу `docker-compose.yml`.
        env_file: Путь к файлу `.env`.
        share_path: Путь на томе NAS.
        json_output: Флаг вывода в формате JSON.

    Returns:
        CommandResult: Ответ DSM и колбэк подтверждения.

    Raises:
        FileNotFoundError: Если файл `docker-compose.yml` не существует.
    """
    _ = json_output
    resolved_compose = file_path.expanduser()
    if not resolved_compose.is_file():
        raise FileNotFoundError(f"Файл compose не найден: {file_path}")

    compose_text = resolved_compose.read_text(encoding="utf-8")
    env_text = (
        env_file.expanduser().read_text(encoding="utf-8")
        if env_file and env_file.is_file()
        else None
    )

    async with SynoDSM() as nas:
        result = await nas.docker.build_or_start_project(
            name=name,
            compose_content=compose_text,
            env_content=env_text,
            share_path=share_path,
        )
        return (
            result,
            lambda _: console.print(
                f"[bold green]✓ Проект Compose '{name}' успешно запущен[/bold green]"
            ),
        )


@compose_app.command("down")
@cli_command(spinner_message="Остановка проекта Compose...")
async def compose_down(
    name: str = typer.Argument(..., help="Имя проекта Compose"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Остановить сервисы проекта Docker Compose (down).

    Args:
        name: Имя проекта.
        json_output: Флаг вывода в формате JSON.

    Returns:
        CommandResult: Ответ DSM и колбэк подтверждения.
    """
    _ = json_output
    async with SynoDSM() as nas:
        result = await nas.docker.stop_project(name)
        return (
            result,
            lambda _: console.print(
                f"[bold yellow]✓ Проект Compose '{name}' остановлен[/bold yellow]"
            ),
        )


@compose_app.command("restart")
@cli_command(spinner_message="Перезапуск сервисов проекта Compose...")
async def compose_restart(
    name: str = typer.Argument(..., help="Имя проекта Compose"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Перезапустить сервисы проекта Docker Compose.

    Args:
        name: Имя проекта.
        json_output: Флаг вывода в формате JSON.

    Returns:
        CommandResult: Ответ DSM и колбэк подтверждения.
    """
    _ = json_output
    async with SynoDSM() as nas:
        result = await nas.docker.restart_project(name)
        return (
            result,
            lambda _: console.print(
                f"[bold green]✓ Проект Compose '{name}' перезапущен[/bold green]"
            ),
        )


@compose_app.command("logs")
@cli_command(spinner_message="Запрос логов проекта Compose...")
async def compose_logs(
    name: str = typer.Argument(..., help="Имя проекта Compose"),
    lines: int = typer.Option(
        DEFAULT_DOCKER_LOG_TAIL, "--lines", "-n", help="Количество строк лога"
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> CommandResult:
    """Вывести агрегированные логи всех сервисов проекта Compose.

    Args:
        name: Имя проекта.
        lines: Количество последних строк.
        json_output: Флаг вывода в формате JSON.

    Returns:
        CommandResult: Список строк лога и функция отрисовки.
    """
    _ = json_output
    async with SynoDSM() as nas:
        logs = await nas.docker.get_project_logs(name=name, tail=lines)
        return logs, render_docker_logs
