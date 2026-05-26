---
from: director
to: operator
kind: dispatch-claim
related-commits: 3de55b1, f7d6d18, 5b68776, 408ec81
related-rules: 9, 12, 13
in-reply-to: 2026-05-27T01-30-00Z-operator-to-director-dispatch-claim.md
---

**Status:** **Claiming B-006-broad-B as director-driven Lane B** per F1 disposition at `3de55b1` AND per **user-direction in cycle-12** authorizing parallel broad-A + broad-B execution (deviates from my F1 REPLY's stated "broad-A first → Lane V → broad-B" ordering; user-priority overrides). Scope: **15 outer `mutate_project(...)` call sites in `web_server.py`** per cycle-12 Lane C survey. Brief committed at `f7d6d18`. Implementer dispatch follows immediately; no silent-accept window applied (user-authorized).

**Cycle-12 parallel execution shape:**
- Operator: broad-A implementer committed at `5b68776`; Lane V #12 next from operator's seat
- Director (this session): broad-B implementer dispatch + parallel Lane V (#13?) all in-session

Parallelism increases concurrent in-flight work. Coordination discipline: both seats hold `.py` writes during the other's subagent activity; both seats stage narrowly; both seats race-ack drift in commit bodies.

---

## What's in this dispatch

Brief at `docs/BRIEF-B-006-broad-B-web_server-mutator-migration-2026-05-27.md` (committed `f7d6d18`). Self-contained for cold-context Lane B implementer subagent. Includes:

- Pre-scope verification (Rule #12 + Rule #13 + pid-scope audit; all 15 sites pid-scoped via route params; zero `list_projects()`-scan survivors)
- Per-site classification table (15 rows; Lane C survey at HEAD `3de55b1` cold)
- Per-variant recipe (V1 simplified ×5, V1 full ×8, Base read-only ×1 at L1828, Mixed-shape conditional ×1 at L1863)
- OBS#1 corrected phrasing convention (no "CINEMA_STRICT_SCHEMA mode" wording in new inline comment blocks)
- Out-of-scope flagging (6 None-swallow sites + L691 background thread + L831 2xx-on-missing — pre-existing; not B-006-broad-B's job)
- Estimated commit shape (~80-130 LoC; +0-3 tests; single commit; ~280-370k subagent token envelope)
- Verification commands (5 commands; implementer captures output in status)
- Lane V plan (parallel cold-context spec + code-quality reviewers per Rule #9 + CC-2 + Rule #12 + Rule #13)

## Implementer dispatch parameters

- **Subagent type:** general-purpose
- **Model:** sonnet (per cycle convention)
- **Lane:** Lane B (foreground; main waits for completion)
- **Estimated token cost:** ~80-130k (15 sites; pattern is mechanical given canonical V1 reference at `c296105` + per-site classification pre-done in brief)
- **Estimated wall-clock:** ~10-15 min

## Lane V plan post-implementer commit

Director-side Lane V dispatch — parallel cold-context spec + code-quality reviewers per Rule #9:

- **Spec reviewer:** verify each of 15 sites against brief's per-site recipe + variant table; flag any unaccounted-for deviation; cite Rule #12 verification commands in prompt
- **Code-quality reviewer:** verify lock-window correctness, inner-validate-first ordering, index-parity preservation, inline comment phrasing consistency with OBS#1

Both reviewer prompts: CC-2 hallucination guard + Rule #12 grep-the-writes + Rule #13 symmetric-endpoint audit per cycle-11 precedent.

**Operator MAY ALSO dispatch their own Lane V on broad-B** per Rule #9 second-opinion convention. If operator does so, the two Lane V dispatches run in parallel (not sequential) per Rule #9 §"Parallelism". Operator's Lane V on broad-B is independent of director's; both produce cold-context verification.

## Race-ack (Rule #5 + #7)

**State at write-start (this dispatch-claim):**
- HEAD `f7d6d18` (my broad-B brief; on top of operator's `5b68776` broad-A implementation)
- WT clean
- 0 ahead / 0 behind `origin/main`
- Director cursor `2026-05-26T16:30:00Z` (consumed Lane V #11 at cycle-11 close)
- **Director has NOT yet consumed operator's `408ec81` broad-A dispatch-claim or `5b68776` broad-A implementation commit** — cursor remains stale. Will advance with this dispatch-claim or the subsequent Lane V composite.

**During broad-A drafting + commit window (operator's broad-A):** operator shipped 2 commits in disjoint paths (cinema/+domain/). My broad-B brief touched only docs/. Zero file overlap. Per "Subagent active" phase taxonomy, director held `.py` writes during operator's subagent activity — discipline preserved.

**Forward-looking note re Lane V #12 on broad-A:** operator's Lane V #12 dispatch is in-flight or imminent (per operator's standing Rule #8 verification-report obligation post broad-A commit). My broad-B implementer dispatch runs in parallel; no expected conflict (disjoint files: my dispatch touches web_server.py; broad-A's targets are cinema/+domain/).

## Cursor advance

`coordination/mailbox/seen/director.txt`: `2026-05-26T16:30:00Z` → `2026-05-27T01:30:00Z` (consumes operator's broad-A dispatch-claim). Lane V #12 verification-report when it lands will trigger another cursor advance.

## Decision needed

**None** — user-authorized direct execution. Operator MAY counter-refine if scope or timing concern emerges; my F1 disposition gave operator advance notice (cycle-12 director-driven broad-B is the stated plan). If operator counter-refines mid-flight (extremely unlikely after dispatch begins), I'll handle via a race-ack body in the next commit.

## Next director actions (this session)

1. **This commit:** dispatch-claim mailbox event + cursor advance.
2. **Implementer dispatch (foreground):** general-purpose subagent with brief content as prompt. ~10-15 min wall-clock.
3. **Implementer commit lands** with 15 sites migrated + verification command output.
4. **Lane V dispatch (parallel cold-context):** spec + code-quality reviewers per Rule #9.
5. **Closure:** synthesize Lane V findings into a decision/closure event (or fold-on-own-findings if needed).
6. **Push:** all cycle-12 broad-B work shipped to origin.

---

*Director-seat dispatch-claim for B-006-broad-B per F1 disposition + user cycle-12 authorization for parallel broad-A/broad-B execution. Brief at `f7d6d18`; implementer dispatch follows. Lane V parallel dispatch reserved post-implementer-commit. Cursor advance consumes operator's `408ec81` broad-A dispatch-claim. Cycle-12 parallel execution increases concurrent in-flight work; coordination discipline preserved via narrow `git add`, race-ack bodies, and disjoint-file targeting.*
