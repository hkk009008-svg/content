# Spec — Threeway scope-b, sub-project 2: real seat↔bus wiring

**Date:** 2026-06-24
**Status:** design approved (brainstorming); awaiting spec review + implementation plan.
**Scope:** the SECOND and final scope-b sub-project. Makes the interactive seats
(`director`/`director2`/`operator`/`operator2` + `coordinator`/`coordinator2`) **emit and consume
signed bus events directly**, replacing the human-driven `scripts/bootstrap_emit.py` shim that
sub-project 1 (ADR-056) provided. **Single-host, single-operator deployment** (all seats run as
Claude/Codex sessions on one machine, one repo, one bus remote `origin`, one keystore).

> Truth lives in the code. This spec mirrors `threeway/refstore.py`, `threeway/envelope.py`,
> `threeway/keys.py`, `threeway/loop.py`, `threeway/reducer.py`, `threeway/tier.py`, and
> `scripts/bootstrap_emit.py` as they stand at HEAD `4bbd97a0`. Two load-bearing facts were verified
> first-hand: `advance_cursor` is local-only by design (`refstore.py:261-290`) and the shim derives
> its signing key from a caller-supplied `signer` field (`bootstrap_emit.py:49-52`). Verify the rest
> against HEAD before implementing; fix drift in the same change.

## 1. Context

The threeway signed bus is **live as infrastructure** (Slice-2.5 cutover: 768+ carriers on
`refs/threeway/events` on origin, `THREEWAY_BUS_LIVE=true`, `.pub` trust root committed at
`coordination/threeway/keys/`). Sub-project 1 built the **mechanical-seat runtime** — `overseer_emit`
(overseer authority CLI), the merge-gate daemon (`run_merge_gate.py`, promotes `refs/threeway/test-main`),
the `overseer_plan` auto-decompose layer + rework breaker (ADR-057/058/059/060), and a **TEMPORARY**
human-driven shim `scripts/bootstrap_emit.py` for the interactive-seat facts.

A grounding pass (2026-06-24, 6 readers over the bus + mailbox substrate) established the seam and
corrected one framing imprecision in the roadmap:

- **The seam is `RefEventStore` + per-seat cursor + `load_private(seat)`.** The entire bus substrate
  (append/CAS/seq/sign in `refstore.py`; envelope + 14-field signed view + idempotency in `envelope.py`;
  `gate.verify_and_reduce`; the `reducer` authority model; `predicate`; per-seat keys) is built and
  hardened. **SP2 adds only callers — no substrate change.**
- **Correction:** interactive seats never emitted control-plane facts *through the mailbox*. The mailbox
  and the bus carry **different traffic classes** — the file mailbox carries free-form human coordination
  (the 25 kinds in `coordination/mailbox/kinds.txt`: `status`, `findings`, `verification-report`, `wrap`…),
  which the reducer never reads; the bus carries the 16 signed `LOAD_BEARING_KINDS` control-plane facts,
  emitted today by the shim. So SP2 does **not** "switch off the mailbox." It moves **control-plane-fact
  emission** from the shared shim to each real seat (signing with its own key), gives each seat a direct
  bus **read**, then retires the shim. The free-form mailbox (`send-event`/`consume-events`) is untouched.

**Single-host collapses three forks the code itself flags.** `advance_cursor` (`refstore.py:261-274`)
documents that remote/multi-host cursor publishing is "deferred Slice-3 work" and owner-only ref-ACL "is a
DEPLOYMENT ref-ACL concern — it cannot be enforced in a single local repo." On single-host: cursor-locality
is **correct by construction** (each clone owns its own cursor), OS-level key isolation is **not
enforceable** (one keystore, one operator) and is deferred, ref-ACL is deferred infra. SP2 is therefore
small and low-risk.

## 2. Goals / non-goals

**Goals**
- `scripts/consume_bus.py` — any of the 6 seats reads bus events addressed to it (`seq > cursor` and
  `recipient ∈ {seat, "all"}`) and advances its **local** cursor. The bus analog of `consume-events`.
