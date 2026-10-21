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

## Online players + hand-written questions (social)

The same service also runs the small "who is online" room behind the game's
**ONLINE** screen, so the `/ai` funnel path exposes it with no extra setup.
Everything is in memory: a restart empties the room, and presence is rebuilt by
the next poll.

| endpoint | what it does |
|---|---|
| `POST /v1/presence` | heartbeat. Returns the current online list, plus any questions addressed to you and results for questions you sent |
| `POST /v1/send-question` | deliver a hand-written question to one peer, or `"all"` |
| `POST /v1/answer` | report a recipient's answer back to the question's author |

Delivery is **one-shot**: the server clears an item as it hands it over, so a
question is never replayed. Items expire after `RELAY_QUESTION_TTL` (900s) and a
peer is dropped from the room after `RELAY_PEER_TTL` (20s) without a poll.

These endpoints are deliberately **open** — the game ships with no token, and
the whole point is that any copy can see the others. They are rate-limited
separately (`RELAY_SOCIAL_RATE`/min, `RELAY_SOCIAL_BURST`) and every string is
capped, so all they can move is a question-sized payload. They never touch the
Groq upstream or the API key.

Knobs (all optional, in `relay.env`):

| var | default | meaning |
|---|---|---|
| `RELAY_PEER_TTL` | `20` | seconds without a poll before a peer leaves the list |
| `RELAY_QUESTION_TTL` | `900` | seconds a question/result may sit undelivered |
| `RELAY_INBOX_MAX` | `12` | queued questions kept per player |
| `RELAY_RESULT_MAX` | `12` | answer results kept per sender |
| `RELAY_SOCIAL_RATE` | `120` | social requests per minute per IP |
| `RELAY_SOCIAL_BURST` | `40` | social requests per 3s per IP |

