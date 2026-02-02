from openai import OpenAI
import logging
import traceback

logger = logging.getLogger(__name__)


def get_client(api_key: str, base_url: str | None = None, timeout: float = 120.0) -> OpenAI:
    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing. Set it in .env.")
    if base_url is not None:
        logger.info("OpenAI base_url (raw): %r", base_url)
    cleaned = (base_url or "").strip()
    if cleaned and not cleaned.startswith(("http://", "https://")):
        cleaned = "https://" + cleaned
    if not cleaned:
        cleaned = "https://api.openai.com/v1"
        logger.info("OpenAI base_url: default %s", cleaned)
    else:
        logger.info("OpenAI base_url (cleaned): %s", cleaned)
    return OpenAI(api_key=api_key, base_url=cleaned, timeout=timeout)


def _extract_response_text(response: object) -> str:
    # Preferred SDK helper when available.
    text = getattr(response, "output_text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()

    data = None
    if hasattr(response, "model_dump"):
        try:
            data = response.model_dump()
        except Exception:
            data = None
    if data is None:
        data = getattr(response, "__dict__", {})

    parts: list[str] = []
    for item in (data.get("output") or []):
        for content in (item.get("content") or []):
            if isinstance(content, dict):
                if content.get("type") in {"output_text", "text"} and content.get("text"):
                    parts.append(content["text"])

    if not parts and data.get("choices"):
        for choice in data.get("choices") or []:
            message = choice.get("message") if isinstance(choice, dict) else None
            if isinstance(message, dict) and message.get("content"):
                parts.append(message["content"])

    return "\n".join(parts).strip()


def generate_with_openai(
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 1400,
    temperature: float = 0.2,
    base_url: str | None = None,
) -> str:
    client = get_client(api_key=api_key, base_url=base_url)

    def _chat_only(selected_model: str, token_limit: int, allow_temperature: bool) -> str:
        # Boost max tokens for GPT-5 since it often truncates; cap reasonably.
        if selected_model.startswith("gpt-5"):
            token_limit = max(token_limit, 4000)
        chat_params = {
            "model": selected_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "text"},
        }
        if selected_model.startswith("gpt-5"):
            chat_params["max_completion_tokens"] = token_limit
        else:
            chat_params["max_tokens"] = token_limit
        if allow_temperature and temperature is not None:
            chat_params["temperature"] = temperature
        resp = client.chat.completions.create(**chat_params)
        content = resp.choices[0].message.content if resp and resp.choices else ""
        if not content:
            try:
                logger.warning(
                    "OpenAI chat returned empty content. model=%s id=%s usage=%s first_choice=%s",
                    selected_model,
                    getattr(resp, "id", None),
                    getattr(resp, "usage", None),
                    (resp.choices[0].model_dump() if resp and resp.choices else None),
                )
            except Exception:
                logger.warning("OpenAI chat returned empty content (logging failed).")
        return (content or "").strip()

    try:
        # For GPT-5 family, use chat.completions directly (more stable and avoids
        # max_tokens / temperature incompatibilities on responses API).
        if model.startswith("gpt-5"):
            text = _chat_only(model, max_tokens, allow_temperature=False)
            if text:
                return text
            # Fallback to a stable model if GPT-5 returned empty
            fallback_model = "gpt-4o"
            logger.warning("GPT-5 chat returned empty; falling back to %s", fallback_model)
            return _chat_only(fallback_model, min(max_tokens, 1200), allow_temperature=True)

        # For other models, prefer Responses API (cheaper), with fallback to chat.
        params = {
            "model": model,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_prompt}],
                },
            ],
            "max_output_tokens": max_tokens,
        }
        if temperature is not None:
            params["temperature"] = temperature

        response = client.responses.create(**params)
        text = _extract_response_text(response)
        if text:
            return text

        output_count = 0
        try:
            output_count = len(getattr(response, "output", []) or [])
        except Exception:
            output_count = 0
        logger.warning(
            "OpenAI response had no text output; trying chat fallback. model=%s output_items=%s response_id=%s",
            model,
            output_count,
            getattr(response, "id", None),
        )
        fallback_text = _chat_only(model, max_tokens, allow_temperature=True)
        if fallback_text:
            return fallback_text
        logger.error("Chat fallback also returned empty text.")
        return ""
    except Exception as exc:
        _raise_openai_error(exc)
 
 
def _raise_openai_error(exc: Exception) -> None:
    logger.error("OpenAI request failed: %s", exc)
    logger.error("OpenAI traceback:\n%s", traceback.format_exc())
    raise ValueError(f"OpenAI request failed: {exc}")
