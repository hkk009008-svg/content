## Summary
<!-- 1-3 sentences. What changed and why, in operator-friendly language. -->

## Why
<!-- Motivation. If this maps to a strategic-review P-priority, link the section. -->

## Test plan
- [ ] `ARCHITECTURE.md §15` smoke passes locally
- [ ] `.venv/bin/python -m pytest tests/unit/ -q` clean (baseline 2026-05-24: **478 pass / 3 skip / 0 fail**)
- [ ] `cd web && npx tsc --noEmit` silent
- [ ] CI (`.github/workflows/ci.yml`) is green on this PR
- [ ] ARCHITECTURE.md updated if a documented subsystem (entry, orchestrator, phases, gates, identity, video routing, audio, LLM, frontend) was touched
- [ ] [DECISIONS.md](../DECISIONS.md) appended (new ADR) if this is an architectural decision

## Strategic-review P-priority (if applicable)
See [docs/STRATEGIC_REVIEW-2026-05-24.md](../docs/STRATEGIC_REVIEW-2026-05-24.md).

- [ ] **P0** — Ship-blocking risk (test coverage, CI, cost-tracking)
- [ ] **P1** — Quality risk (observability, orchestrator size, schema validation, frontend resilience)
- [ ] **P2** — Cost / efficiency (LLM cost default, pod billing, cascade visibility)
- [ ] **P3** — Code health (concurrency hygiene, dead code, deduplication)
- [ ] **P4** — Strategic / open (vendor sprawl, multi-user, review fatigue, experiment tracking, console mode)
- [ ] N/A — Routine fix / cleanup / refactor not tied to a P-priority

## Verification output
<!--
Per CLAUDE.md / AGENTS.md "Verification discipline" (Rule 3): if this PR
makes inventory-shaped claims (counts, file presence, LOC, etc.), paste the
producing command + output here. Authority-voice claims without verifying
output get pushed back.
-->

```
$ <command>
<output>
```

## Out of scope
<!-- Anything noticed but deliberately not addressed. Goes to "Findings" if
escalating in the strategic review next cycle. -->
