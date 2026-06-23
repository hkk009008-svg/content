# overseer-plan auto-decompose layer — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking. Per the user's standing directive (2026-06-21), subagent dispatches default to `model: 'sonnet'`; escalate to `opus` only after asking. NOTE: per CLAUDE.md R-ORCH this is a SINGLE tightly-coupled component (~300 LOC, one new script + one new test file) → execute in MAIN context (TDD), not fan-out; independent Lane-V (non-author) follows.

**Goal:** Add `scripts/overseer_plan.py` — a layer above the verified `overseer_emit` that reads one JSON chief-decision file + the live bus and, on `--confirm`, emits the overseer facts emittable now (`brief`/`assignment`/`cycle_go`), surfacing the rest as owed; it never emits `release_order`.

**Architecture:** Pure consumer of `overseer_emit.main(argv)` (one signing path, no fact-shape duplication). A presence-based planner queries the reduced `EffectiveState` for absent overseer facts; dry-run by default; `--confirm` forwards each emit through `overseer_emit`. Idempotent (re-reads the bus each run, plans only absent facts).

**Tech Stack:** Python 3, pytest. Signed event-sourced bus (`threeway/`), Ed25519 + RFC 8785. **Run threeway tests with the mandatory `env -u GIT_INDEX_FILE` prefix; repo python is `.venv/bin/python` (no bare `python`).** Acceptance gates: `scripts/ci_smoke.py`, `scripts/check_no_ceremony.py`.

**Spec:** [`docs/superpowers/specs/2026-06-23-overseer-plan-auto-decompose-design.md`](../specs/2026-06-23-overseer-plan-auto-decompose-design.md). Baseline HEAD `b4eae43a`.

---

## Verified anchors (re-derived at HEAD `b4eae43a` / `a488276a`; do NOT re-derive)

- `EffectiveState` accessors (all methods; `threeway/reducer.py`): `brief(brief_id, version)` :94, `assignment(pair)` :180, `cycle_go(brief_id, version)` :106, `release_order(candidate_id)` :109, `candidate(candidate_id, seat=None)` :118, `ci_result(subject_sha)` :115, `effective_attestation(candidate_id, att_kind, seat)` :85 (returns a raw `Event | None`). All return `None` when absent.
- `verify_and_reduce(events, registry_dir, bus_id, gate_seat="merge-gate")` (`threeway/gate.py:38`); `reduce(events)` (`threeway/reducer.py:226`, no signing — for pure planner unit tests).
- `RefEventStore(repo, remote=None)` (`refstore.py:92`); `.all_events()` (`:230`).
- `scripts/overseer_emit.py`: `main(argv) -> int` (`:85`, 0 ok / 1 fail), `BUS="prod"` (`:24`), `_common` registers `--bus-id` (`:91`), `--remote` default `origin` normalizing `""`/`none`→local (`:93`,`:129-130`). Subcommand flags verified at `:95-126`.
- Import reuse: `from scripts import overseer_emit` (namespace package; repo-root on `sys.path` via the ADR-055 bootstrap) — same idiom as `test_threeway_merge_gate_daemon.py:74 from scripts import run_merge_gate`.
- `threeway.policy.default_policy().policy_digest()` is the digest the gate checks `cycle_go` against (`predicate.py:121`).
- Test fixtures are FILE-LOCAL (no threeway `conftest.py`): copy `seatkit` from `tests/unit/test_threeway_gate.py:17-34` (per-seat keypairs → registry `.pub` + keystore hex; `monkeypatch.setenv("THREEWAY_KEYSTORE", ks)`; returns `(reg, ks, privs)`; seats include `overseer, ci, merge-gate, coordinator, operator`).

## File structure

| File | Responsibility | Change |
|---|---|---|
| `scripts/overseer_plan.py` | decision loader + presence planner + dry-run/confirm CLI; reuses `overseer_emit` | **Create** |
| `tests/unit/test_threeway_overseer_plan.py` | loader/planner/dry-run/confirm/idempotency/tier pins | **Create** |
| `tests/unit/test_threeway_activation_scripts.py` | add `overseer_plan.py` to the bare-subprocess pin | **Modify** |
| `DECISIONS.md` | ADR-057 (DD-1..DD-5) | **Modify** (append) |
| `ARCHITECTURE.md` | record the new script in the threeway topology | **Modify** |

