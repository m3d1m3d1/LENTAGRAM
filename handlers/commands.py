import logging
import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from services.channel_service import ChannelService
from services.i18n import SUPPORTED_LANGUAGES, get as tr

logger = logging.getLogger(__name__)
channel_service = ChannelService()


def t(user_id: int, key: str, **kwargs) -> str:
    return tr(channel_service.get_user_language(user_id), key, **kwargs)


def build_main_menu(user_id: int) -> InlineKeyboardMarkup:
    settings = channel_service.get_user_settings(user_id)
    lang = settings["language_code"]
    active_id = settings["active_feed_id"]
    show_all = settings["show_all_feeds"]
    feeds = channel_service.get_user_feeds(user_id)

    keyboard = [
        [InlineKeyboardButton(tr(lang, "button_create_feed"), callback_data="create_feed")],
        [InlineKeyboardButton(tr(lang, "button_my_feeds"), callback_data="list_feeds")],
    ]
    if feeds:
        if show_all or active_id is None:
            keyboard.append([InlineKeyboardButton(tr(lang, "showing_all_feeds"), callback_data="switch_feed_menu")])
        else:
            active_feed = next((f for f in feeds if f["id"] == active_id), None)
            keyboard.append([InlineKeyboardButton(tr(lang, "showing_feed", name=active_feed["name"] if active_feed else "?"), callback_data="switch_feed_menu")])

    keyboard.extend([
        [InlineKeyboardButton(tr(lang, "button_settings"), callback_data="settings")],
        [InlineKeyboardButton(tr(lang, "button_clear_chat"), callback_data="clear_chat_menu")],
        [InlineKeyboardButton(tr(lang, "button_help"), callback_data="help")],
    ])
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    text = t(user_id, "start_message")
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=build_main_menu(user_id))
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=build_main_menu(user_id))


async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    text = f"{t(user_id, 'settings_title')}\n\n{t(user_id, 'settings_description')}"
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(user_id, "button_language"), callback_data="language_menu")],
        [InlineKeyboardButton(t(user_id, "button_back_main"), callback_data="back_to_main")],
    ])
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)


async def language_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    keyboard = [[InlineKeyboardButton(meta["label"], callback_data=f"set_language_{code}")] for code, meta in SUPPORTED_LANGUAGES.items()]
    keyboard.append([InlineKeyboardButton(t(user_id, "button_back"), callback_data="settings")])
    await query.edit_message_text(
        f"{t(user_id, 'language_title')}\n\n{t(user_id, 'language_description')}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    language = query.data.rsplit("_", 1)[-1]
    channel_service.set_user_language(user_id, language)
    await query.edit_message_text(
        tr(language, "language_changed"),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(tr(language, "button_back_main"), callback_data="back_to_main")]]),
    )


async def switch_feed_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    feeds = channel_service.get_user_feeds(user_id)
    settings = channel_service.get_user_settings(user_id)
    lang = settings["language_code"]
    active_id = settings["active_feed_id"]
    show_all = settings["show_all_feeds"]

    lines = [tr(lang, "feed_select_title")]
    keyboard = []
    lines.append(tr(lang, "all_feeds_selected" if (show_all or active_id is None) else "all_feeds_unselected"))
    keyboard.append([InlineKeyboardButton(tr(lang, "all_feeds_button_selected" if (show_all or active_id is None) else "all_feeds_button_unselected"), callback_data="activate_all_feeds")])
    for feed in feeds:
        is_active = (active_id == feed["id"]) and not show_all
        icon = "🔴" if is_active else "⚪"
        lines.append(f"• {icon} «{feed['name']}» ({len(feed['channels'])} {tr(lang, 'channels_count_short')})")
        keyboard.append([InlineKeyboardButton(f"{icon} «{feed['name']}»", callback_data=f"activate_feed_{feed['id']}")])
    keyboard.append([InlineKeyboardButton(tr(lang, "button_back"), callback_data="back_to_main")])
    await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))


