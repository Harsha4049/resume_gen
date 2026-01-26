from anthropic import Anthropic


def get_client(api_key: str) -> Anthropic:
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is missing. Set it in .env.")
    return Anthropic(api_key=api_key)


def generate_with_claude(
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 1400,
    temperature: float = 0.2,
) -> str:
    client = get_client(api_key)

    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    out = []
    for block in msg.content:
        if getattr(block, "type", None) == "text":
            out.append(block.text)
    return "\n".join(out).strip()
