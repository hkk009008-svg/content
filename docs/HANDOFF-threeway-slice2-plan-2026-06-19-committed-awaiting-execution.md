# HANDOFF — Cross-Provider Seat Topology, Slice 2: PLAN COMMITTED, awaiting GO to execute (2026-06-19)

**Read this first if you are picking up the cross-provider seat-topology work and were prompted
"continue task."** Companion docs: spec `docs/superpowers/specs/2026-06-19-cross-provider-seat-topology-design.md`
(rev 5); Slice-1 handoff `docs/HANDOFF-threeway-slice1-2026-06-19-executed-merged-pushed.md`;
ADR-030 (Slice 1) in `DECISIONS.md`.

## TL;DR — what "continue task" means now

Slice 1 is **done, merged, pushed** (`origin/main`). Slice 2 has a **complete, multi-agent-reviewed
implementation plan that is committed on its own branch** — it has NOT been implemented. **"Continue
task" = EXECUTE the Slice 2 plan** via `superpowers:subagent-driven-development` (Opus implementers),
in a fresh worktree off the plan branch. Do **not** re-plan, do **not** re-execute Slice 1.

## Exact state (verify with `git log -1` + `git branch` — trust git, not this prose)

- **`main`** == `origin/main` @ `04977b2d` (Slice 1). Plus this handoff commit (local, unpushed).
- **Plan branch: `docs/threeway-slice2-plan` @ `e7920e8f`** — two commits (`817a68ca` original plan +
  `e7920e8f` audit revision). The Slice 2 plan is now **1365 lines**, REVISED per an external audit
  (3 blockers + 5 hardening issues) and re-reviewed (4 git/python-running agents; Tasks 8/9 approved,
  Tasks 3/10 blockers fixed + verified). **NOT merged to `main`, NOT pushed.** On `main` the plan files
  do not exist — read them from the branch.
- **Plan files (on the branch):** `docs/superpowers/plans/2026-06-19-cross-provider-seat-topology-slice2.md`
  + the deferral stub `…-slice2.5-legacy-bus-migration.md`.
- `package.json` / `package-lock.json`: the pre-existing unrelated `codex-chatgpt-control`
  working-tree change was **reverted**. **NEVER commit it.**
- `.venv/` lives only in the **main checkout**; a worktree needs a symlink (see Execution §3).

## Decisions — BOTH user-APPROVED (already baked into the plan)

- **D-A — sign `brief_version`** as a signed `_signed_view` field (Chunk 1 Task 3). Closes a real
  post-sign authorization-redirect (the predicate reads `cand.brief_version` off the *unsigned*
  envelope at `predicate.py:74,:100,:143-144`). **Schema policy (REVISED per audit Blocker 3):** add a
  signed **`signature_version = "threeway-sign/2"`** discriminator (NOT a `schema_version` bump — lower
  blast radius) + a **fail-closed, NON-DESTRUCTIVE `preflight_bus_init`** (checks local *and* remote
  `refs/threeway/*`, aborts on any prior state, never deletes). Final signed set = 14 fields.
