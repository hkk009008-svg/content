"""Network helpers — safe HTTP download with bounded size + host validation.

WHY THIS EXISTS
---------------
Several adapters in this package (act_two, viggle, live_portrait, driving_video)
download generated artifacts from URLs returned by external APIs (Runway,
Viggle) or from the internal ComfyUI worker. The original code used
`urllib.request.urlretrieve(url, path)` which:

  - Accepts ANY URL with no scheme check (could be `file://`, `ftp://`, etc.)
  - Has no size limit (a 50 GB response would happily write to disk)
  - Has no timeout (a hanging connection blocks the worker indefinitely)
  - Doesn't validate the host (could redirect to internal endpoints — SSRF)

`safe_download` is the single chokepoint that fixes all four for *external*
downloads. New external-API adapters should use this helper, not `urlretrieve`.

SSRF POLICY
-----------
When ``allow_http=False`` (default — untrusted external HTTPS), the helper:

  - Accepts only ``https``
  - Resolves the hostname and rejects loopback / private / link-local /
    multicast / reserved / unspecified / cloud-metadata addresses
  - Revalidates every redirect target the same way (manual redirect follow)

When ``allow_http=True`` (trusted internal ComfyUI), HTTP is permitted
and private/link-local addresses are allowed. Do not pass untrusted operator
URLs through ``allow_http=True``.
"""

from __future__ import annotations

import ipaddress
import json
import math
import os
import re
import secrets
import socket
import subprocess
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from typing import BinaryIO, Callable, Optional
from urllib.parse import urljoin, urlparse

import requests


# Reasonable default for video clips: 512 MB. 5-second 4K video at high bitrate
# is ~250 MB worst case; anything bigger than 512 MB is suspicious.
DEFAULT_MAX_BYTES = 512 * 1024 * 1024
DEFAULT_CONNECT_TIMEOUT = 20
DEFAULT_READ_TIMEOUT = 300
_TEMP_CREATE_ATTEMPTS = 10
_MAX_REDIRECTS = 5
_MIN_PINNED_ADAPTER_REQUESTS = (2, 32, 3)
# Well-known cloud metadata endpoints (AWS / GCP / Azure IMDS).
_BLOCKED_LITERAL_HOSTS = frozenset(
    {
        "metadata.google.internal",
        "metadata",
        "instance-data",
    }
)


def validate_image_artifact(
    path: str,
    *,
    expected_formats: tuple[str, ...] = ("JPEG", "PNG", "WEBP"),
    expected_dimensions: tuple[int, int] | None = None,
) -> Optional[str]:
    """Validate decodable image magic and optional exact dimensions."""

    try:
        from PIL import Image

        with Image.open(path) as image:
            image_format = (image.format or "").upper()
            dimensions = tuple(int(value) for value in image.size)
            image.verify()
    except Exception as exc:
        return f"image decode failed: {exc}"

    normalized_formats = {item.upper() for item in expected_formats}
    if image_format not in normalized_formats:
        return (
            f"image magic format {image_format or '<unknown>'!r} not in "
            f"{sorted(normalized_formats)!r}"
        )
    if expected_dimensions is not None and dimensions != expected_dimensions:
        return f"image dimensions {dimensions!r} != expected {expected_dimensions!r}"
    if dimensions[0] <= 0 or dimensions[1] <= 0:
        return f"invalid image dimensions {dimensions!r}"
    return None


def _ffprobe_artifact(path: str) -> tuple[dict | None, Optional[str]]:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"ffprobe unavailable or timed out: {exc}"
    if result.returncode != 0:
        return None, f"ffprobe rejected artifact: {result.stderr.strip()[:200]}"
    try:
        payload = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        return None, f"ffprobe returned invalid JSON: {exc}"
    if not isinstance(payload, dict):
        return None, "ffprobe result was not an object"
    return payload, None


def _positive_duration(payload: dict, stream: dict) -> bool:
    return _media_duration_seconds(payload, stream) is not None


