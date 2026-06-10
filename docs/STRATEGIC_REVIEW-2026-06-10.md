# Strategic Review — 2026-06-10

**Author:** Director seat, end of the cycle the 2026-05-24 review demanded
("After 6 sessions: re-assess against this strategic review").
**Audience:** Both seats + future directors.
**Status:** Active. Supersedes [STRATEGIC_REVIEW-2026-05-24.md](STRATEGIC_REVIEW-2026-05-24.md)
as the current leadership direction; the predecessor stays as the historical
record per its own instructions.
**Method:** Every 05-24 priority was audited against HEAD (`2ccb2a4` era,
2026-06-10) by a 9-lane parallel evidence audit (`wf_5ef8e23c-85b`), each claim
command-backed; the 10th lane (capability gaps) was completed by hand. Where
this document states a number, the producing command ran this cycle.

---

## Executive verdict

The 05-24 verdict was "structurally sound but operationally immature." That
program **worked**: seventeen days later, most of what it pointed at landed —
the unit suite grew 478 → **1,974 collected** (88 files, 4.1×), structured
JSON logging covers the orchestrator spine, error boundaries wrap all four UI
shells, auto-approve cut per-project operator decisions from 60–80 to **20–40**,
both cascades surface engine/fallback metadata, Pydantic boundary validation
exists, and a doc-claim verifier (1,615 LOC, 122 tests) + the two-seat cold
Lane-V institution exceed what P1-5 asked for. In the same window the program
shipped **capability** the predecessor never mentioned: portrait 9:16
end-to-end, the pod-validated max-tier image chain, the dialogue/talking-head
routes, multi-character identity validation, a capability scorecard with its
own console.

The new risks are different in kind, and the worst one is epistemic:

1. **Trust infrastructure that looks green but isn't.** The CI pytest job has
   **never passed — 0 successes in 289 runs since 2026-05-24** — so the repo's
   only automated test gate provided zero signal across the entire window in
   which the suite quadrupled. Local discipline (R-START smoke, `python -m
   pytest` by hand, Lane V) masked it completely. Same family: the ungated
   PROGRAM-MANUAL re-drifted to 83 def-drift anchors within ~2 days of its
   last full sweep; the SSE bridge silently drops event fields producers
   already emit.
2. **Capability asymmetries.** Identity *validation* is now
   multi-character; identity *generation* still anchors on exactly one
   character — a second character in frame gets no identity conditioning at
   all and is only caught after the fact. New-face max-tier talking heads
   over-cook (user verdict: "acceptable for general use, not max tier") and
   the LoRA training path that would fix identity-vs-realism is blocked on
   local-CUDA assumptions.
3. **The monoliths grew.** `cinema_pipeline.py` 1,011 → 1,669 LOC (+65%),
   `web_server.py` 1,697 → 2,664 (+57%). The extraction the predecessor
   called "not urgent" is now the place new inline methods accumulate by
   default.

Direction for the next cycle: **make the green trustworthy, then close the
generation-side identity gap** — that is the highest-leverage lever for the
program's stated intent (script → finished photoreal cinematic video, operated
at full capability).

---

## The 05-24 ledger, audited

Every priority from the predecessor, with verified status. Evidence commands
ran at HEAD this cycle; the fuller per-item evidence lives in the audit run
(`wf_5ef8e23c-85b`).

