"""Regression tests for .codex/hooks/guard-git-index.sh."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / ".codex" / "hooks" / "guard-git-index.sh"


def _run_hook(command: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["GIT_INDEX_FILE"] = "/tmp/codex-seat-index-test"
    payload = json.dumps({"tool_input": {"command": command}})
    return subprocess.run(
        [str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
    )


def test_quoted_pipe_regex_does_not_look_like_shell_pipe() -> None:
    result = _run_hook("rg -n 'git|pytest|GIT_INDEX_FILE' .codex/hooks tests/unit")
    assert result.returncode == 0, result.stderr


def test_bare_pytest_is_blocked_under_seat_index() -> None:
    result = _run_hook(".venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py -q")
    assert result.returncode == 2
    assert "env -u GIT_INDEX_FILE" in result.stderr


def test_bare_git_add_is_blocked_under_seat_index() -> None:
    result = _run_hook("git add scripts/protocol_capacity.py")
    assert result.returncode == 2
    assert "git add" in result.stderr


def test_env_u_git_index_prefix_is_allowed() -> None:
    result = _run_hook("env -u GIT_INDEX_FILE git add scripts/protocol_capacity.py")
    assert result.returncode == 0, result.stderr