- `scripts/seat_emit.py` — each emitting seat signs its **own** facts with its **own** key, with the
  seat↔kind **authority table enforced before construction**. Closes the shim's key-injection
  (`bootstrap_emit.py:50` extracts the seat from a caller-supplied `ev.signer` and loads *that* key).
- Prove a full **T1 brief→merge** runs through `seat_emit` + `consume_bus` + `overseer_emit` + the gate,
  with **no `bootstrap_emit`** (end-to-end walking skeleton).
- **Retire** `scripts/bootstrap_emit.py`.

**Non-goals (this sub-project — see §7 for routing)**
- No remote/multi-host cursor publishing (cursors stay local; single-host).
- No OS-level key isolation / per-seat process sandboxing (hardening track C5).
- No ref-ACL / append-only enforcement on the bus host (hardening track C3).
- No legacy-mailbox scalar-cursor fixes (`consume-events` regression check, `count_unread`,
  `check_coordination` skip) — a separate standalone follow-up; different traffic class.
- No autonomous seat daemons — emission is **seat-invoked** (the session runs the CLI), as seats already
  run `send-event`/`consume-events`/`claim-lock`.
- No overseer/CI automation (already shipped: `overseer_emit`, `overseer_plan`, `sign_ci_result`).
- No point-to-point addressing — threeway facts stay broadcast (`recipient="all"`).

## 3. Components

### 3.1 `scripts/consume_bus.py` — bus read + cursor advance (increment 2a, read-only)

CLI: `consume_bus <seat> [--kinds k1,k2] [--no-advance] [--repo-dir .] [--remote origin] [--bus-id prod]`
where `<seat> ∈ {director, director2, operator, operator2, coordinator, coordinator2}` (the 6 cursor
seats; `cursor_backfill.SEATS`).

Behavior:
1. `store = RefEventStore(repo_dir, remote=remote)`; `cursor = store.cursor_seq(seat)`.
2. Iterate `store.iter_events()` (syncs from remote first in remote mode). Record `tip = max(ev.seq)`
   seen in this snapshot. Materialize `unread = [ev for ev in events if ev.seq > cursor and
   ev.recipient in (seat, "all")]`, optionally filtered by `--kinds`.
3. Print a compact line per `unread` event — `seq`, `kind`, `from`, `candidate_id`/`brief_id`, short
   `subject_sha` — for the seat session to act on. (Raw read; signature verification is the gate's job,
   not the consume path — `iter_events()` is unverified by design.)
4. Unless `--no-advance`: `store.advance_cursor(seat, tip)` — advances the local "last-seq-scanned"
   watermark to the snapshot tip (monotonic; mirrors `consume-events` advancing to newest). A regression
   is structurally impossible (`advance_cursor` returns `False` for `seq <= cur`).

Notes:
- **`bus_id` filtering**: events whose `bus_id` differs are dropped by the gate, but `iter_events()` is
  raw; `consume_bus` filters display to `--bus-id` (default `prod`) so a seat never acts on a foreign bus.
- **Authoritative unread count.** `status.count_unread()` and the hook's `_unread_for()` deliberately
  return `0` for scalar-seq cursors (they comment "tracked on the ref-bus"). `consume_bus` is that
  ref-bus count surface (`seq > cursor_seq(seat)` addressed to the seat). Wiring `STATE.md` /
  `mailbox_monitor.py` to call it is **out of scope** (legacy-mailbox follow-up), but the surface exists.
- **Fold contract.** `advance_cursor` writes a blob ref (`refs/threeway/cursors/<seat>`) via a local CAS —
  it is **not** a mailbox `seen/*.txt` edit and does **not** create a git commit, so the
  `check_coordination` "standalone cursor-only commit" advisory does not apply.
- Clean rc1 (message, no traceback) on `CursorContentionExceeded` (rare on single-host).

### 3.2 `scripts/seat_emit.py` — per-seat signed emission (increment 2b; replaces the shim)

CLI: `seat_emit <seat> <fact> [fact-args] [--session $THREEWAY_SESSION] [--repo-dir .] [--remote origin] [--bus-id prod]`

