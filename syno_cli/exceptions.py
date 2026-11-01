"""Иерархия пользовательских исключений для работы с Synology DSM Web API."""

from typing import Optional

DSM_ERROR_CODES: dict[int, str] = {
    100: "Неизвестная ошибка (Unknown error)",
    101: "Не указаны обязательные параметры api, version или method",
    102: "Запрашиваемый интерфейс API не существует",
    103: "Запрашиваемый метод не существует",
    104: "Данная версия API не поддерживается",
    105: "Недостаточно прав у текущей сессии (Insufficient user privilege)",
    106: "Время ожидания сессии истекло (Session timeout)",
    107: "Сессия прервана дублирующим входом",
    119: "Невалидный идентификатор сессии (SID not found / Invalid session)",
    400: "Неверное имя пользователя или пароль",
    401: "Учетная запись отключена",
    402: "Доступ запрещен (Permission denied)",
    403: "Требуется двухфакторный код аутентификации (2FA OTP code required)",
    404: "Неверный код двухфакторной аутентификации (Invalid OTP code)",
    408: "Истек срок действия пароля",
}


class DsmApiError(Exception):
    """
    Базовое исключение ошибки ответа Synology DSM API.

    Attributes:
        code (int): Числовой код ошибки DSM.
        api_name (Optional[str]): Имя вызываемого интерфейса API.
        message (str): Человекочитаемое описание ошибки.
    """

    def __init__(self, code: int, api_name: Optional[str] = None, details: Optional[str] = None) -> None:
        self.code = code
        self.api_name = api_name
        base_msg = DSM_ERROR_CODES.get(code, f"Неизвестный код ошибки DSM ({code})")
        if api_name:
            base_msg = f"[{api_name}] Код {code}: {base_msg}"
        if details:
            base_msg = f"{base_msg} ({details})"
        self.message = base_msg
        super().__init__(self.message)


class DsmAuthError(DsmApiError):
    """Исключение ошибок аутентификации, авторизации или невалидной сессии."""


class DsmTaskNotFoundError(DsmApiError):
    """Исключение при отсутствии запрашиваемой задачи, контейнера или ВМ."""
