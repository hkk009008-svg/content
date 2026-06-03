# Design — Part-3 deferred moderate/minor fixes (full ledger clear)

*Date: 2026-06-03. Branch: `feat/max-tier-provisioning` (== `main` == `origin` at `26d9b1e`).
Status: DRAFT (pre spec-review).*

## 1. Context

The Test/Audit program (spec `docs/superpowers/specs/2026-06-02-program-test-audit-plan-design.md`)
characterized 6 zero-test components with offline tests that **pin current behavior**, tagging
suspicious behaviors `# CANDIDATE BUG`. Part-3's **HIGH** subset (F1/F2/F3) shipped last session
(`38064f9..20673a6`, Lane-V-clean at `25d9634`). This spec covers the **deferred moderates/minors** —
the remaining `# CANDIDATE BUG` markers across 5 components — as a single **full-ledger-clear** cycle,
mirroring the Part-3 HIGH design-first approach (brainstorm → spec → plan → subagent-driven TDD).

**Grounding note (ADR-013 / handoff discipline):** every finding below was re-adjudicated against the
**real source** (not the test's claim) and against the program's capability intent (PROGRAM-MANUAL §5).
The survey was wrong in 3 places — corrections are called out inline. Line numbers are **as-of `26d9b1e`
and approximate**; implementers verify against actual source and report divergences (plan-vs-source rule).

## 2. Scope (user-approved: "full ledger clear")

| Bucket | Findings | Action |
|---|---|---|
| **FIX** (behavior change, TDD flip marker) | G(sora)2, G(ltx)1, G1(style), G3(style), G4(identity), G2(vision) | 6 fixes |
| **CLEANUP** (mechanical, low-risk) | sora dead `download_url`, validator:822 nit, chief_director:341 annotation | 3 cleanups |
| **DOCUMENT** (no behavior change — comment + downgrade marker) | G(sora)1, G(ltx)3, G5(vision) | 3 docs |
| **LEAVE** (note only) | G3(identity) `MULTIPLE_FACES_AMBIGUOUS` | 1 leave |

**Marker-resolution rule:** after this cycle, **zero `# CANDIDATE BUG` markers remain**. For FIX items the
test flips to assert the *fixed* behavior (watch fail → implement → watch pass). For DOCUMENT/LEAVE items the
test still pins current behavior but the marker comment is rewritten from `# CANDIDATE BUG` to
`# DOCUMENTED-INTENTIONAL:` (or `# DEAD-CODE (intentional):`) with a one-line rationale, so the grep audit
(`grep -rn "CANDIDATE BUG" tests/unit/`) returns empty as the cycle's done-signal.

## 3. The FIX items

### 3.1 G(sora)2 — Sora resolution ignored (⭐ capability) — `sora_native.py`

**Current:** `generate_video(resolution="1080p", ...)` accepts the param (signature ~`:49`) but never reads
it — `size="1280x720"` is hardcoded (~`:116`) and the image is always resized to 1280×720 (~`:97`). The
production caller `phase_c_ffmpeg.py:~249` never passes `resolution=`. The OpenAI Sora-2 API `size` field
accepts `1920x1080`, so we ship 720p while promising 1080p — a silent capability floor (PROGRAM-MANUAL §5
treats resolution as a primary quality lever).

**Fix:** add `RESOLUTION_MAP = {"480p":"480x270","720p":"1280x720","1080p":"1920x1080"}` (mirror
`ltx_native.RESOLUTION_MAP`). Wire it into the `size=` field AND the `img.resize()` call. Update the caller
`phase_c_ffmpeg.py` to pass `resolution="1080p"` (capability-max default). ~10 LOC, mechanical.

**Marker:** `tests/unit/test_sora_native.py:~180` flips from "size is always 1280x720" to "size honors
resolution → 1080p maps to 1920x1080"; add a 480p/720p parametrization.

**Blast radius:** 1 production caller (`phase_c_ffmpeg.py`). Low risk — only affects Sora-routed shots.

### 3.2 G(ltx)1 — LTX HTTPError no fallback + over-broad generic fallback (⭐ capability) — `ltx_native.py`

**Current:** in `_native_generate` (~`:262-271`), `urllib.request.HTTPError` is caught WITHOUT triggering
the FAL fallback (falls through to implicit `None`), while a *generic* `Exception` DOES trigger the FAL
fallback. So a transient API 5xx silently drops the shot, while a *local* bug (bad path, JSON decode error)
wrongly triggers (and burns) a FAL call. `_native_transition`/`_native_request`/`_download_native_result`
are DORMANT — not on this live path; do not touch.

**Fix (Option A — recommended):** differentiate by HTTP status. `HTTPError`: `code >= 500` AND FAL
available → fall back to FAL; else log + `None`. Generic `Exception`: if it's a local error
(`OSError`/`FileNotFoundError`/`json.JSONDecodeError`) → log + `None` (no fallback); else → existing FAL
fallback. ~8 LOC, mechanical. 5xx→FAL restores resilience (capability); local-error guard stops bug-masking.

**Marker:** `tests/unit/test_ltx_native.py:~317` flips "HTTPError → no fallback" to "5xx HTTPError → FAL
fallback fires"; `:~359` flips "generic always falls back" to "local OSError → no fallback (None)".

**Blast radius:** caller chain `phase_c_ffmpeg.py:~318 → generate_video → _native_generate`; the caller
already handles `None` (`try_next_api` at ~`:334`). Internal change, no signature change.

### 3.3 G1 — `use_web_research` flag inconsistently honored (⚠ DECISION) — `llm/style_director.py`

**Current:** `research_cinematography(mood, ...)` (the primary mood-grounding research) is called
**unconditionally** (~`:46-54`, comment: "Always ... grounds the LLM in real cinema"), while the *secondary*
`_research_aesthetic` reference-film call IS gated by `use_web_research` (~`:57`). So the flag is **partially
live** — it gates one research call but not the other. `use_web_research` defaults `False` and is plumbed
from the web API (`web_server.py:~1427`). A flag that's advertised + plumbed but only half-honored is a
contract bug regardless of which way it's resolved.

**⚠ DESIGN DECISION (flagged for spec-review veto).** Three resolutions:
- **(a) Remove the flag** — research always-on, delete `use_web_research` from the signature + web plumbing.
  Cleanest; keeps capability; but removes an outward API field (it was ignored anyway) and removes an
  operator knob.
- **(b) Honor strictly** — gate both calls behind `use_web_research`. Default `False` → research OFF by
  default → **silent capability regression** (rejected).
- **(c) RECOMMENDED — gate both consistently, default `True`.** Make `use_web_research` gate *both* research
  calls (consistent contract), and flip its default to `True`. Research stays on by default (capability
  preserved), the contract bug is fixed, AND the operator retains a working knob to disable web research for
  speed/cost (PROGRAM-MANUAL "capability-knobs playbook" favors a working knob over a removed one). The
  web-API default also flips to `True` where omitted.

This is the only finding in the batch with a real capability-relevant trade-off; per PROGRAM-MANUAL intent
it is surfaced rather than silently decided. **Default plan = (c)**; reviewer/user may redirect to (a).

**Fix (c):** ~5-8 LOC. Wrap the `research_cinematography` block in `if use_web_research:`; flip the signature
default + the `web_server.py` `.get("use_web_research", True)` default.

**Marker:** `tests/unit/test_style_director.py:~275/:~298` flips "called unconditionally" to "honors
`use_web_research`: True → called, False → skipped"; add the default-True assertion.

**Blast radius:** 1 production caller (`web_server.py:~1420`). `research_cinematography` is also used by
`scene_decomposer.py` independently — out of scope, do not touch. Outward contract: the web endpoint's
default behavior is unchanged (research still on by default under (c)).

### 3.4 G3 — `openai.OpenAI()` constructed before `try` — `llm/style_director.py`

**Current:** `client = openai.OpenAI(api_key=api_key)` (~`:42`) is outside the `try` block (~`:92`) whose
`except` returns `_default_style_rules`. If construction raises (SDK import/version, DNS at init), it
propagates uncaught — defeating the graceful-degradation fallback that feeds every downstream shot.

**Fix:** move the construction inside the `try` at ~`:92`. ~3 LOC, mechanical. The separate research `try`
(~`:46`, has its own `except: pass`) is unaffected.

**Marker:** `tests/unit/test_style_director.py:~343` flips "client constructed before try (no fallback if it
raises)" to "construction failure → falls back to `_default_style_rules`".

