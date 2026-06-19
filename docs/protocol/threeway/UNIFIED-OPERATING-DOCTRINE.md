# Unified Operating Doctrine — Claude · Codex · Antigravity

**Status:** Active reference. **Truth-source pointers:** the cross-provider protocol itself
is specified in
[`docs/superpowers/specs/2026-06-19-cross-provider-seat-topology-design.md`](../../superpowers/specs/2026-06-19-cross-provider-seat-topology-design.md);
the agent-agnostic principle root is [`AGENTS.md`](../../../AGENTS.md); Claude tool mechanics are in
[`CLAUDE.md`](../../../CLAUDE.md); Codex mechanics are in
[`docs/protocol/codex/continuation.md`](../codex/continuation.md). **When this doc and any of
those disagree on a fact, they win and this doc is stale — fix it in the same change.**

This document is the single statement of the rules **all three providers follow**. It exists
because the user-principal wants one unified system across Claude, Codex, and Antigravity — not
three disconnected playbooks. It folds the **three-way signed-bus protocol** and
**Antigravity** into that model, and gives one **capability-mapping table** so each provider
binds the shared rules to its own primitives.

---

## 0. The two layers (read this first)

The system has **two layers**. Keeping them separate is what lets "unified rules" and "Antigravity
holds no seat" both be true at once.

| Layer | What it governs | Cross-provider? | Where it lives |
|---|---|---|---|
| **Layer 1 — Protocol / topology** | *Who* builds / verifies / integrates / releases; the signed event bus; the merge-gate; signatures | **Provider-fixed** (independence is the point) | spec §4–§9; the `threeway/` package |
| **Layer 2 — Operating doctrine** | *How* any session works: evidence, verification, agents/subagents, orchestration, git hygiene, coordination | **Portable** — every provider follows it verbatim | this doc Part II; `AGENTS.md`; `docs/protocol/{agents,claude}/` |

- **Layer 2 is what you adopt to "follow the same rules."** It is provider-neutral. Claude, Codex,
  and Antigravity all obey it; only the *mechanism* (the tool you call) differs — see the Part III
  mapping.
- **Layer 1 is what fixes who-may-do-what.** It is deliberately *not* symmetric across providers:
  the builder's provider may never be the primary verifier or executing integrator of its own work.
  Antigravity is excluded from Layer-1 seats by design (§1, D11).

---

# Part I — Layer 1: the three-way cross-provider protocol

> Full normative detail is in the spec. This is the operating summary every provider needs in
> context. **Build status matters: do not treat this as live infrastructure yet — see §I.5.**

## I.1 Why it exists

A formal audit of the imported "Three-Way kit" did not clear its gate on two grounds (spec §1):
(1) the correctness argument needs **three distinct providers**, but the repo ran **four all-Claude
seats**; (2) two CRITICALs lived on **Antigravity's CLI write path**. The user-principal's design
neutralizes both: **cross-provider pairs** restore independence, and **Antigravity leaves the CLI
write path** (strategic reasoning becomes human-relayed apps; the overseer is a mechanical, code-read-only process).

## I.2 Seats and who occupies them (spec §4, `threeway/loop.py:43-52`)

| Seat (bus id) | Provider | Layer | May NOT |
|---|---|---|---|
| `director` (Pair A) | **Codex** | build (own branch) | push `main`; verify/integrate own work |
| `director2` (Pair B) | **Claude** | build (own branch) | push `main`; verify/integrate own work |
| `operator` (Pair A) | **Claude** | verify (**read-only repo**) | edit candidate; integrate; push `main` |
| `operator2` (Pair B) | **Codex** | verify (**read-only repo**) | edit candidate; integrate; push `main` |
| `coordinator` (Pair A) | **Claude** | integrate (staging refs only) | write `main`; semantic code edits |
| `coordinator2` (Pair B) | **Codex** | integrate (staging refs only) | write `main`; semantic code edits |
| **merge-gate** | mechanical | release (**sole writer of protected `main`**) | run candidate code |
| `overseer` | mechanical | strategy (control-plane; **read-only on code**) | author code; issue a verdict |
| dual chief | **Gemini Deep Think + ChatGPT Pro** (apps, human-relayed) | strategy | write code or state directly |

