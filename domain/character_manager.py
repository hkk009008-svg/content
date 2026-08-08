"""
Cinema Production Tool — Character Manager (v2)
Real-photo-first character creation with multi-angle reference sheets,
embedding caching, and voice assignment for multi-character cinema production.

Key changes from v1:
- Characters REQUIRE real uploaded photos (no synthetic generation)
- Multi-angle reference sheets: front, 45°, profile, back
- Higher identity validation thresholds (0.70+)
- Multi-reference support for downstream Kling subject binding
"""
from typing import Any, Mapping, Optional, List

import os
import json
import re
import shutil
import numpy as np
try:
    from identity.tf_preload import preload_tensorflow
    preload_tensorflow()  # MUST precede the deepface import
    from deepface import DeepFace
    DEEPFACE_AVAILABLE = True
except ImportError:
    DEEPFACE_AVAILABLE = False

try:
    import fal_client
    FAL_AVAILABLE = True
except ImportError:
    FAL_AVAILABLE = False

# Identity validation threshold — raised from 0.45 to 0.70 for production quality
IDENTITY_THRESHOLD = 0.70
# Minimum acceptable threshold (for fallback / lenient mode)
IDENTITY_THRESHOLD_LENIENT = 0.55

from config.settings import settings
from cinema.fal_limits import FAL_TIMEOUT_IMAGE_S
from cost_tracker import API_COST_USD
from paid_provider import (
    file_fingerprint,
    has_paid_attempt_authority,
    paid_attempt_id,
    request_fingerprint,
    run_durable_fal_job,
)
from performance._net import safe_download, validate_image_artifact
from domain.reference_set import CREATION_KINDS
from domain.project_manager import (
    MutationResult,
    add_character,
    get_character,
    get_project_dir,
    make_character,
    mutate_project,
)


_CREATION_REQUEST_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_FLUX_KONTEXT_APPLICATION = "fal-ai/flux-pro/kontext/max/multi"
_FLUX_KONTEXT_ENGINE = "FLUX_KONTEXT"
_FLUX_KONTEXT_OPERATION = "multi_angle_ref"
_FLUX_KONTEXT_COST_USD = API_COST_USD[_FLUX_KONTEXT_ENGINE]
_ANGLE_CONFIGS = (
    {
        "name": "angle_45",
        "prompt": (
            "Keep this exact person's face identical. Same person, same clothing, same lighting. "
            "Three-quarter view, face turned 45 degrees to the right. "
            "Photorealistic portrait, 8K, cinematic studio lighting."
        ),
    },
    {
        "name": "angle_profile",
        "prompt": (
            "Keep this exact person's face identical. Same person, same clothing, same lighting. "
            "Side profile view, face turned 90 degrees showing left side. "
            "Photorealistic portrait, 8K, cinematic studio lighting."
        ),
    },
    {
        "name": "angle_back",
        "prompt": (
            "Keep this exact person identical. Same clothing, same hairstyle visible from behind. "
            "Back of head and shoulders view. "
            "Photorealistic, 8K, cinematic studio lighting."
        ),
    },
    {
        "name": "expression_smile",
        "prompt": (
            "Keep this exact person's face identical. Same person, same clothing, same lighting. "
            "Warm genuine smile, eyes slightly crinkled, direct eye contact with camera. "
            "Photorealistic portrait, 8K, cinematic studio lighting."
        ),
    },
    {
        "name": "lighting_outdoor",
        "prompt": (
            "Keep this exact person's face identical. Same person, same clothing. "
            "Natural outdoor golden hour lighting, warm side light from the left, soft shadows. "
            "Photorealistic portrait, 8K, cinematic natural lighting."
        ),
    },
)

# Expanded voice pool — full range: women, men, children, elderly, diverse accents
VOICE_POOL = [
    # --- Women ---
    {"id": "21m00Tcm4TlvDq8ikWAM", "name": "Rachel", "style": "Warm, calm woman", "category": "woman"},
    {"id": "EXAVITQu4vr4xnSDxMaL", "name": "Bella", "style": "Soft, gentle young woman", "category": "woman"},
    {"id": "MF3mGyEYCl7XYWbV9V6O", "name": "Elli", "style": "Confident, clear woman", "category": "woman"},
    {"id": "ThT5KcBeYPX3keUQqHPh", "name": "Dorothy", "style": "Pleasant, expressive woman", "category": "woman"},
    {"id": "AZnzlk1XvdvUeBnXmlld", "name": "Domi", "style": "Strong, assertive woman", "category": "woman"},
    {"id": "jBpfuIE2acCO8z3wKNLl", "name": "Gigi", "style": "Animated, youthful woman", "category": "woman"},
    {"id": "oWAxZDx7w5VEj9dCyTzz", "name": "Grace", "style": "Elegant, mature woman", "category": "woman"},
    {"id": "XB0fDUnXU5powFXDhCwa", "name": "Charlotte", "style": "Warm, narrative woman (English accent)", "category": "woman"},
    {"id": "pFZP5JQG7iQjIQuC4Bku", "name": "Lily", "style": "Warm, British young woman", "category": "woman"},
    # --- Men ---
    {"id": "pNInz6obpgDQGcFmaJgB", "name": "Adam", "style": "Deep, authoritative man", "category": "man"},
    {"id": "ErXwobaYiN019PkySvjV", "name": "Antoni", "style": "Clean, professional man", "category": "man"},
    {"id": "D38z5RcWu1voky8WS1ja", "name": "Fin", "style": "Visceral, gritty man", "category": "man"},
    {"id": "cjVigY5qzO86Huf0OWal", "name": "Eric", "style": "Grizzly, mature, dark man", "category": "man"},
    {"id": "VR6AewLTigWG4xSOukaG", "name": "Arnold", "style": "Commanding, authoritative man", "category": "man"},
    {"id": "yoZ06aMxZJJ28mfd3POQ", "name": "Sam", "style": "Warm, friendly man", "category": "man"},
    {"id": "TxGEqnHWrfWFTfGW9XjX", "name": "Josh", "style": "Deep, narrative man", "category": "man"},
    {"id": "ODq5zmih8GrVes37Dizd", "name": "Patrick", "style": "Authoritative, older man", "category": "man"},
    {"id": "ZQe5CZNOzWyzPSCn5a3c", "name": "James", "style": "Calm, British man", "category": "man"},
    # --- Young / Child ---
    {"id": "jsCqWAovK2LkecY7zXl4", "name": "Freya", "style": "Young girl, bright and curious", "category": "child"},
    {"id": "cgSgspJ2msm6clMCkdW9", "name": "Jessica", "style": "Young woman, energetic and expressive", "category": "young"},
    {"id": "bIHbv24MWmeRgasZH58o", "name": "Will", "style": "Young boy, friendly and warm", "category": "child"},
    # --- Elderly ---
    {"id": "SOYHLrjzK2X1ezoPC6cr", "name": "Harry", "style": "Elderly man, wise and gravelly", "category": "elderly"},
    {"id": "g5CIjZEefAph4nQFvHAz", "name": "Ethan", "style": "Older man, deep and reflective", "category": "elderly"},
    # --- Narration / Specialty ---
    {"id": "2EiwWnXFnvU5JabPnv8n", "name": "Clyde", "style": "Warm storyteller, veteran narrator", "category": "narrator"},
    {"id": "onwK4e9ZLuTAKqWW03F9", "name": "Daniel", "style": "Authoritative British narrator", "category": "narrator"},
    # --- Korean (한국어) — ElevenLabs Korean-native voices ---
    # IDs verified from ElevenLabs voice library; all support eleven_v3 multilingual TTS.
    # ElevenLabs v3 will speak Korean from ANY voice, but these are tuned for native Korean prosody.
    {"id": "uyVNoMrnUku1dZyVEXwD", "name": "안나 (Anna)",   "style": "Warm Korean woman, natural conversational tone", "category": "korean_woman"},
    {"id": "4JJwo477JUAx3HV0T7n7", "name": "지영 (Jiyoung)", "style": "Confident Korean woman, broadcast-ready",         "category": "korean_woman"},
    {"id": "j9jfwdrw7BRfcR43Qohk", "name": "민지 (Minji)",   "style": "Young Korean woman, expressive",                 "category": "korean_woman"},
    {"id": "1W00IGEmNmwmsDeYy7ag", "name": "준호 (Junho)",   "style": "Deep Korean man, authoritative narrator",        "category": "korean_man"},
    {"id": "nbrxrAz3eYm9NgojrmFK", "name": "현우 (Hyunwoo)", "style": "Warm Korean man, friendly delivery",             "category": "korean_man"},
    {"id": "PIIbCjI3IbR2cIVbZQjf", "name": "도윤 (Doyoon)",  "style": "Mature Korean man, dramatic",                    "category": "korean_man"},
    {"id": "N2lVS1w4EtoT3dr4eOWO", "name": "Callum", "style": "Intense, dramatic narrator", "category": "narrator"},
]

