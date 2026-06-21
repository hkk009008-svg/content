#!/usr/bin/env python3
"""Read-only readiness check for the three-way ready-not-live adoption phase."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from threeway import keys_bootstrap, legacy_projector
from threeway.divergence import diverge
from threeway.refstore import EVENTS_REF

RUNTIME_SIGNING_SEATS = tuple(keys_bootstrap.SEATS)
REQUIRED_RUNTIME_PATHS = (
    "threeway/refstore.py",
    "threeway/gate.py",
    "threeway/cutover.py",
    "threeway/keys_bootstrap.py",
    "scripts/threeway_readiness.py",
    "scripts/threeway_append_event.py",
    "scripts/threeway_ci_result.py",
    "scripts/threeway_gate_runner.py",
    "scripts/threeway_cutover_check.py",
)
CI_DRY_RUN_WORKFLOW = ".github/workflows/threeway-ci-dry-run.yml"
AUTHORITY_FLIP_MARKERS = (
    "coordination/threeway/AUTHORITY-LIVE",
    "coordination/threeway/authority-live.json",
)


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _check(check_id: str, status: str, summary: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": status,
        "summary": summary,
        "details": details or {},
    }


def _blocker(blocker_id: str, summary: str) -> dict[str, str]:
    return {"id": blocker_id, "summary": summary}


def _runtime_paths(repo: Path) -> dict[str, Any]:
    missing = [p for p in REQUIRED_RUNTIME_PATHS if not (repo / p).exists()]
    if not (repo / CI_DRY_RUN_WORKFLOW).exists():
        missing.append(CI_DRY_RUN_WORKFLOW)
    status = "pass" if not missing else "blocker"
    return _check(
        "runtime-placeholders",
        status,
        "ready-not-live runtime surfaces are present" if not missing else "missing runtime surfaces",
        {"missing": missing, "required": list(REQUIRED_RUNTIME_PATHS) + [CI_DRY_RUN_WORKFLOW]},
    )


def _key_roster() -> dict[str, Any]:
    expected = {
        "director",
        "operator",
        "coordinator",
        "director2",
        "operator2",
        "coordinator2",
        "overseer",
        "ci",
        "merge-gate",
        "chief-gemini",
        "chief-chatgpt",
    }
    seats = set(RUNTIME_SIGNING_SEATS)
    missing = sorted(expected - seats)
    extras = sorted(seats - expected)
    return _check(
        "key-roster-support",
        "pass" if not missing and not extras else "blocker",
        "key bootstrap covers all runtime signing seats" if not missing and not extras else "key bootstrap roster drift",
        {"seats": list(RUNTIME_SIGNING_SEATS), "missing": missing, "extras": extras},
    )


def _production_registry(repo: Path) -> dict[str, Any]:
    registry = repo / "coordination" / "threeway" / "keys"
    missing = [seat for seat in RUNTIME_SIGNING_SEATS if not (registry / f"{seat}.pub").exists()]
    present = [seat for seat in RUNTIME_SIGNING_SEATS if (registry / f"{seat}.pub").exists()]
    return _check(
        "production-registry",
        "blocker" if missing else "pass",
        "production public-key registry is incomplete" if missing else "production public-key registry is complete",
        {"registry": str(registry), "present": present, "missing": missing},
    )


def _ref_bus(repo: Path) -> dict[str, Any]:
    refs = _git(repo, "for-each-ref", "refs/threeway", "--format=%(refname)").stdout.splitlines()
    return _check(
        "ref-bus-state",
        "pass",
        "threeway ref bus is not live" if EVENTS_REF not in refs else "threeway events ref already exists",
        {"events_ref": EVENTS_REF, "events_ref_present": EVENTS_REF in refs, "refs": refs},
    )


def _legacy_divergence(repo: Path) -> dict[str, Any]:
    sent = repo / "coordination" / "mailbox" / "sent"
    seen = repo / "coordination" / "mailbox" / "seen"
    if not sent.exists() or not seen.exists():
        return _check(
            "legacy-divergence",
            "warn",
            "legacy mailbox paths are not both present",
            {"sent_exists": sent.exists(), "seen_exists": seen.exists()},
        )
    try:
        projected = legacy_projector.project(sent)
        report = diverge(projected, sent, seen)
    except Exception as exc:
        return _check("legacy-divergence", "warn", "legacy divergence check could not run", {"error": str(exc)})
    return _check(
        "legacy-divergence",
        "pass" if report.ok else "warn",
        "legacy mailbox projection matches" if report.ok else "legacy mailbox projection has drift",
        {"projected_events": len(projected), "drifts": report.drifts},
    )


def _ci_dry_run(repo: Path) -> dict[str, Any]:
    path = repo / CI_DRY_RUN_WORKFLOW
    if not path.exists():
        return _check("ci-dry-run", "blocker", "manual threeway CI dry-run workflow missing", {"path": CI_DRY_RUN_WORKFLOW})
    text = path.read_text(encoding="utf-8")
    manual_only = "workflow_dispatch:" in text and "pull_request:" not in text and "push:" not in text
    signs_artifact = "scripts/threeway_ci_result.py" in text and "actions/upload-artifact" in text
    no_append = "threeway_append_event.py" not in text and "RefEventStore" not in text
    ok = manual_only and signs_artifact and no_append
    return _check(
        "ci-dry-run",
        "pass" if ok else "blocker",
        "manual-only signed ci_result dry-run workflow present" if ok else "ci dry-run workflow is not safe/manual-only",
        {"manual_only": manual_only, "signs_artifact": signs_artifact, "no_bus_append": no_append, "path": CI_DRY_RUN_WORKFLOW},
    )


def _gate_runner(repo: Path) -> dict[str, Any]:
    path = repo / "scripts" / "threeway_gate_runner.py"
    if not path.exists():
        return _check("gate-runner", "blocker", "gate dry-run wrapper missing", {"path": "scripts/threeway_gate_runner.py"})
    text = path.read_text(encoding="utf-8")
    refuses_main = "protected main" in text and "refs/heads/main" in text
    dry_ref = "refs/threeway/test-main" in text
    return _check(
        "gate-runner",
        "pass" if refuses_main and dry_ref else "blocker",
        "gate runner defaults to dry-run test ref and refuses main" if refuses_main and dry_ref else "gate runner safety checks incomplete",
        {"refuses_main": refuses_main, "dry_run_ref": dry_ref},
    )


def _authority_flip(repo: Path) -> dict[str, Any]:
    markers = [p for p in AUTHORITY_FLIP_MARKERS if (repo / p).exists()]
    return _check(
        "authority-flip",
        "pass" if not markers else "blocker",
        "authority flip: inactive" if not markers else "authority flip marker present",
        {"active": bool(markers), "markers": markers},
    )


def check_readiness(repo: Path | str | None = None) -> dict[str, Any]:
    repo_path = Path(repo) if repo is not None else repo_root()
    checks = [
        _key_roster(),
        _production_registry(repo_path),
        _runtime_paths(repo_path),
        _ref_bus(repo_path),
        _legacy_divergence(repo_path),
        _ci_dry_run(repo_path),
        _gate_runner(repo_path),
        _authority_flip(repo_path),
    ]
    blockers: list[dict[str, str]] = []
    by_id = {c["id"]: c for c in checks}
    if by_id["key-roster-support"]["status"] == "blocker":
        blockers.append(_blocker("key-roster-missing", by_id["key-roster-support"]["summary"]))
    if by_id["production-registry"]["status"] == "blocker":
        blockers.append(_blocker("production-registry-missing", by_id["production-registry"]["summary"]))
    if by_id["runtime-placeholders"]["status"] == "blocker":
        blockers.append(_blocker("runtime-placeholders-missing", by_id["runtime-placeholders"]["summary"]))
    if by_id["ci-dry-run"]["status"] == "blocker":
        blockers.append(_blocker("ci-dry-run-missing", by_id["ci-dry-run"]["summary"]))
    if by_id["gate-runner"]["status"] == "blocker":
        blockers.append(_blocker("gate-runner-missing", by_id["gate-runner"]["summary"]))
    if by_id["authority-flip"]["status"] == "blocker":
        blockers.append(_blocker("authority-flip-active", by_id["authority-flip"]["summary"]))

    authority_active = bool(by_id["authority-flip"]["details"].get("active"))
    status = "READY-NOT-LIVE" if not blockers else "BLOCKED"
    summary = (
        f"threeway ready-not-live: status={status}; blockers={len(blockers)}; "
        f"{by_id['authority-flip']['summary']}; legacy mailbox remains authoritative"
    )
    return {
        "mode": "ready-not-live",
        "status": status,
        "authority_flip_active": authority_active,
        "summary": summary,
        "checks": checks,
        "blockers": blockers,
    }


def _state_line(report: dict[str, Any]) -> str:
    return (
        f"threeway: ready-not-live status={report['status']} "
        f"blockers={len(report['blockers'])} "
        f"authority_flip={'active' if report['authority_flip_active'] else 'inactive'}"
    )


def _hook_summary(report: dict[str, Any]) -> str:
    return (
        f"threeway ready-not-live: {report['status']}; "
        f"blockers={len(report['blockers'])}; no authority flip; legacy mailbox authoritative"
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--state-line", action="store_true")
    parser.add_argument("--hook-summary", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = check_readiness(repo_root())
    except Exception as exc:
        if args.hook_summary:
            print(f"threeway ready-not-live: hook failed open ({exc})")
            return 0
        print(str(exc), file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.state_line:
        print(_state_line(report))
    elif args.hook_summary:
        print(_hook_summary(report))
    else:
        print(report["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
