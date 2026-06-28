"""Capability scorecard: per-dimension PASS/FAIL + (live/e2e) measured-vs-bar."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class ScorecardEntry:
    dimension: str
    claim_id: str
    tier: str
    passed: bool
    measured: Optional[float] = None
    bar: Optional[float] = None
    detail: str = ""


class Scorecard:
    def __init__(self) -> None:
        self.entries: list[ScorecardEntry] = []

    def record(self, *, dimension, claim_id, tier, passed,
               measured=None, bar=None, detail="") -> None:
        self.entries.append(ScorecardEntry(
            dimension=dimension, claim_id=claim_id, tier=tier,
            passed=bool(passed), measured=measured, bar=bar, detail=detail))

    def rollup(self) -> dict:
        out: dict[str, dict] = {}
        for e in self.entries:
            d = out.setdefault(e.dimension, {"passed": 0, "failed": 0})
            d["passed" if e.passed else "failed"] += 1
        return out

    def render_markdown(self) -> str:
        lines = ["# Capability Scorecard", ""]
        for dim, r in sorted(self.rollup().items()):
            lines.append(f"## {dim}  ({r['passed']} pass / {r['failed']} fail)")
            for e in [x for x in self.entries if x.dimension == dim]:
                status = "PASS" if e.passed else "FAIL"
                metric = f"  {e.measured:.2f} vs bar {e.bar:.2f}" if (e.measured is not None and e.bar is not None) else ""
                extra = f" — {e.detail}" if e.detail else ""
                lines.append(f"- [{e.tier}] {e.claim_id}: {status}{metric}{extra}")
            lines.append("")
        return "\n".join(lines)

    def render_json(self) -> str:
        return json.dumps({"entries": [asdict(e) for e in self.entries]}, indent=2)
