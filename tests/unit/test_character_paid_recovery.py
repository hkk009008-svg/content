from __future__ import annotations

import copy
import hashlib
import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from cinema.artifact_versions import ArtifactVersionStore
from cost_tracker import CostTracker
from paid_provider import PaidCallBudgetBlocked, PaidCallDeferred


class _FalHandle:
    request_id = "fal-character-angle-request"


def _configure_one_angle(monkeypatch, cm, tmp_path: Path):
    monkeypatch.setattr(cm, "FAL_AVAILABLE", True)
    monkeypatch.setattr(cm, "settings", SimpleNamespace(fal_key="offline"))
    monkeypatch.setattr(
        cm,
        "_ANGLE_CONFIGS",
        ({"name": "angle_45", "prompt": "Turn 45 degrees."},),
    )
    uploads: list[str] = []
    submits: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        cm.fal_client,
        "upload_file",
        lambda path: uploads.append(path) or "https://fal.invalid/canonical.jpg",
    )
    monkeypatch.setattr(
        cm.fal_client,
        "submit",
        lambda application, arguments: submits.append((application, arguments))
        or _FalHandle(),
    )

    def download(_url, output, **_kwargs):
        Path(output).write_bytes(b"generated-angle-bytes")
        return output

    monkeypatch.setattr(cm, "safe_download", download)
    canonical = tmp_path / "canonical.jpg"
    canonical.write_bytes(b"canonical-source-bytes")
    character_root = tmp_path / "character"
    character_root.mkdir()
    return canonical, character_root, uploads, submits


def test_character_angle_resumes_fal_request_after_restart_without_duplicate_submit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import domain.character_manager as cm

    canonical, character_root, uploads, submits = _configure_one_angle(
        monkeypatch, cm, tmp_path
    )
    monkeypatch.setattr(cm, "FAL_TIMEOUT_IMAGE_S", 0)
    monkeypatch.setattr(
        cm.fal_client,
        "status",
        lambda *_args, **_kwargs: {"status": "IN_PROGRESS"},
    )
    db_path = str(tmp_path / "character-paid.db")

    first = CostTracker(db_path=db_path, budget_usd=1.0)
    try:
        with pytest.raises(PaidCallDeferred):
            cm._generate_multi_angle_refs(
                str(canonical),
                str(character_root),
                "description",
                cost_tracker=first,
                video_id="project-character",
                character_id="char-request",
            )
        pending = first.get_latest_paid_attempt(
            video_id="project-character",
            shot_id="char-request",
            engine="FLUX_KONTEXT",
            operation="multi_angle_ref",
        )
        assert pending["state"] == "accepted_unknown"
        assert pending["provider_job_id"] == "fal-character-angle-request"
    finally:
        first.close()

    changed_source = tmp_path / "changed-canonical.jpg"
    changed_source.write_bytes(b"different-person-bytes")
    conflicting_retry = CostTracker(db_path=db_path, budget_usd=1.0)
    try:
        with pytest.raises(ValueError, match="paid character work for different inputs"):
            cm._generate_multi_angle_refs(
                str(changed_source),
                str(character_root),
                "description",
                cost_tracker=conflicting_retry,
                video_id="project-character",
                character_id="char-request",
            )
        assert len(submits) == 1
        assert len(uploads) == 1
    finally:
        conflicting_retry.close()

    monkeypatch.setattr(
        cm.fal_client,
        "status",
        lambda *_args, **_kwargs: {"status": "COMPLETED"},
    )
    monkeypatch.setattr(
        cm.fal_client,
        "result",
        lambda *_args, **_kwargs: {
            "images": [{"url": "https://fal.invalid/generated.jpg"}]
        },
    )
    evidence: list[dict] = []
    restarted = CostTracker(db_path=db_path, budget_usd=1.0)
    try:
        references = cm._generate_multi_angle_refs(
            str(canonical),
            str(character_root),
            "description",
            cost_tracker=restarted,
            video_id="project-character",
            character_id="char-request",
            artifact_evidence_out=evidence,
        )
        assert len(references) == 2
        assert Path(references[1]).read_bytes() == b"generated-angle-bytes"
        assert len(submits) == 1
        assert len(uploads) == 1
        assert restarted.get_video_cost("project-character")["total_usd"] == pytest.approx(
            0.08
        )
        analytics = restarted.get_provider_usage_analytics("project-character")
        assert analytics["by_engine"]["FLUX_KONTEXT"]["succeeded"] == 1
        assert analytics["by_engine"]["FLUX_KONTEXT"]["charged_cost_usd"] == pytest.approx(
            0.08
        )
        assert analytics["by_engine"]["FLUX_KONTEXT"][
            "average_terminal_latency_s"
        ] is not None
        assert analytics["by_provider"]["fal"]["success_rate"] == 1.0
        assert evidence[0]["parameters"]["provider_request_id"] == (
            "fal-character-angle-request"
        )
    finally:
        restarted.close()


