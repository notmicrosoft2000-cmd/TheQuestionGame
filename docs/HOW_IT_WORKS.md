# How it works

Plain-language explanation of the online parts: the AI, the relay, the room,
and the home server that ties them together. No code required.

If you want the engineering version — file names, gotchas, deploy commands —
read [`AI_HANDBOOK.md`](AI_HANDBOOK.md) instead. This file is for understanding;
that one is for changing things.

---

## The one thing that confuses everybody

There are three things people call by different names, and they are all **the
same program on the same machine**:

```
                 YOUR HOME SERVER   192.168.99.56
                 ==================================
                 one program: relay.py
                 one URL:  wikipedia.tail06361a.ts.net/ai
                 |
  AI requests --->|  /v1/chat/completions   (adds the secret key, asks Groq)
  the room ------>|  /v1/presence           (who is playing right now)
  answers ------->|  /v1/answer             (replies going back)
  questions ----->|  /v1/send-question      (operator only, needs a token)
                 ==================================
```

So "the AI proxy" and "the relay" are not two systems. When someone says *"the
relay"* they might mean the **program** (`relay.py`) or the **job it does**
(sitting in the middle passing messages). Usually it is both at once.

The practical consequence: **one deploy restarts everything.** AI, room,
questions and effects all update together, because they are one process.

---

## 1. Why the AI goes through your home server

This is the key-protection design, and it is the most important thing to
understand.

### The problem

The game needs an AI to generate questions. That needs a Groq API key. If that
key were inside the download it would be:

- sitting on every player's disk,
- extractable in about a minute (unzip, search for strings, done),
- free for anyone to drain — your bill, their entertainment.

### The solution

The key never leaves your house.

```
 player's game              YOUR home server                 Groq
 -------------              ----------------                 ----
 "generate a question"  ->  checks the request is sane
                            ADDS the secret key  ----------> api.groq.com
                            forwards the reply      <------  (the answer)
```

The game holds **no key at all**. The download literally sends the word
`"relay"` where a key would go — a placeholder. The real key is added by your
server, at the last moment, on the way out.

The key lives in one file on your server (`/opt/tqg-relay/relay.env`), readable
only by root. Even your own day-to-day account cannot read it. It is never in
git, never in a build, never in a chat.

### It is also a bouncer, not just a curtain

Hiding the key is not enough on its own — someone could still hammer your server
and burn your quota. So the server also:

- **ignores the model the client asked for** and forces its own;
- **caps the conversation** (12 messages, 8000 characters each);
- **caps the output length**;
- **strips unknown fields** — only role and content survive;
- **rate-limits per IP**, answering `429 slow down`.

So it says: *I will talk to Groq for you, but only on my terms.*

### Is that safe?

Yes. The server holds the secret, the client holds nothing. A player can use the
AI; they cannot take the key. This is a standard pattern.

**One honest caveat.** The AI endpoint is currently open — anyone who has the
URL can use it, limited by rate limiting only. That is a *quota* risk, not a key
leak. There is an optional shared-secret switch (`RELAY_APP_TOKEN`) that is off
by default.

---

## 2. Why the room needs a middleman

Two players' computers cannot find each other. No public addresses, firewalls in
the way, and one of them might be on a phone hotspot. So instead of talking to
each other, **everyone talks to your server**, and it hands messages over.

```
   player A ---\
                \
                 >--- YOUR home server (remembers who is around)
                /
   player B ---/
```

What the server knows:

- **who is playing** — a list of names, refreshed every few seconds;
- **questions waiting** to be picked up, held for 15 minutes at most;
- **answers** on their way back to whoever asked;
- **effects** waiting to be played.

What it deliberately does **not** have: a database, accounts, passwords, or
history. The room is **in memory only**. Restart the server and everyone is
gone. There is nothing to leak because nothing is stored.

Two rules worth knowing:

- **One-shot delivery.** An item is deleted the moment it is handed over, so a
  question is never replayed. A player who quits before seeing it loses it —
  which is better than replaying old questions for ever.
- **Peers expire.** Stop polling for 20 seconds and you drop off the list.

---

## 3. The sender/receiver split

This is the rule that keeps the fiction intact.

| Half | Who has it | What it can do |
|---|---|---|
| **Receiver** | everyone's download | be seen, see the room, answer questions |
| **Sender** | the operator only | write questions, fire effects |

Only the operator's separate sender app can **write** — because only it holds
the send token. Every download is a receiver, and the shipped game has **no code
path that could send a question at all**, even if someone decompiled it.

Why bother? Because it means the game can only say things *you* wrote. Nobody
can make the game ask something you did not compose. The relay enforces this
before it even looks at the contents of a message.

### Two secrets, easily mixed up

| Secret | Lives where | Protects | In the download? |
|---|---|---|---|
| The AI key | your server only | **your money** | never |
| The send token | your token file + the sender app | **the fiction** | never |

The AI key stops strangers spending your money. The send token stops strangers
writing your game's words. Different jobs, both server-side, neither shipped.

---

## 4. What a player's game actually does

On the ONLINE screen the game checks in with the room every few seconds. That
check-in is also the delivery mechanism: the reply carries anything waiting —
a question, an effect, an answer to something you sent.

The player sees:

- whether the relay is reachable (`ONLINE`, `RECONNECTING...`, `OFFLINE`);
- who else is in the room — **players only**; the operator is hidden, so nothing
  hints that someone is watching;
