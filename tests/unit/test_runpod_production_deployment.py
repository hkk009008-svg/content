from __future__ import annotations

import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib
import json
from pathlib import Path
import re
import sys
import threading

import pytest


ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy" / "runpod-comfyui"
sys.path.insert(0, str(DEPLOY / "bin"))

gateway = importlib.import_module("gateway")
model_artifacts = importlib.import_module("model_artifacts")
preflight = importlib.import_module("preflight")
probe_module = importlib.import_module("probe")
startup_guard = importlib.import_module("startup_guard")


def _manifest() -> dict:
    return json.loads((DEPLOY / "models.json").read_text(encoding="utf-8"))


def test_production_model_manifest_is_complete_and_workflow_bound():
    manifest = _manifest()
    model_artifacts.validate_manifest(manifest)
    preflight.workflow_model_contract(ROOT / "pulid.json", manifest)
    assert all(artifact["required"] is True for artifact in manifest["artifacts"])
    assert all(len(artifact["sha256"]) == 64 for artifact in manifest["artifacts"])


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (lambda item: item.pop("sha256"), "sha256"),
        (lambda item: item.__setitem__("sha256", "TBD"), "sha256"),
        (lambda item: item.__setitem__("destination", "../escape"), "traversal-free"),
        (lambda item: item.pop("license"), "license"),
    ],
)
def test_model_manifest_fails_closed_for_missing_or_placeholder_metadata(mutation, match):
    manifest = _manifest()
    mutation(manifest["artifacts"][0])
    with pytest.raises(model_artifacts.ManifestError, match=match):
        model_artifacts.validate_manifest(manifest)


def test_small_artifact_checksum_positive_and_negative(tmp_path):
    payload = b"verified-model-fixture"
    artifact = {
        "id": "fixture",
        "required": True,
        "kind": "file",
        "source": {
            "repository": "https://example.invalid/models",
            "revision": "fixture-v1",
            "url": "https://example.invalid/model.bin",
        },
        "license": {
            "declared_by_distributor": "MIT",
            "upstream_terms": "MIT",
            "review_note": "test fixture",
        },
        "expected_bytes": len(payload),
        "sha256": __import__("hashlib").sha256(payload).hexdigest(),
        "destination": "fixtures/model.bin",
    }
    destination = tmp_path / artifact["destination"]
    destination.parent.mkdir(parents=True)
    destination.write_bytes(payload)
    model_artifacts.verify_artifact(tmp_path, artifact)
    destination.write_bytes(payload + b"corrupt")
    with pytest.raises(model_artifacts.ArtifactError, match="byte count"):
        model_artifacts.verify_artifact(tmp_path, artifact)


def test_revision_manifest_requires_full_commit_sha():
    revisions = json.loads((DEPLOY / "revisions.json").read_text(encoding="utf-8"))
    preflight.validate_revisions_payload(revisions)
    invalid = copy.deepcopy(revisions)
    invalid["components"][0]["commit"] = "main"
    with pytest.raises(preflight.PreflightError, match="full lowercase SHA"):
        preflight.validate_revisions_payload(invalid)


def test_dockerfile_exposes_only_authenticated_gateway_and_pins_sources():
    dockerfile = (DEPLOY / "Dockerfile").read_text(encoding="utf-8")
    revisions = json.loads((DEPLOY / "revisions.json").read_text(encoding="utf-8"))
    assert "@sha256:77f17f843507062875ce8be2a6f76aa6aa3df7f9ef1e31d9d7432f4b0f563dee" in dockerfile
    assert "EXPOSE 8189" in dockerfile
    assert "EXPOSE 8188" not in dockerfile
    assert "nohup" not in dockerfile
    entrypoint = (DEPLOY / "bin" / "entrypoint.sh").read_text(encoding="utf-8")
    assert "exec /opt/content-venv/bin/supervisord" in entrypoint
    for component in revisions["components"]:
        assert component["commit"] in dockerfile


def test_gateway_rejects_missing_short_prefixed_tokens_and_non_loopback_upstream():
    for token in ("", "short", "Bearer " + "x" * 40):
        with pytest.raises(gateway.GatewayConfigError):
            gateway.validate_token(token)
    assert gateway.validate_token("x" * 32) == "x" * 32
    with pytest.raises(gateway.GatewayConfigError, match="loopback"):
        gateway.validate_upstream("http://0.0.0.0:8188")


class _HealthHandler(BaseHTTPRequestHandler):
    responses: dict[str, tuple[int, object]] = {}

    def do_GET(self):
        status, payload = self.responses.get(self.path, (404, {"error": "missing"}))
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


@pytest.fixture
def health_server():
    _HealthHandler.responses = {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_liveness_and_readiness_probe_positive_fixture(health_server):
    _HealthHandler.responses = {
        "/health/live": (200, {"status": "live"}),
        "/health/ready": (200, {"status": "ready", "checked_at_unix": 1}),
    }
    probe_module.probe(health_server, "liveness", 2)
    probe_module.probe(health_server, "readiness", 2)


@pytest.mark.parametrize(
    "response",
    [(503, {"status": "not_ready"}), (200, {"status": "live"}), (200, ["ready"])],
)
def test_readiness_probe_negative_fixtures(health_server, response):
    _HealthHandler.responses = {"/health/ready": response}
    with pytest.raises(RuntimeError, match="readiness probe"):
        probe_module.probe(health_server, "readiness", 2)


def test_setup_runpod_is_explicitly_non_production_and_fails_required_node_gap():
    script = (ROOT / "scripts" / "setup_runpod.sh").read_text(encoding="utf-8")
    assert "NOT A PRODUCTION DEPLOYMENT" in script
    assert "use deploy/runpod-comfyui/" in script
    assert "PULID_NODES_OK" in script
    assert "required PuLID nodes are missing" in script
    assert "exit 1" in script


def test_image_security_workflow_builds_and_scans_the_production_contract():
    workflow = (ROOT / ".github" / "workflows" / "runpod-image-security.yml").read_text(
        encoding="utf-8"
    )
    assert "'deploy/runpod-comfyui/**'" in workflow
    assert "'pulid.json'" in workflow
    assert "deploy/runpod-comfyui/lock_requirements.sh" in workflow
    assert "git diff --exit-code -- deploy/runpod-comfyui/requirements.lock" in workflow
    assert "file: deploy/runpod-comfyui/Dockerfile" in workflow
    assert "platforms: linux/amd64" in workflow
    assert "push: false" in workflow
    assert "format: cyclonedx-json" in workflow
    assert "severity-cutoff: high" in workflow
    assert "severity: HIGH,CRITICAL" in workflow
    assert "version: v0.69.3" in workflow

    uses = re.findall(r"^\s*uses:\s*([^\s#]+)", workflow, flags=re.MULTILINE)
    assert uses
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", use) for use in uses)
