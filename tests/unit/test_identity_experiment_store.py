from __future__ import annotations

from pathlib import Path

import pytest

from identity.experiment_store import (
    IdentityExperimentConflict,
    IdentityExperimentStore,
    IdentityExperimentValidationError,
)
from identity.protocols import BENCHMARK_PROMPT, SUPPORTED_PROTOCOL_ID


def _references(root: Path, count: int = 4) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    for index in range(count):
        path = root / f"reference-{index + 1}.png"
        path.write_bytes(f"reference-{index + 1}".encode())
        values.append(("canonical" if index == 0 else "angle", str(path)))
    return values


def _create(
    store: IdentityExperimentStore,
    root: Path,
    *,
    request_id: str = "request-0001",
    prompt: str = BENCHMARK_PROMPT,
):
    return store.create_experiment(
        project_id="project-a",
        character_id="character-a",
        request_id=request_id,
        prompt=prompt,
        aspect_ratio="1:1",
        protocol_id=SUPPORTED_PROTOCOL_ID,
        lora_consent=True,
        project_root=root,
        subject_paths=_references(root),
    )


def test_create_is_a_small_fixed_native_and_lora_queue(tmp_path: Path) -> None:
    store = IdentityExperimentStore(tmp_path / "identity.db")

    result = _create(store, tmp_path)

    assert result.created is True
    assert result.experiment["state"] == "queued"
    assert result.experiment["method"] == "identity_comparison"
    assert result.experiment["lora_consent"] is True
    assert [cell["method"] for cell in result.experiment["cells"]] == [
        "native_flux2",
        "native_flux2",
        "native_flux2",
        "flux2_character_lora",
        "flux2_character_lora",
    ]
    assert [cell["reference_count"] for cell in result.experiment["cells"]] == [1, 2, 4, 0, 0]
    assert all("path" not in reference for reference in result.experiment["references"])
    internal = store.get_internal(result.experiment["experiment_id"])
    assert internal is not None
    assert all(
        ".identity_lab/experiments/" in reference["path"]
        for reference in internal["references"]
    )


def test_same_request_replays_but_cannot_change_inputs(tmp_path: Path) -> None:
    store = IdentityExperimentStore(tmp_path / "identity.db")
    first = _create(store, tmp_path)

    replay = _create(store, tmp_path)

    assert replay.created is False
    assert replay.experiment["experiment_id"] == first.experiment["experiment_id"]
    with pytest.raises(IdentityExperimentConflict, match="different inputs"):
        _create(store, tmp_path, prompt="A different benchmark prompt")


def test_active_or_unknown_experiment_rejects_a_different_request(tmp_path: Path) -> None:
    store = IdentityExperimentStore(tmp_path / "identity.db")
    first = _create(store, tmp_path).experiment

    with pytest.raises(IdentityExperimentConflict, match="already has an active"):
        _create(store, tmp_path, request_id="request-0002")
    assert len(store.list_experiments("project-a")) == 1

    assert store.claim_next() is not None
    store.mark_cell_running(first["experiment_id"], "native_flux2:r1:s0")
    store.block_cell(
        first["experiment_id"],
        "native_flux2:r1:s0",
        state="unknown",
        safe_error="acknowledgement lost",
    )
    with pytest.raises(IdentityExperimentConflict, match="already has an active"):
        _create(store, tmp_path, request_id="request-0003")
    assert len(store.list_experiments("project-a")) == 1


def test_native_comparison_requires_four_distinct_reference_files(tmp_path: Path) -> None:
    store = IdentityExperimentStore(tmp_path / "identity.db")

    with pytest.raises(IdentityExperimentValidationError, match="four approved references"):
        store.create_experiment(
            project_id="project-a",
            character_id="character-a",
            request_id="request-0001",
            prompt=BENCHMARK_PROMPT,
            aspect_ratio="1:1",
            protocol_id=SUPPORTED_PROTOCOL_ID,
            lora_consent=True,
            project_root=tmp_path,
            subject_paths=_references(tmp_path, count=3),
        )


