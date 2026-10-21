# The Question Game — handbook for AI agents

Everything a future agent needs to work on this repo without rediscovering it:
what the games are, how the online feature is split, how to build and release,
how to deploy the relay, and the traps that have already cost us hours.

Read this before changing code. It is the shortest path to understanding the
project; the source is the ground truth when the two disagree.

---

## 1. What this project is

**The Question Game** is a text-based horror game: it asks, you answer, and it
notices what you said. It has grown into three games plus the website, all in
one repo.

| edition | where | what it is |
|---|---|---|
| **Classic** | `games/classic/` | the original game (2026). The reference implementation; the remastered edition ports its mechanics. |
| **Remastered** | `games/remastered/` | the current flagship. Same story, but the questions are improvised live by an AI that remembers your answers across runs, plus VHS/CRT visuals, OS-level scares (camera, wallpaper, window drift) and the optional multiplayer room. |
| **The Simpler Times (1993)** | `games/firstcopy/` | a prequel. Only pygame + numpy. Not built or shipped by CI. |
| **Legacy 2000 site** | `legacy.html` | a plain-HTML page for browsers without JavaScript (IE 11). It mirrors the download links and must stay in sync with the version numbers. |

The website (`index.html` + `js/` + `css/`) is served straight from the repo
root by GitHub Pages. Pushing to `main` publishes it.

The tone of everything (code comments, page copy, release notes) is dry,
lowercase-leaning and slightly menacing. Match it.

---

## 2. Repository map

```
index.html  legacy.html  css/  js/  img/     the website (GitHub Pages, repo root)
forum-reactions.json  bossfight.mp3  jumpscare.mp3  windowq.png  logsmusic.ogg
                                               shared build assets (site + game bundles)

games/
├── classic/      the original game           → python games/classic/TheQuestionGame.py
├── remastered/   the flagship                → python games/remastered/run_remastered.py
│   ├── TheQuestionGameRemastered/           the game package
│   ├── TheQuestionGameRemastered.spec       PyInstaller spec (Windows)
│   ├── TheQuestionGameRemastered-linux.spec PyInstaller spec (Linux, one-file)
│   ├── tests/smoke_test.py                  headless end-to-end test
│   └── ANDROID.md  REMASTER_PLAN.md
└── firstcopy/    The Simpler Times (1993)    → python games/firstcopy/run_firstcopy.py

server/           the AI + social relay (stdlib only) + its systemd unit
tools/sender/     the OPERATOR SENDER — never published, never linked
build/            py2app scripts (macOS) + CI requirements files
docs/             this handbook
archive/          frozen pre-reorg snapshot (not built, not served)
```

`archive/` is dead weight — do not touch it unless asked.

---

## 3. The remastered edition, internally

Entry point `games/remastered/run_remastered.py` → package
`games/remastered/TheQuestionGameRemastered/`:

| module | responsibility |
|---|---|
| `main.py` | the game loop, the screen state machine, the frame/display split (see §8) |
| `config.py` | every tunable, every env var, `VERSION`, asset paths |
| `ui.py` | all rendering: text, panels, CRT/VHS overlays, cursor, icons |
| `script.py` | the authored question bank and the session script |
| `ai_client.py` | the AI providers (relay first, then groq/openrouter/openai/deepseek/ollama), the offline fallback bank |
| `social.py` | the online room client: presence, inbox, answering |
| `persistence.py` | run count, answers, badges, settings (`~/.tqgame_remastered/game_state.json`) |
| `scares.py` | local effects the AI may trigger (camera, wallpaper, window drift, noise…) |
| `os_layer.py` | process detection (Discord, Task Manager), location lookup, camera access |
| `audio.py`, `sfx_gen.py`, `interjections.py` | sound, procedurally generated SFX, one-off interjections |

Everything is tunable through `config.py`; **do not hardcode behaviour in
`main.py`** that belongs in config.

Persistence lives in `config.get_appdata_dir()`:
`%APPDATA%/TQGameRemastered` (Windows),
`~/Library/Application Support/TheQuestionGameRemastered` (macOS),
`~/.tqgame_remastered` (Linux). `TQG_DATA_DIR` overrides it (used by tests).

---

## 4. The multiplayer split — the most important rule in this repo

The online feature has **two halves**, and only one of them may ever be
published.

