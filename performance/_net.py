"""Network helpers — safe HTTP download with bounded size + host validation.

WHY THIS EXISTS
---------------
Several adapters in this package (act_one, viggle, live_portrait, driving_video)
download generated artifacts from URLs returned by external APIs (Runway,
Viggle) or from the internal ComfyUI pod. The original code used
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

When ``allow_http=True`` (trusted internal ComfyUI / RunPod), HTTP is permitted
and private/link-local addresses are allowed. Do not pass untrusted operator
URLs through ``allow_http=True``.
"""

from __future__ import annotations

import ipaddress
import os
import secrets
import socket
from typing import BinaryIO, Optional
from urllib.parse import urljoin, urlparse

import requests


# Reasonable default for video clips: 512 MB. 5-second 4K video at high bitrate
# is ~250 MB worst case; anything bigger than 512 MB is suspicious.
DEFAULT_MAX_BYTES = 512 * 1024 * 1024
DEFAULT_CONNECT_TIMEOUT = 20
DEFAULT_READ_TIMEOUT = 300
_TEMP_CREATE_ATTEMPTS = 10
_MAX_REDIRECTS = 5
# Well-known cloud metadata endpoints (AWS / GCP / Azure IMDS).
_BLOCKED_LITERAL_HOSTS = frozenset(
    {
        "metadata.google.internal",
        "metadata",
        "instance-data",
    }
)


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
    )


def _validate_download_url(url: str, *, allow_http: bool) -> Optional[str]:
    """Return None when URL is acceptable; otherwise a refusal reason string."""
    if not url:
        return "empty URL"

    parsed = urlparse(url)
    allowed_schemes = ("https", "http") if allow_http else ("https",)
    if parsed.scheme not in allowed_schemes:
        return f"refusing scheme={parsed.scheme!r} (allowed={allowed_schemes})"
    if not parsed.hostname:
        return f"refusing URL without host: {url[:80]}"

    hostname = parsed.hostname.lower().rstrip(".")
    if hostname in _BLOCKED_LITERAL_HOSTS and not allow_http:
        return f"refusing blocked metadata host: {hostname}"

    # Literal IP in the URL — check directly (no DNS).
    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None

    if allow_http:
        # Trusted internal path: scheme + netloc already checked.
        return None

    if literal_ip is not None:
        if _ip_is_blocked(literal_ip):
            return f"refusing blocked address {literal_ip}"
        return None

    # Resolve hostname and reject any answer in a prohibited range (DNS rebinding).
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        addrinfo = socket.getaddrinfo(
            hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        return f"refusing unresolvable host {hostname!r}: {exc}"

    if not addrinfo:
        return f"refusing host with no addresses: {hostname}"

    for entry in addrinfo:
        sockaddr = entry[4]
        try:
            resolved = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            return f"refusing unparseable resolved address {sockaddr[0]!r}"
        if _ip_is_blocked(resolved):
            return f"refusing host {hostname} resolving to blocked address {resolved}"
    return None


def safe_download(
    url: str,
    dest_path: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
    read_timeout: float = DEFAULT_READ_TIMEOUT,
    allow_http: bool = False,
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
            targets. Set True only for trusted internal hosts (ComfyUI pod,
            RunPod) where private HTTP is expected.

    Returns:
        The dest_path on success, None on any failure. Failures are logged
        with a [SAFE-DL] prefix so callers can grep traces.
    """
    current_url = url
    temp_path: Optional[str] = None
    try:
        for _ in range(_MAX_REDIRECTS + 1):
            reason = _validate_download_url(current_url, allow_http=allow_http)
            if reason is not None:
                print(f"   [SAFE-DL] {reason}")
                return None

            with requests.get(
                current_url,
                stream=True,
                timeout=(connect_timeout, read_timeout),
                allow_redirects=False,
            ) as r:
                if r.is_redirect or r.status_code in (301, 302, 303, 307, 308):
                    location = r.headers.get("Location")
                    if not location:
                        print("   [SAFE-DL] redirect without Location header")
                        return None
                    current_url = urljoin(current_url, location)
                    continue

                r.raise_for_status()
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
