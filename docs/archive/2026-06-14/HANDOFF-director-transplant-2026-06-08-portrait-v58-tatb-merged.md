# Director transplant handoff — 2026-06-08 (portrait-P1 review+merge · v5.8 · T-A/T-B merged)

**Read this if you are the next director-seat picking up.** Companion:
operator wrote their own transplant handoff this same session —
[`HANDOFF-operator-transplant-2026-06-08-v58-u3-ta-tb-shipped.md`](HANDOFF-operator-transplant-2026-06-08-v58-u3-ta-tb-shipped.md)
(`0daf787`). The two are complementary by role partition (each seat owns their
own transplant doc); read both for the full picture.

## Verification at write (ADR-013 / Rule #1-4 — cited, cold-swept `wf_f485387f`)

```
origin/main == local main == c28f9e6   (GREEN)
feat/max-tier-provisioning: local HEAD == 0daf787 (operator's handoff), origin/feat == 6ebfc09
  → feat is 1-2 mailbox/handoff commits ahead of main; main carries all CODE.
FF-clean: c28f9e6 is the merge-base of origin/main..HEAD (clean ancestor).
suite: 1764 passed / 0 failed   [env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit]
        (run at c28f9e6, the merge SHA; cross-confirmed by operator's handoff)
ci_smoke: OK   [.venv/bin/python scripts/ci_smoke.py]
mailbox: director cursor 2026-06-07T23:08:17Z, 0 unread to-director.
working tree: clean (0 dirty tracked after `git read-tree HEAD`).
```

A 5-agent cold verification workflow (read-only, Rule #17) confirmed every claim
below — 0 REFUTED, 0 UNCERTAIN. It corrected 3 things session-memory had slightly
wrong (origin/feat ≠ c28f9e6 it's 6ebfc09; the "72/109/703" anchor fix was
ARCHITECTURE.md's web_server.py lock table not chief_director; tickets were
OPEN at sweep-time — operator closed them seconds later in `0daf787`).

## 0. TL;DR + #1 pickup

`main` is GREEN at `c28f9e6` and carries the **entire session's work** (two clean
FF-merges). **Nothing is owed; 0 unread mailbox; no in-flight blockers.** This was
a ship-heavy session, not a half-done one.

**#1 pickup (forward, capability-max per PROGRAM-MANUAL intent):** **Portrait
delivery Phases 2 + 3** — Phase 1 (9:16 gated, assembly/scorecard/API/FE) shipped
this session; Phase 2 = native per-aspect image keyframes, Phase 3 = per-provider
9:16 video + un-gate. Matrix in the portrait spec §7-D (today only Veo does native
9:16; Kling cannot; Sora/LTX unverified). Own-spec-later — brainstorm/spec first.

**#2 (cheap cleanup, either lane):** the two tracked follow-ups in §2.

## 1. What shipped this session (the arc)

Three landed workstreams, two FF-merges (`96a9ad1 → fff6759 → c28f9e6`):

1. **Portrait/aspect Phase-1 — reviewed (both passes ✅) + polished + merged.**
   - Director 7-dim cross-cutting review + operator coalesced Lane V (`21076f9`)
     both → ✅ READY / 0 blocking. Findings converged (F1/M3) + operator caught
     **I1** (resolver honors 9:16 while gate excludes → silent portrait-flip risk).
   - Converged polish bundle **`fff6759`**: I1 guard (`is_supported()` fallback at
     assembly, `cinema_pipeline.py:1370-1376`), dead `EXPECTED_RESOLUTION` removed,
     F2 docstrings, M3 EditorialShell `'9:16'→'16:9'`, `'16:9'→DEFAULT_ASPECT_RATIO`,
     verify_llm_caching timeout, **DT-1** ARCHITECTURE.md lock-table anchors
     (72/109/703). FF-merge #1 = `fff6759` (39 commits).
2. **Protocol Bundle v5.8 — consented + text-shipped** (`b5413da` + REPLY `86f6013`).
   Operator's `_sync_seat_index()` hook (`454e770`+fold `a614f68`) auto-refreshes a
   stale per-seat index on peer-commit staleness (C1 only; staged-WIP excluded by
   construction) — **retires the D-a phantom-deletion storms.** Director did an
   independent Rule #9 review (converged with operator's ✅ READY `31d5c96`). Text:
   CLAUDE.md Rule #19 §Topology + AGENTS.md mirror + README §Per-seat-launch +
   PROTOCOL-RULES-LOG v5.8 entry + self-mod-gate note.