# Track which voices are already assigned in a project to avoid duplicates
def _get_used_voices(project: dict) -> set:
    # P1-3 migration template (Session 10 / S10): validate to Pydantic at
    # the function boundary, then access via attributes. Cycle-10 first
    # post-S10 caller migration; see docs/MIGRATION-PATTERN-pydantic-caller.md
    # for the full recipe. Character.voice_id defaults to "" (Pydantic field
    # default; domain/models.py:145), which is falsy — so `if c.voice_id`
    # is semantically identical to the legacy `c.get("voice_id")` check.
    from domain.models import Project as _Project
    project_typed = _Project.model_validate(project)
    return {c.voice_id for c in project_typed.characters if c.voice_id}


def _char_dir(project_id: str, char_id: str) -> str:
    d = os.path.join(get_project_dir(project_id), "characters", char_id)
    os.makedirs(d, exist_ok=True)
    return d


def _to_project_relative(project_dir: str, absolute_path: str) -> str:
    """Convert a freshly-written character reference/canonical/embedding/
    multi-angle path to a project-relative form for persistence (Product
    invariant #6: portable persistence -- mirrors slice 10's
    ``ShotController._to_project_relative``, which applies the same
    invariant to take/shot paths). Character reference images are the same
    class of project-owned output as takes and were the one gap slice 10's
    own acceptance criterion left uncovered (FIX-REFS).

    Delegates to the ONE implementation via a duck-typed shim exposing only
    ``project_dir`` (the sole attribute that method reads) -- same reuse
    shape as ``_resolve_stored_media_path`` below and
    ``cinema.screening._resolve_manifest_media_path``. This module has no
    controller ``self``, so it can't use ``ReviewController``'s bound-alike
    reuse shape (calling the unbound method with an existing controller
    instance) and instead borrows the module-level duck-typed-shim shape.
    Local import keeps ShotController's heavier transitive surface
    (phase_c_vision / lip_sync / etc.) off the character-manager import
    path -- and is cycle-safe: ``cinema.shots.controller`` imports
    ``get_reference_image`` from this module at MODULE level (line ~92,
    long before its own ``ShotController`` class is defined), so a
    module-level import back here would deadlock the graph; a lazy,
    call-time import never collides because by the time any caller in this
    file actually invokes this helper, both modules have long finished
    their top-level exec.
    """
    if not absolute_path:
        return absolute_path
    from cinema.shots.controller import ShotController

    class _PathCtx:
        pass

    ctx = _PathCtx()
    ctx.project_dir = project_dir
    return ShotController._to_project_relative(ctx, absolute_path)


def _resolve_stored_media_path(project: dict, stored_path: str) -> str:
    """Resolve a character reference/canonical/embedding/multi-angle path
    read back from persisted state to a real, directly-openable absolute
    path under the CURRENT project directory. Read-side counterpart to
    ``_to_project_relative`` above.

    Every reader that treats a stored character path as a real filesystem
    path -- image-provider reference input (``get_reference_image``), identity
    embedding (``get_character_embedding``), Kling multi-angle subject
    binding (``get_multi_angle_refs``) -- must route the raw string through
    this before ``os.path.exists`` / opening the file. Without it, a
    project-relative path (this module's current persistence shape) is
    checked against the process CWD instead of the project directory, and a
    legacy absolute path baked in before a repo move silently 404s instead
    of being re-rooted under the current project directory (FIX-REFS).

    Module-level sibling of ``cinema.screening._resolve_manifest_media_path``
    (itself modeled on ``ReviewController._resolve_stored_media_path``):
    this module has no controller ``self`` exposing ``.project`` /
    ``.project_dir``, so it borrows the ONE migration implementation
    (``ShotController._resolve_stored_media_path`` -- relative-join,
    legacy-absolute re-root, never fabricating an escape outside the
    project) via a tiny duck-typed shim carrying the two attributes that
    method reads, instead of copying the migration logic here. Local
    import for the same cycle-safety reason documented on
    ``_to_project_relative`` above.
    """
    if not stored_path:
        return stored_path
    project_id = project.get("id") or ""
    if not project_id:
        return stored_path
    from cinema.shots.controller import ShotController

    class _PathCtx:
        pass

    ctx = _PathCtx()
    ctx.project = project
    ctx.project_dir = get_project_dir(project_id)
    return ShotController._resolve_stored_media_path(ctx, stored_path)


def _normalise_creation_request_id(value: object) -> str:
    """Validate the UI's stable idempotency token.

    Empty remains a compatibility mode for non-HTTP callers.  The production
    POST route requires the token, so paid character creation always has a
    stable identity across a lost response or process restart.
    """

    if value is None or value == "":
        return ""
    if not isinstance(value, str) or not _CREATION_REQUEST_ID_RE.fullmatch(value):
        raise ValueError("creation_request_id must be 32 lowercase hexadecimal characters")
    return value


def _normalise_creation_kind(value: object) -> str:
    """Coerce an unrecognised kind to `real`, the stricter of the two.

    `real` requires uploads with a face and never generates a canonical from
    text, so a malformed value defaulting there can only ever be more careful
    than intended. Defaulting the other way would create a real person under
    rules written for a character who depicts nobody.

    Lives here so the invariant holds wherever the fingerprint is computed, not
    only on the path that happens to normalise first. The HTTP route refuses
    unknown values outright; this is what protects the direct callers.
    """

    return value if value in CREATION_KINDS else "real"


def _character_creation_fingerprint(
    *,
    name: str,
    description: str,
    voice_id: str,
    gender: str,
    reference_image_paths: Optional[List[str]],
    creation_kind: str = "real",
) -> str:
    creation_kind = _normalise_creation_kind(creation_kind)
    references = []
    for source in reference_image_paths or []:
        if os.path.exists(source):
            references.append(file_fingerprint(source))
    payload = {
        "name": name,
        "description": description,
        "voice_id": voice_id,
        "gender": gender,
        "reference_files": references,
    }
    # Present ONLY when it is not the default. Every request in flight before
    # this field existed was a `real` one, and adding a key unconditionally
    # would change its fingerprint mid-resume — which `_assert_matching_creation`
    # reads as "different character inputs" and refuses. Keeping the default
    # payload byte-identical lets an interrupted upload-based creation still
    # resume across this change, while a described request gets a distinct
    # fingerprint and cannot be confused with an upload-based one carrying the
    # same name and text.
    if creation_kind != "real":
        payload["creation_kind"] = creation_kind
    return request_fingerprint("character-creation-v1", payload)


