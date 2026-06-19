#!/usr/bin/env python3
"""consume_reviewer_result.py — the instrument that consumes a `reviewer-result/1` block.

ADR-032 shipped a machine-readable reviewer-result schema (docs/templates/claude/reviewer.md)
but DEFERRED its consumer: an unconsumed schema is itself ceremony (ADR-028). This is that
consumer. Given a verification-report event (a `coordination/mailbox/sent/*verification-report*.md`
file, or stdin), it:

  1. EXTRACTS the `reviewer-result/1` json block (the LAST one, the schema is emitted last).
  2. VALIDATES the schema invariants (pass/issues/unable_to_verify discipline).
  3. DETECTS FABRICATION — re-runs the pytest command(s) the reviewer *claims* it ran and
     diffs the real summary against the reported one. This is the central value: a reviewer
     can paste a fake "N passed" it never executed; a fabricated summary is a HARD FAIL.
     The re-runner executes ONLY a canonical pytest argv (never a shell, never a bare script
     or arbitrary binary) and confines targets to within repo_root — but pytest itself imports
     conftest.py from the target path, so run it with the tree AT the reviewed commit.
  4. MAPS reviewer severity -> inventory severity and PROPOSES (never applies) the
     docs/REMEDIATION-INVENTORY.md status transitions the verdict implies.

The mailbox-level block stays OPTIONAL (an absent block is "nothing to consume", exit 0);
only a PRESENT-but-invalid or PRESENT-but-fabricated block is a hard fail. The fabrication
re-run only makes sense with the working tree AT the reviewed commit, so it lives in the
on-demand CLI — `smoke_check()` (wired into ci_smoke) does schema-validation ONLY, never the
re-run (re-running a historical event's pins against today's HEAD would false-alarm).

Severity map (ADR-032): critical->CRITICAL, important->MAJOR, minor->MEDIUM.

Usage:
    .venv/bin/python scripts/consume_reviewer_result.py <event.md>     # consume a file (re-runs pins)
    .venv/bin/python scripts/consume_reviewer_result.py --stdin        # consume from stdin
Exit codes:
    0 — no block to consume, OR block present + schema-valid + summaries honest
    1 — block present and a schema invariant is violated OR a fabricated summary was detected
    2 — usage error
"""
from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

SCHEMA_VERSION = "reviewer-result/1"

# Reviewer severity (issues[].severity) -> REMEDIATION-INVENTORY.md severity (ADR-032).
SEVERITY_MAP = {"critical": "CRITICAL", "important": "MAJOR", "minor": "MEDIUM"}

# The only `unable_to_verify` triggers (reviewer.md Evidence preamble).
UTV_REASONS = {"U1", "U2", "U3", "U4", "U5"}

VERDICTS = {"pass", "issues", "unable_to_verify"}

# Fenced ```json blocks. Non-greedy body up to the closing fence. Tolerates leading
# horizontal indentation on the fence lines (a fence may be nested in a markdown list).
_JSON_FENCE_RE = re.compile(r"^[ \t]*```json[ \t]*\n(.*?)\n[ \t]*```", re.DOTALL | re.MULTILINE)


class ResultParseError(ValueError):
    """A fence claims to be `reviewer-result/1` but is not valid JSON.

    Distinct from "no block present" (None) — a malformed block of our own schema
    is a real defect to surface, not a silently-skipped absence.
    """


# ---------------------------------------------------------------------------
# 1. Extraction
# ---------------------------------------------------------------------------

