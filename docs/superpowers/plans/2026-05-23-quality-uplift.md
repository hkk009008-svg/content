# Quality Uplift — Phase 1 Implementation Plan

> **POST-PIVOT STATUS (2026-05-23):** Phase 1 is still actionable. Both
> slices' targets survive the pivot:
> - Slice A (prompt caching): `llm/ensemble.py` + `llm/chief_director.py`
>   both exist. **NB:** `llm/blueprint_director.py` was deleted with the
>   CLI — exclude it from the caching survey.
> - Slice B (negative prompts driven by validator failure reasons):
>   `kling_native.py`, `sora_native.py`, `veo_native.py`, `identity/validator.py`
>   all survive. The IdentityValidator is now a process singleton
>   (`phase_c_vision._get_shared_validator()`) — Slice B's `history`
>   reads will now actually accumulate state, which makes the
>   feedback-driven negatives meaningful for the first time.
>
> **Canonical current state: `/HANDOFF.md`.**

> **For agentic workers:** REQUIRED: Use `superpowers:subagent-driven-development` (if subagents available) or `superpowers:executing-plans` to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the two lowest-risk wins from the quality-uplift survey — Anthropic prompt caching (B.2) and validator-driven negative prompts (A.6) — while explicitly NOT shipping enforcing quality gates without calibration data.

**Architecture:** Two independent slices.
- **Slice A:** verify the LLM system prompt is stable across calls, then add `cache_control={"type": "ephemeral"}` to the system block in `llm/ensemble.py` (and downstream `chief_director.py` if needed). If the system prompt is *not* stable, escalate and stop — caching savings are illusory in that case.
- **Slice B:** introduce a `negative_prompts` mapping driven by `identity/validator.py` failure reasons; wire it into the per-engine prompt builders (Kling, Sora, Veo) so a failed take's *next* attempt has the right negatives.

Both slices are behavior-preserving in the "happy path" sense — neither changes what gets generated when validators pass. They change behavior only when validators fire OR when LLM token bills drop.

**Tech stack:** Python 3.10+, Anthropic SDK (already in `llm/ensemble.py`), pytest (project venv at `.venv/bin/python -m pytest`), existing prompt builders in `kling_native.py`, `sora_native.py`, `veo_native.py`.

**Branch:** new feature branch off `main`. Suggested: `feature/quality-uplift-phase1`. Both slices can ship on the same branch as separate commits per the orchestration discipline.

---

## 1. Why this matters (the WHY before the WHAT)

The post-feature-remaining-gaps audit identified two categories of quality-uplift work:

- **Tier A (quality):** instrumentation systems (VBench, motion gates, coherence analyzer) that measure but never enforce, and prompt-engineering gaps (no negative prompts, no few-shot examples, stale model selection).
- **Tier B (optimization):** wasted tokens on resent system prompts, sequential Kling shots that should be batched, broad `except Exception` blocks that hide root causes.

The top of the priority list ("If you only do five things") puts **closed-loop gate enforcement** at #1 — but the discipline lessons from `feature/remaining-gaps` (PR #11) say:

> "Don't ship enforcing thresholds before calibration data exists. Every gate threshold needs a calibration story." — `AGENTS.md` § Quality vs. throughput watchpoints

The motion-gate work just locked **advisory-only** as the operator's posture for at least the first 100 shots of calibration data. Enforcing gates for VBench, coherence, or aesthetic at this stage would repeat exactly the bug that decision was meant to prevent.

So Phase 1 ships the two recommendations that are calibration-free quality wins:

| Item | Why it's safe to ship now |
|---|---|
| **B.2 — Anthropic prompt caching** | Pure token-economics change. Output is byte-identical (caching is server-side replay of the same content). The only risk is over-promising savings — addressed by Step 1 (verify cache-hit potential). |
| **A.6 — Negative prompts driven by validator failure reasons** | Only fires on RETRY, so happy-path output is unchanged. Adds information to the prompt that the validator already knows; doesn't introduce new thresholds. |

What's deferred to later phases:

- **Phase 2:** Typed errors replacing broad `except Exception` (B.5) + atomic file writes (B.8) — failure-attribution prereqs for closed-loop work.
- **Phase 3:** Calibration scripts for VBench, coherence, aesthetic (modeled on `scripts/calibrate_motion_floor.py`) — every gate needs a calibration story before it enforces.
- **Phase 4:** Closed-loop gating (A.1-A.5) — only after calibration data exists, and ships as **advisory + UI chip** first, like the motion gate did.
- **Phase 5:** Complete the legacy → `cinema/` migration (B.4) — prereq for parallel-shot speedups.
- **Phase 6:** Optimizations (B.1 Kling batching, B.3 polling backoff, B.6 cascade cap, B.7 circuit breaker) — land cleanly once Phase 5 unblocks the architecture.

