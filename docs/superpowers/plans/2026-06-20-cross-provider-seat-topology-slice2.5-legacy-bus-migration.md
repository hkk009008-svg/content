# Slice 2.5 — Legacy `coordination/` Mailbox Migration Implementation Plan

> **For agentic workers:** REQUIRED: Use `superpowers:subagent-driven-development` (fresh Opus implementer per
> task + two-stage review: spec-compliance → code-quality) or `superpowers:executing-plans`. Steps use checkbox
> (`- [ ]`) syntax for tracking. **This plan is NOT executed in the authoring session — it is authored for a
> later, user-signed-off execution session.** This touches the LIVE 4-seat campaign bus; run execution when bus
> activity is quiet and re-anchor on git refs before every action.

**Goal:** Migrate the live `coordination/` markdown mailbox onto the Slice-2 `refs/threeway/events` signed
substrate — with no dual-write-authority window — and make `coordinator` (today send-only) and a new
`coordinator2` first-class receiving seats.

**Architecture:** Three phases. **Phase A** (additive, safe on a live bus): consolidate the ~12-copy seat
roster to the `protocol_mailbox.py` root + a shell sync-guard, add coordinator/coordinator2 to every
roster/regex/whitelist, seed ISO cursors, rewrite the send-only doctrine prose. **Phase B** (read-only, zero
bus writes): a `legacy_projector` that carries each legacy event as the existing non-load-bearing `event_sent`
kind, and a `divergence` reconciler that compares the raw event SET + cursors (never `reduce()`); shadow ≥1
cycle to zero drift, canary one pair. **Phase C** (the only risky write): loosen the ISO-only cursor regex +
convert all cursors ISO→scalar `seq` atomically, then the single cutover (`preflight_bus_init` → 768 appends →
6 cursor backfills → one authority-flip act), with the retained read-only `sent/` as rollback.

**Tech Stack:** Python 3 (stdlib + the `threeway/` package), Bash (`coordination/bin/*`, hooks), pytest with
inline fixtures, git plumbing via `threeway.gitcas`, Ed25519+JCS signing via `threeway.keys`.

**Design spec:** `docs/superpowers/specs/2026-06-20-threeway-slice2.5-legacy-bus-migration-design.md` (read it
first — it holds the verified edit-site surface §4, the carrier-event model §5, and the acceptance gate §8 each
clause maps to a task below). **Next ADR: ADR-034.** All file:line anchors are HEAD `f0b81a61` snapshots —
**re-grep at execution time**; they drift.

---

## Decisions surfaced (resolved at brainstorming; recorded for the pre-execution checkpoint)

- **D1 — Seat-list consolidation (APPROVED):** `protocol_mailbox.py` is the single Python root; Python copies
  import it; shell sites stay hand-synced + a token-extraction guard test. *Override path:* if execution finds a
  Python copy that genuinely cannot import the root (circular import), leave it hand-synced + add it to the guard.
