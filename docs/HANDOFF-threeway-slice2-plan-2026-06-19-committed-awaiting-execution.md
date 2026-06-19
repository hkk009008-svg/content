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
- **Plan branch: `docs/threeway-slice2-plan` @ `817a68ca`** — one commit, the Slice 2 plan only
  (1110 lines). **NOT merged to `main`, NOT pushed.** On `main` the plan file does not exist yet —
  read it from the branch.
- **Plan file:** `docs/superpowers/plans/2026-06-19-cross-provider-seat-topology-slice2.md`
  (on the branch above).
- `package.json` / `package-lock.json`: the pre-existing unrelated `codex-chatgpt-control`
  working-tree change was **reverted**. **NEVER commit it.**
- `.venv/` lives only in the **main checkout**; a worktree needs a symlink (see Execution §3).

## Decisions — BOTH user-APPROVED (already baked into the plan)

- **D-A — sign `brief_version`** as a 13th `_signed_view` field (Chunk 1 Task 3). Closes a real
  post-sign authorization-redirect (the predicate reads `cand.brief_version` off the *unsigned*
  envelope at `predicate.py:74,:100,:143-144`). **Schema policy = NO MIGRATION, RESET** (no persistent
  threeway events exist: trust root has only `README.md`, no `refs/threeway/events`, Slice-1 stores
  are ephemeral). **Do NOT bump `schema_version`.**
- **D-B — legacy `coordination/` mailbox migration (§8.7/§8.8) DEFERRED** to a separately tracked
  **"Slice 2.5: legacy bus migration"** (scope + exact edit sites fixed in the plan's D-B section).
  Its plan doc is authored only after Slice 2's gate is green (§11 boundary rule). **Pair B in
  Slice 2 needs only new threeway keystore seats, not legacy-bus edits.**

## Four robustness requirements the user added — all folded in (verify in the plan before executing)

1. **Both** a deterministic forced-CAS-loss test (`test_concurrent_append_loses_no_event_and_re_signs`,
   via the `_before_cas` seam) **and** a genuine two-process race test
   (`test_genuine_two_process_race_no_loss`, `multiprocessing` spawn + module-level worker;
   thread-pool fallback documented). Task 9.
2. **Ambiguous-push idempotency** (effectively-once): `RefEventStore.append` computes
   `idempotency_key(ev)` once and scans for an existing match at the top of every loop iteration →
   returns the persisted event instead of double-appending (covers lost-ack / crash-after-CAS /
   timed-out retry). Tests `test_ambiguous_push_timed_out_retry_is_idempotent` +
   `test_crash_after_cas_then_retry_no_double_append` (uses an `_after_cas` seam). Task 8/9.
3. **No-migration schema-reset policy** (Task 3, see D-A above).
4. **Monotonic CAS cursor** (`advance_cursor` retry loop: refuse `seq <= current`, CAS with
   `expected_old`, re-read on a lost CAS so the higher value always wins). Task 10.

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
  TOP of each loop iteration.
- Genuine race test = `multiprocessing` spawn + a **module-level** worker (picklable); thread-pool is
  the documented fallback if the harness can't import the test module in a spawned child.
- Event ids are scoped by `candidate_id` (`id=f"{kind}-{sender}-{candidate_id}"`) — else Pair A/B
  overseer events collide on `events/<brief_id>/<id>.json` and overwrite each other.
- `build_candidate_events` gains `pair=PAIR_A` + `candidate_id="c1"` kwargs; defaults preserve all
  Slice-1 callers.

## What NOT to do

- Do NOT re-author the Slice 2 plan (committed + reviewed).
- Do NOT re-execute Slice 1.
- Do NOT commit `package.json` / `package-lock.json`.
- Do NOT bump `schema_version` (the no-migration reset policy is intentional).
- Do NOT do the legacy mailbox migration in Slice 2 (it is the separately tracked Slice 2.5).

## Subagent model = OPUS (standing user directive).

---
*Session 2026-06-19: planned Slice 2 end-to-end — understand workflow (6 agents) → authored the plan →
two review rounds (per-chunk + spec-fidelity + git-validated technical-correctness; a git-running
reviewer caught a real `build_tree_with` 0-byte-index bug, fixed) → folded the user's 4 robustness
requirements → committed on `docs/threeway-slice2-plan @ 817a68ca`. No implementation begun.*
