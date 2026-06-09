"""Guard: every production `fal_client.subscribe` call passes `client_timeout`.

fal_client 1.0.0 waits INDEFINITELY when `client_timeout` is unset — an
untimed subscribe is a whole-pipeline stall hazard (cycle-18 roadmap item:
video-gen timeouts; observed class: a hung FAL job blocks the run forever
instead of failing into the provider cascade). On expiry the SDK cancels
the remote request and raises `FalClientTimeoutError` (an `Exception`
subclass), which the call sites' existing cascade/fallback handlers route
around.

AST-based so any NEW call site fails loud here until it picks a bound from
`cinema/fal_limits.py`. Scripts (ephemeral pod drivers), tests, and
worktree copies are out of scope.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Directory parts that are not production pipeline code.
_EXCLUDED_PARTS = {
    ".venv", "node_modules", ".claude", ".git",
    "tests", "scripts", "logs", "web", "docs",
}


def _production_py_files():
    for path in sorted(REPO_ROOT.rglob("*.py")):
        rel_parts = path.relative_to(REPO_ROOT).parts
        if _EXCLUDED_PARTS.intersection(rel_parts):
            continue
        yield path


def _parsed(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"))


def _fal_subscribe_calls(tree: ast.AST):
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "subscribe"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "fal_client"
        ):
            yield node


class TestFalSubscribeClientTimeout:
    def test_every_production_subscribe_passes_client_timeout(self):
        violations = []
        total = 0
        for path in _production_py_files():
            for call in _fal_subscribe_calls(_parsed(path)):
                total += 1
                if "client_timeout" not in {kw.arg for kw in call.keywords}:
                    violations.append(
                        f"{path.relative_to(REPO_ROOT)}:{call.lineno}"
                    )
        assert total > 0, "guard found no fal_client.subscribe calls — scan broken?"
        assert violations == [], (
            "fal_client.subscribe without client_timeout (indefinite-hang "
            "hazard — pick a bound from cinema/fal_limits.py): "
            + ", ".join(violations)
        )

    def test_no_aliased_or_bare_import_dodges_the_guard(self):
        # The AST guard matches the `fal_client.subscribe(...)` attribute form
        # only; both `from fal_client import subscribe` and
        # `import fal_client as fc` would silently dodge it.
        for path in _production_py_files():
            for node in ast.walk(_parsed(path)):
                if isinstance(node, ast.ImportFrom) and node.module == "fal_client":
                    imported = {alias.name for alias in node.names}
                    assert "subscribe" not in imported, (
                        f"{path.relative_to(REPO_ROOT)}:{node.lineno}: "
                        "`from fal_client import subscribe` dodges the timeout guard"
                    )
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert not (
                            alias.name == "fal_client" and alias.asname
                        ), (
                            f"{path.relative_to(REPO_ROOT)}:{node.lineno}: "
                            f"`import fal_client as {alias.asname}` dodges the timeout guard"
                        )


class TestFalLimits:
    def test_bounds_exist_and_are_sane(self):
        from cinema.fal_limits import (
            FAL_TIMEOUT_IMAGE_S,
            FAL_TIMEOUT_TALKING_HEAD_S,
            FAL_TIMEOUT_VIDEO_S,
        )

        # Video class must clear the observed Kling i2v slow tail (178-195s)
        # with the same headroom rationale as kling_native's 300s poll bound,
        # while still bounding a genuinely stuck job.
        assert 300 <= FAL_TIMEOUT_VIDEO_S <= 1800
        # Image class: FLUX fallbacks are seconds-fast; bound absorbs queue wait.
        assert 60 <= FAL_TIMEOUT_IMAGE_S <= 600
        # Talking-head generation scales with audio length: measured ~40x
        # realtime locally (logs/_lipsync_gen_test.log: 3.84s audio -> 156s
        # wall), so a contract-legal 60s job extrapolates past 600s and a
        # 600s bound would CANCEL legitimately progressing long-form jobs
        # (silent Omnihuman -> Aurora-720p downgrade). Review wf_e0d1765b.
        assert 900 <= FAL_TIMEOUT_TALKING_HEAD_S <= 3600
        assert FAL_TIMEOUT_IMAGE_S < FAL_TIMEOUT_VIDEO_S < FAL_TIMEOUT_TALKING_HEAD_S

    def test_production_sites_use_named_bounds_not_magic_numbers(self):
        # client_timeout must reference a FAL_TIMEOUT_* name (directly or via
        # attribute) — not an inline literal, and not an arbitrary variable
        # that could be bound to None and silently reinstate the indefinite
        # hang this suite exists to prevent.
        offenders = []
        for path in _production_py_files():
            for call in _fal_subscribe_calls(_parsed(path)):
                for kw in call.keywords:
                    if kw.arg != "client_timeout":
                        continue
                    value = kw.value
                    named_ok = (
                        isinstance(value, ast.Name)
                        and value.id.startswith("FAL_TIMEOUT_")
                    ) or (
                        isinstance(value, ast.Attribute)
                        and value.attr.startswith("FAL_TIMEOUT_")
                    )
                    if not named_ok:
                        offenders.append(
                            f"{path.relative_to(REPO_ROOT)}:{call.lineno}"
                        )
        assert offenders == [], (
            "client_timeout must be a FAL_TIMEOUT_* name from "
            "cinema/fal_limits.py: " + ", ".join(offenders)
        )


class TestSeedancePollTimed:
    def test_no_untimed_requests_calls_in_phase_c_ffmpeg(self):
        # The Seedance status poll (`requests.get(poll_url, ...)`) hung
        # indefinitely per iteration when FAL/Seedance stalled mid-poll;
        # every requests.get/post in the module must carry timeout=.
        tree = _parsed(REPO_ROOT / "phase_c_ffmpeg.py")
        untimed = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"get", "post"}
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "requests"
            and "timeout" not in {kw.arg for kw in node.keywords}
        ]
        assert untimed == [], (
            f"untimed requests call(s) in phase_c_ffmpeg.py at lines {untimed}"
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
