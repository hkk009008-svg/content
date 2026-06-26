#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from threeway import LOAD_BEARING_KINDS  # noqa: E402


@dataclass(frozen=True)
class MechanismRow:
    kind: str
    status: str
    emitters: tuple[str, ...]
    tests: tuple[str, ...]
    note: str


_ROWS = {
    "brief": MechanismRow("brief", "live", ("scripts/overseer_emit.py brief",), ("tests/unit/test_threeway_overseer_emit.py",), "overseer-authority fact"),
    "brief_superseded": MechanismRow("brief_superseded", "partial", ("threeway/reducer.py",), ("tests/unit/test_threeway_tier.py",), "reducer support exists; CLI added in this plan"),
    "candidate": MechanismRow("candidate", "live", ("scripts/seat_emit.py coordinator candidate", "scripts/seat_emit.py coordinator2 candidate"), ("tests/unit/test_threeway_seat_emit.py",), "interactive coordinator fact"),
    "candidate_aborted": MechanismRow("candidate_aborted", "live", ("scripts/seat_emit.py coordinator candidate_aborted", "scripts/seat_emit.py coordinator2 candidate_aborted"), ("tests/unit/test_threeway_seat_emit.py",), "interactive coordinator abort fact"),
    "assignment": MechanismRow("assignment", "live", ("scripts/overseer_emit.py assignment",), ("tests/unit/test_threeway_overseer_emit.py",), "overseer assignment"),
    "attestation": MechanismRow("attestation", "live", ("scripts/seat_emit.py operator attestation", "scripts/seat_emit.py operator2 attestation"), ("tests/unit/test_threeway_seat_emit.py",), "primary verifier attestation"),
    "attestation_revoked": MechanismRow("attestation_revoked", "partial", ("threeway/reducer.py",), ("tests/unit/test_threeway_tier.py",), "reducer support exists; CLI added in this plan"),
    "co_sign": MechanismRow("co_sign", "partial", ("threeway/tier.py",), ("tests/unit/test_threeway_tier.py",), "gate support exists; seat CLI added in this plan"),
    "re_verify": MechanismRow("re_verify", "partial", ("threeway/tier.py",), ("tests/unit/test_threeway_tier.py",), "gate support exists; seat CLI added in this plan"),
    "re_verify_challenge": MechanismRow("re_verify_challenge", "live", ("scripts/overseer_emit.py re_verify_challenge",), ("tests/unit/test_threeway_overseer_emit.py",), "overseer nonce challenge"),
    "cycle_go": MechanismRow("cycle_go", "live", ("scripts/overseer_emit.py cycle_go",), ("tests/unit/test_threeway_overseer_emit.py",), "overseer cycle authorization"),
    "release_requested": MechanismRow("release_requested", "live", ("scripts/seat_emit.py coordinator release_requested", "scripts/seat_emit.py coordinator2 release_requested"), ("tests/unit/test_threeway_seat_emit.py",), "interactive coordinator release request"),
    "release_order": MechanismRow("release_order", "live", ("scripts/overseer_emit.py release_order",), ("tests/unit/test_threeway_overseer_emit.py",), "manual overseer release order"),
    "human_approval": MechanismRow("human_approval", "partial", ("threeway/tier.py",), ("tests/unit/test_threeway_tier.py",), "gate support exists; chief CLI added in this plan"),
    "approver_roster": MechanismRow("approver_roster", "live", ("scripts/overseer_emit.py approver_roster",), ("tests/unit/test_threeway_overseer_emit.py",), "overseer roster"),
    "ci_result": MechanismRow("ci_result", "live", ("scripts/sign_ci_result.py",), ("tests/unit/test_threeway_e2e_walking_skeleton.py",), "CI attestor fact"),
    "merge_completed": MechanismRow("merge_completed", "live", ("threeway/gate.py run_gate",), ("tests/unit/test_threeway_e2e_walking_skeleton.py",), "merge-gate completion fact"),
}


def collect_mechanisms() -> dict[str, MechanismRow]:
    missing = set(LOAD_BEARING_KINDS) - set(_ROWS)
    extra = set(_ROWS) - set(LOAD_BEARING_KINDS)
    if missing or extra:
        raise AssertionError(f"ledger drift: missing={sorted(missing)} extra={sorted(extra)}")
    return dict(sorted(_ROWS.items()))


def render_markdown(rows: dict[str, MechanismRow]) -> str:
    lines = [
        "# Threeway Mechanism Ledger",
        "",
        "Generated and checked by:",
        "",
        "```bash",
        ".venv/bin/python scripts/threeway_mechanism_ledger.py --check",
        "```",
        "",
        "| Kind | Status | Runtime emitters / support | Tests | Note |",
        "|---|---|---|---|---|",
    ]
    for row in rows.values():
        emitters = "<br>".join(f"`{emitter}`" for emitter in row.emitters)
        tests = "<br>".join(f"`{test}`" for test in row.tests)
        lines.append(f"| `{row.kind}` | `{row.status}` | {emitters} | {tests} | {row.note} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render or check the threeway mechanism ledger.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    rows = collect_mechanisms()
    text = render_markdown(rows)
    if args.check:
        expected = _REPO_ROOT / "docs/protocol/threeway/MECHANISM-LEDGER.md"
        actual = expected.read_text(encoding="utf-8") if expected.exists() else ""
        if actual != text:
            print("MECHANISM-LEDGER.md is stale; rerender with this script", file=sys.stderr)
            return 1
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
