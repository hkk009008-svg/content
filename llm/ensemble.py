"""
Competitive multi-LLM generation and judging system for the cinema pipeline.

Generates candidate outputs from multiple models in parallel, then uses a
judge model to select the best result.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import math
import sys
import time
import warnings
from dataclasses import dataclass
from typing import Any
from config.settings import settings as env_settings   # aliased to avoid clash with the per-instance `settings: dict` ctor arg below
from paid_provider import (
    PaidCallDeferred,
    has_paid_attempt_authority,
    openai_output_limit_kwargs,
    run_fenced_llm_call,
)


logger = logging.getLogger(__name__)


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
    winner_index: int | None
    winner_content: Any
    scores: list[float]
    reasoning: str
    candidates: list[Any]
    models_used: list[str]
    judge_model: str
    judgment_status: str = "SELECTED"


@dataclass(frozen=True)
class _JudgeDecision:
    """Strict, provider-independent result returned by the ensemble judge."""

    scores: list[float]
    winner: int
    reasoning: str


def _parse_judge_decision(raw: Any, candidate_count: int) -> _JudgeDecision:
    """Parse and validate the exact judge schema.

    A syntactically valid JSON value is not enough: score count/ranges, winner
    bounds, and the winner/score relationship are part of the executable
    contract.  Invalid output remains unjudged rather than silently promoting a
    roster-position candidate.
    """

    parsed = json.loads(_strip_json_fences(raw)) if isinstance(raw, str) else raw
    if not isinstance(parsed, dict):
        raise ValueError("judge response must be a JSON object")

    required = {"scores", "winner", "reasoning"}
    if set(parsed) != required:
        missing = sorted(required - set(parsed))
        extra = sorted(set(parsed) - required)
        raise ValueError(
            f"judge response keys mismatch (missing={missing}, extra={extra})"
        )

    raw_scores = parsed["scores"]
    if not isinstance(raw_scores, list) or len(raw_scores) != candidate_count:
        raise ValueError(
            f"judge scores must contain exactly {candidate_count} entries"
        )

    scores: list[float] = []
    for value in raw_scores:
        if isinstance(value, bool):
            raise ValueError("judge scores must be numeric, not boolean")
        try:
            score = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("judge scores must be numeric") from exc
        if not math.isfinite(score) or not 0.0 <= score <= 10.0:
            raise ValueError("judge scores must be finite values in [0, 10]")
        scores.append(score)

    winner = parsed["winner"]
    if isinstance(winner, bool) or not isinstance(winner, int):
        raise ValueError("judge winner must be an integer")
    if not 0 <= winner < candidate_count:
        raise ValueError("judge winner is outside the candidate range")
    if scores[winner] != max(scores):
        raise ValueError("judge winner must reference a highest-scored candidate")

    reasoning = parsed["reasoning"]
    if not isinstance(reasoning, str) or not reasoning.strip():
        raise ValueError("judge reasoning must be a non-empty string")

    return _JudgeDecision(scores=scores, winner=winner, reasoning=reasoning.strip())


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

    def __init__(
        self,
        settings: dict | None = None,
        cost_tracker: Any | None = None,
        video_id: str = "",
    ) -> None:
        # Keep the public client attributes available for caller/test injection,
        # but do not import or construct an SDK until its key is configured.
        anthropic_key = env_settings.anthropic_api_key
        if anthropic_key:
            import anthropic
            self.anthropic_client = anthropic.Anthropic(
                api_key=anthropic_key,
                timeout=120.0,
            )
        else:
            self.anthropic_client = None

        openai_key = env_settings.openai_api_key
        if openai_key:
            import openai
            self.openai_client = openai.OpenAI(
                api_key=openai_key,
                timeout=120.0,
            )
        else:
            self.openai_client = None

        self.cost_tracker = cost_tracker
        inherited_video_id = getattr(cost_tracker, "default_video_id", "")
        self.video_id = str(
            video_id
            or (inherited_video_id if isinstance(inherited_video_id, str) else "")
        )[:128]

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
        self.candidate_timeout_s = 120.0
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
                    # gemini-2.5-pro shuts down 2026-10-16 (Slice 6b); migrated
                    # to its documented successor gemini-3.1-pro-preview —
                    # itself preview-tier (confirmed via 2026-07-31 WebFetch of
                    # the model page), which is why the web_server.py option
                    # label says "(Preview)". Structured outputs are supported
                    # there too, so the existing response_mime_type-based
                    # json_mode path in _generate_gemini carries over unchanged.
                    "gemini-pro": "gemini-3.1-pro-preview",
                }
                self.judge_model_override = judge_map.get(judge_pref)

    def _log_llm_usage(
        self,
        model: str,
        operation: str,
        input_tokens: Any,
        output_tokens: Any,
    ) -> None:
        """Record LLM token usage on the shared budget tracker when present."""
        if self.cost_tracker is None or has_paid_attempt_authority(self.cost_tracker):
            return

        try:
            input_count = int(input_tokens or 0)
            output_count = int(output_tokens or 0)
        except (TypeError, ValueError):
            return

        if input_count <= 0 and output_count <= 0:
            return

        try:
            self.cost_tracker.log_llm(
                model=model,
                operation=operation,
                input_tokens=input_count,
                output_tokens=output_count,
                video_id=getattr(self, "video_id", ""),
            )
        except Exception as exc:  # noqa: BLE001
            msg = f"[LLMEnsemble] Failed to record LLM usage for {model!r}: {exc}"
            # BOTH channels (ADR-066/067): once DeepFace/TF loads anywhere in
            # the process, a fronted ignore-all warnings filter silences bare
            # warnings.warn — and unrecorded LLM spend under-reads the budget
            # gate for the rest of the run (llmensemble-cost-uncounted class).
            print(msg, file=sys.stderr)
            warnings.warn(msg, stacklevel=2)

    def _call_with_observation(
        self,
        *,
        provider: str,
        model: str,
        operation: str,
        call: Any,
        request_payload: Any,
        max_output_tokens: int,
        attempt_scope: str = "",
    ) -> Any:
        """Invoke one SDK request with durable authority when available.

        Provider observations expose latency/outcome. A real project tracker
        additionally owns the atomic budget reservation and no-replay fence;
        narrow standalone trackers retain the legacy direct-call behavior.
        """
        started = time.perf_counter()

        def persist(status: str, latency_ms: int) -> None:
            tracker = getattr(self, "cost_tracker", None)
            if has_paid_attempt_authority(tracker):
                # The paid-attempt row already owns this exact outcome and
                # terminal latency. A second provider_observation would double
                # the analytics sample and cross health thresholds early.
                return
            recorder = getattr(tracker, "record_provider_observation", None)
            if not callable(recorder):
                return
            try:
                recorder(
                    provider=provider,
                    engine=model,
                    operation=operation,
                    status=status,
                    latency_ms=latency_ms,
                    video_id=getattr(self, "video_id", ""),
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Planning LLM observation recording failed",
                    extra={
                        "provider": provider,
                        "engine": model,
                        "code": operation,
                        "status": "observation_unrecorded",
                        "video_id": getattr(self, "video_id", ""),
                    },
                    exc_info=exc,
                )

        try:
            response = run_fenced_llm_call(
                call=call,
                provider=provider,
                model=model,
                operation=operation,
                request_payload=request_payload,
                max_output_tokens=max_output_tokens,
                cost_tracker=getattr(self, "cost_tracker", None),
                video_id=getattr(self, "video_id", ""),
                attempt_scope=attempt_scope,
            )
        except Exception:
            latency_ms = max(0, round((time.perf_counter() - started) * 1000))
            persist("failed", latency_ms)
            logger.warning(
                "Planning LLM request failed",
                extra={
                    "provider": provider,
                    "engine": model,
                    "code": operation,
                    "latency_ms": latency_ms,
                    "status": "failed",
                    "video_id": getattr(self, "video_id", ""),
                },
            )
            raise
        latency_ms = max(0, round((time.perf_counter() - started) * 1000))
        persist("succeeded", latency_ms)
        logger.info(
            "Planning LLM request completed",
            extra={
                "provider": provider,
                "engine": model,
                "code": operation,
                "latency_ms": latency_ms,
                "status": "succeeded",
                "video_id": getattr(self, "video_id", ""),
            },
        )
        return response

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
        requirements: list[str] | None = None,
        rubric: dict[str, str] | None = None,
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
            Explicit judge override for this call. Precedence is
            ``judge_model`` argument → ``self.judge_model_override``
            (from settings ``quality_judge_llm``) → ``_DEFAULT_JUDGE``.
        json_mode:
            When ``True``, OpenAI calls use ``response_format={"type": "json_object"}``.
        tool_schema:
            If provided, Anthropic calls use ``tools=[tool_schema]`` and
            the tool_use result is extracted as the candidate output.
        requirements:
            Optional task-specific requirements the judge must apply in
            addition to the original prompts.
        rubric:
            Optional named judging dimensions. Values describe what each
            dimension means; provider/model identities are never shown.

        Notes
        -----
        When ``self.competitive_enabled`` is False (settings
        ``competitive_generation=False``), only the first model in the
        roster is dispatched and judging is skipped (auto-win).

        Returns
        -------
        EnsembleResult
        """
        if models is None:
            models = list(
                _DEFAULT_MODELS.get(task_type, _DEFAULT_MODELS["default"])
            )
        else:
            models = list(models)

        # Honor constructor settings: competitive_generation=False → single model.
        if not self.competitive_enabled:
            models = models[:1]

        effective_judge = (
            judge_model
            or self.judge_model_override
            or _DEFAULT_JUDGE
        )

        if not models:
            return EnsembleResult(
                winner_index=None,
                winner_content=None,
                scores=[],
                reasoning="No candidate models were configured.",
                candidates=[],
                models_used=[],
                judge_model=effective_judge,
                judgment_status="NO_CANDIDATE",
            )

        # Generate from every model in parallel. Futures are keyed by roster
        # position, not model ID, so duplicate model entries cannot overwrite
        # each other. Explicit shutdown(wait=False) prevents the old context-
        # manager behavior from waiting indefinitely after the ensemble deadline.
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=len(models))
        futures: dict[concurrent.futures.Future, int] = {}
        ordered_candidates: list[Any] = [None] * len(models)
        try:
            for index, model in enumerate(models):
                future = pool.submit(
                    self._generate_single,
                    model,
                    system_prompt,
                    user_prompt,
                    json_mode,
                    tool_schema,
                    operation="llm_ensemble_candidate",
                    attempt_scope=f"candidate:{index}",
                )
                futures[future] = index

            try:
                for future in concurrent.futures.as_completed(
                    futures,
                    timeout=max(
                        0.001,
                        float(getattr(self, "candidate_timeout_s", 120.0)),
                    ),
                ):
                    index = futures[future]
                    _returned_model, output = future.result()
                    ordered_candidates[index] = output
            except TimeoutError:
                print("[LLMEnsemble] Candidate deadline reached; unfinished calls excluded")
        finally:
            for future in futures:
                if not future.done():
                    future.cancel()
            pool.shutdown(wait=False, cancel_futures=True)

        ordered_models = list(models)

        # Judge the candidates (auto-wins when only one candidate remains).
        winner_index, scores, reasoning = self._judge(
            ordered_candidates,
            ordered_models,
            system_prompt,
            user_prompt=user_prompt,
            task_type=task_type,
            requirements=requirements,
            rubric=rubric,
            judge_model=effective_judge,
        )

        valid_count = sum(candidate is not None for candidate in ordered_candidates)
        if winner_index is None:
            judgment_status = "NO_CANDIDATE" if valid_count == 0 else "UNABLE_TO_JUDGE"
            winner_content = None
        else:
            judgment_status = "SINGLE_CANDIDATE" if valid_count == 1 else "SELECTED"
            winner_content = ordered_candidates[winner_index]

        return EnsembleResult(
            winner_index=winner_index,
            winner_content=winner_content,
            scores=scores,
            reasoning=reasoning,
            candidates=ordered_candidates,
            models_used=ordered_models,
            judge_model=effective_judge,
            judgment_status=judgment_status,
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
        operation: str = "llm_ensemble_call",
        attempt_scope: str = "",
    ) -> tuple[str, Any]:
        """Route a generation request to the correct provider.

        Returns ``(model, output_content)`` on success or
        ``(model, None)`` on failure.
        """
        try:
            if model.startswith("claude"):
                return self._generate_anthropic(
                    model, system_prompt, user_prompt, tool_schema, operation=operation,
                    attempt_scope=attempt_scope,
                )
            elif model.startswith("gpt") or model.startswith("o4"):
                return self._generate_openai(
                    model, system_prompt, user_prompt, json_mode, operation=operation,
                    attempt_scope=attempt_scope,
                )
            elif model.startswith("gemini"):
                return self._generate_gemini(
                    model, system_prompt, user_prompt, json_mode, operation=operation,
                    attempt_scope=attempt_scope,
                )
            else:
                # Unknown provider -- attempt OpenAI-compatible call.
                return self._generate_openai(
                    model, system_prompt, user_prompt, json_mode, operation=operation,
                    attempt_scope=attempt_scope,
                )
        except PaidCallDeferred:
            raise
        except Exception as exc:  # noqa: BLE001
            print(f"[LLMEnsemble] Generation failed for {model}: {exc}")
            return (model, None)

    def _generate_anthropic(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        tool_schema: dict | None = None,
        operation: str = "llm_ensemble_call",
        attempt_scope: str = "",
    ) -> tuple[str, Any]:
        """Call the Anthropic messages API."""
        if self.anthropic_client is None:
            raise RuntimeError(
                "Anthropic model requested but ANTHROPIC_API_KEY is not configured"
            )

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": 4096,
            "system": build_anthropic_system_blocks(system_prompt),
            "messages": [{"role": "user", "content": user_prompt}],
        }
        if tool_schema is not None:
            kwargs["tools"] = [tool_schema]

        response = self._call_with_observation(
            provider="anthropic",
            model=model,
            operation=operation,
            call=lambda: self.anthropic_client.messages.create(**kwargs),
            request_payload=kwargs,
            max_output_tokens=4096,
            attempt_scope=attempt_scope,
        )

        if hasattr(response, "usage"):
            cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
            cache_creation = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
            input_tokens = getattr(response.usage, "input_tokens", 0) or 0
            output_tokens = getattr(response.usage, "output_tokens", 0) or 0
            self._log_llm_usage(model, operation, input_tokens, output_tokens)
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
        operation: str = "llm_ensemble_call",
        attempt_scope: str = "",
    ) -> tuple[str, Any]:
        """Call the OpenAI chat completions API."""
        if self.openai_client is None:
            raise RuntimeError(
                "OpenAI model requested but OPENAI_API_KEY is not configured"
            )

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        kwargs.update(openai_output_limit_kwargs(model, 4096))

        response = self._call_with_observation(
            provider="openai",
            model=model,
            operation=operation,
            call=lambda: self.openai_client.chat.completions.create(**kwargs),
            request_payload=kwargs,
            max_output_tokens=4096,
            attempt_scope=attempt_scope,
        )
        usage = getattr(response, "usage", None)
        if usage is not None:
            input_tokens = (
                getattr(usage, "prompt_tokens", None)
                or getattr(usage, "input_tokens", 0)
                or 0
            )
            output_tokens = (
                getattr(usage, "completion_tokens", None)
                or getattr(usage, "output_tokens", 0)
                or 0
            )
            self._log_llm_usage(model, operation, input_tokens, output_tokens)
        content = response.choices[0].message.content
        return (model, content)

    def _generate_gemini(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
        operation: str = "llm_ensemble_call",
        attempt_scope: str = "",
    ) -> tuple[str, Any]:
        """Call the Google Gemini generateContent API.

        Matches the OpenAI/Anthropic helpers' return shape: ``(model, text)``.
        Uses the new google-genai SDK (genai.Client) — same one used by
        veo_native.py and phase_c_vision.validate_scene_coherence_vision.
        """
        if self.gemini_client is None:
            raise RuntimeError(
                "Gemini model requested but GEMINI_API_KEY / GOOGLE_API_KEY is not configured"
            )

        from google.genai import types

        config_kwargs: dict[str, Any] = {
            "system_instruction": system_prompt,
            "max_output_tokens": 4096,
        }
        if json_mode:
            config_kwargs["response_mime_type"] = "application/json"

        response = self._call_with_observation(
            provider="google",
            model=model,
            operation=operation,
            call=lambda: self.gemini_client.models.generate_content(
                model=model,
                contents=user_prompt,
                config=types.GenerateContentConfig(**config_kwargs),
            ),
            request_payload={
                "model": model,
                "contents": user_prompt,
                "config": config_kwargs,
            },
            max_output_tokens=4096,
            attempt_scope=attempt_scope,
        )
        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            input_tokens = getattr(usage, "prompt_token_count", 0) or 0
            output_tokens = getattr(usage, "candidates_token_count", 0) or 0
            self._log_llm_usage(model, operation, input_tokens, output_tokens)
        return (model, response.text)

    # ------------------------------------------------------------------
    # Judging
    # ------------------------------------------------------------------

    def _judge(
        self,
        candidates: list[Any],
        models: list[str],
        system_prompt: str,
        user_prompt: str = "",
        task_type: str = "default",
        requirements: list[str] | None = None,
        rubric: dict[str, str] | None = None,
        judge_model: str | None = None,
    ) -> tuple[int | None, list[float], str]:
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
            return (None, [0.0] * len(candidates), "All candidates failed to generate output.")

        if len(valid) == 1:
            # Only one succeeded -- auto-win.
            idx = valid[0][0]
            scores = [0.0] * len(candidates)
            scores[idx] = 8.0
            return (idx, scores, "Only one candidate produced output; no comparative judgment was needed.")

        # Build a complete, anonymous judging packet. Candidate provider/model
        # identities are intentionally excluded to avoid prestige/provider bias.
        candidate_blocks: list[str] = []
        for seq, (_orig_idx, _model, content) in enumerate(valid):
            label = chr(ord("A") + seq) if seq < 26 else str(seq + 1)
            if isinstance(content, str):
                text = content
            else:
                text = json.dumps(content, ensure_ascii=False, default=str)
            candidate_blocks.append(f"--- Candidate {label} ---\n{text}")

        effective_requirements = list(requirements or [])
        effective_rubric = rubric or {
            "instruction_following": "Satisfies the original request and every explicit constraint.",
            "technical_accuracy": "Is internally correct, executable, and free of fabricated claims.",
            "completeness": "Covers the requested task without material omissions.",
            "cinematic_quality": "Shows coherent, production-appropriate creative judgment.",
        }
        judge_packet = {
            "task_type": task_type,
            "original_system_prompt": system_prompt,
            "original_user_prompt": user_prompt,
            "requirements": effective_requirements,
            "rubric": effective_rubric,
            "candidate_labels": [
                chr(ord("A") + i) if i < 26 else str(i + 1)
                for i in range(len(valid))
            ],
        }

        judge_user_prompt = (
            "Evaluate the anonymous candidates against this complete task packet:\n"
            + json.dumps(judge_packet, ensure_ascii=False, indent=2)
            + "\n\n"
            + "\n\n".join(candidate_blocks)
            + "\n\n"
            "Return one aggregate 0-10 score per candidate after applying every rubric dimension.\n"
            'Respond with exactly this JSON schema and no extra keys: '
            '{"scores": [score1, score2, ...], "winner": <0-indexed candidate position>, "reasoning": "non-empty explanation"}'
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
                        operation="llm_ensemble_judge",
                    )
                elif judge_model.startswith("gemini"):
                    _, raw = self._generate_gemini(
                        judge_model,
                        "You are an impartial quality judge. Respond only with valid JSON.",
                        prompt,
                        json_mode=True,
                        operation="llm_ensemble_judge",
                    )
                else:
                    _, raw = self._generate_openai(
                        judge_model,
                        "You are an impartial quality judge. Respond only with valid JSON.",
                        prompt,
                        json_mode=True,
                        operation="llm_ensemble_judge",
                    )
                return raw
            # ---------------------------------------------------------------------

            # Retry once for either invalid JSON or a schema-contract failure.
            raw = _call_judge(judge_user_prompt)
            try:
                decision = _parse_judge_decision(raw, len(valid))
            except (json.JSONDecodeError, ValueError, TypeError) as first_error:
                correction_prompt = (
                    judge_user_prompt
                    + "\n\nYour previous response violated the JSON contract: "
                    + str(first_error)
                    + ". Output ONLY a conforming JSON object."
                )
                raw = _call_judge(correction_prompt)
                decision = _parse_judge_decision(raw, len(valid))

            # Map the winner index back to the original candidate list.
            winner_original_idx = valid[decision.winner][0]

            # Build full scores list (0.0 for failed candidates).
            full_scores = [0.0] * len(candidates)
            for seq, (orig_idx, _, _) in enumerate(valid):
                full_scores[orig_idx] = decision.scores[seq]

            print(
                f"[Ensemble] Judge: {judge_model} picked candidate "
                f"{winner_original_idx} with score {full_scores[winner_original_idx]:.2f}"
            )
            return (winner_original_idx, full_scores, decision.reasoning)

        except PaidCallDeferred:
            raise
        except Exception as exc:  # noqa: BLE001
            # A judge failure is not evidence that roster position zero is best.
            # Preserve the inability to decide so callers can route to a manual or
            # deterministic fallback explicitly.
            print(f"[LLMEnsemble] Judging failed: {exc}")
            scores = [0.0] * len(candidates)
            return (None, scores, f"Unable to judge candidates: {exc}")
