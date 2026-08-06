from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
from pathlib import Path

import pytest

import scripts.install_cinemaker_shortcut as shortcut
from scripts.install_cinemaker_shortcut import (
    BUNDLE_ID,
    ShortcutInstallError,
    install_shortcut,
)


ROOT = Path(__file__).resolve().parents[2]


def test_launcher_rebuilds_removed_ui_and_supports_installed_pointer() -> None:
    launcher = (ROOT / "Cinemaker.app/Contents/MacOS/Cinemaker").read_text()

    assert "Contents/Resources/repository-path" in launcher
    assert "The Content repository moved or is unavailable" in launcher
    assert 'if [ ! -f "$ROOT/web/dist/index.html" ]' in launcher
    assert 'npm" --prefix "$ROOT/web" run build' not in launcher
    assert '"$NPM" --prefix "$ROOT/web" run build' in launcher
    assert launcher.index("cinemaker-launch.log") < launcher.index("web/dist/index.html")


def test_launcher_reports_an_empty_installed_repository_pointer(tmp_path: Path) -> None:
    bundle = tmp_path / "Cinemaker.app"
    shutil.copytree(ROOT / "Cinemaker.app", bundle)
    pointer = bundle / "Contents/Resources/repository-path"
    pointer.write_bytes(b"")

    completed = subprocess.run(
        ["/bin/bash", str(bundle / "Contents/MacOS/Cinemaker")],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
        env={**os.environ, "CINEMAKER_SUPPRESS_DIALOG": "1"},
    )

    assert completed.returncode == 1
    assert "repository pointer is empty or unreadable" in completed.stderr


def test_launcher_accepts_repository_pointer_without_final_newline(tmp_path: Path) -> None:
    bundle = tmp_path / "Cinemaker.app"
    repository = tmp_path / "Content"
    repository.mkdir()
    shutil.copytree(ROOT / "Cinemaker.app", bundle)
    pointer = bundle / "Contents/Resources/repository-path"
    pointer.write_bytes(os.fsencode(repository))

    completed = subprocess.run(
        ["/bin/bash", str(bundle / "Contents/MacOS/Cinemaker")],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
        env={**os.environ, "CINEMAKER_SUPPRESS_DIALOG": "1"},
    )

    assert completed.returncode == 1
    assert "Python venv not found" in completed.stderr
    assert "repository pointer" not in completed.stderr


def test_installer_creates_repo_bound_app_and_replaces_only_same_bundle(tmp_path: Path) -> None:
    destination = tmp_path / "Applications" / "Cinemaker.app"

    installed = install_shortcut(ROOT, destination, sign=False, register=False)
    assert installed == destination
    assert (destination / "Contents/Resources/repository-path").read_text().strip() == str(ROOT)
    assert (destination / "Contents/MacOS/Cinemaker").stat().st_mode & 0o111

    # An idempotent reinstall may replace only our own bundle.
    install_shortcut(ROOT, destination, sign=False, register=False)
    info = plistlib.loads((destination / "Contents/Info.plist").read_bytes())
    assert info["CFBundleIdentifier"] == BUNDLE_ID


def test_installer_refuses_symlink_and_foreign_bundle(tmp_path: Path) -> None:
    applications = tmp_path / "Applications"
    applications.mkdir()
    destination = applications / "Cinemaker.app"
    destination.symlink_to(ROOT / "Cinemaker.app")
    with pytest.raises(ShortcutInstallError, match="symlinked"):
        install_shortcut(ROOT, destination, sign=False, register=False)

    destination.unlink()
    (destination / "Contents").mkdir(parents=True)
    (destination / "Contents/Info.plist").write_bytes(
        plistlib.dumps({"CFBundleIdentifier": "example.foreign"})
    )
    with pytest.raises(ShortcutInstallError, match="unexpected identifier"):
        install_shortcut(ROOT, destination, sign=False, register=False)

    with pytest.raises(ShortcutInstallError, match="tracked source bundle"):
        install_shortcut(ROOT, ROOT / "Cinemaker.app", sign=False, register=False)


def test_installer_keeps_committed_app_when_launchservices_times_out(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    destination = tmp_path / "Applications/Cinemaker.app"
    install_shortcut(ROOT, destination, sign=False, register=False)
    previous_only = destination / "previous-only.txt"
    previous_only.write_text("old install", encoding="utf-8")

    def registration_timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("lsregister", 30)

    monkeypatch.setattr(shortcut.sys, "platform", "darwin")
    monkeypatch.setattr(shortcut.subprocess, "run", registration_timeout)

    installed = install_shortcut(ROOT, destination, sign=False, register=True)

    assert installed == destination
    assert not previous_only.exists()
    assert (destination / "Contents/Resources/repository-path").read_text().strip() == str(ROOT)
    assert not list(destination.parent.glob(".cinemaker-install-*"))


def test_installer_preserves_previous_app_when_replacement_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    destination = tmp_path / "Applications/Cinemaker.app"
    install_shortcut(ROOT, destination, sign=False, register=False)
    previous_only = destination / "previous-only.txt"
    previous_only.write_text("recover this install", encoding="utf-8")

    real_replace = os.replace
    replace_calls = 0

    def fail_replacement(source, target):
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 1:
            return real_replace(source, target)
        if replace_calls == 2:
            raise OSError("injected app install failure")
        raise AssertionError("automatic rollback must not be attempted")

    monkeypatch.setattr(shortcut.os, "replace", fail_replacement)

    with pytest.raises(ShortcutInstallError, match="recovery copy remains at") as caught:
        install_shortcut(ROOT, destination, sign=False, register=False)

    assert replace_calls == 2
    recovery_roots = list(destination.parent.glob(".cinemaker-install-*"))
    assert len(recovery_roots) == 1
    recovery = recovery_roots[0] / "previous.app"
    assert recovery.is_dir()
    assert (recovery / "previous-only.txt").read_text(encoding="utf-8") == (
        "recover this install"
    )
    assert str(recovery) in str(caught.value)
    assert not destination.exists()


def test_installer_preserves_backup_without_overwriting_reappeared_destination(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    destination = tmp_path / "Applications/Cinemaker.app"
    install_shortcut(ROOT, destination, sign=False, register=False)
    (destination / "previous-only.txt").write_text("previous app", encoding="utf-8")

    real_replace = os.replace
    replace_calls = 0

    def fail_after_recreating_destination(source, target):
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 1:
            return real_replace(source, target)
        if replace_calls == 2:
            destination.mkdir()
            (destination / "reappeared.txt").write_text(
                "do not overwrite",
                encoding="utf-8",
            )
            raise OSError("injected staged replacement failure")
        raise AssertionError("no further rename may overwrite the reappeared destination")

    monkeypatch.setattr(shortcut.os, "replace", fail_after_recreating_destination)

    with pytest.raises(ShortcutInstallError, match="destination was left untouched") as caught:
        install_shortcut(ROOT, destination, sign=False, register=False)

    assert replace_calls == 2
    assert (destination / "reappeared.txt").read_text(encoding="utf-8") == (
        "do not overwrite"
    )
    recovery_roots = list(destination.parent.glob(".cinemaker-install-*"))
    assert len(recovery_roots) == 1
    recovery = recovery_roots[0] / "previous.app"
    assert (recovery / "previous-only.txt").read_text(encoding="utf-8") == (
        "previous app"
    )
    assert str(recovery) in str(caught.value)
