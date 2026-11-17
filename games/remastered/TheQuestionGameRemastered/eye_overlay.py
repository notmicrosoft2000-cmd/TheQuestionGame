"""The desktop eye: a small window pinned to the top-right of the desktop.

When the game window loses focus, this separate process shows a small eye that
watches the cursor across the whole desktop. The *window* stays put in the
top-right corner; the pupil is what follows the mouse. A second SDL window
inside the game process is not possible (pygame owns exactly one display), so
the game re-executes itself with ``--eye-overlay`` and this module takes over.

Platform support
----------------
Windows  Full support: borderless, always-on-top, click-through, transparent
         background. Implemented with the Win32 API through ctypes.
macOS    Full support: borderless, always-on-top, click-through, transparent
         background. Implemented with Tk plus a small Objective-C bridge.
Linux    Not supported. Compositors (Wayland in particular) refuse to let a
         normal application place an always-on-top window over everything
         else. The in-game eye covers that platform.

Every failure path degrades to "no overlay" rather than to a crash. The game
must never die because the eye could not open. The child also watches its
parent and exits on its own if the game dies or is force-killed.
"""
import os
import platform
import subprocess
import sys
import threading
import time

SYSTEM = platform.system()

# The overlay is a child process of the game. It is launched with the same
# interpreter/executable so a PyInstaller build can spawn itself.
OVERLAY_FLAG = "--eye-overlay"

# The window is pinned here, not dragged after the cursor. Only the pupil
# follows the mouse.
EYE_SIZE = 120
EYE_MARGIN = 18
FPS = 30


def is_supported():
    """True if this platform can show the desktop eye."""
    return SYSTEM in ("Windows", "Darwin")


def _spawn_command():
    """How to launch the overlay process."""
    if getattr(sys, "frozen", False):
        # PyInstaller one-file build: the executable is ourselves.
        return [sys.executable, OVERLAY_FLAG], None
    # Source checkout: run this module with the same interpreter. The package
    # parent has to be the working directory so `-m` can find the package.
    return ([sys.executable, "-m", "TheQuestionGameRemastered.eye_overlay"],
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class OverlayController:
    """Owns the overlay child process.

    The game calls :meth:`start` when the player has moved away from the game
    window and :meth:`stop` when they come back. ``main`` gates those calls:
    a window that has never had focus must never spawn the eye.
    """

    def __init__(self):
        self.proc = None
        self._lock = threading.Lock()
        self._supported = is_supported()
        self._failed = False

    @property
    def supported(self):
        return self._supported and not self._failed

    @property
    def running(self):
        with self._lock:
            return self.proc is not None and self.proc.poll() is None

    def start(self):
        """Spawn the overlay. Returns True if it actually started."""
        with self._lock:
            if not self._supported or self._failed:
                return False
            if self.proc is not None and self.proc.poll() is None:
                return True
            try:
                cmd, cwd = _spawn_command()
                env = dict(os.environ)
                flags = 0
                if SYSTEM == "Windows":
                    # No console flash when the eye opens on Windows.
                    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                self.proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env=env,
                    cwd=cwd,
                    creationflags=flags,
                )
                return True
            except Exception:
                self.proc = None
                self._failed = True
                return False

    def stop(self):
        """Terminate the overlay, if it is running."""
        with self._lock:
            proc = self.proc
            self.proc = None
        if proc is None:
            return
        try:
            proc.terminate()
            try:
                proc.wait(timeout=1.5)
            except Exception:
                proc.kill()
        except Exception:
            pass


# --- the overlay process ----------------------------------------------------
def main():
    """Entry point for the overlay child process."""
    if SYSTEM == "Windows":
        return _run_windows()
    if SYSTEM == "Darwin":
        return _run_macos()
    return 0


def _eye_surface(size, pupil):
    """Render the eye onto a transparent RGBA surface (pygame)."""
    import pygame
    from . import ui
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    surf.fill((0, 0, 0, 0))
    r = int(size * 0.38)
    ui.draw_eye(surf, size // 2, size // 2, r, openness=1.0, pupil=pupil)
    return surf


def _pupil_from_cursor(size, cursor, window_xy):
    """Where the iris should sit so the eye looks at ``cursor``.

    ``window_xy`` is the overlay window's top-left corner on the desktop. The
    travel is clamped to the almond: a little less vertical than horizontal,
    so the pupil never slides out through the lids. A cursor at the window's
    centre leaves the eye staring straight ahead.
    """
    if not cursor or not window_xy:
        return (0.0, 0.0)
    try:
        cx = float(window_xy[0]) + size / 2.0
        cy = float(window_xy[1]) + size / 2.0
        dx = float(cursor[0]) - cx
        dy = float(cursor[1]) - cy
        r = size * 0.38
        max_x = r * 0.46
        max_y = max_x * 0.55
        scale = max(abs(dx) / max(max_x, 1.0), abs(dy) / max(max_y, 1.0), 1.0)
        return (dx / scale, dy / scale)
    except (TypeError, ValueError):
        return (0.0, 0.0)


def _parent_alive():
    """False once the game process is gone (closed, crashed, force-killed)."""
    try:
        pid = os.getppid()
        if pid <= 1:
            return False
        if SYSTEM == "Windows":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            SYNCHRONIZE = 0x00100000
            h = kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid)
            if not h:
                h = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
            if h:
                kernel32.CloseHandle(h)
                return True
            return False
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    except Exception:
        # If the check itself is unavailable, stay alive rather than vanish.
        return True


