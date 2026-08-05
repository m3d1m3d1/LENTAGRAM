# Lentagram Bot - Telegram News Aggregator

[![CI/CD](https://github.com/m3d1m3d1/LENTAGRAM/actions/workflows/ci.yml/badge.svg)](https://github.com/m3d1m3d1/LENTAGRAM/actions)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

🤖 **Lentagram** — умный агрегатор новостей в Telegram с AI-фильтрацией и персонализированными лентами.

---

## 📋 Содержание

- [Возможности](#-возможности)
- [Быстрый старт](#-быстрый-старт)
- [Архитектура проекта](#-архитектура-проекта)
- [Tech Stack](#-tech-stack)
- [Конфигурация](#-конфигурация)
- [Запуск в Docker](#-запуск-в-docker)
- [Разработка и тестирование](#-разработка-и-тестирование)
- [Troubleshooting](#-troubleshooting)

---

## ✨ Возможности

### Для пользователей
- 📰 **Персонализированные ленты** — создавайте собственные новостные потоки
- 🔗 **Мультиканальность** — подключайте несколько каналов к одной ленте
- 🧠 **AI-фильтрация** — автоматический анализ контента через LLM (Gemini, Groq, OpenRouter)
- 📊 **Аналитика** — отслеживайте лайки/дизлайки для улучшения рекомендаций
- 🎯 **Умная группировка** — альбомы медиа отправляются единым сообщением

### Для разработчиков
- 🐳 **Docker-контейнеризация** — готовый образ для развёртывания
- ✅ **CI/CD pipeline** — автоматические тесты и сборка
- 🧪 **Покрытие тестами** — unit и integration тесты
- 📝 **Миграции БД** — версионирование схемы базы данных
- 🪵 **Профессиональное логирование** — цветной вывод + ротация файлов
- 🔄 **Retry-логика** — обработка временных ошибок сети
- 🔒 **Валидация настроек** — Pydantic Settings для type-safe конфигурации

---

## 🚀 Быстрый старт

### Предварительные требования

- Python 3.12+
- Telegram Bot Token ([получить у @BotFather](https://t.me/BotFather))
- Telegram API ID и Hash ([получить на my.telegram.org](https://my.telegram.org))

### 1. Клонирование репозитория

```bash
git clone https://github.com/m3d1m3d1/LENTAGRAM.git
cd lentagram-bot
```

### 2. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 3. Настройка окружения

Скопируйте пример файла окружения:

```bash
cp .env.example .env
```

Отредактируйте `.env` и добавьте ваши ключи:

```env
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
API_ID=12345678
API_HASH=abcdef1234567890abcdef1234567890

# Опционально: AI сервисы для фильтрации
GEMINI_API_KEY=your_gemini_key
GROQ_API_KEY=your_groq_key
OPENROUTER_API_KEY=your_openrouter_key

# Опционально: настройки
LOG_LEVEL=INFO
DATABASE_PATH=bot_database.db
```

### 4. Запуск бота

```bash
python main.py
```

---

## 🏗️ Архитектура проекта

```
lentagram-bot/
├── main.py                 # Точка входа, настройка application
├── config.py               # Конфигурация (Pydantic Settings)
├── config_new.py           # Новая типизированная конфигурация
├── requirements.txt        # Зависимости Python
├── Dockerfile              # Docker образ
├── .env.example            # Шаблон переменных окружения
├── .github/workflows/
│   └── ci.yml              # CI/CD pipeline
│
├── handlers/               # Обработчики событий Telegram
│   ├── commands.py         # Команды бота (/start, /help)
│   ├── feeds.py            # Управление лентами
│   └── channels.py         # Управление каналами
│
├── services/               # Бизнес-логика
│   ├── database.py         # Работа с БД
│   ├── migrations.py       # Миграции БД
│   ├── channel_service.py  # Сервис каналов
│   ├── telethon_client.py  # Telethon клиент
│   └── ai/                 # AI модули
│       ├── analyzer.py     # Анализ контента
│       ├── classifier.py   # Классификация постов
│       └── llm_client.py   # Клиент для LLM API
│
├── utils/                  # Утилиты
│   ├── logger.py           # Настройка логирования
│   ├── error_handling.py   # Retry-логика и Circuit Breaker
│   └── text.py             # Текстовые утилиты
│
├── tests/                  # Тесты
│   ├── test_main.py        # Основные тесты
│   └── conftest.py         # pytest конфигурация
│
└── logs/                   # Логи (создаётся автоматически)
    └── bot.log
```

---

## 🛠️ Tech Stack

| Категория | Технологии |
|-----------|------------|
| **Язык** | Python 3.12+ |
| **Telegram Bot** | python-telegram-bot v21.6 |
| **Telegram Client** | Telethon v1.36.0 |
| **База данных** | SQLite3 + миграции |
| **AI/LLM** | Google Gemini, Groq, OpenRouter, Anthropic |
| **Конфигурация** | Pydantic Settings, python-dotenv |
| **Логирование** | logging с ротацией файлов |
| **Тестирование** | pytest, pytest-asyncio, pytest-cov |
| **CI/CD** | GitHub Actions |
| **Контейнеризация** | Docker, Docker Compose |
| **Linting** | flake8 |

---

## ⚙️ Конфигурация

### Обязательные переменные

| Переменная | Описание | Пример |
|------------|----------|--------|
| `TELEGRAM_BOT_TOKEN` | Токен бота от @BotFather | `123456:ABC-...` |
| `API_ID` | API ID из my.telegram.org | `12345678` |
| `API_HASH` | API Hash из my.telegram.org | `abc123...` |

### Опциональные переменные

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `TELETHON_SESSION` | Сессия Telethon | `""` |
| `GEMINI_API_KEY` | Ключ Google Gemini API | `None` |
| `GROQ_API_KEY` | Ключ Groq API | `None` |
| `AI_DAILY_REQUEST_LIMIT` | Дневной лимит AI-запросов | `1000` |
| `AI_DAILY_TOKEN_LIMIT` | Дневной лимит AI-токенов | `500000` |
| `AI_FAILURE_COOLDOWN_SECONDS` | Cooldown после полного отказа AI | `600` |
| `OPENROUTER_API_KEY` | Ключ OpenRouter API | `None` |
| `ANTHROPIC_API_KEY` | Ключ Anthropic API | `None` |
| `LOG_LEVEL` | Уровень логирования | `INFO` |
| `DATABASE_PATH` | Путь к базе данных | `bot_database.db` |
| `REQUEST_TIMEOUT` | Таймаут запросов (сек) | `30` |
| `MAX_RETRIES` | Макс. количество попыток | `3` |

### AI-фильтрация

Бот поддерживает несколько AI-провайдеров. Если ключ не задан — фильтрация отключена, бот работает в обычном режиме.

Для включения AI-фильтрации добавьте хотя бы один ключ:

```env
GEMINI_API_KEY=your_key_here
```

---

## 🐳 Запуск в Docker

### Сборка образа

```bash
docker build -t lentagram-bot .
```

### Запуск контейнера

```bash
docker run -d \
  --name lentagram \
  --restart unless-stopped \
  -v $(pwd)/.env:/app/.env \
  -v $(pwd)/data:/app/data \
  lentagram-bot
```

### Docker Compose (рекомендуется)

Создайте `docker-compose.yml`:

```yaml
version: '3.8'

services:
  bot:
    build: .
    container_name: lentagram-bot
    restart: unless-stopped
    env_file:
      - .env
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    healthcheck:
      test: ["CMD", "python", "-c", "print('OK')"]
      interval: 30s
      timeout: 10s
      retries: 3
```

Запуск:

```bash
docker-compose up -d
```

Просмотр логов:

```bash
docker-compose logs -f bot
```

---

## 🧪 Разработка и тестирование

### Запуск тестов

```bash
# Все тесты
pytest tests/ -v

# С покрытием кода
pytest tests/ -v --cov=. --cov-report=html

# Один конкретный тест
pytest tests/test_main.py::TestConfig::test_settings_validation -v
```

### Линтинг кода

```bash
flake8 . --max-line-length=127 --statistics
```

### Проверка типов (опционально)

Установите mypy:

```bash
pip install mypy
mypy . --ignore-missing-imports
```

### Добавление новых миграций

1. Откройте `services/migrations.py`
2. Добавьте новую миграцию в список `MIGRATIONS`:

```python
MIGRATIONS = [
    # ... существующие миграции
    (
        "004_add_new_feature",
        """
        CREATE TABLE IF NOT EXISTS new_table (...);
        """
    ),
]
```

3. Миграция применится автоматически при следующем запуске

---

## 🔧 Troubleshooting

### Ошибка: "Файл .env не найден"

**Решение:** Создайте файл `.env` в корне проекта или скопируйте шаблон:

```bash
cp .env.example .env
```

### Ошибка: "Не все обязательные переменные окружения установлены"

**Решение:** Проверьте наличие в `.env`:
- `TELEGRAM_BOT_TOKEN`
- `API_ID`
- `API_HASH`

### Бот не запускается в Docker

**Решение:**
1. Проверьте пути к томам в docker-compose.yml
2. Убедитесь что `.env` файл доступен внутри контейнера
3. Проверьте логи: `docker-compose logs bot`

### AI-фильтрация не работает

**Решение:**
1. Проверьте что добавлен хотя бы один API ключ (GEMINI, GROQ, OPENROUTER)
2. Проверьте лимиты API вашего провайдера
3. Включите debug-логирование: `LOG_LEVEL=DEBUG`

### Ошибки подключения к Telegram

**Решение:**
1. Проверьте правильность API_ID и API_HASH
2. Убедитесь что сессия Telethon действительна
3. При использовании прокси настройте переменные окружения

---

## 🤝 Contributing

Мы приветствуем вклад в проект! 

### Как внести изменения

1. Fork репозиторий
2. Создайте feature branch (`git checkout -b feature/amazing-feature`)
3. Commit изменения (`git commit -m 'Add amazing feature'`)
4. Push в branch (`git push origin feature/amazing-feature`)
5. Откройте Pull Request

### Требования к коду

- Следуйте PEP 8
- Добавляйте тесты для нового функционала
- Обновляйте документацию при изменении API
- Используйте type hints

---

## 📄 Лицензия

Этот проект распространяется под лицензией MIT. См. файл [LICENSE](LICENSE) для деталей.

---

## 📞 Контакты

- **Автор**: Alexander Boiko
- **Email**: lilmedibleedem@proton.me
- **Telegram**: [@Koolmedivh]

---

<div align="center">

**Made with ❤️ by Alexander Boiko**

[⬆️ Вернуться к началу](#lentagram-bot---telegram-news-aggregator)

</div>:
