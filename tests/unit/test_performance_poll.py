"""Tests for performance/_poll.py — generic task poller."""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from performance._poll import poll_task


class TestSuccess:
    def test_immediate_success(self):
        get_status = MagicMock(return_value={"status": "SUCCEEDED"})
        result = poll_task(get_status, success_states={"SUCCEEDED"}, terminal_states={"FAILED"},
                          interval_s=0.01, timeout_s=1.0)
        assert result == {"status": "SUCCEEDED"}
        assert get_status.call_count == 1

    def test_case_normalization(self):
        get_status = MagicMock(return_value={"status": "succeeded"})
        result = poll_task(get_status, success_states={"SUCCEEDED"}, terminal_states={"FAILED"},
                          interval_s=0.01, timeout_s=1.0)
        assert result is not None

    def test_eventual_success(self):
        get_status = MagicMock(side_effect=[
            {"status": "PROCESSING"}, {"status": "PROCESSING"}, {"status": "SUCCEEDED"},
        ])
        result = poll_task(get_status, success_states={"SUCCEEDED"}, terminal_states={"FAILED"},
                          interval_s=0.01, timeout_s=1.0)
        assert result == {"status": "SUCCEEDED"}
        assert get_status.call_count == 3


class TestTerminal:
    def test_terminal_failure_returns_none(self):
        get_status = MagicMock(return_value={"status": "FAILED"})
        result = poll_task(get_status, success_states={"SUCCEEDED"}, terminal_states={"FAILED", "CANCELLED"},
                          interval_s=0.01, timeout_s=1.0)
        assert result is None

    def test_terminal_cancelled_returns_none(self):
        get_status = MagicMock(return_value={"status": "CANCELLED"})
        result = poll_task(get_status, success_states={"SUCCEEDED"}, terminal_states={"FAILED", "CANCELLED"},
                          interval_s=0.01, timeout_s=1.0)
        assert result is None


class TestTimeout:
    def test_timeout_returns_none(self):
        get_status = MagicMock(return_value={"status": "PROCESSING"})
        start = time.time()
        result = poll_task(get_status, success_states={"SUCCEEDED"}, terminal_states={"FAILED"},
                          interval_s=0.05, timeout_s=0.2)
        elapsed = time.time() - start
        assert result is None
        assert 0.15 <= elapsed <= 0.5


class TestResilience:
    def test_get_status_exception_keeps_polling(self):
        get_status = MagicMock(side_effect=[
            RuntimeError("blip"), {"status": "SUCCEEDED"},
        ])
        result = poll_task(get_status, success_states={"SUCCEEDED"}, terminal_states={"FAILED"},
                          interval_s=0.01, timeout_s=1.0)
        assert result == {"status": "SUCCEEDED"}
        assert get_status.call_count == 2
