from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from identity.experiment_store import IdentityExperimentStore


@pytest.fixture
def identity_client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("IDENTITY_EXPERIMENT_DB_PATH", str(tmp_path / "identity.db"))
    import web_identity_experiments
    import web_server

    monkeypatch.setattr(
        web_identity_experiments,
        "_store",
        lambda: IdentityExperimentStore(tmp_path / "identity.db"),
    )
    monkeypatch.setattr(web_identity_experiments, "_wake_dispatcher", lambda: None)
    monkeypatch.setattr(
        web_identity_experiments,
        "_lora_method_card",
        lambda: {
            "method": "flux2_character_lora",
            "label": "FLUX.2 character LoRA",
            "state": "available",
            "reason": "Training and inference benchmark passed.",
            "blocker_code": "",
            "candidate_sha256": "c" * 64,
        },
    )
    project = {
        "id": "project-a",
        "name": "Project A",
        "global_settings": {"aspect_ratio": "1:1"},
        "characters": [
            {
                "id": "character-a",
                "name": "Character A",
                "canonical_reference": "reference-1.png",
                "reference_images": ["reference-1.png", "reference-4.png"],
                "multi_angle_refs": ["reference-2.png", "reference-3.png"],
            }
        ],
    }
    project_root = tmp_path / "projects" / "project-a"
    project_root.mkdir(parents=True)
    for index in range(1, 5):
        (project_root / f"reference-{index}.png").write_bytes(f"ref-{index}".encode())
    monkeypatch.setattr(web_identity_experiments, "load_existing_project_readonly", lambda pid: project if pid == "project-a" else None)
    monkeypatch.setattr(web_identity_experiments, "get_project_dir", lambda pid: str(project_root))
    monkeypatch.setattr(
        web_identity_experiments,
        "get_identity_reference_paths",
        lambda _project, _cid, _protocol: [
            ("canonical" if index == 1 else "angle", str(project_root / f"reference-{index}.png"))
            for index in range(1, 5)
        ],
    )
    web_server.app.config.update(TESTING=True)
    return web_server.app.test_client()


def _create_body(identity_client, request_id: str, **extra):
    listed = identity_client.get("/api/projects/project-a/identity-experiments").get_json()
    body = {
        "character_id": "character-a",
        "request_id": request_id,
        "lora_consent": True,
        "reference_fingerprint": listed["characters"][0]["reference_fingerprint"],
    }
    body.update(extra)
    return body


def test_list_returns_history_method_truth_and_character_eligibility(identity_client) -> None:
    response = identity_client.get("/api/projects/project-a/identity-experiments")

    assert response.status_code == 200
    body = response.get_json()
    assert body["experiments"] == []
    assert len(body["characters"]) == 1
    assert {
        key: body["characters"][0][key]
        for key in ("character_id", "name", "eligible", "reference_count", "reason")
    } == {
        "character_id": "character-a",
        "name": "Character A",
        "eligible": True,
        "reference_count": 4,
        "reason": "",
    }
    assert [method["state"] for method in body["methods"]] == ["available", "available", "blocked"]


def test_reference_consent_is_bound_to_the_exact_server_selected_tuple(identity_client) -> None:
    listed = identity_client.get("/api/projects/project-a/identity-experiments").get_json()
    character = listed["characters"][0]

    assert len(character["references"]) == 4
    assert [reference["role"] for reference in character["references"]] == [
        "canonical",
        "angle",
        "angle",
        "angle",
    ]
    assert all(len(reference["sha256"]) == 64 for reference in character["references"])
    assert all(reference["media_path"].startswith("reference-") for reference in character["references"])
    assert len(character["reference_fingerprint"]) == 64

    stale = identity_client.post(
        "/api/projects/project-a/identity-experiments",
        json={
            "character_id": "character-a",
            "request_id": "request-stale-fingerprint",
            "lora_consent": True,
            "reference_fingerprint": "0" * 64,
        },
    )
    assert stale.status_code == 409
    assert "changed" in stale.get_json()["error"].lower()


