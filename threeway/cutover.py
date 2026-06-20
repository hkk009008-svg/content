"""The single authoritative cutover (Slice 2.5 §5c): preflight -> sign+append all
carriers in §6 total order -> backfill 6 cursors -> one authority-flip act. On ANY
append/cursor failure, tear down the partial events ref so no reader sees a half bus.

Consumes (never edits) the Slice-2 substrate: preflight_bus_init, RefEventStore,
advance_cursor; and the Phase-B legacy_projector + cursor_backfill. Pure composition.

API seam (verified at exec, diverged from the plan's snapshot): the Phase-B
`legacy_projector.project()` consumes the `sent/` directory DIRECTLY (not a coord
root), while `cursor_backfill` resolves `coordination/mailbox` from a coord root via
`_mailbox_base`. run_cutover takes the coord root and bridges the two: it derives the
sent/ dir from the root with the SAME `_mailbox_base` logic cursor_backfill uses, so
the projector + backfill can never disagree about which mailbox they are migrating.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass

from threeway import cursor_backfill, gitcas, legacy_projector
from threeway.gitcas import preflight_bus_init
from threeway.refstore import EVENTS_REF, RefEventStore

_SEATS = ("director", "director2", "operator", "operator2", "coordinator", "coordinator2")


def _cursor_ref(seat: str) -> str:
    # MUST match RefEventStore._cursor_ref (refstore.py:200) EXACTLY — the snapshot
    # below restores/deletes the very refs advance_cursor writes. There is no shared
    # CURSORS_REF_PREFIX constant, so this f-string mirrors that literal by hand;
    # if refstore's cursor-ref scheme ever changes, this must change in lockstep.
    return f"refs/threeway/cursors/{seat}"


@dataclass
class CutoverResult:
    appended: int
    cursors: dict[str, int]
    # all appends + cursors succeeded; the caller MAY now commit the authority-flip
    # marker. NOT the authority flip itself (that is the caller's marker commit) —
    # this is a precondition / GO signal only.
    ready_to_flip: bool


def _sent_dir(coord_root):
    # SINGLE source of truth for the mailbox location, shared with cursor_backfill, so
    # the projection (this dir) and the backfill (seen/ under the same base) can never
    # diverge across the two layouts (root-containing-coordination OR root-is-coordination).
    return cursor_backfill._mailbox_base(coord_root) / "sent"


def _read_iso_cursors(coord_root) -> dict:
    seen = cursor_backfill._seen_dir(coord_root)
    return {p.stem: p.read_text().strip() for p in seen.iterdir() if p.suffix == ".txt"}


def _snapshot_refs(repo) -> dict:
    # Capture the PRE-RUN OID of every ref this cutover may write (the events ref + all
    # 6 cursor refs), so _teardown can restore EXACT prior state on any failure — not
    # blind-delete. None marks a ref that did not exist pre-run. This is what makes
    # teardown non-destructive even under force=True, where preflight_bus_init
    # SHORT-CIRCUITS (gitcas.py:243-244) and does NOT prove the bus was absent: a
    # pre-existing refs/threeway/events is exactly the force=True "acknowledge it" case.
    snap = {EVENTS_REF: gitcas.rev_parse(repo, EVENTS_REF)}
    for seat in _SEATS:
        ref = _cursor_ref(seat)
        snap[ref] = gitcas.rev_parse_any(repo, ref)   # cursor refs point at a BLOB, not a commit
    return snap


def _teardown(repo, snapshot: dict) -> None:
    # NON-DESTRUCTIVE: restore every ref to its captured PRE-RUN state. A ref that did
    # not exist pre-run (oid is None) is deleted (it can only hold commits THIS run made);
    # a ref that DID exist is reset to its prior OID (so a pre-existing bus under force=True
    # survives a mid-cutover failure intact). A failed RESTORE is surfaced (check=True) —
    # silently leaving a ref at a half-built state would defeat the non-destructive intent;
    # a delete of an absent ref stays best-effort (check=False).
    for ref, oid in snapshot.items():
        if oid is None:
            subprocess.run(["git", "-C", str(repo), "update-ref", "-d", ref],
                           capture_output=True, env=gitcas._env(), check=False)
        else:
            subprocess.run(["git", "-C", str(repo), "update-ref", ref, oid],
                           capture_output=True, env=gitcas._env(), check=True)


def run_cutover(repo, coord_root, importer_key, *, force: bool = False) -> CutoverResult:
    """Operator note: at live scale (~768 events) the append loop is O(n^2) — RefEventStore
    re-scans every prior event for idempotency on EACH append — so it runs ~50 min with NO
    progress output. That is EXPECTED, not a hang; do not abort it as stuck."""
    # (1) FAIL-CLOSED pre-check: refuses over any pre-existing refs/threeway/*, never
    #     deletes. force=True is an explicit operator acknowledgement (gitcas:243-244).
    preflight_bus_init(repo, force=force)

    # (1b) Snapshot the PRE-RUN OID of the events ref + all 6 cursor refs BEFORE we touch
    #      anything, so teardown restores exact prior state (not blind-delete) on failure.
    #      Required under force=True: preflight short-circuits there, so a pre-existing bus
    #      is NOT proven absent and an unconditional teardown would DELETE it.
    snapshot = _snapshot_refs(repo)

    # (2) project the legacy bus into carrier event_sent Events in §6 total order. The
    #     projector reads the sent/ dir directly + already returns events total-ordered.
    sent_dir = _sent_dir(coord_root)
    carriers = legacy_projector.project(sent_dir)

    store = RefEventStore(repo)
    appended = 0
    try:
        # (3) sign + append every carrier in order (importer key needs NO registry
        #     entry: event_sent is not load-bearing -> gate skips its signature).
        for ev in carriers:
            store.append(ev, importer_key)
            appended += 1
    except Exception:
        # (5) on ANY append failure, restore every ref to its pre-run snapshot.
        _teardown(repo, snapshot)
        raise

    # (4) backfill all 6 seats' cursors from the §6 ISO->seq map. total_order over the
    #     carrier filenames validates totality (raises on a non-event filename) before we
    #     advance any cursor; iso_to_seq_map recomputes the same order internally from the
    #     raw names + the seat ISO cursors (its real Phase-B signature).
    carrier_names = [ev.payload["source_filename"] for ev in carriers]
    cursor_backfill.total_order(carrier_names)            # validates totality (raises on a bad name)
    seq_map = cursor_backfill.iso_to_seq_map(carrier_names, _read_iso_cursors(coord_root))
    cursors = {}
    try:
        for seat in _SEATS:
            seq = seq_map.get(seat, 0)
            store.advance_cursor(seat, seq)               # seq==0 allowed (refstore:236-240)
            cursors[seat] = store.cursor_seq(seat)
    except Exception:
        _teardown(repo, snapshot)
        raise

    # (5b) ALSO rewrite the legacy seen/*.txt to scalar + archive the reversible manifest.
    #      A failure HERE is INTENTIONALLY not torn down: (a) the authority-flip marker
    #      commit has not happened, so legacy sent/ is still authoritative and readers are
    #      unharmed; (b) cursor_backfill.backfill is idempotent/archive-once, so a retry
    #      resumes cheaply; (c) tearing down would discard all the successful appends above
    #      for a recoverable filesystem error.
    cursor_backfill.backfill(coord_root)

    # (6) AUTHORITY FLIP = the single explicit act, only after ALL appends + cursors.
    #     (The marker/doctrine commit is the caller's; this returns the GO signal —
    #     ready_to_flip, not the flip itself.)
    return CutoverResult(appended=appended, cursors=cursors, ready_to_flip=True)