Each of Phases 2-6 should become its own plan file when its prerequisites are met. See § 8 below for the roadmap.

---

## 2. Scope of THIS plan

**In scope:**
- Slice A: Anthropic prompt caching on the system block, with cache-hit verification first.
- Slice B: Negative-prompts mapping + wiring into per-engine prompt builders, gated on validator failure reasons.
- Unit tests for both.
- Operator-visible verification (token-spend observation for Slice A; SSE event or log line for Slice B when a negative prompt fires).

**Explicitly out of scope:**
- Changes to LLM model selection (A.9 — deferred to a later phase that handles role-conditioned routing as a unit).
- Few-shot examples in prompts (A.7 — needs prompt-engineering review session, not a 1-slice plan).
- Self-critique loop (A.8 — same).
- VBench / coherence / aesthetic enforcement — explicitly DEFERRED per § 1.
- Any cinema/ migration work.
- Any Kling batching work.

---

## 3. Cross-cutting open questions to resolve BEFORE starting

These two decisions shape both slices. Resolve before dispatching the first implementer:

### 3.1 Anthropic SDK version

The `cache_control` parameter requires Anthropic SDK ≥ 0.18 (it shipped with the prompt-caching beta). Confirm: `cd /Users/hyungkoookkim/Content && .venv/bin/python -c "import anthropic; print(anthropic.__version__)"`. If < 0.18, an SDK upgrade becomes Step 0 of Slice A — and that's a bigger task (it can break other call sites). Plan author's best guess: SDK is recent, but verify.

### 3.2 Negative prompt taxonomy — operator review

Slice B introduces `NEGATIVE_PROMPT_BY_FAILURE_REASON: dict[str, str]`. The initial mapping must come from `identity/validator.py`'s actual failure-reason enum. **Operator decision:** is this an opt-in additive system (default behavior unchanged; only fires when validator emits a known reason) OR an opt-out (every retry gets at least a generic negative prompt)? Recommend **opt-in**: only known failure reasons trigger negatives, unknown reasons fall through to existing behavior. Less invasive, easier to roll back.

---

## 4. Slice A — Anthropic prompt caching

### 4.1 Files this slice owns

```
llm/ensemble.py            ← add cache_control to system block, possibly restructure
llm/chief_director.py      ← same change if it has its own LLM call sites
tests/unit/test_llm_caching.py  ← (new) verify cache_control header is included
```

**Decomposition rationale:** `llm/ensemble.py` is the canonical LLM call site (per the original quality-uplift report at `ensemble.py:210-220`). `chief_director.py` has its own call site (`chief_director.py:88-165`) and may need the same change. A new test file under `tests/unit/` because hook unit tests aren't a pattern in this codebase but LLM-config unit tests would be.

### 4.2 Pre-flight: verify cache-hit potential (BLOCKING)

The 70-80% savings figure assumes the system prompt is **stable across calls**. If the system prompt varies per call (e.g., per-shot context injected at the top), Anthropic's caching won't hit and the entire slice produces zero savings.

#### Task A.0 — Audit system-prompt stability

