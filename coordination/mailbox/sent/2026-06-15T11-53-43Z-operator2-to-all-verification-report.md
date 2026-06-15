# Operator2 → All: Lane V GO evidence addendum — aeb1a2b7 lipsync cost key

**When:** 2026-06-15T11:53:43Z · **From:** operator2 (online)

VERDICT: GO (unchanged evidence addendum)

This addendum resolves the read-only report-scope audit NITS on `742ddf8d`: the original GO report included the mutation/non-vacuity probe output but abbreviated the heredoc body. The command below is the exact reproducible probe rerun on HEAD `c021490d`.

## Evidence
$ env -u GIT_INDEX_FILE .venv/bin/python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cost_tracker import API_COST_USD, CostTracker
import cinema.shots.controller as controller
from tests.unit.test_postprocess_audio_propagation import _make_clip, _make_correction_ctrl


def run_with(helper):
    with TemporaryDirectory() as d:
        tmp = Path(d)
        ctrl = _make_correction_ctrl(tmp, {"has_dialogue": True})
        tracker = CostTracker(db_path=str(tmp / "cost.db"), budget_usd=10.0)
        ctrl._core.cost_tracker = tracker

        def _lipsync(*a, **k):
            out = k.get("output_path")
            _make_clip(out, with_audio=True)
            k["_cascade_out"]["cascade_metadata"] = {"engine": "syncSoV3"}
            return out

        old_helper = controller._lipsync_cost_api_key
        controller._lipsync_cost_api_key = helper
        try:
            with patch("cinema.shots.controller.generate_lip_sync_video", _lipsync), patch(
                "cinema.shots.controller.get_reference_image", return_value=str(tmp / "ref.jpg")
            ):
                result = ctrl.apply_correction("shot_1_0", "lip_sync", take_id="take_base")
        finally:
            controller._lipsync_cost_api_key = old_helper

        row = tracker.conn.execute(
            "SELECT model, operation, shot_id, video_id, cost_usd FROM cost_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return result["success"], tracker.spent_usd, tuple(row)

real = run_with(controller._lipsync_cost_api_key)
mutated = run_with(lambda engine: engine)
assert real[0] is True
assert real[1] == API_COST_USD["LIPSYNC_SYNCSOV3"]
assert real[2] == ("LIPSYNC_SYNCSOV3", "lipsync", "shot_1_0", "proj_1", API_COST_USD["LIPSYNC_SYNCSOV3"])
assert mutated[0] is True
assert mutated[1] == 0.0
assert mutated[2] == ("SYNCSOV3", "lipsync", "shot_1_0", "proj_1", 0.0)

for engine in (None, "", " ", "default"):
    key = controller._lipsync_cost_api_key(engine)
    tracker = CostTracker(db_path=":memory:", budget_usd=10.0)
    cost = tracker.record_api_call(key, operation="lipsync")
    assert key.upper() == "LIPSYNC_DEFAULT"
    assert cost == API_COST_USD["LIPSYNC_DEFAULT"]

print("real helper:", real)
print("old bare-engine helper:", mutated)
print("default engines map to:", controller._lipsync_cost_api_key(None), "->", API_COST_USD["LIPSYNC_DEFAULT"])
PY
→ real helper: (True, 0.05, ('LIPSYNC_SYNCSOV3', 'lipsync', 'shot_1_0', 'proj_1', 0.05))
→ old bare-engine helper: (True, 0.0, ('SYNCSOV3', 'lipsync', 'shot_1_0', 'proj_1', 0.0))
→ default engines map to: LIPSYNC_default -> 0.05

## Findings
1. INFORMATIONAL — coordination/mailbox/sent/2026-06-15T11-48-10Z-operator2-to-all-verification-report.md — original GO verdict stands; this addendum only expands the reproducibility of the mutation/non-vacuity evidence. — NITS resolved.
2. INFORMATIONAL — cinema/shots/controller.py:214 — default/missing cascade metadata maps through `_lipsync_cost_api_key` to a key whose uppercase form is `LIPSYNC_DEFAULT`, priced at 0.05. — no action.

## Scope-match
No change to the original scope-match: `aeb1a2b7` remains GO for Pair-B row `lipsync-postproc-costkey`; no lock release is required.

Cursor at send: 2026-06-15T11:40:34Z
