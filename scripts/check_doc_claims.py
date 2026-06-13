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

import ast
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
    doc_col: Optional[tuple[int, int]] = None  # (start, end) span of THIS anchor on the
    # doc line; set at detection so --fix rewrites the exact occurrence (ADV-1).


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

# Inline-backtick anchor: `path:line` or `path:line-line` (range).
# The range separator accepts ASCII hyphen, en-dash (–, U+2013), and em-dash
# (—, U+2014) — the docs use en-dashes heavily and an ASCII-only class made
# those range anchors INVISIBLE (Slice 3). --fix canonicalizes to ASCII hyphen.
# The literal backticks ARE part of the match (so the span includes them) →
# this is what enforces "standalone token": `mod.py:10)` / `mod.py:10 (x)` /
# `mod.py:10:20` do NOT match. Extension class is letters-only ([A-Za-z]+),
# matching _ANCHOR_RE, so version tokens (`v1.2:30`) are rejected.
_INLINE_ANCHOR_RE = re.compile(
    r'`(?P<file>[A-Za-z0-9_./-]+\.[A-Za-z]+):(?P<line>\d+)(?:[-–—](?P<end>\d+))?`'
)

# Path-LESS continuation anchor: a bare `:line` / `:line-line` backtick token
# that INHERITS its file from the nearest preceding full inline anchor ON THE
# SAME LINE.  Compound doc cells write the filename once and continue with bare
# colons: `lip_sync.py:177` / `:470` / `:697`.  The 2nd/3rd terms carry no path,
# so _INLINE_ANCHOR_RE (which REQUIRES path.ext) never saw them — they were
# silently unverified.  A continuation anchor is only promoted when a same-line
# full anchor precedes it (see _ordered_line_anchors); a bare `:N` whose file is
# established by a markdown LINK on a *previous* line (ARCHITECTURE.md bullet
# lists) has no same-line full anchor and stays inert, exactly as before.
_CONTINUATION_ANCHOR_RE = re.compile(
    r'`:(?P<line>\d+)(?:[-–—](?P<end>\d+))?`'
)

# Multi-range anchor: a backtick token citing a comma-list of lines and/or ranges —
# `path:A-B, C-D` (ranges) OR `path:N, M` (bare lines, e.g. project_manager.py:133,924).
# The comma precedes the closing backtick, so _INLINE_ANCHOR_RE cannot parse EITHER
# shape. These ARE verified now (Commit 2): a bound symbol's def must fall within ONE
# comma-term; with no symbol, every term must be in-bounds. Multi-range --fix is OUT
# of scope -> drift is report-only (non-fixable). The first comma-term may be a bare
# line OR a range; `[^`]*` stays within one backtick pair (cannot cross the closing
# backtick), so a single anchor followed by PROSE commas (`mod.py:1-5` covers 9, 12)
# does NOT false-fire. Named groups capture file + the raw term-list for parsing.
_MULTIRANGE_RE = re.compile(
    r'`(?P<file>[A-Za-z0-9_./-]+\.[A-Za-z]+):'
    r'(?P<terms>\d+(?:[-–—]\d+)?\s*,\s*\d+[-–—]?\d*[^`]*)`'
)


def _parse_multirange_terms(terms_text: str) -> "Optional[list[tuple[int, int]]]":
    """Parse a comma-list of bare lines and/or ranges into [(lo, hi), ...].

    Each term is `N` (-> (N, N)) or `A-B` (ASCII hyphen / en-dash / em-dash ->
    (A, B)). Returns None if ANY term is unparseable (so the caller can fall back
    to the 'NOT verified' warning rather than silently mis-verifying). Whitespace
    around commas and terms is tolerated; a trailing empty term is ignored.
    """
    terms: "list[tuple[int, int]]" = []
    raw = terms_text.strip().rstrip(",").strip()
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = re.fullmatch(r'(\d+)(?:[-–—](\d+))?', chunk)
        if not m:
            return None  # an unparseable term -> bail (keep the warning path)
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else lo
        if hi < lo:
            lo, hi = hi, lo
        terms.append((lo, hi))
    return terms or None

# Slash-list anchor: ONE backtick token citing slash-separated BARE lines —
# `path:N / M / P` (PROGRAM-MANUAL compound table rows write the filename once
# and continue with slashes INSIDE the same token, e.g.
# `quality_max.py:461 / 509 / 543 / 564 / 587`). _INLINE_ANCHOR_RE requires the
# closing backtick right after the first number, _CONTINUATION_ANCHOR_RE wants
# separate `:N` tokens, _MULTIRANGE_RE wants commas — so these cells were
# silently unverified (PROGRAM-MANUAL:556 drifted +20 under a green gate; Lane V
# slice-2 Chunk-1 find). Each term becomes a positional anchor (k-th term pairs
# with the k-th symbol of the row's symbol cell via _positional_symbol_map);
# unpaired terms are bounds-only, NEVER nearest-before (nearest-before would
# bind the cell's last symbol to every term and --fix would corrupt correct
# rows). Terms are bare lines only — no ranges (none exist in the real rows);
# a slash cell with a range term fails strict parse and WARNS via
# _SLASHLIST_LOOSE_RE (ADV-2: warn, don't silently skip).
_SLASHLIST_ANCHOR_RE = re.compile(
    r'`(?P<file>[A-Za-z0-9_./-]+\.[A-Za-z]+):(?P<terms>\d+(?:\s*/\s*\d+)+)`'
)

# Loose probe for the warning path: a backtick token with a file:line prefix and
# a digit/digit slash somewhere after the colon that the STRICT regex (and
# multirange, for comma cells) did not claim.
_SLASHLIST_LOOSE_RE = re.compile(
    r'`[A-Za-z0-9_./-]+\.[A-Za-z]+:[^`]*\d\s*/\s*\d[^`]*`'
)

# Fenced-code-block markers (``` or ~~~, 3+). A line starting one toggles fence state.
_FENCE_RE = re.compile(r'^\s*(`{3,}|~{3,})')

# Drift kinds that are advisory (non-fatal; exit-code-neutral).
ADVISORY_KINDS = {"ambiguous_path"}

