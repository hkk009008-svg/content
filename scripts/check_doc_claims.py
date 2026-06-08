#!/usr/bin/env python3
"""Doc-claim verifier — Phase 1: line-anchor checker.

Public API
----------
Drift            dataclass for a single drift finding
check_line_anchors(doc_paths, repo_root) -> list[Drift]
check_sha_refs(doc_paths, repo_root) -> list[Drift]   (git: resolve/reachable/subject)
audit_sha_refs(doc_paths, repo_root) -> list[dict]    (raw git facts per citation)
run(doc_paths, repo_root, fix=False) -> list[Drift]
CHECKERS         enabled default checkers (line-anchors only; SHA + manifest are opt-in)
main(argv=None)  -> int   (exit 0=clean, 1=drift, >1=error)
"""
from __future__ import annotations

import re
import subprocess
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
    kind: str                    # missing_file | def_drift | out_of_bounds | ambiguous_path
    symbol: Optional[str]
    suggested_line: Optional[int]
    fixable: bool
    message: str
    style: str = "link"          # "link" | "inline" — which syntax to rewrite on --fix
    candidates: Optional[list[str]] = None   # ambiguous_path: the colliding tracked relpaths


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

# Inline-backtick anchor: `path:line` or `path:line-line`.
# The literal backticks ARE part of the match (so the span includes them) →
# this is what enforces "standalone token": `mod.py:10)` / `mod.py:10 (x)` /
# `mod.py:10:20` do NOT match. Extension class is letters-only ([A-Za-z]+),
# matching _ANCHOR_RE, so version tokens (`v1.2:30`) are rejected.
_INLINE_ANCHOR_RE = re.compile(
    r'`(?P<file>[A-Za-z0-9_./-]+\.[A-Za-z]+):(?P<line>\d+)(?:-(?P<end>\d+))?`'
)

# Fenced-code-block markers (``` or ~~~, 3+). A line starting one toggles fence state.
_FENCE_RE = re.compile(r'^\s*(`{3,}|~{3,})')

# Drift kinds that are advisory (non-fatal; exit-code-neutral).
ADVISORY_KINDS = {"ambiguous_path"}

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


