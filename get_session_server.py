import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from config import API_ID, API_HASH

async def main():
    print("🔐 Получение строки сессии Telethon на сервере...")
    
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    
    await client.connect()
    
    if await client.is_user_authorized():
        print("✅ Уже авторизован!")
    else:
        phone = input("Введи номер телефона (с +, например +79991112233): ").strip()
        await client.send_code_request(phone)
        
        code = input("Код из Telegram: ").strip()
        
        try:
            await client.sign_in(phone, code)
            print("✅ Вход без 2FA")
        except SessionPasswordNeededError:
            password = input("Пароль 2FA: ").strip()
            await client.sign_in(password=password)
            print("✅ Вход с 2FA успешен")

    # ПРОВЕРКА: убедимся, что авторизация полная
    me = await client.get_me()
    print(f"✅ Авторизован как: {me.first_name} (@{me.username}), id={me.id}")
    
    # Ждём немного, чтобы сессия полностью сохранилась
    await asyncio.sleep(2)
    
    session_string = client.session.save()
    print(f"✅ Длина строки сессии: {len(session_string)}")
    
    print("\n" + "="*60)
    print("✅ СТРОКА СЕССИИ:")
    print(session_string)
    print("="*60)
    print(f'\nДобавь в .env:\nTELETHON_SESSION="{session_string}"')

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())