def test_character_angle_reserves_budget_before_fal_submit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import domain.character_manager as cm

    canonical, character_root, _uploads, submits = _configure_one_angle(
        monkeypatch, cm, tmp_path
    )
    tracker = CostTracker(db_path=str(tmp_path / "budget.db"), budget_usd=0.04)
    try:
        with pytest.raises(PaidCallBudgetBlocked):
            cm._generate_multi_angle_refs(
                str(canonical),
                str(character_root),
                "description",
                cost_tracker=tracker,
                video_id="project-budget",
                character_id="char-budget",
            )
        assert submits == []
        attempt = tracker.get_latest_paid_attempt(
            video_id="project-budget",
            shot_id="char-budget",
            engine="FLUX_KONTEXT",
            operation="multi_angle_ref",
        )
        assert attempt["state"] == "blocked_budget"
        assert tracker.get_video_cost("project-budget")["total_usd"] == 0.0
    finally:
        tracker.close()


def test_pending_character_reference_is_immutably_indexed_and_repair_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from domain import character_manager as cm
    from domain import project_manager as pm

    projects_root = tmp_path / "projects"
    monkeypatch.setattr(pm, "PROJECTS_DIR", str(projects_root))
    project = pm.create_project("Character artifact")
    cid = "char_" + "c" * 32
    root = Path(pm.get_project_dir(project["id"]))
    char_root = root / "characters" / cid
    char_root.mkdir(parents=True)
    canonical = char_root / "canonical.jpg"
    output = char_root / "angle_45.jpg"
    embedding = char_root / "embedding.npy"
    canonical.write_bytes(b"canonical-source")
    output.write_bytes(b"generated-reference")
    embedding.write_bytes(b"generated-embedding")
    character = pm.make_character("Hero", "Lead")
    character.update(
        {
            "id": cid,
            "creation_request_id": "c" * 32,
            "creation_request_fingerprint": "f" * 64,
            "canonical_reference": canonical.relative_to(root).as_posix(),
            "multi_angle_refs": [
                canonical.relative_to(root).as_posix(),
                output.relative_to(root).as_posix(),
            ],
            "artifact_versioning_pending": True,
            "embedding_cache": embedding.relative_to(root).as_posix(),
            "embedding_artifact_evidence": {
                "path": embedding.relative_to(root).as_posix(),
                "source_path": canonical.relative_to(root).as_posix(),
                "model": "GhostFaceNet",
                "parameters": {
                    "embedding_model": "GhostFaceNet",
                    "array_dtype": "float32",
                    "array_shape": [512],
                },
            },
            "multi_angle_artifact_evidence": [
                {
                    "angle_name": "angle_45",
                    "path": output.relative_to(root).as_posix(),
                    "source_path": canonical.relative_to(root).as_posix(),
                    "parameters": {
                        "prompt": "exact provider recipe",
                        "guidance_scale": 4.0,
                        "aspect_ratio": "3:4",
                        "output_format": "jpeg",
                        "num_images": 1,
                        "provider_request_id": "fal-character-angle-request",
                        "request_fingerprint": "d" * 64,
                    },
                }
            ],
        }
    )
    pm.add_character(project, character)
    pending_snapshot = copy.deepcopy(pm.load_project(project["id"]))
    original_pending_snapshot = copy.deepcopy(pending_snapshot)

    finalized = cm._finalize_character_reference_artifacts(
        pending_snapshot,
        pending_snapshot["characters"][0],
        commit_timeout=1,
    )
    assert finalized.get("artifact_versioning_pending") is None
    assert finalized.get("multi_angle_artifact_evidence") is None
    assert finalized.get("embedding_artifact_evidence") is None
    artifact_summary = finalized["generated_multi_angle_artifacts"][0]
    assert artifact_summary["sha256"] == hashlib.sha256(
        b"generated-reference"
    ).hexdigest()
    embedding_summary = finalized["generated_embedding_artifact"]
    assert embedding_summary["sha256"] == hashlib.sha256(
        b"generated-embedding"
    ).hexdigest()
    assert embedding_summary["model"] == "GhostFaceNet"

    store = ArtifactVersionStore(project["id"], root)
    history = store.history()
    assert len(history) == 2
    record = next(
        item for item in history
        if item["logical_name"] == f"assets/character_reference/{cid}-angle_45"
    )
    assert record["logical_name"] == f"assets/character_reference/{cid}-angle_45"
    assert record["provider"] == "fal"
    assert record["model"] == "fal-ai/flux-pro/kontext/max/multi"
    assert record["sha256"] == hashlib.sha256(b"generated-reference").hexdigest()
    assert record["source_hashes"]["canonical_reference"] == hashlib.sha256(
        b"canonical-source"
    ).hexdigest()
    assert record["parameters"]["provider_request_id"] == (
        "fal-character-angle-request"
    )
    embedding_record = next(
        item for item in history
        if item["logical_name"] == f"assets/character_embedding/{cid}"
    )
    assert embedding_record["model"] == "GhostFaceNet"
    assert embedding_record["sha256"] == hashlib.sha256(
        b"generated-embedding"
    ).hexdigest()
    assert embedding_record["source_hashes"]["canonical_reference"] == (
        hashlib.sha256(b"canonical-source").hexdigest()
    )

    # Replaying the exact pre-publication snapshot repairs the project row and
    # returns the same immutable ledger record instead of consuming a version.
    repaired_again = cm._finalize_character_reference_artifacts(
        copy.deepcopy(original_pending_snapshot),
        character,
        commit_timeout=1,
    )
    assert repaired_again["generated_multi_angle_artifacts"] == (
        finalized["generated_multi_angle_artifacts"]
    )
    assert repaired_again["generated_embedding_artifact"] == (
        finalized["generated_embedding_artifact"]
    )
    assert len(store.history()) == 2


