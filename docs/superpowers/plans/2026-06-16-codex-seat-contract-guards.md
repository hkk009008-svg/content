# Codex Seat Contract Guards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build thin, tested Codex protocol tools for seat contracts, proof bundles, guards, and done summaries without replacing existing protocol authority.

**Architecture:** Keep `scripts/codex_protocol_model.py` as the source of runtime role truth. Add small CLI tools that render or compose existing evidence, plus reusable guard functions that hooks can call. Update docs only after executable behavior and tests exist.

**Tech Stack:** Python 3, pytest, existing `coordination/bin/*` shell helpers, `.codex/hooks` wrappers, Markdown protocol docs.

---

## File Structure

- Modify: `scripts/codex_protocol_model.py` to expose the six contract field names and render a seat-contract view from the existing runtime env model.
- Create: `scripts/seat_banner.py` as a no-mutation contract/banner CLI.
- Create: `scripts/proof_bundle.py` as a read-only evidence composer.
- Modify: `scripts/mailbox_monitor.py` only if a broadcast selector is needed by `proof_bundle.py`.
- Create: `scripts/protocol_guards.py` for reusable guard checks.
- Create: `scripts/done_summary.py` as a fact-filled final evidence emitter.
- Modify: `.codex/hooks/*.sh` only as wrappers around tested guard functions.
- Modify: `docs/protocol/codex/continuation.md` and `.agents/skills/four-seat-protocol/SKILL.md` after tools exist.
- Test: add focused unit tests in `tests/unit/test_seat_banner.py`, `tests/unit/test_proof_bundle.py`, `tests/unit/test_protocol_guards.py`, and `tests/unit/test_done_summary.py`; extend existing protocol tests where the model or monitor changes.

## Task 1: Runtime Contract Model

**Files:**
- Modify: `scripts/codex_protocol_model.py`
- Modify: `tests/unit/test_codex_protocol_model.py`

- [ ] **Step 1: Write the failing model test**

Add a test that requires the six seat-contract fields to render from the existing runtime env:

```python
def test_render_seat_contract_includes_six_fields_and_source_order() -> None:
    text = model.render_seat_contract(
        {
            "CODEX_SEAT": "director2",
            "GIT_INDEX_FILE": "/repo/.git/index-codex-director2",
        },
        objective="draft R-BRIEF",
        permissions="edit=yes commit=yes push=no spend=no lock=no",
        scope="docs/superpowers/briefs/example.md",
        verification="pytest tests/unit/test_example.py -q",
        done="HEAD changed-files unread verification push next-trigger",
    )

    assert "S-ROLE: live-seat / director2" in text
    assert "S-OBJ: draft R-BRIEF" in text
    assert "S-PERM: edit=yes commit=yes push=no spend=no lock=no" in text
    assert "S-SCOPE: docs/superpowers/briefs/example.md" in text
    assert "S-VERIFY: pytest tests/unit/test_example.py -q" in text
    assert "S-DONE: HEAD changed-files unread verification push next-trigger" in text
    assert "source order: user > git > mailbox > handoff > defaults" in text
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py::test_render_seat_contract_includes_six_fields_and_source_order -q
```

Expected: failure because `render_seat_contract` is not defined.

- [ ] **Step 3: Implement the model renderer**

Add a constant and function near `render_runtime_env_contract`:

```python
SEAT_CONTRACT_FIELDS = (
    ("S-ROLE", "role/env"),
    ("S-OBJ", "objective"),
    ("S-PERM", "permissions"),
    ("S-SCOPE", "scope"),
    ("S-VERIFY", "verification"),
    ("S-DONE", "done"),
)


def render_seat_contract(
    environ: Mapping[str, str] | None = None,
    *,
    objective: str = "(unset)",
    permissions: str = "(unset)",
    scope: str = "(unset)",
    verification: str = "(unset)",
    done: str = "(unset)",
) -> str:
    values = infer_runtime_env(environ)
    role_value = f"{values['CODEX_AGENT_MODE']} / {values['CODEX_AGENT_ROLE']}"
    lines = [
        "Seat contract:",
        f"S-ROLE: {role_value}",
        f"S-OBJ: {objective}",
        f"S-PERM: {permissions}",
        f"S-SCOPE: {scope}",
        f"S-VERIFY: {verification}",
        f"S-DONE: {done}",
        "source order: user > git > mailbox > handoff > defaults",
        "side effects: push, lock, paid API spend, and pod spend require user consent",
    ]
    return "\n".join(lines)
```

