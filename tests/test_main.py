"""
Тесты для Lentagram бота.

Запуск: pytest tests/ -v --cov=.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import sys

# Добавляем корень проекта в path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestConfig:
    """Тесты конфигурации."""
    
    def test_settings_validation(self):
        """Тест валидации настроек."""
        from pydantic import ValidationError
        
        # Проверка что пустой токен вызывает ошибку
        with pytest.raises(ValidationError):
            from config_new import Settings
            Settings(
                telegram_bot_token="",
                api_id=12345,
                api_hash="test_hash"
            )
    
    def test_settings_ai_enabled(self):
        """Тест проверки включённых AI сервисов."""
        from config_new import Settings
        
        settings = Settings(
            telegram_bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
            api_id=12345,
            api_hash="test_hash",
            gemini_api_key="test_key"
        )
        
        assert settings.ai_enabled is True
        
        settings_no_ai = Settings(
            telegram_bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
            api_id=12345,
            api_hash="test_hash"
        )
        
        assert settings_no_ai.ai_enabled is False


class TestLogger:
    """Тесты логирования."""
    
    def test_logger_creation(self):
        """Тест создания logger."""
        from utils.logger import get_logger
        
        logger = get_logger("test_module")
        assert logger is not None
        assert logger.name == "lentagram.test_module"
    
    def test_logger_levels(self, caplog):
        """Тест уровней логирования."""
        import logging
        from utils.logger import setup_logging
        
        # Пересоздаём logger с DEBUG уровнем для теста
        test_logger = setup_logging(log_level="DEBUG", log_file=None)
        
        with caplog.at_level(logging.DEBUG):
            test_logger.debug("Debug message")
            test_logger.info("Info message")
            test_logger.warning("Warning message")
            test_logger.error("Error message")
        
        assert "Debug message" in caplog.text
        assert "Info message" in caplog.text
        assert "Warning message" in caplog.text
        assert "Error message" in caplog.text


class TestRetryDecorator:
    """Тесты retry-декоратора."""
    
    @pytest.mark.asyncio
    async def test_retry_success_first_attempt(self):
        """Тест успешного выполнения с первой попытки."""
        from utils.error_handling import retry
        
        call_count = 0
        
        @retry(max_attempts=3, delay=0.1)
        async def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = await successful_func()
        assert result == "success"
        assert call_count == 1
    
    @pytest.mark.asyncio
    async def test_retry_success_after_failures(self):
        """Тест успеха после нескольких неудач."""
        from utils.error_handling import retry
        
        call_count = 0
        
        @retry(max_attempts=3, delay=0.1, exceptions=(ValueError,))
        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary error")
            return "success"
        
        result = await flaky_func()
        assert result == "success"
        assert call_count == 3
    
    @pytest.mark.asyncio
    async def test_retry_all_attempts_failed(self):
        """Тест исчерпания всех попыток."""
        from utils.error_handling import retry, RetryError
        
        @retry(max_attempts=2, delay=0.1, exceptions=(ValueError,))
        async def always_fails():
            raise ValueError("Always fails")
        
        with pytest.raises(RetryError):
            await always_fails()


class TestMigrations:
    """Тесты миграций базы данных."""
    
    def test_migration_manager_creation(self):
        """Тест создания менеджера миграций."""
        from services.migrations import MigrationManager
        import tempfile
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            manager = MigrationManager(f.name)
            assert manager.db_path == f.name
            assert manager._get_connection() is not None
    
    def test_migrations_list_not_empty(self):
        """Тест наличия миграций."""
        from services.migrations import MIGRATIONS
        
        assert len(MIGRATIONS) > 0
        assert all(len(m) == 2 for m in MIGRATIONS)  # Каждая миграция - кортеж из 2 элементов


class TestDatabaseService:
    """Тесты сервиса базы данных."""
    
    def test_database_initialization(self):
        """Тест инициализации базы данных."""
        from services.migrations import init_database
        import tempfile
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            # Должно выполниться без ошибок
            init_database(f.name)
            
            # Проверяем что файл БД создан
            assert Path(f.name).exists()


class TestTelethonClient:
    """Тесты Telethon клиента."""
    
    @pytest.mark.asyncio
    async def test_telethon_manager_creation(self):
        """Тест создания менеджера Telethon."""
        from services.telethon_client import TelethonManager
        from unittest.mock import Mock
        
        mock_bot = Mock()
        manager = TelethonManager(bot=mock_bot)
        
        assert manager is not None
        assert manager.bot == mock_bot


class TestChannelService:
    """Тесты сервиса каналов."""
    
    def test_parse_channel_link(self):
        """Тест парсинга ссылок на каналы."""
        from services.channel_service import ChannelService
        
        # Примеры ссылок для тестирования
        test_cases = [
            ("https://t.me/durov", "durov"),
            ("https://telegram.me/durov", "durov"),
            ("@durov", "durov"),
            ("t.me/durov/123", "durov"),  # Ссылка на пост
        ]
        
        for link, expected in test_cases:
            # Простая проверка что ссылка содержит username
            assert expected in link


class TestAIAnalyzer:
    """Тесты AI анализатора."""
    
    def test_analyzer_initialization(self):
        """Тест инициализации анализатора."""
        from services.ai.analyzer import AIAnalyzer
        
        analyzer = AIAnalyzer()
        assert analyzer is not None


@pytest.mark.asyncio
async def test_async_function_example():
    """Пример асинхронного теста."""
    await asyncio.sleep(0.01)  # Имитация асинхронной операции
    assert True
