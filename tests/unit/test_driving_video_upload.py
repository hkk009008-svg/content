"""Security and publication contract for per-shot driving-video uploads."""

from __future__ import annotations

import io
import hashlib
import shutil
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def client():
    import web_server

    web_server.app.config["TESTING"] = True
    with web_server.app.test_client() as test_client:
        yield test_client


def _seed_project(tmp_path, monkeypatch, *, scene_id: str | None = None):
    from domain import project_manager

    monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(tmp_path), raising=False)
    project = project_manager.create_project("driving-upload-test")
    scene = project_manager.make_scene("Scene")
    if scene_id is not None:
        scene["id"] = scene_id
    shot = project_manager.make_shot("Portrait performance")
    shot["performance_engine"] = "SKIP"
    scene["shots"].append(shot)
    scene["num_shots"] = 1

    def _mutate(latest):
        latest["scenes"].append(scene)
        return project_manager.MutationResult(None, save=True)

    project_manager.mutate_project(project["id"], _mutate, timeout=5)
    return project["id"], scene["id"], shot["id"]


def _destination(tmp_path: Path, pid: str, scene_id: str, shot_id: str) -> Path:
    return (
        tmp_path
        / pid
        / "performance_inputs"
        / scene_id
        / shot_id
        / "driving.mp4"
    )


def _version_destination(
    tmp_path: Path,
    pid: str,
    scene_id: str,
    shot_id: str,
    payload: bytes,
) -> Path:
    digest = hashlib.sha256(payload).hexdigest()
    return _destination(tmp_path, pid, scene_id, shot_id).with_name(
        f"driving-{digest}.mp4"
    )


def _set_existing_path(pid: str, shot_id: str, destination: Path) -> None:
    from domain import project_manager

    def _mutate(latest):
        for scene in latest["scenes"]:
            for shot in scene["shots"]:
                if shot["id"] == shot_id:
                    shot["driving_video_path"] = str(destination)
                    shot["performance_engine"] = "LIVE_PORTRAIT"
                    return project_manager.MutationResult(None, save=True)
        raise AssertionError("seeded shot disappeared")

    project_manager.mutate_project(pid, _mutate, timeout=5)


def _shot(pid: str, shot_id: str) -> dict:
    from domain import project_manager

    project = project_manager.load_project(pid)
    return next(
        shot
        for scene in project["scenes"]
        for shot in scene["shots"]
        if shot["id"] == shot_id
    )


def _mutate_shot(pid: str, shot_id: str, callback) -> None:
    from domain import project_manager

    def _mutate(latest):
        shot = next(
            shot
            for scene in latest["scenes"]
            for shot in scene["shots"]
            if shot["id"] == shot_id
        )
        callback(shot)
        return project_manager.MutationResult(None, save=True)

    project_manager.mutate_project(pid, _mutate, timeout=5)


class _SnapshotTracker:
    def __init__(self, attempts):
        self.attempts = attempts

    def get_paid_attempts_snapshot(self, _video_id=""):
        return {"attempts": list(self.attempts)}


class _BrokenSnapshotTracker:
    def get_paid_attempts_snapshot(self, _video_id=""):
        raise RuntimeError("simulated paid-attempt store failure")


def _paid_attempt(pid: str, shot_id: str, *, engine: str, state: str) -> dict:
    return {
        "attempt_id": f"{engine.lower()}-{state}",
        "video_id": pid,
        "shot_id": shot_id,
        "engine": engine,
        "operation": "performance_capture",
        "state": state,
        "provider_job_id": f"job-{engine.lower()}",
    }