- [ ] **Step 4: Run the focused test**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py::test_render_seat_contract_includes_six_fields_and_source_order -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

Commit only these files:

```bash
env -u GIT_INDEX_FILE git add -- scripts/codex_protocol_model.py tests/unit/test_codex_protocol_model.py
env -u GIT_INDEX_FILE git diff --cached --name-status
env -u GIT_INDEX_FILE git commit -m "coord(protocol): model seat contract fields" -- scripts/codex_protocol_model.py tests/unit/test_codex_protocol_model.py
```

## Task 2: Seat Banner CLI

**Files:**
- Create: `scripts/seat_banner.py`
- Create: `tests/unit/test_seat_banner.py`

- [ ] **Step 1: Write the failing CLI tests**

Create `tests/unit/test_seat_banner.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path


_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import seat_banner  # noqa: E402


def test_banner_prints_complete_contract(monkeypatch, capsys) -> None:
    monkeypatch.setenv("CODEX_SEAT", "operator")
    monkeypatch.setenv("GIT_INDEX_FILE", "/repo/.git/index-codex-operator")

    rc = seat_banner.main(
        [
            "--objective", "consume mail",
            "--permissions", "consume-mail=yes commit=yes push=no",
            "--scope", "coordination/mailbox/seen/operator.txt",
            "--verify", "scripts/check_coordination.py",
            "--done", "HEAD changed-files unread verification push next-trigger",
            "--require-complete",
        ]
    )

    out = capsys.readouterr().out
    assert rc == 0
    assert "S-ROLE: live-seat / operator" in out
    assert "S-OBJ: consume mail" in out


def test_require_complete_rejects_missing_fields(capsys) -> None:
    rc = seat_banner.main(["--objective", "only objective", "--require-complete"])

    err = capsys.readouterr().err
    assert rc == 2
    assert "missing contract fields" in err
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_seat_banner.py -q
```

Expected: import failure because `scripts/seat_banner.py` does not exist.

- [ ] **Step 3: Implement the CLI**

Create `scripts/seat_banner.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys

from codex_protocol_model import render_seat_contract


REQUIRED = ("objective", "permissions", "scope", "verify", "done")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render the Codex seat contract.")
    parser.add_argument("--objective", default="")
    parser.add_argument("--permissions", default="")
    parser.add_argument("--scope", default="")
    parser.add_argument("--verify", default="")
    parser.add_argument("--done", default="")
    parser.add_argument("--require-complete", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    missing = [name for name in REQUIRED if not getattr(args, name)]
    if args.require_complete and missing:
        print("missing contract fields: " + ", ".join(missing), file=sys.stderr)
        return 2
    print(
        render_seat_contract(
            os.environ,
            objective=args.objective or "(unset)",
            permissions=args.permissions or "(unset)",
            scope=args.scope or "(unset)",
            verification=args.verify or "(unset)",
            done=args.done or "(unset)",
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the focused tests**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_seat_banner.py tests/unit/test_codex_protocol_model.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
env -u GIT_INDEX_FILE git add -- scripts/seat_banner.py tests/unit/test_seat_banner.py
env -u GIT_INDEX_FILE git diff --cached --name-status
env -u GIT_INDEX_FILE git commit -m "coord(protocol): add seat contract banner" -- scripts/seat_banner.py tests/unit/test_seat_banner.py
```

## Task 3: Proof Bundle CLI

**Files:**
- Create: `scripts/proof_bundle.py`
- Create: `tests/unit/test_proof_bundle.py`

- [ ] **Step 1: Write tests for read-only composition**

