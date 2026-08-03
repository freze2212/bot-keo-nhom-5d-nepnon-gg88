"""Kiểm tra số tin nhắn nguồn trên tài khoản bot."""
import asyncio
import os
import sys
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import (
    PhoneCodeEmptyError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

load_dotenv()

SOURCES = ['house4179']
phone = (os.getenv('PHONE') or '').strip().replace(' ', '')
phone_digits = ''.join(c for c in phone if c.isdigit())
SESSION_NAME = f'user_session_{phone_digits}' if phone_digits else 'user_session'
client = None


def get_client():
    if client is None:
        raise RuntimeError('Telegram client chua duoc khoi tao')
    return client


async def login_client():
    telegram_client = get_client()
    if not telegram_client.is_connected():
        print('[INFO] Dang mo ket noi toi Telegram...')
        await asyncio.wait_for(telegram_client.connect(), timeout=30)
        print('[INFO] Da mo ket noi toi Telegram')
    else:
        print('[INFO] Telegram client da connected san')

    print('[INFO] Dang kiem tra trang thai dang nhap...')
    if await asyncio.wait_for(telegram_client.is_user_authorized(), timeout=30):
        print('[INFO] Session da dang nhap san, bo qua buoc OTP')
        return
    print('[INFO] Session chua dang nhap, se gui ma OTP')

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        print(f'[INFO] Dang gui yeu cau OTP lan {attempt}/{max_attempts}...')
        sent_code = await asyncio.wait_for(telegram_client.send_code_request(phone), timeout=60)
        print('[INFO] Da gui OTP. Kiem tra Telegram/SMS va nhap ma moi nhat.')
        code = input('Please enter the code you received: ').strip()

        try:
            await telegram_client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=sent_code.phone_code_hash,
            )
            return
        except SessionPasswordNeededError:
            password = input('Please enter your 2FA password: ').strip()
            await telegram_client.sign_in(password=password)
            return
        except PhoneCodeExpiredError:
            print(f"[WARN] Ma OTP da het han. Dang xin ma moi ({attempt}/{max_attempts})...")
        except (PhoneCodeInvalidError, PhoneCodeEmptyError):
            print(f"[WARN] Ma OTP khong hop le. Hay nhap dung ma moi nhat ({attempt}/{max_attempts})...")
        except asyncio.TimeoutError:
            print(f"[WARN] Telegram phan hoi qua lau khi gui/kiem tra OTP ({attempt}/{max_attempts})...")

    raise RuntimeError('Dang nhap that bai sau nhieu lan thu OTP. Hay chay lai lenh va nhap ma moi nhat ngay khi nhan duoc.')


async def count_messages(username):
    telegram_client = get_client()
    me = await telegram_client.get_me()
    try:
        user = await telegram_client.get_entity(username)
    except Exception as e:
        print(f"  @{username}: KHONG TIM THAY - {e}")
        return

    messages = []
    async for message in telegram_client.iter_messages(user, limit=100):
        if message.sender_id == me.id:
            messages.append(message)
    messages.sort(key=lambda x: x.id)

    print(f"  @{username}: {len(messages)} tin (can toi thieu 13)")
    for i, msg in enumerate(messages[:15]):
        preview = (msg.text or msg.message or '[media]').replace('\n', ' ')[:60]
        print(f"    [{i}] id={msg.id} | {preview}")
    if len(messages) > 15:
        print(f"    ... va {len(messages) - 15} tin nua")


async def main():
    global client
    if not phone:
        print('[ERROR] PHONE chua cau hinh trong .env')
        return
    client = TelegramClient(SESSION_NAME, int(os.getenv('API_ID')), os.getenv('API_HASH'))
    await login_client()
    me = await client.get_me()
    print(f"Tai khoan: {me.first_name} (@{me.username})")
    print(f"Session: {SESSION_NAME}")
    print("Dem tin do ban gui cho:")
    for src in SOURCES:
        await count_messages(src)


if __name__ == '__main__':
    asyncio.run(main())
