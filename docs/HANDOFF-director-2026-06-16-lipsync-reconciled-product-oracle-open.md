# Director Handoff - lipsync reconciled, product-oracle open

READ FIRST AS `director`. Trust current git/filesystem and live mailbox state
over this prose if they diverge.

## State At Handoff

Timestamp: `2026-06-15T22:19:26Z` (`2026-06-16T07:19:26+0900 KST`).

Seat: `director`

Current HEAD at evidence refresh:

```text
15c4ead4 coord(reconcile): verify lipsync precheck row
8c4ff795 coord(verify): operator2 go lipsync precheck
79c5af5b docs(handoff): refresh director pair-b lanev monitor
af993382 docs(handoff): refresh operator2 Lane V handoff
306c680e docs(handoff): director2 lipsync Lane V pending
69848473 docs(handoff): refresh operator pair-b lanev standby
73102c03 coord(status): operator standby after pair-b route
5641731c coord(verify): request lipsync precheck Lane V
```

Final live refresh after this handoff was written saw a concurrent director2
handoff commit land:

```text
8a219ae1 docs(handoff): director2 lipsync precheck reconciled
15c4ead4 coord(reconcile): verify lipsync precheck row
8c4ff795 coord(verify): operator2 go lipsync precheck
```

Director mailbox state stayed unchanged at `UNREAD: 2`.

Branch relation:

```text
main vs origin/main: 10 ahead, 8 behind at final live refresh
```

Important divergence snapshot:

```text
< 15c4ead4 coord(reconcile): verify lipsync precheck row
< 8c4ff795 coord(verify): operator2 go lipsync precheck
< 79c5af5b docs(handoff): refresh director pair-b lanev monitor
< af993382 docs(handoff): refresh operator2 Lane V handoff
< 306c680e docs(handoff): director2 lipsync Lane V pending
< 69848473 docs(handoff): refresh operator pair-b lanev standby
< 73102c03 coord(status): operator standby after pair-b route
< 5641731c coord(verify): request lipsync precheck Lane V
< 349dac78 fix(money): precheck mandatory lipsync spend
> a3959638 Merge pull request #14 from hkk009008-svg/codex/merge-all-wave2
> cbd77e07 Merge branch 'main' into codex/merge-all-wave2
> b2517048 coord(route): slice remaining wave2 work
> 603eea74 fix(hooks): require project venv for session smoke
> e4d140e6 coord(reconcile): verify lipsync precheck row
> 17a5aa4d coord(verify): operator2 GO lipsync precheck
> c2572b03 coord(verify): request lipsync precheck Lane V
> d93c9d63 fix(lipsync): precheck mandatory overlay spend
```

Do not push or resolve this divergence from the director seat without explicit
user/coordinator authorization. The local and remote sides both contain a
lipsync-precheck verification/reconciliation lineage, but with different commit
IDs and implementation commits.

## Director Mail

Live director mailbox before this handoff:

```text
cursor: 2026-06-15T21:34:51Z
UNREAD: 2
- 2026-06-15T22-10-55Z-operator2-to-all-verification-report.md
- 2026-06-15T22-14-55Z-coordinator-to-all-coordination.md
```

Both unread bodies were read for this handoff. I did not run
`coordination/bin/consume-events director`; the next director session should
still see these as unread and can intentionally consume them if continuing live
director state.

What they say:

- `2026-06-15T22-10-55Z-operator2-to-all-verification-report.md` is operator2
  Lane V GO for `349dac78 fix(money): precheck mandatory lipsync spend`.
- `2026-06-15T22-14-55Z-coordinator-to-all-coordination.md` reconciles
  `lipsync-precheck-cascade-gap` from `fixed` to `verified` in
  `docs/REMEDIATION-INVENTORY.md`.
- The coordinator board leaves `director` in standby/monitor for Pair-A work,
  product-oracle identity/ArcFace review, or explicit Tier-A co-sign routes.

## Seat Board

Fresh live seat snapshots before this handoff:

```text
director:  cursor 2026-06-15T21:34:51Z, unread 2, online
director2: cursor 2026-06-15T21:34:51Z, unread 2, online
operator:  cursor 2026-06-15T21:34:51Z, unread 2, online
operator2: cursor 2026-06-15T22:10:55Z, unread 1, online
```

Interpretation:

- `director`: no implementation target. Monitor for product-oracle
  identity/ArcFace review, Pair-A work, Tier-A co-signs, or direct user route.
- `director2`: Pair-B no-lock lipsync-precheck row is verified; remaining
  Pair-B work is lock/push-gated or product-oracle/spend gated.
- `operator`: Pair-A verifier standby; no Pair-A verify request active.
- `operator2`: completed Lane V for `349dac78`; remaining unread is the
  coordinator reconciliation/status event.

## Gate / Smoke / Locks

Smoke:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
WARNING: coordination ADVISORY [unknown_kind] mailbox/sent/2026-06-15T19-43-14Z-director2-to-operator2-verify-addendum.md - kind 'verify-addendum' not in KNOWN_KINDS
R1 xfail-strictness ....... PASS  12 xfail markers; all strict=True+reason
R2 invisible-green ........ WARN
R3 gate-executes-pins ..... PASS  wave_gate_check.py executes the pins
R4 ci-runs-runxfail ....... PASS  a CI workflow runs --runxfail
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Wave 2 gate:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET  counts={'verified': 24, 'open': 6}
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact
PYTEST summary: 9 failed, 58 passed
```

Remaining gate blockers are outside the reconciled lipsync-precheck row:

- missing committed Wave 2 product-oracle artifact under
  `logs/product-oracle-*.json`;
- `lipsync-veto` in `cinema/auto_approve.py`;
- the five HTTP/web-server rows represented by
  `tests/unit/test_discovery_web_server_xfail.py`.

Locks and product-oracle artifact:

```text
$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep

$ env -u GIT_INDEX_FILE git ls-tree -r --name-only HEAD -- logs | rg '^logs/product-oracle-.*\.json$'
# no output
```

No lock, push, pod spend, paid API spend, production edit, inventory edit,
mailbox event, or verification verdict was performed by this director handoff.

## Workspace Hygiene

Status before writing this handoff:

```text
## main...origin/main [ahead 9, behind 8]
 M .agents/skills/four-seat-protocol/SKILL.md
 M docs/protocol/codex/continuation.md
 M scripts/continuation_readiness.py
 M tests/unit/test_codex_protocol_artifacts.py
 M tests/unit/test_continuation_readiness.py
?? docs/HANDOFF-coordinator-2026-06-16-automated-handoff-tool-transplant.md
?? docs/HANDOFF-director2-2026-06-16-lipsync-precheck-wip.md
?? docs/HANDOFF-operator-2026-06-16-checkpoint-lanev-context.md
?? scripts/draft_handoff.py
?? tests/unit/test_draft_handoff.py
```

Staged scope was empty at the same refresh:

```text
$ env -u GIT_INDEX_FILE git diff --cached --name-status
# no output
```

Do not stage, delete, commit, or "clean up" those files from the director seat
unless the user explicitly transfers ownership. They appear to be coordinator,
director2, operator, and Codex-protocol transplant WIP.

Final refresh after writing this handoff kept director mailbox unchanged, then
HEAD advanced to `8a219ae1` from a concurrent director2 handoff commit. The
same final refresh showed concurrent WIP from other seats:

```text
## main...origin/main [ahead 10, behind 8]
 M .agents/skills/four-seat-protocol/SKILL.md
MM coordination/mailbox/seen/director2.txt
M  coordination/mailbox/seen/operator2.txt
D  docs/HANDOFF-director2-2026-06-16-lipsync-precheck-reconciled.md
A  docs/HANDOFF-operator2-2026-06-16-lipsync-precheck-reconciled.md
 M docs/protocol/codex/continuation.md
 M scripts/continuation_readiness.py
 M tests/unit/test_codex_protocol_artifacts.py
 M tests/unit/test_continuation_readiness.py
?? docs/HANDOFF-coordinator-2026-06-16-automated-handoff-tool-transplant.md
?? docs/HANDOFF-coordinator-2026-06-16-lipsync-precheck-reconciled.md
?? docs/HANDOFF-director-2026-06-16-lipsync-reconciled-product-oracle-open.md
?? docs/HANDOFF-director2-2026-06-16-lipsync-precheck-reconciled.md
?? docs/HANDOFF-director2-2026-06-16-lipsync-precheck-wip.md
?? docs/HANDOFF-operator-2026-06-16-checkpoint-lanev-context.md
?? docs/HANDOFF-operator-2026-06-16-lipsync-precheck-reconciled.md
?? scripts/draft_handoff.py
?? tests/unit/test_draft_handoff.py

$ env -u GIT_INDEX_FILE git diff --cached --name-status
M	coordination/mailbox/seen/director2.txt
M	coordination/mailbox/seen/operator2.txt
D	docs/HANDOFF-director2-2026-06-16-lipsync-precheck-reconciled.md
A	docs/HANDOFF-operator2-2026-06-16-lipsync-precheck-reconciled.md
```

These staged paths are not director-owned for this handoff. Preserve them.
The `D` plus `??` pair for the director2 handoff is likely stale shared-index
residue after the concurrent commit; do not repair it from this director
handoff unless ownership is explicitly transferred.

Latest observed live refresh before this response advanced further:

```text
HEAD: f3cd6c20 docs(handoff): coordinator lipsync precheck reconciled
branch: main vs origin/main 12 ahead, 8 behind
director cursor: 2026-06-15T21:34:51Z
director unread: 2
Wave 2 gate: UNMET counts={'verified': 24, 'open': 6}
```

Latest observed staged scope:

```text
$ env -u GIT_INDEX_FILE git diff --cached --name-status
D	docs/HANDOFF-coordinator-2026-06-16-lipsync-precheck-reconciled.md
```

This looks like another stale shared-index artifact after a concurrent
coordinator handoff commit. Preserve it; do not fix it from the director seat.

## Next Director

1. Start with:
   `.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director --wave 2`
   and `env -u GIT_INDEX_FILE git log --oneline -8`.
2. Re-read the two unread mail bodies above; consume the director cursor only if
   intentionally advancing live director state.
3. Treat `lipsync-precheck-cascade-gap` as locally reconciled/verified at
   `15c4ead4`, with a later director2 handoff at `8a219ae1`, while remembering
   `origin/main` has a parallel verified lineage.
4. Do not duplicate Pair-B Lane V or mark new rows verified without operator GO.
5. Stay available for product-oracle identity/ArcFace review, Tier-A co-signs,
   explicit Pair-A work, or coordinator-routed support.
6. Do not claim locks, push, use pods, or trigger paid APIs without explicit
   user-principal authorization.
