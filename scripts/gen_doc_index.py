#!/usr/bin/env python3
"""Regenerate docs/ADR-INDEX.md and the strata-stats block in docs/INDEX.md.

Committed instrument (R-MEASURE culture): the numbers in the navigation docs
come from this script, not from memory. Run from the repo root:

    env -u GIT_INDEX_FILE .venv/bin/python scripts/gen_doc_index.py          # rewrite both
    env -u GIT_INDEX_FILE .venv/bin/python scripts/gen_doc_index.py --check  # verify, no writes

--check exits 1 if either file's generated region is stale, so it can serve as
a cheap CI guard. Only the region between the BEGIN/END GENERATED markers in
INDEX.md is touched; ADR-INDEX.md is fully generated.

DECISIONS.md is declared immutable — this script only READS it. ADR headings
are expected to look like `## ADR-NNN — Title`; anything that deviates is
listed verbatim rather than dropped, so a format drift is visible instead of
silently shrinking the index.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
DECISIONS = ROOT / "DECISIONS.md"
ADR_INDEX = DOCS / "ADR-INDEX.md"
INDEX = DOCS / "INDEX.md"

BEGIN = "<!-- BEGIN GENERATED (scripts/gen_doc_index.py) -->"
END = "<!-- END GENERATED -->"

PREFIXES = (
    "HANDOFF-",
    "BRIEF-",
    "PROPOSAL-",
    "REPLY-",
    "AUDIT-",
    "SPEC-",
    "STRATEGIC_REVIEW-",
    "RUNBOOK-",
)

# Accepts both heading forms in DECISIONS.md ("ADR-001 — title" and
# "ADR-064: title"). The template heading "ADR-NNN" has no digits, so it never
# matches and is excluded from counts on purpose.
ADR_RE = re.compile(r"^## (ADR-\d+)\s*(?:[—-]|:)\s*(.+?)\s*$")
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def adr_table() -> str:
    lines = ["| ADR | Title |", "|---|---|"]
    odd: list[str] = []
    for raw in DECISIONS.read_text(encoding="utf-8").splitlines():
        if not raw.startswith("## ADR"):
            continue
        match = ADR_RE.match(raw)
        if match:
            title = match.group(2).replace("|", "\\|")
            lines.append(f"| {match.group(1)} | {title} |")
        elif "ADR-NNN" not in raw:  # the template heading is expected noise
            odd.append(raw)
    if odd:
        lines.append("")
        lines.append("Unparsed ADR headings (format drift — fix the parser or the heading):")
        lines.extend(f"- `{line}`" for line in odd)
    return "\n".join(lines)


def strata_stats() -> str:
    # The two generated navigation files are excluded from their own counts;
    # otherwise creating ADR-INDEX.md stales the count INDEX.md just embedded,
    # and gen/--check can never converge.
    self_files = {INDEX.name, ADR_INDEX.name}
    entries = sorted(p.name for p in DOCS.iterdir() if p.name not in self_files)
    files = [p for p in DOCS.iterdir() if p.is_file() and p.name not in self_files]
    subdirs = sorted(p.name for p in DOCS.iterdir() if p.is_dir())
    counts = Counter()
    for name in (p.name for p in files):
        for prefix in PREFIXES:
            if name.startswith(prefix):
                counts[prefix] += 1
                break
        else:
            counts["(singleton)"] += 1
    handoff_dates = sorted(
        m.group(1)
        for p in files
        if p.name.startswith("HANDOFF-")
        for m in [DATE_RE.search(p.name)]
        if m
    )
    span = f"{handoff_dates[0]} .. {handoff_dates[-1]}" if handoff_dates else "n/a"
    archive_files = sum(1 for p in (DOCS / "archive").rglob("*") if p.is_file()) if (DOCS / "archive").is_dir() else 0
    superpowers = {
        sub: sum(1 for p in (DOCS / "superpowers" / sub).iterdir() if p.is_file())
        for sub in ("plans", "specs", "briefs")
        if (DOCS / "superpowers" / sub).is_dir()
    }
    adr_rows = sum(
        1
        for line in DECISIONS.read_text(encoding="utf-8").splitlines()
        if ADR_RE.match(line)
    )
    rows = [
        f"- docs/ top level: {len(entries)} entries ({len(files)} files, {len(subdirs)} subdirs: {', '.join(subdirs)})",
        *(f"- {prefix}* : {counts[prefix]}" for prefix in PREFIXES if counts[prefix]),
        f"- singletons (no series prefix): {counts['(singleton)']}",
        f"- HANDOFF date span: {span}",
        f"- docs/archive recursive file count: {archive_files}",
        f"- docs/superpowers: " + ", ".join(f"{k}={v}" for k, v in superpowers.items()),
        f"- ADR entries in DECISIONS.md: {adr_rows} (template heading excluded)",
    ]
    return "\n".join(rows)


def render_adr_index() -> str:
    return (
        "# ADR index (generated)\n\n"
        "One row per `## ADR` heading in [DECISIONS.md](../DECISIONS.md), which is\n"
        "immutable and stays the source of truth — read the full entry there.\n"
        "Regenerate with `env -u GIT_INDEX_FILE .venv/bin/python scripts/gen_doc_index.py`.\n\n"
        f"{adr_table()}\n"
    )


def splice_index(text: str) -> str:
    block = f"{BEGIN}\n{strata_stats()}\n{END}"
    if BEGIN in text and END in text:
        pre = text.split(BEGIN)[0]
        post = text.split(END, 1)[1]
        return pre + block + post
    raise SystemExit(f"markers missing from {INDEX} — add {BEGIN} / {END} first")


def main() -> int:
    check = "--check" in sys.argv[1:]
    new_adr = render_adr_index()
    new_index = splice_index(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else None
    if check:
        stale = []
        if not ADR_INDEX.exists() or ADR_INDEX.read_text(encoding="utf-8") != new_adr:
            stale.append(str(ADR_INDEX))
        if new_index is not None and INDEX.read_text(encoding="utf-8") != new_index:
            stale.append(str(INDEX))
        if stale:
            print("STALE: " + ", ".join(stale))
            return 1
        print("doc indexes current")
        return 0
    ADR_INDEX.write_text(new_adr, encoding="utf-8")
    if new_index is not None:
        INDEX.write_text(new_index, encoding="utf-8")
    print(f"wrote {ADR_INDEX}" + (f" and refreshed {INDEX}" if new_index else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
