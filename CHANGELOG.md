# Changelog

What changed, newest first. Dates are the commit date (YYYY-MM-DD).

This file covers the **games and the server**. The website has its own long
history in the git log; only version-bearing site changes are listed here.

Version numbers follow the game's `config.VERSION`. Release tags look like
`v6.1-alpha-remastered`; the site picks the newest one automatically.

---

## v6.1-alpha — 2026-10-22

### Changed

- **Sessions are roughly twice as long.** The AI now writes 22 / 32 / 46
  questions for runs 1 / 2 / 3 (was 14 / 18 / 26), and the guaranteed scare
  floor rises to 3 / 7 / 12. A full run no longer ends before it has time to
  get under your skin.
- **The entity stops asking the same question.** Every question the player has
  ever answered is kept in the save (new `asked_questions` field) and the most
  recent 60 are sent to the model as a hard "never repeat" list. The prompt also
  rotates an explicit subject per question, so it cannot orbit the same three
  ideas. Duplicates from the model trigger one retry with a "different subject"
  nudge, and identical effects are blocked locally for the rest of the session.
  The offline bank grows from 24 to 109 unique questions and filters itself
  against both the current session and earlier runs.
- **The ambience is the Classic v2.02 buzz again.** The remastered bed layered
  detuned drones, LFO drift and tape hiss, which read as static. It is now a
  clean 50 Hz mains hum with quiet 100/150 Hz harmonics, a whisper of noise and
  a loop-locked breath, at the old, quieter channel level.
- **Text is back to Classic thickness.** The bundled Courier face has taller
  glyph metrics than the system face the Classic edition used, which made every
  line look heavier at the same point size. "Courier" now prefers the system
  face (bundled stays as a packaged-build fallback), and the 8-direction opaque
  halo became a translucent 4-direction halo.

### Added

- **Malware-theme scares.** Eight new effects sell the feeling that something
  got installed: a fake antivirus scan (`fake_scan`), a fake blue screen
  (`fake_bsod`), a fake administrator console typing on its own
  (`fake_terminal`), a file-manager window listing real file names
  (`file_names`), a fake OS sign-in alert (`security_alert`), the real clipboard
  (`clipboard`), the real window title (`window_title`), and one harmless
  uniquely-named `.txt` on the real Desktop (`desktop_note`). The note never
  overwrites an existing file, is capped at one per session, and every one of
  these effects degrades to a no-op (or to the in-app fake scan) on platforms
  or setups where it cannot work.
- **New ACCESSIBILITY setting: "Disable Desktop Scares".** Swaps the four
  real-desktop effects for the in-app fake scan while keeping the beat. Tests
  and screenshots use `TQG_SAFE_SCARES=1` for the same guarantee.
- New authored malware beats in all three runs, with longer endings.

### Fixed

- The relay and the operator sender now recognise all eight new effect names.

### Site

- The download page now leads with the Remastered build. The stable Classic
  v2.02 card is the last card and starts collapsed, so the current release is
  the first thing a player sees; the Classic downloads open on click.

---

## v6.0.0 — 2026-10-22

A big release. The game gets a settings overhaul it badly needed, a pile of
quality-of-life, a real graphics control panel, and — because it turns out the
game needed one — **an eye that watches you the whole time**.

### Added

- **The watching eye.** There is an eye in the corner of the screen, and there
  is no way to turn it off. It is drawn in the game's own language: barebone
  white sclera, black iris, black pupil, a hard black socket ring. No art
  assets, no veins, no glamour — just a drawn shape that watches.
  - It **follows the cursor**. Move the mouse and the pupil goes with it.
  - It **looks at what you are choosing**. When a menu option is highlighted,
    the pupil turns to look straight at it, and it moves fast enough that you
    can actually see it move between options.
  - It **sits in different corners**: bottom-right in the menus and on the
    title screen, top-right during the game, out of the way of the text.
  - It **blinks**, at irregular intervals, and it blinks a lot more and turns
    **red** whenever a scare is playing — a flicker, a corruption, a whisper.
  - It gets **more erratic in later sessions**: faster blinking, more
    wandering, a wider pulse.
  - It **keeps its own tally of your answers.** Answer the same thing twice and
    the pupil contracts and holds that stare. Do it three times and the eye
    swells and flushes red. Hesitate on a question for long enough and it
    widens instead.
  - The pupil **breathes** — a slow, irregular swell and shrink, all the time.
  - At the **end of the session** the corner eye stands down and **one big eye
    takes over the whole screen**, sitting behind the text and staring out.
    That is the last thing you see.