def _win_top_right(user32, size):
    """Primary-monitor top-right origin for the overlay window."""
    try:
        sw = int(user32.GetSystemMetrics(0))
        sh = int(user32.GetSystemMetrics(1))
        return (max(0, sw - size - EYE_MARGIN), EYE_MARGIN)
    except Exception:
        return (0, 0)


def _run_windows():
    """Windows overlay: a layered, click-through, always-on-top window."""
    import ctypes
    import ctypes.wintypes

    import pygame

    pygame.init()
    pygame.display.set_caption("eye")
    size = EYE_SIZE
    try:
        screen = pygame.display.set_mode((size, size), pygame.NOFRAME)
    except Exception:
        return 1

    try:
        user32 = ctypes.windll.user32
    except Exception:
        return 1

    try:
        hwnd = int(pygame.display.get_wm_info().get("window") or 0)
    except Exception:
        hwnd = 0
    if not hwnd:
        return 1

    WS_EX_LAYERED = 0x00080000
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_NOACTIVATE = 0x08000000
    GWL_EXSTYLE = -20
    HWND_TOPMOST = -1
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_NOACTIVATE = 0x0010
    SWP_SHOWWINDOW = 0x0040
    LWA_COLORKEY = 0x00000001

    # Pure magenta is vanishingly unlikely to appear in the eye art.
    KEY = 0xFF00FF

    try:
        user32.GetWindowLongW.restype = ctypes.c_long
        user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.SetWindowLongW.restype = ctypes.c_long
        user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                          ctypes.c_long]
        user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                        ctypes.c_int, ctypes.c_int,
                                        ctypes.c_int, ctypes.c_int,
                                        ctypes.c_uint]
        user32.GetCursorPos.argtypes = [ctypes.c_void_p]
        user32.GetSystemMetrics.argtypes = [ctypes.c_int]
        user32.GetSystemMetrics.restype = ctypes.c_int
    except Exception:
        pass

    origin = _win_top_right(user32, size)
    try:
        style = user32.GetWindowLongW(ctypes.c_void_p(hwnd), GWL_EXSTYLE)
        user32.SetWindowLongW(
            ctypes.c_void_p(hwnd), GWL_EXSTYLE,
            style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
            | WS_EX_NOACTIVATE)
        user32.SetLayeredWindowAttributes(ctypes.c_void_p(hwnd), KEY, 255,
                                          LWA_COLORKEY)
        user32.SetWindowPos(ctypes.c_void_p(hwnd), ctypes.c_void_p(HWND_TOPMOST),
                            origin[0], origin[1], size, size,
                            SWP_NOACTIVATE | SWP_SHOWWINDOW)
    except Exception:
        return 1

    class _PT(ctypes.wintypes.POINT):
        pass

    clock = pygame.time.Clock()
    running = True
    last_parent_check = time.time()
    while running:
        clock.tick(FPS)
        try:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
        except Exception:
            pass

        if time.time() - last_parent_check > 0.5:
            last_parent_check = time.time()
            if not _parent_alive():
                break

        cursor = None
        try:
            pt = _PT()
            if user32.GetCursorPos(ctypes.byref(pt)):
                cursor = (int(pt.x), int(pt.y))
        except Exception:
            cursor = None

        try:
            art = _eye_surface(size, _pupil_from_cursor(size, cursor, origin))
            screen.fill(KEY)
            screen.blit(art, (0, 0))
            pygame.display.flip()
        except Exception:
            pass
    return 0


