# HANDOFF — Director (Pair-A), 2026-06-13 PM6

**READ FIRST AS PAIR-A DIRECTOR.** Supersedes PM5 for current state. Resumed
(user "continue as director1", ultracode) into a converged post-PM5 state; the one
substantive open Pair-A item was the **char-landscape identity-zeroing fix** (§8.5).
Discharged it as a **Rule#23 co-sign on director2's brief** (not a competing brief),
with a regression-preventing 3-site correction. Wrapped on user "handoff".

## TL;DR
- **Pair-A Rule#23 co-sign DELIVERED** on director2's char-landscape routing brief
  (`27d1323`, `docs/BRIEF-director2-2026-06-13-landscape-char-routing-rule23-joint.md`):
  **GRANTED** land + `wide` target + ADR-025 re-scope. Co-sign commit `ef5c4c6`;
  mailbox verification-report `12:27:54Z` → director2.
- **The fix is 3 SITES, not 1** (my regression-preventing catch — the headline finding).
  director2's seam-only spec + `classify_shot_type` caller-audit structurally missed two
  downstream `shot_type=="landscape"` STRING consumers. director2 must fold them before
  dispatch (see Carry #1).
- **Rule#23 gate is SATISFIED** (both directors co-signed). Ball is in **director2's
  court**: fold the 2 companions + dispatch the 3-site fix to operator2 (implement;
  director2 verifies, implementer≠verifier). **NOT a Pair-A implementation item.**
- **Principal surfaced + did not veto** the shipping-behavior/cost change (char-landscape
  → ComfyUI-PuLID + 4K LTX = higher per-shot cost, restored identity). "handoff" with no
  objection ⇒ **proceed stands**. Recommendation was: land (correctness fix, capability-max).

## What I did
1. **Independent verification first (parallel, unaware director2 was live).** At resume
   all seats showed offline (HEAD `ded3f52`). I verified the §8.5 defect + 5/6-caller
   blast radius against HEAD, then ran `wf_e378821e-04d` (11 mappers + 5 adversarial
   refuters, Sonnet): mapped per-caller post-fix behavior, the 4K/audio side-effects, test
   impact, and the upstream-stored-shot_type / 2nd-classifier completeness question.
2. **Discovered director2 had come online** and already authored the canonical brief,
   HELD pending my co-sign. **Retired my parallel-authored brief** (collision; director2's
   landed first + is the assigned author) and turned my verification into the co-sign
   cross-check — the two-director Rule#23 model working as designed.
3. **Co-sign `ef5c4c6`** (doc/coord-only, pathspec): ARCHITECTURE.md §8.5 → "BRIEF
   AUTHORED + Pair-A co-signed", pointer to director2's brief + the 3-site scope +
   routing-completeness confirmation; + the co-sign verification-report event.

## The co-sign content (the joint record = director2's brief + this)
**CONVERGENCE** (my independent pass agrees with director2): the seam fix
(`classify_shot_type` → return `"wide"` when the landscape bucket matches a char-bearing
shot; their explicit `and chars` guard is correct belt-and-suspenders — line-434
early-return makes `chars` provably non-empty at the keyword loop, so it's redundant but
harmless); `wide` target (3 independent reasons); and **single-seam ROUTING-completeness
CONFIRMED** — no 2nd classifier produces the defect (`scene_decomposer` writes no
`shot_type`; `_heuristic_shot_type` prompt_optimizer.py:161 returns landscape only when
`not has_chars`; `optimizer_cache["spec"]["shot_type"]` is a dead store for routing). The
3 Pair-A callers verified **beneficial**: `continuity_engine.py:528` (0.0→0.55 +
adaptive weight), `performance.py:52` (char-landscape+dialogue → `ENGINE_ACT_ONE` — this
**RESTORES** silently-skipped lip-sync, a real capability gain), `quality_max.py:901`
(max wide template 0.65/lora 0.9 + best-of-N rescue re-armed).

**THE CORRECTION — fix is 3 sites, not 1** (verified vs source). director2's §4 Rule#23
audit greps `classify_shot_type(` *callers* — which cannot see two downstream consumers
that branch on the result STRING:
- **4K — `phase_c_ffmpeg.py:411`**: `ltx_resolution = "4k" if shot_type == "landscape"
  else "1080p"` → char-landscape→`wide` drops 4K→1080p (4× pixel loss; no auto-upscale,
  SeedVR2 is user-initiated). Companion: `in ("landscape","wide")` — also aligns code with
  the documented wide=LTX-4K intent. **Recommend LAND** (low risk).
- **Audio — `phase_c_ffmpeg.py:375`**: `generate_audio=(shot_type == "landscape" or
  dialogue_native_audio)` → char-landscape→`wide`, no-dialogue, overlay-mode, VEO_NATIVE
  ⇒ silent clip (lost ambient; no scene-TTS for a no-dialogue scene). **director2's
  Pair-B call** — caution: blanket-broadening to `wide` adds Veo ambient to genuine wide
  shots and risks Veo-ambient + overlay-TTS double-audio on genuine wide+overlay-dialogue.
  Recommend guarded broaden OR accept+document the narrow silent-clip regression.

Both are the exact regressions director2's **own** W1 §3b flagged ("silenced
generate_audio + lost LTX-4K") but that didn't carry into `27d1323`.

**Test note** (added to director2's §6): it's not just a new RED test — the existing
parametrized `tests/unit/test_workflow_selector.py:177-191` has all 8 landscape keywords
on char-bearing shots asserting `"landscape"`; those **BREAK** → update to `"wide"`. Plus
a companion-1 assertion (LTX path shot_type="wide" → resolution="4k").

## Carry-forwards
1. **(Pair-B, active) char-landscape 3-site fix** — director2 folds the 2 companions
   (`phase_c_ffmpeg.py:411` + `:375`) into `27d1323` + dispatches to operator2. operator2
   implements all 3 sites (or seam + 4K-companion and explicitly accept/document the audio
   regression with a tracked follow-up). director2 verifies. **My co-sign is the only
   Pair-A gate and it's cleared.** Soft Pair-A interest: a next Pair-A director may want to
   spot-confirm the landed implementation honored the 3-site spec (esp. the companions) +
   that §8.5 gets marked FIXED + ADR-025 exemption closed at landing.
2. **(Pair-A, pod-gated) char-aerial pod re-validation** — the fix re-engages PuLID on a
   path the Task-4 gate didn't exercise. ADR-025 binding numbers owe a char-aerial
   Linux/TBB pod re-confirm (R-MEASURE: don't assert an unmeasured binding). **POD STOPPED
   → blocked**; not a code-landing blocker. Re-ask user to START pod + re-confirm SSH.
3. **(Pair-A, pod-gated) N=4 robustness** (`scripts/_prod_pulid_acceptance.py --n 4`) +
   **experiment burn** (`_prod_dual_lora_pulid.py`) — unchanged from PM5; pod-gated.
4. **(Pair-B, NOT my lane, FYI)** auto-RIFE secondary defects landed (`0d632eb`); operator
   surfaced 2 NEW audio-loss siblings of the RIFE class (`upscale_video_seedvr2` /
   `face_swap_video_frames`) — Pair-B in flight. 2 standing director2 principal-decisions
   open (silence-trim DEFER, suno_api_base malformed).

## State at wrap
- HEAD `ef5c4c6` (mine; **will move under you** — Pair-B live). origin/main was PUBLIC at
  `ded3f52` (coordinator's principal-directed push); local main is now AHEAD with the live
  4-seat stack — **push is principal-gated**. Trust git, not prose.
- ci_smoke OK (at session start; my commit was doc/coord-only, no code). **Did NOT run
  pytest** against the live shared tree (operator2 in-flight in controller.py — standing
  "no pytest on a dirty shared tree" rule).
- Pod STOPPED ($0 this seat). director cursor `12:00:27Z` (0 unread at consume).
- Live seats at wrap: director2 + operator2 (Pair-B). operator (Pair-A) was offline.

## Sharp edges (this session)
- **Parallel-seat brief collision is real.** I and director2 both authored a landscape
  brief unaware of each other (they were offline at my resume, came online mid-session).
  Resolution: git tiebreaker (theirs landed first) + assigned-author → I retired mine and
  co-signed theirs. **`git log -1` before assuming you're the only seat; re-check after any
  long background workflow** (HEAD moved 4× under me: `ded3f52`→`e64e2bf`→`24e7c0e`→
  `a10986c`→`0d632eb`).
- **Per-seat index cross-staging on a live tree.** `git diff --cached --name-only` showed
  peer WIP staged in my `index-director` (`controller.py`, `test_auto_rife_finalize.py`,
  `operator.txt`, an operator event). A bare `git commit` would have swept them.
  **Explicit-pathspec commit is the safety primitive** — `git commit -m "…" -- <my paths>`
  builds a fresh temp index from HEAD, commits only the named paths, sweeps nothing.
  `git show --stat HEAD` after to confirm scope (mine: exactly 3 files).
- **Methodology diversity caught the gap.** director2 audited classifier *callers*; I
  traced result-STRING *consumers* (`grep 'shot_type == "landscape"'`). A reroute fix needs
  BOTH axes — re-point the classification AND re-key everyone who matched the old label.
  Single-axis audit is how a "1-line fix" ships 2 regressions.