**Blast radius:** local; 1 caller. Fallback path already exists/tested. Zero regression risk.

### 3.5 G4 — `validate_video(threshold=0.0)` divergence (latent) — `identity/validator.py`

**Current:** `th = threshold or get_threshold_for_shot(...)` (~`:155`) makes `th` the shot threshold when
`threshold=0.0` (0.0 is falsy), but `if threshold is None:` (~`:166`) is False so the local `threshold`
stays `0.0`; the actual gate `matched = similarity >= threshold` (~`:506`) then passes EVERYTHING. **Latent:**
the only production caller (`continuity_engine.py:~616`) passes through a non-zero threshold; no prod path
passes `0.0` today. Still a real defect — a caller using `0.0` to mean "score but don't gate" silently gets
`passed=True` for off-model frames, anti-capability for the identity gate.

**Fix (Option A):** collapse to one variable —
`threshold = threshold if threshold is not None else get_threshold_for_shot(...)` (replace the `or`
anti-pattern at ~`:155`), delete the `:166-167` re-assignment, use `threshold` consistently. ~2 LOC.
`0.0` becomes a real override (gate disabled *intentionally*, not by accident). Does NOT re-touch the
Part-3 `overall_score: Optional[float]` surface.

**Marker:** `tests/unit/test_identity_validator.py:~876` flips "threshold=0.0 → everything passes
(divergence)" to "threshold=0.0 is honored as a real override (single variable, no divergence)".

