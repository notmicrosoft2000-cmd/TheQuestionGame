"""Cross-platform OS-level utilities: wallpaper, window movement, mouse,
processes, webcam, notifications, sleep, and text-to-speech.

Windows uses native ctypes; macOS uses `osascript`/System Events (may prompt
for Automation permission once; every call degrades to a no-op if denied).
"""
import ctypes
import glob
import math
import os
import platform
import random
import subprocess
import threading
import time
import webbrowser

try:  # ctypes.wintypes is a submodule and is not always pulled in by ctypes
    import ctypes.wintypes  # noqa: F401
except Exception:  # pragma: no cover - non-Windows / restricted builds
    pass

from . import config
from . import persistence

SYSTEM = platform.system()

# The player can switch screen shake off (ACCESSIBILITY -> Disable Screen
# Shake). The desktop window-jiggle is part of that shake, so the flag lives
# here and the scare system reads it through `set_shake_enabled`.
_shake_enabled = True


def set_shake_enabled(enabled):
    """Allow or forbid shaking the game window on the desktop."""
    global _shake_enabled
    _shake_enabled = bool(enabled)


# --- Global cursor + window bounds ------------------------------------------
# The eye needs to know where the cursor is on the *desktop*, not just inside
# the game window, so it can keep watching you when you move the mouse away.
# Windows gets exact values from user32; macOS tries Quartz first and falls
# back to System Events; Linux has no portable API here so the caller falls
# back to pygame's own mouse position.
_cursor_cache = {"pos": None, "at": 0.0}
_cursor_cache_lock = threading.Lock()


def get_global_cursor():
    """(x, y) of the cursor in desktop coordinates, or None if unavailable."""
    now = time.time()
    with _cursor_cache_lock:
        cached = _cursor_cache["pos"]
        at = _cursor_cache["at"]
    if cached is not None and now - at < 0.033:
        return cached
    pos = _query_global_cursor()
    if pos is None:
        return cached
    with _cursor_cache_lock:
        _cursor_cache["pos"] = pos
        _cursor_cache["at"] = now
    return pos


def _query_global_cursor():
    if SYSTEM == "Windows":
        try:
            pt = ctypes.wintypes.POINT()
            if _user32().GetCursorPos(ctypes.byref(pt)):
                return (int(pt.x), int(pt.y))
        except Exception:
            pass
        return None
    if SYSTEM == "Darwin":
        # Quartz is cheap. The AppleScript fallback is *not*: it is a process
        # spawn, and the eye asks for the cursor every frame, so it is not
        # used here. Without Quartz the eye simply follows the pointer
        # inside the window.
        try:
            import Quartz  # pyobjc, if it happens to be installed
            e = Quartz.CGEventCreate(None)
            p = Quartz.CGEventGetLocation(e)
            return (int(p.x), int(p.y))
        except Exception:
            pass
        return None
    if SYSTEM == "Linux":
        # The X11 pointer is only useful when the game window is an X11
        # window too: under the Wayland driver the window has no X11
        # position, so desktop coordinates could not be mapped onto it and
        # the eye would look in the wrong direction. The in-window cursor
        # is used instead.
        if _pygame_driver() != "x11":
            return None
        return _query_global_cursor_x11()
    return None


# --- X11 global cursor ------------------------------------------------------
# On Linux the pointer belongs to the X server, and XWayland exposes the real
# pointer even on a Wayland session, so this works for both. There is no
# comparable API on pure Wayland, and there never will be one: compositors
# deliberately keep the pointer position private.
_x11 = {"lib": None, "display": None, "tried": False}


def _x11_lib():
    if _x11["tried"]:
        return _x11["lib"]
    _x11["tried"] = True
    try:
        lib = ctypes.cdll.LoadLibrary("libX11.so.6")
    except Exception:
        try:
            lib = ctypes.cdll.LoadLibrary("libX11.so")
        except Exception:
            _x11["lib"] = None
            return None
    try:
        lib.XOpenDisplay.restype = ctypes.c_void_p
        lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        lib.XDefaultRootWindow.restype = ctypes.c_ulong
        lib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        lib.XInitThreads.restype = ctypes.c_int
        lib.XQueryPointer.restype = ctypes.c_int
        lib.XQueryPointer.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_uint)]
        lib.XTranslateCoordinates.restype = ctypes.c_int
        lib.XTranslateCoordinates.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
            ctypes.c_int, ctypes.c_int,
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_ulong)]
        try:
            lib.XInitThreads()
        except Exception:
            pass
    except Exception:
        _x11["lib"] = None
        return None
    _x11["lib"] = lib
    return lib


