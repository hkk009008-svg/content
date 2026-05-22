"""Tests for engine-input preconditions in domain/performance.py."""
from __future__ import annotations

import pytest

from domain.performance import (
    ENGINE_ACT_ONE, ENGINE_LIVE_PORTRAIT, ENGINE_VIGGLE, ENGINE_SKIP,
    precondition_error,
)


class TestActOnePrecondition:
    def test_empty_audio_returns_error(self):
        assert precondition_error(ENGINE_ACT_ONE, audio_path="", driving_video_path="") is not None
        assert "audio" in precondition_error(ENGINE_ACT_ONE, audio_path="", driving_video_path="").lower()

    def test_none_audio_returns_error(self):
        assert precondition_error(ENGINE_ACT_ONE, audio_path=None, driving_video_path=None) is not None

    def test_audio_present_returns_none(self):
        assert precondition_error(ENGINE_ACT_ONE, audio_path="/tmp/a.wav", driving_video_path="") is None

    def test_audio_and_driving_present_returns_none(self):
        assert precondition_error(ENGINE_ACT_ONE, audio_path="/tmp/a.wav", driving_video_path="/tmp/d.mp4") is None


class TestLivePortraitPrecondition:
    def test_missing_driving_video_returns_error(self):
        err = precondition_error(ENGINE_LIVE_PORTRAIT, audio_path="/tmp/a.wav", driving_video_path="")
        assert err is not None and "driving" in err.lower()

    def test_driving_video_present_returns_none(self):
        assert precondition_error(ENGINE_LIVE_PORTRAIT, audio_path="/tmp/a.wav", driving_video_path="/tmp/d.mp4") is None


class TestVigglePrecondition:
    def test_missing_driving_video_returns_error(self):
        err = precondition_error(ENGINE_VIGGLE, audio_path="", driving_video_path="")
        assert err is not None and "driving" in err.lower()


class TestSkipPrecondition:
    def test_skip_returns_none_regardless(self):
        assert precondition_error(ENGINE_SKIP, audio_path="", driving_video_path="") is None
