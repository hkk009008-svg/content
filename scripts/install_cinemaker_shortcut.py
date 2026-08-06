#!/usr/bin/env python3
"""Install the tracked Cinemaker bundle as a stable per-user app shortcut."""

from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


BUNDLE_ID = "local.content.cinemaker"


class ShortcutInstallError(RuntimeError):
    """The requested shortcut install was unsafe or incomplete."""


def _bundle_id(bundle: Path) -> str:
    info = bundle / "Contents" / "Info.plist"
    try:
        payload = plistlib.loads(info.read_bytes())
    except (OSError, plistlib.InvalidFileException) as exc:
        raise ShortcutInstallError(f"invalid app bundle at {bundle}") from exc
    value = payload.get("CFBundleIdentifier")
    if value != BUNDLE_ID:
        raise ShortcutInstallError(
            f"refusing app bundle with unexpected identifier {value!r}"
        )
    return value


def install_shortcut(
    repo_root: Path,
    destination: Path,
    *,
    sign: bool = True,
    register: bool = True,
) -> Path:
    """Atomically install a repo-bound app copy at *destination*."""

    root = repo_root.expanduser().resolve(strict=True)
    source = root / "Cinemaker.app"
    if not (root / "web_server.py").is_file() or not source.is_dir():
        raise ShortcutInstallError("repository does not contain the Cinemaker app")
    _bundle_id(source)

    requested_target = destination.expanduser()
    if not requested_target.is_absolute() or requested_target.name != "Cinemaker.app":
        raise ShortcutInstallError("destination must be an absolute Cinemaker.app path")
    requested_target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    if requested_target.is_symlink():
        raise ShortcutInstallError("refusing to replace a symlinked app shortcut")
    target = requested_target.parent.resolve(strict=True) / requested_target.name
    if target == source.resolve(strict=True):
        raise ShortcutInstallError("destination must not replace the tracked source bundle")
    if target.exists():
        if not target.is_dir():
            raise ShortcutInstallError("refusing to replace a non-directory shortcut")
        _bundle_id(target)

    staging_root = Path(tempfile.mkdtemp(prefix=".cinemaker-install-", dir=target.parent))
    staged = staging_root / target.name
    backup = staging_root / "previous.app"
    replaced = False
    preserve_recovery = False
    try:
        shutil.copytree(source, staged, symlinks=True)
        pointer = staged / "Contents" / "Resources" / "repository-path"
        pointer.write_text(f"{root}\n", encoding="utf-8")
        pointer.chmod(0o600)
        launcher = staged / "Contents" / "MacOS" / "Cinemaker"
        launcher.chmod(0o755)

        if sign and sys.platform == "darwin":
            signed = subprocess.run(
                ["/usr/bin/codesign", "--force", "--deep", "--sign", "-", str(staged)],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if signed.returncode:
                raise ShortcutInstallError("ad-hoc signing the app shortcut failed")

        if target.exists():
            os.replace(target, backup)
            replaced = True
        try:
            os.replace(staged, target)
        except Exception as install_error:
            if replaced:
                # Once the prior app is in the private backup, never attempt a
                # second rename into the public destination: another actor may
                # recreate that entry at any time. Preserve the exact recovery
                # path for explicit operator recovery instead.
                preserve_recovery = True
                if target.exists() or target.is_symlink():
                    raise ShortcutInstallError(
                        "app replacement failed after the destination reappeared; "
                        "the destination was left untouched and the recovery "
                        f"copy remains at {backup}"
                    ) from install_error
                raise ShortcutInstallError(
                    "app replacement failed; automatic rollback was not attempted "
                    f"and the recovery copy remains at {backup}"
                ) from install_error
            raise

        if register and sys.platform == "darwin":
            # The app replacement is already committed. LaunchServices
            # registration is advisory and must not turn a successful atomic
            # install into a reported failure or discard the recovery copy.
            try:
                subprocess.run(
                    [
                        "/System/Library/Frameworks/CoreServices.framework/Frameworks/"
                        "LaunchServices.framework/Support/lsregister",
                        "-f",
                        str(target),
                    ],
                    check=False,
                    capture_output=True,
                    timeout=30,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
        return target
    finally:
        if not preserve_recovery:
            shutil.rmtree(staging_root, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path.home() / "Applications" / "Cinemaker.app",
    )
    parser.add_argument("--no-sign", action="store_true")
    parser.add_argument("--no-register", action="store_true")
    parser.add_argument("--open", action="store_true", dest="open_app")
    args = parser.parse_args(argv)
    try:
        target = install_shortcut(
            args.repo_root,
            args.destination,
            sign=not args.no_sign,
            register=not args.no_register,
        )
    except (OSError, ShortcutInstallError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(f"Installed Cinemaker shortcut at {target}")
    if args.open_app:
        subprocess.run(["/usr/bin/open", str(target)], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
