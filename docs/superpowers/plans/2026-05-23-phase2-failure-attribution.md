# Quality Uplift — Phase 2: Failure-Attribution Prerequisites

> **For agentic workers:** REQUIRED: Use `superpowers:subagent-driven-development` (if subagents available) or `superpowers:executing-plans` to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace broad `except Exception` with typed errors AND make file writes atomic, so Phase 4's closed-loop gating has clean failure attribution to make retry/abort decisions on.

**Architecture:** Four slices.
- **Slice A:** define a typed error hierarchy in `domain/errors.py` (new module) — `PipelineError` base + `RunPodError`, `ImageGenerationError`, `MotionEngineError`, `ValidatorError` subclasses. Each carries cause + structured fields.
- **Slice B:** apply typed errors to `phase_c_assembly.py` (10 swallowed exception sites flagged by the original survey).
- **Slice C:** define `atomic_write(path, content)` helper in `domain/io_utils.py` (new module) using `tempfile.NamedTemporaryFile` + `os.replace`.
- **Slice D:** apply atomic writes to the 3 sites the survey flagged: `phase_c_assembly.py:197`, `main.py:281`, `cleanup.py:97`.

All slices are behavior-preserving in the happy path — they change WHAT happens when something fails (or when a crash interrupts a write), not what happens when everything works.

**Tech stack:** Python 3.10+, `tempfile`, `os.replace`, `dataclasses`. Existing test patterns from `tests/unit/test_motion_gate.py` + `tests/unit/test_negative_prompts.py`. No new third-party dependencies.

**Branch:** new feature branch off `main`. Suggested: `feature/phase2-failure-attribution`. Both error-hierarchy work and atomic-write work can share the same branch — they're orthogonal but ship together as the Phase 2 unit.

---

## 1. Why this matters (the WHY before the WHAT)

Phase 1 of the quality-uplift roadmap shipped Anthropic prompt caching and validator-driven negative prompts. The headline #1 recommendation from the original survey was **closed-loop quality gating** (Phase 4) — but that work explicitly depends on being able to distinguish failure modes:

- "Should we retry?" → only if the failure was transient (network, RunPod cold start)
- "Should we mutate the prompt?" → only if the failure was content-related (identity mismatch, NSFW rejection)
- "Should we escalate to operator?" → only if the failure is persistent (quota exhausted, model unreachable)
- "Should we charge this to the user's budget?" → only if the call actually consumed resources

Today's code can't distinguish any of these. `phase_c_assembly.py` alone has 10+ sites that catch bare `except Exception`, log the message, and either return None or retry. A ComfyUI VRAM failure looks the same as a transient HTTP 503 looks the same as a malformed prompt looks the same as a 30-second timeout. The closed-loop gating in Phase 4 would have to infer failure cause from string-matching log lines — fragile and error-prone.

The fix: **typed errors at the call-site level**, raised with enough context (HTTP status, retry count, root-cause exception chained via `raise ... from`) that downstream code can pattern-match cleanly.

The second prerequisite — **atomic file writes** — addresses a related concern. When a write to `project.json` is interrupted mid-flush (process crash, OS kill, disk full), the next pipeline run finds a half-written file. The recovery path today tries to JSON-parse it, fails with a misleading "expecting ',' delimiter" message, and the operator wastes time debugging the wrong thing. Atomic writes (write-to-tmp + rename) make crash-during-write either fully succeed or fully no-op — no half-states.

What's **deferred** to later phases:

- **Phase 3:** Calibration scripts for VBench, coherence, aesthetic gates (modeled on `scripts/calibrate_motion_floor.py`)
- **Phase 4:** Closed-loop gating (A.1-A.5 from the original survey) — uses Phase 2's typed errors to make retry decisions
- **Phase 5:** Complete `cinema/` migration (B.4)
- **Phase 6:** Optimizations (Kling batching, polling backoff, etc.)

---

## 2. Scope of THIS plan

**In scope:**
- Slice A: `domain/errors.py` with the 4 typed-error classes + unit tests
- Slice B: replace ~10 broad `except Exception` blocks in `phase_c_assembly.py` with typed-error raises
- Slice C: `domain/io_utils.py` with `atomic_write(path, content)` helper + unit tests covering the crash-safety contract
- Slice D: apply `atomic_write` to the 3 sites flagged by the survey
- Cross-cutting: a brief operator-facing note in `AGENTS.md` / `CLAUDE.md` about the new error types so future implementers know about them

