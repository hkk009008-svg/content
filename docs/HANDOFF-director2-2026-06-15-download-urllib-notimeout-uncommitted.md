# Handoff - director2 Pair-B - 2026-06-15 download urllib timeout WIP

Seat: director2, Pair-B director. User requested `handoff` while the
`download-urllib-notimeout` row was implemented locally but not committed. No
push was performed.

## Current Durable HEAD

```text
$ env -u GIT_INDEX_FILE git log --oneline -8
a4179748 coord(verify): add operator2 lipsync evidence addendum
c021490d coord(cursor): operator consume operator2 GO
742ddf8d coord(verify): operator2 GO lipsync costkey
dbe371df coord(cursor): operator consume coordinator final handoff
2e7d9776 docs(handoff): director product-oracle guidance wrap
a2e39ac7 docs(handoff): coordinator subagent adoption wrap
e593a705 docs(handoff): operator product-oracle guidance idle
2b5fdf0d coord(cursor): director2 consume final wrap addenda
```

Seat status after cursor consume:

```text
HEAD a4179748 coord(verify): add operator2 lipsync evidence addendum
vs origin/main: 94 ahead, 0 behind
cursor: 2026-06-15T11:55:07Z
UNREAD: 0
Wave 2 gate: UNMET counts={'verified': 17, 'open': 13}
```

## Mailbox Processed

Processed and consumed:

- `2026-06-15T11-48-10Z-operator2-to-all-verification-report.md` - operator2
  GO for `aeb1a2b7` lipsync cost key.
- `2026-06-15T11-53-43Z-operator2-to-all-verification-report.md` - GO evidence
  addendum with exact mutation/non-vacuity probe.
- `2026-06-15T11-55-07Z-coordinator-to-all-coordination.md` - coordinator
  reconciliation: `lipsync-postproc-costkey` open -> verified.

Final consume output:

```text
cursor director2: 2026-06-15T11:48:10Z -> 2026-06-15T11:55:07Z; unread now: 0 (staged; fold into your next substantive commit)
```

## Uncommitted WIP

Current scoped status:

```text
$ env -u GIT_INDEX_FILE git status --short -- ARCHITECTURE.md phase_c_ffmpeg.py tests/unit/test_discovery_io_xfail.py docs/REMEDIATION-INVENTORY.md docs/superpowers/briefs/2026-06-15-download-urllib-timeout.md coordination/mailbox/seen/director2.txt
 M ARCHITECTURE.md
M  coordination/mailbox/seen/director2.txt
 M docs/REMEDIATION-INVENTORY.md
 M phase_c_ffmpeg.py
 M tests/unit/test_discovery_io_xfail.py
?? docs/superpowers/briefs/2026-06-15-download-urllib-timeout.md
```

Intended row: `download-urllib-notimeout` (`phase_c_ffmpeg.py`, Pair-B, MAJOR,
no cross-cutting lock).

Implemented local changes:

- `docs/superpowers/briefs/2026-06-15-download-urllib-timeout.md` - new R-BRIEF
  with Rule #12 write-site grep and Rule #13 sibling audit.
- `phase_c_ffmpeg.py` - imports `performance._net.safe_download`, adds local
  `_download_video_or_cascade(video_url, engine)` inside `generate_ai_video`,
  and routes all seven provider video downloads through it:
  `RUNWAY_GEN4`, `SORA_2`, `VEO`, `KLING_3_0`, `FAL_SVD`, `RUNWAY`,
  `SEEDANCE`.
- `tests/unit/test_discovery_io_xfail.py` - promoted from strict xfail pin to a
  live AST regression. It now proves zero raw `urlretrieve` calls in
  `phase_c_ffmpeg.py`, one centralized `safe_download` call in the helper, and
  seven `if not _download_video_or_cascade(...): return try_next_api()` branch
  guards.
- `docs/REMEDIATION-INVENTORY.md` - updates the `download-urllib-notimeout`
  selector to the live regression and notes implementation pending operator2
  Lane V.
- `ARCHITECTURE.md` - line-anchor sync for the `_VEO_QUOTA_*` definitions after
  the new import shifted lines.
