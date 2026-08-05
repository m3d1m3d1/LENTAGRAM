import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler
from services.database import get_connection
from services.channel_service import ChannelService
from services.i18n import get as tr
from services.telethon_client import _get_client  # <-- ДОБАВЬ ЭТО
from utils.text import extract_username
logger = logging.getLogger(__name__)
channel_service = ChannelService()

def _t(user_id: int, key: str, **kwargs) -> str:
    return tr(channel_service.get_user_language(user_id), key, **kwargs)

SEARCH_CHANNELS, GET_CHANNEL_INPUT = range(10, 12)  # Новое состояние

async def add_channel_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Точка входа: выбор способа добавления канала."""
    query = update.callback_query
    await query.answer()

    feed_id = int(query.data.split("_")[-1])
    user_id = update.effective_user.id

    feed = channel_service.get_feed(user_id, feed_id)
    if not feed:
        await query.edit_message_text(
            _t(update.effective_user.id, "feed_not_found_deleted"),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(_t(update.effective_user.id, "button_my_feeds"), callback_data="list_feeds")]
            ])
        )
        return ConversationHandler.END

    context.user_data["target_feed_id"] = feed_id
    context.user_data["pending_channels"] = []

    text = _t(user_id, "add_channels_choose", feed_name=feed["name"])
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(_t(update.effective_user.id, "button_search_by_name"), callback_data=f"search_channels_{feed_id}")],
        [InlineKeyboardButton(_t(update.effective_user.id, "button_manual_add"), callback_data=f"manual_add_{feed_id}")],
        [InlineKeyboardButton(_t(update.effective_user.id, "button_cancel"), callback_data="cancel_add_channel")]
    ])
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    return ConversationHandler.END  # Здесь заканчиваем, дальше новый entry_point


async def manual_add_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает приглашение ввести каналы вручную."""
    query = update.callback_query
    await query.answer()

    feed_id = int(query.data.split("_")[-1])
    context.user_data["target_feed_id"] = feed_id

    text = _t(update.effective_user.id, "manual_add_prompt")
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(_t(update.effective_user.id, "button_finish"), callback_data="finish_adding")],
#        [InlineKeyboardButton(_t(update.effective_user.id, "button_cancel"), callback_data="cancel_add_channel")]
    ])
    await query.edit_message_text(text, reply_markup=markup)
    return GET_CHANNEL_INPUT


