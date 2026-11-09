"""Централизованная инфраструктура CLI: единый декоратор команд и маршрутизация вывода."""

import asyncio
import json
import sys
from functools import wraps
from typing import Any, Callable, Coroutine, Optional, TypeAlias, TypeVar

import httpx
from pydantic import BaseModel, ValidationError
from rich.console import Console

from syno_cli.constants import ExitCode
from syno_cli.exceptions import DsmApiError, DsmAuthError

console = Console(stderr=False)
error_console = Console(stderr=True)

T = TypeVar("T")
RenderCallback: TypeAlias = Optional[Callable[[Any], None]]
CommandResult: TypeAlias = tuple[Any, RenderCallback]


def emit_output(
    data: Any,
    json_output: bool,
    render_func: RenderCallback = None,
) -> None:
    """Осуществляет централизованный вывод результата работы команды.

    Args:
        data: Данные ответа (Pydantic-модель, список, словарь или примитив).
        json_output: Флаг принудительного вывода в формате JSON.
        render_func: Пользовательская функция отрисовки Rich-таблицы или панели.
    """
    if json_output:
        if isinstance(data, BaseModel):
            payload = data.model_dump_json(indent=2)
        elif isinstance(data, (dict, list)):
            payload = json.dumps(data, indent=2, ensure_ascii=False)
        else:
            payload = json.dumps({"result": str(data)}, indent=2, ensure_ascii=False)
        sys.stdout.write(payload + "\n")
        sys.stdout.flush()
        return

    if render_func is not None:
        render_func(data)
    elif isinstance(data, BaseModel):
        console.print(data.model_dump())
    elif isinstance(data, str):
        console.print(data)


def _handle_cli_exception(exc: Exception, json_output: bool) -> int:
    """Форматирует перехваченное исключение в stderr и возвращает код выхода процесса.

    Args:
        exc: Перехваченное исключение.
        json_output: Выводить ли ошибку в формате JSON.

    Returns:
        int: Код завершения процесса из `ExitCode`.
    """
    if isinstance(exc, DsmAuthError):
        err_payload: dict[str, Any] = {"error": "AuthError", "code": exc.code, "detail": str(exc)}
        rich_msg = f"[bold red]✗ Ошибка аутентификации DSM ({exc.code}):[/bold red] {exc}"
        exit_code = int(ExitCode.AUTH_ERROR)
    elif isinstance(exc, DsmApiError):
        err_payload = {"error": "DsmApiError", "code": exc.code, "detail": str(exc)}
        rich_msg = f"[bold red]✗ Ошибка Synology Web API ({exc.code}):[/bold red] {exc}"
        exit_code = int(ExitCode.API_ERROR)
    elif isinstance(exc, ValidationError):
        err_payload = {"error": "ValidationError", "errors": exc.errors()}
        rich_msg = f"[bold red]✗ Ошибка схемы данных:[/bold red] {exc}"
        exit_code = int(ExitCode.VALIDATION_ERROR)
    elif isinstance(exc, (httpx.RequestError, OSError)):
        err_payload = {"error": "NetworkError", "detail": str(exc)}
        rich_msg = f"[bold red]✗ Сетевая ошибка соединения с NAS:[/bold red] {exc}"
        exit_code = int(ExitCode.NETWORK_ERROR)
    else:
        err_payload = {"error": "UnexpectedError", "detail": str(exc)}
        rich_msg = f"[bold red]✗ Непредвиденный сбой:[/bold red] {exc}"
        exit_code = int(ExitCode.UNEXPECTED_ERROR)

    if json_output:
        sys.stderr.write(json.dumps(err_payload, ensure_ascii=False) + "\n")
    else:
        error_console.print(rich_msg)
    return exit_code


def cli_command(
    spinner_message: Optional[str] = None,
) -> Callable[
    [Callable[..., Coroutine[Any, Any, CommandResult]]],
    Callable[..., None],
]:
    """Декоратор консольных команд для запуска корутин и централизованной обработки ошибок.

    Args:
        spinner_message: Текст для анимации ожидания в терминале.

    Returns:
        Callable: Обернутая синхронная функция для регистрации в Typer.
    """

    def decorator(
        func: Callable[..., Coroutine[Any, Any, CommandResult]],
    ) -> Callable[..., None]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> None:
            json_output: bool = bool(kwargs.get("json_output", False))

            async def _executor() -> None:
                if spinner_message and not json_output:
                    with console.status(f"[bold cyan]{spinner_message}[/bold cyan]"):
                        result, render_func = await func(*args, **kwargs)
                else:
                    result, render_func = await func(*args, **kwargs)
                emit_output(result, json_output=json_output, render_func=render_func)

            try:
                asyncio.run(_executor())
            except Exception as exc:
                sys.exit(_handle_cli_exception(exc, json_output))

        return wrapper

    return decorator
