"""Regression tests for .claude/hooks/guard-bash-safety.sh.

The guard ports six previously-inert `.claude/hookify.*.local.md` rules plus
three measurement-instrument traps into a hook that actually executes.

Two properties matter and are tested separately:

* it CATCHES the mistakes (a guard that cannot fail proves nothing), and
* it does NOT catch legitimate commands. The false-positive tests carry more
  weight than the catches: a guard that cries wolf gets disabled, and a
  disabled guard is exactly the inert state this replaces.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / ".claude" / "hooks" / "guard-bash-safety.sh"

BLOCK = 2
ALLOW = 0


def _run(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(HOOK)],
        input=json.dumps({"tool_input": {"command": command}}),
        capture_output=True,
        text=True,
    )


def test_hook_is_executable() -> None:
    assert HOOK.is_file()
    assert HOOK.stat().st_mode & 0o111, "hook must be executable to ever run"


# --- fail-open: a broken guard must never halt work ------------------------


@pytest.mark.parametrize(
    "payload",
    [
        "not json at all",
        "{}",
        '{"tool_input": null}',
        '{"tool_input": {"command": null}}',
        '{"tool_input": {"command": ""}}',
        '[1, 2, 3]',
    ],
)
def test_malformed_payloads_fail_open(payload: str) -> None:
    result = subprocess.run(
        [str(HOOK)], input=payload, capture_output=True, text=True
    )
    assert result.returncode == ALLOW, result.stderr


# --- ported hookify rules: the catches -------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "git push --force origin main",
        "git push -f origin main",
        "git -C /tmp/repo push --force",
    ],
)
def test_force_push_is_blocked(command: str) -> None:
    result = _run(command)
    assert result.returncode == BLOCK
    assert "force-push" in result.stderr


@pytest.mark.parametrize(
    "command",
    ["git add -A", "git add --all", "git add .", "git add . && git commit -m x"],
)
def test_bulk_git_add_is_blocked(command: str) -> None:
    result = _run(command)
    assert result.returncode == BLOCK
    assert "bulk" in result.stderr


@pytest.mark.parametrize(
    "command",
    ["git commit --no-verify -m x", "git commit --no-gpg-sign -m x"],
)
def test_hook_and_signing_bypass_is_blocked(command: str) -> None:
    result = _run(command)
    assert result.returncode == BLOCK
    assert "hooks or signing" in result.stderr


@pytest.mark.parametrize(
    "command",
    ["pytest tests/unit -q", "python3 -m pytest tests/ -q", "python -m pytest"],
)
def test_pytest_outside_the_venv_is_blocked(command: str) -> None:
    result = _run(command)
    assert result.returncode == BLOCK
    assert "venv" in result.stderr


# --- instrument traps: the catches -----------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        'scripts/check.py | tail -5; echo "EXIT=$?"',
        "make lint | head; echo $?",
        'a | b && echo "rc=$?"',
        # Deliberately caught even where the reading happens to be harmless.
        # `$?` after ANY pipeline is ambiguous about which status it reports,
        # and the guard's suggested fix costs seconds. Over-blocking here is
        # cheaper than the phantom finding an unnoticed misreading produced.
        "ls | wc -l; echo $?",
    ],
)
def test_exit_code_after_a_pipeline_is_blocked(command: str) -> None:
    """`cmd | tail; echo $?` reports tail's status. Observed live: a --check
    that printed STALE was recorded as exit 0."""

    result = _run(command)
    assert result.returncode == BLOCK
    assert "$?" in result.stderr


@pytest.mark.parametrize(
    "command",
    ["ps aux | grep -c pytest", "ps -ef | grep -c python", "ps aux | grep -ci node"],
)
def test_self_matching_process_count_is_blocked(command: str) -> None:
    """Observed live: one pytest run counted as five, because the counting
    shell's own command line contained the word."""

    result = _run(command)
    assert result.returncode == BLOCK
    assert "self-matching" in result.stderr


# --- false positives: legitimate commands must pass ------------------------


@pytest.mark.parametrize(
    "command",
    [
        # The correct forms the guard exists to steer toward.
        'scripts/check.py > out.txt 2>&1; echo "EXIT=$?"',
        "make lint | tail -5; echo ${PIPESTATUS[0]}",
        "ps aux | grep -c '[p]ytest'",
        "env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/ -q",
        ".venv/bin/python -m pytest tests/unit -q",
        # Ordinary git work.
        "git push origin main",
        "git push --force-with-lease origin feature",
        "git add path/one.py path/two.py",
        "git add -u",
        "git commit -m 'fix: thing'",
        "git status --short",
        # `git`, `pytest`, `-A` and `.` appearing as ARGUMENTS, not commands.
        "grep -rn 'git add .' docs/",
        "rg -n 'pytest|git push --force' .claude/hooks",
        "echo 'git add --all is banned here'",
        # A quoted pipe inside a regex is not a shell pipeline.
        "rg -n 'foo|bar' src/; echo $?",
        # Counting non-process things is unaffected.
        "cat file.txt | grep -c pattern",
    ],
)
def test_legitimate_commands_are_allowed(command: str) -> None:
    result = _run(command)
    assert result.returncode == ALLOW, (
        f"false positive on a legitimate command: {command}\n{result.stderr}"
    )


def test_guard_is_registered_in_checked_in_settings() -> None:
    """An unregistered hook is exactly the inert state this replaces."""

    settings = json.loads((ROOT / ".claude" / "settings.json").read_text())
    commands = [
        hook.get("command", "")
        for entry in settings.get("hooks", {}).get("PreToolUse", [])
        for hook in entry.get("hooks", [])
    ]
    assert any("guard-bash-safety.sh" in c for c in commands), (
        "guard-bash-safety.sh is not wired into .claude/settings.json"
    )
