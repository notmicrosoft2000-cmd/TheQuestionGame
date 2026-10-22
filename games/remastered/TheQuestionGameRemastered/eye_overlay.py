"""The desktop eye: a small borderless window that follows the player's cursor
around the desktop, so the game can watch them even when it is not the
foreground window.

This runs as a *separate process*. A second SDL window inside the game process
is not possible (pygame owns exactly one display), so the game re-executes
itself with ``--eye-overlay`` and this module takes over.

Platform support
----------------
Windows  Full support: borderless, always-on-top, click-through, transparent
         background. Implemented with the Win32 API through ctypes.
macOS    Full support: borderless, always-on-top, click-through, transparent
         background. Implemented with Tk (for the window) plus a small
         Objective-C bridge (for click-through and the window level).
Linux    Not supported. Compositors (Wayland in particular) refuse to let a
         normal application place an always-on-top window over everything
         else, and X11's override-redirect hacks are not worth the trouble.
         The in-game eye covers this platform.

Every failure path here degrades to "no overlay" rather than to a crash. The
game must never die because the eye could not open.
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

# How far the eye sits from the cursor, so it never sits *on* the pointer.
CURSOR_OFFSET = 26

# The window size of the eye (square).
EYE_SIZE = 120


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
    window and :meth:`stop` when they come back.
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
                self.proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env=env,
                    cwd=cwd,
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


def _pupil_toward_cursor(size, pupil_max_frac=0.52):
    """The eye trails the cursor, so the pupil always looks back at it."""
    import math
    r = int(size * 0.38)
    off = r * pupil_max_frac
    d = math.sqrt(2) / 2.0
    return (-off * d, -off * d)


def _run_windows():
    """Windows overlay: a Win32 layered, click-through, always-on-top window."""
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

    # The colour used as the transparency key. Pure magenta is vanishingly
    # unlikely to appear in the eye art.
    KEY = 0xFF00FF

    try:
        user32.GetWindowLongW.restype = ctypes.c_long
        user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.SetWindowLongW.restype = ctypes.c_long
        user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
        user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                        ctypes.c_int, ctypes.c_int,
                                        ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        user32.GetCursorPos.argtypes = [ctypes.c_void_p]
    except Exception:
        pass

    try:
        style = user32.GetWindowLongW(ctypes.c_void_p(hwnd), GWL_EXSTYLE)
        user32.SetWindowLongW(
            ctypes.c_void_p(hwnd), GWL_EXSTYLE,
            style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
        user32.SetLayeredWindowAttributes(ctypes.c_void_p(hwnd), KEY, 255, LWA_COLORKEY)
        user32.SetWindowPos(ctypes.c_void_p(hwnd), ctypes.c_void_p(HWND_TOPMOST),
                            0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
    except Exception:
        return 1

    class _PT(ctypes.wintypes.POINT):
        pass

    # The eye art never changes (the pupil always looks back at the cursor),
    # so it is rendered exactly once.
    try:
        art = _eye_surface(size, _pupil_toward_cursor(size))
    except Exception:
        return 1

    clock = pygame.time.Clock()
    running = True
    while running:
        clock.tick(60)
        try:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
        except Exception:
            pass

        cursor = None
        try:
            pt = _PT()
            if user32.GetCursorPos(ctypes.byref(pt)):
                cursor = (int(pt.x), int(pt.y))
        except Exception:
            cursor = None
        if cursor is None:
            time.sleep(0.05)
            continue

        # Move the window so the eye trails the cursor.
        try:
            user32.SetWindowPos(ctypes.c_void_p(hwnd), ctypes.c_void_p(HWND_TOPMOST),
                                int(cursor[0] + CURSOR_OFFSET),
                                int(cursor[1] + CURSOR_OFFSET),
                                size, size, SWP_NOACTIVATE | SWP_SHOWWINDOW)
        except Exception:
            pass

        screen.fill((255, 0, 255))      # the transparency key colour
        screen.blit(art, (0, 0))
        try:
            pygame.display.flip()
        except Exception:
            pass
    return 0


def _run_macos():
    """macOS overlay: a Tk window (borderless, always on top, transparent)
    with the eye drawn into it."""
    try:
        import tkinter
    except Exception:
        return 1

    import pygame
    # pygame has to be initialised before `ui` is imported: ui reads the font
    # at import time.
    pygame.init()
    from . import ui

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
        # understand the special "systemTransparent" background colour: a
        # toplevel painted in it is see-through. Best effort either way.
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
    except Exception:
        try:
            root.destroy()
        except Exception:
            pass
        return 1

    # Click-through: find the NSWindow Tk created and tell AppKit to ignore
    # mouse events. If this fails the eye still works, it just eats clicks.
    try:
        _mac_make_click_through(root)
    except Exception:
        pass

    # Render the eye art once, to a PNG with alpha, and hand it to Tk.
    photo = None
    pupil = _pupil_toward_cursor(size)
    try:
        import base64
        import tempfile
        frame = _eye_surface(size, pupil)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fh:
            path = fh.name
        pygame.image.save(frame, path)
        with open(path, "rb") as fh:
            data = fh.read()
        try:
            os.unlink(path)
        except Exception:
            pass
        photo = tkinter.PhotoImage(data=base64.b64encode(data))
        canvas.delete("all")
        canvas.create_image(0, 0, image=photo, anchor="nw")
        root.update()
    except Exception:
        photo = None

    if photo is None:
        # Some Tk builds cannot read a PNG. Draw the same eye with canvas
        # primitives instead — fewer shades, but the same shape.
        try:
            px, py = pupil
            r = size * 0.38
            cx = cy = size // 2
            ry = r * 0.56
            ir = r * 0.54
            pr = ir * 0.5
            canvas.delete("all")
            canvas.create_oval(cx - r - 2, cy - ry - 2, cx + r + 2, cy + ry + 2,
                               fill="black", outline="")
            canvas.create_oval(cx - r, cy - ry, cx + r, cy + ry,
                               fill="#eeeeea", outline="")
            canvas.create_oval(cx + px - ir, cy + py - ir, cx + px + ir, cy + py + ir,
                               fill="#0c0c0c", outline="")
            canvas.create_oval(cx + px - pr, cy + py - pr, cx + px + pr, cy + py + pr,
                               fill="black", outline="")
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

    while running:
        try:
            root.update()
        except Exception:
            break
        cursor = None
        try:
            from . import os_layer
            cursor = os_layer.get_global_cursor()
        except Exception:
            cursor = None
        if cursor is None:
            time.sleep(0.05)
            continue
        try:
            root.geometry("+%d+%d" % (int(cursor[0] + CURSOR_OFFSET),
                                      int(cursor[1] + CURSOR_OFFSET)))
        except Exception:
            pass
        time.sleep(0.016)
    return 0


def _mac_make_click_through(root):
    """Tell AppKit the Tk window should ignore mouse events and float above
    everything else.

    The overlay process also switches itself to a prohibited activation
    policy, so it does not steal focus from whatever the player clicked, and
    does not put a second icon in the Dock.
    """
    import ctypes

    libobjc = ctypes.cdll.LoadLibrary("/usr/lib/libobjc.dylib")
    libobjc.objc_getClass.restype = ctypes.c_void_p
    libobjc.objc_sel_registerName.restype = ctypes.c_void_p
    libobjc.objc_msgSend.restype = ctypes.c_void_p
    libobjc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

    ns_app_cls = libobjc.objc_getClass(b"NSApplication")
    sel_shared = libobjc.objc_sel_registerName(b"sharedApplication")
    ns_app = libobjc.objc_msgSend(ctypes.c_void_p(ns_app_cls),
                                  ctypes.c_void_p(sel_shared))
    if not ns_app:
        return False

    # NSApplicationActivationPolicyProhibited = 2. The eye is a background
    # agent: no Dock tile, no focus stealing.
    sel_policy = libobjc.objc_sel_registerName(b"setActivationPolicy:")
    libobjc.objc_msgSend(ctypes.c_void_p(ns_app), ctypes.c_void_p(sel_policy),
                         ctypes.c_long(2))

    sel_windows = libobjc.objc_sel_registerName(b"windows")
    windows = libobjc.objc_msgSend(ctypes.c_void_p(ns_app),
                                   ctypes.c_void_p(sel_windows))
    sel_count = libobjc.objc_sel_registerName(b"count")
    count = libobjc.objc_msgSend(ctypes.c_void_p(windows), ctypes.c_void_p(sel_count))
    if not count:
        return False
    sel_obj_at = libobjc.objc_sel_registerName(b"objectAtIndex:")
    for i in range(int(count)):
        ns_window = libobjc.objc_msgSend(ctypes.c_void_p(windows),
                                         ctypes.c_void_p(sel_obj_at),
                                         ctypes.c_long(i))
        if not ns_window:
            continue
        sel_ignore = libobjc.objc_sel_registerName(b"setIgnoresMouseEvents:")
        libobjc.objc_msgSend(ctypes.c_void_p(ns_window),
                             ctypes.c_void_p(sel_ignore), ctypes.c_bool(True))
        sel_level = libobjc.objc_sel_registerName(b"setLevel:")
        # NSPopUpMenuWindowLevel (101) sits above almost everything.
        libobjc.objc_msgSend(ctypes.c_void_p(ns_window),
                             ctypes.c_void_p(sel_level), ctypes.c_long(101))
        return True
    return False


if __name__ == "__main__":
    sys.exit(main())
