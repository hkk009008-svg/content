"""Conservative provenance adapters for generated cinema artifacts.

The generation controllers own provider dispatch and project mutation. This
module is deliberately smaller: once a take, rejected paid candidate, or final
master is available, it translates only the evidence already present into an
:class:`~cinema.artifact_versions.ArtifactVersionStore` record.

Requested providers are never promoted to actual providers.  Missing source
files are omitted rather than represented by invented hashes, and every
reproducibility record remains non-bit-exact under the store's policy.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from cinema.artifact_versions import (
    ArtifactIntegrityError,
    ArtifactPathError,
    ArtifactValidationError,
    ArtifactVersionStore,
    DISTRIBUTION_CLIENT,
    DISTRIBUTION_INTERNAL,
    _is_sensitive_parameter_key,
)


_TAKE_KINDS = {"keyframe", "performance", "motion", "postprocess"}
_AUXILIARY_KINDS = {
    "background_music",
    "character_embedding",
    "character_reference",
    "dialogue",
    "driving_video",
    "foley",
    "scene_preview",
}
_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SENSITIVE_KEYS = {
    "access_key",
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "credential",
    "credentials",
    "password",
    "private_key",
    "secret",
    "token",
}
_RECIPE_KEYS = {
    "action",
    "attempt_id",
    "attempt_state",
    "aspect_ratio",
    "audio_embedded",
    "camera",
    "color_grade_preset",
    "denoise_strength",
    "dialogue_audio_in_clip",
    "driving_provider",
    "driving_source",
    "duration",
    "duration_s",
    "factor",
    "fps",
    "has_dialogue",
    "mode",
    "music_mood",
    "music_mastering",
    "negative_prompt",
    "noise_scale",
    "num_frames",
    "pacing",
    "positive_prompt",
    "preset",
    "prompt",
    "provider",
    "provider_job_id",
    "provider_status",
    "quality",
    "rejection_stage",
    "request_fingerprint",
    "resolution",
    "scale",
    "scene_transitions",
    "score",
    "shot_type",
    "strength",
    "target_api",
    "target_resolution",
    "threshold",
    "transition_duration",
    "use_scene_detection",
    "validation_state",
}
_TAKE_DEPENDENCIES = {
    "keyframe": ("cinema/shots/controller.py", "phase_c_assembly.py"),
    "performance": ("cinema/shots/controller.py", "performance/_router.py"),
    "motion": ("cinema/shots/controller.py", "phase_c_ffmpeg.py"),
    "postprocess": ("cinema/shots/controller.py",),
}
_POSTPROCESS_DEPENDENCIES = {
    "color_grade": ("phase_c_ffmpeg.py",),
    "face_swap": ("phase_c_vision.py", "lip_sync.py"),
    "lip_sync": ("lip_sync.py",),
    "rife": ("lip_sync.py",),
    "speed": ("phase_c_ffmpeg.py",),
    "upscale": ("lip_sync.py",),
}
_POSTPROCESS_MODELS = {
    "color_grade": "ffmpeg-color-grade",
    "rife": "fal-ai/rife/video",
    "speed": "ffmpeg-speed-adjustment",
    "upscale": "fal-ai/seedvr/upscale/video",
}
_POSTPROCESS_PROVIDERS = {
    "rife": "FAL_RIFE",
    "upscale": "FAL_SEEDVR2",
}
_POSTPROCESS_PARAMETER_KEYS = {
    # These are the only caller-supplied fields the current correction
    # controller actually consumes for the corresponding successful output.
    "color_grade": {"preset"},
    "speed": {"factor"},
}
_AUXILIARY_DEPENDENCIES = {
    "background_music": ("audio/music.py", "audio/effects.py"),
    "character_embedding": ("domain/character_manager.py", "identity/validator.py"),
    "character_reference": ("domain/character_manager.py", "paid_provider.py"),
    "dialogue": ("audio/dialogue.py", "audio/effects.py"),
    "driving_video": ("web_server.py", "performance/_net.py"),
    "foley": ("audio/foley.py", "audio/effects.py"),
    "scene_preview": ("cinema/shots/controller.py", "phase_c_ffmpeg.py"),
}
_SOURCE_COLLECTIONS = (
    "keyframe_takes",
    "performance_takes",
    "motion_takes",
    "postprocess_variants",
)


def _canonical_hash(value: Any, *, field: str) -> str:
    try:
        payload = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ArtifactValidationError(f"{field} must be finite JSON data") from exc
    return hashlib.sha256(payload).hexdigest()


def _normalise_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _safe_json_value(value: Any, *, depth: int = 0) -> Any:
    """Return bounded JSON evidence or ``None`` for an unsafe value.

    This function is used only after field allowlisting.  It still removes
    credential-shaped nested keys so a future structured recipe cannot smuggle
    a secret into the immutable ledger.
    """

    if depth > 5:
        return None
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        if len(value) > 20_000 or "\x00" in value:
            return None
        return value
    if isinstance(value, (list, tuple)):
        if len(value) > 100:
            return None
        result = []
        for item in value:
            cleaned = _safe_json_value(item, depth=depth + 1)
            if cleaned is not None:
                result.append(cleaned)
        return result
    if isinstance(value, Mapping):
        if len(value) > 100:
            return None
        result: dict[str, Any] = {}
        for raw_key, child in value.items():
            if not isinstance(raw_key, str) or not raw_key or len(raw_key) > 128:
                continue
            if (
                _normalise_key(raw_key) in _SENSITIVE_KEYS
                or _is_sensitive_parameter_key(raw_key)
            ):
                continue
            cleaned = _safe_json_value(child, depth=depth + 1)
            if cleaned is not None:
                result[raw_key] = cleaned
        return result
    return None


def _selected_recipe(source: object) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        return {}
    selected: dict[str, Any] = {}
    for key in sorted(_RECIPE_KEYS):
        if key not in source:
            continue
        value = _safe_json_value(source[key])
        if value is not None:
            selected[key] = value
    return selected


def _selected_named_fields(source: object, names: set[str]) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        return {}
    selected: dict[str, Any] = {}
    for key in sorted(names):
        if key not in source:
            continue
        value = _safe_json_value(source[key])
        if value is not None:
            selected[key] = value
    return selected


def _safe_component(field: str, value: object) -> str:
    if not isinstance(value, str) or not _COMPONENT_RE.fullmatch(value):
        raise ArtifactValidationError(f"{field} must be one bounded portable component")
    if value in {".", ".."}:
        raise ArtifactValidationError(f"{field} cannot be a traversal component")
    return value


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 256:
        return None
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        return None
    return value


def _seed_from(take: Mapping[str, Any], metadata: Mapping[str, Any], cascade: Mapping[str, Any]) -> int | str | None:
    for source in (cascade, metadata, take):
        seed = source.get("seed")
        if isinstance(seed, bool):
            continue
        if isinstance(seed, int):
            return seed
        if isinstance(seed, str) and seed and len(seed) <= 256:
            return seed
    return None


def _project_snapshot(project_id: str, supplied: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if supplied is None:
        from domain.project_manager import load_project

        supplied = load_project(project_id)
    if not isinstance(supplied, Mapping):
        raise ArtifactValidationError("project_snapshot must be a project object")
    if supplied.get("id") != project_id:
        raise ArtifactValidationError("project_snapshot does not belong to project_id")
    return supplied


def _find_shot(snapshot: Mapping[str, Any], shot_id: str) -> Mapping[str, Any] | None:
    scenes = snapshot.get("scenes")
    if not isinstance(scenes, list):
        return None
    for scene in scenes:
        if not isinstance(scene, Mapping):
            continue
        shots = scene.get("shots")
        if not isinstance(shots, list):
            continue
        for shot in shots:
            if isinstance(shot, Mapping) and shot.get("id") == shot_id:
                return shot
    return None


def _find_take_path(shot: Mapping[str, Any] | None, take_id: object) -> str | None:
    if shot is None or not isinstance(take_id, str) or not take_id:
        return None
    for collection in _SOURCE_COLLECTIONS:
        takes = shot.get(collection)
        if not isinstance(takes, list):
            continue
        for candidate in takes:
            if not isinstance(candidate, Mapping) or candidate.get("id") != take_id:
                continue
            path = candidate.get("path")
            return path if isinstance(path, str) and path else None
    return None


def _add_source_hash(
    hashes: dict[str, str],
    store: ArtifactVersionStore,
    label: str,
    path: object,
) -> None:
    """Hash one project-owned source; omit missing/unowned optional inputs."""

    if not isinstance(path, (str, os.PathLike)) or not os.fspath(path):
        return
    try:
        observed = store.observe_file(path)
    except (ArtifactPathError, TypeError, ValueError):
        return
    # ArtifactIntegrityError intentionally propagates: a source that mutates
    # while being observed cannot safely become provenance evidence.
    candidate = label
    suffix = 2
    while candidate in hashes and hashes[candidate] != observed.sha256:
        candidate = f"{label}:{suffix}"
        suffix += 1
    hashes[candidate] = observed.sha256


def _take_source_hashes(
    store: ArtifactVersionStore,
    shot: Mapping[str, Any] | None,
    take: Mapping[str, Any],
    metadata: Mapping[str, Any],
    snapshot_hash: str,
) -> dict[str, str]:
    hashes = {"project_snapshot": snapshot_hash}
    for role, field in (("source_take", "source_take_id"), ("parent_take", "parent_take_id")):
        take_id = take.get(field)
        _add_source_hash(hashes, store, role, _find_take_path(shot, take_id))

    strategy = metadata.get("identity_strategy")
    if isinstance(strategy, Mapping):
        conditioned = strategy.get("conditioned_chars")
        if isinstance(conditioned, list):
            for char_index, spec in enumerate(conditioned):
                if not isinstance(spec, Mapping):
                    continue
                _add_source_hash(
                    hashes,
                    store,
                    f"identity_reference:{char_index}",
                    spec.get("reference"),
                )
                angles = spec.get("multi_angle_refs")
                if isinstance(angles, list):
                    for angle_index, angle_path in enumerate(angles):
                        _add_source_hash(
                            hashes,
                            store,
                            f"identity_reference:{char_index}:angle:{angle_index}",
                            angle_path,
                        )

    _add_source_hash(hashes, store, "performance_audio", metadata.get("audio_path"))
    _add_source_hash(hashes, store, "storyboard_source", metadata.get("storyboard_source"))
    action_params = metadata.get("params")
    if isinstance(action_params, Mapping):
        _add_source_hash(hashes, store, "postprocess_lut", action_params.get("lut_path"))
    if metadata.get("action") == "face_swap":
        _add_source_hash(
            hashes,
            store,
            "face_swap_identity_reference",
            metadata.get("identity_reference_path"),
        )
    if metadata.get("action") == "lip_sync":
        for label, field in (
            ("lip_sync_audio", "audio_path"),
            ("lip_sync_character_reference", "character_reference_path"),
            ("lip_sync_video_input", "lipsync_input_video_path"),
        ):
            _add_source_hash(hashes, store, label, metadata.get(field))

    if take.get("kind") == "performance":
        # New accepted takes persist the exact operator-uploaded dispatch input
        # here. The shot-level fallback keeps pre-ledger upload takes indexable.
        driving_path = (
            metadata.get("dispatched_driving_video_path")
            or metadata.get("driving_video_path")
        )
        if not driving_path and shot is not None and metadata.get("driving_source") == "upload":
            driving_path = shot.get("driving_video_path")
        _add_source_hash(
            hashes,
            store,
            "performance_driving_input",
            driving_path,
        )
    if take.get("kind") == "motion" and shot is not None:
        # The controller forwards this approved take to the dispatcher when it
        # exists.  The label intentionally says dispatch reference: a provider
        # that does not support motion references may ignore the argument.
        performance_take_id = shot.get("approved_performance_take_id")
        _add_source_hash(
            hashes,
            store,
            "dispatch_performance_reference",
            _find_take_path(shot, performance_take_id),
        )

    # Structured iteration references are contextual inputs when they resolve
    # to a concrete take in the same shot.  Merely naming a missing reference
    # never manufactures a source hash.
    reference_lists = []
    intent = take.get("intent")
    if isinstance(intent, Mapping) and isinstance(intent.get("refs"), list):
        reference_lists.append(intent["refs"])
    if isinstance(metadata.get("anchor_refs"), list):
        reference_lists.append(metadata["anchor_refs"])
    ref_index = 0
    for refs in reference_lists:
        for reference in refs:
            if not isinstance(reference, Mapping):
                continue
            ref_take_id = reference.get("take_id")
            ref_path = _find_take_path(shot, ref_take_id)
            if ref_path:
                _add_source_hash(hashes, store, f"iteration_reference:{ref_index}", ref_path)
                ref_index += 1
    return hashes


def _identity_recipe(value: object) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    recipe: dict[str, Any] = {}
    for key in ("mechanism_tag", "primary_char_id", "unconditioned_chars"):
        if key in value:
            cleaned = _safe_json_value(value[key])
            if cleaned is not None:
                recipe[key] = cleaned
    conditioned = value.get("conditioned_chars")
    if isinstance(conditioned, list):
        ids = [
            spec.get("char_id")
            for spec in conditioned
            if isinstance(spec, Mapping) and isinstance(spec.get("char_id"), str)
        ]
        if ids:
            recipe["conditioned_char_ids"] = ids[:100]
    return recipe or None


def _iteration_recipe(take: Mapping[str, Any], metadata: Mapping[str, Any]) -> dict[str, Any]:
    recipe: dict[str, Any] = {}
    revised_prompt = _safe_json_value(take.get("revised_prompt"))
    if isinstance(revised_prompt, str):
        recipe["revised_prompt"] = revised_prompt
    intent = take.get("intent")
    if isinstance(intent, Mapping):
        selected: dict[str, Any] = {}
        for key in ("prose", "target_stage", "verb"):
            cleaned = _safe_json_value(intent.get(key))
            if cleaned is not None:
                selected[key] = cleaned
        intent_params = _selected_recipe(intent.get("params"))
        if intent_params:
            selected["params"] = intent_params
        if selected:
            recipe["intent"] = selected
    delta = _selected_recipe(metadata.get("params_delta"))
    if delta:
        recipe["params_delta"] = delta
    return recipe


def _take_parameters(
    take_kind: str,
    take: Mapping[str, Any],
    metadata: Mapping[str, Any],
    cascade: Mapping[str, Any],
) -> dict[str, Any]:
    parameters: dict[str, Any] = {"take_kind": take_kind}
    status = _optional_text(take.get("status"))
    if status and status != "generated":
        parameters["status"] = status
    take_recipe = _selected_recipe(metadata)
    action = metadata.get("action")
    postprocess_recipe = _selected_named_fields(
        metadata.get("params"),
        _POSTPROCESS_PARAMETER_KEYS.get(action, set()) if isinstance(action, str) else set(),
    )
    if postprocess_recipe:
        take_recipe["params"] = postprocess_recipe
    identity = _identity_recipe(metadata.get("identity_strategy"))
    if identity:
        take_recipe["identity_strategy"] = identity
    if take_recipe:
        parameters["take_recipe"] = take_recipe
    provider_recipe = _selected_recipe(cascade)
    if provider_recipe:
        parameters["provider_recipe"] = provider_recipe
    iteration = _iteration_recipe(take, metadata)
    if iteration:
        parameters["iteration"] = iteration
    return parameters


def _provider_and_model(
    take_kind: str,
    metadata: Mapping[str, Any],
    cascade: Mapping[str, Any],
) -> tuple[str | None, str | None]:
    provider = _optional_text(cascade.get("engine"))
    if provider is None and take_kind == "keyframe":
        provider = _optional_text(metadata.get("mechanism_actually_used"))
    if provider is None and take_kind == "performance":
        provider = _optional_text(metadata.get("engine"))

    model = None
    for source, keys in (
        # Cascade metadata is emitted only for the accepted winner.
        (cascade, ("model", "model_id", "model_name")),
        # A generic metadata.model may be merely requested, so only the
        # explicitly actual field is accepted outside winner metadata.
        (metadata, ("actual_model",)),
    ):
        for key in keys:
            model = _optional_text(source.get(key))
            if model is not None:
                break
        if model is not None:
            break

    if take_kind == "postprocess":
        action = metadata.get("action")
        if provider is None and isinstance(action, str):
            provider = _POSTPROCESS_PROVIDERS.get(action)
        if model is None and isinstance(action, str):
            model = _POSTPROCESS_MODELS.get(action)
    return provider, model


def _hash_regular_file(path: Path) -> str:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as exc:
        raise ArtifactPathError(f"dependency file is missing: {path.name}") from exc
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise ArtifactPathError(f"dependency is not a plain file: {path.name}")
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ArtifactPathError(f"dependency cannot be opened: {path.name}") from exc
    digest = hashlib.sha256()
    total = 0
    try:
        before = os.fstat(fd)
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_identity != after_identity or total != after.st_size:
        raise ArtifactIntegrityError(f"dependency changed while hashed: {path.name}")
    return digest.hexdigest()


def _source_dependency_hashes(paths: Sequence[str]) -> dict[str, str]:
    repository_root = Path(__file__).resolve().parents[1]
    hashes: dict[str, str] = {}
    for relative in dict.fromkeys(paths):
        path = repository_root / relative
        try:
            hashes[relative] = _hash_regular_file(path)
        except ArtifactPathError:
            # A packaged deployment may not ship Python source.  In that case
            # omit the source hash; never substitute a source-tree guess.
            continue
    return hashes


def _tool_version_hash(executable: str) -> str | None:
    try:
        completed = subprocess.run(
            [executable, "-version"],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0 or not completed.stdout:
        return None
    payload = completed.stdout + b"\x00stderr\x00" + completed.stderr
    return hashlib.sha256(payload).hexdigest()


def _take_dependency_hashes(take_kind: str, metadata: Mapping[str, Any]) -> dict[str, str]:
    paths = list(_TAKE_DEPENDENCIES[take_kind])
    if take_kind == "postprocess":
        action = metadata.get("action")
        if isinstance(action, str):
            paths.extend(_POSTPROCESS_DEPENDENCIES.get(action, ()))
    return _source_dependency_hashes(paths)


def record_take_version(
    project_id: str,
    shot_id: str,
    take_kind: str,
    take: Mapping[str, Any],
    *,
    project_snapshot: Mapping[str, Any] | None = None,
    project_root: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Record one generated keyframe/performance/motion/postprocess artifact.

    Accepted takes should be the object returned by project mutation. A paid
    candidate rejected by a local gate may instead carry ``status=rejected``;
    it remains internal evidence and is never promoted into project selection.
    When ``project_snapshot`` is omitted, the persisted project is loaded.
    """

    project_value = _safe_component("project_id", project_id)
    shot_value = _safe_component("shot_id", shot_id)
    if take_kind not in _TAKE_KINDS:
        raise ArtifactValidationError("take_kind is not supported")
    if not isinstance(take, Mapping):
        raise ArtifactValidationError("take must be a generated take object")
    if take.get("kind") != take_kind:
        raise ArtifactValidationError("take kind does not match take_kind")
    take_id = _safe_component("take id", take.get("id"))
    take_path = take.get("path")
    if not isinstance(take_path, str) or not take_path:
        raise ArtifactValidationError("generated take has no output path")

    snapshot = _project_snapshot(project_value, project_snapshot)
    snapshot_hash = _canonical_hash(snapshot, field="project_snapshot")
    shot = _find_shot(snapshot, shot_value)
    metadata = take.get("metadata") if isinstance(take.get("metadata"), Mapping) else {}
    cascade = (
        take.get("cascade_metadata")
        if isinstance(take.get("cascade_metadata"), Mapping)
        else {}
    )
    store = (
        ArtifactVersionStore(project_value, project_root)
        if project_root is not None
        else ArtifactVersionStore.for_project(project_value)
    )
    source_hashes = _take_source_hashes(store, shot, take, metadata, snapshot_hash)
    dependencies = _take_dependency_hashes(take_kind, metadata)
    provider, model = _provider_and_model(take_kind, metadata, cascade)

    return store.record_artifact(
        f"shots/{shot_value}/{take_kind}/{take_id}",
        take_path,
        provider=provider,
        model=model,
        parameters=_take_parameters(take_kind, take, metadata, cascade),
        seed=_seed_from(take, metadata, cascade),
        source_hashes=source_hashes,
        dependency_hashes=dependencies,
        distribution_class=DISTRIBUTION_INTERNAL,
    )


