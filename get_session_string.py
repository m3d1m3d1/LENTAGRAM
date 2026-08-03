import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from config import API_ID, API_HASH


async def main():
    print("🔐 Получение строки сессии Telethon...")
    print("Введи номер телефона (с +, например +79991112233):")

    client = TelegramClient(
        StringSession(),
        API_ID,
        API_HASH,
#        proxy=("http", "127.0.0.1", 10808)
    )

    await client.connect()

    if await client.is_user_authorized():
        print("✅ Уже авторизован!")
    else:
        phone = input("Телефон: ").strip()
        await client.send_code_request(phone)

        code = input("Код из Telegram: ").strip()

        try:
            await client.sign_in(phone, code)
            print("✅ Вход без 2FA")
        except SessionPasswordNeededError:
            print("⚠️ Требуется пароль 2FA")
            password = input("Пароль 2FA (ввод видимый): ").strip()
            await client.sign_in(password=password)
            print("✅ Вход с 2FA успешен")

    session_string = client.session.save()

    print("\n" + "=" * 60)
    print("✅ СТРОКА СЕССИИ:")
    print(session_string)
    print("=" * 60)
    print("\nДобавь в .env на сервере:")
    print(f'TELETHON_SESSION="{session_string}"')

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())