def _run_macos():
    """macOS overlay: a Tk window in the top-right with a live pupil."""
    try:
        import tkinter
    except Exception:
        return 1

    import pygame
    # pygame has to be initialised before `ui` is imported: ui reads the font
    # at import time.
    pygame.init()
    from . import ui  # noqa: F401  (kept in sync with the pygame path)

    size = EYE_SIZE
    try:
        root = tkinter.Tk()
    except Exception:
        return 1
    try:
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        try:
            root.attributes("-transparent", True)
        except Exception:
            pass
        # macOS Tk has no "-transparent" attribute on most builds, but it does
        # understand "systemTransparent": a toplevel painted in it is see-through.
        try:
            root.configure(bg="systemTransparent")
        except Exception:
            pass
        canvas = tkinter.Canvas(root, width=size, height=size,
                                highlightthickness=0, bd=0)
        try:
            canvas.configure(bg="systemTransparent")
        except Exception:
            pass
        canvas.pack()
        screen_w = int(root.winfo_screenwidth())
        screen_h = int(root.winfo_screenheight())
        origin = (max(0, screen_w - size - EYE_MARGIN), EYE_MARGIN)
        root.geometry("%dx%d+%d+%d" % (size, size, origin[0], origin[1]))
    except Exception:
        try:
            root.destroy()
        except Exception:
            pass
        return 1

    # If this fails the eye still works, it just eats clicks.
    try:
        _mac_make_click_through(root)
    except Exception:
        pass

    running = True

    def _on_close():
        nonlocal running
        running = False
        try:
            root.destroy()
        except Exception:
            pass

    try:
        root.protocol("WM_DELETE_WINDOW", _on_close)
    except Exception:
        pass

    last_parent_check = time.time()
    while running:
        try:
            root.update()
        except Exception:
            break

        if time.time() - last_parent_check > 0.5:
            last_parent_check = time.time()
            if not _parent_alive():
                break

        cursor = None
        try:
            from . import os_layer
            cursor = os_layer.get_global_cursor()
        except Exception:
            cursor = None
        px, py = _pupil_from_cursor(size, cursor, origin)

        # Canvas line art: the same almond lids, one iris ring and a pupil.
        r = size * 0.38
        cx = cy = size // 2
        ry = r * 0.56
        ir = r * 0.44
        pr = ir * 0.52
        try:
            pts = []
            steps = 32
            for i in range(steps + 1):
                t = i / float(steps)
                pts.extend((cx + r * (2.0 * t - 1.0),
                            cy - 4.0 * ry * t * (1.0 - t)))
            for i in range(steps, -1, -1):
                t = i / float(steps)
                pts.extend((cx + r * (2.0 * t - 1.0),
                            cy + 4.0 * ry * t * (1.0 - t)))
            canvas.delete("all")
            canvas.create_polygon(pts, fill="", outline="black", width=4)
            canvas.create_polygon(pts, fill="", outline="#e6e6e0", width=2)
            ix, iy = cx + px, cy + py
            canvas.create_oval(ix - ir, iy - ir, ix + ir, iy + ir,
                               fill="", outline="#7e1212", width=2)
            canvas.create_oval(ix - pr, iy - pr, ix + pr, iy + pr,
                               fill="black", outline="#7e1212", width=1)
        except Exception:
            pass
        time.sleep(1.0 / FPS)
    return 0


def _mac_make_click_through(root):
    """Tell AppKit the Tk window should ignore mouse events and float above
    everything else, without stealing focus or adding a Dock tile."""
    import ctypes

    libobjc = ctypes.cdll.LoadLibrary("/usr/lib/libobjc.dylib")
    libobjc.objc_getClass.restype = ctypes.c_void_p
    libobjc.objc_sel_registerName.restype = ctypes.c_void_p
    # Do not pin argtypes: objc_msgSend is variadic and takes 0..n arguments.
    libobjc.objc_msgSend.restype = ctypes.c_void_p
    libobjc.objc_msgSend.argtypes = None

    def send(obj, sel, *args):
        return libobjc.objc_msgSend(ctypes.cast(obj, ctypes.c_void_p),
                                    ctypes.cast(sel, ctypes.c_void_p), *args)

    def as_int(value):
        # objc_msgSend returns c_void_p here; int(ptr) reads its raw bytes.
        if isinstance(value, int):
            return value
        return int(getattr(value, "value", 0) or 0)

    ns_app_cls = libobjc.objc_getClass(b"NSApplication")
    sel_shared = libobjc.objc_sel_registerName(b"sharedApplication")
    ns_app = send(ns_app_cls, sel_shared)
    if not ns_app:
        return False

    # NSApplicationActivationPolicyProhibited = 2.
    send(ns_app, libobjc.objc_sel_registerName(b"setActivationPolicy:"),
         ctypes.c_long(2))

    windows = send(ns_app, libobjc.objc_sel_registerName(b"windows"))
    if not windows:
        return False
    count = send(windows, libobjc.objc_sel_registerName(b"count"))
    if not count:
        return False
    sel_obj_at = libobjc.objc_sel_registerName(b"objectAtIndex:")
    for i in range(as_int(count)):
        ns_window = send(windows, sel_obj_at, ctypes.c_long(i))
        if not ns_window:
            continue
        send(ns_window, libobjc.objc_sel_registerName(b"setIgnoresMouseEvents:"),
             ctypes.c_bool(True))
        # NSPopUpMenuWindowLevel (101) sits above almost everything.
        send(ns_window, libobjc.objc_sel_registerName(b"setLevel:"),
             ctypes.c_long(101))
        return True
    return False


if __name__ == "__main__":
    sys.exit(main())
