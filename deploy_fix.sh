#!/bin/bash
# Deploy script for kupinne-bot
# Usage: bash deploy_fix.sh

set -e

echo "=== Cleaning up old venv ==="
cd /var/www/gg88/bot-keo-nhom/5d/kupinne-bot || exit 1
rm -rf venv
hash -r

echo "=== Creating new venv ==="
python3 -m venv venv
source venv/bin/activate

echo "=== Installing dependencies ==="
pip install -r requirements.txt

echo "=== Running test (will exit after startup test) ==="
timeout 30 python3 bot.py 2>&1 || true

echo "=== Checking syntax ==="
python3 -m py_compile bot.py && echo "✓ Syntax OK"

echo "=== Done! ==="
echo "To run manually: python3 bot.py"
echo "To run with PM2: pm2 start ecosystem.config.js"
