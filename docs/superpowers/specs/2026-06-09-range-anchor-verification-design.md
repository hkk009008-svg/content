# Design — range-anchor verification in `check_doc_claims.py` (Finding-1 Slice 3)

- **Status:** Proposed (brainstorming complete; pending spec review + user approval)
- **Date:** 2026-06-09
- **Author:** operator-seat
- **Builds on:** Slice 1 (inline-backtick anchor def-checking, `docs/superpowers/specs/2026-06-08-inline-backtick-anchor-verification-design.md`; shipped `26c318b`/`94c00fc`/`5b1a643`/`13d550b`) and Slice 2 (manual + digests anchor sweep, `32f6e52`/`78bdd83`/`202b8ed`/`05c22d8`).
- **Agreed operator-owned, non-urgent, zero Phase-3 entanglement** per director disposition `2026-06-08T17:13:00Z` ("Real blind spot — range anchors def-rot silently … yours to spec next session").

## 1. Problem

`scripts/check_doc_claims.py` verifies that doc anchors of the form `` `file.py:NNN` `` (and `` `file.py:N-M` `` ranges, and markdown-link `](file.py:NNN)`) still point at the symbol the prose names. Slice 1 made single-line inline anchors **def-checked** (resolve the bound symbol → flag if its def moved). Slice 2 swept the manual + digests to "no drift."

**The handoff diagnosed Slice 3 as:** range anchors are bounds-checked only; the fix is "resolve the prose-named symbol within a cited range + flag if it moved out."

**The actual root cause is different and worse — a regex separator mismatch.** `_INLINE_ANCHOR_RE`'s range group is ASCII-hyphen-only:

```python
# scripts/check_doc_claims.py:69
r'`(?P<file>[A-Za-z0-9_./-]+\.[A-Za-z]+):(?P<line>\d+)(?:-(?P<end>\d+))?`'
#                                                      ^^^ ASCII '-' only
```

But the docs use **en-dashes** (`–`, U+2013) for ranges throughout. An en-dash range anchor does not match the regex *at all* (the optional end-group fails AND the required closing backtick fails) — so it is **completely invisible**: not def-checked, not bounds-checked, not even seen.

**Verified populations** (`grep -oE '\`…:\d+[sep]\d+\`'`, 2026-06-09):

| Doc | ASCII hyphen ranges | en-dash ranges | em-dash ranges |
|---|---|---|---|
| `docs/PROGRAM-MANUAL-digests.md` | 302 | **256** | 0 |
| `docs/PROGRAM-MANUAL.md` | 31 | **2** | 0 |

**Verified hidden rot** — simulating the fix (regex range-sep `-` → `[-–—]`) and running the real `check_line_anchors` on both docs surfaces **43 drifts that are invisible today**:

```
TOTAL drifts under patched regex: 43
by kind: {'def_drift': 38, 'ambiguous_path': 5}
# e.g. try_next_api cited phase_c_ffmpeg.py:765, def at :138
#      split_video_into_segments cited :858, def at :872
```

