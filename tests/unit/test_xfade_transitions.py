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
