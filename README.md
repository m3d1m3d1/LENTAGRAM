Lentagram AI 🤖
AI-powered Telegram Intelligence Platform

Интеллектуальная система персонального мониторинга Telegram-источников с использованием LLM-моделей.

Lentagram автоматически собирает информацию из Telegram-каналов, анализирует содержание сообщений, классифицирует контент и формирует персонализированные информационные ленты.

Основные возможности:

AI Content Processing:

LLM-классификация Telegram-постов;
определение релевантности контента;
автоматическое создание кратких summary;
тематическая категоризация сообщений;
персональные рекомендации.

Telegram Intelligence:

мониторинг Telegram-каналов через Telethon;
создание пользовательских лент;
обработка медиа-контента;
управление источниками.

Personalization:
пользовательские темы интересов;
feedback loop;
адаптация рекомендаций на основе реакций.

Architecture:
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

Tech Stack:

Backend:

Python 3.11
AsyncIO
FastAPI (planned/current migration)

Telegram:

Telethon
python-telegram-bot

AI:

OpenRouter API
Llama models
Prompt Engineering
RAG architecture (planned)
Vector Search (planned)

Storage

Current:

SQLite

Migration:

PostgreSQL
Redis
Qdrant

DevOps:

Linux VPS
Docker
Git
Systemd