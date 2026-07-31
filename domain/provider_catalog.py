"""Typed, immutable provider policy facts.

This module is deliberately additive.  The legacy ``API_REGISTRY`` remains the
current compatibility surface until its consumers migrate in later tasks.
Static provider policy, date-effective policy, and observed runtime readiness
are kept separate here so a missing credential cannot rewrite lifecycle truth.

Runtime snapshots contain symbolic names only.  They never retain credential
values, imported module objects, or service payloads.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import StrEnum
from importlib.util import find_spec
from math import isfinite
from numbers import Real
from types import MappingProxyType
from typing import Callable, Mapping
from urllib.parse import urlparse


class Modality(StrEnum):
    VIDEO = "video"
    LIPSYNC = "lipsync"
    TTS = "tts"
    IMAGE = "image"
    MUSIC = "music"
    FOLEY = "foley"
    UPSCALE = "upscale"


class Maturity(StrEnum):
    STABLE = "stable"
    PREVIEW = "preview"
    BETA = "beta"
    UNKNOWN = "unknown"


class Lifecycle(StrEnum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


class ProductSupport(StrEnum):
    SUPPORTED = "supported"
    LIMITED = "limited"
    NOT_IMPLEMENTED = "not_implemented"
    DISCONNECTED = "disconnected"
    KNOWN_BROKEN = "known_broken"
    UNSUPPORTED = "unsupported"


class Provider(StrEnum):
    INTERNAL = "internal"
    KLING = "kling"
    OPENAI = "openai"
    GOOGLE = "google"
    GOOGLE_GEMINI_API = "google_gemini_api"
    RUNWAY = "runway"
    LTX_FAL = "ltx_fal"
    FAL = "fal"
    ELEVENLABS = "elevenlabs"
    CARTESIA = "cartesia"
    LOCAL_OPEN_WEIGHTS = "local_open_weights"
    RUNPOD_COMFYUI = "runpod_comfyui"
    SUNO_API_ORG = "sunoapi_org_proxy"
    STABILITY = "stability"
    ADOBE = "adobe"
    TOPAZ = "topaz"
    VIGGLE = "viggle"


class RequirementKind(StrEnum):
    CREDENTIAL = "credential"
    MODULE = "module"
    SERVICE = "service"


class SourceKind(StrEnum):
    PRIMARY_CONTRACT = "primary_contract"
    LIFECYCLE_NOTICE = "lifecycle_notice"
    REPO_EVIDENCE = "repo_evidence"
    UNVERIFIED = "unverified"


class RuntimeAvailabilityState(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    NOT_DISPATCHABLE = "not_dispatchable"


def _is_finite_real(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, Real):
        return False
    if isinstance(value, int):
        return True
    try:
        return isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


@dataclass(frozen=True)
class ParameterConstraint:
    name: str
    allowed_values: tuple[str | int | float | bool, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    max_items: int | None = None
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed_values", tuple(self.allowed_values))
        if not self.name:
            raise ValueError("parameter constraint name must not be empty")
        for bound_name, bound in (
            ("minimum", self.minimum),
            ("maximum", self.maximum),
        ):
            if bound is not None and not _is_finite_real(bound):
                raise ValueError(
                    f"{self.name}: {bound_name} must be a finite real number"
                )
        for value in self.allowed_values:
            if isinstance(value, bool) or isinstance(value, str):
                continue
            if not _is_finite_real(value):
                raise ValueError(
                    f"{self.name}: numeric allowed_values must be finite"
                )
        if len(set(self.allowed_values)) != len(self.allowed_values):
            raise ValueError(f"{self.name}: allowed_values must be unique")
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise ValueError(f"{self.name}: minimum must not exceed maximum")
        if self.max_items is not None:
            if isinstance(self.max_items, bool) or not isinstance(
                self.max_items,
                int,
            ):
                raise ValueError(
                    f"{self.name}: max_items must be a non-negative integer"
                )
            if self.max_items < 0:
                raise ValueError(
                    f"{self.name}: max_items must be a non-negative integer"
                )
        if self.allowed_values and (
            self.minimum is not None or self.maximum is not None
        ):
            for value in self.allowed_values:
                if isinstance(value, bool) or not isinstance(value, Real):
                    raise ValueError(
                        f"{self.name}: numeric bounds require numeric allowed_values"
                    )
                if self.minimum is not None and value < self.minimum:
                    raise ValueError(
                        f"{self.name}: allowed value is below minimum"
                    )
                if self.maximum is not None and value > self.maximum:
                    raise ValueError(
                        f"{self.name}: allowed value is above maximum"
                    )


@dataclass(frozen=True)
class RuntimeRequirement:
    kind: RequirementKind
    name: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("runtime requirement name must not be empty")


@dataclass(frozen=True)
class SourceCheck:
    checked_at: date
    url: str | None
    kind: SourceKind

    def __post_init__(self) -> None:
        if self.kind is SourceKind.UNVERIFIED and self.url is not None:
            raise ValueError("unverified source checks must not claim a URL")
        if self.kind in {
            SourceKind.PRIMARY_CONTRACT,
            SourceKind.LIFECYCLE_NOTICE,
        }:
            parsed = urlparse(self.url) if isinstance(self.url, str) else None
            if (
                parsed is None
                or parsed.scheme.lower() not in {"http", "https"}
                or not parsed.netloc
            ):
                raise ValueError(
                    "primary contracts and lifecycle notices require an HTTP(S) URL"
                )


@dataclass(frozen=True)
class CatalogEntry:
    key: str
    label: str
    modality: Modality
    maturity: Maturity
    lifecycle: Lifecycle
    product_support: ProductSupport
    provider: Provider
    selectable: bool
    dispatchable: bool
    spendable: bool
    native_audio: bool
    parameters: tuple[ParameterConstraint, ...]
    runtime_options: tuple[tuple[RuntimeRequirement, ...], ...]
    source: SourceCheck
    sunset_on: date | None = None
    legacy_visible: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", tuple(self.parameters))
        object.__setattr__(
            self,
            "runtime_options",
            tuple(tuple(option) for option in self.runtime_options),
        )
        if not self.key or not self.label:
            raise ValueError("catalog key and label must not be empty")
        names = [parameter.name for parameter in self.parameters]
        if len(names) != len(set(names)):
            raise ValueError(f"{self.key}: parameter names must be unique")
        if any(not option for option in self.runtime_options):
            raise ValueError(f"{self.key}: runtime alternatives must not be empty")
        if not self.dispatchable and self.runtime_options:
            raise ValueError(
                f"{self.key}: non-dispatchable entries cannot have runtime options"
            )
        if self.dispatchable and not self.runtime_options:
            raise ValueError(
                f"{self.key}: dispatchable entries need at least one runtime option"
            )
        if self.spendable and not self.dispatchable:
            raise ValueError(f"{self.key}: spendable entries must be dispatchable")
        if self.spendable and self.provider is Provider.INTERNAL:
            raise ValueError(f"{self.key}: internal entries cannot be spendable")
        if self.selectable and self.modality is not Modality.VIDEO:
            raise ValueError(f"{self.key}: only video entries may be shot-selectable")
        if self.selectable and self.key != "AUTO" and not self.dispatchable:
            raise ValueError(
                f"{self.key}: selectable engines must be dispatchable"
            )
        denied_support = {
            ProductSupport.NOT_IMPLEMENTED,
            ProductSupport.DISCONNECTED,
            ProductSupport.KNOWN_BROKEN,
            ProductSupport.UNSUPPORTED,
        }
        if self.lifecycle is Lifecycle.RETIRED or self.product_support in denied_support:
            if self.selectable or self.dispatchable or self.spendable:
                raise ValueError(
                    f"{self.key}: retired or unsupported entries must fail closed"
                )


@dataclass(frozen=True)
class EffectivePolicy:
    lifecycle: Lifecycle
    selectable: bool
    dispatchable: bool
    spendable: bool


@dataclass(frozen=True)
class RuntimeSnapshot:
    """Names of currently present runtime requirements.

    Values are converted to frozensets so callers cannot mutate a snapshot
    after an availability decision has been made.
    """

    credentials: frozenset[str] = frozenset()
    modules: frozenset[str] = frozenset()
    services: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        supplied = {
            RequirementKind.CREDENTIAL: frozenset(self.credentials),
            RequirementKind.MODULE: frozenset(self.modules),
            RequirementKind.SERVICE: frozenset(self.services),
        }
        labels = {
            RequirementKind.CREDENTIAL: "credentials",
            RequirementKind.MODULE: "modules",
            RequirementKind.SERVICE: "services",
        }
        for kind, names in supplied.items():
            if not names <= _RUNTIME_REQUIREMENT_NAMES[kind]:
                raise ValueError(
                    f"runtime snapshot {labels[kind]} contain unknown symbolic names"
                )
        object.__setattr__(
            self,
            "credentials",
            supplied[RequirementKind.CREDENTIAL],
        )
        object.__setattr__(self, "modules", supplied[RequirementKind.MODULE])
        object.__setattr__(self, "services", supplied[RequirementKind.SERVICE])

    @classmethod
    def from_settings(
        cls,
        settings_obj: object,
        module_probe: Callable[[str], bool] | None = None,
        *,
        services: frozenset[str] | set[str] | tuple[str, ...] = (),
    ) -> RuntimeSnapshot:
        """Build a symbolic snapshot without retaining settings values.

        ``module_probe`` is injectable for deterministic tests.  The default
        uses ``importlib.util.find_spec`` and treats probe errors as absence.
        Services are explicit observations; a configured URL is not proof that
        a remote service or pod is ready.
        """

        credential_names = _RUNTIME_REQUIREMENT_NAMES[RequirementKind.CREDENTIAL]
        module_names = _RUNTIME_REQUIREMENT_NAMES[RequirementKind.MODULE]
        present_credentials = frozenset(
            name for name in credential_names if bool(getattr(settings_obj, name, ""))
        )

        if module_probe is None:

            def default_probe(name: str) -> bool:
                try:
                    return find_spec(name) is not None
                except (ImportError, ModuleNotFoundError, ValueError):
                    return False

            module_probe = default_probe

        present_modules = frozenset(
            name for name in module_names if bool(module_probe(name))
        )
        return cls(
            credentials=present_credentials,
            modules=present_modules,
            services=frozenset(services),
        )

    @property
    def present_credentials(self) -> frozenset[str]:
        return self.credentials

    @property
    def present_modules(self) -> frozenset[str]:
        return self.modules

    @property
    def present_services(self) -> frozenset[str]:
        return self.services


@dataclass(frozen=True)
class RuntimeAvailability:
    state: RuntimeAvailabilityState
    effective_selectable: bool
    effective_dispatchable: bool
    effective_spendable: bool
    missing_options: tuple[tuple[RuntimeRequirement, ...], ...] = ()

    @property
    def available(self) -> bool:
        return self.state is RuntimeAvailabilityState.AVAILABLE

    @property
    def missing_requirements(self) -> tuple[RuntimeRequirement, ...]:
        """Unique symbolic requirements missing across all alternatives."""

        seen: set[RuntimeRequirement] = set()
        ordered: list[RuntimeRequirement] = []
        for option in self.missing_options:
            for requirement in option:
                if requirement not in seen:
                    seen.add(requirement)
                    ordered.append(requirement)
        return tuple(ordered)

    def __bool__(self) -> bool:
        return self.available


_CHECKED_AT = date(2026, 7, 30)
_SORA_SUNSET = date(2026, 9, 24)


def _source(
    url: str | None = None,
    kind: SourceKind = SourceKind.UNVERIFIED,
) -> SourceCheck:
    return SourceCheck(checked_at=_CHECKED_AT, url=url, kind=kind)


def _requirement(kind: RequirementKind, name: str) -> RuntimeRequirement:
    return RuntimeRequirement(kind=kind, name=name)


def _credential(name: str) -> RuntimeRequirement:
    return _requirement(RequirementKind.CREDENTIAL, name)


def _module(name: str) -> RuntimeRequirement:
    return _requirement(RequirementKind.MODULE, name)


def _service(name: str) -> RuntimeRequirement:
    return _requirement(RequirementKind.SERVICE, name)


_FAL_RUNTIME = ((_credential("fal_key"), _module("fal_client")),)
_RUNWAY_RUNTIME = (
    (_credential("runwayml_api_secret"), _module("runwayml")),
)
_ELEVENLABS_RUNTIME = (
    (_credential("elevenlabs_api_key"), _module("elevenlabs")),
)

_SORA_PARAMETERS = (
    ParameterConstraint("duration", allowed_values=(4, 8, 12, 16, 20)),
    ParameterConstraint(
        "resolution",
        allowed_values=("720p",),
        note="The current sora-2 product path is clamped to 720p.",
    ),
    ParameterConstraint("aspect_ratio", allowed_values=("16:9", "9:16")),
    ParameterConstraint(
        "input_references",
        max_items=1,
        note="At most one still-or-video input reference.",
    ),
)

_VEO_PARAMETERS = (
    ParameterConstraint("duration", allowed_values=(4, 6, 8)),
    ParameterConstraint("resolution", allowed_values=("720p", "1080p")),
    ParameterConstraint(
        "additional_reference_images",
        max_items=0,
        note="The current start-image I2V path accepts no extra references.",
    ),
    ParameterConstraint(
        "driving_video",
        allowed_values=(False,),
        note="The current start-image I2V path has no driving-video input.",
    ),
    ParameterConstraint(
        "native_audio",
        allowed_values=(False, True),
        note="Native audio is conditional on the Vertex backend.",
    ),
)

_RUNWAY_GEN4_PARAMETERS = (
    # Re-verified 2026-07-30 (slice 5b, Act-Two migration audit) against the
    # installed runwayml SDK's Gen4Turbo TypedDict: `prompt_image` is typed
    # Union[str, Iterable[...]] — the SDK CAN accept several reference
    # images — but phase_c_ffmpeg.py's RUNWAY_GEN4 branch only ever
    # constructs and sends a single base64 image (`prompt_image=data_uri`).
    # max_items=1 pins that IMPLEMENTATION reality, not the SDK's ceiling —
    # this is the source of truth for "single reference image" labeling;
    # there is no multi-reference/"style lock with 3 refs" behavior to
    # remove here, that claim lived only in comments/docstrings (fixed in
    # phase_c_ffmpeg.py) and in domain.scene_decomposer.API_REGISTRY's
    # RUNWAY_GEN4 description (out of this slice's owned files).
    ParameterConstraint("model", allowed_values=("gen4_turbo",)),
    ParameterConstraint("input_images", max_items=1),
    ParameterConstraint("duration", allowed_values=(10,)),
)

_LTX_PARAMETERS = (
    ParameterConstraint("duration", allowed_values=(6, 8, 10)),
    ParameterConstraint(
        "resolution",
        allowed_values=("1080p", "1440p", "2160p"),
    ),
    ParameterConstraint(
        "audio",
        allowed_values=(False,),
        note="The current trustworthy FAL profile is silent.",
    ),
)

_KLING_3_PARAMETERS = (
    ParameterConstraint("duration", allowed_values=(5,)),
    ParameterConstraint(
        "element_images",
        max_items=4,
        note="One frontal image plus at most three reference images.",
    ),
)

_SEEDANCE_PARAMETERS = (
    ParameterConstraint("duration", minimum=4, maximum=15),
    ParameterConstraint("reference_images", max_items=9),
    ParameterConstraint(
        "audio",
        allowed_values=(False,),
        note="The current product path deliberately disables audio.",
    ),
)

_GEMINI_OMNI_PARAMETERS = (
    # https://ai.google.dev/gemini-api/docs/omni — response_format.aspect_ratio
    # accepts "16:9"/"9:16" directly; the adapter threads
    # cinema.aspect.fal_aspect_ratio() into it (gemini_omni_native.py).
    ParameterConstraint("aspect_ratio", allowed_values=("16:9", "9:16")),
    ParameterConstraint(
        "duration",
        note="Prompt-inferred — this API has no structured duration kwarg.",
    ),
    ParameterConstraint(
        "resolution",
        note="Prompt-inferred — this API has no structured resolution kwarg.",
    ),
)

_FAL_SVD_PARAMETERS = (
    ParameterConstraint("motion_bucket_id", allowed_values=(127,)),
    ParameterConstraint("cond_aug", allowed_values=(0.02,)),
    ParameterConstraint(
        "aspect_ratio",
        note="No portrait-output guarantee has been established.",
    ),
)

_FOLEY_PARAMETERS = (
    ParameterConstraint("duration", maximum=190),
    ParameterConstraint("steps", minimum=30, maximum=100),
    ParameterConstraint("cfg_scale", minimum=1, maximum=10),
)


def _entry(
    key: str,
    label: str,
    modality: Modality,
    maturity: Maturity,
    lifecycle: Lifecycle,
    product_support: ProductSupport,
    provider: Provider,
    flags: tuple[bool, bool, bool],
    *,
    native_audio: bool = False,
    parameters: tuple[ParameterConstraint, ...] = (),
    runtime_options: tuple[tuple[RuntimeRequirement, ...], ...] = (),
    source: SourceCheck | None = None,
    sunset_on: date | None = None,
    legacy_visible: bool = True,
) -> CatalogEntry:
    selectable, dispatchable, spendable = flags
    return CatalogEntry(
        key=key,
        label=label,
        modality=modality,
        maturity=maturity,
        lifecycle=lifecycle,
        product_support=product_support,
        provider=provider,
        selectable=selectable,
        dispatchable=dispatchable,
        spendable=spendable,
        native_audio=native_audio,
        parameters=parameters,
        runtime_options=runtime_options,
        source=source or _source(),
        sunset_on=sunset_on,
        legacy_visible=legacy_visible,
    )


_CATALOG_ROWS = (
    _entry(
        "AUTO",
        "Auto (Smart Routing)",
        Modality.VIDEO,
        Maturity.STABLE,
        Lifecycle.ACTIVE,
        ProductSupport.SUPPORTED,
        Provider.INTERNAL,
        (True, False, False),
        source=_source(kind=SourceKind.REPO_EVIDENCE),
    ),
    _entry(
        "KLING_NATIVE",
        "Kling Native (legacy v1.6)",
        Modality.VIDEO,
        Maturity.UNKNOWN,
        Lifecycle.DEPRECATED,
        ProductSupport.LIMITED,
        Provider.KLING,
        (False, True, True),
        runtime_options=(
            (
                _credential("kling_access_key"),
                _credential("kling_secret_key"),
                _module("jwt"),
            ),
        ),
    ),
    _entry(
        "SORA_NATIVE",
        "Sora 2 Native",
        Modality.VIDEO,
        Maturity.STABLE,
        Lifecycle.DEPRECATED,
        ProductSupport.LIMITED,
        Provider.OPENAI,
        (False, True, True),
        parameters=_SORA_PARAMETERS,
        runtime_options=((_credential("openai_api_key"), _module("openai")),),
        source=_source(
            "https://help.openai.com/en/articles/"
            "20001152-what-to-know-about-the-sora-discontinuation",
            SourceKind.LIFECYCLE_NOTICE,
        ),
        sunset_on=_SORA_SUNSET,
    ),
    _entry(
        "VEO_NATIVE",
        "Veo 3.1 Native",
        Modality.VIDEO,
        Maturity.STABLE,
        Lifecycle.ACTIVE,
        ProductSupport.LIMITED,
        Provider.GOOGLE,
        (True, True, True),
        native_audio=True,
        parameters=_VEO_PARAMETERS,
        runtime_options=(
            (
                _credential("google_cloud_project"),
                _service("google_adc"),
                _module("google.genai"),
            ),
            (_credential("google_api_key"), _module("google.genai")),
        ),
        source=_source(
            "https://ai.google.dev/gemini-api/docs/video",
            SourceKind.PRIMARY_CONTRACT,
        ),
    ),
    _entry(
        "GEMINI_OMNI",
        "Gemini Omni Flash (Preview)",
        Modality.VIDEO,
        Maturity.PREVIEW,
        Lifecycle.ACTIVE,
        # Repaired 2026-07-30 (Slice 3): the adapter's inline-base64,
        # URI/Files-API polling+download, and failed/empty-terminal handling
        # were fixed in gemini_omni_native.py, and this entry re-admitted
        # from KNOWN_BROKEN to its truthful current state. LIMITED (not
        # SUPPORTED) because duration/resolution/audio are prompt-inferred —
        # no structured kwargs, unlike the sibling native video engines.
        ProductSupport.LIMITED,
        Provider.GOOGLE_GEMINI_API,
        (True, True, True),
        native_audio=True,
        parameters=_GEMINI_OMNI_PARAMETERS,
        runtime_options=(
            (_credential("google_api_key"), _module("google.genai")),
            (_credential("gemini_api_key"), _module("google.genai")),
        ),
        source=_source(
            "https://ai.google.dev/gemini-api/docs/omni",
            SourceKind.PRIMARY_CONTRACT,
        ),
    ),
    _entry(
        "RUNWAY_GEN4",
        "Runway Gen-4 Turbo",
        Modality.VIDEO,
        Maturity.STABLE,
        Lifecycle.ACTIVE,
        ProductSupport.LIMITED,
        Provider.RUNWAY,
        (True, True, True),
        parameters=_RUNWAY_GEN4_PARAMETERS,
        runtime_options=_RUNWAY_RUNTIME,
        source=_source(
            "https://docs.dev.runwayml.com/guides/models/",
            SourceKind.PRIMARY_CONTRACT,
        ),
    ),
    _entry(
        "LTX",
        "LTX Video 2.3",
        Modality.VIDEO,
        Maturity.STABLE,
        Lifecycle.ACTIVE,
        ProductSupport.LIMITED,
        Provider.LTX_FAL,
        (False, True, True),
        parameters=_LTX_PARAMETERS,
        runtime_options=_FAL_RUNTIME,
        source=_source(
            "https://docs.ltx.io/api-documentation/api-reference/"
            "video-generation/image-to-video",
            SourceKind.PRIMARY_CONTRACT,
        ),
    ),
    _entry(
        "KLING_3_0",
        "Kling v3 Pro (FAL)",
        Modality.VIDEO,
        Maturity.STABLE,
        Lifecycle.ACTIVE,
        ProductSupport.SUPPORTED,
        Provider.FAL,
        (True, True, True),
        parameters=_KLING_3_PARAMETERS,
        runtime_options=_FAL_RUNTIME,
        source=_source(
            "https://fal.ai/models/fal-ai/kling-video/v3/pro/image-to-video/api",
            SourceKind.PRIMARY_CONTRACT,
        ),
    ),
    _entry(
        "SORA_2",
        "Sora 2 (FAL Proxy)",
        Modality.VIDEO,
        Maturity.UNKNOWN,
        Lifecycle.RETIRED,
        ProductSupport.UNSUPPORTED,
        Provider.FAL,
        (False, False, False),
        source=_source(
            "https://fal.ai/models/fal-ai/sora-2/image-to-video/api",
            SourceKind.LIFECYCLE_NOTICE,
        ),
    ),
    _entry(
        "SEEDANCE",
        "Seedance 2.0 (FAL)",
        Modality.VIDEO,
        Maturity.STABLE,
        Lifecycle.ACTIVE,
        ProductSupport.SUPPORTED,
        Provider.FAL,
        (True, True, True),
        parameters=_SEEDANCE_PARAMETERS,
        runtime_options=_FAL_RUNTIME,
        source=_source(
            "https://fal.ai/models/bytedance/seedance-2.0/image-to-video/api",
            SourceKind.PRIMARY_CONTRACT,
        ),
    ),
    _entry(
        "VEO",
        "Veo (FAL Proxy)",
        Modality.VIDEO,
        Maturity.STABLE,
        Lifecycle.ACTIVE,
        ProductSupport.SUPPORTED,
        Provider.FAL,
        (True, True, True),
        runtime_options=_FAL_RUNTIME,
        source=_source(
            "https://fal.ai/models/fal-ai/veo3.1/reference-to-video/api",
            SourceKind.PRIMARY_CONTRACT,
        ),
    ),
    _entry(
        "RUNWAY",
        "Runway (legacy Gen-3)",
        Modality.VIDEO,
        Maturity.STABLE,
        Lifecycle.DEPRECATED,
        ProductSupport.LIMITED,
        Provider.RUNWAY,
        (False, True, True),
        runtime_options=_RUNWAY_RUNTIME,
        source=_source(
            "https://docs.dev.runwayml.com/guides/pricing/",
            SourceKind.LIFECYCLE_NOTICE,
        ),
    ),
    _entry(
        "FAL_SVD",
        "Stable Video Diffusion (FAL)",
        Modality.VIDEO,
        Maturity.UNKNOWN,
        Lifecycle.ACTIVE,
        ProductSupport.LIMITED,
        Provider.FAL,
        (False, True, True),
        parameters=_FAL_SVD_PARAMETERS,
        runtime_options=_FAL_RUNTIME,
        legacy_visible=False,
    ),
    _entry(
        "MUSETALK",
        "MuseTalk v1.5",
        Modality.LIPSYNC,
        Maturity.UNKNOWN,
        Lifecycle.ACTIVE,
        ProductSupport.SUPPORTED,
        Provider.FAL,
        (False, True, True),
        runtime_options=_FAL_RUNTIME,
    ),
    _entry(
        "OMNIHUMAN_V1_5",
        "Omnihuman v1.5",
        Modality.LIPSYNC,
        Maturity.UNKNOWN,
        Lifecycle.ACTIVE,
        ProductSupport.SUPPORTED,
        Provider.FAL,
        (False, True, True),
        runtime_options=_FAL_RUNTIME,
    ),
    _entry(
        "LATENTSYNC",
        "LatentSync v1.6",
        Modality.LIPSYNC,
        Maturity.UNKNOWN,
        Lifecycle.ACTIVE,
        ProductSupport.SUPPORTED,
        Provider.FAL,
        (False, True, True),
        runtime_options=_FAL_RUNTIME,
    ),
    _entry(
        "SYNC_V2",
        "Sync lipsync-2 (legacy)",
        Modality.LIPSYNC,
        Maturity.UNKNOWN,
        Lifecycle.DEPRECATED,
        ProductSupport.LIMITED,
        Provider.FAL,
        (False, True, True),
        runtime_options=_FAL_RUNTIME,
    ),
    _entry(
        "SYNC_SO_V3",
        "sync-3 (Sync Labs)",
        Modality.LIPSYNC,
        Maturity.UNKNOWN,
        Lifecycle.ACTIVE,
        ProductSupport.SUPPORTED,
        Provider.FAL,
        (False, True, True),
        runtime_options=_FAL_RUNTIME,
    ),
    _entry(
        "KLING_LIPSYNC_2",
        "Kling Lip Sync 2",
        Modality.LIPSYNC,
        Maturity.UNKNOWN,
        Lifecycle.ACTIVE,
        ProductSupport.NOT_IMPLEMENTED,
        Provider.FAL,
        (False, False, False),
    ),
    _entry(
        "PIXVERSE_LS2",
        "PixVerse Lip Sync v2",
        Modality.LIPSYNC,
        Maturity.UNKNOWN,
        Lifecycle.ACTIVE,
        ProductSupport.NOT_IMPLEMENTED,
        Provider.FAL,
        (False, False, False),
    ),
    _entry(
        "REACT_1",
        "sync.so react-1",
        Modality.LIPSYNC,
        Maturity.UNKNOWN,
        Lifecycle.ACTIVE,
        ProductSupport.NOT_IMPLEMENTED,
        Provider.FAL,
        (False, False, False),
    ),
    _entry(
        "KLING_AVATAR_V2",
        "Kling AI Avatar v2",
        Modality.LIPSYNC,
        Maturity.UNKNOWN,
        Lifecycle.ACTIVE,
        ProductSupport.NOT_IMPLEMENTED,
        Provider.FAL,
        (False, False, False),
    ),
    _entry(
        # Confirmed KNOWN_BROKEN/RETIRED against the installed runwayml SDK
        # (v4.14.0, 2026-07-30, slice 5b): RunwayML().character_performance
        # .create()'s `model` param is typed Literal["act_two"] — "act_one"
        # is not a constructible request on this endpoint any more. The
        # replacement adapter (performance/act_two.py) targets the live
        # act_two model; this entry intentionally stays retired/broken under
        # the OLD "RUNWAY_ACT_ONE" key rather than being renamed, because the
        # key must keep mirroring domain.scene_decomposer.API_REGISTRY's key
        # (test_catalog_exactly_covers_legacy_registry_plus_fal_svd_
        # mutation_pin pins CATALOG's key set to API_REGISTRY's) — renaming
        # it here without also updating that legacy registry (out of this
        # slice's owned files) would desync the two.
        "RUNWAY_ACT_ONE",
        "Runway Act-One",
        Modality.LIPSYNC,
        Maturity.STABLE,
        Lifecycle.RETIRED,
        ProductSupport.KNOWN_BROKEN,
        Provider.RUNWAY,
        (False, False, False),
        source=_source(
            "https://docs.dev.runwayml.com/guides/models/",
            SourceKind.LIFECYCLE_NOTICE,
        ),
    ),
    _entry(
        "ELEVENLABS_V3",
        "ElevenLabs v3",
        Modality.TTS,
        Maturity.STABLE,
        Lifecycle.ACTIVE,
        ProductSupport.SUPPORTED,
        Provider.ELEVENLABS,
        (False, True, True),
        runtime_options=_ELEVENLABS_RUNTIME,
        source=_source(
            "https://elevenlabs.io/docs/api-reference/text-to-speech/convert",
            SourceKind.PRIMARY_CONTRACT,
        ),
    ),
    _entry(
        "ELEVENLABS_DIALOGUE",
        "ElevenLabs v3 Dialogue Mode",
        Modality.TTS,
        Maturity.BETA,
        Lifecycle.ACTIVE,
        ProductSupport.LIMITED,
        Provider.ELEVENLABS,
        (False, True, True),
        runtime_options=_ELEVENLABS_RUNTIME,
    ),
    _entry(
        "CARTESIA_SONIC_2",
        "Cartesia Sonic 2",
        Modality.TTS,
        Maturity.STABLE,
        Lifecycle.ACTIVE,
        ProductSupport.LIMITED,
        Provider.CARTESIA,
        (False, True, True),
        runtime_options=((_credential("cartesia_api_key"),),),
        source=_source(
            "https://docs.cartesia.ai/build-with-cartesia/tts-models/api-changes",
            SourceKind.PRIMARY_CONTRACT,
        ),
    ),
    _entry(
        "OPENAI_AUDIO",
        "OpenAI gpt-4o-audio",
        Modality.TTS,
        Maturity.STABLE,
        Lifecycle.ACTIVE,
        ProductSupport.NOT_IMPLEMENTED,
        Provider.OPENAI,
        (False, False, False),
        source=_source(kind=SourceKind.REPO_EVIDENCE),
    ),
    _entry(
        "F5_TTS",
        "F5-TTS (open-weights)",
        Modality.TTS,
        Maturity.UNKNOWN,
        Lifecycle.ACTIVE,
        ProductSupport.NOT_IMPLEMENTED,
        Provider.LOCAL_OPEN_WEIGHTS,
        (False, False, False),
    ),
    _entry(
        "GPT_SOVITS",
        "GPT-SoVITS v2",
        Modality.TTS,
        Maturity.UNKNOWN,
        Lifecycle.ACTIVE,
        ProductSupport.NOT_IMPLEMENTED,
        Provider.LOCAL_OPEN_WEIGHTS,
        (False, False, False),
    ),
    _entry(
        "FLUX_DEV",
        "FLUX-Dev (current)",
        Modality.IMAGE,
        Maturity.STABLE,
        Lifecycle.ACTIVE,
        ProductSupport.SUPPORTED,
        Provider.RUNPOD_COMFYUI,
        (False, True, True),
        runtime_options=((_service("comfyui_readiness"),),),
        source=_source(kind=SourceKind.REPO_EVIDENCE),
    ),
    _entry(
        "HIDREAM_I1",
        "HiDream-I1-Full",
        Modality.IMAGE,
        Maturity.UNKNOWN,
        Lifecycle.ACTIVE,
        ProductSupport.NOT_IMPLEMENTED,
        Provider.RUNPOD_COMFYUI,
        (False, False, False),
    ),
    _entry(
        "SD3_5_LARGE",
        "Stable Diffusion 3.5 Large",
        Modality.IMAGE,
        Maturity.UNKNOWN,
        Lifecycle.ACTIVE,
        ProductSupport.NOT_IMPLEMENTED,
        Provider.RUNPOD_COMFYUI,
        (False, False, False),
    ),
    _entry(
        "SUNO_V5",
        "Suno V5 (SunoAPI.org proxy)",
        Modality.MUSIC,
        Maturity.UNKNOWN,
        Lifecycle.ACTIVE,
        ProductSupport.LIMITED,
        Provider.SUNO_API_ORG,
        (False, True, True),
        runtime_options=((_credential("suno_api_key"),),),
    ),
    _entry(
        "ELEVENLABS_MUSIC",
        "ElevenLabs Music",
        Modality.MUSIC,
        Maturity.UNKNOWN,
        Lifecycle.ACTIVE,
        ProductSupport.NOT_IMPLEMENTED,
        Provider.ELEVENLABS,
        (False, False, False),
    ),
    _entry(
        "STABLE_AUDIO_2",
        "Stable Audio 2.0",
        Modality.MUSIC,
        Maturity.UNKNOWN,
        Lifecycle.ACTIVE,
        ProductSupport.LIMITED,
        Provider.FAL,
        (False, True, True),
        runtime_options=_FAL_RUNTIME,
    ),
    _entry(
        "STABLE_AUDIO_FOLEY",
        "Stable Audio (Foley)",
        Modality.FOLEY,
        Maturity.STABLE,
        Lifecycle.ACTIVE,
        ProductSupport.SUPPORTED,
        Provider.STABILITY,
        (False, True, True),
        parameters=_FOLEY_PARAMETERS,
        runtime_options=((_credential("stability_api_key"),),),
        source=_source(
            "https://platform.stability.ai/docs/api-reference",
            SourceKind.PRIMARY_CONTRACT,
        ),
    ),
    _entry(
        "ADOBE_AUDIO_AI",
        "Adobe Audio AI (Project Sonic)",
        Modality.FOLEY,
        Maturity.UNKNOWN,
        Lifecycle.ACTIVE,
        ProductSupport.NOT_IMPLEMENTED,
        Provider.ADOBE,
        (False, False, False),
    ),
    _entry(
        "SUPIR_V0Q",
        "SUPIR-v0Q (image)",
        Modality.UPSCALE,
        Maturity.UNKNOWN,
        Lifecycle.RETIRED,
        ProductSupport.DISCONNECTED,
        Provider.RUNPOD_COMFYUI,
        (False, False, False),
        source=_source(kind=SourceKind.REPO_EVIDENCE),
    ),
    _entry(
        "TOPAZ_ASTRA",
        "Topaz Video AI Astra",
        Modality.UPSCALE,
        Maturity.UNKNOWN,
        Lifecycle.ACTIVE,
        ProductSupport.NOT_IMPLEMENTED,
        Provider.TOPAZ,
        (False, False, False),
    ),
    _entry(
        "SEEDVR2",
        "SeedVR2",
        Modality.UPSCALE,
        Maturity.UNKNOWN,
        Lifecycle.ACTIVE,
        ProductSupport.SUPPORTED,
        Provider.FAL,
        (False, True, True),
        runtime_options=_FAL_RUNTIME,
    ),
    _entry(
        "CCSR",
        "CCSR (image)",
        Modality.UPSCALE,
        Maturity.UNKNOWN,
        Lifecycle.ACTIVE,
        ProductSupport.DISCONNECTED,
        Provider.RUNPOD_COMFYUI,
        (False, False, False),
        source=_source(kind=SourceKind.REPO_EVIDENCE),
    ),
    _entry(
        # Slice 6c3: prior audits claimed Viggle had "no official contract" —
        # that is stale. Viggle now publishes a developer API at
        # https://docs.viggle.ai (verified 2026-07-31; viggle.ai itself 403s
        # bots, so docs.viggle.ai is the only fetchable source). The live
        # adapter (performance/viggle.py) provably mismatches that contract:
        #   adapter                                  docs.viggle.ai
        #   --------------------------------------   ---------------------------
        #   https://api.viggle.ai/v1/motion-transfer  https://apis.viggle.ai/v1/renders
        #   https://api.viggle.ai/v1/jobs/{job_id}     GET /v1/renders/{id}
        #   files={"character_image", "motion_video"}  {"image"/"image_url",
        #                                                "motion_video"/"motion_video_url"}
        #   background_mode: white|green|transparent   background_mode: original|solid|
        #                                                transparent (+ bg_color)
        # i.e. wrong subdomain, wrong path, wrong polling shape, and two of
        # three field names differ — this is not a credentials gap, it is a
        # broken integration. KNOWN_BROKEN here is catalog-only (there is no
        # "VIGGLE" row in domain.scene_decomposer.API_REGISTRY to project
        # from — Viggle motion-retargeting was never routed through the
        # legacy shot-generation registry; it's a Mode-A "performance
        # capture" engine, a separate axis governed by
        # domain/performance.py's ENGINE_VIGGLE + performance/_router.py).
        # Added the same catalog-only way FAL_SVD was (legacy_visible=False).
        #
        # IMPORTANT — this entry does NOT yet gate performance/_router.py:
        # verified by grep that neither domain/performance.py nor
        # performance/_router.py import anything from domain.provider_catalog
        # (only workflow_selector.py, phase_c_ffmpeg.py, web_server.py,
        # llm/prompt_optimizer.py, cinema/phases/motion_render.py,
        # cinema/shots/controller.py, domain/scene_decomposer.py, and
        # domain/video_engine_policy.py consult this module). So today the
        # Mode-A dispatcher (performance/_router.py:78-83) will still call
        # performance.viggle.generate_viggle_performance() unconditionally
        # when ENGINE_VIGGLE is selected — this KNOWN_BROKEN row records
        # catalog truth (fails closed for anything that DOES consult
        # effective_policy/runtime_availability, mirroring RUNWAY_ACT_ONE)
        # but is NOT yet wired into the Mode-A dispatch path itself. Wiring
        # domain/performance.py's engine selection to consult this catalog
        # entry (so ENGINE_VIGGLE is never chosen, and _router.py refuses to
        # dispatch it) is the dedicated repair slice referenced above — out
        # of this slice's owned pathspec (domain/provider_catalog.py only).
        "VIGGLE",
        "Viggle (motion retargeting)",
        Modality.VIDEO,
        Maturity.UNKNOWN,
        Lifecycle.ACTIVE,
        ProductSupport.KNOWN_BROKEN,
        Provider.VIGGLE,
        (False, False, False),
        source=_source("https://docs.viggle.ai", SourceKind.LIFECYCLE_NOTICE),
        legacy_visible=False,
    ),
)


if len({entry.key for entry in _CATALOG_ROWS}) != len(_CATALOG_ROWS):
    raise ValueError("provider catalog keys must be unique")

CATALOG: Mapping[str, CatalogEntry] = MappingProxyType(
    {entry.key: entry for entry in _CATALOG_ROWS}
)

_RUNTIME_REQUIREMENT_NAMES: Mapping[
    RequirementKind,
    frozenset[str],
] = MappingProxyType(
    {
        kind: frozenset(
            requirement.name
            for entry in CATALOG.values()
            for option in entry.runtime_options
            for requirement in option
            if requirement.kind is kind
        )
        for kind in RequirementKind
    }
)


def get_entry(key: str) -> CatalogEntry:
    """Return the canonical entry, raising ``KeyError`` for unknown IDs."""

    return CATALOG[key]


def _utc_calendar_date() -> date:
    return datetime.now(timezone.utc).date()


def effective_policy(
    key: str,
    *,
    on_date: date | None = None,
) -> EffectivePolicy:
    """Resolve lifecycle and flags for a UTC calendar date.

    A sunset applies on its announced date, not the day after.  This fail-closed
    ``>=`` boundary is intentional and mutation-pinned by tests.
    """

    entry = get_entry(key)
    effective_date = on_date if on_date is not None else _utc_calendar_date()
    if isinstance(effective_date, datetime) or not isinstance(
        effective_date,
        date,
    ):
        raise TypeError(
            "on_date must be a datetime.date; datetime values are not accepted"
        )

    if entry.sunset_on is not None and effective_date >= entry.sunset_on:
        return EffectivePolicy(
            lifecycle=Lifecycle.RETIRED,
            selectable=False,
            dispatchable=False,
            spendable=False,
        )
    return EffectivePolicy(
        lifecycle=entry.lifecycle,
        selectable=entry.selectable,
        dispatchable=entry.dispatchable,
        spendable=entry.spendable,
    )


def _requirement_present(
    requirement: RuntimeRequirement,
    snapshot: RuntimeSnapshot,
) -> bool:
    if requirement.kind is RequirementKind.CREDENTIAL:
        return requirement.name in snapshot.credentials
    if requirement.kind is RequirementKind.MODULE:
        return requirement.name in snapshot.modules
    return requirement.name in snapshot.services


def runtime_availability(
    key: str,
    snapshot: RuntimeSnapshot,
    *,
    on_date: date | None = None,
) -> RuntimeAvailability:
    """Resolve observed readiness without changing static catalog truth."""

    entry = get_entry(key)
    policy = effective_policy(key, on_date=on_date)
    if not policy.dispatchable:
        return RuntimeAvailability(
            state=RuntimeAvailabilityState.NOT_DISPATCHABLE,
            effective_selectable=policy.selectable,
            effective_dispatchable=False,
            effective_spendable=False,
        )

    missing_options: list[tuple[RuntimeRequirement, ...]] = []
    for option in entry.runtime_options:
        missing = tuple(
            requirement
            for requirement in option
            if not _requirement_present(requirement, snapshot)
        )
        if not missing:
            return RuntimeAvailability(
                state=RuntimeAvailabilityState.AVAILABLE,
                effective_selectable=policy.selectable,
                effective_dispatchable=policy.dispatchable,
                effective_spendable=policy.spendable,
            )
        missing_options.append(missing)

    return RuntimeAvailability(
        state=RuntimeAvailabilityState.UNAVAILABLE,
        effective_selectable=False,
        effective_dispatchable=False,
        effective_spendable=False,
        missing_options=tuple(missing_options),
    )


def project_legacy_registry(
    legacy_rows: Mapping[str, Mapping[str, object]],
    *,
    on_date: date | None = None,
) -> dict[str, dict[str, object]]:
    """Copy supplied legacy rows and overlay typed, date-effective truth.

    Catalog-only records are never injected.  ``deepcopy`` prevents mutable
    legacy values such as ``best_for`` lists from aliasing the caller's rows.
    """

    projected: dict[str, dict[str, object]] = {}
    for key, source_row in legacy_rows.items():
        entry = CATALOG.get(key)
        if entry is None or not entry.legacy_visible:
            continue
        policy = effective_policy(key, on_date=on_date)
        row = deepcopy(dict(source_row))
        row.update(
            {
                "label": entry.label,
                "modality": entry.modality.value,
                "status": _legacy_effective_status(entry, policy),
                "maturity": entry.maturity.value,
                "lifecycle": policy.lifecycle.value,
                "product_support": entry.product_support.value,
                "provider": entry.provider.value,
                "selectable": policy.selectable,
                "dispatchable": policy.dispatchable,
                "spendable": policy.spendable,
                "native_audio": entry.native_audio,
                "sunset_on": (
                    entry.sunset_on.isoformat()
                    if entry.sunset_on is not None
                    else None
                ),
                "legacy_visible": entry.legacy_visible,
            }
        )
        projected[key] = row
    return projected


def _legacy_effective_status(
    entry: CatalogEntry,
    policy: EffectivePolicy,
) -> str:
    """Map typed policy into the legacy eligibility vocabulary, fail closed."""

    if entry.key == "AUTO":
        return "live"
    if policy.lifecycle is Lifecycle.RETIRED:
        return "retired"
    if not policy.dispatchable:
        return "disabled"
    if entry.maturity is Maturity.BETA:
        return "beta"
    return "live"


__all__ = [
    "CATALOG",
    "CatalogEntry",
    "EffectivePolicy",
    "Lifecycle",
    "Maturity",
    "Modality",
    "ParameterConstraint",
    "ProductSupport",
    "Provider",
    "RequirementKind",
    "RuntimeAvailability",
    "RuntimeAvailabilityState",
    "RuntimeRequirement",
    "RuntimeSnapshot",
    "SourceCheck",
    "SourceKind",
    "effective_policy",
    "get_entry",
    "project_legacy_registry",
    "runtime_availability",
]
