from __future__ import annotations

from copy import deepcopy
from dataclasses import fields, replace
from datetime import date
from types import MappingProxyType, SimpleNamespace

import pytest

from config.settings import Settings
from domain.provider_catalog import (
    CATALOG,
    CatalogEntry,
    Lifecycle,
    Maturity,
    Modality,
    ProductSupport,
    Provider,
    RequirementKind,
    RuntimeAvailabilityState,
    RuntimeSnapshot,
    SourceCheck,
    SourceKind,
    effective_policy,
    get_entry,
    project_legacy_registry,
    runtime_availability,
)
from domain.scene_decomposer import API_REGISTRY


PRE_SUNSET = date(2026, 9, 23)
SUNSET = date(2026, 9, 24)


def test_catalog_exactly_covers_legacy_registry_plus_fal_svd_mutation_pin() -> None:
    expected = set(API_REGISTRY) | {"FAL_SVD"}

    assert isinstance(CATALOG, MappingProxyType)
    assert len(API_REGISTRY) == 40
    assert len(CATALOG) == 41
    assert set(CATALOG) == expected
    assert "FAL_SVD" in CATALOG
    assert CATALOG["FAL_SVD"].legacy_visible is False


def test_catalog_mapping_and_entries_are_immutable() -> None:
    with pytest.raises(TypeError):
        CATALOG["NEW"] = CATALOG["AUTO"]  # type: ignore[index]
    with pytest.raises((AttributeError, TypeError)):
        CATALOG["AUTO"].label = "changed"  # type: ignore[misc]


def test_legacy_projection_is_exact_nonmutating_copy() -> None:
    source_before = deepcopy(API_REGISTRY)
    canonical_auto = CATALOG["AUTO"]

    projected = project_legacy_registry(API_REGISTRY, on_date=PRE_SUNSET)

    assert set(projected) == set(API_REGISTRY)
    assert len(projected) == 40
    assert "FAL_SVD" not in projected
    assert API_REGISTRY == source_before
    assert CATALOG["AUTO"] is canonical_auto

    projected["AUTO"]["label"] = "mutated projection"
    projected["AUTO"]["best_for"].append("projection_only")  # type: ignore[union-attr]
    assert API_REGISTRY == source_before
    assert CATALOG["AUTO"].label == "Auto (Smart Routing)"

    API_REGISTRY["AUTO"]["best_for"].append("source_only")
    try:
        assert "source_only" not in projected["AUTO"]["best_for"]
    finally:
        API_REGISTRY["AUTO"]["best_for"].remove("source_only")


def test_legacy_projection_overlays_typed_effective_truth() -> None:
    projected = project_legacy_registry(API_REGISTRY, on_date=SUNSET)
    sora = projected["SORA_NATIVE"]

    assert sora["maturity"] == Maturity.STABLE.value
    assert sora["lifecycle"] == Lifecycle.RETIRED.value
    assert sora["status"] == "retired"
    assert sora["product_support"] == ProductSupport.LIMITED.value
    assert sora["provider"] == Provider.OPENAI.value
    assert sora["selectable"] is False
    assert sora["dispatchable"] is False
    assert sora["spendable"] is False
    assert sora["sunset_on"] == "2026-09-24"


def test_legacy_projection_status_is_fail_closed_and_date_effective() -> None:
    before = project_legacy_registry(API_REGISTRY, on_date=PRE_SUNSET)
    at_sunset = project_legacy_registry(API_REGISTRY, on_date=SUNSET)

    assert before["SORA_NATIVE"]["status"] == "live"
    assert at_sunset["SORA_NATIVE"]["status"] == "retired"
    assert before["SORA_2"]["status"] == "retired"
    assert before["GEMINI_OMNI"]["status"] == "disabled"
    assert before["RUNWAY_ACT_ONE"]["status"] == "retired"
    assert before["ELEVENLABS_DIALOGUE"]["status"] == "beta"
    for key in ("SORA_2", "GEMINI_OMNI", "RUNWAY_ACT_ONE"):
        assert before[key]["status"] != "live"


def test_sora_fal_is_retired_and_cannot_be_enabled_mutation_pin() -> None:
    sora = get_entry("SORA_2")

    assert sora.lifecycle is Lifecycle.RETIRED
    assert sora.product_support is ProductSupport.UNSUPPORTED
    assert (sora.selectable, sora.dispatchable, sora.spendable) == (
        False,
        False,
        False,
    )
    assert runtime_availability(
        "SORA_2",
        RuntimeSnapshot(
            credentials={"fal_key"},
            modules={"fal_client"},
        ),
        on_date=PRE_SUNSET,
    ).state is RuntimeAvailabilityState.NOT_DISPATCHABLE

    with pytest.raises(ValueError, match="retired or unsupported"):
        replace(
            sora,
            selectable=True,
            dispatchable=True,
            spendable=True,
            runtime_options=get_entry("KLING_3_0").runtime_options,
        )


