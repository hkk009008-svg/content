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

import concurrent.futures
import copy
import hashlib
import json
import os
import random
import shutil
import threading
import time
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

if TYPE_CHECKING:
    from cinema.context import PipelineContext

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
from phase_c_assembly import RunPodComfyUI, ImageGenResult

from cinema.aspect import portrait_swap, DEFAULT_ASPECT_RATIO


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


# ---------------------------------------------------------------------------
# MaxTier UI overlay validation
# ---------------------------------------------------------------------------
# Bounds mirror two React panels:
#   * web/src/components/settings/AdvancedSection.tsx::MaxTierComfyControls
#     (17 sampler / CN / post-pass knobs)
#   * web/src/components/settings/MaxQualityTierSection.tsx
#     (7 best-of-N halt knobs + the halt_rule radio group)
# Keep in sync when UI ranges change. Out-of-range numeric values are clamped
# (the UI can still send 99 via the JSON API even when the slider stops at 5);
# unknown enum / wrong-type values are rejected so the template default wins,
# rather than passing junk to ComfyUI where it would either silently corrupt
# the image or surface as a server error the max-tier fall-through masks.
#
# Schema entry forms:
#   ("numeric", type, min, max)
#   ("enum", *allowed_values)
#   ("bool",)
_MAX_TIER_KNOB_SCHEMA: Dict[str, Tuple] = {
    # Sampling / guidance
    "slg_scale":                 ("numeric", float, 0.0, 5.0),
    "freeu_b1":                  ("numeric", float, 1.0, 1.8),
    "freeu_b2":                  ("numeric", float, 1.0, 1.8),
    "freeu_s1":                  ("numeric", float, 0.0, 1.5),
    "freeu_s2":                  ("numeric", float, 0.0, 1.5),
    "ays_steps":                 ("numeric", int,   15,  40),
    "detail_daemon_amount":      ("numeric", float, 0.0, 1.0),
    # ControlNet channel strengths (UI key — overlay re-maps to cn_*_strength)
    "controlnet_canny_strength": ("numeric", float, 0.0, 0.5),
    "controlnet_pose_strength":  ("numeric", float, 0.0, 0.6),
    "controlnet_tile_strength":  ("numeric", float, 0.0, 0.5),
    # Redux + Hires fix + FaceDetailer + SUPIR
    "redux_strength":            ("enum", "high", "medium", "low"),
    "hires_fix_enabled":         ("bool",),
    "hires_fix_denoise":         ("numeric", float, 0.40, 0.6),  # floor 0.40: pod proved 0.25 disintegrates (2026-06-09)
    "hires_fix_steps":           ("numeric", int,   5,   40),
    "face_detailer_enabled":     ("bool",),
    "face_detailer_guide_size":  ("enum", 512, 1024, 2048),
    "supir_enabled":             ("bool",),
    "supir_steps":               ("numeric", int,   20,  100),
    # Adaptive-halt knobs (MaxQualityTierSection.tsx). Arc threshold floors
    # at 0.50 while composite floors at 0.70 because raw ArcFace scores live
    # lower than composite (0.6·arc + 0.4·aesthetic) — the looser arc bound
    # lets operators express identity-tolerant policies.
    "max_candidate_count":          ("numeric", int,   1,    16),
    "max_candidate_batch":          ("numeric", int,   1,    8),
    "max_halt_threshold_composite": ("numeric", float, 0.70, 1.00),
    "max_halt_threshold_arc":       ("numeric", float, 0.50, 1.00),
    "max_halt_min_n":               ("numeric", int,   1,    8),
    "max_regenerate_floor_arc":     ("numeric", float, 0.50, 1.00),
    "max_halt_rule":                ("enum", "composite_only", "conjunctive", "budget_only"),
    # Per-batch candidate parallelism (added 2026-05-24). Default 1 preserves
    # the historic sequential behavior; up to 4 concurrent workers overlap the
    # ComfyUI submit/poll/download cycle on the same pod. ComfyUI itself queues
    # prompts, so on a single-GPU pod the model still runs one-at-a-time — the
    # wall-clock win is from overlapping the wait + scoring phases.
    "max_quality_parallel_workers": ("numeric", int,   1,    4),
}


