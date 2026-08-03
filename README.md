# bot-keo-nhom-5d-g

Telegram userbot (Telethon) — forward tin từ `@house4179` sang nhóm theo lịch, kèm ảnh kết quả ngẫu nhiên.

## Cấu hình `.env`

```env
API_ID=
API_HASH=
PHONE=+84xxxxxxxxx
GROUP=-100xxxxxxxxxx,@ten_nhom_khac
```

Lấy `API_ID` / `API_HASH` tại https://my.telegram.org

## Chạy local

```bash
python3 -m venv venv
# Windows: .\venv\Scripts\activate
# macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
python3 bot.py
```

## Deploy VPS (PM2)

```bash
git clone https://github.com/freze2212/bot-keo-nhom-5d-g.git
cd bot-keo-nhom-5d-g
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
nano .env   # điền API_ID, API_HASH, PHONE, GROUP
python3 bot.py   # nhập OTP lần đầu
pm2 start ecosystem.config.js
pm2 save
pm2 logs bot-keo-nhom-5d-g
```

## Lưu ý

- Gửi **9 tin mẫu** vào `@house4179` (tin 8 = CON, tin 9 = CÁI).
- `GROUP` có thể nhận 1 hoặc nhiều giá trị, ngăn cách bằng dấu phẩy `,`, chấm phẩy `;` hoặc xuống dòng.
- Account phải **join tất cả nhóm** trong `GROUP`.
- Không commit `.env` và `user_session*.session`.