def test_create_requires_character_retry_key_and_lora_consent(identity_client) -> None:
    missing_binding = identity_client.post(
        "/api/projects/project-a/identity-experiments",
        json={"character_id": "character-a", "request_id": "request-missing", "lora_consent": True},
    )
    assert missing_binding.status_code == 400

    response = identity_client.post(
        "/api/projects/project-a/identity-experiments",
        json=_create_body(identity_client, "request-0001"),
    )

    assert response.status_code == 202
    body = response.get_json()
    assert body["state"] == "queued"
    assert body["method"] == "identity_comparison"
    assert body["lora_consent"] is True
    assert [cell["reference_count"] for cell in body["cells"]] == [1, 2, 4, 0, 0]

    rejected = identity_client.post(
        "/api/projects/project-a/identity-experiments",
        json=_create_body(identity_client, "request-0002", method="pulid_flux2"),
    )
    assert rejected.status_code == 400

    replacement = identity_client.post(
        "/api/projects/project-a/identity-experiments",
        json=_create_body(identity_client, "request-0003"),
    )
    assert replacement.status_code == 409
    assert "active identity experiment" in replacement.get_json()["error"]


def test_create_accepts_the_truthful_first_canary_state(
    identity_client, monkeypatch
) -> None:
    import web_identity_experiments

    monkeypatch.setattr(
        web_identity_experiments,
        "_lora_method_card",
        lambda: {
            "method": "flux2_character_lora",
            "label": "FLUX.2 character LoRA",
            "state": "canary",
            "reason": "The first run establishes both proofs.",
            "blocker_code": "candidate_training_not_proven",
            "candidate_sha256": "c" * 64,
        },
    )

    response = identity_client.post(
        "/api/projects/project-a/identity-experiments",
        json=_create_body(identity_client, "canary-request-0001"),
    )

    assert response.status_code == 202
    assert response.get_json()["method"] == "identity_comparison"


def test_create_requires_four_server_resolved_references(identity_client, monkeypatch) -> None:
    import web_identity_experiments

    project_root = Path(web_identity_experiments.get_project_dir("project-a"))

    monkeypatch.setattr(
        web_identity_experiments,
        "get_identity_reference_paths",
        lambda *_args: [("canonical", str(project_root / "reference-1.png"))],
    )
    response = identity_client.post(
        "/api/projects/project-a/identity-experiments",
        json={
            "character_id": "character-a",
            "request_id": "request-0001",
            "lora_consent": True,
            "reference_fingerprint": "0" * 64,
        },
    )

    assert response.status_code == 409
    assert "four approved references" in response.get_json()["error"]


def test_detail_cancel_resume_and_project_scope(identity_client) -> None:
    created = identity_client.post(
        "/api/projects/project-a/identity-experiments",
        json=_create_body(identity_client, "request-0001"),
    ).get_json()
    experiment_id = created["experiment_id"]

    detail = identity_client.get(f"/api/projects/project-a/identity-experiments/{experiment_id}")
    assert detail.status_code == 200
    assert detail.get_json()["experiment_id"] == experiment_id
    assert identity_client.get(f"/api/projects/other/identity-experiments/{experiment_id}").status_code == 404

    cancelled = identity_client.post(
        f"/api/projects/project-a/identity-experiments/{experiment_id}/cancel",
        json={},
    )
    assert cancelled.status_code == 200
    assert cancelled.get_json()["state"] == "cancelled"

    resumed = identity_client.post(
        f"/api/projects/project-a/identity-experiments/{experiment_id}/resume",
        json={},
    )
    assert resumed.status_code == 409


def test_resume_returns_conflict_when_another_experiment_is_active(identity_client) -> None:
    import web_identity_experiments

    historical = identity_client.post(
        "/api/projects/project-a/identity-experiments",
        json=_create_body(identity_client, "request-0001"),
    ).get_json()
    store = web_identity_experiments._store()
    assert store.claim_next() is not None
    store.mark_cell_running(historical["experiment_id"], "native_flux2:r1:s0")
    store.block_cell(
        historical["experiment_id"],
        "native_flux2:r1:s0",
        state="blocked",
        safe_error="worker unavailable",
    )
    active = identity_client.post(
        "/api/projects/project-a/identity-experiments",
        json=_create_body(identity_client, "request-0002"),
    )
    assert active.status_code == 202

    resumed = identity_client.post(
        f"/api/projects/project-a/identity-experiments/{historical['experiment_id']}/resume",
        json={},
    )

    assert resumed.status_code == 409
    assert "active identity experiment" in resumed.get_json()["error"]


