# Tier F — Audit Re-execution (cycle-17 entry)

**Date:** 2026-05-28 · **Method:** blind read-only subagent re-audit (brief v2.0 §7.1),
every status grep/Read-verified with `file:line`; director spot-checked the 2 NEW gaps.
**Range audited:** cycle-17 HEAD (`d46a3e4`→`fd67f2e` during the run; findings are in
files orthogonal to that range's `llm/` + `auto_approve` changes, so unaffected).
**Baseline:** cycle-16 finding catalog in [CYCLE-16-CLOSING-REPORT-2026-05-27.md](CYCLE-16-CLOSING-REPORT-2026-05-27.md).

> **Brief-staleness flag:** §7.2 cites baseline SHA `a79c59` — it does **not resolve**
> as a commit. The real baseline is the closing-report catalog (cycle-16 reel-HEAD was
> ~`515e2ff`). §7.2's `a79c59` reference should be corrected to the closing report;
> left unfixed here (no confidently-verifiable replacement SHA — flag, don't guess).

## §1. Acceptance (brief §7.3) — MET

- ✅ Audit completed without crash.
- ✅ The 3 known-closed do **not** re-surface; the 7 known-open are correctly carried.
- ✅ **0 REGRESSED** — every cycle-16 closure held.
- ✅ Quality-debt trend recorded (§4); 2 NEW gaps filed as cycle-17+ candidates (§3).

The blind dispatch independently reproduced §7.2's expected delta (3 closed / 7 open)
without being fed it — so the expected delta is corroborated by cold re-verification.

## §2. Per-finding re-classification (10 baseline)

| ID | Status | Evidence |
|---|---|---|
| F-A.1/F-B.1 storyboard_mode | **OPEN** | `generate_storyboard` (`kling_native.py:310`) 0 callers; `storyboard_mode` only *written* `web_server.py:343`, read by no Python; UI exposes it (`ApiEnginesSection.tsx:15`) → inert toggle |
| F-A.2 LoRA validator | **OPEN** | `prep/lora_training.py:515-533` `validate_lora_quality` returns `LORA_VALIDATION_SKIPPED` (-1.0); docstring "STUB"; caller `:481` stores `None` |
| F-A.3 batch_optimize_scene | **OPEN** | `llm/prompt_optimizer.py:459` sole occurrence — 0 callers; per-shot path used at `cinema/shots/controller.py:391` |
| F-A.4 validate_multi_identity | **OPEN** | `domain/continuity_engine.py:118` defined; 0 real callers; wired path is single-char `validate_shot` (`:587`) |
| F-B.2 prompt_optimizer default | **CLOSED** | `domain/project_manager.py:338` `"prompt_optimizer_enabled": True`; read `controller.py:391` |
| F-B.3/F-C.2 hires_fix wire | **OPEN** | overlaid `quality_max.py:664` but `_inject_post_passes` (`:497`) never reads it; explicit NOTE `:728` "NOT injected" |
| F-D.1/MR-C0 FLUX_KONTEXT tracking | **CLOSED** | `domain/character_manager.py:328` `record_api_call("FLUX_KONTEXT", "multi_angle_ref")` inside the angle loop (`:297`) |
| F-F.1 lipsync cost tracking | **OPEN** | `lip_sync.py` 0 cost refs across 14+ paid FAL engines; reached prod `controller.py:1499` |
| F-F.2 LLM cost tracking | **OPEN** | `llm/chief_director.py`/`director.py` 0 cost refs; `ensemble.py:256-264` reads `usage` only to `print`, never `log_llm` |
| F-F.5 web_research log_llm | **CLOSED** | `web_research.py:172` (Phase-1) + `:212` (Phase-2) both logged |

## §3. NEW gaps (cycle-17+ candidates — director spot-check verified)

| Gap | Status | Evidence (verified) |
|---|---|---|
| **NEW-1: `camera_motion_native` inert toggle (UI lie)** | OPEN | written only `web_server.py:352`; surfaced in UI (`project.ts`, `ApiEnginesSection.tsx:36`); **read by no Python** (grep confirmed). Same shape as F-A.1 storyboard_mode. |
| **NEW-2: native motion modules have zero call-site cost tracking** | OPEN | `sora_native.py` / `veo_native.py` / `ltx_native.py` / `kling_native.py` each grep `0` for `record_api_call`/`CostTracker`/`log_*`. Cost recorded once generically at `controller.py:1045` on the winning-engine string. **Structural root of the cycle-16 cost-attribution advisories** (phantom Sora / Kling double-count, §5.6 / C-D-cost-1/2): per-provider spend is never recorded at the call site, only inferred. |

Cross-checked as *correctly wired* (NOT gaps): `face_consistency`, `char_lora_paths`,
`lipsync_engine_priority`, `dialogue_mode_enabled`, `lipsync_quality_validation`,
keyframe cost (`controller.py:547`).

## §4. Quality-debt trend

Net open **7 → 9** (10 baseline: 3 CLOSED / 7 OPEN; +2 NEW). The 3 closures were all
the *cheap* single-`record_api_call` cost wires; the *hard* OPEN items (real LoRA impl
~100 LoC, hires_fix node injection, storyboard wiring, batch-optimizer refactor) are
untouched, and a fresh pass found 2 more of the same two classes. **Read: not closing
faster than the surface reveals.** The dominant debt is one theme — **call-site
cost-attribution** (F-F.1 + F-F.2 + NEW-2): paid calls without call-site cost records.
That cluster is the highest-leverage cycle-17+ target.

## §5. Confidence + scope notes

- All 10 statuses + both NEW gaps are cold grep/Read-verified; high confidence.
- NEW-2's *exact* phantom-Sora mechanism is inferred from architecture (no call-site
  record → generic lookup), not runtime-replayed; the structural gap itself is verified.
- `cinema/auto_approve.py` + `cinema/review/controller.py` were operator's in-flight
  Phase-1 edits during the audit — deliberately **not** assessed (none of the 10
  findings nor the 2 NEW gaps are primarily sited there).
