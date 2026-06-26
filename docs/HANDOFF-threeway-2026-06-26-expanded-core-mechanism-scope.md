# Handoff: Three-Way Expanded Core Mechanism Scope

Date: 2026-06-26
Mode: Codex readiness bridge
Seat: none claimed

## Supersession

This pre-implementation scope handoff was superseded by
`docs/superpowers/specs/2026-06-26-threeway-expanded-core-mechanism.md` and
`docs/superpowers/plans/2026-06-26-threeway-expanded-core-mechanism.md`, then implemented on branch
`antigravity-harness-adoption` through the Task 1-8 commit sequence. It is retained as the durable
scope-transfer artifact that preceded the approved spec/plan.

## Trigger

The user asked Codex to read the three-way protocol under `docs/` and implement it
as a core mechanism. After the first bounded option set, the user selected the
bus-first Codex core path (`1`) and then expanded the scope:

> no include t2/t3 and any other problems that are not addressed also

No implementation has started. This handoff preserves the repo-grounded scope and
next trigger before any context transfer.

## Current State Evidence

Readiness and mailbox orientation were performed without consuming mailbox
cursors.

```text
$ .venv/bin/python scripts/continuation_readiness.py
role: readiness bridge
head: a8a5fba5 feat: Adopt Three-Way Protocol via Antigravity harness skill
mailbox: read-only; all seats unread=0
cursors: director=768 director2=767 operator=765 operator2=766 coordinator=764 coordinator2=764
wave 2 gate: MET
check_no_ceremony: clean except pre-existing R2 WARN on cv2 importorskip
smoke: not run by this command
```

```text
$ .venv/bin/python scripts/mailbox_monitor.py --once
generated_at: 2026-06-26T10:51:28Z
latest coordinator broadcast: 2026-06-17T08-51-24Z-coordinator-to-all-coordination.md
all seats unread=0
pair heartbeats: STALE 8d14h
coordinators: n/a
```

```text
$ env -u GIT_INDEX_FILE git status --short
<clean before this handoff file>
```

```text
$ env -u GIT_INDEX_FILE git log --oneline -8
a8a5fba5 feat: Adopt Three-Way Protocol via Antigravity harness skill
be496b8e Merge pull request #24 from hkk009008-svg/claude/confident-poitras-19b467
a37d25f9 feat(threeway): finish ADR-062 de-degrade -- seat_status + STATE.md hook read the live ref-bus [ADR-063]
25d9f04a chore(threeway): commit the Slice-2.5 cursor migration -- seen/*.txt ISO->scalar + reversible manifest [ADR-062/ADR-034]
86d1bfc6 docs(threeway): address Lane-V verification NITs (stale refs, tighter assert, estimate labels) [ADR-062]
67ea66c7 feat(threeway): de-degrade legacy unread surfaces to the live ref-bus; consume-events refuses scalar cursors [ADR-062]
32deadb2 perf(threeway): RefEventStore.iter_events_since -- O(unread) cursor-relative bus read [ADR-062 DD-3]
48b33841 feat(threeway): bus_unread -- real ref-bus unread for migrated (scalar-cursor) seats
```

Local and remote bus refs matched at handoff time:

```text
$ env -u GIT_INDEX_FILE git for-each-ref refs/threeway/ --format='%(refname) %(objectname)'
refs/threeway/cursors/coordinator c8b655041e9ab47fe105f0207040a59f1df7c355
refs/threeway/cursors/coordinator2 c8b655041e9ab47fe105f0207040a59f1df7c355
refs/threeway/cursors/director dc763bf5dc2825e38546f1bf3c168a7a4382a9e3
refs/threeway/cursors/director2 3efc6163adf1fdf93d0e46720db5086fa7a7b636
refs/threeway/cursors/operator c099824b749c254be1d598d029b54be34a9aefad
refs/threeway/cursors/operator2 3e6c7aa1c51fb8d96171884cdd1d74b46a927d90
refs/threeway/events df80e8180d9856cfed134d87ef2a460aa2f1e693

$ env -u GIT_INDEX_FILE git ls-remote origin 'refs/threeway/*'
<same seven refs and object IDs>
```

## Repo-Grounded Findings

Already-live core:

