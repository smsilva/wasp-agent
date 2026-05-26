import pytest


def test_build_model_ollama(mock_agno, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.1")
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")

    from wasp.models import build_model

    build_model()

    mock_agno["agno.models.ollama"].Ollama.assert_called_once_with(
        id="llama3.1", host="http://localhost:11434"
    )


def test_build_model_anthropic(mock_agno, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok")

    from wasp.models import build_model

    build_model()

    mock_agno["agno.models.anthropic"].Claude.assert_called_once_with(
        id="claude-sonnet", auth_token="tok"
    )


def test_build_model_openai(mock_agno, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    from wasp.models import build_model

    build_model()

    mock_agno["agno.models.openai"].OpenAIChat.assert_called_once_with(
        id="gpt-4o", api_key="sk-test", base_url=None
    )


def test_build_model_openai_with_base_url(mock_agno, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://proxy:8080")

    from wasp.models import build_model

    build_model()

    mock_agno["agno.models.openai"].OpenAIChat.assert_called_once_with(
        id="gpt-4o", api_key="sk-test", base_url="http://proxy:8080"
    )


def test_build_model_unknown_raises(mock_agno, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "unknown")

    from wasp.models import build_model

    with pytest.raises(ValueError, match="Invalid LLM_PROVIDER"):
        build_model()