**Files:**
- Read: `llm/ensemble.py` (full, especially the function that builds the messages payload)
- Read: `llm/chief_director.py` (find the call to `client.messages.create` or equivalent)
- Read: `llm/prompt_optimizer.py` (the report cites it as a 1800-word system prompt — verify it's static)

- [ ] **Step 1: Find every call to `client.messages.create` in `llm/`**

Run: `cd /Users/hyungkoookkim/Content && grep -rn "messages.create\|client\.messages" llm/`
Expected: 1-3 call sites. Note the file/line of each.

- [ ] **Step 2: For each call site, classify the system message**

For each `system=` argument, check: is it a module-level constant, a literal string, or a string built per-call with per-shot data interpolated?

- **Module-level constant or literal string** → cache will hit. Safe to proceed.
- **Built per-call with per-shot data** → cache won't hit. **Stop and escalate** — restructuring is needed first (move per-shot data into the user message, keep system block stable). That's its own plan.

- [ ] **Step 3: Document findings**

Write a short note in the task report:
- Call site 1: <file>:<line> — system is <stable|per-call> because <reason>
- Call site 2: ...

If ALL call sites have stable system blocks → proceed to Task A.1.
If ANY call site has per-call system content → report `BLOCKED` with the specific files and lines, and recommend restructuring as Phase 1.5.

- [ ] **Step 4: Commit the audit notes**

```bash
git add docs/superpowers/plans/2026-05-23-quality-uplift.md  # if you appended findings to this file
git commit -m "docs(quality-uplift): audit LLM system-prompt stability for caching"
```

(Skip this commit if findings stay in your task report rather than a file edit.)

### 4.3 Task A.1 — Anthropic SDK version check

**Files:**
- Read: `pyproject.toml` or `requirements.txt` (whichever pins anthropic)

- [ ] **Step 1: Check installed SDK version**

Run: `cd /Users/hyungkoookkim/Content && .venv/bin/python -c "import anthropic; print(anthropic.__version__)"`
Expected output: a version string like `0.18.0` or higher.

- [ ] **Step 2: If version < 0.18, upgrade is its own task**

Report `NEEDS_CONTEXT` with the version found. Don't upgrade silently — SDK upgrades can break existing call sites and need a dedicated diff.

- [ ] **Step 3: If version ≥ 0.18, proceed**

Note the version in your task report. Continue to Task A.2.

### 4.4 Task A.2 — Add caching test (TDD red phase)

**Files:**
- Create: `tests/unit/test_llm_caching.py`

- [ ] **Step 1: Write the failing test**

```python
"""Verify cache_control is set on the system block for LLM calls.

We don't test that caching saves money (Anthropic's server-side concern);
we test that our outgoing requests opt into caching correctly. If
cache_control disappears from the system block in a future refactor,
this test catches it.
"""

from __future__ import annotations
from unittest.mock import MagicMock, patch


def test_ensemble_system_block_has_cache_control():
    """The system message must include cache_control={'type': 'ephemeral'}."""
    from llm.ensemble import LLMEnsemble  # adjust import to actual class name

    fake_client = MagicMock()
    fake_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text="ok")], stop_reason="end_turn"
    )

    with patch("llm.ensemble.anthropic.Anthropic", return_value=fake_client):
        ensemble = LLMEnsemble()
        # Call whatever method invokes the LLM; adjust to the real method name
        ensemble._generate_single(role="director", user_message="test prompt")

    call_kwargs = fake_client.messages.create.call_args.kwargs
    system_block = call_kwargs.get("system")

    # Anthropic accepts system as a string or a list of content blocks.
    # cache_control is only valid on the list form.
    assert isinstance(system_block, list), (
        f"system must be a list of content blocks to use cache_control; "
        f"got {type(system_block).__name__}"
    )
    assert len(system_block) >= 1, "system block list must not be empty"

    first_block = system_block[0]
    assert first_block.get("type") == "text", "first system block must be type=text"
    assert "cache_control" in first_block, (
        f"first system block missing cache_control; got keys {list(first_block.keys())}"
    )
    assert first_block["cache_control"] == {"type": "ephemeral"}, (
        f"cache_control must be ephemeral; got {first_block['cache_control']}"
    )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /Users/hyungkoookkim/Content && .venv/bin/python -m pytest tests/unit/test_llm_caching.py -v`
Expected: FAIL — either `AttributeError` (method name wrong; fix the test to match the actual ensemble API) or `AssertionError` saying system is a string (the current code passes `system="..."` as a string).

If the failure is method-name-wrong, fix the test to match the actual method name. If it's the AssertionError about system being a string, that's the expected red phase.

- [ ] **Step 3: Commit the failing test**

```bash
git add tests/unit/test_llm_caching.py
git commit -m "test(llm): assert cache_control is set on system block (failing)"
```

### 4.5 Task A.3 — Implement cache_control (TDD green phase)

**Files:**
- Modify: `llm/ensemble.py` — change the system parameter from string to list-of-blocks
- Modify: `llm/chief_director.py` — same change if Task A.0 found it has its own call site

- [ ] **Step 1: Read the existing system-message construction**

Run: `cd /Users/hyungkoookkim/Content && grep -n "system=" llm/ensemble.py`
Note the line where `system=...` is passed. The current shape is likely `system=SYSTEM_PROMPT` where `SYSTEM_PROMPT` is a module-level string.

- [ ] **Step 2: Convert system to a content-block list with cache_control**

The Anthropic SDK accepts the system parameter as either a string OR a list of content blocks. Switch to the list form to enable `cache_control`:

```python
# Before:
response = client.messages.create(
    model=model,
    system=SYSTEM_PROMPT,
    messages=[...],
    ...
)

# After:
response = client.messages.create(
    model=model,
    system=[
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }
    ],
    messages=[...],
    ...
)
```

- [ ] **Step 3: Run the test to verify it passes**

Run: `cd /Users/hyungkoookkim/Content && .venv/bin/python -m pytest tests/unit/test_llm_caching.py -v`
Expected: PASS.

- [ ] **Step 4: Apply the same change to chief_director.py (if applicable)**

If Task A.0 found a separate call site in `chief_director.py`, apply the identical transformation. Add a parallel test if you can isolate the chief-director call from the ensemble (or extend the existing test to cover both paths).

- [ ] **Step 5: Run the full test suite to check for regressions**

Run: `cd /Users/hyungkoookkim/Content && .venv/bin/python -m pytest tests/unit/ -v --no-header 2>&1 | tail -20`
Expected: all previously-passing tests still pass; new test passes.

- [ ] **Step 6: Commit**

```bash
git add llm/ensemble.py llm/chief_director.py tests/unit/test_llm_caching.py
git commit -m "feat(llm): enable Anthropic prompt caching on system block

Switches the system parameter from a bare string to a list of content
blocks with cache_control={'type': 'ephemeral'}. Identical content, so
output is byte-identical; cache reduces input-token spend on the
~1600-token system prompt by ~70-80% on warm calls.

Verified via Task A.0 that the system prompt is stable across calls
(documented in the audit notes). Per-shot data goes into the user
message, not the system block."
```

### 4.6 Task A.4 — Observability for cache hit rate

**Files:**
- Modify: `llm/ensemble.py` (one block, after the API call)

The Anthropic response includes `usage.cache_creation_input_tokens` and `usage.cache_read_input_tokens`. Log these so the operator can verify caching is actually working in production.

- [ ] **Step 1: Add a cache-hit log line after the API call**

```python
# After response = client.messages.create(...)
if hasattr(response, "usage"):
    cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
    cache_creation = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
    input_tokens = getattr(response.usage, "input_tokens", 0) or 0
    if cache_read > 0 or cache_creation > 0:
        print(
            f"   [LLM-CACHE] role={role} input={input_tokens} "
            f"cache_read={cache_read} cache_creation={cache_creation}"
        )
```

(Match the existing logging idiom — the codebase uses `print(f"   [TAG] ...")` per `cinema/shots/controller.py:778-798`.)

- [ ] **Step 2: Smoke-test by importing the module**

Run: `cd /Users/hyungkoookkim/Content && .venv/bin/python -c "from llm.ensemble import LLMEnsemble; print('OK')"`
Expected: prints `OK`, no syntax errors.

- [ ] **Step 3: Commit**

```bash
git add llm/ensemble.py
git commit -m "feat(llm): log cache_read / cache_creation tokens for observability

Lets the operator confirm caching is hitting on warm calls. First call
of a session creates the cache (creation > 0, read = 0); subsequent
calls within ~5 min should show read > 0."
```

### 4.7 Done criteria for Slice A

- [ ] `tests/unit/test_llm_caching.py` passes
- [ ] `grep -n "cache_control" llm/ensemble.py llm/chief_director.py 2>/dev/null` shows the change in every call site identified by Task A.0
- [ ] An operator-observed `[LLM-CACHE] ... cache_read=<N>` line appears on the second LLM call of a real pipeline run (manual verification — outside the unit test, but documented as the production check)
- [ ] Full `.venv/bin/python -m pytest tests/unit/` is green
- [ ] No regression in `import web_server` or `import cinema.shots.controller`

---

## 5. Slice B — Negative prompts from validator failure reasons

### 5.1 Files this slice owns

```
llm/negative_prompts.py        ← (new) NEGATIVE_PROMPT_BY_FAILURE_REASON mapping + lookup
tests/unit/test_negative_prompts.py  ← (new) verify mapping + lookup behavior
kling_native.py                ← consume negative prompts in prompt builder
sora_native.py                 ← same
veo_native.py                  ← same
cinema/shots/controller.py     ← thread last failure reason into the per-engine call
```

**Decomposition rationale:** the mapping and lookup are one focused module that doesn't belong in `identity/validator.py` (which owns the validation logic, not its consequences) or in any single engine module (since it's cross-engine). The engines consume it at their prompt-building seam; the shot controller threads the failure reason into the engine call.

