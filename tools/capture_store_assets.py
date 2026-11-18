#!/usr/bin/env python3
"""Capture real frames from the remastered game for store listings.

Runs the actual Game class headlessly with the Android platform flag on, so the
screens show the phone layout (touch wording, Low-mode renderer, 1280x720
landscape). Writes PNG screenshots plus two looping GIFs made from real frames.

    ~/.myenv/bin/python tools/capture_store_assets.py

Outputs to store-assets/ in the repo root. The dummy SDL driver still advances
Game.now from wall-clock time, so the helpers below sleep between frames --
without that, fades never finish and questions stay half-typed.
"""
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "store-assets")
FRAMES = os.path.join(OUT, "frames")
DATA = "/tmp/opencode/tqg_capture_data"

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["TQG_DATA_DIR"] = DATA
os.environ["TQG_SOCIAL"] = "0"
os.environ["TQG_SAFE_SCARES"] = "1"
shutil.rmtree(DATA, ignore_errors=True)
os.makedirs(DATA, exist_ok=True)
shutil.rmtree(FRAMES, ignore_errors=True)
os.makedirs(FRAMES, exist_ok=True)

sys.path.insert(0, os.path.join(ROOT, "games", "remastered"))

import pygame  # noqa: E402

from TheQuestionGameRemastered import config, main as gmain, os_layer  # noqa: E402

# No speech engine: pyttsx3/espeak segfaults intermittently in this container.
os_layer.speak_text = lambda *a, **k: None
# Never call the live relay; the offline question bank answers immediately.
config.AI_PROVIDERS["relay"]["url"] = "http://127.0.0.1:9/v1/chat/completions"

# Present a phone-shaped landscape display to the Android code path.
class _Info:
    current_w = 1280
    current_h = 720


pygame.display.Info = lambda: _Info()
config.IS_ANDROID = True
gmain.IS_ANDROID = True


def _phone_display(self):
    """The dummy driver ignores FULLSCREEN, so force a 16:9 phone window."""
    self._video_applied = self._video_wanted()
    return pygame.display.set_mode((1280, 720))


gmain.Game._create_display = _phone_display

game = gmain.Game()


def tick():
    game._update()
    game._draw()


def advance(seconds):
    """Let real time pass so fades/timers/typing progress like a real session."""
    end = time.time() + seconds
    while time.time() < end:
        tick()
        time.sleep(0.02)
    tick()


def shot(name):
    path = os.path.join(OUT, name)
    pygame.image.save(pygame.display.get_surface(), path)
    print("saved", path, flush=True)
    return path


def frame(prefix, index):
    path = os.path.join(FRAMES, "%s_%03d.png" % (prefix, index))
    pygame.image.save(pygame.display.get_surface(), path)
    return path


def make_gif(name, count, fps=8, width=720):
    # Frames are written as name_000.png, name_001.png, ... so ffmpeg can read
    # them straight from the numbered pattern. The concat demuxer drops most
    # frames for an image sequence, so it is deliberately not used here.
    pattern = os.path.join(FRAMES, name + "_%03d.png")
    palette = os.path.join(FRAMES, name + "_palette.png")
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-framerate", str(fps), "-i", pattern,
        "-vf", "scale=%d:-1:flags=lanczos,palettegen=stats_mode=diff" % width,
        palette,
    ], check=True)
    out = os.path.join(OUT, name + ".gif")
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-framerate", str(fps), "-i", pattern,
        "-i", palette,
        "-lavfi", "scale=%d:-1:flags=lanczos [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=3" % width,
        "-loop", "0", out,
    ], check=True)
    print("saved", out, "(%d frames)" % count, flush=True)


def force_full_question():
    """Skip the typing animation and draw the finished question + options."""
    step = game.active_script[game.current_step]
    game.typing_state = "WAITING"
    game.typing_index = len(step.get("q") or "")
    game.fade["active"] = False
    game.fade["alpha"] = 0
    game._draw()  # no _update: it would put the typewriter back into TYPING


# --- Title ------------------------------------------------------------------
game.state = "TITLE"
game._on_state_enter()
advance(1.5)
shot("01-title.png")
title_frames = []
for i in range(90):
    tick()
    if i % 3 == 0:
        title_frames.append(frame("title", len(title_frames)))
    time.sleep(0.02)
make_gif("title", len(title_frames))

# --- Playing ----------------------------------------------------------------
game.state = "PLAYING"
game._on_state_enter()
advance(1.2)
gameplay_frames = []
# Real typing: THINKING dots give way to the question appearing character by
# character, then the answer options fade in when it finishes.
for i in range(180):
    tick()
    if i % 3 == 0:
        gameplay_frames.append(frame("gameplay", len(gameplay_frames)))
    if game.typing_state == "WAITING" and i > 30:
        break
    time.sleep(0.02)
force_full_question()
for _ in range(8):
    time.sleep(0.08)
    game._draw()
    gameplay_frames.append(frame("gameplay", len(gameplay_frames)))
shot("02-question.png")
make_gif("gameplay", len(gameplay_frames))

# --- Pause ------------------------------------------------------------------
game.paused = True
advance(0.3)
shot("03-pause.png")
game.paused = False

# --- Settings / Online / Help -----------------------------------------------
for state, filename in (("SETTINGS", "04-settings.png"),
                        ("ONLINE", "05-online.png"),
                        ("HELP", "06-help.png")):
    try:
        game.state = state
        game._on_state_enter()
        advance(0.5)
        shot(filename)
    except Exception as exc:
        print("skip", state, repr(exc), flush=True)

print("DONE", flush=True)
