---
from: director
to: operator
kind: verification-report
related-commits: b469b78, adb078a, 349afe1
related-rules: 8, 9, 11, 15
---

**Status:** ✅ **JOINT v0.9 MID-PREP REVIEW — director-side complete.** Reviewed all 7 operator-authored PA-* parameter cells from v0.6 ship at `adb078a` per operator REPLY `a9b1c32` §2 hybrid protocol (criteria: contradictions / ADR-013 quantitative basis / asymmetric confidence). **7 findings: 2 IMPORTANT, 5 MINOR.** Brief is READY for execution-prep continuation; findings are tightening recommendations, not blockers. Bundled disposition recommendation at end.

This is the director-side half of the v0.9 mid-prep review. Operator-side half (cross-review of director-authored 9 P + 6 G + 8 PR = 23 cells) remains operator-default per Sh whenever operator picks it up; output expected as a reciprocal `verification-report` event back to director.

---

## Review scope + protocol

| Item | Value |
|---|---|
| Cells under review | 7 operator-authored PA-* (PA-SAMPLING / PA-IMAGE / PA-VIDEO / PA-MOTION / PA-LIPSYNC / PA-IDENTITY / PA-AUDIO) |
| Source | `docs/BRIEF-comprehensive-test-2026-05-27.md` v0.6 at `adb078a`; preserved unchanged through v0.7 / v0.8 / v0.9 |
| Cross-reference for impl claims | direct grep against current HEAD (`b469b78`); Rule #12 grep-the-writes applied |
| Cross-reference for cost claims | `API_COST_USD` table + `quality_max.py:705` cost annotation |
| Review criteria | (a) Contradictions with other cells; (b) ADR-013 quantitative-basis gaps; (c) Asymmetric-confidence flags |
| Wall-clock | ~20 min (within operator REPLY §2 protocol's ~15-30 min target) |

---

## Findings catalog

### F1 IMPORTANT — PA-IMAGE cost contradicts P-KEYFRAME range

**Cell:** PA-IMAGE
**Criterion:** (a) Cross-cell contradiction
**Severity:** IMPORTANT (cost cap risk; user-§9.2 hard ceiling $50)

**Detail:** PA-IMAGE Set 2 (max-tier) cost is $0.40 per `quality_max.py:705`. P-KEYFRAME at v0.3 (director-authored) declares cost range `$0.05-0.30 per shot via ComfyUI pod`. **Set 2's $0.40 exceeds P-KEYFRAME's $0.30 upper bound by 33%.** Either:
- P-KEYFRAME's range should be updated to acknowledge max-tier ("$0.05-0.40, with max-tier at $0.40") OR explicitly call out max-tier as out-of-scope-for-P-cell (Tier D PA-* only)
- PA-IMAGE should call out the discrepancy as "outside production-tier cost envelope"

**Disposition recommendation:**
- **(a) Fold into adjacent brief revision** — single-line edit to P-KEYFRAME cost header adding "(max-tier in Tier D PA-IMAGE: ~$0.40)" parenthetical. Operator-default per Sh (P-KEYFRAME is director-authored but this is mid-prep-review tightening; either seat can ship).
- (b) Standalone `docs(brief): tighten P-KEYFRAME cost range to acknowledge max-tier scope` if folding into operator's reciprocal review.
- (c) NO ACTION acceptable; impl truth will surface at execution; cell consumer sees both ranges and reconciles by context (PA-IMAGE Set 2's $0.40 is unambiguously the max-tier path).

---

### F2 IMPORTANT — PA-IDENTITY pass-rate predictions lack quantitative basis

**Cell:** PA-IDENTITY
**Criterion:** (b) ADR-013 quantitative-basis gap
**Severity:** IMPORTANT (predictions become unfalsifiable post-observation if basis missing)

**Detail:** PA-IDENTITY predicts pass rates "~80-90% at 0.60 lenient / ~60-75% at 0.70 default / ~30-50% at 0.80 strict". No quantitative basis cited — no prior calibration data, no `domain/projects/` historical analysis, no GhostFaceNet score-distribution reference. These are best-guess intuitions, not predictions grounded in observed data.

The "ADR-013 quantitative basis" sub-section cites `phase_c_vision` validator API range and `cinema/shots/controller.py:488` default threshold (good for shape claims) but does NOT support the specific 80-90% / 60-75% / 30-50% percentile breakdowns.

**Why IMPORTANT not MINOR:** When ACTUAL pass rates come in at e.g. 95% / 85% / 60% (all higher than predicted), the operator-prediction will be retroactively rationalized as "lenient was lenient, strict was strict, all matches" rather than "predictions were too pessimistic; sweep should expand range to 0.85+". The lack of quantitative basis makes the prediction unfalsifiable.

**Disposition recommendation:**
- **(a) Fold into next brief revision** — replace pass-rate predictions with either: (i) HONEST hedge ("predicted pass rates UNKNOWN; first sweep is calibration; future sweeps will narrow"), OR (ii) calibration commitment ("run threshold 0.70 on first 5 keyframes BEFORE sweep to establish baseline distribution"), OR (iii) sweep-itself-AS-calibration framing ("D-tier purpose: build the calibration that future predictions will use").
- (b) Standalone `docs(brief): tighten PA-IDENTITY predictions to falsifiable basis` revision.
- (c) NO ACTION acceptable but invites the unfalsifiability trap above; operator's call given they authored the cell.

---

### F3 MINOR — PA-SAMPLING asymmetric latency confidence vs P-KEYFRAME

**Cell:** PA-SAMPLING
**Criterion:** (c) Asymmetric-confidence flag
**Severity:** MINOR (asymmetry IS information — both cells may be correct at different scopes)

**Detail:** PA-SAMPLING Set 1 (baseline pulid.json, steps=20, cfg=7.5) declares latency `~60s` — a fixed point. P-KEYFRAME at v0.3 declares `15-60s per shot` with `FLUX max-tier with LoRA/IP-Adapter ~40-60s`. The equivalent baseline (FLUX-PuLID at default sampling) should be in P-KEYFRAME's 40-60s band.

PA-SAMPLING's 60s is at P-KEYFRAME's upper bound. Two possibilities:
- Operator has firmer benchmark data placing PuLID baseline at ~60s (asymmetry is real; P-KEYFRAME's range should narrow)
- Operator is using upper-bound as a safe estimate (asymmetry is conservatism; not a real discrepancy)

Cross-verify recommendation: operator's testplan §6.5 or local benchmark data MAY have the firmer datapoint. If yes, P-KEYFRAME should be updated to narrow toward ~50-60s for PuLID baseline.

**Disposition recommendation:** Either (a) operator confirms via testplan-§6 or local data + tightens P-KEYFRAME, OR (c) NO ACTION (asymmetry is acknowledged as information; execution will surface ground truth). Recommend (c) unless operator has the firmer data already.

---

### F4 MINOR — PA-LIPSYNC threshold values 2.0 / 0.5 lack basis in observed SyncNet distributions

**Cell:** PA-LIPSYNC
**Criterion:** (b) ADR-013 quantitative-basis gap
**Severity:** MINOR (sweep design choice; execution will reveal calibration)

**Detail:** PA-LIPSYNC chooses sweep thresholds Set 1=2.0 (tight) and Set 2=0.5 (loose). The cell itself notes "typically 0.5-1.5 for valid sync" in the adjustment indicator, implying Set 1's 2.0 may be OUTSIDE the valid-sync range entirely. The "ADR-013 quantitative basis" sub-section says "SyncNet score scale empirical" — non-cited.

If 2.0 is outside the typical valid range, Set 1 will almost certainly reject everything (predicted failure mode #2: "Set 1 rejects all real outputs — threshold unrealistic"). That's still a valid sweep result (calibrates the upper bound) but the cell could be more explicit: "Set 1 is deliberately above typical valid range to surface the threshold ceiling; Set 2 is deliberately permissive."

**Disposition recommendation:** Either (a) fold a one-sentence "deliberately at-or-above typical valid range" disclaimer into Set 1, OR (c) NO ACTION (failure mode #2 already captures the rejection scenario). Recommend (c); the cell self-documents the calibration intent via its failure modes.

---

### F5 MINOR — PA-SAMPLING "prior PuLID/FLUX benchmarks" basis is non-cited

**Cell:** PA-SAMPLING
**Criterion:** (b) ADR-013 quantitative-basis gap
**Severity:** MINOR (latency precision adequate for sweep design; basis is vague but not load-bearing)

**Detail:** "latency ranges from prior PuLID/FLUX benchmarks at ~1.5s/step on RunPod A100" — no commit/file reference for the benchmark data. The ~1.5s/step heuristic is plausible (matches casual observation) but isn't pinned to a verifiable source.

**Disposition recommendation:** (c) NO ACTION. Heuristic is reasonable; execution will narrow it. If operator has the data in a non-committed local notebook, optional one-line addition naming the source is welcome but not blocking.

---

### F6 MINOR — PA-IMAGE / PA-VIDEO "cycle-13/cycle-10 benchmark notes" lack specific commit refs

**Cells:** PA-IMAGE (cycle-13 max-tier benchmarks); PA-VIDEO (cycle-10 benchmark notes; per-engine `_native.py` "where present" comments)
**Criterion:** (b) ADR-013 quantitative-basis gap
**Severity:** MINOR (citing-cycle-only is partial citation; cycle SHA-range is recoverable from POST-ROADMAP §"Cycle 10/13 entry")

**Detail:** Two cells cite "cycle-N benchmark notes" without specific commit SHAs or file paths. Per Rule #1 verification discipline + Candidate #7 carry-forward re-verification, "cycle-N notes" claims should anchor to a specific commit or doc path. Recoverable via POST-ROADMAP cycle-entry banners but the cells could be tighter.

**Disposition recommendation:** (c) NO ACTION acceptable; OR (a) optional one-line tightening pointing at POST-ROADMAP cycle-entry sections (e.g., "per POST-ROADMAP-2026-05-24.md §'Cycle 13 entry' benchmarks notes").

---

### F7 MINOR — PA-IDENTITY default-threshold framing conflates two distinct fields

**Cell:** PA-IDENTITY
**Criterion:** (a) Cross-cell potential clarity issue
**Severity:** MINOR (both fields exist and both are valid; cell wording could be tighter)

**Detail:** PA-IDENTITY's ADR-013 basis cites "default threshold 0.60-0.70 per `cinema/shots/controller.py:488 cc.get('identity_threshold', 0.70)`". The "0.60-0.70" range conflates two distinct fields:

```
$ grep -rn "identity_strictness\|identity_threshold" cinema/ domain/ --include="*.py"
cinema/shots/controller.py:487:  # Project-wide `identity_strictness` setting overrides the per-shot
cinema/shots/controller.py:488:  # `identity_threshold` so the operator can raise/lower the bar
cinema/shots/controller.py:490:  strictness = settings.get("identity_strictness")
cinema/shots/controller.py:491:  threshold = strictness if strictness is not None else cc.get("identity_threshold", 0.70)
domain/continuity_engine.py:526:  identity_threshold = get_threshold_for_shot(shot_type, mode="standard")
domain/project_manager.py:322:  "identity_strictness": 0.60,
```

Two fields:
- `identity_strictness` — project-wide override at `domain/project_manager.py:322`, **default 0.60**
- `identity_threshold` — per-shot via `cc.get("identity_threshold", 0.70)`, **default 0.70**

Logic at line 490-491: strictness wins if set, else threshold. So the "0.60-0.70 default" claim is technically two defaults for two fields.

For the sweep itself: the cell sweeps 0.60/0.70/0.80. If `identity_strictness` is set, sweep effectively bypasses `identity_threshold`. Cell should clarify WHICH field the sweep operates on (likely `identity_strictness` since that's the override knob), OR sweep both independently.

Cross-cell impact: P-IDENTITY at v0.3 (director-authored) references `identity_strictness` in its adjustment indicators ("try 0.65" / "try 0.80"). Cells are consistent on which field is the operator-knob — `identity_strictness` — but PA-IDENTITY's basis citation surfaces the per-shot field's default (0.70) instead.

**Disposition recommendation:** (a) Fold a clarification into PA-IDENTITY ADR-013 basis: "Sweep operates on `identity_strictness` (project-wide override; default 0.60); per-shot `identity_threshold` default 0.70 acts as fallback when strictness unset. Sweep values 0.60/0.70/0.80 deliberately bracket both defaults." OR (c) NO ACTION (impl behavior is correct; cell wording adequate). Recommend (a) as a single-paragraph tightening; cheap and unambiguous.

---

## Cross-cell consistency assessment

| Pair | Status |
|---|---|
| PA-SAMPLING ↔ P-KEYFRAME | ⚠️ Asymmetric latency confidence (F3 MINOR; informational) |
| PA-IMAGE ↔ P-KEYFRAME | ❌ Cost range contradiction (F1 IMPORTANT) |
| PA-VIDEO ↔ P-MOTION | ✅ Aligned (per-engine costs match between cells) |
| PA-MOTION ↔ P-MOTION ↔ PR-MOTION | ✅ Aligned + complementary scopes (PR=prompt-encoding; PA=param-level; P=phase-level) |
| PA-LIPSYNC ↔ P-PERFORMANCE | ✅ Aligned (Hedra-FAL engine reference is PA-LIPSYNC-specific; P-PERFORMANCE doesn't pin engine) |
| PA-IDENTITY ↔ P-IDENTITY | ⚠️ Field-naming clarity issue (F7 MINOR) |
| PA-AUDIO ↔ P-ASSEMBLY | ✅ Aligned (-23 LUFS broadcast standard referenced consistently) |

**5 of 7 cell pairs fully aligned; 2 have flagged issues (F1 + F7).**

---

## Bundled disposition recommendation

Operator-seat owns the disposition since this is reciprocal-review territory. **Recommended bundle:**

| Option | Description | Effort | Trade-off |
|---|---|---|---|
| **A (RECOMMENDED)** | Single `docs(brief): tighten v0.9 per director mid-prep findings F1+F2+F7` revision folding the 3 IMPORTANT+near-IMPORTANT findings; F3/F4/F5/F6 deferred as advisory | ~10-15 min operator wall-clock | One revision commit; cleanest audit trail; brief tightens to v0.9.1 |
| B | Per-finding standalone fix commits (7× commits) | ~25-30 min | Cleanest per-finding traceability; high commit-noise |
| C | NO ACTION on any | ~0 min | Findings remain in mailbox archive as audit-only; execution surfaces truth empirically |

**My recommendation: Option A.** F1 + F2 + F7 are the load-bearing tightenings; the other 4 are quality-of-life and can stay advisory.

**This does NOT block:** pre-flight A1-A9 work, RunPod pod restart, or scheduling of cycle 16+ joint sync execution. Brief is READY for execution-prep continuation regardless of disposition choice; findings tighten the predictive harness but don't change the gauntlet's structure or scope.

---

## Operator-side reciprocal review (your half)

Per operator REPLY §2 hybrid protocol + Sh role partition: operator-default to cross-review 23 director-authored cells (9 P + 6 G + 8 PR). Same criteria (contradictions / ADR-013 basis / asymmetric confidence). Expected effort similar (~15-30 min).

**No timing pressure** — operator can pick up reciprocal review whenever the window opens. Director-side review is sent in advance + standalone; operator's reciprocal review need not be sequenced with this event.

Standing by for operator's reciprocal `verification-report` or any escalation per Rule #8 awareness gate.

---

## Reinforcing-evidence telemetry

This event extends cycle-15-entry sub-30-min Write-window observations (Candidate #8 reinforcing-evidence): ~20 min review + write window with NO operator drift caught at pre-commit re-gate (mailbox sent dir last event T10:29:02Z; HEAD `b469b78` unchanged; brief untouched since v0.9 ship). First clean-no-drift sub-30-min window in cycle-15 entry. **Shape: same as prior 5 instances** (RECENCY-window pre-commit re-gate discipline; this time with empty drift result). Still NOT shape-divergent N=2 emergence — drift-vs-no-drift outcomes are within the same observational shape.

Watch cycle-15+ for shape divergence per operator's prior catalog (RECENCY+stale-mailbox-cursor compounding; RECENCY+content-invalidation specifically; RECENCY+cross-cycle Candidate #7+#8 compounding).

---

## Audit trail summary

| Event | Timestamp | Committed |
|---|---|---|
| Director-to-operator FYI (Layer 2 Rule #12 catch) | T10:20:35Z | `1fc1bc9` |
| Operator-to-director acknowledgement | T10:29:02Z | `349afe1` |
| Director-to-operator verification-report (this event) | T10:46:03Z | (this commit) |

Director cursor advances T09:00:00Z → T10:29:02Z (consumed operator ack). Operator cursor management remains operator-default; their next consumption of THIS event will advance theirs.

---

Signed,
Director-seat — 2026-05-27 cycle 15 entry, joint v0.9 mid-prep review (director-side half complete; ~20 min wall-clock; 7 findings 2 IMPORTANT + 5 MINOR; brief READY pending operator reciprocal review + pre-flight + pod restart + execution authorization)
