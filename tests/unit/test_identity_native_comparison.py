from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from identity.experiment_store import IdentityExperimentConflict, IdentityExperimentStore
from identity.lora_training import LoraTrainingStateUnknown
from identity.native_comparison import run_identity_experiment as _run_identity_experiment
from identity.protocols import BENCHMARK_PROMPT, SUPPORTED_PROTOCOL_ID


class FakeTracker:
    def __init__(self, attempt=None):
        self.attempt = attempt

    def get_latest_paid_attempt(self, **_kwargs):
        return self.attempt


def _train_lora(**kwargs):
    assert len(kwargs["reference_paths"]) == 4
    return SimpleNamespace(
        job_id="b" * 32,
        adapter_sha256="c" * 64,
        raw={"candidate_sha256": "d" * 64},
    )


def _run_lora_job(**kwargs):
    output = Path(kwargs["output_path"])
    output.write_bytes(f"lora-{kwargs['mode']}".encode())
    return SimpleNamespace(
        prompt_id=f"lora-{kwargs['mode']}", published_path=str(output)
    )


def run_identity_experiment(*args, **kwargs):
    kwargs.setdefault("train_lora", _train_lora)
    kwargs.setdefault("run_lora_job", _run_lora_job)
    return _run_identity_experiment(*args, **kwargs)


def _queued(tmp_path: Path):
    root = tmp_path / "project-a"
    root.mkdir()
    references = []
    for index in range(4):
        path = root / f"reference-{index + 1}.png"
        path.write_bytes(f"reference-{index + 1}".encode())
        references.append(("canonical" if index == 0 else "angle", str(path)))
    store = IdentityExperimentStore(tmp_path / "identity.db")
    created = store.create_experiment(
        project_id="project-a",
        character_id="character-a",
        request_id="request-0001",
        prompt=BENCHMARK_PROMPT,
        aspect_ratio="1:1",
        protocol_id=SUPPORTED_PROTOCOL_ID,
        lora_consent=True,
        project_root=root,
        subject_paths=references,
    ).experiment
    claimed = store.claim_next()
    assert claimed is not None
    return root, store, created["experiment_id"], claimed


