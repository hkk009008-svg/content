# Core Live-Seat Behavior Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Encode canonical live-seat behavior sources so `director` uses `director2` behavior and `operator2` uses `operator` behavior while all four concrete seat identities remain intact.

**Architecture:** Add a small behavior-source map to `scripts/codex_protocol_model.py`, render it through the runtime environment contract, and document it in the Codex live-seat surfaces. Keep mailbox, cursor, heartbeat, event-addressing, and git-index operations tied to the concrete seat, never to the behavior source.

**Tech Stack:** Python 3, pytest, TOML role prompts, Markdown protocol docs, Content four-seat mailbox/status harness.

---

## Next Seat To Initiate

Initiating seat: `director2`.

Verification seat after implementation: `operator`.

Reason: this change makes `director2` the canonical director behavior source and `operator` the canonical operator behavior source. `director2` should initiate the protocol/harness implementation. `operator` should independently verify the final diff because `operator` is the canonical operator behavior source being preserved.

Launch contract for the initiating seat:

```bash
cd /Users/hyungkoookkim/Content
export CODEX_SEAT=director2
export GIT_INDEX_FILE="$(git rev-parse --absolute-git-dir)/index-codex-director2"
[ -f "$GIT_INDEX_FILE" ] || git read-tree HEAD
codex
```

First prompt for that session:

```text
continue as director2
Implement docs/superpowers/plans/2026-06-16-core-live-seat-behavior-unification.md.
Allowed scope: scripts/codex_protocol_model.py, tests/unit/test_codex_protocol_model.py,
.codex/agents/protocol-director.toml, .codex/agents/protocol-operator.toml,
tests/unit/test_codex_protocol_artifacts.py, docs/protocol/codex/continuation.md,
.agents/skills/four-seat-protocol/SKILL.md, and a director2 verify-request mailbox event.
No production pipeline edits, no inventory edits, no lock actions, no push, no spend.
After implementation and focused verification, send a verify-request to operator.
```

## File Structure

- Modify `scripts/codex_protocol_model.py`: own the behavior-source mapping, helper, runtime env value, and runtime contract rule.
- Modify `tests/unit/test_codex_protocol_model.py`: pin the mapping, unknown-seat behavior, concrete identity preservation, and rendered runtime contract output.
- Modify `.codex/agents/protocol-director.toml`: state that `director2` is the canonical behavior source for both director seats.
- Modify `.codex/agents/protocol-operator.toml`: state that `operator` is the canonical behavior source for both operator seats.
- Modify `tests/unit/test_codex_protocol_artifacts.py`: require the role prompts and docs to name the behavior-source rule.
- Modify `docs/protocol/codex/continuation.md`: document live-seat behavior-source mapping.
- Modify `.agents/skills/four-seat-protocol/SKILL.md`: mirror the operational rule in the runtime checklist.
- Create one mailbox verify request from `director2` to `operator` after implementation:
  `coordination/mailbox/sent/<timestamp>-director2-to-operator-verify-request.md`.

## Task 0: Director2 Orientation

**Files:**
- Read: `docs/superpowers/specs/2026-06-16-core-live-seat-behavior-unification-design.md`
- Read: `docs/superpowers/plans/2026-06-16-core-live-seat-behavior-unification.md`
- Read: live mailbox bodies reported by `seat_status.py`

- [ ] **Step 1: Refresh live director2 state**

Run:

```bash
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py director2 --wave 2
env -u GIT_INDEX_FILE git log --oneline -5
env -u GIT_INDEX_FILE git status --short --branch
```

Expected: command output names current HEAD, director2 unread count, Wave 2 state, and a clean or understood worktree. Surface unread count before acting.

- [ ] **Step 2: Read relevant mailbox bodies**

For each unread or latest routing body named by `seat_status.py`, run:

```bash
sed -n '1,220p' coordination/mailbox/sent/<mailbox-file>.md
```

Expected: no newer mailbox body contradicts this plan. If a newer coordinator route supersedes this plan, stop and follow the newer route.

- [ ] **Step 3: Confirm implementation scope before edits**

Run:

```bash
env -u GIT_INDEX_FILE git diff --name-status
env -u GIT_INDEX_FILE git diff --cached --name-status
```