- `scripts/consume_bus.py`, `scripts/seat_emit.py`, and
  `scripts/bus_unread.py` exist.
- `scripts/bootstrap_emit.py` is absent, consistent with ADR-061 retirement.
- `docs/HANDOFF-threeway-2026-06-26-SP2-executed-4-phases-lane-v-go-pushed.md`
  reports SP2 live: `consume_bus` and `seat_emit` are the T1 path, and
  `bootstrap_emit` is retired.
- `threeway/tier.py` already enforces T2/T3 policy at read/gate time.
- `threeway/reducer.py` already folds T2/T3 and revocation-like facts including
  `co_sign`, `re_verify`, `human_approval`, `attestation_revoked`,
  `brief_superseded`, `approver_roster`, and `re_verify_challenge`.
- `scripts/overseer_plan.py` already emits T3 overseer-plan facts
  `approver_roster` and `re_verify_challenge`.

Known unresolved gaps to include, not defer silently:

- `scripts/seat_emit.py` is T1-only today. Its authority map covers
  coordinator candidates/release requests/aborts and operator attestations, but
  not `co_sign`, `re_verify`, `human_approval`, or `attestation_revoked`.
- `scripts/overseer_emit.py` supports overseer facts such as `brief`,
  `assignment`, `cycle_go`, `release_order`, `approver_roster`, and
  `re_verify_challenge`, but not `brief_superseded` or a revocation CLI.
- ADR-061 explicitly leaves T2/T3 emission as follow-on work:
  `attestation_revoked`, `co_sign`, and `re_verify`; human approval is test-built
  or manual today, not a principal-safe CLI flow.
- Several `docs/protocol/threeway/*` files still contain stale adoption-era
  claims such as "wired into nothing", "legacy mailbox bus still live", or
  "keys not provisioned". These need doc sync after the executable design lands.
- Real-main operation remains a hardening track. Existing safe paths target
  `refs/threeway/test-main`; production `main` requires guardrails for required
  CI, trust-anchor/ref-ACL checks, key lifecycle, and break-glass behavior.

## Expanded Implementation Scope

The next agent should treat the request as: make the signed three-way bus a core
Codex mechanism, including T2/T3 and known unresolved protocol problems.

Recommended tracks:

1. Gap ledger: create a repo-truth inventory of already-live, partially-live, and
   missing three-way mechanisms. Separate T1, T2, T3, revocation/supersession,
   CI attestation, real-main guardrails, key lifecycle, and docs drift.
2. Bus-first Codex core: make Codex/four-seat readiness, continuation, mailbox,
   and state surfaces prefer the signed bus for three-way protocol state while
   preserving free-form mailbox artifacts where appropriate.
3. Authority-complete emitters: add CLI paths for T2 `co_sign`, T3 `re_verify`
   and `human_approval`, plus revocation/supersession facts such as
   `attestation_revoked` and `brief_superseded`, with key-bound authority checks.
4. T2/T3 walking skeletons: add focused tests and scripts that produce and gate a
   complete T2 and T3 path on `refs/threeway/test-main`, including negative cases
   for missing co-sign, stale challenge nonce, and missing required human
   approvals.
5. Hardening track: handle CI attestor gaps, required-CI/dead-config checks,
   richer attestation payloads, key rotation/revocation/break-glass policy,
   ref-ACL/trust-anchor preflight, and explicit real-main safety boundaries.
6. Docs sync: update stale three-way docs only after executable behavior is
   pinned by tests and commands, citing verifying commands next to factual claims.

## Next Trigger

If the user says `continue threeway expanded core spec` or otherwise approves
this expanded scope, write a spec first, then review it before code:

`docs/superpowers/specs/2026-06-26-threeway-expanded-core-mechanism.md`

The spec should preserve the tracks above, name the exact files to change, define
acceptance tests, and explicitly identify any deferred gap with either a strict
xfail pin or a `test-infeasible` handoff reason.

Do not start implementation from this handoff alone unless the user explicitly
approves the design/spec gate or gives a newer direct instruction that overrides
it.

## Side Effects

- No mailbox cursor was consumed.
- No seat was claimed.
- No commit, push, or merge was performed.
- This handoff file is the only intended worktree change from the handoff step.
