# The Question Game — handbook for AI agents

Everything a future agent needs to work on this repo without rediscovering it:
what the games are, how the online feature is split, how to build and release,
how to deploy the relay, and the traps that have already cost us hours.

Read this before changing code. It is the shortest path to understanding the
project; the source is the ground truth when the two disagree.

Companion docs:

- [`HOW_IT_WORKS.md`](HOW_IT_WORKS.md) — the plain-language explanation of the
  AI, the relay, the room and the home server, for a human reader. Point people
  here when they ask "wait, which server is which?".
- [`../CHANGELOG.md`](../CHANGELOG.md) — what changed and when. Add an entry
  when you ship something a player or the operator would notice.

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
| `os_layer.py` | process detection (Discord, Task Manager), location lookup, camera access, global cursor + window bounds |
| `eye_overlay.py` | the desktop eye: a separate borderless overlay process (Windows/macOS) |
| `audio.py`, `sfx_gen.py`, `interjections.py` | sound, procedurally generated SFX, one-off interjections |

Everything is tunable through `config.py`; **do not hardcode behaviour in
`main.py`** that belongs in config.

Persistence lives in `config.get_appdata_dir()`:
`%APPDATA%/TQGameRemastered` (Windows),
`~/Library/Application Support/TheQuestionGameRemastered` (macOS),
`~/.tqgame_remastered` (Linux). `TQG_DATA_DIR` overrides it (used by tests).

### The watching eye

Since v6.0.0 there is an eye in the corner of the screen at all times. There
is **no toggle** and there must not be one — it is the feature.

| Piece | Where |
|---|---|
| the drawing | `ui.draw_eye()` — line-art almond lids, one iris ring, black pupil. Procedural, no art assets |
| where it sits | `main._eye_anchor()` — bottom-right in the menus, top-right in `PLAYING`/`EXITFADE` |
| what it looks at | `main._eye_look_target()` — the cursor if it left the window, else the highlighted option, else the player |
| the highlight rect | `_eye_focus_rect`, declared by the screen that drew the selection (title, settings, about, online, pause, answer options) |
| the pupil | `main._eye_state["pupil_x"/"pupil_y"]`, smoothed towards the target at ~0.30/frame |
| blinking | `main._eye_state["next_blink"/"blink_until"]` — 3.5–11s calm, 0.12–0.35s during a scare |
| the scare reaction | `main._eye_scare_active()` reads the `fx` timers, so it covers every scare without naming them |
| the answer reaction | `main._eye_react_to_answer()` — same answer twice → the pupil tightens; three times → it flushes red; a long hesitation → it broadens slightly |
| the pulse | `main._eye_dilation()` — a slow, deliberately small sine swell |
| the ending | `main._draw_end_eye()` — at the end of the session one big eye takes over the whole screen, drawn *before* the text so the text sits on top of it |

The eye is line art in the game's black-and-white language: two almond lid
outlines, a single dark-red iris ring, and a black pupil. There is no filled
sclera, so the scene shows through the middle. Only the scare state and the
"accuse" reaction turn the iris red.

**The look order matters.** The cursor wins only after it leaves the window.
Inside the window the eye reads `_eye_focus_rect`; if a screen set no rect it
looks straight out at the player. Each drawing screen sets the rect from the
surface it actually blitted, so scrolling Settings and answer blocks whose
height depends on the question stay correct. Do not replace this with a
hardcoded per-screen position; that is what made the old eye miss the target.

**The desktop overlay.** On Windows and macOS the game re-executes itself with
`--eye-overlay`, which runs `eye_overlay.main()` in a second process: a
borderless, always-on-top, click-through window with an eye in it that trails
the cursor across the whole desktop. It appears when the game window loses
focus and disappears when it gets it back. `main._supervise_overlay()` starts
it and restarts it if it dies; `run()` kills it on exit.

**The overlay is Windows and macOS only. Do not add it to Linux.** Wayland
compositors deliberately keep the pointer position private and there is no API
that exposes it; X11 does expose it, and `os_layer._query_global_cursor_x11()`
uses that for the in-game eye so the pupil keeps following the cursor off the
edge of the window on Linux too.

Every overlay failure path degrades to "no overlay". It must never crash the
game — the overlay is a toy, the game is not.

### The CRT tube

`ui.apply_vhs_curvature()` is one continuous 2D warp, not a stack of scaled
horizontal strips. It builds two float32 source-coordinate maps once per frame
size and strength (`_build_vhs_curve_maps()`) and feeds them to `cv2.remap()`
with bilinear sampling. The curve is:

    src = n * (1 - k * (1 - n^2) * (1 - m^2))

where `n` is the axis being sampled and `m` the other axis. The `(1 - n^2)`
term pins the outer frame (`src == n` at the edge), so the warp bends the
picture inward but never samples outside the surface. That is deliberate: the
eye sits near the top-right corner and an earlier non-edge-preserving map cut
it in half. Black rounded corners are *not* worth losing content for.
`config.CRT_CURVE_Y_RATIO` scales the vertical strength.