Expected: no unrelated staged changes. Preserve any unrelated dirty work by using explicit pathspecs in all later staging commands.

## Task 1: Kernel Behavior Source Contract

**Files:**
- Modify: `scripts/codex_protocol_model.py`
- Modify: `tests/unit/test_codex_protocol_model.py`

- [ ] **Step 1: Write failing model tests**

Add this test after `test_coordinator_invariants_pin_unpinned_cursor_and_single_route` in `tests/unit/test_codex_protocol_model.py`:

```python
def test_live_seat_behavior_sources_preserve_concrete_identity() -> None:
    assert model.SEAT_BEHAVIOR_SOURCE == {
        "director": "director2",
        "director2": "director2",
        "operator": "operator",
        "operator2": "operator",
    }
    assert model.behavior_source_for_seat("director") == "director2"
    assert model.behavior_source_for_seat("director2") == "director2"
    assert model.behavior_source_for_seat("operator") == "operator"
    assert model.behavior_source_for_seat("operator2") == "operator"
    assert model.behavior_source_for_seat("coordinator") is None
    assert model.behavior_source_for_seat("not-a-seat") is None

    director_text = model.render_runtime_env_contract(
        {
            "CODEX_SEAT": "director",
            "GIT_INDEX_FILE": "/repo/.git/index-codex-director",
        }
    )
    operator2_text = model.render_runtime_env_contract(
        {
            "CODEX_SEAT": "operator2",
            "GIT_INDEX_FILE": "/repo/.git/index-codex-operator2",
        }
    )

    assert "CODEX_AGENT_ROLE=director" in director_text
    assert "CODEX_SEAT=director" in director_text
    assert "CODEX_BEHAVIOR_SOURCE=director2" in director_text
    assert "GIT_INDEX_FILE=/repo/.git/index-codex-director" in director_text

    assert "CODEX_AGENT_ROLE=operator2" in operator2_text
    assert "CODEX_SEAT=operator2" in operator2_text
    assert "CODEX_BEHAVIOR_SOURCE=operator" in operator2_text
    assert "GIT_INDEX_FILE=/repo/.git/index-codex-operator2" in operator2_text
```

Extend the existing `test_runtime_env_contract_infers_live_seat_and_user_gated_side_effects` with:

```python
    assert "CODEX_BEHAVIOR_SOURCE=director2" in text
```

Extend the existing `test_runtime_env_contract_models_operator_and_specialist_authority` with:

```python
    assert "CODEX_BEHAVIOR_SOURCE=operator" in operator_text
    assert "CODEX_BEHAVIOR_SOURCE=(none)" in specialist_text
```

Extend the existing `test_main_renders_current_environment` with:

```python
    assert "CODEX_BEHAVIOR_SOURCE=director2" in out
```

- [ ] **Step 2: Run model tests and confirm the intended failure**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py::test_live_seat_behavior_sources_preserve_concrete_identity -q
```

Expected: FAIL because `SEAT_BEHAVIOR_SOURCE`, `behavior_source_for_seat`, or `CODEX_BEHAVIOR_SOURCE` is not defined yet.

- [ ] **Step 3: Implement behavior-source mapping and runtime env value**

In `scripts/codex_protocol_model.py`, add this block immediately after `OPERATOR_SEATS = ("operator", "operator2")`:

```python
SEAT_BEHAVIOR_SOURCE = {
    "director": "director2",
    "director2": "director2",
    "operator": "operator",
    "operator2": "operator",
}


def behavior_source_for_seat(seat: str) -> str | None:
    """Return the canonical behavior source for a concrete live seat."""
    return SEAT_BEHAVIOR_SOURCE.get(seat)
```

In `RUNTIME_ENV_VARIABLES`, add this tuple immediately after the `CODEX_SEAT` tuple:

```python
    (
        "CODEX_BEHAVIOR_SOURCE",
        "director2 | operator | (none)",
        "names the canonical live-seat behavior source while CODEX_SEAT remains the concrete mailbox, cursor, and git-index identity",
    ),
```

In `infer_runtime_env`, add this line immediately after the `seat_display` block:

```python
    behavior_source = behavior_source_for_seat(role) if mode == "live-seat" else None
