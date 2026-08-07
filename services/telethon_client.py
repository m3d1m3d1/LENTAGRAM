import asyncio
import io
import logging
from typing import Optional

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telegram.constants import ParseMode
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
    InputMediaPhoto,
    InputMediaVideo,
    InputMediaDocument,
    InputMediaAudio,
)

from config import API_ID, API_HASH, TELETHON_SESSION
from services.channel_service import ChannelService
from services.ai.analyzer import AIAnalyzer
from services.ai.availability import ai_availability_manager
from services.feed_selector import FeedSelector


logger = logging.getLogger(__name__)


_client: Optional[TelegramClient] = None


def _get_client() -> TelegramClient:
    """
    Singleton Telethon client.
    Один процесс = один TelegramClient.
    """
    global _client

    if _client is None:
        if TELETHON_SESSION:
            session = StringSession(TELETHON_SESSION)
            logger.info(
                "Creating Telethon StringSession client"
            )
        else:
            session = "lentagram_session"
            logger.info(
                "Creating Telethon file session client"
            )

        _client = TelegramClient(
            session,
            API_ID,
            API_HASH,
        )

    return _client


async def _ensure_connected(
    client: TelegramClient
) -> None:
    """
    Гарантирует подключение перед RPC.
    """
    if not client.is_connected():
        logger.warning(
            "Telethon disconnected, reconnecting..."
        )
        await client.connect()


def reset_client():
    """
    Сброс singleton клиента.
    """
    global _client

    if _client:
        _client = None
        logger.info(
            "Telethon client reset"
        )


