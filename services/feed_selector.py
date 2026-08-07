import logging
from typing import Optional

from services.database import get_connection
from services.ai.llm_client import chat_completion

logger = logging.getLogger(__name__)


class FeedSelector:
    """
    Сервис выбора целевой ленты для доставки поста пользователю.
    
    Основной принцип: один пользователь получает пост только один раз,
    даже если канал присутствует в нескольких его лентах.
    
    Если AI включен — выполняет один запрос к LLM для выбора ленты.
    Если AI выключен — выбирает primary ленту (куда канал был добавлен раньше всего).
    """

    async def choose_feed(
        self,
        post_text: str,
        candidate_feeds: list[dict],
        ai_enabled: bool,
    ) -> Optional[dict]:
        """
        Выбирает одну целевую ленту из списка кандидатных лент пользователя.
        
        Args:
            post_text: Текст поста для анализа
            candidate_feeds: Список лент пользователя, содержащих этот канал
                Каждая лента: {feed_id, user_id, name, topic, ai_filter_enabled, ...}
            ai_enabled: Флаг использования AI для выбора
        
        Returns:
            dict: Выбранная лента или None если список пуст
        """
        if not candidate_feeds:
            logger.warning("Список кандидатных лент пуст")
            return None
        
        if len(candidate_feeds) == 1:
            logger.info(f"Единственная лента feed_id={candidate_feeds[0]['feed_id']}")
            return candidate_feeds[0]
        
        if ai_enabled:
            selected = await self._choose_with_ai(post_text, candidate_feeds)
            if selected:
                return selected
            logger.warning("AI выбор не удался, используем fallback на primary feed")
        
        # Fallback: выбираем primary feed (самый ранний created_at)
        primary_feed = self._get_primary_feed(candidate_feeds)
        logger.info(f"Выбрана primary лента feed_id={primary_feed['feed_id']}")
        return primary_feed

    async def _choose_with_ai(
        self,
        post_text: str,
        candidate_feeds: list[dict],
    ) -> Optional[dict]:
        """
        Выполняет AI-анализ для выбора наиболее подходящей ленты.
        
        Передает модели:
        - текст поста
        - список лент с id, названием и темой
        
        Ожидает ответ:
        {
            "feed_id": int,
            "confidence": float,
            "reason": str
        }
        """
        feeds_info = []
        for feed in candidate_feeds:
            feeds_info.append({
                "id": feed["feed_id"],
                "name": feed.get("name", f"Лента {feed['feed_id']}"),
                "topic": feed.get("topic") or "без темы",
            })
        
        prompt = (
            "Выберите наиболее подходящую ленту для этого Telegram-поста. "
            "Верните JSON с полями: feed_id (int), confidence (float 0-1), reason (string). "
            "Учитывайте тему каждой ленты и содержание поста.\n\n"
            "Пост:\n"
            f"{post_text[:600]}\n\n"
            "Кандидатные ленты:\n"
        )
        
        for i, feed in enumerate(feeds_info, 1):
            prompt += f"{i}. ID={feed['id']}, Название=\"{feed['name']}\", Тема=\"{feed['topic']}\"\n"
        
        prompt += "\nПример ответа: {\"feed_id\": 5, \"confidence\": 0.92, \"reason\": \"Пост соответствует теме ленты\"}"
        
        try:
            response = await chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=100,
            )
            
            content = response.content.strip()
            content = content.replace("```json", "").replace("```", "").strip()
            logger.info(f"AI feed selector raw: {content[:300]}")
            
            import json
            parsed = json.loads(content)
            
            if not isinstance(parsed, dict):
                logger.warning(f"AI вернул не-словарь: {type(parsed)}")
                return None
            
            feed_id = parsed.get("feed_id")
            confidence = parsed.get("confidence", 0.0)
            
            # Валидация результата
            if feed_id is None:
                logger.warning("AI не вернул feed_id")
                return None
            
            # Проверяем, что feed_id существует в кандидатных лентах
            matching_feeds = [f for f in candidate_feeds if f["feed_id"] == feed_id]
            if not matching_feeds:
                logger.warning(f"AI вернул несуществующий feed_id={feed_id}")
                return None
            
            # Проверка confidence (порог 0.3)
            if confidence < 0.3:
                logger.info(f"AI confidence {confidence} ниже порога 0.3")
                return None
            
            logger.info(f"AI выбрал feed_id={feed_id} confidence={confidence}")
            return matching_feeds[0]
            
        except Exception as e:
            logger.error(f"Ошибка AI выбора ленты: {e}", exc_info=True)
            return None

    def _get_primary_feed(self, candidate_feeds: list[dict]) -> dict:
        """
        Возвращает primary ленту — ту, куда канал был добавлен раньше всего.
        
        Использует поле created_at таблицы feed_channels.
        """
        if not candidate_feeds:
            raise ValueError("Список лент пуст")
        
        if len(candidate_feeds) == 1:
            return candidate_feeds[0]
        
        # Собираем feed_id для запроса
        feed_ids = [f["feed_id"] for f in candidate_feeds]
        
        # Получаем информацию о времени добавления канала в каждую ленту
        # Нам нужно найти channel_id из первой ленты (он одинаковый для всех)
        sample_channel_id = candidate_feeds[0].get("_channel_id")
        
        with get_connection() as conn:
            # Запрос для получения created_at для каждой ленты
            placeholders = ",".join("?" * len(feed_ids))
            
            if sample_channel_id:
                # Если у нас есть channel_id, фильтруем по нему
                rows = conn.execute(f"""
                    SELECT feed_id, created_at
                    FROM feed_channels
                    WHERE feed_id IN ({placeholders}) AND channel_id = ?
                    ORDER BY created_at ASC
                    LIMIT 1
                """, (*feed_ids, sample_channel_id)).fetchone()
            else:
                # Если channel_id неизвестен, берем самую раннюю ленту вообще
                # Это менее точно, но лучше чем ничего
                rows = conn.execute(f"""
                    SELECT feed_id, created_at
                    FROM feed_channels
                    WHERE feed_id IN ({placeholders})
                    ORDER BY created_at ASC
                    LIMIT 1
                """, feed_ids).fetchone()
            
            if rows:
                primary_feed_id = rows["feed_id"]
                for feed in candidate_feeds:
                    if feed["feed_id"] == primary_feed_id:
                        logger.info(f"Primary feed determined by created_at: feed_id={primary_feed_id}")
                        return feed
            
            # Fallback: возвращаем первую ленту
            logger.warning("Не удалось определить primary feed по created_at, используем первую")
            return candidate_feeds[0]

    def set_channel_id_for_feeds(self, candidate_feeds: list[dict], channel_id: int) -> list[dict]:
        """Добавляет channel_id к каждому элементу candidate_feeds для последующего использования."""
        for feed in candidate_feeds:
            feed["_channel_id"] = channel_id
        return candidate_feeds