def test_sora_native_sunset_uses_greater_than_or_equal_boundary_mutation_pin() -> None:
    before = effective_policy("SORA_NATIVE", on_date=PRE_SUNSET)
    at_sunset = effective_policy("SORA_NATIVE", on_date=SUNSET)

    assert before.lifecycle is Lifecycle.DEPRECATED
    assert before.selectable is False
    assert before.dispatchable is True
    assert before.spendable is True
    assert at_sunset.lifecycle is Lifecycle.RETIRED
    assert at_sunset.selectable is False
    assert at_sunset.dispatchable is False
    assert at_sunset.spendable is False


def test_selectable_entries_are_eligible_video_targets() -> None:
    allowed_support = {ProductSupport.SUPPORTED, ProductSupport.LIMITED}

    for key, entry in CATALOG.items():
        if not entry.selectable:
            continue
        policy = effective_policy(key, on_date=PRE_SUNSET)
        assert entry.modality is Modality.VIDEO, key
        assert entry.product_support in allowed_support, key
        if key == "AUTO":
            assert policy.dispatchable is False
        else:
            assert policy.dispatchable is True, key


def test_spendable_entries_are_external_and_dispatchable() -> None:
    for key in CATALOG:
        policy = effective_policy(key, on_date=PRE_SUNSET)
        if policy.spendable:
            assert policy.dispatchable is True, key
            assert CATALOG[key].provider is not Provider.INTERNAL, key


def test_denied_support_and_retired_entries_fail_closed() -> None:
    denied_support = {
        ProductSupport.UNSUPPORTED,
        ProductSupport.KNOWN_BROKEN,
        ProductSupport.DISCONNECTED,
        ProductSupport.NOT_IMPLEMENTED,
    }

    for key, entry in CATALOG.items():
        if entry.lifecycle is Lifecycle.RETIRED or entry.product_support in denied_support:
            assert entry.selectable is False, key
            assert entry.dispatchable is False, key
            assert entry.spendable is False, key
            assert entry.runtime_options == (), key


def test_non_video_entries_are_never_shot_selectable() -> None:
    for key, entry in CATALOG.items():
        if entry.modality is not Modality.VIDEO:
            assert entry.selectable is False, key


def test_parameter_names_and_shapes_are_coherent() -> None:
    for key, entry in CATALOG.items():
        names = [constraint.name for constraint in entry.parameters]
        assert len(names) == len(set(names)), key
        for constraint in entry.parameters:
            assert constraint.name
            assert len(constraint.allowed_values) == len(
                set(constraint.allowed_values)
            )
            if constraint.minimum is not None and constraint.maximum is not None:
                assert constraint.minimum <= constraint.maximum
            if constraint.max_items is not None:
                assert constraint.max_items >= 0
            assert (
                constraint.allowed_values
                or constraint.minimum is not None
                or constraint.maximum is not None
                or constraint.max_items is not None
                or constraint.note
            ), f"{key}.{constraint.name} has no bounded fact"


def test_known_parameter_contracts_are_pinned() -> None:
    def constraints(key: str) -> dict[str, object]:
        return {item.name: item for item in CATALOG[key].parameters}

    sora = constraints("SORA_NATIVE")
    assert sora["duration"].allowed_values == (4, 8, 12, 16, 20)
    assert sora["resolution"].allowed_values == ("720p",)
    assert sora["aspect_ratio"].allowed_values == ("16:9", "9:16")
    assert sora["input_references"].max_items == 1

    veo = constraints("VEO_NATIVE")
    assert veo["duration"].allowed_values == (4, 6, 8)
    assert veo["resolution"].allowed_values == ("720p", "1080p")
    assert veo["additional_reference_images"].max_items == 0
    assert veo["driving_video"].allowed_values == (False,)
    assert "Vertex" in veo["native_audio"].note

    runway = constraints("RUNWAY_GEN4")
    assert runway["model"].allowed_values == ("gen4_turbo",)
    assert runway["input_images"].max_items == 1
    assert runway["duration"].allowed_values == (10,)

    ltx = constraints("LTX")
    assert ltx["duration"].allowed_values == (6, 8, 10)
    assert ltx["resolution"].allowed_values == ("1080p", "1440p", "2160p")
    assert ltx["audio"].allowed_values == (False,)

    kling = constraints("KLING_3_0")
    assert kling["duration"].allowed_values == (5,)
    assert kling["element_images"].max_items == 4

    seedance = constraints("SEEDANCE")
    assert (seedance["duration"].minimum, seedance["duration"].maximum) == (4, 15)
    assert seedance["reference_images"].max_items == 9
    assert seedance["audio"].allowed_values == (False,)

    svd = constraints("FAL_SVD")
    assert svd["motion_bucket_id"].allowed_values == (127,)
    assert svd["cond_aug"].allowed_values == (0.02,)
    assert "portrait" in svd["aspect_ratio"].note.lower()

    foley = constraints("STABLE_AUDIO_FOLEY")
    assert foley["duration"].maximum == 190
    assert (foley["steps"].minimum, foley["steps"].maximum) == (30, 100)
    assert "cfg" not in foley
    assert (foley["cfg_scale"].minimum, foley["cfg_scale"].maximum) == (1, 10)