```

In the returned dictionary from `infer_runtime_env`, add this entry immediately after `"CODEX_SEAT": seat_display,`:

```python
        "CODEX_BEHAVIOR_SOURCE": behavior_source or "(none)",
```

In `render_runtime_env_contract`, add this rule inside the `"contract rules:"` tuple immediately after the rule for `CODEX_SEAT selects a live seat`:

```python
            "- CODEX_BEHAVIOR_SOURCE names the canonical live-seat behavior source; CODEX_SEAT remains the concrete mailbox, cursor, and git-index identity.",
```

- [ ] **Step 4: Run focused model tests**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py -q
```

Expected: PASS for all tests in `tests/unit/test_codex_protocol_model.py`.

- [ ] **Step 5: Commit kernel contract**

Run:

```bash
env -u GIT_INDEX_FILE git status --short
env -u GIT_INDEX_FILE git add scripts/codex_protocol_model.py tests/unit/test_codex_protocol_model.py
env -u GIT_INDEX_FILE git diff --cached --name-status
env -u GIT_INDEX_FILE git commit -m "codex(protocol): add live-seat behavior source"
```

Expected staged scope:

```text
M	scripts/codex_protocol_model.py
M	tests/unit/test_codex_protocol_model.py
```

## Task 2: Role Prompt Language

**Files:**
- Modify: `.codex/agents/protocol-director.toml`
- Modify: `.codex/agents/protocol-operator.toml`
- Modify: `tests/unit/test_codex_protocol_artifacts.py`

- [ ] **Step 1: Write failing role-prompt tests**

In `tests/unit/test_codex_protocol_artifacts.py`, add a `behavior_source` expectation to the `protocol-director.toml` entry:

```python
            "behavior_source": (
                "Canonical behavior source: `director2` for both `director` "
                "and `director2`; concrete seat identity still controls "
                "mailbox, cursor, and git-index paths."
            ),
```

Add a `behavior_source` expectation to the `protocol-operator.toml` entry:

```python
            "behavior_source": (
                "Canonical behavior source: `operator` for both `operator` "
                "and `operator2`; concrete seat identity still controls "
                "mailbox, cursor, and git-index paths."
            ),
```

Inside the assertion loop in `test_core_role_prompts_are_compact_kernel_adapters`, add:

```python
        if "behavior_source" in expected:
            assert expected["behavior_source"] in text
```

- [ ] **Step 2: Run artifact test and confirm the intended failure**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_artifacts.py::test_core_role_prompts_are_compact_kernel_adapters -q
```

Expected: FAIL because the role prompts do not yet contain the canonical behavior-source sentences.

- [ ] **Step 3: Update director role prompt**

In `.codex/agents/protocol-director.toml`, insert this paragraph after the concrete-seat mode paragraph:

```text
Canonical behavior source: `director2` for both `director` and `director2`; concrete seat identity still controls mailbox, cursor, and git-index paths.
```

- [ ] **Step 4: Update operator role prompt**

In `.codex/agents/protocol-operator.toml`, insert this paragraph after the concrete-seat mode paragraph:

```text
Canonical behavior source: `operator` for both `operator` and `operator2`; concrete seat identity still controls mailbox, cursor, and git-index paths.
```

- [ ] **Step 5: Run focused artifact tests**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_artifacts.py::test_core_role_prompts_are_compact_kernel_adapters -q
```

Expected: PASS for `test_core_role_prompts_are_compact_kernel_adapters`.

- [ ] **Step 6: Commit role prompt changes**

Run:

```bash
env -u GIT_INDEX_FILE git add .codex/agents/protocol-director.toml .codex/agents/protocol-operator.toml tests/unit/test_codex_protocol_artifacts.py
env -u GIT_INDEX_FILE git diff --cached --name-status
env -u GIT_INDEX_FILE git commit -m "codex(protocol): name canonical live-seat behavior"
```

Expected staged scope:

```text
M	.codex/agents/protocol-director.toml
M	.codex/agents/protocol-operator.toml
M	tests/unit/test_codex_protocol_artifacts.py
```

## Task 3: Adapter And Skill Documentation

**Files:**
- Modify: `docs/protocol/codex/continuation.md`
- Modify: `.agents/skills/four-seat-protocol/SKILL.md`
- Modify: `tests/unit/test_codex_protocol_artifacts.py`

