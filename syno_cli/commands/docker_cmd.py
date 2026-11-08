"""CLI-команды управления Docker и Container Manager в Synology DSM."""

from typing import Any, Optional, Tuple

import typer

from syno_cli.client.base import BaseSynoClient
from syno_cli.client.docker import SynoDockerClient
from syno_cli.commands.common import cli_command, console
from syno_cli.views.tables import (
    render_docker_containers,
    render_docker_images,
)

docker_app = typer.Typer(help="Управление контейнерами, образами и проектами Docker.")


@docker_app.command("ps")
@cli_command(spinner_message="Получение списка контейнеров Docker...")
async def docker_ps(
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> Tuple[Any, Any]:
    """Вывести список всех контейнеров Docker и их текущие статусы."""
    base = BaseSynoClient()
    try:
        docker = SynoDockerClient(base)
        containers = await docker.list_containers()
        return containers, render_docker_containers
    finally:
        await base.close()


@docker_app.command("images")
@cli_command(spinner_message="Запрос локальных образов Docker...")
async def docker_images(
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> Tuple[Any, Any]:
    """Вывести список загруженных локальных Docker-образов."""
    base = BaseSynoClient()
    try:
        docker = SynoDockerClient(base)
        images = await docker.list_images()
        return images, render_docker_images
    finally:
        await base.close()


@docker_app.command("pull")
@cli_command(spinner_message="Отправка запроса на загрузку образа...")
async def docker_pull(
    image: str = typer.Argument(..., help="Имя образа с тегом, например nginx:latest"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> Tuple[Any, Any]:
    """Загрузить (pull) указанный Docker-образ из реестра на Synology NAS."""
    repo, tag = (image.split(":", 1) + ["latest"])[:2] if ":" in image else (image, "latest")
    base = BaseSynoClient()
    try:
        docker = SynoDockerClient(base)
        result = await docker.pull_image(repo, tag)
        return (
            result,
            lambda _: console.print(
                f"[bold green]✓ Запущена загрузка образа {repo}:{tag}[/bold green]"
            ),
        )
    finally:
        await base.close()


@docker_app.command("run")
@cli_command(spinner_message="Создание и запуск контейнера...")
async def docker_run(
    name: str = typer.Option(..., "--name", "-n", help="Имя создаваемого контейнера"),
    image: str = typer.Option(..., "--image", "-i", help="Образ (например, redis:alpine)"),
    port: Optional[list[str]] = typer.Option(None, "--port", "-p", help="Проброс портов HOST:CONT"),
    volume: Optional[list[str]] = typer.Option(None, "--volume", "-v", help="Тома /host:/cont"),
    env: Optional[list[str]] = typer.Option(None, "--env", "-e", help="Переменные KEY=VAL"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> Tuple[Any, Any]:
    """Создать и запустить новый Docker-контейнер на Synology NAS."""
    base = BaseSynoClient()
    try:
        docker = SynoDockerClient(base)
        result = await docker.create_container(
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
    finally:
        await base.close()


@docker_app.command("start")
@cli_command(spinner_message="Запуск контейнера...")
async def docker_start(
    name: str = typer.Argument(..., help="Имя контейнера"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> Tuple[Any, Any]:
    """Запустить остановленный Docker-контейнер."""
    base = BaseSynoClient()
    try:
        result = await SynoDockerClient(base).start_container(name)
        return (
            result,
            lambda _: console.print(f"[bold green]✓ Контейнер '{name}' запущен[/bold green]"),
        )
    finally:
        await base.close()


@docker_app.command("stop")
@cli_command(spinner_message="Остановка контейнера...")
async def docker_stop(
    name: str = typer.Argument(..., help="Имя контейнера"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Вывод в формате JSON"),
) -> Tuple[Any, Any]:
    """Остановить работающий Docker-контейнер."""
    base = BaseSynoClient()
    try:
        result = await SynoDockerClient(base).stop_container(name)
        return (
            result,
            lambda _: console.print(f"[bold yellow]✓ Контейнер '{name}' остановлен[/bold yellow]"),
        )
    finally:
        await base.close()