def test_fal_availability_requires_credential_and_module() -> None:
    available = runtime_availability(
        "KLING_3_0",
        RuntimeSnapshot(credentials={"fal_key"}, modules={"fal_client"}),
        on_date=PRE_SUNSET,
    )
    missing_credential = runtime_availability(
        "KLING_3_0",
        RuntimeSnapshot(modules={"fal_client"}),
        on_date=PRE_SUNSET,
    )

    assert available.state is RuntimeAvailabilityState.AVAILABLE
    assert available.effective_dispatchable is True
    assert available.effective_spendable is True
    assert missing_credential.state is RuntimeAvailabilityState.UNAVAILABLE
    assert missing_credential.effective_dispatchable is False
    assert {
        requirement.name for requirement in missing_credential.missing_requirements
    } == {"fal_key"}


def test_kling_native_availability_requires_both_credentials_and_jwt() -> None:
    complete = RuntimeSnapshot(
        credentials={"kling_access_key", "kling_secret_key"},
        modules={"jwt"},
    )
    missing_secret = RuntimeSnapshot(
        credentials={"kling_access_key"},
        modules={"jwt"},
    )

    assert runtime_availability(
        "KLING_NATIVE", complete, on_date=PRE_SUNSET
    ).state is RuntimeAvailabilityState.AVAILABLE
    result = runtime_availability(
        "KLING_NATIVE", missing_secret, on_date=PRE_SUNSET
    )
    assert result.state is RuntimeAvailabilityState.UNAVAILABLE
    assert [requirement.name for requirement in result.missing_requirements] == [
        "kling_secret_key"
    ]


def test_ltx_only_trusts_fal_alternative_until_adapter_repair() -> None:
    with pytest.raises(ValueError, match="unknown symbolic names") as exc_info:
        RuntimeSnapshot(credentials={"ltx_api_key"})
    assert "ltx_api_key" not in repr(exc_info.value)

    no_trustworthy_option = RuntimeSnapshot()
    trustworthy_fal = RuntimeSnapshot(
        credentials={"fal_key"},
        modules={"fal_client"},
    )

    native_result = runtime_availability(
        "LTX", no_trustworthy_option, on_date=PRE_SUNSET
    )
    fal_result = runtime_availability("LTX", trustworthy_fal, on_date=PRE_SUNSET)

    assert native_result.state is RuntimeAvailabilityState.UNAVAILABLE
    assert {
        requirement.name for requirement in native_result.missing_requirements
    } == {"fal_key", "fal_client"}
    assert fal_result.state is RuntimeAvailabilityState.AVAILABLE


def test_veo_runtime_alternatives_are_or_of_and_groups() -> None:
    vertex = RuntimeSnapshot(
        credentials={"google_cloud_project"},
        modules={"google.genai"},
        services={"google_adc"},
    )
    api_key = RuntimeSnapshot(
        credentials={"google_api_key"},
        modules={"google.genai"},
    )
    project_without_adc = RuntimeSnapshot(
        credentials={"google_cloud_project"},
        modules={"google.genai"},
    )

    assert runtime_availability(
        "VEO_NATIVE", vertex, on_date=PRE_SUNSET
    ).available
    assert runtime_availability(
        "VEO_NATIVE", api_key, on_date=PRE_SUNSET
    ).available
    result = runtime_availability(
        "VEO_NATIVE", project_without_adc, on_date=PRE_SUNSET
    )
    assert result.state is RuntimeAvailabilityState.UNAVAILABLE
    assert {requirement.name for requirement in result.missing_options[0]} == {
        "google_adc"
    }
    assert {requirement.name for requirement in result.missing_options[1]} == {
        "google_api_key"
    }


def test_non_dispatchable_entries_have_no_options_and_short_circuit() -> None:
    full_snapshot = RuntimeSnapshot(
        credentials={
            "fal_key",
            "google_api_key",
            "openai_api_key",
        },
        modules={"fal_client", "google.genai", "openai"},
        services={"google_adc", "comfyui_readiness"},
    )

    for key in ("GEMINI_OMNI", "SORA_2", "OPENAI_AUDIO", "RUNWAY_ACT_ONE"):
        assert CATALOG[key].runtime_options == ()
        result = runtime_availability(key, full_snapshot, on_date=PRE_SUNSET)
        assert result.state is RuntimeAvailabilityState.NOT_DISPATCHABLE
        assert result.missing_options == ()


