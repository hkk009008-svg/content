#!/usr/bin/env python3
"""Doc-claim verifier — Phase 1: line-anchor checker.

Public API
----------
Drift            dataclass for a single drift finding
check_line_anchors(doc_paths, repo_root) -> list[Drift]
run(doc_paths, repo_root, fix=False) -> list[Drift]
CHECKERS         list of enabled checker functions
main(argv=None)  -> int   (exit 0=clean, 1=drift, >1=error)
"""
from __future__ import annotations

import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class Drift:
    doc_path: str
    doc_line: int
    target_file: str
    target_line: int
    kind: str                    # missing_file | def_drift | out_of_bounds
    symbol: Optional[str]
    suggested_line: Optional[int]
    fixable: bool
    message: str


# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

# Matches the LINK part of a markdown anchor: ](path/to/file.ext:NNN)
# Captures file and line number.
_ANCHOR_RE = re.compile(
    r'\[(?P<display>[^\]]*)\]'      # display text
    r'\((?P<file>[A-Za-z0-9_./-]+\.[A-Za-z]+):(?P<line>\d+)\)'
)

# Backtick-delimited tokens on a line
_BACKTICK_RE = re.compile(r'`([^`]+)`')

# Leading identifier from a backtick token
_IDENT_RE = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)')

# Definition patterns (def / async def / class at any indent, or module-level assignment)
def _def_lines(source_lines: list[str], symbol: str) -> list[int]:
    """Return 1-based line numbers where `symbol` is defined."""
    def_pat = re.compile(
        r'^\s*(async\s+def|def|class)\s+' + re.escape(symbol) + r'\b'
    )
    assign_pat = re.compile(
        r'^' + re.escape(symbol) + r'\s*[:=]'
    )
    found = []
    for i, line in enumerate(source_lines, 1):
        if def_pat.match(line) or assign_pat.match(line):
            found.append(i)
    return found


# ---------------------------------------------------------------------------
# Per-anchor check
# ---------------------------------------------------------------------------

def check_anchor(
    doc_path: str,
    doc_line_num: int,
    doc_line_text: str,
    target_file_rel: str,
    target_line: int,
    display_text: str,
    repo_root: Path,
) -> Optional[Drift]:
    """Return a Drift if the anchor is stale, else None."""

    # Step 1 — file existence
    target_path = repo_root / target_file_rel
    if not target_path.exists():
        return Drift(
            doc_path=doc_path,
            doc_line=doc_line_num,
            target_file=target_file_rel,
            target_line=target_line,
            kind="missing_file",
            symbol=None,
            suggested_line=None,
            fixable=False,
            message=f"target file not found: {target_file_rel}",
        )

    source_lines = target_path.read_text(encoding="utf-8", errors="replace").splitlines()

    # Step 2 — symbol binding
    # Find all backtick tokens on the doc line
    backtick_tokens = list(_BACKTICK_RE.finditer(doc_line_text))

    # Find position of the anchor link in the line to pick nearest backtick
    anchor_match = None
    for m in _ANCHOR_RE.finditer(doc_line_text):
        if (m.group("file") == target_file_rel and
                int(m.group("line")) == target_line):
            anchor_match = m
            break

    symbol = None
    if anchor_match and backtick_tokens:
        anchor_start = anchor_match.start()
        # Prefer token immediately before anchor; fall back to after
        before = [t for t in backtick_tokens if t.end() <= anchor_start]
        after = [t for t in backtick_tokens if t.start() >= anchor_match.end()]
        candidate = before[-1] if before else (after[0] if after else None)

        if candidate:
            token_text = candidate.group(1)
            ident_match = _IDENT_RE.match(token_text)
            if ident_match:
                ident = ident_match.group(1)
                # Dotted/attribute skip: char immediately after ident in token
                pos_after = ident_match.end()
                if pos_after < len(token_text) and token_text[pos_after] == '.':
                    # Dotted — skip symbol binding, fall through to bounds
                    pass
                else:
                    symbol = ident

    if symbol is not None:
        def_line_list = _def_lines(source_lines, symbol)
        if def_line_list:
            # Check if target_line matches any def line, OR matches a ranged display
            # Parse display text for range like "file:A-B"
            range_match = re.search(r':(\d+)-(\d+)$', display_text)
            if range_match:
                range_a, range_b = int(range_match.group(1)), int(range_match.group(2))
            else:
                range_a, range_b = None, None

            ok = False
            if target_line in def_line_list:
                ok = True
            elif range_a is not None:
                if any(range_a <= d <= range_b for d in def_line_list):
                    ok = True

            if not ok:
                fixable = len(def_line_list) == 1
                suggested = def_line_list[0] if fixable else None
                return Drift(
                    doc_path=doc_path,
                    doc_line=doc_line_num,
                    target_file=target_file_rel,
                    target_line=target_line,
                    kind="def_drift",
                    symbol=symbol,
                    suggested_line=suggested,
                    fixable=fixable,
                    message=(
                        f"`{symbol}` def is at line {def_line_list[0] if len(def_line_list)==1 else def_line_list}"
                        f", anchor points at {target_line}"
                    ),
                )
            return None  # OK — symbol bound correctly

        # 0 def lines found — fall through to bounds check (step 3)

    # Step 3 — bounds only
    n_lines = len(source_lines)
    if target_line < 1 or target_line > n_lines:
        return Drift(
            doc_path=doc_path,
            doc_line=doc_line_num,
            target_file=target_file_rel,
            target_line=target_line,
            kind="out_of_bounds",
            symbol=symbol,
            suggested_line=None,
            fixable=False,
            message=(
                f"line {target_line} out of bounds (file has {n_lines} lines)"
            ),
        )

    return None  # OK — in bounds, no symbol binding


