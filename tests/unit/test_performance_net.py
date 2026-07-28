"""Tests for atomic, bounded downloads in performance/_net.py."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import requests

from performance import _net


class _FakeResponse:
    def __init__(self, items=(), *, headers=None, status_code=200):
        self._items = items
        self.headers = headers or {}
        self.status_code = status_code

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    @property
    def is_redirect(self):
        return self.status_code in (301, 302, 303, 307, 308)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"status {self.status_code}")
        return None

    def iter_content(self, *, chunk_size):
        assert chunk_size == 64 * 1024
        for item in self._items:
            if isinstance(item, BaseException):
                raise item
            yield item


def _install_response(monkeypatch, response, *, expected_url="https://example.test/video.mp4"):
    _allow_public_resolution(monkeypatch)

    def fake_get(url, *, stream, timeout, allow_redirects=True):
        assert url == expected_url
        assert stream is True
        assert allow_redirects is False
        assert timeout == (_net.DEFAULT_CONNECT_TIMEOUT, _net.DEFAULT_READ_TIMEOUT)
        return response

    monkeypatch.setattr(_net.requests, "get", fake_get)


def _allow_public_resolution(monkeypatch, host="example.test", ip="93.184.216.34"):
    """Stub DNS so external HTTPS tests do not depend on real resolution."""
    monkeypatch.setattr(
        _net.socket,
        "getaddrinfo",
        lambda hostname, port, *a, **k: [
            (0, 0, 0, "", (ip if hostname == host else "127.0.0.1", port))
        ],
    )


def _temp_residue(destination: Path):
    return list(destination.parent.glob(".safe-download-*.tmp"))


@pytest.mark.parametrize(
    "stream_error",
    [
        requests.exceptions.Timeout("read timed out"),
        requests.exceptions.ConnectionError("connection reset"),
    ],
    ids=["timeout", "reset"],
)
def test_midstream_failure_preserves_existing_destination(
    tmp_path, monkeypatch, stream_error
):
    destination = tmp_path / "artifact.mp4"
    destination.write_bytes(b"known-good")
    _install_response(
        monkeypatch,
        _FakeResponse([b"partial-data", stream_error]),
    )

    result = _net.safe_download(
        "https://example.test/video.mp4",
        str(destination),
    )

    assert result is None
    assert destination.read_bytes() == b"known-good"
    assert _temp_residue(destination) == []


def test_failed_new_download_leaves_no_destination(tmp_path, monkeypatch):
    destination = tmp_path / "artifact.mp4"
    _install_response(
        monkeypatch,
        _FakeResponse(
            [
                b"partial-data",
                requests.exceptions.ConnectionError("connection reset"),
            ]
        ),
    )

    result = _net.safe_download(
        "https://example.test/video.mp4",
        str(destination),
    )

    assert result is None
    assert not destination.exists()
    assert _temp_residue(destination) == []


def test_success_atomically_replaces_and_returns_destination(tmp_path, monkeypatch):
    destination = tmp_path / "artifact.mp4"
    destination.write_bytes(b"known-good")
    _install_response(monkeypatch, _FakeResponse([b"new-", b"artifact"]))
    real_replace = _net.os.replace
    replace_observations = []

    def observing_replace(source, target):
        replace_observations.append(
            (Path(source).read_bytes(), Path(target).read_bytes())
        )
        real_replace(source, target)

    monkeypatch.setattr(_net.os, "replace", observing_replace)

    result = _net.safe_download(
        "https://example.test/video.mp4",
        str(destination),
    )

    assert result == str(destination)
    assert replace_observations == [(b"new-artifact", b"known-good")]
    assert destination.read_bytes() == b"new-artifact"
    assert _temp_residue(destination) == []


def test_success_preserves_existing_destination_mode(tmp_path, monkeypatch):
    destination = tmp_path / "artifact.mp4"
    destination.write_bytes(b"known-good")
    destination.chmod(0o640)
    _install_response(monkeypatch, _FakeResponse([b"new-artifact"]))

    result = _net.safe_download(
        "https://example.test/video.mp4",
        str(destination),
    )

    assert result == str(destination)
    assert destination.stat().st_mode & 0o777 == 0o640


@pytest.mark.parametrize(
    ("process_umask", "expected_mode"),
    [(0o077, 0o600), (0o002, 0o664)],
)
def test_new_destination_matches_open_mode_under_umask(
    tmp_path, monkeypatch, process_umask, expected_mode
):
    baseline = tmp_path / "baseline.mp4"
    destination = tmp_path / "download.mp4"
    _install_response(monkeypatch, _FakeResponse([b"new-artifact"]))

    previous_umask = os.umask(process_umask)
    try:
        with open(baseline, "wb") as f:
            f.write(b"prior-open-semantics")
        result = _net.safe_download(
            "https://example.test/video.mp4",
            str(destination),
        )
    finally:
        os.umask(previous_umask)

    assert result == str(destination)
    baseline_mode = baseline.stat().st_mode & 0o777
    destination_mode = destination.stat().st_mode & 0o777
    assert baseline_mode == expected_mode
    assert destination_mode == baseline_mode


def test_temp_file_is_in_destination_directory(tmp_path, monkeypatch):
    destination = tmp_path / "nested" / "artifact.mp4"
    destination.parent.mkdir()
    _install_response(monkeypatch, _FakeResponse([b"new-artifact"]))
    real_replace = _net.os.replace
    replace_parents = []

    def observing_replace(source, target):
        replace_parents.append((Path(source).parent, Path(target).parent))
        real_replace(source, target)

    monkeypatch.setattr(_net.os, "replace", observing_replace)

    result = _net.safe_download(
        "https://example.test/video.mp4",
        str(destination),
    )

    assert result == str(destination)
    assert replace_parents == [(destination.parent, destination.parent)]


def test_long_destination_name_does_not_expand_temp_prefix(tmp_path, monkeypatch):
    destination = tmp_path / f"{'a' * 240}.mp4"
    _install_response(monkeypatch, _FakeResponse([b"new-artifact"]))

    result = _net.safe_download(
        "https://example.test/video.mp4",
        str(destination),
    )

    assert result == str(destination)
    assert destination.read_bytes() == b"new-artifact"
    assert _temp_residue(destination) == []


def test_temp_name_collision_retries_without_overwriting(tmp_path, monkeypatch):
    destination = tmp_path / "artifact.mp4"
    colliding_temp = tmp_path / f".safe-download-{'0' * 16}.tmp"
    colliding_temp.write_bytes(b"belongs-to-another-download")
    tokens = iter(["0" * 16, "1" * 16])
    monkeypatch.setattr(_net.secrets, "token_hex", lambda size: next(tokens))
    _install_response(monkeypatch, _FakeResponse([b"new-artifact"]))

    result = _net.safe_download(
        "https://example.test/video.mp4",
        str(destination),
    )

    assert result == str(destination)
    assert destination.read_bytes() == b"new-artifact"
    assert colliding_temp.read_bytes() == b"belongs-to-another-download"


def test_fdopen_failure_after_closing_fd_removes_temp(tmp_path, monkeypatch):
    real_close = os.close

    def close_then_fail(fd, mode):
        real_close(fd)
        raise RuntimeError("fdopen failed after taking ownership")

    monkeypatch.setattr(_net.os, "fdopen", close_then_fail)

    with pytest.raises(
        RuntimeError,
        match="fdopen failed after taking ownership",
    ):
        _net._open_download_temp(str(tmp_path))

    assert list(tmp_path.glob(".safe-download-*.tmp")) == []


def test_empty_content_fails_without_replacing_destination(tmp_path, monkeypatch):
    destination = tmp_path / "artifact.mp4"
    destination.write_bytes(b"known-good")
    _install_response(monkeypatch, _FakeResponse())

    result = _net.safe_download(
        "https://example.test/video.mp4",
        str(destination),
    )

    assert result is None
    assert destination.read_bytes() == b"known-good"
    assert _temp_residue(destination) == []


def test_declared_size_overflow_fails_without_replacing_destination(
    tmp_path, monkeypatch
):
    destination = tmp_path / "artifact.mp4"
    destination.write_bytes(b"known-good")
    _install_response(
        monkeypatch,
        _FakeResponse([b"unused"], headers={"content-length": "6"}),
    )

    result = _net.safe_download(
        "https://example.test/video.mp4",
        str(destination),
        max_bytes=5,
    )

    assert result is None
    assert destination.read_bytes() == b"known-good"
    assert _temp_residue(destination) == []


def test_streamed_size_overflow_fails_without_replacing_destination(
    tmp_path, monkeypatch
):
    destination = tmp_path / "artifact.mp4"
    destination.write_bytes(b"known-good")
    _install_response(monkeypatch, _FakeResponse([b"1234", b"56"]))

    result = _net.safe_download(
        "https://example.test/video.mp4",
        str(destination),
        max_bytes=5,
    )

    assert result is None
    assert destination.read_bytes() == b"known-good"
    assert _temp_residue(destination) == []


def test_exactly_max_bytes_succeeds(tmp_path, monkeypatch):
    destination = tmp_path / "artifact.mp4"
    _install_response(
        monkeypatch,
        _FakeResponse(
            [b"12", b"345"],
            headers={"content-length": "5"},
        ),
    )

    result = _net.safe_download(
        "https://example.test/video.mp4",
        str(destination),
        max_bytes=5,
    )

    assert result == str(destination)
    assert destination.read_bytes() == b"12345"
    assert _temp_residue(destination) == []


def test_replace_failure_preserves_destination_and_removes_temp(
    tmp_path, monkeypatch
):
    destination = tmp_path / "artifact.mp4"
    destination.write_bytes(b"known-good")
    _install_response(monkeypatch, _FakeResponse([b"new-artifact"]))

    def failed_replace(source, target):
        raise OSError("replace failed")

    monkeypatch.setattr(_net.os, "replace", failed_replace)

    result = _net.safe_download(
        "https://example.test/video.mp4",
        str(destination),
    )

    assert result is None
    assert destination.read_bytes() == b"known-good"
    assert _temp_residue(destination) == []


@pytest.mark.parametrize(
    "blocked_url",
    [
        "https://127.0.0.1/secret",
        "https://10.0.0.5/secret",
        "https://169.254.169.254/latest/meta-data/",
        "https://metadata.google.internal/computeMetadata/v1/",
        "file:///etc/passwd",
        "http://example.test/video.mp4",
    ],
)
def test_ssrf_blocks_private_metadata_and_non_https(tmp_path, monkeypatch, blocked_url):
    destination = tmp_path / "artifact.mp4"
    destination.write_bytes(b"known-good")
    called = []

    def fail_if_called(*a, **k):
        called.append((a, k))
        raise AssertionError("requests.get must not run for blocked URLs")

    monkeypatch.setattr(_net.requests, "get", fail_if_called)

    result = _net.safe_download(blocked_url, str(destination))

    assert result is None
    assert destination.read_bytes() == b"known-good"
    assert called == []


def test_ssrf_blocks_hostname_resolving_to_loopback(tmp_path, monkeypatch):
    destination = tmp_path / "artifact.mp4"
    destination.write_bytes(b"known-good")
    monkeypatch.setattr(
        _net.socket,
        "getaddrinfo",
        lambda hostname, port, *a, **k: [
            (0, 0, 0, "", ("127.0.0.1", port))
        ],
    )
    called = []

    def fail_if_called(*a, **k):
        called.append(1)
        raise AssertionError("must not fetch")

    monkeypatch.setattr(_net.requests, "get", fail_if_called)

    result = _net.safe_download(
        "https://evil.example/video.mp4",
        str(destination),
    )

    assert result is None
    assert destination.read_bytes() == b"known-good"
    assert called == []


def test_redirect_to_private_ip_is_refused(tmp_path, monkeypatch):
    destination = tmp_path / "artifact.mp4"
    destination.write_bytes(b"known-good")
    _allow_public_resolution(monkeypatch)
    responses = iter(
        [
            _FakeResponse(
                status_code=302,
                headers={"Location": "https://127.0.0.1/internal"},
            ),
        ]
    )
    seen = []

    def fake_get(url, *, stream, timeout, allow_redirects=True):
        seen.append(url)
        assert allow_redirects is False
        return next(responses)

    monkeypatch.setattr(_net.requests, "get", fake_get)

    result = _net.safe_download(
        "https://example.test/video.mp4",
        str(destination),
    )

    assert result is None
    assert seen == ["https://example.test/video.mp4"]
    assert destination.read_bytes() == b"known-good"


def test_allow_http_permits_trusted_private_host(tmp_path, monkeypatch):
    destination = tmp_path / "artifact.mp4"
    response = _FakeResponse([b"pod-bytes"])

    def fake_get(url, *, stream, timeout, allow_redirects=True):
        assert url == "http://10.0.0.8:8188/view"
        assert allow_redirects is False
        return response

    monkeypatch.setattr(_net.requests, "get", fake_get)

    result = _net.safe_download(
        "http://10.0.0.8:8188/view",
        str(destination),
        allow_http=True,
    )

    assert result == str(destination)
    assert destination.read_bytes() == b"pod-bytes"