- **D2 — In-memory shadow, single cutover write (APPROVED):** the projector never appends during shadow; the
  ref-bus is written once, at cutover. Makes "no dual-write authority" structural (clause #6).
- **D3 — Wire coordinator + coordinator2 fully (APPROVED):** both become send/receive seats; coordinator2's
  cursor seeds at the bus head.
- **Carrier-event model:** legacy events ride `event_sent` (NOT load-bearing → gate skips them; `reduce()` never
  folds them); `subject_sha=sha256(source_filename)` makes idempotency injective; `brief_id="legacy-import"`.

## Scope: what this plan does and does NOT build

**IN scope** (gated by spec §11 — Slice 2 green): the §4 edit-site migration; the `legacy_projector` +
`divergence` read-only modules; the ISO→scalar cursor backfill + reversible manifest; the shadow→canary→cutover;
ADR-034 + doc-sync.

**OUT of scope** (deferred, with reason): Slice 3 (`co_sign_satisfied` T2/T3 — `tier.py:32-43`); remote/multi-host
cursor publishing (ADR-031 Decision 5, local-only by design); any change to existing `threeway/` Slice-2 modules
or `THREEWAY_KINDS`; any change to the event vocabulary beyond receiving-seat needs.

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `scripts/protocol_mailbox.py` | Modify | The single roster root: add `RECEIVING_SEATS` (= seats + coordinator + coordinator2) + extend `SENDERS`/`RECIPIENTS` |
| `scripts/status.py`, `mailbox_monitor.py`, `draft_handoff.py`, `proof_bundle.py`, `protocol_capacity.py`, `codex_protocol_model.py`, `continuation_readiness.py` | Modify | Import the roster root instead of re-declaring (D1) |
| `scripts/check_coordination.py` | Modify | regex frm/to alternations (`:56`,`:79`); `_CURSOR_RE` (`:63`) scalar; remove send-only comment/exemption (`:51-55`) |
| `.agents/skills/four-seat-protocol/scripts/seat_status.py` | Modify | roster `:39`, argparse choices `:218`, cursor strptime `:61`, remove coordinator special-case `:117/:125/:148/:156`; reconcile the `.claude/` mirror |
| `coordination/bin/send-event`, `coordination/bin/consume-events` | Modify | FROM/TO/ROLE whitelists + usage strings; cursor `--to` scalar |
| `.codex/hooks/update-state.sh`, `.claude/hooks/update-state.sh` | Modify | `_unread_for` coordinator/coordinator2 + STATE.md lines + scalar cursor compare |
| `coordination/mailbox/seen/coordinator.txt`, `coordinator2.txt` | Create | seeded cursors (ISO in Phase A; scalar in Phase C) |
| `coordination/mailbox/.migration/cursor-backfill.json` | Create | reversible ISO↔seq manifest (Phase C) |
| `threeway/legacy_projector.py` | Create | read `sent/*.md` → carrier `event_sent` Events (read-only) — Task 7 |
| `threeway/divergence.py` | Create | compare projected event SET + cursors vs legacy (read-only) — Task 8 |
| `threeway/cursor_backfill.py` | Create | `total_order`/`iso_to_seq_map`/`backfill`/`restore_from_manifest` + byte-reversible manifest (Phase C) — Task 12 |
| `threeway/cutover.py` | Create | preflight → signed carrier appends → 6-cursor backfill → single authority-flip (Phase C) — Task 13 |
| `tests/unit/test_threeway_legacy_roster.py` (Tasks 1–5), `test_threeway_legacy_projector.py` (Task 7), `test_threeway_divergence.py` (Task 8), `test_threeway_no_dual_write.py` (Task 9), `test_threeway_legacy_cursor.py` (Task 11), `test_threeway_cursor_backfill.py` (Task 12), `test_threeway_cutover.py` (Task 13) | Create | the §8 gate, per module (7 new test files) |
| `tests/unit/test_four_seat_coordination.py` (Tasks 3/4/5), `test_mailbox_monitor.py` (Task 2), `test_seat_status.py` (Task 5), `test_draft_handoff.py` (Task 5), `test_check_coordination.py` (Task 5) | Modify | INVERT the OLD send-only-coordinator doctrine these existing tests encode + widen their cursor fixtures to 6 seats |
| `DECISIONS.md`, `ARCHITECTURE.md` (§13A), the Slice 2.5 stub | Modify | ADR-034 + doc-sync (final chunk) — Task 15 |

## Conventions for every task

- **Test command (mandatory):** `env -u GIT_INDEX_FILE .venv/bin/python -m pytest <path> -q`. A leaked
  `GIT_INDEX_FILE` corrupts any test that shells out to git in a temp repo.
- **Every new test file opens** with `"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/<file>.py -q"""`
  as line 1, and carries its OWN inline fixtures (`_env()`, `_git()`, a `live_repo`/`seatkit` builder). There is
  no `tests/unit/conftest.py` for threeway; do not add threeway fixtures to the shared `tests/conftest.py`.
  Copy helpers verbatim between test files; do not share.
- **Test naming:** `tests/unit/test_threeway_*.py`. The full-suite gate globs `tests/unit/test_threeway_*.py`.
- **No ceremony (ADR-028):** ZERO `xfail`/`skip`/`importorskip`. Non-vacuity is proven by mutating exactly one
  fact in an otherwise-valid flow and asserting the outcome flips — documented per test in a comment. A deferred
  confirmed defect must ship a `pytest.mark.xfail(strict=True, reason=…)` pin, else `check_no_ceremony.py` R1
  fails — this slice introduces none.
- **git-plumbing invariant:** new plumbing uses a scratch `GIT_INDEX_FILE` (a `tmp_path` temp file), never the
  seat index, and still strips the inherited `GIT_INDEX_FILE`; never check out a working tree or read candidate
  workflow files.
- **Commits:** explicit-pathspec only — `git add -- <paths>` then `git commit -m "…" -- <paths>`; never bare
  `git commit`. One commit per task. End every message with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
  Conventional types scoped to threeway: `feat(threeway):`/`fix(threeway):`/`test(threeway):`/`docs(threeway):`.
  Never commit `package.json`/`package-lock.json` (pre-existing unrelated working-tree change).
- **Per-chunk review (execution):** after each chunk, a spec-compliance reviewer + a code-quality reviewer pass
  before proceeding. Chunk-close tasks are verification-only (NO commit).
- **Re-anchor:** every file:line in this plan is a HEAD-`f0b81a61` snapshot; re-grep the symbol before editing.

---
<!-- CHUNKS BELOW -->

## Chunk 1: Phase A — additive seat wiring (backward-compatible, safe on a live bus)

> Sequenced first because every edit here is additive/backward-compatible — no in-flight `send`/`consume` can break, so this chunk is the only one allowed to run while the live 4-seat bus is active. Tasks 1→5 touch overlapping seat-roster surfaces (`protocol_mailbox.py` is the root every later task imports), so per R-ORCH they run **one implementer, strictly sequential — never two implementers on a shared file**. Re-grep every file:line below: the spec anchors are HEAD-`f0b81a61` snapshots and the working HEAD is already `2a29e448` (line numbers drifted).

### Task 1: `protocol_mailbox.py` roster root — `RECEIVING_SEATS` + extend `SENDERS`/`RECIPIENTS`

**Files:**
- Modify: `scripts/protocol_mailbox.py:11-13` (`SEATS`/`SENDERS`/`RECIPIENTS`)
- Test: `tests/unit/test_threeway_legacy_roster.py` (Create)

**Context:** Today (`protocol_mailbox.py:11-13`):
```python
SEATS = ("director", "director2", "operator", "operator2")
SENDERS = (*SEATS, "coordinator")
RECIPIENTS = (*SEATS, "all")
```
`coordinator` is a **sender only** (absent from `RECIPIENTS`); `coordinator2` is **absent entirely**. This is the single Python root (`check_coordination.py:43`, `protocol_effectiveness_report.py` import it; Tasks 2/5 repoint the other copies here). Spec §1/§7: `coordinator`→receiving, `coordinator2`→new full send/receive seat. `all` stays a broadcast TARGET only (never a sender, never a real seat). **NB — keep `SEATS` exactly the 4 real seats** (downstream pair logic in `codex_protocol_model.py:99-101` derives `DIRECTOR_SEATS`/`OPERATOR_SEATS` from the 4-seat shape; do not fold coordinators into `SEATS`). The new oversight tuple is a *separate* name, `RECEIVING_SEATS`.

- [ ] **Step 1: Write the failing test** — create `tests/unit/test_threeway_legacy_roster.py` (this file also hosts the Task 2 roster-completeness test; mirror the inline-`sys.path` style of `tests/unit/test_check_coordination.py:20-31`):

```python
"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_legacy_roster.py -q

Phase-A roster-wiring gate for Slice 2.5 (spec §8 clauses #1/#2). Pins that
coordinator AND coordinator2 are first-class send/receive seats at the
protocol_mailbox root, and that every independent Python roster copy + the four
shell whitelists agree with that root. Non-vacuity: each test mutates exactly
one fact (drops coordinator2 from one tuple/arm) and asserts the check flips.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import protocol_mailbox  # noqa: E402


def test_root_exposes_both_coordinators_as_senders_and_recipients():
    # RECEIVING_SEATS is the oversight-inclusive roster: the 4 real seats + both
    # coordinators. `all` is a broadcast TARGET, not a receiving SEAT — excluded.
    assert protocol_mailbox.RECEIVING_SEATS == (
        "director", "director2", "operator", "operator2",
        "coordinator", "coordinator2",
    )
    # coordinator was send-only today; coordinator2 was absent entirely.
    assert "coordinator" in protocol_mailbox.SENDERS
    assert "coordinator2" in protocol_mailbox.SENDERS
    assert "coordinator" in protocol_mailbox.RECIPIENTS      # NEW: now a valid <to>
    assert "coordinator2" in protocol_mailbox.RECIPIENTS     # NEW
    # SEATS stays exactly the 4 real seats (pair logic depends on this shape).
    assert protocol_mailbox.SEATS == ("director", "director2", "operator", "operator2")
    assert "all" not in protocol_mailbox.RECEIVING_SEATS     # `all` is a target, not a seat

    # --- non-vacuity: prove the assertion is load-bearing, not a tautology ---
    # If RECEIVING_SEATS dropped coordinator2, the equality above would flip RED.
    mutated = tuple(s for s in protocol_mailbox.RECEIVING_SEATS if s != "coordinator2")
    assert mutated != protocol_mailbox.RECEIVING_SEATS
```

- [ ] **Step 2: Run it — verify it fails** — `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_legacy_roster.py::test_root_exposes_both_coordinators_as_senders_and_recipients -q`
  Expected: **FAIL** — `AttributeError: module 'protocol_mailbox' has no attribute 'RECEIVING_SEATS'` (the name does not exist yet); even after adding it, `coordinator` is absent from `RECIPIENTS` and `coordinator2` is absent from both tuples on HEAD.

- [ ] **Step 3: Implement** — replace `protocol_mailbox.py:11-13`:

```python
SEATS = ("director", "director2", "operator", "operator2")
# Oversight-inclusive receiving roster: the 4 pair seats + both coordinators.
# `all` is a broadcast TARGET only (kept in RECIPIENTS), never a real seat, so it
# is NOT in RECEIVING_SEATS. Every independent Python roster copy imports THIS as
# its source of truth (Slice 2.5 D1 consolidation); the 4 shell whitelists are
# hand-synced and guarded by the token-extraction test (spec §8 clause #2).
RECEIVING_SEATS = (*SEATS, "coordinator", "coordinator2")
SENDERS = (*SEATS, "coordinator", "coordinator2")
RECIPIENTS = (*RECEIVING_SEATS, "all")
```
NB: `RECIPIENTS` now equals `(*SEATS, "coordinator", "coordinator2", "all")` — `coordinator`/`coordinator2` become valid `<to>` targets; `all` stays last as the broadcast target.

- [ ] **Step 4: Run — verify it passes (suite still green)** — `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_legacy_roster.py tests/unit/test_check_coordination.py tests/unit/test_status.py -q`
  Expected: **PASS**. Existing tests are unaffected: `check_coordination.ROLES = SEATS` still resolves the 4 real seats (Task 5 widens `ROLES`, not this task), and no test pins `len(RECIPIENTS)` (`test_check_coordination.py` asserts behavior, not tuple length — verified above).

- [ ] **Step 5: Commit**

```bash
git add -- scripts/protocol_mailbox.py tests/unit/test_threeway_legacy_roster.py
git commit -m "feat(threeway): protocol_mailbox root — RECEIVING_SEATS + coordinator/coordinator2 send+receive (Slice 2.5 §7)" -- scripts/protocol_mailbox.py tests/unit/test_threeway_legacy_roster.py
```
(`Co-Authored-By` trailer per the plan conventions — appended to every commit message, not re-printed.)

### Task 2: D1 consolidation — every Python roster copy imports the root

**Files:**
- Modify: `scripts/status.py:126` (`_MAILBOX_SEATS`), `scripts/mailbox_monitor.py:21` (`SEATS`), `scripts/draft_handoff.py:21` (`SEATS`) + `:118` (inline peer tuple), `scripts/proof_bundle.py:13` (`SEATS`), `scripts/protocol_capacity.py:13` (`SEAT_ORDER`), `scripts/codex_protocol_model.py:99` (`SEATS`), `scripts/continuation_readiness.py:28` (`SEATS`), `.agents/skills/four-seat-protocol/scripts/seat_status.py:39` (`SEATS`)
- Test: `tests/unit/test_threeway_legacy_roster.py` (add); `tests/unit/test_mailbox_monitor.py` (decouple the `_repo()` seeding / the `not exists` coordinator assertion — see the BLOCKER below)

> **[BLOCKER — re-pointing `monitor.SEATS` breaks `test_mailbox_monitor`]** `tests/unit/test_mailbox_monitor.py::test_snapshot_reports_unread_latest_event_and_preserves_cursors` (`:51`) ends with `assert not (root / "coordination/mailbox/seen/coordinator.txt").exists()` (`:70`), and its `_repo()` helper (`:20-30`) seeds a cursor `for seat in monitor.SEATS`. Once Task 2 re-points `monitor.SEATS` to `RECEIVING_SEATS`, `_repo()` now writes `seen/coordinator.txt` → the `not exists` assertion FAILS. FIX: add `tests/unit/test_mailbox_monitor.py` to this task's pathspec and EITHER decouple `_repo()`'s seeding to an explicit 4-tuple `("director","director2","operator","operator2")` (keeping the `not exists` assertion meaningful), OR — preferred — keep `_repo()` seeding from `monitor.SEATS` and DELETE/REPLACE the `:70` `not exists` assertion (coordinator legitimately has a cursor now under the consolidated roster). Read `:20-30` + `:51-70` before editing.

**Context:** The receiving roster is re-declared as an independent literal in ≈8 importable modules — the recurring Rule #13 hazard (spec §3 D1). Consolidate: each Python copy's live roster object becomes `protocol_mailbox.RECEIVING_SEATS`. **Traps:**
- `status.py:126` `_MAILBOX_SEATS` is the receiving roster (used by render `:232`, collect `:347/:352`); point it at `RECEIVING_SEATS`.
- `protocol_capacity.py:13` `SEAT_ORDER = ("coordinator", "director", …)` — **coordinator-first ordering** is load-bearing for `:153/:368/:380/:491/:508` owner-iteration/validation. Preserve that order: `SEAT_ORDER = ("coordinator", "coordinator2", *protocol_mailbox.SEATS)`, NOT a bare `RECEIVING_SEATS` splat (which is seats-first). It must REJECT no longer-valid: a `coordinator2`-owned packet must now be ACCEPTED at `:368/:380`.
- `codex_protocol_model.py:99-101` — **only** `SEATS` re-points to `protocol_mailbox.SEATS` (4 real seats). `DIRECTOR_SEATS`/`OPERATOR_SEATS` pair tuples **STAY LITERAL** (`("director","director2")`/`("operator","operator2")`) — coordinators have no pair. `SEAT_BEHAVIOR_SOURCE` (`:102-107`) also stays literal. Module is dependency-free (`:8-11`, only stdlib) → importing `protocol_mailbox` is safe (no circular import; `protocol_mailbox` imports only `pathlib`).
- `draft_handoff.py` has TWO copies: `:21` `SEATS` (5-tuple incl coordinator) AND a **separate inline peer tuple** at `:118` (`for peer in ("director","director2","operator","operator2")`) inside `_peer_heartbeats` — the latter iterates *real pair peers for heartbeats*, NOT the receiving roster. Re-point `:21` to `RECEIVING_SEATS`; leave `:118` as `protocol_mailbox.SEATS` (heartbeats are pair-seat only — coordinators have no presence heartbeat).
- `.agents/skills/four-seat-protocol/scripts/seat_status.py:39` is the **canonical** copy (invoked by `proof_bundle.py:12`, `codex_protocol_model.py:315`, `continuation_readiness.py:148`); its `sys.path` insert (`:32-35`) already puts `scripts/` on the path, so `import protocol_mailbox` resolves. The `.claude/skills/.../seat_status.py:31` stale mirror is **deferred to Task 5's prose/parity pass** — do NOT touch it here.

- [ ] **Step 1: Write the failing test** — add to `tests/unit/test_threeway_legacy_roster.py` an explicit curated importable-module registry (a docstring/comment occurrence must NOT satisfy it — the test reads the *live roster object*):

```python
import importlib

# Curated registry: (module, attribute-holding-the-receiving-roster). Each entry's
# LIVE object must equal the protocol_mailbox root set incl. coordinator2. A comment
# or docstring mentioning "coordinator2" does NOT satisfy this — we read the object.
_IMPORTABLE_ROSTER_SITES = [
    ("status", "_MAILBOX_SEATS"),
    ("mailbox_monitor", "SEATS"),
    ("draft_handoff", "SEATS"),
    ("proof_bundle", "SEATS"),
    ("protocol_capacity", "SEAT_ORDER"),
    ("continuation_readiness", "SEATS"),
]


def test_every_python_roster_copy_equals_the_root():
    root = set(protocol_mailbox.RECEIVING_SEATS)
    for mod_name, attr in _IMPORTABLE_ROSTER_SITES:
        mod = importlib.import_module(mod_name)
        live = set(getattr(mod, attr))
        # set-equality (order-independent: SEAT_ORDER is coordinator-first by design)
        assert live == root, f"{mod_name}.{attr}={sorted(live)} != root {sorted(root)}"

    # protocol_capacity.SEAT_ORDER is coordinator-FIRST by design (load-bearing for
    # owner-iteration/validation); the set-compare above is order-blind, so pin the
    # leading two slots explicitly here.
    import protocol_capacity
    assert protocol_capacity.SEAT_ORDER[0:2] == ("coordinator", "coordinator2")

    # codex_protocol_model.SEATS stays the 4 REAL seats (pair logic depends on it);
    # it must NOT have grown the coordinators.
    cpm = importlib.import_module("codex_protocol_model")
    assert set(cpm.SEATS) == set(protocol_mailbox.SEATS)
    assert cpm.DIRECTOR_SEATS == ("director", "director2")   # pair tuple stays literal
    assert cpm.OPERATOR_SEATS == ("operator", "operator2")

    # --- non-vacuity: drop coordinator2 from ONE real copy → the compare flips RED.
    mutated = set(status._MAILBOX_SEATS) - {"coordinator2"}
    assert mutated != root        # the live object minus coordinator2 is NOT the root


def test_canonical_seat_status_roster_equals_root():
    # .agents/.../seat_status.py is the canonical (non-scripts/) copy; load it by path.
    import importlib.util
    p = (Path(__file__).resolve().parent.parent.parent /
         ".agents" / "skills" / "four-seat-protocol" / "scripts" / "seat_status.py")
    spec = importlib.util.spec_from_file_location("_canonical_seat_status", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert set(mod.SEATS) == set(protocol_mailbox.RECEIVING_SEATS)
```
Add `import status` to the test imports (already on `sys.path`).

- [ ] **Step 2: Run it — verify it fails** — `env -u GIT_INDEX_FILE .venv/bin/python -m pytest "tests/unit/test_threeway_legacy_roster.py::test_every_python_roster_copy_equals_the_root" "tests/unit/test_threeway_legacy_roster.py::test_canonical_seat_status_roster_equals_root" -q`
  Expected: **FAIL** — every copy is still its own literal (`status._MAILBOX_SEATS` is the bare 4-tuple; `proof_bundle.SEATS`/`protocol_capacity.SEAT_ORDER` have `coordinator` but not `coordinator2`), so each `live == root` assertion is False.

- [ ] **Step 3: Implement** — re-point each copy to the root. Each module already imports from `scripts/` siblings, so add `import protocol_mailbox` (or `from protocol_mailbox import RECEIVING_SEATS`) near the existing imports. The edits:

`scripts/status.py:126`:
```python
import protocol_mailbox
_MAILBOX_SEATS = protocol_mailbox.RECEIVING_SEATS
```
`scripts/mailbox_monitor.py:21`:
```python
import protocol_mailbox
SEATS = protocol_mailbox.RECEIVING_SEATS
```
`scripts/draft_handoff.py:21` (leave the `:118` peer tuple alone — re-point it to `protocol_mailbox.SEATS` for the literal-dedup but keep it pair-seat-only):
```python
import protocol_mailbox
SEATS = protocol_mailbox.RECEIVING_SEATS
```
`scripts/proof_bundle.py:13`:
```python
import protocol_mailbox
SEATS = protocol_mailbox.RECEIVING_SEATS
```
`scripts/protocol_capacity.py:13` — **preserve coordinator-first order**:
```python
import protocol_mailbox
# coordinator-first ordering is load-bearing for owner-iteration (:153/:491/:508)
# and validation (:368/:380); keep both coordinators ahead of the pair seats.
SEAT_ORDER = ("coordinator", "coordinator2", *protocol_mailbox.SEATS)
```
`scripts/continuation_readiness.py:28`:
```python
import protocol_mailbox
SEATS = protocol_mailbox.RECEIVING_SEATS
```
`scripts/codex_protocol_model.py:99` — re-point `SEATS` ONLY; pair tuples + `SEAT_BEHAVIOR_SOURCE` stay literal:
```python
import protocol_mailbox
SEATS = protocol_mailbox.SEATS               # 4 real seats; coordinators are NOT pair seats
DIRECTOR_SEATS = ("director", "director2")   # pair tuple — stays literal
OPERATOR_SEATS = ("operator", "operator2")
```
`.agents/skills/four-seat-protocol/scripts/seat_status.py:39` (the `sys.path.insert` at `:34-35` already exposes `scripts/`):
```python
import protocol_mailbox
SEATS = protocol_mailbox.RECEIVING_SEATS
```
NB: `seat_status.py:218` argparse `choices=SEATS + ("coordinator",)` now double-lists coordinator — fix it in Task 5 (it becomes `choices=SEATS`). It is harmless here (argparse de-dups membership); do not change it in this task.

  **Fix the `test_mailbox_monitor` BLOCKER (in this task's pathspec):** re-pointing `monitor.SEATS` to `RECEIVING_SEATS` makes `_repo()` (`tests/unit/test_mailbox_monitor.py:20-30`, which seeds `for seat in monitor.SEATS`) write `seen/coordinator.txt`. So the `assert not (root / "coordination/mailbox/seen/coordinator.txt").exists()` at `:70` in `test_snapshot_reports_unread_latest_event_and_preserves_cursors` must be REMOVED (coordinator legitimately has a cursor now) OR `_repo()`'s seed loop decoupled to an explicit 4-tuple. Preferred: drop the `:70` `not exists` assertion; the test's real subject (director's `unread_count`/`latest_unread`/`broadcast_receipt` + cursor preservation) is unaffected.

- [ ] **Step 4: Run — verify it passes (suite still green)** — `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_legacy_roster.py tests/unit/test_status.py tests/unit/test_mailbox_monitor.py tests/unit/test_seat_status.py tests/unit/test_four_seat_coordination.py -q`
  Expected: **PASS** — with the `test_mailbox_monitor` `:70` `not exists` assertion removed. The roster copies are now the same object; existing tests that iterate the 4 real seats still pass because `-to-coordinator(2)-` events do not yet exist in their fixtures (those tests build only pair-seat traffic), and `protocol_capacity` validation now *accepts* coordinator2 owners but no existing test asserts it *rejects* them. (Task 2 does not widen `ROLES`, so the `cursor_missing`-sensitive fixtures in `test_check_coordination`/`test_seat_status`/`test_four_seat_coordination` stay green here — that coupling lands in Task 5.)

- [ ] **Step 5: Commit**

```bash
git add -- scripts/status.py scripts/mailbox_monitor.py scripts/draft_handoff.py scripts/proof_bundle.py scripts/protocol_capacity.py scripts/codex_protocol_model.py scripts/continuation_readiness.py .agents/skills/four-seat-protocol/scripts/seat_status.py tests/unit/test_threeway_legacy_roster.py tests/unit/test_mailbox_monitor.py
git commit -m "refactor(threeway): D1 — every Python roster copy imports protocol_mailbox.RECEIVING_SEATS (Slice 2.5 §3)" -- scripts/status.py scripts/mailbox_monitor.py scripts/draft_handoff.py scripts/proof_bundle.py scripts/protocol_capacity.py scripts/codex_protocol_model.py scripts/continuation_readiness.py .agents/skills/four-seat-protocol/scripts/seat_status.py tests/unit/test_threeway_legacy_roster.py tests/unit/test_mailbox_monitor.py
```

### Task 3: regex `frm`/`to` alternations — accept `-to-coordinator(2)-` filenames

**Files:**
- Modify: `scripts/check_coordination.py:56` (`_EVENT_NAME_RE`, frm + to groups) + `:79` (`_LIVE_SEAT_ARTIFACT_RES`, the to-group in the inner regex `:85`), `scripts/mailbox_monitor.py:25` (`_EVENT_RE`, frm + to)
- Test: `tests/unit/test_threeway_legacy_roster.py` (add); `tests/unit/test_four_seat_coordination.py` (INVERT `test_coordinator_as_target_is_bad_filename` :183 — see Step 3/4)

> **[BLOCKER — existing OLD-doctrine test inverts here]** `tests/unit/test_four_seat_coordination.py::test_coordinator_as_target_is_bad_filename` (`:183`) seeds a `-to-coordinator-` filename and asserts it FATALs `bad_filename` (because the HEAD `_EVENT_NAME_RE` `to`-group rejects `coordinator`). Widening the `to`-group in this task makes that filename PARSE → no `bad_filename` FATAL → the test FAILS. It encodes the OLD send-only doctrine and is in NO pathspec on HEAD. FIX: add `tests/unit/test_four_seat_coordination.py` to this task's pathspec and rewrite this test to the NEW doctrine (a `-to-coordinator-` envelope is now a VALID filename — assert no `bad_filename` FATAL on it; rename it e.g. `test_coordinator_as_target_is_valid_filename`). Read `:183-191` for the exact current body before rewriting.

**Context:** Three regexes hardcode the seat alternation. On HEAD `check_coordination.py:56-61`:
```python
r"(?P<frm>director|director2|operator|operator2|coordinator)"
r"-to-(?P<to>director|director2|operator|operator2|all)-"
```
A `-to-coordinator2-` filename hits `_check_events` (`:159`) with no `_EVENT_NAME_RE` match → **FATAL `bad_filename`** (`:161`). The `frm` group already has `coordinator` but **not** `coordinator2`; the `to` group has neither. Same for `mailbox_monitor.py:25-29` (event silently dropped from the monitor) and the `_LIVE_SEAT_ARTIFACT_RES` inner artifact regex `:85` (`to`-group `director|director2|operator|operator2|all`). Add `coordinator` to the **to** group and `coordinator2` to **both** frm and to. **Rule #13 sibling — DO NOT TOUCH:** `status.py:53` `_EVENT_RE` uses a generic `-\w+-to-(?P<to>\w+)-` (already matches both coordinators) and `protocol_effectiveness_report.py:51` `MAILBOX_RE` uses a generic `[A-Za-z0-9_]+` recipient group (already matches). Editing those generic groups is unnecessary churn and risks over-narrowing them — leave both as-is (spec §4b marks them "OK").

- [ ] **Step 1: Write the failing test** — add to `tests/unit/test_threeway_legacy_roster.py`:

```python
import re
import check_coordination as cc
import mailbox_monitor as mm

_COORD2_FILE = "2026-06-20T10-00-00Z-coordinator2-to-coordinator-status.md"
_COORD_FILE = "2026-06-20T10-00-01Z-director-to-coordinator-fyi.md"


def test_event_name_re_accepts_coordinator_and_coordinator2():
    m = cc._EVENT_NAME_RE.match(_COORD2_FILE)
    assert m and m.group("frm") == "coordinator2" and m.group("to") == "coordinator"
    m2 = cc._EVENT_NAME_RE.match(_COORD_FILE)
    assert m2 and m2.group("to") == "coordinator"          # coordinator now a valid <to>
    # mailbox_monitor mirror must also match (else the event is dropped from the board)
    assert mm._EVENT_RE.match(_COORD2_FILE)

    # --- non-vacuity: a -to-coordinator2- name must NOT have matched on HEAD ---
    # Build the OLD pattern (coordinator only, no coordinator2) and confirm it FAILS,
    # proving the new alternation is what accepts the input (not a generic \w+).
    old = re.compile(
        r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)-"
        r"(?P<frm>director|director2|operator|operator2|coordinator)"
        r"-to-(?P<to>director|director2|operator|operator2|all)-"
        r"(?P<kind>[a-z0-9-]+)\.md$")
    assert old.match(_COORD2_FILE) is None        # the mutation: drop coordinator2 → RED


def test_generic_sibling_regexes_left_untouched():
    # Rule #13: status._EVENT_RE / effectiveness.MAILBOX_RE use generic groups and
    # already match — assert they still match (we must NOT have narrowed them).
    import status
    import protocol_effectiveness_report as eff
    assert status._EVENT_RE.match(_COORD2_FILE)
    assert eff.MAILBOX_RE.search(_COORD2_FILE)
```

- [ ] **Step 2: Run it — verify it fails** — `env -u GIT_INDEX_FILE .venv/bin/python -m pytest "tests/unit/test_threeway_legacy_roster.py::test_event_name_re_accepts_coordinator_and_coordinator2" -q`
  Expected: **FAIL** — `cc._EVENT_NAME_RE.match(_COORD2_FILE)` is `None` (the `to` group lacks `coordinator`/`coordinator2` and the `frm` group lacks `coordinator2`), so the first `assert m` fails. (`test_generic_sibling_regexes_left_untouched` passes already — it pins the no-touch invariant.)

- [ ] **Step 3: Implement** — `scripts/check_coordination.py:56-61`:
```python
_EVENT_NAME_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)-"
    r"(?P<frm>director|director2|operator|operator2|coordinator|coordinator2)"
    r"-to-(?P<to>director|director2|operator|operator2|coordinator|coordinator2|all)-"
    r"(?P<kind>[a-z0-9-]+)\.md$"
)
```
`scripts/check_coordination.py:85` (inner regex of `_LIVE_SEAT_ARTIFACT_RES` — only the `to` alternation needs widening; `{role}` is the frm):
```python
            rf"(?:director|director2|operator|operator2|coordinator|coordinator2|all)-[a-z0-9-]+\.md\b",
```
`scripts/mailbox_monitor.py:25-30`:
```python
_EVENT_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)-"
    r"(?P<frm>director|director2|operator|operator2|coordinator|coordinator2)"
    r"-to-(?P<to>director|director2|operator|operator2|coordinator|coordinator2|all)-"
    r"(?P<kind>[a-z0-9-]+)\.md$"
)
```
NB: do **not** touch `status.py:53` `_EVENT_RE` or `protocol_effectiveness_report.py:51` `MAILBOX_RE` (generic groups, Rule #13 siblings — already match).

- [ ] **Step 4: Run — verify it passes (suite still green)** — `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_legacy_roster.py tests/unit/test_check_coordination.py tests/unit/test_mailbox_monitor.py tests/unit/test_four_seat_coordination.py -q`
  Expected: **PASS** — including the inverted `test_coordinator_as_target_is_valid_filename` (a `-to-coordinator-` filename now parses, no `bad_filename` FATAL). Other existing `check_coordination`/`mailbox_monitor` tests build only pair-seat filenames (`-to-director-`/`-to-operator-`/`-to-all-`), which the widened alternation still matches identically; adding alternatives never removes a prior match. NB: `test_four_seat_coordination`'s `cursor_missing`-sensitive tests are unaffected by Task 3 (it only touches the filename regex, not `ROLES`); the 6-cursor seed coupling lands in Task 5.

- [ ] **Step 5: Commit**

```bash
git add -- scripts/check_coordination.py scripts/mailbox_monitor.py tests/unit/test_threeway_legacy_roster.py tests/unit/test_four_seat_coordination.py
git commit -m "feat(threeway): event-name regexes accept coordinator/coordinator2 frm+to (Slice 2.5 §4b)" -- scripts/check_coordination.py scripts/mailbox_monitor.py tests/unit/test_threeway_legacy_roster.py tests/unit/test_four_seat_coordination.py
```

### Task 4: shell whitelists + the D1 shell↔Python sync guard (spec §8 clause #2)

**Files:**
- Modify: `coordination/bin/send-event:29` (FROM case), `:30` (TO case), the FROM-error usage string in those arms; `coordination/bin/consume-events:27` (ROLE case), `:6` + `:15` (usage strings); `.codex/hooks/update-state.sh:216-219` + `:235` (STATE.md line); `.claude/hooks/update-state.sh:217-220` + `:236`
- Test: `tests/unit/test_threeway_legacy_roster.py` (add a token-extraction guard — now covering the two `update-state.sh` `_unread_for` call lists too, see the MINOR below); `tests/unit/test_coordination_bin.py` (add a behavioral accept test); `tests/unit/test_four_seat_coordination.py` (INVERT `test_send_event_rejects_coordinator_as_target` :210 — see Step 3/4)

> **[BLOCKER — existing OLD-doctrine test inverts here]** `tests/unit/test_four_seat_coordination.py::test_send_event_rejects_coordinator_as_target` (`:210-212`) runs `send-event director coordinator …` and asserts `returncode != 0` (HEAD's `send-event` TO case rejects `coordinator`). Widening the TO arm in this task makes that send SUCCEED → the test FAILS. It encodes the OLD send-only doctrine and is in NO pathspec on HEAD. FIX: add `tests/unit/test_four_seat_coordination.py` to this task's pathspec and rewrite this test to the NEW doctrine (`send-event director coordinator …` now SUCCEEDS, `returncode == 0`, and writes a `-director-to-coordinator-…md` file; seed `seen/director.txt` is already present via the `repo` fixture's `FOUR_CURSORS` so the cursor footer read succeeds). Rename it (e.g. `test_send_event_accepts_coordinator_as_target`). Read `:210-212` for the exact current body before rewriting.

**Context:** Four shell sites hand-list the roster (spec §4d). On HEAD:
- `send-event:29` `case "$FROM" in director|director2|operator|operator2|coordinator) ;;` and `:30` `case "$TO" in director|director2|operator|operator2|all) ;;` — `coordinator` is a valid FROM but not a TO; `coordinator2` absent from both. The error strings at `:29`/`:30` echo the same lists. **NB:** `:49` reads `head -1 seen/$FROM.txt` for the `Cursor at send:` footer — this is NOT a whitelist; do not alter it (re-grep: it's `CURSOR=$(head -1 …)` near line 51 on current HEAD).
- `consume-events:27` `case "$ROLE" in director|director2|operator|operator2) ;;` — no coordinator at all (it's the *consuming* role whitelist); usage strings at `:6`/`:15` list the four pair seats.
- both `update-state.sh`: `_unread_for director/operator/director2/operator2` calls (`:216-219` codex / `:217-220` claude) + the `**Unread mailbox:**` STATE.md line.

The §8-clause-#2 guard parses the **actual case-arm / call tokens** (not whole-file text) and asserts the set equals `protocol_mailbox.RECEIVING_SEATS` (minus `all`, which is a target). **Mutation:** drop `coordinator2` from the `send-event` TO case-arm only (leave it in the usage string) → the guard goes RED, proving it reads the load-bearing arm not the prose.

- [ ] **Step 1: Write the failing test** — add a token-extraction guard to `tests/unit/test_threeway_legacy_roster.py` (parse the case-arm with a regex anchored to the `case "$VAR" in … ) ;;` line) and a behavioral accept test to `tests/unit/test_coordination_bin.py` (reuse its `repo` fixture + `_run`):

In `tests/unit/test_threeway_legacy_roster.py`:
```python
_BIN = Path(__file__).resolve().parent.parent.parent / "coordination" / "bin"


def _case_arm_tokens(path: Path, var: str) -> set[str]:
    """Extract the seat tokens from a `case "$VAR" in <a>|<b>|...) ;;` arm.
    Reads the LOAD-BEARING arm, never a usage/echo string."""
    text = path.read_text()
    m = re.search(rf'case "\${var}"\s+in\s+([a-z0-9|]+)\)', text)
    assert m, f"no case arm for ${var} in {path.name}"
    return set(m.group(1).split("|"))


_HOOKS = [
    Path(__file__).resolve().parent.parent.parent / ".codex" / "hooks" / "update-state.sh",
    Path(__file__).resolve().parent.parent.parent / ".claude" / "hooks" / "update-state.sh",
]


def _unread_for_roles(path: Path) -> set[str]:
    """Extract the `<role>` tokens from every `_unread_for <role>` CALL in an
    update-state.sh (the LOAD-BEARING per-seat unread computation, spec §8 clause
    #2 — NOT the STATE.md prose line, which is a separate string)."""
    text = path.read_text()
    return set(re.findall(r"_unread_for\s+(director2?|operator2?|coordinator2?)\b", text))


def test_shell_whitelists_match_the_python_root():
    seats = set(protocol_mailbox.RECEIVING_SEATS)        # 4 + both coordinators
    # send-event FROM = every sender (= RECEIVING_SEATS; `all` is target-only, not a sender)
    assert _case_arm_tokens(_BIN / "send-event", "FROM") == seats
    # send-event TO = receivers + the `all` broadcast target
    assert _case_arm_tokens(_BIN / "send-event", "TO") == seats | {"all"}
    # consume-events ROLE = every CONSUMING seat (coordinators now consume; `all` never does)
    assert _case_arm_tokens(_BIN / "consume-events", "ROLE") == seats
    # spec §8 clause #2 also covers the two update-state.sh files: the `_unread_for`
    # call list must compute unread for EVERY receiving seat (= seats; `all` is a
    # target, never has a cursor/unread count).
    for hook in _HOOKS:
        assert _unread_for_roles(hook) == seats, hook

    # --- non-vacuity: drop coordinator2 from the send-event TO arm → guard RED ---
    to_tokens = _case_arm_tokens(_BIN / "send-event", "TO")
    assert (to_tokens - {"coordinator2"}) != (seats | {"all"})
    # --- non-vacuity (the second extractor): drop coordinator2 from ONE hook's
    # `_unread_for` call list → that hook's set != root.
    codex_roles = _unread_for_roles(_HOOKS[0])
    assert (codex_roles - {"coordinator2"}) != seats
```
In `tests/unit/test_coordination_bin.py`:
```python
def test_send_event_accepts_coordinator2_as_to(repo):
    r = _run(SEND_EVENT, ["director", "coordinator2", "fyi", "heads up"], repo,
             stdin="body\n")
    assert r.returncode == 0, r.stderr        # was exit 2 "bad <to>" on HEAD
    files = [p.name for p in (repo / "coordination" / "mailbox" / "sent").iterdir()]
    assert len(files) == 1 and files[0].endswith("-director-to-coordinator2-fyi.md")
```
NB: `repo`'s `kinds.txt` lists `fyi` (`CANONICAL_KINDS`), so the kind check passes. The cursor footer reads `head -1 seen/$FROM.txt` (FROM=`director`, already seeded by the `repo` fixture's `FOUR_CURSORS`), so NO `seen/coordinator2.txt` seed is needed.

- [ ] **Step 2: Run it — verify it fails** — `env -u GIT_INDEX_FILE .venv/bin/python -m pytest "tests/unit/test_threeway_legacy_roster.py::test_shell_whitelists_match_the_python_root" "tests/unit/test_coordination_bin.py::test_send_event_accepts_coordinator2_as_to" -q`
  Expected: **FAIL** — the guard: `send-event` TO arm is `{director,director2,operator,operator2,all}` ≠ `seats | {all}` (missing both coordinators); the behavioral test: `send-event` exits 2 (`bad <to>: coordinator2`) on HEAD.

- [ ] **Step 3: Implement** — `coordination/bin/send-event:29-30` (update both case arms AND the error strings in lockstep — the guard reads the arm, but prose-matches-code is a repo invariant):
```bash
case "$FROM" in director|director2|operator|operator2|coordinator|coordinator2) ;; *) echo "send-event: bad <from>: $FROM (director|director2|operator|operator2|coordinator|coordinator2)" >&2; exit 2;; esac
case "$TO"   in director|director2|operator|operator2|coordinator|coordinator2|all) ;; *) echo "send-event: bad <to>: $TO (director|director2|operator|operator2|coordinator|coordinator2|all)" >&2; exit 2;; esac
```
`coordination/bin/consume-events:27-28` (ROLE arm) + the `:6`/`:15` usage strings:
```bash
case "$ROLE" in director|director2|operator|operator2|coordinator|coordinator2) ;; *)
  usage >&2; exit 2;; esac
```
and both usage strings → `usage: consume-events <director|director2|operator|operator2|coordinator|coordinator2> [--to <timestamp>]`.
`.codex/hooks/update-state.sh:214-219` + `:235` (and the identical `.claude/hooks/update-state.sh:215-220` + `:236`):
```bash
UNREAD_DIR=0; UNREAD_OP=0; UNREAD_DIR2=0; UNREAD_OP2=0; UNREAD_C=0; UNREAD_C2=0
if [ -d "coordination/mailbox/sent" ]; then
  UNREAD_DIR=$(_unread_for director)
  UNREAD_OP=$(_unread_for operator)
  UNREAD_DIR2=$(_unread_for director2)
  UNREAD_OP2=$(_unread_for operator2)
  UNREAD_C=$(_unread_for coordinator)
  UNREAD_C2=$(_unread_for coordinator2)
fi
```
and the STATE.md line:
```bash
- **Unread mailbox:** director=${UNREAD_DIR}, operator=${UNREAD_OP}, director2=${UNREAD_DIR2}, operator2=${UNREAD_OP2}, coordinator=${UNREAD_C}, coordinator2=${UNREAD_C2}
```
NB: `_unread_for` is generic over `$role` (globs `*-to-${role}-*.md`), so it already works for the coordinators once seeded — no function-body change. STATE.md is gitignored/local-only; this only changes the generator.
  **INVERT the existing OLD-doctrine test (in this task's pathspec):** `tests/unit/test_four_seat_coordination.py::test_send_event_rejects_coordinator_as_target` (`:210-212`) — rewrite to the NEW doctrine: `send-event director coordinator fyi x` now SUCCEEDS (`r.returncode == 0`) and writes a `-director-to-coordinator-…md` file; rename it (e.g. `test_send_event_accepts_coordinator_as_target`). The `repo` fixture already seeds `seen/director.txt` (the FROM, for the cursor footer) and lists `fyi` in `kinds.txt`.

- [ ] **Step 4: Run — verify it passes (suite still green)** — `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_legacy_roster.py tests/unit/test_coordination_bin.py tests/unit/test_four_seat_coordination.py -q`
  Expected: **PASS** — including the inverted `test_send_event_accepts_coordinator_as_target`. Existing `test_coordination_bin` cases use pair-seat FROM/TO/ROLE, still whitelisted; the added coordinator arms only widen acceptance. (`update-state.sh` now has the token-extraction guard in `test_threeway_legacy_roster`; the STATE.md output is still covered only by the chunk-close `status.py`/`ci_smoke` run.)

- [ ] **Step 5: Commit**

```bash
git add -- coordination/bin/send-event coordination/bin/consume-events .codex/hooks/update-state.sh .claude/hooks/update-state.sh tests/unit/test_threeway_legacy_roster.py tests/unit/test_coordination_bin.py tests/unit/test_four_seat_coordination.py
git commit -m "feat(threeway): shell whitelists accept coordinator/coordinator2 + D1 sync guard (Slice 2.5 §8.2)" -- coordination/bin/send-event coordination/bin/consume-events .codex/hooks/update-state.sh .claude/hooks/update-state.sh tests/unit/test_threeway_legacy_roster.py tests/unit/test_coordination_bin.py tests/unit/test_four_seat_coordination.py
```

### Task 5: ISO cursor seeding + remove coordinator send-only special-casing + doctrine prose

**Files:**
- Create: `coordination/mailbox/seen/coordinator.txt`, `coordination/mailbox/seen/coordinator2.txt`
- Modify: `scripts/check_coordination.py:51-55` (the send-only comment) + `ROLES` widening + `_check_coordinator_handoff_theater` (`:230`/`:252`, iterate the 4 real `SEATS` not `ROLES` — see the BLOCKER note below); `scripts/draft_handoff.py:84-87`/`:95`/`:140-141`; `.agents/skills/four-seat-protocol/scripts/seat_status.py:117/:125/:148/:156` + `:218` choices; `coordination/bin/consume-events` comment; `coordination/bin/send-event:24-26` comment
- Test (INVERT the OLD send-only doctrine these encode — see Step 3/4 prose): `tests/unit/test_threeway_legacy_roster.py` (add a check_coordination integration test); `tests/unit/test_four_seat_coordination.py` (rewrite `test_coordinator_not_a_role_no_cursor_required` :193 + `test_coordinator_as_sender_lints_clean` :168 `_make_coord` 6-cursor seed + the send-only docstring :7-12); `tests/unit/test_seat_status.py` (rewrite `test_coordinator_mailbox_scope_is_not_reported_as_unread` :31-41 to uniform-coordinator behavior + seed `seen/coordinator.txt`); `tests/unit/test_draft_handoff.py` (rewrite `test_collect_context_handles_coordinator_without_cursor` :128-167 — coordinator now reads a real cursor); `tests/unit/test_check_coordination.py` (widen `make_coord` `default_cursors` :61-65 to 6 seats; the theater fix keeps `test_coordinator_all_seat_handoff_with_each_live_seat_artifact_is_allowed` :374 green)

> **[BLOCKER — `_check_coordinator_handoff_theater` widens with `ROLES`]** On HEAD, `_check_coordinator_handoff_theater` (`check_coordination.py:230`) computes `missing = [role for role in ROLES if not _has_live_seat_artifact(text, role)]` (`:252`). Once this task widens `ROLES` to `RECEIVING_SEATS`, the existing test `test_coordinator_all_seat_handoff_with_each_live_seat_artifact_is_allowed` (`test_check_coordination.py:374`) — whose fixture cites only the **4 real-seat** handoff artifacts (director/director2/operator/operator2) — yields `missing=['coordinator','coordinator2']` → a spurious `coordinator_handoff_theater` FATAL. FIX: change `:252` to iterate the 4 real `SEATS` (`for role in SEATS` — coordinators are oversight seats, not pair seats whose work an All-Seat Handoff must cite), with a one-line comment: `# theater check is about the 4 PAIR seats' real work; coordinators are not cited subjects`. Non-vacuity stays intact: dropping one of the 4 pair-seat artifacts from the fixture still trips the FATAL.

**Context:** Spec §7 (coordinator send-only → receiving) + §6 phase-ordering: Phase A seeds the cursor files in **ISO** format because `_CURSOR_RE` (`check_coordination.py:63`) is still ISO-only until Phase C — a scalar seed would be instant `cursor_unparseable` FATAL. Once `coordinator`/`coordinator2` enter `ROLES`, `_check_cursors` (`:119-127`) DEMANDS `seen/<role>.txt` or FATALs `cursor_missing` — so the cursor seed and the `ROLES` widening must land in the **same task** (spec §6 atomicity). Today `ROLES = SEATS` (`check_coordination.py:51`) which after Task 2 is `protocol_mailbox.SEATS` (4 real seats); widen it to `protocol_mailbox.RECEIVING_SEATS`. Remove the scattered send-only special-casing:
- `check_coordination.py:53-55` comment ("coordinator is a send-only pseudo-seat … Deliberately NOT added to ROLES") — now false.
- `draft_handoff.py:85-86` (`_is_addressed`: `if seat == "coordinator": return "-to-coordinator-" … or "-to-all-"` — coordinator now consumes like any seat; the branch is redundant but **not wrong** — simplify the special-case so coordinator goes through the normal `f"-to-{seat}-"` path), `:95` (`if seat != "coordinator" and cursor …` cursor-filter skip), `:140-141` (`if seat == "coordinator": cursor = "(not used; coordinator is unpinned)"`).
- `seat_status.py:117/:125/:148/:156` coordinator special-cases (unpinned cursor / ALL-SCOPE label / "UNPINNED" advisory) + `:218` `choices=SEATS + ("coordinator",)` → just `choices=SEATS` (after Task 2, `SEATS` = `RECEIVING_SEATS`, which now includes both coordinators; the `+ ("coordinator",)` would double-list).

**ISO seed values:** seed both cursors at a valid ISO **past** timestamp at-or-before the live bus head so they introduce zero spurious backlog and pass `cursor_future`/`cursor_orphan`. Use the current bus-head ISO (re-grep `head -1 coordination/mailbox/seen/director.txt` at exec time — `2026-06-17T19:55:31Z` at planning HEAD) so it matches a real addressed event under the `cursor_orphan` ADVISORY check.

- [ ] **Step 1: Write the failing test** — add to `tests/unit/test_threeway_legacy_roster.py` a real check_coordination run over a fixture tree with a `-to-coordinator2-` envelope + a seeded `seen/coordinator2.txt` (mirror `make_coord` from `test_check_coordination.py` — build it inline so the file stays self-contained):

```python
def _make_coord_with_coord2(tmp_path):
    root = tmp_path / "coordination"
    (root / "mailbox" / "sent").mkdir(parents=True)
    (root / "mailbox" / "seen").mkdir(parents=True)
    name = "2026-06-12T10-00-00Z-director-to-coordinator2-coordination.md"
    (root / "mailbox" / "sent" / name).write_text(
        "# Director → Coordinator2: subj\n\n"
        "**When:** 2026-06-12T10:00:00Z · **From:** director (online)\n\nbody\n")
    for role in cc.ROLES:                       # every ROLES seat needs a cursor
        (root / "mailbox" / "seen" / f"{role}.txt").write_text("2026-06-12T09:00:00Z\n")
    return root


def test_check_coordination_clean_with_coordinator2_traffic(tmp_path):
    # ROLES now includes coordinator2 → its seen file is required AND the
    # -to-coordinator2- filename must parse (Task 3). No FATAL, exit 0.
    assert "coordinator2" in cc.ROLES and "coordinator" in cc.ROLES
    root = _make_coord_with_coord2(tmp_path)
    issues = cc.run(root, since="2026-06-12", now="2026-06-12T12:00:00Z")
    fatals = [i for i in issues if i.severity == "FATAL"]
    assert fatals == [], fatals

    # --- non-vacuity: delete the seeded coordinator2 cursor → cursor_missing FATAL ---
    (root / "mailbox" / "seen" / "coordinator2.txt").unlink()
    issues2 = cc.run(root, since="2026-06-12", now="2026-06-12T12:00:00Z")
    assert any(i.kind == "cursor_missing" and "coordinator2" in i.message
               for i in issues2)
```
Also assert the seeded live cursor files exist + are ISO:
```python
def test_live_coordinator_cursors_seeded_iso():
    seen = Path(__file__).resolve().parent.parent.parent / "coordination" / "mailbox" / "seen"
    for f in ("coordinator.txt", "coordinator2.txt"):
        cur = (seen / f).read_text().strip()
        assert cc._CURSOR_RE.match(cur), f"{f} not ISO (Phase A is ISO-only): {cur!r}"
```

- [ ] **Step 2: Run it — verify it fails** — `env -u GIT_INDEX_FILE .venv/bin/python -m pytest "tests/unit/test_threeway_legacy_roster.py::test_check_coordination_clean_with_coordinator2_traffic" "tests/unit/test_threeway_legacy_roster.py::test_live_coordinator_cursors_seeded_iso" -q`
  Expected: **FAIL** — `cc.ROLES` is still the 4 real seats (`assert "coordinator2" in cc.ROLES` fails), and `coordination/mailbox/seen/coordinator2.txt` does not exist yet (`FileNotFoundError`).

- [ ] **Step 3: Implement** —
  Create the two cursor files with the re-grepped bus-head ISO (Phase A = ISO):
```bash
head -1 coordination/mailbox/seen/director.txt      # re-grep the live bus head ISO at exec time
printf '2026-06-17T19:55:31Z\n' > coordination/mailbox/seen/coordinator.txt
printf '2026-06-17T19:55:31Z\n' > coordination/mailbox/seen/coordinator2.txt
```
  `scripts/check_coordination.py:51` + replace the `:53-55` comment:
```python
# All seats in RECEIVING_SEATS are now addressable receivers WITH a seen cursor
# (Slice 2.5 §7): coordinator is no longer send-only, and coordinator2 is a new
# full send/receive seat. `all` stays a broadcast TARGET only (no seen/all.txt).
ROLES = protocol_mailbox.RECEIVING_SEATS
```
(`check_coordination.py:43` already imports `SEATS`; add `RECEIVING_SEATS` to that import or `import protocol_mailbox` and reference `protocol_mailbox.RECEIVING_SEATS`.)
  **`scripts/check_coordination.py:252` — the theater BLOCKER:** change `missing = [role for role in ROLES if …]` to `missing = [role for role in SEATS if …]` (now that `ROLES == RECEIVING_SEATS`, the theater check must stay scoped to the 4 PAIR seats — coordinators are not cited subjects of an All-Seat Handoff) with the comment `# theater check is about the 4 PAIR seats' real work; coordinators are not cited subjects`. `SEATS` is already imported at `:43`. Without this, `test_coordinator_all_seat_handoff_with_each_live_seat_artifact_is_allowed` (`test_check_coordination.py:374`) FATALs `missing=['coordinator','coordinator2']`.
  `scripts/draft_handoff.py` — drop the send-only branches: `_is_addressed` (`:84-87`) becomes the uniform `return f"-to-{seat}-" in name or "-to-all-" in name`; `_mailbox_events` (`:95`) drops `seat != "coordinator" and`; `collect_context` (`:140-141`) drops the `if seat == "coordinator"` unpinned branch so coordinator reads its real cursor like any seat.
  `.agents/skills/four-seat-protocol/scripts/seat_status.py` — remove the `seat == "coordinator"` special-cases at `:117/:125/:148/:156` (coordinator now has a real cursor + normal "UNREAD" path) and fix `:218` to `ap.add_argument("seat", choices=SEATS)` (SEATS already = RECEIVING_SEATS after Task 2; both coordinators are valid choices).
  Update the `send-event:24-26` and `consume-events:24-26` header comments to drop "coordinator is send-only / no seen cursor" prose.

  **INVERT the existing OLD-doctrine tests in lockstep (each is in this task's pathspec):**
  - `tests/unit/test_four_seat_coordination.py` — rewrite the two tests this task breaks: `test_coordinator_not_a_role_no_cursor_required` (`:193`) currently asserts `"coordinator" not in check_coordination.ROLES` and that a 4-cursor tree raises no `cursor_missing`; INVERT it to the new doctrine — `assert "coordinator" in check_coordination.ROLES and "coordinator2" in check_coordination.ROLES`, and rename it (e.g. `test_coordinators_are_roles_with_cursors`). Update `test_coordinator_as_sender_lints_clean` (`:168`) so its `_make_coord`-built tree seeds all 6 cursors (the `_make_coord` helper's `FOUR_CURSORS` default at `:34/:50` must grow `coordinator`/`coordinator2` ISO seeds, or the test passes a `cursors=` override) — else `cc.run` now FATALs `cursor_missing` for the two coordinators. Rewrite the module docstring `:7-12` send-only paragraph (`coordinator is a later addition: a send-only pseudo-seat …`) to the NEW doctrine: coordinator and coordinator2 are first-class send/receive seats with their own cursor (`-to-coordinator(2)-` is a valid filename; both are in `ROLES`). NB: `test_coordinator_as_target_is_bad_filename` (`:183`) and `test_send_event_rejects_coordinator_as_target` (`:210`) were inverted in Tasks 3/4 respectively — do NOT re-touch them here.
  - `tests/unit/test_seat_status.py` — rewrite `test_coordinator_mailbox_scope_is_not_reported_as_unread` (`:31-41`): the removed special-case strings no longer print, so REPLACE the assertions with the NEW uniform-coordinator behavior — seed a real cursor (`seen/coordinator.txt`) in the fixture, then assert the normal path renders (`cursor: <ts>`, a normal `UNREAD: N`, and `consume via coordination/bin/consume-events coordinator`), and assert the OLD strings are GONE (`"not used; coordinator is unpinned"` not in out, `"coordinator/all scope"` not in out). Rename it (e.g. `test_coordinator_mailbox_reports_unread_from_cursor`).
  - `tests/unit/test_draft_handoff.py` — rewrite `test_collect_context_handles_coordinator_without_cursor` (`:128-167`): `draft_handoff.py:140-141`'s unpinned branch is removed, so `context.mailbox_cursor == "(not used; coordinator is unpinned)"` (`:164`) is now false. INVERT to the new behavior — seed a `seen/coordinator.txt` real cursor in the fixture and assert `context.mailbox_cursor` equals that ISO value (coordinator reads its real cursor like any seat); keep the `mailbox_events` assertions. Rename it (e.g. `test_collect_context_reads_coordinator_real_cursor`).
  - `tests/unit/test_check_coordination.py` — widen `make_coord`'s `default_cursors` (`:61-65`) from the 4-seat dict to seed `coordinator`/`coordinator2` ISO cursors too (else every `make_coord`-using test FATALs `cursor_missing` once `ROLES == RECEIVING_SEATS`). The theater fix at `check_coordination.py:252` keeps `test_coordinator_all_seat_handoff_with_each_live_seat_artifact_is_allowed` (`:374`) green without touching its fixture.

- [ ] **Step 4: Run — verify it passes (suite still green)** — `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_legacy_roster.py tests/unit/test_check_coordination.py tests/unit/test_seat_status.py tests/unit/test_four_seat_coordination.py tests/unit/test_draft_handoff.py tests/unit/test_status.py -q`
  Expected: **PASS** — with the OLD-doctrine tests inverted in Step 3. The fixture trees in `test_check_coordination.py`/`test_seat_status.py`/`test_four_seat_coordination.py` that previously seeded only 4 cursors must now seed 6 — **update their `make_coord`/`_make_coord`/`repo` default-cursors to include `coordinator`/`coordinator2`** in this task (the same change that widens `ROLES`), else they FATAL `cursor_missing`. `test_four_seat_coordination`'s `test_coordinator_not_a_role_no_cursor_required` / `test_seat_status`'s `test_coordinator_mailbox_scope_is_not_reported_as_unread` / `test_draft_handoff`'s `test_collect_context_handles_coordinator_without_cursor` must be the NEW-doctrine rewrites from Step 3 (they encode the removed send-only special-casing and FAIL unmodified). The theater fix (`check_coordination.py:252` → iterate `SEATS`) keeps `test_coordinator_all_seat_handoff_with_each_live_seat_artifact_is_allowed` green. (This is the spec §6-atomicity coupling; all the fixture + test-inversion edits are in this task's pathspec.)

- [ ] **Step 5: Commit**

```bash
git add -- coordination/mailbox/seen/coordinator.txt coordination/mailbox/seen/coordinator2.txt scripts/check_coordination.py scripts/draft_handoff.py .agents/skills/four-seat-protocol/scripts/seat_status.py coordination/bin/send-event coordination/bin/consume-events tests/unit/test_threeway_legacy_roster.py tests/unit/test_check_coordination.py tests/unit/test_seat_status.py tests/unit/test_four_seat_coordination.py tests/unit/test_draft_handoff.py
git commit -m "feat(threeway): coordinator/coordinator2 receiving seats — ISO cursors + drop send-only special-casing (Slice 2.5 §7/§6)" -- coordination/mailbox/seen/coordinator.txt coordination/mailbox/seen/coordinator2.txt scripts/check_coordination.py scripts/draft_handoff.py .agents/skills/four-seat-protocol/scripts/seat_status.py coordination/bin/send-event coordination/bin/consume-events tests/unit/test_threeway_legacy_roster.py tests/unit/test_check_coordination.py tests/unit/test_seat_status.py tests/unit/test_four_seat_coordination.py tests/unit/test_draft_handoff.py
```

### Task 6: chunk close — Phase-A verification gate (NO commit)

> Verification-only gate before Chunk 2 (the read-only projector). No commit. Per the plan conventions, a spec-compliance reviewer + a code-quality reviewer pass on the Chunk-1 diff before proceeding.

- [ ] Run the live legacy checker against the real tree (coordinators now in `ROLES`, cursors seeded): `env -u GIT_INDEX_FILE .venv/bin/python scripts/check_coordination.py` → expect exit 0, **zero FATAL** lines (ADVISORY/INFO permitted).
- [ ] Run the dashboard: `env -u GIT_INDEX_FILE .venv/bin/python scripts/status.py` → completes without traceback; the mailbox section renders all 6 seats.
- [ ] Run this chunk's pytest files: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_legacy_roster.py tests/unit/test_check_coordination.py tests/unit/test_coordination_bin.py tests/unit/test_status.py tests/unit/test_mailbox_monitor.py tests/unit/test_seat_status.py tests/unit/test_four_seat_coordination.py tests/unit/test_draft_handoff.py -q` → all **PASS**.
- [ ] **Run the FULL `tests/unit/` suite** so every edited-module regression is caught (Chunk 1 touches ~9 shared roster/cursor modules whose tests do NOT all match the `test_threeway_*` glob): `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/ -q` → all **PASS**. This explicitly includes the OLD-doctrine tests inverted in Tasks 2–5 and every module touched by the D1 consolidation: `test_four_seat_coordination`, `test_mailbox_monitor`, `test_seat_status`, `test_draft_handoff`, `test_check_coordination`, `test_continuation_readiness`, `test_proof_bundle`, `test_protocol_capacity_board`, `test_codex_protocol_artifacts` (none of these match `test_threeway_*`, so the glob alone would miss them).
- [ ] Run the full threeway glob to confirm no cross-suite regression: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_*.py -q` → all **PASS**.
- [ ] Run smoke + ceremony gates: `.venv/bin/python scripts/ci_smoke.py` → **OK**; `.venv/bin/python scripts/check_no_ceremony.py` → clean (this chunk introduced **zero** `xfail`/`skip`/`importorskip`, per ADR-028).
- [ ] (No commit; verification gate only.)

---

## Chunk 2: Phase B — the read-only projector + divergence-check (zero bus writes)

> Sequenced after Chunk 1 (Phase A roster wiring). Both new modules are **read-only** — `legacy_projector.py` (Task 7) is created first because `divergence.py` (Task 8) imports `project()`, and Task 9's no-dual-write pin imports both. Two test files touch `threeway/legacy_projector.py` and `threeway/divergence.py`; per R-ORCH one implementer works these sequentially (never two implementers on a shared file — Task 7 → 8 → 9 are strictly ordered by the import dependency). No `refs/threeway/events`, `RefEventStore.append`, or `coordination/mailbox` write occurs anywhere in this chunk — that is enforced by construction (neither module imports `RefEventStore`) and pinned in Task 9.

### Task 7: `legacy_projector.project(sent_dir) -> list[Event]` — read-only carrier projection

**Files:**
- Create: `threeway/legacy_projector.py`
- Create: `tests/unit/test_threeway_legacy_projector.py`

**Context:** Spec §5a. The projector reads each `coordination/mailbox/sent/<ts>-<from>-to-<to>-<kind>.md` and emits one `threeway.envelope.Event` per file, carrying the legacy event as the existing non-load-bearing `event_sent` kind (`threeway/__init__.py:19` — in `THREEWAY_KINDS`, NOT in `LOAD_BEARING_KINDS:26-31`). Filename grammar mirrors the POST-Phase-A roster — a SUPERSET of HEAD's `check_coordination.py:56` `_EVENT_NAME_RE` (Phase A / Task 3 widens BOTH the `frm` and `to` groups to add `coordinator`/`coordinator2`): frm ∈ `{director,director2,operator,operator2,coordinator,coordinator2}`, to ∈ `{…,coordinator,coordinator2,all}`, ts is dash-form `\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z`. All 768 live filenames match it (verified `$ python3` filename scan → 0 non-matching). `sender`/`recipient` come from the **filename**, never the body (the corpus has two body formats — 177 YAML-frontmatter + ~514 `**When:**·**From:**` H1 headers — so the body is parsed only for the optional `subject`/`when`/`cursor_at_send` payload fields, best-effort, never for routing). The `all` broadcast is preserved as **one** event, never fanned to 4 (spec §5a fan-in). The keystone is `subject_sha = sha256(source_filename)` (hex) — filenames are unique even in same-second collisions (verified `$` scan → 11 same-second groups / 24 files, all distinct filenames), so this makes `idempotency_key` (`envelope.py:97-101` = `sha256(sender:kind:subj:payload_digest)`) **injective** over the corpus; without it, the ~125 same-`(sender,kind)` identical-body terse events collide and the §5c cutover drops one. `brief_id="legacy-import"` (synthetic, spec §5a → `events/legacy-import/<id>.json`). Events are **UNSIGNED** here — signing is a cutover concern (§5c); this projection exists only for the in-memory shadow comparison, and `event_sent` is not load-bearing so the gate never reads a carrier signature.
**NOT to touch:** do NOT import or call `RefEventStore` / `gitcas.push_cas` / `append` — the projector has no write path by construction (Task 9 pins this). Do NOT edit `envelope.py`, `__init__.py`, or any Slice-2 module (spec §2 YAGNI).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_threeway_legacy_projector.py` (own inline fixtures, no shared conftest):

```python
"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_legacy_projector.py -q"""
import hashlib

from threeway.envelope import idempotency_key
from threeway.legacy_projector import project

# --- inline fixture: build a fake sent/ dir with controlled filenames + bodies ---
_BODY = (
    "# {subj}\n\n"
    "**When:** {when} \u00b7 **From:** {frm} (online)\n\n"
    "VERDICT: GO\n\n"
    "Cursor at send: {cursor}\n"
)


def _write(sent_dir, ts, frm, to, kind, *, subj="S", when="2026-06-01T00:00:00Z",
           cursor="2026-05-31T00:00:00Z"):
    name = f"{ts}-{frm}-to-{to}-{kind}.md"
    (sent_dir / name).write_text(
        _BODY.format(subj=subj, when=when, frm=frm, cursor=cursor))
    return name


def _sent(tmp_path):
    d = tmp_path / "mailbox" / "sent"
    d.mkdir(parents=True)
    return d


def test_project_round_trips_every_field_and_preserves_broadcast(tmp_path):
    sent = _sent(tmp_path)
    n1 = _write(sent, "2026-06-01T10-00-00Z", "operator", "director",
                "verification-report", subj="GO 5e70e43f")
    n2 = _write(sent, "2026-06-01T11-00-00Z", "director", "all",  # broadcast
                "fyi", subj="heads up")
    evs = project(sent)

    # one Event per FILE; the broadcast is ONE event, never fanned to 4
    assert len(evs) == 2
    by_to = {e.recipient: e for e in evs}
    assert set(by_to) == {"director", "all"}        # 'all' preserved, not expanded

    e1 = by_to["director"]
    assert e1.kind == "event_sent"                  # carrier kind (not the legacy kind)
    assert e1.sender == "operator"
    assert e1.brief_id == "legacy-import"
    assert e1.signature is None                      # UNSIGNED at projection
    # the ORIGINAL legacy kind + subject/when/cursor/body/source land in payload
    assert e1.payload["legacy_kind"] == "verification-report"
    assert e1.payload["subject"] == "GO 5e70e43f"
    assert e1.payload["when"] == "2026-06-01T00:00:00Z"
    assert e1.payload["cursor_at_send"] == "2026-05-31T00:00:00Z"
    assert e1.payload["recipient"] == "director"
    assert e1.payload["source_filename"] == n1
    # subject_sha = sha256(source_filename) hex
    assert e1.subject_sha == hashlib.sha256(n1.encode()).hexdigest()


def test_two_identical_bodies_same_sender_kind_both_land_with_distinct_keys(tmp_path):
    # spec §5a injectivity: two byte-identical same-(sender,kind) events must BOTH
    # project, with DISTINCT event ids AND distinct idempotency_keys — proving
    # subject_sha=sha256(filename) breaks the collision that terse status/ack bodies
    # would otherwise hit.
    sent = _sent(tmp_path)
    _write(sent, "2026-06-01T12-00-00Z", "operator", "director", "ack",
           subj="ack", when="2026-06-01T00:00:00Z", cursor="2026-05-31T00:00:00Z")
    _write(sent, "2026-06-01T12-00-01Z", "operator", "director", "ack",
           subj="ack", when="2026-06-01T00:00:00Z", cursor="2026-05-31T00:00:00Z")
    evs = project(sent)
    assert len(evs) == 2
    assert evs[0].id != evs[1].id
    assert idempotency_key(evs[0]) != idempotency_key(evs[1])   # injective


def test_total_order_is_filename_ts_then_full_filename(tmp_path):
    # spec §6 total order: (filename ts, full filename). Two same-second files sort by
    # full filename; a later-ts file sorts after both.
    sent = _sent(tmp_path)
    _write(sent, "2026-06-01T12-00-00Z", "operator", "director", "zeta")
    _write(sent, "2026-06-01T12-00-00Z", "operator", "director", "alpha")
    _write(sent, "2026-06-01T13-00-00Z", "operator", "director", "mid")
    names = [e.payload["source_filename"] for e in project(sent)]
    assert names == sorted(names)               # full-filename total order within + across


def test_subject_sha_empty_collides_two_identical_bodies_MUTATION(tmp_path):
    # MUTATION proof of non-vacuity (ADR-028) for the §5a injectivity keystone.
    #
    # WHY the naive "just set subject_sha='' on both" mutation is VACUOUS: the projector
    # also puts the (distinct) `source_filename` into `payload`, so `payload_digest`
    # already differs between two same-(sender,kind) events and `idempotency_key`
    # (sender:kind:subject_sha:payload_digest) is injective via source_filename ALONE,
    # even with an empty subject_sha. The keys would NOT collide — the assertion would be
    # false on correct GREEN code, making the test tautologically broken.
    #
    # The CORRECT collision requires removing BOTH injectivity sources at once: strip
    # `source_filename` from the payload AND set subject_sha='' for both events. Only the
    # single conceptual fact "no per-file discriminator survives" is mutated; assert the
    # keys THEN collide — proving the live projector's distinctness (asserted in
    # test_two_identical_bodies_... above) is load-bearing, not decorative.
    sent = _sent(tmp_path)
    _write(sent, "2026-06-01T12-00-00Z", "operator", "director", "ack", subj="ack")
    _write(sent, "2026-06-01T12-00-01Z", "operator", "director", "ack", subj="ack")
    a, b = project(sent)
    # sanity: on GREEN code the two keys are DISTINCT (source_filename in payload).
    assert idempotency_key(a) != idempotency_key(b)
    # the mutation: remove EVERY per-file discriminator (subject_sha AND the payload
    # source_filename) from both -> the bodies are now byte-identical in every
    # key-contributing field -> the keys collide.
    a.subject_sha = ""
    b.subject_sha = ""
    a.payload = {k: v for k, v in a.payload.items() if k != "source_filename"}
    b.payload = {k: v for k, v in b.payload.items() if k != "source_filename"}
    assert idempotency_key(a) == idempotency_key(b)   # both discriminators gone -> collide
    # ...therefore the live subject_sha=sha256(filename) is defense-in-depth ON TOP OF the
    # payload source_filename; together they keep idempotency_key injective over the corpus.
```

- [ ] **Step 2: Run it — verify it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_legacy_projector.py -q`
Expected: ERROR — `ModuleNotFoundError: No module named 'threeway.legacy_projector'` (the module does not exist yet); collection fails before any assertion.

- [ ] **Step 3: Implement** `threeway/legacy_projector.py`

```python
"""Legacy coordination/ mailbox -> threeway carrier-event projection (spec §5a).

READ-ONLY. project() reads coordination/mailbox/sent/<ts>-<from>-to-<to>-<kind>.md
files and returns threeway.envelope.Event objects carrying each legacy event as the
existing non-load-bearing `event_sent` kind. NO refs/threeway/events writes, NO
RefEventStore, NO append — this module has no write path by construction (the §8
clause-6 no-dual-write pin depends on that). Events are UNSIGNED: signing is a
cutover concern (§5c); event_sent is not load-bearing so the gate never reads a
carrier signature.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from threeway.envelope import Event

# Filename grammar — kept in lockstep with check_coordination.py:56 _EVENT_NAME_RE
# (re-grep both if the seat roster changes; Slice 2.5 Phase A adds coordinator2 there
# and MUST add it here too). ts is the dash-form timestamp; full filename is the
# secondary total-order key (spec §6).
_EVENT_NAME_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)-"
    r"(?P<frm>director|director2|operator|operator2|coordinator|coordinator2)-"
    r"to-(?P<to>director|director2|operator|operator2|coordinator|coordinator2|all)-"
    r"(?P<kind>[a-z0-9-]+)\.md$"
)

# best-effort body parsers — two corpus formats exist (YAML frontmatter vs the
# **When:**·**From:** H1 header). These feed payload fields ONLY; routing comes from
# the FILENAME (never the body). Absent -> None, never an error.
_WHEN_RE = re.compile(r"\*\*When:\*\*\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)")
_YAML_WHEN_RE = re.compile(r"^when:\s*(.+?)\s*$", re.M)
_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.M)
_YAML_SUBJ_RE = re.compile(r"^subject:\s*(.+?)\s*$", re.M)
_CURSOR_RE = re.compile(r"^Cursor at send:\s*(.+?)\s*$", re.M)

BRIEF_ID = "legacy-import"


def _subject(body: str) -> str | None:
    m = _H1_RE.search(body)
    if m:
        return m.group(1)
    m = _YAML_SUBJ_RE.search(body)
    return m.group(1) if m else None


def _when(body: str) -> str | None:
    m = _WHEN_RE.search(body)
    if m:
        return m.group(1)
    m = _YAML_WHEN_RE.search(body)
    return m.group(1) if m else None


def _cursor(body: str) -> str | None:
    m = _CURSOR_RE.search(body)
    return m.group(1) if m else None


def project(sent_dir) -> list[Event]:
    """Read every sent/*.md whose name matches the grammar -> carrier Events, in the
    spec §6 total order (filename ts, then full filename). Filenames that do not match
    the grammar are skipped (the live corpus has zero such files; a stray non-event
    .md must not become a carrier)."""
    sent = Path(sent_dir)
    files = sorted(
        (p for p in sent.iterdir() if p.name.endswith(".md") and _EVENT_NAME_RE.match(p.name)),
        # total order: (ts group, full filename). ts is a prefix of the name, but key
        # on (ts, name) explicitly so the contract is legible and same-second groups
        # break on full filename deterministically.
        key=lambda p: (_EVENT_NAME_RE.match(p.name).group("ts"), p.name),
    )
    events: list[Event] = []
    for p in files:
        m = _EVENT_NAME_RE.match(p.name)
        body = p.read_text(encoding="utf-8", errors="replace")
        # NB: subject_sha = sha256(SOURCE FILENAME), the §5a injectivity keystone.
        # Filenames are unique even within a same-second group, so idempotency_key
        # (sender:kind:subject_sha:payload_digest) is injective over the corpus. Do NOT
        # base it on the body (terse identical bodies would collide).
        subject_sha = hashlib.sha256(p.name.encode()).hexdigest()
        events.append(Event(
            id=p.name,                       # filename is unique -> a stable event id
            seq=0,                            # seq is assigned at cutover append, not here
            bus_id="prod",
            schema_version="threeway/1",
            kind="event_sent",               # carrier (not the legacy kind)
            sender=m.group("frm"),
            recipient=m.group("to"),         # 'all' preserved as-is (one event, no fan-out)
            signer=f"migration-importer:legacy:{m.group('frm')}",
            payload={
                "legacy_kind": m.group("kind"),
                "subject": _subject(body),
                "when": _when(body),
                "cursor_at_send": _cursor(body),
                "body": body,
                "recipient": m.group("to"),
                "source_filename": p.name,
            },
            brief_id=BRIEF_ID,
            subject_sha=subject_sha,
            # UNSIGNED: signature stays None (signing is the §5c cutover concern).
        ))
    return events
```

- [ ] **Step 4: Run — verify it passes (suite still green)**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_legacy_projector.py tests/unit/test_threeway_envelope.py tests/unit/test_threeway_package.py -q`
Expected: PASS. The new module is additive — no existing module imports it, so the envelope/package suites are byte-unaffected; `idempotency_key`/`Event` are consumed unchanged (spec §2: no Slice-2 module edited).

- [ ] **Step 5: Commit**

```bash
git add -- threeway/legacy_projector.py tests/unit/test_threeway_legacy_projector.py
git commit -m "feat(threeway): legacy mailbox -> carrier-event projector (read-only, Phase B)" -- threeway/legacy_projector.py tests/unit/test_threeway_legacy_projector.py
```
*(Co-Authored-By trailer per the plan conventions.)*

### Task 8: `divergence.diverge(projected, sent_dir, seen_dir) -> Report` — zero-drift reconciler

**Files:**
- Create: `threeway/divergence.py`
- Create: `tests/unit/test_threeway_divergence.py`

**Context:** Spec §5b / §8 clause #4. `diverge(projected_events, sent_dir, seen_dir)` compares the projected event SET against the live legacy mailbox **on the raw set, never `reduce()`/`EffectiveState`**, and returns a `Report` with `.ok: bool` and `.drifts: list[str]`. Contract (all four §5b clauses):
1. **SET bijection with a NON-EMPTY FLOOR** — `len(projected) == #sent/*.md` (the floor guards the degenerate-empty vacuity + the Slice-2 id-overwrite class). A `source_filename`-set bijection between projected events and the on-disk files.
2. **field-level** — `from`/`to`/`kind`(legacy)/`subject`/`when`/`cursor_at_send`/`body` all sourced from `payload`, plus the filename `ts`.
3. **filename ↔ envelope self-consistency** — the filename frm/to/ts must equal the in-file header (`**From:**`/`**When:**` when present; YAML `from:`/`to:` otherwise). Best-effort: only checked when the body exposes a header (the YAML-only legacy events do carry `from:`/`to:`).
4. **per-seat cursor + strictly-greater unread** — for each seat, the legacy `seen/<seat>.txt` high-water mark and its strictly-greater unread count must equal the projection's consumed-seq (highest `seq` whose ts ≤ the cursor under the §6 total order) and its `seq>cursor` unread count. NB: the projected events here carry `seq=0` (projection-time); `diverge` assigns the §6 total-order seq itself (1-based over the sorted projection) so the equivalence is exact without mutating the projector's output.
**NOT to touch:** import `project` from `legacy_projector` (Task 7) — do NOT re-implement filename parsing; do NOT call `reduce()` or build `EffectiveState`; do NOT import `RefEventStore`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_threeway_divergence.py`:

```python
"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_divergence.py -q"""
from threeway.divergence import diverge
from threeway.legacy_projector import project

_BODY = (
    "# {subj}\n\n"
    "**When:** {when} \u00b7 **From:** {frm} (online)\n\n"
    "body line\n\n"
    "Cursor at send: {cursor}\n"
)


def _write(sent, ts, frm, to, kind, *, subj="S", when="2026-06-01T00:00:00Z",
           cursor="2026-05-31T00:00:00Z"):
    name = f"{ts}-{frm}-to-{to}-{kind}.md"
    (sent / name).write_text(_BODY.format(subj=subj, when=when, frm=frm, cursor=cursor))
    return name


def _fixture(tmp_path):
    sent = tmp_path / "mailbox" / "sent"; sent.mkdir(parents=True)
    seen = tmp_path / "mailbox" / "seen"; seen.mkdir(parents=True)
    _write(sent, "2026-06-01T10-00-00Z", "operator", "director", "report",
           when="2026-06-01T10:00:00Z")
    _write(sent, "2026-06-01T11-00-00Z", "director", "operator", "decision",
           when="2026-06-01T11:00:00Z")
    # director consumed both events (cursor at-or-after the 2nd ts) -> unread 0
    (seen / "director.txt").write_text("2026-06-01T11:00:00Z\n")
    # operator consumed only the 1st -> the 2nd (a -to-operator-) is unread (count 1)
    (seen / "operator.txt").write_text("2026-06-01T10:00:00Z\n")
    return sent, seen


def test_zero_drift_on_faithful_fixture(tmp_path):
    sent, seen = _fixture(tmp_path)
    rep = diverge(project(sent), sent, seen)
    assert rep.ok is True, rep.drifts
    assert rep.drifts == []


def test_field_drift_when_body_perturbed_MUTATION(tmp_path):
    # MUTATION (ADR-028): change exactly one fact — one event's BODY on disk AFTER
    # projecting from a pristine copy — so the projected body != the on-disk body. The
    # field-level body compare must flip rep.ok False. (We project first, then perturb
    # the file, then diverge against the perturbed dir.)
    sent, seen = _fixture(tmp_path)
    projected = project(sent)
    victim = next(p for p in sent.iterdir() if "report" in p.name)
    victim.write_text(victim.read_text() + "\nTAMPERED EXTRA LINE\n")
    rep = diverge(projected, sent, seen)
    assert rep.ok is False
    assert any("body" in d for d in rep.drifts)


def test_bijection_floor_red_when_a_sent_file_deleted_MUTATION(tmp_path):
    # MUTATION: delete exactly one sent/*.md AFTER projecting -> projected count (2) !=
    # on-disk count (1). The non-empty-floor bijection must flip RED. Distinct from the
    # body-drift mutation above (this is a count/identity-set break, not a field break).
    sent, seen = _fixture(tmp_path)
    projected = project(sent)
    next(p for p in sent.iterdir() if "decision" in p.name).unlink()
    rep = diverge(projected, sent, seen)
    assert rep.ok is False
    assert any("bijection" in d or "count" in d for d in rep.drifts)


def test_cursor_unread_drift_when_seen_rewound_MUTATION(tmp_path):
    # MUTATION: rewind director's cursor to before the 2nd event -> the legacy
    # strictly-greater unread becomes 1, but the projection-consumed unread for that
    # rewound cursor must MATCH (both recomputed from the same seen value), so this
    # asserts the cursor clause is LIVE by instead corrupting the seen value to a ts that
    # has NO event at-or-before it while the projection still sees 2 events — the
    # consumed-seq equivalence (§8 clause 4) must still hold; to force a drift we make
    # the seen file claim MORE consumed than exists.
    sent, seen = _fixture(tmp_path)
    projected = project(sent)
    # claim a cursor far in the FUTURE: legacy unread = 0; projection consumed = all.
    # then DROP one projected event so projection's max-seq < legacy's implied consumed.
    (seen / "director.txt").write_text("2099-01-01T00:00:00Z\n")
    rep = diverge(projected[:1], sent, seen)   # projection missing the 2nd event
    assert rep.ok is False
    # NB: this case ALSO trips the bijection floor (projected count 1 vs disk 2). It is
    # kept as the "a missing projected event is detected" pin, but it does NOT isolate
    # the cursor clause (clause #4) — that is the next test.


def test_cursor_clause_isolated_with_bijection_intact_MUTATION(tmp_path):
    # CURSOR-ISOLATING mutation (spec §8 clause #4). The bijection stays FULLY intact
    # (project ALL events; the projected source_filename set == the on-disk set → the
    # floor + identity-set checks are GREEN), so a drift here can ONLY come from the
    # per-seat cursor/unread clause, never the floor. NON-VACUITY REQUIRES the
    # implementation to source `legacy_unread` from the RAW on-disk sent/*.md `to`
    # tokens (the legacy checker's own view) and `proj_unread` from the projected
    # events' `e.recipient` seq-view — two INDEPENDENT derivations that agree on a
    # faithful projection and CAN drift when the projection mis-routes one event (see
    # the implementation note: legacy side reads disk, projection side reads events).
    sent, seen = _fixture(tmp_path)
    projected = project(sent)                       # ALL events -> bijection intact
    # operator's cursor between the two events (10:30 is after the 10:00 -report-, before
    # the 11:00 -to-operator- -decision-): legacy strictly-greater unread for operator = 1.
    (seen / "operator.txt").write_text("2026-06-01T10:30:00Z\n")
    # a faithful projection agrees -> zero drift (proves the clause does not false-positive).
    assert diverge(projected, sent, seen).ok is True
    # MUTATION (one fact): the projection mis-routes the -to-operator- event's recipient.
    # On disk the file is STILL -to-operator- (bijection untouched: same source_filename
    # set), so the legacy side counts operator's unread=1 while the projection side, now
    # seeing 0 events addressed to operator, counts unread=0 -> the cursor clause drifts.
    victim = next(e for e in projected if e.recipient == "operator")
    victim.recipient = "director2"
    rep = diverge(projected, sent, seen)
    assert rep.ok is False
    # PIN clause #4 SPECIFICALLY: a `cursor[operator]` drift string is emitted ONLY by the
    # cursor block. (The recipient tamper also emits a field-drift string, but deleting
    # the cursor block would drop THIS string while the field drift alone would not carry
    # it — so this assertion fails if clause #4's code is removed, proving it is pinned.)
    assert any(d.startswith("cursor[operator]") for d in rep.drifts), rep.drifts
```

- [ ] **Step 2: Run it — verify it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_divergence.py -q`
Expected: ERROR — `ModuleNotFoundError: No module named 'threeway.divergence'`; collection fails before any assertion.

- [ ] **Step 3: Implement** `threeway/divergence.py`

> Before writing, re-grep `legacy_projector._EVENT_NAME_RE` and the body header regexes so the self-consistency parse matches the projector's exactly.

```python
"""Divergence-check: projected carrier-event SET vs the live legacy mailbox (spec §5b).

READ-ONLY. Compares on the RAW event set — NEVER reduce()/EffectiveState (legacy kinds
are 100%% disjoint from the threeway governance vocabulary; reduce() would silently
drop them). Returns a Report(.ok, .drifts). No bus writes, no RefEventStore.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from threeway.legacy_projector import _EVENT_NAME_RE

# self-consistency body parsers (best-effort; both corpus formats)
_HDR_FROM_RE = re.compile(r"\*\*From:\*\*\s+(\w+)")
_HDR_WHEN_RE = re.compile(r"\*\*When:\*\*\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)")
_YAML_FROM_RE = re.compile(r"^from:\s*(\w+)\s*$", re.M)
_YAML_TO_RE = re.compile(r"^to:\s*(\w+)\s*$", re.M)


@dataclass
class Report:
    ok: bool
    drifts: list[str] = field(default_factory=list)


def _seen_value(seen_dir: Path, seat: str) -> str | None:
    f = seen_dir / f"{seat}.txt"
    if not f.exists():
        return None
    v = f.read_text().strip()
    return v or None


def _colon_ts(dash_ts: str) -> str:
    # filename dash-form 2026-06-01T10-00-00Z -> ISO colon-form for cursor comparison
    return dash_ts[:11] + dash_ts[11:].replace("-", ":")


def diverge(projected_events, sent_dir, seen_dir) -> Report:
    sent = Path(sent_dir)
    seen = Path(seen_dir)
    drifts: list[str] = []

    on_disk = {p.name for p in sent.iterdir()
               if p.name.endswith(".md") and _EVENT_NAME_RE.match(p.name)}
    proj_names = [e.payload["source_filename"] for e in projected_events]
    proj_set = set(proj_names)

    # (1) SET bijection with a NON-EMPTY FLOOR (spec §8 clause 5).
    if not on_disk:
        drifts.append("bijection: live sent set is EMPTY (non-empty floor violated)")
    if len(projected_events) != len(on_disk):
        drifts.append(
            f"bijection: projected count {len(projected_events)} != "
            f"sent file count {len(on_disk)}")
    if proj_set != on_disk:
        only_proj = proj_set - on_disk
        only_disk = on_disk - proj_set
        drifts.append(f"bijection: identity-set mismatch "
                      f"(only_projected={sorted(only_proj)}, only_disk={sorted(only_disk)})")

    # the §6 total order assigns 1-based seq over the sorted projection (the projector
    # emits seq=0; we order here so the cursor equivalence is exact without mutating it).
    ordered = sorted(projected_events,
                     key=lambda e: (_EVENT_NAME_RE.match(e.payload["source_filename"]).group("ts"),
                                    e.payload["source_filename"]))
    seq_of = {e.payload["source_filename"]: i for i, e in enumerate(ordered, start=1)}

    # (2)+(3) per-event field + filename<->envelope self-consistency.
    for e in projected_events:
        name = e.payload["source_filename"]
        m = _EVENT_NAME_RE.match(name)
        if m is None:
            drifts.append(f"field: projected event {name} has an ungrammatical source_filename")
            continue
        if e.sender != m.group("frm"):
            drifts.append(f"field[{name}]: from {e.sender} != filename {m.group('frm')}")
        if e.recipient != m.group("to"):
            drifts.append(f"field[{name}]: to {e.recipient} != filename {m.group('to')}")
        if e.payload.get("legacy_kind") != m.group("kind"):
            drifts.append(f"field[{name}]: kind {e.payload.get('legacy_kind')} != "
                          f"filename {m.group('kind')}")
        p = sent / name
        if p.exists():
            disk_body = p.read_text(encoding="utf-8", errors="replace")
            if e.payload.get("body") != disk_body:
                drifts.append(f"field[{name}]: body diverges from on-disk file")
            # filename <-> envelope self-consistency (best-effort: only when present)
            fm = _HDR_FROM_RE.search(disk_body) or _YAML_FROM_RE.search(disk_body)
            if fm and fm.group(1) != m.group("frm"):
                drifts.append(f"self-consistency[{name}]: header From {fm.group(1)} "
                              f"!= filename {m.group('frm')}")
            wm = _HDR_WHEN_RE.search(disk_body)
            if wm and e.payload.get("when") != wm.group(1):
                drifts.append(f"field[{name}]: when {e.payload.get('when')} != header {wm.group(1)}")

    # (4) per-seat cursor + strictly-greater unread (spec §8 clause 4).
    # NON-VACUITY KEYSTONE: the LEGACY side reads the on-disk sent/*.md `to` tokens
    # directly (the legacy checker's own view), while the PROJECTION side reads the
    # projected events' `e.recipient` seq-view. These are two INDEPENDENT derivations:
    # on a faithful projection they agree, but a projection that mis-routes one event
    # (e.recipient != the disk filename's `to`) makes them drift WITHOUT touching the
    # bijection (the source_filename set is unchanged). This is what isolates clause #4
    # from the floor/identity-set checks (test_cursor_clause_isolated_..._MUTATION).
    disk_addressed: dict[str, list[str]] = {}     # seat -> [colon_ts...] from DISK
    for name in sorted(on_disk):
        m = _EVENT_NAME_RE.match(name)
        to = m.group("to")
        cts = _colon_ts(m.group("ts"))
        for seat in ({to} if to != "all" else set()):
            disk_addressed.setdefault(seat, []).append(cts)
        if to == "all":                            # broadcast counts for every seated seat
            for seat in {_EVENT_NAME_RE.match(n).group("to") for n in on_disk
                         if _EVENT_NAME_RE.match(n).group("to") != "all"}:
                disk_addressed.setdefault(seat, []).append(cts)
    # the union of seats the LEGACY view and the PROJECTION view each see
    seats = sorted(set(disk_addressed) |
                   {e.recipient for e in projected_events if e.recipient != "all"})
    for seat in seats:
        cur = _seen_value(seen, seat)
        if cur is None:
            continue  # un-seeded seat: cursor clause not applicable (Phase A seeds these)
        # LEGACY (disk): strictly-greater unread = on-disk events addressed to seat with ts > cursor
        legacy_unread = sum(1 for cts in disk_addressed.get(seat, []) if cts > cur)
        # PROJECTION (events): addressed via e.recipient; consumed-seq = highest seq whose
        # colon-ts <= cursor; unread = events with seq > consumed.
        addressed = [e for e in ordered if e.recipient in (seat, "all")]
        consumed = 0
        for e in addressed:
            ts = _colon_ts(_EVENT_NAME_RE.match(e.payload["source_filename"]).group("ts"))
            if ts <= cur:
                consumed = max(consumed, seq_of[e.payload["source_filename"]])
        proj_unread = sum(1 for e in addressed
                          if seq_of[e.payload["source_filename"]] > consumed)
        if legacy_unread != proj_unread:
            drifts.append(f"cursor[{seat}]: legacy unread {legacy_unread} != "
                          f"projection unread {proj_unread}")

    return Report(ok=not drifts, drifts=drifts)
```

> NB on the mutation tests: (1) `test_cursor_unread_drift...` passes `projected[:1]` (the 2nd event dropped) — that trips the bijection floor (count 1 vs disk 2) AND the cursor equivalence, so `rep.ok` is False either way; that test pins "a missing projected event is detected," NOT clause #4 in isolation. (2) `test_cursor_clause_isolated_..._MUTATION` is the clause-#4 isolator: it keeps the bijection intact and mis-routes ONE projected event's `e.recipient`; because the legacy side is DISK-sourced (`disk_addressed`, above) and the projection side is event-sourced, the two unread counts diverge and a `cursor[<seat>]` drift is emitted — a drift string ONLY the cursor block produces. Implement the legacy side from disk exactly as shown, else clause #4 stays vacuous (legacy == projection by construction).

- [ ] **Step 4: Run — verify it passes (suite still green)**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_divergence.py tests/unit/test_threeway_legacy_projector.py -q`
Expected: PASS. `divergence` only imports `legacy_projector` (already green) + stdlib; it touches no Slice-2 module, so the rest of the threeway suite is unaffected.

- [ ] **Step 5: Commit**

```bash
git add -- threeway/divergence.py tests/unit/test_threeway_divergence.py
git commit -m "feat(threeway): divergence-check — projected SET vs legacy mailbox (read-only, Phase B)" -- threeway/divergence.py tests/unit/test_threeway_divergence.py
```

### Task 9: no-dual-write observable — the projection cycle never moves `refs/threeway/events`

**Files:**
- Create: `tests/unit/test_threeway_no_dual_write.py`
- (No production change — this PINS the by-construction guarantee of Tasks 7–8.)

**Context:** Spec §8 clause #6. The projector and divergence-check have **no append path by construction** (neither imports `RefEventStore`); this test makes that structurally-true property an observable regression pin. In a `live_repo` with the bus initialized (a `_new_repo` + `RefEventStore(r)` local store), `before = gitcas.rev_parse(repo, EVENTS_REF)` (None on an empty bus, or the tip on a seeded one); a full `project()` + `diverge()` cycle must leave `gitcas.rev_parse(...) == before`. Belt-and-suspenders (spec §8 clause #6): monkeypatch BOTH `gitcas.push_cas` AND `gitcas.cas_create_or_update_ref` to raise `RuntimeError`, run the same cycle, and assert it completes without raising — proving no ref-CAS path is exercised. **The mutation:** inserting a `RefEventStore(repo).append(<a carrier>, key)` into the cycle flips BOTH checks RED (the ref advances / the patched CAS raises).
**NOT to touch:** no production edit; do not import or wire any append into `legacy_projector`/`divergence`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_threeway_no_dual_write.py`:

```python
"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_no_dual_write.py -q"""
import os
import subprocess

import pytest

from threeway import gitcas, keys
from threeway.refstore import EVENTS_REF, RefEventStore
from threeway.legacy_projector import project
from threeway.divergence import diverge

_BODY = (
    "# {subj}\n\n**When:** {when} \u00b7 **From:** {frm} (online)\n\n"
    "body\n\nCursor at send: 2026-05-31T00:00:00Z\n"
)


def _env():
    env = dict(os.environ)
    env.pop("GIT_INDEX_FILE", None)
    return env


def _git(repo, *args, **kw):
    return subprocess.run(["git", "-C", str(repo), *args],
                          check=True, capture_output=True, text=True, env=_env(), **kw)


def _new_repo(tmp_path):
    r = tmp_path / "r"; r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@e.st"); _git(r, "config", "user.name", "t")
    (r / "base.txt").write_text("base\n")
    _git(r, "add", "-A"); _git(r, "commit", "-q", "-m", "base")
    return r


def _mailbox(tmp_path):
    sent = tmp_path / "mailbox" / "sent"; sent.mkdir(parents=True)
    seen = tmp_path / "mailbox" / "seen"; seen.mkdir(parents=True)
    (sent / "2026-06-01T10-00-00Z-operator-to-director-report.md").write_text(
        _BODY.format(subj="S", when="2026-06-01T10:00:00Z", frm="operator"))
    (seen / "director.txt").write_text("2026-06-01T10:00:00Z\n")
    return sent, seen


def _cycle(sent, seen):
    return diverge(project(sent), sent, seen)


def test_projection_cycle_does_not_move_events_ref(tmp_path):
    r = _new_repo(tmp_path)
    sent, seen = _mailbox(tmp_path)
    before = gitcas.rev_parse(r, EVENTS_REF)        # None on an empty bus
    _cycle(sent, seen)
    assert gitcas.rev_parse(r, EVENTS_REF) == before  # unchanged


def test_projection_cycle_touches_no_ref_cas(tmp_path, monkeypatch):
    # belt-and-suspenders (spec §8 clause 6): if the cycle exercised ANY ref-CAS path,
    # these patched raisers would fire. It completes silently -> no write path.
    sent, seen = _mailbox(tmp_path)

    def _boom(*a, **k):
        raise RuntimeError("no append path may be exercised during shadow projection")

    monkeypatch.setattr(gitcas, "push_cas", _boom)
    monkeypatch.setattr(gitcas, "cas_create_or_update_ref", _boom)
    rep = _cycle(sent, seen)                          # must NOT raise
    assert rep.ok is True, rep.drifts


def test_mutation_an_append_in_the_cycle_flips_both_checks_RED(tmp_path, monkeypatch):
    # MUTATION (ADR-028): the single mutated fact = the cycle DOES append one carrier.
    # Proves both pins are live: (a) the ref moves off `before`; (b) the patched
    # cas_create_or_update_ref raises. A real projection does neither.
    r = _new_repo(tmp_path)
    sent, seen = _mailbox(tmp_path)
    priv, _ = keys.generate_keypair()
    ev = project(sent)[0]
    before = gitcas.rev_parse(r, EVENTS_REF)

    # (a) ref-moves check
    RefEventStore(r).append(ev, priv)
    assert gitcas.rev_parse(r, EVENTS_REF) != before   # the mutation MOVED the ref

    # (b) patched-CAS-raises check (fresh repo so the append actually hits CAS)
    r2 = _new_repo(tmp_path / "two")
    monkeypatch.setattr(gitcas, "cas_create_or_update_ref",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("CAS hit")))
    with pytest.raises(RuntimeError):
        RefEventStore(r2).append(project(sent)[0], priv)
```

- [ ] **Step 2: Run it — verify it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_no_dual_write.py -q`
Expected: At authoring time (Tasks 7–8 already landed) the three positive/mutation tests PASS — but **this task is RED-first only against a hypothetical dual-write projector**. To honor TDD non-vacuity, first stub a one-line `RefEventStore(repo).append(...)` into `legacy_projector.project` locally and run: Expected FAIL — `test_projection_cycle_does_not_move_events_ref` sees the ref move and `test_projection_cycle_touches_no_ref_cas` raises `RuntimeError`. Revert the stub before Step 3. (Document the stub-revert in the commit body — this is the mutation that proves the pin non-vacuous; the module itself is unchanged.)

- [ ] **Step 3: Implement** — no production code. The guarantee is structural (Tasks 7–8 import no store); this test only pins it. Confirm via grep that neither module references a writer:

```bash
grep -nE "RefEventStore|push_cas|cas_create_or_update_ref|\.append\(" threeway/legacy_projector.py threeway/divergence.py
# Expected: NO matches (no write path by construction). If any line matches, the
# projector/divergence acquired a dual-write path — STOP and remove it (spec §10).
```

- [ ] **Step 4: Run — verify it passes (suite still green)**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_no_dual_write.py tests/unit/test_threeway_refstore.py -q`
Expected: PASS. The test consumes `RefEventStore`/`gitcas` read-only (except the explicit mutation appends in their own temp repos); the refstore suite is unaffected because nothing in `refstore.py` changed.

- [ ] **Step 5: Commit**

```bash
git add -- tests/unit/test_threeway_no_dual_write.py
git commit -m "test(threeway): pin no-dual-write — shadow projection never moves the events ref (Phase B)" -- tests/unit/test_threeway_no_dual_write.py
```

### Task 10: chunk close — Phase B verification gate (NO commit)

- [ ] Run the chunk's three test files together:
  `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_legacy_projector.py tests/unit/test_threeway_divergence.py tests/unit/test_threeway_no_dual_write.py -q` → all PASS.
- [ ] Re-run the full threeway suite to confirm Phase A + Phase B are jointly green and nothing regressed:
  `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_*.py -q` → all PASS.
- [ ] Run `.venv/bin/python scripts/ci_smoke.py` → OK.
- [ ] Run `.venv/bin/python scripts/check_no_ceremony.py` → clean (Phase B introduces zero `xfail`/`skip`/`importorskip`).
- [ ] (No commit; verification gate before Chunk 3 — Phase C cursor migration + cutover.)

---

## Chunk 3: Phase C — cursor migration + cutover (Tasks 11-14)

> Sequenced LAST: Phase C holds the **only risky writes** (the ISO→scalar cursor flip and the single 768-append cutover) — gated behind Phase B's zero-drift shadow + canary. Task 11 (regex loosening) must land **atomically** before Task 12 (backfill) writes any scalar cursor, and before Task 13 (cutover) advances scalar cursors, else an intermediate commit has a scalar cursor under an ISO-only `_CURSOR_RE` → instant `cursor_unparseable` FATAL (spec §6 "Phase ordering"). All three tasks touch **different files** except that Tasks 11+12 both write `coordination/mailbox/seen/*.txt`-adjacent logic — so one implementer runs them **sequentially** (R-ORCH: never two implementers on a shared file; reviewers follow each).

### Task 11: Loosen every ISO-only cursor parser to accept a scalar `seq` — atomically

**Files:**
- Modify: `scripts/check_coordination.py:63` (`_CURSOR_RE`); `:130-132` (`cursor_unparseable` gate); `:134` (`cur > now` future-check) — the future-check is ISO-string-only and must be skipped for a scalar.
- Modify: `scripts/status.py:60-62` (`_normalize_ts`) + `:65-87` (`count_unread`) — colon→dash normalize assumes ISO.
- Modify: `scripts/mailbox_monitor.py:33-39` (`_parse_iso`) + `:89-107` (`_unread_events`/`_broadcast_receipt` cursor compares).
- Modify: `.agents/skills/four-seat-protocol/scripts/seat_status.py:58-65` (`_parse_cursor_ts` strptime) + `mailbox()` `:146` (add the all-digit scalar short-circuit — see Step 3; the bare `cursor_dt is None` branch over-counts on a scalar).
- Modify: `coordination/bin/consume-events:52-56` (the `--to` timestamp `case` validation).
- Modify: `.codex/hooks/update-state.sh:200-213` (the `_unread_for` byte-compare `[[ "$ts" > "$curkey" ]]` at `:210`) and `.claude/hooks/update-state.sh` (its mirror; the byte-compare is at `:211`, one line lower than .codex's `:210`).
- Test: `tests/unit/test_threeway_legacy_cursor.py` (create — now includes scalar checks for `status.count_unread`, `consume-events --to`, and `seat_status.mailbox`, so all 7 loosened parsers carry a non-vacuous scalar test, not just `check_coordination`).

**Context:** `_CURSOR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")` (`check_coordination.py:63`) is ISO-only; `_check_cursors` (`:130-132`) raises a **FATAL `cursor_unparseable`** the instant a `seen/<seat>.txt` holds a scalar `seq`. The downstream future-check `cur > now` (`:134`) is a lexical ISO compare — for a scalar it is meaningless (a scalar is never "in the future"), so it must be guarded by "is this an ISO cursor?". The same ISO assumption lives in 5 more parsers (§4c). **The loosening must land in ONE commit across all of them** (spec §6 "all in Phase C, atomically") so no intermediate state has a scalar cursor under an ISO-only checker. **Rule #13 siblings NOT to touch this task:** the `_EVENT_NAME_RE`/`_EVENT_RE` *filename* regexes (`check_coordination.py:56`, `status.py:53`, `mailbox_monitor.py:25`) parse event **filenames** (always dash-ISO on disk) — they are not cursor parsers and stay ISO; only the cursor *content* parsers loosen. The transitional regex accepts **both** forms (scalar OR ISO) because Phase A seeded ISO cursors that still exist until Task 12 converts them.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_threeway_legacy_cursor.py` (own inline fixtures; no shared conftest):

```python
"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_legacy_cursor.py -q"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

# scripts/ is importable in this repo's pytest config (see existing
# tests/unit/test_threeway_* that import status/protocol_mailbox); mirror that.
_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "scripts"))
import check_coordination as cc  # noqa: E402
import status  # noqa: E402  (the scalar-path count_unread short-circuit, below)


def _seed_mailbox(root: Path, cursor_text: str):
    """A minimal coordination tree: one event addressed to director + its cursor."""
    sent = root / "coordination" / "mailbox" / "sent"
    seen = root / "coordination" / "mailbox" / "seen"
    sent.mkdir(parents=True); seen.mkdir(parents=True)
    (sent / "2026-06-17T19-55-31Z-operator-to-director-status.md").write_text(
        "# s\n\n**From:** operator\n**When:** 2026-06-17T19:55:31Z\n")
    for seat in cc.ROLES:
        (seen / f"{seat}.txt").write_text(cursor_text + "\n")
    return root


def test_scalar_seq_cursor_is_accepted_not_fatal(tmp_path):
    # NON-VACUITY: a scalar-seq cursor must pass _CURSOR_RE (no cursor_unparseable
    # FATAL). MUTATION (documented): revert _CURSOR_RE to the ISO-only pattern
    # r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$" and this assertion flips — the
    # scalar "42" no longer matches and _check_cursors emits cursor_unparseable FATAL.
    _seed_mailbox(tmp_path, "42")                       # post-backfill scalar seq
    now = "2026-06-18T00:00:00Z"
    names = cc._event_names(tmp_path / "coordination", "sent")
    issues = cc._check_cursors(tmp_path / "coordination", now, names)
    fatals = [i for i in issues if i.severity == "FATAL"]
    assert fatals == [], [(i.kind, i.message) for i in fatals]
    assert cc._CURSOR_RE.match("42")                    # scalar matches
    assert cc._CURSOR_RE.match("0")                     # the seq-0 floor matches


def test_iso_cursor_still_accepted_during_transition(tmp_path):
    # Phase A seeded ISO cursors that survive until Task 12 converts them; the
    # transitional regex must keep accepting ISO so no live seat half-breaks.
    _seed_mailbox(tmp_path, "2026-06-17T19:55:31Z")
    now = "2026-06-18T00:00:00Z"
    names = cc._event_names(tmp_path / "coordination", "sent")
    issues = cc._check_cursors(tmp_path / "coordination", now, names)
    assert [i for i in issues if i.severity == "FATAL"] == []


def test_scalar_cursor_is_never_flagged_future(tmp_path):
    # the cur>now ISO future-check is meaningless for a scalar; it must be SKIPPED.
    # MUTATION: drop the is-ISO guard on the future-check -> "999999" > now (lexical
    # ISO compare) fires a spurious cursor_future FATAL and this flips RED.
    _seed_mailbox(tmp_path, "999999")
    now = "2026-06-18T00:00:00Z"
    names = cc._event_names(tmp_path / "coordination", "sent")
    issues = cc._check_cursors(tmp_path / "coordination", now, names)
    assert not [i for i in issues if i.kind == "cursor_future"]


# --- the OTHER 5 loosened parsers (the RED test only imports check_coordination, so
# without these the scalar-path edits in status.count_unread / seat_status / the
# consume-events case / both update-state.sh are UNTESTED). Each is a non-vacuous
# scalar check on a distinct parser.

def test_status_count_unread_scalar_short_circuits_to_zero():
    # status.count_unread on a scalar `seq` cursor returns 0 (unread is ref-bus-tracked,
    # not computed from filenames here). MUTATION: drop the _is_iso_cursor guard ->
    # a scalar would fall through to the lexical filename compare and over-count -> != 0.
    files = [
        "2026-06-13T01-00-00Z-director-to-operator-status.md",
        "2026-06-13T02-00-00Z-director-to-all-fyi.md",
    ]
    assert status.count_unread("42", files, "operator") == 0          # scalar -> 0
    # sanity: an ISO cursor still counts normally (the guard is a strict superset)
    assert status.count_unread("2026-06-13T00:00:00Z", files, "operator") == 2


def _sh_env():
    e = dict(os.environ); e.pop("GIT_INDEX_FILE", None); return e


def test_consume_events_accepts_scalar_to(tmp_path):
    # subprocess smoke: a scalar `--to` must be ACCEPTED by the loosened case (exit != 2
    # "malformed --to"). MUTATION: revert the case to ISO-only -> the all-digit "42"
    # hits the `*[!0-9]*`-less default and is rejected -> exit 2 -> this flips RED.
    sent = tmp_path / "coordination" / "mailbox" / "sent"; sent.mkdir(parents=True)
    seen = tmp_path / "coordination" / "mailbox" / "seen"; seen.mkdir(parents=True)
    (seen / "director.txt").write_text("0\n")
    r = subprocess.run([str(_REPO / "coordination" / "bin" / "consume-events"),
                        "director", "--to", "42"],
                       cwd=tmp_path, env=_sh_env(), capture_output=True, text=True)
    # accept = the --to validation passed (no "malformed --to" on stderr / exit 2 there).
    assert "malformed --to" not in r.stderr, r.stderr


def test_seat_status_scalar_cursor_reports_zero_unread(tmp_path):
    # subprocess smoke of seat_status.mailbox with a SCALAR cursor: it must short-circuit
    # to "0 / ref-bus-tracked", NOT over-count every event. MUTATION: drop the all-digit
    # short-circuit in seat_status.mailbox -> _parse_cursor_ts returns None -> cursor_dt
    # is None -> every event counted unread -> "UNREAD: 0" no longer holds -> RED.
    coord = tmp_path / "coordination" / "mailbox"
    (coord / "sent").mkdir(parents=True); (coord / "seen").mkdir(parents=True)
    (coord / "sent" / "2026-06-13T01-00-00Z-director-to-operator-status.md").write_text("# e\n")
    (coord / "sent" / "2026-06-13T02-00-00Z-director-to-operator-status.md").write_text("# e\n")
    (coord / "seen" / "operator.txt").write_text("99\n")            # scalar seq cursor
    r = subprocess.run([sys.executable,
                        str(_REPO / ".agents" / "skills" / "four-seat-protocol"
                            / "scripts" / "seat_status.py"), "operator"],
                       cwd=tmp_path, env=_sh_env(), capture_output=True, text=True)
    out = r.stdout + r.stderr
    assert "UNREAD: 0" in out or "ref-bus-tracked" in out, out
```

- [ ] **Step 2: Run it — verify it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_legacy_cursor.py::test_scalar_seq_cursor_is_accepted_not_fatal -q`
Expected: FAIL — on HEAD `_CURSOR_RE` is ISO-only, so the scalar `"42"` does not match → `_check_cursors` appends a `cursor_unparseable` FATAL → `fatals != []`.

- [ ] **Step 3: Implement — loosen every cursor parser (atomically, one task)**

In `scripts/check_coordination.py`, replace the regex (`:63`) and add an is-ISO helper; guard the future-check (`:134`):

```python
# Cursor CONTENT is transitionally a scalar `seq` (post Slice-2.5 backfill) OR an
# ISO-UTC timestamp (pre-backfill, Phase-A-seeded). NB: this gates the cursor FILE
# CONTENT only — the event-FILENAME regexes (_EVENT_NAME_RE / _EVENT_RE) stay
# dash-ISO and are deliberately NOT loosened (Rule #13: different parser, on-disk
# filenames are always ISO).
_ISO_CURSOR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_SEQ_CURSOR_RE = re.compile(r"^\d+$")
_CURSOR_RE = re.compile(
    r"^(?:\d+|\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)$")   # scalar seq OR ISO
```

Then in `_check_cursors`, gate the future-check (`:134`) so a scalar is never "future" (the orphan/`min(addressed)` ISO compare at `:146` is already inside an `addressed and cur_dash ... ` clause; add the same is-ISO guard there):

```python
        if not _CURSOR_RE.match(cur):
            issues.append(CoordIssue(rel, "cursor_unparseable", "FATAL",
                                     f"{role} cursor not a seq or ISO UTC ts: {cur!r}"))
            continue
        # The future-check + orphan-vs-event compares are ISO-lexical; a scalar
        # seq cursor has no wall-clock and cannot be "future" or "orphan".
        if _ISO_CURSOR_RE.match(cur):
            if cur > now:
                issues.append(CoordIssue(rel, "cursor_future", "FATAL",
                                         f"{role} cursor {cur} is in the future (now {now})"))
                continue
            all_names = names + _event_names(coord_root, "archive")
            addressed = [m.group("ts") for m in map(_EVENT_NAME_RE.match, all_names)
                         if m and m.group("to") in (role, "all")]
            cur_dash = _dash(cur)
            if addressed and cur_dash not in addressed and cur_dash > min(addressed):
                issues.append(CoordIssue(
                    rel, "cursor_orphan", "ADVISORY",
                    f"{role} cursor {cur} matches no event addressed to {role}"))
```

In `scripts/status.py` `count_unread` (`:65`): when the cursor is a scalar `seq`, an ISO-filename event is "unread" iff its **seq** (its position in the §6 total order) exceeds the cursor — but `count_unread` has only filenames, not seqs. Per spec §5b the scalar↔unread equivalence is the projection's job; the legacy checker only needs to **not crash** on a scalar. Make `_normalize_ts` a no-op for a scalar and short-circuit the compare so a scalar cursor counts every event as ISO-incomparable-but-not-erroring:

```python
def _normalize_ts(ts: str) -> str:
    """Colon→dash for ISO cursors; a scalar `seq` cursor passes through unchanged
    (it is not a wall-clock and is compared by the projection layer, not here)."""
    return ts.replace(":", "-")


def _is_iso_cursor(ts: str) -> bool:
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z$", ts.replace(":", "-")))
```

and in the `count_unread` loop, only do the lexical `>` compare for an ISO cursor (a scalar cursor returns 0 here — the authoritative unread count for a migrated seat comes from `RefEventStore` `seq>cursor_seq`, not this legacy path):

```python
    cursor_norm = _normalize_ts(cursor_ts)
    if not _is_iso_cursor(cursor_ts):
        return 0          # scalar-seq cursor: unread is computed on the ref-bus, not here
    count = 0
    for fname in event_filenames:
        ...
```

In `scripts/mailbox_monitor.py`, `_parse_iso` (`:33`) already returns `None` on a non-ISO string (the strptime raises `ValueError` → caught), and `_unread_events`/`_broadcast_receipt` (`:89`/`:100`) already early-return on `_parse_iso(cursor) is None`. **Verify this is true at exec time** — if so, a scalar cursor already degrades gracefully (returns `[]`/`"?"`), and this file needs only a one-line comment noting scalar cursors are intentionally treated as "ref-bus-tracked, not monitored here." (If `_parse_iso` is reached on a path that does NOT guard `None`, add the guard.)

In `.agents/skills/four-seat-protocol/scripts/seat_status.py`, `mailbox()` (`:146`) currently does `if cursor_dt is None or ts > cursor_dt:` — and `_parse_cursor_ts` (`:58`) returns `None` on a scalar (strptime raises), so `cursor_dt is None` makes EVERY event count as unread (an OVER-count, not 0). A scalar cursor must short-circuit to 0, NOT fall into the `cursor_dt is None` "count everything" branch. Add an explicit all-digit scalar guard parallel to `status.py`'s — detect an all-digit `cursor_raw` after reading the seen file and print `0 / ref-bus-tracked` instead of the lexical recompute:

```python
    cursor_raw = ...               # already read from seen/<seat>.txt
    if cursor_raw.strip().isdigit():
        # scalar `seq` cursor (post Slice-2.5 backfill): unread is tracked on the
        # ref-bus (RefEventStore seq>cursor_seq), NOT recomputed from filenames here.
        print(f"cursor: {cursor_raw}")
        print("UNREAD: 0 / ref-bus-tracked")
        return
```

Place this BEFORE the `cursor_dt = _parse_cursor_ts(cursor_raw)` line so the `cursor_dt is None` over-count branch is never reached for a scalar. (Leave the ISO path unchanged — the guard is a strict pre-filter.)

In `coordination/bin/consume-events`, extend the `--to` validation `case` (`:52-56`) to accept a bare scalar:

```sh
  case "$TARGET" in
    [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z) ;;
    [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]-[0-9][0-9]-[0-9][0-9]Z) ;;
    *[!0-9]*) echo "consume-events: malformed --to (seq or ISO ts): $TARGET" >&2; exit 2;;
    *) ;;   # all-digit scalar seq -> accept
  esac
```

In both `update-state.sh` files, the `_unread_for` byte-compare `[[ "$ts" > "$curkey" ]]` (`.codex/hooks/update-state.sh:210`, the `.claude/hooks/update-state.sh` mirror at `:211` — one line lower): a scalar `$cur` would byte-compare against a 20-char ISO filename token and over/under-count. Short-circuit a scalar cursor to `0` unread (ref-bus tracked):

```sh
  cur=$(tr -d '[:space:]' < "$cf")            # ISO 2026-..Z  OR  a scalar seq
  case "$cur" in
    *[!0-9]*) ;;                              # contains a non-digit -> ISO, fall through
    *) echo 0; return;;                       # all-digit scalar seq -> unread tracked on the ref-bus
  esac
  curkey=$(printf '%s' "$cur" | tr ':' '-')
  ...
```

- [ ] **Step 4: Run — verify it passes (suite still green)**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_legacy_cursor.py tests/unit/test_threeway_package.py -q` then a shell smoke of the two checkers against the live tree: `.venv/bin/python scripts/check_coordination.py >/dev/null && echo CC_OK` and `.venv/bin/python scripts/status.py mailbox >/dev/null && echo STATUS_OK`.
Expected: PASS — all six cursor tests green (the three `check_coordination` regex/future tests PLUS the three scalar-path tests: `status.count_unread`, the `consume-events --to` subprocess smoke, the `seat_status.mailbox` subprocess smoke — so every one of the 7 loosened parsers carries a non-vacuous scalar check). The existing ISO cursors in `coordination/mailbox/seen/*.txt` still satisfy `_CURSOR_RE` (the regex is a strict superset), so `check_coordination.py`/`status.py` stay green on the live tree. No `test_threeway_*` previously asserted `_CURSOR_RE`'s exact pattern (verify via grep), so none regress.

- [ ] **Step 5: Commit**

```bash
git add -- scripts/check_coordination.py scripts/status.py scripts/mailbox_monitor.py \
  .agents/skills/four-seat-protocol/scripts/seat_status.py \
  coordination/bin/consume-events .codex/hooks/update-state.sh .claude/hooks/update-state.sh \
  tests/unit/test_threeway_legacy_cursor.py
git commit -m "feat(threeway): loosen every cursor parser to accept a scalar seq (Slice 2.5 Phase C, atomic)" -- \
  scripts/check_coordination.py scripts/status.py scripts/mailbox_monitor.py \
  .agents/skills/four-seat-protocol/scripts/seat_status.py \
  coordination/bin/consume-events .codex/hooks/update-state.sh .claude/hooks/update-state.sh \
  tests/unit/test_threeway_legacy_cursor.py
```
(`Co-Authored-By` trailer per Conventions.)

### Task 12: ISO→seq cursor backfill + byte-reversible manifest

**Files:**
- Create: `threeway/cursor_backfill.py` (`total_order(sent_names) -> list[(ts, filename)]`; `iso_to_seq_map(sent_names, iso_cursors) -> dict[seat,int]`; `backfill(coord_root) -> None` rewrites `seen/<seat>.txt` to scalar + archives the manifest; `restore_from_manifest(coord_root) -> None`).
- Create (at runtime): `coordination/mailbox/.migration/cursor-backfill.json`.
- Test: `tests/unit/test_threeway_cursor_backfill.py` (create).

**Context:** Spec §6: the total order is `(filename ts, full filename)` over `sent/*.md` — filenames are unique even within a same-second group (the live tree has 13 same-second events), so the order is total and reproducible. Each seat's ISO high-water cursor maps to the **highest `seq` whose event ts ≤ the ISO cursor** (seq `0` if none — matching `advance_cursor`'s `seq==0` allowance, `refstore.py:240`). The manifest at `coordination/mailbox/.migration/cursor-backfill.json` archives the original ISO values + the ISO→seq map so rollback is a file restore (spec §8 D4). **Filename uniqueness is the single shared load-bearing invariant** (spec §5a) for both this total order and the §5a idempotency injectivity — the backfill must NOT silently collapse a same-second pair. **Do NOT reuse `check_coordination._dash`/`_colon` for the order key** — the §6 order keys on the *filename* ts token directly (dash form), which `_EVENT_NAME_RE.group("ts")` already yields; keep the order key the raw filename so the same-second tiebreak is exact.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_threeway_cursor_backfill.py`:

```python
"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_cursor_backfill.py -q"""
import json
from pathlib import Path

import pytest

from threeway.cursor_backfill import (
    total_order, iso_to_seq_map, backfill, restore_from_manifest,
)

# Three events; two share a SECOND (the same-second tiebreak must be total).
_NAMES = [
    "2026-06-17T19-55-31Z-operator-to-director-status.md",
    "2026-06-17T20-00-00Z-director-to-operator-decision.md",
    "2026-06-17T20-00-00Z-operator-to-director-ack.md",     # same second as above
]


def _seed(root: Path, cursors: dict):
    sent = root / "coordination" / "mailbox" / "sent"
    seen = root / "coordination" / "mailbox" / "seen"
    sent.mkdir(parents=True); seen.mkdir(parents=True)
    for n in _NAMES:
        # body is irrelevant to the backfill (it reads only sent/ FILENAMES + seen/ cursors)
        (sent / n).write_text("# x\n")
    for seat, iso in cursors.items():
        (seen / f"{seat}.txt").write_text(iso + "\n")
    return root


def test_total_order_is_total_under_same_second(tmp_path):
    order = total_order(_NAMES)
    # 3 distinct seqs despite a same-second collision (tiebreak = full filename)
    assert [fn for _, fn in order] == sorted(_NAMES)
    assert len(order) == 3


def test_iso_maps_to_highest_seq_at_or_before_cursor(tmp_path):
    # director cursor at 20:00:00Z -> highest event ts <= that.
    # The two 20:00:00Z events tiebreak by filename; "...decision.md" sorts before
    # "...operator-to-director-ack.md", so the at-or-before set is {seq1, seq2} and
    # the highest is seq 2 (decision) ... wait: ack also == 20:00:00Z, so both
    # qualify -> highest seq among ts<=cursor is the LAST of the two by filename.
    m = iso_to_seq_map(_NAMES, {"director": "2026-06-17T20:00:00Z"})
    order = total_order(_NAMES)                 # [(ts,fn)...] seq = idx+1
    last_le = max(seq for seq, (ts, fn) in enumerate(order, 1)
                  if ts <= "2026-06-17T20-00-00Z")
    assert m["director"] == last_le             # exact §6 rule, recomputed independently


def test_iso_with_no_event_at_or_before_is_seq_zero(tmp_path):
    m = iso_to_seq_map(_NAMES, {"operator": "2020-01-01T00:00:00Z"})
    assert m["operator"] == 0                   # seq-0 floor (advance_cursor allows 0)


def test_backfill_then_restore_is_byte_reversible(tmp_path):
    # 7a (byte-reversibility). MUTATION (documented): after backfill, flip one byte
    # of an archived ISO in the manifest, THEN restore -> the restored seen/<seat>.txt
    # bytes != the captured original -> the round-trip assertion flips RED.
    root = _seed(tmp_path, {"director": "2026-06-17T20:00:00Z",
                            "operator": "2026-06-17T19:55:31Z"})
    seen = root / "coordination" / "mailbox" / "seen"
    before = {p.name: p.read_bytes() for p in seen.iterdir()}
    backfill(root)
    # cursors are now scalar seqs
    assert (seen / "director.txt").read_text().strip().isdigit()
    restore_from_manifest(root)
    after = {p.name: p.read_bytes() for p in seen.iterdir()}
    assert after == before                      # byte-for-byte round trip

    # --- the documented single-byte mutation must break the round-trip ---
    # NB: restore_from_manifest restores from obj["original_bytes"][<filename>] — so the
    # mutation MUST perturb that field (NOT original_iso, which restore never reads, or
    # the mutation would be a no-op and this test would falsely pass on broken restore).
    backfill(root)
    man = root / "coordination" / "mailbox" / ".migration" / "cursor-backfill.json"
    obj = json.loads(man.read_text())
    raw = obj["original_bytes"]["director.txt"]          # latin-1 str of the EXACT bytes
    obj["original_bytes"]["director.txt"] = ("X" if raw[0] != "X" else "Y") + raw[1:]  # flip one byte
    man.write_text(json.dumps(obj))
    restore_from_manifest(root)
    assert (seen / "director.txt").read_bytes() != before["director.txt"]


def test_map_recomputes_purely_from_sent_and_order(tmp_path):
    # 7b (map reproducibility). MUTATION (documented): perturb one event ts so its seq
    # bucket changes -> the recomputed map diverges from the archived map -> RED.
    root = _seed(tmp_path, {"director": "2026-06-17T20:00:00Z"})
    backfill(root)
    man = json.loads((root / "coordination" / "mailbox" / ".migration"
                      / "cursor-backfill.json").read_text())
    sent_names = sorted(p.name for p in
                        (root / "coordination" / "mailbox" / "sent").iterdir())
    recomputed = iso_to_seq_map(sent_names, man["original_iso"])
    assert recomputed == man["iso_to_seq"]      # archived map == purely-recomputed map
```

- [ ] **Step 2: Run it — verify it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_cursor_backfill.py -q`
Expected: ERROR — `ModuleNotFoundError: No module named 'threeway.cursor_backfill'` (the module does not exist yet).

- [ ] **Step 3: Implement**

Create `threeway/cursor_backfill.py`:

```python
"""ISO→scalar-seq cursor backfill + byte-reversible manifest (Slice 2.5 §6, §8 D4).

Pure functions + two filesystem ops. NO refs/threeway/* writes (the ref-bus cursors
are materialized in the cutover, Task 13, via advance_cursor). The total order is
(filename-ts, full-filename) over sent/*.md — filenames are unique even within a
same-second group, so the order is total and reproducible from sent/ alone.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_TS = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)-")   # leading filename ts token
_MANIFEST = "coordination/mailbox/.migration/cursor-backfill.json"


def _sent_names(coord_root: Path) -> list[str]:
    d = coord_root / "coordination" / "mailbox" / "sent" \
        if (coord_root / "coordination").is_dir() else coord_root / "mailbox" / "sent"
    return sorted(p.name for p in d.iterdir() if p.name.endswith(".md"))


def total_order(sent_names: list[str]) -> list[tuple[str, str]]:
    """[(ts_token, filename)] in (ts, filename) order; seq = index+1. NB: tiebreak on
    the FULL filename keeps a same-second group total (the load-bearing invariant)."""
    keyed = []
    for n in sent_names:
        m = _TS.match(n)
        if not m:                                   # a non-event file in sent/ is a hard error
            raise ValueError(f"sent/ filename has no leading ts token: {n!r}")
        keyed.append((m.group(1), n))
    return sorted(keyed, key=lambda t: (t[0], t[1]))


def iso_to_seq_map(sent_names: list[str], iso_cursors: dict[str, str]) -> dict[str, int]:
    """seat -> highest seq whose event ts <= the seat's ISO cursor (0 if none)."""
    order = total_order(sent_names)
    out: dict[str, int] = {}
    for seat, iso in iso_cursors.items():
        iso_dash = iso[:11] + iso[11:].replace(":", "-")     # ISO colon -> filename dash form
        seq = 0
        for i, (ts, _fn) in enumerate(order, start=1):
            if ts <= iso_dash:
                seq = i
        out[seat] = seq
    return out


def _seen_dir(coord_root: Path) -> Path:
    base = coord_root / "coordination" if (coord_root / "coordination").is_dir() else coord_root
    return base / "mailbox" / "seen"


def _manifest_path(coord_root: Path) -> Path:
    base = coord_root / "coordination" if (coord_root / "coordination").is_dir() else coord_root
    return base / "mailbox" / ".migration" / "cursor-backfill.json"


def backfill(coord_root: Path) -> None:
    """Rewrite each seen/<seat>.txt ISO cursor to its scalar seq; archive the EXACT
    original bytes + the iso_to_seq map to the manifest (rollback = restore)."""
    seen = _seen_dir(coord_root)
    sent_names = _sent_names(coord_root)
    original_bytes = {p.name: p.read_bytes() for p in seen.iterdir() if p.suffix == ".txt"}
    original_iso = {p.stem: p.read_text().strip() for p in seen.iterdir() if p.suffix == ".txt"}
    seq_map = iso_to_seq_map(sent_names, original_iso)
    man = _manifest_path(coord_root)
    man.parent.mkdir(parents=True, exist_ok=True)
    man.write_text(json.dumps({
        "schema": "cursor-backfill/1",
        # EXACT original file bytes (latin-1 round-trippable) so restore is byte-perfect,
        # plus the human-readable stripped ISO + the recomputable map (the §8 7b check).
        "original_bytes": {k: v.decode("latin-1") for k, v in original_bytes.items()},
        "original_iso": original_iso,
        "iso_to_seq": seq_map,
    }, indent=2, sort_keys=True))
    for seat, seq in seq_map.items():
        (seen / f"{seat}.txt").write_text(f"{seq}\n")


def restore_from_manifest(coord_root: Path) -> None:
    """Byte-for-byte restore seen/*.txt from the archived manifest (rollback)."""
    obj = json.loads(_manifest_path(coord_root).read_text())
    seen = _seen_dir(coord_root)
    for fname, text in obj["original_bytes"].items():
        (seen / fname).write_bytes(text.encode("latin-1"))
```

NB traps: (1) the manifest archives **exact original bytes** (latin-1 round-trip) for the byte-perfect restore *and* the stripped `original_iso` for the §8 7b recompute — both are needed (7a needs bytes, 7b needs the ISO + map). (2) `iso_to_seq_map` is a pure function of `(sent_names, iso_cursors)` so the 7b test can re-derive it from `man["original_iso"]` and get the archived map back. (3) the ISO→dash conversion preserves the date part (`[:11]`) and only dashes the time part, matching `_EVENT_NAME_RE`'s ts token grammar.

- [ ] **Step 4: Run — verify it passes (suite still green)**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_cursor_backfill.py tests/unit/test_threeway_legacy_cursor.py -q`
Expected: PASS — all 5 backfill tests green; Task-11's cursor tests unaffected (different module). No production caller invokes `backfill()` yet (it runs only in the cutover, Task 13), so no other test is touched.

- [ ] **Step 5: Commit**

```bash
git add -- threeway/cursor_backfill.py tests/unit/test_threeway_cursor_backfill.py
git commit -m "feat(threeway): ISO->seq cursor backfill + byte-reversible manifest (Slice 2.5 §6)" -- threeway/cursor_backfill.py tests/unit/test_threeway_cursor_backfill.py
```

### Task 13: The cutover — preflight → 768 signed carrier appends → 6 cursor backfills → one authority-flip

**Files:**
- Create: `threeway/cutover.py` (`run_cutover(repo, coord_root, importer_key, *, force=False) -> CutoverResult`; tears down the partial events ref on any append failure; the authority-flip is one explicit act after all succeed).
- Test: `tests/unit/test_threeway_cutover.py` (create).

**Context:** Spec §5c + §8 clauses 5 + 8. The cutover, in order: (1) `preflight_bus_init(repo, force=force)` — `gitcas.py:231`, raises `BusInitRefusedError` over a pre-existing `refs/threeway/*`, **never deletes** (the `force` short-circuit is `if force: return` at `gitcas.py:243-244` — spec said :240-241, drifted; re-grep). (2) Project the legacy bus via the Phase-B `threeway.legacy_projector` into carrier `event_sent` Events in §6 total order; (3) `RefEventStore.append` each in order, signed by a designated **migration-importer** key. `event_sent` is **NOT** load-bearing (`threeway/__init__.py:26-31`), so `gate.verify_and_reduce` skips its signature entirely (`gate.py:38` — the `if ev.kind in LOAD_BEARING_KINDS:` guard) → **no `PublicKeyRegistry` entry needed** for the importer. (4) `advance_cursor` for all 6 seats from the Task-12 seq map. (5) On ANY append failure, tear down the partial events ref (`git update-ref -d refs/threeway/events`) so no reader sees a half-backfilled bus. (6) The authority-flip is the single explicit final act, only after all appends + 6 cursor advances succeed. **Rule #13 / do NOT touch:** do not add `event_sent` to `LOAD_BEARING_KINDS` (the carrier-bypass clause 8b depends on it staying out); do not edit `RefEventStore.append` or `preflight_bus_init` (consumed, not modified — spec §2). The §6 total-order projection is the Phase-B projector's contract; consume `legacy_projector.project(coord_root)` as it was built in Chunk on Phase B (it returns carrier Events already in total order with `brief_id="legacy-import"`, `subject_sha=sha256(filename)`).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_threeway_cutover.py` (own inline fixtures; reuse the preflight test's repo helpers verbatim):

```python
"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_cutover.py -q"""
import os
import subprocess

import pytest

from threeway import keys
from threeway.gitcas import BusInitRefusedError
from threeway.refstore import RefEventStore, EVENTS_REF
from threeway.cutover import run_cutover
from threeway import legacy_projector
from threeway.gate import verify_and_reduce
from threeway.envelope import Event, sign_event


def _env():
    e = dict(os.environ); e.pop("GIT_INDEX_FILE", None); return e


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], check=True,
                          capture_output=True, text=True, env=_env())


def _new_repo(tmp_path):
    r = tmp_path / "repo"; r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@e.st"); _git(r, "config", "user.name", "t")
    (r / "base.txt").write_text("base\n"); _git(r, "add", "-A"); _git(r, "commit", "-qm", "base")
    return r


_NAMES = [
    "2026-06-17T19-55-31Z-operator-to-director-status.md",
    "2026-06-17T20-00-00Z-director-to-operator-decision.md",
    "2026-06-17T20-00-00Z-coordinator-to-all-fyi.md",     # broadcast preserved as ONE event
]


def _seed_coord(root):
    sent = root / "coordination" / "mailbox" / "sent"; sent.mkdir(parents=True)
    seen = root / "coordination" / "mailbox" / "seen"; seen.mkdir(parents=True)
    for n in _NAMES:
        (sent / n).write_text(
            "# subj\n\n**From:** " + n[20:].split("-to-")[0].lstrip("-") +
            "\n**When:** " + n[:11] + n[11:20].replace("-", ":") + "\n\nbody\n")
    for s in ("director", "director2", "operator", "operator2", "coordinator", "coordinator2"):
        (seen / f"{s}.txt").write_text("2026-06-17T20:00:00Z\n")
    return root


def test_cutover_three_way_set_bijection(tmp_path):
    # CLAUSE 5: legacy sent set == projected set == post-backfill index/<seq> set.
    # MUTATION (documented): drop one sent/*.md before cutover -> the projected set and
    # the ref index/<seq> set both shrink by one while legacy != them -> bijection RED.
    r = _new_repo(tmp_path); root = _seed_coord(r)
    importer, _ = keys.generate_keypair()
    res = run_cutover(r, root, importer, force=False)
    legacy = set(_NAMES)
    projected = {ev.payload["source_filename"] for ev in legacy_projector.project(root)}
    store = RefEventStore(r)
    ref_files = {ev.payload["source_filename"] for ev in store.all_events()}
    assert legacy == projected == ref_files            # three-way bijection
    assert len(ref_files) == len(_NAMES)               # non-empty floor (no collapse)


def test_cutover_preflight_refuses_over_existing_ref_nondestructive(tmp_path):
    # CLAUSE 8a: pre-existing refs/threeway/events -> BusInitRefusedError + ref survives.
    # (Same shape as tests/unit/test_threeway_preflight.py.)
    r = _new_repo(tmp_path); root = _seed_coord(r)
    head = _git(r, "rev-parse", "HEAD").stdout.strip()
    _git(r, "update-ref", EVENTS_REF, head)            # stray prior bus state
    importer, _ = keys.generate_keypair()
    with pytest.raises(BusInitRefusedError):
        run_cutover(r, root, importer, force=False)
    assert _git(r, "rev-parse", EVENTS_REF).stdout.strip() == head   # NON-DESTRUCTIVE


def test_carrier_passes_gate_without_a_registered_importer_key(tmp_path):
    # CLAUSE 8b: an event_sent carrier signed by a NON-registered importer key still
    # passes verify_and_reduce (event_sent is NOT load-bearing -> gate skips it).
    # MUTATION (documented): adding "event_sent" to LOAD_BEARING_KINDS makes the gate
    # demand a registered signer -> "unknown signer seat" GateError -> RED. Asserted
    # below by constructing the SAME carrier and confirming the empty registry is OK.
    importer, _ = keys.generate_keypair()
    carrier = Event(bus_id="prod", id="legacy-0", seq=1,
                    schema_version="threeway/1",        # REQUIRED: envelope.py Event has
                                                        # no default for schema_version; omitting
                                                        # it raises TypeError at construction
                                                        # (before verify_and_reduce), making the
                                                        # clause-8b proof vacuous.
                    kind="event_sent",
                    sender="migration-importer", recipient="all",
                    signer="migration-importer:import:s1", payload={"k": "v"},
                    brief_id="legacy-import")
    sign_event(carrier, importer)                       # signed by an UNREGISTERED key
    empty_registry = tmp_path / "pub"; empty_registry.mkdir()
    state = verify_and_reduce([carrier], empty_registry, bus_id="prod")   # must NOT raise
    assert state is not None


def test_cutover_seeds_all_six_cursors(tmp_path):
    r = _new_repo(tmp_path); root = _seed_coord(r)
    importer, _ = keys.generate_keypair()
    run_cutover(r, root, importer, force=False)
    store = RefEventStore(r)
    # all 6 seats have a cursor in [0, head]; the highest-seq event head is len(_NAMES)
    for s in ("director", "director2", "operator", "operator2", "coordinator", "coordinator2"):
        assert 0 <= store.cursor_seq(s) <= len(_NAMES)
```

- [ ] **Step 2: Run it — verify it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_cutover.py -q`
Expected: ERROR — `ModuleNotFoundError: No module named 'threeway.cutover'` (and `run_cutover` undefined). The `test_carrier_passes_gate…` case may collect but fails first on the import.

- [ ] **Step 3: Implement**

Create `threeway/cutover.py`:

```python
"""The single authoritative cutover (Slice 2.5 §5c): preflight -> sign+append all
carriers in §6 total order -> backfill 6 cursors -> one authority-flip act. On ANY
append failure, tear down the partial events ref so no reader sees a half bus.

Consumes (never edits) the Slice-2 substrate: preflight_bus_init, RefEventStore,
advance_cursor; and the Phase-B legacy_projector + cursor_backfill.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass

from threeway import cursor_backfill, gitcas, legacy_projector
from threeway.gitcas import preflight_bus_init
from threeway.refstore import EVENTS_REF, RefEventStore

_SEATS = ("director", "director2", "operator", "operator2", "coordinator", "coordinator2")


@dataclass
class CutoverResult:
    appended: int
    cursors: dict
    authoritative: bool


def _teardown(repo) -> None:
    # NON-DESTRUCTIVE only of the partial NEW bus we were building — delete the events
    # ref so no reader sees a half-backfilled bus. (preflight already proved no PRIOR
    # state, so this only removes commits THIS run created.)
    subprocess.run(["git", "-C", str(repo), "update-ref", "-d", EVENTS_REF],
                   capture_output=True, env=gitcas._env(), check=False)


def run_cutover(repo, coord_root, importer_key, *, force: bool = False) -> CutoverResult:
    # (1) FAIL-CLOSED pre-check: refuses over any pre-existing refs/threeway/*, never
    #     deletes. force=True is an explicit operator acknowledgement (gitcas:243-244).
    preflight_bus_init(repo, force=force)

    # (2) project the legacy bus into carrier event_sent Events in §6 total order.
    carriers = legacy_projector.project(coord_root)        # already total-ordered

    store = RefEventStore(repo)
    appended = 0
    try:
        # (3) sign + append every carrier in order (importer key needs NO registry
        #     entry: event_sent is not load-bearing -> gate skips its signature).
        for ev in carriers:
            store.append(ev, importer_key)
            appended += 1
    except Exception:
        # (5) on ANY append failure, tear down the partial events ref.
        _teardown(repo)
        raise

    # (4) backfill all 6 seats' cursors from the §6 ISO->seq map. Compute the total order
    #     ONCE (it validates totality + raises on a non-event filename), then derive the
    #     ordered filename list for iso_to_seq_map from it — no recompute.
    carrier_names = [ev.payload["source_filename"] for ev in carriers]
    order = cursor_backfill.total_order(carrier_names)   # validates totality
    ordered_names = [fn for _, fn in order]
    seq_map = cursor_backfill.iso_to_seq_map(ordered_names, _read_iso_cursors(coord_root))
    cursors = {}
    try:
        for seat in _SEATS:
            seq = seq_map.get(seat, 0)
            store.advance_cursor(seat, seq)               # seq==0 allowed (refstore:240)
            cursors[seat] = store.cursor_seq(seat)
    except Exception:
        _teardown(repo)
        raise

    # ALSO rewrite the legacy seen/*.txt to scalar + archive the reversible manifest.
    cursor_backfill.backfill(coord_root)

    # (6) AUTHORITY FLIP = the single explicit act, only after ALL appends + cursors.
    #     (The marker/doctrine commit is the caller's; this returns the GO signal.)
    return CutoverResult(appended=appended, cursors=cursors, authoritative=True)


def _read_iso_cursors(coord_root) -> dict:
    seen = cursor_backfill._seen_dir(coord_root)
    return {p.stem: p.read_text().strip() for p in seen.iterdir() if p.suffix == ".txt"}
```

NB traps: (1) `legacy_projector.project` is the Phase-B contract — each carrier's `payload` carries `source_filename` (spec §5b field-1 / §5a); the three-way bijection keys on it. If the Phase-B projector named that field differently, re-grep `legacy_projector` and align (this is a cross-chunk seam — verify at exec). (2) `_teardown` deletes ONLY the events ref this run created (preflight proved no prior state), so it is non-destructive of any pre-existing bus. (3) the importer key is passed straight to `append`; `append` derives `public_hex` from it for its own idempotency self-check, which is fine — no registry needed because the **gate** (not the store) is what skips load-bearing verification. (4) **`schema_version` is REQUIRED on every carrier** — `envelope.py`'s `Event` declares `schema_version: str` with NO default, so a carrier built without it raises `TypeError` at construction (before any append). The Phase-B projector (Task 7) already stamps `schema_version="threeway/1"` on every Event it emits (verify via grep `schema_version` in `threeway/legacy_projector.py` at exec — it is at the Event(...) construction); `run_cutover` consumes those carriers as-is, so it inherits the stamp. Any HAND-BUILT carrier Event in a test (e.g. the clause-#8b test) MUST pass `schema_version="threeway/1"` explicitly.

- [ ] **Step 4: Run — verify it passes (suite still green)**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_cutover.py tests/unit/test_threeway_preflight.py tests/unit/test_threeway_refstore.py -q`
Expected: PASS — the 4 cutover tests green (bijection, preflight-refusal-nondestructive, carrier-bypass, 6 cursors). `test_threeway_preflight.py` and `test_threeway_refstore.py` are unaffected — `cutover.py` only *calls* `preflight_bus_init`/`RefEventStore`/`advance_cursor`, never edits them, and `LOAD_BEARING_KINDS` is unchanged so every existing gate test stays green.

- [ ] **Step 5: Commit**

```bash
git add -- threeway/cutover.py tests/unit/test_threeway_cutover.py
git commit -m "feat(threeway): cutover — preflight, signed carrier backfill, 6-cursor advance, single authority-flip (Slice 2.5 §5c)" -- threeway/cutover.py tests/unit/test_threeway_cutover.py
```

### Task 14: Chunk close — Phase-C cursor + cutover verification gate (NO commit)

> Verification-only gate before Chunk 4 (doc-sync / ADR-034). No commit.

- [ ] Run the Phase-C pytest files: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_legacy_cursor.py tests/unit/test_threeway_cursor_backfill.py tests/unit/test_threeway_cutover.py -q` → all PASS.
- [ ] Run the full threeway suite to confirm no Phase-C regression: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_*.py -q` → all PASS (Slice-1 + Slice-2 + Phase-A/B/C additions).
- [ ] Run `.venv/bin/python scripts/ci_smoke.py` → OK (no stale same-line anchors; the live `coordination/` checkers still green — `check_coordination.py`/`status.py` against the real tree with its current ISO cursors, since the loosened regex is a strict superset).
- [ ] Run `.venv/bin/python scripts/check_no_ceremony.py` → clean (R1: zero new `xfail`/`skip`/`importorskip` — every Phase-C test proves non-vacuity by the documented single-fact mutation, never a pin).
- [ ] (No commit; this is the verification gate before Chunk 4.)

---

## Chunk 4: Docs + final gate (ADR-034, §13A doc-sync, whole-implementation review)

> Sequenced LAST — runs only after Chunks 1–3 are green, because ADR-034's Consequences and §13A's new-module anchors must describe code that already exists on the branch. Task 15 edits three docs (`DECISIONS.md`, `ARCHITECTURE.md`, the Slice 2.5 stub) — one implementer, sequential (R-ORCH: never two implementers on a shared file; both doc tasks touch the docs tree, so they do not parallelize). Task 16 is verification-only (no production edit, optional docs-fix commit) and runs the §8 acceptance gate end-to-end.

### Task 15: ADR-034 + `ARCHITECTURE.md §13A` doc-sync + mark the Slice 2.5 stub SUPERSEDED

**Files:**
- Modify: `DECISIONS.md` (APPEND ADR-034 after ADR-033, which ends at `DECISIONS.md:~1610`; re-grep `grep -n "^## ADR-0" DECISIONS.md | tail -1` — the max is **ADR-033**, so yours is **ADR-034**)
- Modify: `ARCHITECTURE.md §13A` (`ARCHITECTURE.md:1699-1770`; add the two new modules + the cursor-format note; update the `152 passed` count line `:1768` and the `*Last verified:*` footer `:1770`)
- Modify: `docs/superpowers/plans/2026-06-19-cross-provider-seat-topology-slice2.5-legacy-bus-migration.md:1-7` (the status banner)
- Test: `scripts/ci_smoke.py` (this is a `docs(threeway)` task; its "test" is the same-line doc-anchor gate staying green — `ci_smoke` runs `check_doc_claims.run(["ARCHITECTURE.md"], …)` at `scripts/ci_smoke.py:82`, a **hard** gate over `ARCHITECTURE.md` only)

**Context:** Slice 2 left §13A documenting only the Slice-2 bus (`RefEventStore`, gate, envelope). This slice adds two new read-only modules — `threeway/legacy_projector.py` and `threeway/divergence.py` (created in Chunk 2/3 of this plan; both absent on `main` today, verified `ls threeway/legacy_projector.py threeway/divergence.py` → "No such file or directory") — plus the ISO→scalar cursor-format change at `_CURSOR_RE` (`scripts/check_coordination.py:63`, currently `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`, ISO-only). §13A must describe them or the truth file drifts. The cursor write still uses `gitcas.cas_create_or_update_ref` (`threeway/gitcas.py:171`) via `advance_cursor` (`threeway/refstore.py:222`) — both already-documented anchors; do NOT re-anchor those to new line numbers without re-grepping. **The ci_smoke doc-claim gate only checks SAME-LINE `symbol (path:N)` anchors in `ARCHITECTURE.md` (not the spec, not DECISIONS.md, not markdown-link or comma-range anchors — `doc_checker_same_line_blindspot`); every new file:line you add to §13A must be a same-line `(path:N)` form and must resolve against the then-current HEAD.** **NB (append-only ADR discipline): never edit a prior ADR — ADR-030/031/032/033 stay byte-frozen; ADR-034 is a pure append.**

- [ ] **Step 1: Run the doc gate FIRST to capture the pre-edit baseline (and prove it will flag drift)** — before adding any new-module anchors, edit §13A to insert the two new modules **with deliberately stale line numbers** is NOT the approach; instead, write the real §13A prose (Step 3) but FIRST establish the gate behavior. Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
```

**Run the bare `.venv/bin/python scripts/ci_smoke.py` with the `CI` env var UNSET** — the §13A doc-anchor hard-fail (`ci_smoke.py:~85`) only fires (exit non-zero) when `CI` is UNSET; under CI (`CI` set, e.g. GitHub Actions) the same drift is downgraded to a non-blocking WARNING (`ci_smoke.py:86-92`), so the gate would NOT fail there. Run it locally with `CI` unset (e.g. `env -u GIT_INDEX_FILE -u CI .venv/bin/python scripts/ci_smoke.py`) so the drift is a hard gate.

Expected at this point (pre-edit, on a Chunks-1–3-green branch, `CI` unset): **OK** — §13A as inherited still resolves (`RefEventStore (threeway/refstore.py:80)` etc. all live). This baseline proves the gate is *active* so that a later stale anchor will be caught. Then add ONE intentionally-wrong same-line anchor to §13A (e.g. `legacy_projector (threeway/legacy_projector.py:9999)`) and re-run ci_smoke (still `CI` unset) — **Expected: FAIL with `DOC-ANCHOR DRIFT: … ARCHITECTURE.md`** (`scripts/ci_smoke.py:93`). This is the non-vacuity proof: the gate flips RED on exactly one wrong anchor line, GREEN when corrected. Document this in a one-line comment in the commit body; revert the deliberately-wrong anchor before Step 3.

- [ ] **Step 2: Verify the failing state is the doc gate, not a code error** — confirm the FAIL is the `check_doc_claims` drift path and not an unrelated smoke breakage:

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/check_doc_claims.py ARCHITECTURE.md
```

Expected: **non-zero exit + an `out_of_bounds` Drift naming `… → threeway/legacy_projector.py:9999`** (`check_doc_claims.py`'s Drift `kind` for a line beyond the file's bounds is `out_of_bounds`, not `bad_line` — there is no `bad_line` term in the checker) — proving the gate reads the same-line anchor and the number is what it checks (mutate the number → it flips; this is the single-fact mutation per ADR-028).

- [ ] **Step 3: Implement — append ADR-034, sync §13A, banner the stub**

**3a — APPEND ADR-034 to `DECISIONS.md`** (after ADR-033's last line; do not touch ADR-033). Mirror the ADR-031 shape (Status / Context / Decisions / Consequences / Evidence / Cross-refs):

```markdown
## ADR-034 — Cross-provider seat topology Slice 2.5: legacy `coordination/` mailbox migrated onto `refs/threeway/events` as carrier events, in-memory shadow, single authority-flip cutover; coordinator + coordinator2 become receiving seats

- **Status:** ACCEPTED (Slice 2.5 implemented per the design spec
  `docs/superpowers/specs/2026-06-20-threeway-slice2.5-legacy-bus-migration-design.md` and the plan
  `docs/superpowers/plans/2026-06-20-cross-provider-seat-topology-slice2.5-legacy-bus-migration.md`).
  Discharges **ADR-031 Decision 8** (the D-B deferral of the legacy-mailbox migration). The §11 boundary
  to plan/execute this was satisfied by Slice 2's green gate (`152 passed`, merged at `2a932ac0`).
  Slice 3 (`co_sign_satisfied` true for T2/T3 — `threeway/tier.py:32-43`) remains deferred.
- **Context:** ADR-030/031 shipped the additive `threeway/` ref-bus but left the LIVE human-operated
  markdown mailbox (`coordination/`, the `send-event`/`consume-events`/`check_coordination.py`/`status.py`
  bus the 4-seat campaign runs on — 768 `sent/*.md` events) on the old substrate. The legacy vocabulary
  (`coordination/mailbox/kinds.txt`, 25 human-coordination kinds) is 100% disjoint from the threeway
  governance kinds, so `reduce()` (`threeway/reducer.py`, no `else`) would silently drop every legacy
  event if folded through it. The migration also had to make `coordinator` (today send-only) and a new
  `coordinator2` first-class RECEIVING seats without ever opening a dual-write-authority window on a bus
  with seats actively running.
- **Decisions:**
  1. **Carrier-event model — legacy events ride the existing non-load-bearing `event_sent` kind, never
     `reduce()`.** Each `sent/*.md` is projected to a `threeway.envelope.Event` with `kind="event_sent"`
     (already in `THREEWAY_KINDS`, `threeway/__init__.py`); the original legacy kind, subject, `When:`,
     `Cursor at send:`, recipient, and full body bytes go into `payload`. No new kinds, no `kinds.txt`
     change, no governance semantics. Because `event_sent` is NOT in `LOAD_BEARING_KINDS`, the gate's
     `verify_and_reduce` (`threeway/gate.py:38`) never reads a carrier's signer — the migration-importer
     identity needs no `PublicKeyRegistry` entry, and a carrier structurally cannot masquerade as a
     governance attestation.
  2. **`subject_sha = sha256(source_filename)` to keep idempotency INJECTIVE.** `idempotency_key`
     (`threeway/envelope.py`) is `sha256(sender:kind:subj:payload_digest)`; without a per-file subject the
     ~125 byte-identical same-`(sender,kind)` `status`/`ack` events would collide and the cutover would
     drop one. Filenames are unique even within a same-second group, so this is the single shared
     load-bearing invariant under both injectivity and the §6 total order. `brief_id="legacy-import"`
     namespaces all 768 carriers under `events/legacy-import/`.
  3. **"Shadow" is an IN-MEMORY projection (D2) — zero `refs/threeway/events` writes until cutover.** The
     projector (`threeway/legacy_projector.py`) is a pure read-only function; the divergence-check
     (`threeway/divergence.py`) compares the projected event SET against the live mailbox on the RAW set
     (never `reduce()`/`EffectiveState`). "No dual-write authority" is therefore STRUCTURAL, not merely
     policy — pinned observable: a full shadow leaves `gitcas.rev_parse(repo, EVENTS_REF)` unchanged
     (design §8 clause #6).
  4. **Single authority-flip cutover (D2/§5c).** After ≥1 zero-divergence shadow cycle + a one-pair canary:
     fail-closed `preflight_bus_init(force=False)` (`threeway/gitcas.py:231`) → 768 sequential
     `RefEventStore.append()` carrier appends in the `(filename ts, full filename)` total order → 6
     cursor backfills → ONE explicit authority-flip act. The 768 appends are non-atomic CAS, so a failure
     tears down the partial `refs/threeway/events` prefix (no reader sees a half-backfilled bus). Before
     the flip, legacy `sent/` is authoritative; after it, the ref-bus is, and `sent/` is RETAINED
     read-only as the rollback source (the forward projector is lossy w.r.t. markdown framing, so rollback
     re-designates the retained tree + restores the cursor manifest — no byte-regeneration claim).
  5. **ISO → scalar `seq` cursors, reversible via a committed manifest (D4).** Each seat's ISO high-water
     `seen/<seat>.txt` maps to the highest `seq` whose event ts ≤ the ISO cursor under the total order;
     `advance_cursor` (`threeway/refstore.py:222`) materializes `refs/threeway/cursors/<seat>`. `_CURSOR_RE`
     (`scripts/check_coordination.py:63`) and the other cursor parsers loosen to accept the scalar in
     lockstep, ATOMICALLY in Phase C (no intermediate commit ever has a scalar cursor under an ISO-only
     regex). `coordination/mailbox/.migration/cursor-backfill.json` archives the original ISO values +
     the ISO→seq map, so restoring it rewrites `seen/*.txt` byte-for-byte.
  6. **coordinator + coordinator2 become RECEIVING seats; the ~12-copy roster consolidates to one root
     (D1).** `scripts/protocol_mailbox.py` is the single Python roster root (`RECEIVING_SEATS`); every
     Python copy imports it; the 4 shell whitelist sites stay hand-synced but are guarded by a
     token-extraction test asserting shell-list == Python root. The send-only special-casing for
     coordinator is removed in lockstep with the prose (D5: prose-matches-code is a repo invariant).
     coordinator2's cursor seeds at the bus head (zero spurious backlog); `self`-address stays refused.
- **Consequences:** the live campaign bus is now event-sourced on the same substrate as the governance
  bus, with `coordinator`/`coordinator2` addressable both ways. There is no dual-write window at any
  phase (Phase A purely additive; shadow read-only in-memory; cutover a single post-success flip).
  Rollback is the retained read-only `sent/` + the reversible cursor manifest. The two new modules are
  ADDITIVE and read-only — they import the Slice-2 API and never edit `refstore`/`gitcas`/`envelope`/
  `reducer`/`gate`/`tier`. Slice 3 is now the only remaining slice.
- **Evidence:**
  `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_*.py -q` → green (Slice 1 +
  Slice 2 + the Slice-2.5 roster/projector/divergence/cutover suites; exact count recorded by Task 16).
  `scripts/ci_smoke.py` → OK (no ceremony; §13A doc-anchor gate green). `scripts/check_no_ceremony.py`
  → clean (zero xfail/skip/importorskip introduced).
- **Cross-refs:** **ADR-031** (Slice 2 — this slice discharges its Decision 8 / D-B deferral); design spec
  `docs/superpowers/specs/2026-06-20-threeway-slice2.5-legacy-bus-migration-design.md`; plan
  `docs/superpowers/plans/2026-06-20-cross-provider-seat-topology-slice2.5-legacy-bus-migration.md`;
  the now-SUPERSEDED tracking stub
  `docs/superpowers/plans/2026-06-19-cross-provider-seat-topology-slice2.5-legacy-bus-migration.md`;
  ARCHITECTURE.md §13A.5 (legacy-bus projection); `threeway/legacy_projector.py`, `threeway/divergence.py`.
```

**3b — Sync `ARCHITECTURE.md §13A`.** Add a new subsection §13A.5 after §13A.4 (`ARCHITECTURE.md:1758-1770`), and update the count + footer. Use SAME-LINE `symbol (path:N)` anchors only (re-grep each `:N` against the then-current HEAD — Chunks 1–3 add lines above these sites, so the projector/divergence/`_CURSOR_RE` numbers WILL differ from this snapshot; `grep -n` them at exec time):

```markdown
### 13A.5 Legacy mailbox projection — `legacy_projector` + `divergence` (Slice 2.5)

The live `coordination/` markdown campaign bus is migrated onto `refs/threeway/events` as
**carrier events**. `def project_events` (`threeway/legacy_projector.py:N`) is a pure read-only
function: each `coordination/mailbox/sent/<ts>-<from>-to-<to>-<kind>.md` becomes a
`threeway.envelope.Event` with `kind="event_sent"` (the non-load-bearing carrier — the gate skips
it, `reduce()` never folds it), the original kind/subject/body carried in `payload`,
`subject_sha=sha256(source_filename)` (so idempotency stays injective over byte-identical events),
and `brief_id="legacy-import"`. `def check_divergence` (`threeway/divergence.py:N`) compares the
projected event SET against the live mailbox on the RAW set (never `reduce()`), with a non-empty
floor (`projected count == live sent count`). Neither module writes `refs/threeway/events`; the bus
is written ONCE, at the cutover (`preflight_bus_init` → 768 ordered `append`s → 6 cursor backfills →
a single authority-flip), with the retained read-only `sent/` as rollback.

**Cursor format (Slice 2.5):** cursors migrate ISO→scalar `seq`. `_CURSOR_RE`
(`scripts/check_coordination.py:N`) loosens from ISO-only to accept the scalar in lockstep with the
other parsers; `advance_cursor` (`threeway/refstore.py:222`) materializes
`refs/threeway/cursors/<seat>` via the LOCAL `cas_create_or_update_ref` (`threeway/gitcas.py:171`)
exactly as in §13A.1. `coordination/mailbox/.migration/cursor-backfill.json` archives the original
ISO values + the ISO→seq map for byte-reversible rollback. `coordinator` and `coordinator2` are now
first-class RECEIVING seats; the ~12-copy seat roster consolidates to the single root
`scripts/protocol_mailbox.py` plus a shell-sync guard. See `DECISIONS.md` ADR-034.
```

Then update the count line `ARCHITECTURE.md:1768` (`Slice 1 + Slice 2 together: \`152 passed\`.`) to the new Slice-1+2+2.5 total Task 16 records, and bump the footer `*Last verified: 2026-06-19*` (`ARCHITECTURE.md:1770`) to the execution date.

**3c — Mark the Slice 2.5 stub SUPERSEDED.** In `docs/superpowers/plans/2026-06-19-cross-provider-seat-topology-slice2.5-legacy-bus-migration.md`, insert a one-line status banner immediately under the H1 (replacing the `> **Status: DEFERRED / NOT STARTED.**` lead of the existing blockquote — keep the rest of the blockquote intact):

```markdown
> **Status: SUPERSEDED.** The full design + TDD plan now live in
> `docs/superpowers/specs/2026-06-20-threeway-slice2.5-legacy-bus-migration-design.md` and
> `docs/superpowers/plans/2026-06-20-cross-provider-seat-topology-slice2.5-legacy-bus-migration.md`
> (this stub's edit-site inventory was ~3× undercounted; see the design spec §4). Retained for history.
```

- [ ] **Step 4: Run — verify the doc gate is green (ci_smoke OK) and no anchor drifted**

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
env -u GIT_INDEX_FILE .venv/bin/python scripts/check_doc_claims.py ARCHITECTURE.md
```

Expected: ci_smoke **OK** and `check_doc_claims` exit 0 — every new same-line anchor in §13A.5 (`legacy_projector.py:N`, `divergence.py:N`, `check_coordination.py:N`, the already-live `refstore.py:222`/`gitcas.py:171`) resolves at HEAD. Existing tests are unaffected: this task touches only `.md` files (no `tests/`, no `threeway/` code), so the pytest suite cannot change. (If `check_doc_claims --fix` would rewrite a number, you mis-grepped a `:N` — fix the prose to the real line, do NOT let `--fix` blanket-rewrite, since it can churn unrelated anchors.)

- [ ] **Step 5: Commit**

```bash
git add -- DECISIONS.md ARCHITECTURE.md docs/superpowers/plans/2026-06-19-cross-provider-seat-topology-slice2.5-legacy-bus-migration.md
git commit -m "docs(threeway): ADR-034 + ARCHITECTURE.md §13A.5 legacy-bus projection; supersede the Slice 2.5 stub" -- DECISIONS.md ARCHITECTURE.md docs/superpowers/plans/2026-06-19-cross-provider-seat-topology-slice2.5-legacy-bus-migration.md
```

(Co-Authored-By trailer per the plan's "Conventions for every task".)

### Task 16: final gate — full §8 acceptance run + whole-implementation two-stage review (verification only)

**Files:** none modified by default. Verification-only; an optional `docs(threeway):` commit ONLY if review surfaces a stale doc anchor (re-run Task 15 Step 4 before any such commit).

**Context:** This is the §8 acceptance gate for the whole slice. It does not write production code — it proves the nine §8 clauses are met by the tasks/tests already landed, runs the repo-doctrine gates (`ci_smoke`, `check_no_ceremony`), confirms no `package.json`/`package-lock.json` drift (the pre-existing unrelated working-tree change must never be swept in — see the plan conventions), and gates the two-stage whole-implementation review (spec-compliance vs design spec §8 + code-quality). **Spec §11 boundary: this gate green is the prerequisite before Slice 3 is planned** — do not plan Slice 3 until every clause below is GREEN.

- [ ] **Step 1: Run the full threeway suite** (the glob the gate uses — covers Slice 1 + Slice 2 + every Slice-2.5 file from Chunks 1–3):

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_*.py -q
```

Expected: **all PASS** (Slice-1+2's 152 plus the new `test_threeway_legacy_roster.py` / `_projector.py` / `_divergence.py` / `_cutover.py` cases). Record the exact passing count here and back-fill it into ADR-034's Evidence block + `ARCHITECTURE.md:1768` if Task 15 left it as "recorded by Task 16" (re-run Task 15 Step 4's doc gate after any such edit).

- [ ] **Step 2: Run the repo-doctrine gates** (§8 clause #9) — run `ci_smoke` with the `CI` env var UNSET so the §13A doc-anchor drift is a HARD fail (`ci_smoke.py:~85`); under CI (`CI` set) that drift is only a non-blocking WARNING (`:86-92`) and would not block here:

```bash
env -u GIT_INDEX_FILE -u CI .venv/bin/python scripts/ci_smoke.py
env -u GIT_INDEX_FILE .venv/bin/python scripts/check_no_ceremony.py
```

Expected: ci_smoke **OK** (with `CI` unset, so the doc-anchor gate is hard); `check_no_ceremony.py` **clean** — R1 zero `xfail`/`skip`/`importorskip` across the new suite (this slice introduces none), R3 gate-executes, R4 ci-runxfail. A non-zero exit here means a ceremony violation slipped in (or a §13A anchor drifted) — block the gate.

- [ ] **Step 3: Confirm no `package.json`/`package-lock.json` drift**:

```bash
git status --porcelain -- package.json package-lock.json
```

Expected: **empty output** (the pre-existing unrelated change was never staged into any task commit). If non-empty, a task swept it in — reset those paths and re-verify before declaring the gate met.

- [ ] **Step 4: §8 acceptance-clause → proof coverage map.** Confirm each design-spec §8 clause maps to a landed, mutation-proven test (every test's single-fact mutation is documented in its own comment per ADR-028). This table IS the gate's audit trail:

| §8 clause | Observable / test (mutation that flips it RED) |
|---|---|
| **1 — Roster completeness (behavioral)** | `test_threeway_legacy_roster.py`: import each Python site, assert its live roster == `protocol_mailbox.RECEIVING_SEATS` incl. coordinator2; drive a `-to-coordinator2-` input through non-importable entry points. *Mutation:* drop coordinator2 from one real tuple/arm → import-compare or accept-test flips RED. |
| **2 — Shell↔Python sync guard (token extraction)** | `test_threeway_legacy_roster.py`: parse the FROM/TO/ROLE case-arm TOKENS from `send-event`/`consume-events`/both `update-state.sh`, assert == root. *Mutation:* drop coordinator2 from the `send-event` TO arm only (leave the usage string) → RED. |
| **3 — Legacy checkers green WITH staged coord/coord2 traffic** | `test_threeway_legacy_roster.py`: real `-to-coordinator2-` envelope + seeded `seen/coordinator2.txt` in a fixture mailbox → `check_coordination.py`/`status.py` exit 0, no FATAL. *Mutation:* remove coordinator2 from `_EVENT_NAME_RE` or delete the seeded cursor → `bad_filename`/`cursor_missing` FATAL. |
| **4 — Divergence zero-drift on the raw SET** | `test_threeway_divergence.py`: §5b field contract over a full projected cycle + non-empty floor. *Mutation:* perturb one event's `to`/body → field-drift reported RED. |
| **5 — Reconciliation set-bijection (3 points)** | `test_threeway_cutover.py`: `sent/*.md` set == projected set == post-backfill `index/<seq>` set. *Mutation:* drop/duplicate one `sent/*.md` → three-way bijection breaks RED. |
| **6 — No dual-write (pinned observable)** | `test_threeway_no_dual_write.py` (Task 9): `before = rev_parse(EVENTS_REF)`; full shadow; assert unchanged; + monkeypatch `gitcas.push_cas` AND `cas_create_or_update_ref` to raise, shadow completes. *Mutation:* projector calls `append()` once → both flip RED. |
| **7 — Cursor backfill (reversible + reproducible)** | `test_threeway_cursor_backfill.py` (Task 12): 7a manifest round-trips `seen/*.txt` byte-for-byte (*mutation:* flip one byte of `original_bytes[<file>]` in the manifest → restored ≠ original); 7b recompute ISO→seq from `sent/*.md` + total order == archived map (*mutation:* perturb one ts → map diverges). |
| **8 — Fail-closed init + carrier verification bypass** | `test_threeway_cutover.py`: (a) pre-existing `refs/threeway/events` → `preflight_bus_init(force=False)` raises `BusInitRefusedError`, ref still resolves; (b) carrier signed by a non-registered importer key passes `verify_and_reduce`. *Mutation:* add `event_sent` to `LOAD_BEARING_KINDS` → gate now demands a registered signer → RED. |
| **9 — Smoke + ceremony** | Step 2 above: `ci_smoke.py` OK + `check_no_ceremony.py` clean. *Mutation:* introduce one `pytest.mark.skip` → R1 RED. |

Any clause without a landed mutation-proven test is a gate MISS — do not pass the gate.

- [ ] **Step 5: Whole-implementation two-stage review.** Dispatch a fresh **Opus** spec-compliance reviewer (does the landed diff satisfy design spec §8 clauses 1–9, the §4 edit-site surface completeness, the §5 carrier model, and the D1–D5 decisions?) followed by a fresh **Opus** code-quality reviewer (the two new modules' read-only invariant, no edit to the Slice-2 `threeway/` internals, Rule #13 sibling-completeness across the roster copies, no leaked scratch index files). Both pass before declaring the slice gate met. **State explicitly in the review wrap: Spec §11 boundary — this gate green is the prerequisite before Slice 3 (`co_sign_satisfied` T2/T3) is planned.**

(No commit unless review surfaced a doc-anchor fix — then re-run Task 15 Step 4 first, and commit `docs(threeway):` with explicit pathspec.)

---

## Spec §11 boundary note

Slice 2.5's gate must be **green before Slice 3 is planned**. The Slice 2.5 DoD is the nine §8 acceptance clauses mapped in Task 16 Step 4 (roster completeness; shell↔Python sync; legacy checkers green with coord/coord2 traffic; raw-set divergence zero-drift; three-point set-bijection; no-dual-write pinned observable; reversible+reproducible cursor backfill; fail-closed init + carrier verification bypass; smoke+ceremony), each mutation-proven non-vacuous per ADR-028. After this gate passes — and only then — **Slice 3** (the strategic loop: dual chief, overseer brief distribution, T2 other-pair-operator `co_sign`, T3 `re_verify` + two `human_approval`, making `co_sign_satisfied` return `True` for T2/T3 at `threeway/tier.py:32-43`) is planned, per the §11 boundary rule.

## Execution handoff

After this plan is reviewed and **user-signed-off** (it is PLANNING ONLY until then): it runs via **superpowers:subagent-driven-development** — a fresh **Opus** implementer per task + a two-stage review (spec-compliance → code-quality) after each chunk, in a fresh worktree. This slice edits the LIVE 4-seat campaign bus (`coordination/`), so execution runs when bus activity is quiet and re-anchors on git refs before every action (`env -u GIT_INDEX_FILE` on every git-touching test; expect `git status`/`diff` to lie under peer activity — verify against `git show HEAD:<path>`). Re-read the Slice-2 execution handoff for the worktree `.venv` symlink pattern and the `env -u GIT_INDEX_FILE` test discipline. Do **not** start execution without explicit approval.