# Definition patterns (def / async def / class at any indent, or module-level assignment)
def _def_lines(source_lines: list[str], symbol: str) -> list[int]:
    """Return 1-based line numbers where `symbol` is defined.

    `def`/`class` match at any indent.  Plain assignments match at column 0
    only — EXCEPT ALL-CAPS constants (the module-constant convention), which
    are ALSO matched when assigned at indent.  This covers the optional-import
    / config-guard pattern (``try: FLAG = True`` / ``except: FLAG = False``,
    or an ``if``-guarded constant) so a stale anchor to such a constant is
    caught instead of passing silently as bounds-only.  Lowercase names stay
    column-0-only so local variables (``    x = 1`` inside a function) are
    never bound as defs and cannot produce false drifts.

    Lines inside triple-quoted spans (docstrings / prompt templates) and
    comment-only lines are skipped — without this, indented ALL-CAPS env-var
    prose like ``    WEB_CORS_ORIGINS=*`` *documented inside a docstring*
    would be mistaken for a constant definition (the relaxed-indent rule's
    one real footgun; triple-quote tracking mirrors `_def_extent_end`).
    """
    def_pat = re.compile(
        r'^\s*(async\s+def|def|class)\s+' + re.escape(symbol) + r'\b'
    )
    # ALL-CAPS → constant convention → allow leading indent; else column-0 only.
    indent = r'^\s*' if symbol.isupper() else r'^'
    assign_pat = re.compile(
        indent + re.escape(symbol) + r'\s*[:=]'
    )
    found = []
    in_string = False
    for i, line in enumerate(source_lines, 1):
        quotes = line.count('"""') + line.count("'''")
        if in_string:
            # Inside a triple-quoted span — never a real def; flip state if
            # this line closes the span (odd quote count).
            if quotes % 2 == 1:
                in_string = False
            continue
        if not line.lstrip().startswith("#") and (
            def_pat.match(line) or assign_pat.match(line)
        ):
            found.append(i)
        if quotes % 2 == 1:
            in_string = True
    return found


def _enclosing_def(source_lines: list[str], line_num: int) -> Optional[str]:
    """Nearest enclosing def/class of 1-based *line_num*: 'fn', 'Cls.method',
    bare 'Cls' (class body before any method), or None (module level).
    Indent-scan, not AST — good enough for the audit listing."""
    def_re = re.compile(r'^(\s*)(?:async\s+)?def\s+([A-Za-z_]\w*)')
    cls_re = re.compile(r'^(\s*)class\s+([A-Za-z_]\w*)')
    method: Optional[tuple[int, str]] = None
    for i in range(min(line_num, len(source_lines)) - 1, -1, -1):
        dm = def_re.match(source_lines[i])
        if dm:
            if len(dm.group(1)) == 0:
                return dm.group(2)
            if method is None:
                method = (len(dm.group(1)), dm.group(2))
            continue
        cm = cls_re.match(source_lines[i])
        if cm:
            if method is not None and len(cm.group(1)) < method[0]:
                return f"{cm.group(2)}.{method[1]}"
            if method is None and len(cm.group(1)) == 0:
                return cm.group(2)
    return method[1] if method else None


def _def_extent_end(source_lines: list[str], def_line: int) -> int:
    """Last 1-based line of the block opened at *def_line* (indent-scan;
    blank lines never close a block). Triple-quoted spans are skipped —
    docstrings/LLM prompt templates routinely contain zero-indent text
    that would otherwise read as a dedent and truncate the extent."""
    base = source_lines[def_line - 1]
    base_indent = len(base) - len(base.lstrip())
    end = def_line
    in_string = False
    for i in range(def_line + 1, len(source_lines) + 1):
        text = source_lines[i - 1]
        quotes = text.count('"""') + text.count("'''")
        if in_string:
            end = i
            if quotes % 2 == 1:
                in_string = False
            continue
        if quotes % 2 == 1:
            in_string = True
            end = i
            continue
        if not text.strip():
            continue
        if len(text) - len(text.lstrip()) <= base_indent:
            break
        end = i
    return end


def _is_executable_body_line(
    source_lines: list[str], def_line: int, target_line: int,
) -> bool:
    """True when target_line is executable BODY code of the def at def_line —
    not the signature continuation, the docstring, a blank, or a comment-only
    line.

    Direction-blindness guard for the extent rule: a def-cite drifted by a
    small upward shift of the def (lines deleted above it, or a --fix'd
    anchor surviving a revert) lands a few lines PAST the def — on exactly
    these line classes — and the bare extent rule accepted it silently
    (live incident: anchor :454 over `_allocate_ref_slots` def :450,
    2026-06-11). Deliberate body cites (a gate check, a registry entry, a
    composition line) cite executable code.
    """
    raw = source_lines[target_line - 1] if 1 <= target_line <= len(source_lines) else ""
    stripped = raw.strip()
    if not stripped or stripped.startswith("#"):
        return False
    try:
        tree = ast.parse("\n".join(source_lines))
    except SyntaxError:
        return True  # can't classify docstrings/signatures — lexical checks only
    node = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and n.lineno == def_line
        ),
        None,
    )
    if node is None or not node.body:
        return True
    first = node.body[0]
    code_start = first.lineno
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        code_start = (first.end_lineno or first.lineno) + 1
    return target_line >= code_start


def _usage_cite_acceptance(
    doc_line_text: str,
    source_lines: list[str],
    target_line: int,
    range_a: Optional[int],
    range_b: Optional[int],
    bound_symbol: Optional[str],
) -> bool:
    """Accept a non-def-line anchor as a deliberate usage-site citation.

    Rule A: any backticked identifier token on the doc line occurs
    word-bounded on the cited line (or any line of the cited range).
    Rule B: the cited line is executable BODY code within the bound symbol's
    def extent — signature continuations, docstrings, blanks, and
    comment-only lines are NOT accepted (see _is_executable_body_line):
    that is where direction-drifted def-cites land, and the bare extent
    rule was direction-blind to them (anchor:454 over def:450 sat unflagged,
    2026-06-11 incident).

    Why: the binder treats every anchor as a def-citation, but doc anchors
    routinely cite usage sites — a gate check, a registry entry, a
    composition line. Reporting those as def_drift makes --fix actively
    corrupt them (14 hand-verified cases in docs/PROGRAM-MANUAL.md at
    2d58fca). Known accepted residual: a truly-drifted def-cite whose new
    cited line happens to CALL the symbol (Rule A) or lands on executable
    body code inside the extent (Rule B) passes silently — far cheaper
    than --fix dragging correct usage cites to the def.
    """
    tokens: set[str] = set()
    for t in _BACKTICK_RE.finditer(doc_line_text):
        text = t.group(1)
        if ':' in text or '/' in text or text.endswith('.py'):
            continue  # path/anchor tokens — their fragments match spuriously
        m = _IDENT_RE.match(text)
        if m:
            tokens.add(m.group(1))
    scan = (
        range(range_a, range_b + 1)
        if range_a is not None and range_b is not None
        else (target_line,)
    )
    _strings_re = re.compile(r"'[^']*'|\"[^\"]*\"")
    for ln in scan:
        if not (1 <= ln <= len(source_lines)):
            continue
        no_comment = source_lines[ln - 1].split('#', 1)[0]
        code_only = _strings_re.sub('', no_comment)
        for tok in tokens:
            # The BOUND symbol must occur as CODE — a comment/string mention
            # is the classic false-pass (TestProseMentionNoFalsePass). Other
            # tokens corroborate from strings too (dict keys, env-var names)
            # but never from comments.
            haystack = code_only if tok == bound_symbol else no_comment
            if re.search(r'(?<!\w)' + re.escape(tok) + r'(?!\w)', haystack):
                return True
    if bound_symbol:
        # Extent rule only when the binding is unambiguous (exactly one def);
        # duplicate defs make the binding itself unreliable.
        def_lines = _def_lines(source_lines, bound_symbol)
        if len(def_lines) == 1:
            d = def_lines[0]
            if (
                d <= target_line <= _def_extent_end(source_lines, d)
                and _is_executable_body_line(source_lines, d, target_line)
            ):
                return True
    return False


