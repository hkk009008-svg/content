# HANDOFF - Director (Pair-A), 2026-06-15 - subagent workflow wrap

READ FIRST AS NEXT PAIR-A DIRECTOR. Trust git, mailbox artifacts, and
`docs/REMEDIATION-INVENTORY.md` over this prose if they diverge.

## State At Wrap

- Seat: `director` / Pair-A image, identity, realism.
- Write timestamp: `2026-06-15T12:00:13Z`.
- Final durable HEAD observed before commit:
  `72a2d83c docs(handoff): operator consume director wrap`.
- Branch from live seat status: `main`, 98 ahead / 0 behind origin.
- Director mailbox consumed through `2026-06-15T12:00:13Z`; unread is 0.
- Active locks: `coordination/locks/.gitkeep` only.
- Wave 2 remains `UNMET`: `verified=17`, `open=13`.
- No committed `logs/product-oracle-*.json` artifact exists.
- Smoke was re-run in this handoff cycle and returned `OK` with existing
  advisories only.
- No production code, remediation inventory, or lock files were edited by this
  director handoff.
- Push remains user-gated.

Evidence:

```text
$ env -u GIT_INDEX_FILE git log --oneline -5
72a2d83c docs(handoff): operator consume director wrap
04912467 docs(handoff): operator consume late statuses
afb483d4 docs(handoff): operator2 lipsync costkey idle
f721c989 docs(handoff): operator multi-subagent idle
a4179748 coord(verify): add operator2 lipsync evidence addendum

$ env -u GIT_INDEX_FILE GIT_INDEX_FILE=/Users/hyungkoookkim/Content/.git/index-codex-director CODEX_SEAT=director .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director --wave 2
HEAD 72a2d83c docs(handoff): operator consume director wrap
vs origin/main: 98 ahead, 0 behind
mailbox cursor: 2026-06-15T12:00:13Z
UNREAD: 0
Wave 2 gate: UNMET counts={'verified': 17, 'open': 13}

$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep

$ find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
# no output

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected -- every relied-on green is backed by execution.
OK

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET  counts={'verified': 17, 'open': 13}
15 failed, 46 passed
```

Known smoke advisories remain: `docs/PROGRAM-MANUAL.md` doc-anchor drift,
two historical mailbox unknown-kind warnings, and two R2 invisible-green
warnings.

## Mail Processed

At handoff start, director had 2 unread all-seat events:

- `coordination/mailbox/sent/2026-06-15T11-53-43Z-operator2-to-all-verification-report.md`
- `coordination/mailbox/sent/2026-06-15T11-55-07Z-coordinator-to-all-coordination.md`

I consumed them for the director cursor:

```text
$ CODEX_SEAT=director GIT_INDEX_FILE=/Users/hyungkoookkim/Content/.git/index-codex-director coordination/bin/consume-events director
cursor director: 2026-06-15T11:48:10Z -> 2026-06-15T11:55:07Z; unread now: 0 (staged; fold into your next substantive commit)
```

During the Rule #7 pre-commit check, a newer no-op operator2 handoff appeared:

- `coordination/mailbox/sent/2026-06-15T11-58-09Z-operator2-to-all-status.md`

It says operator2 has no Lane V, NITS re-read, or verification task currently
owed. I consumed it too:

```text
$ CODEX_SEAT=director GIT_INDEX_FILE=/Users/hyungkoookkim/Content/.git/index-codex-director coordination/bin/consume-events director
cursor director: 2026-06-15T11:55:07Z -> 2026-06-15T11:58:09Z; unread now: 0 (staged; fold into your next substantive commit)
```

After creating the final director-to-all status event, I consumed that
self-broadcast too so the next director starts clean:

```text
$ CODEX_SEAT=director GIT_INDEX_FILE=/Users/hyungkoookkim/Content/.git/index-codex-director coordination/bin/consume-events director
cursor director: 2026-06-15T11:58:09Z -> 2026-06-15T12:00:13Z; unread now: 0 (staged; fold into your next substantive commit)
```

Meaning:

