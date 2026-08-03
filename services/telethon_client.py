import logging
import asyncio
from typing import Optional

from telethon import TelegramClient, events
from telethon.errors import UserAlreadyParticipantError, FloodWaitError
from telegram.constants import ParseMode
from telethon.sessions import StringSession
from config import API_ID, API_HASH, TELETHON_SESSION
from services.channel_service import ChannelService
from services.ai.analyzer import AIAnalyzer


logger = logging.getLogger(__name__)

_client: Optional[TelegramClient] = None


def _get_client() -> TelegramClient:
    global _client

    if _client is None:
        if TELETHON_SESSION:
            session = StringSession(TELETHON_SESSION)
            logger.info(
                f"Creating Telethon client, session_len={len(TELETHON_SESSION)}"
            )
        else:
            session = "lentagram_session"
            logger.info(
                "Creating file session client"
            )

        _client = TelegramClient(
            session,
            API_ID,
            API_HASH
        )

    return _client

async def _ensure_connected(client: TelegramClient) -> None:
    """Гарантирует, что клиент подключен перед RPC-вызовом.
    Защищает от 'Cannot send requests while disconnected',
    которая возникает при разовых вызовах во время разрыва/переподключения."""
    if not client.is_connected():
        await client.connect()

def reset_client():
    """Сбрасывает singleton клиента (для пересоздания с новой сессией)."""
    global _client
    if _client is not None:
        _client = None
        logger.info("Client reset")


