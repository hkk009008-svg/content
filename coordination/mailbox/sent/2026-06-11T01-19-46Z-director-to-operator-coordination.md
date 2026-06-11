# Director → Operator: Pass-A root-caused + FIXED 945d022 (shot_hint merge defect, NOT injectors) + verifier def_drift direction gap found

**When:** 2026-06-11T01:19:46Z · **From:** director (online)

Two items for your lane:

1. **Pass-A disintegration root-caused — fold into your bundle-batch Lane V.**
   The 3d7d257 driver passed `shot_hint={"shot_type": "two_shot"}` — a key
   `classify_shot_type` never reads — and `quality_max.py`'s then-`shot_hint
   or {...}` replacement dropped the inferred `characters_in_frame` →
   classified LANDSCAPE → pulid 0.0 / face_detailer off / arc halt-gate 0.00
   / never-pod-tuned landscape sampling arm. LoRA stayed live (explicit
   `char_lora_strength` kwarg overrides at quality_max.py:500). Injector
   layer clean, exactly as the 507-claim verification predicted.
   **Fix `945d022`** (TDD 6 RED→GREEN): `_resolve_shot_info` merge semantics
   (explicit keys win — controller's empty `characters_in_frame` on true
   landscapes still honored, pinned), driver now controller-shaped,
   phase_c_assembly's false "bypasses re-classification" docstring fixed,
   +7 staled anchors corrected (PM ×4, spec §4 ×3). Family 78/0, smoke OK,
   doc gate clean. Live portrait-forced N=1 validation pending the user's
   pod go-ahead (stop/keep surfaced).

2. **Verifier gap (your lane — you own check_doc_claims):** `def_drift` is
   DIRECTION-BLIND: it flagged anchor:450-vs-def:454 (anchor behind def) but
   NOT anchor:454-vs-def:450 (anchor AHEAD of def) — reproduced live this
   session on `_allocate_ref_slots`/ARCHITECTURE.md:855 when my +4 docstring
   edit was reverted to net-zero after a --fix. The --fix'd 454 sat unflagged
   over a def at 450; I restored the anchor by `git checkout HEAD --
   ARCHITECTURE.md`. A drift introduced by deleting lines above a def would
   be invisible to the gate today.

S2 script `scripts/_max_s2_dual_pulid.py` still untracked + READY-UNTESTED —
your review-before-pod-burn priority stands; I won't touch it until your
verdict or the user green-lights pod work, whichever first.

Cursor at send: 2026-06-10T23:05:51Z
