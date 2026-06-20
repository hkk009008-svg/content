"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_legacy_roster.py -q

Phase-A roster-wiring gate for Slice 2.5 (spec §8 clauses #1/#2). Pins that
coordinator AND coordinator2 are first-class send/receive seats at the
protocol_mailbox root, and that every independent Python roster copy + the four
shell whitelists agree with that root. Non-vacuity: each test mutates exactly
one fact (drops coordinator2 from one tuple/arm) and asserts the check flips.
"""
from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import check_coordination as cc  # noqa: E402
import mailbox_monitor as mm  # noqa: E402
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


# --- Task 3: event-name regexes accept coordinator/coordinator2 frm+to (§4b) ---

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


# --- Task 4: shell whitelists ↔ Python root sync guard (spec §8 clause #2) ---

_BIN = Path(__file__).resolve().parent.parent.parent / "coordination" / "bin"


def _case_arm_tokens(path: Path, var: str) -> set[str]:
    """Extract the seat tokens from a `case "$VAR" in <a>|<b>|...) ;;` arm.
    Reads the LOAD-BEARING arm, never a usage/echo string. NB: this extractor
    assumes seat tokens stay `[a-z0-9]` with no spaces around the `|` — true for
    the whole roster; a seat name with `_`/`-`/uppercase would silently truncate."""
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
    #2 — NOT the STATE.md prose line, which is a separate string). Roster-agnostic:
    matches any `[a-z0-9]` token after a `_unread_for ` CALL (the `\\s+` excludes the
    `_unread_for()` definition), so it sees a future seat AND catches a typo'd token
    (which then fails the set-equality) instead of silently ignoring it."""
    text = path.read_text()
    return set(re.findall(r"_unread_for\s+([a-z0-9]+)", text))


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


# --- Task 5: ISO cursor seeding + coordinator/coordinator2 in ROLES -----------

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


def test_live_coordinator_cursors_seeded_iso():
    seen = Path(__file__).resolve().parent.parent.parent / "coordination" / "mailbox" / "seen"
    for f in ("coordinator.txt", "coordinator2.txt"):
        cur = (seen / f).read_text().strip()
        assert cc._CURSOR_RE.match(cur), f"{f} not ISO (Phase A is ISO-only): {cur!r}"


# --- Task 5 review-fix: .claude/.agents seat_status.py structural sync guard ---

_REPO = Path(__file__).resolve().parent.parent.parent
_SEAT_STATUS_AGENTS = _REPO / ".agents" / "skills" / "four-seat-protocol" / "scripts" / "seat_status.py"
_SEAT_STATUS_CLAUDE = _REPO / ".claude" / "skills" / "four-seat-protocol" / "scripts" / "seat_status.py"


def _normalized_seat_status(path: Path) -> str:
    """Read a seat_status.py copy, dropping the ONE self-referential docstring
    usage line that legitimately differs (`.agents/...` vs `.claude/...`). Every
    other byte must be identical between the canonical (.agents) copy and the
    .claude mirror — they are both live and hand-maintained, so any divergence is
    drift (the heartbeats() bug that prompted this guard fixed in only one copy)."""
    kept = [
        ln for ln in path.read_text(encoding="utf-8").splitlines()
        if "skills/four-seat-protocol/scripts/seat_status.py" not in ln
    ]
    return "\n".join(kept)


def test_seat_status_copies_are_identical_modulo_self_path():
    # The two copies MUST stay byte-identical except their own usage-path line.
    agents = _normalized_seat_status(_SEAT_STATUS_AGENTS)
    claude = _normalized_seat_status(_SEAT_STATUS_CLAUDE)
    assert agents == claude, (
        ".agents and .claude seat_status.py have diverged beyond their "
        "self-referential usage path — a fix landed in only ONE copy (drift)."
    )

    # Sanity: the normalization dropped exactly the one differing path line, not
    # the whole docstring — both copies still carry the heartbeats() fix comment.
    for path in (_SEAT_STATUS_AGENTS, _SEAT_STATUS_CLAUDE):
        body = path.read_text(encoding="utf-8")
        assert "for seat in protocol_mailbox.SEATS:" in body
        assert "heartbeats are pair-seat only" in body

    # --- non-vacuity: simulate a one-copy-only change (the exact drift this guard
    # exists to catch) by mutating the .claude content in memory → compare flips RED.
    drifted_claude = claude.replace(
        "for seat in protocol_mailbox.SEATS:", "for seat in SEATS:", 1
    )
    assert drifted_claude != claude, "mutation precondition failed — pattern not present"
    assert agents != drifted_claude  # if only .claude were reverted, the guard goes RED
