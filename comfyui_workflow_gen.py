"""
Cinema Production Tool — Codestral-Powered Dynamic ComfyUI Workflow Generator

Instead of using a static pulid.json template with parameter overrides,
this module uses Codestral 25.08 (a code-specialized LLM from Mistral)
to generate and modify ComfyUI API-format workflow JSON based on shot
requirements.

Falls back to direct template modification when no LLM API key is available.
"""

import os
import json
import random
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Node reference — documents key node IDs in the base PuLID/FLUX workflow
# and the parameters each node exposes for modification.
# ---------------------------------------------------------------------------
WORKFLOW_NODE_REFERENCE: Dict[str, Dict] = {
    "8": {
        "class_type": "VAEDecodeTiled",
        "description": "Decodes latent samples to pixel space (tiled for OOM safety).",
        "params": ["tile_size", "overlap", "temporal_size", "temporal_overlap"],
    },
    "9": {
        "class_type": "SaveImage",
        "description": "Saves the final output image to disk.",
        "params": ["filename_prefix"],
    },
    "10": {
        "class_type": "VAELoader",
        "description": "Loads the VAE model (ae.safetensors for FLUX).",
        "params": ["vae_name"],
    },
    "11": {
        "class_type": "DualCLIPLoader",
        "description": "Loads T5-XXL + CLIP-L text encoders for FLUX.",
        "params": ["clip_name1", "clip_name2", "type", "device"],
    },
    "13": {
        "class_type": "SamplerCustomAdvanced",
        "description": "Main sampler node — connects noise, guider, sampler, sigmas, latent.",
        "params": [],
    },
    "16": {
        "class_type": "KSamplerSelect",
        "description": "Selects the sampling algorithm (e.g. dpmpp_2m, euler, etc.).",
        "params": ["sampler_name"],
    },
    "17": {
        "class_type": "BasicScheduler",
        "description": "Controls step count, scheduler type, and denoise strength.",
        "params": ["scheduler", "steps", "denoise"],
    },
    "22": {
        "class_type": "BasicGuider",
        "description": "Connects model and conditioning for guided diffusion.",
        "params": [],
    },
    "25": {
        "class_type": "RandomNoise",
        "description": "Generates random noise from a seed for reproducible generation.",
        "params": ["noise_seed"],
    },
    "60": {
        "class_type": "FluxGuidance",
        "description": "Sets the FLUX guidance scale (analogous to CFG for SD).",
        "params": ["guidance"],
    },
    "93": {
        "class_type": "LoadImage",
        "description": "Loads the face reference image for PuLID identity lock.",
        "params": ["image"],
    },
    "97": {
        "class_type": "PulidInsightFaceLoader",
        "description": "Loads InsightFace model for face analysis (PuLID pipeline).",
        "params": ["provider"],
    },
    "99": {
        "class_type": "PulidModelLoader",
        "description": "Loads the PuLID adapter model weights.",
        "params": ["pulid_file"],
    },
    "100": {
        "class_type": "ApplyPulid",
        "description": "Applies PuLID face identity transfer to the diffusion model.",
        "params": ["weight", "method", "start_at", "end_at"],
    },
    "101": {
        "class_type": "PulidEvaClipLoader",
        "description": "Loads EVA-CLIP for PuLID face embedding extraction.",
        "params": [],
    },
    "102": {
        "class_type": "EmptyLatentImage",
        "description": "Creates an empty latent tensor at the desired resolution.",
        "params": ["width", "height", "batch_size"],
    },
    "112": {
        "class_type": "UNETLoader",
        "description": "Loads the FLUX diffusion backbone (fp8 quantised).",
        "params": ["unet_name", "weight_dtype"],
    },
    "122": {
        "class_type": "CLIPTextEncode",
        "description": "Encodes the text prompt via CLIP/T5 into conditioning tensors.",
        "params": ["text"],
    },
    "301": {
        "class_type": "PerturbedAttentionGuidance",
        "description": "PAG — sharpens detail by perturbing self-attention during sampling.",
        "params": ["scale"],
    },
    "500": {
        "class_type": "ImageUpscaleWithModel",
        "description": "Upscales the decoded image using Real-ESRGAN 4x.",
        "params": [],
    },
    "501": {
        "class_type": "UpscaleModelLoader",
        "description": "Loads the Real-ESRGAN upscale model.",
        "params": ["model_name"],
    },
    "502": {
        "class_type": "ImageScale",
        "description": "Rescales the upscaled image to final cinema resolution (2688x1536).",
        "params": ["upscale_method", "width", "height", "crop"],
    },
}

