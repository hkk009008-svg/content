"""Thin native FLUX.2 1/2/4 comparison runner."""

from __future__ import annotations

import hashlib
import stat
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, ContextManager, Mapping

from filelock import FileLock, Timeout as FileLockTimeout

from cinema.artifact_versions import ArtifactVersionStore
from config.settings import settings
from cost_tracker import CostTracker
from identity.experiment_store import IdentityExperimentStore
from identity.lora_training import LoraTrainingStateUnknown
from identity.protocols import LORA_BENCHMARK_PROMPT
from pipeline_jobs import safe_error_summary


IDENTITY_THRESHOLD = 0.70


@contextmanager
def _cost_tracker_context():
    with CostTracker(db_path=settings.experiments_db_path) as tracker:
        yield tracker


def _score_local_identity(
    output_path: str,
    reference_path: str,
    character_id: str,
) -> tuple[float | None, str]:
    """Score locally only; never fall through to a paid vision model."""

    from identity import validator as validator_module

    if not validator_module.DEEPFACE_AVAILABLE:
        return None, "unknown"
    validator = validator_module.IdentityValidator(vision_fallback=None)
    result = validator.validate_image(
        output_path,
        reference_path,
        character_id=character_id,
        shot_type="portrait",
        threshold=IDENTITY_THRESHOLD,
    )
    score = result.overall_score
    if result.skipped or score is None:
        return None, "unknown"
    return float(score), "passed" if result.passed else "failed"


def _verify_reference(reference: Mapping[str, Any]) -> str:
    path = Path(str(reference["path"]))
    try:
        before = path.lstat()
        resolved = path.resolve(strict=True)
    except (FileNotFoundError, OSError, RuntimeError) as exc:
        raise RuntimeError("approved identity reference is no longer available") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RuntimeError("approved identity reference is no longer available")
    content = resolved.read_bytes()
    after = path.lstat()
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or path.resolve(strict=True) != resolved:
        raise RuntimeError("approved identity reference changed during verification")
    if hashlib.sha256(content).hexdigest() != reference["sha256"]:
        raise RuntimeError("approved identity reference changed after admission")
    if len(content) != reference["size_bytes"]:
        raise RuntimeError("approved identity reference size changed after admission")
    return str(resolved)


def _attempt_after_error(
    tracker: Any,
    *,
    project_id: str,
    shot_id: str,
    engine: str,
    operation: str,
) -> Mapping[str, Any] | None:
    getter = getattr(tracker, "get_latest_paid_attempt", None)
    if not callable(getter):
        return None
    return getter(
        video_id=project_id,
        shot_id=shot_id,
        engine=engine,
        operation=operation,
    )


def _failure_state(attempt: Mapping[str, Any] | None) -> str:
    state = str((attempt or {}).get("state") or "")
    if state in {"accepted_unknown", "running", "reserved", "submitting"}:
        return "unknown"
    if state == "succeeded":
        # Provider work exists but local reconciliation (for example artifact
        # recording) did not finish. Keep the experiment non-replaceable; an
        # explicit resume reuses this cell's exact request identity.
        return "unknown"
    if state == "failed_unbilled":
        return "failed"
    # No durable attempt means the call stopped before provider submission.
    return "blocked"


