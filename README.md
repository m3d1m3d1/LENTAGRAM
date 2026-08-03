Lentagram AI 🤖
AI-powered Telegram Intelligence Platform

Интеллектуальная система персонального мониторинга Telegram-источников с использованием LLM-моделей.

Lentagram автоматически собирает информацию из Telegram-каналов, анализирует содержание сообщений, классифицирует контент и формирует персонализированные информационные ленты.

## Быстрый старт

### 1. Клонирование репозитория
```bash
git clone <repository-url>
cd lentagram
```

### 2. Установка зависимостей
```bash
pip install -r requirements.txt
```

### 3. Настройка переменных окружения
Создайте файл `.env` в корне проекта и добавьте следующие переменные:

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
API_ID=your_api_id_here
API_HASH=your_api_hash_here

# Опционально: сессия Telethon (если есть)
TELETHON_SESSION=

# Опционально: ключи для AI-классификаторов
OPENROUTER_API_KEY=
GEMINI_API_KEY=
GROQ_API_KEY=
```

**Получение credentials:**
- `TELEGRAM_BOT_TOKEN`: создайте бота через [@BotFather](https://t.me/BotFather)
- `API_ID` и `API_HASH`: получите на [my.telegram.org](https://my.telegram.org/apps)

### 4. Запуск бота
```bash
python main.py
```

## Основные возможности

### AI Content Processing

- **LLM-классификация Telegram-постов** — автоматическое определение тематики контента
- **Определение релевантности** — фильтрация постов по заданной теме
- **Автоматическое создание summary** — краткое изложение содержания поста
- **Тематическая категоризация** — распределение по категориям
- **Персональные рекомендации** — адаптация на основе feedback пользователя

### Telegram Intelligence

- **Мониторинг каналов через Telethon** — отслеживание новых постов в реальном времени
- **Создание пользовательских лент** — группировка каналов по темам
- **Обработка медиа-контента** — поддержка фото, видео, документов
- **Управление источниками** — добавление/удаление каналов

### Personalization

- **Пользовательские темы интересов** — настройка фильтров для каждой ленты
- **Feedback loop** — лайки/дизлайки для обучения модели
- **Адаптация рекомендаций** — учёт предпочтений пользователя

## Архитектура

```
                 Telegram API
                     |
                     |
              Telethon Listener
                     |
                     |
              Message Pipeline
                     |
        --------------------------
        |                        |
     AI Engine               Database
        |
 -----------------
 |       |       |
LLM   Summary  Embeddings


                     |
                     |
               Telegram Bot
                     |
                   User
```

## Tech Stack

### Backend

- Python 3.11+
- AsyncIO
- python-telegram-bot v21.6
- Telethon v1.36.0

### AI

- OpenRouter API (Llama models)
- Google Generative AI (Gemini)
- Groq API
- Prompt Engineering
- RAG architecture (planned)
- Vector Search (planned)

### Storage

**Current:**
- SQLite

**Planned migration:**
- PostgreSQL
- Redis (cache)
- Qdrant (vector search)

### DevOps

- Linux VPS
- Docker (planned)
- Git
- Systemd

## Структура проекта

```
/workspace
├── main.py                 # Точка входа, настройка бота
├── config.py               # Переменные окружения
├── requirements.txt        # Зависимости
├── README.md              # Документация
├── handlers/
│   ├── commands.py        # Обработчики команд (/start, /help)
│   ├── feeds.py           # Управление лентами
│   └── channels.py        # Управление каналами
├── services/
│   ├── database.py        # Инициализация БД, подключения
│   ├── channel_service.py # Слой доступа к данным
│   ├── telethon_client.py # Telethon менеджер
│   └── ai/
│       ├── analyzer.py    # AI-анализ постов
│       └── classifier.py  # Классификация
└── utils/
    └── text.py            # Утилиты для работы с текстом
```

## Конфигурация AI-фильтрации

AI-фильтрация включена по умолчанию для новых лент. Для управления:

1. Выберите ленту в меню «Мои ленты»
2. Нажмите «⚙️ AI-фильтр» для включения/отключения
3. При создании ленты можно указать тему для более точной фильтрации

## Troubleshooting

### Ошибка «Файл .env не найден»
Создайте файл `.env` в корне проекта (см. раздел «Настройка»)

### Ошибка авторизации Telethon
Запустите `get_session_string.py` для получения session string

### Посты не приходят
- Проверьте, что канал добавлен в ленту
- Убедитесь, что AI-фильтр не отклоняет посты
- Проверьте логи на наличие ошибок

## Лицензия

MIT License