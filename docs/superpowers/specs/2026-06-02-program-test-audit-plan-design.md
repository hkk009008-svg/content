# AI Cinema Pipeline — Test / Audit Plan (intent-grounded)

**Date:** 2026-06-02
**Status:** Design — pending spec review + user approval, then execution
**Builds on:** `docs/superpowers/specs/2026-06-01-comprehensive-capability-test-suite-design.md` (`75ada03`, approved-in-brainstorming, pending execution). This plan **extends** that design with four things it predates: the production+LoRA photoreal reframe, the Veo+overlay dialogue decision, the new untested `hedra_native.py`, and a concrete UI-surfacing dimension. It does not re-derive it.

## Purpose

A systematic, **manual-intent-grounded** plan to determine, for the whole program:
1. **What works vs what's broken** — measured against the manual's *definition of success*, not just code coverage.
2. **What to prune** — verified dead code (keeping dormant *quality* levers).
3. **What to fix** — bugs, no-ops, dormant levers to wire, stale docs.
4. **How the UI should reflect it** — surface capability, quality, and health the UI hides today.

## How to read this plan

- **Truth order:** `ARCHITECTURE.md` > `docs/PROGRAM-MANUAL.md` > digests. **Verify at HEAD before acting** — anchors here are point-in-time (branch `feat/max-tier-provisioning` @ `cb31207`).
- **Execution tiers (cost-aware):** 🟢 **offline** ($0, unit/mocked) · 🟡 **live** (real API call, $) · 🔴 **e2e** (full pipeline run, $$).
- Every "works/broken" verdict in Part 1 is scored against a **Part 0** success criterion.
- **Output of execution** = a **scorecard** (measured-vs-intended-bar) + prune/fix PRs + UI surfacing.

---

## Part 0 — Definition of Success (the yardstick, from the manual)

What the program is *for* (manual §1.2–§1.3): collapse the multi-week production chain into one automated, human-in-the-loop flow turning *script/idea + characters + locations* → a finished, sound-synced, photorealistic cinematic MP4 (`exports/final_cinema.mp4`). "Not a slideshow of disconnected clips." Each criterion below is the bar Part 1 tests against.

| # | Success criterion | Manual § | "Met" means |
|---|---|---|---|
| S1 | **Same face every shot** | §1.4, §5.3B | PuLID lock + `IdentityValidator` per-frame score ≥ per-shot bar (portrait .75/.70/.60 … action .65/.60/.50) |
| S2 | **Same location/architecture** | §5.3D | Deterministic per-location seed + verbatim `prompt_fragment` injected into every shot at that location |
| S3 | **Coherent lighting/color/composition** | §5.3D, §1.5 | `coherence_analyzer` overall ≥ .6 between consecutive shots |
| S4 | **Dialogue is real** | §5.3C, §1.4 | Native-audio (Veo) OR a mandatory lip-sync pass, SyncNet ≥ .65 (.70 Korean). **NEW decision: dialogue = Veo video → overlay(your TTS); Veo native for single shots** |
| S5 | **Full audio stack** | §5.4 | TTS + BGM + foley, 3-track mix (voice 1.0 / BGM .12 / foley .20), EBU R128 −14 LUFS |
| S6 | **Broadcast format** | §2.1 | 1920×1080 @ 30fps, h264 crf20 + AAC; clean concat or clamped xfade |
| S7 | **Photorealism** | §5.4 | **REFRAMED (real finding, supersedes manual):** production tier + per-char LoRA @ strength 0.55 is photoreal+identity; *max tier renders painterly*. Veo RAI blocks hyper-processed keyframes (production keyframes pass) |
| S8 | **Two quality tiers** | §5.2 | production (~$0.04/keyframe, `pulid.json`) vs max (~$0.40, `pulid_max.json`) both runnable |
| S9 | **Never silently ship junk** | §1.5 | Every stage gated+scored (ChiefDirector prompts, ArcFace+aesthetic images, optical-flow motion, SyncNet lip-sync); failures diagnosed, not buried |
| S10 | **Degrade gracefully** | §1.5 | Vendor cascade (9-engine video, image ComfyUI→FAL→…), LLM fallback, deterministic LLM-free fallbacks; missing key narrows capability, doesn't kill the run |
| S11 | **Human-in-loop OR headless** | §1.4, §5.4 | 5 gates with auto-approve heuristics; `headless=True` → unsatisfied gates fail-fast (`GateNotSatisfiedError`) |
| S12 | **Resumable** | §1.5, §2.5 | Disk checkpoint after every scene; crashed run restarts where it left off |
| S13 | **Tunable** | §1.5, §5.7 | Behavior via `global_settings`/`get_project_setting`; `pipeline_context.md` injected into every LLM |
| S14 | **Cost-tracked** | §1.5, §5.3E | `CostTracker` logs every call; hard-gate vs `budget_limit_usd` |

