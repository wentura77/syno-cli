"""CLI-команды управления Docker и Container Manager в Synology DSM."""

import asyncio
from typing import Optional

import typer

from syno_cli.client.base import BaseSynoClient
from syno_cli.client.docker import SynoDockerClient
from syno_cli.views.tables import (
    console,
    render_docker_containers,
    render_docker_images,
)

docker_app = typer.Typer(help="Управление контейнерами, образами и проектами Docker.")


@docker_app.command("ps")
def docker_ps() -> None:
    """Вывести список всех контейнеров Docker и их текущие статусы."""

    async def _impl() -> None:
        """Асинхронно получить и отобразить список контейнеров."""
        base = BaseSynoClient()
        try:
            docker = SynoDockerClient(base)
            containers = await docker.list_containers()
            render_docker_containers(containers)
        finally:
            await base.close()

    asyncio.run(_impl())


@docker_app.command("images")
def docker_images() -> None:
    """Вывести список загруженных локальных Docker-образов."""

    async def _impl() -> None:
        """Асинхронно получить и отобразить локальные образы."""
        base = BaseSynoClient()
        try:
            docker = SynoDockerClient(base)
            images = await docker.list_images()
            render_docker_images(images)
        finally:
            await base.close()

    asyncio.run(_impl())


@docker_app.command("pull")
def docker_pull(
    image: str = typer.Argument(..., help="Имя образа с тегом, например nginx:latest"),
) -> None:
    """Загрузить (pull) указанный Docker-образ из реестра на Synology NAS.

    Args:
        image: Имя репозитория и тег образа через двоеточие.
    """
    repo, tag = (image.split(":", 1) + ["latest"])[:2] if ":" in image else (image, "latest")

    async def _impl() -> None:
        """Асинхронно отправить запрос на загрузку образа."""
        base = BaseSynoClient()
        try:
            docker = SynoDockerClient(base)
            await docker.pull_image(repo, tag)
            console.print(f"[bold green]✓ Запущена загрузка образа {repo}:{tag}[/bold green]")
        finally:
            await base.close()

    asyncio.run(_impl())


@docker_app.command("run")
def docker_run(
    name: str = typer.Option(..., "--name", "-n", help="Имя создаваемого контейнера"),
    image: str = typer.Option(..., "--image", "-i", help="Образ (например, redis:alpine)"),
    port: Optional[list[str]] = typer.Option(None, "--port", "-p", help="Проброс портов HOST:CONT"),
    volume: Optional[list[str]] = typer.Option(None, "--volume", "-v", help="Тома /host:/cont"),
    env: Optional[list[str]] = typer.Option(None, "--env", "-e", help="Переменные KEY=VAL"),
) -> None:
    """Создать и запустить новый Docker-контейнер на Synology NAS.

    Args:
        name: Уникальное имя создаваемого контейнера.
        image: Базовый образ для развёртывания.
        port: Список пробрасываемых портов в формате хост:контейнер.
        volume: Список монтируемых каталогов в формате хост:контейнер.
        env: Список переменных окружения в формате КЛЮЧ=ЗНАЧЕНИЕ.
    """

    async def _impl() -> None:
        """Асинхронно создать и запустить контейнер."""
        base = BaseSynoClient()
        try:
            docker = SynoDockerClient(base)
            await docker.create_container(
                name=name,
                image=image,
                ports=port,
                volumes=volume,
                env_vars=env,
                auto_start=True,
            )
            console.print(
                f"[bold green]✓ Контейнер '{name}' ({image}) создан и запущен[/bold green]"
            )
        finally:
            await base.close()

    asyncio.run(_impl())


@docker_app.command("start")
def docker_start(name: str = typer.Argument(..., help="Имя контейнера")) -> None:
    """Запустить остановленный Docker-контейнер.

    Args:
        name: Имя целевого контейнера.
    """

    async def _impl() -> None:
        """Асинхронно отправить команду запуска контейнера."""
        base = BaseSynoClient()
        try:
            await SynoDockerClient(base).start_container(name)
            console.print(f"[bold green]✓ Контейнер '{name}' запущен[/bold green]")
        finally:
            await base.close()

    asyncio.run(_impl())


@docker_app.command("stop")
def docker_stop(name: str = typer.Argument(..., help="Имя контейнера")) -> None:
    """Остановить работающий Docker-контейнер.

    Args:
        name: Имя целевого контейнера.
    """

    async def _impl() -> None:
        """Асинхронно отправить команду остановки контейнера."""
        base = BaseSynoClient()
        try:
            await SynoDockerClient(base).stop_container(name)
            console.print(f"[bold yellow]✓ Контейнер '{name}' остановлен[/bold yellow]")
        finally:
            await base.close()

    asyncio.run(_impl())