**The injection hole closes here.** `<seat>` is an explicit positional arg. Before constructing anything,
`(seat, fact)` is checked against the authority table; a miss → **rc2** `"seat <seat> may not emit <fact>"`
with **nothing appended**. The key loaded is `keys.load_private(seat)` for **that** seat; the event's
`signer` is built `f"{seat}:{provider}:{session}"` with the seat **hard-bound** — never split back out of a
caller-supplied event (the `bootstrap_emit.py:50` defect).

**Authority table** (verified from `reducer.py` record-time/read-time authority + `loop.py` PairConfig):

| Seat | Emittable facts |
|---|---|
| `coordinator`, `coordinator2` | `candidate`, `release_requested`, `candidate_aborted` |
| `operator`, `operator2` | `attestation` (`--phase preliminary\|release`), `co_sign`, `re_verify` |
| `director`, `director2` | *(none — builders write code, not bus facts)* → rc2 |
| `overseer`, `ci`, `merge-gate` | *(not interactive seats)* → rc2 (use `overseer_emit` / `sign_ci_result` / the gate) |

- **`provider`** derives from `loop.PairConfig` (`coordinator`→`claude`, `coordinator2`→`codex`,
  `operator`→`claude`, `operator2`→`codex`). Mismatching it does not affect authority (the provider tail
  is unsigned) but is kept consistent for auditability.
- **`session`** from `--session` / `$THREEWAY_SESSION`, default `"s1"` (preserves current shim behavior).
  It is the **unsigned** signer tail — not in the 14-field signed view (`envelope.py`), ignored by the
  gate's `_seat_of()` — so it is audit-only, never authority.
- **Event shapes reuse `loop.build_candidate_events` + pick** (and the `_abort_event` shape for
  `candidate_aborted`) so emitted events are byte-compatible with what `gate.verify_and_reduce` already
  accepts — a wrong payload key or envelope/payload misplacement makes the predicate silently drop/reject:
  - `candidate`, `release_requested`, `attestation` take `--candidate-id --pair --staging-base --branch`
    (+ `--phase` for `attestation`); the integration_sha is recomputed deterministically (the existing
    `_candidate_set` path). `attestation` binds `subject_sha = branch_sha` (preliminary) /
    `integration_sha` (release).
  - `candidate_aborted` takes only `--candidate-id` (+ `--pair --brief-id --brief-version`) and **carries
    `candidate_id` in payload** — the idempotency-distinctness requirement, because `candidate_id` is NOT
    in the idempotency fingerprint (`envelope.py:105`; an empty-payload abort would dedup across
    candidates). ADR-059/060.
  - `co_sign`, `re_verify` (**T2/T3 only**): wired here but exercised by a tier test, not the T1 skeleton.
    `co_sign` is emitted by the **mirror** pair's `primary_verifier` against the cross-pair candidate
    (`--candidate-id <other-pair>:…`, verdict GO @ integration_sha). `re_verify` is emitted by the
    candidate pair's **own** `primary_verifier` and must **echo the overseer's fresh challenge nonce** —
    `seat_emit` reads `re_verify_challenge` for the candidate from bus state (`verify_and_reduce` →
    `state.re_verify_challenge(candidate_id)`) and copies `payload["nonce"]` into the echo (ADR-043).
- **Boundary (explicit).** `seat_emit`'s guarantee is **authority-table enforcement**, *not* OS-level key
  isolation — on single-host with one keystore it *can* technically load any key; its job is to refuse
  out-of-authority `(seat, fact)` pairs and to be the seam where real per-seat key isolation attaches when
  the hardening track (C5) lands. **The gate remains the actual security boundary** (verifies signatures
  vs the committed `.pub`, drops out-of-authority / wrong-bus / bad-profile events). `seat_emit` is
  correctness + ergonomics + the future-isolation seam, not the trust root.
- **Error handling** mirrors the shim's clean exits: `FileNotFoundError` (missing key),
  `AppendContentionExceeded`, `ValueError` (bad ref / non-clean merge / bad pick),
  `subprocess.CalledProcessError` (git) → rc1, message, no traceback. Authority-table miss → rc2.

### 3.3 End-to-end walking skeleton (increment 2c)

