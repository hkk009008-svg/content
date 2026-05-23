#!/usr/bin/env python3
"""Generate docs/CODEBASE_DUMP.md -- whole codebase as a single markdown file.

For external verification (human reviewer OR a different LLM context).
Walks the project tree, dumps every Python source file + key docs into
a single navigable markdown document with a ToC.

Excludes
========

  .venv/                  virtualenv
  __pycache__/            bytecode cache
  .git/                   git internals
  .gitnexus/              gitnexus internals
  .serena/                serena internals
  .claude/                claude code internals
  .agents/                LLM tool configurations (not codebase)
  web/dist/               built JS artifacts
  web/node_modules/       JS deps
  projects/               runtime project data
  domain/projects/        runtime project data
  cinema_pipeline_v2/     dead V2 path (per memory)

Includes
========

  *.py    all Python source
  *.md    docs/, AGENTS.md, CLAUDE.md
  requirements*.txt
  .env.example
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT = REPO_ROOT / "docs" / "CODEBASE_DUMP.md"

EXCLUDE_DIRS = {
    ".venv", "__pycache__", ".git", ".gitnexus", ".serena", ".claude",
    ".agents", "web", "node_modules", "projects", "cinema_pipeline_v2",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
}
EXCLUDE_FILES = {
    "CODEBASE_DUMP.md",          # don't include self
    ".DS_Store",
    "CALIBRATION_MATRIX.txt",    # operator content-strategy notes, not codebase
    "used_topics.txt",           # runtime history of generated topics
    "requirements-frozen-py39.txt",  # auto-generated pip freeze snapshot
}
INCLUDE_SUFFIXES = {".py", ".md", ".txt", ".example"}


def should_skip(path: Path) -> bool:
    """True if path should be excluded."""
    if path.name in EXCLUDE_FILES:
        return True
    if path.name.startswith("."):
        # Skip hidden files except a small whitelist
        if path.name not in {".env.example"}:
            return True
    for part in path.parts:
        if part in EXCLUDE_DIRS:
            return True
    return False


def get_language(path: Path) -> str:
    """Return code-fence language tag for syntax highlighting."""
    ext = path.suffix.lower()
    return {
        ".py": "python",
        ".md": "markdown",
        ".txt": "",
        ".example": "ini",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".sh": "bash",
    }.get(ext, "")


def collect_files() -> dict[str, list[Path]]:
    """Walk the repo tree; categorize files by tier."""
    tiers: dict[str, list[Path]] = {
        "tier_meta": [],          # CLAUDE.md, AGENTS.md, requirements, env
        "tier_arch_core": [],     # cinema/, cinema_pipeline.py, main.py, web_server.py, web_services.py
        "tier_arch_tools": [],    # tools/
        "tier_domain": [],        # domain/, audio/, llm/, identity/, config/
        "tier_phases": [],        # cinema/phases/
        "tier_legacy_root": [],   # phase_*.py, other root .py
        "tier_tests": [],         # tests/
        "tier_docs": [],          # docs/
    }
    classified: set[Path] = set()

    for path in sorted(REPO_ROOT.rglob("*")):
        if not path.is_file() or should_skip(path):
            continue
        if path.suffix.lower() not in INCLUDE_SUFFIXES:
            continue
        rel = path.relative_to(REPO_ROOT)
        parts = rel.parts

        # Categorize
        if rel.name in {"CLAUDE.md", "AGENTS.md", ".env.example"} or rel.name.startswith("requirements"):
            tiers["tier_meta"].append(path)
        elif parts[0] == "cinema" and len(parts) >= 2 and parts[1] == "phases":
            tiers["tier_phases"].append(path)
        elif parts[0] == "cinema":
            tiers["tier_arch_core"].append(path)
        elif rel.name in {"cinema_pipeline.py", "main.py", "web_server.py", "web_services.py", "cleanup.py"}:
            tiers["tier_arch_core"].append(path)
        elif parts[0] == "tools":
            tiers["tier_arch_tools"].append(path)
        elif parts[0] in {"domain", "audio", "llm", "identity", "config"}:
            tiers["tier_domain"].append(path)
        elif parts[0] == "tests":
            tiers["tier_tests"].append(path)
        elif parts[0] == "docs":
            tiers["tier_docs"].append(path)
        elif rel.name.startswith("phase_") and rel.suffix == ".py":
            tiers["tier_legacy_root"].append(path)
        elif len(parts) == 1 and rel.suffix == ".py":
            tiers["tier_legacy_root"].append(path)
        else:
            # Catch-all -- shouldn't happen but log
            print(f"WARN: uncategorized: {rel}", file=sys.stderr)
            tiers["tier_legacy_root"].append(path)
        classified.add(path)

    return tiers


def emit_file(out, path: Path, base: Path) -> None:
    """Emit a single file's content as a markdown section."""
    rel = path.relative_to(base)
    lang = get_language(path)
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        out.write(f"### `{rel}`\n\n_(binary file, skipped)_\n\n---\n\n")
        return

    # Anchor-friendly id
    anchor = "file-" + str(rel).replace("/", "-").replace(".", "-").lower()

    out.write(f"### `{rel}` <a name=\"{anchor}\"></a>\n\n")
    line_count = content.count("\n") + (0 if content.endswith("\n") else 1)
    out.write(f"_{line_count} lines_\n\n")
    out.write(f"```{lang}\n")
    out.write(content)
    if not content.endswith("\n"):
        out.write("\n")
    out.write("```\n\n---\n\n")