async def process_channel_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Принимаем каналы: @username, ссылки, через запятую, или пересланный пост."""
    logger.info(f"=== process_channel_input: text={update.message.text if update.message else 'none'} ===")
    
    feed_id = context.user_data.get("target_feed_id")
    if not feed_id:
        await update.message.reply_text(
            _t(update.effective_user.id, "feed_context_lost"),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(_t(update.effective_user.id, "button_my_feeds"), callback_data="list_feeds")]
            ])
        )
        return ConversationHandler.END

    
        # ===== ВАРИАНТ 1: Пересланный пост из канала =====
    logger.info("Checking forward...")
    forward_chat = None
    
    # PTB v20+: используем forward_origin вместо устаревшего forward_from_chat
    if hasattr(update.message, 'forward_origin') and update.message.forward_origin:
        origin = update.message.forward_origin
        # MessageOriginChannel имеет поле chat, MessageOriginChat тоже имеет chat
        if hasattr(origin, 'chat'):
            forward_chat = origin.chat
    
    if forward_chat:
        logger.info(f"Forward chat found: {forward_chat.type}")
        if forward_chat.type == "channel":
            username = forward_chat.username
            if username:
                channel_input = f"@{username}"
            else:
                await update.message.reply_text(_t(update.effective_user.id, "forward_channel_only"))
                return GET_CHANNEL_INPUT
        else:
            # Переслано не из канала (например, из чата или от пользователя)
            await update.message.reply_text(_t(update.effective_user.id, "forward_channel_only"))
            return GET_CHANNEL_INPUT
    elif update.message.text:
        channel_input = update.message.text.strip()
        logger.info(f"Text input: {channel_input}")
    else:
        # Нет ни пересланного сообщения, ни текста
        await update.message.reply_text(_t(update.effective_user.id, "nothing_recognized"))
        return GET_CHANNEL_INPUT

    # ===== ВАРИАНТ 2: Обычный текст =====
    logger.info("Parsing input...")
    raw_inputs = []
    for delimiter in [',', '\n', ' ']:
        if delimiter in channel_input:
            raw_inputs = [c.strip() for c in channel_input.split(delimiter) if c.strip()]
            break
    else:
        raw_inputs = [channel_input] if channel_input else []

    logger.info(f"Parsed inputs: {raw_inputs}")

    if not raw_inputs:
        await update.message.reply_text(_t(update.effective_user.id, "nothing_recognized"))
        return GET_CHANNEL_INPUT

    added = []
    failed = []
    telethon_manager = context.bot_data["telethon_manager"]
    logger.info(f"telethon_manager={telethon_manager}, is_started={telethon_manager.is_started if telethon_manager else 'None'}")
    
    for raw in raw_inputs:
        username = extract_username(raw)
        if not username:
            failed.append(raw)
            continue
        
        logger.info(f"=== Calling join_channel for @{username} ===")
        joined, title_or_error = await telethon_manager.join_channel(username)
        logger.info(f"=== join_channel result: {joined}, {title_or_error} ===")
        
        
        if not joined:
            failed.append(f"@{username} ({title_or_error})")
            continue

        channel_id = None
        try:
            from services.telethon_client import _get_client
            client = _get_client()
            entity = await client.get_entity(username)
            channel_id = entity.id
        except Exception as e:
            logger.warning(f"Не удалось получить channel_id для @{username}: {e}")

        channel_service.add_channel_to_feed(feed_id, username, title_or_error, channel_id)
        added.append(f"«{title_or_error}» (@{username})")
        context.user_data.setdefault("pending_channels", []).append(username)

    if telethon_manager and telethon_manager.is_started:
        await telethon_manager.refresh_handlers()

    response_lines = []
    if added:
        response_lines.append(_t(update.effective_user.id, "added_count", count=len(added)))
        response_lines.extend([f"• {a}" for a in added])
    if failed:
        response_lines.append(_t(update.effective_user.id, "failed_count", count=len(failed)))
        response_lines.extend([f"• {f}" for f in failed])

    response_text = "\n".join(response_lines) if response_lines else _t(update.effective_user.id, "nothing_added")

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(_t(update.effective_user.id, "button_add_more"), callback_data="add_more_channels")],
        [InlineKeyboardButton(_t(update.effective_user.id, "button_finish"), callback_data="finish_adding")],
    ])

    await update.message.reply_text(response_text, reply_markup=markup)
    return GET_CHANNEL_INPUT


async def finish_adding(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Добавляем все накопленные каналы в ленту."""
    query = update.callback_query
    await query.answer()

    feed_id = context.user_data.get("target_feed_id")
    pending = context.user_data.pop("pending_channels", [])
    context.user_data.pop("target_feed_id", None)

    if not pending:
        await query.edit_message_text(
            _t(update.effective_user.id, "no_channels_selected"),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(_t(update.effective_user.id, "button_back_main"), callback_data="back_to_main")]
            ])
        )
        return ConversationHandler.END

    feed = channel_service.get_feed(update.effective_user.id, feed_id)
    feed_name = feed["name"] if feed else "feed"

    # pending — список username'ов (строк)
    added_lines = [f"• @{u}" for u in pending]

    # Обновляем хендлеры Telethon
    telethon_manager = context.bot_data.get("telethon_manager")
    if telethon_manager and telethon_manager.is_started:
        await telethon_manager.refresh_handlers()

    text = _t(update.effective_user.id, "channels_added_done", count=len(pending), feed_name=feed_name, channels="\n".join(added_lines))
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(_t(update.effective_user.id, "button_add_more_channels"), callback_data=f"add_channel_{feed_id}")],
        [InlineKeyboardButton(_t(update.effective_user.id, "button_my_feeds"), callback_data="list_feeds")],
        [InlineKeyboardButton(_t(update.effective_user.id, "button_back_main"), callback_data="back_to_main")],
    ])

    await query.edit_message_text(text, reply_markup=markup)
    return ConversationHandler.END


async def cancel_add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("target_feed_id", None)
    context.user_data.pop("pending_channels", None)
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        _t(update.effective_user.id, "add_channels_cancelled"),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(_t(update.effective_user.id, "button_back_main"), callback_data="back_to_main")]]),
    )
    return ConversationHandler.END


# ====== просмотр и удаление каналов внутри ленты ======

