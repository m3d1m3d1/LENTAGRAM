import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_i18n_fallbacks():
    from services.i18n import get

    assert get("en", "button_create_feed") == "➕ Create feed"
    assert get("en", "missing_key") == "missing_key"
    assert get("de", "button_create_feed") == "➕ Создать ленту"


def test_user_language_persistence(tmp_path, monkeypatch):
    import services.database as database
    from services.database import init_db
    from services.channel_service import ChannelService

    monkeypatch.setattr(database, "DB_PATH", tmp_path / "channels.db")
    init_db()

    service = ChannelService()
    assert service.get_user_language(123) == "ru"
    service.set_user_language(123, "en")
    assert service.get_user_language(123) == "en"

    # Updating other settings must not reset the language preference.
    service.set_show_all_feeds(123)
    assert service.get_user_language(123) == "en"
