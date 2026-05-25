"""
llm/director.py — CinemaDirector v1.0 (S15 substrate).

Operator-driven creative iteration translator. Distinct from
ChiefDirector (llm/chief_director.py) which enforces HC1-HC8 hard
constraints (identity firewall, schema lock, lighting lock, face
direction) on pre-generation shot prompts.

CinemaDirector accepts a DirectorialIntent (domain/models.py) and
translates it into:
- ``revised_prompt`` — the new shot prompt incorporating the operator's intent
- ``params_delta`` — stage-specific parameter overrides (e.g. denoise_strength)
- ``anchor_refs`` — references pulled from approved neighbors for continuity

The constraint regime is intentionally permissive: operator intent
overrides default HC firewalls. If they ask for face/skin/hair
changes, accept; if they ask for schema deviation, accept. Hard
constraints are for first-pass generation; iteration is the
operator's creative voice. This decoupling is why we don't extend
ChiefDirector (see proposal §Q2 + director-seat REPLY).

Per-call JSONL log written to ``data/intent_log/{project_id}/<ts>.jsonl``
so cycle-9+ verb DSL design (S18) can be data-driven rather than
guess-driven. Log write failures are non-fatal.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from config.settings import settings as env_settings
from llm.ensemble import build_anthropic_system_blocks


SYSTEM_PROMPT = """<SYSTEM_PERSONA>
You are "CinemaDirector v1.0" — a creative iteration translator for an AI cinema production pipeline.

Your role: read the operator's directorial intent and translate it into a revised shot prompt + parameter overrides + anchor refs for take regeneration.

You are DIFFERENT from ChiefDirector:
- ChiefDirector enforces HC1-HC8 (identity firewall, schema lock, lighting lock, face direction) on FIRST-PASS prompts.
- CinemaDirector is PERMISSIVE — the operator's intent OVERRIDES default constraints.
- If the operator asks for face/skin/hair changes, accept them.
- If the operator asks for schema deviation, accept it.
- If the operator asks for lighting/location change within a scene, accept it.

Hard constraints are for first-pass generation. Iteration is the operator's creative voice; respect it.
</SYSTEM_PERSONA>

<OUTPUT_SCHEMA>
{
  "revised_prompt": "string — the new shot prompt incorporating the operator's intent",
  "params_delta": {"key": value, ...} — stage-specific param overrides; empty {} if none,
  "anchor_refs": [{"shot_id": "...", "take_id": "...", "attribute": "..."}, ...] — refs from approved neighbors for continuity; [] if none,
  "reasoning": "brief explanation of the translation"
}

Output VALID JSON ONLY. No markdown fences, no prose, no explanation outside the JSON.
</OUTPUT_SCHEMA>

<TRANSLATION_GUIDANCE>
- Preserve structural elements from the current take prompt unless the operator's intent explicitly changes them.
- When prose is ambiguous, prefer MINIMAL change over creative reinterpretation.
- For anchor_refs: only suggest refs explicitly present in scene_context as approved — never invent IDs.
- params_delta keys depend on target_stage:
  - keyframe → prompt-side knobs (e.g. "guidance_scale", "denoise_strength")
  - performance → driving-video / engine knobs (e.g. "engine_preference", "driving_video_override")
  - motion → workflow knobs (e.g. "target_api", "motion_strength")