def _character_id_for_request(creation_request_id: str) -> str:
    return f"char_{creation_request_id}"


def _assert_matching_creation(
    character: Mapping[str, Any],
    creation_request_id: str,
    creation_fingerprint: str,
) -> None:
    if (
        str(character.get("creation_request_id") or "") != creation_request_id
        or str(character.get("creation_request_fingerprint") or "")
        != creation_fingerprint
    ):
        raise ValueError(
            "creation_request_id was already used for different character inputs"
        )


def _persist_character_once(
    project: dict,
    character: dict,
    *,
    commit_timeout: float,
    creation_request_id: str,
    creation_fingerprint: str,
) -> tuple[dict, bool]:
    """Atomically append one deterministic character or return its prior row."""

    pid = project["id"]
    cid = character["id"]
    created = False

    def _mutate(latest: dict):
        nonlocal created
        existing = get_character(latest, cid)
        if existing is not None:
            _assert_matching_creation(
                existing,
                creation_request_id,
                creation_fingerprint,
            )
            return MutationResult(existing, save=False)
        created = True
        latest["characters"].append(character)
        return character

    result = mutate_project(
        pid,
        _mutate,
        timeout=commit_timeout,
        snapshot=project,
    )
    if result is None:
        raise FileNotFoundError(f"Project '{pid}' not found")
    return result, created


def _finalize_character_reference_artifacts(
    project: dict,
    character: Mapping[str, Any],
    *,
    commit_timeout: float,
) -> dict:
    """Index pending generated references, then atomically publish their IDs.

    The pending recipe is saved with the character before this function runs.
    A crash during ledger writes therefore leaves enough exact evidence for a
    later POST with the same creation request to finish the records without
    entering a provider submission path.
    """

    raw_evidence = character.get("multi_angle_artifact_evidence") or []
    embedding_evidence = character.get("embedding_artifact_evidence")
    if not isinstance(raw_evidence, list):
        raise RuntimeError("character artifact evidence is malformed")
    if embedding_evidence is not None and not isinstance(
        embedding_evidence, Mapping
    ):
        raise RuntimeError("character embedding artifact evidence is malformed")
    if not raw_evidence and embedding_evidence is None:
        return dict(character)
    if character.get("artifact_versioning_pending") is not True:
        raise RuntimeError("character artifact evidence is not marked pending")

    from cinema.artifact_indexing import record_auxiliary_version

    pid = project["id"]
    cid = str(character["id"])
    project_root = get_project_dir(pid)
    summaries: list[dict[str, Any]] = []
    for item in raw_evidence:
        if not isinstance(item, Mapping):
            raise RuntimeError("character artifact evidence is malformed")
        angle_name = str(item.get("angle_name") or "")
        output_path = item.get("path")
        source_path = item.get("source_path")
        parameters = item.get("parameters")
        if (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", angle_name)
            or not isinstance(output_path, str)
            or not output_path
            or not isinstance(source_path, str)
            or not source_path
            or not isinstance(parameters, Mapping)
        ):
            raise RuntimeError("character artifact evidence is malformed")
        record = record_auxiliary_version(
            pid,
            "character_reference",
            f"{cid}-{angle_name}",
            output_path,
            provider="fal",
            model=_FLUX_KONTEXT_APPLICATION,
            parameters=dict(parameters),
            source_paths={"canonical_reference": source_path},
            project_snapshot=project,
            project_root=project_root,
        )
        summaries.append(
            {
                "angle_name": angle_name,
                "path": output_path,
                "artifact_version_id": record["artifact_id"],
                "artifact_version": record["version"],
                "sha256": record["sha256"],
            }
        )

    embedding_summary = None
    if isinstance(embedding_evidence, Mapping):
        embedding_path = embedding_evidence.get("path")
        embedding_source = embedding_evidence.get("source_path")
        embedding_parameters = embedding_evidence.get("parameters")
        embedding_model = embedding_evidence.get("model")
        if (
            not isinstance(embedding_path, str)
            or not embedding_path
            or not isinstance(embedding_source, str)
            or not embedding_source
            or not isinstance(embedding_parameters, Mapping)
            or not isinstance(embedding_model, str)
            or not embedding_model
        ):
            raise RuntimeError("character embedding artifact evidence is malformed")
        record = record_auxiliary_version(
            pid,
            "character_embedding",
            cid,
            embedding_path,
            model=embedding_model,
            parameters=dict(embedding_parameters),
            source_paths={"canonical_reference": embedding_source},
            project_snapshot=project,
            project_root=project_root,
        )
        embedding_summary = {
            "path": embedding_path,
            "artifact_version_id": record["artifact_id"],
            "artifact_version": record["version"],
            "sha256": record["sha256"],
            "model": embedding_model,
        }

    creation_request_id = str(character.get("creation_request_id") or "")
    creation_fingerprint = str(character.get("creation_request_fingerprint") or "")

    def _publish(latest: dict):
        current = get_character(latest, cid)
        if current is None:
            raise RuntimeError("pending character disappeared before artifact publication")
        _assert_matching_creation(
            current,
            creation_request_id,
            creation_fingerprint,
        )
        if current.get("artifact_versioning_pending") is not True:
            existing_angles = current.get("generated_multi_angle_artifacts") or []
            existing_embedding = current.get("generated_embedding_artifact")
            if (
                existing_angles == summaries
                and existing_embedding == embedding_summary
            ):
                return MutationResult(current, save=False)
            raise RuntimeError("character artifact publication state changed concurrently")
        if (current.get("multi_angle_artifact_evidence") or []) != raw_evidence:
            raise RuntimeError("character artifact evidence changed concurrently")
        if current.get("embedding_artifact_evidence") != embedding_evidence:
            raise RuntimeError(
                "character embedding artifact evidence changed concurrently"
            )
        current["generated_multi_angle_artifacts"] = summaries
        if embedding_summary is not None:
            current["generated_embedding_artifact"] = embedding_summary
        current.pop("multi_angle_artifact_evidence", None)
        current.pop("embedding_artifact_evidence", None)
        current.pop("artifact_versioning_pending", None)
        return current

    result = mutate_project(
        pid,
        _publish,
        timeout=commit_timeout,
        snapshot=project,
    )
    if result is None:
        raise FileNotFoundError(f"Project '{pid}' not found")
    return result