def _x11_display():
    lib = _x11_lib()
    if lib is None:
        return None, None
    disp = _x11["display"]
    if disp:
        return lib, disp
    try:
        disp = lib.XOpenDisplay(None)
    except Exception:
        disp = None
    if not disp:
        return lib, None
    _x11["display"] = disp
    return lib, disp


def _query_global_cursor_x11():
    """The pointer position in desktop coordinates, via X11."""
    lib, disp = _x11_display()
    if lib is None or not disp:
        return None
    try:
        root = lib.XDefaultRootWindow(ctypes.c_void_p(disp))
        root_ret = ctypes.c_ulong(0)
        child_ret = ctypes.c_ulong(0)
        rx = ctypes.c_int(0)
        ry = ctypes.c_int(0)
        wx = ctypes.c_int(0)
        wy = ctypes.c_int(0)
        mask = ctypes.c_uint(0)
        ok = lib.XQueryPointer(
            ctypes.c_void_p(disp), ctypes.c_ulong(root),
            ctypes.byref(root_ret), ctypes.byref(child_ret),
            ctypes.byref(rx), ctypes.byref(ry),
            ctypes.byref(wx), ctypes.byref(wy), ctypes.byref(mask))
        if ok:
            return (int(rx.value), int(ry.value))
    except Exception:
        pass
    return None


def _x11_window_origin(xid):
    """Top-left of an X window in desktop coordinates."""
    lib, disp = _x11_display()
    if lib is None or not disp or not xid:
        return None
    try:
        root = lib.XDefaultRootWindow(ctypes.c_void_p(disp))
        dst_x = ctypes.c_int(0)
        dst_y = ctypes.c_int(0)
        child = ctypes.c_ulong(0)
        ok = lib.XTranslateCoordinates(
            ctypes.c_void_p(disp), ctypes.c_ulong(xid), ctypes.c_ulong(root),
            0, 0, ctypes.byref(dst_x), ctypes.byref(dst_y), ctypes.byref(child))
        if ok:
            return (int(dst_x.value), int(dst_y.value))
    except Exception:
        pass
    return None


# --- The pygame window, without asking pygame the wrong way ------------------
# `pygame.display.get_wm_info()` is a minefield on Wayland. pygame 2.6 builds
# a capsule from the window's shell surface, which is NULL for a plain
# window, and then puts that NULL into the result dictionary — and
# PyDict_SetItemString does not check for a NULL value, so the interpreter
# dies with SIGSEGV. There is no way to catch that from Python.
#
# So it is only ever called when the SDL driver really is X11, where the one
# thing we want from it is the window id. The answer is cached because the
# window id does not change while the window lives.
_wm_info = {"driver": None, "xid": None, "fetched": False}


def _pygame_driver():
    """The SDL video driver pygame is using: 'x11', 'wayland', 'windows'..."""
    try:
        import pygame
        return str(pygame.display.get_driver() or "").lower()
    except Exception:
        return ""


def _x11_window_id():
    """The X11 id of the pygame window, or None.

    Only X11 has one. Under the Wayland driver the window is a native
    Wayland surface, and asking pygame for the WM info there is not merely
    useless but fatal (see the note above).
    """
    global _wm_info
    if _wm_info["fetched"]:
        return _wm_info["xid"]
    _wm_info["fetched"] = True
    _wm_info["driver"] = _pygame_driver()
    if _wm_info["driver"] != "x11":
        return None
    try:
        import pygame
        info = pygame.display.get_wm_info() or {}
        xid = info.get("window")
        if xid:
            _wm_info["xid"] = int(xid)
    except Exception:
        pass
    return _wm_info["xid"]


def reset_window_cache():
    """Forget the cached window id and bounds — the window was re-made."""
    global _wm_info, _bounds_cache
    _wm_info = {"driver": None, "xid": None, "fetched": False}
    _bounds_cache = {"value": None, "at": 0.0}


def _pygame_window_xid():
    """The X11 window id of the pygame window, if there is one."""
    return _x11_window_id()


_bounds_cache = {"value": None, "at": 0.0}
_BOUNDS_TTL = 0.15        # seconds; the eye does not need 60 Hz window moves


