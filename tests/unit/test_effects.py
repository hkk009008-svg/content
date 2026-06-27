# tests/unit/test_effects.py
"""Characterization tests for audio.effects voice-FX router (offline, mocked).

Pins CORRECT current behaviour of apply_voice_effect's engine priority
(AU > Pedalboard > FFmpeg) and its never-raise / always-return-a-valid-path
contract, plus the two engine helpers' return-original-on-failure sentinel that
the router's short-circuit logic depends on. No real ffmpeg/plugin invocation,
no spend.

Tier 3 (Audio DSP) of the 2026-06-26 coordinator test-coverage directive;
R-BRIEF docs/superpowers/briefs/2026-06-27-testcov-pairb-tier3.md.
"""
from __future__ import annotations

import pytest

# effects.py hard-imports pedalboard at module top (no graceful fallback);
# skip cleanly where the optional native dep is absent (mirrors the cv2
# importorskip convention used by test_coherence_analyzer.py).
pytest.importorskip("pedalboard")

from unittest.mock import patch  # noqa: E402

import audio.effects as effects  # noqa: E402
from audio.effects import apply_voice_effect  # noqa: E402


# ---- engine priority: AU > Pedalboard > FFmpeg (effects.py:248-284) ------

def test_au_plugin_wins_and_short_circuits_other_engines():
    with patch.object(effects, "apply_au_plugin", return_value="/out/au.mp3") as au, \
         patch.object(effects, "apply_pedalboard_chain") as pb, \
         patch("subprocess.run") as run:
        result = apply_voice_effect(
            "/in.wav", "/out/au.mp3", effect="cinema_reverb",
            au_plugin="Decapitator", pedalboard_chain=[{"type": "reverb"}],
        )
    assert result == "/out/au.mp3"
    au.assert_called_once()
    pb.assert_not_called()          # priority short-circuit (effects.py:251-252)
    run.assert_not_called()


def test_au_noop_falls_through_to_pedalboard():
    # helper returns the ORIGINAL path (identity sentinel) -> not a real result,
    # so the router must fall through to the next engine (effects.py:251 `!=`).
    with patch.object(effects, "apply_au_plugin", return_value="/in.wav") as au, \
         patch.object(effects, "apply_pedalboard_chain", return_value="/out/pb.mp3") as pb, \
         patch("subprocess.run") as run:
        result = apply_voice_effect(
            "/in.wav", "/out/pb.mp3", effect="cinema_reverb",
            au_plugin="Missing", pedalboard_chain=[{"type": "reverb"}],
        )
    assert result == "/out/pb.mp3"
    au.assert_called_once()
    pb.assert_called_once()
    run.assert_not_called()


def test_pedalboard_used_when_no_au_plugin():
    with patch.object(effects, "apply_pedalboard_chain", return_value="/out/pb.mp3") as pb, \
         patch("subprocess.run") as run:
        result = apply_voice_effect(
            "/in.wav", "/out/pb.mp3", pedalboard_chain=[{"type": "gain", "gain_db": 2}],
        )
    assert result == "/out/pb.mp3"
    pb.assert_called_once()
    run.assert_not_called()


# ---- FFmpeg path + no-op / failure contract (effects.py:260-284) ---------

def test_effect_none_returns_original_unchanged():
    with patch("subprocess.run") as run:
        result = apply_voice_effect("/in.wav", "/out.mp3", effect="none")
    assert result == "/in.wav"      # effects.py:261-262
    run.assert_not_called()


def test_unknown_effect_returns_original():
    with patch("subprocess.run") as run:
        result = apply_voice_effect("/in.wav", "/out.mp3", effect="does_not_exist")
    assert result == "/in.wav"      # effect not in VOICE_EFFECTS (effects.py:261-262)
    run.assert_not_called()


def test_ffmpeg_success_returns_output_path():
    with patch("subprocess.run") as run, \
         patch.object(effects.os.path, "exists", return_value=True), \
         patch.object(effects.os.path, "getsize", return_value=4096):
        result = apply_voice_effect("/in.wav", "/out.mp3", effect="telephone")
    assert result == "/out.mp3"     # non-empty output -> success (effects.py:277-279)
    run.assert_called_once()


def test_ffmpeg_empty_output_falls_back_to_original():
    # ffmpeg "ran" but produced a missing/0-byte file -> return original (effects.py:280)
    with patch("subprocess.run"), \
         patch.object(effects.os.path, "exists", return_value=True), \
         patch.object(effects.os.path, "getsize", return_value=0):
        result = apply_voice_effect("/in.wav", "/out.mp3", effect="telephone")
    assert result == "/in.wav"


def test_ffmpeg_raises_is_swallowed_and_returns_original():
    # the router NEVER propagates a subprocess failure (effects.py:282-284)
    with patch("subprocess.run", side_effect=OSError("ffmpeg not found")):
        result = apply_voice_effect("/in.wav", "/out.mp3", effect="telephone")
    assert result == "/in.wav"


# NOTE: apply_voice_effect:265 (`if not filter_chain: return audio_path`) is a
# DEFENSIVE branch unreachable via the shipped presets — the only preset with
# filter=None is "none", already returned at :261. We do not fabricate an
# unreachable-path test for it (verified: only "none" has filter=None).


# ---- Rule #13 sibling audit: the helpers' return-original sentinel -------
# The router's short-circuit (`result != audio_path`) is COUPLED to these
# helpers returning the original path (identity) on any no-op/failure. A future
# engine added to the router must preserve this sentinel or the priority logic
# silently breaks.

def test_apply_au_plugin_not_found_returns_original():
    # no AU components directory matches -> returns the original path, never raises
    with patch.object(effects.os.path, "exists", return_value=False):
        assert effects.apply_au_plugin("/in.wav", "/out.mp3", "Nonexistent") == "/in.wav"


def test_apply_pedalboard_chain_empty_returns_original():
    assert effects.apply_pedalboard_chain("/in.wav", "/out.mp3", effects=None) == "/in.wav"
    assert effects.apply_pedalboard_chain("/in.wav", "/out.mp3", effects=[]) == "/in.wav"


def test_apply_pedalboard_chain_unknown_types_filter_to_empty_returns_original():
    # all fx types unknown -> chain stays empty -> return original, no raise (effects.py:197-198)
    assert effects.apply_pedalboard_chain(
        "/in.wav", "/out.mp3", effects=[{"type": "no_such_fx"}],
    ) == "/in.wav"
