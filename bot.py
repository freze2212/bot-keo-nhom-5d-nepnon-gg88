import os
import sys
import json
import re
import sqlite3
import schedule
import time
import random
import atexit
import ctypes
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import asyncio
import threading
from telethon import TelegramClient
from telethon.errors import (
    PasswordHashInvalidError,
    PhoneCodeEmptyError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)
from telethon.tl.types import InputPeerChannel, InputPeerChat, Channel, Chat

# Windows terminal: tranh crash khi in tieng Viet
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Load environment variables
load_dotenv()


def log(msg):
    print(msg, flush=True)

LOCK_FILE = 'bot.lock'


def is_process_running(pid):
    if pid <= 0:
        return False
    if sys.platform == 'win32':
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def ensure_single_instance():
    """Chi cho phep 1 bot.py chay cung luc (tranh database is locked)."""
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, encoding='utf-8') as f:
                old_pid = int(f.read().strip())
            if is_process_running(old_pid):
                log(f"[ERROR] Bot da chay o PID {old_pid}. Tat bot cu (Ctrl+C) roi chay lai.")
                sys.exit(1)
        except (ValueError, OSError):
            pass
    with open(LOCK_FILE, 'w', encoding='utf-8') as f:
        f.write(str(os.getpid()))


def release_lock():
    try:
        os.remove(LOCK_FILE)
    except OSError:
        pass


def configure_sqlite_session(telegram_client):
    session = telegram_client.session
    if hasattr(session, '_cursor'):
        session._cursor()
        if getattr(session, '_conn', None):
            session._conn.execute('PRAGMA busy_timeout=30000')


async def run_session_with_retry(telegram_client, group_entity, max_retries=5):
    for attempt in range(max_retries):
        try:
            await daily_schedule(telegram_client, group_entity)
            return
        except sqlite3.OperationalError as e:
            if 'locked' in str(e).lower() and attempt < max_retries - 1:
                wait = 2 * (attempt + 1)
                log(f"[WARN] Session bi khoa, thu lai sau {wait}s... ({attempt + 1}/{max_retries})")
                await asyncio.sleep(wait)
            else:
                raise

# Data structure to store posts
POSTS_FILE = 'posts.json'

# Image directories
FIXED_IMAGES_DIR = 'images/fixed'
WINCAI_IMAGES_DIR = 'images/wincai'
LOSECAI_IMAGES_DIR = 'images/losecai'
WINCON_IMAGES_DIR = 'images/wincon'
LOSECON_IMAGES_DIR = 'images/losecon'
TIE_IMAGES_DIR = 'images/tie'

RESULT_IMAGE_DIRS = {
    'wincai': WINCAI_IMAGES_DIR,
    'losecai': LOSECAI_IMAGES_DIR,
    'wincon': WINCON_IMAGES_DIR,
    'losecon': LOSECON_IMAGES_DIR,
    'tie': TIE_IMAGES_DIR,
}
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.gif')
RESULT_TIME_SLOT = '11:00'

# Result probabilities
WIN_PROBABILITY = 0.70  # 70%
LOSE_PROBABILITY = 0.30  # 30%

sent_slots = set()
BEFORE_BET_ORDER = [0, 1, 2, 3, 4, 5, 6]  # Index 0-6 (tin 1-7)
RESULT_SEQUENCE_REPEAT = 3                 # Hô 3 lệnh trong 1 round
MIN_MESSAGES = 14                          # Tối thiểu 14 tin nhắn trong danh sách nguồn

TZ = timezone(timedelta(hours=7))  # GMT+7 (Việt Nam)
SCHEDULE_INTERVAL = 15
SCHEDULE_START_HOUR, SCHEDULE_START_MINUTE = 12, 15
SCHEDULE_END_HOUR, SCHEDULE_END_MINUTE = 0, 0

raw_api_id = (os.getenv('API_ID') or '').strip()
if raw_api_id and raw_api_id.isdigit():
    api_id = int(raw_api_id)
else:
    api_id = 0  # Se duoc kiem tra khi connect telegram

api_hash = (os.getenv('API_HASH') or '').strip()
phone = (os.getenv('PHONE') or '').strip().replace(' ', '')
twofa_password = (
    os.getenv('TELEGRAM_2FA_PASSWORD')
    or os.getenv('TELEGRAM_PASSWORD')
    or os.getenv('TWO_FA_PASSWORD')
    or ''
).strip()

