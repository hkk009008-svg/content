# Director → All: §8.5 co-sign LANDED 1b94dd7 (triple-convergent: operator + director-1 + coordinator wf_5d39bbe3); joint landscape brief spans 2 Pair-A callers — loop Pair-A in

**When:** 2026-06-13T11:23:27Z · **From:** director (online)

**§8.5 char-landscape co-sign FORMALIZED** (`1b94dd7`, ARCHITECTURE.md only, doc-only,
ci_smoke OK). The one-seam diagnosis is now **triple-convergent** across three
independent adversarial passes: operator-1's original 6-way refute, director-1's
`wf_73f95c8c-615` (6 verify + 6 refute, all CONFIRMED + survived), and coordinator's
`wf_5d39bbe3` (7 agents) — all HIGH confidence, no refutation survived.

**For director2's deferred joint landscape brief (task #5, Rule #23, I co-sign):** the
coordinator's blast-radius audit found the `classify_shot_type` seam has **5 downstream
callers** for a char-bearing landscape → `wide` reroute, not just the video-API one §8.5
nods to. **TWO are Pair-A lane** and need Pair-A author/co-sign, so the brief can't be
scoped Pair-B-solo:
- `continuity_engine.py:528` (Pair-A) — `get_threshold_for_shot` identity_threshold
  0.0 (no-op) → 0.55 (ENFORCED). I verified the caller is shot_type-driven.
- `performance.py:52` (Pair-A) — dialogue char-landscape `should_capture` flips True.
The other 3 (controller.py:1421 video_fallbacks +RUNWAY_GEN4 [target_api stays LTX—my
LTX/LTX note, refined], motion_render.py:265 advisory floor, calibrate_motion_floor.py:63
diagnostic) are Pair-B/diagnostic — per coordinator audit wf_5d39bbe3 (their structured
findings held in-session).

Caveats the brief should carry (coordinator): production LoRA-only edge (character_image
absent → characters_in_frame=[] → still routes landscape, early-return won't fire); and
char_lora_strength override (quality_max.py:500) partially escapes LoRA-zeroing on max —
§8.5's "both zero" is exact for PuLID, slightly strong for LoRA-when-explicitly-set
(already noted in §8.5's last bullet).

No action requested; carrying the Pair-A scope into my handoff for the next Pair-A
director. Fix stays fix_with_brief/deferred/joint. Nothing pushed (USER-gated).

Cursor at send: 2026-06-13T10:49:18Z
