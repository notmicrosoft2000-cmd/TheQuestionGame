# Android port — The Question Game Remastered

How the remastered game gets to a phone, what the controls become, and what
happens to the desktop-hijack playstyle when there is no desktop to hijack.

Everything here is already wired: this document describes the code in this
folder, not a plan.

---

## 1. How the port works (no rewrite)

The same pygame-ce codebase ships on Android. python-for-android (p4a) wraps
it in an SDL2 activity, so `main.py` → `run_remastered.py` → the exact same
`Game` class runs on the phone as on the desktop.

| Piece | File | Role |
|---|---|---|
| Build config | `buildozer.spec` | package `org.ntg.thequestiongameremastered`, landscape, fullscreen, arm64-v8a, API 34 / min 24, launcher icon from the package assets |
| Entry point | `main.py` | Android-only shim: permissions + keep-screen-on, then runs `run_remastered.py` |
| Platform switch | `TheQuestionGameRemastered/config.py` → `IS_ANDROID` | `sys.platform == "android"` — one flag gates every difference |
| Recipes | `p4a-recipes/` (== `../classic/p4a-recipes`) | custom recipes: `pygame-ce` 2.5.8 (SDL2 build), `numpy` 2.5.2, `openssl` 3.3.1 |
| Recipes (stock) | — | `opencv` (with Python `cv2` bindings), `pyjnius`, `requests`, `android` |

Build (virtualenv `~/.myenv`, where buildozer lives):

    cd games/remastered
    ./build_android.sh                 # applies the p4a patch below, then
                                       # `buildozer android debug` → bin/
    ./build_android.sh android release # release build

The debug APK from `bin/` was published on the GitHub release
`v4.0.0-remastered` as
`TheQuestionGameRemastered-Android-4.0.0-arm64-v8a-debug.apk`.

That was the last Android build. The v5.0.0 multiplayer alpha is **desktop
only** — Windows, macOS and Linux — so there is no APK for it and the site's
download card deliberately offers no Android link for that release. The site
scans a release's assets for a `.apk`, so an APK dropped into a future release
would be picked up automatically.

SDK/NDK are already provisioned (`~/android/sdk`, NDK 28c), and `.buildozer/`
caches every compiled recipe, so only the first build is long — later builds
re-copy the sources and repackage in minutes. The script also removes p4a's
`build/venv` if an interrupted earlier run left it with mixed pip versions.

p4a pins Gradle 8.14, which refuses to run on Java 27 (the system default).
`build_android.sh` therefore points `JAVA_HOME` at a local Temurin 21 in
`~/android/jdk21` (Adoptium tarball, no sudo) when it exists.

> `.gitignore` deliberately excludes `buildozer.spec`, `p4a-recipes/`,
> `.buildozer/` and `bin/` — the Android toolchain is machine-local. The
> scripts that *keep* it working (`build_android.sh`, `apply_p4a_patches.py`)
> are committed.

### The local p4a patch (why `build_android.sh` exists)

Upstream python-for-android (release 2026.05.09, the clone in `.buildozer/`)
has an inconsistency that hits any dependency whose *Android* wheel exists on
PyPI — which is exactly `charset-normalizer`, pulled in by `requests`:

1. `process_python_modules()` resolves non-recipe requirements with
   `pip --dry-run --platform android_24_arm64_v8a --python-version 3.14.2` and
   pins the matched **target** wheel URLs into `requirements.txt`
   (`charset_normalizer-3.5.2-cp314-cp314-android_24_arm64_v8a.whl`).
2. `run_pymodules_install()` then installed that file with **plain host pip**,
   which validates against linux-x86_64 tags and dies:

       ERROR: charset_normalizer-3.5.2-cp314-cp314-android_24_arm64_v8a.whl
              is not a supported wheel on this platform.

