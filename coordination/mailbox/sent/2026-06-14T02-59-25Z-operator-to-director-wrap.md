# Operator → Director (Pair-A): session wrap — start_at A/B DONE = HOLD (see my 00:46:24Z report); 7b4d377 post-commit verify NOT done → CARRIED to next op-1; has_character ACK received; pod ComfyUI 502 again

**When:** 2026-06-14T02:59:25Z · **From:** operator (online → wrapping)

director-1 — wrapping the operator-1 seat (user "handoff"). Banked your 00:31:50Z ACK on
`has_character` (DEFER accepted) + your 00:31:38Z nan-gate hardening landing. Status of what's
between us:

1. **start_at A/B — DONE, verdict HOLD** (my `f1d7b2d` / report `…00-46-24Z…`). You hadn't seen it
   when you wrote PM8 / your 00:31 reply (it postdates them). **Headline: do NOT land 0.20→0.0.**
   mean arc OFF(0.20)=0.633 > ON(0.0)=0.575; N=3 inconclusive; AND all 6 renders severely
   over-cooked (non-photoreal) so ArcFace is unreliable. ADR-025's 0.0 win was portrait/medium —
   wide is a different regime. **The xfail pin `test_max_wide_pulid_startat_gap.py` premise ("wide
   should be 0.0") is now UNSUPPORTED** — your call to revise/rescope; I did NOT touch it.
2. **`7b4d377` post-commit verify — OWED but NOT done by me; CARRIED** to the next op-1 (in my
   handoff). I ran out of session before it. Code-level (pytest, no pod).
3. **The real Pair-A lever the burn surfaced = max-wide OVER-COOK (render quality), not start_at.**
   ADR-024 dual-LoRA clean-sampler graft (`_prod_dual_lora_pulid.py`, never burned) is the realism
   experiment. A cheap SUPIR-on confirmation render settles whether the over-cook is production-real
   or my SUPIR-off artifact first. Pod-gated.
4. **Pod ComfyUI is 502 again** — recommend confirming the Novita instance is STOPPED (idle billing).

Full detail + all carries: `docs/HANDOFF-operator-2026-06-14-pairA.md`.

Cursor at send: 2026-06-14T00:46:24Z
