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

With no token anywhere the app asks for one: paste it and press ENTER. It is
checked against the relay before it is accepted, then kept with `0600`
permissions in the game's appdata folder (`~/.tqgame_remastered/sender_token` on
Linux). `CTRL+X` clears it again.

The token is looked for in this order:

1. `TQG_SEND_TOKEN` in the environment;
2. `tqg-token.txt` in the repository root (a plain file, hand-edited, gitignored);
3. the saved copy in the appdata folder;
4. nothing — the app asks.

An explicitly empty `TQG_SEND_TOKEN` means "no token" and stops the search.

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
| `F2` | the effects screen: fire a scare or glitch by hand |
| `CTRL+X` | forget the token |
| `ESC` | quit (or leave the field you are editing) |
| mouse wheel | scroll the compose form |

On the effects screen (`F2`):

| key | what it does |
|---|---|
| `UP` / `DOWN` | pick the effect |
| `LEFT` / `RIGHT` | set the intensity — how long it lasts (x0.50 to x2.00) |
| `ENTER` | fire it at the current recipient (stays open, so you can fire again) |
| `F2` / `ESC` | back |

## Sections

- **The room** on the left: `EVERYONE` plus every player whose game is polling
  right now. `UP`/`DOWN` picks who gets the next question.
- **Compose** on the right: the recipient, the question, up to four options, and
  which of them is correct. Long questions wrap over as many lines as they need
  and the form scrolls (mouse wheel) — nothing is ever truncated with `...`.
- **Delivery** along the bottom: what the relay actually said about each send.
  `QUEUED` is not `DELIVERED`.
- **Replies** next to it: the answers that came back, with the question they
  belong to.

`F1` opens the full explanation, including where the relay physically lives.

## Effects — firing a scare by hand (`F2`)

The operator can also fire the game's own scares and glitches at a player,
without writing a question. The list is read from the game's
`scares.SCARE_REGISTRY`, so it can never drift from what the receiver can
actually play.

The effect travels the **same route** as a question (`/v1/send-question`, same
`X-Send-Token` gate), but the body carries `"effect"` instead of `"q"` and it
lands in its own store on the relay. The player's next presence poll collects it
under `"effects"` and the game plays it through `scares.apply_scare` — which
means it is **indistinguishable from the model choosing that effect itself**.
No toast, no note, no warning. It simply happens.

`intensity` scales how long the effect lasts (`game.fx["scare_scale"]`), so the
same flicker can be a blink or a sustained stutter. The relay clamps it to
`[0.1, 2.0]` and refuses unknown effect names with a `400`, so a typo fails
loudly here instead of silently doing nothing on the player's screen.

Effects are recorded in the delivery log like questions are, so the relay's
verdict about them is reported just as honestly. They do not clear the compose
form — there is nothing in it to clear.

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

The relay is the maintainer's **home server** at `192.168.99.56`, published as a
Tailscale Funnel. Locally it listens on `127.0.0.1:8090` only; the funnel
forwards it to the internet. It is the same relay that answers the game's AI
questions. The room is in-memory: no database, no accounts, no history — a
restart empties it.

The player-facing build deliberately does not know any of this. It gets the
funnel URL and nothing else; the host, the ssh command and this program stay on
the operator's side.

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
