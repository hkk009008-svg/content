# Session-start protocol (read me first)

**Truth lives in `ARCHITECTURE.md` at the repo root.** This file (CLAUDE.md)
is the *process layer* — the impact-analysis method, multi-task orchestration, session
discipline. `ARCHITECTURE.md` is the *truth layer* — verified facts about the
pipeline, with file:line references and a §15 smoke test. When they disagree
about facts, `ARCHITECTURE.md` wins.

Both files drift from the actual code between sessions. Before doing any
non-trivial work, verify against current source. If a claim is stale,
**fix the relevant file in the same change** that exposes the staleness —
don't let a wrong claim survive your session.

Trust the code; update the prose when it diverges.

## Load policy (how to use this file)

This file is an **operative router**: it holds only what must be active *before
you know the task*. Everything task-specific lives in linked docs, pulled on demand.

- Do NOT read linked protocol docs at session start.
- Read a linked doc only when its trigger fires.
- When dispatching a subagent, include only the relevant rule IDs + template
  slice — never inherited doctrine.
- `docs/PROGRAM-MANUAL.md` is pull-on-demand only — read
  `docs/protocol/program-manual-guide.md` before using/maintaining it; never load
  the full manual at session start.

## R-START — session-start checklist
Scope: both
Trigger: start of every session, before non-trivial work.
Action: (1) Run the §15 smoke block — `.venv/bin/python scripts/ci_smoke.py`; if it
fails, the doc is stale OR the working tree is broken — fix one before proceeding.
(2) Skim `ARCHITECTURE.md` §2 topology; spot-check `ls cinema/ cinema/phases/
cinema/review/ cinema/shots/` and `wc -l cinema_pipeline.py web_server.py
phase_c_ffmpeg.py`. (3) `git log --oneline -20`; if a commit touched a module
documented in `ARCHITECTURE.md` since its `*Last verified:*` footer, re-read that
section against the code. (4) If you find a stale claim, fix `ARCHITECTURE.md` first,
in the same commit (or a `docs:` prep commit right before) the task lands.
Evidence: smoke output captured; the fixing commit when a claim was stale.
Details: docs/protocol/claude/core.md

# The user-principal's intent for this program (read PROGRAM-MANUAL.md)

**The user-principal has designated [docs/PROGRAM-MANUAL.md](docs/PROGRAM-MANUAL.md)
as the canonical
expression of their intent for this program.** Read it early to internalize *what we
build* — turning a script/idea into finished, photorealistic cinematic video with
synced audio (manual §1–§2) — and *how the user wants it driven*: to realize the
program's **full capability** (manual §5 is the capability-maximization playbook;
§3/§4/§6 show how the machine interconnects). When a decision trades off against
realizing that full capability, **surface it rather than silently making the call.**
Keep the manual true as the code evolves (same staleness discipline as `ARCHITECTURE.md`).

# Repo doc map

