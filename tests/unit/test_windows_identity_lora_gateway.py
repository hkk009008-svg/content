from __future__ import annotations

import asyncio
import hashlib
import json
import importlib.util
from pathlib import Path
import struct
import sys
from types import ModuleType, SimpleNamespace

from aiohttp.test_utils import make_mocked_request
import pytest


ROOT = Path(__file__).resolve().parents[2] / "deploy" / "windows-liveportrait-worker"
LORA_PACKAGE = ROOT.parent / "windows-flux2-lora"
CANDIDATE_SHA = ""
TOKEN = "t" * 32


def _load_gateway():
    name = "windows_identity_lora_gateway"
    spec = importlib.util.spec_from_file_location(name, ROOT / "gateway.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_real_lora_training_modules():
    previous = sys.modules.get("contract")
    contract = ModuleType("contract")
    contract.__file__ = str(LORA_PACKAGE / "contract.py")
    sys.modules["contract"] = contract
    try:
        exec(
            compile(
                (LORA_PACKAGE / "contract.py").read_bytes(),
                str(LORA_PACKAGE / "contract.py"),
                "exec",
            ),
            contract.__dict__,
        )
        train = ModuleType("gateway_test_real_lora_train")
        train.__file__ = str(LORA_PACKAGE / "train.py")
        exec(
            compile(
                (LORA_PACKAGE / "train.py").read_bytes(),
                str(LORA_PACKAGE / "train.py"),
                "exec",
            ),
            train.__dict__,
        )
    finally:
        if previous is None:
            sys.modules.pop("contract", None)
        else:
            sys.modules["contract"] = previous
    return contract, train


class _Content:
    def __init__(self, body: bytes) -> None:
        self.body = body

    async def iter_chunked(self, size: int):
        for offset in range(0, len(self.body), max(1, size)):
            yield self.body[offset : offset + size]


class _Request:
    def __init__(
        self,
        *,
        body: bytes = b"",
        content_type: str = "application/json",
        match_info: dict[str, str] | None = None,
        path: str = "/",
        content_length: int | None = None,
    ) -> None:
        self.content = _Content(body)
        self.content_type = content_type
        self.content_length = len(body) if content_length is None else content_length
        self.match_info = match_info or {}
        self.path = path
        self.headers: dict[str, str] = {}
        self.method = "POST"


class _UpstreamResponse:
    def __init__(self, payload: object, status: int = 200) -> None:
        self.payload = payload
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def json(self):
        return self.payload


class _QueueSession:
    def __init__(
        self,
        payload: object | None = None,
        *,
        free_status: int = 200,
        stats_payloads: list[object] | None = None,
    ) -> None:
        self.payload = (
            {"queue_running": [], "queue_pending": []}
            if payload is None
            else payload
        )
        self.free_status = free_status
        self.stats_payloads = stats_payloads or [
            {
                "system": {"os": "nt"},
                "devices": [
                    {
                        "type": "cuda",
                        "index": 0,
                        "vram_total": 16 * 1024 * 1024 * 1024,
                        "vram_free": 14_500_000_000,
                    }
                ],
            }
        ]
        self.stats_index = 0
        self.gets: list[str] = []
        self.posts: list[tuple[str, object, object]] = []

    def get(self, url: str, **_kwargs):
        self.gets.append(url)
        if url.endswith("/system_stats"):
            index = min(self.stats_index, len(self.stats_payloads) - 1)
            self.stats_index += 1
            return _UpstreamResponse(self.stats_payloads[index])
        return _UpstreamResponse(self.payload)

    def post(self, url: str, *, json: object, timeout: object):
        self.posts.append((url, json, timeout))
        return _UpstreamResponse({}, self.free_status)


class _Process:
    def __init__(self) -> None:
        self.done = asyncio.Event()
        self.return_code = 3

    async def wait(self) -> int:
        await self.done.wait()
        return self.return_code


def _png(index: int, width: int = 512, height: int = 512) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + struct.pack(">II", width, height)
        + bytes([8, 2, 0, 0, index])
        + b"crc!"
    )


def _manifest(images: list[bytes], *, suffix: str = "") -> dict[str, object]:
    return {
        "schema_version": 1,
        "contract": "flux2-klein-character-lora-canary-v1",
        "candidate_sha256": CANDIDATE_SHA,
        "consent": True,
        "references": [
            {
                "sha256": hashlib.sha256(image).hexdigest(),
                "caption": (
                    "portrait photograph of hkkperson person, "
                    f"identity reference view {index}{suffix}"
                ),
            }
            for index, image in enumerate(images, 1)
        ],
    }


def _job_id(module, manifest: dict[str, object]) -> str:
    return hashlib.sha256(module._canonical_json(manifest)).hexdigest()[:32]


def _json_request(payload: object, *, job_id: str) -> _Request:
    return _Request(
        body=json.dumps(payload).encode(),
        match_info={"job_id": job_id},
        path=f"/api/identity-lora/jobs/{job_id}",
    )


def _body(response) -> dict[str, object]:
    return json.loads(response.body)


def _mark_flux2_ready(gateway) -> None:
    gateway._flux2_status_record = lambda: {
        "state": "ready",
        "runtime_contract_sha256": "f" * 64,
    }


