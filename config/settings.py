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

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env", override=True)


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _parse_cors_origins(raw: str) -> tuple[str, ...]:
    """Parse WEB_CORS_ORIGINS env into a tuple of origin patterns.

    Empty / unset → safe localhost-only default. To intentionally allow
    every origin (the pre-2026-05-23 wide-open behavior), set
    WEB_CORS_ORIGINS=*. To allow LAN access, set the env to a
    comma-separated list including the LAN IP, e.g.
    ``WEB_CORS_ORIGINS=http://localhost:8080,http://192.168.1.50:8080``.
    """
    if not raw.strip():
        return ("http://localhost:8080", "http://localhost:5173")
    parsed = tuple(origin.strip() for origin in raw.split(",") if origin.strip())
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
    seedance_api_key: str

    # Audio / TTS
    elevenlabs_api_key: str
    cartesia_api_key: str       # Sonic 2 — low-latency TTS, native Korean prosody
    stability_api_key: str      # Stable Audio 2 — foley + music generation
    suno_api_key: str           # Suno V5 — full song generation with vocals
    suno_api_base: str          # Suno V5 endpoint (override for self-hosted / fork)

    # Performance capture (new phase — face/body retargeting for cinema dialogue)
    viggle_api_key: str         # Viggle — full-body motion retargeting from operator-shot phone reference
    hedra_api_key: str          # Hedra — audio-driven driving-face synth (Mode B autopilot)

    # Google Cloud (Veo, Vertex)
    google_cloud_project: str
    google_cloud_location: str

    # Research / web
    firecrawl_api_key: str
    pexels_api_key: str
    tavily_api_key: str

    # ComfyUI
    comfyui_server_url: str

    # Paths
    project_root: Path
    experiments_db_path: str
    performance_cache_dir: str   # SHA256-keyed driving-video cache (performance/_cache.py)

    # Performance-capture tuning
    motion_gate_samples: int     # #frame-pair samples for optical-flow scoring (performance/motion_gate.py)

    # Web server — bind address + CORS allowlist
    web_bind_host: str                  # default 127.0.0.1 (loopback only). Set WEB_BIND_HOST=0.0.0.0 to expose on LAN.
    web_cors_origins: tuple[str, ...]   # default localhost dev origins. Set WEB_CORS_ORIGINS=* for wide-open (pre-hardening default).

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
            seedance_api_key=_env("SEEDANCE_API_KEY"),
            elevenlabs_api_key=_env("ELEVENLABS_API_KEY"),
            cartesia_api_key=_env("CARTESIA_API_KEY"),
            stability_api_key=_env("STABILITY_API_KEY"),
            # SUNO_TOKEN is the legacy alias the music module used to read
            # directly; preserve it here so the env contract is unchanged.
            suno_api_key=_env("SUNO_API_KEY") or _env("SUNO_TOKEN"),
            suno_api_base=_env("SUNO_API_BASE", "https://api.suno.ai/v1"),
            viggle_api_key=_env("VIGGLE_API_KEY"),
            hedra_api_key=_env("HEDRA_API_KEY"),
            google_cloud_project=_env("GOOGLE_CLOUD_PROJECT"),
            google_cloud_location=_env("GOOGLE_CLOUD_LOCATION", "us-central1"),
            firecrawl_api_key=_env("FIRECRAWL_API_KEY"),
            pexels_api_key=_env("PEXELS_API_KEY"),
            tavily_api_key=_env("TAVILY_API_KEY"),
            comfyui_server_url=_env("COMFYUI_SERVER_URL", "http://127.0.0.1:8188"),
            project_root=_PROJECT_ROOT,
            experiments_db_path=_env("EXPERIMENTS_DB_PATH", "data/experiments.db"),
            performance_cache_dir=_env("PERFORMANCE_CACHE_DIR", "data/cache/driving"),
            motion_gate_samples=int(_env("MOTION_GATE_SAMPLES", "8")),
            web_bind_host=_env("WEB_BIND_HOST", "127.0.0.1"),
            web_cors_origins=_parse_cors_origins(_env("WEB_CORS_ORIGINS", "")),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()


settings = get_settings()