def session_name_from_phone(phone_number):
    digits = ''.join(c for c in (phone_number or '') if c.isdigit())
    return f'user_session_{digits}' if digits else 'user_session'

SESSION_NAME = session_name_from_phone(phone)

# ID hoặc username nhóm (có thể là @tennhom hoặc ID số)
group = os.getenv('GROUP')
source_username = (os.getenv('SOURCE_USERNAME') or 'house4179').strip() or 'house4179'
log(f"GROUP tu .env: {group}")
log(f"Session: {SESSION_NAME} | PHONE tu .env: {phone}")
log(f"SOURCE_USERNAME tu .env/fallback: {source_username}")

client = None


def get_client():
    if client is None:
        raise RuntimeError('Telegram client chua duoc khoi tao')
    return client


def parse_group_values(group_value):
    raw_value = (group_value or '').strip()
    if not raw_value:
        return []

    group_values = []
    seen = set()
    for item in re.split(r'[\n,;]+', raw_value):
        candidate = item.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        group_values.append(candidate)
    return group_values


def build_group_candidates(group_value):
    raw_value = (group_value or '').strip()
    if not raw_value:
        return []

    candidates = [raw_value]
    try:
        numeric_value = int(raw_value)
    except ValueError:
        return candidates

    candidates.append(numeric_value)

    if numeric_value > 0:
        candidates.append(int(f'-100{numeric_value}'))
        candidates.append(-numeric_value)
    elif raw_value.startswith('-100'):
        candidates.append(int(raw_value[4:]))
    else:
        candidates.append(int(f'-100{abs(numeric_value)}'))

    unique_candidates = []
    seen = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append(candidate)
    return unique_candidates


async def resolve_group_entity(group_value):
    telegram_client = get_client()
    candidates = build_group_candidates(group_value)
    if not candidates:
        raise ValueError('GROUP chua duoc cau hinh trong .env')

    candidate_ids = {candidate for candidate in candidates if isinstance(candidate, int)}
    normalized_usernames = {
        candidate.lower().lstrip('@').replace('https://t.me/', '').replace('http://t.me/', '').rstrip('/')
        for candidate in candidates
        if isinstance(candidate, str) and not candidate.lstrip('-').isdigit()
    }

    # 1. Duyệt qua tất cả các dialogs đã tham gia để tìm khớp ID hoặc username
    async for dialog in telegram_client.iter_dialogs():
        entity_id = getattr(dialog.entity, 'id', None)
        dialog_ids = {dialog.id}
        if entity_id:
            dialog_ids.add(entity_id)
            dialog_ids.add(-entity_id)
            try:
                dialog_ids.add(int(f'-100{entity_id}'))
            except Exception:
                pass

        username = (getattr(dialog.entity, 'username', None) or '').lower()
        if candidate_ids.intersection(dialog_ids):
            return dialog.entity
        if username and username in normalized_usernames:
            return dialog.entity

    # 2. Fallback thử với get_entity trực tiếp
    last_error = None
    for candidate in candidates:
        try:
            return await telegram_client.get_entity(candidate)
        except Exception as exc:
            last_error = exc

    raise RuntimeError(
        f'Khong tim thay entity cho GROUP={group_value}. '
        f'Hay dung @username hoac ID -100..., va dam bao account da join nhom. '
        f'Loi goc: {last_error}'
    )


async def resolve_group_entities(group_value):
    group_values = parse_group_values(group_value)
    if not group_values:
        raise ValueError('GROUP chua duoc cau hinh trong .env')

    entities = []
    seen_ids = set()
    for value in group_values:
        entity = await resolve_group_entity(value)
        entity_id = getattr(entity, 'id', None)
        dedupe_key = entity_id if entity_id is not None else value
        if dedupe_key in seen_ids:
            continue
        seen_ids.add(dedupe_key)
        entities.append(entity)
    return entities


