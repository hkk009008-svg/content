"""
quality_max — MAX-quality image generation orchestrator (N=8 adaptive halt).

The "max" tier path. Invoked by generate_ai_broll(..., quality_tier="max").

Pipeline per shot:
  1. Load pulid_max.json (cached at module level).
  2. Probe pod /object_info once per session — cache available node classes.
  3. Prune nodes the pod doesn't support; rewire downstream consumers.
  4. Inject per-shot values: prompt, refs, LoRA, CN strengths, latent source.
  5. Best-of-N=8 with adaptive halt (face_validator_gate.should_halt):
       - generate 4 candidates with different seeds (parallelizable via ComfyUI queue)
       - score each (ArcFace + Aesthetic v2 -> composite)
       - if halt-threshold met -> stop
       - else generate next 4
  6. If best candidate fails regenerate_floor -> retry with PuLID boost.
  7. Cache prev_shot_latent for next call's LatentBlend.

External deps assumed available on the pod (pruned if missing):
  - PuLID-FLUX (ApplyPulidFlux, PulidFluxModelLoader, etc.)
  - FLUX Union ControlNet Pro (Shakker-Labs)
  - FLUX Redux (StyleModelApplyAdvanced)
  - SkipLayerGuidanceDiT, FreeU_V2, DifferentialDiffusion
  - AlignYourStepsScheduler, DetailDaemonSamplerNode
  - LatentBlend, LatentUpscaleBy
  - DepthAnythingV2Preprocessor, DWPreprocessor, CannyEdgePreprocessor
  - FaceDetailer (Impact Pack)
  - SUPIR_model_loader_v2 + SUPIR_first_stage + SUPIR_sample + SUPIR_decode
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import random
import shutil
import threading
import time
from typing import Dict, List, Optional, Set, Tuple

import requests

from config.settings import settings
from face_validator_gate import (
    CandidateScore,
    should_halt,
    score_candidate,
    select_best,
    needs_regenerate,
)
from workflow_selector import classify_shot_type, get_max_quality_params

# Reuse the existing RunPod client class — no duplication.
from phase_c_assembly import RunPodComfyUI


# ---------------------------------------------------------------------------
# Caches
# ---------------------------------------------------------------------------

_MAX_WORKFLOW_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pulid_max.json")
_MAX_WORKFLOW_CACHED: Optional[dict] = None
_NODE_AVAILABILITY_CACHED: Optional[Set[str]] = None
_NODE_AVAILABILITY_SERVER: Optional[str] = None  # server_url it was probed against
_UPLOAD_CACHE: Dict[str, str] = {}  # content_hash -> remote_filename

# Locks for module-level mutable caches. The web_server processes requests in
# threads (and ShotController may parallelize candidate generation), so two
# threads can race the lazy-load. The granularity is per-cache so the workflow
# JSON load doesn't block uploads, etc.
_WORKFLOW_LOCK = threading.Lock()
_NODE_AVAILABILITY_LOCK = threading.Lock()
_UPLOAD_CACHE_LOCK = threading.Lock()


def _load_max_workflow() -> dict:
    """Load pulid_max.json once and deep-copy on each access."""
    global _MAX_WORKFLOW_CACHED
    with _WORKFLOW_LOCK:
        if _MAX_WORKFLOW_CACHED is None:
            if not os.path.exists(_MAX_WORKFLOW_PATH):
                raise FileNotFoundError(f"pulid_max.json not found at {_MAX_WORKFLOW_PATH}")
            with open(_MAX_WORKFLOW_PATH, "r") as f:
                _MAX_WORKFLOW_CACHED = json.load(f)
    return copy.deepcopy(_MAX_WORKFLOW_CACHED)


def _swap_to_hidream(workflow: dict, available: Set[str]) -> bool:
    """Replace the FLUX UNet loader with HiDream-I1's loader when requested.

    HiDream-I1-Full (17B params) beats FLUX-Dev on photorealism benchmarks but:
      - Has no PuLID equivalent (identity lock comes from LoRA + Redux only)
      - Requires the HiDream-AI/HiDream-I1 custom node installed on the pod
      - Requires the model file (~35GB) at models/diffusion_models/HiDream-I1-Full.safetensors

    The swap is conservative: if the HiDream node class isn't on the pod, this
    no-ops and returns False — caller stays on FLUX. Existing identity stack
    (LoRA at node 700) carries through unchanged.

    Returns True if the swap succeeded, False if it skipped.
    """
    # Probe for the HiDream loader class. Community wrappers expose it under
    # one of these names; try them in order.
    hidream_classes = ("HiDreamModelLoader", "HiDreamI1Loader", "HiDreamLoader")
    chosen = next((c for c in hidream_classes if c in available), None)
    if not chosen:
        return False
    if "112" not in workflow:
        return False

    # Swap node 112 from UNETLoader → HiDreamModelLoader
    workflow["112"]["class_type"] = chosen
    workflow["112"]["inputs"] = {
        "model_name": "HiDream-I1-Full.safetensors",
        "weight_dtype": "fp16",
    }
    workflow["112"].setdefault("_meta", {})
    workflow["112"]["_meta"]["title"] = f"HiDream-I1-Full ({chosen})"

    # PuLID-FLUX nodes (97/99/100/101/93) need to be stripped since HiDream
    # has no PuLID-equivalent. LoRA (700) still applies cleanly.
    for nid in ("97", "99", "100", "101", "93"):
        if nid in workflow:
            workflow.pop(nid)
    # Rewire whatever consumed ApplyPulidFlux output (was node 100) back to
    # the LoRA chain (node 700).
    for node in workflow.values():
        if not isinstance(node, dict) or "inputs" not in node:
            continue
        for k, v in list(node["inputs"].items()):
            if isinstance(v, list) and len(v) == 2 and str(v[0]) == "100":
                node["inputs"][k] = ["700", 0]

    # CLIP for HiDream uses its own dual-CLIP; keep DualCLIPLoader (node 11)
    # since HiDream nodes typically accept the same flux-type CLIP outputs.
    # If HiDream needs a different CLIP loader the workflow will fail-fast
    # at queue time and the cascade falls back to production tier.
    return True


def _probe_node_availability(server_url: str) -> Set[str]:
    """Query the pod's /object_info ONCE per (process, server_url) and cache.

    Returns the set of class_types the pod actually exposes. Used to prune
    nodes for missing custom-node packs before submission, so workflows
    fail-loud at probe time instead of failing-cryptic at queue time.

    Failure handling: a transient probe failure is NOT cached — the next call
    re-probes. Previously a single network blip cached an empty set forever,
    silently disabling pruning for the rest of the process. Now the empty set
    is returned just for this call and the cache remains unset.
    """
    global _NODE_AVAILABILITY_CACHED, _NODE_AVAILABILITY_SERVER
    with _NODE_AVAILABILITY_LOCK:
        if _NODE_AVAILABILITY_CACHED is not None and _NODE_AVAILABILITY_SERVER == server_url:
            return _NODE_AVAILABILITY_CACHED

    try:
        url = f"{server_url.rstrip('/')}/object_info"
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        info = r.json()
        available = set(info.keys())
        print(f"[quality_max] Pod /object_info: {len(available)} node classes available")
        with _NODE_AVAILABILITY_LOCK:
            _NODE_AVAILABILITY_CACHED = available
            _NODE_AVAILABILITY_SERVER = server_url
        return available
    except Exception as e:
        print(f"[quality_max] /object_info probe failed ({e}). Assuming all-available "
              f"for THIS call (cache not poisoned; next call will retry).")
        # Return an empty set for this caller but DO NOT mutate the cache —
        # the next request gets a fresh probe attempt.
        return set()


def _content_hash(path: str) -> str:
    """SHA-1 of file contents, for upload de-duplication."""
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _upload_with_cache(comfy: RunPodComfyUI, local_path: str) -> str:
    """Upload local_path to the pod. Returns remote filename. Cached by content
    hash so the same file (e.g., character face anchor) is uploaded once per
    pipeline run, not once per shot.

    Thread-safety: the cache check and the upload-then-insert are bracketed by
    a lock so two concurrent shots referencing the same content can't both
    upload (wasted bandwidth) or both insert (last-writer-wins is fine in this
    direction but the duplicate upload was the cost).
    """
    h = _content_hash(local_path)
    with _UPLOAD_CACHE_LOCK:
        cached = _UPLOAD_CACHE.get(h)
        if cached is not None:
            return cached
    remote = comfy.upload_image(local_path)
    with _UPLOAD_CACHE_LOCK:
        # Honor an earlier writer if one slipped in while we were uploading —
        # cheap correctness; the remote is content-addressed so any winner is OK.
        _UPLOAD_CACHE.setdefault(h, remote)
        return _UPLOAD_CACHE[h]


# ---------------------------------------------------------------------------
# Workflow injection — split by axis
# ---------------------------------------------------------------------------

def _prune_node(workflow: dict, node_id: str, rewire_to: Optional[Tuple[str, int]] = None):
    """Remove a node and rewire any downstream consumer that referenced it.

    rewire_to: if provided, any input that was [node_id, slot] gets replaced
    with rewire_to (e.g., bypass a missing CN by pointing downstream straight
    at the upstream conditioning node).
    """
    workflow.pop(node_id, None)
    if rewire_to is None:
        return
    for nid, node in workflow.items():
        if not isinstance(node, dict) or "inputs" not in node:
            continue
        for k, v in node["inputs"].items():
            if isinstance(v, list) and len(v) == 2 and str(v[0]) == node_id:
                node["inputs"][k] = list(rewire_to)


def _prune_unavailable(workflow: dict, available: Set[str], has_character: bool, has_init: bool):
    """Strip nodes whose class_type isn't on this pod, with safe rewires."""
    if not available:
        return  # probe failed — best effort

    # No character -> drop identity stack entirely
    if not has_character:
        for nid in ("700", "93", "97", "99", "101", "100"):
            _prune_node(workflow, nid, rewire_to=("112", 0) if nid == "100" else None)
        # If 700 was dropped, CLIPTextEncode needs base CLIP
        if "122" in workflow:
            workflow["122"]["inputs"]["clip"] = ["11", 0]

    # No init image -> drop CN, Redux, img2img, latent blend
    if not has_init:
        for nid in ("400", "401", "402", "403", "404", "410", "411", "412",
                    "420", "421", "422", "431", "432", "800", "801", "803", "804", "810",
                    "200", "201", "250"):
            _prune_node(workflow, nid)
        # Rewire BasicGuider.conditioning straight to FluxGuidance
        if "22" in workflow:
            workflow["22"]["inputs"]["conditioning"] = ["60", 0]
        # Rewire sampler latent to EmptyLatentImage
        if "13" in workflow:
            workflow["13"]["inputs"]["latent_image"] = ["102", 0]

    # Per-class pruning
    pruning_rules = [
        # (node_id, rewire_to_if_missing)
        ("770", ("301", 0)),   # SLG -> upstream PAG
        ("772", ("770", 0) if "770" in workflow else ("301", 0)),  # FreeU
        ("740", ("772", 0) if "772" in workflow else ("770", 0) if "770" in workflow else ("301", 0)),  # DiffDiff
        ("780", ("16", 0)),    # DetailDaemon -> base sampler
        ("250", ("201", 0) if has_init else ("102", 0)),  # LatentBlend -> upstream latent
        ("900", None),         # LatentUpscale (hires-fix pass 2)
        ("901", None),         # 2nd sampler
        ("902", None),         # 2nd VAEDecode
        ("600", ("902", 0) if "902" in workflow else ("8", 0)),    # FaceDetailer
        ("610", ("600", 0) if "600" in workflow else ("902", 0) if "902" in workflow else ("8", 0)),  # ReActor
        ("500", None),         # SUPIR loader
        ("501", None), ("502", None), ("503", None),
        ("950", ("503", 0) if "503" in workflow else ("610", 0) if "610" in workflow else ("8", 0)),
    ]
    for nid, fallback in pruning_rules:
        if nid not in workflow:
            continue
        node = workflow[nid]
        if isinstance(node, dict) and node.get("class_type") not in available:
            _prune_node(workflow, nid, rewire_to=fallback)

    # If hires-fix was pruned, SaveImage feed needs rewiring
    save_feed_priority = ["950", "503", "610", "600", "902", "8"]
    feed_node = next((n for n in save_feed_priority if n in workflow), "8")
    if "9" in workflow:
        workflow["9"]["inputs"]["images"] = [feed_node, 0]


