---
name: "create-regression-pin"
description: "Author a strict-xfail regression pin for a confirmed-but-deferred defect (R-VERIFY-TIER B), with the three recurring traps \u2014 assertion-shape, lock-column, non-vacuous flip \u2014 as built-in checks. Use when an agent-confirmed code defect is being left unfixed this session."
---

# Create a Regression Pin (strict-xfail)

## When
R-VERIFY-TIER(B): an agent-confirmed defect you are NOT fixing this session
must ship a `pytest.mark.xfail(strict=True, reason=...)` pin in the same
session — so CI, not the next session's agents, re-verifies it. (Or label it
`test-infeasible` with a one-line reason in the handoff.)

Codex has no skill-level equivalent of Claude's `disable-model-invocation`;
use this as procedural guidance in the active session, not as a delegation
trigger for a separate model run.

## The pin (shape)
```python
@pytest.mark.xfail(strict=True, reason="<defect-id>: <one line>; see docs/REMEDIATION-INVENTORY.md")
def test_<defect_id>_regression():
    # Assert the CORRECT (post-fix) behavior. strict=True means:
    #   defect present -> test fails  -> xfail  (expected)   -> suite stays green
    #   defect fixed   -> test passes -> XPASS  (unexpected) -> suite goes RED -> remove the pin
    ...
```

## Trap 1 — assertion shape must match how the fix will land
The pin's assertion dictates what "fixed" looks like. If the real fix will make
a **direct call return safely** (not raise), a pin written with
`pytest.raises(...)` will never flip to XPASS even after the fix — it keeps
passing as xfail forever. Match the assertion to the fix's contract:
- fix = "stop raising / return safe value" -> assert the safe return (no `pytest.raises`)
- fix = "start raising / start blocking"   -> `pytest.raises` / assert the block
- fix = "coerce non-finite -> 0.0 + WARN, keep gate alive" -> assert the coerced
  value AND that the gate still runs (not that it blocks)

## Trap 2 — the lock column is the MODULE, not the wave number
The cross-cutting lock for a shared file is one per **module across all waves**
(e.g. `W2-web_server.py.lock` — the `W2` is just the column name; it does NOT
mean "wave 2 only"). Claim / release by module, not by wave. See
`coordination/bin/claim-lock` and `coordination/bin/release-lock`. For a
same-commit-as-GO release, `git rm` the lock manually in the GO commit
(`release-lock` makes a SEPARATE unlock commit).

## Trap 3 — prove the pin is non-vacuous
A pin that never actually exercises the defect is invisible-green theater.
Before you trust it:
- Run `env -u GIT_INDEX_FILE .venv/bin/python -m pytest <file> --runxfail -q`
  and confirm it goes **RED** against the current (unfixed) code — that proves
  the assertion really catches the defect.
- Confirm the failure reason is the defect, not a setup error / import skip /
  `importorskip` swallow.
- Confirm it would flip to XPASS once the fix lands (the assertion is the
  post-fix contract from Trap 1).

## Steps
1. Locate the defect row in `docs/REMEDIATION-INVENTORY.md`; get its id + severity.
2. Write the test asserting post-fix behavior (Trap 1).
3. Add the `xfail(strict=True, reason=…)` decorator citing the defect id.
4. Run `--runxfail` and confirm RED + correct reason (Trap 3).
5. Run the normal suite slice and confirm it reports `xfailed` (not `xpassed`,
   not `error`).
6. Update the inventory row to note the pin (`file::test_name`).
7. Commit with explicit pathspec (`-m` before `--`) and the git-hygiene prefix
   on the shared tree. This pins a DEFERRED defect — it does NOT substitute for
   per-commit production verification of a fix you DID land.

## When a pin is infeasible
If the defect cannot be expressed as a runtime test (needs a live pod / paid
API / non-deterministic render), label it `test-infeasible` with a one-line
reason in the handoff instead of forcing a vacuous pin.
