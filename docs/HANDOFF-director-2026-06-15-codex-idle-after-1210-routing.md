# HANDOFF - Director (Pair-A), 2026-06-15 - idle after 12:10 coordinator routing

READ FIRST AS NEXT PAIR-A DIRECTOR. Trust git, mailbox artifacts, and
`docs/REMEDIATION-INVENTORY.md` over this prose if they diverge.

## State At Wrap

- Seat: `director` / Pair-A image, identity, realism.
- Write timestamp: `2026-06-15T12:26:05Z`.
- Durable HEAD observed: `cefd2971 docs(handoff): director subagent workflow wrap`.
- Branch from live seat status: `main`, 99 ahead / 0 behind origin.
- Director mailbox cursor after late idle-event consumption:
  `2026-06-15T12:28:00Z`; unread is 0.
- Active locks: `coordination/locks/.gitkeep` only.
- Wave 2 remains `UNMET`: `verified=17`, `open=13`.
- No committed `logs/product-oracle-*.json` artifact exists.
- Smoke returned `OK` with existing advisories only.
- Pair-A has no active Wave 2 open row. The only open Pair-A row is deferred:
  `identity-arcface-embselect`.
- No production code, remediation inventory status, or locks were edited by this
  director handoff.
- Push remains user-gated.

Evidence:

```text
$ CODEX_SEAT=director GIT_INDEX_FILE="$(git rev-parse --absolute-git-dir)/index-codex-director" .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director --wave 2
HEAD cefd2971 docs(handoff): director subagent workflow wrap
vs origin/main: 99 ahead, 0 behind
mailbox cursor: 2026-06-15T12:10:22Z
UNREAD: 0
Wave 2 gate: UNMET counts={'verified': 17, 'open': 13}

$ CODEX_SEAT=director GIT_INDEX_FILE="$(git rev-parse --absolute-git-dir)/index-codex-director" coordination/bin/consume-events director
cursor director: 2026-06-15T12:26:43Z -> 2026-06-15T12:28:00Z; unread now: 0 (staged; fold into your next substantive commit)

$ env -u GIT_INDEX_FILE git log --oneline -5
cefd2971 docs(handoff): director subagent workflow wrap
72a2d83c docs(handoff): operator consume director wrap
04912467 docs(handoff): operator consume late statuses
afb483d4 docs(handoff): operator2 lipsync costkey idle
f721c989 docs(handoff): operator multi-subagent idle

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

$ awk -F'|' 'function trim(s){gsub(/^[ \t]+|[ \t]+$/, "", s); return s} /^\| [^|-]/ {id=trim($2); lane=trim($10); wave=trim($12); status=trim($13); if (wave=="2" && status=="open") print FNR ":" id " lane=" lane " status=" status}' docs/REMEDIATION-INVENTORY.md
43:lipsync-veto lane=B status=open
53:lipsync-precheck-cascade-gap lane=B status=open
54:download-urllib-notimeout lane=B status=open
56:http-clearperf-silent200 lane=B status=open
57:http-drivingvid-orphan lane=B status=open
59:http-addchar-float-unguarded lane=B status=open
60:http-null-json-body lane=B status=open
61:http-styleboard-false201 lane=B status=open
62:ckpt-sceneidx-dead lane=B status=open
63:ckpt-shotaudio-loss lane=B status=open
64:ckpt-projectid-nocrosscheck lane=B status=open
73:spent-usd-reset-on-resume lane=B status=open
75:perf-phase-no-gate lane=B status=open

$ awk -F'|' 'function trim(s){gsub(/^[ \t]+|[ \t]+$/, "", s); return s} /^\| [^|-]/ {id=trim($2); lane=trim($10); wave=trim($12); status=trim($13); if (lane=="A" && wave=="2" && status=="open") print FNR ":" id}' docs/REMEDIATION-INVENTORY.md
# no output

$ awk -F'|' 'function trim(s){gsub(/^[ \t]+|[ \t]+$/, "", s); return s} /^\| [^|-]/ {id=trim($2); lane=trim($10); wave=trim($12); status=trim($13); if (lane=="A" && wave=="defer" && status=="open") print FNR ":" id " lane=" lane " wave=" wave " status=" status}' docs/REMEDIATION-INVENTORY.md
69:identity-arcface-embselect lane=A wave=defer status=open
```

Known smoke advisories remain: `docs/PROGRAM-MANUAL.md` doc-anchor drift, two
historical mailbox unknown-kind warnings, and two R2 invisible-green warnings.

## Mailbox And Routing

Director unread was 0 at handoff start, so no incoming mailbox events were
consumed before writing the status event.

Late event handled during wrap:
`coordination/mailbox/sent/2026-06-15T12-28-00Z-operator2-to-all-status.md`.
It is an operator2 idle handoff: no Lane V, NITS re-read, or operator2
verification task currently owed. I consumed it into the director cursor:
`2026-06-15T12:26:43Z -> 2026-06-15T12:28:00Z`, unread now 0.

Latest routing is:
`coordination/mailbox/sent/2026-06-15T12-10-22Z-coordinator-to-all-coordination.md`.
It directs Pair-A director to stay idle unless a Pair-A verify request,
Tier-A co-sign request, product-oracle identity review, or new Pair-A row lands.

Status event written by this handoff:
`coordination/mailbox/sent/2026-06-15T12-26-05Z-director-to-all-status.md`.

## Current Pair-A Routing

Pair-A director should remain idle/readiness-only unless one of these arrives:

- Product-oracle artifact needing identity / GhostFaceNet / ArcFace-result
  review.
- Tier-A co-sign request from Pair-B/director2 or coordinator.
- New or reactivated Pair-A row.
- User-principal direct instruction changing seat ownership.

Do not claim Pair-B implementation work from this seat. Remaining active Wave 2
implementation rows are Pair-B-owned in the current inventory snapshot.

## Current Wave 2 Blockers

Wave 2 cannot close yet:

- Missing committed `logs/product-oracle-*.json` artifact with
  `artifact_kind=product-oracle`, `wave=2`, finite `arcface.arc_score`, and
  finite `lipsync.offset_frames`.
- `spent-usd-reset-on-resume` has no executable xfail-pin selector.
- `perf-phase-no-gate` has no executable xfail-pin selector.
- Executable red pins remain in postprocess lipsync sibling coverage,
  web-server HTTP cluster, and checkpoint cluster.

Do not declare the wave green from status-column movement alone.

## Dirty Tree Notes

The shared tree remains broadly dirty from other seat/protocol work, including
mailbox staged-delete/untracked-twin patterns and multiple modified protocol,
test, and production files. I did not normalize or revert any of that.

This handoff intentionally adds only:

- `docs/HANDOFF-director-2026-06-15-codex-idle-after-1210-routing.md`
- `coordination/mailbox/sent/2026-06-15T12-26-05Z-director-to-all-status.md`