**Codex occupies:** `director` (Pair A builder), `operator2` (Pair B verifier), `coordinator2`
(Pair B integrator). **Claude occupies:** `director2` (Pair B builder), `operator` (Pair A
verifier), `coordinator` (Pair A integrator). **Antigravity occupies no seat** — see Part IV / the
Antigravity manual.

**Emergent independence property:** the provider that wrote a change is locked out of the *primary*
verification and the *executing* integration of its own work.

## I.3 The two buses (do not confuse them)

| | Legacy mailbox bus (live today) | Three-way signed bus (built, not yet live) |
|---|---|---|
| Location | `coordination/mailbox/` (`sent/`, `seen/<seat>.txt`) | `coordination/threeway/` + git ref `refs/threeway/events` |
| Record | timestamp-named markdown events | immutable **signed** JSON facts, monotonic `seq` |
| Signatures | none | **mandatory** Ed25519 per seat (`threeway/keys.py`) |
| Authority | the current live coordination substrate | the *future* substrate after migration |

## I.4 The two loops (spec §5)

- **Tactical (per task):** `brief → build → preliminary verify → integrate (stage) → release
  attestation → release`. The director builds on its branch; the cross-provider operator verifies a
  fresh checkout; the coordinator does a **deterministic merge-only** stage (any conflict → ABORT →
  REWORK, never a semantic edit); the operator re-verifies the **exact `integration_sha`**; the
  merge-gate promotes via **exact-SHA compare-and-swap** only when both the operator's release
  attestation and the overseer's `release_order` exist.
- **Strategic (per cycle):** `results → overseer (data→info) → dual chief (analyze + order) →
  overseer (distribute briefs + cycle_go) → tactical loop`. The overseer's `cycle_go` is the
  *strategic* key; the per-SHA `release_order` is the *merge* key.

The merge-gate **re-evaluates the full predicate itself** from authoritative bus state and **never
trusts the trigger or runs candidate code** (`threeway/gate.py:95-144`,
`threeway/predicate.py:39-153`). Authority is checked **by seat**, not by signature validity alone
(`predicate.py:120-127`): `overseer` signs brief/assignment/cycle_go/release_order, the executing
coordinator signs the candidate, the named primary verifier signs attestations, `ci` signs
`ci_result`.

## I.5 Build status — what is and is NOT real yet (verify before relying)

- **Slice 1 + Slice 2 = built and merged.** The `threeway/` package (signed JSON bus, effective-state
  reducer, gate-computed tier, mechanical exact-SHA merge-gate, `RefEventStore` on
  `refs/threeway/events`) exists and passes its adversarial gate suite.
- **The package is wired into NOTHING.** `import threeway` appears only inside `threeway/` and
  `tests/` — no live seat, harness, or CI emits a threeway event today. The live coordination
  substrate is still the **legacy mailbox bus**.
- **Slice 2.5 (legacy-bus migration) is a DEFERRED tracking stub**, not an implementation plan
  ([plan](../../superpowers/plans/2026-06-19-cross-provider-seat-topology-slice2.5-legacy-bus-migration.md)).
- **Slice 3 (strategic loop + T2/T3 co-sign) is unbuilt** — `co_sign_satisfied` returns False for
  T2/T3, so escalated tiers cannot promote yet.
- **Keys are not provisioned** — `coordination/threeway/keys/` holds only a README; no `.pub` files
  exist. The merge-gate protected runner is design intent, not deployed.

**Therefore "adopting the protocol" means executing the remaining migration in order, not flipping a
switch.** See each provider's adoption manual for the sequenced path.

## I.6 Load-bearing Layer-1 invariants (memorize)

1. **No dual-write authority at any point** (spec §8 item 8, line 400; Slice 2.5 line 70, *audited*). Migration is
   **shadow read-only projection → single-writer cutover**. The legacy mailbox stays authoritative
   until cutover; the new bus shadows it. Never "read old from mailbox, write new to the bus."
2. **The builder's provider never primarily verifies or executes integration of its own work.**
3. **The merge-gate is the sole writer of protected `main`** and **never executes candidate code**;
   it recomputes the merge and refuses to trust the coordinator's claimed `integration_sha`.
4. **Every load-bearing fact is signed; authority is by seat.**
5. **Antigravity is off every Layer-1 write/verify/integrate/bus path** (§1, D11).

---

# Part II — Layer 2: the unified operating doctrine (portable, all three providers)