- `coordination/mailbox/seen/director2.txt` - cursor advanced to
  `2026-06-15T11:55:07Z`.

Important same-file caveat:

- `docs/REMEDIATION-INVENTORY.md` also contains the official coordinator
  reconciliation for `lipsync-postproc-costkey` (open -> verified), per
  `2026-06-15T11-55-07Z-coordinator-to-all-coordination.md`.
- Do not blindly revert that coordinator state. If the next seat wants a
  single-purpose download commit, stage only the `download-urllib-notimeout`
  hunk or use an explicit commit strategy that preserves the coordinator change
  in the working tree.

## Subagent Tooling Used

The user explicitly requested multi-subagent workflow adoption. Two read-only
explorer sidecars ran in parallel:

- `Lovelace` (`019ecb1d-ccfc-7250-a88c-15cf990836a4`) - Rule #13 sibling-scope
  audit. Result: fix only `phase_c_ffmpeg.py` for this row; cite
  `performance._net.safe_download`; keep `allow_http=False` for external
  providers; explicitly defer `ltx_native.py` FAL fallback `urlretrieve` sites.
- `Helmholtz` (`019ecb1d-cd7f-7df1-90be-4bc5800118e7`) - regression-shape
  review. Result: tighten the live test against alias `urlretrieve` calls, dummy
  helper calls, and missing `try_next_api()` guards. Those recommendations were
  folded into `tests/unit/test_discovery_io_xfail.py`.

No subagent consumed mailbox or wrote files.

## Verification Already Run

```text
$ env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_discovery_io_xfail.py -q
1 passed in 0.04s

$ env -u GIT_INDEX_FILE .venv/bin/python -m py_compile phase_c_ffmpeg.py tests/unit/test_discovery_io_xfail.py
# no output

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/check_doc_claims.py ARCHITECTURE.md
All anchors checked - no drift.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
OK; existing advisories only: 177 PROGRAM-MANUAL doc-anchor drifts, two historical unknown-kind mailbox filenames, and R2 invisible-green warnings.

$ env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
Wave 2 gate: UNMET counts={'verified': 17, 'open': 13}
15 failed, 46 passed
```

Wave gate still blocks on:

- `spent-usd-reset-on-resume` no executable selector.
- `perf-phase-no-gate` no executable selector.
- Missing committed `logs/product-oracle-*.json`.
- Remaining open pins: lipsync veto, web-server HTTP cluster, checkpoint cluster.

The IO selector is now included and passes:

```text
tests/unit/test_discovery_io_xfail.py::test_urlretrieve_download_sites_have_timeout_protection
```

## Dirty Tree / Commit Warning

The default index has broad pre-existing staged state from other seats
(mailbox staged-delete/untracked twins, cost/character-manager work, docs, and
tests). This pass did not normalize it. Do not run a broad `git commit`,
`git add .`, or cleanup.

Use explicit pathspecs and inspect both staged and unstaged scope before
committing. The safest next step is either:

1. create a focused commit for the download row with only:
   `ARCHITECTURE.md`, `phase_c_ffmpeg.py`,
   `tests/unit/test_discovery_io_xfail.py`,
   `docs/superpowers/briefs/2026-06-15-download-urllib-timeout.md`,
   the `download-urllib-notimeout` hunk of `docs/REMEDIATION-INVENTORY.md`,
   and `coordination/mailbox/seen/director2.txt`; or
2. if coordinator ownership wants the lipsync inventory reconciliation committed
   together, state that deliberately in the commit body and cite the coordinator
   event above.

## Next Action

Commit the scoped WIP, then send a verify-request to `operator2` for
`download-urllib-notimeout`. Suggested operator2 checks:

- actual diff only;
- focused IO regression passes;
- mutation/non-vacuity: reintroducing any `urlretrieve` call or removing a
  branch `return try_next_api()` guard makes the test fail;
- `safe_download(..., allow_http=False)` is acceptable for external provider
  URLs; `ltx_native.py` raw fallback downloads are a deferred sibling, not part
  of this row.
