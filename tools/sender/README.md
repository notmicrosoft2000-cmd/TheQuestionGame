# The operator sender

**This program is not part of any release. It is never linked from the
website, never shipped, never bundled.** It is the *writing* half of the
online feature; the game everyone downloads is the *receiving* half. The relay
enforces the split server-side — `POST /v1/send-question` refuses any caller
without the send token.

If you find yourself about to publish this, don't.

## What it does

- joins the room under its own operator identity and shows who is playing
- composes a question: text, up to four options, and which one is correct
- fires it at one player or at everyone in the room
- reports what the relay actually did — delivered, refused, nobody there
- shows the answers that come back, right or wrong

## Running it

```sh
python3 tools/sender/sender.py
```

With no token in the environment the app asks for one: paste it and press
ENTER. It is checked against the relay before it is accepted, then kept with
`0600` permissions in the game's appdata folder
(`~/.tqgame_remastered/sender_token` on Linux). `CTRL+X` clears it again.

To skip the prompt:

```sh
TQG_SEND_TOKEN=... python3 tools/sender/sender.py
```

The environment wins over the saved file. An explicitly empty `TQG_SEND_TOKEN`
means "no token" and does *not* fall back to the file.

`TQG_SENDER_NAME` sets the name the operator appears under in the room
(default `OPERATOR`).

## Getting the token

The token is the relay's `RELAY_SEND_TOKEN`. On the relay host it lives in
`/opt/tqg-relay/relay.env`, which is root-only:

```sh
ssh nept@192.168.99.56 "sudo grep RELAY_SEND_TOKEN /opt/tqg-relay/relay.env"
```

## Keys

| key | what it does |
|---|---|
| `TAB` / `SHIFT+TAB` | move between fields |
| `ENTER` | edit the focused field, or press the focused button |
| `UP` / `DOWN` | on the `SEND TO` field: choose who receives the question |
| `1` `2` `3` `4` | set which option is the correct one |
| `F1` (or `H`) | the "how this works" screen |
| `CTRL+X` | forget the token |
| `ESC` | quit (or leave the field you are editing) |

The room list is on the left, the compose form in the middle, and the delivery
log plus the answers on the right.

## How a question travels

```
player's game            this app                   the relay
-----------            --------                   --------
polls /v1/presence  ->  polls /v1/presence      ->  keeps the room in memory
shows the ONLINE screen  sees who is playing       ->  expires idle peers
plays a question        composes a question       ->  one-shot delivery:
answers it              posts /v1/send-question        the item is cleared
                           (with X-Send-Token)            the moment it is
                           <- "delivered to N"             handed over
                        polls /v1/presence      <-  the answer comes back
                         sees RIGHT / WRONG            on the next poll
```

Three relay behaviours to keep in mind:

- **"join presence first"** — the relay only knows you exist once it has
  polled you in. Send before that and it refuses you.
- **"nobody to send to"** — a question addressed to a peer who has dropped off
  (20 s without a poll) has nobody to go to.
- **one-shot** — a question is delivered once. If it is not picked up, it is
  gone.

## Tests

```sh
python3 tools/sender/test_sender.py     # prints SENDER_OK
```

The test starts a real relay in-process and drives the whole path: the sender
joins, a receiving client joins, the question is delivered, the answer comes
back. It also covers the token gate — the right token is accepted, a wrong one
is refused, and an unreachable relay is reported as offline rather than as a
bad token.
