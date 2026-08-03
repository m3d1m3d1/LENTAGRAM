import logging
import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from services.channel_service import ChannelService

logger = logging.getLogger(__name__)
channel_service = ChannelService()

WELCOME_TEXT = (
    "👋 <b>Привет!</b>\n\n"
    "Я — <b>Lentagram</b>, бот для персональных новостных лент.\n\n"
    "Что я умею:\n"
    "• Создавать тематические «ленты» (подборки каналов)\n"
    "• Следить за новыми постами из добавленных каналов\n"
    "• Фильтровать посты по смыслу через ИИ\n"
    "• Переключаться между лентами — показывать только нужные посты\n\n"
    "Начни с создания первой ленты 👇"
)


def build_main_menu(user_id: int) -> InlineKeyboardMarkup:
    """Строит главное меню с учётом активной ленты."""
    settings = channel_service.get_user_settings(user_id)
    active_id = settings["active_feed_id"]
    show_all = settings["show_all_feeds"]

    feeds = channel_service.get_user_feeds(user_id)

    keyboard = [
        [InlineKeyboardButton("➕ Создать ленту", callback_data="create_feed")],
        [InlineKeyboardButton("📂 Мои ленты", callback_data="list_feeds")],
    ]

    # Кнопки переключения лент
    if feeds:
        if show_all or active_id is None:
            keyboard.append([InlineKeyboardButton("🔴 Показываю: ВСЕ ленты", callback_data="switch_feed_menu")])
        else:
            active_feed = next((f for f in feeds if f["id"] == active_id), None)
            name = active_feed["name"] if active_feed else "?"
            keyboard.append([InlineKeyboardButton(f"🔴 Показываю: «{name}»", callback_data="switch_feed_menu")])

    keyboard.extend([
        [InlineKeyboardButton("🧹 Очистить чат", callback_data="clear_chat_menu")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")],
    ])

    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Главное меню бота."""
    user_id = update.effective_user.id
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            WELCOME_TEXT, parse_mode=ParseMode.HTML, reply_markup=build_main_menu(user_id)
        )
    else:
        await update.message.reply_text(
            WELCOME_TEXT, parse_mode=ParseMode.HTML, reply_markup=build_main_menu(user_id)
        )


async def switch_feed_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Меню выбора активной ленты."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    feeds = channel_service.get_user_feeds(user_id)
    settings = channel_service.get_user_settings(user_id)
    active_id = settings["active_feed_id"]
    show_all = settings["show_all_feeds"]

    lines = ["📡 <b>Выбери, какие посты показывать:</b>\n"]
    keyboard = []

    # Кнопка "Все ленты"
    if show_all or active_id is None:
        lines.append("• 🔴 ВСЕ ленты (сейчас выбрано)")
    else:
        lines.append("• ⚪ ВСЕ ленты")
    keyboard.append([InlineKeyboardButton(
        "🔴 ВСЕ ленты" if (show_all or active_id is None) else "⚪ ВСЕ ленты",
        callback_data="activate_all_feeds"
    )])

    # Кнопки по каждой ленте
    for feed in feeds:
        is_active = (active_id == feed["id"]) and not show_all
        icon = "🔴" if is_active else "⚪"
        lines.append(f"• {icon} «{feed['name']}» ({len(feed['channels'])} кан.)")
        keyboard.append([InlineKeyboardButton(
            f"{icon} «{feed['name']}»",
            callback_data=f"activate_feed_{feed['id']}"
        )])

    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def activate_feed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Активирует конкретную ленту и показывает последние 5 постов."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    feed_id = int(query.data.split("_")[-1])
    channel_service.set_active_feed(user_id, feed_id)

    feed = channel_service.get_feed(user_id, feed_id)
    if not feed:
        await query.edit_message_text("⚠️ Лента не найдена")
        return

    # Показываем последние 5 постов из ленты
    last_posts = channel_service.get_last_posts(feed_id, limit=5)

    lines = [f"✅ Активна лента «{feed['name']}»\n"]
    lines.append(f"📋 Каналов: {len(feed['channels'])} | Тема: {feed.get('topic') or 'нет'}\n")

    if last_posts:
        lines.append("<b>Последние посты:</b>\n")
        for i, post in enumerate(last_posts, 1):
            preview = (post.get("post_text") or "")[:100].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if len(preview) == 100:
                preview += "…"
            channel_name = post.get("username") or post.get("title") or "канал"
            lines.append(f"{i}. <b>@{channel_name}</b>: {preview}")
    else:
        lines.append("📭 Пока нет постов в этой ленте.\nНовые посты будут приходить автоматически.")

    lines.append(f"\n🔴 Сейчас показываются посты ТОЛЬКО из «{feed['name']}»")

    keyboard = [
        [InlineKeyboardButton("📡 Сменить ленту", callback_data="switch_feed_menu")],
        [InlineKeyboardButton("🏠 В главное меню", callback_data="back_to_main")],
    ]

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def activate_all_feeds(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Активирует показ всех лент."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    channel_service.set_show_all_feeds(user_id)

    feeds = channel_service.get_user_feeds(user_id)

    lines = ["✅ Показываются посты из ВСЕХ лент\n"]
    for feed in feeds:
        lines.append(f"• «{feed['name']}» — {len(feed['channels'])} кан.")

    keyboard = [
        [InlineKeyboardButton("📡 Сменить ленту", callback_data="switch_feed_menu")],
        [InlineKeyboardButton("🏠 В главное меню", callback_data="back_to_main")],
    ]

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает справку."""
    text = (
        "📖 <b>Как пользоваться Lentagram</b>\n\n"
        "<b>Переключение лент</b>\n"
        "• Нажми «🔴 Показываю: ...» в главном меню\n"
        "• Выбери конкретную ленту — будут только её посты\n"
        "• Или «ВСЕ ленты» — посты из всех сразу\n"
        "• При переключении покажу последние 5 постов\n\n"
        "<b>Создание ленты</b>\n"
        "1. Нажми «➕ Создать ленту»\n"
        "2. Введи название и тему\n\n"
        "<b>Добавление каналов</b>\n"
        "• Присылай @username по одному, потом «Закончить»\n\n"
        "<b>Команды</b>\n"
        "/start — главное меню\n"
        "/feeds — список лент\n"
        "/clear — очистить чат\n"
        "/help — эта справка"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 В главное меню", callback_data="back_to_main")],
    ])

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)


