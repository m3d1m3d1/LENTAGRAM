"""
Модуль логирования для приложения.

Настраивает централизованное логирование с поддержкой:
- Консольного вывода с цветами
- Записи в файл
- Разных уровней логирования
- Форматирования с информацией о времени и модуле
"""
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional


class ColorFormatter(logging.Formatter):
    """Форматтер с цветным выводом для консоли."""
    
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
    }
    RESET = '\033[0m'
    
    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = "logs/bot.log",
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 3
) -> logging.Logger:
    """
    Настраивает систему логирования для приложения.
    
    Args:
        log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Путь к файлу логов (None для отключения файлового логирования)
        max_bytes: Максимальный размер файла логов перед ротацией
        backup_count: Количество файлов резервных копий
    
    Returns:
        Настроенный logger для основного приложения
    """
    # Создаем директорию для логов если нужно
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Получаем уровень логирования
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Создаем главный logger приложения
    logger = logging.getLogger("lentagram")
    logger.setLevel(numeric_level)
    
    # Очищаем существующие handlers
    logger.handlers.clear()
    
    # Консольный handler с цветным форматированием
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_formatter = ColorFormatter(
        '%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # Файловый handler с ротацией
    if log_file:
        try:
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8'
            )
            file_handler.setLevel(numeric_level)
            file_formatter = logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(funcName)s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            logger.warning(f"Не удалось создать файл логов {log_file}: {e}")
    
    # Логгер для telegram.ext
    telegram_logger = logging.getLogger("telegram.ext")
    telegram_logger.setLevel(logging.WARNING)
    
    # Логгер для httpx (клиент Telegram)
    httpx_logger = logging.getLogger("httpx")
    httpx_logger.setLevel(logging.WARNING)
    
    logger.info(f"Логирование настроено (уровень: {log_level})")
    
    return logger


# Глобальный logger
logger = setup_logging()


def get_logger(name: str) -> logging.Logger:
    """
    Получает logger для конкретного модуля.
    
    Args:
        name: Имя модуля (обычно __name__)
    
    Returns:
        Logger с именем родительского приложения
    """
    return logging.getLogger(f"lentagram.{name}")
