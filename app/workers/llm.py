"""Unified LLM client — switch provider via LLM_PROVIDER env var."""
from app.config import settings


def complete(system: str, user: str) -> str:
    """Send a system + user message and return the text response."""
    provider = settings.llm_provider.lower()

    if provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        msg = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text.strip()

    if provider in ("openai", "groq"):
        if provider == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=settings.openai_api_key)
            model = settings.openai_model
        else:
            from groq import Groq
            client = Groq(api_key=settings.groq_api_key)
            model = settings.groq_model

        resp = client.chat.completions.create(
            model=model,
            max_tokens=1024,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return (resp.choices[0].message.content or "").strip()

    raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r}. Use 'anthropic', 'openai', or 'groq'.")
