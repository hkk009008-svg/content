"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_run_merge_gate_protected_main.py -q"""

import contextlib
import io


def _run(argv):
    from scripts.run_merge_gate import main
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()


def test_refs_heads_main_requires_explicit_allow_flag(tmp_path, monkeypatch):
    rc, out, err = _run(["--repo-dir", str(tmp_path), "--main-ref", "refs/heads/main", "--run-once"])
    assert rc == 2
    assert "refusing protected main" in err


def test_refs_heads_main_allow_still_fails_closed_without_deployment_preflight(tmp_path, monkeypatch):
    rc, out, err = _run(["--repo-dir", str(tmp_path), "--main-ref", "refs/heads/main",
                         "--allow-protected-main", "--run-once"])
    assert rc == 1
    assert "protected-main deployment controls unavailable" in err