class TelethonManager:

    def __init__(self, bot):
        self.bot = bot

        self.channel_service = ChannelService()
        self.ai_analyzer = AIAnalyzer()
        self.feed_selector = FeedSelector()

        self._started = False
        self._runner_task = None


    async def start(self) -> None:
        """
        Запуск Telethon клиента.
        """

        client = _get_client()

        logger.info(
            "Starting Telethon..."
        )

        try:
            await client.connect()

            if not await client.is_user_authorized():
                logger.error(
                    "Telethon user is not authorized"
                )

                await client.disconnect()
                return


            me = await client.get_me()

            logger.info(
                f"Logged in as "
                f"{me.first_name} "
                f"(@{me.username})"
            )


            client.add_event_handler(
                self._on_new_message,
                events.NewMessage()
            )


            self._runner_task = asyncio.create_task(
                client.run_until_disconnected()
            )


            self._started = True


            logger.info(
                "✅ Telethon started"
            )


        except Exception:
            logger.exception(
                "Telethon start failed"
            )

            await client.disconnect()



    async def stop(self):

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


        logger.info(
            "Telethon stopped"
        )


    def is_started(self):
        return self._started



    async def refresh_handlers(self):

        if not self._started:
            logger.warning(
                "Telethon not started"
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
            "Telethon handlers refreshed"
        )



    async def join_channel(
        self,
        username: str
    ) -> tuple[bool, str]:
        """
        Проверяет доступность канала.
        НЕ подписывает аккаунт.
        """

        try:
            client = _get_client()

            await _ensure_connected(
                client
            )

            entity = await client.get_entity(
                username
            )


            if not getattr(
                entity,
                "broadcast",
                False
            ):
                return False, "Это не Telegram канал"


            return True, entity.title or username


        except Exception as e:

            logger.error(
                f"Channel check failed: {e}"
            )

            return False, "Нет доступа"
    async def _on_new_message(
        self,
        event: events.NewMessage.Event
    ) -> None:

        if not event.chat:
            return


        if not event.is_channel:
            return


        channel_id = event.chat.id

        logger.info(
            f"New channel message: {channel_id}"
        )


        channel_db_id = (
            self.channel_service
            .get_channel_db_id(channel_id)
        )


        if not channel_db_id:
            logger.debug(
                f"Channel {channel_id} not registered"
            )
            return



        user_ids = (
            self.channel_service
            .get_users_subscribed_to_channel(
                channel_id
            )
        )


        if not user_ids:
            return



        username = getattr(
            event.chat,
            "username",
            None
        )


        if username:
            post_link = (
                f"https://t.me/"
                f"{username}/"
                f"{event.message.id}"
            )

            channel_name = username

        else:
            post_link = (
                f"https://t.me/c/"
                f"{str(channel_id)[4:]}/"
                f"{event.message.id}"
            )

            channel_name = (
                f"channel_{channel_id}"
            )



        post_text = (
            event.message.message
            or event.message.text
            or ""
        )

        grouped_id = getattr(event.message, "grouped_id", None)

        if grouped_id:
            logger.info(
                f"Album message detected: {grouped_id}"
            )

        for user_id in user_ids:

            try:

                await self._process_for_user(
                    user_id=user_id,
                    channel_db_id=channel_db_id,
                    channel_name=channel_name,
                    post_text=post_text,
                    post_link=post_link,
                    message=event.message,
                )


            except Exception:

                logger.exception(
                    f"Failed processing "
                    f"message for user {user_id}"
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


        logger.info(
            f"Processing post for user {user_id}"
        )



        candidate_feeds = (
            self.channel_service
            .get_user_feeds_for_channel(
                user_id,
                channel_db_id
            )
        )


        if not candidate_feeds:

            return



        user_settings = (
            self.channel_service
            .get_user_settings(user_id)
        )


        active_id = (
            user_settings
            .get("active_feed_id")
        )

        show_all = bool(
            int(
                user_settings
                    .get("show_all_feeds", 1
                )
            )
        )


        filtered_feeds = []


        for feed in candidate_feeds:

            if (
                not show_all
                and active_id
                and feed["feed_id"] != active_id
            ):
                continue


            filtered_feeds.append(feed)



        if not filtered_feeds:

            return



        candidate_feeds = filtered_feeds



        already_sent = False


        for feed in candidate_feeds:

            if self.channel_service.is_post_sent(
                feed["feed_id"],
                channel_db_id,
                message.id
            ):

                already_sent = True
                break



        if already_sent:

            logger.info(
                "Post already delivered"
            )

            return




        ai_enabled = any(
            feed.get(
                "ai_filter_enabled",
                True
            )
            for feed in candidate_feeds
        )



        selected_feed = await (
            self.feed_selector
            .choose_feed(
                post_text=post_text,
                candidate_feeds=candidate_feeds,
                ai_enabled=ai_enabled,
            )
        )



        if not selected_feed:

            logger.info(
                "No suitable feed selected"
            )

            return



        logger.info(
            f"Selected feed "
            f"{selected_feed['name']}"
        )



        post_id = (
            self.channel_service.save_post(
                selected_feed["feed_id"],
                channel_db_id,
                message.id,
                post_text,
            )
        )


        if not post_id:

            return



        analysis = None



        if selected_feed.get(
            "ai_filter_enabled",
            True
        ):

            try:

                analysis = (
                    await self.ai_analyzer
                    .analyze_post(
                        post_text,
                        selected_feed.get(
                            "topic"
                        )
                    )
                )



                logger.info(
                    "AI analysis complete: "
                    f"{analysis}"
                )



            except Exception as e:

                logger.error(
                    f"AI analysis failed: {e}"
                )


                await self._start_ai_degradation(
                    ai_availability_manager
                    .get_state()
                    .disabled_reason
                    or "provider_error"
                )


                return




            if not analysis.get(
                "relevant",
                True
            ):

                logger.info(
                    "Post rejected by AI"
                )


                try:

                    self.channel_service.save_ai_analysis(
                        post_id,
                        analysis
                    )

                except Exception:

                    logger.exception(
                        "Failed saving AI analysis"
                    )


                ai_availability_manager.record_rejected_post()

                return



            try:

                self.channel_service.save_ai_analysis(
                    post_id,
                    analysis
                )

            except Exception:

                logger.exception(
                    "Failed saving AI analysis"
                )



        await self._deliver_to_user(
            selected_feed,
            channel_name,
            post_text,
            post_link,
            message,
            channel_db_id,
            analysis,
            post_id,
        )



        logger.info(
            f"Delivered post "
            f"to user {user_id}"
        )
    async def _start_ai_degradation(
        self,
        reason: str
    ) -> None:
        """
        Временно отключает AI-фильтры
        и уведомляет пользователей.
        """


        affected_users = (
            self.channel_service
            .temporarily_disable_ai_filters()
        )


        if not affected_users:
            return



        reason_text = {
            "quota_exceeded":
                "дневной лимит AI исчерпан",

            "provider_error":
                "AI-провайдер временно недоступен",

            "timeout":
                "AI не отвечает вовремя",

        }.get(
            reason,
            "неизвестная ошибка AI"
        )



        text = (
            "⚠️ AI-фильтрация временно отключена.\n\n"
            f"Причина: {reason_text}\n\n"
            "Новости продолжают поступать без AI-фильтра."
        )



        for user_id in affected_users:

            try:

                await self.bot.send_message(
                    chat_id=user_id,
                    text=text,
                )


            except Exception as e:

                logger.warning(
                    f"Failed AI notification "
                    f"for {user_id}: {e}"
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
        Отправка новости пользователю.
        Поддерживает:
        - текст
        - фото
        - видео
        - документы
        - feedback кнопки
        """


        feedback_markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "❤️ Полезно",
                        callback_data=f"fb_like_{post_id}"
                    ),

                    InlineKeyboardButton(
                        "👎 Неинтересно",
                        callback_data=f"fb_dislike_{post_id}"
                    )
                ]
            ]
        )



        safe_text = (
            post_text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )


        preview = (
            safe_text[:700]
            +
            ("…" if len(safe_text) > 700 else "")
        )



        ai_block = ""


        if ai_analysis:

            ai_block = (
                "🤖 "
                f"{ai_analysis.get('category', '')}\n"
                "⭐ "
                f"Важность: "
                f"{ai_analysis.get('importance', '?')}\n\n"
            )



        caption = (
            f"📬 Лента «{feed['name']}»\n\n"
            f"{ai_block}"
            f"{preview}\n\n"
            f'<a href="{post_link}">'
            "🔗 Открыть оригинал"
            "</a>"
        )



        if len(caption) > 4096:

            caption = caption[:4093] + "..."



        try:

            client = _get_client()

            await _ensure_connected(
                client
            )



            if message.media:

                buffer = await client.download_media(
                    message.media,
                    bytes
                )


                if buffer:

                    media_file = InputFile(
                        io.BytesIO(buffer)
                    )


                    if message.photo:

                        await self.bot.send_photo(
                            chat_id=feed["user_id"],
                            photo=media_file,
                            caption=caption,
                            parse_mode=ParseMode.HTML,
                            reply_markup=feedback_markup,
                        )


                    elif message.video:

                        await self.bot.send_video(
                            chat_id=feed["user_id"],
                            video=media_file,
                            caption=caption,
                            parse_mode=ParseMode.HTML,
                            reply_markup=feedback_markup,
                        )


                    elif message.document:

                        await self.bot.send_document(
                            chat_id=feed["user_id"],
                            document=media_file,
                            caption=caption,
                            parse_mode=ParseMode.HTML,
                            reply_markup=feedback_markup,
                        )


                    elif message.audio:

                        await self.bot.send_audio(
                            chat_id=feed["user_id"],
                            audio=media_file,
                            caption=caption,
                            parse_mode=ParseMode.HTML,
                            reply_markup=feedback_markup,
                        )


                    else:

                        await self.bot.send_document(
                            chat_id=feed["user_id"],
                            document=media_file,
                            caption=caption,
                            parse_mode=ParseMode.HTML,
                            reply_markup=feedback_markup,
                        )


                    return




            await self.bot.send_message(
                chat_id=feed["user_id"],
                text=caption,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=feedback_markup,
            )



        except Exception as e:

            logger.error(
                f"Delivery failed: {e}",
                exc_info=True
            )


            try:

                await self.bot.send_message(
                    chat_id=feed["user_id"],
                    text=caption,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )


            except Exception:

                logger.exception(
                    "Fallback delivery failed"
                )