> All files are new except two append/extend edits. No shared-lock needed (peers offline; re-anchor before each commit anyway).

---

## Chunk 1: overseer_plan.py — loader, planner, dry-run, confirm

### Task 1: Decision loader + validation

**Files:** Create `scripts/overseer_plan.py`; Create `tests/unit/test_threeway_overseer_plan.py`.

- [ ] **Step 1 (RED):** write loader pins. Put the helpers + these tests in the new test file.

```python
import json, os, subprocess, sys
from pathlib import Path
import pytest
from threeway.gate import verify_and_reduce
from threeway.reducer import reduce
from threeway.refstore import RefEventStore
# copy seatkit from tests/unit/test_threeway_gate.py:17-34 into this file

_REPO_ROOT = Path(__file__).resolve().parents[2]

def _new_repo(tmp_path):
    r = tmp_path / "repo"; r.mkdir()
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    return r

def _decision_dict(**over):
    d = {"schema": "overseer-decision/1", "candidate_id": "A:c1", "brief_id": "b1",
         "brief_version": 1, "tier": "T1", "allowed_paths": ["cinema/"],
         "assignment": {"pair": "A", "builder": "director", "builder_provider": "codex",
                        "primary_verifier": "operator", "primary_verifier_provider": "claude",
                        "executing_coordinator": "coordinator"},
         "policy_digest": None}
    d.update(over); return d

def _decision_file(tmp_path, **over):
    p = tmp_path / "decision.json"; p.write_text(json.dumps(_decision_dict(**over))); return p

def test_load_decision_valid(tmp_path):
    from scripts.overseer_plan import load_decision
    d = load_decision(str(_decision_file(tmp_path)))
    assert d["candidate_id"] == "A:c1" and d["brief_version"] == 1
    assert d["assignment"]["primary_verifier"] == "operator"

def test_load_decision_missing_field_is_decision_error(tmp_path):
    from scripts.overseer_plan import load_decision, DecisionError
    bad = _decision_dict(); del bad["brief_id"]
    p = tmp_path / "bad.json"; p.write_text(json.dumps(bad))
    with pytest.raises(DecisionError):
        load_decision(str(p))

def test_load_decision_rejects_t3(tmp_path):
    from scripts.overseer_plan import load_decision, DecisionError
    with pytest.raises(DecisionError):
        load_decision(str(_decision_file(tmp_path, tier="T3")))

def test_main_bad_decision_returns_rc2(tmp_path):
    from scripts.overseer_plan import main
    bad = _decision_dict(); del bad["assignment"]
    p = tmp_path / "bad.json"; p.write_text(json.dumps(bad))
    assert main(["--decision", str(p), "--repo-dir", str(_new_repo(tmp_path)), "--remote", ""]) == 2
```

- [ ] **Step 2: run → FAIL** (`ModuleNotFoundError: scripts.overseer_plan`).
Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_overseer_plan.py -q`

- [ ] **Step 3 (GREEN):** create `scripts/overseer_plan.py` with the header/bootstrap, `SCHEMA`, `DecisionError`, `load_decision`, `_policy_digest`, and an argparse `main` whose error path returns rc 2 (the planner/confirm come in Tasks 2-3 — for now `main` may just load+`return 2` on error, `return 0` otherwise; Task 2 fleshes the body). Use the exact code in §"Full overseer_plan.py" below (write the whole file once; later tasks only add tests).

- [ ] **Step 4: run → PASS** the four loader tests.
- [ ] **Step 5: Commit** `feat(threeway): overseer_plan decision loader + validation [ADR-057]`.

### Task 2: Presence planner (emittable + owed)

**Files:** `scripts/overseer_plan.py` (already complete from Task 1's full-file write); add tests.

- [ ] **Step 1 (RED):** planner pins (use `reduce([])` for the empty-state unit; a real bus for idempotency).

```python
def test_plan_empty_bus_emits_all_three_and_owes_the_rest(tmp_path):
    from scripts.overseer_plan import load_decision, plan
    d = load_decision(str(_decision_file(tmp_path)))
    emittable, owed = plan(d, reduce([]))
    assert emittable == ["brief", "assignment", "cycle_go"]
    owed_facts = {f for f, _ in owed}
    assert ("release_order", "overseer-manual") in owed
    assert "candidate" in owed_facts and "attestation:preliminary" in owed_facts