async def activate_feed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    lang = channel_service.get_user_language(user_id)
    feed_id = int(query.data.split("_")[-1])
    channel_service.set_active_feed(user_id, feed_id)
    feed = channel_service.get_feed(user_id, feed_id)
    if not feed:
        await query.edit_message_text(tr(lang, "feed_not_found"))
        return
    last_posts = channel_service.get_last_posts(feed_id, limit=5)
    lines = [tr(lang, "active_feed_title", name=feed["name"])]
    lines.append(tr(lang, "feed_summary", channels_count=len(feed["channels"]), topic=feed.get("topic") or tr(lang, "no_topic")))
    if last_posts:
        lines.append(tr(lang, "latest_posts_title"))
        for i, post in enumerate(last_posts, 1):
            preview = (post.get("post_text") or "")[:100].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if len(preview) == 100:
                preview += "…"
            channel_name = post.get("username") or post.get("title") or tr(lang, "channel_fallback")
            lines.append(f"{i}. <b>@{channel_name}</b>: {preview}")
    else:
        lines.append(tr(lang, "no_posts_in_feed"))
    lines.append(tr(lang, "only_feed_showing", name=feed["name"]))
    keyboard = [[InlineKeyboardButton(tr(lang, "button_change_feed"), callback_data="switch_feed_menu")], [InlineKeyboardButton(tr(lang, "button_back_main"), callback_data="back_to_main")]]
    await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))


async def activate_all_feeds(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    lang = channel_service.get_user_language(user_id)
    channel_service.set_show_all_feeds(user_id)
    lines = [tr(lang, "all_feeds_active")]
    for feed in channel_service.get_user_feeds(user_id):
        lines.append(f"• «{feed['name']}» — {len(feed['channels'])} {tr(lang, 'channels_count_short')}")
    keyboard = [[InlineKeyboardButton(tr(lang, "button_change_feed"), callback_data="switch_feed_menu")], [InlineKeyboardButton(tr(lang, "button_back_main"), callback_data="back_to_main")]]
    await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    markup = InlineKeyboardMarkup([[InlineKeyboardButton(t(user_id, "button_back_main"), callback_data="back_to_main")]])
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(t(user_id, "help_text"), parse_mode=ParseMode.HTML, reply_markup=markup)
    else:
        await update.message.reply_text(t(user_id, "help_text"), parse_mode=ParseMode.HTML, reply_markup=markup)


async def clear_chat_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(user_id, "button_clear_today"), callback_data="clear_chat_today")],
        [InlineKeyboardButton(t(user_id, "button_clear_all"), callback_data="clear_chat_all")],
        [InlineKeyboardButton(t(user_id, "button_back"), callback_data="back_to_main")],
    ])
    await query.edit_message_text(t(user_id, "clear_chat_title"), parse_mode=ParseMode.HTML, reply_markup=markup)


async def clear_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    bot = context.bot
    period = query.data
    period_text = t(user_id, "period_today" if period == "clear_chat_today" else "period_all")
    try:
        await query.delete_message()
    except Exception:
        pass
    current_msg_id = update.effective_message.message_id
    deleted = 0
    async def try_delete(msg_id):
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg_id)
            return True
        except Exception:
            return False
    for batch_start in range(1, 101, 20):
        deleted += sum(await asyncio.gather(*[try_delete(current_msg_id - offset) for offset in range(batch_start, batch_start + 20)]))
    confirm_msg = await bot.send_message(chat_id=chat_id, text=t(user_id, "clear_confirm", deleted=deleted, period=period_text))
    await asyncio.sleep(2)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=confirm_msg.message_id)
    except Exception:
        pass
    await bot.send_message(chat_id=chat_id, text=t(user_id, "start_message"), parse_mode=ParseMode.HTML, reply_markup=build_main_menu(user_id))