def _validate_overlay_value(ui_key: str, value):
    """Validate a UI overlay value against `_MAX_TIER_KNOB_SCHEMA`.

    Returns `(accepted, warning)`:
      * `accepted` — value to write into `params` (possibly clamped). `None`
        means skip the override (template default wins).
      * `warning` — human-readable string when the value was modified or
        rejected; `None` on clean pass-through.

    Unknown `ui_key` passes through unchanged so a knob added to the overlay
    blocks before its schema entry lands still applies (rather than being
    silently dropped).
    """
    schema = _MAX_TIER_KNOB_SCHEMA.get(ui_key)
    if schema is None:
        return value, None
    kind = schema[0]
    if kind == "numeric":
        _, typ, lo, hi = schema
        # bool is a subclass of int; reject explicitly so freeu_b1=True
        # doesn't silently coerce to 1.0.
        if isinstance(value, bool):
            return None, f"{ui_key}={value!r} is bool, expected {typ.__name__}; skipped"
        try:
            v = typ(value)
        except (TypeError, ValueError):
            return None, f"{ui_key}={value!r} not coercible to {typ.__name__}; skipped"
        if v < lo:
            return typ(lo), f"{ui_key}={value} below min {lo}; clamped to {lo}"
        if v > hi:
            return typ(hi), f"{ui_key}={value} above max {hi}; clamped to {hi}"
        return v, None
    if kind == "enum":
        allowed = schema[1:]
        if value in allowed:
            return value, None
        return None, f"{ui_key}={value!r} not in {list(allowed)}; skipped"
    if kind == "bool":
        if isinstance(value, bool):
            return value, None
        return None, f"{ui_key}={value!r} not bool; skipped"
    return value, None  # unreachable for current schema shapes


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

