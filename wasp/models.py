import os


def build_model():
    provider = os.getenv("LLM_PROVIDER", "ollama")
    if provider == "ollama":
        from agno.models.ollama import Ollama

        return Ollama(
            id=os.getenv("OLLAMA_MODEL", "llama3.1"),
            host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        )
    if provider == "anthropic":
        from agno.models.anthropic import Claude

        return Claude(
            id=os.getenv("ANTHROPIC_MODEL", "anthropic.claude-4-6-sonnet"),
            auth_token=os.getenv("ANTHROPIC_AUTH_TOKEN"),
        )
    if provider == "openai":
        from agno.models.openai import OpenAIChat

        return OpenAIChat(
            id=os.getenv("OPENAI_MODEL", "gpt-4o"),
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL") or None,
        )
    raise ValueError(
        f"Invalid LLM_PROVIDER: {provider!r}. Use: ollama, anthropic, openai"
    )