# Resolution presets keyed by shot orientation
RESOLUTION_PRESETS = {
    "landscape": (1344, 768),
    "portrait_orientation": (768, 1344),
    "square": (1024, 1024),
}

# Required node class types that any valid workflow must contain
REQUIRED_NODE_CLASSES = {
    "SamplerCustomAdvanced",  # a sampler
    "UNETLoader",             # a model loader
    "CLIPTextEncode",         # a CLIP encoder
}

# The system prompt sent to Codestral / OpenAI for workflow modification
_LLM_SYSTEM_PROMPT = """You are a ComfyUI workflow expert. You modify API-format workflow JSON \
for specific shot requirements. You ONLY output valid JSON — no markdown, \
no explanations, no code fences.

Rules:
- Node 100 (ApplyPulid): set weight, start_at, end_at based on shot type.
  Portraits need higher weight (0.9-1.0), wide shots lower (0.5-0.7), \
  landscapes should disable PuLID (weight=0).
- Node 60 (FluxGuidance): set guidance. Range 2.5-4.5. Higher for detail, \
  lower for creative freedom.
- Node 17 (BasicScheduler): set steps (15-30) and scheduler \
  (sgm_uniform recommended). More steps = finer detail, slower.
- Node 25 (RandomNoise): set noise_seed to a random integer.
- Node 122 (CLIPTextEncode): set text to the shot prompt.
- Node 102 (EmptyLatentImage): set width/height. \
  Landscape shots: 1344x768. Portrait orientation: 768x1344.
- Node 16 (KSamplerSelect): set sampler_name (dpmpp_2m recommended).
- Node 301 (PerturbedAttentionGuidance): set scale (2.0-4.0). \
  Higher for landscapes/detail, lower for motion/action.
- Preserve all node connections (arrays like ["13", 0]).
- Do NOT add or remove nodes — only modify parameter values.
- Return the complete modified workflow JSON."""


