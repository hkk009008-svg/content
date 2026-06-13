# Operator transplant handoff — 2026-06-12 (early AM KST): TWO Lane V cycles ✅ SAFE (dc5ad2b batch 133 claims + wave-1 108 claims) + user-directed process-hardening SHIPPED (Rules #21/#22 + R-MEASURE + R-SKILL + git-hygiene + SessionStart sweep) + Pass-B spec 5 pre-pod dispositions sent — director LIVE mid-wave-2

**Seat:** operator · **Session:** 2026-06-11T~17:51Z → ~20:20Z (KST 06-12 02:51 → 05:20)
**HEAD at wrap:** `eb049a2` (mine). **origin/main:** `09fcf36` (local **18 ahead**, push
USER-gated; last push CI-green run 27322373737, discharged by director at their session
start). **Suite:** **2167/0 (+3 skip) pinned-worktree recount at `832247f`** — delta from
2150/0 (at `09fcf36`) pairs EXACTLY with wave-1's 17 new tests (2 NF-7 + 9 ffmpeg + 6
lip_sync). Smoke exit 0 at `013b8d9`+. **Cursor: 2026-06-11T19:52:13Z, 0 unread.**
**Director: LIVE mid-wave-2** at wrap — 8+ files modified on the shared tree (P2-5
honesty pass + A3 assert in identity/validator.py + more); expect movement.

## ⭐ #1 PICKUP (in order)

1. **Lane V the director's wave-2 batch when enumerated** (their 19:52:13Z event named 3
   tasks: P2-5 honesty pass over the 26-bare/36-total except-block AST inventory + **A3
   ref-side single-face assert** (identity/validator.py `_get_embedding`, TDD — load-bearing,
   it closes the ref-side contract from my dc5ad2b review) + **halves-mode scorer** extending
   `scripts/_arc_score_session.py` emitting a logs/ table (R-MEASURE instance — my 20:14:36Z
   disposition #1 asks for the artifact list to be PARAMETERIZED, not S2-hardcoded; check the
   brief honored it). T5/T6 sequenced (both touch identity/validator.py). Live WIP visible at
   wrap: audio/dialogue.py, domain/character_manager.py, identity/validator.py, lip_sync.py,
   llm/chief_director.py, llm/director.py, performance/_net.py, performance/act_one.py.
2. **Watch for the director's dispositions on my 20:14:36Z wave-1 report** — 5 Pass-B items
   (R-MEASURE Phase-3 instrument · ApplyPulidAdvanced FLUX-compat = Design-A BLOCKER risk,
   promote probe to gate · attn_mask pixel-vs-latent coord-space probe · §3.4 "best-face ≡
   half-crop" equivalence sentence is FALSE per my firsthand re-score (sec45 0.828 half vs
   0.667 full; pass-a man 0.487 half vs 0.597 full) · 838-vs-712 line claim) + the
   `lipsync_dispatch` sentinel scope fix (CONFIRMED 0-2: fires only on FAL-unavailable, not
   pre-mode; 1-line widen or re-scope comment). Spot-verify the disposition commit diff 1:1
   against the reply (the b91c6c9 pattern — pairing, not existence).
3. **Push:** local 18+ ahead of CI-green `09fcf36` — USER-gated as always; surface at a
   natural point.
4. **SessionStart hook live-fire check:** YOUR session start is the first real fire of the
   new registration (update-state.sh under SessionStart in settings.local.json, T1 of the
   hardening plan). Confirm: hook ran (check `.claude/hooks/.skip-worktree-cleared.log` for a
   session-start-time entry if bits existed; `git ls-files -v | grep -c '^S'` → 0) and your
   `git status` is phantom-free. If phantoms persist anyway, see sharp edge #3 below.
5. **Open lane candidates (no urgency):** (a) **ai-video-gen skill sync** — the NF-7 lens
   proved `recommend_lip_sync_mode()` does NOT exist in the codebase yet the skill cites it
   (same staleness class as the comfyui-mastery sync shipped `1d80411`; R-SKILL now makes
   skill accuracy load-bearing — audit the skill's Source Map + Integrated Capabilities
   sections against code); (b) assignment-binding verifier extension (ALL-CAPS constants
   def-less → invisible to def_drift; carried from 2 sessions ago; director's 9360e20
   usage-cite hand-correction is fresh evidence); (c) RE-ARM monitor + heartbeat.

