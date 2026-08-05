import logging
from dataclasses import dataclass

import aiohttp

from config import GEMINI_API_KEY, GROQ_API_KEY
from services.ai.availability import ai_availability_manager

logger = logging.getLogger(__name__)

_PROVIDERS = [
    {"name": "gemini", "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "model": "gemini-2.0-flash", "api_key": GEMINI_API_KEY},
    {"name": "groq", "url": "https://api.groq.com/openai/v1/chat/completions", "model": "llama-3.3-70b-versatile", "api_key": GROQ_API_KEY},
]


@dataclass
class LLMResponse:
    content: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0


def estimate_tokens(text: str) -> int:
    return max(1, len(text or "") // 4)


def estimate_messages_tokens(messages: list[dict]) -> int:
    return sum(estimate_tokens(str(m.get("content", ""))) for m in messages)


def _usage_from_response(data: dict, fallback_input: int, fallback_output_text: str) -> tuple[int, int]:
    usage = data.get("usage") or {}
    input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens") or fallback_input
    output_tokens = usage.get("completion_tokens") or usage.get("output_tokens") or estimate_tokens(fallback_output_text)
    return int(input_tokens), int(output_tokens)


async def chat_completion(messages: list[dict], temperature: float = 0.2, max_tokens: int = 80) -> LLMResponse:
    """Send request through providers. Raises when no real AI result is available."""
    estimated_input = estimate_messages_tokens(messages)
    ai_availability_manager.ensure_can_call(estimated_input)
    timeout = aiohttp.ClientTimeout(total=30)
    last_reason = "provider_error"

    for provider in _PROVIDERS:
        if not provider["api_key"]:
            logger.info("%s: skipped, no API key", provider["name"])
            continue
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    provider["url"],
                    headers={"Authorization": f"Bearer {provider['api_key']}", "Content-Type": "application/json"},
                    json={"model": provider["model"], "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
                ) as resp:
                    if resp.status == 429:
                        last_reason = "quota_exceeded"
                        logger.warning("%s: quota exhausted (429)", provider["name"])
                        continue
                    if resp.status != 200:
                        body = await resp.text()
                        logger.warning("%s: HTTP %s: %s", provider["name"], resp.status, body[:300])
                        continue
                    data = await resp.json()
                    content = data["choices"][0]["message"].get("content")
                    if not content:
                        logger.warning("%s: empty content", provider["name"])
                        continue
                    input_tokens, output_tokens = _usage_from_response(data, estimated_input, content)
                    ai_availability_manager.record_usage(success=True, input_tokens=input_tokens, output_tokens=output_tokens)
                    if not ai_availability_manager.get_state().is_available:
                        ai_availability_manager.mark_available()
                    logger.info("%s: successful AI response", provider["name"])
                    return LLMResponse(content=content, provider=provider["name"], input_tokens=input_tokens, output_tokens=output_tokens)
        except TimeoutError:
            last_reason = "timeout"
            logger.warning("%s: timeout", provider["name"])
        except aiohttp.ClientError as e:
            last_reason = "provider_error"
            logger.warning("%s: network error: %s", provider["name"], e)
        except Exception as e:
            last_reason = "unknown"
            logger.warning("%s: unexpected error: %s", provider["name"], e)

    ai_availability_manager.record_usage(success=False, input_tokens=estimated_input, provider_error=True)
    ai_availability_manager.mark_unavailable(last_reason)
    raise RuntimeError(f"All AI providers unavailable: {last_reason}")