def _fallback_symbol(
    line_text: str,
    anchor_span: "tuple[int, int]",
    source_lines: list[str],
    exclude: Optional[str],
    preceding_only: bool,
) -> Optional[str]:
    """Step 2.5 def-aware fallback: when the nearest/bound token has no def in
    the target file, retry the line's OTHER identifier tokens by distance from
    the anchor and return the first that actually defines in the target.
    Inline anchors stay preceding-only (symbol-precedes-anchor convention);
    link anchors may fall back to after-tokens, mirroring each path's existing
    nearest-binding side rules. Path tokens (`mod.py:10`) self-exclude via the
    dotted-attribute rule in _ident_token."""
    a_start, a_end = anchor_span
    # Segment scoping: an anchor's symbol cannot live beyond a NEIGHBORING
    # anchor on the same line (C-1 guard family: in two-anchor-column compound
    # rows, a col-3 anchor must never reach back across col-2's anchors and
    # steal col-1's symbols — that is exactly the --fix corruption shape).
    seg_lo, seg_hi = 0, len(line_text)
    for pat in (_ANCHOR_RE, _INLINE_ANCHOR_RE, _CONTINUATION_ANCHOR_RE, _MULTIRANGE_RE):
        for am in pat.finditer(line_text):
            if am.end() <= a_start:
                seg_lo = max(seg_lo, am.end())
            elif am.start() >= a_end:
                seg_hi = min(seg_hi, am.start())
    candidates: list[tuple[int, str]] = []
    for t in _BACKTICK_RE.finditer(line_text):
        if t.end() <= a_start and t.start() >= seg_lo:
            dist = a_start - t.end()
        elif t.start() >= a_end and t.end() <= seg_hi and not preceding_only:
            dist = t.start() - a_end
        else:
            continue  # own span/overlap, disallowed side, or outside the segment
        ident = _ident_token(t.group(1))
        if ident is None or ident == exclude:
            continue
        candidates.append((dist, ident))
    seen: set[str] = set()
    for _, ident in sorted(candidates, key=lambda c: c[0]):
        if ident in seen:
            continue
        seen.add(ident)
        if _def_lines(source_lines, ident):
            return ident
    return None


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
    Ambiguity tie-break order: a symbol defined in exactly one candidate
    wins; else a token that IS a tracked relpath (root-exact — the root
    re-export shims) wins; else advisory.
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
        defining = []
        for c in matches:
            # git ls-files lists TRACKED paths even if absent on disk (staged
            # deletion, `git rm --cached`, sparse checkout, mid-rename). An
            # unreadable candidate must NOT abort the run (CQ-1) — treat it as
            # non-defining (skip); resolution then falls to the root-exact
            # tie-break or the advisory below (an absent root-exact file
            # surfaces downstream as a fatal missing_file — deliberate).
            try:
                src = (repo_root / c).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if _def_lines(src.splitlines(), symbol):
                defining.append(c)
        if len(defining) == 1:
            return defining[0], None            # disambiguated -> real check
    if token_file in matches:
        # Root-exact: the bare token IS a tracked relpath (only possible for
        # a repo-root file, e.g. the root re-export shims). "Qualify with a
        # directory" is unsatisfiable at the root, so exactness breaks the
        # tie when symbol evidence is absent or inconclusive; a symbol
        # defined in exactly one candidate (above) stays the stronger signal.
        return token_file, None
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


def _ident_token(token_text: str) -> Optional[str]:
    """Return the bare leading identifier of a backtick token, or None when the
    token is not a bindable bare identifier (dotted/attribute, or non-identifier).
    Mirrors _bind_inline_symbol's identifier rule but operates on the token text."""
    ident_match = _IDENT_RE.match(token_text)
    if not ident_match:
        return None
    pos_after = ident_match.end()
    if pos_after < len(token_text) and token_text[pos_after] == ".":
        return None  # dotted/attribute
    return ident_match.group(1)


