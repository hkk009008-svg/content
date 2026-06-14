"""Live regression for Wave-1 Task 7 — costtracker-perf-uncounted (W1:CRITICAL).

Origin: hardening-campaign discovery wf_13f9d2f6-f93 confirmed[4]. The budget gate
reads ONLY the shared ``CostTracker.spent_usd`` accumulator, but two things broke that
contract:

  (a) ``log_api()`` / ``log_llm()`` wrote SQLite (via ``log()``) without incrementing
      ``spent_usd`` — only ``record_api_call()`` did. So any phase that called
      ``log_api()``/``log_llm()`` directly was invisible to the gate.
  (b) ``record_api_call()`` incremented ``spent_usd`` itself AND called ``log_api()``,
      so once the increment moves to the ``log()`` chokepoint the old ``record_api_call``
      increment must be removed or it double-counts.
  (c) the 4 performance phases (live_portrait / viggle / act_one / driving_video) each
      constructed a THROWAWAY ``CostTracker()`` and logged onto it — the increment landed
      on a discarded instance, never the shared one the gate reads.
  (d) the controller dispatched performance without passing its shared tracker.

THE FIX (all parts land atomically):
  (a) increment ``spent_usd`` at the ``log()`` chokepoint (both log_api/log_llm funnel there);
  (b) remove the now-duplicate increment in ``record_api_call()``;
  (c) thread an optional shared ``cost_tracker`` through ``performance/_router.dispatch`` ->
      ``_dispatch_inner`` -> each phase's ``_cost_log`` (``cost_tracker or CostTracker()``);
  (d) the controller passes ``self.cost_tracker`` at the dispatch + driving-synth call sites.

These tests assert the fix BEYOND the xfail pin (which only checked part (a)): the
double-count guard (b) and the threading seam (c) that actually closes the per-shot hole.
The xfail pins test_log_api_increments_spent_usd / test_log_llm_increments_spent_usd were
removed from tests/unit/test_discovery_cost_xfail.py when this landed (XPASS-flip); the
lipsync-postproc-costkey pin there is a DIFFERENT defect and stays xfail.
"""
import pytest

from domain.performance import ENGINE_ACT_ONE


# ---------------------------------------------------------------------------
# (a) log_api / log_llm now increment the shared accumulator via the log() chokepoint
# ---------------------------------------------------------------------------

def test_log_api_increments_spent_usd(tmp_path):
    """log_api() must update spent_usd so the budget gate sees the spend."""
    from cost_tracker import CostTracker

    tracker = CostTracker(db_path=str(tmp_path / "cost.db"), budget_usd=10.0)
    assert tracker.spent_usd == 0.0

    tracker.log_api(
        provider="comfyui", model="COMFYUI_PULID",
        operation="image_generation", cost_usd=0.04,
    )
    assert tracker.spent_usd == pytest.approx(0.04)


def test_log_llm_increments_spent_usd(tmp_path):
    """log_llm() must update spent_usd so the budget gate sees LLM spend."""
    from cost_tracker import CostTracker

    tracker = CostTracker(db_path=str(tmp_path / "cost.db"), budget_usd=10.0)
    assert tracker.spent_usd == 0.0

    # claude-sonnet-4-6: $3.00/M input -> 100k input tokens == $0.30
    tracker.log_llm(
        model="claude-sonnet-4-6", operation="script_generation",
        input_tokens=100_000, output_tokens=1_000,
    )
    assert tracker.spent_usd > 0.0


def test_bare_log_increments_spent_usd(tmp_path):
    """The chokepoint itself: log() accumulates, so spent_usd == sum of logged costs."""
    from cost_tracker import CostTracker

    tracker = CostTracker(db_path=str(tmp_path / "cost.db"), budget_usd=10.0)
    tracker.log(provider="a", model="m", operation="o", cost_usd=0.10)
    tracker.log(provider="b", model="m", operation="o", cost_usd=0.05)
    assert tracker.spent_usd == pytest.approx(0.15)
    # And it mirrors the SQLite truth (get_session_cost sums the DB).
    assert tracker.spent_usd == pytest.approx(tracker.get_session_cost())


# ---------------------------------------------------------------------------
# (b) record_api_call increments EXACTLY once — no double-count after the :407 removal
# ---------------------------------------------------------------------------

def test_record_api_call_single_increment_no_double_count(tmp_path):
    """record_api_call() calls log_api() (-> log(), which now increments). It must
    NOT also increment separately, or every recorded call double-counts."""
    from cost_tracker import CostTracker, API_COST_USD

    tracker = CostTracker(db_path=str(tmp_path / "cost.db"), budget_usd=100.0)
    cost = tracker.record_api_call("VEO")
    assert cost > 0.0, "precondition: VEO must be priced"
    # spent_usd reflects exactly ONE increment of the recorded cost (not 2x).
    assert tracker.spent_usd == pytest.approx(cost)

    tracker.record_api_call("VEO")
    assert tracker.spent_usd == pytest.approx(2 * cost)


