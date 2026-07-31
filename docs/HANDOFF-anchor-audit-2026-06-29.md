# Handoff — file:line ANCHOR AUDIT of ARCHITECTURE.md + docs/PROGRAM-MANUAL.md

**Session:** 2026-06-28→29 · **Branch:** `claude/romantic-ellis-c4a06d`
**Landed commit:** `76e4b7e1` (doc-only, 29 anchor fixes) on top of `41dee2dd`.
**Status:** Partial. Highest-confidence drift fixed + verified. The bulk
(~231 bounds-only stale anchors) was FOUND + adversarially verified this session
but its detailed correction list was lost to scratchpad cleanup → **regenerable**
via the turnkey procedure in §6 below. Two judgement-call anchors deferred (§4).

---

## 1. Goal

Every code anchor in the two truth/intent docs — `file.py:line`,
`[file:N](file:N)`, `(file:N)`, `` `file:N` ``, bare continuation `` `:N` `` —
must point at the symbol/behavior the surrounding prose claims. Scope is
**doc-truth reconciliation only** — NO code changes.

## 2. Why this drift survives the green gate (the blindspot — read first)

`scripts/check_doc_claims.py` (run by `scripts/ci_smoke.py`; hard gate on
ARCHITECTURE.md, advisory on PROGRAM-MANUAL.md) can only **verify an anchor when
it binds a code symbol** to the cited line. Everything else it cannot judge:

| Surface | Why unverified | This session |
|---|---|---|
| **Bounds-only anchors** | No bindable symbol → checker only checks `line ≤ len(file)`, never the prose claim | 485 found (118 ARCH + 367 MANUAL); audited (§3) |
| **Inert continuation anchors** | bare `` `:N` `` whose file is inherited from a *prior* line / markdown-link / implied prose — checker leaves them `inert`, never even in `--list-unbound` | 33 found; 27 stale; **26 of them = the MANUAL:405 endpoint cell** |

`--list-unbound` enumerates the first class. The second class is invisible to the
tool and must be swept separately (script in §6.4). **A green `ci_smoke` proves
nothing about either class.** (See memory `doc_checker_same_line_blindspot`.)

## 3. What this session measured (against HEAD `41dee2dd`)

Raw anchor occurrences (grep `[A-Za-z0-9_./-]+\.[A-Za-z]+:[0-9]+`):
ARCHITECTURE.md **286**, PROGRAM-MANUAL.md **705**.

Bounds-only (`--list-unbound`): ARCH **118**, MANUAL **367** = **485**.
Audited via a 23-cluster fan-out workflow (one agent per source-file cluster +
an adversarial verify pass per cluster; 46 agents, ~2.16M tok):

- **251 OK · 231 STALE · 4 wrong-file.** Audit & adversarial-verify agreed on the
  exact corrected line for **all 231 (0 conflicts, 0 rescued-to-OK)**.
- ⚠️ The 231 detailed corrections lived only in the workflow output JSON, which
  was deleted on the session boundary. They are **runtime measurements, list not
  persisted** → regenerate (§6), do not trust any frozen numbers.

Inert sweep (33 anchors): **27 stale, 6 OK**, every correction grep-confirmed.

## 4. What LANDED in `76e4b7e1` (29 fixes — verified twice, grep-confirmed)

All re-verified by direct grep this session; `check_doc_claims` exit 0 on both docs after.

- **ARCHITECTURE.md:1332** — `` `:734` `` → `` `:746` `` (734 is a comment; the
  `dialogue_audio_in_clip` count is at `cinema_pipeline.py:746`).
- **PROGRAM-MANUAL.md:405** — all **26** `@app.route` endpoint anchors in the
  file-less compound cell, re-pointed to true decorator lines in `web_server.py`
  (every one matched `grep -n '@app.route' web_server.py`; drift +19..+106 lines).
- **PROGRAM-MANUAL.md:901** — `motion_render.py:393` → `:397` (the
  `2 <= len(unapproved) <= 6` storyboard check).
- **PROGRAM-MANUAL.md:1183** — `phase_c_ffmpeg.py:1539` → `cinema_pipeline.py:1375`
  (wrong file: `transition_duration` is read in `cinema_pipeline.py:1375`).

### Deferred (NOT touched — need judgement, not a mechanical bump)

