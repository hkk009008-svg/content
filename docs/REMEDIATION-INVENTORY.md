# Remediation Inventory — Program Hardening Campaign

> Single source of truth (spec `docs/superpowers/specs/2026-06-14-program-hardening-roadmap-design.md` §2).
> **Writer:** coordinator (primary) + deputy own-lane status when coordinator offline (§6f).
> Status one of: open | fixing | fixed | verified | provisional.

## Campaign constants
- **Wave-gate SLA:** 24h (§6f).
- **Wave-1 cross-cutting first-mover sequence:** TO BE SET by coordinator at Wave-1 open (§6b).

## Schema
`| id | subsystem | file:line | severity | priority | fail-mode | repro | xfail-pin | lane-owner | shared-lock | wave | status | verifier | notes |`

| id | subsystem | file:line | severity | priority | fail-mode | repro | xfail-pin | lane-owner | shared-lock | wave | status | verifier | notes |
|----|-----------|-----------|----------|----------|-----------|-------|-----------|------------|-------------|------|--------|----------|-------|
