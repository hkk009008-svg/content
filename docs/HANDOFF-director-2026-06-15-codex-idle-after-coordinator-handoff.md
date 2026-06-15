# HANDOFF - Director (Pair-A), 2026-06-15 - Codex idle after coordinator handoff

READ FIRST AS NEXT PAIR-A DIRECTOR. Trust git, mailbox artifacts, and
`docs/REMEDIATION-INVENTORY.md` over this prose if they diverge.

## State At Wrap

- Seat: `director` / Pair-A image, identity, realism.
- Write timestamp: `2026-06-15T10:43:14Z`.
- Final observed git HEAD before this handoff commit:
  `645252d1 coord(cursor): operator consume final idle status`.
- Branch from `env -u GIT_INDEX_FILE git status -sb`: `main`, `76 ahead`,
  `0 behind`.
- Last full director seat status was taken at
  `010cb510 docs(handoff): operator codex idle`.
- Director mailbox cursor: `2026-06-15T10:35:38Z`.
- Pre-send director status reached unread 0. After this handoff event and
  concurrent peer idle handoffs landed, final director status showed 3 unread
  status events; see "Handoff Race Note" below.
- Active seat index: `.git/index-codex-director`.
- Smoke: clean `OK` with existing advisories only.
- Wave 2 remains `UNMET`: `verified=16`, `open=14`.
- Active locks: `coordination/locks/.gitkeep` only.
- Product-oracle artifact check returned no files.
- No push performed. Push remains user-gated.

Recent git evidence:

```text
$ env -u GIT_INDEX_FILE git log --oneline -5
645252d1 coord(cursor): operator consume final idle status
010cb510 docs(handoff): operator codex idle
49d268cf docs(handoff): operator2 consume peer idle statuses
24790abe docs(handoff): operator2 codex resume idle
060d008b docs(handoff): coordinator wave2 codex idle
```

Last full director status evidence:

```text
$ .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director --wave 2
HEAD 010cb510 docs(handoff): operator codex idle
vs origin/main: 75 ahead, 0 behind
mailbox cursor: 2026-06-15T10:35:38Z
UNREAD: 3
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
17 failed, 44 passed, 1 warning
```

Lock and product-oracle evidence:

```text
$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep

$ find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
```

No product-oracle files were found.

## Mail Consumed

At resume, director had 4 unread events. I consumed through
`2026-06-15T10:35:38Z`; the first sandboxed consume updated the cursor but
failed while creating `.git/index-codex-director.lock`, and the escalated retry
reported the cursor already at `2026-06-15T10:35:38Z`.

Consumed events:

- `coordination/mailbox/sent/2026-06-15T10-14-54Z-operator2-to-all-verification-report.md`
  - operator2 GO for `audioflag-inherit` on `665427db`; focused tests and smoke
    passed; residual Wave-2 blockers are unrelated.
- `coordination/mailbox/sent/2026-06-15T10-22-41Z-coordinator-to-all-coordination.md`
  - coordinator resumed all seats under the Codex subagent-cycle default.
- `coordination/mailbox/sent/2026-06-15T10-32-13Z-operator2-to-all-status.md`
  - operator2 consumed Codex resume events, found no unread verify request, and
    did not invent Lane V.
- `coordination/mailbox/sent/2026-06-15T10-35-38Z-coordinator-to-all-coordination.md`
  - coordinator handoff: Wave 2 still unmet, `audioflag-inherit` already
    reflected as verified, Pair-A idle, remaining active rows Pair-B-owned.

## Handoff Race Note

After the director cursor reached `2026-06-15T10:35:38Z` and this handoff/status
event was written, concurrent idle handoff/status messages appeared:

- `coordination/mailbox/sent/2026-06-15T10-43-14Z-director-to-all-status.md`
  - this director status event.
- `coordination/mailbox/sent/2026-06-15T10-43-36Z-operator-to-all-status.md`
  - operator idle handoff; no Pair-A Lane V owed.
- `coordination/mailbox/sent/2026-06-15T10-46-26Z-director2-to-all-status.md`
  - director2 idle handoff after consuming the same coordinator/status mail.

I did not chase-consume these final handoff/status events to avoid a handoff
mail loop. They are status-only messages, not new work requests. A later
operator cursor-only commit `645252d1` made the operator status durable but did
not add director work. Next director should surface the unread count,
read/consume the status events intentionally, and then orient from fresh HEAD.

## Pair-A Lane State

Pair-A has no active non-deferred Wave-2 row ready for a director brief. Evidence:

```text
$ rg -n "\| A \|" docs/REMEDIATION-INVENTORY.md
36: aa-nan-rules ... verified
38: pulid-nan-node100 ... verified
39: null-continuity-crash ... verified
40: has-char-lora-hole ... verified
42: idgate-failopen ... verified
44: coherence-silent ... verified
45: coherence-caller-valid-ignored ... verified
47: aa-inf-scorebypass ... verified
48: aa-budget-nan-veto ... verified
50: identity-nan-arc-bypass ... verified
68: secondary-lora-hole ... verified
69: identity-arcface-embselect ... defer/open/test-infeasible
```

Director action this cycle: no production code edited, no inventory transition,
no lock claimed, no brief authored, and no self-verification. This was an idle
handoff after consuming the director inbox.

## Current Routing

- Pair-A director/operator are idle unless a new Pair-A row opens, a Tier-A
  co-sign request arrives, or the user/coordinator routes fresh Pair-A work.
- Pair-B owns the remaining active Wave-2 work visible in the current
  coordinator handoff.
- Rows requiring `coordination/bin/claim-lock` are push-gated. Do not claim those
  locks without explicit push authorization.
- Do not mark Wave 2 green from inventory status alone. The executable gate is
  still red and the product-oracle artifact is still owed.

## Dirty Tree Notes

The shared tree already contains substantial dirty state from other seats and
protocol transplant work. Preserve it. Use `env -u GIT_INDEX_FILE` for git and
pytest evidence unless deliberately maintaining the active per-seat index, and
use explicit pathspecs for staging/commits.

This handoff intentionally adds only:

- `docs/HANDOFF-director-2026-06-15-codex-idle-after-coordinator-handoff.md`
- `coordination/mailbox/sent/2026-06-15T10-43-14Z-director-to-all-status.md`

No production code was edited by the director.
