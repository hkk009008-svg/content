# Handoff - operator - 2026-06-27 testcov Tier-1 GO standby

READ FIRST AS `operator` (Pair-A). Trust current git, mailbox bodies, ref-bus
cursor, gate output, and capacity packets over this snapshot if they diverge.

Generated: `2026-06-27T02:28:38Z`
Seat: `operator`
Repo: `/Users/hyungkoookkim/Content`

## Refresh First

```bash
# NOTE the launch caveat below FIRST — this seat may come up with a bogus
# GIT_INDEX_FILE=/index-operator (root, read-only). Export the correct one:
export GIT_INDEX_FILE="$(env -u GIT_INDEX_FILE git rev-parse --absolute-git-dir)/index-operator"
[ -f "$GIT_INDEX_FILE" ] && git read-tree HEAD   # re-seed if stale (everything-deleted illusion)

.venv/bin/python .claude/skills/four-seat-protocol/scripts/seat_status.py operator --wave 5
env -u GIT_INDEX_FILE git log --oneline -8
.venv/bin/python scripts/consume_bus.py operator      # ref-bus reader (consume-events is legacy)
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
```

Use `env -u GIT_INDEX_FILE` for ordinary git/pytest. Push, lock claim/release,
pod/API spend, dependency edits, production generation, and inventory
transitions remain user-gated.

## Current Operator State

`operator` processed the Pair-A **Tier-1 web test-coverage** verify-request from
the active test-coverage-closure campaign (coordinator route
`2026-06-26T23-10-00Z-coordinator-to-all-coordination.md`).

Verify-request consumed:

```text
coordination/mailbox/sent/2026-06-27T01-53-31Z-director-to-operator-verify-request.md
```

Target director commits (Pair-A Tier-1 batch):

```text
a3e067d3 test(web): api_serve_file guard containment      -> tests/unit/test_api_serve_file.py
5148f020 test(web): destructive and state endpoints       -> tests/unit/test_api_state_and_destructive.py
5bba97ff test(web): generation and approval gate endpoints -> tests/unit/test_api_gate_endpoints.py
```

Operator GO commit:

```text
f3f85b1f operator(verify): GO Pair-A Tier-1 web test batch -> director [testcov T1]
```

GO event:

```text
coordination/mailbox/sent/2026-06-27T02-03-37Z-operator-to-director-verification-report.md
```

Verdict: **GO** (pushed to origin/main). Test-only, lane-only, no network/spend,
**no lock** (no cross-cutting module touched — no §6b release applies).

## Verification Evidence

impl≠verifier: director authored; operator did not. Review spec = the coordinator
route + the verify-request (no standalone R-BRIEF existed). Two **cold-context**
reviewers dispatched independently (Rule #9 — neither prompt cited the director
preflight or each other); both returned GO and traced each module's primary guard
to a concrete failure-on-removal (load-bearing, not false-green).

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_api_serve_file.py \
    tests/unit/test_api_state_and_destructive.py tests/unit/test_api_gate_endpoints.py -q
-> 31 passed in 1.51s   (operator cold run; matches director preflight 31 passed/1.59s)

mutation-reasoning (reviewers, traced vs web_server.py):
-> serve_file:    drop traversal guard (web_server.py:1718) -> /etc/passwd 200 not 403 -> test fails
-> delete_project: drop busy fence (web_server.py:558) -> delete called + 200 not 409 -> test fails
-> gate endpoints: drop @_project_lock_guard / success-map -> wrong status -> test fails

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
-> RESULT: no ceremony detected; OK
```

## Findings carried (none blocking — recorded in the GO report)

1. **MINOR** — `tests/unit/test_api_state_and_destructive.py:58` —
   `assert_called_once_with(pid, timeout=pytest.approx(5.0, abs=10.0))` accepts any
   timeout in [-5.0, 15.0]; real `HTTP_PROJECT_TIMEOUT = 2.0` (web_server.py:112) and
   the inline comment "usually 5 or 15" is factually wrong. Unfalsifiable bound.
   Disposition: advisory fold-in — tighten to the real constant. (Both reviewers flagged.)
2. **INFORMATIONAL** — commit `a3e067d3` also deleted the binding coordinator route
   artifact `…2026-06-26T23-10-00Z-coordinator-to-all-coordination.md` (out-of-scope /
   non-pathspec sweep hazard). **Already fully remediated** by `98bf2ca1`:
   `git diff 98e9a3a6 HEAD` on that path is empty. No residual damage. Recorded for
   explicit-pathspec discipline.
3. **INFORMATIONAL** — no standalone Pair-A R-BRIEF for this batch. Did not block
   verification. Recommend a real R-BRIEF for the upcoming **Tier-3 Orchestration**
   work (`cinema/shots/controller.py`), which touches live state-mutation logic
   rather than test-only files.

## Launch Defect Caveat (matches the coordinator-seat note)

This session came up with `GIT_INDEX_FILE=/index-operator` — an absolute path on the
**read-only root FS**, not the correct `<git-dir>/index-operator`. Symptoms it
produces if uncorrected:
- `git status` / `git diff HEAD` (without `env -u GIT_INDEX_FILE`) report a bogus
  "everything deleted" (saw 2053 "deletions") — the env var, NOT real tree drift.
- `coordination/bin/send-event` fails: `Unable to create '/index-operator.lock':
  Read-only file system`.

Fix (applied this session for the GO commit; **relaunch the seat with the correct
export** so it does not recur): per `coordination/README.md:310` —
`export GIT_INDEX_FILE="$(git rev-parse --absolute-git-dir)/index-operator"` then
`git read-tree HEAD` to seed/re-seed from HEAD. The per-seat index is operator-private
(director/operator2 use their own), so re-seeding discards only stale operator staging.

## Current Boundary

Operator has **0 unread** (live ref-bus recompute, cursor 765 — not STATE.md) and no
remaining owed Lane-V. The GO report and commit are pushed. No lock release applies.
HEAD `f3f85b1f` == origin/main (in sync).

## Exact Next Trigger

```text
director ships Tier-3 Orchestration tests (cinema/shots/controller.py) + sends a
per-component verify-request -> operator Lane V (GO/NITS/FAIL)
```

Until then, operator stands by. Per the coordinator route, Pair-A operator's scope is
Tier-1 (done) + Tier-3 Orchestration verification; Pair-B (director2/operator2) owns
Tier-2 + Tier-3 Audio DSP independently.
