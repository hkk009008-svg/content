# Cross-Provider Seat Topology — Slice 2 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking. **Subagent model = OPUS** (standing user directive 2026-06-19). Test command is **mandatory-prefixed**: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest … -q`.

**Goal:** Harden the Slice-1 `threeway/` coordination bus into the spec §8 event-sourced design — one git commit per event on `refs/threeway/events` appended via an expected-old-OID CAS loop with per-seat cursor refs — add Pair B as a concurrent mirror, prove no lost/duplicated event under a 2-process race, and fold in the three carried fail-closed hardening findings.

**Architecture:** Replace the single-writer file `EventStore` (which globs filenames for `seq`) with a `RefEventStore` that writes each event as a git commit on `refs/threeway/events` (event blob + `index/<seq>` entry), allocating `seq` from the ref tip and re-signing on every CAS retry — behind the *same* `append`/`iter_events`/`all_events` interface the Slice-1 docstring already promised to keep stable. The mechanical merge-gate is unchanged in shape (it is only a *caller* of the store); Slice 2 adds the serial merge-queue re-stage path and a second pair. Three carried findings (scope-boundary, uncaught `CalledProcessError`, unsigned `brief_version`) are fixed first as fail-closed hardening.

**Tech Stack:** Python 3.11 (stdlib `subprocess` over `git` plumbing, object-store only — never a working tree), `cryptography` Ed25519, `rfc8785` JCS canonicalization, `pytest`. No new dependencies.

---

## Decisions surfaced (resolve at the pre-execution checkpoint)

Two consequential calls were surfaced and **both are now APPROVED by the user-principal (2026-06-19)**; they are baked into this plan as described below.

**D-A — Carried finding #3 (`brief_version`): SIGN it (add a 13th signed field). APPROVED.** *Baked into Chunk 1, Task 3; schema-reset policy in Task 3.*
The merge predicate reads the **candidate event's** `brief_version` field (`cand.brief_version`, off the unsigned envelope, at `predicate.py:74,:100,:143-144`) to choose *which* brief governs `allowed_paths`/tier, *which* `cycle_go` authorizes the merge, and the supersession freshness gate — but `brief_version` is excluded from the 12-field `_signed_view`, so a validly-signed candidate can be replayed with `brief_version` mutated post-sign (verify still passes) to redirect authorization to a different version. This is a real fail-open authorization-redirection vector, not a doc mismatch. Cost of signing: ~1 code line + 3 in-file comment syncs + a spec-text update; **no test count-pins exist and all fixtures sign live**, so blast radius is contained. The alternative (amend spec §6.3 to call `brief_version` an unsigned routing hint) leaves the supersession check reading attacker-mutable data — rejected. **If you prefer the spec-amendment instead, drop Task 3's `_signed_view` edit and replace it with the §6.3 prose change.**