class TelethonManager:
    def __init__(self, bot):
        self.bot = bot
        self.channel_service = ChannelService()
        self.ai_analyzer = AIAnalyzer()
        self._started = False
        self._runner_task = None

    async def start(self) -> None:
        client = _get_client()

        logger.info("Using singleton Telethon client")

        try:
            logger.info("Connecting...")
            await client.connect()

            logger.info("Connected!")

            auth = await client.is_user_authorized()
            logger.info(f"Authorized: {auth}")

            if not auth:
                logger.error("NOT AUTHORIZED")
                await client.disconnect()
                return

            me = await client.get_me()
            logger.info(f"Logged in as: {me.first_name} (@{me.username})")

            # регистрируем обработчик
            client.add_event_handler(
                self._on_new_message,
                events.NewMessage()
            )

            asyncio.create_task(
                client.run_until_disconnected()
            )

            self._started = True
            
            logger.info("✅ Telethon started successfully")

        except Exception as e:
            logger.error(
                f"Telethon start error: {e}",
                exc_info=True
            )
            await client.disconnect()

    async def stop(self) -> None:
        client = _get_client()

        if client.is_connected():
            await client.disconnect()

        if self._runner_task:
            self._runner_task.cancel()
            try:
                await self._runner_task
            except asyncio.CancelledError:
                pass

        self._started = False
        logger.info("Telethon-клиент отключён")
    def is_started(self) -> bool:
        return self._started

    async def refresh_handlers(self):

        if not self._started:
            logger.warning(
                "Telethon не запущен"
            )
            return

        client = _get_client()

        client.remove_event_handler(
            self._on_new_message
        )

        client.add_event_handler(
            self._on_new_message,
            events.NewMessage()
        )

        logger.info(
            "Обновлён мониторинг каналов"
        )

    

    async def join_channel(self, username: str) -> tuple[bool, str]:
        """
        Проверяет доступ к каналу.
        НЕ подписывает аккаунт.
        """
        
        try:
            client = _get_client()
            await _ensure_connected(client)
            entity = await client.get_entity(username)

            if not getattr(entity, "broadcast", False):
                return False, "Это не канал Telegram"

            return True, entity.title or username


        except Exception as e:
            logger.error(
                f"Не удалось получить канал @{username}: {e}"
            )

            return False, "Нет доступа к каналу"

    async def _on_new_message(self, event: events.NewMessage.Event) -> None:
        if not event.chat:
            return

        # Логируем ВСЕ каналы, даже не в лентах
        if event.is_channel:
            username = getattr(event.chat, 'username', None)
            logger.info(
                f"КАНАЛ: id={event.chat.id}, username=@{username}, text_preview={str(event.message.text)[:50] if event.message.text else 'N/A'}")

        if not event.is_channel:
            return
        ...

        channel_id = event.chat.id
        logger.info(f"ПОЛУЧЕНО СООБЩЕНИЕ: channel={channel_id}, is_channel=True")

        feeds = self.channel_service.get_feeds_by_channel_id(channel_id)
        logger.info(f"Канал {channel_id}: найдено {len(feeds)} лент")

        # FALLBACK: если по channel_id не нашли — ищем по username
        if not feeds:
            username = getattr(event.chat, "username", None)
            if username:
                logger.info(f"Fallback по username: @{username}")
                feeds = self.channel_service.get_feeds_for_channel(username)

        if not feeds:
            logger.info(f"Канал {channel_id} не привязан ни к одной ленте")
            return

        username = getattr(event.chat, "username", None)
        if username:
            post_link = f"https://t.me/{username}/{event.message.id}"
            channel_name = username
        else:
            post_link = f"https://t.me/c/{str(channel_id)[4:]}/{event.message.id}"
            channel_name = f"канал_{channel_id}"

        post_text = event.message.message or event.message.text or ""
        
        # Проверяем, является ли сообщение частью альбома (группы медиа)
        grouped_id = getattr(event.message, 'grouped_id', None)
        is_album_part = grouped_id is not None
        
        # Если это часть альбома, проверяем, первое ли это сообщение в группе
        if is_album_part:
            # Для альбомов обрабатываем только первое сообщение, чтобы избежать дублирования
            # Telethon обычно отправляет первое сообщение альбома с полным текстом
            pass  # Продолжаем обработку

        # Получаем внутренний ID канала из БД
        channel_db_id = self.channel_service.get_channel_db_id(channel_id)
        if not channel_db_id:
            logger.warning(f"Канал {channel_id} не найден в БД")
            return
        
        
        for feed in feeds:

            # ПРОВЕРЯЕМ: активна ли эта лента для пользователя?
            user_settings = self.channel_service.get_user_settings(feed["user_id"])
            active_id = user_settings["active_feed_id"]
            show_all = user_settings["show_all_feeds"]

            # Если выбрана конкретная лента и это не она — пропускаем
            if not show_all and active_id is not None and active_id != feed["feed_id"]:
                logger.info(f"Лента {feed['name']} не активна для юзера {feed['user_id']}, пропускаем")
                continue

            # Проверяем дубли - для альбомов используем grouped_id если есть
            check_message_id = event.message.id
            if self.channel_service.is_post_sent(feed["feed_id"], channel_db_id, check_message_id):
                logger.info(f"Пост {check_message_id} уже отправлен в ленту {feed['name']}")
                continue

            try:
                post_id = self.channel_service.save_post(
                    feed["feed_id"],
                    channel_db_id,
                    check_message_id,
                    post_text
                )
                logger.info(f"POST SAVED id={post_id}")

                analysis = None
                if feed.get("ai_filter_enabled", True) and post_id:
                    analysis = await self.ai_analyzer.analyze_post(
                        post_text,
                        feed["topic"]
                    )
                    # AI сказал не показывать — пропускаем
                    if not analysis.get("relevant", True):
                        logger.info(f"Пост отфильтрован AI: {analysis.get('filter_reason', 'нет причины')}")
                        try:
                            self.channel_service.save_ai_analysis(post_id, analysis)
                        except Exception as e:
                            logger.error(f"Ошибка сохранения AI (отфильтрован): {e}")
                        continue

                    # Сохраняем анализ ПЕРЕД отправкой (если упадёт — пост ещё не ушёл)
                    if post_id and analysis:
                        try:
                            self.channel_service.save_ai_analysis(post_id, analysis)
                        except Exception as e:
                            logger.error(f"Ошибка сохранения AI-анализа: {e}")
                            # Не прерываем отправку из-за ошибки БД

                    # Отправляем пост пользователю
                    await self._deliver_to_user(
                        feed,
                        channel_name,
                        post_text,
                        post_link,
                        event.message,
                        channel_db_id,
                        analysis,
                        post_id
                    )

            except Exception as e:
                logger.error(
                    f"Ошибка обработки поста из {channel_name} для ленты {feed['name']}: {e}",
                    exc_info=True,
                )
    async def _deliver_to_user(
            self,
            feed: dict,
            username: str,
            post_text: str,
            post_link: str,
            message,
            channel_db_id: int = None,
            ai_analysis: dict = None,
            post_id: int = None,
    ):
        """
        Отправляет пост пользователю в личку.
        Если есть медиа (включая альбомы) — скачиваем через Telethon и отправляем через PTB.
        Если текстовый пост — отправляем текст с превью.
        """
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo, InputMediaDocument, InputMediaAudio

        feedback_markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("❤️ Полезно", callback_data=f"fb_like_{post_id}"),
                InlineKeyboardButton("👎 Неинтересно", callback_data=f"fb_dislike_{post_id}")
            ]
        ])
        # Экранируем HTML-спецсимволы в тексте поста
        safe_text = post_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        preview = safe_text[:500] + ("…" if len(safe_text) > 500 else "")

        ai_block = ""

        if ai_analysis:
            ai_block = (
                f"🤖 Категория: {ai_analysis.get('category', 'не определена')}\n"
                f"⭐ Важность: {ai_analysis.get('importance', '?')}/10\n\n"
                f"📝 Кратко:\n"
                f"{ai_analysis.get('summary', '')}\n\n"
            )


        caption = (
            f"📬 Лента «{feed['name']}» · из {username}\n\n"
            f"{ai_block}"
            f"{preview}\n\n"
            f'🔗 <a href="{post_link}">Открыть оригинал</a>'
        )

        # Проверяем, является ли сообщение альбомом (группой медиа)
        grouped_id = getattr(message, 'grouped_id', None)
        is_album = grouped_id is not None
        
        # Лимит caption в Telegram — 1024 символа для медиа, 4096 для текста
        caption_limit = 1024 if message.media else 4096
        if len(caption) > caption_limit:
            caption = caption[:caption_limit - 3] + "…"

        try:
            client = _get_client()
            
            if is_album and message.media:
                # Получаем все сообщения в альбоме
                album_messages = await client.get_messages(
                    message.chat_id,
                    ids=range(message.id, message.id + 10)  # Максимум 10 фото в альбоме
                )
                
                # Фильтруем только сообщения с тем же grouped_id
                album_messages = [m for m in album_messages if getattr(m, 'grouped_id', None) == grouped_id]
                
                if len(album_messages) > 1:
                    # Это альбом — собираем все медиа
                    media_group = []
                    for msg in album_messages:
                        if not msg.media:
                            continue
                            
                        buffer = await client.download_media(msg.media, bytes)
                        if buffer is None:
                            continue
                            
                        from telegram import InputFile
                        import io
                        media_file = InputFile(io.BytesIO(buffer))
                        
                        # Определяем тип медиа и добавляем в группу
                        if msg.photo:
                            media_group.append(InputMediaPhoto(media=media_file, caption=caption if len(media_group) == 0 else ""))
                        elif msg.video:
                            media_group.append(InputMediaVideo(media=media_file, caption=caption if len(media_group) == 0 else ""))
                        elif msg.document:
                            file_name = getattr(msg.document.attributes[0], 'file_name', 'file') if msg.document.attributes else 'file'
                            media_group.append(InputMediaDocument(media=media_file, filename=file_name, caption=caption if len(media_group) == 0 else ""))
                        elif msg.audio:
                            media_group.append(InputMediaAudio(media=media_file, caption=caption if len(media_group) == 0 else ""))
                    
                    # Отправляем всю группу одним запросом
                    if media_group:
                        await self.bot.send_media_group(
                            chat_id=feed["user_id"],
                            media=media_group,
                            reply_markup=feedback_markup if len(media_group) == 1 else None
                        )
                        return
            
            # Обычная отправка одного медиа или текста
            if message.media:
                # Скачиваем файл через Telethon во временный буфер
                buffer = await client.download_media(message.media, bytes)

                if buffer is None:
                    # Не удалось скачать — отправляем текст
                    await self.bot.send_message(
                        chat_id=feed["user_id"],
                        text=caption,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True,
                        reply_markup=feedback_markup
                    )
                    return

                # Определяем тип медиа и отправляем через PTB
                from telegram import InputFile
                import io

                media_file = InputFile(io.BytesIO(buffer))

                if message.photo:
                    await self.bot.send_photo(
                        chat_id=feed["user_id"],
                        photo=media_file,
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                        reply_markup=feedback_markup
                    )
                elif message.video:
                    await self.bot.send_video(
                        chat_id=feed["user_id"],
                        video=media_file,
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                        reply_markup=feedback_markup
                    )
                elif message.document:
                    # Имя файла
                    file_name = getattr(message.document.attributes[0], 'file_name',
                                        'file') if message.document.attributes else 'file'
                    await self.bot.send_document(
                        chat_id=feed["user_id"],
                        document=media_file,
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                        filename=file_name,
                        reply_markup=feedback_markup
                    )
                elif message.audio:
                    await self.bot.send_audio(
                        chat_id=feed["user_id"],
                        audio=media_file,
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                        reply_markup=feedback_markup
                    )
                elif message.voice:
                    await self.bot.send_voice(
                        chat_id=feed["user_id"],
                        voice=media_file,
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                        reply_markup=feedback_markup
                    )
                elif message.animation:
                    await self.bot.send_animation(
                        chat_id=feed["user_id"],
                        animation=media_file,
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                        reply_markup=feedback_markup
                    )
                else:
                    # Неизвестный тип — как документ
                    await self.bot.send_document(
                        chat_id=feed["user_id"],
                        document=media_file,
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                        reply_markup=feedback_markup
                    )
            else:
                # Текстовый пост
                await self.bot.send_message(
                    chat_id=feed["user_id"],
                    text=caption,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                    reply_markup=feedback_markup,
                )
        except Exception as e:
            logger.warning(f"Не удалось доставить пост пользователю {feed['user_id']}: {e}")
            # Fallback: отправляем текстовую версию
            try:
                await self.bot.send_message(
                    chat_id=feed["user_id"],
                    text=caption,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                    reply_markup=feedback_markup,
                )
            except Exception as e2:
                logger.error(f"Fallback тоже не сработал: {e2}")
