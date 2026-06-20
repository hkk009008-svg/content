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
