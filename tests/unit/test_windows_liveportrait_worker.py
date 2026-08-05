from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import base64
from pathlib import Path
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2] / "deploy" / "windows-liveportrait-worker"
MODEL_REVISION = "59f30f36d7b791929c25437df7461d5b0e0010b1"
EXPECTED_MODELS = {
    "appearance_feature_extractor.safetensors": (
        3361936,
        "38bef5de50a92bf1fc66e8c511051a19dfacdf80c37f8713425ec15dc9ca7d34",
    ),
    "motion_extractor.safetensors": (
        112496256,
        "3568cd410e29d046771acb55ecfdfe4c7c197d345bd8b7f95942ef63130b6c9e",
    ),
    "spade_generator.safetensors": (
        221771768,
        "ca04fbec765745e9eae836d2d7522c274647b277ce5f25104fa1705b75222212",
    ),
    "stitching_retargeting_module.safetensors": (
        911836,
        "60725cf3523ae413880da28ed583c9e84c5c25695a0cef1b77210ea31cc424ea",
    ),
    "warping_module.safetensors": (
        182158564,
        "f7b7834bd6039b4088f72e5161e60ad366f68a3763df8a3eac0bc0f9d46fdbbf",
    ),
    "landmark.onnx": (
        114666491,
        "31d22a5041326c31f19b78886939a634a5aedcaa5ab8b9b951a1167595d147db",
    ),
}


def _json(name: str) -> dict:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def _load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_revision_manifest_pins_windows_blackwell_matrix() -> None:
    manifest = _json("revisions.json")
    assert manifest["schema_version"] == 1
    assert manifest["platform"] == {
        "operating_system": "Windows 11",
        "architecture": "AMD64",
        "python": "3.12",
    }
    assert manifest["python_packages"] == {
        "torch": "2.11.0+cu130",
        "torchvision": "0.26.0+cu130",
        "torchaudio": "2.11.0+cu130",
        "numpy": "1.26.4",
        "mediapipe": "0.10.14",
        "onnxruntime": "1.19.2",
        "opencv-contrib-python": "4.11.0.86",
    }
    assert {
        component["id"]: component["commit"] for component in manifest["components"]
    } == {
        "comfyui": "b1693ecba9f5b65f8c80ab36b195ab963ec92413",
        "liveportrait-kj": "4d9dc6205b793ffd0fb319816136d9b8c0dbfdff",
        "video-helper-suite": "4ee72c065db22c9d96c2427954dc69e7b908444b",
    }
    assert manifest["components"][0]["version"] == "0.30.0"
    assert {wheel["sha256"] for wheel in manifest["wheels"]} == {
        "ef8beae16d781c3244ef28dc7bee6d8871c26bbde65d5bf66e902cb61972c4ab",
        "a3578f7c8e8a2724306c68c56873a1675fa7ce45471e18235c720a2ed242fe44",
        "f74949f9ace1e4a6cf9468bdb3211b9cfa0af6ea348125471ac71c8621d6c77d",
    }
    assert all("cp312-cp312-win_amd64.whl" in wheel["url"] for wheel in manifest["wheels"])


def test_model_manifest_is_exact_six_artifact_contract() -> None:
    artifacts = _json("models.json")["artifacts"]
    assert len(artifacts) == 6
    actual = {
        Path(artifact["destination"]).name: (
            artifact["expected_bytes"],
            artifact["sha256"],
        )
        for artifact in artifacts
    }
    assert actual == EXPECTED_MODELS
    for artifact in artifacts:
        filename = Path(artifact["destination"]).name
        assert artifact["destination"] == f"liveportrait/{filename}"
        assert artifact["source"]["revision"] == MODEL_REVISION
        assert f"/resolve/{MODEL_REVISION}/{filename}?download=true" in artifact["source"]["url"]
        assert artifact["license"]["declared_by_distributor"] == "UNDECLARED"
    destinations = "\n".join(artifact["destination"].lower() for artifact in artifacts)
    assert "insightface" not in destinations
    assert "landmark_model.pth" not in destinations


