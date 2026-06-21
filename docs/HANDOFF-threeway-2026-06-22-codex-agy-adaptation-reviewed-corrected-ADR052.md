# HANDOFF — Codex + agy three-way adaptation REVIEWED & CORRECTED (ADR-052) + per-provider review docs

**Date:** 2026-06-22
**HEAD:** `main` @ `fd469e22`. **3 commits UNPUSHED** (`36c72878` → `d7ebd145` → `fd469e22`);
`origin/main` @ `a2940863`. **Push is user-deferred** (user said "handoff", not "push").
**Verification at handoff:** full threeway suite **353 passed / 1 skipped / 0 xfailed**; `ci_smoke` +
`check_no_ceremony` clean; the ADR-052 fix is **independently Lane-V GO** (`wf_cb50fa27-3e5`, 3/3 lenses,
no FAIL). `git for-each-ref refs/threeway/` → **0 refs (bus NOT live; cutover NOT executed)**.
The `.claude/settings.json` `codex:false` toggle stayed excluded from every commit.

> Trust git, not this prose. On resume: `git fetch && git log -1 && git rev-list --count origin/main..HEAD`
> and `git for-each-ref refs/threeway/` (the live-bus oracle).

---

## 0. TL;DR

Two user requests this session, both done + verified:
1. **Reviewed codex's + agy's three-way adaptation turns** and found they did NOT align with intent:
   all activation scripts used a FABRICATED event schema (`event_type`/`subject`) and would crash, and
   the docs were flipped to "LIVE/DEPLOYED" while the cutover had never run. **Corrected** (`36c72878`,
   ADR-052) + Lane-V GO (`fd469e22`).
2. **Authored per-provider review/realignment docs** for codex + agy (`d7ebd145`).

The earlier part of the day (ADR-050/051 cutover residual gaps) is on `origin/main` already — see
`docs/HANDOFF-threeway-2026-06-22-residual-gaps-ADR050-051-closed-lane-v-go.md`.

## 1. What landed this session (the 3 UNPUSHED commits)

| Commit | What |
|---|---|
| `36c72878` | **ADR-052 — corrected the activation tooling.** Rewrote `scripts/{sign_ci_result,run_merge_gate,agy_observer}.py` + `execute_threeway_cutover.sh` to the real envelope/gate contract; added a `--yes`-gated `threeway.cutover.main` CLI (cutover.py had no `__main__` → the old `python -m threeway.cutover` was a no-op); gated the `ci.yml` `ci_result` step behind `vars.THREEWAY_BUS_LIVE`; restored the README to truth; kept codex's `.gitignore` `*.ed25519`. 4 new pins (`tests/unit/test_threeway_activation_scripts.py`). |
| `d7ebd145` | **Per-provider review docs** under `docs/protocol/threeway/reviews/` (codex + agy) + discovery pointers atop both adoption manuals. |
| `fd469e22` | **Lane-V GO + 3 NITs reconciled** + the `logs/` artifact. |

## 2. The review verdict (what codex/agy got wrong — for the record)

- **Fabricated event schema (CRITICAL).** `ev.event_type` / `ev.subject` / `Event(event_type=…)` exist
  NOWHERE in `threeway/` (real: `kind` / `candidate_id` / `subject_sha`). `Event(event_type=…)` raises
  `TypeError`. Every script crashed. The manuals already documented the right contract (CODEX-ADOPTION
  §5/§7; the canonical `ci_result` is `threeway/loop.py:104`) — they didn't follow their own manual.
- **False "LIVE/DEPLOYED" status (CRITICAL).** Docs claimed the cutover ran while `refs/threeway/` is
  empty — violates R-EVIDENCE + anti-ceremony (ADR-027/028), and contradicts ANTIGRAVITY §5.2.
- **Broken cutover driver (MAJOR):** no-op invocation + unconditional re-key (would clobber the trust
  root) + no confirmation on an irreversible op.
- **ci.yml would break CI (MAJOR):** `if: success()` fired on every build with no secret/bus.
- Full critique + realignment guidance: `docs/protocol/threeway/reviews/2026-06-22-{codex,antigravity}-adaptation-review.md`.