def _inject_identity(workflow: dict, char_lora: Optional[str], face_anchor_remote: Optional[str],
                      params: dict, has_character: bool):
    """Wire LoRA name + face ref into the identity stack."""
    if not has_character:
        return
    if "700" in workflow:
        if char_lora:
            workflow["700"]["inputs"]["lora_name"] = char_lora
            workflow["700"]["inputs"]["strength_model"] = params.get("lora_strength_model", 1.0)
            workflow["700"]["inputs"]["strength_clip"] = params.get("lora_strength_clip", 1.0)
        else:
            # No LoRA -> set strength to 0 (load runs but has zero effect)
            workflow["700"]["inputs"]["strength_model"] = 0.0
            workflow["700"]["inputs"]["strength_clip"] = 0.0
    if face_anchor_remote and "93" in workflow:
        workflow["93"]["inputs"]["image"] = face_anchor_remote
    if "100" in workflow:
        workflow["100"]["inputs"]["weight"] = params.get("pulid_weight", 0.85)
        workflow["100"]["inputs"]["start_at"] = params.get("pulid_start_at", 0.0)
        workflow["100"]["inputs"]["end_at"] = params.get("pulid_end_at", 0.90)


def _inject_conditioning(workflow: dict, prompt: str, prev_shot_remote: Optional[str],
                          style_remote: Optional[str], params: dict, has_character: bool):
    """Prompt + CN channels + Redux."""
    if "122" in workflow:
        workflow["122"]["inputs"]["text"] = prompt
    if "60" in workflow:
        workflow["60"]["inputs"]["guidance"] = params.get("guidance", 3.5)

    if prev_shot_remote:
        if "400" in workflow:
            workflow["400"]["inputs"]["image"] = prev_shot_remote
        # CN strengths from params
        for nid, key in (("404", "cn_depth_strength"),
                         ("412", "cn_canny_strength"),
                         ("422", "cn_pose_strength"),
                         ("432", "cn_tile_strength")):
            if nid in workflow and key in params:
                workflow[nid]["inputs"]["strength"] = params[key]
        # Drop pose channel for landscape / no character
        if not has_character or params.get("cn_pose_strength", 0.0) <= 0.001:
            _prune_node(workflow, "420")
            _prune_node(workflow, "421")
            # Rewire CN chain: tile (432) skips pose (422), chains from canny (412)
            if "432" in workflow and "412" in workflow:
                workflow["432"]["inputs"]["positive"] = ["412", 0]
                workflow["432"]["inputs"]["negative"] = ["412", 1]
            _prune_node(workflow, "422")

    if style_remote and "810" in workflow:
        workflow["810"]["inputs"]["image"] = style_remote
    if "804" in workflow:
        workflow["804"]["inputs"]["image_strength"] = params.get("redux_strength", "high")


