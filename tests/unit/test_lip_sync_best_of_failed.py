"""Tests for the lip-sync best-of-failed recovery (D6).

When no engine clears the sync gate, both ``lipsync_overlay`` and
``lipsync_generation`` fall back to copying the highest-scored *failed*
candidate to ``output_path`` and returning it. The bug: if that copy raised
(disk full, permission), the code logged the error but still returned
``output_path`` — a path that was never written. The router's contract is
``None`` = "no usable output, keep the original video" (generate_lip_sync_video
docstring), so a failed copy must return ``None``, not a truthy stale path.

The recovery logic was duplicated across both functions (the root cause of the
two-site defect), so it is now a single ``_return_best_of_failed`` helper —
tested directly here, and asserted to be the single source of truth for both
call sites (Rule #13 symmetric-endpoint guard).
"""
from __future__ import annotations

import os
from unittest.mock import patch

import lip_sync


class TestReturnBestOfFailedHelper:
    def test_returns_none_when_copy_fails(self, tmp_path):
        """A failed restore copy must return None, never the unwritten path."""
        best = tmp_path / "best.tmp"
        best.write_bytes(b"video")
        out = str(tmp_path / "out.mp4")
        candidates = [(0.5, str(best), "Hedra")]

        with patch("shutil.copyfile", side_effect=OSError("disk full")):
            result = lip_sync._return_best_of_failed(
                candidates, out,
                threshold=0.8, attempts=["Hedra"],
                cascade_out=None, kind="generation",
            )

        assert result is None, "failed best-of-failed copy must yield None, not a stale path"

    def test_returns_output_and_cleans_up_on_success(self, tmp_path):
        """A successful restore returns output_path, picks the highest score,
        cleans up every stash, and records fallback cascade metadata."""
        best = tmp_path / "best.tmp"
        best.write_bytes(b"best-bytes")
        other = tmp_path / "other.tmp"
        other.write_bytes(b"x")
        out = str(tmp_path / "out.mp4")
        candidates = [(0.3, str(other), "Kling"), (0.5, str(best), "Hedra")]
        cascade: dict = {}

        result = lip_sync._return_best_of_failed(
            candidates, out,
            threshold=0.8, attempts=["Hedra", "Kling"],
            cascade_out=cascade, kind="generation",
        )

        assert result == out
        assert os.path.exists(out)                      # best copied to output
        assert not best.exists() and not other.exists() # all stashes cleaned
        md = cascade["cascade_metadata"]
        assert md["engine"] == "Hedra"                  # highest score wins
        assert md["fallback"] is True
        assert md["attempts"] == ["Hedra", "Kling"]


class TestBothCallSitesUseHelper:
    """Rule #13: the recovery logic must be the single helper at BOTH sites,
    so the copy-failure fix can never regress at only one of them."""

    def test_overlay_uses_helper(self):
        import inspect
        assert "_return_best_of_failed" in inspect.getsource(lip_sync.lipsync_overlay)

    def test_generation_uses_helper(self):
        import inspect
        assert "_return_best_of_failed" in inspect.getsource(lip_sync.lipsync_generation)