def _gateway(tmp_path: Path, module, monkeypatch, *, death_guaranteed: bool = True):
    global CANDIDATE_SHA
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path))
    program_files = tmp_path / "Program Files"
    program_files.mkdir(exist_ok=True)
    monkeypatch.setenv("ProgramFiles", str(program_files))
    state = tmp_path / "Content" / "IdentityLab" / "flux2-lora"
    package = state / "package"
    package.mkdir(parents=True, exist_ok=True)
    runtime = state / "runtime" / "venv" / "Scripts"
    runtime.mkdir(parents=True, exist_ok=True)
    python = runtime / "python.exe"
    runner = package / "train.py"
    python.write_bytes(b"fixed python")
    package_files = {
        "README.md": b"test package\n",
        "Install-Candidate.ps1": b"install\n",
        "Benchmark-Candidate.ps1": b"benchmark\n",
        "benchmark.py": b"benchmark python\n",
        "contract.py": b'''from pathlib import Path
import hashlib
import json

def validate_package(root):
    return {}

def package_digest(root):
    return hashlib.sha256((Path(root) / "candidate.json").read_bytes()).hexdigest()

def validate_gateway_admission(state_root, job_id, candidate_sha256):
    root = Path(state_root)
    input_root = root / "jobs" / job_id / "input"
    expected = {"job.json"}
    for index in range(1, 5):
        expected.add(f"reference-{index:02d}.png")
        expected.add(f"reference-{index:02d}.txt")
    if {path.name for path in input_root.iterdir()} != expected:
        raise ValueError("input tree drifted")
    if candidate_sha256 != package_digest(root / "package"):
        raise ValueError("candidate drifted")
    return {"job_id": job_id, "candidate_sha256": candidate_sha256}

def validate_gateway_training_result(
    state_root, job_id, *, expected_activity_lease_sha256, comfy_lora_root=None
):
    root = Path(state_root)
    job = root / "jobs" / job_id
    candidate = package_digest(root / "package")
    manifest_sha = hashlib.sha256((job / "manifest.json").read_bytes()).hexdigest()
    common = {
        "job_id": job_id,
        "candidate_sha256": candidate,
        "manifest_sha256": manifest_sha,
    }
    terminal_path = job / "evidence" / "terminal.json"
    if not terminal_path.exists():
        if (job / "evidence" / "started.json").exists():
            return {**common, "state": "interrupted", "retry_mode": "checkpoint"}
        return {**common, "state": "not_started", "retry_mode": "initial"}
    terminal = json.loads(terminal_path.read_text())
    if terminal["activity_lease_sha256"] != expected_activity_lease_sha256:
        raise ValueError("lease drifted")
    if terminal["state"] != "training_passed":
        state = "training_unknown" if terminal["state"] == "unknown" else "training_failed"
        return {
            **common,
            "state": state,
            "retry_mode": "none",
            "blocker_code": terminal["blocker_code"],
        }
    adapter = terminal["adapter"]
    adapter_path = job / "adapter" / adapter["filename"]
    metadata = json.loads((job / "adapter" / adapter["metadata_filename"]).read_text())
    if comfy_lora_root is not None:
        published = Path(comfy_lora_root) / adapter["filename"]
        if published.read_bytes() != adapter_path.read_bytes():
            raise ValueError("published adapter drifted")
    return {
        **common,
        "state": "training_passed",
        "retry_mode": "none",
        "terminal_sha256": hashlib.sha256(terminal_path.read_bytes()).hexdigest(),
        "runtime_contract_sha256": terminal["inference_runtime_sha256"],
        "activity_lease_sha256": expected_activity_lease_sha256,
        "adapter_path": str(adapter_path.resolve()),
        "adapter": adapter,
        "metadata": metadata,
        "training": {
            "attempt": terminal["attempt"],
            "resumed": terminal["resumed"],
            "elapsed_seconds": terminal["elapsed_seconds"],
            "peak_vram_bytes": terminal["peak_vram_bytes"],
        },
    }

def validate_gateway_benchmark_result(
    state_root,
    job_id,
    *,
    expected_training_activity_lease_sha256,
    expected_benchmark_activity_lease_sha256,
    comfy_lora_root=None,
):
    training = validate_gateway_training_result(
        state_root,
        job_id,
        expected_activity_lease_sha256=expected_training_activity_lease_sha256,
        comfy_lora_root=comfy_lora_root,
    )
    job = Path(state_root) / "jobs" / job_id
    evidence = job / "evidence"
    proof_path = evidence / "inference-benchmark.json"
    if not proof_path.exists():
        if (evidence / "inference-benchmark-unknown.json").exists():
            return {**training, "state": "benchmark_unknown", "retry_mode": "none"}
        if (evidence / "inference-benchmark-failed.json").exists():
            return {**training, "state": "benchmark_failed", "retry_mode": "none"}
        if (evidence / "inference-benchmark-attempt.json").exists() or (job / "benchmark").exists():
            raise ValueError("benchmark preflight artifacts require reconciliation")
        return {**training, "state": "benchmark_not_run", "retry_mode": "benchmark"}
    proof = json.loads(proof_path.read_text())
    if proof["benchmark_activity_lease_sha256"] != expected_benchmark_activity_lease_sha256:
        raise ValueError("benchmark lease drifted")
    return {
        **training,
        "state": "benchmark_passed",
        "retry_mode": "none",
        "proof_sha256": hashlib.sha256(proof_path.read_bytes()).hexdigest(),
        "control": proof["control"],
        "lora": proof["lora"],
    }

def validate_lora_safetensors(*args, **kwargs):
    return {}

def validate_adapter_file(path, metadata, *, root):
    adapter = metadata["adapter"]
    payload = Path(path).read_bytes()
    if len(payload) != adapter["bytes"] or hashlib.sha256(payload).hexdigest() != adapter["sha256"]:
        raise ValueError("adapter drifted")
    return {"bytes": len(payload), "sha256": adapter["sha256"]}
''',
        "inference.py": b"inference python\n",
        "install.py": b"install python\n",
        "preflight.py": b"preflight python\n",
        "requirements.in": b"requirements\n",
        "requirements.lock": b"locked requirements\n",
        "train.py": b"fixed runner\n",
    }
    for name, content in package_files.items():
        (package / name).write_bytes(content)
    candidate = {
        "schema_version": 1,
        "capability": "identity-flux2-klein-lora",
        "candidate_state": "not_installed",
        "readiness": {},
        "storage": {},
        "training": {},
        "resources": {},
        "upstreams": {},
        "inference": {},
        "bindings": {
            name: hashlib.sha256(content).hexdigest()
            for name, content in package_files.items()
        },
    }
    candidate_bytes = json.dumps(candidate, indent=2).encode()
    (package / "candidate.json").write_bytes(candidate_bytes)
    CANDIDATE_SHA = hashlib.sha256(candidate_bytes).hexdigest()
    comfy = tmp_path / "comfy-loras"
    flux2 = tmp_path / "localapp" / "ContentFlux2Klein"
    flux2.mkdir(parents=True, exist_ok=True)
    sentinel = tmp_path / "ready.json"
    revisions = tmp_path / "revisions.json"
    models = tmp_path / "models.json"
    probe = tmp_path / "probe.json"
    for path in (sentinel, revisions, models, probe):
        path.write_text("{}", encoding="utf-8")
    processes: list[_Process] = []
    calls: list[tuple[object, ...]] = []

    async def spawn(*argv, **kwargs):
        calls.append((*argv, kwargs))
        process = _Process()
        processes.append(process)
        return process

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", spawn)
    gateway = module.AuthenticatedGateway(
        upstream="http://127.0.0.1:8188",
        token=TOKEN,
        sentinel=sentinel,
        revisions=revisions,
        models=models,
        probe_contract=probe,
        flux2_state_root=flux2,
        lora_state_root=state,
        lora_python=python,
        lora_runner=runner,
        lora_comfy_root=comfy,
        lora_candidate_sha256=CANDIDATE_SHA,
        lora_process_death_guaranteed=death_guaranteed,
    )
    gateway.session = _QueueSession()
    _mark_flux2_ready(gateway)
    return gateway, processes, calls


async def _upload(gateway, images: list[bytes]) -> None:
    for image in images:
        digest = hashlib.sha256(image).hexdigest()
        response = await gateway.lora_put_blob(
            _Request(
                body=image,
                content_type="application/octet-stream",
                match_info={"sha256": digest},
                path=f"/api/identity-lora/blobs/{digest}",
            )
        )
        assert response.status in {200, 201}


async def _stop(processes: list[_Process], return_code: int = 3) -> None:
    for process in processes:
        process.return_code = return_code
        process.done.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)


def _safetensors() -> bytes:
    header = json.dumps(
        {
            "layer.lora_A.weight": {
                "dtype": "BF16",
                "shape": [16, 1],
                "data_offsets": [0, 32],
            },
            "layer.lora_B.weight": {
                "dtype": "BF16",
                "shape": [1, 16],
                "data_offsets": [32, 64],
            },
        },
        separators=(",", ":"),
    ).encode()
    return struct.pack("<Q", len(header)) + header + bytes(range(64))


