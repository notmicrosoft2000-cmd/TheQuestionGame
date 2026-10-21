import os
import platform
import sys

APP_NAME = "The Question Game Remastered"
VERSION = "4.0.0"

# --- Platform ---------------------------------------------------------------
# python-for-android reports sys.platform == "android"; platform.system() is
# kept as a belt-and-braces check because some SDL builds only report Linux.
# Touch input, fullscreen display and the Android back key all key off this.
IS_ANDROID = sys.platform == "android" or platform.system() == "Android"

# --- AI providers ------------------------------------------------------------
# Everything here is FREE — no paid key is ever required:
#   * Ollama   — fully local, no key at all (install Ollama, pull llama3.2)
#   * OpenRouter — free account, free models (":free" suffix), no credit card
#   * Groq     — free tier; embedded key below (rotate it if abused)
#   * OpenAI / DeepSeek — optional paid, only used if you set their key
#
# Default is Groq's free tier (Neptune's call — no paid key, no setup, fast).
# Alternatives, all free, are one env var away:
#   TQG_AI_PROVIDER=auto       -> Ollama if it has a usable model, else OpenRouter
#                                 if TQG_OPENROUTER_KEY is set, else Groq
#   TQG_AI_PROVIDER=ollama     -> fully local (needs a non-thinking model pulled,
#                                 e.g. `ollama pull llama3.2:3b`);
#                                 the qwen3 thinking builds installed on this
#                                 machine dump chain-of-thought as the answer
#                                 and are auto-skipped.
#   TQG_AI_PROVIDER=openrouter -> free-tier ":free" models (free signup key)
#
# All endpoints speak the OpenAI-compatible chat/completions schema, so adding
# a provider is a config-only change. The offline bank always backstops.
#
# SHIPPED DEFAULT: the "relay". The game contains NO API key — it sends its
# request to Neptune's server, which holds the key and forwards it. This is why
# a fresh install needs no setup, and why the key can be rotated without
# re-releasing the game. See server/relay.py.
#
#   Relay URL:       default below                     -> TQG_RELAY_URL
#   Relay app token: the shared secret, if enabled     -> TQG_RELAY_TOKEN
#   OpenRouter key:  https://openrouter.ai/keys        -> TQG_OPENROUTER_KEY
#   Ollama host:     default http://localhost:11434    -> TQG_OLLAMA_HOST
#
# The relay is tried first; if it is unreachable the game falls through to any
# provider below with a key, and finally to the offline bank. A player who wants
# to bring their own key can set TQG_GROQ_KEY and select TQG_AI_PROVIDER=groq.
RELAY_URL = os.environ.get("TQG_RELAY_URL", "https://wikipedia.tail06361a.ts.net/ai/v1/chat/completions")
RELAY_TOKEN = os.environ.get("TQG_RELAY_TOKEN", "")

# --- Online players + hand-written questions ---------------------------------
# Same server as the relay (the /ai funnel prefix), different endpoints:
#   POST {SOCIAL_URL}/v1/presence        heartbeat -> who is online, inbox, results
#   POST {SOCIAL_URL}/v1/send-question   deliver a question to a player or "all"
#   POST {SOCIAL_URL}/v1/answer          report an answer back to its author
# The whole feature is optional and fails soft: if the relay is unreachable the
# game just shows OFFLINE and keeps playing. See social.py.
_RELAY_ROOT = RELAY_URL.split("/v1/")[0].rstrip("/")
SOCIAL_URL = os.environ.get("TQG_SOCIAL_URL", _RELAY_ROOT).rstrip("/")
SOCIAL_ENABLED = os.environ.get("TQG_SOCIAL", "1").strip().lower() not in (
    "0", "false", "no", "off")
SOCIAL_POLL_SECS = float(os.environ.get("TQG_SOCIAL_POLL", "4"))
SOCIAL_TIMEOUT = float(os.environ.get("TQG_SOCIAL_TIMEOUT", "6"))
# Limits mirror server/relay.py; the server enforces them again.
SOCIAL_NAME_MAX = 20
SOCIAL_Q_MAX = 200
SOCIAL_OPT_MAX = 60
SOCIAL_OPTS_MAX = 4
SOCIAL_INBOX_MAX = 8
# NOTE: the game can *receive* questions but never writes them. The right to
# send lives in the separate operator sender app (tools/sender), which is the
# only thing that reads TQG_SEND_TOKEN. Nothing in the shipped game carries a
# send token — there is no code path here that could send one.

AI_PROVIDER = os.environ.get("TQG_AI_PROVIDER", "relay")

