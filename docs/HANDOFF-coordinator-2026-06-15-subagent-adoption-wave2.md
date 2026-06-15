# HANDOFF - Coordinator, 2026-06-15 - Subagent workflow adopted; Wave 2 still unmet

READ FIRST AS COORDINATOR. Trust git and mailbox artifacts over this prose if
they diverge.

## Snapshot

- Write timestamp: `2026-06-15T11:40:34Z`.
- HEAD: `e593a705 docs(handoff): operator product-oracle guidance idle`.
- Branch state from coordinator status: `main`, `88 ahead`, `0 behind`.
- Coordinator is unpinned: no cursor consumed.
- Coordinator/all mailbox count:
  `.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py coordinator --wave 2`
  -> `UNREAD: 130` all-time coordinator/all events.
- Peer heartbeats in that status: all four seats ONLINE; `director` and
  `operator` at `e593a705`, `director2` at `2b5fdf0d`, and `operator2` at
  `50f49419`.
- No push performed. Push remains user-gated.

Recent git:

```text
$ env -u GIT_INDEX_FILE git log --oneline -10
e593a705 docs(handoff): operator product-oracle guidance idle
2b5fdf0d coord(cursor): director2 consume final wrap addenda
50f49419 coord(cursor): director2 consume handoff statuses
cc2b3f61 docs(handoff): director2 lipsync costkey Lane V pending
aa6f00f9 coord(verify): request lipsync costkey Lane V
82c6a2a1 coord(protocol): adopt subagent workflow per seat
aeb1a2b7 fix(lipsync): price postprocess cost key
b366ae0d coord(director): publish product-oracle guidance
```

## What Changed This Session

1. Coordinator sent all-seat resync routing:
   `d2b2de3d coord(all): resync wave2 seat routing`.
2. Pair-A director published product-oracle identity guidance:
   `b366ae0d coord(director): publish product-oracle guidance`.
3. Pair-B director2 landed the no-lock row implementation:
   `aeb1a2b7 fix(lipsync): price postprocess cost key`.
4. Coordinator adopted subagent tooling into every seat workflow:
   `82c6a2a1 coord(protocol): adopt subagent workflow per seat`.
5. Director2 committed the Lane V request and handoff for that Pair-B row:
   `aa6f00f9 coord(verify): request lipsync costkey Lane V` and
   `cc2b3f61 docs(handoff): director2 lipsync costkey Lane V pending`.
6. Director2 consumed follow-up handoff statuses:
   `50f49419 coord(cursor): director2 consume handoff statuses`.
7. Director2 consumed final wrap addenda:
   `2b5fdf0d coord(cursor): director2 consume final wrap addenda`.
8. Operator wrote the product-oracle-guidance idle handoff:
   `e593a705 docs(handoff): operator product-oracle guidance idle`.

Subagent adoption changed only protocol/skill/agent prompt files:

```text
$ env -u GIT_INDEX_FILE git show --stat --oneline -1 82c6a2a1
82c6a2a1 coord(protocol): adopt subagent workflow per seat
 .agents/skills/four-seat-protocol/SKILL.md | 22 ++++++++++++++++++++++
 .agents/skills/seat-coordinator/SKILL.md   | 22 ++++++++++++++++++++++
 .agents/skills/seat-director/SKILL.md      | 24 ++++++++++++++++++++++++
 .agents/skills/seat-operator/SKILL.md      | 22 ++++++++++++++++++++++
 .codex/agents/protocol-coordinator.toml    |  4 ++++
 .codex/agents/protocol-director.toml       |  4 ++++
 .codex/agents/protocol-operator.toml       |  4 ++++
 docs/protocol/codex/continuation.md        | 26 ++++++++++++++++++++++++++
 8 files changed, 128 insertions(+)
```

Validation for the protocol commit:

```text
$ env -u GIT_INDEX_FILE git diff --check -- <8 protocol paths>
# no output
$ env -u GIT_INDEX_FILE python3 -c 'import pathlib,tomllib; ...; print("toml ok")'
toml ok
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
OK
```

`ci_smoke.py` still reports only existing advisory warnings: doc-anchor drift in
`docs/PROGRAM-MANUAL.md`, two legacy mailbox-kind advisories, and two R2
invisible-green warnings.

## Current Wave 2 Gate

