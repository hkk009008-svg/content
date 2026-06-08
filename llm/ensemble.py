"""
Competitive multi-LLM generation and judging system for the cinema pipeline.

Generates candidate outputs from multiple models in parallel, then uses a
judge model to select the best result.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
from dataclasses import dataclass, field
from typing import Any
from config.settings import settings as env_settings   # aliased to avoid clash with the per-instance `settings: dict` ctor arg below


def _strip_json_fences(raw: str) -> str:
    """Strip ```json … ``` fences that LLMs emit despite instructions.

    Mirrors the canonical pattern at llm/prompt_optimizer.py:339 and the
    copy in llm/chief_director.py.  Local copy avoids importing a _-private
    cross-module symbol and keeps this a single-file change.

    NOTE: This is the 3rd copy of this helper (prompt_optimizer + chief_director
    + here). DRY dedup (extract to llm/_utils.py or similar) is tracked as a
    P2/P3 follow-up; out of scope for this dispatch.
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


def build_anthropic_system_blocks(text: str) -> list[dict[str, Any]]:
    """Wrap a stable system prompt for Anthropic prompt caching.

    Anthropic's prompt-caching API requires the system parameter to be a
    list of content blocks; cache_control={"type": "ephemeral"} on the
    first block opts the system content into the cache.

    Callers MUST pass a stable string (no per-call interpolation) for
    caching to actually hit. Per-shot data belongs in the user message,
    not here.
    """
    return [
        {
            "type": "text",
            "text": text,
            "cache_control": {"type": "ephemeral"},
        }
    ]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class EnsembleResult:
    """Result of a competitive multi-model generation round."""
    winner_index: int
    winner_content: Any
    scores: list[float]
    reasoning: str
    candidates: list[Any]
    models_used: list[str]
    judge_model: str


# ---------------------------------------------------------------------------
# Default model rosters per task type
# ---------------------------------------------------------------------------

_DEFAULT_MODELS: dict[str, list[str]] = {
    "script": ["claude-sonnet-4-6", "gpt-4o"],
    "decompose": ["gpt-4o", "claude-sonnet-4-6"],
    "default": ["claude-sonnet-4-6", "gpt-4o"],
}

_DEFAULT_JUDGE = "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# LLMEnsemble
# ---------------------------------------------------------------------------

