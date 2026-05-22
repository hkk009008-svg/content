"""Tests for performance/_cache.py — content-hash cache for driving synth."""
from __future__ import annotations

import os

import pytest

from performance._cache import driving_cache_key, lookup_cache, store_cache


def test_hash_stable_for_same_content(tmp_path):
    a1 = tmp_path / "a1.wav"; a1.write_bytes(b"abc")
    a2 = tmp_path / "a2.wav"; a2.write_bytes(b"abc")  # same content, different path
    kf = tmp_path / "kf.png"; kf.write_bytes(b"xyz")
    k1 = driving_cache_key(str(a1), str(kf), duration_s=5.0)
    k2 = driving_cache_key(str(a2), str(kf), duration_s=5.0)
    assert k1 == k2


def test_hash_differs_for_different_audio(tmp_path):
    a1 = tmp_path / "a1.wav"; a1.write_bytes(b"abc")
    a2 = tmp_path / "a2.wav"; a2.write_bytes(b"xyz")  # different content
    kf = tmp_path / "kf.png"; kf.write_bytes(b"xyz")
    assert driving_cache_key(str(a1), str(kf), 5.0) != driving_cache_key(str(a2), str(kf), 5.0)


def test_lookup_misses_when_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("PERFORMANCE_CACHE_DIR", str(tmp_path / "cache"))
    a = tmp_path / "a.wav"; a.write_bytes(b"abc")
    kf = tmp_path / "kf.png"; kf.write_bytes(b"xyz")
    key = driving_cache_key(str(a), str(kf), 5.0)
    assert lookup_cache(key) is None


def test_store_then_lookup_hits(tmp_path, monkeypatch):
    monkeypatch.setenv("PERFORMANCE_CACHE_DIR", str(tmp_path / "cache"))
    a = tmp_path / "a.wav"; a.write_bytes(b"abc")
    kf = tmp_path / "kf.png"; kf.write_bytes(b"xyz")
    real_output = tmp_path / "real.mp4"; real_output.write_bytes(b"video-data")
    key = driving_cache_key(str(a), str(kf), 5.0)

    store_cache(key, str(real_output))
    cached = lookup_cache(key)

    assert cached is not None
    assert os.path.exists(cached)
    assert open(cached, "rb").read() == b"video-data"


def test_synth_returns_cache_provider_on_hit(tmp_path, monkeypatch):
    """End-to-end: prime cache, call synth, assert provider=='cache'."""
    from unittest.mock import patch
    from performance.driving_video import synth_driving_face_from_audio
    monkeypatch.setenv("PERFORMANCE_CACHE_DIR", str(tmp_path / "cache"))
    a = tmp_path / "a.wav"; a.write_bytes(b"audio-bytes")
    kf = tmp_path / "kf.png"; kf.write_bytes(b"keyframe-bytes")
    cached_video = tmp_path / "cached.mp4"; cached_video.write_bytes(b"prev")
    key = driving_cache_key(str(a), str(kf), 5.0)
    store_cache(key, str(cached_video))
    out = tmp_path / "out.mp4"
    with patch("performance.driving_video._synth_via_hedra") as mock_h, \
         patch("performance.driving_video._synth_via_sadtalker") as mock_s:
        result = synth_driving_face_from_audio(
            audio_path=str(a), keyframe_path=str(kf),
            output_mp4=str(out), duration_s=5.0,
        )
        assert result == (str(out), "cache")
        mock_h.assert_not_called()
        mock_s.assert_not_called()
