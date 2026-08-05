import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler
from services.ai.filter_generator import FilterGenerator
from services.channel_service import ChannelService
from services.i18n import get as tr

logger = logging.getLogger(__name__)
channel_service = ChannelService()
filter_generator = FilterGenerator()

def _lang(user_id: int) -> str:
    return channel_service.get_user_language(user_id)

def _t(user_id: int, key: str, **kwargs) -> str:
    return tr(_lang(user_id), key, **kwargs)


def _filters_ready_text(user_id: int, feed_name: str, generated_by: str) -> str:
    if generated_by == "fallback":
        return _t(user_id, "filters_ready_fallback", feed_name=feed_name)
    return _t(user_id, "filters_ready_ai", feed_name=feed_name)
GET_FEED_NAME, GET_FEED_FILTER = range(2)
GET_EDITED_FILTER = 20

# ====== СОЗДАНИЕ ЛЕНТЫ ======

async def create_feed_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Точка входа: спрашиваем название ленты."""
    text = _t(update.effective_user.id, "create_feed_prompt")
    markup = InlineKeyboardMarkup([[InlineKeyboardButton(_t(update.effective_user.id, "button_cancel"), callback_data="cancel_feed_creation")]])

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)

    return GET_FEED_NAME


async def get_feed_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    print(f">>> get_feed_name called! text='{update.message.text if update.message else 'NO MESSAGE'}'")
    feed_name = update.message.text.strip()
    if not feed_name:
        await update.message.reply_text(_t(update.effective_user.id, "feed_name_empty"))
        return GET_FEED_NAME

    context.user_data["new_feed_name"] = feed_name

    waiting_message = await update.message.reply_text(
        _t(update.effective_user.id, "generating_filters", feed_name=feed_name)
    )

    # --- защита от зависания ИИ ---
    try:
        result = await asyncio.wait_for(
            filter_generator.generate_filters(feed_name),
            timeout=30.0
        )
    except asyncio.TimeoutError as e:
        logger.error(
            "Filter generation failed: error_type=%s, model=%s, endpoint=%s",
            "timeout",
            "configured AI provider chain",
            "filter_generator.generate_filters",
            exc_info=True
        )
        result = filter_generator.fallback_result(
            feed_name,
            "timeout",
            error_message=str(e) or "Filter generation timed out",
        )
    except Exception as e:
        logger.error(
            "Filter generation failed: error_type=%s, model=%s, endpoint=%s",
            "unknown",
            "configured AI provider chain",
            "filter_generator.generate_filters",
            exc_info=True
        )
        result = filter_generator.fallback_result(
            feed_name,
            "unknown",
            error_message=str(e),
        )
    # ------------------------------

    filters = result["filters"]
    generated_by = result.get("generated_by", "ai")
    logger.info("Filter generation source: %s", generated_by)

    context.user_data["generated_filters"] = filters


    text = _filters_ready_text(update.effective_user.id, feed_name, generated_by)


    for i, item in enumerate(filters, start=1):
        text += (
            f"<b>{i}. {item['title']}</b>\n"
            f"{item['description']}\n\n"
        )


    keyboard = [
        [
            InlineKeyboardButton(
                "1️⃣",
                callback_data="choose_filter_0"
            ),
            InlineKeyboardButton(
                "2️⃣",
                callback_data="choose_filter_1"
            )
        ],
        [
            InlineKeyboardButton(
                "3️⃣",
                callback_data="choose_filter_2"
            ),
            InlineKeyboardButton(
                _t(update.effective_user.id, "button_custom_filter"),
                callback_data="choose_filter_custom"
            )
        ],
        [
            InlineKeyboardButton(
                _t(update.effective_user.id, "button_cancel"),
                callback_data="cancel_feed_creation"
            )
        ]
    ]


    await waiting_message.edit_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


    return GET_FEED_FILTER

async def choose_filter(update: Update, context: ContextTypes.DEFAULT_TYPE)-> int:

    query = update.callback_query
    await query.answer()

    data = query.data


    if data == "choose_filter_custom":

        context.user_data["waiting_custom_filter"] = True

        await query.edit_message_text(
            _t(update.effective_user.id, "custom_filter_prompt")
        )

        return GET_FEED_FILTER



    index = int(data.split("_")[-1])


    filters = context.user_data.get(
        "generated_filters",
        []
    )


    if index >= len(filters):
        return ConversationHandler.END


    selected_filter = filters[index]["ai_prompt"]


    return await _finish_feed_creation(
        update,
        context,
        selected_filter
    )   


async def get_feed_filter(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return GET_FEED_FILTER


    filter_prompt = update.message.text.strip()

    if not filter_prompt:
        await update.message.reply_text(
            _t(update.effective_user.id, "filter_empty")
        )
        return GET_FEED_FILTER


    return await _finish_feed_creation(
        update,
        context,
        filter_prompt
    )

async def _finish_feed_creation(update: Update, context: ContextTypes.DEFAULT_TYPE, filter_prompt: str | None) -> int:
    user_id = update.effective_user.id
    feed_name = context.user_data.pop("new_feed_name", None)

    if not feed_name:
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(_t(user_id, "button_create_feed"), callback_data="create_feed")],
            [InlineKeyboardButton(_t(user_id, "button_back_main"), callback_data="back_to_main")],
        ])
        await _reply(update, _t(user_id, "feed_creation_lost"), markup)
        return ConversationHandler.END

    feed_id = channel_service.create_feed(user_id, feed_name, filter_prompt)

    text = (
            _t(user_id, "feed_created", feed_name=feed_name)
            + (_t(user_id, "feed_created_with_filter", filter_prompt=filter_prompt) if filter_prompt else _t(user_id, "feed_created_without_filter"))
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(_t(user_id, "button_add_channel"), callback_data=f"add_channel_{feed_id}")],
        [InlineKeyboardButton(_t(user_id, "button_my_feeds"), callback_data="list_feeds")],
        [InlineKeyboardButton(_t(user_id, "button_back_main"), callback_data="back_to_main")],
    ])
    await _reply(update, text, markup)
    return ConversationHandler.END


async def cancel_feed_creation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("new_feed_name", None)
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        _t(update.effective_user.id, "feed_creation_cancelled"),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(_t(user_id, "button_back_main"), callback_data="back_to_main")]]),
    )
    return ConversationHandler.END


# ====== ПРОСМОТР / УДАЛЕНИЕ ЛЕНТ ======

async def list_feeds(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user_id = update.effective_user.id
        feeds = channel_service.get_user_feeds(user_id)

        if not feeds:
            text = _t(user_id, "no_feeds")
            markup = InlineKeyboardMarkup([[InlineKeyboardButton(_t(user_id, "button_create_feed"), callback_data="create_feed")]])
            await _reply(update, text, markup)
            return

        lines = []
        for feed in feeds:
            topic_part = _t(user_id, "feed_topic_part", topic=feed["topic"]) if feed["topic"] else ""
            filter_status = "🤖" if feed.get("ai_filter_enabled", True) else "🚫"
            lines.append(f"• <b>{feed['name']}</b> {filter_status} ({len(feed['channels'])} кан.){topic_part}")
        text = _t(user_id, "feeds_title") + "\n".join(lines)

        keyboard = []
        for feed in feeds:
            filter_btn_text = _t(user_id, "ai_on") if feed.get("ai_filter_enabled", True) else _t(user_id, "ai_off")
            keyboard.append([
                InlineKeyboardButton(f"📡 {feed['name']}", callback_data=f"channels_{feed['id']}"),
                InlineKeyboardButton(filter_btn_text, callback_data=f"toggle_ai_{feed['id']}"),
                InlineKeyboardButton("🗑", callback_data=f"delete_feed_{feed['id']}"),
            ])
        keyboard.append([InlineKeyboardButton(_t(user_id, "button_create_new_feed"), callback_data="create_feed")])
        keyboard.append([InlineKeyboardButton(_t(user_id, "button_back"), callback_data="back_to_main")])

        await _reply(update, text, InlineKeyboardMarkup(keyboard))

    except Exception as e:
        logger.error(f"Ошибка в list_feeds: {e}", exc_info=True)
        markup = InlineKeyboardMarkup([[InlineKeyboardButton(_t(user_id, "button_back_main"), callback_data="back_to_main")]])
        await _reply(update, _t(update.effective_user.id, "feeds_load_error"), markup)


async def delete_feed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    feed_id = int(query.data.split("_")[-1])
    user_id = update.effective_user.id

    channel_service.delete_feed(user_id, feed_id)
    await list_feeds(update, context)


async def toggle_ai_filter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """callback_data вида toggle_ai_<feed_id> — переключает ИИ-фильтр."""
    query = update.callback_query
    await query.answer()
    feed_id = int(query.data.split("_")[-1])
    user_id = update.effective_user.id

    new_state = channel_service.toggle_ai_filter(user_id, feed_id)
    status = _t(user_id, "ai_filter_enabled") if new_state else _t(user_id, "ai_filter_disabled")

    await query.answer(_t(user_id, "ai_filter_status", status=status))
    await list_feeds(update, context)


# ====== хелпер: ответ одинаково для callback и обычного сообщения ======

async def _reply(update: Update, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)

def _escape_html(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def edit_filter_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает текущий фильтр ленты в копируемом виде и просит прислать новый."""
    query = update.callback_query
    await query.answer()

    feed_id = int(query.data.split("_")[-1])
    user_id = update.effective_user.id

    feed = channel_service.get_feed(user_id, feed_id)
    if not feed:
        await query.edit_message_text(
            _t(user_id, "feed_not_found_deleted"),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(_t(user_id, "button_my_feeds"), callback_data="list_feeds")]
            ])
        )
        return ConversationHandler.END

    context.user_data["editing_feed_id"] = feed_id

    current_filter = feed.get("topic") or _t(user_id, "filter_not_set")
    safe_filter = _escape_html(current_filter)

    text = _t(user_id, "edit_filter_prompt", feed_name=feed["name"], filter_text=safe_filter)
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(_t(update.effective_user.id, "button_cancel"), callback_data="cancel_edit_filter")]
    ])

    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    return GET_EDITED_FILTER


