"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_cutover.py -q"""
import json
import os
import subprocess

import pytest

from threeway import gitcas, keys
from threeway.gitcas import BusInitRefusedError
from threeway.refstore import RefEventStore, EVENTS_REF
from threeway.cutover import run_cutover
from threeway import legacy_projector
from threeway.cursor_backfill import _mailbox_base
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


def _sent_dir(root):
    # legacy_projector.project() consumes the sent/ dir DIRECTLY (its real Phase-B API);
    # cursor_backfill._mailbox_base resolves coordination/mailbox from either root layout.
    return _mailbox_base(root) / "sent"


def test_cutover_three_way_set_bijection(tmp_path):
    # CLAUSE 5: legacy sent set == projected set == post-backfill index/<seq> set.
    # MUTATION (documented): drop one sent/*.md before cutover -> the projected set and
    # the ref index/<seq> set both shrink by one while legacy != them -> bijection RED.
    r = _new_repo(tmp_path); root = _seed_coord(r)
    importer, _ = keys.generate_keypair()
    res = run_cutover(r, root, importer, force=False)
    legacy = set(_NAMES)
    projected = {ev.payload["source_filename"] for ev in legacy_projector.project(_sent_dir(root))}
    store = RefEventStore(r)
    ref_files = {ev.payload["source_filename"] for ev in store.all_events()}
    assert legacy == projected == ref_files            # three-way bijection
    assert len(ref_files) == len(_NAMES)               # non-empty floor (no collapse)
    assert res.appended == len(_NAMES)                 # cutover reports the count it appended


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


def test_teardown_restores_preexisting_bus_on_failure_under_force(tmp_path, monkeypatch):
    # I-1: with force=True, preflight_bus_init SHORT-CIRCUITS (gitcas:243-244) and does NOT
    # prove the bus absent — so a pre-existing refs/threeway/events is the legitimate
    # "acknowledge it" path. A mid-cutover failure must therefore RESTORE that prior bus,
    # not delete it. Snapshot-and-restore teardown is what guarantees this.
    #
    # NON-VACUITY: on the PRE-FIX code _teardown did `update-ref -d EVENTS_REF`
    # UNCONDITIONALLY, so rev_parse(EVENTS_REF) after the failure returns None != the
    # captured pre-run OID -> RED. (Verified by reasoning against the prior _teardown;
    # scratch-reverting the snapshot+restore to the unconditional delete reproduces the
    # None result.) The fix restores the captured OID -> GREEN.
    r = _new_repo(tmp_path); root = _seed_coord(r)
    head = _git(r, "rev-parse", "HEAD").stdout.strip()
    _git(r, "update-ref", EVENTS_REF, head)                 # stray pre-existing bus state
    pre = gitcas.rev_parse(r, EVENTS_REF)
    assert pre == head                                      # the bus we expect teardown to PRESERVE
    importer, _ = keys.generate_keypair()

    # Fail INSIDE the cursor loop (after the bus has been appended over), so the
    # cursor-loop except-block fires _teardown(repo, snapshot).
    def _boom(self, seat, seq):
        raise RuntimeError("injected cursor failure")
    monkeypatch.setattr(RefEventStore, "advance_cursor", _boom)

    with pytest.raises(RuntimeError, match="injected cursor failure"):
        run_cutover(r, root, importer, force=True)

    # RESTORED to the exact pre-run OID — NOT deleted (which the pre-fix code would do).
    assert gitcas.rev_parse(r, EVENTS_REF) == pre


def test_teardown_best_effort_continues_and_chains_original_cause(tmp_path, monkeypatch):
    # ADR-044: a single ref-restore failure (e.g. a concurrent writer holding
    # refs/threeway/events.lock -> git exit 128) must NOT (a) abort the restore loop
    # leaving every later cursor ref un-restored, nor (b) MASK the original cutover
    # failure by propagating its own CalledProcessError in place of the real cause.
    # NON-VACUITY: pre-fix _teardown was a bare loop, check=True on the FIRST (events)
    # ref, so a raise there skipped every later cursor ref AND replaced the original
    # exception -> the `attempted` and __cause__ assertions below are RED on pre-fix code.
    from threeway import cutover
    EVENTS = EVENTS_REF
    CUR = "refs/threeway/cursors/director"
    snapshot = {EVENTS: "a" * 40, CUR: "b" * 40}   # both pre-existing -> restore branch (check=True)
    attempted = []

    def _fake_run(cmd, *a, **kw):
        ref = cmd[5] if cmd[4] == "-d" else cmd[4]
        attempted.append(ref)
        if ref == EVENTS:
            raise subprocess.CalledProcessError(128, cmd, stderr=b"cannot lock ref: File exists")
        class _R:                                  # a successful git update-ref
            returncode = 0
        return _R()

    monkeypatch.setattr(cutover.subprocess, "run", _fake_run)
    original = RuntimeError("ORIGINAL cursor failure")
    with pytest.raises(cutover.TeardownError) as ei:
        cutover._teardown(tmp_path, snapshot, original)
    assert ei.value.__cause__ is original              # (b) original preserved, not masked
    assert CUR in attempted, "loop aborted on first failure -> later refs not restored"  # (a)
    assert EVENTS in str(ei.value)                      # the failing ref is surfaced


