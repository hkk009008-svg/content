# HANDOFF — threeway scope-b sub-project 1 IMPLEMENTED + independent Lane-V **GO**

**Date:** 2026-06-23
**HEAD at handoff:** `main` @ `affe1454` (== origin/main; 0 ahead / 0 behind). Verify with `git log -1`.
**Live oracle:** `git for-each-ref refs/threeway/` · `git ls-remote origin 'refs/threeway/*'`.

> Trust git + the oracle, not this prose. Re-anchor (`git fetch`; ahead/behind) before any commit/push.

## 0. TL;DR

Scope-b **sub-project 1 (minimal operable mechanical-seat runtime)** is **implemented, pushed, and
independently Lane-V verified GO (with non-blocking NITS).** All 10 plan tasks landed across 13 commits
(`859f4d37`…`affe1454`, all on origin/main). The walking-skeleton drives a full **T1 brief→merge** through
the real CLIs as subprocesses + the daemon `--run-once`, advancing the protected **TEST** ref
`refs/threeway/test-main` (real `refs/heads/main` untouched). An independent Lane-V workflow
(`wf_1f903155-0cc`; 5 cold-context verifiers + 18 executed mutations + 3 adversarial refutations)
re-derived **GO** — every safety/authority guard is mutation-proven load-bearing.

## 1. What is operable now (the three mechanical seats)

| Component | File | Role |
|---|---|---|
| Overseer authority CLI | `scripts/overseer_emit.py` | 6 overseer facts (brief/assignment/cycle_go/release_order/approver_roster/re_verify_challenge), signed with the overseer key ONLY |
| Interactive-seat shim (TEMPORARY) | `scripts/bootstrap_emit.py` | candidate + release_requested (coordinator key) + both attestations (primary_verifier key); replaced by sub-project 2 |
| Merge-gate daemon | `scripts/run_merge_gate.py` | hardened: TEST-ref default (DD-1), `--remote` (DD-3), SIGTERM/SIGINT clean-shutdown (exit 0, stop-at-top) |
| Daemon wrapper | `scripts/run_merge_gate.sh` | passes `--main-ref refs/threeway/test-main` + `--remote origin`; NO PYTHONPATH (DD-2) |
| CI signer | `scripts/sign_ci_result.py` | already operable (ADR-055); folded into the bare-subprocess pin |

Operating model = **human-operated signing CLIs** against the **TEST** ref. Real `refs/heads/main`
promotion is deliberately NOT wired (hardening track). ADR-056 (DECISIONS.md) records DD-1..DD-5;
DD-1 (TEST-ref default — a behavior change to an existing CLI) is recorded **USER-RATIFIED 2026-06-23**.

## 2. Lane-V verdict — GO (with NITS)

**Evidence artifact:** `logs/verify-adr056-scope-b-sp1-lane-v.json` (R-MEASURE instrument output).
**Baseline:** threeway suite `376 passed, 1 skipped`; `ci_smoke` OK; `check_no_ceremony` clean.

- **5 dimensions all GO/NITS** (overseer_emit, bootstrap_emit, merge-gate daemon [keystone], E2E,
  docs/scope/ceremony). No CRITICAL/MAJOR, no scope violations, all 6 acceptance criteria backed by real tests.
- **18 mutations executed; 15 RED-as-expected** — including the keystone DD-1 (revert default →
  `refs/heads/main` ⇒ pin fails), stop-at-top, exit-0-not-130, both wrapper guards, overseer-key
  enforcement, the envelope-vs-payload `subject_sha` split, nonce-freshness, both attestation SHA
  bindings, distinct attestation ids, and "drop `release_order` ⇒ E2E ref refuses to advance."
- **3 stayed-green mutations were adversarially refuted as non-defects (high confidence each):**
  (a) `brief_version` IS in the cycle_go payload (no live bug); (b) pre-signing is harmless because
  `store.append` always re-signs over the real seq (correct-code property); (c) `release_requested` is a
  signal-only daemon trigger the predicate never consults (a forged one only wastes a gate run).

## 3. NITS (non-blocking; optional test-strengthening — NO xfail owed, no confirmed unfixed defect)

1. `test_threeway_overseer_emit.py`: assert `cg.payload['brief_version']==1`; add an `AppendContentionExceeded`→rc1 pin (DD-4 contention path untested); optional wrong-key mutation pin for `release_order`/`re_verify_challenge`.
2. `test_threeway_bootstrap_emit.py`: assert `release_requested` signer seat == `coordinator` (one-liner, makes the coordinator-key claim mutation-testable); add an unclean-merge (conflicting-branch) fixture.
3. `test_threeway_merge_gate_daemon.py`: the `.sh` wrapper is content-scanned, never executed — add a `run_merge_gate.sh --run-once` smoke.
4. `run_merge_gate.py:105-106`: per-iteration `except` swallows infra errors with no structured persistent-failure signal (monitoring gap, not correctness).
5. `test_threeway_e2e_walking_skeleton.py`: redundant `monkeypatch.setenv(THREEWAY_KEYSTORE)` (comment or drop); pass `--remote ''` to `sign_ci_result` for symmetry; add an explicit assert that real `refs/heads/main` is unchanged.
6. **PRE-EXISTING / out-of-scope:** `DECISIONS.md:2718` stale-looking SHA `a38a3d69` (a subagent run-id in the ADR-054 block that `ci_smoke` false-positives as a commit); design-spec sys.path anchor `:19-22` should be `:20-22`.

## 4. NEXT (chief/user prioritization — per the plan, "in whatever order the chiefs prioritize")

1. **Push** the verification artifacts (`logs/verify-adr056-…json` + this handoff) — implementation commits are already on origin.
2. Pick the next track:
   - **Automation track** (`overseer-plan` auto-decompose, spec §7) — turns one chief decision + bus state into the ordered emit sequence; first step toward the automated overseer. Sits ABOVE the manual `overseer_emit` this slice built.
   - **Hardening track** (gates production sign-off → real-`main` promotion): CI attestor, external trust anchor, ref-ACL/append-only enforcement, liveness/recovery (wire the dead `rework.py` ESCALATE breaker), key rotation/revocation.
   - **Sub-project 2**: real seat↔bus wiring (interactive seats emit/consume bus events) — removes `bootstrap_emit.py`.
3. Optional: fold the §3 NITS into a small follow-up (a fresh implementer; impl≠verifier — the verifier seat must not author them).

Also still open (pre-existing background, from the go-live session): the 6 `coordination/mailbox/seen/*.txt`
(ISO→scalar) + `coordination/mailbox/.migration/` rollback manifest are uncommitted — decide whether to
commit them for durable migration rollback.

## 5. Sharp edges (this session)

- **Lane-V mutation pass edits the live tree** — it was run by a single sequential agent that restored every
  file via `git checkout HEAD -- <file>`; final `git status` showed ONLY the pre-existing cutover artifacts
  (tree clean). Never run parallel mutation agents on the shared tree without worktree isolation.
- **`send-event` writes the OLD mailbox + stages; it does NOT push the live signed bus** (`refs/threeway/events`).
  With all seats offline, the durable Lane-V record is the committed `logs/` artifact + this handoff, not a
  mailbox event with no reader.
- **`ci_smoke` R3/R4 now PASS** — the plan (line 820) warned they "may remain RED pending FIX-1/FIX-2"; that
  wave-gate ceremony work has since landed, so this slice ships into a clean ceremony gate.
- Mandatory `env -u GIT_INDEX_FILE` prefix on all threeway python (per-seat index pollution); repo python is `.venv/bin/python` (no bare `python` on PATH).