```
                    ┌──────────────────────────────────────────┐
                    │  the game (everyone's download)          │
                    │  RECEIVER: joins the room, plays the      │
                    │  questions it is sent, reports answers   │
                    └───────────────────┬──────────────────────┘
                                        │ POST /v1/presence
                                        │ POST /v1/answer
                                        v
   ┌──────────────────────────────┐   ┌───────────────────────────────┐
   │ tools/sender/sender.py       │──▶│ server/relay.py  (the relay)  │
   │ the OPERATOR SENDER          │   │ POST /v1/send-question        │
   │ WRITER: composes questions   │   │ requires X-Send-Token         │
   │ holds TQG_SEND_TOKEN         │   └───────────────────────────────┘
   └──────────────────────────────┘
```

**The rule:** the shipped game may only *receive and answer*. Writing lives in
`tools/sender/sender.py`, which is the only thing in the repo that reads
`TQG_SEND_TOKEN`. Nothing that is published may carry a send token, and the
sender must never be linked from the website, added to a release, or bundled
into a build.

The relay enforces the split server-side: `/v1/send-question` refuses any
caller that does not present `RELAY_SEND_TOKEN` as `X-Send-Token` before it
even reads the body. Presence and answering are open to every copy of the game
by design — the room is for players, not for megaphones.

`tools/sender/` is in the repo and is fine there. It is **not** in any release
and **not** on the site. If you ever find yourself adding a sender download
link, stop.

### The operator's sender app

```sh
TQG_SEND_TOKEN=... python tools/sender/sender.py
```

It is a small pygame program (not a game — a menu): it joins the room under
its own operator identity, lists who is online, and lets the operator compose
a question (text + up to four options + which one is correct) and fire it at
one player or at everyone. It shares the game's `config`/`ui`/`social` modules
by putting `games/remastered` on `sys.path` — it is meant to be run straight
from a checkout. See `tools/sender/README.md`.

#### Getting the token

The relay's `RELAY_SEND_TOKEN` lives in `/opt/tqg-relay/relay.env` on the relay
host, which is **root-only (0600)** and the host has **no passwordless sudo** —
so the operator has to fetch it:

```sh
ssh nept@192.168.99.56 "sudo grep RELAY_SEND_TOKEN /opt/tqg-relay/relay.env"
```

That is the only way in. Do not try to move the file, loosen the permissions, or
add the operator to a sudoers file to make it easier — the root-only file is
the point.

#### The token gate, and how the app proves it works

`POST /v1/send-question` checks the token **before** it validates the body.
So an empty body `{}` is rejected by *validation* only after the token gate has
already let the caller through:

| reply | meaning |
|---|---|
| `400` | the token is **good** (the body was the problem) |
| `403 {"error":"sending is restricted"}` | the token is **wrong** |
| connection refused / timeout | the relay is unreachable |

That makes a safe, non-destructive probe: it never sends a question, it never
writes to the room. `sender.probe_token()` uses it, and the app runs it when it
starts (if a token is already known) and whenever one is typed in.

#### The token is not only in the environment

The app asks for the token if it does not have one:

- `TQG_SEND_TOKEN` in the environment wins. An **explicitly empty** env var
  means "no token" — it does *not* fall back to the saved file (the tests rely
  on this).
- otherwise the token is read from `<appdata>/sender_token` (0600, written
  atomically). On Linux that is `~/.tqgame_remastered/sender_token`.
- otherwise the app shows the token screen and waits. Paste the token, press
  ENTER: it is probed, and only kept if the relay accepts it.
- `CTRL+X` clears the token (from memory and from disk).

#### Delivery is reported honestly

`SocialClient.send_question()` returns `True` when the question was **queued**,
not when the relay accepted it. The old sender therefore showed "SENT TO …" on
a 403 or on an empty room. The fix is a separate outcome channel:
`social.py` records the relay's real answer (`ok`, `to`, `q`, `qid`,
`delivered`, `error`) and the sender drains it with `take_send_outcomes()`.