**D-B — Legacy `coordination/` mailbox migration (spec §8.7/§8.8): DEFER into a separately tracked slice (APPROVED).** *User-approved 2026-06-19.*
Spec §8 folds two things together: the *new* `threeway/` event bus (this slice's headline) and *migrating the live human-operated markdown mailbox* (`send-event`/`consume-events`/`check_coordination.py`/`status.py`) to it. The §11 Slice 2 gate tests only the new ref-bus's race-safety — the legacy migration is **not gated**. Touching it means editing **6 independent seat-list copies** on the bus the live 4-seat campaign uses right now, with no gate payoff. The Pair-B work in this slice needs only new *threeway keystore* seats, not legacy edits.

**Tracked as its own slice — "Slice 2.5: legacy bus migration"** (sequenced after Slice 2's gate, before/with Slice 3). Its scope is fixed and the exact edit sites are already inventoried (the Slice-1 understand pass catalogued all of them):
- **Add `coordinator`/`coordinator2` as addressable receiving seats** — `scripts/protocol_mailbox.py:11` (`SEATS`, the canonical root that propagates to `RECIPIENTS`/`check_coordination.py ROLES`), `coordination/bin/send-event:29-30` (FROM/TO whitelists), `coordination/bin/consume-events:27` (ROLE whitelist + usage strings), `scripts/check_coordination.py:58-59,:85` (hardcoded seat regexes) + its `:51-55` comment, `scripts/status.py:126` (`_MAILBOX_SEATS`, an independent copy) + argparse help. **Note: spec §8.7's "four files to keep in sync" omits `protocol_mailbox.py` — it is the real root; treat it as a 5th sync target.**
- **Cursor backfill** ISO-timestamp → scalar `seq` for the 4 (→6) `seen/<seat>.txt` files + the per-seat `refs/threeway/cursors/<seat>` refs; change `check_coordination.py:63 _CURSOR_RE` (currently ISO-only, fatal on a scalar).
- **Shadow then retire** `events/`+`index/` alongside `mailbox/sent/` (read-only projection first), **no dual-write authority** at any point.
- **Gate:** the legacy-bus checkers (`check_coordination.py`, `status.py`) stay green across the seat additions; cursor backfill is reversible; no event lost in the shadow→authority cutover.

This plan does **not** create the Slice 2.5 plan doc (that is authored after Slice 2's gate is green, per the §11 boundary rule); it records the scope so nothing is dropped.

---

## Scope: what this plan does and does NOT build

**IN scope (gated by spec §11 Slice 2 DoD):**
- The three carried fail-closed findings (Chunk 1).
- Git object-store plumbing to write events as commits on a ref (Chunk 2).
- `RefEventStore`: one-commit-per-event on `refs/threeway/events` + `index/<seq>` + expected-old-OID CAS append loop with re-fetch/re-seq/re-sign; per-seat cursor refs `refs/threeway/cursors/<seat>`; the **2-process race gate** (Chunk 3).
- Pair B (director2/operator2/coordinator2): new keystore seats + a pair-parametrized candidate builder; two-pair concurrency; the **serial merge-queue re-stage-the-loser** path; abort-on-conflict → rework (Chunk 4).
- The Slice 2 adversarial gate suite, ADR-031, and `ARCHITECTURE.md`/spec doc-sync (Chunk 5).

**OUT of scope (deferred, with reason):**
- **Legacy `coordination/` markdown-bus migration** (§8.7/§8.8): receiving-seat edits to `send-event`/`consume-events`/`check_coordination.py`/`status.py`/`protocol_mailbox.py`, the ISO→scalar-`seq` cursor backfill, and the shadow-then-retire projection. **Deferred per Decision D-B into a separately tracked slice — "Slice 2.5: legacy bus migration"** (scope + exact edit sites fixed under D-B above; its plan doc is authored after Slice 2's gate is green).
- **Slice 3 strategic loop**: dual chief, overseer brief distribution, T2 other-pair-operator `co_sign`, T3 `re_verify` + two `human_approval`. `co_sign_satisfied` keeps returning `False` for T2/T3 (Slice-1 behavior) so escalated tiers still cannot promote.
- **Non-test key/CI provisioning** (§6.4 deployment): all tests use ephemeral generated keys; a real run needs the keystore + CI signer provisioned off-repo. Flagged, not built. `threeway/keys_bootstrap.py` is the provisioning CLI; Task 4.2 extends its seat tuple only.
- **Rebase merge strategy** (§6.4 defers it; v1 stays merge-only, abort-on-conflict).

---

## File Structure

| File | Slice-2 change | Responsibility |
|---|---|---|
| `threeway/predicate.py` | **modify** (`_within_allowed` + a `rev_parse` guard before `:94`) | F1 scope-boundary + F2 existence-guard. |
| `threeway/gate.py` | **modify** (`import subprocess`; `try/except` around the predicate+recompute; duck-typed store) | F2 contract backstop; accept `RefEventStore`. |
| `threeway/envelope.py` | **modify** (`_signed_view` 13th field + comment sync) | D-A: sign `brief_version`. |
| `threeway/gitcas.py` | **modify** (add object-store event-write plumbing) | Blob/tree/commit/ref-CAS primitives for the event ref. |
| `threeway/refstore.py` | **create** | `RefEventStore` — the §8 event-sourced substrate + per-seat cursors. |
| `threeway/loop.py` | **modify** (pair-parametrize `build_candidate_events`) | Pair A *and* Pair B fact builders. |
| `threeway/keys_bootstrap.py` | **modify** (`SEATS` += director2/operator2/coordinator2) | Provision the new seats' keypairs. |
| `DECISIONS.md` | **append** ADR-031 | Slice-2 design record. |
| `ARCHITECTURE.md` | **add** a `threeway/` section | The package is currently undocumented in the truth file (0 mentions). |
| `docs/superpowers/specs/2026-06-19-cross-provider-seat-topology-design.md` | **modify** §6.2/§6.3 | Reconcile `merge_completed` enum + the 13-field signed set. |
| `tests/unit/test_threeway_gitcas.py` | **modify** | Cover the new plumbing. |
| `tests/unit/test_threeway_refstore.py` | **create** | `RefEventStore` + cursors + the 2-process race. |
| `tests/unit/test_threeway_predicate.py` | **modify** | F1 + F2 unit pins. |
| `tests/unit/test_threeway_envelope.py` | **modify** | D-A signed-`brief_version` pins. |
| `tests/unit/test_threeway_gate.py` | **modify** | F2 gate-level pin; duck-typed store. |
| `tests/unit/test_threeway_loop.py` | **modify** | Pair B builder. |
| `tests/unit/test_threeway_slice2_adversarial.py` | **create** | The §11 Slice 2 DoD gate suite. |

`RefEventStore` is a new file (not an edit of `store.py`) so the Slice-1 file `EventStore` and its 6 unit tests stay green as a reference substrate; the gate is made store-agnostic (it only calls `append`/`all_events`). The two stores share the `append(ev, priv)→Event` / `iter_events()` / `all_events()` interface.

---

## Conventions for every task

- **Test command (mandatory):** `env -u GIT_INDEX_FILE .venv/bin/python -m pytest <path> -q`. A leaked `GIT_INDEX_FILE` corrupts any test that shells out to git in a temp repo.
- **Every new test file opens** with `"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/<file>.py -q"""` as line 1, and carries its **own inline fixtures** (`_env()`, `_git()`, `seatkit`, `live_repo`-style). There is no `tests/unit/conftest.py`; do not add threeway fixtures to the shared `tests/conftest.py`.
- **No ceremony (ADR-028):** the threeway suite ships **zero** `xfail`/`skip`/`importorskip`. Prove every adversarial test non-vacuous by **mutating exactly one fact** in an otherwise-valid flow and asserting the outcome flips (ref does NOT advance). If a confirmed defect must be deferred, the pin MUST be `pytest.mark.xfail(strict=True, reason=…)` (else `scripts/check_no_ceremony.py` R1 fails) — but this slice introduces none.
- **Commits:** explicit-pathspec only — `git add -- <paths>` then `git commit -m "…" -- <paths>`; never bare `git commit`. End every message with the `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` trailer. One commit per task.
- **Never commit** `package.json`/`package-lock.json` — they carry a pre-existing unrelated `codex-chatgpt-control` working-tree change.
- **`git` plumbing invariant (gitcas):** never check out a working tree, never read/execute candidate workflow files. New plumbing uses a *scratch* `GIT_INDEX_FILE` (a `tmp_path`-style temp file), never the seat index, and still strips the inherited `GIT_INDEX_FILE` from the environment.
- **Smoke:** `.venv/bin/python scripts/ci_smoke.py` must stay green; run it at the end of each chunk.
- **Per-chunk review:** after each chunk, a `plan-document-reviewer` (planning) / spec-compliance + code-quality reviewers (execution) pass before proceeding.

---

## Chunk 1: Fail-closed hardening findings + spec reconciliation

> Sequenced first to de-risk the substrate work. Tasks 1–2 both edit `predicate.py`/`gate.py` → one implementer, sequential (R-ORCH: never two implementers on a shared file). Task 3 edits `envelope.py`; Task 4 is doc-only.

### Task 1: F1 — `_within_allowed` path-boundary (scope-bypass, predicate-only)

**Files:**
- Modify: `threeway/predicate.py:150-156` (`_within_allowed`)
- Test: `tests/unit/test_threeway_predicate.py`

**Context:** `predicate.py:154` accepts a diff path if `path == a or path.startswith(a)`. With an allow entry lacking a trailing slash (`allowed=["cinema"]`) this false-accepts a sibling (`"cinemax/y"`, `"cinema_secrets.txt"`) — a directory-scope escape. Latent today (every emit uses `"cinema/"`) but unguarded. **Rule #13 sibling: `tier._path_tier` (tier.py:13-18) uses the identical shape but there over-matching only RAISES the tier (fail-safe) — DO NOT change `tier._path_tier`.**

- [ ] **Step 1: Write the failing test**

In `tests/unit/test_threeway_predicate.py` (mirror the `_full_event_set`/`FakeRepo`/`reduce`/`evaluate` house style):

```python
def test_rejects_sibling_prefix_path_with_no_trailing_slash():
    # an allowed prefix WITHOUT a trailing slash must not swallow a sibling dir
    events = _full_event_set()
    for e in events:
        if e.kind == "brief":
            e.payload["allowed_paths"] = ["cinema"]      # no trailing slash
    repo = FakeRepo(diff=["cinemax/leak.py"])            # sibling — must REJECT
    d = evaluate("c1", reduce(events), repo, default_policy())
    assert d.outcome == REJECTED and "allowed_paths" in d.reason
```

- [ ] **Step 2: Run it — verify it fails**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_predicate.py::test_rejects_sibling_prefix_path_with_no_trailing_slash -q`
Expected: FAIL — on HEAD `startswith("cinema")` is True, so the path is accepted and the diff is not REJECTED for scope.

- [ ] **Step 3: Implement the boundary normalizer (predicate ONLY)**

Replace `_within_allowed` (predicate.py:150-156):

```python
def _within_allowed(diff, allowed) -> bool:
    if not allowed:
        return False
    for path in diff:
        if not any(_under(path, a) for a in allowed):
            return False
    return True


def _under(path: str, allowed: str) -> bool:
    # path-segment boundary: "cinema" matches "cinema/..." but NOT "cinemax/...";
    # an exact-file allow (e.g. "requirements.txt") still matches via ==.
    # NB: the identical shape in tier._path_tier is INTENTIONALLY left generous —
    # over-matching there only RAISES the tier (fail-safe). Do not "consistency-fix" it.
    if path == allowed:
        return True
    prefix = allowed if allowed.endswith("/") else allowed + "/"
    return path.startswith(prefix)
```

- [ ] **Step 4: Run — verify it passes (and the suite is still green)**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_predicate.py -q`
Expected: PASS (new test green; existing scope tests use trailing-slash allows and out-of-tree reject diffs → unaffected).

- [ ] **Step 5: Commit**

```bash
git add -- threeway/predicate.py tests/unit/test_threeway_predicate.py
git commit -m "fix(threeway): scope check requires a path-segment boundary (F1)" -- threeway/predicate.py tests/unit/test_threeway_predicate.py
```

### Task 2: F2 — a nonexistent attested SHA REJECTS, never crashes the gate

**Files:**
- Modify: `threeway/predicate.py:93-94` (add a `rev_parse` existence guard)
- Modify: `threeway/gate.py` (`import subprocess`; wrap the predicate + merge recompute in `try/except`)
- Test: `tests/unit/test_threeway_gate.py`, `tests/unit/test_threeway_predicate.py`

**Context:** `gitcas.changed_paths` (gitcas.py:43-45) and `gitcas.commit_tree` (gitcas.py:58-64) inherit `check=True`, so a well-formed-but-nonexistent SHA makes git exit 128 → `subprocess.CalledProcessError` escapes `evaluate` (predicate.py:94) and `run_gate` (gate.py:96/:109) — fail-closed (ref never moves) but it violates the `run_gate → GateResult` totality contract. Fix in two layers: a precise predicate guard + a gate backstop that also covers the gate-side `commit_tree`.

- [ ] **Step 1: Write the failing gate test**

In `tests/unit/test_threeway_gate.py` (reuse `live_repo`/`seatkit`; build a full valid set but bind candidate/release-attestation/ci_result/release_order to a ghost SHA — adapt the local `_valid_events_for` helper or `build_candidate_events` with a nonexistent `integration_sha`). **NOTE:** `test_threeway_gate.py` has no `_head` helper (only the adversarial file does), so this test resolves the ref inline via the file's existing `_git` helper — do not call `_head(r)` here.

```python
def test_run_gate_rejects_nonexistent_integration_sha_not_raises(live_repo, seatkit):
    r, base, branch = live_repo
    reg, ks, privs = seatkit
    store = EventStore(r / "coordination" / "threeway" / "events")
    ghost = "0" * 39 + "1"                       # 40-hex, no such object
    events = build_candidate_events(base, branch, ghost, privs, bus_id="prod")
    for ev in events:
        store.append(ev, privs[ev.signer.split(":", 1)[0]])
    res = run_gate("c1", store, r, registry_dir=reg, bus_id="prod",
                   main_ref="refs/threeway/test-main")
    assert res.outcome == "REJECTED", res.reason          # must NOT raise
    assert "integration_sha" in res.reason or "known commit" in res.reason
    # fail-closed: the protected ref did NOT move (inline rev-parse; no _head helper here)
    assert _git(r, "rev-parse", "refs/threeway/test-main").stdout.strip() == base
```

- [ ] **Step 2: Run it — verify it errors (not just fails)**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_gate.py::test_run_gate_rejects_nonexistent_integration_sha_not_raises -q`
Expected: ERROR — `subprocess.CalledProcessError` (returncode 128) raised out of `run_gate` at the `changed_paths` call; the assert is never reached.

- [ ] **Step 3a: Predicate guard (primary, named reason)**

In `threeway/predicate.py`, immediately before the `diff = repo.changed_paths(...)` line (currently `:94`):

```python
    # tier is GATE-COMPUTED, never trusted from the candidate.
    # fail-closed: a well-formed-but-nonexistent attested SHA must REJECT, not
    # crash changed_paths (git exit 128 -> CalledProcessError escapes run_gate).
    if repo.rev_parse(integ) is None:
        return Decision(REJECTED, "integration_sha is not a known commit")
    if repo.rev_parse(staging_base) is None:
        return Decision(REJECTED, "staging_base_sha is not a known commit")
    diff = repo.changed_paths(staging_base, integ)
```

- [ ] **Step 3b: Gate backstop (covers the gate-side `commit_tree`)**

In `threeway/gate.py`, add `import subprocess` at the top, and wrap the predicate evaluation + merge recompute (steps 3–4, currently gate.py:95-117) so any residual `CalledProcessError` becomes a REJECTED `GateResult`:

```python
    try:
        d = evaluate(candidate_id, state, _RepoAdapter(repo), policy, main_ref=main_ref)
        if d.outcome == REJECTED:
            return GateResult("REJECTED", d.reason)
        if d.outcome == PENDING:
            return GateResult("PENDING", d.reason)
        # 4. MERGEABLE — recompute the trusted merge … (existing body unchanged)
        cand = state.candidate(candidate_id)
        base = cand.payload["staging_base_sha"]
        branch = cand.payload["branch_sha"]
        tree, clean = gitcas.merge_tree(repo, base, branch)
        if not clean:
            return GateResult("REJECTED", "merge not clean (textual conflict) -> ABORT/REWORK")
        merge_commit = gitcas.commit_tree(repo, tree, [base, branch],
                                          f"threeway merge {candidate_id}")
        if merge_commit != cand.payload["integration_sha"]:
            return GateResult("REJECTED", "recomputed merge != attested integration_sha")
        if not gitcas.cas_update_ref(repo, main_ref, merge_commit, base):
            return GateResult("REJECTED", "stale: CAS expected-old no longer matches main.head")
    except subprocess.CalledProcessError as e:
        return GateResult("REJECTED", f"git plumbing failed on attested SHA: {e}")
```

Do **not** flip `gitcas._run` to a global `check=False` — that would silently mask real object-store corruption into empty results and break `merge_tree`'s exit-code-driven `clean` flag.

- [ ] **Step 4: Add the predicate-unit companion + run**

In `tests/unit/test_threeway_predicate.py`, a `FakeRepo` whose `rev_parse` returns `None` for the ghost SHA must yield `REJECTED`:

```python
def test_rejects_nonexistent_integration_sha():
    events = _full_event_set()
    repo = FakeRepo(rev_parse_map={MAIN_REF_VALUE: STAGING_BASE})  # integ resolves to None
    d = evaluate("c1", reduce(events), repo, default_policy())
    assert d.outcome == REJECTED and "known commit" in d.reason
```

(Adapt to the file's actual `FakeRepo` shape — extend it to return `None` for unknown refs instead of a fixed head.)

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_gate.py tests/unit/test_threeway_predicate.py -q`
Expected: PASS (gate test returns REJECTED + ref unmoved; predicate unit green; existing tests whose `FakeRepo.rev_parse` returns a fixed head for any ref are unaffected).

- [ ] **Step 5: Commit**

```bash
git add -- threeway/predicate.py threeway/gate.py tests/unit/test_threeway_gate.py tests/unit/test_threeway_predicate.py
git commit -m "fix(threeway): nonexistent attested SHA REJECTs, run_gate stays total (F2)" -- threeway/predicate.py threeway/gate.py tests/unit/test_threeway_gate.py tests/unit/test_threeway_predicate.py
```

### Task 3: F3 / D-A — sign `brief_version` (close the authorization-redirection vector)

**Files:**
- Modify: `threeway/envelope.py` (`_signed_view` + the three single-source-of-truth comment lists)
- Test: `tests/unit/test_threeway_envelope.py`

**Context:** `brief_version` is read off the *unsigned* envelope by the predicate to pick the governing brief/`cycle_go`/supersession version (predicate.py:74,:100,:143-144). Signing it closes a post-sign mutation vector. **No test asserts the signed-field count; all fixtures sign live → no fixture regeneration.** (See Decision D-A for the override path.)

- [ ] **Step 1: Write the failing security pins**

In `tests/unit/test_threeway_envelope.py` (mirror `test_verify_fails_if_any_signed_field_is_mutated` and `test_signed_bytes_excludes_ephemeral_fields`):

```python
def test_verify_fails_if_brief_version_is_mutated():
    priv, pub_hex = keys.generate_keypair()
    ev = _ev(brief_version=1)
    sign_event(ev, priv)
    ev.brief_version = 2                      # redirect brief/cycle_go/freshness lookups
    with pytest.raises(InvalidSignature):
        verify_event(ev, pub_hex)

def test_signed_bytes_binds_brief_version():
    ev = _ev(brief_version=7)
    assert b"brief_version" in signed_bytes(ev)
```

- [ ] **Step 2: Run — verify both fail**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_envelope.py::test_verify_fails_if_brief_version_is_mutated tests/unit/test_threeway_envelope.py::test_signed_bytes_binds_brief_version -q`
Expected: FAIL — `brief_version` is absent from `_signed_view`, so mutation does not break verify and `signed_bytes` lacks the field.

- [ ] **Step 3: Add `brief_version` as the 13th signed field**

In `threeway/envelope.py`, append to the dict returned by `_signed_view` (after `"causation_id": ev.causation_id,`):

```python
        "causation_id": ev.causation_id,
        "brief_version": ev.brief_version,
```

Then sync **every `12`/`12-field` occurrence (4 sites)** that the file declares as the single source of truth, so they cannot drift: the module docstring (envelope.py:~6-8), the comment block (envelope.py:~25-29), the `_signed_view` docstring (`"""Return the 12-field dict…"""` at envelope.py:~69), and **move `brief_version` out of** the "intentionally NOT signed" comment (envelope.py:~62-67, which also says "12 fields in `_signed_view`"). Each must now read the 13-field set including `brief_version`. (`idempotency_key` already references `brief_version` as a fallback subject — no change there; `canonicalize` serializes `None` deterministically so null-`brief_version` events still sign/verify.)

- [ ] **Step 4: Run the envelope suite**

Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_envelope.py -q`
Expected: PASS (both new pins green; the 8 existing envelope tests unaffected — none asserts a field count).

- [ ] **Step 5: Commit**

```bash
git add -- threeway/envelope.py tests/unit/test_threeway_envelope.py
git commit -m "fix(threeway): sign brief_version — close post-sign authorization redirect (F3/D-A)" -- threeway/envelope.py tests/unit/test_threeway_envelope.py
```

**Signature-schema change policy (no migration — reset, because no persistent events exist).** Adding a 13th signed field changes the signed-bytes schema, so events signed under the old 12-field set would not verify under the new one. **There is nothing to migrate:** the threeway bus has **no persisted production events** — the committed trust root `coordination/threeway/keys/` holds only `README.md` (no `.pub`), there is no `refs/threeway/events` ref, and every Slice-1 store is an ephemeral per-test directory (re-built from `seatkit`/`live_repo` fixtures each run). So the policy is an explicit **reset**: the 13-field set is the normative signed schema as of Slice 2; pre-existing signatures (which exist only inside test runs that re-sign live) are not carried forward. The `schema_version` field (`threeway/1`, `__init__.py:11`, itself a signed field) is the forward lever **if** a future signed-set change ever ships against a *deployed* bus — then the gate would dual-verify by `schema_version` or require a bus drain. For Slice 2 that machinery is unnecessary and deliberately not built. **Do NOT bump `schema_version` for this change** — bumping would force-edit every `"threeway/1"` literal across the builders/tests for zero benefit while no old events exist to distinguish. (Record this policy in ADR-031, Task 18.)

### Task 4: Spec reconciliation (doc-only) — `merge_completed` enum + 13-field signed set

**Files:**
- Modify: `docs/superpowers/specs/2026-06-19-cross-provider-seat-topology-design.md` (§6.2 lines ~169-174 enum; §6.2 signed-set text ~191-193; §6.3 ~240-256)
- Modify: `threeway/__init__.py:21-23` (delete the now-resolved gap note)

- [ ] **Step 1: Edit the spec §6.2 kind enum** — append `merge_completed` to the list (currently ends `… event_retried, dead_letter }`).
- [ ] **Step 2: Edit the spec §6.2 signed-set text** (~lines 191-193) — state 13 fields including `brief_version`, matching Task 3.
- [ ] **Step 3: Edit spec §6.3** — note the attestation/predicate brief+version binding is now cryptographic (signed `brief_version`), not a plaintext lookup.
- [ ] **Step 4: Remove the gap note** at `threeway/__init__.py:21-23` ("not yet in the spec §6.2 kind enum") — the enum now includes it.
- [ ] **Step 5: Verify smoke + commit**

Run: `.venv/bin/python scripts/ci_smoke.py` → expect OK (doc-claim gate is same-line anchors; spec is advisory, but keep it true).
Run: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_package.py -q` → PASS (`test_core_kinds_present` already enforces `merge_completed` in `THREEWAY_KINDS`).

```bash
git add -- docs/superpowers/specs/2026-06-19-cross-provider-seat-topology-design.md threeway/__init__.py
git commit -m "docs(threeway): spec §6.2/§6.3 — add merge_completed enum + 13-field signed set" -- docs/superpowers/specs/2026-06-19-cross-provider-seat-topology-design.md threeway/__init__.py
```

---

## Chunk 2: Git object-store plumbing for the event ref

> Adds the primitives `RefEventStore` needs, all object-store-only (no working tree). Builds trees via a **scratch** `GIT_INDEX_FILE`, never the seat index. Each task is one primitive + its temp-repo test in `tests/unit/test_threeway_gitcas.py`.

**Shared invariant for every primitive:** reuse `gitcas._env()` (strips the inherited `GIT_INDEX_FILE`) and `gitcas._DET_ENV` for any commit; the scratch index path is created with `tempfile` under the repo and removed after.

### Task 5: `write_blob` + `read_blob_at`

**Files:** Modify `threeway/gitcas.py`; Test `tests/unit/test_threeway_gitcas.py`.

- [ ] **Step 0: Add the single-repo test helper `_new_repo`** (DEFINE it — it does not exist; the file's existing `repo` fixture returns a `(r, base, branch)` tuple, but Chunk-2/3 tests want a bare repo path). Add to `tests/unit/test_threeway_gitcas.py` (and copy the same body into the new `tests/unit/test_threeway_refstore.py` in Chunk 3 — inline fixtures, no shared conftest):

```python
def _new_repo(tmp_path):
    r = tmp_path / "r"; r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@e.st"); _git(r, "config", "user.name", "t")
    (r / "base.txt").write_text("base\n")
    _git(r, "add", "-A"); _git(r, "commit", "-q", "-m", "base")
    return r        # NOTE: returns the repo PATH only (not the fixture's tuple)
```

- [ ] **Step 1: Failing test**

```python
def test_write_blob_and_read_back(tmp_path):
    r = _new_repo(tmp_path)
    oid = gitcas.write_blob(r, b'{"k": 1}\n')
    assert len(oid) == 40
    assert gitcas.read_blob(r, oid) == b'{"k": 1}\n'

def test_read_blob_at_commit_path_missing_returns_none(tmp_path):
    r = _new_repo(tmp_path)
    head = _git(r, "rev-parse", "HEAD").stdout.strip()
    assert gitcas.read_blob_at(r, head, "index/00000001") is None
```

- [ ] **Step 2: Run → FAIL** (after `_new_repo` exists, the first unimplemented call fails with `AttributeError: module 'threeway.gitcas' has no attribute 'write_blob'`/`read_blob`/`read_blob_at`, depending on collection order — any of the three is the intended red).

- [ ] **Step 3: Implement**

```python
# NB: blob I/O deliberately does NOT route through gitcas._run — _run forces text=True,
# which would corrupt read_blob's raw bytes. Keep these as raw subprocess.run(env=_env()).
def write_blob(repo, data: bytes) -> str:
    """Write a blob into the object store; return its 40-hex OID. No working tree."""
    p = subprocess.run(["git", "-C", str(repo), "hash-object", "-w", "--stdin"],
                       input=data, capture_output=True, env=_env(), check=True)
    return p.stdout.decode().strip()


def read_blob(repo, oid: str) -> bytes:
    p = subprocess.run(["git", "-C", str(repo), "cat-file", "blob", oid],
                       capture_output=True, env=_env(), check=True)
    return p.stdout


def read_blob_at(repo, commit_ish: str, path: str) -> bytes | None:
    """Read blob bytes at <commit>:<path>; None if the path is absent."""
    p = subprocess.run(["git", "-C", str(repo), "cat-file", "blob", f"{commit_ish}:{path}"],
                       capture_output=True, env=_env(), check=False)
    return p.stdout if p.returncode == 0 else None
```

(Note `input=` is bytes → do not pass `text=True` here.)

- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** (`feat(threeway): gitcas blob write/read primitives`).

### Task 6: `list_index_seqs` + `build_tree_with` + `commit_on` + `cas_create_or_update_ref`

**Files:** Modify `threeway/gitcas.py`; Test `tests/unit/test_threeway_gitcas.py`.

- [ ] **Step 1: Failing tests**

```python
def test_build_tree_extends_parent_and_commits_on_ref(tmp_path):
    r = _new_repo(tmp_path)
    b1 = gitcas.write_blob(r, b'{"e": 1}\n')
    idx1 = gitcas.write_blob(r, b'{"uuid": "e1", "path": "events/b1/e1.json"}\n')
    tree = gitcas.build_tree_with(r, None, [
        ("events/b1/e1.json", b1), ("index/00000001", idx1)])
    c1 = gitcas.commit_on(r, tree, None, "threeway event 00000001")
    # create the ref via CAS with no expected-old
    assert gitcas.cas_create_or_update_ref(r, "refs/threeway/events", c1, None) is True
    assert gitcas.list_index_seqs(r, c1) == [1]
    assert gitcas.read_blob_at(r, c1, "events/b1/e1.json") == b'{"e": 1}\n'

def test_cas_create_rejects_when_ref_already_exists(tmp_path):
    r = _new_repo(tmp_path)
    tree = gitcas.build_tree_with(r, None, [("index/00000001", gitcas.write_blob(r, b"x"))])
    c1 = gitcas.commit_on(r, tree, None, "e1")
    assert gitcas.cas_create_or_update_ref(r, "refs/threeway/events", c1, None) is True
    # a second create with expected-old=None must FAIL (ref exists)
    assert gitcas.cas_create_or_update_ref(r, "refs/threeway/events", c1, None) is False

def test_second_event_extends_first_tree(tmp_path):
    r = _new_repo(tmp_path)
    t1 = gitcas.build_tree_with(r, None, [("index/00000001", gitcas.write_blob(r, b"a"))])
    c1 = gitcas.commit_on(r, t1, None, "e1")
    t1_tree = _git(r, "rev-parse", f"{c1}^{{tree}}").stdout.strip()
    t2 = gitcas.build_tree_with(r, t1_tree, [("index/00000002", gitcas.write_blob(r, b"b"))])
    c2 = gitcas.commit_on(r, t2, c1, "e2")
    assert gitcas.list_index_seqs(r, c2) == [1, 2]

def test_tree_of_resolves_commit_tree(tmp_path):
    r = _new_repo(tmp_path)
    c1 = gitcas.commit_on(r, gitcas.build_tree_with(
        r, None, [("index/00000001", gitcas.write_blob(r, b"a"))]), None, "e1")
    assert gitcas.tree_of(r, c1) == _git(r, "rev-parse", f"{c1}^{{tree}}").stdout.strip()
    assert gitcas.tree_of(r, "0" * 39 + "1") is None      # unresolvable -> None
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement**

Add `import tempfile` to the **top-of-file imports** of `gitcas.py` (alongside the existing `import os`, `import subprocess`), then add these functions:

```python
def list_index_seqs(repo, commit_ish: str) -> list[int]:
    """Sorted seqs from index/<8-digit> entries at <commit>. [] if ref/tree absent."""
    p = _run(repo, "ls-tree", "--name-only", commit_ish, "index/", check=False)
    if p.returncode != 0:
        return []
    seqs = []
    for line in p.stdout.splitlines():
        name = line.rsplit("/", 1)[-1]
        if name.isdigit():
            seqs.append(int(name))
    return sorted(seqs)


def build_tree_with(repo, base_tree: str | None, entries: list[tuple[str, str]]) -> str:
    """Return a tree OID = base_tree (or empty) plus (path, blob_oid) entries.
    Uses a SCRATCH index file — never the seat index, never a working tree."""
    # Reserve a NAME but leave NO file: git refuses a pre-existing 0-byte GIT_INDEX_FILE
    # ("index file smaller than expected") and only creates a fresh index when the path
    # is ABSENT. So mkstemp then immediately remove. (NamedTemporaryFile would leave the
    # empty file behind and break update-index.)
    fd, idx = tempfile.mkstemp(dir=str(repo), suffix=".idx")
    os.close(fd)
    os.remove(idx)
    try:
        env = _env({"GIT_INDEX_FILE": idx})
        if base_tree:
            subprocess.run(["git", "-C", str(repo), "read-tree", base_tree],
                           env=env, check=True, capture_output=True)
        for path, blob in entries:
            subprocess.run(["git", "-C", str(repo), "update-index", "--add",
                            "--cacheinfo", f"100644,{blob},{path}"],
                           env=env, check=True, capture_output=True)
        p = subprocess.run(["git", "-C", str(repo), "write-tree"],
                           env=env, check=True, capture_output=True, text=True)
        return p.stdout.strip()
    finally:
        if os.path.exists(idx):
            os.remove(idx)


def tree_of(repo, commit_ish: str) -> str | None:
    """Resolve <commit>^{tree} to a tree OID; None if unresolvable.
    REQUIRED because gitcas.rev_parse hardcodes a ^{commit} peel — calling it with
    f'{tip}^{{tree}}' becomes '{tip}^{tree}^{commit}' and ERRORS. Do not reuse rev_parse
    for tree resolution (the predicate gate depends on rev_parse's ^{commit} peel)."""
    p = _run(repo, "rev-parse", "--verify", f"{commit_ish}^{{tree}}", check=False)
    return p.stdout.strip() if p.returncode == 0 else None


def commit_on(repo, tree_oid: str, parent: str | None, message: str) -> str:
    args = ["commit-tree", tree_oid]
    if parent:
        args += ["-p", parent]
    args += ["-m", message]
    p = _run(repo, *args, env_extra=_DET_ENV)
    return p.stdout.strip()


_ZERO_OID = "0" * 40

def cas_create_or_update_ref(repo, ref: str, new_oid: str, expected_old: str | None) -> bool:
    """Atomic ref CAS. expected_old=None creates the ref (must not exist, zero-OID old)."""
    old = expected_old if expected_old is not None else _ZERO_OID
    p = _run(repo, "update-ref", ref, new_oid, old, check=False)
    return p.returncode == 0
```

- [ ] **Step 4: Run → PASS.** Confirm `build_tree_with` leaves no `*.idx` files (the `finally` removes the scratch index).
- [ ] **Step 5: Commit** (`feat(threeway): gitcas tree/commit/ref-CAS plumbing for the event ref`).

### Task 7: chunk close — gitcas suite + smoke

- [ ] Run `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_gitcas.py -q` → all PASS.
- [ ] Run `.venv/bin/python scripts/ci_smoke.py` → OK.
- [ ] (No commit; this is a verification gate before Chunk 3.)

---

## Chunk 3: `RefEventStore` — the event-sourced substrate + cursors + the 2-process race

> The §8 core. Implements the same `append`/`iter_events`/`all_events` interface on `refs/threeway/events`, plus per-seat cursor refs. The headline §11 Slice 2 gate ("no lost/duplicated event under a 2-process race") lives in Task 9.

### Task 8: `RefEventStore.append` (CAS loop, re-seq + re-sign) + `iter_events`/`all_events`

**Files:** Create `threeway/refstore.py`; Test `tests/unit/test_threeway_refstore.py`.

**Design:** one commit per event on `refs/threeway/events`; commit tree adds `events/<brief_id>/<id>.json` (the signed event JSON) + `index/<seq>` (`{uuid, path, object_digest}`). `append` reads the tip, allocates `seq = max(index seqs)+1`, sets `ev.seq`, **signs**, builds the extending tree, commits with parent=tip, and CAS-pushes with `expected_old=tip`. On a **lost-CAS** (a competitor advanced the tip) it re-reads the tip, re-allocates `seq`, **re-signs** (seq is in the signed bytes), and retries with bounded backoff. **Ambiguous-push idempotency (effectively-once, spec §6.2):** at the top of every loop iteration `append` scans for an event with the same `idempotency_key` (which excludes `seq` + ephemeral fields, so a re-signed retry of the *same logical fact* has the *same* key); if found it returns the persisted event instead of double-appending — so a push whose ack was lost, a crash-after-CAS-before-return, or a timed-out retry all de-duplicate. This makes `append` safe to retry under ambiguity.

- [ ] **Step 1: Failing tests (interface parity with `EventStore`)**

Define the file's inline helpers first (no shared conftest). Copy `_env`/`_git`/`_new_repo` from `test_threeway_gitcas.py` (Task 5 Step 0), import `keys`/`Event`/`verify_event`, and DEFINE a **seq-less `_unsigned`** — the existing `_unsigned` in `test_threeway_store.py:7` requires a positional `seq` and so cannot be reused here:

```python
"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_refstore.py -q"""
import os, subprocess, pytest
from threeway import keys
from threeway.envelope import Event, verify_event
from threeway.refstore import RefEventStore, BusContentionError

# _env / _git / _new_repo: copy verbatim from test_threeway_gitcas.py (Task 5 Step 0)

def _unsigned(id="e", kind="attestation", signer="operator:claude:s1", **over):
    base = dict(id=id, seq=0, bus_id="prod", schema_version="threeway/1", kind=kind,
                sender="operator", recipient="all", signer=signer, payload={"k": id},
                brief_id="b1", brief_version=1)
    base.update(over)
    return Event(**base)
# ----

def test_append_assigns_monotonic_seq_from_one(tmp_path):
    r = _new_repo(tmp_path)
    priv, _ = keys.generate_keypair()
    store = RefEventStore(r)
    a = store.append(_unsigned(kind="attestation"), priv)
    b = store.append(_unsigned(kind="attestation"), priv)
    assert (a.seq, b.seq) == (1, 2)

def test_iter_events_returns_in_seq_order_and_verifies(tmp_path):
    r = _new_repo(tmp_path)
    priv, pub = keys.generate_keypair()
    store = RefEventStore(r)
    store.append(_unsigned(id="e1"), priv)
    store.append(_unsigned(id="e2"), priv)
    evs = store.all_events()
    assert [e.id for e in evs] == ["e1", "e2"]
    # the persisted event is signed over its assigned seq (verify with the right key)
    verify_event(evs[0], pub)                     # does not raise

def test_seq_persists_across_store_reopen(tmp_path):
    r = _new_repo(tmp_path)
    priv, _ = keys.generate_keypair()
    RefEventStore(r).append(_unsigned(id="e1"), priv)
    again = RefEventStore(r).append(_unsigned(id="e2"), priv)
    assert again.seq == 2                          # tip-derived, durable
```

- [ ] **Step 2: Run → FAIL** (no `threeway.refstore`).

- [ ] **Step 3: Implement `RefEventStore`**

```python
"""RefEventStore — the spec §8 event-sourced substrate.

One git commit per event on EVENTS_REF; the commit tree adds the signed event
JSON (events/<brief_id>/<id>.json) and its index entry (index/<seq:08d>).
seq is allocated from the ref tip and the event is RE-SIGNED on every CAS retry
(seq is in the signed bytes). Same public interface as threeway.store.EventStore;
iter_events()/all_events() are RAW readers (no signature verify — that stays the
gate's chokepoint).
"""
from __future__ import annotations

import hashlib
import json
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from threeway import gitcas
from threeway.envelope import (Event, from_json_obj, idempotency_key,
                               sign_event, to_json_obj)

EVENTS_REF = "refs/threeway/events"
_MAX_RETRIES = 50
_BACKOFF_BASE = 0.005


class BusContentionError(RuntimeError):
    pass


class RefEventStore:
    def __init__(self, repo, events_ref: str = EVENTS_REF):
        self._repo = repo
        self._ref = events_ref

    def _tip(self) -> str | None:
        return gitcas.rev_parse(self._repo, self._ref)

    def _find_by_idempotency_key(self, key: str) -> Event | None:
        # idempotency_key is seq-independent (spec §6.2: excludes seq + ephemeral
        # fields), so a re-signed retry of the SAME logical fact has the SAME key.
        for ev in self.iter_events():
            if idempotency_key(ev) == key:
                return ev
        return None

    def append(self, ev: Event, private_key: Ed25519PrivateKey,
               _before_cas=None, _after_cas=None) -> Event:
        # _before_cas / _after_cas: test-only seams (None in production) to drive a
        # race / simulate a lost ack. AMBIGUOUS-PUSH IDEMPOTENCY: the key is computed
        # from the logical fields BEFORE seq assignment, so a retry after a push whose
        # ack was lost (or a crash-after-CAS-before-return) is de-duplicated below.
        target_key = idempotency_key(ev)
        for attempt in range(_MAX_RETRIES):
            # effectively-once: if this exact logical fact already landed (a prior CAS
            # succeeded but we didn't observe it), return the persisted event — never
            # double-append. This is what makes an ambiguous push safe to retry.
            existing = self._find_by_idempotency_key(target_key)
            if existing is not None:
                return existing

            tip = self._tip()
            seqs = gitcas.list_index_seqs(self._repo, tip) if tip else []
            ev.seq = (max(seqs) + 1) if seqs else 1
            sign_event(ev, private_key)                       # signs over the NEW seq

            event_bytes = json.dumps(to_json_obj(ev), ensure_ascii=False).encode()
            event_path = f"events/{ev.brief_id}/{ev.id}.json"
            digest = hashlib.sha256(event_bytes).hexdigest()
            index_bytes = json.dumps(
                {"uuid": ev.id, "path": event_path, "object_digest": digest},
                ensure_ascii=False).encode()
            index_path = f"index/{ev.seq:08d}"

            blob_e = gitcas.write_blob(self._repo, event_bytes)
            blob_i = gitcas.write_blob(self._repo, index_bytes)
            base_tree = gitcas.tree_of(self._repo, tip) if tip else None
            tree = gitcas.build_tree_with(
                self._repo, base_tree,
                [(event_path, blob_e), (index_path, blob_i)])
            commit = gitcas.commit_on(self._repo, tree, tip,
                                      f"threeway event {ev.seq:08d}")

            if _before_cas is not None:
                _before_cas(attempt)                          # competitor slips in here

            if gitcas.cas_create_or_update_ref(self._repo, self._ref, commit, tip):
                if _after_cas is not None:
                    _after_cas(attempt)        # test seam: simulate a lost ack post-CAS
                return ev
            time.sleep(_BACKOFF_BASE * (2 ** min(attempt, 6)))  # re-loop: re-seq + re-sign
        raise BusContentionError(f"event ref CAS lost {_MAX_RETRIES}x")

    def iter_events(self):
        tip = self._tip()
        if tip is None:
            return
        for seq in gitcas.list_index_seqs(self._repo, tip):
            idx = gitcas.read_blob_at(self._repo, tip, f"index/{seq:08d}")
            if idx is None:
                continue
            entry = json.loads(idx)
            raw = gitcas.read_blob_at(self._repo, tip, entry["path"])
            if raw is None:
                continue
            yield from_json_obj(json.loads(raw))

    def all_events(self) -> list[Event]:
        return list(self.iter_events())
```

`gitcas.tree_of` (added in Chunk 2 Task 6) resolves `tip^{tree}` to the parent tree OID for `build_tree_with`'s base. **Do NOT** use `gitcas.rev_parse` for this — it hardcodes a `^{commit}` peel, so `rev_parse(repo, f"{tip}^{{tree}}")` becomes `{tip}^{tree}^{commit}` and errors (returns `None`), silently producing an empty base tree and dropping all prior events. The empirical check confirming this is in the technical review.

- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** (`feat(threeway): RefEventStore — one-commit-per-event ref bus with append-CAS`).

### Task 9: the 2-process race + ambiguous-push idempotency

**Files:** Test `tests/unit/test_threeway_refstore.py`.

This task ships FOUR tests covering the §11 Slice 2 DoD's "no lost/duplicated event under a 2-process race" plus the effectively-once contract: **(9a)** a *deterministic forced-CAS-loss* test, **(9b)** a *genuine multi-process race* test, **(9c)** a timed-out-retry idempotency test, **(9d)** a crash-after-CAS-before-ack idempotency test.

- [ ] **Step 1a — deterministic forced-CAS-loss (one retry, via the `_before_cas` seam):**

```python
def test_concurrent_append_loses_no_event_and_re_signs(tmp_path):
    r = _new_repo(tmp_path)
    pa, pua = keys.generate_keypair()
    pb, pub_b = keys.generate_keypair()
    store = RefEventStore(r)
    # writer B appears exactly once, during writer A's first build, advancing the tip
    fired = {"n": 0}
    competitor = RefEventStore(r)
    def inject(attempt):
        if fired["n"] == 0:
            fired["n"] += 1
            competitor.append(_unsigned(id="B", signer="operator:codex:s1"), pb)
    a = store.append(_unsigned(id="A", signer="operator:claude:s1"), pa, _before_cas=inject)
    evs = {e.id: e for e in RefEventStore(r).all_events()}
    assert sorted(evs) == ["A", "B"]                 # neither lost, neither duplicated
    assert {evs["A"].seq, evs["B"].seq} == {1, 2}    # distinct, contiguous
    assert a.seq == 2                                # A re-seq'd after losing the first CAS
    verify_event(evs["A"], pua)                      # A re-signed over seq=2 (does not raise)
    verify_event(evs["B"], pub_b)

def test_append_raises_bus_contention_after_max_retries(tmp_path):
    r = _new_repo(tmp_path)
    p, _ = keys.generate_keypair(); op, _ = keys.generate_keypair()
    other = RefEventStore(r)
    def always_steal(attempt):
        other.append(_unsigned(id=f"x{attempt}"), op)   # advance the tip every attempt
    with pytest.raises(BusContentionError):
        RefEventStore(r).append(_unsigned(id="A"), p, _before_cas=always_steal)
```

- [ ] **Step 1b — genuine multi-process race (real OS processes, no seam).** The worker MUST be module-level so `multiprocessing` (spawn) can pickle it. Two real processes append concurrently to the *same* repo; the ref CAS is the only serialization point.

```python
import multiprocessing as mp

def _race_worker(args):                       # module-level: picklable under spawn
    repo, ks, seat, ids = args
    os.environ["THREEWAY_KEYSTORE"] = ks
    from threeway.keys import load_private
    from threeway.refstore import RefEventStore
    store = RefEventStore(repo); priv = load_private(seat)
    for i in ids:
        store.append(_unsigned(id=i, signer=f"{seat}:p:s1"), priv)

def test_genuine_two_process_race_no_loss(tmp_path):
    r = _new_repo(tmp_path)
    ks = tmp_path / "ks"; ks.mkdir()
    for s in ("operator", "operator2"):
        priv, _ = keys.generate_keypair()
        (ks / f"{s}.ed25519").write_text(keys.private_to_hex(priv) + "\n")
    N = 8
    work = [(str(r), str(ks), "operator",  [f"a{i}" for i in range(N)]),
            (str(r), str(ks), "operator2", [f"b{i}" for i in range(N)])]
    with mp.get_context("spawn").Pool(2) as pool:
        pool.map(_race_worker, work)
    evs = RefEventStore(r).all_events()
    assert len(evs) == 2 * N                              # nothing lost / duplicated
    assert sorted(e.seq for e in evs) == list(range(1, 2 * N + 1))   # distinct, contiguous
    assert len({e.id for e in evs}) == 2 * N             # every id present exactly once
```

> If the CI harness cannot import the test module in a spawned child (sys.path/conftest), fall back to `concurrent.futures.ThreadPoolExecutor` with the same body — each thread still spawns real concurrent `git` processes that genuinely contend on the ref CAS; the assertions are identical. Keep BOTH the deterministic (1a) and the genuine-race (1b) tests — the deterministic one pins the re-sign-on-retry semantics exactly; the genuine one proves the invariant holds under real concurrency.

- [ ] **Step 1c/1d — ambiguous-push idempotency (effectively-once):**

```python
def test_ambiguous_push_timed_out_retry_is_idempotent(tmp_path):
    # the SAME logical fact appended twice (a timed-out retry) lands exactly ONCE
    r = _new_repo(tmp_path); p, _ = keys.generate_keypair()
    store = RefEventStore(r)
    first = store.append(_unsigned(id="e1", kind="attestation"), p)
    again = store.append(_unsigned(id="e1", kind="attestation"), p)   # identical logical fact
    assert len(store.all_events()) == 1                  # de-duplicated by idempotency_key
    assert again.seq == first.seq                        # returned the persisted event

def test_crash_after_cas_then_retry_no_double_append(tmp_path):
    # CAS lands but the ack is "lost" (crash post-CAS); the retry must NOT double-append
    r = _new_repo(tmp_path); p, _ = keys.generate_keypair()
    store = RefEventStore(r)
    def boom(attempt): raise RuntimeError("ack lost after CAS")
    with pytest.raises(RuntimeError):
        store.append(_unsigned(id="e1", kind="attestation"), p, _after_cas=boom)
    assert len(store.all_events()) == 1                  # it DID land once
    store.append(_unsigned(id="e1", kind="attestation"), p)   # retry the same logical fact
    assert len(store.all_events()) == 1                  # idempotent: still exactly one
```

- [ ] **Step 2: Run → FAIL** (genuine-race + idempotency tests fail until Task 8's loop has the idempotency scan + re-seq/re-sign).
- [ ] **Step 3:** The Task-8 `append` already implements both the re-seq/re-sign loop and the `_find_by_idempotency_key` scan; if 9a fails, the re-sign is missing; if 9c/9d fail, the idempotency scan is missing or runs in the wrong place (it must be at the TOP of each loop iteration). Fix `RefEventStore.append`.
- [ ] **Step 4: Run → PASS.** (1b may take a second or two — real process startup.)
- [ ] **Step 5: Commit** (`test(threeway): 2-process race (deterministic + genuine) + ambiguous-push idempotency (§11 Slice 2)`).

### Task 10: per-seat cursor refs (`refs/threeway/cursors/<seat>`)

**Files:** Modify `threeway/refstore.py`; Test `tests/unit/test_threeway_refstore.py`.

**Design:** a cursor = "last `seq` scanned," stored as a blob (decimal `seq`) the ref points at; advanced by that seat via CAS. (A cursor is not a side-effect record; durable `event_acknowledged` facts + idempotent handlers cover a crash between acting and advancing — that handler work is Slice 3.)

- [ ] **Step 1: Failing tests**

```python
def test_cursor_starts_at_zero_and_advances(tmp_path):
    r = _new_repo(tmp_path); p, _ = keys.generate_keypair()
    store = RefEventStore(r)
    store.append(_unsigned(id="e1"), p); store.append(_unsigned(id="e2"), p)
    assert store.cursor_seq("operator") == 0
    store.advance_cursor("operator", 2)
    assert store.cursor_seq("operator") == 2

def test_cursor_advance_rejects_regression(tmp_path):
    r = _new_repo(tmp_path)
    store = RefEventStore(r)
    store.advance_cursor("operator", 5)
    assert store.advance_cursor("operator", 3) is False    # no going backward
    assert store.cursor_seq("operator") == 5

def test_cursor_advance_is_monotonic_under_cas_contention(tmp_path):
    # a concurrent advance to a HIGHER seq between this writer's read and CAS must not
    # cause a regression: the loser's CAS misses, it re-reads the higher value and no-ops.
    import threeway.refstore as _rs
    r = _new_repo(tmp_path)
    store = RefEventStore(r); other = RefEventStore(r)
    orig = _rs.gitcas.write_blob
    state = {"bumped": False}
    def racing_write(repo, data):                  # seam between this writer's read and CAS
        oid = orig(repo, data)
        if not state["bumped"]:
            state["bumped"] = True
            other.advance_cursor("operator", 9)    # competitor jumps ahead mid-attempt
        return oid
    _rs.gitcas.write_blob = racing_write
    try:
        assert store.advance_cursor("operator", 4) is False   # CAS misses; re-reads 9; 4<=9
    finally:
        _rs.gitcas.write_blob = orig
    assert store.cursor_seq("operator") == 9       # highest wins; never regressed
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** — `advance_cursor` is a **monotonic CAS loop**: read the current cursor, refuse if `seq <= current` (monotonic, no regression), else CAS the new seq blob with `expected_old = current_oid`; on a lost CAS (a concurrent advance moved the cursor) re-read and re-check monotonicity, so the higher value always wins and the loser never overwrites it.

```python
    def _cursor_ref(self, seat: str) -> str:
        return f"refs/threeway/cursors/{seat}"

    def _read_cursor(self, ref):
        oid = gitcas.rev_parse_any(self._repo, ref)        # blob, not commit
        cur = int(gitcas.read_blob(self._repo, oid).decode()) if oid is not None else 0
        return oid, cur

    def cursor_seq(self, seat: str) -> int:
        return self._read_cursor(self._cursor_ref(seat))[1]

    def advance_cursor(self, seat: str, seq: int) -> bool:
        ref = self._cursor_ref(seat)
        for _ in range(_MAX_RETRIES):
            cur_oid, cur = self._read_cursor(ref)
            if seq <= cur:
                return False                               # monotonic: regression / no-op
            new_oid = gitcas.write_blob(self._repo, f"{seq}\n".encode())
            if gitcas.cas_create_or_update_ref(self._repo, ref, new_oid, cur_oid):
                return True
            time.sleep(_BACKOFF_BASE)                      # CAS lost a concurrent advance; re-read
        raise BusContentionError(f"cursor CAS lost for {seat}")
```

Add `gitcas.rev_parse_any(repo, ref)` — like `rev_parse` but resolves to any object (a blob), `git rev-parse --verify <ref>` without the `^{commit}` peel; `None` on absence. (Add it to `gitcas.py` in this task with a one-line test.) The contention test monkeypatches `threeway.refstore.gitcas.write_blob` to inject a competitor between this writer's read and CAS — keep the patch local (restore in `finally`).

- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** (`feat(threeway): per-seat cursor refs — monotonic CAS advance with re-read on contention`).

### Task 11: chunk close — refstore suite + smoke

- [ ] `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_refstore.py tests/unit/test_threeway_gitcas.py -q` → PASS.
- [ ] `.venv/bin/python scripts/ci_smoke.py` → OK.

---

## Chunk 4: Pair B, two-pair concurrency, and the serial merge-queue re-stage

### Task 12: pair-parametrize `build_candidate_events` (Pair A + Pair B)

**Files:** Modify `threeway/loop.py`; Test `tests/unit/test_threeway_loop.py`.

**Context:** `build_candidate_events` (loop.py:29-56) hardcodes Pair A (pair "A", director/operator/coordinator, providers codex/claude/claude) **and** a hardcoded `candidate_id="c1"` and event ids `id=f"{kind}-{sender}"` (loop.py:18-20). Pair B = pair "B", director2/operator2/coordinator2, providers claude/codex/codex. **Two collisions must be fixed so two pairs can coexist in one `RefEventStore`:** (a) the builder must take a `candidate_id` so `state.release_order(candidate_id)` resolves per-candidate; (b) overseer-sent events (`brief`/`assignment`/`cycle_go`/`release_order`) get identical ids across pairs (`assignment-overseer` in both), and the event tree path is `events/<brief_id>/<id>.json` — identical ids OVERWRITE each other and lose one pair's facts. Scope the event `id` by `candidate_id`.

- [ ] **Step 1: Failing test** (define the `_privs_for` helper too — it does not exist):

```python
def _privs_for(seats):
    return {s: keys.generate_keypair()[0] for s in seats}

def test_build_candidate_events_for_pair_b():
    privs = _privs_for(("director2", "operator2", "coordinator2", "overseer", "ci"))
    evs = build_candidate_events("1"*40, "3"*40, "2"*40, privs, pair=PAIR_B, candidate_id="c2")
    a = next(e for e in evs if e.kind == "assignment")
    assert a.payload["pair"] == "B"
    assert a.payload["builder"] == "director2" and a.payload["builder_provider"] == "claude"
    assert a.payload["primary_verifier"] == "operator2" and a.payload["primary_verifier_provider"] == "codex"
    assert a.payload["executing_coordinator"] == "coordinator2"
    cand = next(e for e in evs if e.kind == "candidate")
    assert cand.signer.split(":", 1)[0] == "coordinator2"
    assert cand.candidate_id == "c2"

def test_two_pairs_have_disjoint_event_ids_and_per_candidate_release_order():
    privs = _privs_for(("director", "operator", "coordinator", "director2", "operator2",
                        "coordinator2", "overseer", "ci"))
    a = build_candidate_events("1"*40, "3"*40, "2"*40, privs, pair=PAIR_A, candidate_id="c1")
    b = build_candidate_events("1"*40, "4"*40, "5"*40, privs, pair=PAIR_B, candidate_id="c2")
    assert {e.id for e in a}.isdisjoint({e.id for e in b})           # no tree-path collision
    ro_a = next(e for e in a if e.kind == "release_order")
    ro_b = next(e for e in b if e.kind == "release_order")
    assert ro_a.payload["candidate_id"] == "c1" and ro_b.payload["candidate_id"] == "c2"
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** — in `threeway/loop.py`:
  1. Introduce a `PairConfig` (pair id, builder, builder_provider, primary_verifier, verifier_provider, coordinator) and `PAIR_A`/`PAIR_B` constants (Pair A = current Slice-1 values; Pair B = director2/claude, operator2/codex, coordinator2).
  2. Add `pair=PAIR_A` and `candidate_id="c1"` kwargs to `build_candidate_events`; keep the existing positional signature + defaults so all Slice-1 callers are unaffected.
  3. Thread the pair's seats/providers/signers through every `_e(...)` call.
  4. Thread `candidate_id` into the `candidate` envelope field for EVERY event **and** into the `release_requested`/`release_order` payloads (currently hardcoded `"candidate_id": "c1"` at loop.py:53,55).
  5. Scope event ids: make `_e` derive `id=f"{kind}-{sender}-{candidate_id}"` (or include `pair`+`candidate_id`) so two pairs' overseer-sent events never share a tree path.
- [ ] **Step 4: Run** `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_loop.py -q` → PASS (Slice-1 Pair-A test still green — its default `candidate_id="c1"` preserves the old ids' candidate scope; new Pair-B + disjoint-id tests green).
- [ ] **Step 5: Commit** (`feat(threeway): pair-parametrized candidate builder with per-candidate ids (Pair A + Pair B)`).

### Task 13: provision Pair-B seat keys

**Files:** Modify `threeway/keys_bootstrap.py:13` (`SEATS`); Test `tests/unit/test_threeway_keys_bootstrap.py` (or the keys test that asserts the seat tuple).

- [ ] **Step 1: Failing test** — assert `keys_bootstrap.SEATS` contains `director2`, `operator2`, `coordinator2` (and a bootstrap run writes their `.pub`/`.ed25519`).
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** — `SEATS = ("director", "operator", "coordinator", "director2", "operator2", "coordinator2", "overseer", "ci", "merge-gate")`.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** (`feat(threeway): bootstrap Pair-B seat keypairs`).

### Task 14: serial merge-queue — re-stage the loser when `main` advances

**Files:** Test `tests/unit/test_threeway_slice2_adversarial.py` (create); possibly a thin queue-slot guard in `threeway/gate.py`.

**Context (§11 Slice 2 second gate):** two candidates target `main`; the gate (sole writer) promotes one via CAS; the other's `staging_base != main.head` → REJECTED "stale" → rework re-stages as a **new** candidate (new `candidate_id`, `staging_base` = the new `main.head`) → COMPLETED. Slice 1 already implements the CAS + the "stale" REJECTED; this task proves the two-candidate serial behavior and the re-stage path, across two pairs.

- [ ] **Step 1: Define the file preamble + fixtures, then the failing/guard test.** `tests/unit/test_threeway_slice2_adversarial.py` opens with the mandatory `"""Run: …"""` docstring and carries its own inline harness (no shared conftest). Spell out every symbol the test uses — none of `MAIN`/`_stage`/`_populate`/`world_two_pairs`/`PAIR_A`/`PAIR_B`/`_head` exists yet:

```python
"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_slice2_adversarial.py -q"""
import os, subprocess, pytest
from threeway import gitcas, keys
from threeway.refstore import RefEventStore
from threeway.gate import run_gate
from threeway.loop import build_candidate_events, PAIR_A, PAIR_B

MAIN = "refs/threeway/test-main"
_SEATS = ("director", "operator", "coordinator", "director2", "operator2",
          "coordinator2", "overseer", "ci", "merge-gate")

# _env / _git: copy verbatim from test_threeway_gate_adversarial.py

def _head(r):
    return _git(r, "rev-parse", MAIN).stdout.strip()

def _populate(store, events, privs):
    for ev in events:
        store.append(ev, privs[ev.signer.split(":", 1)[0]])

def _stage(r, base, branch, cid):
    # the gate recomputes the merge with message f"threeway merge {cid}" under the
    # deterministic env and REJECTs unless it equals the attested integration_sha
    # (gate.py:110-113). _stage MUST use the IDENTICAL message + env so they match.
    tree, clean = gitcas.merge_tree(r, base, branch)
    assert clean
    return gitcas.commit_tree(r, tree, [base, branch], f"threeway merge {cid}")

@pytest.fixture()
def world_two_pairs(tmp_path, monkeypatch):
    r = tmp_path / "repo"; r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@e.st"); _git(r, "config", "user.name", "t")
    (r / "base.txt").write_text("base\n"); _git(r, "add", "-A"); _git(r, "commit", "-qm", "base")
    base = _git(r, "rev-parse", "HEAD").stdout.strip()
    _git(r, "update-ref", MAIN, base)
    # two non-conflicting feature branches off base (distinct files)
    _git(r, "checkout", "-q", "-b", "feat_a")
    (r / "a.txt").write_text("a\n"); _git(r, "add", "-A"); _git(r, "commit", "-qm", "a")
    branch_a = _git(r, "rev-parse", "HEAD").stdout.strip()
    _git(r, "checkout", "-q", base); _git(r, "checkout", "-q", "-b", "feat_b")
    (r / "b.txt").write_text("b\n"); _git(r, "add", "-A"); _git(r, "commit", "-qm", "b")
    branch_b = _git(r, "rev-parse", "HEAD").stdout.strip()
    # keys for all seats (incl. Pair B + merge-gate for the merge_completed fact)
    reg = tmp_path / "pub"; ks = tmp_path / "ks"; reg.mkdir(); ks.mkdir(); privs = {}
    for s in _SEATS:
        priv, pub = keys.generate_keypair()
        (reg / f"{s}.pub").write_text(pub + "\n")
        (ks / f"{s}.ed25519").write_text(keys.private_to_hex(priv) + "\n")
        privs[s] = priv
    monkeypatch.setenv("THREEWAY_KEYSTORE", str(ks))
    return r, base, branch_a, branch_b, reg, privs

def test_serial_queue_rejects_stale_loser_then_restage_completes(world_two_pairs):
    r, base, branch_a, branch_b, reg, privs = world_two_pairs
    store = RefEventStore(r)
    a_integ = _stage(r, base, branch_a, "c1")          # both staged off the SAME base
    b_integ = _stage(r, base, branch_b, "c2")
    _populate(store, build_candidate_events(base, branch_a, a_integ, privs,
                                            pair=PAIR_A, candidate_id="c1"), privs)
    _populate(store, build_candidate_events(base, branch_b, b_integ, privs,
                                            pair=PAIR_B, candidate_id="c2"), privs)
    r1 = run_gate("c1", store, r, registry_dir=reg, bus_id="prod", main_ref=MAIN)
    assert r1.outcome == "COMPLETED", r1.reason
    new_main = _head(r); assert new_main == a_integ
    # B is now stale (its staging_base != main.head)
    r2 = run_gate("c2", store, r, registry_dir=reg, bus_id="prod", main_ref=MAIN)
    assert r2.outcome == "REJECTED" and "stale" in r2.reason
    assert _head(r) == new_main                        # gate did NOT write on the loser
    # re-stage B onto the new main.head as a fresh candidate c2b
    b2_integ = _stage(r, new_main, branch_b, "c2b")
    _populate(store, build_candidate_events(new_main, branch_b, b2_integ, privs,
                                            pair=PAIR_B, candidate_id="c2b"), privs)
    r3 = run_gate("c2b", store, r, registry_dir=reg, bus_id="prod", main_ref=MAIN)
    assert r3.outcome == "COMPLETED", r3.reason
    assert _head(r) == b2_integ
```

- [ ] **Step 2: Run → FAIL** (any wiring gaps).
- [ ] **Step 3: Implement** — most behavior already exists (Slice-1 CAS + "stale" REJECTED); the work is the fixtures above plus, optionally, a thin queue-slot guard: before evaluating, `run_gate` acquires a lock ref `refs/threeway/queue-slot` via `cas_create_or_update_ref` and releases it after, so two concurrent gate invocations serialize. Keep it minimal — the single mechanical gate process is the real serialization point (spec §4); this test proves the re-stage semantics. **If `run_gate` keeps signing `merge_completed` with `merge-gate`,** confirm `world_two_pairs` provisions the `merge-gate` key (it does, via `_SEATS`).
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** (`test(threeway): serial merge-queue re-stages the stale loser (§11 Slice 2)`).

### Task 15: abort-on-conflict → rework (two pairs)

**Files:** Test `tests/unit/test_threeway_slice2_adversarial.py`.

- [ ] **Step 1: Failing test** — two candidates whose branches conflict on the same file; the second to stage produces a non-clean merge → `run_gate` returns REJECTED "merge not clean … ABORT/REWORK", ref unmoved. (Exercises the existing `merge_tree` clean=False path under the two-pair scenario.)
- [ ] **Step 2: Run → FAIL/Implement fixtures → Step 4: PASS.**
- [ ] **Step 5: Commit** (`test(threeway): abort-on-conflict → rework under two pairs`).

### Task 16: chunk close

- [ ] `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_*.py -q` → all PASS.
- [ ] `.venv/bin/python scripts/ci_smoke.py` → OK.

---

## Chunk 5: Slice 2 adversarial gate suite, ADR-031, and doc-sync

### Task 17: consolidate the §11 Slice 2 DoD suite + prove non-vacuous

**Files:** `tests/unit/test_threeway_slice2_adversarial.py`.

The §11 Slice 2 Definition-of-Done — every clause maps to passing, mutation-proven test(s):
- [ ] **No lost/duplicated event under a 2-process race** → Task 9, covered by BOTH `test_concurrent_append_loses_no_event_and_re_signs` (deterministic forced-CAS-loss, pins the re-sign-on-retry semantics) AND `test_genuine_two_process_race_no_loss` (real OS processes). Supporting effectively-once robustness: `test_ambiguous_push_timed_out_retry_is_idempotent` + `test_crash_after_cas_then_retry_no_double_append`.
- [ ] **Abort-on-conflict → rework** → Task 15.
- [ ] **Serial merge queue re-stages the loser when `main` advances** → Task 14.

- [ ] **Step 1:** Add a `## Slice 2 DoD coverage` docstring/table in `tests/unit/test_threeway_slice2_adversarial.py` mapping each DoD clause → its test name(s). **Note the map spans two files:** the race + idempotency tests live in `tests/unit/test_threeway_refstore.py` (Task 9); abort→rework (Task 15) and serial re-stage (Task 14) live in this file. (The Slice-1 precedent is the docstring header of `tests/unit/test_threeway_gate_adversarial.py` — imitate its style; it has no table, so this map is a small improvement, not a literal mirror.)
- [ ] **Step 2: Prove non-vacuous** — for each DoD test, confirm the single-fact mutation flips the outcome (e.g., remove the re-seq/re-sign in `RefEventStore.append` → `test_concurrent_…` must fail; this is a transient check, do not commit the mutation). Document the mutation in a comment per test.
- [ ] **Step 3:** Run `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_slice2_adversarial.py tests/unit/test_threeway_refstore.py -q` → all PASS.
- [ ] **Step 4: Commit** (`test(threeway): Slice 2 DoD coverage map + non-vacuity comments`).

### Task 18: ADR-031 + `ARCHITECTURE.md` threeway section

**Files:** Append `DECISIONS.md` (ADR-031, after ADR-030); add a `threeway/` section to `ARCHITECTURE.md`.

- [ ] **Step 1: ADR-031** — record the Slice-2 design calls: the `refs/threeway/events` one-commit-per-event topology + expected-old-OID append-CAS (re-seq + **re-sign** on retry); **ambiguous-push idempotency** (effectively-once via `idempotency_key` dedup — a retry of a fact whose ack was lost de-duplicates); per-seat cursor refs as **monotonic CAS-advanced** `seq` blobs (re-read on contention); `brief_version` added to the signed set (D-A) with the **no-persistent-events schema-reset policy** (no migration; `schema_version` is the forward lever); the legacy-mailbox migration deferred (D-B) and **tracked as Slice 2.5**; the serial merge-queue re-stage. Cross-reference ADR-030.
- [ ] **Step 2: `ARCHITECTURE.md`** — add a concise `threeway/` subsystem section (the package is currently absent — 0 mentions). Cover: the event bus (`refstore.py` / `refs/threeway/events`), the merge-gate (`gate.py`), the predicate (`predicate.py`), key trust root (`coordination/threeway/keys/`), and the mandatory `env -u GIT_INDEX_FILE` test prefix. Use same-line `symbol (path:N)` anchors so `check_doc_claims`/`ci_smoke` gates them.
- [ ] **Step 3: Verify** `.venv/bin/python scripts/ci_smoke.py` → OK (no stale same-line anchors).
- [ ] **Step 4: Commit** (`docs(threeway): ADR-031 + ARCHITECTURE.md threeway section`).

### Task 19: final whole-suite + smoke gate

- [ ] **Step 1:** `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_*.py -q` → expect the full suite green (Slice-1's 93 + the Slice-2 additions).
- [ ] **Step 2:** `.venv/bin/python scripts/ci_smoke.py` → OK.
- [ ] **Step 3:** `.venv/bin/python scripts/check_no_ceremony.py` (R1 over the threeway suite) → no new violations (the suite ships zero xfail; mutation-based non-vacuity).
- [ ] **Step 4:** Confirm `git status` shows only intended files (NOT `package.json`/`package-lock.json`).
- [ ] **Step 5:** Final whole-implementation code review (spec §11 Slice 2 gate met), then `superpowers:finishing-a-development-branch` to integrate (repo convention: direct-to-`main`, fast-forward).

---

## Spec §11 boundary note

Slice 2's gate must be **green before Slice 3 is planned**. The Slice 2 DoD is the three clauses in Task 17 (no lost/dup under race; abort→rework; serial re-stage), each mutation-proven non-vacuous. After this gate passes: **Slice 2.5 (legacy bus migration, D-B)** is authored and executed, then **Slice 3** (strategic loop, T2 other-pair `co_sign`, T3 `re_verify` + two `human_approval`). Each is planned only after the prior slice's gate is green, per the §11 boundary rule.

## Execution handoff

After this plan is reviewed: it runs via **superpowers:subagent-driven-development** — fresh **Opus** implementer per task + two-stage review (spec-compliance → code-quality), in a fresh worktree (`.worktrees/threeway-slice2`). Re-read `docs/HANDOFF-threeway-slice1-2026-06-19-executed-merged-pushed.md` for the worktree `.venv` symlink pattern and the `env -u GIT_INDEX_FILE` test discipline. Do **not** start execution without explicit approval.
