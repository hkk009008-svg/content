"""Regression tests for full .claude/hooks/update-state.sh behavior."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent
HOOK_PATH = ROOT / ".claude" / "hooks" / "update-state.sh"


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("GIT_INDEX_FILE", None)
    return env


def _init_repo(tmp: Path) -> dict[str, str]:
    env = _clean_env()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp, env=env, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp,
        env=env,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp,
        env=env,
        check=True,
    )
    (tmp / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp, env=env, check=True)
    return env


def test_state_regen_uses_default_index_when_seat_index_is_bad():
    """A bad per-seat index must not make the PostToolUse hook exit 128."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        env = _init_repo(tmp)

        hook_dir = tmp / ".claude" / "hooks"
        hook_dir.mkdir(parents=True)
        shutil.copy2(HOOK_PATH, hook_dir / "update-state.sh")
        (tmp / ".gitignore").write_text(
            "STATE.md\ncoordination/presence/\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "add", ".claude/hooks/update-state.sh", ".gitignore"],
            cwd=tmp,
            env=env,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-q", "-m", "add hook"],
            cwd=tmp,
            env=env,
            check=True,
        )

        bad_index = tmp / ".git" / "index-codex-test"
        bad_index.write_text("not a git index\n", encoding="utf-8")
        env["GIT_INDEX_FILE"] = str(bad_index)
        env["CLAUDE_SEAT"] = "operator"

        result = subprocess.run(
            ["bash", str(hook_dir / "update-state.sh")],
            cwd=tmp,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, (
            f"hook should fail open around a bad seat index; "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        state = (tmp / "STATE.md").read_text(encoding="utf-8")
        assert "- **Working tree:** clean" in state