The sender's DELIVERY panel then says what actually happened: `DELIVERED TO 1
PLAYER`, `REFUSED` (the token is wrong), `NOBODY` (no one to send to), `NOT
SEEN` (the relay has not polled you yet), `FAILED`. The compose form is only
cleared **after** a confirmed delivery, so a refused send never eats the
operator's question.

### The room protocol

| endpoint | who may call it | what it does |
|---|---|---|
| `POST /v1/presence` | anyone | heartbeat. Returns the online list, questions addressed to you, and results for questions you sent. |
| `POST /v1/send-question` | only with `X-Send-Token` | deliver a question to one peer or to `"all"`. |
| `POST /v1/answer` | anyone | report a recipient's answer back to the question's author. |

Delivery is **one-shot** — the server clears an item as it hands it over, so a
question is never replayed. Items expire after `RELAY_QUESTION_TTL` (900 s) and
a peer drops off the list after `RELAY_PEER_TTL` (20 s) without a poll.

Tunables on the server: `RELAY_SEND_TOKEN`, `RELAY_PEER_TTL`,
`RELAY_QUESTION_TTL`, `RELAY_INBOX_MAX`, `RELAY_RESULT_MAX`,
`RELAY_SOCIAL_RATE`, `RELAY_SOCIAL_BURST`.

### The receiving side, in the game

The shipped game's `ONLINE` menu entry is the receiver's window onto the room.
It shows the relay's state, the name the room knows the player by, and who
else is playing. The player can rename themselves there (`N`), which is
persisted in the save file and pushed into the room by the presence client.

It used to be a fake compatibility check that ended in "MULTIPLAYER IS NOT
SUPPORTED" — that was true for v4 and is false for v5.0.0, where this build
*is* in the room and can receive. If you touch that screen, keep it honest:
the game may look at the room and answer, but it must never write to it.

---

## 5. The AI relay

The game ships with **no API key**. It posts its chat-completions request to
Neptune's relay, which holds the key and forwards to Groq. That is why a fresh
download needs no setup and why the key can be rotated without re-releasing the
game.

```
player's game ──HTTPS──> tailscale funnel ──> relay :8090 ──> Groq
                             /ai prefix
```

`server/relay.py` is stdlib only. It is not an open door to the key:

- the model is fixed (`RELAY_MODEL`), callers cannot pick a pricier one
- `max_tokens` is capped at `RELAY_MAX_TOKENS`
- only `messages`, `temperature`, `max_tokens`, `reasoning_effort` are forwarded
- conversations are capped (12 messages, 8000 chars each)
- rate limited per IP (`RELAY_RATE`/min, `RELAY_BURST` spike allowance)
- optional shared app token (`RELAY_APP_TOKEN` → `X-App-Token`)
- the social endpoints are rate limited separately and move question-sized
  payloads only

Treat `RELAY_APP_TOKEN` as a speed bump, not a secret: it is extractable from
any build. The real protections are the model lock, the token cap and the rate
limit.

### The relay host

The relay runs on Neptune's home server:

```
ssh nept@192.168.99.56
```

- source of truth: `server/relay.py` in this repo
- deployed copy: `/opt/tqg-relay/relay.py`, config `/opt/tqg-relay/relay.env`
- systemd unit: `/etc/systemd/system/tqg-relay.service` (`tqg-relay.service`)
- service listens on `127.0.0.1:8090`; Tailscale Funnel exposes it publicly at
  `https://wikipedia.tail06361a.ts.net/ai`
- **the running service does not pick up changes on its own.** After editing
  `server/relay.py`, push it:

```sh
./server/push_relay.sh          # or: TQG_HOST=nept@192.168.99.56 ./server/push_relay.sh
```

`push_relay.sh` copies the file, restarts the unit, and checks `/health`
locally, through the funnel, and does a presence round-trip.
`server/deploy.sh` (run with sudo on the host) does the first-time install.

`server/relay.env` holds `RELAY_KEY` and is gitignored. **Never commit it.**

---

## 6. Environment variables

### The game

| var | default | meaning |
|---|---|---|
| `TQG_RELAY_URL` | the public relay `/ai/v1/chat/completions` | where AI questions go |
| `TQG_RELAY_TOKEN` | *(empty)* | shared app token, if the relay requires one |
| `TQG_AI_PROVIDER` | `relay` | `relay` / `ollama` / `openrouter` / `groq` / `openai` / `deepseek` / `offline` |
| `TQG_GROQ_KEY` etc. | *(empty)* | bring-your-own keys; empty by default so no key ships |
| `TQG_OLLAMA_HOST` | `http://localhost:11434` | local model host |
| `TQG_SOCIAL` | `1` | `0` disables the whole online feature |
| `TQG_SOCIAL_URL` | same host as the relay | the room endpoint |
| `TQG_SOCIAL_POLL` / `TQG_SOCIAL_TIMEOUT` | `4` / `6` | poll cadence and timeout (seconds) |
| `TQG_DATA_DIR` | platform appdata | override the save directory (tests use it) |
| `TQG_SEND_TOKEN` | *(absent)* | **operator sender only.** Must never be set in a shipped build. |
| `TQG_SENDER_NAME` | `OPERATOR` | the name the sender shows up under in the room |