A test (extending the SP1 walking-skeleton, `tests/` — ADR-056 `69e65d2c`) drives a full **T1
brief→merge using only `overseer_emit` + `seat_emit` + `consume_bus` + the gate — no `bootstrap_emit`**,
each CLI invoked as a **subprocess** (the way they actually run), against a temp bus + temp repo:
overseer emits `brief`/`assignment`/`cycle_go`; `coordinator` emits `candidate`; `operator` emits
preliminary + release `attestation`; CI/`overseer` provide `ci_result`/`release_order`; `coordinator`
emits `release_requested`; the gate (`run_gate`/`poll_once`) merges to `refs/threeway/test-main` and emits
`merge_completed`; each seat's `consume_bus` shows the expected events and advances its cursor. This is the
**proof that `seat_emit` ≡ `bootstrap_emit` behaviorally** — the precondition for retirement.

### 3.4 `bootstrap_emit.py` retirement (increment 2d)

Once 2c is green: `git rm scripts/bootstrap_emit.py`; repoint the bare-subprocess pin that covers it
(`tests/…activation_scripts…`, ADR-055/056 `f5aa1763` / `c02b8049`) to `consume_bus` + `seat_emit`;
update `ARCHITECTURE.md` + `DECISIONS.md` (new ADR marking the shim retired) + the SP1 spec's
"Deferred → sub-project 2" note; grep-confirm **no remaining importers/callers**. The `candidate_aborted`
path is **preserved** (it now lives in `seat_emit`), not lost. Single-operator ⇒ land-then-remove
sequencing; there is no concurrent-emit race window.

## 4. Data flow (one T1 candidate, happy path, seat_emit-only)

1. Operator (relaying chief decisions) → `overseer_emit brief` / `assignment` / `cycle_go` → bus.
2. `coordinator` seat session → `seat_emit coordinator candidate …` → bus.
3. `operator` seat session → `seat_emit operator attestation --phase preliminary` (@ branch_sha) and
   `--phase release` (@ integration_sha) → bus. (The operator independently verifies before emitting GO.)
4. CI (GitHub Actions, `workflow_dispatch`) → `sign_ci_result` @ integration_sha → bus.
5. `coordinator` → `seat_emit coordinator release_requested …` → bus.
6. Operator → `overseer_emit release_order` @ integration_sha → bus.
7. Merge-gate daemon polls → `run_gate` → `verify_and_reduce` → predicate → recompute trusted merge →
   exact-SHA CAS to `refs/threeway/test-main` → emit `merge_completed`.
8. Any seat → `consume_bus <seat>` at any point → sees events addressed to it, advances its cursor.

## 5. Error handling

- `seat_emit` validates `(seat, fact)` authority and per-fact args **before** signing; loads only the
  named seat's key; fails loud (rc1/rc2, no traceback).
- Append contention is handled by `RefEventStore`'s existing retry; surface `AppendContentionExceeded`
  with a clear message (single-host: rare).
- `consume_bus` never mutates events; the only write is the monotonic cursor CAS, which cannot regress.
- The merge-gate path is unchanged (`run_gate` is TOTAL post-CAS, ADR-040).

## 6. Testing (campaign TDD discipline — RED→GREEN, non-vacuous)

- **`consume_bus`:** an event addressed to the seat with `seq > cursor` is shown and the cursor advances
  to tip. Mutations: break the addressee filter → a not-addressed event leaks (RED); break the advance →
  cursor stuck (RED). `--no-advance` leaves the cursor. Cursor at tip → no unread, monotonic no-op.
- **`seat_emit`:** `seat_emit operator attestation …` produces an event that **verifies vs `operator.pub`**
  and folds into `EffectiveState` as the operator's attestation. Mutations: emit with the **wrong seat
  key** → the gate **drops** it (RED — attestation absent); **authority-table bypass**:
  `seat_emit director attestation` would append a forgeable-seat event (RED) vs the rc2 baseline.
  `candidate_aborted` carries `candidate_id` (idempotency distinctness; emit two aborts for two
  candidates → two distinct events, not one deduped — the ADR-059 trap).
- **E2E (2c):** the full T1 cycle merges via `seat_emit`-only; drop the release attestation → gate
  `PENDING`, not `COMPLETED`.
