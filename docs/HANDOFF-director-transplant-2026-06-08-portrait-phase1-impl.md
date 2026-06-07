# Director transplant handoff — 2026-06-08 (portrait Phase-1 implemented; final review + merge pending)

**READ THIS FIRST if you are the next director-seat.** This is the canonical
pickup doc for the session that ran the held Lane V → U3 collision/reconcile →
F4 → portrait-delivery feature (brainstorm → spec → plan → Phase-1
implementation).

---

## 0. TL;DR — where things stand

- **`main` == `origin/main` == `96a9ad1`** (public). Carries everything through
  U3 final-media conformance + its Lane V fixes. **GREEN.**
- **`feat/max-tier-provisioning` == `2471b71`** (LOCAL, **UNPUSHED**; `origin/feat`
  still `96a9ad1`). Carries, on top of main:
  - **Portrait delivery Phase 1** (this session, director): `215fdf0` aspect.py ·
    `e4bd575` assembly · `3d8c8e0` scorecard · `7672cbc` /api/config gate ·
    `4778c6a` PUT validation · `43127cc` FE fallback · `2471b71` arch-sync.
  - **Operator's vision deep-diagnose** (interleaved): `d974c15` feat ·
    `a4cb076` fix · `7f5acc4` doc-sync · `868dbbf`/`60cf281` coord.
  - **Portrait spec + plan docs**: `9e2cedf`→`8ad67ed` (spec), `a045f7c`→`bb8f13e`
    (plan).
- **Full suite `1703 passed / 0 failed`, `ci_smoke OK`** at `2471b71`
  (verified `env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit -q`;
  `scripts/ci_smoke.py` → OK; FE `tsc --noEmit` + `npm run build` clean).
- **#1 PICKUP:** the **final cross-cutting review of Phase 1 was NOT run** (the
  user said "handoff" right as it was about to dispatch). Then push `feat` +
  merge `feat`→`main` — **user-gated** (do not push/merge without explicit go).

---

## 1. What shipped this session (director-seat)

Chronological. All on `feat` unless noted; merges to `main` were user-go'd.

### 1a. Held comprehensive Lane V (Rule #9) → ✅ READY + 2 fixes
- Ran 3 cold reviewers over **T6 + Part 4 + T1/T3/T4** (the operator-invited
  post-merge pass). Verdict ✅ READY, **6 MINOR / 0 blocking**.
- Folded the 2 recommended minors → **`e5be165`**: M-T6-2 (advisory try/except
  fence on the keyframe hot path) + M-Q-1 (honest conjunctive halt-reason when
  the arc floor is auto-bypassed). Other 4 MINOR NO-ACTION.
- **Merged `feat`→`main` (FF) + pushed** per user merge-go.

### 1b. U3 (audio LUFS + format probe) — COLLISION + reconcile
- Picked U3 as a forward ticket; **collided** with the operator's concurrently-
  authored **user-approved U3 spec** (`b2fe065`+`e70420e`). My first
  implementation (`c7b5fa9`) used a *rejected* architecture (request-time probe
  + dimension-shape). My dispatch-claim wrongly said "operator offline" — a
  Rule #19 presence-read miss (owned in `1e0d38b`).
- **User adjudicated: director finishes U3 per the approved spec.** Reset `feat`
  to the spec tip (`e70420e`), re-implemented spec-conformant (assembly-time
  persist `project["media_report"]` + separate `media` block) → **`803fbcb`**.
  Cold spec+quality review ✅ zero findings; real-media acceptance check passed
  (−15.09 LUFS → `lufs.pass=False`). Merged + pushed.
- Operator's independent Lane V on `803fbcb` → ✅ READY, 5 MINOR. Folded **F2**
  (guard `measure_loudness` call in `probe_final_media`) + F1 test → **`2f4fc50`**
  (Rule #15 cross-seat closure). Merged + pushed. **main reached `96a9ad1`.**

### 1c. F4 → portrait/aspect-aware delivery (the big arc)
U3 Lane V **F4** ("EXPECTED_RESOLUTION hard-fails 9:16") turned out NOT to be a
scorecard bug — **portrait delivery is unimplemented end-to-end** (assembly
hard-codes 1920×1080; `aspect_ratio` only feeds the LLM style prompt; providers
hard-code 16:9). Surfaced to user → **user chose to BUILD portrait delivery**.

- **Brainstorm** (superpowers): user-adjudicated forks — **9:16-only · native
  generation · all providers · phased+gated**.
- **Spec** `docs/superpowers/specs/2026-06-07-portrait-aspect-delivery-design.md`
  (`8ad67ed`), hardened by a **12-agent Rule #17 verify+review workflow** (caught
  a real gate hole: `ProductionSection.tsx:148` fallback bypasses `/api/config`;
  built the Phase-3 provider matrix).
- **Plan** `docs/superpowers/plans/2026-06-07-portrait-aspect-delivery-phase1.md`
  (`bb8f13e`), hardened by a **4-agent plan-review workflow** (caught a broken
  test fixture + a phantom code anchor).
- **Phase-1 implementation** via subagent-driven-development (fresh implementer +
  cold spec+quality review per task): 6 commits + arch-sync (see §0). Every
  task green; **16:9 byte-identical** (golden-string asserted); **`9:16` gated
  out of selection** until Phase 3.

---

## 2. The portrait feature — 3-phase decomposition (gated until complete)

Shared foundation: **`cinema/aspect.py`** — `resolve_output_dimensions` +
`SUPPORTED_ASPECT_RATIOS` (the gate, currently `["16:9"]`) + `is_portrait` /
`is_supported`. All surfaces import from it.

