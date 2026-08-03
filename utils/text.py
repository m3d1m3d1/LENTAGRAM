"""Утилиты для работы с текстом и ссылками Telegram."""

import re

_USERNAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{3,31}$")


def extract_username(text: str) -> str | None:
    """
    Извлекает @username канала из различных форматов ввода:
    - @username
    - t.me/username
    - https://t.me/username
    - https://t.me/username/123
    - username (без @)

    Возвращает username без @ или None, если формат не распознан.
    """
    text = text.strip()
    if not text:
        return None

    url_match = re.search(r"t\.me/([a-zA-Z][a-zA-Z0-9_]{3,31})", text)
    if url_match:
        return url_match.group(1).lower()

    if text.startswith("@"):
        text = text[1:]

    text = text.lower().strip()

    if _USERNAME_PATTERN.match(text):
        return text

    return None