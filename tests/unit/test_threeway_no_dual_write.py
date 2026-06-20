"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_no_dual_write.py -q"""
import os
import subprocess

import pytest

from threeway import gitcas, keys
from threeway.refstore import EVENTS_REF, RefEventStore
from threeway.legacy_projector import project
from threeway.divergence import diverge

_BODY = (
    "# {subj}\n\n**When:** {when} · **From:** {frm} (online)\n\n"
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
    # parents=True: the mutation test passes `tmp_path / "two"` (a not-yet-created
    # parent) for the second fresh repo, so the intermediate dir must be created too.
    r = tmp_path / "r"; r.mkdir(parents=True)
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
