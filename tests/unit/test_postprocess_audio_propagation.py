"""§3 audio-sibling family — postprocess audio-flag-propagation (operator2).

THE DEFECT (verified 2026-06-13, operator2 workflow wf_69ba3ee7-acd; originating
finds: operator-1 `4ad4c21` strip audio-loss, director2 PM7 §3 flag-propagation
design). `apply_correction` mints a postprocess variant via
`make_take("postprocess", metadata={"action","params"})` — no audio-flag slot.
Across the 6 transform branches:

  * STRIP    — upscale (`upscale_video_seedvr2`), face_swap (`face_swap_video_frames`)
               produce VIDEO-ONLY clips (no source-audio re-mux).
  * PRESERVE — rife (already re-muxes), color_grade (`-c:a copy`), speed (atempo)
               carry the source audio through.
  * GENERATE — lip_sync embeds fresh dialogue.

…but NO branch sets `audio_embedded` / `dialogue_audio_in_clip` on the variant.
When such a variant is approved as the shot's final take, the assembler
(`_build_scene_packages`) sees no flag, generates standalone scene-TTS, and the
final-mux filtergraph routes voice to the TTS input and DROPS the clip's embedded
`[0:a]` (cinema_pipeline.py:1545-1547) — the take's real voice is REPLACED by
generic TTS (voice-loss, NOT double-voice; symptom re-characterised by the
wf_69ba3ee7 synthesis — the filtergraph never mixes [0:a] alongside the TTS).

THE FIX (3 parts):
  1. Re-mux source audio in the 2 strippers, IN PLACE, mirroring
     lip_sync._restore_audio_track. Best-effort + source-audio-gated: a dialogue
     source gets its audio restored onto the (higher-res / swapped) clip; a silent
     source is left byte-identical (re-mux skipped).
  2. Inherit the base take's audio flags onto the variant when the variant clip
     actually carries audio (gated on phase_c_ffmpeg._has_audio_stream) — covers
     PRESERVE actions + successfully re-muxed STRIP; a failed-remux / silent strip
     stays unflagged so the assembler fills with TTS (degraded, not worse).
  3. lip_sync sets dialogue_audio_in_clip=True DIRECTLY (it GENERATES dialogue;
     a silent base has no flag to inherit) — completeness find C4, mirrors the
     motion-take path at controller.py:1801.

Real-seam: real ffmpeg/ffprobe build the fixtures and assert audio streams; only
the fal cloud round-trip, the lipsync engine, and the storage mutator are mocked.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import dataclasses
from unittest.mock import MagicMock, patch

import pytest

_HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
pytestmark = pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH")


# ---------------------------------------------------------------------------
# Real-ffmpeg fixture helpers (mirror tests/unit/test_rife_audio_remux.py)
# ---------------------------------------------------------------------------

def _make_clip(path, *, with_audio: bool) -> None:
    """Build a 1s 64x64 test clip, optionally with a 440Hz sine audio track."""
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=64x64:rate=10"]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:a", "aac"]
    cmd += ["-pix_fmt", "yuv420p", "-c:v", "libx264", "-shortest", str(path)]
    subprocess.run(cmd, check=True, capture_output=True)


def _has_audio(path) -> bool:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return "audio" in out.stdout


# ===========================================================================
# Part 1a — upscale_video_seedvr2 re-mux (lip_sync.py)
# ===========================================================================

def _mock_seedvr_cloud(monkeypatch, cloud_returns_path):
    """Patch upscale_video_seedvr2's cloud round-trip so safe_download drops
    `cloud_returns_path` (the video-only SeedVR2 result) at the requested dest."""
    import types

    import lip_sync

    monkeypatch.setattr(lip_sync, "FAL_AVAILABLE", True, raising=False)
    monkeypatch.setattr(lip_sync, "ENV_SETTINGS", types.SimpleNamespace(fal_key="test-key"))
    fake_fal = MagicMock()
    fake_fal.upload_file.return_value = "https://fake/upload"
    fake_fal.subscribe.return_value = {"video": {"url": "https://fake/seedvr.mp4"}}
    monkeypatch.setattr(lip_sync, "fal_client", fake_fal, raising=False)

    def _fake_download(url, dest):
        shutil.copyfile(cloud_returns_path, dest)
        return dest

    monkeypatch.setattr(lip_sync, "safe_download", _fake_download)


class TestUpscaleAudioRemux:

    def test_upscale_restores_source_audio(self, tmp_path, monkeypatch):
        """A SeedVR2 upscale of an audio-bearing dialogue clip must return a clip
        that STILL has audio — the cloud returns video-only; without a re-mux the
        source dialogue is silently dropped (operator-1's strip find)."""
        import lip_sync

        source = tmp_path / "source_with_audio.mp4"
        _make_clip(source, with_audio=True)
        assert _has_audio(source), "fixture sanity: source must have audio"

        cloud_video_only = tmp_path / "seedvr_result.mp4"
        _make_clip(cloud_video_only, with_audio=False)
        _mock_seedvr_cloud(monkeypatch, cloud_video_only)

        out = lip_sync.upscale_video_seedvr2(str(source), str(tmp_path / "out.mp4"))

        assert out is not None
        assert _has_audio(out), "upscale output silently dropped the source audio track"

    def test_upscale_silent_source_stays_video_only(self, tmp_path, monkeypatch):
        """A genuinely silent (non-dialogue) source upscales fine and stays
        video-only — re-mux is skipped for sources with no audio (byte-identical
        to pre-fix behavior for the common B-roll path)."""
        import lip_sync

        source = tmp_path / "silent_source.mp4"
        _make_clip(source, with_audio=False)
        assert not _has_audio(source)

        cloud_video_only = tmp_path / "seedvr_result.mp4"
        _make_clip(cloud_video_only, with_audio=False)
        _mock_seedvr_cloud(monkeypatch, cloud_video_only)

        out = lip_sync.upscale_video_seedvr2(str(source), str(tmp_path / "out.mp4"))

        assert out is not None, "upscale must still succeed on a silent clip"
        assert not _has_audio(out)

    def test_upscale_remux_failure_keeps_video_only_output(self, tmp_path, monkeypatch):
        """STRIPPER semantics differ from RIFE: if the audio re-mux fails, the
        upscaled (video-only) clip is KEPT and the path is still returned (NOT
        None) — the flag-propagation safety net leaves it unflagged so the
        assembler fills with TTS. Audio integrity is recovered at assembly, so the
        higher-res upscale is not thrown away."""
        import lip_sync

        source = tmp_path / "source_with_audio.mp4"
        _make_clip(source, with_audio=True)
        cloud_video_only = tmp_path / "seedvr_result.mp4"
        _make_clip(cloud_video_only, with_audio=False)
        _mock_seedvr_cloud(monkeypatch, cloud_video_only)
        # Force the re-mux to fail.
        monkeypatch.setattr(lip_sync, "_restore_audio_track", lambda *a, **k: False)

        out_path = tmp_path / "out.mp4"
        out = lip_sync.upscale_video_seedvr2(str(source), str(out_path))

        assert out == str(out_path), "upscale must keep the video-only clip on re-mux failure"
        assert out is not None


# ===========================================================================
# Part 1b — face_swap_video_frames re-mux (phase_c_vision.py)
# ===========================================================================

def _fal_settings():
    from config.settings import settings as _real_settings
    return dataclasses.replace(_real_settings, fal_key="fal_test_key")


class TestFaceSwapAudioRemux:

    def test_face_swap_fal_restores_source_audio(self, tmp_path):
        """A fal.ai PixVerse swap returns video-only; the swap of an audio-bearing
        dialogue clip must return a clip that STILL has audio (operator-1's second
        strip sibling)."""
        import phase_c_vision as pcv

        source = tmp_path / "source_with_audio.mp4"
        _make_clip(source, with_audio=True)
        assert _has_audio(source)
        out = tmp_path / "swapped.mp4"

        mock_fal = MagicMock()
        mock_fal.upload_file.return_value = "http://fal/upload"
        mock_fal.subscribe.return_value = {"video": {"url": "http://fal/swap.mp4"}}

        import urllib.request as _urllib_req

        def _fake_retrieve(url, dest):
            _make_clip(dest, with_audio=False)  # cloud swap output is video-only

        with patch.object(pcv, "settings", _fal_settings()), \
             patch.dict(sys.modules, {"fal_client": mock_fal}), \
             patch.object(_urllib_req, "urlretrieve", _fake_retrieve):
            result = pcv.face_swap_video_frames(str(source), str(tmp_path / "ref.jpg"), str(out))

        assert result == str(out)
        assert _has_audio(out), "face_swap output silently dropped the source audio track"

    def test_face_swap_silent_source_stays_video_only(self, tmp_path):
        """A silent source face-swaps fine and stays video-only (re-mux skipped)."""
        import phase_c_vision as pcv

        source = tmp_path / "silent_source.mp4"
        _make_clip(source, with_audio=False)
        out = tmp_path / "swapped.mp4"

        mock_fal = MagicMock()
        mock_fal.upload_file.return_value = "http://fal/upload"
        mock_fal.subscribe.return_value = {"video": {"url": "http://fal/swap.mp4"}}

        import urllib.request as _urllib_req

        def _fake_retrieve(url, dest):
            _make_clip(dest, with_audio=False)

        with patch.object(pcv, "settings", _fal_settings()), \
             patch.dict(sys.modules, {"fal_client": mock_fal}), \
             patch.object(_urllib_req, "urlretrieve", _fake_retrieve):
            result = pcv.face_swap_video_frames(str(source), str(tmp_path / "ref.jpg"), str(out))

        assert result == str(out)
        assert not _has_audio(out)


# ===========================================================================
# Part 2 + Part 3 — flag propagation through the REAL apply_correction dispatch
# ===========================================================================

def _make_correction_ctrl(tmp_path, base_meta: dict):
    """Build a minimal ShotController whose base motion take carries `base_meta`,
    capturing the postprocess variant the dispatch stores (real apply_correction
    body; only storage + the transform are mocked)."""
    from cinema.shots.controller import ShotController

    base_path = str(tmp_path / "base.mp4")
    _make_clip(base_path, with_audio=True)

    shot = {
        "id": "shot_1_0",
        "plan_status": "approved",
        "characters_in_frame": ["char_1"],
        "camera": "medium",
        "target_api": "AUTO",
        "approved_final_take_id": "take_base",
        "motion_takes": [{"id": "take_base", "kind": "motion", "path": base_path, "metadata": dict(base_meta)}],
        "postprocess_variants": [],
    }
    scene = {
        "id": "scene_1", "title": "T", "action": "A", "location_id": "loc_1",
        "shots": [shot], "characters_present": ["char_1"],
    }
    project = {
        "id": "proj_1", "scenes": [scene],
        "characters": [{"id": "char_1", "name": "Alice"}],
        "objects": [], "locations": [],
        "global_settings": {"face_swap_enabled": True},
    }

    host = MagicMock()
    host._refresh_project_snapshot.return_value = project
    host._ensure_scene_audio.return_value = str(tmp_path / "scene_tts.mp3")
    lifecycle = MagicMock()
    runstate = MagicMock()
    runstate.shot_results = {}
    core = MagicMock()
    core.project = project
    core.project_dir = str(tmp_path)

    ctrl = ShotController(core=core, lifecycle=lifecycle, host=host, runstate=runstate)
    ctrl._take_output_path = MagicMock(
        side_effect=lambda sid, tid, ext: str(tmp_path / f"{tid}{ext}")
    )

    def _capture_mutate(shot_id, mutator):
        fake_shot: dict = {}
        mutator({}, fake_shot)
        return fake_shot["postprocess_variants"][-1]

    ctrl._mutate_shot = MagicMock(side_effect=_capture_mutate)
    return ctrl


def _audio_writing_transform(out_path, *a, **k):
    """Stand-in for a PRESERVE transform: writes an audio-bearing clip to out."""
    _make_clip(out_path, with_audio=True)
    return out_path


class TestApplyCorrectionFlagPropagation:

    def test_color_grade_variant_inherits_audio_embedded(self, tmp_path):
        """PRESERVE action on an audio_embedded base → variant inherits the flag
        (the assembler will then suppress redundant scene-TTS)."""
        ctrl = _make_correction_ctrl(tmp_path, {"has_dialogue": True, "audio_embedded": True})

        def _grade(video_path, output_path, **kw):
            _make_clip(output_path, with_audio=True)
            return output_path

        with patch("phase_c_ffmpeg.apply_color_grade", _grade):
            result = ctrl.apply_correction("shot_1_0", "color_grade", take_id="take_base")

        assert result["success"] is True, result
        assert result["take"]["metadata"].get("audio_embedded") is True

    def test_speed_variant_inherits_dialogue_audio_in_clip(self, tmp_path):
        """PRESERVE action on a dialogue_audio_in_clip (overlay) base → inherits."""
        ctrl = _make_correction_ctrl(tmp_path, {"has_dialogue": True, "dialogue_audio_in_clip": True})

        def _speed(video_path, output_path, **kw):
            _make_clip(output_path, with_audio=True)
            return output_path

        with patch("phase_c_ffmpeg.adjust_speed", _speed):
            result = ctrl.apply_correction("shot_1_0", "speed", params={"factor": 2.0}, take_id="take_base")

        assert result["success"] is True, result
        assert result["take"]["metadata"].get("dialogue_audio_in_clip") is True

    def test_strip_variant_without_audio_gets_no_flag(self, tmp_path):
        """STRIP action whose output has NO audio (re-mux failed / silent) must NOT
        inherit the base flag — the assembler then fills with TTS (degraded, not a
        silent clip falsely claiming embedded audio)."""
        ctrl = _make_correction_ctrl(
            tmp_path,
            {"has_dialogue": True, "audio_embedded": True, "dialogue_audio_in_clip": True},
        )

        def _upscale(video_path, output_path, **kw):
            _make_clip(output_path, with_audio=False)  # strip → video-only
            return output_path

        with patch("cinema.shots.controller.upscale_video_seedvr2", _upscale):
            result = ctrl.apply_correction("shot_1_0", "upscale", take_id="take_base")

        assert result["success"] is True, result
        # BOTH flags must stay absent on a video-only STRIP — the single
        # _has_audio_stream guard covers both; assert both so a future guard-split
        # that leaks dialogue_audio_in_clip is caught (§3 verify NIT-2).
        assert result["take"]["metadata"].get("audio_embedded") is not True
        assert result["take"]["metadata"].get("dialogue_audio_in_clip") is not True

    def test_preserve_variant_no_flag_when_base_unflagged(self, tmp_path):
        """PRESERVE action on an UNFLAGGED base → no flag fabricated (nothing to
        inherit; the base never carried embedded audio)."""
        ctrl = _make_correction_ctrl(tmp_path, {"has_dialogue": False})

        with patch("phase_c_ffmpeg.apply_color_grade", _audio_writing_transform):
            result = ctrl.apply_correction("shot_1_0", "color_grade", take_id="take_base")

        assert result["success"] is True, result
        meta = result["take"]["metadata"]
        assert meta.get("audio_embedded") is not True
        assert meta.get("dialogue_audio_in_clip") is not True

    def test_lip_sync_variant_sets_dialogue_audio_in_clip_directly(self, tmp_path):
        """GENERATE action (lip_sync) on a SILENT/unflagged base → variant gets
        dialogue_audio_in_clip=True DIRECTLY (it embeds fresh dialogue; there is no
        base flag to inherit). Mirrors the motion-take path at controller.py:1801."""
        ctrl = _make_correction_ctrl(tmp_path, {"has_dialogue": True})  # base NOT flagged

        def _lipsync(*a, **k):
            out = k.get("output_path")
            _make_clip(out, with_audio=True)
            return out

        with patch("cinema.shots.controller.generate_lip_sync_video", _lipsync), \
             patch("cinema.shots.controller.get_reference_image", return_value=str(tmp_path / "ref.jpg")):
            result = ctrl.apply_correction("shot_1_0", "lip_sync", take_id="take_base")

        assert result["success"] is True, result
        assert result["take"]["metadata"].get("dialogue_audio_in_clip") is True

    def test_lip_sync_variant_records_namespaced_lipsync_cost(self, tmp_path):
        """Postprocess lip_sync records the cascade winner with a LIPSYNC_* key.

        Regression for lipsync-postproc-costkey: the correction path used to pass
        raw cascade engine names such as ``syncSoV3`` to CostTracker, so the table
        lookup missed ``LIPSYNC_SYNCSOV3`` and charged $0.00.
        """
        from cost_tracker import API_COST_USD, CostTracker

        ctrl = _make_correction_ctrl(tmp_path, {"has_dialogue": True})
        tracker = CostTracker(db_path=str(tmp_path / "cost.db"), budget_usd=10.0)
        ctrl._core.cost_tracker = tracker

        def _lipsync(*a, **k):
            out = k.get("output_path")
            _make_clip(out, with_audio=True)
            k["_cascade_out"]["cascade_metadata"] = {"engine": "syncSoV3"}
            return out

        with patch("cinema.shots.controller.generate_lip_sync_video", _lipsync), \
             patch("cinema.shots.controller.get_reference_image", return_value=str(tmp_path / "ref.jpg")):
            result = ctrl.apply_correction("shot_1_0", "lip_sync", take_id="take_base")

        assert result["success"] is True, result
        assert tracker.spent_usd == pytest.approx(API_COST_USD["LIPSYNC_SYNCSOV3"])
        row = tracker.conn.execute(
            "SELECT model, operation, shot_id, video_id FROM cost_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert tuple(row) == ("LIPSYNC_SYNCSOV3", "lipsync", "shot_1_0", "proj_1")


# ===========================================================================
# C1 closure — the assembler honors the flag on a POSTPROCESS variant
# ===========================================================================

class TestAssemblerHonorsFlaggedPostprocessVariant:
    """The linchpin (wf_69ba3ee7 C1): a flagged postprocess variant approved as
    the final take suppresses standalone scene-TTS, exactly like a motion take.
    Mirrors TestAssemblerOverlayInClipDedup but with the approved take living in
    postprocess_variants."""

    def _make_pipeline(self, tmp_path):
        from cinema_pipeline import CinemaPipeline
        from cinema.runstate import RunState

        pipeline = object.__new__(CinemaPipeline)
        pipeline._runstate = RunState()
        pipeline._ensure_scene_audio = MagicMock(return_value=str(tmp_path / "scene_audio.mp3"))
        pipeline._ensure_scene_foley = MagicMock(return_value="")
        pipeline._resolve_take_path = MagicMock(
            side_effect=lambda shot, take_id: self._variant_path(shot, take_id)
        )
        return pipeline

    def _variant_path(self, shot, take_id):
        for take in shot.get("postprocess_variants", []):
            if take["id"] == take_id:
                return take["path"]
        return ""

    def test_flagged_postprocess_variant_suppresses_tts(self, tmp_path):
        pipeline = self._make_pipeline(tmp_path)
        variant_path = str(tmp_path / "variant.mp4")
        open(variant_path, "wb").write(b"fake")
        scene = {
            "id": "scene_pp",
            "characters_present": [],
            "shots": [{
                "id": "shot_pp1",
                "approved_final_take_id": "take_var",
                "motion_takes": [],
                "postprocess_variants": [
                    {"id": "take_var", "kind": "postprocess", "path": variant_path,
                     "metadata": {"has_dialogue": True, "audio_embedded": True}},
                ],
                "characters_in_frame": ["char_1"],
            }],
        }
        packages, missing = pipeline._build_scene_packages({"scenes": [scene], "characters": []})

        assert missing == [], f"unexpected missing: {missing}"
        assert packages[0]["audio"] is None, (
            "a flagged postprocess variant must suppress standalone TTS just like a "
            f"motion take; got audio={packages[0]['audio']!r}"
        )