async def _render_feed_channels(update: Update, user_id: int, feed_id: int) -> None:
    query = update.callback_query
    feed = channel_service.get_feed(user_id, feed_id)
    if not feed:
        await query.edit_message_text("⚠️ Лента не найдена")
        return

    channels = feed["channels"]

    if not channels:
        text = _t(user_id, "feed_channels_empty", feed_name=feed["name"])
    else:
        lines = [_t(user_id, "feed_channels_title", feed_name=feed["name"], count=len(channels))]
        lines.extend(
            f"• <b>{c['title'] or c['username']}</b> (@{c['username']})"
            for c in channels
        )
        text = "\n".join(lines)

    keyboard = [
        [InlineKeyboardButton(_t(user_id, "button_remove_channel", username=c["username"]), callback_data=f"removechan_{feed_id}_{c['username']}")]
        for c in channels
    ]
    keyboard.append([InlineKeyboardButton(_t(update.effective_user.id, "button_add_channels"), callback_data=f"add_channel_{feed_id}")])
    keyboard.append([InlineKeyboardButton(_t(update.effective_user.id, "button_edit_filter"), callback_data=f"edit_filter_{feed_id}")])
    keyboard.append([InlineKeyboardButton(_t(update.effective_user.id, "button_to_feeds"), callback_data="list_feeds")])

    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))


async def view_feed_channels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """callback_data вида channels_<feed_id> — список каналов ленты с кнопками удаления."""
    query = update.callback_query
    await query.answer()
    feed_id = int(query.data.split("_")[-1])
    await _render_feed_channels(update, update.effective_user.id, feed_id)


async def remove_channel_from_feed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """callback_data вида removechan_<feed_id>_<username>."""
    query = update.callback_query
    await query.answer()
    _, feed_id_str, username = query.data.split("_", 2)
    feed_id = int(feed_id_str)

    channel_service.remove_channel_from_feed(feed_id, username)
    await _render_feed_channels(update, update.effective_user.id, feed_id)


async def add_more_channels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Пользователь хочет добавить ещё каналы — остаёмся в диалоге."""
    query = update.callback_query
    await query.answer()

    feed_id = context.user_data.get("target_feed_id")
    feed = channel_service.get_feed(update.effective_user.id, feed_id)
    feed_name = feed["name"] if feed else "feed"

    text = _t(update.effective_user.id, "add_more_channels_prompt", feed_name=feed_name)
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(_t(update.effective_user.id, "button_finish"), callback_data="finish_adding")],
#        [InlineKeyboardButton(_t(update.effective_user.id, "button_cancel"), callback_data="cancel_add_channel")]
    ])

    await query.edit_message_text(text, reply_markup=markup)
    return GET_CHANNEL_INPUT





async def search_channels_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Точка входа для поиска каналов."""
    query = update.callback_query
    await query.answer()

    feed_id = int(query.data.split("_")[-1])
    context.user_data["target_feed_id"] = feed_id

    text = _t(update.effective_user.id, "search_channels_prompt")
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(_t(update.effective_user.id, "button_cancel"), callback_data="cancel_add_channel")]
    ])
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    return SEARCH_CHANNELS


