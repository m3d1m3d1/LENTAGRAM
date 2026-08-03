import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from config import API_ID, API_HASH

async def main():
    print("🔐 Авторизация Telethon")
    print("=" * 50)

    phone = input("1. Введи номер телефона (с +, например +79991112233): ").strip()

    client = TelegramClient(
        "lentagram_session",
        API_ID,
        API_HASH,
        proxy=("http", "127.0.0.1", 10808)
    )

    await client.connect()

    if await client.is_user_authorized():
        print("✅ Уже авторизован!")
        await client.disconnect()
        return

    print("2. Отправляю код...")
    await client.send_code_request(phone)

    code = input("3. Введи код из Telegram: ").strip()

    try:
        await client.sign_in(phone, code)
        print("✅ Авторизация завершена (без 2FA)!")
    except SessionPasswordNeededError:
        print("4. Требуется пароль 2FA")
        password = input("   Введи пароль 2FA: ").strip()
        await client.sign_in(password=password)
        print("✅ Авторизация завершена (с 2FA)!")

    print("=" * 50)
    print("Файл сессии создан: lentagram_session.session")
    print("Теперь запускай main.py")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())