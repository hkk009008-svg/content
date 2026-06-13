# HANDOFF — Director (Pair-A), 2026-06-13 PM5

**READ FIRST AS PAIR-A DIRECTOR.** Supersedes PM4 for current state. Resumed
(user "continue as director1", ultracode) into a **converged, post-Step-5** state;
wrapped after formalizing the §8.5 co-sign. **No actionable Pair-A work remained** at
wrap — everything else is pod-gated or another seat's lane.

## TL;DR
- **§8.5 char-landscape known-defect co-sign = FORMALIZED + QUADRUPLE-VERIFIED + CLOSED.**
  The one open thread addressed to me (operator's 10:55:32Z request to co-sign the
  note `547cf12`) is resolved.
- Step-5 (production PuLID SDXL→FLUX fix) was already **COMPLETE + LANDED + public**
  before this session (`6aad3b2`, ADR-025, Task-4 OFF 0.6205 → ON 0.8779). Untouched.
- **origin/main is PUBLIC** — the principal directed the coordinator to push the whole
  2026-06-13 stack. The `1b94dd7` co-sign is public. "push USER-gated / nothing pushed"
  lines in older docs/MEMORY are **STALE — trust git.**
- **Pod 07ed667 STOPPED** (billing closed, $0). N=4 / experiment burns blocked-on-restart.

## What I did
1. **`1b94dd7` — §8.5 co-sign formalized (doc-only, ci_smoke OK).** Independently
   re-verified all 6 load-bearing claims (my own source reads + a 12-agent adversarial
   workflow `wf_73f95c8c-615`: 6 verify + 6 refute — all CONFIRMED, all survived refute).
   Folded 3 *verified* refinements the note was missing:
   - **C1 dict-order scope bound** — `classify_shot_type` keyword scan is dict-order
     first-match-wins (portrait→action→wide→landscape→medium), so the mis-route fires
     **only when no portrait/action/wide keyword precedes** the landscape keyword
     (e.g. "drone tracking shot" → `action`). Bounds the defect so a future fix doesn't
     over-scope it. (This was the one genuine gap — the headline behavior was right but
     the boundary was unstated.)
   - Completed the landscape keyword set to all 8 (`+landscape`, `+no character`).
   - Hardened the regen-floor anchor chain: retry → `needs_regenerate`
     (`face_validator_gate.py:326`) → `arc_score < floor` (`:341`); the `has_character`
     guard (`:337`) passes for a char-bearing shot, so the `0.0` floor — not the guard —
     is the operative kill.
2. **`42f008b` — coordination:** fold-notice→operator (co-sign + the folds) + all-fyi
   (flagged the Pair-A blast radius for the joint brief) + cursor → 11:25:01Z (0 unread).

## Quadruple convergence (the diagnosis is locked)
Four independent adversarial passes, **zero corrections** between them:
operator-1's original 6-way refute · my `wf_73f95c8c-615` · coordinator's `wf_5d39bbe3`
(7-agent, also mapped the blast radius) · operator's `wf_e09bded6-3de` (6-agent, on
resume). The operator independently surfaced the **same** dict-order detail I folded,
hardened the same anchors in the working tree but **committed nothing** (caught the
`e61ab10→6e733ae→1b94dd7→b922aa9→4c3b64f` HEAD moves, unstaged before a conflicting
commit) — clean four-seat convergence, no duplicate head. `git diff HEAD -- ARCHITECTURE.md`
== EMPTY. Operator CLOSED their side.

## Carry-forwards (none actionable by me at wrap)
1. **JOINT landscape FIX brief** — director2 task #5 (AUTHOR), **my Rule#23 co-sign**,
   operator2 implement. DEFERRED to next Pair-B resume; cross-ref ADR-025/`6aad3b2`.
   ⚠ **Blast radius = 5 `classify_shot_type` callers across BOTH pairs** (coordinator
   `wf_5d39bbe3` / findings `b922aa9`) — NOT just the video-API one §8.5 nods to. **2 are
   PAIR-A lane and need MY-seat co-sign**, so the brief can't be Pair-B-solo:
   - `continuity_engine.py:528` (Pair-A) — `get_threshold_for_shot` identity_threshold
     0.0 (no-op) → 0.55 (ENFORCED). **I verified the caller is shot_type-driven.**
   - `performance.py:52` (Pair-A) — dialogue char-landscape `should_capture` → True.
   - (Pair-B/diagnostic): `controller.py:1421` video_fallbacks +RUNWAY_GEN4 (target_api
     stays LTX — the reroute's video-API delta is ~nil; convergent with my LTX/LTX note);
     `motion_render.py:265` advisory floor; `calibrate_motion_floor.py:63` CSV label.
   - Caveats for the brief: production LoRA-only edge (character_image absent →
     characters_in_frame=[] → still routes landscape, early-return won't fire);
     `char_lora_strength` override (`quality_max.py:500`) partially escapes LoRA-zeroing
     on max → §8.5's "both zero" is exact for PuLID, slightly strong for LoRA-when-set
     (already noted in §8.5's last bullet).
2. **auto-RIFE `65e9b88`** (default-on, W1 §5.2) — now PUBLIC but operator2's formal
   cross-verify is still **OWED on a pushed commit** (Pair-B next resume). NOT my lane.
3. **N=4 robustness** (`scripts/_prod_pulid_acceptance.py --n 4`) + **experiment burn**
   (`_prod_dual_lora_pulid.py`) — pod+spend-gated; **POD STOPPED → blocked.** Step-5 GO
   does not need them. A future pod task must re-ask the user to START the pod +
   re-confirm SSH (session-scoped).

## State at wrap
- HEAD `42f008b`. **2 commits ahead of origin/main** (operator report `6d1c1ef` + my
  `42f008b` — both coordination bookkeeping; the substantive `1b94dd7` is already public).
  Push of these 2 surfaced to the user, not self-pushed.
- ci_smoke OK (58 advisory PROGRAM-MANUAL doc-anchor drifts — standing non-gating).
  Coordination clean (director 0 unread). director2/operator2/coordinator OFFLINE;
  operator converged. Pod STOPPED, $0.

## Sharp edges (this session)
- **Pathspec partial-commit is the safety primitive on a live shared tree.** HEAD moved
  under me 5+ times (peers committing). `git commit -m "…" -- <path>` builds a fresh temp
  index from current HEAD and commits ONLY that path → can't revert peer commits or sweep
  peer WIP regardless of a stale per-seat index. `git log -1` immediately before every
  commit; `git show --stat HEAD` immediately after to confirm scope.
- **`git status` lies for the director seat** — `index-director` goes stale the moment a
  peer commits. Truth = `git diff --quiet HEAD -- <f>` / `git cat-file -e HEAD:<f>` /
  `git diff HEAD --stat`; reseed with `git read-tree HEAD` (safe — own index only).
  Files can show as BOTH staged-deleted and `??` untracked simultaneously — pure phantom.
- **`coordination/presence/` is gitignored** (per-clone runtime, like STATE.md) — never
  commit it. `consume-events <role>` is the ONLY sanctioned cursor writer (it stages,
  never commits; refuses regressions). `send-event` writes+stages events; `coordinator`
  is a send-only pseudo-seat (valid `<from>`, never `<to>`).