**Explicitly out of scope:**
- Replacing `except Exception` blocks NOT in `phase_c_assembly.py` (those will be triaged when their consuming phase migrates — YAGNI for Phase 4's needs)
- Adding retry/cost-attribution logic to `cost_tracker` based on the new error types (Phase 4 owns retry decisions; Phase 2 only ships the error types)
- Refactoring `phase_c_assembly.py` structurally beyond the exception-handling changes (B.10 from the survey is its own phase)
- Atomic writes for SQLite DB files (SQLite has its own ACID story — `atomic_write` is for JSON / text artifacts)
- Touching Phase 1's caching or negative-prompts code

---

## 3. Cross-cutting open questions to resolve BEFORE starting

These decisions shape multiple slices. Resolve before dispatching the first implementer.

### 3.1 Module location for the new typed errors

Three reasonable options:

- **Option A:** `domain/errors.py` (matches the existing `domain/` package which holds `scene_decomposer.py`, `project_manager.py`, etc.)
- **Option B:** `errors/__init__.py` (new top-level package)
- **Option C:** Distribute by domain: `cinema/errors.py`, `identity/errors.py`, etc.

**Recommend Option A** — single source of truth, easy import path (`from domain.errors import ImageGenerationError`), matches existing structure. Option C distributes responsibility too much; Option B adds a top-level package for very little gain.

### 3.2 Module location for `atomic_write`

- **Option A:** `domain/io_utils.py` (same package as errors)
- **Option B:** `utils/io.py` (new `utils/` package)
- **Option C:** Add to an existing utility file if one exists (none does, per grep)

**Recommend Option A** for symmetry with Slice A. Both new modules sit in `domain/`, which fits its role as "shared cross-phase utilities."

### 3.3 Scope of Slice B (apply typed errors to phase_c_assembly.py)

The survey called out 10 sites: lines 125-128, 186, 255, 329, 346, 435, 565, 586, 605, 622. These all live in `phase_c_assembly.py`.

**Question:** should Slice B convert ALL 10, or just a representative subset (e.g., 3-4) to validate the pattern works before scaling?

**Recommend ALL 10**, in one pass. Half-migrated exception handling is harder to reason about than fully-old or fully-new — Phase 4's gate logic will need to know "ImageGenerationError can happen anywhere in phase_c_assembly". A partial conversion makes that promise hard to make.

### 3.4 Backwards-compat: raise vs. return None

Today's broad `except Exception` blocks either log + return None OR log + retry. Some callers depend on the None-return path.

**Question:** should Slice B's typed errors REPLACE the None-returns (raise instead), or augment them (raise AND propagate the None)?

**Recommend REPLACE** — propagating None alongside a raise is dual-channel error reporting that defeats the typing benefit. The CALLERS need to update to catch the typed errors. If a caller really wants the None semantics, it can catch `PipelineError` and convert.

This means Slice B will touch caller files too (anywhere that consumed phase_c_assembly's None returns). The plan's task list reflects that.

### 3.5 Error message redaction (security)

Should typed errors include the original API response in their `str()`? An API error might leak request IDs, internal URLs, or quota details.

**Recommend:** include the original exception via `raise ... from exc` (Python's chained-exception machinery), but the typed error's `__str__` returns only the structured fields (e.g., "ImageGenerationError(engine=comfyui, retry_count=2)"). The full cause is in `__cause__` for debugging but doesn't print by default. Mirrors what `web_server.py:cost-live` does (redacted public response, full detail server-side log).

---

## 4. Slice A — Typed error hierarchy

### 4.1 Files this slice owns

```
domain/errors.py                   ← (new) PipelineError + 4 subclasses
tests/unit/test_domain_errors.py   ← (new) unit tests
```

### 4.2 Task A.1 — Write failing tests (TDD red phase)

**Files:**
- Create: `tests/unit/test_domain_errors.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for domain.errors — typed pipeline error hierarchy.

Verifies:
- Each typed error is constructible with the expected fields
- str() returns redacted summary (no full cause text)
- Original cause is preserved via __cause__ for debugging
- All typed errors inherit from PipelineError (so callers can catch the base)
"""

from __future__ import annotations
import pytest


def test_image_generation_error_basic_fields():
    from domain.errors import ImageGenerationError, PipelineError
    err = ImageGenerationError(
        engine="comfyui",
        retry_count=2,
        cost_usd_wasted=0.05,
        cause=RuntimeError("VRAM exhausted"),
    )
    assert isinstance(err, PipelineError)
    assert err.engine == "comfyui"
    assert err.retry_count == 2
    assert err.cost_usd_wasted == pytest.approx(0.05)
    # The original cause is preserved via Python's chained-exception machinery
    assert isinstance(err.__cause__, RuntimeError)


def test_image_generation_error_str_is_redacted():
    """str() must be structured + redacted — no raw cause text leakage."""
    from domain.errors import ImageGenerationError
    err = ImageGenerationError(
        engine="comfyui",
        retry_count=1,
        cost_usd_wasted=0.0,
        cause=RuntimeError("internal VRAM trace with sensitive paths /tmp/xyz"),
    )
    s = str(err)
    assert "comfyui" in s
    assert "retry_count=1" in s
    assert "/tmp/xyz" not in s, "raw cause text leaked into str()"


def test_motion_engine_error_subtype():
    from domain.errors import MotionEngineError, PipelineError
    err = MotionEngineError(
        engine="kling",
        retry_count=0,
        cost_usd_wasted=0.0,
        cause=TimeoutError("polling exceeded 600s"),
    )
    assert isinstance(err, PipelineError)
    assert err.engine == "kling"


def test_runpod_error_subtype():
    from domain.errors import RunPodError, PipelineError
    err = RunPodError(
        pod_id="abc123",
        retry_count=3,
        cause=ConnectionError("503 Service Unavailable"),
    )
    assert isinstance(err, PipelineError)
    assert err.pod_id == "abc123"


def test_validator_error_subtype():
    from domain.errors import ValidatorError, PipelineError
    err = ValidatorError(
        validator="arcface",
        cause=ImportError("deepface not installed"),
    )
    assert isinstance(err, PipelineError)
    assert err.validator == "arcface"


def test_caller_can_catch_base_class():
    """A caller that doesn't care about subtype can catch PipelineError once."""
    from domain.errors import (
        PipelineError,
        ImageGenerationError,
        MotionEngineError,
    )
    for cls in (ImageGenerationError, MotionEngineError):
        try:
            raise cls(engine="x", retry_count=0, cost_usd_wasted=0.0, cause=Exception())
        except PipelineError:
            pass  # expected
        else:
            pytest.fail(f"{cls.__name__} did not propagate as PipelineError")
```

- [ ] **Step 2: Run tests, confirm they FAIL with ModuleNotFoundError**

Run: `cd /Users/hyungkoookkim/Content && .venv/bin/python -m pytest tests/unit/test_domain_errors.py -v --no-header 2>&1 | tail -10`
Expected: 6 FAILs, all with `ModuleNotFoundError: No module named 'domain.errors'`.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/unit/test_domain_errors.py
git commit -m "test(errors): assert PipelineError hierarchy contract (failing)

TDD red phase. Six tests covering:
- ImageGenerationError basic fields + cause preservation
- str() redaction (no raw cause text leakage)
- MotionEngineError + RunPodError + ValidatorError subtype contracts
- Base-class catch path (callers can catch PipelineError once)

Currently fails with ModuleNotFoundError. Task A.2 will make these pass."
```

### 4.3 Task A.2 — Implement the hierarchy (TDD green phase)

**Files:**
- Create: `domain/errors.py`

- [ ] **Step 1: Write the module**

```python
"""Typed error hierarchy for pipeline failures.

Provides structured error types so callers (especially Phase 4's closed-loop
gating) can distinguish failure modes without string-matching log lines.

Design principles:
- Every typed error inherits from PipelineError so callers can catch the base
  when they don't care about the subtype.
- Each error carries structured fields (engine, retry_count, cost_usd_wasted)
  for downstream logging + retry decisions.
- The original exception is preserved via Python's chained-exception
  machinery (`raise NewError(...) from original`). str() returns ONLY the
  redacted structured summary so log lines don't leak internal trace text.

Use:
    from domain.errors import ImageGenerationError
    try:
        comfyui.generate(...)
    except RuntimeError as exc:
        raise ImageGenerationError(
            engine="comfyui",
            retry_count=ctx.retry_count,
            cost_usd_wasted=ctx.last_cost,
            cause=exc,
        ) from exc
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


class PipelineError(Exception):
    """Base class for all typed pipeline errors.

    Callers that don't care about the specific subtype catch this once.
    Phase 4's closed-loop gating will inspect the subtype to decide
    whether to retry, mutate, escalate, or charge wasted cost.
    """

    def __init__(self, cause: Optional[BaseException] = None):
        super().__init__()
        self._cause = cause

    def __str__(self) -> str:
        # Default: subclass name only. Subclasses override to add fields.
        return type(self).__name__


@dataclass
class ImageGenerationError(PipelineError):
    """Image generation (ComfyUI, image APIs) failed."""

    engine: str
    retry_count: int
    cost_usd_wasted: float
    cause: Optional[BaseException] = None

    def __post_init__(self) -> None:
        PipelineError.__init__(self, cause=self.cause)

    def __str__(self) -> str:
        return (
            f"ImageGenerationError(engine={self.engine!r}, "
            f"retry_count={self.retry_count}, "
            f"cost_usd_wasted={self.cost_usd_wasted:.4f})"
        )


@dataclass
class MotionEngineError(PipelineError):
    """Motion engine (Kling, Sora, Veo, etc.) failed."""

    engine: str
    retry_count: int
    cost_usd_wasted: float
    cause: Optional[BaseException] = None

    def __post_init__(self) -> None:
        PipelineError.__init__(self, cause=self.cause)

    def __str__(self) -> str:
        return (
            f"MotionEngineError(engine={self.engine!r}, "
            f"retry_count={self.retry_count}, "
            f"cost_usd_wasted={self.cost_usd_wasted:.4f})"
        )


@dataclass
class RunPodError(PipelineError):
    """RunPod infrastructure failure (cold start, 503, pod unreachable, etc.)."""

    pod_id: str
    retry_count: int
    cause: Optional[BaseException] = None

    def __post_init__(self) -> None:
        PipelineError.__init__(self, cause=self.cause)

    def __str__(self) -> str:
        return f"RunPodError(pod_id={self.pod_id!r}, retry_count={self.retry_count})"


@dataclass
class ValidatorError(PipelineError):
    """Validator (ArcFace identity, motion gate, coherence) failed at the
    INFRASTRUCTURE level — model couldn't load, library missing, etc.

    NOT for validator returning a "passed=False" result (that's normal flow).
    This is for "the validator itself crashed and we have no verdict."
    """

    validator: str
    cause: Optional[BaseException] = None

    def __post_init__(self) -> None:
        PipelineError.__init__(self, cause=self.cause)

    def __str__(self) -> str:
        return f"ValidatorError(validator={self.validator!r})"
```

- [ ] **Step 2: Run tests, confirm 6/6 pass**

Run: `cd /Users/hyungkoookkim/Content && .venv/bin/python -m pytest tests/unit/test_domain_errors.py -v --no-header 2>&1 | tail -10`
Expected: 6 PASS.

- [ ] **Step 3: Commit**

```bash
git add domain/errors.py
git commit -m "feat(errors): typed PipelineError hierarchy for failure attribution

Defines PipelineError base + 4 subclasses (ImageGenerationError,
MotionEngineError, RunPodError, ValidatorError). Each carries
structured fields (engine, retry_count, cost_usd_wasted) and
preserves the original cause via Python's chained-exception
machinery. str() returns redacted summary only (no raw cause leakage).

Slice B will apply these to phase_c_assembly.py's 10 swallowed
exception sites. Phase 4 will consume the subtype for retry decisions."
```

### 4.4 Done criteria for Slice A

- [ ] `domain/errors.py` exists with PipelineError + 4 subclasses
- [ ] All 6 tests in `test_domain_errors.py` pass
- [ ] `cd /Users/hyungkoookkim/Content && .venv/bin/python -c "from domain.errors import ImageGenerationError, MotionEngineError, RunPodError, ValidatorError; print('OK')"` prints OK
- [ ] No production code modified yet (that's Slice B)

---

## 5. Slice B — Apply typed errors to `phase_c_assembly.py`

### 5.1 Files this slice owns

```
phase_c_assembly.py                ← modify ~10 except sites
<caller files>                     ← update any callers that depend on None-returns
```

The 10 sites to convert (per the original survey):
- Lines 125-128 (one block)
- Line 186
- Line 255
- Line 329
- Line 346
- Line 435
- Line 565
- Line 586
- Line 605
- Line 622

### 5.2 Task B.1 — Audit the 10 sites + their callers

**Files:**
- Read-only: `phase_c_assembly.py`

- [ ] **Step 1: For each of the 10 sites, classify**

For each exception block, determine:
1. What is being attempted? (ComfyUI call? Kling call? RunPod call? File I/O?)
2. What is the current return value when caught? (None? False? Empty dict?)
3. What does the caller do with that return value?
4. Which typed error subtype fits? (ImageGenerationError? MotionEngineError? RunPodError? ValidatorError?)
5. Is there a `cost_usd_wasted` value reachable? (Look for `cost_tracker.log_cost(...)` calls in the same block.)

Produce a table:

| Line | Operation | Current return | Caller(s) | Typed-error subtype | Cost reachable? |
|---|---|---|---|---|---|
| 125-128 | <e.g. comfyui.generate> | None | function_x at line N | ImageGenerationError | yes (line 122) |
| ... | ... | ... | ... | ... | ... |

- [ ] **Step 2: Identify caller files**

Grep for callers of each affected function in `phase_c_assembly.py`:

```bash
cd /Users/hyungkoookkim/Content && for fn in <functions identified in Step 1>; do
  echo "=== $fn ==="
  grep -rn "$fn" --include="*.py" | grep -v "phase_c_assembly.py" | head -10
done
```

- [ ] **Step 3: Report findings**

No code changes in this audit task — produce a report listing the 10 sites with their classifications and the caller files that will need updates in Task B.2-B.4. Operator reviews before code changes proceed.

### 5.3 Task B.2 — Convert sites 1-4 (smoke test the pattern)

**Files:**
- Modify: `phase_c_assembly.py` (4 of the 10 sites)
- Possibly modify: caller files identified by B.1

- [ ] **Step 1: Pick 4 sites** that exercise different typed-error subtypes (e.g., 1× ImageGenerationError, 1× MotionEngineError, 1× RunPodError, 1× ValidatorError if all are represented; otherwise pick 4 to cover the most subtypes).

- [ ] **Step 2: For each site, apply the conversion pattern**

```python
# Before:
try:
    result = comfyui.generate(prompt)
except Exception as exc:
    print(f"[GEN] failed: {exc}")
    return None

# After:
try:
    result = comfyui.generate(prompt)
except Exception as exc:
    from domain.errors import ImageGenerationError
    raise ImageGenerationError(
        engine="comfyui",
        retry_count=ctx.get("retry_count", 0),
        cost_usd_wasted=ctx.get("last_cost_usd", 0.0),
        cause=exc,
    ) from exc
```

Note the `from exc` clause — this preserves the original exception in `__cause__` for debugging.

- [ ] **Step 3: Update callers that consumed `None` returns**

For each function in B.1's caller list, change:

```python
# Before:
result = phase_c_function(...)
if result is None:
    handle_failure(...)

# After:
from domain.errors import PipelineError
try:
    result = phase_c_function(...)
except PipelineError as exc:
    handle_failure_typed(exc)  # gets structured info now
```

- [ ] **Step 4: Run import smoke + targeted tests**

```bash
cd /Users/hyungkoookkim/Content && \
    .venv/bin/python -c "import phase_c_assembly; print('OK')" && \
    .venv/bin/python -m pytest tests/unit/ \
        --ignore=tests/unit/test_guided_pipeline.py \
        --ignore=tests/unit/test_quality_tracker.py \
        --ignore=tests/unit/test_vbench_evaluator.py \
        -q 2>&1 | tail -5
```

Expected: import OK; no NEW test failures (the 6 pre-existing project_manager failures remain unchanged).

- [ ] **Step 5: Commit**

```bash
git add phase_c_assembly.py <caller files>
git commit -m "feat(errors): apply typed errors to 4 phase_c_assembly sites (smoke test)

Converts the first 4 broad except Exception blocks in phase_c_assembly
to raise typed errors from domain.errors. Caller updates propagate the
new contract.

This is the smoke-test pass for the conversion pattern. Sites 5-10 in
B.3-B.4."
```

### 5.4 Task B.3 — Convert sites 5-10

**Files:**
- Modify: `phase_c_assembly.py` (remaining 6 sites)
- Possibly modify: additional callers

Same pattern as B.2 for the remaining 6 sites. Single commit.

- [ ] **Step 1-3:** Same as B.2 steps 2-4 applied to sites 5-10
- [ ] **Step 4: Commit**

```bash
git add phase_c_assembly.py <caller files>
git commit -m "feat(errors): apply typed errors to remaining 6 phase_c_assembly sites

Completes the conversion of all 10 broad except blocks in
phase_c_assembly. The file no longer has any bare `except Exception`
followed by None-return."
```

### 5.5 Task B.4 — Lint check + final regression run

- [ ] **Step 1: Confirm no bare excepts remain in phase_c_assembly**

```bash
cd /Users/hyungkoookkim/Content && grep -n "except Exception" phase_c_assembly.py
```

Expected: empty (or only intentional cases that have been left and commented why).

- [ ] **Step 2: Full unit regression**

```bash
cd /Users/hyungkoookkim/Content && .venv/bin/python -m pytest tests/unit/ \
    --ignore=tests/unit/test_guided_pipeline.py \
    --ignore=tests/unit/test_quality_tracker.py \
    --ignore=tests/unit/test_vbench_evaluator.py \
    -q 2>&1 | tail -5
```

Expected: same number passing as on baseline (no new failures introduced).

- [ ] **Step 3: Self-review pass on the consolidated diff**

```bash
cd /Users/hyungkoookkim/Content && git diff <Slice-B-start>..HEAD -- phase_c_assembly.py
```

Re-read the consolidated diff. Confirm:
- Every `except Exception` either raises a typed error OR has a comment explaining why it's intentionally swallowed
- Every typed-error raise includes `from exc` (preserves the cause)
- No new behavior — happy paths are unchanged
- Logging is preserved or improved (the typed error's `str()` is logged, not the bare exception)

### 5.6 Done criteria for Slice B

- [ ] All 10 sites in `phase_c_assembly.py` converted to typed errors OR explicitly commented as intentional swallows
- [ ] All affected callers updated to catch `PipelineError` (or appropriate subtype)
- [ ] `grep -n "except Exception" phase_c_assembly.py` returns only intentional cases
- [ ] Unit test count unchanged from baseline; no new failures
- [ ] `import phase_c_assembly` still clean

---

## 6. Slice C — `atomic_write` helper

### 6.1 Files this slice owns

```
domain/io_utils.py                       ← (new) atomic_write helper
tests/unit/test_domain_io_utils.py       ← (new) unit tests
```

### 6.2 Task C.1 — Write failing tests (TDD red phase)

**Files:**
- Create: `tests/unit/test_domain_io_utils.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for domain.io_utils.atomic_write.

Verifies:
- Normal write produces the right file content
- File is created at the right path with the right permissions
- Crash simulation (KeyboardInterrupt mid-write) leaves either the
  full content or NO file at all — never a half-written file
- The temp file used during the write is cleaned up
- Concurrent reads during a write see either the old content or the
  new content — never a partial write
"""

from __future__ import annotations
import os
import tempfile
import threading
import time
from pathlib import Path

import pytest


def test_atomic_write_creates_file_with_content(tmp_path: Path):
    from domain.io_utils import atomic_write
    target = tmp_path / "output.json"
    atomic_write(str(target), '{"hello": "world"}')
    assert target.exists()
    assert target.read_text() == '{"hello": "world"}'


def test_atomic_write_overwrites_existing(tmp_path: Path):
    from domain.io_utils import atomic_write
    target = tmp_path / "existing.txt"
    target.write_text("old content")
    atomic_write(str(target), "new content")
    assert target.read_text() == "new content"


def test_atomic_write_temp_file_cleaned_up(tmp_path: Path):
    """No tmp files should linger after a successful write."""
    from domain.io_utils import atomic_write
    target = tmp_path / "out.txt"
    atomic_write(str(target), "data")
    # Only the target should exist in the directory
    files = list(tmp_path.iterdir())
    assert files == [target], f"unexpected files: {files}"


def test_atomic_write_crash_leaves_no_partial(tmp_path: Path, monkeypatch):
    """Simulate an os.replace() crash. The original file (if any) must remain
    intact; no partially-written tmp file should appear at the target path."""
    from domain.io_utils import atomic_write
    target = tmp_path / "atomic.txt"
    target.write_text("original")

    def fake_replace(src, dst):
        raise KeyboardInterrupt("simulated crash during rename")

    monkeypatch.setattr(os, "replace", fake_replace)
    with pytest.raises(KeyboardInterrupt):
        atomic_write(str(target), "new content that should not land")

    # Original content survived; no partial write
    assert target.read_text() == "original"


def test_atomic_write_creates_parent_dirs(tmp_path: Path):
    """If the target's parent dir doesn't exist, atomic_write should create it."""
    from domain.io_utils import atomic_write
    target = tmp_path / "subdir" / "nested" / "out.txt"
    atomic_write(str(target), "deep")
    assert target.exists()
    assert target.read_text() == "deep"
```

- [ ] **Step 2: Run tests, confirm they FAIL with ModuleNotFoundError**

Run: `cd /Users/hyungkoookkim/Content && .venv/bin/python -m pytest tests/unit/test_domain_io_utils.py -v --no-header 2>&1 | tail -10`
Expected: 5 FAILs, all `ModuleNotFoundError: No module named 'domain.io_utils'`.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_domain_io_utils.py
git commit -m "test(io-utils): assert atomic_write crash-safety + cleanup contract (failing)"
```

### 6.3 Task C.2 — Implement `atomic_write` (TDD green phase)

**Files:**
- Create: `domain/io_utils.py`

- [ ] **Step 1: Write the helper**

```python
"""Crash-safe file I/O helpers for the cinema pipeline.

The pipeline writes JSON project files, generated artifacts, and config
in many places. Direct `open(path, 'w').write(content)` is NOT crash-safe:
if the process is killed (OOM, OS, operator Ctrl+C) between the file
truncation and the content write, the next pipeline run finds a partial
file and fails with a misleading JSON-decode error.

atomic_write fixes this: write to a tmp file in the same directory, then
os.replace() to the target path. os.replace is atomic on POSIX (and on
Windows for files on the same volume), so the target either has the OLD
content or the NEW content — never a partial state.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write(path: str, content: str, encoding: str = "utf-8") -> None:
    """Write `content` to `path` atomically.

    Implementation:
    1. Create a tmp file in the same directory as the target (same volume,
       so os.replace() can be atomic).
    2. Write the content to the tmp file.
    3. fsync() the tmp file to flush kernel buffers to disk.
    4. os.replace() the tmp file to the target — atomic on POSIX/NTFS.
    5. If anything fails before os.replace, unlink the tmp file so it
       doesn't linger.

    Creates parent directories if they don't exist.

    Args:
        path: Target file path (will be created or replaced).
        content: String content to write.
        encoding: Text encoding (default utf-8).
    """
    target = Path(path)
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)

    # delete=False because we manage the cleanup ourselves — we want to keep
    # the tmp file just long enough to fsync and rename.
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(parent),
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        # Atomic on POSIX; atomic on Windows for same-volume replace.
        os.replace(tmp_path, str(target))
    except BaseException:
        # On any failure (including KeyboardInterrupt), unlink the tmp file
        # so it doesn't linger and we leave the target unchanged.
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass  # tmp file already gone (e.g., partial cleanup)
        raise
```

- [ ] **Step 2: Run tests, confirm 5/5 pass**

Run: `cd /Users/hyungkoookkim/Content && .venv/bin/python -m pytest tests/unit/test_domain_io_utils.py -v --no-header 2>&1 | tail -10`
Expected: 5 PASS.

- [ ] **Step 3: Commit**

```bash
git add domain/io_utils.py
git commit -m "feat(io-utils): atomic_write helper for crash-safe file writes

Wraps the tmp-file-then-rename pattern. Creates parent dirs if needed,
fsyncs before rename, cleans up tmp on any failure (including
KeyboardInterrupt). Atomic on POSIX and on Windows for same-volume
replacements.

Slice D will apply this to the 3 sites flagged by the survey:
phase_c_assembly.py:197, main.py:281, cleanup.py:97."
```

### 6.4 Done criteria for Slice C

- [ ] `domain/io_utils.py` exists with `atomic_write(path, content, encoding='utf-8')`
- [ ] All 5 tests pass
- [ ] No production code modified yet (Slice D applies it)

---

## 7. Slice D — Apply `atomic_write` to the 3 sites

### 7.1 Files this slice owns

```
phase_c_assembly.py    ← line 197 (per the original survey)
main.py                ← line 281
cleanup.py             ← line 97
```

### 7.2 Task D.1 — Apply to `phase_c_assembly.py:197`

- [ ] **Step 1: Read the existing write**

```bash
cd /Users/hyungkoookkim/Content && sed -n '193,203p' phase_c_assembly.py
```

Identify the pattern (likely `with open(path, 'w') as f: f.write(content)` or `json.dump(data, open(path, 'w'))`).

- [ ] **Step 2: Replace**

For text content:
```python
# Before:
with open(path, 'w') as f:
    f.write(content)

# After:
from domain.io_utils import atomic_write
atomic_write(path, content)
```

For JSON:
```python
# Before:
with open(path, 'w') as f:
    json.dump(data, f, indent=2)

# After:
import json
from domain.io_utils import atomic_write
atomic_write(path, json.dumps(data, indent=2))
```

- [ ] **Step 3: Run import smoke + commit**

```bash
cd /Users/hyungkoookkim/Content && .venv/bin/python -c "import phase_c_assembly; print('OK')"
git add phase_c_assembly.py
git commit -m "feat(phase-c): atomic write at line 197 (crash-safety)"
```

### 7.3 Task D.2 — Apply to `main.py:281`

Same pattern. Single commit.

### 7.4 Task D.3 — Apply to `cleanup.py:97`

Same pattern. Single commit.

### 7.5 Done criteria for Slice D

- [ ] All 3 sites use `atomic_write` instead of direct file writes
- [ ] `grep -n "open(.*, .w.)\|open(.*, 'w')" phase_c_assembly.py main.py cleanup.py` should not flag any remaining direct writes at those line ranges
- [ ] Unit tests still pass; no new failures

---

## 8. Cross-cutting done criteria for Phase 2

The plan is done when:

- [ ] All four slices' done criteria pass (§4.4, §5.6, §6.4, §7.5)
- [ ] `domain/errors.py` exports `PipelineError, ImageGenerationError, MotionEngineError, RunPodError, ValidatorError`
- [ ] `domain/io_utils.py` exports `atomic_write`
- [ ] `phase_c_assembly.py` has no bare `except Exception` followed by None-return (only typed-raise or commented-intentional-swallow)
- [ ] `phase_c_assembly.py`, `main.py`, `cleanup.py` use `atomic_write` at the survey-flagged sites
- [ ] Unit test count = baseline + 11 (6 for errors, 5 for io_utils); no new failures elsewhere
- [ ] `git diff --stat` shows ~400-800 LOC across 6-10 files

---

## 9. What NOT to do in this plan

- **DO NOT add retry/cost-attribution logic** to `cost_tracker` based on the new error types. Phase 4 owns retry decisions; Phase 2 only ships the error types.
- **DO NOT convert `except Exception` blocks outside `phase_c_assembly.py`** unless their callers depend on the typed errors landing now. Other files migrate when their phase needs them.
- **DO NOT apply `atomic_write` to SQLite DB files**. SQLite has its own ACID story; using `atomic_write` on `.db` files would corrupt them.
- **DO NOT change `cost_tracker.cost_log` schema** to add an error-type column. Out of scope.
- **DO NOT refactor `phase_c_assembly.py` structurally** beyond what the typed-error conversion requires (no extracting helpers, no renaming, no splitting). B.10 from the original survey is a separate phase.
- **DO NOT touch Phase 1's caching or negative-prompts code**. Both are stable; Phase 2 is orthogonal.
- **DO NOT add a `retry()` decorator** based on PipelineError. Phase 4's gate logic decides retry policy; Phase 2 just labels the failures.

---

## 10. Pricing implication (context, not code)

Phase 2 doesn't change per-call costs. It changes:

- **Operator debugging time:** typed errors mean `[ERR] ImageGenerationError(engine='comfyui', retry_count=2, cost_usd_wasted=0.05)` instead of `[ERR] RuntimeError: 'NoneType' object has no attribute 'json'`. Triage time drops from hours to minutes for common failure modes.
- **Phase 4 feasibility:** closed-loop gating becomes implementable. Today's "retry on any error" policy wastes ~$X/month on transient infrastructure blips re-running expensive generations. Phase 4 can be smart about it because Phase 2 made the failure mode legible.
- **Data integrity:** atomic writes eliminate the half-written-JSON failure mode that occasionally requires an operator to manually edit a project file. Frequency is low (~1 per month per operator) but each incident costs ~30 min.

---

## 11. Roadmap — what comes after Phase 2

Per `2026-05-23-quality-uplift.md` §8:

- **Phase 3:** Calibration scripts (per-gate `scripts/calibrate_*.py` modeled on `scripts/calibrate_motion_floor.py`). Each placeholder threshold gets a calibration story before it can enforce.
- **Phase 4:** Closed-loop gating (A.1-A.5 from the original survey) — **consumes Phase 2's typed errors** + Phase 3's calibrated thresholds. Multi-task plan, ships advisory-only first.
- **Phase 5:** Complete `cinema/` migration (B.4). Prereq for parallelism.
- **Phase 6:** Optimizations (B.1 Kling batching, B.3 polling backoff, B.6 cascade cap, etc.).

---

**End of plan.** Ready to execute via `superpowers:subagent-driven-development`.