def extract_result_block(text: str) -> dict | None:
    """Return the LAST `reviewer-result/1` json object in `text`, or None if absent.

    A fenced ```json block that mentions our schema string but fails to parse raises
    ResultParseError (don't hide a malformed result as "no block"). Unrelated json
    blocks (other schema_version) are ignored.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")  # tolerate CRLF / lone-CR events
    found: list[dict] = []
    for body in _JSON_FENCE_RE.findall(text):
        # Only treat a MALFORMED fence as our (raisable) block if it carries the
        # schema_version KEY — not merely the version string somewhere in prose.
        looks_ours = '"schema_version"' in body and SCHEMA_VERSION in body
        try:
            obj = json.loads(body)
        except json.JSONDecodeError as exc:
            if looks_ours:
                raise ResultParseError(
                    f"fence carries the {SCHEMA_VERSION} schema_version but is not valid JSON: {exc}"
                ) from exc
            continue
        if isinstance(obj, dict) and obj.get("schema_version") == SCHEMA_VERSION:
            found.append(obj)
    return found[-1] if found else None


# ---------------------------------------------------------------------------
# 2. Schema validation
# ---------------------------------------------------------------------------

def validate_schema(result: dict) -> list[str]:
    """Return a list of invariant violations (empty == valid).

    Invariants (reviewer.md / ADR-032):
      - verdict ∈ {pass, issues, unable_to_verify}
      - pass            ⇒ issues empty
      - issues          ⇒ ≥1 entry
      - unable_to_verify ⇒ issues empty AND unverifiable_reason ∈ U1..U5 AND blocked non-null
      - reviewed_head == reviewed_commit unless verdict == unable_to_verify (else forced U4)
      - working_tree_clean == false co-occurs ONLY with unable_to_verify
    """
    v: list[str] = []
    verdict = result.get("verdict")

    # Type-guard the containers FIRST: a wrong-type block must be a clean schema
    # violation, never an uncaught crash in a downstream iterator (R6 / recheck).
    issues = result.get("issues")
    if issues is None:
        issues = []
    elif not isinstance(issues, list):
        v.append(f"`issues` must be a list, got {type(issues).__name__}")
        issues = []
    commands = result.get("commands")
    if commands is not None and not isinstance(commands, list):
        v.append(f"`commands` must be a list, got {type(commands).__name__}")

    if verdict not in VERDICTS:
        v.append(f"verdict {verdict!r} is not one of {sorted(VERDICTS)}")

    if verdict == "pass" and issues:
        v.append("verdict 'pass' requires issues to be empty (a clean pass has zero issues)")
    if verdict == "issues" and not issues:
        v.append("verdict 'issues' requires a non-empty issues list (≥1 entry)")
    if verdict == "unable_to_verify":
        if issues:
            v.append("verdict 'unable_to_verify' requires issues to be empty (the code is unjudged)")
        reason = result.get("unverifiable_reason")
        if reason not in UTV_REASONS:
            v.append(
                f"unable_to_verify requires unverifiable_reason ∈ {sorted(UTV_REASONS)}, got {reason!r}"
            )
        if result.get("blocked") is None:
            v.append("unable_to_verify requires a non-null `blocked` naming the failing command")

    reviewed_head = result.get("reviewed_head")
    reviewed_commit = result.get("reviewed_commit")
    if reviewed_head != reviewed_commit and verdict != "unable_to_verify":
        v.append(
            f"reviewed_head ({reviewed_head!r}) != reviewed_commit ({reviewed_commit!r}) "
            "is only valid with verdict 'unable_to_verify' (U4 — cannot prove the right code was read)"
        )

    if result.get("working_tree_clean") is False and verdict != "unable_to_verify":
        v.append(
            "working_tree_clean=false co-occurs ONLY with verdict 'unable_to_verify' (U3); "
            f"a {verdict!r} verdict requires a clean tree over the reviewed paths"
        )

    return v


# ---------------------------------------------------------------------------
# 3. Fabrication detection — re-run the reported pytest, diff the real summary
# ---------------------------------------------------------------------------

# Count tokens in a pytest summary line. Warnings are excluded from the compared
# set: they are non-deterministic noise, not a test outcome.
_OUTCOME_RE = re.compile(
    r"(\d+)\s+(passed|failed|errors?|skipped|xfailed|xpassed|deselected|warnings?)\b"
)
_COMPARED_OUTCOMES = {"passed", "failed", "error", "skipped", "xfailed", "xpassed", "deselected"}

# Shell metacharacters that, if present, mean we refuse to execute the string
# (it is not a clean single command). We never run the reviewer's command via a shell.
_SHELL_METACHARS = set(";&|<>`$(){}\n\\")

_PYTHON_RE = re.compile(r"python[\d.]*$")  # python, python3, python3.13, .venv/bin/python
_PYTEST_RE = re.compile(r"pytest$")        # pytest, .venv/bin/pytest console script
_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")  # env VAR=value prefix token


def parse_pytest_summary(text: str) -> dict[str, int]:
    """Normalize a pytest summary (or full output) to {outcome: count}, duration dropped.

    Takes the LAST outcome-bearing line (the tail summary). The `in <duration>s` tail
    and any `warning(s)` count are deliberately ignored — they are non-deterministic
    and would make an honest report look fabricated.
    """
    summary_line = ""
    for raw in text.splitlines():
        line = raw.strip().strip("=").strip()
        if line and _OUTCOME_RE.search(line):
            summary_line = line
    counts: dict[str, int] = {}
    for n, outcome in _OUTCOME_RE.findall(summary_line):
        if outcome.startswith("error"):
            key = "error"
        elif outcome.startswith("warning"):
            key = "warning"
        else:
            key = outcome
        if key not in _COMPARED_OUTCOMES:
            continue
        counts[key] = counts.get(key, 0) + int(n)
    return counts


def safe_pytest_argv(command: str) -> list[str] | None:
    """Return a clean argv IFF `command` is a safe-to-re-run pytest invocation, else None.

    SECURITY: the command string comes from an UNTRUSTED mailbox event, and the returned
    argv is handed straight to subprocess.run(argv) (NO shell). A presence check ("`pytest`
    appears as a token") is bypassable (`python evil.py pytest`, `env ./evil pytest`,
    `env PATH=/tmp/evil pytest`), so we enforce STRUCTURE:
      (a) no shell metacharacters; (b) parses cleanly with shlex;
      (c) an optional env prefix is the BARE word `env` followed by ONLY `-u NAME` unsets
          (the repo idiom `env -u GIT_INDEX_FILE …`). A `VAR=value` assignment (PATH=,
          PYTHONPATH=, LD_PRELOAD=, …) is REFUSED — it redirects what env/the interpreter
          loads. A path-y `env` token (`/tmp/evil/env`) does NOT qualify as the prefix;
      (d) the launcher carries a path separator (a bare basename is PATH-resolved — the
          redirection vector) and is EITHER a `python`-family interpreter immediately
          followed by `-m pytest`, OR a `pytest` console-script basename run directly.
    Anything else (a script path, an arbitrary binary under env, a git/util command, a
    shell-chained payload) returns None and is NEVER executed. We never use shell=True.

    NOTE: this vets the INVOCATION only. pytest still imports `conftest.py` from the target
    path at collection, so the re-run is only as trusted as the tree it runs against — the
    caller (recheck_commands) additionally confines targets to within repo_root.
    """
    if any(c in command for c in _SHELL_METACHARS):
        return None
    try:
        argv = shlex.split(command)
    except ValueError:
        return None
    if not argv:
        return None

    rest = argv
    if rest[0] == "env":
        # Strip an env prefix of ONLY `-u NAME` unsets (the repo idiom
        # `env -u GIT_INDEX_FILE …`). The token must be the BARE word `env`: a path
        # whose basename is `env` (e.g. `/tmp/evil/env`) is what subprocess.run would
        # actually exec as argv[0], so it must NOT qualify as the prefix (else the
        # downstream launcher check vets `.venv/bin/python` while env runs the attacker
        # binary). A NAME=value ASSIGNMENT is an injection vector too — `env
        # PATH=/tmp/evil pytest` makes env resolve a hostile `pytest` (ACE) — so any
        # assignment or other env option is refused outright.
        rest = rest[1:]
        i = 0
        while i < len(rest) and rest[i] == "-u" and i + 1 < len(rest):
            i += 2
        rest = rest[i:]
        if not rest or rest[0].startswith("-") or _ENV_ASSIGN_RE.match(rest[0]):
            return None  # residual env option / NAME=value assignment -> refuse
    if not rest:
        return None

    # The launcher (what env execs / the interpreter) must carry a path separator. A
    # bare basename (`pytest`, `python`) is resolved via PATH — the redirection vector
    # the C1 hardening set out to close. A separator'd launcher (`.venv/bin/python`, an
    # absolute interpreter path) is resolved directly; recheck_commands then confines it
    # to repo_root via _path_escapes_repo.
    if "/" not in rest[0] and "\\" not in rest[0]:
        return None
    launcher = Path(rest[0]).name
    if _PYTEST_RE.match(launcher):
        return argv  # pytest console script run directly
    if _PYTHON_RE.match(launcher) and len(rest) >= 3 and rest[1] == "-m" and rest[2] == "pytest":
        return argv  # python -m pytest …
    return None


def _pytest_launcher(argv: list[str]) -> str:
    """The token that will actually be EXECUTED as the launcher (post `env -u` strip)."""
    rest = argv
    if rest and Path(rest[0]).name == "env":
        rest = rest[1:]
        i = 0
        while i < len(rest) and rest[i] == "-u" and i + 1 < len(rest):
            i += 2
        rest = rest[i:]
    return rest[0] if rest else ""


def _path_escapes_repo(token: str, repo_root, *, allow_sys_executable: bool = False) -> bool:
    """True if a path-bearing `token` resolves OUTSIDE repo_root.

    A bare command name (no separator) is resolved via the operator's TRUSTED PATH
    (the untrusted command string can no longer inject PATH), so it is not flagged.
    `allow_sys_executable` whitelists the real interpreter, which legitimately lives
    outside a per-invocation repo_root (e.g. a venv outside the reviewed worktree).
    """
    if "/" not in token and "\\" not in token:
        return False
    p = Path(token)
    try:
        resolved = (p if p.is_absolute() else Path(repo_root) / p).resolve()
        if allow_sys_executable and resolved == Path(sys.executable).resolve():
            return False
        resolved.relative_to(Path(repo_root).resolve())
        return False
    except (ValueError, OSError):
        return True


def _pytest_args(argv: list[str]) -> list[str]:
    """The pytest TARGETS/flags — argv after the `env` prefix, launcher, and `-m pytest` head.

    Scanning these (not raw argv[1:]) keeps the launcher path itself — e.g. the idiom's
    `.venv/bin/python`, a symlink resolving outside the repo — from being mis-read as an
    out-of-repo target (which would wrongly skip the re-run). The launcher is vetted
    separately by _path_escapes_repo with the sys.executable allowance.
    """
    rest = argv
    if rest and Path(rest[0]).name == "env":
        rest = rest[1:]
        i = 0
        while i < len(rest) and rest[i] == "-u" and i + 1 < len(rest):
            i += 2
        rest = rest[i:]
    if not rest:
        return []
    if _PYTHON_RE.match(Path(rest[0]).name) and len(rest) >= 3 and rest[1:3] == ["-m", "pytest"]:
        return rest[3:]  # after `python -m pytest`
    return rest[1:]  # after the `pytest` console script


def _target_escapes_repo(argv: list[str], repo_root) -> bool:
    """True if any path-like TARGET in `argv` resolves OUTSIDE repo_root.

    Confines the re-run (and thus any auto-imported conftest.py) to the repo tree at the
    reviewed commit: a crafted event pointing pytest at `/tmp/evil/` (with a malicious
    conftest) is refused. Node-ids (`tests/x.py::TestY::test_z`) are split on `::`.
    """
    root = Path(repo_root).resolve()
    for tok in _pytest_args(argv):
        if tok.startswith("-"):
            continue
        pathpart = tok.split("::", 1)[0]
        if "/" not in pathpart and not pathpart.endswith(".py"):
            continue  # not a path-like target (e.g. a bare keyword, '-q')
        try:
            p = Path(pathpart)
            resolved = (p if p.is_absolute() else root / p).resolve()
            resolved.relative_to(root)
        except (ValueError, OSError):
            return True
    return False


@dataclass
class FabricationFinding:
    """A reviewer-claimed command whose re-run contradicts the reported result."""

    command: str
    reported_summary: dict[str, int]
    actual_summary: dict[str, int]
    reported_exit: int | None
    actual_exit: int
    detail: str


def _subprocess_run(argv: list[str], cwd: str) -> tuple[int, str]:
    """Default command runner: execute argv (NO shell), return (exit_code, combined output)."""
    proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def recheck_commands(result: dict, repo_root, *, run=None) -> list[FabricationFinding]:
    """Re-run each reported pytest command and flag any contradiction (fabrication).

    A command is flagged if the re-run's normalized summary differs from the reported
    `summary`, OR the re-run's exit code differs from the reported `exit_code`. Non-pytest
    or unsafe commands are skipped (never executed). `run` is injectable for tests.
    """
    run = run or _subprocess_run
    findings: list[FabricationFinding] = []
    commands = result.get("commands")
    if not isinstance(commands, list):
        return findings  # wrong-type commands is a schema violation surfaced elsewhere
    for cmd in commands:
        if not isinstance(cmd, dict):
            continue
        command = cmd.get("command", "")
        argv = safe_pytest_argv(command)
        if argv is None:
            continue  # not a re-runnable pin (git/util command, or unsafe) — skip
        # Confine BOTH the token subprocess.run actually execs (argv[0]) and its
        # post-env launcher: a `/tmp/evil/env` prefix would otherwise leave the escape
        # check vetting the in-repo `.venv/bin/python` while env spawns the attacker.
        if _path_escapes_repo(argv[0], repo_root, allow_sys_executable=True) or \
                _path_escapes_repo(_pytest_launcher(argv), repo_root, allow_sys_executable=True):
            continue  # exec'd binary or its launcher escapes repo_root — refuse
        if _target_escapes_repo(argv, repo_root):
            continue  # target resolves outside repo_root — refuse to execute (untrusted conftest)
        reported_summary = parse_pytest_summary(cmd.get("summary", ""))
        reported_exit = cmd.get("exit_code")
        actual_exit, output = run(argv, str(repo_root))
        actual_summary = parse_pytest_summary(output)
        mismatches: list[str] = []
        if actual_summary != reported_summary:
            mismatches.append(
                f"summary reported {reported_summary} but re-run produced {actual_summary}"
            )
        if reported_exit is not None and actual_exit != reported_exit:
            mismatches.append(
                f"exit_code reported {reported_exit} but re-run exited {actual_exit}"
            )
        if mismatches:
            findings.append(
                FabricationFinding(
                    command=command,
                    reported_summary=reported_summary,
                    actual_summary=actual_summary,
                    reported_exit=reported_exit,
                    actual_exit=actual_exit,
                    detail="; ".join(mismatches),
                )
            )
    return findings


# ---------------------------------------------------------------------------
# 4. Severity mapping + inventory transition PROPOSALS (never applied)
# ---------------------------------------------------------------------------

def map_severity(reviewer_severity: str) -> str:
    """Map a reviewer `issues[].severity` to a REMEDIATION-INVENTORY.md severity (ADR-032)."""
    key = (reviewer_severity or "").strip().lower()
    if key not in SEVERITY_MAP:
        raise ValueError(
            f"unknown reviewer severity {reviewer_severity!r}; expected one of {sorted(SEVERITY_MAP)}"
        )
    return SEVERITY_MAP[key]


@dataclass
class InventoryProposal:
    """A PROPOSED (never auto-applied) REMEDIATION-INVENTORY.md status transition."""

    row_id: str
    current_status: str
    proposed_status: str
    verdict: str
    severities: list[str]
    reason: str


def _parse_inventory(text: str) -> tuple[list[str] | None, list[list[str]]]:
    """Header-aware parse of the inventory pipe table -> (lowercased header, data rows).

    A self-contained copy (the consumer stays a leaf in the dependency graph: nothing
    in scripts/ should have to import this module to use check_no_ceremony, so this
    module imports nothing back). Mirrors check_no_ceremony._inventory_data_rows.
    """
    header: list[str] | None = None
    rows: list[list[str]] = []
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 2 or set("".join(cells)) <= set("-: "):  # blank / separator row
            continue
        low = [c.lower() for c in cells]
        if header is None:
            if low[0] == "id" and "status" in low:
                header = low
            continue
        rows.append(cells)
    return header, rows


def _transition_for(verdict: str, current: str, severities: list[str]) -> tuple[str, str]:
    """Compute (proposed_status, reason) for a matched row given the reviewer verdict."""
    cur_low = current.lower()
    if verdict == "pass":
        if cur_low == "verified":
            return current, "already verified; a fresh pass re-confirms (no change)"
        return "verified", "spec+code-quality pass — propose advance to verified"
    if verdict == "issues":
        sev = ", ".join(severities) if severities else "unmapped severity"
        if cur_low == "verified":
            return "open", (
                f"issues found ({sev}) but row is 'verified' — REGRESSION; propose revert to open"
            )
        return current, f"issues found ({sev}) — do NOT advance to verified; keep {current!r}"
    if verdict == "unable_to_verify":
        return current, "unable_to_verify — RE-DISPATCH in a fixed env; no status change"
    return current, f"unrecognized verdict {verdict!r} — no proposal"


def propose_inventory_transitions(result: dict, inventory_text: str) -> list[InventoryProposal]:
    """Propose status transitions for inventory rows that cite the reviewed commit.

    Proposes ONLY — never writes the file. A row is matched when the reviewed commit
    (full SHA or its 7-char short form) appears in any cell.
    """
    header, rows = _parse_inventory(inventory_text)
    if not header:
        return []
    id_idx = header.index("id")
    status_idx = header.index("status")
    verdict = result.get("verdict")
    commit = (result.get("reviewed_commit") or "").strip()
    short = commit[:7]
    severities = sorted(
        {
            map_severity(i["severity"])
            for i in (result.get("issues") or [])
            if (i.get("severity") or "").strip().lower() in SEVERITY_MAP
        }
    )
    proposals: list[InventoryProposal] = []
    if not commit:
        return proposals
    # Match the commit (full or 7-char short form) only as a whole token — a bare
    # substring would over-match a longer SHA that merely shares the prefix.
    commit_re = re.compile(rf"\b(?:{re.escape(commit)}|{re.escape(short)})\b")
    for cells in rows:
        rowtext = " ".join(cells)
        if not commit_re.search(rowtext):
            continue
        rid = cells[id_idx] if len(cells) > id_idx else "<?>"
        current = cells[status_idx] if len(cells) > status_idx else ""
        proposed, reason = _transition_for(verdict, current, severities)
        proposals.append(
            InventoryProposal(
                row_id=rid,
                current_status=current,
                proposed_status=proposed,
                verdict=verdict,
                severities=severities,
                reason=reason,
            )
        )
    return proposals


# ---------------------------------------------------------------------------
# 5. Mailbox scan + orchestration + CLI
# ---------------------------------------------------------------------------

def _mailbox_reports(repo_root) -> list[Path]:
    sent = Path(repo_root) / "coordination" / "mailbox" / "sent"
    if not sent.exists():
        return []
    return sorted(sent.glob("*verification-report*.md"))


def iter_reviewer_results(repo_root) -> list[tuple[Path, dict]]:
    """Return (path, result) for every mailbox verification-report carrying a block.

    Events with no `reviewer-result/1` block are skipped (the block is OPTIONAL at the
    mailbox level — ADR-032). A malformed block of our own schema raises ResultParseError
    annotated with the path (the caller surfaces it as a violation).
    """
    results: list[tuple[Path, dict]] = []
    for path in _mailbox_reports(repo_root):
        try:
            block = extract_result_block(path.read_text())
        except ResultParseError as exc:
            raise ResultParseError(f"{path.name}: {exc}") from exc
        if block is not None:
            results.append((path, block))
    return results


def smoke_check(repo_root) -> int:
    """ci_smoke entry: schema-validate any present mailbox blocks. NEVER re-runs pytest.

    Re-running a historical event's pins against today's HEAD would false-alarm (wrong
    tree), so the fabrication re-run lives in the on-demand CLI, not here. Zero blocks
    (today's state) -> silent 0. Returns 1 only on a malformed or schema-invalid block.
    """
    try:
        results = iter_reviewer_results(repo_root)
    except ResultParseError as exc:
        print(f"REVIEWER-RESULT: malformed block — {exc}")
        return 1
    bad = 0
    for path, result in results:
        violations = validate_schema(result)
        if violations:
            bad += 1
            print(f"REVIEWER-RESULT schema violation in {path.name}:")
            for v in violations:
                print(f"     - {v}")
    if bad:
        return 1
    if results:
        print(f"REVIEWER-RESULT: {len(results)} block(s) schema-valid (fabrication re-run is CLI-only)")
    return 0


@dataclass
class ConsumeReport:
    """The outcome of consuming one event: present? valid? honest? what to propose?"""

    block_present: bool
    verdict: str | None
    schema_violations: list[str]
    fabrications: list[FabricationFinding]
    proposals: list[InventoryProposal]

    def ok(self) -> bool:
        """A clean consume: no block (nothing to do), or a valid + non-fabricated block."""
        if not self.block_present:
            return True
        return not self.schema_violations and not self.fabrications


def consume(text: str, repo_root, *, recheck: bool = True, run=None) -> ConsumeReport:
    """Full consume: extract -> validate -> (re-run for fabrication) -> propose transitions."""
    block = extract_result_block(text)
    if block is None:
        return ConsumeReport(False, None, [], [], [])
    violations = validate_schema(block)
    fabrications = recheck_commands(block, repo_root, run=run) if recheck else []
    inv = Path(repo_root) / "docs" / "REMEDIATION-INVENTORY.md"
    proposals = propose_inventory_transitions(block, inv.read_text()) if inv.exists() else []
    return ConsumeReport(True, block.get("verdict"), violations, fabrications, proposals)


def _print_report(report: ConsumeReport, source: str) -> None:
    print(f"CONSUME reviewer-result/1 — {source}")
    if not report.block_present:
        print("  no reviewer-result block present — nothing to consume (block is OPTIONAL)")
        return
    print(f"  verdict: {report.verdict}")
    if report.schema_violations:
        print(f"  SCHEMA VIOLATIONS ({len(report.schema_violations)}):")
        for v in report.schema_violations:
            print(f"     - {v}")
    if report.fabrications:
        print(f"  FABRICATION DETECTED ({len(report.fabrications)}) — reported summary != re-run:")
        for f in report.fabrications:
            print(f"     ! {f.command}")
            print(f"       {f.detail}")
    if report.proposals:
        print(f"  PROPOSED inventory transitions ({len(report.proposals)}) — NOT applied:")
        for p in report.proposals:
            print(f"     · {p.row_id}: {p.current_status} -> {p.proposed_status}  ({p.reason})")
    if report.ok() and not report.fabrications and not report.schema_violations:
        print("  OK — block schema-valid and every re-run summary matched")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: consume_reviewer_result.py <event.md> | --stdin", file=sys.stderr)
        return 2
    if argv[0] == "--stdin":
        text, source = sys.stdin.read(), "<stdin>"
    else:
        path = Path(argv[0])
        if not path.exists():
            print(f"no such file: {path}", file=sys.stderr)
            return 2
        text, source = path.read_text(), str(path)
    try:
        report = consume(text, _REPO_ROOT, recheck=True)
    except ResultParseError as exc:
        print(f"malformed reviewer-result block: {exc}", file=sys.stderr)
        return 1
    _print_report(report, source)
    return 0 if report.ok() else 1


if __name__ == "__main__":
    raise SystemExit(main())
