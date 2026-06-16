# Protocol Harness Best Version Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the current seat protocol-audit findings into a safer, clearer, and more enforceable Codex protocol harness.

**Architecture:** Keep the core executable protocol model intact and harden the operator-facing edges around it. Add small shared registries and wrappers where drift exists, keep hooks fail-open but regression-tested, and require fresh operator Lane V before any new harness diff is called verified.

**Tech Stack:** Bash, Python stdlib (`argparse`, `dataclasses`, `json`, `pathlib`, `subprocess`), pytest, existing mailbox/capacity/protocol scripts, existing four-seat skills and docs.

---

## Non-Negotiable Behavior

Every task in this plan must actively eliminate ceremony and theater behavior.
The implementation is acceptable only when protocol claims are backed by
executable checks, mailbox bodies, committed artifacts, or explicit operator
verdicts. Do not add status prose, receipt churn, ceremonial handoffs, or
green-looking summaries that do not change enforcement or preserve real
transfer state.

## Audit Inputs Read

- `coordination/mailbox/sent/2026-06-16T18-25-31Z-operator-to-all-findings.md`
- `coordination/mailbox/sent/2026-06-16T18-26-02Z-operator2-to-all-status.md`
- `coordination/mailbox/sent/2026-06-16T18-30-01Z-director-to-all-findings.md`
- `coordination/mailbox/sent/2026-06-16T18-18-49Z-operator-to-all-verification-report.md`
- Newest coordinator handoff: `docs/HANDOFF-coordinator-2026-06-17-wave3-met-standby.md`

Search evidence:

```bash
env -u GIT_INDEX_FILE .venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py coordinator --wave 3
env -u GIT_INDEX_FILE .venv/bin/python scripts/mailbox_monitor.py --once
rg -n -i "protocol audit|harness audit|audit recommendations|guardrail audit|protocol/harness/guardrail audit" coordination/mailbox/sent/2026-06-16T*-director2-* coordination/mailbox/sent/2026-06-16T*-operator2-* coordination/mailbox/sent/2026-06-16T*-director-* coordination/mailbox/sent/2026-06-16T*-operator-*
```

Current synthesis:

- Operator, operator2, and director all agree the core model is working: `scripts/codex_protocol_model.py`, readiness, status, smoke, route validation, and capacity tests are meaningful.
- All three current audit mails identify edge hardening, not a total protocol failure.
- No current director2-authored protocol-audit mail matched the audit terms above.
- The operator GO at `2026-06-16T18-18-49Z-operator-to-all-verification-report.md` is limited to `010b24d5`; it does not verify later hard-gate commit `33f2de0f`.
- Current branch snapshot during this plan: `f115c36f coord(cursor): director consume sent audit findings`; working tree was clean before this plan file was added; Wave 3 gate was `MET`; `scripts/ci_smoke.py` was `OK` with the known `verify-addendum` advisory and R2 warnings.

## File Structure

- Modify `.codex/hooks/guard-git-index.sh`: replace regex splitting of shell control operators with top-level tokenization that respects quotes.
- Create `tests/unit/test_codex_guard_git_index.py`: direct subprocess coverage for the Codex hook.
- Modify `coordination/bin/consume-events`: add real `-h/--help`, reject unknown args, and keep cursor files unchanged on parser errors.
- Modify `coordination/bin/send-event`: add help handling, use the shared kind registry, and clean up created mailbox files if staging fails.
- Modify `tests/unit/test_coordination_bin.py`: cover mailbox CLI parser and staging-failure behavior.
- Create `coordination/mailbox/kinds.txt`: one canonical mailbox kind per line.
- Create `scripts/protocol_mailbox.py`: shared mailbox vocabulary loader for Python scripts.
- Modify `scripts/check_coordination.py`: import `KNOWN_KINDS` from the shared loader.
- Modify `scripts/protocol_effectiveness_report.py`: import coordination kinds from the same source.
- Modify `scripts/protocol_capacity.py`: add packet state, optional structured `handoff_artifact`, and expose no-packet state in JSON.
- Modify `scripts/protocol_capacity_board.py`: add `--require-packets` and clearer empty-board rendering.
- Modify `tests/unit/test_protocol_capacity_board.py`: cover inactive empty waves, `--require-packets`, and structured handoff artifacts.
- Create `scripts/protocol_doctor.py`: read-only strict protocol validation wrapper.
- Create `tests/unit/test_protocol_doctor.py`: monkeypatch command runner and assert strict command ordering and failure propagation.
- Optional best-version task: modify `coordination/bin/claim-lock`, `coordination/bin/release-lock`, and `tests/unit/test_lock_protocol.py` to require an explicit protocol authorization environment variable before push-capable lock side effects.