def test_plan_idempotent_after_brief_present(seatkit, tmp_path):
    reg, ks, privs = seatkit
    repo = _new_repo(tmp_path)
    from scripts import overseer_emit
    from scripts.overseer_plan import load_decision, plan
    # emit ONLY brief via overseer_emit directly
    assert overseer_emit.main(["brief", "--candidate-id", "A:c1", "--brief-id", "b1",
                               "--assigned-tier", "T1", "--allowed-paths", "cinema/",
                               "--repo-dir", str(repo), "--remote", ""]) == 0
    state = verify_and_reduce(RefEventStore(Path(repo)).all_events(), registry_dir=str(reg), bus_id="prod")
    emittable, _ = plan(load_decision(str(_decision_file(tmp_path))), state)
    assert emittable == ["assignment", "cycle_go"]   # brief no longer emittable
```

- [ ] **Step 2: run → FAIL** (no `plan`, or wrong result) — if you wrote the full file in Task 1, `plan` exists and these pass; otherwise add `plan`. Confirm RED→GREEN by temporarily breaking one accessor check.
- [ ] **Step 3 (GREEN):** ensure `plan` matches §"Full overseer_plan.py".
- [ ] **Step 4: run → PASS.**
- [ ] **Step 5: Commit** `feat(threeway): overseer_plan presence planner (emittable + owed) [ADR-057]`.

### Task 3: dry-run (default, signs nothing) + `--confirm` (reuse overseer_emit) + Q4 guard

**Files:** `scripts/overseer_plan.py`; add tests.

- [ ] **Step 1 (RED):**

```python
def _events(repo): return RefEventStore(Path(repo)).all_events()

def test_dry_run_default_emits_nothing(seatkit, tmp_path, capsys):
    reg, ks, privs = seatkit; repo = _new_repo(tmp_path)
    from scripts.overseer_plan import main
    rc = main(["--decision", str(_decision_file(tmp_path)), "--repo-dir", str(repo),
               "--registry-dir", str(reg), "--remote", ""])
    assert rc == 0
    assert len(_events(repo)) == 0                       # bus byte-unchanged — nothing signed
    assert "WOULD EMIT" in capsys.readouterr().out

def test_confirm_emits_overseer_facts_never_release_order(seatkit, tmp_path):
    reg, ks, privs = seatkit; repo = _new_repo(tmp_path)
    from scripts.overseer_plan import main
    rc = main(["--decision", str(_decision_file(tmp_path)), "--repo-dir", str(repo),
               "--registry-dir", str(reg), "--remote", "", "--confirm"])
    assert rc == 0
    state = verify_and_reduce(_events(repo), registry_dir=str(reg), bus_id="prod")
    assert state.brief("b1", 1) is not None and state.brief("b1", 1).signer.split(":", 1)[0] == "overseer"
    assert state.assignment("A") is not None and state.cycle_go("b1", 1) is not None
    assert state.release_order("A:c1") is None           # Q4 GUARD: overseer_plan never emits it
```

- [ ] **Step 2: run → FAIL** (dry-run/confirm body absent).
- [ ] **Step 3 (GREEN):** ensure `main`'s dry-run + confirm loop match §"Full overseer_plan.py".
- [ ] **Step 4: run → PASS** the full file.
Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_overseer_plan.py -q`
- [ ] **Step 5 (mutation — prove the Q4 guard is load-bearing):** temporarily add `"release_order"` to `_EMITTABLE` and add an arm to `_emit_argv` (e.g. `release_order` with `--integration-sha deadbeef`); run `test_confirm_emits_overseer_facts_never_release_order` → it MUST go RED (`state.release_order` non-None). Then REVERT. Record the RED in the commit body.
- [ ] **Step 6: Commit** `feat(threeway): overseer_plan dry-run + --confirm (reuse overseer_emit; release_order never auto-emitted) [ADR-057]`.

### Task 4: idempotency pin