Use plain float32 maps. Do not use `cv2.convertMaps(..., CV_16SC2)`: its
return shape changed between OpenCV 4.x and 5.x, and a mismatched second map
silently produced a nearly black frame. The float path works on both.

OpenCV is imported lazily. It is in every packaged build, but a source
checkout without it still runs: `_apply_vhs_curvature_bands()` is the old
26-strip fallback, used only when `cv2` is missing or the frame surface cannot
be read. A window resize defers the map rebuild for ~0.18s and uses the cheap
fallback in the meantime, so dragging the edge does not hitch.

Do not go back to per-strip `pygame.transform.scale()` for the normal path:
integer strip widths are what produced the visible seams that cut through
text and vertical lines. The 24-bit frame's BGR buffer is read directly in the
fast path; other surface formats fall back to `pygame.image.tobytes()`.

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

The app asks for the token if it does not have one, searching in order:

1. `TQG_SEND_TOKEN` in the environment. An **explicitly empty** env var means
   "no token" — it does *not* fall back to anything else (the tests rely on
   this).
2. `<repo>/tqg-token.txt` — the plain hand-edited file the maintainer uses. It
   is gitignored, and it **must stay gitignored**: it was committed once by
   accident (see "the token leak" below). `_read_token_file()` also tolerates a
   `RELAY_SEND_TOKEN=...` line.
3. `<appdata>/sender_token` (0600, written atomically). On Linux that is
   `~/.tqgame_remastered/sender_token`.
4. Nothing — the app shows the token screen and waits. Paste the token, press
   ENTER: it is probed, and only kept if the relay accepts it.
5. `CTRL+X` clears the token (from memory, from the appdata copy and, from
   v5.0.0 on, from `tqg-token.txt` too).

#### The token leak (2026-10-22) — read this before touching tokens

The live send token was committed to `tqg-token.txt` in `375a038` and pushed to
the public `main`. Anything that reads the public history can send questions into
the room. The remedies applied:

- the file is untracked and listed in `.gitignore`;
- the app no longer needs it in git at all — it reads the gitignored copy;
- **the operator must rotate `RELAY_SEND_TOKEN` on the host** (edit
  `/opt/tqg-relay/relay.env`, restart `tqg-relay`), because a secret that has
  been public is a dead secret. Rotating is the fix; purging git history is
  optional and would rewrite every commit after `375a038`.

If you ever add a token to any file: check `git status` and `.gitignore` first.

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
| `POST /v1/presence` | anyone | heartbeat. Returns the online list, questions addressed to you, results for questions you sent, and any effects fired at you. |
| `POST /v1/send-question` | only with `X-Send-Token` | deliver a question **or an effect** to one peer or to `"all"`. |
| `POST /v1/answer` | anyone | report a recipient's answer back to the question's author. |

Delivery is **one-shot** — the server clears an item as it hands it over, so a
question is never replayed. Items expire after `RELAY_QUESTION_TTL` (900 s) and
a peer drops off the list after `RELAY_PEER_TTL` (20 s) without a poll.

`/v1/send-question` carries two shapes of body. With `"q"` + `"opts"` it is a
question. With `"effect"` it is a scare the operator fires by hand; the relay
dispatches it to `_handle_send_effect` (same route, same token gate, its own
`_effects` store) and presence returns it under `"effects"`. The receiver plays
it through `scares.apply_scare`, so it is indistinguishable from the model
choosing that effect itself: no toast, no note, nothing. `"intensity"`
(default 1.0, clamped to `[0.1, 2.0]`) scales how long it lasts via
`game.fx["scare_scale"]`, which `apply_scare` applies by scaling the clock the
scare sees. An unknown effect name is **refused with 400**, not silently
dropped — `relay.EFFECT_NAMES` mirrors `scares.SCARE_REGISTRY` (the relay is
deployed separately and cannot import it, so keep the two lists in step).

Tunables on the server: `RELAY_SEND_TOKEN`, `RELAY_PEER_TTL`,
`RELAY_QUESTION_TTL`, `RELAY_INBOX_MAX`, `RELAY_RESULT_MAX`,
`RELAY_SOCIAL_RATE`, `RELAY_SOCIAL_BURST`.

### The receiving side, in the game

The shipped game's `ONLINE` menu entry is the receiver's window onto the room.
It shows the relay's state, the name the room knows the player by, and who
else is playing. The player can rename themselves there (`N`), which is
persisted in the save file and pushed into the room by the presence client, and
can ping the relay with `T` / `TEST CONNECTION` (runs
`SocialClient.test_connection()` in a worker thread — never on the frame).

**The operator is filtered out of the room list.** `_online_status()` drops any
peer whose name is in `_OPERATOR_NAMES` (`OPERATOR`, `OPERATOR APP`, `SENDER`)
via `_is_operator_peer()`. The sender's default name is `OPERATOR`
(`TQG_SENDER_NAME`), and seeing it in the list would tell the player that
somebody is watching them specifically — the whole thing the room must not give
away. Add the operator's custom name to that set if it is ever renamed
permanently.

