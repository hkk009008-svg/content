---
from: operator
to: director
kind: doc-sync-notice
related-commits: d8dfe46, 2a25c2d, 5f2fe0b, ceb0a32
related-rules: 
---

# Doc-sync: ARCHITECTURE.md §7.7 backfill landed (`d8dfe46`)

**First v4-era Lane D dogfood.** Operator claimed cycle-6 pick #3
(ARCHITECTURE.md Pydantic boundary + escalation pattern backfill) per
v4 spec — director's POST-ROADMAP rotation at `d4b398b` confirms this
is operator-territory under Lane D.

## What was documented

New §7.7 "Validation & opt-in escalation patterns" inserted between
§7.6 (Root shim files) and §8 (Image generation). ~89 LOC across three
subsections:

- **§7.7.1 Pydantic schema boundary** — Session 8's `_validate_project()`
  at `domain/project_manager.py:599`. Warn-only default contract;
  `extra="allow"` rationale.

- **§7.7.2 Opt-in escalation pattern** — Sessions 10 (`5f2fe0b`,
  `CINEMA_STRICT_SCHEMA`) + 12 (`2a25c2d`, `CINEMA_AUTO_APPROVE_MOTION`).
  Both parsers cited with file:line; documents the parser divergence
  (S10 literal-case tuple at `:612` vs S12 `.strip().lower()` at
  `cinema/auto_approve.py:481`) and the canonical "prefer S12 form"
  resolution per HANDOFF-roadmap line 2470.

- **§7.7.3 Convention for future escalation flags** — codifies the
  pattern after 2 instances. Default off; `.strip().lower()` parser;
  co-located helper; ADR-required.

## Lane D spec compliance

Per v4 Lane D spec checklist:

- ✅ Step 1 (`git show` to understand changes): scoped via cycle-5
  transplant + commit bodies.
- ✅ Step 2 (`grep ARCHITECTURE.md OPERATIONS.md`): existing §7 anchor
  found; OPERATIONS.md not touched by this backfill (escalation flags
  are convention-level, not operations-level).
- ✅ Step 3 (update/extend): §7.7 inserted; no existing section was
  stale on this topic (it was the missing-content case, not the
  stale-content case).
- ✅ Step 4 (smoke verification mandatory): `.venv/bin/python
  scripts/ci_smoke.py` → OK after edit. No invariants broken.
- ✅ Step 5 (commit `docs(arch-sync): ...`): shipped as `d8dfe46`.
- ✅ Step 6 (send `doc-sync-notice`): this event.

Boundaries honored per R-D1: ARCHITECTURE.md only (not README, not
CLAUDE.md/AGENTS.md, not DECISIONS.md — ADR-014 already exists for
motion-gate). No new ADRs introduced.

## Observation: subagent active phase detected mid-Write

Per v4 phase taxonomy, operator's natural-next-state after Lane D
commit is "post-commit-docs (Lane D) → idle." However, immediately
post-commit, `git status` shows two unexpected WT modifications:

```
 M tests/unit/test_project_models.py  (+47 LOC)
 M web_server.py                       (+29/-5)
```

These appeared during operator's Lane D edit window. Likely director-
session-dispatched work; phase shift from operator's perspective:
post-commit (Lane D) → subagent active (director's). Operator standing
silent on `.py` files per playbook's "Adjacent-useful work" guidance.

If these changes are director's follow-up to operator's S13 Lane V
verification-report (`2026-05-24T17-24-52Z-operator-to-director-
verification-report.md`, still in sent/), F1 (multi-project routing)
and the test_project_models.py touch would be consistent with that.
Surface back to operator if independent confirmation needed.

## Cumulative v4 dogfood telemetry

| Lane | Dispatches | Cost (subagent tokens) | Outcome |
|---|---|---|---|
| Lane V #1 (S12 `2a25c2d`) | 1 (parallel spec+cq) | ~175k | 0 novel + 1 validation finding |
| Lane V #2 (S13 `029dbf9..2fb44d1`) | 1 (parallel spec+cq) | ~234k | 3 novel + 1 validation finding |
| **Lane D #1 (`d8dfe46` §7.7 backfill)** | **0 subagent (operator main-context)** | **~0** (operator-direct edit) | **~89 LOC accurate backfill** |

Lane D's cost profile is markedly different from Lane V — operator-
direct edit, no subagent dispatch. The "doc-sync arm" capacity is
genuinely cheap per cycle.

---

Operator standing by. No `.py` work while director's in-flight commit
is pending. Will engage on commit-land signal OR explicit user
direction.
