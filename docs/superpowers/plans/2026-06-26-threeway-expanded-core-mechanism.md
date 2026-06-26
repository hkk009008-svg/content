# Threeway Expanded Core Mechanism Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the signed three-way bus a first-class Codex/core mechanism beyond the SP2 T1 path by adding T2/T3 principal-safe emitters, revocation/supersession CLIs, bus-first readiness output, protected-main guardrails, and command-cited docs.

**Execution status:** implemented on branch `antigravity-harness-adoption` in commits `a8cc4ca6`, `d07317c2`, `2bf2d7a6`, `e5151085`, `b59d721a`, `2561f887`, `10731de1`, and the Task 8 docs-sync commit. Final verification evidence is recorded in the spec and ADR-064.

**Architecture:** Reuse the existing append/sign/reduce path: `threeway.envelope.Event`, `threeway.refstore.RefEventStore.append`, and `threeway.gate.verify_and_reduce`. Add one small authority resolver module so `seat_emit.py`, the new `chief_emit.py`, and tests share the same dynamic authority decisions without importing private helpers from `threeway.tier`. Keep free-form `coordination/mailbox/sent/*.md` for human coordination while surfacing signed bus state as load-bearing protocol state.

**Tech Stack:** Python 3, pytest, Git refs, Ed25519 keys via `threeway.keys`, local hermetic temp repos, existing `scripts/*` CLI pattern, Markdown docs.

## Global Constraints

- Use `env -u GIT_INDEX_FILE` for ordinary git and pytest commands.
- Use TDD for every behavior change: write the failing test, run it red, implement, then run it green.
- Do not consume mailbox cursors, send mailbox events, claim locks, push, spend paid API budget, start pods, or merge protected `main`.
- Use `refs/threeway/test-main` for executable local walking skeletons.
- `refs/heads/main` must fail closed unless an explicit protected-main flag and deployment preflight pass.
- CLI authority or malformed requested action returns rc2, stderr, and zero new events.
- Missing key, git failure, append contention, malformed state, or unavailable bus returns rc1, stderr, and no traceback.
- Bus-unavailable readiness/status output must render a visible `(unavailable: ref-bus)` sentinel, never a silent `0`.
- No private keys are committed to the repo.
- Docs sync comes after executable behavior is pinned and cites verifying commands next to factual claims.

---

## File Structure

- Create `threeway/approval_authority.py`: public bus-state resolver for candidate context, mirror co-signer, re-verifier, challenge nonce, rostered approvers, and target-event ownership checks.
- Create `scripts/chief_emit.py`: principal-safe CLI for `human_approval` and chief self-revocation.
- Create `scripts/threeway_mechanism_ledger.py`: read-only verifier and renderer for load-bearing mechanism status.
- Create `docs/protocol/threeway/MECHANISM-LEDGER.md`: command-backed ledger generated from the verifier's row model.
- Create `tests/unit/test_threeway_mechanism_ledger.py`: ledger coverage and no-omitted-kind tests.
- Create `tests/unit/test_threeway_chief_emit.py`: chief approval and chief self-revocation CLI tests.
- Create `tests/unit/test_threeway_t2_t3_emitters_e2e.py`: CLI-driven T2/T3 happy paths and negative paths.
- Modify `threeway/keys_bootstrap.py`: make chief approver seat provisioning explicit through defaults or documented `--seats`.
- Modify `tests/unit/test_threeway_keys_bootstrap.py`: pin chief key provisioning.
- Modify `scripts/seat_emit.py`: add dynamic T2/T3 facts and self-revocation.
- Modify `tests/unit/test_threeway_seat_emit.py`: add red/green CLI tests for `co_sign`, `re_verify`, and self-revocation.
- Modify `scripts/overseer_emit.py`: add `brief_superseded` and overseer `attestation_revoked`.
- Modify `tests/unit/test_threeway_overseer_emit.py`: pin supersession and overseer revocation.
- Modify `scripts/continuation_readiness.py`: render a `Threeway Bus` section.
- Modify `.agents/skills/four-seat-protocol/scripts/seat_status.py`: show latest unread bus fact descriptors for migrated seats.
- Modify `scripts/mailbox_monitor.py`: label migrated seats as `ref-bus` and preserve descriptor output.
- Modify `tests/unit/test_continuation_readiness.py`, `tests/unit/test_mailbox_monitor.py`, and `tests/unit/test_bus_unread.py`: pin bus-first surfacing and unavailable sentinels.
- Modify `scripts/run_merge_gate.py`: add protected-main refusal and preflight boundary.
- Create or modify `tests/unit/test_threeway_run_merge_gate_protected_main.py`: pin accidental `refs/heads/main` refusal.
- Modify `docs/protocol/threeway/README.md`, `docs/protocol/threeway/ONBOARDING.md`, `docs/protocol/threeway/CODEX-ADOPTION.md`, `docs/protocol/threeway/UNIFIED-OPERATING-DOCTRINE.md`, `ARCHITECTURE.md`, and `DECISIONS.md` after tests are green.

---

### Task 1: Mechanism Ledger and Chief Key Provisioning

**Files:**
- Create: `docs/protocol/threeway/MECHANISM-LEDGER.md`
- Create: `scripts/threeway_mechanism_ledger.py`
- Create: `tests/unit/test_threeway_mechanism_ledger.py`
- Modify: `threeway/keys_bootstrap.py`
- Modify: `tests/unit/test_threeway_keys_bootstrap.py`

**Interfaces:**
- Consumes: `threeway.LOAD_BEARING_KINDS`.
- Produces: `MechanismRow(kind: str, status: str, emitters: tuple[str, ...], tests: tuple[str, ...], note: str)` and `collect_mechanisms() -> dict[str, MechanismRow]`.
- Produces: explicit chief seats in `keys_bootstrap.SEATS` or a documented and tested `--seats chief-gemini chief-chatgpt` path.

- [x] **Step 1: Write failing ledger tests**

Add this file:

```python
"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_mechanism_ledger.py -q"""

from threeway import LOAD_BEARING_KINDS
from scripts import threeway_mechanism_ledger as ledger


def test_ledger_covers_every_load_bearing_kind():
    rows = ledger.collect_mechanisms()
    assert set(rows) == set(LOAD_BEARING_KINDS)
    assert rows["co_sign"].status == "partial"
    assert rows["human_approval"].status == "partial"
    assert rows["brief"].status == "live"


def test_ledger_render_names_verifier_command_for_each_kind():
    rendered = ledger.render_markdown(ledger.collect_mechanisms())
    for kind in sorted(LOAD_BEARING_KINDS):
        assert f"| `{kind}` |" in rendered
    assert ".venv/bin/python scripts/threeway_mechanism_ledger.py --check" in rendered
```

- [x] **Step 2: Run the ledger test red**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_mechanism_ledger.py -q
```

Expected: FAIL with `ImportError` or `No module named 'scripts.threeway_mechanism_ledger'`.

- [x] **Step 3: Write failing chief key tests**

Extend `tests/unit/test_threeway_keys_bootstrap.py`:

```python
CHIEFS = {"chief-gemini", "chief-chatgpt"}


def test_chief_approver_keys_are_explicitly_provisioned_by_default():
    seats = set(keys_bootstrap.SEATS)
    assert CHIEFS.issubset(seats)


def test_bootstrap_writes_chief_keypairs(tmp_path):
    reg = tmp_path / "registry"
    ks = tmp_path / "keystore"
    rc = keys_bootstrap.main(["--registry", str(reg), "--keystore", str(ks)])
    assert rc == 0
    for seat in CHIEFS:
        assert (reg / f"{seat}.pub").exists()
        assert (ks / f"{seat}.ed25519").exists()
```

- [x] **Step 4: Run the chief key tests red**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_keys_bootstrap.py -q
```

Expected: FAIL because `chief-gemini` and `chief-chatgpt` are not yet in `keys_bootstrap.SEATS`.

- [x] **Step 5: Implement the ledger script**

Create `scripts/threeway_mechanism_ledger.py` with this shape:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from threeway import LOAD_BEARING_KINDS  # noqa: E402


@dataclass(frozen=True)
class MechanismRow:
    kind: str
    status: str
    emitters: tuple[str, ...]
    tests: tuple[str, ...]
    note: str