def _apply_model_precision(workflow: dict, precision: str):
    """Re-point the FLUX UNet (112) + T5 text encoder (11) to fp8 weights when
    precision='fp8', so the fp16-canonical pulid_max.json runs on an fp8-
    provisioned pod (the filenames setup_runpod.sh downloads). precision='fp16'
    (the true-max flag) leaves the fp16 defaults, which setup_runpod.sh --max-fp16
    provisions. Guarded + idempotent: only swaps a UNETLoader / DualCLIPLoader
    whose name still references fp16, so a HiDream-swapped node 112 or an
    already-fp8 graph is left untouched.
    """
    if precision != "fp8":
        return
    n112 = workflow.get("112")
    if (isinstance(n112, dict) and n112.get("class_type") == "UNETLoader"
            and "fp16" in str(n112.get("inputs", {}).get("unet_name", ""))):
        n112["inputs"]["unet_name"] = "FLUX1/flux1-dev-fp8.safetensors"
    n11 = workflow.get("11")
    if (isinstance(n11, dict) and n11.get("class_type") == "DualCLIPLoader"
            and "fp16" in str(n11.get("inputs", {}).get("clip_name1", ""))):
        n11["inputs"]["clip_name1"] = "t5xxl_fp8_e4m3fn.safetensors"


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
        # FaceDetailer(600) reads the popped LoRA stack (600.clip<-[700,1]) and
        # ReActor(610) face-swaps a popped source face (610.source_image<-[93,0]);
        # a no-character shot has no face to detail or swap. Drop both face passes,
        # feeding the SUPIR/save chain from the base VAEDecode (same fallbacks as
        # the pruning_rules 600/610 rows). Without this they survive on a full pod
        # with [700,1]/[93,0] links reachable from SaveImage -> /prompt validation
        # reject -> silent production-tier fallback for landscape/establishing max
        # shots. (Ported from max-tier Lane V F1, 4b20f1b; the FLUX-incompat
        # 100-bridge half is N/A here -- this 56-node version has no such loop and
        # the 100->112 rewire above already handles every [100, slot] model ref.)
        _prune_node(workflow, "600", rewire_to=("902", 0) if "902" in workflow else ("8", 0))
        _prune_node(workflow, "610", rewire_to=("902", 0) if "902" in workflow else ("8", 0))

    # No init image -> drop CN, Redux, img2img, latent blend
    if not has_init:
        for nid in ("400", "401", "402", "403", "404", "410", "411", "412",
                    "420", "421", "422", "431", "432", "800", "801", "803", "804", "810",
                    "200", "201", "250"):
            _prune_node(workflow, nid)
        # Rewire BasicGuider.conditioning straight to FluxGuidance
        if "22" in workflow:
            workflow["22"]["inputs"]["conditioning"] = ["60", 0]
        # FaceDetailer(600) reads the same pruned Redux conditioning [804,0] as
        # the guider above (for BOTH its positive and negative inputs); mirror the
        # 22->[60,0] rewire so a character text-to-image shot (has_character, no
        # init) doesn't leave 600.positive/negative -> [804,0] dangling -> /prompt
        # reject -> silent production-tier fallback. No-character shots prune 600
        # entirely in the has_character branch above, so this only fires for
        # character + no-init. (Rule #13 symmetric completion of the 22 rewire.)
        if "600" in workflow:
            workflow["600"]["inputs"]["positive"] = ["60", 0]
            workflow["600"]["inputs"]["negative"] = ["60", 0]
        # Rewire sampler latent to EmptyLatentImage
        if "13" in workflow:
            workflow["13"]["inputs"]["latent_image"] = ["102", 0]

    # FLUX-incompatibility prunes (independent of pod availability): these
    # advanced guidance patches pass /prompt validation but raise at RUNTIME on
    # this ComfyUI's FLUX forward (verified empirically against the live pod):
    #   - FreeU_V2 (772): reads model_config.unet_config["model_channels"] which
    #     FLUX's transformer config doesn't expose -> KeyError 'model_channels'.
    #   - SkipLayerGuidanceDiT (770) / PerturbedAttentionGuidance (301) /
    #     DifferentialDiffusion (740): inject a 'timestep_zero_index' kwarg this
    #     build's FLUX forward_orig() rejects -> TypeError at the sampler.
    # Chain is 100(PuLID)->301->770->772->740->22(BasicGuider). Drop each and
    # bridge to its nearest surviving upstream so BasicGuider/FaceDetailer still
    # receive the PuLID-patched model (PuLID + FaceDetailer + ReActor + SUPIR
    # carry the quality). Ported from max-tier-provisioning-2026-06-01; the
    # no-char path pops 100, so bridge to base UNet 112 when 100 is already gone.
    for _bad, _up in (("772", "770"), ("770", "301"), ("301", "100"), ("740", "100")):
        if _bad in workflow:
            _tgt = _up if _up in workflow else ("112" if "100" not in workflow else "100")
            _prune_node(workflow, _bad, rewire_to=(_tgt, 0))

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


# NOTE(P1-1 s2): defined-but-unwired until Task 7 wires it into
# generate_ai_broll_max — delete this note in that commit.
def _assemble_max_prompt(prompt: str, char_lora_trigger: Optional[str],
                          secondary_chars: Optional[list]) -> str:
    """Prepend LoRA trigger tokens (training-caption convention: token first).

    Primary trigger first, then each secondary's — but a secondary token only
    when that secondary actually carries a LoRA (a trigger without its LoRA in
    the chain is noise). No tokens -> prompt unchanged (every pre-slice-2
    call path).
    """
    triggers = [char_lora_trigger] if char_lora_trigger else []
    for entry in secondary_chars or []:
        if entry.get("trigger") and entry.get("lora_path"):
            triggers.append(entry["trigger"])
    if not triggers:
        return prompt
    return f"{', '.join(triggers)}, {prompt}"