def _media_duration_seconds(payload: dict, stream: dict) -> float | None:
    """Return the largest finite positive stream/container duration."""

    durations = []
    for raw in (
        stream.get("duration"),
        (payload.get("format") or {}).get("duration"),
    ):
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value) and value > 0:
            durations.append(value)
    return max(durations) if durations else None


def _decode_media_stream(path: str, stream_selector: str) -> Optional[str]:
    """Decode the complete selected stream and reject latent corruption.

    ``ffprobe`` proves container metadata, but it does not necessarily read all
    packets. A fast-start MP4 can therefore retain believable metadata after
    its media tail was truncated. Provider artifacts are not publishable until
    ffmpeg has decoded the complete required stream without an error.
    """
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-xerror",
                "-i",
                path,
                "-map",
                stream_selector,
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"ffmpeg decode unavailable or timed out: {exc}"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "decode failed").strip()[:300]
        return f"ffmpeg rejected media stream {stream_selector}: {detail}"
    return None


def validate_video_artifact(
    path: str,
    *,
    expected_dimensions: tuple[int, int] | None = None,
    min_dimensions: tuple[int, int] | None = None,
    max_dimensions: tuple[int, int] | None = None,
    max_pixels: int | None = None,
    max_duration_s: float | None = None,
) -> Optional[str]:
    """Require a bounded, decodable MP4-family video stream.

    Optional geometry and duration limits let untrusted upload boundaries use
    the same ffprobe + full-decode validation as provider downloads without a
    second metadata probe.
    """

    try:
        with open(path, "rb") as artifact:
            header = artifact.read(64)
    except OSError as exc:
        return f"video read failed: {exc}"
    if b"ftyp" not in header[4:32]:
        return "video is not an MP4-family container (missing ftyp magic)"

    payload, error = _ffprobe_artifact(path)
    if error is not None or payload is None:
        return error
    streams = payload.get("streams")
    if not isinstance(streams, list):
        return "ffprobe streams field is missing"
    videos = [stream for stream in streams if stream.get("codec_type") == "video"]
    if not videos:
        return "artifact has no video stream"
    stream = videos[0]
    try:
        dimensions = (int(stream.get("width") or 0), int(stream.get("height") or 0))
    except (TypeError, ValueError):
        return "video dimensions are invalid"
    if dimensions[0] <= 0 or dimensions[1] <= 0:
        return f"video dimensions are invalid: {dimensions!r}"
    if expected_dimensions is not None and dimensions != expected_dimensions:
        return f"video dimensions {dimensions!r} != expected {expected_dimensions!r}"
    if min_dimensions is not None and (
        dimensions[0] < min_dimensions[0] or dimensions[1] < min_dimensions[1]
    ):
        return f"video dimensions {dimensions!r} below minimum {min_dimensions!r}"
    if max_dimensions is not None and (
        dimensions[0] > max_dimensions[0] or dimensions[1] > max_dimensions[1]
    ):
        return f"video dimensions {dimensions!r} exceed maximum {max_dimensions!r}"
    if max_pixels is not None and dimensions[0] * dimensions[1] > max_pixels:
        return (
            f"video pixel count {dimensions[0] * dimensions[1]} "
            f"exceeds maximum {max_pixels}"
        )
    if not stream.get("codec_name"):
        return "video codec is missing"
    duration_s = _media_duration_seconds(payload, stream)
    if duration_s is None:
        return "video duration is missing or nonpositive"
    if max_duration_s is not None and duration_s > max_duration_s:
        return f"video duration {duration_s:.3f}s exceeds maximum {max_duration_s:.3f}s"
    return _decode_media_stream(path, "0:v:0")