def _ident_tokens(token_text: str, text_start: int) -> "list[tuple[int, str]]":
    """Positions + idents a backtick token contributes to positional pairing.

    A token of slash-separated BARE idents (`make_take / make_shot / ...` —
    the single-token compound symbol cell, PROGRAM-MANUAL:556/:464 shape)
    contributes EACH ident at its own in-line position, so a slash-list anchor
    cell of the same arity pairs positionally. Any segment that is not a bare
    identifier (dotted, prose, empty) demotes the whole token to the
    single-ident rule (_ident_token) — conservative: a half-parseable cell must
    not fabricate a count match. *text_start* is the position of the token TEXT
    (after the opening backtick) on the doc line."""
    if "/" in token_text:
        segs = [s.strip() for s in token_text.split("/")]
        if len(segs) > 1 and all(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', s) for s in segs):
            out: "list[tuple[int, str]]" = []
            pos = 0
            for s in segs:
                at = token_text.index(s, pos)
                out.append((text_start + at, s))
                pos = at + len(s)
            return out
    ident = _ident_token(token_text)
    return [(text_start, ident)] if ident is not None else []


def _ordered_line_anchors(line_text: str) -> "list[dict]":
    """Return every inline anchor on *line_text* in left-to-right source order.

    Each entry is a dict: {start, end, file, line, end_line (Optional[int])}.
    Includes both full inline anchors (`path.py:N`) AND path-less continuation
    anchors (`:N`) that inherit the file of the nearest preceding FULL anchor on
    the SAME line (compound-cell form `path.py:177` / `:470` / `:697`). A
    continuation anchor with no preceding same-line full anchor is dropped (it
    stays inert, matching pre-positional behavior — see _CONTINUATION_ANCHOR_RE).
    """
    fulls = []
    for m in _INLINE_ANCHOR_RE.finditer(line_text):
        fulls.append({
            "start": m.start(), "end": m.end(),
            "file": m.group("file"), "line": int(m.group("line")),
            "end_line": int(m.group("end")) if m.group("end") else None,
        })
    full_spans = [(f["start"], f["end"]) for f in fulls]
    conts = []
    for m in _CONTINUATION_ANCHOR_RE.finditer(line_text):
        # Skip if this `:N` span is actually the tail of a full anchor match
        # (defensive — the two regexes shouldn't overlap, but be safe).
        if any(s <= m.start() < e for s, e in full_spans):
            continue
        # Inherit the file from the nearest preceding FULL anchor on this line.
        preceding = [f for f in fulls if f["end"] <= m.start()]
        if not preceding:
            continue  # no same-line file context -> stays inert
        inherited = preceding[-1]["file"]
        conts.append({
            "start": m.start(), "end": m.end(),
            "file": inherited, "line": int(m.group("line")),
            "end_line": int(m.group("end")) if m.group("end") else None,
        })
    # Slash-list expansion: ONE backtick token `path:N / M / P` becomes one
    # positional anchor PER TERM. Each anchor's span is the term's DIGITS only
    # (so --fix rewrites the number in place, preserving prefix/separators).
    # Cannot overlap the other shapes: inline needs the closing backtick right
    # after the number, continuation needs a `:N` token, multirange needs commas.
    slashes = []
    for m in _SLASHLIST_ANCHOR_RE.finditer(line_text):
        terms_start = m.start("terms")
        for tm in re.finditer(r'\d+', m.group("terms")):
            slashes.append({
                "start": terms_start + tm.start(), "end": terms_start + tm.end(),
                "file": m.group("file"), "line": int(tm.group(0)),
                "end_line": None, "style": "slash",
            })
    return sorted(fulls + conts + slashes, key=lambda a: a["start"])


def _column_of(pos: int, bar_positions: "list[int]") -> int:
    """Markdown-table column index of a source position (0-based). With no
    pipes the whole line is column 0 — non-table lines are one logical column."""
    c = 0
    for b in bar_positions:
        if pos > b:
            c += 1
        else:
            break
    return c


def _positional_symbol_map(line_text: str, anchors: "list[dict]") -> "dict[int, str]":
    """Column-scoped positional pairing for compound multi-symbol cells.

    The compound shape this fixes is a markdown-table row whose symbol column
    lists N>1 backtick identifiers and whose anchor column lists the SAME N
    anchors, all symbols preceding all anchors:

        | `symA` / `symB` / `symC` | `path.py:1` / `:3` / `:5` | description |

    The nearest-backtick heuristic mis-binds here (binds `:1` to `symC`); this
    pairs the k-th anchor to the k-th identifier of the symbol column.

    Returns {anchor_start: symbol} for the anchors it can pair; an empty/partial
    map leaves the rest to the caller's nearest-before fallback. The rule is
    COLUMN-SCOPED (not whole-line) so prose-backtick tokens in OTHER table
    columns (e.g. `mode="auto"` in a description cell) do not pollute the count.

    For a non-table line (no pipes) the whole line is one column, so this
    degenerates to: pair iff #idents == #anchors and N>1 — matching the simple
    whole-line rule for the rare non-table compound line.
    """
    if len(anchors) <= 1:
        return {}
    bars = [m.start() for m in re.finditer(r'\|', line_text)]
    anchor_spans = [(a["start"], a["end"]) for a in anchors]

    # All bindable identifier tokens (excluding the anchor tokens themselves),
    # grouped by table column.
    idents_by_col: "dict[int, list[tuple[int, str]]]" = {}
    for m in _BACKTICK_RE.finditer(line_text):
        if any(s <= m.start() < e for s, e in anchor_spans):
            continue  # this token IS an anchor
        # NOTE a slash-list anchor token is NOT excluded by the span check
        # (its per-term spans start after the backtick) — but its text begins
        # `file.ext:`, so _ident_tokens demotes to _ident_token, which returns
        # None on the dotted file prefix. It contributes no idents.
        for ipos, ident in _ident_tokens(m.group(1), m.start(1)):
            col = _column_of(ipos, bars)
            idents_by_col.setdefault(col, []).append((ipos, ident))

    # Group anchors by column.
    anchors_by_col: "dict[int, list[dict]]" = {}
    for a in anchors:
        anchors_by_col.setdefault(_column_of(a["start"], bars), []).append(a)

    mapping: "dict[int, str]" = {}
    for acol, col_anchors in anchors_by_col.items():
        if len(col_anchors) <= 1:
            continue  # single anchor in this column -> nearest-before is correct
        # The symbol column is the nearest PRECEDING column that has identifiers
        # (col acol-1, acol-2, ...) — BUT only if no anchor column intervenes
        # (C-1). An anchor column may be consumed by at most ONE anchor column
        # (its nearest following anchor column): if the walk-back hits another
        # anchor column before any ident column, THIS column shares its symbols
        # with that earlier anchor column, so we leave it to nearest-before/bounds
        # (no positional entry) rather than re-binding to an already-consumed
        # symbol column. Same-column idents still count for acol=0 (the rare
        # non-table whole-line compound line — no preceding column to walk).
        sym_idents = None
        for c in range(acol - 1, -1, -1):
            if idents_by_col.get(c):
                sym_idents = idents_by_col[c]
                break
            if c in anchors_by_col:
                break  # intervening anchor column -> this column shares its symbols
        if sym_idents is None and acol == 0:
            sym_idents = idents_by_col.get(acol)
        if not sym_idents or len(sym_idents) != len(col_anchors):
            continue  # count mismatch -> don't pair this column (nearest-before)
        ordered_anchors = sorted(col_anchors, key=lambda a: a["start"])
        ordered_idents = sorted(sym_idents, key=lambda t: t[0])
        for i, a in enumerate(ordered_anchors):
            mapping[a["start"]] = ordered_idents[i][1]
    return mapping


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
    doc_col: Optional[tuple[int, int]] = None,
    symbol_fallback: bool = False,
    unbound_sink: "Optional[list[dict]]" = None,
) -> Optional[Drift]:
    """Return a Drift if the anchor is stale, else None.

    *doc_col*, when given, is the (start, end) span of this anchor on the doc
    line; it is stamped onto the returned Drift so --fix can rewrite the exact
    occurrence by position rather than by a global keyed regex sub (ADV-1).
    """

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
            doc_col=doc_col,
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

    # Step 2.5 — def-aware fallback. When the nearest-bound token has no def in
    # the target file (or nothing bound at all), retry the line's other tokens
    # by distance instead of silently degrading to bounds-only. Positionally
    # paired symbols are authoritative: callers signal eligibility via
    # rebind_symbol (link nearest path) or symbol_fallback (inline nearest path).
    if (
        (rebind_symbol or symbol_fallback)
        and doc_col is not None
        and (symbol is None or not _def_lines(source_lines, symbol))
    ):
        fb = _fallback_symbol(
            doc_line_text, doc_col, source_lines,
            exclude=symbol, preceding_only=(style == "inline"),
        )
        if fb is not None:
            symbol = fb

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
                if _usage_cite_acceptance(
                    doc_line_text, source_lines, target_line,
                    range_a, range_b, symbol,
                ):
                    if unbound_sink is not None:
                        unbound_sink.append({
                            "doc_path": doc_path,
                            "doc_line": doc_line_num,
                            "target_file": target_file_rel,
                            "target_line": target_line,
                            "symbol": symbol,
                            "enclosing": _enclosing_def(source_lines, target_line),
                            "usage_cite": True,
                        })
                    return None
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
                    doc_col=doc_col,
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
            doc_col=doc_col,
        )

    # Audit sink: reaching here means the anchor passed BOUNDS-ONLY (symbol was
    # never bound, or bound with 0 defs even after the Step-2.5 fallback) — the
    # silent-degrade class --list-unbound exists to surface.
    if unbound_sink is not None:
        unbound_sink.append({
            "doc_path": doc_path,
            "doc_line": doc_line_num,
            "target_file": target_file_rel,
            "target_line": target_line,
            "symbol": symbol,
            "enclosing": _enclosing_def(source_lines, target_line),
        })

    return None  # OK — in bounds, no symbol binding


