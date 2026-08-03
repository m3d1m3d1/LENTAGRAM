# Lentagram AI 🤖

[English version below](#lentagram-ai-)

**Интеллектуальная платформа для мониторинга Telegram с использованием искусственного интеллекта**

Lentagram автоматически собирает информацию из Telegram-каналов, анализирует содержание сообщений с помощью LLM, классифицирует контент и формирует персонализированные информационные ленты.

---

## 🚀 Быстрый старт

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
Создайте файл `.env` в корне проекта:

```bash
cp .env.example .env
```

Или создайте вручную и добавьте следующие переменные:

```env
# Обязательные параметры
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

**Где получить credentials:**
- `TELEGRAM_BOT_TOKEN`: создайте бота через [@BotFather](https://t.me/BotFather)
- `API_ID` и `API_HASH`: получите на [my.telegram.org](https://my.telegram.org/apps)

### 4. Запуск бота
```bash
python main.py
```

При первом запуске бот запросит авторизацию в Telegram (номер телефона и код подтверждения).

---

## ✨ Основные возможности

### 🧠 AI Content Processing

- **LLM-классификация постов** — автоматическое определение тематики контента
- **Определение релевантности** — фильтрация постов по заданной теме
- **Автоматическое создание summary** — краткое изложение содержания поста
- **Тематическая категоризация** — распределение по категориям
- **Персональные рекомендации** — адаптация на основе feedback пользователя

### 📡 Telegram Intelligence

- **Мониторинг каналов через Telethon** — отслеживание новых постов в реальном времени
- **Создание пользовательских лент** — группировка каналов по темам
- **Обработка медиа-контента** — поддержка фото, видео, документов и альбомов
- **Управление источниками** — добавление/удаление каналов

### 🎯 Personalization

- **Пользовательские темы интересов** — настройка фильтров для каждой ленты
- **Feedback loop** — лайки/дизлайки для обучения модели
- **Адаптация рекомендаций** — учёт предпочтений пользователя

---

## 🏗️ Архитектура

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

---

## 🛠️ Tech Stack

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

---

## 📁 Структура проекта

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

---

## ⚙️ Конфигурация AI-фильтрации

AI-фильтрация включена по умолчанию для новых лент. Для управления:

1. Выберите ленту в меню «Мои ленты»
2. Нажмите «⚙️ AI-фильтр» для включения/отключения
3. При создании ленты можно указать тему для более точной фильтрации

---

## 🔧 Troubleshooting

### Ошибка «Файл .env не найден»
Создайте файл `.env` в корне проекта (см. раздел «Настройка»)

### Ошибка авторизации Telethon
Запустите `get_session_string.py` для получения session string

### Посты не приходят
- Проверьте, что канал добавлен в ленту
- Убедитесь, что AI-фильтр не отклоняет посты
- Проверьте логи на наличие ошибок

### Проблемы с медиа-альбомами
Если медиафайлы разбиваются на отдельные сообщения, убедитесь, что используется последняя версия кода с поддержкой grouped_id

---

## 📄 Лицензия

MIT License

---

<br>

# Lentagram AI 🤖

**AI-powered Telegram Intelligence Platform**

Lentagram automatically collects information from Telegram channels, analyzes message content using LLMs, classifies content, and creates personalized news feeds.

---

## 🚀 Quick Start

### 1. Clone the repository
```bash
git clone <repository-url>
cd lentagram
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure environment variables
Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Or create manually and add the following variables:

```env
# Required parameters
TELEGRAM_BOT_TOKEN=your_bot_token_here
API_ID=your_api_id_here
API_HASH=your_api_hash_here

# Optional: Telethon session (if available)
TELETHON_SESSION=

# Optional: AI classifier keys
OPENROUTER_API_KEY=
GEMINI_API_KEY=
GROQ_API_KEY=
```

**Where to get credentials:**
- `TELEGRAM_BOT_TOKEN`: create a bot via [@BotFather](https://t.me/BotFather)
- `API_ID` and `API_HASH`: get them at [my.telegram.org](https://my.telegram.org/apps)

### 4. Run the bot
```bash
python main.py
```

On first run, the bot will request Telegram authorization (phone number and confirmation code).

---

## ✨ Key Features

### 🧠 AI Content Processing

- **LLM Post Classification** — automatic content topic detection
- **Relevance Detection** — filter posts by specified topic
- **Auto Summary Generation** — brief content summarization
- **Topic Categorization** — distribution by categories
- **Personalized Recommendations** — adaptation based on user feedback

### 📡 Telegram Intelligence

- **Telethon Channel Monitoring** — real-time new post tracking
- **Custom Feed Creation** — channel grouping by topics
- **Media Content Processing** — support for photos, videos, documents, and albums
- **Source Management** — add/remove channels

### 🎯 Personalization

- **Custom Interest Topics** — configure filters for each feed
- **Feedback Loop** — likes/dislikes for model training
- **Recommendation Adaptation** — learning user preferences

---

## 🏗️ Architecture

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

---

## 🛠️ Tech Stack

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

---

## 📁 Project Structure

```
/workspace
├── main.py                 # Entry point, bot setup
├── config.py               # Environment variables
├── requirements.txt        # Dependencies
├── README.md              # Documentation
├── handlers/
│   ├── commands.py        # Command handlers (/start, /help)
│   ├── feeds.py           # Feed management
│   └── channels.py        # Channel management
├── services/
│   ├── database.py        # DB initialization, connections
│   ├── channel_service.py # Data access layer
│   ├── telethon_client.py # Telethon manager
│   └── ai/
│       ├── analyzer.py    # AI post analysis
│       └── classifier.py  # Classification
└── utils/
    └── text.py            # Text processing utilities
```

---

## ⚙️ AI Filter Configuration

AI filtering is enabled by default for new feeds. To manage:

1. Select a feed in the "My Feeds" menu
2. Click "⚙️ AI Filter" to enable/disable
3. When creating a feed, you can specify a topic for more accurate filtering

---

## 🔧 Troubleshooting

### Error "File .env not found"
Create a `.env` file in the project root (see "Configuration" section)

### Telethon Authorization Error
Run `get_session_string.py` to obtain session string

### Posts not arriving
- Check that the channel is added to the feed
- Ensure AI filter is not rejecting posts
- Check logs for errors

### Media Album Issues
If media files are split into separate messages, ensure you're using the latest code version with grouped_id support

---

## 📄 License

MIT License