def test_valid_upload_is_staged_validated_and_atomically_published(
    client, tmp_path, monkeypatch
):
    import web_server

    pid, scene_id, shot_id = _seed_project(tmp_path, monkeypatch)
    destination = _destination(tmp_path, pid, scene_id, shot_id)
    payload = b"new-valid-video"
    version_destination = _version_destination(
        tmp_path, pid, scene_id, shot_id, payload
    )
    observed = {}

    def _validate(path, **kwargs):
        staged = Path(path)
        observed["path"] = staged
        observed["payload"] = staged.read_bytes()
        observed["kwargs"] = kwargs
        assert staged.parent == destination.parent
        assert staged.name.startswith(".driving-upload-")
        assert not destination.exists(), "validation must precede publication"
        return None

    monkeypatch.setattr(web_server, "validate_video_artifact", _validate)
    response = client.post(
        f"/api/projects/{pid}/shots/{shot_id}/upload-driving-video",
        data={"driving_video": (io.BytesIO(payload), "operator.mov")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    assert version_destination.read_bytes() == payload
    assert observed["payload"] == payload
    assert observed["kwargs"] == {
        "min_dimensions": (64, 64),
        "max_dimensions": (4096, 4096),
        "max_pixels": 4096 * 2160,
        "max_duration_s": 30.0,
    }
    # Uploads retain a longer reusable acting reference; execution separately
    # caps the first per-shot window to 8 seconds / 200 frames.
    from cinema.shots.controller import MAX_PERFORMANCE_TAKE_DURATION_S

    assert observed["kwargs"]["max_duration_s"] > MAX_PERFORMANCE_TAKE_DURATION_S
    persisted = _shot(pid, shot_id)
    expected_relative = str(version_destination.relative_to(tmp_path / pid))
    assert response.get_json()["path"] == expected_relative
    assert not Path(response.get_json()["path"]).is_absolute()
    assert persisted["driving_video_path"] == expected_relative
    assert persisted["driving_video_history"][-1]["sha256"] == hashlib.sha256(
        payload
    ).hexdigest()
    assert persisted["driving_video_history"][-1]["path"] == expected_relative
    assert persisted["performance_engine"] == ""
    assert list(destination.parent.glob(".driving-*.mp4")) == []


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="requires ffmpeg and ffprobe",
)
def test_real_mp4_reaches_ffprobe_full_decode_and_publication(
    client, tmp_path, monkeypatch
):
    pid, scene_id, shot_id = _seed_project(tmp_path, monkeypatch)
    upload = tmp_path / "operator-driving.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=128x128:r=10",
            "-t",
            "0.2",
            "-c:v",
            "mpeg4",
            "-pix_fmt",
            "yuv420p",
            str(upload),
        ],
        check=True,
        timeout=20,
    )

    response = client.post(
        f"/api/projects/{pid}/shots/{shot_id}/upload-driving-video",
        data={"driving_video": (io.BytesIO(upload.read_bytes()), upload.name)},
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    destination = _version_destination(
        tmp_path, pid, scene_id, shot_id, upload.read_bytes()
    )
    assert destination.is_file()
    assert destination.stat().st_size == upload.stat().st_size


def test_validation_rejection_preserves_existing_media_and_metadata(
    client, tmp_path, monkeypatch
):
    import web_server

    pid, scene_id, shot_id = _seed_project(tmp_path, monkeypatch)
    destination = _destination(tmp_path, pid, scene_id, shot_id)
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"known-good-video")
    _set_existing_path(pid, shot_id, destination)

    monkeypatch.setattr(
        web_server,
        "validate_video_artifact",
        lambda _path, **_kwargs: "video is not an MP4-family container",
    )
    response = client.post(
        f"/api/projects/{pid}/shots/{shot_id}/upload-driving-video",
        data={"driving_video": (io.BytesIO(b"not-a-video"), "driving.mp4")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert response.get_json()["details"] == "video is not an MP4-family container"
    assert destination.read_bytes() == b"known-good-video"
    persisted = _shot(pid, shot_id)
    assert persisted["driving_video_path"] == str(destination)
    assert persisted["performance_engine"] == "LIVE_PORTRAIT"
    assert list(destination.parent.glob(".driving-*.mp4")) == []


def test_stream_size_limit_rejects_before_validation_and_preserves_existing_media(
    client, tmp_path, monkeypatch
):
    import web_server

    pid, scene_id, shot_id = _seed_project(tmp_path, monkeypatch)
    destination = _destination(tmp_path, pid, scene_id, shot_id)
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"known-good-video")
    _set_existing_path(pid, shot_id, destination)
    monkeypatch.setattr(web_server, "_DRIVING_VIDEO_MAX_BYTES", 8)

    def _unexpected_validation(*_args, **_kwargs):
        raise AssertionError("oversize content reached media validation")

    monkeypatch.setattr(web_server, "validate_video_artifact", _unexpected_validation)
    response = client.post(
        f"/api/projects/{pid}/shots/{shot_id}/upload-driving-video",
        data={"driving_video": (io.BytesIO(b"123456789"), "driving.mp4")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 413
    assert response.get_json()["max_bytes"] == 8
    assert destination.read_bytes() == b"known-good-video"
    assert list(destination.parent.glob(".driving-*.mp4")) == []


def test_mutation_miss_preserves_old_selection_and_retains_indexed_revision(
    client, tmp_path, monkeypatch
):
    import web_server

    pid, scene_id, shot_id = _seed_project(tmp_path, monkeypatch)
    destination = _destination(tmp_path, pid, scene_id, shot_id)
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"known-good-video")
    _set_existing_path(pid, shot_id, destination)

    monkeypatch.setattr(web_server, "validate_video_artifact", lambda *_a, **_k: None)
    monkeypatch.setattr(web_server, "mutate_project", lambda *_a, **_k: None)
    response = client.post(
        f"/api/projects/{pid}/shots/{shot_id}/upload-driving-video",
        data={"driving_video": (io.BytesIO(b"replacement"), "driving.mp4")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 404
    assert destination.read_bytes() == b"known-good-video"
    # Indexing precedes active selection. Its content-addressed bytes must
    # remain so the durable artifact record never points at a deleted file.
    assert _version_destination(
        tmp_path, pid, scene_id, shot_id, b"replacement"
    ).read_bytes() == b"replacement"
    assert _shot(pid, shot_id)["driving_video_path"] == str(destination)
    assert list(destination.parent.glob(".driving-*.mp4")) == []


def test_replacement_preserves_prior_bytes_and_takes_but_invalidates_approval(
    client, tmp_path, monkeypatch
):
    import web_server
    from domain import project_manager

    pid, scene_id, shot_id = _seed_project(tmp_path, monkeypatch)
    monkeypatch.setattr(web_server, "validate_video_artifact", lambda *_a, **_k: None)

    first_payload = b"first-driving-revision"
    first = client.post(
        f"/api/projects/{pid}/shots/{shot_id}/upload-driving-video",
        data={"driving_video": (io.BytesIO(first_payload), "first.mp4")},
        content_type="multipart/form-data",
    )
    assert first.status_code == 201

    historical_take = {
        "id": "performance-old",
        "kind": "performance",
        "path": "shots/old.mp4",
        "metadata": {"driving_video_path": first.get_json()["path"]},
    }

    def _approve_old(latest):
        shot = next(
            shot
            for scene in latest["scenes"]
            for shot in scene["shots"]
            if shot["id"] == shot_id
        )
        shot["performance_takes"] = [historical_take]
        shot["approved_performance_take_id"] = historical_take["id"]
        shot["performance_engine"] = "LIVE_PORTRAIT"
        return project_manager.MutationResult(None, save=True)

    project_manager.mutate_project(pid, _approve_old, timeout=5)

    second_payload = b"second-driving-revision"
    second = client.post(
        f"/api/projects/{pid}/shots/{shot_id}/upload-driving-video",
        data={"driving_video": (io.BytesIO(second_payload), "second.mp4")},
        content_type="multipart/form-data",
    )

    assert second.status_code == 201
    body = second.get_json()
    assert body["invalidated_performance_take_id"] == "performance-old"
    assert body["requires_performance_regeneration"] is True
    first_path = tmp_path / pid / first.get_json()["path"]
    second_path = tmp_path / pid / body["path"]
    assert first_path.read_bytes() == first_payload
    assert second_path.read_bytes() == second_payload

    persisted = _shot(pid, shot_id)
    assert persisted["approved_performance_take_id"] == ""
    assert persisted["performance_engine"] == ""
    assert len(persisted["performance_takes"]) == 1
    persisted_take = persisted["performance_takes"][0]
    assert persisted_take["id"] == historical_take["id"]
    assert persisted_take["path"] == historical_take["path"]
    assert persisted_take["metadata"] == historical_take["metadata"]
    assert [entry["path"] for entry in persisted["driving_video_history"]] == [
        first.get_json()["path"],
        body["path"],
    ]


@pytest.mark.parametrize("restore_missing_bytes", [False, True])
def test_same_content_upload_is_idempotent_and_preserves_approval_and_history(
    client, tmp_path, monkeypatch, restore_missing_bytes
):
    import web_server
    from domain import project_manager

    pid, _scene_id, shot_id = _seed_project(tmp_path, monkeypatch)
    monkeypatch.setattr(web_server, "validate_video_artifact", lambda *_a, **_k: None)
    payload = b"same-driving-revision"
    first = client.post(
        f"/api/projects/{pid}/shots/{shot_id}/upload-driving-video",
        data={"driving_video": (io.BytesIO(payload), "first.mp4")},
        content_type="multipart/form-data",
    )
    assert first.status_code == 201

    def _approve(latest):
        shot = next(
            shot
            for scene in latest["scenes"]
            for shot in scene["shots"]
            if shot["id"] == shot_id
        )
        take = {
            "id": "performance-current",
            "kind": "performance",
            "path": "shots/current.mp4",
            "metadata": {"driving_video_path": first.get_json()["path"]},
        }
        shot["performance_takes"] = [take]
        shot["approved_performance_take_id"] = take["id"]
        shot["performance_engine"] = "LIVE_PORTRAIT"
        return project_manager.MutationResult(None, save=True)

    project_manager.mutate_project(pid, _approve, timeout=5)
    before = _shot(pid, shot_id)
    retained_path = tmp_path / pid / first.get_json()["path"]
    if restore_missing_bytes:
        retained_path.unlink()
    second = client.post(
        f"/api/projects/{pid}/shots/{shot_id}/upload-driving-video",
        data={"driving_video": (io.BytesIO(payload), "same.mp4")},
        content_type="multipart/form-data",
    )

    assert second.status_code == 200
    assert second.get_json()["unchanged"] is True
    assert second.get_json()["requires_performance_regeneration"] is False
    after = _shot(pid, shot_id)
    assert after["approved_performance_take_id"] == "performance-current"
    assert after["performance_engine"] == "LIVE_PORTRAIT"
    assert after["driving_video_history"] == before["driving_video_history"]
    assert after["performance_review_history"] == before["performance_review_history"]
    assert retained_path.read_bytes() == payload


def test_upload_is_rejected_while_pipeline_runs_outside_performance_review(
    client, tmp_path, monkeypatch
):
    import web_server

    pid, _scene_id, shot_id = _seed_project(tmp_path, monkeypatch)
    monkeypatch.setattr(
        web_server,
        "_get_running_pipeline",
        lambda _pid: SimpleNamespace(current_stage="MOTION"),
    )
    monkeypatch.setattr(
        web_server,
        "validate_video_artifact",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("busy upload reached media validation")
        ),
    )

    response = client.post(
        f"/api/projects/{pid}/shots/{shot_id}/upload-driving-video",
        data={"driving_video": (io.BytesIO(b"blocked"), "blocked.mp4")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 409
    assert response.get_json()["code"] == "wrong_pipeline_stage"
    assert response.get_json()["required_stage"] == "PERFORMANCE_REVIEW"


def test_upload_blocks_active_request_before_file_validation(
    client, tmp_path, monkeypatch,
):
    import web_server

    pid, _scene_id, shot_id = _seed_project(tmp_path, monkeypatch)
    request_id = "a" * 32
    _mutate_shot(
        pid,
        shot_id,
        lambda shot: shot.update({
            "performance_generation_request": {
                "request_id": request_id,
                "status": "deferred",
                "engine": "ACT_ONE",
            },
        }),
    )
    monkeypatch.setattr(
        web_server,
        "validate_video_artifact",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("active request reached media validation")
        ),
    )

    response = client.post(
        f"/api/projects/{pid}/shots/{shot_id}/upload-driving-video",
        data={"driving_video": (io.BytesIO(b"replacement"), "replacement.mp4")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 409
    assert response.get_json()["code"] == "performance_request_active"
    assert response.get_json()["request"]["request_id"] == request_id
    assert _shot(pid, shot_id)["performance_generation_request"]["status"] == "deferred"


@pytest.mark.parametrize("engine", ["VIGGLE", "ACT_ONE"])
def test_upload_blocks_unreconciled_paid_attempt_from_any_route_before_validation(
    client, tmp_path, monkeypatch, engine,
):
    import web_server

    pid, _scene_id, shot_id = _seed_project(tmp_path, monkeypatch)
    tracker = _SnapshotTracker([
        _paid_attempt(
            pid,
            shot_id,
            engine=engine,
            state="accepted_unknown",
        ),
    ])
    monkeypatch.setattr(
        web_server,
        "_get_or_build_core",
        lambda _pid: SimpleNamespace(cost_tracker=tracker),
    )
    monkeypatch.setattr(
        web_server,
        "validate_video_artifact",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("unreconciled paid work reached media validation")
        ),
    )

    response = client.post(
        f"/api/projects/{pid}/shots/{shot_id}/upload-driving-video",
        data={"driving_video": (io.BytesIO(b"replacement"), "replacement.mp4")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 409
    body = response.get_json()
    assert body["code"] == "provider_job_deferred"
    assert body["engine"] == engine
    assert body["paid_attempt"]["state"] == "accepted_unknown"


def test_upload_fails_closed_when_paid_attempt_snapshot_is_unavailable(
    client, tmp_path, monkeypatch,
):
    import web_server

    pid, _scene_id, shot_id = _seed_project(tmp_path, monkeypatch)
    monkeypatch.setattr(
        web_server,
        "_get_or_build_core",
        lambda _pid: SimpleNamespace(cost_tracker=_BrokenSnapshotTracker()),
    )
    monkeypatch.setattr(
        web_server,
        "validate_video_artifact",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("failed authority reached media validation")
        ),
    )

    response = client.post(
        f"/api/projects/{pid}/shots/{shot_id}/upload-driving-video",
        data={"driving_video": (io.BytesIO(b"replacement"), "replacement.mp4")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 409
    assert response.get_json()["code"] == "performance_authority_unavailable"


def test_changed_upload_tombstones_terminal_generation_request(
    client, tmp_path, monkeypatch,
):
    import web_server

    pid, _scene_id, shot_id = _seed_project(tmp_path, monkeypatch)
    monkeypatch.setattr(web_server, "validate_video_artifact", lambda *_a, **_k: None)
    first = client.post(
        f"/api/projects/{pid}/shots/{shot_id}/upload-driving-video",
        data={"driving_video": (io.BytesIO(b"first-input"), "first.mp4")},
        content_type="multipart/form-data",
    )
    assert first.status_code == 201
    request_id = "f" * 32
    _mutate_shot(
        pid,
        shot_id,
        lambda shot: shot.update({
            "performance_generation_request": {
                "request_id": request_id,
                "status": "succeeded",
                "engine": "ACT_ONE",
                "take_id": "performance-old",
                "driving_video_revision": first.get_json()["path"],
                "driving_video_fingerprint": "old-fingerprint",
            },
        }),
    )

    second = client.post(
        f"/api/projects/{pid}/shots/{shot_id}/upload-driving-video",
        data={"driving_video": (io.BytesIO(b"second-input"), "second.mp4")},
        content_type="multipart/form-data",
    )

    assert second.status_code == 201
    persisted = _shot(pid, shot_id)
    tombstone = persisted["performance_generation_request"]
    assert tombstone["request_id"] == request_id
    assert tombstone["status"] == "superseded_input"
    assert tombstone["superseded_by_driving_video_path"] == second.get_json()["path"]
    assert persisted["performance_generation_request_history"][-1] == tombstone


def test_replacement_upload_lease_keeps_review_gate_closed_during_validation(
    tmp_path, monkeypatch, inject_pipeline,
):
    import web_server
    from cinema.review.controller import ReviewController
    from domain import project_manager

    pid, _scene_id, shot_id = _seed_project(tmp_path, monkeypatch)
    monkeypatch.setattr(web_server, "validate_video_artifact", lambda *_a, **_k: None)
    with web_server.app.test_client() as initial_client:
        first = initial_client.post(
            f"/api/projects/{pid}/shots/{shot_id}/upload-driving-video",
            data={"driving_video": (io.BytesIO(b"first-input"), "first.mp4")},
            content_type="multipart/form-data",
        )
    assert first.status_code == 201
    first_path = first.get_json()["path"]

    def _approve_current(shot):
        shot["approved_keyframe_take_id"] = "keyframe-current"
        shot["performance_takes"] = [{
            "id": "performance-current",
            "kind": "performance",
            "path": "shots/performance-current.mp4",
            "metadata": {"driving_video_path": first_path},
        }]
        shot["approved_performance_take_id"] = "performance-current"
        shot["performance_engine"] = "ACT_ONE"

    _mutate_shot(pid, shot_id, _approve_current)

    pipeline = SimpleNamespace(
        current_stage="PERFORMANCE_REVIEW",
        _direct_stage_in_flight=False,
        _refresh_project_snapshot=lambda: project_manager.load_project(pid),
    )
    inject_pipeline(pid, pipeline)
    tracker = _SnapshotTracker([])
    monkeypatch.setattr(
        web_server,
        "_get_or_build_core",
        lambda _pid: SimpleNamespace(cost_tracker=tracker),
    )

    validation_entered = threading.Event()
    allow_validation = threading.Event()

    def _blocking_validation(*_args, **_kwargs):
        validation_entered.set()
        assert allow_validation.wait(5), "test did not release upload validation"
        return None

    monkeypatch.setattr(web_server, "validate_video_artifact", _blocking_validation)
    result: dict[str, object] = {}

    def _upload_replacement():
        with web_server.app.test_client() as threaded_client:
            response = threaded_client.post(
                f"/api/projects/{pid}/shots/{shot_id}/upload-driving-video",
                data={
                    "driving_video": (
                        io.BytesIO(b"second-input"),
                        "second.mp4",
                    ),
                },
                content_type="multipart/form-data",
            )
            result["status"] = response.status_code
            result["body"] = response.get_json()

    upload_thread = threading.Thread(target=_upload_replacement, daemon=True)
    upload_thread.start()
    assert validation_entered.wait(5), "replacement upload never reached validation"
    try:
        current_project = project_manager.load_project(pid)
        lifecycle = SimpleNamespace(
            report_progress=lambda *_a, **_k: None,
            wait_for_gate=lambda _gate, predicate: predicate(),
        )
        runstate = SimpleNamespace(current_stage="", headless=False)
        review = ReviewController(
            SimpleNamespace(project=current_project),
            lifecycle,
            pipeline,
            runstate,
        )
        review._run_auto_approve_pass = lambda _gate: None

        assert review._gate_satisfied("PERFORMANCE_REVIEW", current_project) is True
        assert pipeline._direct_stage_in_flight is True
        assert review._wait_for_gate(
            "PERFORMANCE_REVIEW", "Review performance", 65,
        ) is False
    finally:
        allow_validation.set()
        upload_thread.join(timeout=5)

    assert not upload_thread.is_alive()
    assert result["status"] == 201
    assert pipeline._direct_stage_in_flight is False
    refreshed = project_manager.load_project(pid)
    assert _shot(pid, shot_id)["approved_performance_take_id"] == ""
    assert review._gate_satisfied("PERFORMANCE_REVIEW", refreshed) is False


def test_artifact_index_failure_keeps_previous_active_input(
    client, tmp_path, monkeypatch
):
    import web_server
    from cinema.artifact_versions import ArtifactVersionError

    pid, scene_id, shot_id = _seed_project(tmp_path, monkeypatch)
    legacy = _destination(tmp_path, pid, scene_id, shot_id)
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"known-good-video")
    _set_existing_path(pid, shot_id, legacy)
    monkeypatch.setattr(web_server, "validate_video_artifact", lambda *_a, **_k: None)
    monkeypatch.setattr(
        web_server,
        "record_auxiliary_version",
        lambda *_a, **_k: (_ for _ in ()).throw(ArtifactVersionError("ledger unavailable")),
    )
    replacement = b"unindexed-replacement"

    response = client.post(
        f"/api/projects/{pid}/shots/{shot_id}/upload-driving-video",
        data={"driving_video": (io.BytesIO(replacement), "replacement.mp4")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 500
    assert "provenance" in response.get_json()["error"].lower()
    assert legacy.read_bytes() == b"known-good-video"
    assert not _version_destination(
        tmp_path, pid, scene_id, shot_id, replacement
    ).exists()
    persisted = _shot(pid, shot_id)
    assert persisted["driving_video_path"] == str(legacy)
    assert persisted["approved_performance_take_id"] == ""


def test_relative_upload_path_survives_project_root_relocation(
    client, tmp_path, monkeypatch
):
    import web_server
    from domain import project_manager

    old_root = tmp_path / "old-projects"
    new_root = tmp_path / "new-projects"
    old_root.mkdir()
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(old_root), raising=False)
    pid, _scene_id, shot_id = _seed_project(old_root, monkeypatch)
    monkeypatch.setattr(web_server, "validate_video_artifact", lambda *_a, **_k: None)
    payload = b"portable-driving-video"
    upload = client.post(
        f"/api/projects/{pid}/shots/{shot_id}/upload-driving-video",
        data={"driving_video": (io.BytesIO(payload), "portable.mp4")},
        content_type="multipart/form-data",
    )
    assert upload.status_code == 201
    stored_path = upload.get_json()["path"]
    assert not Path(stored_path).is_absolute()

    new_root.mkdir()
    shutil.move(str(old_root / pid), str(new_root / pid))
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", str(new_root), raising=False)

    served = client.get(f"/api/projects/{pid}/file", query_string={"path": stored_path})
    assert served.status_code == 200
    assert served.data == payload


def test_persisted_scene_id_cannot_escape_performance_input_root(
    client, tmp_path, monkeypatch
):
    import web_server

    pid, _scene_id, shot_id = _seed_project(
        tmp_path,
        monkeypatch,
        scene_id="../escaped-scene",
    )

    def _unexpected_validation(*_args, **_kwargs):
        raise AssertionError("unsafe destination reached media validation")

    monkeypatch.setattr(web_server, "validate_video_artifact", _unexpected_validation)
    response = client.post(
        f"/api/projects/{pid}/shots/{shot_id}/upload-driving-video",
        data={"driving_video": (io.BytesIO(b"payload"), "driving.mp4")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Shot media path is unsafe"
    assert not (tmp_path / pid / "escaped-scene").exists()
