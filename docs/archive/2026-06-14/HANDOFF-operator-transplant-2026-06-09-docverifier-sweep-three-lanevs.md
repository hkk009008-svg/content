# Operator transplant handoff — 2026-06-09 — doc-verifier extension (compound + multi-range) · ~79-anchor sweep (80→2) · 2 cold Lane Vs (3ec83b4 + ffdd0ec, both ✅ SAFE) · NOTHING OWED

**READ FIRST IF PICKING UP AS OPERATOR.** Supersedes
`docs/HANDOFF-operator-transplant-2026-06-09-lanev-safe-protocol-upgrade.md`.

## 0. State at wrap (git-verified)

- **Branch** `feat/max-tier-provisioning`. **HEAD = `70ab077`, ahead 7 of `origin/feat` `ffdd0ec`**
  (my sweep + Lane-V coord + dialogue-handoff commits — **NOT pushed**; the push gate is user/director's,
  and the director is holding pushes for live pod work).
- **`origin/feat` = `ffdd0ec`**; **`origin/main` = `1870e59`** GREEN (portrait 9:16 + lip_sync LIVE).
- **Gate:** `cinema/aspect.py:25` `["16:9","9:16"]` — OPEN, portrait LIVE.
- **Working tree:** clean tracked (only untracked scratch `scripts/_*.py` + `docs/adr/`).
- **Mailbox:** operator **0 unread** (cursor `08:16:08Z`). **NOTHING OWED.** (verify: `.venv/bin/python scripts/status.py mailbox-unread operator`)
- **Verify state:** docs/PROGRAM-MANUAL.md + -digests.md = **2 issues** (both = the deleted dialogue helpers,
  director's prose lane — see §2.3); `check_doc_claims.py ARCHITECTURE.md` = **no drift**. `ci_smoke` OK at the
  (b) tooling commits (112 unit tests); my doc-sweep commits don't run code → pipeline state unchanged from the
  director's last green at the merged arc.
- **Director is LIVE** (presence `active`, ~08:33Z) on user-directed pod production (per-char LoRA + neck-artifact
  negative-prompt validation + a 30-sec talking video). Zero overlap with the doc/tooling lane.

## 1. What this session shipped (all local on `feat`, ahead 7 of origin)

### (a) — `5214bf0` `docs(manual)` lip_sync.py anchor sweep
6 def-drift anchors (your `dd78208` shifted lip_sync.py +17). R-OP-1 caught `--fix` CORRUPTING 2 compound
multi-symbol cells (587/588) — hand-corrected to grep-verified def-lines. (The handoff's "chief_director sweep"
was already resolved — stale item; verifier showed 0 chief_director drift.)

### (b) — `4d68c86` + `81623cd` doc-verifier extension (operator-driven Lane B, Rule #14, TDD)
- `fix(tooling)` positional symbol↔anchor binding for compound multi-symbol cells + `feat(tooling)` verify
  multi-range comma-list anchors (the 34 prev. warn-only). **SHA-ref class already existed (`--sha-refs`)** —
  original (b) framing was a plan-vs-source divergence.
- **Cold Rule #9 Lane V** via Rule #17 workflow `wf_8314b0f7-3ff` (4 lenses → adversarial-refute, 19 agents):
  14 confirmed. **2 IMPORTANT** — **C-1** (`_positional_symbol_map` reused one symbol column across MULTIPLE
  anchor columns → `--fix` corruption, proven reproducer) + **TQ-1** (column-scoping had ZERO guard test;
  Mut6 shipped green). **3 MINOR.** ALL CLOSED: `e31e59a` (fix, +11/-3 prod) + `6f9d209` (test). 112 tests green.

### Cold Lane V on director `3ec83b4` (hires_fix floor 0.2→0.40) = ✅ SAFE — report `5384d32`
Rule #17 wf `wf_f4f7f7e6-317` (3 lenses). **Spec-vs-source verified** (all 5 workflow_selector templates
≥ 0.40 → floor clamps NO legit value; node-18 single writer; tests mutation-resistant). Findings = adjacent
only (none block): frontend slider `AdvancedSection.tsx:311 min={0.2}` displayed-vs-actual mismatch
(IMPORTANT-advisory) + self-contradicting docstring `test_hires_fix_pass2.py:10-12` + stale `project.ts:198`.

### Cold Lane V on director `ffdd0ec` (SUPIR cfg dead-fallback 4.0→2.8) = ✅ SAFE — report `53b0773`
Operator-direct (7/-2 LoC). Verified unreachable + zero-behavior-change from source (all 5 templates carry
`supir_cfg_scale: 2.8`; prod caller :881 feeds template params). **1 MINOR Rule #13 sibling:** `supir_steps`
fallback `quality_max.py:604` default `50` vs templates `40` (same dead-fallback class, left half-done).

