import json
import os
import shutil
import subprocess
import tempfile
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

    def test_audio_flags_none_defaults_all_audio(self):
        fg, vlab, alab = pcf._build_xfade_filtergraph([4.0, 5.0], 0.5, "dissolve")
        assert "acrossfade" in fg
        assert "anullsrc" not in fg
        assert alab == "a1"

    def test_all_audio_uses_raw_acrossfade(self):
        fg, vlab, alab = pcf._build_xfade_filtergraph(
            [4.0, 5.0], 0.5, "dissolve", audio_flags=[True, True])
        assert "[0:a][1:a]acrossfade" in fg
        assert "anullsrc" not in fg
        assert "aformat" not in fg
        assert alab == "a1"

    def test_mixed_audio_pads_silent_leg(self):
        # input 0 has audio, input 1 silent (durations 4.0, 5.0)
        fg, vlab, alab = pcf._build_xfade_filtergraph(
            [4.0, 5.0], 0.5, "dissolve", audio_flags=[True, False])
        assert "[0:a]aresample=48000" in fg                          # real leg normalized
        assert "anullsrc=r=48000:cl=stereo,atrim=0:5" in fg          # silent leg, input-1 dur
        assert "aformat=sample_fmts=fltp:channel_layouts=stereo" in fg
        assert "acrossfade" in fg
        assert alab == "a1"

    def test_mixed_audio_silent_first(self):
        fg, vlab, alab = pcf._build_xfade_filtergraph(
            [4.0, 5.0], 0.5, "dissolve", audio_flags=[False, True])
        assert "anullsrc=r=48000:cl=stereo,atrim=0:4" in fg          # leg 0 silent, dur 4
        assert "[1:a]aresample=48000" in fg                          # leg 1 real
        assert alab == "a1"

    def test_mixed_audio_silent_middle(self):
        # 3 clips, middle silent ([T, F, T]) — the chained-acrossfade mixed shape
        fg, vlab, alab = pcf._build_xfade_filtergraph(
            [4.0, 5.0, 6.0], 0.5, "dissolve", audio_flags=[True, False, True])
        assert "[0:a]aresample=48000" in fg                          # leg 0 real, normalized
        assert "anullsrc=r=48000:cl=stereo,atrim=0:5" in fg          # leg 1 silent, mid dur 5
        assert "[2:a]aresample=48000" in fg                          # leg 2 real, normalized
        assert "aformat=sample_fmts=fltp:channel_layouts=stereo" in fg
        assert fg.count("acrossfade") == 2                           # chained over 3 legs
        assert alab == "a2"


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
    def test_no_audio_video_only(self):
        fg, vlab, alab = pcf._build_xfade_filtergraph(
            [4.0, 5.0], 0.5, "dissolve", audio_flags=[False, False])
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

    def test_mixed_audio_cmd_maps_audio(self):
        # Mixed presence (input 0 audio, input 1 silent) -> audio preserved via
        # anullsrc-pad, so the command maps an audio stream + re-encodes (Lane V #25 M1).
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            m = mock.MagicMock()
            m.returncode = 0
            return m

        with mock.patch.object(pcf, "_probe_duration", side_effect=[4.0, 5.0]), \
             mock.patch.object(pcf, "_has_audio_stream", side_effect=[True, False]), \
             mock.patch("subprocess.run", side_effect=fake_run):
            pcf.xfade_concat(["/s0.mp4", "/s1.mp4"], "/out.mp4")
        joined = " ".join(captured["cmd"])
        assert "-map [a1]" in joined
        assert "aac" in joined
        assert "anullsrc" in joined


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "ffmpeg/ffprobe not available")
class TestXfadeConcatRealFFmpeg(unittest.TestCase):
    def _make_clip(self, path, dur, with_audio):
        cmd = ["ffmpeg", "-y", "-f", "lavfi",
               "-i", f"testsrc=size=320x240:rate=30:duration={dur}"]
        if with_audio:
            cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}"]
        cmd += ["-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast"]
        if with_audio:
            cmd += ["-c:a", "aac", "-shortest"]
        cmd.append(path)
        subprocess.run(cmd, check=True, capture_output=True)

    def _has_audio(self, path):
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=codec_type", "-of", "csv=p=0", path],
            capture_output=True, text=True, check=True).stdout
        return "audio" in out

    def _audio_duration(self, path):
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=duration", "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, check=True).stdout.strip()
        return float(out)

    def test_mixed_audio_runs_and_outputs_audio(self):
        with tempfile.TemporaryDirectory() as d:
            a = os.path.join(d, "a.mp4")
            b = os.path.join(d, "b.mp4")
            out = os.path.join(d, "out.mp4")
            self._make_clip(a, 3, with_audio=True)
            self._make_clip(b, 3, with_audio=False)
            pcf.xfade_concat([a, b], out, duration=0.5)
            assert os.path.exists(out)
            assert self._has_audio(out)  # M1 fix: audio preserved, not dropped
            # Duration ~ sum - overlap = 3 + 3 - 0.5 = 5.5s; guards atrim under-trim.
            self.assertAlmostEqual(self._audio_duration(out), 5.5, delta=0.3)
