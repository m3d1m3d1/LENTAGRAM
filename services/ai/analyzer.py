import json
import logging
import re

from services.ai.llm_client import chat_completion
from services.ai.availability import ai_availability_manager

logger = logging.getLogger(__name__)

POST_PREVIEW_LIMIT = 600
CATEGORIES = {"AI", "TECH", "WAR", "BUSINESS", "SPORT", "SCIENCE", "FINANCE", "OTHER"}
IMPORTANCE_LEVELS = {"HIGH", "MEDIUM", "LOW"}
URL_ONLY_RE = re.compile(r"^(?:https?://\S+|www\.\S+)(?:\s+(?:https?://\S+|www\.\S+))*$", re.IGNORECASE)
TEXT_RE = re.compile(r"[\wА-Яа-яЁё]", re.UNICODE)


class AIAnalyzer:
    """
    AI слой Lentagram.
    Анализирует Telegram посты:
    - релевантность;
    - категорию;
    - важность.

    Использует общий клиент с fallback Gemini -> Groq.
    """

    async def analyze_post(self, text: str, filter_prompt: str | None = None):
        if self._is_obviously_irrelevant(text):
            return {
                "relevant": False,
                "category": "OTHER",
                "importance": "LOW",
            }

        rules = filter_prompt or "No special rules; accept all useful posts."
        post_preview = text[:POST_PREVIEW_LIMIT]

        prompt = (
            "Classify this Telegram post for a user feed. Return JSON only. "
            "Fields: relevant boolean; category one of AI,TECH,WAR,BUSINESS,SPORT,SCIENCE,FINANCE,OTHER only; "
            "importance one of HIGH,MEDIUM,LOW only.\n"
            f"Rules: {rules}\n"
            f"Post: {post_preview}\n"
            '{"relevant":true,"category":"AI","importance":"MEDIUM"}'
        )

        response = await chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=50,
        )

        content = response.content
        content = content.replace("```json", "").replace("```", "").strip()
        logger.info(f"AI content raw: {content[:300]}")

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"AI не-JSON: {e}")
            ai_availability_manager.mark_unavailable("provider_error")
            raise RuntimeError("AI returned invalid analysis")

        if not isinstance(parsed, dict):
            logger.warning(f"AI вернул не-словарь: {type(parsed)}")
            ai_availability_manager.mark_unavailable("provider_error")
            raise RuntimeError("AI returned invalid analysis")

        category = str(parsed.get("category") or "OTHER").upper()
        if category not in CATEGORIES:
            category = "OTHER"

        importance = str(parsed.get("importance") or "LOW").upper()
        if importance not in IMPORTANCE_LEVELS:
            importance = "LOW"

        return {
            "relevant": bool(parsed.get("relevant", True)),
            "category": category,
            "importance": importance,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "provider": response.provider,
        }

    def _is_obviously_irrelevant(self, text: str) -> bool:
        stripped = (text or "").strip()
        if len(stripped) < 20:
            return True
        if URL_ONLY_RE.fullmatch(stripped):
            return True
        return not TEXT_RE.search(stripped)

