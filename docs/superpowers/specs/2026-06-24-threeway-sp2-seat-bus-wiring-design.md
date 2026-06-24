# Spec — Threeway scope-b, sub-project 2: real seat↔bus wiring (T1 shim-equivalent)

**Date:** 2026-06-24
**Status:** design approved (brainstorming) + 5-iteration adversarial spec review converged (factual lens
approved; no blockers). Scope refined post-review to T1-shim-equivalence (T2/T3 emission deferred, §7).
Awaiting user spec review → implementation plan.
**Scope:** the SECOND and final scope-b sub-project. Makes the interactive seats
(`director`/`director2`/`operator`/`operator2` + `coordinator`/`coordinator2`) **emit and consume signed
bus events directly**, replacing the human-driven `scripts/bootstrap_emit.py` shim (ADR-056). `seat_emit`
covers exactly the shim's facts (the **T1** control-plane facts); `consume_bus` gives each seat a direct bus
read. **Single-host, single-operator deployment** (all seats run as Claude/Codex sessions on one machine,
one repo, one bus remote `origin`, one keystore).

> Truth lives in the code. This spec mirrors `threeway/refstore.py`, `threeway/envelope.py`,
> `threeway/keys.py`, `threeway/loop.py`, `threeway/reducer.py`, `threeway/predicate.py`, and
> `scripts/{bootstrap_emit.py,run_merge_gate.py}` as they stand at HEAD `4bbd97a0`. Load-bearing facts
> verified first-hand: `advance_cursor` is local-only (`refstore.py:261-290`); the shim derives its signing
> key from a caller-supplied `signer` (`bootstrap_emit.py:49-52`); `predicate.py` never reads
> `release_requested` (its only consumer is `run_merge_gate.py:28,42,47`); `PairConfig` has
> `coordinator_provider`/`verifier_provider`, no `operator_provider` (`loop.py:33-51`); `is_aborted` resolves
> abort authority at read time (`reducer.py:95-119`). Verify the rest against HEAD before implementing; fix
> drift in the same change.

## 1. Context

The threeway signed bus is **live as infrastructure** (Slice-2.5 cutover: 768+ carriers on
`refs/threeway/events` on origin, `THREEWAY_BUS_LIVE=true`, `.pub` trust root at
`coordination/threeway/keys/`). Sub-project 1 built the **mechanical-seat runtime** — `overseer_emit`, the
merge-gate daemon (`run_merge_gate.py`, promotes `refs/threeway/test-main`), `overseer_plan`
(ADR-057/058/059/060), and the **TEMPORARY** human-driven shim `scripts/bootstrap_emit.py` for the
interactive-seat facts.

A 2026-06-24 grounding pass established the seam and corrected a roadmap imprecision:

- **The seam is `RefEventStore` + per-seat cursor + `load_private(seat)`.** The entire bus substrate
  (append/CAS/seq/sign in `refstore.py`; envelope + 14-field signed view + idempotency in `envelope.py`;
  `gate.verify_and_reduce`; the `reducer` authority model; `predicate`; per-seat keys) is built and
  hardened. **SP2 adds only callers — no substrate change.**
- **Correction:** interactive seats never emitted control-plane facts *through the mailbox*. The file
  mailbox carries free-form human coordination (the 25 kinds in `coordination/mailbox/kinds.txt`); the bus
  carries the 17 signed `LOAD_BEARING_KINDS` control-plane facts, emitted today by the shim. So SP2 does
  **not** switch off the mailbox: it moves control-plane-fact **emission** from the shared shim to each real
  seat (signing with its own key), gives each seat a direct bus **read**, then retires the shim. The
  free-form mailbox (`send-event`/`consume-events`) is untouched.

**Single-host collapses three forks the code itself flags.** `advance_cursor` (`refstore.py:261-274`)
documents that remote/multi-host cursor publishing is "deferred Slice-3 work" and owner-only ref-ACL "is a
DEPLOYMENT ref-ACL concern — it cannot be enforced in a single local repo." On single-host: cursor-locality
is **correct by construction**, OS-level key isolation is **not enforceable** (one keystore) and is
deferred, ref-ACL is deferred infra. SP2 is therefore small and low-risk.