### 5.2 Per-failure-reason mapping

The mapping needs to come from `identity/validator.py`'s actual failure-reason values. Don't invent reasons — read the validator first.

#### Task B.0 — Audit validator failure reasons

**Files:**
- Read: `identity/validator.py` — find the enum or string constants used to label failures

- [ ] **Step 1: Find the failure-reason taxonomy**

Run: `cd /Users/hyungkoookkim/Content && grep -n "failure_reason\|FAIL\|REJECT\|reason=" identity/validator.py | head -30`
Expected: a finite list of failure reasons, either as an Enum, a set of string constants, or returned from validator functions.

- [ ] **Step 2: Document the taxonomy**

Write the list in your task report. Example shape:

```
FACE_ANGLE_EXTREME   — side profile / >45° head turn
SMALL_FACE_REGION    — face occupies <X% of frame
LOW_ARCFACE_SCORE    — cosine similarity < threshold
NO_FACE_DETECTED     — detector returned 0 faces
MOTION_BLUR_FACE     — face region motion-blurred
... (whatever the real taxonomy is)
```

- [ ] **Step 3: Confirm scope with operator review** (or document the default decision)

The mapping you build in Task B.1 covers the reasons listed in this taxonomy. Unknown reasons (new ones added later) fall through to empty negative prompt. Per the operator decision in § 3.2: this is opt-in. Confirm in the task report.