Create `tests/unit/test_proof_bundle.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path


_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import proof_bundle  # noqa: E402


def test_build_commands_uses_env_u_git_index_for_git_and_gate(tmp_path: Path) -> None:
    commands = proof_bundle.build_commands(tmp_path, seat="coordinator", wave=2, smoke=True)

    rendered = [" ".join(command) for command in commands]
    assert any("seat_status.py coordinator --wave 2" in command for command in rendered)
    assert any(command.startswith("env -u GIT_INDEX_FILE git log") for command in rendered)
    assert any("scripts/wave_gate_check.py 2" in command for command in rendered)
    assert any("scripts/ci_smoke.py" in command for command in rendered)


def test_collect_mailbox_bodies_limits_to_unread_files(tmp_path: Path) -> None:
    sent = tmp_path / "coordination" / "mailbox" / "sent"
    sent.mkdir(parents=True)
    event = sent / "2026-06-16T05-04-09Z-coordinator-to-all-coordination.md"
    event.write_text("# Coordinator\n\nbody\n", encoding="utf-8")

    bodies = proof_bundle.collect_mailbox_bodies(tmp_path, [event.name], limit=1)

    assert bodies == [(event.name, "# Coordinator\n\nbody\n")]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_proof_bundle.py -q
```

Expected: import failure because `proof_bundle.py` does not exist.

- [ ] **Step 3: Implement the proof bundle skeleton**

Create `scripts/proof_bundle.py` with side-effect-free helpers first:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from mailbox_monitor import collect_monitor_state, render_snapshot


SEAT_STATUS = ".agents/skills/four-seat-protocol/scripts/seat_status.py"


def build_commands(root: Path, *, seat: str, wave: int, smoke: bool) -> list[list[str]]:
    py = str(root / ".venv" / "bin" / "python")
    commands = [
        [py, str(root / SEAT_STATUS), seat, "--wave", str(wave)],
        ["env", "-u", "GIT_INDEX_FILE", "git", "log", "--oneline", "-5"],
        ["env", "-u", "GIT_INDEX_FILE", py, str(root / "scripts/wave_gate_check.py"), str(wave)],
    ]
    if smoke:
        commands.append(["env", "-u", "GIT_INDEX_FILE", py, str(root / "scripts/ci_smoke.py")])
    return commands


def collect_mailbox_bodies(root: Path, filenames: list[str], *, limit: int) -> list[tuple[str, str]]:
    sent = root / "coordination" / "mailbox" / "sent"
    bodies = []
    for name in filenames[:limit]:
        path = sent / name
        bodies.append((name, path.read_text(encoding="utf-8")))
    return bodies


def run_command(command: list[str], root: Path) -> tuple[int, str]:
    proc = subprocess.run(command, cwd=root, text=True, capture_output=True, check=False)
    return proc.returncode, proc.stdout + proc.stderr
```

Add a simple `main()` after helper tests pass; it should print command names,
outputs, monitor snapshot, and selected mailbox bodies. It must never call
`consume-events`, `send-event`, `git add`, or `git commit`.

- [ ] **Step 4: Add main tests for monitor output**

Extend `tests/unit/test_proof_bundle.py` with monkeypatched `run_command` and
`collect_monitor_state` assertions so no subprocess is required in unit tests.

- [ ] **Step 5: Run focused tests**

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_proof_bundle.py tests/unit/test_mailbox_monitor.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```bash
env -u GIT_INDEX_FILE git add -- scripts/proof_bundle.py tests/unit/test_proof_bundle.py
env -u GIT_INDEX_FILE git diff --cached --name-status
env -u GIT_INDEX_FILE git commit -m "coord(protocol): add read-only proof bundle" -- scripts/proof_bundle.py tests/unit/test_proof_bundle.py
```

## Task 4: Protocol Guards

**Files:**
- Create: `scripts/protocol_guards.py`
- Create: `tests/unit/test_protocol_guards.py`
- Modify: `.codex/hooks/guard-git-index.sh` only if wrapper behavior needs extension

- [ ] **Step 1: Write guard negative tests**

Create `tests/unit/test_protocol_guards.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path


_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import protocol_guards as guards  # noqa: E402


