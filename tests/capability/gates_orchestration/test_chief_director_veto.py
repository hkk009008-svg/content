"""Offline capability tests for llm/chief_director.py veto-decision composition.

These exercise the ChiefDirector's OWN decision logic (the spec §7 blind spot) —
NOT the parse paths (test_chief_director_parse.py) or the gate's consumption
(test_auto_approve.py). No real LLM call: the no-client branches need zero mocking;
the except-fallback tiering monkeypatches _call_llm to return invalid JSON.

evaluate_generation_quality(self, image_path, reference_path, identity_result=None,
identity_score=0.0, ...) — image_path AND reference_path are both required
positionals, so every call passes image_path=None, reference_path=None.
"""
import types

import pytest

from llm.chief_director import ChiefDirector, _strip_json_fences


def _coherence(score):
    return types.SimpleNamespace(overall_coherence_score=score)


def _cd():
    cd = ChiefDirector(project={})
    cd.client = None  # ensure the no-client path even if a key leaks into the env
    return cd


@pytest.mark.offline
def test_no_client_identity_fail_requires_review(capability_record):
    cd = _cd()
    # Missing ChiefDirector evidence is an infrastructure state, not a quality
    # verdict, even when deterministic identity scoring failed.
    out = cd.evaluate_generation_quality(
        image_path=None, reference_path=None, identity_result=None,
        coherence_result=_coherence(0.9), identity_score=0.50,
    )
    assert out["decision"] == "REVIEW_REQUIRED"
    assert "mutation_level" not in out
    capability_record(claim_id="CD-01", passed=True)


@pytest.mark.offline
def test_no_client_coherence_only_fail_requires_review(capability_record):
    cd = _cd()
    # No client may not turn a coherence-only failure into ACCEPT.
    out = cd.evaluate_generation_quality(
        image_path=None, reference_path=None, identity_result=None,
        coherence_result=_coherence(0.30), identity_score=0.90,
    )
    assert out["decision"] == "REVIEW_REQUIRED"
    capability_record(claim_id="CD-02", passed=True)


@pytest.mark.offline
def test_except_fallback_mutation_level_tiering(capability_record):
    # The except-fallback (llm/chief_director.py:603-651) wraps json.loads of the LLM
    # reply — NOT the _call_llm call itself. So we make _call_llm RETURN unparseable
    # text; json.loads then raises and the except tiers the retry by identity_score:
    # >0.55->1, >0.40->2, else->3 (strict >). None->1.
    def _bad_json(*a, **k):
        return "}{ not valid json"

    def _level(identity_score, coherence_result):
        cd = ChiefDirector(project={})
        cd.client = object()        # truthy -> skip the no-client early return
        cd._call_llm = _bad_json    # returns garbage -> json.loads raises -> except-fallback
        out = cd.evaluate_generation_quality(
            image_path=None, reference_path=None, identity_result=None,
            coherence_result=coherence_result, identity_score=identity_score,
        )
        assert out["decision"] == "REVIEW_REQUIRED", out
        return out["mutation_level"]

    # numeric tiering: identity < 0.70 fails -> identity_passed=False -> no ACCEPT
    # short-circuit; coherence_result=None skips the prompt-builder's coherence_info
    # block (reads color_drift/lighting_consistency, llm/chief_director.py:517-524).
    assert _level(0.60, None) == 1
    assert _level(0.45, None) == 2
    assert _level(0.30, None) == 3
    # None identity (skipped) short-circuits to manual review before an LLM call;
    # it has no mutation-level inference because there was no measurable score.
    cd = ChiefDirector(project={})
    cd.client = object()
    cd._call_llm = _bad_json
    skipped = cd.evaluate_generation_quality(
        image_path=None,
        reference_path=None,
        identity_result=None,
        coherence_result=_coherence(0.30),
        identity_score=None,
    )
    assert skipped["decision"] == "REVIEW_REQUIRED"
    assert "mutation_level" not in skipped
    capability_record(claim_id="CD-03", passed=True)


@pytest.mark.offline
def test_validate_shot_prompts_no_client_requires_review(capability_record):
    cd = _cd()
    shots = [{"prompt": "a wide shot"}]
    out = cd.validate_shot_prompts(shots, {"id": "scene_1"})
    assert out["decision"] == "REVIEW_REQUIRED"
    assert out["violations"]
    assert out["shots"] is shots
    capability_record(claim_id="CD-04", passed=True)


@pytest.mark.offline
def test_strip_json_fences(capability_record):
    assert _strip_json_fences('```json\n{"a":1}\n```') == '{"a":1}'
    assert _strip_json_fences('```\n{"a":1}\n```') == '{"a":1}'
    assert _strip_json_fences('{"a":1}') == '{"a":1}'
    capability_record(claim_id="CD-05", passed=True)


@pytest.mark.offline
def test_get_diagnostic_summary_empty_and_populated(capability_record):
    cd = _cd()
    assert cd.get_diagnostic_summary() == "No diagnostic data collected."
    cd.diagnostic_log.append(
        {"stage": "shot_validation", "decision": "APPROVED", "score": 0.9})
    summary = cd.get_diagnostic_summary()
    assert "shot_validation" in summary and "APPROVED" in summary and "0.9" in summary
    capability_record(claim_id="CD-06", passed=True)