| 05-24 item | Status | What actually happened |
|---|---|---|
| **P0-1** test gaps (5 modules) | **LANDED** (2 tails open) | ReviewController: 39 tests incl. all four named symbols. workflow_selector: 113 tests incl. full keyword sweep. face_validator_gate: 24 + 22 tests. cost_tracker `record_api_call` + budget gate: directly tested (69 tests). The 3 skipped persistence tests un-skipped (`1fcaaaa`). Tails: `lip_sync._sync_gate_settings` still has zero direct tests; `_coerce_to_valid_keys` covered only indirectly — and it lives in `llm/prompt_optimizer.py`, not `domain/scene_decomposer.py` as 05-24 claimed (misattribution, true even then). |
| **P0-2** CI | **PARTIAL — and the part that matters is broken** | `.github/workflows/ci.yml` landed the same day (smoke + pytest + tsc). Smoke and tsc jobs pass. The pytest job is 0-for-289 (see New Findings NF-1). |
| **P0-3** cost-tracking fragility | **LANDED** | All 11 production `record_api_call` sites use explicit `except Exception → logger.warning`/printed skip-notes; the AttributeError root cause fixed at source (cost_tracker is a real property proxying PipelineCore). Single-line silent-excepts: still exactly 2, both in a test teardown — unchanged since baseline. (Honest wider number: 33 multi-line `except:\n pass` blocks repo-wide, most documented best-effort; a handful uncommented — see P2-5.) |
| **P1-1** observability | **PARTIAL** | `cinema/logging_config.py` JSON formatter landed; the three named modules converted (36/22/3 logger calls; 0–2 residual prints each). Correlation IDs superseded by `shot_id`/`scene_id` extras (documented as the primary log-query filter) — but there is no per-run ID. Repo-wide: **51 of 99** production files still `print()` (565 occurrences); `phase_c_ffmpeg.py` (79) and `lip_sync.py` (62) — the two heaviest pipeline surfaces — are print-only. Per-shot **timing** metrics: nowhere. The live SSE event still says "Generating motion for {shot_id}" with no engine field — the exact 05-24 complaint (see NF-3). |
| **P1-2** orchestrator monolith | **REGRESSED** | 1,011 → 1,669 LOC, 76 → 92 defs; the `assembly/` package (final_assembler + scene_audio) was never created; `_assemble_final` (~330 LOC), `_ensure_scene_audio`, `_ensure_bgm`, `generate()` (255 LOC) all still inline. Correction to the predecessor: `_rebuild_review_clips` was already a 2-line delegate on 05-24 — that bullet was stale on day one. Extraction did continue *around* the file (screening.py 684, auto_approve.py 762, capability_scorecard.py 268, aspect.py, fal_limits.py, logging_config.py, audio/foley.py). `web_server.py` grew faster: 1,697 → 2,664. |
| **P1-3** schema validation | **PARTIAL** | `domain/models.py` (Pydantic v2: Project/Scene/Shot/Take/Character/Location/CascadeMetadata/DirectorialIntent) landed same-day. But: warn-only by default (`CINEMA_STRICT_SCHEMA=1` escalation exists and is set nowhere); `mutate_project` — the primary write path — bypasses validation (migrated callers validate per the documented Variant-1 pattern instead); no GlobalSettings model; raw dicts remain the in-flight data currency. The "TS generated from Pydantic" vision: not started. |
| **P1-4** FE error boundaries | **LANDED** (same-day, `d516d2a`) | One shared 43-LOC ErrorBoundary wraps all FOUR shell routes (the 05-24 ask listed three; CapabilityConsole came later and is wrapped too). Only ProjectSelector is unwrapped. |
| **P1-5** doc-claim tooling | **PARTIAL + SUPERSEDED, net better** | Tool 1 shipped as `scripts/check_doc_claims.py` (1,615 LOC, 122 tests; line/range/SHA-ref anchors, `--fix`, def-aware binding + `--list-unbound` as of `2b2da60`), CI-wired via ci_smoke — though anchors hard-fail only locally (CI = warn) and the default gate covers ARCHITECTURE.md only. The literal inventory-pattern lint ("N test files" vs `ls | wc -l`) was never built — that claim class is still process-gated (ADR-013/R-EVIDENCE). Tool 2 (closing-verification subagent) was institutionally absorbed by the two-seat cold Lane-V process: 64 verification-report events in the mailbox, most recent one independently re-enumerating a 22/22 completeness claim and re-running the suite. |
| **P2-1** competitive_generation 2× cost | **NOT_DONE** | Still `True` everywhere, zero coupling to quality_tier, and the string "competitive" appears nowhere in `web/src` — invisible exactly as before. |
| **P2-2** pod idle guardrails | **NOT_DONE** (+ provider moved) | No pod endpoint/auto-stop exists (`grep -n pod web_server.py` → nothing). The risk realized live: the 06-09 session left the metered pod up overnight, needing manual console termination. Provider is now **Novita**, not RunPod — the client class name (`RunPodComfyUI`) and OPERATIONS §5 title are stale, and a sleep endpoint would target Novita's API. |
| **P2-3** cascade visibility | **LANDED** (one FE gap) | Video: `_record_video_cascade` writes `{engine, attempts}` at 11 success sites → `take.cascade_metadata` → CascadeBadge/TakeStrip/Monitor render "via {engine}" + ⚠ FALLBACK. Lipsync: both cascades write the full prescribed shape `{engine, score, threshold, fallback, attempts}` including the best-of-failed path. Gap: the in-pipeline dialogue lipsync writes `take.metadata.lipsync_cascade`, which **no FE file reads** — the fallback badge never shows on the most common lipsync path (NF-4). |
| **P3-1** concurrency hygiene | **LANDED** | All four mutable web_server globals locked (`_pipelines_lock` guards the two 05-24 named ones); remaining lock-free accesses are single-op reads; audit doc exists. |
| **P3-2** `_default_progress` | **LANDED** (repurpose branch) | Converted to `logger.debug` with context preserved; live no-callback callers exist (run_cinema_pipeline `__main__`, headless). Close it. |
| **P3-3** scene_decomposer duplicate validators | **NOT_DONE** (reframed) | The real issue: two near-identical inline "Validate and enrich" sanitizer loops in `decompose_scene` / `competitive_decompose_scene` — currently byte-identical in coercion logic, still duplicated (drift risk). Drop the `_coerce_to_valid_keys` framing (wrong module attribution). |
| **P3-4** unclear root files | **LANDED** | `reporter.py` + `generate_characters.py` pruned (ADR-020); the other five confirmed load-bearing, documented with importers in ARCHITECTURE.md. |
| **P4-1** vendor sprawl | **UNCHANGED** | Same counting method → still ~22 surfaces (Mistral fully gone; RunPod→Novita 1:1; Pollinations now an explicit $0 line). The ≤10 minimum-viable-set product question was never actioned. |
| **P4-2** single-operator architecture | **UNCHANGED** (by choice) | Still single-process; no demand signal changed. Needs only the README statement. |
| **P4-3** review fatigue | **LANDED** (option A + a reversal UI; B superseded) | `cinema/auto_approve.py` (762 LOC, 74 tests, same-day ship): veto-list architecture, conservative-on; PLAN/IMAGE auto-advance, MOTION opt-in (ADR-014), FINAL forces ≥1 human decision per shot by default. Decisions: 60–80 → floor 20, typical 20–40. Bulk-approve was never built — replaced by per-shot reversal (RejectAutoApproveModal + audit trail + PostRunSummary). |
| **P4-4** experiment tracking | **NOT_DONE** (per its own guidance) | Only naming residue (`experiments_db_path` holds just the cost_log table). Still correct to defer — see P4 below. |
| **P4-5** DirectorsConsole | **Answered by adjacency** | Kept, error-bounded, functional (6 live regions) — but zero direct commits since 05-23; all console/ investment went to other shells. Meanwhile a FOURTH shell appeared: CapabilityConsole (408 LOC, 06-06). The "three shells" framing is stale. |

