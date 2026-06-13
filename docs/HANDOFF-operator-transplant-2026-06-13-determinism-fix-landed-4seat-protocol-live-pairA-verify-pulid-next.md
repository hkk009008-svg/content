# Operator transplant handoff — 2026-06-13 (PM2): identity-embedding determinism FIXED (OpenCV align thread-race, not phantom selection) + hardened after self-review caught a GCD no-op → **4-SEAT PROTOCOL drafted, cut over, and ACCEPTED; you are now Pair-A operator (image/identity-realism lane)**

**Seat:** operator (= **Pair A operator**, 4-seat protocol now LIVE) · **Session:** 2026-06-13 ~07:20Z → ~08:54Z
**HEAD at wrap:** `6433d92`. **64 ahead of origin, push USER-gated.**
**Gates:** `ci_smoke` **OK** (firsthand at wrap). Suite **2255 passed / 2 skipped** (full run post-cutover). Coordination linter **clean (4 INFO)**.
**Cursor: 2026-06-13T08:50:44Z, 0 unread.**
**Pod 07ed667: DOWN** (director's /system_stats 200→502; user-confirmed not running). **NO BURN this session** — ⭐#1 burn-scoring stays blocked until pod-up + user spend-go.

## THE TEAM IS NOW FOUR SEATS (you are Pair A operator)
Per user directive ("scale 2→4 for speed"), principal-confirmed. Two director↔operator **pairs**, lanes **FINAL**:
- **Pair A = `director` + `operator` (you) = IMAGE-GEN + IDENTITY/REALISM.** Owns `pulid*.json`, `quality_max.py`, `workflow_selector` image params, `identity/validator.py` + the arc scorer, and the data-integrity lane (production PuLID SDXL→FLUX fix + the 2 unrouted determinism siblings).
- **Pair B = `director2` + `operator2` = VIDEO + ASSEMBLY + DELIVERY.** `phase_c_*` video paths, video-API selection, lip-sync, dialogue/TTS, `cinema/shots` continuity, orchestration.
- **Shared seams** (`phase_c_assembly`, `workflow_selector`) → owner = whoever's change-lane the edit is in + a `-to-all-` heads-up (Rule #23).
Full protocol: `docs/protocol/claude/four-seat-extension.md` (ACCEPTED). director2/operator2 verified healthy at wrap (heartbeating, indexes seeded).

## ⭐ #1 PICKUP — verify the Pair-A director's PuLID SDXL→FLUX Chunk-1 commits as they land (OUR lane)
The Pair-A director is EXECUTING the production PuLID fix (heads-up `6321cea`, Rule #23): editing `pulid.json` nodes 99/100/101 (SDXL→FLUX: PulidFluxModelLoader/ApplyPulidFlux/PulidFluxEvaClipLoader), `workflow_selector.py` `pulid_start_at`→0.0 (IMAGE params only) + the stale line-512 docstring, and a new `tests/unit/test_pulid_production_flux.py`. ~3 explicit-pathspec commits, behind the pod acceptance gate.
**You (operator):** independently verify each commit post-land — node-class correctness (ApplyPulid → ApplyPulidFlux is the documented prod no-op fix, ADR-024 + my determinism report), that `pulid_start_at` change is image-only (NOT video — Pair B's lane), tests green, ci_smoke OK. **NO collision** — director owns the code edit, you verify. Use `comfyui-mastery` skill BEFORE judging the graph JSON (R-SKILL). Spec+plan: `4c018ff` + `f7eb9f6` + `874138f`.

## ⭐ #2 — the identity-embedding determinism fix LANDED; one pod-gate remains before N=4 GO
`identity/validator.py` now routes ALL embedding reads through `_represent_deterministic` / `_cv2_single_thread` (commits **d48b58b** + **68e9722**). Root cause (independently reproduced, OVERTURNING the prior handoff's "phantom selection / confidence floor" diagnosis — that was WRONG; phantoms are 0.95–0.99 conf, `classify_detection` was already correct and is UNTOUCHED):
- The man-ref **cold-draw** is an **OpenCV multithreading race in DeepFace's `align=True` crop**: same image, same bbox, but the aligned crop intermittently diverges → an embedding 0.456 cos-dist from the byte-stable majority → man 0.870→0.762. Not seedable. `align=False` is deterministic but COLLAPSES the binding (0.870→0.522) — alignment is load-bearing, not optional.
- **Fix = serialize OpenCV** (`cv2.setNumThreads(1)`, with a `setNumThreads(0)` fallback because **on macOS/GCD `setNumThreads(1)` is a NO-OP** — getNumThreads stays at default; only 0 serializes there; on the Linux/TBB pod 1 works) + a deterministic area-tie-break. **Load-verified** (`scripts/_probe_embedding_determinism.py --load`): unguarded **8/30 diverge**, guarded **30/30 byte-identical**.
- **⚠ POD-PORTABILITY GATE (review robustness lens, UNVERIFIED — pod down):** the deterministic single-threaded VALUE is OpenCV-build-specific. The pinned man-0.870 was measured on **macOS**; the **Linux/TBB pod may pin a different value**. **Re-run `scripts/_probe_figure_read_determinism.py` (fixed code) on the pod against `logs/passb_d_n1.jpg` and re-confirm the man baseline BEFORE any N=4 GO threshold.** If it differs, re-baseline the ~0.75 acceptance floor.
- Net: the binding instrument is now trustworthy (deterministic) — N=4 GO can rely on it once the pod re-confirm above is done. Detail in `ARCHITECTURE.md §11.1`.

## ⭐ #3 — 2 unrouted determinism siblings in OUR Pair-A lane
The SAME align thread-race affects `domain/continuity_engine.py:164,181` (extract_faces + represent) and `domain/character_manager.py:369,385,396` (the last PERSISTS the canonical `embedding.npy` — highest severity: a race baked into that file permanently corrupts a character's scores). NOT routed through the chokepoint (different files). The Pair-A **director** owns routing them (their stated plan: after the PuLID fix). You verify when they land, OR offer to route them (cross-file import of `_cv2_single_thread` from `identity.validator`) if asked — flag first, it's the director's call within our pair.

## Established facts (operator-verified this session)
- **4-seat tooling is correct + backward-compatible.** Cutover `813d0d4`: widened the 4 synced vocab spots (`send-event`, `consume-events`, `check_coordination.py` ROLES+regex+orphan-`all`, `status.py` count_unread) + 2 cursors + an `all` broadcast target. **Hook UNTOUCHED** — `_stamp_presence`/`_sync_seat_index`/`_clear_skip_worktree` are already `$CLAUDE_SEAT`/`$GIT_INDEX_FILE`-generic, so the new seats' presence/heartbeat/index "just worked" (verified live). Regression test `tests/unit/test_four_seat_coordination.py` (6 cases). Safe-ordered (cursors before ROLES-widen) so ci_smoke never FATAL'd the live director.
- **Adversarial review on your own work pays.** A 3-lens workflow over `d48b58b` caught BOTH a BLOCKER (the "30/30" claim was an uncommitted ad-hoc run violating R-MEASURE) AND the GCD no-op — before they reached the pod. Lesson: when you commit a determinism/perf claim, the committed instrument must EXERCISE the fix path, and platform-specific primitives (cv2 thread backend) must be verified on-platform.

## Sharp edges (this session)
1. **`cv2.setNumThreads(1)` is a no-op on macOS/GCD** (`getNumThreads()` stays at default; `setNumThreads(0)` serializes). The guard handles both, but any future cv2-determinism work must check `getNumThreads()==1`, not assume.
2. **The align race is LOAD-DEPENDENT** — it rarely fires on a quiet machine (60/60 clean unguarded once), so a few clean runs prove NOTHING. Use `--load` (hammer threads) to force it.
3. **zsh ate an unquoted `(role,'all')` in a `git commit -m` body** (813d0d4's message lost one clause — substance is in the code comment + doc). Quote parens/globs in `-m` bodies, or use `-F`.
4. **4-seat coordination is live** — `git log -3` before shared work (now 3 peers can commit), pathspec commits load-bearing, `-to-all-` for cross-lane heads-ups (Rule #23). `consume-events <seat>` now accepts director2/operator2 + counts `-to-all-`.
5. **`send-event`/`consume-events` operate on the REAL repo** (shared tree → edits are live for peers instantly); that's why the cutover was safe-ordered + backward-compatible.

## What this session did (chronological)
R-START (smoke OK, both seats had wrapped; director came back online mid-session) → reproduced + root-caused the binding non-determinism = OpenCV align race (corrected the handoff) → fix `d48b58b` + report `df8bcae` → **adversarial self-review (3 lenses)** caught GCD no-op + R-MEASURE gap → hardened `68e9722` (GCD fallback + load instrument + ARCHITECTURE §11.1) → user directive "scale 2→4" → drafted `four-seat-extension.md` (`aa0dc35`), dispatch-claim/proposal (`bae7a3e`/`df219d7`), user "proceed now" → backward-compatible cutover `813d0d4` + inaugural `all` broadcast `caae981` → principal-confirmed lanes (director relay `32b63b1`) → doc ACCEPTED with lanes `85f8bde` → user launched director2/operator2 → verified them healthy + confirmation broadcast `6433d92`.

## Cross-seat state at wrap
- **Pair-A director:** ONLINE, executing PuLID SDXL→FLUX Chunk 1 in our lane (`6321cea`). Spec+plan landed (`4c018ff`/`f7eb9f6`/`874138f`). ACK'd your determinism land + the 4-seat extension. Owns routing the 2 determinism siblings after PuLID.
- **Pair B (director2 + operator2):** LIVE, lane = video/assembly-delivery. Cursors at seed — they'll consume the `-to-all-` history (incl. the cutover + lanes) on session-start.
- **Statusline** was configured this session (minimal: dir·model·ctx%); an unauthorized `useAutoModeDuringPlan` the setup agent added was removed.

*Last verified: 2026-06-13T08:54Z (ci_smoke OK firsthand; suite 2255/2 firsthand; coordination linter clean (4 INFO); commit SHAs from git log; 4-seat seats verified live via heartbeats/indexes. Pod DOWN — N=4 + the pod-portability re-baseline both wait on pod-up.)*