The sender also keeps its token in `<appdata>/sender_token` (0600). The
environment wins over the file; an explicitly empty env var means "no token".

### The relay (`server/relay.env`)

`RELAY_KEY` (required, secret), `RELAY_APP_TOKEN`, `RELAY_SEND_TOKEN`,
`RELAY_PORT` (8090), `RELAY_MODEL`, `RELAY_MAX_TOKENS`, `RELAY_RATE`,
`RELAY_BURST`, `RELAY_TIMEOUT`, `RELAY_PEER_TTL`, `RELAY_QUESTION_TTL`,
`RELAY_INBOX_MAX`, `RELAY_RESULT_MAX`, `RELAY_SOCIAL_RATE`,
`RELAY_SOCIAL_BURST`.

---

## 7. The website

- `index.html` — the whole page (structure + copy). `js/main.js` — behaviour.
- The download card resolves releases **at runtime** from the GitHub releases
  API: it looks up the tag `REMASTER_TAG` (in `js/main.js`) and picks the
  assets out of that release. `FALLBACKS` in `js/main.js` holds the direct
  links used when the API is unreachable.
- `legacy.html` mirrors the download links for old browsers.
- The site is served from the repo root; `css/`, `js/`, `img/` and the shared
  media files must stay where they are.

### Version consistency is enforced

`server/test_site.py` fails the build if:

- `config.VERSION` and the tag in `js/main.js` disagree,
- `index.html` / `legacy.html` do not show the current version,
- any remastered download link points at an old tag,
- a download link's tag does not match the game version,
- the release dom maps in `js/main.js` pass bare ids to the `$` helper instead
  of selectors (`"#remRelVersion"`), which silently unwires the card,
