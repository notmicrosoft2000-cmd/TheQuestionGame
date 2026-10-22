# Changelog

What changed, newest first. Dates are the commit date (YYYY-MM-DD).

This file covers the **games and the server**. The website has its own long
history in the git log; only version-bearing site changes are listed here.

Version numbers follow the game's `config.VERSION`. Release tags look like
`v5.1.0-beta-remastered`; the site picks the newest one automatically.

---

## Unreleased

Nothing yet.

---

## v5.1.0-beta — 2026-10-22

The multiplayer alpha, fixed. Four things were broken or missing, and all four
are on the **receiving** side — what a player's download does.

### Fixed

- **The operator was visible in the room.** `OPERATOR` (the sender's default
  name) showed up in the ONLINE list, which told the player somebody was
  watching them specifically. The list now drops operator peers and shows only
  players. The operator still receives questions and answers.
- **A hand-written question announced itself.** The playing screen drew
  `QUESTION FROM <NAME>` above any question that came from the room — with the
  sender's default name that read "QUESTION FROM OPERATOR". The label is gone.
  A question from the room is now indistinguishable from a generated one: no
  label, no toast, no counter.
- **ONLINE and the operator sender crashed on open.** pygame 2.x defines no
  uppercase letter key constants, so `K_N` / `K_H` raised `AttributeError` the
  moment those screens were used. Shifted letters arrive as lowercase plus a
  modifier; both bad usages are removed.

### Added

- **An operator effects channel.** The sender can now fire the game's own
  scares and glitches by hand (F2 screen, 20 effects read from the game's
  registry, with an intensity dial). They ride the same route and the same
  token gate as a question but land in their own store, arrive on the next
  presence poll, and the game plays them through its own scare system —
  indistinguishable from the model choosing them. Nothing announces them.
- **Intensity scales an effect's duration.** The relay clamps the operator's
  dial to `[0.1, 2.0]`; the receiver stretches the deadline each scare writes.
  Scaling the game clock instead was wrong twice over (2x lasted for the whole
  uptime, 0.5x landed in the past so nothing showed) and was caught by test.
- **Reconnect and resume.** The presence worker backs off (`poll * 2^fails`,
  capped at 20s) and reports `RECONNECTING` for the first two failures instead
  of flashing `OFFLINE`. A recovered link shows `RECONNECTED xN`.
- **A connection test** on the ONLINE screen (`T`), which times a round trip to
  the relay on a worker thread.
- **Lobby placeholders.** A "LOBBIES — COMING SOON" section with four teased
  rooms, every entry tagged `SOON`/`LATER`, and a blurb that says outright none
  of it works. Nothing there is clickable.
- **The default room name is the account running the game** (`getpass.getuser()`,
  falling back to `USER`/`USERNAME`/`LOGNAME`, then `guest-NNNN`).

### Changed

- **The download page resolves the newest published release** instead of
  pinning one tag for ever. It keeps the previous release as a fallback if the
  GitHub API is unreachable.
- **Sender layout.** Long questions and options wrap over as many lines as they
  need and the form scrolls; nothing is truncated with `...`. The help screen
  is two columns with its own smaller font.
- **Token sources, in order:** `TQG_SEND_TOKEN`, then `<repo>/tqg-token.txt`,
  then the app-data copy (`0600`), then ask. An explicitly empty env var stops
  the search.
- **The relay refuses an unknown effect name** with `400` instead of silently
  delivering nothing, so a typo in the sender fails loudly.
- **The relay was redeployed** with the effects channel.

### Notes

- The relay lives on the maintainer's home server (`192.168.99.56`) and is
  exposed through a Tailscale Funnel. It is the **same** server that proxies the
  AI. See [`docs/HOW_IT_WORKS.md`](docs/HOW_IT_WORKS.md).
- `RELAY_SEND_TOKEN` still needs rotating: the old value is in public history at
  `375a038`. The file is untracked and gitignored from here on.

---

## v5.0.0-remastered — 2026-10-21

The multiplayer alpha itself, and the run of fixes that made it usable.

- **The online room exists.** Players see who else is running the game right now
  (names only), whether the relay is reachable, and the name the room knows them
  by. The room lives in memory on the relay: no database, no accounts, no
  history.
- **Hand-written questions, delivered one-shot.** A question is cleared the
  moment it is handed over, so it is never replayed. Items expire after 15
  minutes; a peer drops off the list after 20 seconds without a poll.
- **The sender/receiver split.** Only the operator's separate sender app can
  write questions, because only it holds the send token. Every download is a
  receiver: it can be seen and can answer, but has no code path that could send
  a question. The relay enforces this before it even reads the body.
- **Answers go back.** When a player answers a hand-written question, the sender
  is told whether they got it right, with the name they are playing under.
- **The sending half is not published.** It is not linked from the site and
  cannot be downloaded.

### Fixed before release

- **Black window on Wayland** — the frame was losing its alpha.
- **Black window and broken drag-resize** (second cause).
- **The ONLINE screen crashed** on open (see v5.1.0 above).
- **The operator sender did not work** end to end.
- **The headless smoke test touched the network**, which made CI flaky. It now
  runs offline, and its frame budget is measured against the machine rather
  than the clock.

---

## v4.0.0 — 2026-10-20

- Dynamic scaling and more random AI questions.
- **The AI relay.** No API key ships with the game any more: the game asks the
  maintainer's server, which holds the key and forwards the request. This is
  what stops the key being extractable from a download.
- Resizable frame, VPN-guarded geo, guaranteed webcam, plain AI questions.

---

## v3.0.2 — 2026-10-20

- Visible AI, real sound files, a working EXIT.
- PyInstaller specs anchored to the spec file rather than the current directory,
  so builds work from any CWD.
- Legacy build archived; build files moved under `build/`.
- Site: key scrub, release wiring fix.

---

## Android

The Android port shipped (commit `39a6883`), crashed on launch, was patched and
then support was **paused**: the APK crashes on launch and every Android download
path is intercepted with a "fatal bug" notice. Do not re-enable it without
fixing the crash and proving it on a device.

---

## How to add an entry

When you change something a player or the operator would notice, add it under a
new version heading at the top, in the same shape: `Fixed`, `Added`, `Changed`,
`Notes`. Say what the user sees, not which function moved. If it was a bug, say
how it presented — "ONLINE and the sender crashed on open" beats "removed invalid
key constants".