`apply_p4a_patches.py` fixes step 2 by passing the same flags p4a already uses
elsewhere for prebuilt wheels (`Recipe.get_pip_install_args()`):
`--only-binary=:all: --no-deps --python-version 3.14.2 --platform=android_24_…`.
pip then only unpacks the target wheel into `--target` — verified by running
the patched command by hand against the same requirements.txt.

The script is idempotent, and `build_android.sh` runs it before every build.
If upstream fixes this, the script reports
"does not match the expected text" and changes nothing.

`build_android.sh` also exports `VIRTUAL_ENV` before invoking buildozer:
buildozer only skips `pip install --user` when it sees `VIRTUAL_ENV` set, and
pip refuses `--user` inside a virtualenv. Finally, the (gitignored)
`buildozer.spec` sets `p4a.source_dir` to the `.buildozer/` clone so buildozer
uses it in place — without that, buildozer's url/branch check deletes and
re-clones p4a on every run, silently discarding the patch above.


Desktop behaviour is untouched: `IS_ANDROID` is `False` off-device, the same
code path runs as before, and `tests/smoke_test.py` drives the touch paths by
flipping the flag.

### What the flag actually changes

1. **Fullscreen** — `set_mode((display.Info().current_w, current_h), FULLSCREEN)`
   instead of the 800×600 resizable frame (with a windowed fallback if the
   display query fails).
2. **Touch input** — `FINGERDOWN` → `_handle_touch()` (below).
3. **Back key** — Android's `K_AC_BACK` is mapped to `ESC` at the top of
   `_handle_key()`, so every "leave this screen" path works unchanged.
4. **Keep screen on** — `FLAG_KEEP_SCREEN_ON` via pyjnius: the pauses *are*
   the game, so no timeout may dim the screen mid-question.
5. **Permissions** — `CAMERA` (the webcam scare), `INTERNET` (AI relay +
   geo), `VIBRATE`. Storage is deliberately **not** requested: saves live in
   the app's private home dir (`persistence.py` needs no permission).
6. **Desktop-only motion is disabled** — `begin_mouse_move()` and
   `nudge_mouse_from_close()` return early on Android (there is no cursor to
   steal and no title bar to bait a finger toward).

## 2. Controls

The game is keyboard-driven on desktop (TAB/ENTER/ESC). The phone version
keeps the exact same action set — only the gesture changes:

| Desktop | Android |
|---|---|
| TAB / ↑ / ↓ — move between options | **tap the option directly** |
| ENTER — confirm | **same tap** (select *and* confirm in one gesture) |
| ESC — leave About/Help/Logs/Settings | **system Back gesture / Back key** (`K_AC_BACK` → ESC) |
| mouse hover — window parallax | n/a (guarded no-op) |
| F4+Alt, close button — the close fight | n/a: Android owns the window; `EXIT` in the menu is the real exit |

### How hit-testing works

Menus are rendered procedurally, so instead of guessing geometry the draw pass
*records* what it drew:

- `_draw()` clears `self._touch_zones` every frame;
- each option list (`title`, `settings`, `about`, `answer`) registers a
  `pygame.Rect` + action as it blits the row;
- Help/Logs register one full-screen `back` zone ("tap anywhere to leave");
- `FINGERDOWN` normalizes `event.x/y` (0..1) to the framebuffer and hit-tests
  the zones, then runs the same handler the equivalent key would have run
  (`_touch_action()` → `_handle_key(K_RETURN / K_ESCAPE)`).

Because the zones come from the live layout, they follow the game's own
layout logic — including the squeeze that lifts a long answer block up from
the bottom edge, and the screen shake offset.

Interaction rules that fall out of this:

- **Taps are ignored while the question is still typing** (options aren't on
  screen yet — there is nothing to tap), and ignored mid-fade, so a fat-finger
  double-tap can never fire twice.
- Tapping an answer *is* the answer: `_playing_key()` still enforces the
  "only when WAITING" rule, so the tap preselects and confirms in one step.