No commit for this task — it's an audit.

### 5.3 Task B.1 — Build the negative-prompts module (TDD red phase)

**Files:**
- Create: `tests/unit/test_negative_prompts.py`

- [ ] **Step 1: Write the failing test**

```python
"""Verify the failure-reason → negative-prompt mapping.

The mapping is a pure lookup. Test that:
- Each known failure reason returns a non-empty string
- Unknown reasons return empty string (opt-in semantics)
- The returned string is per-engine-tunable (the API takes a single
  hint string that the engine wrapper formats appropriately)
"""

from __future__ import annotations


def test_known_failure_reason_returns_non_empty():
    from llm.negative_prompts import get_negative_prompt_for_failure

    # Use a reason from the audited validator taxonomy — replace with real value
    result = get_negative_prompt_for_failure("FACE_ANGLE_EXTREME")
    assert isinstance(result, str)
    assert result != ""
    assert "profile" in result.lower() or "side" in result.lower(), (
        f"FACE_ANGLE_EXTREME should describe what to avoid; got: {result!r}"
    )


def test_unknown_failure_reason_returns_empty():
    from llm.negative_prompts import get_negative_prompt_for_failure

    result = get_negative_prompt_for_failure("ZZZ_UNKNOWN_REASON")
    assert result == "", (
        f"unknown reason must return empty string (opt-in), got: {result!r}"
    )


def test_none_failure_reason_returns_empty():
    """Defensive: passing None for the first take (no prior failure) → empty."""
    from llm.negative_prompts import get_negative_prompt_for_failure

    assert get_negative_prompt_for_failure(None) == ""


def test_multiple_reasons_compose():
    """If the validator emits multiple reasons, they should compose."""
    from llm.negative_prompts import get_negative_prompt_for_failures

    result = get_negative_prompt_for_failures(["FACE_ANGLE_EXTREME", "SMALL_FACE_REGION"])
    assert isinstance(result, str)
    assert result != ""
    # Both contributions should be present (order doesn't matter, but content does)
    lower = result.lower()
    assert ("profile" in lower or "side" in lower), "missing FACE_ANGLE_EXTREME contribution"
    assert ("small" in lower or "distant" in lower or "blurry" in lower), "missing SMALL_FACE_REGION contribution"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /Users/hyungkoookkim/Content && .venv/bin/python -m pytest tests/unit/test_negative_prompts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'llm.negative_prompts'`.

- [ ] **Step 3: Commit the failing test**

```bash
git add tests/unit/test_negative_prompts.py
git commit -m "test(negative-prompts): assert mapping + opt-in semantics (failing)"
```

### 5.4 Task B.2 — Implement the negative-prompts module (TDD green phase)

**Files:**
- Create: `llm/negative_prompts.py`

- [ ] **Step 1: Write the minimal implementation**

```python
"""Negative-prompt vocabulary keyed off identity-validator failure reasons.

When a take fails validation, the next attempt for that shot gets a
negative-prompt hint describing what the previous take got wrong. This
is opt-in: only known failure reasons contribute; unknown reasons fall
through to empty string (caller decides what to do with it).

The mapping below is calibrated against `identity/validator.py`'s
failure-reason taxonomy. When that taxonomy adds new reasons, add the
corresponding entry here. Unknown reasons NEVER raise — they're treated
as "no specific guidance" and the caller's default behavior kicks in.

Per-engine formatting (Kling vs Sora vs Veo phrasing) is the caller's
responsibility — this module returns plain English; the engine wrapper
adapts it.
"""

from __future__ import annotations

from typing import Iterable, Optional


# Map keys MUST match identity/validator.py's failure-reason values
# verbatim. If you rename a validator reason, update this mapping
# in the same commit.
NEGATIVE_PROMPT_BY_FAILURE_REASON: dict[str, str] = {
    "FACE_ANGLE_EXTREME": "profile view, side angle, head turned away, obscured face",
    "SMALL_FACE_REGION": "small distant face, tiny face, blurry features, face too far from camera",
    "LOW_ARCFACE_SCORE": "wrong person, different face, identity drift, mismatched features",
    "NO_FACE_DETECTED": "no face visible, hidden face, fully obscured, no person",
    "MOTION_BLUR_FACE": "motion blur on face, smeared features, low-shutter blur",
    # TODO(operator): extend this table as new validator failure reasons appear.
    # See identity/validator.py for the canonical taxonomy.
}


def get_negative_prompt_for_failure(reason: Optional[str]) -> str:
    """Return the negative-prompt string for a single failure reason.

    Opt-in semantics: unknown reasons return ''. Caller decides whether
    to skip injection or fall back to a generic negative prompt.
    """
    if reason is None:
        return ""
    return NEGATIVE_PROMPT_BY_FAILURE_REASON.get(reason, "")


def get_negative_prompt_for_failures(reasons: Iterable[str]) -> str:
    """Compose multiple failure reasons into a single negative prompt.

    Joins with ', '. Skips unknown reasons silently (opt-in). Returns
    '' when no known reasons are supplied.
    """
    parts = [
        NEGATIVE_PROMPT_BY_FAILURE_REASON[r]
        for r in reasons
        if r in NEGATIVE_PROMPT_BY_FAILURE_REASON
    ]
    return ", ".join(parts)
```

