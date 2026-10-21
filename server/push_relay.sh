#!/usr/bin/env bash
# Push the current relay to the live host and restart it.
#
#   ./server/push_relay.sh                 # uses the default host below
#   TQG_HOST=nept@192.168.99.56 ./server/push_relay.sh
#
# Copies relay.py over the deployed copy, restarts the systemd unit, and checks
# /health both locally and through the public funnel. Run it after any change to
# server/relay.py — the running service does NOT pick changes up on its own.
set -euo pipefail

HOST="${TQG_HOST:-nept@192.168.99.56}"
DEST="${TQG_RELAY_DIR:-/opt/tqg-relay}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/relay.py"

echo "[*] copying relay.py -> ${HOST}:${DEST}/relay.py"
scp -q "$SRC" "${HOST}:/tmp/relay.py.new"
ssh "$HOST" "sudo -n install -m 0755 /tmp/relay.py.new '$DEST/relay.py' && sudo -n systemctl restart tqg-relay" \
    || { echo "[!] needs passwordless sudo on $HOST (or run deploy.sh there instead)" >&2; exit 1; }

sleep 1
echo "[*] local health:"
ssh "$HOST" "curl -s -m 5 http://127.0.0.1:8090/health" || true
echo
echo "[*] public health:"
curl -s -m 8 https://wikipedia.tail06361a.ts.net/ai/health || echo "(no funnel response)"
echo
echo "[*] social smoke (presence round-trip through the funnel):"
curl -s -m 8 -X POST https://wikipedia.tail06361a.ts.net/ai/v1/presence \
    -H 'Content-Type: application/json' \
    -d '{"id":"deploycheck0001","name":"deploy","platform":"sh"}' || true
echo
