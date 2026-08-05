"""Resolve the guarded ComfyUI performance-worker boundary.

Dedicated workers retain their legacy contract.  One endpoint may represent
both image and performance roles only when both settings use the same strong
credential and runtime performs the authenticated capability-superset proof;
static URL equality alone never establishes readiness.
"""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
from urllib.parse import urlsplit

from config.settings import settings


@dataclass(frozen=True)
class PerformanceComfyUIEndpoint:
    server_url: str
    api_key: str
    dedicated: bool = True
    shared_endpoint: bool = False
    configuration_error: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.server_url)

    @property
    def usable(self) -> bool:
        return self.configured and not self.configuration_error

    @property
    def requires_capability_proof(self) -> bool:
        return self.shared_endpoint


def _is_loopback(hostname: str) -> bool:
    if hostname.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _configuration_error(server_url: str, api_key: str) -> str:
    try:
        parsed = urlsplit(server_url)
    except ValueError:
        return "invalid_url"
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        return "invalid_url"
    lowered = api_key.lower()
    if (
        len(api_key) < 32
        or lowered.startswith("bearer ")
        or lowered in {"changeme", "replace-me", "placeholder"}
    ):
        return "invalid_token"
    # Source media and bearer credentials must never cross a plaintext LAN.
    # The supported local topology is HTTP through a Mac loopback SSH tunnel;
    # direct remote endpoints must terminate HTTPS.
    if parsed.scheme == "http" and not _is_loopback(parsed.hostname):
        return "insecure_transport"
    return ""


def _endpoint_identity(server_url: str) -> tuple[str, str, int, str] | None:
    try:
        parsed = urlsplit(server_url)
        if not parsed.hostname or parsed.scheme not in {"http", "https"}:
            return None
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return None
    hostname = parsed.hostname.lower()
    if _is_loopback(hostname):
        # ``localhost``, 127.0.0.0/8, and ::1 can all name the same listener.
        # Canonicalize them so alternate loopback spellings cannot disguise a
        # shared image/performance endpoint.
        hostname = "loopback"
    return (
        parsed.scheme.lower(),
        hostname,
        port,
        parsed.path.rstrip("/"),
    )


def resolve_performance_comfyui(
    settings_obj: object = settings,
) -> PerformanceComfyUIEndpoint:
    """Return the dedicated performance URL/token without mixing credentials."""

    dedicated_url = (
        getattr(settings_obj, "performance_comfyui_server_url", "") or ""
    ).strip().rstrip("/")
    api_key = (
        getattr(settings_obj, "performance_comfyui_api_key", "") or ""
    ).strip()
    image_url = (
        getattr(settings_obj, "comfyui_server_url", "") or ""
    ).strip().rstrip("/")
    image_api_key = (
        getattr(settings_obj, "comfyui_api_key", "") or ""
    ).strip()
    shared_endpoint = bool(
        dedicated_url
        and image_url
        and _endpoint_identity(dedicated_url) == _endpoint_identity(image_url)
    )
    configuration_error = (
        _configuration_error(dedicated_url, api_key) if dedicated_url else ""
    )
    if shared_endpoint and image_api_key != api_key:
        configuration_error = "shared_credentials"
    return PerformanceComfyUIEndpoint(
        server_url=dedicated_url,
        api_key=api_key,
        dedicated=not shared_endpoint,
        shared_endpoint=shared_endpoint,
        configuration_error=configuration_error,
    )
