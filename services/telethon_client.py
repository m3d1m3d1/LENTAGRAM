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
from services.ai.availability import ai_availability_manager
from services.feed_selector import FeedSelector


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
        self.feed_selector = FeedSelector()
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
        
        channel_id = event.chat.id
        logger.info(f"ПОЛУЧЕНО СООБЩЕНИЕ: channel={channel_id}, is_channel=True")

        # Получаем внутренний ID канала из БД
        channel_db_id = self.channel_service.get_channel_db_id(channel_id)
        if not channel_db_id:
            logger.warning(f"Канал {channel_id} не найден в БД")
            return

        # Находим всех пользователей, у которых есть ленты с этим каналом
        user_ids = self.channel_service.get_users_subscribed_to_channel(channel_db_id)
        logger.info(f"Найдено {len(user_ids)} пользователей, подписанных на канал {channel_id}")

        if not user_ids:
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

        # Обрабатываем для каждого пользователя отдельно
        for user_id in user_ids:
            await self._process_for_user(
                user_id=user_id,
                channel_db_id=channel_db_id,
                channel_name=channel_name,
                post_text=post_text,
                post_link=post_link,
                message=event.message,
            )

    async def _process_for_user(
        self,
        user_id: int,
        channel_db_id: int,
        channel_name: str,
        post_text: str,
        post_link: str,
        message,
    ) -> None:
        """
        Обрабатывает пост для одного пользователя.
        
        1. Находит все ленты пользователя, содержащие этот канал
        2. Проверяет настройки активности лент
        3. Выбирает одну целевую ленту (через FeedSelector)
        4. Выполняет AI-анализ только для выбранной ленты
        5. Отправляет пост один раз
        """
        logger.info(f"Обработка для пользователя {user_id}")
        
        # Получаем все ленты пользователя с этим каналом
        candidate_feeds = self.channel_service.get_user_feeds_for_channel(user_id, channel_db_id)
        logger.info(f"Пользователь {user_id} имеет {len(candidate_feeds)} подходящих лент")
        
        if not candidate_feeds:
            logger.info(f"У пользователя {user_id} нет лент с каналом {channel_db_id}")
            return
        
        # Фильтруем неактивные ленты согласно настройкам пользователя
        user_settings = self.channel_service.get_user_settings(user_id)
        active_id = user_settings["active_feed_id"]
        show_all = user_settings["show_all_feeds"]
        
        filtered_feeds = []
        for feed in candidate_feeds:
            # Если выбрана конкретная лента и это не она — пропускаем
            if not show_all and active_id is not None and active_id != feed["feed_id"]:
                logger.info(f"Лента {feed['name']} не активна для юзера {user_id}, пропускаем")
                continue
            filtered_feeds.append(feed)
        
        if not filtered_feeds:
            logger.info(f"Все ленты пользователя {user_id} отфильтрованы по настройкам активности")
            return
        
        candidate_feeds = filtered_feeds
        
        # Проверяем, был ли уже отправлен этот пост в какую-либо из лент пользователя
        check_message_id = message.id
        already_sent = False
        for feed in candidate_feeds:
            if self.channel_service.is_post_sent(feed["feed_id"], channel_db_id, check_message_id):
                logger.info(f"Пост {check_message_id} уже отправлен в ленту {feed['name']} для пользователя {user_id}")
                already_sent = True
                break
        
        if already_sent:
            return
        
        # Выбираем целевую ленту через FeedSelector
        ai_enabled = any(f.get("ai_filter_enabled", True) for f in candidate_feeds)
        logger.info(f"AI {'включен' if ai_enabled else 'выключен'} для пользователя {user_id}")
        
        selected_feed = await self.feed_selector.choose_feed(
            post_text=post_text,
            candidate_feeds=candidate_feeds,
            ai_enabled=ai_enabled,
        )
        
        if not selected_feed:
            logger.warning(f"Не удалось выбрать ленту для пользователя {user_id}")
            return
        
        logger.info(f"Выбрана лента feed_id={selected_feed['feed_id']} ({selected_feed['name']}) для доставки")
        
        # Сохраняем пост в БД для выбранной ленты
        try:
            post_id = self.channel_service.save_post(
                selected_feed["feed_id"],
                channel_db_id,
                check_message_id,
                post_text
            )
            logger.info(f"POST SAVED id={post_id}")
            
            if post_id is None:
                logger.warning(f"Не удалось сохранить пост для пользователя {user_id}")
                return
                
        except Exception as e:
            logger.error(f"Ошибка сохранения поста: {e}", exc_info=True)
            return
        
        # Выполняем AI-анализ только если он включен для выбранной ленты
        analysis = None
        if selected_feed.get("ai_filter_enabled", True):
            try:
                analysis = await self.ai_analyzer.analyze_post(
                    post_text,
                    selected_feed.get("topic")
                )
                logger.info(f"AI анализ завершен: relevant={analysis.get('relevant', True)}, category={analysis.get('category')}")
                
            except Exception as e:
                logger.error(f"AI analysis failed; post will not be published via fake fallback: {e}")
                await self._start_ai_degradation(ai_availability_manager.get_state().disabled_reason or "provider_error")
                return
            
            # AI сказал не показывать — пропускаем
            if not analysis.get("relevant", True):
                logger.info(f"Пост отфильтрован AI: {analysis.get('filter_reason', 'нет причины')}")
                try:
                    self.channel_service.save_ai_analysis(post_id, analysis)
                except Exception as e:
                    logger.error(f"Ошибка сохранения AI (отфильтрован): {e}")
                ai_availability_manager.record_rejected_post()
                return
            
            # Сохраняем AI-анализ
            try:
                self.channel_service.save_ai_analysis(post_id, analysis)
            except Exception as e:
                logger.error(f"Ошибка сохранения AI-анализа: {e}")
                # Не прерываем отправку из-за ошибки БД
        
        # Отправляем пост пользователю (один вызов)
        await self._deliver_to_user(
            selected_feed,
            channel_name,
            post_text,
            post_link,
            message,
            channel_db_id,
            analysis,
            post_id
        )
        
        logger.info(f"Сообщение успешно доставлено пользователю {user_id}")

    async def _start_ai_degradation(self, reason: str) -> None:
        """Disable AI filters temporarily and notify affected users once per incident."""
        affected_user_ids = self.channel_service.temporarily_disable_ai_filters()
        if not affected_user_ids:
            return

        reason_text = {
            "quota_exceeded": "дневной лимит AI обработки исчерпан",
            "provider_error": "AI-провайдеры временно недоступны",
            "timeout": "AI-провайдеры не отвечают вовремя",
            "unknown": "неизвестная ошибка AI-сервиса",
        }.get(reason, "неизвестная ошибка AI-сервиса")
        message = (
            "⚠️ AI-фильтрация временно отключена.\n\n"
            f"Причина: {reason_text}.\n\n"
            "Чтобы продолжать получать новости:\n"
            "• отключите AI-фильтр вручную в настройках ленты\n\n"
            "💎 В будущем дополнительные AI-лимиты будут доступны в Premium-подписке."
        )
        from services.database import get_connection
        with get_connection() as conn:
            row = conn.execute("SELECT notification_sent_at FROM ai_availability WHERE id = 1").fetchone()
            if row and row["notification_sent_at"]:
                return
            conn.execute("UPDATE ai_availability SET notification_sent_at = CURRENT_TIMESTAMP WHERE id = 1")
            conn.commit()

        for user_id in affected_user_ids:
            try:
                await self.bot.send_message(chat_id=user_id, text=message)
            except Exception as e:
                logger.warning("Failed to send AI outage notification to %s: %s", user_id, e)

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
                f"⭐ Важность: {ai_analysis.get('importance', '?')}\n\n"
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