**Files:** add a test only.

- [ ] **Step 1 (RED):**
```python
def test_confirm_idempotent_second_run_is_noop(seatkit, tmp_path):
    reg, ks, privs = seatkit; repo = _new_repo(tmp_path)
    from scripts.overseer_plan import main
    args = ["--decision", str(_decision_file(tmp_path)), "--repo-dir", str(repo),
            "--registry-dir", str(reg), "--remote", "", "--confirm"]
    assert main(args) == 0
    n_after_first = len(_events(repo))
    assert main(args) == 0                  # second run: nothing emittable
    assert len(_events(repo)) == n_after_first   # zero new events; no EventIdCollision failure
```
- [ ] **Step 2: run.** With the advance-model planner this PASSES immediately (the second run reads the bus, finds all three present, plans nothing). To prove non-vacuity, temporarily make `plan` ignore presence (always return all three emittable) → the second run errors on EventIdCollision (rc 1) → RED. Revert.
- [ ] **Step 3: run → PASS.**
- [ ] **Step 4: Commit** `test(threeway): overseer_plan idempotency pin [ADR-057]`.

---

## Chunk 2: activation coverage + docs + gates

### Task 5: bare-subprocess activation pin

**Files:** Modify `tests/unit/test_threeway_activation_scripts.py`.

- [ ] **Step 1:** add `overseer_plan.py` to the `_ACTIVATION_SCRIPTS` list (the existing parametrized `ModuleNotFoundError`-absent + `returncode==0` pin). NOTE: `overseer_plan.py` uses `add_subparsers`? **No** — it has only flags (`--decision` required). A bare `--help` exits 0 and prints help before the required-arg check, so the existing pin works as-is.
- [ ] **Step 2: run** the activation suite. Confirm non-vacuity by temporarily deleting the `sys.path` bootstrap from `overseer_plan.py` → `ModuleNotFoundError` in stderr → RED; restore.
Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_activation_scripts.py -q`
- [ ] **Step 3: Commit** `test(threeway): cover overseer_plan in the bare-subprocess pin [ADR-055/057]`.

### Task 6: ADR-057 + ARCHITECTURE + gates

**Files:** Modify `DECISIONS.md`, `ARCHITECTURE.md`.

- [ ] **Step 1:** Append **ADR-057** to `DECISIONS.md` (never edit prior entries): record DD-1 (advance model), DD-2 (JSON decision file), DD-3 (T0/T1 scope), DD-4 (`release_order` never auto-emitted), DD-5 (single signing path via `overseer_emit`), with the rationale from the spec.
- [ ] **Step 2:** Update `ARCHITECTURE.md` — add `overseer_plan.py` to the threeway script topology with a SAME-LINE `symbol (path:N)` anchor (the doc-checker only gates same-line anchors).
- [ ] **Step 3:** Run the acceptance gates and capture output:
```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
env -u GIT_INDEX_FILE .venv/bin/python scripts/check_no_ceremony.py
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/ -k threeway -q
```
Expected: ci_smoke OK; check_no_ceremony clean (no NEW ceremony); threeway suite green.
- [ ] **Step 4: Commit** `docs(threeway): ADR-057 + ARCHITECTURE for overseer_plan auto-decompose`.

---

## Full overseer_plan.py (write verbatim in Task 1, Step 3)

```python
#!/usr/bin/env python3
"""overseer_plan.py — auto-decompose one chief decision into the overseer facts emittable now.

Reads a JSON decision file (overseer-decision/1) + the live bus, computes which overseer facts
(brief/assignment/cycle_go) are ABSENT and therefore emittable, and — on --confirm — emits them by
REUSING scripts/overseer_emit.main (one signing path; ADR-057 DD-5). Dry-run by default. NEVER emits
release_order (the merge-authorization key stays a deliberate manual `overseer_emit` act; ADR-057 DD-4).
Surfaces every still-owed fact (release_order + the non-overseer candidate/attestation/ci_result) by owner.
"""
import argparse
import json
import sys
from pathlib import Path

# ADR-055: bare `python scripts/overseer_plan.py` puts scripts/ (not the repo root) on sys.path[0];
# put the repo root first so `import threeway` / `from scripts import overseer_emit` resolve.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts import overseer_emit
from threeway.gate import verify_and_reduce
from threeway.policy import default_policy
from threeway.refstore import RefEventStore

