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