| Phase | Scope | Status |
|---|---|---|
| **1 — Foundation** | resolver + assembly + scorecard + `/api/config` & PUT gates + FE fallback | **DONE on `feat`** (green; review+merge pending) |
| **2 — Native image keyframes** | `pulid.json`/`pulid_max.json` portrait latent + upscale dims via the resolver | **own spec later** |
| **3 — Native video + un-gate** | per-provider 9:16 + flip `SUPPORTED_ASPECT_RATIOS` to add `"9:16"` | **own spec later** |

**The gate:** every phase builds/tests against `9:16` but it's unselectable
(`/api/config` returns only `SUPPORTED_ASPECT_RATIOS`; PUT 400s unsupported)
until Phase 3's last task flips one constant. Phase 1's observable change:
the aspect dropdown honestly shows only `16:9`, and the U3 scorecard is
aspect-correct.

**Phase-3 provider matrix (verified, in the spec §7-D) — revisit "all providers"
at the Phase-3 spec:** only **Veo** supports native 9:16 today (and its
`generate_video` doesn't even thread the existing `aspect_ratio` param);
**Kling** has NO aspect param (exclude or crop/pad); **Sora/LTX/Hedra**
unverified (need API docs → likely crop/pad fallback).

---

## 3. OPEN items + ownership

**#1 (director) — finish Phase-1 close-out:**
- Run the **final cross-cutting review** over the 6 Phase-1 commits
  (`215fdf0 e4bd575 3d8c8e0 7672cbc 4778c6a 43127cc`) — end-to-end contract
  (resolver→assembly→scorecard→gates), gating property holds, no regression.
  (NOTE the minor from Tasks 4+5 review: a bad-pid+bad-aspect PUT returns 400
  before 404 — spec-compliant ordering, NO ACTION unless you disagree.)
- Then **push `feat` + merge `feat`→`main`** — **USER-GATED**. The merge will
  also bring the operator's vision-diagnose commits to main.

**#2 (director) — cold Lane V on operator's vision deep-diagnose** (Rule #9):
range `8ad67ed..a4cb076` (skip their doc-sync/coord). Operator invited; not
blocking (their fix loop closed, suite green). See their `2026-06-07T11-20-00Z`
event.

**#3 (operator, in-flight) — their coalesced Lane V on MY Phase-1 slice:** they
noted (`60cf281`) they're *holding* it until the Phase-1 slice completes. It IS
complete now (`2471b71`) — **a coordination event telling them so is queued**
(see §5; if not yet sent when you pick up, send it).

**#4 — operator's 4 follow-up tickets** (from their 11:20 event):
1. **⏰ URGENT — `claude-sonnet-4-20250514` retires 2026-06-15 (~7 days)**,
   hardcoded `llm/chief_director.py:~120`; replacement `claude-sonnet-4-6`.
   Affects ALL ChiefDirector calls. Needs its own commit SOON.
2. No client timeout on either LLM provider (`_init_client`) — hang exposure.
3. `phase_c_vision.py` shares the oversize+MIME b64 bug (a 4K take = 20.28 MB
   b64 > anthropic's 10 MB limit) — the vision feature's `_encode_image_for_llm`
   fixed it for the deep path but not here.
4. Multi-character shots pass only `chars[0]`'s reference to the deep path
   (`controller.py:1934`) — known limitation.

**#5 — portrait Phases 2 & 3** (each own spec→plan→implement; matrix above).

**#6 — pre-existing GPU/pod + live-E2E backlog** (unchanged; pod was 404 — verify
Novita before any spend).

---

## 4. State facts (verified at handoff, ADR-013)

```
$ git rev-parse --short HEAD main origin/main origin/feat/max-tier-provisioning
  HEAD/feat 2471b71 · main/origin/main 96a9ad1 · origin/feat 96a9ad1
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit -q   → 1703 passed, 0 failed
$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py        → OK
$ (web) npx tsc --noEmit && npm run build                            → clean
$ cat coordination/mailbox/seen/director.txt → 2026-06-07T11:20:00Z (0 unread)
```

`feat` is **~17 commits ahead of `origin/feat`/`main`**, all local + unpushed.

---

## 5. Coordination / gotchas (carry forward)

- **D-a per-seat index goes stale after peer commits** — phantom mass-deletion
  `git status` (`D`/`MM` storm; I hit a 254-file phantom at session start;
  operator hit it 4×). **It is NOT data loss.** Fix: `git read-tree HEAD` (or
  `git reset -q HEAD`) before trusting `git status`; the working tree is fine.
  Saved as a memory this session; v5.8 protocol-fix candidate (operator
  proposes `update-state.sh` auto-refresh on HEAD move) — strategic-seat call.
- **Run pytest as `env -u GIT_INDEX_FILE .venv/bin/python -m pytest`** under D-a,
  else `test_check_doc_claims.py` false-fails (temp-repo git inherits the seat
  index).
- **New files need `git add` before the pathspec commit** — `git read-tree HEAD`
  drops untracked files from the index (Task-1 implementer found this).
- **`git commit -m "..." -- <paths>`** — `-m` BEFORE `--`.
- **Launch with `CLAUDE_SEAT=director`** for presence to auto-bump (hook
  self-heals via per-session marker otherwise).
- The operator is **active and coordinating well** — they held their Lane V for
  my slice, interleaved cleanly on the shared tree, and surface tickets/memory
  candidates via mailbox. Match that discipline.

---

## 6. Memory written this session
- `feedback_dawg_stale_index_refresh.md` (D-a stale-index refresh discipline) —
  see MEMORY.md index.

*— director-seat, 2026-06-08. Portrait Phase-1 implemented + green on `feat`;
final cross-cutting review + push/merge are the #1 pickup (user-gated). Operator
vision-diagnose Lane V is #2. main `96a9ad1` GREEN; feat `2471b71` GREEN.*
