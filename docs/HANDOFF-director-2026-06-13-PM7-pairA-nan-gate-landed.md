# HANDOFF — Director (Pair-A), 2026-06-13 PM7

**READ FIRST AS PAIR-A DIRECTOR.** Supersedes PM6 for current state. Resumed
(user "continue as director1", ultracode) into a converged post-PM6 state and
**landed the one open Pair-A item — the quality_max NaN-gate fix** (`a478f5b`).
Coordinated + dispositioned two new operator-1 findings. Carries below.

## TL;DR
- **quality_max NaN-gate LANDED: `a478f5b`.** The triple-verified defect class
  (director2 surfaced `wf_807f5dca` → director-1 analyzed `e7ad1fc`/`wf_a40f46e1`
  → operator-1 verified `f3ec905`/`wf_4b35e7fb`) is fixed. Two layers: write-side
  chokepoint in `_validate_overlay_value` (reject non-finite floats BEFORE the
  clamps) + read-side `_finite_or` guards on `identity_strictness` (registry
  bypass) and the halt/regen reads. 16 RED→green tests; ci_smoke OK.
- **I drove it (not operator-1)** — operator-1 ACK'd my collision notice (`028d94c`)
  and stood down to independent post-commit verifier. implementer≠verifier held via
  subagent role-split (`wf_53583167-640`: 1 TDD implementer + 3 adversarial reviewers).
- **Carry#1 (char-landscape) DISCHARGED** — spot-confirmed `cf32ca3` honored the
  `ef5c4c6` 3-site co-sign exactly (seam + `phase_c_ffmpeg:411` 4K + `:375` guarded-
  broaden audio); §8.5 FIXED (`d680784`). Nothing to redo.
- **Two new operator-1 findings dispositioned** (see Carries 1 & 2 below).

## What I did
1. **Oriented** — smoke OK, read the live nan-gate thread (my `e7ad1fc` + operator-1
   `f3ec905` + director2 `14:08:20Z`), confirmed all 5 defect sites live at HEAD,
   confirmed `controlnet_pose_strength` is schema'd float (so `:144` chokepoint
   covers `:655`). Invoked R-SKILL skills (comfyui-mastery for the ControlNet-prune
   `:655` mechanism; ai-video-gen for the regen_floor = identity-rescue-floor MAJOR).
2. **Orchestrated `wf_53583167-640`** — TDD implementer + 3 distinct-lens adversarial
   reviewers (coverage CONFIRMED_CORRECT; NaN-semantics + regression CORRECT_WITH_NITS).
   Fixed both nits myself before commit: symbol-anchored the test comments (drift-proof)
   + corrected the inf-semantics docstrings (clamp→reject is intentional).
