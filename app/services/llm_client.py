from app.config import settings
from app.services.claude_client import generate_with_claude
from app.services.openai_client import generate_with_openai


def _normalized_provider(provider: str | None) -> str:
    value = (provider or settings.llm_provider or "anthropic").strip().lower()
    if value in {"openai", "gpt", "gpt-5", "gpt-5-mini"}:
        return "openai"
    return "anthropic"


def get_active_model(provider: str | None = None) -> str:
    provider_name = _normalized_provider(provider)
    if provider_name == "openai":
        return settings.openai_model
    return settings.claude_model


def generate_with_llm(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 1400,
    temperature: float = 0.2,
    provider: str | None = None,
    model: str | None = None,
) -> str:
    provider_name = _normalized_provider(provider)
    if provider_name == "openai":
        return generate_with_openai(
            api_key=settings.openai_api_key,
            model=model or settings.openai_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            base_url=settings.openai_base_url or None,
        )

    return generate_with_claude(
        api_key=settings.anthropic_api_key,
        model=model or settings.claude_model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=max_tokens,
        temperature=temperature,
    )