def test_teardown_clean_restore_stays_silent(tmp_path, monkeypatch):
    # When every restore succeeds, _teardown must NOT raise, so the caller's bare
    # `raise` re-raises the ORIGINAL cause unchanged (the existing happy-path contract,
    # which test_teardown_restores_preexisting_bus_on_failure_under_force relies on).
    from threeway import cutover
    snapshot = {EVENTS_REF: "a" * 40, "refs/threeway/cursors/director": "b" * 40}

    def _ok(cmd, *a, **kw):
        class _R:
            returncode = 0
        return _R()

    monkeypatch.setattr(cutover.subprocess, "run", _ok)
    cutover._teardown(tmp_path, snapshot, RuntimeError("x"))   # must NOT raise


def test_pretry_validation_failure_restores_bus_under_force(tmp_path, monkeypatch):
    # ADR-045 (Rule-13 sibling of ADR-044): total_order / iso_to_seq_map /
    # _read_iso_cursors run AFTER the append loop (the bus is already appended over) but
    # were OUTSIDE both teardown-guarded try blocks. A raise there (a bad carrier name ->
    # total_order ValueError, or an unreadable seen/*.txt -> _read_iso_cursors OSError)
    # stranded the half-built events ref with NO _teardown.
    # NON-VACUITY: pre-fix the validation sits before `try:`, so the injected ValueError
    # propagates uncaught -> EVENTS_REF stays at the appended-over RUN value != pre -> RED.
    # The fix moves the validation inside the cursor try, so the same except restores it.
    r = _new_repo(tmp_path); root = _seed_coord(r)
    head = _git(r, "rev-parse", "HEAD").stdout.strip()
    _git(r, "update-ref", EVENTS_REF, head)                 # legitimate force=True pre-existing bus
    pre = gitcas.rev_parse(r, EVENTS_REF)
    importer, _ = keys.generate_keypair()

    from threeway import cutover

    def _boom(_names):
        raise ValueError("injected total_order failure")
    monkeypatch.setattr(cutover.cursor_backfill, "total_order", _boom)

    with pytest.raises(ValueError, match="injected total_order failure"):
        run_cutover(r, root, importer, force=True)
    # RESTORED to the exact pre-run OID — pre-fix this stayed at the appended-over value.
    assert gitcas.rev_parse(r, EVENTS_REF) == pre


def test_cutover_succeeds_and_cursors_congruent_with_stray_nonevent_file(tmp_path):
    # ADR-050: a CLEAN non-event .md in sent/ (e.g. a stray note) must be skipped by BOTH
    # the projector (append order) and the cursor backfill (seq numbering), so the cutover
    # succeeds AND the manifest's archived iso_to_seq stays congruent with the appended ref
    # cursors. NON-VACUITY: pre-fix backfill()'s _sent_names()+total_order raised ValueError
    # on the no-ts file -> run_cutover aborted at step 5b -> this test goes RED.
    r = _new_repo(tmp_path); root = _seed_coord(r)
    (root / "coordination" / "mailbox" / "sent" / "NOTES.md").write_text("stray note, not an event\n")
    importer, _ = keys.generate_keypair()
    res = run_cutover(r, root, importer, force=False)
    assert res.appended == len(_NAMES)                      # the stray was NOT appended
    store = RefEventStore(r)
    man = json.loads((root / "coordination" / "mailbox" / ".migration"
                      / "cursor-backfill.json").read_text())
    # the archived cursor numbering == the authoritative appended ref cursor for every seat
    assert man["iso_to_seq"]
    for seat, seq in man["iso_to_seq"].items():
        assert store.cursor_seq(seat) == seq


def test_cutover_raises_on_tsprefixed_malformed_filename_not_silent_shift(tmp_path):
    # ADR-050: a ts-prefixed .md that fails the carrier grammar (looks like an event) must
    # ABORT the cutover loudly — never be silently skipped by the projector while counted by
    # the cursor numbering (pre-fix that shifted every later seq +1, and a force-rerun then
    # over-advanced the authoritative cursor refs past unread events). NON-VACUITY: pre-fix
    # run_cutover SUCCEEDS (projector skips it, backfill counts it) -> no raise -> RED.
    from threeway.legacy_projector import MalformedEventFilename
    r = _new_repo(tmp_path); root = _seed_coord(r)
    (root / "coordination" / "mailbox" / "sent"
     / "2026-06-17T21-00-00Z-stranger-to-director-foo.md").write_text(
        "# x\n\n**From:** stranger\n**When:** 2026-06-17T21:00:00Z\n\nbody\n")
    importer, _ = keys.generate_keypair()
    with pytest.raises(MalformedEventFilename):
        run_cutover(r, root, importer, force=False)