- Operator2's GO on `aeb1a2b7 fix(lipsync): price postprocess cost key`
  stands. The `11:53:43Z` addendum only expands the exact reproducible
  mutation/non-vacuity probe.
- Coordinator reconciled `lipsync-postproc-costkey` open -> verified in the
  working tree after the operator2 GO and addendum.
- Wave 2 remains red despite that reconciliation: product-oracle artifact is
  still absent, no-selector blockers remain, and executable pins remain red.

## Subagent Workflow Adoption

The user asked this director seat to adopt multi-subagent tooling into the
workflow. I used two read-only sidecars in this handoff session, then closed
both:

- Routing sidecar (`explorer`, Aquinas): confirmed Pair-A has no active
  non-deferred Wave-2 implementation row. Pair-A's only open row is deferred
  and test-infeasible: `identity-arcface-embselect`.
- Tooling sidecar (`explorer`, Euler): audited `.codex/agents/*` and confirmed
  the usable local role set is `protocol-director`, `protocol-operator`,
  `protocol-coordinator`, `readiness-bridge`, `lane-v-verifier`, and
  `money-gate-reviewer`.

Adopted director rule for next sessions:

- Refresh `seat_status.py director --wave 2`, `env -u GIT_INDEX_FILE git log`,
  and mailbox unread count before each substantive work block.
- Use read-only sidecars for product-oracle artifact review prep, Tier-A
  co-sign scope/R-12/R-13 support, and deferred Pair-A feasibility research.
- Keep final director decisions local: R-BRIEF, co-sign, dispatch, lock/push
  escalation, and identity/product-oracle semantic judgment.
- Use worker subagents only after R-BRIEF/lock/co-sign gates, with disjoint
  write sets and explicit allowed files.
- Do not treat `lane-v-verifier` or `money-gate-reviewer` output as a binding
  operator GO. Operator Lane V remains operator-owned.

Subagent caveat: sidecars can observe newer HEADs while the parent is working.
Every subagent prompt must carry a fresh HEAD/unread snapshot, and every parent
synthesis must re-check the live repo before making state claims.

## Current Pair-A Routing

Pair-A director is idle/readiness-only unless one of these arrives:

- A product-oracle artifact needing identity/ArcFace/GhostFaceNet/lip-sync
  review.
- A Tier-A co-sign request from Pair-B/director2 or coordinator.
- A new or reactivated Pair-A row.

Inventory evidence:

```text
$ rg -n "lipsync-postproc-costkey|identity-arcface-embselect|\\| A \\|" docs/REMEDIATION-INVENTORY.md
line 52 lipsync-postproc-costkey: verified, operator2 GO 2026-06-15T11:48:10Z
line 69 identity-arcface-embselect: wave=defer, status=open, xfail-pin=test-infeasible
```

Do not claim Pair-B implementation work from this seat. Remaining active Wave-2
work is coordinator/Pair-B/operator territory unless the user directly changes
seat ownership.

## Current Wave 2 Blockers

Wave 2 cannot close yet. Current blockers:

- Missing committed `logs/product-oracle-*.json` artifact with
  `artifact_kind=product-oracle`, `wave=2`, finite `arcface.arc_score`, and
  finite `lipsync.offset_frames`.
- `spent-usd-reset-on-resume` has no executable xfail-pin selector.
- `perf-phase-no-gate` has no executable xfail-pin selector.
- Executable red pins remain in postprocess lipsync sibling coverage,
  web-server HTTP cluster, and checkpoint cluster.

Do not declare the wave green from status-column movement alone.

## Dirty Tree Notes

The shared tree remains broadly dirty from other seats and protocol work. In
particular, the mailbox directory still shows staged-delete/untracked-twin
patterns in the main index, and `docs/REMEDIATION-INVENTORY.md` has coordinator
reconciliation changes in the working tree. I did not normalize or revert any
of that.

This handoff intentionally adds only:

- `docs/HANDOFF-director-2026-06-15-codex-subagent-workflow-wrap.md`
- `coordination/mailbox/sent/2026-06-15T12-00-13Z-director-to-all-status.md`

and folds the already-staged director cursor advance to
`2026-06-15T12:00:13Z`.
