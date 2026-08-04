"""Tests for scripts/check_env_example.py — .env.example completeness checker.

Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_check_env_example.py -q

Mirrors the check_doc_claims.py / check_coordination.py verifier pattern:
real tmp_path fixtures, no mocking. Slice 14a added this checker after
finding .env.example carried two dead rows (SEEDANCE_API_KEY, HEDRA_API_KEY —
neither is read anywhere config/settings.py's _env() calls reach) and was
missing IDENTITY_EMBED_MODEL (a real, consumed field). These tests pin both
directions of that drift class plus a real-repo integration check.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from check_env_example import (  # noqa: E402
    check,
    read_example_row_keys,
    read_settings_env_keys,
)


def _write_settings(tmp_path: Path, body: str) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / "settings.py"
    path.write_text(body, encoding="utf-8")
    return path


def _write_example(tmp_path: Path, body: str) -> Path:
    path = tmp_path / ".env.example"
    path.write_text(body, encoding="utf-8")
    return path


def test_read_settings_env_keys_extracts_env_calls(tmp_path):
    settings = _write_settings(
        tmp_path,
        'x = _env("FOO_KEY")\n'
        'y = _env("BAR_KEY", "default")\n'
        'z = _env("FOO_KEY")\n',  # duplicate — must not double-count as separate keys
    )
    assert read_settings_env_keys(settings) == {"FOO_KEY", "BAR_KEY"}


def test_read_settings_env_keys_extracts_typed_reader_calls(tmp_path):
    settings = _write_settings(
        tmp_path,
        'a = _optional_env("OPTIONAL_KEY")\n'
        'b = _parse_int("COUNT_KEY", 8, minimum=1)\n',
    )
    assert read_settings_env_keys(settings) == {"OPTIONAL_KEY", "COUNT_KEY"}


def test_read_example_row_keys_only_matches_line_start_assignments(tmp_path):
    example = _write_example(
        tmp_path,
        "# a comment mentioning FAKE_MENTION= mid-sentence is not a row\n"
        "REAL_ROW=\n"
        "ANOTHER_ROW=some_default\n",
    )
    assert read_example_row_keys(example) == {"REAL_ROW", "ANOTHER_ROW"}


def test_check_clean_when_sets_match_exactly(tmp_path):
    _write_settings(tmp_path, 'a = _env("ONE")\nb = _env("TWO", "x")\n')
    _write_example(tmp_path, "ONE=\nTWO=x\n")
    assert check(tmp_path) == []


def test_check_detects_missing_key(tmp_path):
    _write_settings(tmp_path, 'a = _env("ONE")\nb = _env("TWO")\n')
    _write_example(tmp_path, "ONE=\n")  # TWO undocumented anywhere
    messages = check(tmp_path)
    assert len(messages) == 1
    assert "missing_key" in messages[0]
    assert "TWO" in messages[0]


def test_check_detects_dead_row(tmp_path):
    _write_settings(tmp_path, 'a = _env("ONE")\n')
    _write_example(tmp_path, "ONE=\nTOTALLY_UNCONSUMED=\n")
    messages = check(tmp_path)
    assert len(messages) == 1
    assert "dead_row" in messages[0]
    assert "TOTALLY_UNCONSUMED" in messages[0]


def test_check_accepts_key_documented_only_in_prose_not_as_its_own_row(tmp_path):
    """A legacy-alias key (like SUNO_TOKEN) can be satisfied by mention in a
    comment near its primary key's row — it does not need its own bare row."""
    _write_settings(
        tmp_path,
        'a = _env("PRIMARY_KEY") or _env("LEGACY_ALIAS")\n',
    )
    _write_example(
        tmp_path,
        "# PRIMARY_KEY — LEGACY_ALIAS accepted as a fallback if unset.\n"
        "PRIMARY_KEY=\n",
    )
    assert check(tmp_path) == []


def test_real_repo_env_example_matches_real_settings():
    """Integration pin: the actual .env.example this slice shipped exactly
    covers the actual config/settings.py _env(...) keys, with zero dead rows
    (this is the exact claim .env.example's own header makes)."""
    messages = check(REPO_ROOT)
    assert messages == [], f"real .env.example drifted from config/settings.py: {messages}"


def test_real_repo_has_no_seedance_or_hedra_dead_rows():
    """Regression pin for the specific dead keys Slice 14a removed."""
    row_keys = read_example_row_keys(REPO_ROOT / ".env.example")
    assert "SEEDANCE_API_KEY" not in row_keys, (
        "SEEDANCE_API_KEY reintroduced — Seedance dispatches via FAL_KEY, "
        "not its own key (verify before restoring this row)"
    )
    assert "HEDRA_API_KEY" not in row_keys, (
        "HEDRA_API_KEY reintroduced — Hedra was fully removed (WS4); "
        "verify a real consumer exists before restoring this row"
    )


def test_real_repo_documents_identity_embed_model():
    """Regression pin: IDENTITY_EMBED_MODEL is a real, consumed field
    (identity/validator.py) that Slice 14a found missing from .env.example."""
    row_keys = read_example_row_keys(REPO_ROOT / ".env.example")
    assert "IDENTITY_EMBED_MODEL" in row_keys
