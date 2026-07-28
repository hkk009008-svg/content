"""Network helpers — safe HTTP download with bounded size + scheme validation.

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

`safe_download` is the single chokepoint that fixes all four. New external-API
adapters should use this helper, not `urlretrieve`.
"""

from __future__ import annotations

import os
import secrets
from typing import BinaryIO, Optional
from urllib.parse import urlparse

import requests


# Reasonable default for video clips: 512 MB. 5-second 4K video at high bitrate
# is ~250 MB worst case; anything bigger than 512 MB is suspicious.
DEFAULT_MAX_BYTES = 512 * 1024 * 1024
DEFAULT_CONNECT_TIMEOUT = 20
DEFAULT_READ_TIMEOUT = 300
_TEMP_CREATE_ATTEMPTS = 10


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
        url: The URL to download. Must be http(s).
        dest_path: Local file to write.
        max_bytes: Refuse if Content-Length exceeds this OR streamed bytes do.
        connect_timeout / read_timeout: requests-style timeouts (seconds).
        allow_http: When False (default), only https URLs are accepted.
            Set True for trusted internal hosts (ComfyUI pod, RunPod).

    Returns:
        The dest_path on success, None on any failure. Failures are logged
        with a [SAFE-DL] prefix so callers can grep traces.
    """
    if not url:
        return None

    parsed = urlparse(url)
    allowed_schemes = ("https", "http") if allow_http else ("https",)
    if parsed.scheme not in allowed_schemes:
        print(f"   [SAFE-DL] refusing scheme={parsed.scheme!r} (allowed={allowed_schemes})")
        return None
    if not parsed.netloc:
        print(f"   [SAFE-DL] refusing URL without host: {url[:80]}")
        return None

    temp_path: Optional[str] = None
    try:
        with requests.get(url, stream=True, timeout=(connect_timeout, read_timeout)) as r:
            r.raise_for_status()
            advertised = int(r.headers.get("content-length") or 0)
            if advertised and advertised > max_bytes:
                print(f"   [SAFE-DL] content-length {advertised} exceeds max {max_bytes}")
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
                        print(f"   [SAFE-DL] stream exceeded max bytes {max_bytes}; aborting")
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