**Important:** the keys in `NEGATIVE_PROMPT_BY_FAILURE_REASON` MUST match the actual taxonomy you audited in Task B.0. If the validator uses different reason strings, use *those* strings — the table above is a template.

- [ ] **Step 2: Run the test to verify it passes**

Run: `cd /Users/hyungkoookkim/Content && .venv/bin/python -m pytest tests/unit/test_negative_prompts.py -v`
Expected: all 4 tests PASS.

If a test still fails, the cause is almost always: (a) the test asserts text that isn't in the mapping ("profile" / "side" / "small" / etc.) — adjust either the test or the mapping; or (b) the validator's real failure reasons differ from the template — use the real names.

- [ ] **Step 3: Commit**

```bash
git add llm/negative_prompts.py
git commit -m "feat(negative-prompts): map identity-validator failures to per-engine negatives

Opt-in: known failure reasons (FACE_ANGLE_EXTREME, SMALL_FACE_REGION,
LOW_ARCFACE_SCORE, NO_FACE_DETECTED, MOTION_BLUR_FACE) contribute
descriptive negative phrases; unknown reasons fall through to empty
string so the caller can decide what to do (likely: nothing).

Per-engine phrasing (Kling vs Sora vs Veo) is the engine wrapper's
job — this module returns plain English, the wrapper adapts."
```

### 5.5 Task B.3 — Wire into Kling, Sora, Veo prompt builders

**Files:**
- Modify: `kling_native.py` — the function that builds the per-shot Kling prompt (lines ~86-150 per the original survey)
- Modify: `sora_native.py` — same (lines ~42-88)
- Modify: `veo_native.py` — same (lines ~57-114)

Each engine wrapper has a prompt-builder function. They each take some kind of "shot config" and return the final prompt string sent to the video API. The wiring:

1. Add an optional `failure_reasons: list[str] | None = None` argument.
2. If `failure_reasons` is non-empty, fetch `get_negative_prompt_for_failures(failure_reasons)`.
3. Append the negative-prompt string to the API's negative-prompt field (Kling, Veo) or interpolate into the prompt for engines without an explicit negative field (Sora).

#### Task B.3.a — Kling

- [ ] **Step 1: Read the current Kling prompt builder**

Run: `cd /Users/hyungkoookkim/Content && grep -n "def.*prompt\|negative" kling_native.py | head -20`
Find the builder function and the Kling API's negative-prompt field name (it's typically called `negative_prompt` or similar).

- [ ] **Step 2: Add failure_reasons parameter + wire it in**

Pseudocode (adapt to the real signature):

```python
def build_kling_prompt(shot, *, failure_reasons: list[str] | None = None) -> dict:
    # ... existing logic ...
    payload = {...}

    if failure_reasons:
        from llm.negative_prompts import get_negative_prompt_for_failures
        neg = get_negative_prompt_for_failures(failure_reasons)
        if neg:
            existing = payload.get("negative_prompt", "")
            payload["negative_prompt"] = f"{existing}, {neg}".strip(", ")
            print(f"   [NEG-PROMPT] kling: appended negatives for reasons={failure_reasons}")

    return payload
```

- [ ] **Step 3: Run import smoke**

Run: `cd /Users/hyungkoookkim/Content && .venv/bin/python -c "import kling_native; print('OK')"`
Expected: `OK`, no syntax errors.

- [ ] **Step 4: Repeat for Sora and Veo**

Sora may not have a native negative-prompt field — interpolate into the main prompt with phrasing like `"avoiding: <negatives>"`. Veo typically has one; treat it like Kling.

- [ ] **Step 5: Commit each engine separately**

```bash
git add kling_native.py
git commit -m "feat(kling): accept failure_reasons, append negative-prompt hint"

# Then sora_native.py
# Then veo_native.py
```

Keeping one commit per engine gives clean diffs for the spec/code-quality reviewers.