# ---------------------------------------------------------------------------
# Main checker
# ---------------------------------------------------------------------------

def check_line_anchors(doc_paths: list[str], repo_root: Path) -> list[Drift]:
    """Check all line-anchors in the given markdown docs. Returns list of Drift."""
    drifts: list[Drift] = []

    for doc_path in doc_paths:
        full_path = Path(doc_path) if Path(doc_path).is_absolute() else repo_root / doc_path
        if not full_path.exists():
            # Can't check a non-existent doc — skip silently
            continue

        doc_text = full_path.read_text(encoding="utf-8", errors="replace")
        doc_lines = doc_text.splitlines()

        for line_num, line_text in enumerate(doc_lines, 1):
            for m in _ANCHOR_RE.finditer(line_text):
                display = m.group("display")
                target_file_rel = m.group("file")
                target_line = int(m.group("line"))

                drift = check_anchor(
                    doc_path=str(full_path),
                    doc_line_num=line_num,
                    doc_line_text=line_text,
                    target_file_rel=target_file_rel,
                    target_line=target_line,
                    display_text=display,
                    repo_root=repo_root,
                )
                if drift is not None:
                    drifts.append(drift)

    return drifts


# ---------------------------------------------------------------------------
# Fix logic
# ---------------------------------------------------------------------------

def _shift_display(display: str, old: int, new: int) -> str:
    """Shift the line reference in an anchor's display text from `old` to `new`.

    Handles a range `:old-B` (start AND end shift by the same delta, preserving
    span → `:new-(B+delta)`) and a bare `:old` (→ `:new`). Works whether or not
    the display carries a filename prefix (e.g. `core.py:75-115` or `:138-140`).
    Other numbers are left untouched.
    """
    delta = new - old
    for rm in re.finditer(r':(\d+)-(\d+)', display):
        if int(rm.group(1)) == old:
            end = int(rm.group(2)) + delta
            return display[:rm.start()] + f":{new}-{end}" + display[rm.end():]
    return re.sub(
        r':(\d+)\b',
        lambda m: f":{new}" if int(m.group(1)) == old else m.group(0),
        display,
    )


def _apply_fixes(drifts: list[Drift]) -> list[Drift]:
    """Apply fixable def_drift corrections in-place. Return remaining (unfixed) drifts."""
    def _is_fixable(d: Drift) -> bool:
        return d.kind == "def_drift" and d.fixable and d.suggested_line is not None

    fixable = [d for d in drifts if _is_fixable(d)]
    unfixed = [d for d in drifts if not _is_fixable(d)]

    from collections import defaultdict
    by_doc: dict[str, list[Drift]] = defaultdict(list)
    for d in fixable:
        by_doc[d.doc_path].append(d)

    for doc_path, doc_drifts in by_doc.items():
        path = Path(doc_path)
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)

        for drift in doc_drifts:
            idx = drift.doc_line - 1  # 0-based
            old, new = drift.target_line, drift.suggested_line

            def _rewrite(m: "re.Match", _d: Drift = drift, _old: int = old, _new: int = new) -> str:
                # Only rewrite the one anchor this drift refers to (file + line).
                if m.group("file") != _d.target_file or int(m.group("line")) != _old:
                    return m.group(0)
                new_display = _shift_display(m.group("display"), _old, _new)
                return f"[{new_display}]({_d.target_file}:{_new})"

            lines[idx] = _ANCHOR_RE.sub(_rewrite, lines[idx])
            print(f"  FIXED  {doc_path}:{drift.doc_line}  "
                  f"{drift.target_file}:{old} → {drift.target_file}:{new}")

        path.write_text("".join(lines), encoding="utf-8")

    return unfixed


# ---------------------------------------------------------------------------
# Manifest auditing (pipeline_status.toml)
# ---------------------------------------------------------------------------