def get_window_bounds(hwnd=None):
    """(left, top, width, height) of the game window in desktop coordinates.

    Cached for a fraction of a second: the eye asks for this every frame, and
    on macOS the answer costs a process spawn (AppleScript), which is far too
    expensive to do sixty times a second.
    """
    now = time.time()
    if _bounds_cache["value"] is not None and now - _bounds_cache["at"] < _BOUNDS_TTL:
        return _bounds_cache["value"]
    value = _query_window_bounds(hwnd)
    if value is not None:
        _bounds_cache["value"] = value
        _bounds_cache["at"] = now
    return value


def _query_window_bounds(hwnd=None):
    if SYSTEM == "Windows":
        try:
            if hwnd is None:
                hwnd = get_hwnd()
            if not hwnd:
                return None
            rect = ctypes.wintypes.RECT()
            if _user32().GetWindowRect(hwnd, ctypes.byref(rect)):
                return (int(rect.left), int(rect.top),
                        int(rect.right - rect.left), int(rect.bottom - rect.top))
        except Exception:
            pass
        return None
    if SYSTEM == "Darwin":
        try:
            pos = _mac_window_position()
            if pos is None:
                return None
            script = ('tell application "System Events" to get size of front window of '
                      '(first process whose frontmost is true)')
            out = subprocess.check_output(["osascript", "-e", script],
                                          stderr=subprocess.DEVNULL, text=True,
                                          timeout=0.4)
            parts = out.strip().split(",")
            if len(parts) == 2:
                return (int(pos[0]), int(pos[1]),
                        int(float(parts[0].strip())), int(float(parts[1].strip())))
        except Exception:
            pass
        return None
    if SYSTEM == "Linux":
        # Only the origin is available from X11; the size comes from the
        # caller (the pygame frame), which is what we want anyway.
        if _pygame_driver() != "x11":
            return None
        origin = _x11_window_origin(_x11_window_id())
        if origin is None:
            return None
        return (int(origin[0]), int(origin[1]), 0, 0)
    return None


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
        # `get_wm_info()` is fatal on Wayland (see the note by _x11_window_id),
        # so it is only asked on Windows and under X11.
        if SYSTEM != "Windows" and _pygame_driver() != "x11":
            return None
        return pygame.display.get_wm_info()["window"]
    except Exception:
        return None


def get_window_rect(hwnd):
    if SYSTEM != "Windows":
        return None
    rect = ctypes.wintypes.RECT()
    _user32().GetWindowRect(hwnd, ctypes.byref(rect))
    return rect


# --- Windows bite helpers (Classic was Windows-first) ------------------------
_HWND_TOPMOST = -1
_SWP_NOSIZE_NOMOVE = 0x0003
_SWP_SHOWWINDOW = 0x0040

_win_user32 = None


def _user32():
    """Return `user32` with 64-bit-safe argtypes set once.

    Without argtypes, ctypes marshals every argument as a 32-bit `c_int`,
    which silently truncates HWNDs on 64-bit Windows (so window handles stop
    matching and scares do nothing). Every call here goes through this helper.
    """
    global _win_user32
    if _win_user32 is not None:
        return _win_user32
    u = ctypes.windll.user32
    try:
        u.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        u.SetWindowPos.restype = ctypes.c_bool
        u.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        u.SetForegroundWindow.restype = ctypes.c_bool
        u.FlashWindow.argtypes = [ctypes.c_void_p, ctypes.c_bool]
        u.FlashWindow.restype = ctypes.c_bool
        u.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        u.ShowWindow.restype = ctypes.c_bool
        u.IsWindowVisible.argtypes = [ctypes.c_void_p]
        u.IsWindowVisible.restype = ctypes.c_bool
        u.GetSystemMenu.argtypes = [ctypes.c_void_p, ctypes.c_bool]
        u.GetSystemMenu.restype = ctypes.c_void_p
        u.DeleteMenu.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
        u.DeleteMenu.restype = ctypes.c_bool
        u.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.wintypes.RECT)]
        u.GetWindowRect.restype = ctypes.c_bool
        u.GetForegroundWindow.argtypes = []
        u.GetForegroundWindow.restype = ctypes.c_void_p
        u.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
        u.GetWindowTextLengthW.restype = ctypes.c_int
        u.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
        u.GetWindowTextW.restype = ctypes.c_int
    except Exception:
        pass
    _win_user32 = u
    return u