def check_multirange_anchor(
    doc_path: str,
    doc_line_num: int,
    doc_line_text: str,
    token_file: str,
    terms_text: str,
    repo_root: Path,
    *,
    resolved_rel: Optional[str],
    symbol: Optional[str],
) -> Optional[Drift]:
    """Verify a comma-list multi-range anchor (`path:A-B, C-D` / `path:N, M`).

    Semantics (mirrors the single-range logic in check_anchor):
      * If *symbol* is bound and HAS def lines: OK iff some def line falls within
        ONE comma-term; else def_drift (report-only — fixable=False, since
        multi-range --fix is out of scope).
      * If no symbol (or no def lines): every term must be in-bounds (1..n);
        any out-of-range term -> out_of_bounds (non-fixable).
      * Missing file -> missing_file.

    Returns a Drift on a problem, else None. NEVER returns a fixable drift, so
    _apply_fixes (which requires fixable=True) leaves multi-range anchors alone.
    """
    read_rel = resolved_rel if resolved_rel is not None else token_file
    target_path = repo_root / read_rel
    if not target_path.exists():
        return Drift(
            doc_path=doc_path, doc_line=doc_line_num, target_file=token_file,
            target_line=0, kind="missing_file", symbol=None, suggested_line=None,
            fixable=False, message=f"target file not found: {token_file}",
            style="inline",
        )

    terms = _parse_multirange_terms(terms_text)
    if terms is None:
        return None  # unparseable -> caller keeps the 'NOT verified' warning

    source_lines = target_path.read_text(encoding="utf-8", errors="replace").splitlines()
    n_lines = len(source_lines)

    if symbol is not None:
        def_line_list = _def_lines(source_lines, symbol)
        if def_line_list:
            if any(lo <= d <= hi for d in def_line_list for (lo, hi) in terms):
                return None  # a def falls within one term -> OK
            return Drift(
                doc_path=doc_path, doc_line=doc_line_num, target_file=token_file,
                target_line=terms[0][0], kind="def_drift", symbol=symbol,
                suggested_line=None, fixable=False,
                message=(
                    f"`{symbol}` def is at line "
                    f"{def_line_list[0] if len(def_line_list) == 1 else def_line_list}"
                    f", multi-range anchor cites {terms_text.strip()} "
                    f"(none contains the def)"
                ),
                style="inline",
            )
        # 0 def lines -> fall through to bounds-check each term.

    # No symbol (or no def): every term must be in-bounds.
    for (lo, hi) in terms:
        if lo < 1 or hi > n_lines:
            return Drift(
                doc_path=doc_path, doc_line=doc_line_num, target_file=token_file,
                target_line=lo, kind="out_of_bounds", symbol=symbol,
                suggested_line=None, fixable=False,
                message=(
                    f"multi-range term {lo}" + (f"-{hi}" if hi != lo else "")
                    + f" out of bounds (file has {n_lines} lines)"
                ),
                style="inline",
            )
    return None  # all terms in bounds


# ---------------------------------------------------------------------------
# Main checker
# ---------------------------------------------------------------------------

