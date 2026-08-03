import logging
import aiohttp

from config import GEMINI_API_KEY, GROQ_API_KEY

logger = logging.getLogger(__name__)

# Порядок провайдеров: сначала Gemini (щедрый бесплатный лимит),
# при ошибке/исчерпании лимита — автоматический fallback на Groq.
# Оба используют OpenAI-совместимый формат, поэтому запрос и разбор
# ответа одинаковы для обоих — не нужно дублировать логику.
_PROVIDERS = [
    {
        "name": "gemini",
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "model": "gemini-2.0-flash",
        "api_key": GEMINI_API_KEY,
    },
    {
        "name": "groq",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "model": "llama-3.3-70b-versatile",
        "api_key": GROQ_API_KEY,
    },
]


async def chat_completion(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 800,
) -> str | None:
    """
    Отправляет запрос по цепочке провайдеров: Gemini -> Groq.
    Возвращает текст ответа модели, либо None, если оба провайдера недоступны
    (исчерпан лимит, сетевая ошибка, невалидный ответ).
    """
    timeout = aiohttp.ClientTimeout(total=30)

    for provider in _PROVIDERS:
        if not provider["api_key"]:
            logger.info(f"{provider['name']}: пропущен, нет API-ключа")
            continue

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    provider["url"],
                    headers={
                        "Authorization": f"Bearer {provider['api_key']}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": provider["model"],
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                ) as resp:
                    if resp.status == 429:
                        logger.warning(
                            f"{provider['name']}: лимит исчерпан (429), пробуем следующего провайдера"
                        )
                        continue

                    if resp.status != 200:
                        body = await resp.text()
                        logger.warning(f"{provider['name']}: HTTP {resp.status}: {body[:300]}")
                        continue

                    data = await resp.json()
                    content = data["choices"][0]["message"].get("content")

                    if not content:
                        logger.warning(f"{provider['name']}: пустой content в ответе")
                        continue

                    logger.info(f"{provider['name']}: успешный ответ")
                    return content

        except aiohttp.ClientError as e:
            logger.warning(f"{provider['name']}: сетевая ошибка: {e}")
            continue
        except Exception as e:
            logger.warning(f"{provider['name']}: неожиданная ошибка: {e}")
            continue

    logger.error("Все AI-провайдеры недоступны")
    return None