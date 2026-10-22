# The Question Game

Three desktop games plus the website, in one repo.

> **Working on this repo? Read [`docs/AI_HANDBOOK.md`](docs/AI_HANDBOOK.md) first.**
> It covers the editions, the multiplayer sender/receiver split, the relay, the
> build/release flow, the tests, and the traps (the Wayland alpha bug in
> particular) that have already cost us hours.
>
> Want the plain-language version instead? [`docs/HOW_IT_WORKS.md`](docs/HOW_IT_WORKS.md)
> explains the AI, the relay and the room with no code. Changes are listed in
> [`CHANGELOG.md`](CHANGELOG.md).

## Layout

```
index.html  legacy.html  css/  js/  img/      the website (served from repo root
forum-reactions.json  bossfight.mp3            on GitHub Pages — do not move these)
jumpscare.mp3  windowq.png  logsmusic.ogg      shared build assets (site + game bundles)

games/
├── classic/      the original game            → python games/classic/TheQuestionGame.py
├── remastered/   the remastered game          → python games/remastered/run_remastered.py
│                 (Android APK: buildozer android debug — see ANDROID.md)
└── firstcopy/    The Simpler Times (1993)     → python games/firstcopy/run_firstcopy.py
                    (a prequel; requires only pygame + numpy)

.github/workflows/   CI: builds Linux/macOS binaries on GitHub Releases
build/mac/           py2app build scripts for the macOS builds (used by CI)
build/requirements-*.txt   CI build dependencies (shared by the classic/remastered builds)
archive/             frozen pre-reorg snapshot of the repo (not built, not served)
tools/               local build tooling (gitignored)
```

## Running a game

Each game folder is self-contained: source, readme, PyInstaller `.spec`,
and (for firstcopy) its own `requirements.txt`.

- The Simpler Times: `pip install -r games/firstcopy/requirements.txt` then
  `python games/firstcopy/run_firstcopy.py`
- Classic / remastered: the game reads `windowq.png` / `logsmusic.ogg` from
  the current directory, so run them from the repo root as shown above.

## Headless test

`games/firstcopy/playtest.py` drives the real game against a dummy display
and asserts on all four endings. From `games/firstcopy/`:

    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python playtest.py