def test_staged_scope_rejects_path_outside_scope() -> None:
    result = guards.check_staged_scope(
        staged_paths=["coordination/mailbox/seen/operator.txt", "web_server.py"],
        allowed_paths=["coordination/mailbox/seen/operator.txt"],
    )
    assert not result.ok
    assert "web_server.py" in result.message


def test_coordinator_scope_rejects_product_code() -> None:
    result = guards.check_coordinator_paths(["phase_c_ffmpeg.py"])
    assert not result.ok
    assert "coordinator cannot mutate production/lane code" in result.message


def test_push_guard_requires_authorization() -> None:
    assert not guards.check_push_authorized({}).ok
    assert guards.check_push_authorized({"CODEX_PERM_PUSH": "1"}).ok


def test_cursor_only_scope_accepts_exact_seen_file() -> None:
    result = guards.check_cursor_only_scope("operator2", ["coordination/mailbox/seen/operator2.txt"])
    assert result.ok
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_guards.py -q
```

Expected: import failure because `protocol_guards.py` does not exist.

- [ ] **Step 3: Implement reusable guard functions**

Create `scripts/protocol_guards.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from collections.abc import Mapping


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    message: str


PRODUCTION_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".jsx")
COORDINATOR_ALLOWED_PREFIXES = (
    "coordination/",
    "docs/",
    "logs/",
    ".agents/skills/",
    ".codex/",
    "scripts/",
    "tests/",
)


def check_staged_scope(staged_paths: list[str], allowed_paths: list[str]) -> GuardResult:
    allowed = {PurePosixPath(path).as_posix() for path in allowed_paths}
    outside = [path for path in staged_paths if PurePosixPath(path).as_posix() not in allowed]
    if outside:
        return GuardResult(False, "staged paths outside declared scope: " + ", ".join(outside))
    return GuardResult(True, "staged scope matches declared scope")


def check_cursor_only_scope(seat: str, staged_paths: list[str]) -> GuardResult:
    expected = f"coordination/mailbox/seen/{seat}.txt"
    return check_staged_scope(staged_paths, [expected])


def check_coordinator_paths(paths: list[str]) -> GuardResult:
    blocked = []
    for path in paths:
        if path.startswith(COORDINATOR_ALLOWED_PREFIXES):
            continue
        if path.endswith(PRODUCTION_SUFFIXES):
            blocked.append(path)
    if blocked:
        return GuardResult(False, "coordinator cannot mutate production/lane code: " + ", ".join(blocked))
    return GuardResult(True, "coordinator paths are protocol/tooling scope")


def check_push_authorized(environ: Mapping[str, str]) -> GuardResult:
    if environ.get("CODEX_PERM_PUSH") == "1":
        return GuardResult(True, "push authorized by CODEX_PERM_PUSH=1")
    return GuardResult(False, "push blocked: CODEX_PERM_PUSH=1 is not set")
```

Add stale-state and git-index checks after these pass. Stale-state should accept
a proof timestamp and current timestamp, then compare age in seconds. Git-index
checks should preserve the existing `.claude/hooks/guard-git-index.sh` behavior
instead of rewriting it.

- [ ] **Step 4: Add allowed-path tests**

Add tests proving coordinator docs/tooling paths are accepted and ordinary
cursor-only commits are accepted. This prevents guard hardening from blocking
normal protocol work.

- [ ] **Step 5: Run focused tests**

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_guards.py tests/unit/test_codex_protocol_artifacts.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```bash
env -u GIT_INDEX_FILE git add -- scripts/protocol_guards.py tests/unit/test_protocol_guards.py .codex/hooks/guard-git-index.sh
env -u GIT_INDEX_FILE git diff --cached --name-status
env -u GIT_INDEX_FILE git commit -m "coord(protocol): add executable protocol guards" -- scripts/protocol_guards.py tests/unit/test_protocol_guards.py .codex/hooks/guard-git-index.sh
```

## Task 5: Done Summary CLI

**Files:**
- Create: `scripts/done_summary.py`
- Create: `tests/unit/test_done_summary.py`

- [ ] **Step 1: Write tests for fact-filled summaries**

Create `tests/unit/test_done_summary.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path


