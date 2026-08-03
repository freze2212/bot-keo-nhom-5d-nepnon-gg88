with open('bot.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f"Before: {len(lines)} lines")

# 0-indexed: delete 683, 684, 685 (1-indexed: 684, 685, 686)
# These are:
# 683: "  for index in AFTER_RESULT_ORDER:"
# 684: '    await forward_slot(index, f"Đã gửi tin nhắn thứ {index + 1}")'
# 685: "    await asyncio.sleep(10)"
#
# The FIRST block (line 683-685, 0-indexed 682-684) KEEPS
# The DUPLICATE block (line 687-689, 0-indexed 686-688) REMOVE

removed = lines[686:689]
print(f"Removing lines: {removed}")
del lines[686:689]

print(f"After: {len(lines)} lines")

with open('bot.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
print("DONE!")