def _inject_identity(workflow: dict, char_lora: Optional[str], face_anchor_remote: Optional[str],
                      params: dict, has_character: bool,
                      char_lora_strength: Optional[float] = None):
    """Wire LoRA name + face ref into the identity stack.

    char_lora_strength: per-character validated strength from project settings.
        When provided (not None), overrides the tier-default params["lora_strength_model"].
        None (the default) → use params["lora_strength_model"] unchanged (backward-compat).
    """
    if not has_character:
        return
    if "700" in workflow:
        if char_lora:
            # ComfyUI's LoraLoader expects a loras/-relative name, not an absolute path.
            # pod-side placement of the file into ComfyUI's loras/ dir under this
            # basename is the slice-2 POD-SESSION step (spec §7.2).
            workflow["700"]["inputs"]["lora_name"] = os.path.basename(char_lora)
            # Use the validated per-character strength if provided; else fall back to
            # the tier-default model/clip values SEPARATELY (preserves the original
            # independent-clip behavior — they aren't always equal, cf. _max_lora_test).
            # `is not None` so strength=0.0 is honored (not treated as falsy → tier default).
            s_model = char_lora_strength if char_lora_strength is not None else params.get("lora_strength_model", 1.0)
            s_clip = char_lora_strength if char_lora_strength is not None else params.get("lora_strength_clip", 1.0)
            workflow["700"]["inputs"]["strength_model"] = s_model
            workflow["700"]["inputs"]["strength_clip"] = s_clip
        else:
            # No trained per-char LoRA -> drop LoraLoader(700) entirely and feed
            # PuLID(100)/CLIP consumers from the base loaders, so the graph
            # validates without a PLACEHOLDER_char.safetensors file (LoraLoader
            # would otherwise reject the missing file). Identity is carried by
            # PuLID(100) alone, applied on the base UNet; a per-char LoRA would
            # add fidelity -- this is an explicit LoRA-less degradation, NOT full
            # max. 700's consumers: 100.model<-[700,0], 122.clip<-[700,1],
            # 600.clip<-[700,1] (600 only if FaceDetailer survived).
            print("[quality_max] no per-char LoRA -> running LoRA-less (PuLID-only "
                  "identity; train a per-char LoRA for full max fidelity)")
            _prune_node(workflow, "700")
            if "100" in workflow:
                workflow["100"]["inputs"]["model"] = ["112", 0]
            if "122" in workflow:
                workflow["122"]["inputs"]["clip"] = ["11", 0]
            if "600" in workflow:
                workflow["600"]["inputs"]["clip"] = ["11", 0]
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
        # Dead fallbacks mirror MAX_QUALITY_TEMPLATES (steps 40, cfg 2.8); never reached on the
        # production path (templates always carry these keys). Clean same-base A/B 2026-06-09
        # (seed 741305880): cfg 2.8 arc 0.7939 >= 2.0 arc 0.7886; 4.0 sweep-disfavored. Aligning
        # the unreachable defaults to the real template values (not an arbitrary 50/4.0) kills the
        # footgun a hand-built param dict would otherwise hit. (Templates unchanged: the A/B gave
        # no evidence to lower cfg.)
        workflow["502"]["inputs"]["steps"] = params.get("supir_steps", 40)
        workflow["502"]["inputs"]["cfg_scale_start"] = params.get("supir_cfg_scale", 2.8)
        workflow["502"]["inputs"]["cfg_scale_end"] = params.get("supir_cfg_scale", 2.8)

    # Final downsample resolution
    if "950" in workflow:
        w, h = params.get("final_resolution", (3840, 2160))
        workflow["950"]["inputs"]["width"] = w
        workflow["950"]["inputs"]["height"] = h

    # Hires-fix Pass-2: run node 901 (refine pass) at a gentler denoise for photorealism.
    # Baseline points 901's sigmas at node 17 @ denoise=1.0 -> over-processed/painterly.
    # POD-VALIDATED 2026-06-09 (Novita RTX 6000 Ada): denoise=0.40 fires + holds identity
    # (arc ~0.83, 4K master); the floor matters -> denoise=0.25 catastrophically
    # disintegrates (arc ~0.48). See docs/pipeline_status.toml [hires_fix] (status=wired).
    if params.get("hires_fix_enabled", True) and "901" in workflow and "17" in workflow:
        workflow["18"] = copy.deepcopy(workflow["17"])
        workflow["18"]["inputs"]["denoise"] = params.get("hires_fix_denoise", 0.40)
        workflow["18"]["inputs"]["steps"] = params.get("hires_fix_steps", 18)
        workflow["901"]["inputs"]["sigmas"] = ["18", 0]


