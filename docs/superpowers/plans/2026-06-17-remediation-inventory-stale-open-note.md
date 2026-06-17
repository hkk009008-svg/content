# Remediation Inventory Stale Open Note Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove stale "still-open" wording from the remediation inventory when the referenced row is already `verified`, and add a regression check that prevents the same contradiction from reappearing.

**Architecture:** Keep this as a coordinator-owned docs/test correction. Do not touch production pipeline code, locks, spend surfaces, or mailbox cursors. Add one focused unit test that parses `docs/REMEDIATION-INVENTORY.md` and fails when a closed/excluded note calls a `verified` row "still-open".

**Tech Stack:** Markdown inventory, Python stdlib parsing, pytest.

---

### File Structure

- Modify: `docs/REMEDIATION-INVENTORY.md`
  - Responsibility: campaign inventory source of truth and historical notes.
  - Change: rewrite the stale `null-continuity-crash` note so it says the sibling row is tracked above and now verified.
- Create: `tests/unit/test_remediation_inventory_doc_consistency.py`
  - Responsibility: guard inventory prose against contradictions with row status.
  - Change: parse the inventory table, find verified IDs, and fail if the prose says a verified row is still open.

### Task 1: Add A Regression For Verified Rows Called Still Open

**Files:**
- Create: `tests/unit/test_remediation_inventory_doc_consistency.py`

- [x] **Step 1: Write the failing test**

Create `tests/unit/test_remediation_inventory_doc_consistency.py` with:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "docs" / "REMEDIATION-INVENTORY.md"


def _inventory_rows(text: str) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        if not line.startswith("| "):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 13 or cells[0] in {"id", "----"}:
            continue
        rows[cells[0]] = {
            "id": cells[0],
            "status": cells[11],
        }
    return rows


def test_verified_inventory_rows_are_not_described_as_still_open() -> None:
    text = INVENTORY.read_text(encoding="utf-8")
    rows = _inventory_rows(text)
    verified_ids = {row_id for row_id, row in rows.items() if row["status"] == "verified"}

    stale_mentions = [
        row_id
        for row_id in verified_ids
        if f"`{row_id}`" in text and f"`{row_id}` above is a *separate, still-open*" in text
    ]

    assert stale_mentions == []
```

- [x] **Step 2: Run the test to verify it fails**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_remediation_inventory_doc_consistency.py -q
```

Expected:

```text
FAILED tests/unit/test_remediation_inventory_doc_consistency.py::test_verified_inventory_rows_are_not_described_as_still_open
E       AssertionError: assert ['null-continuity-crash'] == []
```

- [ ] **Step 3: Commit the failing regression pin**

Do this only if the project convention allows a temporary red commit for plan execution. Otherwise keep the test unstaged until Task 2.

```bash
env -u GIT_INDEX_FILE git add tests/unit/test_remediation_inventory_doc_consistency.py
env -u GIT_INDEX_FILE git commit -m "test(protocol): pin remediation inventory stale-open wording"
```

### Task 2: Correct The Inventory Note

**Files:**
- Modify: `docs/REMEDIATION-INVENTORY.md:82`

- [x] **Step 1: Replace the stale sentence**

Change line 82 from:

```markdown
- **`workflow_selector.py`** — the main non-finite/param issue is closed by `bf1034a` (re-verify only). NOTE: `null-continuity-crash` above is a *separate, still-open* sibling crash in the same module that `bf1034a`'s audit boundary did not extend to.
```

to:

```markdown
- **`workflow_selector.py`** — the main non-finite/param issue is closed by `bf1034a` (re-verify only). NOTE: `null-continuity-crash` above was a separate sibling crash in the same module that `bf1034a`'s audit boundary did not extend to; it is now tracked above as `verified` with operator-1 GO evidence.
```

- [x] **Step 2: Run the new regression**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_remediation_inventory_doc_consistency.py -q
```

Expected:

```text
1 passed
```

- [x] **Step 3: Verify inventory row status still agrees with the coordinator readout**

Run:

```bash
awk -F'|' '/^\| [A-Za-z0-9_-]+ / {gsub(/^ +| +$/, "", $2); gsub(/^ +| +$/, "", $13); if ($2 != "id") {rows++; status[$13]++}} END {print "rows=" rows; for (s in status) print "status " s "=" status[s]}' docs/REMEDIATION-INVENTORY.md
```

Expected:

```text
rows=42
status verified=42
```

- [ ] **Step 4: Run coordinator-safe verification**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_doctor.py --wave 5
```

Expected:

```text
RESULT: no ceremony detected
OK
PROTOCOL DOCTOR: PASS
```

- [ ] **Step 5: Commit the docs/test correction**

Run:

```bash
env -u GIT_INDEX_FILE git add docs/REMEDIATION-INVENTORY.md tests/unit/test_remediation_inventory_doc_consistency.py
env -u GIT_INDEX_FILE git commit -m "docs(protocol): fix stale remediation inventory open note"
```

### Task 3: Coordinator Closeout

**Files:**
- Read: `coordination/mailbox/sent/2026-06-17T08-51-24Z-coordinator-to-all-coordination.md`
- Read: `docs/HANDOFF-coordinator-2026-06-17-wave5-dual-binding-closeout.md`
- Optional create: `docs/HANDOFF-coordinator-2026-06-17-remediation-inventory-note.md`

- [ ] **Step 1: Recheck mailbox and route state**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/mailbox_monitor.py --once
env -u GIT_INDEX_FILE .venv/bin/python scripts/protocol_capacity_board.py --wave 5
```

Expected:

```text
receipt split: consumed=4 unread=0 unknown=0
valid: true
BLOCKING ISSUES
- none
```

- [ ] **Step 2: Decide whether a mailbox event is warranted**

Do not send a mailbox event if the only change is this docs/test correction and all seats still have unread `0`. This correction does not route new production work, change a gate, claim/release locks, or require operator GO.

- [ ] **Step 3: Write a handoff only if this becomes a real transfer boundary**

If the implementation is the final action before context transfer, create a narrow handoff:

```markdown
# Coordinator Handoff - Remediation Inventory Stale Note Correction

Repo: `/Users/hyungkoookkim/Content`

## Scope

Docs/test-only correction for stale `null-continuity-crash` wording in `docs/REMEDIATION-INVENTORY.md`.

## Evidence

- `tests/unit/test_remediation_inventory_doc_consistency.py -q` -> `1 passed`
- `scripts/ci_smoke.py` -> `OK`
- `scripts/protocol_doctor.py --wave 5` -> `PROTOCOL DOCTOR: PASS`
- `scripts/mailbox_monitor.py --once` -> all seats unread `0`

## Exact Next Trigger

`push`
```

- [ ] **Step 4: Inspect scope before stopping**

Run:

```bash
env -u GIT_INDEX_FILE git status --short --branch
env -u GIT_INDEX_FILE git show --stat --oneline --no-renames HEAD
```

Expected:

```text
Only docs/test/optional handoff files changed by this plan are in scope.
```

### Self-Review

- Spec coverage: fixes the exact contradiction observed in `docs/REMEDIATION-INVENTORY.md:82` and protects it with an executable doc-consistency test.
- Placeholder scan: no `TBD`, `TODO`, or unspecified test commands remain.
- Protocol fit: coordinator-owned docs/test scope only; no production pipeline edits, no lock side effects, no cursor consumption, no spend, and no push without user instruction.
