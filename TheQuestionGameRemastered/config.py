import os
import platform
import sys

APP_NAME = "The Question Game Remastered"
VERSION = "2.03"

# --- AI (embedded key — rotate it if it gets abused) ---
GROQ_KEY = "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"
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_TIMEOUT = 30
GROQ_MAX_TOKENS = 320
GROQ_TEMPERATURE = 1.05

# Human-authored fixed opening per session; the AI fills everything after it.
FIXED_OPENING_COUNT = 6

# How many AI questions to attempt per run.
AI_QUESTION_COUNT = {1: 12, 2: 10, 3: 8}

# Local horror effects the AI may pick from (implemented in scares.py).
AI_SCARE_NAMES = [
    "flicker", "webcam_flash", "whisper", "window_shake", "mouse_move",
    "wallpaper", "picture", "notification", "heartbeat", "rumble",
    "corruption", "static_scream", "reverse_chord",
]

# --- Display ---
WINDOW_W, WINDOW_H = 800, 600
WEBCAM_DURATION = 20
FRAMERATE = 60

# --- Persistence ---
def get_appdata_dir():
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        return os.path.join(base, "TQGameRemastered")
    if system == "Darwin":
        return os.path.expanduser("~/Library/Application Support/TheQuestionGameRemastered")
    return os.path.join(os.path.expanduser("~"), ".tqgame_remastered")

APP_DATA_DIR = get_appdata_dir()
STATE_FILE = os.path.join(APP_DATA_DIR, "game_state.json")
BADGES_FILE = os.path.join(APP_DATA_DIR, "badges.json")
WALLPAPER_DIR = os.path.join(APP_DATA_DIR, "wallpaper")

# Full-brightness color map used to build solid wallpaper images.
WALLPAPER_COLORS = {
    "red": (200, 0, 0),
    "green": (0, 160, 0),
    "blue": (0, 40, 180),
    "black": (0, 0, 0),
    "white": (235, 235, 235),
    "purple": (110, 20, 130),
}

FAV_COLOR_OPTIONS = ["Red", "Blue", "Green", "Black", "White", "Purple"]

DEFAULT_STATE = {
    "run_count": 1,
    "fav_color": "black",
    "answers": {},
    "answer_times": {},
    "original_wallpaper": "",
    "last_close_time": 0,
    "idle_events": 0,
    "task_manager_opened": False,
    "false_memory_used": False,
    "discord_voice_lie_flagged": False,
    "lie_count": 0,
    "hesitation_count": 0,
    "lie_ids": [],
    "logs_unlocked": False,
    "_ended": False,
    "settings": {"text_speed": 0.04, "vhs_intensity": 1.0, "sway_intensity": 1.0, "text_size": 1.0},
}

# Settings UI options -> numeric values.
SETTING_OPTIONS = {
    "Text Speed": ["Fast", "Normal", "Slow"],
    "VHS Effects": ["Off", "Low", "Normal", "High"],
    "Text Sway": ["Off", "Low", "Normal", "High"],
    "Text Size": ["Small", "Normal", "Large"],
}
SETTING_MAPS = {
    "Text Speed": [0.015, 0.04, 0.08],
    "VHS Effects": [0.0, 0.4, 1.0, 2.0],
    "Text Sway": [0.0, 0.4, 1.0, 1.8],
    "Text Size": [0.8, 1.0, 1.25],
}
SETTING_DEFAULTS = {
    "Text Speed": 1,
    "VHS Effects": 2,
    "Text Sway": 2,
    "Text Size": 1,
}

COLOR_BLACK = (0, 0, 0)
COLOR_WHITE = (220, 220, 220)
COLOR_GREEN = (0, 220, 0)
COLOR_RED = (200, 0, 0)
COLOR_DARK_RED = (100, 0, 0)
COLOR_DIM_RED = (60, 0, 0)

# Local asset lookup: packaged builds ship assets next to the exe; source
# builds find them in the package folder.
def asset_path(name):
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "assets", name))
        candidates.append(os.path.join(meipass, name))
    if sys.platform == "darwin" and getattr(sys, "frozen", False):
        res = os.path.join(os.path.dirname(sys.executable), "..", "Resources")
        candidates.append(os.path.join(res, "assets", name))
        candidates.append(os.path.join(res, name))
    candidates += [
        os.path.join(here, "assets", name),
        os.path.join(here, name),
        os.path.join(os.path.dirname(here), name),
        name,
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[0]