**Blast radius:** 1 production caller (`continuity_engine.py:~616`, passes `None` → unchanged behavior).

### 3.6 G2 — FaceFusion silent `None` (mild) — `phase_c_vision.py` + `cinema/shots/controller.py`

**Current:** `face_swap_video_frames` (~`:52-104`) is a best-effort cascade (fal.ai → FaceFusion CLI →
skip). The FaceFusion branch gates on `returncode==0 AND os.path.exists(output)` (~`:96`); a partial write
(rc 0, no file) falls through to `return None`. The **only** caller is the *manual operator* face-swap
action (`controller.py:~1939`): `if result: variant["path"] = result` — on `None` the variant silently keeps
the un-swapped source and the action reports success. The operator clicked "face swap," it no-op'd, and they
weren't told. (Same *class* as Part-3 F1 silent-pass, but bounded to a manual action, not a core gate.)

**Fix (caller-side, minimal):** at `controller.py:~1939`, when `result is None`, surface an explicit reason
on the variant/response (e.g. `variant["warning"] = "face_swap could not be applied (no swapper
succeeded)"` or `{"success": True, "warning": ...}`) so the operator isn't misled. Do NOT change the
cascade's intentional fal→facefusion→skip behavior. ~3-5 LOC. (The function's `None` return is fine; the bug
is the *caller* treating None as a clean success.)