def _build_basename_index(repo_root: Path) -> "tuple[dict[str, list[str]], bool]":
    """Map basename -> sorted [tracked relpaths] from `git ls-files`.

    git ls-files is tracked-only, so worktree/venv/dist copies are excluded —
    the exact trap that would make every basename look ambiguous. Returns
    (index, git_ok); git_ok=False when git is unavailable/errors (index empty).
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files"],
            capture_output=True, text=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return {}, False
    index: dict[str, list[str]] = {}
    for rel in out.splitlines():
        rel = rel.strip()
        if rel:
            index.setdefault(Path(rel).name, []).append(rel)
    for k in index:
        index[k].sort()
    return index, True


def _resolve_inline_target(
    token_file: str,
    symbol: Optional[str],
    basename_index: "dict[str, list[str]]",
    repo_root: Path,
) -> "tuple[Optional[str], Optional[list[str]]]":
    """Resolve an inline anchor's file token to a tracked relpath.

    Returns (resolved_rel, candidates):
      (rel, None)        -> resolved to exactly one path; caller checks it.
      (None, None)       -> skip (0 matches / absolute / parent-relative).
      (None, [c1, c2..]) -> ambiguous_path advisory (candidates listed).
    Directory-qualified within-repo tokens pass through as-is; existence
    (incl. missing_file) is handled downstream by check_anchor.
    """
    parts = token_file.split("/")
    if token_file.startswith("/") or ".." in parts:
        return None, None                       # absolute / parent-relative -> skip
    if "/" in token_file:
        return token_file, None                 # dir-qualified within repo
    matches = basename_index.get(token_file, [])
    if len(matches) == 1:
        return matches[0], None
    if len(matches) == 0:
        return None, None                       # not a real tracked file -> skip
    # Ambiguous (>=2): try symbol-disambiguation.
    if symbol:
        defining = [
            c for c in matches
            if _def_lines(
                (repo_root / c).read_text(encoding="utf-8", errors="replace").splitlines(),
                symbol,
            )
        ]
        if len(defining) == 1:
            return defining[0], None            # disambiguated -> real check
    return None, matches                        # truly ambiguous -> advisory


def _bind_inline_symbol(line_text: str, anchor_start: int) -> Optional[str]:
    """Bind the symbol for an inline anchor: the nearest backtick token that ENDS
    before `anchor_start` (preceding-only — drop the markdown-link after-fallback,
    since the inline convention is symbol-precedes-anchor). Excludes the anchor's
    own backtick span by construction (we only consider tokens ending <= anchor_start).
    Returns the leading identifier, or None (incl. the dotted-attribute skip)."""
    preceding = [t for t in _BACKTICK_RE.finditer(line_text) if t.end() <= anchor_start]
    if not preceding:
        return None
    token_text = preceding[-1].group(1)
    ident_match = _IDENT_RE.match(token_text)
    if not ident_match:
        return None
    ident = ident_match.group(1)
    pos_after = ident_match.end()
    if pos_after < len(token_text) and token_text[pos_after] == ".":
        return None  # dotted/attribute -> no symbol bind (falls through to bounds)
    return ident


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
    *,
    resolved_rel: Optional[str] = None,
    symbol: Optional[str] = None,
    rebind_symbol: bool = True,
    style: str = "link",
) -> Optional[Drift]:
    """Return a Drift if the anchor is stale, else None."""

    # Step 1 — file existence
    read_rel = resolved_rel if resolved_rel is not None else target_file_rel
    target_path = repo_root / read_rel
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
            style=style,
        )

    source_lines = target_path.read_text(encoding="utf-8", errors="replace").splitlines()

    # Step 2 — symbol binding
    if rebind_symbol:
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
    # else: use the `symbol` parameter as-is (pre-bound by check_line_anchors).

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
                    style=style,
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
            style=style,
        )

    return None  # OK — in bounds, no symbol binding


# ---------------------------------------------------------------------------
# Main checker
# ---------------------------------------------------------------------------

def check_line_anchors(doc_paths: list[str], repo_root: Path) -> list[Drift]:
    """Check all line-anchors (markdown-link AND inline-backtick) in the given docs."""
    drifts: list[Drift] = []
    basename_index, git_ok = _build_basename_index(repo_root)
    unresolved_bare = 0   # for the git-absent warning

    for doc_path in doc_paths:
        full_path = Path(doc_path) if Path(doc_path).is_absolute() else repo_root / doc_path
        if not full_path.exists():
            continue
        doc_lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()

        in_fence = False
        for line_num, line_text in enumerate(doc_lines, 1):
            if _FENCE_RE.match(line_text):
                in_fence = not in_fence
                continue
            if in_fence:
                continue

            # --- markdown-link anchors (existing behavior) ---
            link_keys = set()
            for m in _ANCHOR_RE.finditer(line_text):
                target_file_rel = m.group("file")
                target_line = int(m.group("line"))
                link_keys.add((target_file_rel, target_line))
                drift = check_anchor(
                    doc_path=str(full_path), doc_line_num=line_num,
                    doc_line_text=line_text, target_file_rel=target_file_rel,
                    target_line=target_line, display_text=m.group("display"),
                    repo_root=repo_root,
                )
                if drift is not None:
                    drifts.append(drift)

            # --- inline-backtick anchors (new) ---
            for m in _INLINE_ANCHOR_RE.finditer(line_text):
                token_file = m.group("file")
                target_line = int(m.group("line"))
                # de-dup: skip an inline match whose (file,line) equals a link on the
                # same line (rare; correctness guard, not a span-inside heuristic).
                if (token_file, target_line) in link_keys:
                    continue
                # ORDERING: bind symbol BEFORE resolution (resolution needs it).
                symbol = _bind_inline_symbol(line_text, m.start())
                resolved_rel, candidates = _resolve_inline_target(
                    token_file, symbol, basename_index, repo_root)
                if candidates is not None:
                    drifts.append(Drift(
                        doc_path=str(full_path), doc_line=line_num,
                        target_file=token_file, target_line=target_line,
                        kind="ambiguous_path", symbol=symbol, suggested_line=None,
                        fixable=False,
                        message=(f"`{token_file}` is ambiguous ({len(candidates)} tracked "
                                 f"matches): {', '.join(candidates)} — qualify with a directory"),
                        style="inline", candidates=candidates,
                    ))
                    continue
                if resolved_rel is None:
                    if "/" not in token_file and not git_ok:
                        unresolved_bare += 1
                    continue
                end = m.group("end")
                display = f"{token_file}:{target_line}" + (f"-{end}" if end else "")
                drift = check_anchor(
                    doc_path=str(full_path), doc_line_num=line_num,
                    doc_line_text=line_text, target_file_rel=token_file,
                    target_line=target_line, display_text=display, repo_root=repo_root,
                    resolved_rel=resolved_rel, symbol=symbol,
                    rebind_symbol=False, style="inline",
                )
                if drift is not None:
                    drifts.append(drift)

    if unresolved_bare and not git_ok:
        print(f"WARNING: {unresolved_bare} bare inline anchor(s) could not be resolved "
              f"(git unavailable — basename index empty). These were skipped, NOT verified.",
              file=sys.stderr)
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
# Commit-SHA reference checking (Tier 2: resolve + reachable + quoted-subject)
# ---------------------------------------------------------------------------

# Default doc set for SHA-ref checking — the SHA-dense docs (anchors default to
# ARCHITECTURE.md only).  README/OPERATIONS carry no SHA citations.
SHA_DEFAULT_DOCS = ["CLAUDE.md", "DECISIONS.md", "ARCHITECTURE.md"]

# A backtick token's contents that look like a git short/long SHA (lowercase hex,
# 7-40 chars).  All real citations are 7-char; the wider bound is future-proofing.
_SHA_TOKEN_RE = re.compile(r'^[0-9a-f]{7,40}$')

# A backtick token whose contents are a conventional-commit subject
# (e.g. `fix(web): ...`, `docs: ...`).  Used to detect a quoted commit subject
# sitting next to a cited SHA on the same doc line.
_CONV_COMMIT_RE = re.compile(
    r'^(?:feat|fix|docs|chore|refactor|test|style|perf|build|ci|revert|coord|merge|wip)'
    r'(?:\([^)]*\))?: \S'
)


def _nearest_token(target, candidates):
    """Return the candidate match nearest to *target* on a line (prefer before)."""
    if not candidates:
        return None
    start = target.start()
    before = [c for c in candidates if c.end() <= start]
    if before:
        return before[-1]
    after = [c for c in candidates if c.start() >= target.end()]
    return after[0] if after else None


def _collect_sha_citations(doc_paths: list[str], repo_root: Path) -> list[dict]:
    """Scan docs for backtick SHA tokens; pair each with an adjacent quoted subject.

    Returns one dict per citation: {doc_path, doc_line, sha, quoted_subject}.
    """
    citations: list[dict] = []
    for doc_path in doc_paths:
        full = Path(doc_path) if Path(doc_path).is_absolute() else repo_root / doc_path
        if not full.exists():
            continue
        for line_num, line in enumerate(
            full.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            tokens = list(_BACKTICK_RE.finditer(line))
            if not tokens:
                continue
            sha_tokens = [t for t in tokens if _SHA_TOKEN_RE.match(t.group(1))]
            if not sha_tokens:
                continue
            subj_tokens = [t for t in tokens if _CONV_COMMIT_RE.match(t.group(1))]
            for st in sha_tokens:
                quoted = _nearest_token(st, subj_tokens)
                citations.append({
                    "doc_path": str(full),
                    "doc_line": line_num,
                    "sha": st.group(1),
                    "quoted_subject": quoted.group(1) if quoted else None,
                })
    return citations


def _git_run(repo_root: Path, args: list[str], stdin: Optional[str] = None):
    """Run a git command; return CompletedProcess, or None if git is unavailable."""
    try:
        return subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True, text=True, input=stdin,
        )
    except OSError:
        return None


def _repo_state(repo_root: Path) -> tuple[bool, bool]:
    """Return (is_git_repo, is_shallow). (False, False) when not a repo."""
    r = _git_run(repo_root, ["rev-parse", "--is-shallow-repository"])
    if r is None or r.returncode != 0:
        return (False, False)
    return (True, r.stdout.strip() == "true")


def _resolve_commits(repo_root: Path, shas: list[str]) -> dict:
    """Batch-resolve abbreviated SHAs to full commit oids via cat-file.

    Returns {short_sha: full_oid} for inputs that resolve to a commit object.
    """
    if not shas:
        return {}
    r = _git_run(repo_root, ["cat-file", "--batch-check"], stdin="\n".join(shas) + "\n")
    if r is None or r.returncode != 0:
        return {}
    resolved: dict = {}
    for sha, line in zip(shas, r.stdout.splitlines()):
        parts = line.split()
        # Resolved line: "<full-oid> <type> <size>"; missing/ambiguous: "<input> missing".
        if len(parts) >= 2 and parts[1] == "commit":
            resolved[sha] = parts[0]
    return resolved


def _reachable_oids(repo_root: Path) -> set:
    """Return the set of full commit oids reachable from HEAD."""
    r = _git_run(repo_root, ["rev-list", "HEAD"])
    if r is None or r.returncode != 0:
        return set()
    return set(r.stdout.split())


def _commit_subjects(repo_root: Path, oids: list[str]) -> dict:
    """Return {full_oid: subject} for the given commit oids (one git call)."""
    if not oids:
        return {}
    sep = "\x1f"
    r = _git_run(repo_root, ["show", "-s", f"--format=%H{sep}%s", *oids])
    if r is None or r.returncode != 0:
        return {}
    subjects: dict = {}
    for line in r.stdout.splitlines():
        if sep in line:
            h, s = line.split(sep, 1)
            subjects[h] = s
    return subjects


def _subject_matches(quoted: str, actual: str) -> bool:
    """True if the whitespace-normalised quoted subject is contained in actual.

    Containment (not equality) tolerates the doc truncating a long subject.
    """
    q = " ".join(quoted.split()).strip()
    a = " ".join(actual.split()).strip()
    return bool(q) and q in a


def audit_sha_refs(doc_paths: list[str], repo_root: Path) -> list[dict]:
    """Gather git facts for every backtick SHA citation across *doc_paths*.

    Returns one dict per citation with keys:
        doc_path, doc_line, sha, quoted_subject,
        resolves (bool), reachable (bool|None — None when repo is shallow),
        full_oid (str|None), actual_subject (str|None),
        subject_ok (bool|None — None when no subject is quoted), problem (str|None).

    Returns [] when there are no citations OR repo_root is not a git repo.
    Never raises.
    """
    citations = _collect_sha_citations(doc_paths, repo_root)
    if not citations:
        return []

    is_repo, shallow = _repo_state(repo_root)
    if not is_repo:
        return []

    unique = sorted({c["sha"] for c in citations})
    resolved = _resolve_commits(repo_root, unique)
    reachable = None if shallow else _reachable_oids(repo_root)
    subjects = _commit_subjects(repo_root, sorted(set(resolved.values())))

    rows: list[dict] = []
    for c in citations:
        full_oid = resolved.get(c["sha"])
        if full_oid is None:
            rows.append({
                **c, "resolves": False, "reachable": None, "full_oid": None,
                "actual_subject": None, "subject_ok": None,
                "problem": "does not resolve to a commit",
            })
            continue

        reach = None if reachable is None else (full_oid in reachable)
        actual_subject = subjects.get(full_oid)
        quoted = c["quoted_subject"]
        subject_ok = None
        if quoted is not None and actual_subject is not None:
            subject_ok = _subject_matches(quoted, actual_subject)

        if reach is False:
            problem = "resolves but is not reachable from HEAD"
        elif subject_ok is False:
            problem = "quoted subject does not match the commit"
        else:
            problem = None

        rows.append({
            **c, "resolves": True, "reachable": reach, "full_oid": full_oid,
            "actual_subject": actual_subject, "subject_ok": subject_ok,
            "problem": problem,
        })
    return rows


def check_sha_refs(doc_paths: list[str], repo_root: Path) -> list[Drift]:
    """Derive Drift objects from audit_sha_refs for every problematic citation.

    kind="sha_not_found"        — SHA does not resolve to a commit
    kind="sha_unreachable"      — resolves but not reachable from HEAD
    kind="sha_subject_mismatch" — adjacent quoted subject != the commit's subject

    NOT added to CHECKERS: the default path is pure-filesystem / git-free.
    """
    drifts: list[Drift] = []
    for r in audit_sha_refs(doc_paths, repo_root):
        if not r["resolves"]:
            kind = "sha_not_found"
            message = f"`{r['sha']}` does not resolve to a commit"
        elif r["reachable"] is False:
            kind = "sha_unreachable"
            message = f"`{r['sha']}` resolves but is not reachable from HEAD"
        elif r["subject_ok"] is False:
            kind = "sha_subject_mismatch"
            message = (
                f"`{r['sha']}` quoted subject {r['quoted_subject']!r} "
                f"does not match actual {r['actual_subject']!r}"
            )
        else:
            continue
        drifts.append(Drift(
            doc_path=r["doc_path"],
            doc_line=r["doc_line"],
            target_file="",
            target_line=0,
            kind=kind,
            symbol=r["sha"],
            suggested_line=None,
            fixable=False,
            message=message,
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

def _report_sha_drifts(drifts: list[Drift], n_docs: int) -> int:
    """Print a SHA-ref drift report. Return 0 (clean) or 1 (drift)."""
    if not drifts:
        print(f"SHA refs checked across {n_docs} doc(s) — no drift.")
        return 0
    print(f"\n{'='*60}")
    print(f"SHA-REF DRIFT REPORT  ({len(drifts)} issue(s))")
    print(f"{'='*60}")
    for d in drifts:
        print(f"  [{d.kind}]  {d.doc_path}:{d.doc_line}  (sha: `{d.symbol}`)")
        print(f"    {d.message}")
    return 1


def _print_sha_subjects(docs: list[str], repo_root: Path) -> int:
    """List every cited SHA with its actual subject (manual mis-citation review)."""
    rows = audit_sha_refs(docs, repo_root)
    if not rows:
        print("No SHA citations found.")
        return 0
    for r in rows:
        if not r["resolves"]:
            subject, flag = "<unresolved>", " [NOT FOUND]"
        else:
            subject = r["actual_subject"] or "<no subject>"
            if r["reachable"] is False:
                flag = " [UNREACHABLE]"
            elif r["subject_ok"] is False:
                flag = " [SUBJECT MISMATCH]"
            else:
                flag = ""
        print(f"  {r['sha']}  {subject}{flag}  ({Path(r['doc_path']).name}:{r['doc_line']})")
    return 0


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Verify doc line-anchors and commit-SHA refs against source/git."
    )
    parser.add_argument("--fix", action="store_true", help="Auto-fix def_drift anchors.")
    parser.add_argument(
        "--sha-refs", action="store_true",
        help="Check commit-SHA refs (resolve + reachable from HEAD + quoted-subject match).",
    )
    parser.add_argument(
        "--show-subjects", action="store_true",
        help="List every cited SHA with its actual commit subject (mis-citation review).",
    )
    parser.add_argument(
        "docs",
        nargs="*",
        help=(
            "Markdown doc(s) to check (relative to repo root). Default: ARCHITECTURE.md "
            "for anchors; CLAUDE.md DECISIONS.md ARCHITECTURE.md for --sha-refs/--show-subjects."
        ),
    )
    args = parser.parse_args(argv)

    # Repo root = parent of scripts/ (this file's parent's parent)
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent

    sha_mode = args.sha_refs or args.show_subjects
    docs = args.docs or (SHA_DEFAULT_DOCS if sha_mode else ["ARCHITECTURE.md"])

    if args.show_subjects:
        return _print_sha_subjects(docs, repo_root)

    if args.sha_refs:
        return _report_sha_drifts(check_sha_refs(docs, repo_root), len(docs))

    drifts = run(docs, repo_root, fix=args.fix)

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