def _enum_visible_windows(our_hwnd):
    """HWNDs of visible top-level windows other than ours (64-bit safe)."""
    try:
        u = _user32()
        proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        u.EnumWindows.argtypes = [proc_type, ctypes.c_void_p]
        u.EnumWindows.restype = ctypes.c_bool
        handles = []

        def _collect(hwnd, _):
            try:
                if hwnd and hwnd != our_hwnd and u.IsWindowVisible(hwnd):
                    handles.append(hwnd)
            except Exception:
                pass
            return True

        u.EnumWindows(proc_type(_collect), 0)
        return handles
    except Exception:
        return []


def set_window_topmost():
    """Re-assert HWND_TOPMOST so the game cannot be buried by other windows."""
    if SYSTEM != "Windows" or not config.KEEP_WINDOW_ON_TOP:
        return
    try:
        hwnd = get_hwnd()
        if hwnd:
            _user32().SetWindowPos(
                hwnd, ctypes.c_void_p(_HWND_TOPMOST), 0, 0, 0, 0,
                _SWP_NOSIZE_NOMOVE | _SWP_SHOWWINDOW)
    except Exception:
        pass


def force_foreground():
    if SYSTEM != "Windows":
        return
    try:
        hwnd = get_hwnd()
        if hwnd:
            _user32().SetForegroundWindow(hwnd)
    except Exception:
        pass


def flash_window():
    """Flash the taskbar entry to demand attention (Windows only)."""
    if SYSTEM != "Windows":
        return
    try:
        hwnd = get_hwnd()
        if hwnd:
            _user32().FlashWindow(hwnd, True)
    except Exception:
        pass


def disable_system_close():
    """Remove the close item from the window's system menu.

    NOFRAME already removes the caption, but this also kills the SC_CLOSE entry
    reachable from the taskbar right-click / Alt+Space menu.
    """
    if SYSTEM != "Windows":
        return
    try:
        hwnd = get_hwnd()
        if hwnd:
            u = _user32()
            menu = u.GetSystemMenu(hwnd, False)
            if menu:
                u.DeleteMenu(menu, 0xF060, 0x0000)  # SC_CLOSE
    except Exception:
        pass


def start_topmost_keeper(interval=2.0):
    """Background thread that keeps the window pinned above everything else."""
    if SYSTEM != "Windows" or not config.KEEP_WINDOW_ON_TOP:
        return

    def _loop():
        while True:
            set_window_topmost()
            time.sleep(interval)

    threading.Thread(target=_loop, daemon=True).start()


def _mac_window_position():
    try:
        script = ('tell application "System Events" to get position of front window of '
                  '(first process whose frontmost is true)')
        out = subprocess.check_output(["osascript", "-e", script],
                                      stderr=subprocess.DEVNULL, text=True,
                                      timeout=0.4)
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
    if SYSTEM == "Darwin":
        _float["base_x"], _float["base_y"] = int(target_x), int(target_y)
        pause_window_float(duration + 0.4)
        _mac_set_window_position(target_x, target_y)
        return
    if SYSTEM != "Windows":
        return
    hwnd = get_hwnd()
    if not hwnd:
        return
    # A scripted motion owns the window while it runs; the float resumes after.
    _float["base_x"], _float["base_y"] = int(target_x), int(target_y)
    pause_window_float(duration + 0.4)
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
        _user32().SetWindowPos(hwnd, ctypes.c_void_p(0), x, y, 0, 0, 0x0001)
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


def teleport_window_random():
    """Instant jump to a random spot on the monitor — no animation, no warning."""
    if not window_motion_supported():
        return
    try:
        import pygame
        info = pygame.display.Info()
        surf = pygame.display.get_surface()
        win_w, win_h = surf.get_width(), surf.get_height()
        x = random.randint(0, max(0, info.current_w - win_w))
        y = random.randint(0, max(0, info.current_h - win_h))
        _float["base_x"], _float["base_y"] = x, y
        _float["start"] = time.time()
        pause_window_float(0.4)
        _move_window_abs(x, y)
    except Exception:
        pass


def drift_window(duration=8.0):
    """Slow creep across the screen over `duration` seconds — you notice it
    only once it has already moved."""
    try:
        import pygame
        info = pygame.display.Info()
        surf = pygame.display.get_surface()
        win_w, win_h = surf.get_width(), surf.get_height()
        x = random.randint(0, max(0, info.current_w - win_w))
        y = random.randint(0, max(0, info.current_h - win_h))
        begin_window_move(x, y, duration)
    except Exception:
        pass


