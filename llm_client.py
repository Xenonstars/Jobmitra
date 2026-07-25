import json
import requests
import structlog

from config import settings

logger = structlog.get_logger(__name__)


def _ollama_chat(prompt: str, model: str, max_tokens: int, temperature: float) -> str:
    import ollama

    response = ollama.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        options={"num_predict": max_tokens, "temperature": temperature},
    )
    return response["message"]["content"]


def _groq_chat(prompt: str, model: str, max_tokens: int, temperature: float) -> str:
    if not settings.GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY must be set when LLM_PROVIDER=groq")

    url = settings.GROQ_BASE_URL.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_output_tokens": max_tokens,
        "temperature": temperature,
    }
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    response = requests.post(url, json=payload, headers=headers, timeout=settings.LLM_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


def llm_chat(prompt: str, model: str, max_tokens: int, temperature: float) -> str:
    provider = settings.LLM_PROVIDER.lower()
    if provider == "ollama":
        return _ollama_chat(prompt, model, max_tokens, temperature)
    if provider == "groq":
        return _groq_chat(prompt, model, max_tokens, temperature)
    if provider == "anthropic":
        raise NotImplementedError("Anthropic provider is not implemented in this repository.")
    raise ValueError(f"Unsupported LLM provider: {settings.LLM_PROVIDER}")
