import logging
import sqlite3
from typing import Optional
from services.database import get_connection
from services.i18n import DEFAULT_LANGUAGE, normalize_language

logger = logging.getLogger(__name__)


class ChannelService:
    """
    Единственный слой доступа к данным в проекте.
    Никакого in-memory хранилища рядом — всё идёт через SQLite,
    поэтому состояние переживает перезапуск бота.
    """

    # ---------- ленты ----------
    def save_ai_analysis(
        self,                           
        post_id: int,
        analysis: dict
):
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO post_ai_analysis
                (
                    post_id,
                    category,
                    importance
                )
                VALUES (?, ?, ?)
                """,
                (
                    post_id,
                    analysis.get("category"),
                    analysis.get("importance")
                )
            )

            conn.commit()
    def create_feed(self, user_id: int, name: str, topic: Optional[str] = None, ai_filter_enabled: bool = True) -> int:
        """Создаёт ленту, возвращает её id."""
        with get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO feeds (user_id, name, topic, ai_filter_enabled) VALUES (?, ?, ?, ?)",
                (user_id, name, topic, 1 if ai_filter_enabled else 0),
            )
            conn.commit()
            return cursor.lastrowid

    def get_user_feeds(self, user_id: int) -> list[dict]:
        """Возвращает ленты пользователя вместе со списком каналов в каждой."""
        with get_connection() as conn:
            feeds = conn.execute(
                "SELECT id, name, topic, ai_filter_enabled, temporarily_disabled_by_system FROM feeds WHERE user_id = ? ORDER BY id",
                (user_id,),
            ).fetchall()

            result = []
            for feed in feeds:
                channels = conn.execute(
                    """
                    SELECT c.username, c.title
                    FROM channels c
                    JOIN feed_channels fc ON fc.channel_id = c.id
                    WHERE fc.feed_id = ?
                    """,
                    (feed["id"],),
                ).fetchall()
                result.append({
                    "id": feed["id"],
                    "name": feed["name"],
                    "topic": feed["topic"],
                    "ai_filter_enabled": bool(feed["ai_filter_enabled"]),
                    "temporarily_disabled_by_system": bool(feed["temporarily_disabled_by_system"]),
                    "channels": [dict(c) for c in channels],
                })
            return result

    def get_feed(self, user_id: int, feed_id: int) -> Optional[dict]:
        """Возвращает конкретную ленту пользователя (или None, если не его / не существует)."""
        for feed in self.get_user_feeds(user_id):
            if feed["id"] == feed_id:
                return feed
        return None

    def delete_feed(self, user_id: int, feed_id: int) -> bool:
        """
        Удаляет ленту вместе со всеми зависимыми записями.
        Порядок важен: сначала самые "дочерние" таблицы, потом сама лента.
        Делаем это явно, а не полагаемся на ON DELETE CASCADE из схемы,
        т.к. на существующей БД constraint мог быть создан раньше
        (CREATE TABLE IF NOT EXISTS не меняет уже существующие таблицы).
        """
        with get_connection() as conn:
            # Убеждаемся, что лента принадлежит этому пользователю
            row = conn.execute(
                "SELECT id FROM feeds WHERE id = ? AND user_id = ?",
                (feed_id, user_id),
            ).fetchone()
            if not row:
                return False

            # feedback зависит от posts — удаляем первым
            conn.execute(
                "DELETE FROM post_feedback WHERE feed_id = ?",
                (feed_id,),
            )
            # AI-анализ зависит от posts
            conn.execute(
                """
                DELETE FROM post_ai_analysis
                WHERE post_id IN (SELECT id FROM posts WHERE feed_id = ?)
                """,
                (feed_id,),
            )
            conn.execute(
                "DELETE FROM posts WHERE feed_id = ?",
                (feed_id,),
            )
            conn.execute(
                "DELETE FROM feed_channels WHERE feed_id = ?",
                (feed_id,),
            )
            # Если лента была активной у кого-то — сбрасываем на "все ленты"
            conn.execute(
                """
                UPDATE user_settings
                SET active_feed_id = NULL, show_all_feeds = 1
                WHERE active_feed_id = ?
                """,
                (feed_id,),
            )

            cursor = conn.execute(
                "DELETE FROM feeds WHERE id = ? AND user_id = ?",
                (feed_id, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def toggle_ai_filter(self, user_id: int, feed_id: int) -> bool:
        """Переключает ai_filter_enabled для ленты. Возвращает новое значение."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT ai_filter_enabled FROM feeds WHERE id = ? AND user_id = ?",
                (feed_id, user_id),
            ).fetchone()
            if not row:
                return False

            new_value = 0 if row["ai_filter_enabled"] else 1
            conn.execute(
                "UPDATE feeds SET ai_filter_enabled = ?, temporarily_disabled_by_system = 0 WHERE id = ? AND user_id = ?",
                (new_value, feed_id, user_id),
            )
            conn.commit()
            return bool(new_value)


    def temporarily_disable_ai_filters(self) -> list[int]:
        """Disables currently enabled AI filters without losing user intent. Returns affected user ids."""
        with get_connection() as conn:
            rows = conn.execute("SELECT DISTINCT user_id FROM feeds WHERE ai_filter_enabled = 1").fetchall()
            conn.execute("""
                UPDATE feeds
                SET ai_filter_enabled = 0, temporarily_disabled_by_system = 1
                WHERE ai_filter_enabled = 1
            """)
            conn.commit()
            return [r["user_id"] for r in rows]

    def restore_system_disabled_ai_filters(self) -> int:
        """Restores only AI filters disabled by the system outage/quota flow."""
        with get_connection() as conn:
            cursor = conn.execute("""
                UPDATE feeds
                SET ai_filter_enabled = 1, temporarily_disabled_by_system = 0
                WHERE temporarily_disabled_by_system = 1
            """)
            conn.commit()
            return cursor.rowcount

    # ---------- настройки пользователя ----------
    def update_feed_filter(self, user_id: int, feed_id: int, new_topic: str) -> bool:
        """Обновляет тему/фильтр ленты. Возвращает True, если лента найдена и принадлежит пользователю."""
        with get_connection() as conn:
            cursor = conn.execute(
                "UPDATE feeds SET topic = ? WHERE id = ? AND user_id = ?",
                (new_topic, feed_id, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0
            
    def get_user_settings(self, user_id: int) -> dict:
        """Возвращает настройки пользователя (active_feed_id, show_all_feeds, language_code)."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT active_feed_id, show_all_feeds, language_code FROM user_settings WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                # Создаём дефолтные настройки
                conn.execute(
                    "INSERT INTO user_settings (user_id, active_feed_id, show_all_feeds, language_code) VALUES (?, NULL, 1, ?)",
                    (user_id, DEFAULT_LANGUAGE),
                )
                conn.commit()
                return {"active_feed_id": None, "show_all_feeds": True, "language_code": DEFAULT_LANGUAGE}
            return {
                "active_feed_id": row["active_feed_id"],
                "show_all_feeds": bool(row["show_all_feeds"]),
                "language_code": normalize_language(row["language_code"]),
            }

    def get_user_language(self, user_id: int) -> str:
        """Возвращает язык интерфейса пользователя, создавая настройки по умолчанию при необходимости."""
        return self.get_user_settings(user_id)["language_code"]

    def set_user_language(self, user_id: int, language_code: str) -> str:
        """Сохраняет язык интерфейса пользователя и возвращает нормализованное значение."""
        language = normalize_language(language_code)
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO user_settings (user_id, active_feed_id, show_all_feeds, language_code)
                   VALUES (?, NULL, 1, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                   language_code = excluded.language_code""",
                (user_id, language),
            )
            conn.commit()
        return language

    def set_active_feed(self, user_id: int, feed_id: int | None) -> None:
        """Устанавливает активную ленту (None = все ленты)."""
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO user_settings (user_id, active_feed_id, show_all_feeds, language_code)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                   active_feed_id = excluded.active_feed_id,
                   show_all_feeds = excluded.show_all_feeds""",
                (user_id, feed_id, 0 if feed_id else 1, DEFAULT_LANGUAGE),
            )
            conn.commit()

    def set_show_all_feeds(self, user_id: int) -> None:
        """Показывать посты из всех лент."""
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO user_settings (user_id, active_feed_id, show_all_feeds, language_code)
                   VALUES (?, NULL, 1, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                   active_feed_id = NULL,
                   show_all_feeds = 1""",
                (user_id, DEFAULT_LANGUAGE),
            )
            conn.commit()

    def get_active_feeds_for_user(self, user_id: int) -> list[dict]:
        """Возвращает ленты, из которых сейчас должны приходить посты."""
        settings = self.get_user_settings(user_id)

        if settings["show_all_feeds"] or settings["active_feed_id"] is None:
            return self.get_user_feeds(user_id)

        feed = self.get_feed(user_id, settings["active_feed_id"])
        return [feed] if feed else []

    # ---------- история постов (дополнение) ----------

    def get_last_posts(self, feed_id: int, limit: int = 5) -> list[dict]:
        """Возвращает последние N постов из ленты."""
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT p.message_id, p.post_text, p.sent_at,
                       c.username, c.title, c.channel_id
                FROM posts p
                JOIN channels c ON c.id = p.channel_id
                WHERE p.feed_id = ?
                ORDER BY p.sent_at DESC
                LIMIT ?
                """,
                (feed_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def save_post(self, feed_id: int, channel_id: int, message_id: int, post_text: str | None = None) -> int | None:
        """Сохраняет пост с текстом для истории. Возвращает id поста (нового или существующего)."""
        with get_connection() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO posts (feed_id, channel_id, message_id, post_text) VALUES (?, ?, ?, ?)",
                (feed_id, channel_id, message_id, post_text),
            )
            conn.commit()

            # Если вставили новый — сразу вернули id
            if cursor.lastrowid:
                return cursor.lastrowid

            # Если IGNORE (пост уже есть) — ищем существующий id
            row = conn.execute(
                "SELECT id FROM posts WHERE feed_id = ? AND channel_id = ? AND message_id = ?",
                (feed_id, channel_id, message_id),
            ).fetchone()
            return row["id"] if row else None

    # ---------- каналы ----------

    def add_channel_to_feed(self, feed_id: int, username: str, title: Optional[str] = None,
                            channel_id: Optional[int] = None) -> bool:
        """Добавляет канал (создаёт запись о канале, если её ещё нет) и привязывает к ленте."""
        username = username.lower().strip("@") if username else None
        with get_connection() as conn:
            # Создаём канал, если его ещё нет
            conn.execute(
                "INSERT OR IGNORE INTO channels (username, title, channel_id) VALUES (?, ?, ?)",
                (username, title, channel_id),
            )

            # Получаем ID канала (вне зависимости, создали ли мы его сейчас или он уже был)
            if channel_id:
                channel_row = conn.execute(
                    "SELECT id FROM channels WHERE channel_id = ? OR username = ?",
                    (channel_id, username)
                ).fetchone()
            else:
                channel_row = conn.execute(
                    "SELECT id FROM channels WHERE username = ?",
                    (username,)
                ).fetchone()

            if not channel_row:
                logger.error(f"Не удалось получить ID канала @{username}")
                return False

            # Обновляем title, если передан новый
            if title:
                conn.execute(
                    "UPDATE channels SET title = ? WHERE id = ?",
                    (title, channel_row["id"]),
                )

            # Привязываем канал к ленте
            try:
                conn.execute(
                    "INSERT INTO feed_channels (feed_id, channel_id) VALUES (?, ?)",
                    (feed_id, channel_row["id"]),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                # Уже привязан к этой ленте — не считаем это ошибкой
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Ошибка привязки канала @{username} к ленте {feed_id}: {e}")
                conn.rollback()
                return False

    def remove_channel_from_feed(self, feed_id: int, username: str) -> bool:
        username = username.lower().strip("@")
        with get_connection() as conn:
            channel_row = conn.execute(
                "SELECT id FROM channels WHERE username = ?", (username,)
            ).fetchone()
            if not channel_row:
                return False

            cursor = conn.execute(
                "DELETE FROM feed_channels WHERE feed_id = ? AND channel_id = ?",
                (feed_id, channel_row["id"]),
            )
            conn.commit()
            return cursor.rowcount > 0

    # ---------- вызовы со стороны Telethon-клиента ----------

    def get_monitored_usernames(self) -> list[str]:
        """Список всех каналов, за которыми вообще нужно следить (по всем пользователям)."""
        with get_connection() as conn:
            rows = conn.execute("SELECT DISTINCT username FROM channels WHERE username IS NOT NULL").fetchall()
            return [r["username"] for r in rows]

    def get_feeds_for_channel(self, username: str) -> list[dict]:
        """Все ленты (с их владельцем и темой), в которые входит этот канал."""
        username = username.lower().strip("@")
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT f.id AS feed_id, f.user_id, f.name, f.topic, f.ai_filter_enabled, f.temporarily_disabled_by_system
                FROM feeds f
                JOIN feed_channels fc ON fc.feed_id = f.id
                JOIN channels c ON c.id = fc.channel_id
                WHERE c.username = ?
                """,
                (username,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_feeds_by_channel_id(self, channel_id: int) -> list[dict]:
        """Все ленты (с их владельцем и темой), в которые входит канал по его числовому ID."""
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT f.id AS feed_id, f.user_id, f.name, f.topic, f.ai_filter_enabled, f.temporarily_disabled_by_system
                FROM feeds f
                JOIN feed_channels fc ON fc.feed_id = f.id
                JOIN channels c ON c.id = fc.channel_id
                WHERE c.channel_id = ?
                """,
                (channel_id,),
            ).fetchall()
            return [dict(r) for r in rows]
    # ---------- история постов ----------

    def is_post_sent(self, feed_id: int, channel_id: int, message_id: int) -> bool:
        """Проверяет, был ли уже отправлен этот пост в эту ленту."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM posts WHERE feed_id = ? AND channel_id = ? AND message_id = ?",
                (feed_id, channel_id, message_id),
            ).fetchone()
            return row is not None

    def mark_post_sent(self, feed_id: int, channel_id: int, message_id: int) -> None:
        """Отмечает пост как отправленный."""
        with get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO posts (feed_id, channel_id, message_id) VALUES (?, ?, ?)",
                (feed_id, channel_id, message_id),
            )
            conn.commit()
    def get_channel_db_id(self, telegram_channel_id: int) -> Optional[int]:
        """Возвращает внутренний ID канала по его Telegram ID."""
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM channels WHERE channel_id = ?",
                (telegram_channel_id,),
            ).fetchone()
            return row["id"] if row else None