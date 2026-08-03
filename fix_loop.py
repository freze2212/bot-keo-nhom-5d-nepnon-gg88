with open('bot.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Lines 683-689 (1-indexed) = indices 682-688 (0-indexed)
# Replace with correct structure
new_lines = lines[:682] + [
    '        print("=== KẾT THÚC PHIÊN ===\\n")\n',
    '\n',
    '    for index in AFTER_RESULT_ORDER:\n',
    '        await forward_slot(index, f"Đã gửi tin nhắn thứ {index + 1}")\n',
    '        await asyncio.sleep(10)\n',
] + lines[689:]

with open('bot.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Fixed! AFTER_RESULT_ORDER now correctly placed after the for loop.")
