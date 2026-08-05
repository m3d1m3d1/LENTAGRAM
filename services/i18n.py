import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "ru"
SUPPORTED_LANGUAGES = {
    "ru": {"label": "🇷🇺 Русский", "name": "русский"},
    "en": {"label": "🇬🇧 English", "name": "English"},
}
_LOCALES_DIR = Path(__file__).parent.parent / "locales"


@lru_cache(maxsize=1)
def _load_locales() -> dict[str, dict[str, str]]:
    locales: dict[str, dict[str, str]] = {}
    for path in _LOCALES_DIR.glob("*.json"):
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                locales[path.stem] = {str(k): str(v) for k, v in data.items()}
        except Exception as exc:
            logger.warning("Failed to load locale %s: %s", path, exc)
    return locales


def normalize_language(language_code: str | None) -> str:
    return language_code if language_code in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def get(language_code: str | None, key: str, **kwargs: Any) -> str:
    language = normalize_language(language_code)
    locales = _load_locales()
    text = locales.get(language, {}).get(key)
    if text is None:
        text = locales.get(DEFAULT_LANGUAGE, {}).get(key, key)
    try:
        return text.format(**kwargs)
    except Exception:
        logger.warning("Failed to format i18n key=%s language=%s", key, language)
        return text


def user_get(user_id: int, key: str, **kwargs: Any) -> str:
    from services.channel_service import ChannelService

    language = ChannelService().get_user_language(user_id)
    return get(language, key, **kwargs)
