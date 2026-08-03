import logging

logger = logging.getLogger(__name__)


class AISummarizer:
    prompt = f"""
    Ты профессиональный редактор новостей.

    Твоя задача:
    сделать краткое понятное объяснение новости.

    Текст:
    {text}

    Создай:

    summary:
    - 1-3 предложения
    - объясни что произошло
    - почему это важно
    - не копируй оригинальный текст


    Пример:

    Оригинал:
    "OpenAI выпустила GPT-5"

    Плохо:
    "OpenAI выпустила GPT-5"

    Хорошо:
    "Компания OpenAI представила новое поколение языковой модели GPT-5, которая улучшает качество генерации текста и обработки сложных задач."


    Верни JSON:
    {
    "summary":"",
    "category":"",
    "importance":1-10,
    "importance_reason":"",
    "keywords":[]
    }
    """


    async def summarize(
        self,
        text: str
    ) -> str:

        return text[:200]