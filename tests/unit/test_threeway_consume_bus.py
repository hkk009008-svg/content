"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_consume_bus.py -q"""
import contextlib
import io
import os
import subprocess

import pytest

from threeway import keys
from threeway.envelope import Event
from threeway.loop import PAIR_A, build_candidate_events
from threeway.refstore import RefEventStore


# --- fixtures copied from tests/unit/test_threeway_gate.py (per-file convention) ---
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
    """Sign+append each event with ITS seat's key (signer prefix); return the last stored Event."""
    store = RefEventStore(repo)
    last = None
    for ev in events:
        last = store.append(ev, keys.load_private(ev.signer.split(":", 1)[0]))
    return last


def _run(argv):
    from scripts.consume_bus import main
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = main(argv)
    return rc, out.getvalue()


def test_shows_addressed_event_and_advances_cursor(seatkit, live_repo):
    r, base, branch = live_repo
    last = _append_all(r, build_candidate_events(base, branch, "0" * 40, {}, pair=PAIR_A, candidate_id="c1"))
    rc, out = _run(["coordinator", "--repo-dir", str(r), "--remote", ""])
    assert rc == 0
    kinds = {l.split("\t")[1] for l in out.splitlines() if l.strip()}
    assert "candidate" in kinds
    assert RefEventStore(r).cursor_seq("coordinator") == last.seq          # advanced to tip


def test_no_advance_leaves_cursor(seatkit, live_repo):
    r, base, branch = live_repo
    _append_all(r, build_candidate_events(base, branch, "0" * 40, {}, pair=PAIR_A, candidate_id="c1"))
    _run(["coordinator", "--repo-dir", str(r), "--remote", "", "--no-advance"])
    assert RefEventStore(r).cursor_seq("coordinator") == 0


def test_addressee_filter_hides_directed_event(seatkit, live_repo):
    # MUTATION TARGET: an event with recipient="director" must NOT show for coordinator.
    r, base, branch = live_repo
    ev = Event(id="x-coordinator-c1", seq=0, bus_id="prod", schema_version="threeway/1",
               kind="candidate", sender="coordinator", recipient="director",
               signer="coordinator:claude:s1", payload={"candidate_id": "A:c1"},
               brief_id="b1", brief_version=1, candidate_id="A:c1")
    RefEventStore(r).append(ev, keys.load_private("coordinator"))
    rc, out = _run(["coordinator", "--repo-dir", str(r), "--remote", ""])
    assert rc == 0 and out.strip() == ""                                   # leaks RED if filter removed


def test_empty_bus_clean_noop(seatkit, live_repo):
    r, *_ = live_repo
    rc, out = _run(["operator", "--repo-dir", str(r), "--remote", ""])
    assert rc == 0 and out.strip() == ""
    assert RefEventStore(r).cursor_seq("operator") == 0                     # no max() ValueError; cursor 0


def test_kinds_filter(seatkit, live_repo):
    r, base, branch = live_repo
    _append_all(r, build_candidate_events(base, branch, "0" * 40, {}, pair=PAIR_A, candidate_id="c1"))
    rc, out = _run(["coordinator", "--repo-dir", str(r), "--remote", "", "--kinds", "candidate"])
    assert {l.split("\t")[1] for l in out.splitlines() if l.strip()} == {"candidate"}


def test_bus_id_filter_hides_foreign(seatkit, live_repo):
    r, base, branch = live_repo
    _append_all(r, build_candidate_events(base, branch, "0" * 40, {}, bus_id="staging",
                                          pair=PAIR_A, candidate_id="c1"))
    rc, out = _run(["coordinator", "--repo-dir", str(r), "--remote", "", "--bus-id", "prod"])
    assert out.strip() == ""                                               # foreign-bus hidden


def test_corrupt_cursor_exits_rc1(seatkit, live_repo):
    r, base, branch = live_repo
    _append_all(r, build_candidate_events(base, branch, "0" * 40, {}, pair=PAIR_A, candidate_id="c1"))
    oid = _git(r, "hash-object", "-w", "--stdin", stdin=b"not-an-int\n").stdout.decode().strip()
    _git(r, "update-ref", "refs/threeway/cursors/coordinator", oid)
    rc, _ = _run(["coordinator", "--repo-dir", str(r), "--remote", ""])
    assert rc == 1                                                         # CursorCorruptionError, no traceback


def test_already_seen_events_hidden_past_cursor(seatkit, live_repo):
    # NON-VACUOUS cursor-filter pin: events at or below the cursor must NOT re-show.
    # MUTATION TARGET: `ev.seq > cursor` -> `ev.seq >= 0` must redden this.
    r, base, branch = live_repo
    _append_all(r, build_candidate_events(base, branch, "0" * 40, {}, pair=PAIR_A, candidate_id="c1"))
    rc, out1 = _run(["coordinator", "--repo-dir", str(r), "--remote", ""])      # 1st read advances cursor to tip
    assert rc == 0 and out1.strip() != ""                                        # saw the first batch
    seen_tip = RefEventStore(r).cursor_seq("coordinator")
    assert seen_tip > 0
    nxt = Event(id="extra-coordinator-c2", seq=0, bus_id="prod", schema_version="threeway/1",
                kind="candidate", sender="coordinator", recipient="all",
                signer="coordinator:claude:s1", payload={"candidate_id": "A:c2"},
                brief_id="b1", brief_version=1, candidate_id="A:c2")
    RefEventStore(r).append(nxt, keys.load_private("coordinator"))               # ONE event past the cursor
    rc, out2 = _run(["coordinator", "--repo-dir", str(r), "--remote", ""])
    assert rc == 0
    lines = [l for l in out2.splitlines() if l.strip()]
    assert len(lines) == 1 and lines[0].split("\t")[3] == "A:c2"                  # ONLY the post-cursor event
