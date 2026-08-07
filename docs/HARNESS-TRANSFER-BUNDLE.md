# Harness transfer bundle

What a new repo copies to inherit this project's AI-engineering harness. Each
row names its source of best practice and its CURRENT GAP here — a gap listed
honestly beats a claimed capability that does not exist (several rows below
are aspirations, marked as such; copying this file does not copy them into
existence).

Born from the 2026-08-07 Identity Lab campaign
([RETRO-2026-08-07-identity-lab.md](RETRO-2026-08-07-identity-lab.md)):
~16 defects, none caught by a 5,535-test suite, all caught by running or
reading code on the target machine. The harness's job is to make that class of
lesson cheap the second time.

## The manifest

| Item | What it is | Practice source | Gap here today |
| --- | --- | --- | --- |
| `CLAUDE.md` | Operative router, <200 lines: only what the agent cannot infer — commands it can't guess, repo etiquette, trigger→doc routing. Truth lives in ARCHITECTURE.md, process in CLAUDE.md, and staleness is fixed in the same change that exposes it. | Anthropic best-practices; this repo's own router | This repo's is 254 lines — 27% over its own spec; trim on next revision |
| `AGENTS.md` | Cross-tool index (<150 lines) byte-consistent with CLAUDE.md — cross-family reviewer lanes (Codex/AGY) read THIS file, not CLAUDE.md. | agents.md convention | This repo's is 391 lines — 2.6× the spec; keep the two in sync manually |
| `.claude/skills/` | The skill library. Per-repo procedures + traps; portable disciplines go to `~/.claude/skills/` instead so every repo inherits them. House style: stance → do-this-first command → numbered chain → Trap N → red flags; commands name their EXECUTING HOST; no hardcoded digests. | This repo (8 committed prior + 4 new = 12); obra/superpowers pattern | Skills with `.agents/skills/` twins must be synced in the same commit — `scripts/ci_smoke.py` fails on twin drift (it caught this bundle's own edits) |
| `~/.claude/skills/` (global) | `probe-a-claim`, `prove-a-control`, `check-artifact-that-runs`, `falsify-first-debugging` — the portable verification core. | Session-proven 2026-08-07 | — |
| `.claude/settings.json` | TARGET: committed hooks + curated permission allowlist, with `"ask": ["Bash(git push*)"]` keeping a human on the push gate even under bypassPermissions. | code.claude.com/docs permissions | **GAP, three parts: (1) no `ask` key exists in ANY settings layer today, and `git push *` sits in the ALLOW lists of both the machine-global `~/.claude/settings.json` and this repo's gitignored `settings.local.json` — pushes are pre-approved, the opposite of the target; (2) the committed settings.json has hooks but NO `permissions` key at all (the allowlist lives only in the gitignored local file); (3) the six `.claude/hookify.*.local.md` guards (force-push, git-add-all, no-verify, …) are INERT — plugin disabled and files gitignored. Port them into checked-in PreToolUse hooks, then delete the hookify files.** |
| `.claude/agents/` | A fresh-context, diff-only reviewer agent definition. | Community harness repos | Exists (`agents/`); audit before copying |
| `scripts/ci_smoke.py`-equivalent | THE agent-runnable self-test a session runs first; CLAUDE.md's session-start rule points at it. | This repo (R-START) | — |
| `scripts/gen_doc_index.py`-equivalent | Committed instrument regenerating the doc indexes; `--check` mode doubles as a CI staleness guard. Numbers in nav docs come from instruments, not memory. | This repo (R-MEASURE culture) | — |
| `scripts/verify-harness.sh` | Executes every command cited in CLAUDE.md/AGENTS.md and resolves every doc pointer — attacks the "prose outlived its mechanism" class directly. | netresearch harness layers | **GAP: does not exist anywhere yet. Highest-value missing piece.** |
| Verification-debt guards | Tests that bound what the suite CANNOT see: coverage-inventory of unexecuted script surfaces, assertion-class budgets AT their measured limits, and a pin that fails loudly the day real execution coverage arrives (deleting the pin is the good news). Model: `tests/unit/test_windows_powershell_verification_debt.py`. | This repo, born from ledger #1–2 | Pattern exists for PowerShell only |
| `memory/MEMORY.md` skeleton | One-line index → one-fact files; write-as-learned, not at session end; stale memories rewritten the moment they mislead. | This user's memory convention | — |
| `docs/INDEX.md` + retro convention | Navigation index (instrument-generated stats) + a RETRO doc per campaign with the routing footer discipline: every lesson names the skill/memory/doc it now lives in. | This repo | — |
| `bootstrap/new-repo.sh` + `sync.sh` | Mechanized copy of the above into a fresh repo, and drift-sync back. | agent-guards pattern | **GAP: does not exist; Track-B-style transfers are manual.** |

## Completeness rubric (audit a harness against these eight layers)

context (CLAUDE.md/AGENTS.md/docs routing) · tools (skills, scripts) ·
planning (task lists, briefs) · verification (smoke, guards, two-control
doctrine) · memory (MEMORY.md, retros) · permissions (settings, hooks, push
gates) · observability (logs/, evidence chains, status instruments) ·
sandboxes (worktrees, scratch dirs, isolated venvs).

A transfer that copies files but skips the VERIFICATION and PERMISSIONS
columns transfers the look of the harness without its load-bearing parts.

## Transfer procedure (until bootstrap scripts exist)

1. Copy the global skills first (`~/.claude/skills/` — they follow the user,
   not the repo).
2. Copy `.claude/` (skills, settings, agents), prune repo-specific skills.
3. Copy `scripts/ci_smoke.py` and `scripts/gen_doc_index.py` equivalents;
   rewrite their repo-specific checks FIRST — a smoke that vacuously passes is
   worse than none (two-control doctrine: prove it can fail).
4. Seed `CLAUDE.md` from this repo's router structure: session-start rule,
   doc map, trigger→skill routing. Keep under 200 lines.
5. Seed `docs/INDEX.md` + an empty INCIDENT-LOG; adopt the retro convention
   at the first incident, not before.
6. Write the first memory file: what this repo is, where truth lives.
