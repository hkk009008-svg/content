# Protocol Harness Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the approved protocol harness unification by making `scripts/codex_protocol_model.py` the thin kernel and turning Codex docs, skills, and role prompts into checked adapter surfaces.

**Architecture:** The executable kernel owns active invariants, runtime modes, side-effect gates, and demoted optional concepts. Adapter surfaces repeat only short command checklists and point back to the kernel; focused tests prevent drift, mandatory ceremony language, and duplicated default workflows from returning.

**Tech Stack:** Python stdlib, pytest, Markdown docs, TOML role prompts, existing Codex protocol scripts.

---

## File Structure

- `scripts/codex_protocol_model.py`: canonical active invariants, optional/demoted concepts, runtime contract rendering, and compact adapter text.
- `tests/unit/test_codex_protocol_model.py`: model-level tests for active invariants, demoted concepts, live-loop vocabulary, and runtime rendering.
- `tests/unit/test_codex_protocol_artifacts.py`: artifact tests for adapter surfaces and role TOMLs.
- `docs/protocol/codex/continuation.md`: Codex operating adapter, not a duplicate manual.
- `.agents/skills/four-seat-protocol/SKILL.md`: short runtime checklist.
- `.agents/skills/seat-coordinator/SKILL.md`: short coordinator authority checklist.
- `.codex/agents/protocol-coordinator.toml`, `.codex/agents/protocol-director.toml`, `.codex/agents/protocol-operator.toml`: compact role prompts.
- `AGENTS.md`: root process pointer to the kernel-backed Codex harness.

## Task 1: Kernel Demotion Metadata And Model Tests

**Files:**
- Modify: `scripts/codex_protocol_model.py`
- Modify: `tests/unit/test_codex_protocol_model.py`

- [ ] **Step 1: Add failing model tests for the thin-kernel contract**

Add tests that assert:

```python
def test_kernel_names_active_invariants_and_demoted_runtime_concepts() -> None:
    text = model.render_kernel_contract()

    assert "Active kernel invariants" in text
    assert "durable shared state beats chat memory" in text
    assert "mailbox-first decisions" in text
    assert "explicit mode" in text
    assert "user-gated side effects" in text
    assert "operator verification-report GO" in text
    assert "Demoted optional concepts" in text
    assert "capacity-max cycle: explicit coordinator tool" in text
    assert "no-op evidence: only after a seat was actually queried or oriented" in text
    assert "Rotating Planning Relay: optional rare cross-seat planning pattern" in text
    assert "proof-bundle language: use concrete evidence names" in text


def test_live_loop_uses_concrete_evidence_and_not_default_ceremony() -> None:
    loop = model.render_live_loop()

    assert "mailbox bodies" in loop
    assert "gate output" in loop
    assert "smoke output" in loop
    assert "diff scope" in loop
    assert "Use the Rotating Planning Relay" not in loop
    assert "no-op evidence so the coordinator knows" not in loop
    assert "proof bundle" not in loop.lower()
```

- [ ] **Step 2: Run the model tests and verify RED**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py -q
```

Expected: failure because `render_kernel_contract()` does not exist and the live loop still includes mandatory relay wording.

- [ ] **Step 3: Add the minimal kernel implementation**

In `scripts/codex_protocol_model.py`, add:

```python
ACTIVE_KERNEL_INVARIANTS = (
    ("durable shared state beats chat memory", "read git, mailbox bodies, cursors, locks, logs, gate evidence, and operator reports before stale prose"),
    ("mailbox-first decisions", "check mail and read relevant bodies before protocol decisions or state-asserting writes"),
    ("explicit mode", "readiness bridge, live seat, coordinator, and subagent stay distinct"),
    ("coordinator is unpinned", "coordinator reads all-scope mail and never consumes a coordinator cursor"),
    ("env-u git policy", "ordinary git and pytest use env -u GIT_INDEX_FILE unless maintaining a seat index"),
    ("user-gated side effects", "push, lock-claim side effects, paid API spend, and pod spend require explicit user consent"),
    ("coordinator no production fixes", "coordinator may route and reconcile but not author behavior-changing production fixes"),
    ("operator verification-report GO", "verified transitions require operator GO plus executed evidence"),
    ("wave gate is evidence", "wave_gate_check.py is process evidence, not row-correctness proof"),
    ("single consolidated route", "cross-seat awareness uses one coordinator event when routing is warranted"),
)

