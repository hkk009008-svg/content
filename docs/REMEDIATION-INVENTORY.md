# Remediation Inventory — Program Hardening Campaign

> Single source of truth (spec `docs/superpowers/specs/2026-06-14-program-hardening-roadmap-design.md` §2).
> **Writer:** coordinator (primary) + deputy own-lane status when coordinator offline (§6f).
> Status one of: open | fixing | fixed | verified | provisional.

## Campaign constants
- **Wave-gate SLA:** 24h (§6f).
- **Wave-1 cross-cutting first-mover sequence:** TO BE SET by coordinator at Wave-1 open (§6b), AFTER discovery (Task 7) so newly-found cross-cutting pins are included. Seed signal so far: `auto_approve.py` W1 pin is Pair-A (`aa-nan-rules`); `core.py` W1 pin is Pair-B (`budget-nan`).

## Schema
`| id | subsystem | file:line | severity | priority | fail-mode | repro | xfail-pin | lane-owner | shared-lock | wave | status | verifier | notes |`

| id | subsystem | file:line | severity | priority | fail-mode | repro | xfail-pin | lane-owner | shared-lock | wave | status | verifier | notes |
|----|-----------|-----------|----------|----------|-----------|-------|-----------|------------|-------------|------|--------|----------|-------|
| aa-nan-rules | gates | cinema/auto_approve.py:118 | CRITICAL |  | NaN threshold makes nan>0 False so the veto rule never registers and the gate silently passes everything (one variant = unbounded per-shot spend) | yes | tests/unit/test_auto_approve_nangate_xfail.py | A | W1-auto_approve.py.lock | 1 | open |  | cross-cutting module; 5 parametrized cases; fix = finite-guard the numeric reads in from_project via cinema.context._finite_or; Pair-A disposition owed (image/identity gates dominate) |
| budget-nan | money | cinema/core.py:101 | CRITICAL |  | NaN budget survives float() and bool(nan)=True stores it so would_exceed/is_over_budget compare against NaN (always False) -> unbounded spend masquerading as a set cap | yes | tests/unit/test_budget_nan_gate_xfail.py | B | W1-core.py.lock | 1 | open |  | pin self-labeled major; coordinator reclassified CRITICAL per §4 (money-loss); open design Q = fail-safe block vs None=unlimited (surface, do not silently decide) |
| pulid-nan-node100 | identity | quality_max.py:560 | CRITICAL |  | NaN pulid_weight reaches PuLID node-100 weight (no _finite_or guard unlike nodes 700/701); start_at/end_at 561-562 share the gap; silent render corruption | yes | tests/unit/test_nangate_siblings_op1_verify.py | A |  | 1 | open |  | sibling of 7b4d377; reachable via controller.py:778 pulid_weight_override (no chokepoint); director-1 import-swap pass owns the fix |
| null-continuity-crash | identity | workflow_selector.py:515 | CRITICAL |  | JSON-null continuity_options -> None.get(img2img_denoise) AttributeError crash in get_workflow_params | yes | tests/unit/test_nangate_siblings_op1_verify.py | A |  | 1 | open |  | sibling of bf1034a; sibling site quality_max.py:1041 already has the isinstance dict-guard this block lacks; director-1 import-swap pass |
| has-char-lora-hole | identity | quality_max.py:1006 | MAJOR |  | has_character keys off the face reference only; a LoRA-only shot gets has_character=False -> _prune_unavailable drops node 700 and _inject_identity early-returns -> trained LoRA silently dropped (zero identity, no retry) | yes | tests/unit/test_has_character_lora_only_hole.py | A |  | 2 | open |  | borderline gate-bypass (ArcFace gate keys off same flag); dispositioned director-1 PM7 DESIGN backlog; fix = decouple has_face_ref/has_char_lora (~24 sites) |
| audioflag-inherit | assembly | cinema/shots/controller.py:241 | MAJOR |  | swallowed _has_audio_stream failure drops the variant audio flags silently -> scene-TTS overwrites the take real voice (voice-loss); no WARNING logged | yes | tests/unit/test_lane_silent_gate_siblings_xfail.py | B |  | 2 | open |  | silent-gate-degradation family; fix = WARN before the silent return |
| idgate-failopen | identity | phase_c_vision.py:351 | MAJOR |  | identity-gate fallback returns default_pass confidence 0.7 on an Anthropic API error (print not log) -> PASSES every non-strict identity threshold | yes | tests/unit/test_lane_silent_gate_siblings_xfail.py | A |  | 2 | open |  | CROSS-LANE: phase_c_* is Pair-B module per §6b but content is Pair-A identity -> needs co-sign; the fail-open-to-PASS policy could be CRITICAL gate-bypass (Pair-A policy call); pin tests the observability half |
| lipsync-veto | gates | cinema/auto_approve.py:502 | MAJOR |  | _best_take_lipsync ignores dialogue_audio_in_clip and a postprocess lip_sync variant carries no lipsync_score -> a manually-fixed shot is still vetoed on the base motion take 0.0 score | yes | tests/unit/test_postprocess_audio_siblings_xfail.py | B | W2-auto_approve.py.lock | 2 | open |  | cross-cutting auto_approve module; director2 disposition owed |
| coherence-silent | gates | coherence_analyzer.py:202 | MEDIUM |  | unreadable image -> color_drift=0.0 and valid=False with NO log (module has zero logging) -> silently suppresses the color_grade gate | yes | tests/unit/test_lane_silent_gate_siblings_xfail.py | A |  | 2 | open |  | pin tests analyzer-side observability; the deeper caller-side .valid-ignore (color_grade suppression) is MAJOR and UNPINNED -> track in the hardening epic; §6b module = Pair-A |
| perf-take-meta | assembly | cinema_pipeline.py:703 | MEDIUM |  | a performance take approved as final -> _approved_take_metadata returns {} (only motion+postprocess searched) -> scene-TTS muxed over the embedded voice (voice-replacement) | yes | tests/unit/test_postprocess_audio_siblings_xfail.py | B |  | 2 | open |  | fix = add performance_takes to the search tuple; director2 disposition owed |

## Closed / excluded-from-discovery (HEAD-checked verified, spec §3/§5)
These are NOT re-hunted by the Phase-0 discovery workflow (Task 7 excludes them); Wave 1 carries only a re-verification check, not a fresh fix.
- **`workflow_selector.py`** — the main non-finite/param issue is closed by `bf1034a` (re-verify only). NOTE: `null-continuity-crash` above is a *separate, still-open* sibling crash in the same module that `bf1034a`'s audit boundary did not extend to.
- **Determinism (OpenCV thread-race)** — closed: `cv2.setNumThreads(1)` + deterministic tie-break (`ARCHITECTURE.md` §11.1, 30/30 byte-identical). Wave-1 re-verification only; Phase-0 discovery must not re-discover it.

## Rejected findings (discovery)
_(populated by Task 7 — refuted candidates recorded here, never silently dropped, spec §3)_