async def save_edited_filter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет новый текст фильтра, присланный пользователем."""
    new_filter = update.message.text.strip()
    if not new_filter:
        await update.message.reply_text(_t(update.effective_user.id, "filter_empty_retry"))
        return GET_EDITED_FILTER

    feed_id = context.user_data.pop("editing_feed_id", None)
    if not feed_id:
        await update.message.reply_text(
            _t(update.effective_user.id, "feed_context_lost"),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(_t(user_id, "button_my_feeds"), callback_data="list_feeds")]
            ])
        )
        return ConversationHandler.END

    user_id = update.effective_user.id
    ok = channel_service.update_feed_filter(user_id, feed_id, new_filter)

    if not ok:
        await update.message.reply_text(
            _t(user_id, "filter_save_failed"),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(_t(user_id, "button_my_feeds"), callback_data="list_feeds")]
            ])
        )
        return ConversationHandler.END

    feed = channel_service.get_feed(user_id, feed_id)
    feed_name = feed["name"] if feed else "feed"

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(_t(user_id, "button_to_feed_channels"), callback_data=f"channels_{feed_id}")],
        [InlineKeyboardButton(_t(user_id, "button_my_feeds"), callback_data="list_feeds")],
    ])
    await update.message.reply_text(
        _t(user_id, "filter_updated", feed_name=feed_name),
        reply_markup=markup,
    )
    return ConversationHandler.END


async def cancel_edit_filter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("editing_feed_id", None)
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        _t(update.effective_user.id, "edit_cancelled"),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(_t(user_id, "button_back_main"), callback_data="back_to_main")]]),
    )
    return ConversationHandler.END


