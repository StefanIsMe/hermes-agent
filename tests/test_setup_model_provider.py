"""Regression tests for interactive setup provider/model persistence."""

from __future__ import annotations

import yaml


def _read_env(home):
    env_path = home / ".env"
    data = {}
    if not env_path.exists():
        return data
    for line in env_path.read_text().splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k] = v
    return data


def test_setup_keep_current_custom_does_not_fall_through(tmp_path, monkeypatch):
    """Selecting "Keep current" on a custom provider must remain custom."""
    from hermes_cli.config import save_env_value
    from hermes_cli.setup import setup_model_provider

    home = tmp_path / "hermes"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.delenv("HERMES_INFERENCE_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    # Existing custom endpoint + OR key (skip optional OpenRouter prompt).
    save_env_value("OPENAI_BASE_URL", "https://example.invalid/v1")
    save_env_value("OPENAI_API_KEY", "sk-custom")
    save_env_value("OPENROUTER_API_KEY", "sk-or")

    monkeypatch.setattr("hermes_cli.auth.get_active_provider", lambda: None)
    monkeypatch.setattr("hermes_cli.auth.detect_external_credentials", lambda: [])

    calls = {"count": 0}

    def fake_prompt_choice(_question, choices, default=0):
        calls["count"] += 1
        # First menu = provider menu. Pick "Keep current (...)".
        if calls["count"] == 1:
            return len(choices) - 1
        raise AssertionError("Model menu should not appear for keep-current custom")

    monkeypatch.setattr("hermes_cli.setup.prompt_choice", fake_prompt_choice)
    monkeypatch.setattr("hermes_cli.setup.prompt", lambda *args, **kwargs: "")
    monkeypatch.setattr("hermes_cli.setup.prompt_yes_no", lambda *args, **kwargs: False)

    setup_model_provider({"model": "glm-5"})

    env = _read_env(home)
    assert env.get("HERMES_INFERENCE_PROVIDER") == "custom"
    assert calls["count"] == 1


def test_setup_switch_custom_to_codex_updates_provider(tmp_path, monkeypatch):
    """Switching provider to OpenAI Codex must persist provider + clear custom URL."""
    from hermes_cli.config import save_env_value
    from hermes_cli.setup import setup_model_provider

    home = tmp_path / "hermes"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.delenv("HERMES_INFERENCE_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    # Start from custom endpoint state.
    save_env_value("OPENAI_BASE_URL", "https://example.invalid/v1")
    save_env_value("OPENAI_API_KEY", "sk-custom")
    save_env_value("OPENROUTER_API_KEY", "sk-or")

    monkeypatch.setattr("hermes_cli.auth.get_active_provider", lambda: None)
    monkeypatch.setattr("hermes_cli.auth.detect_external_credentials", lambda: [])
    monkeypatch.setattr("hermes_cli.auth._login_openai_codex", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "hermes_cli.codex_models.get_codex_model_ids",
        lambda: ["openai/gpt-5.3-codex", "openai/gpt-5-codex-mini"],
    )

    # 1st prompt_choice = provider (OpenAI Codex index), 2nd = model pick.
    picks = iter([2, 0])
    monkeypatch.setattr("hermes_cli.setup.prompt_choice", lambda *args, **kwargs: next(picks))
    monkeypatch.setattr("hermes_cli.setup.prompt", lambda *args, **kwargs: "")
    monkeypatch.setattr("hermes_cli.setup.prompt_yes_no", lambda *args, **kwargs: False)

    setup_model_provider({"model": "glm-5"})

    env = _read_env(home)
    assert env.get("HERMES_INFERENCE_PROVIDER") == "openai-codex"
    assert env.get("OPENAI_BASE_URL", None) == ""

    cfg = yaml.safe_load((home / "config.yaml").read_text()) or {}
    model_cfg = cfg.get("model")
    if isinstance(model_cfg, dict):
        assert model_cfg.get("provider") == "openai-codex"
        assert model_cfg.get("default") == "openai/gpt-5.3-codex"
    else:
        assert model_cfg == "openai/gpt-5.3-codex"