def test_dependency_selection_excludes_noncommercial_and_gpu_onnx_paths() -> None:
    requirements = (ROOT / "requirements.worker.txt").read_text(encoding="utf-8").lower()
    installed_lines = {
        line.strip().split("==", 1)[0]
        for line in requirements.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert "mediapipe" in installed_lines
    assert "onnxruntime" in installed_lines
    assert "insightface" not in installed_lines
    assert "onnxruntime-gpu" not in installed_lines
    lock_lines = [
        line.strip()
        for line in (ROOT / "requirements.lock").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert all("==" in line or " @ " in line for line in lock_lines)
    assert not any(line.startswith(("insightface==", "onnxruntime-gpu==")) for line in lock_lines)
    assert sum(line.startswith("opencv-") for line in lock_lines) == 1
    assert "opencv-contrib-python==4.11.0.86" in lock_lines


def test_powershell_network_and_secret_invariants() -> None:
    scripts = {
        path.name: path.read_text(encoding="utf-8") for path in ROOT.glob("*.ps1")
    }
    assert scripts
    assert all("0.0.0.0" not in content for content in scripts.values())

    start = scripts["Start-Worker.ps1"]
    assert '"--listen", "127.0.0.1"' in start
    assert '"--port", "8188"' in start
    assert '"--port", "8189"' in start
    assert '"--upstream", "http://127.0.0.1:8188"' in start
    assert '"COMFYUI_API_KEY" = $plainToken' in start
    assert "Remove-Item -LiteralPath $sentinel" in start
    assert '"--user-directory", $userRoot' in start
    assert '"PYTHONDONTWRITEBYTECODE" = "1"' in start
    assert start.count('"PYTHONDONTWRITEBYTECODE" = "1"') == 2
    assert '& $python "-B" @preflightArguments' in start
    assert '& $python "-B" `' in start
    assert '"HF_HOME" = (Join-Path $cacheRoot "huggingface")' in start
    assert "Start-Process" in start
    assert "RedirectStandardOutput" in start
    assert "RedirectStandardError" in start
    assert "BeginOutputReadLine" not in start
    assert "add_OutputDataReceived" not in start
    assert "Stop-LoggedProcess" in start
    assert "CreateJobObject" in start
    assert "SetInformationJobObject" in start
    assert "JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE" in start
    assert "AssignProcessToJobObject" in start
    assert "CreateKillOnCloseJob" in start
    assert "AssignProcess" in start
    assert "$workerJob.Dispose()" in start
    assert start.index("AssignProcess") < start.index("return $process")
    assert "EventWaitHandle" in start
    assert "-EncodedCommand" in start
    assert "$readyGate.WaitOne(10000)" in start
    assert "$launchGate.Set()" in start
    assert start.index("[ContentWorkerJob]::AssignProcess") < start.index(
        "$readyGate.WaitOne(10000)"
    )
    assert start.index("$readyGate.WaitOne(10000)") < start.index("$launchGate.Set()")
    assert "exited during startup with code" in start
    assert "last-preflight.json" in start
    assert '"--comfy-url" "http://127.0.0.1:8188"' in start
    assert '"--worker-supervisor-pid" $comfyProcess.Id' in start
    assert "PreflightOnly and Benchmark are mutually exclusive" in start
    assert '$comfyArguments += "--cache-none"' in start
    assert '"http://127.0.0.1:8188/free"' in start
    assert '"unload_models":true' in start

    test_worker = scripts["Test-Worker.ps1"]
    assert "WORKER_PREFLIGHT_PASSED" in test_worker
    assert "WORKER_PREFLIGHT_FAILED" in test_worker
    assert "execution_canary.state" in test_worker
    assert "exit 0" in test_worker and "exit 1" in test_worker

    benchmark_worker = scripts["Benchmark-Worker.ps1"]
    assert "schema_version -ne 3" in benchmark_worker
    assert "frame_count -ne 200" in benchmark_worker
    assert "clip_seconds -ne 8" in benchmark_worker
    assert "measured_jobs -ne 10" in benchmark_worker
    assert "max_concurrency -ne 1" in benchmark_worker
    assert 'comfy_cache_mode -ne "none"' in benchmark_worker
    assert "restart_recovery" in benchmark_worker
    assert "-PreflightOnly" in benchmark_worker
    assert '& $python "-B" $normalizer' in benchmark_worker

    benchmark = (ROOT / "benchmark.py").read_text(encoding="utf-8")
    assert "MEASURED_JOBS = 10" in benchmark
    assert "CLIP_SECONDS = 8" in benchmark
    assert "FRAME_COUNT = FRAME_RATE * CLIP_SECONDS" in benchmark
    assert "validate_video_container" in benchmark
    assert "assert_queue_idle" in benchmark
    assert '"p95_inclusive"' in benchmark
    assert '"peak_vram_mib"' in benchmark
    assert '"comfy_cache_mode": "none"' in benchmark
    assert '"hardware": hardware_identity()' in benchmark
    assert 'run_prefix = f"worker-benchmark-{uuid.uuid4().hex}"' in benchmark
    assert "cleanup_owned_outputs(output_root, run_prefix)" in benchmark

    secret = scripts["Set-WorkerSecret.ps1"]
    assert "Read-Host" in secret and "-AsSecureString" in secret
    assert "ConvertFrom-SecureString" in secret
    assert "SetAccessRuleProtection($true, $false)" in secret
    assert "ConvertFrom-SecureString -Key" not in secret
    assert "ConvertFrom-SecureString -SecureKey" not in secret

    register = scripts["Register-WorkerTask.ps1"]
    assert "-RemoteAddress $MacIPAddress" in register
    assert "-LocalPort 22" in register
    assert "8188" not in register and "8189" not in register
    assert "New-ScheduledTaskTrigger -AtLogOn" in register
    assert "-RunLevel Limited" in register
    assert "-MultipleInstances IgnoreNew" in register
    assert "Disable-NetFirewallRule" not in register
    assert "will not mutate non-package firewall rules" in register
    assert "-PolicyStore ActiveStore" in register
    assert '$value -eq "Any"' in register
    assert '$value -match "^(\\d+)-(\\d+)$"' in register
    assert "Test-RuleExactlyAllowsMacSsh" in register
    assert "Test-RuleCouldApplyToSshd" in register
    assert "Test-Rfc1918IPv4" in register
    assert "$octets[0] -eq 10" in register
    assert "$octets[0] -eq 172" in register
    assert "$octets[0] -eq 192" in register
    assert "Get-NetFirewallApplicationFilter" in register
    assert "Get-NetFirewallServiceFilter" in register
    assert '\\OpenSSH\\sshd.exe' in register
    assert "$Rule.Owner" in register
    assert "Start-Worker.ps1" in register
    assert "-PreflightOnly" in register
    assert "last-preflight.json" in register
    assert "Test-Worker.ps1" not in register
    assert register.index("Get-NetFirewallRule") < register.index("-PreflightOnly")
    assert "$firewallCreated" in register
    assert "if ($firewallCreated)" in register
    assert "Remove-NetFirewallRule" in register


def _valid_benchmark_evidence() -> dict:
    probe = _json("probes/probe.json")
    revisions = _json("revisions.json")
    package_paths = {
        "benchmark_instrument_sha256": ROOT / "benchmark.py",
        "benchmark_normalizer_sha256": ROOT / "normalize_benchmark.py",
        "benchmark_launcher_sha256": ROOT / "Benchmark-Worker.ps1",
        "worker_supervisor_sha256": ROOT / "Start-Worker.ps1",
        "preflight_instrument_sha256": ROOT / "preflight.py",
        "models_manifest_sha256": ROOT / "models.json",
        "revisions_manifest_sha256": ROOT / "revisions.json",
        "requirements_lock_sha256": ROOT / "requirements.lock",
        "probe_contract_sha256": ROOT / "probes" / "probe.json",
        "workflow_base_sha256": ROOT / "probes" / probe["workflow"],
    }
    binding = {
        key: hashlib.sha256(path.read_bytes()).hexdigest()
        for key, path in package_paths.items()
    }
    binding["source_revisions"] = {
        component["id"]: component["commit"] for component in revisions["components"]
    }
    binding["package_contract_sha256"] = hashlib.sha256(
        json.dumps(binding, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    elapsed = [float(value) for value in range(1, 11)]
    return {
        "schema_version": 3,
        "status": "passed",
        "role": "performance-liveportrait",
        "started_at_unix": 1,
        "completed_at_unix": 2,
        "frame_count": 200,
        "frame_rate": 25,
        "clip_seconds": 8.0,
        "warmup_jobs": 1,
        "measured_jobs": 10,
        "max_concurrency": 1,
        "comfy_cache_mode": "none",
        "all_outputs_decoded": True,
        "workflow_base_sha256": binding["workflow_base_sha256"],
        "driver_sha256": "b" * 64,
        "hardware": {
            "gpu": "Test GPU",
            "vram_total_mib": 16000,
            "cpu": "Test CPU",
            "system_ram_bytes": 64000000000,
            "operating_system": "Windows-11",
        },
        "runtime": {
            "python": "3.12.10",
            "python_executable": "D:/worker/python.exe",
            "torch": "2.11.0+cu130",
            "pyav": "18.0.0",
            "psutil": "7.2.2",
            **binding,
            "driver_sha256": "b" * 64,
        },
        "warmup": {
            "label": "warmup",
            "decoded_frames": 200,
            "elapsed_seconds": 1.0,
            "output_bytes": 2000,
            "output_sha256": "c" * 64,
        },
        "jobs": [
            {
                "label": f"measured-{index:02d}",
                "decoded_frames": 200,
                "elapsed_seconds": elapsed[index - 1],
                "output_bytes": 2000 + index,
                "output_sha256": f"{index:064x}",
            }
            for index in range(1, 11)
        ],
        "latency_seconds": {
            "minimum": 1.0,
            "maximum": 10.0,
            "mean": 5.5,
            "p50": 5.5,
            "p95_inclusive": 9.55,
        },
        "resources": {
            "target_sample_interval_seconds": 0.25,
            "max_accepted_sample_interval_seconds": 3.0,
            "sample_count": 241,
            "sample_offsets_seconds": [value * 0.25 for value in range(241)],
            "sampling_elapsed_seconds": 60.0,
            "observed_sample_interval_seconds": {
                "minimum": 0.25,
                "maximum": 0.25,
                "mean": 0.25,
                "p50": 0.25,
                "p95_inclusive": 0.25,
            },
            "baseline_vram_mib": 1000,
            "peak_vram_mib": 3000,
            "delta_vram_mib": 2000,
            "baseline_worker_rss_bytes": 100,
            "peak_worker_rss_bytes": 300,
            "delta_worker_rss_bytes": 200,
            "baseline_system_ram_bytes": 1000,
            "peak_system_ram_bytes": 1500,
            "delta_system_ram_bytes": 500,
        },
        "restart_recovery": {"state": "passed", "checked_at_unix": 3},
    }


def test_benchmark_normalizer_recomputes_and_binds_raw_evidence() -> None:
    normalizer = _load_module(
        "windows_liveportrait_benchmark_normalizer",
        "normalize_benchmark.py",
    )
    evidence = _valid_benchmark_evidence()
    evidence["hardware"]["unexpected_private_note"] = "do-not-publish"
    evidence["runtime"]["api_key"] = "do-not-publish"
    evidence["resources"]["unexpected_sampler_detail"] = "do-not-publish"
    raw = json.dumps(evidence).encode("utf-8")
    normalized = normalizer.normalize(raw)

    assert normalized["raw_evidence_sha256"] == hashlib.sha256(raw).hexdigest()
    assert normalized["schema_version"] == 2
    assert normalized["workload"]["clip_seconds"] == 8.0
    assert normalized["latency_seconds"]["p95_inclusive"] == 9.55
    assert normalized["decision"]["queue_concurrency"] == 1
    assert "python_executable" not in normalized["runtime"]
    assert "unexpected_private_note" not in normalized["hardware"]
    assert "api_key" not in normalized["runtime"]
    assert "unexpected_sampler_detail" not in normalized["resources"]


def test_benchmark_normalizer_rejects_replayed_or_inconsistent_measurements() -> None:
    normalizer = _load_module(
        "windows_liveportrait_benchmark_normalizer_reject",
        "normalize_benchmark.py",
    )
    raw = _valid_benchmark_evidence()
    raw["jobs"][2]["decoded_frames"] = 50
    try:
        normalizer.normalize(json.dumps(raw).encode("utf-8"))
    except normalizer.EvidenceError as exc:
        assert "did not decode every frame" in str(exc)
    else:
        raise AssertionError("incomplete 8-second output was accepted as benchmark evidence")


def test_benchmark_normalizer_rejects_non_finite_or_unbound_measurements() -> None:
    normalizer = _load_module(
        "windows_liveportrait_benchmark_normalizer_finite",
        "normalize_benchmark.py",
    )
    corruptions = (
        lambda raw: raw["jobs"][0].__setitem__("elapsed_seconds", float("nan")),
        lambda raw: raw["resources"].__setitem__("peak_vram_mib", float("inf")),
        lambda raw: raw.__setitem__("workflow_base_sha256", "f" * 64),
        lambda raw: raw["runtime"].__setitem__(
            "benchmark_instrument_sha256", "f" * 64
        ),
        lambda raw: raw["runtime"].__setitem__(
            "benchmark_launcher_sha256", "f" * 64
        ),
        lambda raw: raw["runtime"].__setitem__(
            "worker_supervisor_sha256", "f" * 64
        ),
        lambda raw: raw["runtime"].__setitem__(
            "preflight_instrument_sha256", "f" * 64
        ),
        lambda raw: raw["resources"].__setitem__(
            "baseline_worker_rss_bytes", 0
        ),
        lambda raw: raw["resources"].__setitem__("peak_worker_rss_bytes", 0),
    )
    for corrupt in corruptions:
        raw = _valid_benchmark_evidence()
        corrupt(raw)
        try:
            normalizer.normalize(json.dumps(raw).encode("utf-8"))
        except normalizer.EvidenceError:
            pass
        else:
            raise AssertionError("non-finite or unbound benchmark evidence was accepted")


def test_benchmark_worker_rss_is_bound_to_the_exact_comfyui_pid(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "av", SimpleNamespace(__version__="test"))
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(__version__="test"))
    monkeypatch.setitem(
        sys.modules,
        "psutil",
        SimpleNamespace(
            __version__="test",
            AccessDenied=type("AccessDenied", (Exception,), {}),
            NoSuchProcess=type("NoSuchProcess", (Exception,), {}),
            ZombieProcess=type("ZombieProcess", (Exception,), {}),
        ),
    )
    worker_preflight = _load_module(
        "windows_liveportrait_benchmark_worker_preflight",
        "preflight.py",
    )
    monkeypatch.setitem(sys.modules, "preflight", worker_preflight)
    benchmark = _load_module(
        "windows_liveportrait_benchmark_worker_rss",
        "benchmark.py",
    )
    comfy_root = Path("C:/worker/sources/ComfyUI")

    class Memory:
        def __init__(self, rss: int) -> None:
            self.rss = rss

    class Process:
        def __init__(
            self,
            pid: int,
            command: list[str],
            rss: int,
            children: list["Process"] | None = None,
            executable: str | None = None,
        ) -> None:
            self.pid = pid
            self._command = command
            self._rss = rss
            self._children = children or []
            self._executable = executable or sys.executable

        def cmdline(self) -> list[str]:
            return self._command

        def children(self, *, recursive: bool) -> list["Process"]:
            assert recursive is True
            return self._children

        def exe(self) -> str:
            return self._executable

        def memory_info(self) -> Memory:
            return Memory(self._rss)

    expected_main = str((comfy_root / "main.py").resolve())
    helper = Process(44, ["python", "helper.py"], 200)
    worker = Process(43, [sys.executable, expected_main], 100, [helper])
    supervisor = Process(42, ["powershell", "-EncodedCommand", "..."], 50, [worker])
    monkeypatch.setattr(
        benchmark.psutil,
        "Process",
        lambda pid: supervisor,
        raising=False,
    )
    assert benchmark.worker_rss_bytes(42, comfy_root, Path(sys.executable)) == 300

    wrong = Process(99, ["python", "C:/other/main.py"], 500)
    wrong_supervisor = Process(98, ["powershell"], 50, [wrong])
    monkeypatch.setattr(benchmark.psutil, "Process", lambda pid: wrong_supervisor)
    try:
        benchmark.worker_rss_bytes(98, comfy_root, Path(sys.executable))
    except benchmark.PreflightError as exc:
        assert "exactly one expected ComfyUI process" in str(exc)
    else:
        raise AssertionError("an unrelated process was accepted as the worker RSS source")


def test_benchmark_normalizer_rejects_sparse_resource_sampling() -> None:
    normalizer = _load_module(
        "windows_liveportrait_benchmark_normalizer_sparse",
        "normalize_benchmark.py",
    )
    raw = _valid_benchmark_evidence()
    offsets = [float(value * 4) for value in range(16)]
    raw["resources"].update(
        {
            "sample_count": len(offsets),
            "sample_offsets_seconds": offsets,
            "sampling_elapsed_seconds": offsets[-1],
            "observed_sample_interval_seconds": {
                "minimum": 4.0,
                "maximum": 4.0,
                "mean": 4.0,
                "p50": 4.0,
                "p95_inclusive": 4.0,
            },
        }
    )
    try:
        normalizer.normalize(json.dumps(raw).encode("utf-8"))
    except normalizer.EvidenceError as exc:
        assert "unobserved gap" in str(exc)
    else:
        raise AssertionError("a four-second blind spot was accepted as resource evidence")


def test_mac_tunnel_launch_agent_is_loopback_supervised_and_fail_closed() -> None:
    installer = _load_module(
        "windows_liveportrait_mac_tunnel",
        "install_mac_tunnel.py",
    )
    arguments = installer._ssh_arguments(
        windows_host="192.0.2.16",
        windows_user="worker",
        identity_file=Path("/private/worker-key"),
        known_hosts=Path("/private/known_hosts"),
        local_port=18189,
        remote_port=8189,
    )
    payload = installer._plist_payload(
        label=installer.DEFAULT_LABEL,
        arguments=arguments,
        home=Path("/Users/worker"),
        log_directory=Path("/Users/worker/.local/state/content/tunnel"),
    )

    joined = " ".join(arguments)
    assert arguments[1:3] == ["-F", "/dev/null"]
    assert "127.0.0.1:18189:127.0.0.1:8189" in joined
    for required in (
        "BatchMode=yes",
        "IdentitiesOnly=yes",
        "ExitOnForwardFailure=yes",
        "ServerAliveInterval=15",
        "ServerAliveCountMax=3",
        "StrictHostKeyChecking=yes",
        "GatewayPorts=no",
    ):
        assert required in joined
    assert payload["RunAtLoad"] is True
    assert payload["KeepAlive"] == {"NetworkState": True, "SuccessfulExit": False}
    assert payload["ThrottleInterval"] == 10


def test_mac_tunnel_refuses_public_or_loopback_windows_addresses() -> None:
    installer = _load_module(
        "windows_liveportrait_mac_tunnel_addresses",
        "install_mac_tunnel.py",
    )
    for address in (
        "0.0.0.0",
        "127.0.0.1",
        "192.0.2.1",
        "198.51.100.1",
        "203.0.113.1",
        "255.255.255.255",
        "8.8.8.8",
        "fe80::1",
        "worker.example.com",
    ):
        try:
            installer._private_ipv4(address)
        except installer.TunnelInstallError:
            pass
        else:
            raise AssertionError(f"unsafe Windows address accepted: {address}")


def test_install_is_verified_and_does_not_start_or_register() -> None:
    installer = (ROOT / "Install-Worker.ps1").read_text(encoding="utf-8")
    assert "Get-FileHash" in installer
    assert "expected_bytes" in installer and "sha256" in installer
    assert "pip" in installer and "check" in installer
    assert "Start-Worker.ps1 -" not in installer
    assert "Register-ScheduledTask" not in installer
    assert "New-NetFirewallRule" not in installer
    assert "Install-ProbeAssets" in installer
    assert "FromBase64String" in installer
    assert "--untracked-files=all" in installer
    assert "--untracked-files=no" not in installer
    assert "status --ignored --porcelain --untracked-files=all" in installer
    assert "LivePortrait model inventory contains unexpected or missing files" in installer
    assert "$freshClone = $false" in installer
    assert "if (-not $freshClone)" in installer
    assert installer.count("Assert-PinnedRepositoryClean -Component $Component") == 2
    assert "Install-ExactPackage" in installer
    assert "Get-ExactPackageInventory" in installer
    assert "package-stage-$identifier" in installer
    assert "package-backup-$identifier" in installer
    assert "Staged worker package differs from source" in installer
    assert 'Where-Object { $_.Name -ne "__pycache__" }' not in installer
    assert "Remove-PythonBytecode" in installer
    for exact_flux_model in (
        "!! models/diffusion_models/flux-2-klein-4b-fp8.safetensors",
        "!! models/text_encoders/qwen_3_4b.safetensors",
        "!! models/vae/flux2-klein-vae-bf16.safetensors",
    ):
        assert exact_flux_model in installer
    assert 'StartsWith("!! models/diffusion_models/")' not in installer
    assert 'StartsWith("!! models/text_encoders/")' not in installer
    assert 'StartsWith("!! models/vae/")' not in installer


def test_tracked_probe_matches_runtime_builder_and_fixture_contract() -> None:
    from performance.live_portrait_workflow import build_live_portrait_workflow

    contract = _json("probes/probe.json")
    workflow_path = ROOT / "probes" / contract["workflow"]
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    assert workflow == build_live_portrait_workflow(
        "source-face.jpg", "driving-expression.mp4", 1 / 25
    )
    assert hashlib.sha256(workflow_path.read_bytes()).hexdigest() == contract["workflow_sha256"]
    assert workflow["10"]["inputs"]["image"] == contract["fixtures"][0]["path"]
    assert workflow["11"]["inputs"]["video"] == contract["fixtures"][1]["path"]
    assert workflow["11"]["inputs"]["frame_load_cap"] == 1
    assert contract["output_node_ids"] == ["19"]

    preflight_module = _load_module("windows_liveportrait_topology", "preflight.py")
    assert preflight_module.upstream_node_ids(workflow, "19") == set(workflow)
    assert workflow["19"]["class_type"] == "VHS_VideoCombine"

    provenance = _json("fixtures/provenance.json")
    assert provenance["source"]["sha256"] == (
        "97471b9377c817251c86dbb58982464d7586b6b3d800936683f900da668c0fb6"
    )
    source_asset = ROOT.parents[1] / provenance["source"]["repository_path"]
    assert hashlib.sha256(source_asset.read_bytes()).hexdigest() == provenance["source"]["sha256"]
    for fixture in contract["fixtures"]:
        payload = ROOT / "fixtures" / f"{fixture['path']}.b64"
        decoded = base64.b64decode(payload.read_text(encoding="ascii"), validate=False)
        assert len(decoded) == fixture["expected_bytes"]
        assert hashlib.sha256(decoded).hexdigest() == fixture["sha256"]
        if fixture["path"].endswith(".jpg"):
            assert decoded.startswith(b"\xff\xd8\xff") and decoded.endswith(b"\xff\xd9")
        else:
            assert decoded[4:8] == b"ftyp"
            assert b"moov" in decoded and b"mdat" in decoded

    preflight = (ROOT / "preflight.py").read_text(encoding="utf-8")
    assert 'inputs.get("frame_load_cap") == 1' in preflight
    assert 'inputs.get("landmarkrunner_onnx_device") != "CPU"' in preflight
    assert '"LivePortraitLoadCropper"' in preflight
    assert '"LivePortraitLoadMediaPipeCropper"' in preflight
    assert 'payload={"prompt": graph' in preflight
    assert 'prefix = f"content-worker-preflight-{uuid.uuid4().hex}"' in preflight
    assert "cleanup_owned_outputs(output_root, prefix)" in preflight
    assert 'cv2.__version__ != "4.11.0"' in preflight
    assert '"opencv-python-headless"' in preflight
    assert "upstream_node_ids(workflow, \"19\")" in preflight
    assert "validate_video_container(artifact, expected_frames=1)" in preflight
    assert '"--ignored"' in preflight and '"--untracked-files=all"' in preflight
    assert "--untracked-files=no" not in preflight
    assert "actual_paths != expected_paths" in preflight


def test_probe_output_cleanup_is_uuid_scoped_and_preserves_unrelated_files(
    tmp_path: Path,
) -> None:
    preflight = _load_module("windows_liveportrait_output_cleanup", "preflight.py")
    output_root = tmp_path / "output"
    nested = output_root / "nested"
    nested.mkdir(parents=True)
    prefix = "content-worker-preflight-0123456789abcdef"
    owned_video = output_root / f"{prefix}_00001.mp4"
    owned_sidecar = nested / f"{prefix}_00001.png"
    unrelated = output_root / "client-project-output.mp4"
    for path in (owned_video, owned_sidecar, unrelated):
        path.write_bytes(b"fixture")

    preflight.cleanup_owned_outputs(output_root, prefix)

    assert not owned_video.exists()
    assert not owned_sidecar.exists()
    assert unrelated.read_bytes() == b"fixture"


def test_expression_probe_submits_a_copy_and_cleans_media_sidecars(
    monkeypatch,
    tmp_path: Path,
) -> None:
    preflight = _load_module("windows_liveportrait_probe_cleanup", "preflight.py")
    output_root = tmp_path / "output"
    output_root.mkdir()
    unrelated = output_root / "client-output.mp4"
    unrelated.write_bytes(b"preserve")
    workflow = {"19": {"inputs": {"filename_prefix": "tracked-prefix"}}}
    submitted_prefix = ""

    def fake_api(_base_url, path, *, method="GET", payload=None, timeout=15):
        nonlocal submitted_prefix
        if path == "/prompt":
            assert method == "POST"
            submitted_prefix = payload["prompt"]["19"]["inputs"][
                "filename_prefix"
            ]
            (output_root / f"{submitted_prefix}_00001.mp4").write_bytes(b"video")
            (output_root / f"{submitted_prefix}_00001.png").write_bytes(b"sidecar")
            return {"prompt_id": "prompt-1"}
        assert path == "/history/prompt-1"
        return {
            "prompt-1": {
                "status": {"completed": True},
                "outputs": {
                    "19": {
                        "gifs": [
                            {
                                "filename": f"{submitted_prefix}_00001.mp4",
                                "subfolder": "",
                            }
                        ]
                    }
                },
            }
        }

    monkeypatch.setattr(preflight, "api_json", fake_api)
    monkeypatch.setattr(preflight, "validate_video_container", lambda *_a, **_k: None)

    assert preflight.execute_probe(
        "http://127.0.0.1:8188",
        workflow,
        ["19"],
        output_root,
    ) == "prompt-1"
    assert workflow["19"]["inputs"]["filename_prefix"] == "tracked-prefix"
    assert submitted_prefix.startswith("content-worker-preflight-")
    assert not list(output_root.glob(f"{submitted_prefix}*"))
    assert unrelated.read_bytes() == b"preserve"


def test_probe_output_cleanup_refuses_links(tmp_path: Path) -> None:
    preflight = _load_module("windows_liveportrait_output_link", "preflight.py")
    output_root = tmp_path / "output"
    output_root.mkdir()
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"fixture")
    linked = output_root / "content-worker-preflight-linked.mp4"
    linked.symlink_to(outside)

    try:
        preflight.cleanup_owned_outputs(
            output_root, "content-worker-preflight-linked"
        )
    except preflight.PreflightError as exc:
        assert "linked worker output" in str(exc)
    else:
        raise AssertionError("linked output was accepted for cleanup")
    assert outside.read_bytes() == b"fixture"


def test_gateway_rejects_stale_or_unproven_sentinel(tmp_path: Path) -> None:
    gateway_module = _load_module("windows_liveportrait_gateway", "gateway.py")
    from performance.worker_readiness import expected_flux2_worker_contract

    assert gateway_module.FLUX2_PACKAGE_FIELDS == (
        expected_flux2_worker_contract().gateway_fields()
    )
    revisions = tmp_path / "revisions.json"
    models = tmp_path / "models.json"
    probes = tmp_path / "probes"
    probes.mkdir()
    workflow = probes / "workflow.json"
    contract = probes / "probe.json"
    sentinel = tmp_path / "ready.json"
    revisions.write_text("{}\n", encoding="utf-8")
    models.write_text("{}\n", encoding="utf-8")
    workflow.write_text('{"1":{"class_type":"LoadImage","inputs":{}}}\n', encoding="utf-8")
    workflow_hash = hashlib.sha256(workflow.read_bytes()).hexdigest()
    contract.write_text(
        json.dumps({"workflow": "workflow.json", "workflow_sha256": workflow_hash}),
        encoding="utf-8",
    )

    worker = gateway_module.AuthenticatedGateway(
        upstream="http://127.0.0.1:8188",
        token="a" * 32,
        sentinel=sentinel,
        revisions=revisions,
        models=models,
        probe_contract=contract,
    )
    expected = worker._expected_contract()
    assert expected is not None
    ready = {
        "status": "ready",
        "role": "performance-liveportrait",
        "startup_ready": True,
        "execution_proven": True,
        "execution_canary": {"state": "passed"},
        **expected,
    }
    sentinel.write_text(json.dumps(ready), encoding="utf-8")
    assert worker._ready_record() == ready
    assert worker._capability_record() == {
        "schema_version": 1,
        "status": "partial",
        "capabilities": {
            "performance-liveportrait": {
                "role": "performance-liveportrait",
                "status": "ready",
                "startup_ready": True,
                "execution_proven": True,
                "execution_canary_state": "passed",
                "workflow_sha256": ready["workflow_sha256"],
                "model_manifest_sha256": ready["model_manifest_sha256"],
                "revisions_manifest_sha256": ready["revisions_manifest_sha256"],
                "contract_digest": ready["contract_digest"],
            },
            "image-flux2-klein": {
                **gateway_module.FLUX2_PACKAGE_FIELDS,
                "state": "not_installed",
                "startup_ready": False,
                "execution_proven": False,
                "benchmark_state": "not_run",
                "blocker_code": "candidate_artifacts_not_installed",
                "artifacts_installed": False,
                "runtime_contract_sha256": "",
                "license_review_state": "official_sources_selected_derivation_pending",
                "execution_canary_state": "not_run",
                "execution_canary_sha256": "",
                "benchmark_sha256": "",
            },
        },
    }

    state_root = tmp_path / "flux2-state"
    evidence_root = state_root / "evidence"
    evidence_root.mkdir(parents=True)

    def write_evidence(name: str, payload: dict) -> dict:
        path = evidence_root / f"{name}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        record = {
            "path": str(path.relative_to(state_root)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "run_id": str(payload.get("run_id") or payload.get("benchmark_id")),
            "status": payload["status"],
        }
        return record

    install = write_evidence("install", {
        "capability": "image-flux2-klein",
        "status": "installed_needs_execution_probe",
        "run_id": "install-1",
    })
    canary_payload = {
        "capability": "image-flux2-klein",
        "status": "fixed_probe_passed",
        "run_id": "canary-1",
        "workflow_sha256": "d" * 64,
        "runtime_contract_sha256": "f" * 64,
        "output": {"sha256": "e" * 64},
    }
    canary = write_evidence("canary", canary_payload)
    canary.update(
        workflow_sha256=canary_payload["workflow_sha256"],
        output_sha256=canary_payload["output"]["sha256"],
    )
    benchmark = write_evidence("benchmark", {
        "capability": "image-flux2-klein",
        "status": "benchmark_passed",
        "benchmark_id": "benchmark-1",
        "runtime_contract_sha256": "f" * 64,
        "probe_evidence_sha256": canary["sha256"],
        "sequence": [1, 2, 10],
        "benchmark_state": "passed",
    })
    status_path = state_root / "status.json"
    status_path.write_text(json.dumps({
        "schema_version": 1,
        "capability": "image-flux2-klein",
        "state": "ready",
        "startup_ready": True,
        "execution_proven": True,
        "benchmark_state": "passed",
        "blocker_code": None,
        "artifacts_installed": True,
        "license_review_state": "official_source_derivation_verified",
        "runtime_contract_sha256": "f" * 64,
        "artifact_manifest_sha256": gateway_module.FLUX2_PACKAGE_FIELDS[
            "model_manifest_sha256"
        ],
        "workflow_contract_sha256": gateway_module.FLUX2_PACKAGE_FIELDS[
            "workflow_sha256"
        ],
        "updated_at": "2026-08-06T00:00:00Z",
        "evidence": {
            "install": install,
            "canary": canary,
            "benchmark": benchmark,
        },
    }), encoding="utf-8")
    worker.flux2_state_root = state_root
    assert worker._capability_record()["capabilities"]["image-flux2-klein"][
        "state"
    ] == "ready"

    (evidence_root / "canary.json").write_text("{}", encoding="utf-8")
    blocked = worker._capability_record()["capabilities"]["image-flux2-klein"]
    assert blocked["state"] == "blocked"
    assert blocked["blocker_code"] == "candidate_status_evidence_invalid"

    for field, bad_value in (
        ("role", "image-worker"),
        ("execution_proven", False),
        ("workflow_sha256", "0" * 64),
        ("contract_digest", "0" * 64),
    ):
        altered = {**ready, field: bad_value}
        sentinel.write_text(json.dumps(altered), encoding="utf-8")
        assert worker._ready_record() is None
        assert worker._capability_record() is None


def test_unified_capability_route_requires_bearer_authentication(tmp_path: Path) -> None:
    gateway_module = _load_module("windows_liveportrait_capability_auth", "gateway.py")
    revisions = tmp_path / "revisions.json"
    models = tmp_path / "models.json"
    probes = tmp_path / "probes"
    probes.mkdir()
    workflow = probes / "workflow.json"
    contract = probes / "probe.json"
    sentinel = tmp_path / "ready.json"
    revisions.write_text("{}\n", encoding="utf-8")
    models.write_text("{}\n", encoding="utf-8")
    workflow.write_text('{"1":{"class_type":"LoadImage","inputs":{}}}\n', encoding="utf-8")
    workflow_hash = hashlib.sha256(workflow.read_bytes()).hexdigest()
    contract.write_text(
        json.dumps({"workflow": "workflow.json", "workflow_sha256": workflow_hash}),
        encoding="utf-8",
    )
    worker = gateway_module.AuthenticatedGateway(
        upstream="http://127.0.0.1:8188",
        token="a" * 32,
        sentinel=sentinel,
        revisions=revisions,
        models=models,
        probe_contract=contract,
    )
    expected = worker._expected_contract()
    assert expected is not None
    sentinel.write_text(
        json.dumps({
            "status": "ready",
            "role": "performance-liveportrait",
            "startup_ready": True,
            "execution_proven": True,
            "execution_canary": {"state": "passed"},
            **expected,
        }),
        encoding="utf-8",
    )
    calls = []

    async def handler(request):
        calls.append(request.path)
        return object()

    unauthorized = SimpleNamespace(
        path="/api/capabilities/ready",
        headers={},
    )
    response = asyncio.run(worker.access_control(unauthorized, handler))
    assert response.status == 401
    assert calls == []

    authorized = SimpleNamespace(
        path="/api/capabilities/ready",
        headers={"Authorization": f"Bearer {'a' * 32}"},
    )
    marker = asyncio.run(worker.access_control(authorized, handler))
    assert marker is not None
    assert calls == ["/api/capabilities/ready"]

    legacy_health = SimpleNamespace(path="/health/ready", headers={})
    asyncio.run(worker.access_control(legacy_health, handler))
    assert calls[-1] == "/health/ready"

    class BackendResponse:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def json(self):
            return {"system": {"os": "nt"}}

    class BackendSession:
        def get(self, url):
            assert url == "http://127.0.0.1:8188/system_stats"
            return BackendResponse()

    worker.session = BackendSession()
    capability_response = asyncio.run(worker.capabilities_ready(authorized))
    capability_payload = json.loads(capability_response.body)
    assert capability_response.status == 200
    assert set(capability_payload["capabilities"]) == {
        "performance-liveportrait", "image-flux2-klein"
    }
    legacy_response = asyncio.run(worker.ready(legacy_health))
    legacy_payload = json.loads(legacy_response.body)
    assert legacy_response.status == 200
    assert legacy_payload["status"] == "ready"
    assert "capabilities" not in legacy_payload

    app = gateway_module.create_app(worker)
    registered = {
        route.resource.canonical for route in app.router.routes()
    }
    assert "/api/capabilities/ready" in registered


def test_sentinel_contract_digest_is_canonical_and_role_bound(tmp_path: Path) -> None:
    preflight = _load_module("windows_liveportrait_preflight", "preflight.py")
    revisions = tmp_path / "revisions.json"
    models = tmp_path / "models.json"
    workflow = tmp_path / "workflow.json"
    sentinel = tmp_path / "ready.json"
    for path, content in (
        (revisions, b"revisions\n"),
        (models, b"models\n"),
        (workflow, b"workflow\n"),
    ):
        path.write_bytes(content)
    preflight.write_sentinel(
        sentinel,
        gpu_name="test gpu",
        prompt_id="prompt-1",
        revisions_path=revisions,
        models_path=models,
        workflow_path=workflow,
    )
    payload = json.loads(sentinel.read_text(encoding="utf-8"))
    contract = {
        "model_manifest_sha256": hashlib.sha256(b"models\n").hexdigest(),
        "revisions_manifest_sha256": hashlib.sha256(b"revisions\n").hexdigest(),
        "role": "performance-liveportrait",
        "workflow_sha256": hashlib.sha256(b"workflow\n").hexdigest(),
    }
    expected_digest = hashlib.sha256(
        json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert payload["contract_digest"] == expected_digest
    assert payload["startup_ready"] is True
    assert payload["execution_proven"] is True
    assert payload["execution_canary"]["state"] == "passed"


def test_source_status_allowlist_rejects_ignored_executable_and_config() -> None:
    preflight = _load_module("windows_liveportrait_source_status", "preflight.py")
    allowed_nested = {
        "custom_nodes/ComfyUI-LivePortraitKJ",
        "custom_nodes/ComfyUI-VideoHelperSuite",
    }
    status = [
        "!! custom_nodes/ComfyUI-LivePortraitKJ/",
        "!! custom_nodes/ComfyUI-VideoHelperSuite/",
        "!! models/liveportrait/landmark.onnx",
        "!! models/diffusion_models/flux-2-klein-4b-fp8.safetensors",
        "!! models/text_encoders/qwen_3_4b.safetensors",
        "!! models/vae/flux2-klein-vae-bf16.safetensors",
        "!! models/diffusion_models/flux-2-klein-4b-fp8.safetensors.partial",
        "!! models/diffusion_models/evil.safetensors",
        "?? models/text_encoders/qwen_3_4b.safetensors",
        "!! models/vae/",
        "!! custom_nodes/evil.py",
        "?? startup-config.yaml",
        " M main.py",
    ]
    assert preflight.unexpected_source_changes("comfyui", status, allowed_nested) == [
        "!! models/diffusion_models/flux-2-klein-4b-fp8.safetensors.partial",
        "!! models/diffusion_models/evil.safetensors",
        "?? models/text_encoders/qwen_3_4b.safetensors",
        "!! models/vae/",
        "!! custom_nodes/evil.py",
        "?? startup-config.yaml",
        " M main.py",
    ]
    assert preflight.unexpected_source_changes(
        "liveportrait-kj", ["!! config.yaml", "?? payload.py"], set()
    ) == ["!! config.yaml", "?? payload.py"]