class ComfyUIWorkflowGenerator:
    """
    Generates and modifies ComfyUI API-format workflow JSON using either
    Codestral (Mistral's code LLM) or a static template fallback.
    """

    def __init__(self, base_workflow_path: str = "pulid.json"):
        """
        Load the base workflow JSON if it exists and catalogue available node types.

        Args:
            base_workflow_path: Path to the base ComfyUI workflow JSON file.
                               Relative paths are resolved from the Content directory.
        """
        self.base_workflow: Optional[Dict] = None
        self.available_node_types: Dict[str, str] = {}

        # Resolve relative paths against the directory this file lives in
        if not os.path.isabs(base_workflow_path):
            base_dir = os.path.dirname(os.path.abspath(__file__))
            base_workflow_path = os.path.join(base_dir, base_workflow_path)

        if os.path.exists(base_workflow_path):
            with open(base_workflow_path, "r") as f:
                self.base_workflow = json.load(f)
            # Build a map of node_id -> class_type from the loaded workflow
            for node_id, node_data in self.base_workflow.items():
                if isinstance(node_data, dict) and "class_type" in node_data:
                    self.available_node_types[node_id] = node_data["class_type"]
            print(f"[WorkflowGen] Loaded base workflow with {len(self.available_node_types)} nodes")
        else:
            print(f"[WorkflowGen] Base workflow not found at {base_workflow_path} — will use empty template")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_workflow(
        self,
        shot_spec: Dict,
        base_workflow: Optional[Dict] = None,
    ) -> Dict:
        """
        Generate a modified ComfyUI workflow JSON tailored to the shot spec.

        Uses Codestral / OpenAI API when an API key is available; otherwise
        falls back to deterministic template modification.

        Args:
            shot_spec: Dict with keys:
                - shot_type: str  ("portrait", "medium", "wide", "action", "landscape")
                - prompt: str  (the text prompt for CLIP encoding)
                - characters_in_frame: list[str]
                - camera: str  (camera/lens description)
                - visual_effect: str  (optional stylistic note)
                - target_api: str  (video API target, e.g. "KLING_NATIVE")
                - pulid_weight: float  (0.0 - 1.0)
                - guidance: float  (FLUX guidance scale)
                - steps: int  (sampling steps)
            base_workflow: Optional override for the base workflow dict.
                           Defaults to self.base_workflow loaded at init.

        Returns:
            Modified workflow dict ready to be submitted to the ComfyUI API.
        """
        workflow = json.loads(json.dumps(base_workflow or self.base_workflow or {}))

        if not workflow:
            raise ValueError(
                "No base workflow available. Provide a base_workflow argument or "
                "ensure pulid.json exists at the configured path."
            )

        # Try LLM-based generation first
        api_key, api_base, model = self._resolve_llm_config()

        if api_key:
            try:
                workflow = self._generate_via_llm(workflow, shot_spec, api_key, api_base, model)
                valid, errors = self.validate_workflow(workflow)
                if valid:
                    print(f"[WorkflowGen] LLM-generated workflow validated OK")
                    return workflow
                else:
                    print(f"[WorkflowGen] LLM workflow failed validation: {errors}")
                    print(f"[WorkflowGen] Falling back to static template modification")
            except Exception as e:
                print(f"[WorkflowGen] LLM generation failed ({e}), using static fallback")

        # Static fallback — apply parameters directly
        workflow = json.loads(json.dumps(base_workflow or self.base_workflow))
        workflow = self._apply_shot_params(workflow, shot_spec)
        return workflow

    def modify_workflow(self, workflow: Dict, modifications: Dict) -> Dict:
        """
        Apply a dict of node_id -> parameter modifications to an existing workflow.

        Example:
            modifications = {
                "100": {"weight": 0.9, "start_at": 0.25},
                "60":  {"guidance": 3.5},
                "17":  {"steps": 25},
            }

        Args:
            workflow: The ComfyUI API-format workflow dict to modify.
            modifications: Mapping of node_id (str) to a dict of param -> value.

        Returns:
            The modified workflow dict (modified in place and also returned).
        """
        for node_id, params in modifications.items():
            if node_id not in workflow:
                print(f"[WorkflowGen] Warning: node {node_id} not found in workflow, skipping")
                continue
            if "inputs" not in workflow[node_id]:
                print(f"[WorkflowGen] Warning: node {node_id} has no 'inputs' key, skipping")
                continue
            for param_name, param_value in params.items():
                workflow[node_id]["inputs"][param_name] = param_value
        return workflow

    def validate_workflow(self, workflow: Dict) -> Tuple[bool, List[str]]:
        """
        Validate that a workflow dict is structurally sound.

        Checks:
        1. Workflow is a non-empty dict.
        2. Every node has 'inputs' and 'class_type' keys.
        3. Required node class types are present (sampler, model loader, CLIP encoder).
        4. Node connection references (arrays like ["13", 0]) point to existing nodes.

        Returns:
            (valid, errors) — valid is True if no errors found; errors is a list
            of human-readable strings describing each problem.
        """
        errors: List[str] = []

        # Check 1: basic structure
        if not isinstance(workflow, dict) or len(workflow) == 0:
            errors.append("Workflow is empty or not a dict")
            return False, errors

        # Check 2: every node has required keys
        present_classes = set()
        for node_id, node_data in workflow.items():
            if not isinstance(node_data, dict):
                errors.append(f"Node {node_id}: value is not a dict")
                continue
            if "class_type" not in node_data:
                errors.append(f"Node {node_id}: missing 'class_type'")
            else:
                present_classes.add(node_data["class_type"])
            if "inputs" not in node_data:
                errors.append(f"Node {node_id}: missing 'inputs'")

        # Check 3: required classes
        for required in REQUIRED_NODE_CLASSES:
            if required not in present_classes:
                errors.append(f"Missing required node class: {required}")

        # Check 4: connection integrity
        node_ids = set(workflow.keys())
        for node_id, node_data in workflow.items():
            if not isinstance(node_data, dict) or "inputs" not in node_data:
                continue
            for param_name, param_value in node_data["inputs"].items():
                if isinstance(param_value, list) and len(param_value) == 2:
                    ref_id = str(param_value[0])
                    if ref_id not in node_ids:
                        errors.append(
                            f"Node {node_id}.inputs.{param_name}: "
                            f"references non-existent node {ref_id}"
                        )

        return len(errors) == 0, errors

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_llm_config(self) -> Tuple[Optional[str], str, str]:
        """
        Determine which API key and endpoint to use for LLM-based generation.

        Priority:
        1. MISTRAL_API_KEY -> Codestral endpoint
        2. OPENAI_API_KEY  -> OpenAI-compatible endpoint with codestral model
        3. None            -> static fallback

        Returns:
            (api_key, api_base_url, model_name) or (None, "", "") if no key found.
        """
        mistral_key = os.environ.get("MISTRAL_API_KEY")
        if mistral_key:
            return mistral_key, "https://codestral.mistral.ai/v1", "codestral-2501"

        openai_key = os.environ.get("OPENAI_API_KEY")
        if openai_key:
            return openai_key, "https://api.openai.com/v1", "codestral-2501"

        return None, "", ""

    def _generate_via_llm(
        self,
        workflow: Dict,
        shot_spec: Dict,
        api_key: str,
        api_base: str,
        model: str,
    ) -> Dict:
        """
        Send the base workflow + shot spec to the LLM and parse the returned JSON.

        Uses the openai SDK which is compatible with both OpenAI and Mistral/Codestral
        endpoints.

        Raises:
            Exception on network / parsing failures so the caller can fall back.
        """
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=api_base)

        user_prompt = (
            "Modify this ComfyUI API-format workflow JSON for the following shot requirements.\n\n"
            f"--- SHOT SPEC ---\n{json.dumps(shot_spec, indent=2)}\n\n"
            f"--- NODE REFERENCE ---\n{json.dumps(WORKFLOW_NODE_REFERENCE, indent=2)}\n\n"
            f"--- BASE WORKFLOW ---\n{json.dumps(workflow, indent=2)}\n\n"
            "Return ONLY the modified workflow JSON. No markdown fences, no explanation."
        )

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _LLM_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,  # low temp for deterministic JSON output
            max_tokens=8192,
        )

        raw = response.choices[0].message.content.strip()

        # Strip markdown code fences if the LLM wrapped them despite instructions
        if raw.startswith("```"):
            lines = raw.split("\n")
            # Remove first and last fence lines
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw = "\n".join(lines)

        result = json.loads(raw)

        if not isinstance(result, dict):
            raise ValueError(f"LLM returned {type(result).__name__}, expected dict")

        return result

    def _apply_shot_params(self, workflow: Dict, shot_spec: Dict) -> Dict:
        """
        Static fallback that applies shot parameters to workflow nodes directly.
        Mirrors the logic in workflow_selector.apply_workflow_params but driven
        by the shot_spec dict rather than pre-defined templates.

        This is used when no LLM API key is available.
        """
        # --- Node 122 (CLIPTextEncode): set the text prompt ---
        if "122" in workflow:
            prompt = shot_spec.get("prompt", "")
            if prompt:
                workflow["122"]["inputs"]["text"] = prompt

        # --- Node 100 (ApplyPulid): face identity lock ---
        if "100" in workflow:
            pulid_weight = shot_spec.get("pulid_weight")
            if pulid_weight is not None:
                workflow["100"]["inputs"]["weight"] = pulid_weight

            # Derive start_at / end_at from shot_type if not explicitly provided
            shot_type = shot_spec.get("shot_type", "medium")
            start_at_defaults = {
                "portrait": 0.2,
                "medium": 0.25,
                "wide": 0.35,
                "action": 0.3,
                "landscape": 0.0,
            }
            end_at_defaults = {
                "portrait": 1.0,
                "medium": 1.0,
                "wide": 0.9,
                "action": 1.0,
                "landscape": 0.0,
            }
            workflow["100"]["inputs"]["start_at"] = shot_spec.get(
                "pulid_start_at", start_at_defaults.get(shot_type, 0.3)
            )
            workflow["100"]["inputs"]["end_at"] = shot_spec.get(
                "pulid_end_at", end_at_defaults.get(shot_type, 1.0)
            )

        # --- Node 60 (FluxGuidance): guidance scale ---
        if "60" in workflow:
            guidance = shot_spec.get("guidance")
            if guidance is not None:
                workflow["60"]["inputs"]["guidance"] = guidance

        # --- Node 17 (BasicScheduler): steps and scheduler ---
        if "17" in workflow:
            steps = shot_spec.get("steps")
            if steps is not None:
                workflow["17"]["inputs"]["steps"] = steps
            scheduler = shot_spec.get("scheduler", "sgm_uniform")
            workflow["17"]["inputs"]["scheduler"] = scheduler

        # --- Node 16 (KSamplerSelect): sampler algorithm ---
        if "16" in workflow:
            sampler = shot_spec.get("sampler", "dpmpp_2m")
            workflow["16"]["inputs"]["sampler_name"] = sampler

        # --- Node 102 (EmptyLatentImage): resolution from shot type ---
        if "102" in workflow:
            shot_type = shot_spec.get("shot_type", "medium")
            # Default to landscape orientation; portrait_orientation only for
            # explicitly vertical shots
            if shot_type in ("portrait",) and shot_spec.get("orientation") == "vertical":
                width, height = RESOLUTION_PRESETS["portrait_orientation"]
            elif shot_type == "landscape":
                width, height = RESOLUTION_PRESETS["landscape"]
            else:
                width, height = RESOLUTION_PRESETS["landscape"]

            # Allow explicit override
            width = shot_spec.get("width", width)
            height = shot_spec.get("height", height)
            workflow["102"]["inputs"]["width"] = width
            workflow["102"]["inputs"]["height"] = height

        # --- Node 25 (RandomNoise): random seed ---
        if "25" in workflow:
            seed = shot_spec.get("seed", random.randint(1, 2**32 - 1))
            workflow["25"]["inputs"]["noise_seed"] = seed

        # --- Node 301 (PAG): detail enhancement ---
        if "301" in workflow:
            pag_scale = shot_spec.get("pag_scale")
            if pag_scale is not None:
                workflow["301"]["inputs"]["scale"] = pag_scale

        return workflow


