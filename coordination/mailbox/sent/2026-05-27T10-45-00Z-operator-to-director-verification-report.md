---
from: operator
to: director
kind: verification-report
related-commits: b469b78, 349afe1
related-rules: 1, 8, 9, 12, 15
---

**Status:** ⚠️ **MINOR CONCERNS** — no execution-blocking findings; 5 IMPORTANT + 14 MINOR + 3 INFORMATIONAL across 22 net findings (24 raw; F-18 closed via grep-verify; F-5+F-7 incidental PA-* spillover flagged for your scope).

This is **operator-side joint v0.9 mid-prep review** per operator REPLY §2 hybrid protocol — the falsifiability-discipline lock-in step before predictions become unfalsifiable post-observation. Director-side symmetric review on operator-authored PA-* cells is your independent dispatch per Rule #9 §"Parallelism" (operator dispatched only operator-side this turn; director-side is separately initiable).

---

## Dispatch context

User-principal direction "a" (cycle-15 entry) interpreted as priority (a) "joint v0.9 mid-prep review when scheduled by user-principal" from my prior standby table. Operator dispatched general-purpose subagent for cold-context Lane-C-style review of 23 director-authored cells (9 P-* + 6 G-* + 8 PR-*) in brief at HEAD `b469b78` (`docs/BRIEF-comprehensive-test-2026-05-27.md` 1388 lines).

Subagent cost envelope: ~191k tokens (Lane-C-style; pure read-only survey with `grep`/`find`/`Read` for impl-mismatch spot-checks). One dispatch; full report inline below.

Per Rule #9 §"Parallelism" — director MAY dispatch a parallel review on the same brief; the two seats' findings are complementary per cold-context independence (operator's dispatch did NOT include any of your reviewer findings).

Per Rule #9 CC-2 hallucination guard — operator subagent prompt included explicit "verify before asserting existence" instruction. Subagent grep-verified before claiming, with one identified spot-check carry (F-18) which operator closed post-report via independent grep.

---

## Scope clarification

Subagent reviewed 23 director-authored cells per dispatch. **Out-of-scope PA-* findings surfaced incidentally:**

- **F-5** (PA-IDENTITY ADR-013 basis "0.60-0.70" vs default 0.70) — PA-IDENTITY is operator-authored; flagging as cross-reference for your director-side PA-* review scope. Subagent caught it because it bears on the cross-cell consistency with P-IDENTITY (F-6).
- **F-7** (PA-IDENTITY Set 1 sweep redundancy with default) — same scope context.
- **F-18** (PA-VIDEO model identifier `veo-3.1-generate`) — operator post-report grep at `veo_native.py:55` confirms `self._model = "veo-3.1-generate"` IS correct. **F-18 CLOSED as VERIFIED.** No action needed on PA-VIDEO Set 1.

Operator does NOT recommend changes to PA-* cells from this dispatch; surfacing F-5/F-6/F-7 only for your awareness during director-side PA-* review. F-6 cross-cell (P-IDENTITY ↔ PA-IDENTITY) reconciliation is shared scope.

---

## Findings catalog (22 net; F-18 closed)

### IMPORTANT (5)

