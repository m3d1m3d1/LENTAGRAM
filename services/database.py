import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "channels.db"


def init_db() -> None:
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feeds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            topic TEXT,
            ai_filter_enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            title TEXT,
            channel_id INTEGER UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feed_channels (
            feed_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            PRIMARY KEY (feed_id, channel_id),
            FOREIGN KEY (feed_id) REFERENCES feeds(id) ON DELETE CASCADE,
            FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feed_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            filter_prompt TEXT,
            post_text TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(feed_id, channel_id, message_id),
            FOREIGN KEY (feed_id) REFERENCES feeds(id) ON DELETE CASCADE,
            FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE
        )
    """)

    # НОВАЯ ТАБЛИЦА: настройки пользователя
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            active_feed_id INTEGER DEFAULT NULL,
            show_all_feeds INTEGER DEFAULT 1,
            FOREIGN KEY (active_feed_id) REFERENCES feeds(id) ON DELETE SET NULL
        )
    """)

    # Таблица feedback для обучения промпта
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS post_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            feed_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            feedback INTEGER NOT NULL,      -- 1 = лайк, -1 = дизлайк
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (feed_id) REFERENCES feeds(id) ON DELETE CASCADE,
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,

            UNIQUE(user_id, feed_id, post_id)
        )
    ''')
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS post_ai_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER UNIQUE,
            category TEXT,
            importance TEXT,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (post_id)
            REFERENCES posts(id)
            ON DELETE CASCADE
        )
    """)

    # Миграции
    for col, table in [("ai_filter_enabled", "feeds"), ("channel_id", "channels")]:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} INTEGER DEFAULT 1")
            conn.commit()
        except sqlite3.OperationalError:
            pass

    # Отдельная миграция: post_feedback раньше был на channel_id, теперь на post_id
    try:
        cursor.execute("ALTER TABLE post_feedback ADD COLUMN post_id INTEGER")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()