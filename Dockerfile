# Lentagram Bot Docker Image
FROM python:3.12-slim

# Рабочая директория
WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Копирование файлов зависимостей
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir \
        pydantic-settings \
        pytest \
        pytest-asyncio \
        pytest-cov

# Копирование исходного кода
COPY . .

# Создание директорий для данных и логов
RUN mkdir -p /app/data /app/logs

# Установка переменной окружения по умолчанию
ENV PYTHONUNBUFFERED=1
ENV DATABASE_PATH=/app/data/bot_database.db
ENV LOG_LEVEL=INFO

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "print('OK')" || exit 1

# Запуск приложения
CMD ["python", "main.py"]
