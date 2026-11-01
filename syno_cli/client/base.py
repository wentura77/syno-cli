"""Базовый асинхронный HTTP-клиент для взаимодействия с Synology DSM Web API."""

import json
from pathlib import Path
from typing import Any, Optional
import httpx

from syno_cli.config import SynoSettings, settings as default_settings
from syno_cli.exceptions import DsmApiError, DsmAuthError


class BaseSynoClient:
    """
    Базовый клиент Synology DSM Web API.

    Отвечает за:
    - обнаружение доступных эндпоинтов через `SYNO.API.Info`;
    - аутентификацию через `SYNO.API.Auth` с поддержкой 2FA (OTP);
    - кэширование идентификатора сессии (`sid`) и карты API на диске;
    - автоматический перелогин при истечении сессии (коды 105, 106, 107, 119).
    """

    def __init__(
        self,
        config: Optional[SynoSettings] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.config = config or default_settings
        self.sid: Optional[str] = None
        self.api_map: dict[str, dict[str, Any]] = {}
        self.client = httpx.AsyncClient(
            base_url=self.config.base_url,
            verify=False,
            timeout=30.0,
            transport=transport,
        )
        self._load_session()

    def _load_session(self) -> None:
        """Загружает сохраненный токен `sid` и карту API из локального кэш-файла."""
        path: Path = self.config.session_file
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self.sid = data.get("sid")
                self.api_map = data.get("api_map", {})
            except Exception:
                self.sid = None

    def _save_session(self) -> None:
        """Сохраняет текущий токен `sid` и карту API в локальный кэш-файл."""
        try:
            payload = {"sid": self.sid, "api_map": self.api_map}
            self.config.session_file.write_text(
                json.dumps(payload, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    def _clear_session(self) -> None:
        """Очищает токен сессии в памяти и удаляет кэш-файл."""
        self.sid = None
        if self.config.session_file.exists():
            try:
                self.config.session_file.unlink()
            except Exception:
                pass

    async def discover_apis(self) -> dict[str, dict[str, Any]]:
        """Запрашивает карту поддерживаемых API и их CGI-путей через `SYNO.API.Info`."""
        resp = await self.client.get(
            "/webapi/query.cgi",
            params={
                "api": "SYNO.API.Info",
                "version": "1",
                "method": "query",
                "query": "all",
            },
        )
        resp.raise_for_status()
        body = resp.json()
        if not body.get("success"):
            code = body.get("error", {}).get("code", 100)
            raise DsmApiError(code=code, api_name="SYNO.API.Info")
        self.api_map = body.get("data", {})
        self._save_session()
        return self.api_map

    async def login(self, otp_code: Optional[str] = None) -> str:
        """Выполняет вход в DSM через `SYNO.API.Auth` и сохраняет `sid`."""
        if not self.api_map:
            try:
                await self.discover_apis()
            except Exception:
                pass

        auth_cgi, auth_ver = self._resolve_cgi_and_version("SYNO.API.Auth", default_version=6)
        if auth_cgi == "/webapi/entry.cgi" and "SYNO.API.Auth" not in self.api_map:
            auth_cgi = "/webapi/auth.cgi"

        params: dict[str, Any] = {
            "api": "SYNO.API.Auth",
            "version": str(auth_ver),
            "method": "login",
            "account": self.config.user,
            "passwd": self.config.password,
            "session": "SynoCLI",
            "format": "sid",
        }
        effective_otp = otp_code or self.config.otp_code
        if effective_otp:
            params["otp_code"] = effective_otp

        resp = await self.client.get(auth_cgi, params=params)
        resp.raise_for_status()
        body = resp.json()

        if not body.get("success"):
            code = body.get("error", {}).get("code", 400)
            self._clear_session()
            raise DsmAuthError(code=code, api_name="SYNO.API.Auth")

        self.sid = body["data"]["sid"]
        self._save_session()
        return str(self.sid)

    async def logout(self) -> None:
        """Завершает активную сессию на сервере DSM и очищает локальный кэш."""
        if not self.sid:
            return
        try:
            await self.client.get(
                "/webapi/auth.cgi",
                params={
                    "api": "SYNO.API.Auth",
                    "version": "6",
                    "method": "logout",
                    "session": "SynoCLI",
                    "_sid": self.sid,
                },
            )
        finally:
            self._clear_session()

    def _resolve_cgi_and_version(self, api_name: str, default_version: int = 1) -> tuple[str, int]:
        """Определяет путь CGI-обработчика и максимальную поддерживаемую версию API."""
        if api_name in self.api_map:
            info = self.api_map[api_name]
            path = info.get("path", "entry.cgi").lstrip("/")
            version = info.get("maxVersion", default_version)
            return f"/webapi/{path}", int(version)
        return "/webapi/entry.cgi", default_version

    async def request(
        self,
        api_name: str,
        method: str,
        version: Optional[int] = None,
        params: Optional[dict[str, Any]] = None,
        http_method: str = "GET",
        files: Optional[dict[str, Any]] = None,
        retry_auth: bool = True,
    ) -> dict[str, Any]:
        """Выполняет авторизованный запрос к Synology DSM Web API."""
        if not self.sid:
            await self.login()
        elif not self.api_map:
            try:
                await self.discover_apis()
            except Exception:
                pass

        cgi_path, resolved_ver = self._resolve_cgi_and_version(api_name, version or 1)
        use_version = resolved_ver if api_name in self.api_map else (version or resolved_ver)

        req_params: dict[str, Any] = {
            "api": api_name,
            "version": str(use_version),
            "method": method,
            "_sid": self.sid,
        }
        if params:
            for k, v in params.items():
                if isinstance(v, (dict, list, bool)):
                    req_params[k] = json.dumps(v)
                elif v is not None:
                    req_params[k] = v

        if http_method.upper() == "POST":
            if files:
                query_params = {
                    "api": api_name,
                    "version": str(use_version),
                    "method": method,
                    "_sid": self.sid,
                }
                form_data = {k: str(v) for k, v in (params or {}).items() if v is not None}
                resp = await self.client.post(
                    cgi_path, params=query_params, data=form_data, files=files
                )
            else:
                resp = await self.client.post(cgi_path, data=req_params)
        else:
            resp = await self.client.get(cgi_path, params=req_params)

        resp.raise_for_status()
        body = resp.json()

        if not body.get("success"):
            code = body.get("error", {}).get("code", 100)
            if code in (105, 106, 107, 119) and retry_auth:
                self._clear_session()
                await self.login()
                return await self.request(
                    api_name=api_name,
                    method=method,
                    version=version,
                    params=params,
                    http_method=http_method,
                    files=files,
                    retry_auth=False,
                )
            if code in (400, 401, 402, 403, 404):
                raise DsmAuthError(code=code, api_name=api_name)
            raise DsmApiError(code=code, api_name=api_name)

        return body.get("data", {})

    async def close(self) -> None:
        """Закрывает асинхронную HTTP-сессию клиента."""
        await self.client.aclose()
