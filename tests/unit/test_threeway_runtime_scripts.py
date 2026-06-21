"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_runtime_scripts.py -q"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from threeway import keys
from threeway.envelope import Event, from_json_obj, verify_event

ROOT = Path(__file__).resolve().parents[2]


def _env(extra=None):
    env = dict(os.environ)
    env.pop("GIT_INDEX_FILE", None)
    if extra:
        env.update(extra)
    return env


def _run(script: str, *args, env=None, cwd=ROOT):
    return subprocess.run(
        [sys.executable, str(ROOT / script), *map(str, args)],
        cwd=str(cwd),
        env=_env(env),
        capture_output=True,
        text=True,
    )


def _git(repo: Path, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        env=_env(),
        capture_output=True,
        text=True,
        check=check,
    )


def _write_keypair(registry: Path, keystore: Path, seat: str):
    registry.mkdir(parents=True, exist_ok=True)
    keystore.mkdir(parents=True, exist_ok=True)
    private_key, public_hex = keys.generate_keypair()
    (registry / f"{seat}.pub").write_text(public_hex + "\n")
    (keystore / f"{seat}.ed25519").write_text(keys.private_to_hex(private_key) + "\n")
    return private_key, public_hex


def _write_event(path: Path, *, kind: str, seat: str, bus_id: str = "dry-run-bus") -> None:
    event = Event(
        id=f"{kind}-{seat}",
        seq=0,
        bus_id=bus_id,
        schema_version="threeway/1",
        kind=kind,
        sender=seat,
        recipient="all",
        signer=f"{seat}:codex:test",
        payload={"pair": "A"} if kind == "candidate" else {"result": "PASS"},
        candidate_id="A:c1" if kind == "candidate" else None,
        subject_sha="1" * 40 if kind != "candidate" else None,
    )
    path.write_text(json.dumps({
        "id": event.id,
        "seq": event.seq,
        "bus_id": event.bus_id,
        "schema_version": event.schema_version,
        "kind": event.kind,
        "from": event.sender,
        "to": event.recipient,
        "signer": event.signer,
        "brief_id": event.brief_id,
        "candidate_id": event.candidate_id,
        "subject_sha": event.subject_sha,
        "brief_version": event.brief_version,
        "causation_id": event.causation_id,
        "signature_version": event.signature_version,
        "supersedes_event_id": event.supersedes_event_id,
        "revokes_event_id": event.revokes_event_id,
        "payload": event.payload,
        "created_at": event.created_at,
        "signature": event.signature,
    }))


def test_append_event_refuses_wrong_kind_authority(tmp_path):
    registry = tmp_path / "registry"
    keystore = tmp_path / "keystore"
    _write_keypair(registry, keystore, "coordinator")
    event_path = tmp_path / "ci-result-by-coordinator.json"
    _write_event(event_path, kind="ci_result", seat="coordinator")

    result = _run(
        "scripts/threeway_append_event.py",
        "--store-dir", tmp_path / "events",
        "--registry", registry,
        "--keystore", keystore,
        "--bus-id", "dry-run-bus",
        "--seat", "coordinator",
        "--event-json", event_path,
    )

    assert result.returncode != 0
    assert "ci_result" in result.stderr
    assert "ci" in result.stderr
    assert not (tmp_path / "events").exists()


def test_append_event_signs_without_committing_private_key_material(tmp_path):
    registry = tmp_path / "registry"
    keystore = tmp_path / "keystore"
    private_key, public_hex = _write_keypair(registry, keystore, "coordinator")
    private_seed = keys.private_to_hex(private_key)
    event_path = tmp_path / "candidate.json"
    _write_event(event_path, kind="candidate", seat="coordinator")

    result = _run(
        "scripts/threeway_append_event.py",
        "--store-dir", tmp_path / "events",
        "--registry", registry,
        "--keystore", keystore,
        "--bus-id", "dry-run-bus",
        "--seat", "coordinator",
        "--event-json", event_path,
    )

    assert result.returncode == 0, result.stderr
    event_files = sorted((tmp_path / "events").glob("*.json"))
    assert len(event_files) == 1
    written = json.loads(event_files[0].read_text())
    assert written["signature"]
    assert private_seed not in event_files[0].read_text()
    assert not list((tmp_path / "events").glob("*.ed25519"))
    verify_event(from_json_obj(written), public_hex)


