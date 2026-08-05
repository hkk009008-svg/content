#!/usr/bin/env python3
""".env.example completeness checker (Slice 14a — generated-facts validation).

``config/settings.py`` is the single source of truth for which environment
variables this pipeline reads (its own docstring says so — every var goes
through ``Settings.from_env()`` via a small environment-reader helper).
``.env.example`` makes the same authoritative claim for operators: "every
variable read by config/settings.py appears below."

This script makes that claim machine-checked instead of hand-maintained trust:

  1. missing_key   — a key read in config/settings.py does not
                      appear anywhere (row or comment) in .env.example.
  2. dead_row      — a ``KEY=`` row in .env.example is not read by a supported
                      environment helper in config/settings.py at all (e.g. the
                      SEEDANCE_API_KEY / HEDRA_API_KEY rows removed in Slice
                      14a: Seedance actually dispatches through FAL_KEY, and
                      Hedra has zero remaining consumers post-WS4 removal).

A key legitimately read directly via ``os.environ`` elsewhere in the
codebase (bypassing config.settings, e.g. internal dev toggles like
CINEMA_LOG_LEVEL) is intentionally NOT in this check's scope — .env.example's
own header only promises coverage of config/settings.py's variables, and this
script enforces exactly that promise, not a whole-repo env-var sweep.

Public API
----------
read_settings_env_keys(settings_path) -> set[str]   keys read by env helpers
read_example_row_keys(example_path)   -> set[str]    "KEY=" row keys
read_example_text(example_path)       -> str
check(repo_root) -> list[str]                        drift messages (empty = clean)
main(argv=None) -> int                                exit 0=clean, 1=drift, >1=error

Usage:
  .venv/bin/python scripts/check_env_example.py            # exit 0 clean, 1 on drift
  .venv/bin/python scripts/check_env_example.py --check     # same (explicit alias)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = ROOT / "config" / "settings.py"
EXAMPLE_PATH = ROOT / ".env.example"

# Settings.from_env() uses these helpers with a literal key as their first
# argument. Keep this list explicit so unrelated string-bearing calls cannot
# accidentally make a dead .env.example row look consumed.
_ENV_CALL_RE = re.compile(
    r'_(?:env|optional_env|parse_int)\(\s*"([A-Z0-9_]+)"'
)
_SECRET_ENV_CALL_RE = re.compile(r'_secret_env\(\s*"([A-Z0-9_]+)"')
_ROW_KEY_RE = re.compile(r'^([A-Z][A-Z0-9_]*)=', re.MULTILINE)


def read_settings_env_keys(settings_path: Path = SETTINGS_PATH) -> set[str]:
    """Return every literal KEY passed to a supported env-reader helper."""
    src = settings_path.read_text()
    keys = set(_ENV_CALL_RE.findall(src))
    for key in _SECRET_ENV_CALL_RE.findall(src):
        keys.add(key)
        keys.add(f"{key}_FILE")
    return keys


def read_example_text(example_path: Path = EXAMPLE_PATH) -> str:
    return example_path.read_text()


def read_example_row_keys(example_path: Path = EXAMPLE_PATH) -> set[str]:
    """Return every ``KEY=`` row key at the start of a line in .env.example."""
    return set(_ROW_KEY_RE.findall(read_example_text(example_path)))


def check(repo_root: Path = ROOT) -> list[str]:
    """Return a list of human-readable drift messages; empty means clean."""
    settings_path = repo_root / "config" / "settings.py"
    example_path = repo_root / ".env.example"

    consumed = read_settings_env_keys(settings_path)
    example_text = read_example_text(example_path)
    row_keys = read_example_row_keys(example_path)

    messages: list[str] = []

    missing = sorted(k for k in consumed if k not in example_text)
    for key in missing:
        messages.append(
            f"missing_key: {key} is read by config/settings.py but "
            f"does not appear anywhere in .env.example"
        )

    dead = sorted(k for k in row_keys if k not in consumed)
    for key in dead:
        messages.append(
            f"dead_row: .env.example has a '{key}=' row, but config/settings.py "
            f"never reads {key} via a supported env helper — verify the real consumer (it may "
            f"be routed through a different provider's key, e.g. FAL_KEY) before "
            f"either wiring it or removing the row"
        )

    return messages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Explicit alias for the (only) verification mode this script runs.",
    )
    parser.parse_args(argv)

    messages = check()
    if not messages:
        print("OK: .env.example exactly covers config/settings.py's environment keys.")
        return 0

    print(f"DRIFT: {len(messages)} finding(s) between .env.example and "
          f"config/settings.py:")
    for msg in messages:
        print(f"  - {msg}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