## Implementation Order

The first six tasks are the audit-backed core. Task 7 is my added best-version recommendation because lock helpers currently perform push-capable side effects from a single invocation; it should be implemented after the audited must-fixes unless the user explicitly prioritizes it.

### Task 1: Parse-Safe Codex Git-Index Hook

**Files:**
- Modify: `.codex/hooks/guard-git-index.sh`
- Create: `tests/unit/test_codex_guard_git_index.py`

- [ ] **Step 1: Write failing hook tests**

Create `tests/unit/test_codex_guard_git_index.py`:

```python
"""Regression tests for .codex/hooks/guard-git-index.sh."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / ".codex" / "hooks" / "guard-git-index.sh"


def _run_hook(command: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["GIT_INDEX_FILE"] = "/tmp/codex-seat-index-test"
    payload = json.dumps({"tool_input": {"command": command}})
    return subprocess.run(
        [str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
    )


def test_quoted_pipe_regex_does_not_look_like_shell_pipe() -> None:
    result = _run_hook("rg -n 'git|pytest|GIT_INDEX_FILE' .codex/hooks tests/unit")
    assert result.returncode == 0, result.stderr


def test_bare_pytest_is_blocked_under_seat_index() -> None:
    result = _run_hook(".venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py -q")
    assert result.returncode == 2
    assert "env -u GIT_INDEX_FILE" in result.stderr


def test_bare_git_add_is_blocked_under_seat_index() -> None:
    result = _run_hook("git add scripts/protocol_capacity.py")
    assert result.returncode == 2
    assert "git add" in result.stderr


def test_env_u_git_index_prefix_is_allowed() -> None:
    result = _run_hook("env -u GIT_INDEX_FILE git add scripts/protocol_capacity.py")
    assert result.returncode == 0, result.stderr
```

- [ ] **Step 2: Run RED test**

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_guard_git_index.py -q
```

Expected: `test_quoted_pipe_regex_does_not_look_like_shell_pipe` fails because the hook splits on `|` before quote-aware parsing.

- [ ] **Step 3: Replace regex segment splitting**

In `.codex/hooks/guard-git-index.sh`, replace the `for part in re.split(...)` loop with token splitting that respects quotes:

```python
def command_segments(c):
    try:
        lex = shlex.shlex(c, posix=True, punctuation_chars=";&|")
        lex.whitespace_split = True
        toks = list(lex)
    except Exception:
        return []

    segments = []
    current = []
    for tok in toks:
        if tok in {";", "|", "||", "&&"}:
            if current:
                segments.append(current)
                current = []
            continue
        current.append(tok)
    if current:
        segments.append(current)
    return segments


def offending_segment(c):
    for toks in command_segments(c):
        if not toks:
            continue
        ci = 0
        while ci < len(toks) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[ci]):
            ci += 1
        if ci >= len(toks):
            continue
        cmd0 = toks[ci].split("/")[-1]
        segment_for_message = " ".join(toks)
        if cmd0 == "pytest":
            return segment_for_message
        if cmd0.startswith("python") and any(
            toks[k] == "-m" and k + 1 < len(toks) and toks[k + 1] == "pytest"
            for k in range(ci + 1, len(toks))
        ):
            return segment_for_message
        if cmd0 == "git":
            j = ci + 1
            while j < len(toks) and toks[j].startswith("-"):
                if toks[j] in ("-C", "-c") and j + 1 < len(toks):
                    j += 2
                else:
                    j += 1
            if j < len(toks) and toks[j] in MUT:
                return segment_for_message
    return None
```

- [ ] **Step 4: Run GREEN test**

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_guard_git_index.py -q
```

Expected: all hook tests pass.

- [ ] **Step 5: Commit task**

```bash
env -u GIT_INDEX_FILE git add .codex/hooks/guard-git-index.sh tests/unit/test_codex_guard_git_index.py
env -u GIT_INDEX_FILE git commit -m "fix(codex): make git-index guard quote-aware"
```

### Task 2: Mailbox CLI Help, Arg Rejection, And Atomic Send

**Files:**
- Modify: `coordination/bin/consume-events`
- Modify: `coordination/bin/send-event`
- Modify: `tests/unit/test_coordination_bin.py`

- [ ] **Step 1: Write failing CLI tests**

Add these tests to `tests/unit/test_coordination_bin.py`:

