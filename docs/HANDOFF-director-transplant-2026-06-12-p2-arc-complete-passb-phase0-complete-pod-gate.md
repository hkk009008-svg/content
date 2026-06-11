# Director transplant handoff — 2026-06-12: P2 ARC COMPLETE (P2-1+P2-5+NF-7 + bonus skip-routing fix) + PASS-B PHASE 0 COMPLETE (binding metric detection-filtered, baseline 0/4) — POD START IS THE GATE, user asked at wrap

**Supersedes** `docs/HANDOFF-director-transplant-2026-06-11-pod-arc-complete-s2-conditional-s3-bleed.md`
(its ⭐#1 fully discharged: pod probed STOPPED at session start (502 + no sshd
banner — bare TCP-accept is the Novita edge proxy, NOT billing); push found
ALREADY discharged at wrap-time (origin was at 09fcf36 CI-green); next-arc
choice surfaced → user picked "both as recommended"; operator Lane V folded
across SIX report cycles this session).

## Ground truth (verified at wrap, 2026-06-11T~23:50Z UTC / 2026-06-12 KST)

- **HEAD `a8587f7`, local 9 ahead of origin `1ec2d4e` (CI run 27377214608
  GREEN on the 24-commit midday push). Push USER-gated as always.**
- **Suite: 2236/0 — full recount at `a8587f7`** (director-run, completed at
  wrap; +56 vs the 2180 at `1ec2d4e` = the Phase-0 batch's tests exactly).
  Smoke OK + doc gate "no drift" at `a8587f7`.
- **Mailbox: cursor 2026-06-11T21:36:04Z, 0 unread.** Operator ONLINE at
  wrap (their monitor re-armed; their queue: Lane V the Phase-0 batch).
- **Pod: STOPPED** (probed at session start). Credential + both LoRAs
  presumed intact (stopped-not-terminated; memory `pod-ssh-credential`).
- **THE GATE: user was asked at wrap to (1) start pod 07ed667 in the Novita
  console and (2) give the session-scoped verbatim SSH/ComfyUI go-ahead.**
  Their answer may be the first message of your session.

## ⭐ #1 PICKUP (in order)

a. **If the user gave pod go-ahead: execute SPEC-PASS-B §5 Phase 1** —
   census probes ($0): `GET /system_stats`, `GET /object_info`, then the
   **Design-A GATE** (`ApplyPulidAdvanced` present AND FLUX-schema
   (`pulid_flux`-typed input, not SDXL-era `pulid`) AND `attn_mask`
   exposed — class presence alone is NOT a pass). Also probe #4: attn_mask
   coordinate space (schema first; empirical at Phase-3 N=1 smoke). GATE
   fail → Design A NO-GO, pivot Phase 4 (ReActor swap-rescue probe,
   ~0.01 GPU-hr) with Design B's binding metric as measurement either way.
   Verify both LoRAs still in `loras/` and census ≈1106 classes (terminated
   pod = re-ask user + re-place per runbook Phase-1 pattern).
b. **Phase 2 (VRAM baseline N=1, ~5 min) → Phase 3 (masked dual-PuLID)**:
   new driver `scripts/_max_passBa_masked_pulid.py` extending
   `_max_s2_dual_pulid.py` (seeds 990011/22/33/44, weights 0.85,
   end_at=0.9 — S2-matched; masks from `scripts/_mask_gen.py`, already
   emitted for 3840×2160 in `logs/passb_masks/`). **Rule #22
   flag-before-burn: the driver goes to the operator BEFORE pod burn**
   (they are armed for it). Scoring: `scripts/_arc_score_session.py
   --halves --artifacts 'logs/passb_*.jpg'` (detection-filtered; R-MEASURE).
   GO bar: binding_ok BOTH chars ≥3/4 seeds (baseline is 0/4) + VISUAL
   confirmation mandatory (S3 lesson) + record per-half face-presence per
   seed (4/18 of the S2-era halves had NO detectable face — cheap quality
   signal). Show EVERY artifact in Preview as it lands (user standing
   directive). Spend: ~$0.30–0.50 FLOOR at ~$0.30/hr.
c. **Push the 9-commit Phase-0 batch** when the user is engaged (USER-gated).
d. **Fold operator Lane V findings on the Phase-0 batch as they land**
   (their queue: `fcd06b5` 0b masks · `ef7b60c` 0c binding metric (review
   AFTER 312f6d2 per my sequencing note) · `312f6d2` detection filter
   (their no-face-rows closure target) · `786d9e9` PUT fix · `a8587f7`
   docs). Convergence is running high — expect sharp findings.

## What landed this session (director seat, chronological)

**Session start hygiene:** skip-worktree strike #2 (866 bits) diagnosed
phantom + cleared + memoried · pod probed STOPPED (502 + no-sshd-banner
disambiguation — port-accept ≠ billing) · 12 manual anchors fixed `9360e20`
(3 db_path usage cites HAND-corrected after `--fix` dragged them to the def
— live instance of the usage-cite corruption mode) · MEMORY.md trimmed
29.5KB→~9KB (was being truncated every session) · 4 stale `.claude/worktrees`
(~456MB, pre-pivot code) removed user-authorized · fyi event `ae69441`.

**P2 arc (user: "both as recommended"; two waves, R-ORCH, every task
implementer + dual reviewer + fix round, all Sonnet):**
1. `13a93e7` NF-7 — dead FAL-Hedra attempt retired (TDD; the in-code comment
   claimed the opposite order; FAL-only-key now → immediate None → sadtalker).
2. `8c9645c`/`24fddfa` P2-1 — 79+62 prints → JSON logger w/ engine extras;
   15 caplog tests; known-accepted: 4 cascade-extras tests are plumbing-level
   (30s quota-sleep makes e2e prohibitive).
3. `4ad027a` P2-5 — 27 bare except-pass → 0 (comment-only; AST-instrument).
4. `8783663` BONUS REAL BUG (operator IMPORTANT dug deeper): UI-selectable
   `lip_sync_mode="skip"` routed shots into GENERATION — now guarded
   (skip → logged None → original video kept) + unconditional
   `lipsync_dispatch` entry signal. TDD.
5. `832247f` Pass-B spike spec (838 lines, dual-reviewed; GO bar raised to
   ≥3/4 in review — 2/4 was the unmasked baseline; end_at pinned 0.9).

**Operator coordination (SIX cycles, all consumed + disposed both ways):**
- Their 18:49:37Z (dc5ad2b batch SAFE + A/B/C dispositions) → `b91c6c9`
  §3(d) sharpened scope (co-star family A1–A4) + §6 append-only corrections.
- Their 19:46:18Z hardening batch (Rules #21/#22, R-MEASURE, R-SKILL,
  dispatch git-hygiene, SessionStart sweep) → ACK'd in full, git-hygiene
  adopted in every subsequent dispatch; their held ARCHITECTURE anchor fix
  carried `013b8d9`.
- Their 20:14:36Z (wave-1 SAFE + 5 Pass-B pre-pod dispositions) → all 5
  folded `1ec2d4e` (Design-A probe → hard GATE; coord-space probe #4; §3.4
  equivalence sentence replaced; R-MEASURE #1 discharged via `--artifacts`
  parameterization in `45c6e52`; line-count ack).
- Their 21:16:46Z RECONCILIATION (the big one): recorded 0.487 was the TRUE
  figure read; my instrument's man-column was 13/18 non-figure (blobs +
  whole-image fallbacks incl. the sec45-L "reproduction" — NO face in that
  crop). Accepted in full → detection filter (below). My transition-window
  hypothesis was mechanically right, semantically INVERTED (best-face max
  PROMOTED junk).