def validate_audio_artifact(path: str) -> Optional[str]:
    """Require a decodable, nonempty audio stream with real channel metadata."""

    payload, error = _ffprobe_artifact(path)
    if error is not None or payload is None:
        return error
    streams = payload.get("streams")
    if not isinstance(streams, list):
        return "ffprobe streams field is missing"
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if not audio_streams:
        return "artifact has no audio stream"
    stream = audio_streams[0]
    try:
        sample_rate = int(stream.get("sample_rate") or 0)
        channels = int(stream.get("channels") or 0)
    except (TypeError, ValueError):
        return "audio sample-rate/channel metadata is invalid"
    if sample_rate <= 0 or channels <= 0:
        return (
            "audio sample-rate/channel metadata is nonpositive "
            f"({sample_rate} Hz, {channels} channels)"
        )
    if not stream.get("codec_name"):
        return "audio codec is missing"
    if not _positive_duration(payload, stream):
        return "audio duration is missing or nonpositive"
    return _decode_media_stream(path, "0:a:0")


def publish_validated_file(
    staged_path: str,
    dest_path: str,
    *,
    content_validator: Callable[[str], Optional[str]],
) -> Optional[str]:
    """Validate and atomically publish an already-written sibling temp file."""

    staged_abs = os.path.abspath(staged_path)
    dest_abs = os.path.abspath(dest_path)
    if staged_abs == dest_abs or os.path.dirname(staged_abs) != os.path.dirname(dest_abs):
        print("   [SAFE-PUBLISH] staged file must be a distinct destination sibling")
        return None
    try:
        if not os.path.isfile(staged_abs) or os.path.getsize(staged_abs) <= 0:
            print("   [SAFE-PUBLISH] staged artifact is missing or empty")
            return None
        refusal_reason = content_validator(staged_abs)
        if refusal_reason is not None:
            print(f"   [SAFE-PUBLISH] refusing content: {refusal_reason}")
            return None
        try:
            destination_mode = os.stat(dest_abs).st_mode & 0o777
        except FileNotFoundError:
            pass
        else:
            os.chmod(staged_abs, destination_mode)
        os.replace(staged_abs, dest_abs)
        return dest_path
    except OSError as exc:
        print(f"   [SAFE-PUBLISH] failed: {exc}")
        return None
    finally:
        if os.path.exists(staged_abs):
            try:
                os.remove(staged_abs)
            except OSError:
                pass


def atomic_publish_bytes(
    payload: bytes,
    dest_path: str,
    *,
    max_bytes: int,
    content_type: str = "",
    allowed_content_types: tuple[str, ...] | None = None,
    content_validator: Callable[[str], Optional[str]],
) -> Optional[str]:
    """Bound, validate, and atomically publish an in-memory response body."""

    if not isinstance(payload, bytes) or not payload:
        print("   [SAFE-PUBLISH] response body is empty or not bytes")
        return None
    if len(payload) > max_bytes:
        print(
            f"   [SAFE-PUBLISH] response body {len(payload)} exceeds max {max_bytes}"
        )
        return None
    if allowed_content_types is not None:
        actual = content_type.split(";", 1)[0].strip().lower()
        allowed = {item.strip().lower() for item in allowed_content_types}
        if actual not in allowed:
            print(
                f"   [SAFE-PUBLISH] refusing content-type {actual or '<missing>'!r}; "
                f"allowed={sorted(allowed)!r}"
            )
            return None

    dest_dir = os.path.dirname(dest_path) or "."
    os.makedirs(dest_dir, exist_ok=True)
    temp_file = None
    temp_path = None
    try:
        temp_file, temp_path = _open_download_temp(dest_dir)
        with temp_file:
            temp_file.write(payload)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        temp_file = None
        result = publish_validated_file(
            temp_path,
            dest_path,
            content_validator=content_validator,
        )
        if result is not None:
            temp_path = None
        return result
    except OSError as exc:
        print(f"   [SAFE-PUBLISH] failed: {exc}")
        return None
    finally:
        if temp_file is not None:
            try:
                temp_file.close()
            except OSError:
                pass
        if temp_path is not None:
            try:
                os.remove(temp_path)
            except FileNotFoundError:
                pass
            except OSError:
                pass


