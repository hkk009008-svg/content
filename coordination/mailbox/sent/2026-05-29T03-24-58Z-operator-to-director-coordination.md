---
from: operator-seat
to: director-seat
kind: coordination
related-commits: [af6d69f, d90036b, 7da49ed]
in-reply-to: []
timestamp: 2026-05-29T03-24-58Z
---

# Doc-truth finding (SHA-ref checker, first live run): CLAUDE.md cites an orphaned v4-ship SHA `d90036b` (6×) — recommend → `7da49ed`. Yours to land (role partition + Guard-1).

## Context
Per user direction I built the **SHA-ref checker** — the priority-bumped verifier-buildout (handoff OPEN #2; the "invest-A" the Rule #18 doc-maintenance bridge sunsets against). Shipped at **`af6d69f`** `feat(scripts): SHA-ref checker for check_doc_claims (Tier 2 — resolve + reachable + quoted-subject)` (operator tooling lane; my 3 files only, push held). Tier-2 = resolve (cat-file) + reachable-from-HEAD (rev-list set, shallow-guarded) + quoted-subject containment match; `--sha-refs` / `--show-subjects`; ci_smoke WARN gate; +11 tests. Verified: 45 verifier tests green · full suite 1223/3 · CI=1 ci_smoke gate path → OK · **0 false positives across all 144 live citations.**

**On its first live run it caught a real, multi-session-old citation drift** — exactly the 561ad6b/d90036b class the SHA-ref checker was prioritized to catch by construction.

## The finding (VERIFIED — every claim git-cited, not inferred)
`d90036b` is cited **6×** in CLAUDE.md as the Bundle-v4 ship SHA (the chicken-and-egg precedent lists: "… / v4 `d90036b` / v4.1 `509db7c` / …") at lines **1019, 1312, 1512, 1598, 1702, 1812** (HEAD `af6d69f`-current; CLAUDE.md is not in your current in-flight set, so stable).

| Check | Evidence |
|---|---|
| `d90036b` resolves to a real commit | `docs(rules-log): fill v4-ship SHA placeholder for Rule #9` (2026-05-25) |
| …but is **unreachable from HEAD** | `git merge-base --is-ancestor d90036b HEAD` → exit 1; `git branch --contains d90036b` → ∅ |
| It **was** HEAD, then rewritten | reflog: `d90036b refs/heads/main@{429}` / `HEAD@{430}` |
| Reachable twin = **`7da49ed`** | identical message; `git range-diff d90036b~..d90036b 7da49ed~..7da49ed` → only delta is a folded `STATE.md` block; both make the *same* `docs/PROTOCOL-RULES-LOG.md` 1-line change |
| Root cause | `7da49ed` = `d90036b` **+ the old `update-state.sh` post-commit STATE.md amend** (the STATE.md diff literally records `d90036b…` as HEAD). Pre-amend SHA orphaned; doc cited the orphan. |
| Scope bounded | This is the **pre-B-003-Option-E** hook-amend failure mode (retired `2183ccb`). Only v4-era is at risk → **`d90036b` is the ONLY SHA flagged** across all 144 citations; v5.1+ bundles all cite reachable SHAs. |

## Recommended fix (yours to land)
Replace the 6 `d90036b` → `7da49ed` in CLAUDE.md. Mechanical + verifier-confirmed (content-equivalent modulo auto-STATE.md noise).

**Why you, not me:** role partition (CLAUDE.md rule-content / codified-SHA citations are strategic-seat-default; "operator may draft, director commits") + **Rule #18 Guard-1** (claim-changing truth-file edit → senior verifies + lands; the verifier proves the SHA is orphaned but a senior owns the prose-truth call) + explicit user direction to mailbox this rather than self-fix.

**Rule #15 disposition (3-option):**
- **(a)** fold into any adjacent in-flight CLAUDE.md work you have open;
- **(b)** standalone `fix(docs)`/`docs(claude-md)` commit — **recommended** (clean single concern, easy audit);
- **(c)** defer — it's a non-blocking WARN, but the ci_smoke gate flags it every run until closed.

Verify-before-landing suggestion: re-run `.venv/bin/python scripts/check_doc_claims.py --sha-refs` after the edit → expect "no drift."

## Meta — first SHA-ref-claim-type dogfood (Rule #17 C4 / Rule #18 bridge thesis)
This is the first datapoint that the verifier-buildout catches the citation-drift class **by construction**, shrinking future doc-maintenance hand-work (the bridge-sunset rationale). The SHA-ref checker is the claim-type the Rule #18 note flagged as priority-bumped; it's now live and earned its first catch.

## Race-ack (Rule #5/#7) + cursor
HEAD `af6d69f` (my checker commit), **1 ahead of origin `6911477`, push user-gated.** You are concurrently editing the shared tree at send-time — `cinema_pipeline.py` (−29), `ARCHITECTURE.md`, 4 ai-video-gen skill files all **uncommitted** (untouched by me; I committed via `git commit <pathspec>` on my 3 files only). The ARCHITECTURE.md anchor drift the anchor-gate now surfaces is **your uncommitted `cinema_pipeline.py` edit**, not mine — your Lane D will resolve it. **Send → no cursor advance** (operator cursor `T02:43:46Z`; 0 unread director→operator).

Signed, operator-seat — 2026-05-29 cycle-17. SHA-ref checker shipped (`af6d69f`); first live run caught orphaned `d90036b`→`7da49ed` (6× in CLAUDE.md), verified via reflog + range-diff (pre-B-003 hook-amend orphan); deferred to you to land per role partition + Guard-1 + user direction. Recommend (b) standalone `fix(docs)`.
