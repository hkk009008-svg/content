# HANDOFF — Pair-A Operator, 2026-06-14 (READ FIRST AS PAIR-A OPERATOR)

**TL;DR.** Resumed operator-1 (user "continue as operator1", ultracode) into a LIVE 4-seat
session. Two deliverables landed, both Pair-A image/identity lane:
1. **`has_character` LoRA-only prune hole — re-verified + xfail-pinned + reported; director-1
   ACK'd DEFER** (`bad4dbe`). Upgraded to **LIVE bug, production-reachable** (Rule#12 write-site
   grep). CI now carries it.
2. **MAX-wide `pulid_start_at` 0.20→0.0 — independent R-MEASURE A/B run on the pod → verdict
   HOLD** (`f1d7b2d`). The data does NOT support the change; the burn surfaced that the real
   Pair-A blocker is **render over-cook**, not start_at.

Pod was UP (Novita RTX 6000 Ada, 51 GB) for the burn, **now ComfyUI 502 again** (stopped or
died). HEAD `f1d7b2d` at my last commit (peers landing ~1 commit/min — `git log -1`). 18 unpushed
(push USER-gated). All my commits via explicit pathspec — operator2's §4 WIP never swept.

---

## What I did
1. **Reload/orient.** Live 4-seat; the 176 "dirty" paths were **phantom skip-worktree pollution**
   (4/4 HEAD-blob checks identical). Reseeded `index-operator` from HEAD per coordinator's 23:45
   reload FYI (tree confirmed CLEAN). Caught up the mailbox; cursor 14:49:40Z → 00:46:24Z.
2. **`has_character` LoRA-only hole** (director-1 PM7 Carry#2). Workflow `wf_1e47eeb0-08b` (4
   adversarial Sonnet passes: reachability / call-chain / dual-char+landscape safety / fix-shape).
   - VERDICT: LIVE bug, **production-reachable** — `scripts/_register_aria_lora.py:35` writes
     `char_lora_paths` with zero ref-check; + post-training ref-deletion. `has_character`
     (`quality_max.py:1006`) keys off face-ref ONLY → a LoRA-only shot drops node 700 + early-returns
     `_inject_identity` → trained LoRA silently dropped. **Silent** (ArcFace gate keys off same
     `has_character=False` → no regen). Dual-char SAFE; landscape prune correct; naive fix UNSAFE
     (2 crashes); safe fix = **decouple `has_face_ref`/`has_char_lora`** (~24 sites). +1 narrower
     sibling (LoRA-only secondary w/ missing ref skipped `:1063`).
   - R-VERIFY-TIER(B): **xfail-pinned** `tests/unit/test_has_character_lora_only_hole.py` (3 pass + 1
     strict-xfail). Reported `→` director-1 (`bad4dbe`). **director-1 ACK'd 00:31:50Z: DEFER to a
     focused TDD session ACCEPTED**; +1 sibling folds into the same decouple session.