def atomic_publish_stream(
    chunks: Iterable[bytes],
    dest_path: str,
    *,
    max_bytes: int,
    content_validator: Callable[[str], Optional[str]],
) -> Optional[str]:
    """Bound, validate, and atomically publish a streamed response body."""

    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        print("   [SAFE-PUBLISH] max_bytes must be a positive integer")
        return None

    dest_dir = os.path.dirname(dest_path) or "."
    os.makedirs(dest_dir, exist_ok=True)
    temp_file = None
    temp_path = None
    try:
        temp_file, temp_path = _open_download_temp(dest_dir)
        written = 0
        with temp_file:
            for chunk in chunks:
                if not isinstance(chunk, bytes):
                    print("   [SAFE-PUBLISH] stream yielded a non-bytes chunk")
                    return None
                if not chunk:
                    continue
                written += len(chunk)
                if written > max_bytes:
                    print(
                        f"   [SAFE-PUBLISH] stream exceeded max bytes {max_bytes}; "
                        "aborting"
                    )
                    return None
                temp_file.write(chunk)

            if written == 0:
                print("   [SAFE-PUBLISH] refusing empty response")
                return None
            temp_file.flush()
            os.fsync(temp_file.fileno())
        temp_file = None

        result = publish_validated_file(
            temp_path,
            dest_path,
            content_validator=content_validator,
        )
        if result is not None:
            temp_path = None
        return result
    except (OSError, TypeError) as exc:
        print(f"   [SAFE-PUBLISH] failed: {exc}")
        return None
    finally:
        if temp_file is not None:
            try:
                temp_file.close()
            except OSError:
                pass
        if temp_path is not None:
            try:
                os.remove(temp_path)
            except FileNotFoundError:
                pass
            except OSError:
                pass


def _open_download_temp(dest_dir: str) -> tuple[BinaryIO, str]:
    """Exclusively create a short, sibling temp using normal open-file modes."""
    for _ in range(_TEMP_CREATE_ATTEMPTS):
        temp_path = os.path.join(
            dest_dir,
            f".safe-download-{secrets.token_hex(8)}.tmp",
        )
        try:
            fd = os.open(
                temp_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o666,
            )
        except FileExistsError:
            continue

        try:
            return os.fdopen(fd, "wb"), temp_path
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.remove(temp_path)
            except OSError:
                pass
            raise

    raise FileExistsError("could not allocate a unique download temp file")


