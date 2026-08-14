"""OS window tricks for The Simpler Times.

The entity has hands. Two real, harmless effects on the player's desktop:
the game's own window drifts and shoves itself around, and the mouse is
ejected whenever it strays inside the window. Windows uses Win32 directly,
Linux uses X11 through ctypes, and macOS degrades to no-ops so the game
stays playable (just less haunted) everywhere.

Nothing here destroys data or takes over the machine — it only moves this
program's own window and the pointer, which is exactly as far as the entity
is allowed to reach.
"""
import ctypes
import platform

_SYS = platform.system()

_WIN = _SYS == "Windows"
_X11 = False
_LIB = None
if _SYS == "Linux":
    try:
        _LIB = ctypes.CDLL("libX11.so.6")
        _WinType = ctypes.c_ulong
        _LIB.XMoveWindow.argtypes = [ctypes.c_void_p, _WinType,
                                     ctypes.c_int, ctypes.c_int]
        _LIB.XMoveWindow.restype = ctypes.c_int
        _LIB.XWarpPointer.argtypes = [ctypes.c_void_p, _WinType, _WinType,
                                      ctypes.c_int, ctypes.c_int, ctypes.c_uint,
                                      ctypes.c_uint, ctypes.c_int, ctypes.c_int]
        _LIB.XWarpPointer.restype = ctypes.c_int
        _LIB.XFlush.argtypes = [ctypes.c_void_p]
        _LIB.XFlush.restype = ctypes.c_int
        _LIB.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        _LIB.XDefaultRootWindow.restype = _WinType
        _LIB.XDisplayWidth.argtypes = [ctypes.c_void_p, ctypes.c_int]
        _LIB.XDisplayWidth.restype = ctypes.c_int
        _LIB.XDisplayHeight.argtypes = [ctypes.c_void_p, ctypes.c_int]
        _LIB.XDisplayHeight.restype = ctypes.c_int
        _LIB.XTranslateCoordinates.argtypes = [ctypes.c_void_p, _WinType,
                                                _WinType, ctypes.c_int,
                                                ctypes.c_int,
                                                ctypes.POINTER(ctypes.c_int),
                                                ctypes.POINTER(ctypes.c_int),
                                                ctypes.POINTER(_WinType)]
        _LIB.XTranslateCoordinates.restype = ctypes.c_int
        _LIB.XQueryPointer.argtypes = [ctypes.c_void_p, _WinType,
                                       ctypes.POINTER(_WinType),
                                       ctypes.POINTER(_WinType),
                                       ctypes.POINTER(ctypes.c_int),
                                       ctypes.POINTER(ctypes.c_int),
                                       ctypes.POINTER(ctypes.c_int),
                                       ctypes.POINTER(ctypes.c_int),
                                       ctypes.POINTER(ctypes.c_uint)]
        _LIB.XQueryPointer.restype = ctypes.c_int
        _X11 = True
    except Exception:
        _X11 = False
        _LIB = None


def supported():
    """True when we can actually move windows / warp the pointer here."""
    return _WIN or _X11


_HEADLESS_DRIVERS = {"dummy", "offscreen", "headless"}


def _headless():
    """True when running under a video driver with no real OS window."""
    try:
        import pygame
        return pygame.display.get_driver() in _HEADLESS_DRIVERS
    except Exception:
        return True


def _wm_info():
    try:
        import pygame
        # get_wm_info() is not safe under headless/CI video drivers (it has
        # been seen to hand back garbage window pointers), so never call it
        # there — drift/guard just stay off.
        if _headless():
            return {}
        return pygame.display.get_wm_info()
    except Exception:
        return {}


_INFO_CACHE = None   # wm_info dict, or {} once it proved unavailable


def _window():
    """The OS window handle, or None. Cached: fetched at most once."""
    global _INFO_CACHE
    if _INFO_CACHE is None:
        _INFO_CACHE = _wm_info()
    win = _INFO_CACHE.get("window")
    if win:
        return int(win)
    return None


def _display():
    """X11 Display pointer (Linux only), or None."""
    if not _X11:
        return None
    global _INFO_CACHE
    if _INFO_CACHE is None:
        _INFO_CACHE = _wm_info()
    d = _INFO_CACHE.get("display")
    if d:
        return ctypes.c_void_p(int(d))
    return None


def get_position():
    """Current window position (x, y) in screen coords, or None."""
    hwnd = _window()
    if not hwnd:
        return None
    try:
        if _WIN:
            rect = ctypes.wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
            return (rect.left, rect.top)
        if _X11:
            display = _display()
            if not display:
                return None
            root = _LIB.XDefaultRootWindow(display)
            x, y = ctypes.c_int(), ctypes.c_int()
            child = _WinType()
            ok = _LIB.XTranslateCoordinates(display, hwnd, root, 0, 0,
                                            ctypes.byref(x), ctypes.byref(y),
                                            ctypes.byref(child))
            if not ok:
                return None
            return (x.value, y.value)
    except Exception:
        return None
    return None


def get_window_size():
    """Width/height of the game window (OS truth on Windows, pygame else)."""
    hwnd = _window()
    if not hwnd:
        return None
    if _WIN:
        try:
            rect = ctypes.wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
            return (rect.right - rect.left, rect.bottom - rect.top)
        except Exception:
            pass
    try:
        import pygame
        return pygame.display.get_surface().get_size()
    except Exception:
        return None


def screen_size():
    """Primary display size (w, h), or None."""
    try:
        if _WIN:
            return (ctypes.windll.user32.GetSystemMetrics(0),
                    ctypes.windll.user32.GetSystemMetrics(1))
        if _X11:
            display = _display()
            if display:
                return (_LIB.XDisplayWidth(display, 0),
                        _LIB.XDisplayHeight(display, 0))
    except Exception:
        pass
    try:
        import pygame
        info = pygame.display.Info()
        if info.current_w and info.current_h:
            return (info.current_w, info.current_h)
    except Exception:
        pass
    return None