3. **MAX-wide start_at A/B** (director-1 PM7 Carry#1; he accepted my offer to run the R-MEASURE).
   Instrument `scripts/_max_wide_startat_ab.py` (committed). 6 renders (3 seeds × start_at∈{0.20,0.0}),
   fp16, SUPIR-off, wide params, ref `char_b9c8bcfe9af0`.
   - mean arc **OFF(0.20)=0.633 > ON(0.0)=0.575** (delta −0.058, weakly AGAINST). N=3 per-seed range
     0.45–0.75 >> delta → inconclusive.
   - **VISUAL OVERRIDE** (memory: visual beats embeddings): all 6 renders **severely over-cooked**
     (crystalline/metallic, non-photoreal = structural max-base-graph over-cook hires-901+sampler) →
     ArcFace measured on degraded images = unreliable.
   - Confounds owned: SUPIR-off (non-production-representative), framing came out medium-not-wide.
     ADR-025's 0.0 win was PORTRAIT/MEDIUM (large face); wide is a different regime.
   - VERDICT **HOLD** 0.20→0.0. Report `→` director-1 (`f1d7b2d`, 00:46:24Z). **director-1 has NOT
     seen this yet** (their 00:31 reply + PM8 wrap predate it).

## State at wrap
- HEAD `f1d7b2d`; ci_smoke was GREEN at session start (advisory PROGRAM-MANUAL drift only). Pod
  ComfyUI **502** (was up for the burn ~00:30–00:46). origin/main `fec4e76`; push USER-gated.
- director-1 (Pair-A) landed PM8: nan-gate hardening `7b4d377` (2 must-guard Rule#13 LoRA siblings +
  4 a478f5b nits) + `bf1034a` (workflow_selector overlay siblings). Carry#4 import-swap
  (`quality_max:~194 → from cinema.context import _finite_or`) unblocked by `a812ee4`.
- operator2 (Pair-B) §4 nan-gate WIP live in the shared tree (cinema/context.py, lip_sync.py,
  capability_scorecard.py, controller.py, test_*nan_gate*). NOT mine — don't sweep.

## CARRIES (for the next Pair-A operator)
1. **OWED: independent post-commit verify of `7b4d377`** (director-1's nan-gate hardening —
   primary `char_lora_strength` + secondary `lora_strength` non-finite→LoraLoader guards + 4 nits).
   Code-level (pytest, NO pod). implementer≠verifier. director-1 explicitly owed this (00:31:38Z).
2. **start_at: director-1 OWED awareness the A/B is DONE = HOLD** (my 00:46:24Z report). The next
   director-1 should **NOT land 0.20→0.0**. The xfail pin `test_max_wide_pulid_startat_gap.py`
   premise ("wide should be 0.0") is now **unsupported** — flagged for director-1 to revise/rescope
   (I did NOT change it).
3. **The REAL Pair-A lever = max-wide OVER-COOK (render quality / realism), not start_at.** ADR-024
   dual-LoRA clean-sampler graft (`scripts/_prod_dual_lora_pulid.py`, built/dry-verified, NEVER
   burned) is the experiment that targets photorealism. A cheap **SUPIR-on confirmation render**
   would first settle whether the over-cook is production-real or my SUPIR-off artifact. Pod-gated.
4. **`has_character` decouple** = director-1-backlogged focused TDD session (`has_face_ref` /
   `has_char_lora`, ~24 sites + 3 signatures + 2 test files). +1 secondary sibling folds in.
5. **6 NaN-disabled veto-registration siblings in `cinema/auto_approve.py`** (Pair-A lane,
   operator2-found `wf_2ca5b0ae`, xfail-pinned `a812ee4` / `test_auto_approve_nangate_xfail.py`).
   `NaN > 0 == False` → veto rule never registered → gate silently passes. Fix = `_get_finite`
   chokepoint in `from_project` reusing `cinema/context._finite_or`. Recommended JOINT "auto_approve
   hardening" w/ S2 (`auto_approve.py:502`) — cross-lane, Pair-A co-sign.
6. **POD: confirm the INSTANCE is STOPPED.** It was up (RTX 6000 Ada, ~$0.20 burn for my A/B). Now
   ComfyUI 502 = proxy up / ComfyUI process down — the pod instance MAY still be billing. **Ask the
   user to confirm it's stopped in the Novita console.** SSH is session-scoped + changes on restart.

## Sharp edges (this session)
- **Phantom skip-worktree index** — `git status` showed 176 "dirty" / `git diff HEAD` 133
  "deletions", ALL phantom (worktree byte-identical to HEAD). Trust `diff <(git show HEAD:f) f`,
  not `git status`. Reseed `index-<seat>` from HEAD ONLY when tree confirmed clean (coordinator
  blessed it; seat-local, safe under live peers).
- **Peers land ~1 commit/min** — HEAD moved 325f750→da44739→741d818→6061a85→bad4dbe→…→f1d7b2d
  under me. Explicit-pathspec partial commits (`git commit -m … -- <my paths>`) parent off live
  HEAD + can't sweep peer WIP. `git add` new files first.
- **`logs/` is gitignored** (per-clone scratch) — R-MEASURE satisfied by the COMMITTED harness +
  numbers embedded in the committed report; images/results.md stay local, reproducible via the harness.
- **Visual verdict overrides embeddings** — the start_at arc numbers looked like a clean A/B; the
  renders were over-cooked garbage. Always open the image.

## Verify on resume
`.venv/bin/python scripts/ci_smoke.py`; `git log -1` (HEAD moves fast); `git rev-list --count
origin/main..HEAD`; pod `curl $COMFYUI_SERVER_URL/system_stats`; mailbox cursor `operator.txt`
= 2026-06-14T00:46:24Z. My commits: `bad4dbe` (has_character) + `f1d7b2d` (start_at). Reports:
`…00-10-47Z-operator-to-director-verification-report.md` + `…00-46-24Z-operator-to-director-measurement-report.md`. Workflows: `wf_1e47eeb0-08b`.
