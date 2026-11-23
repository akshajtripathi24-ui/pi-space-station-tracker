#!/bin/bash
# Makes the space station tracker start automatically whenever the Pi boots,
# and restart by itself if it ever crashes.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$DIR/venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

sudo tee /etc/systemd/system/isstracker.service > /dev/null << SERVICE
[Unit]
Description=Pi Space Station Tracker
After=network-online.target time-sync.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$DIR
ExecStart=$PY $DIR/server.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable isstracker
sudo systemctl restart isstracker
echo
echo "Done! The space station tracker now runs in the background and starts on boot."
echo "Open:          http://$(hostname).local:8080"
echo "    (or use the Pi's IP address:  http://YOUR-PI-IP:8080  - find it with: hostname -I)"
echo "See its log:   journalctl -u isstracker -f"
echo "Stop it:       sudo systemctl stop isstracker"
echo "Turn off auto: sudo systemctl disable --now isstracker"
