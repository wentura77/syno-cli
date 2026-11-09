"""Базовый асинхронный HTTP-клиент для взаимодействия с Synology DSM Web API."""

import json
import ssl
from pathlib import Path
from typing import Any, Callable, Optional, cast

import httpx

from syno_cli.config import DEFAULT_SESSION_FILE, SynoSettings
from syno_cli.config import settings as default_settings
from syno_cli.constants import (
    AUTH_ERROR_CODES,
    DEFAULT_CONNECT_TIMEOUT_SEC,
    DEFAULT_TIMEOUT_SEC,
    DOWNLOAD_CHUNK_SIZE,
    DSM_ERR_BAD_CREDENTIALS,
    DSM_ERR_INVALID_SESSION,
    DSM_ERR_UNKNOWN,
    KEEPALIVE_EXPIRY_SEC,
    MAX_KEEPALIVE_CONNECTIONS,
    SESSION_EXPIRED_CODES,
    SESSION_NAME,
)
from syno_cli.exceptions import DsmApiError, DsmAuthError
from syno_cli.session_storage import BaseSessionStorage, get_session_storage


def _create_ssl_context() -> ssl.SSLContext:
    """Создает SSL-контекст для работы с самоподписанными сертификатами Synology DSM.

    Отключает проверку совпадения имени хоста и устаревшие протоколы SSLv2/SSLv3.

    Returns:
        ssl.SSLContext: Настроенный SSL-контекст.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.options |= getattr(ssl, "OP_NO_SSLv2", 0)
    ctx.options |= getattr(ssl, "OP_NO_SSLv3", 0)
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
            transport: Кастомный транспорт (для модульных тестов с `httpx.MockTransport`).
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
        limits = httpx.Limits(
            max_keepalive_connections=MAX_KEEPALIVE_CONNECTIONS,
            keepalive_expiry=KEEPALIVE_EXPIRY_SEC,
        )
        self.client = httpx.AsyncClient(
            base_url=self.config.base_url,
            verify=verify_ssl,
            timeout=httpx.Timeout(DEFAULT_TIMEOUT_SEC, connect=DEFAULT_CONNECT_TIMEOUT_SEC),
            limits=limits,
            headers={"Connection": "close"},
            transport=transport,
            follow_redirects=True,
        )
        self._load_session()

    def _load_session(self) -> None:
        """Загружает и расшифровывает сохраненный токен `sid` и карту API из хранилища."""
        try:
            data = self.storage.load()
            if not data:
                return
            self.sid = data.get("sid")
            api_map_raw = data.get("api_map", {})
            self.api_map = api_map_raw if isinstance(api_map_raw, dict) else {}
        except Exception:
            self.sid = None
            self.api_map = {}

    def _save_session(self) -> None:
        """Шифрует и сохраняет текущий токен `sid` и карту API в хранилище."""
        try:
            self.storage.save({"sid": self.sid, "api_map": self.api_map})
        except Exception:
            pass

    def clear_session(self) -> None:
        """Очищает токен сессии в памяти и удаляет зашифрованный кэш."""
        self.sid = None
        try:
            self.storage.clear()
        except Exception:
            pass

    async def ensure_authenticated(self) -> None:
        """Гарантирует наличие активной сессии `sid` и загруженной карты `api_map`."""
        if not self.sid:
            await self.login()
            return
        if not self.api_map:
            try:
                await self.discover_apis()
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
            code = int(body.get("error", {}).get("code", DSM_ERR_UNKNOWN))
            raise DsmApiError(code=code, api_name="SYNO.API.Info")

        data = body.get("data", {})
        self.api_map = data if isinstance(data, dict) else {}
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

        auth_cgi, auth_ver = self.resolve_endpoint("SYNO.API.Auth", default_version=6)
        if auth_cgi == "/webapi/entry.cgi" and "SYNO.API.Auth" not in self.api_map:
            auth_cgi = "/webapi/auth.cgi"

        params: dict[str, Any] = {
            "api": "SYNO.API.Auth",
            "version": str(auth_ver),
            "method": "login",
            "account": self.config.user,
            "passwd": self.config.password,
            "session": SESSION_NAME,
            "format": "sid",
        }
        effective_otp = otp_code or self.config.otp_code
        if effective_otp:
            params["otp_code"] = effective_otp

        resp = await self.client.get(auth_cgi, params=params)
        resp.raise_for_status()
        body = resp.json()

        if not body.get("success"):
            code = int(body.get("error", {}).get("code", DSM_ERR_BAD_CREDENTIALS))
            self.clear_session()
            raise DsmAuthError(code=code, api_name="SYNO.API.Auth")

        self.sid = str(body["data"]["sid"])
        self._save_session()
        return self.sid

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
                    "session": SESSION_NAME,
                    "_sid": self.sid,
                },
            )
        finally:
            self.clear_session()

    def resolve_endpoint(self, api_name: str, default_version: int = 1) -> tuple[str, int]:
        """Определяет путь CGI-обработчика и максимальную поддерживаемую версию API.

        Args:
            api_name: Имя интерфейса API (например, `SYNO.Docker.Container`).
            default_version: Версия по умолчанию, если API отсутствует в карте.

        Returns:
            tuple[str, int]: Кортеж `(путь_к_cgi, версия)`.
        """
        if api_name in self.api_map:
            info = self.api_map[api_name]
            path = str(info.get("path", "entry.cgi")).lstrip("/")
            version = int(info.get("maxVersion", default_version))
            return f"/webapi/{path}", version
        return "/webapi/entry.cgi", default_version

    @staticmethod
    def _serialize_params(params: Optional[dict[str, Any]]) -> dict[str, Any]:
        """Сериализует сложные типы параметров (словари, списки, булевы) в JSON-строки.

        Args:
            params: Исходный словарь параметров.

        Returns:
            dict[str, Any]: Подготовленный словарь параметров.
        """
        if not params:
            return {}
        serialized: dict[str, Any] = {}
        for key, value in params.items():
            if isinstance(value, (dict, list, bool)):
                serialized[key] = json.dumps(value)
            elif value is not None:
                serialized[key] = value
        return serialized

    def _auth_headers(self) -> Optional[dict[str, str]]:
        """Формирует заголовок Cookie с идентификатором текущей сессии.

        Returns:
            Optional[dict[str, str]]: Заголовок Cookie или None.
        """
        return {"Cookie": f"id={self.sid}"} if self.sid else None

    async def request(
        self,
        api_name: str,
        method: str,
        version: Optional[int] = None,
        params: Optional[dict[str, Any]] = None,
        http_method: str = "GET",
        files: Optional[dict[str, Any]] = None,
        timeout: Optional[httpx.Timeout] = None,
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
            timeout: Индивидуальный таймаут для тяжелых операций (например, Upload).
            retry_auth: Разрешить ли автоматический повторный вход при истечении `sid`.

        Returns:
            dict[str, Any]: Содержимое поля `data` успешного ответа DSM.

        Raises:
            DsmAuthError: При ошибке авторизации.
            DsmApiError: При любой прикладной ошибке API.
        """
        await self.ensure_authenticated()

        cgi_path, resolved_ver = self.resolve_endpoint(api_name, version or 1)
        use_version = (
            version if version is not None else (resolved_ver if api_name in self.api_map else 1)
        )
        headers = self._auth_headers()

        try:
            if http_method.upper() == "POST" and files:
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
                    headers=headers,
                    timeout=timeout or self.client.timeout,
                )
            elif http_method.upper() == "POST":
                req_params: dict[str, Any] = {
                    "api": api_name,
                    "version": str(use_version),
                    "method": method,
                    "_sid": self.sid,
                    **self._serialize_params(params),
                }
                resp = await self.client.post(
                    cgi_path,
                    data=req_params,
                    headers=headers,
                    timeout=timeout or self.client.timeout,
                )
            else:
                req_params = {
                    "api": api_name,
                    "version": str(use_version),
                    "method": method,
                    "_sid": self.sid,
                    **self._serialize_params(params),
                }
                resp = await self.client.get(
                    cgi_path,
                    params=req_params,
                    headers=headers,
                    timeout=timeout or self.client.timeout,
                )
        except OSError as exc:
            if retry_auth:
                self.clear_session()
                await self.login()
                return await self.request(
                    api_name=api_name,
                    method=method,
                    version=version,
                    params=params,
                    http_method=http_method,
                    files=files,
                    timeout=timeout,
                    retry_auth=False,
                )
            raise DsmApiError(
                code=DSM_ERR_INVALID_SESSION,
                api_name=api_name,
                details=f"Сервер NAS разорвал соединение ({exc})",
            ) from exc

        resp.raise_for_status()
        body = resp.json()

        if not body.get("success"):
            code = int(body.get("error", {}).get("code", DSM_ERR_UNKNOWN))
            if code in SESSION_EXPIRED_CODES and retry_auth:
                self.clear_session()
                await self.login()
                return await self.request(
                    api_name=api_name,
                    method=method,
                    version=version,
                    params=params,
                    http_method=http_method,
                    files=files,
                    timeout=timeout,
                    retry_auth=False,
                )
            if code in AUTH_ERROR_CODES:
                raise DsmAuthError(code=code, api_name=api_name)
            raise DsmApiError(code=code, api_name=api_name)

        data = body.get("data", {})
        return cast(dict[str, Any], data) if isinstance(data, dict) else {}

    async def stream_download(
        self,
        api_name: str,
        method: str,
        params: dict[str, Any],
        target_file: Path,
        default_version: int = 2,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        retry_auth: bool = True,
    ) -> Path:
        """Выполняет потоковое скачивание бинарного файла с проверкой JSON-ошибок DSM.

        Args:
            api_name: Имя API (например, `SYNO.FileStation.Download`).
            method: Метод API (`download`).
            params: Дополнительные параметры запроса.
            target_file: Локальный путь сохранения файла.
            default_version: Версия API по умолчанию.
            progress_callback: Коллбэк прогресса `(downloaded_bytes, total_bytes)`.
            retry_auth: Повторить ли запрос при истечении сессии.

        Returns:
            Path: Путь к сохраненному файлу.

        Raises:
            DsmApiError: Если вместо файла сервер вернул JSON-ошибку.
        """
        await self.ensure_authenticated()
        cgi_path, ver = self.resolve_endpoint(api_name, default_version)
        query_params = {
            "api": api_name,
            "version": str(ver),
            "method": method,
            "_sid": str(self.sid),
            **params,
        }

        async with self.client.stream(
            "GET", cgi_path, params=query_params, headers=self._auth_headers()
        ) as resp:
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "").lower()

            if "application/json" in content_type or "text/plain" in content_type:
                raw_bytes = await resp.aread()
                code = self._extract_stream_error_code(raw_bytes)
                if code is not None:
                    if code in SESSION_EXPIRED_CODES and retry_auth:
                        self.clear_session()
                        await self.login()
                        return await self.stream_download(
                            api_name=api_name,
                            method=method,
                            params=params,
                            target_file=target_file,
                            default_version=default_version,
                            progress_callback=progress_callback,
                            retry_auth=False,
                        )
                    raise DsmApiError(code=code, api_name=api_name)

                target_file.write_bytes(raw_bytes)
                if progress_callback:
                    progress_callback(len(raw_bytes), len(raw_bytes))
                return target_file

            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            with open(target_file, "wb") as file_out:
                async for chunk in resp.aiter_bytes(chunk_size=DOWNLOAD_CHUNK_SIZE):
                    file_out.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total)

        return target_file

    @staticmethod
    def _extract_stream_error_code(raw_bytes: bytes) -> Optional[int]:
        """Проверяет, является ли текстовый ответ JSON-ошибкой DSM API.

        Args:
            raw_bytes: Прочитанные байты ответа.

        Returns:
            Optional[int]: Код ошибки DSM или None, если это обычный текстовый файл.
        """
        try:
            body = json.loads(raw_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

        if isinstance(body, dict) and not body.get("success", True):
            return int(body.get("error", {}).get("code", DSM_ERR_UNKNOWN))
        return None

    async def close(self) -> None:
        """Закрывает асинхронную HTTP-сессию клиента."""
        await self.client.aclose()
