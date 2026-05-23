"""Coverage for env vars that were previously read directly via os.environ.

The single-source-of-truth pattern (config/settings.py docstring) requires
every env-derived value to land on the Settings dataclass first. These
tests lock down the fields added to absorb three pre-existing bypasses:

  * audio/music.py     — SUNO_API_KEY / SUNO_TOKEN / SUNO_API_BASE
  * performance/_cache.py        — PERFORMANCE_CACHE_DIR
  * performance/motion_gate.py   — MOTION_GATE_SAMPLES
"""
from __future__ import annotations

from config.settings import Settings


class TestNewSettingsFields:
    def test_suno_api_base_field_has_documented_default(self, monkeypatch):
        monkeypatch.delenv("SUNO_API_BASE", raising=False)
        s = Settings.from_env()
        assert s.suno_api_base == "https://api.suno.ai/v1"

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