def _inject_aspect(workflow: dict, aspect_ratio: Optional[str]) -> None:
    """Transpose the max-tier latent + final-scale nodes to portrait when 9:16.

    Reads each node's CURRENT (landscape) width/height and rotates them via
    portrait_swap, so the tier keeps its tuned pixel budget — just rotated.
    Node 102 = EmptyLatentImage (1024×576); node 950 = ImageScale final
    (3840×2160). Landscape / None / unknown → no-op (portrait_swap returns
    the dims unchanged). Robust to template dim changes (reads, not hardcodes).
    Must run AFTER _inject_post_passes (which sets node 950's dims).
    """
    for node_id in ("102", "950"):
        node = workflow.get(node_id)
        if not isinstance(node, dict):
            continue
        ins = node.get("inputs", {})
        w, h = ins.get("width"), ins.get("height")
        if isinstance(w, int) and isinstance(h, int):
            ins["width"], ins["height"] = portrait_swap(w, h, aspect_ratio)


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
    char_lora_strength: Optional[float] = None,
    char_lora_trigger: Optional[str] = None,
    secondary_chars: Optional[List[dict]] = None,
    style_reference: Optional[str] = None,
    shot_hint: Optional[dict] = None,
    ctx: Optional["PipelineContext"] = None,
) -> Optional["ImageGenResult"]:
    """N=8 adaptive best-of generation. Returns ImageGenResult or None.

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

    # Read the project's aspect ratio for portrait-aware generation.
    # Single function-scope import for get_project_setting (None-safe: ctx=None →
    # returns DEFAULT_ASPECT_RATIO); the conditional override blocks below reuse it.
    from cinema.context import get_project_setting
    aspect_ratio = get_project_setting(ctx, "aspect_ratio", DEFAULT_ASPECT_RATIO)

    # ---- Per-project UI overrides (from ctx.global_settings) ----
    # 7 MaxQualityTier halt knobs — override the shot-type defaults above.
    # Same validation contract as the 17 ComfyControls below: clamp numeric
    # out-of-range inputs, reject unknown enums/wrong types. The JSON API can
    # send any value past the React slider bounds.
    if ctx is not None:
        for ui_key, param_key in (
            ("max_candidate_count",          "candidate_count"),
            ("max_candidate_batch",          "candidate_batch"),
            ("max_halt_threshold_composite", "halt_threshold_composite"),
            ("max_halt_threshold_arc",       "halt_threshold_arc"),
            ("max_halt_min_n",               "halt_min_n"),
            ("max_regenerate_floor_arc",     "regenerate_floor_arc"),
            ("max_halt_rule",                "halt_rule"),
            ("max_quality_parallel_workers", "parallel_workers"),
        ):
            override = get_project_setting(ctx, ui_key, None)
            if override is None:
                continue
            accepted, warning = _validate_overlay_value(ui_key, override)
            if warning:
                print(f"[quality_max] UI overlay: {warning}")
            if accepted is not None:
                params[param_key] = accepted

        # 17 MaxTierComfyControls — overlay into params so the existing
        # _inject_sampling / _inject_conditioning / _inject_post_passes
        # helpers pick them up automatically.  UI key → params key mapping.
        # Values are passed through _validate_overlay_value to clamp numeric
        # out-of-range inputs and reject unknown enums/wrong types — the JSON
        # API can send any value past the React slider bounds.
        for ui_key, param_key in (
            # Sampling / guidance controls
            ("slg_scale",                "slg_scale"),
            ("freeu_b1",                 "freeu_b1"),
            ("freeu_b2",                 "freeu_b2"),
            ("freeu_s1",                 "freeu_s1"),
            ("freeu_s2",                 "freeu_s2"),
            ("ays_steps",                "ays_steps"),
            ("detail_daemon_amount",     "detail_daemon_amount"),
            # ControlNet channel strengths (UI name differs from params key)
            ("controlnet_canny_strength", "cn_canny_strength"),
            ("controlnet_pose_strength",  "cn_pose_strength"),
            ("controlnet_tile_strength",  "cn_tile_strength"),
            # Redux style reference strength
            ("redux_strength",           "redux_strength"),
            # Hires-fix pass
            ("hires_fix_enabled",        "hires_fix_enabled"),
            ("hires_fix_denoise",        "hires_fix_denoise"),
            ("hires_fix_steps",          "hires_fix_steps"),
            # FaceDetailer
            ("face_detailer_enabled",    "face_detailer_enabled"),
            ("face_detailer_guide_size", "face_detailer_guide_size"),
            # SUPIR upscaler
            ("supir_enabled",            "supir_enabled"),
            ("supir_steps",              "supir_steps"),
        ):
            override = get_project_setting(ctx, ui_key, None)
            if override is None:
                continue
            accepted, warning = _validate_overlay_value(ui_key, override)
            if warning:
                print(f"[quality_max] UI overlay: {warning}")
            if accepted is not None:
                params[param_key] = accepted

        # img2img_denoise is nested under continuity_options (not a flat UI key),
        # so it isn't in the loop above. Overlay it onto denoise_default, which
        # quality_max applies at the BasicScheduler denoise node (~line 481).
        # Mirrors the standard-path wire at phase_c_assembly.py:276-281 (same
        # [0.2, 0.6] slider clamp). Completes the max-tier half of img2img_denoise.
        _co = (ctx.global_settings or {}).get("continuity_options", {})
        _i2i = _co.get("img2img_denoise") if isinstance(_co, dict) else None
        if isinstance(_i2i, (int, float)):
            params["denoise_default"] = max(0.2, min(0.6, float(_i2i)))

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

    # Model precision: pulid_max.json is fp16-canonical. Re-point UNet/T5 to fp8
    # for the fp8-provisioned pod (the default first-run path); fp16 (true max)
    # is opt-in via params['max_model_precision'] or $MAX_MODEL_PRECISION and
    # needs setup_runpod.sh --max-fp16. No-op if HiDream swapped node 112.
    max_precision = (params.get("max_model_precision")
                     or os.environ.get("MAX_MODEL_PRECISION", "fp8"))
    _apply_model_precision(workflow, max_precision)
    print(f"[quality_max] model precision: {max_precision}"
          + (" (UNet/T5 re-pointed to fp8 weights)" if max_precision == "fp8"
             else " (fp16 canonical; needs --max-fp16 provisioning)"))

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
    _inject_identity(workflow, char_lora_path, face_anchor_remote, params, has_character,
                     char_lora_strength=char_lora_strength)
    _inject_conditioning(workflow, prompt, init_remote, style_remote, params, has_character)
    _inject_sampling(workflow, params)
    _inject_latent_source(workflow, init_remote, params)
    _inject_post_passes(workflow, params, available)
    _inject_aspect(workflow, aspect_ratio)  # transpose nodes 102+950 once; deepcopy loop inherits

    # ---- Best-of-N adaptive halt loop ----
    n_max = int(params.get("candidate_count", 8))
    batch = int(params.get("candidate_batch", 4))
    halt_min_n = int(params.get("halt_min_n", 4))
    halt_composite = float(params.get("halt_threshold_composite", 0.92))
    halt_arc = float(params.get("halt_threshold_arc", 0.85))
    regen_floor = float(params.get("regenerate_floor_arc", 0.82))
    halt_rule = params.get("halt_rule", "composite_only")

    scores: List[CandidateScore] = []
    candidate_paths: List[str] = []
    base_seed = seed if seed is not None else random.randint(1, 2**31 - 1)
    # Step-3 (2026-05-24) per-batch parallelism. Default 1 = identical
    # sequential behavior. Validation already clamped to [1, 4] in the overlay
    # block above. ThreadPoolExecutor.map yields in submission order so the
    # print + scores ordering stays stable across workers settings.
    parallel_workers = max(1, min(4, int(params.get("parallel_workers", 1))))
    # Bundle-A 1.1 (2026-05-24): rolling-stats success_rate gate. Previously
    # every candidate scored with threshold=0.0 -> validate_image marked it
    # passed=True regardless of similarity, polluting the rolling history that
    # feeds get_adaptive_pulid_weight. Pass the project's identity acceptance
    # bar so passed=True means "would have been acceptable as the final shot".
    if ctx is not None:
        identity_threshold = float(get_project_setting(ctx, "identity_strictness", 0.60))
    else:
        identity_threshold = 0.60

    def _run_candidate(task):
        cand_index, cand_seed, cand_path, wf = task
        saved = _run_one_candidate(comfy, wf, cand_path)
        if not saved:
            return None
        cs = score_candidate(
            saved,
            character_image if has_character else None,
            threshold=identity_threshold,
        )
        cs.seed = cand_seed
        return (cand_index, cand_seed, saved, cs)

    while len(scores) < n_max:
        # Generate next batch (or remainder)
        remaining = n_max - len(scores)
        this_batch = min(batch, remaining)

        # Pre-compute seeds + paths so parallel workers don't race on len(scores).
        starting_index = len(scores)
        tasks = []
        for i in range(this_batch):
            cand_index = starting_index + i
            cand_seed = base_seed + cand_index * 1009  # deterministic spread
            cand_path = f"{os.path.splitext(output_filename)[0]}_cand{cand_index}.jpg"
            wf = copy.deepcopy(workflow)
            if "25" in wf:
                wf["25"]["inputs"]["noise_seed"] = cand_seed
            tasks.append((cand_index, cand_seed, cand_path, wf))

        with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_workers) as pool:
            for result in pool.map(_run_candidate, tasks):
                if result is None:
                    continue
                _idx, cand_seed, saved, cs = result
                candidate_paths.append(saved)
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
            halt_rule=halt_rule,
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
        _inject_identity(workflow, char_lora_path, face_anchor_remote, boosted_params, has_character,
                         char_lora_strength=char_lora_strength)
        retry_seed = base_seed + n_max * 1009
        retry_wf = copy.deepcopy(workflow)
        if "25" in retry_wf:
            retry_wf["25"]["inputs"]["noise_seed"] = retry_seed
        retry_path = f"{os.path.splitext(output_filename)[0]}_retry.jpg"
        saved = _run_one_candidate(comfy, retry_wf, retry_path)
        if saved:
            retry_score = score_candidate(
                saved,
                character_image if has_character else None,
                threshold=identity_threshold,
            )
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
    # Max tier runs entirely on the ComfyUI pod (N=8 PuLID best-of); a non-None
    # return is always a pod generation, so the provenance is QUALITY_MAX.
    return ImageGenResult(output_filename, "QUALITY_MAX")
