"""Tests for domain/shot_types.py — canonical shot-type names + normalizer."""
from __future__ import annotations

import pytest

from domain.shot_types import (
    SHOT_TYPE_CLOSE, SHOT_TYPE_PORTRAIT, SHOT_TYPE_MEDIUM,
    SHOT_TYPE_WIDE, SHOT_TYPE_LANDSCAPE, SHOT_TYPE_ACTION,
    FACE_READABLE_SHOTS,
    normalize_shot_type,
)


class TestNormalize:
    @pytest.mark.parametrize("alias,expected", [
        ("close-up", SHOT_TYPE_CLOSE),
        ("CLOSE-UP", SHOT_TYPE_CLOSE),
        ("closeup", SHOT_TYPE_CLOSE),
        ("close_up", SHOT_TYPE_CLOSE),
        ("ecu", SHOT_TYPE_CLOSE),
        ("portrait", SHOT_TYPE_PORTRAIT),
        ("medium", SHOT_TYPE_MEDIUM),
        ("wide", SHOT_TYPE_WIDE),
        ("landscape", SHOT_TYPE_LANDSCAPE),
        ("action", SHOT_TYPE_ACTION),
    ])
    def test_known_aliases(self, alias, expected):
        assert normalize_shot_type(alias) == expected

    def test_empty_string(self):
        assert normalize_shot_type("") == ""

    def test_none(self):
        assert normalize_shot_type(None) == ""

    def test_unknown_passes_through_lowercased(self):
        # An unknown shot type still normalizes to lowercase — caller's
        # branches fall through, no silent rename.
        assert normalize_shot_type("OVER_SHOULDER") == "over_shoulder"


class TestFaceReadableSet:
    def test_close_is_face_readable(self):
        assert SHOT_TYPE_CLOSE in FACE_READABLE_SHOTS

    def test_portrait_is_face_readable(self):
        assert SHOT_TYPE_PORTRAIT in FACE_READABLE_SHOTS

    def test_medium_is_face_readable(self):
        assert SHOT_TYPE_MEDIUM in FACE_READABLE_SHOTS

    def test_landscape_is_not_face_readable(self):
        assert SHOT_TYPE_LANDSCAPE not in FACE_READABLE_SHOTS