- [ ] **Step 1: Write failing documentation test**

Add this test after `test_codex_adapters_are_kernel_backed_and_do_not_require_default_ceremony` in `tests/unit/test_codex_protocol_artifacts.py`:

```python
def test_codex_live_seat_docs_name_behavior_source_without_identity_deletion():
    paths = [
        ROOT / "docs" / "protocol" / "codex" / "continuation.md",
        ROOT / ".agents" / "skills" / "four-seat-protocol" / "SKILL.md",
    ]

    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert (
            "Behavior source map: `director -> director2`, `director2 -> director2`, "
            "`operator -> operator`, `operator2 -> operator`."
        ) in text
        assert (
            "Mailbox, cursor, heartbeat, event-addressing, and git-index operations "
            "use the concrete seat, not the behavior source."
        ) in text
```

- [ ] **Step 2: Run documentation test and confirm the intended failure**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_artifacts.py::test_codex_live_seat_docs_name_behavior_source_without_identity_deletion -q
```

Expected: FAIL because the docs do not yet contain the behavior-source map.

- [ ] **Step 3: Update continuation adapter**

In `docs/protocol/codex/continuation.md`, add this section after `## Runtime modes`:

```markdown
## Live-Seat Behavior Sources

Concrete live-seat identity and canonical behavior source are separate.
Behavior source map: `director -> director2`, `director2 -> director2`,
`operator -> operator`, `operator2 -> operator`.

Mailbox, cursor, heartbeat, event-addressing, and git-index operations use the
concrete seat, not the behavior source. For example, `CODEX_SEAT=director`
uses director mailbox/cursor/index paths while following the `director2`
behavior source.
```

- [ ] **Step 4: Update four-seat protocol skill**

In `.agents/skills/four-seat-protocol/SKILL.md`, add this section after `## Mode selection`:

```markdown
## Live-seat behavior sources

Concrete live-seat identity and canonical behavior source are separate.
Behavior source map: `director -> director2`, `director2 -> director2`,
`operator -> operator`, `operator2 -> operator`.

Mailbox, cursor, heartbeat, event-addressing, and git-index operations use the
concrete seat, not the behavior source. For example, `CODEX_SEAT=operator2`
uses operator2 mailbox/cursor/index paths while following the `operator`
behavior source.
```

- [ ] **Step 5: Run focused documentation tests**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_artifacts.py -q
```

Expected: PASS for all tests in `tests/unit/test_codex_protocol_artifacts.py`.

- [ ] **Step 6: Commit docs and artifact tests**

Run:

```bash
env -u GIT_INDEX_FILE git add docs/protocol/codex/continuation.md .agents/skills/four-seat-protocol/SKILL.md tests/unit/test_codex_protocol_artifacts.py
env -u GIT_INDEX_FILE git diff --cached --name-status
env -u GIT_INDEX_FILE git commit -m "docs(protocol): document live-seat behavior sources"
```

Expected staged scope:

```text
M	.agents/skills/four-seat-protocol/SKILL.md
M	docs/protocol/codex/continuation.md
M	tests/unit/test_codex_protocol_artifacts.py
```

## Task 4: Full Verification And Director2 Verify Request

**Files:**
- Create: `coordination/mailbox/sent/<timestamp>-director2-to-operator-verify-request.md`

- [ ] **Step 1: Run implementation verification bundle**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py tests/unit/test_codex_protocol_artifacts.py tests/unit/test_continuation_readiness.py -q
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
```

Expected:

```text
pytest: all selected tests pass
ci_smoke.py: OK, with only existing advisories/warnings
wave_gate_check.py 2: Wave 2 gate: MET counts={'verified': 30}
```

- [ ] **Step 2: Inspect final diff scope**

Run:

```bash
env -u GIT_INDEX_FILE git log --oneline -6
env -u GIT_INDEX_FILE git show --stat --oneline HEAD~3..HEAD
env -u GIT_INDEX_FILE git status --short --branch
```

Expected: recent commits are the three implementation commits from Tasks 1-3, and the worktree has no unrelated unstaged or staged changes.

- [ ] **Step 3: Send verify request to operator**

Create a mailbox file named with the current UTC timestamp:

