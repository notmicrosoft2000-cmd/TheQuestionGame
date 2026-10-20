# The Question Game — AI relay

The game ships with **no API key**. It sends its question requests here; this
relay holds the key and forwards them to Groq. That means a fresh install needs
no setup, and the key can be rotated without re-releasing the game.

```
player's game ──HTTPS──> tailscale funnel ──> this relay ──> Groq
                              /ai               :8090        (key lives here)
```

## Files

| file | what it is |
|---|---|
| `relay.py` | the service — stdlib only, no dependencies |
| `relay.env.example` | config template; copy to `relay.env` and fill in the key |
| `tqg-relay.service` | systemd unit |
| `deploy.sh` | installs everything and starts the service |

## What it protects against

It is not an open door to your key. It accepts one endpoint, locks the model,
caps tokens, drops every field it does not recognise, and rate-limits per IP:

- **model is fixed** — callers cannot switch to a more expensive model
- **`max_tokens` is capped** at `RELAY_MAX_TOKENS`
- **only** `messages`, `temperature`, `max_tokens`, `reasoning_effort` are forwarded
- **conversation capped** at 12 messages, 8000 chars each
- **rate limit** `RELAY_RATE`/min with a `RELAY_BURST` spike allowance
- optional **shared app token** (`X-App-Token`) so the URL alone is useless

## Deploy (Ubuntu, systemd)

```sh
sudo ./deploy.sh
sudo nano /opt/tqg-relay/relay.env     # set RELAY_KEY (and RELAY_APP_TOKEN)
sudo systemctl restart tqg-relay
curl -s localhost:8090/health
```

Then expose it publicly with Tailscale Funnel:

```sh
sudo tailscale funnel --bg --set-path /ai http://127.0.0.1:8090
tailscale funnel status
```

The public URL becomes `https://<machine>.<tailnet>.ts.net/ai`, and the game's
`RELAY_URL` (in `config.py`) already points at it.

## Manually, without systemd

```sh
set -a; . ./relay.env; set +a
python3 relay.py
```

## Note on the app token

If you set `RELAY_APP_TOKEN`, the shipped game's `TQG_RELAY_TOKEN` / config
`RELAY_TOKEN` must match it. Leave it empty to accept any caller (rate limits
still apply). Setting it is recommended if the URL is shared publicly, but the
token is extractable from the build — treat it as a speed bump, not a secret.
The real protections are the model lock, the token cap, and the rate limit.
