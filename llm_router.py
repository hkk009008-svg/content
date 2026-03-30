"""
Cinema Pipeline - Unified LLM Routing Layer

Routes LLM calls to optimal providers per task type with automatic fallback,
exponential backoff, cost tracking, and prompt caching support.
"""

import os
import time
import random
import base64
import logging
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class LLMResponse:
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    tool_calls: Optional[list] = None


@dataclass
class CostEntry:
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


# ---------------------------------------------------------------------------
# Cost table (per 1M tokens)
# ---------------------------------------------------------------------------

COST_PER_1M = {
    "claude-sonnet-4-20250514":   {"input": 3.00,  "output": 15.00},
    "claude-opus-4-20250918":     {"input": 5.00,  "output": 25.00},
    "claude-haiku-4-5":           {"input": 1.00,  "output": 5.00},
    "gpt-4.1":                    {"input": 2.00,  "output": 8.00},
    "gpt-4.1-mini":               {"input": 0.40,  "output": 1.60},
    "gpt-4.1-nano":               {"input": 0.10,  "output": 0.40},
    "gpt-4o":                     {"input": 2.50,  "output": 10.00},
    "o4-mini":                    {"input": 1.10,  "output": 4.40},
    "gemini-2.5-flash":           {"input": 0.30,  "output": 2.50},
    "gemini-2.5-pro":             {"input": 1.25,  "output": 10.00},
}

# ---------------------------------------------------------------------------
# Routing table
# ---------------------------------------------------------------------------

ROUTING_TABLE: dict[str, dict] = {
    "creative_scene":   {"primary": "claude-sonnet-4-20250514", "fallback": "claude-opus-4-20250918"},
    "structured_json":  {"primary": "gpt-4.1-mini",             "fallback": "gpt-4.1"},
    "video_analysis":   {"primary": "gemini-2.5-flash",         "fallback": "gemini-2.5-pro"},
    "classification":   {"primary": "gpt-4.1-nano",             "fallback": "claude-haiku-4-5"},
    "quality_review":   {"primary": "claude-opus-4-20250918",   "fallback": "o4-mini"},
    "identity_vision":  {"primary": "claude-sonnet-4-20250514", "fallback": "o4-mini"},
    "coherence_vision": {"primary": "gemini-2.5-flash",         "fallback": "gemini-2.5-pro"},
    "shot_quality":     {"primary": "o4-mini",                  "fallback": "gpt-4o"},
    "scene_decompose":  {"primary": "gpt-4.1",                  "fallback": "claude-sonnet-4-20250514"},
    "chief_director":   {"primary": "claude-sonnet-4-20250514", "fallback": "gpt-4o"},
}


def get_routing_table(settings: dict | None = None) -> dict[str, dict]:
    """Return ROUTING_TABLE with optional overrides from project settings."""
    table = {k: dict(v) for k, v in ROUTING_TABLE.items()}  # deep copy
    if not settings:
        return table

    creative_map = {
        "claude-sonnet": "claude-sonnet-4-20250514",
        "gpt-4o": "gpt-4o",
    }
    judge_map = {
        "claude-opus": "claude-opus-4-20250918",
        "gpt-4o": "gpt-4o",
        "gemini-pro": "gemini-2.5-pro",
    }

    creative_pref = settings.get("creative_llm", "auto")
    if creative_pref != "auto" and creative_pref in creative_map:
        model = creative_map[creative_pref]
        for key in ("creative_scene", "scene_decompose", "chief_director"):
            if key in table:
                table[key]["primary"] = model

    judge_pref = settings.get("quality_judge_llm", "auto")
    if judge_pref != "auto" and judge_pref in judge_map:
        model = judge_map[judge_pref]
        if "quality_review" in table:
            table["quality_review"]["primary"] = model

    return table


def _provider_for_model(model: str) -> str:
    if model.startswith("claude"):
        return "anthropic"
    if model.startswith("gemini"):
        return "google"
    return "openai"


