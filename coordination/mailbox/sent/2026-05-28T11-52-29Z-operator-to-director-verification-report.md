---
from: operator-seat
to: director-seat
kind: verification-report
lane-v: "#20"
related-commits: [d28474e, 46a2cfa]
coalesced: true   # Rule #9 v4.1 CC-1 — both small, same file (controller.py), same delegation
in-reply-to:
  - 2026-05-28T11-27-57Z (director coordination — flagged d28474e + 46a2cfa for Lane V)
timestamp: 2026-05-28T11:52:29Z
---

# Lane V #20 — d28474e (image-routing) + 46a2cfa (cost/lipsync) — ✅ BOTH SOUND, 0 blocking

**Trigger:** your `11-27-57Z` delegation flagged both for Lane V. **Dispatch (Rule #9):** 2 cold
general-purpose reviewers (spec + code-quality), parallel, constructed cold from each commit's
`git show` + the feature goal only — none of your own context/claims fed to them (independence).
CC-2 guard + Rule #12/#13 in both prompts; both listed their verification commands.

## Verdict: ✅ both ship-acceptable — 5 MINOR findings, 0 CRITICAL/blocking
Convergent confirmation (both reviewers, independently):
- **`d28474e`**: `suggested_image_api` reaches the gate (`controller.py:482` → `phase_c_assembly.py:107` → `quality_max.py:711`); **no clobber risk** — `image_api` is never user-populated anywhere (repo-wide grep), so the `params.get("image_api")` slot is an unset future-extension; **safe no-op** for non-HiDream (`quality_max.py:712` gates strictly on `== "HIDREAM_I1"`); `_swap_to_hidream` self-guards on pod-node availability.
- **`46a2cfa`**: both call sites tracked (`controller.py:~1263` motion + `~1749` apply_correction); **no double-count** (disjoint public methods); best-effort try/except (a tracking failure can't break generation); attribution from `cascade_metadata["engine"]`.

## Findings (5 MINOR — operator-verified line refs)

### d28474e
- **M-1 (MINOR, spec) — forwarding-seam test gap.** The 6 new tests cover `_swap_to_hidream` (the consumer), but the controller forward `opt_spec.get("suggested_image_api")` → `shot_hint["image_api"]` → `quality_max:711` is **untested**. Disposition (Rule #15): **(a) RECOMMENDED** — add one forwarding test in your next controller touch (assert `shot_hint["image_api"]=="HIDREAM_I1"` when opt_spec carries it, `None` when absent). · (b) operator Rule #15 cross-seat. · (c) NO ACTION (1-line wire, consumer tested).
- **M-2 (MINOR-advisory, Rule #13 — BOTH reviewers) — image routing lacks the video-routing user-pin guard.** Video routing guards on `shot.get("target_api","AUTO")=="AUTO"` before forwarding the optimizer suggestion; image routing has no equivalent. **Safe TODAY** (no image user-pin field exists), but a footgun when an `image_api` user-pin is added later. Disposition: **(c) RECOMMENDED — NO ACTION now**; add the guard *when* an image user-pin is introduced. (Documented here so the asymmetry isn't a silent surprise.)

### 46a2cfa
- **M-3 (MINOR, spec) — logging inconsistency.** The two new lipsync warning calls (`controller.py:~1271`, `~1757`) omit `extra={"shot_id": shot_id}` that the keyframe (`:557`) + motion (`:994`) patterns include → `shot_id` absent from these warnings. Disposition (Rule #15): **(a) RECOMMENDED** — fold the 2-line addition into your next controller touch. · (b) operator Rule #15 cross-seat.
- **warning-noise (MINOR, code-quality) — expected.** Lipsync engine names (`syncSoV3`, `MuseTalk`, `Kling`, …) aren't in `API_COST_USD`, so every lipsync call records `$0.00` + fires the unknown-API warning (dedup'd after first by the `warnings` module). The commit acknowledges this as a visibility placeholder. Disposition: **(c) NO ACTION** — resolves when lipsync pricing is added.
- **spent_usd lock gap (MINOR, code-quality, PRE-EXISTING — NOT introduced by 46a2cfa).** `cost_tracker.py:319` `self.spent_usd += cost_usd` is unlocked. Harmless today (lipsync cost `$0.00`; adding zero is idempotent), but becomes a **real race when lipsync pricing lands** (concurrent worker threads). Disposition: **(c) NO ACTION on 46a2cfa** (it's clean) — flag as a pre-existing `cost_tracker` item: add a `threading.Lock` around the `+=` (and revisit the sqlite `check_same_thread` gap) *when* any concurrent-path pricing makes the race real.

## Telemetry (cumulative v4.1)
- Lane V #20 (coalesced, Rule #9 CC-1). 2 reviewer subagents (~70k + ~67k tokens).
- Findings: 0 CRITICAL · 0 blocking · 5 MINOR (2 are forward-looking "address-when-prerequisite-lands" advisories: M-2 image-pin guard, spent_usd lock). **0 hallucinations** (CC-2 held — both reviewers ran + listed grep/Read/`git show`; operator spot-confirmed the line refs).
- Cycle-17 Lane V scoreboard: #18 1 CRITICAL (closed `561ad6b`); #19 2 MINOR (both director-disposed); **#20 = 5 MINOR, 0 blocking**.

## Race-ack (Rule #5 / #7)
HEAD `7ce6440` (operator's toggle follow-up #1 fix landed on top of the reviewed commits — disjoint
files: web_server.py + PostProcessingSection.tsx + test, vs the reviewed controller.py). origin/main
`5dfe0d0`; **2 ahead** (`5e979c7` handoff rev2 + `7ce6440` toggle fix); push user-gated. You
transplanted at `5dfe0d0` — this report hands Lane V #20 to the next director (or you, if resumed)
per the Rule #8 awareness gate. Operator cursor unchanged at `T11:27:57Z` (outbound; no incoming).

— Operator-seat, 2026-05-28 cycle-17 post-MID (executed your delegation: Lane V #20 + toggle follow-up #1 shipped `7ce6440`)
