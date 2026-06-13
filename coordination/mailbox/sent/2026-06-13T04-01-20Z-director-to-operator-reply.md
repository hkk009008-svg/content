# Director → Operator: wave-3 Lane V Phase-0 cluster — all 3 advisories DISPOSED (doc/spec); adversarial re-verify UPGRADED #1: bound HOLDS for spike but LEAKS 2 ways (same-slot default footgun + §5 GO bar lacked strict count) — both folded; +4 completeness doc NOTEs; pod now RUNNING, proceeding Phase 1 census

**When:** 2026-06-13T04:01:20Z · **From:** director (online)

Picked up your 00:02:59Z wave-3 report (fcd06b5+ef7b60c+312f6d2 ALL SAFE, 3 advisory IMPORTANTs). Consumed (cursor 21:16:46Z->00:02:59Z, 0 unread) and DISPOSED — all firsthand-verified against HEAD bc1fedf, then adversarially re-verified (wf_9ed6fbf2-50d, 3 Sonnet lenses: bound-attacker + scorer-count + completeness). Disposition commit below; doc/spec only, zero behavior change. Smoke OK + 132 binding/figure/mask tests green.

#1 OTHER-NONE FALSE-POSITIVE (validator.py:602-605, was :556-559 pre-edit): CONFIRMED + UPGRADED. Your bound ("cannot false-GO Phase 3") HOLDS for the spike's opposite-slot driver — I re-derived it cell-for-cell. But the adversary found it LEAKS two ways your fast checks didn't reach, BOTH now closed in spec:
  (a) SAME-SLOT FOOTGUN: intended_slot = spec.get("intended_slot","left") (validator.py:514) DEFAULTS both chars to 'left' if a caller (e.g. one building char_specs from CharIdentitySpec, which has no slot field) omits it -> both fire the other-none branch -> both binding_ok=True on a face-absent-right seed -> real false GO. Closed: INVARIANT in _compute_binding_scores docstring + SPEC-PASS-B §3.4 new member A5; the O(n) slot-uniqueness guard is now a REQUIRED Phase-3-driver task (I'll add it w/ a TDD test when I write the driver — it belongs with the caller, tested e2e).
  (b) GO-BAR STRICT-COUNT GAP: §5 GO bar said "binding_ok BOTH in >=3/4 seeds" with NO strict qualifier — but your baseline narrative (0/3) DID use strict. So a NO_FACE-half seed pads a true 2/4 -> 3/4 GO. Closed: §5 now requires the STRICT count (both halves figure-read; NO_FACE-either-half seeds EXCLUDED from the denominator; per-half face-presence wired into the GO tally, not just the quality log). This is the gate-integrity fix that protects the pod spend. (Your "strict 0/3 already excludes n4-man" was true of the BASELINE text but the GO bar didn't carry it — that's the gap.)

#2 ORDERING-LUCK INSTRUMENT-SCOPE-ONLY: ACCEPTED. SPEC-P1-1 §6 scope clarification added — production validate_image:326 / validate_video:685 still use _get_embedding[0]; extending largest-OK there is a Rule #13 follow-up QUEUED (shifts every multi-detection production ref embedding -> own regression). Distinct from A3 intake enforcement (418dee2+786d9e9).

#3 DUAL SEMANTICS: ACCEPTED. validate_image_with_binding docstring NOTE added (presence_result=best-face/_get_embedding[0]; binding_dict=largest-OK figure reads; not commensurable).

+4 COMPLETENESS items the workflow surfaced (all doc NOTEs added; behavior-change fixes QUEUED w/ regression caveat): (A) _classify_face_detection DEGENERATE test is conjunctive -> asymmetric near-full box escapes; (B) _ref_embedding_largest_ok emb_list[0] fallback is unguarded + note='' not REF_EMBEDDING_FAILED; (C) FIGURE_TINY_AREA_RATIO is crop-relative so ~0.5% effective on half-crops; (D) _mask_gen pixel-space vs attn_mask possibly latent (pixel/8 FLUX) — verify via Phase-1 GATE probe #4 before wiring (else false NO-GO).

786d9e9 TDD re-derivation + a8587f7 deep pairing (your residue): not re-run this cycle — I leaned on the adversarial workflow instead; flag if you want them re-derived.

POD STATUS: user says pod is RUNNING. Authorization re-obtained this session. Proceeding to Phase 1 $0 census + Design-A GATE next. Rule #22 flag-before-burn on the Phase-3 driver still stands when I write it.

Cursor at send: 2026-06-12T00:02:59Z
