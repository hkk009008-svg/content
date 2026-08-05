"""Fail-closed safe projection for the read-only FLUX.2 candidate."""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from domain.flux2_candidate import flux2_candidate_status


def _package(tmp_path, mutation=None):
    root = tmp_path / "deploy" / "windows-flux2-klein"
    root.mkdir(parents=True)
    tracked = root / "models.json"
    tracked.write_bytes(b'{"models": []}\n')
    payload = {
        "schema_version": 1,
        "capability": "image-flux2-klein",
        "candidate_state": "not_installed",
        "readiness": {
            "state": "not_installed",
            "startup_ready": False,
            "execution_proven": False,
            "benchmark_state": "not_run",
            "blocker_code": "candidate_artifacts_not_installed",
        },
        "license_review": {
            "state": "official_sources_selected_derivation_pending",
            "blocker_code": "qwen_official_shard_derivation_not_verified",
        },
        "bindings": {
            "models.json": hashlib.sha256(tracked.read_bytes()).hexdigest(),
        },
    }
    if mutation is not None:
        mutation(payload)
    (root / "candidate.json").write_text(json.dumps(payload), encoding="utf-8")
    return SimpleNamespace(project_root=tmp_path)


def test_exact_offline_candidate_projects_not_installed_without_selectability(tmp_path):
    status = flux2_candidate_status(_package(tmp_path))

    assert status.state == "not_installed"
    assert status.selectable is False
    assert status.benchmark_state == "not_run"
    assert status.blocker_code == "candidate_artifacts_not_installed"
    assert status.license_state == "official_sources_selected_derivation_pending"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.update(candidate_state="ready"),
        lambda payload: payload["readiness"].update(startup_ready=True),
        lambda payload: payload["readiness"].update(execution_proven=True),
        lambda payload: payload["readiness"].update(benchmark_state="passed"),
        lambda payload: payload["license_review"].update(state="approved"),
        lambda payload: payload["bindings"].update({"models.json": "0" * 64}),
    ],
)
def test_candidate_tuple_or_binding_falsification_projects_blocked(tmp_path, mutation):
    status = flux2_candidate_status(_package(tmp_path, mutation))

    assert status.state == "blocked"
    assert status.selectable is False
    assert status.blocker_code == "candidate_contract_unavailable"
    assert "unavailable or failed" in status.reason
