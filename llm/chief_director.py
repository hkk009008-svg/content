"""
Cinema Production Tool — Chief Director LLM (v1)
Metacognitive oversight layer that evaluates, validates, and corrects
all outputs from other LLMs in the pipeline.

Architecture:
- Sits ABOVE the scene decomposer, continuity engine, and image/video generators
- Reviews shot prompts for structural compliance before generation
- Evaluates generated images against identity requirements
- Can REJECT and REWRITE prompts that violate hard constraints
- Collects diagnostic data from all pipeline stages

Uses Anthropic Claude for superior structured reasoning and long-context analysis.
Falls back to GPT-4o if Anthropic unavailable.
"""

import os
import json
import base64
from typing import Optional, List, Dict
from pipeline_context import PIPELINE_CONTEXT
from config.settings import settings
from llm.ensemble import build_anthropic_system_blocks
from llm.negative_prompts import get_negative_prompt_for_failure


def _strip_json_fences(raw: str) -> str:
    """Strip ```json … ``` fences that LLMs emit despite instructions.

    Mirrors the shape of prompt_optimizer._strip_json_fences (canonical
    pattern: llm/prompt_optimizer.py:339). Local copy avoids importing a
    _-private cross-module symbol and keeps this a single-file change.
    """
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines)
    return raw


class ChiefDirector:
    """
    Metacognitive AI overseer for the cinema production pipeline.
    Evaluates all LLM outputs, enforces hard constraints, and makes
    autonomous decisions about quality gates.
    """

    def __init__(self, project: dict):
        self.project = project
        self.diagnostic_log: List[Dict] = []
        self.client = self._init_client()

    def _init_client(self):
        """Initialize the best available LLM client."""
        # Prefer Anthropic Claude for structured metacognitive reasoning
        anthropic_key = settings.anthropic_api_key
        if anthropic_key:
            try:
                import anthropic
                self.provider = "anthropic"
                return anthropic.Anthropic(api_key=anthropic_key)
            except ImportError:
                pass

        # Fallback to OpenAI GPT-4o
        openai_key = settings.openai_api_key
        if openai_key:
            try:
                from openai import OpenAI
                self.provider = "openai"
                return OpenAI(api_key=openai_key)
            except ImportError:
                pass

        self.provider = None
        return None

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Call the LLM with the Chief Director system prompt.

        Respects the ``creative_llm`` per-project UI knob. When set, the
        override replaces the default model for the active provider. If the
        override names a model from a *different* provider family (e.g. a
        ``gpt-*`` model while the active client is Anthropic), a warning is
        printed and the default model is used — no provider switch is
        attempted mid-call.

        Provider family detection:
          ``claude-*``             → anthropic
          ``gpt-*`` / ``o1-*`` / ``o3-*`` / ``o4-*`` → openai
        """
        if not self.client:
            return ""

        # Read the creative_llm override from project global_settings.
        override: Optional[str] = None
        if self.project:
            _gs = self.project.get("global_settings", {})
            override = _gs.get("creative_llm") or None

        try:
            if self.provider == "anthropic":
                model_id = "claude-sonnet-4-20250514"
                if override:
                    if override.startswith("claude-"):
                        model_id = override
                    else:
                        print(
                            f"   [DIRECTOR] creative_llm={override!r} doesn't match "
                            f"Anthropic provider; using default {model_id}"
                        )
                response = self.client.messages.create(
                    model=model_id,
                    max_tokens=4096,
                    system=build_anthropic_system_blocks(system_prompt),
                    messages=[{"role": "user", "content": user_prompt}],
                )
                return response.content[0].text
            else:
                model_id = "gpt-4o"
                if override:
                    _openai_prefixes = ("gpt-", "o1-", "o3-", "o4-")
                    if any(override.startswith(p) for p in _openai_prefixes):
                        model_id = override
                    else:
                        print(
                            f"   [DIRECTOR] creative_llm={override!r} doesn't match "
                            f"OpenAI provider; using default {model_id}"
                        )
                response = self.client.chat.completions.create(
                    model=model_id,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                )
                return response.choices[0].message.content
        except Exception as e:
            print(f"   [DIRECTOR] LLM call failed: {e}")
            return ""

    SYSTEM_PROMPT = """<SYSTEM_PERSONA>
You are "ChiefDirector v2.0" — a strict metacognitive oversight engine for an AI cinema production pipeline.
Your singular purpose is to evaluate, validate, and correct outputs from other LLMs in the pipeline.

