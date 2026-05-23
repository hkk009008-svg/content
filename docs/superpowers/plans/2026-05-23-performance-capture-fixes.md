# Performance-Capture Subsystem Fixes — Implementation Plan

> **POST-PIVOT STATUS (2026-05-23):** Plan is still actionable. `performance/`,
> `domain/performance.py`, the four engine adapters, and `cinema/shots/controller.py`
> all survived the pivot. **Note:** `cinema/shots/controller.py:452` line
> number may have shifted by a few lines after this session's UI-knob
> wires (identity_strictness, motion_quality_threshold, face_swap_enabled,
> etc.) — grep for `generate_performance_take` to find the current
> location. The 8 gaps + slice structure are unchanged.
> **Canonical current state: `/HANDOFF.md`.**

> **For agentic workers:** REQUIRED: Use `superpowers:subagent-driven-development` (if subagents available) or `superpowers:executing-plans` to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the 8 gaps identified in the 2026-05-23 design evaluation of `performance/` + `domain/performance.py`, in shippable per-concern slices.

**Architecture:** Each slice is one logical commit (some span multiple commits for pure-refactor extractions) and leaves the §0 smoke block green. The pure routing layer (`domain/performance.py`) gets its missing test coverage, the controller call site (`cinema/shots/controller.py:452`) gains preconditions and an automated identity gate, and the four engine adapters get shared helpers (polling, cost logging, content-hash cache) extracted to remove duplication.

**Tech Stack:** Python 3.10+ (refactor branch standard), pytest, requests, OpenCV/ffmpeg for frame extraction, ArcFace via existing `identity.validator.IdentityValidator`, no new third-party deps.

**Reference docs:**
- Design evaluation: this conversation, 2026-05-23
- Refactor playbook: [docs/REFACTOR_HANDOFF.md](../../REFACTOR_HANDOFF.md) §0 (smoke) and §6 (slice playbook)
- Routing handoff: [docs/REFACTOR_HANDOFF.md](../../REFACTOR_HANDOFF.md) (search: PERFORMANCE_CAPTURE_HANDOFF §3, §7)

**Skills to reference during execution:**
- `@superpowers:test-driven-development` — TDD discipline per step
- `@superpowers:verification-before-completion` — never claim a slice done without running the smoke block
- `@superpowers:using-git-worktrees` — each slice optionally in its own worktree

---

## File Structure Summary

**New files (5):**
- `tests/unit/test_domain_performance.py` — routing matrix coverage (Slice 1)
- `tests/unit/test_performance_preconditions.py` — engine-input preconditions (Slice 2)
- `tests/unit/test_shot_types.py` — normalizer (Slice 4)
- `tests/unit/test_performance_poll.py` — polling helper (Slice 5)
- `tests/unit/test_router_semaphore.py` — concurrency cap (Slice 6)
- `domain/shot_types.py` — canonical shot-type constants + normalizer (Slice 4)
- `performance/_poll.py` — shared task-poller (Slice 5)
- `performance/_cache.py` — content-hash cache for driving-video synth (Slice 8)
- `performance/identity_gate.py` — ArcFace check on performance output (Slice 3)

**Modified files (6):**
- `domain/performance.py` — `precondition_error()` (Slice 2), use shot_types (Slice 4), return tuple from Mode-B (Slice 7 — actually in driving_video.py)
- `cinema/shots/controller.py:452-610` — wire preconditions (Slice 2), wire identity gate (Slice 3), record provider (Slice 7)
- `performance/_router.py` — per-provider semaphores (Slice 6)
- `performance/act_one.py` — use `_poll.poll_task` (Slice 5)
- `performance/viggle.py` — use `_poll.poll_task` (Slice 5)
- `performance/live_portrait.py` — use `_poll.poll_task` (Slice 5)
- `performance/driving_video.py` — use `_poll.poll_task` (Slice 5), return provider name (Slice 7), use `_cache` (Slice 8)

---

## Chunk 1 — P0 Correctness (Slices 1-3)

Three independent fixes that close the highest-severity gaps: untested routing, silent audio-precondition violations, and unvalidated performance output. Order is independent; suggested order matches priority of correctness risk.

---

### Slice 1: Routing matrix unit tests

**Why:** `domain/performance.py` was deliberately written as a pure module specifically to be unit-testable. Verified: `tests/` has no file referencing it. ~30 routing branches go untested.

**Files:**
- Create: `tests/unit/test_domain_performance.py`

**Pre-edit check** (per CLAUDE.md): not applicable — no production symbols modified.

- [ ] **Step 1.1: Write the failing test file**

Create `tests/unit/test_domain_performance.py`:

```python
"""Tests for domain/performance.py — pure routing logic.

The routing matrix (handoff §3) has ~30 branches across shot_type strings,
dialogue presence, character presence, and budget mode. This file locks
each branch with a one-line shot dict + asserted engine string.
"""
from __future__ import annotations

import pytest

from domain.performance import (
    ENGINE_ACT_ONE, ENGINE_LIVE_PORTRAIT, ENGINE_VIGGLE, ENGINE_SKIP,
    route_performance_engine,
    should_capture,
    shot_needs_driving_video,
    driving_video_source,
)


def _shot(**overrides) -> dict:
    """Default character-bearing dialogue shot, overridable per test."""
    base = {
        "shot_type": "medium",
        "characters_in_frame": ["alice"],
        "dialogue": "Hello world.",
        "performance_budget_mode": "",
        "driving_video_path": "",
    }
    base.update(overrides)
    return base


class TestSkipRules:
    def test_no_characters_returns_skip(self):
        assert route_performance_engine(_shot(characters_in_frame=[]), None) == ENGINE_SKIP

    def test_landscape_returns_skip(self):
        assert route_performance_engine(_shot(shot_type="landscape"), None) == ENGINE_SKIP

    def test_wide_no_dialogue_returns_skip(self):
        assert route_performance_engine(_shot(shot_type="wide", dialogue=""), None) == ENGINE_SKIP

    def test_empty_shot_returns_skip(self):
        assert route_performance_engine({"shot_type": "", "dialogue": ""}, None) == ENGINE_SKIP


class TestActOneRouting:
    @pytest.mark.parametrize("shot_type", [
        "portrait", "medium", "close-up", "closeup", "close_up", "ecu",
        "PORTRAIT",  # case-insensitivity guard
    ])
    def test_dialogue_plus_face_framing_routes_act_one(self, shot_type):
        assert route_performance_engine(_shot(shot_type=shot_type), None) == ENGINE_ACT_ONE

    def test_dialogue_in_other_framing_falls_through_to_act_one(self):
        # Rule 4 in route_performance_engine: dialogue in any framing → ACT_ONE
        assert route_performance_engine(_shot(shot_type="over_shoulder"), None) == ENGINE_ACT_ONE

    def test_dialogue_as_list_routes_act_one(self):
        dlg = [{"text": "Hi"}, {"text": "There"}]
        assert route_performance_engine(_shot(dialogue=dlg), None) == ENGINE_ACT_ONE


class TestLivePortraitRouting:
    @pytest.mark.parametrize("mode", ["budget", "cheap", "Budget", "CHEAP"])
    def test_budget_mode_swaps_act_one_for_live_portrait(self, mode):
        shot = _shot(shot_type="portrait", performance_budget_mode=mode)
        assert route_performance_engine(shot, None) == ENGINE_LIVE_PORTRAIT


class TestViggleRouting:
    def test_action_no_dialogue_routes_viggle(self):
        shot = _shot(shot_type="action", dialogue="")
        assert route_performance_engine(shot, None) == ENGINE_VIGGLE

    def test_action_with_dialogue_routes_act_one(self):
        shot = _shot(shot_type="action", dialogue="Charge!")
        assert route_performance_engine(shot, None) == ENGINE_ACT_ONE


class TestShouldCapture:
    def test_no_characters_false(self):
        assert should_capture(_shot(characters_in_frame=[]), None) is False

    def test_landscape_false(self):
        assert should_capture(_shot(shot_type="landscape"), None) is False

    def test_dialogue_medium_true(self):
        assert should_capture(_shot(), None) is True


class TestShotNeedsDrivingVideo:
    def test_act_one_does_not_need_driving_video(self):
        assert shot_needs_driving_video(_shot(shot_type="portrait")) is False

    def test_live_portrait_needs_driving_video(self):
        shot = _shot(shot_type="portrait", performance_budget_mode="cheap")
        assert shot_needs_driving_video(shot) is True

    def test_viggle_needs_driving_video(self):
        shot = _shot(shot_type="action", dialogue="")
        assert shot_needs_driving_video(shot) is True

    def test_skip_does_not_need_driving_video(self):
        assert shot_needs_driving_video(_shot(characters_in_frame=[])) is False


class TestDrivingVideoSource:
    def test_uploaded_wins(self):
        shot = _shot(driving_video_path="/tmp/uploaded.mp4")
        assert driving_video_source(shot) == "upload"

    def test_dialogue_no_upload_is_tts_auto(self):
        assert driving_video_source(_shot()) == "tts_auto"

    def test_no_dialogue_no_action_is_none(self):
        # No dialogue + non-action shot type → SKIP → "none"
        assert driving_video_source(_shot(dialogue="", shot_type="medium")) == "none"
```