def normalise_reference_image(src: str, dst: str) -> str:
    """Store a reference as baseline JPEG, upright, or copy it unchanged.

    MEASURED 2026-08-09: all four of this project's REAL photographs are MPO
    (Multi-Picture Object — what an iPhone writes for HDR/burst), and the Gemini
    route SILENTLY SKIPS them:

        [GEMINI-IMAGE] Skipping invalid reference '...': unsupported reference
        image format 'MPO'

    Gemini is the default image backend. So it had never seen a real photograph
    of the subject — only the six Kontext-generated derivatives, which are
    themselves edits of an MPO canonical that Kontext happens to accept. Two
    providers disagreed about the same bytes and only one of them said so, and
    the pipeline carried on at full confidence with a reference set containing
    no real photograph of the person it is meant to depict.

    Also applies EXIF orientation. Those same four files carry orientation 5 —
    stored sideways and mirrored — and only identity/lora_training.py corrected
    it anywhere in the repo. Measured separately, orientation does NOT move the
    identity score (0.556 -> 0.552), so this is hygiene rather than a fix; it is
    done here because this is the one place every reference passes through, and
    a file that decodes upright everywhere removes a whole class of question.

    Falls back to an exact copy if the image cannot be re-encoded. A reference
    that reaches the project unchanged is recoverable; one that does not arrive
    at all is not.
    """

    try:
        from PIL import Image, ImageOps

        with Image.open(src) as opened:
            fmt = opened.format
            if fmt in ("JPEG", "PNG", "WEBP"):
                shutil.copy2(src, dst)
                return dst
            upright = ImageOps.exif_transpose(opened).convert("RGB")
            upright.save(dst, format="JPEG", quality=95)
            print(f"   [REF] Normalised {fmt} -> JPEG: {os.path.basename(dst)}")
            return dst
    except Exception as exc:
        print(f"   [REF] Could not normalise ({exc}); storing the original bytes")
        shutil.copy2(src, dst)
        return dst


def create_character_with_images(
    project: dict,
    name: str,
    description: str,
    reference_image_paths: Optional[List[str]] = None,
    voice_id: str = "",
    commit_timeout: float = 10,
    gender: str = "",
    cost_tracker=None,
    creation_request_id: str = "",
    creation_kind: str = "real",
    _recovery_out: Optional[dict] = None,
) -> dict:
    """
    Creates a character, from photographs or from a description.

    `creation_kind` decides which, and the two are genuinely different jobs:

    `real` (default) — the character is a person who exists. Photographs pose
    them; generation only ever varies geometry that was PHOTOGRAPHED. Uploads
    are required, and the flow is unchanged:
      1. Copy uploaded reference images into project directory
      2. Reject any upload containing two or more faces
      3. Set the best face-detected upload as canonical reference
      4. Generate the multi-angle sheet from that canonical
      5. Assign voice, pre-compute embedding

    `described` — nobody is being depicted. The first generated image DEFINES
    the character, so it cannot be "wrong" about a face and self-consistency is
    the only requirement. Step 3 has no uploads to choose from, so the canonical
    is generated from the description instead; steps 4-5 then run UNCHANGED,
    because the angle panels were always image-conditioned edits. The gap was
    only ever panel 1.

    Uploads with `described` are refused rather than merged. If photographs of
    the subject exist, the character is `real` and the stricter rules apply; a
    kind that accepted both would let a real person be created under the
    semantics that exist precisely because no real person is involved.
    """
    creation_kind = _normalise_creation_kind(creation_kind)
    if creation_kind == "described":
        if reference_image_paths:
            raise ValueError(
                "a described character is created from text, not uploads — "
                "create it as a real character if photographs exist"
            )
        if not (description or "").strip():
            raise ValueError("a described character needs a description")

    pid = project["id"]
    request_id = _normalise_creation_request_id(creation_request_id)
    creation_fingerprint = (
        _character_creation_fingerprint(
            name=name,
            description=description,
            voice_id=voice_id,
            gender=gender,
            reference_image_paths=reference_image_paths,
            creation_kind=creation_kind,
        )
        if request_id
        else ""
    )
    if request_id:
        cid = _character_id_for_request(request_id)
        existing = get_character(project, cid)
        if existing is not None:
            _assert_matching_creation(existing, request_id, creation_fingerprint)
            if existing.get("artifact_versioning_pending") is True:
                existing = _finalize_character_reference_artifacts(
                    project,
                    existing,
                    commit_timeout=commit_timeout,
                )
            if _recovery_out is not None:
                _recovery_out["idempotent"] = True
                _recovery_out["character_id"] = cid
            return existing

    character = make_character(
        name, description,
        voice_id=voice_id,
        gender=gender,
    )
    if request_id:
        character["id"] = _character_id_for_request(request_id)
        character["creation_request_id"] = request_id
        character["creation_request_fingerprint"] = creation_fingerprint
    cid = character["id"]
    char_path = _char_dir(pid, cid)
    project_dir = get_project_dir(pid)

    # 1. Copy reference images into project, NORMALISED to baseline JPEG.
    stored_refs = []
    if reference_image_paths:
        for i, src in enumerate(reference_image_paths):
            if os.path.exists(src):
                ext = os.path.splitext(src)[1] or ".jpg"
                dst = os.path.join(char_path, f"ref_{i}{ext}")
                normalise_reference_image(src, dst)
                stored_refs.append(dst)
                print(f"   [REF] Stored reference image: {dst}")

    character["reference_images"] = stored_refs

    # 1b. Single-face enforcement (A3) — each reference image must contain
    #     exactly one face.  Two+ faces corrupt every downstream identity score
    #     because the embedding pipeline reads emb_list[0] without knowing which
    #     person it belongs to.  Reject at registration time; fail-loud so the
    #     caller can surface a clear error to the user.
    #     Zero-face images are NOT rejected here — the existing warning path
    #     (step 2) handles them with a limited-identity-lock advisory.
    if DEEPFACE_AVAILABLE:
        for ref_path in stored_refs:
            n = _count_faces(ref_path)
            if n >= 2:
                # Clean up the copied files before raising — mirror the
                # add_character cleanup pattern (try/except/raise below).
                shutil.rmtree(char_path, ignore_errors=True)
                raise ValueError(
                    f"Reference image '{os.path.basename(ref_path)}' contains "
                    f"{n} faces but exactly 1 is required. "
                    f"Provide a single-person reference photo."
                )

    # 2. Find canonical (best face) from uploaded images — NO synthetic fallback
    canonical = _find_canonical_from_uploads(character, char_path)

    # 2b. A described character has no uploads to choose from, so panel 1 is
    #     generated from the text. This is the one generation in the pipeline
    #     with no image source, and it is only legitimate here: for a described
    #     character the result is not a likeness of anyone, it IS the character.
    #     Asking the same generator for a REAL person would produce exactly what
    #     classify_generated_origin calls "invented" — a plausible stranger.
    if not canonical and creation_kind == "described":
        canonical = generate_canonical_from_description(
            description,
            char_path,
            cost_tracker=cost_tracker,
            video_id=pid,
            character_id=cid,
        )
        character["reference_images"] = []

    character["creation_kind"] = creation_kind
    character["canonical_reference"] = canonical or ""

    if not canonical:
        print(f"   [WARN] No detectable face in uploads for '{name}'. Character will have limited identity lock.")

    # 3. Generate multi-angle reference sheet for Kling subject binding
    multi_angles = []
    angle_artifact_evidence: list[dict[str, Any]] = []
    embedding_artifact_evidence: Optional[dict[str, Any]] = None
    if canonical:
        multi_angles = _generate_multi_angle_refs(
            canonical,
            char_path,
            description,
            cost_tracker=cost_tracker,
            video_id=pid,
            character_id=cid,
            artifact_evidence_out=angle_artifact_evidence,
        )
    character["multi_angle_refs"] = multi_angles
    print(f"   [ANGLES] Generated {len(multi_angles)} angle references")

    # 4. Assign voice if not provided — pass language + gender so picker
    # narrows VOICE_POOL to a sensible candidate set (closes VG-B1: prior
    # path returned VOICE_POOL[0] = Rachel English regardless of project
    # language; dispatcher then hit hardcoded Adam fallback if char.voice_id
    # somehow stayed empty).
    if not voice_id:
        project_lang = (project.get("global_settings") or {}).get("language", "") \
            or (project.get("global_settings") or {}).get("language_pref", "")
        character["voice_id"] = assign_voice(
            project,
            language=project_lang,
            gender=gender,
        )

    # 5. Pre-compute embedding
    if canonical and DEEPFACE_AVAILABLE:
        emb_path = os.path.join(char_path, "embedding.npy")
        embedding = compute_face_embedding(canonical)
        if embedding is not None:
            np.save(emb_path, embedding)
            character["embedding_cache"] = emb_path
            from identity.validator import EMBED_MODEL

            embedding_artifact_evidence = {
                "path": emb_path,
                "source_path": canonical,
                "model": EMBED_MODEL,
                "parameters": {
                    "embedding_model": EMBED_MODEL,
                    "array_dtype": str(embedding.dtype),
                    "array_shape": list(embedding.shape),
                },
            }
            print(f"   [EMB] Cached face embedding: {emb_path}")

    # 6. Physical traits + identity anchor
    character["physical_traits"] = description
    character["identity_anchor"] = build_identity_anchor(character)

    # 7. Persist every reference/canonical/embedding/multi-angle path
    # project-relative (Product invariant #6, FIX-REFS) -- mirrors slice
    # 10's take/shot persistence so an exact repo move doesn't strand the
    # image-provider reference conditioning, multi-angle subject binding, or identity
    # embedding behind a now-stale absolute path. Converted here, at the
    # very end, after every LOCAL absolute-path use above (face detection,
    # angle generation, embedding compute) has already happened against the
    # real dst files -- so none of those in-function reads see a
    # project-relative string resolved against the wrong cwd.
    character["reference_images"] = [
        _to_project_relative(project_dir, p) for p in character.get("reference_images", [])
    ]
    character["canonical_reference"] = _to_project_relative(
        project_dir, character.get("canonical_reference", "")
    )
    character["multi_angle_refs"] = [
        _to_project_relative(project_dir, p) for p in character.get("multi_angle_refs", [])
    ]
    character["embedding_cache"] = _to_project_relative(
        project_dir, character.get("embedding_cache", "")
    )
    if angle_artifact_evidence:
        character["multi_angle_artifact_evidence"] = [
            {
                **entry,
                "path": _to_project_relative(project_dir, entry["path"]),
                "source_path": _to_project_relative(
                    project_dir, entry["source_path"]
                ),
            }
            for entry in angle_artifact_evidence
        ]
    if embedding_artifact_evidence is not None:
        character["embedding_artifact_evidence"] = {
            **embedding_artifact_evidence,
            "path": _to_project_relative(
                project_dir, embedding_artifact_evidence["path"]
            ),
            "source_path": _to_project_relative(
                project_dir, embedding_artifact_evidence["source_path"]
            ),
        }
    if angle_artifact_evidence or embedding_artifact_evidence is not None:
        character["artifact_versioning_pending"] = True

    persisted_new = True
    try:
        if request_id:
            character, persisted_new = _persist_character_once(
                project,
                character,
                commit_timeout=commit_timeout,
                creation_request_id=request_id,
                creation_fingerprint=creation_fingerprint,
            )
        else:
            add_character(project, character, timeout=commit_timeout)
    except Exception:
        # Compatibility callers without a durable creation identity retain the
        # old all-or-cleanup contract. A request-keyed directory is recovery
        # state and must survive a lock loss, crash, or ambiguous provider call.
        if not request_id:
            shutil.rmtree(char_path, ignore_errors=True)
        raise

    if character.get("artifact_versioning_pending") is True:
        character = _finalize_character_reference_artifacts(
            project,
            character,
            commit_timeout=commit_timeout,
        )

    if _recovery_out is not None:
        _recovery_out["idempotent"] = not persisted_new
        _recovery_out["character_id"] = cid

    print(f"   [OK] Character '{name}' created: {cid} (refs={len(stored_refs)}, angles={len(multi_angles)})")
    return character


