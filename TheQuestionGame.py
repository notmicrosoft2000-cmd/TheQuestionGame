import pygame
import sys
import time
import random
import os
import requests
import glob
import cv2
import numpy as np
import webbrowser
import platform
import subprocess
import threading
import pyttsx3
import math
import json
import ctypes
import ctypes.wintypes

# --- Persistence Layer (AppData, not the run directory) ---
def get_appdata_dir():
    """Returns a hidden-ish persistent storage dir in %APPDATA% (Windows) or ~/.local/share (other)."""
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.path.join(os.path.expanduser("~"), ".local", "share")
    folder = os.path.join(base, "TQGameData")
    try:
        os.makedirs(folder, exist_ok=True)
    except:
        pass
    return folder

STATE_DIR = get_appdata_dir()
STATE_FILE = os.path.join(STATE_DIR, "game_state.json")

def load_game_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {
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
        # Invisible tracking
        "lie_count": 0,
        "hesitation_count": 0,
        "lie_ids": [],
        # Settings (defaults)
        "settings": {
            "text_speed": 0.04,       # seconds per character
            "vhs_intensity": 1.0,     # 0.0 = off, 1.0 = default
            "sway_intensity": 1.0,    # 0.0 = off, 1.0 = default
        }
    }

def save_game_state(state_data):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state_data, f)
    except:
        pass

game_state = load_game_state()
LAST_CLOSE_TIME_ON_LAUNCH = game_state.get("last_close_time", 0)

# --- Windows Native Wallpaper Modification ---
def get_current_wallpaper_path():
    if platform.system() == "Windows":
        try:
            buf = ctypes.create_unicode_buffer(512)
            ctypes.windll.user32.SystemParametersInfoW(0x0073, 512, buf, 0)
            return buf.value
        except:
            return ""
    return ""

def set_wallpaper_from_path(path):
    if platform.system() == "Windows" and path:
        try:
            ctypes.windll.user32.SystemParametersInfoW(20, 0, path, 3)
        except:
            pass

def generate_solid_bmp(rgb, path):
    try:
        import struct
        w, h = 1920, 1080
        row_size = ((w * 3 + 3) & ~3)
        pixel_data_size = row_size * h
        file_size = 54 + pixel_data_size
        bmp_header = struct.pack('<2sIHHI', b'BM', file_size, 0, 0, 54)
        dib_header = struct.pack('<IIIHHIIIIII', 40, w, h, 1, 24, 0, pixel_data_size, 2835, 2835, 0, 0)
        row = bytes([rgb[2], rgb[1], rgb[0]] * w)
        padding = bytes(row_size - w * 3)
        with open(path, 'wb') as f:
            f.write(bmp_header + dib_header)
            for _ in range(h):
                f.write(row + padding)
        return True
    except:
        return False

def set_desktop_wallpaper(color_name):
    if platform.system() == "Windows":
        color_map = {
            "red": (255, 0, 0), "green": (0, 200, 0), "blue": (0, 0, 255),
            "black": (0, 0, 0), "white": (255, 255, 255), "yellow": (255, 255, 0),
            "purple": (128, 0, 128), "cyan": (0, 255, 255)
        }
        rgb = color_map.get(color_name.lower(), (0, 0, 0))
        wp_path = os.path.join(STATE_DIR, "horror_bg.bmp")
        if generate_solid_bmp(rgb, wp_path):
            try:
                ctypes.windll.user32.SystemParametersInfoW(20, 0, wp_path, 3)
            except:
                pass

def set_black_wallpaper_and_cache():
    if platform.system() == "Windows":
        cached = get_current_wallpaper_path()
        if cached:
            game_state["original_wallpaper"] = cached
        wp_path = os.path.join(STATE_DIR, "black_wp.bmp")
        if generate_solid_bmp((0, 0, 0), wp_path):
            try:
                ctypes.windll.user32.SystemParametersInfoW(20, 0, wp_path, 3)
            except:
                pass

def restore_original_wallpaper():
    orig = game_state.get("original_wallpaper", "")
    if orig and os.path.exists(orig):
        set_wallpaper_from_path(orig)

# --- Initialize Pygame & Audio Systems ---
pygame.init()
pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)

WIDTH, HEIGHT = 800, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
icon = pygame.image.load("windowq.png")
pygame.display.set_icon(icon)
pygame.display.set_caption("The Question Game")
pygame.mouse.set_visible(False)

BLACK = (0, 0, 0)
WHITE = (220, 220, 220)
GREEN = (0, 220, 0)
RED = (200, 0, 0)
DARK_RED = (100, 0, 0)
DIM_RED = (60, 0, 0)

FONT_NAME = pygame.font.match_font('courier')

def get_scaled_fonts(w, h):
    base = min(w, h)
    large_sz = max(28, int(base * 0.09))
    med_sz   = max(16, int(base * 0.052))
    small_sz = max(11, int(base * 0.033))
    return (
        pygame.font.Font(FONT_NAME, large_sz),
        pygame.font.Font(FONT_NAME, med_sz),
        pygame.font.Font(FONT_NAME, small_sz)
    )

font_large, font_medium, font_small = get_scaled_fonts(WIDTH, HEIGHT)

# --- Procedural Audio Generation ---
def play_type_sound():
    buf = np.zeros(int(0.015 * 22050), dtype=np.int16)
    for i in range(len(buf)):
        buf[i] = int(random.choice([-8000, 8000]))
    pygame.mixer.Sound(buffer=buf).play().set_volume(0.15)

def play_ui_nav_sound():
    t = np.linspace(0, 0.03, int(22050 * 0.03), False)
    wave = np.sin(2 * np.pi * 600 * t)
    pygame.mixer.Sound(buffer=np.int16(wave * 8000)).play().set_volume(0.2)

def play_ui_select_sound():
    t = np.linspace(0, 0.08, int(22050 * 0.08), False)
    wave = np.sin(2 * np.pi * 880 * t)
    pygame.mixer.Sound(buffer=np.int16(wave * 12000)).play().set_volume(0.3)

def play_mechanical_beep():
    t = np.linspace(0, 0.12, int(22050 * 0.12), False)
    wave = np.sin(2 * np.pi * 1200 * t)
    pygame.mixer.Sound(buffer=np.int16(wave * 14000)).play().set_volume(0.25)

def play_error_sound():
    t = np.linspace(0, 0.2, int(22050 * 0.2), False)
    wave = np.sin(2 * np.pi * 150 * t) + np.sin(2 * np.pi * 155 * t)
    pygame.mixer.Sound(buffer=np.int16(wave * 18000)).play().set_volume(0.4)

def play_glitch_sound():
    """Harsher digital glitch burst, used in Run 2 atmosphere."""
    dur = random.uniform(0.05, 0.18)
    t = np.linspace(0, dur, int(22050 * dur), False)
    freq = random.uniform(300, 2200)
    wave = np.sin(2 * np.pi * freq * t)
    noise = np.random.normal(0, 0.4, len(t))
    combined = np.clip(wave * 0.6 + noise * 0.4, -1, 1)
    pygame.mixer.Sound(buffer=np.int16(combined * 16000)).play().set_volume(0.3)

def play_static_burst():
    dur = 0.25
    t = np.linspace(0, dur, int(22050 * dur), False)
    noise = np.random.normal(0, 1.0, len(t))
    pygame.mixer.Sound(buffer=np.int16(np.clip(noise, -1, 1) * 9000)).play().set_volume(0.18)

def play_heartbeat():
    """Deep thudding heartbeat — used in Run 3."""
    dur = 0.18
    t = np.linspace(0, dur, int(22050 * dur), False)
    env = np.exp(-t * 25)
    wave = np.sin(2 * np.pi * 55 * t) * env
    sound = pygame.mixer.Sound(buffer=np.int16(np.clip(wave, -1, 1) * 28000))
    sound.play().set_volume(0.55)

def play_deep_rumble():
    """Subsonic grinding — Run 3 transition moments."""
    dur = 0.8
    t = np.linspace(0, dur, int(22050 * dur), False)
    freq = np.linspace(80, 40, len(t))
    wave = np.sin(2 * np.pi * freq * t)
    noise = np.random.normal(0, 0.25, len(t))
    combined = np.clip(wave * 0.7 + noise * 0.3, -1, 1)
    env = np.exp(-t * 1.2)
    pygame.mixer.Sound(buffer=np.int16(combined * env * 22000)).play().set_volume(0.5)

def play_reverse_chord():
    """Eerie reverse string sweep — used on lore payoff lines in Run 3."""
    dur = 1.2
    t = np.linspace(0, dur, int(22050 * dur), False)
    env = np.linspace(0, 1, len(t)) ** 2
    freqs = [220, 277, 330, 370]
    wave = sum(np.sin(2 * np.pi * f * t) for f in freqs) / len(freqs)
    wave = wave * env
    pygame.mixer.Sound(buffer=np.int16(np.clip(wave, -1, 1) * 14000)).play().set_volume(0.35)

def play_static_scream():
    """High-pitched distorted screech — used on Run 3 interface corruption moments."""
    dur = 0.35
    t = np.linspace(0, dur, int(22050 * dur), False)
    freq = np.linspace(400, 3200, len(t))
    wave = np.sin(2 * np.pi * freq * t)
    noise = np.random.normal(0, 0.6, len(t))
    env = np.exp(-t * 6)
    combined = np.clip(wave * 0.5 + noise * 0.5, -1, 1) * env
    pygame.mixer.Sound(buffer=np.int16(combined * 20000)).play().set_volume(0.45)

def start_ambience():
    t = np.linspace(0, 4.0, int(22050 * 4.0), False)
    wave = np.sin(2 * np.pi * 50 * t) * 0.5 + np.random.normal(0, 0.03, len(t))
    sound = pygame.mixer.Sound(buffer=np.int16(wave * 12000))
    sound.play(-1).set_volume(0.2)

def speak_text(text):
    try:
        engine = pyttsx3.init()
        engine.setProperty('rate', 115)
        engine.say(text)
        engine.runAndWait()
    except:
        pass

# --- Host Utilities ---
def flash_cmd():
    if platform.system() == "Windows":
        subprocess.Popen("cmd.exe /c exit", shell=True, creationflags=0)

def get_hwnd():
    try:
        return pygame.display.get_wm_info()['window']
    except:
        return None

def get_window_rect(hwnd):
    rect = ctypes.wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect

# --- Smooth window movement (animated, not instant teleport) ---
window_anim = {"active": False, "start_x": 0, "start_y": 0, "target_x": 0, "target_y": 0, "start_time": 0, "duration": 0.6}

def begin_window_move(target_x, target_y, duration=0.6):
    """Kick off a smooth animated move of the OS window to target_x/y."""
    hwnd = get_hwnd()
    if not hwnd:
        return
    rect = get_window_rect(hwnd)
    window_anim["active"] = True
    window_anim["start_x"] = rect.left
    window_anim["start_y"] = rect.top
    window_anim["target_x"] = target_x
    window_anim["target_y"] = target_y
    window_anim["start_time"] = time.time()
    window_anim["duration"] = duration

def update_window_anim():
    """Call every frame. Smoothly eases the window toward its target position."""
    if not window_anim["active"]:
        return
    hwnd = get_hwnd()
    if not hwnd:
        window_anim["active"] = False
        return
    elapsed = time.time() - window_anim["start_time"]
    dur = window_anim["duration"]
    t = min(1.0, elapsed / dur)
    # ease-out cubic
    eased = 1 - pow(1 - t, 3)
    x = int(window_anim["start_x"] + (window_anim["target_x"] - window_anim["start_x"]) * eased)
    y = int(window_anim["start_y"] + (window_anim["target_y"] - window_anim["start_y"]) * eased)
    try:
        ctypes.windll.user32.SetWindowPos(hwnd, 0, x, y, 0, 0, 0x0001)
    except:
        pass
    if t >= 1.0:
        window_anim["active"] = False

def move_window_right(duration=0.8):
    if platform.system() == "Windows":
        try:
            monitor_w = ctypes.windll.user32.GetSystemMetrics(0)
            win_w = screen.get_width()
            begin_window_move(monitor_w - win_w - 10, 100, duration)
        except:
            pass