SCHEMA = "overseer-decision/1"
_TIERS_SUPPORTED = ("T0", "T1")
_ASSIGNMENT_FIELDS = ("pair", "builder", "builder_provider", "primary_verifier",
                      "primary_verifier_provider", "executing_coordinator")
# overseer facts overseer_plan may EMIT; release_order is deliberately excluded (DD-4).
_EMITTABLE = ("brief", "assignment", "cycle_go")


class DecisionError(ValueError):
    """Malformed or unsupported decision file (-> exit 2)."""


def load_decision(path) -> dict:
    """Read + validate the JSON decision. Raise DecisionError on any problem."""
    try:
        raw = json.loads(Path(path).read_text())
    except FileNotFoundError as e:
        raise DecisionError(f"decision file not found: {path}") from e
    except json.JSONDecodeError as e:
        raise DecisionError(f"decision file is not valid JSON: {e}") from e
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        got = raw.get("schema") if isinstance(raw, dict) else type(raw).__name__
        raise DecisionError(f"decision schema must be {SCHEMA!r}, got {got!r}")
    for f in ("candidate_id", "brief_id", "tier", "allowed_paths", "assignment"):
        if f not in raw:
            raise DecisionError(f"decision missing required field: {f!r}")
    if raw["tier"] not in _TIERS_SUPPORTED:
        raise DecisionError(f"tier {raw['tier']!r} unsupported — overseer_plan handles T0/T1 only "
                            "(T2/T3 approver_roster/re_verify_challenge are a documented fast-follow)")
    if not isinstance(raw["allowed_paths"], list) or not raw["allowed_paths"]:
        raise DecisionError("allowed_paths must be a non-empty list")
    asg = raw["assignment"]
    if not isinstance(asg, dict):
        raise DecisionError("assignment must be an object")
    for f in _ASSIGNMENT_FIELDS:
        if not asg.get(f):
            raise DecisionError(f"assignment missing required field: {f!r}")
    raw.setdefault("brief_version", 1)
    raw.setdefault("policy_digest", None)
    return raw


def _policy_digest(decision) -> str:
    return decision["policy_digest"] or default_policy().policy_digest()


def plan(decision, state):
    """Return (emittable, owed).
    emittable: absent overseer facts among (brief, assignment, cycle_go), canonical order.
    owed: [(fact, owner)] for everything else still missing (release_order + non-overseer facts)."""
    cid = decision["candidate_id"]
    bid = decision["brief_id"]
    ver = decision["brief_version"]
    pv = decision["assignment"]["primary_verifier"]
    pair = decision["assignment"]["pair"]

    emittable = []
    if state.brief(bid, ver) is None:
        emittable.append("brief")
    if state.assignment(pair) is None:
        emittable.append("assignment")
    if state.cycle_go(bid, ver) is None:
        emittable.append("cycle_go")

    owed = []
    cand = state.candidate(cid)
    if cand is None:
        owed.append(("candidate", "coordinator"))
    if state.effective_attestation(cid, "preliminary", pv) is None:
        owed.append(("attestation:preliminary", pv))
    if state.effective_attestation(cid, "release", pv) is None:
        owed.append(("attestation:release", pv))
    if cand is not None:
        integ = cand.payload.get("integration_sha")
        if integ and state.ci_result(integ) is None:
            owed.append(("ci_result", "ci"))
    if state.release_order(cid) is None:
        owed.append(("release_order", "overseer-manual"))  # DD-4: surfaced, NEVER emitted here
    return emittable, owed