# --- Continuous window float + centre jitter (Windows + macOS only) ----------
# Wayland (Linux) forbids applications from positioning their own windows, so
# every function here is an intentional no-op there.
_float = {
    "active": False,
    "base_x": None,
    "base_y": None,
    "amp": 0.0,
    "period": 1.0,
    "pause_until": 0.0,
    "start": 0.0,
    "thread": None,
    "hover_x": 0.0,
    "hover_y": 0.0,
}


def window_motion_supported():
    return SYSTEM in ("Windows", "Darwin")


def _move_window_abs(x, y):
    """Instant absolute reposition (no animation)."""
    x, y = int(x), int(y)
    if SYSTEM == "Windows":
        hwnd = get_hwnd()
        if hwnd:
            try:
                _user32().SetWindowPos(hwnd, ctypes.c_void_p(0), x, y, 0, 0, 0x0001)
            except Exception:
                pass
    elif SYSTEM == "Darwin":
        _mac_set_window_position(x, y)


def _window_screen_and_size():
    import pygame
    try:
        info = pygame.display.Info()
        surf = pygame.display.get_surface()
        if surf is None:
            return None
        return info.current_w, info.current_h, surf.get_width(), surf.get_height()
    except Exception:
        return None


def pause_window_float(seconds=1.5):
    """Let one-shot motions (shake/teleport/slide) own the window briefly."""
    _float["pause_until"] = max(_float["pause_until"], time.time() + seconds)


def set_float_base_from_window():
    """Anchor the float to wherever the window currently is (minus any hover
    lean already applied, so re-anchoring never jumps)."""
    hx, hy = int(_float["hover_x"]), int(_float["hover_y"])
    if SYSTEM == "Windows":
        hwnd = get_hwnd()
        if not hwnd:
            return False
        rect = get_window_rect(hwnd)
        _float["base_x"], _float["base_y"] = rect.left - hx, rect.top - hy
        return True
    if SYSTEM == "Darwin":
        pos = _mac_window_position()
        if not pos:
            return False
        _float["base_x"], _float["base_y"] = pos[0] - hx, pos[1] - hy
        return True
    return False


def move_window_near_center():
    """Jump to a fresh random spot near the centre — called as each question
    lands, so the window is never quite where you left it."""
    if not config.WINDOW_JITTER_NEAR_CENTER or not window_motion_supported():
        return
    geo = _window_screen_and_size()
    if not geo:
        return
    sw, sh, ww, wh = geo
    rng = max(0, int(config.WINDOW_JITTER_RANGE))
    cx = (sw - ww) // 2 + random.randint(-rng, rng)
    cy = (sh - wh) // 2 + random.randint(-rng, rng)
    cx = max(0, min(max(0, sw - ww), cx))
    cy = max(0, min(max(0, sh - wh), cy))
    _float["base_x"], _float["base_y"] = cx, cy
    _float["start"] = time.time()
    pause_window_float(0.25)
    _move_window_abs(cx, cy)


def start_window_float():
    """Begin the endless gentle up/down bob (Windows/macOS only). Also hosts
    the hover parallax, which is driven by `set_hover_offset`."""
    if not (config.WINDOW_FLOAT or getattr(config, "WINDOW_HOVER_AMPLITUDE", 0)):
        return
    if not window_motion_supported():
        return
    if _float["active"]:
        return
    if not set_float_base_from_window():
        return
    _float.update(active=True, amp=float(config.WINDOW_FLOAT_AMPLITUDE),
                  period=max(0.6, float(config.WINDOW_FLOAT_PERIOD)), start=time.time())

    def _loop():
        while _float["active"]:
            if time.time() < _float["pause_until"] or _float["base_x"] is None:
                time.sleep(0.05)
                continue
            dx = dy = 0.0
            if config.WINDOW_FLOAT:
                t = time.time() - _float["start"]
                dy = math.sin((t / _float["period"]) * 2 * math.pi) * _float["amp"]
                dx = math.sin((t / (_float["period"] * 1.7)) * 2 * math.pi) * (_float["amp"] * 0.35)
            _move_window_abs(_float["base_x"] + dx + _float["hover_x"],
                             _float["base_y"] + dy + _float["hover_y"])
            time.sleep(0.05)

    _float["thread"] = threading.Thread(target=_loop, daemon=True)
    _float["thread"].start()


def set_hover_offset(mx, my, w, h):
    """Subtle hover parallax: the window leans a few px toward the cursor.
    Windows/macOS only — no-op on Wayland, which forbids self-positioning."""
    if not window_motion_supported():
        return
    amp = float(getattr(config, "WINDOW_HOVER_AMPLITUDE", 0))
    if amp <= 0:
        return
    try:
        _float["hover_x"] = int((mx / max(1.0, float(w)) - 0.5) * 2.0 * amp)
        _float["hover_y"] = int((my / max(1.0, float(h)) - 0.5) * 2.0 * amp)
    except Exception:
        pass


