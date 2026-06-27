# tests/unit/test_voiceover.py
"""Characterization tests for audio.voiceover.get_voice_direction (pure, no I/O).

Pins CORRECT current behaviour: exact match, case/whitespace normalization,
fuzzy substring resolution with INSERTION-order precedence (not alphabetical),
and the unknown -> "natural" default (no KeyError). Also pins the always-present
key shape that web_server.py re-exports for the UI dropdown. Test-only.

Tier 3 (Audio DSP) of the 2026-06-26 coordinator test-coverage directive;
R-BRIEF docs/superpowers/briefs/2026-06-27-testcov-pairb-tier3.md.
"""
from __future__ import annotations

from audio.voiceover import (
    get_voice_direction,
    VOICE_DIRECTIONS,
    DELIVERY_STYLES,
)

# The four keys every profile carries; web_server.py re-exports VOICE_DIRECTIONS
# for the UI, so this shape is a cross-surface contract. `markup` is optional.
_REQUIRED_KEYS = {"stability", "similarity", "style", "speaker_boost"}


# ---- resolution branches (voiceover.py:294 / :298-300 / :303) -----------

def test_exact_match_returns_that_profile():
    # returns the live dict object, not a copy (voiceover.py:295)
    assert get_voice_direction("natural") is VOICE_DIRECTIONS["natural"]


def test_case_and_whitespace_are_normalized():
    # delivery.lower().strip() (voiceover.py:291)
    assert get_voice_direction("  WHISPER ") is VOICE_DIRECTIONS["whisper"]


def test_fuzzy_substring_match_resolves_to_the_contained_key():
    # a sentence that merely CONTAINS a key resolves to that key (voiceover.py:298-300)
    assert get_voice_direction("he said, whispering") is VOICE_DIRECTIONS["whisper"]


def test_unknown_delivery_defaults_to_natural_without_keyerror():
    # no exact and no fuzzy hit -> "natural" fallback, never raises (voiceover.py:303)
    assert get_voice_direction("zzz-nonsense-not-a-style") is VOICE_DIRECTIONS["natural"]


def test_fuzzy_precedence_follows_insertion_order_not_alphabetical():
    # The fuzzy loop iterates VOICE_DIRECTIONS in INSERTION order while
    # DELIVERY_STYLES is alphabetical -> the first key in insertion order that is a
    # substring wins, even if another contained key sorts earlier. A future dict
    # reorder that silently changes which profile a phrase resolves to is caught here.
    # Search for an unambiguous pair (insertion-first is alphabetically LATER, no
    # confounding key is a substring, and neither is the "natural" fallback so a pass
    # can't be misread as the default firing).
    keys = list(VOICE_DIRECTIONS.keys())
    chosen = None
    for i, k_early in enumerate(keys):
        if k_early == "natural":
            continue
        for k_late in keys[i + 1:]:
            if k_late == "natural":
                continue
            if not (k_early > k_late):          # want insertion-first alphabetically later
                continue
            if k_early in k_late or k_late in k_early:
                continue
            delivery = f"{k_early}|{k_late}"
            if [k for k in keys if k not in (k_early, k_late) and k in delivery]:
                continue                        # a third key would confound precedence
            if delivery in VOICE_DIRECTIONS:
                continue                        # must exercise the fuzzy loop, not exact match
            chosen = (k_early, k_late, delivery)
            break
        if chosen:
            break

    assert chosen is not None, "expected a key pair to demonstrate insertion-order precedence"
    k_early, k_late, delivery = chosen
    result = get_voice_direction(delivery)
    assert result is VOICE_DIRECTIONS[k_early]       # insertion-order-first wins
    assert result is not VOICE_DIRECTIONS[k_late]    # NOT the alphabetically-earlier key


# ---- Rule #13 sibling/shape contract ------------------------------------

def test_every_profile_has_the_required_key_shape():
    for name, profile in VOICE_DIRECTIONS.items():
        missing = _REQUIRED_KEYS - set(profile)
        assert not missing, f"profile {name!r} missing required keys {missing}"


def test_markup_is_optional_not_universal():
    # callers must not assume `markup` is present on every profile
    have = [k for k, d in VOICE_DIRECTIONS.items() if "markup" in d]
    assert have, "expected some profiles to carry markup"
    assert len(have) < len(VOICE_DIRECTIONS), "markup is optional, not on every profile"


def test_delivery_styles_is_sorted_keys():
    # voiceover.py:307 — DELIVERY_STYLES drives the frontend dropdown
    assert DELIVERY_STYLES == sorted(VOICE_DIRECTIONS.keys())