def check_line_anchors(
    doc_paths: list[str], repo_root: Path,
    unbound_sink: "Optional[list[dict]]" = None,
) -> list[Drift]:
    """Check all line-anchors (markdown-link AND inline-backtick) in the given docs.

    unbound_sink: optional audit collector — every anchor that passes BOUNDS-ONLY
    (no symbol bound / 0 defs) is recorded with its enclosing def (--list-unbound).
    Default None = zero behavior change."""
    drifts: list[Drift] = []
    basename_index, git_ok = _build_basename_index(repo_root)
    unresolved_bare = 0   # for the git-absent warning

    for doc_path in doc_paths:
        full_path = Path(doc_path) if Path(doc_path).is_absolute() else repo_root / doc_path
        if not full_path.exists():
            # A silently skipped doc is a FALSE GREEN — the gate reports "no
            # drift" while checking nothing (wrong-root invocation / renamed
            # gated doc, reproduced 2026-06-11). Fail loud instead.
            raise FileNotFoundError(
                f"doc not found: {doc_path} (resolved to {full_path})"
            )
        doc_lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()

        in_fence = False
        multirange_unparseable = 0   # comma-list anchors that could NOT be verified
        slashlist_unparseable = 0    # slash-list anchors that could NOT be verified
        for line_num, line_text in enumerate(doc_lines, 1):
            if _FENCE_RE.match(line_text):
                in_fence = not in_fence
                continue
            if in_fence:
                continue

            # --- markdown-link anchors (existing behavior) ---
            # Positional symbol binding (compound multi-symbol rows): when the line
            # carries N>1 identifier tokens and exactly N link anchors, pair the
            # k-th anchor to the k-th identifier in source order. Otherwise the map
            # is empty and check_anchor's nearest-before rebind applies as before.
            link_matches = list(_ANCHOR_RE.finditer(line_text))
            link_anchor_dicts = [{"start": m.start(), "end": m.end(),
                                  "file": m.group("file"),
                                  "line": int(m.group("line"))} for m in link_matches]
            link_pos_map = _positional_symbol_map(line_text, link_anchor_dicts)
            link_keys = set()
            for m in link_matches:
                target_file_rel = m.group("file")
                target_line = int(m.group("line"))
                link_keys.add((target_file_rel, target_line))
                pos_sym = link_pos_map.get(m.start())
                drift = check_anchor(
                    doc_path=str(full_path), doc_line_num=line_num,
                    doc_line_text=line_text, target_file_rel=target_file_rel,
                    target_line=target_line, display_text=m.group("display"),
                    repo_root=repo_root, doc_col=(m.start(), m.end()),
                    symbol=pos_sym,
                    rebind_symbol=pos_sym is None,
                    unbound_sink=unbound_sink,
                )
                if drift is not None:
                    drifts.append(drift)

            # --- inline-backtick anchors (full + path-less continuation) ---
            # Iterate the full ordered anchor list so compound-cell continuation
            # anchors (`:470` inheriting `lip_sync.py` from `lip_sync.py:177`) are
            # verified, and apply the positional symbol map so the k-th anchor binds
            # to the k-th identifier (fixing the nearest-before mis-binding).
            inline_anchors = _ordered_line_anchors(line_text)
            inline_pos_map = _positional_symbol_map(line_text, inline_anchors)
            for a in inline_anchors:
                token_file = a["file"]
                target_line = a["line"]
                anchor_start = a["start"]
                # de-dup: skip an inline match whose (file,line) equals a link on the
                # same line (rare; correctness guard, not a span-inside heuristic).
                if (token_file, target_line) in link_keys:
                    continue
                a_style = a.get("style", "inline")
                # Symbol: positional pairing when the line matched; else
                # nearest-before — EXCEPT slash-list terms, which are
                # positional-or-bounds-only: nearest-before would bind the
                # cell's last symbol to EVERY term, and --fix would then
                # rewrite correct terms to that symbol's def (corruption).
                symbol = inline_pos_map.get(anchor_start)
                if symbol is None and a_style != "slash":
                    symbol = _bind_inline_symbol(line_text, anchor_start)
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
                end = a["end_line"]
                display = f"{token_file}:{target_line}" + (f"-{end}" if end else "")
                drift = check_anchor(
                    doc_path=str(full_path), doc_line_num=line_num,
                    doc_line_text=line_text, target_file_rel=token_file,
                    target_line=target_line, display_text=display, repo_root=repo_root,
                    resolved_rel=resolved_rel, symbol=symbol,
                    rebind_symbol=False, style=a_style, doc_col=(a["start"], a["end"]),
                    symbol_fallback=(a_style != "slash"
                                     and inline_pos_map.get(anchor_start) is None),
                    unbound_sink=unbound_sink,
                )
                if drift is not None:
                    drifts.append(drift)

            # --- multi-range comma-list anchors (`file:A-B, C-D` / `file:N, M`) ---
            # Verified now (Commit 2): a bound symbol's def must fall within ONE
            # comma-term; with no symbol every term must be in-bounds. Report-only
            # (never fixable). A term that fails to parse, or a bare basename that
            # can't be resolved, keeps the legacy 'NOT verified' warning.
            for m in _MULTIRANGE_RE.finditer(line_text):
                token_file = m.group("file")
                terms_text = m.group("terms")
                mr_symbol = _bind_inline_symbol(line_text, m.start())
                resolved_rel, candidates = _resolve_inline_target(
                    token_file, mr_symbol, basename_index, repo_root)
                if candidates is not None:
                    drifts.append(Drift(
                        doc_path=str(full_path), doc_line=line_num,
                        target_file=token_file, target_line=0,
                        kind="ambiguous_path", symbol=mr_symbol, suggested_line=None,
                        fixable=False,
                        message=(f"`{token_file}` is ambiguous ({len(candidates)} tracked "
                                 f"matches): {', '.join(candidates)} — qualify with a directory"),
                        style="inline", candidates=candidates,
                    ))
                    continue
                if resolved_rel is None:
                    # Unresolved bare basename (not a tracked file, or git absent):
                    # cannot verify -> keep the warning rather than silently skip.
                    multirange_unparseable += 1
                    continue
                if _parse_multirange_terms(terms_text) is None:
                    multirange_unparseable += 1  # a term failed to parse
                    continue
                drift = check_multirange_anchor(
                    doc_path=str(full_path), doc_line_num=line_num,
                    doc_line_text=line_text, token_file=token_file,
                    terms_text=terms_text, repo_root=repo_root,
                    resolved_rel=resolved_rel, symbol=mr_symbol,
                )
                if drift is not None:
                    drifts.append(drift)

            # --- slash-list loose probe (ADV-2: warn, don't silently skip) ---
            # A slash-ish anchor token the STRICT regex could not parse (range
            # term, non-numeric segment) would otherwise vanish exactly the way
            # whole slash cells did pre-slash-support. Spans already claimed by
            # the strict slash regex or by multirange (comma cells) are fine.
            claimed_spans = (
                [(m.start(), m.end()) for m in _SLASHLIST_ANCHOR_RE.finditer(line_text)]
                + [(m.start(), m.end()) for m in _MULTIRANGE_RE.finditer(line_text)]
            )
            for m in _SLASHLIST_LOOSE_RE.finditer(line_text):
                if any(s <= m.start() < e for s, e in claimed_spans):
                    continue
                slashlist_unparseable += 1

        # Any multi-range anchors we could NOT verify (unparseable terms / unresolved
        # bare basename) still warn rather than silently skip (ADV-2 principle).
        if multirange_unparseable:
            print(f"WARNING: {full_path}: {multirange_unparseable} multi-range anchor(s) "
                  f"(e.g. `file.py:A-B, C-D`) could NOT be verified — unparseable terms "
                  f"or unresolved file. Split into single-range anchors to verify.",
                  file=sys.stderr)
        if slashlist_unparseable:
            print(f"WARNING: {full_path}: {slashlist_unparseable} slash-list anchor(s) "
                  f"(e.g. `file.py:N / M`) could NOT be verified — non-bare term "
                  f"(slash lists take bare line numbers only; no ranges). Use bare "
                  f"numbers or split into single anchors.",
                  file=sys.stderr)

        # EOF with the fence still open (ADV-2): an unbalanced/stray fence leaves
        # in_fence=True for the rest of the doc, silently skipping every later
        # anchor — the exact phantom-survival this tool exists to prevent. Warn
        # loudly (we do NOT attempt CommonMark nested-fence close-length matching).
        if in_fence:
            print(f"WARNING: {full_path}: unclosed code fence at EOF — anchors after "
                  f"the last unclosed fence were NOT verified.", file=sys.stderr)

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
    The range separator is accepted as ASCII hyphen, en-dash, or em-dash on read
    and always EMITTED as ASCII hyphen (canonicalization). Other numbers are left
    untouched.
    """
    delta = new - old
    for rm in re.finditer(r':(\d+)[-–—](\d+)', display):
        if int(rm.group(1)) == old:
            end = int(rm.group(2)) + delta
            return display[:rm.start()] + f":{new}-{end}" + display[rm.end():]
    return re.sub(
        r':(\d+)\b',
        lambda m: f":{new}" if int(m.group(1)) == old else m.group(0),
        display,
    )


def _rewrite_anchor_occurrence(occ_text: str, drift: Drift) -> Optional[str]:
    """Rewrite a SINGLE anchor occurrence (the exact substring spanned by
    drift.doc_col) from its stale line to drift.suggested_line.

    Returns the rewritten substring, or None if *occ_text* does not match the
    expected anchor at the expected (file, line) — a span/identity guard so a
    drifted span never rewrites the wrong token. Matched anchor-form is chosen
    by drift.style.
    """
    old, new = drift.target_line, drift.suggested_line
    if drift.style == "slash":
        # A slash-list term's span is its DIGITS only — rewrite the number in
        # place (prefix/separators live outside the span). Identity guard:
        # the span must hold exactly the stale number.
        if re.fullmatch(r'\d+', occ_text) and int(occ_text) == old:
            return str(new)
        return None
    if drift.style == "inline":
        m = _INLINE_ANCHOR_RE.fullmatch(occ_text)
        if m is not None and m.group("file") == drift.target_file and int(m.group("line")) == old:
            end = m.group("end")
            body = _shift_display(
                f"{drift.target_file}:{old}" + (f"-{end}" if end else ""), old, new
            )
            return f"`{body}`"
        # Path-less continuation anchor (`:N` / `:A-B`): the file is inherited
        # from a preceding same-line full anchor, so the occurrence carries NO
        # filename. Rewrite preserving the path-less form (do NOT inject the
        # inherited file — that would corrupt the compound cell's continuation
        # syntax). Identity guard is the line number only (the file was already
        # validated at detection time via the inherited context).
        cm = _CONTINUATION_ANCHOR_RE.fullmatch(occ_text)
        if cm is not None and int(cm.group("line")) == old:
            end = cm.group("end")
            body = _shift_display(f":{old}" + (f"-{end}" if end else ""), old, new)
            return f"`{body}`"
        return None
    # link
    m = _ANCHOR_RE.fullmatch(occ_text)
    if m is None or m.group("file") != drift.target_file or int(m.group("line")) != old:
        return None
    new_display = _shift_display(m.group("display"), old, new)
    return f"[{new_display}]({drift.target_file}:{new})"


def _apply_fixes(drifts: list[Drift]) -> list[Drift]:
    """Apply fixable def_drift corrections in-place. Return remaining (unfixed) drifts.

    Span-based (ADV-1): each fixable drift carries its anchor's (start, end) column
    span on the doc line (drift.doc_col). On a single doc line we rewrite each
    occurrence at its own span, processing RIGHT-to-LEFT (descending start column)
    so a left-side edit never invalidates a still-pending right-side span. This is
    what keeps two same-bare-token-different-resolved-file anchors on one line each
    getting their OWN correct new line (a global keyed regex sub would clobber the
    second). A drift lacking a span (legacy/defensive) falls back to the old global
    keyed sub for that occurrence only.
    """
    def _is_fixable(d: Drift) -> bool:
        return d.kind == "def_drift" and d.fixable and d.suggested_line is not None

    fixable = [d for d in drifts if _is_fixable(d)]
    unfixed = [d for d in drifts if not _is_fixable(d)]

    from collections import defaultdict
    by_line: dict[tuple[str, int], list[Drift]] = defaultdict(list)
    for d in fixable:
        by_line[(d.doc_path, d.doc_line)].append(d)

    # Group the lines back per-doc so we read/write each file once.
    docs: dict[str, set[int]] = defaultdict(set)
    for (doc_path, doc_line) in by_line:
        docs[doc_path].add(doc_line)

    for doc_path, _line_nums in docs.items():
        path = Path(doc_path)
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)

        for doc_line in sorted(_line_nums):
            idx = doc_line - 1  # 0-based
            line_drifts = by_line[(doc_path, doc_line)]

            spanned = [d for d in line_drifts if d.doc_col is not None]
            legacy = [d for d in line_drifts if d.doc_col is None]

            # --- span-based: edit each occurrence by its own column, right-to-left ---
            # Descending start column → leftward splices keep rightward spans valid.
            for drift in sorted(spanned, key=lambda d: d.doc_col[0], reverse=True):
                start, end = drift.doc_col
                occ = lines[idx][start:end]
                replacement = _rewrite_anchor_occurrence(occ, drift)
                if replacement is None:
                    # Span no longer holds the expected anchor (line content shifted
                    # out from under us) — leave it for a human, do NOT corrupt.
                    unfixed.append(drift)
                    continue
                lines[idx] = lines[idx][:start] + replacement + lines[idx][end:]
                print(f"  FIXED  {doc_path}:{doc_line}  "
                      f"{drift.target_file}:{drift.target_line} → "
                      f"{drift.target_file}:{drift.suggested_line}")

            # --- legacy fallback (no span): old global keyed sub for this drift ---
            for drift in legacy:
                old, new = drift.target_line, drift.suggested_line

                def _rewrite_link(m, _d=drift, _old=old, _new=new):
                    if m.group("file") != _d.target_file or int(m.group("line")) != _old:
                        return m.group(0)
                    new_display = _shift_display(m.group("display"), _old, _new)
                    return f"[{new_display}]({_d.target_file}:{_new})"

                def _rewrite_inline(m, _d=drift, _old=old, _new=new):
                    if m.group("file") != _d.target_file or int(m.group("line")) != _old:
                        return m.group(0)
                    end = m.group("end")
                    body = _shift_display(
                        f"{_d.target_file}:{_old}" + (f"-{end}" if end else ""), _old, _new
                    )
                    return f"`{body}`"

                lines[idx] = _ANCHOR_RE.sub(_rewrite_link, lines[idx])
                lines[idx] = _INLINE_ANCHOR_RE.sub(_rewrite_inline, lines[idx])
                print(f"  FIXED  {doc_path}:{doc_line}  "
                      f"{drift.target_file}:{old} → {drift.target_file}:{new}")

        path.write_text("".join(lines), encoding="utf-8")

    return unfixed


def _split_advisories(drifts: list[Drift]) -> "tuple[list[Drift], list[Drift]]":
    """Partition into (fatal, advisory) by kind. Advisories are exit-code-neutral."""
    fatal = [d for d in drifts if d.kind not in ADVISORY_KINDS]
    advisory = [d for d in drifts if d.kind in ADVISORY_KINDS]
    return fatal, advisory


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
# NOTE: the per-rule "Codified SHA:" provenance that used to live in CLAUDE.md /
# AGENTS.md was relocated to docs/protocol/{claude,agents}/director-operator.md by
# the operative/provenance split (manifest: docs/protocol/migration-map-claudemd-split.md);
# those files are included here so --sha-refs still covers the relocated provenance.
SHA_DEFAULT_DOCS = [
    "CLAUDE.md",
    "AGENTS.md",
    "DECISIONS.md",
    "ARCHITECTURE.md",
    "docs/protocol/claude/director-operator.md",
    "docs/protocol/agents/director-operator.md",
]

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
            # Same false-green guard as check_line_anchors: never skip a
            # requested doc silently.
            raise FileNotFoundError(
                f"doc not found: {doc_path} (resolved to {full})"
            )
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


def run(doc_paths: list[str], repo_root: Path, fix: bool = False,
        exclude_targets: "Optional[list[str]]" = None) -> list[Drift]:
    """Run all enabled checkers; apply fixes when fix=True. Return remaining drift.

    exclude_targets: when fixing, hold back any drift whose target file contains one
    of these substrings (e.g. a source file under active edit by a concurrent seat).
    Excluded drifts are still DETECTED and remain in the return value — they are
    simply not auto-fixed — so a sweep can fix the stable subset now and defer
    in-flight-file anchors (which would only re-drift) to a later pass.
    """
    exclude_targets = exclude_targets or []

    def _excluded(d: Drift) -> bool:
        return bool(exclude_targets) and any(p in (d.target_file or "") for p in exclude_targets)

    all_drifts: list[Drift] = []
    for checker in CHECKERS:
        all_drifts.extend(checker(doc_paths, repo_root))

    if not fix:
        return all_drifts

    # Apply fixes to convergence. A single _apply_fixes pass is span-safe but not
    # always idempotent: when a fixable anchor's span overlaps another (e.g. an
    # inline anchor nested inside a drifting markdown-link display), the span/
    # identity guard in _rewrite_anchor_occurrence DEFERS the outer anchor (leaves
    # it unfixed) rather than risk a wrong rewrite (NC-MINOR-1). Re-detecting after
    # each pass lets the deferred anchor settle and be fixed next pass. Bounded so a
    # pathologically non-applying drift cannot spin forever — it surfaces as a warning
    # plus the residual drift in the return value (non-zero exit at the CLI level).
    # exclude_targets are held back from _apply_fixes AND excluded from the
    # convergence predicate, so the loop terminates with them still flagged (deferred).
    _MAX_FIX_PASSES = 10
    for _ in range(_MAX_FIX_PASSES):
        _apply_fixes([d for d in all_drifts if not _excluded(d)])
        all_drifts = []
        for checker in CHECKERS:
            all_drifts.extend(checker(doc_paths, repo_root))
        # mirrors _is_fixable (nested in _apply_fixes): a def_drift with a concrete
        # suggested line is the only auto-applyable kind.
        if not any(d.kind == "def_drift" and d.fixable and d.suggested_line is not None
                   and not _excluded(d) for d in all_drifts):
            break
    else:
        print(f"WARNING: --fix did not converge after {_MAX_FIX_PASSES} passes; "
              f"fixable drift remains (possible overlapping/pathological anchors) — "
              f"re-run --fix or correct by hand.", file=sys.stderr)

    return all_drifts


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
        "--list-unbound", action="store_true",
        help="Audit-only: list anchors that verify BOUNDS-ONLY (no symbol binding), "
             "with the enclosing def at the cited line. Never gates (exit 0). "
             "Covers link/inline/continuation anchors; multirange anchors are "
             "verified separately and not audited here.",
    )
    parser.add_argument(
        "--exclude-target", action="append", default=[], metavar="SUBSTR",
        help="With --fix, skip drifts whose target file contains SUBSTR (repeatable). "
             "Defers anchors into files under concurrent edit; they stay flagged, not fixed.",
    )
    parser.add_argument(
        "docs",
        nargs="*",
        help=(
            "Markdown doc(s) to check (relative to repo root). Default: ARCHITECTURE.md "
            "for anchors; for --sha-refs/--show-subjects the SHA-dense set "
            "(CLAUDE.md, AGENTS.md, DECISIONS.md, ARCHITECTURE.md, and the relocated "
            "docs/protocol/{claude,agents}/director-operator.md provenance)."
        ),
    )
    args = parser.parse_args(argv)

    # Repo root = parent of scripts/ (this file's parent's parent)
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent

    sha_mode = args.sha_refs or args.show_subjects
    docs = args.docs or (SHA_DEFAULT_DOCS if sha_mode else ["ARCHITECTURE.md"])

    # Missing docs fail loud (exit 2) — a skipped doc would be a false green.
    missing = [
        d for d in docs
        if not (Path(d) if Path(d).is_absolute() else repo_root / d).exists()
    ]
    if missing:
        for d in missing:
            print(f"ERROR: doc not found: {d} (repo root: {repo_root})")
        return 2

    if args.list_unbound:
        sink: list[dict] = []
        check_line_anchors(docs, repo_root, unbound_sink=sink)
        print(f"UNBOUND-ANCHOR AUDIT  ({len(sink)} bounds-only anchor(s) "
              f"across {len(docs)} doc(s)) — advisory, exit-neutral")
        for e in sink:
            if e.get("usage_cite"):
                sym = f" (usage-cite of `{e['symbol']}`)"
            else:
                sym = f" (bound `{e['symbol']}`: 0 defs)" if e["symbol"] else ""
            enc = e["enclosing"] or "<module level>"
            print(f"  {e['doc_path']}:{e['doc_line']}  →  "
                  f"{e['target_file']}:{e['target_line']}  enclosing: {enc}{sym}")
        return 0

    if args.show_subjects:
        return _print_sha_subjects(docs, repo_root)

    if args.sha_refs:
        return _report_sha_drifts(check_sha_refs(docs, repo_root), len(docs))

    drifts = run(docs, repo_root, fix=args.fix, exclude_targets=args.exclude_target)
    fatal, advisories = _split_advisories(drifts)

    if not fatal and not advisories:
        print(f"{'All' if not args.fix else 'Remaining'} anchors checked — no drift.")
        return 0

    if fatal:
        print(f"\n{'='*60}")
        print(f"DOC-ANCHOR DRIFT REPORT  ({len(fatal)} issue(s))")
        print(f"{'='*60}")
        for d in fatal:
            fix_hint = f"  → suggested: line {d.suggested_line}" if d.suggested_line else ""
            print(
                f"  [{d.kind}]  {d.doc_path}:{d.doc_line}"
                f"  →  {d.target_file}:{d.target_line}"
                + (f"  (symbol: `{d.symbol}`)" if d.symbol else "")
                + fix_hint
            )
            print(f"    {d.message}")
        fixable_count = sum(1 for d in fatal if d.fixable)
        if fixable_count:
            print(f"\n{fixable_count} fixable def_drift(s). Run: "
                  f".venv/bin/python scripts/check_doc_claims.py --fix")
        unfixable = [d for d in fatal if not d.fixable]
        if unfixable:
            print(f"{len(unfixable)} drift(s) require manual intervention.")

    if advisories:
        print(f"\n{'-'*60}")
        print(f"ADVISORIES  ({len(advisories)} ambiguous anchor(s) — exit-neutral)")
        print(f"{'-'*60}")
        for d in advisories:
            print(f"  [{d.kind}]  {d.doc_path}:{d.doc_line}  `{d.target_file}:{d.target_line}`")
            print(f"    {d.message}")

    return 1 if fatal else 0


if __name__ == "__main__":
    sys.exit(main())