def test_runtime_credential_names_are_real_settings_fields() -> None:
    settings_fields = {field.name for field in fields(Settings)}
    requirement_names = {
        requirement.name
        for entry in CATALOG.values()
        for option in entry.runtime_options
        for requirement in option
        if requirement.kind is RequirementKind.CREDENTIAL
    }

    assert requirement_names
    assert requirement_names <= settings_fields


def test_runtime_snapshot_from_settings_never_retains_or_renders_secrets() -> None:
    sentinel = "TOP_SECRET_SENTINEL_DO_NOT_LEAK"
    fake_settings = SimpleNamespace(fal_key=sentinel)

    snapshot = RuntimeSnapshot.from_settings(
        fake_settings,
        module_probe=lambda name: name == "fal_client",
    )
    result = runtime_availability(
        "KLING_3_0",
        snapshot,
        on_date=PRE_SUNSET,
    )

    assert snapshot.credentials == frozenset({"fal_key"})
    assert snapshot.modules == frozenset({"fal_client"})
    assert result.state is RuntimeAvailabilityState.AVAILABLE
    assert sentinel not in repr(snapshot)
    assert sentinel not in str(snapshot)
    assert sentinel not in repr(result)
    assert sentinel not in str(result)


@pytest.mark.parametrize("field_name", ("credentials", "modules", "services"))
def test_runtime_snapshot_rejects_unknown_names_without_rendering_them(
    field_name: str,
) -> None:
    sentinel = "TOP_SECRET_DIRECT_CONSTRUCTION_SENTINEL"

    with pytest.raises(ValueError, match="unknown symbolic names") as exc_info:
        RuntimeSnapshot(**{field_name: {sentinel}})

    assert sentinel not in repr(exc_info.value)
    assert sentinel not in str(exc_info.value)


def test_runtime_snapshot_rejects_requirement_names_in_the_wrong_kind() -> None:
    with pytest.raises(ValueError, match="credentials"):
        RuntimeSnapshot(credentials={"fal_client"})
    with pytest.raises(ValueError, match="modules"):
        RuntimeSnapshot(modules={"fal_key"})
    with pytest.raises(ValueError, match="services"):
        RuntimeSnapshot(services={"openai"})


def test_sources_are_single_checked_records_with_unverified_urls_fail_closed() -> None:
    for key, entry in CATALOG.items():
        assert isinstance(entry.source, SourceCheck), key
        assert entry.source.checked_at == date(2026, 7, 30), key
        if entry.source.kind is SourceKind.UNVERIFIED:
            assert entry.source.url is None, key


@pytest.mark.parametrize(
    ("kind", "url"),
    (
        (SourceKind.PRIMARY_CONTRACT, None),
        (SourceKind.PRIMARY_CONTRACT, ""),
        (SourceKind.PRIMARY_CONTRACT, "provider.example/api"),
        (SourceKind.PRIMARY_CONTRACT, "ftp://provider.example/api"),
        (SourceKind.PRIMARY_CONTRACT, "http://"),
        (SourceKind.PRIMARY_CONTRACT, "https:///missing-host"),
        (SourceKind.LIFECYCLE_NOTICE, None),
        (SourceKind.LIFECYCLE_NOTICE, "file:///tmp/notice"),
    ),
)
def test_verified_sources_require_nonempty_http_urls(
    kind: SourceKind,
    url: str | None,
) -> None:
    with pytest.raises(ValueError, match=r"HTTP\(S\) URL"):
        SourceCheck(checked_at=date(2026, 7, 30), url=url, kind=kind)


def test_unverified_sources_reject_claimed_urls() -> None:
    with pytest.raises(ValueError, match="must not claim"):
        SourceCheck(
            checked_at=date(2026, 7, 30),
            url="https://provider.example/unverified",
            kind=SourceKind.UNVERIFIED,
        )
    assert SourceCheck(
        checked_at=date(2026, 7, 30),
        url=None,
        kind=SourceKind.REPO_EVIDENCE,
    ).url is None


def test_catalog_entry_field_boundary_is_exactly_typed() -> None:
    assert {field.name for field in fields(CatalogEntry)} == {
        "key",
        "label",
        "modality",
        "maturity",
        "lifecycle",
        "product_support",
        "provider",
        "selectable",
        "dispatchable",
        "spendable",
        "native_audio",
        "parameters",
        "runtime_options",
        "source",
        "sunset_on",
        "legacy_visible",
    }
