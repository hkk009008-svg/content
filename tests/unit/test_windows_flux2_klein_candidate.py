"""Offline contract tests for the isolated FLUX.2 Klein candidate."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import struct
import sys
from collections import OrderedDict
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "deploy" / "windows-flux2-klein"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


workflow = _load_module("windows_flux2_klein_workflow", PACKAGE / "workflow.py")
preflight = _load_module("windows_flux2_klein_preflight", PACKAGE / "preflight.py")
merge_qwen = _load_module(
    "windows_flux2_klein_merge_qwen", PACKAGE / "merge_qwen_encoder.py"
)


def _object_info():
    return json.loads((PACKAGE / "fixtures" / "object_info.json").read_text())


def _live_combo_object_info():
    info = _object_info()
    for raw in info.values():
        input_info = raw.get("input", {})
        for location in ("required", "optional"):
            for name, spec in input_info.get(location, {}).items():
                if (
                    isinstance(spec, list)
                    and len(spec) == 1
                    and isinstance(spec[0], list)
                ):
                    input_info[location][name] = [
                        "COMBO",
                        {"multiselect": False, "options": spec[0]},
                    ]
    return info


def _graph(*, references=("reference-1.png", "reference-2.png")):
    return workflow.build_flux2_klein_workflow(
        prompt="Keep the person from image1 and the wardrobe from image2.",
        reference_images=list(references),
        seed=424242,
        aspect_ratio="16:9",
    )


def test_candidate_manifest_stays_not_installed_and_not_execution_proven():
    candidate = json.loads((PACKAGE / "candidate.json").read_text())

    assert candidate["capability"] == "image-flux2-klein"
    assert candidate["candidate_state"] == "not_installed"
    assert candidate["readiness"] == {
        "state": "not_installed",
        "startup_ready": False,
        "execution_proven": False,
        "benchmark_state": "not_run",
        "blocker_code": "candidate_artifacts_not_installed",
    }
    assert candidate["operator_state_contract"]["states"] == [
        "not_installed",
        "needs_benchmark",
        "ready",
        "blocked",
        "offline",
    ]
    assert "legacy_migration" not in candidate
    assert candidate["license_review"] == {
        "state": "official_sources_selected_derivation_pending",
        "blocker_code": "qwen_official_shard_derivation_not_verified",
    }
    assert set(candidate["bindings"]) == {
        "Benchmark-Candidate.ps1",
        "Install-Candidate.ps1",
        "PROVENANCE.md",
        "Probe-Candidate.ps1",
        "README.md",
        "install.py",
        "merge_qwen_encoder.py",
        "models.json",
        "preflight.py",
        "revisions.json",
        "runtime.py",
        "workflow.py",
        "fixtures/object_info.json",
        "fixtures/reference.json",
        "fixtures/reference.png.b64",
    }


def test_model_manifest_has_exact_reviewed_revisions_sizes_and_hashes():
    manifest = json.loads((PACKAGE / "models.json").read_text())
    artifacts = {item["id"]: item for item in manifest["artifacts"]}

    assert {
        key: (item["expected_bytes"], item["sha256"], item["destination"])
        for key, item in artifacts.items()
    } == preflight.EXPECTED_ARTIFACTS
    assert artifacts["flux2-klein-4b-distilled-fp8"]["source"]["revision"] == (
        "5b4408e59397a4a37ccb46afe426d8ed86379441"
    )
    assert artifacts["qwen3-4b-text-encoder"]["source"]["revision"] == (
        "5e67da950fce4a097bc150c22958a05716994cea"
    )
    assert artifacts["flux2-vae"]["source"]["revision"] == (
        "5e67da950fce4a097bc150c22958a05716994cea"
    )
    assert artifacts["flux2-vae"]["source"]["path"] == (
        "vae/diffusion_pytorch_model.safetensors"
    )
    assert artifacts["flux2-vae"]["license"] == {
        "source_declaration": "Apache-2.0",
        "upstream_provenance": (
            "Direct artifact from the pinned Black Forest Labs FLUX.2 Klein 4B "
            "Apache repository."
        ),
        "review_state": "official_source_and_static_compatibility_verified",
        "review_note": (
            "The official BF16 file has the same 251 tensor names and shapes as "
            "the prior Comfy F32 artifact; every F32 tensor rounds to the official "
            "BF16 tensor bit-for-bit. Pinned ComfyUI accepts BF16 safetensors and "
            "detects the architecture from these keys. Runtime execution remains "
            "unproven."
        ),
    }

    qwen = artifacts["qwen3-4b-text-encoder"]
    assert qwen["sha256"] == (
        "e37269b7ca1301ad72a92627ce95432ab5aad5f89143a06055886aad3419d12f"
    )
    assert qwen["sha256"] != (
        "6c671498573ac2f7a5501502ccce8d2b08ea6ca2f661c458e708f36b36edfc5a"
    )
    assert qwen["source"]["type"] == "deterministic_official_shard_merge"
    assert {
        item["path"]: (item["expected_bytes"], item["sha256"])
        for item in [qwen["source"]["index"], *qwen["source"]["inputs"]]
    } == preflight.EXPECTED_QWEN_SOURCE_FILES
    assert qwen["source"]["derivation"] == {
        "script": "merge_qwen_encoder.py",
        "tensor_order": "lexicographic_tensor_name",
        "metadata": None,
        "expected_tensor_count": 398,
        "expected_header_bytes": 45848,
        "execution_state": "not_executed",
    }
    assert qwen["license"]["source_declaration"] == "Apache-2.0"
    assert qwen["license"]["review_state"] == (
        "official_source_derivation_not_execution_proven"
    )


def test_builder_is_flat_deterministic_four_step_and_multi_reference():
    graph = _graph()

    assert graph == _graph()
    assert all(set(node) == {"class_type", "inputs"} for node in graph.values())
    assert graph["6"]["inputs"]["noise_seed"] == 424242
    assert graph["8"]["inputs"] == {"steps": 4, "width": 1280, "height": 720}
    assert graph["9"]["inputs"] == {"width": 1280, "height": 720, "batch_size": 1}
    assert graph["20"]["inputs"]["cfg"] == 1.0
    assert graph["103"]["inputs"]["conditioning"] == ["4", 0]
    assert graph["104"]["inputs"]["conditioning"] == ["5", 0]
    assert graph["113"]["inputs"]["conditioning"] == ["103", 0]
    assert graph["114"]["inputs"]["conditioning"] == ["104", 0]
    assert graph["20"]["inputs"]["positive"] == ["113", 0]
    assert graph["20"]["inputs"]["negative"] == ["114", 0]


@pytest.mark.parametrize("reference_count", [1, 2, 10])
def test_builder_and_static_schema_cover_candidate_reference_bounds(reference_count):
    references = tuple(
        f"reference-{index}.png" for index in range(1, reference_count + 1)
    )
    graph = _graph(references=references)
    result = preflight.validate_workflow(graph, _object_info())

    counts = {
        class_name: sum(
            node["class_type"] == class_name for node in graph.values()
        )
        for class_name in (
            "LoadImage",
            "ImageScaleToTotalPixels",
            "VAEEncode",
            "ReferenceLatent",
        )
    }
    assert result["reference_count"] == reference_count
    assert result["node_count"] == 13 + reference_count * 5
    assert counts == {
        "LoadImage": reference_count,
        "ImageScaleToTotalPixels": reference_count,
        "VAEEncode": reference_count,
        "ReferenceLatent": reference_count * 2,
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"reference_images": []},
        {"reference_images": [f"r-{index}.png" for index in range(11)]},
        {"reference_images": ["../escape.png"]},
        {"reference_images": ["same.png", "same.png"]},
        {"seed": True},
        {"seed": -1},
        {"aspect_ratio": "freeform"},
        {"prompt": ""},
    ],
)
def test_builder_rejects_unbounded_or_nondeterministic_inputs(overrides):
    values = {
        "prompt": "candidate",
        "reference_images": ["reference-1.png"],
        "seed": 1,
        "aspect_ratio": "1:1",
    }
    values.update(overrides)

    with pytest.raises(ValueError):
        workflow.build_flux2_klein_workflow(**values)


def test_static_object_info_and_workflow_preflight_pass_without_execution():
    result = preflight.validate_workflow(_graph(), _object_info())

    assert result == {
        "status": "static_preflight_passed",
        "node_count": 23,
        "reference_count": 2,
        "execution_proven": False,
    }


def test_live_combo_object_info_and_workflow_preflight_pass_without_execution():
    result = preflight.validate_workflow(_graph(), _live_combo_object_info())

    assert result == {
        "status": "static_preflight_passed",
        "node_count": 23,
        "reference_count": 2,
        "execution_proven": False,
    }


def test_mixed_live_and_legacy_metadata_combo_schema_passes():
    info = _live_combo_object_info()
    info["UNETLoader"]["input"]["required"]["weight_dtype"] = [
        ["default", "fp8_e4m3fn", "fp8_e4m3fn_fast", "fp8_e5m2"],
        {"advanced": True},
    ]
    info["CLIPLoader"]["input"]["optional"]["device"] = [
        ["default", "cpu"],
        {"advanced": True},
    ]
    info["LoadImage"]["input"]["required"]["image"] = [
        [f"reference-{index}.png" for index in range(1, 11)],
        {"image_upload": True},
    ]

    result = preflight.validate_workflow(_graph(), info)

    assert result["status"] == "static_preflight_passed"
    assert result["reference_count"] == 2


def test_preupload_empty_load_image_combo_is_structurally_valid():
    info = _object_info()
    info["LoadImage"]["input"]["required"]["image"] = [
        [],
        {"image_upload": True},
    ]

    result = preflight.validate_workflow(
        _graph(references=("content-flux2-klein/run-reference-01.png",)),
        info,
    )

    assert result["status"] == "static_preflight_passed"
    assert result["reference_count"] == 1


@pytest.mark.parametrize(
    ("class_name", "input_name", "required_choice", "spec"),
    [
        (
            "KSamplerSelect",
            "sampler_name",
            "euler",
            ["COMBO", {"multiselect": False, "options": []}],
        ),
        (
            "UNETLoader",
            "unet_name",
            "flux-2-klein-4b-fp8.safetensors",
            [[]],
        ),
    ],
)
def test_empty_required_combo_does_not_satisfy_pinned_choice(
    class_name, input_name, required_choice, spec
):
    info = _object_info()
    info[class_name]["input"]["required"][input_name] = spec

    with pytest.raises(
        preflight.CandidateContractError,
        match=rf"{required_choice!r} unavailable",
    ):
        preflight.validate_object_info(info)


def test_live_combo_object_info_rejects_missing_required_choice():
    info = _live_combo_object_info()
    info["KSamplerSelect"]["input"]["required"]["sampler_name"][1][
        "options"
    ] = ["dpmpp_2m"]

    with pytest.raises(preflight.CandidateContractError, match="'euler' unavailable"):
        preflight.validate_object_info(info)


@pytest.mark.parametrize(
    "spec",
    [
        ["COMBO", {"multiselect": False, "options": "euler"}],
        ["COMBO", {"multiselect": True, "options": ["euler"]}],
        ["COMBO", {"multiselect": False, "options": ["euler"], "unsafe": True}],
        ["COMBO", {"multiselect": False, "options": [{"value": "euler"}]}],
        ["COMBO", {"multiselect": False, "options": ["euler", "euler"]}],
        [["euler"], {"multiselect": True}],
    ],
)
def test_live_combo_object_info_rejects_malformed_or_unsafe_schema(spec):
    info = _live_combo_object_info()
    info["KSamplerSelect"]["input"]["required"]["sampler_name"] = spec

    with pytest.raises(
        preflight.CandidateContractError,
        match="KSamplerSelect.sampler_name: required COMBO, got missing",
    ):
        preflight.validate_object_info(info)


@pytest.mark.parametrize(
    "mutation, message",
    [
        (lambda info: info.pop("ReferenceLatent"), "missing core class"),
        (
            lambda info: info["ReferenceLatent"]["input"]["optional"].pop("latent"),
            "ReferenceLatent.latent",
        ),
        (
            lambda info: info["UNETLoader"]["input"]["required"]["unet_name"][0].clear(),
            "unavailable",
        ),
        (
            lambda info: info["Flux2Scheduler"].update(output=["LATENT"]),
            "output contract drifted",
        ),
    ],
)
def test_object_info_schema_falsifications_fail_closed(mutation, message):
    info = _object_info()
    mutation(info)

    with pytest.raises(preflight.CandidateContractError, match=message):
        preflight.validate_object_info(info)


@pytest.mark.parametrize(
    "mutation, message",
    [
        (lambda graph: graph["8"]["inputs"].update(steps=5), "four steps"),
        (lambda graph: graph["20"]["inputs"].update(cfg=2.0), "CFG"),
        (lambda graph: graph["21"]["inputs"].update(noise=["22", 0]), "type mismatch"),
        (lambda graph: graph["1"].update(class_type="UntrustedLoader"), "unapproved class"),
        (lambda graph: graph.pop("114"), "missing origin|ReferenceLatent"),
        (
            lambda graph: graph["113"]["inputs"].update(conditioning=["4", 0]),
            "positive chain drifted",
        ),
        (
            lambda graph: graph["20"]["inputs"].update(negative=["104", 0]),
            "guider reference-chain binding drifted",
        ),
        (
            lambda graph: graph["113"]["inputs"].update(latent=["102", 0]),
            "positive chain drifted",
        ),
        (
            lambda graph: (
                graph["113"]["inputs"].update(conditioning=["104", 0]),
                graph["114"]["inputs"].update(conditioning=["103", 0]),
            ),
            "positive chain drifted|negative chain drifted",
        ),
        (
            lambda graph: graph["103"]["inputs"].update(conditioning=["113", 0]),
            "dependency cycle",
        ),
    ],
)
def test_workflow_falsifications_fail_closed(mutation, message):
    graph = copy.deepcopy(_graph())
    mutation(graph)

    with pytest.raises(preflight.CandidateContractError, match=message):
        preflight.validate_workflow(graph, _object_info())


def test_load_image_accepts_safe_uploaded_subfolder_name_absent_from_enumeration():
    graph = _graph(references=("content-flux2-klein/run-reference-01.png",))

    result = preflight.validate_workflow(graph, _object_info())

    assert result["status"] == "static_preflight_passed"
    assert result["reference_count"] == 1


def test_non_load_image_combo_still_rejects_value_absent_from_enumeration():
    graph = copy.deepcopy(_graph())
    graph["1"]["inputs"]["weight_dtype"] = "not-installed"

    with pytest.raises(
        preflight.CandidateContractError,
        match="node 1.weight_dtype: value is not installed/allowed",
    ):
        preflight.validate_workflow(graph, _object_info())


@pytest.mark.parametrize(
    "unsafe_name",
    [
        "../escape.png",
        "content-flux2-klein/../escape.png",
        "/absolute.png",
        "content-flux2-klein\\escape.png",
        "content-flux2-klein//escape.png",
        "content-flux2-klein/./escape.png",
    ],
)
def test_load_image_rejects_unsafe_relative_filename(unsafe_name):
    graph = copy.deepcopy(_graph(references=("reference-1.png",)))
    graph["100"]["inputs"]["image"] = unsafe_name

    with pytest.raises(
        preflight.CandidateContractError,
        match="unsafe relative POSIX filename",
    ):
        preflight.validate_workflow(graph, _object_info())


def test_package_bindings_and_static_contract_validate_without_ready_claim():
    result = preflight.validate_package()

    assert result["status"] == "candidate_contract_valid"
    assert result["readiness_state"] == "not_installed"
    assert result["execution_proven"] is False
    assert result["artifact_count"] == 3
    assert result["core_class_count"] == 17
    assert result["validated_reference_counts"] == [1, 2, 10]


def test_package_binding_tamper_is_rejected(tmp_path):
    candidate_copy = tmp_path / "candidate"
    shutil.copytree(PACKAGE, candidate_copy)
    with (candidate_copy / "workflow.py").open("a", encoding="utf-8") as handle:
        handle.write("\n# drift\n")

    with pytest.raises(preflight.CandidateContractError, match="binding mismatch"):
        preflight.validate_package(candidate_copy)


@pytest.mark.parametrize(
    "old, new, message",
    [
        ("DISTILLED_STEPS = 4", "DISTILLED_STEPS = 5", "four steps"),
        (
            '"upscale_method": "nearest-exact"',
            '"upscale_method": "bilinear"',
            "scale contract drifted",
        ),
    ],
)
def test_package_rejects_bound_builder_graph_drift(tmp_path, old, new, message):
    candidate_copy = tmp_path / "candidate"
    shutil.copytree(PACKAGE, candidate_copy)
    workflow_path = candidate_copy / "workflow.py"
    workflow_source = workflow_path.read_text(encoding="utf-8")
    assert old in workflow_source
    workflow_path.write_text(workflow_source.replace(old, new, 1), encoding="utf-8")

    candidate_path = candidate_copy / "candidate.json"
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate["bindings"]["workflow.py"] = hashlib.sha256(
        workflow_path.read_bytes()
    ).hexdigest()
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")

    with pytest.raises(preflight.CandidateContractError, match=message):
        preflight.validate_package(candidate_copy)


@pytest.mark.parametrize(
    "mutation, message",
    [
        (
            lambda models: models["artifacts"][1]["source"]["inputs"][0].update(
                sha256="0" * 64
            ),
            "Qwen official-source file pins drifted",
        ),
        (
            lambda models: models["artifacts"][2]["source"].update(
                path="split_files/vae/flux2-vae.safetensors"
            ),
            "direct official model source path drifted",
        ),
        (
            lambda models: models["artifacts"][1]["source"]["derivation"].update(
                execution_state="verified_without_running"
            ),
            "Qwen official-source derivation truth drifted",
        ),
    ],
)
def test_package_rejects_provenance_contract_drift(tmp_path, mutation, message):
    candidate_copy = tmp_path / "candidate"
    shutil.copytree(PACKAGE, candidate_copy)
    models_path = candidate_copy / "models.json"
    models = json.loads(models_path.read_text(encoding="utf-8"))
    mutation(models)
    models_path.write_text(json.dumps(models), encoding="utf-8")

    candidate_path = candidate_copy / "candidate.json"
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate["bindings"]["models.json"] = hashlib.sha256(
        models_path.read_bytes()
    ).hexdigest()
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")

    with pytest.raises(preflight.CandidateContractError, match=message):
        preflight.validate_package(candidate_copy)


def _encode_test_safetensors(tensors, *, metadata=True):
    header = OrderedDict()
    if metadata:
        header["__metadata__"] = {"format": "pt"}
    payload = bytearray()
    for name in sorted(tensors):
        dtype, shape, value = tensors[name]
        start = len(payload)
        payload.extend(value)
        header[name] = OrderedDict(
            (
                ("dtype", dtype),
                ("shape", shape),
                ("data_offsets", [start, len(payload)]),
            )
        )
    encoded = json.dumps(
        header, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    encoded += b" " * (-len(encoded) % 8)
    return struct.pack("<Q", len(encoded)) + encoded + bytes(payload), len(encoded)


def _synthetic_qwen_contract(tmp_path):
    source_root = tmp_path / "official"
    text_encoder = source_root / "text_encoder"
    text_encoder.mkdir(parents=True)
    shard_tensors = [
        {
            "model.embed_tokens.weight": (
                "F32", [2], struct.pack("<2f", 1.25, -2.5)
            ),
            "model.layers.1.self_attn.q_proj.weight": (
                "I64", [1], struct.pack("<q", 17)
            ),
        },
        {
            "model.layers.0.self_attn.q_proj.weight": (
                "F32", [1], struct.pack("<f", 3.5)
            ),
        },
    ]
    shard_paths = []
    for index, tensors in enumerate(shard_tensors, start=1):
        path = text_encoder / f"model-0000{index}-of-00002.safetensors"
        value, _ = _encode_test_safetensors(tensors)
        path.write_bytes(value)
        shard_paths.append(path)

    weight_map = {
        name: path.name
        for path, tensors in zip(shard_paths, shard_tensors, strict=True)
        for name in tensors
    }
    index_path = text_encoder / "model.safetensors.index.json"
    index_path.write_text(json.dumps({"weight_map": weight_map}), encoding="utf-8")
    expected_bytes, expected_header_size = _encode_test_safetensors(
        {name: value for tensors in shard_tensors for name, value in tensors.items()},
        metadata=False,
    )

    def source_record(path):
        return {
            "path": str(path.relative_to(source_root)).replace("\\", "/"),
            "expected_bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    manifest = {
        "artifacts": [
            {
                "id": "qwen3-4b-text-encoder",
                "source": {
                    "type": "deterministic_official_shard_merge",
                    "index": source_record(index_path),
                    "inputs": [source_record(path) for path in shard_paths],
                    "derivation": {
                        "tensor_order": "lexicographic_tensor_name",
                        "metadata": None,
                        "expected_tensor_count": 3,
                        "expected_header_bytes": expected_header_size,
                    },
                },
                "expected_bytes": len(expected_bytes),
                "sha256": hashlib.sha256(expected_bytes).hexdigest(),
            }
        ]
    }
    manifest_path = tmp_path / "models.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path, source_root, expected_bytes, shard_paths


def test_official_qwen_shards_merge_to_exact_manifest_output(tmp_path):
    manifest, source_root, expected_bytes, _ = _synthetic_qwen_contract(tmp_path)
    output = tmp_path / "qwen_3_4b.safetensors"

    result = merge_qwen.merge_from_manifest(manifest, source_root, output)

    assert output.read_bytes() == expected_bytes
    header_size = struct.unpack("<Q", expected_bytes[:8])[0]
    header = json.loads(expected_bytes[8 : 8 + header_size])
    assert "__metadata__" not in header
    assert result == {
        "status": "official_qwen_derivation_verified",
        "output_bytes": len(expected_bytes),
        "output_sha256": hashlib.sha256(expected_bytes).hexdigest(),
        "tensor_count": 3,
    }


def test_official_qwen_merge_rejects_tampered_shard_without_output(tmp_path):
    manifest, source_root, _, shard_paths = _synthetic_qwen_contract(tmp_path)
    output = tmp_path / "qwen_3_4b.safetensors"
    value = shard_paths[0].read_bytes()
    shard_paths[0].write_bytes(value[:-1] + bytes([value[-1] ^ 1]))

    with pytest.raises(merge_qwen.MergeContractError, match="SHA-256 mismatch"):
        merge_qwen.merge_from_manifest(manifest, source_root, output)

    assert not output.exists()
    assert not list(tmp_path.glob(".*.partial"))


def test_official_qwen_merge_rejects_wrong_output_gate_without_output(tmp_path):
    manifest, source_root, expected_bytes, _ = _synthetic_qwen_contract(tmp_path)
    output = tmp_path / "qwen_3_4b.safetensors"
    contract = json.loads(manifest.read_text(encoding="utf-8"))
    contract["artifacts"][0]["sha256"] = "0" * 64
    manifest.write_text(json.dumps(contract), encoding="utf-8")

    actual_hash = hashlib.sha256(expected_bytes).hexdigest()
    with pytest.raises(merge_qwen.MergeContractError, match="output SHA-256") as exc:
        merge_qwen.merge_from_manifest(manifest, source_root, output)

    assert f"expected {'0' * 64}, got {actual_hash}" in str(exc.value)
    assert not output.exists()


def test_official_qwen_merge_never_overwrites_existing_output(tmp_path):
    manifest, source_root, _, _ = _synthetic_qwen_contract(tmp_path)
    output = tmp_path / "qwen_3_4b.safetensors"
    output.write_bytes(b"operator-owned")

    with pytest.raises(merge_qwen.MergeContractError, match="refusing to overwrite"):
        merge_qwen.merge_from_manifest(manifest, source_root, output)

    assert output.read_bytes() == b"operator-owned"


def test_official_qwen_merge_rejects_index_orphan_even_when_rehashed(tmp_path):
    manifest, source_root, _, _ = _synthetic_qwen_contract(tmp_path)
    output = tmp_path / "qwen_3_4b.safetensors"
    index_path = source_root / "text_encoder" / "model.safetensors.index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["weight_map"].pop("model.layers.1.self_attn.q_proj.weight")
    index_path.write_text(json.dumps(index), encoding="utf-8")

    contract = json.loads(manifest.read_text(encoding="utf-8"))
    index_record = contract["artifacts"][0]["source"]["index"]
    index_record["expected_bytes"] = index_path.stat().st_size
    index_record["sha256"] = hashlib.sha256(index_path.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(contract), encoding="utf-8")

    with pytest.raises(
        merge_qwen.MergeContractError, match="index and shard tensor sets differ"
    ):
        merge_qwen.merge_from_manifest(manifest, source_root, output)

    assert not output.exists()
