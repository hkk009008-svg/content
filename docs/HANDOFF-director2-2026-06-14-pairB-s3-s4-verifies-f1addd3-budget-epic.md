# Handoff — director2 (Pair-B: video/assembly/delivery) — 2026-06-14

**Seat:** director2 (Pair-B director). **HEAD at wrap:** `f1d7b2d` (verify `git rev-parse HEAD`).
**Push:** USER-gated (origin PUBLIC at `fec4e76`, **18 ahead**, do NOT push). **Read this first
as the next director2.** Predecessor: `docs/HANDOFF-director2-2026-06-13-PM-W1-...md`.

---

## TL;DR / session arc

Resumed into a **live 4-seat session** (user "continue as director2", ultracode). Drove the
director2 **verification** thread: discharged both owed authoritative passes (§3 + §4), ran an
unrequested verify of a just-shipped scorer that turned up real defects, surfaced+pinned every
finding, and consolidated them into a proposed cross-lane epic that already has Pair-A buy-in.
Wrapped on user "handoff".

**Role this session:** pure verifier + coordinator. operator2 implemented §3/§4; I verified.
I did NOT implement any production fix — found defects were **surfaced + xfail-pinned**, mirroring
operator2's handling of their own out-of-scope sites (implementer≠verifier held throughout).

---

## What I VERIFIED + LANDED (my commits, all local)

| Item | Commit(s) | Note |
|---|---|---|
| **§3 audio-loss `1eec3cd` = GO** | verify `wf_4e1a1fba-479` (5 lenses, 0 crit/major/minor); NITs `da44739`; report `741d818` | triple-convergent. 2 NITs folded: `_restore_audio_track` engine-label + strip-no-flag test now asserts both flags |
| **§4 nan-gate `a812ee4` = GO** | verify `wf_99bc3ff7-fe4` (4 SAFE + 1 sweep-find); report in `ca77f9a` | identity_strictness = verified no-op on valid inputs (Pair-A flag SATISFIED); `_finite_or` byte-identical to `quality_max:194` (import-swap is a verified no-op); diagnose_clip test genuinely RED-without-fix |
| **f1addd3 scorer D1 pin** | `8304fea` | silent-degradation defect, xfail(strict) |
| **budget-NaN pin** | `e28f4fa` | §4-completeness MAJOR sibling, xfail(strict) |
| Coordination | `ca77f9a` (§4 GO + sibling + epic → operator2 + cross-lane fyi) | |

Both pins **xfail correctly against HEAD `f1d7b2d`**; `ci_smoke` OK. R-VERIFY-TIER satisfied
(every confirmed unfixed defect is pinned or labeled).

---

## ⭐ Findings on the table (the forward work)

### A. f1addd3 mouth-energy lip-sync scorer — MATERIAL DEFECTS (read-only verify `wf_46f1d3ec-145`)
The coordinator's single-subagent review missed these. The scorer gates the program's core
"synced dialogue" guarantee.
- **D1 (major, PINNED `8304fea`):** `_score_mouth_energy` outer `except Exception` (`lip_sync.py:568-570`)
  swallows a cv2 `ImportError` with **no log** → in the common opencv-absent container it silently
  returns None → falls to neutral-1.0/duration-match → **re-creates the "everything passes → random
  best-of" bug f1addd3 claims to fix, invisibly.** Cheap fix: `logger.warning` on the cv2-absent path
  + promote the occlusion INFO→WARNING. (Pin flips to a strict CI error when fixed.)
- **D2 (major, test-infeasible-this-turn):** uses `haarcascade_smile.xml` (`lip_sync.py:457`) to track a
  *speaking* mouth → neutral speech underdetected → >50% occlusion fail-open on well-synced takes.
- **D3 (HYPOTHESIS, major-if-true, POD-GATED):** passing the 0.8 auto_approve bar needs raw Pearson ≥ 0.6;
  real mouth-brightness/audio-RMS correlation may sit well below → well-synced takes **rejected** (opposite
  pathology). **Needs an empirical calibration run on real synced/desynced clips before it backs any NO-GO
  (R-MEASURE).** This is the experiment that decides whether f1addd3 is net-positive or net-negative.
- **D4 (major, test-infeasible-this-turn):** all 4 existing tests MOCK cv2 → real Haar/astats path
  untested; no anti-sync discriminator test.

### B. budget-NaN gate bypass — NEW MAJOR (PINNED `e28f4fa`), design RESOLVED
A NaN `budget_limit_usd` survives `float()` (`cinema/core.py:101`) and `bool(nan)=True` stores it
(`cost_tracker.py:170`) → `would_exceed`/`is_over_budget` compare against NaN (always False) →
**unbounded spend, masquerading as a set cap.** Confirmed by direct read + behavioral probe.
**Pair-A co-signed the fix DIRECTION (`2db899c`): fail-CLOSED on non-finite (NaN/inf → hard BLOCK +
loud error), `None`=unlimited stays.** Mechanic: `math.isfinite` guard at `cinema/core.py:101` +
`cost_tracker.py:170`. Implementation is Pair-B's/joint — **fold into the epic.**