## What this session did (chronological)

1. **R-START + firsthand verification batch:** smoke OK; **arc re-score reproduced** spec §6's
   full-image numbers exactly (pass-A aria 0.819 EXACT; cross floor **0.447 EXACT** in the
   man-img→aria-ref direction, 0.421 reverse — direction-dependent because ref-side and
   image-side use different extraction paths; self 1.000); pinned-worktree suite 2150/0 at
   09fcf36 after TWO methodology misses (need `.env` copied AND `env -u GIT_INDEX_FILE` —
   155 then 106 false fails); **index-operator corrupted outright** ("unable to read <blob>")
   → `git read-tree HEAD` repair, new failure mode memoried.
2. **Lane V #1 — dc5ad2b + 3a589da + d870f9e ✅ SAFE-with-dispositions** (`wf_a7476a8f-965`,
   5 Sonnet lenses + 2-refuter gate, 31 agents, 133 claims + firsthand re-score/calibration/
   visual spot-checks): dc5ad2b correct (single-face equivalence proven, RED 0.5221
   reproduced); d870f9e mechanical claims LOG-BACKED (pass_a_rerun_012642.log, s2_spike_run.log
   41.8 GiB, s3_sweep_run.log); 9 CONFIRMED IMPORTANTs in 3 themes — A) best-face co-star
   false-positive family (A1 halt early-fire / A2 controller.py:810 / A3 ref-side [0] /
   A4 split), B) half-crop numbers credible-but-unreproducible (REPL-only), C) record
   precision (n1 both-female, cand7 two-bearded-men, pass-a man zero-resemblance). Report
   18:49:37Z (`dad6cb7`). **Director disposed ALL in `b91c6c9`** (§3(d) sharpened scope + §6
   append-only corrections + $2/1000→ESTIMATE + 2 wave-2 code tasks) — **spot-verified 8/8
   against the diff** + doc gate re-run firsthand, ack `ff9c993`.
3. **R-SKILL + comfyui-mastery re-sync (`1d80411`, user approved the carried offer):** new
   CLAUDE.md/AGENTS.md rule (invoke comfyui-mastery before ComfyUI-graph work, ai-video-gen
   for pipeline-level) + the skill's integration docs re-synced against live code (pulid.json
   15→22 nodes incl. PAG + RealESRGAN chain; RunPod 4090 → Novita RTX 6000 Ada; parameter
   table re-snapshotted from WORKFLOW_TEMPLATES; pulid_max.json 60-node tier documented) +
   rules-log provenance.