**Scope is the shim's facts only.** The shim emits the **T1** facts: `candidate`, `attestation`
(preliminary/release), `release_requested`, `candidate_aborted`. It does NOT emit `attestation_revoked`,
`co_sign`, or `re_verify` — those are NEW capability (T2/T3), nothing emits them today, and bundling them
would gate shim retirement on unrelated new features. They are **deferred to a follow-on spec** (§7).

## 2. Goals / non-goals

**Goals**
- `scripts/consume_bus.py` — any of the 6 seats reads bus events addressed to it (`seq > cursor` and
  `recipient ∈ {seat, "all"}`, on its `--bus-id`) and advances its **local** cursor. The bus analog of
  `consume-events`.
- `scripts/seat_emit.py` — each emitting seat signs its **own** shim-equivalent (T1) fact with its **own**
  key, with the seat↔kind **authority table enforced before construction**. Closes the shim's key-injection
  (`bootstrap_emit.py:50` extracts the seat from a caller-supplied `ev.signer` and loads *that* key).
- Prove a full **T1 brief→merge** through `seat_emit` + `consume_bus` + `overseer_emit` + the gate with
  **no `bootstrap_emit`** (E2E walking skeleton), by modifying the existing E2E test in place.
- **Retire** `scripts/bootstrap_emit.py` (and its now-orphaned test).

**Non-goals (this sub-project — see §7 for routing)**
- **T2/T3 emission** — `attestation_revoked`, `co_sign`, `re_verify` (new capability, not shim-replacement;
  the most complex paths — `re_verify` needs a registry-verified bus read + nonce echo). Deferred to a
  follow-on.
- Remote/multi-host cursor publishing (cursors stay local; single-host).
- OS-level per-seat key isolation / process sandboxing (hardening track C5).
- Ref-ACL / append-only enforcement on the bus host (hardening track C3).
- Legacy-mailbox scalar-cursor fixes (`consume-events` regression check, `count_unread`,
  `check_coordination`) — a separate follow-up; different traffic class.
- Autonomous seat daemons — emission is **seat-invoked** (the session runs the CLI), as seats already run
  `send-event`/`consume-events`/`claim-lock`.
- Overseer/CI automation (already shipped). Point-to-point addressing (facts stay broadcast).

## 3. Components

### 3.1 `scripts/consume_bus.py` — bus read + cursor advance (increment 2a, read-only)

CLI: `consume_bus <seat> [--kinds k1,k2] [--no-advance] [--repo-dir .] [--remote origin] [--bus-id prod]`
where `<seat> ∈ {director, director2, operator, operator2, coordinator, coordinator2}` (the 6 cursor seats;
`cursor_backfill.SEATS`).

Behavior:
1. **Normalize `--remote`:** `remote = (args.remote or None)` — an empty string becomes `None` (local
   mode). `RefEventStore` checks `self._remote is not None` (not truthiness), so a bare `""` would otherwise
   trigger a fetch against an empty remote name (the shim does this normalization at `bootstrap_emit.py:51`).
   Build `store = RefEventStore(repo_dir, remote=remote)`; `cursor = store.cursor_seq(seat)`.
2. **Collect once:** `events = list(store.iter_events())` — materialize into a list in a SINGLE pass.
   `iter_events()` is a generator that re-fetches from the remote on each call (`refstore.py:226-228`);
   iterating it twice would issue two fetches and risk a tip/unread mismatch. Derive both `tip` and `unread`
   from this one list.
3. **Tip = full-snapshot watermark:** `tip = max((ev.seq for ev in events), default=0)`. The `default=0`
   form is the canonical empty-bus-safe shape (no `if events:` branch). `tip` is the seq the seat has now
   **scanned the events-ref through**; `bus_id` and addressee are *display* filters and do NOT narrow the
   watermark (advancing to the full tip is safe because every on-bus event addressed to the seat with
   `seq ≤ tip` is displayed in this same pass — §8).
