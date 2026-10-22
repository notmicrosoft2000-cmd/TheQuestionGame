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
  live by an AI, so no two sessions are the same. Questions are generated in
  the background while you read, so there is no wait between them.
- The AI may choose local effects: screen flicker, screen tearing, chromatic
  splitting, webcam flash, whispered speech, window shake, window teleport,
  slow window drift, mouse movement, wallpaper changes, notifications,
  jump scares, and sound. On Windows it can also shake or minimize every other
  window you have open. It only ever picks from a fixed local set — nothing
  else runs.
- The window is locked at a fixed size with no title bar and no close,
  minimize, or maximize buttons. Close attempts (the X, Alt+F4, the menu
  EXIT item) are refused, and refused loudly — escalation is the point. On
  Windows it also keeps itself pinned on top, flashes the taskbar entry, and
  strips the close item out of the system menu, so the only way out is the
  Task Manager (Activity Monitor on macOS).
- It watches the machine: some questions are built from what is actually open
  and where you actually are ("Discord is running…", "Are you currently in
  {your city}, {your country}?"), it shows your country's flag, and it notices
  when you open the Task Manager. The AI is told roughly where you are, so it
  can tailor questions to your nation.
- It opens the camera and tells you it is doing so — once in Run 1, and again
  in later runs.
- It catches contradictions: answer "Are you alone?" one way and it will ask
  again later, then throw the difference back at you. Long pauses and quick
  answers both get called out, and there is a badge for staring at a question
  for a full minute.
- Music: logsmusic.ogg on the hidden logs screen, bossfight.mp3 through
  Session 3, jumpscare.mp3 on the big scares.
- If the AI is unreachable, the game falls back to built-in questions and
  still works offline.
- Location is approximate and derived from your network address (city-level),
  not GPS. The flag and nation-tailored questions need a working connection;
  without one the game simply omits them.
- A webcam scare may briefly request your camera. Deny it and the game skips
  it without asking again.

ONLINE (who is playing + questions from the operator):
- This is the multiplayer alpha (v5.1.0-beta). Treat it as an alpha: it will break,
  and it will break often. When it does, the rest of the game is unaffected.
- This build is the RECEIVER half. It joins the room, plays the questions the
  operator sends, and reports your answers back. The half that writes questions
  is the operator's own program: it is not part of this build, it is not
  published, and it cannot be downloaded from the site.
- The title menu has an ONLINE entry. It shows everyone else running the game
  right now (names only), whether the relay is reachable, and the name the
  room knows you by.
- How it works, end to end: your game checks in with the room every few seconds
  (that is why other players can see you), with the name you are playing under.
  The room itself lives on the server that runs the game — the same one that
  answers the AI questions. Nothing is installed on your machine and no file is
  written there for it.
- Questions written by hand by the operator can join the queue between the
  ordinary generated ones. They look exactly the same and nothing announces
  them — the whole point is that you cannot tell which questions were written
  for you.
- When you answer one, the operator is told whether you got it right, with the
  name you are playing under.
- Press N on the ONLINE screen to set your own name; press T to test the
  connection to the room right there and then. Your default name is the name of
  the account running the game.
- Questions are held for a quarter of an hour if nobody is playing yet.
- Nothing here is required: if the relay is down the screen says OFFLINE and the
  rest of the game is unaffected.
- Turn the whole thing off with TQG_SOCIAL=0, or point it at your own relay with
  TQG_SOCIAL_URL (defaults to the same host as TQG_RELAY_URL).

AI PROVIDERS (advanced):
- The game ships with NO API key. It asks Neptune's relay, which holds the key
  and forwards the request to Groq (model openai/gpt-oss-120b). Nothing secret is
  in this build, and the key can be rotated server-side without a new release.
- Settings -> AI Source switches between:
    Relay    the built-in server relay (default; needs internet)
    Local    a local Ollama model, if you have one installed
    Offline  no network at all; the built-in question bank only
- Point at a different relay or bring your own key with env vars:
    TQG_RELAY_URL / TQG_RELAY_TOKEN   a self-hosted relay (see server/relay.py)
    TQG_AI_PROVIDER=groq + TQG_GROQ_KEY=...   your own Groq key, direct
- The game talks to any OpenAI-compatible chat API. Other providers (openrouter,
  openai, deepseek, ollama) are one env var away; see config.py.
- If the relay is unreachable the game falls back to the offline question bank
  instantly, so it always runs.

RUNNING FROM SOURCE:
- pip install -r build/requirements-mac-remastered.txt (or the linux one)
- python -m TheQuestionGameRemastered.main
- Testing: set TQG_DATA_DIR to a temp dir so saves stay out of your real
  profile (the automated tests do this).