| Need to | Read |
|---|---|
| Get oriented (purpose + quick start) | [README.md](README.md) |
| Understand the code (verified truth — what's where, what does what) | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Learn the whole program + how to operate it for maximum capability | [docs/PROGRAM-MANUAL.md](docs/PROGRAM-MANUAL.md) |
| Run / configure / troubleshoot | [OPERATIONS.md](OPERATIONS.md) |
| See WHY the architecture is shaped this way (ADR log) | [DECISIONS.md](DECISIONS.md) |
| Full process detail (core / orchestration / director-operator / failure-modes) | [docs/protocol/claude/](docs/protocol/claude/) |
| Subagent prompt bodies (implementer / reviewer) | [docs/templates/claude/](docs/templates/claude/) |
| Rule provenance (codified SHAs, empirical basis, beneficiary/consent) | [docs/PROTOCOL-RULES-LOG.md](docs/PROTOCOL-RULES-LOG.md) |
| The CLAUDE/AGENTS operative-split map | [docs/protocol/migration-map-claudemd-split.md](docs/protocol/migration-map-claudemd-split.md) |
| Current leadership critique + forward direction | [docs/STRATEGIC_REVIEW-2026-06-10.md](docs/STRATEGIC_REVIEW-2026-06-10.md) |
| Test-coverage gaps + prioritized test proposal | [docs/TEST-COVERAGE-ANALYSIS-2026-06-14.md](docs/TEST-COVERAGE-ANALYSIS-2026-06-14.md) |
| Execute a roadmap session (operator manual, why + how + acceptance) | [docs/HANDOFF-roadmap-2026-05-24.md](docs/HANDOFF-roadmap-2026-05-24.md) |
| Past handoffs (historical) | [docs/archive/](docs/archive/) |

Don't duplicate ARCHITECTURE.md content in this file. Record load-bearing subsystem
facts in `ARCHITECTURE.md`; for decisions (with rationale), append to `DECISIONS.md`
— never edit prior entries.

# Impact analysis before editing

Before modifying a function, class, or method, gauge its blast radius with
grep + Read (the de-facto method across every session to date):

- `grep -rn 'symbolName' --include='*.py' .` to find the definition + callers;
  Read the call sites; grep imports for cross-file references.
- Report the direct callers + risk to the user before editing a high-fanout
  symbol.
- Before committing, run `git show --stat` / `git diff` to confirm the changed
  scope matches intent.

For renames / extracts / splits: grep the symbol across the repo first
(callers, imports, string references), update every site, then re-grep to
confirm none remain. Don't find-and-replace blind to the call graph.

# Verification discipline (R-EVIDENCE)
Scope: both
Trigger: making any specific factual/inventory claim — "N files", "Y functions",
"Z tests", "N LOC", "present in <path>", "absent from <path>", "X is unused".
Action: cite the producing command's output in the same change (paste command +
output, or `verified via $ <cmd> → <result>`). A command scoped to one path proves
only that path — re-run at the wider scope before making a wider claim. If you
cannot run the verifying command, label the claim **unverified** rather than
asserting it. Never apply director-voice authority over an unverified factual claim.
Evidence: the command + its output, in the doc/commit body (cite or don't claim).
Details: docs/protocol/claude/core.md (ADR-013; the 24-vs-1 origin story).

# Measurement-as-artifact (R-MEASURE)
Scope: both
Trigger: recording a number that backs a GO/NO-GO verdict, a gate threshold,
or a spec/record claim (arc scores, VRAM peaks, prices, durations, counts).
Action: the number must be produced by a COMMITTED script/command and
persisted to (or directly citable from) a `logs/` artifact in the same change
that records it. Ad-hoc runtime measurements may be recorded only when
explicitly labeled estimate / runtime-unreproducible. Extends R-EVIDENCE from
"cite the command" to "commit the instrument".
Evidence: script path + `logs/` artifact cited next to the number.
Details: docs/PROTOCOL-RULES-LOG.md (R-MEASURE entry; origin = the 2026-06-11
half-crop numbers that backed S2/S3 verdicts from REPL-only measurement).

# Verification tiering (R-VERIFY-TIER)
Scope: both
Trigger: about to launch a 3rd+ independent verification pass on a claim two seats
already confirmed; OR confirming a code defect you are NOT fixing this session.
Action: (A) For doc-only notes about an already-known/deferred defect, convergence =
TWO independent seats confirming the same file:line claims (a Rule #23 co-sign counts
as one). A 3rd pass is allowed ONLY for a genuinely different question, stated before
launch. Does NOT relax per-commit production-code verification (Lane V / Rule #9).
(B) An agent-confirmed defect left unfixed this session must ship a
`pytest.mark.xfail(strict=True, reason=...)` pin in the same session, or be labeled
`test-infeasible` with a one-line reason in the handoff — so CI, not the next
session's agents, re-verifies.
Evidence: the stated new question for any 3rd pass; the xfail pin (or test-infeasible label).
Details: docs/protocol/claude/core.md (R-VERIFY-TIER); origin = audit wf_6be2ee18-f4b
(the §8.5 char-landscape note drew ~25-31 agent-runs across 4 passes for one doc paragraph).

# Multi-task orchestration (R-ORCH)
Scope: both
Trigger: a plan with ≥5 independent sub-tasks OR ≥800 LOC of total change; or a
user-referenced plan file under `docs/superpowers/plans/`.
Action: orchestrate — do NOT implement in main context. Main holds the plan + task
state + ~1–3k summary per task; a fresh implementer subagent does each task, then a
spec reviewer + a code-quality reviewer review the actual diff per task. **Never run
two implementers in parallel on shared files** (sequential only); reviewers go after
implementation. A single change OR tightly-coupled work → stay in main context.
Evidence: one commit per task (clean BASE..HEAD range); task state.
Details: docs/protocol/claude/orchestration.md; prompt bodies in docs/templates/claude/.

# Implementation safety rules (specific, repeatedly useful — tied to prior CRITICALs)

## R-BRIEF — brief-pattern adherence
Scope: both
Trigger: a brief says "mirror pattern X at file:line" or "use the existing _foo_-style endpoint".
Action: verify the FULL shape of X (signature, route path, scope params, error
handling, lock guards) before implementing — brief-pattern references are implicit
specs. If the named helper doesn't exist or the wording is ambiguous, report the
divergence BEFORE implementing.
Details: docs/protocol/claude/director-operator.md (composes with Rule #12).

## R-PID — pid-scope endpoint check
Scope: both
Trigger: adding/touching an HTTP endpoint on a project-scoped resource (shots,
scenes, locations, characters).
Action: verify the route takes `<pid>` explicitly. Do NOT scan `list_projects()` to
find a matching resource — IDs collide across projects. Inspect a sibling endpoint
(e.g. `api_update_shot_prompt`) to confirm route shape + scoping.
Details: docs/protocol/claude/director-operator.md (Rule #13).

## R-SKILL — project-skill load triggers
Scope: both
Trigger: about to author, modify, review, or debug ComfyUI graph code/JSON
(`pulid*.json`, node wiring, samplers, PuLID/IP-Adapter/LoRA chains,
graph-injection helpers in `quality_max.py`) — or pipeline-level
video-generation design work (shot routing, video-API selection,
identity/continuity systems, lip-sync).
Action: invoke the matching project skill BEFORE writing or judging the code —
`comfyui-mastery` for ComfyUI-graph work, `ai-video-gen` for pipeline-level
work. When a skill prior shapes a verdict, name it in the work product (the
2026-06-11 S2 dual-PuLID verdicts leaned on comfyui-mastery's single-face
prior + `ApplyPulidAdvanced.attn_mask` escape hatch).
Details: .claude/skills/comfyui-mastery/SKILL.md; .claude/skills/ai-video-gen/SKILL.md.

## Rule #12 — grep-the-writes
Scope: both
Trigger: a brief names a schema field / dict key / mutator / write-path as a target of new code.
Action: grep the production WRITE site (not just the type declaration) to prove the
symbol is populated at runtime — type-declaration is not write-evidence. Cite the grep.
Details: docs/protocol/claude/director-operator.md (Rule #12).

## Rule #13 — symmetric-endpoint audit
Scope: both
Trigger: adding/modifying an endpoint that bypasses a fence, gates on a persistent
flag, or touches shared state other endpoints touch.
Action: audit ALL sibling endpoints on the same fence/flag/state for parallel checks
the new one should mirror — and for checks the existing ones may be missing; fold the
fix or document the exemption.
Details: docs/protocol/claude/director-operator.md (Rule #13).

# Director–Operator concurrent operation (minimal model)

Four Claude sessions (two pairs) run in parallel by design — **director-seats** (strategy, briefs,
ADRs, push decisions) and **operator-seats** (independent post-commit verification,
doc-sync, mailbox reports). Four seats / two pairs of one team; specialization, not hierarchy;
all serve the user-principal. A `coordinator` seat is spawned **on demand** at multi-pair-wrap
boundaries for read-only cross-pair audit — not a standing concurrent seat (see
docs/protocol/claude/four-seat-extension.md §10). Load-bearing invariants:

- **User is principal.** User direct instructions override everything.
- **Authority precedence:** user > git commits (durable record) > mailbox `sent/`
  events (bind the receiving seat — Rule #8) > STATE.md (stale cache) > default.
- **Git is the tiebreaker.** Before acting on a shared task, run `git log --oneline -3`;
  the first commit to land wins.
- **Signal via artifacts** (mailbox event / presence file), not chat alone.

Full governance — Rules #7–#23, the disagreement protocol, emergency handling, phase
taxonomy, and mailbox protocol — lives in **docs/protocol/claude/director-operator.md**;
read it only when coordinating with the other seat. Rule provenance (codified SHAs,
empirical basis, beneficiary/consent) is in docs/PROTOCOL-RULES-LOG.md.

- **Rule #23 co-sign is TIERED** (Lever #7, audit `wf_6be2ee18-f4b`; body in
  `docs/protocol/claude/four-seat-extension.md` §6). Classifier: *would the
  co-signer's verification change which files/sites the implementation touches?*
  **Tier A** (yes) = co-signer lands a mailbox `verification-report` BEFORE dispatch
  (async-OK via workflow+mailbox, no session restart). **Tier B** (no) = awareness
  heads-up, 48h proceed-if-no-objection. Unsure → Tier A.

# Claude Code mechanics

- **AskUserQuestion** — use for choices that are cross-cutting, set policy
  (advisory-vs-fail gates), or are reversible only with effort (public-API rename,
  license). Don't ask for which file a helper goes in or a naming choice the file's
  convention answers — make the reasonable call and keep going.
- **Background work** — `run_in_background: true` for long verification (pytest,
  vite build) when you have independent work meanwhile; don't poll a task you
  started — the harness notifies on completion.
- **Dispatch templates** — implementer + reviewer prompt bodies live in
  docs/templates/claude/. Per the load policy, a dispatch includes only the relevant
  rule IDs + the template slice, never inherited doctrine. Every dispatch includes
  the templates' **Git hygiene** block (subagents prefix all git with
  `env -u GIT_INDEX_FILE` — seat-index corruption vector, 2026-06-12).
- **Git-tooling sharp edges** — the recurring shared-tree/index edges (phantom index,
  case-only renames, pathspec discipline, `env -u GIT_INDEX_FILE`, ComfyUI cache-hit
  false-fail) are documented once in `docs/protocol/claude/core.md` →
  "Git-tooling sharp edges (standing)". Reference it; do not re-derive in handoffs.
