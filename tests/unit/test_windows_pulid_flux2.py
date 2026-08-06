"""Offline adversarial tests for the quarantined PuLID-FLUX2 package."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "deploy" / "windows-pulid-flux2"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


verify = _load_module("windows_pulid_flux2_verify", PACKAGE / "verify.py")
CANDIDATE = json.loads((PACKAGE / "candidate.json").read_text())


def _spec(shape, *, dtype="F32"):
    size = 1
    for value in shape:
        size *= value
    return {"dtype": dtype, "shape": list(shape), "data_offsets": [0, size * 4]}


def _runtime(injection_map=None):
    return {
        "source_commit": "1" * 40,
        "architecture": {
            "hidden_size": 3072,
            "double_blocks": 5,
            "single_blocks": 20,
        },
        "runtime_namespaces": ["double_ca", "single_ca"],
        "strict_state_dict": True,
        "injection_map": injection_map
        or {"double_ca": [0, 2], "single_ca": [1, 7, 19]},
        "random_fallbacks": [],
    }


def _license():
    evidence = "Reviewed license record 2026-08-06."
    return {
        "license_state": "commercially_permissible_verified",
        "commercial_use_approved": True,
        "artifact_sha256": "a" * 64,
        "license_evidence": evidence,
        "license_evidence_sha256": hashlib.sha256(evidence.encode("utf-8")).hexdigest(),
    }


def _published_like_header():
    return {
        "__metadata__": {},
        "id_former.latents": _spec([1, 4, 4096]),
        "pulid_ca_double.0.to_q.weight": _spec([1024, 4096]),
        "pulid_ca_double.0.to_out.weight": _spec([4096, 1024]),
    }


def _write_tiny_safetensors(path: Path, raw_header: bytes, payload: bytes = b""):
    path.write_bytes(struct.pack("<Q", len(raw_header)) + raw_header + payload)


def test_manifest_pins_candidate_and_can_never_claim_production_ready():
    pins = CANDIDATE["pins"]
    assert CANDIDATE["status"]["usage"] == "evaluation_only"
    assert CANDIDATE["status"]["compatibility"] == "incompatible"
    assert CANDIDATE["status"]["license"] == "license_blocked"
    assert CANDIDATE["status"]["production_ready"] is False
    assert pins["flux2_source"] == {
        "repository": "black-forest-labs/flux2",
        "commit": "50fe5162777813d869182b139e83b10743caef15",
        "architecture": {
            "hidden_size": 3072,
            "double_blocks": 5,
            "single_blocks": 20,
        },
    }
    assert pins["node_source"]["commit"] == (
        "3a0a3f5f18260fc914f96a8c7f0f23c835e881cd"
    )
    model = pins["published_model"]
    assert model["revision"] == "550167db98d7169bfc83f9aa8225bd0da70f2d6b"
    assert {
        item["id"]: (item["expected_bytes"], item["sha256"])
        for item in model["artifacts"]
    } == {
        "v1": (
            1364389800,
            "5fe643927aa398f0ffefa4f9796675c2c7d116e78aa96b2416d4d0f54c63fc10",
        ),
        "v2": (
            1364389800,
            "d5d291cb054eb6eceb25e3b46eff8f05f7b58f8f19a89ec76ba730a6ba8935bb",
        ),
    }
    assert model["observed_header"]["tensor_count"] == 119
    assert model["observed_header"]["dtypes"] == {"F32": 119}
    assert model["observed_header"]["id_former.latents"] == [1, 4, 4096]
    assert model["observed_header"]["legacy_namespaces"] == {
        "pulid_ca_double": [0, 1, 2, 3, 4],
        "pulid_ca_single": [0, 1, 2, 3, 4, 5, 6],
    }
    gate = CANDIDATE["replacement_gate"]
    assert gate["state"] == "unresolved"
    assert "projection_tensor_shapes" in gate["unresolved"]
    assert "injection_tensor_contract" not in gate

    report = verify.candidate_report()
    assert report["production_ready"] is False
    assert report["candidate_status"]["production_ready"] is False


def test_manifest_refuses_a_ready_mutation(tmp_path):
    mutation = json.loads(json.dumps(CANDIDATE))
    mutation["status"]["production_ready"] = True
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(mutation))

    with pytest.raises(verify.CompatibilityError, match="cannot change production_ready"):
        verify.load_candidate(path)


def test_current_candidate_fails_closed_for_runtime_and_license():
    report = verify.audit_header(_published_like_header())

    assert report["static_header_contract_passed"] is False
    assert report["production_ready"] is False
    assert report["candidate_status"]["usage"] == "evaluation_only"
    assert report["candidate_status"]["compatibility"] == "incompatible"
    assert report["candidate_status"]["license"] == "license_blocked"
    assert {
        "runtime_strict_load_disabled",
        "runtime_random_fallback_declared",
        "runtime_injection_map_unresolved",
        "replacement_projection_contract_unresolved",
        "checkpoint_runtime_namespace_mismatch",
        "published_checkpoint_hidden_size_mismatch",
        "face_model_noncommercial",
    } <= set(report["blockers"])


def test_caller_supplied_replacement_claims_remain_evidence_blocked():
    runtime = _runtime()
    report = verify.audit_header(
        {"__metadata__": {}},
        runtime_audit=runtime,
        face_model_license=_license(),
    )

    assert report["static_header_contract_passed"] is False
    assert {
        "runtime_evidence_not_independently_verified",
        "license_evidence_not_independently_verified",
        "replacement_projection_contract_unresolved",
    } <= set(report["blockers"])
    assert report["production_ready"] is False
    assert report["candidate_status"]["production_ready"] is False
    assert report["candidate_status"]["benchmark_state"] == "ineligible"


def test_caller_cannot_replace_the_shipped_candidate_contract():
    forged = json.loads(json.dumps(CANDIDATE))
    forged["pins"]["node_source"] = _runtime()
    forged["pins"]["face_model"] = _license()

    with pytest.raises(TypeError, match="unexpected keyword argument"):
        verify.audit_header(
            {"__metadata__": {}},
            candidate=forged,
        )


def test_legacy_namespace_and_4096_injector_are_rejected():
    runtime = _runtime()
    header = _published_like_header()

    report = verify.audit_header(
        header,
        runtime_audit=runtime,
        face_model_license=_license(),
    )

    assert "legacy_injection_namespace" in report["blockers"]
    assert "published_checkpoint_hidden_size_mismatch" in report["blockers"]


def test_wrong_runtime_architecture_is_rejected():
    runtime = _runtime()
    runtime["architecture"]["hidden_size"] = 4096

    report = verify.audit_header(
        {"__metadata__": {}},
        runtime_audit=runtime,
        face_model_license=_license(),
    )

    assert "runtime_architecture_mismatch" in report["blockers"]


def test_runtime_injection_map_rejects_boolean_indices():
    runtime = _runtime({"double_ca": [False], "single_ca": [True]})

    report = verify.audit_header(
        {"__metadata__": {}},
        runtime_audit=runtime,
        face_model_license=_license(),
    )

    assert "runtime_injection_map_unresolved" in report["blockers"]
    assert report["static_header_contract_passed"] is False


def test_license_evidence_digest_must_bind_the_exact_record():
    runtime = _runtime()
    license_info = _license()
    license_info["license_evidence_sha256"] = "b" * 64

    report = verify.audit_header(
        {"__metadata__": {}},
        runtime_audit=runtime,
        face_model_license=license_info,
    )

    assert "face_model_license_unresolved" in report["blockers"]
    assert report["static_header_contract_passed"] is False


@pytest.mark.parametrize(
    ("license_info", "blocker"),
    [
        (
            {
                "license_state": "noncommercial_research_only",
                "commercial_use_approved": False,
            },
            "face_model_noncommercial",
        ),
        ({}, "face_model_license_unresolved"),
        (
            {
                "license_state": "commercially_permissible_verified",
                "commercial_use_approved": True,
                "artifact_sha256": "not-a-hash",
                "license_evidence": "claim only",
            },
            "face_model_license_unresolved",
        ),
    ],
)
def test_noncommercial_or_unresolved_face_license_fails(license_info, blocker):
    runtime = _runtime()
    report = verify.audit_header(
        {"__metadata__": {}},
        runtime_audit=runtime,
        face_model_license=license_info,
    )
    assert blocker in report["blockers"]


def test_random_fallback_declaration_fails_even_with_matching_header():
    runtime = _runtime()
    runtime["random_fallbacks"] = ["projection_on_dimension_mismatch"]
    report = verify.audit_header(
        {"__metadata__": {}},
        runtime_audit=runtime,
        face_model_license=_license(),
    )
    assert "runtime_random_fallback_declared" in report["blockers"]


def test_reader_reads_bounded_header_without_loading_payload(tmp_path):
    header = {
        "__metadata__": {"format": "pt"},
        "tiny": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]},
    }
    raw = json.dumps(header, separators=(",", ":")).encode()
    path = tmp_path / "tiny.safetensors"
    _write_tiny_safetensors(path, raw, b"DATA")

    assert verify.read_safetensors_header(path) == header


def test_reader_rejects_oversized_truncated_and_duplicate_headers(tmp_path):
    oversized = tmp_path / "oversized.safetensors"
    oversized.write_bytes(struct.pack("<Q", verify.MAX_HEADER_BYTES + 1))
    with pytest.raises(verify.CompatibilityError, match="unsafe"):
        verify.read_safetensors_header(oversized)

    truncated = tmp_path / "truncated.safetensors"
    truncated.write_bytes(struct.pack("<Q", 20) + b"{}")
    with pytest.raises(verify.CompatibilityError, match="truncated"):
        verify.read_safetensors_header(truncated)

    duplicate = tmp_path / "duplicate.safetensors"
    raw = b'{"x":{"dtype":"F32","shape":[0],"data_offsets":[0,0]},"x":{}}'
    _write_tiny_safetensors(duplicate, raw)
    with pytest.raises(verify.CompatibilityError, match="duplicate JSON key"):
        verify.read_safetensors_header(duplicate)


def test_reader_normalizes_pathological_json_integer_to_structured_failure(
    tmp_path, capsys
):
    checkpoint = tmp_path / "pathological-integer.safetensors"
    raw = (
        b'{"x":{"dtype":"F32","shape":['
        + b"9" * 5000
        + b'],"data_offsets":[0,0]}}'
    )
    _write_tiny_safetensors(checkpoint, raw)

    assert verify.main([str(checkpoint)]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["static_header_contract_passed"] is False
    assert report["blockers"] == ["unsafe_or_invalid_checkpoint_header"]


def test_reader_rejects_symlink_and_payload_span_lies(tmp_path):
    target = tmp_path / "target.safetensors"
    header = {
        "tiny": {"dtype": "F32", "shape": [2], "data_offsets": [0, 8]}
    }
    raw = json.dumps(header, separators=(",", ":")).encode()
    _write_tiny_safetensors(target, raw, b"only")
    link = tmp_path / "link.safetensors"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(verify.CompatibilityError, match="non-symlink"):
        verify.read_safetensors_header(link)
    with pytest.raises(verify.CompatibilityError, match="span exceeds"):
        verify.read_safetensors_header(target)


def test_package_contains_no_installer_runner_or_network_code():
    names = {path.name for path in PACKAGE.iterdir() if path.is_file()}
    assert names == {"README.md", "candidate.json", "verify.py"}
    source = (PACKAGE / "verify.py").read_text()
    assert "urllib" not in source
    assert "requests" not in source
    assert "subprocess" not in source
    assert "production_ready\": True" not in source
