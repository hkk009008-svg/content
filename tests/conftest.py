"""Shared pytest fixtures for the content test suite."""

import os
import sys
import tempfile

import pytest

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


@pytest.fixture
def quality_tracker():
    """A QualityTracker backed by an in-memory SQLite database."""
    from quality_tracker import QualityTracker

    tracker = QualityTracker(db_path=":memory:")
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