**Consequence (Rule #18 Guard-1 "verifier-clean ≠ true"):** Slice 2's *"manual + digests fully anchor-clean / no drift"* (commit bodies + operator handoff §0) was a **false-clean** — 43 stale anchors were never in the verifier's view. This slice corrects that claim.

## 2. Goal / non-goals

**Goal.** Make en/em-dash range anchors visible to the verifier (closing the 258-anchor blind spot), sweep the now-surfaced drift, and correct the false-clean.

**Non-goals.**
- **Symbol-in-range binding enhancement (the handoff's original framing) — OUT.** Post-fix classification (2026-06-09) shows of all visible range anchors: **94 def-check cleanly**, but **490 fall to bounds-only** — and that residual is *legitimate*: dominated by **region anchors** (`cinema_pipeline.py:855-893` describing a code *block*, no single symbol) and **false-binds** (prose words in backticks — `llm`, `audio`, `ok`, `exports` — that have no Python def). Chasing a "missed symbol" in those would be high-false-positive, low-signal. The def-check already fires for the 94 real-symbol cases; that is sufficient.
- **Markdown-link range def-checking — OUT (none exist).** 0 markdown-link ranges in either doc (verified). The latent asymmetry (link ranges carry `:A-B` in the URL, not `display_text`, so `check_anchor`'s `range_match` can't see the span) is documented as a known limitation, not fixed.
- **Doc-wide en-dash → hyphen normalization — OUT.** Per the brainstorming decision (tolerant-accept + canonicalize-on-`--fix`-touch only), untouched passing anchors keep their en-dash. No 258-line normalization diff.

## 3. Approved decisions (from brainstorming)

1. **Dash policy (Q1):** *tolerant accept + canonicalize on `--fix`.* The regex accepts `-`, `–`, `—`; `--fix` emits ASCII hyphen, so an anchor it rewrites is canonicalized as a side effect, but untouched anchors keep their separator (contained diff, gradual canonicalization).
2. **Multi-range anchors (Q2):** `` `file:A-B, C-D` `` (~7; still unparseable after the en-dash fix because the comma precedes the closing backtick) → *warn, do not verify.* Emit a loud stderr count ("N multi-range anchor(s) NOT verified — split to verify"), mirroring the existing ADV-2 unclosed-fence and bare-unresolved warnings. Never silently skipped.
3. **Symbol-in-range residual:** excluded (see §2 non-goals).
4. **Sweep in-slice:** Part 2 (doc sweep + false-clean correction) ships in the same slice as Part 1 (verifier code), not deferred.

## 4. Design (Approach A — surgical regex tolerance)

Chosen over Approach B (a centralized `_canonicalize_dashes()` normalize-on-read pass) because A is a one-character-class change at each of the two sites that parse/rewrite ranges, matches the existing per-regex style, and adds no indirection layer / second "what is an anchor" decision point.

### 4.1 Detection — `_INLINE_ANCHOR_RE` (~L69)

```python
# range separator: accept hyphen, en-dash, em-dash
r'`(?P<file>[A-Za-z0-9_./-]+\.[A-Za-z]+):(?P<line>\d+)(?:[-–—](?P<end>\d+))?`'
```

Em-dash (`—`) is included defensively though 0 exist today — it prevents the same invisible-anchor class from recurring under a different dash. No other regex changes: `_ANCHOR_RE` (markdown-link) does not capture ranges, and 0 markdown-link ranges exist.

Once matched, en/em-dash ranges flow **unchanged** through the existing pipeline: `_bind_inline_symbol` → `_resolve_inline_target` → `check_anchor`. `check_anchor`'s range def-check (L268, `re.search(r':(\d+)-(\d+)$', display_text)`) reads `display_text`, which `check_line_anchors` builds at L393 as `f"{token_file}:{target_line}" + (f"-{end}" if end else "")` — i.e. **already ASCII hyphen** regardless of the source dash. So no change is needed at the def-check or display-build sites.

### 4.2 `--fix` canonicalization — `_shift_display` (~L432)

`_shift_display` currently matches ranges with ASCII hyphen only:

```python
for rm in re.finditer(r':(\d+)-(\d+)', display):   # accept en/em-dash on read:
for rm in re.finditer(r':(\d+)[-–—](\d+)', display):
```

It already **emits** ASCII hyphen (`f":{new}-{end}"`), so widening the read pattern is the whole change: a `--fix` on an en-dash anchor shifts the line *and* canonicalizes the separator. `_rewrite_anchor_occurrence` (~L457) reconstructs the inline body as `f"{drift.target_file}:{old}" + (f"-{end}" if end else "")` — already ASCII hyphen once `end` captures from the widened `_INLINE_ANCHOR_RE.fullmatch`; verify, no logic change.

### 4.3 Multi-range warning (NEW)

After the per-doc anchor loop in `check_line_anchors`, scan for the multi-range shape the anchor regex cannot fully parse — a backtick-delimited `file:N[sep]M` followed by `, K…` before the closing backtick:

```python
_MULTIRANGE_RE = re.compile(r'`[A-Za-z0-9_./-]+\.[A-Za-z]+:\d+[-–—]\d+\s*,\s*\d+[-–—]?\d*[^`]*`')
```

Count matches per run; emit one aggregate stderr warning (mirroring L408-410 / L412-415):

```
WARNING: N multi-range anchor(s) (e.g. `ltx_native.py:157-195, 273-305`) were NOT
verified — the comma-list form is unparseable. Split into single-range anchors to verify.
```

The warning is informational (stderr); it does **not** change the exit code by itself (consistent with the bare-unresolved warning). This preserves the verifier's core invariant — *never silently skip an anchor* (the ADV-2 principle).

### 4.4 Repo-wide sweep — Part 2 (after the tool ships green)

1. Run `check_doc_claims.py --fix docs/PROGRAM-MANUAL.md docs/PROGRAM-MANUAL-digests.md`. Expected: ~38 `def_drift`s corrected + canonicalized to hyphen.
2. Manually resolve the ~5 `ambiguous_path` (Slice-2b rules: bare filename matching ≥2 tracked paths → directory-qualify, e.g. `controller.py` >L700 → `cinema/shots/`).
3. Address the ~7 multi-range warnings: split into single-range anchors where the symbol is clear, else leave warned.
4. Re-run without `--fix`; **expected exit clean** (0 unwarned drift) on both docs.
5. **Correct the false-clean** in the slice commit body + spec note (the Slice-2 "no drift" claim covered only regex-visible anchors).

Counts above are *estimates from the 2026-06-09 simulation*; the implementer captures the actual `--fix` output and reconciles in the sweep commit body (Rule #1).

## 5. Testing (TDD — `tests/unit/test_check_doc_claims.py`)

Write tests first, watch them fail against current HEAD, then implement:

1. **en-dash range matches + def-checks.** `` `mod.py:10–20` `` with prose symbol whose def is at 15 → OK (in range); def at 25 → `def_drift`.
2. **em-dash range matches** likewise (`—`).
3. **ASCII-hyphen ranges unchanged** (regression) — existing range behavior preserved.
4. **`--fix` canonicalizes + shifts.** En-dash anchor whose symbol moved → after `--fix`, the anchor reads ASCII hyphen `:new-(end+delta)` with the span preserved.
5. **`--fix` idempotency** — running twice yields a stable file (existing convergence loop, exercised on an en-dash input).
6. **multi-range warning** — a `` `m.py:1-5, 9-12` `` line produces the stderr warning, the multi-range anchor is NOT counted as a silent pass, and a normal anchor on the same line is still verified.
7. **bounds-only legitimacy** — an en-dash region anchor with no bindable symbol still bounds-checks (in-bounds → OK; past EOF → `out_of_bounds`), confirming the residual is handled, not crashed.

## 6. Acceptance criteria

- New tests (1-7) green; full verifier suite still green (was `81 passed`, `tests/unit/test_check_doc_claims.py`).
- `check_doc_claims.py docs/PROGRAM-MANUAL.md docs/PROGRAM-MANUAL-digests.md` exits clean (0 unwarned drift), multi-range warning shows the expected count.
- §15 `ci_smoke.py` OK; full unit suite still green (baseline 1892/0).
- Slice commit body captures the real `--fix` output (Rule #1) and corrects the Slice-2 false-clean.

## 7. Risks / edge cases

- **Em-dash false-defense.** 0 em-dashes today; including `—` costs nothing and prevents recurrence. Low risk.
- **Canonicalization churn.** Bounded to anchors `--fix` touches (per Q1) — the ~43 drifted ones, not all 258. The remaining ~215 visible-but-passing en-dash anchors stay as-is (functionally fine, stylistically mixed). Accepted trade-off.
- **Multi-range under-coverage.** ~7 anchors remain unverified-by-design; the loud warning is the mitigation (no silent skip). A future slice may add full comma-list support if the count grows.
- **`--fix` span-guard interaction (ADV-1).** The widened regex changes match spans; `_rewrite_anchor_occurrence`'s fullmatch + (file,line) identity guard (L455/L464) already refuses to rewrite a non-matching span — so a widened match that no longer holds the expected anchor is left for a human, not corrupted. Covered by the existing guard; add a test asserting an en-dash span still round-trips.
- **Markdown-link range asymmetry.** Documented known-limitation (0 such anchors). If markdown-link ranges are introduced later, `check_anchor`'s `range_match` won't see the span (it scans `display_text`, not the URL) and would flag a false `def_drift` on a valid in-range link. Out of scope now; noted for the next author.

## 8. Composition with protocol

- **Rule #18 (doc-maintenance / verifier-buildout):** this slice extends the machine-verified claim coverage — exactly the verifier-buildout the doc-maintenance role's value declines against. It is the principled fix for a claim-type the verifier was blind to.
- **Rule #1 / ADR-013:** the sweep commit captures `--fix` output; this spec cites every count's command.
- **Operator-owned (Finding-1 lane):** the verifier is operator-owned (user-directed). Per-feat Lane V (Rule #9) is released to the director-seat as second opinion when the feat lands.
- **Zero Phase-3 entanglement:** touches only `scripts/check_doc_claims.py` + its tests + the two doc files. No `cinema/` / `domain/` / `web_server.py` / pipeline surface.
