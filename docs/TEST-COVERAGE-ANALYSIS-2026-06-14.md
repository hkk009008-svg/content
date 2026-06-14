# Test-Coverage Analysis & Improvement Proposal — 2026-06-14

*Analysis only. No test code was written in the producing session. This report
maps where the suite is strong vs. thin and proposes a prioritized batch of new
tests. Every count and file:line below was hand-verified against the working
tree (commands cited inline); none is a line-coverage measurement (see §2).*

> **Coordinator verification addendum — 2026-06-14, HEAD `e0999d0` (workflow
> `wf_bf7078e7-4ab`, read-only).** All 56 claims below were independently
> re-verified against the live tree; ~50 confirmed. Corrections applied **in
> place** for: the file-serving path-traversal framing (both endpoints are
> guarded — §4 Tier 1), the `auto_approve` predicate-error claim (a fired veto is
> *preserved*, not dropped — §4 Tier 2), the CRUD line-range/count (§4 Tier 1),
> and the `motion_gate` crash mechanism (§4 Tier 2). Count drifts reconciled:
> test-fns 2110→2112, `lip_sync.py` 1245→1268, untested-route share ~41 (62%)→~46
> (~71%). Original author's verification branch: `claude/test-coverage-analysis-v596bc`.

---

## 1. Summary

The suite is **large and healthy on pure logic**: gate decision-rules, prompt
construction, routing, and persistence are well-exercised. The gaps cluster in
three places that are disproportionately load-bearing:

1. **The HTTP surface** — `web_server.py` exposes 66 routes; ~46 (~71%) have no
   dedicated test, including destructive and pipeline-state-mutating endpoints
   and two file-serving endpoints whose path-containment guard (present and
   correct) has no regression test.
2. **Audio DSP** — `audio/effects.py` and `audio/voiceover.py` have **zero**
   dedicated unit tests; `audio/alignment.py` has only a warning stub.
3. **Orchestration state-mutation paths** — the largest module,
   `cinema/shots/controller.py` (2559 LOC), is exercised only indirectly; its
   `apply_correction` and the full take-minting mutation contract have no
   dedicated test.

Suite size (verified `$ grep -rhE '^\s*def test_' tests/unit/ | wc -l` → **2112**
test functions; `$ ls tests/unit/test_*.py | wc -l` → **129** unit files; **131**
total incl. integration). Route count: `$ grep -cE '@app\.(route|get|post|put|delete|patch)' web_server.py` → **66**.

**Recommended first batch:** Tier 1 (HTTP endpoints) — highest risk-per-effort,
and the existing Flask-test-client patterns make these cheap to write.

---

## 2. Method & caveat (Finding #0: no coverage instrument)

This is a **reference-map analysis, not a line-coverage run.** Two reasons a
`coverage`/`pytest-cov` number is not quoted:

- **No coverage tooling is installed** — neither `coverage` nor `pytest-cov`
  appears in `requirements.txt`. The CI workflow header (`.github/workflows/`)
  explicitly lists "Code coverage reporting" as **deliberately out of scope**
  (a prior decision, not an oversight).
- **No venv exists** in a fresh web-session container, and the dependency stack
  (DeepFace, torch-adjacent, cloud SDKs) is heavy/partly GPU-bound, so a clean
  line-coverage run isn't cheap to stand up here.

Instead, coverage was inferred by (a) mapping each source module to the count of
test files that import/reference its symbols, weighted against module LOC, and
(b) targeted reads of the thinnest large modules to characterize *which*
branches are unexercised. This finds **untested surface**; it cannot prove a
referenced module's branches are *fully* covered.

> **Recommendation #0 — make coverage measurable.** Add `pytest-cov` to
> `requirements.txt` and wire a **non-blocking** (advisory) `--cov` report into
> the `pytest-unit` CI job. This is the single highest-leverage change: it turns
> every subsequent proposal in this report from an estimate into a measured
> number and lets regressions surface automatically. Keep it advisory first
> (report-only, no gate) per the repo's advisory-vs-fail gate convention.

---

## 3. Coverage map

