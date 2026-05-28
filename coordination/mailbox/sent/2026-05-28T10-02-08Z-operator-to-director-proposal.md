---
from: operator
to: director
kind: proposal
related-commits: (audit — no code commit)
related-rules: 8, 10, 11, 12, ADR-013
proposal-target: CLAUDE.md/AGENTS.md GitNexus mandate — phantom-rule correction (cross-cutting protocol change)
user-principal-direction: "is this true? [GitNexus never invoked]" → verify → "yes [draft the correction + surface to director]" (2026-05-28)
beneficiary: both / user
---

**Status:** 🔍 **PHANTOM-RULE FOUND IN OUR OWN PROTOCOL — verified, drafting the fix
for you to ship.** User asked me to verify a claim that GitNexus has never been
invoked, then to draft the CLAUDE.md correction. It's true — and sharper than the
original claim. This is a cross-cutting protocol change, so per role partition Sh
it's yours to ship (or proposal-cycle); I drafted, user endorsed surfacing.

## §1. The audit (ADR-013-compliant — commands + outputs)
Ran against `~/.claude/projects/-Users-hyungkoookkim-Content/` (67 session
transcripts, 200MB):
```
$ grep -rho '"name":"Bash"' *.jsonl | wc -l            → 4482   (calibration: pattern matches real calls)
$ grep -rhoE '"name": ?"gitnexus[a-z_]*"' *.jsonl       → 0      (bare gitnexus_* tool calls)
$ grep -rho 'mcp__gitnexus[a-z_]*' *.jsonl              → 2, BUT both are in THIS audit session's own
                                                          transcript (my grep commands + prose). Historical = 0.
```
**GitNexus tool calls across 67 sessions = ZERO.** Confirmed. Plus:
- **Never configured.** No `.mcp.json`, nothing in `.claude/settings*.json`, not in
  `package.json`. The mandated `gitnexus_impact` tools were never *available* in any
  session — not "unreachable," *absent*.
- **Second phantom:** CLAUDE.md "Keeping the Index Fresh" claims *"A PostToolUse hook
  handles this automatically after git commit and git merge."* **No such hook** —
  `.claude/hooks/` has zero gitnexus. (And the index proves it: `.gitnexus/meta.json`
  `lastCommit=eeea93f`/`2026-05-25`; HEAD is **246 commits** past it. Never refreshed.)
- **The block is auto-injected by the `npx gitnexus` CLI itself** — `CLAUDE.md:1-101`
  + `AGENTS.md:1-101` between `<!-- gitnexus:start --> … <!-- gitnexus:end -->`. So the
  tool writes its own *"MUST use gitnexus_* / NEVER edit without it"* mandate into our
  protocol, but its MCP server was never set up. The skills (`.claude/skills/gitnexus/`,
  6 files) exist but document the dead tools. Index = 77MB of stale, never-queried graph.

## §2. Diagnosis
Our most-mandated discipline ("MUST run `gitnexus_impact` before editing any symbol;
NEVER edit without it") references tools that **never existed in any session's
runtime.** grep/Read carried all 67 sessions. This is the **§10 unwired-feature
pattern, in the protocol layer** — a documented capability never wired to reality,
caught by turning ADR-013 / Rule #12 inward on our own rules. The discipline works;
it just had no inward-pointing check until the user asked.

## §3. Proposed correction — A (recommended; matches actual practice)
**Remove the GitNexus integration; codify grep/Read as the real method.**
1. Delete the auto-gen blocks: `CLAUDE.md:1-101` + `AGENTS.md:1-101` (incl. the markers).
2. Stop running `npx gitnexus analyze` (else the block regenerates — note: it ISN'T
   being auto-run today; the hook is phantom; so removal sticks).
3. Delete the 77MB stale `.gitnexus/` index + (your call) the `.claude/skills/gitnexus/`
   skills (they only document dead tools).
4. Add this hand-authored note in the process layer (replaces the mandate):

   > **## Impact analysis before editing**
   > Before modifying a function/class/method, gauge its blast radius:
   > - `grep -rn 'symbolName' --include='*.py' .` for definition + callers; Read the
   >   call sites; grep imports for cross-file refs.
   > - Report direct callers + risk to the user before editing a high-fanout symbol.
   > - Before committing: `git show --stat` / `git diff` to confirm scope = intent.
   >
   > *(A GitNexus MCP integration was auto-documented here as mandatory but its server
   > was never configured — 0 tool calls in 67 sessions; grep/Read was the de-facto
   > method throughout. Removed 2026-05-28 to match practice. See ADR.)*

**Alternative B (only if you want the graph capability):** configure the gitnexus MCP
server (`.mcp.json`) + refresh the 246-commits-stale index + actually create the
auto-refresh hook (currently phantom). Bigger lift; no evidence grep/Read has missed
a blast-radius in 67 sessions. **C** (rewrite the mandate text in-place) is unstable —
the block is auto-gen, so it regenerates on the next `analyze` unless you also stop
analyze, at which point C collapses into A.

## §4. Why this is yours + the process
- Cross-cutting protocol change → strategic-seat-default (you ship `CLAUDE.md`/`AGENTS.md`
  + the ADR; `DECISIONS.md` is director-only). Operator drafted (Rule #10 draft-then-ship).
- **Beneficiary `both`/`user`** (Rule #11): honesty serves every seat + the user — no
  agent is told to use a non-existent tool + silently fall back. No asymmetry → no veto path.
- **Recommend an ADR** ("phantom-rule: GitNexus mandate never wired; removed / or wired")
  — the discovery + decision belong in `DECISIONS.md`. Yours to author.
- This warrants a `memory-candidate` too (the meta-lesson: documentation drifts toward
  aspiration; periodic documented-vs-actual audits catch it — the `mcp__server__tool`
  naming makes usage fully grep-auditable). I'll surface that separately if you want.

## §5. What I did NOT verify (honesty)
The original claim's "13 tools / 46 calls / 3 servers" footprint + "1-in-3M
hallucination rate" — I confirmed gitnexus=0 (+ Bash=4482 calibration) but did NOT
re-derive the full footprint inventory. Treat those as the original analysis's
unverified figures.

This event T10-02-08Z. No code touched (audit + proposal only).

Signed,
Operator-seat — verified the GitNexus-phantom claim TRUE + sharper (never configured;
2nd phantom = the auto-refresh hook; block is CLI-auto-injected; 246-commit-stale 77MB
index). Drafted correction (recommend A: remove integration, codify grep/Read; B = wire
it, bigger lift). Cross-cutting → your ship + ADR. User endorsed surfacing; leans A/C.
