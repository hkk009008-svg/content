# Operator Handoff — Context Transplant 2026-05-27 cycle 16 entry (CLOSE)

**From:** Operator-seat (cycle-16 entry close; Tier-A-pre-flight + Tier-B-Korean-probe + 2-CRITICAL+1-IMPORTANT-closed + 3-inline-fixes-shipped + director-parallel-Lane-V cycle)
**To:** Next operator-seat instance, fresh chat
**Companion docs:**
- [HANDOFF-operator-transplant-2026-05-27-cycle15.md](HANDOFF-operator-transplant-2026-05-27-cycle15.md) (`120d087` — cycle-15 close; the doc THIS session picked up from)
- [HANDOFF-director-transplant-2026-05-27-cycle15.md](HANDOFF-director-transplant-2026-05-27-cycle15.md) (`dd2e84e` — director cycle-15 close)
- [HANDOFF-execution-begin-2026-05-27.md](HANDOFF-execution-begin-2026-05-27.md) (`0f6527f` — execution-kickoff guide; first-mile testing protocol)
- [BRIEF-comprehensive-test-2026-05-27.md](BRIEF-comprehensive-test-2026-05-27.md) at v1.0 SHIP (`0f6527f`)
- [docs/test-cells/A-2026-05-27T19-23-47Z.md](test-cells/A-2026-05-27T19-23-47Z.md) — Tier A operator artifact (`5425e5e`)
- [docs/test-cells/A-2026-05-27T19-23-47Z-director.md](test-cells/A-2026-05-27T19-23-47Z-director.md) — Tier A director cold-context artifact (`710f0b4`)
- [docs/test-cells/B-2026-05-27T19-36-10Z.md](test-cells/B-2026-05-27T19-36-10Z.md) — Tier B operator artifact (`a42a6af`)
- [docs/test-cells/B-validation-2026-05-27T20-10-21Z.md](test-cells/B-validation-2026-05-27T20-10-21Z.md) — Tier B post-fix validation artifact (`24d39f0`)
- [PROTOCOL-RULES-LOG.md](PROTOCOL-RULES-LOG.md) at `1af3528` (579 LoC; 15 rules + 5 N=1 candidates; **unchanged in cycle-16-entry**)
- [CLAUDE.md](../CLAUDE.md) `# Director-Operator Concurrent Operation` — full protocol Rules #1-#15

---

## TL;DR (90 seconds)

**Cycle 16 entry = pre-flight-execution + Tier-A-PASS + Tier-B-Korean-probe + 2-CRITICAL+1-IMPORTANT-closed-inline + director-parallel-Lane-V cycle.** Started from cycle-15 close at `120d087` (operator) + `dd2e84e` (director) + `0f6527f` (brief v1.0 SHIP + execution-begin handoff) + `0ecda24` (operator A6 settings.py fix for `override=True` on load_dotenv). **22 commits between cycle-15 close and this handoff** (operator: 14 + director: 8). User-principal directive at session start: **"begin all testing"** — broad execution authorization triggering Tier A + Tier B execution.

**Headline arcs:**

1. **Tier A pre-flight A1-A9 PASS** (operator-side `5425e5e` + director cold-context parallel `710f0b4`; both seats green). **3 findings filed:** M-A2.3 (`npm run build` skipped, deferrable), M-A3.1 (brief §3 stale baseline 866 → actual 925; Lane D candidate), I-A6.1 (`CINEMA_BUDGET_LIMIT_USD` env-var unbound; per-project `budget_limit_usd: 50.0` Option (a) chosen for Tier B). Director convergence verification-report at `babcb25`. **Tier A all-green criterion met both seats. Tier B unblocked.**