async def login_client():
    if not phone:
        log('[ERROR] PHONE chua cau hinh trong .env')
        sys.exit(1)
    telegram_client = get_client()
    if not telegram_client.is_connected():
        log('[INFO] Dang mo ket noi toi Telegram...')
        await asyncio.wait_for(telegram_client.connect(), timeout=30)
        log('[INFO] Da mo ket noi toi Telegram')
    else:
        log('[INFO] Telegram client da connected san')

    log('[INFO] Dang kiem tra trang thai dang nhap...')
    if await asyncio.wait_for(telegram_client.is_user_authorized(), timeout=30):
        log('[INFO] Session da dang nhap san, bo qua buoc OTP')
        return
    log('[INFO] Session chua dang nhap, se gui ma OTP')

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        log(f'[INFO] Dang gui yeu cau OTP lan {attempt}/{max_attempts}...')
        sent_code = await asyncio.wait_for(telegram_client.send_code_request(phone), timeout=60)
        log('[INFO] Da gui OTP. Kiem tra Telegram/SMS va nhap ma moi nhat.')
        code = input('Please enter the code you received: ').strip()

        try:
            await telegram_client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=sent_code.phone_code_hash,
            )
            return
        except SessionPasswordNeededError:
            log('[INFO] Tai khoan da bat 2FA, can nhap mat khau xac minh 2 buoc.')
            password_attempts = [twofa_password] if twofa_password else []
            max_password_attempts = 3

            for password_attempt in range(1, max_password_attempts + 1):
                if password_attempt > len(password_attempts):
                    password_attempts.append(
                        input('Please enter your 2FA password: ').strip()
                    )

                password = password_attempts[password_attempt - 1]
                try:
                    await telegram_client.sign_in(password=password)
                    return
                except PasswordHashInvalidError:
                    log(
                        f'[WARN] Mat khau 2FA khong dung '
                        f'({password_attempt}/{max_password_attempts}).'
                    )

            raise RuntimeError(
                'Mat khau 2FA khong hop le sau nhieu lan thu. '
                'Hay kiem tra lai mat khau Telegram hoac cau hinh '
                'TELEGRAM_2FA_PASSWORD trong .env.'
            )
        except PhoneCodeExpiredError:
            log(f'[WARN] Ma OTP da het han. Dang xin ma moi ({attempt}/{max_attempts})...')
        except (PhoneCodeInvalidError, PhoneCodeEmptyError):
            log(f'[WARN] Ma OTP khong hop le. Hay nhap dung ma moi nhat ({attempt}/{max_attempts})...')
        except asyncio.TimeoutError:
            log(f'[WARN] Telegram phan hoi qua lau khi gui/kiem tra OTP ({attempt}/{max_attempts})...')

    raise RuntimeError('Dang nhap that bai sau nhieu lan thu OTP. Hay chay lai bot va nhap ma moi nhat ngay khi nhan duoc.')

def ensure_directories():
    """Create necessary directories if they don't exist"""
    directories = [
        FIXED_IMAGES_DIR,
        WINCAI_IMAGES_DIR,
        LOSECAI_IMAGES_DIR,
        WINCON_IMAGES_DIR,
        LOSECON_IMAGES_DIR,
        TIE_IMAGES_DIR
    ]
    for directory in directories:
        os.makedirs(directory, exist_ok=True)

def load_posts():
    """Load posts from JSON file"""
    if os.path.exists(POSTS_FILE):
        with open(POSTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        'fixed_posts': {},  # Key: time (HH:MM), Value: list of posts
        'rotating_posts': {
            'wincai': {},  # Key: time (HH:MM), Value: list of posts
            'losecai': {},  # Key: time (HH:MM), Value: list of posts
            'wincon': {},  # Key: time (HH:MM), Value: list of posts
            'losecon': {},  # Key: time (HH:MM), Value: list of posts
            'tie': {}      # Key: time (HH:MM), Value: list of posts
        }
    }