AI_PROVIDERS = {
    # Neptune's relay: no key here on purpose — the server injects it.
    "relay": {
        "url": RELAY_URL,
        "key": RELAY_TOKEN or "relay",
        "model": os.environ.get("TQG_RELAY_MODEL", "openai/gpt-oss-120b"),
        "extra": {"reasoning_effort": os.environ.get("TQG_RELAY_EFFORT", "low")},
        "header_token": RELAY_TOKEN,
    },
    # Direct Groq, only used if the player supplies their own key (or the relay
    # falls through). Empty by default so no key ships in the build.
    "groq": {
        "url": os.environ.get("TQG_GROQ_URL", "https://api.groq.com/openai/v1/chat/completions"),
        "key": os.environ.get("TQG_GROQ_KEY", ""),
        "model": os.environ.get("TQG_GROQ_MODEL", "openai/gpt-oss-120b"),
        # gpt-oss models accept reasoning_effort; "low" keeps replies snappy.
        "extra": {"reasoning_effort": os.environ.get("TQG_GROQ_EFFORT", "low")},
    },
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "key": os.environ.get("TQG_OPENROUTER_KEY", ""),
        "model": os.environ.get("TQG_OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"),
    },
    "openai": {
        "url": "https://api.openai.com/v1/chat/completions",
        "key": os.environ.get("TQG_OPENAI_KEY", ""),
        "model": os.environ.get("TQG_OPENAI_MODEL", "gpt-4o-mini"),
    },
    "deepseek": {
        "url": "https://api.deepseek.com/v1/chat/completions",
        "key": os.environ.get("TQG_DEEPSEEK_KEY", ""),
        "model": os.environ.get("TQG_DEEPSEEK_MODEL", "deepseek-chat"),
    },
    "ollama": {
        "url": os.environ.get("TQG_OLLAMA_HOST", "http://localhost:11434") + "/v1/chat/completions",
        "key": "ollama",
        "model": os.environ.get("TQG_OLLAMA_MODEL", "llama3.2"),
    },
}
AI_TIMEOUT = 12  # short: dead network must reach the offline bank quickly
AI_MAX_TOKENS = 320
# Sampling temperature. This used to sit at 1.05, which is above 1.0 and was the
# single biggest cause of the model writing purple metaphor ("the void tightens")
# instead of a plain question. Horror comes from being *specific and true*, not
# from being florid, so we sample cooler — enough variety to never repeat a line,
# not enough for the model to drift into poetry.
AI_TEMPERATURE = 0.75

# Legacy aliases (kept so anything still referencing GROQ_* keeps working).
GROQ_KEY = AI_PROVIDERS["groq"]["key"]
GROQ_MODEL = AI_PROVIDERS["groq"]["model"]
GROQ_URL = AI_PROVIDERS["groq"]["url"]
GROQ_TIMEOUT = AI_TIMEOUT
GROQ_MAX_TOKENS = AI_MAX_TOKENS
GROQ_TEMPERATURE = AI_TEMPERATURE

# Human-authored fixed opening per session. Only the first block of it is
# guaranteed to run *before* the AI chimes in — the rest is interleaved, so the
# machine feels alive from the opening minutes instead of only at the tail.
FIXED_OPENING_COUNT = 6

# How many authored beats to play before the first AI question in each run.
# Run 1 eases you in; by run 3 it improvises almost immediately.
AI_OPENS_AT = {1: 5, 2: 3, 3: 2}

# How many AI questions to place in each run. Sessions get LONGER and meaner as
# they go, not shorter: run 3 is the real ending and should feel endless.
AI_QUESTION_COUNT = {1: 14, 2: 18, 3: 26}

# Minimum number of local effects that MUST fire in each run, regardless of what
# the model chooses. Guarantees the escalation is felt even offline or when the
# AI keeps answering "none".
SCARE_FLOOR = {1: 2, 2: 5, 3: 9}

# Effects the forced floor is allowed to use. Deliberately excludes the ones that
# hijack hardware or the player's machine (webcam_flash, jumpscare, wallpaper,
# picture, windows_*, notification) so a top-up can never do something drastic
# behind the player's back — it just leans on tone.
SCARE_FLOOR_POOL = [
    "flicker", "whisper", "heartbeat", "rumble", "corruption",
    "reverse_chord", "rgb_split", "screen_tear", "window_drift", "static_scream",
]
# webcam_flash is the one hardware effect the floor is allowed to reach for,
# and only because the camera scare ships on by default (WEBCAM_GUARANTEED,
# defined with the other webcam options further down). Without this the camera
# would never fire on a run where the model keeps answering "none" or the AI is
# in Offline mode — it would be a setting nobody ever sees. Everything else
# that hijacks the desktop stays out of the floor.
SCARE_FLOOR_INCLUDE_WEBCAM = True

