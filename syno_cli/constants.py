"""Глобальные константы, коды протокола DSM и параметры по умолчанию."""

from enum import IntEnum
from typing import Final

# Сеть и HTTP-соединения
DEFAULT_HTTPS_PORT: Final[int] = 5001
DEFAULT_HTTP_PORT: Final[int] = 5000
DEFAULT_TIMEOUT_SEC: Final[float] = 120.0
DEFAULT_CONNECT_TIMEOUT_SEC: Final[float] = 15.0
UPLOAD_WRITE_TIMEOUT_SEC: Final[float] = 3600.0
UPLOAD_POOL_TIMEOUT_SEC: Final[float] = 30.0
KEEPALIVE_EXPIRY_SEC: Final[float] = 5.0
MAX_KEEPALIVE_CONNECTIONS: Final[int] = 0

# Размеры буферов потоковой передачи
DOWNLOAD_CHUNK_SIZE: Final[int] = 65_536  # 64 KB
UPLOAD_CHUNK_SIZE: Final[int] = 1_048_576  # 1 MB

# Криптография и хранение сессий
PBKDF2_ITERATIONS: Final[int] = 100_000
PBKDF2_KEY_LENGTH: Final[int] = 32
SECURE_FILE_PERMISSIONS: Final[int] = 0o600
SESSION_NAME: Final[str] = "SynoCLI"

# Коды ошибок Synology DSM Web API
DSM_ERR_UNKNOWN: Final[int] = 100
DSM_ERR_API_NOT_EXISTS: Final[int] = 102
DSM_ERR_INVALID_SESSION: Final[int] = 119
DSM_ERR_BAD_CREDENTIALS: Final[int] = 400

SESSION_EXPIRED_CODES: Final[frozenset[int]] = frozenset({105, 106, 107, 119})
AUTH_ERROR_CODES: Final[frozenset[int]] = frozenset({400, 401, 402, 403, 404, 408})

# Единицы времени и объемов данных
BYTES_IN_KB: Final[float] = 1024.0
SECONDS_IN_MINUTE: Final[int] = 60
SECONDS_IN_HOUR: Final[int] = 3600
SECONDS_IN_DAY: Final[int] = 86_400

# Параметры виртуализации (VMM) и Docker по умолчанию
DEFAULT_VMM_CPU_WEIGHT: Final[int] = 256
DEFAULT_VMM_RAM_MB: Final[int] = 1024
DEFAULT_VMM_DISK_GB: Final[int] = 20
DEFAULT_VMM_DEV_WEIGHT: Final[int] = 3
DEFAULT_VMM_VNIC_VIRTIO: Final[int] = 1
DEFAULT_LOG_LINES: Final[int] = 50
DEFAULT_DOCKER_LOG_TAIL: Final[int] = 100


class ExitCode(IntEnum):
    """Коды завершения процесса CLI."""

    SUCCESS = 0
    AUTH_ERROR = 1
    API_ERROR = 2
    VALIDATION_ERROR = 3
    NETWORK_ERROR = 4
    UNEXPECTED_ERROR = 5
