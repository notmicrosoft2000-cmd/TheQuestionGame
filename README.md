# The Question Game

Three desktop games plus the website, in one repo.

## Layout

```
index.html  css/  js/  img/        the website (served from repo root on
bossfight.mp3  jumpscare.mp3        GitHub Pages — do not move these)
windowq.png  logsmusic.ogg         shared build assets (site + game bundles)

games/
├── classic/      the original game            → python games/classic/TheQuestionGame.py
├── remastered/   the remastered game          → python games/remastered/run_remastered.py
└── firstcopy/    The Simpler Times (1993)     → python games/firstcopy/run_firstcopy.py
                    (a prequel; requires only pygame + numpy)

.github/workflows/   CI: builds Linux/macOS binaries on GitHub Releases
mac/                 py2app build scripts for the macOS builds (used by CI)
requirements-*.txt   CI build dependencies (shared by the classic/remastered builds)
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
