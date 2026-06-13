# Migration manifest: CLAUDE.md / AGENTS.md split

This file is the **single source of truth** for the documentation refactor that
splits `CLAUDE.md` (2,111 lines) and `AGENTS.md` (1,698 lines) into lean
"operative router" files plus on-trigger referenced documents.

**Add-first rule:** a stub may NOT ship in a strip slice until the corresponding
section's `Preserved?` cell in Part B is flipped to `✓`, confirmed by running
`grep -F "<anchor>" <destination>` against the destination file.

The manifest is built from verified file state at commit `1870e59` on branch
`claude/execution-plan-6dfws3`.

**Strategy (decided this session): two parallel trees.** Each router relocates its OWN verbatim text into its own tree (`docs/protocol/claude/*` from CLAUDE.md, `docs/protocol/agents/*` from AGENTS.md, and `docs/templates/claude/*` + `docs/templates/agents/*`). Only `docs/PROTOCOL-RULES-LOG.md` (provenance) and `docs/protocol/advisory-candidates.md` (shared list) are shared. No rule body is merged across files — relocations are purely verbatim per-file copies.

---

## Part A — Stable-ID crosswalk table

| Handle | Rule | Existing #? |
|---|---|---|
| `R-TRUTH` | Truth hierarchy (ARCHITECTURE.md=truth, CLAUDE.md/AGENTS.md=process layer, code beats docs) | — |
| `R-START` | Session-start checklist (§15 smoke, topology spot-check, recent git log, fix stale doc) | — |
| `R-IMPACT` | Impact-analysis invariant (grep defs/callers/imports before editing; report blast radius) | — |
| `R-EVIDENCE` | Evidence discipline for factual claims (cite or don't claim; scope stays scoped; pre-commit trip-wire) | ADR-013 / Rules #1–3 |
| `R-ORCH` | Orchestration trigger (≥5 sub-tasks or ≥800 LOC → orchestrate, not in main context) | — |
| `R-BRIEF` | Brief-pattern adherence (verify full shape of named pattern before implementing) | project-conv #4 |
| `R-PID` | PID-scope endpoint check (verify route takes `<pid>` explicitly; inspect existing endpoints) | project-conv #5 |
| Rule #7 | Pre-commit re-verify (the pre-commit gate; close the Write→commit hole) | #7 |
| Rule #8 | Mailbox events have authority equal to user-relayed signals | #8 |
| Rule #9 | Independent reviewer convention (second-opinion, cold context) | #9 |
| Rule #10 | Joint-team mode (co-agent mode; symmetric specialization) | #10 |
| Rule #11 | Codification bias check (beneficiary annotation on new rules) | #11 |
| Rule #12 | Brief-level grep-the-writes discipline (type-declaration is not write-evidence) | #12 |
| Rule #13 | Symmetric-endpoint audit discipline (a new defense names what existing endpoints may be missing) | #13 |
| Rule #14 | Operator-driven Lane B template + selection criteria | #14 |
| Rule #15 | Cross-seat fix-on-received-findings convention | #15 |
| Rule #16 | User-direction without owner-spec (complementary-parallel work with mandatory convergence) | #16 |
| Rule #17 | Workflow-assisted analysis lanes (read-analysis multiplier, not implementation engine) | #17 |
| Rule #18 | Doc-maintenance as a verifier-scoped dispatch pattern | #18 |
| Rule #19 | Live-presence-over-inferred-idle | #19 |
| Rule #20 | Shared-state-accuracy (awareness gate computes truth; does not trust stale snapshot) | #20 |

---

## Part B — Migration map table

Columns:
- **Source file** — `CLAUDE.md` or `AGENTS.md`
- **Source heading + line range** — `#`/`##` heading text and start–end lines (end = line before next heading)
- **Destination** — target path (most do not exist yet; that is expected)
- **Root stub (ID)** — handle/Rule# kept as stub in the root file, `STAYS` (kept in root in full or short), or `—` (pure relocation, no stub)
- **Grep anchor** — a distinctive verbatim phrase (5–12 words) unique in the source file (verified via `grep -cF "<phrase>" <file>` → 1)
- **Preserved?** — `✗ (not yet relocated)` for all rows; later slices flip to ✓

### CLAUDE.md sections

| Source file | Source heading + line range | Destination | Root stub (ID) | Grep anchor (unique phrase) | Preserved? |
|---|---|---|---|---|---|
| CLAUDE.md | `# Session-start protocol (read me first)` L1–30 | `docs/protocol/claude/core.md` (detail) | `STAYS (R-TRUTH verbatim + R-START stub)` | `Trust the code; update the prose when it diverges` | ✓ (added; root copy retained) |
| CLAUDE.md | `# The user-principal's intent for this program (read PROGRAM-MANUAL.md)` L31–52 | STAYS in root (short pointer) | `STAYS (short pointer)` | `capability-maximization user manual` | ✗ (not yet relocated) |
| CLAUDE.md | `# Repo doc map` L53–71 | STAYS in root (router index; update with new protocol docs) | `STAYS (router index)` | `GitNexus MCP integration was auto-documented` | ✗ (not yet relocated) |
| CLAUDE.md | `# Impact analysis before editing` L72–91 | STAYS in root (full) | `STAYS (R-IMPACT, full)` | `de-facto method across every session to date` | ✗ (not yet relocated) |
| CLAUDE.md | `# Verification discipline for factual claims` L92–101 | `docs/protocol/claude/core.md` (full body incl. 24-vs-1 origin) | `STAYS (R-EVIDENCE short stub)` | `session memory trusted over filesystem` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Rule 1 — No inventory claim without verification output` L102–113 | `docs/protocol/claude/core.md` | `STAYS (R-EVIDENCE short stub)` | `The shell never lies about what it ran` (Rule 2 section, part of R-EVIDENCE block) | ✓ (added; root copy retained) |
| CLAUDE.md | `## Rule 2 — Scoped output stays scoped` L114–124 | `docs/protocol/claude/core.md` | `STAYS (R-EVIDENCE short stub)` | `The shell never lies about what it ran` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Rule 3 — Pre-commit trip-wire for strategic docs` L125–135 | `docs/protocol/claude/core.md` | `STAYS (R-EVIDENCE short stub)` | `24-vs-1 test error` | ✓ (added; root copy retained) |
| CLAUDE.md | `## When you cannot comply` L136–145 | `docs/protocol/claude/core.md` | `—` | `Authority and verification travel together` | ✓ (added; root copy retained) |
| CLAUDE.md | `## When does this apply?` L146–158 | `docs/protocol/claude/core.md` | `—` | `specific factual claims = verification required` | ✓ (added; root copy retained) |
| CLAUDE.md | `## When you change something` L159–171 | `docs/protocol/claude/core.md` | `—` | `don't implement in main context` | ✓ (added; root copy retained) |
| CLAUDE.md | `# Working a Multi-Task Plan` L172–184 | `docs/protocol/claude/orchestration.md` | `R-ORCH (trigger stub)` | `1M / 2M+ token` | ✓ (added; root copy retained) |
| CLAUDE.md | `## When to invoke` L185–193 | `docs/protocol/claude/orchestration.md` | `—` | `orchestration overhead isn't worth it` | ✓ (added; root copy retained) |
| CLAUDE.md | `## The per-task loop (sequential, never parallel)` L194–213 | `docs/protocol/claude/orchestration.md` | `—` | `Dispatch spec compliance reviewer` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Delegation heuristics — Lane A / B / C` L214–251 | `docs/protocol/claude/orchestration.md` | `—` | `Lane A — execute in main context` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Implementer prompt template` L252–319 | `docs/templates/claude/implementer.md` | `—` | `A good implementer prompt is 80-150 lines and lets the subagent act` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Hardening notes — provenance for the implementer-template additions` L320–352 | `docs/templates/claude/implementer.md` | `—` | `do NOT trim these` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Spec reviewer prompt template` L353–381 | `docs/templates/claude/reviewer.md` | `—` | `reviewing whether Task` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Code quality reviewer prompt template` L382–403 | `docs/templates/claude/reviewer.md` | `—` | `Report: Strengths, Issues (Critical / Important / Minor)` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Plan vs. source — the divergence rule` L404–419 | `docs/protocol/claude/orchestration.md` | `—` | `motion_floor_for` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Commit discipline for reviewability` L420–435 | `docs/protocol/claude/orchestration.md` | `—` | `Baseline commit first` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Context hygiene (the long-session rule)` L436–451 | `docs/protocol/claude/orchestration.md` | `—` | `Summaries in main, full content in subagents` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Compaction signals and what to do` L452–480 | `docs/protocol/claude/orchestration.md` | `—` | `Commit pending work immediately` | ✓ (added; root copy retained) |
| CLAUDE.md | `## AskUserQuestion discipline` L481–491 | `docs/protocol/claude/orchestration.md` (body); root keeps `## Claude Code mechanics` stub | `STAYS (short stub in ## Claude Code mechanics block)` | `Are reversible only with effort (renaming a public API` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Background work` L492–501 | `docs/protocol/claude/orchestration.md` (body); root keeps `## Claude Code mechanics` stub | `STAYS (short stub in ## Claude Code mechanics block)` | `poll a background task you started` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Pre-existing failures` L502–512 | `docs/protocol/claude/orchestration.md` | `—` | `mark it \`xfail\` (or tighten tolerance) early in the branch if` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Quality vs. throughput watchpoints` L513–530 | `docs/protocol/claude/failure-modes.md` | `—` | `throughput optimization is "ship when the code quality reviewer says approve"` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Failure modes and false positives observed` L531–591 | `docs/protocol/claude/failure-modes.md` | `—` | `Spec reviewer flagged two missing requirements in a render component` | ✓ (added; root copy retained) |
| CLAUDE.md | `### Reviewer false positives` L536–564 | `docs/protocol/claude/failure-modes.md` | `—` | `automated security warnings can be wrong about instruction-following` | ✓ (added; root copy retained) |
| CLAUDE.md | `### Tool and environment failure modes` L565–584 | `docs/protocol/claude/failure-modes.md` | `—` | `File has not been read yet` | ✓ (added; root copy retained) |
| CLAUDE.md | `### Detection pattern` L585–591 | `docs/protocol/claude/failure-modes.md` | `—` | `do a quick targeted verification (single` | ✓ (added; root copy retained) |
| CLAUDE.md | `## When NOT to use this pattern` L592–601 | `docs/protocol/claude/orchestration.md` | `—` | `Tasks with constant operator feedback` | ✓ (added; root copy retained) |
| CLAUDE.md | `# Director-Operator Concurrent Operation` L602–605 | `docs/protocol/claude/director-operator.md` | `pointer` | `two parallel Claude sessions by design` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Two-seat team model (Protocol Bundle v5)` L606–646 | `docs/protocol/claude/director-operator.md` | `pointer` | `specialization is cognitive-load distribution, not hierarchy` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Role partition` L647–726 | `docs/protocol/claude/director-operator.md` | `pointer` | `Strategic-seat-default` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Signaling: narrate before acting on shared tasks` L727–745 | `docs/protocol/claude/director-operator.md` | `pointer` | `Dispatching parallel reviewers` | ✓ (added; root copy retained) |
| CLAUDE.md | `## State-asserting writes: gate on \`git log --oneline -5\`` L746–759 | `docs/protocol/claude/director-operator.md` | `pointer` | `State-asserting writes` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Race-acknowledging commit bodies` L760–771 | `docs/protocol/claude/director-operator.md` | `pointer` | `name the shift in the commit body` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Pre-commit re-verify (Rule #7)` L772–798 | `docs/protocol/claude/director-operator.md` | `pointer` | `Monitor.tsx shipped during operator's` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Mailbox events have authority equal to user-relayed signals (Rule #8)` L799–858 | `docs/protocol/claude/director-operator.md` | `pointer` | `Session-bootstrap awareness gate` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Independent reviewer convention (Rule #9)` L859–940 | `docs/protocol/claude/director-operator.md` | `pointer` | `second-opinion convention` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Joint-team mode (Rule #10)` L941–972 | `docs/protocol/claude/director-operator.md` | `pointer` | `co-agent mode` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Codification bias check (Rule #11)` L973–1002 | `docs/protocol/claude/director-operator.md` | `pointer` | `primary beneficiary` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Brief-level grep-the-writes discipline (Rule #12)` L1003–1051 | `docs/protocol/claude/director-operator.md` (full body) | `STAYS (short stub)` | `type-declaration is not write-evidence` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Symmetric-endpoint audit discipline (Rule #13)` L1052–1112 | `docs/protocol/claude/director-operator.md` (full body) | `STAYS (short stub)` | `a new defense names what existing endpoints` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Operator-driven Lane B template + selection criteria (Rule #14)` L1113–1347 | `docs/protocol/claude/director-operator.md` | `pointer` | `when operator-seat may dispatch Lane B` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Cross-seat fix-on-received-findings convention (Rule #15)` L1348–1553 | `docs/protocol/claude/director-operator.md` | `pointer` | `when one seat closes the other seat's Lane V finding` | ✓ (added; root copy retained) |
| CLAUDE.md | `## User-direction without owner-spec (Rule #16)` L1554–1632 | `docs/protocol/claude/director-operator.md` | `pointer` | `complementary-parallel work with mandatory convergence` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Workflow-assisted analysis lanes (Rule #17)` L1633–1736 | `docs/protocol/claude/director-operator.md` | `pointer` | `read-analysis multiplier, not an implementation engine` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Doc-maintenance as a verifier-scoped dispatch pattern (Rule #18)` L1737–1846 | `docs/protocol/claude/director-operator.md` | `pointer` | `librarian wielding the verifier` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Live-presence-over-inferred-idle (Rule #19)` L1847–1906 | `docs/protocol/claude/director-operator.md` | `pointer` | `read the peer's presence; don't infer liveness` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Shared-state-accuracy (Rule #20)` L1907–1940 | `docs/protocol/claude/director-operator.md` | `pointer` | `awareness gate computes truth; it does not trust a stale snapshot` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Disagreement protocol (v5)` L1941–1984 | `docs/protocol/claude/director-operator.md` | `pointer` | `2-cycle limit` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Emergency handling protocol (v5)` L1985–2039 | `docs/protocol/claude/director-operator.md` | `pointer` | `Production-affecting OR user-data-integrity issue` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Git is the tiebreaker` L2040–2050 | `docs/protocol/claude/director-operator.md` | `pointer` | `first commit to land wins` | ✓ (added; root copy retained) |
| CLAUDE.md | `## When the other party is offline` L2051–2062 | `docs/protocol/claude/director-operator.md` | `pointer` | `takes the full loop unilaterally` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Phase taxonomy (Protocol Bundle v4)` L2063–2089 | `docs/protocol/claude/director-operator.md` | `pointer` | `Detection is hybrid: explicit` | ✓ (added; root copy retained) |
| CLAUDE.md | `## Adjacent-useful work when you can't claim the loop` L2090–2111 | `docs/protocol/claude/director-operator.md` | `pointer` | `Standby OR work on pre-listed operator-claimable backlog` | ✓ (added; root copy retained) |

### CLAUDE.md — Rule provenance fragments

These are the "Codified SHA / Empirical basis / Beneficiary" provenance blocks
embedded inside each Rule #N section body. They relocate to
`docs/PROTOCOL-RULES-LOG.md` (which already has a `## Rule registry` table).

| Source file | Source heading + line range | Destination | Root stub (ID) | Grep anchor (unique phrase) | Preserved? |
|---|---|---|---|---|---|
| CLAUDE.md | Rule #12 provenance fragment (within L1003–1051) | `docs/protocol/claude/director-operator.md (within Rule #12 body)` | `—` | `Codified SHA: \`8ab0bbb\` (Protocol Bundle v5.1 ship; filled per` | ✓ (preserved verbatim within Rule body) |
| CLAUDE.md | Rule #13 provenance fragment (within L1052–1112) | `docs/protocol/claude/director-operator.md (within Rule #13 body)` | `—` | `Codified SHA: \`8ab0bbb\` (Protocol Bundle v5.1 ship; filled per` | ✓ (preserved verbatim within Rule body) |
| CLAUDE.md | Rule #14 provenance fragment (within L1113–1347) | `docs/protocol/claude/director-operator.md (within Rule #14 body)` | `—` | `Codified SHA: \`61cac6d\` (Protocol Bundle v5.2 ship; filled per chicken-and-egg` | ✓ (preserved verbatim within Rule body) |
| CLAUDE.md | Rule #15 provenance fragment (within L1348–1553) | `docs/protocol/claude/director-operator.md (within Rule #15 body)` | `—` | `Codified SHA: \`24c145a\` (Protocol Bundle v5.3 ship; filled per chicken-and-` | ✓ (preserved verbatim within Rule body) |
| CLAUDE.md | Rule #16 provenance fragment (within L1554–1632) | `docs/protocol/claude/director-operator.md (within Rule #16 body)` | `—` | `Codified SHA: \`7773502\` (Protocol Bundle` | ✓ (preserved verbatim within Rule body) |
| CLAUDE.md | Rule #17 provenance fragment (within L1633–1736) | `docs/protocol/claude/director-operator.md (within Rule #17 body)` | `—` | `Codified SHA: \`52658eb\` (Protocol Bundle v5.5 ship; filled` | ✓ (preserved verbatim within Rule body) |
| CLAUDE.md | Rule #18 provenance fragment (within L1737–1846) | `docs/protocol/claude/director-operator.md (within Rule #18 body)` | `—` | `Codified SHA: \`4eecb72\` (Protocol Bundle v5.6 ship; filled per` | ✓ (preserved verbatim within Rule body) |
| CLAUDE.md | Rule #19 provenance fragment (within L1847–1906) | `docs/protocol/claude/director-operator.md (within Rule #19 body)` | `—` | `Codified SHA: \`cec6d72\` (filled next session-close per` | ✓ (preserved verbatim within Rule body) |
| CLAUDE.md | Rule #20 provenance fragment (within L1907–1940) | `docs/protocol/claude/director-operator.md (within Rule #20 body)` | `—` | `Codified SHA: \`cec6d72\` (filled next session-close).` | ✓ (preserved verbatim within Rule body) |

---

### AGENTS.md sections

| Source file | Source heading + line range | Destination | Root stub (ID) | Grep anchor (unique phrase) | Preserved? |
|---|---|---|---|---|---|
| AGENTS.md | `# About this document` L1–20 | STAYS in AGENTS.md router (self-identity intro) | `STAYS (AGENTS router)` | `agent-agnostic root` | ✗ (not yet relocated) |
| AGENTS.md | `# Session-start protocol (read me first)` L21–51 | `docs/protocol/agents/core.md` | `STAYS (R-TRUTH verbatim + R-START stub)` | `Trust the code; update the prose when it diverges` | ✓ (added; root copy retained) |
| AGENTS.md | `# The user-principal's intent for this program (read PROGRAM-MANUAL.md)` L52–73 | STAYS in AGENTS.md router (short pointer) | `STAYS (short pointer)` | `capability-maximization user manual` | ✗ (not yet relocated) |
| AGENTS.md | `# Repo doc map` L74–92 | STAYS in root (router index; update with new protocol docs) | `STAYS (router index)` | `GitNexus MCP integration was auto-documented` | ✗ (not yet relocated) |
| AGENTS.md | `# Impact analysis before editing` L93–112 | STAYS in AGENTS.md router (full) | `STAYS (R-IMPACT, full)` | `de-facto method across every session to date` | ✗ (not yet relocated) |
| AGENTS.md | `# Verification discipline for factual claims` L113–122 | `docs/protocol/agents/core.md` | `STAYS (R-EVIDENCE short stub)` | `session memory trusted over filesystem` | ✓ (added; root copy retained) |
| AGENTS.md | `## Rule 1 — No inventory claim without verification output` L123–134 | `docs/protocol/agents/core.md` | `STAYS (R-EVIDENCE short stub)` | `Just trust me` is not acceptable | ✓ (added; root copy retained) |
| AGENTS.md | `## Rule 2 — Scoped output stays scoped` L135–145 | `docs/protocol/agents/core.md` | `STAYS (R-EVIDENCE short stub)` | `The shell never lies about what it ran` | ✓ (added; root copy retained) |
| AGENTS.md | `## Rule 3 — Pre-commit trip-wire for strategic docs` L146–156 | `docs/protocol/agents/core.md` | `STAYS (R-EVIDENCE short stub)` | `24-vs-1 test error` | ✓ (added; root copy retained) |
| AGENTS.md | `## When you cannot comply` L157–166 | `docs/protocol/agents/core.md` | `—` | `Authority and verification travel together` | ✓ (added; root copy retained) |
| AGENTS.md | `## When does this apply?` L167–179 | `docs/protocol/agents/core.md` | `—` | `specific factual claims = verification required` | ✓ (added; root copy retained) |
| AGENTS.md | `## When you change something` L180–192 | `docs/protocol/agents/core.md` | `—` | `don't implement in main context — orchestrate` | ✓ (added; root copy retained) |
| AGENTS.md | `# Multi-task orchestration` L193–210 | `docs/protocol/agents/orchestration.md` | `R-ORCH (trigger stub)` | `1M / 2M+ token` | ✓ (added; root copy retained) |
| AGENTS.md | `## When to invoke` L211–218 | `docs/protocol/agents/orchestration.md` | `—` | `orchestration overhead isn't worth it` | ✓ (added; root copy retained) |
| AGENTS.md | `## The per-task loop (sequential, never parallel)` L219–245 | `docs/protocol/agents/orchestration.md` | `—` | `Dispatch spec compliance reviewer` | ✓ (added; root copy retained) |
| AGENTS.md | `## Delegation heuristics — Lane A / B / C` L246–285 | `docs/protocol/agents/orchestration.md` | `—` | `Lane A — execute in main context` | ✓ (added; root copy retained) |
| AGENTS.md | `## Prompt template (for Lane B implementers)` L286–354 | `docs/templates/agents/implementer.md` | `—` | `A good implementer prompt is 80-150 lines and includes` | ✓ (added; root copy retained) |
| AGENTS.md | `## Hardening notes — provenance for the implementer-template additions` L355–379 | `docs/templates/agents/implementer.md` | `—` | `Carry them forward in future dispatches; if you trim the template, do NOT trim these` | ✓ (added; root copy retained) |
| AGENTS.md | `## Plan vs. source — the divergence rule` L380–394 | `docs/protocol/agents/orchestration.md` | `—` | `motion_floor_for` | ✓ (added; root copy retained) |
| AGENTS.md | `## Commit discipline for reviewability` L395–408 | `docs/protocol/agents/orchestration.md` | `—` | `Baseline commit first` | ✓ (added; root copy retained) |
| AGENTS.md | `## Context hygiene (the long-session rule)` L409–424 | `docs/protocol/agents/orchestration.md` | `—` | `Summaries in main, full content in subagents` | ✓ (added; root copy retained) |
| AGENTS.md | `## Compaction signals and what to do` L425–447 | `docs/protocol/agents/orchestration.md` | `—` | `Commit pending work immediately` | ✓ (added; root copy retained) |
| AGENTS.md | `## Quality vs. throughput watchpoints` L448–465 | `docs/protocol/agents/failure-modes.md` | `—` | `checking the right things` | ✓ (added; root copy retained) |
| AGENTS.md | `## Failure modes and false positives` L466–521 | `docs/protocol/agents/failure-modes.md` | `—` | `Fresh instance "tool X not available"` | ✓ (added; root copy retained) |
| AGENTS.md | `## When NOT to orchestrate` L522–532 | `docs/protocol/agents/orchestration.md` | `—` | `Tasks needing constant operator feedback` | ✓ (added; root copy retained) |
| AGENTS.md | `# Director-Operator Concurrent Operation` L533–536 | `docs/protocol/agents/director-operator.md` | `pointer` | `two parallel agent sessions by design` | ✓ (added; root copy retained) |
| AGENTS.md | `## Two-seat team model (Protocol Bundle v5)` L537–572 | `docs/protocol/agents/director-operator.md` | `pointer` | `specialization is cognitive-load distribution, not hierarchy` | ✓ (added; root copy retained) |
| AGENTS.md | `## Role partition` L573–639 | `docs/protocol/agents/director-operator.md` | `pointer` | `Strategic-seat-default` | ✓ (added; root copy retained) |
| AGENTS.md | `## Signaling: narrate before acting on shared tasks` L640–654 | `docs/protocol/agents/director-operator.md` | `pointer` | `Dispatching parallel reviewers` | ✓ (added; root copy retained) |
| AGENTS.md | `## State-asserting writes: gate on \`git log --oneline -5\`` L655–668 | `docs/protocol/agents/director-operator.md` | `pointer` | `State-asserting writes` | ✓ (added; root copy retained) |
| AGENTS.md | `## Race-acknowledging commit bodies` L669–680 | `docs/protocol/agents/director-operator.md` | `pointer` | `name the shift in the commit body` | ✓ (added; root copy retained) |
| AGENTS.md | `## Pre-commit re-verify (Rule #7)` L681–707 | `docs/protocol/agents/director-operator.md` | `pointer` | `Monitor.tsx shipped during operator's` | ✓ (added; root copy retained) |
| AGENTS.md | `## Mailbox events have authority equal to user-relayed signals (Rule #8)` L708–767 | `docs/protocol/agents/director-operator.md` | `pointer` | `Session-bootstrap awareness gate` | ✓ (added; root copy retained) |
| AGENTS.md | `## Independent reviewer convention (Rule #9)` L768–843 | `docs/protocol/agents/director-operator.md` | `pointer` | `second-opinion convention` | ✓ (added; root copy retained) |
| AGENTS.md | `## Joint-team mode (Rule #10)` L844–862 | `docs/protocol/agents/director-operator.md` | `pointer` | `co-agent mode` | ✓ (added; root copy retained) |
| AGENTS.md | `## Codification bias check (Rule #11)` L863–884 | `docs/protocol/agents/director-operator.md` | `pointer` | `primary beneficiary` | ✓ (added; root copy retained) |
| AGENTS.md | `## Brief-level grep-the-writes discipline (Rule #12)` L885–920 | `docs/protocol/agents/director-operator.md` (full body) | `STAYS (short stub in AGENTS router)` | `type-declaration is not write-evidence` | ✓ (added; root copy retained) |
| AGENTS.md | `## Symmetric-endpoint audit discipline (Rule #13)` L921–966 | `docs/protocol/agents/director-operator.md` (full body) | `STAYS (short stub in AGENTS router)` | `a new defense names what existing endpoints` | ✓ (added; root copy retained) |
| AGENTS.md | `## Operator-driven Lane B template + selection criteria (Rule #14)` L967–1076 | `docs/protocol/agents/director-operator.md` | `pointer` | `when operator-seat may dispatch Lane B` | ✓ (added; root copy retained) |
| AGENTS.md | `## Cross-seat fix-on-received-findings convention (Rule #15)` L1077–1190 | `docs/protocol/agents/director-operator.md` | `pointer` | `when one seat closes the other seat's Lane V finding` | ✓ (added; root copy retained) |
| AGENTS.md | `## User-direction without owner-spec (Rule #16)` L1191–1269 | `docs/protocol/agents/director-operator.md` | `pointer` | `complementary-parallel work with mandatory convergence` | ✓ (added; root copy retained) |
| AGENTS.md | `## Workflow-assisted analysis lanes (Rule #17)` L1270–1373 | `docs/protocol/agents/director-operator.md` | `pointer` | `read-analysis multiplier, not an implementation engine` | ✓ (added; root copy retained) |
| AGENTS.md | `## Doc-maintenance as a verifier-scoped dispatch pattern (Rule #18)` L1374–1483 | `docs/protocol/agents/director-operator.md` | `pointer` | `librarian wielding the verifier` | ✓ (added; root copy retained) |
| AGENTS.md | `## Live-presence-over-inferred-idle (Rule #19)` L1484–1543 | `docs/protocol/agents/director-operator.md` | `pointer` | `read the peer's presence; don't infer liveness` | ✓ (added; root copy retained) |
| AGENTS.md | `## Shared-state-accuracy (Rule #20)` L1544–1577 | `docs/protocol/agents/director-operator.md` | `pointer` | `awareness gate computes truth; it does not trust a stale snapshot` | ✓ (added; root copy retained) |
| AGENTS.md | `## Disagreement protocol (v5)` L1578–1595 | `docs/protocol/agents/director-operator.md` | `pointer` | `2-cycle limit` | ✓ (added; root copy retained) |
| AGENTS.md | `## Emergency handling protocol (v5)` L1596–1618 | `docs/protocol/agents/director-operator.md` | `pointer` | `Production-affecting OR user-data-integrity issue` | ✓ (added; root copy retained) |
| AGENTS.md | `## Git is the tiebreaker` L1619–1628 | `docs/protocol/agents/director-operator.md` | `pointer` | `The other's subagent output is discarded` | ✓ (added; root copy retained) |
| AGENTS.md | `## When the other party is offline` L1629–1634 | `docs/protocol/agents/director-operator.md` | `pointer` | `takes the full loop unilaterally` | ✓ (added; root copy retained) |
| AGENTS.md | `## Phase taxonomy (Protocol Bundle v4)` L1635–1661 | `docs/protocol/agents/director-operator.md` | `pointer` | `Standby OR work on pre-listed operator-claimable backlog` | ✓ (added; root copy retained) |
| AGENTS.md | `## Adjacent-useful work when you can't claim the loop` L1662–1673 | `docs/protocol/agents/director-operator.md` | `pointer` | `nor dispatch a duplicate reviewer` | ✓ (added; root copy retained) |
| AGENTS.md | `# Coordinating with CLAUDE.md` L1674–1698 | STAYS in AGENTS.md router | `STAYS (AGENTS router)` | `sibling documents. They share` | ✗ (not yet relocated) |

### AGENTS.md — Rule provenance fragments

| Source file | Source heading + line range | Destination | Root stub (ID) | Grep anchor (unique phrase) | Preserved? |
|---|---|---|---|---|---|
| AGENTS.md | Rule #12 provenance fragment (within L885–920) | `docs/protocol/agents/director-operator.md (within Rule #12 body)` | `—` | `Codified SHA: \`8ab0bbb\` (Protocol Bundle v5.1 ship; chicken-and-egg` | ✓ (preserved verbatim within Rule body) |
| AGENTS.md | Rule #13 provenance fragment (within L921–966) | `docs/protocol/agents/director-operator.md (within Rule #13 body)` | `—` | `Codified SHA: \`8ab0bbb\` (Protocol Bundle v5.1 ship; chicken-and-egg` | ✓ (preserved verbatim within Rule body) |
| AGENTS.md | Rule #14 provenance fragment (within L967–1076) | `docs/protocol/agents/director-operator.md (within Rule #14 body)` | `—` | `Codified SHA: \`61cac6d\` (Protocol Bundle v5.2 ship; chicken-and-egg` | ✓ (preserved verbatim within Rule body) |
| AGENTS.md | Rule #15 provenance fragment (within L1077–1190) | `docs/protocol/agents/director-operator.md (within Rule #15 body)` | `—` | `Codified SHA: \`24c145a\` (Protocol Bundle v5.3 ship; chicken-and-egg` | ✓ (preserved verbatim within Rule body) |
| AGENTS.md | Rule #16 provenance fragment (within L1191–1269) | `docs/protocol/agents/director-operator.md (within Rule #16 body)` | `—` | `Codified SHA: \`7773502\` (Protocol Bundle` | ✓ (preserved verbatim within Rule body) |
| AGENTS.md | Rule #17 provenance fragment (within L1270–1373) | `docs/protocol/agents/director-operator.md (within Rule #17 body)` | `—` | `Codified SHA: \`52658eb\` (Protocol Bundle v5.5 ship; filled` | ✓ (preserved verbatim within Rule body) |
| AGENTS.md | Rule #18 provenance fragment (within L1374–1483) | `docs/protocol/agents/director-operator.md (within Rule #18 body)` | `—` | `Codified SHA: \`4eecb72\` (Protocol Bundle v5.6 ship; filled per` | ✓ (preserved verbatim within Rule body) |
| AGENTS.md | Rule #19 provenance fragment (within L1484–1543) | `docs/protocol/agents/director-operator.md (within Rule #19 body)` | `—` | `Codified SHA: \`cec6d72\` (filled next session-close per` | ✓ (preserved verbatim within Rule body) |
| AGENTS.md | Rule #20 provenance fragment (within L1544–1577) | `docs/protocol/agents/director-operator.md (within Rule #20 body)` | `—` | `Codified SHA: \`cec6d72\` (filled next session-close).` | ✓ (preserved verbatim within Rule body) |

---

## Divergence notes

1. **CLAUDE.md `## Failure modes and false positives observed` (L531) vs AGENTS.md `## Failure modes and false positives` (L466):** Different heading text and different body (CLAUDE.md has 7 numbered items + Detection pattern as a sub-section; AGENTS.md has 8 shorter items merged into one section with `## When NOT to orchestrate` as a sibling rather than a sub-section). Mapped to `docs/protocol/failure-modes.md` for both but they are NOT identical bodies — the strip slices will need to write file-specific content or merge them explicitly.

2. **CLAUDE.md `## When NOT to use this pattern` (L592) vs AGENTS.md `## When NOT to orchestrate` (L522):** Different heading text; nearly parallel body (AGENTS.md is more terse and agent-agnostic). Both map to `docs/protocol/orchestration.md`. Initial anchor selection for AGENTS.md `## Failure modes and false positives` collided with AGENTS.md `## When NOT to orchestrate` (both could match "Tasks needing constant operator feedback"). Corrected: `## Failure modes and false positives` uses anchor `Fresh instance "tool X not available"` (unique to that section at L495); `## When NOT to orchestrate` uses `Tasks needing constant operator feedback` (unique to L531). Verified: `grep -cF 'Fresh instance "tool X not available"' AGENTS.md` → 1; `grep -cF "Tasks needing constant operator feedback" AGENTS.md` → 1.

3. **CLAUDE.md Rule #14 spans L1113–1347 (234 lines) and has full sub-sections (`### Selection criteria`, `### Template`, `### Working criteria`, `### Composition`, `### Beneficiary`).** AGENTS.md Rule #14 spans L967–1076 (109 lines) with compressed sub-sections (`### Selection criteria (ALL must hold)`, `### Template (5-stage flow)`, `### Working criteria (dogfood)`, `### Composition`, `### Beneficiary (per R11)`). Both map to `docs/protocol/director-operator.md`; the strip slices should use the CLAUDE.md body as canonical (more detailed).

4. **AGENTS.md `## Prompt template (for Lane B implementers)` (L286)** has a different heading from CLAUDE.md's `## Implementer prompt template` (L252) and a lighter body (no Spec reviewer / Code quality reviewer templates — those are referenced out to CLAUDE.md). Both map to `docs/templates/implementer.md`.

5. **Two-tree decision (this session).** Analysis showed AGENTS.md is a compressed, agent-agnostic rendering and CLAUDE.md is the detailed Claude-specific superset (NOT byte-identical — the earlier 'identical body' assumption was falsified for Rules #9–#15, the orchestration prose, failure-modes, disagreement, emergency, role-partition, and adjacent-work sections; Rules #8, #17 and the two-seat model ARE identical). To preserve each file's voice exactly with zero rewording and clean Preserved?-grep checks, each router relocates its own verbatim text into its own tree. This keeps (but relocates off the always-loaded hot path) the existing duplication; it does not attempt dedup. Future protocol edits must touch both trees.

6. **Four-seat extension (added post-migration).** The transition from the 2-seat to 4-seat model is documented in `docs/protocol/claude/four-seat-extension.md`. The core protocol documents (`director-operator.md`, `CLAUDE.md`, `AGENTS.md`) have been updated to reflect this shift, and the extension details the tooling cutover and `coordinator` role.
