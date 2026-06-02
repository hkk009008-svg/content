"""dialogue_voice_mode resolution (global_settings key, default 'overlay')."""
from cinema.shots.controller import _dialogue_voice_mode  # new helper


def test_defaults_to_overlay():
    assert _dialogue_voice_mode({}) == "overlay"
    assert _dialogue_voice_mode({"other": 1}) == "overlay"


def test_respects_explicit_value():
    assert _dialogue_voice_mode({"dialogue_voice_mode": "native"}) == "native"
    assert _dialogue_voice_mode({"dialogue_voice_mode": "overlay"}) == "overlay"


def test_unknown_value_falls_back_to_overlay():
    # Guard against typos in project settings.
    assert _dialogue_voice_mode({"dialogue_voice_mode": "bogus"}) == "overlay"