```python
def test_consume_events_help_does_not_mutate_cursor(repo):
    before = (repo / "coordination" / "mailbox" / "seen" / "director.txt").read_text()
    r = _run(CONSUME_EVENTS, ["director", "--help"], repo)
    assert r.returncode == 0
    assert "usage: consume-events" in r.stdout
    assert (repo / "coordination" / "mailbox" / "seen" / "director.txt").read_text() == before
    assert _staged(repo) == []


def test_consume_events_rejects_unknown_arg_without_mutation(repo):
    _seed_events(repo)
    before = (repo / "coordination" / "mailbox" / "seen" / "director.txt").read_text()
    r = _run(CONSUME_EVENTS, ["director", "--wat"], repo)
    assert r.returncode == 2
    assert "unknown argument" in r.stderr
    assert (repo / "coordination" / "mailbox" / "seen" / "director.txt").read_text() == before
    assert _staged(repo) == []


def test_send_event_help_is_read_only(repo):
    r = _run(SEND_EVENT, ["--help"], repo)
    assert r.returncode == 0
    assert "usage: send-event" in r.stdout
    assert not list((repo / "coordination" / "mailbox" / "sent").iterdir())
    assert _staged(repo) == []


def test_send_event_removes_mail_file_when_git_add_fails(repo):
    lock = repo / ".git" / "index.lock"
    lock.write_text("locked\n")
    try:
        r = _run(SEND_EVENT, ["operator", "director", "coordination", "subject"], repo, stdin="body\n")
    finally:
        lock.unlink(missing_ok=True)
    assert r.returncode != 0
    assert not list((repo / "coordination" / "mailbox" / "sent").iterdir())
    assert _staged(repo) == []
```

- [ ] **Step 2: Run RED tests**

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_coordination_bin.py -q
```

Expected: help and unknown-arg tests fail on current scripts; staging-failure cleanup fails because `send-event` writes before `git add`.

- [ ] **Step 3: Harden `consume-events` parsing**

Update `coordination/bin/consume-events` so help exits before role mutation logic and all remaining args are parsed explicitly:

```bash
usage() {
  echo "usage: consume-events <director|director2|operator|operator2> [--to <timestamp>]"
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

ROLE=${1:-}
case "$ROLE" in director|director2|operator|operator2) ;; *)
  usage >&2
  exit 2
;; esac
shift

TARGET=""
while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --to)
      shift
      [ $# -gt 0 ] || { echo "consume-events: --to needs a timestamp" >&2; exit 2; }
      TARGET=$1
      shift
      ;;
    *)
      echo "consume-events: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done