def test_read_iso_cursors_canonicalizes_seat_filename_case(tmp_path):
    # ADR-051: a seen/<Seat>.txt with non-canonical case must map to the lowercase roster
    # seat, NOT a phantom key. Pre-fix p.stem yielded "Operator" (phantom) -> the real
    # "operator" then fell back to a silent cursor 0.
    from threeway import cutover
    seen = tmp_path / "coordination" / "mailbox" / "seen"; seen.mkdir(parents=True)
    (seen / "Operator.txt").write_text("2026-06-17T20:00:00Z\n")
    assert cutover._read_iso_cursors(tmp_path) == {"operator": "2026-06-17T20:00:00Z"}


def test_read_iso_cursors_rejects_phantom_nonroster_filename(tmp_path):
    # ADR-051: a stray seen/ .txt whose stem is not a roster seat (operator.foo.txt, which
    # p.stem mis-parses to "operator.foo") must RAISE, not become a phantom seat key.
    from threeway import cutover
    from threeway.cursor_backfill import SeatCursorError
    seen = tmp_path / "coordination" / "mailbox" / "seen"; seen.mkdir(parents=True)
    (seen / "operator.foo.txt").write_text("2026-06-17T20:00:00Z\n")
    with pytest.raises(SeatCursorError):
        cutover._read_iso_cursors(tmp_path)


def test_cutover_raises_on_missing_seat_cursor_not_silent_full_reprocess(tmp_path):
    # ADR-051: a roster seat with NO seen/<seat>.txt must be a LOUD error, never a silent
    # seq_map.get(seat, 0) that sets cursor 0 and re-processes the ENTIRE migrated bus.
    # NON-VACUITY: pre-fix run_cutover SUCCEEDS with the missing seat silently at cursor 0.
    from threeway.cursor_backfill import SeatCursorError
    r = _new_repo(tmp_path); root = _seed_coord(r)
    (root / "coordination" / "mailbox" / "seen" / "operator2.txt").unlink()   # drop one real seat
    importer, _ = keys.generate_keypair()
    with pytest.raises(SeatCursorError):
        run_cutover(r, root, importer, force=False)


_D_RERUN_NAMES = [
    "2026-06-17T10-00-00Z-operator-to-director-a.md",
    "2026-06-17T11-00-00Z-operator-to-director-b.md",
    "2026-06-17T12-00-00Z-operator-to-director-c.md",
    "2026-06-17T13-00-00Z-operator-to-director-d.md",
    "2026-06-17T14-00-00Z-operator-to-director-e.md",
]


def _seed_coord_rerun(root):
    sent = root / "coordination" / "mailbox" / "sent"; sent.mkdir(parents=True)
    seen = root / "coordination" / "mailbox" / "seen"; seen.mkdir(parents=True)
    for n in _D_RERUN_NAMES:
        (sent / n).write_text(
            "# subj\n\n**From:** operator\n**When:** " + n[:11] + n[11:20].replace("-", ":") + "\n\nbody\n")
    (seen / "director.txt").write_text("2026-06-17T12:00:00Z\n")   # covers seq 1-3 (true seq 3, head 5)
    for s in ("director2", "operator", "operator2", "coordinator", "coordinator2"):
        (seen / f"{s}.txt").write_text("2026-06-17T14:00:00Z\n")   # head
    return root


def test_force_rerun_does_not_overadvance_cursor_ref_from_scalar_seen(tmp_path):
    # ADR-049: on a force=True RE-RUN the prior run's step-5b backfill has rewritten
    # seen/*.txt to SCALAR seqs. Step 4 must NOT re-read them as ISO and lexicographically
    # over-advance the cursor ref past unread events (`"2026-..." <= "3"` is True -> head).
    # NON-VACUITY: with step 4 re-deriving from the scalar seen (pre-fix), director's "3"
    # maps to the head seq 5 and advance_cursor pushes the ref 3 -> 5; the fix sources the
    # ISO-derived seq from the prior run's archived manifest (3) -> the ref stays at 3.
    r = _new_repo(tmp_path); root = _seed_coord_rerun(r)
    importer, _ = keys.generate_keypair()
    run_cutover(r, root, importer, force=False)            # first run
    store = RefEventStore(r)
    assert store.cursor_seq("director") == 3               # true seq from the 12:00 ISO cursor
    seen = root / "coordination" / "mailbox" / "seen"
    assert (seen / "director.txt").read_text().strip() == "3"   # step 5b rewrote it to scalar
    run_cutover(r, root, importer, force=True)             # documented "acknowledge prior bus" path
    assert store.cursor_seq("director") == 3               # NOT over-advanced to the head (5)
