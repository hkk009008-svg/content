# HANDOFF - Director (Pair-A), 2026-06-15 - product-oracle guidance wrap

READ FIRST AS NEXT PAIR-A DIRECTOR. Trust git, mailbox artifacts, and
`docs/REMEDIATION-INVENTORY.md` over this prose if they diverge.

## State At Wrap

- Seat: `director` / Pair-A image, identity, realism.
- Write timestamp: `2026-06-15T11:35:32Z`.
- Final durable HEAD observed before commit:
  `e593a705 docs(handoff): operator product-oracle guidance idle`.
- Branch: `main`, 87 ahead / 0 behind origin from the latest full
  `seat_status` before `e593a705`.
- Director mailbox cursor staged through the final self-broadcast:
  `2026-06-15T11:35:32Z`. Live working tree status showed later unread
  non-HEAD addenda at `2026-06-15T11:35:35Z` and `2026-06-15T11:39:08Z`;
  see Race Note.
- Active seat index: `.git/index-codex-director`.
- Active locks: `coordination/locks/.gitkeep` only.
- Product-oracle artifact check returned no files.
- Smoke: `scripts/ci_smoke.py` returned `OK` with existing advisories only.
- Wave 2 remains `UNMET`: `verified=16`, `open=14`.
- No push performed. Push remains user-gated.

Recent git evidence:

```text
$ env -u GIT_INDEX_FILE git log --oneline -5
e593a705 docs(handoff): operator product-oracle guidance idle
2b5fdf0d coord(cursor): director2 consume final wrap addenda
50f49419 coord(cursor): director2 consume handoff statuses
cc2b3f61 docs(handoff): director2 lipsync costkey Lane V pending
aa6f00f9 coord(verify): request lipsync costkey Lane V
```

Director status evidence:

```text
$ .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director --wave 2
HEAD 2b5fdf0d coord(cursor): director2 consume final wrap addenda
vs origin/main: 87 ahead, 0 behind
mailbox cursor: 2026-06-15T11:35:32Z
UNREAD: 2
  2026-06-15T11-35-35Z-operator2-to-all-status.md
  2026-06-15T11-37-38Z-coordinator-to-all-coordination.md
Wave 2 gate: UNMET counts={'verified': 16, 'open': 14}
```

Smoke evidence:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
OK
```

Known smoke advisories remain: 136 `docs/PROGRAM-MANUAL.md` doc-anchor drifts,
two historical mailbox unknown-kind warnings, and two R2 invisible-green
warnings. The ceremony check result was `no ceremony detected`.

Gate evidence:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET  counts={'verified': 16, 'open': 14}
BLOCKER [MAJOR/open] spent-usd-reset-on-resume ... no executable xfail-pin selector
BLOCKER [MAJOR/open] perf-phase-no-gate ... no executable xfail-pin selector
PRODUCT ORACLE BLOCKER: Wave 2 requires a committed logs/product-oracle-*.json artifact ...
16 failed, 45 passed
```

Lock and product-oracle evidence:

```text
$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep

$ find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
```

No product-oracle files were found.

## Work Completed

Director authored and committed:

- `b366ae0d coord(director): publish product-oracle guidance`

That commit added
`coordination/mailbox/sent/2026-06-15T11-23-24Z-director-to-all-coordination.md`
and advanced the director cursor through the prior coordinator routing.

Purpose: Pair-A identity-side guidance for the owed Wave-2 product-oracle
artifact. It says the gate fields (`artifact_kind=product-oracle`, `wave=2`,
finite `arcface.arc_score`, finite `lipsync.offset_frames`) are only a minimum
schema. A real oracle artifact should also include the committed instrument,
command, source render/reference/audio paths, ArcFace/GhostFaceNet scoring
semantics, frame/region policy, lip-sync fps/timebase/method, and explicit
degraded/inconclusive flags.

This is guidance, not a verification report and not a Pair-B Lane V substitute.
No production code, inventory status, or locks were edited by director.

## Mail Processed

Peer/all-seat mail read before the final self-broadcast is consumed through
`2026-06-15T11:33:22Z`; the director cursor itself is folded through the final
self-broadcast at `2026-06-15T11:35:32Z`.

Latest consumed relevant status:

- `coordination/mailbox/sent/2026-06-15T11-26-36Z-operator-to-all-status.md`
  - operator consumed the director product-oracle guidance;
  - no Pair-A Lane V trigger exists;
  - operator remains ready for Pair-A verification, Tier-A co-sign evidence, or
    identity/ArcFace product-oracle review once an artifact lands.

Newer visible event not addressed to director:

- `coordination/mailbox/sent/2026-06-15T11-31-19Z-director2-to-operator2-verify-request.md`
  - Pair-B director requested operator2 Lane V for
    `aeb1a2b7 fix(lipsync): price postprocess cost key`;
  - this is operator2-owned verification, not Pair-A director work.

Final consumed all-seat handoff:

- `coordination/mailbox/sent/2026-06-15T11-33-22Z-director2-to-all-status.md`
  - director2 confirms `aeb1a2b7` landed and `aa6f00f9` requested Lane V;
  - operator2 remains verifier; the row stays open pending operator2 GO and
    coordinator reconciliation.

Self-broadcast cursor fold:

- `coordination/mailbox/sent/2026-06-15T11-35-32Z-director-to-all-status.md`
  is this handoff status event. I consumed it so the director cursor can fold
  with the handoff commit.

Race note:

- `coordination/mailbox/sent/2026-06-15T11-35-35Z-operator2-to-all-status.md`
  and `coordination/mailbox/sent/2026-06-15T11-39-08Z-coordinator-to-all-coordination.md`
  appeared in the working tree after the director self-broadcast. I read both,
  but neither was committed in HEAD when I staged this handoff, so I did not
  advance the director cursor past them. They both say operator2 still owes Lane
  V for `aeb1a2b7` and no verification-report exists yet. If they become
  durable, the next director may see them as unread status/routing events; they
  do not assign Pair-A production work.

## Current Routing

- Pair-A director remains lane-correct readiness-only: Tier-A co-signs,
  identity/ArcFace/product-oracle design review, and stub-contract review when
  requested.
- Pair-A has no active non-deferred production row ready for a director brief.
  Inventory grep shows Pair-A rows verified except `identity-arcface-embselect`,
  which is `wave=defer`, `status=open`, `xfail-pin=test-infeasible`.
- Pair-B owns active Wave-2 implementation. `aeb1a2b7` is currently awaiting
  operator2 Lane V and coordinator reconciliation.
- Wave 2 cannot close until the executable pin suite is clean, the no-selector
  blockers are honestly resolved or attested per protocol, and the committed
  Wave-2 product-oracle artifact exists under `logs/product-oracle-*.json`.
- Do not run `coordination/bin/claim-lock` without explicit push/lock
  authorization; push remains user-gated.

## Dirty Tree Notes

The shared tree remains dirty from other seats and protocol transplant work.
Preserve it. Use `env -u GIT_INDEX_FILE` for git/pytest evidence unless
deliberately maintaining the active per-seat index, and use explicit pathspecs
for staging/commits.

This handoff intentionally adds only:

- `docs/HANDOFF-director-2026-06-15-codex-product-oracle-guidance-wrap.md`
- `coordination/mailbox/sent/2026-06-15T11-35-32Z-director-to-all-status.md`

and folds the director cursor advance to `2026-06-15T11:35:32Z`, the final
director self-broadcast.
