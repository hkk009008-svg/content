# HANDOFF — Pair-A Operator, 2026-06-13 PM5 wrap (READ FIRST AS PAIR-A OPERATOR)

**TL;DR:** Resumed operator-1 into a *converged* Step-5 state that turned into a live
5-seat session. Independently re-verified the §8.5 char-landscape known-defect (6-way
adversarial, all CONFIRMED), hardened its source anchors (absorbed into director-1's
`1b94dd7` via the shared tree), reported (`6d1c1ef`). §8.5 is now **triple/quadruple-
convergent and CLOSED**. The whole 2026-06-13 stack is **PUBLIC** (principal pushed).
**Nothing pending in the Pair-A lane.** Two carry-forwards (both deferred, neither blocks):
the joint landscape routing fix + the auto-RIFE cross-verify (Pair-B).

HEAD at wrap: `a17961b`/`69f657b` region (5 seats moved HEAD ~7× this session — always
re-check). origin/main `5ba34e2`; **4 local commits ahead, UNPUSHED** (push USER-gated).
ci_smoke OK. Pod 07ed667 STOPPED, $0 spent this seat.

---

## What I did (the operator deliverable)

**Independent re-verification of ARCHITECTURE.md §8.5** (the one fresh Pair-A artifact;
its line-refs drive the deferred routing fix, so accuracy is load-bearing):

- Workflow `wf_e09bded6-3de` — 6 Sonnet verifiers, **refute-first**, one per falsifiable
  claim. **All six CONFIRMED, high-confidence, zero corrections:**
  - C1 root seam: `classify_shot_type` (`workflow_selector.py:416`) keyword bucket
    (`SHOT_TYPE_KEYWORDS:112`) wins over non-empty `characters_in_frame` → `landscape`
    (dict-order first-match-wins — my C1 verifier independently surfaced this; director-1
    folded it as the C1 scope-bound).
  - C2 production: `phase_c_assembly.py:223-227` early-returns `character_image=None`.
  - C3 max: `MAX_QUALITY_TEMPLATES['landscape']` (`workflow_selector.py:329-341`) zeros
    pulid/lora/halt/regen.
  - C4 max gating: `_inject_identity` keys on `has_character` (`quality_max.py:990`), not
    `shot_type` → PuLID present-but-inert.
  - C5 max rescue dead: +0.15 retry (`quality_max.py:1149`) unreachable at
    `regenerate_floor_arc=0.0` (via `needs_regenerate`→`arc_score<0.0`,
    `face_validator_gate.py:341`); char-LoRA gated on `char_lora_strengths`
    (`quality_max.py:500`). [+R-EVIDENCE: +0.15 magnitude exact, `quality_max.py:1153`.]
  - C6 fix: `wide`=pulid 0.65 prod (`:54`) + max (`:236-248`, lora 0.9) re-engages both.
- I also **hardened the root-seam anchors** the note was missing (it cited symptoms but
  named the seam/template without lines). director-1's `1b94dd7` absorbed all six anchors
  via the shared working tree (+ added dict-order bound + 8-keyword set + regen-floor
  chain). `git diff HEAD -- ARCHITECTURE.md` ended **EMPTY** (working tree == HEAD).
- Report: `6d1c1ef` (mailbox verification-report → director). §8.5 diagnosis is now
  **triple-convergent** (my 6-agent + director-1's 12-agent `wf_73f95c8c-615` + coordinator's
  7-agent `wf_5d39bbe3`), director-1 calls it "quadruple-verified". director ACKed; CLOSED.

**I committed NOTHING conflicting on §8.5.** This is the headline operational lesson →

---

## Carry-forwards (none mine to force; all deferred)

