#!/bin/bash
# ReaderPlus Setup — Debian/Ubuntu als root, oder in einem Container mit Bind-Mounts.
set -e

install_root="${READERPLUS_HOME:-/var/www}"
echo "==== ReaderPlus Setup ===="
echo "Install root: $install_root"

# 0. System-Packages (falls möglich)
if command -v apt-get >/dev/null 2>&1; then
  echo "[*] System-Packages..."
  apt-get update -qq || true
  apt-get install -y -qq python3 python3-pip ffmpeg \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2 libnspr4 libatspi2.0-0 || true
fi

# 1. Verzeichnisse
mkdir -p "$install_root/html" "$install_root/piper-voices"

# 2. App-Files
cp -f readerplus.html "$install_root/html/"
cp -f aa_proxy.py "$install_root/"
cp -f piper-voices/*.onnx "$install_root/piper-voices/" 2>/dev/null || true
cp -f piper-voices/*.onnx.json "$install_root/piper-voices/" 2>/dev/null || true
chmod +x setup.sh

# 3. Python-Dependencies
echo "[*] Installing Python deps..."
pip3 install --break-system-packages -q -r requirements.txt || \
  pip3 install --quiet -r requirements.txt

# 4. Playwright Chromium Download (best-effort)
echo "[*] Playwright Chromium..."
python3 -m playwright install chromium 2>&1 | tail -2 || true

# 5. systemd-Service (falls systemctl)
if command -v systemctl >/dev/null 2>&1; then
  echo "[*] systemd service..."
  cat > /etc/systemd/system/readerplus-aa.service <<EOF
[Unit]
Description=ReaderPlus AA + Piper Proxy
After=network.target

[Service]
ExecStart=/usr/bin/python3 $install_root/aa_proxy.py
Restart=always
RestartSec=5
User=root
Environment=AA_BASE=https://annas-archive.gl
Environment=VOICES_DIR=$install_root/piper-voices

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable readerplus-aa.service
  systemctl restart readerplus-aa.service || true
fi

# 6. Caddyfile (falls /etc/caddy/Caddyfile existiert)
if [ -f /etc/caddy/Caddyfile ] && ! grep -q "18792" /etc/caddy/Caddyfile; then
  echo "[*] Caddyfile Eintrag..."
  cat >> /etc/caddy/Caddyfile <<'CADDY'

# ReaderPlus
:9999 {
  root * /var/www/html
  redir / /readerplus.html
  handle /api/* {
    reverse_proxy 127.0.0.1:18792
  }
  file_server
}
CADDY
  systemctl reload caddy 2>/dev/null || true
fi

echo
echo "==== Setup complete ===="
echo "  Webapp:    http://<server>:9999/"
echo "  Health:    curl http://127.0.0.1:18792/api/health"