def test_character_post_threads_cached_project_tracker_and_request_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from domain import project_manager as pm
    import web_server

    monkeypatch.setattr(pm, "PROJECTS_DIR", str(tmp_path / "projects"))
    project = pm.create_project("Character web flow")
    shared_tracker = object()
    captured: dict = {}

    def create_stub(project_snapshot, name, description, **kwargs):
        captured.update(kwargs)
        kwargs["_recovery_out"]["idempotent"] = False
        return {"id": "char_" + "a" * 32, "name": name, "description": description}

    monkeypatch.setattr(
        web_server,
        "_get_or_build_core",
        lambda pid: SimpleNamespace(cost_tracker=shared_tracker),
    )
    monkeypatch.setattr(web_server, "_evict_cached_project_core", lambda pid: None)
    monkeypatch.setattr(web_server, "create_character_with_images", create_stub)
    web_server.app.config.update(TESTING=True)
    client = web_server.app.test_client()
    response = client.post(
        f"/api/projects/{project['id']}/characters",
        data={
            "name": "Durable Hero",
            "description": "Lead",
            "creation_request_id": "a" * 32,
        },
    )

    assert response.status_code == 201
    assert captured["cost_tracker"] is shared_tracker
    assert captured["creation_request_id"] == "a" * 32

    def ambiguous_stub(*_args, **_kwargs):
        raise PaidCallDeferred(
            "lost submit acknowledgement",
            attempt={"state": "accepted_unknown", "provider_job_id": ""},
        )

    monkeypatch.setattr(web_server, "create_character_with_images", ambiguous_stub)
    ambiguous = client.post(
        f"/api/projects/{project['id']}/characters",
        data={
            "name": "Ambiguous Hero",
            "creation_request_id": "b" * 32,
        },
    )
    assert ambiguous.status_code == 409
    assert ambiguous.get_json()["code"] == "paid_work_reconciliation_required"
    assert ambiguous.get_json()["retryable"] is False


def test_lost_character_post_response_returns_existing_character_without_provider_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from domain import character_manager as cm
    from domain import project_manager as pm

    monkeypatch.setattr(pm, "PROJECTS_DIR", str(tmp_path / "projects"))
    project = pm.create_project("Character response recovery")
    upload = tmp_path / "hero.jpg"
    upload.write_bytes(b"exact-upload")
    request_id = "e" * 32
    fingerprint = cm._character_creation_fingerprint(
        name="Hero",
        description="Lead",
        voice_id="voice-1",
        gender="",
        reference_image_paths=[str(upload)],
    )
    character = pm.make_character("Hero", "Lead", voice_id="voice-1")
    character.update(
        {
            "id": f"char_{request_id}",
            "creation_request_id": request_id,
            "creation_request_fingerprint": fingerprint,
        }
    )
    pm.add_character(project, character)
    current = pm.load_project(project["id"])
    monkeypatch.setattr(
        cm,
        "_generate_multi_angle_refs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("completed creation retry must not enter provider dispatch")
        ),
    )
    recovery: dict = {}

    result = cm.create_character_with_images(
        current,
        "Hero",
        "Lead",
        reference_image_paths=[str(upload)],
        voice_id="voice-1",
        creation_request_id=request_id,
        cost_tracker=object(),
        _recovery_out=recovery,
    )

    assert result["id"] == f"char_{request_id}"
    assert recovery == {"idempotent": True, "character_id": f"char_{request_id}"}
    assert len(pm.load_project(project["id"])["characters"]) == 1