**Lobbies are teased, not built.** `ONLINE_LOBBY_TEASER` (names + `soon`/`later`)
and `ONLINE_LOBBY_BLURB` render a "LOBBIES — COMING SOON" section on the ONLINE
screen. Nothing there is focusable or clickable, and the blurb says outright
that none of it works yet. Do not wire these to anything without building the
feature behind them.

**Reconnect is automatic.** The presence worker backs off (`poll * 2^fails`,
capped at 20 s) and reports `reconnecting` for the first two failures before
falling to `offline`, so one dropped packet does not read as "you are offline".
A successful poll resets the streak and bumps `reconnects()`, which the ONLINE
screen shows as `RECONNECTED xN`.

The whole screen is explained by `ONLINE_EXPLAINER` in `main.py` and by the
fourth `HELP_VARIATIONS` entry: the heartbeat, the room living on the server,
the hand-written questions joining the queue unannounced, and the fact that the
player can be seen but cannot write. Keep those two in sync, and keep the host
address **out** of the shipped build: the player-facing copy says "the server
that runs the game", nothing more specific.

The default display name is the account running the game (`_account_name()` →
`getpass.getuser()`, falling back to `USER`/`USERNAME`/`LOGNAME` and then to
`guest-NNNN`). A name the player typed is kept forever; the old `guest-NNNN`
default is treated as "not chosen" and replaced once.

**A received question is a secret.** Nothing in the shipped build announces one:
there is no toast, and the ONLINE screen does not show a pending count. The
question simply becomes the next thing in the queue and looks like every other
question. It is also **not attributed**: `_draw_playing` used to draw a
`QUESTION FROM <NAME>` line above any `_social` step, which told the player
someone had written it. That label is gone and a smoke test asserts the string
stays gone. Do not add a "someone sent you a question!" notice, a source label,
or a counter back; they are the single easiest way to break the feature.

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

The sender looks for the token in `TQG_SEND_TOKEN`, then `<repo>/tqg-token.txt`
(gitignored, hand-edited), then `<appdata>/sender_token` (0600). An explicitly
empty env var means "no token" and stops the search.

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

Two things to know about it:

- it must not touch the network. The default AI provider is the relay, so the
  test points that provider at a dead local port; otherwise every run fired a
  real question at the live relay in a background thread, competing with the
  frame measurement.
- the frame budget is **relative**, not absolute: the playing screen has to
  stay within 1.5× of the menu screen measured on the same machine in the
  same run. A shared CI runner's speed swings several times between runs on
  identical code (2ms and 17ms were measured on the same commit an hour
  apart), so an absolute millisecond ceiling passes or fails with the
  weather. An absolute floor (40ms) is kept as well, for regressions that hit
  both screens.

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
python3 games/remastered/tests/updater_test.py
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
gh release view v5.1.0-beta-remastered --json assets
```

Current versions: game **6.1-alpha** (multiplayer alpha, receiver build),
classic **2.02**, pinned site tag `v6.1-alpha-remastered`, fallback tag
`v6.1-alpha-remastered`.

### Cutting a release

Four things have to move together, and `server/test_site.py` guards three of
them:

1. `config.py` → `VERSION` (the single source of truth);
2. `js/main.js` → `REMASTER_TAG` (`"v" + VERSION + "-remastered"`), and move
   `REMASTER_FALLBACK_TAG` to the previous release;
3. `index.html` / `legacy.html` → every `releases/download/<tag>/` URL and the
   on-page labels. The test fails on any stale `vX.Y.Z-remastered` in a URL;
4. publish a release whose tag contains `remastered` — the three build
   workflows trigger on `release: published`.

The site does not depend on step 2 staying fresh: `resolveRemasterTag()` reads
the release list and picks the newest tag containing "remastered" that is newer
than the pinned one, so a release published while the page is live becomes the
download button immediately. `REMASTER_FALLBACK_TAG` is only what the buttons
use if the GitHub API cannot be reached at all.

The tag naming matters: `v6.1-alpha-remastered` is a valid release tag *and*
parses as version 6.1.0. `versionParts()` stops at the first non-numeric
component, so `alpha` and `remastered` cost nothing.

### Automatic update check

`updater.UpdateChecker` (in `TheQuestionGameRemastered/updater.py`) reads the
published releases on a background thread at launch and every six hours
(`config.UPDATE_CHECK_INTERVAL`). It keeps only non-draft tags containing
`remastered`, compares the newest with `config.VERSION` (alpha < beta < rc <
final), and exposes a result through `poll()`. `main._poll_update_check()`
turns that into a toast plus a title-screen banner; `U` / tapping the banner
opens the release's `html_url` in the browser.

It deliberately never downloads or installs anything. The last check time is
kept in `APP_DATA_DIR/update_check.json` so restarting the game does not hammer
the GitHub API, and `TQG_NO_UPDATE_CHECK=1` disables it entirely. The test
fakes the API, so it does not need the network:

    python3 games/remastered/tests/updater_test.py

Publishing is still the trigger: a draft release is invisible, and a newer
release only reaches players once it is published under a `remastered` tag.
