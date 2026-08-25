#!/bin/zsh
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required. Install Python 3, then run this file again."
  read -k 1 "?Press any key to close..."
  exit 1
fi

LAN_IP=$(ipconfig getifaddr en0 2>/dev/null)
if [ -z "$LAN_IP" ]; then
  LAN_IP=$(ipconfig getifaddr en1 2>/dev/null)
fi

export HOST=0.0.0.0
export PORT=8000

open "http://127.0.0.1:8000" >/dev/null 2>&1 &

echo ""
echo "CivilStandards is starting."
echo "Mac:    http://127.0.0.1:8000"
if [ -n "$LAN_IP" ]; then
  echo "iPhone/iPad on the same Wi-Fi: http://$LAN_IP:8000"
fi
echo ""
echo "Keep this window open while using the site. Press Control-C to stop it."
echo ""
python server.py