- the name the room knows them by, which they can change;
- a connection test, and a count of how many times a dropped link recovered;
- lobby placeholders, clearly marked as not working yet.

### A question from the room is a total secret

This is deliberate and easy to break by accident. A hand-written question:

- arrives **without warning** — no toast, no sound, no popup;
- carries **no label** — it does not say who wrote it;
- is **not counted** anywhere;
- **looks exactly like** a generated question, and sits in the queue like one.

The point is that the player cannot tell which questions were written for them,
or that anyone is there at all. Do not add a "someone sent you a question!"
notice. It is the fastest way to break the feature.

### Firing an effect by hand

The operator can also trigger the game's own scares — a flicker, a whisper, a
screen tear — without writing a question. They arrive the same way and are
equally unannounced: the game plays them exactly as if it had chosen them
itself. The intensity dial controls how **long** the effect lasts.

---

## 5. The settings screen

The settings are seven tabs: `AUDIO`, `VIDEO`, `GRAPHICS`, `GAMEPLAY`,
`ACCESSIBILITY`, `CONTROLS` and `OTHER`. Everything in them is written to the
save file and comes back on the next run.

- **AUDIO** — master, sound-effect, ambience and music volumes, each with a
  mute. The player's volume and the game's own level are kept apart and
  multiplied, so the game can still duck the effects under the music without
  ever making the music louder than the player asked for.
- **VIDEO** — fullscreen, vsync, the window resolution, and the UI scale. The
  UI scale is a real scale: the game is drawn at another resolution and
  stretched to the window, so the text and the layout grow together.
- **GRAPHICS** — a performance preset, a CRT switch with its own intensity,
  and a toggle for every post-processing layer (scanlines, vignette, dust, the
  static line, tube curvature, the phosphor mask). `Low` turns the expensive
  layers off by itself.
- **GAMEPLAY** — font, text speed, text size, text sway and the AI source.
- **ACCESSIBILITY** — reduce flashes, disable screen shake, disable webcam
  scares. These are honoured in one place, the scare system, so no effect can
  slip past them. "Disable screen shake" also stops the *window* from
  moving, not just the picture inside it.
- **CONTROLS** — rebind up, down, confirm and back/pause. A rebind that would
  shadow another action is rejected, not accepted silently.
- **OTHER** — the VHS effects, and the reset.

`ESC` during the game opens a pause menu: resume, settings, main menu, exit.

---

## 6. The eye

There is an eye in the corner of the screen the whole time you play. It is not
an option and there is no switch to turn it off — that is the point of it.

It is drawn in the game's own colours: a white almond, a black iris, a black
pupil, a hard black ring around it. Nothing else. It blinks at irregular
intervals, and it is always watching something.

**What it watches.** Mostly you. Move the mouse and the pupil follows. When a
menu option is highlighted, it turns and looks straight at that option. It
sits in the bottom-right corner in the menus and moves to the top-right when
the game starts, out of the way of the text.

**When a scare fires** — a flicker, a corruption, a whisper, anything the game
does to scare you — the eye blinks far more often and its iris turns red. It
watches you get scared.

**It keeps score.** Answer the same thing twice in a row and the pupil
contracts and holds that stare. Do it a third time and the eye swells and
flushes red. Hesitate on a question for long enough and it widens instead. It
is counting.

**Later sessions are worse.** The eye blinks faster, wanders more, and its
pulse gets wider.

**At the end of the session** the corner eye steps aside and **one big eye
takes over the whole screen**, sitting behind the text and staring out at you.
That is the last thing you see before the game closes.

### The eye on your desktop

On **Windows and macOS**, when you click away from the game window, a small
borderless window with an eye in it appears on your desktop and follows your
cursor around — into other windows, across the screen. It cannot be clicked
on, and it goes away the moment you go back to the game.

**Linux does not get the desktop version.** Wayland, the display server most
Linux desktops use, deliberately keeps the pointer position private and does
not let applications read it. There is no way around that and there never will
be. The in-game eye still works on Linux: it follows the cursor, and it keeps
following it even when the cursor leaves the game window, so the pupil slides
to the edge of the iris and stares out of the screen at wherever you went.

---

## 7. Where everything runs

| Thing | Where |
|---|---|
| The website | GitHub Pages, served from the repo root |
| The game (all editions) | each player's own machine |
| The AI proxy + relay | your home server, one program |
| The operator sender | your machine |

The server is reached through a **Tailscale Funnel** — a secure tunnel that
publishes one local port to the internet without opening anything else. Locally
it listens on `127.0.0.1:8090`; the funnel forwards the public URL to it.

**After changing the server code you must redeploy it.** Editing the file in git
does not change the program that is running. Run `./server/push_relay.sh` (it
needs your password) or copy the file and restart the service by hand.

---

## 8. Common misunderstandings

- *"The AI and the relay are different servers."* No — one program, one machine.
- *"The API key is in the game somewhere."* No. The download holds no key.
- *"Players can write questions, they just do not have a UI for it."* No. There
  is no send path in the download at all.
- *"I changed the relay, so it is live."* Only after a redeploy and restart.
- *"Restarting the server loses the questions."* Correct — the room is memory
  only. There is no history to recover.
- *"The operator shows up in the room, that is fine."* It is not. The operator is
  filtered out on purpose.