def _inject_sampling(workflow: dict, params: dict):
    """AYS / sampler / PAG-SLG-FreeU scales / DetailDaemon."""
    if "17" in workflow:
        workflow["17"]["inputs"]["steps"] = params.get("ays_steps", 28)
    if "16" in workflow:
        workflow["16"]["inputs"]["sampler_name"] = params.get("sampler", "dpmpp_3m_sde_gpu")
    if "301" in workflow:
        workflow["301"]["inputs"]["scale"] = params.get("pag_scale", 3.0)
    if "770" in workflow:
        workflow["770"]["inputs"]["scale"] = params.get("slg_scale", 2.5)
        workflow["770"]["inputs"]["double_layers"] = params.get("slg_double_layers", "7,8,9")
        workflow["770"]["inputs"]["single_layers"] = params.get("slg_single_layers", "10,11")
    if "772" in workflow:
        workflow["772"]["inputs"]["b1"] = params.get("freeu_b1", 1.3)
        workflow["772"]["inputs"]["b2"] = params.get("freeu_b2", 1.4)
        workflow["772"]["inputs"]["s1"] = params.get("freeu_s1", 0.9)
        workflow["772"]["inputs"]["s2"] = params.get("freeu_s2", 0.2)
    if "780" in workflow:
        workflow["780"]["inputs"]["detail_amount"] = params.get("detail_daemon_amount", 0.5)