def set_position(x, y):
    """Move the game window to (x, y) on the desktop."""
    hwnd = _window()
    if not hwnd:
        return
    try:
        if _WIN:
            w, h = get_window_size() or (640, 480)
            ctypes.windll.user32.MoveWindow(
                hwnd, int(x), int(y), int(w), int(h), True)
        elif _X11:
            display = _display()
            if display:
                _LIB.XMoveWindow(display, hwnd, int(x), int(y))
                _LIB.XFlush(display)
    except Exception:
        pass


def cursor_position():
    """Pointer position in screen coords, or None."""
    try:
        if _WIN:
            pt = ctypes.wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            return (pt.x, pt.y)
        if _X11:
            display = _display()
            if not display:
                return None
            hwnd = _window()
            if not hwnd:
                return None
            root = _WinType()
            child = _WinType()
            rx, ry, wx, wy = (ctypes.c_int(), ctypes.c_int(),
                              ctypes.c_int(), ctypes.c_int())
            mask = ctypes.c_uint()
            ok = _LIB.XQueryPointer(display, hwnd, ctypes.byref(root),
                                    ctypes.byref(child), ctypes.byref(rx),
                                    ctypes.byref(ry), ctypes.byref(wx),
                                    ctypes.byref(wy), ctypes.byref(mask))
            if not ok:
                return None
            return (rx.value, ry.value)
    except Exception:
        return None
    return None


def eject_to(x, y):
    """Warp the pointer out of the way, to (x, y) on the desktop."""
    try:
        if _WIN:
            ctypes.windll.user32.SetCursorPos(int(x), int(y))
        elif _X11:
            display = _display()
            if display:
                root = _LIB.XDefaultRootWindow(display)
                _LIB.XWarpPointer(display, 0, root, 0, 0, 0, 0,
                                  int(x), int(y))
                _LIB.XFlush(display)
    except Exception:
        pass


class WindowTrick:
    """Drifting, shoving window plus a mouse eject guard.

    Call tick(dt) every frame (window movement) and guard_mouse() when the
    window has focus (mouse eject). All OS calls are throttled and wrapped,
    so this is safe on every platform and under the dummy video driver.
    """

    READ_INTERVAL = 0.15
    MOVE_THROTTLE = 0.05
    GUARD_COOLDOWN = 0.5

    def __init__(self, guard_enabled=True):
        self.drift = supported() and not _headless()
        self.guard_enabled = guard_enabled
        self._t = 0.0
        self._last_read = 0.0
        self._last_move = 0.0
        self._last_guard = 0.0
        self._grace_until = 0.0
        self._pos = None
        self._vel = [0.0, 0.0]
        self._nudge_until = 0.0
        self._shake = None

    def set_guard(self, on):
        self.guard_enabled = bool(on)

    def grace(self, seconds=1.5):
        """ESC mercy: stop ejecting the mouse for a moment."""
        self._grace_until = self._t + seconds

    def burst(self, vx, vy):
        self._vel[0] += vx
        self._vel[1] += vy

    def shove(self, amplitude=14, duration=0.6):
        self._shake = (self._t + duration, amplitude)

    def tick(self, dt):
        if not self.drift:
            return
        self._t += dt
        if self._t - self._last_read >= self.READ_INTERVAL:
            self._last_read = self._t
            self._pos = get_position() or self._pos
        if self._pos is None:
            return

        x, y = self._pos
        if self._shake is not None:
            until, amp = self._shake
            if self._t < until:
                step = int(self._t * 24)
                sx = amp if step % 2 else -amp
                sy = amp if (step // 2) % 2 else -amp
                x += sx
                y += sy
            else:
                self._shake = None

        if self._t >= self._nudge_until:
            import random
            self._nudge_until = self._t + random.uniform(4.0, 9.0)
            speed = random.uniform(6.0, 22.0)
            self.burst(speed * random.choice((-1, 1)),
                       speed * random.choice((-1, 1)) * random.uniform(0.3, 1.0))

        self._vel[0] *= 0.90
        self._vel[1] *= 0.90
        if abs(self._vel[0]) < 0.5 and abs(self._vel[1]) < 0.5:
            self._vel[0] = self._vel[1] = 0.0
        x += self._vel[0] * dt
        y += self._vel[1] * dt

        sw, sh = screen_size()
        if sw and sh:
            ww, wh = get_window_size() or (640, 480)
            x = max(0, min(x, sw - ww))
            y = max(0, min(y, sh - 40))

        if (int(x), int(y)) != (int(self._pos[0]), int(self._pos[1])) and \
                self._t - self._last_move >= self.MOVE_THROTTLE:
            self._last_move = self._t
            self._pos = (x, y)
            set_position(x, y)

    def guard_mouse(self):
        """If the pointer is inside the game window, throw it out."""
        if not (self.drift and self.guard_enabled):
            return
        if self._t < self._grace_until:
            return
        if self._t - self._last_guard < self.GUARD_COOLDOWN:
            return
        try:
            import pygame
            if not pygame.mouse.get_focused():
                return
        except Exception:
            return
        pos = get_position()
        size = get_window_size()
        cur = cursor_position()
        sw, sh = screen_size()
        if not (pos and size and cur and sw and sh):
            return
        x, y = pos
        ww, wh = size
        if x <= cur[0] < x + ww and y <= cur[1] < y + wh:
            self._last_guard = self._t
            far_x = 0 if x + ww / 2 < sw / 2 else sw - 1
            far_y = 0 if y + wh / 2 < sh / 2 else sh - 1
            eject_to(far_x, far_y)
