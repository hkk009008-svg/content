"""R-VERIFY-TIER(B) xfail pin — discovery-wf_13f9d2f6-f93, confirmed[8].

BUG: W2:MAJOR:download-urllib-notimeout
  phase_c_ffmpeg.py:490,550,633,738,824,870,957 — all seven video-download sites call
  urllib.request.urlretrieve(url, path) with NO timeout argument, and there is no
  socket.setdefaulttimeout() anywhere in the module. A stalled CDN that sends data slowly
  will block the pipeline thread indefinitely; the except-Exception guard on each branch
  only fires for connection/DNS errors at the poll/submit phase, not for a slow-read CDN
  transfer already underway. Fix = set socket.setdefaulttimeout(N) before the first
  urlretrieve call (or wrap downloads in urllib.request.urlopen with a timeout and shutil.
  copyfileobj). When fixed the xfail xpasses (strict) -> delete this pin.

Source: logs/discovery-wf_13f9d2f6-f93.json confirmed[8]; refuters returned
  refuted=False (all seven bare call sites confirmed, no socket.setdefaulttimeout in repo).
"""

import ast
import pathlib

import pytest

_MODULE_PATH = pathlib.Path(__file__).parent.parent.parent / "phase_c_ffmpeg.py"

# ---------------------------------------------------------------------------
# Static source approach: the download sites are only reachable through the
# large generate_ai_video() dispatch function, so a behavioural monkeypatch
# would require constructing heavy API mocks for seven different engine paths.
# Instead we assert the FIXED state on the real source text — a genuine check
# against the live code, not a vacuous constant. (See brief: "source-assert is
# acceptable as long as it targets the REAL code.")
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "W2:MAJOR:download-urllib-notimeout phase_c_ffmpeg.py:490,550,633,738,824,870,957 "
        "urllib.request.urlretrieve called at 7 download sites with no timeout and no "
        "socket.setdefaulttimeout() anywhere in the module; a stalled CDN blocks the "
        "pipeline thread indefinitely. Fix = socket.setdefaulttimeout or urlopen+timeout "
        "wrapper before downloads; then this xpasses (strict) and the pin is removed."
    ),
)
def test_urlretrieve_download_sites_have_timeout_protection():
    """Assert the fixed state: a socket timeout guard exists in phase_c_ffmpeg.

    Today: no socket.setdefaulttimeout() call and no timeout-bearing urlopen
    wrapper exist in the module -> assertion fails -> XFAIL (expected failure).

    When fixed: the assertion passes -> strict xfail flips to XPASS -> delete pin.
    """
    source = _MODULE_PATH.read_text(encoding="utf-8")

    # Confirm the module still contains bare urlretrieve calls (defect still present).
    # If all 7 sites are removed/replaced, the xfail premise changes; document that.
    urlretrieve_count = source.count("urllib.request.urlretrieve")
    assert urlretrieve_count > 0, (
        "phase_c_ffmpeg.py contains no urllib.request.urlretrieve calls — "
        "if all download sites were replaced, re-scope this pin."
    )

    # The FIXED condition: at least one of these timeout mechanisms must be present.
    has_socket_default_timeout = "socket.setdefaulttimeout(" in source
    has_urlopen_with_timeout = (
        "urllib.request.urlopen(" in source and "timeout=" in source
    )

    assert has_socket_default_timeout or has_urlopen_with_timeout, (
        f"phase_c_ffmpeg.py has {urlretrieve_count} bare urllib.request.urlretrieve "
        "call(s) with no timeout protection: no socket.setdefaulttimeout() and no "
        "urlopen(timeout=...) wrapper found. A stalled CDN transfer blocks the pipeline "
        "thread indefinitely. (W2:MAJOR:download-urllib-notimeout)"
    )