def record_auxiliary_version(
    project_id: str,
    asset_kind: str,
    asset_id: str,
    path: str | os.PathLike[str],
    *,
    provider: str | None = None,
    model: str | None = None,
    parameters: Mapping[str, Any] | None = None,
    seed: int | str | None = None,
    source_paths: Mapping[str, str | os.PathLike[str]] | None = None,
    project_snapshot: Mapping[str, Any] | None = None,
    project_root: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Retain a generated non-take asset with conservative provenance."""

    project_value = _safe_component("project_id", project_id)
    if asset_kind not in _AUXILIARY_KINDS:
        raise ArtifactValidationError("asset_kind is not supported")
    asset_value = _safe_component("asset_id", asset_id)
    snapshot = _project_snapshot(project_value, project_snapshot)
    store = (
        ArtifactVersionStore(project_value, project_root)
        if project_root is not None
        else ArtifactVersionStore.for_project(project_value)
    )
    source_hashes = {
        "project_snapshot": _canonical_hash(snapshot, field="project_snapshot")
    }
    if source_paths is not None:
        if not isinstance(source_paths, Mapping):
            raise ArtifactValidationError("source_paths must be an object")
        for raw_label, source_path in sorted(source_paths.items()):
            label = _safe_component("source label", raw_label)
            _add_source_hash(source_hashes, store, label, source_path)

    cleaned_parameters = _safe_json_value(parameters or {})
    if not isinstance(cleaned_parameters, Mapping):
        raise ArtifactValidationError("parameters must be a safe JSON object")
    return store.record_artifact(
        f"assets/{asset_kind}/{asset_value}",
        path,
        provider=_optional_text(provider),
        model=_optional_text(model),
        parameters=dict(cleaned_parameters),
        seed=seed,
        source_hashes=source_hashes,
        dependency_hashes=_source_dependency_hashes(
            _AUXILIARY_DEPENDENCIES[asset_kind]
        ),
        distribution_class=DISTRIBUTION_INTERNAL,
    )


def _final_source_hashes(
    store: ArtifactVersionStore,
    scene_data: Sequence[Mapping[str, Any]],
    bgm_path: str | os.PathLike[str] | None,
    snapshot_hash: str,
) -> tuple[dict[str, str], int]:
    hashes = {"project_snapshot": snapshot_hash}
    clip_count = 0
    for scene_index, scene in enumerate(scene_data):
        if not isinstance(scene, Mapping):
            raise ArtifactValidationError("scene_data entries must be objects")
        clips = scene.get("clips")
        if clips is not None and not isinstance(clips, list):
            raise ArtifactValidationError("scene clips must be a list")
        for clip_index, clip_path in enumerate(clips or []):
            before = len(hashes)
            _add_source_hash(
                hashes,
                store,
                f"scene:{scene_index}:clip:{clip_index}",
                clip_path,
            )
            if len(hashes) > before:
                clip_count += 1
        _add_source_hash(hashes, store, f"scene:{scene_index}:dialogue", scene.get("audio"))
        foley = scene.get("foley")
        if foley is not None and not isinstance(foley, list):
            raise ArtifactValidationError("scene foley must be a list")
        for foley_index, foley_path in enumerate(foley or []):
            _add_source_hash(
                hashes,
                store,
                f"scene:{scene_index}:foley:{foley_index}",
                foley_path,
            )
    _add_source_hash(hashes, store, "background_music", bgm_path)
    return hashes, clip_count


def record_final_version(
    project_id: str,
    final_path: str | os.PathLike[str],
    scene_data: Sequence[Mapping[str, Any]],
    bgm_path: str | os.PathLike[str] | None,
    settings: Mapping[str, Any],
    project_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Record one assembled final master as a client deliverable.

    The final bytes, every still-present project-owned media input, the exact
    project snapshot, assembly source files, and local ffmpeg version output
    are hashed.  The resulting record still states ``bit_exact=False`` because
    codec/tool/platform behavior is not asserted deterministic.
    """

    project_value = _safe_component("project_id", project_id)
    if isinstance(scene_data, (str, bytes)) or not isinstance(scene_data, Sequence):
        raise ArtifactValidationError("scene_data must be a sequence of scene objects")
    if not isinstance(settings, Mapping):
        raise ArtifactValidationError("settings must be an object")
    snapshot = _project_snapshot(project_value, project_snapshot)
    snapshot_hash = _canonical_hash(snapshot, field="project_snapshot")
    store = ArtifactVersionStore.for_project(project_value)
    final_observation = store.observe_file(final_path)
    parts = PurePosixPath(final_observation.relative_path).parts
    if len(parts) < 2 or parts[0] != "exports":
        raise ArtifactValidationError("final master must be published below exports/")

    source_hashes, clip_count = _final_source_hashes(
        store,
        scene_data,
        bgm_path,
        snapshot_hash,
    )
    dependencies = _source_dependency_hashes(
        ("cinema_pipeline.py", "phase_c_ffmpeg.py", "cinema/aspect.py")
    )
    ffmpeg_hash = _tool_version_hash("ffmpeg")
    if ffmpeg_hash is not None:
        dependencies["ffmpeg -version"] = ffmpeg_hash

    assembly_settings = _selected_recipe(settings)
    fixed_recipe: dict[str, Any] = {
        "audio_codec": "aac",
        "audio_bitrate": "192k",
        "normalization_fps": 30,
        "normalization_video_codec": "libx264",
        "requested_loudnorm": {
            "target_i": -14.0,
            "target_lra": 11.0,
            "target_tp": -1.5,
        },
    }
    if "background_music" in source_hashes:
        fixed_recipe["bgm_volume"] = 0.12
    if any(key.startswith("scene:") and ":foley:" in key for key in source_hashes):
        fixed_recipe["foley_volume"] = 0.20

    parameters: dict[str, Any] = {
        "assembly_settings": assembly_settings,
        "source_scene_count": len(scene_data),
        "source_clip_count": clip_count,
        "fixed_recipe": fixed_recipe,
    }

    return store.record_artifact(
        "final/master",
        final_path,
        media_type="video/mp4",
        model="ffmpeg-final-assembly",
        parameters=parameters,
        source_hashes=source_hashes,
        dependency_hashes=dependencies,
        distribution_class=DISTRIBUTION_CLIENT,
    )


__all__ = [
    "record_auxiliary_version",
    "record_final_version",
    "record_take_version",
]