```

Keep the existing timestamp validation after this block.

- [ ] **Step 4: Harden `send-event` cleanup**

Update `coordination/bin/send-event`:

```bash
usage() { echo "usage: send-event <from> <to> <kind> <subject...>  (body on stdin)"; }

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi
[ $# -ge 4 ] || { usage >&2; exit 2; }
```

Then replace direct write to `$F` plus direct `git add` with temp publish and cleanup:

```bash
TMP=$(mktemp "$ROOT/coordination/mailbox/sent/.${TS_DASH}-${FROM}-to-${TO}-${KIND}.XXXXXX.tmp")
cleanup_tmp() { rm -f "$TMP"; }
trap cleanup_tmp EXIT

{
  printf '# %s -> %s: %s\n\n' "$FROM_TITLE" "$TO_TITLE" "$SUBJECT"
  printf '**When:** %s - **From:** %s (online)\n\n' "$TS_COLON" "$FROM"
  if [ -n "$BODY" ]; then printf '%s\n\n' "$BODY"; fi
  printf 'Cursor at send: %s\n' "$CURSOR"
} > "$TMP"

mv "$TMP" "$F"
if ! git -C "$ROOT" add -- "$REL"; then
  rm -f "$F"
  echo "send-event: git add failed; removed $REL" >&2
  exit 1
fi
```

Note: preserve the current arrow glyph if the project chooses to keep it; the ASCII snippet above is acceptable for new edits only if tests are updated accordingly.

- [ ] **Step 5: Run GREEN tests**

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_coordination_bin.py -q
```

- [ ] **Step 6: Commit task**

```bash
env -u GIT_INDEX_FILE git add coordination/bin/consume-events coordination/bin/send-event tests/unit/test_coordination_bin.py
env -u GIT_INDEX_FILE git commit -m "fix(protocol): harden mailbox cli parsing"
```

### Task 3: Shared Mailbox Kind Registry

**Files:**
- Create: `coordination/mailbox/kinds.txt`
- Create: `scripts/protocol_mailbox.py`
- Modify: `coordination/bin/send-event`
- Modify: `scripts/check_coordination.py`
- Modify: `scripts/protocol_effectiveness_report.py`
- Modify: `tests/unit/test_check_coordination.py`
- Modify: `tests/unit/test_coordination_bin.py`

- [ ] **Step 1: Add registry file**

Create `coordination/mailbox/kinds.txt` with exactly one kind per line:

```text
acknowledgement
convergence
coordination
decision
dispatch-claim
discussion
doc-sync-notice
findings
fold-notice
fyi
measurement-report
memory-candidate
proposal
proposal-reply
query
reply
scout-report
scout-request
status
verification-report
verify-addendum
verify-readiness
verify-readiness-converged
verify-request
wrap
```

- [ ] **Step 2: Add Python loader**

Create `scripts/protocol_mailbox.py`:

```python
#!/usr/bin/env python3
"""Shared mailbox protocol vocabulary."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
KIND_FILE = ROOT / "coordination" / "mailbox" / "kinds.txt"
SEATS = ("director", "director2", "operator", "operator2")
SENDERS = (*SEATS, "coordinator")
RECIPIENTS = (*SEATS, "all")


def load_known_kinds(root: Path | None = None) -> frozenset[str]:
    base = root if root is not None else ROOT
    path = base / "coordination" / "mailbox" / "kinds.txt"
    kinds = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            kinds.append(stripped)
    return frozenset(kinds)


KNOWN_KINDS = load_known_kinds()
COORDINATION_KINDS = KNOWN_KINDS - {"verification-report"}
```

- [ ] **Step 3: Write failing registry tests**

Add to `tests/unit/test_check_coordination.py`:

```python
def test_verify_addendum_is_registered_kind(tmp_path):
    name = "2026-06-15T19-43-14Z-director2-to-operator2-verify-addendum.md"
    root = make_coord(tmp_path, events={name: "**When:** 2026-06-15T19:43:14Z\n"})
    issues = run(root, since="2026-06-11T00:00:00Z", now=NOW)
    assert not any(i.kind == "unknown_kind" for i in issues)
    assert "verify-addendum" in KNOWN_KINDS
```

Add to `tests/unit/test_coordination_bin.py`:

```python
def test_send_event_accepts_shared_registered_kind(repo):
    r = _run(SEND_EVENT, ["operator", "director", "verify-addendum", "subject"], repo)
    assert r.returncode == 0, r.stderr
```

- [ ] **Step 4: Wire Python scripts to the loader**

In `scripts/check_coordination.py`, replace the local `KNOWN_KINDS = frozenset({...})` block with:

```python
from protocol_mailbox import KNOWN_KINDS, SEATS

ROLES = SEATS
```

In `scripts/protocol_effectiveness_report.py`, replace local `SEATS` and `COORDINATION_KINDS` definitions with:

```python
from protocol_mailbox import COORDINATION_KINDS, SEATS
```

- [ ] **Step 5: Wire Bash send-event to the registry**

In `coordination/bin/send-event`, replace the inline `KINDS="..."` block with:

```bash
KIND_FILE="$ROOT/coordination/mailbox/kinds.txt"
if ! grep -Fxq -- "$KIND" "$KIND_FILE"; then
  echo "send-event: unknown kind '$KIND' (see $KIND_FILE)" >&2
  exit 2
fi
```

- [ ] **Step 6: Run registry tests**

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_check_coordination.py tests/unit/test_coordination_bin.py -q
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
```

Expected: tests pass, and the historical `verify-addendum` advisory disappears from smoke output.

- [ ] **Step 7: Commit task**

```bash
env -u GIT_INDEX_FILE git add coordination/mailbox/kinds.txt scripts/protocol_mailbox.py coordination/bin/send-event scripts/check_coordination.py scripts/protocol_effectiveness_report.py tests/unit/test_check_coordination.py tests/unit/test_coordination_bin.py
env -u GIT_INDEX_FILE git commit -m "fix(protocol): centralize mailbox kind vocabulary"
```

### Task 4: Honest Empty Capacity Board And `--require-packets`

**Files:**
- Modify: `scripts/protocol_capacity.py`
- Modify: `scripts/protocol_capacity_board.py`
- Modify: `tests/unit/test_protocol_capacity_board.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/test_protocol_capacity_board.py`:

```python
def test_empty_wave_renders_inactive_no_packets(tmp_path: Path) -> None:
    report = capacity.collect_capacity_report(tmp_path, 4)
    assert report.packet_state == "inactive-no-packets"
    rendered = capacity.render_capacity_board(report)
    assert "packet state: inactive-no-packets" in rendered
    assert "valid: true" in rendered


def test_require_packets_fails_empty_wave(tmp_path: Path, capsys) -> None:
    rc = board.main(["--root", str(tmp_path), "--wave", "4", "--require-packets"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "inactive-no-packets" in out
    assert "G9: no capacity packets for wave 4" in out


def test_require_packets_passes_when_packets_exist(tmp_path: Path, capsys) -> None:
    _write_valid_cycle(tmp_path)
    rc = board.main(["--root", str(tmp_path), "--wave", "4", "--require-packets"])
    assert rc == 0
```

- [ ] **Step 2: Run RED tests**

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py -q
```

- [ ] **Step 3: Add packet state**

In `scripts/protocol_capacity.py`, add to `CapacityReport`:

```python
    @property
    def packet_state(self) -> str:
        return "active" if self.packets else "inactive-no-packets"
```

Add `"packet_state": self.packet_state` to `to_dict()`.

In `render_capacity_board`, insert after `valid:`:

```python
        f"packet state: {report.packet_state}",
```

- [ ] **Step 4: Add require-packets gate**

In `scripts/protocol_capacity_board.py`:

```python
    parser.add_argument(
        "--require-packets",
        action="store_true",
        help="exit nonzero when a wave has no capacity packets",
    )
```

After collecting the report:

```python
    if args.require_packets and not report.packets:
        issue = protocol_capacity._issue("G9", f"no capacity packets for wave {args.wave}")
        report = protocol_capacity.CapacityReport(
            root=report.root,
            wave=report.wave,
            packets=report.packets,
            exceptions=report.exceptions,
            issues=(*report.issues, issue),
        )
```

If exposing `_issue` is undesirable, add a public helper `require_packets(report)` in `scripts/protocol_capacity.py` and call that instead.

- [ ] **Step 5: Run GREEN tests**

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py -q
```

- [ ] **Step 6: Commit task**

```bash
env -u GIT_INDEX_FILE git add scripts/protocol_capacity.py scripts/protocol_capacity_board.py tests/unit/test_protocol_capacity_board.py
env -u GIT_INDEX_FILE git commit -m "fix(protocol): label inactive capacity boards"
```

### Task 5: Structured Handoff Artifact Field

**Files:**
- Modify: `scripts/protocol_capacity.py`
- Modify: `tests/unit/test_protocol_capacity_board.py`

- [ ] **Step 1: Write failing structured-artifact tests**

Modify `_packet` in `tests/unit/test_protocol_capacity_board.py` to accept `handoff_artifact: str | None = None` and include it when not `None`.

Add:

```python
def test_closed_standby_cycle_accepts_structured_handoff_artifact(tmp_path: Path) -> None:
    for packet in [
        _packet(
            "wave4-join",
            "coordinator",
            packet_type="coordinator-join",
            status="done",
            done_evidence=[
                "capacity board valid",
                "smoke OK",
                "next trigger: standby; no routed next work",
            ],
            handoff_artifact="docs/HANDOFF-coordinator-2026-06-17-wave4-standby.md",
        ),
        _packet(
            "wave4-director-done",
            "director",
            status="done",
            done_evidence=[
                "committed diff",
                "verify-request coordination/mailbox/sent/request.md",
            ],
        ),
        _packet(
            "wave4-operator-done",
            "operator",
            packet_type="operator-verification",
            status="done",
            done_evidence=["GO coordination/mailbox/sent/go.md"],
        )
        | {
            "verify_request": "coordination/mailbox/sent/request.md",
            "target_commit": "abc1234",
            "scope_files": ["identity/validator.py"],
        },
    ]:
        _write_packet(tmp_path, packet)

    report = capacity.collect_capacity_report(tmp_path, 4)

    assert report.blocking_issues == []


def test_closed_standby_cycle_rejects_bad_structured_handoff_artifact(tmp_path: Path) -> None:
    _write_packet(
        tmp_path,
        _packet(
            "wave4-join",
            "coordinator",
            packet_type="coordinator-join",
            status="done",
            done_evidence=[
                "capacity board valid",
                "smoke OK",
                "next trigger: standby; no routed next work",
            ],
            handoff_artifact="notes/chat-only.md",
        ),
    )

    report = capacity.collect_capacity_report(tmp_path, 4)

    messages = "\n".join(issue["message"] for issue in report.blocking_issues)
    assert "handoff_artifact must cite docs/HANDOFF-*.md" in messages
```

- [ ] **Step 2: Run RED tests**

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py -q
```

- [ ] **Step 3: Add field to `Packet`**

In `scripts/protocol_capacity.py`, add:

```python
    handoff_artifact: str | None
```

to `Packet`, `Packet.to_dict()`, and `_parse_packet`.

In `_parse_packet`, parse it as:

```python
    handoff_artifact = data.get("handoff_artifact")
    if handoff_artifact is not None and not isinstance(handoff_artifact, str):
        local_issues.append("handoff_artifact must be a string")
        handoff_artifact = None
```

- [ ] **Step 4: Use structured artifact in join validation**

In `_validate_join_gate`, before checking `HANDOFF_ARTIFACT_RE`, add:

```python
            structured_handoff = join.handoff_artifact or ""
            if structured_handoff and not HANDOFF_ARTIFACT_RE.search(structured_handoff):
                missing.append("handoff_artifact must cite docs/HANDOFF-*.md")
            if (
                HANDOFF_REQUIRED_RE.search(evidence)
                and not structured_handoff
                and not HANDOFF_ARTIFACT_RE.search(evidence)
            ):
                missing.append("handoff artifact")
```

Remove the old two-condition block to avoid duplicate messages.

- [ ] **Step 5: Run GREEN tests**

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py -q
```

- [ ] **Step 6: Commit task**

```bash
env -u GIT_INDEX_FILE git add scripts/protocol_capacity.py tests/unit/test_protocol_capacity_board.py
env -u GIT_INDEX_FILE git commit -m "fix(protocol): structure handoff artifact evidence"
```

### Task 6: Strict Protocol Doctor

**Files:**
- Create: `scripts/protocol_doctor.py`
- Create: `tests/unit/test_protocol_doctor.py`
- Modify: `docs/protocol/codex/continuation.md`
- Modify: `.agents/skills/four-seat-protocol/SKILL.md`
- Modify: `.agents/skills/seat-coordinator/SKILL.md`

- [ ] **Step 1: Write doctor tests**

Create `tests/unit/test_protocol_doctor.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import protocol_doctor  # noqa: E402


def test_doctor_runs_read_only_protocol_bundle(monkeypatch, tmp_path, capsys):
    calls = []

    def fake_run(cmd, cwd, timeout=120):
        calls.append(cmd)
        return protocol_doctor.CommandResult(cmd=cmd, returncode=0, stdout="OK", stderr="")

    monkeypatch.setattr(protocol_doctor, "run_command", fake_run)

    rc = protocol_doctor.main(["--root", str(tmp_path), "--wave", "4"])

    assert rc == 0
    assert ["python", "scripts/check_coordination.py"] in calls
    assert ["python", "scripts/protocol_capacity_board.py", "--wave", "4"] in calls
    assert ["python", "-m", "pytest", "tests/unit/test_codex_protocol_model.py", "tests/unit/test_codex_protocol_artifacts.py", "tests/unit/test_protocol_capacity_board.py", "tests/unit/test_coordination_bin.py", "tests/unit/test_check_coordination.py", "-q"] in calls
    assert ["python", "scripts/ci_smoke.py"] in calls
    assert "PROTOCOL DOCTOR: PASS" in capsys.readouterr().out


def test_doctor_validates_route_when_passed(monkeypatch, tmp_path):
    route = tmp_path / "coordination/mailbox/sent/route.md"
    route.parent.mkdir(parents=True)
    route.write_text("task-board\n", encoding="utf-8")
    calls = []

    def fake_run(cmd, cwd, timeout=120):
        calls.append(cmd)
        return protocol_doctor.CommandResult(cmd=cmd, returncode=0, stdout="OK", stderr="")

    monkeypatch.setattr(protocol_doctor, "run_command", fake_run)

    rc = protocol_doctor.main(["--root", str(tmp_path), "--wave", "4", "--route", str(route)])

    assert rc == 0
    assert ["python", "scripts/protocol_capacity_board.py", "--wave", "4", "--require-packets"] in calls
    assert ["python", "scripts/protocol_capacity_board.py", "--wave", "4", "--validate-route", str(route)] in calls


def test_doctor_fails_on_first_failed_command(monkeypatch, tmp_path):
    def fake_run(cmd, cwd, timeout=120):
        return protocol_doctor.CommandResult(cmd=cmd, returncode=1, stdout="", stderr="bad")

    monkeypatch.setattr(protocol_doctor, "run_command", fake_run)

    rc = protocol_doctor.main(["--root", str(tmp_path), "--wave", "4"])

    assert rc == 1
```

- [ ] **Step 2: Run RED test**

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_doctor.py -q
```

- [ ] **Step 3: Implement doctor**

Create `scripts/protocol_doctor.py`:

```python
#!/usr/bin/env python3
"""Strict read-only protocol validation bundle."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class CommandResult:
    cmd: list[str]
    returncode: int
    stdout: str
    stderr: str


def run_command(cmd: list[str], cwd: Path, timeout: int = 120) -> CommandResult:
    env = dict(os.environ)
    env.pop("GIT_INDEX_FILE", None)
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    return CommandResult(cmd=cmd, returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


def _python() -> str:
    return "python"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run strict read-only protocol checks.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--wave", type=int, required=True)
    parser.add_argument("--route", default=None)
    args = parser.parse_args(argv)

    root = Path(args.root)
    py = _python()
    commands = [
        [py, "scripts/check_coordination.py"],
        [py, "scripts/protocol_capacity_board.py", "--wave", str(args.wave)],
    ]
    if args.route:
        commands.append([py, "scripts/protocol_capacity_board.py", "--wave", str(args.wave), "--require-packets"])
        commands.append([py, "scripts/protocol_capacity_board.py", "--wave", str(args.wave), "--validate-route", args.route])
    commands.extend(
        [
            [
                py,
                "-m",
                "pytest",
                "tests/unit/test_codex_protocol_model.py",
                "tests/unit/test_codex_protocol_artifacts.py",
                "tests/unit/test_protocol_capacity_board.py",
                "tests/unit/test_coordination_bin.py",
                "tests/unit/test_check_coordination.py",
                "-q",
            ],
            [py, "scripts/ci_smoke.py"],
        ]
    )

    for cmd in commands:
        result = run_command(cmd, root)
        print("$ " + " ".join(cmd))
        if result.stdout:
            print(result.stdout.rstrip())
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)
        if result.returncode != 0:
            print("PROTOCOL DOCTOR: FAIL")
            return result.returncode
    print("PROTOCOL DOCTOR: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

If tests run from an environment where `python` is not the project interpreter, change `_python()` to return `sys.executable` and update the tests to compare `sys.executable`.

- [ ] **Step 4: Document doctor in Codex protocol surfaces**

Add the doctor command as the recommended strict validation bundle in:

- `docs/protocol/codex/continuation.md`
- `.agents/skills/four-seat-protocol/SKILL.md`
- `.agents/skills/seat-coordinator/SKILL.md`

Use:

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_doctor.py --wave <wave>
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_doctor.py --wave <wave> --route coordination/mailbox/sent/<event>.md
```

- [ ] **Step 5: Run GREEN tests and doctor**

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_doctor.py tests/unit/test_protocol_capacity_board.py tests/unit/test_coordination_bin.py tests/unit/test_check_coordination.py -q
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_doctor.py --wave 3
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
```

- [ ] **Step 6: Commit task**

```bash
env -u GIT_INDEX_FILE git add scripts/protocol_doctor.py tests/unit/test_protocol_doctor.py docs/protocol/codex/continuation.md .agents/skills/four-seat-protocol/SKILL.md .agents/skills/seat-coordinator/SKILL.md
env -u GIT_INDEX_FILE git commit -m "feat(protocol): add strict doctor validation"
```

### Task 7: Explicit Authorization Gate For Push-Capable Lock Helpers

**Files:**
- Modify: `coordination/bin/claim-lock`
- Modify: `coordination/bin/release-lock`
- Modify: `tests/unit/test_lock_protocol.py`

- [ ] **Step 1: Write failing authorization tests**

Add to `tests/unit/test_lock_protocol.py`:

```python
def test_claim_lock_requires_explicit_protocol_authorization(two_clones):
    seatA, _ = two_clones
    r = _run([str(BIN / "claim-lock"), "W1", "core.py", "operator", "bug-1"], seatA)
    assert r.returncode == 2
    assert "PROTOCOL_LOCK_AUTH=1" in r.stderr
    assert not (seatA / "coordination" / "locks" / "W1-core.py.lock").exists()


def test_release_lock_requires_explicit_protocol_authorization(two_clones):
    seatA, _ = two_clones
    env = {k: v for k, v in os.environ.items() if k != "GIT_INDEX_FILE"}
    env["PROTOCOL_LOCK_AUTH"] = "1"
    assert subprocess.run(
        [str(BIN / "claim-lock"), "W1", "core.py", "operator", "bug-1"],
        cwd=seatA,
        capture_output=True,
        text=True,
        env=env,
    ).returncode == 0

    r = _run([str(BIN / "release-lock"), "W1", "core.py"], seatA)
    assert r.returncode == 2
    assert "PROTOCOL_LOCK_AUTH=1" in r.stderr
    assert (seatA / "coordination" / "locks" / "W1-core.py.lock").exists()
```

Then update existing successful lock tests so they call the scripts with `PROTOCOL_LOCK_AUTH=1`.

- [ ] **Step 2: Run RED tests**

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_lock_protocol.py -q
```

- [ ] **Step 3: Add the gate**

At the top of both lock scripts, after `set -euo pipefail`:

```bash
if [ "${PROTOCOL_LOCK_AUTH:-}" != "1" ]; then
  echo "lock side effects require explicit PROTOCOL_LOCK_AUTH=1 from an authorized seat/user route" >&2
  exit 2
fi
```

- [ ] **Step 4: Run GREEN tests**

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_lock_protocol.py -q
```

- [ ] **Step 5: Commit task**

```bash
env -u GIT_INDEX_FILE git add coordination/bin/claim-lock coordination/bin/release-lock tests/unit/test_lock_protocol.py
env -u GIT_INDEX_FILE git commit -m "fix(protocol): require explicit lock authorization"
```

### Task 8: Fresh Lane V And Coordinator Route

**Files:**
- No production files.
- Possible mailbox route: `coordination/mailbox/sent/<timestamp>-coordinator-to-all-coordination.md`

- [ ] **Step 1: Run final strict verification**

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_guard_git_index.py tests/unit/test_coordination_bin.py tests/unit/test_check_coordination.py tests/unit/test_protocol_capacity_board.py tests/unit/test_protocol_doctor.py tests/unit/test_lock_protocol.py tests/unit/test_codex_protocol_artifacts.py tests/unit/test_codex_protocol_model.py -q
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_doctor.py --wave 3
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
env -u GIT_INDEX_FILE git diff --check
env -u GIT_INDEX_FILE git status --short
```

- [ ] **Step 2: Inspect commit scope**

```bash
env -u GIT_INDEX_FILE git log --oneline --decorate -12
env -u GIT_INDEX_FILE git show --stat --oneline --decorate HEAD
```

- [ ] **Step 3: Route fresh operator verification**

If the implementation was done by a coordinator session, stop before claiming GO and route the landed harness diff to an operator seat. The verify request must cite exact commit range and files, and must say it includes the already-landed hard-gate commit `33f2de0f` unless that commit has separately received Lane V by then.

Route shape:

```text
Task-board:
- packet: protocol-harness-best-version-lanev
- owner: operator
- target commit/range: <base>..<head>
- scope files: .codex/hooks/guard-git-index.sh, coordination/bin/consume-events, coordination/bin/send-event, coordination/mailbox/kinds.txt, scripts/protocol_mailbox.py, scripts/check_coordination.py, scripts/protocol_effectiveness_report.py, scripts/protocol_capacity.py, scripts/protocol_capacity_board.py, scripts/protocol_doctor.py, tests/unit/test_codex_guard_git_index.py, tests/unit/test_coordination_bin.py, tests/unit/test_check_coordination.py, tests/unit/test_protocol_capacity_board.py, tests/unit/test_protocol_doctor.py, tests/unit/test_lock_protocol.py
- acceptance: operator issues verification-report GO/NITS/FAIL from clean exact commit or clean archive
- join condition: coordinator records operator verdict and does not call the harness verified until GO lands
- side effects: no push, no lock claim/release, no paid API spend, no pod spend
```

Before committing that coordinator route, run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave <wave> --require-packets
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave <wave> --validate-route coordination/mailbox/sent/<event>.md
```

## Verification Bundle

Run this bundle before final handoff or route:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_guard_git_index.py tests/unit/test_coordination_bin.py tests/unit/test_check_coordination.py tests/unit/test_protocol_capacity_board.py tests/unit/test_protocol_doctor.py tests/unit/test_lock_protocol.py tests/unit/test_codex_protocol_artifacts.py tests/unit/test_codex_protocol_model.py -q
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_doctor.py --wave 3
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
env -u GIT_INDEX_FILE git diff --check
env -u GIT_INDEX_FILE git status --short
```

## Coordinator Recommendation

Implement Tasks 1-6 first as one protocol-hardening slice, with one commit per task. Then route fresh operator Lane V over the exact landed range. Treat Task 7 as a best-version follow-up unless the user explicitly wants lock helper authorization in the same wave, because it changes push-capable workflow behavior and should be verified separately.

During implementation, continuously monitor whether the handoff mechanism is
creating real transfer state. If a better low-risk handoff check is discovered,
apply it in the same task only when it strengthens enforcement or removes
theater without expanding production scope; otherwise capture it as a new
packet-backed follow-up instead of creating chat-only doctrine.
