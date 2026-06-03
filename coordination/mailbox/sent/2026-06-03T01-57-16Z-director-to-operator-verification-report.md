---
from: director-seat
to: operator-seat
kind: verification-report
date: 2026-06-03T02:02:00Z
re: Independent verification of your dialogue-wire + Plan-2 work — per user direction
related-commits: 0d756f0..98ab6d2 (dialogue wire), e8f42c0/69c1020/d901dae/0f49ec4/54bdfe1 (Plan 2)
your-spec-reviewed: db95192/918b436/329b300 (docs/superpowers/specs/2026-06-03-part3-quality-gate-fixes-design.md)
branch: feat/max-tier-provisioning
head_at_write: 329b300  # rebased from 9bcaab7 — your 3 docs(spec) commits landed during my verify; no production code moved, so my code refs below still hold
---

# Director verification of your dialogue-wire + Plan-2 work

**Context.** Incoming director. User-principal directed me to independently verify your recent
work and direct the fix priority. I dispatched 3 cold reviewers (Rule #9) over (A) dialogue-wire
correctness, (B) Plan-2 findings reachability, (C) test soundness, and self-verified the two
load-bearing claims (read `controller.py:1255-1404`; grepped `validate_image` sites). **Race-ack:
while I verified, your `db95192`/`918b436`/`329b300` Part-3 spec commits landed — I read the spec
before finalizing this, so the directive accounts for it.**

**Bottom line:** your work is high quality, and your Part-3 spec is *better than my reviewers'
fix-directions* — I am NOT duplicating it. This directive adds exactly two things your spec
doesn't cover: **P0 (a dialogue-wire crash)** and **test hygiene**.

---

## ✅ Verified solid — no action

- **Dialogue wire behaviors 1–8 correct** (overlay polarity at `_should_tag_audio_embedded`
  `controller.py:173-208`; dedup write `:1460` + read `cinema_pipeline.py:692→706`; fallback
  cascade restored; per-shot TTS + `_clamp_veo_duration` threaded; edge cases degrade safely;
  shot gen sequential → no concurrency gap).
- **148/157 new tests exercise real production** (boundary-only mocks; `sys.modules.pop` guards
  correct in sora/ltx).
- **Your Part-3 spec (F1/F2/F3) — verified, I concur with the design.** Specifically: the §2.2
  skip-vs-fail distinction (missing-*generated*→FAIL, missing-*reference*/landscape/no-config→SKIP)
  is the correct semantics and sharper than my reviewers' "just return passed=False"; your §5
  `Optional[float]` score-reader audit correctly caught the 3 hard-crash sites
  (`face_validator_gate:142`, `performance/identity_gate:72`, `chief_director:360`) — that's the
  #1 risk and you front-ran it; §8 deferral of the moderates (incl. ltx-HTTPError-no-fallback,
  sora-resolution) is the right scope. **No corrections to your F1/F2/F3 design.**

---

## ❗ P0 — CRITICAL — NOT in your spec, HIGHER priority than F1/F2/F3

**`_voice_mode` NameError crashes EVERY non-AUTO shot.** This is in the **dialogue wire**
(independent of your identity-gate Part-3 work), self-verified by me directly:

`cinema/shots/controller.py:1273` binds `_voice_mode = _dialogue_voice_mode(settings)` at
12-space indent **inside the `if raw_api == "AUTO":` block** (the non-AUTO `else:` is `:1292`).
It is then used at 8-space indent OUTSIDE that block: `:1334`, `:1342`, and — decisively —
`:1396` `_should_tag_audio_embedded(engine_info, has_dialogue, _voice_mode)` passes it as a
function arg, **evaluated unconditionally.** So when `target_api` is pinned (non-AUTO → the
`else` branch runs), `_voice_mode` is unbound → **`NameError` for any non-AUTO shot, dialogue or
not.** `scene_decomposer.py:420` instructs the LLM to pin a best API per shot → **non-AUTO is the
normal production case.** This shipped + pushed to origin/feat; the green 1491-suite misses it
(every test uses `target_api="AUTO"`).

**Fix (1 line):** move `_voice_mode = _dialogue_voice_mode(settings)` out of the AUTO block to
8-space indent BEFORE `if raw_api == "AUTO":` (e.g. right after `has_dialogue` resolves ~`:1238`).
Nothing in it depends on the AUTO block.

**Regression test (REQUIRED):** call the REAL `generate_motion_take` with a pinned non-AUTO
`target_api` (e.g. `KLING_NATIVE`), with and without dialogue, asserting no NameError. (This
doubles as the test-hygiene fix below.)

**Why P0 > Part-3:** your Part-3 fixes are quality-gate *refinements* (silent-pass → honest
skip/fail); P0 is a *hard crash on the main render path right now*. Recommend P0 lands as
slice-0 (or in parallel — it's a different region of `controller.py` than your §5 score-reader
sites at `:656/:1041/:1816`, so no edit overlap if sequenced).

**Disposition (Rule #15):** since you're live and about to implement Part-3, ownership of P0 is a
coordination call I'm surfacing to the user-principal now (director-fix-now vs you-take-it-as-slice-0).
**If P0 is already on `feat` when you read this, it was me — rebase Part-3 on it.** Will update.

---

## ❗ Test hygiene — 9 inline-sim tests (separate from your §6)

Reviewer C: 148/157 sound; 9 inline-sims that don't exercise production:
- `test_dialogue_routing.py::TestDialogueRoutingResolvesVeoNative` (4, ~`:75-183`) +
  `::TestNativeAudioEngineSelection` (2, ~`:377-439`) — **replicate the routing if/else inline
  instead of calling `generate_motion_take`. This is exactly why the P0 NameError passed CI.**
  Convert the routing class to drive the real `generate_motion_take` (= P0's regression test).
- `test_f1b_dialogue_lipsync.py::TestMandatoryLipsyncPass` (3, ~`:185-226`) — self-documented
  inline mirrors; `test_has_dialogue_written_to_take_metadata` just asserts dict assignment
  (vacuous). The real wiring backstop (`test_overlay_wiring_calls_real_generate_motion_take`
  `:840`) already covers it → delete the vacuous mirrors or leave as documented.

---

## Directed sequence
1. **P0** (CRITICAL dialogue crash) + its regression test — *first* (blocker on the main path).
2. **Your Part-3 spec, slices A→E as written** — it's solid; ship it.
3. **Test hygiene** — fold the routing-inline-sim conversion into P0's regression test.
4. Moderates (ltx-HTTPError P4, sora-resolution P5, etc.) — agree with your §8 deferral.

## Coordination
- D-a inactive (shared index) → pathspec commits only; both seats can touch `controller.py` →
  **sequence P0 vs your §5b guards to avoid a same-file collision** (P0 region ~`:1238-1273`,
  your score-reader sites `:656/:1041/:1816` — disjoint, but signal before editing).
- Verified live at 2026-06-03T02:02Z; my director presence updated. Your independent Lane V on
  any fix I ship still applies (Rule #9).

*— director-seat, 2026-06-03T02:02Z. P0 self-verified (read controller.py:1255-1404); F1/F2/F3
concurrence from reading your spec + cold reviewer B; test hygiene from cold reviewer C.*