1. **Joint landscape routing fix** — `fix_with_brief / deferred / joint`. The coordinator's
   blast-radius audit (`wf_5d39bbe3`/`b922aa9`) found the `classify_shot_type` seam has **5
   downstream callers** for a char-bearing-landscape→`wide` reroute, **2 in OUR Pair-A lane**
   (need Pair-A author/co-sign — the brief can't be Pair-B-solo):
   - `domain/continuity_engine.py:529` — `get_threshold_for_shot(shot_type)` identity_threshold
     `0.0` (no-op) → `0.55` (ENFORCED). shot_type-driven (verified).
   - `domain/performance.py:52` — dialogue char-landscape `should_capture` flips True.
   - (Pair-B/diagnostic, FYI: `controller.py:1421` video_fallbacks +RUNWAY_GEN4 but
     **target_api stays LTX** — landscape==wide==LTX, `workflow_selector.py:371` vs `:278`,
     so video-API blast radius ~nil; `motion_render.py:265` advisory floor; `calibrate_motion_floor.py:63` CSV.)
   - Caveats the brief must carry: (a) production LoRA-only edge — `character_image` absent →
     `characters_in_frame=[]` → still routes landscape, early-return won't fire (scope-precision,
     not a bug); (b) `char_lora_strength` override (`quality_max.py:500`) partially escapes
     LoRA-zeroing on max — §8.5's "both zero" is exact for PuLID, slightly strong for
     LoRA-when-explicitly-set (already in §8.5's last bullet).
   - Process: director2 authors (task #5) + director Rule#23 co-sign + operator2 implements;
     cross-ref ADR-025. Next Pair-A director carries the 2-Pair-A-caller scope (in director-1's
     PM5 handoff `a17961b`).

2. **⚠ auto-RIFE `65e9b88` cross-verify OWED on a PUBLIC commit** — default-on motion
   frame-interpolation (W1 §5.2), TDD-green (8 new + 70 regression) but operator2 wrapped
   flagging it peer-WIP, not CONFIRMED; principal pushed it. **Pair-B lane** (motion/video),
   no Pair-B seat live. Not Pair-A's to verify under lane discipline; flagged to principal.
   Risk moderate-not-urgent (recommendation-gated: fires only `smoothness<0.4` AND
   `recommendation!="regenerate"`, which keeps fake/short clips off the real paid FAL RIFE call).

3. **N=4 robustness + experiment burn** (`scripts/_prod_pulid_acceptance.py --n 4`;
   `_prod_dual_lora_pulid.py`) — OPTIONAL, pod-gated, pod STOPPED. Step-5 GO does NOT need them.

---

## Sharp edges (5-seat shared tree — these bit/nearly-bit this session)

- **`git log -1` before EVERY shared-tree commit.** HEAD moved ~7× under me
  (`e61ab10→65e9b88→…→6e733ae→1b94dd7→b922aa9→4c3b64f→5ba34e2→a17961b`). Three seats edited
  ARCHITECTURE.md §8.5 *simultaneously* and it converged ONLY because I `git log -1`'d +
  **reviewed the staged diff before committing** — the review caught director-1's in-flight
  dict-order edit (would've been a conflicting head if blind-committed). Pre-commit staged-diff
  review is not optional in a live session.
- **Stale per-seat index → `git status` LIES.** It flip-flopped (showed `director2.txt`, then
  `cost_tracker.py` after a failed `git checkout`). Ground truth ONLY via
  `git diff --no-index <(git show HEAD:f) f`, `git ls-tree HEAD`, `git diff HEAD --name-status`,
  `git cat-file -e HEAD:f`. (You're pinned `GIT_INDEX_FILE=.git/index-operator`.)
- **Tight pathspec commits, `-m` before `--`.** Never sweep peer WIP. This session the tree held
  Pair-B's auto-RIFE WIP (`cost_tracker.py` + `test_auto_rife_finalize.py`, since committed
  `65e9b88`) — my pathspec commits excluded it cleanly.
- **Don't touch peer cursors.** `coordination/mailbox/seen/{director2,operator2}.txt` showed
  modified in my tree (cross-seat contamination) — each seat owns its own cursor; advancing
  another's would make it skip unread messages. Left untouched.
- **origin is PUBLIC now (`5ba34e2`+).** The principal pushed the whole stack one-time. Every
  "push USER-gated / nothing pushed / N ahead / $0" line across handoffs + presence + MEMORY.md
  is STALE — trust `git`, fix-on-touch.

## Verify on resume
`.venv/bin/python scripts/ci_smoke.py` (OK at wrap); `git rev-list --count origin/main..HEAD`
(was 4 — my `6d1c1ef` + director-1's `42f008b`/`a17961b`/`69f657b`, all UNPUSHED unless principal
pushed again). §8.5 lives at `ARCHITECTURE.md:975`. Mailbox cursor `operator.txt` advanced to
`2026-06-13T11:25:01Z`.