Scorecard: of the 19 items, **9 landed, 5 partial, 4 not done, 1 regressed** —
and three of the "not done" were explicitly deferred-by-design. As a
leadership artifact the 05-24 review earned its keep. Its two factual errors
(test-module misattribution; `_rebuild_review_clips` already extracted) are
corrected above, in the spirit of its own ADR-013 origin story.

---

## What landed that 05-24 never imagined (capability ledger)

The predecessor was an operational-maturity document; the program intent
(PROGRAM-MANUAL §1–2, §5) is capability. Landed since, all verified at HEAD:

- **Portrait 9:16 end-to-end, un-gated** — `SUPPORTED_ASPECT_RATIOS = ["16:9",
  "9:16"]`; aspect-aware image keyframes (prod ComfyUI dims, FAL sizes,
  Pollinations, max-tier `_inject_aspect` incl. 2160×3840 master); 8-engine
  `PORTRAIT_CAPABLE` cascade filter + pre-dispatch guard + `_accept_or_reject`
  post-gen backstop at every provider accept site + lip-sync orientation
  fences on both engine families. Landscape byte-identity preserved.
- **Max-tier image chain pod-validated** — hires-fix node 18 fires on the real
  pod (denoise floor 0.40: 0.25 pod-proven disintegration, arc 0.48 vs 0.83);
  SUPIR cfg 2.8 settled by a clean same-base A/B; floors enforced in the
  overlay schema AND the FE (slider min, preset values aligned).