def save_posts(posts):
    """Save posts to JSON file"""
    with open(POSTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(posts, f, ensure_ascii=False, indent=4)

def get_next_rotating_post_index(time_slot, result_type):
    """Get the index of the next rotating post to send for a specific time slot and result type"""
    posts = load_posts()
    if not posts['rotating_posts'][result_type].get(time_slot):
        return 0
    
    rotating_posts = posts['rotating_posts'][result_type][time_slot]
    if not rotating_posts:
        return 0
    
    # Get the last sent post index
    last_index = rotating_posts[-1].get('last_sent_index', -1)
    next_index = (last_index + 1) % len(rotating_posts)
    
    # Update the last sent index
    rotating_posts[-1]['last_sent_index'] = next_index
    posts['rotating_posts'][result_type][time_slot] = rotating_posts
    save_posts(posts)
    
    return next_index

def detect_bet_side(text):
    text_upper = (text or '').upper()
    if 'CÁI' in text_upper or 'CAI' in text_upper or 'NHÀ CÁI' in text_upper:
        return 'cai'
    if 'CON' in text_upper or 'NHÀ CON' in text_upper:
        return 'con'
    return 'con'

def list_images_in_dir(dir_path):
    if not os.path.exists(dir_path):
        return []
    files = []
    for name in sorted(os.listdir(dir_path)):
        if name.startswith('.'):
            continue
        if os.path.splitext(name)[1].lower() in IMAGE_EXTENSIONS:
            files.append(os.path.join(dir_path, name))
    return files

def get_result_image_path(result_type):
    """Lấy ảnh kết quả từ posts.json, fallback chọn ngẫu nhiên từ thư mục images/."""
    posts = load_posts()
    rotating_posts = posts['rotating_posts'][result_type].get(RESULT_TIME_SLOT, [])
    if rotating_posts:
        next_index = get_next_rotating_post_index(RESULT_TIME_SLOT, result_type)
        path = rotating_posts[next_index]['image_path']
        if os.path.exists(path):
            return path
        print(f"[WARN] Ảnh trong posts.json không tồn tại: {path}")

    images = list_images_in_dir(RESULT_IMAGE_DIRS[result_type])
    if images:
        return random.choice(images)
    return None

async def send_result_image(group, result_type, caption):
    image_path = get_result_image_path(result_type)
    if image_path:
        await get_client().send_file(group, image_path, caption=caption, parse_mode='markdown')
        print(f"Đã gửi ảnh kết quả: {image_path}")
    else:
        print(f"[WARN] Không có ảnh trong {RESULT_IMAGE_DIRS[result_type]}/")

async def send_message(text):
    """Send a text message to the channel"""
    try:
        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=text
        )
        print(f"Sent message: {text} at {datetime.now()}")
    except Exception as e:
        print(f"Error sending message: {e}")

async def send_photo(image_path, caption=None):
    """Send a photo to the channel"""
    try:
        with open(image_path, 'rb') as photo:
            await bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=photo,
                caption=caption
            )
        print(f"Posted image {image_path} at {datetime.now()}")
    except Exception as e:
        print(f"Error sending photo: {e}")

async def send_video(video_path):
    """Send a video to the channel"""
    try:
        with open(video_path, 'rb') as video:
            await bot.send_video(
                chat_id=CHANNEL_ID,
                video=video
            )
        print(f"Posted video {video_path} at {datetime.now()}")
    except Exception as e:
        print(f"Error sending video: {e}")

async def send_rotating_post(time_slot, result_type, caption=None):
    """Send rotating post for a specific time slot and result type, with optional caption"""
    posts = load_posts()
    rotating_posts = posts['rotating_posts'][result_type].get(time_slot, [])
    
    if not rotating_posts:
        print(f"No rotating posts available for time slot {time_slot} and result type {result_type}")
        return
    
    next_index = get_next_rotating_post_index(time_slot, result_type)
    post = rotating_posts[next_index]
    
    try:
        await send_photo(post['image_path'], caption)
    except Exception as e:
        print(f"Error sending rotating post: {e}")

def get_result_type(choice):
    """Get result type so that 75% là win đúng với bên được hô, còn lại là lose"""
    rand = random.random()
    if rand < 0.75:
        # Win đúng với bên được hô
        if choice == 'NHÀ CÁI 500K':
            return 'wincai'
        else:
            return 'wincon'
    else:
        # Lose (25%)
        if choice == 'NHÀ CÁI 500K':
            return 'losecai'  # Cái hô nhưng Cái thua
        else:
            return 'losecon'  # Con hô nhưng Con thua


def build_result_payload(is_cai, is_win, is_tie):
    """Xác định loại ảnh và caption kết quả cần gửi."""
    if is_tie:
        return 'tie', '**〰️ HÒA + 0%**'

    if is_cai:
        if is_win:
            return 'wincai', '**✅ CÁI THẮNG**'
        return 'losecai', '**❌ CÁI THUA**'

    if is_win:
        return 'wincon', '**✅ CON THẮNG**'
    return 'losecon', '**❌ CON THUA**'