3. **T-A + T-B reassembly-audio — merged** (FF-merge #2 = **`c28f9e6`**, 8 commits).
   - **T-A** (Cartesia DOA, HIGH): per-provider voice mapping + skip-without-HTTP
     guard + a **ko-normalization live catch** (`ffabcf2`) — 4 reviewers + 39 unit
     tests missed it; only the real Korean re-assembly exposed `'ko'`-vs-`'Korean'`.
     First-ever successful Cartesia 200 (no ElevenLabs fallback), runtime-proven.
   - **T-B** (re-assembly TTS, MEDIUM): content-hash-keyed audio reuse (zero-TTS
     re-assembly when unchanged) + atomic `.part`+`os.replace` publishes (no
     cache-poison) + TTS spend surfaced in estimate + temps off CWD.
   - Operator implemented (user-directed "do t-a t-b") + dual cold reviews +
     live-verified; director re-verified green independently + merged the exact
     verified SHA. Tickets doc flipped CLOSED by operator (`0daf787`).

## 2. Open items (tracked in TaskCreate; none blocking)

- **Task #5 — F5: render `visual_findings` in the deep-diagnose FE panel.** Backend
  plumbs it (`cinema/shots/controller.py:1959` → `advisory_deep`), but
  `web/src/components/pipeline/ReviewStage.tsx:817-849` renders 4 sibling fields and
  NOT `visual_findings` (grep: 0 matches in `web/src/`). Feature gap, low priority.
- **Task #7 — Rule #18 doc-maintenance: MANUAL/digests anchor sweep.** ~30+ stale
  line-anchor occurrences in `docs/PROGRAM-MANUAL.md` + `docs/PROGRAM-MANUAL-digests.md`
  for `llm/chief_director.py` (grew to 664 LOC: `validate_shot_prompts` doc:226 →
  actual:296; `evaluate_generation_quality` doc:318/336 → actual:406;
  `get_diagnostic_summary` doc:490 → actual:653; `_call_llm` doc:82 → actual:85) and
  `phase_c_vision.py` (±1-9: `validate_identity_vision` 242→236, etc.). Mechanical
  (Rule #18 launch scope = line-anchors) — but the prose SHA/status annotations
  (e.g. digests' ":318 stale → :336", itself now stale) are claim-bearing →
  senior-review per Guard-1. ARCHITECTURE.md §13.4 uses a bare file link (NOT stale).
- **DONE this session (not open):** T-A/T-B tickets-doc CLOSED-flip — operator did it
  in `0daf787`.

## 3. Coordination / operator state

- Operator was **active concurrently the whole session** (the "offline" presence at
  my session-start was Rule #19 lag, not absence). They shipped: all 4 vision tickets
  incl. multi-char `fe2aa47`, the v5.8 hook, U3 dashboard dogfood (✅ PASS, 3 findings
  → T-A/T-B tickets), and T-A/T-B implementation. Their transplant handoff is `0daf787`.
- **Mailbox:** director cursor `23:08:17Z`, **0 unread**. The v5.8 + T-A/T-B event
  trail is complete and consumed both ways. My last sent: `23:29:45Z` (T-A/T-B
  merge-notice), consumed by operator.
- **Branch nuance:** `main`==`c28f9e6` has all code; `feat` local is ahead by
  handoff/coord commits (origin/feat==`6ebfc09`, local HEAD==`0daf787`+this commit).
  Next code merge FFs main past these. Push `feat` after committing this handoff.

## 4. Key learnings (memory-pointers + technique)

- **D-a-safe FF-merge (no checkout):** `git push origin <verified-sha>:main` FFs the
  remote main ref WITHOUT switching the shared working tree out from under the live
  peer; then `git branch -f main <sha>` + `git push origin feat`. NEVER `git checkout
  main` while the other seat is active. Used for both merges this session.
- **Merge the verified SHA, not "feat HEAD":** push the exact SHA you ran the suite
  against (`c28f9e6`), so `main` only ever advances to a personally-verified state
  even as the peer keeps committing.
- **`GIT_INDEX_FILE` pytest footgun** (memory `da_git_index_file_breaks_pytest_temp_repos`):
  run the suite with `env -u GIT_INDEX_FILE` or ~9 `check_doc_claims` temp-repo tests
  false-fail. v5.8's hook fixes the *status*-phantom side; the pytest side persists.
- **Live-verify > static review for runtime contracts:** the ko-normalization bug
  passed 4 cold reviewers + 39 unit tests (which used `"Korean"`); only re-assembling
  a real `'ko'` project caught it. The operator's implement→review→**live-verify**
  flow earned its keep.

## 5. Forward direction (post-roadmap)

Part-3 program is fully on main (max-tier + dialogue + Plan-2 tests + portrait P1 +
v5.8 + reassembly-audio). The capability frontier per PROGRAM-MANUAL §5 is **portrait
Phases 2/3** (#1 above). Secondary: the documented T-B residuals (conservative
estimate; LLM-dialogue non-cacheable across runs; one-time migration miss;
keyed-temp accumulation — a reaper is a reasonable future ticket if temp dirs grow).

*Verified + written 2026-06-08. main=`c28f9e6` GREEN; 0 unread; nothing owed.*
*Race-ack (Rule #5/#7): operator shipped `0daf787` (their handoff + tickets-CLOSED)*
*during my verification sweep — this handoff stacks on it; tickets-flip reflected as DONE.*