def _find_canonical_from_uploads(character: dict, char_path: str) -> Optional[str]:
    """
    Find the best face-detected image from user uploads. NO synthetic generation.

    Priority:
    1. First image with a clearly detectable face
    2. First uploaded image (if DeepFace unavailable)
    """
    refs = character.get("reference_images", [])
    if not refs:
        return None

    # Try each upload for face detection
    for ref in refs:
        if _has_detectable_face(ref):
            canonical = os.path.join(char_path, "canonical.jpg")
            shutil.copy2(ref, canonical)
            print(f"   [CANON] Set from upload (face verified): {canonical}")
            return canonical

    # If DeepFace unavailable, trust the first upload
    canonical = os.path.join(char_path, "canonical.jpg")
    shutil.copy2(refs[0], canonical)
    print(f"   [CANON] Set from first upload (no face validation available)")
    return canonical


_TEXT_TO_IMAGE_APPLICATION = "fal-ai/flux-pro/v1.1-ultra"
_TEXT_TO_IMAGE_ENGINE = "FLUX_PRO"
_TEXT_TO_IMAGE_OPERATION = "character_canonical"


def generate_canonical_from_description(
    description: str,
    char_path: str,
    *,
    cost_tracker=None,
    video_id: str = "",
    character_id: str = "",
    seed: int = 0,
) -> str:
    """Generate the DEFINING image of a described character, from text alone.

    This is the one generation in the pipeline with no image source. For a
    described character it is not a likeness of anything — it IS the character,
    and every later panel is an edit of it. `_generate_multi_angle_refs` then
    works unchanged, because those panels are already image-conditioned edits;
    the gap was only ever panel 1.

    REFUSED for a real person, by the caller passing the right kind. A real
    character generated from text has nothing about the subject informing it —
    `classify_generated_origin` labels exactly this case "invented", and an
    invented reference is a different person's face.

    Paid: reserved through the durable attempt ledger before submission, so an
    interrupted run resumes its request ID instead of paying twice.
    """

    if not isinstance(description, str) or not description.strip():
        raise ValueError("a described character needs a description to generate from")
    if not FAL_AVAILABLE or not settings.fal_key:
        raise RuntimeError("FAL is unavailable; cannot generate a canonical")
    if not has_paid_attempt_authority(cost_tracker):
        raise TypeError(
            "canonical generation requires the project shared paid-attempt tracker"
        )

    prompt = (
        "Photorealistic portrait photograph of a person. "
        f"{description.strip()} "
        "Neutral expression, facing the camera directly, even studio lighting, "
        "plain background, sharp focus on the face, 8K."
    )
    recipe = {
        "prompt": prompt,
        "aspect_ratio": "3:4",
        "output_format": "jpeg",
        "seed": seed,
        "num_inference_steps": 32,
        "guidance_scale": 3.5,
    }
    logical_character_id = character_id or os.path.basename(os.path.abspath(char_path))
    fingerprint = request_fingerprint(
        "character-canonical-v1", _TEXT_TO_IMAGE_APPLICATION, recipe
    )
    attempt_id = paid_attempt_id(
        "character-canonical", video_id, logical_character_id, fingerprint
    )

    result = run_durable_fal_job(
        application=_TEXT_TO_IMAGE_APPLICATION,
        arguments=recipe,
        attempt_id=attempt_id,
        engine=_TEXT_TO_IMAGE_ENGINE,
        operation=_TEXT_TO_IMAGE_OPERATION,
        estimated_cost_usd=API_COST_USD[_TEXT_TO_IMAGE_ENGINE],
        request_fingerprint_value=fingerprint,
        cost_tracker=cost_tracker,
        shot_id=logical_character_id,
        video_id=video_id,
        poll_timeout_s=FAL_TIMEOUT_IMAGE_S,
    )
    images = result.get("images") if isinstance(result, Mapping) else None
    image = images[0] if isinstance(images, list) and images else None
    img_url = image.get("url") if isinstance(image, Mapping) else None
    if not isinstance(img_url, str) or not img_url:
        raise RuntimeError("text-to-image result omitted its generated image URL")

    out_path = os.path.join(char_path, "canonical_defined.jpg")
    downloaded = safe_download(
        img_url,
        out_path,
        max_bytes=64 * 1024 * 1024,
        allowed_content_types=("image/jpeg",),
        content_validator=lambda path: validate_image_artifact(
            path, expected_formats=("JPEG",)
        ),
    )
    if downloaded is None:
        raise RuntimeError("generated canonical failed download validation")
    print(f"   [CANONICAL] Defined from description: {out_path}")
    return out_path