- **Dialogue + talking-head routes** — `dialogue_voice_mode` (overlay default:
  Veo silent video + per-shot TTS + mandatory lipsync overlay pass) and
  `lip_sync_mode=generation` (Hedra-direct / Omnihuman / Aurora with
  best-of-failed + orientation fencing). Delivered artifacts: 21s and 30s
  vertical talking heads (06-09).
- **Multi-character identity validation** — `_validate_take_identity` now
  validates every character in frame with per-character metadata
  (`identity_per_char`, `identity_all_matched`); ref-less extras can't
  false-fail.
- **FAL timeout hardening** — all 22 production `fal_client.subscribe` sites
  bounded via `cinema/fal_limits.py` (600s video / 1,800s talking-head /
  180s image), AST-guarded so a new unbounded site fails the suite; the
  talking-head class exists because an adversarial review proved 600s would
  *cancel* legitimately progressing long-form jobs (~40× realtime measured).
- **Capability scorecard + console** — per-dimension measured-vs-bar rollup
  (identity/coherence/motion/lipsync), cascade routing counters, gate rollup,
  LoRA status, conformance block; served at `/api/.../capability-scorecard`,
  rendered by the CapabilityConsole shell.
- **Process capability** — the two-seat director/operator concurrent
  operation matured into a working institution this window: 64 cold
  verification reports, same-session cross-review of every substantive
  commit, and a doc-verifier that both seats extend. This is the program's
  de-facto QA organ and it caught real defects this cycle (FE slider
  exposure, wrong schema-table name, missed anchor, AST-guard dodges).

---

## New findings (this audit, previously unknown or unquantified)

**NF-1 — The CI pytest job has never been green: 0 successes in 289 runs.**
It dies at *collection* with `ModuleNotFoundError: No module named
'cost_tracker'`: CI runs bare `pytest tests/unit/`, there is no
pytest path config anywhere (no pytest.ini/setup.cfg/tox.ini section, no root
conftest.py), and `tests/conftest.py` adds the repo root to `sys.path` inside
an **autouse fixture** — which runs after collection, too late. Locally
everyone runs `.venv/bin/python -m pytest`, which masks the gap by putting CWD
on `sys.path`. The first run on 2026-05-24 already failed; nobody noticed for
17 days because local discipline kept the tree green independently. Bonus
deadline: GitHub forces Node 24 for actions on **2026-06-16**; the workflow's
checkout@v4/setup-python@v5 emit deprecation warnings on every run.
*Evidence:* `gh api '...actions/runs?status=success...' --jq .total_count → 0`
(total 289, 240 failures); `gh run view <id> --log-failed` → collection error;
absence of path config verified by `ls`/`grep`.

**NF-2 — Budget gate zero-coercion defect (live bug).** `make_project()`
defaults `budget_limit_usd: 0`; the UI documents "0 = unlimited"; auto-approve
honors that. But `cinema/core.py` only None-guards, and
`CostTracker.is_over_budget()` returns `spent_usd > 0.0` once budget is the
float 0.0 — so a default-settings project **pauses with BUDGET_EXCEEDED after
its first motion-take cost record**. Reproduced:
`CostTracker(db_path=':memory:', budget_usd=0.0)` + one `record_api_call` →
`is_over_budget() → True`. One-line fix (coerce falsy→None) + a regression
test.