4. **Display set:** `shown = [ev for ev in events if ev.seq > cursor and ev.bus_id == bus_id and
   ev.recipient in (seat, "all")]`, optionally narrowed by `--kinds`. Print one **TAB-separated** line per
   shown event (raw read — signature verification is the gate's job, not the consume path):
   `<seq>\t<kind>\t<from>\t<candidate_id|brief_id|->\t<subject_sha[:12]|->` (`-` for an absent optional
   field). This exact format is the contract the §6 unit pin and §3.3 E2E assertions parse.
5. **Advance** unless `--no-advance`: `store.advance_cursor(seat, tip)` — monotonic local CAS; mirrors
   `consume-events` advancing to newest. Regression is structurally impossible (`advance_cursor` returns
   `False` for `seq <= cur`).

Notes:
- **Empty bus / fresh seat.** `tip := 0`; `advance_cursor(seat, 0)` is called unconditionally and is a
  no-op for ANY seat — two distinct substrate guards: `refstore.py:279` (`seq != 0 and seq not in valid`)
  is why no `ValueError` is raised (the `seq == 0` case skips the index-range check, `valid == set()` on an
  empty bus), and `refstore.py:284` (`seq <= cur`, `0 <= cur` for any `cur >= 0`) is why it returns `False`
  (no write). Do not add a conditional that skips the call.
- **Authoritative unread count.** `status.count_unread()` / the hook's `_unread_for()` deliberately return
  `0` for scalar-seq cursors ("tracked on the ref-bus"). `consume_bus` is that surface (`seq > cursor` on
  `bus_id`, addressed to the seat). Wiring `STATE.md`/`mailbox_monitor.py` to it is out of scope (§7).
- **Fold contract.** `advance_cursor` writes a blob ref (`refs/threeway/cursors/<seat>`) via a local CAS —
  not a `seen/*.txt` edit and no git commit, so the `check_coordination` standalone-cursor-commit advisory
  does not apply.
- **Error handling** (no traceback): `CursorContentionExceeded` → rc1 (rare on single-host);
  `CursorCorruptionError` (`refstore.py:253-255`, a `ValueError` subclass — NOT caught by a
  `CursorContentionExceeded` handler) → rc1 `"cursor blob corrupt for <seat>: …"`.

### 3.2 `scripts/seat_emit.py` — per-seat signed emission (increment 2b; replaces the shim)

CLI: `seat_emit <seat> <fact> [fact-args] [--session $THREEWAY_SESSION] [--repo-dir .] [--remote origin] [--bus-id prod]`

**The injection hole closes here.** `<seat>` is an explicit positional arg. The `(seat, fact)` pair is
checked against the authority table **FIRST — before any `PairConfig` lookup or construction**; a miss →
**rc2** `"seat <seat> may not emit <fact>"` with **nothing appended** (so a builder/unknown seat hits rc2,
never a `KeyError`). The key loaded is `keys.load_private(seat)` for **that** seat; the `signer` is built
`f"{seat}:{provider}:{session}"` with the seat **hard-bound** — never split back out of a caller-supplied
event (the `bootstrap_emit.py:50` defect).

**Authority table** (the T1 shim facts; verified from `reducer.py` + `loop.py` PairConfig):

| Seat | Emittable facts |
|---|---|
| `coordinator`, `coordinator2` | `candidate`, `release_requested`, `candidate_aborted` |
| `operator`, `operator2` | `attestation` (`--phase preliminary\|release`) |
| `director`, `director2` | *(none — builders write code, not bus facts)* → rc2 |
| `overseer`, `ci`, `merge-gate` | *(not interactive seats)* → rc2 (use `overseer_emit` / `sign_ci_result` / the gate) |

`attestation_revoked`, `co_sign`, `re_verify` are **deferred** (§7) — not in this table.

- **`provider`** is resolved by scanning `[loop.PAIR_A, loop.PAIR_B]`: `seat == pair.coordinator →
  pair.coordinator_provider`; `seat == pair.primary_verifier → pair.verifier_provider` (PairConfig's fields
  are `coordinator_provider`/`verifier_provider`, `loop.py:33-51` — there is NO `operator_provider`). This
  yields `coordinator`→`claude`, `coordinator2`→`codex`, `operator`→`claude`, `operator2`→`codex`.
  Equivalently hold a derived `{seat: provider}` constant built from `PAIR_A`/`PAIR_B` at module load — do
  NOT hard-code a separate table that can drift from `loop.py`.
- **`session`** from `--session`/`$THREEWAY_SESSION`, default `"s1"`. The **unsigned** signer tail (not in
  the 14-field signed view; ignored by the gate's `_seat_of()`) — audit-only, never authority.
- **Event shapes reuse `loop.build_candidate_events` + pick** (and `_abort_event` for `candidate_aborted`)
  so emitted events are byte-compatible with what `gate.verify_and_reduce` accepts — a wrong payload key or
  envelope/payload misplacement makes the predicate silently drop/reject:
  - `candidate`, `release_requested`, `attestation` take `--candidate-id --pair --staging-base --branch
    --tier T0|T1|T2|T3` (default `T1`; + `--phase` for `attestation`). `--tier` is the
    `build_candidate_events` tier arg (the shim's `--tier`); **load-bearing for `candidate`** (sets
    `risk_tier_claimed`, which the gate's `effective_tier` checks against `cycle_go.tier`) and a harmless
    build-input for the other picked facts. **`integration_sha` is RECOMPUTED locally** via `_candidate_set`
    (`git merge-tree` + `git commit-tree`, deterministic per ADR-048) — NEVER read from the bus. It binds
    `subject_sha`: `branch_sha` for `attestation --phase preliminary`; `integration_sha` for `attestation
    --phase release`, `candidate`, `release_requested`. `release_requested` (payload just `{candidate_id}`)
    still needs `--staging-base --branch --tier` so its event is **byte-equivalent to
    `build_candidate_events`** — a non-`None` `subject_sha` that the idempotency key includes
    (`envelope.py:97-107`) and the shim already sets. (The predicate does NOT read `release_requested`, §8;
    the requirement is shim-equivalence + idempotency stability, not a predicate match.)
  - `candidate_aborted` takes `--candidate-id --pair [--brief-id --brief-version]` and **carries
    `candidate_id` in payload** — idempotency-distinctness, because `candidate_id` is NOT in the idempotency
    fingerprint (`envelope.py:105`; an empty-payload abort would dedup across candidates). Bare local ids
    are pair-namespaced (`c9` + `--pair A` → `A:c9`). ADR-059/060.
- **Boundary (explicit).** `seat_emit`'s guarantee is **authority-table enforcement**, *not* OS-level key
  isolation (one keystore on single-host). **The gate is the real security boundary** (verifies signatures
  vs the committed `.pub`, drops out-of-authority/wrong-bus/bad-profile events). `seat_emit` is correctness
  + ergonomics + the seam where per-seat key isolation attaches when the hardening track (C5) lands.
- **Error handling** mirrors the shim's clean exits: `FileNotFoundError` (missing key),
  `AppendContentionExceeded`, `ValueError` (bad ref / non-clean merge / bad pick),
  `subprocess.CalledProcessError` (git) → rc1, message, no traceback. Authority-table miss → rc2.

### 3.3 End-to-end walking skeleton (increment 2c)

The E2E **MODIFIES the existing `tests/unit/test_threeway_e2e_walking_skeleton.py` in place** (ADR-056
`69e65d2c`) — swapping its `bootstrap_emit` calls for `seat_emit` + `consume_bus`, so no
`bootstrap_emit`-dependent test file survives into 2d. It drives a full **T1 brief→merge using only
`overseer_emit` + `seat_emit` + `consume_bus` + the gate — no `bootstrap_emit`**, each CLI invoked as a
**subprocess** against a temp bus + temp repo (`--remote ""` local mode): overseer emits
`brief`/`assignment`/`cycle_go`; `coordinator` emits `candidate`; `operator` emits preliminary `attestation`;
CI signs `ci_result`; `operator` emits release `attestation`; `coordinator` emits `release_requested`;
overseer emits `release_order`; the gate (`run_gate`/`poll_once`) merges to `refs/threeway/test-main` and
emits `merge_completed`.

**consume_bus assertion (exact, not just rc0):** because every T1 fact is broadcast (`recipient="all"`), a
seat reading from `cursor=0` after the merge sees the SAME exhaustive **10-event** set — `brief`,
`assignment`, `cycle_go`, `candidate`, `attestation`(preliminary), `attestation`(release), `ci_result`,
`release_requested`, `release_order`, `merge_completed` (9 distinct kinds; `attestation` twice) — and
advances its cursor to the **tip seq = 10**. Assert the exact parsed kind-multiset + final cursor for **one
representative seat** (`coordinator`) and a cursor-advance read for one other (they are identical, all
being broadcast — six identical assertions add no signal and are brittle). The addressee filter is NOT
exercised here (all-broadcast) — that is the §6 `consume_bus` unit pin's job (a synthetic non-`all` event).
This is the **behavioral-equivalence proof that `seat_emit` ≡ the shim's T1 facts** — the precondition for
retirement. The `consume_bus`+`seat_emit` bare-subprocess pin (§6) must ALSO be green at 2c (it covers
`sys.path` self-bootstrap + clean `--help`, NOT equivalence).

### 3.4 `bootstrap_emit.py` retirement (increment 2d)

Once 2c is green — the E2E proves behavioral equivalence AND the bare-subprocess pin confirms `sys.path`
self-bootstrap (the bare-subprocess pin ALONE is not the equivalence proof): in **one commit**,
`git rm scripts/bootstrap_emit.py` AND `git rm tests/unit/test_threeway_bootstrap_emit.py` (its 5 tests
`from scripts.bootstrap_emit import main`, lines 64/90/111/125/138 — orphaned by the `rm`; left in place
they break pytest collection and the "full threeway suite green" gate) AND repoint the `_ACTIVATION_SCRIPTS`
entry in the bare-subprocess pin (`tests/unit/test_threeway_activation_scripts.py:213`, ADR-055/056
`f5aa1763`/`c02b8049`) from `bootstrap_emit.py` to `consume_bus` + `seat_emit` — atomic, so no pin goes RED
on a missing script without a green replacement. **Coverage migration (all 5 deleted tests land in §6):**
seat-fact round-trips → `test_threeway_seat_emit.py`; `candidate_aborted` authoritative-fold
(coordinator abort + assignment → `is_aborted()==True`) → §6 abort positive-path pin; bare-id namespacing →
§6 namespacing pin; the two error-path totality tests (bad `--repo-dir`, unresolvable ref → clean rc1) → §6
error-path pin. Same commit: update `ARCHITECTURE.md` + `DECISIONS.md` (new ADR marking the shim retired) +
the SP1 spec's "Deferred → sub-project 2" note; grep-confirm **no remaining importers/callers in src OR
tests**. The `candidate_aborted` path is **preserved** (it now lives in `seat_emit`), not lost.
Single-operator ⇒ land-then-remove; no concurrent-emit race window.

## 4. Data flow (one T1 candidate, happy path, seat_emit-only)

1. Operator (relaying chief decisions) → `overseer_emit brief` / `assignment` / `cycle_go` → bus.
2. `coordinator` → `seat_emit coordinator candidate …` → bus.
3. `operator` → `seat_emit operator attestation --phase preliminary` (@ branch_sha) → bus.
4. CI (GitHub Actions, `workflow_dispatch`) → `sign_ci_result` @ integration_sha → bus. (CI runs AFTER the
   candidate is on the bus — `integration_sha` must be known first. The 2c E2E replicates the SP1 ordering:
   preliminary attestation → CI → release attestation; "after the candidate" is the logical minimum.)
5. `operator` → `seat_emit operator attestation --phase release` (@ integration_sha) → bus.
6. `coordinator` → `seat_emit coordinator release_requested …` → bus.
7. Operator → `overseer_emit release_order` @ integration_sha → bus.
8. Merge-gate daemon polls (`collect_candidate_ids` via `release_requested`/`release_order`) → `run_gate` →
   `verify_and_reduce` → predicate → recompute trusted merge → exact-SHA CAS to `refs/threeway/test-main` →
   emit `merge_completed`.
9. Any seat → `consume_bus <seat>` at any point → sees events addressed to it, advances its cursor.

## 5. Error handling

- `seat_emit` validates `(seat, fact)` authority and per-fact args **before** signing; loads only the named
  seat's key; fails loud (rc1/rc2, no traceback). Authority miss = rc2; runtime failures = rc1.
- `consume_bus` normalizes `--remote ""`→`None`, catches `CursorContentionExceeded` and the
  `ValueError`-subclass `CursorCorruptionError` → rc1, no traceback; never mutates events (only the
  monotonic cursor CAS).
- Append contention → `RefEventStore`'s existing retry; surface `AppendContentionExceeded` clearly.
- The merge-gate path is unchanged (`run_gate` is TOTAL post-CAS, ADR-040).

## 6. Testing (campaign TDD discipline — RED→GREEN, non-vacuous)

- **`consume_bus`** (`tests/unit/test_threeway_consume_bus.py`)**:** an event addressed to the seat with
  `seq > cursor` is shown (exact TAB-line format) and the cursor advances to tip. Mutations: break the
  addressee filter → a synthetic non-`all` event leaks (RED); break the advance → cursor stuck (RED).
  `--no-advance` leaves the cursor. **Empty bus** → no output, cursor stays `0`, rc0 (no `max()` error).
  **`--kinds k1`** → a different-kind event is hidden (RED if it leaks). **`bus_id`** → a foreign-`bus_id`
  event is hidden even at `seq > cursor` (RED if it leaks). **`CursorCorruptionError`** (planted corrupt
  cursor blob) → rc1, no traceback.
- **`seat_emit`** (`tests/unit/test_threeway_seat_emit.py`)**:** `seat_emit operator attestation …` produces
  an event that **verifies vs `operator.pub`** and folds as the operator's attestation; wrong-seat-key
  mutation → the gate **drops** it (RED). **Authority-table enforcement (non-vacuous — rc2 AND zero new bus
  events, NOT state-absence):** `seat_emit director attestation` → rc2 + zero events; `seat_emit director
  candidate_aborted` → rc2 + zero events (class-(2): the gate's `is_aborted` is read-time, so seat_emit's
  static guard is the only record-time barrier — a state/gate assertion would be vacuous); `seat_emit
  director release_requested` → rc2 + zero events (class-(3): the gate never reads `release_requested`, so
  assert ONLY rc2 + zero events, never a gate outcome).
- **`candidate_aborted` (migrated coverage):** carries `candidate_id` (two aborts for two candidates → two
  distinct events, not one deduped — ADR-059 trap); **authoritative-fold positive path** —
  `seat_emit coordinator candidate_aborted` + an overseer `assignment` naming that coordinator as
  `executing_coordinator` → `state.is_aborted(cid)==True` (RED if the authority chain breaks); **bare-id
  namespacing** — `--candidate-id c9 --pair A` → the stored event's `candidate_id == "A:c9"`; **error-path
  totality** — bad `--repo-dir` / unresolvable ref → clean rc1, no traceback.
- **`--tier` binding:** `seat_emit coordinator candidate --tier T2 …` sets `risk_tier_claimed == "T2"` in the
  emitted payload (the `--tier`→`risk_tier_claimed` binding §9 relies on).
- **E2E (2c):** full T1 cycle merges via `seat_emit`-only; drop the release attestation → gate `PENDING`
  not `COMPLETED`; `consume_bus` exact-multiset + cursor assertion for the representative seat.
- **Bare-subprocess pin:** `consume_bus` + `seat_emit` run clean as subprocesses (sys.path self-bootstrap,
  ADR-055), repointed from the shim's pin (`f5aa1763`).
- **Gates:** `check_no_ceremony` clean; `ci_smoke` OK; full threeway suite green; spec drift fixed in-change.
  **Each increment's commit gets an independent adversarial Lane-V** before its cross-cutting effects land.

## 7. Scope boundaries

**In:** §3 components (2a–2d) + §6 tests + this spec's §8 invariants — the **T1 shim-equivalent** facts.

**Deferred → follow-on spec (T2/T3 emission; NEW capability, not shim-replacement):**
- `attestation_revoked` (operator self-revoke), `co_sign` (mirror-pair verifier), `re_verify` (own-pair
  verifier, echoing the overseer challenge nonce under key `challenge_nonce` — `tier.py:131,138`; needs a
  registry-verified bus read for the nonce). To land when T2/T3 campaigns are actually deployed. The gate
  already enforces their dynamic verifier authority (`tier._mirror_pair_verifier_seat`,
  `_t3_cross_provider_re_verify`); the follow-on adds only the emitters.

**Deferred → hardening track (gates production sign-off; roadmap C-items):**
- Remote/multi-host cursor publishing; OS-level per-seat key isolation (C5); ref-ACL on the bus host (C3).

**Deferred → separate standalone follow-up (free-form mailbox traffic class):**
- `consume-events` scalar-seq regression check, `status.count_unread()`/`_unread_for()` returning `0` for
  scalar cursors, `check_coordination._check_cursors()` skipping scalar cursors. SP2's `consume_bus`
  provides the authoritative bus unread surface; wiring the mailbox tools to it is the follow-up's job.

## 8. Carried decisions / invariants (verified at HEAD `4bbd97a0`)

- **Cursor locality is correct, not a gap (`refstore.py:261-290`).** `advance_cursor` writes the cursor blob
  via the **local** `cas_create_or_update_ref`, never `push_cas`; `_sync()` + in-range validation still run
  against the authoritative event head, so a cursor never advances past events that exist on the authority.
- **Cursor watermark vs display filters.** The cursor is "scanned the events-ref through seq N." `consume_bus`
  advances to the full-snapshot tip and filters DISPLAY by `bus_id`/addressee — safe because every on-bus
  event addressed to the seat with `seq ≤ tip` is displayed in the same pass before the advance; an on-bus
  event not addressed to the seat is correctly skipped (not "lost"), and a foreign-`bus_id` event is never
  the seat's concern.
- **Seat identity is key-bound; the signer tail is unsigned (`bootstrap_emit.py:49-52`, `envelope.py`).**
  The gate keys on `signer.split(":",1)[0]` for `<seat>.pub` lookup; the `provider:session` tail is outside
  the signed set and MUST NOT be trusted for authority. `seat_emit` hard-binds the seat (positional arg →
  `load_private(seat)`), not derive it from event content.
- **`candidate_id` is signed but NOT in the idempotency fingerprint (`envelope.py:84` vs `:105`).** Any
  per-candidate fact of the same `(sender, kind, subject, payload)` shape must carry `candidate_id` in
  payload or `RefEventStore` dedups the second. `candidate_aborted` does; `seat_emit` preserves it.
- **Threeway facts are broadcast (`recipient="all"`); the reducer/gate are recipient-blind.** `consume_bus`
  filters `recipient ∈ {seat, "all"}` for the inbox view only; no point-to-point semantics.
- **Where authority lives, for the facts SP2 emits (so pins are non-vacuous).** (1) **Record-time
  singletons** (`brief`/`assignment`/`cycle_go`/`release_order`/`ci_result`/`merge_completed` etc.): the
  reducer DROPS a wrong-seat event at fold time — not SP2's facts. (2) **Read-time authority** — `candidate`
  (`authoritative_candidate`, ADR-039/042), `attestation` (predicate resolves the assigned primary_verifier;
  no record-time filter), `candidate_aborted` (`is_aborted`→`executing_coordinator`, `reducer.py:95-119`):
  folded from ANY seat, the gate resolves the correct seat at READ time. `seat_emit`'s static table is a
  COARSE pre-filter; the gate is the real authority — so a `seat_emit` authority-bypass pin must assert
  **rc2 + zero new events**, never a gate/state outcome. (3) **Predicate-invisible** — `release_requested`:
  `reducer.py:371-372` folds it unfiltered and **`predicate.py` never reads it** (only the merge-gate
  daemon's `collect_candidate_ids`, `run_merge_gate.py:28,42,47`, uses it to choose which candidates to
  attempt). `seat_emit`'s rule on it is a correctness/hygiene control, NOT a security boundary; its pin
  asserts **rc2 + zero events ONLY**.
- **`seat_emit` is not the trust root.** The gate (`verify_and_reduce` + `run_gate`) is the security
  boundary; `seat_emit` enforcement is correctness + the future-isolation seam.

## 9. Acceptance criteria

- `consume_bus <seat>` shows exactly the events addressed to `<seat>` (on `--bus-id`, `seq > cursor`) in the
  TAB-line format, advances the local cursor to the snapshot tip (or leaves it under `--no-advance`);
  regression, addressee-leak, `--kinds`, `bus_id`, empty-bus, and `CursorCorruptionError` pins all behave;
  `--remote ""` runs in local mode.
- `seat_emit <seat> <fact>` (T1 facts) round-trips through `verify_and_reduce` as authority-correct and
  verifies against `<seat>.pub`; the wrong-key pin is RED; every per-fact authority-bypass pin asserts
  **rc2 AND zero new bus events** (not state-absence/gate-outcome); `candidate_aborted` authoritative-fold,
  bare-id namespacing, and error-path rc1 pins pass; `--tier` reaches `risk_tier_claimed`.
- The E2E walking-skeleton drives a full T1 brief→merge through `seat_emit` + `consume_bus` + `overseer_emit`
  + the gate with **no `bootstrap_emit`**, with an exact `consume_bus` multiset + cursor assertion, and passes.
- `bootstrap_emit.py` **and** `tests/unit/test_threeway_bootstrap_emit.py` are removed (all 5 behaviors
  migrated to §6), the bare-subprocess pin repointed, docs synced, no importers remain in src or tests.
- `ci_smoke` + `check_no_ceremony` clean; full threeway suite green; spec drift fixed in-change.