def _calc_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = COST_PER_1M.get(model, {"input": 0.0, "output": 0.0})
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class CinemaLLMRouter:
    """Unified LLM routing layer for the cinema pipeline."""

    def __init__(self):
        self._cost_log: list[CostEntry] = []

        # Lazy-initialised SDK clients
        self._anthropic_client = None
        self._openai_client = None
        self._gemini_configured = False

    # -- SDK client helpers --------------------------------------------------

    def _get_anthropic(self):
        if self._anthropic_client is None:
            import anthropic
            self._anthropic_client = anthropic.Anthropic(
                api_key=os.getenv("ANTHROPIC_API_KEY"),
            )
        return self._anthropic_client

    def _get_openai(self):
        if self._openai_client is None:
            from openai import OpenAI
            self._openai_client = OpenAI(
                api_key=os.getenv("OPENAI_API_KEY"),
            )
        return self._openai_client

    def _ensure_gemini(self):
        if not self._gemini_configured:
            from google import genai
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            self._gemini_client = genai.Client(api_key=api_key)
            self._gemini_configured = True

    # -- Provider call implementations --------------------------------------

    def _call_anthropic(
        self,
        model: str,
        messages: list[dict],
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[list] = None,
    ) -> LLMResponse:
        client = self._get_anthropic()

        kwargs: dict = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens or 4096,
        }

        # Prompt caching on system prompt
        if system:
            kwargs["system"] = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]

        if temperature is not None:
            kwargs["temperature"] = temperature

        if tools:
            kwargs["tools"] = tools

        resp = client.messages.create(**kwargs)

        # Extract text content
        content_parts = [b.text for b in resp.content if hasattr(b, "text")]
        content = "\n".join(content_parts)

        # Extract tool use blocks
        tool_calls = [
            {"id": b.id, "name": b.name, "input": b.input}
            for b in resp.content
            if b.type == "tool_use"
        ]

        input_tokens = resp.usage.input_tokens
        output_tokens = resp.usage.output_tokens
        cache_read = getattr(resp.usage, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(resp.usage, "cache_creation_input_tokens", 0) or 0

        cost = _calc_cost(model, input_tokens, output_tokens)

        self._cost_log.append(
            CostEntry(
                model=model,
                provider="anthropic",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                cache_read_tokens=cache_read,
                cache_write_tokens=cache_write,
            )
        )

        return LLMResponse(
            content=content,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            tool_calls=tool_calls or None,
        )

    def _call_openai(
        self,
        model: str,
        messages: list[dict],
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        tools: Optional[list] = None,
    ) -> LLMResponse:
        client = self._get_openai()

        full_messages: list[dict] = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        kwargs: dict = {
            "model": model,
            "messages": full_messages,
        }

        if temperature is not None:
            kwargs["temperature"] = temperature

        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        if tools:
            kwargs["tools"] = tools

        resp = client.chat.completions.create(**kwargs)

        choice = resp.choices[0]
        content = choice.message.content or ""

        tool_calls = None
        if choice.message.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                }
                for tc in choice.message.tool_calls
            ]

        input_tokens = resp.usage.prompt_tokens
        output_tokens = resp.usage.completion_tokens
        cost = _calc_cost(model, input_tokens, output_tokens)

        self._cost_log.append(
            CostEntry(
                model=model,
                provider="openai",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
            )
        )

        return LLMResponse(
            content=content,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            tool_calls=tool_calls,
        )

    def _call_gemini(
        self,
        model: str,
        messages: list[dict],
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        from google.genai import types as genai_types

        self._ensure_gemini()
        client = self._gemini_client

        # Build contents list from messages
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            parts = []
            if isinstance(msg.get("content"), str):
                parts.append(genai_types.Part.from_text(text=msg["content"]))
            elif isinstance(msg.get("content"), list):
                for item in msg["content"]:
                    if isinstance(item, str):
                        parts.append(genai_types.Part.from_text(text=item))
                    elif isinstance(item, dict):
                        if item.get("type") == "text":
                            parts.append(genai_types.Part.from_text(text=item["text"]))
                        elif item.get("type") == "image" and "data" in item:
                            parts.append(
                                genai_types.Part.from_bytes(
                                    data=base64.b64decode(item["data"]),
                                    mime_type=item.get("mime_type", "image/jpeg"),
                                )
                            )
            contents.append(genai_types.Content(role=role, parts=parts))

        config = genai_types.GenerateContentConfig()
        if system:
            config.system_instruction = system
        if temperature is not None:
            config.temperature = temperature
        if max_tokens is not None:
            config.max_output_tokens = max_tokens

        resp = client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

        content = resp.text or ""
        input_tokens = getattr(resp.usage_metadata, "prompt_token_count", 0) or 0
        output_tokens = getattr(resp.usage_metadata, "candidates_token_count", 0) or 0
        cost = _calc_cost(model, input_tokens, output_tokens)

        self._cost_log.append(
            CostEntry(
                model=model,
                provider="google",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
            )
        )

        return LLMResponse(
            content=content,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
        )

    # -- Dispatch helper -----------------------------------------------------

    def _dispatch(
        self,
        model: str,
        messages: list[dict],
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        tools: Optional[list] = None,
    ) -> LLMResponse:
        provider = _provider_for_model(model)
        if provider == "anthropic":
            return self._call_anthropic(model, messages, system, temperature, max_tokens, tools)
        elif provider == "google":
            return self._call_gemini(model, messages, system, temperature, max_tokens)
        else:
            return self._call_openai(model, messages, system, temperature, max_tokens, json_mode, tools)

    # -- Public API ----------------------------------------------------------

    def call(
        self,
        task_type: str,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        tools: Optional[list] = None,
    ) -> LLMResponse:
        """Route an LLM call to the optimal provider for *task_type*.

        Tries the primary model first; on any exception falls back to the
        secondary model.  Each attempt uses exponential backoff with jitter
        (base 1 s, factor 2, cap 30 s, 3 retries).
        """
        route = ROUTING_TABLE.get(task_type)
        if route is None:
            raise ValueError(
                f"Unknown task_type '{task_type}'. "
                f"Valid types: {', '.join(sorted(ROUTING_TABLE))}"
            )

        models_to_try = [route["primary"], route["fallback"]]

        last_exc: Optional[Exception] = None
        for model in models_to_try:
            try:
                return self._call_with_retries(
                    model=model,
                    messages=messages,
                    system=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                    tools=tools,
                )
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Model %s failed for task %s: %s — trying fallback",
                    model,
                    task_type,
                    exc,
                )

        raise RuntimeError(
            f"All models failed for task_type '{task_type}': {last_exc}"
        ) from last_exc

    def call_vision(
        self,
        task_type: str,
        messages: list[dict],
        image_paths: Optional[list[str]] = None,
        video_path: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Call with image or video content attached to the last user message."""
        enriched = list(messages)

        # Build the multimodal content list for the last user message
        last_msg = enriched[-1]
        if last_msg["role"] != "user":
            raise ValueError("Last message must be a user message for vision calls")

        parts: list = []
        text = last_msg.get("content", "")
        if isinstance(text, str):
            parts.append({"type": "text", "text": text})
        elif isinstance(text, list):
            parts.extend(text)

        if image_paths:
            for path in image_paths:
                with open(path, "rb") as f:
                    img_data = base64.b64encode(f.read()).decode()
                ext = os.path.splitext(path)[1].lower().lstrip(".")
                mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp", "gif": "image/gif"}.get(ext, "image/jpeg")

                route = ROUTING_TABLE.get(task_type, {})
                provider = _provider_for_model(route.get("primary", ""))

                if provider == "anthropic":
                    parts.append({
                        "type": "image",
                        "source": {"type": "base64", "media_type": mime, "data": img_data},
                    })
                elif provider == "openai":
                    parts.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{img_data}"},
                    })
                else:
                    # Gemini - handled via content builder in _call_gemini
                    parts.append({
                        "type": "image",
                        "data": img_data,
                        "mime_type": mime,
                    })

        if video_path:
            with open(video_path, "rb") as f:
                vid_data = base64.b64encode(f.read()).decode()
            ext = os.path.splitext(video_path)[1].lower().lstrip(".")
            mime = {"mp4": "video/mp4", "webm": "video/webm", "mov": "video/quicktime"}.get(ext, "video/mp4")
            parts.append({"type": "image", "data": vid_data, "mime_type": mime})

        enriched[-1] = {"role": "user", "content": parts}

        return self.call(
            task_type=task_type,
            messages=enriched,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    # -- Retry logic ---------------------------------------------------------

    def _call_with_retries(
        self,
        model: str,
        messages: list[dict],
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
        tools: Optional[list] = None,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
    ) -> LLMResponse:
        last_exc: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                return self._dispatch(
                    model=model,
                    messages=messages,
                    system=system,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                    tools=tools,
                )
            except Exception as exc:
                last_exc = exc
                if attempt < max_retries:
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    jitter = random.uniform(0, delay * 0.5)
                    sleep_time = delay + jitter
                    logger.info(
                        "Retry %d/%d for %s in %.1fs: %s",
                        attempt + 1,
                        max_retries,
                        model,
                        sleep_time,
                        exc,
                    )
                    time.sleep(sleep_time)

        raise last_exc  # type: ignore[misc]

    # -- Cost tracking -------------------------------------------------------

    def get_cost_summary(self) -> dict:
        """Return total costs grouped by provider and by model."""
        by_provider: dict[str, float] = defaultdict(float)
        by_model: dict[str, dict] = defaultdict(lambda: {
            "calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
        })
        total_cost = 0.0

        for entry in self._cost_log:
            by_provider[entry.provider] += entry.cost_usd
            m = by_model[entry.model]
            m["calls"] += 1
            m["input_tokens"] += entry.input_tokens
            m["output_tokens"] += entry.output_tokens
            m["cost_usd"] += entry.cost_usd
            m["cache_read_tokens"] += entry.cache_read_tokens
            m["cache_write_tokens"] += entry.cache_write_tokens
            total_cost += entry.cost_usd

        return {
            "total_cost_usd": round(total_cost, 6),
            "by_provider": dict(by_provider),
            "by_model": dict(by_model),
            "total_calls": len(self._cost_log),
        }

    def reset_costs(self) -> None:
        """Clear all accumulated cost entries."""
        self._cost_log.clear()


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    router = CinemaLLMRouter()

    print("=== Cinema LLM Router ===")
    print(f"Routing table ({len(ROUTING_TABLE)} task types):")
    for task, route in ROUTING_TABLE.items():
        print(f"  {task:20s}  primary={route['primary']:30s}  fallback={route['fallback']}")

    print(f"\nCost table ({len(COST_PER_1M)} models):")
    for model, rates in COST_PER_1M.items():
        print(f"  {model:30s}  ${rates['input']:.2f} in / ${rates['output']:.2f} out  (per 1M)")

    # Quick smoke test — only runs if API keys are set
    api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY")
    if api_key:
        print("\n--- Smoke test: classification task ---")
        try:
            resp = router.call(
                task_type="classification",
                messages=[{"role": "user", "content": "Is this scene indoor or outdoor: A man walks into a bar."}],
                temperature=0.0,
                max_tokens=64,
            )
            print(f"Model:  {resp.model}")
            print(f"Tokens: {resp.input_tokens} in / {resp.output_tokens} out")
            print(f"Cost:   ${resp.cost_usd:.6f}")
            print(f"Reply:  {resp.content[:200]}")
        except Exception as exc:
            print(f"Smoke test failed (expected if keys missing): {exc}")

        print("\n--- Cost summary ---")
        summary = router.get_cost_summary()
        print(f"Total calls: {summary['total_calls']}")
        print(f"Total cost:  ${summary['total_cost_usd']:.6f}")
        for model, info in summary["by_model"].items():
            print(f"  {model}: {info['calls']} calls, ${info['cost_usd']:.6f}")
    else:
        print("\nNo API keys found -- skipping live smoke test.")
        print("Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or GEMINI_API_KEY to enable.")

    print("\nRouter initialised successfully.")
