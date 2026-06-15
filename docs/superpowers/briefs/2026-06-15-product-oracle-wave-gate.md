# R-BRIEF: ADR-027 FIX-5 - product-oracle wave-close gate

PRIORITY: MAJOR        LANE: B (video/assembly/audio)
CROSS-CUTTING: no (does not touch auto_approve.py, cinema/context.py, core.py, or web_server.py)

## The defect

ADR-027 and the roadmap require Wave 2+ to have at least one committed product-oracle
artifact in `logs/` before a wave can close. The current executable gate enforces
row pins and no-oracle blockers, but it does not enforce the product-oracle close
condition, so a future Wave 2 could turn green on structural pins alone.

## Rule #12 - grep-the-writes

TARGET SYMBOL: committed `logs/` product-oracle artifact.

Verified existing tracking surface:

```bash
$ rg -n "^logs/\*|^!logs/|prod_pulid_acceptance|json.dump\(result|out = f\"logs/" .gitignore scripts/_prod_pulid_acceptance.py docs/superpowers -g '*.py' -g '*.md' -g '.gitignore'
.gitignore:64:logs/*
.gitignore:67:!logs/discovery-*.json
scripts/_prod_pulid_acceptance.py:18:land in logs/prod_pulid_acceptance_<date>.json (R-MEASURE).
scripts/_prod_pulid_acceptance.py:145:    out = f"logs/prod_pulid_acceptance_{date}.json"
scripts/_prod_pulid_acceptance.py:147:        json.dump(result, f, indent=2)
```

Runtime writer evidence exists for an ArcFace R-MEASURE artifact, but the output
is currently gitignored. FIX-5 therefore needs both a gate check and a tracked
artifact naming contract (`logs/product-oracle-*.json`).

## Rule #13 - symmetric / sibling audit

Shared enforcement surface:

```bash
$ sed -n '120,150p' .github/workflows/ci.yml
Run executable Wave 1 pin gate -> python scripts/wave_gate_check.py 1
Run no-ceremony detector -> python scripts/check_no_ceremony.py

$ sed -n '1163,1235p' DECISIONS.md
ADR-027 says FIX-1/2/4 are implemented and FIX-5 remains pending.

$ sed -n '130,145p' docs/superpowers/specs/2026-06-14-program-hardening-roadmap-design.md
Wave 2 onward requires one committed product-oracle artifact in logs/.
```

Fold now:

- `scripts/wave_gate_check.py`: Wave 2+ verdict includes product-oracle blockers.
- `.gitignore`: allow `logs/product-oracle-*.json` so the required artifact can be committed.
- `tests/unit/test_wave_gate_check.py`: cover Wave 1 unaffected, Wave 2 blocked without artifact, valid artifact accepted, invalid artifact rejected.
- ADR/inventory wording: mark FIX-5 as gate-enforced by this brief's implementation.

Defer:

- Authoring `scripts/measure_lipsync_offset.py` and the real baseline burn artifact remains the product-execution task. This gate only prevents closure until that committed artifact exists.
- Operator-GO impl!=verifier remains a known ADR-027 gap; this brief does not claim to enforce it.

## Full-shape pattern reference

Mirror `scripts/wave_gate_check.py`:

- read-only gate;
- deterministic report object plus CLI diagnostics;
- non-zero exit on hard blockers;
- no inventory mutation;
- `GIT_INDEX_FILE` removed from subprocess git/pytest checks where the result must reflect repository HEAD, not a seat-local index.

## The fix

Add a Wave 2+ product-oracle check to `gate_report()`:

- find committed `logs/product-oracle-*.json` files from `HEAD`;
- accept at least one JSON artifact whose `artifact_kind` is `product-oracle`, whose `wave` matches the requested wave, and whose metrics include finite `arcface.arc_score` plus finite `lipsync.offset_frames`;
- fail closed with a named product-oracle blocker when no valid artifact exists;
- leave Wave 1 unchanged.

Expected scope: about 80 LoC in `scripts/wave_gate_check.py`, focused unit tests, one `.gitignore` exception, and small ADR/inventory wording updates.

## Verification the operator/CI will run

```bash
env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_wave_gate_check.py -q
env -u GIT_INDEX_FILE .venv/bin/python scripts/wave_gate_check.py 2
env -u GIT_INDEX_FILE .venv/bin/python scripts/ci_smoke.py
```

Expected:

- unit tests pass;
- Wave 2 remains UNMET and prints a product-oracle blocker in addition to existing open-pin blockers;
- smoke remains OK.
