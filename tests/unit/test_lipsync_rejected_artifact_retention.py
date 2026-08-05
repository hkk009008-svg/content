"""Offline coverage for immutable retention of rejected paid lip-sync output."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import lip_sync


class _PaidAuthority:
    """Small explicit capability stub; provider execution itself is mocked."""

    paid_attempt_authority_version = 1

    def reserve_paid_attempt(self, *args, **kwargs):  # pragma: no cover - capability only
        raise AssertionError("provider wrapper is mocked")

    def update_paid_attempt(self, *args, **kwargs):  # pragma: no cover - capability only
        raise AssertionError("provider wrapper is mocked")

    def reconcile_paid_attempt(self, *args, **kwargs):  # pragma: no cover - capability only
        raise AssertionError("provider wrapper is mocked")

    def get_paid_attempt(self, *args, **kwargs):  # pragma: no cover - capability only
        raise AssertionError("provider wrapper is mocked")

    def get_latest_paid_attempt(self, *args, **kwargs):  # pragma: no cover - capability only
        raise AssertionError("provider wrapper is mocked")


def _artifact_record(index: int) -> dict:
    digest = f"{index:064x}"
    return {
        "artifact_id": f"av-{digest[:24]}",
        "logical_name": f"shots/shot_a/postprocess/reject_{index}",
        "version": 1,
        "sha256": digest,
        "object_path": f".artifact_versions/objects/{digest}",
    }


def _run_generation(
    tmp_path: Path,
    *,
    scores,
    orientations,
    handler,
    aspect_ratio: str = "9:16",
):
    face = tmp_path / "face.jpg"
    audio = tmp_path / "dialogue.wav"
    output = tmp_path / "lipsync.mp4"
    face.write_bytes(b"face")
    audio.write_bytes(b"audio")
    cascade: dict = {}
    provider_calls: list[str] = []

    def fake_paid_job(**kwargs):
        engine = kwargs["engine_key"]
        provider_calls.append(engine)
        attempt = {
            "attempt_id": f"fal-lipsync:{engine.lower()}",
            "provider": "fal",
            "engine": engine,
            "model": kwargs["application"],
            "provider_job_id": f"request-{engine.lower()}",
            "request_fingerprint": f"fingerprint-{engine.lower()}",
            "provider_status": "completed",
            "state": "succeeded",
        }
        kwargs["cascade_out"]["_active_paid_attempt"] = attempt
        kwargs["cascade_out"]["paid_attempt"] = dict(attempt)
        kwargs["cascade_out"]["paid_cost_recorded"] = True
        return {"video": {"url": f"https://example.test/{engine}.mp4"}}

    def fake_download(url, path, *args, **kwargs):
        del args, kwargs
        Path(path).write_bytes(Path(url).stem.encode("ascii"))
        return path

    fal = MagicMock()
    fal.upload_file.return_value = "https://example.test/upload"
    prereqs = SimpleNamespace(passed=True, warnings=[], blockers=[])

    with (
        patch("lip_sync.FAL_AVAILABLE", True),
        patch("lip_sync.ENV_SETTINGS", SimpleNamespace(fal_key="key")),
        patch("lip_sync.check_generation_prerequisites", return_value=prereqs),
        patch("lip_sync.fal_client", fal),
        patch("lip_sync._run_lipsync_fal_job", side_effect=fake_paid_job),
        patch("lip_sync.safe_download", side_effect=fake_download),
        patch("lip_sync.validate_lipsync_quality", side_effect=list(scores)),
        patch("phase_c_ffmpeg._accept_or_reject", side_effect=list(orientations)),
    ):
        result = lip_sync.lipsync_generation(
            str(face),
            str(audio),
            str(output),
            settings={
                "aspect_ratio": aspect_ratio,
                "lipsync_validation_threshold": 0.65,
            },
            _cascade_out=cascade,
            cost_tracker=_PaidAuthority(),
            shot_id="shot_a",
            video_id="project_a",
            _retain_rejected_candidate=handler,
        )
    return result, output, cascade, provider_calls


def test_quality_reject_is_retained_before_next_provider_overwrites_it(tmp_path):
    seen = []

    def retain(evidence):
        # The callback runs while the shared output still contains this exact
        # provider's bytes, before Aurora is allowed to overwrite it.
        assert Path(evidence["path"]).read_bytes() == b"LIPSYNC_OMNIHUMAN"
        seen.append(evidence)
        return _artifact_record(len(seen))

    result, output, cascade, calls = _run_generation(
        tmp_path,
        scores=[0.21, 0.91],
        orientations=[True, True],
        handler=retain,
    )

    assert result == str(output)
    assert output.read_bytes() == b"LIPSYNC_AURORA"
    assert calls == ["LIPSYNC_OMNIHUMAN", "LIPSYNC_AURORA"]
    assert len(seen) == 1
    evidence = cascade["rejected_candidates"][0]
    assert evidence["attempt_id"] == "fal-lipsync:lipsync_omnihuman"
    assert evidence["provider"] == "fal"
    assert evidence["model"] == "fal-ai/bytedance/omnihuman/v1.5"
    assert evidence["score"] == 0.21
    assert evidence["validation_state"] == "FAIL"
    assert evidence["rejection_stage"] == "quality_gate"
    assert evidence["retained"] is True
    assert evidence["retained_path"].startswith(".artifact_versions/objects/")


def test_overlay_quality_reject_uses_the_same_paid_retention_fence(tmp_path):
    video = tmp_path / "source.mp4"
    audio = tmp_path / "dialogue.wav"
    output = tmp_path / "overlay.mp4"
    video.write_bytes(b"video")
    audio.write_bytes(b"audio")
    cascade: dict = {}
    calls = []
    seen = []

    def fake_paid_job(**kwargs):
        engine = kwargs["engine_key"]
        calls.append(engine)
        attempt = {
            "attempt_id": f"fal-lipsync:{engine.lower()}",
            "provider": "fal",
            "engine": engine,
            "model": kwargs["application"],
            "provider_job_id": f"request-{engine.lower()}",
            "request_fingerprint": f"fingerprint-{engine.lower()}",
            "provider_status": "completed",
            "state": "succeeded",
        }
        kwargs["cascade_out"]["_active_paid_attempt"] = attempt
        return {"video": {"url": f"https://example.test/{engine}.mp4"}}

    def fake_download(url, path, *args, **kwargs):
        del args, kwargs
        Path(path).write_bytes(Path(url).stem.encode("ascii"))
        return path

    def retain(evidence):
        assert Path(evidence["path"]).read_bytes() == b"LIPSYNC_SYNCSOV3"
        seen.append(evidence)
        return _artifact_record(len(seen))

    fal = MagicMock()
    fal.upload_file.return_value = "https://example.test/upload"
    prereqs = SimpleNamespace(passed=True, warnings=[], blockers=[])
    with (
        patch("lip_sync.FAL_AVAILABLE", True),
        patch("lip_sync.ENV_SETTINGS", SimpleNamespace(fal_key="key")),
        patch("lip_sync.check_overlay_prerequisites", return_value=prereqs),
        patch("lip_sync.fal_client", fal),
        patch("lip_sync._run_lipsync_fal_job", side_effect=fake_paid_job),
        patch("lip_sync.safe_download", side_effect=fake_download),
        patch("lip_sync.validate_lipsync_quality", side_effect=[0.2, 0.9]),
    ):
        result = lip_sync.lipsync_overlay(
            str(video),
            str(audio),
            str(output),
            _cascade_out=cascade,
            cost_tracker=_PaidAuthority(),
            shot_id="shot_a",
            video_id="project_a",
            _retain_rejected_candidate=retain,
        )

    assert result == str(output)
    assert output.read_bytes() == b"LIPSYNC_MUSETALK"
    assert calls == ["LIPSYNC_SYNCSOV3", "LIPSYNC_MUSETALK"]
    assert len(seen) == 1
    assert cascade["rejected_candidates"][0]["rejection_stage"] == "quality_gate"
    assert cascade["rejected_candidates"][0]["retained"] is True


def test_orientation_reject_is_retained_but_cannot_win_best_of_failed(tmp_path):
    seen = []

    def retain(evidence):
        assert Path(evidence["path"]).read_bytes() == b"LIPSYNC_OMNIHUMAN"
        seen.append(evidence)
        return _artifact_record(len(seen))

    result, output, cascade, calls = _run_generation(
        tmp_path,
        scores=[0.92],
        orientations=[False, True],
        handler=retain,
    )

    assert result == str(output)
    assert output.read_bytes() == b"LIPSYNC_AURORA"
    assert calls == ["LIPSYNC_OMNIHUMAN", "LIPSYNC_AURORA"]
    assert len(seen) == 1
    evidence = cascade["rejected_candidates"][0]
    assert evidence["rejection_stage"] == "orientation_gate"
    assert evidence["validation_state"] == "FAIL"
    assert evidence["score"] is None
    assert evidence["aspect_ratio"] == "9:16"


def test_best_of_failed_deletes_stashes_only_after_every_reject_is_retained(tmp_path):
    retained_bytes = []

    def retain(evidence):
        retained_bytes.append(Path(evidence["path"]).read_bytes())
        return _artifact_record(len(retained_bytes))

    result, output, cascade, calls = _run_generation(
        tmp_path,
        scores=[0.22, 0.44],
        orientations=[True, True],
        handler=retain,
    )

    assert result == str(output)
    assert output.read_bytes() == b"LIPSYNC_AURORA"
    assert calls == ["LIPSYNC_OMNIHUMAN", "LIPSYNC_AURORA"]
    assert retained_bytes == [b"LIPSYNC_OMNIHUMAN", b"LIPSYNC_AURORA"]
    assert all(item["retained"] for item in cascade["rejected_candidates"])
    assert list(tmp_path.glob("*.tmp")) == []
    assert cascade["cascade_metadata"]["engine"] == "Aurora"
    assert cascade["cascade_metadata"]["fallback"] is True


def test_retention_failure_stops_fallback_and_leaves_exact_recovery_bytes(tmp_path):
    def fail_retention(_evidence):
        raise OSError("artifact ledger unavailable")

    result, output, cascade, calls = _run_generation(
        tmp_path,
        scores=[0.18],
        orientations=[True],
        handler=fail_retention,
    )

    assert result is None
    assert calls == ["LIPSYNC_OMNIHUMAN"]
    assert output.read_bytes() == b"LIPSYNC_OMNIHUMAN"
    assert list(tmp_path.glob("*.tmp")) == []
    assert cascade["rejected_candidate_retention_failed"] is True
    recovery = cascade["recovery_candidate"]
    assert recovery["retained"] is False
    assert recovery["attempt_id"] == "fal-lipsync:lipsync_omnihuman"
    assert recovery["path"] == str(output.resolve())
    assert "artifact ledger unavailable" in recovery["retention_error"]