_ROWS = {
    "brief": MechanismRow("brief", "live", ("scripts/overseer_emit.py brief",), ("tests/unit/test_threeway_overseer_emit.py",), "overseer-authority fact"),
    "brief_superseded": MechanismRow("brief_superseded", "partial", ("threeway/reducer.py",), ("tests/unit/test_threeway_tier.py",), "reducer support exists; CLI added in this plan"),
    "candidate": MechanismRow("candidate", "live", ("scripts/seat_emit.py coordinator candidate", "scripts/seat_emit.py coordinator2 candidate"), ("tests/unit/test_threeway_seat_emit.py",), "interactive coordinator fact"),
    "candidate_aborted": MechanismRow("candidate_aborted", "live", ("scripts/seat_emit.py coordinator candidate_aborted", "scripts/seat_emit.py coordinator2 candidate_aborted"), ("tests/unit/test_threeway_seat_emit.py",), "interactive coordinator abort fact"),
    "assignment": MechanismRow("assignment", "live", ("scripts/overseer_emit.py assignment",), ("tests/unit/test_threeway_overseer_emit.py",), "overseer assignment"),
    "attestation": MechanismRow("attestation", "live", ("scripts/seat_emit.py operator attestation", "scripts/seat_emit.py operator2 attestation"), ("tests/unit/test_threeway_seat_emit.py",), "primary verifier attestation"),
    "attestation_revoked": MechanismRow("attestation_revoked", "partial", ("threeway/reducer.py",), ("tests/unit/test_threeway_tier.py",), "reducer support exists; CLI added in this plan"),
    "co_sign": MechanismRow("co_sign", "partial", ("threeway/tier.py",), ("tests/unit/test_threeway_tier.py",), "gate support exists; seat CLI added in this plan"),
    "re_verify": MechanismRow("re_verify", "partial", ("threeway/tier.py",), ("tests/unit/test_threeway_tier.py",), "gate support exists; seat CLI added in this plan"),
    "re_verify_challenge": MechanismRow("re_verify_challenge", "live", ("scripts/overseer_emit.py re_verify_challenge",), ("tests/unit/test_threeway_overseer_emit.py",), "overseer nonce challenge"),
    "cycle_go": MechanismRow("cycle_go", "live", ("scripts/overseer_emit.py cycle_go",), ("tests/unit/test_threeway_overseer_emit.py",), "overseer cycle authorization"),
    "release_requested": MechanismRow("release_requested", "live", ("scripts/seat_emit.py coordinator release_requested", "scripts/seat_emit.py coordinator2 release_requested"), ("tests/unit/test_threeway_seat_emit.py",), "interactive coordinator release request"),
    "release_order": MechanismRow("release_order", "live", ("scripts/overseer_emit.py release_order",), ("tests/unit/test_threeway_overseer_emit.py",), "manual overseer release order"),
    "human_approval": MechanismRow("human_approval", "partial", ("threeway/tier.py",), ("tests/unit/test_threeway_tier.py",), "gate support exists; chief CLI added in this plan"),
    "approver_roster": MechanismRow("approver_roster", "live", ("scripts/overseer_emit.py approver_roster",), ("tests/unit/test_threeway_overseer_emit.py",), "overseer roster"),
    "ci_result": MechanismRow("ci_result", "live", ("scripts/sign_ci_result.py",), ("tests/unit/test_threeway_e2e_walking_skeleton.py",), "CI attestor fact"),
    "merge_completed": MechanismRow("merge_completed", "live", ("threeway/gate.py run_gate",), ("tests/unit/test_threeway_e2e_walking_skeleton.py",), "merge-gate completion fact"),
}


def collect_mechanisms() -> dict[str, MechanismRow]:
    missing = set(LOAD_BEARING_KINDS) - set(_ROWS)
    extra = set(_ROWS) - set(LOAD_BEARING_KINDS)
    if missing or extra:
        raise AssertionError(f"ledger drift: missing={sorted(missing)} extra={sorted(extra)}")
    return dict(sorted(_ROWS.items()))