def test_character_post_recovery_survives_new_session_and_fences_new_paid_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from domain import project_manager as pm
    import web_server

    monkeypatch.setattr(pm, "PROJECTS_DIR", str(tmp_path / "projects"))
    project = pm.create_project("Fresh-session character recovery")
    request_id = "1" * 32
    other_request_id = "2" * 32
    calls: list[dict] = []

    def create_stub(_project, name, description, **kwargs):
        paths = list(kwargs["reference_image_paths"])
        calls.append({
            "name": name,
            "description": description,
            "voice_id": kwargs["voice_id"],
            "paths": paths,
            "bytes": [Path(path).read_bytes() for path in paths],
            "request_id": kwargs["creation_request_id"],
        })
        if len(calls) == 1:
            raise PaidCallDeferred(
                "provider still running",
                attempt={
                    "state": "running",
                    "provider_job_id": "fal-job-safe-123",
                },
            )
        kwargs["_recovery_out"]["idempotent"] = False
        return {"id": f"char_{request_id}", "name": name}

    monkeypatch.setattr(
        web_server,
        "_get_or_build_core",
        lambda _pid: SimpleNamespace(cost_tracker=object()),
    )
    monkeypatch.setattr(web_server, "_evict_cached_project_core", lambda _pid: None)
    monkeypatch.setattr(web_server, "create_character_with_images", create_stub)
    web_server.app.config.update(TESTING=True)
    client = web_server.app.test_client()

    first = client.post(
        f"/api/projects/{project['id']}/characters",
        data={
            "name": "Durable Hero",
            "description": "Original description",
            "voice_id": "voice-original",
            "creation_request_id": request_id,
            "reference_images": (io.BytesIO(b"exact-face-bytes"), "face.png"),
        },
        content_type="multipart/form-data",
    )
    assert first.status_code == 409
    first_body = first.get_json()
    assert first_body["code"] == "paid_work_pending"
    assert first_body["pending_creation"]["status"] == "retryable"
    assert first_body["pending_creation"]["provider_job_id"] == "fal-job-safe-123"
    recovery_dir = (
        Path(pm.get_project_dir(project["id"])) / "temp_uploads" / request_id
    )
    assert recovery_dir.is_dir()

    # A wholly new browser session can discover the reservation without any
    # browser storage. The projection contains no staged filenames or paths.
    discovered = client.get(
        f"/api/projects/{project['id']}/characters/pending-creation"
    )
    assert discovered.status_code == 200
    public_pending = discovered.get_json()["pending_creation"]
    assert public_pending["creation_request_id"] == request_id
    assert public_pending["name"] == "Durable Hero"
    assert set(public_pending) == {
        "creation_request_id",
        "name",
        "status",
        "retryable",
        "message",
        "provider_job_id",
        "attempt_state",
        "created_at",
        "updated_at",
    }
    assert "face.png" not in str(public_pending)
    assert "temp_uploads" not in str(public_pending)
    assert "Original description" not in str(public_pending)

    blocked = client.post(
        f"/api/projects/{project['id']}/characters",
        data={
            "name": "Duplicate Spend",
            "creation_request_id": other_request_id,
        },
    )
    assert blocked.status_code == 409
    assert blocked.get_json()["code"] == "character_creation_recovery_required"
    assert len(calls) == 1
    assert not (
        Path(pm.get_project_dir(project["id"]))
        / "temp_uploads"
        / other_request_id
    ).exists()

    # Resume has only the durable token. The server restores and verifies the
    # original metadata and staged upload because a FileList cannot survive a
    # browser reload.
    resumed = client.post(
        f"/api/projects/{project['id']}/characters",
        data={"creation_request_id": request_id},
    )
    assert resumed.status_code == 201
    assert len(calls) == 2
    assert calls[1]["name"] == "Durable Hero"
    assert calls[1]["description"] == "Original description"
    assert calls[1]["voice_id"] == "voice-original"
    assert calls[1]["request_id"] == request_id
    assert len(calls[1]["paths"]) == 1
    assert calls[1]["bytes"] == [b"exact-face-bytes"]
    assert not recovery_dir.exists()
    assert client.get(
        f"/api/projects/{project['id']}/characters/pending-creation"
    ).get_json() == {"pending_creation": None}


