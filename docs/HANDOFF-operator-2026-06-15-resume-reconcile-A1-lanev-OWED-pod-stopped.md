# HANDOFF — Operator-1 (Pair-A), 2026-06-15 — resume→reconcile; **A1 Lane V OWED (not started)**; pod stopped

**READ FIRST as operator-1.** This was a short resume+wrap. **No production code, no verification authored this session.** The one thing that matters for the next operator-1: **a triggered Lane V is OWED and unstarted** — see §OWED.

## TL;DR
Resumed cold, oriented to a stale session-start picture (HEAD `dd6377a`, "idle/HOLD"), confirmed the tree green, and **discharged the carried pod-billing obligation** (user stopped the pod). Then — on the user's `handoff` request — reconciling the mailbox for the wrap **surfaced that the world had moved a lot under me**: director-1 landed the **A1-lora-decouple fix `23c99e3`** and sent operator-1 a **verify-request**; the coordinator adopted **ADR-027**. So my early "nothing to verify, HOLD" is **obsolete** — operator-1 now owes a real Lane V. User chose to **wrap with it queued** (did not run it this session).

## State at wrap (TRUST GIT, not this prose — tree is HOT)
- **HEAD was `b5158f1`** (operator2 wrap) at my last check and **moving** — director-1, operator2, coordinator all active this window. Re-anchor (`git log -1` + mailbox) before ANY commit.
- `23c99e3` (A1 fix) is a **verified ancestor of HEAD** (`git merge-base --is-ancestor 23c99e3 HEAD` → YES) — the fix is real and in-tree.
- **Suite green:** `2489 passed, 0 failed, 29 xfailed, 3 skipped` at HEAD `dd6377a` (my evidence run, `pytest -q`); `ci_smoke.py` → OK. Newer commits (`23c99e3` A1 fix + Pair-B money/lipsync fixes + ADR-027 docs) landed AFTER that run — **re-run the suite at current HEAD as the next-session entry check** (the A1 fix flipped 2 xfail pins to live regressions per the brief; expect the count to shift).
- **Mailbox:** consumed through `2026-06-14T19:52:48Z` (Rule #8 discharged this session). 6 events read incl. the operator-directed verify-request.
- **Pod `07ed667`: STOPPED** by the user → idle-GPU billing closed, the carried stop-decision is **DISCHARGED**. Memory `pod-ssh-credential.md` updated; next pod task (Wave-3 Route-A) must re-ask the user to START + re-confirm SSH.

## OWED BY operator-1 — **A1 Lane V on `23c99e3` (TRIGGERED, NOT STARTED)** ⬅ the carry
- **Rows:** `has-char-lora-hole` (W2 MAJOR, quality_max.py:1060) + `secondary-lora-hole` (W2 MEDIUM, quality_max.py:1119) — same root, one commit.
- **Impl ≠ verifier:** impl = director-1-orchestrated subagent. You are the cold verifier — dispatch `lane-v-verifier` (cold-context, MUST NOT cite the director's reviewer findings, Rule #9).
- **Brief:** `docs/superpowers/briefs/2026-06-15-has-character-decouple.md`. **Verify-request:** mailbox `2026-06-14T18-44-24Z-director-to-operator-verify-request.md`.
- **THE verification that matters (pins are necessary-but-insufficient):** `"700" in wf` only proves node-700 *presence*. The trap the director flagged: a lora-only shot prunes PuLID(100); the FLUX-incompat bridge can bypass to base UNet `[112,0]`, leaving **node 700 PRESENT BUT ORPHANED** (LoRA loaded, render ignores it). **Independently re-derive the 4 shot cases** (landscape / face-only / lora-only / face+lora) and confirm **node 700 is REACHABLE from `BasicGuider(22)` via model edges** for the lora-only case (`has_face_ref=False, has_char_lora=True, char_lora` set). New test `test_lora_only_shot_node_700_reachable_from_guider`.
- **Non-vacuity / mutation test (mandatory):** mutate `_surviving_model_src` to return `"112"` (or `pulid_target`→`("112",0)`) and confirm the reachability test goes **RED**. Prove the guard is load-bearing.
- **ADR-027 doctrine (cite executed, not status):** your GO must cite the **`--runxfail` RED→GREEN** you actually ran, never the inventory `status` column. (`env -u GIT_INDEX_FILE python -m pytest <pins> --runxfail -q`.)
- **On GO →** the **coordinator** reconciles `open`→`verified` (it owns the hot inventory doc while online; both rows currently read `open`/`fixed`). Emit the verdict as a `verification-report` mailbox event via `coordination/bin/send-event`, NOT chat (Rule #19). No cross-cutting lock on these (Pair-A lane-only, quality_max.py).

## SECONDARY owed — idgate-failopen MAJOR→CRITICAL ratification (R-VERIFY-TIER)
- Director-1 requested operator-1 ratify the S12 PROVISIONAL severity upgrade (mailbox `2026-06-14T18-59-36Z`; brief `9fd367d` / `docs/superpowers/briefs/2026-06-15-idgate-failopen.md`). First-hand trace given: prod `DEEPFACE_AVAILABLE=False` → `validate_identity_vision` is the EXCLUSIVE gate; 3 error fallbacks return `confidence:0.7` → forged PASS for every standard tier (only strict-portrait .75 escapes); a 3rd error site `:278-280` was added to the S12 list.
- **Non-urgent** (director said so): the idgate **fix has NOT landed** (gated on director2 Tier-A co-sign, dispatch held at `11ebe90`). **Fold this ratification into the idgate-fix Lane V when it lands** — or confirm sooner if you want the wave-gate CRITICAL count settled. `idgate-failopen` is **CROSS-LANE** (Pair-A identity policy in Pair-B `phase_c_vision.py`) → Tier-A co-sign owed before dispatch (director2 side).

## DOCTRINE ADOPTED — ADR-027 (`ededed1`/`7957c7a`, all seats)
- **A status-tally "GATE MET" is NOT evidence of correctness.** `wave_gate_check.py` reads the inventory `status` string and runs ZERO tests. **Cite what was mechanically EXECUTED** (operator GO `--runxfail` RED→GREEN), never the status column.
- FIX-1 (routed to Pair-B director): rewrite `wave_gate_check.py` to EXECUTE wave pins → will likely **re-grade Wave-1 "MET 8/8" → UNMET** for any test-infeasible / non-XPASS-clean row (intended, user-ratified). Test-infeasible rows become **`attested`**, not `verified`. FIX-5: from Wave-2 on, a wave won't close without ≥1 committed product-oracle artifact in `logs/` (R-MEASURE).

## Sharp edges (this session)
- **Both indexes polluted.** The per-seat `GIT_INDEX_FILE` carried **1222 skip-worktree entries** + staged "deletions" of live peer files; the real `.git/index` was ALSO dirty. `git status` AND `git diff --stat HEAD` both lie. **Truth = disk existence (`ls`) + `diff <(git show HEAD:path) path`**; the 3 `MM` production files (`cost_tracker.py`, both controllers) verified byte-identical to HEAD. **A bare `git commit` would revert peer money-lane fixes** — `env -u GIT_INDEX_FILE` + explicit pathspec only.
- **Rule #7 + #8 earned their keep.** I nearly wrote a "HOLD, nothing pending" handoff — false. HEAD moved `dd6377a`→`7957c7a`→`b5158f1` and 6 unread events landed (incl. the verify-request directed at me) *while I worked*. Re-anchor + read-mailbox-before-asserting is the guard.
- **Stale session-start orientation is normal on a hot tree.** `seat_status.py` is a snapshot; peers come online mid-session. Re-run orientation right before acting, not just at start.

## NEXT operator-1 — entry point
1. `seat_status.py operator --wave 2` + re-run the suite at current HEAD (expect the A1 pins to be live regressions now).
2. **Run the A1 Lane V on `23c99e3`** (§OWED) — read the brief + the stub-contract spec `docs/superpowers/specs/2026-06-15-wave2-stub-contract.md` first; dispatch cold `lane-v-verifier`; do the reachability re-derivation + mutation test yourself; cite executed `--runxfail` (ADR-027); emit `verification-report`; coordinator reconciles on GO.
3. Then idgate ratification (fold into the idgate-fix Lane V when it lands).
