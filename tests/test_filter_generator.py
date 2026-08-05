import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _stub_llm_client(monkeypatch):
    llm_client = types.ModuleType("services.ai.llm_client")

    async def chat_completion(*args, **kwargs):
        raise RuntimeError("429 rate limit")

    llm_client.chat_completion = chat_completion
    monkeypatch.setitem(sys.modules, "services.ai.llm_client", llm_client)


def test_fallback_result_preserves_error_metadata(monkeypatch):
    _stub_llm_client(monkeypatch)
    from services.ai.filter_generator import FilterGenerator

    result = FilterGenerator().fallback_result(
        "Новости AI",
        "quota_exceeded",
        error_message="429 rate limit",
    )

    assert result["generated_by"] == "fallback"
    assert result["error_type"] == "quota_exceeded"
    assert result["error_message"] == "429 rate limit"
    assert result["topic"] == "Новости AI"
    assert len(result["filters"]) == 3
    assert all("Новости AI" in item["ai_prompt"] for item in result["filters"])


def test_filters_ready_text_warns_for_fallback(monkeypatch):
    _stub_llm_client(monkeypatch)
    import handlers.feeds as feeds

    monkeypatch.setattr(feeds, "_lang", lambda user_id: "ru")

    fallback_text = feeds._filters_ready_text(123, "Новости AI", "fallback")
    ai_text = feeds._filters_ready_text(123, "Новости AI", "ai")

    assert "⚠️ AI-анализ временно недоступен" in fallback_text
    assert "стандартные фильтры" in fallback_text
    assert "🤖 Я подготовил варианты ИИ-фильтра" not in fallback_text
    assert "🤖 Я подготовил варианты ИИ-фильтра" in ai_text


async def test_generate_filters_fallback_keeps_error_metadata(monkeypatch):
    _stub_llm_client(monkeypatch)
    sys.modules.pop("services.ai.filter_generator", None)
    from services.ai.filter_generator import FilterGenerator

    result = await FilterGenerator().generate_filters("Новости AI")

    assert result["generated_by"] == "fallback"
    assert result["error_type"] == "quota_exceeded"
    assert result["error_message"] == "429 rate limit"