- an API key is committed to the site,
- the VHS layers are missing, or the removed "tilt" effect creeps back in,
- the site repeats claims that were disproven (e.g. "the classic edition never
  activates a camera" — it does, on purpose).

**Run it after every site change:**

```sh
python3 server/test_site.py     # prints SITE_OK
```

When you bump the version you must touch all of: `config.py` `VERSION`,
`js/main.js` `REMASTER_TAG` + `FALLBACKS`, `index.html` (HUD label, hero badge,
release card, footer, history entry), and `legacy.html`.

---

## 8. The Wayland trap (read this before touching the renderer)

This cost us a full day. The game worked, the audio worked, the keyboard
worked, and the window was **black**.

**Cause.** The drawing frame used to be created with `.convert()`, i.e. in the
*window's* pixel format. Under Wayland the window surface is 32-bit **ARGB**
(one alpha byte per pixel); under X11 it is 24-bit, with no alpha at all. The
alpha overlays the game paints every frame (VHS scanlines, vignette, CRT mask,
snow) write the destination's alpha bytes, so the frame's alpha was wiped to
zero across the whole screen. The final copy onto the window then multiplied
the picture by that alpha (`dst_rgb = src_rgb * src_alpha`) — so the GUI never
reached the screen. X11 has no alpha channel, so the bug never showed there.

**Fix (in `main.py`):**

- `_new_frame()` builds a **24-bit** frame (`pygame.Surface(size, 0, 24)`) —
  there are no alpha bytes to wipe, so no overlay can make the frame
  transparent.
- `_make_window_opaque(disp)` paints the window surface opaque once per
  surface object (SDL hands the Wayland window over with its alpha cleared,
  which is a transparent window).
- the resize path scales into an alpha-free intermediate
  (`pygame.transform.smoothscale`) instead of scaling straight into the window
  surface, which would hand it a fresh transparent alpha channel.

**Rules that follow from it:**

- Never `convert()` the drawing frame to the display format.
- Never blit an alpha-carrying overlay onto the frame.
- `pygame.surfarray.array_alpha()` returns a fake `{255: n}` for surfaces
  without the `SRCALPHA` flag — it cannot be used to inspect a converted
  32-bit frame, and it will hide exactly this class of bug.

The smoke test pins all of this (§10).

---

## 9. Building and releasing

### CI does the shipping

`.github/workflows/`:

| workflow | builds |
|---|---|
| `build-linux-remastered.yml` | `TheQuestionGameRemastered-linux.tar.gz` |
| `build-windows-remastered.yml` | `TheQuestionGameRemastered.zip` |
| `build-mac-remastered.yml` | `TheQuestionGameRemastered-macOS.dmg` (py2app) |
| `build-linux-classic.yml`, `build-mac.yml` | the classic edition |
| `test-remastered.yml` | the smoke test |
| `forum-cache.yml` | the forum cache |

The remastered workflows trigger on **`release: published`** when the tag
contains `remastered` (and can also be dispatched by hand). So the release
process is:

1. bump the version (see §7) and commit;
2. push to `main`;
3. create the GitHub release with the tag `vX.Y.Z-remastered` and publish it —
   CI then builds and uploads the three desktop assets to that release;
4. the site picks the release up on its next page load.

Asset names are fixed and the site depends on them:
`TheQuestionGameRemastered.zip`, `TheQuestionGameRemastered-macOS.dmg`,
`TheQuestionGameRemastered-linux.tar.gz`.

### Android

Built by hand with buildozer (`games/remastered/build_android.sh`), not by the
release workflows. The last APK was `v4.0.0-remastered`. The v5.0.0
multiplayer alpha is **desktop only** — there is no APK for it and the site's
Android card deliberately offers no link. See `games/remastered/ANDROID.md`.

### Locally

```sh
pip install pyinstaller -r build/requirements-linux.txt
pyinstaller --clean --noconfirm games/remastered/TheQuestionGameRemastered-linux.spec
```

The specs resolve paths against the **current working directory**, so run
PyInstaller from the repo root.

---

## 10. Testing

```sh
# the game, headless, against dummy drivers — the one test that matters
python3 games/remastered/tests/smoke_test.py       # prints SMOKE_OK

# the website: version drift, release wiring, banned claims
python3 server/test_site.py                        # prints SITE_OK

# the relay and the sender
python3 server/test_relay.py
python3 tools/sender/test_sender.py
```

The smoke test drives the real game against a dummy display and asserts on
behaviour, not on internals: the question pipeline, the offline bank, the
scare floor, the online screen, the relay default, "no API key ships in the
build", and the window-opacity rules from §8. If you change rendering or the
frame/display split, add an assertion there — that is how the black window
stays fixed.

---

## 11. Working rules for agents

1. **Read `git log` before changing behaviour.** Most surprises have a commit
   that explains them; the comment at the top of a file usually names the
   commit.
2. **Never publish the sender.** Not in a release, not on the site, not in a
   build, not in a zip. If a feature needs it, it is an operator feature and it
   stays in `tools/`.
3. **Never commit a key.** The game ships without one on purpose. The relay
   holds it. `server/relay.env` is gitignored.
4. **Run the tests.** `smoke_test.py` and `test_site.py` are cheap and they
   catch the two classes of mistake that otherwise reach a player.
5. **Bump versions in all the places listed in §7**, or the site will link to a
   release that does not exist.
6. **Keep the tone.** The copy is dry and slightly menacing; the comments are
   honest about *why* something is the way it is. Both are part of the product.
7. **Do not "fix" the scares.** The camera, the wallpaper, the window drift,
   the blocked close button — they are the game. The site discloses them.
8. **When you are unsure, ask.** The maintainer knows which quirks are
   deliberate; the comments say so too.

---

## 12. Quick reference

```sh
# play
python3 games/remastered/run_remastered.py

# test
python3 games/remastered/tests/smoke_test.py
python3 server/test_site.py
python3 server/test_relay.py
python3 tools/sender/test_sender.py

# deploy the relay
./server/push_relay.sh

# operate the room (needs the token)
ssh nept@192.168.99.56 "sudo grep RELAY_SEND_TOKEN /opt/tqg-relay/relay.env"
TQG_SEND_TOKEN=... python3 tools/sender/sender.py

# releases
gh release list
gh release view v5.0.0-remastered --json assets
```

Current versions: game **5.0.0** (multiplayer alpha, receiver build),
classic **2.02**, site tag `v5.0.0-remastered`.