- **ARCHITECTURE.md:1063** — prose: `` `optimizer_cache["spec"]["shot_type"]` is a
  dead store for routing; `prompt_optimizer.py:177` ``. **`optimizer_cache` does
  not exist** anywhere in `llm/prompt_optimizer.py` (the file resolves via the
  checker's basename index; line 177 is inside `_heuristic_purpose`). This is a
  **prose-level drift**, not a line bump — the likely real target is the
  `spec["shot_type"]` store (`llm/prompt_optimizer.py:300` / `:322-323`). Fix the
  PROSE + anchor together; this is a HARD-GATED doc, do not guess.
- **PROGRAM-MANUAL.md:901 `motion_render.py:364`** — lands inside the M-1 guard
  comment block (`cinema/phases/motion_render.py:355-368`); defensibly within the
  guard region (cite-the-block). Left as-is; bump to `:368` (the
  `not is_portrait(_aspect)` line) only if you want code-line precision.

## 5. What REMAINS

1. **Regenerate + land the ~231 bounds-only STALE fixes** (the bulk). Procedure §6.
   Re-run against *current* HEAD — line numbers drift every commit, so do NOT
   resurrect this session's numbers even if you find them.
2. **ARCH:1063 prose fix** (§4).
3. **Optional — the ~506 symbol-bound anchors** the checker already validates as
   fresh (def present at/near cited line). Lower value; the checker guards these.
   Only sweep if "every anchor, semantically" is required beyond def-presence.

## 6. Turnkey reproduction (no venv needed — `check_doc_claims` is pure stdlib)

Use `/opt/homebrew/bin/python3.13`. All scratchpad paths below are examples.

### 6.1 Inventory the bounds-only surface
```
python3.13 scripts/check_doc_claims.py --list-unbound ARCHITECTURE.md      > unbound_arch.txt
python3.13 scripts/check_doc_claims.py --list-unbound docs/PROGRAM-MANUAL.md > unbound_manual.txt
```
Each line: `<abs_doc>:<doc_line>  →  <target_file>:<target_line>  enclosing: <def>`.

### 6.2 Build a per-target-file clustered manifest
`build_manifest.py` (parse both dumps; group by target file; pack into ~22-anchor
clusters → `manifest.json` of `[{cluster_id, files, n_anchors, anchors:[{doc,
doc_line, target_file, target_line, enclosing, note}]}]`). Regex for a dump line:
`^\s*(?P<doc>\S+?):(?P<dl>\d+)\s+→\s+(?P<tf>\S+?):(?P<tl>\d+)\s+enclosing:\s+(?P<enc>.*?)\s*$`.

### 6.3 Fan-out audit workflow (the expensive, high-value step)
Launch `Workflow({scriptPath: anchor_audit.workflow.js, args:'{"manifestPath":"…/manifest.json","nClusters":N}'})`.
Key design (already proven this session):
- **args arrives as a STRING** — `const cfg = typeof args==='string'?JSON.parse(args):args`.
- Workflow scripts can't read files → each agent runs a Bash step-0 to fetch its
  cluster: `python3.13 -c "import json;d=json.load(open('MANIFEST'));c=[x for x in d if x['cluster_id']==ID][0];print(json.dumps(c['anchors']))"`.
- `pipeline(clusterIds, auditAgent, verifyStaleOnly)` — stage 2 re-checks ONLY the
  non-OK findings, adversarially (default-disagree). `model:'sonnet'` per the
  subagent-model directive.
- Audit agent returns schema `{findings:[{doc,doc_line,target_file,cited_line,
  claimed,verdict(OK|STALE|UNRESOLVABLE),correct_line,old_token,new_token,
  source_evidence,reason}]}`. STALE = symbol exists at a DIFFERENT line;
  UNRESOLVABLE = symbol gone / wrong file (needs prose/path fix).
- **Persist the result to a committed/durable path immediately** (`tasks/*.output`
  and scratchpad are wiped on session boundary — that's why this session's 231
  list was lost).

### 6.4 Inert continuation sweep (the tool can't see these)
`find_inert.py` — for each doc line with bare `` `:\d+` `` tokens where NO full
`` `file.ext:\d+` `` precedes the first bare token ON THE SAME LINE, the file is
inherited cross-line/implied → audit those against the inherited file (resolve the
file from prose, NOT just "nearest markdown link" — e.g. MANUAL:405's file is the
implied `web_server.py`, ARCH:1331-1332 inherit `cinema_pipeline.py` from an inline
mention, not the L1324 controller.py link).

### 6.5 Reconcile → apply → gate → commit
- `reconcile.py` — keep a STALE only when audit & verify agree on the same
  `new_token`; bucket disagreements/UNRESOLVABLE for manual review.
- **Spot-check a stratified sample yourself** before applying (integrator's
  Lane-V due diligence — don't apply agent output blind).
- `apply_fixes.py` — boundary-safe single-occurrence replace per doc line
  (trailing-digit lookahead so `foo.py:55 != foo.py:550`; refuses 0-or-多 matches).
  Handles the MANUAL:405 case of 26 edits on one line cleanly.
- Gate: `python3.13 scripts/check_doc_claims.py ARCHITECTURE.md` (exit 0 = pass)
  + `… docs/PROGRAM-MANUAL.md` (advisory).
- Commit doc-only, **explicit pathspec, `-m` before `--`** (shared index):
  `git commit -m "…" -- ARCHITECTURE.md docs/PROGRAM-MANUAL.md`.

## 7. Sharp edges hit this session

- Scratchpad + `tasks/*.output` are **session-ephemeral** → persist workflow
  output to a durable path the moment it lands.
- `Workflow` `args` is delivered as a **JSON string**, not a parsed object.
- The audit agents' "wrong file" UNRESOLVABLE verdicts over-fired: the checker
  resolves **basenames** via an index, and the docs use basenames **deliberately**
  (MANUAL:901 cites `motion_render.py` 4× as a paragraph convention). Most
  "wrong-file" calls were really **line-only** fixes with the basename kept — only
  MANUAL:1183 was a genuine wrong-file. Read the doc's local convention before
  rewriting a path.
- No `.venv` this session (torch/deepface absent) → the §15 import-smoke
  (`ci_smoke.py` §15.2) is environment-blocked, but the **doc-anchor gate runs
  standalone** on system `python3.13`. Doc-only work does not need the heavy venv.
