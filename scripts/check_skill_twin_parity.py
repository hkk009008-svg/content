#!/usr/bin/env python3
"""Skill-twin body-parity gate: .agents/skills/* must track .claude/skills/*.

WHY (ADR-077): `.agents/skills/` holds the Codex-seat twins of the maintained
`.claude/skills/` project-knowledge skills, and AGENTS.md's R-SKILL rule routes
live Codex seats at them as authoritative doctrine. History shows the twins rot
silently: the ai-video-gen twins froze at 7682c128 and missed four .claude-only
maintenance commits including both 2026-07-11 routing migrations (fixed in
9ba9cc92). A stale twin is worse than none — R-SKILL grants it authority.

WHAT: for each GATED dir, the set of `*.md` files must match on both sides and
every file's BODY (after stripping a leading `--- ... ---` YAML frontmatter
block) must be byte-identical. Frontmatter is exempt by design: the Codex twins
intentionally quote YAML values and may add Codex-only fields
(`disable-model-invocation`).

NOT gated, on purpose:
  - The seat-doctrine skills (four-seat-protocol, seat-coordinator,
    seat-director, seat-operator, create-regression-pin, wave-gate) — deliberate
    Codex-specific forks (see 7d189987; four-seat-protocol is titled "for
    Codex" and diverges by hundreds of lines).
  - Dirs existing on one side only (e.g. .agents/skills/antigravity-harness).
  - Non-.md files — scripts self-reference their own path (seat_status.py's
    usage string says .agents/... vs .claude/...), so byte-parity would
    false-alarm forever.
  - `.claude/skill-eval/` frozen snapshots (ADR-063: editing a baseline
    corrupts the old-vs-new eval).

Fixing a failure: `cp .claude/skills/<dir>/<file> .agents/skills/<dir>/<file>`
in the same commit as the .claude edit (or vice versa if the twin was edited —
.claude is the maintained copy; sync .agents FROM it unless you know better).

Adding a new gated pair: append the dir name to GATED_DIRS.

Usage:
    .venv/bin/python scripts/check_skill_twin_parity.py

Exit codes: 0 = parity holds; 1 = drift found.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Project-knowledge twins that R-SKILL points seats at. Body-parity REQUIRED.
GATED_DIRS = ("ai-video-gen", "comfyui-mastery")

AGENTS_ROOT = Path(".agents/skills")
CLAUDE_ROOT = Path(".claude/skills")


def strip_frontmatter(text: str) -> str:
    """Return text minus a leading YAML frontmatter block, if present."""
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---", 4)
    if end == -1:
        return text
    return text[end + len("\n---"):].lstrip("\n")


def run(repo_root: Path) -> list[str]:
    """Return drift descriptions (empty list = parity holds)."""
    issues: list[str] = []
    for dirname in GATED_DIRS:
        agents_dir = repo_root / AGENTS_ROOT / dirname
        claude_dir = repo_root / CLAUDE_ROOT / dirname
        for side, d in (("agents", agents_dir), ("claude", claude_dir)):
            if not d.is_dir():
                issues.append(f"{dirname}: {side} twin dir missing ({d})")
        if not (agents_dir.is_dir() and claude_dir.is_dir()):
            continue

        agents_md = {p.relative_to(agents_dir) for p in agents_dir.rglob("*.md")}
        claude_md = {p.relative_to(claude_dir) for p in claude_dir.rglob("*.md")}
        for rel in sorted(claude_md - agents_md):
            issues.append(f"{dirname}/{rel}: missing from .agents twin")
        for rel in sorted(agents_md - claude_md):
            issues.append(f"{dirname}/{rel}: missing from .claude (maintained) copy")

        for rel in sorted(agents_md & claude_md):
            a_body = strip_frontmatter((agents_dir / rel).read_text(encoding="utf-8"))
            c_body = strip_frontmatter((claude_dir / rel).read_text(encoding="utf-8"))
            if a_body != c_body:
                issues.append(
                    f"{dirname}/{rel}: body differs from the .claude copy "
                    f"(frontmatter-exempt compare)"
                )
    return issues


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    issues = run(repo_root)
    if issues:
        print(f"SKILL-TWIN DRIFT: {len(issues)} issue(s)")
        for issue in issues:
            print(f"  {issue}")
        print(
            "\nFix: cp .claude/skills/<dir>/<file> .agents/skills/<dir>/<file> "
            "(sync FROM the maintained .claude copy) in the same commit."
        )
        return 1
    for dirname in GATED_DIRS:
        print(f"twin-parity {dirname} ... PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