# ... остальные функции (clear_chat_menu, clear_chat) остаются без изменений
CLEAR_MENU = InlineKeyboardMarkup([
    [InlineKeyboardButton("📅 За сегодня", callback_data="clear_chat_today")],
    [InlineKeyboardButton("🗑 За всё время", callback_data="clear_chat_all")],
    [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")],
])


async def clear_chat_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает меню выбора периода очистки."""
    query = update.callback_query
    await query.answer()

    text = (
        "🧹 <b>Очистка чата</b>\n\n"
        "Выбери период:\n\n"
        "📅 <b>За сегодня</b> — удалю сообщения за последние 24 часа\n"
        "🗑 <b>За всё время</b> — удалю всё возможное (ограничение Telegram: до 48 часов)\n\n"
        "⚠️ Удаляются только сообщения бота. Твои сообщения останутся."
    )

    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=CLEAR_MENU)


async def clear_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Очищает чат за выбранный период."""
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    bot = context.bot
    period = query.data

    period_text = "за сегодня" if period == "clear_chat_today" else "за всё время"

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
        tasks = [
            try_delete(current_msg_id - offset)
            for offset in range(batch_start, batch_start + 20)
        ]
        results = await asyncio.gather(*tasks)
        deleted += sum(results)

    confirm_msg = await bot.send_message(
        chat_id=chat_id,
        text=f"🧹 Удалено ~{deleted} сообщений {period_text}!"
    )

    await asyncio.sleep(2)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=confirm_msg.message_id)
    except Exception:
        pass

    await bot.send_message(
        chat_id=chat_id,
        text=WELCOME_TEXT,
        parse_mode=ParseMode.HTML,
        reply_markup=build_main_menu(update.effective_user.id),
    )