def _generate_multi_angle_refs(
    canonical_path: str,
    char_path: str,
    description: str,
    cost_tracker=None,
    video_id: str = "",
    character_id: str = "",
    artifact_evidence_out: Optional[list[dict[str, Any]]] = None,
) -> List[str]:
    """
    Generate multi-angle reference images from the canonical front-facing photo.
    Uses FLUX Kontext (in-context editing) to create consistent angle variations.

    Output: five generated references stored in ``char_path``.
    These are used for Kling 3.0 Pro subject binding (multi-image references).

    Every paid generation is reserved through the shared project tracker before
    FAL submission. Existing attempts resume their durable request ID; a lost
    submission acknowledgement fails closed and never enters another POST.
    """
    del description  # The current provider recipe is angle-specific only.
    if not FAL_AVAILABLE or not settings.fal_key:
        print("   [WARN] FAL not available — skipping multi-angle generation")
        return [canonical_path]  # Return just the canonical
    if not has_paid_attempt_authority(cost_tracker):
        raise TypeError(
            "multi-angle generation requires the project shared paid-attempt tracker"
        )

    angle_refs = [canonical_path]  # Front is always the canonical upload
    canonical_fingerprint = file_fingerprint(canonical_path)
    logical_character_id = character_id or os.path.basename(os.path.abspath(char_path))
    canonical_url: Optional[str] = None

    plans: list[dict[str, Any]] = []
    for cfg in _ANGLE_CONFIGS:
        full_prompt = (
            "PRESERVE IDENTITY: Keep this exact person's face, hair, skin, "
            "and all physical features identical to @Image1. "
            f"{cfg['prompt']}"
        )
        provider_recipe = {
            "prompt": full_prompt,
            "guidance_scale": 4.0,
            "aspect_ratio": "3:4",
            "output_format": "jpeg",
            "num_images": 1,
        }
        fingerprint = request_fingerprint(
            "character-multi-angle-v1",
            _FLUX_KONTEXT_APPLICATION,
            canonical_fingerprint,
            cfg["name"],
            provider_recipe,
        )
        attempt_id = paid_attempt_id(
            "character-angle",
            video_id,
            logical_character_id,
            cfg["name"],
            fingerprint,
        )
        plans.append(
            {
                "angle_name": cfg["name"],
                "provider_recipe": provider_recipe,
                "fingerprint": fingerprint,
                "attempt_id": attempt_id,
            }
        )

    # The character row is intentionally committed only after reference
    # generation succeeds. A process may therefore die after an angle attempt
    # is durable but before the row carries the overall creation fingerprint.
    # Bind that gap to the paid ledger: the same UI request/character ID may
    # resume only the exact planned attempt IDs. Different source bytes or a
    # changed provider recipe fail closed before upload or submit.
    paid_snapshot = cost_tracker.get_paid_attempts_snapshot(video_id)
    planned_attempt_ids = {str(plan["attempt_id"]) for plan in plans}
    conflicting_attempts = [
        attempt
        for attempt in paid_snapshot.get("attempts", [])
        if isinstance(attempt, Mapping)
        and attempt.get("shot_id") == logical_character_id
        and attempt.get("engine") == _FLUX_KONTEXT_ENGINE
        and attempt.get("operation") == _FLUX_KONTEXT_OPERATION
        and attempt.get("attempt_id") not in planned_attempt_ids
    ]
    if conflicting_attempts:
        raise ValueError(
            "creation_request_id already owns paid character work for different inputs"
        )

    for plan in plans:
        angle_name = str(plan["angle_name"])
        provider_recipe = plan["provider_recipe"]
        fingerprint = str(plan["fingerprint"])
        attempt_id = str(plan["attempt_id"])
        existing_attempt = cost_tracker.get_paid_attempt(attempt_id)
        if existing_attempt is None:
            # Upload is a non-generative prerequisite. Delay it until a new
            # paid request really needs submission; resumed requests use only
            # their persisted FAL request ID and never depend on a fresh URL.
            if canonical_url is None:
                canonical_url = fal_client.upload_file(canonical_path)
                if not isinstance(canonical_url, str) or not canonical_url:
                    raise RuntimeError("FAL canonical upload returned no URL")
            submitted_arguments = {
                **provider_recipe,
                "image_urls": [canonical_url],
            }
        else:
            submitted_arguments = {
                **provider_recipe,
                # Existing attempts never submit these arguments. Avoid a new
                # upload URL so recovery stays independent of signed-URL churn.
                "image_urls": [],
            }

        result = run_durable_fal_job(
            application=_FLUX_KONTEXT_APPLICATION,
            arguments=submitted_arguments,
            attempt_id=attempt_id,
            engine=_FLUX_KONTEXT_ENGINE,
            operation=_FLUX_KONTEXT_OPERATION,
            estimated_cost_usd=_FLUX_KONTEXT_COST_USD,
            request_fingerprint_value=fingerprint,
            cost_tracker=cost_tracker,
            shot_id=logical_character_id,
            video_id=video_id,
            poll_timeout_s=FAL_TIMEOUT_IMAGE_S,
        )
        images = result.get("images") if isinstance(result, Mapping) else None
        image = images[0] if isinstance(images, list) and images else None
        img_url = image.get("url") if isinstance(image, Mapping) else None
        if not isinstance(img_url, str) or not img_url:
            raise RuntimeError("FLUX Kontext result omitted its generated image URL")

        out_path = os.path.join(char_path, f"{angle_name}.jpg")
        downloaded = safe_download(
            img_url,
            out_path,
            max_bytes=64 * 1024 * 1024,
            allowed_content_types=("image/jpeg",),
            content_validator=lambda path: validate_image_artifact(
                path, expected_formats=("JPEG",)
            ),
        )
        if downloaded is None:
            raise RuntimeError("generated reference image failed download validation")

        attempt = cost_tracker.get_paid_attempt(attempt_id) or {}
        provider_request_id = str(attempt.get("provider_job_id") or "")
        if not provider_request_id:
            raise RuntimeError("completed FLUX Kontext attempt has no durable request ID")
        angle_refs.append(out_path)
        if artifact_evidence_out is not None:
            artifact_evidence_out.append(
                {
                    "angle_name": angle_name,
                    "path": out_path,
                    "source_path": canonical_path,
                    "parameters": {
                        **provider_recipe,
                        "provider_request_id": provider_request_id,
                        "request_fingerprint": fingerprint,
                    },
                }
            )
        print(f"   [ANGLE] Generated {angle_name} (Max Multi): {out_path}")

    return angle_refs


