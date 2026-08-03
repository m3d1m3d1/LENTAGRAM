"""
Миграции базы данных для Lentagram бота.

Управляет версионированием схемы БД и автоматическим применением миграций.
"""
import sqlite3
from pathlib import Path
from typing import List, Tuple
from utils.logger import get_logger

logger = get_logger(__name__)


class MigrationManager:
    """Менеджер миграций базы данных."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.migrations_table = "_migrations"
    
    def _get_connection(self) -> sqlite3.Connection:
        """Создаёт подключение к БД."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _ensure_migrations_table(self, conn: sqlite3.Connection) -> None:
        """Создаёт таблицу для отслеживания применённых миграций."""
        cursor = conn.cursor()
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.migrations_table} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                migration_name TEXT UNIQUE NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    
    def _get_applied_migrations(self, conn: sqlite3.Connection) -> List[str]:
        """Возвращает список уже применённых миграций."""
        cursor = conn.cursor()
        cursor.execute(f"SELECT migration_name FROM {self.migrations_table} ORDER BY id")
        return [row['migration_name'] for row in cursor.fetchall()]
    
    def _apply_migration(
        self, 
        conn: sqlite3.Connection, 
        migration_name: str,
        migration_sql: str
    ) -> None:
        """Применяет одну миграцию."""
        cursor = conn.cursor()
        
        # Выполняем SQL миграции
        cursor.executescript(migration_sql)
        
        # Записываем факт применения миграции
        cursor.execute(
            f"INSERT INTO {self.migrations_table} (migration_name) VALUES (?)",
            (migration_name,)
        )
        
        conn.commit()
        logger.info(f"Применена миграция: {migration_name}")
    
    def run_migrations(self, migrations: List[Tuple[str, str]]) -> None:
        """
        Применяет все неприменённые миграции.
        
        Args:
            migrations: Список кортежей (имя_миграции, SQL_код)
        """
        conn = self._get_connection()
        try:
            self._ensure_migrations_table(conn)
            applied = self._get_applied_migrations(conn)
            
            for migration_name, migration_sql in migrations:
                if migration_name not in applied:
                    self._apply_migration(conn, migration_name, migration_sql)
                else:
                    logger.debug(f"Миграция {migration_name} уже применена")
            
            logger.info("Все миграции применены успешно")
        finally:
            conn.close()


# Список миграций в порядке применения
MIGRATIONS = [
    (
        "001_initial_schema",
        """
        -- Таблица пользователей (администраторов бота)
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Таблица лент новостей
        CREATE TABLE IF NOT EXISTS feeds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            filter_prompt TEXT,
            ai_enabled BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        
        -- Таблица каналов
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feed_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            channel_username TEXT,
            channel_title TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (feed_id) REFERENCES feeds(id) ON DELETE CASCADE,
            UNIQUE(feed_id, channel_id)
        );
        
        -- Таблица постов
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            forwarded_message_id INTEGER,
            content TEXT,
            media_type TEXT,
            media_urls TEXT,
            ai_analysis TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE,
            UNIQUE(channel_id, message_id)
        );
        
        -- Таблица аналитики (лайки/дизлайки)
        CREATE TABLE IF NOT EXISTS analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            feedback_type TEXT CHECK(feedback_type IN ('like', 'dislike')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(post_id, user_id)
        );
        
        -- Индексы для производительности
        CREATE INDEX IF NOT EXISTS idx_feeds_user_id ON feeds(user_id);
        CREATE INDEX IF NOT EXISTS idx_channels_feed_id ON channels(feed_id);
        CREATE INDEX IF NOT EXISTS idx_posts_channel_id ON posts(channel_id);
        CREATE INDEX IF NOT EXISTS idx_analytics_post_id ON analytics(post_id);
        """
    ),
    (
        "002_add_ai_cache",
        """
        -- Таблица кэширования AI анализа
        CREATE TABLE IF NOT EXISTS ai_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_hash TEXT UNIQUE NOT NULL,
            analysis_result TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_ai_cache_hash ON ai_cache(content_hash);
        CREATE INDEX IF NOT EXISTS idx_ai_cache_expires ON ai_cache(expires_at);
        """
    ),
    (
        "003_add_error_logs",
        """
        -- Таблица логов ошибок
        CREATE TABLE IF NOT EXISTS error_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            error_type TEXT NOT NULL,
            error_message TEXT NOT NULL,
            stack_trace TEXT,
            context TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_error_logs_created ON error_logs(created_at);
        """
    ),
]


def init_database(db_path: str = "bot_database.db") -> None:
    """
    Инициализирует базу данных и применяет все миграции.
    
    Args:
        db_path: Путь к файлу базы данных
    """
    logger.info(f"Инициализация базы данных: {db_path}")
    
    manager = MigrationManager(db_path)
    manager.run_migrations(MIGRATIONS)
    
    logger.info("База данных успешно инициализирована")