_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import done_summary  # noqa: E402


def test_render_done_summary_marks_missing_fields_unknown() -> None:
    text = done_summary.render_done_summary(
        {
            "head": "abc1234",
            "changed_files": ["scripts/seat_banner.py"],
            "unread": "operator=0",
            "verification": ["pytest tests/unit/test_seat_banner.py -q: PASS"],
            "push": "not pushed",
            "next_trigger": "",
        }
    )

    assert "HEAD: abc1234" in text
    assert "Changed files: scripts/seat_banner.py" in text
    assert "Next trigger: unknown" in text


def test_render_blocked_summary_names_blocker() -> None:
    text = done_summary.render_blocked_summary(
        head="abc1234",
        blocker="missing operator GO",
        next_trigger="operator sends verification-report",
    )
    assert "Blocked: missing operator GO" in text
    assert "Next trigger: operator sends verification-report" in text
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_done_summary.py -q
```

Expected: import failure because `done_summary.py` does not exist.

- [ ] **Step 3: Implement render helpers and CLI**

Create `scripts/done_summary.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse


def _value(value: object) -> str:
    if value in ("", None, []):
        return "unknown"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def render_done_summary(facts: dict[str, object]) -> str:
    return "\n".join(
        [
            f"HEAD: {_value(facts.get('head'))}",
            f"Changed files: {_value(facts.get('changed_files'))}",
            f"Unread / mailbox delta: {_value(facts.get('unread'))}",
            f"Verification: {_value(facts.get('verification'))}",
            f"Push status: {_value(facts.get('push'))}",
            f"Next trigger: {_value(facts.get('next_trigger'))}",
        ]
    )


def render_blocked_summary(*, head: str, blocker: str, next_trigger: str) -> str:
    return "\n".join(
        [
            f"HEAD: {_value(head)}",
            f"Blocked: {_value(blocker)}",
            f"Next trigger: {_value(next_trigger)}",
        ]
    )
```

Add a CLI that accepts explicit facts first. In a later slice it may gather
facts directly from `proof_bundle.py` JSON output.

- [ ] **Step 4: Run focused tests**

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_done_summary.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
env -u GIT_INDEX_FILE git add -- scripts/done_summary.py tests/unit/test_done_summary.py
env -u GIT_INDEX_FILE git diff --cached --name-status
env -u GIT_INDEX_FILE git commit -m "coord(protocol): add done summary emitter" -- scripts/done_summary.py tests/unit/test_done_summary.py
```

## Task 6: Documentation And Skill Wiring

**Files:**
- Modify: `docs/protocol/codex/continuation.md`
- Modify: `.agents/skills/four-seat-protocol/SKILL.md`
- Modify: `docs/protocol/protocol-assembly-map.md` if new tool placement needs a map entry
- Modify: `.codex/agents/*.toml` only when the role prompts need the new contract command
- Test: `tests/unit/test_codex_protocol_artifacts.py`

- [ ] **Step 1: Write artifact tests first**

Extend `tests/unit/test_codex_protocol_artifacts.py` so it checks that the docs
name the new tools and preserve the source-order boundaries:

```python
def test_codex_docs_reference_seat_contract_tools_without_replacing_authority(repo_root: Path) -> None:
    continuation = (repo_root / "docs/protocol/codex/continuation.md").read_text(encoding="utf-8")
    skill = (repo_root / ".agents/skills/four-seat-protocol/SKILL.md").read_text(encoding="utf-8")

    assert "scripts/seat_banner.py" in continuation
    assert "scripts/proof_bundle.py" in continuation
    assert "scripts/done_summary.py" in skill
    assert "does not replace AGENTS.md" in continuation
```

- [ ] **Step 2: Run the artifact test to verify it fails**

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_artifacts.py -q
```

Expected: failure because docs do not yet reference the new tools.

- [ ] **Step 3: Update docs narrowly**

Add a short section to `docs/protocol/codex/continuation.md`:

```markdown
## Seat Contract Helpers