---

## Part 1 — Capability ledger: what works / what's broken

Each success criterion → test method → tier → current status. **Status from the grounding survey** (test landscape + component map). ✅ tested · ⚠️ partial/contract-only · ❌ **zero behavioral test (blind spot)**.

| Crit | Test method | Tier | Current status | Gap to close |
|---|---|---|---|---|
| S1 face | Score known on-model vs off-model frames through `IdentityValidator.validate_video`; assert per-shot bars + rolling-stats PuLID feedback | 🟢 | ❌ `identity/validator.py` **0 behavioral-test refs** (4 production importers — `identity/__init__.py`, `performance/identity_gate.py`, `face_validator_gate.py`, `continuity_engine.py`; biggest *test* blind spot, NOT dead); `identity_gate` ✅ | Behavioral tests for the validator + adaptive-weight loop |
| S2 location | Assert same seed+`prompt_fragment` injected for two shots at one location | 🟢 | ⚠️ `location_manager` partial | Determinism + injection test |
| S3 coherence | Synthetic shot pairs → `assess_coherence` ≥/< .6 boundary | 🟢 | ✅ `test_coherence_analyzer` | (light) error paths |
| S4 dialogue | (a) Veo native-audio config; (b) **Veo→overlay(TTS)** produces video+audio, SyncNet ≥ .65; (c) generation cascade (Hedra→Omnihuman) | 🟡 | ⚠️ `lip_sync` contract (F1b); `veo_native` config ✅; **Veo+overlay & `hedra_native` only manually validated this session** | Tests for overlay cascade + `hedra_native`; wire Veo+overlay as default route |
| S5 audio | TTS/BGM/foley generation + 3-track mix levels + loudnorm target | 🟡 | ✅ audio gen (cartesia/foley/suno); ⚠️ mix/loudnorm | Assert −14 LUFS + track gains on a fixture |
| S6 format | ffprobe final mp4: 1920×1080/30/h264/aac | 🟢 | ⚠️ assembly provenance only | Probe-and-assert (also feeds UI Part 4) |
| S7 photoreal | (a) production+LoRA@0.55 identity 0.45–0.86; (b) max=painterly regression check; (c) Veo-RAI keyframe pass | 🟡 | ❌ no automated aesthetic/realism test; **manually validated this session** | Codify the production+LoRA recipe as the photoreal path; aesthetic-score harness |
| S8 tiers | Both `pulid.json` + `pulid_max.json` build valid ComfyUI graphs | 🟢 | ✅ `test_quality_max_overlay/prune` | production-tier graph test |
| S9 gates | ChiefDirector veto *composition* (HC1–HC8 → REJECT/MODIFY); each gate rejects junk | 🟢 | ⚠️ `chief_director` parse only; **veto-composition ❌**; `auto_approve` ✅ | Veto-composition behavioral tests |
| S10 degrade | Force primary-API failure → assert correct fallback + retry/quota-vs-timeout classification | 🟢 | ⚠️ cascade *order* tested; error/fallback classification ❌ | Fault-injection tests |
| S11 headless | `headless=True` + unsatisfied gate → `GateNotSatisfiedError`; auto-approve path | 🟢/🔴 | ⚠️ gate logic ✅; e2e headless ❌ | Headless smoke (e2e) |
| S12 resume | Kill mid-scene → restart → resumes from checkpoint | 🔴 | ⚠️ `refresh_project_snapshot` ✅; full resume ❌ | Resume e2e |
| S13 tunable | `get_project_setting` plumbing (the getattr-silent-fail stays dead) | 🟢 | ✅ ci_smoke §15.7 | (covered) |
| S14 cost | Every call logged; budget gate halts | 🟢 | ✅ `test_cost_tracker`; **but audio uncapped + per-process reset (see Part 3)** | Audio-cost cap test |