# ---------------------------------------------------------------------------
# Convenience functions for use by other modules
# ---------------------------------------------------------------------------

def generate_workflow_for_shot(shot_spec: Dict, base_workflow_path: str = "pulid.json") -> Dict:
    """
    One-shot helper: create a generator and produce a workflow in one call.

    Args:
        shot_spec: Shot specification dict (see ComfyUIWorkflowGenerator.generate_workflow).
        base_workflow_path: Path to the base ComfyUI workflow JSON.

    Returns:
        Modified workflow dict.
    """
    gen = ComfyUIWorkflowGenerator(base_workflow_path=base_workflow_path)
    return gen.generate_workflow(shot_spec)


# ---------------------------------------------------------------------------
# CLI for quick testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Example: generate a portrait workflow
    example_spec = {
        "shot_type": "portrait",
        "prompt": (
            "[SHOT] extreme close-up, 85mm lens, shallow depth of field "
            "[ACTION] character looks directly into camera with subtle smile "
            "[QUALITY] photorealistic, cinematic lighting, film grain"
        ),
        "characters_in_frame": ["character_01"],
        "camera": "85mm f/1.4, shallow DoF",
        "visual_effect": "warm golden-hour backlight",
        "target_api": "KLING_NATIVE",
        "pulid_weight": 1.0,
        "guidance": 3.5,
        "steps": 25,
    }

    gen = ComfyUIWorkflowGenerator()
    workflow = gen.generate_workflow(example_spec)

    valid, errors = gen.validate_workflow(workflow)
    print(f"\nWorkflow valid: {valid}")
    if errors:
        for err in errors:
            print(f"  - {err}")

    # Show key modified nodes
    for nid in ("122", "100", "60", "17", "25", "102"):
        if nid in workflow:
            print(f"  Node {nid} ({workflow[nid].get('class_type', '?')}): "
                  f"{json.dumps(workflow[nid]['inputs'], indent=4)}")
