"""TDD tests for check_no_ceremony.py R6 — report-cites-executed-pin (ADR-032).

Run: .venv/bin/python -m pytest tests/unit/test_check_no_ceremony_r6.py -q

R6 is high-precision: it fires ONLY on a verification-report whose machine-readable
`reviewer-result/1` block has verdict `pass` yet cites NO executed `--runxfail` pin in
commands[]. A `pass` that never re-ran the pins is ceremony (ADR-027) — a green with no
execution behind it. Reports with no block (today's state) and non-pass verdicts are inert.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import check_no_ceremony as cnc  # noqa: E402


def _block(verdict="pass", commands=None, issues=None) -> str:
    cmds = commands if commands is not None else [
        {"command": ".venv/bin/python -m pytest x.py --runxfail -q",
         "exit_code": 0, "summary": "1 passed in 0.10s"}
    ]
    obj = {
        "schema_version": "reviewer-result/1", "role": "spec", "verdict": verdict,
        "reviewed_commit": "abc1234", "reviewed_head": "abc1234", "working_tree_clean": True,
        "commands": cmds, "issues": issues or [],
        "commit_trailer": {"present": True, "expected": "x", "observed": "x"},
        "unverifiable_reason": None if verdict != "unable_to_verify" else "U1",
        "blocked": None if verdict != "unable_to_verify" else {"command": "x"},
    }
    return json.dumps(obj, indent=2)


def _event(body: str) -> str:
    return f"# report\n\n## RESULT SCHEMA\n\n```json\n{body}\n```\n"


def _mailbox(tmp_path, *bodies):
    sent = tmp_path / "coordination" / "mailbox" / "sent"
    sent.mkdir(parents=True)
    for i, b in enumerate(bodies):
        (sent / f"2026-06-20T0{i}-00-00Z-operator-to-director-verification-report.md").write_text(b)
    return tmp_path


_NO_RUNXFAIL_CMD = [{"command": ".venv/bin/python -m pytest x.py -q",
                     "exit_code": 0, "summary": "1 passed in 0.10s"}]


# ---------------------------------------------------------------------------
# Pure helper
# ---------------------------------------------------------------------------

def test_pure_pass_with_runxfail_is_clean():
    named = [("r.md", json.loads(_block(verdict="pass")))]
    assert cnc._pass_reports_missing_runxfail(named) == []


def test_pure_pass_without_runxfail_is_flagged():
    named = [("r.md", json.loads(_block(verdict="pass", commands=_NO_RUNXFAIL_CMD)))]
    assert cnc._pass_reports_missing_runxfail(named)


def test_pure_issues_verdict_is_not_gated():
    named = [("r.md", json.loads(_block(
        verdict="issues",
        issues=[{"severity": "minor", "file": "x", "line": 1, "requirement": "u", "finding": "f"}],
        commands=[{"command": ".venv/bin/python -m pytest x.py -q", "exit_code": 1,
                   "summary": "1 failed in 0.10s"}],
    )))]
    assert cnc._pass_reports_missing_runxfail(named) == []


def test_pure_utv_verdict_is_not_gated():
    named = [("r.md", json.loads(_block(verdict="unable_to_verify", commands=[])))]
    assert cnc._pass_reports_missing_runxfail(named) == []


# ---------------------------------------------------------------------------
# Rule end-to-end (fixture mailbox via repo_root param)
# ---------------------------------------------------------------------------

def test_rule_zero_blocks_passes(tmp_path):
    repo = _mailbox(tmp_path, "# report\n\nno machine block\n")
    status, _ = cnc.rule_report_cites_executed_pin(repo)
    assert status == "PASS"


def test_rule_pass_with_runxfail_passes(tmp_path):
    repo = _mailbox(tmp_path, _event(_block(verdict="pass")))
    status, _ = cnc.rule_report_cites_executed_pin(repo)
    assert status == "PASS"


def test_rule_pass_without_runxfail_FAILS(tmp_path):
    # NON-VACUITY: a crafted pass-report with no --runxfail command must hard-fail R6.
    repo = _mailbox(tmp_path, _event(_block(verdict="pass", commands=_NO_RUNXFAIL_CMD)))
    status, lines = cnc.rule_report_cites_executed_pin(repo)
    assert status == "FAIL"
    assert any("--runxfail" in line for line in lines)


def test_rule_malformed_block_fails_loudly(tmp_path):
    bad = "# report\n\n```json\n{\"schema_version\": \"reviewer-result/1\",,}\n```\n"
    repo = _mailbox(tmp_path, bad)
    status, _ = cnc.rule_report_cites_executed_pin(repo)
    assert status == "FAIL"
