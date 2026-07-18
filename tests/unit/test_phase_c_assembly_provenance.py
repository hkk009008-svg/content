"""Provenance threading for image-generation backends (phase_c_assembly).

Keyframe cost attribution requires knowing which backend actually produced an
image — the ComfyUI/PuLID pod vs a FAL fallback (and which FAL model). These
tests pin the `api_name` each branch reports via `ImageGenResult`, so cost_log
can distinguish "ran on the pod" from "fell back to FAL".

Offline: fal_client and the image download are stubbed; no GPU, no pod, no
network, no API calls.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
import urllib.request
from unittest.mock import MagicMock

import pytest

import phase_c_assembly as pca


@pytest.fixture
def stub_fal(monkeypatch):
    """Stub the lazily-imported `fal_client` + the image download so
    `_fal_flux_fallback` runs offline and deterministically succeeds."""
    fake = MagicMock()
    fake.upload_file.return_value = "https://fake/upload"
    fake.subscribe.return_value = {"images": [{"url": "https://fake/image.jpg"}]}
    monkeypatch.setitem(sys.modules, "fal_client", fake)
    # settings is a frozen dataclass — replace the whole object (preserving
    # every other field) rather than setattr-ing a field.
    monkeypatch.setattr(pca, "settings", dataclasses.replace(pca.settings, fal_key="test-key"))

    def _fake_retrieve(url, filename):
        with open(filename, "wb") as fh:
            fh.write(b"jpeg-bytes")

    monkeypatch.setattr(urllib.request, "urlretrieve", _fake_retrieve)
    return fake


class TestFalFallbackProvenance:
    """`_fal_flux_fallback` reports which FAL model produced the image."""

    def test_kontext_branch_reports_flux_kontext(self, stub_fal, tmp_path):
        # A character reference engages Kontext Max Multi (identity-preserving).
        char = tmp_path / "face.jpg"
        char.write_bytes(b"face")
        out = str(tmp_path / "out.jpg")

        res = pca._fal_flux_fallback("a prompt", out, seed=7, character_image=str(char))

        assert isinstance(res, pca.ImageGenResult)
        assert res.path == out
        assert res.api_name == "FLUX_KONTEXT"

    def test_fluxpro_branch_reports_flux_pro(self, stub_fal, tmp_path):
        # No character reference → skip Kontext, run FLUX-Pro (no face-lock).
        out = str(tmp_path / "out.jpg")

        res = pca._fal_flux_fallback("a prompt", out, seed=7, character_image=None)

        assert isinstance(res, pca.ImageGenResult)
        assert res.api_name == "FLUX_PRO"

    def test_schnell_branch_reports_flux_schnell(self, stub_fal, tmp_path):
        # FLUX-Pro fails, FLUX-schnell succeeds → FLUX_SCHNELL.
        stub_fal.subscribe.side_effect = [
            RuntimeError("flux-pro down"),                      # 1st call: FLUX-Pro
            {"images": [{"url": "https://fake/schnell.jpg"}]},  # 2nd call: schnell
        ]
        out = str(tmp_path / "out.jpg")

        res = pca._fal_flux_fallback("a prompt", out, seed=7, character_image=None)

        assert isinstance(res, pca.ImageGenResult)
        assert res.api_name == "FLUX_SCHNELL"

    def test_pollinations_branch_reports_pollinations(self, stub_fal, tmp_path, monkeypatch):
        # FLUX-Pro AND schnell fail; the free Pollinations fallback returns
        # enough bytes → POLLINATIONS.
        stub_fal.subscribe.side_effect = RuntimeError("fal down")

        class _Resp:
            def read(self_inner):
                return b"x" * 6000  # > 5000-byte floor in _fal_flux_fallback

        monkeypatch.setattr(urllib.request, "urlopen", lambda url: _Resp())
        out = str(tmp_path / "out.jpg")

        res = pca._fal_flux_fallback("a prompt", out, seed=7, character_image=None)

        assert isinstance(res, pca.ImageGenResult)
        assert res.api_name == "POLLINATIONS"

    def test_no_fal_key_returns_none(self, monkeypatch, tmp_path):
        # No FAL key → None (failure), so the caller's `if not result` guard
        # still trips and the keyframe is reported as failed.
        monkeypatch.setattr(pca, "settings", dataclasses.replace(pca.settings, fal_key=""))
        res = pca._fal_flux_fallback("p", str(tmp_path / "o.jpg"), character_image=None)
        assert res is None


class TestKontextFailureProvenance:
    """V-1 pin (spec AC6 / Lane-V V-6): Kontext failure with secondaries falls
    back with the ORIGINAL prompt — the multi-char rewrite must never escape the
    Kontext try-block (phase_c_assembly passes `prompt`, not `kontext_prompt`,
    to the FLUX-Pro fallback)."""

    def test_kontext_failure_with_secondaries_falls_back_with_original_prompt(
        self, monkeypatch, tmp_path
    ):
        """When the Kontext subscribe raises and secondary_char_refs were passed,
        the FLUX-Pro fallback receives the ORIGINAL prompt (no @Image in it)
        and result.api_name == FLUX_PRO."""
        fake = MagicMock()
        fake.upload_file.return_value = "https://fake/upload"
        # 1st subscribe call → Kontext endpoint raises; 2nd → FLUX-Pro succeeds
        flux_pro_captured: dict = {}

        def _subscribe(endpoint, **kwargs):
            if "kontext" in endpoint:
                raise RuntimeError("kontext down for test")
            flux_pro_captured["endpoint"] = endpoint
            flux_pro_captured["arguments"] = kwargs.get("arguments", {})
            return {"images": [{"url": "https://fake/fluxpro.jpg"}]}

        fake.subscribe.side_effect = _subscribe
        monkeypatch.setitem(sys.modules, "fal_client", fake)
        monkeypatch.setattr(
            pca, "settings",
            dataclasses.replace(pca.settings, fal_key="test-key"),
        )

        def _fake_retrieve(url, filename):
            with open(filename, "wb") as fh:
                fh.write(b"jpeg-bytes")

        monkeypatch.setattr(urllib.request, "urlretrieve", _fake_retrieve)

        char = tmp_path / "face.jpg"
        char.write_bytes(b"face")
        secondary = tmp_path / "secondary.jpg"
        secondary.write_bytes(b"sec")
        out = str(tmp_path / "out.jpg")
        original_prompt = "A rooftop scene at golden hour"

        result = pca._fal_flux_fallback(
            original_prompt,
            out,
            character_image=str(char),
            identity_anchor="a woman with auburn hair",
            secondary_char_refs=[{
                "char_id": "char_b",
                "reference": str(secondary),
                "multi_angle_refs": [],
                "identity_anchor": "a man with a grey beard",
            }],
        )

        assert result is not None
        assert result.api_name == "FLUX_PRO"
        # V-1 invariant: FLUX-Pro received the ORIGINAL prompt, not the @ImageN rewrite
        captured_prompt = flux_pro_captured["arguments"]["prompt"]
        assert captured_prompt == original_prompt, (
            f"V-1 VIOLATED: FLUX-Pro received rewritten prompt.\n"
            f"Expected: {original_prompt!r}\nGot: {captured_prompt!r}"
        )
        assert "@Image" not in captured_prompt, (
            f"V-1 VIOLATED: @ImageN token escaped the Kontext try-block: {captured_prompt!r}"
        )


class TestImageGenResultShape:
    """`ImageGenResult` is a lightweight, backward-compatible carrier."""

    def test_is_truthy_and_carries_fields(self):
        r = pca.ImageGenResult("/tmp/x.jpg", "COMFYUI_PULID")
        assert r  # truthy on success (the caller's `if not result` guard)
        assert r.path == "/tmp/x.jpg"
        assert r.api_name == "COMFYUI_PULID"


class TestGeminiImagePriorityZero:
    """WS3 PRIORITY-0 gate: Gemini 2.5 Flash Image (Nano Banana) tried before
    the pod when identity_backend != 'pod'. Offline: gemini_image_native and
    phase_c_vision are stubbed via monkeypatch so this runs without any real
    Google/Vertex/network call (COST CONTROL)."""

    @pytest.fixture
    def gemini_enabled_settings(self, monkeypatch):
        """A google_api_key present + identity_backend='gemini_multiref' ctx.

        Real PipelineContext (not a bare dict) — the ComfyUI/workflow_selector
        integration further down generate_ai_broll reads `ctx.global_settings`
        as an ATTRIBUTE (phase_c_assembly.py's
        `get_workflow_params(shot_type, settings=ctx.global_settings if ctx
        else None)`), which only a bare dict's `.get()`-only contract doesn't
        satisfy. Mirrors the real construction at
        cinema/shots/controller.py's `ctx = PipelineContext(global_settings=settings)`.
        """
        monkeypatch.setattr(
            pca, "settings",
            dataclasses.replace(pca.settings, google_api_key="test-google-key", fal_key=""),
        )
        from cinema.context import PipelineContext
        return PipelineContext(global_settings={"identity_backend": "gemini_multiref"})

    @pytest.fixture
    def stub_gemini_client(self, monkeypatch):
        """Stub gemini_image_native.GeminiImageAPI so no real client/network
        is touched; writes a real file to output_filename on success (mirrors
        the real client's file-write side effect) so os.path.exists checks
        downstream stay honest."""
        import sys
        import types as _types

        calls = {}

        class _FakeGeminiImageAPI:
            def __init__(self):
                calls["constructed"] = True

            def generate_image(self, prompt, output_path, **kwargs):
                calls["kwargs"] = kwargs
                calls["output_path"] = output_path
                with open(output_path, "wb") as fh:
                    fh.write(b"gemini-image-bytes")
                return output_path

        fake_module = _types.ModuleType("gemini_image_native")
        fake_module.GeminiImageAPI = _FakeGeminiImageAPI
        fake_module.GEMINI_MULTIREF_MAX_REFS = 8
        monkeypatch.setitem(sys.modules, "gemini_image_native", fake_module)
        return calls

    @pytest.fixture
    def stub_validator(self, monkeypatch):
        """Stub phase_c_vision._get_shared_validator; the `passed` return
        value is set per-test via the closure list `_passed_box`."""
        _passed_box = {"passed": True, "score": 0.85}

        class _FakeValidateResult:
            def __init__(self):
                self.overall_score = _passed_box["score"]
                self.passed = _passed_box["passed"]
                self.threshold_used = 0.65
                self.character_results = {}

        class _FakeValidator:
            def validate_image(self, *args, **kwargs):
                return _FakeValidateResult()

        monkeypatch.setattr("phase_c_vision._get_shared_validator", lambda: _FakeValidator())
        return _passed_box

    def test_gemini_image_success_skips_pod_entirely(
        self, gemini_enabled_settings, stub_gemini_client, stub_validator, tmp_path, monkeypatch
    ):
        """A passing identity check returns GEMINI_IMAGE and never touches the
        pod (comfyui_server_url present but never read/called)."""
        monkeypatch.setattr(
            pca, "settings",
            dataclasses.replace(pca.settings, google_api_key="test-google-key",
                                comfyui_server_url="http://pod-should-not-be-called:8188"),
        )
        char = tmp_path / "face.jpg"
        char.write_bytes(b"face")
        out = str(tmp_path / "out.jpg")

        # RunPodComfyUI must never be constructed on this path.
        def _fail_if_called(*a, **kw):
            raise AssertionError("pod (RunPodComfyUI) must not be called when Gemini succeeds")
        monkeypatch.setattr(pca, "RunPodComfyUI", _fail_if_called)

        res = pca.generate_ai_broll(
            "a prompt", out, character_image=str(char),
            ctx=gemini_enabled_settings,
        )

        assert isinstance(res, pca.ImageGenResult)
        assert res.path == out
        assert res.api_name == "GEMINI_IMAGE"
        assert stub_gemini_client["constructed"] is True
        assert os.path.exists(out)

    def test_gemini_identity_fail_falls_through_to_pod_and_logs_comparison(
        self, gemini_enabled_settings, stub_gemini_client, stub_validator, tmp_path, monkeypatch
    ):
        """A failing identity check does NOT return GEMINI_IMAGE — it falls
        through to the pod (PRIORITY-1, mocked queue_prompt reached) and
        appends one logs/gemini_image_arc_comparison.jsonl line."""
        from tests.unit.test_phase_c_assembly_portrait import _stub_comfyui_path, _minimal_pulid_workflow

        stub_validator["passed"] = False
        stub_validator["score"] = 0.31

        # Reuse the established pod-dispatch stub (pulid.json + queue_prompt
        # capture) so the pod path is reached exactly like the portrait suite
        # exercises it — no real GPU/pod/network. Runs AFTER
        # gemini_enabled_settings, so its dataclasses.replace(pca.settings, ...)
        # base already carries google_api_key="test-google-key" forward.
        captured_workflow = _stub_comfyui_path(monkeypatch, tmp_path)
        # _stub_comfyui_path's minimal workflow has no node "93" (the PuLID
        # LoadImage node) because its own tests never pass character_image.
        # This test DOES (the Gemini gate requires it), which walks the
        # `workflow["93"]["inputs"]["image"] = ...` line (phase_c_assembly.py)
        # — extend the fixture workflow with that one extra node.
        extended_workflow = _minimal_pulid_workflow()
        extended_workflow["93"] = {"inputs": {"image": ""}, "class_type": "LoadImage"}
        (tmp_path / "pulid.json").write_text(json.dumps(extended_workflow))

        monkeypatch.chdir(tmp_path)  # logs/gemini_image_arc_comparison.jsonl is CWD-relative

        char = tmp_path / "face.jpg"
        char.write_bytes(b"face")
        out = str(tmp_path / "out.jpg")

        res = pca.generate_ai_broll(
            "a prompt", out, character_image=str(char),
            ctx=gemini_enabled_settings,
        )

        # The pod path was reached: queue_prompt captured a real workflow dict.
        assert captured_workflow, "identity-score-fail must fall through to the pod, not return early"
        assert res.api_name != "GEMINI_IMAGE"

        comparison_log = tmp_path / "logs" / "gemini_image_arc_comparison.jsonl"
        assert comparison_log.exists()
        line = json.loads(comparison_log.read_text().strip().splitlines()[-1])
        assert line["gemini_score"] == pytest.approx(0.31)
        assert line["character_image"] == str(char)

    def test_gemini_exception_falls_through_gracefully(
        self, gemini_enabled_settings, tmp_path, monkeypatch
    ):
        """An exception anywhere in the PRIORITY-0 block (e.g. GeminiImageAPI
        construction raising) must not propagate — it falls through to the
        existing FAL/pod cascade exactly like a missing pod does."""
        import sys
        import types as _types

        class _RaisingGeminiImageAPI:
            def __init__(self):
                raise RuntimeError("simulated client construction failure")

        fake_module = _types.ModuleType("gemini_image_native")
        fake_module.GeminiImageAPI = _RaisingGeminiImageAPI
        monkeypatch.setitem(sys.modules, "gemini_image_native", fake_module)

        monkeypatch.setattr(
            pca, "settings",
            dataclasses.replace(pca.settings, google_api_key="test-google-key",
                                comfyui_server_url="", fal_key="test-fal-key"),
        )
        fake_fal = MagicMock()
        fake_fal.upload_file.return_value = "https://fake/upload"
        fake_fal.subscribe.return_value = {"images": [{"url": "https://fake/image.jpg"}]}
        monkeypatch.setitem(sys.modules, "fal_client", fake_fal)

        import urllib.request

        def _fake_retrieve(url, filename):
            with open(filename, "wb") as fh:
                fh.write(b"jpeg-bytes")
        monkeypatch.setattr(urllib.request, "urlretrieve", _fake_retrieve)

        char = tmp_path / "face.jpg"
        char.write_bytes(b"face")
        out = str(tmp_path / "out.jpg")

        res = pca.generate_ai_broll(
            "a prompt", out, character_image=str(char),
            ctx=gemini_enabled_settings,
        )

        # Falls through to FLUX Kontext (FAL) — no exception escapes.
        assert isinstance(res, pca.ImageGenResult)
        assert res.api_name == "FLUX_KONTEXT"

    def test_identity_backend_pod_skips_gemini_entirely(self, tmp_path, monkeypatch, stub_fal):
        """Explicit identity_backend='pod' (a project's WS3 opt-out from the
        now-default gemini_multiref primary — FIX C) must never engage the
        PRIORITY-0 block — the production pod/FAL cascade behavior stays
        byte-for-byte unchanged for opted-out projects. (Key-ABSENT no
        longer means 'pod' — it now means gemini_multiref; see
        test_no_ctx_now_defaults_to_gemini_primary below.)"""
        import sys
        gemini_constructed = {"value": False}

        class _FakeGeminiImageAPI:
            def __init__(self):
                gemini_constructed["value"] = True

        import types as _types
        fake_module = _types.ModuleType("gemini_image_native")
        fake_module.GeminiImageAPI = _FakeGeminiImageAPI
        monkeypatch.setitem(sys.modules, "gemini_image_native", fake_module)

        # Force the ComfyUI branch off (comfyui_server_url="") so the call
        # deterministically lands in the already-stubbed FAL path — this repo
        # has a real pod URL in .env, and generate_ai_broll (unlike
        # _fal_flux_fallback called directly elsewhere in this file) would
        # otherwise attempt a real pod HTTP call (COST CONTROL).
        monkeypatch.setattr(pca, "settings", dataclasses.replace(pca.settings, comfyui_server_url=""))

        char = tmp_path / "face.jpg"
        char.write_bytes(b"face")
        out = str(tmp_path / "out.jpg")

        from cinema.context import PipelineContext
        res = pca.generate_ai_broll(
            "a prompt", out, character_image=str(char),
            ctx=PipelineContext(global_settings={"identity_backend": "pod"}),
        )

        assert isinstance(res, pca.ImageGenResult)
        assert gemini_constructed["value"] is False

    def test_no_ctx_now_defaults_to_gemini_primary(
        self, stub_gemini_client, stub_validator, stub_fal, tmp_path, monkeypatch
    ):
        """FIX C (WS3 default-on, user-confirmed): ctx=None hits
        get_project_setting's None-safe branch (cinema/context.py:177-178),
        which returns the passed-in default with no project to read from —
        and that default is now 'gemini_multiref', not 'pod'. There is no
        special-casing between "no ctx" and "ctx present but
        identity_backend unset": both share the same
        get_project_setting(..., default=...) plumbing, so this INVERTS the
        prior test_no_ctx_skips_gemini_entirely pin by design (mirrors the
        WS2 dialogue-routing test update in test_f1b_dialogue_lipsync.py —
        a legitimate expected-value change, not a masking one).

        Stubs the Gemini client/validator (COST CONTROL: this repo's .env
        carries a real GOOGLE_API_KEY, so an unstubbed call here would hit
        the network now that the gate is open by default) and forces a
        deterministic fake key so the assertion never depends on local
        .env contents.
        """
        monkeypatch.setattr(
            pca, "settings",
            dataclasses.replace(pca.settings, google_api_key="test-google-key",
                                comfyui_server_url=""),
        )

        char = tmp_path / "face.jpg"
        char.write_bytes(b"face")
        out = str(tmp_path / "out.jpg")

        res = pca.generate_ai_broll("a prompt", out, character_image=str(char), ctx=None)

        assert isinstance(res, pca.ImageGenResult)
        assert res.api_name == "GEMINI_IMAGE"
        assert stub_gemini_client["constructed"] is True

    # -----------------------------------------------------------------
    # WS3 money-loss close-out: Gemini bills ($0.03) on generation,
    # independent of whether the identity check later rejects it. A
    # bill-but-reject must not vanish when the pod/FAL cascade wins —
    # mirror of cinema/shots/controller.py::_record_billed_rejects on the
    # video side (money-gate finding 2026-07-11: offline-probe proven,
    # invisible to would_exceed/is_over_budget before this fix).
    # -----------------------------------------------------------------

    def test_gemini_billed_reject_threads_onto_fallback_winner(
        self, gemini_enabled_settings, stub_gemini_client, stub_validator, stub_fal, tmp_path, monkeypatch
    ):
        """A Gemini bill-but-identity-reject must be threaded onto whichever
        backend the pod/FAL cascade ultimately returns as `billed_rejects`,
        so the caller can record the $0.03 Google already billed even
        though Gemini lost the identity check."""
        stub_validator["passed"] = False
        stub_validator["score"] = 0.31

        # COST CONTROL: this repo has a real pod URL in .env — force the
        # ComfyUI branch off (mirrors test_identity_backend_pod_skips_gemini_
        # entirely / test_no_ctx_now_defaults_to_gemini_primary above) so the
        # call deterministically lands in the already-stubbed FAL path
        # instead of risking a real pod HTTP call.
        monkeypatch.setattr(
            pca, "settings",
            dataclasses.replace(pca.settings, google_api_key="test-google-key",
                                comfyui_server_url=""),
        )
        monkeypatch.chdir(tmp_path)  # gemini_image_arc_comparison.jsonl is CWD-relative

        char = tmp_path / "face.jpg"
        char.write_bytes(b"face")
        out = str(tmp_path / "out.jpg")

        res = pca.generate_ai_broll(
            "a prompt", out, character_image=str(char),
            ctx=gemini_enabled_settings,
        )

        assert isinstance(res, pca.ImageGenResult)
        assert res.api_name == "FLUX_KONTEXT", (
            f"expected the FAL Kontext fallback to win; got {res.api_name!r}"
        )
        assert res.billed_rejects == ("GEMINI_IMAGE",), (
            f"Gemini billed a frame that then lost identity — it must "
            f"survive as billed_rejects on the winning result; got "
            f"{res.billed_rejects!r}"
        )

    def test_gemini_success_never_populates_billed_rejects(
        self, gemini_enabled_settings, stub_gemini_client, stub_validator, tmp_path, monkeypatch
    ):
        """A passing Gemini identity check IS the winner, not a reject —
        billed_rejects must stay empty on the success return path (L213
        returns immediately, before the reject-tracking append)."""
        monkeypatch.setattr(
            pca, "settings",
            dataclasses.replace(pca.settings, google_api_key="test-google-key",
                                comfyui_server_url="http://pod-should-not-be-called:8188"),
        )
        char = tmp_path / "face.jpg"
        char.write_bytes(b"face")
        out = str(tmp_path / "out.jpg")

        res = pca.generate_ai_broll(
            "a prompt", out, character_image=str(char),
            ctx=gemini_enabled_settings,
        )

        assert res.api_name == "GEMINI_IMAGE"
        assert res.billed_rejects == ()

    def test_billed_reject_recorded_alongside_winner_via_keyframe_take(
        self, stub_gemini_client, stub_validator, stub_fal, tmp_path, monkeypatch
    ):
        """End-to-end regression driven through the REAL controller seam
        (cinema/shots/controller.py::generate_keyframe_take), not just
        generate_ai_broll directly. Gemini bills a real image ($0.03) that
        then FAILS identity, falls through to the FAL Kontext fallback which
        wins. cost_tracker must record BOTH the FAL winner
        (operation="keyframe_generation") AND the Gemini bill-but-reject
        (operation="image_generation_rejected") — before this fix the
        Gemini spend was invisible to would_exceed/is_over_budget."""
        from cinema.shots.controller import ShotController

        stub_validator["passed"] = False
        stub_validator["score"] = 0.31

        # COST CONTROL: force the ComfyUI branch off (real pod URL in .env)
        # so the call deterministically lands in the already-stubbed FAL
        # path, same rationale as the generate_ai_broll-level tests above.
        monkeypatch.setattr(
            pca, "settings",
            dataclasses.replace(pca.settings, google_api_key="test-google-key",
                                comfyui_server_url=""),
        )
        monkeypatch.chdir(tmp_path)  # gemini_image_arc_comparison.jsonl is CWD-relative

        char = tmp_path / "face.jpg"
        char.write_bytes(b"face")
        img_path = str(tmp_path / "keyframe.jpg")

        shot = {
            "id": "shot_1_0",
            "plan_status": "approved",
            "characters_in_frame": [],
            "camera": "medium_shot",
            "target_api": "AUTO",
        }
        scene = {"id": "scene_1", "title": "T", "action": "A", "location_id": None, "shots": [shot]}
        project = {
            "id": "proj_1",
            "scenes": [scene],
            "characters": [],
            "objects": [],
            "locations": [],
            "global_settings": {"identity_backend": "gemini_multiref"},
        }

        host = MagicMock()
        host._refresh_project_snapshot.return_value = project
        lifecycle = MagicMock()
        runstate = MagicMock()
        runstate.shot_results = {}
        core = MagicMock()
        core.project = project
        core.project_dir = str(tmp_path)
        core.continuity.enhance_shot_prompt.return_value = {
            "prompt": "base prompt",
            "continuity_config": {"primary_reference": str(char)},
        }
        core.cost_tracker = MagicMock()

        ctrl = ShotController(core=core, lifecycle=lifecycle, host=host, runstate=runstate)
        ctrl._take_output_path = MagicMock(return_value=img_path)
        ctrl._resolve_previous_approved_keyframe = MagicMock(return_value="")
        ctrl._mutate_shot = MagicMock()

        result = ctrl.generate_keyframe_take("scene_1", "shot_1_0", positive_prompt="a test prompt")

        assert result.get("success") is True, f"expected success, got {result}"

        calls = ctrl.cost_tracker.record_api_call.call_args_list
        by_op = {c.kwargs.get("operation"): c for c in calls}
        assert "keyframe_generation" in by_op and "image_generation_rejected" in by_op, (
            f"expected winner + Gemini-reject records; got {calls}"
        )
        assert by_op["keyframe_generation"].args[0] == "FLUX_KONTEXT", (
            f"expected the FAL Kontext fallback to win; got "
            f"{by_op['keyframe_generation'].args[0]!r}"
        )
        assert by_op["image_generation_rejected"].args[0] == "GEMINI_IMAGE", (
            f"expected the billed-but-rejected Gemini call recorded; got {calls}"
        )
