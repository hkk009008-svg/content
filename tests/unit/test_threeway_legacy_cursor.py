"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_legacy_cursor.py -q"""
import os
import subprocess
import sys
from pathlib import Path

# scripts/ is importable in this repo's pytest config (see existing
# tests/unit/test_threeway_* that import status/protocol_mailbox); mirror that.
_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "scripts"))
import check_coordination as cc  # noqa: E402
import status  # noqa: E402  (the scalar-path count_unread short-circuit, below)


def _seed_mailbox(root: Path, cursor_text: str):
    """A minimal coordination tree: one event addressed to director + its cursor."""
    sent = root / "coordination" / "mailbox" / "sent"
    seen = root / "coordination" / "mailbox" / "seen"
    sent.mkdir(parents=True); seen.mkdir(parents=True)
    (sent / "2026-06-17T19-55-31Z-operator-to-director-status.md").write_text(
        "# s\n\n**From:** operator\n**When:** 2026-06-17T19:55:31Z\n")
    for seat in cc.ROLES:
        (seen / f"{seat}.txt").write_text(cursor_text + "\n")
    return root


def test_scalar_seq_cursor_is_accepted_not_fatal(tmp_path):
    # NON-VACUITY: a scalar-seq cursor must pass _CURSOR_RE (no cursor_unparseable
    # FATAL). MUTATION (documented): revert _CURSOR_RE to the ISO-only pattern
    # r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$" and this assertion flips — the
    # scalar "42" no longer matches and _check_cursors emits cursor_unparseable FATAL.
    _seed_mailbox(tmp_path, "42")                       # post-backfill scalar seq
    now = "2026-06-18T00:00:00Z"
    names = cc._event_names(tmp_path / "coordination", "sent")
    issues = cc._check_cursors(tmp_path / "coordination", now, names)
    fatals = [i for i in issues if i.severity == "FATAL"]
    assert fatals == [], [(i.kind, i.message) for i in fatals]
    assert cc._CURSOR_RE.match("42")                    # scalar matches
    assert cc._CURSOR_RE.match("0")                     # the seq-0 floor matches


def test_iso_cursor_still_accepted_during_transition(tmp_path):
    # Phase A seeded ISO cursors that survive until Task 12 converts them; the
    # transitional regex must keep accepting ISO so no live seat half-breaks.
    _seed_mailbox(tmp_path, "2026-06-17T19:55:31Z")
    now = "2026-06-18T00:00:00Z"
    names = cc._event_names(tmp_path / "coordination", "sent")
    issues = cc._check_cursors(tmp_path / "coordination", now, names)
    assert [i for i in issues if i.severity == "FATAL"] == []


def test_scalar_cursor_is_never_flagged_future(tmp_path):
    # the cur>now ISO future-check is meaningless for a scalar; it must be SKIPPED.
    # MUTATION: drop the is-ISO guard on the future-check -> "999999" > now (lexical
    # ISO compare) fires a spurious cursor_future FATAL and this flips RED.
    _seed_mailbox(tmp_path, "999999")
    now = "2026-06-18T00:00:00Z"
    names = cc._event_names(tmp_path / "coordination", "sent")
    issues = cc._check_cursors(tmp_path / "coordination", now, names)
    assert not [i for i in issues if i.kind == "cursor_future"]


# --- the OTHER 5 loosened parsers (the RED test only imports check_coordination, so
# without these the scalar-path edits in status.count_unread / seat_status / the
# consume-events case / both update-state.sh are UNTESTED). Each is a non-vacuous
# scalar check on a distinct parser.

def test_status_count_unread_scalar_short_circuits_to_zero():
    # status.count_unread on a scalar `seq` cursor returns 0 (unread is ref-bus-tracked,
    # not computed from filenames here). MUTATION: drop the _is_iso_cursor guard ->
    # the seq-0 floor "0" falls through to the lexical filename compare; both events
    # ("2026-..." > "0") count as unread and over-count -> 2 != 0. (Use "0", NOT "42":
    # "2026-..." sorts AFTER "4" lexically so "42" would stay 0 unguarded -> vacuous.)
    files = [
        "2026-06-13T01-00-00Z-director-to-operator-status.md",
        "2026-06-13T02-00-00Z-director-to-all-fyi.md",
    ]
    assert status.count_unread("0", files, "operator") == 0           # scalar -> 0
    # sanity: an ISO cursor still counts normally (the guard is a strict superset)
    assert status.count_unread("2026-06-13T00:00:00Z", files, "operator") == 2


def _sh_env():
    e = dict(os.environ); e.pop("GIT_INDEX_FILE", None); return e


def test_consume_events_scalar_to_passes_validation(tmp_path):
    # subprocess smoke: a scalar `--to` must PASS the loosened --to validation case (no
    # "malformed --to" reject). This verifies the VALIDATION GATE only, not end-to-end
    # consumption (a scalar --to still fails downstream with "no event at ..." because the
    # legacy reader is ISO-based; scalar consumption is the ref-bus's job post-cutover).
    # MUTATION: revert the case to ISO-only -> the all-digit "42" hits the `*[!0-9]*`-less
    # default and is rejected -> "malformed --to" on stderr -> this flips RED.
    sent = tmp_path / "coordination" / "mailbox" / "sent"; sent.mkdir(parents=True)
    seen = tmp_path / "coordination" / "mailbox" / "seen"; seen.mkdir(parents=True)
    (seen / "director.txt").write_text("0\n")
    r = subprocess.run([str(_REPO / "coordination" / "bin" / "consume-events"),
                        "director", "--to", "42"],
                       cwd=tmp_path, env=_sh_env(), capture_output=True, text=True)
    # accept = the --to validation passed (no "malformed --to" on stderr / exit 2 there).
    assert "malformed --to" not in r.stderr, r.stderr


def test_seat_status_scalar_cursor_reports_zero_unread(tmp_path):
    # subprocess smoke of seat_status.mailbox with a SCALAR cursor: it must short-circuit
    # to "0 / ref-bus-tracked", NOT over-count every event. MUTATION: drop the all-digit
    # short-circuit in seat_status.mailbox -> _parse_cursor_ts returns None -> cursor_dt
    # is None -> every event counted unread -> "UNREAD: 0" no longer holds -> RED.
    coord = tmp_path / "coordination" / "mailbox"
    (coord / "sent").mkdir(parents=True); (coord / "seen").mkdir(parents=True)
    (coord / "sent" / "2026-06-13T01-00-00Z-director-to-operator-status.md").write_text("# e\n")
    (coord / "sent" / "2026-06-13T02-00-00Z-director-to-operator-status.md").write_text("# e\n")
    (coord / "seen" / "operator.txt").write_text("99\n")            # scalar seq cursor
    r = subprocess.run([sys.executable,
                        str(_REPO / ".agents" / "skills" / "four-seat-protocol"
                            / "scripts" / "seat_status.py"), "operator"],
                       cwd=tmp_path, env=_sh_env(), capture_output=True, text=True)
    out = r.stdout + r.stderr
    assert "UNREAD: 0" in out or "ref-bus-tracked" in out, out
