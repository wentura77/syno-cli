"""Клиент работы с системными журналами событий (Log Center) в Synology DSM."""

from typing import Any, Optional

from syno_cli.client.base import BaseSynoClient


class SynoLogsClient:
    """Клиент для взаимодействия с API SYNO.Core.SyslogClient.*."""

    def __init__(self, base: BaseSynoClient) -> None:
        """Инициализирует клиент журналов.

        Args:
            base: Экземпляр базового клиента DSM.
        """
        self.base = base

    async def list_logs(
        self,
        level: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        keyword: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Запрашивает системные логи DSM.

        Args:
            level: Фильтр критичности (info, warn, err).
            limit: Количество записей.
            offset: Смещение выборки.
            keyword: Ключевое слово для поиска.

        Returns:
            list[dict[str, Any]]: Список записей системного журнала.
        """
        params: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
        }
        if level:
            params["level"] = level
        if keyword:
            params["keyword"] = keyword

        # 1. Пробуем основной интерфейс SYNO.Core.SyslogClient.Log
        try:
            data = await self.base.request(
                "SYNO.Core.SyslogClient.Log",
                "list",
                version=1,
                params=params,
            )
            items = data.get("items", data.get("logs", []))
            if isinstance(items, list):
                return list(items)
        except Exception:
            pass

        # 2. Fallback: SYNO.Core.SyslogClient.Setting.Log (DSM 7.x)
        data = await self.base.request(
            "SYNO.Core.SyslogClient.Setting.Log",
            "list",
            version=1,
            params=params,
        )
        items = data.get("items", data.get("logs", []))
        return list(items) if isinstance(items, list) else []