- **A desktop eye (Windows and macOS).** When the game window loses focus, a
  borderless, always-on-top, click-through window appears on the desktop with
  an eye in it, and that eye trails your cursor across your whole screen. It
  follows you into other windows. Bring the game back and it disappears again.
  It runs as a separate process (`--eye-overlay`), is supervised by the game,
  and dies with it. Linux does not get the desktop overlay — Wayland
  compositors deliberately keep the pointer position private, and there is no
  way around that — but the in-game eye follows the cursor off the edge of the
  window there instead.
- **A settings overhaul.** The old flat list of eight options is now seven
  tabbed categories — `AUDIO`, `VIDEO`, `GRAPHICS`, `GAMEPLAY`,
  `ACCESSIBILITY`, `CONTROLS`, `OTHER` — and everything in them is saved to
  the save file and survives a restart.
- **Volume controls.** Separate master, sound-effect, ambience and music
  sliders, each with a mute. The game honours them everywhere, including the
  procedurally generated sound.
- **Video options.** Fullscreen, vsync (asked of the driver — a driver that
  cannot do it simply runs unthrottled), a window resolution from 640×480 to
  1600×1200, and a UI scale from 75% to 150%. The UI scale is a *real* scale:
  the game is drawn at another resolution and stretched to the window, so the
  text and the layout grow together instead of the text drifting out of its
  boxes.
- **A graphics control panel.** A performance preset (`Low` / `Medium` /
  `High`), a CRT on/off switch with its own intensity, and individual toggles
  for every post-processing layer: scanlines, vignette, dust, the static line,
  tube curvature and the phosphor mask. `Low` turns the expensive layers off
  by itself.
- **A pause menu.** `ESC` during the game opens `RESUME` / `SETTINGS` /
  `MAIN MENU` / `EXIT` instead of the game just ignoring the key.
- **Key rebinding.** The `CONTROLS` tab rebinds up, down, confirm and
  back/pause. Rebinds are saved with the rest of the settings, and a conflict
  is rejected rather than silently shadowing another action.
- **Photosensitivity switches.** `Reduce Flashes`, `Disable Screen Shake` and
  `Disable Webcam Scares` — and the scare system actually respects them.

### Changed

- The version label on the title screen moved from the bottom-right to the
  top-right. The bottom-right corner belongs to the eye now.
- The settings list scrolls when a category is taller than the window
  (`GRAPHICS` has nine options).
- `Text Speed` and `VHS Effects` gained more steps (`Very Fast` …
  `Very Slow`, and `Extreme`).

### Fixed

- Turning fullscreen off left the window at its fullscreen size on some SDL
  versions (2.28 on Linux, for one). SDL throws away a size request that
  arrives while the window is still fullscreen, so the game was left drawing
  into a window the player never asked for. It asks for the size again now.
- The eye asked pygame for the window's system information every frame. On
  Wayland that call is **fatal** — pygame 2.6 builds a capsule from the
  window's shell surface, which is `NULL` for a plain window, and
  `PyDict_SetItemString` does not check for a `NULL` value, so the interpreter
  died with `SIGSEGV` and there was no way to catch it from Python. The
  desktop cursor is now only asked for under X11, where the answer can be
  mapped onto the window. On Wayland the eye follows the pointer inside the
  window, which is all the compositor allows anyway.
- The eye asked the OS where the game window was on *every frame*. On macOS
  that answer cost a process spawn (AppleScript) sixty times a second. The
  window position is now cached for a fraction of a second, and the cursor is
  read through Quartz only, never through AppleScript.

### Notes

- The desktop eye is **Windows and macOS only**. The in-game eye is on every
  platform, including Linux and Android.
- Every overlay failure path degrades to "no overlay". It never crashes the
  game.

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