**Zero-test blind spots (highest leverage, all 🟢 $0):** `identity/validator.py`, `style_director.py`, `sora_native.py`, `ltx_native.py`, `phase_c_vision.py`, **`hedra_native.py`** (new). These are Phase A of execution (Part 5).

---

## Part 2 — Prune list (what to cut)

Grep-verified zero-live-callers on this branch (excl. tests/worktrees). **Re-verify method (mandatory before any delete):** re-grep incl. tests + dynamic/string refs at prune time (per `feedback_re-verify-before-destructive-commits`); one `chore` commit per concern; ADR per ADR-016; land on `main`.

| Candidate | Evidence | Action |
|---|---|---|
| `reporter.py` (whole file) | no `import reporter` | **prune** (ARCHITECTURE §17 "true orphan") |
| `generate_characters.py` (whole file) | superseded by `character_manager.create_character_with_images` | **prune** |
| `dialogue_writer.{format_dialogue_for_voiceover, dialogue_to_narration_text}` | 0 non-test callers | **prune** |
| `continuity_engine.{record_shot_generated, reset_scene}` | 0 callers; dead `last_generated_image` path | **prune** |
| `continuity_engine.validate_multi_identity` | 0 callers; only a docstring ref (`identity/validator.py:45`) | **Phase-A decision** (owner: prune-verification step): default **prune** unless multi-char (Tier-D) is roadmapped; update the `validator.py:45` docstring either way |
| *(optional, ops not quality)* `auto_approve.summarize_audit`, `cinema/pipeline.py::CinemaPipeline` (§15.9), `run_tier_c.py` | 0 prod importers | **prune-optional** |

**KEEP — dormant *quality* levers (NOT prune; pruning trades against full capability):** `chief_director.evaluate_generation_quality` + `negative_prompts.py` (the auto-diagnose/remediate loop), `ltx_native.{_fal_transition,_native_transition}`, `validate_lora_quality` (implement — see Part 3), `hires_fix`, `continuity_engine.validate_multi_identity` (if multi-char reaches Tier-D). These move to Part 3 as *wire* candidates.

---

## Part 3 — Fix list (what to repair)