DEMOTED_RUNTIME_CONCEPTS = (
    ("capacity-max cycle", "explicit coordinator tool for active multi-seat work, not every status check"),
    ("no-op evidence", "only after a seat was actually queried or oriented"),
    ("Rotating Planning Relay", "optional rare cross-seat planning pattern"),
    ("protocol-effectiveness report", "read-only diagnostics only"),
    ("proof-bundle language", "use concrete evidence names: status, git log, mailbox bodies, gate output, smoke output, and diff scope"),
    ("handoff ceremony", "narrow handoff only at real transfer boundaries or explicit request"),
)
```

Then add `render_kernel_contract()` and update `LIVE_LOOP_STEPS` so the default loop uses concrete evidence names and does not require the relay.

- [ ] **Step 4: Run model tests and verify GREEN**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py -q
```

Expected: all tests in that file pass.

- [ ] **Step 5: Commit Task 1**

```bash
env -u GIT_INDEX_FILE git add scripts/codex_protocol_model.py tests/unit/test_codex_protocol_model.py
env -u GIT_INDEX_FILE git commit -m "codex(protocol): slim harness kernel"
```

## Task 2: Adapter Docs And Skills

**Files:**
- Modify: `tests/unit/test_codex_protocol_artifacts.py`
- Modify: `docs/protocol/codex/continuation.md`
- Modify: `.agents/skills/four-seat-protocol/SKILL.md`
- Modify: `.agents/skills/seat-coordinator/SKILL.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Add failing adapter artifact tests**

Add tests that read the four adapter surfaces and assert:

```python
def test_codex_adapters_are_kernel_backed_and_do_not_require_default_ceremony():
    paths = [
        ROOT / "docs" / "protocol" / "codex" / "continuation.md",
        ROOT / ".agents" / "skills" / "four-seat-protocol" / "SKILL.md",
        ROOT / ".agents" / "skills" / "seat-coordinator" / "SKILL.md",
        ROOT / "AGENTS.md",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "scripts/codex_protocol_model.py" in text
        assert "durable shared state beats chat memory" in text
        assert "mailbox-first" in text.lower() or "check mail" in text.lower()
        assert "proof bundle" not in text.lower()
        assert "proof-bundle" not in text.lower()
        assert "Rotating Planning Relay" not in text
        assert "Idle seats return no-op evidence" not in text
        assert "every eligible seat" not in text
```

Also update existing artifact tests so they no longer require default capacity-max, relay, or no-op evidence language in adapter surfaces.

- [ ] **Step 2: Run artifact tests and verify RED**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_artifacts.py -q
```

Expected: failures because the adapters still contain duplicated mandatory relay/capacity/no-op wording.

- [ ] **Step 3: Trim the adapters**

Replace long duplicated doctrine with short adapter content:

- `docs/protocol/codex/continuation.md` keeps: kernel source, runtime modes, first commands for readiness/live/coordinator, mailbox-first rule, side-effect gate, optional tools, subagent note, and verification commands.
- `.agents/skills/four-seat-protocol/SKILL.md` keeps: source order, mode selection, readiness/live/coordinator checklists, mailbox/cursor rules, git-index rule, and related files.
- `.agents/skills/seat-coordinator/SKILL.md` keeps: coordinator prohibition, first commands, inventory/gate authority, no-op fast path, allowed coordinator writes, and push/lock/spend gates.
- `AGENTS.md` Codex section points to the kernel and continuation adapter without duplicating capacity-max/no-op details.

Do not edit production pipeline modules. Preserve the meaning of proven active invariants.

- [ ] **Step 4: Run artifact tests and verify GREEN**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_artifacts.py -q
```

Expected: all artifact tests pass.

- [ ] **Step 5: Commit Task 2**

```bash
env -u GIT_INDEX_FILE git add AGENTS.md docs/protocol/codex/continuation.md .agents/skills/four-seat-protocol/SKILL.md .agents/skills/seat-coordinator/SKILL.md tests/unit/test_codex_protocol_artifacts.py
env -u GIT_INDEX_FILE git commit -m "docs(protocol): trim codex harness adapters"
```

## Task 3: Role Prompts And Final Drift Guards

**Files:**
- Modify: `tests/unit/test_codex_protocol_artifacts.py`
- Modify: `.codex/agents/protocol-coordinator.toml`
- Modify: `.codex/agents/protocol-director.toml`
- Modify: `.codex/agents/protocol-operator.toml`

- [ ] **Step 1: Add failing role-prompt tests**

Add tests that require the three role prompts to name mode, first commands, authority boundary, mutation boundary, mailbox-first rule, expected output, and kernel source. Also assert they do not contain default relay/no-op/proof-bundle ceremony language:

```python
def test_core_role_prompts_are_compact_kernel_adapters():
    for name in ("protocol-coordinator.toml", "protocol-director.toml", "protocol-operator.toml"):
        data = tomllib.loads((ROOT / ".codex" / "agents" / name).read_text(encoding="utf-8"))
        text = data["developer_instructions"]
        assert "scripts/codex_protocol_model.py" in text
        assert "durable shared state beats chat memory" in text
        assert "Allowed mutation" in text
        assert "Expected output" in text
        assert "Always check mail" in text
        assert "Rotating Planning Relay" not in text
        assert "proof bundle" not in text.lower()
        assert "idle/no-op evidence" not in text.lower()
```

- [ ] **Step 2: Run the role artifact tests and verify RED**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_artifacts.py -q
```

Expected: failures because existing prompts still carry duplicated capacity/relay/no-op text.

- [ ] **Step 3: Trim the three core role prompts**

Each prompt should be compact:

- `protocol-coordinator`: explicit coordinator use, first four commands, allowed mutation `coordination/docs/logs only`, coordinator prohibition, expected capacity-board/single-route/no-op report.
- `protocol-director`: explicit concrete director seat, first two commands, mailbox-first, allowed mutation `seat-owned docs/code within route`, no operator GO, expected brief/fix/verify-request or blocked handoff.
- `protocol-operator`: explicit concrete operator seat, first two commands, mailbox-first, allowed mutation `verification report/cursor/docs only unless user overrides`, no production fixes by default, expected GO/NITS/FAIL or no target report.

- [ ] **Step 4: Run artifact tests and verify GREEN**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_artifacts.py -q
```

Expected: all artifact tests pass.

- [ ] **Step 5: Commit Task 3**

```bash
env -u GIT_INDEX_FILE git add tests/unit/test_codex_protocol_artifacts.py .codex/agents/protocol-coordinator.toml .codex/agents/protocol-director.toml .codex/agents/protocol-operator.toml
env -u GIT_INDEX_FILE git commit -m "codex(protocol): compact role prompt adapters"
```

## Final Verification

- [ ] Run focused protocol tests:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py tests/unit/test_codex_protocol_artifacts.py tests/unit/test_continuation_readiness.py -q
```

- [ ] Run coordination/ceremony checks:

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/check_coordination.py
env -u GIT_INDEX_FILE .venv/bin/python scripts/check_no_ceremony.py
```

- [ ] Run smoke:

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
```

- [ ] Inspect final scope:

```bash
env -u GIT_INDEX_FILE git status --short
env -u GIT_INDEX_FILE git log --oneline -8
env -u GIT_INDEX_FILE git show --stat --oneline HEAD
```

Expected: only protocol/docs/tests/role-prompt files changed by the new commits; no production pipeline modules changed; no push performed.
