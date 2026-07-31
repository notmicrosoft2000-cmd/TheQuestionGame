This game is for windows 10 and 11.
When sharing this game, please do not just share the .exe. share the zip file because these files in the zip require assets.

LINUX (via WSL):
- Install WSLg: wsl --install
- From inside WSL:
    sudo apt update && sudo apt install -y python3-pip espeak
    pip install -r requirements.txt
    python3 TheQuestionGame.py
- Windows-only features (wallpaper change, window pinning, typing
  detection) are skipped automatically; the game itself runs normally.