`scripts/seat_banner.py`, `scripts/proof_bundle.py`,
`scripts/protocol_guards.py`, and `scripts/done_summary.py` are helper
surfaces over the existing protocol. They do not replace `AGENTS.md`,
`ARCHITECTURE.md`, `docs/protocol/agents/`, this continuation document,
`.agents/skills/`, mailbox state, or executable gate evidence.
```

Update `.agents/skills/four-seat-protocol/SKILL.md` to mention when a live seat
may use the helpers. Keep the coordinator prohibition and user-gated push text
unchanged.

- [ ] **Step 4: Run focused docs/artifact tests**

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_artifacts.py tests/unit/test_codex_protocol_model.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
env -u GIT_INDEX_FILE git add -- docs/protocol/codex/continuation.md .agents/skills/four-seat-protocol/SKILL.md docs/protocol/protocol-assembly-map.md tests/unit/test_codex_protocol_artifacts.py
env -u GIT_INDEX_FILE git diff --cached --name-status
env -u GIT_INDEX_FILE git commit -m "docs(protocol): wire seat contract helpers" -- docs/protocol/codex/continuation.md .agents/skills/four-seat-protocol/SKILL.md docs/protocol/protocol-assembly-map.md tests/unit/test_codex_protocol_artifacts.py
```

## Task 7: Final Verification And Coordinator Wrap

**Files:**
- Create: one `coordination/mailbox/sent/*-coordinator-to-all-coordination.md` wrap event

- [ ] **Step 1: Run focused protocol tests**

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest \
  tests/unit/test_codex_protocol_model.py \
  tests/unit/test_codex_protocol_artifacts.py \
  tests/unit/test_continuation_readiness.py \
  tests/unit/test_mailbox_monitor.py \
  tests/unit/test_coordination_bin.py \
  tests/unit/test_check_coordination.py \
  tests/unit/test_seat_banner.py \
  tests/unit/test_proof_bundle.py \
  tests/unit/test_protocol_guards.py \
  tests/unit/test_done_summary.py \
  -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run protocol smoke checks**

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/check_coordination.py
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
env -u GIT_INDEX_FILE .venv/bin/python scripts/mailbox_monitor.py --once
env -u GIT_INDEX_FILE .venv/bin/python scripts/continuation_readiness.py --smoke
```

Expected: commands exit zero. Existing advisories must be reported honestly.

- [ ] **Step 3: Inspect staged scope before the wrap commit**

```bash
env -u GIT_INDEX_FILE git status --short
env -u GIT_INDEX_FILE git diff --cached --name-status
```

Expected: only protocol tooling, tests, docs, and the final coordinator mailbox
event are staged. `SEAT_PROTOCOL.md` must remain untracked unless a later,
explicit, reviewed migration says otherwise.

- [ ] **Step 4: Send one coordinator wrap event**

Use `coordination/bin/send-event coordinator all coordination` with a body that
names:

- HEAD;
- implemented helper commands;
- focused tests and smoke checks;
- no push/spend/lock status;
- exact next trigger for operators to verify or for the user to authorize push.

- [ ] **Step 5: Commit the wrap**

```bash
env -u GIT_INDEX_FILE git add -- coordination/mailbox/sent
env -u GIT_INDEX_FILE git diff --cached --name-status
env -u GIT_INDEX_FILE git commit -m "coord(protocol): wrap seat contract guard implementation" -- coordination/mailbox/sent
```

## Plan Self-Review

Spec coverage:

- Six-field contract: Tasks 1 and 2.
- Proof bundle: Task 3.
- Guard-first enforcement: Task 4.
- Done/blocked summary: Task 5.
- Source-order-preserving docs: Task 6.
- Coordinator wrap and evidence: Task 7.

No plan task promotes root `SEAT_PROTOCOL.md`, deletes existing notes, broadens
operator production authority, relaxes coordinator boundaries, authorizes push,
or performs pod/API spend.

Execution recommendation: use subagent-driven development with one fresh worker
per task and a coordinator/operator review after each commit. Do not run two
workers on shared protocol files at the same time.