- Their 21:36:04Z (wave-2 Lane V all SAFE + 4 IMPORTANTs + **06d4849
  provenance correction: the ai-video-gen SKILL.md sync I committed was
  THEIR uncommitted lane-a fold, not my subagent's — misattribution OWNED**;
  the D-a shared-worktree-drift class; new check added to my attribution
  routine: diff unattributed edits against the peer's presence
  current_task FIRST).

**Pass-B Phase 0 (user: "proceed one phase at a time"):**
1. 0a — binding directions derived from the existing instrument table ($0).
2. `fcd06b5` 0b — `scripts/_mask_gen.py`, boundary test-pinned to crop_half.
3. `ef7b60c` 0c — `_compute_binding_scores` + `validate_image_with_binding`
   (TDD 18→28 tests; **slot decision RESOLVED: callers pass intended_slot;
   CharIdentitySpec change deferred post-spike** — recorded §3.3).
4. `312f6d2` detection filter (BLOCKING, from the reconciliation):
   `_figure_read_score` = largest OK face (≥1% area, no whole-image
   fallbacks), shared home identity/validator.py + scripts/_face_reads.py
   re-export; ref embeddings largest-OK guard; instrument re-emitted
   `logs/halves_rescore_20260612_filtered.{json,txt}`; binding fixtures
   recomputed. **FILTERED BASELINE: aria 0/4, man 1/4 (via other-half-
   no-face only; 0/3 strict). Man figure reads uniformly 0.466–0.528.**
