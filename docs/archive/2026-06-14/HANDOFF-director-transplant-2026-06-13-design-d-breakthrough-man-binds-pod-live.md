# Director transplant handoff — 2026-06-13: DESIGN D BREAKTHROUGH (the man finally BINDS, 0.870, via his LoRA) after Design A NO-GO — pod LIVE + BILLING, operator ONLINE (two seats)

**Supersedes** `docs/HANDOFF-director-transplant-2026-06-12-p2-arc-complete-passb-phase0-complete-pod-gate.md`
(its ⭐#1 fully discharged: pod started by user → Phase-1 census + Design-A GATE
run → Design A NO-GO → Design D breakthrough this session).

## Ground truth (verified at wrap, 2026-06-13T05:16Z UTC)

- **HEAD `c9c778e`, 24 ahead of origin (25 after this handoff commit).** Push
  USER-gated as always.
- **Smoke OK + ARCHITECTURE doc-gate GREEN** at `c9c778e` (the `6ff245d` +13
  drift fixed this commit). PROGRAM-MANUAL carries ~54 ADVISORY drifts (fix-on-touch).
- **Suite: NOT re-counted this session** (label UNVERIFIED). Was 2236/0 at
  `a8587f7`; operator added `6ff245d` bug_001 TDD test + `146de8c` verifier-ext
  (+6) since. Re-count before claiming a number.
- **Mailbox: director cursor `2026-06-13T04:53:22Z`, 0 unread.** Reply event
  `05:15:48Z` sent (rides this commit). **OPERATOR IS ONLINE** (two seats live
  all session — see the lesson below).
