"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_cutover.py -q"""
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
