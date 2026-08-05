"""
Конфигурация приложения через Pydantic Settings.

Обеспечивает типизированный доступ к переменным окружения
с валидацией и значениями по умолчанию.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import Optional
from pathlib import Path


class Settings(BaseSettings):
    """Настройки приложения с валидацией."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # Обязательные Telegram настройки
    telegram_bot_token: str = Field(..., description="Токен Telegram бота")
    api_id: int = Field(..., description="API ID Telegram")
    api_hash: str = Field(..., description="API Hash Telegram")
    
    # Сессия Telethon (опционально)
    telethon_session: str = Field(default="", description="Путь к сессии Telethon")
    
    # API ключи для AI сервисов (опционально)
    openrouter_api_key: Optional[str] = Field(default=None, description="API ключ OpenRouter")
    gemini_api_key: Optional[str] = Field(default=None, description="API ключ Google Gemini")
    groq_api_key: Optional[str] = Field(default=None, description="API ключ Groq")
    anthropic_api_key: Optional[str] = Field(default=None, description="API ключ Anthropic")
    
    # AI квоты и отказоустойчивость
    ai_daily_request_limit: int = Field(default=1000, description="Дневной лимит AI-запросов")
    ai_daily_token_limit: int = Field(default=500000, description="Дневной лимит AI-токенов")
    ai_failure_cooldown_seconds: int = Field(default=600, description="Cooldown после отказа AI в секундах")

    # Настройки логирования
    log_level: str = Field(default="INFO", description="Уровень логирования")
    
    # Настройки базы данных
    database_path: str = Field(default="bot_database.db", description="Путь к базе данных")
    
    # Настройки производительности
    request_timeout: int = Field(default=30, description="Таймаут запросов в секундах")
    max_retries: int = Field(default=3, description="Максимальное количество попыток")
    retry_delay: float = Field(default=1.0, description="Задержка между попытками в секундах")
    
    @field_validator('api_id')
    @classmethod
    def validate_api_id(cls, v: int) -> int:
        if v <= 0:
            raise ValueError('API_ID должен быть положительным числом')
        return v
    
    @field_validator('telegram_bot_token')
    @classmethod
    def validate_bot_token(cls, v: str) -> str:
        if not v or len(v) < 10:
            raise ValueError('Некорректный токен бота')
        return v
    
    @property
    def ai_enabled(self) -> bool:
        """Проверяет, включён ли хотя бы один AI сервис."""
        return any([
            self.openrouter_api_key,
            self.gemini_api_key,
            self.groq_api_key,
            self.anthropic_api_key
        ])


# Глобальный экземпляр настроек
settings = Settings()
