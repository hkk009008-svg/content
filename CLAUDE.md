<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **Content** (2083 symbols, 11937 relationships, 177 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## When Debugging

1. `gitnexus_query({query: "<error or symptom>"})` — find execution flows related to the issue
2. `gitnexus_context({name: "<suspect function>"})` — see all callers, callees, and process participation
3. `READ gitnexus://repo/Content/process/{processName}` — trace the full execution flow step by step
4. For regressions: `gitnexus_detect_changes({scope: "compare", base_ref: "main"})` — see what your branch changed

## When Refactoring

- **Renaming**: MUST use `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` first. Review the preview — graph edits are safe, text_search edits need manual review. Then run with `dry_run: false`.
- **Extracting/Splitting**: MUST run `gitnexus_context({name: "target"})` to see all incoming/outgoing refs, then `gitnexus_impact({target: "target", direction: "upstream"})` to find all external callers before moving code.
- After any refactor: run `gitnexus_detect_changes({scope: "all"})` to verify only expected files changed.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Tools Quick Reference

| Tool | When to use | Command |
|------|-------------|---------|
| `query` | Find code by concept | `gitnexus_query({query: "auth validation"})` |
| `context` | 360-degree view of one symbol | `gitnexus_context({name: "validateUser"})` |
| `impact` | Blast radius before editing | `gitnexus_impact({target: "X", direction: "upstream"})` |
| `detect_changes` | Pre-commit scope check | `gitnexus_detect_changes({scope: "staged"})` |
| `rename` | Safe multi-file rename | `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` |
| `cypher` | Custom graph queries | `gitnexus_cypher({query: "MATCH ..."})` |

## Impact Risk Levels

| Depth | Meaning | Action |
|-------|---------|--------|
| d=1 | WILL BREAK — direct callers/importers | MUST update these |
| d=2 | LIKELY AFFECTED — indirect deps | Should test |
| d=3 | MAY NEED TESTING — transitive | Test if critical path |

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/Content/context` | Codebase overview, check index freshness |
| `gitnexus://repo/Content/clusters` | All functional areas |
| `gitnexus://repo/Content/processes` | All execution flows |
| `gitnexus://repo/Content/process/{name}` | Step-by-step execution trace |

## Self-Check Before Finishing

Before completing any code modification task, verify:
1. `gitnexus_impact` was run for all modified symbols
2. No HIGH/CRITICAL risk warnings were ignored
3. `gitnexus_detect_changes()` confirms changes match expected scope
4. All d=1 (WILL BREAK) dependents were updated

## Keeping the Index Fresh

After committing code changes, the GitNexus index becomes stale. Re-run analyze to update it:

```bash
npx gitnexus analyze
```

If the index previously included embeddings, preserve them by adding `--embeddings`:

```bash
npx gitnexus analyze --embeddings
```

To check whether embeddings exist, inspect `.gitnexus/meta.json` — the `stats.embeddings` field shows the count (0 means no embeddings). **Running analyze without `--embeddings` will delete any previously generated embeddings.**

> Claude Code users: A PostToolUse hook handles this automatically after `git commit` and `git merge`.

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->

# Architecture Preamble

This repo is an AI cinema/video generation pipeline. Topic → 60-second
YouTube Short, end-to-end. Phase 6 of `refactor/architecture-cleanup`
finished the audio-domain split; the layout below is the post-refactor
state of the tree.

## Two entry points

- **`main.py:run_autonomous_pipeline`** — CLI, non-interactive. Uses
  `cinema.pipeline.CinemaPipeline` (the new driver) for the 3 migrated
  phases; legacy free-function calls for the others.
- **`web_server.py`** → **`cinema_pipeline.CinemaPipeline`** — interactive
  dashboard with pause/resume + SSE progress + operator review gates.
  Still the legacy 1,526-line orchestrator; migration is documented at
  `docs/CINEMA_PIPELINE_MIGRATION_DESIGN.md`.

## Top-level package layout

| Path | Owns |
|------|------|
| `cinema/` | Phase protocol + driver. `cinema/pipeline.py` is the iterator; `cinema/phases/*.py` are the 8 Phase wrappers. |
| `audio/` | All audio domain: `_client.py`, `srt.py`, `music.py`, `effects.py`, `voiceover.py`, `dialogue.py`, `foley.py`. |
| `llm/` | LLM domain: `ensemble.py`, `chief_director.py`, `blueprint_director.py`, `style_director.py`. |
| `identity/` | Face/identity validation. `validator.py` was the Phase 3 cycle break (no longer pulls `phase_c_vision`). |
| `config/` | `settings.py` (Settings dataclass + singleton) + `prompts/` markdown. |
| `data/` | Runtime data (SQLite, gitignored). |
| `docs/` | `REFACTOR_HANDOFF.md` is the operating manual for the refactor branch. |
| `tests/` | `tests/unit/` (12 files, pure logic) + `tests/integration/` (3 files, hit real APIs). |
| (root) | Legacy modules pending migration: `cinema_pipeline.py`, `web_server.py`, plus per-shot loop deps (character/location/continuity managers, scene_decomposer, dialogue_writer — Phase 8 candidates) and the `phase_*_*.py` shims. |

## Phase protocol contract

Every phase class in `cinema/phases/*.py` satisfies:

```python
class Phase(Protocol):
    name: str
    def run(self, ctx: PipelineContext) -> PhaseResult: ...
```

`PipelineContext` (in `cinema/context.py`) is a dataclass that *also*
implements the dict API (`__getitem__`, `__setitem__`, `get`, `update`,
`keys`, `items`, `values`, `as_dict`) — so legacy `def f(ctx: dict)`
functions keep working when passed a `PipelineContext`. This is the
bridge that lets migration proceed incrementally.

## Invariants (REFACTOR_HANDOFF.md §4)

These are mechanically verified by the smoke block in §0 of the handoff:

1. All `.py` files compile.
2. `import identity.validator` does NOT pull `phase_c_vision`.
3. `LLMEnsemble()` instantiates.
4. The 8 Phase classes satisfy the `Phase` protocol.
5. Every audio re-export is identity-equal (`audio.X.fn is phase_b_audio.fn`).
6. `main.py` imports cleanly.
7. `phase_b_audio.client` is an `ElevenLabs` instance (= `audio._client.client`).

## When you change something

Beyond the GitNexus checks above, the refactor-branch workflow expects:

- One commit per logical slice. Identity-check (`a is b`) for every
  re-export. Run the §0 smoke block before declaring a slice done.
- Don't combine concerns. A bug fix isn't a refactor isn't a feature.
- See REFACTOR_HANDOFF.md §6 for the canonical five-step slice playbook
  (read → write → re-export → verify with identity check → commit).