- **D-B — legacy `coordination/` mailbox migration (§8.7/§8.8) DEFERRED** to a separately tracked
  **"Slice 2.5: legacy bus migration"** (scope + exact edit sites fixed in the plan's D-B section).
  Its plan doc is authored only after Slice 2's gate is green (§11 boundary rule). **Pair B in
  Slice 2 needs only new threeway keystore seats, not legacy-bus edits.**

## Audit-hardened behaviors — all folded in + re-reviewed (verify in the plan before executing)

The plan was revised against an external audit. Key design moves the implementer must honor:
1. **`RefEventStore` is dual-mode:** authoritative **remote push-CAS** (spec §8 — `git push
   --force-with-lease` to a bare bus; fetch + re-seq + re-sign on rejection) for the genuine
   concurrency tests, and **local update-ref CAS** for co-located/gate use.
2. **Genuine two-process race is the §11 gate** (`test_genuine_two_process_race_no_loss`): two real
   `Process`es over a bare remote + a start `Barrier` + **`assert total_retries >= 1`** (proves
   overlap) + exact-once-by-identity + **every signature verified**. A thread test is NOT a gate
   substitute; spawn-unavailable ⇒ gate UNMET.
3. **Idempotency that VERIFIES, not just key-matches (Blocker 1):** `append` recomputes the key from
   stored fields, **verifies the candidate's signature** against the appender's own derived pubkey
   (`keys.public_hex(priv)` — add it), compares an actor-scoped **`_request_fingerprint`**, returns on
   match / raises **`IdempotencyKeyReused`** on key-collision-different-request. Genuine ambiguous push
   recovery via a **fresh clone** (`test_ambiguous_remote_push_recovers_via_fresh_clone`).
4. **Bounded retries:** `max_attempts` + jitter + typed `AppendContentionExceeded` /
   `CursorContentionExceeded`; injectable `sleeper` (tests pass `lambda _: None`).
5. **Validated monotonic-CAS cursor:** reject negative / beyond-head / no-index-entry; malformed blob
   → `CursorCorruptionError`; owner-only is a deployment ref-ACL (test-infeasible locally).

## Plan structure (5 chunks, 19 TDD tasks)

- **Chunk 1 (T1–4):** the 3 carried fail-closed findings (F1 `_within_allowed` path-boundary;
  F2 nonexistent-SHA → REJECTED keeping `run_gate` total; F3 sign `brief_version`) + spec
  reconciliation (`merge_completed` enum, 13-field signed set).
- **Chunk 2 (T5–7):** gitcas object-store plumbing — `write_blob`/`read_blob`/`read_blob_at`/
  `list_index_seqs`/`build_tree_with`/`tree_of`/`commit_on`/`cas_create_or_update_ref`.
- **Chunk 3 (T8–11):** `RefEventStore` (one commit per event on `refs/threeway/events` + `index/<seq>`,
  append-CAS loop with re-seq/re-sign + idempotency), the 2-process race, monotonic-CAS cursor refs.
- **Chunk 4 (T12–16):** pair-parametrized `build_candidate_events` (+ `pair=`/`candidate_id=` kwargs,
  candidate-scoped event ids), Pair-B keys, serial merge-queue re-stage-the-loser, abort-on-conflict.
- **Chunk 5 (T17–19):** Slice 2 adversarial DoD suite (mutation-proven non-vacuous), ADR-031,
  the first `ARCHITECTURE.md` threeway section, final whole-suite + smoke gate.

## How to execute (the "continue task" procedure)

1. `git log -1` and `git branch` — confirm `docs/threeway-slice2-plan @ 817a68ca` exists.
2. Read the plan: `git show docs/threeway-slice2-plan:docs/superpowers/plans/2026-06-19-cross-provider-seat-topology-slice2.md`
   (or check out the branch).
3. Fresh worktree off the plan branch (so the plan + base are present):
   `git worktree add .worktrees/threeway-slice2 docs/threeway-slice2-plan`
   then symlink the venv: `ln -s /Users/hyungkoookkim/Content/.venv .worktrees/threeway-slice2/.venv`
   (`.worktrees/` is gitignored).
4. Run `superpowers:subagent-driven-development`: one **OPUS** implementer per task + a spec-compliance
   reviewer + a code-quality reviewer per task; **sequential** (never two implementers on a shared file —
   Chunk 1 T1/T2 both touch `predicate.py`/`gate.py`; sequential chunks otherwise).
5. **Test command (mandatory):** `env -u GIT_INDEX_FILE .venv/bin/python -m pytest <path> -q`.
   Smoke: `.venv/bin/python scripts/ci_smoke.py`. No-ceremony: `.venv/bin/python scripts/check_no_ceremony.py`.
6. Commits: explicit pathspec, `Co-Authored-By` trailer, never bare `git commit`, NEVER commit
   `package.json`/`package-lock.json`.
7. After all chunks + final review green → the §11 Slice 2 gate is met. **Merge decision (plan branch +
   the Slice-2 implementation → `main`) is the user's.** Then Slice 2.5 / Slice 3 may be planned.

## Execution sharp edges — already RESOLVED in the plan (do not re-derive)

- `build_tree_with` uses `tempfile.mkstemp` + immediate `os.remove` (NOT `NamedTemporaryFile`) — git
  rejects a pre-existing **0-byte** `GIT_INDEX_FILE` (`index file smaller than expected`). Empirically
  verified by a git-running reviewer.
- `gitcas.tree_of` is required because `gitcas.rev_parse` hardcodes a `^{commit}` peel and cannot
  resolve `^{tree}` (it would double-peel to `^{tree}^{commit}` → None → silently drop all prior events).
- Cursor refs CAN point directly at a blob (git allows it); a cursor = a seq blob, advanced by
  monotonic CAS via `rev_parse_any` (a `rev-parse --verify <ref>` with no peel).
- `append` re-signs on EVERY CAS retry (`seq` is a signed field); the idempotency scan must sit at the
  TOP of each loop iteration AND fetch authoritative state first (remote mode).
- Genuine race test = `multiprocessing` **spawn** + a **module-level** worker (picklable) + a
  `ctx.Barrier`/`ctx.Queue` passed as `Process` args (works under spawn; a `Pool` cannot pickle a
  Barrier — use explicit `Process`).
- **Naming trap (audit-caught):** the new signed field `signature_version` contains the substring
  `signature`, which trips the existing `assert b"signature" not in sb` at `test_threeway_envelope.py:53`
  → tighten it to `assert b'"signature"' not in sb` (quoted JSON key). One-line fix, in Task 3.
- **Remote push-CAS:** create form = `git push <remote> <commit>:<ref>` (no force, create-only);
  update form = `git push --force-with-lease=<ref>:<expected_old> …` (explicit expected-old). `preflight`
  must check the **remote** (`git ls-remote`) too — a fresh clone's local `for-each-ref` misses
  remote-only state (empirically confirmed).
- **Cursor head-validation** (`seq` must have an `index/<seq>` entry) means cursor tests must `append`
  events first; advancing on an empty bus now (correctly) raises `ValueError`.
- Event ids are scoped by `candidate_id` (`id=f"{kind}-{sender}-{candidate_id}"`) — else Pair A/B
  overseer events collide on `events/<brief_id>/<id>.json` and overwrite each other.
- `build_candidate_events` gains `pair=PAIR_A` + `candidate_id="c1"` kwargs; defaults preserve all
  Slice-1 callers.

## What NOT to do

- Do NOT re-author the Slice 2 plan (committed + reviewed).
- Do NOT re-execute Slice 1.
- Do NOT commit `package.json` / `package-lock.json`.
- Do NOT bump `schema_version`; the discriminator is the new `signature_version` field (lower blast
  radius). Do NOT make `preflight_bus_init` destructive — it must abort, never delete.
- Do NOT do the legacy mailbox migration in Slice 2 (it is the separately tracked Slice 2.5).

## Subagent model = OPUS (standing user directive).

---
*Session 2026-06-19: planned Slice 2 end-to-end — understand workflow (6 agents) → authored the plan →
two review rounds (per-chunk + spec-fidelity + git-validated technical-correctness; a git-running
reviewer caught a real `build_tree_with` 0-byte-index bug, fixed) → folded the user's 4 robustness
requirements → committed on `docs/threeway-slice2-plan @ 817a68ca`. No implementation begun.*
