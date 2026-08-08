"""Text-to-canonical generation: the one generation with no image source.

For a DESCRIBED character this image is not a likeness of anything — it IS the
character, and every later panel is an edit of it. `_generate_multi_angle_refs`
then works unchanged, because those panels are already image-conditioned edits.
The gap was only ever panel 1.

For a REAL person the same call would produce a stranger:
`classify_generated_origin("real", requested_yaw=..., source_yaw="")` returns
"invented" precisely because nothing about the subject informed the image.
"""

from __future__ import annotations

import pytest
from types import SimpleNamespace

import domain.character_manager as cm
from domain.reference_set import classify_generated_origin


class _RealTracker:
    """Satisfies has_paid_attempt_authority without reaching a provider."""

    paid_attempt_authority_version = 1

    def __getattr__(self, _name):
        return lambda *a, **k: None


def test_an_empty_description_is_refused_before_any_spend() -> None:
    """A described character with nothing to describe cannot be defined."""

    with pytest.raises(ValueError, match="needs a description"):
        cm.generate_canonical_from_description("   ", "/tmp/x", cost_tracker=_RealTracker())


def test_a_stubbed_tracker_cannot_authorise_paid_generation(monkeypatch) -> None:
    """The durable ledger is what makes an interrupted run resume, not repay.

    This is the same guard that refused a stubbed tracker on the local FLUX.2
    path — a duck-typed mock must never route a provider call into a durable
    polling path with no real ledger behind it.
    """

    # `settings` is a FROZEN dataclass, so the module reference is replaced
    # rather than a field assigned.
    monkeypatch.setattr(cm, "FAL_AVAILABLE", True)
    monkeypatch.setattr(cm, "settings", SimpleNamespace(fal_key="k" * 32))

    class _Stub:
        def __getattr__(self, _name):
            return lambda *a, **k: None

    with pytest.raises(TypeError, match="paid-attempt tracker"):
        cm.generate_canonical_from_description("a tall man", "/tmp/x", cost_tracker=_Stub())


def test_missing_fal_stops_rather_than_silently_skipping(monkeypatch) -> None:
    """_generate_multi_angle_refs returns the canonical SILENTLY when FAL is
    absent, which is how the sheet feature sat un-run and looked absent. This
    path raises instead."""

    monkeypatch.setattr(cm, "FAL_AVAILABLE", False)
    with pytest.raises(RuntimeError, match="FAL is unavailable"):
        cm.generate_canonical_from_description(
            "a tall man", "/tmp/x", cost_tracker=_RealTracker()
        )


def test_the_provenance_of_a_text_generated_canonical(monkeypatch) -> None:
    """What the record must say about the image this produces.

    Described: "defined" — it is the ground truth, not an edit of one.
    Real: "invented" — a stranger, because no source informed it.
    """

    assert classify_generated_origin(
        "described", requested_yaw="front", source_yaw=""
    ) == "defined"
    assert classify_generated_origin(
        "real", requested_yaw="front", source_yaw=""
    ) == "invented"


def test_the_recorded_cost_is_the_one_the_caller_will_be_charged() -> None:
    """A cost shown before the click must be the cost the ledger reserves."""

    assert cm.API_COST_USD[cm._TEXT_TO_IMAGE_ENGINE] == 0.05
    assert cm._TEXT_TO_IMAGE_APPLICATION == "fal-ai/flux-pro/v1.1-ultra"