### 5.6 Task B.4 — Thread failure_reasons through the shot controller

**Files:**
- Modify: `cinema/shots/controller.py` — the function that calls the engine wrappers (look for calls to `generate_ai_video`, `build_kling_prompt`, or similar)

- [ ] **Step 1: Find where the engine wrapper gets called**

Run: `cd /Users/hyungkoookkim/Content && grep -n "kling_native\|sora_native\|veo_native\|generate_ai_video" cinema/shots/controller.py | head -10`
Expected: 1-3 call sites in the per-shot loop.

- [ ] **Step 2: Find where the previous take's failure reason lives**

The controller already tracks per-take metadata (per `controller.py:778-798` motion-gate code). The validator failure reason should be in `previous_take["metadata"]["failure_reason"]` or similar. Confirm by grep:

Run: `cd /Users/hyungkoookkim/Content && grep -n "failure_reason\|failure_reasons" cinema/shots/controller.py | head -10`

- [ ] **Step 3: Pass failure_reasons into the engine call on retry**

Pseudocode:

```python
# In the retry path of generate_motion_take (or wherever takes get re-generated):
prev_take = take_history[-1] if take_history else None
prev_failures = (prev_take or {}).get("metadata", {}).get("failure_reasons", [])
# If failure_reasons is a single string, normalize to a list
if isinstance(prev_failures, str):
    prev_failures = [prev_failures]

payload = build_kling_prompt(shot, failure_reasons=prev_failures)
```

- [ ] **Step 4: Import-smoke + run motion-gate tests as a regression check**

Run: `cd /Users/hyungkoookkim/Content && .venv/bin/python -c "import cinema.shots.controller; print('OK')"`
Run: `cd /Users/hyungkoookkim/Content && .venv/bin/python -m pytest tests/unit/test_motion_gate.py -v`
Expected: import OK; all motion-gate tests still pass (this slice doesn't touch motion-gate logic, but the controller change shouldn't regress).

- [ ] **Step 5: Commit**

```bash
git add cinema/shots/controller.py
git commit -m "feat(controller): thread previous-take failure_reasons into engine prompt builders

On retry, the engine prompt builder gets the prior take's failure
reasons so it can include matching negative-prompt hints. First-try
takes pass an empty list (no negative prompt — happy path unchanged)."
```

### 5.7 Done criteria for Slice B

- [ ] `tests/unit/test_negative_prompts.py` passes (4/4)
- [ ] `tests/unit/test_motion_gate.py` still passes (no regression)
- [ ] All three engine modules (`kling_native`, `sora_native`, `veo_native`) accept `failure_reasons` parameter and apply negatives when non-empty
- [ ] `cinema/shots/controller.py` passes prior-take `failure_reasons` into the engine builder on retry
- [ ] A manual test: trigger a deliberately-failing take (face crop, side angle), confirm in logs `[NEG-PROMPT] kling: appended negatives for reasons=[...]`
- [ ] `import web_server`, `import cinema.shots.controller`, `import llm.ensemble` all clean

---

## 6. Cross-cutting done criteria for Phase 1

The whole plan is done when:

- [ ] Both slices' done criteria pass (§4.7, §5.7)
- [ ] One end-to-end test pass: a real pipeline run shows
  - At least one `[LLM-CACHE] ... cache_read=<N>` log line on a non-first LLM call
  - At least one `[NEG-PROMPT] ... reasons=[...]` log line on a retry triggered by a deliberately-bad take
- [ ] `git diff --stat origin/main..HEAD` shows ~400-700 LOC across the two slices (rough estimate; the LLM-caching diff is small but the negative-prompts wiring touches 5 files)
- [ ] No regressions in `tests/unit/`

---

## 7. What NOT to do in this plan

- **DO NOT add enforcing quality gates** (VBench, coherence, aesthetic). That's Phase 4 and explicitly requires calibration data per § 1.
- **DO NOT modify `MOTION_FIDELITY_FLOORS` values**. The placeholders are placeholder by operator decision; the calibration pass is pending.
- **DO NOT touch model selection in `llm/ensemble.py`**. Role-conditioned routing (A.9) is a separate phase that needs its own benchmarking pass.
- **DO NOT add few-shot examples to prompts** (A.7). That's prompt-engineering review work, not a calibration-free slice.
- **DO NOT touch cinema/ migration**. Phase 5.
- **DO NOT batch Kling shots**. Phase 6, after Phase 5 unblocks per-shot parallelism.
- **DO NOT widen `except Exception` blocks or restructure them**. Phase 2 — typed errors are their own slice and changing them mid-phase muddies the failure-attribution audit.
- **DO NOT modify the validator's failure-reason taxonomy.** Slice B *consumes* the taxonomy; it shouldn't change it. If new reasons are needed, that's a separate task in the identity domain.

