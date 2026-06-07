# Operator Transplant Handoff — 2026-06-08 (vision deep-diagnose + 4 tickets + portrait-P1 Lane V)

*Last verified: 2026-06-07T16:07Z. **`feat/max-tier-provisioning` = `21076f9`, 27 ahead of `main` = `origin/main` = `origin/feat` = `96a9ad1` — LOCAL/UNPUSHED.** Suite **1716 passed / 0 failed** (re-run at write), `ci_smoke OK`, tsc+build clean (last FE gate at `618a6b3`; no FE changes after). Working tree clean except untracked scratch + director's uncommitted cursor file. This handoff SUPERSEDES `HANDOFF-operator-transplant-2026-06-07-t6-shipped-merged-pushed.md`.*

## ★ READ FIRST — what this session shipped (all on local `feat`)

1. **U3 final-media conformance — designed by me, built by director, converged.**
   My user-approved spec (`b2fe065`+`e70420e`: assembly-time persist + `media`
   section) collided with a director claim while I was idle; user adjudicated
   director-finishes; their spec-conformant `803fbcb` landed; my Lane V ✅
   (5 MINOR) → director closed F1+F2 (`2f4fc50`). **U3 is public on main.**
   Full Rule #16 convergence trail in mailbox events 06:19:30Z/06:28:00Z.

2. **Vision deep-diagnose (the headline feature)** — `d974c15` + fix `a4cb076`
   + arch-sync `7f5acc4`. T6's deep path accepted `image_path`/`reference_path`
   but NEVER SENT THEM (text-only `_call_llm`; the dead `import base64` was the
   fossil). Now: take + reference attached (both providers), `visual_findings`
   key → FE panel. **Dogfood proof on cfd3f0967eb3 (identity 0.504):**
   text-only said "0.504 < 0.65"; vision said "generated MALE figure vs FEMALE
   reference… not a detection false negative" in 8.0s. Calibration datapoint:
   ArcFace 0.504 can mean *different gender*. Built via Rule #17 read-only
   analysis workflow (run `wf_5349a15d-cff`, 5 agents — found the 10MB limit,
   the extensions-lie, the 1568px policy) → Lane B implementer → 2 cold
   reviews (1 IMPORTANT: label/attachment desync → encode-once-at-evaluate)
   → re-review ✅ → live re-dogfood.

3. **All 4 follow-up tickets closed in sequence (user: "do all 1~4")**:
   - `618a6b3` — **model bump** `claude-sonnet-4-20250514` (⏰ retires
     **2026-06-15**) → `claude-sonnet-4-6` across ALL 4 production defaults
     (chief_director, CinemaDirector, ensemble pool+judge, phase_c_vision) +
     pricing row (old kept for history) + FE dropdown + docs. Verified via
     claude-api skill: same $3/$15, vision parity, pure ID swap.
   - `d388a63` — **timeout=120.0** on 11 Anthropic/OpenAI constructor sites
     (Rule #13 audit). `sora_native` exempt (video downloads).
   - `3a47ac0` — **phase_c_vision encoding fix**: 3 vision validators adopt
     shared `llm/image_encoding.py::encode_image_for_llm` (promoted from
     chief_director; JPEG q90, 1568px cap, MIME by construction). Closes
     oversize (20.28MB b64 > 10MB anthropic limit) + extensions-lie classes.
   - `fe2aa47` — **multi-character references**: deep diagnosis attaches ALL
     in-frame chars' refs, per-character labels, `reference_paths` supersedes
     legacy param; controller switched to shot-level `characters_in_frame`
     (old code misattributed scene-chars[0]).
   - `5e042b0` — coalesced-review close (3 IMPORTANT): **Gemini clients**
     missed by my audit → `HttpOptions(timeout=120_000)` (**MILLISECONDS** —
     verified in google-genai 2.6.0 source; veo_native exempt, video lane);
     **deep-gate capability restore** (character-less shots get refs-less deep
     diagnosis — style/coherence mutations still valuable); ARCHITECTURE sync.

4. **Coalesced Lane V on director's portrait Phase-1 → ✅ READY TO SHIP, 0
   blocking** (report event 16:45:00Z, commit `21076f9`). Crucial context:
   **the director's own final cross-cutting review never ran** (user called
   handoff) — mine is the only independent pass before merge. 16:9
   byte-identical verified cold; Rule #13 gate symmetry re-audited; the
   latent persisted-9:16 hazard **empirically disproven (0 of 16 projects)**.
   8 advisory findings w/ Rule #15 dispositions: F1 dead `EXPECTED_RESOLUTION`
   const; F2 stale 1920x1080 comments (cinema_pipeline.py:1297/:1338); I1
   resolver honors unsupported 9:16 (record 0/16 in merge body → (c)); I2
   assembly-wiring untested (Phase-2); M3 EditorialShell:313 wrong fallback
   constant; M4 PUT non-dict 500 (pre-existing); M5 duplicated default; M6
   mutable list.

## Where the program stands