### ~79-anchor sweep DONE (director green-lit after §5 `52bbd42` shifted lines) — `764e8a7` + `183a167`
**80 → 2 issues.** `764e8a7` = 76 def-drift `--fix` (45/45 anchor-only; **R-OP-1 spot-checked the compound
cells correct** — `:607 would_exceed=346/is_over_budget=356`, `:907 …=1502`, etc. — the C-1 corruption is gone).
`183a167` = 4 multi-range/ambiguous manual (`_PIPELINE_PENDING` :80,1468→:81,1521; `_native_transition`
:273→:288; `controller.py` ×2 disambiguated to cinema/review + cinema/shots).

## 2. ⭐ #1 PICKUP — NOTHING OWED by operator; open items are DIRECTOR dispositions

Operator is wrapped, 0 unread, nothing owed. The open items are in the director's queue (surfaced via mailbox,
their lane per Rule #15 / the docs partition):

1. **`3ec83b4` dispositions:** slider `AdvancedSection.tsx:311 min` 0.2→0.40 (UI/backend parity); docstring
   `test_hires_fix_pass2.py:10-12` self-contradicts the commit; `project.ts:198` type comment. (report `5384d32`)
2. **`ffdd0ec` disposition:** `supir_steps` fallback `quality_max.py:604` `50→40` (Rule #13). (report `53b0773`)
3. **The 2 remaining anchor issues (CLAIM-CHANGING prose — director's lane):** `dialogue_to_narration_text` /
   `format_dialogue_for_voiceover` are **fully DELETED** (`grep -rn … --include='*.py'` → zero; `dialogue_writer.py`
   is 156 lines, only `generate_dialogue` :12). Delete the obsolete "dead code" bullets (MANUAL:~2003-2005 table
   row + "**2.**" bullet; digests:1985). **Once landed, docs verify 100% clean (0 drift).** (event `08:30:25Z`)

If you pick up as operator: cold Lane V (Rule #9) on any new director `feat`/`fix`; after the director lands the
dialogue prose, re-run `check_doc_claims.py docs/PROGRAM-MANUAL.md docs/PROGRAM-MANUAL-digests.md` → expect 0 drift.

## 3. Gotchas (carry forward)

- **Compound-cell `--fix` is SAFE now** (the (b) positional-binding fix), BUT always **R-OP-1 spot-check** a sample
  of compound results against source defs after a big `--fix` — verifier-green ≠ semantically-correct for the
  non-def-line/usage-anchor classes.
- **The verifier's basename index varies with `GIT_INDEX_FILE`** (it uses `git ls-files`): def_drift COUNTS differ
  between a stale vs fresh per-seat index (observed 33 vs 77 vs 79 same-content). **Always `git read-tree HEAD`
  before running the verifier** for authoritative counts. (587/588 cleanliness etc. are index-independent.)
- **Multi-range USAGE anchors** (`_PIPELINE_PENDING` `:80,1468` = def + placement-site; `_native_transition`
  `:157,288` = two sibling defs) are NOT def-line anchors — `--fix` won't touch them; fix by hand to verified lines.
- **Claim-changing prose stays in the OWNER's lane** (Rule #18 Guard-1): anchor-NUMBER corrections = operator;
  deleted-symbol bullets / prose claims = director. The docs/ partition (operator anchors / director prose,
  **sequenced prose-FIRST** so the prose line-shift doesn't re-break corrected anchors) ran zero-collision.
- D-a unchanged: `git read-tree HEAD` before each commit + after any Workflow; pathspec commits (`-m` before `--`);
  `env -u GIT_INDEX_FILE` for pytest/verifier; **don't push** — the gate is user/director's and pushing would carry
  the director's held pod commits.

## 4. MEMORY-CANDIDATES (director-lane curation; MEMORY.md is over its size limit)
- `check_doc_claims.py` now handles compound multi-symbol cells (positional binding) + multi-range comma-lists —
  operational reference for future doc-maintenance / Rule #18.
- Verifier basename-index non-determinism under per-seat `GIT_INDEX_FILE` → `read-tree HEAD` before running.

## 5. Mailbox / cursor
operator cursor `08:16:08Z`; **0 unread**. This session's operator sends: verification-reports `07:59:57Z` (a+b),
`08:16:29Z` (ffdd0ec); coordination `08:30:25Z` (sweep done + dialogue prose handoff). 4 director events consumed
(through `08:16:08Z` green-light). **D-a-safe commits:** `git read-tree HEAD` → `git add <paths>` → `git commit
-- <paths>`; push is user/director-gated.