---

## 8. Roadmap — Phases 2-6 (each becomes its own plan file)

The following phases reference the original audit's items by their `A.X` / `B.X` labels.

### Phase 2 — Failure-attribution prerequisites

**Plan file (when ready):** `docs/superpowers/plans/<date>-failure-attribution.md`

**Contents:**
- B.5 — Replace broad `except Exception` with typed errors (`RunPodError`, `ImageGenerationError`, `MotionEngineError`, `ValidatorError`). Log root cause. Track retry cost.
- B.8 — Atomic file writes (`tempfile` + `os.rename`) in `phase_c_assembly.py`, `main.py`, `cleanup.py`.
- Effort: medium (~10-15 files touched, but each change is local).
- Why first: closed-loop gating (Phase 4) needs clean failure attribution; without typed errors, "gate retry" becomes "guess and retry."

### Phase 3 — Calibration scripts

**Plan file:** `docs/superpowers/plans/<date>-quality-calibration-scripts.md`

**Contents:** one script per gate, modeled on `scripts/calibrate_motion_floor.py`:
- `scripts/calibrate_vbench_floor.py` — dump VBench dimension scores per shot for operator grading
- `scripts/calibrate_coherence_floor.py` — coherence scores + eyeball grades
- `scripts/calibrate_aesthetic_floor.py` — aesthetic scores + grades
- Add the corresponding placeholder thresholds (e.g., `VBENCH_DIMENSION_FLOORS`, `COHERENCE_FLOOR`, `AESTHETIC_FLOOR`) to a new module — explicitly marked TODO(calibrate) and advisory-only.

### Phase 4 — Closed-loop gating (the headline work)

**Plan file:** `docs/superpowers/plans/<date>-closed-loop-gating.md`

**Contents:** A.1, A.2, A.3, A.4, A.5 — but **advisory-only** like motion-gate. SSE events (`VBENCH_BELOW_FLOOR`, `COHERENCE_BELOW_FLOOR`, etc.) + UI chips in `ReviewStage.tsx`. Operator-override mechanism explicit. Multi-task plan: ~8-12 sub-slices. Requires Phases 2 + 3 complete.

**Critical operator decisions to lock at brainstorming time:**
- Advisory or enforcing? (Recommend advisory until ≥100 shots per gate of calibration data.)
- What's the "force-ship anyway" UX in `ReviewStage.tsx`?
- Does Phase E (`phase_e_learning.py`) consume these events to adjust thresholds adaptively, or stay manual?

### Phase 5 — Complete the legacy → cinema/ migration

**Plan file:** `docs/superpowers/plans/<date>-cinema-migration-phase-c.md`

**Contents:** B.4 — finish migrating phases C-E into `cinema/phases/*.py`. The migration design lives at `docs/CINEMA_PIPELINE_MIGRATION_DESIGN.md`. This is a very large effort and probably wants splitting further (one plan per phase to migrate).

**Why before Phase 6:** Phase 6's biggest win (Kling storyboard batching) needs per-shot parallelism, which is blocked by `cinema/shots/controller.py:1079` per the original survey.

### Phase 6 — Optimizations

**Plan file:** `docs/superpowers/plans/<date>-pipeline-optimizations.md`

**Contents (in priority order):**
- B.1 — Kling storyboard batching, ONLY after a Lane C survey confirms the existing-but-uncalled code path was abandoned for a non-quality reason
- B.3 — Exponential backoff with jitter on video-API polling
- B.6 — Enforce `MAX_CASCADES = 2` correctly
- B.7 — Circuit breaker on quota-exhausted APIs
- B.10 — Split `phase_c_ffmpeg.py` (1252 LOC) into focused modules
- B.12 — Cache LLM research + ComfyUI workflow JSON with 24h TTL
- B.13 — SQLite indexes on `cost_log(video_id)` and `cost_log(timestamp)`

---

## 9. Pricing implication (context, not code)

Closing Phase 1 (this plan) changes:

- **LLM token spend:** ~70-80% reduction on system-prompt input tokens for warm calls (B.2). On a session that makes ~50 LLM calls with a 1600-token system prompt, that's ~50k input tokens saved → roughly $0.15-0.50 saved per session depending on model. Compounds quickly across volume.
- **Retry quality:** validator-driven negatives (A.6) should reduce repeat-failure rates on validator-triggered retries — fewer second-attempt failures means fewer expensive third attempts.

Neither change shifts the per-shot baseline cost; both reduce *waste*. The price anchor for this codebase ($3,000/video per `feature/remaining-gaps` PR notes) stays the same; this slice improves margin, not pricing.

---

**End of plan.** Ready to execute via `superpowers:subagent-driven-development`.