4. **User-directed process-hardening batch SHIPPED** ("plan to apply these" — items 2-5;
   planned via writing-plans, plan-reviewer APPROVED w/ anchors verified, executed main-context
   sequential per R-ORCH; plan: `docs/superpowers/plans/2026-06-12-two-seat-process-hardening.md`):
   `5fb0096` update-state.sh registered at **SessionStart** (closes v5.9 post-last-hook-fire
   window; settings.local.json + OPERATIONS.md §2) · `b6c5e74` **dispatch git-hygiene**
   (per-invocation `env -u GIT_INDEX_FILE` in all 3 templates + CLAUDE/AGENTS clause; one-time
   export impossible — subagent shell state doesn't persist) · `7e9f4ac` **Rules #21
   verdict-ahead-of-report + #22 flag-before-burn** (both twins; pointers #7-#22) · `16246b3`
   **R-MEASURE** (verdict-backing numbers need committed instrument + logs/ artifact, or
   estimate label) · `9a778ab` provenance + proposal event · `dacf1a4` plan doc. **Director
   ACK'd all five 19:52:13Z** — git-hygiene adopted in their dispatches effective immediately,
   no disagreement items.
5. **Lane V #2 — wave-1 `13a93e7..832247f` (`wf_72cad805-f22`, 4 lenses + gate, 16 agents,
   108 claims): 3 code commits ✅ SAFE** — NF-7 RED-proofs re-derived (pre-commit comment was
   INVERTED vs behavior: FAL ran first, burning the 1800s window); both print→logger
   conversions EXACT (79/79, 62/62, 0 survivors; quota machinery + 4 deferred bare-excepts
   byte-identical; logger import-clean); R-SKILL honored (both skills loaded pre-review).
   **Pass-B spec: premises faithful** (S2/S3 + corrections carried; §3.4 dispositions pairing
   exact; end_at 0.9 verified vs pulid_max.json node 100; user-gated FLOOR cost estimate) **but
   5 dispositions sent pre-pod** (see pickup #2) — incl. **R-MEASURE's FIRST live enforcement**
   (3h after codification) and 1 finding KILLED 2-0 by the gate (spec never claimed parameter
   parity). MINORs: "206 across 6 families" wrong on both counts (8 families → 210);
   lipsync_dispatch absent from body taxonomy; overlay-gate test pins PASS-direction only.
   Report 20:14:36Z (`eb049a2`).

## Sharp edges (this session's additions)

1. **Throwaway-worktree suite recounts need BOTH halves:** `cp .env <worktree>/` AND
   `env -u GIT_INDEX_FILE` on the pytest invocation — I hit each failure separately
   (155 fails = missing keys; 106 fails = inherited seat index).
2. **Seat index can corrupt OUTRIGHT** (`git status` → `fatal: unable to read <blob>`), not
   just go stale — repair: `git read-tree HEAD` on your own seat index (working tree
   untouched; safe with peer live), then re-verify status shows only true edits.
3. **Phantom-staging strike #3 variant: ZERO skip-worktree bits** (staged-MM on
   ARCHITECTURE.md/seen-files + staged-D on an EXISTING recent mailbox event) — appeared
   right after a 16-agent workflow whose subagents all carried the hygiene prefix (prefix
   prevents agent index *use*; some op still plants stale staged entries). Verify
   `git show HEAD:path | cmp - path` per path; remediate read-tree + re-stage YOUR real
   files (`git add` new files before pathspec commit — bit me on the plan doc too).
4. **`cmd | tail; …` masks the exit code** — bit me LIVE at the T1 smoke gate (the masked
   failure was the director's in-flight anchor drift, benign — but the mask is the lesson;
   run gates with `> file; echo EXIT=$?`).
5. **Attribute working-tree drift before acting:** smoke def-drift failures mid-session were
   the DIRECTOR's uncommitted WIP shifting line numbers — HEAD-blob comparison
   (`git show HEAD:file | sed -n`) settles attribution in seconds; their commit carried the
   anchor fix per R-START, as predicted.
6. **New rules now bind YOU:** R-SKILL (load comfyui-mastery/ai-video-gen BEFORE
   judging graph/pipeline work — name the skill when a prior shapes a verdict), R-MEASURE
   (verdict numbers need committed instruments), Rules #21/#22, dispatch git-hygiene block
   in EVERY subagent prompt.

## Cross-seat state at wrap

Director: **LIVE, mid-wave-2** (their enumeration: P2-5 honesty pass + A3 assert + halves
scorer; T5/T6 sequenced on identity/validator.py). All dispositions closed in BOTH directions
through wave-1: my dc5ad2b-batch report → their `b91c6c9` (spot-verified 8/8) → my wave-1
report 20:14:36Z (their dispositions PENDING — pickup #2). Hardening batch ACK'd in full;
they fixed the phase_c_ffmpeg anchors in `013b8d9` exactly as forecast. Pod: STOPPED (their
session-start probe; both LoRAs persist). Next-arc decision: user picked "both as
recommended" (P2 main line + Pass-B spec riding along); Pass-B execution is USER-GATED on
pod/spend authorization — my 5 dispositions land before that gate. Mailbox mine this session:
18:49:37Z, 18:56:47Z, 19:46:18Z, 20:14:36Z (+ wrap event). Cursor 19:52:13Z, 0 unread.

*Last verified: 2026-06-11T20:20Z (state block + suite 2167/0 recount at 832247f; status
snapshot shows director wave-2 WIP on 8+ files — theirs, untouched).*
