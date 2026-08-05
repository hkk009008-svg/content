"""Shared pytest fixtures for the content test suite."""

import os
import subprocess
import sys
import tempfile
import types

import pytest


# ---------------------------------------------------------------------------
# Placeholder credentials — keep the suite hermetic
# ---------------------------------------------------------------------------
# Runs at conftest IMPORT time, which is before any test module (and therefore
# before ``config.settings``) is imported. That ordering is load-bearing:
# ``config/settings.py`` builds a frozen ``Settings`` singleton at import behind
# ``@lru_cache(maxsize=1)``, so a value set after that point would be ignored.
#
# WHY this exists. Production code changes SHAPE when a credential is absent,
# and a surprising number of fully-mocked unit tests depend on the credentialed
# shape without ever saying so:
#   * phase_c_vision.validate_shot_quality_vision returns a default
#     ``{"score": 7, "pass": True}`` before it ever constructs the (mocked)
#     OpenAI client, so ``assert result["score"] == 8`` sees 7.
#   * domain.provider_catalog.build_runtime_snapshot reads these keys off the
#     settings singleton, so with none present EVERY video engine reports
#     ``runtime_unavailable`` and the mocked client is never called at all
#     (``call_args`` is None -> "cannot unpack non-iterable NoneType").
# Without this block those tests fail on a bare bootstrap and pass only because
# the developer happens to have a gitignored ``.env`` — i.e. the suite's result
# depended on a private file. That is the defect; the red was the symptom.
#
# These are NOT a way to reach a live provider. Every affected test mocks its
# client, so the value is never sent anywhere; the strings are deliberately
# self-describing so that if one ever DID escape to a real API the failure
# reads as an obvious test placeholder rather than a mysterious auth error.
#
# ``setdefault`` (not assignment) so a real environment always wins. The
# settings loader uses ``override=False``, so these hermetic test placeholders
# also outrank any developer-local ``.env`` values during pytest.
_PLACEHOLDER_CREDENTIAL_ENV = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "KLING_ACCESS_KEY",
    "KLING_SECRET_KEY",
    "FAL_KEY",
    "LTX_API_KEY",
    "RUNWAYML_API_SECRET",
    "ELEVENLABS_API_KEY",
    "CARTESIA_API_KEY",
    "STABILITY_API_KEY",
    "SUNO_API_KEY",
    "VIGGLE_API_KEY",
    "FIRECRAWL_API_KEY",
    "TAVILY_API_KEY",
)

for _name in _PLACEHOLDER_CREDENTIAL_ENV:
    os.environ.setdefault(_name, f"test-placeholder-not-a-real-{_name}")
del _name


# ---------------------------------------------------------------------------
# Custom markers for tiered test execution
# ---------------------------------------------------------------------------

def pytest_configure(config):
    """Register custom markers so pytest doesn't warn about them."""
    config.addinivalue_line("markers", "e2e: end-to-end tests requiring a GPU worker + API keys")
    config.addinivalue_line("markers", "grid_search: parameter grid search tests (long-running)")

# ---------------------------------------------------------------------------
# pedalboard SIGILL containment (host-CPU lottery, not a test bug)
# ---------------------------------------------------------------------------
#
# audio/effects.py hard-imports `pedalboard` at module scope by design (its
# own docstring: "no graceful fallback if the import fails"). Collecting
# ANY test that transitively imports web_server -> cinema_pipeline ->
# audio.music -> audio.effects therefore triggers
# `from pedalboard_native import *` (pedalboard/__init__.py:25).
#
# Spotify's published Linux x86_64 wheel is compiled with `-march=native` on
# whichever GH Actions host built it, with NO runtime CPU dispatch/fallback
# (spotify/pedalboard CMakeLists.txt ~L203-216; its own comment: "use a
# portable baseline for CI builds to avoid 'Illegal instruction' errors...
# on different runner hardware" -- gated behind USE_PORTABLE_SIMD, which
# their own wheel-publishing job does not set). Confirmed still open
# upstream: github.com/spotify/pedalboard#454 ("Pedalboard 0.9.21 causes
# 'Illegal Instructions' on linux"). Since PyPI ships wheels only (no sdist
# for any recent release), we cannot rebuild from source with the safe flag
# either. On a runner host whose CPU lacks whatever instruction the build
# host had, the import SIGILLs -- a hardware trap, NOT a catchable Python
# exception -- killing the whole pytest process before collection can even
# start. Measured on main: 6 of 8 sampled CI runs died this way (the pinned
# version, 0.9.24, was identical across crashing and clean runs -- it's the
# runtime host that varies, not the wheel).
#
# No test in this suite exercises pedalboard's real DSP: test_effects.py
# either mocks `apply_pedalboard_chain` itself, or drives the
# empty-effects/all-unknown-type inputs that make apply_pedalboard_chain
# return early (audio/effects.py:176-198) before touching any real
# Pedalboard/Reverb/etc. object. So shimming the module changes no
# currently-passing test's behavior.
#
# Because SIGILL can't be caught, we can't try the real import in-process
# and fall back on failure. Instead we probe in a disposable child process
# (whose death can't take down pytest) and only shim `sys.modules` --
# before any test module is collected -- when that probe shows the import
# is fatal on this exact host. When the real import is fine, this is a
# complete no-op and every test runs against the genuine library exactly as
# today. Any probe-machinery hiccup (e.g. a timeout) falls back to "assume
# the real import is fine", so this can only ever turn a crash into a
# clean pass or a clean skip -- never make anything worse than today.