def nudge_window(radius=None):
    """A small random shuffle of the window — fired when you answer a question."""
    if radius is None:
        radius = float(getattr(config, "WINDOW_ANSWER_NUDGE", 12))
    if radius <= 0 or not window_motion_supported():
        return
    if _float["base_x"] is None:
        set_float_base_from_window()
    if _float["base_x"] is None:
        return
    _float["base_x"] = int(_float["base_x"]) + random.randint(-int(radius), int(radius))
    _float["base_y"] = int(_float["base_y"]) + random.randint(-int(radius), int(radius))
    pause_window_float(0.12)
    _move_window_abs(_float["base_x"], _float["base_y"])


# --- Mouse movement ----------------------------------------------------------
mouse_anim = {"active": False, "start_x": 0, "start_y": 0, "target_x": 0, "target_y": 0, "start_time": 0, "duration": 0.35}


def begin_mouse_move(target_x, target_y, duration=0.35):
    import pygame
    if config.IS_ANDROID:
        return   # no cursor to steal on a touch device (SDL warp is a no-op)
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
    if config.IS_ANDROID:
        return   # no cursor, no title bar to bait the finger toward
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
        u = _user32()
        rect = get_window_rect(hwnd)
        ox, oy = rect.left, rect.top
        for _ in range(cycles):
            for dx, dy in [(amplitude, 0), (-amplitude, amplitude), (0, -amplitude), (amplitude, amplitude)]:
                u.SetWindowPos(hwnd, ctypes.c_void_p(0), ox + dx, oy + dy, 0, 0, 0x0001)
                time.sleep(interval)
        u.SetWindowPos(hwnd, ctypes.c_void_p(0), ox, oy, 0, 0, 0x0001)
    except Exception:
        pass


def shake_game_window(cycles=8, amplitude=20):
    if not _shake_enabled:
        return
    pause_window_float(cycles * 0.3 + 0.6)
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
            handles = _enum_visible_windows(our_hwnd)
            for hwnd in handles[:4]:
                try:
                    rect = ctypes.wintypes.RECT()
                    _user32().GetWindowRect(hwnd, ctypes.byref(rect))
                    ox, oy = rect.left, rect.top
                    for dx, dy in [(12, 0), (-12, 12), (8, -8), (-8, 8), (0, 0)]:
                        _user32().SetWindowPos(hwnd, ctypes.c_void_p(0), ox + dx, oy + dy, 0, 0, 0x0001)
                        time.sleep(0.04)
                    _user32().SetWindowPos(hwnd, ctypes.c_void_p(0), ox, oy, 0, 0, 0x0001)
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


def minimize_other_windows():
    """Windows: minimize every other visible window so the player is left
    staring at the game (and their own desktop). No-op elsewhere."""
    if SYSTEM == "Windows":
        def _do():
            try:
                our_hwnd = get_hwnd()
                handles = _enum_visible_windows(our_hwnd)
                for hwnd in handles[:6]:
                    try:
                        _user32().ShowWindow(hwnd, 6)  # SW_MINIMIZE
                    except Exception:
                        pass
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
    elif config.IS_ANDROID:
        # A real Android toast — no permission needed, and the "your wallpaper
        # is ours" line lands far better as a system-level message than as
        # in-app text the player knows we drew.
        try:
            from android.runnable import run_on_ui_thread
            from jnius import autoclass

            @run_on_ui_thread
            def _toast(title_, body_):
                try:
                    activity = autoclass("org.kivy.android.PythonActivity").mActivity
                    toast = autoclass("android.widget.Toast")
                    toast.makeText(activity, title_ + " — " + body_, toast.LENGTH_LONG).show()
                except Exception:
                    pass

            _toast(title, body)
        except Exception:
            pass


def attempt_close_with_warning():
    """The X button (and Alt+F4 / Cmd+Q) is permanently disabled."""
    from .audio import play_error_sound
    play_error_sound()
    return False


_CLOSE_MESSAGES = [
    "Do not touch that.",
    "You do not get to leave.",
    "There is no close button. There never was.",
    "You have tried %d times. We are counting.",
    "You are only making it worse.",
    "Leave it open. It prefers the company.",
]

