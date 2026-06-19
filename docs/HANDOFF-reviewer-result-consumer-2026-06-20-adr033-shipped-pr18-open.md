# HANDOFF — ADR-033 reviewer-result consumer: ✅ MERGED to main (`fe3411db`)

**Date:** 2026-06-20 · **Branch:** `feat/reviewer-result-consumer` · **Status:** ✅ **MERGED to `main`**
via [PR #18](https://github.com/hkk009008-svg/content/pull/18) (merge commit `fe3411db`). All CI green
(ARCHITECTURE.md §15 smoke / TypeScript / pytest tests/unit/). **Nothing outstanding.**

## TL;DR — what's the state

ADR-033 (the deferred follow-up of ADR-032 Decision 5) is **DONE and MERGED to `main`**
(merge `fe3411db`, 2026-06-20). Getting there required fixing several **pre-existing,
unrelated** failures that a long-broken CI gate had masked — see "Merge journey" below.
**Nothing outstanding for ADR-033.**

## Merge journey — what else had to be fixed to reach green (all pre-existing, unrelated to ADR-033)

Making PR #18's CI actually pass surfaced issues the long-broken pytest gate had hidden:
- **gen4 stale test** (`a92a2389`) — `test_phase_c_video_aspect.py::TestRunwayGen4Model` mocked `urllib.urlretrieve` while the code moved to `performance._net.safe_download`; on a fake URL it cascaded to the gen3a engine and asserted the wrong model/ratio. Fixed the mock boundary.
- **CI pytest gate was structurally timing out** — `ci.yml` `pytest-unit` had `timeout-minutes: 15`, but the suite ran ~27 min (tests making real network calls), so the job was killed on **every** branch incl. `main` (its runs all show "cancelled"). A check that can never complete is itself ceremony (ADR-028).
- **lock-protocol branch-determinism** (`d388aae9`) — `test_lock_protocol.py` assumed git's default branch is `main`; CI defaults to `master`, so the `two_clones` fixture left seatB on the wrong branch and the lock-collision the test asserts never happened. Pinned seatB to `main`+upstream; verified 7 passed under **both** `main` and `master`.
- **offline-suite restoration** (`6b43320c`, the B2 follow-up) — mocked 6 network-touching tests at the boundary the code actually crosses (`safe_download` / `fal_client` / `urllib.urlopen` / …), taking the suite from ~27 min → **~2 min offline (2947 passed, zero sockets)**, restored the CI timeout 40→15, and wired `check_no_ceremony` into CI. The pytest gate is functional again for the first time in a while.

Final merged range = `2a932ac0..6b43320c` (11 commits + the `origin/main` integration merge `db8d7218`).

## What landed (ADR-033 core, 6 commits, `2a932ac0..9bb70fc3`)

| commit | what |
|---|---|
| `b306c66c` | `scripts/consume_reviewer_result.py` — parse `reviewer-result/1` / schema-validate / **fabrication re-run** / severity map / inventory-transition proposals (propose-only) |
| `73230f23` | `check_no_ceremony.py` **R6** (`report-cites-executed-pin`) + wire consumer into `ci_smoke` (schema-validation half only) |
| `21233442` | **ADR-033** in `DECISIONS.md` + plan "Deferred follow-up" marked DONE |
| `b08add6f` | `fix(consumer)` — close the ACE class in `safe_pytest_argv` env-prefix + launcher vetting (added 4 security-regression pins) |
| `db8d7218` | merge `origin/main` (Slice-2.5 handoff doc `d33bbec0`) — clean, no conflicts |
| `9bb70fc3` | doc-sync — corrected ADR-033 Decision 6(c) launcher policy + `83→87` count to match the final code |

Deliverable per ADR-033: consumer CLI + `smoke_check()` + R6 + ci_smoke wiring. The
mailbox-level JSON block **STAYS OPTIONAL** (Decision 5 — promoting it to MANDATORY is a
separate future decision, NOT done here). R6 is **inert until reviewers emit blocks** (zero
in the mailbox today) — it has teeth the moment they do.

## Verification evidence (re-run on settled HEAD `9bb70fc3`; all green)

- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_consume_reviewer_result.py tests/unit/test_check_no_ceremony_r6.py -q` → **87 passed** (79 consumer incl. 2 real-pytest fabrication integration tests + 8 R6)
- `.venv/bin/python scripts/ci_smoke.py` → **OK** · `.venv/bin/python scripts/check_no_ceremony.py` → exit 0, R5+R6 PASS
- R6 **non-vacuity** proven: a crafted `pass` report with no `--runxfail` command → `rule_report_cites_executed_pin` returns FAIL
- Neighboring guard suites (`test_check_doc_claims`/`test_check_coordination`/`test_coordination_bin`/`test_four_seat_coordination`) → **204 passed**
- Security re-proof (black-box): 7 ACE vectors refused, 3 legit forms accepted; out-of-repo launcher refused by `recheck_commands`, the legit `.venv/bin/python` launcher still **executes** (symlink false-positive avoided)
- Live fabrication demo: CLI fed a report claiming "42 passed" for a pin whose real run is "1 passed" → `FABRICATION DETECTED`, exit 1

## The re-runner security design — DO NOT REGRESS

`safe_pytest_argv` + `_path_escapes_repo` + `_pytest_args` enforce STRUCTURE on an
**untrusted** mailbox command string handed to `subprocess.run(argv)` (never `shell=True`):
1. no shell metacharacters; shlex-parseable.
2. pytest must be **executed** (`<python> -m pytest …` or a `pytest` console script), not merely a present token (`python evil.py pytest` refused).
3. `env` prefix may carry only `-u NAME` unsets — NO `NAME=value` assignment (`env PATH=/evil pytest` injection refused); the `env` token must be the bare word (a path-y `/tmp/evil/env` does not qualify).
4. the launcher must **carry a path separator** and resolve to an in-repo path or `sys.executable` — a **bare PATH-resolved name is refused** (it is the PATH-redirection vector), and an absolute out-of-repo path (`/tmp/evil/pytest`) is refused.
5. pytest **targets** are confined to `repo_root` (out-of-repo `conftest.py` refused).

Key subtlety a future editor will trip on: `.venv/bin/python` is a **symlink OUT of the
repo** (`→ python3.13`), so confining the launcher with naive `.resolve()` would wrongly
SKIP the repo's own canonical re-run. That's why the launcher is vetted via
`_path_escapes_repo(..., allow_sys_executable=True)` and `_pytest_args` separates the
launcher from targets. If you "simplify" this, re-run the C1/C2 security tests — they pin it.

## Sharp edges learned this session (read before touching the shared tree)

- **Concurrent SUBAGENTS edit + commit the SAME task on the shared working tree, mid-session.** This session the consumer file was rewritten ~4× and committed 4× by intended subagents *after* my own review workflow ended. My verification was stale until I gated on it. **Verify against the SETTLED tree:** confirm file-hash stability (e.g. a background `until`-loop watching `md5`) before trusting any test run; re-anchor on git refs (`git rev-parse HEAD`, `git status`) before/after. A "completed" workflow notification does NOT mean every spawned process has stopped.
- **Two-dot `git diff origin/main..HEAD` on a branch that is BEHIND its target shows the target's newer commits as spurious "deletions."** Here it falsely implied my branch deleted the Slice-2.5 handoff. Use `git diff $(git merge-base origin/main HEAD)..HEAD` (or three-dot `origin/main...HEAD`) for "what my branch actually changes."
- **Dispatch cold review fan-outs with a read-only agent type** (`lane-v-verifier`: Read/Grep/Glob/Bash) — NOT the default full-tool workflow agent. A reviewer that can Edit/Write can silently mutate the artifact it reviews. (My review workflow had full tools; it only read + built a PoC here, but it *could* have edited.)
- `.tmp.driveupload/` at repo root is **unrelated Google-Drive temp junk** (untracked) — leave it, never `git add` it.
- Own-seat commit form: PLAIN `git commit -m "..." -- <paths>` (explicit pathspec, `-m` before `--`, no `env -u`); the hook blocks only a bare no-pathspec commit. Index was clean this session (0 skip-worktree).

## Pointers

- ADR-033: `DECISIONS.md` (tail) · ADR-032 (the schema this consumes) · ADR-027/028 (execute-the-oracle / ceremony-forbidden)
- Plan: `docs/superpowers/plans/2026-06-19-harden-verification-dispatch.md` (Deferred follow-up, marked DONE)
- Schema contract: `docs/templates/claude/reviewer.md` (`reviewer-result/1`)
- The consumer CLI: `.venv/bin/python scripts/consume_reviewer_result.py <event.md>` (re-runs pins; tree must be at the reviewed commit) · `--stdin` also supported

## Status: DONE — no actions outstanding

1. ✅ **MERGED to `main`** (`fe3411db`, PR #18). ADR-033 core + the four pre-existing-failure fixes above are all on `main`, CI green. This handoff is now an archival record (its filename still says "pr18-open" — historical).
2. The broader program-hardening campaign (REMEDIATION-INVENTORY, Slice 2.5 migration-plan authoring) is separate work — see the campaign handoffs, not this one.
3. (Deferred, no date — do NOT action speculatively) ADR-033 Decision 5: promoting the mailbox-level JSON block to MANDATORY is a future decision, gated on reviewers emitting blocks in practice + the consumer being exercised on real events.