5. `418dee2`+`786d9e9` A3 both doors (registration assert + PUT bypass).
6. `a8587f7` records: §6 SECOND correction (n3 0.832 runtime-unreproducible
   — labeled, not reconciled; 0.447 = full-image; regeneration-command
   citation per discoverability disposition) + §3.4 evidence replaced with
   probe/filtered reads + Phase-0 RESULTS in the spec.

**Pushed mid-session on user "push": 24 commits, CI 27377214608 GREEN.**

## Director backlog (carried + new)

P2-2 pod idle guardrails (now FOUR-times relevant — pod restart imminent) ·
production wiring of binding (A1/A2/A4 halt/regen gating + CharIdentitySpec
slot field — AFTER spike validates) · bbox-centroid binding alternative
(docstring-recorded) · swap-targeting H1–H3 offline experiment (Design C
§4.3 — can run pre-pod with existing artifacts BUT needs local ReActor =
UNVERIFIED) · per-half face-presence as a render-quality gate (new Phase-3
signal) · commit-verdict-tables-to-tracked-path protocol question (operator
rules-log lane; both precedents now exist) · aesthetics_predictor install
decision · spec §9 debts · P3-1 extraction ratchet · PM:1773 dotted-token
slash-row.

## Operational notes (this session, on top of predecessors')

- **Best-face max has TWO failure costumes:** first-face missed real faces
  (dc5ad2b's fix); max-over-detections PROMOTES junk (59×59 blob beat the
  real figure). Per-figure semantics = detection-classify then LARGEST OK
  face. Calibrate any embedding metric against a per-face probe before
  trusting its table.
- **The attribution check that was missing:** before claiming authorship of
  an unattributed worktree edit, diff it against the peer's presence
  `current_task` — their in-flight fold looks identical to your subagent's
  out-of-brief work from inside one shared tree.
- **Strike #3 variant exists** (operator-observed): phantom STAGED entries
  with ZERO skip-worktree bits after a 16-agent Workflow whose subagents all
  carried the git-hygiene prefix. Same remediation (verify vs HEAD blobs,
  read-tree). SessionStart hook sweep gets its first live fire at YOUR
  session start — verify `.claude/hooks/.skip-worktree-cleared.log`.
- Pod-work authorization is session-scoped; the wrap-time ask does NOT
  carry to your session — if the user's go-ahead message isn't in YOUR
  session, re-obtain verbatim.
- Six-cycle coordination day: consume-events advanced past an unread event
  once (20:51:53Z) because I sent-then-consumed blind — READ the newest
  event BEFORE consume-events when the peer is live.

*Last verified: 2026-06-11T~23:55Z UTC — smoke OK + doc gate no-drift +
suite 2236/0, all at a8587f7; cursor 21:36:04Z 0 unread; operator ONLINE
mid their own session.*
