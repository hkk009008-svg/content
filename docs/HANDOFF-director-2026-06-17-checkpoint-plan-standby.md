# Handoff - director - 2026-06-17 checkpoint plan standby

READ FIRST AS `director`. Trust current git, mailbox bodies, and live gate
evidence over this prose if they diverge.

## State At Wrap

Generated: `2026-06-16T16:10:12Z` (`2026-06-17T01:10:12+0900 KST`).
Seat: `director`.
Repo: `/Users/hyungkoookkim/Content`.

Latest live status before this handoff:

```text
HEAD: 5ca9e824 coord(cursor): operator consume checkpoint route
Branch: main, 4 ahead / 0 behind origin/main
director cursor: 2026-06-16T16:03:34Z
director unread: 0
Wave 2 gate: MET counts={'verified': 30}
selector tail: 71 passed
```

Recent commits at orientation:

```text
5ca9e824 coord(cursor): operator consume checkpoint route
d89c5fe9 operator2(handoff): stand by for checkpoint plan
a524c7ba coord(cursor): director consume checkpoint planning route
80f6a8a2 coord(route): open checkpoint planning pass
7dde8947 docs(handoff): capture coordinator push boundary
```

Smoke before this handoff:

```text
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
RESULT: no ceremony detected - every relied-on green is backed by execution.
OK
```

Known smoke advisories only:

- `verify-addendum` mailbox kind is not in `KNOWN_KINDS`.
- `tests/unit/test_discovery_identity_xfail.py:193` has a `skip()` in a pin
  file.
- `tests/unit/test_lane_silent_gate_siblings_xfail.py:64` uses
  `importorskip('cv2')`, and the dependency is present.

## Mail Read

The current binding event is:

- `coordination/mailbox/sent/2026-06-16T16-03-34Z-coordinator-to-all-coordination.md`

It was already consumed for this concrete `director` seat in:

```text
a524c7ba coord(cursor): director consume checkpoint planning route
```

Current `director` unread after refresh is `0`.

The route explicitly opens no immediate Pair-A production, pod, spend,
inventory, lock, push, or verification task for `director`.

## Director Routing Decision

No director-owned implementation or verification work is active from this
checkpoint route.

Binding route interpretation:

- `director2` owns the next no-spend planning artifact for the three deferred
  Pair-B checkpoint rows:
  `ckpt-nan-json-token`, `ckpt-sceneclips-dead`, and
  `ckpt-stage-notrestored`.
- `operator2` stands by to cold-review that future checkpoint mini-batch plan.
- `director` remains standby for a concrete Pair-A artifact, identity/ArcFace
  design review, Tier-A co-sign request, or later coordinator route.
- Pair-A Wave-3 realism / dual-character work remains pod/spend-gated and is
  not opened by the checkpoint route.

If a later route asks `director` to judge the Wave-3 realism or dual-character
track, start from:

- `docs/superpowers/plans/2026-06-15-dual-char-attn-mask-binding.md`
- the matching ComfyUI/video-generation project skills before graph or
  pipeline judgment.

## Workspace Caveat

Before writing this handoff, the shared worktree showed an unrelated dirty
path:

```text
M coordination/mailbox/seen/director2.txt
```

That is not director-owned for this turn. Preserve it unless ownership is
explicitly transferred. This handoff should be committed as the only
director-owned path for this wrap.

## Exact Next Trigger

For `director`, wait for one of:

- a concrete Pair-A artifact or verification route,
- a Tier-A co-sign request,
- an identity/ArcFace/product-oracle design-review request,
- a coordinator route that explicitly opens Pair-A Wave-3 realism or
  dual-character work.

Do not claim locks, edit production code, change inventory, push, spend on pods
or paid APIs, or verify director-owned work from this handoff alone.