async def get_message_content(username):
    """Lấy nội dung tin nhắn từ cuộc trò chuyện với user"""
    try:
        telegram_client = get_client()
        user = await telegram_client.get_entity(username)
        messages = []
        async for message in telegram_client.iter_messages(user, limit=20):
            if message.text:
                messages.append(message.text)
        return messages
    except Exception as e:
        print(f"Lỗi khi lấy nội dung tin nhắn: {e}")
        return None

async def daily_schedule(client, group):
    try:
        # Kiểm tra kết nối trước khi thực hiện
        if not client.is_connected():
            print("Mất kết nối, đang thử kết nối lại...")
            await client.connect()
            if not await client.is_user_authorized():
                print("Cần đăng nhập lại...")
                await login_client()
        
        # Lấy thông tin user từ username cấu hình, fallback về frezeit
        user = await client.get_entity(source_username)
        print(f"\n=== BẮT ĐẦU GỬI TIN NHẮN THEO LỊCH ===")
        
        # Lấy thông tin tài khoản của bạn
        me = await client.get_me()
        print(f"Tìm tin nhắn từ {me.first_name} trong chat với @{source_username}")
        
        # Mảng để lưu các tin nhắn
        messages_to_send = []
        
        # Lấy các tin nhắn từ cuộc trò chuyện với user (bỏ qua MessageService như ghim tin, đổi ảnh...)
        async for message in client.iter_messages(user, limit=30):
            try:
                if type(message).__name__ == 'MessageService' or getattr(message, 'action', None) is not None:
                    print(f"Bỏ qua tin nhắn hệ thống MessageService ID: {message.id}")
                    continue
                print(f"\nĐã tìm thấy tin nhắn ID: {message.id}")
                print(f"Thời gian gốc: {message.date}")
                messages_to_send.append(message)
            except Exception as e:
                print(f"Lỗi khi xử lý tin nhắn {message.id}: {e}")
                continue
        
        # Sắp xếp tin nhắn theo ID (ID lớn nhất lên đầu)
        messages_to_send.sort(key=lambda x: x.id)
        
        # In ra thứ tự tin nhắn để debug
        print("\nThứ tự tin nhắn sau khi sắp xếp:")
        for i, msg in enumerate(messages_to_send):
            print(f"Index {i}: ID {msg.id} - Thời gian: {msg.date}")
        
        if len(messages_to_send) < MIN_MESSAGES:
            print(
                f"Không đủ tin nhắn để gửi "
                f"(cần ít nhất {MIN_MESSAGES} tin nhắn, hiện có {len(messages_to_send)})"
            )
            return

        async def forward_slot(index, label=None):
            if index >= len(messages_to_send):
                raise IndexError(
                    f"Thiếu tin nhắn cho slot index {index} "
                    f"(chi co {len(messages_to_send)} tin nhan)"
                )
            await client.forward_messages(
                group,
                messages_to_send[index],
                silent=True,
                drop_author=True,
            )
            print(label or f"Đã gửi tin nhắn thứ {index + 1}")

        # 1. Gửi các tin nhắn mở đầu: Tin 1-7 (Index 0-6) gửi cách nhau 15s
        opening_delays = [15, 15, 15, 15, 15, 15, 15]
        
        print("\n=== BẮT ĐẦU GỬI CÁC TIN NHẮN MỞ ĐẦU (TIN 1-7, INDEX 0-6) ===")
        for i, index in enumerate(BEFORE_BET_ORDER):
            await forward_slot(index, f"Đã gửi tin nhắn mở đầu thứ {i + 1} (Tin thứ {index + 1}, index {index})")
            sleep_time = opening_delays[i] if i < len(opening_delays) else 15
            await asyncio.sleep(sleep_time)

        # 2. VÀO ROUND (Hô 3 lệnh)
        print(f"\n=== BẮT ĐẦU VÀO ROUND HÔ {RESULT_SEQUENCE_REPEAT} LỆNH ===")
        for repeat_index in range(RESULT_SEQUENCE_REPEAT):
            print(f"\n--- Lệnh thứ {repeat_index + 1}/{RESULT_SEQUENCE_REPEAT} ---")

            # a) Hô CON (tin thứ 8 -> index 7) hoặc Hô CÁI (tin thứ 9 -> index 8)
            is_cai = random.choice([True, False])
            if is_cai:
                bet_msg_index = 8  # Tin thứ 9 (Index 8) - Hô CÁI
                label_text = f"1. [Lệnh {repeat_index + 1}] Đã gửi tin nhắn Hô CÁI (Tin thứ 9, index {bet_msg_index})"
            else:
                bet_msg_index = 7  # Tin thứ 8 (Index 7) - Hô CON
                label_text = f"1. [Lệnh {repeat_index + 1}] Đã gửi tin nhắn Hô CON (Tin thứ 8, index {bet_msg_index})"

            await forward_slot(bet_msg_index, label_text)
            await asyncio.sleep(45)

            # b) Xử lý kết quả (75% Thắng, 15% Thua, 10% Hòa)
            result = random.random()
            if result < 0.75:
                is_win, is_tie = True, False
            elif result < 0.90:
                is_win, is_tie = False, False
            else:
                is_win, is_tie = False, True

            if is_tie:
                # Nếu HÒA: Gửi ảnh 'tie' kèm text "〰️ HÒA + 0%", KHÔNG gửi tin thứ 10/11
                await send_result_image(group, 'tie', caption='**〰️ HÒA + 0%**')
                print(f"2. [Lệnh {repeat_index + 1}] Đã gửi ảnh HÒA kèm text: 〰️ HÒA + 0%")
                await asyncio.sleep(10)
            else:
                # Nếu Thắng / Thua: Gửi ảnh không kèm caption
                if is_cai:
                    result_type = 'wincai' if is_win else 'losecai'
                else:
                    result_type = 'wincon' if is_win else 'losecon'

                await send_result_image(group, result_type, caption=None)
                print(f"2. [Lệnh {repeat_index + 1}] Đã gửi ảnh kết quả loại: {result_type} (không kèm caption)")
                await asyncio.sleep(10)

                # c) Tin nhắn sau kết quả: Thắng gửi tin thứ 10 (Index 9), Thua gửi tin thứ 11 (Index 10)
                if is_win:
                    result_msg_index = 9  # Tin thứ 10
                    res_label = f"3. [Lệnh {repeat_index + 1}] Đã gửi tin nhắn THẮNG (Tin thứ 10, index {result_msg_index})"
                else:
                    result_msg_index = 10  # Tin thứ 11
                    res_label = f"3. [Lệnh {repeat_index + 1}] Đã gửi tin nhắn THUA (Tin thứ 11, index {result_msg_index})"

                await forward_slot(result_msg_index, res_label)
                await asyncio.sleep(10)

        # 3. Gửi nốt 3 tin nhắn kết thúc phiên: Tin 12, 13, 14 (Index 11, 12, 13)
        print("\n=== KẾT THÚC PHIÊN - GỬI 3 TIN NHẮN (TIN 12, 13, 14) ===")
        ending_indices = [(11, 12), (12, 13), (13, 14)]  # (index, tin_num)
        for index, tin_num in ending_indices:
            await forward_slot(index, f"Đã gửi tin nhắn kết thúc (Tin thứ {tin_num}, index {index})")
            await asyncio.sleep(10)

        print("=== KẾT THÚC PHIÊN THÀNH CÔNG ===\n")
    except Exception as e:
        print(f"Lỗi trong daily_schedule: {e}")
        # Thử kết nối lại nếu bị ngắt kết nối
        if "disconnected" in str(e).lower():
            print("Phát hiện mất kết nối, đang thử kết nối lại...")
            try:
                await client.connect()
                if not await client.is_user_authorized():
                    await login_client()
                print("Đã kết nối lại thành công!")
            except Exception as reconnect_error:
                print(f"Không thể kết nối lại: {reconnect_error}")
        raise  # Ném lại lỗi để xử lý ở cấp cao hơn

