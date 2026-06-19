# HANDOFF (next instance) — 2026-06-20 session wrap: ADR-033 shipped + CI pytest gate restored

**`main` is at `970ce907`** (verify: `git rev-parse origin/main` — local `main` may be stale; see warnings). All
work below is **merged to `main`, CI green**. Nothing is mid-flight from this session. This is an
orientation doc, not a task with owed steps.

## What shipped this session

1. **ADR-033 — reviewer-result consumer** (the deferred follow-up of ADR-032 Decision 5). `scripts/consume_reviewer_result.py` (parse `reviewer-result/1` → schema-validate → **fabrication re-run** → severity map → propose-only inventory transitions), `check_no_ceremony.py` **R6** (`report-cites-executed-pin`), and `ci_smoke` wiring. The re-runner executes untrusted mailbox command strings, so it's hardened (no shell; structural pytest-only launcher vetting; `env -u NAME` prefix only, no `NAME=value` assignments; launcher + targets confined to repo_root with a `sys.executable` allowance for the `.venv` symlink). Details: `DECISIONS.md` ADR-033.

2. **Four pre-existing, unrelated failures** that a long-broken CI gate had masked — all fixed en route to a green merge:
   - **gen4 stale test** — `test_phase_c_video_aspect.py::TestRunwayGen4Model` mocked `urllib.urlretrieve` while the code moved to `performance._net.safe_download`; on a fake URL it cascaded to the gen3a engine.
   - **CI pytest gate was structurally timing out** — `ci.yml pytest-unit` had `timeout-minutes: 15` on a ~27-min suite, so the job was killed on **every** branch incl. `main` (runs showed "cancelled"). A check that can never complete is itself ceremony (ADR-028).
   - **lock-protocol branch non-determinism** — `test_lock_protocol.py`'s `two_clones` fixture assumed git's default branch is `main`; CI defaults to `master`, so seatB ended up on the wrong branch and the lock collision never happened. Pinned seatB to `main`+upstream.
   - **offline-suite restoration** (the B2 follow-up) — six tests made real network calls; mocking them at the boundary the code actually crosses took the suite **~27 min → ~2 min offline (2947 passed, zero sockets)**, restored the CI timeout 40→15, and **wired `check_no_ceremony` into CI**. The pytest gate is functional again for the first time in a while.

## ⚠️ Operating warnings — the shared working tree is HOT (this bit repeatedly)

This repo runs **many concurrent agents/seats on one shared checkout + index**. During this session the tree
moved under me constantly. Internalize these or you WILL ship wrong:

- **Concurrent subagents/peers edit AND commit the same files mid-session**, continuing past "workflow completed" notifications. Before trusting any test/verification result, gate on **content-hash stability** (e.g. a background `until`-loop on `md5`), then verify the **settled** tree. Re-anchor `git rev-parse HEAD` before/after every mutating step.
- **The checked-out branch switches under you.** A commit of mine once landed on a *peer's* branch because the checkout flipped mid-command — caught via the `[branch sha]` prefix in `git commit` output. Always `git commit -- <explicit pathspec>` (never bare), and re-check `git rev-parse --abbrev-ref HEAD` immediately before commit/push.
- **The shared index carries peer staged WIP.** Right now (session end) `main`'s index has a peer's staged `AGENTS.md` + `docs/protocol/threeway/*` manuals; a bare `git add`/commit or a forced FF would clobber it. Local `main` could NOT be fast-forwarded for this reason — **do not stash or discard peer staged work**. Work in an **isolated `git worktree` off `origin/main`** (this handoff was written that way).
- **`origin/main` is the truth; local `main` is often stale.** It moved ~15 commits during this session. Use `git diff $(git merge-base origin/main HEAD)..HEAD` (or three-dot) for "what my branch changed" — a two-dot `origin/main..HEAD` on a behind-branch shows the target's newer commits as spurious **deletions** (this caused a false "my branch deletes a doc" alarm).
- **Dispatch cold-review fan-outs with a read-only agent type** (`lane-v-verifier`: Read/Grep/Glob/Bash), never the default full-tool workflow agent — a reviewer that can Edit/Write silently mutates the artifact under review.
- `.tmp.driveupload/` at repo root is **unrelated Google-Drive temp junk** — leave it, never `git add` it.

## Open / not-done (do NOT action speculatively)

- **Unmerged peer/codex branches** exist (`codex/hf-alignment-review`, `codex/protocol-harness-audit-finish`, `capability-test-suite`, `chore/untrack-modules-fix-settings`, `claude/angry-kapitsa-*`, `codex/continue-handoff-read`). These are **other seats' work** — review before merging; do NOT bulk-merge to `main`.
- **ADR-033 Decision 5** (deferred, no date): promoting the mailbox-level `reviewer-result/1` block from OPTIONAL → MANDATORY is a future decision, gated on reviewers actually emitting blocks + the consumer being exercised on real events. R6 is inert until then (zero blocks in the mailbox).
- The broader **program-hardening campaign** (REMEDIATION-INVENTORY, Slice 2.5 migration-plan) is separate — see the campaign handoffs, not this one.

## Pointers

- ADR-033 + the merge journey: `DECISIONS.md` (ADR-033) and `docs/HANDOFF-reviewer-result-consumer-2026-06-20-adr033-shipped-pr18-open.md`.
- Consumer CLI: `.venv/bin/python scripts/consume_reviewer_result.py <event.md>` (re-runs pins; tree must be at the reviewed commit) · `--stdin` supported.
- CI: `.github/workflows/ci.yml` (3 jobs: §15 smoke / pytest tests/unit/ + wave-gate + no-ceremony / TypeScript). Suite is **offline ~2 min** — keep it that way (mock network boundaries; don't reintroduce real calls).