def _emit_argv(fact, decision, repo_dir, remote, bus_id):
    cid = decision["candidate_id"]
    bid = decision["brief_id"]
    tier = decision["tier"]
    ver = decision["brief_version"]
    asg = decision["assignment"]
    tail = ["--repo-dir", repo_dir, "--remote", remote, "--bus-id", bus_id]
    if fact == "brief":
        return ["brief", "--candidate-id", cid, "--brief-id", bid, "--assigned-tier", tier,
                "--allowed-paths", *decision["allowed_paths"], *tail]
    if fact == "assignment":
        return ["assignment", "--candidate-id", cid, "--pair", asg["pair"],
                "--builder", asg["builder"], "--builder-provider", asg["builder_provider"],
                "--primary-verifier", asg["primary_verifier"],
                "--primary-verifier-provider", asg["primary_verifier_provider"],
                "--executing-coordinator", asg["executing_coordinator"], *tail]
    if fact == "cycle_go":
        return ["cycle_go", "--candidate-id", cid, "--brief-id", bid, "--brief-version", str(ver),
                "--tier", tier, "--policy-digest", _policy_digest(decision), *tail]
    raise ValueError(f"{fact!r} is not an overseer_plan-emittable fact")  # release_order never reaches here


def _read_state(repo_dir, registry_dir, remote, bus_id):
    store = RefEventStore(Path(repo_dir), remote=(remote or None))
    return verify_and_reduce(store.all_events(), registry_dir=registry_dir, bus_id=bus_id)


def _print_plan(emittable, owed, *, confirm):
    if emittable:
        print(f"{'EMITTING' if confirm else 'WOULD EMIT'} (overseer): {', '.join(emittable)}")
    else:
        print("Nothing to emit (all emittable overseer facts already present).")
    if owed:
        print("OWED (not overseer_plan's to emit):")
        for fact, owner in owed:
            print(f"  - {fact}  [{owner}]")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Auto-decompose a chief decision into the overseer facts emittable now.")
    ap.add_argument("--decision", required=True, help="path to an overseer-decision/1 JSON file")
    ap.add_argument("--repo-dir", default=".")
    ap.add_argument("--registry-dir", default="coordination/threeway/keys")
    ap.add_argument("--remote", default="origin", help='"" or "none" = local mode')
    ap.add_argument("--bus-id", default="prod")
    ap.add_argument("--confirm", action="store_true", help="actually emit (default: dry-run)")
    args = ap.parse_args(argv)

    try:
        decision = load_decision(args.decision)
    except DecisionError as e:
        print(f"Invalid decision: {e}", file=sys.stderr)
        return 2

    remote = None if (args.remote or "").lower() in ("", "none") else args.remote
    state = _read_state(args.repo_dir, args.registry_dir, remote, args.bus_id)
    emittable, owed = plan(decision, state)
    _print_plan(emittable, owed, confirm=args.confirm)

    if not args.confirm:
        return 0
    for fact in emittable:
        # Reuse overseer_emit (one signing path). Pass the RAW --remote so overseer_emit applies its own
        # ""/none -> None normalization; forward --bus-id so the write namespace == the read namespace.
        rc = overseer_emit.main(_emit_argv(fact, decision, args.repo_dir, args.remote, args.bus_id))
        if rc != 0:
            print(f"overseer_plan: emit of {fact!r} failed (rc {rc}); stopping.", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

---

## Acceptance criteria (verify before claiming done)

- [ ] `load_decision` accepts a valid `overseer-decision/1` file and raises `DecisionError` (→ rc 2) on a missing field or a T2/T3 tier.
- [ ] `plan` on an empty bus returns `["brief","assignment","cycle_go"]` emittable + owes `release_order` (overseer-manual) and the non-overseer facts; with `brief` present it returns only `["assignment","cycle_go"]` (idempotency).
- [ ] dry-run (default) leaves the bus byte-unchanged and prints the plan; `--confirm` emits the three overseer facts (authority-correct = `overseer`) and **never** `release_order` (mutation-tested RED).
- [ ] Re-running `--confirm` is a no-op (zero new events).
- [ ] `overseer_plan.py` is covered by the bare-subprocess activation pin (no `ModuleNotFoundError`; `--help` rc 0).
- [ ] ADR-057 + ARCHITECTURE updated; `ci_smoke` + `check_no_ceremony` clean; full threeway suite green.

## Post-implementation handoff

Per campaign discipline (impl≠verifier): the implementer's commits are `fixed`, NOT `verified`. Request an independent operator Lane-V pass (mutation-test: dry-run-no-emit, `--confirm` authority round-trip, the `release_order`-never-emitted Q4 guard, idempotency) before marking verified. Then the T3 extension or the hardening track per chief prioritization.