def emit_toc(out, tiers: dict[str, list[Path]], base: Path) -> None:
    """Emit table of contents linking to each file's anchor."""
    tier_titles = {
        "tier_meta": "Meta (CLAUDE.md, AGENTS.md, requirements, env)",
        "tier_arch_core": "Architecture Core (cinema/, root orchestrator files)",
        "tier_arch_tools": "Architecture Tools (tools/)",
        "tier_phases": "Phase Wrappers (cinema/phases/)",
        "tier_domain": "Domain Modules (domain/, audio/, llm/, identity/, config/)",
        "tier_legacy_root": "Legacy Root Modules (phase_*.py + other root .py)",
        "tier_tests": "Tests (tests/unit/, tests/integration/)",
        "tier_docs": "Documentation (docs/)",
    }
    out.write("## Table of Contents\n\n")
    for tier, paths in tiers.items():
        if not paths:
            continue
        title = tier_titles[tier]
        out.write(f"### {title}\n\n")
        for p in paths:
            rel = p.relative_to(base)
            anchor = "file-" + str(rel).replace("/", "-").replace(".", "-").lower()
            out.write(f"- [`{rel}`](#{anchor})\n")
        out.write("\n")
    out.write("---\n\n")


def main() -> int:
    import subprocess
    import datetime

    tiers = collect_files()

    # Get commit + branch
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
        commits_ahead = subprocess.check_output(
            ["git", "rev-list", "--count", "pre-refactor-baseline..HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except subprocess.CalledProcessError:
        commit = branch = commits_ahead = "unknown"

    total_files = sum(len(v) for v in tiers.values())
    total_loc = 0
    for paths in tiers.values():
        for p in paths:
            try:
                total_loc += p.read_text(encoding="utf-8").count("\n")
            except UnicodeDecodeError:
                pass

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8") as out:
        out.write("# Cinema Pipeline -- Codebase Dump\n\n")
        out.write(
            f"Generated for external verification on {datetime.date.today().isoformat()}.\n\n"
        )
        out.write("## Metadata\n\n")
        out.write(f"- **Repo:** Content (cinema video generation pipeline)\n")
        out.write(f"- **Branch:** `{branch}`\n")
        out.write(f"- **HEAD:** `{commit}`\n")
        out.write(f"- **Commits ahead of `pre-refactor-baseline`:** {commits_ahead}\n")
        out.write(f"- **Total files included:** {total_files}\n")
        out.write(f"- **Total LOC (approx, source + docs):** {total_loc:,}\n")
        out.write("\n")
        out.write(
            "## Excluded from this dump\n\n"
            "- `.venv/`, `__pycache__/`, `.git/`, `.gitnexus/`, `.serena/`, `.claude/`\n"
            "- `.agents/` (LLM tool configurations, not codebase)\n"
            "- `web/dist/`, `web/node_modules/` (built JS artifacts + deps)\n"
            "- `projects/`, `domain/projects/` (runtime project data)\n"
            "- `cinema_pipeline_v2/` (dead V2 path)\n\n"
            "## How to read this dump\n\n"
            "Files are grouped into 8 tiers (see ToC). Each file has its own H3 header with its repo-relative path, the line count, then the file content in a fenced code block. Use the ToC to jump.\n\n"
            "---\n\n"
        )
        emit_toc(out, tiers, REPO_ROOT)

        tier_titles = {
            "tier_meta": "Meta (CLAUDE.md, AGENTS.md, requirements, env)",
            "tier_arch_core": "Architecture Core (cinema/, root orchestrator files)",
            "tier_arch_tools": "Architecture Tools (tools/)",
            "tier_phases": "Phase Wrappers (cinema/phases/)",
            "tier_domain": "Domain Modules (domain/, audio/, llm/, identity/, config/)",
            "tier_legacy_root": "Legacy Root Modules (phase_*.py + other root .py)",
            "tier_tests": "Tests (tests/unit/, tests/integration/)",
            "tier_docs": "Documentation (docs/)",
        }
        for tier, paths in tiers.items():
            if not paths:
                continue
            out.write(f"## {tier_titles[tier]}\n\n")
            for p in paths:
                emit_file(out, p, REPO_ROOT)

    size_kb = OUTPUT.stat().st_size / 1024
    print(f"Wrote {OUTPUT.relative_to(REPO_ROOT)}: {total_files} files, "
          f"{total_loc:,} lines of content, {size_kb:.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
