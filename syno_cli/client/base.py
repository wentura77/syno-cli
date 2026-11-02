"""Базовый асинхронный HTTP-клиент для взаимодействия с Synology DSM Web API."""

import json
from pathlib import Path
import ssl
from typing import Any, Optional
import httpx

from syno_cli.config import DEFAULT_SESSION_FILE, SynoSettings, settings as default_settings
from syno_cli.exceptions import DsmApiError, DsmAuthError
from syno_cli.session_storage import BaseSessionStorage, get_session_storage


def _create_ssl_context() -> ssl.SSLContext:
    """Создает SSL-контекст для работы с самоподписанными сертификатами Synology DSM.

    Returns:
        ssl.SSLContext: Настроенный SSL-контекст без проверки имени хоста.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


class BaseSynoClient:
    """Базовый клиент Synology DSM Web API с шифрованием сессии.

    Отвечает за:
    - обнаружение доступных эндпоинтов через `SYNO.API.Info`;
    - аутентификацию через `SYNO.API.Auth` с поддержкой 2FA (OTP);
    - защищенное кэширование токена сессии (`sid`) и карты API в `user_cache_dir`;
    - автоматический перелогин при истечении сессии (коды 105, 106, 107, 119).
    """

    def __init__(
        self,
        config: Optional[SynoSettings] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        session_backend: Optional[str] = None,
    ) -> None:
        """Инициализирует базовый клиент Synology и загружает зашифрованную сессию.

        Args:
            config: Объект настроек подключения.
            transport: Кастомный транспорт (для unit-тестов с `httpx.MockTransport`).
            session_backend: Принудительный выбор бэкенда (`'file'`, `'keyring'`, `'auto'`).
        """
        self.config = config or default_settings
        self.sid: Optional[str] = None
        self.api_map: dict[str, dict[str, Any]] = {}
        self._transport = transport

        # Если в тестах передан кастомный путь session_file, используем файловый бэкенд
        custom_file_override = self.config.session_file != DEFAULT_SESSION_FILE
        effective_backend = (
            session_backend
            if session_backend is not None
            else ("file" if custom_file_override else self.config.session_backend)
        )
        self.storage: BaseSessionStorage = get_session_storage(
            backend=effective_backend,
            file_path=Path(self.config.session_file),
        )

        verify_ssl: Any = _create_ssl_context() if self.config.secure else False
        self.client = httpx.AsyncClient(
            base_url=self.config.base_url,
            verify=verify_ssl,
            timeout=httpx.Timeout(120.0, connect=15.0),
            transport=transport,
            follow_redirects=True,
        )
        self._load_session()

    def _load_session(self) -> None:
        """Загружает и расшифровывает сохраненный токен `sid` и карту API из хранилища."""
        try:
            data = self.storage.load()
            if data:
                self.sid = data.get("sid")
                api_map_raw = data.get("api_map", {})
                self.api_map = api_map_raw if isinstance(api_map_raw, dict) else {}
        except Exception:
            self.sid = None
            self.api_map = {}

    def _save_session(self) -> None:
        """Шифрует и сохраняет текущий токен `sid` и карту API в хранилище."""
        try:
            payload: dict[str, Any] = {"sid": self.sid, "api_map": self.api_map}
            self.storage.save(payload)
        except Exception:
            pass

    def _clear_session(self) -> None:
        """Очищает токен сессии в памяти и удаляет зашифрованный кэш."""
        self.sid = None
        try:
            self.storage.clear()
        except Exception:
            pass

    async def discover_apis(self) -> dict[str, dict[str, Any]]:
        """Запрашивает карту поддерживаемых API и их CGI-путей через `SYNO.API.Info`.

        Returns:
            dict[str, dict[str, Any]]: Словарь описания API интерфейсов DSM.

        Raises:
            DsmApiError: При ошибке выполнения запроса к DSM.
        """
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
        """Выполняет вход в DSM через `SYNO.API.Auth` и сохраняет зашифрованный `sid`.

        Args:
            otp_code: Одноразовый код 2FA (если включена двухфакторная защита).

        Returns:
            str: Полученный идентификатор сессии (`sid`).

        Raises:
            DsmAuthError: Если логин, пароль или OTP-код неверны.
        """
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
        """Определяет путь CGI-обработчика и максимальную поддерживаемую версию API.

        Args:
            api_name: Имя интерфейса API (например, `SYNO.Docker.Container`).
            default_version: Версия по умолчанию, если API отсутствует в карте.

        Returns:
            tuple[str, int]: Кортеж `(путь_к_cgi, версия)`.
        """
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
        """Выполняет авторизованный запрос к Synology DSM Web API.

        Args:
            api_name: Имя вызываемого интерфейса API.
            method: Вызываемый метод интерфейса.
            version: Версия API (определяется автоматически, если None).
            params: Дополнительные параметры вызова.
            http_method: HTTP-метод (`GET` или `POST`).
            files: Файлы для multipart/form-data загрузки.
            retry_auth: Разрешить ли автоматический повторный вход при протухании `sid`.

        Returns:
            dict[str, Any]: Содержимое поля `data` успешного ответа DSM.

        Raises:
            DsmAuthError: При ошибке авторизации.
            DsmApiError: При любой прикладной ошибке API.
        """
        if not self.sid:
            await self.login()
        elif not self.api_map:
            try:
                await self.discover_apis()
            except Exception:
                pass

        cgi_path, resolved_ver = self._resolve_cgi_and_version(api_name, version or 1)
        use_version = (
            version
            if version is not None
            else (resolved_ver if api_name in self.api_map else 1)
        )

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

        req_headers = {"Cookie": f"id={self.sid}"} if self.sid else None

        if http_method.upper() == "POST":
            if files:
                query_params = {
                    "api": api_name,
                    "version": str(use_version),
                    "method": method,
                    "_sid": str(self.sid),
                }
                form_data = {k: str(v) for k, v in (params or {}).items() if v is not None}
                resp = await self.client.post(
                    cgi_path,
                    params=query_params,
                    data=form_data,
                    files=files,
                    headers=req_headers,
                )
            else:
                resp = await self.client.post(cgi_path, data=req_params, headers=req_headers)
        else:
            resp = await self.client.get(cgi_path, params=req_params, headers=req_headers)

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