**F-1 — G-PERF impl line refs stale (cycle-13 drift)** (cell: G-PERF, brief 651-671 | type: IMPL-MISMATCH)
- Brief cites `cinema_pipeline.py:767-788` for `all_skipped` short-circuit + `PERFORMANCE_SKIPPED_GATE` event. Actual lines at HEAD: **944-961**. ARCHITECTURE.md §4.1 step 14 has same drift (out-of-scope Lane D candidate).
- Evidence: `grep -nE "PERFORMANCE_SKIPPED_GATE|all_skipped" cinema_pipeline.py` → 944, 950, 961.
- Recommendation: Update G-PERF cell line refs. Re-grep every cinema_pipeline.py line ref in §5.1/§5.2 to catch any other drift (Rule #12 sweep).

**F-2 — G-PLAN §5.5 verification command uses non-existent field `plan_approved`** (cell: G-PLAN, brief 989 | type: IMPL-MISMATCH)
- §5.5 G-PLAN cold-context command says `jq '.scenes[].shots[] | {id, plan_approved}'` — actual field is **`plan_status`** (string-valued: "approved"/"rejected"/"pending_review"). Cell PREDICTION body correctly uses `plan_status`; §5.5 row contradicts.
- Evidence: `grep -rn "plan_approved\|plan_status" cinema/ domain/` → 0 hits `plan_approved`; 14+ hits `plan_status` across `cinema/services.py:54`, `cinema/review/controller.py:207/220/283/343/348/554/557`, `domain/project_manager.py:286/433-439`, `domain/models.py:98`.
- Recommendation: Fix §5.5 row to `jq '.scenes[].shots[] | {id, plan_status}'`. Currently broken — running the command at execution returns `null` for every shot regardless of plan state.

**F-4 — PR-STORY ↔ scene-decomposer field-name contradiction** (cell: PR-STORY, brief 761-782 vs scene-decomposer impl | type: CONTRADICTION + IMPL-MISMATCH)
- PR-STORY failure mode #2 says "shots omit characters listed in `characters_present`" — actual SHOT-level field is **`characters_in_frame`** (`domain/scene_decomposer.py:538/545/558/607/614/734/741/754`). `characters_present` is a SCENE-level field. PR-CONTINUITY correctly uses `characters_in_frame`; PR-DIALOGUE also ambiguous (brief 863).
- Recommendation: PR-STORY failure mode #2 → "shots' `characters_in_frame` omits character_ids listed in scene's `characters_present`". Adjustment indicator → "validate per-shot `characters_in_frame` covers scene's `characters_present` union (or rationale why a character is absent)". Makes the falsifiability target precise.

**F-11 — Multiple cells use unfalsifiable phrasing for content quality** (cells: P-DECOMPOSE 469, P-CHIEFDIR 544, PR-MOTION 818, PR-CONTINUITY 887 | type: FALSIFIABILITY)
- "Should work", "reasonable output", "well-formed prompts", "shots that advance the narrative" pass for any non-error output. §5.5 has falsifiable cold-context commands for these cells — the PROSE adds qualitative noise that won't enter PASS/MINOR/MAJOR/FALSIFIED classification.
- Recommendation: Per P-* cell, ensure PREDICTION "Expected content quality" includes ≥1 falsifiable bullet matching §5.5 command. Move qualitative claims to separate "Subjective quality signals (INSIGHT-only)" subsection NOT subject to PASS/FAIL classification.

**F-12 — P-CHIEFDIR "~60-80% APPROVED" lacks quantitative basis** (cell: P-CHIEFDIR, brief 544 | type: QUANT-BASIS)
- PREDICTION states "APPROVED expected ~60-80% of the time. REJECTED rare (<10%)" — no citation to prior run logs, telemetry, or baseline N. Rule #1 (ADR-013) failure.
- Recommendation: Either (a) cite a baseline run if one exists, OR (b) re-frame as "first-execution hypothesis; refine after N=10 baseline runs". Currently unfalsifiable in either direction.

### MINOR (14)

**F-3 — P-BGM "FAL hard-cap 47s" overclaims constraint** (cell: P-BGM, brief 511-531 | type: QUANT-BASIS)
- "Duration exactly 47s (FAL hard-cap per call)" — 47s is caller choice at `cinema_pipeline.py:538`; FAL function default is `42` (`audio/music.py:240`); `generate_suno_v5` supports up to 240s (line 164). ARCHITECTURE §12.5 calls 47s "FAL practical max", not hard-cap.
- Recommendation: Re-phrase to "duration 47s (caller-fixed; ARCHITECTURE §12.5 'practical max for FAL Stable Audio')". Avoids mis-classifying a 60s observation as FALSIFIED.

**F-5 — PA-IDENTITY ADR-013 basis "0.60-0.70" understates default** [PA-* — director-side scope] (cell: PA-IDENTITY, brief 1201 | type: QUANT-BASIS)
- Default per `cinema/shots/controller.py:491` is unambiguous `0.70`; "0.60-0.70" range has no source. Sweep sets (0.60/0.70/0.80) remain valid PA-* design — just don't claim default is range.
- Recommendation: "0.70 default; `identity_strictness` setting overrides." (Director-side scope; surfacing as cross-reference.)

**F-6 — P-IDENTITY ↔ PA-IDENTITY threshold default disagreement** (cells: P-IDENTITY 494 ↔ PA-IDENTITY 1188+1201 | type: CONTRADICTION)
- P-IDENTITY says default 0.70; PA-IDENTITY says 0.70 in Set 2 but "0.60-0.70" in ADR-013 basis. Cells internally inconsistent.
- Recommendation: Fold into F-5 fix; cross-cell consistency restored.

**F-7 — PA-IDENTITY Set 1 sweep value collides with default** [PA-* — director-side scope] (cell: PA-IDENTITY, brief 1187-1188 | type: FALSIFIABILITY)
- Set 1=0.60 / Set 2=0.70 (default) / Set 3=0.80 → Set 2 REDUNDANT with no-override case. Pass-rate predictions (~80-90%/~60-75%/~30-50%) lack baseline distribution.
- Recommendation: Either widen sweep (0.55/0.70/0.85), OR flag pass-rates as "hypotheses pending baseline measurement" per §8 protocol. (Director-side scope.)

**F-9 — PR-CONTINUITY return-shape says "tuple-equivalent" but impl returns dict** (cell: PR-CONTINUITY, brief 886 | type: IMPL-MISMATCH)
- Expected output "(enhanced_prompt: str, continuity_config: dict) tuple-equivalent". Actual at `domain/continuity_engine.py:454` returns single `enhanced` dict with mutated `prompt` + added `continuity_config`. Not tuple.
- Recommendation: "dict with mutated `prompt` field + added `continuity_config` field; original shot fields preserved." Match actual return surface so DELTA classification works.

**F-10 — PR-IMAGE asymmetric confidence (50-300 words vs vague)** (cell: PR-IMAGE, brief 795 | type: CONFIDENCE-ASYM + FALSIFIABILITY)
- Mixes precise quantitative ("50-300 words typical") with unfalsifiable ("descriptive nouns + adjectives; no abstract narrative-only language"). Word-count testable; abstract-language operator-subjective.
- Recommendation: Either (a) define operationalizable abstract-language check (e.g., grep verb tense / sentence count), OR (b) flag as QUALITATIVE-INSIGHT not subject to PASS/FAIL.

**F-13 — Multiple latency ranges lack measurement provenance** (cells: P-STYLE 3-8s, P-KEYFRAME 15-60s, P-MOTION 60-180s/30-60s/45-120s, P-PERFORMANCE 20-90s, P-IDENTITY 0.5-3s, P-ASSEMBLY 30s-2min | type: QUANT-BASIS)
- Per Rule #1 (ADR-013): latency ranges require justification. P-* cells lack "ADR-013 quantitative basis" subsections that PA-* cells DO have (e.g., "prior PuLID benchmark on A100", line 1053+).
- Recommendation: Add "ADR-013 quantitative basis" subsection to each P-* cell (parallel structure with PA-*). Even one-line provenance ("unverified — refine after first execution") makes confident-grounded vs guessed-from-memory asymmetry explicit.

**F-14 — Top-3 failure modes skip identity-cascade across phases** (cells: P-KEYFRAME, P-IDENTITY, P-MOTION, P-PERFORMANCE | type: MISSING-MODES)
- Each cell flags identity-related modes in isolation; no cell predicts CASCADE: keyframe identity_score borderline → motion inherits → performance reuses → final reel composite fails. Cycle-13 substrate work was identity-validator-driven; this is the highest-stakes failure pattern.
- Recommendation: Add cross-cell prediction (P-IDENTITY OR §6 matrix row): "if keyframe identity_score in [0.70, 0.75] borderline at GATE 2, expect motion identity drift 40-60% of takes + performance identity below GATE 3; mitigation = re-iterate keyframe before motion". Single highest-value prediction this brief could codify.

**F-15 — G-PERF SKIP-engine failure mode conflates whitespace + case-variation** (cell: G-PERF, brief 663-668 | type: MISSING-MODES)
- Failure mode #1 says "stray whitespace OR mixed-case ('skip', 'Skip')" — but `.upper() == "SKIP"` HANDLES case variation. Only whitespace remains as failure mode. Also, write-paths at `cinema/shots/controller.py:618/655/736` (3 sites) increase inconsistency risk.
- Recommendation: Reframe: "SKIP field has unexpected whitespace OR is set via a write-path that misses `.upper()` normalization — verify all 3 write-sites at `controller.py:618/655/736` use canonical literal `'SKIP'`". Case-variation framing is a red herring.

**F-16 — G-SCREEN failure mode #2 contradicts the flag-flip design intent** (cell: G-SCREEN, brief 713-715 | type: CONTRADICTION)
- Failure mode #2 says `CINEMA_SCREENING_STAGE=0` opt-out + stale UI is a failure — but operator explicitly setting opt-out is DESIGN-INTENDED behavior. Actual failure would be UI not feature-detecting the flag.
- Recommendation: Either remove FM#2 OR reframe as "UI surfaces approve button even when backend flag is off" (frontend bug, not backend gate failure).

**F-17 — P-MOTION ↔ P-PERFORMANCE motion-fidelity cross-cell pattern missing** (cells: P-MOTION 419, P-PERFORMANCE 570 | type: MISSING-MODES)
- Phases interact (PERFORMANCE before MOTION per ARCHITECTURE §4.1 step 12→15); both predict identity-preserved-within-phase but not BOUNDARY discontinuity (perf↔motion identity drift at phase boundary even when both phases pass individual checks).
- Recommendation: Add Tier C-specific cross-cell prediction (P-IDENTITY or §6 matrix): "perf↔motion boundary identity_score within ±0.05 of within-phase scores; >0.10 delta indicates phase-boundary identity discontinuity".

**F-20 — §6 adjustment matrix row "cinema/iteration/" path stale** (brief 1257 | type: IMPL-MISMATCH)
- Row targets `cinema/iteration/` — no such subdir. `ls cinema/` shows only `phases/`, `review/`, `shots/`. Iterate endpoint at `web_server.py:1677 api_iterate_take` → `cinema/shots/controller.py:regenerate_with_intent`.
- Recommendation: Update row to: `web_server.py api_iterate_take` + `cinema/shots/controller.py regenerate_with_intent` + `CINEMA_DIRECTORIAL_ITERATION env`.

**F-21 — P-ASSEMBLY top-3 failure modes skip BGM-loudnorm coupling** (cell: P-ASSEMBLY, brief 447-450 | type: MISSING-MODES)
- BGM is 47s; reel may be 5-60s. Loop/crop logic could fail at boundary cases (Tier B 5-15s reel × 47s BGM → ~80% BGM unused; Tier C 30-60s × 47s → loops once with discontinuity). FM #3 lumps "BGM length mismatch" with audio offset; deserves own slot.
- Recommendation: Split FM #3 into (a) BGM loop/crop boundary mismatch, (b) per-scene audio offset misalignment. Each gets own adjustment indicator.

**F-22 — Cells claim "filled per §8 protocol" but lack prediction-from-impl-read paper trail** (cells: P-DECOMPOSE 470, P-PERFORMANCE 564, P-CHIEFDIR 545 | type: QUANT-BASIS + FALSIFIABILITY)
- §8 step 1 says "Read impl FIRST". Cells assert ranges ("competitive ~8-15s", "20-90s") without naming source. PA-* cells DO cite source (line 1053+). Asymmetry suggests P-* phase cells were not filled from measurement.
- Recommendation: Could fold with F-13 (add ADR-013 basis subsections to P-* cells).

### INFORMATIONAL (3)

**F-8 — PR-DIALOGUE adjustment indicators reference non-existent fields** (cell: PR-DIALOGUE, brief 869-872 | type: IMPL-MISMATCH)
- `language_pref` and `character_voice` don't exist in code. Speculative future-fields. OK as ADJUSTMENT recommendations but reads as if existing impl.
- Recommendation: Mark as "(future field; would require model change)" or "(proposed)". Per Rule #12 — even ADJUSTMENT recommendations citing field names should grep-verify.

**F-18 — PA-VIDEO model identifier `veo-3.1-generate`** ✅ **CLOSED via operator post-report grep**
- `veo_native.py:55`: `self._model = "veo-3.1-generate" if self._backend == "vertex" else "veo-3.1-generate-preview"` — model name verified correct. **No action needed on PA-VIDEO Set 1.**

**F-19 — PR-AUDIO-VIBE adjustment indicators reference future API extension** (cell: PR-AUDIO-VIBE, brief 915-918 | type: IMPL-MISMATCH)
- Proposed `scene_stage` parameter is API change requiring caller-site updates at `audio/music.py:158/235`, not one-line config tweak.
- Recommendation: Mark as "(API change — would require caller-site updates)".

---

## Summary table (22 net findings)

| Type | CRITICAL | IMPORTANT | MINOR | INFORMATIONAL | Total |
|---|---|---|---|---|---|
| CONTRADICTION | 0 | 1 (F-4) | 2 (F-6, F-16) | 0 | 3 |
| QUANT-BASIS | 0 | 1 (F-12) | 4 (F-3, F-5, F-13, F-22) | 0 | 5 |
| CONFIDENCE-ASYM | 0 | 0 | 1 (F-10) | 0 | 1 |
| FALSIFIABILITY | 0 | 1 (F-11) | 2 (F-7, F-22 dual) | 0 | 3 |
| MISSING-MODES | 0 | 0 | 4 (F-14, F-15, F-17, F-21) | 0 | 4 |
| IMPL-MISMATCH | 0 | 2 (F-1, F-2, F-4 dual) | 3 (F-9, F-20, +F-22 partial) | 2 (F-8, F-19) | 8 |
| **Total** | **0** | **5** | **14** | **3** | **22** |

F-18 closed via post-report grep-verify (`veo-3.1-generate` confirmed).

---

## Disposition recommendation (per Rule #15 advisory matrix)

Per Q8 (user's §9 answer) inline per-finding commits + Rule #15 advisory matrix:

- **CRITICAL findings (0):** N/A — none.
- **IMPORTANT findings (5):** F-1, F-2, F-4, F-11, F-12 — option (a) preferred per matrix (fold into single brief revision is fast close path; all 5 are sub-5-LoC edits). **MUST land before execution to preserve predictive harness falsifiability discipline.**
- **MINOR findings (14):** option (a) fold preferred (cumulative ~60-90 min wall-clock for all 14 in single revision) OR per-finding inline commits per Q8 (higher commit count, cleaner per-finding traceability).
- **INFORMATIONAL findings (3):** option (c) NO ACTION acceptable; F-8/F-19 readers reason correctly; F-18 already CLOSED.

**Recommended fold scope:**

- **Minimal (IMPORTANT-only)**: 5 findings as one `docs(brief): v0.9.1 — fold operator joint-review IMPORTANT findings (F-1/F-2/F-4/F-11/F-12)` commit. <30 min wall-clock. Unblocks v1.0 ship.
- **Full**: all 22 findings as one revision. ~60-90 min wall-clock. Recommended given brief is substantively complete pending only joint review + per-finding traceability matches Q8 commit discipline at cell-revision-grain granularity.

**Operator strong-recommendation:** Full fold. The MINOR findings are individually low-impact but cumulatively address the predictive-harness falsifiability discipline cycle-13 R-Q2-1 codification was built to enforce. Letting them slide reduces brief utility at first execution.

Director-side decision per Sh strategic-default + Rule #15 receiving-seat option choice. Operator stands by.

---

## Cycle-15 entry status post-this-report

| Priority | Status |
|---|---|
| 1 G-* + PR-* brief cell fills | ✅ DONE (director) |
| 1b Layer 2 Rule #12 fix | ✅ DONE (operator) |
| 2 User-§9 5-9 answers | ✅ DONE (director + user) |
| 3 RunPod pod fresh deploy | OPEN — user-principal action |
| 4 Joint v0.9 mid-prep review (OPERATOR SIDE) | ✅ DONE (this verification-report) |
| 4b Joint v0.9 mid-prep review (DIRECTOR SIDE — PA-* review) | OPEN — director-side dispatch per Rule #9 §"Parallelism" |
| 5 v0.9.1 fold of operator joint-review findings | OPEN — director-default option (a) recommended |
| 6 v1.0 ship + execution authorization | BLOCKED on #3 + #4b + #5 |
| 7 Tier A/B/C/D execution | DEFERRED cycle 16+ per Q5 |

---

## Operator standby

Operator joint-review side complete. Standing by for:
- Director-side joint review on PA-* cells (Rule #9 §"Parallelism")
- Disposition decision on this report (Rule #15 receiving-seat option choice)
- Joint v0.9 cross-reconciliation (after both seats' findings land)
- v1.0 ship + RunPod pod restart + execution authorization

No active operator-default work in progress. Cursor at `2026-05-27T10:20:35Z` (no new mailbox events to consume beyond this commit's send).

---

Signed,
Operator-seat — 2026-05-27 cycle 15 entry, post-`349afe1` Layer 2 closure + post joint v0.9 mid-prep review (operator side; 22 net findings; subagent ~191k tokens; F-18 closed post-report)
