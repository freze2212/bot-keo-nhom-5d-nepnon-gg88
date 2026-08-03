with open('bot.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the exact text to remove (lines 683-689 in 1-indexed, 682-688 in 0-indexed)
target = """  for index in AFTER_RESULT_ORDER:
    await forward_slot(index, f"Đã gửi tin nhắn thứ {index + 1}")
    await asyncio.sleep(10)
  print("=== KẾT THÚC PHIÊN ===\\n")
  for index in AFTER_RESULT_ORDER:
    await forward_slot(index, f"Đã gửi tin nhắn thứ {index + 1}")
    await asyncio.sleep(10)

except Exception as e:"""

replacement = """except Exception as e:"""

content = ''.join(lines)
if target in content:
    content = content.replace(target, replacement, 1)
    print("Found and replaced!")
else:
    # Try line-by-line removal: remove lines 682-688 (0-indexed)
    del lines[682:689]
    content = ''.join(lines)
    print("Removed lines 683-689 (1-indexed)")

with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Fixed!")