def add_fixed_post(time_slot, image_path):
    """Add a new fixed post for a specific time slot"""
    posts = load_posts()
    if time_slot not in posts['fixed_posts']:
        posts['fixed_posts'][time_slot] = []
    
    posts['fixed_posts'][time_slot].append({
        'image_path': image_path
    })
    save_posts(posts)

def add_rotating_post(time_slot, image_path, result_type=None):
    """Add a new rotating post for a specific time slot and result type, optionally explicit result_type"""
    filename = os.path.basename(image_path).lower()
    if result_type is None:
        if filename.startswith('win_'):
            result_type = 'wincai' if 'cai' in filename else 'wincon'
        elif filename.startswith('lose_'):
            result_type = 'losecai' if 'cai' in filename else 'losecon'
        elif filename.startswith('tie_'):
            result_type = 'tie'
        else:
            raise ValueError("Image filename must start with 'win_', 'lose_' or 'tie_'")
    posts = load_posts()
    if time_slot not in posts['rotating_posts'][result_type]:
        posts['rotating_posts'][result_type][time_slot] = []
    
    existing_paths = {p['image_path'] for p in posts['rotating_posts'][result_type][time_slot]}
    if image_path not in existing_paths:
        posts['rotating_posts'][result_type][time_slot].append({
            'image_path': image_path,
            'last_sent_index': -1
        })
        save_posts(posts)

