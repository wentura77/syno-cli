"""Модульные тесты динамического автодополнения удаленных путей в шелле (completion.py)."""

from unittest.mock import AsyncMock, patch

import pytest

from syno_cli.commands.completion import (
    _build_suggestion_path,
    _split_incomplete_path,
    complete_remote_path,
)

# ---------------------------------------------------------------------------
# 1. Юнит-тесты вспомогательных функций разбора и форматирования путей
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("incomplete", "expected_parent", "expected_prefix"),
    [
        ("", "/", ""),
        ("/", "/", ""),
        ("/volume1", "/", "volume1"),
        ("/volume1/", "/volume1", ""),
        ("/volume1/doc", "/volume1", "doc"),
        ("/volume1/docker/app", "/volume1/docker", "app"),
        ("relative_path", "/", "relative_path"),
    ],
)
def test_split_incomplete_path(
    incomplete: str, expected_parent: str, expected_prefix: str
) -> None:
    """Проверяет корректность разбиения неполного пути на parent_dir и prefix."""
    parent_dir, prefix = _split_incomplete_path(incomplete)
    assert parent_dir == expected_parent
    assert prefix == expected_prefix


def test_build_suggestion_path_directories_and_files() -> None:
    """Проверяет добавление завершающего слэша для директорий и его отсутствие для файлов."""
    # Корневой каталог
    assert _build_suggestion_path("/", "volume1", is_dir=True) == "/volume1/"
    assert _build_suggestion_path("/", "file.txt", is_dir=False) == "/file.txt"

    # Вложенная директория
    assert (
        _build_suggestion_path("/volume1", "docker", is_dir=True)
        == "/volume1/docker/"
    )
    assert (
        _build_suggestion_path("/volume1/docker", "compose.yml", is_dir=False)
        == "/volume1/docker/compose.yml"
    )

    # Путь с завершающим слэшем у родителя
    assert (
        _build_suggestion_path("/volume1/", "data", is_dir=True)
        == "/volume1/data/"
    )


# ---------------------------------------------------------------------------
# 2. Интеграционные тесты complete_remote_path с мокированием SynoDSM
# ---------------------------------------------------------------------------


def test_complete_remote_path_success() -> None:
    """Проверяет автодополнение с фильтрацией по префиксу и форматированием слешей."""
    mock_files = [
        {"name": "docker", "isdir": True},
        {"name": "document.pdf", "isdir": False},
        {"name": "downloads", "isdir": True},
        {"name": "music", "isdir": True},
    ]

    with patch("syno_cli.commands.completion.SynoDSM") as mock_dsm:
        instance = mock_dsm.return_value.__aenter__.return_value
        instance.files.list_dir = AsyncMock(return_value=mock_files)

        # Поиск по префиксу 'doc' в /volume1/
        suggestions = complete_remote_path(
            ctx=None, args=[], incomplete="/volume1/doc"
        )

        assert len(suggestions) == 2
        # Папка должна завершаться слэшем, файл — нет
        assert "/volume1/docker/" in suggestions
        assert "/volume1/document.pdf" in suggestions
        assert "/volume1/downloads/" not in suggestions
        assert "/volume1/music/" not in suggestions

        instance.files.list_dir.assert_awaited_once_with("/volume1")


def test_complete_remote_path_case_insensitive() -> None:
    """Проверяет регистронезависимую фильтрацию элементов."""
    mock_files = [
        {"name": "Photos", "isdir": True},
        {"name": "phone_backup.zip", "isdir": False},
        {"name": "public", "isdir": True},
    ]

    with patch("syno_cli.commands.completion.SynoDSM") as mock_dsm:
        instance = mock_dsm.return_value.__aenter__.return_value
        instance.files.list_dir = AsyncMock(return_value=mock_files)

        # Префикс в нижнем регистре находит 'Photos' и 'phone_backup.zip'
        suggestions = complete_remote_path(
            ctx=None, args=[], incomplete="/volume1/ph"
        )

        assert len(suggestions) == 2
        assert "/volume1/Photos/" in suggestions
        assert "/volume1/phone_backup.zip" in suggestions
        assert "/volume1/public/" not in suggestions


def test_complete_remote_path_network_or_api_error_returns_empty_list() -> None:
    """Проверяет возврат пустого списка [] при сбоях сети/API без выброса исключения."""
    with patch("syno_cli.commands.completion.SynoDSM") as mock_dsm:
        instance = mock_dsm.return_value.__aenter__.return_value
        instance.files.list_dir = AsyncMock(side_effect=OSError("Network unreachable"))

        # Вызов не должен выбрасывать исключение и ронять шелл
        suggestions = complete_remote_path(
            ctx=None, args=[], incomplete="/volume1/test"
        )

        assert suggestions == []
