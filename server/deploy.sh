#!/usr/bin/env bash
# Deploy the TQG AI relay on a Linux host with systemd.
#
# Usage:   sudo ./server/deploy.sh
# Then:    edit /opt/tqg-relay/relay.env and put your Groq key in RELAY_KEY
# Then:    sudo systemctl restart tqg-relay
#
# Idempotent: safe to re-run after pulling changes.

set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${TQG_RELAY_DIR:-/opt/tqg-relay}"
UNIT=/etc/systemd/system/tqg-relay.service
PY="$(command -v python3)"

if [[ $EUID -ne 0 ]]; then
    echo "run me with sudo" >&2
    exit 1
fi
if [[ -z "$PY" ]]; then
    echo "python3 not found" >&2
    exit 1
fi

echo "[*] installing to $DEST"
mkdir -p "$DEST"
install -m 0755 "$SRC_DIR/relay.py" "$DEST/relay.py"

if [[ ! -f "$DEST/relay.env" ]]; then
    install -m 0600 "$SRC_DIR/relay.env.example" "$DEST/relay.env"
    echo "[!] created $DEST/relay.env — you MUST set RELAY_KEY in it:"
    echo "    sudo nano $DEST/relay.env && sudo systemctl restart tqg-relay"
else
    echo "[*] keeping existing $DEST/relay.env"
fi
chmod 600 "$DEST/relay.env"

echo "[*] writing $UNIT"
sed "s|__DIR__|$DEST|g" "$SRC_DIR/tqg-relay.service" > "$UNIT"
# The unit assumes /usr/bin/python3; rewrite if this host differs.
sed -i "s|/usr/bin/python3|$PY|" "$UNIT"

systemctl daemon-reload
systemctl enable --now tqg-relay
sleep 1
systemctl --no-pager status tqg-relay || true

echo
echo "[*] health check:"
curl -s -m 5 http://127.0.0.1:"$(grep -oP 'RELAY_PORT=\K.*' "$DEST/relay.env" 2>/dev/null || echo 8090)"/health || \
    echo "(no response yet — check: journalctl -u tqg-relay -n 30)"
echo
echo "[*] done. Now expose it through Tailscale:"
echo "    sudo tailscale funnel --bg --set-path /ai http://127.0.0.1:8090"
echo "    tailscale funnel status"
