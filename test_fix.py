with open(r'c:\BOT TELE\ghe-nepnon\bot.py', encoding='utf-8') as f:
    txt = f.read()

# Remove duplicate: second "for index in AFTER_RESULT_ORDER:" block
# Lines 683-689 (0-indexed 682-688): weave avg .w[.q.øßúô«.
target = '''    for index in AFTER_RESULT_ORDER:
      await forward_slot(index, f"Đã gửi tin nhắn thứ {index + 1}")
      await asyncio.sleep(10)
    print("=== KẾT THÚC PHIÊN ===\\n")
    for index in AFTER_RESULT_ORDER:
      await forward_slot(index, f"Đã gửi tin nhắn thứ {index + 1}")
      await asyncio.sleep(10)

  except Exception as e:'''

replacement = '''except Exception as e:'''

if target in txt:
    txt = txt.replace(target, replacement, 1)
    with open(r'c:\BOT TELE\ghe-nepnon\bot.py', 'w', encoding='utf-8') as f:
        f.write(txt)
    print('SUCCESS: Fixed!')
else:
    print('ERROR: pattern not found')