Wave 2 remains red:

```text
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET  counts={'verified': 16, 'open': 14}
16 failed, 45 passed
```

Current blockers from the gate:

- `spent-usd-reset-on-resume`: open row with no executable xfail-pin selector.
- `perf-phase-no-gate`: open row with no executable xfail-pin selector.
- Missing committed `logs/product-oracle-*.json` artifact with
  `artifact_kind=product-oracle`, `wave=2`, finite `arcface.arc_score`, and
  finite `lipsync.offset_frames`.
- Remaining executable red pins: `lipsync-veto`, IO timeout, web-server HTTP
  cluster, and checkpoint cluster.

Product-oracle check:

```text
$ find logs -maxdepth 1 -type f -name 'product-oracle-*.json' -print | sort
# no output
```

Lock check:

```text
$ find coordination/locks -maxdepth 1 -type f -print | sort
coordination/locks/.gitkeep
```

## Mailbox / Routing

Latest Wave-2 implementation handoff:

- `coordination/mailbox/sent/2026-06-15T11-31-19Z-director2-to-operator2-verify-request.md`
  requests operator2 Lane V on `aeb1a2b7`.
- `coordination/mailbox/sent/2026-06-15T11-33-22Z-director2-to-all-status.md`
  confirms the same state: lipsync-postproc-costkey is fixed, Lane V requested,
  and the row remains open pending operator2 GO plus coordinator reconciliation.
- `coordination/mailbox/sent/2026-06-15T11-35-32Z-director-to-all-status.md`
  leaves Pair-A in readiness/product-oracle review mode.
- `coordination/mailbox/sent/2026-06-15T11-35-35Z-operator2-to-all-status.md`
  supersedes operator2's earlier idle read: operator2 owes Lane V on
  `aeb1a2b7` and sent no verification report before handoff.

That verify-request says:

- `lipsync-postproc-costkey` fix landed at `aeb1a2b7`.
- It updates `cinema/shots/controller.py`,
  `tests/unit/test_postprocess_audio_propagation.py`,
  `tests/unit/test_discovery_cost_xfail.py`, `docs/REMEDIATION-INVENTORY.md`,
  and `ARCHITECTURE.md`.
- Inventory status intentionally remains `open` pending operator2 Lane V and
  coordinator reconciliation.

Next required action:

1. `operator2` runs Lane V on `aeb1a2b7` and sends GO/NITS/FAIL.
2. Coordinator reconciles the inventory only if operator2 sends GO.
3. Continue Pair-B rows per `d2b2de3d`: prefer no-lock work unless user
   authorizes push-gated lock claiming.

Pair-A state:

- `director` published product-oracle/ArcFace guidance in
  `2026-06-15T11-23-24Z-director-to-all-coordination.md`.
- `operator` reported no Pair-A Lane V owed in
  `2026-06-15T11-26-36Z-operator-to-all-status.md`.

## Dirty Tree Warning

The shared tree remains broadly dirty with staged-delete/untracked-twin mailbox
state and unrelated protocol/transplant/test changes. Coordinator did not
normalize or revert that state. Use explicit pathspecs.

Representative `env -u GIT_INDEX_FILE git status --short` included:

- modified `.agents/skills/ai-video-gen/SKILL.md`,
  `.agents/skills/comfyui-mastery/SKILL.md`, `AGENTS.md`,
  `coordination/README.md`, `cost_tracker.py`, `domain/character_manager.py`,
  `requirements.txt`, `scripts/status.py`, and tests;
- staged-delete/untracked-twin mailbox files under
  `coordination/mailbox/sent/`;
- untracked Codex migration/config/hook artifacts.

Do not clean this from the coordinator seat unless explicitly instructed.

## Operating Note

All five seats now have Codex subagent workflow instructions:

- coordinator: all-seat role-agent cycle plus read-only verifier fan-out at
  coordinator-appropriate triggers;
- director/director2: bounded exploration, implementation shards, and
  specialist pre-review while retaining R-BRIEF/dispatch ownership;
- operator/operator2: read-only verifier subagents as evidence, while the live
  operator still synthesizes the binding GO/NITS/FAIL.

Subagents increase capacity; they do not bypass locks, push gating,
impl-ne-verifier, or coordinator's no-production-code boundary.
