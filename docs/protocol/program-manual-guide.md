# Guideline — Using & Maintaining `docs/PROGRAM-MANUAL.md`

*The manual is a **deep reference snapshot**, not a living source of truth. Its
prose is durable; its `file:line` anchors, LOC counts, and numeric floors decay
with every commit. This guideline governs how to read it without over-loading,
and how to keep it from becoming a maintained-looking artifact that lies.*

> Truth hierarchy: **current source and `ARCHITECTURE.md` win on any factual
> conflict** (code beats docs; `ARCHITECTURE.md` is the verified-truth doc). The
> manual is the narrative + operating layer on top of them.

-----

## Activation (wire this upstream, or it binds nothing)

This guide governs the manual, but a load policy living in an unread doc binds
nothing. The pointer below is wired into **both** the top of
`docs/PROGRAM-MANUAL.md` *and* the load-policy section of **both** root routers
(`CLAUDE.md` and `AGENTS.md`), so a seat sees it **before** deciding whether to
open the 219KB manual:

> `docs/PROGRAM-MANUAL.md` is pull-on-demand only. Before using or maintaining
> it, read `docs/protocol/program-manual-guide.md`. Do not load the full manual
> at session start.

Keep this guide as a sidecar at `docs/protocol/program-manual-guide.md` — do
**not** merge it into the manual (that would grow the thing it governs).

-----

## Part 1 — Using the manual

### 1.1 Load policy (binding)

- **Never load the manual at session start.** It is pull-on-demand only. At
  ~219KB it is the single largest read-me-first hazard in the repo.
- **Read by section, not whole-document.** Open only what the task needs:

  |Need                                                        |Read     |
  |------------------------------------------------------------|---------|
  |Mental model / how a run flows                              |§1–§2    |
  |Max-capability operation                                    |§5       |
  |Concrete run configuration                                  |§5.4–§5.6|
  |Troubleshooting / failure modes                             |§7.5     |
  |Before trusting old line numbers / source maps / plan claims|§7.6     |
- **Whole-doc read is justified only** for program-level orientation, capability
  planning, or manual maintenance.
- **Dispatching a subagent:** pass only the relevant **section anchor** + the
  task-specific requirement — never the whole manual, never inherited prose.

### 1.2 Trust model (when to believe it)

- **Check the staleness first.** The provenance header states the HEAD/date the
  manual was verified at. Run `git log --oneline <that-HEAD>..HEAD` — the more
  commits since, the more its specifics are suspect.
- **Prose ages slowly; anchors age fast.** Trust the *narrative* (what a
  subsystem does, how stages connect) more than any `file:line` or LOC number.
- **Grep the symbol, not the line.** The function/class name is the load-bearing
  reference; if a line number doesn't match, re-grep — don't assume the doc is
  wrong about the *behavior*.
- **On any factual conflict, verify against current source and `ARCHITECTURE.md`,
  which win** — the manual loses.
- **Treat numeric floors/thresholds as point-in-time.** Confirm against source
  before relying on a specific value (composite floors, lipsync floor, cascade
  order, etc.).

-----

## Part 2 — Maintaining the manual

### 2.1 It is regenerated, not hand-grown

The manual is produced by the Rule #17 read-only analysis workflow *(Rule #17 —
workflow-assisted analysis lanes; rule body in `docs/protocol/claude/director-operator.md`,
agent-agnostic copy in `docs/protocol/agents/director-operator.md`; provenance in
`docs/PROTOCOL-RULES-LOG.md`)* — parallel mapping subagents → synthesis → every
`file:line` claim verified + sampled.
**Default to regeneration for anything structural; reserve hand-edits for small,
localized corrections.** A drifted manual is re-derived, not patched section by
section.

### 2.2 What invalidates it (regenerate triggers)

Regenerate (or scope-patch the affected sections) when any of these land:

- a module is **renamed, moved, deleted**, or split (esp. the shim ↔ `domain/`
  layout, or anything that changes a canonical path);
- the **API/cascade order** or engine roster changes;
- **gate logic, auto-approve rules, or thresholds** change;
- a **new subsystem or stage** is added;
- a documented **footgun is fixed** (update §7.6 *and* the relevant section).

### 2.3 Update the provenance every time — make staleness visible

- Every regeneration **must** update the document-level provenance header to the
  new HEAD/date. **Never leave a stale "accurate at" stamp** — a fresh-looking
  header on stale content is the core failure mode.
- **Do not hand-type per-section verification dates that rot independently.**
  Either keep verification **document-level only**, or tie any per-section stamp
  to an automated re-verification pass (below) that re-stamps it. A hand-typed
  "verified 2026-05-30" on a section whose code changed next week actively lies.

### 2.4 Make drift fail loud (the verification pass)

- **Precondition — the validator exists and covers the manual.** The
  `check_doc_claims` validator (Rule #18 — verifier-scoped doc-maintenance; rule
  body in `docs/protocol/claude/director-operator.md` / `docs/protocol/agents/director-operator.md`,
  provenance in `docs/PROTOCOL-RULES-LOG.md`) lives at `scripts/check_doc_claims.py`
  and **does cover `docs/PROGRAM-MANUAL.md`**: run
  `.venv/bin/python scripts/check_doc_claims.py docs/PROGRAM-MANUAL.md`. It flags
  `def_drift` anchors and auto-fixes them with `--fix`. **Known limitation:** the
  comma-list multi-range anchor form (`file.py:A-B, C-D`) is *not* verified — split
  such anchors into single ranges if you need them gated.
- When run, it should **flag every anchor whose symbol no longer resolves**.
- Treat its output as a gate, not a report: unresolved anchors block "the manual
  is current" claims. Silent staleness is the enemy; a noisy drift report is the
  fix.
- Run it on a cadence (e.g. before relying on the manual for a capability-planning
  task) and after any large refactor.

### 2.5 Hand-edit discipline (when you do patch)

- **Add-only / localized:** correct the affected anchor + line, don't rewrite
  surrounding prose.
- **Prefer symbol names over fresh line numbers** in any edit, so the patch
  doesn't immediately re-rot.
- **No semantic/behavioral claim changes without verifying against source** and
  citing the command that confirmed it (ADR-013: verification travels with the
  claim).
- **No new aspirational guarantees** ("never fails", "fully safe unattended").
  Preserve existing caveats; the manual documents footguns, it doesn't paper over
  them.

### 2.6 Anti-duplication

- Don't add a second capability/config table that overlaps §5.3 / §5.4 — reconcile
  into or index the existing ones. Parallel tables drift apart.
- One home per fact. If something belongs in `ARCHITECTURE.md`, link to it; don't
  restate it here where it can diverge.

-----

## When in doubt

The manual tells you **what the system does and how to drive it**; current source
and `ARCHITECTURE.md` tell you **what is true right now**. Use the manual to
navigate and plan; verify against source before you act on a specific number,
path, or line. If the two disagree, the source wins and the manual needs a
regenerate.
