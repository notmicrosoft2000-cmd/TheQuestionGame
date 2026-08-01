"""Cross-platform OS-level utilities: wallpaper, window movement, mouse,
processes, webcam, notifications, sleep, and text-to-speech.

Windows uses native ctypes; macOS uses `osascript`/System Events (may prompt
for Automation permission once; every call degrades to a no-op if denied).
"""
import ctypes
import glob
import os
import platform
import random
import subprocess
import threading
import time
import webbrowser

from . import config
from . import persistence

SYSTEM = platform.system()


# --- Desktop wallpaper -------------------------------------------------------
def get_current_wallpaper_path():
    if SYSTEM == "Windows":
        try:
            buf = ctypes.create_unicode_buffer(512)
            ctypes.windll.user32.SystemParametersInfoW(0x0073, 512, buf, 0)
            return buf.value
        except Exception:
            return ""
    if SYSTEM == "Darwin":
        try:
            script = 'tell application "System Events" to get picture of desktop 1'
            out = subprocess.check_output(["osascript", "-e", script], stderr=subprocess.DEVNULL, text=True).strip()
            if out and out.lower() != "missing value":
                return out
        except Exception:
            pass
    return ""


def set_wallpaper_from_path(path):
    if not path or not os.path.exists(path):
        return
    if SYSTEM == "Windows":
        try:
            ctypes.windll.user32.SystemParametersInfoW(20, 0, path, 3)
        except Exception:
            pass
    elif SYSTEM == "Darwin":
        try:
            p = os.path.abspath(path).replace('"', '\\"')
            script = 'tell application "System Events" to set picture of every desktop to POSIX file "%s"' % p
            subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


def generate_solid_wallpaper(rgb, path):
    """Write a solid-color wallpaper image (BMP on Windows, PNG elsewhere)."""
    try:
        import pygame
        w, h = 1920, 1080
        surf = pygame.Surface((w, h))
        surf.fill(rgb)
        pygame.image.save(surf, path)
        return True
    except Exception:
        return False


def set_desktop_wallpaper(color_name):
    if SYSTEM not in ("Windows", "Darwin"):
        return
    rgb = config.WALLPAPER_COLORS.get(color_name.lower(), (0, 0, 0))
    ext = ".bmp" if SYSTEM == "Windows" else ".png"
    try:
        os.makedirs(config.WALLPAPER_DIR, exist_ok=True)
    except Exception:
        pass
    wp_path = os.path.join(config.WALLPAPER_DIR, "horror_bg" + ext)
    if generate_solid_wallpaper(rgb, wp_path):
        set_wallpaper_from_path(wp_path)


def set_black_wallpaper_and_cache(game_state):
    if SYSTEM not in ("Windows", "Darwin"):
        return
    cached = get_current_wallpaper_path()
    if cached:
        game_state["original_wallpaper"] = cached
        persistence.save_game_state(game_state)
    ext = ".bmp" if SYSTEM == "Windows" else ".png"
    try:
        os.makedirs(config.WALLPAPER_DIR, exist_ok=True)
    except Exception:
        pass
    wp_path = os.path.join(config.WALLPAPER_DIR, "black_wp" + ext)
    if generate_solid_wallpaper((0, 0, 0), wp_path):
        set_wallpaper_from_path(wp_path)


def restore_original_wallpaper(game_state):
    orig = game_state.get("original_wallpaper", "")
    if orig and os.path.exists(orig):
        set_wallpaper_from_path(orig)


# --- Window helpers ----------------------------------------------------------
def get_hwnd():
    try:
        import pygame
        return pygame.display.get_wm_info()["window"]
    except Exception:
        return None


def get_window_rect(hwnd):
    if SYSTEM != "Windows":
        return None
    rect = ctypes.wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect


def _mac_window_position():
    try:
        script = ('tell application "System Events" to get position of front window of '
                  '(first process whose frontmost is true)')
        out = subprocess.check_output(["osascript", "-e", script], stderr=subprocess.DEVNULL, text=True)
        parts = out.strip().split(",")
        if len(parts) == 2:
            return int(parts[0].strip()), int(parts[1].strip())
    except Exception:
        pass
    return None


def _mac_set_window_position(x, y):
    try:
        script = ('tell application "System Events" to set position of front window of '
                  '(first process whose frontmost is true) to {%d, %d}' % (int(x), int(y)))
        subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


window_anim = {"active": False, "start_x": 0, "start_y": 0, "target_x": 0, "target_y": 0, "start_time": 0, "duration": 0.6}


def begin_window_move(target_x, target_y, duration=0.6):
    hwnd = get_hwnd()
    if not hwnd:
        return
    if SYSTEM != "Windows":
        _mac_set_window_position(target_x, target_y)
        return
    rect = get_window_rect(hwnd)
    window_anim.update(active=True, start_x=rect.left, start_y=rect.top,
                       target_x=target_x, target_y=target_y,
                       start_time=time.time(), duration=duration)