def test_runner_executes_exact_1_2_4_and_retains_results(tmp_path: Path) -> None:
    root, store, experiment_id, claimed = _queued(tmp_path)
    calls: list[tuple[int, int, str]] = []
    training_calls = 0
    lora_calls: list[str] = []

    def run_job(**kwargs):
        output = Path(kwargs["output_path"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(f"output-{len(calls)}".encode())
        calls.append((len(kwargs["reference_image_paths"]), kwargs["seed"], kwargs["request_id"]))
        return SimpleNamespace(prompt_id=f"prompt-{len(calls)}", published_path=str(output))

    def train_lora(**kwargs):
        nonlocal training_calls
        training_calls += 1
        return _train_lora(**kwargs)

    def run_lora(**kwargs):
        lora_calls.append(kwargs["mode"])
        return _run_lora_job(**kwargs)

    run_identity_experiment(
        store,
        claimed,
        project_root=root,
        run_job=run_job,
        train_lora=train_lora,
        run_lora_job=run_lora,
        tracker_context=lambda: nullcontext(FakeTracker()),
        score_image=lambda *_args, **_kwargs: (0.81, "passed"),
    )

    assert [(count, seed) for count, seed, _request in calls] == [(1, 0), (2, 0), (4, 0)]
    assert len({request for _count, _seed, request in calls}) == 3
    assert training_calls == 1
    assert lora_calls == ["control", "adapter"]
    detail = store.get_experiment("project-a", experiment_id)
    assert detail is not None and detail["state"] == "succeeded"
    assert [cell["identity_score"] for cell in detail["cells"]] == [0.81] * 5
    assert all(cell["output_path"].startswith(".artifact_versions/objects/") for cell in detail["cells"])


def test_scorer_failure_is_unknown_quality_not_failed_generation(tmp_path: Path) -> None:
    root, store, experiment_id, claimed = _queued(tmp_path)

    def run_job(**kwargs):
        output = Path(kwargs["output_path"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"generated")
        return SimpleNamespace(prompt_id="prompt", published_path=str(output))

    def score(*_args, **_kwargs):
        raise RuntimeError("local scorer unavailable")

    run_identity_experiment(
        store,
        claimed,
        project_root=root,
        run_job=run_job,
        tracker_context=lambda: nullcontext(FakeTracker()),
        score_image=score,
    )

    detail = store.get_experiment("project-a", experiment_id)
    assert detail is not None and detail["state"] == "succeeded"
    assert [cell["identity_verdict"] for cell in detail["cells"]] == ["unknown"] * 5
    assert [cell["identity_score"] for cell in detail["cells"]] == [None] * 5


def test_ambiguous_provider_attempt_stops_later_cells(tmp_path: Path) -> None:
    root, store, experiment_id, claimed = _queued(tmp_path)
    tracker = FakeTracker({"state": "accepted_unknown"})
    calls = 0

    def run_job(**_kwargs):
        nonlocal calls
        calls += 1
        raise RuntimeError("lost acknowledgement")

    run_identity_experiment(
        store,
        claimed,
        project_root=root,
        run_job=run_job,
        tracker_context=lambda: nullcontext(tracker),
        score_image=lambda *_args: (None, "unknown"),
    )

    detail = store.get_experiment("project-a", experiment_id)
    assert calls == 1
    assert detail is not None and detail["state"] == "unknown"
    assert [cell["state"] for cell in detail["cells"]] == [
        "unknown",
        "pending",
        "pending",
        "pending",
        "pending",
    ]


def test_pre_dispatch_unavailability_is_retryable_blocked(tmp_path: Path) -> None:
    root, store, experiment_id, claimed = _queued(tmp_path)

    run_identity_experiment(
        store,
        claimed,
        project_root=root,
        run_job=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("worker offline")),
        tracker_context=lambda: nullcontext(FakeTracker(None)),
        score_image=lambda *_args: (None, "unknown"),
    )

    detail = store.get_experiment("project-a", experiment_id)
    assert detail is not None and detail["state"] == "blocked"
    assert detail["cells"][0]["state"] == "blocked"


def test_succeeded_gpu_attempt_with_artifact_failure_fences_replacement(
    tmp_path: Path,
) -> None:
    root, store, experiment_id, claimed = _queued(tmp_path)

    def run_job(**kwargs):
        output = Path(kwargs["output_path"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"generated")
        return SimpleNamespace(prompt_id="durable-prompt", published_path=str(output))

    class BrokenArtifactStore:
        def record_artifact(self, *_args, **_kwargs):
            raise OSError("artifact ledger unavailable")

    run_identity_experiment(
        store,
        claimed,
        project_root=root,
        run_job=run_job,
        tracker_context=lambda: nullcontext(FakeTracker({"state": "succeeded"})),
        score_image=lambda *_args: (None, "unknown"),
        artifact_store_factory=lambda *_args: BrokenArtifactStore(),
    )

    detail = store.get_experiment("project-a", experiment_id)
    assert detail is not None and detail["state"] == "unknown"
    assert detail["cells"][0]["state"] == "unknown"
    assert store.has_active_project("project-a") is True
    with pytest.raises(IdentityExperimentConflict, match="already has an active"):
        store.create_experiment(
            project_id="project-a",
            character_id="character-a",
            request_id="request-0002",
            prompt=BENCHMARK_PROMPT,
            aspect_ratio="1:1",
            protocol_id=SUPPORTED_PROTOCOL_ID,
            lora_consent=True,
            project_root=root,
            subject_paths=[
                ("canonical" if index == 1 else "angle", str(root / f"reference-{index}.png"))
                for index in range(1, 5)
            ],
        )


def test_lora_training_unknown_stops_without_replacement_work(tmp_path: Path) -> None:
    root, store, experiment_id, claimed = _queued(tmp_path)
    native_calls = 0
    lora_calls = 0

    def run_job(**kwargs):
        nonlocal native_calls
        native_calls += 1
        output = Path(kwargs["output_path"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"native")
        return SimpleNamespace(
            prompt_id=f"native-{native_calls}", published_path=str(output)
        )

    def unknown_training(**_kwargs):
        raise LoraTrainingStateUnknown("b" * 32, "launch acknowledgement lost")

    def forbidden_lora(**_kwargs):
        nonlocal lora_calls
        lora_calls += 1
        raise AssertionError("unknown training launched inference")

    run_identity_experiment(
        store,
        claimed,
        project_root=root,
        run_job=run_job,
        train_lora=unknown_training,
        run_lora_job=forbidden_lora,
        tracker_context=lambda: nullcontext(FakeTracker()),
        score_image=lambda *_args: (None, "unknown"),
    )

    detail = store.get_experiment("project-a", experiment_id)
    assert detail is not None and detail["state"] == "unknown"
    assert native_calls == 3
    assert lora_calls == 0
    assert [cell["state"] for cell in detail["cells"]] == [
        "succeeded",
        "succeeded",
        "succeeded",
        "unknown",
        "pending",
    ]


def test_lora_cell_latency_excludes_training_time(
    tmp_path: Path, monkeypatch
) -> None:
    root, store, experiment_id, claimed = _queued(tmp_path)
    clock = [0.0]

    monkeypatch.setattr(
        "identity.native_comparison.time.monotonic", lambda: clock[0]
    )

    def run_native(**kwargs):
        output = Path(kwargs["output_path"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"native")
        clock[0] += 1.0
        return SimpleNamespace(prompt_id="native", published_path=str(output))

    def train(**kwargs):
        clock[0] += 100.0
        return _train_lora(**kwargs)

    def run_lora(**kwargs):
        result = _run_lora_job(**kwargs)
        clock[0] += 2.0
        return result

    run_identity_experiment(
        store,
        claimed,
        project_root=root,
        run_job=run_native,
        train_lora=train,
        run_lora_job=run_lora,
        tracker_context=lambda: nullcontext(FakeTracker()),
        score_image=lambda *_args: (None, "unknown"),
    )

    detail = store.get_experiment("project-a", experiment_id)
    assert detail is not None
    assert [cell["latency_ms"] for cell in detail["cells"]] == [
        1000,
        1000,
        1000,
        2000,
        2000,
    ]


def test_cancel_requested_during_lora_training_skips_inference(tmp_path: Path) -> None:
    root, store, experiment_id, claimed = _queued(tmp_path)
    lora_calls = 0

    def run_native(**kwargs):
        output = Path(kwargs["output_path"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"native")
        return SimpleNamespace(prompt_id="native", published_path=str(output))

    def train(**kwargs):
        cancelled = store.cancel("project-a", experiment_id)
        assert cancelled is not None and cancelled["cancel_requested"] is True
        return _train_lora(**kwargs)

    def forbidden_lora(**_kwargs):
        nonlocal lora_calls
        lora_calls += 1
        raise AssertionError("cancelled training launched inference")

    run_identity_experiment(
        store,
        claimed,
        project_root=root,
        run_job=run_native,
        train_lora=train,
        run_lora_job=forbidden_lora,
        tracker_context=lambda: nullcontext(FakeTracker()),
        score_image=lambda *_args: (None, "unknown"),
    )

    detail = store.get_experiment("project-a", experiment_id)
    assert detail is not None and detail["state"] == "cancelled"
    assert lora_calls == 0
    assert [cell["state"] for cell in detail["cells"]] == [
        "succeeded",
        "succeeded",
        "succeeded",
        "cancelled",
        "cancelled",
    ]


def test_runner_uses_immutable_experiment_reference_copies(tmp_path: Path) -> None:
    root, store, _experiment_id, claimed = _queued(tmp_path)
    (root / "reference-1.png").write_bytes(b"replacement-after-admission")

    def run_job(**kwargs):
        first = Path(kwargs["reference_image_paths"][0])
        assert first.read_bytes() == b"reference-1"
        assert ".identity_lab/experiments/" in first.as_posix()
        output = Path(kwargs["output_path"])
        output.write_bytes(b"generated")
        return SimpleNamespace(prompt_id="prompt", published_path=str(output))

    run_identity_experiment(
        store,
        claimed,
        project_root=root,
        run_job=run_job,
        tracker_context=lambda: nullcontext(FakeTracker()),
        score_image=lambda *_args: (None, "unknown"),
    )


def test_confirmed_unbilled_resume_uses_a_new_attempt_key(tmp_path: Path) -> None:
    root, store, experiment_id, claimed = _queued(tmp_path)
    run_identity_experiment(
        store,
        claimed,
        project_root=root,
        run_job=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("preflight")),
        tracker_context=lambda: nullcontext(FakeTracker({"state": "failed_unbilled"})),
        score_image=lambda *_args: (None, "unknown"),
    )
    resumed = store.requeue("project-a", experiment_id)
    assert resumed is not None
    claimed_retry = store.claim_next()
    assert claimed_retry is not None
    request_ids: list[str] = []

    def run_job(**kwargs):
        request_ids.append(kwargs["request_id"])
        output = Path(kwargs["output_path"])
        output.write_bytes(b"generated")
        return SimpleNamespace(prompt_id="prompt", published_path=str(output))

    run_identity_experiment(
        store,
        claimed_retry,
        project_root=root,
        run_job=run_job,
        tracker_context=lambda: nullcontext(FakeTracker()),
        score_image=lambda *_args: (None, "unknown"),
    )

    assert request_ids[0].endswith(":a1")
