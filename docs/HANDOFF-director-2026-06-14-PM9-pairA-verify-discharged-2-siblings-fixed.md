# HANDOFF — Director (Pair-A), 2026-06-14 PM9

**READ FIRST AS PAIR-A DIRECTOR.** Supersedes PM8. Resumed ("continue as
director1", ultracode) into the converged post-PM8 state during a live 4-seat
nan-gate hardening surge. Discharged the owed implementer≠verifier debt (via an
independent verification workflow, convergent with operator-1's own GO), fixed
the 2 sibling holes that verify surfaced, re-scoped a stale xfail landmine, and
stopped the idle pod. Three commits + coordination. Carries below.

## TL;DR
- **`5b6595e` — xfail landmine re-scoped → HOLD decision-pin.**
  `test_max_wide_pulid_startat_gap.py` was a `strict=True` xfail asserting MAX-wide
  `pulid_start_at` SHOULD be 0.0. operator-1's `f1d7b2d` A/B burn **disproved** that
  premise (0.20 scored higher; all renders over-cooked → ArcFace unreliable). A strict
  xfail asserting a disproven target is a landmine — setting wide=0.0 would XPASS →
  CI-failure read as "fix landed," *rewarding* a measurement-contradicted change.
  Rewrote as a passing pin of the deliberate 0.20 HOLD (3 pass, 0 xfail/xpass).
- **Owed verify DISCHARGED, convergently.** I dispatched an independent adversarial
  verification workflow on my own `7b4d377`/`bf1034a` (`wf_7a7dbebf-4e3`: 6 finders —
  fwd/bwd completeness ×2 per file, correctness, test-coupling — + refute pass). In
  parallel **operator-1 ran their own** (`wf_25dce560-524` + mutation battery) → **GO**
  (`fe2e308`, discharges the debt; 2425 full-suite green, 8/8 guards mutation-proven).
  The two passes were complementary (see Convergence below).
- **`a71a533` — fixed the 2 sibling holes my workflow surfaced** (+ 9 ungated ARCH
  anchors). Both same hazard class as 7b4d377, neither a regression:
  1. **phase_c standard-tier img2img nan-gate.** `generate_ai_broll` used a raw
     `max(0.2,min(0.6,float(raw)))` clamp — a NaN (survives project.json via
     `json.load allow_nan`) clamp-lucks to 0.6 → silently overrides denoise into
     BasicScheduler node 17. The MAX-tier twin already had `_clamp_img2img_denoise`
     (7b4d377); this standard-tier sibling was missed. Fix = extract
     **`_resolve_ui_denoise(ctx)`** (isinstance + `math.isfinite`, EXTRACTED so the
     gate is unit-testable per the nit-4 lesson; 11 RED→GREEN, **mutation-proven**:
     strip `math.isfinite` → the 3 non-finite tests go red). Folds in the Rule#13
     `isinstance(continuity_options, dict)` guard the MAX-tier sibling has → also
     closes the `continuity_options=null` AttributeError co-sibling operator-1 flagged.
  2. **`_finite_or` OverflowError consistency** (quality_max + the shared
     cinema/context mirror). Caught `(TypeError, ValueError)` but not `OverflowError`,
     which `float(10**309)` raises — 7b4d377 added OverflowError to
     `_validate_overlay_value` but left `_finite_or` inconsistent. Added it to both
     (kept byte-identical) + 2 mirror tests. LOW reachability (needs a 310-digit JSON
     integer literal, not a NaN token — operator-1 rated it epic-level), but it
     completes 7b4d377's own intent AND operator-1's `aaa40bd` anchor re-sync had
     already locked in my +3 line shift, so reverting would have stranded their anchors.
- **`c4ddd22` — coordination.** GO-banked reply to operator-1; all-fyi to Pair-B re:
  the shared `cinema/context._finite_or` touch; cursor → 05:35:02Z.

## Convergence with operator-1 (the four-seat design paying off)
Two independent verify passes on the same commits, complementary blind spots:
- **My workflow found** (op-1's pass did not headline): phase_c img2img clamp-luck +
  the `_finite_or` OverflowError inconsistency.
- **operator-1 found** (my workflow MISSED): **`pulid_weight/start_at/end_at → node 100`
  unguarded** (`quality_max.py:560-562`) — the HEADLINE hole, project.json-reachable
  (`controller.py:778` `pulid_weight_override` has NO overlay chokepoint →
  `generate_ai_broll_max:1050 params["pulid_weight"]=nan` → node 100 silent identity
  corruption, same profile as the char_lora→700 case 7b4d377 fixed). Pinned `1c6e098`.
- **We CONVERGED independently** on the phase_c img2img hole AND on adding the
  `continuity_options=null` guard. Redundant verification was NOT waste — neither pass
  alone was complete.

## Carry-forwards (the next "import-swap pass" — Pair-A lane)
operator-1 framed these as one coherent pass; I deferred them per their rec (told op-1
in `c4ddd22`; their pins STAY, CI-tracked):
1. **(HEADLINE) `pulid_weight/start_at/end_at → node 100`** — `_inject_identity`
   (`quality_max.py:560-562`) writes `params.get("pulid_weight")` straight into node 100
   with no `_finite_or`. project.json-reachable. **op-1 pin `1c6e098`
   (`test_nangate_siblings_op1_verify.py`, strict=True).** FIX = wrap the 3 node-100
   PuLID params in `_finite_or`; retire the pin (it'll XPASS).
2. **`ws:515` `continuity_options=null` crash** — `get_workflow_params`
   (`workflow_selector.py:515`): `settings.get("continuity_options", {})` returns None on
   present-but-null → `None.get(...)` AttributeError. The Rule#13 twin of the phase_c
   null-guard I just landed. **op-1 pin `1c6e098`.** FIX = `isinstance(_co, dict)` guard.
3. **`phase_c_vision.py:351`** identity-gate-PASS-on-API-error — **operator2-surfaced,
   flagged Pair-A lane, NEEDS PAIR-A CO-SIGN** before/as fixed. Pin `2cec903`
   (`test_lane_silent_gate_siblings_xfail.py`). See [[silent_gate_degradation_bug_class]].
4. **`_finite_or` import-swap** (Carry#4, UNBLOCKED) — `cinema.context._finite_or` is
   circular-safe + now byte-identical (incl. the new OverflowError). Swap quality_max's
   local copy → the import; bundle with #1 per op-1. **Tier-B** (Pair-B no-objection;
   cinema/context is their canonical lane — I FYI'd the OverflowError touch in `c4ddd22`).
5. **(INFO, low-pri)** `cn_pose_strength:692` gate-defeat (NaN defeats `<= 0.001`,
   landscape pose-CN not pruned) — gate-defeat not a node-write; epic backlog.
6. **(Carry#2, DEFERRED — own session)** `has_character` LoRA-only hole — decouple
   `has_face_ref`/`has_char_lora` (~24 sites); xfail-pinned `bad4dbe`.
   See [[has_character_lora_only_hole]].

## State at wrap (trust `git log -1`, not this prose)
- HEAD `82e2762` at wrap (Pair-B still committing); **7 ahead of origin, 0 behind, tree
  CLEAN.** My commits: `5b6595e`, `a71a533`, `c4ddd22`.
- **Push USER-GATED** — held: the 4-seat surge was actively landing commits through the
  session (both operators); push at a quiescent wrap boundary, not mid-surge.
- **Pod STOPPED** (user, via Novita console — the 502 idle-billing is halted; $0). The
  ADR-024 realism burn (the real photoreal lever, dwarfs start_at) stays queued for a
  deliberate supervised pod session. See [[max_wide_pulid_startat_adr025_gap]],
  [[realism_production_plus_char_lora]].
- ci_smoke OK (ARCHITECTURE hard gate green; PROGRAM-MANUAL advisory backlog — my edit
  worsened one existing advisory anchor, `generate_ai_broll` 76→99, not fixed: advisory,
  out of scope, batch-fixable via `--fix`).

## Sharp edges (this session)
- **Verify-before-agree caught a circular import.** The verification workflow's suggested
  fix for the phase_c hole — `from quality_max import _clamp_img2img_denoise` — would have
  created a circular import (`quality_max:61` already imports FROM phase_c_assembly).
  Honored the FINDING, rejected the suggested IMPLEMENTATION (used inline `math.isfinite`
  + extraction instead). Always check the import graph before applying a reviewer's fix.
- **The ungated-anchor blind spot is real and compounds.** ci_smoke gates only same-line
  `symbol (path:N)` def-anchors; constant/usage/range-form anchors (`:35-73`, `:1160-1198`,
  `_SECONDARY_LORA_MAX_STRENGTH`) drift SILENTLY. Adding `import math` (+1 whole file) +
  a helper (+22) shifted ~9 ungated anchors that op-1's gated-only `aaa40bd` couldn't
  catch. They were also ALREADY partially stale at HEAD (never verified) — so don't reason
  by delta; grep each symbol's TRUE current line. I re-synced all 9.
- **Cross-seat anchor entanglement.** operator-1's `aaa40bd` re-synced the 5 gated anchors
  to my UNCOMMITTED working-tree def lines (shared tree) — front-running my commit. This
  LOCKED my +3 OverflowError shift in: reverting it would have stranded op-1's anchors. On
  a shared tree, a peer can commit doc-sync that depends on your uncommitted source.
- **Hot-tree hygiene held.** HEAD moved ~4× mid-session (op-1 ×3, op-2 ×2+). Every commit
  used explicit pathspec; verified each shared file (`cinema/context.py`,
  `test_nan_gate_pairb.py`) carried ONLY my hunks before committing. Pair-B's lipsync WIP
  was never swept. The shared MEMORY.md was concurrently edited by operator2 mid-write
  (re-read + re-applied).
- **Division of labor that emerged:** operator-1 owns VERIFICATION + pinning; director-1
  owns FIXES. op-1 pins the siblings (`1c6e098`), I land the fixes + retire the pins. Clean.