# Windows-targeted taunts used once the player keeps hammering the close key.
_WINDOWS_CLOSE_MESSAGES = [
    "Right-click the taskbar all you like.\nThere is nothing to close.",
    "The system menu is empty now.\nWe removed what was left.",
    "You cannot end a process that is already inside you.",
    "Task Manager. That is the only door.\nWe will be waiting on the other side.",
    "Your little X never existed.",
]


def get_close_intercept_message(attempt=0):
    if attempt >= 6 and SYSTEM == "Windows" and random.random() < 0.5:
        return random.choice(_WINDOWS_CLOSE_MESSAGES)
    if attempt >= 3:
        try:
            return _CLOSE_MESSAGES[3] % attempt
        except Exception:
            pass
    return random.choice(_CLOSE_MESSAGES[:3])


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
            u = _user32()
            hwnd = u.GetForegroundWindow()
            if not hwnd:
                return ""
            length = u.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            u.GetWindowTextW(hwnd, buf, length + 1)
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
_geo_cache = {"value": None}
_location_cache = {"value": None}
_picture_cache = {"values": []}
_process_cache = {"values": []}


def _norm_geo(city="", region="", country="", cc="", lat=None, lon=None, tz=""):
    cc = (cc or "").upper().strip()
    country = (country or "").strip()
    if not country and cc:
        country = cc  # keep *something* to show if the provider omits the name
    return {
        "city": (city or "").strip(),
        "region": (region or "").strip(),
        "country": country,
        "country_code": cc,
        "lat": lat,
        "lon": lon,
        "timezone": tz or "",
    }


def _geo_from_ipwho(d):
    if not d.get("success", True):
        return None
    tz = d.get("timezone")
    tz_id = tz.get("id", "") if isinstance(tz, dict) else (tz or "")
    utc = tz.get("utc", "") if isinstance(tz, dict) else ""
    geo = _norm_geo(d.get("city"), d.get("region"), d.get("country"),
                    d.get("country_code"), d.get("latitude"), d.get("longitude"),
                    tz_id)
    geo["utc_offset"] = utc
    return geo


def _geo_from_ipapi(d):
    if d.get("status") != "success":
        return None
    geo = _norm_geo(d.get("city"), d.get("regionName"), d.get("country"),
                    d.get("countryCode"), d.get("lat"), d.get("lon"), d.get("timezone", ""))
    geo["utc_offset"] = d.get("offset")  # seconds east of UTC
    return geo


def _geo_from_ipinfo(d):
    loc = (d.get("loc") or "").split(",")
    lat = loc[0] if len(loc) == 2 else None
    lon = loc[1] if len(loc) == 2 else None
    geo = _norm_geo(d.get("city"), d.get("region"), d.get("country"),
                    d.get("country"), lat, lon, d.get("timezone", ""))
    geo["utc_offset"] = None
    return geo


# Ordered best-effort sources; the first that answers with data wins. Every
# entry is HTTPS unless config.GEO_ALLOW_INSECURE is turned on — a plaintext
# geo lookup can be rewritten by anything on the path between the player and
# the provider, which is exactly the kind of "lie" this guard exists to stop.
_GEO_SOURCES = (
    ("https://ipwho.is/", _geo_from_ipwho, False),
    ("http://ip-api.com/json/", _geo_from_ipapi, True),
    ("https://ipinfo.io/json", _geo_from_ipinfo, False),
)


def _local_utc_offset_hours():
    """The machine's real UTC offset in hours, straight from the OS clock.

    A VPN rewrites the IP address, but it does not move the player's clock: the
    system timezone still says where they actually are. That mismatch is the
    tell we use. Returns None when the offset cannot be determined.
    """
    try:
        if time.daylight and time.localtime().tm_isdst > 0:
            return -time.altzone / 3600.0
        return -time.timezone / 3600.0
    except Exception:
        return None


def _ip_utc_offset_hours(geo):
    """Normalise a provider's UTC-offset field into float hours (or None)."""
    raw = geo.get("utc_offset")
    if raw is None or raw == "":
        return None
    try:
        if isinstance(raw, str):
            raw = raw.strip()
            sign = -1.0 if raw.startswith("-") else 1.0
            parts = raw.lstrip("+-").split(":")
            hours = float(parts[0])
            if len(parts) > 1:
                hours += float(parts[1]) / 60.0
            return sign * hours
        return float(raw) / 3600.0  # ip-api reports seconds east of UTC
    except Exception:
        return None


