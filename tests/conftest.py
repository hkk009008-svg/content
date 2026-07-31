"""Shared pytest fixtures for the content test suite."""

import os
import sys
import tempfile

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
# ``setdefault`` (not assignment) so a real environment always wins, and
# ``config/settings.py``'s ``load_dotenv(..., override=True)`` still overrides
# these for a developer who has a real ``.env``.
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
    config.addinivalue_line("markers", "e2e: end-to-end tests requiring GPU pod + API keys")
    config.addinivalue_line("markers", "grid_search: parameter grid search tests (long-running)")

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
