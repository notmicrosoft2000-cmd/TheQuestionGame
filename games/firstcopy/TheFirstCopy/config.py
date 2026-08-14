"""Configuration for The Simpler Times (1993)."""
import os
import platform
import sys

APP_NAME = "The Simpler Times"
SUBTITLE = "1993"
VERSION = "0.1.0"

# --- Display ---
WINDOW_W, WINDOW_H = 640, 480
FPS = 60
MARGIN = 24

# --- Resolve CWD relative to this file so file paths work from anywhere ---
try:
    _APP_DIR = os.path.dirname(os.path.abspath(
        sys.executable if getattr(sys, "frozen", False) else __file__))
    os.chdir(os.path.dirname(_APP_DIR))
except Exception:
    pass

# --- Persistence (kept separate from the other games' state) ---
def get_appdata_dir():
    """Hidden-ish persistent storage in %APPDATA% (Windows) or ~/.local/share (other)."""
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.path.join(os.path.expanduser("~"), ".local", "share")
    folder = os.path.join(base, "TQFirstCopy")
    try:
        os.makedirs(folder, exist_ok=True)
    except Exception:
        pass
    return folder

STATE_DIR = get_appdata_dir()
STATE_FILE = os.path.join(STATE_DIR, "firstcopy_state.json")
BADGES_FILE = os.path.join(STATE_DIR, "badges.json")

# --- Amber CRT palette (1993 era, distinct from the classic's green) ---
BG          = (6, 4, 0)
PANEL       = (14, 9, 2)
LINE        = (32, 20, 6)
LINE_BRIGHT = (50, 32, 10)
TEXT        = (255, 176, 32)   # amber phosphor
TEXT_BRIGHT = (255, 214, 96)
DIM         = (122, 76, 14)
GREEN       = (0, 220, 0)      # the survivor/"?" emblem color
RED         = (255, 60, 60)    # the entity's accent (the smiley's face)
DARK_RED    = (120, 20, 20)
CYAN        = (0, 216, 255)

# --- Settings defaults ---
DEFAULT_SETTINGS = {
    "text_speed": 0.035,   # seconds per character
    "vhs_intensity": 1.0,  # 0.0 = off, 1.0 = default
    "text_size": 1.0,      # multiplier on base font sizes
    "mouse_guard": True,   # eject the mouse if it enters the window
}


def window_size():
    """Fixed window size: ~3/4 of the primary display, capped.

    The window deliberately never fills the desktop (and is not resizable or
    fullscreenable): it is supposed to look like a program that does not
    quite behave, a beige tower window that sits slightly wrong on the
    screen.
    """
    w, h = WINDOW_W, WINDOW_H
    try:
        import pygame
        info = pygame.display.Info()
        dw, dh = info.current_w, info.current_h
        if dw and dh:
            w = min(int(dw * 0.75), 1280)
            h = min(int(dh * 0.75), 960)
            if w < WINDOW_W or h < WINDOW_H:
                w, h = WINDOW_W, WINDOW_H
    except Exception:
        pass
    return (w, h)

# --- Settings label/value tables (used by the Settings menu) ---
TEXT_SPEED_OPTIONS = [
    ("FAST", 0.008),
    ("NORMAL", 0.035),
    ("SLOW", 0.09),
]
TEXT_SIZE_OPTIONS = [
    ("SMALL", 0.85),
    ("NORMAL", 1.0),
    ("LARGE", 1.25),
]
VHS_OPTIONS = [
    ("OFF", 0.0),
    ("LOW", 0.5),
    ("NORMAL", 1.0),
    ("HIGH", 1.4),
]
