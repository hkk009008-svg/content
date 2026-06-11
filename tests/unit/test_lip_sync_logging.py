"""Unit tests for lip_sync.py JSON-logger conversion (T3 — P2-1b).

Verifies that the structured logger is used correctly:
  1. Cascade step messages carry the `engine` extra field.
  2. Failure paths log at ERROR with identifying context.
  3. The sync-gate path carries structured sync_score / threshold fields.
  4. The generation-prereq blocker path logs at ERROR.

All tests are fully offline — no real API calls, no GPU.
"""

from __future__ import annotations

import types
import sys
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Lightweight stubs so lip_sync imports without heavy optional deps
# ---------------------------------------------------------------------------

def _stub(name: str, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


for _dep in ["fal_client", "hedra_native"]:
    if _dep not in sys.modules:
        _stub(_dep, upload_file=MagicMock(return_value="http://fake/url"))

if "hedra_native" not in sys.modules or not hasattr(sys.modules["hedra_native"], "HedraAPI"):
    sys.modules["hedra_native"] = _stub("hedra_native", HedraAPI=MagicMock)


# ---------------------------------------------------------------------------
# Test 1: cascade step carries `engine` extra in INFO log
# ---------------------------------------------------------------------------

class TestCascadeStepLogsEngine:
    """lipsync_generation INFO messages include the `engine` extra field."""

    def test_hedra_attempt_logs_engine_info(self, caplog):
        """On Hedra attempt, an INFO record with engine='hedra' is emitted."""
        import logging
        import lip_sync

        prereq = types.SimpleNamespace(passed=True, warnings=[], blockers=[])

        fake_fal = MagicMock()
        fake_fal.upload_file.return_value = "http://fake/upload"

        # Hedra returns no output → logs warning and falls through; we only care
        # that the INFO attempt record appeared.
        hedra_instance = MagicMock()
        hedra_instance.generate_talking_head.return_value = None
        hedra_cls = MagicMock(return_value=hedra_instance)

        with (
            patch("lip_sync.FAL_AVAILABLE", True),
            patch("lip_sync.ENV_SETTINGS", types.SimpleNamespace(fal_key="k")),
            patch("lip_sync.check_generation_prerequisites", return_value=prereq),
            patch("lip_sync.fal_client", fake_fal),
            patch("lip_sync._HedraAPI", hedra_cls),
            # Make remaining FAL calls raise so we stop early
            patch("lip_sync.safe_download", return_value=None),
            caplog.at_level(logging.INFO, logger="lip_sync"),
        ):
            # fal_client.subscribe raises to abort the Kling/Omnihuman/Aurora attempts
            fake_fal.subscribe.side_effect = RuntimeError("stop")
            lip_sync.lipsync_generation(
                character_image_path="/tmp/face.jpg",
                audio_path="/tmp/audio.wav",
                output_path="/tmp/out.mp4",
            )

        info_records = [r for r in caplog.records if r.levelno == logging.INFO]
        assert info_records, "Expected at least one INFO record from lipsync_generation"
        engines = [getattr(r, "engine", None) for r in info_records]
        assert "hedra" in engines, (
            f"Expected engine='hedra' in INFO records; got engines={engines!r}"
        )


# ---------------------------------------------------------------------------
# Test 2: FAL-unavailable path logs WARNING with `engine` extra
# ---------------------------------------------------------------------------

class TestFalUnavailableLogsWarning:
    """When FAL is not available, both lipsync paths emit WARNING with engine extra."""

    def test_overlay_fal_unavailable_warns(self, caplog):
        import logging
        import lip_sync

        with (
            patch("lip_sync.FAL_AVAILABLE", False),
            patch("lip_sync.ENV_SETTINGS", types.SimpleNamespace(fal_key=None)),
            caplog.at_level(logging.WARNING, logger="lip_sync"),
        ):
            result = lip_sync.lipsync_overlay(
                video_path="/tmp/vid.mp4",
                audio_path="/tmp/a.wav",
                output_path="/tmp/out.mp4",
            )

        assert result is None
        warn_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warn_records, "Expected at least one WARNING for FAL-unavailable overlay"
        assert any(
            getattr(r, "engine", None) == "overlay" for r in warn_records
        ), f"Expected engine='overlay' in WARNING records; got {[getattr(r,'engine',None) for r in warn_records]!r}"

    def test_generation_fal_unavailable_warns(self, caplog):
        import logging
        import lip_sync

        with (
            patch("lip_sync.FAL_AVAILABLE", False),
            patch("lip_sync.ENV_SETTINGS", types.SimpleNamespace(fal_key=None)),
            caplog.at_level(logging.WARNING, logger="lip_sync"),
        ):
            result = lip_sync.lipsync_generation(
                character_image_path="/tmp/face.jpg",
                audio_path="/tmp/a.wav",
                output_path="/tmp/out.mp4",
            )

        assert result is None
        warn_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warn_records, "Expected at least one WARNING for FAL-unavailable generation"
        assert any(
            getattr(r, "engine", None) == "generation" for r in warn_records
        ), f"Expected engine='generation' in WARNING; got {[getattr(r,'engine',None) for r in warn_records]!r}"


# ---------------------------------------------------------------------------
# Test 3: sync-gate score path carries sync_score + threshold
# ---------------------------------------------------------------------------

class TestSyncGateLogsScore:
    """The sync-gate INFO record carries sync_score and threshold extra fields."""

    def test_generation_gate_score_in_log(self, caplog, tmp_path):
        """After a successful engine output, the gate log includes sync_score."""
        import logging
        import lip_sync

        # Minimal real output file so _accept_or_reject and the gate can run.
        out = str(tmp_path / "out.mp4")
        open(out, "wb").write(b"fake")

        prereq = types.SimpleNamespace(passed=True, warnings=[], blockers=[])

        fake_fal = MagicMock()
        fake_fal.upload_file.return_value = "http://fake/upload"
        fake_fal.subscribe.return_value = {"video": {"url": "http://fake/vid"}}

        def _fake_download(url, path, *a, **kw):
            open(path, "wb").write(b"fake")
            return path

        hedra_cls = MagicMock()
        hedra_cls.return_value.generate_talking_head.return_value = None

        with (
            patch("lip_sync.FAL_AVAILABLE", True),
            patch("lip_sync.ENV_SETTINGS", types.SimpleNamespace(fal_key="k")),
            patch("lip_sync.check_generation_prerequisites", return_value=prereq),
            patch("lip_sync.fal_client", fake_fal),
            patch("lip_sync.safe_download", side_effect=_fake_download),
            patch("lip_sync._HedraAPI", hedra_cls),
            # Gate: score above threshold so first FAL engine wins
            patch("lip_sync.validate_lipsync_quality", return_value=0.85),
            # Orientation: always accept
            patch("phase_c_ffmpeg._accept_or_reject", return_value=True),
            caplog.at_level(logging.INFO, logger="lip_sync"),
        ):
            lip_sync.lipsync_generation(
                character_image_path="/tmp/face.jpg",
                audio_path="/tmp/a.wav",
                output_path=out,
                settings={"lipsync_quality_validation": True, "lipsync_validation_threshold": 0.65},
            )

        gate_records = [
            r for r in caplog.records
            if r.levelno == logging.INFO and hasattr(r, "sync_score")
        ]
        assert gate_records, (
            "Expected at least one INFO record with sync_score from the generation gate; "
            f"all records: {[(r.getMessage(), r.__dict__) for r in caplog.records]}"
        )
        rec = gate_records[0]
        assert hasattr(rec, "threshold"), f"sync gate record missing 'threshold'; record={rec.__dict__!r}"
        assert 0.0 <= rec.sync_score <= 1.0, f"sync_score out of range: {rec.sync_score!r}"


# ---------------------------------------------------------------------------
# Test 3b: overlay-side sync gate carries sync_score + threshold
# ---------------------------------------------------------------------------

class TestOverlaySyncGateLogsScore:
    """The overlay-side sync gate INFO record carries sync_score and threshold extra fields."""

    def test_overlay_gate_score_in_log(self, caplog, tmp_path):
        """After a successful overlay engine output, the gate log includes sync_score."""
        import logging
        import lip_sync

        # Minimal output file so the gate can run
        out = str(tmp_path / "out.mp4")
        open(out, "wb").write(b"fake")

        vid = str(tmp_path / "vid.mp4")
        open(vid, "wb").write(b"fake")

        prereq = types.SimpleNamespace(passed=True, warnings=[], blockers=[])

        fake_fal = MagicMock()
        fake_fal.upload_file.return_value = "http://fake/upload"
        fake_fal.subscribe.return_value = {"video": {"url": "http://fake/vid"}}

        def _fake_download(url, path, *a, **kw):
            open(path, "wb").write(b"fake")
            return path

        with (
            patch("lip_sync.FAL_AVAILABLE", True),
            patch("lip_sync.ENV_SETTINGS", types.SimpleNamespace(fal_key="k")),
            patch("lip_sync.check_overlay_prerequisites", return_value=prereq),
            patch("lip_sync.fal_client", fake_fal),
            patch("lip_sync.safe_download", side_effect=_fake_download),
            # Gate: score above threshold so first engine wins
            patch("lip_sync.validate_lipsync_quality", return_value=0.85),
            # Orientation: always accept
            patch("phase_c_ffmpeg._accept_or_reject", return_value=True),
            caplog.at_level(logging.INFO, logger="lip_sync"),
        ):
            lip_sync.lipsync_overlay(
                video_path=vid,
                audio_path="/tmp/a.wav",
                output_path=out,
                settings={"lipsync_quality_validation": True, "lipsync_validation_threshold": 0.65},
            )

        gate_records = [
            r for r in caplog.records
            if r.levelno == logging.INFO and hasattr(r, "sync_score")
        ]
        assert gate_records, (
            "Expected at least one INFO record with sync_score from the overlay gate; "
            f"all records: {[(r.getMessage(), r.__dict__) for r in caplog.records]}"
        )
        rec = gate_records[0]
        assert hasattr(rec, "threshold"), f"overlay sync gate record missing 'threshold'; record={rec.__dict__!r}"
        assert 0.0 <= rec.sync_score <= 1.0, f"sync_score out of range: {rec.sync_score!r}"


# ---------------------------------------------------------------------------
# Test 4: prerequisite blocker logs at ERROR with engine extra
# ---------------------------------------------------------------------------

class TestPrereqBlockerLogsError:
    """When prerequisites fail, an ERROR record with the engine extra is emitted."""

    def test_generation_prereq_blocker_logs_error(self, caplog):
        import logging
        import lip_sync

        blocked_prereq = types.SimpleNamespace(
            passed=False,
            warnings=[],
            blockers=["BLOCKER: Character image does not exist"],
        )

        with (
            patch("lip_sync.FAL_AVAILABLE", True),
            patch("lip_sync.ENV_SETTINGS", types.SimpleNamespace(fal_key="k")),
            patch("lip_sync.check_generation_prerequisites", return_value=blocked_prereq),
            caplog.at_level(logging.ERROR, logger="lip_sync"),
        ):
            result = lip_sync.lipsync_generation(
                character_image_path="/nonexistent/face.jpg",
                audio_path="/nonexistent/a.wav",
                output_path="/tmp/out.mp4",
            )

        assert result is None
        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert error_records, "Expected ERROR record for prereq blocker"
        assert any(
            getattr(r, "engine", None) == "generation" for r in error_records
        ), (
            f"Expected engine='generation' on ERROR; "
            f"got {[getattr(r,'engine',None) for r in error_records]!r}"
        )
        # The blocker text should appear in the message
        blocker_msgs = [r.getMessage() for r in error_records]
        assert any("BLOCKER" in m for m in blocker_msgs), (
            f"Expected 'BLOCKER' in error message; got {blocker_msgs!r}"
        )