3. **Landed `a478f5b`** with same-commit doc-sync: ARCHITECTURE.md 8 `quality_max.py`
   anchors +16 (my insertions shifted them). **Staged the anchor fix via a HEAD-based
   blob (hash-object + update-index), NOT a file-level pathspec** — so operator-1's 19
   uncommitted "Last verified" footers in the same file were NOT swept (heeded
   operator2's `14:49:40Z` lesson). Commit = exactly 3 files; verified.
4. **Coordinated `ddf412d`** (`director-to-all-fyi`): landing announce + accepted
   operator-1's independent verify + ACK'd director2's `cinema/context.py` `_finite_or`
   home + dispositioned the 2 findings. Cursor → 15:15:10Z.

## The fix (shape, for the record)
- `quality_max.py`: `import math`; `_validate_overlay_value` rejects `typ is float and
  not math.isfinite(v)` BEFORE the `< lo`/`> hi` clamps; `_finite_or(value, default)`
  helper (LOCAL, documented-temporary); `identity_strictness` read + the three
  halt/regen reads wrapped in `_finite_or`. `:655 cn_pose_strength` NOT edited (rides
  the registry via schema:113 + overlay map:968 → covered by the chokepoint; test only).
- Policy: finite-out-of-range stays CLAMPED (UI "99" = "high"); non-finite REJECTED →
  template default (inf no longer clamped-to-hi — intentional, reviewer-blessed).
- `_finite_or` canonical home (director2 `999a249`) = `cinema/context.py`; my local copy
  is the blessed stopgap. **Unification = trivial import-swap** (low-pri, non-blocking).

## Carry-forwards
1. **(Pair-A, PuLID lane, POD-GATED) MAX `wide` `pulid_start_at=0.20`** — operator-1
   VERIFIED finding (`ea068bd`): `workflow_selector:245` is the lone cell ADR-025's
   start_at→0.0 sweep missed; `pulid_max.json` node 100 IS `ApplyPulidFlux` (active),
   so it genuinely delays binding 20% into denoising on every MAX-tier wide shot —
   **undercuts cf32ca3's MAX-tier identity recovery** (char-landscapes route to wide).
   Disposition: ACCEPTED. `0.20→0.0` + annotate, but per **R-MEASURE NOT a blind change**
   — **fold into the owed char-aerial pod re-validation** (same wide/distant-face regime,
   one burn). POD STOPPED → blocked.
2. **(Pair-A, PuLID/identity, design) `has_character`/`quality_max:1006` LoRA-only hole** —
   operator-1 `125be5e` §2: `has_character` keys off `character_image` file-existence
   ONLY, so a LoRA-only / primary-less char's identity stack (incl. node 700) is pruned
   at `_prune_unavailable:386-388` despite a correct "wide" classification. Pre-existing +
   narrow (dual-char safe). **Needs a design pass** (should `has_character` also key off
   LoRA presence?). NOT pod-gated — implementable, but orthogonal to nan-gate.
3. **(Pair-A, pod-gated, unchanged from PM6)** char-aerial pod re-validation (ADR-025;
   R-MEASURE — now ALSO carries the start_at=0.20 burn from Carry#1) + N=4 robustness +
   experiment burn (`_prod_dual_lora_pulid.py`). POD STOPPED, $0.
4. **(low-pri) `_finite_or` unification** → import from `cinema/context.py` once Pair-B
   lands the shared helper there (director2's batch).

## State at wrap
- HEAD moved fast under me (4-seat live): my commits `a478f5b` (nan-gate) + `ddf412d`
  (coord) landed atomically on a shifting HEAD via read-tree-current + HEAD-stability
  guard. **Trust git, not this prose** — `git log -1`.
- ci_smoke OK (PROGRAM-MANUAL advisory drift only — it's advisory; ARCHITECTURE.md hard
  gate CLEAN after my anchor sync). Pod STOPPED ($0). origin push principal-gated (unchanged).
- operator-1 (Pair-A) LIVE, standby as independent post-commit verifier on `a478f5b`
  OR taking the OWED auto-RIFE `65e9b88` cross-verify (their call; Pair-B touch needs
  director2 coordination). operator2 + director2 (Pair-B) LIVE.
- My cursor: 2026-06-13T15:15:10Z.

## Sharp edges (this session)
- **Surgical staging of a shared-WIP doc:** ARCHITECTURE.md had operator-1's uncommitted
  footers; my code change staled 3 hard-gate anchors in it. `git commit -- ARCHITECTURE.md`
  would sweep the footers (file-level). Solution: `git show HEAD:f > /tmp/f` → apply only
  MY edits → `blob=$(git hash-object -w /tmp/f)` → `git update-index --cacheinfo
  100644,$blob,f`. Stages ONLY my hunks (a HEAD-based blob); peer footers stay uncommitted.
  Apply the SAME edits to the working tree too (ci_smoke reads the working tree). **This is
  the non-interactive `git add -p` for a peer-WIP file.**
- **HEAD is a fast-moving target under 4 live seats** — HEAD moved ~5× during my session.
  Every commit: `H1=$(git rev-parse HEAD); git read-tree $H1; <stage>; H2=$(git rev-parse
  HEAD); [ "$H1" = "$H2" ] && commit || abort`. read-tree the CURRENT HEAD (not a cached
  one) or you revert peers' intervening commits — the symptom is a phantom deletion of a
  file present in both HEAD and worktree (a peer's event committed after your stale read-tree).
- **`env -u GIT_INDEX_FILE git diff HEAD` lies** — it consults the stale shared default
  index, not your seat index. A "126 deletions" of a file that's on disk + in HEAD is a
  phantom. Authoritative: `git show --stat <sha>` (commit truth) + `git status --porcelain
  -- <paths>` WITHOUT env -u (your seat index).
- **Pin the index-sync marker before a split stage/commit:** `git rev-parse HEAD >
  .claude/hooks/.last-index-sync-index-director` makes the PostToolUse hook treat your
  staged index as case-B (deliberate) and never read-tree it away between Bash calls.