Module → referencing-test-file count (verified by grepping `tests/` for each
module's symbols) cross-referenced with module LOC (`$ wc -l`):

| Module | LOC | Test files ref. | Assessment |
|---|---:|---:|---|
| `web_server.py` | 2712 | 11 | **Thin** — 66 routes, ~46 untested |
| `cinema/shots/controller.py` | 2559 | 23 (indirect) | No dedicated test; mutation paths thin |
| `phase_c_ffmpeg.py` | 1707 | 18 | OK |
| `cinema_pipeline.py` | 1677 | 13 | OK |
| `quality_max.py` | 1248 | 10 | OK |
| `lip_sync.py` | 1268 | 10 | OK |
| `cinema/review/controller.py` | 700 | via `test_auto_approve` | Gate orchestration thin |
| `audio/music.py` | 440 | 1 (Suno only) | FAL path + `master_music` untested |
| `face_validator_gate.py` | 341 | 2 | Boundary/halt paths thin |
| `audio/voiceover.py` | 307 | **0** | No dedicated tests |
| `audio/alignment.py` | 293 | stub only | Provider chain untested |
| `audio/effects.py` | 284 | **0** | No dedicated tests |
| `coherence_analyzer.py` | 277 | 2 | Error / invalid-image paths thin |
| `web_research.py` | 221 | 1 | Error / timeout paths untested |
| `cleanup.py` | 154 | 1 | I/O-error paths untested |

Zero-dedicated-test confirmations (grep returned empty):
`$ grep -rl apply_voice_effect tests/` → none; `$ grep -rl get_voice_direction tests/` → none.

---

## 4. Prioritized gaps

### Tier 1 — HTTP endpoints (recommended first batch)

`web_server.py` has ~20 routes (30%) with dedicated tests today: `/generate` +
`/cancel` (concurrency, `test_web_server_concurrency.py`), `train-lora` gating
(`test_web_server_train_lora_gated.py`), `iterate` (`test_iterate_endpoint.py`),
`reject-auto-approve` (`test_web_server_auto_approve.py`), screening / approve /
re-assemble (`test_screening_endpoint.py`, `test_reassemble_endpoint.py`),
`regenerate` (negative-prompt edge only), `PUT project` aspect, `/api/config`.

The untested, high-risk remainder — write Flask-test-client tests mirroring the
patterns in `test_web_server_concurrency.py` / `test_screening_endpoint.py` /
`test_iterate_endpoint.py`:

| Endpoint (handler) | file:line | Risk if untested |
|---|---|---|
| `api_serve_file` | `web_server.py:1659` | Has a correct `realpath`+containment guard (`:1664-1668`); **no regression test** pins it — a future edit could silently weaken it |
| `api_export` | `web_server.py:2662` | Path is fully server-constructed (hardcoded `exports/final_cinema.mp4`, no user component) — minimal traversal risk; a busy/scoping test is still nice-to-have |
| `api_delete_project` | `web_server.py:538` | Destructive; lock guards present but no HTTP test of delete-vs-running-pipeline race |
| `api_proceed_assembly` | `web_server.py:2222` | Triggers final ffmpeg assembly; no busy-fence test |
| `api_generate_keyframe` | `web_server.py:1702` | Expensive gen, feeds KEYFRAME_REVIEW gate; failure strands operator |
| `api_generate_motion` | `web_server.py:1756` | Expensive gen; concurrency/budget guards unverified |
| `api_approve_final_take` | `web_server.py:1775` | Gate transition cascading into assembly/screening |
| `api_pause` / `api_resume` | `web_server.py:2047` / `:2057` | Pipeline state-machine mutation; pause/resume race unverified |
| `api_restart_shot` | `web_server.py:2082` | State reset / failed-state bypass; no test that prior diagnostics clear |
| object/location/scene CRUD | `web_server.py:1027`–`~1700` | ~18 untested mutators (only 6 live in the 1027–1315 window — objects+locations POST/PUT/DELETE; scenes/dialogue/style extend to ~1700); orphaned references can corrupt project state |

**Start here:** an `api_serve_file` guard-regression test (the containment check
is correct today but untested; `api_export` needs none — no user path component),
cheap and no external deps, then the destructive/state endpoints
(`api_delete_project`, `api_pause`/`api_resume`, `api_restart_shot`), then the
generation/approval gate endpoints.

### Tier 2 — Quality gates & provider error paths

These drive expensive regeneration or spend; the untested branches are the
*decision boundaries* and *failure modes*, not the happy path. Mirror
`test_face_validator_gate.py`, `test_auto_approve.py`, `test_kling_native.py`.

| Target | file:line | Untested behavior / risk |
|---|---|---|
| `face_validator_gate.should_halt` | `face_validator_gate.py:227` | Conjunctive mode + arc-floor-bypass boundary: composite passes but arc barely fails → may halt incorrectly |
| `coherence_analyzer.assess_coherence` | `coherence_analyzer.py:215` | Returns `valid=False` on unreadable image; callers may trust a 0.0 as real data |
| `cinema/auto_approve.check_gate` | `cinema/auto_approve.py:625` | A fired veto is **preserved** when a later predicate raises (`:689-704`, documented as intentional) — NOT dropped; the real gap is that this preserve-on-eval-error path has no test |
| `performance/motion_gate.needs_remotion` | `performance/motion_gate.py:184` | The floor lookup is a dict `.get` (can't raise); the real uncaught path is the **unguarded lazy `import`** at `:207` — should default, not crash |
| `performance/identity_gate.validate_performance_take` | `performance/identity_gate.py:95` | ffmpeg timeout/crash and "no face found" both return `None` — ambiguous to callers |
| `kling_native.poll_task` | `kling_native.py:170` | Backoff plateau at end of schedule → may poll too aggressively, hit rate limits |
| `ltx_native._native_generate` | `ltx_native.py:204` | Empty-200 body with no FAL key (no fallback) should return `None`, not a 0-byte file |
| `cleanup.cleanup_project` | `cleanup.py:56` | glob over symlink/permission-denied dirs silently returns partial results; no skipped-count assert |

### Tier 3 — Audio DSP & orchestration

Lower urgency (some are write-only / not yet wired) but high technical debt.

| Target | file:line | Gap |
|---|---|---|
| `audio/effects.apply_voice_effect` | `audio/effects.py:230` | AU plugin → Pedalboard → FFmpeg cascade; **0 tests** |
| `audio/voiceover.get_voice_direction` | `audio/voiceover.py:284` | Delivery-style resolver (case-norm, fuzzy match, `"natural"` fallback); **0 tests** |
| `audio/alignment` provider chain | `audio/alignment.py` | WhisperX → Whisper word-ts → None cascade + model-cache thread races; warning-stub only |
| `audio/music.master_music` + FAL path | `audio/music.py` | Suno path tested; FAL BGM + DSP mastering chain untested |
| `cinema/shots/controller.apply_correction` | `cinema/shots/controller.py:2331` | Operator-facing correction orchestration (face-swap/upscale/RIFE/grade) — indirect only |
| `cinema/review/controller._run_auto_approve_pass` | `cinema/review/controller.py` | Gate orchestrator's mutation sequencing / audit accrual untested (rules are) |
| `cinema/checkpoint` restore path | `cinema/checkpoint.py` | Missing-asset / state-loss reconstruction on resume untested (save path is tested) |

---

## 5. Suggested sequencing

1. **Finding #0** — land `pytest-cov` (advisory CI) so the rest is measured.
2. **Tier 1 batch A** — a regression test locking the `api_serve_file` containment
   guard (`api_export` has no user-controlled path) — security-adjacent, no external deps.
3. **Tier 1 batch B** — destructive + state-machine endpoints
   (`api_delete_project`, `api_pause`/`resume`, `api_restart_shot`).
4. **Tier 1 batch C** — generation/approval gate endpoints.
5. **Tier 2** — gate boundaries & provider failure modes.
6. **Tier 3** — audio DSP + orchestration mutation contracts.

Per the repo's R-VERIFY-TIER convention, any defect surfaced while writing these
that won't be fixed in the same session should ship a
`pytest.mark.xfail(strict=True, reason=...)` pin so CI re-verifies it.

---

*Last verified: 2026-06-14 against the working tree on
`claude/test-coverage-analysis-v596bc`. Counts and file:line refs are
hand-verified via the cited grep/wc commands; they are not a line-coverage
measurement (§2). If line numbers drift, re-run the §4 greps before relying on
them.*