def test_claim_and_crash_recovery_requeue_only_the_interrupted_cell(tmp_path: Path) -> None:
    store = IdentityExperimentStore(tmp_path / "identity.db")
    created = _create(store, tmp_path).experiment
    claimed = store.claim_next()
    assert claimed is not None
    assert claimed["experiment_id"] == created["experiment_id"]
    store.mark_cell_running(created["experiment_id"], "native_flux2:r1:s0")

    assert store.recover_running() == 1

    detail = store.get_experiment("project-a", created["experiment_id"])
    assert detail is not None and detail["state"] == "queued"
    assert detail["cells"][0]["state"] == "pending"


def test_results_and_quality_verdict_are_stored_without_failing_generation(tmp_path: Path) -> None:
    store = IdentityExperimentStore(tmp_path / "identity.db")
    experiment_id = _create(store, tmp_path).experiment["experiment_id"]
    assert store.claim_next() is not None
    store.mark_cell_running(experiment_id, "native_flux2:r1:s0")

    store.complete_cell(
        experiment_id,
        "native_flux2:r1:s0",
        prompt_id="prompt-1",
        output_path=".identity_lab/experiments/example/r1.png",
        output_sha256="a" * 64,
        latency_ms=1234,
        identity_score=0.62,
        identity_verdict="failed",
    )

    detail = store.get_experiment("project-a", experiment_id)
    assert detail is not None
    assert detail["state"] == "running"
    assert detail["cells"][0]["state"] == "succeeded"
    assert detail["cells"][0]["identity_verdict"] == "failed"


def test_queued_or_running_rows_fence_project_mutation_until_cancelled(tmp_path: Path) -> None:
    store = IdentityExperimentStore(tmp_path / "identity.db")
    experiment_id = _create(store, tmp_path).experiment["experiment_id"]
    assert store.has_active_project("project-a") is True
    assert store.has_active_character("project-a", "character-a") is True
    assert store.claim_next() is not None
    assert store.has_active_character("project-a", "character-a") is True

    cancelled = store.cancel("project-a", experiment_id)

    assert cancelled is not None and cancelled["cancel_requested"] is True
    store.finish_cancelled(experiment_id)
    assert store.has_active_project("project-a") is False


def test_unknown_work_can_be_resumed_but_never_silently_replaced(tmp_path: Path) -> None:
    store = IdentityExperimentStore(tmp_path / "identity.db")
    experiment_id = _create(store, tmp_path).experiment["experiment_id"]
    assert store.claim_next() is not None
    store.mark_cell_running(experiment_id, "native_flux2:r1:s0")
    store.block_cell(
        experiment_id,
        "native_flux2:r1:s0",
        state="unknown",
        safe_error="Saved provider prompt needs recovery",
    )

    resumed = store.requeue("project-a", experiment_id)

    assert resumed is not None and resumed["state"] == "queued"
    assert resumed["cells"][0]["state"] == "pending"
    assert resumed["cells"][0]["attempt_index"] == 0


def test_confirmed_unbilled_failure_advances_only_its_retry_attempt(tmp_path: Path) -> None:
    store = IdentityExperimentStore(tmp_path / "identity.db")
    experiment_id = _create(store, tmp_path).experiment["experiment_id"]
    assert store.claim_next() is not None
    store.mark_cell_running(experiment_id, "native_flux2:r1:s0")
    store.block_cell(
        experiment_id,
        "native_flux2:r1:s0",
        state="failed",
        safe_error="preflight failed before submission",
    )

    resumed = store.requeue("project-a", experiment_id)

    assert resumed is not None
    assert resumed["cells"][0]["attempt_index"] == 1
    assert resumed["cells"][1]["attempt_index"] == 0


def test_resume_rejects_a_historical_run_while_another_run_is_active(tmp_path: Path) -> None:
    store = IdentityExperimentStore(tmp_path / "identity.db")
    historical_id = _create(store, tmp_path).experiment["experiment_id"]
    assert store.claim_next() is not None
    store.mark_cell_running(historical_id, "native_flux2:r1:s0")
    store.block_cell(
        historical_id,
        "native_flux2:r1:s0",
        state="blocked",
        safe_error="worker unavailable",
    )
    active_id = _create(
        store,
        tmp_path,
        request_id="request-0002",
    ).experiment["experiment_id"]

    with pytest.raises(IdentityExperimentConflict, match="already has an active"):
        store.requeue("project-a", historical_id)

    assert store.get_experiment("project-a", historical_id)["state"] == "blocked"
    assert store.get_experiment("project-a", active_id)["state"] == "queued"