def _write_success_files(module, gateway, job_id: str) -> tuple[Path, dict[str, object]]:
    job = gateway.lora_state_root / "jobs" / job_id
    state = gateway._load_lora_state(job)
    work = job / "work"
    evidence = job / "evidence"
    adapter_root = job / "adapter"
    for directory in (work, evidence, adapter_root):
        directory.mkdir(exist_ok=True)
    config = b'{"fixed":true}\n'
    (work / "train.yaml").write_bytes(config)
    input_sha = hashlib.sha256((job / "input" / "job.json").read_bytes()).hexdigest()
    config_sha = hashlib.sha256(config).hexdigest()
    adapter_bytes = _safetensors()
    adapter_sha = hashlib.sha256(adapter_bytes).hexdigest()
    adapter_name = f"identity-lora-{adapter_sha}.safetensors"
    (adapter_root / adapter_name).write_bytes(adapter_bytes)
    inventory = {
        "tensor_count": 2,
        "pair_count": 1,
        "tensor_inventory_sha256": hashlib.sha256(b"test inventory").hexdigest(),
    }
    metadata = {
        "schema_version": 1,
        "state": "training_passed",
        "job_id": job_id,
        "adapter": {
            "filename": adapter_name,
            "bytes": len(adapter_bytes),
            "sha256": adapter_sha,
            **inventory,
        },
        "training": {
            "input_manifest_sha256": input_sha,
            "config_sha256": config_sha,
            "package_sha256": CANDIDATE_SHA,
        },
        "inference": {
            "runtime_contract_sha256": "f" * 64,
        },
    }
    metadata_name = f"{adapter_name}.json"
    module._atomic_json(adapter_root / metadata_name, metadata)
    metadata_sha = hashlib.sha256((adapter_root / metadata_name).read_bytes()).hexdigest()
    log = b"fixed trainer log\n"
    (evidence / "toolkit.log").write_bytes(log)
    terminal = {
        "schema_version": 1,
        "capability": "identity-flux2-klein-lora",
        "job_id": job_id,
        "contract": module.LORA_CANARY_CONTRACT,
        "candidate_sha256": CANDIDATE_SHA,
        "manifest_sha256": state["manifest_sha256"],
        "state": "training_passed",
        "attempt": 1,
        "resumed": False,
        "blocker_code": None,
        "return_code": 0,
        "elapsed_seconds": 12.5,
        "elapsed_scope": "current_process_attempt",
        "peak_vram_bytes": 1024,
        "telemetry_complete": True,
        "package_sha256": CANDIDATE_SHA,
        "input_manifest_sha256": input_sha,
        "config_sha256": config_sha,
        "log_sha256": hashlib.sha256(log).hexdigest(),
        "adapter": {
            "filename": adapter_name,
            "bytes": len(adapter_bytes),
            "sha256": adapter_sha,
            **inventory,
            "metadata_filename": metadata_name,
            "metadata_sha256": metadata_sha,
        },
        "resume_checkpoint_sha256": None,
        "inference_runtime_sha256": "f" * 64,
        "activity_lease_sha256": state["execution_activity_lease_sha256"],
    }
    module._atomic_json(evidence / "terminal.json", terminal)
    return job, terminal


def _write_benchmark(
    module, gateway, job: Path, terminal: dict[str, object]
) -> dict[str, object]:
    state = gateway._load_lora_state(job)
    proof = {
        "benchmark_activity_lease_sha256": state[
            "benchmark_activity_lease_sha256"
        ],
        "control": {
            "latency_seconds": 1.0,
            "peak_vram_bytes": 1024,
            "output_sha256": "1" * 64,
        },
        "lora": {
            "latency_seconds": 2.0,
            "peak_vram_bytes": 2048,
            "output_sha256": "2" * 64,
        },
    }
    module._atomic_json(
        job / "evidence" / "inference-benchmark.json", proof
    )
    return proof


async def _complete_benchmark(
    module,
    gateway,
    processes: list[_Process],
    job: Path,
    terminal: dict[str, object],
    *,
    return_code: int = 0,
) -> None:
    processes[0].return_code = 0
    processes[0].done.set()
    for _ in range(20):
        await asyncio.sleep(0)
        if len(processes) == 2:
            break
    assert len(processes) == 2
    _write_benchmark(module, gateway, job, terminal)
    processes[1].return_code = return_code
    processes[1].done.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)