| Item | Type | Severity | Action |
|---|---|---|---|
| `validate_lora_quality` → unconditional `-1.0` stub (`prep/lora_training.py:515`) | dormant lever | **HIGH** (LoRA is the #1 identity lever; bad LoRA silently degrades identity) | **Implement** real validation |
| Dialogue routing not defaulted to Veo→overlay | wiring | **HIGH** (this session's decision) | Wire `generate_lip_sync_video` (`lip_sync_mode` routing, `lip_sync.py:680`) + the `motion_render` call-site to default dialogue → Veo video → overlay(TTS) |
| `hires_fix_enabled/denoise` validated+stored but never injected (nodes 900–902 pruned) | no-op | MED | Wire pass-2 denoise or remove the setting |
| `max_halt_rule` accepts 3 modes, `should_halt` implements only composite-only (`face_validator_gate.py:225`) | partial | MED | Implement conjunctive/budget_only or document the limit |
| Budget gate caps video/image only — **audio API costs uncapped**; `spent_usd` resets per-process (§5.3E) | bug | MED | Cap audio; persist spend |
| `evaluate_generation_quality` + `negative_prompts` auto-diagnose loop has no top-level caller | dormant lever | MED | **Wire** the retry/remediate loop into generation |
| `EXPERIMENTS_DB_PATH` read but never wired to CostTracker (always `data/experiments.db`) | no-op | LOW | Wire or remove |
| `pipeline_context.md` lip-sync guidance vs hard-coded `PURPOSE_API_RANKING` disagree (§5.7) | drift | LOW | Reconcile |
| `storyboard_mode` — manifest/manual say "stubbed", but F2b **wired** it (`cinema/phases/motion_render.py`: `_get_storyboard_mode`:45 / `_run_storyboard_scene`:100) | **stale doc** | DOC | Fix `pipeline_status.toml` + manual §5.3A in same change |
| `hedra_native.py` ATTEMPT-0 wiring (`cb31207`) undocumented in `ARCHITECTURE.md §10.6` | **stale doc** | DOC | Document (§10.6 lists Hedra only via FAL) |
| 3 `@unittest.skip` in `test_project_persistence.py:139,203,232` | test debt | LOW | Fix or remove |

---

## Part 4 — UI dimension (how the UI should reflect it)

The UI (React 19, 3-mode; `Telemetry.tsx` shows live cost + identity histogram + failed shots) hides most of the program's quality/health signal. Each gap → what the UI should show, grounded in intent.

| # | UI gap (today) | What the UI should reflect | Intent grounding |
|---|---|---|---|
| U1 | No capability scorecard (`pipeline_status.toml`/`scripts/status.py` are CLI-only) | Render live/wired/stubbed/parked/dead component status + the Part-1 scorecard | S9 (visible quality), S8 (tier reality) |
| U2 | Only *identity* histogram surfaced | Per-shot **coherence / motion-fidelity / SyncNet-lipsync** scores (already in `take.metadata`) | S3, S4, S9 |
| U3 | No loudness/format readout | Probe final mp4 → show −14 LUFS / 1920×1080 / h264+aac pass/fail | S5, S6 |
| U4 | No LoRA quality signal (`validate_lora_quality` stub) | Warn when a LoRA is bad before it silently degrades identity | S1, S7 |
| U5 | No pod/infra health (ComfyUI up/down, CUDA-context errors, Veo quota TTL) | Health panel — operators hit 502s blind today | S10 (degradation visible) |
| U6 | Budget caveats hidden (audio uncapped, per-process reset) | Annotate the cost panel with the real caps | S14 |
| U7 | No headless-readiness indicator (`final_require_human_if_upstream_auto` footgun, defaults True) | Flag headless-readiness before an unattended run dead-ends | S11 |
| U8 | No cascade-provenance ("which engine actually won") | Show per-shot winning engine (`cascade_metadata`) so silent fallbacks (max→production, Veo→silent-Kling) are visible | S9, S10 |

---

## Part 5 — Execution sequencing

Prioritized by leverage-per-dollar. Each phase is independently shippable.

- **Phase A — 🟢 offline, $0 (do first; highest leverage).**
  1. Behavioral tests for the 6 zero-test components (Part 1 blind spots) — esp. `identity/validator.py`.
  2. Re-verify the Part-2 prune list at HEAD (re-grep incl. tests/dynamic refs) → prune PRs.
  3. Audit the Part-3 no-ops (confirm each is dead/partial) → fix tickets; ship the 2 stale-doc fixes immediately.
- **Phase B — 🟡 live, $ (gated on spend-auth).** Per-API capability checks (each video/image/audio engine end-to-end on one fixture) + codify the production+LoRA photoreal path + the Veo+overlay dialogue route (S7, S4).
- **Phase C — 🔴 e2e, $$ (gated on spend-auth).** One headless full-pipeline run on a tiny script → produce the **scorecard** (each S1–S14: measured vs bar) + resume test (S12).
- **Phase D — UI.** Implement Part-4 surfacing, leading with U1 (scorecard) + U2 (per-shot scores) + U8 (provenance) — they reuse data already in `take.metadata`/`pipeline_status.toml`.

**Definition of done:** a committed **scorecard** (S1–S14 measured-vs-bar), merged prune PRs, fix tickets triaged by severity, and the UI surfacing U1/U2/U8 live.

---

## Appendix — Provenance

Grounded in a read-only grounding survey (2026-06-02) of: `docs/PROGRAM-MANUAL.md` (intent), `ARCHITECTURE.md` (truth + §15 smoke), `tests/` (55 unit + 2 integration; `tests/capability/` scaffolding begun — `identity/` subdir), the component map, `web_server.py` (65 routes), and the latest `docs/HANDOFF-*.md` (prune/fix/dormant-lever lists). The production+LoRA photoreal reframe and the Veo+overlay dialogue decision are this session's manually-validated findings (clips: `logs/{veo,hedra,lipsync_gen,veo_musetalk}_v2studio.mp4`). All file:line/§ anchors are point-in-time; re-verify at HEAD before acting.