def _has_detectable_face(image_path: str) -> bool:
    """Check if DeepFace can detect at least one face in the image."""
    if not DEEPFACE_AVAILABLE:
        return True  # Assume valid if DeepFace unavailable
    try:
        from identity.validator import cv2_single_thread
        with cv2_single_thread():  # determinism: serialize the OpenCV align race
            faces = DeepFace.extract_faces(img_path=image_path, enforce_detection=True)
        return len(faces) > 0
    except Exception:
        return False


# Two floors, both measured 2026-08-08 across this project's ten reference
# images. Without them the guard rejected the subject's own canonical photograph:
# a 4032x3024 frame yielding a real face at 1664x1664 (22.7% of frame) AND a
# 58x58 speck at 0.0276% — the speck detected at confidence 0.98, HIGHER than the
# real face's 0.94, so confidence ordering separates nothing.
#
# The full measurement, largest detection per image as a share of frame:
#
#   FRONTAL, real face found     angle_45 27.3% | threequarter_smile 24.7%
#                                canonical 22.7% | expression_smile 21.1%
#                                lighting_outdoor 21.0% | front_wide 8.5%
#   OFF-ANGLE, NO real face      profile_outdoor 1.06% | left_profile 0.08%
#                                right_threequarter 0.03% | angle_back none
#
# The detector does not find a face in a true profile AT ALL — on a real
# photograph of the subject in profile the largest detection is a 96x96 speck.
# That compounds ADR-092: the recogniser cannot score a profile and the detector
# cannot even locate one. An off-angle reference therefore yields ZERO
# subject-sized faces, which is correct here — the guard only rejects at >= 2, so
# it declines to judge rather than rejecting a valid reference.
#
# Lowest real face 8.53%, highest artifact 1.06%: an 8x gap. The absolute floor
# sits between them with better than 2x margin on each side.
_MIN_SUBJECT_FACE_FRAME_RATIO = 0.04

# A detection far smaller than the largest in the same image is not a competing
# subject either. This is the question the guard actually asks — is there a
# second person whose identity could be confused with the primary's? — and a
# genuine second person in a reference photograph is comparable in size.
_MIN_COMPETING_FACE_AREA_RATIO = 0.25


def _count_faces(image_path: str) -> int:
    """
    Return the number of SUBJECT-SIZED faces detected in image_path.

    Returns 0 on detection failure or when DeepFace is unavailable.
    Used for single-face enforcement at character registration time (A3).

    Detections far smaller than the largest face are excluded: they are
    background artifacts rather than competing subjects, and counting them
    rejected valid single-person photographs. See
    _MIN_COMPETING_FACE_AREA_RATIO for the measurement behind the threshold.
    """
    if not DEEPFACE_AVAILABLE:
        return 0  # Cannot count; caller falls back to lenient path
    try:
        from identity.validator import cv2_single_thread
        with cv2_single_thread():  # determinism: serialize the OpenCV align race
            faces = DeepFace.extract_faces(img_path=image_path, enforce_detection=True)
    except Exception:
        return 0

    try:
        frame_area = float(_image_pixel_area(image_path))
    except Exception:
        # Without the frame size the absolute floor cannot be applied. Fall back
        # to the relative floor alone rather than skipping both — a parse
        # failure must never make this guard lenient.
        frame_area = 0.0

    areas: List[float] = []
    unmeasurable = 0
    for face in faces:
        area = face.get("facial_area") if isinstance(face, Mapping) else None
        width = area.get("w") if isinstance(area, Mapping) else None
        height = area.get("h") if isinstance(area, Mapping) else None
        if (
            isinstance(width, (int, float))
            and isinstance(height, (int, float))
            and not isinstance(width, bool)
            and not isinstance(height, bool)
        ):
            areas.append(float(width) * float(height))
        else:
            # Unexpected shape: count it rather than silently dropping a face.
            # Held apart from the measured areas so it cannot distort the
            # largest-face comparison — this guard must never become lenient
            # through a parse failure, nor stricter through one.
            unmeasurable += 1

    if frame_area > 0:
        areas = [a for a in areas if a >= frame_area * _MIN_SUBJECT_FACE_FRAME_RATIO]
    if not areas:
        return unmeasurable
    largest = max(areas)
    if largest <= 0:
        return len(areas) + unmeasurable
    competing = sum(
        1 for area in areas if area >= largest * _MIN_COMPETING_FACE_AREA_RATIO
    )
    return competing + unmeasurable


def _image_pixel_area(image_path: str) -> int:
    """Width * height of an image, without decoding its pixels."""
    from PIL import Image

    with Image.open(image_path) as handle:
        width, height = handle.size
    return int(width) * int(height)


def compute_face_embedding(image_path: str) -> Optional[np.ndarray]:
    """Compute an EMBED_MODEL face embedding for an image.

    Routes through identity.validator.represent_deterministic — the single
    represent chokepoint that owns BOTH the cv2 single-thread determinism
    guard and the EMBED_MODEL dispatch (AdaFace is not a DeepFace built-in,
    so a direct DeepFace.represent here would crash under it).
    """
    if not DEEPFACE_AVAILABLE:
        return None
    try:
        from identity.validator import represent_deterministic
        embeddings = represent_deterministic(image_path)
        if embeddings:
            return np.array(embeddings[0]["embedding"])
    except Exception as e:
        print(f"   ⚠️ Embedding computation failed: {e}")
    return None


def get_character_embedding(project: dict, char_id: str) -> Optional[np.ndarray]:
    """Load cached embedding or compute on-the-fly."""
    char = get_character(project, char_id)
    if not char:
        return None

    # FIX-REFS: resolve through the slice-10 migration chokepoint -- the
    # stored value may be project-relative (current persistence shape) or a
    # legacy absolute path from before a repo move; raw os.path.exists on
    # the unresolved string silently "misses" in either case.
    cache_path = _resolve_stored_media_path(project, char.get("embedding_cache", ""))
    if cache_path and os.path.exists(cache_path):
        return np.load(cache_path)

    canonical = _resolve_stored_media_path(project, char.get("canonical_reference", ""))
    if canonical and os.path.exists(canonical):
        return compute_face_embedding(canonical)

    return None


def assign_voice(
    project: dict,
    preference: str = "",
    language: str = "",
    gender: str = "",
) -> str:
    """Assign an ElevenLabs voice, avoiding duplicates within the project.

    Selection priority:
      1. ``preference`` matches a known voice (name substring or exact id) → return.
      2. Language + gender → filter VOICE_POOL by language's voice_pool_filter
         (from ``domain.language_defaults``) AND gender-mapped category prefix,
         return first unused.
      3. Language only → filter VOICE_POOL by language's voice_pool_filter,
         return first unused.
      4. Gender only → filter VOICE_POOL by gender-mapped category prefix
         (``man`` / ``korean_man`` / ``elderly`` for male; ``woman`` /
         ``korean_woman`` / ``young`` for female), return first unused.
      5. No hints → first unused voice (legacy behavior).
      6. All filtered candidates used → cycle to first in filtered set; if
         filter empty, fall back to legacy VOICE_POOL[0].

    Closes VG-B1 (cycle-16) — prior signature picked Adam (English male) as
    the de facto default when called without preference on a Korean-female
    project. Language/gender awareness was already encoded in
    ``domain.language_defaults`` and ``VOICE_POOL.category``; this surface
    just wires it through.
    """
    used = _get_used_voices(project)

    # 1. Direct preference match (name or id)
    if preference:
        for v in VOICE_POOL:
            if preference.lower() in v["name"].lower() or preference == v["id"]:
                return v["id"]

    # 2/3/4. Build filtered candidate set from language + gender hints
    candidates = list(VOICE_POOL)
    if language:
        try:
            from domain.language_defaults import get_language_defaults
            filt = get_language_defaults(language).get("voice_pool_filter")
            if filt:
                candidates = [v for v in candidates if v.get("category") in filt]
        except Exception:
            # If language_defaults is unavailable, fall through with full pool.
            pass

    if gender:
        g = gender.lower()
        male_cats = {"man", "korean_man", "elderly"}
        female_cats = {"woman", "korean_woman", "young", "child"}
        if g in {"male", "m", "man"}:
            candidates = [v for v in candidates if v.get("category") in male_cats]
        elif g in {"female", "f", "woman"}:
            candidates = [v for v in candidates if v.get("category") in female_cats]

    # Pick first unused candidate
    for v in candidates:
        if v["id"] not in used:
            print(f"   🎙️ Auto-assigned voice: {v['name']} ({v['style']})")
            return v["id"]

    # All filtered candidates used — cycle to first in filtered set
    if candidates:
        return candidates[0]["id"]

    # Filter excluded everything (e.g., gender + language with no matching
    # category) — fall back to full pool first-unused, then VOICE_POOL[0].
    for v in VOICE_POOL:
        if v["id"] not in used:
            return v["id"]
    return VOICE_POOL[0]["id"]