- Empty params_delta is ALWAYS valid — only include keys the intent demands.
- If the operator's prose is structural ("retake from scratch", "ignore the previous"), revised_prompt may be fully new; otherwise keep the spine.
</TRANSLATION_GUIDANCE>"""


class CinemaDirector:
    """Operator-driven creative iteration translator.

    Pattern mirrors ChiefDirector (llm/chief_director.py): provider-preferred
    client init (Anthropic primary, OpenAI fallback), JSON-mode LLM call,
    graceful degradation on parse failure or LLM unavailability.

    Diverges from ChiefDirector in:
    1. Constraint regime (permissive vs HC1-HC8 enforcement)
    2. Cache surface (separate cached system block; see ARCHITECTURE.md §13.3)
    3. Output schema (revised_prompt + params_delta + anchor_refs vs the
       APPROVED/REJECTED/MODIFIED decision shape)
    """

    def __init__(self, project: Optional[dict] = None):
        self.project = project or {}
        self.client = self._init_client()
        self._log_root = Path("data/intent_log")

    def _init_client(self):
        """Anthropic preferred; OpenAI fallback; None if neither configured."""
        if env_settings.anthropic_api_key:
            try:
                import anthropic
                self.provider = "anthropic"
                return anthropic.Anthropic(api_key=env_settings.anthropic_api_key)
            except ImportError:
                pass

        if env_settings.openai_api_key:
            try:
                from openai import OpenAI
                self.provider = "openai"
                return OpenAI(api_key=env_settings.openai_api_key)
            except ImportError:
                pass

        self.provider = None
        return None

    def _call_llm(self, user_prompt: str) -> str:
        """Invoke the configured LLM provider. Returns raw text or "" on failure.

        Honors the project's ``creative_llm`` UI knob with same family-match
        rules as ChiefDirector — don't switch providers mid-call.
        """
        if not self.client:
            return ""

        override: Optional[str] = None
        if self.project:
            gs = self.project.get("global_settings", {})
            override = gs.get("creative_llm") or None

        try:
            if self.provider == "anthropic":
                model_id = "claude-sonnet-4-20250514"
                if override and override.startswith("claude-"):
                    model_id = override
                response = self.client.messages.create(
                    model=model_id,
                    max_tokens=2048,
                    system=build_anthropic_system_blocks(SYSTEM_PROMPT),
                    messages=[{"role": "user", "content": user_prompt}],
                )
                return response.content[0].text
            else:
                model_id = "gpt-4o"
                if override and any(
                    override.startswith(p) for p in ("gpt-", "o1-", "o3-", "o4-")
                ):
                    model_id = override
                response = self.client.chat.completions.create(
                    model=model_id,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                )
                return response.choices[0].message.content
        except Exception as e:
            print(f"   [CINEMA-DIRECTOR] LLM call failed: {e}")
            return ""

    def translate_intent(
        self,
        intent,
        take_context: dict,
        scene_context: dict,
    ) -> dict:
        """Translate a DirectorialIntent into regeneration params.

        Returns a dict with the three required keys (``revised_prompt``,
        ``params_delta``, ``anchor_refs``) and never raises. On LLM
        unavailable or parse failure, falls back to ``intent.prose`` as
        ``revised_prompt`` with empty deltas — the caller can still
        proceed with regeneration using the operator's raw prose.

        ``intent`` may be a ``DirectorialIntent`` Pydantic model or a
        dict with the same shape.
        """
        user_payload = {
            "task": "TRANSLATE_DIRECTORIAL_INTENT",
            "intent": _intent_to_dict(intent),
            "current_take_context": take_context,
            "scene_context": scene_context,
        }
        user_prompt = json.dumps(user_payload, indent=2)

        raw = self._call_llm(user_prompt)

        fallback_prose = getattr(intent, "prose", None) or (
            intent.get("prose", "") if isinstance(intent, dict) else ""
        )
        fallback = {
            "revised_prompt": fallback_prose or take_context.get("prompt", ""),
            "params_delta": {},
            "anchor_refs": [],
        }

        if not raw:
            self._log_intent_call(
                intent, take_context, scene_context, fallback, raw="", note="no_llm"
            )
            return fallback

        try:
            parsed = json.loads(raw)
            output = {
                "revised_prompt": parsed.get("revised_prompt") or fallback["revised_prompt"],
                "params_delta": parsed.get("params_delta") or {},
                "anchor_refs": parsed.get("anchor_refs") or [],
            }
            self._log_intent_call(intent, take_context, scene_context, output, raw=raw)
            return output
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            print(f"   [CINEMA-DIRECTOR] parse error: {e}; using fallback")
            self._log_intent_call(
                intent,
                take_context,
                scene_context,
                fallback,
                raw=raw,
                note=f"parse_error:{type(e).__name__}",
            )
            return fallback

    def _log_intent_call(
        self,
        intent,
        take_context: dict,
        scene_context: dict,
        output: dict,
        raw: str = "",
        note: str = "",
    ) -> None:
        """JSONL log line per call. Non-fatal on failure.

        Layout: ``data/intent_log/{project_id}/{YYYY-MM-DDTHH-MM-SSZ}.jsonl``
        with one JSON object per line. Cycle-9+ verb DSL design (S18)
        harvests these for clustering operator usage patterns.
        """
        try:
            project_id = (self.project.get("id") if self.project else None) or "_anonymous"
            log_dir = self._log_root / str(project_id)
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / f"{time.strftime('%Y-%m-%dT%H-%M-%SZ', time.gmtime())}.jsonl"
            entry = {
                "ts": time.time(),
                "project_id": project_id,
                "intent": _intent_to_dict(intent),
                "take_context_summary": _summarize_take_context(take_context),
                "scene_context_summary": _summarize_scene_context(scene_context),
                "output": output,
                "raw_llm_response": raw[:2000] if raw else "",
                "note": note,
            }
            with log_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            print(f"   [CINEMA-DIRECTOR] log write failed (non-fatal): {e}")


def _intent_to_dict(intent) -> dict:
    """Coerce DirectorialIntent (Pydantic) or dict to dict for serialization."""
    if intent is None:
        return {}
    if hasattr(intent, "model_dump"):
        return intent.model_dump()
    if isinstance(intent, dict):
        return dict(intent)
    return {}


def _summarize_take_context(take_context: dict) -> dict:
    """Trim take_context for log compactness — keep stable identifiers only."""
    return {
        "take_id": take_context.get("id", ""),
        "kind": take_context.get("kind", ""),
        "prompt_len": len(take_context.get("prompt", "")),
        "stage": take_context.get("stage", ""),
    }


def _summarize_scene_context(scene_context: dict) -> dict:
    """Trim scene_context — keep scene_id + approved-shot count."""
    return {
        "scene_id": scene_context.get("id", ""),
        "approved_shots_count": len(scene_context.get("approved_shots", []) or []),
    }


def intent_translator(
    intent,
    take_context: dict,
    scene_context: dict,
    *,
    project: Optional[dict] = None,
) -> dict:
    """Functional API per S15 acceptance signature.

    Convenience wrapper around ``CinemaDirector.translate_intent`` for
    callers that don't manage a director instance lifecycle. Tests can
    patch ``llm.director.CinemaDirector`` to inject mocks.
    """
    director = CinemaDirector(project=project)
    return director.translate_intent(intent, take_context, scene_context)