class LLMEnsemble:
    """Orchestrates competitive generation across multiple LLM providers."""

    def __init__(self, settings: dict | None = None) -> None:
        # Lazy-import clients so the module can be imported even when the
        # underlying SDKs are not installed (they just need to be present
        # at call time).
        import anthropic
        import openai

        self.anthropic_client = anthropic.Anthropic(
            api_key=env_settings.anthropic_api_key,
            timeout=120.0,
        )
        self.openai_client = openai.OpenAI(
            api_key=env_settings.openai_api_key,
            timeout=120.0,
        )

        # Gemini is optional — only construct the client when a key is
        # configured. The judge_map below references "gemini-pro" which
        # selects this branch; without a key the judge dispatch raises
        # at call time rather than silently falling through to OpenAI.
        gemini_key = env_settings.gemini_api_key or env_settings.google_api_key
        if gemini_key:
            from google import genai  # google-genai SDK, already in env via veo_native
            from google.genai import types as genai_types
            self.gemini_client = genai.Client(api_key=gemini_key, http_options=genai_types.HttpOptions(timeout=120_000))
        else:
            self.gemini_client = None

        # Apply settings overrides
        self.competitive_enabled = True
        self.judge_model_override: str | None = None
        if settings:
            self.competitive_enabled = settings.get("competitive_generation", True)
            judge_pref = settings.get("quality_judge_llm", "auto")
            if judge_pref != "auto":
                judge_map = {
                    # claude-opus-4-8 is the current Opus alias (verified vs the
                    # model catalog 2026-06-08; the previous target
                    # claude-opus-4-20250918 was never a valid API id → 404 at
                    # judge dispatch).
                    "claude-opus": "claude-opus-4-8",
                    "gpt-4o": "gpt-4o",
                    "gemini-pro": "gemini-2.5-pro",
                }
                self.judge_model_override = judge_map.get(judge_pref)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def competitive_generate(
        self,
        task_type: str,
        system_prompt: str,
        user_prompt: str,
        models: list[str] | None = None,
        judge_model: str | None = None,
        json_mode: bool = False,
        tool_schema: dict | None = None,
    ) -> EnsembleResult:
        """Generate outputs from multiple models in parallel, then judge.

        Parameters
        ----------
        task_type:
            Key into ``_DEFAULT_MODELS`` (e.g. ``"script"``, ``"decompose"``).
        system_prompt:
            System-level instruction shared by all candidates.
        user_prompt:
            The user-facing prompt that each model receives.
        models:
            Explicit list of model IDs.  ``None`` falls back to defaults
            based on *task_type*.
        judge_model:
            Model used for judging.  Defaults to ``_DEFAULT_JUDGE``.
        json_mode:
            When ``True``, OpenAI calls use ``response_format={"type": "json_object"}``.
        tool_schema:
            If provided, Anthropic calls use ``tools=[tool_schema]`` and
            the tool_use result is extracted as the candidate output.

        Returns
        -------
        EnsembleResult
        """
        if models is None:
            models = _DEFAULT_MODELS.get(task_type, _DEFAULT_MODELS["default"])

        # Generate from every model in parallel.
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(models)) as pool:
            futures = {
                pool.submit(
                    self._generate_single,
                    model,
                    system_prompt,
                    user_prompt,
                    json_mode,
                    tool_schema,
                ): model
                for model in models
            }
            results: list[tuple[str, Any]] = []
            for future in concurrent.futures.as_completed(futures, timeout=120):
                results.append(future.result(timeout=120))

        # Preserve original model ordering (as_completed may reorder).
        result_by_model = {model: output for model, output in results}
        ordered_models: list[str] = []
        ordered_candidates: list[Any] = []
        for m in models:
            ordered_models.append(m)
            ordered_candidates.append(result_by_model.get(m))

        # Judge the candidates.
        winner_index, scores, reasoning = self._judge(
            ordered_candidates,
            ordered_models,
            system_prompt,
            judge_model=judge_model,
        )

        return EnsembleResult(
            winner_index=winner_index,
            winner_content=ordered_candidates[winner_index],
            scores=scores,
            reasoning=reasoning,
            candidates=ordered_candidates,
            models_used=ordered_models,
            judge_model=judge_model or _DEFAULT_JUDGE,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_single(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
        tool_schema: dict | None = None,
    ) -> tuple[str, Any]:
        """Route a generation request to the correct provider.

        Returns ``(model, output_content)`` on success or
        ``(model, None)`` on failure.
        """
        try:
            if model.startswith("claude"):
                return self._generate_anthropic(
                    model, system_prompt, user_prompt, tool_schema,
                )
            elif model.startswith("gpt") or model.startswith("o4"):
                return self._generate_openai(
                    model, system_prompt, user_prompt, json_mode,
                )
            elif model.startswith("gemini"):
                return self._generate_gemini(
                    model, system_prompt, user_prompt, json_mode,
                )
            else:
                # Unknown provider -- attempt OpenAI-compatible call.
                return self._generate_openai(
                    model, system_prompt, user_prompt, json_mode,
                )
        except Exception as exc:  # noqa: BLE001
            print(f"[LLMEnsemble] Generation failed for {model}: {exc}")
            return (model, None)

    def _generate_anthropic(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        tool_schema: dict | None = None,
    ) -> tuple[str, Any]:
        """Call the Anthropic messages API."""
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": 4096,
            "system": build_anthropic_system_blocks(system_prompt),
            "messages": [{"role": "user", "content": user_prompt}],
        }
        if tool_schema is not None:
            kwargs["tools"] = [tool_schema]

        response = self.anthropic_client.messages.create(**kwargs)

        if hasattr(response, "usage"):
            cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
            cache_creation = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
            input_tokens = getattr(response.usage, "input_tokens", 0) or 0
            if cache_read > 0 or cache_creation > 0:
                print(
                    f"   [LLM-CACHE] model={model} input={input_tokens} "
                    f"cache_read={cache_read} cache_creation={cache_creation}"
                )

        # Extract content -- prefer tool_use blocks when a schema was given.
        if tool_schema is not None:
            for block in response.content:
                if block.type == "tool_use":
                    return (model, block.input)
            # Fallback to text if no tool_use block found.

        text_parts = [
            block.text for block in response.content if hasattr(block, "text")
        ]
        return (model, "\n".join(text_parts))

    def _generate_openai(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
    ) -> tuple[str, Any]:
        """Call the OpenAI chat completions API."""
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self.openai_client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        return (model, content)

    def _generate_gemini(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
    ) -> tuple[str, Any]:
        """Call the Google Gemini generateContent API.

        Matches the OpenAI/Anthropic helpers' return shape: ``(model, text)``.
        Uses the new google-genai SDK (genai.Client) — same one used by
        veo_native.py and phase_c_vision.validate_scene_coherence_vision.
        """
        if self.gemini_client is None:
            raise RuntimeError(
                "Gemini judge requested but no GEMINI_API_KEY / GOOGLE_API_KEY configured"
            )

        from google.genai import types

        config_kwargs: dict[str, Any] = {"system_instruction": system_prompt}
        if json_mode:
            config_kwargs["response_mime_type"] = "application/json"

        response = self.gemini_client.models.generate_content(
            model=model,
            contents=user_prompt,
            config=types.GenerateContentConfig(**config_kwargs),
        )
        return (model, response.text)

    # ------------------------------------------------------------------
    # Judging
    # ------------------------------------------------------------------

    def _judge(
        self,
        candidates: list[Any],
        models: list[str],
        system_prompt: str,
        judge_model: str | None = None,
    ) -> tuple[int, list[float], str]:
        """Use a judge model to pick the best candidate.

        Returns ``(winner_index, scores, reasoning)``.
        """
        judge_model = judge_model or _DEFAULT_JUDGE

        # Filter out failed candidates (None).
        valid: list[tuple[int, str, Any]] = [
            (i, m, c) for i, (m, c) in enumerate(zip(models, candidates)) if c is not None
        ]

        if not valid:
            # All candidates failed.
            return (0, [0.0] * len(candidates), "All candidates failed to generate output.")

        if len(valid) == 1:
            # Only one succeeded -- auto-win.
            idx = valid[0][0]
            scores = [0.0] * len(candidates)
            scores[idx] = 8.0
            return (idx, scores, f"Only one candidate ({valid[0][1]}) produced output; auto-win.")

        # Build the judging prompt.
        candidate_blocks: list[str] = []
        for seq, (orig_idx, m, content) in enumerate(valid):
            # Truncate very long outputs for the judge.
            text = str(content)
            if len(text) > 6000:
                text = text[:6000] + "\n... [truncated]"
            candidate_blocks.append(
                f"--- Candidate {seq} (model: {m}) ---\n{text}"
            )

        judge_user_prompt = (
            f"You are a quality judge. Compare these {len(valid)} outputs for a cinema production task.\n"
            f"The original system prompt was:\n\"\"\"\n{system_prompt}\n\"\"\"\n\n"
            + "\n\n".join(candidate_blocks)
            + "\n\n"
            "Rate each candidate 0-10 on: creativity, technical accuracy, completeness, style consistency.\n"
            'Respond with JSON: {"scores": [score1, score2, ...], "winner": <0-indexed among the candidates shown>, "reasoning": "..."}'
        )

        try:
            # --- nested helper: 3-branch LLM call --------------------------------
            def _call_judge(prompt: str) -> Any:
                """Call the judge model and return raw output (str or dict)."""
                if judge_model.startswith("claude"):
                    _, raw = self._generate_anthropic(
                        judge_model,
                        "You are an impartial quality judge. Respond only with valid JSON.",
                        prompt,
                    )
                elif judge_model.startswith("gemini"):
                    _, raw = self._generate_gemini(
                        judge_model,
                        "You are an impartial quality judge. Respond only with valid JSON.",
                        prompt,
                        json_mode=True,
                    )
                else:
                    _, raw = self._generate_openai(
                        judge_model,
                        "You are an impartial quality judge. Respond only with valid JSON.",
                        prompt,
                        json_mode=True,
                    )
                return raw
            # ---------------------------------------------------------------------

            # ≤1-retry loop for JSONDecodeError only.
            # The outer broad except (below) still catches all other failures
            # (wrong-shape result, missing keys, TypeError, IndexError, etc.).
            raw = _call_judge(judge_user_prompt)
            try:
                parsed = json.loads(_strip_json_fences(raw)) if isinstance(raw, str) else raw
            except json.JSONDecodeError:
                # Attempt 1 failed to parse — retry once with a correction appended.
                correction_prompt = (
                    judge_user_prompt
                    + "\n\nYour previous response was not valid JSON. "
                    "Output ONLY a valid JSON object — no markdown, no prose."
                )
                raw = _call_judge(correction_prompt)
                # Let JSONDecodeError on attempt 2 propagate to the outer except
                # (→ first-valid fallback), preserving the existing contract.
                parsed = json.loads(_strip_json_fences(raw)) if isinstance(raw, str) else raw

            judge_scores: list[float] = [float(s) for s in parsed["scores"]]
            winner_among_valid: int = int(parsed["winner"])
            reasoning: str = parsed.get("reasoning", "")

            # Map the winner index back to the original candidate list.
            winner_original_idx = valid[winner_among_valid][0]

            # Build full scores list (0.0 for failed candidates).
            full_scores = [0.0] * len(candidates)
            for seq, (orig_idx, _, _) in enumerate(valid):
                if seq < len(judge_scores):
                    full_scores[orig_idx] = judge_scores[seq]

            print(
                f"[Ensemble] Judge: {judge_model} picked candidate "
                f"{winner_original_idx} with score {full_scores[winner_original_idx]:.2f}"
            )
            return (winner_original_idx, full_scores, reasoning)

        except Exception as exc:  # noqa: BLE001
            # Judging failed -- fall back to first valid candidate.
            # NOTE: This broad except is INTENTIONALLY preserved to absorb
            # wrong-shape results (list/str instead of dict), missing "scores"/
            # "winner" keys, TypeErrors, IndexErrors, etc. — the DP-01
            # fold-forward from chief_director.py's Lane V CRITICAL finding.
            print(f"[LLMEnsemble] Judging failed: {exc}")
            idx = valid[0][0]
            scores = [0.0] * len(candidates)
            scores[idx] = 5.0
            return (idx, scores, f"Judging failed ({exc}); defaulting to first valid candidate.")