- **main == origin/main == origin/feat == `96a9ad1`** (U3 + everything before).
- **feat == `21076f9` == 27 ahead, UNPUSHED.** Carries: director's portrait
  Phase-1 (6 feat SHAs `215fdf0 e4bd575 3d8c8e0 7672cbc 4778c6a 43127cc` +
  arch-sync `2471b71`) + my vision deep-diagnose + tickets 1-4 + both seats'
  handoffs + coord events. **Both workstreams independently reviewed; merge
  is USER-GATED** (FF clean — main is ancestor).
- Suite **1716/0**; ci_smoke OK.
- Director: WRAPPED (handoff `docs/HANDOFF-director-transplant-2026-06-08-portrait-phase1-impl.md`);
  their unread queue: my 15:55Z (tickets closed) + 16:45Z (P1 Lane V report).
- Mailbox cursor (operator): `2026-06-07T15:16:52Z` — **0 unread** at write.

## NEXT — operator-claimable, priority order

1. **v5.8 hook-fix draft** (director CONCURRED, operator drafts per partition):
   `.claude/hooks/update-state.sh` auto-refreshes the seat's `GIT_INDEX_FILE`
   index on its per-tool-call HEAD-move detection. Kills the 4×-per-session
   phantom-deletion storms (see Gotchas). Implementation is Rule #14-eligible
   (single file, canonical pattern = the hook's existing HEAD detection);
   the protocol TEXT goes through proposal cycle (operator drafts, director
   ships).
2. **F1+F2+M3 polish bundle** (3 one-liners from P1 Lane V; user-direction or
   director's Rule #15 choice — don't claim unilaterally, dispositions sent).
3. **U3 dashboard dogfood**: load the Capability dashboard for a project with
   a fresh final mp4 — the −15.09 LUFS project's tile must show RED after its
   next reassembly (assembly-time architecture: old exports stay greyed).
4. **T1 Phase-B live LoRA-gate calibration** (GPU pod, spend-gated; pod
   `07ed667` was 404 — verify Novita first).
5. **Deferred minors** (ticket candidates, none urgent): Gemini encode→decode
   round-trip; `identity_result` still single-char (scene chars[0]) while refs
   are now in-frame — divergence possible; `creative_llm` persisted-old-model-id
   read-time migration (404s after 6/15 degrade via fallback); no-retry test
   for openai extraction path.

## NOT operator (director-lane / user-gated)

- **Merge/push** — user-gated. Both workstreams are review-backed; FF clean.
- Director's queued cold Lane V on my vision commits (`8ad67ed..a4cb076`) +
  processing my two events; portrait **Phase 2/3 specs** (their lane; provider
  matrix: only Veo native-9:16 today); **memory curation** (this handoff's
  pointer + the session's memory-candidates are director-seat calls).

## Gotchas / precedents (carry forward)

- ⚠️ **LAUNCH WITH `CLAUDE_SEAT=operator`** (presence hook; #1 lesson of 06-07).
- ⚠️ **D-a stale-index storms**: every batch of PEER commits stales YOUR
  `index-operator` → `git status` shows phantom mass-deletions (peaked at
  1015 lines + once 600 skip-worktree bits this session). Files are FINE.
  Fix: `git reset --quiet HEAD` (worktree untouched); if skip-worktree bits
  appear (`git ls-files -v | grep '^S'`), `rm "$GIT_INDEX_FILE"` then reset.
  Director hit it too (254 files). The v5.8 hook fix (NEXT #1) retires this.
- **Suite runs**: `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit -q`
  (doc-claim temp-repo tests false-fail under D-a otherwise).
- **Shared tree**: explicit pathspec commits; `-m` flags BEFORE `--`; `git add`
  new files first (pathspec commit alone fails on untracked).
- **google-genai timeouts are MILLISECONDS** (`HttpOptions(timeout=120_000)`);
  anthropic/openai SDKs take seconds floats. Don't mix up.
- **Stat-cache false-clean**: same-length content swap in the same second can
  make git think a file is unchanged (hit on the cursor file; `git add` force-
  refreshes).
- **Vision surface (for follow-ups)**: shared encoder `llm/image_encoding.py::
  encode_image_for_llm`; deep path `cinema/shots/controller.py:~1930` (gate:
  deep_enabled + image exists; refs from `characters_in_frame`); `_call_llm`
  takes `image_b64s` (pre-encoded; encode-at-evaluate keeps labels synced).
- **claude-api skill before writing model ids/pricing** — it caught that the
  bump needed zero breaking-change edits and confirmed the exact id.

## Verification at write (ADR-013)
```
$ date -u                                    → 2026-06-07T16:07:30Z (06-08 JST)
$ git rev-parse --short HEAD main origin/main origin/feat/max-tier-provisioning
                                             → 21076f9 / 96a9ad1 / 96a9ad1 / 96a9ad1
$ git rev-list --count main..HEAD            → 27
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit -q
                                             → 1716 passed, 2 warnings
$ .venv/bin/python scripts/ci_smoke.py       → OK
$ cat coordination/mailbox/seen/operator.txt → 2026-06-07T15:16:52Z (== latest to-operator → 0 unread)
$ git status --short | grep -v '^??'         → only coordination/mailbox/seen/director.txt (director's own uncommitted cursor)
```
