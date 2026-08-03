import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import socket

original_getaddrinfo = socket.getaddrinfo

def getaddrinfo_ipv4(*args, **kwargs):
    return [
        x for x in original_getaddrinfo(*args, **kwargs)
        if x[0] == socket.AF_INET
    ]

socket.getaddrinfo = getaddrinfo_ipv4


import asyncio
import logging
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from config import TELEGRAM_BOT_TOKEN
from services.database import init_db
from services.telethon_client import TelethonManager
from handlers import commands
from handlers import feeds
from handlers import channels
from handlers.feeds import (
    create_feed_start,
    get_feed_name,
    get_feed_filter,
    choose_filter,
    cancel_feed_creation,
    GET_FEED_NAME,
    GET_FEED_FILTER
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logging.getLogger("telegram.ext").setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)

# ConversationHandler ДОЛЖЕН быть глобальным, иначе состояние ломается
create_feed_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(feeds.create_feed_start, pattern="^create_feed$"),
    ],
    states={
        GET_FEED_NAME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, feeds.get_feed_name),
        ],
        GET_FEED_FILTER: [
            # пользователь выбрал 1/2/3/свой вариант
            CallbackQueryHandler(
                feeds.choose_filter,
                pattern="^choose_filter_"
            ),

            # пользователь написал свой фильтр
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                feeds.get_feed_filter
            )
        ],
    },
    fallbacks=[
        CallbackQueryHandler(feeds.cancel_feed_creation, pattern="^cancel_feed_creation$"),
    ],
#    per_message=True,
)
edit_filter_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(feeds.edit_filter_prompt, pattern=r"^edit_filter_\d+$"),
    ],
    states={
        feeds.GET_EDITED_FILTER: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, feeds.save_edited_filter),
        ],
    },
    fallbacks=[
        CallbackQueryHandler(feeds.cancel_edit_filter, pattern="^cancel_edit_filter$"),
    ],
)
add_channel_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(channels.add_channel_prompt, pattern=r"^add_channel_\d+$"),
        CallbackQueryHandler(channels.manual_add_prompt, pattern=r"^manual_add_\d+$"),
        CallbackQueryHandler(channels.search_channels_prompt, pattern=r"^search_channels_\d+$"),
        CallbackQueryHandler(channels.add_found_channel, pattern=r"^add_found_channel_\d+_.+$"),
    ],
    states={
        channels.GET_CHANNEL_INPUT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, channels.process_channel_input),
            CallbackQueryHandler(channels.add_more_channels, pattern="^add_more_channels$"),
            CallbackQueryHandler(channels.finish_adding, pattern="^finish_adding$"),
            CallbackQueryHandler(channels.search_channels_prompt, pattern=r"^search_channels_\d+$"),
        ],
        channels.SEARCH_CHANNELS: [  # НОВОЕ СОСТОЯНИЕ
            MessageHandler(filters.TEXT & ~filters.COMMAND, channels.process_search_results),
            CallbackQueryHandler(channels.search_channels_prompt, pattern=r"^search_channels_\d+$"),
            CallbackQueryHandler(channels.add_found_channel, pattern=r"^add_found_channel_\d+_.+$"),
        ],
    },
    fallbacks=[
        CallbackQueryHandler(channels.cancel_add_channel, pattern="^cancel_add_channel$"),
        CallbackQueryHandler(channels.add_found_channel, pattern=r"^add_found_channel_\d+_.+$"),
    ],
#    per_message=True,
)


# from telegram.request import HTTPXRequest
async def error_handler(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Глобальный обработчик необработанных исключений в хендлерах."""
    logger.error(
        f"Необработанное исключение при обработке update {update}: {context.error}",
        exc_info=context.error,
    )

def build_application():
    application = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
 #       .request(request)
        .build()
    )
    # ---- простые команды ----
    application.add_handler(CommandHandler("start", commands.start))
    application.add_handler(CommandHandler("help", commands.show_help))
    application.add_handler(CommandHandler("feeds", feeds.list_feeds))
    application.add_handler(CommandHandler("clear", commands.clear_chat_menu))

    # ---- ConversationHandlers (глобальные) ----
    from handlers.channels import suggest_add_to_feed

# ---- глобальный хендлер: ссылка/@username/пост без вызова меню ----
#    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.ChatType.GROUPS,suggest_add_to_feed), group=1)
    application.add_handler(create_feed_conv)
    application.add_handler(add_channel_conv)
    application.add_handler(edit_filter_conv)
    # ---- остальные колбэки ----
    application.add_handler(CallbackQueryHandler(commands.switch_feed_menu, pattern="^switch_feed_menu$"))
    application.add_handler(CallbackQueryHandler(commands.activate_feed, pattern=r"^activate_feed_\d+$"))
    application.add_handler(CallbackQueryHandler(commands.activate_all_feeds, pattern="^activate_all_feeds$"))
    application.add_handler(CallbackQueryHandler(feeds.list_feeds, pattern="^list_feeds$"))
    application.add_handler(CallbackQueryHandler(feeds.delete_feed, pattern=r"^delete_feed_\d+$"))
    application.add_handler(CallbackQueryHandler(feeds.toggle_ai_filter, pattern=r"^toggle_ai_\d+$"))
    application.add_handler(CallbackQueryHandler(channels.view_feed_channels, pattern=r"^channels_\d+$"))
    application.add_handler(CallbackQueryHandler(channels.remove_channel_from_feed, pattern=r"^removechan_"))
    application.add_handler(CallbackQueryHandler(commands.clear_chat_menu, pattern="^clear_chat_menu$"))
    application.add_handler(CallbackQueryHandler(commands.clear_chat, pattern="^clear_chat_today$"))
    application.add_handler(CallbackQueryHandler(commands.clear_chat, pattern="^clear_chat_all$"))
    application.add_handler(CallbackQueryHandler(commands.show_help, pattern="^help$"))
    application.add_handler(CallbackQueryHandler(commands.start, pattern="^back_to_main$"))
    application.add_handler(CallbackQueryHandler(channels.quick_add_to_feed, pattern=r"^quick_add_"))
    application.add_handler(CallbackQueryHandler(channels.handle_feedback, pattern=r"^fb_(like|dislike)_"))
    application.add_error_handler(error_handler)
    return application


async def run() -> None:
    init_db()
    application = build_application()

    telethon_manager = TelethonManager(bot=application.bot)
    application.bot_data["telethon_manager"] = telethon_manager

    await application.initialize()
    await application.start()

    logger.info("=== Application started ===")

    try:
        await telethon_manager.start()

        await application.updater.start_polling(
            drop_pending_updates=True
        )

        logger.info("🚀 Lentagram запущен, бот слушает сообщения")

        await asyncio.Event().wait()

    except (KeyboardInterrupt, SystemExit):
        logger.info("Получен сигнал остановки")

    except Exception as e:
        logger.error(
            f"Ошибка в run(): {e}",
            exc_info=True
        )

    finally:
        logger.info("Останавливаем бота...")

        try:
            await application.updater.stop()
        except Exception:
            pass

        try:
            await application.stop()
        except Exception:
            pass

        try:
            await application.shutdown()
        except Exception:
            pass

        try:
            await telethon_manager.stop()
            logger.info("Telethon отключён")
        except Exception as e:
            logger.error(
                f"Ошибка остановки Telethon: {e}",
                exc_info=True
            )

        logger.info("👋 Бот остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Остановлено пользователем")