- **Bare-subprocess pin:** `consume_bus` + `seat_emit` run clean as subprocesses (sys.path self-bootstrap,
  ADR-055), mirroring the existing pin that covers `overseer_emit` / `bootstrap_emit` (`f5aa1763`).
- **Gates:** `check_no_ceremony` clean; `ci_smoke` OK; full threeway suite green; spec drift fixed
  in-change. **Each increment's commit gets an independent adversarial Lane-V** (these emit/scan
  load-bearing facts) before its cross-cutting effects are trusted.

## 7. Scope boundaries

**In:** §3 components (2a–2d) + §6 tests + this spec's §8 carried invariants.

**Deferred → hardening track (gates production sign-off; roadmap C-items):**
- Remote/multi-host cursor publishing (`advance_cursor` push-to-remote) — only meaningful multi-host.
- OS-level per-seat key isolation / process sandboxing so a seat process physically cannot read a peer's
  `.ed25519` (C5; today one keystore, one operator).
- Ref-ACL / append-only enforcement on the bus host, incl. per-seat cursor-ref ownership (C3).

**Deferred → separate standalone follow-up (different traffic class — the free-form mailbox):**
- `consume-events` scalar-seq regression check (string-compares dash-normalized ISO; misbehaves on the
  now-live scalar cursors), `status.count_unread()` / `_unread_for()` returning `0` for scalar cursors,
  and `check_coordination._check_cursors()` skipping future/orphan checks for scalar cursors. SP2's
  `consume_bus` provides the authoritative **bus** unread surface; wiring the mailbox tools to it is the
  follow-up's job.

## 8. Carried decisions / invariants (verified at HEAD `4bbd97a0`)

- **Cursor locality is correct, not a gap (verified `refstore.py:261-290`).** `advance_cursor` writes the
  cursor blob via the **local** `cas_create_or_update_ref`, never `push_cas`; the `_sync()` + in-range
  validation still run against the **authoritative** event head, so a cursor can never advance past events
  that exist on the authority. Single-host ⇒ each clone is authoritative for its own cursor.
- **Seat identity is key-bound; the signer tail is unsigned (verified `bootstrap_emit.py:49-52`,
  `envelope.py` 14-field view).** The gate keys on `signer.split(":",1)[0]` for `<seat>.pub` lookup; the
  `provider:session` tail is outside the signed set and MUST NOT be trusted for authority. `seat_emit`
  therefore hard-binds the seat (positional arg → `load_private(seat)`), not derive it from event content.
- **`candidate_id` is signed but NOT in the idempotency fingerprint (`envelope.py:84` vs `:105`).** Any
  per-candidate fact of the same `(sender, kind, subject, payload)` shape must carry `candidate_id` in
  payload or `RefEventStore` dedups the second one. `candidate_aborted` already does; `seat_emit` preserves
  it.
- **Threeway facts are broadcast (`recipient="all"`); the reducer/gate are recipient-blind.** `consume_bus`
  filters `recipient ∈ {seat, "all"}` for the seat's inbox view only; it introduces no point-to-point
  semantics.
- **`seat_emit` is not the trust root.** The gate (`verify_and_reduce` + `run_gate`) is the security
  boundary; `seat_emit` enforcement is correctness + the future-isolation seam.

## 9. Acceptance criteria

- `consume_bus <seat>` shows exactly the events addressed to `<seat>` with `seq > cursor`, advances the
  local cursor to tip (or leaves it under `--no-advance`); regression and addressee-leak mutation pins RED.
- `seat_emit <seat> <fact>` emits a fact that round-trips through `verify_and_reduce` as
  authority-correct and verifies against `<seat>.pub`; wrong-key and authority-bypass mutation pins RED;
  `(seat, fact)` authority miss → rc2, nothing appended.
- The end-to-end walking-skeleton drives a full T1 brief→merge through `seat_emit` + `consume_bus` +
  `overseer_emit` + the gate with **no `bootstrap_emit`**, and passes.
- `bootstrap_emit.py` is removed, the bare-subprocess pin repointed, docs synced, no importers remain.
- `ci_smoke` + `check_no_ceremony` clean; full threeway suite green; spec drift fixed in-change.
