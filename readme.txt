The Question Game runs on Windows 10/11 and macOS 14+ (Apple Silicon).

When sharing this game, please do not just share a single binary — share the
release zip / dmg because the game requires its asset files.

WINDOWS (10/11):
- Download TheQuestionGame.zip from the GitHub Releases page and unzip it.
- Run TheQuestionGame.exe. (If SmartScreen warns, click "More info" > "Run anyway" — the exe is unsigned.)

macOS (14+ / Apple Silicon only):
- Download TheQuestionGame-macOS.dmg from the GitHub Releases page.
- Open the dmg and drag "The Question Game" into your Applications folder.
- The app is unsigned, so the first launch needs a right-click:
    Right-click "The Question Game" > Open > Open
  (or in Terminal: xattr -cr /Applications/TheQuestion\ Game.app)
- On first use, macOS may ask to let the game control System Events
  (for the wallpaper change) and to access the camera. You may deny either —
  the game keeps running, it just skips those scares.

RUNNING FROM SOURCE:
- pip install -r requirements.txt   (Windows/Linux)
- python TheQuestionGame.py

RUNNING ON macOS FROM SOURCE:
- pip install -r requirements.txt
- python3 TheQuestionGame.py

Linux (via WSL) is no longer supported.