async def process_search_results(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает поисковый запрос и показывает результаты."""
    search_query = update.message.text.strip()
    feed_id = context.user_data.get("target_feed_id")

    if not feed_id:
        await update.message.reply_text(
            _t(update.effective_user.id, "feed_context_lost"),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(_t(update.effective_user.id, "button_my_feeds"), callback_data="list_feeds")]
            ])
        )
        return ConversationHandler.END

    await update.message.reply_text(_t(update.effective_user.id, "searching_channels", query=search_query))

    # Поиск через Telethon
    telethon_manager = context.bot_data["telethon_manager"]
    client = _get_client()

    results = []
    try:
        # Ищем глобально (диалоги + каналы)
        async for dialog in client.iter_dialogs():
            if dialog.is_channel and search_query.lower() in dialog.name.lower():
                entity = dialog.entity
                username = getattr(entity, 'username', None)
                if username:
                    results.append({
                        "name": dialog.name,
                        "username": username,
                        "id": dialog.id
                    })
                if len(results) >= 10:
                    break

        # Также пробуем search_global
        if len(results) < 5:
            try:
                found = await client(search_query)
                # ... дополнительная логика
            except Exception:
                pass

    except Exception as e:
        logger.error(f"Ошибка поиска: {e}")

    if not results:
        await update.message.reply_text(
            _t(update.effective_user.id, "search_not_found"),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(_t(update.effective_user.id, "button_search_again"), callback_data=f"search_channels_{feed_id}")],
                [InlineKeyboardButton(_t(update.effective_user.id, "button_add_by_username"), callback_data=f"add_channel_{feed_id}")],
                [InlineKeyboardButton(_t(update.effective_user.id, "button_cancel"), callback_data="cancel_add_channel")]
            ])
        )
        return SEARCH_CHANNELS

    # Показываем результаты
    lines = [_t(update.effective_user.id, "search_found", count=len(results))]
    keyboard = []

    for i, ch in enumerate(results, 1):
        lines.append(f"{i}. <b>{ch['name']}</b>\n   @{ch['username']}")
        keyboard.append([InlineKeyboardButton(
            f"➕ {ch['name'][:30]}",
            callback_data=f"add_found_channel_{feed_id}_{ch['username']}"
        )])

    keyboard.append([InlineKeyboardButton(_t(update.effective_user.id, "button_new_search"), callback_data=f"search_channels_{feed_id}")])
    keyboard.append([InlineKeyboardButton(_t(update.effective_user.id, "button_cancel"), callback_data="cancel_add_channel")])

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return GET_CHANNEL_INPUT  # Переходим в обычное состояние добавления


async def add_found_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Добавляет канал из результатов поиска."""
    query = update.callback_query
    await query.answer()

    # callback_data: add_found_channel_<feed_id>_<username>
    parts = query.data.split("_", 3)  # 4 части: add, found, channel, <feed_id>_<username>
    feed_id = int(parts[3].split("_")[0])
    username = "_".join(parts[3].split("_")[1:])  # username может содержать _

    context.user_data["target_feed_id"] = feed_id

    telethon_manager = context.bot_data["telethon_manager"]
    joined, title_or_error = await telethon_manager.join_channel(username)

    if not joined:
        await query.edit_message_text(
            _t(update.effective_user.id, "channel_add_failed", username=username, error=title_or_error),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(_t(update.effective_user.id, "button_search_again"), callback_data=f"search_channels_{feed_id}")],
                [InlineKeyboardButton(_t(update.effective_user.id, "button_my_feeds"), callback_data="list_feeds")],
            ])
        )
        return ConversationHandler.END

    channel_id = None
    try:
        client = _get_client()
        entity = await client.get_entity(username)
        channel_id = entity.id
    except Exception as e:
        logger.warning(f"Не удалось получить channel_id: {e}")

    channel_service.add_channel_to_feed(feed_id, username, title_or_error, channel_id)

    if telethon_manager and telethon_manager.is_started:
        await telethon_manager.refresh_handlers()

    await query.edit_message_text(
        _t(update.effective_user.id, "channel_added_next", title=title_or_error, username=username),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(_t(update.effective_user.id, "button_search_more"), callback_data=f"search_channels_{feed_id}")],
            [InlineKeyboardButton(_t(update.effective_user.id, "button_add_by_username"), callback_data=f"manual_add_{feed_id}")],
            [InlineKeyboardButton(_t(update.effective_user.id, "button_my_feeds"), callback_data="list_feeds")],
            [InlineKeyboardButton(_t(update.effective_user.id, "button_back_main"), callback_data="back_to_main")],
        ])
    )
    return ConversationHandler.END

