"""Keyless and configured-client boundaries for llm/ensemble.py."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import llm.ensemble as ensemble_module
from llm.ensemble import LLMEnsemble


def _provider_settings(**overrides):
    values = {
        "anthropic_api_key": "",
        "openai_api_key": "",
        "gemini_api_key": "",
        "google_api_key": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture
def keyless_ensemble(monkeypatch):
    monkeypatch.setattr(ensemble_module, "env_settings", _provider_settings())
    return LLMEnsemble()


def test_fully_keyless_constructor_leaves_optional_clients_none(
    monkeypatch,
):
    tracker = object()
    monkeypatch.setattr(ensemble_module, "env_settings", _provider_settings())

    ensemble = LLMEnsemble(cost_tracker=tracker)

    assert ensemble.anthropic_client is None
    assert ensemble.openai_client is None
    assert ensemble.gemini_client is None
    assert ensemble.cost_tracker is tracker


def test_keyless_constructor_does_not_import_provider_sdks():
    code = r"""
import importlib
import importlib.abc
import sys
from types import SimpleNamespace

blocked_roots = {"anthropic", "openai", "google"}
for module_name in list(sys.modules):
    if module_name.split(".", 1)[0] in blocked_roots:
        del sys.modules[module_name]

class ProviderImportBlocker(importlib.abc.MetaPathFinder):
    def __init__(self):
        self.attempted = []

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".", 1)[0] in blocked_roots:
            self.attempted.append(fullname)
            raise RuntimeError(f"blocked provider import: {fullname}")
        return None

blocker = ProviderImportBlocker()
sys.meta_path.insert(0, blocker)

import llm.ensemble as ensemble_module
ensemble_module.env_settings = SimpleNamespace(
    anthropic_api_key="",
    openai_api_key="",
    gemini_api_key="",
    google_api_key="",
)
ensemble = ensemble_module.LLMEnsemble()
assert ensemble.anthropic_client is None
assert ensemble.openai_client is None
assert ensemble.gemini_client is None
assert blocker.attempted == []

try:
    importlib.import_module("anthropic")
except RuntimeError as exc:
    assert "blocked provider import: anthropic" in str(exc)
else:
    raise AssertionError("provider import blocker was not active")
assert blocker.attempted == ["anthropic"]
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[2],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("judge_alias", "expected_model"),
    [
        ("claude-opus", "claude-opus-4-8"),
        ("gpt-4o", "gpt-4o"),
        ("gemini-pro", "gemini-2.5-pro"),
    ],
)
def test_settings_and_judge_aliases_apply_keyless(
    monkeypatch, judge_alias, expected_model
):
    monkeypatch.setattr(ensemble_module, "env_settings", _provider_settings())

    ensemble = LLMEnsemble(
        settings={
            "competitive_generation": False,
            "quality_judge_llm": judge_alias,
        }
    )

    assert ensemble.competitive_enabled is False
    assert ensemble.judge_model_override == expected_model
    assert ensemble.anthropic_client is None
    assert ensemble.openai_client is None
    assert ensemble.gemini_client is None


def test_direct_anthropic_call_names_missing_credential(keyless_ensemble):
    with pytest.raises(RuntimeError, match=r"Anthropic.*ANTHROPIC_API_KEY"):
        keyless_ensemble._generate_anthropic("claude-sonnet", "system", "user")


def test_direct_openai_call_names_missing_credential(keyless_ensemble):
    with pytest.raises(RuntimeError, match=r"OpenAI.*OPENAI_API_KEY"):
        keyless_ensemble._generate_openai("gpt-4o", "system", "user")


def test_direct_gemini_call_names_missing_credentials(keyless_ensemble):
    with pytest.raises(
        RuntimeError,
        match=r"Gemini.*GEMINI_API_KEY / GOOGLE_API_KEY",
    ):
        keyless_ensemble._generate_gemini("gemini-2.5-pro", "system", "user")


@pytest.mark.parametrize(
    "model",
    ["claude-sonnet-4-6", "gpt-4o", "gemini-2.5-pro"],
)
def test_generate_single_degrades_missing_client_to_none(
    keyless_ensemble, model
):
    assert keyless_ensemble._generate_single(model, "system", "user") == (
        model,
        None,
    )


def test_configured_clients_keep_explicit_timeouts(monkeypatch):
    monkeypatch.setattr(
        ensemble_module,
        "env_settings",
        _provider_settings(
            anthropic_api_key="anthropic-test-key",
            openai_api_key="openai-test-key",
            gemini_api_key="gemini-test-key",
        ),
    )
    anthropic_client = MagicMock()
    openai_client = MagicMock()
    gemini_client = MagicMock()
    http_options = MagicMock()

    with (
        patch(
            "anthropic.Anthropic",
            return_value=anthropic_client,
        ) as anthropic_cls,
        patch(
            "openai.OpenAI",
            return_value=openai_client,
        ) as openai_cls,
        patch(
            "google.genai.types.HttpOptions",
            return_value=http_options,
        ) as http_options_cls,
        patch(
            "google.genai.Client",
            return_value=gemini_client,
        ) as gemini_cls,
    ):
        ensemble = LLMEnsemble()

    anthropic_cls.assert_called_once_with(
        api_key="anthropic-test-key",
        timeout=120.0,
    )
    openai_cls.assert_called_once_with(
        api_key="openai-test-key",
        timeout=120.0,
    )
    http_options_cls.assert_called_once_with(timeout=120_000)
    gemini_cls.assert_called_once_with(
        api_key="gemini-test-key",
        http_options=http_options,
    )
    assert ensemble.anthropic_client is anthropic_client
    assert ensemble.openai_client is openai_client
    assert ensemble.gemini_client is gemini_client