def test_unexpected_runner_error_remains_non_replaceable_unknown(identity_client) -> None:
    import web_identity_experiments

    created = identity_client.post(
        "/api/projects/project-a/identity-experiments",
        json=_create_body(identity_client, "request-0001"),
    ).get_json()
    store = web_identity_experiments._store()
    claimed = store.claim_next()
    assert claimed is not None

    web_identity_experiments._block_unexpected_runner_error(
        store, claimed, RuntimeError("runner boundary failed")
    )

    detail = store.get_experiment("project-a", created["experiment_id"])
    assert detail is not None and detail["state"] == "unknown"
    replacement = identity_client.post(
        "/api/projects/project-a/identity-experiments",
        json=_create_body(identity_client, "request-0002"),
    )
    assert replacement.status_code == 409


def test_browser_cannot_supply_paths_prompts_or_workflow(identity_client) -> None:
    for field, value in (
        ("reference_paths", ["/tmp/private.png"]),
        ("prompt", "override"),
        ("workflow", {"node": "raw"}),
    ):
        response = identity_client.post(
            "/api/projects/project-a/identity-experiments",
            json=_create_body(identity_client, "request-0001", **{field: value}),
        )
        assert response.status_code == 400


def test_wake_restarts_a_dispatcher_whose_runner_thread_exited(monkeypatch) -> None:
    import web_identity_experiments

    class Dispatcher:
        def __init__(self) -> None:
            self.started = 0
            self.woken = 0

        def start(self) -> None:
            self.started += 1

        def wake(self) -> None:
            self.woken += 1

    dispatcher = Dispatcher()
    monkeypatch.setattr(web_identity_experiments, "_dispatcher", dispatcher)

    web_identity_experiments._wake_dispatcher()
    web_identity_experiments._wake_dispatcher()

    assert dispatcher.started == 2
    assert dispatcher.woken == 2


def test_lora_method_uses_the_same_authenticated_shared_worker(monkeypatch) -> None:
    import web_identity_experiments

    calls = []
    endpoint = SimpleNamespace(
        shared_endpoint=True,
        usable=True,
        server_url="http://127.0.0.1:18189",
        api_key="s" * 32,
    )
    monkeypatch.setattr(
        web_identity_experiments,
        "resolve_performance_comfyui",
        lambda _settings: endpoint,
    )

    class Client:
        def __init__(self, server_url, token, **_kwargs):
            calls.append((server_url, token))

        def get_readiness(self, candidate):
            return SimpleNamespace(
                state="ready",
                blocker_code="",
                candidate_sha256=candidate,
                job_submission_ready=True,
            )

    monkeypatch.setattr(web_identity_experiments, "LoraTrainingClient", Client)

    card = web_identity_experiments._lora_method_card()

    assert card["state"] == "available"
    assert calls == [(endpoint.server_url, endpoint.api_key)]


def test_lora_method_exposes_only_the_fresh_bootstrap_as_canary(monkeypatch) -> None:
    import web_identity_experiments

    monkeypatch.setattr(
        web_identity_experiments,
        "resolve_performance_comfyui",
        lambda _settings: SimpleNamespace(
            shared_endpoint=True,
            usable=True,
            server_url="http://127.0.0.1:18189",
            api_key="s" * 32,
        ),
    )

    class Client:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_readiness(self, candidate):
            return SimpleNamespace(
                state="blocked",
                blocker_code="candidate_training_not_proven",
                candidate_sha256=candidate,
                job_submission_ready=True,
            )

    monkeypatch.setattr(web_identity_experiments, "LoraTrainingClient", Client)

    card = web_identity_experiments._lora_method_card()

    assert card["state"] == "canary"
    assert "automatically prove" in card["reason"]


def test_lora_method_stays_blocked_without_shared_worker_contract(monkeypatch) -> None:
    import web_identity_experiments

    monkeypatch.setattr(
        web_identity_experiments,
        "resolve_performance_comfyui",
        lambda _settings: SimpleNamespace(shared_endpoint=False, usable=True),
    )
    monkeypatch.setattr(
        web_identity_experiments,
        "LoraTrainingClient",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unshared worker was queried")
        ),
    )

    assert web_identity_experiments._lora_method_card()["state"] == "blocked"
