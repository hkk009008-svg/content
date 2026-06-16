# Hard-Gated Capacity Scheduler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only protocol capacity scheduler that renders actor packets, fails closed on invalid routing state, validates coordinator task-board events, and documents the new gate for future seats.

**Architecture:** Add an importable scheduler module plus a thin CLI. Tests use temporary repo fixtures so mailbox, locks, packets, exceptions, and inventory behavior are verified without mutating the live protocol state.

**Tech Stack:** Python stdlib (`argparse`, `dataclasses`, `json`, `pathlib`, `subprocess`), pytest, existing protocol docs and skills.

---

### Task 1: Core Scheduler Model

**Files:**
- Create: `scripts/protocol_capacity.py`
- Create: `scripts/protocol_capacity_board.py`
- Test: `tests/unit/test_protocol_capacity_board.py`

- [ ] **Step 1: Write failing tests** for packet schema parsing, exception schema parsing, malformed JSON, invalid owner, invalid packet type, invalid status, one-active-packet-per-seat coverage, WIP limit, path/lock overlap, DAG missing dependency, and DAG cycle rejection.
- [ ] **Step 2: Run tests to verify RED**

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py -q
```

Expected: fails because `protocol_capacity` does not exist.

- [ ] **Step 3: Implement minimal core model** with `CapacityError`, `Packet`, `ProtocolException`, `CapacityReport`, `collect_capacity_report(root, wave, ...)`, and `render_capacity_board(report)`.
- [ ] **Step 4: Run tests to verify GREEN** with the same command.

### Task 2: CLI And JSON Output

**Files:**
- Modify: `scripts/protocol_capacity_board.py`
- Test: `tests/unit/test_protocol_capacity_board.py`

- [ ] **Step 1: Write failing tests** for `main(["--root", tmp, "--wave", "4"])` text output and `--json` machine output.
- [ ] **Step 2: Run tests to verify RED** with the focused pytest command.
- [ ] **Step 3: Implement CLI** with `--root`, `--wave`, `--json`, and `--validate-route`.
- [ ] **Step 4: Run tests to verify GREEN** with the focused pytest command.

### Task 3: Route Validation And Exceptions

**Files:**
- Modify: `scripts/protocol_capacity.py`
- Modify: `scripts/protocol_capacity_board.py`
- Test: `tests/unit/test_protocol_capacity_board.py`

- [ ] **Step 1: Write failing tests** for a valid coordinator task-board route, a route missing packet ids, a route missing join condition, a route that implies push/spend/lock side effects, exception exact-match success, and exception scope mismatch failure.
- [ ] **Step 2: Run tests to verify RED** with the focused pytest command.
- [ ] **Step 3: Implement route validation** that recognizes coordinator-to-all task-board mail, requires all packet ids, checks packet existence and seat coverage, blocks forbidden side effects, requires a join condition, and applies only exact matching active exceptions.
- [ ] **Step 4: Run tests to verify GREEN** with the focused pytest command.

### Task 4: Protocol Integration

**Files:**
- Modify: `scripts/codex_protocol_model.py`
- Modify: `tests/unit/test_codex_protocol_model.py`
- Modify: `docs/protocol/codex/continuation.md`
- Modify: `.agents/skills/four-seat-protocol/SKILL.md`
- Modify: `.agents/skills/seat-coordinator/SKILL.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Write failing tests** that the Codex protocol model mentions the capacity board before active coordinator task-board routes.
- [ ] **Step 2: Run tests to verify RED**

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py -q
```

- [ ] **Step 3: Update docs and skill checklists** so active coordinator task-board routes run `scripts/protocol_capacity_board.py --wave <N>` and route validation before commit.
- [ ] **Step 4: Run tests to verify GREEN** with the model test command.

### Task 5: Verification

**Files:**
- Verify all changed files.

- [ ] **Step 1: Run focused scheduler tests**

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_protocol_capacity_board.py -q
```

- [ ] **Step 2: Run protocol model and artifact tests**

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_codex_protocol_model.py tests/unit/test_codex_protocol_artifacts.py -q
```

- [ ] **Step 3: Run smoke**

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
```

- [ ] **Step 4: Inspect scope**

```bash
env -u GIT_INDEX_FILE git diff --stat
env -u GIT_INDEX_FILE git status --short
```
