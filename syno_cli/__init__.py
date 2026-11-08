"""Synology DSM Python SDK & CLI."""

from syno_cli.client.base import BaseSynoClient
from syno_cli.client.core import SynoCoreClient
from syno_cli.client.docker import SynoDockerClient
from syno_cli.client.download_station import SynoDownloadStationClient
from syno_cli.client.file_station import SynoFileStationClient
from syno_cli.client.logs import SynoLogsClient
from syno_cli.client.vmm import SynoVmmClient
from syno_cli.config import SynoSettings, settings
from syno_cli.exceptions import DsmApiError, DsmAuthError
from syno_cli.facade import SynoDSM

__all__ = [
    "SynoDSM",
    "BaseSynoClient",
    "SynoCoreClient",
    "SynoFileStationClient",
    "SynoDockerClient",
    "SynoLogsClient",
    "SynoDownloadStationClient",
    "SynoVmmClient",
    "SynoSettings",
    "settings",
    "DsmApiError",
    "DsmAuthError",
]
