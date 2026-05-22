"""Tests for performance/_router.py — per-provider concurrency cap."""
from __future__ import annotations

import threading
import time
from unittest.mock import patch

import pytest

from performance._router import dispatch, _SEMAPHORE_LIMITS


class TestSemaphoreConfig:
    def test_each_engine_has_a_limit(self):
        assert "ACT_ONE" in _SEMAPHORE_LIMITS
        assert "LIVE_PORTRAIT" in _SEMAPHORE_LIMITS
        assert "VIGGLE" in _SEMAPHORE_LIMITS

    def test_limits_are_positive_ints(self):
        for engine, limit in _SEMAPHORE_LIMITS.items():
            assert isinstance(limit, int)
            assert limit >= 1


class TestSemaphoreEnforcement:
    def test_act_one_concurrency_capped(self, tmp_path):
        """Spawn 4 threads; max simultaneous in-flight must equal the cap."""
        in_flight = 0
        max_in_flight = 0
        lock = threading.Lock()

        def slow_stub(*a, **kw):
            nonlocal in_flight, max_in_flight
            with lock:
                in_flight += 1
                max_in_flight = max(max_in_flight, in_flight)
            time.sleep(0.05)
            with lock:
                in_flight -= 1
            return str(tmp_path / "out.mp4")

        with patch("performance.act_one.generate_act_one_performance", slow_stub):
            threads = [
                threading.Thread(target=lambda i=i: dispatch(
                    "ACT_ONE",
                    keyframe_path=str(tmp_path / "kf.png"),
                    audio_path=str(tmp_path / "a.wav"),
                    driving_video_path=None,
                    output_mp4=str(tmp_path / f"out{i}.mp4"),
                ))
                for i in range(4)
            ]
            for t in threads: t.start()
            for t in threads: t.join()

        assert max_in_flight <= _SEMAPHORE_LIMITS["ACT_ONE"]
        assert max_in_flight == _SEMAPHORE_LIMITS["ACT_ONE"]
