"""Mock-mode detection + the /api/llm-status endpoint the UI warns from."""
from types import SimpleNamespace


def _settings(provider, ak="", ok=""):
    return SimpleNamespace(llm_provider=provider, anthropic_api_key=ak, openai_api_key=ok,
                           ollama_base_url="http://x")


def test_active_provider_is_mock(monkeypatch):
    from app.agent import llm

    monkeypatch.setattr(llm, "get_settings", lambda: _settings("mock"))
    assert llm.active_provider_is_mock() is True
    monkeypatch.setattr(llm, "get_settings", lambda: _settings("anthropic", ""))
    assert llm.active_provider_is_mock() is True            # configured but keyless -> mock
    monkeypatch.setattr(llm, "get_settings", lambda: _settings("anthropic", "   "))
    assert llm.active_provider_is_mock() is True            # whitespace-only key -> still mock
    monkeypatch.setattr(llm, "get_settings", lambda: _settings("anthropic", "sk-x"))
    assert llm.active_provider_is_mock() is False
    monkeypatch.setattr(llm, "get_settings", lambda: _settings("openai", "", "sk-o"))
    assert llm.active_provider_is_mock() is False
    monkeypatch.setattr(llm, "get_settings", lambda: _settings("ollama"))
    assert llm.active_provider_is_mock() is False
    monkeypatch.setattr(llm, "get_settings", lambda: _settings("weird-unknown"))
    assert llm.active_provider_is_mock() is True            # unrecognized -> treat as mock


def test_llm_status_endpoint(monkeypatch):
    from fastapi.testclient import TestClient

    from app import config
    from app.agent import llm
    from app.main import app

    # Pin settings so the endpoint is deterministic regardless of the runner's env/.env.
    fake = _settings("mock")
    monkeypatch.setattr(config, "get_settings", lambda: fake)
    monkeypatch.setattr(llm, "get_settings", lambda: fake)
    body = TestClient(app).get("/api/llm-status").json()
    assert set(body) == {"mock", "provider"} and isinstance(body["mock"], bool)
    assert body["provider"] == "mock" and body["mock"] is True  # keyless mock -> honestly mock