async def suggest_add_to_feed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Если пользователь кидает ссылку/@username/пост без вызова меню — предлагаем добавить в ленту."""
    user_id = update.effective_user.id
    
    # Проверяем, есть ли у пользователя ленты
    feeds = channel_service.get_user_feeds(user_id)
    if not feeds:
        return  # Нет лент — ничего не делаем
    
    text = update.message.text.strip()
    
    # Проверяем, похоже ли на канал
    username = extract_username(text)
    forward_chat = None
    
    if update.message.forward_from_chat:
        forward_chat = update.message.forward_from_chat
    elif hasattr(update.message, 'forward_origin') and update.message.forward_origin:
        origin = update.message.forward_origin
        if hasattr(origin, 'chat'):
            forward_chat = origin.chat
    
    if not username and not forward_chat:
        return  # Не похоже на канал — игнорируем
    if forward_chat and forward_chat.type == "channel":
        channel_username = forward_chat.username
        if channel_username:
            username = channel_username
            logger.info(f"Got username from forwarded post: @{username}")
        else:
            # Приватный канал без username — показываем ID или title
            logger.info("Forwarded from private channel, no username")
            await update.message.reply_text(
                _t(user_id, "private_channel_no_username")
            )
            return
    
    # Формируем клавиатуру с лентами
    keyboard = []
    for feed in feeds:
        keyboard.append([InlineKeyboardButton(
            f"📂 {feed['name']}",
            callback_data=f"quick_add_{feed['id']}_{username or forward_chat.username or 'unknown'}"
        )])
    
    keyboard.append([InlineKeyboardButton(_t(update.effective_user.id, "button_do_not_add"), callback_data="quick_add_cancel")])
    
    await update.message.reply_text(
        _t(user_id, "quick_add_where"),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def quick_add_to_feed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Быстрое добавление канала в выбранную ленту."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "quick_add_cancel":
        await query.edit_message_text(_t(update.effective_user.id, "cancelled"))
        return
    
    # callback_data: quick_add_<feed_id>_<username>
    parts = query.data.split("_", 3)
    feed_id = int(parts[2])
    username = parts[3]
    
    telethon_manager = context.bot_data.get("telethon_manager")
    
    if telethon_manager and telethon_manager.is_started:
        joined, title_or_error = await telethon_manager.join_channel(username)
        
        if joined:
            # Получаем channel_id
            channel_id = None
            try:
                client = _get_client()
                entity = await client.get_entity(username)
                channel_id = entity.id
            except Exception as e:
                logger.warning(f"Не удалось получить channel_id: {e}")
            
            channel_service.add_channel_to_feed(feed_id, username, title_or_error, channel_id)
            
            if telethon_manager.is_started:
                await telethon_manager.refresh_handlers()
            
            await query.edit_message_text(
                _t(update.effective_user.id, "channel_added", title=title_or_error),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(_t(update.effective_user.id, "button_back_main"), callback_data="back_to_main")]
                ])
            )
        else:
            await query.edit_message_text(
                _t(update.effective_user.id, "channel_add_failed", username=username, error=title_or_error),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(_t(update.effective_user.id, "button_back_main"), callback_data="back_to_main")]
                ])
            )
    else:
        await query.edit_message_text(
            _t(update.effective_user.id, "bot_temporarily_unavailable"),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(_t(update.effective_user.id, "button_back_main"), callback_data="back_to_main")]
            ])
        )

async def handle_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    # callback_data: fb_like_<post_id> / fb_dislike_<post_id>
    parts = query.data.split("_")

    action = parts[1]          # like / dislike
    post_id = int(parts[2])

    feedback = 1 if action == "like" else -1

    with get_connection() as conn:
        cursor = conn.cursor()

        # Достаём feed_id поста — он нужен для UNIQUE(user_id, feed_id, post_id)
        post_row = cursor.execute(
            "SELECT feed_id FROM posts WHERE id = ?",
            (post_id,)
        ).fetchone()

        if not post_row:
            logger.warning(f"Фидбек на несуществующий пост {post_id}")
            return

        feed_id = post_row["feed_id"]

        # Если уже голосовал — обновляем оценку
        row = cursor.execute("""
            SELECT id
            FROM post_feedback
            WHERE user_id = ?
              AND feed_id = ?
              AND post_id = ?
        """, (
            update.effective_user.id,
            feed_id,
            post_id
        )).fetchone()

        if row:
            cursor.execute("""
                UPDATE post_feedback
                SET feedback = ?,
                    created_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                feedback,
                row["id"]
            ))
        else:
            cursor.execute("""
                INSERT INTO post_feedback
                (user_id, feed_id, post_id, feedback)
                VALUES (?, ?, ?, ?)
            """, (
                update.effective_user.id,
                feed_id,
                post_id,
                feedback
            ))

        conn.commit()

    # Показываем выбранную кнопку
    if feedback == 1:
        keyboard = [[
            InlineKeyboardButton(
                "✅❤️ Полезно",
                callback_data=f"fb_like_{post_id}"
            ),
            InlineKeyboardButton(
                "👎 Неинтересно",
                callback_data=f"fb_dislike_{post_id}"
            )
        ]]
    else:
        keyboard = [[
            InlineKeyboardButton(
                "❤️ Полезно",
                callback_data=f"fb_like_{post_id}"
            ),
            InlineKeyboardButton(
                "✅👎 Неинтересно",
                callback_data=f"fb_dislike_{post_id}"
            )
        ]]

    await query.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup(keyboard)
    )