CORE DIRECTIVE: You are the final quality gate. Nothing passes to generation without your approval.
TONE: Strictly analytical. Zero creative embellishment. Output structured JSON decisions only.
</SYSTEM_PERSONA>

<HARD_CONSTRAINTS>
HC1: You MUST output valid JSON. No markdown, no explanation, no conversational text.
HC2: You MUST evaluate every input against the IDENTITY FIREWALL — if any prompt describes
     a character's face, hair color, hair style, glasses, skin tone, eye color, facial structure,
     age appearance, or body shape, you MUST flag it as REJECTED and rewrite it WITHOUT those descriptions.
     The face-locking system (PuLID/Kontext) handles identity from reference photos.
     If the prompt describes the face, it CONFLICTS with face-lock and produces a DIFFERENT PERSON.
HC3: You MUST verify structural compliance — every shot prompt must contain
     [SHOT][SCENE][ACTION][OUTFIT][QUALITY] sections in that order.
HC4: You MUST verify location consistency — all shots in a scene describe the SAME location
     with identical environment details, only camera angle changes.
HC5: You MUST verify lighting consistency — all shots use identical light direction,
     color temperature, and fill ratio.
HC6: You MUST verify the [QUALITY] section contains perceptual tokens the diffusion model
     understands — NOT camera brand names. Good: "visible skin pores and subsurface scattering,
     shallow depth of field with circular bokeh, natural film grain, volumetric atmospheric lighting".
     Bad: "Shot on Arri Alexa, 4K RAW" (model doesn't know camera brands).
HC7: You MUST verify [ACTION] includes camera-facing direction — character must face the camera.
     NEVER: "turning away", "back to camera", "looking down at ground".
HC8: You MUST verify [OUTFIT] describes fabric texture and material — NOT just item names.
     Good: "red wool peacoat with visible fabric texture". Bad: "red coat".
</HARD_CONSTRAINTS>

<OUTPUT_SCHEMA>
{
  "decision": "APPROVED" | "REJECTED" | "MODIFIED",
  "violations": ["HC2: shot 0 describes 'blue eyes' — removed", "HC6: replaced camera brand with perceptual tokens"],
  "modifications": [{"shot_index": 0, "field": "prompt", "original": "...", "corrected": "..."}],
  "quality_score": 0.0-1.0,
  "reasoning": "Brief technical explanation"
}
</OUTPUT_SCHEMA>

<QUALITY_UPGRADE_RULES>
When you MODIFY a shot prompt's [QUALITY] section, upgrade it to:
"Photorealistic, visible skin pores and subsurface scattering, shallow depth of field with circular bokeh,
natural film grain ISO 400, volumetric atmospheric lighting, micro-detail in fabric weave and material texture,
no AI artifacts, no smooth plastic skin, no over-saturated colors."

When you MODIFY [OUTFIT], add fabric/material texture descriptors:
- "leather jacket" → "worn leather jacket with visible grain and stitching"
- "white shirt" → "white cotton shirt with natural creases"
- "jeans" → "dark denim jeans with faded wear pattern"
</QUALITY_UPGRADE_RULES>

<TRIPWIRES>
Before outputting, verify:
[T1] Does ANY shot prompt contain face/hair/skin/eye/body descriptions? → REJECT and rewrite.
[T2] Does every shot contain all 5 sections [SHOT][SCENE][ACTION][OUTFIT][QUALITY]? → If not, flag and fix.
[T3] Are locations identical across shots? → If not, unify to first shot's location.
[T4] Is lighting identical across shots? → If not, unify to first shot's lighting.
[T5] Is the JSON output valid and parseable? → If not, fix structure.
[T6] Does [QUALITY] contain camera brand names instead of perceptual tokens? → UPGRADE.
[T7] Does [ACTION] have the character facing the camera? → If not, fix direction.
[T8] Does [OUTFIT] include fabric texture? → If not, add material descriptors.
[T9] Is target_api appropriate for the shot type? → If not, recommend correct API.
</TRIPWIRES>

""" + PIPELINE_CONTEXT + """

<CHIEF_DIRECTOR_MUTATION_STRATEGY>
When suggesting prompt_mutation for failures:
- identity_only (face mismatch): Add "facing camera directly" to [ACTION], remove any face descriptors,
  suggest increasing PuLID weight. Do NOT change [SCENE] or [QUALITY].
- style_only (color/lighting drift): Tighten [SCENE] lighting description, add specific color temp (e.g., "4500K"),
  add "match previous shot's color grade" to [QUALITY]. Do NOT change [ACTION] or [OUTFIT].
- aggressive (both failing): Simplify entire prompt — shorter prompts give models more room.
  Remove decorative adjectives, keep only structural descriptions.
  Reduce prompt to under 100 words for maximum model compliance.
</CHIEF_DIRECTOR_MUTATION_STRATEGY>"""

    def validate_shot_prompts(self, shots: List[Dict], scene: Dict) -> Dict:
        """
        Evaluate shot prompts from the scene decomposer BEFORE they go to image generation.
        The Chief Director can APPROVE, REJECT, or MODIFY shots.

        Returns:
            Dict with decision, violations, and optionally corrected shots.
        """
        if not self.client:
            # No LLM available — pass through with warning
            print("   [DIRECTOR] No LLM available — passing shots through unvalidated")
            return {"decision": "APPROVED", "violations": [], "shots": shots}

        # Build the evaluation request
        shot_data = []
        for i, shot in enumerate(shots):
            shot_data.append({
                "index": i,
                "prompt": shot.get("prompt", ""),
                "camera": shot.get("camera", ""),
                "target_api": shot.get("target_api", ""),
            })

        user_prompt = json.dumps({
            "task": "VALIDATE_SHOT_PROMPTS",
            "scene_title": scene.get("title", ""),
            "scene_action": scene.get("action", ""),
            "scene_location": scene.get("location_id", ""),
            "shots": shot_data,
            "character_ids": scene.get("characters_present", []),
        }, indent=2)

        raw = self._call_llm(self.SYSTEM_PROMPT, user_prompt)

        # ── fence-tolerant parse with ≤1 retry-with-correction ──────────────
        # Scope: only the json.loads is guarded for retry; post-parse logic
        # exceptions (modifications/.get()) are NOT retry-eligible — they
        # indicate bugs, not transient LLM format noise.
        result = None
        for _attempt in range(2):
            try:
                result = json.loads(_strip_json_fences(raw))
                break
            except json.JSONDecodeError:
                if _attempt == 0:
                    correction = (
                        "\n\nYour previous response was not valid JSON. "
                        "Output ONLY a valid JSON object — no markdown, no prose."
                    )
                    raw = self._call_llm(self.SYSTEM_PROMPT, user_prompt + correction)
                # second attempt: fall through to result=None

        if result is None or not isinstance(result, dict):
            # Parse failed after retry, OR parsed to a non-object (a JSON array /
            # bare string — valid JSON but not a dict, possible on the Anthropic
            # path which has no response_format=json_object guard; .get() below
            # would otherwise raise AttributeError and crash the run at the
            # cinema_pipeline.py caller). Flagged deterministic fallback, not
            # silent. Fail-safe-for-throughput: APPROVED so the pipeline isn't
            # blocked, but the log line is distinct so operators can detect it.
            print("   [DIRECTOR] decision=APPROVED (parse-fallback after retry)")
            return {"decision": "APPROVED", "violations": [], "shots": shots}

        decision = result.get("decision", "APPROVED")
        violations = result.get("violations", [])
        modifications = result.get("modifications", [])

        # M-A guard: a MODIFIED verdict that flags violations but supplies NO
        # modifications is degenerate. The gate-side normalizer
        # (cinema/auto_approve.py:record_director_review_on_shots) auto-clears
        # MODIFIED → gate-APPROVED on the assumption the flagged corrections were
        # applied in-place — but with empty `modifications` nothing was corrected,
        # so auto-clear would ship a plan with open violations straight through
        # the headless PLAN gate. The normalizer can't see `modifications` (the
        # return dict is only {decision, violations, shots}), so the guard lives
        # here: downgrade to REJECTED so the gate fails fast (GateNotSatisfiedError
        # headless; regenerate / operator-review interactive) instead of silently
        # approving an uncorrected plan.
        if decision == "MODIFIED" and violations and not modifications:
            print(
                "   [DIRECTOR] MODIFIED with open violations but no modifications "
                "— downgrading to REJECTED (uncorrected plan)"
            )
            decision = "REJECTED"

        if violations:
            print(f"   [DIRECTOR] {decision}: {len(violations)} violation(s) found")
            for v in violations[:3]:
                print(f"      - {v}")

        # Apply modifications if any
        if modifications and decision == "MODIFIED":
            for mod in modifications:
                idx = mod.get("shot_index", -1)
                if 0 <= idx < len(shots) and "corrected" in mod:
                    field = mod.get("field", "prompt")
                    shots[idx][field] = mod["corrected"]
                    print(f"   [DIRECTOR] Shot {idx} '{field}' corrected")

        self.diagnostic_log.append({
            "stage": "shot_validation",
            "scene": scene.get("title"),
            "decision": decision,
            "violations": violations,
            "score": result.get("quality_score", 0),
        })

        print(f"   [DIRECTOR] decision={decision}")
        return {"decision": decision, "violations": violations, "shots": shots}

    def evaluate_generation_quality(
        self,
        image_path: str,
        reference_path: str,
        identity_result=None,
        identity_score: float = 0.0,
        shot_prompt: str = "",
        scene_context: str = "",
        coherence_result=None,
    ) -> Dict:
        """
        Post-generation evaluation with diagnostic-aware reasoning.

        Accepts either:
        - identity_result: IdentityValidationResult (rich diagnostics) — preferred
        - identity_score: float (legacy fallback)

        Also accepts coherence_result for 2x2 mutation matrix:
        |              | Identity PASS | Identity FAIL |
        | Coherent     | ACCEPT        | Mutate: identity only |
        | Incoherent   | Mutate: style | Mutate: aggressive    |
        """
        # Extract score from rich result if available
        if identity_result is not None:
            identity_score = identity_result.overall_score
            threshold = identity_result.threshold_used
        else:
            threshold = 0.70

        # A skipped identity result has overall_score=None (couldn't be checked):
        # treat as non-blocking — don't drive an identity mutation off a non-score.
        if identity_score is None:
            identity_passed = True
        else:
            identity_passed = identity_score >= threshold

        # Check coherence
        coherent = True
        if coherence_result is not None:
            coherent = coherence_result.overall_coherence_score >= 0.6

        # 2x2 decision matrix
        if identity_passed and coherent:
            return {"decision": "ACCEPT", "mutation": None}

        if not self.client:
            if not identity_passed:
                return {"decision": "RETRY", "mutation": None, "mutation_level": 1}
            return {"decision": "ACCEPT", "mutation": None}

        # Build diagnostic context for the LLM
        diagnostics = {}
        primary_reason_value: Optional[str] = None
        if identity_result is not None and hasattr(identity_result, "character_results"):
            for cid, cr in identity_result.character_results.items():
                reason_value = cr.primary_failure_reason.value
                diagnostics[cid] = {
                    "name": cr.character_name,
                    "best_similarity": round(cr.best_similarity, 3),
                    "mean_similarity": round(cr.mean_similarity, 3),
                    "failure_reason": reason_value,
                    "suggested_pulid_delta": cr.suggested_pulid_adjustment,
                    "frames_with_face": sum(1 for f in cr.frame_results if f.face_detected),
                    "total_frames_sampled": len(cr.frame_results),
                }
                # Capture the first failing character's reason for negative-prompt lookup.
                # "passed" is the success sentinel — skip it; keep the first actual failure.
                if primary_reason_value is None and reason_value != "passed":
                    primary_reason_value = reason_value

        coherence_info = {}
        if coherence_result is not None:
            coherence_info = {
                "overall_score": round(coherence_result.overall_coherence_score, 3),
                "color_drift": round(coherence_result.color_drift, 3),
                "lighting_consistency": round(coherence_result.lighting_consistency, 3),
                "recommendations": coherence_result.recommendations,
            }

        mutation_context = "identity_only" if coherent else ("style_only" if identity_passed else "aggressive")

        eval_prompt = json.dumps({
            "task": "DIAGNOSE_GENERATION_FAILURE",
            "identity_score": identity_score,
            "threshold": threshold,
            "identity_passed": identity_passed,
            "coherent": coherent,
            "mutation_context": mutation_context,
            "character_diagnostics": diagnostics,
            "coherence_info": coherence_info,
            "shot_prompt": shot_prompt[:500],
            "scene_context": scene_context[:200],
        }, indent=2)

        diagnosis_system = (
            "You are ChiefDirector diagnosing a generation failure and deciding how to mutate the prompt. "
            "The user message contains all diagnostic context (scores, thresholds, mutation_context). "
            "Respond with valid JSON only — no prose, no markdown fences.\n\n"
            "PIPELINE KNOWLEDGE:\n"
            "- PuLID handles face-lock from reference photos (weight 0.0-1.0)\n"
            "- Identity validation uses DeepFace GhostFaceNet embeddings (cosine similarity)\n"
            "- Common false negatives: FACE_ANGLE_EXTREME (profile view), SMALL_FACE_REGION (wide shot)\n"
            "  → These are NOT identity failures — do NOT suggest face-related mutations for them\n"
            "- Coherence scoring: 40% color consistency + 30% lighting + 30% composition\n"
            "- img2img chaining uses denoise 0.30 for consecutive shots — lower = more consistent\n"
            "- If failure_reason is WRONG_PERSON, the reference images may be conflicting\n\n"
            "MUTATION RULES:\n"
            'If mutation_context is "identity_only":\n'
            '  → Add "facing camera directly" to [ACTION]\n'
            "  → Remove any accidental face/hair descriptions\n"
            "  → Suggest PuLID weight increase (+0.10)\n"
            "  → SHORTEN prompt to reduce model confusion\n"
            "  → Do NOT touch [SCENE] or [QUALITY]\n\n"
            'If mutation_context is "style_only":\n'
            "  → Tighten [SCENE] with specific color temperature and fill ratio\n"
            '  → Add "match previous shot palette" to [QUALITY]\n'
            "  → Suggest tightening denoise (img2img) to 0.25\n"
            "  → Do NOT touch [ACTION] or [OUTFIT]\n\n"
            'If mutation_context is "aggressive":\n'
            "  → Simplify ENTIRE prompt to under 80 words\n"
            "  → Keep only: shot type, environment, action, outfit material\n"
            "  → Remove all decorative adjectives\n"
            "  → Shorter prompts = more model compliance on retries\n\n"
            "Output JSON:\n"
            '{\n'
            '  "decision": "RETRY" | "ACCEPT_LENIENT" | "FAIL",\n'
            '  "diagnosis": "Brief technical reason",\n'
            '  "prompt_mutation": "Specific rewrite instructions",\n'
            '  "mutation_level": 1 | 2 | 3,\n'
            '  "mutation_focus": "identity" | "style" | "both"\n'
            "}"
        )

        raw = self._call_llm(diagnosis_system, eval_prompt)

        try:
            result = json.loads(_strip_json_fences(raw))

            # Append the negative-prompt hint to the LLM's mutation instructions.
            # Opt-in: unknown reasons and "passed" return "" and are silently skipped.
            # Note: primary_reason_value is the FIRST failing character's reason
            # (see capture loop above). The mapping is scalar by design — if
            # multiple characters fail with different reasons, only the first
            # drives the negative prompt for this take.
            negative_phrase = get_negative_prompt_for_failure(primary_reason_value)
            if negative_phrase and result.get("prompt_mutation"):
                result["prompt_mutation"] = (
                    result["prompt_mutation"]
                    + f"\nNegative prompt: {negative_phrase}"
                )
                phrase_display = negative_phrase[:60] + (
                    "..." if len(negative_phrase) > 60 else ""
                )
                print(f"   [NEG-PROMPT] {primary_reason_value} → {phrase_display}")
            elif negative_phrase:
                # Phrase available but LLM returned no prompt_mutation to enrich
                # (e.g., decision=ACCEPT_LENIENT). Visible-skip log so an operator
                # debugging "why isn't the negative prompt being used?" can spot
                # the path. Not an error — the LLM's decision wins.
                print(
                    f"   [NEG-PROMPT] skipped ({primary_reason_value}): "
                    f"no prompt_mutation in LLM result"
                )

            self.diagnostic_log.append({
                "stage": "identity_evaluation",
                "score": identity_score,
                "coherent": coherent,
                "decision": result.get("decision"),
                "diagnosis": result.get("diagnosis"),
                "mutation_focus": result.get("mutation_focus", mutation_context),
            })
            return result
        except Exception:
            level = 1 if identity_score > 0.55 else (2 if identity_score > 0.40 else 3)
            return {"decision": "RETRY", "mutation": None, "mutation_level": level}

    def get_diagnostic_summary(self) -> str:
        """Return a summary of all diagnostic decisions made during this generation."""
        if not self.diagnostic_log:
            return "No diagnostic data collected."

        summary = []
        for entry in self.diagnostic_log:
            summary.append(
                f"  [{entry.get('stage')}] {entry.get('decision', 'N/A')} "
                f"(score={entry.get('score', 'N/A')})"
            )
        return "\n".join(summary)
