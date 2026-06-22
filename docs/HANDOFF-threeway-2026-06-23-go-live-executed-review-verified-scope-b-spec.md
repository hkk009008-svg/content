# HANDOFF — threeway go-live EXECUTED + architecture review verified + scope-b sub-project-1 spec

**Date:** 2026-06-23
**HEAD at handoff:** `main` @ `e45f2cf6` (ADR-055, peer-landed) — verify with `git log -1` + the live oracle.
**Live oracle:** `git for-each-ref refs/threeway/` and `git ls-remote origin 'refs/threeway/*'`.

> Trust git + the oracle, not this prose. HEAD moved MANY times under this session (peers active on
> main); re-anchor before every commit/push.

## 0. TL;DR

The signed-bus **go-live was executed** (user-gated, this session): the cutover migrated 768 mailbox
events onto `refs/threeway/events`, pushed to origin; `THREEWAY_BUS_LIVE=true`; `THREEWAY_CI_KEY` set;
merge-gate runner validated. **Bus infrastructure is LIVE; the strategic-loop runtime is still UNBUILT.**
An external architecture review was **verified against the code** (most "blocking" issues were already
implemented; genuine gaps catalogued). A **design + spec for scope-b sub-project 1** (minimal operable
mechanical-seat runtime) is written and on origin. NEXT is `writing-plans` → implement it.

## 1. What landed this session (all on origin/main)

| Commit | What |
|---|---|
| `babd428e` | ADR-054 — divergence checker seated-set canonicalized vs the roster (closed the seen/-filename seat-key family; Lane-V GO). |
| `63dd556d` | ADR-054 Lane-V GO reconcile (`fixed`→`verified`) + `logs/` artifact. |
| (no commit) | **Go-live executed:** `THREEWAY_CI_KEY` secret set; cutover ran (768 carriers + 6 cursors on `refs/threeway/events`, pushed to origin); `THREEWAY_BUS_LIVE=true`; merge-gate runner validated `--run-once` (0 candidates → clean). |
| `065525ac` | Recorded go-live; reconciled stale README + UNIFIED-OPERATING-DOCTRINE §I.5 (bus LIVE vs scope-b UNBUILT, with the oracle). |
| `e45f2cf6` | ADR-055 (**peer**) — self-bootstrap `sys.path` in the activation scripts so bare `python scripts/X.py` imports `threeway`; + a bare-subprocess pin. **This pre-empts the spec's old §3.3 CI-fix work.** |
| (this handoff) | scope-b sub-project-1 spec `docs/superpowers/specs/2026-06-22-threeway-scope-b-mechanical-seat-runtime-design.md` + this handoff. |

## 2. Architecture review (2026-06-22) — verified against the code

A thorough external review (16 points) was checked claim-by-claim against the code (workflow
`wf_02eb4393-4e0`, 8 verifiers, file:line evidence). Outcome:

- **Already handled in code (the diagram was lossy, not the protocol):** B2 (integration_sha is a
  deterministic COMMIT OID, `_DET_ENV`+ADR-048; unclean merges hard-rejected), B3 (`human_approval`/
  `approver_roster` ARE first-class load-bearing kinds, key-bound distinctness), B4 (provider read from
  the overseer-signed `assignment`, not the unsigned tail), G3 (tiering diffs staging_base→**integration_sha**,
  the merged tree), and the application-layer half of G2 (unique event ids, monotonic signed seq,
  append-CAS, authority-aware equivocation resolution, malformed-blob drop-not-raise).
- **Genuine gaps → hardening track:** B1-residue (CI **attestor** independent validation — re-derive
  outcome + runner-image/test-set digest + nonce), G1 (external trust anchor for gate/policy/keys),
  G2-substrate (ref-ACL/append-only **enforcement**, retention, replication — deployment), G4 (richer
  attestation payloads), G5 (liveness/recovery; wire the **dead** `rework.py` ESCALATE breaker), I5
  (key rotation/revocation lifecycle), I3 (`required_ci` is dead config).
- **Framing carried into the spec:** B5 fault model (the independent third party is the **mechanical
  gate + overseer + CI**, not a third provider), exact T2/T3 seat enumeration (I4), the B2 note.
- **Presentation (valid):** split the one dense diagram into (1) authority/trust-boundaries and
  (2) candidate protocol; number the lifecycle; mark the untrusted-execution boundary; the "BUS LIVE"
  banner should read "transport+keys live; seat-runtime migration not started."

## 3. Scope-b decomposition + the sub-project-1 spec