**Marker:** `tests/unit/test_phase_c_vision.py:~248/:~259` keeps pinning `face_swap_video_frames` → `None`
on rc0+missing (that's correct cascade behavior — re-comment to `# DOCUMENTED-INTENTIONAL: cascade skip`),
and the *new* assertion goes on the caller surfacing a warning (add a controller-level test, or assert the
function still returns None + document that the caller now surfaces it). Implementer chooses the cleanest
test home; the done-signal is the marker downgraded + a test covering the surfaced-reason.

**Blast radius:** 1 caller (`controller.py:~1939`, operator action). No core-pipeline path. Low risk.

## 4. The CLEANUP items

### 4.1 sora dead `download_url` — `sora_native.py`
Lines ~`:133-142` set `download_url` via an attr-sniffing loop that is **never read** (the real download uses
`self.client.videos.download_content(video.id)` at ~`:146`); `import urllib.request` (~`:14`) exists only for
this dead path. Delete the loop + the unused import. ~9 LOC removal, mechanical. Verify no other `urllib`
use in the file first.

### 4.2 validator:822 nit — `identity/validator.py`
`_vision_llm_validate_video` `total_frames==0` (~`:822-828`) returns an INLINE `passed=False/0.0` result with
no `failure_reason`, unlike `_missing_output_result` (~`:714`, sets
`metadata.failure_reason=GENERATED_IMAGE_MISSING`). Route both `total_frames==0` sites through
`_missing_output_result(shot_type, threshold)` for shape consistency + diagnostic metadata. ~4 LOC, behavior
unchanged (`passed=False` either way). (Director Lane V nit.)

### 4.3 chief_director:341 annotation — `llm/chief_director.py`
Stale annotation `identity_score: float = 0.0` — runtime can now be `Optional[float]` post-Part-3. Change to
`Optional[float]`. 1 LOC. **Unverified by adjudication subagent** — implementer confirms the line + that no
reader breaks on the annotation widening (it's a hint, not runtime) before editing. (Director Lane V nit.)

## 5. The DOCUMENT items (no behavior change — comment + downgrade marker)

### 5.1 G(sora)1 — empty-key `EnvironmentError` — `sora_native.py:~25`
**Survey-corrected to intentional.** Raise-on-init matches `veo_native`'s convention; the caller
(`phase_c_ffmpeg.py`, broad `except` → `try_next_api`) handles it as fallback. `ltx_native`'s silent-None is
the *outlier*, not Sora. Add a class-docstring note ("raise-on-init like Veo; LTX uses deferred-mode"); flip
the test marker to `# DOCUMENTED-INTENTIONAL: raise-on-init convention (matches veo_native; caller handles)`.

### 5.2 G(ltx)3 — `"720p"`→1080p — `ltx_native.py:~36`
**Intentional + already inline-commented.** `RESOLUTION_MAP["720p"]` == 1080p because LTX native lacks true
720p; zero live 720p callers (production passes explicit `"1080p"`/`"4k"`). Capability-positive (more pixels).
Keep behavior; flip the test marker to `# DOCUMENTED-INTENTIONAL: LTX has no true 720p; upgraded to 1080p`.
(Optional follow-up, NOT this cycle: rename default arg `"720p"`→`"1080p"` for honesty.)

### 5.3 G5 — hardcoded 0.7 vision threshold — `phase_c_vision.py` / `identity/validator.py`
**Survey-corrected — NOT a live gate bug.** `validate_identity_vision`'s `result["match"]` (hardcoded `0.7`)
is **advisory**: the `IdentityValidator` wrapper recomputes `matched` with its shot-aware threshold
(`validator.py:~754`) on the production path, so 0.7 never governs a real gate decision. Add a comment on
the raw function ("`match` is advisory; production callers re-threshold via IdentityValidator"); flip the
test marker to `# DOCUMENTED-INTENTIONAL: advisory match key; prod gate re-thresholds`. (Do NOT remove the
`match` key — keeping it is lower-risk than a dict-shape change; the comment is the fix.)

## 6. The LEAVE item

### 6.1 G3(identity) — `MULTIPLE_FACES_AMBIGUOUS` dead enum — `identity/types.py` / `identity/validator.py`
`_classify_failure` never returns it (0 grep hits in `validator.py`); genuinely unreachable. Leave the enum
member (cheap to keep for a future multi-face path). Flip the test marker to
`# DEAD-CODE (intentional): enum member reserved; no classifier path returns it`.

## 7. Testing strategy (TDD — non-negotiable)

Per finding: (1) edit the characterization test to assert the *target* state (fixed behavior for FIX;
re-worded marker for DOCUMENT/LEAVE), (2) run it, watch it FAIL against current code (FIX items only),
(3) implement the minimal fix, (4) watch it PASS, (5) run the component's full test module, (6) run the full
unit suite. **Never weaken a test to pass.** Done-signal for the whole cycle:
`grep -rn "CANDIDATE BUG" tests/unit/` returns **empty**, and `pytest tests/unit/ -q` is green
(baseline 1499/3/0; expect +N subtests, 0 regressions).

## 8. Out of scope / non-goals

- DORMANT LTX levers (`_native_transition`/`_native_request`/`_download_native_result`) — do not touch.
- `research_cinematography` callers other than `style_director` (e.g. `scene_decomposer`) — do not touch.
- Removing the `result["match"]` key or the `MULTIPLE_FACES_AMBIGUOUS` enum — comment-only, no shape change.
- The LTX `"720p"` default-arg rename — optional follow-up, not this cycle.
- Part 4 (UI surfacing) and Part 5 B/C (prune re-verify) — separate cycles.
- Live wired-E2E — spend-gated, separate from testing.

## 9. Execution sequencing (subagent-driven)

Independent per component → one implementer subagent per component (Lane B), parallel-safe but executed
sequentially per the orchestration model (one implementer at a time; spec + code-quality review per task).
Lane-A candidates (do in main): chief_director:341 (1 LOC), the DOCUMENT/LEAVE marker re-wordings (comment
edits). Lane-B (subagent): sora_native (G(sora)2 + dead download_url + G(sora)1 doc), ltx_native (G(ltx)1 +
G(ltx)3 doc), style_director (G1 + G3), identity/validator (G4 + validator:822 nit), phase_c_vision +
controller (G2 + G5 doc). ~5 implementer tasks. The writing-plans step produces the per-task breakdown.

## 10. Risk summary

All fixes are ≤10 LOC, single-caller, with the caller already handling the relevant return shape. The only
outward-facing surface is `web_server` `use_web_research` (G1) — resolved (c) keeps default behavior
unchanged (research on). No fix re-touches the Part-3 `Optional[float]` surface. Latent-bug fix (G4) is
behavior-preserving for the live caller. Baseline is green (1499/3/0 at `26d9b1e`, own run) so any
regression stands out cleanly.