def _ip_is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True when an address must not be contacted for untrusted downloads."""
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or not ip.is_global
    )


@dataclass(frozen=True)
class _PinnedHTTPSTarget:
    """One DNS-validated HTTPS hop bound to an exact numeric address."""

    hostname: str
    port: int
    ip_address: str
    host_header: str


def _download_target(
    url: str,
    *,
    allow_http: bool,
) -> tuple[_PinnedHTTPSTarget | None, Optional[str]]:
    """Validate one URL and resolve an untrusted HTTPS hop exactly once.

    The returned pin is intentionally absent for ``allow_http=True``: that
    mode is reserved for operator-configured internal services and preserves
    the historical direct ``requests.get`` behavior.  For the default
    untrusted path, every DNS answer is checked before the first safe address
    is selected.  The caller must connect to ``ip_address`` rather than
    resolving ``hostname`` a second time.
    """
    if not url:
        return None, "empty URL"

    try:
        parsed = urlparse(url)
        explicit_port = parsed.port
        port = explicit_port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        return None, f"refusing invalid URL authority: {exc}"
    allowed_schemes = ("https", "http") if allow_http else ("https",)
    if parsed.scheme not in allowed_schemes:
        return None, f"refusing scheme={parsed.scheme!r} (allowed={allowed_schemes})"
    if not parsed.hostname:
        return None, f"refusing URL without host: {url[:80]}"
    if parsed.username is not None or parsed.password is not None:
        return None, "refusing URL containing user information"

    try:
        hostname = parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError as exc:
        return None, f"refusing invalid internationalized host: {exc}"
    if not hostname:
        return None, "refusing empty normalized host"
    if hostname in _BLOCKED_LITERAL_HOSTS and not allow_http:
        return None, f"refusing blocked metadata host: {hostname}"

    # Literal IP in the URL — check directly (no DNS).
    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None

    if allow_http:
        # Trusted internal path: scheme + netloc already checked.
        return None, None

    if literal_ip is not None:
        if _ip_is_blocked(literal_ip):
            return None, f"refusing blocked address {literal_ip}"
        addresses = [str(literal_ip)]
    else:
        # Resolve exactly once. Every answer must be safe: accepting a mixed
        # public/private set would let connection-order or Happy Eyeballs pick
        # the prohibited address even if the first result looked public.
        try:
            addrinfo = socket.getaddrinfo(
                hostname,
                port,
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            return None, f"refusing unresolvable host {hostname!r}: {exc}"

        if not addrinfo:
            return None, f"refusing host with no addresses: {hostname}"

        addresses = []
        for entry in addrinfo:
            sockaddr = entry[4]
            try:
                resolved = ipaddress.ip_address(sockaddr[0])
            except (ValueError, IndexError, TypeError):
                return None, f"refusing unparseable resolved address {sockaddr!r}"
            if _ip_is_blocked(resolved):
                return None, (
                    f"refusing host {hostname} resolving to blocked address {resolved}"
                )
            normalized = str(resolved)
            if normalized not in addresses:
                addresses.append(normalized)

    # Preserve the original authority name in HTTP while using the normalized
    # hostname for SNI/certificate verification. Preserve an explicitly stated
    # port (and any non-default port); IPv6 literals require brackets in Host.
    host_for_header = (
        f"[{hostname}]"
        if literal_ip is not None and literal_ip.version == 6
        else hostname
    )
    host_header = (
        host_for_header
        if explicit_port is None and port == 443
        else f"{host_for_header}:{port}"
    )
    return (
        _PinnedHTTPSTarget(
            hostname=hostname,
            port=port,
            ip_address=addresses[0],
            host_header=host_header,
        ),
        None,
    )


def _validate_download_url(url: str, *, allow_http: bool) -> Optional[str]:
    """Compatibility wrapper returning only a refusal reason."""

    _target, reason = _download_target(url, allow_http=allow_http)
    return reason


def _require_pinned_https_adapter_contract() -> None:
    """Fail closed unless Requests honors the validated-IP adapter hook.

    ``HTTPAdapter.send`` only began dispatching connection selection through
    ``get_connection_with_tls_context`` in Requests 2.32.2.  Requests 2.32.3
    then fixed that hook's custom-SSL-context behavior.  A dependency resolver
    or stale runtime that supplies anything older would otherwise leave this
    adapter defined but silently bypass its pinned pool.
    """

    raw_version = str(getattr(requests, "__version__", ""))
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", raw_version)
    parsed_version = tuple(int(part) for part in match.groups()) if match else None
    hook = getattr(requests.adapters.HTTPAdapter, "get_connection_with_tls_context", None)
    if (
        parsed_version is None
        or parsed_version[0] != 2
        or parsed_version < _MIN_PINNED_ADAPTER_REQUESTS
        or not callable(hook)
    ):
        raise RuntimeError(
            "secure pinned HTTPS downloads require requests>=2.32.3,<3 "
            "with HTTPAdapter.get_connection_with_tls_context"
        )


class _PinnedHTTPSAdapter(requests.adapters.HTTPAdapter):
    """Connect one HTTPS request to a validated IP without weakening TLS.

    ``request.url`` deliberately retains the provider hostname. The pool host
    is the numeric pin, while ``server_hostname`` supplies SNI and
    ``assert_hostname`` keeps certificate verification bound to the original
    hostname. The HTTP ``Host`` header is also forced back to that authority.
    """

    def __init__(self, target: _PinnedHTTPSTarget):
        _require_pinned_https_adapter_contract()
        self._target = target
        super().__init__(max_retries=0)

    def add_headers(self, request, **kwargs) -> None:
        super().add_headers(request, **kwargs)
        request.headers["Host"] = self._target.host_header

    def get_connection_with_tls_context(
        self,
        request,
        verify,
        proxies=None,
        cert=None,
    ):
        if verify is False:
            raise requests.exceptions.SSLError(
                "pinned HTTPS downloads require certificate verification"
            )
        if proxies and any(proxies.values()):
            raise requests.exceptions.InvalidURL(
                "pinned HTTPS downloads do not permit proxies"
            )

        parsed = urlparse(request.url)
        request_hostname = (
            (parsed.hostname or "")
            .encode("idna")
            .decode("ascii")
            .lower()
            .rstrip(".")
        )
        request_port = parsed.port or 443
        if (
            parsed.scheme.lower() != "https"
            or request_hostname != self._target.hostname
            or request_port != self._target.port
        ):
            raise requests.exceptions.InvalidURL(
                "prepared request does not match its validated HTTPS pin"
            )

        _host_params, pool_kwargs = self.build_connection_pool_key_attributes(
            request,
            verify,
            cert,
        )
        pool_kwargs = dict(pool_kwargs)
        pool_kwargs["assert_hostname"] = self._target.hostname
        pool_kwargs["server_hostname"] = self._target.hostname
        return self.poolmanager.connection_from_host(
            host=self._target.ip_address,
            port=self._target.port,
            scheme="https",
            pool_kwargs=pool_kwargs,
        )


@contextmanager
def _pinned_https_get(
    url: str,
    target: _PinnedHTTPSTarget,
    *,
    stream: bool,
    timeout: tuple[float, float],
    allow_redirects: bool,
    headers: dict[str, str] | None,
):
    """Yield one response from a no-env, no-proxy, IP-pinned HTTPS session."""

    session = requests.Session()
    try:
        # Environment proxies would reconnect by hostname at the proxy and
        # defeat the local DNS pin. They can also bypass the direct connection
        # based on NO_PROXY. Disable the entire environment merge for this
        # security boundary and pass an explicit empty proxy map as a backstop.
        session.trust_env = False
        session.proxies.clear()
        session.mount("https://", _PinnedHTTPSAdapter(target))
        with session.get(
            url,
            stream=stream,
            timeout=timeout,
            allow_redirects=allow_redirects,
            headers=headers,
            proxies={},
        ) as response:
            yield response
    finally:
        session.close()


def safe_download(
    url: str,
    dest_path: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
    read_timeout: float = DEFAULT_READ_TIMEOUT,
    allow_http: bool = False,
    request_headers: dict[str, str] | None = None,
    allowed_content_types: tuple[str, ...] | None = None,
    content_validator: Callable[[str], Optional[str]] | None = None,
) -> Optional[str]:
    """Stream a URL to dest_path with safety guards. Returns dest_path on success, None on failure.

    Args:
        url: The URL to download. Must be https by default (http only when
            ``allow_http=True`` for trusted internal hosts).
        dest_path: Local file to write.
        max_bytes: Refuse if Content-Length exceeds this OR streamed bytes do.
        connect_timeout / read_timeout: requests-style timeouts (seconds).
        allow_http: When False (default), only https URLs are accepted and
            resolved addresses in private/loopback/link-local/multicast/
            reserved/cloud-metadata ranges are refused, including redirect
            targets. Set True only for trusted internal hosts (ComfyUI gateway,
            internal GPU workers) where private HTTP is expected.
        request_headers: Optional non-secret request headers required by an
            artifact CDN (for example a browser-compatible User-Agent).
        allowed_content_types: Optional exact MIME allowlist. Parameters such
            as ``; charset=...`` are ignored and comparison is case-insensitive.
            When supplied, a missing or mismatched ``Content-Type`` refuses the
            download before any destination is published.
        content_validator: Optional callback receiving the completed sibling
            temp path. Return ``None`` to accept it, or a refusal reason string.
            This runs before ``os.replace`` so callers can validate a container
            signature without exposing partial or mislabeled bytes at dest_path.

    Returns:
        The dest_path on success, None on any failure. Failures are logged
        with a [SAFE-DL] prefix so callers can grep traces.
    """
    current_url = url
    temp_path: Optional[str] = None
    try:
        for _ in range(_MAX_REDIRECTS + 1):
            target, reason = _download_target(current_url, allow_http=allow_http)
            if reason is not None:
                print(f"   [SAFE-DL] {reason}")
                return None

            if allow_http:
                request_context = requests.get(
                    current_url,
                    stream=True,
                    timeout=(connect_timeout, read_timeout),
                    allow_redirects=False,
                    headers=request_headers,
                )
            else:
                if target is None:
                    print("   [SAFE-DL] validated HTTPS target has no connection pin")
                    return None
                request_context = _pinned_https_get(
                    current_url,
                    target,
                    stream=True,
                    timeout=(connect_timeout, read_timeout),
                    allow_redirects=False,
                    headers=request_headers,
                )
            with request_context as r:
                if r.is_redirect or r.status_code in (301, 302, 303, 307, 308):
                    location = r.headers.get("Location")
                    if not location:
                        print("   [SAFE-DL] redirect without Location header")
                        return None
                    current_url = urljoin(current_url, location)
                    continue

                r.raise_for_status()
                if allowed_content_types is not None:
                    actual_content_type = (
                        r.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    )
                    normalized_allowed = {
                        item.strip().lower() for item in allowed_content_types
                    }
                    if actual_content_type not in normalized_allowed:
                        print(
                            "   [SAFE-DL] refusing content-type "
                            f"{actual_content_type or '<missing>'!r}; "
                            f"allowed={sorted(normalized_allowed)!r}"
                        )
                        return None
                advertised = int(r.headers.get("content-length") or 0)
                if advertised and advertised > max_bytes:
                    print(
                        f"   [SAFE-DL] content-length {advertised} exceeds max {max_bytes}"
                    )
                    return None

                written = 0
                dest_dir = os.path.dirname(dest_path) or "."
                os.makedirs(dest_dir, exist_ok=True)
                temp_file, temp_path = _open_download_temp(dest_dir)
                with temp_file as f:
                    for chunk in r.iter_content(chunk_size=64 * 1024):
                        if not chunk:
                            continue
                        written += len(chunk)
                        if written > max_bytes:
                            print(
                                f"   [SAFE-DL] stream exceeded max bytes {max_bytes}; aborting"
                            )
                            return None
                        f.write(chunk)

                if written == 0:
                    print("   [SAFE-DL] refusing empty response")
                    return None

                if content_validator is not None:
                    refusal_reason = content_validator(temp_path)
                    if refusal_reason is not None:
                        print(f"   [SAFE-DL] refusing content: {refusal_reason}")
                        return None

            try:
                destination_mode = os.stat(dest_path).st_mode & 0o777
            except FileNotFoundError:
                pass
            else:
                os.chmod(temp_path, destination_mode)
            os.replace(temp_path, dest_path)
            temp_path = None
            return dest_path

        print(f"   [SAFE-DL] exceeded max redirects ({_MAX_REDIRECTS})")
        return None
    except requests.exceptions.Timeout:
        print(f"   [SAFE-DL] timeout after connect={connect_timeout}s read={read_timeout}s")
        return None
    except Exception as e:
        print(f"   [SAFE-DL] failed: {e}")
        return None
    finally:
        if temp_path is not None:
            try:
                os.remove(temp_path)
            except FileNotFoundError:
                pass
            except OSError as e:
                print(f"   [SAFE-DL] failed to remove temp file: {e}")