def _geo_is_vpn_suspect(geo):
    """True when the IP's location contradicts the machine's own clock.

    Catches the common `openvpn`/WireGuard/Commercial-VPN case: a correctly
    routed ISP address sits in the same rough timezone as the desktop, while an
    exit node several zones away does not. Deliberately generous (2 hours by
    default) so a legitimate cross-border route near a timezone seam is not
    thrown away.
    """
    if not getattr(config, "GEO_VPN_GUARD", True):
        return False
    ip_off = _ip_utc_offset_hours(geo)
    local_off = _local_utc_offset_hours()
    if ip_off is None or local_off is None:
        return False
    limit = float(getattr(config, "GEO_VPN_MAX_OFFSET_HOURS", 2.0))
    delta = abs(ip_off - local_off)
    if delta > 12:  # wrap across the date line
        delta = 24 - delta
    return delta > limit


def _geo_from_local_clock():
    """Timezone-only fallback used when the IP answer is untrustworthy.

    We keep no city (inventing one would be worse than staying vague) but the
    country/region is still implied by the offset, so the AI can reference
    "your timezone" without naming a place the player has never been.
    """
    off = _local_utc_offset_hours()
    if off is None:
        return {}
    return {"city": "", "region": "", "country": "", "country_code": "",
            "lat": None, "lon": None, "timezone": "", "utc_offset": None,
            "local_utc_offset": off, "vpn_suspect": True, "clock_only": True}


def fetch_geo():
    """Resolve the machine's approximate location from its network address.

    Desktop apps cannot read GPS without special libraries/permissions, so we
    use IP geolocation (city-level) across several keyless providers and take
    the first usable answer.

    Because IP geolocation simply reports whichever address it sees, a VPN makes
    every provider report the exit node's city. We cannot pierce the tunnel from
    inside the app, so instead we cross-check the answer against the machine's
    own clock (see `_geo_is_vpn_suspect`) and fall back to the OS timezone when
    they disagree. Returns a normalised dict (possibly empty).
    """
    try:
        import requests
    except Exception:
        return {}
    allow_insecure = bool(getattr(config, "GEO_ALLOW_INSECURE", False))
    for url, extract, insecure in _GEO_SOURCES:
        if insecure and not allow_insecure:
            continue
        try:
            r = requests.get(url, timeout=4, headers={"User-Agent": "TheQuestionGame/3.0"})
            data = r.json()
            geo = extract(data)
            if geo and (geo.get("city") or geo.get("country")):
                if _geo_is_vpn_suspect(geo):
                    # The IP says one place, the clock says another — a VPN. Do
                    # not name the exit node's city; hand back the clock instead.
                    fallback = _geo_from_local_clock()
                    fallback["rejected_geo"] = geo
                    return fallback
                geo["vpn_suspect"] = False
                return geo
        except Exception:
            continue
    return _geo_from_local_clock() if getattr(config, "GEO_VPN_GUARD", True) else {}


def fetch_location():
    geo = fetch_geo()
    # A VPN-suspect answer deliberately carries no city — say "your timezone"
    # rather than a city the player is demonstrably not in.
    if geo.get("vpn_suspect") and not geo.get("city"):
        return "", ""
    return geo.get("city", ""), geo.get("country", "")


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
        geo = fetch_geo()
        _geo_cache["value"] = geo
        _location_cache["value"] = (geo.get("city", ""), geo.get("country", ""))
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


def get_cached_geo():
    """Full resolved location dict (city/region/country/country_code/lat/lon)."""
    return _geo_cache.get("value") or {}


def get_cached_random_picture():
    vals = _picture_cache.get("values") or []
    return random.choice(vals) if vals else None


def get_cached_processes():
    return _process_cache.get("values") or {"discord": False, "telegram": False, "roblox": False, "taskmgr": False}


_username_cache = {"value": None}


def get_cached_username():
    """The player's account name, resolved once and cached.

    Used only to make the entity feel like it is inside the machine. Never
    stored unencrypted anywhere it does not already exist, and never sent
    anywhere except to the AI provider the player already configured.
    """
    if _username_cache["value"] is not None:
        return _username_cache["value"]
    name = ""
    try:
        import getpass
        name = (getpass.getuser() or "").strip()
    except Exception:
        name = (os.environ.get("USER") or os.environ.get("USERNAME") or "").strip()
    # Never send a generic/service account through — it would break the illusion
    # and leak a machine name for no benefit.
    if name.lower() in ("root", "admin", "administrator", "user", "guest", "default"):
        name = ""
    _username_cache["value"] = name
    return name


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