def test_ci_result_binds_integration_policy_result_and_evidence_digest(tmp_path):
    keystore = tmp_path / "keystore"
    _private_key, public_hex = _write_keypair(tmp_path / "registry", keystore, "ci")
    manifest = tmp_path / "evidence-manifest.json"
    manifest.write_text(json.dumps({"tests": ["pytest tests/unit/test_threeway_*.py -q"]}))
    output = tmp_path / "ci-result.json"
    integration_sha = "a" * 40
    policy_digest = "sha256:" + ("b" * 64)

    result = _run(
        "scripts/threeway_ci_result.py",
        "--keystore", keystore,
        "--bus-id", "dry-run-bus",
        "--candidate-id", "A:c1",
        "--integration-sha", integration_sha,
        "--policy-digest", policy_digest,
        "--result", "PASS",
        "--evidence-manifest", manifest,
        "--output", output,
    )

    assert result.returncode == 0, result.stderr
    event = from_json_obj(json.loads(output.read_text()))
    assert event.kind == "ci_result"
    assert event.signer.startswith("ci:")
    assert event.subject_sha == integration_sha
    assert event.payload["integration_sha"] == integration_sha
    assert event.payload["policy_digest"] == policy_digest
    assert event.payload["result"] == "PASS"
    assert event.payload["evidence_manifest_digest"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    verify_event(event, public_hex)


def test_gate_runner_defaults_to_dry_run_test_ref(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    registry = tmp_path / "registry"
    registry.mkdir()

    result = _run(
        "scripts/threeway_gate_runner.py",
        "--repo", repo,
        "--registry", registry,
        "--store-dir", tmp_path / "events",
        "--bus-id", "dry-run-bus",
        "--candidate-id", "A:c1",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["main_ref"] == "refs/threeway/test-main"
    assert payload["outcome"] in {"PENDING", "REJECTED"}


def test_gate_runner_refuses_protected_main(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")

    result = _run(
        "scripts/threeway_gate_runner.py",
        "--repo", repo,
        "--registry", tmp_path / "registry",
        "--store-dir", tmp_path / "events",
        "--bus-id", "dry-run-bus",
        "--candidate-id", "A:c1",
        "--main-ref", "refs/heads/main",
        "--execute",
    )

    assert result.returncode != 0
    assert "protected main" in result.stderr


def test_cutover_check_is_read_only_and_never_flips(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    coord = tmp_path / "coordination"
    (coord / "mailbox" / "sent").mkdir(parents=True)
    (coord / "mailbox" / "seen").mkdir(parents=True)

    result = _run(
        "scripts/threeway_cutover_check.py",
        "--repo", repo,
        "--coord-root", coord,
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["cutover_execute_allowed"] is False
    assert payload["ready_to_flip"] is False
    assert "bijection" in "\n".join(payload["drifts"])
    show_ref = _git(repo, "show-ref", "--verify", "refs/threeway/events", check=False)
    assert show_ref.returncode != 0


def test_threeway_ci_dry_run_workflow_is_manual_only_and_no_bus_append():
    workflow = ROOT / ".github" / "workflows" / "threeway-ci-dry-run.yml"
    text = workflow.read_text()

    assert "workflow_dispatch:" in text
    assert "pull_request:" not in text
    assert "push:" not in text
    assert "tests/unit/test_threeway_*.py" in text
    assert "scripts/threeway_ci_result.py" in text
    assert "actions/upload-artifact" in text
    assert "threeway_append_event.py" not in text
    assert "RefEventStore" not in text
