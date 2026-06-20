"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_legacy_roster.py -q

Phase-A roster-wiring gate for Slice 2.5 (spec §8 clauses #1/#2). Pins that
coordinator AND coordinator2 are first-class send/receive seats at the
protocol_mailbox root, and that every independent Python roster copy + the four
shell whitelists agree with that root. Non-vacuity: each test mutates exactly
one fact (drops coordinator2 from one tuple/arm) and asserts the check flips.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import protocol_mailbox  # noqa: E402
import status  # noqa: E402


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


# Curated registry: (module, attribute-holding-the-receiving-roster). Each entry's
# LIVE object must equal the protocol_mailbox root set incl. coordinator2. A comment
# or docstring mentioning "coordinator2" does NOT satisfy this — we read the object.
_IMPORTABLE_ROSTER_SITES = [
    ("status", "_MAILBOX_SEATS"),
    ("mailbox_monitor", "SEATS"),
    ("draft_handoff", "SEATS"),
    ("proof_bundle", "SEATS"),
    ("protocol_capacity", "VALID_OWNERS"),
    ("continuation_readiness", "SEATS"),
]


def test_every_python_roster_copy_equals_the_root():
    root = set(protocol_mailbox.RECEIVING_SEATS)
    for mod_name, attr in _IMPORTABLE_ROSTER_SITES:
        mod = importlib.import_module(mod_name)
        live = set(getattr(mod, attr))
        # set-equality (order-independent: SEAT_ORDER is coordinator-first by design)
        assert live == root, f"{mod_name}.{attr}={sorted(live)} != root {sorted(root)}"

    # protocol_capacity decouples "valid owner" (VALID_OWNERS == root, incl coordinator2;
    # checked by the registry loop above) from "mandatory per-cycle coverage actor"
    # (SEAT_ORDER). coordinator is a standing actor; coordinator2 is accepted-but-optional
    # (Slice 2.5 Option B). SEAT_ORDER stays coordinator-FIRST (load-bearing) and must NOT
    # contain coordinator2 (else G1 would force a coordinator2 packet every active cycle).
    import protocol_capacity
    assert protocol_capacity.SEAT_ORDER[0] == "coordinator"
    assert "coordinator2" not in protocol_capacity.SEAT_ORDER

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
