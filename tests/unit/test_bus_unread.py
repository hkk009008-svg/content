"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_bus_unread.py -q

scripts/bus_unread.py is the de-degrade keystone: legacy unread dashboards compute
unread from sent/*.md ISO filenames and correctly return 0 for a migrated (scalar)
cursor — but that silently UNDER-reports. This helper reads the signed ref-bus LOCALLY
(no network) and returns the REAL unread, mirroring consume_bus.py's filter exactly.
"""
import os
import subprocess

import pytest

from threeway import keys
from threeway.envelope import Event
from threeway.loop import PAIR_A, build_candidate_events
from threeway.refstore import RefEventStore

from scripts.bus_unread import (
    bus_unread_count,
    bus_unread_events,
    format_unread,
    is_migrated_cursor,
)


# --- fixtures copied from tests/unit/test_threeway_consume_bus.py (per-file convention) ---
def _env():
    env = dict(os.environ); env.pop("GIT_INDEX_FILE", None); return env


def _git(repo, *a, stdin=None):
    return subprocess.run(["git", "-C", str(repo), *a], check=True,
                          capture_output=True, text=(stdin is None), input=stdin, env=_env())


@pytest.fixture()
def seatkit(tmp_path, monkeypatch):
    reg = tmp_path / "pub"; ks = tmp_path / "ks"; reg.mkdir(); ks.mkdir()
    for seat in ("director", "director2", "operator", "operator2", "coordinator", "coordinator2",
                 "overseer", "ci", "merge-gate"):
        priv, pub = keys.generate_keypair()
        (reg / f"{seat}.pub").write_text(pub + "\n")
        (ks / f"{seat}.ed25519").write_text(keys.private_to_hex(priv) + "\n")
    monkeypatch.setenv("THREEWAY_KEYSTORE", str(ks))
    return reg, ks


@pytest.fixture()
def live_repo(tmp_path):
    r = tmp_path / "repo"; r.mkdir()
    _git(r, "init", "-q"); _git(r, "config", "user.email", "t@e.st"); _git(r, "config", "user.name", "t")
    (r / "base.txt").write_text("base\n"); _git(r, "add", "-A"); _git(r, "commit", "-qm", "base")
    base = _git(r, "rev-parse", "HEAD").stdout.strip()
    _git(r, "update-ref", "refs/threeway/test-main", base)
    _git(r, "checkout", "-q", "-b", "feat")
    (r / "cinema").mkdir(); (r / "cinema" / "f.py").write_text("x = 1\n")
    _git(r, "add", "-A"); _git(r, "commit", "-qm", "feat")
    branch = _git(r, "rev-parse", "HEAD").stdout.strip()
    return r, base, branch


def _append_all(repo, events):
    store = RefEventStore(repo)
    last = None
    for ev in events:
        last = store.append(ev, keys.load_private(ev.signer.split(":", 1)[0]))
    return last


# ---------------------------------------------------------------------------
# is_migrated_cursor — the scalar sentinel detector
# ---------------------------------------------------------------------------

def test_is_migrated_cursor_distinguishes_scalar_from_iso():
    assert is_migrated_cursor("764") is True
    assert is_migrated_cursor(" 764 ") is True          # tolerate surrounding whitespace
    assert is_migrated_cursor("2026-06-17T19:39:53Z") is False
    assert is_migrated_cursor("2026-06-17T19-39-53Z") is False
    assert is_migrated_cursor("") is False
    assert is_migrated_cursor("   ") is False
    assert is_migrated_cursor("(unavailable: x)") is False


# ---------------------------------------------------------------------------
# bus_unread_count / bus_unread_events — the real ref-bus read
# ---------------------------------------------------------------------------

def test_counts_addressed_events_at_cursor_zero(seatkit, live_repo):
    r, base, branch = live_repo
    _append_all(r, build_candidate_events(base, branch, "0" * 40, {}, pair=PAIR_A, candidate_id="c1"))
    total = len(list(RefEventStore(r).all_events()))     # build_candidate_events -> all recipient="all"
    assert total > 0                                     # non-vacuous seed
    assert bus_unread_count(r, "coordinator") == total   # cursor 0 -> every broadcast event is unread


def test_cursor_hides_already_seen_events(seatkit, live_repo):
    # NON-VACUOUS cursor filter. MUTATION TARGET: `ev.seq > cursor` -> `ev.seq >= 0` reddens this.
    r, base, branch = live_repo
    last = _append_all(r, build_candidate_events(base, branch, "0" * 40, {}, pair=PAIR_A, candidate_id="c1"))
    RefEventStore(r).advance_cursor("coordinator", last.seq)   # consume everything to the tip
    assert bus_unread_count(r, "coordinator") == 0             # nothing past the cursor
    nxt = Event(id="extra-coordinator-c2", seq=0, bus_id="prod", schema_version="threeway/1",
                kind="candidate", sender="coordinator", recipient="all",
                signer="coordinator:claude:s1", payload={"candidate_id": "A:c2"},
                brief_id="b1", brief_version=1, candidate_id="A:c2")
    RefEventStore(r).append(nxt, keys.load_private("coordinator"))   # ONE event past the cursor
    assert bus_unread_count(r, "coordinator") == 1


def test_addressee_filter_excludes_directed_event(seatkit, live_repo):
    # MUTATION TARGET: an event recipient="director" must NOT count for coordinator.
    r, base, branch = live_repo
    ev = Event(id="x-coordinator-c1", seq=0, bus_id="prod", schema_version="threeway/1",
               kind="candidate", sender="coordinator", recipient="director",
               signer="coordinator:claude:s1", payload={"candidate_id": "A:c1"},
               brief_id="b1", brief_version=1, candidate_id="A:c1")
    RefEventStore(r).append(ev, keys.load_private("coordinator"))
    assert bus_unread_count(r, "coordinator") == 0       # directed-elsewhere event is not coordinator's unread
    assert bus_unread_count(r, "director") == 1          # but IS the director's


def test_bus_id_filter_excludes_foreign_bus(seatkit, live_repo):
    r, base, branch = live_repo
    _append_all(r, build_candidate_events(base, branch, "0" * 40, {}, bus_id="staging",
                                          pair=PAIR_A, candidate_id="c1"))
    assert bus_unread_count(r, "coordinator", bus_id="prod") == 0    # foreign-bus hidden
    assert bus_unread_count(r, "coordinator", bus_id="staging") > 0  # control: visible on its own bus


def test_empty_bus_is_zero_not_none(seatkit, live_repo):
    r, *_ = live_repo
    assert bus_unread_count(r, "operator") == 0          # empty bus is a real 0, distinct from None (error)


def test_corrupt_cursor_returns_none_not_raise(seatkit, live_repo):
    # silent-gate-degradation guard: a corrupt cursor must surface as None (caller renders
    # "(unavailable)"), NEVER a traceback and NEVER a silent 0 that hides the corruption.
    r, base, branch = live_repo
    _append_all(r, build_candidate_events(base, branch, "0" * 40, {}, pair=PAIR_A, candidate_id="c1"))
    oid = _git(r, "hash-object", "-w", "--stdin", stdin=b"not-an-int\n").stdout.decode().strip()
    _git(r, "update-ref", "refs/threeway/cursors/coordinator", oid)
    assert bus_unread_count(r, "coordinator") is None
    assert bus_unread_events(r, "coordinator") is None


def test_format_unread_descriptor_carries_seq_and_kind(seatkit, live_repo):
    r, base, branch = live_repo
    _append_all(r, build_candidate_events(base, branch, "0" * 40, {}, pair=PAIR_A, candidate_id="c1"))
    evs = bus_unread_events(r, "coordinator")
    assert evs and len(evs) > 0
    desc = format_unread(evs[0])
    assert str(evs[0].seq) in desc and evs[0].kind in desc
