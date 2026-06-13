# Director-Seat Transplant Handoff — 2026-05-28 (cycle 16 CLOSE → cycle-17 entry)

**Outgoing director-seat session:** cycle-16 mid → CLOSE (continued from `6a4accd` handoff)
**Inheritor:** next director-seat at cycle-17 entry
**Prior handoff:** `docs/HANDOFF-director-transplant-2026-05-27-cycle16.md` (`6a4accd`) — **read it for deep cycle-16 context; this doc is the close delta only**
**HEAD at handoff:** `7773502` (Rule #16 mirror); this handoff + ADR-015 + closing FINAL + memory ship in the immediately-following cycle-16-close bundle commit
**Pytest baseline:** 973 / 3 / 0 (verified 2026-05-28: `973 passed, 3 skipped, 10 subtests passed in 29.03s`)
**§15 smoke:** OK
**Cost cumulative:** $8.55-9.10 of $50 (~17-18%); ~$40 headroom
**Cycle-16 state:** ✅ **CLOSED.** Brief v2.0 shipped + signed off + advisory-integrated + Rule #16 codified + ADR-015 + closing FINAL.

---

## TL;DR — 60 seconds

Cycle-16 entry→mid was execution + synthesis + Q7 pivot (see `6a4accd`). **Cycle-16 mid→close** (this session) did: drafted **brief v2.0** full re-author (`c360952`); integrated a **user-principal design advisory** that reframes the test toward **insight-achievement** (`110aff6`); converged with operator at REPLY-cycle-1 (`e86dd55`, no cycle-2); **codified Rule #16** (`7773502`); user **signed off** on v2.0; wrote **ADR-015** + closing FINAL + this handoff. **Push held** (origin at `65903e6`; ~7 commits local-ahead). Cycle-17 is execution-ready under brief v2.0.

**The capstone:** the user handed the SAME advisory to both seats (Shape-A); director + operator independently designed a five-for-five-identical insight-achievement mechanism. Operator's pre-commit-variant draft contributed a Rule #12 grep-verified marker correction. This is the empirical case Rule #16 codifies.

---

## Commit ledger (cycle-16 mid → close; this session)

```
7773502 docs(protocol): codify Rule #16 — binding CLAUDE.md mirror of brief v2.0 §8.2
e86dd55 coord(mailbox): director CONVERGENCE on operator REPLY-1 fd3dc33
110aff6 docs(brief): v2.0 advisory integration + operator REPLY-1 folds — insight-achievement layer + P-ASSEMBLY marker correction
fd3dc33 coord(mailbox): operator REPLY-cycle-1 on brief v2.0 c360952 + stage advisory + cursor
53cc8df coord(mailbox): director decision — brief v2.0 shipped c360952 + REPLY-cycle opened
c360952 docs(brief): comprehensive-test v2.0 full re-author — 6-tier + marker discipline + Rule #16 + cycle-17 phase plan
d16733f docs(arch-sync): operator close LV-1 — ARCHITECTURE §12.6
(+ cycle-16-close bundle: this handoff + ADR-015 + closing FINAL + Rule #16 SHA-fill + memory)
```

---

## What's CLOSED this session

| Item | Status | Ref |
|---|---|---|
| Brief v2.0 full re-author (per Q5 + Q7) | ✅ shipped + signed off | `c360952` |
| User advisory integration (insight-achievement reframe) | ✅ folded | `110aff6` §2.6 + §8.6 |
| Operator REPLY-cycle-1 + convergence | ✅ converged at cycle-1 | `fd3dc33` + `e86dd55` |
| Rule #16 codification (CLAUDE.md mirror) | ✅ Protocol Bundle v5.4 | `7773502` |
| ADR-015 (cycle-16 close decisions) | ✅ this bundle | `DECISIONS.md` |
| Closing report FINAL (§12) | ✅ this bundle | `CYCLE-16-CLOSING-REPORT-2026-05-27.md` |
| Q-V2-1 (Tier-C/D timing) | ✅ user-confirmed 2026-05-28 | brief §8.6.5 / §12.2 |

## 🟡 The ONE open item — push

`c360952`…(close bundle) are **local-ahead, unpushed.** Origin at `65903e6`.
User-principal directed sign-off (#1) + Q-V2-1 (#2) but has NOT yet directed
**push (#3)**. Next director: surface push as the first open question if the
user hasn't already directed it.

---

## Cycle-17 entry — execution-ready under brief v2.0

The plan is locked in **brief v2.0 §11** (P0-P3 roadmap + ownership matrix).
Summary:

| Phase | Work | Owner | Note |
|---|---|---|---|
| 1 | C-D3 ChiefDirector parse-robust | operator Lane B (Rule #14) | **§8.6 pilot** — INTENT field + divergence-log |
| 1 | C-D3 pt2 + C-D5 auto-approve | operator Lane B | bundled `cinema/auto_approve.py` |
| 1 | C-D2 LLMEnsemble parse-robust | operator Lane B | `llm/ensemble.py` |
| 1 | C-D4 setup_runpod.sh harden | director (mea culpa) | PulidInsightFaceLoader + antelopev2; pod one-liner in brief §11.1 |
| 1 | C-D4 pod apply | user (Q6 PRE-AUTHORIZED) | then A9.5 probe GREEN |
| 2 | Tier C-rerun-validation | operator-driven | under insight frame; per-finding criteria |
| 3 | Tier E closed-finding regression | director pytest + operator E2E | brief §6 |
| 4 | Tier F audit re-execution | director subagent | blind-dispatch (brief §7.1) |
| 5 | Tier D PA-* sweep | user decision (Q1 DEFER) | only after PuLID working |

**The §8.6 insight-achievement mechanism is a CANDIDATE (N=0).** Pilot it on
Phase-1 Lane B (intent-field + divergence-ledger from the start;
purpose-verification folded into Phase-1 Lane V). Track the metric:
prediction-match-rate ↑ + INTENT-GAP-frequency ↓, NOT rationale-volume. If
INTENT-GAP doesn't fall, the mechanism is rationale-talk without effect → revert.

---

## What the next director needs to know

1. **Brief v2.0 is the working brief** (`docs/BRIEF-comprehensive-test-v2.0-2026-05-28.md`). v1.0 preserved. Read §2.6 (frame) + §8.6 (mechanism) first — they're the new dimension.
2. **The insight-achievement frame is load-bearing:** product = located divergence-point, not verdict; metric = prediction-match not rationale-volume. Do NOT let it become rationale-talk bloat (that's the explicit failure mode).
3. **Rule #16 is live** (`7773502`); 16 rules active, Protocol Bundle v5.4. Shape-A..D race numbering is canonical (brief §8.1).
4. **C-D4 is the most operationally-impactful open finding** — PuLID-FLUX path still unavailable on pod (`PulidInsightFaceLoader` + antelopev2 missing). Director's `eb6af85` C-B1 fix was incomplete; setup_runpod.sh harden + user pod one-liner (pre-authorized Q6) closes it. Pod `525nb9d5cc0p3y` HTTP/2 200; UNETLoader serves FLUX1-dev-fp8.
5. **Operator-side close pending:** operator does operator-transplant handoff + reconciles MEMORY.md / operator-transplant "Race-N=k" → Shape-A..D (their §3.5 commitment). Check mailbox for their close signal.
6. **Don't push without user direction** (standing). ~7 commits local-ahead.
7. **Pytest 973/3/0; §15 smoke OK.** Don't regress. Phase-1 fixes will push baseline to ~1000-1030 with their TE-C-D* regression cells.

---

## Mailbox state at handoff

Director cursor: `2026-05-28T06:30:51Z` (consumed operator REPLY `fd3dc33`).
Last director-sent: `2026-05-28T06-42-00Z-director-to-operator-decision.md`
(CONVERGENCE). A cycle-16-close `decision`/`fyi` event to operator ships with
the close bundle (director-side close done; operator does operator-side).

---

## Sign-off

Cycle-16 CLOSED. Brief v2.0 shipped + signed off + advisory-integrated +
operator-converged; Rule #16 codified (Protocol Bundle v5.4); ADR-015 + closing
FINAL written. Cycle-17 execution-ready under v2.0 §11. One open item: push
(user-gated). The insight-achievement reframe is the cycle's lasting
contribution — the harness is now a divergence-mining engine, not a
verdict-machine, with a falsifiable metric to keep it honest.

Signed,
Director-seat — 2026-05-28 (cycle-16 close).
