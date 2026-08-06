"""Provenance threading for image-generation backends (phase_c_assembly).

Keyframe cost attribution requires knowing which backend actually produced an
image. These tests pin the `api_name` each active branch reports via
`ImageGenResult`.

Offline: fal_client and the image download are stubbed; no GPU and no
network, no API calls.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
import types
import urllib.parse
import urllib.request
from unittest.mock import MagicMock

import pytest

import phase_c_assembly as pca


def test_generated_jpeg_download_is_bounded_mime_checked_and_validated(
    tmp_path, monkeypatch
):
    captured = {}

    def _safe_download(url, destination, **kwargs):
        captured.update(url=url, destination=destination, **kwargs)
        return destination

    monkeypatch.setattr(pca, "safe_download", _safe_download)
    destination = str(tmp_path / "out.jpg")

    assert pca._download_generated_jpeg("https://cdn.example/out.jpg", destination) == destination
    assert captured["max_bytes"] == 64 * 1024 * 1024
    assert captured["allowed_content_types"] == ("image/jpeg",)
    assert callable(captured["content_validator"])


def test_local_flux2_uses_only_four_references_in_stable_precedence(
    tmp_path, monkeypatch
):
    from cinema.context import PipelineContext
    from performance.flux2_klein import Flux2KleinJobResult

    references = []
    for index in range(7):
        path = tmp_path / f"reference-{index}.jpg"
        path.write_bytes(f"reference-{index}".encode("ascii"))
        references.append(str(path))
    output = str(tmp_path / "result.jpg")
    captured = {}

    monkeypatch.setattr(pca, "has_paid_attempt_authority", lambda _tracker: True)
    monkeypatch.setattr(
        "performance.worker_readiness.require_flux2_worker_ready",
        lambda _settings: {"state": "ready"},
    )

    def _run_local(**kwargs):
        captured.update(kwargs)
        return Flux2KleinJobResult(
            prompt_id="prompt-1",
            output={"filename": "result.jpg"},
            history={},
            published_path=output,
        )

    monkeypatch.setattr(
        "performance.flux2_klein.run_flux2_klein_image_job",
        _run_local,
    )
    result = pca.generate_ai_broll(
        "preserve the approved characters",
        output,
        character_image=references[0],
        multi_angle_refs=[references[1], references[0]],
        secondary_char_refs=[
            {
                "reference": references[2],
                "multi_angle_refs": [references[3]],
            },
            {
                "reference": references[4],
                "multi_angle_refs": [references[5]],
            },
        ],
        continuity_reference=references[6],
        ctx=PipelineContext(
            global_settings={"identity_backend": "local_flux2_klein"}
        ),
        cost_tracker=object(),
    )

    assert result == pca.ImageGenResult(output, "FLUX2_KLEIN_LOCAL")
    assert captured["reference_image_paths"] == references[:4]


def test_local_controller_metadata_and_forwarded_refs_share_one_allocation(
    tmp_path, monkeypatch
):
    """The controller must not promise characters absent from the graph."""

    import cinema.shots.controller as controller_module
    from cinema.shots.controller import ShotController
    from cost_tracker import CostTracker

    references = {}
    for name in (
        "primary.jpg",
        "primary-angle.jpg",
        "secondary.jpg",
        "secondary-angle.jpg",
        "third.jpg",
        "continuity.jpg",
    ):
        path = tmp_path / name
        path.write_bytes(name.encode("ascii"))
        references[name] = str(path)

    shot = {
        "id": "shot_1_0",
        "plan_status": "approved",
        "characters_in_frame": ["char_a", "char_b", "char_c"],
        "primary_character": "char_a",
        "camera": "medium_shot",
        "target_api": "AUTO",
    }
    scene = {
        "id": "scene_1",
        "title": "T",
        "action": "A",
        "location_id": None,
        "shots": [shot],
    }
    project = {
        "id": "proj_1",
        "scenes": [scene],
        "characters": [],
        "objects": [],
        "locations": [],
        "global_settings": {"identity_backend": "local_flux2_klein"},
    }
    continuity_config = {
        "primary_reference": references["primary.jpg"],
        "multi_angle_refs": [
            references["primary.jpg"],  # canonical-path duplicate
            references["primary-angle.jpg"],
        ],
        "secondary_chars": [
            {
                "char_id": "char_b",
                "reference": references["secondary.jpg"],
                "multi_angle_refs": [references["secondary-angle.jpg"]],
            },
            {
                "char_id": "char_c",
                "reference": references["third.jpg"],
            },
        ],
        "continuity_reference": references["continuity.jpg"],
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
        "continuity_config": continuity_config,
    }
    core.cost_tracker = CostTracker(
        db_path=str(tmp_path / "local-allocation.db"),
        budget_usd=2.0,
    )
    ctrl = ShotController(core=core, lifecycle=lifecycle, host=host, runstate=runstate)
    ctrl._take_output_path = MagicMock(return_value=str(tmp_path / "keyframe.jpg"))
    ctrl._resolve_previous_approved_keyframe = MagicMock(return_value="")
    ctrl._mutate_shot = lambda shot_id, mutator: mutator(scene, shot).value
    captured = {}

    def _capture_generation(*args, **kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(controller_module, "generate_ai_broll", _capture_generation)
    try:
        result = ctrl.generate_keyframe_take("scene_1", "shot_1_0")
    finally:
        core.cost_tracker.close()

    assert result == {"success": False, "error": "Image generation failed"}
    assert captured["character_image"] == references["primary.jpg"]
    assert captured["multi_angle_refs"] == [references["primary-angle.jpg"]]
    assert captured["secondary_char_refs"] == [
        {
            "char_id": "char_b",
            "reference": references["secondary.jpg"],
            "identity_anchor": "",
            "fidelity": "reference",
            "multi_angle_refs": [references["secondary-angle.jpg"]],
        }
    ]
    assert captured["continuity_reference"] is None
    assert captured["preallocated_flux2_reference_paths"] == (
        references["primary.jpg"],
        references["primary-angle.jpg"],
        references["secondary.jpg"],
        references["secondary-angle.jpg"],
    )
    metadata = captured["artifact_metadata"]["identity_strategy"]
    assert metadata["flux2_reference_paths"] == [
        references["primary.jpg"],
        references["primary-angle.jpg"],
        references["secondary.jpg"],
        references["secondary-angle.jpg"],
    ]
    assert [item["char_id"] for item in metadata["conditioned_chars"]] == [
        "char_a",
        "char_b",
    ]
    assert metadata["unconditioned_chars"] == ["char_c"]


def test_preallocated_local_reference_contract_blocks_all_drift_before_worker(
    tmp_path, monkeypatch
):
    """Exact controller allocations are validated, never silently rewritten."""

    from cinema.context import PipelineContext

    primary = tmp_path / "primary.jpg"
    primary.write_bytes(b"primary")
    secondary = tmp_path / "secondary.jpg"
    secondary.write_bytes(b"secondary")
    symlink = tmp_path / "primary-link.jpg"
    symlink.symlink_to(primary)
    missing = tmp_path / "missing.jpg"

    readiness = MagicMock(return_value={"state": "ready"})
    run_local = MagicMock()
    monkeypatch.setattr(
        "performance.worker_readiness.require_flux2_worker_ready",
        readiness,
    )
    monkeypatch.setattr(
        "performance.flux2_klein.run_flux2_klein_image_job",
        run_local,
    )
    context = PipelineContext(
        global_settings={"identity_backend": "local_flux2_klein"}
    )
    inputs = {
        "character_image": str(primary),
        "secondary_char_refs": [{"char_id": "char_b", "reference": str(secondary)}],
    }
    invalid_contracts = [
        (str(missing),),
        (str(symlink),),
        (str(primary), str(primary)),
        (f"{tmp_path}/./primary.jpg", str(secondary)),
        (str(primary),),  # Valid path, but not the complete decomposed allocation.
    ]

    for index, contract in enumerate(invalid_contracts):
        recovery = {}
        result = pca.generate_ai_broll(
            "preserve the approved characters",
            str(tmp_path / f"blocked-{index}.jpg"),
            ctx=context,
            cost_tracker=object(),
            preallocated_flux2_reference_paths=contract,
            _recovery_out=recovery,
            **inputs,
        )

        assert result is None
        assert recovery["code"] in {
            "local_reference_contract_invalid",
            "local_reference_contract_mismatch",
        }

    readiness.assert_not_called()
    run_local.assert_not_called()


def test_controller_deleted_preallocated_secondary_blocks_before_worker(
    tmp_path, monkeypatch
):
    """A reference disappearing after strategy resolution cannot shrink the run."""

    import cinema.shots.controller as controller_module
    from cinema.shots.controller import ShotController
    from cost_tracker import CostTracker

    primary = tmp_path / "primary.jpg"
    primary.write_bytes(b"primary")
    secondary = tmp_path / "secondary.jpg"
    secondary.write_bytes(b"secondary")
    shot = {
        "id": "shot_1_0",
        "plan_status": "approved",
        "characters_in_frame": ["char_a", "char_b"],
        "primary_character": "char_a",
        "camera": "medium_shot",
        "target_api": "AUTO",
    }
    scene = {
        "id": "scene_1",
        "title": "T",
        "action": "A",
        "location_id": None,
        "shots": [shot],
    }
    project = {
        "id": "proj_1",
        "scenes": [scene],
        "characters": [],
        "objects": [],
        "locations": [],
        "global_settings": {"identity_backend": "local_flux2_klein"},
    }
    continuity_config = {
        "primary_reference": str(primary),
        "secondary_chars": [
            {"char_id": "char_b", "reference": str(secondary)}
        ],
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
        "continuity_config": continuity_config,
    }
    core.cost_tracker = CostTracker(
        db_path=str(tmp_path / "deleted-reference.db"),
        budget_usd=2.0,
    )
    ctrl = ShotController(core=core, lifecycle=lifecycle, host=host, runstate=runstate)
    ctrl._take_output_path = MagicMock(return_value=str(tmp_path / "keyframe.jpg"))
    ctrl._resolve_previous_approved_keyframe = MagicMock(return_value="")
    ctrl._mutate_shot = lambda shot_id, mutator: mutator(scene, shot).value

    real_resolver = controller_module._resolve_identity_strategy

    def _resolve_then_delete(*args, **kwargs):
        strategy = real_resolver(*args, **kwargs)
        secondary.unlink()
        return strategy

    readiness = MagicMock(return_value={"state": "ready"})
    run_local = MagicMock()
    monkeypatch.setattr(
        controller_module,
        "_resolve_identity_strategy",
        _resolve_then_delete,
    )
    monkeypatch.setattr(
        "performance.worker_readiness.require_flux2_worker_ready",
        readiness,
    )
    monkeypatch.setattr(
        "performance.flux2_klein.run_flux2_klein_image_job",
        run_local,
    )

    try:
        result = ctrl.generate_keyframe_take("scene_1", "shot_1_0")
    finally:
        core.cost_tracker.close()

    assert result["success"] is False
    assert result["deferred_job"]["provider_status"] == (
        "local_reference_contract_invalid"
    )
    assert not (tmp_path / "keyframe.jpg").exists()
    assert shot.get("keyframe_takes", []) == []
    readiness.assert_not_called()
    run_local.assert_not_called()


@pytest.fixture
def stub_fal(monkeypatch):
    """Stub the lazily-imported `fal_client` + the image download so
    `_fal_flux_fallback` runs offline and deterministically succeeds."""
    fake = MagicMock()
    fake.upload_file.return_value = "https://fake/upload"
    fake.subscribe.return_value = {"images": [{"url": "https://fake/image.jpg"}]}
    fake.submit.return_value = types.SimpleNamespace(request_id="fal-image-request")
    fake.status.return_value = {"status": "COMPLETED"}
    fake.result.return_value = {"images": [{"url": "https://fake/image.jpg"}]}
    monkeypatch.setitem(sys.modules, "fal_client", fake)
    # settings is a frozen dataclass — replace the whole object (preserving
    # every other field) rather than setattr-ing a field.
    monkeypatch.setattr(pca, "settings", dataclasses.replace(pca.settings, fal_key="test-key"))

    def _fake_download(url, filename):
        with open(filename, "wb") as fh:
            fh.write(b"jpeg-bytes")
        return filename

    monkeypatch.setattr(pca, "_download_generated_jpeg", _fake_download)
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

        out = str(tmp_path / "out.jpg")

        res = pca._fal_flux_fallback("a prompt", out, seed=7, character_image=None)

        assert isinstance(res, pca.ImageGenResult)
        assert res.api_name == "POLLINATIONS"

    @pytest.mark.parametrize(
        ("seed", "expected_seed"),
        [(None, "42"), (0, "0")],
    )
    def test_pollinations_defaults_only_missing_seed(
        self, stub_fal, tmp_path, monkeypatch, seed, expected_seed
    ):
        stub_fal.subscribe.side_effect = RuntimeError("fal down")
        captured_urls = []

        def _fake_download(url, filename):
            captured_urls.append(url)
            with open(filename, "wb") as fh:
                fh.write(b"jpeg-bytes")
            return filename

        monkeypatch.setattr(pca, "_download_generated_jpeg", _fake_download)

        res = pca._fal_flux_fallback(
            "a prompt",
            str(tmp_path / "out.jpg"),
            seed=seed,
            character_image=None,
        )

        assert isinstance(res, pca.ImageGenResult)
        assert res.api_name == "POLLINATIONS"
        assert captured_urls
        query = urllib.parse.parse_qs(
            urllib.parse.urlparse(captured_urls[0]).query
        )
        assert query["seed"] == [expected_seed]

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

        def _fake_download(url, filename):
            with open(filename, "wb") as fh:
                fh.write(b"jpeg-bytes")
            return filename

        monkeypatch.setattr(pca, "_download_generated_jpeg", _fake_download)

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
        r = pca.ImageGenResult("/tmp/x.jpg", "FLUX2_KLEIN_LOCAL")
        assert r  # truthy on success (the caller's `if not result` guard)
        assert r.path == "/tmp/x.jpg"
        assert r.api_name == "FLUX2_KLEIN_LOCAL"


class TestGeminiImagePriorityZero:
    """Gemini image is tried before local and supported cloud fallbacks.
    Offline: gemini_image_native and
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
                calls["count"] = calls.get("count", 0) + 1
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

    def test_gemini_image_success_skips_remaining_providers(
        self, gemini_enabled_settings, stub_gemini_client, stub_validator, tmp_path, monkeypatch
    ):
        """A passing identity check returns GEMINI_IMAGE immediately."""
        monkeypatch.setattr(
            pca, "settings",
            dataclasses.replace(pca.settings, google_api_key="test-google-key",
                                comfyui_server_url="http://worker-should-not-be-called:8188"),
        )
        char = tmp_path / "face.jpg"
        char.write_bytes(b"face")
        out = str(tmp_path / "out.jpg")

        res = pca.generate_ai_broll(
            "a prompt", out, character_image=str(char),
            ctx=gemini_enabled_settings,
        )

        assert isinstance(res, pca.ImageGenResult)
        assert res.path == out
        assert res.api_name == "GEMINI_IMAGE"
        assert stub_gemini_client["constructed"] is True
        assert os.path.exists(out)

    def test_gemini_identity_fail_falls_through_and_traces_artifact(
        self, gemini_enabled_settings, stub_gemini_client, stub_validator, stub_fal, tmp_path, monkeypatch, caplog
    ):
        """A failing identity check does NOT return GEMINI_IMAGE — it falls
        through to a supported provider and
        emits one central trace tied to the retained candidate."""
        stub_validator["passed"] = False
        stub_validator["score"] = 0.31
        monkeypatch.setattr(
            pca,
            "settings",
            dataclasses.replace(
                pca.settings,
                google_api_key="test-google-key",
                fal_key="test-key",
            ),
        )

        monkeypatch.chdir(tmp_path)
        caplog.set_level("INFO", logger="phase_c_assembly")

        char = tmp_path / "face.jpg"
        char.write_bytes(b"face")
        out = str(tmp_path / "out.jpg")
        retained = []

        def _retain(*args, **kwargs):
            take = args[3]
            with open(take["path"], "rb") as handle:
                assert handle.read() == b"gemini-image-bytes"
            retained.append((args, kwargs))
            return {"artifact_id": "av-rejected", "sha256": "a" * 64}

        monkeypatch.setattr(
            "cinema.artifact_indexing.record_take_version",
            _retain,
        )
        project = {
            "id": "project-artifacts",
            "scenes": [{"id": "scene-1", "shots": [{"id": "shot-1"}]}],
        }

        res = pca.generate_ai_broll(
            "a prompt", out, character_image=str(char),
            ctx=gemini_enabled_settings,
            video_id="project-artifacts",
            shot_id="shot-1",
            take_id="take-1",
            project_snapshot=project,
            project_root=tmp_path,
        )

        assert res.api_name == "FLUX_KONTEXT"
        assert stub_fal.subscribe.called
        assert len(retained) == 1
        rejected_take = retained[0][0][3]
        assert rejected_take["id"] == "take-1"
        assert rejected_take["status"] == "rejected"
        assert rejected_take["metadata"]["rejection_stage"] == "identity_validation"
        assert rejected_take["metadata"]["identity_score"] == pytest.approx(0.31)

        trace = next(
            record
            for record in caplog.records
            if record.getMessage() == "Gemini identity candidate rejected"
        )
        assert trace.identity_score == pytest.approx(0.31)
        assert trace.artifact_id == "av-rejected"

    def test_gemini_reject_retention_failure_blocks_overwriting_fallback(
        self,
        gemini_enabled_settings,
        stub_gemini_client,
        stub_validator,
        stub_fal,
        tmp_path,
        monkeypatch,
    ):
        """The only paid frame remains recoverable when immutable copy fails."""
        stub_validator["passed"] = False
        monkeypatch.setattr(
            "cinema.artifact_indexing.record_take_version",
            MagicMock(side_effect=OSError("artifact store unavailable")),
        )
        char = tmp_path / "face.jpg"
        char.write_bytes(b"face")
        out = str(tmp_path / "out.jpg")
        recovery = {}
        project = {
            "id": "project-artifacts",
            "scenes": [{"id": "scene-1", "shots": [{"id": "shot-1"}]}],
        }

        result = pca.generate_ai_broll(
            "a prompt",
            out,
            character_image=str(char),
            ctx=gemini_enabled_settings,
            _recovery_out=recovery,
            video_id="project-artifacts",
            shot_id="shot-1",
            take_id="take-1",
            project_snapshot=project,
            project_root=tmp_path,
        )

        assert result is None
        stub_fal.subscribe.assert_not_called()
        with open(out, "rb") as handle:
            assert handle.read() == b"gemini-image-bytes"
        assert recovery["provider_status"] == "artifact_retention_failed"
        assert "Fallback is blocked" in recovery["reason"]

    def test_completed_gemini_candidate_resumes_from_immutable_bytes(
        self,
        gemini_enabled_settings,
        stub_gemini_client,
        stub_validator,
        tmp_path,
        monkeypatch,
    ):
        from cost_tracker import CostTracker

        monkeypatch.setattr(pca, "validate_image_artifact", lambda *_a, **_k: True)
        char = tmp_path / "face.jpg"
        char.write_bytes(b"face")
        out = str(tmp_path / "out.jpg")
        project = {
            "id": "project-artifacts",
            "scenes": [{"id": "scene-1", "shots": [{"id": "shot-1"}]}],
        }
        call_kwargs = {
            "character_image": str(char),
            "ctx": gemini_enabled_settings,
            "video_id": "project-artifacts",
            "shot_id": "shot-1",
            "take_id": "take-1",
            "project_snapshot": project,
            "project_root": tmp_path,
        }

        with CostTracker(db_path=str(tmp_path / "cost.db")) as tracker:
            first = pca.generate_ai_broll(
                "a prompt", out, cost_tracker=tracker, **call_kwargs
            )
            assert first.api_name == "GEMINI_IMAGE"
            assert stub_gemini_client["count"] == 1
            with open(out, "wb") as handle:
                handle.write(b"stale-mutable-bytes")

            resumed = pca.generate_ai_broll(
                "a prompt", out, cost_tracker=tracker, **call_kwargs
            )

            assert resumed.api_name == "GEMINI_IMAGE"
            assert stub_gemini_client["count"] == 1
            with open(out, "rb") as handle:
                assert handle.read() == b"gemini-image-bytes"
            assert tracker.get_paid_attempts_snapshot("project-artifacts")[
                "attempts"
            ][0]["state"] == "succeeded"

    def test_gemini_exception_falls_through_gracefully(
        self, gemini_enabled_settings, tmp_path, monkeypatch
    ):
        """An exception anywhere in the PRIORITY-0 block (e.g. GeminiImageAPI
        construction raising) must not propagate — it falls through to the
        next eligible supported route."""
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

        def _fake_download(url, filename):
            with open(filename, "wb") as fh:
                fh.write(b"jpeg-bytes")
            return filename
        monkeypatch.setattr(pca, "_download_generated_jpeg", _fake_download)

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

    def test_no_ctx_now_defaults_to_gemini_primary(
        self, stub_gemini_client, stub_validator, stub_fal, tmp_path, monkeypatch
    ):
        """FIX C (WS3 default-on, user-confirmed): ctx=None hits
        get_project_setting's None-safe branch (cinema/context.py:177-178),
        which returns the passed-in default with no project to read from —
        and that default is 'gemini_multiref'. There is no
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
    # bill-but-reject must not vanish when a later supported route wins —
    # mirror of cinema/shots/controller.py::_record_billed_rejects on the
    # video side (money-gate finding 2026-07-11: offline-probe proven,
    # invisible to would_exceed/is_over_budget before this fix).
    # -----------------------------------------------------------------

    def test_gemini_billed_reject_threads_onto_fallback_winner(
        self, gemini_enabled_settings, stub_gemini_client, stub_validator, stub_fal, tmp_path, monkeypatch
    ):
        """A Gemini bill-but-identity-reject must be threaded onto whichever
        backend the remaining route chain ultimately returns as `billed_rejects`,
        so the caller can record the $0.03 Google already billed even
        though Gemini lost the identity check."""
        stub_validator["passed"] = False
        stub_validator["score"] = 0.31

        # COST CONTROL: force the local worker branch off so the
        # call deterministically lands in the already-stubbed FAL path
        # instead of risking a real worker HTTP call.
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

    def test_gemini_billed_reject_survives_validator_exception(
        self, gemini_enabled_settings, stub_gemini_client, stub_fal, tmp_path, monkeypatch
    ):
        """A local validator crash happens after Gemini has generated and
        billed the frame, so fallback attribution must retain that spend."""
        validator = MagicMock()
        validator.validate_image.side_effect = RuntimeError("validator crashed")
        monkeypatch.setattr(
            "phase_c_vision._get_shared_validator",
            lambda: validator,
        )
        monkeypatch.setattr(
            pca, "settings",
            dataclasses.replace(pca.settings, google_api_key="test-google-key",
                                comfyui_server_url=""),
        )

        char = tmp_path / "face.jpg"
        char.write_bytes(b"face")
        out = str(tmp_path / "out.jpg")

        res = pca.generate_ai_broll(
            "a prompt", out, character_image=str(char),
            ctx=gemini_enabled_settings,
        )

        assert res.api_name == "FLUX_KONTEXT"
        assert res.billed_rejects == ("GEMINI_IMAGE",)

    def test_gemini_billed_reject_survives_total_fallback_failure(
        self, gemini_enabled_settings, stub_gemini_client, stub_fal, tmp_path, monkeypatch
    ):
        """No winning result must not erase spend incurred before all
        fallback providers fail."""
        validator = MagicMock()
        validator.validate_image.side_effect = RuntimeError("validator crashed")
        monkeypatch.setattr(
            "phase_c_vision._get_shared_validator",
            lambda: validator,
        )
        stub_fal.subscribe.side_effect = RuntimeError("fal unavailable")
        monkeypatch.setattr(pca, "_download_generated_jpeg", lambda *args, **kwargs: None)
        monkeypatch.setattr(
            pca, "settings",
            dataclasses.replace(pca.settings, google_api_key="test-google-key",
                                comfyui_server_url=""),
        )

        char = tmp_path / "face.jpg"
        char.write_bytes(b"face")
        recovery = {}
        res = pca.generate_ai_broll(
            "a prompt", str(tmp_path / "out.jpg"),
            character_image=str(char),
            ctx=gemini_enabled_settings,
            _recovery_out=recovery,
        )

        assert res is None
        assert recovery == {"_billed_rejects": ("GEMINI_IMAGE",)}

    def test_gemini_success_never_populates_billed_rejects(
        self, gemini_enabled_settings, stub_gemini_client, stub_validator, tmp_path, monkeypatch
    ):
        """A passing Gemini identity check IS the winner, not a reject —
        billed_rejects must stay empty on the success return path (L213
        returns immediately, before the reject-tracking append)."""
        monkeypatch.setattr(
            pca, "settings",
            dataclasses.replace(pca.settings, google_api_key="test-google-key",
                                comfyui_server_url="http://worker-should-not-be-called:8188"),
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

        # COST CONTROL: force the local worker branch off
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
        from cost_tracker import CostTracker
        core.cost_tracker = CostTracker(
            db_path=str(tmp_path / "paid-image.db"),
            budget_usd=2.0,
        )

        ctrl = ShotController(core=core, lifecycle=lifecycle, host=host, runstate=runstate)
        ctrl._take_output_path = MagicMock(return_value=img_path)
        ctrl._resolve_previous_approved_keyframe = MagicMock(return_value="")
        ctrl._mutate_shot = lambda shot_id, mutator: mutator(scene, shot).value

        try:
            result = ctrl.generate_keyframe_take("scene_1", "shot_1_0", positive_prompt="a test prompt")

            assert result.get("success") is True, f"expected success, got {result}"
            attempts = ctrl.cost_tracker.get_paid_attempts_snapshot("proj_1")["attempts"]
            succeeded = {row["engine"] for row in attempts if row["state"] == "succeeded"}
            assert succeeded == {"GEMINI_IMAGE", "FLUX_KONTEXT"}
            assert ctrl.cost_tracker.get_video_cost("proj_1")["total_usd"] == pytest.approx(
                0.067 + 0.08
            )
        finally:
            core.cost_tracker.close()
