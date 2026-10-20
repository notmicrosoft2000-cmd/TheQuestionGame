The Question Game Remastered runs on Windows 10/11, macOS 14+ (Apple Silicon) and Linux (64-bit).

The questions are written fresh every session. It remembers what you said.

WINDOWS (10/11):
- Download TheQuestionGameRemastered.zip from the GitHub Releases page and unzip it.
- Run TheQuestionGameRemastered.exe. (If SmartScreen warns, click "More info" > "Run anyway" — the exe is unsigned.)

macOS (14+ / Apple Silicon only):
- Download TheQuestionGameRemastered-macOS.dmg from the GitHub Releases page.
- Open the dmg and drag "The Question Game Remastered" into your Applications folder.
- The app is unsigned, so the first launch needs a right-click:
    Right-click "The Question Game Remastered" > Open > Open
- On first use, macOS may ask to let the game control System Events (wallpaper
  changes, window movement) and to access the camera. You may deny either —
  the game keeps running, it just skips those scares.

LINUX (64-bit):
- Requires SDL2 and ALSA runtime libraries (Ubuntu/Debian:
    sudo apt install libsdl2-2.0-0 libsdl2-mixer-2.0-0 libsdl2-image-2.0-0 libsdl2-ttf-2.0-0 libasound2)
- Download TheQuestionGameRemastered-linux.tar.gz from the GitHub Releases page and extract it.
- Make it executable and run it from a terminal:
    chmod +x TheQuestionGameRemastered
    ./TheQuestionGameRemastered
- Webcam, wallpaper, window and notification scares are skipped on Linux.

NOTES:
- Only the first few questions are fixed. Everything after them is written
  live by an AI, so no two sessions are the same.
- The AI may choose local effects: screen flicker, webcam flash, whispered
  speech, window shake, mouse movement, wallpaper changes, notifications,
  and sound. It only ever picks from a fixed local set — nothing else runs.
- If the AI is unreachable, the game falls back to built-in questions and
  still works offline.
- A webcam scare may briefly request your camera. Deny it and the game skips
  it without asking again.

RUNNING FROM SOURCE:
- pip install -r requirements.txt
- python -m TheQuestionGameRemastered.main
