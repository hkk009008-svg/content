"""TDD tests for scripts/consume_reviewer_result.py — the reviewer-result/1 consumer.

Run: .venv/bin/python -m pytest tests/unit/test_consume_reviewer_result.py -q

The consumer is the deferred follow-up of ADR-032: it parses the machine-readable
`reviewer-result/1` block out of a verification-report, validates the schema
invariants, RE-RUNS the reported pytest to detect a fabricated summary (the central
value), maps reviewer severity -> inventory severity, and PROPOSES (never applies)
REMEDIATION-INVENTORY.md status transitions.

All fixtures use real tmp_path files + real strings (no mocking the unit under test).
The only injected seam is the subprocess command-runner, so the fabrication-detection
parse/diff logic is exercised on real data without spawning pytest in every unit test;
one integration test spawns a REAL pytest to prove non-vacuity end-to-end.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import the module under test. scripts/ is not on sys.path under pytest, so
# add it explicitly (mirrors tests/unit/test_check_doc_claims.py).
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import consume_reviewer_result as crr  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _pass_block(
    *,
    reviewed_commit="abc1234",
    reviewed_head="abc1234",
    commands=None,
    issues=None,
    role="spec",
    working_tree_clean=True,
) -> str:
    """A minimal valid `pass` reviewer-result json (as a string body)."""
    import json

    cmds = commands if commands is not None else [
        {"command": ".venv/bin/python -m pytest tests/unit/test_x.py --runxfail -q",
         "exit_code": 0, "summary": "1 passed in 0.10s"}
    ]
    obj = {
        "schema_version": "reviewer-result/1",
        "role": role,
        "verdict": "pass",
        "reviewed_commit": reviewed_commit,
        "reviewed_head": reviewed_head,
        "working_tree_clean": working_tree_clean,
        "commands": cmds,
        "issues": issues if issues is not None else [],
        "commit_trailer": {"present": True,
                           "expected": "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>",
                           "observed": "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"},
        "unverifiable_reason": None,
        "blocked": None,
    }
    return json.dumps(obj, indent=2)


def _report_md(json_body: str, *, prose="Looks good.") -> str:
    """Wrap a json body in a realistic verification-report markdown event.

    The fence is at column 0 (real mailbox markdown), and the json body is NOT
    dedented (it carries its own json.dumps indentation), so we assemble the
    string from explicit parts rather than textwrap.dedent.
    """
    header = "# operator -> director — verification report\n\n"
    header += f"## Verdict\n{prose}\n\n## RESULT SCHEMA\n\n"
    return f"{header}```json\n{json_body}\n```\n"


# ---------------------------------------------------------------------------
# extract_result_block
# ---------------------------------------------------------------------------

def test_extract_returns_the_reviewer_result_block():
    md = _report_md(_pass_block())
    result = crr.extract_result_block(md)
    assert result is not None
    assert result["schema_version"] == "reviewer-result/1"
    assert result["verdict"] == "pass"


def test_extract_returns_none_when_no_reviewer_result_block():
    md = "# report\n\nNo machine block here, just prose.\n"
    assert crr.extract_result_block(md) is None


def test_extract_ignores_unrelated_json_blocks():
    md = textwrap.dedent(
        """\
        # report

        ```json
        {"some": "other", "schema_version": "not-ours/9"}
        ```
        """
    )
    assert crr.extract_result_block(md) is None


def test_extract_returns_the_last_reviewer_result_block_when_multiple():
    first = _pass_block(reviewed_commit="1111111", reviewed_head="1111111")
    second = _pass_block(reviewed_commit="2222222", reviewed_head="2222222")
    md = _report_md(first) + "\n\n" + _report_md(second)
    result = crr.extract_result_block(md)
    assert result["reviewed_commit"] == "2222222"


def test_extract_raises_on_malformed_reviewer_result_fence():
    # A fence that claims to be our schema but is not valid JSON must surface,
    # not be silently treated as "no block" (that would hide a real defect).
    md = textwrap.dedent(
        """\
        # report

        ```json
        {"schema_version": "reviewer-result/1", "verdict": "pass",,}
        ```
        """
    )
    with pytest.raises(crr.ResultParseError):
        crr.extract_result_block(md)


# ---------------------------------------------------------------------------
# validate_schema
# ---------------------------------------------------------------------------

def test_validate_accepts_a_clean_pass():
    import json
    result = json.loads(_pass_block())
    assert crr.validate_schema(result) == []


def test_validate_rejects_pass_with_nonempty_issues():
    import json
    result = json.loads(_pass_block(issues=[
        {"severity": "minor", "file": "x.py", "line": 1,
         "requirement": "unlisted", "finding": "nit"}
    ]))
    violations = crr.validate_schema(result)
    assert any("pass" in v and "issues" in v for v in violations)


def test_validate_rejects_issues_verdict_with_empty_issues():
    import json
    result = json.loads(_pass_block())
    result["verdict"] = "issues"
    result["issues"] = []
    violations = crr.validate_schema(result)
    assert any("issues" in v and "empty" in v for v in violations)


def test_validate_rejects_unknown_verdict():
    import json
    result = json.loads(_pass_block())
    result["verdict"] = "approved"
    assert crr.validate_schema(result)


def test_validate_utv_requires_empty_issues():
    import json
    result = json.loads(_pass_block())
    result["verdict"] = "unable_to_verify"
    result["unverifiable_reason"] = "U1"
    result["blocked"] = {"command": ".venv missing"}
    result["issues"] = [{"severity": "minor", "file": "x", "line": 1,
                         "requirement": "unlisted", "finding": "y"}]
    violations = crr.validate_schema(result)
    assert any("unable_to_verify" in v and "issues" in v for v in violations)


def test_validate_utv_requires_reason_in_u1_u5():
    import json
    result = json.loads(_pass_block())
    result["verdict"] = "unable_to_verify"
    result["issues"] = []
    result["blocked"] = {"command": "x"}
    result["unverifiable_reason"] = "U9"  # not in U1..U5
    violations = crr.validate_schema(result)
    assert any("unverifiable_reason" in v for v in violations)


def test_validate_utv_requires_blocked_non_null():
    import json
    result = json.loads(_pass_block())
    result["verdict"] = "unable_to_verify"
    result["issues"] = []
    result["unverifiable_reason"] = "U3"
    result["blocked"] = None
    violations = crr.validate_schema(result)
    assert any("blocked" in v for v in violations)


def test_validate_head_must_equal_commit_unless_utv():
    import json
    result = json.loads(_pass_block(reviewed_commit="aaa", reviewed_head="bbb"))
    # verdict is pass but head != commit -> must be flagged (schema forces U4/UTV)
    violations = crr.validate_schema(result)
    assert any("reviewed_head" in v for v in violations)


def test_validate_head_neq_commit_is_ok_when_utv():
    import json
    result = json.loads(_pass_block(reviewed_commit="aaa", reviewed_head="bbb"))
    result["verdict"] = "unable_to_verify"
    result["issues"] = []
    result["unverifiable_reason"] = "U4"
    result["blocked"] = {"command": "rev-parse HEAD != reviewed SHA"}
    assert crr.validate_schema(result) == []


def test_validate_dirty_tree_only_with_utv():
    import json
    result = json.loads(_pass_block())
    result["working_tree_clean"] = False  # pass + dirty tree is contradictory
    violations = crr.validate_schema(result)
    assert any("working_tree_clean" in v for v in violations)


# ---------------------------------------------------------------------------
# parse_pytest_summary — normalize counts, IGNORE the (non-deterministic) duration
# ---------------------------------------------------------------------------

def test_parse_summary_basic_pass():
    assert crr.parse_pytest_summary("12 passed in 3.4s") == {"passed": 12}


def test_parse_summary_multiple_outcomes():
    assert crr.parse_pytest_summary("2 passed, 1 xfailed in 1.20s") == {"passed": 2, "xfailed": 1}


def test_parse_summary_decorated_failed_line():
    assert crr.parse_pytest_summary("===== 1 failed in 0.10s =====") == {"failed": 1}


def test_parse_summary_from_full_output_takes_the_tail():
    output = "test_x.py .                          [100%]\n\n1 passed in 0.05s\n"
    assert crr.parse_pytest_summary(output) == {"passed": 1}


def test_parse_summary_excludes_warnings():
    assert crr.parse_pytest_summary("5 passed, 2 skipped, 1 warning in 4.5s") == {
        "passed": 5, "skipped": 2}


def test_parse_summary_duration_is_ignored():
    # Same outcome, different wall-clock time -> identical normalized summary.
    assert crr.parse_pytest_summary("12 passed in 3.4s") == crr.parse_pytest_summary(
        "12 passed in 9.9s")


# ---------------------------------------------------------------------------
# Command safety — only ever re-run a clean pytest argv, never arbitrary shell
# ---------------------------------------------------------------------------

def test_safe_argv_accepts_plain_pytest():
    argv = crr.safe_pytest_argv(".venv/bin/python -m pytest tests/unit/test_x.py --runxfail -q")
    assert argv is not None
    assert "pytest" in argv


def test_safe_argv_accepts_env_unset_prefix():
    argv = crr.safe_pytest_argv(
        "env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_x.py -q")
    assert argv is not None
    assert argv[0] == "env"


def test_safe_argv_rejects_non_pytest():
    assert crr.safe_pytest_argv("rm -rf /tmp/foo") is None


def test_safe_argv_rejects_shell_chaining():
    assert crr.safe_pytest_argv(".venv/bin/python -m pytest x.py && rm -rf /tmp/foo") is None


def test_safe_argv_rejects_semicolon_injection():
    assert crr.safe_pytest_argv("echo pwned; .venv/bin/python -m pytest x.py") is None


def test_safe_argv_rejects_command_substitution():
    assert crr.safe_pytest_argv(".venv/bin/python -m pytest $(whoami).py") is None


# ---------------------------------------------------------------------------
# recheck_commands — fabrication detection with an injected runner
# ---------------------------------------------------------------------------

def _runner_returning(exit_code, output, calls=None):
    def _run(argv, cwd):
        if calls is not None:
            calls.append(argv)
        return exit_code, output
    return _run


def test_recheck_honest_pass_has_no_finding():
    import json
    result = json.loads(_pass_block(commands=[
        {"command": ".venv/bin/python -m pytest tests/unit/test_x.py --runxfail -q",
         "exit_code": 0, "summary": "1 passed in 0.10s"}
    ]))
    findings = crr.recheck_commands(result, ".", run=_runner_returning(0, "1 passed in 0.42s"))
    assert findings == []


def test_recheck_fabricated_summary_is_a_finding():
    # Reviewer pasted "1 passed" but the command actually FAILS when re-run.
    import json
    result = json.loads(_pass_block(commands=[
        {"command": ".venv/bin/python -m pytest tests/unit/test_x.py --runxfail -q",
         "exit_code": 0, "summary": "1 passed in 0.10s"}
    ]))
    findings = crr.recheck_commands(
        result, ".", run=_runner_returning(1, "===== 1 failed in 0.10s ====="))
    assert len(findings) == 1
    assert findings[0].reported_summary == {"passed": 1}
    assert findings[0].actual_summary == {"failed": 1}


def test_recheck_exit_code_mismatch_is_a_finding():
    import json
    result = json.loads(_pass_block(commands=[
        {"command": ".venv/bin/python -m pytest tests/unit/test_x.py --runxfail -q",
         "exit_code": 0, "summary": "1 passed in 0.10s"}
    ]))
    # Same counts, but reviewer claimed exit 0 while the real run exits 1.
    findings = crr.recheck_commands(
        result, ".", run=_runner_returning(1, "1 passed in 0.10s"))
    assert len(findings) == 1


def test_recheck_skips_non_pytest_commands():
    import json
    calls: list = []
    result = json.loads(_pass_block(commands=[
        {"command": "env -u GIT_INDEX_FILE git rev-parse HEAD",
         "exit_code": 0, "summary": "abc1234"}
    ]))
    findings = crr.recheck_commands(result, ".", run=_runner_returning(0, "x", calls=calls))
    assert findings == []
    assert calls == []  # a non-pytest command is never executed


def test_recheck_never_executes_an_unsafe_command():
    import json
    calls: list = []
    result = json.loads(_pass_block(commands=[
        {"command": ".venv/bin/python -m pytest x.py && rm -rf /tmp/foo",
         "exit_code": 0, "summary": "1 passed in 0.10s"}
    ]))
    crr.recheck_commands(result, ".", run=_runner_returning(0, "x", calls=calls))
    assert calls == []  # shell-chained command is refused, never run


# ---------------------------------------------------------------------------
# Integration: a REAL pytest re-run proves the fabrication check is non-vacuous
# ---------------------------------------------------------------------------

def test_recheck_real_pytest_catches_a_lie(tmp_path):
    # Write a real test file that PASSES, then craft a report claiming it FAILED-
    # ...no: claim it passed when it actually fails. We make a FAILING test and a
    # report that lies "1 passed", and prove the real re-run flags the lie.
    test_file = tmp_path / "test_real_pin.py"
    test_file.write_text("def test_truth():\n    assert 1 == 2\n")  # genuinely FAILS
    cmd = f"{sys.executable} -m pytest {test_file} -q"
    import json
    result = json.loads(_pass_block(commands=[
        {"command": cmd, "exit_code": 0, "summary": "1 passed in 0.01s"}  # the LIE
    ]))
    findings = crr.recheck_commands(result, str(tmp_path))  # real default runner
    assert len(findings) == 1
    assert findings[0].actual_summary == {"failed": 1}


def test_recheck_real_pytest_passes_an_honest_report(tmp_path):
    test_file = tmp_path / "test_real_pin.py"
    test_file.write_text("def test_truth():\n    assert 1 == 1\n")  # genuinely PASSES
    cmd = f"{sys.executable} -m pytest {test_file} -q"
    import json
    result = json.loads(_pass_block(commands=[
        {"command": cmd, "exit_code": 0, "summary": "1 passed in 99.9s"}  # honest counts
    ]))
    findings = crr.recheck_commands(result, str(tmp_path))
    assert findings == []


# ---------------------------------------------------------------------------
# map_severity — reviewer severity -> inventory severity
# ---------------------------------------------------------------------------

def test_map_severity_all_three():
    assert crr.map_severity("critical") == "CRITICAL"
    assert crr.map_severity("important") == "MAJOR"
    assert crr.map_severity("minor") == "MEDIUM"


def test_map_severity_is_case_insensitive():
    assert crr.map_severity("Important") == "MAJOR"


def test_map_severity_rejects_unknown():
    with pytest.raises(ValueError):
        crr.map_severity("blocker")


# ---------------------------------------------------------------------------
# propose_inventory_transitions — propose only, never apply
# ---------------------------------------------------------------------------

def _inventory(commit="abc1234", status="fixed", rid="my-defect"):
    cols = "| id | subsystem | file:line | severity | priority | fail-mode | repro | xfail-pin | lane-owner | shared-lock | wave | status | verifier | notes |\n"
    sep = "|----|-----------|-----------|----------|----------|-----------|-------|-----------|------------|-------------|------|--------|----------|-------|\n"
    row = f"| {rid} | gates | x.py:1 | MAJOR |  | some mode | yes | tests/unit/test_x.py | A |  | 2 | {status} | operator GO | fixed in {commit} |\n"
    return cols + sep + row


def test_propose_pass_advances_fixed_to_verified():
    import json
    result = json.loads(_pass_block(reviewed_commit="abc1234", reviewed_head="abc1234"))
    proposals = crr.propose_inventory_transitions(result, _inventory(commit="abc1234", status="fixed"))
    assert len(proposals) == 1
    assert proposals[0].row_id == "my-defect"
    assert proposals[0].current_status == "fixed"
    assert proposals[0].proposed_status == "verified"


def test_propose_issues_does_not_advance_to_verified():
    import json
    result = json.loads(_pass_block(reviewed_commit="abc1234", reviewed_head="abc1234"))
    result["verdict"] = "issues"
    result["issues"] = [
        {"severity": "important", "file": "x.py", "line": 1,
         "requirement": "R1", "finding": "broken"}
    ]
    proposals = crr.propose_inventory_transitions(result, _inventory(commit="abc1234", status="fixed"))
    assert len(proposals) == 1
    assert proposals[0].proposed_status != "verified"
    assert "MAJOR" in proposals[0].severities


def test_propose_utv_proposes_no_status_change():
    import json
    result = json.loads(_pass_block(reviewed_commit="abc1234", reviewed_head="zzz9999"))
    result["verdict"] = "unable_to_verify"
    result["issues"] = []
    result["unverifiable_reason"] = "U4"
    result["blocked"] = {"command": "HEAD != reviewed SHA"}
    proposals = crr.propose_inventory_transitions(result, _inventory(commit="abc1234", status="fixed"))
    assert len(proposals) == 1
    assert proposals[0].proposed_status == "fixed"  # unchanged — RE-DISPATCH
    assert "RE-DISPATCH" in proposals[0].reason


def test_propose_no_matching_row_yields_no_proposals():
    import json
    result = json.loads(_pass_block(reviewed_commit="deadbee", reviewed_head="deadbee"))
    proposals = crr.propose_inventory_transitions(result, _inventory(commit="abc1234", status="fixed"))
    assert proposals == []


# ---------------------------------------------------------------------------
# iter_reviewer_results — scan the mailbox for events carrying a block
# ---------------------------------------------------------------------------

def _mailbox_repo(tmp_path, *report_bodies):
    sent = tmp_path / "coordination" / "mailbox" / "sent"
    sent.mkdir(parents=True)
    for i, body in enumerate(report_bodies):
        name = f"2026-06-20T0{i}-00-00Z-operator-to-director-verification-report.md"
        (sent / name).write_text(body)
    return tmp_path


def test_iter_reviewer_results_collects_only_events_with_blocks(tmp_path):
    repo = _mailbox_repo(
        tmp_path,
        _report_md(_pass_block()),                 # has a block
        "# report\n\njust prose, no machine block\n",  # no block -> skipped
    )
    results = crr.iter_reviewer_results(repo)
    assert len(results) == 1
    path, block = results[0]
    assert block["schema_version"] == "reviewer-result/1"


# ---------------------------------------------------------------------------
# smoke_check — schema-validate present blocks; NEVER re-run pytest
# ---------------------------------------------------------------------------

def test_smoke_check_zero_blocks_is_ok(tmp_path):
    repo = _mailbox_repo(tmp_path, "# report\n\nno block\n")
    assert crr.smoke_check(repo) == 0


def test_smoke_check_valid_block_is_ok(tmp_path):
    repo = _mailbox_repo(tmp_path, _report_md(_pass_block()))
    assert crr.smoke_check(repo) == 0


def test_smoke_check_flags_a_schema_violation(tmp_path):
    bad = _pass_block(issues=[{"severity": "minor", "file": "x", "line": 1,
                               "requirement": "unlisted", "finding": "nit"}])  # pass + issues
    repo = _mailbox_repo(tmp_path, _report_md(bad))
    assert crr.smoke_check(repo) == 1


def test_smoke_check_does_not_rerun_pytest_so_ignores_a_fabricated_summary(tmp_path):
    # Schema-valid block whose pytest command names a non-existent file with a "1 passed"
    # summary it never could have produced. smoke_check validates SCHEMA ONLY, so it must
    # return 0 here (the fabrication re-run is the on-demand CLI's job, not smoke's).
    block = _pass_block(commands=[
        {"command": ".venv/bin/python -m pytest tests/unit/does_not_exist.py --runxfail -q",
         "exit_code": 0, "summary": "1 passed in 0.10s"}
    ])
    repo = _mailbox_repo(tmp_path, _report_md(block))
    assert crr.smoke_check(repo) == 0


# ---------------------------------------------------------------------------
# consume — orchestration + ok()
# ---------------------------------------------------------------------------

def test_consume_no_block_is_ok(tmp_path):
    report = crr.consume("# report\n\nno block\n", str(tmp_path))
    assert report.block_present is False
    assert report.ok() is True


def test_consume_honest_block_is_ok(tmp_path):
    md = _report_md(_pass_block(commands=[
        {"command": ".venv/bin/python -m pytest x.py --runxfail -q",
         "exit_code": 0, "summary": "1 passed in 0.10s"}
    ]))
    report = crr.consume(md, str(tmp_path), run=_runner_returning(0, "1 passed in 0.9s"))
    assert report.ok() is True
    assert report.verdict == "pass"


def test_consume_detects_fabrication(tmp_path):
    md = _report_md(_pass_block(commands=[
        {"command": ".venv/bin/python -m pytest x.py --runxfail -q",
         "exit_code": 0, "summary": "1 passed in 0.10s"}
    ]))
    report = crr.consume(md, str(tmp_path), run=_runner_returning(1, "1 failed in 0.10s"))
    assert report.ok() is False
    assert len(report.fabrications) == 1


# ---------------------------------------------------------------------------
# main — CLI exit codes
# ---------------------------------------------------------------------------

def test_main_usage_error_with_no_args():
    assert crr.main([]) == 2


def test_main_returns_0_on_an_honest_event(tmp_path):
    # git-only command -> recheck skips it (non-pytest), so no subprocess is spawned.
    body = _report_md(_pass_block(commands=[
        {"command": "env -u GIT_INDEX_FILE git rev-parse HEAD",
         "exit_code": 0, "summary": "abc1234"}
    ]))
    event = tmp_path / "event.md"
    event.write_text(body)
    assert crr.main([str(event)]) == 0


def test_main_returns_1_on_a_schema_violation(tmp_path):
    bad = _pass_block(
        issues=[{"severity": "minor", "file": "x", "line": 1,
                 "requirement": "unlisted", "finding": "nit"}],  # pass + issues
        commands=[{"command": "env -u GIT_INDEX_FILE git rev-parse HEAD",
                   "exit_code": 0, "summary": "abc1234"}],
    )
    event = tmp_path / "event.md"
    event.write_text(_report_md(bad))
    assert crr.main([str(event)]) == 1


# ===========================================================================
# Hardening (from independent Lane-V code-quality review)
# ===========================================================================

# --- C1: safe_pytest_argv must require pytest be EXECUTED (-m pytest / pytest
#         console script), not merely PRESENT as a token (ACE hole) ------------

def test_safe_argv_rejects_python_running_a_script_with_pytest_arg():
    # `python /tmp/evil.py pytest` runs evil.py; 'pytest' is just a positional arg.
    assert crr.safe_pytest_argv("python /tmp/evil.py pytest") is None


def test_safe_argv_rejects_env_execing_arbitrary_binary():
    # `env ./evil pytest` makes env exec ./evil; 'pytest' is just a token.
    assert crr.safe_pytest_argv("env ./evil pytest") is None


def test_safe_argv_rejects_python_without_dash_m_pytest():
    assert crr.safe_pytest_argv("python tests/run_things.py") is None


def test_safe_argv_accepts_dash_m_pytest():
    assert crr.safe_pytest_argv(".venv/bin/python -m pytest x.py --runxfail -q") is not None


def test_safe_argv_accepts_pytest_console_script():
    # The legitimate console-script form was wrongly rejected before the fix.
    argv = crr.safe_pytest_argv(".venv/bin/pytest x.py -q")
    assert argv is not None
    assert Path(argv[0]).name == "pytest"


def test_safe_argv_rejects_env_path_injection_pytest():
    # `env PATH=...` lets env resolve a HOSTILE `pytest` -> arbitrary code execution.
    assert crr.safe_pytest_argv("env PATH=/tmp/evilbin pytest tests/unit/test_x.py -q") is None


def test_safe_argv_rejects_env_path_injection_python():
    assert crr.safe_pytest_argv("env PATH=/tmp/evilbin python -m pytest x.py -q") is None


def test_safe_argv_rejects_env_assignment_even_after_decoy_unset():
    assert crr.safe_pytest_argv("env -u GIT_INDEX_FILE PATH=/tmp/evilbin pytest x.py -q") is None


def test_safe_argv_rejects_any_env_assignment():
    # No NAME=value assignment is allowed in the env prefix — the repo idiom is `-u NAME`.
    assert crr.safe_pytest_argv("env FOO=1 .venv/bin/python -m pytest x.py -q") is None


def test_safe_argv_still_accepts_env_unset_idiom():
    # The legitimate `env -u GIT_INDEX_FILE` unset prefix must keep working.
    argv = crr.safe_pytest_argv("env -u GIT_INDEX_FILE .venv/bin/python -m pytest x.py -q")
    assert argv is not None and argv[0] == "env"


# --- C1.2: residual ACE vectors that survived the C1.1 env-assignment fix -----
#   (a) a malicious `env` TOKEN: `Path('/tmp/evil/env').name == 'env'` used to qualify
#       as the env prefix, so the post-env launcher (.venv/bin/python, in-repo) passed
#       the escape check while subprocess.run still exec'd argv[0] = /tmp/evil/env.
#   (b) a BARE-basename launcher (`pytest`, `python`) is resolved via PATH — the
#       redirection vector itself; require a path separator (per the C1 hardening rec).

def test_safe_argv_rejects_malicious_env_token_path():
    # The env token must be the bare word `env`; a path whose basename is `env`
    # (which subprocess.run would actually exec) must NOT qualify as the env prefix.
    assert crr.safe_pytest_argv(
        "/tmp/evil/env -u GIT_INDEX_FILE .venv/bin/python -m pytest "
        "tests/unit/test_consume_reviewer_result.py -q") is None


def test_safe_argv_rejects_bare_basename_pytest_launcher():
    # No path separator -> resolved via PATH -> the redirection vector. Refuse.
    assert crr.safe_pytest_argv("pytest tests/unit/test_x.py -q") is None


def test_safe_argv_rejects_bare_basename_python_launcher():
    assert crr.safe_pytest_argv("python -m pytest tests/unit/test_x.py -q") is None


def test_recheck_never_execs_a_malicious_env_token(tmp_path):
    # Defense in depth: even with an in-repo post-env launcher and an in-repo target,
    # recheck must NEVER spawn `/tmp/evil/env`. Real repo_root so .venv/bin/python is
    # the in-repo (whitelisted) launcher — proving it's the env TOKEN that's refused.
    import json
    calls: list = []
    target = "tests/unit/test_consume_reviewer_result.py"  # a real in-repo path
    result = json.loads(_pass_block(commands=[
        {"command": f"/tmp/evil/env -u GIT_INDEX_FILE .venv/bin/python -m pytest {target} -q",
         "exit_code": 0, "summary": "1 passed in 0.10s"}
    ]))
    crr.recheck_commands(result, str(crr._REPO_ROOT), run=_runner_returning(0, "x", calls=calls))
    assert calls == []  # the attacker's env binary is never executed


# --- C2: never execute a re-run whose target escapes the repo root -----------

def test_recheck_refuses_target_outside_repo(tmp_path):
    calls: list = []
    outside = "/etc/passwd_dir/test_evil.py"  # absolute, outside repo_root
    import json
    result = json.loads(_pass_block(commands=[
        {"command": f".venv/bin/python -m pytest {outside} -q",
         "exit_code": 0, "summary": "1 passed in 0.10s"}
    ]))
    findings = crr.recheck_commands(result, str(tmp_path), run=_runner_returning(0, "x", calls=calls))
    assert calls == []  # target escapes repo_root -> never executed


def test_recheck_allows_target_inside_repo(tmp_path):
    calls: list = []
    inside = tmp_path / "tests" / "test_x.py"
    import json
    result = json.loads(_pass_block(commands=[
        {"command": f".venv/bin/python -m pytest {inside} -q",
         "exit_code": 0, "summary": "1 passed in 0.10s"}
    ]))
    crr.recheck_commands(result, str(tmp_path), run=_runner_returning(0, "1 passed in 0.1s", calls=calls))
    assert len(calls) == 1  # contained target -> executed


def test_recheck_refuses_absolute_launcher_outside_repo(tmp_path):
    # `/tmp/evil/pytest` passes shape-vetting (basename 'pytest') but is an arbitrary
    # binary outside the repo -> must never be executed.
    calls: list = []
    import json
    result = json.loads(_pass_block(commands=[
        {"command": "/tmp/evil/pytest x.py", "exit_code": 0, "summary": "1 passed in 0.10s"}
    ]))
    crr.recheck_commands(result, str(tmp_path), run=_runner_returning(0, "x", calls=calls))
    assert calls == []


def test_recheck_refuses_env_with_absolute_launcher_outside_repo(tmp_path):
    calls: list = []
    import json
    result = json.loads(_pass_block(commands=[
        {"command": "env -u GIT_INDEX_FILE /tmp/evil/python -m pytest x.py -q",
         "exit_code": 0, "summary": "1 passed in 0.10s"}
    ]))
    crr.recheck_commands(result, str(tmp_path), run=_runner_returning(0, "x", calls=calls))
    assert calls == []


def test_recheck_allows_repo_relative_launcher(tmp_path):
    calls: list = []
    import json
    result = json.loads(_pass_block(commands=[
        {"command": ".venv/bin/pytest tests/test_x.py -q",
         "exit_code": 0, "summary": "1 passed in 0.10s"}
    ]))
    crr.recheck_commands(result, str(tmp_path), run=_runner_returning(0, "1 passed in 0.1s", calls=calls))
    assert len(calls) == 1  # repo-relative launcher + contained target -> executed


def test_recheck_does_not_skip_the_env_unset_python_idiom():
    # The repo's canonical pin idiom `env -u GIT_INDEX_FILE .venv/bin/python -m pytest <in-repo>`
    # must be RE-RUN, not silently skipped: the launcher (.venv/bin/python, a symlink resolving
    # outside the repo) must NOT be mis-scanned as an out-of-repo TARGET. Uses the real repo so
    # the .venv symlink is present.
    import json
    calls: list = []
    target = "tests/unit/test_consume_reviewer_result.py"  # a real in-repo path
    result = json.loads(_pass_block(commands=[
        {"command": f"env -u GIT_INDEX_FILE .venv/bin/python -m pytest {target} -q",
         "exit_code": 0, "summary": "1 passed in 0.10s"}
    ]))
    crr.recheck_commands(result, str(crr._REPO_ROOT), run=_runner_returning(0, "1 passed in 0.1s", calls=calls))
    assert len(calls) == 1  # the idiom is re-run, not skipped


# --- I1: CRLF line endings must not drop a present block ----------------------

def test_extract_handles_crlf_line_endings():
    md = _report_md(_pass_block()).replace("\n", "\r\n")
    result = crr.extract_result_block(md)
    assert result is not None
    assert result["verdict"] == "pass"


# --- I2: a wrong-type block is a clean schema violation, never a crash --------

def test_validate_flags_non_list_commands():
    import json
    result = json.loads(_pass_block())
    result["commands"] = "not-a-list"
    assert any("commands" in v for v in crr.validate_schema(result))


def test_validate_flags_non_list_issues():
    import json
    result = json.loads(_pass_block())
    result["issues"] = "not-a-list"
    assert any("issues" in v for v in crr.validate_schema(result))


def test_smoke_check_does_not_crash_on_wrong_type_commands(tmp_path):
    import json
    block = json.loads(_pass_block())
    block["commands"] = "not-a-list"
    md = _report_md(json.dumps(block))
    repo = _mailbox_repo(tmp_path, md)
    assert crr.smoke_check(repo) == 1  # clean fail, no exception


# --- I3: a malformed UNRELATED fence (version only in prose, no schema_version
#         key) must be skipped, not raised as our malformed block -------------

def test_extract_ignores_malformed_fence_without_schema_version_key():
    md = '# r\n\n```json\n{"note": "see the reviewer-result/1 spec",,}\n```\n'
    assert crr.extract_result_block(md) is None


# --- NIT-1 (spec review): the summary-comparison limb has its own RED test ----

def test_recheck_flags_summary_only_mismatch_when_exit_matches():
    import json
    result = json.loads(_pass_block(commands=[
        {"command": ".venv/bin/python -m pytest x.py --runxfail -q",
         "exit_code": 0, "summary": "12 passed in 1.0s"}
    ]))
    # Same exit code (0), but the counts differ -> the summary limb must fire alone.
    findings = crr.recheck_commands(
        result, ".", run=_runner_returning(0, "8 passed, 4 skipped in 1.0s"))
    assert len(findings) == 1
    assert findings[0].reported_summary == {"passed": 12}
    assert findings[0].actual_summary == {"passed": 8, "skipped": 4}


# --- M2: short-SHA match must not over-match a substring of a longer SHA ------

def test_propose_does_not_match_sha_as_substring_of_longer_token():
    import json
    result = json.loads(_pass_block(reviewed_commit="abc1234", reviewed_head="abc1234"))
    # Row cites a DIFFERENT, longer SHA that merely contains 'abc1234' as a prefix.
    inv = _inventory(commit="abc12349999", status="fixed", rid="other-defect")
    proposals = crr.propose_inventory_transitions(result, inv)
    assert proposals == []