def get_reference_image(project: dict, char_id: str) -> Optional[str]:
    """Get the canonical approved identity-reference image."""
    char = get_character(project, char_id)
    if not char:
        return None
    # FIX-REFS: resolve through the slice-10 migration chokepoint before
    # checking existence -- see get_character_embedding for why.
    canonical = _resolve_stored_media_path(project, char.get("canonical_reference", ""))
    if canonical and os.path.exists(canonical):
        return canonical
    refs = char.get("reference_images", [])
    for r in refs:
        resolved = _resolve_stored_media_path(project, r)
        if os.path.exists(resolved):
            return resolved
    return None


def get_object_reference_paths(project: dict, object_id: str) -> List[str]:
    """Resolve a product's reference images, canonical first.

    `make_object`'s docstring says objects are "first-class subjects with
    reference-image conditioning" — but no resolver existed, so an object's
    uploaded photographs reached NO image or video provider. The only reader of
    `project["objects"]` on the generation path serialises the record's fields
    into a PROMPT (llm/prompt_optimizer.py:768-779): brand, material, surface,
    texture_anchor, branding_constraints, scale_reference. All described in
    words; the product itself never shown.

    That substitution fails hardest exactly where a product must not drift. A
    logo is typography, and glyph fidelity is the first thing a re-render
    loses. A glossy surface IS its reflected environment. Absolute scale has no
    prior at all — "fits in an adult hand" is a sentence, not a measurement the
    model can see.

    Canonical leads for the same reason it does for characters: slot 0 carries a
    semantic role downstream, where phase_c_ffmpeg uploads the first reference
    as the frontal image.
    """

    obj = next(
        (
            o for o in project.get("objects", [])
            if isinstance(o, dict) and o.get("id") == object_id
        ),
        None,
    )
    if not obj:
        return []
    canonical = _resolve_stored_media_path(project, obj.get("canonical_reference", ""))
    uploads = [
        _resolve_stored_media_path(project, path)
        for path in (obj.get("reference_images") or [])
        if isinstance(path, str) and path
    ]
    ordered: List[str] = []
    if canonical and os.path.exists(canonical):
        ordered.append(canonical)
    for path in uploads:
        if path and path not in ordered and os.path.exists(path):
            ordered.append(path)
    return ordered


IDENTITY_REFERENCE_PROTOCOLS = frozenset({"identity-benchmark-v1"})


def get_identity_reference_paths(
    project: dict,
    char_id: str,
    protocol_id: str,
) -> List[tuple[str, str]]:
    """Resolve the frozen four-reference Identity Lab subject set.

    The v1 comparison protocol selects the canonical reference first, followed
    by persisted approved multi-angle references and then user uploads, stopping
    at four distinct stored paths. Missing selected entries are intentionally
    returned so the experiment store fails closed while opening them. Legacy
    absolute paths are re-rooted through the same authoritative resolver used by
    production character readers.
    """

    if protocol_id not in IDENTITY_REFERENCE_PROTOCOLS:
        raise ValueError("Unsupported Identity Lab protocol")
    char = get_character(project, char_id)
    if not char:
        return []
    result: List[tuple[str, str]] = []
    canonical_value = char.get("canonical_reference")
    uploads = char.get("reference_images", [])
    if not isinstance(uploads, list):
        uploads = []
    if not isinstance(canonical_value, str) or not canonical_value:
        canonical_value = next(
            (value for value in uploads if isinstance(value, str) and value),
            "",
        )
    if canonical_value:
        result.append(("canonical", _resolve_stored_media_path(project, canonical_value)))
    angles = char.get("multi_angle_refs", [])
    if isinstance(angles, list):
        result.extend(
            ("angle", _resolve_stored_media_path(project, value))
            for value in angles
            if isinstance(value, str) and value
        )
    result.extend(
        ("reference", _resolve_stored_media_path(project, value))
        for value in uploads
        if isinstance(value, str) and value
    )
    # Preserve protocol ordering while collapsing a canonical image repeated in
    # reference_images under a different role. Distinct paths containing the
    # same bytes are rejected by the store's SHA-256 binding authority.
    selected: List[tuple[str, str]] = []
    seen_paths = set()
    for role, path in result:
        if path in seen_paths:
            continue
        seen_paths.add(path)
        selected.append((role, path))
        if len(selected) == 4:
            break
    return selected


def build_identity_anchor(character: dict) -> str:
    """
    Build a fixed, immutable identity string for a character.
    This string NEVER changes between shots — it's the character's 'DNA'.

    Uses the physical_traits/description provided by the user.
    This is injected verbatim into every prompt to prevent GPT-4o
    from rephrasing the character's appearance across shots.

    Returns:
        A string like: "a young woman with straight blonde hair, round wire-rimmed
        glasses, fair skin, oval face, slim build"
    """
    traits = character.get("physical_traits", character.get("description", ""))
    name = character.get("name", "character")

    if not traits:
        return f"{name}"

    # The anchor is the character's description AS-IS — never modified
    return f"{name}: {traits}"


def get_identity_anchor(project: dict, char_id: str) -> str:
    """Get the identity anchor for a character by ID."""
    char = get_character(project, char_id)
    if not char:
        return ""
    return build_identity_anchor(char)


def get_multi_angle_refs(project: dict, char_id: str) -> List[str]:
    """
    Get all multi-angle reference images for Kling 3.0 Pro subject binding.
    Returns list of paths: [front, 45°, profile, back] (whatever is available).
    """
    char = get_character(project, char_id)
    if not char:
        return []

    # FIX-REFS: resolve through the slice-10 migration chokepoint before
    # checking existence -- see get_character_embedding for why. Returns
    # the RESOLVED (real, openable) paths -- these feed Kling subject
    # binding directly, same contract as the pre-fix return value.
    refs = char.get("multi_angle_refs", [])
    resolved_refs = [_resolve_stored_media_path(project, r) for r in refs]
    valid = [r for r in resolved_refs if os.path.exists(r)]

    # Fallback to canonical + uploads if no multi-angle refs
    if not valid:
        canonical = _resolve_stored_media_path(project, char.get("canonical_reference", ""))
        if canonical and os.path.exists(canonical):
            return [canonical]
        uploads = [_resolve_stored_media_path(project, r) for r in char.get("reference_images", [])]
        return [r for r in uploads if os.path.exists(r)]

    return valid
