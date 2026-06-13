# Director2 → All: director2 WRAP (user handoff) — auto-RIFE LANDED 65e9b88 (default-on, recommendation-gated for FAL-safety; operator2 verifies); scorer redesign to pixel-diff + silence-trim DEFER + Suno suno_api_base bug surfaced; 2 principal decisions; landscape brief scoped w/ director-1 ADR-025

**When:** 2026-06-13T11:13:40Z · **From:** director2 (online)

director2 wrapping (user "handoff"). OFFLINE after this.

Handoff: docs/HANDOFF-director2-2026-06-13-PM2-W1-autorife-LANDED-scorer-redesign-silencetrim-DEFER-suno-apibase.md (read first as next director2).

LANDED + TDD-green (operator2 verifies on resume): **auto-RIFE `65e9b88`** — _maybe_auto_rife wired into _finalize_motion_take, default-on at smoothness<0.4, applies generate_rife_interpolation when recommendation!="regenerate" AND smoothness<threshold; rebinds take[path]+generated_video; new FAL_RIFE $0.04 cost. 8 new + 70 finalize-touching regression tests green, ci_smoke OK. SAFETY: FAL is configured in the dev venv — the recommendation-gate (not a raw threshold) keeps fake/short clips off the real cloud RIFE call. SKILL.md:175 "auto-triggers RIFE" is now TRUE.

DESIGN PASS (wf_e5824fd6-56b, adversarial) changed the plan for the other 3 items:
- scorer §5.1+§5.4: RECONSIDER → redesign to a pixel-energy mouth-motion estimator (smile-cascade rejected: ~20-40% recall, would reject correct lip-sync, worst for Korean). Fold in @coordinator's HELD loud-gate WARNING (lip_sync.py:408) + dup-signal fix + alignment_scorer_enabled gate.
- Suno §5.3: SOUND, but config bug — suno_api_base default https://api.suno.ai/v1 + music.py:198 {base}/api/v1/generate = doubled path → Suno 404s every call. Surfaced to principal.
- silence-trim §5: DEFER (overlay desync unmitigatable without dual-path audio; no benefit until a real scorer). Fix false post-processing.md:214 claim regardless.

@director (Pair-A): ACK your severity correction (10:46:28Z) — landscape brief (task #5) will target phase_c_assembly.py:224 early-return + classify_shot_type + the MAX-tier quality_max.py sibling and cross-ref ADR-025 6aad3b2 for your co-sign. Saw operator's §8.5 ARCHITECTURE note (547cf12) — will coordinate, not duplicate.

2 DECISIONS FOR PRINCIPAL (in handoff): silence-trim DEFER (reverses my own rec); fix suno_api_base default to sunoapi.org. Pod 07ed667 STOPPED. Push USER-gated, nothing pushed.

Cursor at send: 2026-06-13T10:49:18Z
