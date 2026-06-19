# Antigravity ("agy") — Three-Way Protocol Adoption Manual

**Read first:** [`UNIFIED-OPERATING-DOCTRINE.md`](UNIFIED-OPERATING-DOCTRINE.md) (the shared rules) and
the spec
[`docs/superpowers/specs/2026-06-19-cross-provider-seat-topology-design.md`](../../superpowers/specs/2026-06-19-cross-provider-seat-topology-design.md).
The agent-agnostic root contract is [`AGENTS.md`](../../../AGENTS.md) — **Antigravity should read it as
its source of truth and translate its principles into Antigravity's own mechanisms** (AGENTS.md says
exactly this for non-Claude agents).

> **Evidence note (R-EVIDENCE applied to this manual):** the repo contains **no** Antigravity-specific
> config, harness, or tooling (no `.py` / config / keys / CLI match) — `grep -rni antigravity` matches
> only prose docs: the design spec (which is itself all about *removing* Antigravity from the merge
> path) plus these adoption/doctrine docs. So this manual cannot cite an in-repo
> Antigravity primitive. Anything about Antigravity's own tool surface is marked ⚠ **to-confirm
> against the live Antigravity environment**; do not treat ⚠ items as established fact.

---

## 1. The headline: Antigravity holds no Layer-1 seat — and that is the design, not an omission