def audit_manifest(
    manifest_path: Union[str, Path],
    repo_root: Path,
) -> list[dict]:
    """Parse *manifest_path* (TOML) and validate every component's anchor.

    Returns a list of dicts — one per [[component]] — with keys:
        id, title, status, anchor, note,
        valid (bool), current_line (int|None), problem (str|None).

    Returns [] when the file doesn't exist.
    Never raises; malformed entries produce valid=False entries.
    """
    p = Path(manifest_path)
    if not p.exists():
        return []

    try:
        with open(p, "rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        # Unparseable TOML — treat as zero components
        return []

    results: list[dict] = []
    for entry in data.get("component", []):
        # Collect base fields defensively
        cid = entry.get("id")
        title = entry.get("title", "")
        status = entry.get("status", "")
        anchor = entry.get("anchor")
        note = entry.get("note", "")

        base = {
            "id": cid,
            "title": title,
            "status": status,
            "anchor": anchor,
            "note": note,
        }

        # Guard malformed entries (missing anchor or id)
        if anchor is None or cid is None:
            missing = "anchor" if anchor is None else "id"
            results.append({
                **base,
                "valid": False,
                "current_line": None,
                "problem": f"malformed entry (missing '{missing}')",
            })
            continue

        # Split anchor → (file_rel, symbol) using rsplit on ":" (rightmost)
        # File paths use '/' but no ':'; symbol has no ':'.
        try:
            file_rel, symbol = anchor.rsplit(":", 1)
        except ValueError:
            results.append({
                **base,
                "valid": False,
                "current_line": None,
                "problem": f"malformed anchor (no ':' separator): {anchor!r}",
            })
            continue

        # File existence
        target_path = repo_root / file_rel
        if not target_path.exists():
            results.append({
                **base,
                "valid": False,
                "current_line": None,
                "problem": f"file not found: {file_rel}",
            })
            continue

        # Symbol lookup via _def_lines
        source_lines = target_path.read_text(encoding="utf-8", errors="replace").splitlines()
        def_line_list = _def_lines(source_lines, symbol)
        if not def_line_list:
            results.append({
                **base,
                "valid": False,
                "current_line": None,
                "problem": f"symbol not found: {symbol}",
            })
        else:
            results.append({
                **base,
                "valid": True,
                "current_line": def_line_list[0],
                "problem": None,
            })

    return results


def check_manifest(
    manifest_path: Union[str, Path],
    repo_root: Path,
) -> list[Drift]:
    """Derive Drift objects from audit_manifest for every invalid component.

    kind="manifest_missing_file"     — target file absent
    kind="manifest_symbol_not_found" — file exists but symbol missing
    """
    components = audit_manifest(manifest_path, repo_root)
    drifts: list[Drift] = []
    for comp in components:
        if comp["valid"]:
            continue
        anchor = comp.get("anchor") or ""
        problem = comp.get("problem") or ""
        cid = comp.get("id") or "unknown"

        # Determine target_file and symbol from anchor (best-effort)
        if anchor and ":" in anchor:
            file_rel, symbol = anchor.rsplit(":", 1)
        else:
            file_rel = anchor
            symbol = cid

        # Determine kind
        if "file not found" in problem:
            kind = "manifest_missing_file"
        else:
            kind = "manifest_symbol_not_found"

        drifts.append(Drift(
            doc_path=str(manifest_path),
            doc_line=0,
            target_file=file_rel,
            target_line=0,
            kind=kind,
            symbol=symbol if symbol else cid,
            suggested_line=None,
            fixable=False,
            message=f"{cid}: {problem}",
        ))
    return drifts


# ---------------------------------------------------------------------------
# run() — orchestrates all checkers
# ---------------------------------------------------------------------------

CHECKERS = [check_line_anchors]


def run(doc_paths: list[str], repo_root: Path, fix: bool = False) -> list[Drift]:
    """Run all enabled checkers; apply fixes when fix=True. Return remaining drift."""
    all_drifts: list[Drift] = []
    for checker in CHECKERS:
        all_drifts.extend(checker(doc_paths, repo_root))

    if fix:
        remaining = _apply_fixes(all_drifts)
    else:
        remaining = all_drifts

    return remaining


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Verify doc line-anchors against source files."
    )
    parser.add_argument("--fix", action="store_true", help="Auto-fix def_drift anchors.")
    parser.add_argument(
        "docs",
        nargs="*",
        default=["ARCHITECTURE.md"],
        help="Markdown doc(s) to check (relative to repo root). Default: ARCHITECTURE.md",
    )
    args = parser.parse_args(argv)

    # Repo root = parent of scripts/ (this file's parent's parent)
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent

    drifts = run(args.docs, repo_root, fix=args.fix)

    if not drifts:
        print(f"{'All' if not args.fix else 'Remaining'} anchors checked — no drift.")
        return 0

    print(f"\n{'='*60}")
    print(f"DOC-ANCHOR DRIFT REPORT  ({len(drifts)} issue(s))")
    print(f"{'='*60}")
    for d in drifts:
        fix_hint = f"  → suggested: line {d.suggested_line}" if d.suggested_line else ""
        print(
            f"  [{d.kind}]  {d.doc_path}:{d.doc_line}"
            f"  →  {d.target_file}:{d.target_line}"
            + (f"  (symbol: `{d.symbol}`)" if d.symbol else "")
            + fix_hint
        )
        print(f"    {d.message}")

    fixable_count = sum(1 for d in drifts if d.fixable)
    if fixable_count:
        print(
            f"\n{fixable_count} fixable def_drift(s). Run: "
            f".venv/bin/python scripts/check_doc_claims.py --fix"
        )
    unfixable = [d for d in drifts if not d.fixable]
    if unfixable:
        print(f"{len(unfixable)} drift(s) require manual intervention.")

    return 1


if __name__ == "__main__":
    sys.exit(main())