def _inject_latent_source(workflow: dict, init_remote: Optional[str], params: dict):
    """Pick latent source: EmptyLatent | VAEEncode(init) | LatentBlend(init, empty)."""
    if init_remote and "200" in workflow:
        workflow["200"]["inputs"]["image"] = init_remote
        # Denoise for img2img: use hires_fix_denoise as default (or 1.0 for txt2img)
        if "17" in workflow:
            # Pass 1 denoise comes from params; the 2nd pass (901) re-uses sigmas slot
            workflow["17"]["inputs"]["denoise"] = params.get("denoise_default", 1.0)
        # Use LatentBlend (250) as sampler input — blends init latent with empty noise
        if "250" in workflow and "13" in workflow:
            workflow["250"]["inputs"]["ratio"] = params.get("latent_blend_ratio", 0.15)
            workflow["13"]["inputs"]["latent_image"] = ["250", 0]
        elif "201" in workflow and "13" in workflow:
            workflow["13"]["inputs"]["latent_image"] = ["201", 0]
    else:
        # Txt2img: empty latent feeds sampler
        if "13" in workflow:
            workflow["13"]["inputs"]["latent_image"] = ["102", 0]
        # Drop img2img nodes
        for nid in ("200", "201", "250"):
            _prune_node(workflow, nid)


