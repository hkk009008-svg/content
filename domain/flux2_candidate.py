"""Safe, read-only projection of the tracked FLUX.2 Klein candidate package."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from config.settings import settings


_CANDIDATE_PATH = Path("deploy/windows-flux2-klein/candidate.json")
_HEX_RE = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class Flux2CandidateStatus:
    capability: str
    label: str
    state: str
    selectable: bool
    startup_ready: bool
    execution_proven: bool
    benchmark_state: str
    blocker_code: str
    license_state: str
    license_blocker_code: str
    reason: str

    def public_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def _blocked(reason: str, blocker_code: str = "candidate_contract_unavailable") -> Flux2CandidateStatus:
    return Flux2CandidateStatus(
        capability="image-flux2-klein",
        label="Local FLUX.2 Klein 4B",
        state="blocked",
        selectable=False,
        startup_ready=False,
        execution_proven=False,
        benchmark_state="unknown",
        blocker_code=blocker_code,
        license_state="review_required",
        license_blocker_code="candidate_contract_unavailable",
        reason=reason,
    )


def _verify_bindings(package_root: Path, bindings: object) -> None:
    if not isinstance(bindings, Mapping) or not bindings:
        raise ValueError("candidate bindings are missing")
    root = package_root.resolve()
    for raw_path, expected in bindings.items():
        if (
            not isinstance(raw_path, str)
            or not isinstance(expected, str)
            or not _HEX_RE.fullmatch(expected)
        ):
            raise ValueError("candidate binding is invalid")
        path = (root / raw_path).resolve()
        if root not in path.parents or not path.is_file():
            raise ValueError("candidate binding escapes or is unavailable")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError("candidate binding hash mismatch")


def flux2_candidate_status(settings_obj: object = settings) -> Flux2CandidateStatus:
    project_root = Path(
        getattr(settings_obj, "project_root", Path(__file__).resolve().parent.parent)
    )
    path = project_root / _CANDIDATE_PATH
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(payload, Mapping)
            or payload.get("schema_version") != 1
            or payload.get("capability") != "image-flux2-klein"
        ):
            raise ValueError("candidate schema is invalid")
        readiness = payload.get("readiness")
        license_review = payload.get("license_review")
        if not isinstance(readiness, Mapping) or not isinstance(license_review, Mapping):
            raise ValueError("candidate readiness is invalid")
        state = payload.get("candidate_state")
        readiness_state = readiness.get("state")
        _verify_bindings(path.parent, payload.get("bindings"))
        startup_ready = readiness.get("startup_ready")
        execution_proven = readiness.get("execution_proven")
        if not isinstance(startup_ready, bool) or not isinstance(execution_proven, bool):
            raise ValueError("candidate readiness booleans are invalid")
        benchmark_state = readiness.get("benchmark_state")
        blocker_code = readiness.get("blocker_code")
        license_state = license_review.get("state")
        license_blocker = license_review.get("blocker_code")
        if not all(
            isinstance(value, str) and value
            for value in (
                benchmark_state,
                blocker_code,
                license_state,
                license_blocker,
            )
        ):
            raise ValueError("candidate blocker projection is invalid")
        # The current candidate file is not self-hashed, so accept only its
        # exact reviewed offline tuple. Any future state transition requires a
        # schema/validator update; editing strings cannot paint a false Ready.
        if (
            state != "not_installed"
            or readiness_state != "not_installed"
            or startup_ready is not False
            or execution_proven is not False
            or benchmark_state != "not_run"
            or blocker_code != "candidate_artifacts_not_installed"
            or license_state != "official_sources_selected_derivation_pending"
            or license_blocker != "qwen_official_shard_derivation_not_verified"
        ):
            raise ValueError("candidate offline tuple is invalid")
    except (OSError, json.JSONDecodeError, ValueError):
        return _blocked(
            "FLUX.2 candidate metadata is unavailable or failed its hash bindings."
        )

    reason = (
        "Candidate artifacts are not installed; the benchmark has not run, "
        "and the pinned official Qwen shard derivation has not been executed."
    )
    # Read-only by design. Even a future candidate record that says ready does
    # not add a project setting or selection path without a reviewed rollout.
    return Flux2CandidateStatus(
        capability="image-flux2-klein",
        label="Local FLUX.2 Klein 4B",
        state=str(state),
        selectable=False,
        startup_ready=startup_ready,
        execution_proven=execution_proven,
        benchmark_state=benchmark_state,
        blocker_code=blocker_code,
        license_state=license_state,
        license_blocker_code=license_blocker,
        reason=reason,
    )
