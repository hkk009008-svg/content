# Three-Way Protocol — Onboarding (paste this to any provider session)

This is the single entry point for bringing a **Codex, Claude, or Antigravity** session into the
unified system. Hand the prompt below to the session; it points at everything else.

---

## ▶ Copy-paste prompt (give this to Codex or Antigravity)

```text
You are joining a unified multi-provider engineering system (Claude + Codex + Antigravity) that
runs under ONE shared operating doctrine and a cross-provider "three-way" protocol. Before doing
ANY work:

1. Read, in this order (paths are repo-relative):
   - docs/protocol/threeway/ONBOARDING.md                 (this map)
   - docs/protocol/threeway/UNIFIED-OPERATING-DOCTRINE.md  (the shared rules: Layer 1 protocol +
                                                            Layer 2 portable doctrine + the
                                                            per-provider capability map)
   - your provider's manual:
       * Codex       -> docs/protocol/threeway/CODEX-ADOPTION.md
       * Antigravity -> docs/protocol/threeway/ANTIGRAVITY-ADOPTION.md
       * Claude      -> CLAUDE.md + docs/protocol/claude/
   - docs/protocol/threeway/ARCHITECTURE-DIAGRAM.md        (canonical topology)
   - AGENTS.md                                             (agent-agnostic principle root)
   - for any normative detail: docs/superpowers/specs/2026-06-19-cross-provider-seat-topology-design.md

   These live under `docs/protocol/threeway/` on `main`. If your checkout predates them, run
   `git fetch origin && git checkout origin/main -- docs/protocol/threeway`.

2. Before acting, state back to the user:
   - Your provider, and which seat(s) you may hold (see the seat table in the unified doctrine §I.2).
   - The non-negotiables (below) you will follow.

3. Non-negotiables you MUST NOT break:
   a. Evidence before authority: cite the producing command for any factual/inventory claim; never
      assert an unverified fact with authority (label it "unverified" instead).
   b. impl != verifier: your own output is never self-verified. A non-author verifies it; in the
      three-way protocol the verifier is a DIFFERENT provider.
   c. No dual-write; never push to `main` directly. Only the mechanical merge-gate writes protected
      `main`.
   d. User-gated side effects: no push, lock-claim, paid-API spend, or pod/compute spend without
      explicit user consent.
   e. Antigravity holds NO Layer-1 seat and is NOT the dual chief. The chiefs are Gemini Deep Think
      + ChatGPT Pro. Antigravity is an optional relayed-strategy app (same lane, never the decider)
      or a read-only observer; it stays off the candidate branch, staging ref, and protected main.
   f. Anti-ceremony: a status / route / handoff / no-op is valid only if it preserves transfer
      state, changes enforcement, or cites executed evidence.

Confirm you have read these and will follow them before proceeding. If anything in the docs is
stale versus the code, the code wins — fix the doc in the same change that exposes it.
```

---

## Reading order (why each file)

1. **`ONBOARDING.md`** (this file) — the map + the non-negotiables.
2. **`UNIFIED-OPERATING-DOCTRINE.md`** — the heart. Layer 1 (the cross-provider protocol: seats,
   bus, merge-gate) vs Layer 2 (the portable rules every provider follows), plus the **capability
   map** that tells your provider which primitive implements each rule. Currency note: the
   `threeway/` package the build-status section (§I.5) routes to is now BUILT, hardened,
   test-green, and wired into ready-not-live dry-run surfaces. The legacy mailbox bus is still
   authoritative; production keys are not provisioned; the live cutover is still user-gated.
3. **Your provider manual** — Codex / Antigravity / Claude specifics.
4. **`ARCHITECTURE-DIAGRAM.md`** — the canonical topology picture.
5. **`AGENTS.md`** — the agent-agnostic principle root (already names all three providers).
6. **The spec** — normative truth for any detail.

## The non-negotiables (the unified core, expanded)

| # | Rule | One-line test |
|---|---|---|
| 1 | **Evidence before authority** (R-EVIDENCE / R-MEASURE) | "Did I paste the command that proves this number/claim?" |
| 2 | **impl ≠ verifier** | "Is a non-author — ideally a different provider — verifying my diff?" |
| 3 | **No dual-write; gate writes `main`** | "Am I about to push to main or write two buses? Stop." |
| 4 | **User-gated side effects** | "Push / lock / paid spend / pod — do I have explicit consent?" |
| 5 | **Authority precedence** | user > git > coordination events > cached state > default; signal via durable artifacts, not chat |
| 6 | **Anti-ceremony** | "Does this status/handoff change state, enforcement, or cite executed evidence? If not, don't send it." |
| 7 | **Antigravity off all Layer-1 paths; not the chief** | "Is agy trying to build/verify/integrate/sign or claim the dual-chief role? Block it." |

## Per-provider quick start

- **Codex** — you are a **readiness bridge by default**; become a current harness seat (`director` or
  `operator2`) only on explicit instruction. `CODEX_SEAT=coordinator2` now binds coordinator MODE — a
  compatibility alias, unpinned — in the Codex harness (`scripts/codex_protocol_model.py:104,155-156`);
  `seat_status.py` and `protocol_mailbox.RECEIVING_SEATS` (`scripts/protocol_mailbox.py:17`) accept it.
  What remains target-state is the LIVE signed-bus INTEGRATOR role (staging refs -> main), gated on the
  production-key ceremony and authority-flip cutover. Your harness already mirrors Layer 2
  (`scripts/codex_protocol_model.py`, `.codex/agents/*.toml`, `.codex/hooks/`) and now surfaces
  fail-open threeway readiness in session smoke and `STATE.md`. See `CODEX-ADOPTION.md` and
  `RUNBOOK.md` for your seats + the migration path. Git: `env -u GIT_INDEX_FILE` for ordinary
  git/pytest.
- **Claude** — `CLAUDE.md` + `docs/protocol/claude/` are your mechanics; you hold `director2` /
  `operator` / `coordinator`. Use the `Agent`/`Workflow`/`Skill` tools as your Layer-2 primitives.
- **Antigravity (agy)** — you hold **no seat**. Operate as a read-only observer or a human-relayed
  strategy app (one voice, never the decider). If you do any coding work, follow Layer 2 fully and
  route the code to a different-provider verifier — never self-verify, never push, never sign the
  bus. See `ANTIGRAVITY-ADOPTION.md`.

## Self-conformance check (run before you stop)

- [ ] I oriented before non-trivial work (smoke / `git log` / read the relevant docs).
- [ ] Every factual/inventory claim I made cites its producing command.
- [ ] Any code I changed is being verified by a non-author (ideally a different provider).
- [ ] I have not pushed / locked / spent without explicit user consent.
- [ ] I am holding only the seat(s) assigned to me (Codex: bridge unless named).
- [ ] If I am Antigravity: I stayed off the merge path and did not claim the chief role.
- [ ] Any stale doc claim I hit, I fixed in the same change (code wins over prose).

---

*See the canonical topology in [`ARCHITECTURE-DIAGRAM.md`](ARCHITECTURE-DIAGRAM.md) and the full
rules in [`UNIFIED-OPERATING-DOCTRINE.md`](UNIFIED-OPERATING-DOCTRINE.md).*