def update_window_anim():
    if not window_anim["active"]:
        return
    if SYSTEM != "Windows":
        window_anim["active"] = False
        return
    hwnd = get_hwnd()
    if not hwnd:
        window_anim["active"] = False
        return
    elapsed = time.time() - window_anim["start_time"]
    dur = window_anim["duration"]
    t = min(1.0, elapsed / dur)
    eased = 1 - pow(1 - t, 3)
    x = int(window_anim["start_x"] + (window_anim["target_x"] - window_anim["start_x"]) * eased)
    y = int(window_anim["start_y"] + (window_anim["target_y"] - window_anim["start_y"]) * eased)
    try:
        ctypes.windll.user32.SetWindowPos(hwnd, 0, x, y, 0, 0, 0x0001)
    except Exception:
        pass
    if t >= 1.0:
        window_anim["active"] = False


def move_window_right(duration=0.8):
    try:
        import pygame
        info = pygame.display.Info()
        monitor_w = info.current_w
        win_w = pygame.display.get_surface().get_width()
        begin_window_move(monitor_w - win_w - 10, 100, duration)
    except Exception:
        pass


def move_window_center(duration=0.8):
    try:
        import pygame
        info = pygame.display.Info()
        monitor_w, monitor_h = info.current_w, info.current_h
        surf = pygame.display.get_surface()
        win_w, win_h = surf.get_width(), surf.get_height()
        begin_window_move((monitor_w - win_w) // 2, (monitor_h - win_h) // 2, duration)
    except Exception:
        pass


# --- Mouse movement ----------------------------------------------------------
mouse_anim = {"active": False, "start_x": 0, "start_y": 0, "target_x": 0, "target_y": 0, "start_time": 0, "duration": 0.35}


def begin_mouse_move(target_x, target_y, duration=0.35):
    import pygame
    cur_x, cur_y = pygame.mouse.get_pos()
    mouse_anim.update(active=True, start_x=cur_x, start_y=cur_y,
                      target_x=target_x, target_y=target_y,
                      start_time=time.time(), duration=duration)


def update_mouse_anim():
    import pygame
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
    import pygame
    if mouse_anim["active"]:
        return
    try:
        if SYSTEM == "Windows":
            hwnd = get_hwnd()
            if not hwnd:
                return
            rect = get_window_rect(hwnd)
            pt = ctypes.wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            if pt.x > rect.right - 50 and pt.y < rect.top + 35:
                begin_mouse_move(pt.x - 140, pt.y + 120, 0.4)
        else:
            px, py = pygame.mouse.get_pos()
            surf = pygame.display.get_surface()
            if px > surf.get_width() - 60 and py < 40:
                begin_mouse_move(px - 140, py + 120, 0.4)
    except Exception:
        pass


# --- Intrusion actions -------------------------------------------------------
def minimize_all_windows():
    if SYSTEM in ("Windows", "Darwin"):
        move_window_right()
    threading.Thread(target=speak_text, args=("Look at your desktop. Look at how fragile your sanctuary is.",), daemon=True).start()


def _jiggle_game_window(hwnd, cycles=6, amplitude=18, interval=0.06):
    try:
        rect = get_window_rect(hwnd)
        ox, oy = rect.left, rect.top
        for _ in range(cycles):
            for dx, dy in [(amplitude, 0), (-amplitude, amplitude), (0, -amplitude), (amplitude, amplitude)]:
                ctypes.windll.user32.SetWindowPos(hwnd, 0, ox + dx, oy + dy, 0, 0, 0x0001)
                time.sleep(interval)
        ctypes.windll.user32.SetWindowPos(hwnd, 0, ox, oy, 0, 0, 0x0001)
    except Exception:
        pass


def shake_game_window(cycles=8, amplitude=20):
    if SYSTEM == "Windows":
        hwnd = get_hwnd()
        if hwnd:
            threading.Thread(target=_jiggle_game_window, args=(hwnd, cycles, amplitude), daemon=True).start()
    elif SYSTEM == "Darwin":
        def _jiggle_mac():
            try:
                pos = _mac_window_position()
                if not pos:
                    return
                ox, oy = pos
                for _ in range(cycles):
                    for dx, dy in [(amplitude, 0), (-amplitude, amplitude), (0, -amplitude), (amplitude, amplitude)]:
                        _mac_set_window_position(ox + dx, oy + dy)
                        time.sleep(0.05)
                _mac_set_window_position(ox, oy)
            except Exception:
                pass
        threading.Thread(target=_jiggle_mac, daemon=True).start()


def shake_other_windows():
    if SYSTEM == "Windows":
        def _do():
            our_hwnd = get_hwnd()
            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
            handles = []
            def _collect(hwnd, _):
                if hwnd != our_hwnd and ctypes.windll.user32.IsWindowVisible(hwnd):
                    handles.append(hwnd)
                return True
            ctypes.windll.user32.EnumWindows(EnumWindowsProc(_collect), 0)
            for hwnd in handles[:4]:
                try:
                    rect = ctypes.wintypes.RECT()
                    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    ox, oy = rect.left, rect.top
                    for dx, dy in [(12, 0), (-12, 12), (8, -8), (-8, 8), (0, 0)]:
                        ctypes.windll.user32.SetWindowPos(hwnd, 0, ox + dx, oy + dy, 0, 0, 0x0001)
                        time.sleep(0.04)
                    ctypes.windll.user32.SetWindowPos(hwnd, 0, ox, oy, 0, 0, 0x0001)
                except Exception:
                    pass
        threading.Thread(target=_do, daemon=True).start()
    elif SYSTEM == "Darwin":
        def _do():
            try:
                pos = _mac_window_position()
                if not pos:
                    return
                ox, oy = pos
                for dx, dy in [(12, 0), (-12, 12), (8, -8), (-8, 8), (0, 0)]:
                    _mac_set_window_position(ox + dx, oy + dy)
                    time.sleep(0.04)
                _mac_set_window_position(ox, oy)
            except Exception:
                pass
        threading.Thread(target=_do, daemon=True).start()


def open_random_picture_silently():
    def _do():
        try:
            pic_dir = os.path.join(os.path.expanduser("~"), "Pictures")
            files = glob.glob(os.path.join(pic_dir, "**", "*.[jp][pn]*"), recursive=True)
            if files:
                webbrowser.open(random.choice(files))
                persistence.award_badge("photographer")
        except Exception:
            pass
    threading.Thread(target=_do, daemon=True).start()


def comment_on_open_apps():
    try:
        if SYSTEM == "Windows":
            output = subprocess.getoutput("tasklist /FO CSV /NH").lower()
            app_names = {
                "chrome.exe": "Chrome", "firefox.exe": "Firefox", "msedge.exe": "Edge",
                "spotify.exe": "Spotify", "steam.exe": "Steam", "vlc.exe": "VLC",
                "code.exe": "VS Code", "notepad.exe": "Notepad", "explorer.exe": "Explorer",
                "discord.exe": "Discord", "slack.exe": "Slack", "zoom.exe": "Zoom",
                "obs64.exe": "OBS", "obs32.exe": "OBS",
            }
        elif SYSTEM == "Darwin":
            output = subprocess.getoutput("ps -ax").lower()
            app_names = {
                "chrome": "Chrome", "firefox": "Firefox", "safari": "Safari",
                "spotify": "Spotify", "steam": "Steam", "visual studio code": "VS Code",
                "discord": "Discord", "slack": "Slack", "zoom": "Zoom",
                "obs": "OBS", "messages": "Messages", "music": "Music", "photos": "Photos",
                "terminal": "Terminal",
            }
        else:
            return None
        found = [name for proc, name in app_names.items() if proc in output]
        if found:
            return random.choice([
                "I can see %s is open.\nWas that intentional?" % found[0],
                "You have %s running in the background.\nAre you expecting someone?" % found[0],
                "%s.\nThat is interesting timing." % found[0],
            ])
    except Exception:
        pass
    return None


def show_os_notification(title, body):
    if SYSTEM == "Windows":
        def _do():
            try:
                ps_cmd = (
                    "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
                    "ContentType = WindowsRuntime] | Out-Null; "
                    "$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
                    "[Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
                    "$template.SelectSingleNode('//text[@id=\"1\"]').InnerText = '%s'; "
                    "$template.SelectSingleNode('//text[@id=\"2\"]').InnerText = '%s'; "
                    "$toast = [Windows.UI.Notifications.ToastNotification]::new($template); "
                    "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('%s').Show($toast);"
                    % (title.replace("'", ""), body.replace("'", ""), config.APP_NAME)
                )
                subprocess.Popen(["powershell", "-WindowStyle", "Hidden", "-Command", ps_cmd],
                                 creationflags=subprocess.CREATE_NO_WINDOW)
            except Exception:
                pass
        threading.Thread(target=_do, daemon=True).start()
    elif SYSTEM == "Darwin":
        def _do():
            try:
                script = 'display notification "%s" with title "%s" sound name "default"' % (
                    body.replace('"', '\\"'), title.replace('"', '\\"'))
                subprocess.run(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
        threading.Thread(target=_do, daemon=True).start()


def attempt_close_with_warning():
    """The X button (and Alt+F4 / Cmd+Q) is permanently disabled."""
    from .audio import play_error_sound
    play_error_sound()
    return False


def get_close_intercept_message():
    return "Escaping is not as easy as you think."


def check_processes():
    if SYSTEM == "Windows":
        output = subprocess.getoutput("tasklist").lower()
        return {
            "discord": "discord.exe" in output,
            "telegram": "telegram.exe" in output,
            "roblox": "robloxplayerbeta.exe" in output,
            "taskmgr": "taskmgr.exe" in output,
        }
    if SYSTEM == "Darwin":
        output = subprocess.getoutput("ps -ax").lower()
        return {
            "discord": "discord" in output,
            "telegram": "telegram" in output,
            "roblox": "roblox" in output,
            "taskmgr": "activity monitor" in output,
        }
    return {"discord": False, "telegram": False, "roblox": False, "taskmgr": False}


def get_foreground_window_title():
    if SYSTEM == "Windows":
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value.strip()
        except Exception:
            return ""
    if SYSTEM == "Darwin":
        try:
            import re
            out = subprocess.getoutput("lsappinfo front")
            m = re.search(r'"([^"]+)"', out)
            return m.group(1) if m else out.strip()
        except Exception:
            return ""
    return ""


# --- Location & pictures (cached background prefetch) ------------------------
_location_cache = {"value": None}
_picture_cache = {"values": []}
_process_cache = {"values": []}


def fetch_location():
    try:
        import requests
        r = requests.get("https://ipinfo.io/json", timeout=4)
        data = r.json()
        city = data.get("city", "")
        country = data.get("country", "")
        return (city or ""), (country or "")
    except Exception:
        return "", ""


def get_random_picture():
    try:
        pic_dir = os.path.join(os.path.expanduser("~"), "Pictures")
        files = glob.glob(os.path.join(pic_dir, "**", "*.[jp][pn]*"), recursive=True)
        if files:
            return random.choice(files)
    except Exception:
        pass
    return None


def _prefetch_location():
    try:
        _location_cache["value"] = fetch_location()
    except Exception:
        pass


def _prefetch_pictures():
    try:
        _picture_cache["values"] = [
            p for p in (
                get_random_picture() for _ in range(4)
            ) if p
        ]
    except Exception:
        pass


def _refresh_processes_loop():
    while True:
        try:
            _process_cache["values"] = check_processes()
        except Exception:
            pass
        time.sleep(4)


def get_cached_location():
    return _location_cache.get("value") or ("", "")


def get_cached_random_picture():
    vals = _picture_cache.get("values") or []
    return random.choice(vals) if vals else None


def get_cached_processes():
    return _process_cache.get("values") or {"discord": False, "telegram": False, "roblox": False, "taskmgr": False}


def start_background_prefetch():
    threading.Thread(target=_prefetch_location, daemon=True).start()
    threading.Thread(target=_prefetch_pictures, daemon=True).start()
    threading.Thread(target=_refresh_processes_loop, daemon=True).start()


def put_computer_to_sleep():
    try:
        if SYSTEM == "Windows":
            ctypes.windll.powrprof.SetSuspendState(False, True, False)
        elif SYSTEM == "Darwin":
            subprocess.Popen(["pmset", "sleepnow"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


# --- Text-to-speech ----------------------------------------------------------
try:
    import pyttsx3
    _HAS_PYTTX3 = True
except Exception:
    _HAS_PYTTX3 = False


def speak_text(text):
    try:
        if SYSTEM == "Darwin":
            subprocess.Popen(["say", "-r", "110", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        if not _HAS_PYTTX3:
            return
        engine = pyttsx3.init()
        engine.setProperty("rate", 115)
        engine.say(text)
        engine.runAndWait()
    except Exception:
        pass


def _voice_exists(name):
    try:
        out = subprocess.getoutput("say -v ?")
        return name.lower() in out.lower()
    except Exception:
        return False


def whisper_text(text):
    """Speak the given text back slowly and quietly — the "it answers you" scare."""
    try:
        if SYSTEM == "Darwin":
            subprocess.Popen(["say", "-r", "95", "-v", "Whisper" if _voice_exists("Whisper") else "Alex", text],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        if not _HAS_PYTTX3:
            return
        engine = pyttsx3.init()
        engine.setProperty("rate", 80)
        engine.setProperty("volume", 0.55)
        engine.say(text)
        engine.runAndWait()
    except Exception:
        pass


def flash_cmd():
    """Brief terminal flash — the closest analog of a cmd.exe popup."""
    if SYSTEM == "Windows":
        subprocess.Popen("cmd.exe /c exit", shell=True, creationflags=0)
    elif SYSTEM == "Darwin":
        try:
            script = 'tell application "Terminal" to do script "sleep 0.25; exit"'
            subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
