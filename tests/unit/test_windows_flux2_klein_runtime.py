"""Offline falsification tests for the FLUX.2 installer/probe/benchmark tools."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "deploy" / "windows-flux2-klein"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


installer = _load_module("windows_flux2_klein_test_installer", PACKAGE / "install.py")
runtime = _load_module("windows_flux2_klein_test_runtime", PACKAGE / "runtime.py")


def _record(payload: bytes, *, path="artifact.bin"):
    return {
        "path": path,
        "url": (
            "https://huggingface.co/black-forest-labs/test/resolve/"
            + "a" * 40
            + f"/{path}?download=true"
        ),
        "expected_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


class _Response(io.BytesIO):
    def __init__(self, payload: bytes, *, status=200, headers=None):
        super().__init__(payload)
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def test_fixed_fixture_has_exact_contract_and_decodes():
    payload, contract = runtime.load_fixed_fixture()

    assert len(payload) == 173
    assert hashlib.sha256(payload).hexdigest() == (
        "cd91b55001d19f88023fe80098c6919baeb99a62d4a65ba2d2339e9ca217bca8"
    )
    assert contract["decoded"] == {
        "format": "PNG",
        "mode": "RGB",
        "width": 64,
        "height": 64,
    }


def test_verified_download_publishes_only_after_full_hash(tmp_path):
    payload = b"pinned-official-payload"
    destination = tmp_path / "cache" / "artifact.bin"
    calls = []

    def opener(request, *, timeout):
        calls.append((request.full_url, dict(request.header_items()), timeout))
        return _Response(payload)

    result = installer.download_verified(_record(payload), destination, opener=opener)

    assert result["status"] == "downloaded"
    assert destination.read_bytes() == payload
    assert not destination.with_name("artifact.bin.partial").exists()
    assert calls[0][0].startswith("https://huggingface.co/black-forest-labs/")


def test_verified_download_resumes_owned_partial_with_range(tmp_path):
    payload = b"0123456789abcdef"
    destination = tmp_path / "artifact.bin"
    partial = tmp_path / "artifact.bin.partial"
    partial.write_bytes(payload[:5])

    def opener(request, *, timeout):
        assert request.get_header("Range") == "bytes=5-"
        return _Response(
            payload[5:], status=206, headers={"Content-Range": "bytes 5-15/16"}
        )

    installer.download_verified(_record(payload), destination, opener=opener)

    assert destination.read_bytes() == payload
    assert not partial.exists()


def test_verified_download_hash_failure_never_publishes(tmp_path):
    destination = tmp_path / "artifact.bin"

    with pytest.raises(installer.InstallContractError, match="verification"):
        installer.download_verified(
            _record(b"expected"),
            destination,
            opener=lambda *args, **kwargs: _Response(b"tampered"),
        )

    assert not destination.exists()


def test_direct_install_sources_inherit_top_level_exact_hash_gates():
    manifest = json.loads((PACKAGE / "models.json").read_text())
    direct = [
        artifact
        for artifact in manifest["artifacts"]
        if artifact["source"].get("type") != "deterministic_official_shard_merge"
    ]

    assert len(direct) == 2
    for artifact in direct:
        record = installer._source_records(artifact)[0]
        assert record["expected_bytes"] == artifact["expected_bytes"]
        assert record["sha256"] == artifact["sha256"]
        assert record["url"] == artifact["source"]["url"]


def _synthetic_install_package(tmp_path):
    package = tmp_path / "package"
    package.mkdir()
    direct_a = b"model-a"
    index = b'{"weight_map":{}}'
    shard = b"qwen-shard"
    qwen = b"derived-qwen"
    direct_b = b"vae-b"
    artifacts = [
        {
            "id": "flux2-klein-4b-distilled-fp8",
            **_record(direct_a, path="model-a.safetensors"),
            "source": _record(direct_a, path="model-a.safetensors"),
            "destination": "diffusion_models/model-a.safetensors",
        },
        {
            "id": "qwen3-4b-text-encoder",
            "expected_bytes": len(qwen),
            "sha256": hashlib.sha256(qwen).hexdigest(),
            "destination": "text_encoders/qwen.safetensors",
            "source": {
                "type": "deterministic_official_shard_merge",
                "index": _record(index, path="text_encoder/model.index.json"),
                "inputs": [_record(shard, path="text_encoder/model-1.safetensors")],
                "derivation": {"expected_tensor_count": 1},
            },
        },
        {
            "id": "flux2-vae",
            **_record(direct_b, path="vae.safetensors"),
            "source": _record(direct_b, path="vae.safetensors"),
            "destination": "vae/vae.safetensors",
        },
    ]
    (package / "models.json").write_text(json.dumps({"artifacts": artifacts}))
    (package / "candidate.json").write_text(json.dumps({"bindings": {}}))
    (package / "workflow.py").write_text("# synthetic workflow contract\n")
    payloads = {
        "model-a.safetensors": direct_a,
        "text_encoder/model.index.json": index,
        "text_encoder/model-1.safetensors": shard,
        "vae.safetensors": direct_b,
    }
    return package, artifacts, payloads, qwen


def _comfy_root(tmp_path):
    root = tmp_path / "ComfyUI"
    (root / "models").mkdir(parents=True)
    (root / "main.py").write_text("# synthetic checkout\n")
    return root


def test_installer_refuses_mismatched_existing_model_before_network(tmp_path):
    package, artifacts, _, _ = _synthetic_install_package(tmp_path)
    comfy = _comfy_root(tmp_path)
    target = comfy / "models" / artifacts[0]["destination"]
    target.parent.mkdir(parents=True)
    target.write_bytes(b"wrong")
    calls = []

    with pytest.raises(installer.InstallContractError, match="verification"):
        installer.install_candidate(
            comfy_root=comfy,
            state_root=tmp_path / "state",
            package_root=package,
            package_validator=lambda root: {"status": "candidate_contract_valid"},
            downloader=lambda record, path: calls.append(path),
        )

    assert calls == []
    assert target.read_bytes() == b"wrong"


def test_installer_downloads_derives_and_publishes_exact_synthetic_set(tmp_path):
    package, artifacts, payloads, qwen = _synthetic_install_package(tmp_path)
    comfy = _comfy_root(tmp_path)

    def downloader(record, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payloads[record["path"]])
        return {"status": "downloaded"}

    def merge_tool(manifest_path, source_root, output):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(qwen)
        return {
            "status": "official_qwen_derivation_verified",
            "output_bytes": len(qwen),
            "output_sha256": hashlib.sha256(qwen).hexdigest(),
            "tensor_count": 1,
        }

    evidence = installer.install_candidate(
        comfy_root=comfy,
        state_root=tmp_path / "state",
        package_root=package,
        package_validator=lambda root: {"status": "candidate_contract_valid"},
        downloader=downloader,
        merge_tool=merge_tool,
    )

    assert evidence["status"] == "installed_needs_execution_probe"
    assert evidence["execution_proven"] is False
    assert evidence["license_review"]["state"] == "official_source_derivation_verified"
    expected_payloads = [payloads["model-a.safetensors"], qwen, payloads["vae.safetensors"]]
    for artifact, expected in zip(artifacts, expected_payloads, strict=True):
        assert (comfy / "models" / artifact["destination"]).read_bytes() == expected
    assert (tmp_path / "state" / "install.json").is_file()
    status = json.loads((tmp_path / "state" / "status.json").read_text())
    assert status["state"] == "not_installed"
    assert status["artifacts_installed"] is True
    assert status["evidence"]["install"]["sha256"]


def _output_png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (1024, 1024), (17, 34, 51)).save(buffer, format="PNG")
    return buffer.getvalue()


def _runtime_context(tmp_path):
    comfy = _comfy_root(tmp_path)
    fixture, fixture_contract = runtime.load_fixed_fixture()
    binding = {
        "package": {"candidate_sha256": "a" * 64, "bound_files": {}},
        "artifacts": [{"id": "synthetic", "sha256": "b" * 64}],
        "fixture": {
            "bytes": fixture_contract["expected_bytes"],
            "sha256": fixture_contract["sha256"],
        },
    }
    return {
        "comfy_root": comfy,
        "state_root": tmp_path / "state",
        "fixture": fixture,
        "binding": binding,
        "runtime_contract_sha256": runtime._contract_digest(binding),
    }


def _stats(*, free=12_000_000_000):
    return {
        "devices": [
            {
                "name": "NVIDIA GeForce RTX 5070 Ti",
                "type": "cuda",
                "index": 0,
                "vram_total": 16_000_000_000,
                "vram_free": free,
                "torch_vram_total": 15_000_000_000,
                "torch_vram_free": min(free, 15_000_000_000),
            }
        ]
    }


class _FakeClient:
    endpoint_sha256 = "c" * 64

    def __init__(self, *, schema_error=False, submit_unknown=False):
        self.schema_error = schema_error
        self.submit_unknown = submit_unknown
        self.uploads = 0
        self.submissions = 0
        self.events = []

    def get_object_info(self):
        self.events.append("object_info")
        return {"schema_error": self.schema_error}

    def get_queue(self):
        self.events.append("queue")
        return {"queue_running": [], "queue_pending": []}

    def get_system_stats(self):
        self.events.append("stats")
        return _stats(free=10_000_000_000)

    def upload_image(self, payload, filename):
        self.events.append("upload")
        self.uploads += 1
        return f"content-flux2-klein/{filename}"

    def submit_once(self, workflow, client_id):
        self.events.append("submit")
        self.submissions += 1
        if self.submit_unknown:
            raise runtime.SubmissionUnknownError("unknown")
        return "prompt-1"

    def get_history(self, prompt_id):
        self.events.append("history")
        return {
            prompt_id: {
                "status": {"completed": True, "status_str": "success"},
                "outputs": {
                    "23": {
                        "images": [
                            {"filename": "out.png", "subfolder": "", "type": "output"}
                        ]
                    }
                },
            }
        }

    def download_output(self, locator):
        self.events.append("download")
        return _output_png(), "image/png"


def _schema_validator(value):
    if value.get("schema_error"):
        raise runtime.RuntimeContractError("schema drift")
    return value


def _builder(**kwargs):
    return {"reference_images": kwargs["reference_images"], "seed": kwargs["seed"]}


def _workflow_validator(graph, object_info):
    return {"reference_count": len(graph["reference_images"]), "node_count": 1}


def _case_options():
    return {
        "workflow_builder": _builder,
        "object_info_validator": _schema_validator,
        "workflow_validator": _workflow_validator,
        "sleeper": lambda seconds: None,
    }


def test_probe_validates_before_upload_submits_once_and_decodes_output(tmp_path):
    client = _FakeClient()
    result = runtime.run_probe(
        client=client, context=_runtime_context(tmp_path), **_case_options()
    )

    assert result["status"] == "fixed_probe_passed"
    assert result["execution_proven"] is True
    assert result["output"]["decoded"]["width"] == 1024
    assert result["output"]["decoded"]["height"] == 1024
    assert result["gpu"]["device"]["name"] == "NVIDIA GeForce RTX 5070 Ti"
    assert client.uploads == 1
    assert client.submissions == 1
    assert client.events.index("object_info") < client.events.index("upload")
    assert Path(result["evidence_path"]).is_file()


def test_schema_failure_occurs_before_upload_and_writes_failure_evidence(tmp_path):
    client = _FakeClient(schema_error=True)
    context = _runtime_context(tmp_path)

    with pytest.raises(runtime.RuntimeContractError, match="schema drift"):
        runtime.run_probe(client=client, context=context, **_case_options())

    assert client.uploads == 0
    assert client.submissions == 0
    evidence_paths = list((Path(context["state_root"]) / "evidence" / "probe").glob("*/evidence.json"))
    assert len(evidence_paths) == 1
    assert json.loads(evidence_paths[0].read_text())["status"] == "failed_pre_submission"


def test_ambiguous_submission_is_not_retried_and_persists_unknown(tmp_path):
    client = _FakeClient(submit_unknown=True)
    context = _runtime_context(tmp_path)

    with pytest.raises(runtime.SubmissionUnknownError):
        runtime.run_probe(client=client, context=context, **_case_options())

    assert client.submissions == 1
    evidence_path = next((Path(context["state_root"]) / "evidence" / "probe").glob("*/evidence.json"))
    evidence = json.loads(evidence_path.read_text())
    assert evidence["status"] == "submission_unknown"
    assert evidence["blocker_code"] == "flux2_submission_or_execution_unknown"


def test_benchmark_requires_bound_probe_and_runs_exact_sequence(tmp_path):
    context = _runtime_context(tmp_path)
    probe_path = tmp_path / "probe.json"
    probe_path.write_text(
        json.dumps(
            {
                "capability": runtime.CAPABILITY,
                "kind": "probe",
                "status": "fixed_probe_passed",
                "execution_proven": True,
                "reference_count": 1,
                "runtime_contract_sha256": context["runtime_contract_sha256"],
                "fixture": context["binding"]["fixture"],
                "output": {"sha256": "d" * 64},
            }
        )
    )
    sequence = []

    def case_runner(**kwargs):
        count = kwargs["reference_count"]
        sequence.append(count)
        case_evidence = tmp_path / f"case-{count}.json"
        case_evidence.write_text(json.dumps({"count": count}))
        return {
            "status": "benchmark_case_passed",
            "reference_count": count,
            "latency_seconds": float(count),
            "workflow_sha256": str(count) * 64,
            "output": {"sha256": "e" * 64},
            "gpu": {
                "peak_vram_used_bytes": count * 100,
                "minimum_vram_free_bytes": 1000 - count,
            },
            "evidence_path": str(case_evidence),
        }

    result = runtime.run_benchmark(
        client=object(),
        context=context,
        probe_evidence_path=probe_path,
        case_runner=case_runner,
    )

    assert sequence == [1, 2, 10]
    assert result["status"] == "benchmark_passed"
    assert result["benchmark_state"] == "passed"
    assert result["sequential_no_overlap"] is True
    assert [case["reference_count"] for case in result["cases"]] == sequence


def test_benchmark_rejects_stale_probe_before_any_case(tmp_path):
    context = _runtime_context(tmp_path)
    probe_path = tmp_path / "probe.json"
    probe_path.write_text(
        json.dumps(
            {
                "capability": runtime.CAPABILITY,
                "kind": "probe",
                "status": "fixed_probe_passed",
                "execution_proven": True,
                "reference_count": 1,
                "runtime_contract_sha256": "0" * 64,
                "fixture": context["binding"]["fixture"],
                "output": {"sha256": "d" * 64},
            }
        )
    )
    calls = []

    with pytest.raises(runtime.RuntimeContractError, match="stale"):
        runtime.run_benchmark(
            client=object(),
            context=context,
            probe_evidence_path=probe_path,
            case_runner=lambda **kwargs: calls.append(kwargs),
        )

    assert calls == []


def test_atomic_status_promotes_only_through_bound_probe_and_benchmark(tmp_path):
    package, _, payloads, qwen = _synthetic_install_package(tmp_path)
    comfy = _comfy_root(tmp_path)
    state = tmp_path / "state"

    def downloader(record, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payloads[record["path"]])
        return {"status": "downloaded"}

    def merge_tool(manifest_path, source_root, output):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(qwen)
        return {
            "status": "official_qwen_derivation_verified",
            "output_bytes": len(qwen),
            "output_sha256": hashlib.sha256(qwen).hexdigest(),
            "tensor_count": 1,
        }

    installer.install_candidate(
        comfy_root=comfy,
        state_root=state,
        package_root=package,
        package_validator=lambda root: {"status": "candidate_contract_valid"},
        downloader=downloader,
        merge_tool=merge_tool,
    )
    fixture, fixture_contract = runtime.load_fixed_fixture()
    binding = {
        "package": {"candidate_sha256": "a" * 64, "bound_files": {}},
        "artifacts": [{"id": "synthetic", "sha256": "b" * 64}],
        "fixture": {
            "bytes": fixture_contract["expected_bytes"],
            "sha256": fixture_contract["sha256"],
        },
    }
    context = {
        "comfy_root": comfy,
        "state_root": state,
        "package_root": package,
        "fixture": fixture,
        "binding": binding,
        "runtime_contract_sha256": runtime._contract_digest(binding),
    }
    probe = runtime.run_probe(
        client=_FakeClient(), context=context, **_case_options()
    )
    needs_benchmark = runtime.publish_probe_status(
        context=context, probe_result=probe
    )
    assert needs_benchmark["state"] == "needs_benchmark"
    assert needs_benchmark["evidence"]["canary"]["sha256"] == runtime._sha256_file(
        Path(probe["evidence_path"])
    )

    def case_runner(**kwargs):
        count = kwargs["reference_count"]
        case_path = state / f"case-{count}.json"
        case_path.write_text(json.dumps({"count": count}))
        return {
            "status": "benchmark_case_passed",
            "reference_count": count,
            "latency_seconds": float(count),
            "workflow_sha256": str(count) * 64,
            "output": {"sha256": "e" * 64},
            "gpu": {
                "peak_vram_used_bytes": count * 100,
                "minimum_vram_free_bytes": 1000 - count,
            },
            "evidence_path": str(case_path),
        }

    benchmark = runtime.run_benchmark(
        client=object(),
        context=context,
        probe_evidence_path=Path(probe["evidence_path"]),
        case_runner=case_runner,
    )
    ready = runtime.publish_benchmark_status(
        context=context,
        probe_evidence_path=Path(probe["evidence_path"]),
        benchmark_result=benchmark,
    )
    assert ready["state"] == "ready"
    assert ready["startup_ready"] is True
    assert ready["benchmark_state"] == "passed"

    Path(benchmark["evidence_path"]).write_text("{}")
    with pytest.raises(runtime.RuntimeContractError, match="SHA-256"):
        runtime.load_runtime_status(state, package_root=package)


def test_non_loopback_plaintext_endpoint_requires_authentication():
    with pytest.raises(runtime.RuntimeContractError, match="authentication"):
        runtime.ComfyClient("http://worker.example.test:8188")

    client = runtime.ComfyClient(
        "http://worker.example.test:8188", token="test-token", opener=lambda *args: None
    )
    assert client.endpoint_sha256
