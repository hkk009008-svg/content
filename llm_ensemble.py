"""
Competitive multi-LLM generation and judging system for the cinema pipeline.

Generates candidate outputs from multiple models in parallel, then uses a
judge model to select the best result.  Also provides ensemble quality voting
that aggregates vision-based QA checks across different model backends.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
from dataclasses import dataclass, field
from typing import Any


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


@dataclass
class EnsembleQualityResult:
    """Aggregated result of multi-model quality voting."""
    passed: bool
    votes: list[dict]
    confidence: float
    reasons: list[str]


# ---------------------------------------------------------------------------
# Default model rosters per task type
# ---------------------------------------------------------------------------

_DEFAULT_MODELS: dict[str, list[str]] = {
    "script": ["claude-sonnet-4-20250514", "gpt-4o"],
    "decompose": ["gpt-4o", "claude-sonnet-4-20250514"],
    "default": ["claude-sonnet-4-20250514", "gpt-4o"],
}

_DEFAULT_JUDGE = "claude-sonnet-4-20250514"


# ---------------------------------------------------------------------------
# LLMEnsemble
# ---------------------------------------------------------------------------

class LLMEnsemble:
    """Orchestrates competitive generation across multiple LLM providers."""

    def __init__(self) -> None:
        # Lazy-import clients so the module can be imported even when the
        # underlying SDKs are not installed (they just need to be present
        # at call time).
        import anthropic
        import openai

        self.anthropic_client = anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        )
        self.openai_client = openai.OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY", ""),
        )

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
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())

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

    def ensemble_quality_vote(
        self,
        image_path: str,
        prompt: str,
        reference_path: str | None = None,
    ) -> EnsembleQualityResult:
        """Run 2-3 vision quality checks in parallel and aggregate votes.

        Checks executed:
        1. ``validate_shot_quality_vision`` (GPT-4o) -- composition / artifacts
        2. ``validate_identity_vision`` (Claude) -- identity match (if *reference_path*)
        3. ``validate_scene_coherence_vision`` (Gemini) -- scene coherence

        A candidate passes if at least ``ceil(N/2)`` of the available voters
        pass (i.e. 2-of-3 when all three run, 1-of-2 when only two run).

        Parameters
        ----------
        image_path:
            Path to the generated image to evaluate.
        prompt:
            The original generation prompt (used by shot-quality check).
        reference_path:
            Optional reference image for identity comparison.

        Returns
        -------
        EnsembleQualityResult
        """
        from phase_c_vision import (
            validate_identity_vision,
            validate_scene_coherence_vision,
            validate_shot_quality_vision,
        )

        tasks: list[tuple[str, Any, tuple]] = [
            ("shot_quality", validate_shot_quality_vision, (image_path, prompt)),
            (
                "scene_coherence",
                validate_scene_coherence_vision,
                ([image_path],),  # expects a list; treat single image as 1-shot sequence
            ),
        ]
        if reference_path is not None:
            tasks.append(
                ("identity", validate_identity_vision, (reference_path, image_path)),
            )

        # Execute checks in parallel.
        votes: list[dict] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(tasks)) as pool:
            future_to_name: dict[concurrent.futures.Future, str] = {}
            for name, fn, args in tasks:
                future_to_name[pool.submit(fn, *args)] = name

            for future in concurrent.futures.as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    result = future.result()
                    votes.append({"name": name, **result})
                except Exception as exc:
                    votes.append({
                        "name": name,
                        "passed": False,
                        "score": 0.0,
                        "issues": [f"Check failed with error: {exc}"],
                    })

        # Aggregate.
        pass_count = sum(1 for v in votes if v.get("passed", False))
        total = len(votes)
        threshold = (total // 2) + 1  # majority: 2-of-3 or 1-of-2 (ceildiv)
        passed = pass_count >= threshold

        scores = [v.get("score", 0.0) for v in votes]
        confidence = sum(scores) / len(scores) if scores else 0.0

        reasons: list[str] = []
        for v in votes:
            for issue in v.get("issues", []):
                reasons.append(f"[{v['name']}] {issue}")

        return EnsembleQualityResult(
            passed=passed,
            votes=votes,
            confidence=confidence,
            reasons=reasons,
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
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        if tool_schema is not None:
            kwargs["tools"] = [tool_schema]

        response = self.anthropic_client.messages.create(**kwargs)

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
            if judge_model.startswith("claude"):
                _, raw = self._generate_anthropic(
                    judge_model,
                    "You are an impartial quality judge. Respond only with valid JSON.",
                    judge_user_prompt,
                )
            else:
                _, raw = self._generate_openai(
                    judge_model,
                    "You are an impartial quality judge. Respond only with valid JSON.",
                    judge_user_prompt,
                    json_mode=True,
                )

            parsed = json.loads(raw) if isinstance(raw, str) else raw
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

            return (winner_original_idx, full_scores, reasoning)

        except Exception as exc:  # noqa: BLE001
            # Judging failed -- fall back to first valid candidate.
            print(f"[LLMEnsemble] Judging failed: {exc}")
            idx = valid[0][0]
            scores = [0.0] * len(candidates)
            scores[idx] = 5.0
            return (idx, scores, f"Judging failed ({exc}); defaulting to first valid candidate.")