# Roughly one AI question every N authored/injected beats once the AI is open,
# so the authored script and the machine trade off instead of running in blocks.
AI_INTERLEAVE_EVERY = 2

# Local horror effects the AI may pick from (implemented in scares.py).
AI_SCARE_NAMES = [
    "flicker", "webcam_flash", "whisper", "window_shake", "mouse_move",
    "wallpaper", "picture", "notification", "heartbeat", "rumble",
    "corruption", "static_scream", "reverse_chord",
    "window_teleport", "window_drift", "rgb_split", "screen_tear",
    "jumpscare", "windows_shake", "windows_minimize",
]

# --- Display ---
WINDOW_W, WINDOW_H = 800, 600
WINDOW_LOCKED = False       # False = normal resizable frame (drag the edges)
WINDOW_MIN_W, WINDOW_MIN_H = 640, 480
WINDOW_MAX_W, WINDOW_MAX_H = 3840, 2160   # allow dynamic scaling to any reasonable size; no fullscreen
# The window can be stretched to any size, recommended to play in window mode.
# There is no F11 / Alt+Enter handler, the frame is a plain RESIZABLE window.
# SDL's FULLSCREEN flags are never used.
BLOCK_CLOSE_ATTEMPTS = True
CLOSE_RESIST_MAX = 30   # attempts before the constant-drift "you live here now" phase
WEBCAM_DURATION = 20
# The camera scare is on by default: it needs no prompt and no opt-in, exactly
# like the Classic edition. WEBCAM_GUARANTEED also lets the forced scare floor
# pick it, so the camera still opens on a run where the model never chooses it.
WEBCAM_ENABLED = True
WEBCAM_GUARANTEED = True
if WEBCAM_GUARANTEED and SCARE_FLOOR_INCLUDE_WEBCAM:
    SCARE_FLOOR_POOL.append("webcam_flash")
FRAMERATE = 60
ENABLE_TASKMGR_DETECT = True
ENABLE_DISCORD_DETECT = True
MUSIC_ENABLED = True
WEBCAM_DISTORTION = True   # glitch bars / inversion on the live camera feed
SFX_DUCK_UNDER_MUSIC = 0.55  # SFX volume multiplier while bossfight.mp3 plays
KEEP_WINDOW_ON_TOP = True   # re-assert HWND_TOPMOST so it cannot be buried

# Background music. The track only scores the *menu* screens (Settings /
# About / Help / Logs) — gameplay and the title stay on ambience + SFX only.
MENU_MUSIC = True
MUSIC_MENUS_ONLY = True       # True = no music on TITLE or during PLAYING
MUSIC_VOLUME = 0.5            # menu screens
MUSIC_VOLUME_IN_GAME = 0.32   # (only used if MUSIC_MENUS_ONLY is off)

# --- CRT / VHS look ----------------------------------------------------------
# The frame is finished through a CRT + VHS pass: phosphor triad mask, curved
# tube edges, row curvature, tracking slips, head-switching noise, drifting
# static and a rolling refresh bar.
CRT_ENABLED = True
CRT_INTENSITY = 1.0           # scaled by the VHS Effects setting at runtime
CRT_CURVATURE = 0.16          # 0 = flat panel, 0.16 = strongly bowed tube
CRT_CURVE_BANDS = 26          # horizontal slices used to fake the bow (costly if high)
VHS_TRACKING = True           # horizontal slips + tracking bars
VHS_STATIC = 1.0              # drifting static/snow density multiplier
VHS_STATIC_LINE = 1.0         # faint drifting head line on the main screen
CRT_CORNER_ROUND = 26         # px of rounded/blackened tube corner (0 = square)

# --- Window motion (Windows + macOS only; Wayland forbids apps moving windows)
# The window gently floats up and down the whole time, and jumps to a fresh
# spot near the centre every time a question lands.
WINDOW_FLOAT = True
WINDOW_FLOAT_AMPLITUDE = 14   # pixels of vertical travel
WINDOW_FLOAT_PERIOD = 4.2     # seconds per full bob
WINDOW_JITTER_NEAR_CENTER = True   # nudge near the centre on each new question
WINDOW_JITTER_RANGE = 90      # pixels either side of dead centre
WINDOW_ANSWER_NUDGE = 13      # little shuffle of the window when you answer
WINDOW_HOVER_AMPLITUDE = 6    # subtle hover parallax (px) toward the cursor