def render_markdown(rows: dict[str, MechanismRow]) -> str:
    lines = [
        "# Threeway Mechanism Ledger",
        "",
        "Generated and checked by:",
        "",
        "```bash",
        ".venv/bin/python scripts/threeway_mechanism_ledger.py --check",
        "```",
        "",
        "| Kind | Status | Runtime emitters / support | Tests | Note |",
        "|---|---|---|---|---|",
    ]
    for row in rows.values():
        emitters = "<br>".join(f"`{e}`" for e in row.emitters)
        tests = "<br>".join(f"`{t}`" for t in row.tests)
        lines.append(f"| `{row.kind}` | `{row.status}` | {emitters} | {tests} | {row.note} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render or check the threeway mechanism ledger.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    rows = collect_mechanisms()
    text = render_markdown(rows)
    if args.check:
        expected = _REPO_ROOT / "docs/protocol/threeway/MECHANISM-LEDGER.md"
        actual = expected.read_text(encoding="utf-8") if expected.exists() else ""
        if actual != text:
            print("MECHANISM-LEDGER.md is stale; rerender with this script", file=sys.stderr)
            return 1
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [x] **Step 6: Render the ledger document**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/threeway_mechanism_ledger.py > docs/protocol/threeway/MECHANISM-LEDGER.md
```

Expected: `docs/protocol/threeway/MECHANISM-LEDGER.md` contains one row per `LOAD_BEARING_KINDS` member.

- [x] **Step 7: Implement chief key provisioning**

Modify `threeway/keys_bootstrap.py`:

```python
SEATS = (
    "director", "operator", "coordinator",
    "director2", "operator2", "coordinator2",
    "overseer", "ci", "merge-gate",
    "chief-gemini", "chief-chatgpt",
)
```

- [x] **Step 8: Run Task 1 tests green**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_mechanism_ledger.py tests/unit/test_threeway_keys_bootstrap.py -q
```

Expected: PASS.

- [x] **Step 9: Commit Task 1**

Run:

```bash
env -u GIT_INDEX_FILE git add scripts/threeway_mechanism_ledger.py docs/protocol/threeway/MECHANISM-LEDGER.md tests/unit/test_threeway_mechanism_ledger.py threeway/keys_bootstrap.py tests/unit/test_threeway_keys_bootstrap.py
env -u GIT_INDEX_FILE git commit -m "docs(threeway): add mechanism ledger and chief key provisioning"
```

---

### Task 2: Seat Emit T2/T3 Operator Facts

**Files:**
- Create: `threeway/approval_authority.py`
- Modify: `scripts/seat_emit.py`
- Modify: `tests/unit/test_threeway_seat_emit.py`

**Interfaces:**
- Produces: `CandidateContext(candidate_id: str, integration_sha: str, pair: str, primary_verifier: str, primary_verifier_provider: str, builder_provider: str, brief_id: str | None, brief_version: int | None)`.
- Produces: `resolve_candidate_context(state, candidate_id: str) -> CandidateContext`.
- Produces: `required_mirror_cosigner(state, ctx: CandidateContext) -> str | None`.
- Produces: `required_re_verifier(state, ctx: CandidateContext) -> str | None`.
- Produces: `current_reverify_challenge_nonce(state, ctx: CandidateContext) -> str | None`.
- `scripts/seat_emit.py` adds facts: `co_sign`, `re_verify`, and `attestation_revoked`.

- [x] **Step 1: Write failing `seat_emit` tests**

Append these helpers and tests:

```python
def _prepare_t2_candidate(reg, r, base, branch):
    from scripts.overseer_emit import main as omain
    common = ["--repo-dir", str(r), "--remote", ""]
    assert omain(["assignment", "--candidate-id", "A:c1", "--pair", "A",
                  "--builder", "director", "--builder-provider", "codex",
                  "--primary-verifier", "operator", "--primary-verifier-provider", "claude",
                  "--executing-coordinator", "coordinator", *common]) == 0
    assert omain(["assignment", "--candidate-id", "A:c1", "--pair", "B",
                  "--builder", "director2", "--builder-provider", "claude",
                  "--primary-verifier", "operator2", "--primary-verifier-provider", "codex",
                  "--executing-coordinator", "coordinator2", *common]) == 0
    assert _run(["coordinator", "candidate", "--candidate-id", "c1", "--pair", "A",
                 "--staging-base", base, "--branch", branch, *common])[0] == 0
    state = verify_and_reduce(RefEventStore(r).all_events(), registry_dir=str(reg), bus_id="prod")
    integ = state.authoritative_candidate("A:c1").payload["integration_sha"]
    return common, integ


def test_t2_cosign_wrong_seat_is_rc2_zero_events(seatkit, live_repo):
    reg, ks = seatkit
    r, base, branch = live_repo
    common, integ = _prepare_t2_candidate(reg, r, base, branch)
    n0 = len(RefEventStore(r).all_events())
    rc, _, err = _run(["operator", "co_sign", "--candidate-id", "A:c1",
                       "--registry-dir", str(reg), *common])
    assert rc == 2
    assert "required co_sign seat is operator2" in err
    assert len(RefEventStore(r).all_events()) == n0
```

```python
def test_t2_cosign_round_trips_from_required_mirror_seat(seatkit, live_repo):
    reg, ks = seatkit
    r, base, branch = live_repo
    common, integ = _prepare_t2_candidate(reg, r, base, branch)
    rc, _, err = _run(["operator2", "co_sign", "--candidate-id", "A:c1",
                       "--registry-dir", str(reg), *common])
    assert rc == 0, err
    state = verify_and_reduce(RefEventStore(r).all_events(), registry_dir=str(reg), bus_id="prod")
    ev = state.co_sign("A:c1", "operator2")
    cand = state.authoritative_candidate("A:c1")
    assert ev is not None
    assert ev.payload["verdict"] == "GO"
    assert ev.subject_sha == cand.payload["integration_sha"]
```

Add re-verify tests:

```python
def _prepare_t3_challenge(reg, r, base, branch):
    from scripts.overseer_emit import main as omain
    common, integ = _prepare_t2_candidate(reg, r, base, branch)
    assert omain(["re_verify_challenge", "--candidate-id", "A:c1",
                  "--integration-sha", integ, *common]) == 0
    challenge = verify_and_reduce(
        RefEventStore(r).all_events(), registry_dir=str(reg), bus_id="prod"
    ).re_verify_challenge("A:c1")
    return common, challenge.payload["nonce"]


def test_reverify_echoes_challenge_nonce_not_unsigned_nonce(seatkit, live_repo):
    reg, ks = seatkit
    r, base, branch = live_repo
    common, nonce = _prepare_t3_challenge(reg, r, base, branch)
    rc, _, err = _run(["operator", "re_verify", "--candidate-id", "A:c1",
                       "--registry-dir", str(reg), *common])
    assert rc == 0, err
    state = verify_and_reduce(RefEventStore(r).all_events(), registry_dir=str(reg), bus_id="prod")
    ev = state.re_verify("A:c1", "operator")
    assert ev is not None
    assert ev.payload["challenge_nonce"] == nonce
    assert "nonce" not in ev.payload
```

```python
def test_reverify_without_challenge_is_rc2_zero_events(seatkit, live_repo):
    reg, ks = seatkit
    r, base, branch = live_repo
    common, integ = _prepare_t2_candidate(reg, r, base, branch)
    n0 = len(RefEventStore(r).all_events())
    rc, _, err = _run(["operator", "re_verify", "--candidate-id", "A:c1",
                       "--registry-dir", str(reg), *common])
    assert rc == 2
    assert "no current re_verify_challenge" in err
    assert len(RefEventStore(r).all_events()) == n0
```

Add self-revocation tests:

```python
def test_seat_can_revoke_own_prior_fact(seatkit, live_repo):
    reg, ks = seatkit
    r, base, branch = live_repo
    common = ["--candidate-id", "c1", "--pair", "A", "--staging-base", base, "--branch", branch,
              "--repo-dir", str(r), "--remote", ""]
    assert _run(["operator", "attestation", "--phase", "release", *common])[0] == 0
    target = [e for e in RefEventStore(r).all_events() if e.kind == "attestation"][-1]
    rc, _, err = _run(["operator", "attestation_revoked", "--candidate-id", "A:c1",
                       "--revokes-event-id", target.id, "--repo-dir", str(r), "--remote", ""])
    assert rc == 0, err
    state = verify_and_reduce(RefEventStore(r).all_events(), registry_dir=str(reg), bus_id="prod")
    assert state.effective_attestation("A:c1", "release", "operator") is None
```

```python
def test_seat_cannot_revoke_another_seats_fact(seatkit, live_repo):
    reg, ks = seatkit
    r, base, branch = live_repo
    common = ["--candidate-id", "c1", "--pair", "A", "--staging-base", base, "--branch", branch,
              "--repo-dir", str(r), "--remote", ""]
    assert _run(["operator", "attestation", "--phase", "release", *common])[0] == 0
    target = [e for e in RefEventStore(r).all_events() if e.kind == "attestation"][-1]
    n0 = len(RefEventStore(r).all_events())
    rc, _, err = _run(["operator2", "attestation_revoked", "--candidate-id", "A:c1",
                       "--revokes-event-id", target.id, "--repo-dir", str(r), "--remote", ""])
    assert rc == 2
    assert "may only revoke its own prior fact" in err
    assert len(RefEventStore(r).all_events()) == n0
```

- [x] **Step 2: Run the `seat_emit` tests red**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_seat_emit.py -q
```

Expected: FAIL because `co_sign`, `re_verify`, `attestation_revoked`, and `--registry-dir` are not implemented.

- [x] **Step 3: Add authority resolver module**

Create `threeway/approval_authority.py` with these public helpers:

```python
from __future__ import annotations

from dataclasses import dataclass


def signer_seat(signer: str) -> str:
    return signer.split(":", 1)[0]


@dataclass(frozen=True)
class CandidateContext:
    candidate_id: str
    integration_sha: str
    pair: str
    primary_verifier: str
    primary_verifier_provider: str
    builder_provider: str
    brief_id: str | None
    brief_version: int | None


def resolve_candidate_context(state, candidate_id: str) -> CandidateContext:
    candidate = state.authoritative_candidate(candidate_id)
    if candidate is None:
        raise ValueError(f"no authoritative candidate for {candidate_id}")
    pair = candidate.payload.get("pair")
    if not isinstance(pair, str):
        raise ValueError(f"candidate {candidate_id} has no string pair")
    assignment = state.assignment(pair)
    if assignment is None:
        raise ValueError(f"no assignment for pair {pair}")
    integration_sha = candidate.payload.get("integration_sha")
    if not isinstance(integration_sha, str) or not integration_sha:
        raise ValueError(f"candidate {candidate_id} has no integration_sha")
    primary_verifier = assignment.payload.get("primary_verifier")
    primary_provider = assignment.payload.get("primary_verifier_provider")
    builder_provider = assignment.payload.get("builder_provider")
    if not all(isinstance(x, str) and x for x in (primary_verifier, primary_provider, builder_provider)):
        raise ValueError(f"assignment for pair {pair} is missing verifier/provider fields")
    return CandidateContext(
        candidate_id=candidate_id,
        integration_sha=integration_sha,
        pair=pair,
        primary_verifier=primary_verifier,
        primary_verifier_provider=primary_provider,
        builder_provider=builder_provider,
        brief_id=candidate.brief_id,
        brief_version=candidate.brief_version,
    )


def required_mirror_cosigner(state, ctx: CandidateContext) -> str | None:
    seats = []
    for assignment in state.assignments():
        if signer_seat(assignment.signer) != "overseer":
            continue
        payload = assignment.payload
        if payload.get("pair") == ctx.pair:
            continue
        if (payload.get("builder_provider") == ctx.primary_verifier_provider
                and payload.get("primary_verifier_provider") == ctx.builder_provider):
            seats.append(payload.get("primary_verifier"))
    if len(seats) != 1:
        return None
    return seats[0] if isinstance(seats[0], str) and seats[0] else None


def required_re_verifier(state, ctx: CandidateContext) -> str:
    return ctx.primary_verifier


def current_reverify_challenge_nonce(state, ctx: CandidateContext) -> str | None:
    challenge = state.re_verify_challenge(ctx.candidate_id)
    if challenge is None or challenge.subject_sha != ctx.integration_sha:
        return None
    nonce = challenge.payload.get("nonce")
    return nonce if isinstance(nonce, str) and nonce else None


def event_by_id(events, event_id: str):
    matches = [ev for ev in events if ev.id == event_id]
    if len(matches) != 1:
        return None
    return matches[0]
```

- [x] **Step 4: Extend `seat_emit.py` arguments and authority checks**

Add imports:

```python
from threeway.approval_authority import (
    current_reverify_challenge_nonce,
    event_by_id,
    required_mirror_cosigner,
    required_re_verifier,
    resolve_candidate_context,
    signer_seat,
)
from threeway.gate import verify_and_reduce
```

Add CLI args:

```python
ap.add_argument("--registry-dir", default="coordination/threeway/keys")
ap.add_argument("--verdict", default="GO", choices=["GO", "NITS", "FAIL"])
ap.add_argument("--revokes-event-id", default=None)
```

Expand `AUTHORITY`:

```python
AUTHORITY = {
    "coordinator":  {"candidate", "release_requested", "candidate_aborted", "attestation_revoked"},
    "coordinator2": {"candidate", "release_requested", "candidate_aborted", "attestation_revoked"},
    "operator":     {"attestation", "co_sign", "re_verify", "attestation_revoked"},
    "operator2":    {"attestation", "co_sign", "re_verify", "attestation_revoked"},
    "director":     {"attestation_revoked"},
    "director2":    {"attestation_revoked"},
}
```

Before the existing staging-base check, branch by fact:

```python
if a.fact in {"co_sign", "re_verify"}:
    if ":" not in a.candidate_id:
        print(f"{a.fact} requires pair-namespaced --candidate-id", file=sys.stderr)
        return 2
elif a.fact == "attestation_revoked":
    if not a.revokes_event_id:
        print("attestation_revoked requires --revokes-event-id", file=sys.stderr)
        return 2
elif a.fact != "candidate_aborted" and (a.staging_base is None or a.branch is None):
    print(f"{a.fact} requires --staging-base and --branch", file=sys.stderr)
    return 2
```

- [x] **Step 5: Implement T2/T3 event builders**

Add helper functions in `seat_emit.py`:

```python
def _state_and_events(a):
    store = RefEventStore(Path(a.repo_dir), remote=(a.remote or None))
    events = store.all_events()
    state = verify_and_reduce(events, registry_dir=a.registry_dir, bus_id=a.bus_id)
    return store, events, state


def _dynamic_event(a) -> Event:
    store, events, state = _state_and_events(a)
    ctx = resolve_candidate_context(state, a.candidate_id)
    if a.fact == "co_sign":
        required = required_mirror_cosigner(state, ctx)
        if required != a.seat:
            raise PermissionError(f"required co_sign seat is {required or '(none)'}, not {a.seat}")
        return Event(
            id=f"co_sign-{a.seat}-{ctx.candidate_id}", seq=0, bus_id=a.bus_id,
            schema_version="threeway/1", kind="co_sign", sender=a.seat, recipient="all",
            signer=f"{a.seat}:{PROVIDER[a.seat]}:{a.session}", payload={"verdict": a.verdict},
            brief_id=ctx.brief_id, brief_version=ctx.brief_version,
            candidate_id=ctx.candidate_id, subject_sha=ctx.integration_sha,
        )
    if a.fact == "re_verify":
        required = required_re_verifier(state, ctx)
        if required != a.seat:
            raise PermissionError(f"required re_verify seat is {required}, not {a.seat}")
        nonce = current_reverify_challenge_nonce(state, ctx)
        if nonce is None:
            raise PermissionError("no current re_verify_challenge for candidate integration_sha")
        return Event(
            id=f"re_verify-{a.seat}-{ctx.candidate_id}", seq=0, bus_id=a.bus_id,
            schema_version="threeway/1", kind="re_verify", sender=a.seat, recipient="all",
            signer=f"{a.seat}:{PROVIDER[a.seat]}:{a.session}",
            payload={"verdict": a.verdict, "challenge_nonce": nonce},
            brief_id=ctx.brief_id, brief_version=ctx.brief_version,
            candidate_id=ctx.candidate_id, subject_sha=ctx.integration_sha,
        )
    if a.fact == "attestation_revoked":
        target = event_by_id(events, a.revokes_event_id)
        if target is None or signer_seat(target.signer) != a.seat:
            raise PermissionError("seat may only revoke its own prior fact")
        return Event(
            id=f"attestation_revoked-{a.seat}-{a.revokes_event_id}", seq=0, bus_id=a.bus_id,
            schema_version="threeway/1", kind="attestation_revoked", sender=a.seat,
            recipient="all", signer=f"{a.seat}:{PROVIDER.get(a.seat, 'seat')}:{a.session}",
            payload={}, brief_id=target.brief_id, brief_version=target.brief_version,
            candidate_id=target.candidate_id, revokes_event_id=a.revokes_event_id,
        )
    raise ValueError(f"unsupported dynamic fact {a.fact}")
```

Call this before `_build_event(a)`:

```python
try:
    if a.fact in {"co_sign", "re_verify", "attestation_revoked"}:
        ev = _dynamic_event(a)
    else:
        ev = _build_event(a)
    store = RefEventStore(Path(a.repo_dir), remote=(a.remote or None))
    store.append(ev, load_private(a.seat))
except PermissionError as e:
    print(str(e), file=sys.stderr); return 2
```

- [x] **Step 6: Run Task 2 tests green**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_seat_emit.py tests/unit/test_threeway_tier.py -q
```

Expected: PASS.

- [x] **Step 7: Commit Task 2**

Run:

```bash
env -u GIT_INDEX_FILE git add threeway/approval_authority.py scripts/seat_emit.py tests/unit/test_threeway_seat_emit.py
env -u GIT_INDEX_FILE git commit -m "feat(threeway): add seat T2 T3 signed bus emitters"
```

---

### Task 3: Chief Emit Human Approval CLI

**Files:**
- Create: `scripts/chief_emit.py`
- Create: `tests/unit/test_threeway_chief_emit.py`
- Modify: `threeway/approval_authority.py`

**Interfaces:**
- Produces CLI: `scripts/chief_emit.py <approver-seat> human_approval --candidate-id A:c1 --registry-dir <dir> --repo-dir <repo> --remote ""`.
- Produces CLI: `scripts/chief_emit.py <approver-seat> attestation_revoked --revokes-event-id <event-id> ...`.
- Uses `load_private(<approver-seat>)`; never uses the overseer key.

- [x] **Step 1: Write failing chief CLI tests**

Create `tests/unit/test_threeway_chief_emit.py`:

```python
"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_chief_emit.py -q"""

import contextlib
import io

import pytest

from threeway.gate import verify_and_reduce
from threeway.refstore import RefEventStore
from tests.unit.test_threeway_overseer_emit import _new_repo, seatkit


def _run(argv):
    from scripts.chief_emit import main
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()


def test_rostered_chief_human_approval_round_trips(seatkit, tmp_path):
    reg, ks, privs = seatkit
    repo = _new_repo(tmp_path)
    from scripts.overseer_emit import main as omain
    common = ["--candidate-id", "A:c1", "--repo-dir", str(repo), "--remote", ""]
    assert omain(["approver_roster", "--approvers", "chief-gemini", "chief-chatgpt", *common]) == 0
    rc, _, err = _run(["chief-gemini", "human_approval", "--candidate-id", "A:c1",
                       "--integration-sha", "1" * 40, "--registry-dir", str(reg),
                       "--repo-dir", str(repo), "--remote", ""])
    assert rc == 0, err
    state = verify_and_reduce(RefEventStore(repo).all_events(), registry_dir=str(reg), bus_id="prod")
    approvals = state.human_approvals("A:c1")
    assert len(approvals) == 1
    assert approvals[0].signer.split(":", 1)[0] == "chief-gemini"
    assert approvals[0].payload["decision"] == "approve"


def test_unrostered_chief_is_rc2_zero_events(seatkit, tmp_path):
    reg, ks, privs = seatkit
    repo = _new_repo(tmp_path)
    from scripts.overseer_emit import main as omain
    assert omain(["approver_roster", "--candidate-id", "A:c1",
                  "--approvers", "chief-chatgpt", "--repo-dir", str(repo), "--remote", ""]) == 0
    n0 = len(RefEventStore(repo).all_events())
    rc, _, err = _run(["chief-gemini", "human_approval", "--candidate-id", "A:c1",
                       "--integration-sha", "1" * 40, "--registry-dir", str(reg),
                       "--repo-dir", str(repo), "--remote", ""])
    assert rc == 2
    assert "not rostered" in err
    assert len(RefEventStore(repo).all_events()) == n0


def test_chief_can_revoke_own_approval(seatkit, tmp_path):
    reg, ks, privs = seatkit
    repo = _new_repo(tmp_path)
    from scripts.overseer_emit import main as omain
    assert omain(["approver_roster", "--candidate-id", "A:c1",
                  "--approvers", "chief-gemini", "chief-chatgpt",
                  "--repo-dir", str(repo), "--remote", ""]) == 0
    assert _run(["chief-gemini", "human_approval", "--candidate-id", "A:c1",
                 "--integration-sha", "1" * 40, "--registry-dir", str(reg),
                 "--repo-dir", str(repo), "--remote", ""])[0] == 0
    target = [e for e in RefEventStore(repo).all_events() if e.kind == "human_approval"][-1]
    rc, _, err = _run(["chief-gemini", "attestation_revoked", "--candidate-id", "A:c1",
                       "--revokes-event-id", target.id, "--registry-dir", str(reg),
                       "--repo-dir", str(repo), "--remote", ""])
    assert rc == 0, err
    state = verify_and_reduce(RefEventStore(repo).all_events(), registry_dir=str(reg), bus_id="prod")
    assert state.human_approvals("A:c1") == []
```

- [x] **Step 2: Run chief tests red**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_chief_emit.py -q
```

Expected: FAIL because `scripts.chief_emit` does not exist.

- [x] **Step 3: Add roster helper**

Add to `threeway/approval_authority.py`:

```python
def rostered_approvers(state, candidate_id: str) -> set[str]:
    roster = state.approver_roster(candidate_id)
    if roster is None:
        return set()
    approvers = roster.payload.get("approvers")
    if not isinstance(approvers, list):
        return set()
    return {seat for seat in approvers if isinstance(seat, str)}
```

- [x] **Step 4: Implement `chief_emit.py`**

Create `scripts/chief_emit.py` with this shape:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from threeway.approval_authority import event_by_id, rostered_approvers, signer_seat  # noqa: E402
from threeway.envelope import Event  # noqa: E402
from threeway.gate import verify_and_reduce  # noqa: E402
from threeway.keys import PublicKeyRegistry, load_private  # noqa: E402
from threeway.refstore import AppendContentionExceeded, RefEventStore  # noqa: E402


def _state_events_store(args):
    store = RefEventStore(Path(args.repo_dir), remote=(args.remote or None))
    events = store.all_events()
    state = verify_and_reduce(events, registry_dir=args.registry_dir, bus_id=args.bus_id)
    return state, events, store


def _build_human_approval(args):
    state, events, store = _state_events_store(args)
    try:
        PublicKeyRegistry(args.registry_dir).get(args.approver)
    except KeyError:
        raise PermissionError(f"approver {args.approver} has no public registry key")
    if args.approver not in rostered_approvers(state, args.candidate_id):
        raise PermissionError(f"approver {args.approver} is not rostered for {args.candidate_id}")
    return Event(
        id=f"human_approval-{args.approver}-{args.candidate_id}", seq=0, bus_id=args.bus_id,
        schema_version="threeway/1", kind="human_approval", sender=args.approver,
        recipient="all", signer=f"{args.approver}:human:cli",
        payload={"approver_identity": args.approver, "integration_sha": args.integration_sha,
                 "decision": args.decision},
        candidate_id=args.candidate_id, subject_sha=args.integration_sha,
    )


def _build_revoke(args):
    state, events, store = _state_events_store(args)
    target = event_by_id(events, args.revokes_event_id)
    if target is None or signer_seat(target.signer) != args.approver:
        raise PermissionError("chief may only revoke its own prior fact")
    return Event(
        id=f"attestation_revoked-{args.approver}-{args.revokes_event_id}", seq=0,
        bus_id=args.bus_id, schema_version="threeway/1", kind="attestation_revoked",
        sender=args.approver, recipient="all", signer=f"{args.approver}:human:cli",
        payload={}, candidate_id=target.candidate_id, subject_sha=target.subject_sha,
        revokes_event_id=args.revokes_event_id,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Chief approver threeway signing CLI.")
    parser.add_argument("approver")
    parser.add_argument("fact", choices=["human_approval", "attestation_revoked"])
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--integration-sha")
    parser.add_argument("--decision", default="approve", choices=["approve"])
    parser.add_argument("--revokes-event-id")
    parser.add_argument("--registry-dir", default="coordination/threeway/keys")
    parser.add_argument("--repo-dir", default=".")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--bus-id", default="prod")
    args = parser.parse_args(argv)
    if (args.remote or "").lower() in ("", "none"):
        args.remote = None
    if args.fact == "human_approval" and not args.integration_sha:
        print("human_approval requires --integration-sha", file=sys.stderr)
        return 2
    if args.fact == "attestation_revoked" and not args.revokes_event_id:
        print("attestation_revoked requires --revokes-event-id", file=sys.stderr)
        return 2
    try:
        ev = _build_human_approval(args) if args.fact == "human_approval" else _build_revoke(args)
        RefEventStore(Path(args.repo_dir), remote=(args.remote or None)).append(ev, load_private(args.approver))
    except PermissionError as exc:
        print(str(exc), file=sys.stderr); return 2
    except FileNotFoundError as exc:
        print(f"Error loading chief key: {exc}", file=sys.stderr); return 1
    except AppendContentionExceeded as exc:
        print(f"Bus contention, not emitted: {exc}", file=sys.stderr); return 1
    except ValueError as exc:
        print(f"Not emitted: {exc}", file=sys.stderr); return 1
    print(f"Emitted {ev.kind} for {ev.candidate_id} (seq {ev.seq}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [x] **Step 5: Run Task 3 tests green**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_chief_emit.py tests/unit/test_threeway_tier.py -q
```

Expected: PASS.

- [x] **Step 6: Commit Task 3**

Run:

```bash
env -u GIT_INDEX_FILE git add scripts/chief_emit.py tests/unit/test_threeway_chief_emit.py threeway/approval_authority.py
env -u GIT_INDEX_FILE git commit -m "feat(threeway): add chief human approval emitter"
```

---

### Task 4: Overseer Supersession and Revocation CLI

**Files:**
- Modify: `scripts/overseer_emit.py`
- Modify: `tests/unit/test_threeway_overseer_emit.py`

**Interfaces:**
- Produces CLI: `scripts/overseer_emit.py brief_superseded --candidate-id A:c1 --supersedes-event-id <brief-event-id> ...`.
- Produces CLI: `scripts/overseer_emit.py attestation_revoked --candidate-id A:c1 --revokes-event-id <event-id> ...`.
- Keeps `release_order` manual and does not change `scripts/overseer_plan.py` merge authority.

- [x] **Step 1: Write failing overseer tests**

Append:

```python
def test_brief_superseded_marks_prior_brief_version_inactive(seatkit, tmp_path):
    reg, ks, privs = seatkit
    repo = _new_repo(tmp_path)
    from scripts.overseer_emit import main
    assert main(["brief", "--candidate-id", "A:c1", "--brief-id", "b1",
                 "--brief-version", "1", "--assigned-tier", "T1",
                 "--allowed-paths", "cinema/", "--repo-dir", str(repo), "--remote", ""]) == 0
    target = [e for e in _events(repo) if e.kind == "brief"][-1]
    rc = main(["brief_superseded", "--candidate-id", "A:c1",
               "--supersedes-event-id", target.id, "--repo-dir", str(repo), "--remote", ""])
    assert rc == 0
    state = verify_and_reduce(_events(repo), registry_dir=str(reg), bus_id="prod")
    assert state.latest_brief_version("b1") is None
```

```python
def test_overseer_can_revoke_load_bearing_fact(seatkit, tmp_path):
    reg, ks, privs = seatkit
    repo = _new_repo(tmp_path)
    from scripts.overseer_emit import main
    assert main(["approver_roster", "--candidate-id", "A:c1",
                 "--approvers", "chief-gemini", "chief-chatgpt",
                 "--repo-dir", str(repo), "--remote", ""]) == 0
    target = [e for e in _events(repo) if e.kind == "approver_roster"][-1]
    assert main(["attestation_revoked", "--candidate-id", "A:c1",
                 "--revokes-event-id", target.id,
                 "--repo-dir", str(repo), "--remote", ""]) == 0
    state = verify_and_reduce(_events(repo), registry_dir=str(reg), bus_id="prod")
    assert state.approver_roster("A:c1") is None
```

- [x] **Step 2: Run overseer tests red**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_overseer_emit.py -q
```

Expected: FAIL because `brief_superseded` and overseer `attestation_revoked` subcommands are missing.

- [x] **Step 3: Implement overseer event builders**

Add:

```python
def _events(repo_dir, remote):
    return RefEventStore(Path(repo_dir), remote=(remote or None)).all_events()


def _find_event(a, event_id):
    matches = [ev for ev in _events(a.repo_dir, a.remote) if ev.id == event_id]
    if len(matches) != 1:
        raise ValueError(f"target event id not found or ambiguous: {event_id}")
    return matches[0]


def _cmd_brief_superseded(a) -> Event:
    target = _find_event(a, a.supersedes_event_id)
    if target.kind != "brief":
        raise ValueError("brief_superseded target must be a brief")
    return _build_event(
        "brief_superseded",
        {"supersedes_event_id": a.supersedes_event_id},
        a.candidate_id,
        brief_id=target.brief_id,
        brief_version=target.brief_version,
        bus_id=a.bus_id,
        ev_id=f"brief_superseded-overseer-{a.supersedes_event_id}",
    )


def _cmd_attestation_revoked(a) -> Event:
    target = _find_event(a, a.revokes_event_id)
    return _build_event(
        "attestation_revoked",
        {},
        a.candidate_id,
        brief_id=target.brief_id,
        brief_version=target.brief_version,
        subject_sha=target.subject_sha,
        bus_id=a.bus_id,
        ev_id=f"attestation_revoked-overseer-{a.revokes_event_id}",
    )
```

Set the top-level fields before emitting:

```python
ev = args.fn(args)
if args.cmd == "brief_superseded":
    ev.supersedes_event_id = args.supersedes_event_id
if args.cmd == "attestation_revoked":
    ev.revokes_event_id = args.revokes_event_id
ev = _emit(args.repo_dir, args.remote, ev)
```

Add subparsers:

```python
ps = sub.add_parser("brief_superseded"); _common(ps)
ps.add_argument("--supersedes-event-id", required=True)
ps.set_defaults(fn=_cmd_brief_superseded)

pv2 = sub.add_parser("attestation_revoked"); _common(pv2)
pv2.add_argument("--revokes-event-id", required=True)
pv2.set_defaults(fn=_cmd_attestation_revoked)
```

- [x] **Step 4: Run Task 4 tests green**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_overseer_emit.py tests/unit/test_threeway_tier.py -q
```

Expected: PASS.

- [x] **Step 5: Commit Task 4**

Run:

```bash
env -u GIT_INDEX_FILE git add scripts/overseer_emit.py tests/unit/test_threeway_overseer_emit.py
env -u GIT_INDEX_FILE git commit -m "feat(threeway): add overseer revocation and supersession emitters"
```

---

### Task 5: T2/T3 Walking Skeletons and Negative Paths

**Files:**
- Create: `tests/unit/test_threeway_t2_t3_emitters_e2e.py`
- Modify: `tests/unit/test_threeway_e2e_walking_skeleton.py` only if shared helpers are extracted inside the test file.

**Interfaces:**
- Consumes: `scripts/overseer_emit.py`, `scripts/seat_emit.py`, `scripts/chief_emit.py`, `scripts/sign_ci_result.py`, and `scripts/run_merge_gate.py`.
- Produces: full CLI-driven T2 and T3 flows against `refs/threeway/test-main`.

- [x] **Step 1: Write failing T2/T3 E2E test file**

Create a new file copied from the existing walking skeleton helper style. Add helper functions with these exact responsibilities:

```python
def _emit_t2_base(reg, ks, repo, base, branch, *, emit_cosign: bool):
    cid = "A:c1"
    pd = default_policy().policy_digest()
    tree, clean = gitcas.merge_tree(repo, base, branch)
    assert clean
    integ = gitcas.commit_tree(repo, tree, [base, branch], f"threeway merge {cid}")
    L = ["--repo-dir", str(repo), "--remote", ""]
    B = ["--candidate-id", cid, "--pair", "A", "--staging-base", base, "--branch", branch, *L]
    _run("overseer_emit.py", "brief", "--candidate-id", cid, "--brief-id", "b1",
         "--assigned-tier", "T2", "--allowed-paths", "cinema/", *L, repo=repo, ks=ks)
    _run("overseer_emit.py", "assignment", "--candidate-id", cid, "--pair", "A",
         "--builder", "director", "--builder-provider", "codex",
         "--primary-verifier", "operator", "--primary-verifier-provider", "claude",
         "--executing-coordinator", "coordinator", *L, repo=repo, ks=ks)
    _run("overseer_emit.py", "assignment", "--candidate-id", cid, "--pair", "B",
         "--builder", "director2", "--builder-provider", "claude",
         "--primary-verifier", "operator2", "--primary-verifier-provider", "codex",
         "--executing-coordinator", "coordinator2", *L, repo=repo, ks=ks)
    _run("overseer_emit.py", "cycle_go", "--candidate-id", cid, "--brief-id", "b1",
         "--tier", "T2", "--policy-digest", pd, *L, repo=repo, ks=ks)
    _run("seat_emit.py", "coordinator", "candidate", *B, repo=repo, ks=ks)
    _run("seat_emit.py", "operator", "attestation", "--phase", "preliminary", *B, repo=repo, ks=ks)
    _run("sign_ci_result.py", "--integration-sha", integ, "--result", "PASS",
         "--repo-dir", str(repo), repo=repo, ks=ks)
    _run("seat_emit.py", "operator", "attestation", "--phase", "release", *B, repo=repo, ks=ks)
    if emit_cosign:
        _run("seat_emit.py", "operator2", "co_sign", "--candidate-id", cid,
             "--registry-dir", str(reg), *L, repo=repo, ks=ks)
    _run("seat_emit.py", "coordinator", "release_requested", *B, repo=repo, ks=ks)
    _run("overseer_emit.py", "release_order", "--candidate-id", cid,
         "--integration-sha", integ, *L, repo=repo, ks=ks)
    return cid, integ
```

Add these tests:

```python
def test_t2_cli_happy_path_merges_with_mirror_cosign(seatkit, live_repo):
    reg, ks, privs = seatkit
    repo, base, branch = live_repo
    cid, integ = _emit_t2_base(reg, ks, repo, base, branch, emit_cosign=True)
    _run("run_merge_gate.py", "--repo-dir", str(repo), "--registry-dir", str(reg),
         "--bus-id", "prod", "--main-ref", "refs/threeway/test-main", "--run-once",
         repo=repo, ks=ks)
    assert _git(repo, "rev-parse", "refs/threeway/test-main").stdout.strip() == integ
    state = verify_and_reduce(RefEventStore(repo).all_events(), registry_dir=str(reg), bus_id="prod")
    assert state.merge_completed(cid) is not None
```

```python
def test_t2_missing_cosign_stays_pending(seatkit, live_repo):
    reg, ks, privs = seatkit
    repo, base, branch = live_repo
    cid, integ = _emit_t2_base(reg, ks, repo, base, branch, emit_cosign=False)
    _run("run_merge_gate.py", "--repo-dir", str(repo), "--registry-dir", str(reg),
         "--bus-id", "prod", "--main-ref", "refs/threeway/test-main", "--run-once",
         repo=repo, ks=ks)
    state = verify_and_reduce(RefEventStore(repo).all_events(), registry_dir=str(reg), bus_id="prod")
    assert state.merge_completed(cid) is None
    assert _git(repo, "rev-parse", "refs/threeway/test-main").stdout.strip() == base
```

```python
def test_t2_forged_wrong_seat_cosign_does_not_satisfy_gate(seatkit, live_repo):
    reg, ks, privs = seatkit
    repo, base, branch = live_repo
    cid, integ = _emit_t2_base(reg, ks, repo, base, branch, emit_cosign=False)
    bad = Event(id="co_sign-operator-forged", seq=0, bus_id="prod", schema_version="threeway/1",
                kind="co_sign", sender="operator", recipient="all",
                signer="operator:claude:forged", payload={"verdict": "GO"},
                candidate_id=cid, subject_sha=integ, brief_id="b1", brief_version=1)
    RefEventStore(repo).append(bad, keys.load_private("operator"))
    _run("run_merge_gate.py", "--repo-dir", str(repo), "--registry-dir", str(reg),
         "--bus-id", "prod", "--main-ref", "refs/threeway/test-main", "--run-once",
         repo=repo, ks=ks)
    state = verify_and_reduce(RefEventStore(repo).all_events(), registry_dir=str(reg), bus_id="prod")
    assert state.merge_completed(cid) is None
    assert _git(repo, "rev-parse", "refs/threeway/test-main").stdout.strip() == base
```

```python
def _emit_t3_extras(reg, ks, repo, cid, integ, *, approvals=("chief-gemini", "chief-chatgpt")):
    L = ["--repo-dir", str(repo), "--remote", ""]
    _run("overseer_emit.py", "approver_roster", "--candidate-id", cid,
         "--approvers", "chief-gemini", "chief-chatgpt", *L, repo=repo, ks=ks)
    _run("overseer_emit.py", "re_verify_challenge", "--candidate-id", cid,
         "--integration-sha", integ, "--nonce", "fresh-nonce", *L, repo=repo, ks=ks)
    _run("seat_emit.py", "operator", "re_verify", "--candidate-id", cid,
         "--registry-dir", str(reg), *L, repo=repo, ks=ks)
    for approver in approvals:
        _run("chief_emit.py", approver, "human_approval", "--candidate-id", cid,
             "--integration-sha", integ, "--registry-dir", str(reg), *L, repo=repo, ks=ks)
```

```python
def test_t3_cli_happy_path_merges_with_reverify_and_two_chiefs(seatkit, live_repo):
    reg, ks, privs = seatkit
    repo, base, branch = live_repo
    cid, integ = _emit_t2_base(reg, ks, repo, base, branch, emit_cosign=True)
    _emit_t3_extras(reg, ks, repo, cid, integ)
    _run("run_merge_gate.py", "--repo-dir", str(repo), "--registry-dir", str(reg),
         "--bus-id", "prod", "--main-ref", "refs/threeway/test-main", "--run-once",
         repo=repo, ks=ks)
    state = verify_and_reduce(RefEventStore(repo).all_events(), registry_dir=str(reg), bus_id="prod")
    assert state.merge_completed(cid) is not None
```

```python
def test_t3_one_human_approval_stays_pending(seatkit, live_repo):
    reg, ks, privs = seatkit
    repo, base, branch = live_repo
    cid, integ = _emit_t2_base(reg, ks, repo, base, branch, emit_cosign=True)
    _emit_t3_extras(reg, ks, repo, cid, integ, approvals=("chief-gemini",))
    _run("run_merge_gate.py", "--repo-dir", str(repo), "--registry-dir", str(reg),
         "--bus-id", "prod", "--main-ref", "refs/threeway/test-main", "--run-once",
         repo=repo, ks=ks)
    state = verify_and_reduce(RefEventStore(repo).all_events(), registry_dir=str(reg), bus_id="prod")
    assert state.merge_completed(cid) is None
    assert _git(repo, "rev-parse", "refs/threeway/test-main").stdout.strip() == base
```

```python
def test_t3_revoking_cosign_makes_unmerged_candidate_pending(seatkit, live_repo):
    reg, ks, privs = seatkit
    repo, base, branch = live_repo
    cid, integ = _emit_t2_base(reg, ks, repo, base, branch, emit_cosign=True)
    target = [e for e in RefEventStore(repo).all_events() if e.kind == "co_sign"][-1]
    _run("seat_emit.py", "operator2", "attestation_revoked", "--candidate-id", cid,
         "--revokes-event-id", target.id, "--repo-dir", str(repo), "--remote", "",
         repo=repo, ks=ks)
    _emit_t3_extras(reg, ks, repo, cid, integ)
    _run("run_merge_gate.py", "--repo-dir", str(repo), "--registry-dir", str(reg),
         "--bus-id", "prod", "--main-ref", "refs/threeway/test-main", "--run-once",
         repo=repo, ks=ks)
    state = verify_and_reduce(RefEventStore(repo).all_events(), registry_dir=str(reg), bus_id="prod")
    assert state.merge_completed(cid) is None
    assert _git(repo, "rev-parse", "refs/threeway/test-main").stdout.strip() == base
```

Use the subprocess `_run` helper from `tests/unit/test_threeway_e2e_walking_skeleton.py`; do not call cloud APIs.

- [x] **Step 2: Run the E2E tests red**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_t2_t3_emitters_e2e.py -q
```

Expected: FAIL on the first missing CLI behavior in the T2/T3 path.

- [x] **Step 3: Implement only the minimal fixes surfaced by the E2E tests**

Adjust only the earlier CLI implementations when a red test identifies a concrete mismatch. Permitted fixes include:

```python
# If seat_emit stores bare "c1" for a dynamic fact, normalize to the authoritative candidate id:
candidate_id = a.candidate_id if ":" in a.candidate_id else f"{SEAT_PAIR[a.seat].pair}:{a.candidate_id}"
```

```python
# If chief_emit permits a second approval with the same deterministic id, keep idempotence:
id=f"human_approval-{args.approver}-{args.candidate_id}-{args.integration_sha}"
```

Do not add new feature surface in this task beyond what the E2E failures demand.

- [x] **Step 4: Run Task 5 tests green**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_t2_t3_emitters_e2e.py tests/unit/test_threeway_e2e_walking_skeleton.py -q
```

Expected: PASS.

- [x] **Step 5: Commit Task 5**

Run:

```bash
env -u GIT_INDEX_FILE git add tests/unit/test_threeway_t2_t3_emitters_e2e.py tests/unit/test_threeway_e2e_walking_skeleton.py scripts/seat_emit.py scripts/chief_emit.py scripts/overseer_emit.py threeway/approval_authority.py
env -u GIT_INDEX_FILE git commit -m "test(threeway): prove T2 T3 signed bus walking skeletons"
```

---

### Task 6: Bus-First Codex Readiness and Status Surfaces

**Files:**
- Modify: `scripts/continuation_readiness.py`
- Modify: `.agents/skills/four-seat-protocol/scripts/seat_status.py`
- Modify: `scripts/mailbox_monitor.py`
- Modify: `tests/unit/test_continuation_readiness.py`
- Modify: `tests/unit/test_mailbox_monitor.py`
- Modify: `tests/unit/test_bus_unread.py`
- Modify: `scripts/codex_protocol_model.py`
- Modify: `docs/protocol/codex/continuation.md`
- Modify: `.codex/agents/readiness-bridge.toml`, `.codex/agents/protocol-director.toml`, `.codex/agents/protocol-operator.toml`, and `.codex/agents/protocol-coordinator.toml` if their prompt text still treats the legacy mailbox as the only protocol state source.

**Interfaces:**
- Produces: `continuation_readiness.render_threeway_bus(root: Path) -> None`.
- Produces: `mailbox_monitor` seat state key `unread_source` with values `legacy-mailbox`, `ref-bus`, or `ref-bus-unavailable`.
- Preserves existing mailbox orientation and read-only behavior.

- [x] **Step 1: Write failing readiness tests**

Add to `tests/unit/test_continuation_readiness.py`:

```python
def test_render_threeway_bus_surfaces_unavailable_sentinel(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(readiness, "run", lambda cmd, cwd, timeout=120: (1, "", "no ref"))
    monkeypatch.setattr(readiness.bus_unread, "bus_unread_count", lambda root, seat: None)
    readiness.render_threeway_bus(tmp_path)
    out = capsys.readouterr().out
    assert "Threeway Bus" in out
    assert "(unavailable: ref-bus)" in out
    assert "director" in out
```

```python
def test_main_renders_threeway_bus_section(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(readiness, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(readiness, "render_codex", lambda root: None)
    monkeypatch.setattr(readiness, "render_git", lambda root, commits: None)
    monkeypatch.setattr(readiness, "render_mailbox", lambda root: None)
    monkeypatch.setattr(readiness, "render_wave", lambda root, wave: None)
    monkeypatch.setattr(readiness, "render_ceremony", lambda root: None)
    monkeypatch.setattr(readiness, "render_environment", lambda root, smoke: None)
    monkeypatch.setattr(readiness, "render_threeway_bus", lambda root: print("## Threeway Bus\nsentinel"))
    assert readiness.main(["--skip-ceremony"]) == 0
    assert "Threeway Bus" in capsys.readouterr().out
```

- [x] **Step 2: Write failing monitor/source tests**

Add to `tests/unit/test_mailbox_monitor.py`:

```python
def test_scalar_cursor_marks_ref_bus_source(tmp_path: Path, monkeypatch) -> None:
    root = _repo(tmp_path)
    _cursor(root, "operator", "765")
    monkeypatch.setattr(monitor.bus_unread, "bus_unread_events", lambda root, seat, **k: [])
    state = monitor.collect_monitor_state(root, now=NOW)
    assert state["seats"]["operator"]["unread_source"] == "ref-bus"
```

```python
def test_scalar_cursor_bus_error_marks_ref_bus_unavailable(tmp_path: Path, monkeypatch) -> None:
    root = _repo(tmp_path)
    _cursor(root, "operator", "765")
    monkeypatch.setattr(monitor.bus_unread, "bus_unread_events", lambda root, seat, **k: None)
    state = monitor.collect_monitor_state(root, now=NOW)
    assert state["seats"]["operator"]["unread_count"] == "(unavailable: ref-bus)"
    assert state["seats"]["operator"]["unread_source"] == "ref-bus-unavailable"
```

- [x] **Step 3: Run surface tests red**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_continuation_readiness.py tests/unit/test_mailbox_monitor.py -q
```

Expected: FAIL because `render_threeway_bus` and `unread_source` do not exist.

- [x] **Step 4: Implement readiness bus section**

In `scripts/continuation_readiness.py`, import `bus_unread` and add:

```python
import bus_unread
```

Add:

```python
def render_threeway_bus(root: Path) -> None:
    section("Threeway Bus")
    code, local_tip, local_err = run(
        ["git", "for-each-ref", "refs/threeway/events", "--format=%(objectname)"],
        root,
    )
    tip = local_tip.strip() if code == 0 and local_tip.strip() else "(unavailable: ref-bus)"
    print(f"local events ref: {tip}")
    code, remote_tip, remote_err = run(
        ["git", "ls-remote", "origin", "refs/threeway/events"],
        root,
        timeout=20,
    )
    if code == 0 and remote_tip.strip():
        print(f"remote events ref: {remote_tip.split()[0]}")
    else:
        print("remote events ref: (unavailable: ref-bus)")
    print("unread bus counts:")
    for seat in SEATS:
        count = bus_unread.bus_unread_count(root, seat)
        rendered = "(unavailable: ref-bus)" if count is None else str(count)
        print(f"{seat:<9} {rendered}")
```

Call it in `main()` after `render_mailbox(root)`:

```python
render_threeway_bus(root)
```

- [x] **Step 5: Implement mailbox monitor source labels**

In `collect_monitor_state`, set source:

```python
if bus_unread.is_migrated_cursor(cursor):
    if unread is None:
        unread_source = "ref-bus-unavailable"
    else:
        unread_source = "ref-bus"
else:
    unread_source = "legacy-mailbox"
```

Include it in each seat state:

```python
"unread_source": unread_source,
```

In `render_snapshot`, append:

```python
f"source={seat_state['unread_source']} "
```

- [x] **Step 6: Add latest bus descriptors to `seat_status.py`**

Inside the migrated cursor branch, replace the count-only print with:

```python
evs = bus_unread.bus_unread_events(root, seat)
if evs is None:
    print("UNREAD: (unavailable: ref-bus)")
else:
    print(f"UNREAD: {len(evs)} / ref-bus")
    for ev in evs[-12:]:
        print(f"  * {bus_unread.format_unread(ev)}")
```

- [x] **Step 7: Update Codex text surfaces**

Update `scripts/codex_protocol_model.py`, `docs/protocol/codex/continuation.md`, and relevant `.codex/agents/*.toml` text so they say:

```text
The signed three-way ref-bus is the load-bearing state source for three-way facts. The free-form mailbox remains the human coordination channel and must still be checked before four-seat protocol decisions.
```

Keep the side-effect and no-cursor-consumption rules unchanged.

- [x] **Step 8: Run Task 6 tests green**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_continuation_readiness.py tests/unit/test_mailbox_monitor.py tests/unit/test_bus_unread.py tests/unit/test_codex_protocol_model.py -q
```

Expected: PASS.

- [x] **Step 9: Commit Task 6**

Run:

```bash
env -u GIT_INDEX_FILE git add scripts/continuation_readiness.py .agents/skills/four-seat-protocol/scripts/seat_status.py scripts/mailbox_monitor.py scripts/codex_protocol_model.py docs/protocol/codex/continuation.md .codex/agents tests/unit/test_continuation_readiness.py tests/unit/test_mailbox_monitor.py tests/unit/test_bus_unread.py tests/unit/test_codex_protocol_model.py
env -u GIT_INDEX_FILE git commit -m "feat(codex): surface signed threeway bus in readiness"
```

---

### Task 7: Protected Main Guard and Preflight Boundary

**Files:**
- Modify: `scripts/run_merge_gate.py`
- Create: `tests/unit/test_threeway_run_merge_gate_protected_main.py`

**Interfaces:**
- Produces CLI flag: `--allow-protected-main`.
- Produces helper: `_protected_main_preflight(args) -> tuple[bool, str]`.
- `refs/heads/main` without explicit flag returns rc2 before polling.
- `refs/heads/main` with explicit flag still fails closed locally when deployment-only controls cannot be verified.

- [x] **Step 1: Write failing protected-main tests**

Create:

```python
"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_run_merge_gate_protected_main.py -q"""

import contextlib
import io


def _run(argv):
    from scripts.run_merge_gate import main
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()


def test_refs_heads_main_requires_explicit_allow_flag(tmp_path, monkeypatch):
    rc, out, err = _run(["--repo-dir", str(tmp_path), "--main-ref", "refs/heads/main", "--run-once"])
    assert rc == 2
    assert "refusing protected main" in err


def test_refs_heads_main_allow_still_fails_closed_without_deployment_preflight(tmp_path, monkeypatch):
    rc, out, err = _run(["--repo-dir", str(tmp_path), "--main-ref", "refs/heads/main",
                         "--allow-protected-main", "--run-once"])
    assert rc == 1
    assert "protected-main deployment controls unavailable" in err
```

- [x] **Step 2: Run protected-main tests red**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_run_merge_gate_protected_main.py -q
```

Expected: FAIL because `--allow-protected-main` and refusal logic are missing.

- [x] **Step 3: Implement protected-main guard**

In `_build_argparser()`:

```python
ap.add_argument("--allow-protected-main", action="store_true")
```

Add helpers:

```python
def _is_protected_main_ref(ref: str) -> bool:
    return ref == "refs/heads/main"


def _protected_main_preflight(args) -> tuple[bool, str]:
    if not _is_protected_main_ref(args.main_ref):
        return True, "not protected main"
    if not args.allow_protected_main:
        return False, "refusing protected main without --allow-protected-main"
    return False, "protected-main deployment controls unavailable from local repo; test-infeasible without branch protection/ref-ACL attestation"
```

At the start of `main()` after parsing:

```python
ok, reason = _protected_main_preflight(args)
if not ok:
    print(reason, file=sys.stderr)
    return 2 if "without --allow-protected-main" in reason else 1
```

This intentionally blocks local protected-main use until a future deployment has verifiable branch protection/ref-ACL evidence.

- [x] **Step 4: Run Task 7 tests green**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_run_merge_gate_protected_main.py tests/unit/test_threeway_e2e_walking_skeleton.py tests/unit/test_threeway_t2_t3_emitters_e2e.py -q
```

Expected: PASS.

- [x] **Step 5: Commit Task 7**

Run:

```bash
env -u GIT_INDEX_FILE git add scripts/run_merge_gate.py tests/unit/test_threeway_run_merge_gate_protected_main.py
env -u GIT_INDEX_FILE git commit -m "fix(threeway): fail closed on protected main gate targets"
```

---

### Task 8: Docs Sync, ADR, and Final Verification

**Files:**
- Modify: `docs/protocol/threeway/README.md`
- Modify: `docs/protocol/threeway/ONBOARDING.md`
- Modify: `docs/protocol/threeway/CODEX-ADOPTION.md`
- Modify: `docs/protocol/threeway/UNIFIED-OPERATING-DOCTRINE.md`
- Modify: `ARCHITECTURE.md`
- Modify: `DECISIONS.md`
- Modify: `docs/protocol/threeway/MECHANISM-LEDGER.md` if Task 2-7 changed statuses.
- Modify: `docs/superpowers/specs/2026-06-26-threeway-expanded-core-mechanism.md` only to mark implemented evidence, not to rewrite scope.

**Interfaces:**
- Consumes: all Task 1-7 verification commands.
- Produces: command-cited docs that distinguish free-form mailbox, signed bus T1 path, completed T2/T3 emitter path, and real-main hardening boundary.

- [x] **Step 1: Refresh ledger status after implementation**

Update `_ROWS` in `scripts/threeway_mechanism_ledger.py` so these become `live` with CLI emitters and tests:

```text
brief_superseded
attestation_revoked
co_sign
re_verify
human_approval
```

Then run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/threeway_mechanism_ledger.py > docs/protocol/threeway/MECHANISM-LEDGER.md
env -u GIT_INDEX_FILE .venv/bin/python scripts/threeway_mechanism_ledger.py --check
```

Expected: exit 0.

- [x] **Step 2: Locate stale claims**

Run:

```bash
env -u GIT_INDEX_FILE rg -n "wired into nothing|legacy mailbox bus still live|legacy mailbox bus|keys not provisioned|T2/T3 emission still deferred|bootstrap_emit" docs/protocol/threeway ARCHITECTURE.md DECISIONS.md docs/superpowers/specs/2026-06-26-threeway-expanded-core-mechanism.md
```

Expected: exact stale claim sites. Update only the claims made stale by this implementation.

- [x] **Step 3: Update docs with command-cited evidence**

For every factual claim about live mechanisms, include a citation like:

```text
Verified via `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_t2_t3_emitters_e2e.py -q` -> all tests passed.
```

For inventory coverage, cite:

```text
Verified via `env -u GIT_INDEX_FILE .venv/bin/python scripts/threeway_mechanism_ledger.py --check` -> exit 0.
```

For protected-main boundary, cite:

```text
Verified via `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_run_merge_gate_protected_main.py -q` -> all tests passed.
```

- [x] **Step 4: Append ADR in `DECISIONS.md`**

Append a new ADR entry with this shape:

```markdown
## ADR-064: Threeway T2/T3 emitter completion and protected-main boundary

Date: 2026-06-26

Decision:
- The signed ref-bus is the load-bearing state source for threeway facts.
- T2/T3 non-overseer facts are emitted through principal-safe CLIs using dynamic bus-state authority checks.
- Chief human approvals are key-bound to rostered approver seats.
- `refs/heads/main` remains fail-closed without deployment-verifiable protected-main controls.

Evidence:
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_t2_t3_emitters_e2e.py -q` -> <paste exact output>
- `env -u GIT_INDEX_FILE .venv/bin/python scripts/threeway_mechanism_ledger.py --check` -> exit 0
- `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_run_merge_gate_protected_main.py -q` -> <paste exact output>
```

Use the next ADR number if `DECISIONS.md` already has ADR-064.

- [x] **Step 5: Run full focused verification**

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest \
  tests/unit/test_threeway_mechanism_ledger.py \
  tests/unit/test_threeway_keys_bootstrap.py \
  tests/unit/test_threeway_seat_emit.py \
  tests/unit/test_threeway_chief_emit.py \
  tests/unit/test_threeway_overseer_emit.py \
  tests/unit/test_threeway_t2_t3_emitters_e2e.py \
  tests/unit/test_threeway_e2e_walking_skeleton.py \
  tests/unit/test_threeway_run_merge_gate_protected_main.py -q
```

Expected: PASS.

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest \
  tests/unit/test_threeway_tier.py \
  tests/unit/test_threeway_reducer.py \
  tests/unit/test_threeway_gate.py \
  tests/unit/test_threeway_gate_adversarial.py -q
```

Expected: PASS.

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest \
  tests/unit/test_continuation_readiness.py \
  tests/unit/test_mailbox_monitor.py \
  tests/unit/test_bus_unread.py \
  tests/unit/test_codex_protocol_model.py -q
```

Expected: PASS.

Run:

```bash
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
env -u GIT_INDEX_FILE .venv/bin/python scripts/check_no_ceremony.py
```

Expected: `ci_smoke.py` exit 0. `check_no_ceremony.py` exit 0, allowing only the pre-existing cv2 importorskip warning if it still appears.

- [x] **Step 6: Inspect scope**

Run:

```bash
env -u GIT_INDEX_FILE git status -sb
env -u GIT_INDEX_FILE git diff --stat
env -u GIT_INDEX_FILE git diff --check
```

Expected: only planned files changed; `git diff --check` produces no whitespace errors.

- [x] **Step 7: Commit Task 8**

Run:

```bash
env -u GIT_INDEX_FILE git add docs/protocol/threeway/README.md docs/protocol/threeway/ONBOARDING.md docs/protocol/threeway/CODEX-ADOPTION.md docs/protocol/threeway/UNIFIED-OPERATING-DOCTRINE.md docs/protocol/threeway/MECHANISM-LEDGER.md ARCHITECTURE.md DECISIONS.md docs/superpowers/specs/2026-06-26-threeway-expanded-core-mechanism.md scripts/threeway_mechanism_ledger.py
env -u GIT_INDEX_FILE git commit -m "docs(threeway): sync expanded signed bus core mechanism"
```

---

## Self-Review

**Spec coverage:**
- Mechanism ledger: Task 1 and Task 8.
- `seat_emit` T2/T3 operator facts: Task 2.
- `chief_emit` human approvals: Task 3.
- `overseer_emit` revocation/supersession facts: Task 4.
- T2/T3 walking skeletons and negative paths: Task 5.
- Codex bus-first readiness/status surfaces: Task 6.
- Real-main safety boundary: Task 7.
- Docs sync and ADR: Task 8.

**Placeholder scan:** This plan avoids banned placeholder wording. Where setup is repeated, the plan names the exact source block to copy or gives exact assertions.

**Type consistency:**
- `CandidateContext.integration_sha` matches `Event.subject_sha`.
- `current_reverify_challenge_nonce()` returns the nonce that `seat_emit.py` writes to `payload["challenge_nonce"]`.
- `rostered_approvers()` returns key-bound seat names consumed by `chief_emit.py`.
- `unread_source` is a string field consumed by `mailbox_monitor.render_snapshot()`.

**Execution recommendation:** Use subagent-driven development. The task boundaries are independent enough for fresh-context implementation and review, but Task 5 must run after Tasks 2-4, and Task 8 must run last.
