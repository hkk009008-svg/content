"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_rework.py -q"""
from threeway.envelope import Event
from threeway.rework import rework_count, should_escalate, REWORK_CAP


def _abort(seq):
    return Event(id=f"a{seq}", seq=seq, bus_id="prod", schema_version="threeway/1",
                 kind="candidate_aborted", sender="coordinator", recipient="all",
                 signer="coordinator:claude:s1", payload={}, brief_id="b1",
                 brief_version=1, candidate_id=f"c{seq}")


def test_two_reworks_do_not_escalate():
    events = [_abort(1), _abort(2)]
    assert rework_count(events, "b1", 1) == 2
    assert not should_escalate(events, "b1", 1)


def test_third_rework_escalates():
    events = [_abort(1), _abort(2), _abort(3)]
    assert should_escalate(events, "b1", 1)