# --- AI loop -----------------------------------------------------------------
# Prefetching the *next* question while the current one is on screen meant the
# model never saw the player's latest answer (it always ran ~2 questions
# behind). Off = each question is generated the moment it is needed, using the
# full up-to-date history, with THINKING dots covering the network wait.
AI_PREFETCH_LOOKAHEAD = False

# --- Location awareness (Classic mentioned where you are) -------------------
ENABLE_LOCATION = True        # resolve city/country and ask about it
ENABLE_COUNTRY_FLAG = True    # download + show your country's flag
AI_TAILOR_TO_NATION = True    # let the AI reference the player's country
# IP geolocation is trivially fooled by a VPN — the lookup just reports the exit
# node. We cannot see past a tunnel from inside the app, but we *can* catch the
# lie: a real ISP route sits in the same rough timezone as the machine's clock,
# while a VPN exit usually does not. If the IP's UTC offset disagrees with the
# local clock by more than GEO_VPN_MAX_OFFSET_HOURS, the IP city is treated as
# untrustworthy and we fall back to the OS timezone instead of naming a city the
# player is not in (being told the wrong city breaks the whole illusion).
GEO_VPN_GUARD = True
GEO_VPN_MAX_OFFSET_HOURS = 2.0
# Never ask a plaintext HTTP geolocation endpoint — an on-path attacker (or the
# captive-portal Wi-Fi the player is sitting on) can rewrite that answer freely.
GEO_ALLOW_INSECURE = False

# --- Classic "bite" mechanics (ported from games/classic) --------------------
# The fixed opening plus the AI questions are the skeleton; these are the
# teeth Classic had — contradictions, tailored callbacks, machine awareness.
ENABLE_DYNAMIC_QUESTIONS = True       # location/process/app questions built from real machine state
ENABLE_CONTRADICTIONS = True          # "Are you alone?" asked again, then thrown back at you
ENABLE_HESITATION_CALLOUT = True      # pausing too long gets noticed (Classic: 20s)
ENABLE_BACKGROUND_INTERFERENCE = True  # periodic cmd flash + error beep like Classic
HESITATION_THRESHOLD = 20.0           # seconds before a pause is called out
PATIENT_ONE_THRESHOLD = 60.0          # seconds on one question -> "patient_one" badge
BACKGROUND_INTERFERENCE_INTERVAL = 30.0   # flash_cmd() cadence
BACKGROUND_BEEP_INTERVAL = (15.0, 45.0)   # randomized error-sound cadence

# --- Persistence ---
def get_appdata_dir():
    # Test override: keeps smoke/integration runs off the real save data.
    override = os.environ.get("TQG_DATA_DIR")
    if override:
        return override
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
    "Font": ["Courier", "Terminal", "Mono", "Sans", "Serif"],
    "Text Speed": ["Fast", "Normal", "Slow"],
    "VHS Effects": ["Off", "Low", "Normal", "High"],
    "Text Sway": ["Off", "Low", "Normal", "High"],
    "Text Size": ["Small", "Normal", "Large", "Huge"],
    "AI Source": ["Relay", "Local", "Offline"],
}
SETTING_MAPS = {
    "Text Speed": [0.015, 0.04, 0.08],
    "VHS Effects": [0.0, 0.4, 1.0, 2.0],
    "Text Sway": [0.0, 0.4, 1.0, 1.8],
    "Text Size": [0.8, 1.0, 1.25, 1.6],
}
SETTING_DEFAULTS = {
    "Font": 0,
    "Text Speed": 1,
    "VHS Effects": 2,
    "Text Sway": 2,
    "Text Size": 1,
    "AI Source": 0,
}

# "AI Source" label -> which provider the game selects on that choice.
AI_SOURCE_PROVIDERS = {"Relay": "relay", "Local": "ollama", "Offline": "offline"}

COLOR_BLACK = (0, 0, 0)
COLOR_WHITE = (220, 220, 220)
COLOR_GREEN = (0, 220, 0)
COLOR_RED = (200, 0, 0)
COLOR_DARK_RED = (100, 0, 0)
COLOR_DIM_RED = (60, 0, 0)

# Readability: a 1px dark halo under body/UI text so it stays legible on top of
# static, scanlines and curvature.
TEXT_OUTLINE = True
TEXT_OUTLINE_COLOR = (0, 0, 0)

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