def run_identity_experiment(
    store: IdentityExperimentStore,
    experiment: Mapping[str, Any],
    *,
    project_root: str | Path,
    run_job: Callable[..., Any] | None = None,
    train_lora: Callable[..., Any] | None = None,
    run_lora_job: Callable[..., Any] | None = None,
    tracker_context: Callable[[], ContextManager[Any]] = _cost_tracker_context,
    score_image: Callable[[str, str, str], tuple[float | None, str]] = _score_local_identity,
    artifact_store_factory: Callable[[str, str | Path], ArtifactVersionStore] = ArtifactVersionStore,
) -> None:
    """Execute pending cells sequentially and persist each retained result."""

    if run_job is None:
        from performance.flux2_klein import run_flux2_klein_image_job

        run_job = run_flux2_klein_image_job
    if train_lora is None or run_lora_job is None:
        from identity.lora_inference import run_flux2_lora_image_job, train_character_lora

        train_lora = train_lora or train_character_lora
        run_lora_job = run_lora_job or run_flux2_lora_image_job
    experiment_id = str(experiment["experiment_id"])
    project_id = str(experiment["project_id"])
    character_id = str(experiment["character_id"])
    root = Path(project_root).resolve(strict=True)
    output_dir = root / ".identity_lab" / "experiments" / experiment_id
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_store = artifact_store_factory(project_id, root)
    references = list(experiment["references"])
    lora_evidence: Any | None = None

    with tracker_context() as tracker:
        for cell in experiment["cells"]:
            if cell["state"] == "succeeded":
                continue
            if store.cancel_requested(experiment_id):
                store.finish_cancelled(experiment_id)
                return
            cell_key = str(cell["cell_key"])
            method = str(
                cell.get("method")
                or ("native_flux2" if cell_key.startswith("native_flux2:") else "")
            )
            store.mark_cell_running(experiment_id, cell_key)
            count = int(cell["reference_count"])
            seed = int(cell["seed"])
            attempt_index = int(cell.get("attempt_index", 0))
            variant = "control" if ":control:" in cell_key else "adapter"
            shot_id = (
                f"identity-{experiment_id[:12]}-r{count}"
                if method == "native_flux2"
                else f"identity-{experiment_id[:12]}-lora-{variant}"
            )
            request_id = f"{experiment_id}:{cell_key}:a{attempt_index}"
            output_path = output_dir / (
                f"r{count}.png" if method == "native_flux2" else f"lora-{variant}.png"
            )
            try:
                reference_paths = [_verify_reference(value) for value in references]
                if method == "native_flux2":
                    started = time.monotonic()
                    result = run_job(
                        prompt=experiment["prompt"],
                        reference_image_paths=reference_paths[:count],
                        output_path=str(output_path),
                        seed=seed,
                        aspect_ratio=experiment["aspect_ratio"],
                        cost_tracker=tracker,
                        shot_id=shot_id,
                        video_id=project_id,
                        request_id=request_id,
                        filename_prefix=f"identity-{experiment_id[:12]}-r{count}",
                    )
                    prompt = str(experiment["prompt"])
                    provider_model = "flux2-klein-4b-distilled-fp8"
                    source_hashes = {
                        f"reference-{index + 1}": reference["sha256"]
                        for index, reference in enumerate(references[:count])
                    }
                    parameters = {"reference_count": count}
                    engine = "FLUX2_KLEIN_LOCAL"
                    operation = "keyframe_generation"
                elif method == "flux2_character_lora":
                    if lora_evidence is None:
                        lora_evidence = train_lora(
                            reference_paths=reference_paths,
                            project_id=project_id,
                            character_id=character_id,
                            allow_interrupted_resume=bool(cell.get("explicit_resume")),
                        )
                    if store.cancel_requested(experiment_id):
                        store.finish_cancelled(experiment_id)
                        return
                    started = time.monotonic()
                    result = run_lora_job(
                        prompt=LORA_BENCHMARK_PROMPT,
                        mode=variant,
                        evidence=lora_evidence,
                        output_path=str(output_path),
                        cost_tracker=tracker,
                        shot_id=shot_id,
                        video_id=project_id,
                        request_id=request_id,
                    )
                    prompt = LORA_BENCHMARK_PROMPT
                    provider_model = (
                        "flux2-klein-4b-distilled-fp8-text-control"
                        if variant == "control"
                        else "flux2-klein-4b-distilled-fp8-character-lora"
                    )
                    source_hashes = {
                        f"reference-{index + 1}": reference["sha256"]
                        for index, reference in enumerate(references)
                    }
                    if variant == "adapter":
                        source_hashes["lora-adapter"] = lora_evidence.adapter_sha256
                    parameters = {
                        "reference_count": 0,
                        "lora_variant": variant,
                        "lora_job_id": lora_evidence.job_id,
                        "candidate_sha256": lora_evidence.raw["candidate_sha256"],
                    }
                    engine = "FLUX2_KLEIN_LORA_LOCAL"
                    operation = "identity_inference"
                else:
                    raise RuntimeError("identity comparison cell method is unsupported")
                record = artifact_store.record_artifact(
                    f"identity-lab/{experiment_id}/{cell_key.replace(':', '-')}",
                    result.published_path,
                    media_type="image/png",
                    provider="local_gpu",
                    model=provider_model,
                    parameters={
                        "protocol_id": experiment["protocol_id"],
                        "prompt_sha256": hashlib.sha256(
                            prompt.encode("utf-8")
                        ).hexdigest(),
                        "aspect_ratio": experiment["aspect_ratio"],
                        **parameters,
                    },
                    seed=seed,
                    source_hashes=source_hashes,
                )
            except Exception as exc:
                attempt = _attempt_after_error(
                    tracker,
                    project_id=project_id,
                    shot_id=shot_id,
                    engine=(
                        "FLUX2_KLEIN_LOCAL"
                        if method == "native_flux2"
                        else "FLUX2_KLEIN_LORA_LOCAL"
                    ),
                    operation=(
                        "keyframe_generation"
                        if method == "native_flux2"
                        else "identity_inference"
                    ),
                )
                store.block_cell(
                    experiment_id,
                    cell_key,
                    state=(
                        "unknown"
                        if isinstance(exc, LoraTrainingStateUnknown)
                        else _failure_state(attempt)
                    ),
                    safe_error=safe_error_summary(exc),
                )
                return

            try:
                score, verdict = score_image(
                    str(result.published_path),
                    reference_paths[0],
                    character_id,
                )
                if verdict not in {"passed", "failed", "unknown"}:
                    raise ValueError("identity scorer returned an invalid verdict")
            except Exception:
                score, verdict = None, "unknown"
            latency_ms = max(0, round((time.monotonic() - started) * 1000))
            store.complete_cell(
                experiment_id,
                cell_key,
                prompt_id=str(result.prompt_id),
                output_path=str(record["object_path"]),
                output_sha256=str(record["sha256"]),
                latency_ms=latency_ms,
                identity_score=score,
                identity_verdict=verdict,
            )

    store.finish_succeeded(experiment_id)


class IdentityExperimentDispatcher:
    """One daemon runner guarded by the database's process-liveness lock."""

    def __init__(
        self,
        store: IdentityExperimentStore,
        handler: Callable[[IdentityExperimentStore, Mapping[str, Any]], None],
        *,
        poll_seconds: float = 0.5,
    ) -> None:
        self.store = store
        self.handler = handler
        self.poll_seconds = poll_seconds
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="identity-comparison-runner",
                daemon=True,
            )
            self._thread.start()

    def wake(self) -> None:
        self._wake.set()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def _run(self) -> None:
        lock = FileLock(str(self.store.runner_lock_path), timeout=0, mode=0o600)
        try:
            with lock.acquire(timeout=0):
                self.store.recover_running()
                while not self._stop.is_set():
                    experiment = self.store.claim_next()
                    if experiment is None:
                        self._wake.wait(self.poll_seconds)
                        self._wake.clear()
                        continue
                    self.handler(self.store, experiment)
        except FileLockTimeout:
            # Another web process owns the single runner. Its SQLite queue is
            # shared, so this process needs no duplicate worker thread.
            return
