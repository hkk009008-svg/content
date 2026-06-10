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


def _subscribe_misuse(tree: ast.AST):
    """R1: `fal_client.subscribe` referenced anywhere except as a direct
    call's func — `sub = fal_client.subscribe`, `runner(fal_client.subscribe)`
    — dodges the call-site scan while keeping the untimed behavior."""
    call_funcs = {
        id(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)
    }
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "subscribe"
            and isinstance(node.value, ast.Name)
            and node.value.id == "fal_client"
            and id(node) not in call_funcs
        ):
            yield node


def _fal_client_aliases(tree: ast.AST):
    """R2: a bare `fal_client` Name outside attribute-receiver position —
    `fc = fal_client`, `self.client = fal_client`, passing the module —
    creates an alias the receiver-keyed scans can never see."""
    receiver_ids = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
    }
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Name)
            and node.id == "fal_client"
            and id(node) not in receiver_ids
        ):
            yield node


def _local_fal_timeout_defs(tree: ast.AST):
    """R3a: a FAL_TIMEOUT_*-named assignment in a production module —
    `FAL_TIMEOUT_HACK = None` satisfies the lexical named-bound check
    while reinstating the indefinite hang."""
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for t in targets:
            if isinstance(t, ast.Name) and t.id.startswith("FAL_TIMEOUT_"):
                yield t


def _limits_imports(tree: ast.AST) -> set:
    return {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "cinema.fal_limits"
        for alias in node.names
    }


def _unprovenanced_timeouts(tree: ast.AST):
    """R3b: client_timeout=FAL_TIMEOUT_X is valid only when X is imported
    from cinema.fal_limits in the same module (spelling is not provenance)."""
    imported = _limits_imports(tree)
    for call in _fal_subscribe_calls(tree):
        for kw in call.keywords:
            if kw.arg != "client_timeout":
                continue
            v = kw.value
            if (
                isinstance(v, ast.Name)
                and v.id.startswith("FAL_TIMEOUT_")
                and v.id not in imported
            ):
                yield v


