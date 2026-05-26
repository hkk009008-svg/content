#!/usr/bin/env python3
"""Clean pytest-leaked test fixtures from domain/projects/.

The test suite has historically created projects under the canonical
``domain/projects/`` PROJECTS_DIR when individual tests forgot to redirect
via the ``tmp_projects_dir`` fixture (see ``tests/unit/test_project_manager.py``).
Cycle 10 added a UX-tolerable list_projects (mtime-DESC + search + paginate
via U1 / dea4cc8), but the underlying directory remained polluted with
~2,170 stale dirs as of cycle 13.

This script removes them safely. It uses a whitelist-based discriminator:
a directory is deleted only on a positive match against one of:

    1. Hand-written test dirname (``test_*``, ``fake``, ``MagicMock``,
       ``nonexistent*``, ``stray_*``, ``lock_test_*``).
    2. Missing ``project.json`` (orphaned init — uuid that never persisted,
       OR hand-named pytest dir without persistence).
    3. ``project.json``'s ``name`` field matches a known test-fixture name
       (whitelist below; sourced from cycle-13 audit covering all 15
       distinct ``name`` values present in 2,158 parseable project.json
       files).

Unknown names are KEPT — the script is conservative; a real project with
an unrecognized name is preserved rather than deleted on a false positive.

Default mode is dry-run. Pass ``--execute`` to actually delete.

Usage:
    python scripts/clean_test_fixtures.py                # dry-run report
    python scripts/clean_test_fixtures.py --verbose      # per-project disposition
    python scripts/clean_test_fixtures.py --execute      # actually delete
    python scripts/clean_test_fixtures.py --root <dir>   # alternate root

Exit codes:
    0  — success (dry-run, or execute with zero errors)
    1  — execute completed with one or more rmtree errors
    2  — usage / setup error (root not a directory)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Optional


TEST_FIXTURE_NAMES: frozenset[str] = frozenset({
    "Test Project",
    "Guided Tool",
    "ShotTest",
    "SceneTest",
    "LocTest",
    "CharTest",
    "Test Film",
    "Beta",
    "V2",
    "SaveMe",
    "Roundtrip",
    "Slim",
    "OutputTest",
    "Alpha",
    "test",
})


TEST_DIRNAME_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^test_"),
    re.compile(r"^fake$"),
    re.compile(r"^MagicMock$"),
    re.compile(r"^nonexistent"),
    re.compile(r"^stray_"),
    re.compile(r"^lock_test_"),
)


PROJECT_ID_RE = re.compile(r"^[0-9a-f]{12}$")


def classify(project_dir: Path) -> tuple[str, str]:
    """Return (disposition, reason).

    disposition ∈ {"DELETE", "KEEP", "LOCKED_SKIP"}.
    """
    name = project_dir.name

    for pat in TEST_DIRNAME_PATTERNS:
        if pat.search(name):
            return ("DELETE", f"dirname matches /{pat.pattern}/")

    lock_path = project_dir / "project.lock"
    if lock_path.exists():
        return ("LOCKED_SKIP", "project.lock present (active session?)")

    pj = project_dir / "project.json"
    if not pj.is_file():
        if PROJECT_ID_RE.match(name):
            return ("DELETE", "no project.json (orphaned uuid init)")
        return ("DELETE", "no project.json + non-uuid dirname")

    try:
        with open(pj, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return ("KEEP", f"project.json parse error (preserve for triage): {e}")

    pname = data.get("name", "")
    if pname in TEST_FIXTURE_NAMES:
        return ("DELETE", f"name={pname!r} (test fixture whitelist)")

    return ("KEEP", f"name={pname!r} (not in test whitelist)")


def default_root() -> Path:
    return Path(__file__).resolve().parent.parent / "domain" / "projects"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Project root dir (default: <repo>/domain/projects)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete (default: dry-run)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Per-project disposition output",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else default_root()

    if not root.is_dir():
        print(f"ERROR: {root} is not a directory", file=sys.stderr)
        return 2

    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(f"Mode: {mode}")
    print(f"Root: {root}")
    print()

    dispositions: Counter[str] = Counter()
    reason_counts: Counter[tuple[str, str]] = Counter()
    delete_list: list[Path] = []

    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        disp, reason = classify(entry)
        dispositions[disp] += 1
        reason_counts[(disp, reason)] += 1
        if args.verbose:
            print(f"  {disp:12}  {entry.name}  ({reason})")
        if disp == "DELETE":
            delete_list.append(entry)

    print()
    print("Summary:")
    for d in ("DELETE", "KEEP", "LOCKED_SKIP"):
        print(f"  {d:12}  {dispositions[d]}")
    print()
    print("Dispositions × reason:")
    for (d, r), c in sorted(reason_counts.items()):
        print(f"  [{d:12}] {c:6}  {r}")

    if not delete_list:
        print("\nNothing to delete.")
        return 0

    if not args.execute:
        print(f"\nDRY-RUN: would delete {len(delete_list)} directories.")
        print("Re-run with --execute to actually delete.")
        return 0

    print(f"\nDeleting {len(delete_list)} directories ...")
    errors = 0
    for entry in delete_list:
        try:
            shutil.rmtree(entry)
        except OSError as e:
            print(f"  ERROR removing {entry.name}: {e}", file=sys.stderr)
            errors += 1
    deleted = len(delete_list) - errors
    print(f"Deleted {deleted} dirs ({errors} errors).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
