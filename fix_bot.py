#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fix duplicate code block in bot.py causing SyntaxError"""

import sys

def fix_bot():
    with open('bot.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()

    print(f"Total lines before fix: {len(lines)}")

    # Find the duplicate block (should be around lines 683-689)
    # We need to remove the second "for index in AFTER_RESULT_ORDER:" block
    # Lines 683-685 are the first block (correct)
    # Lines 687-689 are the duplicate (need to remove)

    # Find all occurrences of the pattern
    indices_to_remove = []
    for i, line in enumerate(lines):
        if 'for index in AFTER_RESULT_ORDER:' in line and i > 680:
            # Check if this is the duplicate by looking at context
            if i + 2 < len(lines):
                next_line = lines[i + 1]
                if 'await forward_slot' in next_line:
                    indices_to_remove.append(i)

    print(f"Found {len(indices_to_remove)} occurrences of AFTER_RESULT_ORDER loop")

    # Remove the second occurrence (index 686 in 0-indexed = line 687)
    if len(indices_to_remove) >= 2:
        idx = indices_to_remove[1]  # Second occurrence
        print(f"Removing duplicate block starting at line {idx + 1}")
        # Remove 3 lines: for, await, await sleep
        del lines[idx:idx + 3]

    print(f"Total lines after fix: {len(lines)}")

    with open('bot.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)

    print("✓ Fixed! Duplicate block removed.")
    return True

if __name__ == '__main__':
    try:
        success = fix_bot()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)