def _inject_post_passes(workflow: dict, params: dict, available: Set[str]):
    """Toggle FaceDetailer, SUPIR per shot-type policy + availability."""
    # FaceDetailer
    if not params.get("face_detailer_enabled", True) or "FaceDetailer" not in available:
        _prune_node(workflow, "600", rewire_to=("902", 0) if "902" in workflow else ("8", 0))
    elif "600" in workflow:
        workflow["600"]["inputs"]["guide_size"] = params.get("face_detailer_guide_size", 1024)
        workflow["600"]["inputs"]["denoise"] = params.get("face_detailer_denoise", 0.35)

    # SUPIR
    if not params.get("supir_enabled", True) or "SUPIR_model_loader_v2" not in available:
        feed_node = next((n for n in ("610", "600", "902", "8") if n in workflow), "8")
        for nid in ("500", "501", "502", "503"):
            _prune_node(workflow, nid)
        if "950" in workflow:
            workflow["950"]["inputs"]["image"] = [feed_node, 0]
    elif "502" in workflow:
        workflow["502"]["inputs"]["steps"] = params.get("supir_steps", 50)
        workflow["502"]["inputs"]["cfg_scale_start"] = params.get("supir_cfg_scale", 4.0)
        workflow["502"]["inputs"]["cfg_scale_end"] = params.get("supir_cfg_scale", 4.0)

    # Final downsample resolution
    if "950" in workflow:
        w, h = params.get("final_resolution", (3840, 2160))
        workflow["950"]["inputs"]["width"] = w
        workflow["950"]["inputs"]["height"] = h


# ---------------------------------------------------------------------------
# One-shot generation (submit + poll + download)
# ---------------------------------------------------------------------------