```bash
date -u +"%Y-%m-%dT%H-%M-%SZ-director2-to-operator-verify-request.md"
```

File body:

```markdown
# Director2 -> Operator: verify-request core live-seat behavior unification

**When:** <UTC timestamp> · **From:** director2

Please perform independent Lane V verification of the core live-seat behavior
unification implementation.

Implementation scope:
- `scripts/codex_protocol_model.py`
- `tests/unit/test_codex_protocol_model.py`
- `.codex/agents/protocol-director.toml`
- `.codex/agents/protocol-operator.toml`
- `tests/unit/test_codex_protocol_artifacts.py`
- `docs/protocol/codex/continuation.md`
- `.agents/skills/four-seat-protocol/SKILL.md`

Design source:
- `docs/superpowers/specs/2026-06-16-core-live-seat-behavior-unification-design.md`

Plan source:
- `docs/superpowers/plans/2026-06-16-core-live-seat-behavior-unification.md`

Please verify:
1. `director` keeps concrete identity while reporting behavior source `director2`.
2. `operator2` keeps concrete identity while reporting behavior source `operator`.
3. Unknown or non-live seats do not infer a live behavior source.
4. Mailbox/cursor/git-index language remains tied to concrete seats.
5. Default readiness/startup surfaces do not reintroduce demoted ceremony.

Expected evidence:
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py tests/unit/test_codex_protocol_artifacts.py tests/unit/test_continuation_readiness.py -q`
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py`
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2`

Expected output: GO/NITS/FAIL with concrete file:line findings. No production
pipeline code, inventory, lock, push, or spend action is in scope.
```

Replace `<UTC timestamp>` with the same UTC timestamp used in the filename.

- [ ] **Step 4: Commit verify request**

Run:

```bash
env -u GIT_INDEX_FILE git add coordination/mailbox/sent/<timestamp>-director2-to-operator-verify-request.md
env -u GIT_INDEX_FILE git diff --cached --name-status
env -u GIT_INDEX_FILE git commit -m "coord(verify): request live-seat behavior Lane V"
```

Expected staged scope:

```text
A	coordination/mailbox/sent/<timestamp>-director2-to-operator-verify-request.md
```

## Task 5: Operator Verification Handoff

**Files:**
- Read: implementation commits from Task 1 through Task 4
- Read: `coordination/mailbox/sent/<timestamp>-director2-to-operator-verify-request.md`

- [ ] **Step 1: Launch operator for verification**

Use this launch contract:

```bash
cd /Users/hyungkoookkim/Content
export CODEX_SEAT=operator
export GIT_INDEX_FILE="$(git rev-parse --absolute-git-dir)/index-codex-operator"
[ -f "$GIT_INDEX_FILE" ] || git read-tree HEAD
codex
```

First prompt:

```text
continue as operator
Read coordination/mailbox/sent/<timestamp>-director2-to-operator-verify-request.md.
Verify the core live-seat behavior unification implementation and issue GO/NITS/FAIL.
Do not edit production code, inventory, locks, or push.
```

- [ ] **Step 2: Operator verification commands**

Operator should run:

```bash
.venv/bin/python .agents/skills/four-seat-protocol/scripts/seat_status.py operator --wave 2
env -u GIT_INDEX_FILE git log --oneline -8
env -u GIT_INDEX_FILE git show --stat --patch --find-renames --find-copies HEAD~4..HEAD -- scripts/codex_protocol_model.py tests/unit/test_codex_protocol_model.py .codex/agents/protocol-director.toml .codex/agents/protocol-operator.toml tests/unit/test_codex_protocol_artifacts.py docs/protocol/codex/continuation.md .agents/skills/four-seat-protocol/SKILL.md coordination/mailbox/sent
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py tests/unit/test_codex_protocol_artifacts.py tests/unit/test_continuation_readiness.py -q
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
```

Expected: operator produces one mailbox verification report with GO/NITS/FAIL and executed evidence.

## Final Verification For Director2 Before Stopping

After Task 4, director2 should report:

- current HEAD;
- exact commits made;
- verification commands and outputs;
- verify-request mailbox file path;
- dirty/staged state;
- exact next trigger: `continue as operator` to perform Lane V.

Do not push. Push remains user-gated.
