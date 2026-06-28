# Capability Test Suite — Foundation + Identity Dimension Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the `tests/capability/` framework (tier markers, intent-ledger, capability-scorecard, shared fixtures) and prove it end-to-end with the Identity offline dimension — filling the `identity/validator.py` zero-test blind spot.

**Architecture:** A new *additive* pytest package organized by capability dimension. Each test carries an execution-tier marker (`offline`/`live`/`e2e`) for cheap CI gating, a manual-claim id (the intent ledger, `_ledger.py`) so the suite doubles as a machine-checkable map of manual § → test → pass/gap, and records a result into a capability scorecard (`_scorecard.py`) emitted at session end. Plan 1 builds the framework + the Identity *offline* tests; Plans 2–N add the remaining dimensions/tiers on this exact pattern. The existing 1280-test suite is untouched; where a claim is already covered there, the ledger cross-links rather than duplicates.

**Tech Stack:** Python 3, pytest (markers via `pytest_configure`/`addinivalue_line`; reporting via `pytest_terminal_summary`), numpy + OpenCV for synthetic image fixtures, ffmpeg `testsrc2` for synthetic clips. Always run via the project venv: `.venv/bin/python -m pytest`.

**Spec:** `docs/superpowers/specs/2026-06-01-comprehensive-capability-test-suite-design.md` (§3 layout, §4 Identity bars, §6 ledger/scorecard).

**Branch note:** The shared working tree is currently on `max-tier-provisioning-2026-06-01`. Do NOT switch branches (a live peer is using the tree). Commit additively via explicit pathspec (`git commit -- <paths>`) — the shared index may hold a peer's staged files.

---

## File Structure

| File | Responsibility |
|---|---|
| `tests/capability/conftest.py` | **`sys.path` shim** (so `_ledger`/`_scorecard` import as top-level — **no `__init__.py` packaging**, matching `tests/unit/`); register `offline`/`live`/`e2e` markers; fixtures (`synthetic_image`, `capability_record`); `pytest_terminal_summary` scorecard emit |
| `tests/capability/_ledger.py` | `Claim` dataclass + `LEDGER` seed (Identity claims) + `get`/`by_dimension`/`assert_unique` |
| `tests/capability/_scorecard.py` | `ScorecardEntry` + `Scorecard` collector (`record`, `render_markdown`, `render_json`) |
| `tests/capability/test_framework_smoke.py` | Proves markers + ledger + scorecard wire together |
| `tests/capability/identity/test_identity_logic.py` | Offline Identity machinery: `get_rolling_stats`, `_compute_pulid_delta`, `_compute_sample_positions`, threshold degradation |

> **No `__init__.py` anywhere under `tests/capability/`** — pytest collects by path (like `tests/unit/`), and `tests/capability/conftest.py` adds its own dir to `sys.path` so `_ledger`/`_scorecard` import as plain top-level modules from any subdir. Packaging `tests/` would risk the existing 1280-suite's collection semantics.

---

## Chunk 1: Scaffolding & framework

### Task 1: Package + tier markers

**Files:**
- Create: `tests/capability/conftest.py` (no `__init__.py`)
- Test: `tests/capability/test_framework_smoke.py`

- [ ] **Step 1: Write the failing test** (`tests/capability/test_framework_smoke.py`)

```python
import pytest


@pytest.mark.offline
def test_offline_marker_is_registered(pytestconfig):
    """The capability tier markers must be registered (no 'unknown marker' warning)."""
    markers = pytestconfig.getini("markers")
    joined = "\n".join(markers)
    assert "offline:" in joined
    assert "live:" in joined
    assert "e2e:" in joined
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/capability/test_framework_smoke.py -v`
Expected: FAIL (collection error: `conftest.py`/package missing, or markers not registered).

- [ ] **Step 3: (no package files)**