Scope-b = two independent subsystems:
- **Sub-project 1 (spec written, design APPROVED): minimal operable mechanical-seat runtime.**
  `scripts/overseer_emit.py` (6 overseer facts, human-operated signing CLI), merge-gate **daemon**
  deployment (writes the protected TEST ref `refs/threeway/test-main`, NOT real main; +clean-shutdown
  +wrapper), CI signer (**already done — ADR-055**), `scripts/bootstrap_emit.py` (temporary
  interactive-seat fact shim), and an end-to-end walking-skeleton test. Operating model = human-operated
  CLIs, "minimal operable" (per-principal keys + independent attestor are fast-follows). Spec:
  `docs/superpowers/specs/2026-06-22-threeway-scope-b-mechanical-seat-runtime-design.md`.
- **Automation track (fast-follow, ABOVE sub-project 1):** the **`overseer-plan` auto-decompose layer** —
  ingests ONE structured chief decision + bus state and emits the correct ORDERED sequence of overseer
  facts (dry-run+confirm; overseer-authority facts only; idempotent), instead of the operator
  hand-issuing each `overseer_emit`. First step toward the fully-automated overseer (deferred Approach B).
  Spec §7. Its trigger logic = the overseer-action trigger table (each `PENDING "no <overseer fact>"`).
- **Sub-project 2 (separate, later):** real seat↔bus wiring (interactive seats emit/consume bus events
  instead of the mailbox); removes `bootstrap_emit.py`.
- **Hardening track (gates production sign-off):** the §2 genuine gaps above.

Spec went through one spec-review pass (general-purpose reviewer); all issues fixed (stale §3.3 vs
ADR-055; `brief_version` is an envelope field not a `brief` payload key; `subject_sha` envelope-vs-payload
notation; cite `tier.py`/`reducer.py` for `approver_roster`+`re_verify_challenge` which are absent from
`loop.py`; clean-shutdown contract; subprocess-invoked E2E). **A confirmatory second review pass is
an optional fast-follow.**

## 4. NEXT (in order)

1. **`writing-plans` — DONE** (peer-created, currently **untracked WIP**):
   `docs/superpowers/plans/2026-06-23-threeway-scope-b-mechanical-seat-runtime.md` — 10 tasks / 6 chunks
   at HEAD `84397381`, records design decisions as **ADR-056**. Commit it (it's not mine to commit) then
   execute.
2. Implement sub-project 1 (TDD, campaign discipline). NOTE: §3.3 CI work is already done (ADR-055) —
   start with `overseer_emit.py` + the daemon wrapper/clean-shutdown + `bootstrap_emit.py` + the E2E test.
3. Then the **automation track** (`overseer-plan` auto-decompose, §3 above), the **hardening track**,
   and **sub-project 2** — in whatever order the chiefs prioritize.

Also open (not blocking):
- **Seat consolidation** (answered this session): retire 4 redundant running seats (Codex `director2`,
  Codex `operator`, Claude `director`, Claude `operator2`), relabel Codex `coordinator`→`coordinator2`,
  add Claude `coordinator`. Canonical: Codex={director, operator2, coordinator2}, Claude={director2,
  operator, coordinator}. Mechanical seats (overseer/ci/merge-gate) are processes, not chat sessions.
- **Cutover artifacts uncommitted:** the 6 `coordination/mailbox/seen/*.txt` (ISO→scalar) +
  `coordination/mailbox/.migration/` rollback manifest are modified/untracked (pre-existing background).
  Decide whether to commit them for durable migration rollback.

## 5. Live state (verified)

- `refs/threeway/events` = 768 `event_sent` carriers + 6 cursors, on origin. `THREEWAY_BUS_LIVE=true`,
  `THREEWAY_CI_KEY` set. `.pub` trust root committed (`d2a50f98`); private keys in `~/.threeway/keys/`.
- The strategic loop is NOT running: no seat/harness emits or consumes bus events; the merge-gate is
  validated-not-deployed; the overseer emitter is unbuilt (= sub-project 1).
- Gate's protected ref is `refs/threeway/test-main` (Slice-1); real `refs/heads/main` is untouched by
  the gate and stays that way until the hardening track.

## 6. Sharp edges (this session)

- **HEAD moved under me repeatedly** (peers landing ADR-053 integration_sha wiring `202ff1df`, ADR-055
  `e45f2cf6`). Re-anchor (`git fetch` + ahead/behind) immediately before every commit AND every push;
  push only on `behind==0` (clean fast-forward).
- **A killed background cutover left a partial bus** (294/768, no teardown on SIGKILL) — recovered by
  `git update-ref -d refs/threeway/events` (the teardown's own action) before a clean re-run. The
  long cutover (~50 min, O(n²)) is best run by the user in a terminal, not a reapable background job.
- **Status is an artifact:** never write "live"/"executed" without `git for-each-ref refs/threeway/`.
- **Activation scripts need the repo root on sys.path** — ADR-055 made them self-bootstrap; the daemon
  wrapper must rely on that, not a fragile `PYTHONPATH`.
- **The diagram over-compressed the trust-boundary mechanics** (B2/B3/B4/G3 all "code does it, diagram
  didn't show it") — when a reviewer flags a "blocking" gap, verify against the code first.