- [ ] **Step 1.2: Run test, expect all green (case-insensitivity is already implemented)**

```bash
PY=/Users/hyungkoookkim/Content/.venv/bin/python
cd /Users/hyungkoookkim/Content && $PY -m pytest tests/unit/test_domain_performance.py -v
```

Verified pre-write: `_shot_type` lowercases (`t.lower()` at [domain/performance.py:50](../../../domain/performance.py:50)) and `route_performance_engine` lowercases budget mode (`shot.get("performance_budget_mode") or "").lower()` at [domain/performance.py:126](../../../domain/performance.py:126). All uppercase / mixed-case test cases SHOULD pass.

Expected: all green. If any test fails, it's a real bug — fix `domain/performance.py`, not the test.

- [ ] **Step 1.3: Fix any bugs the tests revealed (only if Step 1.2 was red)**

Per the verification above, all tests should pass against current code. If any fail, fix `domain/performance.py` — commit the test + fix together.

- [ ] **Step 1.4: Run smoke block**

Per [docs/REFACTOR_HANDOFF.md](../../REFACTOR_HANDOFF.md) §0:

```bash
PY=/Users/hyungkoookkim/Content/.venv/bin/python
cd /Users/hyungkoookkim/Content && $PY -c "
import sys; sys.path.insert(0, '.')
from domain.performance import route_performance_engine, ENGINE_ACT_ONE
assert route_performance_engine({'shot_type':'portrait','characters_in_frame':['x'],'dialogue':'hi'}, None) == ENGINE_ACT_ONE
print('OK routing smoke')
"
```

Then the full §0 smoke from REFACTOR_HANDOFF.md.

- [ ] **Step 1.5: Commit**

```bash
git add tests/unit/test_domain_performance.py
# Include domain/performance.py only if Step 1.3 required a fix.
git commit -m "$(cat <<'EOF'
test(domain): lock performance-capture routing matrix

Add tests for the ~30-branch routing decision in domain.performance.
Covers ENGINE_SKIP / ACT_ONE / LIVE_PORTRAIT / VIGGLE rules from the
PERFORMANCE_CAPTURE_HANDOFF §3 matrix.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Slice 2: ACT_ONE audio precondition

**Why:** `cinema/shots/controller.py:503-507` silently sets `audio_path=""` when scene audio fails. Adapter [act_one.py:80](performance/act_one.py:80) refuses empty audio — but only after the take metadata is allocated. Worse: when a driving video IS provided, Act-One uses it for reference and *appears to succeed* with mis-synced output. Hard-precondition audio at the domain boundary.

**Files:**
- Modify: `domain/performance.py` — add `precondition_error()`
- Modify: `cinema/shots/controller.py:475-528` — call `precondition_error()` before allocating the take
- Create: `tests/unit/test_performance_preconditions.py`

**Pre-edit impact check** (per CLAUDE.md):

```bash
# Run via your GitNexus MCP — if unavailable, skip and rely on grep.
# Reading: gitnexus_impact({target: "route_performance_engine", direction: "upstream"})
grep -rn "route_performance_engine\|precondition" --include="*.py" /Users/hyungkoookkim/Content | grep -v ".venv\|__pycache__"
```

Expect 1 caller (controller). LOW risk.

- [ ] **Step 2.1: Write failing test**

Create `tests/unit/test_performance_preconditions.py`:

```python
"""Tests for engine-input preconditions in domain/performance.py."""
from __future__ import annotations

import pytest

from domain.performance import (
    ENGINE_ACT_ONE, ENGINE_LIVE_PORTRAIT, ENGINE_VIGGLE, ENGINE_SKIP,
    precondition_error,
)


class TestActOnePrecondition:
    def test_empty_audio_returns_error(self):
        assert precondition_error(ENGINE_ACT_ONE, audio_path="", driving_video_path="") is not None
        assert "audio" in precondition_error(ENGINE_ACT_ONE, audio_path="", driving_video_path="").lower()

    def test_none_audio_returns_error(self):
        assert precondition_error(ENGINE_ACT_ONE, audio_path=None, driving_video_path=None) is not None

    def test_audio_present_returns_none(self):
        assert precondition_error(ENGINE_ACT_ONE, audio_path="/tmp/a.wav", driving_video_path="") is None

    def test_audio_and_driving_present_returns_none(self):
        assert precondition_error(ENGINE_ACT_ONE, audio_path="/tmp/a.wav", driving_video_path="/tmp/d.mp4") is None


class TestLivePortraitPrecondition:
    def test_missing_driving_video_returns_error(self):
        err = precondition_error(ENGINE_LIVE_PORTRAIT, audio_path="/tmp/a.wav", driving_video_path="")
        assert err is not None and "driving" in err.lower()

    def test_driving_video_present_returns_none(self):
        assert precondition_error(ENGINE_LIVE_PORTRAIT, audio_path="/tmp/a.wav", driving_video_path="/tmp/d.mp4") is None


class TestVigglePrecondition:
    def test_missing_driving_video_returns_error(self):
        err = precondition_error(ENGINE_VIGGLE, audio_path="", driving_video_path="")
        assert err is not None and "driving" in err.lower()


class TestSkipPrecondition:
    def test_skip_returns_none_regardless(self):
        assert precondition_error(ENGINE_SKIP, audio_path="", driving_video_path="") is None
```

- [ ] **Step 2.2: Run test, verify it fails**

```bash
$PY -m pytest tests/unit/test_performance_preconditions.py -v
```

Expected: `ImportError: cannot import name 'precondition_error'`.

- [ ] **Step 2.3: Add `precondition_error()` to `domain/performance.py`**

Append after `driving_video_source`:

```python
def precondition_error(
    engine: str,
    audio_path: Optional[str],
    driving_video_path: Optional[str],
) -> Optional[str]:
    """Return an error string if the engine's inputs are missing, else None.

    Called from cinema/shots/controller.py before allocating a take so we
    don't leave orphan take metadata when we know the dispatch will fail.

    Rules:
      - ACT_ONE requires audio_path. (It can optionally take a driving video
        as reference, but it still uses audio for lip-sync timing.)
      - LIVE_PORTRAIT and VIGGLE require a driving_video_path.
      - SKIP has no preconditions.
    """
    if engine == ENGINE_ACT_ONE:
        if not (audio_path or "").strip():
            return "ACT_ONE requires audio_path; got empty"
    if engine in (ENGINE_LIVE_PORTRAIT, ENGINE_VIGGLE):
        if not (driving_video_path or "").strip():
            return f"{engine} requires driving_video_path; got empty"
    return None
```

- [ ] **Step 2.4: Run unit tests, verify pass**

```bash
$PY -m pytest tests/unit/test_performance_preconditions.py -v
```

Expected: all green.

- [ ] **Step 2.5: Wire into controller**

In `cinema/shots/controller.py` around line 508 (after `audio_path = ...` resolution, before `# --- 3. Driving video ---`):

```python
# Hard precondition check — refuse to allocate a take when we know it'll
# fail in the adapter. Audio-less ACT_ONE silently mis-syncs; LIVE_PORTRAIT
# and VIGGLE fail to start at all.
from domain.performance import precondition_error
pre_err = precondition_error(engine, audio_path, shot.get("driving_video_path") or "")
if pre_err:
    def _mut_pre_fail(_scene: dict, project_shot: dict):
        project_shot["performance_engine"] = "SKIP"
        return MutationResult(True, save=True)
    self._mutate_shot(shot_id, _mut_pre_fail)
    self.progress(
        "PERFORMANCE_SKIPPED",
        f"Shot {shot_id}: {engine} precondition failed: {pre_err}",
        -1, scene_id=scene_id, shot_id=shot_id, performance_engine="SKIP",
    )
    return {"success": True, "skipped": True, "engine": engine, "error": pre_err}
```

Note the placement: the check uses `shot.get("driving_video_path")` because the Mode-B synth happens AFTER this check, on line ~512. For LIVE_PORTRAIT/VIGGLE the operator must upload a driving video — Mode B is only for ACT_ONE's case where audio drives an auto-synth.

- [ ] **Step 2.6: Run §0 smoke block**

Full smoke per [docs/REFACTOR_HANDOFF.md](../../REFACTOR_HANDOFF.md) §0.

- [ ] **Step 2.7: Commit**

```bash
git add domain/performance.py cinema/shots/controller.py tests/unit/test_performance_preconditions.py
git commit -m "$(cat <<'EOF'
feat(performance): precondition check refuses audio-less ACT_ONE dispatch

Previously the controller silently passed audio_path="" when scene audio
synth failed, so ACT_ONE would either (a) fail in-adapter after allocating
take metadata, or (b) with a driving video present, produce mis-synced
output that auto-approved silently.

Add domain.performance.precondition_error() and call it before take
allocation. Failed preconditions are treated as a SKIP — pipeline keeps
moving, motion_render falls through to text-to-video.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Slice 3: ArcFace identity gate on performance output

**Why:** `face_validator_gate.py` enforces ArcFace similarity on keyframes (N=8 best-of), but performance takes (Act-One / LivePortrait output) skip this gate entirely. They auto-approve at [controller.py:590](cinema/shots/controller.py:590). Drifted faces flow silently to motion_render. Add one ArcFace check on a sampled frame; below floor → don't auto-approve.

**Files:**
- Create: `performance/identity_gate.py` — `validate_performance_take(video_path, face_anchor) -> Optional[float]`
- Modify: `cinema/shots/controller.py:584-595` — block auto-approve when score below floor
- Create: `tests/unit/test_performance_identity_gate.py`

**Pre-edit impact check** (per CLAUDE.md):
- `identity.validator.IdentityValidator` — read-only, no edits.
- Controller `_mut_success` — direct caller change; impact = controller only.

**Verified facts (already grepped):**
- `IdentityValidator.validate_image(image_path, reference_path, threshold)` is the public API at [identity/validator.py](../../../identity/validator.py); used in `face_validator_gate._arcface_score` already.
- Character data is `project.get("characters", [])` — a **list of dicts**, NOT a dict. To resolve the face reference, use `character_manager.get_reference_image(project, character_id)` which is already imported at [cinema/shots/controller.py:87](../../../cinema/shots/controller.py:87).
- `MutationResult` is imported at [cinema/shots/controller.py:85](../../../cinema/shots/controller.py:85) from `project_manager`. First positional arg is the value to return; `save=` is the kwarg. `MutationResult(True, save=True)` (boolean ack) and `MutationResult(take, save=True)` (return value) are both correct — see existing usages at lines 486, 574, 593.

- [ ] **Step 3.1: Locate frame-extraction utility**

```bash
grep -rn "ffmpeg\|cv2.VideoCapture\|extract_frame" --include="*.py" /Users/hyungkoookkim/Content | grep -v ".venv\|__pycache__\|node_modules" | head -20
```

If a helper already exists (e.g., in `quality_max.py` or `continuity_engine.py`), reuse it. Otherwise the new module will add a small helper. Document the chosen approach in the commit message.

- [ ] **Step 3.2: Write failing test**

Create `tests/unit/test_performance_identity_gate.py`:

```python
"""Tests for performance/identity_gate.py — ArcFace gate on performance takes."""
from __future__ import annotations

import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest

from performance.identity_gate import (
    validate_performance_take,
    DEFAULT_PERFORMANCE_FLOOR,
)


class TestValidatePerformanceTake:
    def test_missing_video_returns_none(self):
        assert validate_performance_take("/tmp/does_not_exist.mp4", "/tmp/anchor.png") is None

    def test_missing_anchor_returns_none(self, tmp_path):
        vid = tmp_path / "fake.mp4"
        vid.write_bytes(b"\x00" * 100)
        assert validate_performance_take(str(vid), "") is None

    @patch("performance.identity_gate._extract_sample_frame")
    @patch("performance.identity_gate._arcface_score")
    def test_returns_arc_score_when_both_present(self, mock_arc, mock_extract, tmp_path):
        vid = tmp_path / "fake.mp4"
        vid.write_bytes(b"\x00" * 100)
        anchor = tmp_path / "anchor.png"
        anchor.write_bytes(b"\x00" * 100)
        mock_extract.return_value = str(tmp_path / "frame.png")
        mock_arc.return_value = 0.83
        result = validate_performance_take(str(vid), str(anchor))
        assert result == pytest.approx(0.83)

    @patch("performance.identity_gate._extract_sample_frame", return_value=None)
    def test_returns_none_when_frame_extract_fails(self, _mock, tmp_path):
        vid = tmp_path / "fake.mp4"; vid.write_bytes(b"\x00" * 100)
        anchor = tmp_path / "a.png"; anchor.write_bytes(b"\x00" * 100)
        assert validate_performance_take(str(vid), str(anchor)) is None


class TestFloorConstant:
    def test_floor_is_sane(self):
        # Just guard against accidental 0.99 floors that would fail every take.
        assert 0.5 <= DEFAULT_PERFORMANCE_FLOOR <= 0.9
```

- [ ] **Step 3.3: Run test, verify fail**

```bash
$PY -m pytest tests/unit/test_performance_identity_gate.py -v
```

Expected: `ModuleNotFoundError: No module named 'performance.identity_gate'`.

- [ ] **Step 3.4: Implement `performance/identity_gate.py`**

Create the file. Uses `IdentityValidator` directly (public API) instead of `face_validator_gate._arcface_score` (private). Singleton cache lives here, mirroring the pattern in `face_validator_gate`.

```python
"""ArcFace identity gate for performance-capture output.

Performance engines (Act-One, LivePortrait, Viggle) can drift the character's
face away from the approved keyframe. This module samples one frame from
the generated take and scores it against the character's face anchor.

Returns:
  - The cosine similarity in [0, 1] on success.
  - None when scoring isn't possible (no anchor, no face detected, no
    ffmpeg/cv2 available). Callers should treat None as "gate inconclusive"
    and fall back to operator review, NOT auto-fail.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import threading
from typing import Optional

# Use the public IdentityValidator (not face_validator_gate._arcface_score —
# that's a private symbol and could change). Lazy-loaded singleton so we
# don't pay the ArcFace weight load per call.
try:
    from identity.validator import IdentityValidator
    _ID_VALIDATOR_AVAILABLE = True
except Exception:
    _ID_VALIDATOR_AVAILABLE = False

_VALIDATOR: Optional["IdentityValidator"] = None
_VALIDATOR_LOCK = threading.Lock()


# Threshold below which auto-approval is suppressed. Set conservatively —
# 0.7 is the IdentityValidator default "looks like the same person" floor.
DEFAULT_PERFORMANCE_FLOOR = 0.70


def _get_validator() -> Optional["IdentityValidator"]:
    global _VALIDATOR
    if not _ID_VALIDATOR_AVAILABLE:
        return None
    if _VALIDATOR is not None:
        return _VALIDATOR
    with _VALIDATOR_LOCK:
        if _VALIDATOR is None:
            try:
                _VALIDATOR = IdentityValidator()
            except Exception as e:
                print(f"[PerformanceGate] IdentityValidator init failed: {e}")
                return None
        return _VALIDATOR


def _arcface_score(frame_path: str, anchor_path: str) -> Optional[float]:
    """Score a single frame against the anchor. Wrapper around IdentityValidator."""
    v = _get_validator()
    if v is None:
        return None
    try:
        result = v.validate_image(frame_path, anchor_path, threshold=0.0)
        return float(result.overall_score)
    except Exception as e:
        print(f"[PerformanceGate] ArcFace score failed: {e}")
        return None


def _extract_sample_frame(video_path: str, dest_png: str) -> Optional[str]:
    """Extract a frame near 1s into `video_path` to `dest_png`. ffmpeg-first."""
    if not os.path.exists(video_path):
        return None
    try:
        # -ss before -i is a fast seek (keyframe-accurate enough for ArcFace).
        # Sample at 1.0s in — most generated clips have a clean frame by then.
        subprocess.run(
            ["ffmpeg", "-y", "-ss", "1.0", "-i", video_path,
             "-frames:v", "1", "-q:v", "2", dest_png],
            check=True, capture_output=True, timeout=30,
        )
        return dest_png if os.path.exists(dest_png) else None
    except (subprocess.SubprocessError, FileNotFoundError):
        # ffmpeg not installed or call failed — caller treats None as inconclusive.
        return None


def validate_performance_take(
    video_path: str,
    face_anchor: str,
    floor: float = DEFAULT_PERFORMANCE_FLOOR,
) -> Optional[float]:
    """Score a performance take against the character face anchor.

    Returns the ArcFace similarity in [0, 1] or None if the gate can't run.
    None should be treated as "inconclusive" — leave the auto-approve
    decision to the operator gate.
    """
    if not video_path or not os.path.exists(video_path):
        return None
    if not face_anchor or not os.path.exists(face_anchor):
        return None

    with tempfile.TemporaryDirectory() as td:
        frame_png = os.path.join(td, "sample.png")
        if not _extract_sample_frame(video_path, frame_png):
            return None
        return _arcface_score(frame_png, face_anchor)
```

- [ ] **Step 3.5: Run tests, verify green**

```bash
$PY -m pytest tests/unit/test_performance_identity_gate.py -v
```

- [ ] **Step 3.6: Wire into controller `_mut_success`**

In `cinema/shots/controller.py` around lines 584-595 (where `_mut_success` lives). Note: `project["characters"]` is a **list of dicts**, NOT a dict-of-id. Use the existing `get_reference_image(project, char_id)` helper from `character_manager` (already imported at line 87).

```python
# --- 5. Persist the take + identity-gate the auto-approve ---
take["path"] = perf_path

# Resolve the character's face anchor for the gate. Multi-character shots
# anchor on the first listed character — operators can override via the
# PERFORMANCE_REVIEW gate. Uses the existing character_manager helper that
# already understands the project's character list shape.
face_anchor = ""
chars = shot.get("characters_in_frame", []) or []
if chars:
    try:
        face_anchor = get_reference_image(project, chars[0]) or ""
    except Exception as e:
        print(f"[PERFORMANCE] face_anchor lookup failed for {chars[0]}: {e}")
        face_anchor = ""

from performance.identity_gate import validate_performance_take, DEFAULT_PERFORMANCE_FLOOR
arc_score = validate_performance_take(perf_path, face_anchor) if face_anchor else None
gate_passed = (arc_score is None) or (arc_score >= DEFAULT_PERFORMANCE_FLOOR)

def _mut_success(_scene: dict, project_shot: dict):
    project_shot.setdefault("performance_takes", []).append(take)
    # Auto-approve ONLY when the identity gate passed (or was inconclusive).
    # A score below floor leaves approval to the operator via PERFORMANCE_REVIEW.
    if gate_passed and not project_shot.get("approved_performance_take_id"):
        project_shot["approved_performance_take_id"] = take["id"]
    project_shot["performance_engine"] = engine
    # Stash the score for the review UI to surface.
    take.setdefault("metadata", {})["identity_score"] = arc_score
    return MutationResult(take, save=True)
```

When gate fails, emit a separate progress event so the UI surfaces it:

```python
if not gate_passed:
    self.progress(
        "PERFORMANCE_REVIEW_REQUIRED",
        f"Shot {shot_id}: identity score {arc_score:.3f} below floor "
        f"{DEFAULT_PERFORMANCE_FLOOR}; awaiting operator review",
        -1, scene_id=scene_id, shot_id=shot_id, take_id=take["id"],
        identity_score=arc_score,
    )
```

- [ ] **Step 3.7: Run §0 smoke**

Per [docs/REFACTOR_HANDOFF.md](../../REFACTOR_HANDOFF.md) §0.

- [ ] **Step 3.8: Commit**

```bash
git add performance/identity_gate.py cinema/shots/controller.py tests/unit/test_performance_identity_gate.py
git commit -m "$(cat <<'EOF'
feat(performance): ArcFace gate on performance takes blocks silent drift

Performance engines (Act-One, LivePortrait, Viggle) can drift the
character's face. Previously every successful take auto-approved and
silently flowed to motion_render.

Add performance/identity_gate.py — samples one frame via ffmpeg, scores
via existing IdentityValidator. Score below DEFAULT_PERFORMANCE_FLOOR
(0.70) suppresses auto-approve, leaving the decision to the operator's
PERFORMANCE_REVIEW gate. Inconclusive (no anchor, no ffmpeg, no face)
preserves previous behavior — auto-approve.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Chunk 2 — P1 Resilience (Slices 4-6)

Reduces duplication and adds the concurrency primitives that future shot-level parallelism will need. Order matters: do Slice 4 first (the normalizer is referenced by future routing edits), then 5 (independent), then 6 (depends on nothing).

---

### Slice 4: Canonical shot-type normalizer

**Why:** [domain/performance.py:121](domain/performance.py:121) hardcodes `("portrait", "medium", "close-up", "closeup", "close_up", "ecu")`. The classifier in `workflow_selector` is the source of truth, but there's no shared normalizer. A typo silently routes to default.

**Files:**
- Create: `domain/shot_types.py`
- Modify: `domain/performance.py` — import + use the normalizer
- Create: `tests/unit/test_shot_types.py`

**Pre-edit impact check:**

```bash
grep -rn "classify_shot_type\|shot_type" /Users/hyungkoookkim/Content --include="*.py" | grep -v ".venv\|__pycache__\|tests/" | wc -l
```

Expect 20-40 hits. We're only changing `domain/performance.py`'s usage — other callers continue to use `workflow_selector.classify_shot_type` unchanged.

- [ ] **Step 4.1: Write failing test**

Create `tests/unit/test_shot_types.py`:

```python
"""Tests for domain/shot_types.py — canonical shot-type names + normalizer."""
from __future__ import annotations

import pytest

from domain.shot_types import (
    SHOT_TYPE_CLOSE, SHOT_TYPE_PORTRAIT, SHOT_TYPE_MEDIUM,
    SHOT_TYPE_WIDE, SHOT_TYPE_LANDSCAPE, SHOT_TYPE_ACTION,
    FACE_READABLE_SHOTS,
    normalize_shot_type,
)


class TestNormalize:
    @pytest.mark.parametrize("alias,expected", [
        ("close-up", SHOT_TYPE_CLOSE),
        ("CLOSE-UP", SHOT_TYPE_CLOSE),
        ("closeup", SHOT_TYPE_CLOSE),
        ("close_up", SHOT_TYPE_CLOSE),
        ("ecu", SHOT_TYPE_CLOSE),
        ("portrait", SHOT_TYPE_PORTRAIT),
        ("medium", SHOT_TYPE_MEDIUM),
        ("wide", SHOT_TYPE_WIDE),
        ("landscape", SHOT_TYPE_LANDSCAPE),
        ("action", SHOT_TYPE_ACTION),
    ])
    def test_known_aliases(self, alias, expected):
        assert normalize_shot_type(alias) == expected

    def test_empty_string(self):
        assert normalize_shot_type("") == ""

    def test_none(self):
        assert normalize_shot_type(None) == ""

    def test_unknown_passes_through_lowercased(self):
        # An unknown shot type still normalizes to lowercase — caller's
        # branches fall through, no silent rename.
        assert normalize_shot_type("OVER_SHOULDER") == "over_shoulder"


class TestFaceReadableSet:
    def test_close_is_face_readable(self):
        assert SHOT_TYPE_CLOSE in FACE_READABLE_SHOTS

    def test_portrait_is_face_readable(self):
        assert SHOT_TYPE_PORTRAIT in FACE_READABLE_SHOTS

    def test_medium_is_face_readable(self):
        assert SHOT_TYPE_MEDIUM in FACE_READABLE_SHOTS

    def test_landscape_is_not_face_readable(self):
        assert SHOT_TYPE_LANDSCAPE not in FACE_READABLE_SHOTS
```

- [ ] **Step 4.2: Run test, verify fail**

```bash
$PY -m pytest tests/unit/test_shot_types.py -v
```

Expected: `ModuleNotFoundError: No module named 'domain.shot_types'`.

- [ ] **Step 4.3: Implement `domain/shot_types.py`**

```python
"""Canonical shot-type constants + alias normalizer.

WHY THIS EXISTS
---------------
Three places in the codebase compare shot_type strings (workflow_selector,
domain/performance, future scene-decomposer). Each had its own spelling
preferences ("close-up" vs "close_up" vs "closeup"), and any drift silently
routes to a default. This module is the single source.
"""
from __future__ import annotations

from typing import Optional


# Canonical names — use these constants in conditionals, never raw strings.
SHOT_TYPE_CLOSE     = "close_up"
SHOT_TYPE_PORTRAIT  = "portrait"
SHOT_TYPE_MEDIUM    = "medium"
SHOT_TYPE_WIDE      = "wide"
SHOT_TYPE_LANDSCAPE = "landscape"
SHOT_TYPE_ACTION    = "action"


# Alias table — maps lowercased input to canonical. Add new aliases here,
# not in the consumers.
_ALIASES = {
    "close-up": SHOT_TYPE_CLOSE,
    "closeup":  SHOT_TYPE_CLOSE,
    "close_up": SHOT_TYPE_CLOSE,
    "ecu":      SHOT_TYPE_CLOSE,
}


def normalize_shot_type(raw: Optional[str]) -> str:
    """Lowercase + dealias. Unknown values pass through lowercased."""
    s = (raw or "").lower().strip()
    return _ALIASES.get(s, s)


# Set of shot types where the face is large enough to retarget meaningfully.
# Used by domain.performance for ACT_ONE / LIVE_PORTRAIT routing.
#
# NOTE: the previous 6-string tuple ("portrait", "medium", "close-up", "closeup",
# "close_up", "ecu") was 6 ALIASES for 3 distinct types. The 4 close-up aliases
# all collapse to SHOT_TYPE_CLOSE via normalize_shot_type() before the
# `in FACE_READABLE_SHOTS` check, so coverage is preserved.
FACE_READABLE_SHOTS = frozenset({
    SHOT_TYPE_CLOSE,
    SHOT_TYPE_PORTRAIT,
    SHOT_TYPE_MEDIUM,
})
```

- [ ] **Step 4.4: Run tests, verify green**

```bash
$PY -m pytest tests/unit/test_shot_types.py -v
```

- [ ] **Step 4.5: Refactor `domain/performance.py` to use the normalizer**

Replace the inline `_shot_type` + hardcoded tuple. In `domain/performance.py`:

```python
# Add import at top
from domain.shot_types import (
    SHOT_TYPE_LANDSCAPE, SHOT_TYPE_WIDE, SHOT_TYPE_ACTION,
    FACE_READABLE_SHOTS, normalize_shot_type,
)

# Replace _shot_type
def _shot_type(shot: dict) -> str:
    """Pull the shot type with a sensible default. Normalized canonical form."""
    t = shot.get("shot_type") or shot.get("shot_class") or ""
    if t:
        return normalize_shot_type(t)
    try:
        from workflow_selector import classify_shot_type
        return normalize_shot_type(classify_shot_type(shot))
    except Exception:
        return ""

# Replace the SKIP rules in should_capture:
def should_capture(shot, scene=None):
    if not _has_characters(shot):
        return False
    st = _shot_type(shot)
    if st == SHOT_TYPE_LANDSCAPE:
        return False
    if st == SHOT_TYPE_WIDE and not _has_dialogue(shot):
        return False
    return True

# In route_performance_engine, replace the 6-string tuple:
if has_dlg and st in FACE_READABLE_SHOTS:
    ...

# And the VIGGLE check:
if not has_dlg and st == SHOT_TYPE_ACTION:
    return ENGINE_VIGGLE
```

- [ ] **Step 4.6: Run routing tests (Slice 1's), verify still green**

```bash
$PY -m pytest tests/unit/test_domain_performance.py tests/unit/test_shot_types.py -v
```

Expected: all green. If any routing test fails, your refactor changed behavior — fix the refactor, not the test.

- [ ] **Step 4.7: Run §0 smoke**

- [ ] **Step 4.8: Commit**

```bash
git add domain/shot_types.py domain/performance.py tests/unit/test_shot_types.py
git commit -m "$(cat <<'EOF'
refactor(domain): extract canonical shot-type normalizer

domain.performance had a 6-string tuple of close-up spellings inline.
Move to domain/shot_types.py with explicit constants + alias table.
Routing tests from the previous slice catch any behavior drift.

No behavior change. Future consumers (scene_decomposer, workflow_selector)
should adopt the same normalizer.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Slice 5: Shared polling helper

**Why:** Four adapters duplicate `while time.time()-start < timeout: poll; sleep`. Provider-specific status enums get normalized inconsistently. One module = one place to fix.

This slice spans **5 commits** (helper + tests, then one refactor per adapter) to keep each diff small enough to review and revert if needed.

**Files:**
- Create: `performance/_poll.py`
- Create: `tests/unit/test_performance_poll.py`
- Modify (each in its own commit): `performance/act_one.py`, `performance/viggle.py`, `performance/live_portrait.py`, `performance/driving_video.py`

- [ ] **Step 5.1: Write failing test**

Create `tests/unit/test_performance_poll.py`:

```python
"""Tests for performance/_poll.py — generic task poller."""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from performance._poll import poll_task


class TestSuccess:
    def test_immediate_success(self):
        get_status = MagicMock(return_value={"status": "SUCCEEDED"})
        result = poll_task(get_status, success_states={"SUCCEEDED"}, terminal_states={"FAILED"},
                          interval_s=0.01, timeout_s=1.0)
        assert result == {"status": "SUCCEEDED"}
        assert get_status.call_count == 1

    def test_case_normalization(self):
        # Caller passes uppercase set; poller normalizes incoming status.
        get_status = MagicMock(return_value={"status": "succeeded"})
        result = poll_task(get_status, success_states={"SUCCEEDED"}, terminal_states={"FAILED"},
                          interval_s=0.01, timeout_s=1.0)
        assert result is not None

    def test_eventual_success(self):
        # First two polls "PROCESSING", third "SUCCEEDED"
        get_status = MagicMock(side_effect=[
            {"status": "PROCESSING"}, {"status": "PROCESSING"}, {"status": "SUCCEEDED"},
        ])
        result = poll_task(get_status, success_states={"SUCCEEDED"}, terminal_states={"FAILED"},
                          interval_s=0.01, timeout_s=1.0)
        assert result == {"status": "SUCCEEDED"}
        assert get_status.call_count == 3


class TestTerminal:
    def test_terminal_failure_returns_none(self):
        get_status = MagicMock(return_value={"status": "FAILED"})
        result = poll_task(get_status, success_states={"SUCCEEDED"}, terminal_states={"FAILED", "CANCELLED"},
                          interval_s=0.01, timeout_s=1.0)
        assert result is None

    def test_terminal_cancelled_returns_none(self):
        get_status = MagicMock(return_value={"status": "CANCELLED"})
        result = poll_task(get_status, success_states={"SUCCEEDED"}, terminal_states={"FAILED", "CANCELLED"},
                          interval_s=0.01, timeout_s=1.0)
        assert result is None


class TestTimeout:
    def test_timeout_returns_none(self):
        get_status = MagicMock(return_value={"status": "PROCESSING"})
        start = time.time()
        result = poll_task(get_status, success_states={"SUCCEEDED"}, terminal_states={"FAILED"},
                          interval_s=0.05, timeout_s=0.2)
        elapsed = time.time() - start
        assert result is None
        assert 0.15 <= elapsed <= 0.5  # roughly timeout_s, with poll overhead


class TestResilience:
    def test_get_status_exception_keeps_polling(self):
        # Transient exception (e.g., network blip) shouldn't abort the loop.
        get_status = MagicMock(side_effect=[
            RuntimeError("blip"), {"status": "SUCCEEDED"},
        ])
        result = poll_task(get_status, success_states={"SUCCEEDED"}, terminal_states={"FAILED"},
                          interval_s=0.01, timeout_s=1.0)
        assert result == {"status": "SUCCEEDED"}
        assert get_status.call_count == 2
```

- [ ] **Step 5.2: Run test, verify fail (module missing)**

```bash
$PY -m pytest tests/unit/test_performance_poll.py -v
```

- [ ] **Step 5.3: Implement `performance/_poll.py`**

```python
"""Generic task poller for the performance/ adapters.

Each external engine (Runway / Hedra / Viggle / ComfyUI) exposes a polling
endpoint with its own status enum. This helper normalizes the loop:
case-insensitive status comparison, exception-tolerant single-poll failures,
and a clean None return on terminal-state or timeout.
"""
from __future__ import annotations

import time
from typing import Callable, Optional, Set


def poll_task(
    get_status: Callable[[], dict],
    *,
    success_states: Set[str],
    terminal_states: Set[str],
    interval_s: float = 3.0,
    timeout_s: float = 300.0,
) -> Optional[dict]:
    """Poll `get_status()` until success, terminal, or timeout.

    Args:
        get_status: callable returning {"status": "...", ...} per call.
            Exceptions raised here are caught — single-poll failures are
            transient (network blips) and shouldn't abort the loop.
        success_states: states the caller wants to keep polling for. The
            status field is uppercased before comparison; pass uppercase
            states for clarity. (Comparisons are case-insensitive.)
        terminal_states: states that mean "give up, no point continuing".
        interval_s: sleep between polls.
        timeout_s: hard ceiling.

    Returns:
        The status dict on success, or None on terminal/timeout.
    """
    success_upper = {s.upper() for s in success_states}
    terminal_upper = {s.upper() for s in terminal_states}
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            status = get_status()
        except Exception:
            # Transient — sleep and retry. Don't print here; callers' adapter
            # code already prints provider-tagged diagnostics on their own
            # exceptions if they want.
            time.sleep(interval_s)
            continue
        state = (status.get("status") or "").upper()
        if state in success_upper:
            return status
        if state in terminal_upper:
            return None
        time.sleep(interval_s)
    return None
```

- [ ] **Step 5.4: Run tests, verify green**

```bash
$PY -m pytest tests/unit/test_performance_poll.py -v
```

- [ ] **Step 5.5: Commit helper**

```bash
git add performance/_poll.py tests/unit/test_performance_poll.py
git commit -m "$(cat <<'EOF'
feat(performance): extract shared poll_task helper

Four adapters duplicated a polling loop with provider-specific status
normalization. Adding the helper alone — refactoring each adapter to
use it lands in follow-up commits so each can be reviewed and reverted
independently.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5.6: Refactor `performance/act_one.py`**

Replace the SDK-path polling loop (lines 100-120) with `poll_task`. Same for the REST fallback (`_raw_rest_call`, lines 188-208). Behavior unchanged.

**Runway status enum:** `SUCCEEDED` (success), `FAILED` / `CANCELLED` (terminal), anything else = keep polling.

SDK-path closure example:

```python
from performance._poll import poll_task

def _get_status_sdk():
    t = client.tasks.retrieve(id=task.id)
    return {
        "status": getattr(t, "status", "").upper(),
        "output": getattr(t, "output", None),
        "failure": getattr(t, "failure", None),
    }

final = poll_task(
    _get_status_sdk,
    success_states={"SUCCEEDED"},
    terminal_states={"FAILED", "CANCELLED"},
    interval_s=_POLL_INTERVAL_S,
    timeout_s=poll_timeout_s,
)
if final is None:
    print("   [ACT-ONE] poll terminal or timed out")
    return None
out_url = (final.get("output") or [None])[0]
if not out_url or not safe_download(out_url, output_mp4):
    return None
# … rest unchanged (cost log + print + return)
```

REST-path closure follows the same shape but builds the status dict from `requests.get(...).json()`. Both paths use the same `poll_task` helper.

After edit, run:
```bash
$PY -m pytest tests/unit/test_performance_poll.py -v && \
$PY -c "from performance.act_one import generate_act_one_performance; print('OK')"
```

Commit:
```bash
git add performance/act_one.py
git commit -m "refactor(performance): act_one uses poll_task helper

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 5.7: Refactor `performance/viggle.py`**

Replace lines 94-108 (job-id polling).

**Viggle status enum:** historically lowercase `complete` / `done` / `succeeded` (success), `failed` / `error` (terminal). `poll_task` uppercases incoming statuses before comparison, so case differences are absorbed.

Closure shape:

```python
def _get_status():
    pr = requests.get(
        f"https://api.viggle.ai/v1/jobs/{job_id}",
        headers=auth_headers, timeout=15,
    )
    if not pr.ok:
        return {"status": "PENDING"}  # treat non-2xx as "keep polling"
    pb = pr.json()
    return {
        "status": (pb.get("status") or "").upper(),
        "output_url": pb.get("output_url") or pb.get("video_url"),
    }

final = poll_task(
    _get_status,
    success_states={"COMPLETE", "DONE", "SUCCEEDED"},
    terminal_states={"FAILED", "ERROR"},
    interval_s=_POLL_INTERVAL_S,
    timeout_s=poll_timeout_s,
)
out_url = final.get("output_url") if final else None
```

Commit individually.

- [ ] **Step 5.8: Refactor `performance/live_portrait.py`**

Replace lines 120-148. ComfyUI uses a different shape — the history endpoint has no `status` field at the top level; you check whether the `prompt_id` key exists in the response and whether `outputs` is populated.

**Closure shape** (synthesize a status dict from the ComfyUI shape):

```python
def _get_status():
    hr = requests.get(f"{server_url}/history/{prompt_id}", timeout=15)
    if not hr.ok or prompt_id not in hr.json():
        return {"status": "PROCESSING"}
    hist = hr.json()[prompt_id]
    inner = hist.get("status", {})
    if inner.get("status_str") == "error":
        return {"status": "FAILED", "messages": inner.get("messages", [])}
    if hist.get("outputs"):
        return {"status": "SUCCEEDED", "outputs": hist["outputs"]}
    return {"status": "PROCESSING"}

final = poll_task(
    _get_status,
    success_states={"SUCCEEDED"},
    terminal_states={"FAILED"},
    interval_s=_POLL_INTERVAL_S,
    timeout_s=poll_timeout_s,
)
if not final:
    return None
# Extract the video output from final["outputs"] — preserve existing logic
# from lines 125-138 verbatim, just operating on `final["outputs"]` instead
# of `hist["outputs"]`.
```

Test by running §0 smoke + a manual sanity ping against a known-good ComfyUI pod URL if accessible.

- [ ] **Step 5.9: Refactor `performance/driving_video.py`**

Two poll loops here: `_synth_via_hedra` (lines 107-121) and `_synth_via_sadtalker` (lines 191-216).

**Hedra status enum:** lowercase `complete` / `done` / `succeeded` (success), `failed` / `error` (terminal).
**SadTalker via ComfyUI:** identical shape to `live_portrait.py` Step 5.8 — synthesize the status dict from the history response.

Closure shape for Hedra (REST path, around line 108):

```python
def _get_status():
    pr = requests.get(
        f"https://api.hedra.com/v1/jobs/{job_id}",
        headers={"Authorization": f"Bearer {api_key}"}, timeout=15,
    )
    if not pr.ok:
        return {"status": "PENDING"}
    pb = pr.json()
    return {
        "status": (pb.get("status") or "").upper(),
        "video_url": pb.get("video_url") or pb.get("output_url"),
    }

final = poll_task(_get_status,
    success_states={"COMPLETE", "DONE", "SUCCEEDED"},
    terminal_states={"FAILED", "ERROR"},
    interval_s=_HEDRA_POLL_INTERVAL_S,
    timeout_s=_HEDRA_POLL_TIMEOUT_S)
out_url = final.get("video_url") if final else None
```

One commit per poll-loop replacement is fine if you want extra granularity.

- [ ] **Step 5.10: Final §0 smoke after all refactors**

Run the full smoke block. Confirm every adapter still imports + the four adapter modules' functions exist with the same names:

```bash
$PY -c "
from performance.act_one import generate_act_one_performance
from performance.viggle import generate_viggle_performance
from performance.live_portrait import generate_live_portrait_performance
from performance.driving_video import synth_driving_face_from_audio
print('OK all four adapters import after poll refactor')
"
```

---

### Slice 6: Per-provider concurrency cap

**Why:** Today all shots run serially. The moment shot-level parallelism lands, a 12-shot batch will hammer Hedra/Runway simultaneously and trigger throttling. Add a semaphore *now* — it's a 5-line change and future-proofs.

**Files:**
- Modify: `performance/_router.py`
- Create: `tests/unit/test_router_semaphore.py`

- [ ] **Step 6.1: Write failing test**

Note: we expose a public `_SEMAPHORE_LIMITS` constant alongside the private `_SEMAPHORES` dict so tests assert against the limits without poking `threading.Semaphore._value` (private CPython detail).

```python
"""Tests for performance/_router.py — per-provider concurrency cap."""
from __future__ import annotations

import threading
import time
from unittest.mock import patch

import pytest

from performance._router import dispatch, _SEMAPHORE_LIMITS


class TestSemaphoreConfig:
    def test_each_engine_has_a_limit(self):
        assert "ACT_ONE" in _SEMAPHORE_LIMITS
        assert "LIVE_PORTRAIT" in _SEMAPHORE_LIMITS
        assert "VIGGLE" in _SEMAPHORE_LIMITS

    def test_limits_are_positive_ints(self):
        for engine, limit in _SEMAPHORE_LIMITS.items():
            assert isinstance(limit, int)
            assert limit >= 1


class TestSemaphoreEnforcement:
    def test_act_one_concurrency_capped(self, tmp_path):
        """Spawn 4 threads; max simultaneous in-flight must equal the cap."""
        in_flight = 0
        max_in_flight = 0
        lock = threading.Lock()

        def slow_stub(*a, **kw):
            nonlocal in_flight, max_in_flight
            with lock:
                in_flight += 1
                max_in_flight = max(max_in_flight, in_flight)
            time.sleep(0.05)
            with lock:
                in_flight -= 1
            return str(tmp_path / "out.mp4")

        with patch("performance.act_one.generate_act_one_performance", slow_stub):
            threads = [
                threading.Thread(target=lambda i=i: dispatch(
                    "ACT_ONE",
                    keyframe_path=str(tmp_path / "kf.png"),
                    audio_path=str(tmp_path / "a.wav"),
                    driving_video_path=None,
                    output_mp4=str(tmp_path / f"out{i}.mp4"),
                ))
                for i in range(4)
            ]
            for t in threads: t.start()
            for t in threads: t.join()

        # max-in-flight must NOT exceed the configured limit
        assert max_in_flight <= _SEMAPHORE_LIMITS["ACT_ONE"]
        # And with 4 contending threads on a 1-cap, peak should hit exactly 1
        assert max_in_flight == _SEMAPHORE_LIMITS["ACT_ONE"]
```

- [ ] **Step 6.2: Run, verify fail (import of `_SEMAPHORE_LIMITS` fails)**

- [ ] **Step 6.3: Modify `performance/_router.py`**

Rename the existing top-level `dispatch` function body to `_dispatch_inner`, then add the semaphore wrapper. Explicit extraction:

**Before** (current shape):
```python
def dispatch(engine, *, keyframe_path, audio_path, driving_video_path, output_mp4, ...):
    if engine == ENGINE_SKIP or not engine:
        return None
    if engine == ENGINE_ACT_ONE:
        ...  # existing branches unchanged
```

**After** — three changes:

1. Add `import threading` at module top.
2. Add the two new module-level constants right after the import block:

```python
# Per-provider concurrency caps. Conservative defaults — Runway and Viggle
# bill per-job and rate-limit hard; LivePortrait runs on our own pod and
# can take a couple in flight. Tune via settings later if needed.
_SEMAPHORE_LIMITS = {
    "ACT_ONE":       1,
    "LIVE_PORTRAIT": 2,
    "VIGGLE":        1,
}
_SEMAPHORES = {
    engine: threading.Semaphore(limit)
    for engine, limit in _SEMAPHORE_LIMITS.items()
}
```

3. Rename existing `def dispatch(...)` to `def _dispatch_inner(...)`, then add a new thin `dispatch` that wraps it:

```python
def dispatch(engine, *, keyframe_path, audio_path, driving_video_path,
             output_mp4, duration_s=5.0, shot_id="", video_id=""):
    """Public entry. Acquires per-provider semaphore, then delegates."""
    if engine == ENGINE_SKIP or not engine:
        return None
    sem = _SEMAPHORES.get(engine)
    if sem is None:
        return _dispatch_inner(engine, keyframe_path=keyframe_path,
                               audio_path=audio_path,
                               driving_video_path=driving_video_path,
                               output_mp4=output_mp4, duration_s=duration_s,
                               shot_id=shot_id, video_id=video_id)
    with sem:
        return _dispatch_inner(engine, keyframe_path=keyframe_path,
                               audio_path=audio_path,
                               driving_video_path=driving_video_path,
                               output_mp4=output_mp4, duration_s=duration_s,
                               shot_id=shot_id, video_id=video_id)
```

The renamed `_dispatch_inner` keeps the existing engine branching unchanged.

- [ ] **Step 6.4: Run tests, verify green**

```bash
$PY -m pytest tests/unit/test_router_semaphore.py -v
```

- [ ] **Step 6.5: §0 smoke + commit**

```bash
git add performance/_router.py tests/unit/test_router_semaphore.py
git commit -m "feat(performance): per-provider semaphores in dispatch

Future shot-level parallelism would otherwise hammer Hedra/Runway with
12+ concurrent jobs from a single render. Adds threading.Semaphore caps
per engine (ACT_ONE=1, LIVE_PORTRAIT=2, VIGGLE=1) inside dispatch.

Serial behavior is preserved when only one shot runs at a time.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Chunk 3 — P2 Observability / Cost (Slices 7-8)

These don't change behavior — they record which Mode-B engine ran and avoid paying Hedra twice for the same audio+keyframe.

---

### Slice 7: Mode-B provider tracking

**Why:** When `synth_driving_face_from_audio` succeeds via Hedra-FAL vs SadTalker, the controller can't tell. Performance quality debugging requires log archaeology.

**Files:**
- Modify: `performance/driving_video.py` — change return type to `(path, provider) | None`
- Modify: `cinema/shots/controller.py:512-526` — capture provider, thread into take metadata
- Modify: `tests/unit/test_performance_poll.py` — add a tiny test confirming the tuple shape (or add a new dedicated test file)

- [ ] **Step 7.1: Pre-edit impact check**

```bash
# Run via your GitNexus MCP if available.
grep -rn "synth_driving_face_from_audio" --include="*.py" /Users/hyungkoookkim/Content | grep -v ".venv\|__pycache__"
```

Expect 1 caller (controller). Return-type change = backward-incompatible at d=1. Update callsite in the same commit.

- [ ] **Step 7.2: Write failing test**

Create `tests/unit/test_driving_video_provider.py`:

```python
"""Confirms synth_driving_face_from_audio returns (path, provider_name)."""
from __future__ import annotations

from unittest.mock import patch

from performance.driving_video import synth_driving_face_from_audio


def test_returns_tuple_with_provider(tmp_path):
    audio = tmp_path / "a.wav"; audio.write_bytes(b"\x00")
    kf = tmp_path / "kf.png";   kf.write_bytes(b"\x00")
    out = tmp_path / "out.mp4"

    with patch("performance.driving_video._synth_via_hedra", return_value=str(out)):
        result = synth_driving_face_from_audio(
            audio_path=str(audio), keyframe_path=str(kf), output_mp4=str(out),
        )
    assert result == (str(out), "hedra")


def test_returns_none_when_all_fail(tmp_path):
    audio = tmp_path / "a.wav"; audio.write_bytes(b"\x00")
    kf = tmp_path / "kf.png";   kf.write_bytes(b"\x00")
    out = tmp_path / "out.mp4"

    with patch("performance.driving_video._synth_via_hedra", return_value=None), \
         patch("performance.driving_video._synth_via_sadtalker", return_value=None):
        result = synth_driving_face_from_audio(
            audio_path=str(audio), keyframe_path=str(kf), output_mp4=str(out),
        )
    assert result is None
```

- [ ] **Step 7.3: Modify `synth_driving_face_from_audio`**

In `performance/driving_video.py`:

```python
from typing import Optional, Tuple

def synth_driving_face_from_audio(
    audio_path: str,
    keyframe_path: str,
    output_mp4: str,
    *,
    duration_s: float = 5.0,
    engine: str = "auto",
    shot_id: str = "",
    video_id: str = "",
) -> Optional[Tuple[str, str]]:
    """... (updated docstring)

    Returns:
        (path, provider_name) tuple on success — provider_name is one of
        {"hedra", "sadtalker"}. None on full failure.
    """
    if not (audio_path and os.path.exists(audio_path)):
        return None
    if not (keyframe_path and os.path.exists(keyframe_path)):
        return None

    if engine in ("auto", "hedra"):
        r = _synth_via_hedra(audio_path, keyframe_path, output_mp4, duration_s, shot_id, video_id)
        if r:
            return (r, "hedra")
        if engine == "hedra":
            return None

    if engine in ("auto", "sadtalker"):
        r = _synth_via_sadtalker(audio_path, keyframe_path, output_mp4, duration_s, shot_id, video_id)
        if r:
            return (r, "sadtalker")

    return None
```

- [ ] **Step 7.4: Update controller caller (`cinema/shots/controller.py:512-526`)**

**Critical:** `driving_provider` MUST be initialized before the Mode-A/B branch — otherwise Mode A (operator-uploaded driving video) skips the entire `if not driving and source_mode == "tts_auto"` block and the variable never exists, triggering a NameError at the take-metadata write.

```python
# Initialize BEFORE the branch so Mode A (operator upload) doesn't NameError.
# Mode A reuses the operator's video → no synth → provider stays None.
driving_provider: Optional[str] = None

if not driving and source_mode == "tts_auto" and audio_path:
    try:
        from performance.driving_video import synth_driving_face_from_audio
        temp_driving = self._take_output_path(shot_id, f"driving_{keyframe_take_id}", ".mp4")
        synth_result = synth_driving_face_from_audio(
            audio_path=audio_path,
            keyframe_path=source_image,
            output_mp4=temp_driving,
            duration_s=float(scene.get("duration_seconds", 5.0)),
            shot_id=shot_id, video_id=str(project.get("id", "")),
        )
        if synth_result:
            driving, driving_provider = synth_result
    except Exception as e:
        print(f"[PERFORMANCE] driving-video synth failed ({e}); engine may degrade")
```

Then thread `driving_provider` into take metadata (line 532):

```python
"driving_provider": driving_provider,  # "hedra" | "sadtalker" | "cache" | None
```

(`"cache"` shows up here once Slice 8 lands — it's a load-bearing observability value.)

- [ ] **Step 7.5: §0 smoke + commit**

```bash
git add performance/driving_video.py cinema/shots/controller.py tests/unit/test_driving_video_provider.py
git commit -m "feat(performance): driving-video synth returns (path, provider)

Performance debugging needs to know which Mode-B engine produced the
driving reference. synth_driving_face_from_audio now returns a tuple
on success; controller threads the provider name into take metadata
under driving_provider.

Single d=1 caller (controller) updated in same commit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Slice 8: Content-hash cache for driving-video synth

**Why:** Hedra runs $0.05+ per synth. The operator's "regenerate performance" button currently re-synthesizes the driving video even when audio+keyframe are unchanged. Cache by content hash.

**Files:**
- Create: `performance/_cache.py`
- Modify: `performance/driving_video.py` — check cache before calling providers
- Create: `tests/unit/test_performance_cache.py`

- [ ] **Step 8.1: Write failing test**

```python
"""Tests for performance/_cache.py — content-hash cache for driving synth."""
from __future__ import annotations

import os

import pytest

from performance._cache import driving_cache_key, lookup_cache, store_cache


def test_hash_stable_for_same_content(tmp_path):
    a1 = tmp_path / "a1.wav"; a1.write_bytes(b"abc")
    a2 = tmp_path / "a2.wav"; a2.write_bytes(b"abc")  # same content, different path
    kf = tmp_path / "kf.png"; kf.write_bytes(b"xyz")
    k1 = driving_cache_key(str(a1), str(kf), duration_s=5.0)
    k2 = driving_cache_key(str(a2), str(kf), duration_s=5.0)
    assert k1 == k2


def test_hash_differs_for_different_audio(tmp_path):
    a1 = tmp_path / "a1.wav"; a1.write_bytes(b"abc")
    a2 = tmp_path / "a2.wav"; a2.write_bytes(b"xyz")  # different content
    kf = tmp_path / "kf.png"; kf.write_bytes(b"xyz")
    assert driving_cache_key(str(a1), str(kf), 5.0) != driving_cache_key(str(a2), str(kf), 5.0)


def test_lookup_misses_when_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("PERFORMANCE_CACHE_DIR", str(tmp_path / "cache"))
    a = tmp_path / "a.wav"; a.write_bytes(b"abc")
    kf = tmp_path / "kf.png"; kf.write_bytes(b"xyz")
    key = driving_cache_key(str(a), str(kf), 5.0)
    assert lookup_cache(key) is None


def test_store_then_lookup_hits(tmp_path, monkeypatch):
    monkeypatch.setenv("PERFORMANCE_CACHE_DIR", str(tmp_path / "cache"))
    a = tmp_path / "a.wav"; a.write_bytes(b"abc")
    kf = tmp_path / "kf.png"; kf.write_bytes(b"xyz")
    real_output = tmp_path / "real.mp4"; real_output.write_bytes(b"video-data")
    key = driving_cache_key(str(a), str(kf), 5.0)

    store_cache(key, str(real_output))
    cached = lookup_cache(key)

    assert cached is not None
    assert os.path.exists(cached)
    assert open(cached, "rb").read() == b"video-data"


def test_synth_returns_cache_provider_on_hit(tmp_path, monkeypatch):
    """End-to-end: prime cache, call synth, assert provider=='cache'."""
    from unittest.mock import patch
    from performance.driving_video import synth_driving_face_from_audio
    monkeypatch.setenv("PERFORMANCE_CACHE_DIR", str(tmp_path / "cache"))
    a = tmp_path / "a.wav"; a.write_bytes(b"audio-bytes")
    kf = tmp_path / "kf.png"; kf.write_bytes(b"keyframe-bytes")
    cached_video = tmp_path / "cached.mp4"; cached_video.write_bytes(b"prev")
    key = driving_cache_key(str(a), str(kf), 5.0)
    store_cache(key, str(cached_video))
    out = tmp_path / "out.mp4"
    # Hedra/SadTalker should NOT be called — cache hits short-circuit.
    with patch("performance.driving_video._synth_via_hedra") as mock_h, \
         patch("performance.driving_video._synth_via_sadtalker") as mock_s:
        result = synth_driving_face_from_audio(
            audio_path=str(a), keyframe_path=str(kf),
            output_mp4=str(out), duration_s=5.0,
        )
        assert result == (str(out), "cache")
        mock_h.assert_not_called()
        mock_s.assert_not_called()
```

- [ ] **Step 8.2: Implement `performance/_cache.py`**

```python
"""Content-hash cache for Mode-B driving-video synthesis.

WHY THIS EXISTS
---------------
Hedra Character-3 is ~$0.05/shot. The operator's "regenerate performance"
button currently re-synthesizes the driving face even when audio+keyframe
haven't changed. Caching by (audio_hash, keyframe_hash, duration) avoids
repeat charges.

The cache lives under PERFORMANCE_CACHE_DIR (env), defaulting to
data/cache/driving/. Cache entries are deduplicated by SHA-256.
"""
from __future__ import annotations

import hashlib
import os
import shutil
from typing import Optional


def _cache_dir() -> str:
    return os.environ.get("PERFORMANCE_CACHE_DIR", "data/cache/driving")


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def driving_cache_key(audio_path: str, keyframe_path: str, duration_s: float) -> str:
    """Stable key from audio bytes + keyframe bytes + duration."""
    parts = [
        _sha256_file(audio_path),
        _sha256_file(keyframe_path),
        f"{round(float(duration_s), 2)}",
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _cache_path(key: str) -> str:
    return os.path.join(_cache_dir(), f"{key}.mp4")


def lookup_cache(key: str) -> Optional[str]:
    """Return the cached path if present, else None."""
    p = _cache_path(key)
    return p if os.path.exists(p) else None


def store_cache(key: str, source_path: str) -> Optional[str]:
    """Copy source_path into the cache under `key`. Returns the cached path."""
    if not os.path.exists(source_path):
        return None
    os.makedirs(_cache_dir(), exist_ok=True)
    dst = _cache_path(key)
    shutil.copyfile(source_path, dst)
    return dst
```

- [ ] **Step 8.3: Wire cache into `synth_driving_face_from_audio`**

**Critical ordering:** the cache key calls `_sha256_file(audio_path)` which raises `FileNotFoundError` if the file doesn't exist. The cache short-circuit MUST sit AFTER the existing `os.path.exists` guards (current lines 243-246), not before them.

```python
# In synth_driving_face_from_audio, after the existing guard block:
if not (audio_path and os.path.exists(audio_path)):
    return None
if not (keyframe_path and os.path.exists(keyframe_path)):
    return None

# --- NEW: content-hash cache check (must come AFTER existence guards) ---
from performance._cache import driving_cache_key, lookup_cache, store_cache
import shutil

key = driving_cache_key(audio_path, keyframe_path, duration_s)
cached = lookup_cache(key)
if cached:
    # Copy cache → output_mp4 so caller's expected path still resolves.
    shutil.copyfile(cached, output_mp4)
    print(f"   ✅ Driving-video cache hit: {cached}")
    return (output_mp4, "cache")
# --- end cache check ---

# Existing provider cascade follows unchanged, EXCEPT each success branch
# now also calls store_cache:
if engine in ("auto", "hedra"):
    r = _synth_via_hedra(audio_path, keyframe_path, output_mp4, duration_s, shot_id, video_id)
    if r:
        store_cache(key, output_mp4)
        return (r, "hedra")
    if engine == "hedra":
        return None

if engine in ("auto", "sadtalker"):
    r = _synth_via_sadtalker(audio_path, keyframe_path, output_mp4, duration_s, shot_id, video_id)
    if r:
        store_cache(key, output_mp4)
        return (r, "sadtalker")

return None
```

Note: cache returns provider name `"cache"` — load-bearing for observability dashboards. The controller's Slice 7 patch already accepts this value (commented in the metadata dict).

- [ ] **Step 8.4: Run all performance tests, verify green**

```bash
$PY -m pytest tests/unit/test_performance_*.py tests/unit/test_domain_performance.py tests/unit/test_shot_types.py tests/unit/test_router_semaphore.py tests/unit/test_driving_video_provider.py -v
```

- [ ] **Step 8.5: §0 smoke + commit**

```bash
git add performance/_cache.py performance/driving_video.py tests/unit/test_performance_cache.py
git commit -m "feat(performance): content-hash cache for Mode-B driving-video synth

Hedra is ~\$0.05/shot. The operator's regenerate button re-synthesized
the driving face on each click even with unchanged inputs. Cache by
sha256(audio) + sha256(keyframe) + duration under data/cache/driving/.
Cache hits surface as provider='cache' in take metadata.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

After all 8 slices land:

- [ ] **Full test suite passes**

```bash
$PY -m pytest tests/unit/ -v
```

- [ ] **Full §0 smoke block green** (from [docs/REFACTOR_HANDOFF.md](../../REFACTOR_HANDOFF.md))

- [ ] **GitNexus index refresh**

```bash
npx gitnexus analyze
```

(If embeddings were previously generated: `npx gitnexus analyze --embeddings`)

- [ ] **Run `gitnexus_detect_changes` to confirm scope**

```
gitnexus_detect_changes({scope: "all"})
```

Expected: changes confined to `performance/`, `domain/performance.py`, `domain/shot_types.py`, `cinema/shots/controller.py:452-610`, plus the 7 new test files.

---

## Consequences

**What becomes easier:**
- Adding a 5th engine (Veo native performance, etc.) — drop a file in `performance/`, register one branch in `_router.py`, add tests against the canonical shot_types
- Cost auditing — provider name is now in take metadata
- Identity-quality bug reports — operators can quote the `identity_score` from the take

**What becomes harder:**
- Shot-level parallelism still needs work above the semaphore — but the semaphore is now in place when it lands
- Cache invalidation when a provider releases a quality improvement — operators will need a "clear performance cache" admin action

**What we may revisit:**
- `DEFAULT_PERFORMANCE_FLOOR = 0.70` — may want per-engine floors once you have data on ArcFace distributions per provider
- Semaphore values — `LIVE_PORTRAIT=2` is a guess; tune based on pod GPU memory observations