# ---------------------------------------------------------------------------
# (c)+(d) the throwaway-instance hole: dispatch forwards a SHARED tracker so spend
#         lands where the budget gate reads it
# ---------------------------------------------------------------------------

def test_dispatch_forwards_shared_cost_tracker(tmp_path, monkeypatch):
    """dispatch() -> _dispatch_inner -> phase adapter must forward the SAME shared
    cost_tracker instance, so spend accumulates on it rather than on a throwaway."""
    from cost_tracker import CostTracker
    from performance import _router

    shared = CostTracker(db_path=str(tmp_path / "cost.db"), budget_usd=100.0)
    received = {}

    def _stub(keyframe_path, audio_path, output_mp4, *, driving_video_path=None,
              duration_s=5.0, character_id="", shot_id="", video_id="",
              poll_timeout_s=300, cost_tracker=None):
        received["tracker"] = cost_tracker
        if cost_tracker is not None:
            cost_tracker.log_api(provider="runway", model="act_one",
                                 operation="perf", cost_usd=0.25)
        return output_mp4

    # _dispatch_inner imports generate_act_one_performance lazily inside the branch,
    # so patching the module attribute is picked up at call time.
    monkeypatch.setattr("performance.act_one.generate_act_one_performance", _stub)

    before = shared.spent_usd
    out = _router.dispatch(
        ENGINE_ACT_ONE,
        keyframe_path=str(tmp_path / "k.png"),
        audio_path=None,
        driving_video_path=None,
        output_mp4=str(tmp_path / "o.mp4"),
        cost_tracker=shared,
    )
    assert out == str(tmp_path / "o.mp4")
    assert received["tracker"] is shared, (
        "dispatch did not forward the shared CostTracker to the phase adapter — "
        "per-shot spend would land on a throwaway instance (costtracker-perf-uncounted)"
    )
    assert shared.spent_usd > before, "spend did not accumulate on the shared tracker"


def test_perf_cost_log_uses_passed_tracker(tmp_path):
    """Each phase's _cost_log must log onto the passed shared tracker, not a throwaway."""
    from cost_tracker import CostTracker
    from performance import live_portrait, viggle, act_one, driving_video

    # live_portrait._cost_log(duration_s, shot_id, video_id, cost_tracker=...)
    t1 = CostTracker(db_path=str(tmp_path / "c1.db"), budget_usd=100.0)
    live_portrait._cost_log(5.0, "", "", cost_tracker=t1)
    assert t1.spent_usd > 0.0

    # viggle._cost_log(shot_id, video_id, cost_tracker=...)
    t2 = CostTracker(db_path=str(tmp_path / "c2.db"), budget_usd=100.0)
    viggle._cost_log("", "", cost_tracker=t2)
    assert t2.spent_usd > 0.0

    # act_one._cost_log(operation, duration_s, shot_id, video_id, cost_tracker=...)
    t3 = CostTracker(db_path=str(tmp_path / "c3.db"), budget_usd=100.0)
    act_one._cost_log("performance_capture", 5.0, "", "", cost_tracker=t3)
    assert t3.spent_usd > 0.0

    # driving_video._cost_log(provider, duration_s, shot_id, video_id, cost_tracker=...)
    t4 = CostTracker(db_path=str(tmp_path / "c4.db"), budget_usd=100.0)
    driving_video._cost_log("hedra", 5.0, "", "", cost_tracker=t4)
    assert t4.spent_usd > 0.0


def test_dispatch_without_cost_tracker_is_backward_compatible(tmp_path, monkeypatch):
    """Existing callers that pass no cost_tracker must keep working (param is optional)."""
    from performance import _router

    def _stub(keyframe_path, audio_path, output_mp4, *, driving_video_path=None,
              duration_s=5.0, character_id="", shot_id="", video_id="",
              poll_timeout_s=300, cost_tracker=None):
        assert cost_tracker is None  # no tracker supplied -> phase falls back to throwaway
        return output_mp4

    monkeypatch.setattr("performance.act_one.generate_act_one_performance", _stub)
    out = _router.dispatch(
        ENGINE_ACT_ONE,
        keyframe_path=str(tmp_path / "k.png"),
        audio_path=None,
        driving_video_path=None,
        output_mp4=str(tmp_path / "o.mp4"),
    )
    assert out == str(tmp_path / "o.mp4")
