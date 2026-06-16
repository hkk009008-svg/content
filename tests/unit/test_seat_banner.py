from __future__ import annotations

import sys
from pathlib import Path


_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import seat_banner  # noqa: E402


def test_banner_prints_complete_contract(monkeypatch, capsys) -> None:
    monkeypatch.setenv("CODEX_SEAT", "operator")
    monkeypatch.setenv("GIT_INDEX_FILE", "/repo/.git/index-codex-operator")

    rc = seat_banner.main(
        [
            "--objective",
            "consume mail",
            "--permissions",
            "consume-mail=yes commit=yes push=no",
            "--scope",
            "coordination/mailbox/seen/operator.txt",
            "--verify",
            "scripts/check_coordination.py",
            "--done",
            "HEAD changed-files unread verification push next-trigger",
            "--require-complete",
        ]
    )

    out = capsys.readouterr().out
    assert rc == 0
    assert "S-ROLE: live-seat / operator" in out
    assert "S-OBJ: consume mail" in out


def test_require_complete_rejects_missing_fields(capsys) -> None:
    rc = seat_banner.main(["--objective", "only objective", "--require-complete"])

    err = capsys.readouterr().err
    assert rc == 2
    assert "missing contract fields" in err
