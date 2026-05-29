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
