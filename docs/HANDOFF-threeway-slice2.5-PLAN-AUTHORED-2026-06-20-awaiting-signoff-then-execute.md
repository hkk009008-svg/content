# HANDOFF — Slice 2.5: PLAN AUTHORED, awaiting sign-off → execution (2026-06-20)

**Read this first if you were prompted "continue Slice 2.5" or "execute Slice 2.5."** The PLANNING is
**DONE**. This session authored the Slice 2.5 design spec + TDD plan via `brainstorming → writing-plans`,
adversarially reviewed them, and opened **[PR #23](https://github.com/hkk009008-svg/content/pull/23)**.
Companion docs: the design spec + the plan (paths below); the stub
`docs/superpowers/plans/2026-06-19-cross-provider-seat-topology-slice2.5-legacy-bus-migration.md` (now
superseded in scope); the "author the plan" handoff `docs/HANDOFF-threeway-slice2.5-plan-2026-06-20-author-the-migration-plan.md`.

## TL;DR — what "continue Slice 2.5" means now

The plan exists. **NEXT = the user signs off on PR #23, THEN a SEPARATE session EXECUTES the 16 tasks**
(subagent-driven-development, Opus, one commit per task). Do **NOT** re-author the spec/plan, do **NOT**
re-plan, do **NOT** execute before sign-off. If the user says "execute," confirm the sign-off happened, then
follow the plan's Execution handoff.

## Exact state — trust git, not this prose

- Branch **`docs/threeway-slice2.5-plan`** (off `origin/main` `f0b81a61`), 2 commits → **PR #23** open vs `main`:
  - `2a29e448` — design spec `docs/superpowers/specs/2026-06-20-threeway-slice2.5-legacy-bus-migration-design.md` (rev 2)
  - `d11049fb` — TDD plan `docs/superpowers/plans/2026-06-20-cross-provider-seat-topology-slice2.5-legacy-bus-migration.md` (16 tasks, 4 chunks, 2328 lines)
  - (this handoff is a 3rd commit on the same branch.)
- Re-anchor on resume: `git fetch origin && git log --oneline origin/main -5`; `git merge-base --is-ancestor f0b81a61 origin/main`. The earlier threeway-adoption-docs refinement merged as **PR #22** (`f0b81a61`).
- **Next free ADR = ADR-034** (max present = 033 — re-grep `DECISIONS.md` before assigning).

## What this session produced (and how — so you don't re-derive it)

**Pipeline:** grounding workflow (5 Opus readers, `wf_c9162998-703`) → `superpowers:brainstorming` (3 decisions
user-approved) → design spec → **2 adversarial spec-review rounds** (`wf_f2e4a49a-0b4` found 2 blockers;
`wf_1d4b62be-070` confirmed closure) → `superpowers:writing-plans` → 4 parallel Opus chunk-drafters
(`wf_9509d81c-c78`) → **adversarial plan review** (`wf_90981186-a06`, 5 reviewers) → fixes folded in.

**Approved decisions (locked — do not re-litigate without the user):**
- **D1** — consolidate the **~12-copy** seat roster to the `protocol_mailbox.py` root; Python copies import it;
  4 shell whitelists hand-synced + a token-extraction guard test. (The stub said 6 sites; grounding found ~12.)
- **D2** — **in-memory shadow, single cutover write.** The projector never appends during shadow; the ref-bus
  is written exactly once, at cutover. Makes "no dual-write authority" *structural* (acceptance clause #6).
- **D3** — wire **coordinator** (send-only → receiver) **+ new coordinator2** fully; seed coordinator2's cursor
  at the bus head.
- **Carrier-event model** (resolved a spec-review blocker): legacy `kinds.txt` is **100% disjoint** from the
  governance `THREEWAY_KINDS`, so legacy events ride the existing **`event_sent`** kind — which is **NOT**
  load-bearing (`threeway/__init__.py:26-31`), so `gate.verify_and_reduce` skips it and `reducer.reduce()` never
  folds it. `subject_sha = sha256(source_filename)` + `brief_id="legacy-import"` make idempotency injective.

**Plan shape:** 3 phases / 4 chunks. **Chunk 1 (Phase A)** additive seat wiring (all live-safe). **Chunk 2
(Phase B)** read-only `legacy_projector` + `divergence` (zero bus writes). **Chunk 3 (Phase C)** cursor ISO→seq
backfill (byte-reversible manifest) + the single cutover (`preflight_bus_init` → 768 appends → 6 cursor
backfills → one authority-flip, teardown-on-failure). **Chunk 4** ADR-034 + `ARCHITECTURE.md §13A` doc-sync +
final gate. All 9 spec-§8 acceptance clauses map to mutation-proven (ADR-028 zero-ceremony) tests — confirmed by
the plan review's coverage matrix.

## What to do next (on user sign-off — execution session)

1. Re-anchor on git; re-read the plan + spec. **Re-grep EVERY file:line** — anchors are HEAD-`f0b81a61`/`2a29e448`
   snapshots and WILL have drifted.
2. Execute via `superpowers:subagent-driven-development` — fresh Opus implementer per task + two-stage review
   (spec-compliance → code-quality). One commit per task, explicit pathspec, `Co-Authored-By` trailer.
3. **Run execution when bus activity is QUIET** (it edits the live `coordination/` bus). Re-anchor on git refs
   before every action; `env -u GIT_INDEX_FILE` on every git-touching test; expect `git status`/`diff` to lie
   under peer activity — verify against `git show HEAD:<path>`.
4. The **Chunk-1 close gate runs the FULL `tests/unit/` suite** (not just `test_threeway_*`) — the existing
   send-only-doctrine tests are inverted in-lockstep by Tasks 3/4/5; a partial gate would miss regressions.
5. After Slice 2.5's gate is green (§11 boundary): plan **Slice 3** (`co_sign_satisfied` True for T2/T3 —
   `threeway/tier.py:32-43`).

## What NOT to do

- Do NOT execute before the user signs off on PR #23.
- Do NOT re-author/re-plan the spec or plan, and do NOT re-do Slice 2 (merged, gate green).
- Do NOT create a dual-write-authority window; do NOT big-bang the cutover (shadow → canary → single cutover).
- Do NOT reuse ADR-031/032/033 — your Slice 2.5 ADR is **034** (re-grep `DECISIONS.md`).
- Do NOT edit a prior ADR (append only); do NOT commit `package.json`/`package-lock.json`.

## Sharp edges surfaced this session (carry into execution)

- **Existing tests encode the OLD doctrine.** `coordinator`-send-only is pinned by `test_four_seat_coordination.py`,
  `test_mailbox_monitor.py` (`not exists coordinator.txt`), `test_seat_status.py`, `test_draft_handoff.py`, and
  `test_check_coordination.py` (`_check_coordinator_handoff_theater` iterates `ROLES`). Each must be **inverted in
  the same task** that changes the code — the plan does this; verify it during execution.
- **`seat_status.py` canonical copy is `.agents/skills/four-seat-protocol/scripts/seat_status.py`** (per
  `proof_bundle.py:12`), NOT `.claude/skills/…` (stale mirror). Different line numbers.
- **Idempotency injectivity rests on `source_filename` uniqueness** — it's in the carrier payload (so
  `payload_digest` differs) AND `subject_sha=sha256(filename)`. The clause-#5 set-bijection (non-empty floor) is
  the guard if any two `sent/*.md` filenames ever collide.
- **`preflight_bus_init(force=True)` short-circuits** (`gitcas.py:240-241`) — it's an ack gate, not the writer
  and not a guard. The fail-closed check is the `force=False` path.
- **`ci_smoke.py` §13A doc-anchor drift hard-fails only when `CI` is UNSET** (downgrades to a WARNING under CI).
- The carrier `Event(...)` needs `schema_version="threeway/1"` (required field, no default).

---
*Authored 2026-06-20. Slice 2.5 PLANNING complete → PR #23 (planning-only). The earlier threeway-adoption-docs
refinement shipped via PR #22 (`f0b81a61`). Execution is a separate, user-signed-off session.*
