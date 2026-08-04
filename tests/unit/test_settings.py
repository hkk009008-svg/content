"""Coverage for env vars that were previously read directly via os.environ.

The single-source-of-truth pattern (config/settings.py docstring) requires
every env-derived value to land on the Settings dataclass first. These
tests lock down the fields added to absorb three pre-existing bypasses:

  * audio/music.py     — SUNO_API_KEY / SUNO_TOKEN / SUNO_API_BASE
  * performance/_cache.py        — PERFORMANCE_CACHE_DIR
  * performance/motion_gate.py   — MOTION_GATE_SAMPLES
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from config.settings import ConfigurationError, Settings


class TestNewSettingsFields:
    def test_suno_api_base_field_has_documented_default(self, monkeypatch):
        monkeypatch.delenv("SUNO_API_BASE", raising=False)
        s = Settings.from_env()
        # sunoapi.org is the production provider (audio/music.py); the default was
        # moved off the old api.suno.ai/v1 stub in c8f931d (Suno V5 router wiring).
        assert s.suno_api_base == "https://api.sunoapi.org"

    def test_suno_api_base_reads_from_env(self, monkeypatch):
        monkeypatch.setenv("SUNO_API_BASE", "https://api.suno.dev/v2")
        s = Settings.from_env()
        assert s.suno_api_base == "https://api.suno.dev/v2"

    def test_performance_cache_dir_default(self, monkeypatch):
        monkeypatch.delenv("PERFORMANCE_CACHE_DIR", raising=False)
        s = Settings.from_env()
        assert s.performance_cache_dir == "data/cache/driving"

    def test_performance_cache_dir_reads_from_env(self, monkeypatch):
        monkeypatch.setenv("PERFORMANCE_CACHE_DIR", "/tmp/driving")
        s = Settings.from_env()
        assert s.performance_cache_dir == "/tmp/driving"

    def test_motion_gate_samples_default_is_int(self, monkeypatch):
        monkeypatch.delenv("MOTION_GATE_SAMPLES", raising=False)
        s = Settings.from_env()
        assert s.motion_gate_samples == 8
        assert isinstance(s.motion_gate_samples, int)

    def test_motion_gate_samples_coerces_env_string_to_int(self, monkeypatch):
        monkeypatch.setenv("MOTION_GATE_SAMPLES", "16")
        s = Settings.from_env()
        assert s.motion_gate_samples == 16
        assert isinstance(s.motion_gate_samples, int)

    @pytest.mark.parametrize("value", ["not-an-int", "0", "241"])
    def test_invalid_motion_gate_samples_is_named_configuration_error(
        self, monkeypatch, value
    ):
        monkeypatch.setenv("MOTION_GATE_SAMPLES", value)
        with pytest.raises(ConfigurationError, match="MOTION_GATE_SAMPLES"):
            Settings.from_env()

    def test_comfyui_is_unconfigured_when_env_is_absent(self, monkeypatch):
        monkeypatch.delenv("COMFYUI_SERVER_URL", raising=False)
        assert Settings.from_env().comfyui_server_url is None

    @pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.5", "content.local"])
    def test_unauthenticated_remote_bind_is_rejected(self, monkeypatch, host):
        monkeypatch.setenv("WEB_BIND_HOST", host)
        with pytest.raises(ConfigurationError, match="loopback"):
            Settings.from_env()

    @pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost"])
    def test_loopback_bind_is_accepted(self, monkeypatch, host):
        monkeypatch.setenv("WEB_BIND_HOST", host)
        assert Settings.from_env().web_bind_host == host

    def test_wildcard_cors_is_rejected(self, monkeypatch):
        monkeypatch.setenv("WEB_CORS_ORIGINS", "*")
        with pytest.raises(ConfigurationError, match="WEB_CORS_ORIGINS"):
            Settings.from_env()


def test_process_environment_outranks_repository_dotenv():
    """Deployment-injected values must not be replaced while importing settings."""

    env = os.environ.copy()
    env["OPENAI_API_KEY"] = "deployment-authority-value"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from config.settings import settings; print(settings.openai_api_key)",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "deployment-authority-value"


class TestSunoTokenAlias:
    """Preserve the SUNO_TOKEN alias that audio/music.py historically honored."""

    def test_suno_api_key_falls_back_to_suno_token(self, monkeypatch):
        monkeypatch.delenv("SUNO_API_KEY", raising=False)
        monkeypatch.setenv("SUNO_TOKEN", "legacy-token-value")
        s = Settings.from_env()
        assert s.suno_api_key == "legacy-token-value"

    def test_suno_api_key_preferred_over_suno_token(self, monkeypatch):
        monkeypatch.setenv("SUNO_API_KEY", "primary-key")
        monkeypatch.setenv("SUNO_TOKEN", "legacy-token-value")
        s = Settings.from_env()
        assert s.suno_api_key == "primary-key"