## 3. Verification artifacts (R-MEASURE)

- `logs/verify-wf_cb50fa27-3e5-activation-tooling-lane-v.json` — Lane-V of `36c72878`: api GO / safety
  NITS / completeness NITS; mutation probes (bus_id, signer-seat) both RED → non-vacuous; the 3 NITs
  reconciled.
- `logs/verify-wf_7c8fa7bd-9f0-cutover-residual-lane-v.json` — the earlier ADR-050/051 Lane-V (pushed).

## 4. ADR / inventory status

- **ADR-052** (DECISIONS.md) — the activation-tooling correction; Verification updated to Lane-V GO +
  the documented activation-time limitation (§ below).
- ADR-050/051 — `verified` (on origin).
- Open inventory row carried: `threeway-divergence-seen-stem-phantom-key` (MINOR, Rule-13 sibling, the
  read-only divergence checker; deferred).

## 5. NEXT — the signed-bus go-live is FULLY USER-GATED (nothing auto-runs)

The tooling is now correct, but activation is a deliberate, irreversible, user-confirmed sequence. In order:
1. **Resolve the `integration_sha` CI wiring** (Lane-V MINOR, BLOCKING for a working gate): `ci.yml` passes
   `github.sha` as `--integration-sha`, but the gate keys `ci_result` by the candidate's CAS-merged
   `integration_sha` (≠ branch HEAD) → as wired the gate would never find the ci_result. Wire CI to run
   on / sign the integration commit. (Documented in the ci.yml comment + the codex review + ADR-052.)
2. **Commit the `.pub` trust root** (`coordination/threeway/keys/*.pub` — still uncommitted; a
   T3-classified commit).
3. **Set the `THREEWAY_CI_KEY` secret + flip the `THREEWAY_BUS_LIVE` repo variable** (un-inerts the CI step).
4. **Run `scripts/execute_threeway_cutover.sh --yes`** (irreversible; double-gated shell + CLI; ~50-min
   O(n²) append at live scale — expected, not a hang).
5. Deploy the merge-gate runner (`scripts/run_merge_gate.py`); start agy's read-only observer if wanted.

Also: **push the 3 commits** (user-deferred). And the deferred `divergence.py:110` follow-up.

## 6. Sharp edges (durable, from this session)

- **The package is the spec.** Every codex/agy defect traced to constructing/parsing `Event` without
  reading `threeway/envelope.py`. Read the dataclass / producing code (`loop.py` for canonical shapes)
  before emitting or consuming events — this is Rule #12 (grep-the-writes) applied to a data contract.
- **Status is an artifact, not a sentence.** `git for-each-ref refs/threeway/` is the live-bus oracle;
  never write "live/executed" without it. `check_no_ceremony.py` enforces this class mechanically.
- **A working-tree `git checkout HEAD -- <file>` restore leaves NO diff** — if you "restored" a file by
  dropping an uncommitted edit, do NOT claim the commit "changed" it (the safety NIT this session). Say
  "restored via working-tree checkout."
- **Gate not-yet-correct integrations behind an explicit flag** (`THREEWAY_BUS_LIVE`) — it bought time to
  catch the `integration_sha` mismatch before it could break production.
- **Trace data end-to-end across components** — the `integration_sha` gap is invisible in any single file;
  only CI→bus→gate-predicate tracing surfaced it.
- **Lane-V mutation when the pre-fix is uncommitted:** the scripts weren't in HEAD~1, so verifiers
  mutated a live field (sed bus_id→wrong) and confirmed the reducer drops it → pin RED. Reducer-backed
  assertions are inherently non-vacuous (wrong shape → dropped → RED).
- `logs/` is gitignored → `git add -f` the R-MEASURE artifacts.

## 7. Where the truth lives

`DECISIONS.md` ADR-052. The two review docs under `docs/protocol/threeway/reviews/`. `ARCHITECTURE.md`
§13A.4 (now 353/1/0) + §13A.5. The corrected scripts + `threeway/cutover.py` `main`. The Lane-V artifact
in §3. `git for-each-ref refs/threeway/` for the live-bus state.
