"""Централизованная инфраструктура CLI: единый декоратор команд и маршрутизация вывода."""

import asyncio
import json
import sys
from functools import wraps
from typing import Any, Callable, Coroutine, Optional, TypeVar

import httpx
from pydantic import BaseModel, ValidationError
from rich.console import Console

from syno_cli.exceptions import DsmApiError, DsmAuthError

console = Console(stderr=False)
error_console = Console(stderr=True)

T = TypeVar("T")


def emit_output(
    data: Any,
    json_output: bool,
    render_func: Optional[Callable[[Any], None]] = None,
) -> None:
    """Осуществляет централизованный вывод результата работы команды.

    Args:
        data: Данные ответа (Pydantic-модель, список, словарь или примитив).
        json_output: Флаг принудительного вывода в формате JSON.
        render_func: Пользовательская функция отрисовки Rich-таблицы или панели.
    """
    if json_output:
        if isinstance(data, BaseModel):
            sys.stdout.write(data.model_dump_json(indent=2) + "\n")
        elif isinstance(data, (dict, list)):
            sys.stdout.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        else:
            sys.stdout.write(json.dumps({"result": str(data)}, indent=2, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    else:
        if render_func is not None:
            render_func(data)
        elif isinstance(data, BaseModel):
            console.print(data.model_dump())
        elif isinstance(data, str):
            console.print(data)


def cli_command(
    spinner_message: Optional[str] = None,
) -> Callable[
    [Callable[..., Coroutine[Any, Any, tuple[Any, Optional[Callable[[Any], None]]]]]],
    Callable[..., None],
]:
    """Декоратор консольных команд для устранения дублирования asyncio.run и try-except.

    Выполняет:
    - Запуск асинхронного цикла событий через asyncio.run();
    - Отображение спиннера выполнения (если не активен флаг --json);
    - Глобальный перехват исключений и вывод ошибок в stderr (в JSON или Rich-формате);
    - Возврат корректных статус-кодов завершения процесса (sys.exit).

    Args:
        spinner_message: Текст для анимации ожидания в терминале.

    Returns:
        Callable: Обернутая синхронная функция для регистрации в Typer.
    """

    def decorator(
        func: Callable[..., Coroutine[Any, Any, tuple[Any, Optional[Callable[[Any], None]]]]],
    ) -> Callable[..., None]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> None:
            json_output: bool = kwargs.get("json_output", False)

            async def _executor() -> None:
                if spinner_message and not json_output:
                    with console.status(f"[bold cyan]{spinner_message}[/bold cyan]"):
                        result, render_func = await func(*args, **kwargs)
                else:
                    result, render_func = await func(*args, **kwargs)

                emit_output(result, json_output=json_output, render_func=render_func)

            try:
                asyncio.run(_executor())
            except DsmAuthError as exc:
                if json_output:
                    sys.stderr.write(
                        json.dumps(
                            {"error": "AuthError", "code": exc.code, "detail": str(exc)},
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                else:
                    error_console.print(
                        f"[bold red]✗ Ошибка аутентификации DSM ({exc.code}):[/bold red] {exc}"
                    )
                sys.exit(1)
            except DsmApiError as exc:
                if json_output:
                    sys.stderr.write(
                        json.dumps(
                            {"error": "DsmApiError", "code": exc.code, "detail": str(exc)},
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                else:
                    error_console.print(
                        f"[bold red]✗ Ошибка Synology Web API ({exc.code}):[/bold red] {exc}"
                    )
                sys.exit(2)
            except ValidationError as exc:
                if json_output:
                    sys.stderr.write(
                        json.dumps(
                            {"error": "ValidationError", "errors": exc.errors()}, ensure_ascii=False
                        )
                        + "\n"
                    )
                else:
                    error_console.print(f"[bold red]✗ Ошибка схемы данных:[/bold red] {exc}")
                sys.exit(3)
            except (httpx.RequestError, OSError) as exc:
                if json_output:
                    sys.stderr.write(
                        json.dumps(
                            {"error": "NetworkError", "detail": str(exc)}, ensure_ascii=False
                        )
                        + "\n"
                    )
                else:
                    error_console.print(
                        f"[bold red]✗ Сетевая ошибка соединения с NAS:[/bold red] {exc}"
                    )
                sys.exit(4)
            except Exception as exc:
                if json_output:
                    sys.stderr.write(
                        json.dumps(
                            {"error": "UnexpectedError", "detail": str(exc)}, ensure_ascii=False
                        )
                        + "\n"
                    )
                else:
                    error_console.print(f"[bold red]✗ Непредвиденный сбой:[/bold red] {exc}")
                sys.exit(5)

        return wrapper

    return decorator