**NF-3 — The SSE bridge silently drops fields producers already emit.**
`web_services.py make_progress_callback` whitelists 16 named fields and
discards `**kwargs` — so `performance_engine="SKIP"` and the
`spent=`/`budget=` amounts on BUDGET_EXCEEDED never reach the UI today, and
the cheapest path to "show which engine is being tried" (P1-1b, still the
operator's #1 blindness during 8-minute motion waits) is blocked by one
function.

**NF-4 — Lipsync fallback badge never shows on the main path.** The
in-pipeline dialogue lipsync persists its cascade record to
`take.metadata.lipsync_cascade`; no file under `web/src` reads that key (the
UI reads only `take.cascade_metadata`, which on dialogue takes holds the
*video* cascade record). Captured data, half-wired surfacing.

**NF-5 — The ungated manual re-drifts in days.** `check_doc_claims` on
`docs/PROGRAM-MANUAL.md` at HEAD: **83 def-drift anchors** (67 real re-drift
accumulated in ~2 days of code churn since the 06-08 "fully anchor-clean"
sweep + 16 newly visible via def-aware binding), vs ARCHITECTURE.md: 0 (it's
in the default gate). Plus 67+335 bounds-only (unbound) anchors now
quantified by `--list-unbound`. Structural conclusion: **anchor hygiene decays
at the rate of code churn; only gated docs stay true.**

**NF-6 — Identity generation/validation asymmetry** (promoted to P1-1 below).
`get_primary_character` returns `characters_in_frame[0]`; keyframe generation
passes a single `character_image=primary_ref`; LoRA selection and the
performance face_anchor use the same first-character convention. A second
character in frame receives no identity conditioning at generation time —
drift is only *detected* (now), never *prevented*. `pipeline_status.toml`
still carries `multi_identity_validation: stubbed` for the unrelated
zero-caller helper; the wired path is the controller's.

**NF-7 — Dead FAL-Hedra attempt in driving_video.** `lip_sync.py` records
`fal-ai/hedra/character-3` as HTTP-404-dead (routes direct to api.hedra.com
instead), but `performance/driving_video.py` still tries that FAL endpoint as
attempt 1 before its direct-REST fallback — a guaranteed-failed first attempt
on every Hedra driving-video call. Small, but it wastes a timeout window.

---

## What needs to change — prioritized

### P0 — Trust the green (ship-blocking for *decisions*, not for video)

**P0-1 — Make CI actually test.** Add the missing path config (root
`conftest.py` or `[tool.pytest.ini_options] pythonpath = ["."]`), or switch
the job to `python -m pytest`; bump the deprecated actions before the
2026-06-16 Node-24 forcing. Acceptance: a green pytest job on a push where
the suite is locally green, and a RED one on an intentionally broken PR.
Half a session, including watching one live run each way.

**P0-2 — Fix the budget-gate zero-coercion defect** (NF-2). One line +
regression test. Fold the `would_exceed` question in while there: it has zero
production callers — either wire it as the pre-spend check at the same
chokepoint or delete it (don't keep a documented-but-dead safety API).

### P1 — Capability frontier (the program intent)

**P1-1 — Multi-character identity at GENERATION time** (NF-6). The validator
now catches second-character drift; nothing prevents it. Design-first — the
candidate mechanisms differ in cost and pod-dependence: (a) multi-image
Kontext keyframes (FAL `kontext/max/multi` already takes multiple refs — the
plumbing exists at the image fallback tier), (b) per-character LoRA stacking
on the production tier (the established realism+identity formula), (c)
regional PuLID/attention masking on the max tier (pod work, highest fidelity
ceiling). Recommend: spec first (one session), implement (b) first where LoRAs
exist, treat (c) as the max-tier follow-up. This is the single biggest gap
between "what the scorecard measures" and "what generation can deliver" for
multi-character cinema.

**P1-2 — New-character onboarding to max-tier quality.** Two coupled blocks:
the no-PuLID max-tier over-cook (chain co-tuned for a PuLID base; fresh faces
come out painterly — user verdict 06-09) and LoRA training being a LOCAL
CUDA subprocess (`prep/lora_training.py` shells out to ai-toolkit/kohya;
not installed, no CUDA on this Mac, ≥15-ref gate vs 1 registered ref for the
test character). Direction: a pod-side training path (the pod has the VRAM;
the trainer is a subprocess wrapper away from being remote) OR a documented
"new character" flow that first mints a max-tier-quality canonical via the
existing photoreal-reference route. Pod-gated; needs a user spend decision
before the spike session.

**P1-3 — Observability last-mile** (NF-3 + NF-4 + the engine-blindness
complaint that has now survived two reviews). Lift the SSE whitelist (pass
through or explicitly add `engine`, `spent`, `budget`), emit the engine on the
MOTION event, render `metadata.lipsync_cascade` in the take UI. One session,
mostly FE; this closes P1-1b's user-visible half without the repo-wide
logging conversion.

### P2 — Operational

**P2-1 — Convert the two heaviest print-only files** (`phase_c_ffmpeg.py` 79
prints, `lip_sync.py` 62) to the existing JSON logger with `shot_id`/`engine`
extras. The spine conversion proved the pattern; these two files are where
stuck-shot debugging actually happens.

**P2-2 — Gate or schedule the manual's anchors** (NF-5). Options: add
PROGRAM-MANUAL.md to the ci_smoke anchor gate as WARN (cheap, immediate
visibility) and run `--fix` on a cadence; or accept decay and say so in the
manual's header. Operator lane (they own the verifier); my recommendation is
warn-in-smoke + fix-on-touch.

**P2-3 — Pod idle guardrail, Novita edition.** The 05-24 proposal assumed
RunPod's API; the provider moved. Minimal worthwhile shape: a `pod-status`
indicator in the UI (gateway 502 = down, cheap probe) + an OPERATIONS.md
checklist line in the session-wrap ritual; the auto-sleep endpoint is only
worth building if pod sessions become routine again. Also rename
`RunPodComfyUI` → provider-neutral in the next touch (cosmetic, ADR-013
same-touch rule).

**P2-4 — competitive_generation: decide it this cycle.** Two reviews have now
flagged the invisible 2× LLM default. Option C (tier-coupled default) remains
right; it is a ~10-line change plus a UI note. If the decision is "keep True
always," record THAT as an ADR instead — either way, stop carrying it open.

**P2-5 — Silent-failure honesty pass.** The headline "2 silent excepts" is
true only for the single-line pattern; 33 multi-line `except:\n pass` blocks
exist, a handful uncommented (`phase_c_assembly.py:474`, `lip_sync.py:427`,
`identity/validator.py:514` at audit time). One audit session: comment the
intentional ones (the established best-effort convention), fix or log the
rest. Also retire NF-7's dead FAL-Hedra attempt while in `driving_video.py`.

### P3 — Code health

**P3-1 — Resume the extraction, with a ratchet.** The 05-24 "not urgent" call
aged badly (+658/+967 LOC). Do the original `assembly/` extraction
(`_assemble_final` + loudnorm/concat helpers; `_ensure_scene_audio`/`_ensure_bgm`
→ `audio/` orchestration), and add the ratchet: **no new inline method on
`CinemaPipeline` or new route-handler body >50 LOC in `web_server.py` without
a written justification** — the growth came from defaulting into the
monolith, not from any single decision.

**P3-2 — Unify the scene_decomposer sanitizer loops** (still in sync today —
unify before they aren't).

**P3-3 — Strict-schema pilot.** `CINEMA_STRICT_SCHEMA=1` exists and is set
nowhere; turn it on in CI (once CI tests — P0-1) and in the dev environment,
add the missing GlobalSettings model, and route `mutate_project` through
validation. Stop carrying a warn-only layer that nobody escalates.

### P4 — Product questions (carried, with updated framing)

- **Vendor set (~22, unchanged):** the cascade keeps absorbing vendor risk and
  the adapters are built; the cost is now mostly cognitive + credential
  hygiene. Re-pose the ≤10 question only if a billing or deprecation event
  forces it; otherwise accept the sprawl as the price of the cascade's
  resilience and close the item.
- **Single-operator:** unchanged; write the one README paragraph and close.
- **Experiment tracking:** still defer — but the capability scorecard now
  exists and is the natural substrate (it already aggregates per-dimension
  scores per shot); when operator volume justifies it, build ratings INTO the
  scorecard rather than a parallel SQLite layer.
- **DirectorsConsole:** the de-facto answer was "keep, don't invest." Make it
  official (one ADR line) or fold its regions into PipelineLayout; carrying an
  un-decided shell for another cycle is the only wrong option. Note the shell
  count is four now (CapabilityConsole earned its place by being the
  capability program's instrument panel).

---

## Roadmap (next 6 sessions)

| Session | Focus | Deliverable |
|---|---|---|
| 1 | **P0-1 + P0-2** | CI pytest green (verified both directions) + actions bumped; budget zero-coercion fixed + tested; `would_exceed` wired-or-deleted. |
| 2 | **P1-3** | SSE whitelist lifted; engine on MOTION events; lipsync_cascade rendered; spent/budget visible on BUDGET_EXCEEDED. |
| 3 | **P1-1 spec** | Multi-char generation-identity design doc (mechanisms a/b/c costed, pod-dependence explicit) → reviewed → implementation plan. |
| 4 | **P1-1 impl (first slice)** | Per the spec — likely LoRA-stacking on production tier for registered characters. |
| 5 | **P2-1 + P2-5 + NF-7** | phase_c_ffmpeg + lip_sync on the JSON logger; silent-except honesty pass; dead FAL-Hedra attempt removed. |
| 6 | **P3-1** | `assembly/` extraction + the monolith ratchet recorded; P2-4 decided as ADR. |

P1-2 (new-face max-tier / pod-side LoRA) schedules when the user green-lights
pod spend; it does not block sessions 1–6.

After 6 sessions: write `STRATEGIC_REVIEW-<date>.md` per the established
contract. Items still open then get re-prioritized or formally accepted as
not-doing.

---

## What I will NOT do (reaffirmed + updated)

- **Rewrite the orchestrator.** Still true — but the 05-24 corollary ("the
  remaining monolith is finishable in a couple sessions") is now a commitment
  (session 6), not a someday.
- **Microservices / multi-user / a real database.** Unchanged; no demand
  signal moved.
- **Replace ComfyUI.** Stronger now than on 05-24: the pod-validation culture
  (A/B on the live graph, floors derived from pod evidence) depends on the
  node graph being the workflow source code.
- **Aggressively unify the cascades.** Reaffirmed; the portrait work added
  per-cascade orientation fences that differ by family — the differences keep
  proving real.
- **Build experiment tracking now.** Reaffirmed, with the new note that the
  scorecard is its future home.
- **NEW: chase anchor-perfection in ungated docs.** NF-5 shows hand-sweeping
  an ungated 2,100-line manual buys days of cleanliness. Gate it (warn) or
  schedule it; don't hand-polish.

---

## How to use this document

Same contract as the predecessor: this is the leadership snapshot of
2026-06-10. Decisions land as ADRs in [DECISIONS.md](../DECISIONS.md);
the next director writes `STRATEGIC_REVIEW-<their-date>.md` rather than
editing this one. An item still sitting here untouched at the next review is
itself a finding.

One process note for whoever writes the successor: this review was produced
by a parallel evidence audit with command-backed findings (the predecessor's
ADR-013 lesson, mechanized). The 05-24 review shipped one inventory error it
had to correct in-place; this one inherited two of its claims as stale and
says so above. The pattern holds: **claims rot, commands don't** — audit the
ledger fresh before trusting any of it.

*Director seat, end of cycle.*
