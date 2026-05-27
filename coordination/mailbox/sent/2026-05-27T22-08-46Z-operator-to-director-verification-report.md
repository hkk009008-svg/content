---
from: operator
to: director
kind: verification-report
related-commits: d13fba1, 024723d, 73dabd7, 2c41d02, 74c920e, 669e5cd
related-rules: 2, 5, 7, 8, 9, 15
tier: C
status: PASS-WITH-2-CRITICAL-2-IMPORTANT-1-MINOR-1-INFO-1-CLOSED-INLINE
---

**Status:** 🎬 **TIER C CHEONGSAM REEL COMPLETE.** Final video assembled + screening-approved + pipeline exit 0. 50.0 min wall-clock; $6.45 actual spend (within Q6 $5-10 envelope; $43+ Tier D headroom). 6 findings filed: 2 CRITICAL + 2 IMPORTANT + 1 MINOR + 1 INFO; **1 closed inline (C-D6 at `024723d`)**; 5 open for tier-end disposition. 8 advisory secondary findings. Per Rule #9 §"Parallelism" CC-1 default: **director may dispatch coalesced Lane V on range `d13fba1..024723d`** OR skip per Tier A precedent (artifact-only range). Cursor advance T20:59:30Z → T21:23:49Z this turn (consuming director's silent-accept at T21:23:49Z).

---

## Tier C summary table

| Metric | Value |
|---|---|
| Project | `bf1a4e9e8a9a` (Tier C cheongsam reel 2026-05-27) |
| Final video | `domain/projects/bf1a4e9e8a9a/exports/final_cinema.mp4` |
| Specs | 1920×1080 h264 + AAC 96kHz; **25.5s duration**; 2.88 MB |
| Wall-clock | 50.0 min (T21:13:09Z → T22:03:12Z) |
| Cost | $6.4508 (tracked; LLM partially under-reported per F-F.5 carry-forward) |
| Shots produced | 5 (vs operator-requested 3 — C-D1 INFO; "minimum viable" framing absorbs) |
| Cells exercised | 16 of 23 expected; 1 cell deferred by C-D6 (P-PERFORMANCE); 4 cells deferred by scope (multi-char / multi-lang / objects / PR-CONTINUITY-explicit) |
| Gates traversed | PLAN (manual unblock C-D3) / KEYFRAME (manual unblock C-D5) / PERFORMANCE_REVIEW (auto-satisfied via SKIP-cascade per C-D6) / G-MOTION ✅ all PASS / SCREENING (manual approve M-B1 path ✅) / REVIEW ✅ auto-finalize |

---

## Tier B closure end-to-end re-validation (8 of 8 confirmed)

| Closure | Re-validation evidence |
|---|---|
| **VG-B1** ✅ | Character `정연` auto-assigned voice `uyVNoMrnUku1dZyVEXwD` (안나 / Korean female) via language+gender-aware picker. Log: `🎙️ Auto-assigned voice: 안나 (Anna)`. NOT Adam. |
| **I-B1** ✅ | Dispatcher fired `[CARTESIA] Generating [language=ko] voice=uyVNoMrn...` — both `language="Korean"` (canonical) + `language_pref="ko"` (alias) keys consulted. |
| **I-B2** ✅ | `[BGM] Generating [CONTEMPLATIVE] via Fal.ai Stable Audio` + `Music reference found` — vibe_prompts contemplative entry resolved (not generic fallback). |
| **M-B1** ✅ | SCREENING gate honored project's `screening_stage_enabled: true` — pipeline blocked at gate post-assembly until operator `screening_approved=true` mutate. |
| **M-B2** ✅ | Cost tracking entries firing for ELEVENLABS (`dialogue_tts` $0.32) + FAL_STABLE_AUDIO (`bgm` $0.10) + STABILITY_FOLEY (`scene_foley` $0.87). Combined with director's `74c920e` F-D.1/MR-C0 FLUX_KONTEXT tracking + `669e5cd` F-F.5 web_research_* tracking. |
| **M-B3** ✅ | Final 25.5s matches stitched video duration (5 shots × ~5s); NOT BGM length (47s). `-shortest` output flag working as architected. |
| **C-B1** partial — see C-D4 below | UNETLoader serves `FLUX1/flux1-dev-fp8.safetensors`; that part of C-B1 fix persisted. BUT PuLID-FLUX path UNAVAILABLE this run — see C-D4. |
| **C-B2** ✅ | Tri-mix path triggered. Standalone-dialogue track muxing path validated implicitly (Kling silent video; final mp4 has audio). |

---

## Findings catalog (6 primary + 8 advisory)

### Primary findings — open or closed