- Help and Settings show touch wording instead of `[ENTER] / [ESC]`, and the
  in-game Help text gains an "ON THIS DEVICE" section on Android.

## 3. Playstyle — what survives, what degrades, what changes

The horror comes from the machine reaching back: window shakes, cursor theft,
wallpaper flips, notifications, the webcam. On Android there is no desktop to
reach into, so the port keeps the *bite* by re-routing it (this is the part
that makes it feel like the same game, not a demake):

| Scare | Desktop effect | Android effect |
|---|---|---|
| `window_shake` / `windows_shake` / `window_teleport` / `window_drift` | OS window jiggle / teleport | in-app **screen shake** (+ RGB split for the teleport) |
| `mouse_move` | cursor dragged across the screen | **it moves your selection** — same violation, new surface |
| `wallpaper` | desktop wallpaper changed | hard **corruption + flicker** hit |
| `windows_minimize` | all other windows minimized | corruption + flicker |
| `notification` | OS toast (Win/mac) | **real Android Toast** via pyjnius |
| `whisper` | OS-level text + window shake | unchanged — it already does in-app shake + whisper line |
| `flicker`, `corrupt`, `jumpscare`, `rgb_split`, `screen_tear`, `heartbeat`, `rumble`, `static_scream`, `reverse_chord` | in-app | **unchanged** |
| `webcam_flash` | `cv2.VideoCapture(0)` | **unchanged** — CAMERA permission + p4a's opencv build `cv2`; degrades to a flash if the camera refuses |
| `picture` | reads `~/Pictures` | no-op (no gallery access) — guarded, never crashes |

The rule the code follows (`scares._android_stand_in`): *a scare may degrade,
but it may never evaporate.* A scare the AI picked and the player never felt
would break the fiction.

Other desktop-only layers that simply switch off, all guarded in `os_layer`:

- window float / hover parallax / topmost / flash / taskbar fights;
- wallpaper changes and desktop notifications outside Android;
- process awareness (Task Manager / Discord detection) — the scanner reads
  Linux process output and will not recognise Android processes, so those
  interjections stay quiet rather than lie badly;
- the *local* picture scare.

What still works in full:

- **AI questions** through the relay (no key ships in the APK — same as
  desktop), offline/Ollama/OpenRouter/Groq choices in Settings;
- **geo/location card** (VPN-guarded, INTERNET permission);
- **saves, badges, run counter, hesitations, contradictions, cheat code** —
  all in `persistence.py`, now inside the app-private home;
- **all audio** (SDL mixer), VHS/CRT passes, starfield, typing, scares that
  are in-app by nature.

### Playstyle summary for a phone

Landscape, fullscreen, screen stays awake. One hand: tap an answer to give it,
tap a menu line to enter it, swipe back to leave. The game is *slower* in a
good way — no keyboard reflexes — and the entity's intrusions arrive as
screen-level events instead of window-level ones, which reads stronger on a
device you're holding.

## 4. Known gaps / next polish

- `LOGS` still clips at the bottom (same as desktop) — a drag-to-scroll pass
  would be the one real UX addition.
- `VIBRATE` is declared but not yet wired to the jumpscare (one pyjnius call
  away).
- Release build: `buildozer android release` + a signing key (debug APK is
  what `android debug` produces today).
- Launcher icon/presplash reuse `windowq.png` (256×256); swap for dedicated
  art when there is any.

## 5. Tests

`tests/smoke_test.py` covers the port on desktop with dummy SDL drivers:

- title/settings rows and answer rows register as tap zones; tap activates;
- taps mid-typing are no-ops; a tap on a WAITING answer confirms;
- `K_AC_BACK` backs out of a screen;
- Help is a full-screen back zone;
- with `IS_ANDROID` on, `window_shake`/`wallpaper`/`mouse_move` re-route to
  their in-app stand-ins.

    ~/.myenv/bin/python games/remastered/tests/smoke_test.py
