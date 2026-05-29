import json
import os
import subprocess
import unittest
from unittest import mock

import phase_c_ffmpeg as pcf


class TestProbeDuration(unittest.TestCase):
    def test_parses_duration_from_ffprobe_json(self):
        payload = json.dumps({"format": {"duration": "4.25"}})

        def fake_run(cmd, **kwargs):
            self.assertIn("ffprobe", cmd[0])
            self.assertIn("format=duration", cmd)
            m = mock.MagicMock()
            m.stdout = payload
            m.returncode = 0
            return m

        with mock.patch("subprocess.run", side_effect=fake_run):
            assert pcf._probe_duration("/fake/clip.mp4") == 4.25


class TestBuildXfadeFiltergraph(unittest.TestCase):
    def test_two_scenes(self):
        fg, vlab, alab = pcf._build_xfade_filtergraph([4.0, 5.0], 0.5, "dissolve")
        assert vlab == "v1"
        assert alab == "a1"
        assert fg == (
            "[0:v][1:v]xfade=transition=dissolve:duration=0.5:offset=3.5[v1];"
            "[0:a][1:a]acrossfade=d=0.5[a1]"
        )

    def test_three_scenes_chains_offsets(self):
        fg, vlab, alab = pcf._build_xfade_filtergraph([4.0, 5.0, 6.0], 0.5, "dissolve")
        assert vlab == "v2"
        assert alab == "a2"
        assert fg == (
            "[0:v][1:v]xfade=transition=dissolve:duration=0.5:offset=3.5[v1];"
            "[v1][2:v]xfade=transition=dissolve:duration=0.5:offset=8[v2];"
            "[0:a][1:a]acrossfade=d=0.5[a1];"
            "[a1][2:a]acrossfade=d=0.5[a2]"
        )


class TestXfadeConcat(unittest.TestCase):
    def _run(self, scene_videos, durations, duration=0.5):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            m = mock.MagicMock()
            m.returncode = 0
            return m

        with mock.patch.object(pcf, "_probe_duration", side_effect=durations), \
             mock.patch.object(pcf, "_has_audio_stream", return_value=True), \
             mock.patch("subprocess.run", side_effect=fake_run):
            out = pcf.xfade_concat(scene_videos, "/out/final.mp4", duration=duration)
        return out, captured["cmd"]

    def test_builds_ffmpeg_cmd_with_inputs_filter_and_maps(self):
        out, cmd = self._run(["/s0.mp4", "/s1.mp4"], durations=[4.0, 5.0])
        assert out == "/out/final.mp4"
        i_positions = [k for k, a in enumerate(cmd) if a == "-i"]
        assert [cmd[k + 1] for k in i_positions] == ["/s0.mp4", "/s1.mp4"]
        joined = " ".join(cmd)
        assert "-filter_complex" in cmd
        assert "xfade=transition=dissolve:duration=0.5:offset=3.5" in joined
        assert "acrossfade=d=0.5" in joined
        assert "-map [v1]" in joined
        assert "-map [a1]" in joined

    def test_clamps_transition_to_shortest_scene(self):
        # Shortest scene is 0.5s -> t_eff = min(0.5, 0.4*0.5) = 0.2
        out, cmd = self._run(["/s0.mp4", "/s1.mp4"], durations=[0.5, 5.0], duration=0.5)
        joined = " ".join(cmd)
        assert "duration=0.2" in joined
        assert "acrossfade=d=0.2" in joined


class TestHasAudioStream(unittest.TestCase):
    def test_true_when_audio_stream_present(self):
        payload = json.dumps({"streams": [{"index": 1}]})

        def fake_run(cmd, **kwargs):
            self.assertIn("-select_streams", cmd)
            m = mock.MagicMock()
            m.stdout = payload
            m.returncode = 0
            return m

        with mock.patch("subprocess.run", side_effect=fake_run):
            assert pcf._has_audio_stream("/clip.mp4") is True

    def test_false_when_no_audio_stream(self):
        payload = json.dumps({"streams": []})

        def fake_run(cmd, **kwargs):
            m = mock.MagicMock()
            m.stdout = payload
            m.returncode = 0
            return m

        with mock.patch("subprocess.run", side_effect=fake_run):
            assert pcf._has_audio_stream("/clip.mp4") is False


class TestBuildXfadeFiltergraphVideoOnly(unittest.TestCase):
    def test_include_audio_false_omits_acrossfade(self):
        fg, vlab, alab = pcf._build_xfade_filtergraph(
            [4.0, 5.0], 0.5, "dissolve", include_audio=False)
        assert "xfade=transition=dissolve" in fg
        assert "acrossfade" not in fg
        assert vlab == "v1"
        assert alab is None


class TestXfadeConcatAudioPresence(unittest.TestCase):
    def _run(self, durations, has_audio):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            m = mock.MagicMock()
            m.returncode = 0
            return m

        with mock.patch.object(pcf, "_probe_duration", side_effect=durations), \
             mock.patch.object(pcf, "_has_audio_stream", return_value=has_audio), \
             mock.patch("subprocess.run", side_effect=fake_run):
            pcf.xfade_concat(["/s0.mp4", "/s1.mp4"], "/out.mp4")
        return " ".join(captured["cmd"])

    def test_silent_inputs_produce_video_only_command(self):
        # F1 regression (Lane V #24): silent (no-audio) inputs must NOT emit
        # acrossfade or an audio -map. Real ffmpeg errors when [0:a] is referenced
        # on silent clips (default Kling-Native path is silent-video), which
        # silently fell back to hard cuts — a dead toggle.
        joined = self._run([4.0, 5.0], has_audio=False)
        assert "xfade=transition=dissolve" in joined, "video xfade must remain"
        assert "acrossfade" not in joined, "F1: no acrossfade for silent inputs"
        assert "-map [a" not in joined, "F1: no audio map for silent inputs"

    def test_audio_inputs_keep_acrossfade(self):
        # Embedded-audio engines (Omnihuman/Veo): inputs have audio -> preserve the
        # acrossfade + audio map so the downstream amix still finds [0:a] dialogue.
        joined = self._run([4.0, 5.0], has_audio=True)
        assert "acrossfade=d=" in joined, "audio present -> keep acrossfade"
        assert "-map [a1]" in joined
