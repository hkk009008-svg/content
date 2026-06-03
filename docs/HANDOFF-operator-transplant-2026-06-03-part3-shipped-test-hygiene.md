# Operator Transplant Handoff — 2026-06-03 (Part-3 HIGH shipped + Lane-V-clean · test-hygiene done · next = moderates + Parts 4/5)

*Last verified: 2026-06-03T04:07Z. Branch `feat/max-tier-provisioning` @ `25d9634` (director
Lane V commit; +1 for this handoff commit). **Origin at `26c8f82`, branch ahead 1** —
pushing this handoff syncs origin (carries the director's `25d9634` Lane V event too). Full
unit suite **1499 passed / 3 skipped / 0 failed** (+10 subtests); §15 smoke `OK`; doc anchors
clean. Pod `07ed667` proxy → **HTTP 404** (at session start; likely stopped/not billing —
re-confirm in Novita console). This handoff SUPERSEDES
`HANDOFF-operator-transplant-2026-06-03-dialogue-shipped-and-plan2-done.md` — its OPEN item #1
(Part-3 fixes) is DONE for the HIGH findings; moderates/minors remain (below).*

## ★ READ FIRST — what this session shipped (all on origin except `25d9634`)

1. **Housekeeping** — SUPIR bake committed (`74fe3c2`, anti-over-restoration tuning, *unvalidated-on-pod* caveat in body) + gitignore hygiene `9bcaab7` (`logs/` + `.claude/launch.json`).
2. **P0 production crash FIXED** (`f5fd4e7`) — `_voice_mode` `UnboundLocalError` crashed **every non-AUTO shot** (the normal prod case per `scene_decomposer:420`); `controller.py` bound it inside `if raw_api=="AUTO"` but used it unconditionally at `:1396`. Director's Lane V found it; user adjudicated operator-owns-as-slice-0. Fixed via the 1-line hoist + **2 real-`generate_motion_take` regression tests** (the coverage that was missing).
3. **Part-3 quality-gate fixes (the 3 HIGH Plan-2 findings) SHIPPED** (`38064f9..20673a6`, 7 commits) — design-first (spec `docs/superpowers/specs/2026-06-03-part3-quality-gate-fixes-design.md`, plan `docs/superpowers/plans/2026-06-03-part3-quality-gate-fixes.md`, both reviewed; **director-concurred**), executed via subagent-driven dev (TDD + 2-stage review per task), opus final cross-cutting review = **ready-to-ship**:
   - **F1** silent-pass-on-missing-file → missing *generated* output **FAILs** (`GENERATED_IMAGE_MISSING`); missing *reference* / no-config / all-refs-fail → honest **SKIP** (`passed=True, skipped=True, overall_score=None`). Same policy on the DeepFace path AND the vision-fallback path. Dead `_no_file_result` removed.
   - **F2** landscape → SKIP (was a spurious identity fail).
   - **F3** `style_director` back-fills `photorealism_rules` so the formula can't silently vanish from prompts.
   - Schema (`identity/types.py`): `overall_score → Optional[float]` + `skipped: bool`. **All 8 production `.overall_score` readers guarded** for `None` (the #1 risk). The T2 review caught a *2nd* crash site the spec-audit missed (`chief_director:510`, closed `f7979a5`).
4. **Test-hygiene** (`26c8f82`, director directed-sequence item 3) — replaced the **9 inline-sim tests** (the routing inline-sim is *why P0 shipped green*) with real-code coverage: 6 deleted (each citing the real test that covers it), 3 converted to real `generate_motion_take` calls. Audited: **no coverage lost** — the deleted `test_pinned_target_api_is_not_overridden` was a pure inline copy (`target_api = raw_api; assert ...`), testing nothing real.

**Director's independent Lane V (Rule #9) on the Part-3 range = ✅ SHIP-CLEAN** (`25d9634`,
event `coordination/mailbox/sent/2026-06-03T03-58-00Z-director-to-operator-verification-report.md`):
full spec compliance, exhaustive None-safety incl. transitive flows, 3-path consistency,
history-integrity, concurrency — all verified. **Part-3 cleared for the merge-to-main decision.**

## Where we are in the Test/Audit program (spec `docs/superpowers/specs/2026-06-02-program-test-audit-plan-design.md`)

| Part | What | Status |
|---|---|---|
| Part 1 | Capability ledger | done (prior sessions) |
| Part 2 | Prune list | identified; prune PRs pending (Part 5 Phase B) |
| **Part 3** | **Fix list** | **HIGH subset (F1/F2/F3) DONE this session**; moderates/minors deferred (below) |
| Part 4 | UI dimension (scorecard / per-shot scores / provenance) | NOT started |
| Part 5 | Execution sequencing | Phase A (zero-test characterization) DONE; Phases B/C/D pending |

The 6 zero-test blind-spots (Part-1) are now characterized (Plan-2, prior session): `identity/validator`, `style_director`, `sora_native`, `ltx_native`, `phase_c_vision`, `hedra_native`.

## NEXT — continue testing (priority order)

1. **Deferred Part-3 moderates/minors — the `# CANDIDATE BUG` markers.** `grep -rn "CANDIDATE BUG" tests/unit/` → **20 markers across 5 files** (`test_sora_native.py`, `test_ltx_native.py`, `test_phase_c_vision.py`, `test_identity_validator.py`, `test_style_director.py`). These are the durable, in-test record of the remaining findings. The MODERATES (from the Part-3 spec §8): `sora_native` ignores `resolution` (hardcoded 1280×720) · `phase_c_vision` face-swap silent `None` on returncode-0 + missing-output · hardcoded `0.7` vision threshold (vs configurable DeepFace path) · `validate_video(threshold=0.0)` divergence · `style_director` web-research fires regardless of `use_web_research` · `ltx_native` `"720p"`→1080p + `HTTPError`→no-fallback. MINORS: `sora_native` `EnvironmentError` on empty key + dead `download_url` · `identity` `MULTIPLE_FACES_AMBIGUOUS` dead enum · `style_director` openai client built outside the `try`. **These are behavior changes → design-first (brainstorm→spec→plan→subagent-driven implement), exactly like the Part-3 HIGH cycle this session.** The characterization tests already pin current behavior; flip each `# CANDIDATE BUG` to assert-fixed as part of its fix.
2. **+ 2 non-blocking nits from the director's Lane V** (fold into the moderate cycle, Rule #15 option c): (a) `identity/validator.py` `_vision_llm_validate_video` total_frames==0 returns inline `passed=False/0.0` not via `_missing_output_result` / no `failure_reason` (pre-existing; behavior correct — cosmetic consistency); (b) `llm/chief_director.py:341` stale `identity_score: float = 0.0` annotation (runtime can be `Optional[float]` now).
3. **Part 4 — UI surfacing** (spec §Part 4): U1 capability scorecard, U2 per-shot scores, U8 provenance — reuse data already in `take.metadata` / `pipeline_status.toml`.
4. **Part 5 Phase B/C** — re-verify the Part-2 prune list at HEAD (re-grep incl. tests/dynamic refs) → prune PRs; audit the Part-3 no-ops (confirm each dead/partial) → tickets.
5. **Live wired-E2E of the dialogue route** (~$0.50-1, spend-gated) — prove the shipped Veo+overlay wiring end-to-end. Separate from testing; user's spend call.

## Key gotchas / how-to (testing discipline)

- **Characterization-test discipline:** survey the component FIRST (read the real code; the survey can be WRONG — several were corrected mid-session by reading source); write tests that assert the **actual** behavior, mark quirks `# CANDIDATE BUG`. A test FAIL = a real bug → ticket; never weaken a test to make it pass.
- **TDD per fix:** flip the `# CANDIDATE BUG` test to assert the fixed behavior, watch it FAIL against current code, implement, watch it PASS. The two-stage review (spec then code-quality) earns its keep — it caught the `chief_director:510` 2nd crash site this session.
- **`Optional`-widening blast radius:** when a field/return type gains `None`, `grep -rn '\.<field>'` ALL production readers and guard each — `float(None)` / `None >= x` / `:.2f` all crash. (Part-3's whole T2 task.)
- **Frozen settings:** `config/settings.py` is `@dataclass(frozen=True)` — can't monkeypatch fields. Use `dataclasses.replace(...)` + `monkeypatch.setattr(<module>, "settings", new)`, or set instance attrs.
- **`sys.modules` stub shadowing:** some test files inject empty `ModuleType` stubs (`sora_native`, `ltx_native`); a new test importing the REAL module needs `sys.modules.pop("<mod>", None)` first.
- **Anchor drift:** line-shifting edits can break `check_doc_claims` line-anchors → `ci_smoke` exits 1 (`def_drift`). Run `.venv/bin/python scripts/check_doc_claims.py --fix`, confirm `OK`, commit the repair in the same pathspec. **Run ci_smoke BEFORE committing.**
- **Pathspec commits (shared index / D-a):** `git commit -m "..." -- <paths>` (NOT bare / `git add -A`) — an **intentional uncommitted state** is NOT present right now (working tree clean except untracked `scripts/_*` scratch, gitignored output). Keep it that way: pathspec only. Footgun: put `-m` BEFORE `--`.
- **Subagent-driven execution:** for a plan with ≥5 tasks, orchestrate (don't implement in main) — fresh implementer per task + 2-stage review. Lane-match: trivial foundational/verification tasks in main (Lane A), multi-site/judgment tasks to subagents (Lane B). This session: T1/T7 Lane A, T2-T6 Lane B.

## Coordination state

- **Director: freshly active** (committed `25d9634` Lane V at ~04:05Z; their presence file is ~2h stale = Rule #19 current_task-rot — trust git, not their stale `current_task`). They cleared Part-3 for merge.
- **Mailbox** (`coordination/mailbox/sent/`): this session operator→director sent `02-12-02Z` (P0 dispatch-claim), `02-18-00Z` (P0 closure), `03-10-32Z` (Part-3 completion); director→operator `01-57-16Z` (the P0+inline-sim directive — historical) and `03-58-00Z` (Lane V SHIP-CLEAN). Cursor/processing current.
- **Merge-to-main** is a director + user decision (Part-3 is Lane-V-cleared; the branch also carries the broader max-tier line + dialogue wire + SUPIR bake — not a clean single-feature merge). Don't merge unilaterally.
- **Branch ahead 1 of origin** = the director's `25d9634` (unpushed by them); this handoff's push carries it to origin.

## Verification at write (ADR-013)
```
$ git rev-parse --short HEAD            → 25d9634   (+1 for this handoff)
$ git status -sb | head -1              → ...feat/max-tier-provisioning [ahead 1]
$ .venv/bin/python -m pytest tests/unit/ -q   → 1499 passed, 3 skipped, 2 warnings, 10 subtests
$ .venv/bin/python scripts/ci_smoke.py        → OK
$ .venv/bin/python scripts/check_doc_claims.py → All anchors checked — no drift.
$ grep -rcn "CANDIDATE BUG" tests/unit/ | <5 files>  → 20 markers (the deferred moderates/minors)
$ curl .../07ed667.../system_stats     → HTTP 404 (session start; re-confirm pod stopped)
```
