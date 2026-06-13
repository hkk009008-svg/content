#!/usr/bin/env python3
"""scripts/status.py — live "where are we" snapshot of the repo/program state.

Usage
-----
  .venv/bin/python scripts/status.py            # print to stdout
  .venv/bin/python scripts/status.py --write    # stdout + write STATUS.md

Design constraints
------------------
* NEVER hangs or crashes. Every data source is wrapped so a slow/unreachable/
  failing source renders "(unavailable: <reason>)" and the rest still prints.
* stdlib only (urllib, subprocess, re, pathlib, datetime …).
* Pure helpers (count_unread, latest_adr, render) are fully testable.
* I/O collectors (collect_*) each return a value or "(unavailable: ...)" string.
* main(argv=None) -> int always returns 0; the dashboard reports, doesn't gate.

Repo root is resolved as the parent of this file's parent (scripts/ → repo/).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Repo root (works from any CWD)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent


# ===========================================================================
# Pure helpers — TDD'd
# ===========================================================================

# ---------------------------------------------------------------------------
# count_unread
# ---------------------------------------------------------------------------

_TS_LEN = 20  # length of "2026-05-28T20-38-34Z"

# Pattern: <ts>-<from>-to-<to>-<kind>.md
# We extract: ts (first 20 chars), to-seat (segment after "-to-")
_EVENT_RE = re.compile(
    r'^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)'
    r'-\w+-to-(?P<to>\w+)-'
    r'.+\.md$'
)


def _normalize_ts(ts: str) -> str:
    """Normalize a timestamp to dash form: colons → dashes."""
    return ts.replace(":", "-")


def count_unread(cursor_ts: str, event_filenames: list[str], seat: str) -> int:
    """Return the number of events addressed to *seat* whose timestamp is
    STRICTLY GREATER THAN *cursor_ts*.

    Normalization: cursor may use colons (T20:38:34Z); filenames always use
    dashes (T20-38-34Z). Both are normalized to dashes before comparison.
    Malformed filenames are silently skipped.
    """
    cursor_norm = _normalize_ts(cursor_ts)
    count = 0
    for fname in event_filenames:
        m = _EVENT_RE.match(fname)
        if not m:
            continue
        event_ts = m.group("ts")   # already dashes
        event_to = m.group("to")
        # `all` is a broadcast target → addressed to every real seat (4-seat
        # protocol). _EVENT_RE's (?P<to>\w+) already matches director2/operator2.
        if event_to != seat and event_to != "all":
            continue
        if event_ts > cursor_norm:
            count += 1
    return count


# ---------------------------------------------------------------------------
# latest_adr
# ---------------------------------------------------------------------------

# Matches "## ADR-NNN" or "## ADR-NNN — " etc.; NNN must be all digits.
_ADR_RE = re.compile(
    r'^##\s+ADR-(?P<num>\d+)'   # "## ADR-017"
    r'(?:\s*[—–-]+\s*(?P<title>.+))?',  # optional " — <title>"
    re.MULTILINE,
)


def latest_adr(text: str) -> Optional[tuple[int, str]]:
    """Return (highest_adr_number, title_line) from *text*, or None if absent.

    Headings like "## ADR-NNN — <title>" or "## ADR-NNN — <title>: detail".
    Template placeholders (ADR-NNN with non-digit NNN) are ignored.
    """
    best_num: Optional[int] = None
    best_title: str = ""
    for m in _ADR_RE.finditer(text):
        num = int(m.group("num"))
        title_raw = (m.group("title") or "").strip()
        if best_num is None or num > best_num:
            best_num = num
            best_title = title_raw
    if best_num is None:
        return None
    return (best_num, best_title)


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------

_STATUS_ORDER = ["live", "wired", "stubbed", "parked", "dead"]


def render_manifest(components: Optional[list]) -> list[str]:
    """Return lines for the '## Pipeline status (manifest)' section.

    *components* is the list returned by check_doc_claims.audit_manifest,
    or None/[] when no manifest exists.

    Returns a list of strings (no trailing newlines).
    """
    lines: list[str] = []
    lines.append("## Pipeline status (manifest)")

    if components is None:
        lines.append("  (no docs/pipeline_status.toml)")
        lines.append("  source:  docs/pipeline_status.toml (validated by check_doc_claims.audit_manifest)")
        return lines

    if not components:
        lines.append("  (no docs/pipeline_status.toml)")
        lines.append("  source:  docs/pipeline_status.toml (validated by check_doc_claims.audit_manifest)")
        return lines

    # Group by status in canonical order; unknown statuses go last
    grouped: dict[str, list] = {s: [] for s in _STATUS_ORDER}
    other: list = []
    for comp in components:
        status = comp.get("status", "")
        if status in grouped:
            grouped[status].append(comp)
        else:
            other.append(comp)

    for status in _STATUS_ORDER:
        for comp in grouped[status]:
            anchor = comp.get("anchor", "")
            # Split anchor for display: file_rel + symbol
            if anchor and ":" in anchor:
                file_rel, symbol = anchor.rsplit(":", 1)
            else:
                file_rel, symbol = anchor, ""

            if comp.get("valid"):
                line_num = comp.get("current_line")
                lines.append(
                    f"  ✓ {comp['id']}  ({status})  {file_rel}:{symbol} @{line_num}"
                    f"  — {comp['title']}"
                )
            else:
                problem = comp.get("problem", "unknown problem")
                lines.append(
                    f"  ✗ {comp['id']}  ({status})  {file_rel}:{symbol}"
                    f"  [BROKEN: {problem}]"
                )

    for comp in other:
        anchor = comp.get("anchor", "")
        if anchor and ":" in anchor:
            file_rel, symbol = anchor.rsplit(":", 1)
        else:
            file_rel, symbol = anchor, ""
        status = comp.get("status", "unknown")
        if comp.get("valid"):
            line_num = comp.get("current_line")
            lines.append(
                f"  ✓ {comp['id']}  ({status})  {file_rel}:{symbol} @{line_num}"
                f"  — {comp['title']}"
            )
        else:
            problem = comp.get("problem", "unknown problem")
            lines.append(
                f"  ✗ {comp['id']}  ({status})  {file_rel}:{symbol}"
                f"  [BROKEN: {problem}]"
            )

    lines.append("  source:  docs/pipeline_status.toml (validated by check_doc_claims.audit_manifest)")
    return lines


def render(data: dict) -> str:
    """Format an already-collected data dict into the report string.

    All values are pre-collected; this function is pure (no I/O).
    "(unavailable: ...)" strings are passed through verbatim.
    """
    lines: list[str] = []
    a = lines.append

    a(f"# Repo Status  |  generated {data['generated_at']}  |  derived live — do not hand-edit")
    a("")

    # --- Git ---
    a("## Git")
    a(f"  sha:     {data['git_sha']}")
    a(f"  subject: {data['git_subject']}")
    a(f"  branch:  {data['git_branch']}")
    ahead = data['git_ahead']
    behind = data['git_behind']
    a(f"  origin:  {ahead} ahead / {behind} behind origin/main")
    a(f"  dirty:   {data['git_dirty']} file(s) with uncommitted changes")
    a("  source:  git rev-parse, git log -1, git status --porcelain")
    a("")

    # --- Coordination ---
    a("## Coordination (mailbox)")
    a(f"  operator  cursor={data['mailbox_operator_cursor']}  "
      f"unread={data['mailbox_operator_unread']}")
    a(f"  director  cursor={data['mailbox_director_cursor']}  "
      f"unread={data['mailbox_director_unread']}")
    a("  source:  coordination/mailbox/seen/*.txt + coordination/mailbox/sent/")
    a("")

    # --- Decisions ---
    a("## Decisions")
    a(f"  latest ADR: {data['latest_adr']}")
    a("  source:  DECISIONS.md  (grep ^## ADR-NNN)")
    a("")

    # --- Doc integrity ---
    a("## Doc integrity")
    a(f"  anchor-drift: {data['doc_integrity']}")
    a("  source:  scripts/check_doc_claims.py (ARCHITECTURE.md)")
    a("")

    # --- Pod ---
    a("## Infra (GPU pod / ComfyUI)")
    a(f"  pod: {data['pod_status']}")
    a("  source:  .env COMFYUI_SERVER_URL → <url>/system_stats (timeout=3s)")
    a("")

    # --- Pipeline manifest ---
    manifest_components = data.get("manifest_components")
    manifest_lines = render_manifest(manifest_components)
    lines.extend(manifest_lines)
    a("")

    # --- Smoke pointer ---
    a("## Smoke test")
    a("  smoke: run `.venv/bin/python scripts/ci_smoke.py`")
    a("  (not run inline — too heavy for a status command)")

    return "\n".join(lines) + "\n"


# ===========================================================================
# I/O collectors — each returns a value or "(unavailable: <reason>)"
# ===========================================================================

def _run_git(args: list[str], timeout: int = 5) -> str:
    """Run a git command; return stdout stripped or raise."""
    result = subprocess.run(
        ["git"] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {args[0]} failed")
    return result.stdout.strip()


def collect_git(repo_root: Path) -> dict:
    """Collect git state. Each field is a value or '(unavailable: ...)'."""

    def _get(label: str, args: list[str]):
        try:
            return _run_git(args)
        except Exception as e:
            return f"(unavailable: {label}: {e})"

    sha = _get("sha", ["rev-parse", "--short", "HEAD"])
    subject = _get("subject", ["log", "-1", "--format=%s"])
    branch = _get("branch", ["rev-parse", "--abbrev-ref", "HEAD"])

    try:
        ahead_raw = _run_git(["rev-list", "--count", "origin/main..HEAD"])
        ahead = int(ahead_raw)
    except Exception as e:
        ahead = f"(unavailable: ahead: {e})"

    try:
        behind_raw = _run_git(["rev-list", "--count", "HEAD..origin/main"])
        behind = int(behind_raw)
    except Exception as e:
        behind = f"(unavailable: behind: {e})"

    try:
        status_out = _run_git(["status", "--porcelain"])
        dirty = len([l for l in status_out.splitlines() if l.strip()])
    except Exception as e:
        dirty = f"(unavailable: dirty: {e})"

    return {
        "git_sha": sha,
        "git_subject": subject,
        "git_branch": branch,
        "git_ahead": ahead,
        "git_behind": behind,
        "git_dirty": dirty,
    }


def _read_cursor(path: Path) -> str:
    """Read a cursor file; return the timestamp string or '(unavailable: ...)'."""
    try:
        return path.read_text().strip()
    except Exception as e:
        return f"(unavailable: {e})"


def collect_mailbox(repo_root: Path) -> dict:
    """Collect mailbox unread counts and cursors."""
    sent_dir = repo_root / "coordination" / "mailbox" / "sent"
    seen_dir = repo_root / "coordination" / "mailbox" / "seen"

    try:
        event_filenames = [p.name for p in sent_dir.iterdir() if p.is_file()]
    except Exception as e:
        unavail = f"(unavailable: {e})"
        return {
            "mailbox_operator_unread": unavail,
            "mailbox_operator_cursor": unavail,
            "mailbox_director_unread": unavail,
            "mailbox_director_cursor": unavail,
        }

    op_cursor = _read_cursor(seen_dir / "operator.txt")
    dir_cursor = _read_cursor(seen_dir / "director.txt")

    try:
        op_unread = count_unread(op_cursor, event_filenames, "operator")
    except Exception as e:
        op_unread = f"(unavailable: {e})"

    try:
        dir_unread = count_unread(dir_cursor, event_filenames, "director")
    except Exception as e:
        dir_unread = f"(unavailable: {e})"

    return {
        "mailbox_operator_unread": op_unread,
        "mailbox_operator_cursor": op_cursor,
        "mailbox_director_unread": dir_unread,
        "mailbox_director_cursor": dir_cursor,
    }


def collect_adr(repo_root: Path) -> dict:
    """Read DECISIONS.md and extract the latest ADR."""
    try:
        text = (repo_root / "DECISIONS.md").read_text(encoding="utf-8")
        result = latest_adr(text)
        if result is None:
            return {"latest_adr": "(unavailable: no ADR headings found)"}
        num, title = result
        label = f"ADR-{num:03d}"
        if title:
            label += f" — {title}"
        return {"latest_adr": label}
    except Exception as e:
        return {"latest_adr": f"(unavailable: {e})"}


def collect_doc_integrity(repo_root: Path) -> dict:
    """Run check_doc_claims on ARCHITECTURE.md; return drift count or 'clean'."""
    try:
        # scripts/ is already on sys.path when running scripts/status.py
        scripts_dir = str(repo_root / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import check_doc_claims  # type: ignore
        drifts = check_doc_claims.run(["ARCHITECTURE.md"], repo_root)
        n = len(drifts)
        if n == 0:
            val = "clean"
        else:
            val = f"{n} drift(s) — run check_doc_claims.py --fix"
        return {"doc_integrity": val}
    except Exception as e:
        return {"doc_integrity": f"(unavailable: {e})"}


def _parse_env_key(repo_root: Path, key: str) -> Optional[str]:
    """Read KEY=VALUE from .env file. Returns value or None if absent/error."""
    env_path = repo_root / ".env"
    try:
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{key}="):
                return line[len(key) + 1:].strip().strip('"').strip("'")
    except Exception:
        pass  # .env missing or unreadable — caller falls back to env-var or None
    return None


def _probe_url(url: str, timeout: int = 3) -> str:
    """Probe <url>/system_stats; return 'UP' or 'DOWN'."""
    try:
        probe = url.rstrip("/") + "/system_stats"
        with urllib.request.urlopen(probe, timeout=timeout) as resp:
            if resp.status == 200:
                return "UP"
            return f"DOWN (HTTP {resp.status})"
    except Exception:
        return "DOWN"


def collect_pod(repo_root: Path) -> dict:
    """Probe the ComfyUI pod via COMFYUI_SERVER_URL from .env."""
    url = _parse_env_key(repo_root, "COMFYUI_SERVER_URL")
    if not url:
        return {"pod_status": "(unavailable: no COMFYUI_SERVER_URL)"}
    status = _probe_url(url, timeout=3)
    return {"pod_status": status}


def collect_manifest(repo_root: Path) -> dict:
    """Load and validate docs/pipeline_status.toml via check_doc_claims.audit_manifest.

    Returns {"manifest_components": list} where list may be:
      - a list of component dicts (from audit_manifest)
      - [] when the manifest file is absent
      - None when unavailable due to an error (rendered as unavailable sentinel)
    """
    try:
        scripts_dir = str(repo_root / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import check_doc_claims  # type: ignore
        manifest_path = repo_root / "docs" / "pipeline_status.toml"
        components = check_doc_claims.audit_manifest(manifest_path, repo_root)
        # audit_manifest returns [] if file absent — pass through as-is
        return {"manifest_components": components}
    except Exception as e:
        return {"manifest_components": None}


# ===========================================================================
# Main
# ===========================================================================

def _collect_all(repo_root: Path) -> dict:
    """Collect all data sources into a single flat dict."""
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data: dict = {"generated_at": now}
    data.update(collect_git(repo_root))
    data.update(collect_mailbox(repo_root))
    data.update(collect_adr(repo_root))
    data.update(collect_doc_integrity(repo_root))
    data.update(collect_pod(repo_root))
    data.update(collect_manifest(repo_root))
    return data


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print a live status snapshot of the repo.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default=None,
        help="optional subcommand: 'mailbox-unread' (print one seat's live unread count)",
    )
    parser.add_argument(
        "seat",
        nargs="?",
        default=None,
        help="seat for 'mailbox-unread': operator | director",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Also write the report to STATUS.md at the repo root.",
    )
    args = parser.parse_args(argv)

    repo_root = _REPO_ROOT

    # Focused subcommand: print just one seat's LIVE unread count and exit.
    # Reuses the canonical count_unread (via collect_mailbox) — one source of
    # truth, no second copy of the logic — and skips the heavy dashboard (no
    # ComfyUI pod probe / doc reads). This is the instrument Rule #20.1
    # live-recompute should call instead of a hand-rolled `ls|awk` (which has
    # two proven sharp edges: full-filename-vs-bare-prefix over-count, and
    # field-split capturing trailing text).
    if args.command == "mailbox-unread":
        if args.seat not in ("operator", "director"):
            parser.error("mailbox-unread requires a seat: operator | director")
        print(collect_mailbox(repo_root)[f"mailbox_{args.seat}_unread"])
        return 0
    if args.command is not None:
        parser.error(f"unknown command: {args.command!r}")

    data = _collect_all(repo_root)
    report = render(data)

    print(report, end="")

    if args.write:
        out_path = repo_root / "STATUS.md"
        out_path.write_text(report, encoding="utf-8")
        print("(wrote STATUS.md)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
