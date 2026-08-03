import json
import logging
import aiohttp

from config import OPENROUTER_API_KEY

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "Ты — фильтр релевантности постов для персональной новостной ленты. "
    "Тебе дают тему ленты и текст поста из Telegram-канала. "
    "Верни СТРОГО JSON без markdown-обёртки и лишнего текста, "
    'в формате {"relevant": true|false, "reason": "краткое обоснование в одном предложении"}. '
    "relevant = true, если пост по смыслу подходит теме ленты. "
    "Если тема ленты не задана (пустая) — всегда relevant = true."
)

# Бесплатная модель на OpenRouter
DEFAULT_MODEL = "meta-llama/llama-3.1-8b-instruct"

# Прокси для обхода блокировок (Xray/Happ на 127.0.0.1:10808)
#PROXY_URL = "http://127.0.0.1:10808"


class AIClassifier:
    """
    Тонкая обёртка над OpenRouter API (бесплатные модели).
    Если ключ не задан или запрос падает — fail-open:
    считает пост релевантным, чтобы сломанный ИИ-вызов
    не проглатывал реальные посты пользователя.
    """

    def __init__(self):
        self.enabled = bool(OPENROUTER_API_KEY)
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"

    async def is_relevant(self, topic: str | None, post_text: str) -> tuple[bool, str]:
        """Возвращает (relevant, reason). Без темы или без ключа — всегда (True, ...)."""
        if not topic or not topic.strip():
            return True, "у ленты не задана тема — фильтрация не применяется"

        if not self.enabled:
            return True, "ИИ-классификатор отключён (нет OPENROUTER_API_KEY)"

        if not post_text or not post_text.strip():
            return False, "пустой текст поста (например, только медиа без подписи)"

        user_message = (
            f"Тема ленты: {topic}\n\n"
            f"Текст поста:\n{post_text[:3000]}"
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url,
#                   proxy= none,  # Через Xray/Happ
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://github.com/lentagram",
                        "X-Title": "Lentagram Bot",
                    },
                    json={
                        "model": DEFAULT_MODEL,
                        "messages": [
                            {"role": "system", "content": _SYSTEM_PROMPT},
                            {"role": "user", "content": user_message},
                        ],
                        "max_tokens": 200,
                        "temperature": 0.1,
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.warning(f"OpenRouter вернул {resp.status}: {text}")
                        return True, f"ошибка API ({resp.status}) — пост пропущен без фильтрации"

                    data = await resp.json()
                    raw_text = data["choices"][0]["message"]["content"].strip()

                    raw_text = raw_text.replace("```json", "").replace("```", "").strip()

                    parsed = json.loads(raw_text)
                    return bool(parsed.get("relevant", True)), str(parsed.get("reason", ""))

        except aiohttp.ClientError as e:
            logger.warning(f"Сетевая ошибка OpenRouter: {e}")
            return True, "сетевая ошибка — пост пропущен без фильтрации"
        except json.JSONDecodeError as e:
            logger.warning(f"OpenRouter вернул не-JSON: {e}")
            return True, "невалидный ответ модели — пост пропущен без фильтрации"
        except Exception as e:
            logger.warning(f"Ошибка ИИ-классификации: {e}")
            return True, "ошибка вызова ИИ — пост пропущен без фильтрации"