These rules are provider-neutral. Where a rule names a *mechanism* (a git index, a cursor, a
subagent tool), bind it through the Part III capability map; the **principle** is identical
everywhere.

## II.A Truth and evidence

- **R-EVIDENCE — cite the command.** Any specific factual/inventory claim ("N files", "present in
  `<path>`", "X is unused") requires the producing command's output captured in the same change
  (paste cmd + output, or `verified via $ <cmd> → <result>`). A command scoped to one path proves
  only that path — re-run wider before a wider claim. If you cannot run the verifier, label the
  claim **unverified**. *Authority and verification travel together: never apply director-voice
  authority over an unverified claim.* (Origin: the 24-vs-1 inventory error, ADR-013.)
- **R-MEASURE — commit the instrument.** A number backing a GO/NO-GO verdict, gate threshold, or
  spec claim must come from a **committed script/command** persisted to (or citable from) a `logs/`
  artifact in the same change. Ad-hoc runtime numbers only when explicitly labeled
  `estimate`/`runtime-unreproducible`.
- **R-VERIFY-TIER — cap over-verification; pin unfixed defects.** (A) A doc-only note about an
  already-known defect converges at **two** independent confirmations; a 3rd pass needs a *stated
  different question*. (B) A confirmed defect you are **not** fixing this session must ship a
  `pytest.mark.xfail(strict=True, reason=...)` RED pin in the same session, or a `test-infeasible`
  label — so CI, not the next session, re-verifies.
- **ARCHITECTURE.md is the truth layer; process docs are the process layer.** When prose and code
  disagree, **code wins** — and you fix the stale claim in the same change that exposes it.
- **Verification before completion.** Never claim "done / fixed / passing" without running the
  verifying command and confirming output. Evidence precedes assertion, always.

## II.B Impact analysis and implementation safety

- **Impact analysis before editing.** Before modifying a function/class/method, grep the definition
  + callers, Read the call sites, grep imports for cross-file refs; report direct callers + risk
  before editing a high-fanout symbol. For renames/extracts/splits: grep every site, update all,
  re-grep to confirm none remain. Before committing, `git show --stat` / `git diff` to confirm
  scope matches intent.
- **R-BRIEF — a pattern reference is an implicit spec.** "Mirror pattern X at `file:line`" obligates
  you to verify X's **full shape** (signature, route, scope params, error handling, lock guards)
  before implementing. If the named helper doesn't exist or wording is ambiguous, **report the
  divergence before implementing**.
- **Rule #12 — grep-the-writes.** When a brief names a schema field / dict key / mutator / write-path
  as the target of new code, grep the production **write site** (not the type declaration) to prove
  the symbol is populated at runtime. Cite the grep. Type-declaration is not write-evidence.
- **Rule #13 — symmetric-endpoint audit.** When adding/modifying an endpoint that bypasses a fence,
  gates on a persistent flag, or touches shared state, audit **all** sibling endpoints on that
  fence/flag/state for checks the new one should mirror (and checks the existing ones may be
  missing); fold the fix or document the exemption.
- **R-PID — pid-scope endpoints.** A project-scoped resource endpoint must take `<pid>` explicitly;
  never scan a list-all to find a matching resource (IDs collide across projects).
- **Plan-vs-source divergence.** Where a plan/brief value matches the actual source, use the plan's
  value; where they differ, use the **actual** value and report the divergence — never silently
  follow a stale plan, never silently override it.

## II.C Agents and subagents (the portable model)

The term "subagent" means **a fresh-context worker the active session spawns to do one bounded unit
of work and return a compact report**. It exists to keep the main context small and to inject
independent signal. The principles below hold on every provider; the *spawn primitive* differs (Part
III).

- **What a subagent is for.** A subagent starts at ~0 context with a self-contained prompt, digests
  the heavy reading/writing, and returns a 500–2000 token report — paying a ~20× compression so the
  main context grows with *task count*, not work volume.
- **Subagent output is evidence, not authority.** The spawning session reads the actual diff/result;
  it does **not** trust the subagent's self-report. A subagent **cannot** by itself: issue a verdict
  (GO), advance a coordination cursor, send a binding coordination event, claim a lock, push, or
  spend money. Those require the authorized live session to perform the action.
- **impl ≠ verifier (the load-bearing guarantee).** No change reaches "verified" without a
  **non-author** reading the actual diff. Eligibility to verify is **non-authorship**, not title.
  A builder's "looks done" is never a GO. In Layer 1 this is enforced cross-provider; in any regime
  it is enforced as "a different worker than the author verifies."
- **The dispatch contract.** A subagent prompt carries only what it needs to act cold: the task +
  exact location + the *relevant rule IDs and template slice* (never inherited whole-doc doctrine) +
  verification commands + the report format + the env/​git-hygiene block. It inherits **no**
  coordination authority.
- **Reviewers are cold and independent.** A reviewer forms its verdict only from the diff/commit
  under review + the original spec; it must **not** cite or anchor on another reviewer's findings.
  Verify-before-asserting: confirm a symbol/file/line exists against real bytes before claiming a
  defect, else label it unverified.

## II.D Orchestration (scaling work across subagents)

- **R-ORCH — orchestrate, don't implement in main.** When a plan has **≥5 independent sub-tasks** or
  **≥800 LOC** of total change (or a user-referenced plan file), the main session holds the plan +
  task state + a short summary per task while fresh subagents do each task. A single change or
  tightly-coupled work stays in the main session.
- **Per-task loop:** implementer → **spec reviewer** (reads the diff vs the spec line-by-line) →
  **code-quality reviewer** → fix loop → done. After all tasks, a final cross-cutting review over
  the whole `BASE..HEAD` range.
- **Never two implementers in parallel on shared files** — sequential only (they would conflict).
  Parallel **reviewers** are fine.
- **Lane A/B/C delegation heuristic.** *Lane A* = do it in the main session (file already in context
  AND ≤5 LOC mechanical edit, a reviewer's clear 1–2 line fix). *Lane B* = a fresh implementer
  subagent (≥3 files or unread domain, structural change, design judgment). *Lane C* = a read-only
  search/survey subagent (open-ended "where is X / which files reference Y"). Decision tree: small
  mechanical edit in an understood file → A; open-ended multi-file search, no code change → C;
  everything else → B.
- **Commit discipline for reviewability.** Baseline commit first (commit foundational prep before
  dispatching, so each task diff is clean); **one commit per task** (no `--amend` across tasks);
  **fix commits are separate** from feature commits (preserve the audit trail of what a reviewer
  caught). Mark pre-existing/baseline failures `xfail` **early** so a new failure stands out.
- **Don't orchestrate** single-step tasks, tightly-coupled refactors, or interactive exploration.

## II.E Verification and verdicts (one vocabulary everywhere)

- **One verdict enum, three values:** `pass` | `issues` | `unable_to_verify`. Seat shorthand maps
  1:1 — **GO = pass**, **NITS = issues (all minor)**, **FAIL = issues (≥1 critical/important)**,
  **RE-DISPATCH/ESCALATE = unable_to_verify**.
- **`unable_to_verify` is orthogonal to severity and is NEVER a defect** — it is a property of the
  verification *run* (no interpreter, tests couldn't run, wrong SHA checked out). It must never
  become a tracked "defect" or inventory status.
- **NO-GO vs unable_to_verify discriminator:** NO-GO = the check ran and the code failed it.
  unable_to_verify = the check did not run to a conclusion. Never conflate them.
- **Reviewer evidence preamble (anti-ceremony keystone).** Every verification *runs and pastes* its
  commands + output + exit code: confirm the reviewed SHA is checked out, the tree is clean, read
  asserted files **from the commit**, run the mandated tests and paste the literal summary, and
  **the keystone** — re-run each named pin and confirm **a one-fact mutation flips it RED**
  (non-vacuity). *A pin that passes on reverted code is not evidence.* "Looks fine" is not evidence;
  the exit code is.
- **Conflict synthesis.** When two reviewers disagree on the same diff, resolve to the **more
  conservative** verdict (`issues` dominates `pass`; `unable_to_verify` dominates both). A genuine
  contradiction (one says compliant, one finds a critical defect) **escalates** — it never
  auto-merges to pass.
- **Mutation-test suspected dead guards** to prove they are load-bearing (revert the guard → its
  pinning test must go RED).

## II.F Coordination, authority, and side effects

- **Authority precedence:** **user direct instruction > git commits (durable record) > coordination
  events (bind the recipient) > cached state files (STATE.md) > default behavior.** Git is the
  tiebreaker — before acting on a shared task, check `git log`; the first commit to land wins. A
  coordination event obligates the recipient with the same weight as a user instruction.
- **Signal via durable artifacts, not chat.** Binding cross-session signals are files (a coordination
  event, a presence update), never a sentence in a private chat. Chat is a user courtesy, not a peer
  channel.
- **Anti-ceremony / no theater.** A status, route, handoff, receipt, or no-op report is valid **only**
  when it preserves transfer state, changes enforcement, or cites executable evidence. Green-looking
  prose is not protocol proof.
- **User-gated side effects.** Push, lock-claim side effects, paid-API spend, and pod/compute spend
  **always require explicit user consent** — no environment variable or role authorizes them.
- **Flag-before-burn.** Any script that spends clock-billed or per-call money gets a **non-author**
  review before its first execution (idempotency guard, spend-site enumeration, error propagation on
  every paid call, timeout on every blocking call).
- **Same-seat handoff first.** A fresh/transplanted named seat locates the newest
  `docs/HANDOFF-<concrete-seat>-*.md` from that same concrete role before ordinary orientation.

## II.G The four-seat governance rules (#7–#23, condensed)

These govern concurrent seats sharing one tree. Most are **portable principles**; the *mechanism*
(mailbox, per-seat index, locks) maps per provider (Part III).

| Rule | Principle |
|---|---|
| #7 Pre-commit re-verify | Immediately before a state-asserting commit, re-check `git log -5` + new coordination events vs your write-start; re-edit or abort on contradicting drift. |
| #8 Events bind the recipient | A coordination event obligates the receiver as strongly as a user instruction; surface unread count in the first turn at session start, then process. |
| #9 Independent reviewer | The verification pass is a *second opinion* built cold from `BASE..HEAD` + spec only; must not cite the author's reviewer. |
| #10 Joint-team mode | Within a pair, equals; in-lane act unilaterally, cross-cutting goes through a proposal cycle; persistent disagreement escalates after 2 cycles. |
| #11 Codification bias check | A proposed rule names its primary beneficiary; an asymmetric rule gives the other seat veto. |
| #12 Grep-the-writes | (II.B) prove the write site. |
| #13 Symmetric-endpoint audit | (II.B) audit sibling sites on the same fence/flag/state. |
| #15 Fix-on-received-findings | Either seat may close a finding the other surfaced; severity → disposition (CRITICAL→standalone fix, never silent drop). |
| #16 No-owner user direction | If user direction reaches both seats, the second to ship sends a convergence event. |
| #19 Live-presence-over-inferred-idle | Liveness = a fresh heartbeat artifact, not a chat guess; binding signals are artifacts. |
| #21 Verdict-ahead-of-report | If a peer is blocked on a billed resource, send the GO/NO-GO verdict first; the full report follows. |
| #22 Flag-before-burn | (II.F) non-author review before spending money. |
| #23 Lane ownership + **tiered co-sign** | Work in your lane; a cross-lane/cross-cutting change needs the other lane's sign-off. **Tier A** (the co-signer's verification *would* change which files the impl touches) = co-sign **before dispatch**; **Tier B** (it would not) = 48h awareness. Unsure → Tier A. |

**Disagreement protocol:** state it with project-grounded evidence; after 2 reply cycles, escalate to
the user — agents do not argue indefinitely. **Emergency gate (exactly four):** production/data
integrity, security-critical, active cost bleed, or a real external deadline — everything else uses
the normal cycle.

## II.H Failure-mode discipline (portable)

- **Contradiction triggers a targeted check.** When a tool, reviewer, or security warning contradicts
  something you know to be true, do **one** quick Read/grep before acting. Reviewer false-positives
  recur: a "missing requirement" already enforced upstream; a sequencing concern already satisfied by
  your dispatch order; a "symbol not found" because the reviewer grepped the wrong file; a security
  warning firing on an action the user/system explicitly mandated.
- **A reviewer only catches what its prompt tells it to look for.** When the change touches
  concurrency / thread-shared state, explicitly direct the reviewer to inspect lock discipline.

---

# Part III — Capability mapping (the heart of unification)

Each ENV_MECHANIC below is **one principle** with a per-provider binding. Adopt the principle; use
your provider's mechanism. Antigravity bindings have been explicitly established and confirmed.

| Capability (principle) | Claude (Claude Code) | Codex (CLI harness) | Antigravity ("agy") |
|---|---|---|---|
| **Spawn a bounded subagent** | `Agent` tool (`subagent_type`, `model`) | spawnable role agents `.codex/agents/*.toml` + Codex subagents | `invoke_subagent` tool |
| **Deterministic multi-agent orchestration** | `Workflow` tool (fan-out/pipeline) | sequential subagent dispatch per `R-ORCH` | concurrent execution via `invoke_subagent` array |
| **Structured/validated output from a worker** | `schema` on `Agent`/`Workflow`; reviewer `RESULT SCHEMA` json block | prompt-enforced report format + `apply_patch` | Markdown artifacts in `brain/<conversation-id>/` |
| **Load a domain skill before judging code** | `Skill` tool over `.claude/skills/` | `.agents/skills/` + role TOML references | reads `.agents/skills/*/SKILL.md` as markdown |
| **Session-start tripwire / smoke** | SessionStart hook → `ci_smoke.py` | `.codex/hooks/session-smoke.sh` (fail-open) | run `scripts/ci_smoke.py` manually |
| **Per-worker staging isolation on a shared tree** | per-seat `GIT_INDEX_FILE`; subagents prefix `env -u GIT_INDEX_FILE` | same `GIT_INDEX_FILE=<git-dir>/index-codex-$CODEX_SEAT`; `.codex/hooks/guard-git-index.sh` enforces | `env -u GIT_INDEX_FILE` or `Workspace: 'branch'` |
| **Durable coordination channel + read cursor** | mailbox `coordination/mailbox/sent/` + `seen/<seat>.txt` | same mailbox + `coordination/bin/{send-event,consume-events}` | N/A (holds no seat) |
| **Liveness signal separate from intent** | hook-written heartbeat + agent-written presence `.md` | `.codex/hooks/update-state.sh` heartbeat | N/A (holds no seat) |
| **Background long task without polling** | `run_in_background: true`; harness notifies | background command support | `schedule` and `manage_task` tools |
| **Ask the user vs decide** | `AskUserQuestion` (only for cross-cutting/policy/hard-to-reverse) | surface the choice in prose | `ask_question` interactive modal tool |
| **Cross-cutting edit lock** | `coordination/bin/claim-lock` (4 modules only) | same `claim-lock`/`release-lock` | N/A (holds no seat) |

**Invariant across the table:** the *authority rules never change with the mechanism.* A subagent has
no GO/cursor/lock/push/spend authority on any provider; side effects are user-gated on any provider;
impl ≠ verifier on any provider.

---

# Part IV — Per-provider entry points

- **Codex:** read [`CODEX-ADOPTION.md`](CODEX-ADOPTION.md). Codex already runs a full mirror of the
  Layer-2 doctrine (kernel `scripts/codex_protocol_model.py`, six `.codex/agents/*.toml` role agents,
  three hooks, the mailbox bus). Its adoption work is the Layer-1 threeway migration for `director`
  and `operator2`, plus adding target-state `coordinator2` as a real harness/orientation role during
  Slice 2.5 before any Codex session may claim that seat live.
- **Antigravity:** read [`ANTIGRAVITY-ADOPTION.md`](ANTIGRAVITY-ADOPTION.md). Antigravity holds **no
  Layer-1 seat**; it participates as a human-relayed strategic-reasoner (chief axis) and/or
  read-only observer, and adopts the full Layer-2 doctrine for any work an agy session performs.
- **Claude:** `CLAUDE.md` + `docs/protocol/claude/` are the existing mechanics. Claude occupies
  `director2`, `operator`, `coordinator`.

**Root integration:** `AGENTS.md` now names Antigravity and points to this `docs/protocol/threeway/`
package. Keep future changes synchronized with the root router instead of leaving adoption rules only
in these manuals.

---

*Provenance: distilled from `CLAUDE.md`, `AGENTS.md`, `docs/protocol/{claude,agents,codex}/`,
`docs/templates/claude/`, `.agents/skills/seat-*`, the `threeway/` package, and the cross-provider
spec, via an adversarially-verified extraction pass (workflow `wf_7dea0939-78c`, audit
`wf_34ae3dc6-731`). Rule provenance with codified SHAs is in `docs/PROTOCOL-RULES-LOG.md`.*