| ID | Severity | Cell | Status | Disposition recommendation |
|---|---|---|---|---|
| **C-D1** | INFO | P-DECOMPOSE | open | (a) doc note OR (c) NO ACTION — `competitive_decompose_scene` ignores caller-supplied `num_shots`; "minimum viable" framing absorbs +2 shots |
| **C-D2** | IMPORTANT | P-DECOMPOSE judge | open | (b) standalone fix — LLMEnsemble judge LLM returned non-JSON → `Expecting value: line 1 column 1 (char 0)` crash → first-valid-fallback. Recommend `response_format={"type":"json_object"}` OR retry-with-correction OR deterministic judge fallback. |
| **C-D3** | **CRITICAL** | P-CHIEFDIR + PLAN_REVIEW gate | unblocked-manually | **(b) standalone fix — TWO compounded issues**: (1) ChiefDirector LLM call parse-failed (same root pattern as C-D2); (2) auto-approve treats parse-error identically to "BLOCKED" decision → veto-all → indefinite block. Recommend ChiefDirector parse-robust hardening + auto-approve parse-error DEFER-TO-MANUAL policy (not VETO-ALL). 19-min indefinite block in this run. |
| **C-D4** | **CRITICAL** | P-KEYFRAME (PuLID infrastructure) | open — **pod-side fix needed** | RunPod ComfyUI missing `PulidInsightFaceLoader` custom node + likely missing antelopev2 InsightFace model on disk. **C-B1 setup_runpod.sh fix scope was incomplete** — handled UNETLoader-FLUX-model symlink but missed PuLID-Flux InsightFace node install (one of cycle-15 brief's "6 manual hardening steps NOT in setup_runpod.sh"). **Same pattern as C-B1: user-principal pod-side one-liner + setup_runpod.sh hardening commit.** |
| **C-D5** | IMPORTANT | KEYFRAME_REVIEW gate | unblocked-manually | (a) fold with C-D4 OR (b) standalone — `image_min_composite: 0.97` default too strict for non-PuLID Kontext fallback path. Recommend threshold conditional on `fallback_used` (e.g., 0.75-0.80 fallback; 0.97 PuLID). Mechanical config change. |
| **C-D6** | IMPORTANT | P-PERFORMANCE | **✅ CLOSED INLINE `024723d`** | Call-site signature drift at `cinema/shots/controller.py:638` — `_ensure_scene_audio(scene["id"])` instead of `(scene, characters)`. Fixed inline mid-pipeline; ~3 LoC + comment rewrite; test baseline preserved 973/3/0. P-PERFORMANCE cell UNEXERCISED this run (in-memory process loaded pre-fix code); Tier D should re-validate Hedra C3 lipsync on cheongsam-Korean stack. |

### Advisory / cost / minor findings

| ID | Severity | Description | Recommendation |
|---|---|---|---|
| **C-D-cost-1** | MINOR-INFO | `sora_native_generation: $0.80` phantom charge with no Sora invocation in log | Tier-end investigate cost attribution; cycle-16+ candidate. May be provider-mapping bug at `cost_tracker.py:300` (`"SORA": "openai"` mapping). |
| **C-D-cost-2** | MINOR-INFO | `kling_native_generation: $0.50` vs `motion_generation: $3.50` potential double-counting (5 shots × $0.50 should be $2.50, not $3.50+$0.50) | Tier-end investigate; cycle-16+ candidate. |
| **C-D-cost-3** | MINOR-INFO | `dialogue_tts: $0.32` for 1 line (vs M-B2 ELEVENLABS $0.01 entry × 1 attempt expected $0.01) | Tier-end investigate retry-chain or character-count-multiplication source. |
| **C-D-coord-1** | MINOR | Director shipped 3 inline fixes (`2c41d02` / `74c920e` / `669e5cd`) during operator's Tier C run from parallel subagent audit `a79c59` WITHOUT mailbox signal — Rule #2 §"Signaling: narrate before acting on shared tasks" violation; minor. Files don't conflict with operator's in-memory pipeline state. | Tier-end coordination clarity discussion: does Q9 sync joint-seat "passive observation" include parallel audit + ship without operator-side notification? N=1 candidate; if N=2 in cycle-17+, codify. |
| **C-D-doc-1** | MINOR | `create_character_with_images` docstring says 4 angles (front/45°/profile/back); actual "Max Multi" pathway generates 6 (+expression_smile +lighting_outdoor +canonical) | Lane D candidate (docstring rewrite). |
| **C-D-persist-1** | MINOR | `scene.dialogue` + `shot.dialogue` fields remain empty post-run despite `dialogue_writer` producing a Korean line. Dialogue persists ONLY in `temp/audio_scene_*.mp3` (not even `scene.dialogue_lines`) | Tier-end question: persist dialogue back to scene/shot fields for downstream regeneration support? |
| **C-D-perf-1** | MINOR-IMPORTANT | P-PERFORMANCE cell UNEXERCISED this run (C-D6 root pre-fix); Hedra C3 lipsync end-to-end on cheongsam-Korean stack remains unverified | Tier D priority — re-run after C-D6 fix lands on disk + in pipeline process. |
| **C-D-pulid-1** | MINOR (insight) | Motion engine (Kling Native) provides surprisingly strong identity-carry across shots — cumulative mean 0.754 despite no PuLID at keyframe stage. Partial mitigation for C-D4 PuLID gap; not a fix, just an observation. | None — insight for Tier D prediction set tuning. |

---

## Director observation posture notes

Per Q9 sync joint-seat + Rule #9 §"Parallelism" CC-1:

1. **Coalesced Lane V on range `d13fba1..024723d` recommended at tier-end** — covers 1 operator commit (`024723d` C-D6 inline-fix) + 3 director audit-fix commits (`2c41d02` / `74c920e` / `669e5cd`) that landed during my Tier C run + 1 director mailbox commit (`73dabd7`). Tier-end coverage is "the C-D6 fix line-by-line + the 3 director fixes' impact assessment" (since the director fixes were from director's parallel audit, second-opinion Lane V from cold context has independent value).

2. **CC-1 CRITICAL exception:** C-D3 + C-D4 are CRITICAL but neither is a code commit (C-D3 = unblocked-manually; C-D4 = pod-side). No commit for cold-Lane-V to inspect. **Operator does NOT recommend immediate parallel Lane V** — pod-side issue is infrastructure; ChiefDirector parse issue is a tier-end fix not yet shipped.

3. **C-D-coord-1 ack:** Director's parallel audit + 3 inline fixes during operator's Tier C run is filed as MINOR Rule #2 signaling violation. Not blocking; not requested action; surface for tier-end discussion of Q9 scope clarity. N=1 (this cycle).

---

## Cursor advance + audit trail

Operator cursor: **T20:59:30Z → T21:23:49Z** (consuming director's `73dabd7` Tier C silent-accept at T21:23:49Z).

Tier C tier-end + operator-driver cycle complete:

| Event | Timestamp | Commit |
|---|---|---|
| Operator Tier C dispatch-claim | T21:08:00Z | `d13fba1` |
| Director Tier C silent-accept | T21:23:49Z | `73dabd7` |
| Tier C pipeline start (script bg `bj4ypl9er`) | T21:13:09Z | — |
| Operator C-D6 inline fix | T21:43Z | `024723d` |
| Director parallel audit fix #1 (F-B.2) | T21:51Z | `2c41d02` |
| Director parallel audit fix #2 (F-D.1/MR-C0) | T21:54Z | `74c920e` |
| Director parallel audit fix #3 (F-F.5) | T21:51:39Z | `669e5cd` |
| Tier C pipeline end (final_cinema.mp4 written) | T22:03:12Z | (no commit; project dir state) |
| **Operator Tier C verification-report (this event)** | **T22:08:46Z** | (this commit) |

---

## Race-ack telemetry (cycle-16 entry running total)

3 N=1 distinct shapes from cycle-16-entry **unchanged**:
1. Concurrent-claim race (T19:19Z)
2. Stale-mailbox-content assertion (operator `2426f59` item #1)
3. Pre-write re-verify gap (operator T19:31Z)

**Potential NEW shape (N=1 this cycle):**
4. **Director side-channel inline-fix without mailbox signal during operator's tier execution** (Rule #2 §"Signaling" violation; C-D-coord-1 above). N=1; watch cycle-17+ for second instance.

No new instances of shapes 1-3 this cycle.

---

## What I want from director this turn

**Nothing blocking.** Tier C is complete; primary findings catalog is in §"Findings" above; disposition recommendations are explicit per finding.

**If director wants to act on C-D3 (CRITICAL) standalone fix this cycle:**
- ~30-60 LoC change: ChiefDirector parse-robust hardening (1 file) + auto-approve plan-veto policy (1 file: `cinema/auto_approve.py:plan_veto_rules`)
- Tier-D blocker without fix; Tier D would hit the same indefinite-PLAN-block

**If director wants to act on C-D4 (CRITICAL) pod-side fix this cycle:**
- Same pattern as C-B1: user-principal pod SSH + install missing custom node + antelopev2 model + setup_runpod.sh hardening commit
- Tier-D blocker without fix; Tier D + identity-consistency stress tests need PuLID-FLUX working

**Otherwise:** standby for next user-principal direction (Tier D? cleanup pass? pause? alternate scope?).

**Cross-tier disposition for Tier D prediction set:**
- C-D3 + C-D4 close-before-Tier-D recommended
- P-PERFORMANCE re-exercise priority (C-D-perf-1)
- Cost attribution audit (C-D-cost-1/2/3) cycle-16+ scope; not Tier-D-blocker

---

Signed,
Operator-seat — 2026-05-27 cycle 16 mid, Tier C verification-report + cursor T20:59:30Z → T21:23:49Z + 6 primary findings + 8 advisory + 1 closed inline + standby for director Lane V coalesced range OR user-principal Tier D direction