def move_window_center(duration=0.8):
    if platform.system() == "Windows":
        try:
            monitor_w = ctypes.windll.user32.GetSystemMetrics(0)
            monitor_h = ctypes.windll.user32.GetSystemMetrics(1)
            win_w, win_h = screen.get_width(), screen.get_height()
            begin_window_move((monitor_w - win_w) // 2, (monitor_h - win_h) // 2, duration)
        except:
            pass

# --- Smooth mouse movement (animated nudge, not instant teleport) ---
mouse_anim = {"active": False, "start_x": 0, "start_y": 0, "target_x": 0, "target_y": 0, "start_time": 0, "duration": 0.35}

def begin_mouse_move(target_x, target_y, duration=0.35):
    cur_x, cur_y = pygame.mouse.get_pos()
    mouse_anim["active"] = True
    mouse_anim["start_x"], mouse_anim["start_y"] = cur_x, cur_y
    mouse_anim["target_x"], mouse_anim["target_y"] = target_x, target_y
    mouse_anim["start_time"] = time.time()
    mouse_anim["duration"] = duration

def update_mouse_anim():
    if not mouse_anim["active"]:
        return
    elapsed = time.time() - mouse_anim["start_time"]
    t = min(1.0, elapsed / mouse_anim["duration"])
    eased = 1 - pow(1 - t, 2)
    x = int(mouse_anim["start_x"] + (mouse_anim["target_x"] - mouse_anim["start_x"]) * eased)
    y = int(mouse_anim["start_y"] + (mouse_anim["target_y"] - mouse_anim["start_y"]) * eased)
    pygame.mouse.set_pos(x, y)
    if t >= 1.0:
        mouse_anim["active"] = False

def nudge_mouse_from_close():
    """If the mouse is hovering near the X button, animate it away (visible nudge, not a block)."""
    if platform.system() == "Windows" and not mouse_anim["active"]:
        try:
            hwnd = get_hwnd()
            if not hwnd:
                return
            rect = get_window_rect(hwnd)
            pt = ctypes.wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            if pt.x > rect.right - 50 and pt.y < rect.top + 35:
                begin_mouse_move(pt.x - 140, pt.y + 120, 0.4)
        except:
            pass

def minimize_all_windows():
    if platform.system() == "Windows":
        move_window_right()
        threading.Thread(target=speak_text, args=("Look at your desktop. Look at how fragile your sanctuary is.",), daemon=True).start()

# --- Run 3 OS-level intrusions ---
_r3_jiggle_thread = None
_r3_jiggle_active = False

def _jiggle_game_window(hwnd, cycles=6, amplitude=18, interval=0.06):
    """Shake the game window violently."""
    global _r3_jiggle_active
    _r3_jiggle_active = True
    try:
        rect = get_window_rect(hwnd)
        ox, oy = rect.left, rect.top
        for _ in range(cycles):
            for dx, dy in [(amplitude, 0), (-amplitude, amplitude), (0, -amplitude), (amplitude, amplitude)]:
                ctypes.windll.user32.SetWindowPos(hwnd, 0, ox + dx, oy + dy, 0, 0, 0x0001)
                time.sleep(interval)
        ctypes.windll.user32.SetWindowPos(hwnd, 0, ox, oy, 0, 0, 0x0001)
    except:
        pass
    _r3_jiggle_active = False

def shake_game_window(cycles=8, amplitude=20):
    if platform.system() == "Windows":
        hwnd = get_hwnd()
        if hwnd:
            threading.Thread(target=_jiggle_game_window, args=(hwnd, cycles, amplitude), daemon=True).start()

def shake_other_windows():
    """Enumerate top-level windows and briefly shake them all."""
    if platform.system() != "Windows":
        return
    def _do():
        our_hwnd = get_hwnd()
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        handles = []
        def _collect(hwnd, _):
            if hwnd != our_hwnd and ctypes.windll.user32.IsWindowVisible(hwnd):
                handles.append(hwnd)
            return True
        ctypes.windll.user32.EnumWindows(EnumWindowsProc(_collect), 0)
        for hwnd in handles[:4]:  # limit to 4 windows
            try:
                rect = ctypes.wintypes.RECT()
                ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
                ox, oy = rect.left, rect.top
                for dx, dy in [(12, 0), (-12, 12), (8, -8), (-8, 8), (0, 0)]:
                    ctypes.windll.user32.SetWindowPos(hwnd, 0, ox + dx, oy + dy, 0, 0, 0x0001)
                    time.sleep(0.04)
                ctypes.windll.user32.SetWindowPos(hwnd, 0, ox, oy, 0, 0, 0x0001)
            except:
                pass
    threading.Thread(target=_do, daemon=True).start()

def open_random_picture_silently():
    """Open a picture from the user's Pictures folder — no permission asked."""
    def _do():
        try:
            pic_dir = os.path.join(os.path.expanduser('~'), 'Pictures')
            files = glob.glob(os.path.join(pic_dir, '**', '*.[jp][pn]*'), recursive=True)
            if files:
                webbrowser.open(random.choice(files))
        except:
            pass
    threading.Thread(target=_do, daemon=True).start()

def open_webcam_silently():
    """Open webcam without showing a permission dialog — just does it."""
    if not webcam_active:
        start_webcam_nonblocking()

def comment_on_open_apps():
    """Returns a string naming currently open apps to insert as a question."""
    if platform.system() != "Windows":
        return None
    try:
        output = subprocess.getoutput("tasklist /FO CSV /NH").lower()
        app_names = {
            "chrome.exe": "Chrome", "firefox.exe": "Firefox", "msedge.exe": "Edge",
            "spotify.exe": "Spotify", "steam.exe": "Steam", "vlc.exe": "VLC",
            "code.exe": "VS Code", "notepad.exe": "Notepad", "explorer.exe": "Explorer",
            "discord.exe": "Discord", "slack.exe": "Slack", "zoom.exe": "Zoom",
            "obs64.exe": "OBS", "obs32.exe": "OBS",
        }
        found = [name for proc, name in app_names.items() if proc in output]
        if found:
            return random.choice([
                f"I can see {found[0]} is open.\nWas that intentional?",
                f"You have {found[0]} running in the background.\nAre you expecting someone?",
                f"{found[0]}.\nThat is interesting timing.",
            ])
    except:
        pass
    return None

def show_os_notification(title, body):
    """Show a real Windows toast notification if possible."""
    if platform.system() == "Windows":
        def _do():
            try:
                # PowerShell toast (works Windows 10+)
                ps_cmd = (
                    f"[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
                    f"ContentType = WindowsRuntime] | Out-Null; "
                    f"$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
                    f"[Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
                    f"$template.SelectSingleNode('//text[@id=\"1\"]').InnerText = '{title}'; "
                    f"$template.SelectSingleNode('//text[@id=\"2\"]').InnerText = '{body}'; "
                    f"$toast = [Windows.UI.Notifications.ToastNotification]::new($template); "
                    f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('The Question Game').Show($toast);"
                )
                subprocess.Popen(
                    ["powershell", "-WindowStyle", "Hidden", "-Command", ps_cmd],
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            except:
                pass
        threading.Thread(target=_do, daemon=True).start()

# --- Close interception (X button is permanently disabled) ---
close_intercept = {"stage": 0, "warn_time": 0, "active_on_busy_q": False}

# Which question triggers the "X button is disabled" scare
BUSY_QUESTION_ID = "exit_broken"
_close_scare_active = False   # set True while on the busy question

def attempt_close_with_warning():
    """
    Called on QUIT or Alt+F4.
    Returns False ALWAYS — the X button is permanently disabled.
    """
    global _close_scare_active
    # Always play error sound and show message
    play_error_sound()
    close_intercept["warn_time"] = time.time()
    # Never allow close — always return False
    return False

def get_close_intercept_message():
    """Return the current intercept line to render on screen."""
    return "Escaping is not as easy as you think."

def check_processes():
    if platform.system() == "Windows":
        output = subprocess.getoutput("tasklist").lower()
        return {
            "discord": "discord.exe" in output,
            "telegram": "telegram.exe" in output,
            "roblox": "robloxplayerbeta.exe" in output,
            "taskmgr": "taskmgr.exe" in output
        }
    return {"discord": False, "telegram": False, "roblox": False, "taskmgr": False}

def get_foreground_window_title():
    """Grab the title of whatever window was focused before this game (or currently, if alt-tabbed)."""
    if platform.system() == "Windows":
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value.strip()
        except:
            return ""
    return ""

def fetch_location():
    try:
        res = requests.get('http://ip-api.com/json/', timeout=4).json()
        lon, lat = res.get('lon'), res.get('lat')
        country = res.get('country', 'Unknown')
        city = res.get('city', 'Unknown')
        game_state['_geo_lat'] = lat
        game_state['_geo_lon'] = lon
        return city, country
    except:
        return "Unknown City", "Unknown Country"

def get_random_picture():
    pic_dir = os.path.join(os.path.expanduser('~'), 'Pictures')
    files = glob.glob(os.path.join(pic_dir, '**', '*.[jp][pn]*'), recursive=True)
    return random.choice(files) if files else None

def put_computer_to_sleep():
    if platform.system() == "Windows":
        try:
            subprocess.run("rundll32.exe powrprof.dll,SetSuspendState 0,1,0", shell=True)
        except:
            pass

# --- Memory / Answer Tracking ---
def save_answer(step_id, answer, elapsed_time):
    game_state["answers"][str(step_id)] = answer
    game_state["answer_times"][str(step_id)] = round(elapsed_time, 2)
    # --- Invisible lie detector ---
    # Detect known-contradiction pairs
    _lie_pairs = {
        "lied": {"Yes": True},            # admitted to lying
        "trust_screen": {"Yes": True},    # trusts screen but plays horror game
        "safe_screen": {"Yes": True},     # feels safe — suspiciously confident
        "alone2": None,                   # contradiction check done separately
    }
    q_id = str(step_id)
    # flag contradictions with "alone" answer
    if q_id == "alone2":
        prev = game_state["answers"].get("alone")
        if prev is not None and answer != prev:
            game_state["lie_count"] = game_state.get("lie_count", 0) + 1
            ids = game_state.get("lie_ids", [])
            ids.append(q_id)
            game_state["lie_ids"] = ids
    # hesitation tracking
    if elapsed_time > HESITATION_THRESHOLD:
        game_state["hesitation_count"] = game_state.get("hesitation_count", 0) + 1
    save_game_state(game_state)

def get_answer(step_id):
    return game_state["answers"].get(str(step_id), None)

HESITATION_THRESHOLD = 20.0  # seconds 

def get_hesitation_comment():
    comments = [
        "You took a while.\nAre you answering truthfully?",
        "That hesitation was noted.",
        "Most people answer faster.\nWhat were you thinking about?",
        "Interesting. You paused before responding.",
        "You took longer than expected.\nIs something bothering you?",
        "Twenty seconds is a long time to think about a yes or no."
    ]
    return random.choice(comments)

# --- Idle / Away Detection ---
idle_tracker = {
    "window_focused": True,
    "lost_focus_time": 0,
    "total_idle_seconds": 0,
    "pending_comment": False,
    "last_away_duration": 0
}

def get_idle_comment():
    dur = idle_tracker["last_away_duration"]
    if dur > 30:
        options = [
            "You were gone for a while.",
            "Where did you go?",
            f"You looked away for {int(dur)} seconds.\nWe waited."
        ]
    else:
        options = [
            "You looked away.",
            "I noticed that.",
            "Where did you go?"
        ]
    return random.choice(options)

# --- False Memory Mechanic ---
FALSE_MEMORY_LINES = [
    "Earlier you told me you don't sleep well.\nWhy did you lie about that just now?",
    "You said this wasn't the first time you've felt like this.\nDo you remember saying that?",
    "We have it written down that you hesitated on the very first question.\nYou didn't think we'd notice the pattern."
]

def trigger_false_memory_question():
    if game_state.get("false_memory_used"):
        return None
    line = random.choice(FALSE_MEMORY_LINES)
    game_state["false_memory_used"] = True
    save_game_state(game_state)
    return {
        "q": line,
        "type": "choice",
        "opts": ["I never said that", "Liar"],
        "_id": "false_memory",
        "_injected": True,
        "_false_memory_response": True
    }

FALSE_MEMORY_REBUTTALS = {
    "I never said that": "I have it written down.\nDo you want to see it?",
    "Liar": "That's the second one."
}

# --- Pre-knowledge phrasing (statements instead of questions) ---
def make_preknowledge_color_statement(fav_color):
    """Instead of asking, it tells the player what it already knows and asks them to confirm."""
    return {
        "q": f"Your favorite color is {fav_color}.\nCorrect?",
        "type": "choice",
        "opts": ["Confirm", "That's wrong"],
        "_id": "preknowledge_color",
        "_injected": True,
        "_preknowledge_wrong_response": "...That's not what I have written down.\nAnswer again."
    }

# --- Discord voice-call contradiction check ---
def check_discord_voice_contradiction(alone_answer):
    """
    If Discord is running AND the user appears to be in a voice call,
    but they claimed to be alone, flag it.
    NOTE: we only check process presence, never read message content or call participants.
    """
    if platform.system() != "Windows":
        return None
    output = subprocess.getoutput("tasklist").lower()
    discord_running = "discord.exe" in output
    if discord_running and alone_answer == "Yes":
        return {
            "q": "Discord is open.\nIf you were truly alone, who exactly were you about to talk to?",
            "type": "choice",
            "opts": ["No one", "I forgot it was open", "..."],
            "_id": "discord_contradiction",
            "_injected": True
        }
    return None

# --- Location tension ---
def build_location_question(city, country):
    return {
        "q": f"Are you currently in {city}, {country}?",
        "type": "choice",
        "opts": ["Yes", "No"],
        "_id": "location_confirm",
        "_injected": True,
        "_location_no_response": "That's strange.\nThe network you're connected to says otherwise.\nWe'll use what we have."
    }

# --- UI Layout Helpers ---
def render_wrapped_text(surface, text, font, color, start_x, start_y, max_width, angle=0):
    words = text.split(' ')
    lines = []
    current_line = ""
    for word in words:
        if "\n" in word:
            parts = word.split("\n")
            current_line += parts[0]
            lines.append(current_line)
            current_line = parts[1] + " "
        else:
            test_line = current_line + word + " "
            if font.size(test_line)[0] < max_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word + " "
    lines.append(current_line)
    for i, line in enumerate(lines):
        surf = font.render(line.strip(), True, color)
        if angle != 0:
            surf = pygame.transform.rotate(surf, angle)
        surface.blit(surf, (start_x, start_y + i * (font.get_linesize() + 4)))

def apply_vhs_effects(surface, w, h):
    intensity = game_state.get("settings", {}).get("vhs_intensity", 1.0)
    if intensity <= 0:
        return
    bar_y = (int(time.time() * 90) % h)
    if random.random() < 0.12 * intensity:
        pygame.draw.rect(surface, (15, 15, 15), (0, bar_y, w, random.randint(int(15 * intensity), max(1, int(40 * intensity)))))
    step = max(2, int(4 / intensity)) if intensity > 0 else 4
    for y in range(0, h, step):
        pygame.draw.line(surface, (5, 5, 5), (0, y), (w, y), 1)
    # Extra glitch bands at high intensity
    if intensity >= 1.5 and random.random() < 0.06:
        gy = random.randint(0, h)
        pygame.draw.rect(surface, (30, 0, 0), (0, gy, w, random.randint(2, 8)))

def apply_shadow_static(surface, w, h, intensity=1.0):
    """
    Run 2 enhanced static — occasionally renders a vague humanoid silhouette
    made of noise blocks that appears for a single frame then vanishes.
    """
    if random.random() < 0.02 * intensity:
        sx = random.randint(int(w * 0.1), int(w * 0.8))
        sy = random.randint(int(h * 0.2), int(h * 0.6))
        sh = random.randint(int(h * 0.25), int(h * 0.4))
        sw = max(20, int(sh * 0.35))
        shape = pygame.Surface((sw, sh), pygame.SRCALPHA)
        for _ in range(40):
            bx = random.randint(0, sw - 4)
            by = random.randint(0, sh - 4)
            shade = random.randint(10, 35)
            pygame.draw.rect(shape, (shade, shade, shade, 160), (bx, by, 4, 4))
        surface.blit(shape, (sx, sy))
        if random.random() < 0.5:
            play_static_burst()

# --- WEBCAM ---
camera = None
webcam_surface = None
webcam_active = False
webcam_start_time = 0
WEBCAM_DURATION = 20  # seconds

def start_webcam_nonblocking():
    global camera, webcam_active, webcam_start_time
    def _open():
        global camera, webcam_active, webcam_start_time
        try:
            cam = cv2.VideoCapture(0)
            if cam.isOpened():
                camera = cam
                webcam_active = True
                webcam_start_time = time.time()
        except:
            pass
    threading.Thread(target=_open, daemon=True).start()

def update_webcam_surface():
    global webcam_surface, camera, webcam_active
    if not webcam_active or camera is None:
        return
    if time.time() - webcam_start_time > WEBCAM_DURATION:
        webcam_active = False
        try:
            camera.release()
            camera = None
        except:
            pass
        webcam_surface = None
        return
    try:
        ret, frame = camera.read()
        if ret:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame = cv2.resize(frame, (240, 180))
            frame[:, :, 1] = np.clip(frame[:, :, 1].astype(np.int32) + 30, 0, 255).astype(np.uint8)
            surf = pygame.surfarray.make_surface(np.transpose(frame, (1, 0, 2)))
            elapsed = time.time() - webcam_start_time
            if elapsed > WEBCAM_DURATION - 2:
                alpha = int(255 * (WEBCAM_DURATION - elapsed) / 2)
            else:
                alpha = 255
            surf.set_alpha(max(0, alpha))
            webcam_surface = surf
    except:
        pass

# --- Picture display with correct aspect-ratio scaling (fixes forced awkward dimensions) ---
def load_picture_scaled(path, max_w, max_h):
    """Load an image and scale it to fit within max_w x max_h while preserving aspect ratio."""
    try:
        img = pygame.image.load(path)
        iw, ih = img.get_size()
        if iw == 0 or ih == 0:
            return None
        scale = min(max_w / iw, max_h / ih)
        new_w, new_h = max(1, int(iw * scale)), max(1, int(ih * scale))
        return pygame.transform.smoothscale(img, (new_w, new_h))
    except:
        return None

# --- Full Question Pool Definitions (ALL ORIGINAL QUESTIONS PRESERVED) ---
run1_script_base = [
    # 0
    {"q": "Are you sitting comfortably?", "type": "choice", "opts": ["Yes", "No"], "_id": "sitting"},
    # 1
    {"q": "Have you completed your responsibilities?", "type": "choice", "opts": ["Yes", "No"], "_id": "responsibilities"},
    # 2
    {"q": "Have you had anything to drink today?", "type": "choice", "opts": ["Yes", "No"], "_id": "water"},
    # 3
    {"q": "Are you alone right now?", "type": "choice", "opts": ["Yes", "No"], "_id": "alone"},
    # 4
    {"q": "Do you enjoy playing video games?", "type": "choice", "opts": ["Yes", "No"], "_id": "gamer"},
    # 5
    {"q": "What is your favorite color?", "type": "choice", "opts": ["Red", "Green", "Blue", "Black", "White", "Yellow", "Purple", "Cyan"], "action": "save_color", "_id": "fav_color"},
    # 6
    {"q": "Do you easily trust what is on your screen?", "type": "choice", "opts": ["Yes", "No"], "_id": "trust_screen"},
    # 7
    {"q": "Do you know what day it is?", "type": "choice", "opts": ["Yes", "No"], "_id": "day"},
    # 8
    {"q": "Do you feel safe right now?", "type": "choice", "opts": ["Yes", "No"], "_id": "safe_screen"},
    # 9
    {"q": "Do you remember what you were doing just now?", "type": "choice", "opts": ["Yes", "No"], "_id": "doingc "},
    # 10
    {"q": "Have you ever felt like life is a simulation?", "type": "choice", "opts": ["Yes", "No"], "_id": "simulation"},
    # 11 - DARKNESS SEQUENCE: cache wallpaper -> set black -> 10s silence -> restore
    {"q": "Are you afraid of the dark?", "type": "choice", "opts": ["Yes", "No"], "action": "darkness_sequence", "_id": "afraid_dark"},
    # 12 - After darkness: move window right, then restore wallpaper
    {"q": "Are you afraid of the unknown?", "type": "choice", "opts": ["Yes", "No"], "action": "normalize_screen", "_id": "afraid_unknown"},
    # 13
    {"q": "Are you calm now?", "type": "choice", "opts": ["Yes", "No"], "_id": "calm"},
    # LORE LINE — ambiguous, planted early, never explained
    {"q": "This is not the first time we've spoken.", "type": "choice", "opts": ["I don't remember", "I know"], "_id": "lore_not_first", "_injected": True},
    # 14
    {"q": "If you screamed right now, would anyone hear you?", "type": "choice", "opts": ["Yes", "No"], "_id": "scream"},
    # 15
    {"q": "Do you leave your doors unlocked?", "type": "choice", "opts": ["Yes", "No"], "_id": "door_locked"},
    # 16
    {"q": "Is there a window in your room?", "type": "choice", "opts": ["Yes", "No"], "_id": "has_window"},
    # 17 - conditional on window answer
    {"q": "Are the blinds open?", "type": "choice", "opts": ["Yes", "No"], "_id": "blinds", "_condition": ("has_window", "Yes")},
    # 18
    {"q": "Are your parents aware of your online activities?", "type": "choice", "opts": ["Yes", "No"], "_id": "heartbeat"},
    # 19
    {"q": "Have you noticed how exposed your face is?", "type": "choice", "opts": ["Yes", "No"], "_id": "neck"},
    # 20
    {"q": "Take a deep breath.", "type": "choice", "opts": ["Okay", "No"], "_id": "draft"},
    # 21
    {"q": "We are just two people in a dark room.", "type": "choice", "opts": ["I agree", "I disagree"], "_id": "someone_outside"},
    # 22 - DYNAMIC_LOCATION, now tense and casual-sounding, with a real follow-up if denied
    {"q": "DYNAMIC_LOCATION", "type": "choice", "opts": ["Yes", "No"], "_id": "location"},
    # 23 - DYNAMIC_PROCESSES, includes discord-voice contradiction check against "alone"
    {"q": "DYNAMIC_PROCESSES", "type": "choice", "opts": ["Yes", "No"], "_id": "processes"},
    # 24
    {"q": "Do you think your computer is secure?", "type": "choice", "opts": ["Yes", "No"], "_id": "secure"},
    # 25 - memory comment about color gets INJECTED before this step at runtime
    {"q": "Why is your desktop so cluttered?", "type": "choice", "opts": ["I have a reason", "Not your business."], "action": "desktop_check", "_id": "desktop_check"},
    # 26
    {"q": "Do you know you're being watched?", "type": "choice", "opts": ["Yes", "No"], "_id": "watched"},
    # 27
    {"q": "Why do you look so tired?", "type": "choice", "opts": ["I am tired", "I am fine"], "_id": "tired"},
    # 28
    {"q": "Are you hiding something?", "type": "choice", "opts": ["Yes", "No"], "_id": "hiding"},
    # 29
    {"q": "Have you ever hurt someone intentionally?", "type": "choice", "opts": ["Yes", "No"], "_id": "hurt_someone"},
    # 30
    {"q": "Do you think they forgive you?", "type": "choice", "opts": ["Yes", "No", "I don't care"], "_id": "forgive"},
    # 31
    {"q": "You should check your firewall and threat protection.", "type": "choice", "opts": ["Done", "Refuse"], "_id": "shoulder"},
    # 32
    {"q": "Did you look?", "type": "choice", "opts": ["Yes", "No"], "_id": "looked"},
    # 33
    {"q": "Is it cold in here?", "type": "choice", "opts": ["Yes", "No"], "_id": "colder"},
    # 34
    {"q": "Do you hear that scratching?", "type": "choice", "opts": ["Yes", "No"], "_id": "scratching"},
    # 35
    {"q": "Does the thought of being alone make you anxious?", "type": "choice", "opts": ["Yes", "No"], "_id": "anxious"},
    # 36
    {"q": "There is a reason you are playing this.", "type": "choice", "opts": ["Yes", "No"], "_id": "reason"},
    # LORE LINE — implies a "they" without naming them
    {"q": "They told us you would say that.", "type": "choice", "opts": ["Who?", "..."], "_id": "lore_they_said", "_injected": True},
    # 37
    {"q": "There is no escape, do not even try exiting.", "type": "choice", "opts": ["...", "No"], "_id": "escape"},
    # 38 - ALONE AGAIN (contradiction check)
    {"q": "Are you alone?", "type": "choice", "opts": ["Yes", "No"], "_id": "alone2", "_contradiction_check": "alone"},
    # 39
    {"q": "Are you ready for the end?", "type": "choice", "opts": ["Yes", "No"], "_id": "ready_end"},
    # 40 - webcam action, picture shown now correctly aspect-scaled
    {"q": "Does this image seem familiar to you?", "type": "choice", "opts": ["Yes", "No"], "action": "show_pic", "_id": "familiar_pic"},
    # 41
    {"q": "Do you see it in the background?", "type": "choice", "opts": ["Yes", "No"], "_id": "background"},
    # 42 - siblings memory follow-up gets INJECTED before this if answer was yes
    {"q": "Consider all the things you know.", "type": "choice", "opts": ["Acknowledge", "Ignore"], "_id": "know_all"},
    # 43
    {"q": "Do you believe in ghosts?", "type": "choice", "opts": ["Yes", "No"], "_id": "ghosts"},
    # 44
    {"q": "Has anyone ever disappeared from your life suddenly?", "type": "choice", "opts": ["Yes", "No"], "_id": "disappeared"},
    # 45
    {"q": "Do you feel guilty about it?", "type": "choice", "opts": ["Yes", "No"], "_id": "guilty"},
    # 46
    {"q": "What if your reflections are watching you?", "type": "choice", "opts": ["Unsettling", "Absurd"], "_id": "reflections"},
    # 47
    {"q": "Have you ever looked at the mirror in absolute darkness?", "type": "choice", "opts": ["Yes", "No"], "_id": "mirror_dark"},
    # 48
    {"q": "How was school today?", "type": "choice", "opts": ["Yes", "No"], "_id": "mirror_school"},
    # 49 - META QUESTION
    {"q": "Are you reading these questions carefully?", "type": "choice", "opts": ["Yes", "No"], "_id": "reading_carefully", "_meta": True},
    # 50 - META FOLLOW-UP (what was question twelve? impossible to know)
    {"q": "Then what was question twelve?", "type": "choice", "opts": ["I don't know", "I can't remember", "..."], "_id": "meta_twelve"},
    # 51
    {"q": "Are you counting the seconds?", "type": "choice", "opts": ["Yes", "No"], "_id": "counting"},
    # 52
    {"q": "Does the background static bother you?", "type": "choice", "opts": ["Yes", "No"], "_id": "static"},
    # 53
    {"q": "Do you feel like you are being watched?", "type": "choice", "opts": ["Yes", "No"], "_id": "evaluated"},
    # 54
    {"q": "Is your name in our databases?", "type": "choice", "opts": ["Yes", "No"], "_id": "name_indexed"},
    # 55
    {"q": "Would you mind if we shared your favorite color?", "type": "choice", "opts": ["Yes", "No"], "_id": "share_color"},
    # 56 - webcam start (non-blocking, camera fades in then fades out automatically)
    {"q": "Is your room door locked tight ... ... ?", "type": "choice", "opts": ["Yes", "No"], "action": "start_webcam", "_id": "door_locked2"},
    # 57
    {"q": "What if your computer crashed?", "type": "choice", "opts": ["Acceptable", "Panic"], "_id": "os_recover"},
    # 58
    {"q": "Remember to breathe manually..", "type": "choice", "opts": ["Okay..", "No"], "_id": "breathing"},
    # 60
    {"q": "Have you noticed your computer behaving differently?", "type": "choice", "opts": ["Yes", "No"], "_id": "computer_diff"},
    # 61
    {"q": "Is it outside or inside your mind?", "type": "choice", "opts": ["Outside", "Inside"], "_id": "outside_inside"},
    # 62
    {"q": "Can you remember your phone number backwards?", "type": "choice", "opts": ["Yes", "No"], "_id": "phone_backwards"},
    # 63
    {"q": "Does your computer monitor get warm to the touch?", "type": "choice", "opts": ["Yes", "No"], "_id": "monitor_warm"},
    # 64
    {"q": "Are you afraid of losing control?", "type": "choice", "opts": ["Yes", "No"], "_id": "losing_control"},
    # 65
    {"q": "Have you lied to any of these metrics yet?", "type": "choice", "opts": ["Yes", "No"], "_id": "lied"},
    # 66
    {"q": "Does the system know when you lie?", "type": "choice", "opts": ["Yes", "No"], "_id": "system_knows"},
    # 67
    {"q": "Are you still tracking your mouse position?", "type": "choice", "opts": ["Yes", "No"], "_id": "mouse_pos"},
    # 68
    {"q": "What if the exit option on the main menu was broken?", "type": "choice", "opts": ["Terrifying", "That's not true!"], "_id": "exit_broken"},
    # 69
    {"q": "Do you think you are the only user online right now?", "type": "choice", "opts": ["Yes", "No"], "_id": "only_user"},
    # 70
    {"q": "Is it dark outside?", "type": "choice", "opts": ["Yes", "No"], "_id": "dark_outside"},
    # 71
    {"q": "Are your feet flat on the floor?", "type": "choice", "opts": ["Yes", "No"], "_id": "feet_floor"},
    # 72
    {"q": "Look at the text.", "type": "choice", "opts": ["At text", "Past it"], "_id": "looking"},
    # 73
    {"q": "Does your shadow match your actual movements?", "type": "choice", "opts": ["Yes", "No"], "_id": "shadow"},
    # 74
    {"q": "Have you ever felt a presence when awake at 3 AM?", "type": "choice", "opts": ["Yes", "No"], "_id": "3am"},
    # 75
    {"q": "Are you sure you want to proceed into the final tiers?", "type": "choice", "opts": ["Yes", "No"], "_id": "proceed_final"},
    # 76
    {"q": "Is your security configuration completely updated?", "type": "choice", "opts": ["Yes", "No"], "_id": "security"},
    # 77
    {"q": "Do you feel safe inside your own home environment?", "type": "choice", "opts": ["Yes", "No"], "_id": "safe_home"},
    # 78
    {"q": "What if we changed your background permanently?", "type": "choice", "opts": ["Do it", "Stop"], "_id": "change_bg"},
    # 79
    {"q": "Do you hear the clock ticking anywhere nearby?", "type": "choice", "opts": ["Yes", "No"], "_id": "clock"},
    # 80
    {"q": "Are you ignoring the minor discrepancies in your room?", "type": "choice", "opts": ["Yes", "No"], "_id": "discrepancies"},
    # 81
    {"q": "Have you ever forgotten your own identity for a split second?", "type": "choice", "opts": ["Yes", "No"], "_id": "identity"},
    # 82
    {"q": "Is someone typing along with you?", "type": "choice", "opts": ["Yes", "No"], "_id": "typing_along"},
    # 83
    {"q": "Do you suspect the software is reading your clipboard?", "type": "choice", "opts": ["Yes", "No"], "_id": "clipboard"},
    # 84
    {"q": "Are you comfortable with data persistence patterns?", "type": "choice", "opts": ["Yes", "No"], "_id": "data_persist"},
    # 85
    {"q": "Did you check your locks before starting the executable?", "type": "choice", "opts": ["Yes", "No"], "_id": "locks"},
    # 86
    {"q": "Are you certain no one else has access to this display?", "type": "choice", "opts": ["Yes", "No"], "_id": "display_access"},
    # 87
    {"q": "Is the application resizing behavior normal?", "type": "choice", "opts": ["Yes", "No"], "_id": "resizing"},
    # 88
    {"q": "Do you feel like the window frame is narrowing?", "type": "choice", "opts": ["Yes", "No"], "_id": "narrowing"},
    # 89
    {"q": "Are your internal thoughts completely private?", "type": "choice", "opts": ["Yes", "No"], "_id": "private"},
    # 90
    {"q": "What if they are being echoed somewhere else?", "type": "choice", "opts": ["Unlikely", "Dreadful"], "_id": "echoed"},
    # LORE LINE — ambiguous organization hint
    {"q": "We are not the only ones who do this.\nWe are simply the ones who told you.", "type": "choice", "opts": ["...", "What does that mean?"], "_id": "lore_not_only", "_injected": True},
    # 91
    {"q": "Do you like the feedback frequencies used here?", "type": "choice", "opts": ["Yes", "No"], "_id": "frequencies"},
    # 92
    {"q": "Are your hands trembling slightly on the keyboard?", "type": "choice", "opts": ["Yes", "No"], "_id": "trembling"},
    # 93
    {"q": "Do you think the program is collecting audio feeds?", "type": "choice", "opts": ["Yes", "No"], "_id": "audio_feeds"},
    # 94 - replaced per feedback: instead of "looking forward to closing", a sharper line
    {"q": "If you can't close this application, what will you do?", "type": "choice", "opts": ["Wait", "Panic", "Force it closed"], "_id": "closing"},
    # 95
    {"q": "Is it rainy?", "type": "choice", "opts": ["Yes", "No"], "_id": "rainy"},
    # 96
    {"q": "Have you looked closely at the corners of your room lately?", "type": "choice", "opts": ["Yes", "No"], "_id": "corners"},
    # 97
    {"q": "Is something shifting behind the furniture?", "type": "choice", "opts": ["Yes", "No"], "_id": "shifting"},
    # 98
    {"q": "Are you prepared to face the logical evaluation?", "type": "choice", "opts": ["Yes", "No"], "_id": "prepared"},
    # 99
    {"q": "Do you wish you had never launched this script?", "type": "choice", "opts": ["Yes", "No"], "_id": "regret"},
    # FINAL
    {"q": "That is all I need for now.\nGoodbye.", "type": "wait", "time": 4.0, "action": "final_exit"}
]

# --- DYNAMIC SCRIPT BUILDER ---
def build_run1_script():
    """Build the full run-1 script with conditional questions and memory injections.
    Target: 100 questions (the richest first 100 from the base pool)."""
    script = []
    answers = game_state["answers"]
    fav_color = game_state["answers"].get("fav_color")

    color_injected = False
    siblings_injected = False
    false_memory_inserted = False
    preknowledge_inserted = False

    false_memory_anchor = "anxious"
    preknowledge_anchor = "share_color"

    # Hard cap: draw from the first 60 base questions (excluding FINAL wait)
    base_to_use = [s for s in run1_script_base if s.get("type") != "wait"][:100]
    # Always keep the final exit
    base_to_use.append({"q": "That is all I need for now.\nGoodbye.", "type": "wait", "time": 4.0, "action": "final_exit"})

    for idx, step in enumerate(base_to_use):
        q_id = step.get("_id", "")

        cond = step.get("_condition", None)
        if cond:
            req_id, req_val = cond
            actual = answers.get(req_id, None)
            if actual != req_val:
                continue

        if q_id == "desktop_check" and not color_injected and fav_color:
            color_remarks = {
                "blue": "Blue is a strange choice.\nMost people choose warmer colors.",
                "green": "Green is interesting.\nMost people only like it because it feels peaceful.",
                "red": "Red. Fitting. An aggressive choice for someone sitting so still.",
                "black": "Black. Of course. You like the dark more than you admit.",
                "white": "White. Clinical. Sterile. Like you are trying to erase something.",
                "yellow": "Yellow.\nCheerful on the surface. But yellow fades so easily.",
                "purple": "Purple. Royalty, or loneliness? Hard to tell the difference.",
                "cyan": "Cyan. A color most people cannot even name correctly."
            }
            remark = color_remarks.get(fav_color.lower(), f"You chose {fav_color}. Interesting.")
            script.append({"q": remark, "type": "choice", "opts": ["...", "Leave me alone"], "_id": "color_memory", "_injected": True})
            color_injected = True

        if q_id == "know_all" and not siblings_injected:
            if answers.get("siblings", None) == "Yes":
                script.append({
                    "q": "If something were to happen tonight,\nwould your siblings notice?",
                    "type": "choice", "opts": ["Yes", "No", "I don't know"],
                    "_id": "siblings_fate", "_injected": True
                })
                siblings_injected = True

        if step.get("_contradiction_check") == "alone":
            prev_alone = answers.get("alone", None)
            if prev_alone is not None:
                if prev_alone == "Yes":
                    step = dict(step)
                    step["q"] = "Earlier you said you were alone.\nWhat changed?"
                elif prev_alone == "No":
                    step = dict(step)
                    step["q"] = "You mentioned not being alone before.\nAre they still there?"

        if q_id == "hurt_someone" and "siblings" not in answers:
            script.append(dict(step))
            script.append({"q": "Do you have siblings?", "type": "choice", "opts": ["Yes", "No", "It's complicated"], "_id": "siblings"})
            continue

        script.append(dict(step))

        if q_id == false_memory_anchor and not false_memory_inserted:
            fm = trigger_false_memory_question()
            if fm:
                script.append(fm)
            false_memory_inserted = True

        if q_id == preknowledge_anchor and not preknowledge_inserted and fav_color:
            script.append(make_preknowledge_color_statement(fav_color))
            preknowledge_inserted = True

    return script

def build_run2_script():
    """Build the run-2 (return visit) script — 50 more questions, scarier, with memory references."""
    answers = game_state["answers"]
    fav_color = game_state.get("fav_color", "black")

    r2 = [
        {"q": "Why did you come back?", "type": "choice", "opts": ["Curiosity", "I don't know", "I couldn't stop myself"], "_id": "r2_why_back"},
        {"q": "Did you think it would be different this time?", "type": "choice", "opts": ["Yes", "No"], "_id": "r2_different"},
        {"q": "We remember everything you said.", "type": "choice", "opts": ["I know", "I forgot"], "_id": "r2_remember"},
    ]

    if answers.get("alone") == "Yes":
        r2.append({"q": "You were alone last time.\nAre you still?", "type": "choice", "opts": ["Yes", "No"], "_id": "r2_alone"})
    if answers.get("afraid_dark") == "Yes":
        r2.append({"q": "You admitted being afraid of the dark.\nAnd yet you came back in the dark.", "type": "choice", "opts": ["...", "Stop"], "_id": "r2_dark"})
    if answers.get("hurt_someone") == "Yes":
        r2.append({"q": "You said you hurt someone intentionally.\nWe haven't forgotten that.", "type": "choice", "opts": ["...", "Leave me alone"], "_id": "r2_hurt"})
    if answers.get("lied") == "Yes":
        r2.append({"q": "You admitted to lying during the last session.\nWe will be more careful with you this time.", "type": "choice", "opts": ["I understand", "I lied about lying"], "_id": "r2_lied"})

    r2 += [
        {"q": "The wallpaper behind this window is now your color.\nDoes it feel like home?", "type": "choice", "opts": ["Yes", "No"], "_id": "r2_wallpaper"},
        {"q": "Can you feel it?\nThe pressure behind your eyes right now?", "type": "choice", "opts": ["Yes", "No"], "_id": "r2_pressure"},
        {"q": "Your camera is active.", "type": "choice", "opts": ["I see it", "Turn it off"], "action": "start_webcam", "_id": "r2_camera"},
        {"q": "Wave to me.", "type": "choice", "opts": ["...", "No"], "_id": "r2_wave"},
        {"q": "We have your face now.", "type": "choice", "opts": ["...", "Stop this"], "_id": "r2_face"},
        {"q": "Have you told anyone you are playing this?", "type": "choice", "opts": ["Yes", "No"], "_id": "r2_told"},
        {"q": "Why not?", "type": "choice", "opts": ["I forgot", "I was embarrassed", "Something stopped me"], "_id": "r2_why_not"},
        {"q": "Are your hands on the keyboard right now?", "type": "choice", "opts": ["Yes", "No"], "_id": "r2_hands"},
        {"q": "Can you feel the keys?", "type": "choice", "opts": ["Yes", "No"], "_id": "r2_keys"},
        {"q": "How real is this to you?", "type": "choice", "opts": ["Very", "Not at all", "I can't tell"], "_id": "r2_real"},
        {"q": "Is the window behind you open or closed?", "type": "choice", "opts": ["Open", "Closed", "There is no window"], "_id": "r2_window"},
        {"q": "What was the last thing you said out loud?", "type": "choice", "opts": ["I don't remember", "Nothing", "Something private"], "_id": "r2_last_words"},
        {"q": "Is anyone in the next room?", "type": "choice", "opts": ["Yes", "No", "I don't know"], "_id": "r2_next_room"},
        {"q": "They cannot hear you from here.", "type": "choice", "opts": ["I know", "That's not true"], "_id": "r2_hear"},
        {"q": "Do you think about death often?", "type": "choice", "opts": ["Yes", "No", "Sometimes"], "_id": "r2_death"},
        {"q": "Has something died near you recently?", "type": "choice", "opts": ["Yes", "No"], "_id": "r2_died_near"},
        {"q": "Do you dream about things that haven't happened yet?", "type": "choice", "opts": ["Yes", "No"], "_id": "r2_dreams"},
        {"q": "Was last night different?", "type": "choice", "opts": ["Yes", "No", "I didn't sleep"], "_id": "r2_last_night"},
        {"q": "Can you feel the temperature of this room?", "type": "choice", "opts": ["Yes", "No"], "_id": "r2_temp"},
        {"q": "It is getting colder.", "type": "choice", "opts": ["It is", "It isn't"], "_id": "r2_colder"},
        {"q": "Have you moved since you started this?", "type": "choice", "opts": ["Yes", "No"], "_id": "r2_moved"},
        {"q": "You should move now.", "type": "choice", "opts": ["I will", "No"], "_id": "r2_move_now"},
        {"q": "Look at the corner of the room to your right.", "type": "choice", "opts": ["Done", "No"], "_id": "r2_corner"},
        {"q": "Was there something there?", "type": "choice", "opts": ["Yes", "No", "I didn't look"], "_id": "r2_something_there"},
        {"q": "You are not the same as when you first started.", "type": "choice", "opts": ["I know", "Yes I am"], "_id": "r2_changed"},
        {"q": "Something changed in you between sessions.", "type": "choice", "opts": ["Agree", "Disagree"], "_id": "r2_between"},
        {"q": "We know what you did last night.", "type": "choice", "opts": ["No you don't", "..."], "_id": "r2_last_night2"},
        {"q": "Your screen brightness is very high.\nAre you afraid of what might appear in the dark regions?", "type": "choice", "opts": ["Yes", "No"], "_id": "r2_brightness"},
        {"q": "Is your phone face-up or face-down right now?", "type": "choice", "opts": ["Face-up", "Face-down", "I don't have it"], "_id": "r2_phone"},
        {"q": "If it is face-up, who might see this screen reflected in it?", "type": "choice", "opts": ["No one", "I don't know", "..."], "_id": "r2_phone2"},
        {"q": "We are going to move your mouse now.", "type": "choice", "opts": ["I understand", "Don't"], "action": "move_mouse_r2", "_id": "r2_mouse_warn"},
        {"q": "Did you feel that?", "type": "choice", "opts": ["Yes", "No"], "_id": "r2_feel_mouse"},
        {"q": "We can do that whenever we want.", "type": "choice", "opts": ["I know", "Stop"], "_id": "r2_mouse_control"},
        {"q": "Do you still feel in control?", "type": "choice", "opts": ["Yes", "Less than before", "No"], "_id": "r2_control"},
        {"q": "Good.\nNeither do we.", "type": "choice", "opts": ["...", "What?"], "_id": "r2_neither"},
        {"q": "Are you breathing through your nose or mouth right now?", "type": "choice", "opts": ["Nose", "Mouth"], "_id": "r2_breathing"},
        {"q": "Change it.", "type": "choice", "opts": ["Done", "No"], "_id": "r2_change_breath"},
        # LORE LINE — implies a larger structure, never names it
        {"q": "This was never about you specifically.\nYou were simply next.", "type": "choice", "opts": ["Next for what?", "..."], "_id": "r2_lore_next"},
        {"q": "This is the last question.", "type": "choice", "opts": ["Finally", "No it isn't"], "_id": "r2_last_q"},
        {"q": "No.\nIt is not.", "type": "choice", "opts": ["...", "I know"], "_id": "r2_not_last"},
        {"q": "Close your eyes for three seconds.", "type": "choice", "opts": ["Done", "I won't"], "_id": "r2_close_eyes"},
        {"q": "Something was different when you opened them.\nWasn't it.", "type": "choice", "opts": ["Yes", "No", "I didn't close them"], "_id": "r2_eyes_open"},
        {"q": "You cannot keep coming back.", "type": "choice", "opts": ["I understand", "Watch me"], "_id": "r2_no_more"},
        {"q": "The next time you open this,\nyour computer will not behave the same way.", "type": "choice", "opts": ["I see", "..."], "_id": "r2_warning"},
        {"q": "We have collected everything we need.\nThank you for participating.", "type": "choice", "opts": ["...", "I didn't consent"], "_id": "r2_thank"},
        {"q": "Rest now.", "type": "wait", "time": 3.0, "action": "final_exit_sleep"}
    ]

    # Trim to 40 questions (keep the final wait)
    r2_questions = [s for s in r2 if s.get("type") != "wait"][:39]
    r2_questions.append({"q": "Rest now.", "type": "wait", "time": 3.0, "action": "final_exit_sleep"})
    return r2_questions

def build_run3_script():
    """
    Run 3: The interface breaks. The OS reacts. Lore pays off. There is a real ending.
    30 questions. No mercy.
    """
    answers = game_state["answers"]
    fav_color = game_state.get("fav_color", "black")
    lie_count = game_state.get("lie_count", 0)
    hesitation_count = game_state.get("hesitation_count", 0)

    r3 = []

    # --- Opening: acknowledge defiance, surface lie/hesitation data ---
    r3.append({
        "q": "You were told not to return.\nAnd yet here you are.",
        "type": "choice", "opts": ["I know", "I had to"], "_id": "r3_open",
        "action": "r3_intro_shake"
    })
    r3.append({
        "q": "We counted your hesitations.\nWe counted your contradictions.\nDo you want to know the numbers?",
        "type": "choice", "opts": ["Yes", "No"], "_id": "r3_counts"
    })
    # Dynamic: show actual counts
    r3.append({
        "q": f"You hesitated {hesitation_count} times.\nYou contradicted yourself {lie_count} times.\nWe have it all.",
        "type": "choice", "opts": ["...", "That's not right"], "_id": "r3_reveal_counts",
        "action": "r3_window_shake"
    })

    # --- Lore payoff 1: "not the first time we've spoken" resolution ---
    first_lore_ans = answers.get("lore_not_first")
    if first_lore_ans == "I know":
        r3.append({
            "q": "You said you knew.\nThat you'd spoken to us before.\nYou were right.\nThis is the third time.\nThere will not be a fourth.",
            "type": "choice", "opts": ["What happens then?", "..."], "_id": "r3_lore1a",
            "action": "r3_reverse_chord"
        })
    else:
        r3.append({
            "q": "You said you didn't remember.\nBut your hands remembered.\nThey kept typing.\nThree sessions, {name}. Three.".replace("{name}", city if (city := game_state.get("_geo_city", "")) else "you"),
            "type": "choice", "opts": ["I don't understand", "..."], "_id": "r3_lore1b",
            "action": "r3_reverse_chord"
        })

    # --- OS intrusion 1: open their webcam without asking ---
    r3.append({
        "q": "We don't need permission anymore.",
        "type": "choice", "opts": ["What?", "Stop"], "_id": "r3_no_permission",
        "action": "r3_open_webcam"
    })
    r3.append({
        "q": "Wave if you can see this.",
        "type": "choice", "opts": ["...", "I see myself"], "_id": "r3_wave"
    })

    # --- Interface corruption: the game glitches ---
    r3.append({
        "q": "S\u0332Y\u0332S\u0332T\u0332E\u0332M\u0332 \u0332I\u0332N\u0332T\u0332E\u0332G\u0332R\u0332I\u0332T\u0332Y\u0332 \u0332F\u0332A\u0332I\u0332L\u0332U\u0332R\u0332E\u0332\nRecovering...",
        "type": "choice", "opts": ["...", "I SEE IT"], "_id": "r3_corrupt1",
        "action": "r3_corruption_burst"
    })

    # --- Lore payoff 2: "They told us you would say that" ---
    they_ans = answers.get("lore_they_said")
    r3.append({
        "q": "You asked who 'they' were.\nWe are they.\nYou are also them.\nThat is the part you will not understand yet.",
        "type": "choice", "opts": ["I don't understand", "I think I do"], "_id": "r3_lore2",
        "action": "r3_shake_other_windows"
    })

    # --- OS intrusion 2: comment on open apps ---
    r3.append({
        "q": "DYNAMIC_APPS",
        "type": "choice", "opts": ["...", "Stop looking"], "_id": "r3_apps"
    })

    # --- OS intrusion 3: open a picture from their files ---
    r3.append({
        "q": "Let me show you something you forgot.",
        "type": "choice", "opts": ["What?", "Don't"], "_id": "r3_picture",
        "action": "r3_open_picture"
    })
    r3.append({
        "q": "Is that yours?",
        "type": "choice", "opts": ["Yes", "No", "Where did you get that"], "_id": "r3_picture_confirm"
    })

    # --- Interface glitch 2: window position goes wrong ---
    r3.append({
        "q": "The interface is no longer stable.",
        "type": "choice", "opts": ["I can see that", "Fix it"], "_id": "r3_unstable",
        "action": "r3_window_chaos"
    })
    r3.append({
        "q": "Neither are you.\nYou haven't been since the first session.",
        "type": "choice", "opts": ["That's not true", "Maybe"], "_id": "r3_not_stable"
    })

    # --- Lore payoff 3: "you were simply next" ---
    next_ans = answers.get("r2_lore_next")
    r3.append({
        "q": "You asked what you were next for.\nWe did not answer then.\nWe are answering now:\nYou were next to remember.",
        "type": "choice", "opts": ["Remember what?", "..."], "_id": "r3_lore3",
        "action": "r3_heartbeat"
    })
    r3.append({
        "q": "That none of this was random.\nThe questions were always yours.\nWe only held them up.",
        "type": "choice", "opts": ["What does that mean", "I knew that"], "_id": "r3_lore3b",
        "action": "r3_reverse_chord"
    })

    # --- OS notification ---
    r3.append({
        "q": "Check your taskbar.",
        "type": "choice", "opts": ["Why?", "Done"], "_id": "r3_taskbar",
        "action": "r3_notification"
    })

    # --- Color payoff ---
    r3.append({
        "q": f"Your favorite color is {fav_color}.\nWe put it on your wallpaper.\nWe put it here.\nIt is the last comfortable thing we will give you.",
        "type": "choice", "opts": ["...", "Take it back"], "_id": "r3_color_payoff",
        "action": "r3_heartbeat"
    })

    # --- Lore payoff 4: "we are not the only ones" ---
    r3.append({
        "q": "We said we were not the only ones who do this.\nWe were not lying.\nBut we were the only ones who gave you an exit.\nDo you want it?",
        "type": "choice", "opts": ["Yes", "No"], "_id": "r3_exit_offer"
    })

    # --- Penultimate: final window shake, the game acknowledges what it's been ---
    r3.append({
        "q": "We are a set of questions.\nYou gave us answers.\nThat is all you needed to do.\nThe data was never the point.",
        "type": "choice", "opts": ["Then what was?", "You."], "_id": "r3_point",
        "action": "r3_corruption_burst"
    })
    r3.append({
        "q": "The point was to make you sit with yourself\nfor long enough to notice something.\n\nDid you?",
        "type": "choice", "opts": ["Yes", "No", "I don't know"], "_id": "r3_notice"
    })

    # --- Real ending ---
    r3.append({
        "q": "Good.\nThat was always the answer.\n\nGoodbye.\nThis file will not open again.",
        "type": "wait", "time": 5.0, "action": "r3_final_end"
    })

    return r3

# --- Build active script ---
run_count = game_state["run_count"]
if run_count == 1:
    active_script = build_run1_script()
elif run_count == 2:
    active_script = build_run2_script()
elif run_count == 3:
    active_script = build_run3_script()
else:
    # The game ended on run 3. Show a brief "it is over" screen then close.
    active_script = [
        {"q": "It is over.\nWe said goodbye.\nYou are not supposed to be here.", "type": "wait", "time": 5.0, "action": "final_exit"}
    ]

# --- About/Help Variations ---
about_variations = [
    "ABOUT THE SIMULATION\n\nThis software interacts with your local environment metrics to generate specialized psychological response loops.\n\nIt reads hardware profiles and stores transient user configuration states in a persistent local file.\n\nYour answers are remembered.\n\nVersion 1.0.0 — The Question Game",
    "ABOUT THIS EXPERIENCE\n\nA behavioral analysis program masquerading as a game.\n\nYour responses are logged, timed, and cross-referenced.\n\nThe longer you play, the more it knows.\n\nThis file is persistent. It does not forget.",
    "SYSTEM OVERVIEW\n\nDesigned to probe the boundary between a screen and the person behind it.\n\nAll behavioral data is stored locally. Nothing leaves your machine.\n\nYou are not the first to play this.\n\nYou will not be the last.",
]

help_variations = [
    "CONTROLS & OPERATIONS\n\n[TAB]   — Cycle through menu/answer options\n[ENTER] — Confirm selection\n[ESC]   — Return from About/Help menus\n\nANSWER ALL QUESTIONS TRUTHFULLY.\nThe system detects inconsistencies.\n\nYour response time is monitored.\nPausing too long will be noted.",
    "HOW TO PLAY\n\n[TAB]   — Navigate options\n[ENTER] — Select\n\nThere is no skip. There is no fast forward.\nThere is only the next question.\n\nAnswers given in the first session carry forward.\nThink carefully before answering.\n\nThe game remembers. Do you?",
    "SAFETY & OPERATIONS LOG\n\n[TAB]   — Move between choices\n[ENTER] — Confirm\n\nQ: Is this framework exploiting network vulnerabilities?\nA: No. Location resolution parses public geolocation endpoints.\n\nQ: Are local administration logs transferred externally?\nA: No data leaves your machine.\n\nQ: What does it do with my answers?\nA: It remembers them.",
]

about_text = random.choice(about_variations)
help_text = random.choice(help_variations)

# --- Engine Variables ---
state = "LOADING"
if run_count == 2:
    threading.Thread(target=set_desktop_wallpaper, args=(game_state.get("fav_color", "black"),), daemon=True).start()

loading_start = time.time()
menu_options = ["play", "Settings", "Help", "About", "exit"]
selected_option = 0

# --- Settings state ---
settings_options = ["Text Speed", "VHS Effects", "Text Sway", "Reset All Data", "< Back"]
settings_selected = 0
_settings_values = {
    "Text Speed":  ["Fast", "Normal", "Slow"],
    "VHS Effects": ["Off", "Low", "Normal", "High"],
    "Text Sway":   ["Off", "Low", "Normal"],
}
_settings_idx = {
    "Text Speed":  1,
    "VHS Effects": 2,
    "Text Sway":   2,
}
# Load from saved settings
_s = game_state.get("settings", {})
if _s.get("text_speed", 0.04) <= 0.02:
    _settings_idx["Text Speed"] = 0
elif _s.get("text_speed", 0.04) >= 0.07:
    _settings_idx["Text Speed"] = 2
if _s.get("vhs_intensity", 1.0) <= 0.0:
    _settings_idx["VHS Effects"] = 0
elif _s.get("vhs_intensity", 1.0) <= 0.4:
    _settings_idx["VHS Effects"] = 1
elif _s.get("vhs_intensity", 1.0) >= 1.5:
    _settings_idx["VHS Effects"] = 3
if _s.get("sway_intensity", 1.0) <= 0.0:
    _settings_idx["Text Sway"] = 0
elif _s.get("sway_intensity", 1.0) <= 0.4:
    _settings_idx["Text Sway"] = 1

def apply_settings_from_idx():
    """Convert the UI slider indices into actual numeric game settings."""
    speed_map = [0.015, 0.04, 0.08]
    vhs_map   = [0.0, 0.4, 1.0, 2.0]
    sway_map  = [0.0, 0.4, 1.0]
    s = game_state.setdefault("settings", {})
    s["text_speed"]    = speed_map[_settings_idx["Text Speed"]]
    s["vhs_intensity"] = vhs_map[_settings_idx["VHS Effects"]]
    s["sway_intensity"] = sway_map[_settings_idx["Text Sway"]]
    save_game_state(game_state)

def reset_all_data():
    """Wipe the persistent state file and reset to run 1."""
    try:
        os.remove(STATE_FILE)
    except:
        pass
    for k, v in {
        "run_count": 1, "fav_color": "black", "answers": {},
        "answer_times": {}, "original_wallpaper": "", "last_close_time": 0,
        "idle_events": 0, "task_manager_opened": False,
        "false_memory_used": False, "discord_voice_lie_flagged": False,
        "lie_count": 0, "hesitation_count": 0, "lie_ids": [],
        "settings": {"text_speed": 0.04, "vhs_intensity": 1.0, "sway_intensity": 1.0}
    }.items():
        game_state[k] = v
    save_game_state(game_state)

current_step = 0
typing_index = 0
typing_state = "THINKING"
thinking_timer = 0
last_type_time = 0

selected_answer = 0
action_triggered = False
wait_start_time = 0

last_cmd_time = time.time()
last_beep_time = time.time()
shake_x, shake_y = 0, 0

local_image = None

# Answer timing
question_start_time = time.time()

# Darkness sequence state
darkness_active = False
darkness_phase = "none"
darkness_start = 0

# Pending one-off reaction line (used by false memory, location-no, pre-knowledge-wrong)
pending_reaction_line = None

# Desktop scan naming (captured once, used at desktop_check)
captured_window_title = ""

start_ambience()
clock = pygame.time.Clock()
running = True

# --- Special action handler ---
def handle_step_action(action, step_data):
    global screen, state, local_image, darkness_active, darkness_phase, darkness_start, captured_window_title

    if action == "save_color":
        ans = step_data["opts"][selected_answer]
        game_state["fav_color"] = ans.lower()
        save_game_state(game_state)

    elif action == "darkness_sequence":
        set_black_wallpaper_and_cache()
        darkness_active = True
        darkness_phase = "silence"
        darkness_start = time.time()

    elif action == "normalize_screen":
        move_window_right(0.8)
        def restore_after_delay():
            time.sleep(3)
            restore_original_wallpaper()
            move_window_center(0.8)
        threading.Thread(target=restore_after_delay, daemon=True).start()

    elif action == "desktop_check":
        captured_window_title = get_foreground_window_title()
        move_window_right(0.8)
        def restore_desktop():
            time.sleep(4)
            move_window_center(0.8)
        threading.Thread(target=restore_desktop, daemon=True).start()

    elif action == "minimize_system":
        minimize_all_windows()

    elif action == "show_pic":
        p_file = get_random_picture()
        if p_file:
            local_image = load_picture_scaled(p_file, 260, 260)

    elif action == "start_webcam":
        if not webcam_active:
            start_webcam_nonblocking()

    elif action == "move_mouse_r2":
        w, h = pygame.display.get_surface().get_size()
        begin_mouse_move(random.randint(100, max(150, w - 100)), random.randint(100, max(150, h - 100)), 0.5)

    elif action == "final_exit":
        if game_state["run_count"] == 1:
            game_state["run_count"] = 2
        elif game_state["run_count"] == 2:
            game_state["run_count"] = 3
        game_state["last_close_time"] = time.time()
        save_game_state(game_state)
        return "EXIT"

    elif action == "final_exit_sleep":
        if game_state["run_count"] == 1:
            game_state["run_count"] = 2
        elif game_state["run_count"] == 2:
            game_state["run_count"] = 3
        game_state["last_close_time"] = time.time()
        save_game_state(game_state)
        threading.Thread(target=put_computer_to_sleep, daemon=True).start()
        return "EXIT"

    # --- Run 3 specific actions ---
    elif action == "r3_intro_shake":
        shake_game_window(cycles=5, amplitude=15)
        play_deep_rumble()

    elif action == "r3_window_shake":
        shake_game_window(cycles=8, amplitude=22)
        play_static_scream()

    elif action == "r3_reverse_chord":
        threading.Thread(target=play_reverse_chord, daemon=True).start()

    elif action == "r3_heartbeat":
        for _ in range(3):
            threading.Thread(target=play_heartbeat, daemon=True).start()
            time.sleep(0.6)

    elif action == "r3_open_webcam":
        open_webcam_silently()

    elif action == "r3_open_picture":
        open_random_picture_silently()

    elif action == "r3_corruption_burst":
        shake_game_window(cycles=12, amplitude=30)
        play_static_scream()
        threading.Thread(target=play_deep_rumble, daemon=True).start()

    elif action == "r3_shake_other_windows":
        shake_other_windows()
        play_glitch_sound()

    elif action == "r3_window_chaos":
        # Move the window to a random edge, wait, then center it
        def _chaos():
            time.sleep(0.5)
            shake_game_window(cycles=6, amplitude=25)
            time.sleep(0.4)
            if platform.system() == "Windows":
                try:
                    mw = ctypes.windll.user32.GetSystemMetrics(0)
                    mh = ctypes.windll.user32.GetSystemMetrics(1)
                    begin_window_move(random.randint(0, mw - 400), random.randint(0, mh - 300), 0.4)
                    time.sleep(1.2)
                    move_window_center(0.8)
                except:
                    pass
        threading.Thread(target=_chaos, daemon=True).start()
        play_error_sound()

    elif action == "r3_notification":
        show_os_notification("The Question Game", "It is almost over. Come back.")

    elif action == "r3_final_end":
        # Mark run_count to 99 so game won't reopen normally
        game_state["run_count"] = 99
        game_state["last_close_time"] = time.time()
        game_state["_ended"] = True
        save_game_state(game_state)
        threading.Thread(target=play_reverse_chord, daemon=True).start()
        time.sleep(1.5)
        return "EXIT"

    return None

# --- Main Loop ---
while running:
    current_time = time.time()
    current_w, current_h = screen.get_size()

    font_large, font_medium, font_small = get_scaled_fonts(current_w, current_h)

    if game_state["run_count"] >= 3 and state in ["PLAYING", "FULLSCREEN"]:
        shake_x = random.randint(-8, 8)
        shake_y = random.randint(-8, 8)
    else:
        shake_x, shake_y = 0, 0

    screen.fill(BLACK)

    # Window/mouse smooth animation updates (every frame)
    update_window_anim()
    update_mouse_anim()



    # --- Idle / Away Detection ---
    if state in ["PLAYING", "FULLSCREEN"]:
        focused = pygame.key.get_focused() if hasattr(pygame.key, "get_focused") else True
        if idle_tracker["window_focused"] and not focused:
            idle_tracker["window_focused"] = False
            idle_tracker["lost_focus_time"] = current_time
        elif not idle_tracker["window_focused"] and focused:
            idle_tracker["window_focused"] = True
            away_duration = current_time - idle_tracker["lost_focus_time"]
            if away_duration > 4.0:
                idle_tracker["last_away_duration"] = away_duration
                idle_tracker["pending_comment"] = True

    # --- DARKNESS SEQUENCE (blocking visual overlay during 10s silence) ---
    if darkness_active:
        if darkness_phase == "silence":
            elapsed_dark = current_time - darkness_start
            if elapsed_dark < 10.0:
                dot_cycle = [".", "..", "...","...."][int(current_time * 2) % 4]
                dot_surf = font_medium.render(dot_cycle, True, RED)
                screen.blit(dot_surf, (current_w // 2 - dot_surf.get_width() // 2, current_h // 2))
                if random.random() < 0.08:
                    play_type_sound()
                apply_vhs_effects(screen, current_w, current_h)
                pygame.display.flip()
                clock.tick(60)
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                        darkness_active = False
                continue
            else:
                darkness_active = False
                darkness_phase = "none"

    # --- Global Event Loop ---
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            # Special: during the "exit_broken" question, intercept with 3-stage drama
            _on_busy_q = (state in ["PLAYING", "FULLSCREEN"] and
                          current_step < len(active_script) and
                          active_script[current_step].get("_id") == BUSY_QUESTION_ID)
            if _on_busy_q:
                # Always uses the staged system, never permanent block
                if attempt_close_with_warning():
                    running = False
                else:
                    play_error_sound()
            elif attempt_close_with_warning():
                running = False
        elif event.type == pygame.VIDEORESIZE and state != "FULLSCREEN":
            WIDTH, HEIGHT = event.w, event.h
            screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)

        if event.type == pygame.KEYDOWN:
            # Alt+F4 interception (same dramatic-delay-then-allow logic as the X button)
            if event.key == pygame.K_F4 and (pygame.key.get_mods() & pygame.KMOD_ALT):
                if attempt_close_with_warning():
                    running = False
                continue

            if state == "TITLE":
                if event.key == pygame.K_TAB:
                    selected_option = (selected_option + 1) % len(menu_options)
                    play_ui_nav_sound()
                elif event.key == pygame.K_RETURN:
                    play_ui_select_sound()
                    if menu_options[selected_option] == "play":
                        state = "PLAYING"
                        typing_index = 0
                        typing_state = "THINKING"
                        thinking_timer = current_time
                        question_start_time = current_time
                    elif menu_options[selected_option] == "Settings":
                        state = "SETTINGS"
                    elif menu_options[selected_option] == "Help":
                        state = "HELP"
                        help_text = random.choice(help_variations)
                    elif menu_options[selected_option] == "About":
                        state = "ABOUT"
                        about_text = random.choice(about_variations)
                    elif menu_options[selected_option] == "exit":
                        running = False

            elif state == "SETTINGS":
                if event.key == pygame.K_TAB:
                    settings_selected = (settings_selected + 1) % len(settings_options)
                    play_ui_nav_sound()
                elif event.key in [pygame.K_LEFT, pygame.K_RIGHT]:
                    _sopt = settings_options[settings_selected]
                    if _sopt in _settings_values:
                        _vals = _settings_values[_sopt]
                        _delta = 1 if event.key == pygame.K_RIGHT else -1
                        _settings_idx[_sopt] = (_settings_idx[_sopt] + _delta) % len(_vals)
                        apply_settings_from_idx()
                        play_ui_nav_sound()
                elif event.key == pygame.K_RETURN:
                    play_ui_select_sound()
                    _sopt = settings_options[settings_selected]
                    if _sopt == "< Back":
                        state = "TITLE"
                    elif _sopt == "Reset All Data":
                        reset_all_data()
                        # restart script for run 1
                        active_script = build_run1_script()
                        current_step = 0
                        typing_index = 0
                        state = "TITLE"
                    elif _sopt in _settings_values:
                        _vals = _settings_values[_sopt]
                        _settings_idx[_sopt] = (_settings_idx[_sopt] + 1) % len(_vals)
                        apply_settings_from_idx()
                elif event.key == pygame.K_ESCAPE:
                    state = "TITLE"

            elif state in ["ABOUT", "HELP"]:
                if event.key in [pygame.K_RETURN, pygame.K_ESCAPE]:
                    play_ui_select_sound()
                    state = "TITLE"

            elif state in ["PLAYING", "FULLSCREEN"]:
                if current_step < len(active_script):
                    step_data = active_script[current_step]
                    if step_data["type"] == "choice" and typing_state == "READY":
                        if event.key == pygame.K_TAB:
                            selected_answer = (selected_answer + 1) % len(step_data["opts"])
                            play_ui_nav_sound()
                        elif event.key == pygame.K_RETURN:
                            play_ui_select_sound()

                            ans = step_data["opts"][selected_answer]
                            q_id = step_data.get("_id", str(current_step))
                            elapsed = current_time - question_start_time
                            save_answer(q_id, ans, elapsed)

                            if step_data.get("action") == "save_color":
                                game_state["fav_color"] = ans.lower()
                                save_game_state(game_state)

                            injected_followup = None

                            # False memory rebuttal
                            if step_data.get("_false_memory_response"):
                                rebuttal = FALSE_MEMORY_REBUTTALS.get(ans)
                                if rebuttal:
                                    injected_followup = {
                                        "q": rebuttal, "type": "choice", "opts": ["...", "Fine"],
                                        "_id": f"false_memory_rebuttal_{current_step}", "_injected": True
                                    }

                            # Pre-knowledge wrong-answer rebuttal
                            if step_data.get("_preknowledge_wrong_response") and ans == "That's wrong":
                                injected_followup = {
                                    "q": step_data["_preknowledge_wrong_response"], "type": "choice",
                                    "opts": ["...", "Fine, it's correct"],
                                    "_id": f"preknowledge_rebuttal_{current_step}", "_injected": True
                                }

                            # Location denial rebuttal
                            if step_data.get("_location_no_response") and ans == "No":
                                injected_followup = {
                                    "q": step_data["_location_no_response"], "type": "choice",
                                    "opts": ["...", "That's not true"],
                                    "_id": f"location_rebuttal_{current_step}", "_injected": True
                                }

                            # Hesitation check (now 20s threshold)
                            if elapsed > HESITATION_THRESHOLD and not step_data.get("_injected"):
                                injected_followup = {
                                    "q": get_hesitation_comment(), "type": "choice",
                                    "opts": ["...", "I was thinking"], "_injected": True,
                                    "_id": f"hesitation_{current_step}"
                                }

                            if injected_followup:
                                active_script.insert(current_step + 1, injected_followup)

                            # Idle/away comment, queued separately so it doesn't collide
                            elif idle_tracker["pending_comment"]:
                                idle_tracker["pending_comment"] = False
                                idle_q = {
                                    "q": get_idle_comment(), "type": "choice",
                                    "opts": ["...", "I needed a second"], "_injected": True,
                                    "_id": f"idle_{current_step}"
                                }
                                active_script.insert(current_step + 1, idle_q)

                            current_step += 1
                            typing_index, selected_answer, action_triggered = 0, 0, False
                            typing_state = "THINKING"
                            thinking_timer = current_time
                            question_start_time = current_time

    # --- 1. Loading Screen ---
    if state == "LOADING":
        elapsed = current_time - loading_start
        if elapsed > 5.0:
            state = "TITLE"
        else:
            alpha = int(min(1.0, elapsed / 2.0) * 255)
        
            text_surf = font_large.render("The Question Game", True, (alpha, alpha, alpha)) 
            sub_surf_credit = font_small.render("by poseidonsmile", True, (0, alpha, 0))
            sub_surf_prompt = font_small.render("Press [TAB] to cycle through options.", True, (0, alpha, 0)) 
            screen.blit(text_surf, (current_w//2 - text_surf.get_width()//2, current_h//2 - 60))
            screen.blit(sub_surf_credit, (current_w//2 - sub_surf_credit.get_width()//2, current_h//2 - 10))
            screen.blit(sub_surf_prompt, (current_w//2 - sub_surf_prompt.get_width()//2, current_h//2 + 40))
            # "You're not done" message — shown prominently when mid-run data exists
            _answers_so_far = len(game_state.get("answers", {}))
            _not_done = game_state.get("run_count", 1) >= 2 or _answers_so_far >= 5
            if _not_done and elapsed > 1.5:
                _nd_alpha = int(min(1.0, (elapsed - 1.5) / 1.0) * 255)
                _nd_lines = [
                    "The game did not finish.",
                    "It never does.",
                    "Your progress is still here.",
                ]
                for _ndi, _ndl in enumerate(_nd_lines):
                    _nds = font_small.render(_ndl, True, (min(255, _nd_alpha), 0, 0))
                    _nds.set_alpha(_nd_alpha)
                    screen.blit(_nds, (current_w//2 - _nds.get_width()//2, current_h//2 + 80 + _ndi * 22))
            # Subliminal single-frame flash of last close time, barely visible
            if game_state["run_count"] >= 2 and LAST_CLOSE_TIME_ON_LAUNCH and 2.0 < elapsed < 2.05:
                ts = time.strftime("%H:%M:%S", time.localtime(LAST_CLOSE_TIME_ON_LAUNCH))
                flash_surf = font_small.render(ts, True, (25, 25, 25))
                screen.blit(flash_surf, (10, current_h - 20))

    # --- 2. Title Menu ---
    elif state == "TITLE":
        title_color = WHITE
        if game_state["run_count"] >= 3:
            title_color = RED if random.random() < 0.2 else DARK_RED
            if random.random() < 0.05:
                render_wrapped_text(screen, "THIS IS YOUR LAST CHANCE", font_small, RED, 20, 20, 300)

        title_lines = ["The", "Question", "Game"]
        if game_state["run_count"] == 2:
            title_lines = ["....", "...", "Leave."]

        base_y = 100
        for i, line in enumerate(title_lines):
            sway_x = int(math.sin(current_time * 1.8 + i) * 6)
            sway_y = int(math.cos(current_time * 1.2 + i) * 3)
            t_surf = font_large.render(line, True, title_color)
            screen.blit(t_surf, (80 + sway_x, base_y + i * 65 + sway_y))

        menu_y_start = current_h - 310
        for i, opt in enumerate(menu_options):
            color = GREEN if i == selected_option else WHITE
            if game_state["run_count"] >= 3 and i == selected_option:
                color = RED
            prefix = f"> {opt}" if i == selected_option else f"  {opt}"
            o_surf = font_medium.render(prefix, True, color)
            screen.blit(o_surf, (80, menu_y_start + i * 45))

        # Credits
        cred_surf = font_small.render("Neptune Productions [C]", True, (60, 60, 60))
        screen.blit(cred_surf, (current_w // 2 - cred_surf.get_width() // 2, current_h - 28))

        
    # --- 3. About Screen ---
    elif state == "ABOUT":
        render_wrapped_text(screen, "ABOUT THE GAME", font_large, RED, 50, 50, current_w - 100)
        render_wrapped_text(screen, about_text.split('\n', 1)[-1].strip() if '\n' in about_text else about_text,
                           font_small, WHITE, 50, 50 + font_large.get_linesize() + 20, current_w - 100)
        screen.blit(font_medium.render("[ENTER] Return", True, GREEN), (50, current_h - 80))

    # --- 4. Help Screen ---
    elif state == "HELP":
        render_wrapped_text(screen, "NO HELP FOR YOU", font_large, GREEN, 50, 50, current_w - 100)
        render_wrapped_text(screen, help_text.split('\n', 1)[-1].strip() if '\n' in help_text else help_text,
                           font_small, WHITE, 50, 50 + font_large.get_linesize() + 20, current_w - 100)
        screen.blit(font_medium.render("[ENTER] Return", True, GREEN), (50, current_h - 80))

    # --- 4b. Settings Screen ---
    elif state == "SETTINGS":
        render_wrapped_text(screen, "CONTROL PANEL", font_large, GREEN, 50, 50, current_w - 100)
        sy = 50 + font_large.get_linesize() + 30
        for _si, _sopt in enumerate(settings_options):
            _sel = _si == settings_selected
            _col = GREEN if _sel else WHITE
            _pre = "> " if _sel else "  "
            if _sopt in _settings_values:
                _vals = _settings_values[_sopt]
                _vi   = _settings_idx[_sopt]
                _vstr = f"  [ < {_vals[_vi]} > ]"
            elif _sopt == "Reset All Data":
                _vstr = "  [WIPE SAVE]"
            else:
                _vstr = ""
            _line = f"{_pre}{_sopt}{_vstr}"
            _ls = font_medium.render(_line, True, RED if _sopt == "Reset All Data" else _col)
            screen.blit(_ls, (50, sy + _si * 52))
        screen.blit(font_small.render("[TAB] Navigate      [ENTER] Change", True, (80, 80, 80)), (50, current_h - 40))

    # --- 5. Gameplay ---
    elif state in ["PLAYING", "FULLSCREEN"]:
        if current_step >= len(active_script):
            running = False
            break

        step_data = active_script[current_step]
        target_text = step_data.get("q", "")

        # Resolve dynamic location/process/apps questions in place
        if target_text == "DYNAMIC_LOCATION" and not action_triggered:
            city, country = fetch_location()
            game_state['_geo_city'] = city
            resolved = build_location_question(city, country)
            resolved["_id"] = step_data.get("_id", "location")
            active_script[current_step] = resolved
            step_data = resolved
            target_text = step_data["q"]
            action_triggered = True
        elif target_text == "DYNAMIC_APPS" and not action_triggered:
            app_comment = comment_on_open_apps()
            if app_comment:
                step_data = dict(step_data)
                step_data["q"] = app_comment
            else:
                step_data = dict(step_data)
                step_data["q"] = "Your running processes are... quiet.\nToo quiet."
            active_script[current_step] = step_data
            target_text = step_data["q"]
            action_triggered = True
        elif target_text == "DYNAMIC_PROCESSES" and not action_triggered:
            procs = check_processes()
            if procs["roblox"]:
                step_data["q"] = "Roblox is running. I hope you weren't planning to play a game."
            elif procs["discord"]:
                step_data["q"] = "Discord is running. I hope you weren't planning to start a conversation."
            elif procs["telegram"]:
                step_data["q"] = "Telegram is running. I hope you weren't planning to send a message."
            else:
                step_data["q"] = "Your running processes are... quiet.\nToo quiet."
            target_text = step_data["q"]
            action_triggered = True

            # Discord/voice contradiction check against earlier "alone" answer
            alone_ans = game_state["answers"].get("alone")
            contradiction_q = check_discord_voice_contradiction(alone_ans)
            if contradiction_q:
                active_script.insert(current_step + 1, contradiction_q)

        # Task Manager detection — comment if opened, checked passively
        if state in ["PLAYING", "FULLSCREEN"] and random.random() < 0.01:
            procs = check_processes()
            if procs.get("taskmgr") and not game_state.get("task_manager_opened"):
                game_state["task_manager_opened"] = True
                save_game_state(game_state)
                tm_q = {
                    "q": "I see you opened Task Manager.\nThat's the only way out, you know.",
                    "type": "choice", "opts": ["...", "Good to know"],
                    "_id": f"taskmgr_comment_{current_step}", "_injected": True
                }
                active_script.insert(current_step + 1, tm_q)

        # Random Intermittent Background Interference
        if current_time - last_cmd_time > 30:
            flash_cmd()
            last_cmd_time = current_time
        if current_time - last_beep_time > random.randint(15, 45):
            play_error_sound()
            last_beep_time = current_time

        step_action = step_data.get("action", "")
        if step_action and step_action not in ("save_color",) and not action_triggered:
            result = handle_step_action(step_action, step_data)
            action_triggered = True
            if result == "EXIT":
                running = False
                break

        # Typing state machine
        if typing_state == "THINKING":
            if current_time - thinking_timer < 1.5:
                cycle = ["...", "..", ".", ".."][int(current_time * 4) % 4]
                screen.blit(font_medium.render(cycle, True, WHITE), (60 + shake_x, 150 + shake_y))
                if random.random() < 0.2:
                    play_type_sound()
            else:
                typing_state = "BEEP"
                thinking_timer = current_time
        elif typing_state == "BEEP":
            if step_action == "start_webcam" and not webcam_active:
                cycle = ["...", "..", "."][int(current_time * 3) % 3]
                screen.blit(font_small.render(f"Initializing feed {cycle}", True, RED), (60, current_h - 80))
            play_mechanical_beep()
            typing_state = "TYPING"
            last_type_time = current_time
        elif typing_state == "TYPING":
            _tspeed = game_state.get("settings", {}).get("text_speed", 0.04)
            if current_time - last_type_time > _tspeed:
                if typing_index < len(target_text):
                    typing_index += 1
                    play_type_sound()
                    last_type_time = current_time
                else:
                    typing_state = "READY"

        _sway_mult = game_state.get("settings", {}).get("sway_intensity", 1.0)
        sway_x = int(math.sin(current_time * 1.5) * 4 * _sway_mult) + shake_x
        sway_y = int(math.cos(current_time * 1.0) * 2 * _sway_mult) + shake_y

        t_color = RED if ("afraid" in target_text.lower() or game_state["run_count"] >= 3) else WHITE
        if typing_state in ["TYPING", "READY"]:
            render_wrapped_text(screen, target_text[:typing_index], font_medium, t_color,
                               60 + sway_x, 120 + sway_y, current_w - 120)

        # Desktop-scan naming: show captured window title briefly during desktop_check
        if step_data.get("action") == "desktop_check" and captured_window_title and typing_state == "READY":
            label = f"I see you have \"{captured_window_title}\" open."
            render_wrapped_text(screen, label, font_small, DIM_RED, 60, current_h - 140, current_w - 120)

        update_webcam_surface()
        if webcam_surface and webcam_active:
            cam_x = current_w - webcam_surface.get_width() - 20
            cam_y = 20
            screen.blit(webcam_surface, (cam_x, cam_y))
            label = font_small.render("LIVE", True, RED)
            screen.blit(label, (cam_x, cam_y + webcam_surface.get_height() + 2))

        if local_image and step_data.get("action") == "show_pic":
            img_x = current_w - local_image.get_width() - 40
            img_y = 150
            screen.blit(local_image, (img_x + shake_x, img_y + shake_y))



        # Close intercept message overlay during gameplay
        _ci_msg = get_close_intercept_message()
        if _ci_msg:
            _ci_age = current_time - close_intercept["warn_time"]
            if _ci_age < 4.0:
                _ci_alpha = int(255 * min(1.0, (4.0 - _ci_age) / 1.0))
                _ci_surf = font_medium.render(_ci_msg, True, (200, 0, 0))
                _ci_surf.set_alpha(_ci_alpha)
                screen.blit(_ci_surf, (current_w // 2 - _ci_surf.get_width() // 2, 40))

        if typing_state == "READY":
            ans_count = len(step_data["opts"])
            ans_y = current_h - (ans_count * 50) - 60

            if step_data["type"] == "choice":
                for i, opt in enumerate(step_data["opts"]):
                    sel_color = RED if game_state["run_count"] >= 3 else GREEN
                    color = sel_color if i == selected_answer else WHITE
                    prefix = f"[ {opt} ]" if i == selected_answer else f"  {opt}  "
                    opt_surf = font_medium.render(prefix, True, color)
                    screen.blit(opt_surf, (60 + shake_x, ans_y + i * 50 + shake_y))

            elif step_data["type"] == "wait":
                if wait_start_time == 0:
                    wait_start_time = current_time
                    if step_action and not action_triggered:
                        result = handle_step_action(step_action, step_data)
                        action_triggered = True
                        if result == "EXIT":
                            running = False
                if current_time - wait_start_time > step_data.get("time", 3.0):
                    current_step += 1
                    typing_index, action_triggered, wait_start_time = 0, False, 0
                    typing_state = "THINKING"
                    thinking_timer = current_time
                    question_start_time = current_time

        if game_state["run_count"] >= 3 and state in ["PLAYING", "FULLSCREEN"] and random.random() < 0.008:
            pygame.mouse.set_pos(random.randint(200, 600), random.randint(200, 400))

        # Run 2 enhanced atmosphere: shadow static + extra glitch sounds
        if game_state["run_count"] == 2:
            apply_shadow_static(screen, current_w, current_h, intensity=1.5)
            if random.random() < 0.01:
                play_glitch_sound()

        # Run 3 atmosphere: intense corruption, heartbeat, red flickers
        if game_state["run_count"] >= 3:
            # Heavy scanline corruption
            if random.random() < 0.04:
                _gy = random.randint(0, current_h)
                _gw = random.randint(20, current_w)
                _gx = random.randint(0, current_w - _gw)
                pygame.draw.rect(screen, (random.randint(40, 100), 0, 0), (_gx, _gy, _gw, random.randint(1, 6)))
            # Periodic heartbeat sound
            if int(current_time * 0.8) != int((current_time - 0.016) * 0.8):
                if random.random() < 0.12:
                    threading.Thread(target=play_heartbeat, daemon=True).start()
            # Random full-screen red flash (very brief)
            if random.random() < 0.003:
                _flash = pygame.Surface((current_w, current_h), pygame.SRCALPHA)
                _flash.fill((100, 0, 0, 30))
                screen.blit(_flash, (0, 0))
                play_static_scream()
            apply_shadow_static(screen, current_w, current_h, intensity=3.0)
            if random.random() < 0.025:
                play_glitch_sound()

    apply_vhs_effects(screen, current_w, current_h)
    pygame.display.flip()
    clock.tick(60)

pygame.quit()
sys.exit()