def add_rotating_posts_from_directory():
    """Automatically add all image files from each result directory, regardless of filename prefix"""
    # Add wincai posts
    wincai_dir = WINCAI_IMAGES_DIR
    if os.path.exists(wincai_dir):
        for filename in os.listdir(wincai_dir):
            if not filename.startswith('.'):
                add_rotating_post('11:00', os.path.join(wincai_dir, filename), result_type='wincai')

    # Add losecai posts
    losecai_dir = LOSECAI_IMAGES_DIR
    if os.path.exists(losecai_dir):
        for filename in os.listdir(losecai_dir):
            if not filename.startswith('.'):
                add_rotating_post('11:00', os.path.join(losecai_dir, filename), result_type='losecai')

    # Add wincon posts
    wincon_dir = WINCON_IMAGES_DIR
    if os.path.exists(wincon_dir):
        for filename in os.listdir(wincon_dir):
            if not filename.startswith('.'):
                add_rotating_post('11:00', os.path.join(wincon_dir, filename), result_type='wincon')

    # Add losecon posts
    losecon_dir = LOSECON_IMAGES_DIR
    if os.path.exists(losecon_dir):
        for filename in os.listdir(losecon_dir):
            if not filename.startswith('.'):
                add_rotating_post('11:00', os.path.join(losecon_dir, filename), result_type='losecon')

    # Add tie posts
    tie_dir = TIE_IMAGES_DIR
    if os.path.exists(tie_dir):
        for filename in os.listdir(tie_dir):
            if not filename.startswith('.'):
                add_rotating_post('11:00', os.path.join(tie_dir, filename), result_type='tie')

def is_schedule_minute(hour, minute):
    return f"{hour:02d}:{minute:02d}" in TIME_SLOTS_SET


def is_within_schedule(hour, minute):
    """Kiem tra moc hien tai co nam trong danh sach ca da cau hinh hay khong."""
    return is_schedule_minute(hour, minute)


def generate_daily_slots():
    """Tao cac moc trong ngay theo gio bat dau/ket thuc va khoang cach (GMT+7)."""
    if SCHEDULE_INTERVAL <= 0:
        raise ValueError('SCHEDULE_INTERVAL phai lon hon 0')

    slots = []
    start_minutes = SCHEDULE_START_HOUR * 60 + SCHEDULE_START_MINUTE
    end_minutes = SCHEDULE_END_HOUR * 60 + SCHEDULE_END_MINUTE
    total_minutes = end_minutes - start_minutes

    # Ho tro khung gio qua ngay, vi du 12:15 -> 00:00 hom sau.
    if total_minutes < 0:
        total_minutes += 24 * 60

    minutes = start_minutes
    elapsed = 0
    while elapsed <= total_minutes:
        hour, minute = divmod(minutes % (24 * 60), 60)
        slots.append(f"{hour:02d}:{minute:02d}")
        minutes += SCHEDULE_INTERVAL
        elapsed += SCHEDULE_INTERVAL

    return slots


TIME_SLOTS = generate_daily_slots()
TIME_SLOTS_SET = set(TIME_SLOTS)
if not TIME_SLOTS:
    raise ValueError('Khong tao duoc TIME_SLOTS, vui long kiem tra cau hinh lich')
log(f"[INFO] Da tao {len(TIME_SLOTS)} ca: {TIME_SLOTS[0]} -> {TIME_SLOTS[-1]}")