def test_identity_lora_routes_are_explicit_and_invalid_shapes_never_proxy(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_gateway()
    gateway, _processes, _calls = _gateway(tmp_path, module, monkeypatch)
    app = module.create_app(gateway)

    async def resolve(path: str, method: str):
        request = make_mocked_request(method, path, app=app)
        return (await app.router.resolve(request)).handler.__name__

    assert asyncio.run(resolve("/api/identity-lora/jobs/" + "a" * 32, "PUT")) == "lora_put_job"
    assert asyncio.run(resolve("/api/identity-lora/ready", "GET")) == "lora_ready"
    assert asyncio.run(resolve("/api/identity-lora/jobs/" + "A" * 32, "PUT")) == "lora_not_found"
    assert asyncio.run(resolve("/api/identity-lora/blobs/../../prompt", "PUT")) == "lora_not_found"

    gateway._ready_record = lambda: {"status": "ready"}
    called: list[str] = []

    async def handler(request):
        called.append(request.path)
        return module.web.json_response({})

    unauthorized = asyncio.run(
        gateway.access_control(
            SimpleNamespace(path="/api/identity-lora/ready", headers={}), handler
        )
    )
    assert unauthorized.status == 401
    assert called == []

    gateway._ready_record = lambda: None
    backend_blocked = asyncio.run(
        gateway.access_control(
            SimpleNamespace(
                path="/api/identity-lora/ready",
                headers={"Authorization": f"Bearer {TOKEN}"},
            ),
            handler,
        )
    )
    assert backend_blocked.status == 503
    assert _body(backend_blocked) == {
        "schema_version": 1,
        "contract": module.LORA_CANARY_CONTRACT,
        "candidate_sha256": CANDIDATE_SHA,
        "state": "blocked",
        "blocker_code": "backend_not_ready",
        "job_submission_ready": False,
    }
    assert called == []


def test_blob_is_bounded_digest_verified_idempotent_and_refuses_symlink(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_gateway()
    gateway, _processes, _calls = _gateway(tmp_path, module, monkeypatch)
    payload = b"bounded-reference"
    digest = hashlib.sha256(payload).hexdigest()

    async def scenario():
        mismatch = await gateway.lora_put_blob(
            _Request(
                body=payload,
                content_type="application/octet-stream",
                match_info={"sha256": "0" * 64},
            )
        )
        assert mismatch.status == 422
        oversized = await gateway.lora_put_blob(
            _Request(
                body=b"",
                content_type="application/octet-stream",
                match_info={"sha256": digest},
                content_length=module.LORA_MAX_BLOB_BYTES + 1,
            )
        )
        assert oversized.status == 413
        stored = await gateway.lora_put_blob(
            _Request(
                body=payload,
                content_type="application/octet-stream",
                match_info={"sha256": digest},
            )
        )
        replay = await gateway.lora_put_blob(
            _Request(
                body=payload,
                content_type="application/octet-stream",
                match_info={"sha256": digest},
            )
        )
        assert (stored.status, _body(stored)["state"]) == (201, "stored")
        assert (replay.status, _body(replay)["state"]) == (200, "present")

    asyncio.run(scenario())

    other = b"outside"
    other_digest = hashlib.sha256(other).hexdigest()
    outside = tmp_path / "outside"
    outside.write_bytes(other)
    (gateway.lora_state_root / "blobs" / f"{other_digest}.blob").symlink_to(outside)
    response = asyncio.run(
        gateway.lora_put_blob(
            _Request(
                body=other,
                content_type="application/octet-stream",
                match_info={"sha256": other_digest},
            )
        )
    )
    assert response.status == 503
    assert outside.read_bytes() == other


def test_manifest_is_exact_consent_and_candidate_bound_before_launch(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_gateway()
    gateway, processes, calls = _gateway(tmp_path, module, monkeypatch)
    images = [_png(index) for index in range(1, 5)]
    valid = _manifest(images)
    wrong_caption = json.loads(json.dumps(valid))
    wrong_caption["references"][0]["caption"] = "hkkperson alternate caption"

    async def scenario():
        await _upload(gateway, images)
        for mutation in (
            {**valid, "extra": True},
            {**valid, "consent": False},
            {**valid, "candidate_sha256": "d" * 64},
            {**valid, "references": [valid["references"][0]] * 4},
            wrong_caption,
        ):
            response = await gateway.lora_put_job(
                _json_request(mutation, job_id="1" * 32)
            )
            assert response.status in {400, 409}
        assert calls == []
        assert processes == []

    asyncio.run(scenario())


def test_reference_pixel_limit_is_enforced_before_job_materialization(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_gateway()
    gateway, processes, calls = _gateway(tmp_path, module, monkeypatch)
    images = [_png(1, width=8192, height=8192)] + [
        _png(index) for index in range(2, 5)
    ]
    manifest = _manifest(images)
    job_id = _job_id(module, manifest)

    async def scenario():
        await _upload(gateway, images)
        response = await gateway.lora_put_job(
            _json_request(manifest, job_id=job_id)
        )
        assert response.status == 503
        assert calls == []
        assert processes == []
        assert not (gateway.lora_state_root / "jobs" / job_id).exists()

    asyncio.run(scenario())


def test_same_job_race_launches_once_and_materializes_fixed_package_input(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_gateway()
    gateway, processes, calls = _gateway(tmp_path, module, monkeypatch)
    images = [_png(index) for index in range(1, 5)]
    manifest = _manifest(images)
    job_id = _job_id(module, manifest)

    async def scenario():
        await _upload(gateway, images)
        first, second = await asyncio.gather(
            gateway.lora_put_job(_json_request(manifest, job_id=job_id)),
            gateway.lora_put_job(_json_request(manifest, job_id=job_id)),
        )
        assert {first.status, second.status} == {200, 202}
        assert len(calls) == 1
        assert calls[0][0:3] == (
            str(gateway.lora_python),
            str(gateway.lora_runner),
            job_id,
        )
        launch_options = calls[0][-1]
        assert launch_options["cwd"] == str(gateway.lora_runner.parent)
        assert set(launch_options["env"]) == {
            "SystemRoot",
            "PROGRAMDATA",
            "ProgramFiles",
            "LOCALAPPDATA",
            "TEMP",
            "TMP",
            "MPLCONFIGDIR",
            "PYTHONUTF8",
            "PYTHONDONTWRITEBYTECODE",
            "CONTENT_LORA_ACTIVITY_LEASE_SHA256",
        }
        # MPLCONFIGDIR must be non-empty and absolute or it fails open silently.
        # matplotlib tests `if configdir:` -- truthiness, so "" re-arms the exact
        # Path.home() crash this variable exists to prevent -- and resolves a
        # relative value against cwd, which is the digest-pinned package dir.
        # Asserting the value and not merely the key is what makes this a
        # control: the key alone would still pass with an empty string.
        matplotlib_config = launch_options["env"]["MPLCONFIGDIR"]
        assert matplotlib_config
        assert Path(matplotlib_config).is_absolute()
        assert launch_options["env"]["LOCALAPPDATA"] == str(
            gateway.flux2_state_root.parent
        )
        assert launch_options["env"]["ProgramFiles"] == str(
            gateway.lora_program_files
        )
        assert "COMFYUI_API_KEY" not in launch_options["env"]
        job = gateway.lora_state_root / "jobs" / job_id
        admission = json.loads((job / "input" / "job.json").read_text())
        assert set(admission) == {
            "schema_version",
            "job_id",
            "trigger_token",
            "consent",
            "references",
        }
        assert admission["trigger_token"] == "hkkperson"
        assert admission["consent"]["identity_owner_authorized"] is True
        assert [record["image"] for record in admission["references"]] == [
            f"reference-{index:02d}.png" for index in range(1, 5)
        ]
        assert not (job / "output").exists()
        activity_path = gateway.lora_state_root / "locks" / "gateway-activity.lock"
        activity = json.loads(activity_path.read_text())
        assert activity["activity"] == "training"
        assert activity["job_id"] == job_id
        assert (
            launch_options["env"]["CONTENT_LORA_ACTIVITY_LEASE_SHA256"]
            == hashlib.sha256(activity_path.read_bytes()).hexdigest()
        )
        changed = json.loads(json.dumps(manifest))
        changed["references"][0]["sha256"] = "d" * 64
        conflict = await gateway.lora_put_job(_json_request(changed, job_id=job_id))
        other = await gateway.lora_put_job(_json_request(manifest, job_id="3" * 32))
        assert conflict.status == 409
        assert other.status == 409
        assert len(calls) == 1
        await _stop(processes)
        assert not activity_path.exists()

    asyncio.run(scenario())


def test_manifest_digest_is_the_only_job_id_before_and_after_execution(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_gateway()
    gateway, processes, calls = _gateway(tmp_path, module, monkeypatch)
    images = [_png(index) for index in range(1, 5)]
    manifest = _manifest(images)
    canonical = _job_id(module, manifest)
    alternate = "f" * 32 if canonical != "f" * 32 else "e" * 32

    async def scenario():
        await _upload(gateway, images)
        rejected = await gateway.lora_put_job(
            _json_request(manifest, job_id=alternate)
        )
        assert rejected.status == 409
        assert _body(rejected) == {"error": "job_id_contract_mismatch"}
        assert calls == []
        assert not (gateway.lora_state_root / "jobs" / alternate).exists()

        accepted = await gateway.lora_put_job(
            _json_request(manifest, job_id=canonical)
        )
        assert accepted.status == 202
        await _stop(processes)
        replay = await gateway.lora_put_job(
            _json_request(manifest, job_id=alternate)
        )
        assert replay.status == 409
        assert len(calls) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("mutation", ["runner", "pycache", "extra_directory"])
def test_candidate_package_is_rehashed_and_has_no_unbound_entries_before_launch(
    tmp_path: Path, monkeypatch, mutation: str
) -> None:
    module = _load_gateway()
    gateway, _processes, calls = _gateway(tmp_path, module, monkeypatch)
    images = [_png(index) for index in range(1, 5)]
    manifest = _manifest(images)
    job_id = _job_id(module, manifest)
    if mutation == "runner":
        gateway.lora_runner.write_bytes(b"replaced runner\n")
    elif mutation == "pycache":
        cache = gateway.lora_runner.parent / "__pycache__"
        cache.mkdir()
        (cache / "contract.cpython-312.pyc").write_bytes(b"crafted bytecode")
    else:
        (gateway.lora_runner.parent / "extra").mkdir()

    async def scenario():
        await _upload(gateway, images)
        response = await gateway.lora_put_job(
            _json_request(manifest, job_id=job_id)
        )
        assert response.status == 503
        assert _body(response) == {"error": "identity_lora_state_invalid"}
        assert calls == []
        assert not (gateway.lora_state_root / "jobs" / job_id).exists()
        assert not (
            gateway.lora_state_root / "locks" / "gateway-activity.lock"
        ).exists()

    asyncio.run(scenario())


def test_verified_contract_loading_never_creates_bytecode_cache(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_gateway()
    gateway, _processes, _calls = _gateway(tmp_path, module, monkeypatch)
    gateway._validate_lora_package()
    assert not (gateway.lora_runner.parent / "__pycache__").exists()


def test_package_contract_rejects_input_tree_drift_before_runner_launch(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_gateway()
    gateway, _processes, calls = _gateway(tmp_path, module, monkeypatch)
    images = [_png(index) for index in range(1, 5)]
    manifest = _manifest(images)
    job_id = _job_id(module, manifest)
    create = gateway._create_lora_job_files

    def create_with_extra(*args, **kwargs):
        state = create(*args, **kwargs)
        job_dir = args[0]
        (job_dir / "input" / "unmanifested.png").write_bytes(_png(9))
        return state

    gateway._create_lora_job_files = create_with_extra

    async def scenario():
        await _upload(gateway, images)
        response = await gateway.lora_put_job(
            _json_request(manifest, job_id=job_id)
        )
        assert response.status == 503
        assert calls == []

    asyncio.run(scenario())


def test_pre_spawn_training_failure_releases_lease_and_allows_one_retry(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_gateway()
    gateway, _processes, _calls = _gateway(tmp_path, module, monkeypatch)
    images = [_png(index) for index in range(1, 5)]
    manifest = _manifest(images)
    job_id = _job_id(module, manifest)

    async def fail_spawn(*_args, **_kwargs):
        raise OSError("spawn failed before process acknowledgement")

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", fail_spawn)

    async def scenario():
        await _upload(gateway, images)
        response = await gateway.lora_put_job(
            _json_request(manifest, job_id=job_id)
        )
        assert response.status == 503
        state = gateway._load_lora_state(gateway._lora_job_dir(job_id, required=True))
        assert state["state"] == "failed"
        assert state["retriable"] is True
        assert state["retry_mode"] == "initial"
        assert state["blocker_code"] == "trainer_launch_failed"
        assert state["activity_lease_sha256"] is None
        assert not (
            gateway.lora_state_root / "locks" / "gateway-activity.lock"
        ).exists()

    asyncio.run(scenario())


def test_gateway_log_is_outside_real_trainer_evidence_allowlist(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_gateway()
    gateway, processes, _calls = _gateway(tmp_path, module, monkeypatch)
    package_contract, package_train = _load_real_lora_training_modules()
    images = [_png(index) for index in range(1, 5)]
    manifest = _manifest(images)
    job_id = _job_id(module, manifest)
    original_spawn = module.asyncio.create_subprocess_exec
    reset_checked: list[bool] = []

    async def checked_spawn(*args, **kwargs):
        job = gateway._lora_job_dir(job_id, required=True)
        log = job / "gateway-logs" / "runner-1.log"
        assert log.is_file()
        assert not (job / "evidence" / "gateway-runner-1.log").exists()
        package_train._reset_unstarted_partial_evidence(
            package_contract.job_paths(gateway.lora_state_root, job_id),
            job_id,
            activity_lease_sha256=str(
                gateway._load_lora_state(job)["activity_lease_sha256"]
            ),
        )
        reset_checked.append(True)
        return await original_spawn(*args, **kwargs)

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", checked_spawn)

    async def scenario():
        await _upload(gateway, images)
        response = await gateway.lora_put_job(
            _json_request(manifest, job_id=job_id)
        )
        assert response.status == 202
        assert reset_checked == [True]
        await _stop(processes)

    asyncio.run(scenario())


def test_pre_spawn_benchmark_failure_releases_lease_and_allows_one_retry(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_gateway()
    gateway, processes, calls = _gateway(tmp_path, module, monkeypatch)
    images = [_png(index) for index in range(1, 5)]
    manifest = _manifest(images)
    job_id = _job_id(module, manifest)
    original_spawn = module.asyncio.create_subprocess_exec

    async def training_only_spawn(*args, **kwargs):
        if calls:
            raise OSError("benchmark spawn failed before process acknowledgement")
        return await original_spawn(*args, **kwargs)

    monkeypatch.setattr(
        module.asyncio, "create_subprocess_exec", training_only_spawn
    )

    async def scenario():
        await _upload(gateway, images)
        assert (
            await gateway.lora_put_job(_json_request(manifest, job_id=job_id))
        ).status == 202
        job, _terminal = _write_success_files(module, gateway, job_id)
        processes[0].return_code = 0
        processes[0].done.set()
        for _ in range(20):
            await asyncio.sleep(0)
            state = gateway._load_lora_state(job)
            if state["state"] != "running":
                break
        state = gateway._load_lora_state(job)
        assert state["state"] == "failed"
        assert state["retriable"] is True
        assert state["retry_mode"] == "benchmark"
        assert state["blocker_code"] == "benchmark_launch_failed"
        assert state["activity_lease_sha256"] is None
        assert not (
            gateway.lora_state_root / "locks" / "gateway-activity.lock"
        ).exists()

    asyncio.run(scenario())


def test_comfy_queue_and_prompt_race_gate_both_dispatch_orders(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_gateway()
    gateway, processes, calls = _gateway(tmp_path, module, monkeypatch)
    images = [_png(index) for index in range(1, 5)]
    manifest = _manifest(images)
    job_id = _job_id(module, manifest)

    async def scenario():
        await _upload(gateway, images)
        gateway.session = _QueueSession({"queue_running": [[1]], "queue_pending": []})
        busy = await gateway.lora_put_job(
            _json_request(manifest, job_id=job_id)
        )
        assert busy.status == 409
        assert calls == []
        assert not (gateway.lora_state_root / "jobs" / job_id).exists()
        assert not (
            gateway.lora_state_root / "locks" / "gateway-activity.lock"
        ).exists()

        gateway.session = _QueueSession()

        async def accepted_prompt(_request):
            gateway.session.payload["queue_pending"].append(["prompt-1"])
            return module.web.json_response({"prompt_id": "prompt-1"})

        gateway._proxy_unlocked = accepted_prompt
        accepted = await gateway.proxy(
            _Request(path="/prompt", content_type="application/json")
        )
        assert accepted.status == 200
        assert not (
            gateway.lora_state_root / "locks" / "gateway-activity.lock"
        ).exists()
        fenced = await gateway.lora_put_job(
            _json_request(manifest, job_id=job_id)
        )
        assert fenced.status == 409
        assert calls == []

        gateway.session = _QueueSession()
        started = await gateway.lora_put_job(
            _json_request(manifest, job_id=job_id)
        )
        assert started.status == 202
        blocked = await gateway.proxy(
            _Request(path="/prompt", content_type="application/json")
        )
        assert blocked.status == 409
        assert _body(blocked) == {"error": "identity_lora_job_active"}
        await _stop(processes)

    asyncio.run(scenario())


def test_training_frees_comfy_models_under_lease_before_spawn(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_gateway()
    gateway, processes, _calls = _gateway(tmp_path, module, monkeypatch)
    images = [_png(index) for index in range(1, 5)]
    manifest = _manifest(images)
    job_id = _job_id(module, manifest)
    session = gateway.session
    assert isinstance(session, _QueueSession)
    session.stats_payloads = [
        {
            "system": {"os": "nt"},
            "devices": [
                {
                    "type": "cuda",
                    "index": 0,
                    "vram_total": 16 * 1024 * 1024 * 1024,
                    "vram_free": 10_000_000_000,
                }
            ],
        },
        {
            "system": {"os": "nt"},
            "devices": [
                {
                    "type": "cuda",
                    "index": 0,
                    "vram_total": 16 * 1024 * 1024 * 1024,
                    "vram_free": 16 * 1024 * 1024 * 1024,
                }
            ],
        },
    ]
    events: list[str] = []
    original_get = session.get
    original_post = session.post
    original_spawn = module.asyncio.create_subprocess_exec

    def ordered_get(url: str, **kwargs):
        events.append("stats" if url.endswith("/system_stats") else "queue")
        return original_get(url, **kwargs)

    def ordered_post(url: str, *, json: object, timeout: object):
        lock = gateway.lora_state_root / "locks" / "gateway-activity.lock"
        assert json == {"unload_models": True, "free_memory": True}
        assert lock.is_file()
        assert module._json_without_duplicate_keys(lock.read_bytes())["activity"] == (
            "training"
        )
        events.append("free")
        return original_post(url, json=json, timeout=timeout)

    async def ordered_spawn(*args, **kwargs):
        events.append("spawn")
        return await original_spawn(*args, **kwargs)

    session.get = ordered_get
    session.post = ordered_post
    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", ordered_spawn)

    async def scenario():
        await _upload(gateway, images)
        response = await gateway.lora_put_job(
            _json_request(manifest, job_id=job_id)
        )
        assert response.status == 202
        assert events == [
            "queue",
            "free",
            "stats",
            "queue",
            "stats",
            "queue",
            "spawn",
        ]
        assert session.posts[0][0] == "http://127.0.0.1:8188/free"
        await _stop(processes)

    asyncio.run(scenario())


def test_training_does_not_launch_when_comfy_memory_release_fails(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_gateway()
    gateway, _processes, calls = _gateway(tmp_path, module, monkeypatch)
    gateway.session = _QueueSession(free_status=500)
    images = [_png(index) for index in range(1, 5)]
    manifest = _manifest(images)
    job_id = _job_id(module, manifest)

    async def scenario():
        await _upload(gateway, images)
        response = await gateway.lora_put_job(
            _json_request(manifest, job_id=job_id)
        )
        assert response.status == 503
        assert _body(response) == {"error": "comfy_memory_release_failed"}
        assert calls == []
        assert not (gateway.lora_state_root / "jobs" / job_id).exists()
        assert not (
            gateway.lora_state_root / "locks" / "gateway-activity.lock"
        ).exists()

    asyncio.run(scenario())


def test_benchmark_and_prompt_share_one_atomic_gpu_activity_lease(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_gateway()
    gateway, _processes, _calls = _gateway(tmp_path, module, monkeypatch)
    entered = asyncio.Event()
    finish = asyncio.Event()

    async def accepted_prompt(_request):
        entered.set()
        await finish.wait()
        return module.web.json_response({"prompt_id": "p" * 32})

    gateway._proxy_unlocked = accepted_prompt

    async def scenario():
        prompt = asyncio.create_task(
            gateway.proxy(_Request(path="/prompt", content_type="application/json"))
        )
        await entered.wait()
        activity_path = gateway.lora_state_root / "locks" / "gateway-activity.lock"
        record = json.loads(activity_path.read_text())
        assert record["activity"] == "prompt"
        assert gateway._try_acquire_lora_activity("benchmark", "d" * 32) is None
        finish.set()
        assert (await prompt).status == 200
        assert not activity_path.exists()

        benchmark_sha = gateway._try_acquire_lora_activity(
            "benchmark", "d" * 32
        )
        assert benchmark_sha is not None
        blocked = await gateway.proxy(
            _Request(path="/prompt", content_type="application/json")
        )
        assert blocked.status == 409
        assert _body(blocked) == {"error": "identity_lora_gpu_active"}
        assert hashlib.sha256(activity_path.read_bytes()).hexdigest() == benchmark_sha
        gateway._release_lora_activity(benchmark_sha)

    asyncio.run(scenario())


def test_ambiguous_prompt_retains_gpu_lease_and_blocks_training(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_gateway()
    gateway, _processes, calls = _gateway(tmp_path, module, monkeypatch)
    images = [_png(index) for index in range(1, 5)]
    manifest = _manifest(images)
    job_id = _job_id(module, manifest)

    async def unknown(_request):
        return module.web.json_response(
            {"error": "upstream_outcome_unknown"},
            status=502,
            headers={"X-Content-Gateway-Outcome": "unknown"},
        )

    gateway._proxy_unlocked = unknown

    async def scenario():
        response = await gateway.proxy(
            _Request(path="/prompt", content_type="application/json")
        )
        assert response.status == 502
        activity_path = gateway.lora_state_root / "locks" / "gateway-activity.lock"
        assert json.loads(activity_path.read_text())["activity"] == "prompt"
        blocked = await gateway.lora_put_job(
            _json_request(manifest, job_id=job_id)
        )
        assert blocked.status == 409
        assert _body(blocked) == {"error": "identity_lora_gpu_active"}
        assert calls == []

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("queue_payload", "released"),
    [
        ({"queue_running": [], "queue_pending": []}, True),
        ({"queue_running": [["active"]], "queue_pending": []}, False),
        ({}, False),
    ],
)
def test_restart_releases_only_queue_proven_idle_orphan_prompt_lease(
    tmp_path: Path, monkeypatch, queue_payload: object, released: bool
) -> None:
    module = _load_gateway()
    first, _processes, _calls = _gateway(tmp_path, module, monkeypatch)
    digest = first._try_acquire_lora_activity("prompt", "a" * 32)
    assert digest is not None
    lock = first.lora_state_root / "locks" / "gateway-activity.lock"

    restarted, _processes, _calls = _gateway(tmp_path, module, monkeypatch)
    restarted.session = _QueueSession(queue_payload)

    async def scenario():
        await restarted._reconcile_orphan_prompt_activity(startup=True)
        assert lock.exists() is not released
        if not released:
            restarted.session = _QueueSession()
            await restarted._reconcile_orphan_prompt_activity()
            assert not lock.exists()

    asyncio.run(scenario())


def test_startup_recovery_is_unknown_without_job_object_and_only_interrupted_resumes(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_gateway()
    first, processes, _calls = _gateway(tmp_path, module, monkeypatch)
    images = [_png(index) for index in range(1, 5)]
    manifest = _manifest(images)
    job_id = _job_id(module, manifest)

    async def admit():
        await _upload(first, images)
        assert (await first.lora_put_job(_json_request(manifest, job_id=job_id))).status == 202
        assert first._lora_watch_task is not None
        first._lora_watch_task.cancel()
        await asyncio.gather(first._lora_watch_task, return_exceptions=True)

    asyncio.run(admit())

    unknown, _unknown_processes, unknown_calls = _gateway(
        tmp_path, module, monkeypatch, death_guaranteed=False
    )
    unknown._recover_lora_jobs()
    unknown_state = unknown._load_lora_state(unknown._lora_job_dir(job_id, required=True))
    assert unknown_state["state"] == "unknown"
    response = asyncio.run(
        unknown.lora_resume_job(
            _Request(body=b"{}", match_info={"job_id": job_id})
        )
    )
    assert response.status == 409
    assert unknown_calls == []

    # Recreate the durable pre-restart state to exercise the Job Object branch.
    unknown_state["state"] = "running"
    unknown_state["blocker_code"] = ""
    unknown_state["completed_at_unix"] = None
    unknown._write_lora_state(unknown._lora_job_dir(job_id, required=True), unknown_state)
    interrupted, resumed_processes, resumed_calls = _gateway(
        tmp_path, module, monkeypatch, death_guaranteed=True
    )
    interrupted._recover_lora_jobs()
    recovered = interrupted._load_lora_state(
        interrupted._lora_job_dir(job_id, required=True)
    )
    assert recovered["state"] == "interrupted"
    assert recovered["retriable"] is True
    assert recovered["retry_mode"] == "initial"

    async def different_job_is_blocked():
        other_images = [_png(index) for index in range(5, 9)]
        await _upload(interrupted, other_images)
        other_manifest = _manifest(other_images)
        blocked = await interrupted.lora_put_job(
            _json_request(other_manifest, job_id=_job_id(module, other_manifest))
        )
        assert blocked.status == 409
        assert _body(blocked) == {"error": "identity_lora_job_active"}

    asyncio.run(different_job_is_blocked())
    unavailable = asyncio.run(
        interrupted.lora_resume_job(
            _Request(body=b"{}", match_info={"job_id": job_id})
        )
    )
    assert unavailable.status == 202
    assert resumed_calls[0][0:3] == (
        str(interrupted.lora_python),
        str(interrupted.lora_runner),
        job_id,
    )
    resumed_state = interrupted._load_lora_state(
        interrupted._lora_job_dir(job_id, required=True)
    )
    assert resumed_state["retriable"] is False
    assert resumed_state["retry_mode"] == "none"
    replay = asyncio.run(
        interrupted.lora_resume_job(
            _Request(body=b"{}", match_info={"job_id": job_id})
        )
    )
    assert replay.status == 200
    assert len(resumed_calls) == 1
    assert len(resumed_processes) == 1


def test_started_job_object_restart_exposes_one_checkpoint_resume(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_gateway()
    gateway, _processes, _calls = _gateway(tmp_path, module, monkeypatch)
    images = [_png(index) for index in range(1, 5)]
    manifest = _manifest(images)
    job_id = _job_id(module, manifest)

    async def admit():
        await _upload(gateway, images)
        assert (
            await gateway.lora_put_job(_json_request(manifest, job_id=job_id))
        ).status == 202
        assert gateway._lora_watch_task is not None
        gateway._lora_watch_task.cancel()
        await asyncio.gather(gateway._lora_watch_task, return_exceptions=True)

    asyncio.run(admit())
    job = gateway._lora_job_dir(job_id, required=True)
    (job / "evidence").mkdir()
    module._atomic_json(job / "evidence" / "started.json", {"started": True})
    restarted, resumed_processes, resumed_calls = _gateway(
        tmp_path, module, monkeypatch, death_guaranteed=True
    )
    restarted._recover_lora_jobs()
    recovered = restarted._load_lora_state(job)
    assert recovered["retriable"] is True
    assert recovered["retry_mode"] == "checkpoint"
    response = asyncio.run(
        restarted.lora_resume_job(
            _Request(body=b"{}", match_info={"job_id": job_id})
        )
    )
    assert response.status == 202
    assert resumed_calls[0][0:4] == (
        str(restarted.lora_python),
        str(restarted.lora_runner),
        "--resume",
        job_id,
    )
    assert len(resumed_processes) == 1


def test_restart_after_training_pass_publishes_and_exposes_first_benchmark(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_gateway()
    gateway, _processes, _calls = _gateway(tmp_path, module, monkeypatch)
    images = [_png(index) for index in range(1, 5)]
    manifest = _manifest(images)
    job_id = _job_id(module, manifest)

    async def admit():
        await _upload(gateway, images)
        assert (
            await gateway.lora_put_job(_json_request(manifest, job_id=job_id))
        ).status == 202
        job, terminal = _write_success_files(module, gateway, job_id)
        assert gateway._lora_watch_task is not None
        gateway._lora_watch_task.cancel()
        await asyncio.gather(gateway._lora_watch_task, return_exceptions=True)
        return job, terminal

    job, terminal = asyncio.run(admit())
    restarted, resumed_processes, resumed_calls = _gateway(
        tmp_path, module, monkeypatch, death_guaranteed=True
    )
    restarted._recover_lora_jobs()
    recovered = restarted._load_lora_state(job)
    assert recovered["state"] == "failed"
    assert recovered["retriable"] is True
    assert recovered["retry_mode"] == "benchmark"
    assert recovered["benchmark_attempt_index"] == 0
    assert recovered["activity_lease_sha256"] is None
    assert (
        restarted.lora_comfy_root / terminal["adapter"]["filename"]
    ).is_file()

    response = asyncio.run(
        restarted.lora_resume_job(
            _Request(body=b"{}", match_info={"job_id": job_id})
        )
    )
    assert response.status == 202
    assert resumed_calls[0][0:3] == (
        str(restarted.lora_python),
        str(restarted.lora_runner.parent / "benchmark.py"),
        job_id,
    )
    assert restarted._load_lora_state(job)["benchmark_attempt_index"] == 1
    assert len(resumed_processes) == 1


def test_benchmark_restart_reconciles_proof_and_never_stays_running(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_gateway()
    gateway, processes, _calls = _gateway(tmp_path, module, monkeypatch)
    images = [_png(index) for index in range(1, 5)]
    manifest = _manifest(images)
    job_id = _job_id(module, manifest)

    async def reach_benchmark():
        await _upload(gateway, images)
        assert (
            await gateway.lora_put_job(_json_request(manifest, job_id=job_id))
        ).status == 202
        job, terminal = _write_success_files(module, gateway, job_id)
        processes[0].return_code = 0
        processes[0].done.set()
        for _ in range(20):
            await asyncio.sleep(0)
            if len(processes) == 2:
                break
        assert len(processes) == 2
        _write_benchmark(module, gateway, job, terminal)
        assert gateway._lora_watch_task is not None
        gateway._lora_watch_task.cancel()
        await asyncio.gather(gateway._lora_watch_task, return_exceptions=True)
        return job

    job = asyncio.run(reach_benchmark())
    restarted, _restarted_processes, _restarted_calls = _gateway(
        tmp_path, module, monkeypatch, death_guaranteed=True
    )
    restarted._recover_lora_jobs()
    recovered = restarted._load_lora_state(job)
    assert recovered["state"] == "succeeded"
    assert recovered["activity_lease_sha256"] is None
    assert not (
        restarted.lora_state_root / "locks" / "gateway-activity.lock"
    ).exists()
    ready = asyncio.run(restarted.lora_ready(_Request()))
    assert ready.status == 200


@pytest.mark.parametrize("ambiguous", [False, True])
def test_benchmark_restart_retries_only_before_any_submission_evidence(
    tmp_path: Path, monkeypatch, ambiguous: bool
) -> None:
    module = _load_gateway()
    gateway, processes, _calls = _gateway(tmp_path, module, monkeypatch)
    images = [_png(index) for index in range(1, 5)]
    manifest = _manifest(images)
    job_id = _job_id(module, manifest)

    async def reach_benchmark():
        await _upload(gateway, images)
        assert (
            await gateway.lora_put_job(_json_request(manifest, job_id=job_id))
        ).status == 202
        job, _terminal = _write_success_files(module, gateway, job_id)
        processes[0].return_code = 0
        processes[0].done.set()
        for _ in range(20):
            await asyncio.sleep(0)
            if len(processes) == 2:
                break
        assert len(processes) == 2
        assert gateway._lora_watch_task is not None
        gateway._lora_watch_task.cancel()
        await asyncio.gather(gateway._lora_watch_task, return_exceptions=True)
        return job

    job = asyncio.run(reach_benchmark())
    if ambiguous:
        module._atomic_json(
            job / "evidence" / "inference-benchmark-attempt.json",
            {"submission_may_have_happened": True},
        )
    restarted, _restarted_processes, _restarted_calls = _gateway(
        tmp_path, module, monkeypatch, death_guaranteed=True
    )
    restarted._recover_lora_jobs()
    recovered = restarted._load_lora_state(job)
    lock = restarted.lora_state_root / "locks" / "gateway-activity.lock"
    if ambiguous:
        assert recovered["state"] == "unknown"
        assert recovered["retriable"] is False
        assert recovered["retry_mode"] == "none"
        assert lock.is_file()
    else:
        assert recovered["state"] == "failed", recovered["blocker_code"]
        assert recovered["retriable"] is True
        assert recovered["retry_mode"] == "benchmark"
        assert recovered["benchmark_attempt_index"] == 1
        assert not lock.exists()


def test_training_automatically_benchmarks_and_only_then_succeeds(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_gateway()
    gateway, processes, calls = _gateway(tmp_path, module, monkeypatch)
    images = [_png(index) for index in range(1, 5)]
    manifest = _manifest(images)
    job_id = _job_id(module, manifest)

    async def scenario():
        bootstrap = await gateway.lora_ready(_Request())
        assert bootstrap.status == 503
        assert _body(bootstrap)["job_submission_ready"] is True
        await _upload(gateway, images)
        assert (
            await gateway.lora_put_job(_json_request(manifest, job_id=job_id))
        ).status == 202
        job, terminal = _write_success_files(module, gateway, job_id)
        await _complete_benchmark(module, gateway, processes, job, terminal)
        status = await gateway.lora_get_job(
            _Request(match_info={"job_id": job_id})
        )
        assert _body(status)["state"] == "succeeded"
        assert calls[1][0:3] == (
            str(gateway.lora_python),
            str(gateway.lora_runner.parent / "benchmark.py"),
            job_id,
        )
        response = await gateway.lora_get_evidence(
            _Request(match_info={"job_id": job_id})
        )
        assert response.status == 200
        result = _body(response)
        digest = terminal["adapter"]["sha256"]
        assert result["adapter"] == {
            "sha256": digest,
            "size_bytes": terminal["adapter"]["bytes"],
            "comfy_name": f"identity-lora-{digest}.safetensors",
        }
        assert result["adapter_metadata_sha256"] == terminal["adapter"][
            "metadata_sha256"
        ]
        assert result["training"] == {
            "steps": 500,
            "resolution": 512,
            "rank": 16,
            "seed": 0,
            "batch_size": 1,
            "elapsed_seconds": 12.5,
            "peak_vram_bytes": 1024,
        }
        assert result["benchmark"]["control"]["output_sha256"] == "1" * 64
        assert result["benchmark"]["lora"]["output_sha256"] == "2" * 64
        assert (
            gateway.lora_comfy_root / result["adapter"]["comfy_name"]
        ).is_file()

        from identity.lora_training import LoraTrainingClient, LoraTrainingPlan

        class _EvidenceSession:
            def get(self, *_args, **_kwargs):
                return SimpleNamespace(
                    status_code=response.status,
                    content=response.body,
                    json=lambda: json.loads(response.body),
                )

        client = LoraTrainingClient(
            "http://127.0.0.1:8189", TOKEN, session=_EvidenceSession()
        )
        parsed = client._evidence(
            LoraTrainingPlan(job_id=job_id, manifest=manifest, sources=())
        )
        assert parsed.adapter_sha256 == digest
        assert parsed.adapter_metadata_sha256 == terminal["adapter"][
            "metadata_sha256"
        ]
        assert parsed.elapsed_seconds == 12.5
        assert parsed.peak_vram_bytes == 1024

        ready = await gateway.lora_ready(_Request())
        assert ready.status == 200
        assert _body(ready)["state"] == "ready"
        assert _body(ready)["job_submission_ready"] is True

        other_images = [_png(index) for index in range(5, 9)]
        other_manifest = _manifest(other_images)
        other_job_id = _job_id(module, other_manifest)
        await _upload(gateway, other_images)
        assert (
            await gateway.lora_put_job(
                _json_request(other_manifest, job_id=other_job_id)
            )
        ).status == 202
        assert gateway._lora_watch_task is not None
        gateway._lora_watch_task.cancel()
        await asyncio.gather(gateway._lora_watch_task, return_exceptions=True)
        other_job = gateway._lora_job_dir(other_job_id, required=True)
        other_state = gateway._load_lora_state(other_job)
        other_state["state"] = "unknown"
        other_state["blocker_code"] = "process_state_unknown"
        other_state["completed_at_unix"] = other_state["updated_at_unix"]
        gateway._write_lora_state(other_job, other_state)
        blocked = await gateway.lora_ready(_Request())
        assert blocked.status == 503
        assert _body(blocked)["blocker_code"] == "candidate_outcome_unknown"
        assert _body(blocked)["job_submission_ready"] is False

    asyncio.run(scenario())


def test_package_contract_rejection_prevents_adapter_publish(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_gateway()
    gateway, _processes, _calls = _gateway(tmp_path, module, monkeypatch)
    source = tmp_path / "candidate.safetensors"
    source.write_bytes(_safetensors())
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    metadata = {
        "adapter": {
            "filename": f"identity-lora-{digest}.safetensors",
            "bytes": source.stat().st_size,
            "sha256": digest,
        }
    }

    def reject(*_args, **_kwargs):
        raise ValueError("contract rejection")

    gateway._lora_contract.validate_lora_safetensors = reject
    with pytest.raises(ValueError):
        gateway._publish_lora_adapter(source, metadata)
    assert list(gateway.lora_comfy_root.iterdir()) == []


def test_deterministic_benchmark_preflight_failure_allows_one_explicit_retry(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_gateway()
    gateway, processes, calls = _gateway(tmp_path, module, monkeypatch)
    images = [_png(index) for index in range(1, 5)]
    manifest = _manifest(images)
    job_id = _job_id(module, manifest)

    async def scenario():
        await _upload(gateway, images)
        assert (
            await gateway.lora_put_job(_json_request(manifest, job_id=job_id))
        ).status == 202
        job, _terminal = _write_success_files(module, gateway, job_id)
        processes[0].return_code = 0
        processes[0].done.set()
        for _ in range(20):
            await asyncio.sleep(0)
            if len(processes) == 2:
                break
        assert len(processes) == 2
        processes[1].return_code = 2
        processes[1].done.set()
        for _ in range(20):
            await asyncio.sleep(0)
            if gateway._load_lora_state(job)["state"] != "benchmarking":
                break
        failed = gateway._load_lora_state(job)
        assert failed["state"] == "failed"
        assert failed["retriable"] is True
        assert failed["retry_mode"] == "benchmark"
        assert not (gateway.lora_state_root / "locks" / "gateway-activity.lock").exists()
        failed["attempt_index"] = 2
        gateway._write_lora_state(job, failed)

        response = await gateway.lora_resume_job(
            _Request(body=b"{}", match_info={"job_id": job_id})
        )
        assert response.status == 202
        assert calls[2][0:3] == (
            str(gateway.lora_python),
            str(gateway.lora_runner.parent / "benchmark.py"),
            job_id,
        )
        running = gateway._load_lora_state(job)
        assert running["state"] == "benchmarking"
        assert running["retry_mode"] == "none"
        assert running["retriable"] is False
        replay = await gateway.lora_resume_job(
            _Request(body=b"{}", match_info={"job_id": job_id})
        )
        assert replay.status == 409

    asyncio.run(scenario())


def test_benchmark_unknown_retains_lease_and_never_retries(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_gateway()
    gateway, processes, _calls = _gateway(tmp_path, module, monkeypatch)
    images = [_png(index) for index in range(1, 5)]
    manifest = _manifest(images)
    job_id = _job_id(module, manifest)

    async def scenario():
        await _upload(gateway, images)
        assert (
            await gateway.lora_put_job(_json_request(manifest, job_id=job_id))
        ).status == 202
        job, _terminal = _write_success_files(module, gateway, job_id)
        processes[0].return_code = 0
        processes[0].done.set()
        for _ in range(20):
            await asyncio.sleep(0)
            if len(processes) == 2:
                break
        assert len(processes) == 2
        module._atomic_json(
            job / "evidence" / "inference-benchmark-unknown.json",
            {"state": "unknown"},
        )
        processes[1].return_code = 2
        processes[1].done.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        state = gateway._load_lora_state(job)
        assert state["state"] == "unknown"
        assert state["retriable"] is False
        assert state["retry_mode"] == "none"
        assert (
            gateway.lora_state_root / "locks" / "gateway-activity.lock"
        ).is_file()
        blocked = await gateway.lora_resume_job(
            _Request(body=b"{}", match_info={"job_id": job_id})
        )
        assert blocked.status == 409

    asyncio.run(scenario())


def test_terminal_benchmark_failure_is_reported_as_inference_failure(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_gateway()
    gateway, processes, _calls = _gateway(tmp_path, module, monkeypatch)
    images = [_png(index) for index in range(1, 5)]
    manifest = _manifest(images)
    job_id = _job_id(module, manifest)

    async def scenario():
        await _upload(gateway, images)
        assert (
            await gateway.lora_put_job(_json_request(manifest, job_id=job_id))
        ).status == 202
        job, _terminal = _write_success_files(module, gateway, job_id)
        processes[0].return_code = 0
        processes[0].done.set()
        for _ in range(20):
            await asyncio.sleep(0)
            if len(processes) == 2:
                break
        assert len(processes) == 2
        module._atomic_json(
            job / "evidence" / "inference-benchmark-failed.json",
            {"state": "failed"},
        )
        processes[1].return_code = 2
        processes[1].done.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        state = gateway._load_lora_state(job)
        assert state["state"] == "failed"
        assert state["retriable"] is False
        ready = await gateway.lora_ready(_Request())
        assert ready.status == 503
        assert _body(ready)["blocker_code"] == "candidate_inference_failed"
        assert _body(ready)["job_submission_ready"] is True

    asyncio.run(scenario())