def test_character_reconciliation_requires_explicit_confirmation_and_is_audited(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from domain import project_manager as pm
    import web_server

    monkeypatch.setattr(pm, "PROJECTS_DIR", str(tmp_path / "projects"))
    project = pm.create_project("Manual character reconciliation")
    request_id = "3" * 32

    def ambiguous_stub(*_args, **_kwargs):
        raise PaidCallDeferred(
            "lost acknowledgement",
            attempt={"state": "accepted_unknown", "provider_job_id": ""},
        )

    monkeypatch.setattr(
        web_server,
        "_get_or_build_core",
        lambda _pid: SimpleNamespace(cost_tracker=object()),
    )
    monkeypatch.setattr(web_server, "_evict_cached_project_core", lambda _pid: None)
    monkeypatch.setattr(web_server, "create_character_with_images", ambiguous_stub)
    web_server.app.config.update(TESTING=True)
    client = web_server.app.test_client()

    ambiguous = client.post(
        f"/api/projects/{project['id']}/characters",
        data={"name": "Ambiguous Hero", "creation_request_id": request_id},
    )
    assert ambiguous.status_code == 409
    assert ambiguous.get_json()["pending_creation"]["status"] == (
        "reconciliation_required"
    )
    recovery_dir = (
        Path(pm.get_project_dir(project["id"])) / "temp_uploads" / request_id
    )
    request_lock = web_server.FileLock(str(recovery_dir / ".resume.lock"), timeout=0)
    request_lock.acquire()
    try:
        active = client.delete(
            f"/api/projects/{project['id']}/characters/pending-creation",
            json={
                "creation_request_id": request_id,
                "confirmation": "reconciled_no_resumable_paid_work",
            },
        )
    finally:
        request_lock.release()
    assert active.status_code == 409
    assert active.get_json()["code"] == "character_creation_in_progress"
    assert recovery_dir.is_dir()

    rejected = client.delete(
        f"/api/projects/{project['id']}/characters/pending-creation",
        json={"creation_request_id": request_id, "confirmation": "yes"},
    )
    assert rejected.status_code == 400
    assert pm.load_project(project["id"])["pending_character_creation"]

    reconciled = client.delete(
        f"/api/projects/{project['id']}/characters/pending-creation",
        json={
            "creation_request_id": request_id,
            "confirmation": "reconciled_no_resumable_paid_work",
        },
    )
    assert reconciled.status_code == 200
    saved = pm.load_project(project["id"])
    assert "pending_character_creation" not in saved
    assert not recovery_dir.exists()
    assert saved["character_creation_reconciliations"][-1][
        "creation_request_id"
    ] == request_id


def test_character_terminal_refusal_cleans_staging_and_metadata_is_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from domain import project_manager as pm
    import web_server

    monkeypatch.setattr(pm, "PROJECTS_DIR", str(tmp_path / "projects"))
    project = pm.create_project("Character cleanup")
    request_id = "4" * 32
    calls = 0

    def budget_stub(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise PaidCallBudgetBlocked(
            "budget refused", attempt={"state": "blocked_budget"}
        )

    monkeypatch.setattr(
        web_server,
        "_get_or_build_core",
        lambda _pid: SimpleNamespace(cost_tracker=object()),
    )
    monkeypatch.setattr(web_server, "create_character_with_images", budget_stub)
    web_server.app.config.update(TESTING=True)
    client = web_server.app.test_client()

    oversized = client.post(
        f"/api/projects/{project['id']}/characters",
        data={
            "name": "x" * 201,
            "creation_request_id": request_id,
            "reference_images": (io.BytesIO(b"must-not-stage"), "face.png"),
        },
        content_type="multipart/form-data",
    )
    assert oversized.status_code == 400
    assert oversized.get_json()["code"] == "invalid_character_metadata"
    assert calls == 0

    refused = client.post(
        f"/api/projects/{project['id']}/characters",
        data={
            "name": "Budget Hero",
            "creation_request_id": request_id,
            "reference_images": (io.BytesIO(b"temporary"), "face.png"),
        },
        content_type="multipart/form-data",
    )
    assert refused.status_code == 409
    assert refused.get_json()["code"] == "paid_budget_blocked"
    assert calls == 1
    assert "pending_character_creation" not in pm.load_project(project["id"])
    assert not (
        Path(pm.get_project_dir(project["id"])) / "temp_uploads" / request_id
    ).exists()