Do **NOT** add `__init__.py` — `tests/unit/` has none and pytest collects by path. The `sys.path` shim in `conftest.py` (Step 4) makes `_ledger`/`_scorecard` importable as top-level modules, so `tests/` never becomes a package (which would risk the existing suite's collection).

- [ ] **Step 4: Create `tests/capability/conftest.py` with marker registration**

```python
"""Shared fixtures + tier-marker registration for the capability suite.

Tiers:
  offline — deterministic, mocked, $0, always in CI (default for logic tests)
  live    — needs real API/GPU/ComfyUI creds; skipif-gated; costs money
  e2e     — the one paid golden run; opt-in via CAPABILITY_E2E=1
"""
from __future__ import annotations

import os
import sys

# Make the capability helper modules (_ledger, _scorecard) importable as plain
# top-level modules from any test under tests/capability/ (incl. subdirs like
# identity/) WITHOUT packaging tests/. Runs at conftest load = before collection.
sys.path.insert(0, os.path.dirname(__file__))


def pytest_configure(config):
    # Mirrors how tests/conftest.py registers e2e/grid_search.
    config.addinivalue_line("markers", "offline: deterministic capability test, no network/GPU/spend")
    config.addinivalue_line("markers", "live: capability test needing real API/GPU/ComfyUI; skipif-gated")
    config.addinivalue_line("markers", "e2e: full paid golden-run capability test; opt-in via CAPABILITY_E2E=1")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/capability/test_framework_smoke.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/capability/conftest.py tests/capability/test_framework_smoke.py
git commit -- tests/capability/conftest.py tests/capability/test_framework_smoke.py \
  -m "test(capability): scaffold tests/capability (conftest sys.path shim + tier markers)"
```

---

### Task 2: Intent ledger (`_ledger.py`)

**Files:**
- Create: `tests/capability/_ledger.py`
- Test: add to `tests/capability/test_framework_smoke.py`

- [ ] **Step 1: Write the failing test** (append to `test_framework_smoke.py`)

```python
import _ledger  # top-level via conftest sys.path shim


@pytest.mark.offline
def test_ledger_claim_ids_are_unique():
    _ledger.assert_unique()  # raises on duplicate claim_id


@pytest.mark.offline
def test_ledger_lookup_and_filter():
    claim = _ledger.get("ID-01")
    assert claim.dimension == "identity"
    assert claim.manual_section  # non-empty manual reference
    assert claim.tier in {"offline", "live", "e2e"}
    assert all(c.dimension == "identity" for c in _ledger.by_dimension("identity"))
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/capability/test_framework_smoke.py -v`
Expected: FAIL (`ModuleNotFoundError: _ledger`).

- [ ] **Step 3: Implement `tests/capability/_ledger.py`**

```python
"""Intent ledger: maps manual claims → tests. Each capability test references
its claim_id(s); status surfaces in the scorecard's coverage view.

status values:
  asserted          — a capability test asserts this claim
  cross-linked      — already covered by an existing test elsewhere (no dup)
  INTENDED_NOT_WIRED — a documented gap (stub/dead code); the suite asserts the
                       CURRENT (stub) behavior, loudly flagged as not-yet-wired
"""
from __future__ import annotations

from dataclasses import dataclass

_STATUSES = {"asserted", "cross-linked", "INTENDED_NOT_WIRED"}
_TIERS = {"offline", "live", "e2e"}


@dataclass(frozen=True)
class Claim:
    claim_id: str
    dimension: str
    manual_section: str
    tier: str
    status: str
    description: str

    def __post_init__(self):
        assert self.tier in _TIERS, f"{self.claim_id}: bad tier {self.tier!r}"
        assert self.status in _STATUSES, f"{self.claim_id}: bad status {self.status!r}"


# Seed: Identity dimension (Plan 1). Later plans append their dimensions.
LEDGER: list[Claim] = [
    Claim("ID-01", "identity", "manual §4 Stage2 / digests identity/types.py:92",
          "offline", "cross-linked",
          "SHOT_TYPE_THRESHOLDS strict/std/lenient per shot type"),
    Claim("ID-02", "identity", "manual §4 Stage2 / identity/types.py:101",
          "offline", "asserted",
          "get_threshold_for_shot degrades standard→lenient linearly across attempts"),
    Claim("ID-03", "identity", "manual §4 Stage2 / face_validator_gate.py:165",
          "offline", "cross-linked",
          "composite = 0.6*arc + 0.4*aesthetic; missing component -> 0.5"),
    Claim("ID-04", "identity", "manual §4 Stage2 / face_validator_gate.py:225",
          "offline", "cross-linked",
          "should_halt: composite-only at 0.92 once n>=halt_min_n (or n>=halt_max_n)"),
    Claim("ID-05", "identity", "manual §3.10 / identity/validator.py:266",
          "offline", "asserted",
          "get_rolling_stats suggested_pulid_delta from success_rate windows"),
    Claim("ID-06", "identity", "manual §3.10 / identity/validator.py:684",
          "offline", "asserted",
          "_compute_pulid_delta from per-frame similarity + matched flag"),
    Claim("ID-07", "identity", "manual §3.10 / identity/validator.py:365",
          "offline", "asserted",
          "_compute_sample_positions: density-by-shot-type, clamp [3,10], anchors 10/50/90%"),
    Claim("ID-LIVE-01", "identity", "manual §5.4 / spec §4 Identity",
          "live", "asserted",
          "real ComfyUI keyframe ArcFace >= shot-type threshold - margin (later plan)"),
    Claim("ID-E2E-01", "identity", "manual §1 / spec §4 Identity",
          "e2e", "asserted",
          "same character across ALL shots of the golden mp4 >= lenient (later plan)"),
]


def assert_unique() -> None:
    ids = [c.claim_id for c in LEDGER]
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, f"duplicate claim_ids: {sorted(dupes)}"


def get(claim_id: str) -> Claim:
    for c in LEDGER:
        if c.claim_id == claim_id:
            return c
    raise KeyError(f"no ledger claim {claim_id!r}")


def by_dimension(dimension: str) -> list[Claim]:
    return [c for c in LEDGER if c.dimension == dimension]
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/capability/test_framework_smoke.py -v`
Expected: PASS (all ledger tests green).

- [ ] **Step 5: Commit**

```bash
git commit -- tests/capability/_ledger.py tests/capability/test_framework_smoke.py \
  -m "test(capability): intent ledger (Claim registry + Identity seed claims)"
```

---

### Task 3: Capability scorecard (`_scorecard.py`)

**Files:**
- Create: `tests/capability/_scorecard.py`
- Test: `tests/capability/test_scorecard.py`

- [ ] **Step 1: Write the failing test** (`tests/capability/test_scorecard.py`)

```python
import json
import pytest

from _scorecard import Scorecard  # top-level via conftest sys.path shim


@pytest.mark.offline
def test_scorecard_records_and_renders():
    sc = Scorecard()
    sc.record(dimension="identity", claim_id="ID-05", tier="offline", passed=True)
    sc.record(dimension="identity", claim_id="ID-LIVE-01", tier="live",
              passed=False, measured=0.51, bar=0.60, detail="ArcFace below bar")

    md = sc.render_markdown()
    assert "identity" in md
    assert "0.51" in md and "0.60" in md  # measured vs bar shown for live
    assert "FAIL" in md and "PASS" in md

    data = json.loads(sc.render_json())
    rows = [r for r in data["entries"] if r["claim_id"] == "ID-LIVE-01"]
    assert rows and rows[0]["passed"] is False and rows[0]["measured"] == 0.51


@pytest.mark.offline
def test_scorecard_dimension_rollup():
    sc = Scorecard()
    sc.record(dimension="identity", claim_id="ID-05", tier="offline", passed=True)
    sc.record(dimension="identity", claim_id="ID-06", tier="offline", passed=True)
    roll = sc.rollup()
    assert roll["identity"]["passed"] == 2 and roll["identity"]["failed"] == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/capability/test_scorecard.py -v`
Expected: FAIL (`ModuleNotFoundError: _scorecard`).

- [ ] **Step 3: Implement `tests/capability/_scorecard.py`**

```python
"""Capability scorecard: per-dimension PASS/FAIL + (for live/e2e) measured-vs-bar.
The framework supports both offline machinery results (passed only) and
live/e2e capability results (passed + measured + bar). Emitted at session end
by conftest's pytest_terminal_summary hook.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class ScorecardEntry:
    dimension: str
    claim_id: str
    tier: str
    passed: bool
    measured: Optional[float] = None
    bar: Optional[float] = None
    detail: str = ""


class Scorecard:
    def __init__(self) -> None:
        self.entries: list[ScorecardEntry] = []

    def record(self, *, dimension, claim_id, tier, passed,
               measured=None, bar=None, detail="") -> None:
        self.entries.append(ScorecardEntry(
            dimension=dimension, claim_id=claim_id, tier=tier,
            passed=bool(passed), measured=measured, bar=bar, detail=detail))

    def rollup(self) -> dict:
        out: dict[str, dict] = {}
        for e in self.entries:
            d = out.setdefault(e.dimension, {"passed": 0, "failed": 0})
            d["passed" if e.passed else "failed"] += 1
        return out

    def render_markdown(self) -> str:
        lines = ["# Capability Scorecard", ""]
        for dim, r in sorted(self.rollup().items()):
            lines.append(f"## {dim}  ({r['passed']} pass / {r['failed']} fail)")
            for e in [x for x in self.entries if x.dimension == dim]:
                status = "PASS" if e.passed else "FAIL"
                if e.measured is not None and e.bar is not None:
                    metric = f"  {e.measured} vs bar {e.bar}"
                else:
                    metric = ""
                extra = f" — {e.detail}" if e.detail else ""
                lines.append(f"- [{e.tier}] {e.claim_id}: {status}{metric}{extra}")
            lines.append("")
        return "\n".join(lines)

    def render_json(self) -> str:
        return json.dumps({"entries": [asdict(e) for e in self.entries]}, indent=2)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/capability/test_scorecard.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git commit -- tests/capability/_scorecard.py tests/capability/test_scorecard.py \
  -m "test(capability): capability scorecard (record + rollup + markdown/json render)"
```

---

### Task 4: Wire scorecard into pytest + `capability_record` fixture + synthetic fixtures

**Files:**
- Modify: `tests/capability/conftest.py`
- Test: append to `tests/capability/test_framework_smoke.py`

- [ ] **Step 1: Write the failing test** (append to `test_framework_smoke.py`)

```python
@pytest.mark.offline
def test_capability_record_fixture_collects(capability_record, request):
    capability_record(claim_id="ID-02", passed=True)  # dimension inferred from path
    # The session scorecard accumulates entries:
    sc = request.config._capability_scorecard
    assert any(e.claim_id == "ID-02" for e in sc.entries)


@pytest.mark.offline
def test_synthetic_image_fixture(synthetic_image):
    import os
    assert os.path.exists(synthetic_image)
    assert synthetic_image.endswith(".png")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/capability/test_framework_smoke.py -k "fixture" -v`
Expected: FAIL (`fixture 'capability_record' not found`).

- [ ] **Step 3: Extend `tests/capability/conftest.py`** (append)

```python
# top of conftest.py already has the sys.path shim from Task 1 — keep ONE copy
import numpy as np
import pytest

from _scorecard import Scorecard  # top-level via the shim


# EDIT the Task-1 pytest_configure IN PLACE — add the scorecard line; do NOT
# add a second def (only the last binding survives, a silent foot-gun).
def pytest_configure(config):
    config.addinivalue_line("markers", "offline: deterministic capability test, no network/GPU/spend")
    config.addinivalue_line("markers", "live: capability test needing real API/GPU/ComfyUI; skipif-gated")
    config.addinivalue_line("markers", "e2e: full paid golden-run capability test; opt-in via CAPABILITY_E2E=1")
    config._capability_scorecard = Scorecard()


@pytest.fixture
def capability_record(request):
    """Record a capability result; dimension inferred from the test's subpackage."""
    sc = request.config._capability_scorecard
    # tests/capability/<dimension>/test_*.py -> dimension
    parts = request.node.nodeid.split("/")
    dimension = parts[2] if len(parts) > 3 and parts[1] == "capability" else "framework"

    def _record(*, claim_id, passed, tier="offline", measured=None, bar=None, detail=""):
        sc.record(dimension=dimension, claim_id=claim_id, tier=tier,
                  passed=passed, measured=measured, bar=bar, detail=detail)
    return _record


@pytest.fixture
def synthetic_image(tmp_path):
    """A deterministic 256x256 RGB png (no real person)."""
    import cv2
    arr = np.full((256, 256, 3), 127, dtype=np.uint8)
    arr[64:192, 96:160] = 200  # a simple bright block, deterministic
    p = tmp_path / "synthetic.png"
    cv2.imwrite(str(p), arr)
    return str(p)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    sc = getattr(config, "_capability_scorecard", None)
    if sc is None or not sc.entries:
        return
    terminalreporter.write_sep("=", "CAPABILITY SCORECARD")
    terminalreporter.write_line(sc.render_markdown())
```

> **Implementer note:** `conftest.py` may define `pytest_configure` and the `sys.path` shim only ONCE — **edit the Task-1 function in place** to add `config._capability_scorecard = Scorecard()` (do NOT append a second `def pytest_configure`; the second silently shadows the first). Keep a single `sys.path.insert` shim. If `cv2` import fails at collection, guard `synthetic_image` with `pytest.importorskip("cv2")`.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/capability/ -v`
Expected: PASS; the run prints a "CAPABILITY SCORECARD" section.

- [ ] **Step 5: Commit**

```bash
git commit -- tests/capability/conftest.py tests/capability/test_framework_smoke.py \
  -m "test(capability): wire scorecard hook + capability_record + synthetic_image fixtures"
```

---

## Chunk 2: Identity offline dimension

> Targets the real blind spot: `identity/validator.py`'s pure methods (`get_rolling_stats`, `_compute_pulid_delta`, `_compute_sample_positions`) have **zero** existing tests. `get_threshold_for_shot` (ID-02) is asserted here too; `SHOT_TYPE_THRESHOLDS`/composite/`should_halt` (ID-01/03/04) are **cross-linked** in the ledger to the existing `test_identity_types.py` / `test_face_validator_gate.py` (no duplication).

### Task 5: Threshold degradation (ID-02) + PuLID-delta (ID-06)

**Files:**
- Create: `tests/capability/identity/test_identity_logic.py` (no `__init__.py`; collected by path, helper imports resolve via the conftest `sys.path` shim)

- [ ] **Step 1: Write the failing test** (`tests/capability/identity/test_identity_logic.py`)

```python
import pytest

from identity.types import get_threshold_for_shot
from identity.validator import IdentityValidator


@pytest.mark.offline
def test_threshold_degrades_standard_to_lenient(capability_record):
    # portrait: standard 0.70 -> lenient 0.60 across attempts (max_attempts=3)
    first = get_threshold_for_shot("portrait", mode="standard", attempt=0, max_attempts=3)
    last = get_threshold_for_shot("portrait", mode="standard", attempt=2, max_attempts=3)
    assert first == pytest.approx(0.70)
    assert last == pytest.approx(0.60)
    # monotonic non-increasing
    mids = [get_threshold_for_shot("portrait", attempt=a, max_attempts=3) for a in range(3)]
    assert mids == sorted(mids, reverse=True)
    capability_record(claim_id="ID-02", passed=True)


@pytest.mark.offline
def test_pulid_delta_from_similarity(capability_record):
    f = IdentityValidator._compute_pulid_delta
    assert f(0.85, True) == pytest.approx(-0.05)   # matched & strong -> ease off
    assert f(0.70, True) == pytest.approx(0.0)      # matched, not strong -> hold
    assert f(0.58, False) == pytest.approx(0.05)    # unmatched but close -> nudge up
    assert f(0.40, False) == pytest.approx(0.10)    # far miss -> push hard
    capability_record(claim_id="ID-06", passed=True)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/capability/identity/test_identity_logic.py -v`
Expected: FAIL at collection (file doesn't exist yet); once created, assertion-level only if a value differs from source.

- [ ] **Step 3: Run again** (no `__init__.py` needed — the conftest `sys.path` shim resolves the imports). If a value differs from source, correct the test to the source value and record the divergence in the commit body (plan-vs-source rule).

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/capability/identity/test_identity_logic.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git commit -- tests/capability/identity/test_identity_logic.py \
  -m "test(capability): Identity offline — threshold degradation + PuLID-delta (ID-02, ID-06)"
```

---

### Task 6: Rolling-stats PuLID suggestion (ID-05) + sample positions (ID-07)

**Files:**
- Modify: `tests/capability/identity/test_identity_logic.py`

- [ ] **Step 1: Write the failing tests** (append)

```python
from identity.types import (
    IdentityValidationResult, CharacterIdentityResult, FailureReason,
)


def _history_result(cid, similarity, matched):
    """Build an IdentityValidationResult shaped as get_rolling_stats expects:
    self.history is a List[IdentityValidationResult]; each carries a
    CharacterIdentityResult per character (identity/types.py:46-85)."""
    cr = CharacterIdentityResult(
        character_id=cid, character_name=cid,
        best_similarity=similarity, mean_similarity=similarity, min_similarity=similarity,
        frame_results=[], matched=matched,
        primary_failure_reason=FailureReason.PASSED if matched else FailureReason.WRONG_PERSON,
        suggested_pulid_adjustment=0.0,
    )
    return IdentityValidationResult(
        passed=matched, overall_score=similarity, character_results={cid: cr},
        frames_sampled=1, video_duration_seconds=1.0, shot_type="portrait",
        threshold_used=0.70,
    )


@pytest.mark.offline
def test_rolling_stats_suggested_delta(capability_record):
    v = IdentityValidator()  # __init__ sets only dict/list attrs; no torch/DeepFace
    cid = "char_test"
    # self.history is a List[IdentityValidationResult]; 5 misses -> success_rate < 0.5 -> +0.10
    v.history.extend(_history_result(cid, 0.40, matched=False) for _ in range(5))
    stats = v.get_rolling_stats(cid, window=10)
    assert stats["suggested_pulid_delta"] == pytest.approx(0.10)
    capability_record(claim_id="ID-05", passed=True)


@pytest.mark.offline
def test_sample_positions_density_and_clamp(capability_record):
    v = IdentityValidator()
    # portrait density 2.0; clamp [3,10]; sorted ascending.
    pos = v._compute_sample_positions(total_frames=120, fps=30.0, shot_type="portrait")
    assert 3 <= len(pos) <= 10
    assert pos == sorted(pos)
    # landscape density 0.0 -> returns [] (skip), per identity/validator.py:365-406
    land = v._compute_sample_positions(total_frames=120, fps=30.0, shot_type="landscape")
    assert land == []
    capability_record(claim_id="ID-07", passed=True)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/capability/identity/test_identity_logic.py -k "rolling or sample" -v`
Expected: FAIL.

- [ ] **Step 3: (resolved) construction + history shape**

No workaround needed (both verified against source): `IdentityValidator.__init__` (`identity/validator.py:53-62`) sets only dict/list attrs and pulls NO torch/DeepFace (DeepFace import is conditional), so plain `IdentityValidator()` constructs offline. `self.history` is a `List[IdentityValidationResult]` (`:61`); `get_rolling_stats` reads `r.character_results[cid].best_similarity` / `.matched` (`:266-310`) — the `_history_result` helper builds exactly that shape. (`cv2`/`numpy` are imported at module top but are already suite deps, so offline import is fine.)

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/capability/identity/test_identity_logic.py -v`
Expected: PASS (4 Identity tests).

- [ ] **Step 5: Commit**

```bash
git commit -- tests/capability/identity/test_identity_logic.py \
  -m "test(capability): Identity offline — rolling-stats delta + sample positions (ID-05, ID-07)"
```

---

### Task 7: Full-suite green + scorecard demonstration

**Files:** none (verification + ledger-coverage assertion)

- [ ] **Step 1: Write a ledger-coverage test** (`tests/capability/identity/test_identity_logic.py`, append)

```python
@pytest.mark.offline
def test_identity_offline_claims_are_exercised():
    """Every Identity 'asserted' offline claim must be recorded by some test in this run
    OR cross-linked. Guards against silent ledger drift."""
    import _ledger  # top-level via conftest sys.path shim
    offline_asserted = {c.claim_id for c in _ledger.by_dimension("identity")
                        if c.tier == "offline" and c.status == "asserted"}
    assert offline_asserted == {"ID-02", "ID-05", "ID-06", "ID-07"}
```

- [ ] **Step 2: Run the whole capability suite**

Run: `.venv/bin/python -m pytest tests/capability/ -v`
Expected: PASS; terminal prints the CAPABILITY SCORECARD with an `identity` section.

- [ ] **Step 3: Confirm no regression to the existing suite (collection only)**

Run: `.venv/bin/python -m pytest --collect-only -q 2>/dev/null | tail -3`
Expected: collected count = prior baseline (1280) + the new capability tests; no collection errors.

- [ ] **Step 4: Commit**

```bash
git commit -- tests/capability/identity/test_identity_logic.py \
  -m "test(capability): Identity offline ledger-coverage guard + full-suite green"
```

---

## Done criteria (Plan 1)

- `.venv/bin/python -m pytest tests/capability/ -v` is green and prints a capability scorecard with an `identity` section.
- `identity/validator.py`'s three pure methods now have offline coverage (`ID-05/06/07`).
- The framework (markers, `_ledger`, `_scorecard`, fixtures) is in place for Plans 2–N to add dimensions by copying the Identity pattern.
- Existing 1280-test suite still collects clean (no regressions).

## Follow-on plans (not in scope here)

- **Plan 2** — offline core: Gates/auto-approve (incl. the `c917bc1` composite-absent→identity_score fallback + `8cf0f07` tier-aware default), chief_director veto, scene_decomposer, style_director, lip_sync routing, cascade-error, coherence/motion. Same pattern.
- **Plan 3** — thin-area offline (routing/cascade, audio/loudness, format/assembly, cost) + `stubs_and_gaps` ledger (`INTENDED_NOT_WIRED`).
- **Plan 4** — live-component tier (skipif-gated real-artifact validation).
- **Plan 5** — golden E2E + scorecard measured-vs-bar wiring (built; **not run** without explicit user spend authorization).
