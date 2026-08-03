import logging

logger = logging.getLogger(__name__)


class AIClassifier:
    """
    Определяет соответствие поста теме пользователя.
    """


    async def classify(
        self,
        text: str,
        topic: str | None
    ) -> dict:

        if not topic:
            return {
                "relevant": True,
                "reason": "topic is empty"
            }


        return {
            "relevant": True,
            "reason": "placeholder"
        }