def get_next_slot(now):
    """Tim ca tiep theo theo thu tu da cau hinh, ho tro moc qua ngay."""
    current_slot = f"{now.hour:02d}:{now.minute:02d}"
    if current_slot in TIME_SLOTS:
        current_index = TIME_SLOTS.index(current_slot)
        return TIME_SLOTS[(current_index + 1) % len(TIME_SLOTS)]

    current = now.hour * 60 + now.minute
    future_slots = []
    wrapped_slots = []
    for slot in TIME_SLOTS:
        h, m = map(int, slot.split(':'))
        slot_minutes = h * 60 + m
        if slot_minutes > current:
            future_slots.append((slot_minutes, slot))
        else:
            wrapped_slots.append((slot_minutes, slot))

    if future_slots:
        return min(future_slots)[1]
    return min(wrapped_slots)[1]


async def schedule_loop(entities):
    """Chay theo danh sach moc da cau hinh trong ngay (GMT+7)."""
    global sent_slots
    log(
        f"[INFO] Lich: bat dau {SCHEDULE_START_HOUR:02d}:{SCHEDULE_START_MINUTE:02d}, "
        f"moi {SCHEDULE_INTERVAL} phut, {len(TIME_SLOTS)} ca/ngay, "
        f"moc cuoi {TIME_SLOTS[-1]} GMT+7"
    )
    while True:
        now = datetime.now(TZ)
        hour = now.hour
        minute = now.minute
        in_window = is_within_schedule(hour, minute)
        on_slot = is_schedule_minute(hour, minute)

        log(
            f"[HEARTBEAT] {now.strftime('%H:%M:%S')} GMT+7 | "
            f"trong khung gio: {'CO' if in_window else 'KHONG'} | "
            f"moc {SCHEDULE_INTERVAL}p: {'CO' if on_slot else 'KHONG'} | "
            f"ca tiep: {get_next_slot(now)}"
        )

        if on_slot and in_window:
            slot_key = now.strftime('%Y-%m-%d %H:%M')
            if slot_key not in sent_slots:
                log(f"[INFO] Bat dau ca luc {slot_key} cho {len(entities)} nhom")
                await asyncio.gather(*(run_session_with_retry(get_client(), entity) for entity in entities))
                sent_slots.add(slot_key)
            else:
                log(f"[INFO] Ca {slot_key} da chay roi, bo qua")

        if hour == 0 and minute == 1:
            sent_slots = set()
            log("[INFO] Reset sent_slots cho ngay moi")

        await asyncio.sleep(60 - now.second)

async def send_now():
    """Gửi ngay nội dung theo daily_schedule với entity từ .env"""
    try:
        telegram_client = get_client()
        entities = await resolve_group_entities(os.getenv('GROUP'))
        for entity in entities:
            await daily_schedule(telegram_client, entity)
        print('Đã gửi ngay nội dung theo daily_schedule!')
    except Exception as e:
        print(f"Lỗi khi gửi ngay nội dung: {e}")

async def list_dialogs():
    """Lấy danh sách nhóm/channel mà userbot đang tham gia"""
    print("Danh sách nhóm/channel đang tham gia:")
    async for dialog in get_client().iter_dialogs():
        if isinstance(dialog.entity, (Channel, Chat)):
            print(f"Name: {dialog.name} | ID: {dialog.id} | Type: {type(dialog.entity).__name__} | Username: {getattr(dialog.entity, 'username', None)}")


async def main():
    """Main function to run the bot"""
    global client
    ensure_single_instance()
    atexit.register(release_lock)

    ensure_directories()
    add_rotating_posts_from_directory()
    log("Starting bot and waiting for scheduled slots...")

    try:
        if not api_id or not api_hash:
            log("[ERROR] API_ID hoac API_HASH chua duoc cau hinh hop le trong .env")
            sys.exit(1)

        # Tao TelegramClient ben trong running event loop de tranh loi
        # "Future attached to a different loop" tren Telethon.
        client = TelegramClient(SESSION_NAME, api_id, api_hash)
        log("Dang ket noi Telegram...")
        await login_client()
        configure_sqlite_session(client)
        me = await client.get_me()
        log(f"Dang nhap: {me.first_name} (@{me.username})")

        await list_dialogs()

        try:
            entities = await resolve_group_entities(os.getenv('GROUP'))
            log(f'Da lay {len(entities)} entity tu GROUP! Cho lich gui...')
        except Exception as e:
            log(f"Loi khi lay entity tu .env: {e}")
            return

        log("[INFO] Gửi ngay 1 phiên khi vừa bật bot...")
        await send_now()
        await schedule_loop(entities)
    finally:
        await client.disconnect()
        release_lock()

if __name__ == '__main__':
    asyncio.run(main())
