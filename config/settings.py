"""Single source of truth for environment-derived configuration.

`.env` is loaded once at import time. Every module imports the `settings`
singleton instead of calling `os.environ` or `load_dotenv` directly.

Adding a new env var:
  1. Add a typed field to the `Settings` dataclass below.
  2. Read it in `Settings.from_env()`.
  3. Document it in `.env.example`.
  4. Use `settings.your_field` (lowercase) in code.

Empty string means "not configured" — callers can rely on
`if settings.kling_access_key:` truthiness checks.
"""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Deployment/platform environment is authoritative. The repository-local file
# supplies only values the process did not receive explicitly.
load_dotenv(_PROJECT_ROOT / ".env", override=False)


class ConfigurationError(ValueError):
    """A named environment value violates the startup configuration contract."""


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _optional_env(key: str) -> str | None:
    value = os.environ.get(key, "").strip()
    return value or None


def _parse_int(
    key: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    raw = os.environ.get(key)
    if raw is None or not raw.strip():
        value = default
    else:
        try:
            value = int(raw)
        except ValueError as exc:
            raise ConfigurationError(f"{key} must be an integer; received {raw!r}") from exc
    if minimum is not None and value < minimum:
        raise ConfigurationError(f"{key} must be >= {minimum}; received {value}")
    if maximum is not None and value > maximum:
        raise ConfigurationError(f"{key} must be <= {maximum}; received {value}")
    return value


def _parse_loopback_bind_host(raw: str) -> str:
    """Keep the unauthenticated application strictly local."""

    host = raw.strip() or "127.0.0.1"
    if host.lower() == "localhost":
        return host
    try:
        if ipaddress.ip_address(host).is_loopback:
            return host
    except ValueError:
        pass
    raise ConfigurationError(
        "WEB_BIND_HOST must be a loopback address because this server has no "
        "remote authentication layer; use 127.0.0.1, ::1, or localhost"
    )


def _parse_cors_origins(raw: str) -> tuple[str, ...]:
    """Parse WEB_CORS_ORIGINS env into a tuple of origin patterns.

    Empty / unset → safe localhost-only default. A wildcard is rejected because
    any website opened in the same browser could otherwise call the local
    project and destructive APIs.
    """
    if not raw.strip():
        return ("http://localhost:8080", "http://localhost:5173")
    parsed = tuple(origin.strip() for origin in raw.split(",") if origin.strip())
    if "*" in parsed:
        raise ConfigurationError(
            "WEB_CORS_ORIGINS cannot contain '*' for the unauthenticated local server"
        )
    return parsed or ("http://localhost:8080", "http://localhost:5173")


@dataclass(frozen=True)
class Settings:
    # LLM providers
    anthropic_api_key: str
    openai_api_key: str
    gemini_api_key: str
    google_api_key: str

    # Video generation APIs
    kling_access_key: str
    kling_secret_key: str
    fal_key: str
    ltx_api_key: str
    runwayml_api_secret: str
    # Identity-QC embedding backbone (DeepFace model_name). Default GhostFaceNet
    # — ALL calibrated identity thresholds assume its score distribution; see
    # identity/validator.py EMBED_MODEL before changing.
    identity_embed_model: str
    # AdaFace adapter knobs (only consulted when identity_embed_model=AdaFace):
    # checkpoint path ("" → models/adaface/adaface_ir101_ms1mv2.ckpt at repo
    # root; download via scripts/download_adaface_ckpt.py) and vendored-net
    # arch (must match the checkpoint).
    identity_adaface_ckpt: str
    identity_adaface_arch: str

    # Audio / TTS
    elevenlabs_api_key: str
    cartesia_api_key: str       # Sonic 3.5 — low-latency TTS, native Korean prosody
    stability_api_key: str      # Stable Audio 2 — foley + music generation
    suno_api_key: str           # Suno V5 — full song generation with vocals
    suno_api_base: str          # Suno V5 endpoint (override for self-hosted / fork)

    # Performance capture (new phase — face/body retargeting for cinema dialogue)
    viggle_api_key: str         # Viggle — full-body motion retargeting from operator-shot phone reference

    # Google Cloud (Veo, Vertex)
    google_cloud_project: str
    google_cloud_location: str

    # Research / web
    firecrawl_api_key: str
    tavily_api_key: str

    # ComfyUI
    comfyui_server_url: str | None
    comfyui_api_key: str

    # Paths
    project_root: Path
    experiments_db_path: str
    performance_cache_dir: str   # SHA256-keyed driving-video cache (performance/_cache.py)
    pipeline_job_db_path: str    # Durable full-project queue
    pipeline_queue_concurrency: int
    cinema_trace_db_path: str    # Searchable structured trace index
    cinema_trace_retention_days: int
    cinema_trace_max_events: int

    # Performance-capture tuning
    motion_gate_samples: int     # #frame-pair samples for optical-flow scoring (performance/motion_gate.py)

    # Web server — bind address + CORS allowlist
    web_bind_host: str                  # loopback-only until authenticated remote serving exists
    web_cors_origins: tuple[str, ...]   # explicit origins; wildcard is rejected

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            anthropic_api_key=_env("ANTHROPIC_API_KEY"),
            openai_api_key=_env("OPENAI_API_KEY"),
            gemini_api_key=_env("GEMINI_API_KEY"),
            google_api_key=_env("GOOGLE_API_KEY"),
            kling_access_key=_env("KLING_ACCESS_KEY"),
            kling_secret_key=_env("KLING_SECRET_KEY"),
            fal_key=_env("FAL_KEY"),
            ltx_api_key=_env("LTX_API_KEY"),
            runwayml_api_secret=_env("RUNWAYML_API_SECRET"),
            identity_embed_model=_env("IDENTITY_EMBED_MODEL", "GhostFaceNet"),
            identity_adaface_ckpt=_env("IDENTITY_ADAFACE_CKPT", ""),
            identity_adaface_arch=_env("IDENTITY_ADAFACE_ARCH", "ir_101"),
            elevenlabs_api_key=_env("ELEVENLABS_API_KEY"),
            cartesia_api_key=_env("CARTESIA_API_KEY"),
            stability_api_key=_env("STABILITY_API_KEY"),
            # SUNO_TOKEN is the legacy alias the music module used to read
            # directly; preserve it here so the env contract is unchanged.
            suno_api_key=_env("SUNO_API_KEY") or _env("SUNO_TOKEN"),
            suno_api_base=_env("SUNO_API_BASE", "https://api.sunoapi.org"),
            viggle_api_key=_env("VIGGLE_API_KEY"),
            google_cloud_project=_env("GOOGLE_CLOUD_PROJECT"),
            google_cloud_location=_env("GOOGLE_CLOUD_LOCATION", "us-central1"),
            firecrawl_api_key=_env("FIRECRAWL_API_KEY"),
            tavily_api_key=_env("TAVILY_API_KEY"),
            comfyui_server_url=_optional_env("COMFYUI_SERVER_URL"),
            comfyui_api_key=_env("COMFYUI_API_KEY"),
            project_root=_PROJECT_ROOT,
            experiments_db_path=_env("EXPERIMENTS_DB_PATH", "data/experiments.db"),
            performance_cache_dir=_env("PERFORMANCE_CACHE_DIR", "data/cache/driving"),
            pipeline_job_db_path=(
                _env("PIPELINE_JOB_DB_PATH", "data/pipeline_jobs.db").strip()
                or "data/pipeline_jobs.db"
            ),
            pipeline_queue_concurrency=_parse_int(
                "PIPELINE_QUEUE_CONCURRENCY", 1, minimum=1, maximum=8
            ),
            cinema_trace_db_path=(
                _env("CINEMA_TRACE_DB_PATH", "data/telemetry.db").strip()
                or "data/telemetry.db"
            ),
            cinema_trace_retention_days=_parse_int(
                "CINEMA_TRACE_RETENTION_DAYS", 30, minimum=1, maximum=365
            ),
            cinema_trace_max_events=_parse_int(
                "CINEMA_TRACE_MAX_EVENTS", 50_000, minimum=1_000, maximum=1_000_000
            ),
            motion_gate_samples=_parse_int(
                "MOTION_GATE_SAMPLES", 8, minimum=1, maximum=240
            ),
            web_bind_host=_parse_loopback_bind_host(
                _env("WEB_BIND_HOST", "127.0.0.1")
            ),
            web_cors_origins=_parse_cors_origins(_env("WEB_CORS_ORIGINS", "")),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()


settings = get_settings()
