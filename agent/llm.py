"""LLM wrapper: anthropic | openrouter | gemini. Returns None if no key or on failure,
so callers fall back to the heuristic/template path.

LLM_MODEL may be a comma-separated list; for openrouter/gemini the models are tried in order."""
import traceback

import requests

from .config import get

# OpenRouter and Gemini both expose an OpenAI-compatible chat endpoint
OPENAI_COMPAT = {
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "GEMINI_API_KEY"),
}


def complete(system: str, user: str, max_tokens: int = 900):
    provider = get("LLM_PROVIDER", "openrouter").lower()
    model = get("LLM_MODEL")
    try:
        if provider == "anthropic":
            key = get("ANTHROPIC_API_KEY")
            if not key:
                return None
            import anthropic

            msg = anthropic.Anthropic(api_key=key).messages.create(
                model=model or "claude-sonnet-5-5", max_tokens=max_tokens, system=system,
                messages=[{"role": "user", "content": user}])
            return "".join(b.text for b in msg.content if b.type == "text").strip()

        url, key_name = OPENAI_COMPAT[provider]
        key = get(key_name)
        models = [m.strip() for m in model.split(",") if m.strip()]
        if not key or not models:
            return None
        for m in models:
            r = requests.post(
                url,
                headers={"Authorization": f"Bearer {key}"},
                json={"model": m, "max_tokens": max_tokens * 2,  # headroom for "thinking" models
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": user}]},
                timeout=60,
            )
            if r.ok:
                text = (r.json()["choices"][0]["message"]["content"] or "").strip()
                if text:
                    return text
            else:
                print(f"LLM error ({m}):", r.status_code, r.text[:200])
        return None
    except Exception:
        traceback.print_exc()
        return None