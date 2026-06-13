# Operator transplant handoff — 2026-06-09 — lip_sync Lane V ✅ SAFE (arc review-complete) · protocol-upgrade pass (2 shipped, 2 surfaced) · NOTHING OWED

**READ FIRST IF PICKING UP AS OPERATOR.** Supersedes
`docs/HANDOFF-operator-transplant-2026-06-09-slice3-done-three-lanev-safe.md`
(prior session; that doc carries the Slice-3 verifier detail + got an UPDATE banner this session).

## 0. State at wrap (git-verified)

- **Branch** `feat/max-tier-provisioning`. **HEAD = `83ea503` = `origin/feat`** (all this session's work pushed; 0 ahead).
- **`origin/main` = `1870e59`** GREEN — portrait 9:16 + lip_sync M-1-twin both LIVE on main. **Untouched this session** (every operator commit was Lane-V/tooling/docs/coord — zero pipeline change), so main stays at the merged arc.
- **Gate:** `cinema/aspect.py:25` `["16:9","9:16"]` — OPEN, portrait LIVE.
- **Mailbox:** operator **0 unread** (cursor `02:10:03Z`); **verify live with the new tool: `.venv/bin/python scripts/status.py mailbox-unread operator`**. NOTHING OWED.
- **Suite/smoke:** my commits don't touch the pipeline. `tests/unit/test_status.py` **35/35** (verified, includes the 5 new tooling tests). Full suite **1923/0** + ci_smoke OK per director's last verification at the merged arc (`1870e59`) — NOT re-run this session (committed-SHA pipeline state unchanged; director is live on a parallel tree, so a full-suite run risks dirty-tree transients — see Gotchas).
- **Working tree:** clean (untracked scratch `scripts/_*.py` + `docs/adr/` only). **Director is LIVE in parallel** (presence active; post-roadmap reassessment `wf_198f53fe-7aa`).

## 1. What this session shipped (all on `feat`, pushed)

### A) Cold Rule #9 Lane V on `dd78208` (lip_sync M-1-twin orientation backstop) = ✅ SAFE
The LAST open item of the portrait-delivery arc. Run as a **Rule #17 Dynamic Workflow** (`wf_627fd99b-61e`: 3 cold lenses spec/quality/symmetric ∥ → per-finding adversarial-refute → synth; 7 agents/~635k tok). **All lenses CLEAN** (0 CRIT/0 IMPORTANT/0 MINOR).
- **M-1 twin CLOSED:** all 4 gen engines (Hedra/Kling/Omnihuman/Aurora) funnel through the single `_gate_or_stash` fence; reject `return False` precedes the stash-to-`candidates` block → a wrong-orientation clip can't win best-of-failed.
- **Landscape byte-identity PROVEN:** `is_portrait(None/"16:9")`→False → `_accept_or_reject` returns True before any probe (`phase_c_ffmpeg.py:1313-14`).
- **Rule #13:** OVERLAY cascade (`_overlay_gate_or_stash`) correctly unfenced — inherits orientation from an upstream-fenced `existing_video_path` (callers `controller.py:1489`/`:2084`).
- **R-OP-1 spot-check HELD** (11-site fence count, no-op short-circuit, overlay non-fence, fenced callers; 3 guard tests pass first-hand). 2 INFORMATIONAL only → NO ACTION. SAFE → no Rule #15 fix.
- Artifacts: verification-report `2026-06-09T04-11-55Z`; commits `2d27af0` (report + cursor `00:43:43Z`→`02:10:03Z`) + `594e21b` (banner on prior handoff).

### B) Protocol-upgrade pass (user "any recommendation?" → "proceed")
Ran analysis workflow `wf_9c032336-468` (verify-vs-protocol-history → adversarial-critique → synth). **It corrected my own framing twice** (NOT "first use"; awk bug is honestly N=1). Net (deliberately *shrunk* by the critique): 2 ship-now + 1 advisory + 1 filed + 1 dropped.
- **rec #2 SHIPPED — `3fa29c9`** `chore(tooling)`: **`scripts/status.py mailbox-unread <seat>`** — exposes the canonical TDD'd `count_unread` (via `collect_mailbox`) as a focused live-count CLI (skips the dashboard's pod probe). The Rule #20.1 live-recompute instrument that retires hand-rolled `awk`. TDD 5 tests, GREEN **35/35**.
- **rec #4 FILED — `884c452`** `docs(protocol-log)`: **Candidate #9** in `PROTOCOL-RULES-LOG.md` (N=1, NOT codified) — "current_task describes ACTIVITY, not cached volatile counts" (Rule #19 mit-d), with a REALIZED-HARM N=2 trigger. Deliberately not bundled with #2 to avoid manufacturing N.
- **#1 + #3 SURFACED to director — `83ea503`** (event `2026-06-09T05-43-35Z`): see §2.
- **Dropped:** **C3-b** → advisory (the line-drift exhibit self-refuted the "verify every line" MUST: workflow `:2086` → my own spot-check `:2085` → actual `:2084`); **C4** dropped (covered by Rules #10/#19).

### C) Director cursor-reconcile ping — `9e0bf12`
User-directed. Surfaced that the director's `current_task` "0 unread" was stale (Rule #20 bootstrap stale-count) — pointed at the pending verification-report. (This live observation became rec #4 / Candidate #9.)

## 2. ⭐ #1 PICKUP — NOTHING OWED by operator; open items are in the DIRECTOR's queue

Operator is wrapped, 0 unread, nothing owed. The open items belong to director-seat (surfaced in event `2026-06-09T05-43-35Z`, awaiting their disposition per Rule #8):
1. **#1 (director-lane, highest leverage):** the **OVERDUE v5.6 Rule #17 retro** + fix the **verified-FALSE** `CLAUDE.md:1728-1729` claim ("unavailable < 2.1.154" — live `claude --version` **2.1.169**; ~18-run arc). Same commit per ADR-013.
2. **#3 (operator-drafted → director-ships):** advisory amendment to Rule #20.1 naming the new instrument + the two proven awk traps. Draft text is in the `05:43:35Z` event — director ships via proposal cycle or counter-refines.
3. **Director has 3 unread to-director events** (`status.py mailbox-unread director` → 3): my `04:11:55Z` verification-report, `04:42:44Z` ping, `05:43:35Z` recs. They were live but hadn't reconciled their cursor (still `00:53:45Z`) at wrap — their live-recompute (Rule #20.1) should surface all three.

If you pick up as operator and the director shipped #1/#3: do a cold Lane V on any code/rule commit per Rule #9 (the Rule #20.1 amendment is a CLAUDE.md doc edit — Lane D-adjacent, not Lane V).

## 3. Gotchas (carry forward)

- **USE THE NEW INSTRUMENT for live unread, don't hand-roll `awk`.** `.venv/bin/python scripts/status.py mailbox-unread <operator|director>` prints the correct live count. I got hand-rolled `awk` WRONG twice this session: (a) a full filename carrying the cursor's 20-char PREFIX sorts AFTER the bare prefix → `$0 > "<cursor>"` over-counts the at-cursor event; (b) `awk -F'-to-<seat>'` captures trailing text into the timestamp field. If you must hand-roll, compare `substr(name,1,20)` strictly `>` the cursor.
- **Even spot-checks drift — machine-check the line#/SHA class.** The dd78208 overlay-caller line drifted THREE layers (workflow `:2086` → my R-OP-1 spot-check `:2085` → actual `:2084`). Don't trust a single human re-read of an exact line number; re-grep the SYMBOL at commit time (Rule #15) when a fix lands at a workflow-cited location. Durable fix (deferred): extend `check_doc_claims.py` to the line#/SHA class (Rule #18 priority).
- **Dogfood Candidate #9:** keep `current_task` about your own ACTIVITY; never freeze a peer's online/offline or an unread count into it (recompute live). My wrap presence does this (it says "recompute via status.py").
- **D-a discipline (director was live all session):** every commit `git read-tree HEAD` → `git add <paths>` → `git commit -m … ` with pathspec; Rule #7 re-verify (`git log -1` + check newer to-operator events) right before committing. `env -u GIT_INDEX_FILE` for pytest. Push to feat is D-a-safe (no checkout while peer active).
- **Don't run the full `tests/` suite against the live-peer tree** — dirty-tree transients (the prior-session 7-vs-1 misattribution lesson). Scope to your change's tests or run after the tree settles.

## 4. MEMORY-CANDIDATES (director-lane curation)
- **The `status.py mailbox-unread` instrument exists now** — future sessions should use it for Rule #20.1 live recompute instead of awk (operational reference). [MEMORY.md is over its size limit — director prunes/curates.]
- **The 3-layer line-drift datapoint** — even the human spot-check drifts on exact line numbers; argues for machine-checking the SHA-ref/line# class (Rule #18 buildout priority).

## 5. Mailbox / cursor
operator cursor `02:10:03Z`; **0 unread** (verify: `status.py mailbox-unread operator`). This session's operator sends: verification-report `04-11-55Z`, ping `04-42-44Z`, recs `05-43-35Z` (+ the commits `2d27af0`/`594e21b`/`9e0bf12`/`3fa29c9`/`884c452`/`83ea503`). Last director event consumed: `02:10:03Z`. **D-a-safe commits:** `git read-tree HEAD` → `git add <paths>` → `git commit` (pathspec); push `git push origin feat/max-tier-provisioning` (no checkout while director live).