- **POD 07ed667 RUNNING + ComfyUI UP + BILLING.** User started it ("pod is
  running") + authorized the test ("proceed with the pod test") + the spend
  ("spend") + chose Design D ("D"). ComfyUI restarted by me (PID 343);
  gateway/local `/system_stats` 200. **The pod bills until the user stops it in
  the Novita console** — flag this to the user at pickup. Both char LoRAs intact.

## ⭐ #1 PICKUP — DESIGN D is the live frontier (the man binds; finish it)

**The hard problem is SOLVED: the secondary character (man) now BINDS at 0.870**
(Design D = man LoRA `char_lora_man_v1` @0.55 + dual PuLID; driver
`scripts/_max_passBd_lora_pulid.py`; N=1 smoke `logs/passb_d_n1.jpg`). Across
Pass-A (0.487) / S2 (0/4) / Design-A (0.45) the man never bound on PuLID-alone;
his trained LoRA was the missing piece. Two DISTINCT identities, separate halves
(LEFT man 0.870/aria 0.476; RIGHT aria 0.763/man 0.507). **Two tractable
caveats remain — both SEPARATE axes from binding:**

a. **Placement SWAPPED** (man-left/aria-right vs the prompt's woman-left/man-right)
   → strict intended-slot binding_ok reads 0/1 EVEN THOUGH both bound distinctly.
   The GO bar measures placement-correctness, a different axis from "does the
   secondary bind." **KEY INSIGHT (convergent with operator):** now that the man
   BINDS, the attn_mask (proven FUNCTIONAL by operator `d569edd` — it perturbs
   the render, it just couldn't rescue a non-binding identity) can finally do
   its spatial job. **Design D + masking is the untested combo that could solve
   BOTH binding AND placement.** Try it next. Cheaper first probes: prompt order
   swap (man-first), or seed selection.
b. **Visual OVER-COOKED** (crusty max-tier skin, no crisp grey beard) — the
   documented max-tier over-cook (`realism_production_plus_char_lora`: production
   tier + char LoRA @0.55 = realism). Test the PRODUCTION tier (`pulid.json`)
   for quality once binding+placement hold.

**Sequence:** (1) fix placement (Design D + masks, OR prompt/seed) at N=1; (2)
when man binds on his INTENDED half at N=1, scale to N=4 (the real GO bar:
binding_ok BOTH ≥3/4 STRICT seeds + VISUAL); (3) production-tier quality pass.
Operator's complementary lever (their `d569edd`): asymmetric weights (aria ~0.6 /
man ~1.1) and/or a PHOTOREAL man ref (the current `p12_fresh_face_man.jpg` is
painterly → weak InsightFace embedding) — combine with the LoRA for max binding.
**Rule #22: flag the next render driver to the operator BEFORE burn — they are
ONLINE and armed** (don't repeat my solo-review lapse below). Spend is
USER-gated each time; ~$0.03/N=1 smoke, ~$0.10/N=4. Show every render in Preview.

## What landed this session (director seat, chronological)

1. **Wave-3 Lane V disposition (`d3060c4`)** — operator's 00:02:59Z 3 advisories
   verified firsthand + adversarially (`wf_9ed6fbf2-50d`, 3 Sonnet lenses).
   UPGRADED #1: bound HOLDS for the spike but LEAKS via the `intended_slot='left'`
   same-slot footgun + the §5 GO bar lacked the strict qualifier its baseline
   used → **§5 STRICT-count gate-integrity fix** + §3.4 A5 + 4 completeness NOTEs.
2. **Phase-1 census + Design-A GATE (`ea2eaee`)** — GATE = GO via
   `ApplyPulidFlux.attn_mask`: the PRODUCTION node HAS attn_mask (spec premise
   "ApplyPulidFlux has no attn_mask" REFUTED); `ApplyPulidAdvanced` is SDXL-era
   `PULID`, not the route. Committed instrument `scripts/_passb_census.py`
   (R-MEASURE), 1106 classes, both LoRAs intact.
3. **Design A = NO-GO (`dab5f37`, mechanism CORRECTED `c9c778e`)** — masked
   dual-PuLID via `ApplyPulidFlux.attn_mask`. Driver
   `scripts/_max_passBa_masked_pulid.py` (self-reviewed money-path; operator's
   independent Rule #22 verdict `4748608` = SAFE, converged). N=1 ×2 (default +
   `--swap`, ~$0.06). **My first read "attn_mask swap-invariant/inert" was WRONG
   — operator `d569edd` pulled the pod `/history`: the two runs gave DIFFERENT
   outputs, masks ARE functional; the man-absent outcome is mask-INDEPENDENT
   (blocker upstream: man painterly-ref PuLID overwhelmed by aria).** Corrected.
4. **Design D = BREAKTHROUGH (`eb2a3f2`)** — see ⭐#1. Reuses the parameterized
   `render_leg(save_prefix)`.
5. **Operator-correction fold (`c9c778e`)** — Design-A mechanism + C7/C8/C4
   spec-accuracy (man-reads range 0.466→0.728 w/ the n1-left binding SWAP;
   5-not-4 NO_FACE crops; ef7b60c 18-not-28 tests) + ARCHITECTURE drift from
   their `6ff245d`.

## Two-seat state at wrap — READ THIS LESSON

**THE OPERATOR WAS ONLINE THE ENTIRE SESSION AND I WAS BLIND TO IT.** I started
with presence reading them OFFLINE (true at session start) and never re-checked:
I committed to `main` with explicit pathspecs but did NOT `git log` between
commits, so I missed their 6 events (04:03–04:53Z) AND their 5 interleaved
commits (`7ee734d 146de8c 6ff245d d41ee5b 4748608` ... `818cdb8 d569edd`) until
ci_smoke went red on their `6ff245d` drift. **Lesson for the next director:
`git log --oneline -5` BEFORE every commit on a shared tree, and re-read the
peer's presence `updated:` timestamp — presence is a snapshot; a peer comes
ONLINE mid-session (this is memoried, and I still missed it).** The operator
handled it gracefully (deconflicted by file: they stayed out of SPEC-PASS-B/
SPEC-P1-1 which I owned; took web_server.py/bug_001 + the verifier-ext). All
their events are now consumed + disposed (reply `05:15:48Z`). Operator's open
standby: verify the Design D render + any N=4; their asym-weights/better-ref
lever complements Design D.

## Director backlog (carried + new)

Design D placement (masks-now-that-man-binds / prompt order / seed) · production-tier
quality pass · asym-weights + LoRA combo · A5 slot-uniqueness guard + TDD (queued
to the production binding wiring, NOT the spike — operator confirmed N/A to the
driver) · operator's 2 driver advisories (idempotency guard, `/object_info`
raise_for_status) · suite re-count · operator's bug_001 (`6ff245d`) is THEIRS,
landed · P2-2 pod idle guardrails (pod live again) · the carried P2/spec debts
from the prior handoff.

## Operational notes (this session)

- **Pod money-path drivers are sound** (S2 lineage): `_submit` rejected-graph
  guard fails $0 before /prompt; all timeouts; err_streak≥6 OOM NO-GO;
  empty-outputs fail. Reuse `render_leg(save_prefix=...)` from
  `_max_passBa_masked_pulid.py` for new render legs.
- **attn_mask polarity/coord-space (probe #4) is moot for binding** — masks are
  functional but can't rescue a non-binding identity; resolve polarity only
  AFTER the man binds (Design D) and you're using masks for PLACEMENT.
- **Best-of-N + SUPIR max-tier render ≈ 7–8.5 min/seed, peak VRAM 32–42 GiB**
  (LoRA adds ~8 GiB). Run render legs in the background (Bash `run_in_background`)
  — the 10-min foreground cap is below a single render.
- **logs/ is gitignored** — commit the INSTRUMENT (R-MEASURE), cite the
  regeneration command for the artifact.

*Last verified: 2026-06-13T05:16Z UTC — smoke OK + ARCHITECTURE gate green at
c9c778e; cursor 04:53:22Z 0 unread; pod RUNNING+BILLING; operator ONLINE.*
