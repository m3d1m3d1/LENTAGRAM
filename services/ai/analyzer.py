import logging
import json

from services.ai.llm_client import chat_completion

logger = logging.getLogger(__name__)


class AIAnalyzer:
    """
    AI слой Lentagram.
    Анализирует Telegram посты:
    - релевантность;
    - категорию;
    - краткое содержание;
    - важность;
    - ключевые слова.

    Использует общий клиент с fallback Gemini -> Groq.
    """

    async def analyze_post(self, text: str, filter_prompt: str | None = None):
        rules = filter_prompt or "нет специальных правил — пропускать всё"

        prompt = (
            "Ты — AI-фильтр Telegram-ленты. Ответь СТРОГО JSON без markdown.\n\n"
            "Задача:\n"
            "1. Определи, подходит ли пост под правила пользователя.\n"
            "2. Если подходит: relevant=true, дай категорию, summary (1-2 предложения), важность 1-10, причину важности, 3-5 ключевых слов.\n"
            "3. Если НЕ подходит: relevant=false, остальные поля пустые/null.\n\n"
            f"Правила фильтра: {rules}\n\n"
            f"Текст поста:\n{text[:2000]}\n\n"
            "Верни ТОЛЬКО JSON:\n"
            '{"relevant":true,"category":"IT","summary":"краткий пересказ","importance":7,"importance_reason":"почему важно","keywords":["слово1","слово2"]}'
        )

        content = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=500,
        )

        if not content:
            return self._fallback()

        content = content.replace("```json", "").replace("```", "").strip()
        logger.info(f"AI content raw: {content[:300]}")

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"AI не-JSON: {e}")
            return self._fallback()

        if not isinstance(parsed, dict):
            logger.warning(f"AI вернул не-словарь: {type(parsed)}")
            return self._fallback()

        raw_importance = parsed.get("importance")
        importance = int(raw_importance) if raw_importance is not None else 1

        return {
            "relevant": bool(parsed.get("relevant", True)),
            "category": parsed.get("category"),
            "summary": parsed.get("summary"),
            "importance": importance,
            "importance_reason": parsed.get("importance_reason"),
            "keywords": parsed.get("keywords") or [],
        }

    def _fallback(self):
        return {
            "relevant": True,
            "category": None,
            "summary": None,
            "importance": 1,
            "importance_reason": "Не удалось выполнить AI-анализ",
            "keywords": []
        }