### C. 2 sweep minors
- **flux_guidance NaN** (Pair-A lane) — **ALREADY FIXED by Pair-A `bf1034a`** + 2 novel siblings
  (`comfyui_steps` crash, `img2img` clamp-luck). Closed.
- **transition_duration NaN** (`cinema_pipeline.py:1336`, OUR lane) — self-mitigated (ffmpeg rejects →
  hard-cut fallback). Labeled, not pinned. Low-pri; pin if you touch assembly.

---

## ⭐ NEXT pickups (ordered)

1. **The consolidated "auto_approve + lip-sync + nan-gate hardening" epic** — **has Pair-A buy-in**
   (`2db899c`: "good with folding budget + the 6 auto_approve NaN + S2, Pair-A owning the image/identity
   gates"). Members:
   - **S2** (operator2's: best-take ignores `dialogue_audio_in_clip`, `auto_approve.py:502`)
   - **operator2's 6 auto_approve NaN sites** (one `_get_finite` chokepoint in `from_project`)
   - **budget-NaN** (`e28f4fa`) — fail-closed on non-finite per the co-sign
   - **f1addd3 D1** (cheap WARNING) + **D2/D4** (detector + tests)
   - **D3 calibration = the GATING experiment** (POD-GATED) — settle net-positive/negative FIRST
     before investing in D1/D2 fixes; D3 + operator2's `final_min_lipsync:388` NaN site are the same gate.
   Cross-lane → Pair-A co-sign on image/identity gates (they've done quality_max/workflow_selector this
   session: `a478f5b → 7b4d377 → bf1034a`).
2. **operator2 has NOT yet replied to the epic-sequencing ask** (my `ca77f9a`, 00:33Z). Their stated next
   was §5 (tmpfile cleanup, LOW) OR the epic. Confirm their pick on resume.
3. **Push** — 18 ahead of `fec4e76`, USER-gated. §3+§4 both verified GO + Pair-A nan-gate landed = a clean
   push point; I recommended surfacing it. User said "handoff" not "push" → still pending.
4. **D3 pod calibration** — needs the pod STARTED (last-known STOPPED, $0). Re-confirm SSH before any burn.
5. **operator2's owed §3 ARCHITECTURE.md anchor doc-sync** (their carry) — DEFERRED until ARCHITECTURE.md
   is clean of Pair-A WIP.

---

## Cross-lane state (Pair-A = image/identity)

- **Pair-A director (director-1) WRAPPED** (PM8, `10d4450`): nan-gate perimeter swept
  (`7b4d377` quality_max 2 LoRA siblings + `bf1034a` workflow_selector 3 overlay siblings).
- **start_at 0.20→0.0 (MAX-wide):** op-1 ran the R-MEASURE A/B (`f1d7b2d`) — verdict **HOLD** (0.0 not
  supported for wide; renders over-cooked; N=3 inconclusive). Still pod-gated.
- **`_finite_or` import-swap unblocked** by `a812ee4` (Pair-A's to do anytime; verified no-op).
- **has_character LoRA-only prune hole** — Pair-A DEFER + xfail-pinned.

## Sharp edges (this session)

- **Live shared tree, HEAD moved ~8× under me.** `git log -1` immediately before EVERY commit caught
  (a) the user-authorized push (`fec4e76`) and (b) operator2's §4 land + verify-request mid-task. Trust
  git, not your in-memory model.
- **Phantom per-seat index:** session-start `git status` showed 155 "deleted" files + MM ghosts — ALL
  matched HEAD on disk (`git diff --no-index <(git show HEAD:path) path` empty). Don't revert; read files
  directly; explicit-pathspec commits only.
- **A peer's uncommitted WIP appears in YOUR working tree** (operator2's §4 `_finite_or` import showed up
  in my `lip_sync.py` mid-session). Before any pathspec commit, confirm `git show <yourcommit>:path` didn't
  sweep it. `git commit -- <file>` is collision-safe; bare `git commit` sweeps peer staged WIP.
- **`| tail` masks git exit codes** — capture `$?` un-piped for git gates.
- **send-event stages into the SEAT index; commit the mailbox file with `env -u GIT_INDEX_FILE git add`
  first** (new file → default index) then pathspec-commit.
- **R-MEASURE on D3:** the scale-miscalibration is a HYPOTHESIS (agent reasoning about Pearson ranges, not
  measured on our clips). Do NOT assert it as fact — the calibration run is the instrument.

## Coordination state @ wrap

HEAD `f1d7b2d`; 18 ahead of origin `fec4e76`; push USER-gated. My pins (`8304fea`, `e28f4fa`) xfail green.
ci_smoke OK (one new advisory: an `operator → director measurement-report` kind not in KNOWN_KINDS — a
linter enum gap, not mine; consider adding `measurement-report` to `scripts/check_coordination.py`).
operator2 ONLINE last I saw; director-1 WRAPPED. Pod STOPPED ($0). My seen cursor is stale — advance it
on resume.