def _run_one_candidate(comfy: RunPodComfyUI, workflow: dict, output_filename: str,
                        timeout_s: int = 900) -> Optional[str]:
    """Submit workflow, poll, download. Returns saved path or None on failure."""
    try:
        prompt_id = comfy.queue_prompt(workflow)
    except Exception as e:
        print(f"[quality_max] queue_prompt failed: {e}")
        return None

    start = time.time()
    while time.time() - start < timeout_s:
        history = comfy.get_history(prompt_id)
        if prompt_id in history:
            entry = history[prompt_id]
            outputs = entry.get("outputs", {})
            status = entry.get("status", {})
            status_str = status.get("status_str", "")
            if outputs:
                for node_id, node_output in outputs.items():
                    if "images" in node_output:
                        img_info = node_output["images"][0]
                        img_data = comfy.get_image(img_info["filename"], img_info["subfolder"], img_info["type"])
                        if img_data:
                            with open(output_filename, "wb") as f:
                                f.write(img_data)
                            return output_filename
                # Outputs returned but no images -> task failed; surface status
                msgs = status.get("messages", [])
                print(f"[quality_max] queue {prompt_id} returned no images. "
                      f"status='{status_str}', messages={msgs}")
                return None
            if status_str == "error":
                msgs = status.get("messages", [])
                print(f"[quality_max] queue {prompt_id} error: {msgs}")
                return None
        time.sleep(2)

    print(f"[quality_max] queue {prompt_id} timed out after {timeout_s}s")
    return None


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def generate_ai_broll_max(
    prompt: str,
    output_filename: str,
    seed: Optional[int] = None,
    character_image: Optional[str] = None,
    init_image: Optional[str] = None,
    denoise_strength: float = 1.0,
    characters: Optional[List[dict]] = None,
    multi_angle_refs: Optional[List[str]] = None,
    identity_anchor: str = "",
    pulid_weight_override: Optional[float] = None,
    negative_prompt: str = "",
    # max-tier extras:
    char_lora_path: Optional[str] = None,
    style_reference: Optional[str] = None,
    shot_hint: Optional[dict] = None,
) -> Optional[str]:
    """N=8 adaptive best-of generation. Returns saved path or None.

    Mirrors generate_ai_broll's signature so the dispatcher in
    phase_c_assembly.py can forward kwargs unchanged.

    Returns None if the pod is unavailable or pulid_max.json can't load — the
    caller (generate_ai_broll) should then fall back to the production tier.
    """
    server_url = settings.comfyui_server_url
    if not server_url:
        print("[quality_max] No COMFYUI_SERVER_URL; cannot run max tier.")
        return None
    if not os.path.exists(_MAX_WORKFLOW_PATH):
        print(f"[quality_max] {_MAX_WORKFLOW_PATH} missing; falling back to production tier.")
        return None

    # ---- Classification & param lookup ----
    shot_info = shot_hint or {
        "prompt": prompt,
        "characters_in_frame": ["char"] if character_image else [],
    }
    shot_type = classify_shot_type(shot_info)
    params = get_max_quality_params(shot_type)

    # Apply adaptive PuLID weight override (from continuity feedback loop)
    if pulid_weight_override is not None:
        params["pulid_weight"] = pulid_weight_override

    has_character = bool(character_image and os.path.exists(character_image))
    has_init = bool(init_image and os.path.exists(init_image))

    print(f"[quality_max] {shot_type} | N_max={params['candidate_count']} | "
          f"halt@composite={params['halt_threshold_composite']:.2f}, arc={params['halt_threshold_arc']:.2f} | "
          f"char={has_character} init={has_init}")

    # ---- Probe + prep workflow ----
    available = _probe_node_availability(server_url)
    workflow = _load_max_workflow()
    workflow.pop("_metadata", None)

    # Per-shot image-API swap. If the optimizer requested HiDream-I1 and the pod
    # has the custom node installed, swap the UNet loader. PuLID is stripped in
    # that case (HiDream has no PuLID equivalent) but LoRA + Redux still apply.
    requested_image_api = (shot_hint or {}).get("image_api") or params.get("image_api")
    if requested_image_api == "HIDREAM_I1":
        if _swap_to_hidream(workflow, available):
            print("[quality_max] image backbone: HiDream-I1-Full")
        else:
            print("[quality_max] HiDream-I1 requested but node not available on pod; staying on FLUX")

    _prune_unavailable(workflow, available, has_character, has_init)

    comfy = RunPodComfyUI(server_url)

    # ---- Upload + cache reference images ----
    face_anchor_remote = _upload_with_cache(comfy, character_image) if has_character else None
    init_remote = _upload_with_cache(comfy, init_image) if has_init else None
    style_remote = (
        _upload_with_cache(comfy, style_reference)
        if style_reference and os.path.exists(style_reference)
        else (face_anchor_remote if has_character else None)
    )

    # ---- Inject per-axis params ----
    _inject_identity(workflow, char_lora_path, face_anchor_remote, params, has_character)
    _inject_conditioning(workflow, prompt, init_remote, style_remote, params, has_character)
    _inject_sampling(workflow, params)
    _inject_latent_source(workflow, init_remote, params)
    _inject_post_passes(workflow, params, available)

    # NOTE: hires-fix Pass-2 (nodes 901/902) is currently NOT injected — the
    # workflow runs whatever denoise the JSON baseline encodes. Wiring a true
    # second-pass denoise (via a second BasicScheduler or sigma-scale node) is
    # tracked separately; today the post-passes (FaceDetailer / ReActor / SUPIR)
    # carry the quality lift end-of-pipeline.

    # ---- Best-of-N adaptive halt loop ----
    n_max = int(params.get("candidate_count", 8))
    batch = int(params.get("candidate_batch", 4))
    halt_min_n = int(params.get("halt_min_n", 4))
    halt_composite = float(params.get("halt_threshold_composite", 0.92))
    halt_arc = float(params.get("halt_threshold_arc", 0.85))
    regen_floor = float(params.get("regenerate_floor_arc", 0.82))

    scores: List[CandidateScore] = []
    candidate_paths: List[str] = []
    base_seed = seed if seed is not None else random.randint(1, 2**31 - 1)

    while len(scores) < n_max:
        # Generate next batch (or remainder)
        remaining = n_max - len(scores)
        this_batch = min(batch, remaining)
        for i in range(this_batch):
            cand_seed = base_seed + len(scores) * 1009  # deterministic spread
            wf = copy.deepcopy(workflow)
            if "25" in wf:
                wf["25"]["inputs"]["noise_seed"] = cand_seed
            cand_path = f"{os.path.splitext(output_filename)[0]}_cand{len(scores)}.jpg"
            saved = _run_one_candidate(comfy, wf, cand_path)
            if not saved:
                continue
            candidate_paths.append(saved)
            cs = score_candidate(saved, character_image if has_character else None)
            cs.seed = cand_seed
            scores.append(cs)
            print(f"[quality_max]   cand {len(scores)}/{n_max} seed={cand_seed} "
                  f"arc={cs.arc_score:.3f} aes={cs.aesthetic_score:.3f} comp={cs.composite:.3f}")

        decision = should_halt(
            scores,
            halt_threshold_composite=halt_composite,
            halt_threshold_arc=halt_arc,
            halt_min_n=halt_min_n,
            halt_max_n=n_max,
            has_character=has_character,
        )
        if decision.halt:
            print(f"[quality_max] HALT: {decision.reason}")
            break

    best = select_best(scores)
    if best is None:
        print("[quality_max] All candidates failed to generate.")
        return None

    # Identity floor — retry once with PuLID boost if best.arc too low
    if needs_regenerate(best, regen_floor, has_character):
        print(f"[quality_max] Best ArcFace {best.arc_score:.3f} < floor {regen_floor:.2f}. "
              f"Boosting PuLID weight +0.15 and retrying once.")
        boosted_params = dict(params)
        boosted_params["pulid_weight"] = min(1.0, params["pulid_weight"] + 0.15)
        _inject_identity(workflow, char_lora_path, face_anchor_remote, boosted_params, has_character)
        retry_seed = base_seed + n_max * 1009
        retry_wf = copy.deepcopy(workflow)
        if "25" in retry_wf:
            retry_wf["25"]["inputs"]["noise_seed"] = retry_seed
        retry_path = f"{os.path.splitext(output_filename)[0]}_retry.jpg"
        saved = _run_one_candidate(comfy, retry_wf, retry_path)
        if saved:
            retry_score = score_candidate(saved, character_image if has_character else None)
            retry_score.seed = retry_seed
            print(f"[quality_max]   retry seed={retry_seed} arc={retry_score.arc_score:.3f} "
                  f"comp={retry_score.composite:.3f}")
            if retry_score.composite > best.composite:
                best = retry_score
                candidate_paths.append(saved)

    # Promote best candidate to output_filename. Use shutil.copyfile so we don't
    # load the whole image into memory and to keep filesystem metadata semantics
    # consistent with the rest of the pipeline.
    if best.image_path != output_filename:
        shutil.copyfile(best.image_path, output_filename)

    # Cleanup losers (optional — keeping them for now in case caller wants forensics)
    print(f"[quality_max] DONE: best seed={best.seed} composite={best.composite:.3f} "
          f"arc={best.arc_score:.3f} aes={best.aesthetic_score:.3f} -> {output_filename}")
    return output_filename
