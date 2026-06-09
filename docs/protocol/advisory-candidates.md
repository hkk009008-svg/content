# Advisory candidates — thin-evidence rules flagged for later principal review

**Status: audit-only list. NO rule status is changed by this file or by the
CLAUDE.md/AGENTS.md operative-split migration that created it.** This is a parking
list for a *separate, later* advisory-review phase in which the user-principal
decides whether any of these rules should move active → advisory (or be revised),
*with intent*. Until then every rule below remains fully active.

## What "thin evidence" means here

A codified rule whose empirical basis is N=0 (forward-looking codification —
ratified ahead of any real use) or N=1 (a single triggering instance). The
codification threshold for most rules in this repo is N=2; the rules below were
shipped under that bar deliberately (forward-looking ratification or
single-incident response) and are the natural candidates to revisit once more
data accrues.

The authoritative provenance + N-count for every rule lives in
[docs/PROTOCOL-RULES-LOG.md](../PROTOCOL-RULES-LOG.md); this file only *indexes*
the thin-evidence subset. N-counts below are quoted from each rule body's own
"Empirical basis" / "Codified SHA" line (verify against the rule body before
acting).

## Candidates (per the rule bodies' stated empirical basis)

| Rule | Stated evidence at codification | Why thin | Revisit trigger |
|---|---|---|---|
| Rule #17 — Workflow-assisted analysis lanes | N=0 ("forward-looking codification; feature unavailable in current runtime; first dogfood at v5.6") | Ratified ahead of activation; no real use yet | First real `/workflows` run (C4 retro at v5.6) |
| Rule #18 — Doc-maintenance verifier-scoped dispatch | N=0 ("forward-looking: no dogfood result yet — graduation metrics are the first data, post-launch") | Dispatch pattern not yet exercised | First doc-maintenance dispatch; graduation metrics |
| Rule #19 — Live-presence-over-inferred-idle | N=1 (single session's RC1–RC5 + user-reported failure) | Single incident | Recurrence or a clean N=2 incident |
| Rule #20 — Shared-state-accuracy | N=1 (same session as #19: RC3 + RC4) | Single incident | Recurrence; M2 hook validation in the field |

## Out of scope for this file

- Changing any status (no active → advisory here).
- Retiring/deleting rules.
- Re-litigating the N=2 codification threshold.

Anything in those categories belongs to the dedicated advisory-review phase, driven
by the user-principal.
