import os
from pathlib import Path
from dotenv import load_dotenv

# Проверяем наличие .env файла перед загрузкой
env_path = Path(__file__).parent / ".env"
if not env_path.exists():
    raise FileNotFoundError(
        "Файл .env не найден. Создайте файл .env в корне проекта и добавьте необходимые переменные окружения."
    )

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
TELETHON_SESSION = os.getenv("TELETHON_SESSION", "")
# Ключ для ИИ-классификатора. Необязателен: если не задан,
# классификатор просто пропускает все посты (фильтрация отключена),
# бот при этом продолжает работать.
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
AI_DAILY_REQUEST_LIMIT = int(os.getenv("AI_DAILY_REQUEST_LIMIT", "1000"))
AI_DAILY_TOKEN_LIMIT = int(os.getenv("AI_DAILY_TOKEN_LIMIT", "500000"))
AI_FAILURE_COOLDOWN_SECONDS = int(os.getenv("AI_FAILURE_COOLDOWN_SECONDS", "600"))

if not all([TELEGRAM_BOT_TOKEN, API_ID, API_HASH]):
    raise ValueError(
        "Не все обязательные переменные окружения установлены. "
        "Проверь .env файл (нужны TELEGRAM_BOT_TOKEN, API_ID, API_HASH)."
    )

API_ID = int(API_ID)