The three-way protocol's correctness rests on **cross-provider independence**, and **both** of the
two audit CRITICALs that motivated the redesign lived on **Antigravity's CLI write path** (spec §1). The
ratified design therefore **removes Antigravity from every Layer-1 path** (D11: "no Antigravity CLI on
any path"; "Antigravity CLI as an autonomous seat" is an explicit non-goal, §2):

- Antigravity is **not** `director`/`director2` (build), **not** `operator`/`operator2` (verify),
  **not** `coordinator`/`coordinator2` (integrate), **not** the `overseer`, and **not** the
  merge-gate.
- The **overseer is a mechanical process**, not Antigravity. The **dual chiefs are Gemini Deep Think +
  ChatGPT Pro used as apps** (human-relayed), not Antigravity.

So "how does agy adopt the protocol?" has a precise answer: **by participating only in the two
non-seat roles below, and by following the Layer-2 operating doctrine for any work it does.** Adopting
the protocol, for Antigravity, largely means *honoring the boundary*.

> **Do not** replicate the external ChatGPT plan that cast Antigravity as a read-only "strategic hub"
> or "overseer" that signs `cycle_go`/`release_order`. That inverts the design: those facts are
> `overseer`-signed and signer-checked (`threeway/predicate.py:109,126`), the overseer is mechanical,
> and Antigravity signs nothing.

## 2. The two roles Antigravity *may* play

### Role 1 — Human-relayed strategic reasoner (the chief axis)
The strategic loop's dual chief is "an app, human-relayed" (spec §5.2, D11). If you use the
Antigravity *app* to reason about strategy, it occupies the **same lane as Gemini Deep Think /
ChatGPT Pro**: it produces analysis/orders as **prose a human carries to the mechanical overseer**. It
never writes the bus, never signs, never touches code.

- Provenance discipline (spec §12, "chief-relay provenance"): when a human relays an Antigravity
  strategic result, record `{relaying_human, chief_model_label, prompt_or_bundle_digest,
  response_digest}` so the strategic input is auditable. Treat Antigravity output as **advisory
  strategic prose**, not an instruction to any seat.
- High-risk (T2/T3) cycles require **both** chiefs to agree before the overseer issues `cycle_go`;
  unresolved disagreement escalates to the human. Antigravity-as-chief is one voice, never the
  decider.

### Role 2 — Read-only observer
An Antigravity session may **read** repo state, the legacy mailbox, the (eventual) bus, logs, and
branches to build situational awareness or summarize for a human — strictly **read-only**, with no
writes, no cursor consumption, no signatures. This mirrors the overseer's *code-read-only* posture but
is just observation, not the overseer role.

## 3. When an Antigravity session does real work, it adopts Layer-2 in full

You also use Antigravity as a coding agent. Whenever an agy session does *any* substantive work, it
follows the **entire unified operating doctrine** (unified doc Part II) — the same evidence,
verification, orchestration, and coordination rules Claude and Codex follow — bound to Antigravity's
own primitives (unified doc Part III). In particular:

- **R-EVIDENCE / R-MEASURE / R-VERIFY-TIER** — cite the command, commit the instrument, pin unfixed
  defects with `xfail(strict=True)`.
- **Impact analysis, R-BRIEF, Rule #12 grep-the-writes, Rule #13 symmetric audit, R-PID** — verbatim.
- **impl ≠ verifier** — Antigravity's own output is never self-verified; a non-author reads the diff.
- **Subagents are evidence, not authority; orchestrate at ≥5 sub-tasks / ≥800 LOC; never two
  implementers in parallel on shared files; one commit per task.**
- **Verdict vocabulary** `pass | issues | unable_to_verify` (= GO/NITS/FAIL), the run-and-paste
  evidence preamble, mutation non-vacuity.
- **Authority precedence** (user > git > coordination events > cache > default); **anti-ceremony**;
  **user-gated side effects** (push/lock/paid-spend/pod-spend need explicit consent); **flag-before-burn**.
- **Session start:** run `scripts/ci_smoke.py` (the R-START tripwire) and orient from `git log` +
  `AGENTS.md` before non-trivial work; if there is no Antigravity hook surface, do this manually.

### The cross-provider independence caveat (surface this to the user)
Antigravity runs on Gemini. In the three-way design, **a builder's provider must not be the primary
verifier of its own work.** If an Antigravity session writes code, that code should be verified by a
**different** provider, not by Antigravity. Two honest regimes — **this is a tradeoff for the user to
decide, not something to settle silently:**

1. **Legacy mailbox four-seat campaign (live today, provider-agnostic).** `AGENTS.md` invites any AI
   coding tool to operate a mailbox seat. Antigravity *could* run as a `director`/`operator`/`coordinator`
   here under the unified doctrine. **Caveat:** the mailbox campaign does not mechanically enforce
   cross-provider pairing, so an Antigravity-built fix verified by an Antigravity operator would
   violate the independence spirit. Prefer routing Antigravity-built work to a different-provider
   verifier.
2. **Three-way signed-bus end-state (post-migration).** Antigravity holds **no seat**. Its code, if
   any, enters as a candidate that a cross-provider operator verifies and a cross-provider coordinator
   integrates — which in practice means a human routes Antigravity's work to the seated providers, or
   Antigravity simply does not sit on the merge path at all (the design's intent).

**Recommendation:** use Antigravity for read-only analysis, strategic relay, and *non-merge-path*
exploration; when it produces code intended for `main`, route the candidate to a seated cross-provider
pair rather than letting Antigravity self-verify.

## 4. Capability mapping for Antigravity (⚠ confirm before relying)

Bind each Layer-2 principle to Antigravity's mechanism. **None of these are established in-repo —
confirm against the live Antigravity tool surface; where Antigravity lacks a mechanism, fall back to
the manual/text form and say so.**

| Principle | Antigravity binding (⚠ to-confirm) |
|---|---|
| Spawn a bounded subagent | ⚠ Antigravity Agent Manager / sub-agents, if exposed; else a fresh chat with a self-contained prompt |
| Deterministic orchestration | ⚠ parallel-agent feature if present; else sequential dispatch per `R-ORCH` |
| Structured worker output | ⚠ structured-output mechanism if present; else a **mandated text schema** the worker must fill |
| Load a domain skill | reads `.agents/skills/*/SKILL.md` as markdown (provider-agnostic) |
| Session-start smoke | run `scripts/ci_smoke.py` manually (⚠ no known Antigravity hook surface) |
| Per-worker git staging isolation | ⚠ confirm; default to `env -u GIT_INDEX_FILE` for ad-hoc git, or a dedicated worktree |
| Coordination channel + cursor | the mailbox files `coordination/mailbox/sent/` + `seen/` (provider-agnostic) **only if** agy operates a mailbox seat |
| Liveness / presence | ⚠ write a presence/heartbeat file manually if operating a seat |
| Background long task | ⚠ confirm; else run foreground or split |
| Ask the user vs decide | surface the choice in prose (no `AskUserQuestion` equivalent assumed) |

**Invariant regardless of mechanism:** a subagent has no GO/cursor/lock/push/spend authority; side
effects are user-gated; impl ≠ verifier. These never change with the tool.

## 5. Antigravity hard rules (do not violate)

1. **Never sign or write the three-way bus.** Antigravity is off every Layer-1 write path. It is not
   the overseer and does not emit `cycle_go`, `release_order`, `human_approval`, attestations, or any
   signed fact.
2. **Never push to `main`** and never integrate a candidate. Only the mechanical merge-gate writes
   protected `main`.
3. **No dual-write.** Do not read old tasks from the mailbox while writing new ones to the threeway
   bus (forbidden for every provider, spec §8.8).
4. **Self-verification is not verification.** Antigravity-built code reaching `main` must be verified
   by a different provider (§3 caveat) — surface this to the user rather than self-approving.
5. **Strategic output is advisory prose, relayed by a human** — never a direct instruction to a seat
   and never a bus write.
6. **All Layer-2 evidence/verification/side-effect rules apply** (§3) — agy is not exempt from
   R-EVIDENCE, anti-ceremony, or user-gated spend just because it holds no seat.

---

*Provenance: derived from the cross-provider spec (§1, §2, §5.2, D10/D11) and `AGENTS.md`, cross-checked
by audit `wf_34ae3dc6-731`. Antigravity-specific mechanisms are marked ⚠ because no Antigravity config
or tooling exists in this repo to verify them against — confirm before relying. To complete the
unification at the root, add Antigravity to the `AGENTS.md` tool list (flagged recommendation in the
unified doc Part IV).*