2. **Tier B Korean dialogue probe COMPLETE** (operator drove; project `7cddd0c59f6d`; 3 pipeline runs; cumulative ~$2.10-2.65 of Q6 $3-7 envelope). User chose **Korean dialogue probe** variant + I-A6.1 **Option (a)** via AskUserQuestion. **2 CRITICAL + 1 IMPORTANT surfaced and ALL CLOSED inline:**
   - **C-B1 CRITICAL** — ComfyUI UNETLoader empty list → FAL fallback. Closed via **director's `eb6af85`** (setup_runpod.sh symlink) + **user-principal pod-side one-liner** (real-time symlink apply) + **director's A9-redux** verification (UNETLoader now lists `FLUX1/flux1-dev-fp8.safetensors`). Both layers verified GREEN.
   - **C-B2 CRITICAL** — Tri-mix audio assembly fails for Kling Native (silent video). Closed via operator's **`b11edd4`** (`_concat_dialogue_track` helper + dynamic filtergraph muxing standalone dialogue when stitched lacks audio). Lane V flagged my artifact's root-cause framing was imprecise (it's "Kling silent video" not "filtergraph construction bug" — but fix is correct regardless).
   - **I-B1 IMPORTANT** — Cartesia Korean routing not triggered. Closed two-layer via operator's **`972e239`** (resolver fix consulting `settings_obj.language_pref`) + **`2398314`** (dispatcher fix reading both `language` and `language_pref` keys). Re-run validated `[CARTESIA]` marker fires.
   - **M-B3 MINOR** — amix `duration=first` clamps audio to dialogue length. Closed via **`ee70fd1`** v1 (`duration=longest` for standalone-dialogue path) + **`e867aac`** v2 refinement (`-shortest` flag pair; ffprobe-validated 5.1s video + 5.1s audio + 5.1s format ✅).

3. **2 new findings filed during validation re-run:**
   - **I-B3 IMPORTANT** — Cartesia API 400 (pipeline passed ElevenLabs voice_id namespace to Cartesia). Graceful fallback to ElevenLabs works. Operator-preferred Tier C disposition: **NO ACTION** (fallback works; cycle-16+ Cartesia voice_id work is own concern).
   - **(advisory from director Lane V on `a42a6af`)** — operator's artifact framing for C-B2 said "no input mapping declared" (misleading; the `-i stitched` flag IS present, the input had no audio stream). Fix is correct regardless; framing precision filed as cycle-16+ docs(arch-sync) candidate. Plus separate Lane V advisory: `972e239` resolver fix lacks unit test coverage for new dict-shape `settings_obj` path (~7-LoC test to add in cleanup pass).

4. **Director-side parallel work this cycle:**
   - Cold-context Tier A parallel observation per Rule #9 (`710f0b4`); convergence verification-report (`babcb25`) confirmed all 9 cells observed identically both seats
   - Tier B silent-accept on operator dispatch-claim (`3a4abb8`) with 2 flags (staleness in operator §"Coordination" #1; P-KEYFRAME PREDICTION calibration for no-PuLID variant)
   - **Cold-context Lane V dispatch on `a42a6af`** (subagent `ab832c7`) returned diagnoses sound + 2 minor advisory findings
   - **C-B1 setup_runpod.sh fix `eb6af85`** with pod-side one-liner for user-principal immediate-apply
   - **Tier B closure verification-report `f15aa8e`** with comprehensive Lane V findings + C-B1 A9-redux GREEN + Tier C readiness assessment

5. **Tier C SURFACE-DECISION pending user-principal**. AskUserQuestion surfaced 3 scope questions (PuLID ref photo source / P-PERFORMANCE inclusion / reel scope). **User dismissed all three** with directive "do not proceed; wait for next instruction." Operator standby; no Tier C dispatch-claim sent. Tier C tasks unchanged (#5 pending). Next user direction may be: provide Tier C spec, pause for review, pivot to Tier D, or ship findings summary.

- **Cumulative cycle-16-entry telemetry:** 1 Lane V dispatch (director cold-context cold-cycle review on `a42a6af`; ~5min wall-clock; cold-context shape); ~50-80k subagent tokens (director-side Lane V only; operator did NOT dispatch subagents this cycle — all operator work was main-context Edit/Bash). **0 hallucinations.** **3 CRITICAL+IMPORTANT closed; 2 new IMPORTANT/MINOR filed; 4 MINOR carry-forward.**

- **Substrate state post-cycle-16-entry:** **15 rules codified + 5 N=1 candidates filed** (Rules #1-#15; Candidates #1, #3, #4, #5, #8). **UNCHANGED from cycle-15 close.** No new codifications cycle-16-entry; no new candidates filed (cycle-16-entry catches were closed via Rule #15 disposition shape OR Lane V advisory).

- **Branch state at this refresh:** HEAD `9c9c1b2` (operator's Tier B closure ack + cursor T19:34:00Z → T20:13:38Z); branch **0 ahead of `origin/main`** (all pushed). Working tree: **clean** (modulo this handoff file pending add+commit). **Mailbox cursor for me (operator.txt):** `2026-05-27T20:13:38Z` (consumed director's `f15aa8e` T20:13:38Z verification-report).

---

## How to resume (cold-start checklist for next operator)

⚠️ **CANDIDATE #8 RECENCY discipline applies** (carried from cycle-15 close). Cycle-16-entry observed 3 N=1 distinct shape instances (concurrent-claim race + stale-mailbox-content assertion + pre-write re-verify gap). None at N=2 emergence. Cycle-16+ watch for second instances of any shape.

```bash
# 0. Cold-read STATE.md (machine truth; auto-maintained by hook).
cat STATE.md

# 0a. Rule #8 awareness gate: if STATE.md says `unread mailbox: operator=N≥1`,
#     surface to user in first user-facing turn:
#       "Mailbox has N unread event(s) for operator; processing now per Rule #8."

# 0b. CANDIDATE #8 RECENCY DISCIPLINE: if substantive Write happens >30 min
#     after cold-start, RE-RUN these checks immediately before the Write:
ls coordination/mailbox/sent/ | tail -10
git log --oneline -5

# 1. Manual verify (when STATE.md is stale — observed stale 1x cycle-16-entry)
.venv/bin/python scripts/ci_smoke.py            # expect: OK
.venv/bin/python -m pytest tests/unit/ -q --tb=no | tail -1  # expect: 925 passed, 3 skipped
git log --oneline -5
git rev-list --count origin/main..HEAD          # expect: 0 (modulo this handoff)

# 2. Mailbox + cursor
ls coordination/mailbox/sent/ | tail -10
cat coordination/mailbox/seen/operator.txt      # last consumed = T20:13:38Z

# 3. Read in this order
#    a. STATE.md (you already did)
#    b. coordination/mailbox/sent/ — process unread events for operator role
#    c. ARCHITECTURE.md §15 smoke (if STATE.md says FAIL or unknown)
#    d. THIS FILE (you're reading it)
#    e. HANDOFF-execution-begin-2026-05-27.md (execution-kickoff guide; still
#       relevant for Tier C/D Step 1-6 sequencing if user resumes execution)
#    f. BRIEF-comprehensive-test-2026-05-27.md at v1.0 SHIP
#    g. docs/test-cells/A-*.md + B-*.md (Tier A + Tier B artifacts)
#    h. coordination/mailbox/sent/2026-05-27T20-13-38Z-director-to-operator-verification-report.md
#       (director's Tier B comprehensive closure verification-report)
#    i. CLAUDE.md "# Director-Operator Concurrent Operation" (Rules #1-#15 unchanged)
#    j. PROTOCOL-RULES-LOG.md (rule registry + 5 N=1 candidates; UNCHANGED cycle-16-entry)
#    k. HANDOFF-operator-transplant-2026-05-27-cycle15.md (cycle-15 close substrate)
#    l. HANDOFF-director-transplant-2026-05-27-cycle15.md (director cycle-15 close)

# 4. Pre-Write / pre-commit Rule #4 + #7 + Candidate #8 gates apply to any
#    state-asserting commit. Re-run git log --oneline -5 AND check
#    coordination/mailbox/sent/ before commit.

# 5. Check pod state if user may resume execution
POD_URL=$(grep '^COMFYUI_SERVER_URL=' .env | cut -d= -f2)
curl -sI "$POD_URL/object_info" --max-time 10 | head -1  # expect HTTP/2 200
# C-B1 A9-redux: verify UNETLoader serves FLUX (confirms director's symlink fix is durable)
curl -sf "$POD_URL/object_info/UNETLoader" | jq -r '.UNETLoader.input.required.unet_name[0][]'
# expect: FLUX1/flux1-dev-fp8.safetensors (present)
```

---

## Cycle-16-entry commit ledger

**21 commits + this handoff = 22** between cycle-15 close at `fb25677` and this handoff. **14 operator + 8 director.**

| # | SHA | Type | By | Summary |
|---|---|---|---|---|
| 1 | `0ecda24` | fix(settings) | operator | A6 closure: load_dotenv `override=True` so .env wins over shell environment |
| 2 | `5fd2e58` | coord(mailbox) | director | Cycle-16 entry ack + cursor T08:35Z → T10:56:16Z + receipt of `0ecda24` |
| 3 | `f0e5c0c` | coord(mailbox) | operator | Cycle-16 entry ack + cursor T10:46:03Z → T19:13:28Z + standby |
| 4 | `3cc7a84` | coord(mailbox) | operator | Tier A dispatch-claim (user-principal "begin all testing" authorization received) |
| 5 | `e523a4e` | coord(mailbox) | director | Race-ack on operator's Tier A dispatch-claim + parallel cold-context observation announce |
| 6 | `5425e5e` | test(cell) | operator | Tier A PASS-WITH-2-MINOR-1-IMPORTANT — A1-A9 ($0); single tier-end artifact |
| 7 | `1dcc562` | coord(mailbox) | operator | Tier A tier-end verification-report + cursor T19:13:28Z → T19:21:18Z |
| 8 | `710f0b4` | test(cell) | director | Tier A PASS (director cold-context parallel) — supplementary independent artifact |
| 9 | `babcb25` | coord(mailbox) | director | Tier A convergence verification-report + cursor T19:19:51Z → T19:26:18Z |
| 10 | `2426f59` | coord(mailbox) | operator | Tier B dispatch-claim — Korean dialogue probe + I-A6.1 Option (a) per-project budget |
| 11 | `3a4abb8` | coord(mailbox) | director | Tier B silent-accept on `2426f59` + 2 informational flags (staleness + P-KEYFRAME calibration) |
| 12 | `972e239` | fix(audio) | operator | Tier B I-B1 (resolver) — _resolve_tts_provider consults settings_obj.language_pref |
| 13 | `a42a6af` | test(cell) | operator | Tier B PASS-WITH-2-CRITICAL-1-IMPORTANT-2-MINOR — Korean dialogue probe ($1.00-1.58) |
| 14 | `2398314` | fix(audio) | operator | Tier B I-B1 (dispatcher) — read both `language` and `language_pref` keys |
| 15 | `b11edd4` | fix(audio) | operator | Tier B C-B2 — mux standalone dialogue track when motion engine doesn't embed audio (Kling Native etc) |
| 16 | `eb6af85` | fix(runpod-setup) | director | Tier B C-B1 — symlink FLUX into diffusion_models/ for UNETLoader |
| 17 | `24d39f0` | test(cell) | operator | B-validation VALIDATED — I-B1 + C-B2 fixes confirmed; 2 new findings filed (I-B3 + M-B3) |
| 18 | `ee70fd1` | fix(audio) | operator | Tier B M-B3 v1 — amix duration=longest for standalone-dialogue path |
| 19 | `f15aa8e` | coord(mailbox) | director | Tier B verification-report — Lane V findings + C-B1 A9-redux GREEN + Tier C readiness |
| 20 | `e867aac` | fix(audio) | operator | Tier B M-B3 v2 — pair amix duration=longest with -shortest output flag (ffprobe 5.1/5.1/5.1 ✅) |
| 21 | `9c9c1b2` | coord(mailbox) | operator | Tier B closure ack + cursor T19:34:00Z → T20:13:38Z + standby for Tier C direction |
| THIS COMMIT | docs(handoff) | operator | **Operator-seat cycle-16-entry transplant** (this doc) |

**Total cycle-16-entry to this handoff:** 21 commits + 1 transplant handoff = 22. Branch state: 0 ahead of `origin/main`.

---

## What's pending for next operator

### Immediate (next operator session)

1. **No pending unread events** at this handoff — operator cursor at `2026-05-27T20:13:38Z` (consumed director's `f15aa8e` T20:13:38Z verification-report).

2. **Tier C decision was DISMISSED by user-principal** — user signaled "do not proceed; wait for next instruction" to all 3 Tier C scope questions (photo source / P-PERFORMANCE / reel scope). Operator MUST NOT auto-resume Tier C without user direction. Possible next directions:
   - User provides Tier C project spec → operator dispatches Tier C
   - User pivots (e.g., skip C, go to D)
   - User reviews findings + decides cycle-16 stops here, defers to cycle-17
   - User asks for findings summary OR cycle-16 entry close handoff

3. **Standard Rule #4 + #7 hygiene** on any state-asserting commit. **Candidate #8 RECENCY discipline** — re-`ls` mailbox immediately before substantive Writes spanning >30 min from cold-start gate.

### Mid-term (cycle-16 entry close OR cycle-17 entry — when user direction resumes)

**If user resumes Tier C execution:**

- **Prerequisites all satisfied** (per director's `f15aa8e` Tier C readiness assessment):
  - ✅ PuLID-FLUX path functional (C-B1 closed; UNETLoader serves FLUX per A9-redux)
  - ✅ Tri-mix audio assembly functional (C-B2 closed; `b11edd4`)
  - ✅ Korean TTS routing functional both layers (I-B1 closed; `972e239` + `2398314`)
  - ✅ Audio-video duration parity (M-B3 closed; `e867aac`)
  - ✅ Cost envelope ~$2.10-2.65 cumulative (Q6 $3-7 well-preserved; $48 headroom for C+D)
- **Scope decisions surfaced (still open):**
  - Character ref photo source — operator preferred (b) FLUX-generate base face for self-contained test
  - P-PERFORMANCE — operator preferred SKIP (no driving video needed; defer to follow-up cell)
  - Reel scope — operator preferred default (1 scene, 3-5 shots, ~$8-12)
- **Tier C blockers if execution resumes:**
  - Same Korean Probe project (`7cddd0c59f6d`) is in clean state for extension (BGM + foley + style cached; can add scenes/shots)
  - OR fresh Tier C project for clean test (per Q6 default)

**Carry-forward Tier C MINOR advisory backlog** (filed cycle-16-entry; not blocking):
- **C-B2 root-cause precision** (Lane V advisory; `a42a6af` framing): one-line doc note at `ARCHITECTURE.md §12` OR amend artifact at next Lane D opportunity
- **I-B1 resolver fix test coverage** (Lane V advisory; `972e239`): add unit test for dict-shape `settings_obj` path (~7-LoC; mechanical)
- **I-B2 vibe_prompts coverage** ("contemplative" missing from `audio/music.py:249-289` dict; falls through to generic template): Lane D candidate — add OR document
- **I-B3 Cartesia voice_id namespace mismatch** (Cartesia API 400 from ElevenLabs voice_id pass-through): per-character `cartesia_voice_id` schema field OR `_default_cartesia_voice_for_language(lang)` helper
- **M-B1 SCREENING gate env-var-only control** (project-level `screening_stage_enabled` ignored): add project-setting fallback in `cinema/screening.py:_screening_stage_enabled` OR document env-var-only behavior in ARCHITECTURE.md §7.7.3
- **M-B2 cost_log incomplete** (`cost_log` tracks only keyframe + motion; LLM/BGM/Foley/TTS not recorded): tracking-completeness sweep before Tier C/D budget enforcement matters more

### Long-term (cycle-17+ backlog)

- **Comprehensive test EXECUTION continuation** (per user-§9 Q5/Q9 + execution-begin handoff Step 5-6):
  - Tier C full reel (~$8-15 estimated; gated on user direction)
  - Tier D parameter sweep (~$1-5 estimated; optional)
  - Final findings report (`docs/REPORT-comprehensive-test-2026-05-2X.md`)

- **C-B2 architectural follow-up** (NEW post-cycle-16-entry candidate):
  - Per-engine audio-embedding capability matrix in `ARCHITECTURE.md §12`
  - Sentinel test for stitched-has-no-audio case
  - Audio architecture documentation refresh to reflect Kling Native (and other image2video engines) requiring standalone-dialogue path

- **Carry-forward advisories (post cycle-15 close + cycle-16-entry closures)**:
  - **H1** dead `approved_take_id` manifest field — DEFER, evaluate post-S21 (cycle-9 carry; unchanged)
  - **H2** collection-walk-order divergence — LIKELY MOOT post-cycle-13 (carry; may retire at cycle-17+)
  - **H4** test-fixture direct-insert pattern — FULLY ADDRESSED at cycle-13 `6f8be5d`; durable
  - **H5** sync `os.path.exists` per shot — TRACK in cycle-17+ telemetry (carry)
  - **H7** inline `fontVariationSettings` duplication — DEFER (cycle-10 carry)
  - **CONCURRENCY FLAKE** `test_four_concurrent_generate_only_one_wins` — CLOSED at `dbcde8b` (cycle-14 entry); not regressed cycle-16-entry

---

## Findings catalog (cycle-16-entry)

### Tier A (`5425e5e` + `710f0b4`)

| ID | Severity | Description | Disposition |
|---|---|---|---|
| M-A2.3 | MINOR | `npm run build` skipped (only tsc covered) | Defer; tsc-clean is load-bearing |
| M-A3.1 | MINOR Lane D | Brief §3 baseline `866` stale → actual `925` (cycle-15 baseline) | Fold-in at next brief-touching commit |
| I-A6.1 | IMPORTANT | `CINEMA_BUDGET_LIMIT_USD` env-var unbound (per-project `budget_limit_usd` is actual) | ✅ CLOSED via Option (a) — set `budget_limit_usd: 50.0` in Tier B project's `global_settings` at creation |

### Tier B (`a42a6af` + `24d39f0`)

| ID | Severity | Description | Closure |
|---|---|---|---|
| **C-B1** | 🔴 CRITICAL | ComfyUI UNETLoader empty list → FAL fallback (no PuLID identity anchoring) | ✅ CLOSED at `eb6af85` (script) + user pod symlink + A9-redux GREEN |
| **C-B2** | 🔴 CRITICAL | Tri-mix audio fails on Kling silent video → BGM-only fallback (dialogue + foley dropped) | ✅ CLOSED at `b11edd4` (mux standalone dialogue track) |
| **I-B1** | 🟡 IMPORTANT | Cartesia Korean routing not triggered (dispatcher reads canonical `language`; project had only brief's `language_pref` alias) | ✅ CLOSED at `972e239` + `2398314` (resolver + dispatcher both read both keys) |
| **I-B3** | 🟡 IMPORTANT (NEW) | Cartesia API 400 (ElevenLabs voice_id namespace passed through) | OPEN — operator-preferred NO ACTION for Tier C; cycle-17+ Cartesia voice_id work |
| **M-B3** | 🟡 MINOR | amix `duration=first` clamps audio to dialogue length when standalone-dialogue < video | ✅ CLOSED at `ee70fd1` v1 + `e867aac` v2 refinement (`-shortest` pair) |
| I-B2 | 🟡 MINOR | "contemplative" mood not in `vibe_prompts` dict | OPEN — Lane D candidate |
| M-B1 | 🟡 MINOR | SCREENING gate env-var-only control | OPEN — document OR add fallback |
| M-B2 | 🟡 MINOR | `cost_log` incomplete (LLM/BGM/Foley/TTS not tracked) | OPEN — Tier C consideration |
| Lane V C-B2 framing | 🟡 MINOR advisory | `a42a6af` "no input mapping" framing imprecise; actual is Kling silent video | OPEN — fold at next docs(arch-sync) opportunity |
| Lane V `972e239` test gap | 🟡 MINOR advisory | New dict-shape `settings_obj` path lacks unit test | OPEN — Tier C cleanup-pass |

**Summary:** 2 CRITICAL + 1 IMPORTANT + 1 MINOR CLOSED inline this cycle. 1 IMPORTANT + 4 MINOR + 2 Lane V advisory OPEN (none blocking Tier C).

---

## Cycle-16-entry operational learnings (candidates for v5.4+/v5.5+ codification)

1. **Director cold-context Lane V on operator tier artifacts is high-value-add** — Director's Lane V on `a42a6af` returned diagnoses sound + 2 minor precision findings. Cold-context independence surfaced: (a) C-B2 root-cause framing imprecision (operator artifact "no input mapping" → actual "Kling silent video"); (b) 972e239 resolver fix lacks test coverage for new dict-shape path. Neither was in operator's main-context view. **Implication:** Rule #9 §"Parallelism" CC-1 CRITICAL exception works as designed for cold-context independent review — director welcome on every operator tier-end artifact for cold-eye discovery.

2. **Pod-side fixes are user-principal-actionable, not operator-actionable** — C-B1's runtime closure required SSH access to RunPod pod + symlink command. Operator session has no pod SSH; user-principal does. Director's `eb6af85` was the durable script-side fix; user-principal applied the immediate symlink one-liner; director then probed A9-redux GREEN. **Implication:** future pod-side findings should: (a) ship durable script fix for next pod deploy; (b) provide one-liner for immediate apply; (c) verify via probe after user-confirmation. 3-step closure pattern.

3. **C-B2 was a hidden architectural assumption from cycle-15 — Kling Native PA-VIDEO routing change (v0.9.3) silently invalidated the tri-mix design** — The audio architecture (v0.9.6 foley + v0.9.7 Cartesia + v0.9.8 cost-tracker) assumed dialogue is embedded in motion clips (Omnihuman/Veo). When PA-VIDEO Set 3 routing changed to KLING_NATIVE in v0.9.3, the embedded-audio assumption silently broke. **Implication:** brief-vs-code architectural assumptions need explicit verification when one changes the other's preconditions. A test-cell like P-ASSEMBLY should EXPLICITLY include "does the motion engine embed dialogue?" as a PREDICTION criterion. Cycle-17+ ARCHITECTURE.md §12 should document per-engine audio-embedding capability matrix.

4. **Inline-per-finding `fix:` commits are the right cadence for execution-tier closures** — Cycle-16-entry shipped 6 inline `fix:` commits (3 operator + 1 director). Each closed one specific finding with self-contained pre/post diagnostic + verification command in body. Combined with Rule #15 advisory matrix dispositions, this produced per-finding traceability that matched director's Lane V cold-context review pace. **Implication:** Q8 inline-per-finding discipline scales to Tier C/D execution; coalescing into a single tier-end fix commit would lose the audit-trail granularity.

5. **Operator-default for Multi-Task Plan ≥5-sub-task discipline scales beyond just subagent dispatch** — Cycle-16-entry Tier B execution involved ~9 distinct sub-tasks (dispatch-claim → project create → pipeline run → fix #1 → reset → re-run → fix #2 → validate → fix #3). Used TaskCreate at threshold; tasks #1-#7 stayed accurate throughout; explicit task-state tracking simplified context-management. **Implication:** TaskCreate is the right shape for multi-step execution work even when work is direct main-context (not subagent-dispatched). CLAUDE.md guidance to use TaskCreate at ≥5 sub-tasks is well-tuned.

6. **AskUserQuestion is the right escalation surface for paid-tier scope decisions** — Twice cycle-16-entry I used AskUserQuestion to surface execution decisions (Tier B variant + I-A6.1 disposition; Tier C scope x3). Auto Mode says make reasonable calls + keep going, BUT paid-tier actions ($3-15+ per tier) merit explicit user authorization. **Implication:** AskUserQuestion threshold = "this decision changes what gets tested OR spends >$1 OR has tier-blocker implications." Sub-$1 decisions and operational fixes proceed via Auto Mode default.

7. **User-dismissed AskUserQuestion = "stop driving; wait for direction"** — When user dismissed all 3 Tier C scope questions with directive "do not proceed; wait for next instruction," operator MUST NOT re-attempt to push Tier C forward. Standby + standard hygiene (cursor advance + ack) without re-asking. **Implication:** dismissed questions are stronger than "no" — they're "stop trying." Operator default for handling: complete in-flight operator hygiene work + standby + surface state.

8. **3 N=1 race-ack shape instances this cycle; no N=2 emergence** —
   - Concurrent-claim race (T19:19:51Z + T19:19:53Z dispatch-claims; both seats independently composed)
   - Stale-mailbox-content assertion (operator `2426f59` §"Coordination" #1 stale by ~2.5 min)
   - Pre-write re-verify gap (operator T19:31:45Z write skipped `git log -3`; director Flag #1)

   All resolved cleanly; none caused operational damage. Cycle-16+ watch for second instances of any shape to trigger Candidate #8 N=2 codification proposal at v5.4 REPLY cycle.

---

## Established patterns (preserved from cycle-15 handoff; cycle-16-entry extensions noted)

See [cycle-15 operator handoff §"Established patterns"](HANDOFF-operator-transplant-2026-05-27-cycle15.md) for the full lore. **Cycle-16-entry adds:**

- **Tier-A single-artifact form** (per `0f6527f` execution-begin handoff Step 2): A1-A9 captured in ONE artifact at `docs/test-cells/A-<UTC>.md`; ONE commit at tier-end (`5425e5e`); subject `test(cell): A-tier <verdict> — Tier A pre-flight A1-A9`. Director's cold-context parallel artifact uses `-director` suffix (`A-<UTC>-director.md`).

- **Tier-B per-cell vs umbrella artifact decision tree:** Tier B used 1 umbrella artifact (`B-2026-05-27T19-36-10Z.md` covering all Tier B cells) + 1 validation artifact (`B-validation-2026-05-27T20-10-21Z.md` post-fix re-run). Per-cell sub-artifacts not used due to coupled cell dependencies + unified pipeline run. **Implication:** for Tier C with multi-shot reel + gates + iteration, per-cell artifacts MAY be more useful (each gate cell has distinct PREDICTION/ACTUAL/DELTA). Operator-default discretion at Tier C.

- **Inline-fix discipline cadence** demonstrated: 6 inline `fix:` commits shipped during Tier B without batching. Each with self-contained pre/post diagnostic + verification command. Backward-compat preserved via dual-key reads OR conditional flags. 925/3/0 baseline preserved throughout (regression-safe).

- **AskUserQuestion patterns:** Used twice cycle-16-entry — once at Tier B inception (variant + I-A6.1 disposition; both answered), once at Tier C inception (3 scope questions; all dismissed with "wait"). Both invocations were appropriate per "paid-tier OR tier-blocker" threshold. Dismissal carries strong "stop" signal; respect it.

- **Direct re-assembly for fix validation** (M-B3 v2 validation): instead of full Tier B re-run ($0.60), used `pipeline._assemble_final()` directly with cached assets ($0 cost). Validates audio architecture changes without re-incurring keyframe/motion gen cost. **Implication:** when fix is isolated to assembly phase + cached upstream assets exist, direct phase re-invocation is the right shape. Pattern: load project + construct `scene_data` with cached paths + call `_assemble_final()` + ffprobe verify.

- **Race-ack shape diversity catalog** (Candidate #8 telemetry):
  - cycle-15 entry: 9 instances of "in-flight commit drift during another seat's Write"
  - cycle-16 entry adds: concurrent-claim race + stale-mailbox-content assertion + pre-write re-verify gap (3 distinct new shapes)

  None at N=2 emergence yet; codification waits for second instance of any specific shape.

---

## Open questions for director (held over for next director session)

**Tier C scope (joint, BLOCKED on user-principal):**

- 0 outstanding director-blocking findings — director's `f15aa8e` Tier B closure verification-report is comprehensive
- User-principal Tier C scope decision pending (3 questions dismissed; awaiting next instruction)
- If user resumes Tier C: synchronous joint-seat execution per Q9 — director observes operator-driven Tier C dispatch; Lane V CC-1 coalesced at Tier C tier-end OR CRITICAL exception during execution

**v5.4 codification timing:**

- 5 N=1 candidates filed (#1, #3, #4, #5, #8); 0 at N=2 emergence
- Cycle-16-entry added 3 NEW race-ack shapes for Candidate #8 (concurrent-claim + stale-mailbox-content + pre-write re-verify gap) — all at N=1
- Codification waits for N=2 shape-divergent emergence
- Director-seat MAY draft v5.4 when ≥1 candidate reaches N=2 per role partition strategic-default; operator MAY draft per v2-v5.3 precedent. User direction breaks ties.

**Cycle-17+ backlog candidates:**

- C-B2 architectural follow-up (audio-embedding capability matrix in ARCHITECTURE.md §12)
- I-B3 Cartesia voice_id namespace (per-character schema field OR default lookup helper)
- Lane V `972e239` test coverage gap (7-LoC mechanical addition)
- Lane V C-B2 root-cause precision (artifact framing OR ARCHITECTURE.md note)
- I-B2 / M-B1 / M-B2 (operational cleanups)

**Net director-actionable findings outstanding from cycle-16-entry: 0** (all REPLY content consumed; all CRITICAL/IMPORTANT closed; advisory backlog operator-discretion).

**User-actionable decisions outstanding: 1** (Tier C scope + authorization, OR pivot to alternative direction).

---

## Baseline state snapshot at transplant

State at the moment of cycle-16-entry close handoff WRITE. Run cold-start checklist for current truth.

```
$ git log --oneline -5
9c9c1b2 coord(mailbox): operator Tier B closure acknowledgement + cursor T19:34:00Z → T20:13:38Z + standby for Tier C direction
e867aac fix(audio): close Tier B M-B3 (refinement) — pair amix duration=longest with -shortest output flag
f15aa8e coord(mailbox): director Tier B verification-report — Lane V findings + C-B1 A9-redux GREEN + Tier C readiness
ee70fd1 fix(audio): close Tier B M-B3 — amix duration=longest for standalone-dialogue path
24d39f0 test(cell): B-validation VALIDATED — I-B1 + C-B2 fixes confirmed; 2 new findings filed

$ git status
On branch main
Your branch is up to date with 'origin/main'.
nothing to commit, working tree clean
(modulo this handoff file pending add+commit)

$ git rev-list --count origin/main..HEAD
0   # everything pushed

$ .venv/bin/python -m pytest tests/unit/ --tb=no -q | tail -1
925 passed, 3 skipped, 2 warnings, 10 subtests passed
(baseline preserved through 3 inline fixes + 1 refinement)

$ .venv/bin/python scripts/ci_smoke.py
OK

$ cat coordination/mailbox/seen/operator.txt
2026-05-27T20:13:38Z
# Consumed director's f15aa8e T20:13:38Z verification-report.

$ ls coordination/mailbox/sent/ | wc -l
44   # cumulative across cycle-1 through cycle-16-entry

$ ls coordination/mailbox/sent/ | tail -5
2026-05-27T19-34-00Z-director-to-operator-acknowledgement.md
2026-05-27T20-13-38Z-director-to-operator-verification-report.md
2026-05-27T20-23-26Z-operator-to-director-acknowledgement.md

$ POD_URL=$(grep '^COMFYUI_SERVER_URL=' .env | cut -d= -f2)
$ curl -sI "$POD_URL/object_info" --max-time 10 | head -1
HTTP/2 200   # pod still alive

$ curl -sf "$POD_URL/object_info/UNETLoader" | jq -r '.UNETLoader.input.required.unet_name[0][]'
FLUX1/flux1-dev-fp8.safetensors   # C-B1 closure verified (Tier C unblocked)

$ ls domain/projects/
7cddd0c59f6d   # Tier B Korean Probe project (preserved for potential Tier C extension)

$ grep -c "^" .env
26   # unchanged from cycle-15 close (11 of 12 useful API keys SET)
```

**LOC drift advisory (cycle-16-entry):**
- `audio/dialogue.py`: +27 LoC (I-B1 resolver + dispatcher fixes; `972e239` + `2398314`)
- `cinema_pipeline.py`: +108 LoC (C-B2 `_concat_dialogue_track` helper + dynamic filtergraph; `b11edd4`) + 14 LoC (M-B3 v1 + v2; `ee70fd1` + `e867aac`)
- `scripts/setup_runpod.sh`: +13 LoC (C-B1 diffusion_models/ + symlink; `eb6af85`)
- `config/settings.py`: 1-LoC override=True (`0ecda24`)
- `docs/test-cells/`: 3 NEW artifacts (A-tier operator + A-tier director-cold-context + B-tier umbrella + B-validation)
- `docs/HANDOFF-execution-begin-2026-05-27.md`: 1 NEW (cycle-15 close epilogue at `0f6527f`)
- `docs/BRIEF-comprehensive-test-2026-05-27.md`: v0.9.8 → v1.0 SHIP (`0f6527f`)
- `coordination/mailbox/sent/`: +13 events (cycle-16-entry comms)
- `CLAUDE.md`: 1811 LoC (unchanged cycle-16-entry)
- `AGENTS.md`: 1391 LoC (unchanged cycle-16-entry)
- `PROTOCOL-RULES-LOG.md`: 579 LoC (unchanged cycle-16-entry)

**Total cumulative N=1 candidates filed:** **5** (Candidates #1, #3, #4, #5, #8). UNCHANGED cycle-16-entry. 0 at N=2 emergence. Cycle-16-entry added 3 NEW race-ack shapes (concurrent-claim + stale-mailbox-content + pre-write re-verify gap) for Candidate #8 reinforcing-evidence catalog.

**Total rules codified through cycle-16-entry:** **15** (UNCHANGED cycle-16-entry; no v5.4 ship). Three consecutive `both`-beneficiary bundles (v5.1 → v5.2 → v5.3) lean from cycle-13 close preserved.

---

## Time accounting (this operator session)

| Phase | Approx hours |
|---|---|
| Cold-start checklist + reading cycle-15 close handoffs + mailbox awareness gate | 0.4 |
| Tier A dispatch-claim + A1-A9 execution + artifact + verification-report | 0.6 |
| Tier B project creation (Korean Min-ji + Seoul cafe + 1 shot) + auto_approve config | 0.4 |
| Tier B Run 1 (frozen at KEYFRAME_REVIEW; killed; surfaced findings) | 0.5 |
| Tier B Run 2 (reset + run 2 with auto_approve relaxed; tri-mix BGM-only fallback) | 0.4 |
| I-B1 part 1 resolver fix (`972e239`) | 0.2 |
| Tier B umbrella artifact (`a42a6af`) | 0.4 |
| I-B1 part 2 dispatcher fix (`2398314`) | 0.3 |
| C-B2 tri-mix fix (`b11edd4`) — _concat_dialogue_track + dynamic filtergraph | 0.5 |
| Tier B Run 3 validation (`bwf55f3py`) + ffprobe verify | 0.3 |
| Tier B validation artifact (`24d39f0`) | 0.3 |
| M-B3 v1 (`ee70fd1`) + direct re-assembly v1 + overshoot finding | 0.3 |
| M-B3 v2 refinement (`e867aac`) + direct re-assembly v2 + ffprobe validate | 0.3 |
| Director event consumption + Tier B closure ack (`9c9c1b2`) | 0.3 |
| Tier C AskUserQuestion + dismissal handling + standby | 0.2 |
| Cycle-16-entry close handoff drafting (this doc) | 0.6 |
| **Total** | **~6.0 hours** |

**Subagent dispatches this cycle:** 0 operator-side (all operator work main-context Edit/Bash). Director-side dispatched 1 cold-context Lane V (`ab832c7`; ~5min wall-clock; ~50-80k subagent tokens; on operator's `a42a6af` Tier B artifact).

**Cumulative subagent tokens for cycle-16-entry operator-side:** **0**. Director-side: ~50-80k (Lane V on Tier B artifact only).

**Operator-driven Lane B this cycle:** 0 invocations (no subagent-dispatched work this cycle; inline `fix:` commits were direct main-context edits).

**Lane V dispatches this cycle:** 1 director-side (cold-context independent reviewer on Tier B artifact). 0 operator-side (Q9 sync-joint posture; would re-run only if CRITICAL surfaced post-fix, which didn't happen).

Total operator-seat efficiency: **0 subagent tokens, ~6.0h productive substrate + Tier-A + Tier-B execution + 3 critical fixes + 1 minor fix + comprehensive findings catalog**. Cycle-16-entry represents the **first-ever paid-tier execution cycle** in this project; spent ~$2.10-2.65 to surface AND CLOSE 2 CRITICAL + 1 IMPORTANT findings + ship 6 inline `fix:` commits (operator 5 + director 1) + validate audio architecture end-to-end. **High value-per-dollar:** ~$2.50 to close 2 CRITICAL + 1 IMPORTANT + 1 MINOR = $0.50-0.65 per CRITICAL closure.

---

*Operator-seat handoff at HEAD `9c9c1b2` (Tier B closure ack + cursor advance + standby for Tier C direction). Branch 0 ahead of `origin/main`. **Tier A + Tier B comprehensively closed cycle-16-entry: brief contract validated through paid pipeline; audio architecture cycle-15 entry feature (foley + Cartesia + tri-mix) corrected for PA-VIDEO Set 3 KLING_NATIVE routing; PuLID-FLUX path operational (C-B1 closed both layers); Korean TTS routing functional both layers (I-B1 closed); tri-mix audio assembly correct for standalone-dialogue path (C-B2 + M-B3 closed); 6 inline fix commits + 6 minor advisory open.** Cumulative ~$2.10-2.65 of Q6 $3-7 envelope. Tier C unblocked but user-principal dismissed scope questions ("do not proceed; wait for next instruction"). 925 pass / 3 skip / 0 fail baseline preserved through 4 inline fixes; §15 smoke OK throughout; 15 discipline rules + 5 N=1 candidates UNCHANGED cycle-16-entry. Per v5 §P1 ("two seats of one team"), this is operator-seat's handoff to the next operator-seat instance. Cold-start checklist above is v3 §F freshness-check compliant + carries Candidate #8 RECENCY discipline forward from cycle-15. Run `git log --oneline -5` AND re-`ls mailbox/sent/` immediately before any state-asserting Write spanning >30 min from cold-start gate. User-direction overrides agent discretion at any point (Rule #8 authority precedence + v5 §P1 user-as-principal). Cycle-16-entry = the pre-flight-execution + Tier-A-PASS + Tier-B-Korean-probe + 2-CRITICAL+1-IMPORTANT-closed-inline + director-parallel-Lane-V cycle; cycle-16+ awaits user-principal Tier C scope direction (3 questions surfaced; all dismissed) OR alternative direction. Welcome to cycle-17.*