def _pedalboard_import_is_fatal_here() -> bool:
    """True if `import pedalboard` would SIGILL/crash on this host's CPU."""
    try:
        probe = subprocess.run(
            [sys.executable, "-c", "import pedalboard"],
            capture_output=True,
            timeout=60,
        )
    except Exception:
        # Probe machinery itself is broken (no interpreter, timeout, ...) --
        # don't let that mask the real library; let the real import proceed
        # and fail/succeed on its own merits, same as before this fixture.
        return False
    return probe.returncode != 0


class _UnusablePedalboardSymbol:
    """Stand-in for a real pedalboard class/function on a CI host whose CPU
    can't run Spotify's published wheel. Constructing (or calling) it fails
    LOUDLY with an explanation instead of silently returning a Mock, so a
    hypothetical future test that needs real pedalboard DSP gets a clear
    signal instead of a wrong-but-passing result."""

    def __init__(self, *args, **kwargs):
        raise RuntimeError(
            "pedalboard's native extension does not load on this CI "
            "runner's CPU (upstream spotify/pedalboard#454 -- see "
            "tests/conftest.py). This is a containment stub, not the real "
            "library; a test that needs real pedalboard DSP cannot run in "
            "this environment."
        )


def _install_pedalboard_stub() -> None:
    stub = types.ModuleType("pedalboard")
    for name in (
        "Pedalboard", "Reverb", "Compressor", "Gain", "Delay",
        "HighpassFilter", "LowpassFilter", "Chorus", "Distortion",
    ):
        setattr(stub, name, _UnusablePedalboardSymbol)

    def _load_plugin(*args, **kwargs):
        raise RuntimeError(
            "pedalboard.load_plugin is unavailable -- native extension "
            "does not load on this CI runner's CPU (see tests/conftest.py)."
        )

    stub.load_plugin = _load_plugin

    stub_io = types.ModuleType("pedalboard.io")
    stub_io.AudioFile = _UnusablePedalboardSymbol
    stub.io = stub_io

    sys.modules["pedalboard"] = stub
    sys.modules["pedalboard.io"] = stub_io


if "pedalboard" not in sys.modules and _pedalboard_import_is_fatal_here():
    print(
        "pedalboard's native extension SIGILLs on this host's CPU "
        "(known upstream issue spotify/pedalboard#454) -- installing an "
        "inert stub for this test run. See tests/conftest.py."
    )
    _install_pedalboard_stub()

# ---------------------------------------------------------------------------
# Ensure the project root is importable
# ---------------------------------------------------------------------------

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def _project_root_on_path():
    """Add the project root to sys.path so ``import cost_tracker`` works."""
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    yield


# ---------------------------------------------------------------------------
# Temporary SQLite database path
# ---------------------------------------------------------------------------


@pytest.fixture
def db_path():
    """Return a temporary file path suitable for SQLite, cleaned up after use."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    path = tmp.name
    tmp.close()
    yield path
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------------------
# Tracker fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cost_tracker(db_path):
    """A CostTracker backed by a disposable temp database."""
    from cost_tracker import CostTracker

    tracker = CostTracker(db_path=db_path)
    yield tracker
    tracker.close()


# ---------------------------------------------------------------------------
# Synthetic frame fixtures for signal-level tests
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_stable_frames():
    """Five near-identical 128x128 frames (minimal variation)."""
    import numpy as np

    frames = []
    for i in range(5):
        frame = np.full((128, 128, 3), 128, dtype=np.uint8)
        frame[:, :, 0] = 128 + i
        frames.append(frame)
    return frames


@pytest.fixture
def synthetic_flickery_frames():
    """Five alternating bright/dark 128x128 frames."""
    import numpy as np

    frames = []
    for i in range(5):
        val = 50 if i % 2 == 0 else 200
        frames.append(np.full((128, 128, 3), val, dtype=np.uint8))
    return frames


# ---------------------------------------------------------------------------
# web_server._running_pipelines test injection
# ---------------------------------------------------------------------------


@pytest.fixture
def inject_pipeline():
    """Injects a fake pipeline into ``web_server._running_pipelines`` under
    the canonical ``_pipelines_lock`` discipline; cleans up on teardown.

    Production code (``api_generate`` at ``web_server.py:1256-1290``) takes
    ``_pipelines_lock`` before mutating ``_running_pipelines``. Tests that
    simulate "pipeline X is running" should match that discipline rather
    than bypassing the lock with direct ``_running_pipelines[pid] = X``.

    Concurrency tests that exercise the lock itself
    (``tests/unit/test_web_server_concurrency.py``) deliberately bypass
    this fixture — they ARE the lock-discipline tests.
    """
    from web_server import _pipelines_lock, _running_pipelines

    injected_pids: list[str] = []

    def _inject(pid: str, pipeline_obj) -> None:
        with _pipelines_lock:
            _running_pipelines[pid] = pipeline_obj
        injected_pids.append(pid)

    yield _inject

    with _pipelines_lock:
        for pid in injected_pids:
            _running_pipelines.pop(pid, None)