def _non_positive_limit_defs(tree: ast.AST):
    """R4: in the limits module itself, every module-level FAL_TIMEOUT_*
    must be a positive numeric literal — `FAL_TIMEOUT_DISABLED = None`
    in fal_limits.py would poison every importer at once."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id.startswith("FAL_TIMEOUT_"):
                v = node.value
                ok = (
                    isinstance(v, ast.Constant)
                    and isinstance(v.value, (int, float))
                    and not isinstance(v.value, bool)
                    and v.value > 0
                )
                if not ok:
                    yield t


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
        # client_timeout must be a FAL_TIMEOUT_* NAME IMPORTED FROM
        # cinema.fal_limits — not an inline literal, not an attribute form
        # (no production user exists; dropping the allowance closes a dodge),
        # and not a same-spelling local that could be bound to None and
        # silently reinstate the indefinite hang this suite exists to prevent.
        offenders = []
        for path in _production_py_files():
            tree = _parsed(path)
            imported = _limits_imports(tree)
            for call in _fal_subscribe_calls(tree):
                for kw in call.keywords:
                    if kw.arg != "client_timeout":
                        continue
                    value = kw.value
                    named_ok = (
                        isinstance(value, ast.Name)
                        and value.id.startswith("FAL_TIMEOUT_")
                        and value.id in imported
                    )
                    if not named_ok:
                        offenders.append(
                            f"{path.relative_to(REPO_ROOT)}:{call.lineno}"
                        )
        assert offenders == [], (
            "client_timeout must be a FAL_TIMEOUT_* name imported from "
            "cinema.fal_limits: " + ", ".join(offenders)
        )


class TestGuardDodgeRules:
    """Closes the adversarial-developer dodges the base guard misses
    (operator latents, 23:42:25Z report): assignment-aliasing of the
    function or the module, and FAL_TIMEOUT_*-named values without
    provenance from cinema/fal_limits.py. Synthetic snippets double as
    mutation tests: every dodge shape must be DETECTED, every legit
    shape must pass."""

    # --- R1: `fal_client.subscribe` outside direct-call position ---

    def test_r1_detects_assignment_alias(self):
        tree = ast.parse(
            "import fal_client\n"
            "sub = fal_client.subscribe\n"
            "sub(arg)\n"
        )
        assert len(list(_subscribe_misuse(tree))) == 1

    def test_r1_detects_callback_pass(self):
        tree = ast.parse(
            "import fal_client\n"
            "runner(fal_client.subscribe)\n"
        )
        assert len(list(_subscribe_misuse(tree))) == 1

    def test_r1_passes_direct_call(self):
        tree = ast.parse(
            "import fal_client\n"
            "fal_client.subscribe(m, client_timeout=FAL_TIMEOUT_VIDEO_S)\n"
        )
        assert list(_subscribe_misuse(tree)) == []

    def test_r1_repo_clean(self):
        offenders = [
            f"{p.relative_to(REPO_ROOT)}:{n.lineno}"
            for p in _production_py_files()
            for n in _subscribe_misuse(_parsed(p))
        ]
        assert offenders == [], (
            "`fal_client.subscribe` referenced outside a direct call "
            "(alias dodge): " + ", ".join(offenders)
        )

    # --- R2: aliasing the module object itself ---

    def test_r2_detects_module_alias(self):
        tree = ast.parse("import fal_client\nfc = fal_client\n")
        assert len(list(_fal_client_aliases(tree))) == 1

    def test_r2_detects_attribute_stash(self):
        tree = ast.parse("import fal_client\nself.client = fal_client\n")
        assert len(list(_fal_client_aliases(tree))) == 1

    def test_r2_passes_attribute_access(self):
        tree = ast.parse(
            "import fal_client\n"
            "fal_client.upload_file(p)\n"
            "fal_client.subscribe(m, client_timeout=FAL_TIMEOUT_VIDEO_S)\n"
        )
        assert list(_fal_client_aliases(tree)) == []

    def test_r2_repo_clean(self):
        offenders = [
            f"{p.relative_to(REPO_ROOT)}:{n.lineno}"
            for p in _production_py_files()
            for n in _fal_client_aliases(_parsed(p))
        ]
        assert offenders == [], (
            "bare `fal_client` aliased/passed (module-alias dodge): "
            + ", ".join(offenders)
        )

    # --- R3: FAL_TIMEOUT_* provenance ---

    def test_r3_detects_local_fal_timeout_assignment(self):
        tree = ast.parse("FAL_TIMEOUT_HACK = None\n")
        assert len(list(_local_fal_timeout_defs(tree))) == 1

    def test_r3_passes_import_from_limits(self):
        tree = ast.parse(
            "from cinema.fal_limits import FAL_TIMEOUT_VIDEO_S\n"
            "import fal_client\n"
            "fal_client.subscribe(m, client_timeout=FAL_TIMEOUT_VIDEO_S)\n"
        )
        assert list(_local_fal_timeout_defs(tree)) == []
        assert list(_unprovenanced_timeouts(tree)) == []

    def test_r3_detects_unimported_timeout_name(self):
        # Name is FAL_TIMEOUT_-shaped but never imported from
        # cinema.fal_limits — lexically passes the old check, fails now.
        tree = ast.parse(
            "import fal_client\n"
            "FAL_TIMEOUT_LOCAL = None\n"
            "fal_client.subscribe(m, client_timeout=FAL_TIMEOUT_LOCAL)\n"
        )
        assert len(list(_unprovenanced_timeouts(tree))) == 1

    def test_r3_repo_clean(self):
        local_defs = [
            f"{p.relative_to(REPO_ROOT)}:{n.lineno}"
            for p in _production_py_files()
            if p.name != "fal_limits.py"
            for n in _local_fal_timeout_defs(_parsed(p))
        ]
        assert local_defs == [], (
            "FAL_TIMEOUT_* assigned outside cinema/fal_limits.py: "
            + ", ".join(local_defs)
        )
        unprov = [
            f"{p.relative_to(REPO_ROOT)}:{n.lineno}"
            for p in _production_py_files()
            for n in _unprovenanced_timeouts(_parsed(p))
        ]
        assert unprov == [], (
            "client_timeout uses a FAL_TIMEOUT_* name not imported from "
            "cinema.fal_limits: " + ", ".join(unprov)
        )

    # --- R4: the limits module itself defines positive numeric literals ---

    def test_r4_detects_none_valued_limit(self):
        tree = ast.parse("FAL_TIMEOUT_DISABLED = None\n")
        assert len(list(_non_positive_limit_defs(tree))) == 1

    def test_r4_detects_zero_limit(self):
        tree = ast.parse("FAL_TIMEOUT_ZERO = 0\n")
        assert len(list(_non_positive_limit_defs(tree))) == 1

    def test_r4_passes_positive_literal(self):
        tree = ast.parse("FAL_TIMEOUT_VIDEO_S = 600\n")
        assert list(_non_positive_limit_defs(tree)) == []

    def test_r4_real_limits_module_clean(self):
        tree = _parsed(REPO_ROOT / "cinema" / "fal_limits.py")
        offenders = [n.lineno for n in _non_positive_limit_defs(tree)]
        assert offenders == [], (
            f"non-positive/non-literal FAL_TIMEOUT_* in fal_limits.py "
            f"at lines {offenders}"
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
