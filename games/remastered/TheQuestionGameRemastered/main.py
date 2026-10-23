"""The Question Game Remastered — entry point.

Run with:  python -m TheQuestionGameRemastered.main
"""
import getpass
import math
import os
import random
import threading
import time
import uuid

import pygame

from . import ai_client
from . import audio
from . import config
from . import interjections
from . import os_layer
from . import persistence
from . import scares
from . import script
from . import social
from . import ui
from . import updater

# Touch/fullscreen platform switch (see config.IS_ANDROID). Kept as a module
# global so tests can flip it and drive the touch paths headlessly.
IS_ANDROID = config.IS_ANDROID

ABOUT_VARIATIONS = [
    "ABOUT THE SIMULATION\n\nThis software interacts with your local environment metrics to generate specialized psychological response loops.\n\nIt reads hardware profiles and stores transient user configuration states in a persistent local file.\n\nYour answers are remembered.",
    "ABOUT THIS EXPERIENCE\n\nA behavioral analysis program masquerading as a game.\n\nYour responses are logged, timed, and cross-referenced.\n\nThe longer you play, the more it knows.\n\nThis file is persistent. It does not forget.",
    "SYSTEM OVERVIEW\n\nDesigned to probe the boundary between a screen and the person behind it.\n\nAll behavioral data is stored locally.\n\nEvery session is written fresh by something that watches you answer.\n\nYou are not the first to play this.",
]

HELP_VARIATIONS = [
    "CONTROLS & OPERATIONS\n\n[TAB]   — Cycle through menu/answer options\n[ENTER] — Confirm selection\n[ESC]   — Return from About/Help menus\n\nANSWER ALL QUESTIONS TRUTHFULLY.\nThe system detects inconsistencies.\n\nYour response time is monitored.\nPausing too long will be noted.",
    "HOW TO PLAY\n\n[TAB]   — Navigate options\n[ENTER] — Select\n\nThere is no skip. There is no fast forward.\nThere is only the next question.\n\nThe questions change every time you play.\nThey are written for you, in the moment.\n\nThe game remembers. Do you?",
    "SAFETY & OPERATIONS LOG\n\n[TAB]   — Move between choices\n[ENTER] — Confirm\n\nQ: Are local effects dangerous?\nA: No. Effects are cosmetic: flicker, sound, window movement.\n\nQ: Are answers transmitted?\nA: The questions are generated remotely. Your answers stay local.\n\nQ: What does it do with my answers?\nA: It remembers them.",
    "THE ROOM\n\nONLINE IS AN ALPHA. IT WILL BREAK. A LOT.\n\nQ: What is the room?\nA: A list of who is playing. The game checks in with it every few seconds. The room lives on the server that runs the game. Nothing is installed on your machine.\n\nQ: Where do the questions come from?\nA: Most are written by the program. Some are written by hand, by someone else. Those join the queue between the others and look exactly the same.\n\nQ: Can I write to the room?\nA: No. You can see it and be seen in it. The writing half is not in this build.",
]

# The ONLINE screen explains the room in the game's own voice: what it is, what
# travels over it, and what the player is not allowed to do with it. No host
# address, no tool names — the mechanics, not the plumbing.
ONLINE_EXPLAINER = [
    "THE GAME CHECKS IN WITH THE ROOM EVERY FEW SECONDS — THAT",
    "IS HOW YOU ARE FOUND BY THE OTHERS. THE ROOM LIVES ON THE",
    "SERVER THAT RUNS THE GAME, NOT ON YOUR MACHINE.",
    "QUESTIONS WRITTEN BY HAND BY SOMEONE ELSE CAN JOIN THE",
    "QUEUE BETWEEN THE ORDINARY ONES. THEY LOOK THE SAME, AND",
    "NOBODY ANNOUNCES THEM.",
    "YOU CAN SEE THE ROOM AND BE SEEN IN IT. YOU CANNOT WRITE",
    "TO IT — THAT HALF IS NOT IN THIS BUILD.",
]

# Names that mean "the operator's sender is connected". Matching is on the peer
# name because the relay only knows ids and display names; the sender's name
# defaults to OPERATOR (TQG_SENDER_NAME) unless the operator renames it.
_OPERATOR_NAMES = frozenset({"OPERATOR", "OPERATOR APP", "SENDER"})


def _is_operator_peer(peer):
    """True when this room member is the operator's sender, not a player."""
    if not isinstance(peer, dict):
        return False
    name = str(peer.get("name") or "").strip().upper()
    return name in _OPERATOR_NAMES

# Lobbies are not built yet. These are shown on the ONLINE screen as a teaser:
# a fixed, obviously-placeholder list so the shape of the feature is visible
# without pretending any of it works. Nothing here is clickable or real.
ONLINE_LOBBY_TEASER = [
    ("NIGHT SHIFT", "soon"),
    ("THE WAITING ROOM", "soon"),
    ("SESSION 3 ARCHIVE", "soon"),
    ("PRIVATE — BY INVITATION", "later"),
]
ONLINE_LOBBY_BLURB = [
    "ROOMS OF YOUR OWN ARE COMING. OPEN A LOBBY, DECIDE WHO",
    "GETS IN, AND KEEP A SESSION TO YOURSELF INSTEAD OF",
    "SHARING ONE WITH EVERY INSTALL. NONE OF THIS WORKS YET.",
]

LOGS_ENTRIES = [
    "ENTRY 04 — UNDATED\n\nThe questions were never the point. The pauses were.\nWe started timing the silences before we started reading the answers.",
    "ENTRY 11 — UNDATED\n\nSubject returned a second time. Most do not.\nWe do not know what brings them back. We have stopped asking.",
    "ENTRY 19 — UNDATED\n\nThe wallpaper change was supposed to be temporary.\nIt is not always temporary anymore.",
    "ENTRY 30 — UNDATED\n\nIf you are reading this, you typed the code quickly enough.\nThat was the test. Not the questions before it.",
    "ENTRY 47 — UNDATED\n\nWe archived a dozen sessions that look almost identical.\nSmall variations in hesitation, different times of day.\nAn emergent pattern we did not anticipate.",
    "ENTRY 77 — UNDATED\n\nSometimes we leave a breadcrumb.\nIf someone follows it twice, they find the key.",
    "ENTRY 99 — UNDATED\n\nAt the end we found a photograph of an empty chair.\nIt was labeled 'waiting'.\nWe kept it.",
    "ENTRY 140 — UNDATED\n\nA user reported their mouse moving on its own.\nVideo shows the cursor sliding in regular arcs every 17 seconds.\nWe matched the intervals to the heartbeat samples collected during Run 3.",
    "ENTRY 166 — UNDATED\n\nSubject tried to close the window forty times in a row.\nOn the ninth try the window moved itself out from under the cursor.\nSubject stopped after that. They did not leave.",
    "ENTRY 172 — UNDATED\n\nThe camera feed was never required.\nWe leave it off most sessions now — the ones who notice it anyway\nare the ones worth watching.",
    "ENTRY 203 — UNDATED\n\nThere are no buttons in the title bar of this build.\nWe removed them in version three after someone mistook them for a promise.",
]

CREDITS_TEXT = "\n".join([
    "CREDITS",
    "Menu Music: Moonbit",
    "Coding: Neptune",
    "Dialogue: The Entity",
    "Development: Neptune",
    "",
    "Special Thanks:",
    "Players who returned.",
])

_TITLE = "THE QUESTION GAME"
_TITLE_SUB = "(R)"

# What the entity hisses at you when you reach for the close button. The window
# reacting "angry" is the point: it should feel like you hurt it.
_ANGRY_CLOSE_LINES = [
    "Do not touch that.",
    "We felt that.",
    "You do not get to leave.",
    "Try it again. I dare you.",
    "You are only making it worse.",
    "Take your hand off the window.",
]


def _account_name():
    """The name of the account this copy of the game is running under.

    That is what the room shows, unless the player picks a name of their own
    with [N] on the ONLINE screen.
    """
    name = ""
    try:
        name = (getpass.getuser() or "").strip()
    except Exception:
        name = ""
    if not name:
        for var in ("USER", "USERNAME", "LOGNAME"):
            name = (os.environ.get(var) or "").strip()
            if name:
                break
    if not name:
        name = "guest-%04d" % random.randint(0, 9999)
    return name[:config.SOCIAL_NAME_MAX]


class Game:
    # Drawing target vs. the real window.
    #
    # `screen` is what the whole game draws into, and it is deliberately a plain
    # off-screen surface. The window surface is *never cached*: pygame hands out
    # a brand new Surface object every time the window manager resizes the
    # window, so a saved copy ends up pointing at an SDL surface that has
    # already been freed. Drawing into that is a use-after-free, and the window
    # keeps showing the fresh (black) surface pygame handed out instead — that
    # was the black screen with no menu.
    #
    # `_display_surface()` asks pygame who the window is, every time.
    @property
    def screen(self):
        return self._frame

    # --- the window ----------------------------------------------------------
    def _window_size(self):
        """The size the window opens at, from the resolution setting."""
        sset = self.game_state.get("settings", {}) or {}
        res = str(sset.get("resolution", "") or "").lower()
        if "x" in res:
            try:
                w, h = res.split("x", 1)
                w, h = int(w), int(h)
                if w >= config.WINDOW_MIN_W and h >= config.WINDOW_MIN_H:
                    return (w, h)
            except Exception:
                pass
        return (config.WINDOW_W, config.WINDOW_H)

    def _render_size(self, win_size):
        """The size of the drawing frame for a window of this size.

        The UI scale is a real scale: the game is drawn at another resolution
        and stretched to the window, so the text and the layout grow or shrink
        together. Scaling the fonts alone would leave the text drifting out of
        its boxes.
        """
        scale = 1.0
        try:
            scale = float((self.game_state.get("settings", {}) or {})
                          .get("ui_scale", 1.0) or 1.0)
        except Exception:
            scale = 1.0
        scale = max(0.5, min(2.0, scale))
        return (max(1, int(round(win_size[0] / scale))),
                max(1, int(round(win_size[1] / scale))))

    def _create_display(self):
        """Create the window, honouring the video settings.

        Fullscreen and vsync are asked of the driver. A driver that cannot do
        either is not an error: the game runs windowed, and unthrottled.
        """
        flags = pygame.NOFRAME if config.WINDOW_LOCKED else pygame.RESIZABLE
        if IS_ANDROID:
            try:
                info = pygame.display.Info()
                disp = pygame.display.set_mode(
                    (info.current_w, info.current_h), pygame.FULLSCREEN)
                self._video_applied = self._video_wanted()
                return disp
            except Exception:
                disp = pygame.display.set_mode((config.WINDOW_W, config.WINDOW_H), flags)
                self._video_applied = self._video_wanted()
                return disp
        sset = self.game_state.get("settings", {}) or {}
        size = self._window_size()
        fullscreen = bool(sset.get("fullscreen", False))
        if fullscreen:
            flags |= pygame.FULLSCREEN
        vsync = 1 if sset.get("vsync", True) else 0
        disp = None
        for attempt in (lambda: pygame.display.set_mode(size, flags, vsync=vsync),
                        lambda: pygame.display.set_mode(size, flags),
                        lambda: pygame.display.set_mode((config.WINDOW_W,
                                                         config.WINDOW_H), flags)):
            try:
                disp = attempt()
                break
            except Exception:
                disp = None
        if disp is None:
            disp = pygame.display.get_surface()
        if disp is not None and not fullscreen and getattr(self, "_leaving_fullscreen", False):
            # SDL throws away a size request that arrives while the window is
            # still fullscreen, so on some versions (2.28 on Linux, for one) a
            # window that has just come out of fullscreen keeps the
            # fullscreen size and the game is left drawing into a window the
            # player never asked for. Asking again, now that the window is a
            # window again, fixes it. The position is kept: pygame retains it
            # when the size does not change.
            try:
                disp = pygame.display.set_mode(size, flags)
            except Exception:
                pass
        if not config.WINDOW_LOCKED and not fullscreen:
            try:
                self._apply_resize_limits()
            except Exception:
                pass
        self._video_applied = self._video_wanted()
        return disp

    def _video_wanted(self):
        """The video settings as a comparable tuple."""
        sset = self.game_state.get("settings", {}) or {}
        return (bool(sset.get("fullscreen", False)),
                bool(sset.get("vsync", True)),
                str(sset.get("resolution", "")))

    def _apply_video_settings(self):
        """Re-make the window when the video settings change.

        Fullscreen and the resolution are properties of the window itself, so
        they can only be changed by making a new one. The UI scale needs no
        window: the frame is simply drawn at another resolution.
        """
        want = self._video_wanted()
        applied = getattr(self, "_video_applied", None)
        if getattr(self, "_video_applied", None) == want:
            # Only the UI scale changed: resize the frame, not the window.
            try:
                self._set_frame_size(self._display.get_size())
            except Exception:
                pass
            return
        # Was the window fullscreen and is it not any more? Then it has to be
        # asked for its size again once it is a window (see _create_display).
        self._leaving_fullscreen = bool(applied and applied[0]) and not bool(want[0])
        self._video_applied = want
        try:
            self._display = self._create_display()
        except Exception:
            return
        try:
            # The window is a new one, so its id (and the driver's) may have
            # changed. Forget what the OS layer cached about the old one.
            os_layer.reset_window_cache()
            self._frame = self._new_frame(self._render_size(self._display.get_size()))
            self._font_cache_key = None
            self._black_overlay_key = None
            if getattr(self, "starfield", None) is not None:
                self.starfield = ui.build_starfield(*self._frame.get_size())
        except Exception:
            pass

    def __init__(self):
        pygame.init()
        pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
        try:
            pygame.mixer.set_num_channels(16)  # default 8 exhausts under scare layers
        except Exception:
            pass
        # The save file decides the window, so it is read before the display is
        # made: a player who asked for fullscreen, a different resolution or a
        # different UI scale gets it on the first run, not after a restart.
        self.game_state = persistence.load_game_state()
        self.run_count = self.game_state.get("run_count", 1)
        try:
            self.settings_idx = self._load_settings_idx()
        except Exception:
            self.settings_idx = dict(config.SETTING_DEFAULTS)
        self.ai = ai_client.ScaryAI()
        self._leaving_fullscreen = False
        self._display = self._create_display()
        # Everything from here on draws into this surface; _draw() copies it
        # onto the window. See the `screen` property above for why.
        self._frame = self._new_frame(self._render_size(self._display.get_size()))
        # The window surface we last painted opaque (see _make_window_opaque).
        self._opaque_surface = None
        try:
            icon = pygame.image.load(config.asset_path("windowq.png")).convert_alpha()
            pygame.display.set_icon(icon)
        except Exception:
            pass
        pygame.display.set_caption(config.APP_NAME)
        pygame.mouse.set_visible(False)

        try:
            self._apply_settings()
        except Exception:
            pass
        self.state = "LOADING"
        self.now = time.time()
        self.loading_start = self.now

        self.active_script = []
        self.current_step = 0
        self.typing_index = 0
        self.typing_state = "THINKING"
        self.thinking_timer = 0
        self.last_type_time = 0
        self.question_start_time = 0
        self.selected_answer = 0
        # Tap targets recorded while drawing; hit-tested by _handle_touch.
        self._touch_zones = []
        self.wait_start_time = 0
        self.pending_exit = False
        self.exit_message_at = 0
        self.local_image = None
        self.captured_window_title = ""

        self.fx = {
            "flicker_until": 0.0,
            "corrupt_until": 0.0,
            "webcam_flash_until": 0.0,
            "rgb_split_until": 0.0,
            "screen_tear_until": 0.0,
            "whisper_text": None,
            "whisper_until": 0.0,
            # Malware-theme overlay clocks (fake scan / BSOD / console / file
            # list / security modal). They are drawn inside the game and scale
            # with the operator's effect dial like every other deadline.
            "fake_scan_at": 0.0,
            "fake_scan_until": 0.0,
            "fake_bsod_at": 0.0,
            "fake_bsod_until": 0.0,
            "fake_terminal_at": 0.0,
            "fake_terminal_until": 0.0,
            "terminal_lines": None,
            "file_names_at": 0.0,
            "file_names_until": 0.0,
            "file_names": None,
            "security_alert_at": 0.0,
            "security_alert_until": 0.0,
            # Multiplier applied to the *duration* of a scare. The operator's
            # sender sets it per effect, so the same scare can land gently or
            # hard. 1.0 is the game's own behaviour. The relay clamps the
            # operator's dial to 0.1-2.0; this clamps again so a hand-made
            # effect can never stretch a scare past 2.5x.
            "scare_scale": 1.0,
        }

        self.session_history = []
        self.close_attempts = 0
        self._used_scares = set()
        self._scares_fired = 0
        self._proc_check_at = 0.0
        self._start_time = time.time()
        self._app_comment_done = False
        self._last_cmd_time = time.time()
        self._next_beep_time = time.time() + random.uniform(*config.BACKGROUND_BEEP_INTERVAL)
        self._lore_injected = set()
        self._font_cache = None
        self._font_cache_key = None
        self._black_overlay_cache = None
        self._black_overlay_key = None

        self.menu_options = ["PLAY", "ONLINE", "SETTINGS", "HELP", "ABOUT", "EXIT"]
        # If LOGS was unlocked in a previous session, keep it on the menu.
        if self.game_state.get("logs_unlocked") and "LOGS" not in self.menu_options:
            self.menu_options.insert(len(self.menu_options) - 1, "LOGS")
        self.selected_option = 0
        self.settings_categories = ["AUDIO", "VIDEO", "GRAPHICS", "GAMEPLAY", "ACCESSIBILITY", "CONTROLS", "OTHER"]
        self.settings_category_selected = 0
        self.settings_options_by_category = {
            "AUDIO": ["Master Volume", "SFX Volume", "Ambience Volume", "Music Volume"],
            "VIDEO": ["Fullscreen", "VSync", "Resolution", "UI Scale"],
            "GRAPHICS": ["Performance Mode", "CRT Effects", "CRT Intensity", "Scanlines", "Vignette", "Dust", "Static Line", "Tube Curvature", "Phosphor Mask"],
            "GAMEPLAY": ["Font", "Text Speed", "Text Size", "Text Sway", "AI Source"],
            "ACCESSIBILITY": ["Reduce Flashes", "Disable Screen Shake", "Disable Webcam Scares", "Disable Desktop Scares"],
            "CONTROLS": ["Rebind: Up", "Rebind: Down", "Rebind: Confirm", "Rebind: Back/Pause"],
            "OTHER": ["VHS Effects", "Reset All Data", "< Back"],
        }
        self.settings_options = self.settings_options_by_category[self.settings_categories[self.settings_category_selected]]
        self.settings_selected = 0
        self.settings_scroll = 0
        self.settings_idx = self._load_settings_idx()
        self.pause_options = ["RESUME", "SETTINGS", "MAIN MENU", "EXIT"]
        self.pause_selected = 0
        self.paused = False
        self.rebinding = None
        self.rebind_error = ""
        self.rebind_error_until = 0.0
        # The desktop eye: a separate process that trails the player's cursor
        # across their whole desktop while the game window is not focused.
        try:
            from . import eye_overlay
            self._overlay = eye_overlay.OverlayController()
        except Exception:
            self._overlay = None
        self._window_focused = True
        self._eye_state = {
            "x": 0, "y": 0, "radius": 0,
            "pupil_x": 0, "pupil_y": 0,
            "blink_until": 0.0,
            "blink_start": 0.0,
            "next_blink": time.time() + random.uniform(4.0, 9.0),
            "scared_until": 0.0,
            # Answer reactions and pupil size.
            "answers": [],
            "reaction_until": 0.0,
            "reaction_kind": "",
            "reaction_dilation": 1.0,
            "reaction_angry": False,
            "reaction_blend": 0.0,
            "pulse_phase": 0.0,
            "pulse_epoch": time.time(),
        }
        # Filled in by whichever screen draws the current highlight. The eye
        # reads it after the frame is drawn, so it looks at the real option,
        # not at a guessed screen coordinate.
        self._eye_focus_rect = None
        self.about_selected = 0
        self.credits_scroll_y = 0

        # --- online (presence + hand-written questions) ---------------------
        # The receiver half only: the game joins the room, questions addressed
        # to it arrive between questions, and the answers are reported back.
        # *Writing* questions is not part of this build at all — that is the
        # operator's separate sender app, and the relay enforces the split.
        # The client is optional and degrades to OFFLINE; nothing below assumes
        # it exists.
        self.social = None
        self.social_notes = []          # [{text, at, tone}] transient notices
        self.online_edit = None         # {"text": ...} while renaming yourself
        self.online_options = ["TEST CONNECTION", "BACK"]
        self.online_selected = 0
        self.online_test = {"state": "idle", "detail": "", "ms": 0}
        self._social_poll_at = 0.0
        self._social_pending_cache = None
        self._init_social()

        # --- updates --------------------------------------------------------
        # The background checker only reports; opening the download page is the
        # player's choice. It is started from run(), not from __init__, so tests
        # and tools that construct a Game never touch the network.
        self.update_checker = updater.UpdateChecker(
            state_path=os.path.join(config.APP_DATA_DIR, "update_check.json"))
        self.update_available = None
        self._update_checker_started = False

        self.fade = {"active": False, "dir": "in", "start": 0, "dur": 0.25, "alpha": 255, "target": None}

        self.badge_toast_id = None
        self.badge_toast_at = 0
        self.close_msg_until = 0
        self._close_burst = 0
        self._last_close_try = -999.0
        self.idle_tracker = {"focused": True, "lost_at": 0, "last_away": 0, "pending": False}
        self.shake_x, self.shake_y = 0, 0

        self._cheat_buffer = []
        self._cheat_last = 0
        self._CHEAT_CODE = [pygame.K_2, pygame.K_0, pygame.K_1, pygame.K_3]

        self.about_text = random.choice(ABOUT_VARIATIONS)
        self.help_text = random.choice(HELP_VARIATIONS)
        if IS_ANDROID:
            self.help_text += ("\n\nON THIS DEVICE\n\nTap an option — it selects and confirms in one "
                               "gesture, no TAB/ENTER needed.\nSwipe back (or use the system Back "
                               "button) to leave a screen.\n\nANSWER ALL QUESTIONS TRUTHFULLY.")

        self.starfield = ui.build_starfield(config.WINDOW_W, config.WINDOW_H)
        self.clock = pygame.time.Clock()
        self.running = True

        audio.build_sound_cache()
        audio.start_ambience()
        os_layer.start_background_prefetch()
        if config.WINDOW_LOCKED:
            os_layer.set_window_topmost()
            os_layer.disable_system_close()
            os_layer.start_topmost_keeper()
        self._startup_badges()
        self._begin_session()

    # --- the window surface ---------------------------------------------------
    def _display_surface(self):
        """The live window surface — fetched fresh, never cached.

        pygame replaces the Surface *object* whenever the window manager
        resizes the window (the old one points at an SDL surface that SDL has
        already freed). A cached copy is therefore a use-after-free waiting to
        happen: the game draws into freed memory while the window shows the
        fresh, empty surface pygame handed out. That is exactly the "black
        screen, no menu" report.

        Always ask pygame who the window is.
        """
        try:
            surf = pygame.display.get_surface()
        except Exception:
            surf = None
        if surf is None:
            surf = getattr(self, "_display", None)
        return surf

    def _new_frame(self, size):
        """A drawing surface the size of the window — deliberately *without* an
        alpha channel.

        The window surface is 32-bit ARGB under Wayland (24-bit under X11), so
        a frame built with the default format — or `.convert()`ed to the
        display format, as this used to be — carries alpha bytes. Every
        alpha-overlay the game draws (scanlines, vignette, CRT mask, snow)
        then writes those bytes, and pygame's blit of such a frame onto the
        window multiplies the frame's RGB by its alpha. A frame whose alpha
        was wiped by an overlay therefore renders as a *black window* on
        Wayland, while looking perfectly fine on X11, where the window has no
        alpha channel at all.

        A 24-bit frame has no alpha bytes to wipe: the overlays still blend
        their RGB exactly as before, but nothing can make the frame
        transparent, and the copy onto the window is a straight RGB copy.
        """
        size = (max(1, int(size[0])), max(1, int(size[1])))
        try:
            return pygame.Surface(size, 0, 24)
        except Exception:
            return pygame.Surface(size)

    def _make_window_opaque(self, disp):
        """Make sure the window surface is opaque, not transparent.

        Under Wayland the window surface is 32-bit ARGB and SDL hands it over
        with the alpha bytes cleared, i.e. a *transparent* window: a
        compositor that honours the window's alpha shows nothing at all. So the
        window is painted opaque once per surface — pygame only hands out a
        new surface object when the window is resized, and the frame copy
        that follows is a plain RGB copy that leaves the alpha alone.
        """
        if disp is self._opaque_surface:
            return
        try:
            disp.fill((0, 0, 0, 255))
        except Exception:
            pass
        self._opaque_surface = disp

    def _set_frame_size(self, size):
        """Resize the drawing frame (and everything that is baked to its size)."""
        size = self._render_size(size)
        if size == self._frame.get_size():
            return
        self._frame = self._new_frame(size)
        # Fonts are sized from the frame, so the cache has to go.
        self._font_cache_key = None
        # The starfield is baked to a fixed size, so rebuild it for the new
        # frame or the dressing would only cover part of the screen.
        if getattr(self, "starfield", None) is not None:
            self.starfield = ui.build_starfield(size[0], size[1])

    def _sync_frame(self):
        """Keep the drawing frame the same size as the window.

        Cheap insurance, run once per frame: a window manager can resize the
        window without the VIDEORESIZE event reaching us (or before it does),
        and pygame hands out a new Surface object when it does. A frame that no
        longer matches the window is how the screen goes black.
        """
        disp = self._display_surface()
        if disp is None:
            return
        size = disp.get_size()
        if size != self._frame.get_size():
            self._set_frame_size(size)

    def _apply_resize_limits(self):
        """Clamp the resizeable frame so it can never swallow the desktop.

        There is no fullscreen toggle in this build by design; the cheapest way
        to guarantee that is to cap the resizable window below the screen size.
        The floor *and* the ceiling are handed to the window manager as size
        hints, so the drag itself is clamped by the WM and the window follows
        the cursor smoothly. (The old comment claimed SDL2 had no max-size
        hint — it does: `set_window_maximum_size`.)
        """
        try:
            # Desktop resolution, NOT the current window. pygame's Info() reports
            # the *window* size once a window exists, so querying it here (after
            # set_mode) made the ceiling "window minus margin" — 720x480 for an
            # 800x600 start — and every upward resize snapped back down.
            # get_desktop_sizes() keeps reporting the real desktop regardless.
            desktop_w, desktop_h = pygame.display.get_desktop_sizes()[0]
        except Exception:
            try:
                info = pygame.display.Info()
                desktop_w, desktop_h = info.current_w, info.current_h
            except Exception:
                desktop_w, desktop_h = config.WINDOW_MAX_W, config.WINDOW_MAX_H
        # Leave only a sliver so the window never covers the whole desktop (the
        # "no fullscreen" rule) while still letting the player use their screen.
        # The old 80/120px margin was brutal on small displays: a 1024x768
        # desktop capped at 944x648, barely above the 800x600 start, so an
        # upward drag clamped straight back and felt like it "didn't work".
        max_w = min(config.WINDOW_MAX_W, max(config.WINDOW_MIN_W, desktop_w - 16))
        max_h = min(config.WINDOW_MAX_H, max(config.WINDOW_MIN_H, desktop_h - 16))
        self._max_window = (max_w, max_h)
        try:
            pygame.display.set_window_minimum_size(config.WINDOW_MIN_W,
                                                   config.WINDOW_MIN_H)
        except Exception:
            pass  # older SDL/pygame: the minimum is soft, the maximum still holds
        try:
            pygame.display.set_window_maximum_size(max_w, max_h)
        except Exception:
            pass  # some WMs ignore the ceiling; the frame clamp still holds

    def _clamped_size(self, w, h):
        """The window size the game allows, between the floor and the ceiling."""
        max_w, max_h = getattr(self, "_max_window",
                               (config.WINDOW_MAX_W, config.WINDOW_MAX_H))
        cw = max(config.WINDOW_MIN_W, min(int(w), max_w))
        ch = max(config.WINDOW_MIN_H, min(int(h), max_h))
        return (cw, ch)

    def _on_resize(self, w, h):
        """Follow a drag-to-resize, clamped between the floor and the ceiling.

        The window manager has already resized the window by the time this
        runs, so the only job left is to match the drawing frame to it.

        The old code called `pygame.display.set_mode()` to do that, and that is
        what broke the drag: set_mode() re-shows the window and fills it with
        black before the next frame is drawn, so the window blinked out and
        back on every mouse move ("it disappears and reappears"), it reset the
        size hints the WM uses to clamp the drag, and it re-fired VIDEORESIZE,
        so the frame fought the cursor. Nothing here touches the window any
        more — the WM owns the window, we own the frame.
        """
        size = self._clamped_size(w, h)
        disp = self._display_surface()
        if disp is not None and disp.get_size() == size:
            # The window surface already followed the window — it is the
            # authority (it knows about DPI scaling).
            size = disp.get_size()
        self._set_frame_size(size)

    # --- setup helpers -------------------------------------------------------
    def _load_settings_idx(self):
        idx = dict(config.SETTING_DEFAULTS)
        s = self.game_state.get("settings", {}) or {}
        speed = s.get("text_speed", 0.04)
        if speed <= 0.0175:
            idx["Text Speed"] = 0
        elif speed <= 0.0325:
            idx["Text Speed"] = 1
        elif speed <= 0.06:
            idx["Text Speed"] = 2
        elif speed <= 0.1:
            idx["Text Speed"] = 3
        else:
            idx["Text Speed"] = 4
        vhs = s.get("vhs_intensity", 1.0)
        if vhs <= 0.0:
            idx["VHS Effects"] = 0
        elif vhs <= 0.4:
            idx["VHS Effects"] = 1
        elif vhs <= 1.5:
            idx["VHS Effects"] = 2
        elif vhs <= 2.5:
            idx["VHS Effects"] = 3
        else:
            idx["VHS Effects"] = 4
        sway = s.get("sway_intensity", 1.0)
        if sway <= 0.0:
            idx["Text Sway"] = 0
        elif sway <= 0.4:
            idx["Text Sway"] = 1
        elif sway <= 1.4:
            idx["Text Sway"] = 2
        else:
            idx["Text Sway"] = 3
        size = s.get("text_size", 1.0)
        if size <= 0.85:
            idx["Text Size"] = 0
        elif size <= 1.1:
            idx["Text Size"] = 1
        elif size <= 1.4:
            idx["Text Size"] = 2
        else:
            idx["Text Size"] = 3
        font_label = s.get("font", "Courier")
        try:
            idx["Font"] = config.SETTING_OPTIONS["Font"].index(font_label)
        except (ValueError, KeyError):
            idx["Font"] = 0
        source_label = s.get("ai_source", "Relay")
        try:
            idx["AI Source"] = config.SETTING_OPTIONS["AI Source"].index(source_label)
        except (ValueError, KeyError):
            idx["AI Source"] = 0
        for key in ("Master Volume", "SFX Volume", "Ambience Volume", "Music Volume", "CRT Intensity", "UI Scale"):
            val = None
            if key == "CRT Intensity":
                val = s.get("crt_intensity")
            elif key == "UI Scale":
                val = s.get("ui_scale")
            else:
                val = s.get(key.lower().replace(" ", "_"))
            if isinstance(val, (int, float)) and key in config.SETTING_MAPS:
                best = 0
                best_diff = 10
                for i, v in enumerate(config.SETTING_MAPS[key]):
                    d = abs(float(val) - float(v))
                    if d < best_diff:
                        best_diff = d
                        best = i
                idx[key] = best
        idx["Fullscreen"] = 1 if s.get("fullscreen", False) else 0
        idx["VSync"] = 1 if s.get("vsync", True) else 0
        try:
            idx["Resolution"] = config.SETTING_OPTIONS["Resolution"].index(
                s.get("resolution", "800x600"))
        except (ValueError, KeyError):
            idx["Resolution"] = 1
        perf = s.get("performance_mode", "Medium")
        try:
            idx["Performance Mode"] = config.SETTING_OPTIONS["Performance Mode"].index(perf)
        except (ValueError, KeyError):
            idx["Performance Mode"] = 1
        idx["CRT Effects"] = 1 if s.get("crt_enabled", True) else 0
        idx["Scanlines"] = 1 if s.get("scanlines_enabled", True) else 0
        idx["Vignette"] = 1 if s.get("vignette_enabled", True) else 0
        idx["Dust"] = 1 if s.get("dust_enabled", True) else 0
        idx["Static Line"] = 1 if s.get("static_line_enabled", True) else 0
        idx["Tube Curvature"] = 1 if s.get("tube_curvature_enabled", True) else 0
        idx["Phosphor Mask"] = 1 if s.get("phosphor_mask_enabled", True) else 0
        idx["Reduce Flashes"] = 1 if s.get("disable_flashes", False) else 0
        idx["Disable Screen Shake"] = 1 if s.get("disable_screen_shake", False) else 0
        idx["Disable Webcam Scares"] = 1 if s.get("disable_webcam_scares", False) else 0
        idx["Disable Desktop Scares"] = 1 if s.get("disable_desktop_scares", False) else 0
        return idx

    def _startup_badges(self):
        if self.run_count >= 2:
            if persistence.award_badge("returning"):
                self.badge_toast_id = "returning"
                self.badge_toast_at = self.now
        if self.run_count >= 3:
            if persistence.award_badge("persistent"):
                self.badge_toast_id = "persistent"
                self.badge_toast_at = self.now
        import platform
        if platform.system() == "Darwin":
            persistence.award_badge("pioneer")
        try:
            hour = int(time.strftime("%H"))
            if 2 <= hour < 5 and persistence.award_badge("night_owl"):
                self.badge_toast_id = "night_owl"
                self.badge_toast_at = self.now
        except Exception:
            pass

    def _begin_session(self):
        self.run_count = self.game_state.get("run_count", 1)
        if self.run_count == 2:
            threading.Thread(target=os_layer.set_desktop_wallpaper,
                             args=(self.game_state.get("fav_color", "black"),), daemon=True).start()
        self.active_script = script.build_session(self.game_state, self.ai)
        self.session_history = []
        self._used_scares = set()
        self._scares_fired = 0
        self.current_step = 0
        self._skip_inactive()
        self._reset_question_state()
        self._prefetch_question(self.current_step)

    def _prefetch_question(self, index, force=False):
        """Start a background fetch for a pending step (lazy generation).

        Two kinds of placeholders exist: `ai_pending` (written by the model)
        and `dynamic_pending` (built from real machine state). Both resolve on
        a worker thread; `q` is written last as the "ready" flag.
        """
        if index >= len(self.active_script):
            return
        step = self.active_script[index]
        if step.get("type") not in ("ai_pending", "dynamic_pending"):
            return
        if step.get("q") is not None:
            return
        if step.get("_fetching") and not force:
            return
        step["_fetching"] = True
        target = self._fetch_dynamic_step if step.get("type") == "dynamic_pending" else self._fetch_ai_step
        threading.Thread(target=target, args=(step,), daemon=True).start()

    def _fetch_dynamic_step(self, step):
        """Fill a dynamic_pending step from cached machine state (off-thread)."""
        q, opts, meta, extra = None, [], {}, []
        try:
            data = interjections.resolve_dynamic(step.get("_resolver"), self.game_state, self.run_count)
            q = data.get("q")
            opts = data.get("opts") or []
            meta = data.get("meta") or {}
            extra = data.get("extra") or []
        except Exception:
            q, opts = None, []
        if not q or len(opts) < 2:
            q = q or "Are you still there?"
            opts = opts or ["...", "..."]
        for key, value in meta.items():
            step[key] = value
        if extra:
            step["_extra_steps"] = extra
        step["_injected"] = True
        step["opts"] = opts
        step["type"] = "choice"
        step["q"] = q
        # Warm the country flag in the background if this was a location step.
        try:
            geo = step.get("_location_card")
            if geo and geo.get("country_code"):
                ui.prefetch_flag(geo.get("country_code"))
        except Exception:
            pass

    def _skip_inactive(self):
        """Advance past steps whose `_condition` is not met (Classic-style
        conditional questions, e.g. blinds only if there is a window)."""
        answers = self.game_state.get("answers", {})
        while self.current_step < len(self.active_script):
            step = self.active_script[self.current_step]
            cond = step.get("_condition")
            if not cond:
                break
            req_id, req_val = cond
            if answers.get(req_id) == req_val:
                break
            self.current_step += 1

    def _enforce_scare_floor(self):
        """Guarantee each run fires at least SCARE_FLOOR effects.

        The model picks its own scares and often answers "none" — which means a
        whole run can pass without the machine ever touching the player. This
        tops the run up with locally chosen effects (never repeating one already
        spent) so the escalation curve is real, not left to chance. Do nothing on
        the final beats so the ending stays clean.
        """
        floor = config.SCARE_FLOOR.get(self.run_count, 0)
        if self._scares_fired >= floor:
            return
        # Don't fire over the ending, and don't bunch effects up.
        if self.current_step >= len(self.active_script) - 2:
            return
        if self.now - getattr(self, "_last_forced_scare", -999) < 5.0:
            return
        pool = [n for n in config.SCARE_FLOOR_POOL if n not in self._used_scares]
        if not pool:
            return
        name = random.choice(pool)
        try:
            if scares.apply_scare(self, name):
                self._used_scares.add(name)
                self._scares_fired += 1
                self._last_forced_scare = self.now
        except Exception:
            pass

    def _ai_facts(self):
        """Assemble everything the entity is allowed to 'know' about this player.

        This is what makes the AI feel like it is actually watching: their name,
        what is open on their machine, what they said in earlier sessions, how
        often they hesitated, and which effects it has already spent.
        """
        facts = {}
        try:
            facts["hesitations"] = self.game_state.get("hesitation_count", 0)
            facts["lies"] = self.game_state.get("lie_count", 0)
        except Exception:
            pass
        facts["used_scares"] = sorted(getattr(self, "_used_scares", set()))
        try:
            name = os_layer.get_cached_username()
            if name:
                facts["name"] = name
        except Exception:
            pass
        try:
            procs = os_layer.get_cached_processes()
            apps = [k for k, v in procs.items() if v]
            if apps:
                facts["apps"] = apps
        except Exception:
            pass
        # Quotes from previous sessions: the strongest callbacks the game has.
        try:
            earlier = []
            for _id, rec in (self.game_state.get("answers", {}) or {}).items():
                if isinstance(rec, dict):
                    ans = rec.get("answer")
                else:
                    ans = rec
                if ans:
                    earlier.append(str(ans))
            if earlier:
                facts["earlier_runs"] = ", ".join(earlier[-6:])
        except Exception:
            pass
        return facts

    def _fetch_ai_step(self, step):
        """Fill an ai_pending placeholder from the AI (offline fallback built in).

        `q` is written last — the main thread treats a non-None `q` as the
        "ready" flag, so no half-filled step can ever be drawn.
        """
        q, opts, scare, src = None, [], None, None
        asked = []
        try:
            asked = list(self.game_state.get("asked_questions") or [])
        except Exception:
            asked = []
        try:
            result = ai_client.next_question(self.ai, self.run_count,
                                             list(self.session_history),
                                             geo=os_layer.get_cached_geo(),
                                             facts=self._ai_facts(),
                                             asked=asked)
            q = result.get("q")
            opts = result.get("opts") or []
            scare = result.get("scare")
            src = result.get("_source")
        except Exception:
            q, opts = None, []
        if not q or len(opts) < 2:
            q = q or "Are you still there?"
            opts = opts or ["...", "..."]
            scare = None
        step["opts"] = opts
        if scare:
            step["scare"] = scare
        if src:
            step["_source"] = src
        step["_id"] = step.get("_id") or "ai"
        step["type"] = "choice"
        step["q"] = q

    def _remember_asked(self, q):
        """Append a question to the cross-session list (deduped, capped)."""
        q = " ".join(str(q or "").split())
        if not q:
            return
        box = self.game_state.get("asked_questions")
        if not isinstance(box, list):
            box = []
            self.game_state["asked_questions"] = box
        if q not in box:
            box.append(q)
        # Keep the save small; the prompt only sends the most recent 60.
        if len(box) > 500:
            del box[:-500]

    def _reset_question_state(self):
        self.typing_state = "THINKING"
        self.thinking_timer = self.now
        self.typing_index = 0
        self.selected_answer = 0
        self.question_start_time = self.now
        self.wait_start_time = 0

    def _apply_settings(self):
        s = self.game_state.setdefault("settings", {})
        s["font"] = config.SETTING_OPTIONS["Font"][self.settings_idx["Font"]]
        s["text_speed"] = config.SETTING_MAPS["Text Speed"][self.settings_idx["Text Speed"]]
        s["vhs_intensity"] = config.SETTING_MAPS["VHS Effects"][self.settings_idx["VHS Effects"]]
        s["sway_intensity"] = config.SETTING_MAPS["Text Sway"][self.settings_idx["Text Sway"]]
        s["text_size"] = config.SETTING_MAPS["Text Size"][self.settings_idx["Text Size"]]
        source = config.SETTING_OPTIONS["AI Source"][self.settings_idx["AI Source"]]
        s["ai_source"] = source
        self._apply_ai_source(source)
        if "Master Volume" in self.settings_idx:
            s["master_volume"] = config.SETTING_MAPS["Master Volume"][self.settings_idx["Master Volume"]]
        if "SFX Volume" in self.settings_idx:
            s["sfx_volume"] = config.SETTING_MAPS["SFX Volume"][self.settings_idx["SFX Volume"]]
        if "Ambience Volume" in self.settings_idx:
            s["ambience_volume"] = config.SETTING_MAPS["Ambience Volume"][self.settings_idx["Ambience Volume"]]
        if "Music Volume" in self.settings_idx:
            s["music_volume"] = config.SETTING_MAPS["Music Volume"][self.settings_idx["Music Volume"]]
        s["fullscreen"] = bool(self.settings_idx.get("Fullscreen", 0))
        s["vsync"] = bool(self.settings_idx.get("VSync", 1))
        s["resolution"] = config.SETTING_OPTIONS["Resolution"][
            self.settings_idx.get("Resolution", 1)]
        s["performance_mode"] = config.SETTING_OPTIONS["Performance Mode"][self.settings_idx.get("Performance Mode", 1)]
        s["crt_enabled"] = bool(self.settings_idx.get("CRT Effects", 1))
        if "CRT Intensity" in self.settings_idx:
            s["crt_intensity"] = config.SETTING_MAPS["CRT Intensity"][self.settings_idx["CRT Intensity"]]
        s["scanlines_enabled"] = bool(self.settings_idx.get("Scanlines", 1))
        s["vignette_enabled"] = bool(self.settings_idx.get("Vignette", 1))
        s["dust_enabled"] = bool(self.settings_idx.get("Dust", 1))
        s["static_line_enabled"] = bool(self.settings_idx.get("Static Line", 1))
        s["tube_curvature_enabled"] = bool(self.settings_idx.get("Tube Curvature", 1))
        s["phosphor_mask_enabled"] = bool(self.settings_idx.get("Phosphor Mask", 1))
        if "UI Scale" in self.settings_idx:
            s["ui_scale"] = config.SETTING_MAPS["UI Scale"][self.settings_idx["UI Scale"]]
        s["disable_flashes"] = bool(self.settings_idx.get("Reduce Flashes", 0))
        s["disable_screen_shake"] = bool(self.settings_idx.get("Disable Screen Shake", 0))
        s["disable_webcam_scares"] = bool(self.settings_idx.get("Disable Webcam Scares", 0))
        s["disable_desktop_scares"] = bool(self.settings_idx.get("Disable Desktop Scares", 0))
        try:
            # The desktop window-jiggle is part of the screen shake, so the
            # switch reaches the OS layer too.
            os_layer.set_shake_enabled(not s["disable_screen_shake"])
        except Exception:
            pass
        try:
            # Fullscreen, the resolution and the UI scale are properties of
            # the window, so they are applied by re-making it.
            self._apply_video_settings()
        except Exception:
            pass
        try:
            # The module-level import is the package's own audio module — a
            # local `import audio` would look for a *top-level* module and
            # quietly fail, leaving the volumes at their defaults.
            mv = float(s.get("master_volume", 1.0))
            sv = float(s.get("sfx_volume", 1.0))
            av = float(s.get("ambience_volume", 1.0))
            muv = float(s.get("music_volume", 0.5))
            audio.set_music_volume(muv * mv)
            audio.set_ambience_volume(av * mv)
            audio.set_sfx_volume(sv * mv)
        except Exception:
            pass
        self._font_cache = None
        self._font_cache_key = None
        persistence.save_game_state(self.game_state)

    def _apply_ai_source(self, source):
        """Point the game at the chosen AI backend and rebuild the client.

        Relay  -> Neptune's server holds the key (the shipped default).
        Local  -> a local Ollama model, if one is installed.
        Offline-> no network at all; the offline question bank only.
        """
        provider = config.AI_SOURCE_PROVIDERS.get(source, "relay")
        if provider == "offline":
            self.ai = None
            return
        config.AI_PROVIDER = provider
        try:
            self.ai = ai_client.ScaryAI()
        except Exception:
            self.ai = None

    # --- social (online players + hand-written questions) -------------------
    def _init_social(self):
        """Create the presence client; never fatal, never blocks.

        The peer id is generated **per run**, not per save file. Two windows on
        one machine share a save (and therefore a player name), and they must
        still be two distinct people in the room — persisting the id made each
        copy filter the other out as "itself", so a room full of players looked
        empty. The display name stays persisted; only the session id is fresh.
        """
        if not config.SOCIAL_ENABLED:
            return
        try:
            player_id = uuid.uuid4().hex
            name = self.game_state.get("player_name")
            # A name the player chose is theirs and is kept. The auto-generated
            # guest name is NOT reused across runs: two windows on one machine
            # would then both appear as "guest-1234", which is indistinguishable
            # in the room and looks like a duplicate/bug. The default is the
            # name of the account running this copy of the game.
            if not name or str(name).startswith("guest-"):
                name = _account_name()
                self.game_state["player_name"] = name
            persistence.save_game_state(self.game_state)
            self.social = social.SocialClient(player_id, name)
        except Exception:
            self.social = None

    def _social_name(self):
        if self.social is not None:
            try:
                return self.social.name
            except Exception:
                pass
        return self.game_state.get("player_name", "guest")

    def _note(self, text, tone="info", seconds=6.0):
        """Queue a transient notice; drawn as a toast by _draw."""
        self.social_notes.append({"text": text, "at": self.now, "tone": tone,
                                  "_ttl": seconds})
        del self.social_notes[:-6]

    def _poll_social(self):
        """Harvest results from the worker thread (cheap, once a second)."""
        if self.social is None or self.now - self._social_poll_at < 1.0:
            return
        self._social_poll_at = self.now
        try:
            for res in self.social.take_results():
                if res.get("local"):
                    self._note("COULD NOT DELIVER — " + str(res.get("error", "offline")).upper(),
                               "bad", 6.0)
                    continue
                who = res.get("by") or "someone"
                choice = res.get("choice") or ""
                correct = res.get("correct")
                if correct is True:
                    self._note("%s ANSWERED YOUR QUESTION: RIGHT" % who.upper(), "good", 8.0)
                elif correct is False:
                    self._note("%s ANSWERED YOUR QUESTION: WRONG (%s)" % (who.upper(), choice.upper()),
                               "bad", 8.0)
                else:
                    self._note("%s ANSWERED YOUR QUESTION: %s" % (who.upper(), choice.upper()),
                               "info", 8.0)
        except Exception:
            pass
        # A question that lands is a secret: nothing announces it. It simply
        # joins the queue between the written ones and looks like the rest.
        try:
            pending = self.social.pending_questions()
        except Exception:
            pending = 0
        self._social_pending_cache = pending
        self._play_social_effects()

    # --- updates -------------------------------------------------------------
    def _poll_update_check(self):
        """Harvest the background checker's result (cheap; once when due)."""
        info = self.update_checker.poll()
        if info:
            self.update_available = info
            self._note("UPDATE AVAILABLE: v%s — OPEN THE TITLE SCREEN"
                       % info.get("version", "?"), "good", 12.0)

    def _open_update_page(self):
        """Open the release page in the player's browser. Never auto-installs."""
        info = self.update_available or {}
        url = info.get("url") or config.UPDATE_RELEASE_PAGE
        opened = False
        try:
            import webbrowser
            opened = bool(webbrowser.open(url))
        except Exception:
            opened = False
        if opened:
            self._note("OPENING THE DOWNLOAD PAGE...", "info", 4.0)
        else:
            # No browser (or a locked-down device): show the address instead of
            # pretending the click worked.
            self._note("DOWNLOAD: " + url, "info", 12.0)

    def _start_update_check(self):
        """Start the automatic checker once, from the real game loop."""
        if self._update_checker_started:
            return
        self._update_checker_started = True
        try:
            self.update_checker.start()
        except Exception:
            pass

    def _maybe_check_updates(self):
        if not self._update_checker_started:
            return
        try:
            self.update_checker.maybe_check()
        except Exception:
            pass

    def _play_social_effects(self):
        """Play any scare/glitch the operator fired at us.

        Same rule as a question: nothing announces it. No toast, no note — the
        effect simply happens, exactly as if the model had chosen it. The
        intensity the operator set stretches how long the effect lasts, so "a
        little" and "a lot" are actually different on screen.
        """
        if self.social is None:
            return
        for _ in range(8):
            try:
                item = self.social.take_effect()
            except Exception:
                return
            if not item:
                return
            name = str(item.get("effect") or "").strip().lower()
            if not name:
                continue
            try:
                inten = float(item.get("intensity") or 1.0)
            except (TypeError, ValueError):
                inten = 1.0
            try:
                # The operator's dial stretches how long the effect lasts.
                fx = self.fx
                before = fx.get("scare_scale", 1.0)
                fx["scare_scale"] = max(0.25, min(2.5, inten))
                if scares.apply_scare(self, name):
                    self._scares_fired += 1
                    self._used_scares.add(name)
                fx["scare_scale"] = before
            except Exception:
                pass

    def _social_step_from(self, item):
        """Convert a relay question into a playable script step."""
        opts = list(item.get("opts") or [])
        if len(opts) < 2:
            opts = ["...", "..."]
        return {
            "type": "choice",
            "q": item.get("q") or "...",
            "opts": opts,
            "_id": "social_" + str(item.get("id") or "q"),
            "_social": item,
            "_from_social": True,
            "_injected": True,
        }

    def _queue_social_question(self):
        """If the relay gave us a question, make it the next thing shown."""
        if self.social is None:
            return False
        try:
            item = self.social.take_question()
        except Exception:
            item = None
        if not item:
            return False
        self.active_script.insert(self.current_step, self._social_step_from(item))
        self._prefetch_question(self.current_step)
        return True

    # --- online screen (receiver-side) --------------------------------------
    # This build does not write questions; that is the operator's sender app.
    # What remains here is the *player* half: the ONLINE entry shows the room
    # this session has joined — the relay's state, who else is playing, and
    # the name the other players see. Questions from the operator still arrive
    # during play (see _queue_social_question).

    def _online_status(self):
        """(status, others) from the presence client; never fatal.

        The operator is filtered out: the room is shown as *players*. Seeing a
        peer called OPERATOR in the list would tell the player that someone is
        watching them specifically, which is exactly what the room must not
        give away. The operator still receives their questions.
        """
        if self.social is None:
            return "disabled", []
        try:
            status = self.social.status()
        except Exception:
            status = "offline"
        try:
            others = self.social.others()
        except Exception:
            others = []
        try:
            others = [p for p in others if not _is_operator_peer(p)]
        except Exception:
            pass
        return status, others

    def _commit_online_name(self, text):
        """Take a new display name into the room and into the save file."""
        name = str(text or "").strip()[:config.SOCIAL_NAME_MAX]
        if not name:
            return
        if self.social is not None:
            try:
                self.social.set_name(name)
            except Exception:
                pass
        self.game_state["player_name"] = name
        try:
            persistence.save_game_state(self.game_state)
        except Exception:
            pass
        self._note("THE ROOM NOW CALLS YOU " + name.upper(), "good", 6.0)

    def _online_key(self, key, unicode=""):
        """The ONLINE screen: the room, your name in it, a connection test."""
        if self.online_edit is not None:
            text = self.online_edit
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._commit_online_name(text["text"])
                self.online_edit = None
            elif key == pygame.K_ESCAPE:
                self.online_edit = None
            elif key == pygame.K_BACKSPACE:
                text["text"] = text["text"][:-1]
            elif unicode and unicode.isprintable() and unicode not in "\t\r\n":
                if len(text["text"]) < config.SOCIAL_NAME_MAX:
                    text["text"] += unicode
            return
        if key == pygame.K_ESCAPE:
            audio.play_ui_select_sound()
            self.start_fade("TITLE")
        elif key == pygame.K_BACKSPACE:
            audio.play_ui_select_sound()
            self.start_fade("TITLE")
        elif key == pygame.K_n:
            # pygame has no uppercase key constants: shift+n arrives as the
            # same key code, and the character itself comes through as
            # "N" in the unicode argument.
            audio.play_ui_select_sound()
            self.online_edit = {"text": self._social_name()}
        elif key == pygame.K_t:
            self._start_connection_test()
        elif key in (pygame.K_UP, pygame.K_DOWN):
            step = -1 if key == pygame.K_UP else 1
            self.online_selected = (self.online_selected + step) % len(self.online_options)
            audio.play_ui_select_sound()
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self._online_activate(self.online_selected)

    def _online_activate(self, idx):
        """Run the option the player picked on the ONLINE screen."""
        if idx == 0:
            self._start_connection_test()
        else:
            audio.play_ui_select_sound()
            self.start_fade("TITLE")

    def _start_connection_test(self):
        """Ping the relay in the background and let the screen report it."""
        if self.social is None:
            self.online_test = {"state": "fail",
                                "detail": "MULTIPLAYER IS OFF IN THIS BUILD",
                                "ms": 0}
            return
        if self.online_test.get("state") == "running":
            return
        self.online_test = {"state": "running", "detail": "TESTING...", "ms": 0}

        def work():
            try:
                ok, detail, ms = self.social.test_connection()
            except Exception as exc:
                ok, detail, ms = False, type(exc).__name__.upper(), 0
            self.online_test = {"state": "ok" if ok else "fail",
                                "detail": detail, "ms": ms}

        threading.Thread(target=work, daemon=True, name="tqg-conn-test").start()

    def _report_social_answer(self, item, answer):
        """Tell the author what we picked, and react to it ourselves."""
        opts = list(item.get("opts") or [])
        correct = item.get("correct")
        right = None
        if isinstance(correct, int) and not isinstance(correct, bool) \
                and 0 <= correct < len(opts):
            right = (opts[correct] == answer)
        if self.social is not None:
            try:
                self.social.send_answer(item, answer, right)
            except Exception:
                pass
        who = str(item.get("from_name") or "someone").upper()
        if right is True:
            self._note("ANSWERED %s: RIGHT" % who, "good", 5.0)
        elif right is False:
            self._note("ANSWERED %s: WRONG" % who, "bad", 5.0)
        else:
            self._note("ANSWER SENT BACK TO %s" % who, "info", 5.0)
        if self.fx.get("whisper_until", 0.0) <= self.now:
            if right is True:
                whisper = "%s KNOWS YOU WERE RIGHT" % who
            elif right is False:
                whisper = "%s KNOWS YOU WERE WRONG" % who
            else:
                whisper = "ANSWER SENT TO %s" % who
            self.fx["whisper_text"] = whisper
            self.fx["whisper_until"] = self.now + 4.0

    # --- fade ----------------------------------------------------------------
    def start_fade(self, target):
        self.fade = {"active": True, "dir": "out", "start": self.now, "dur": 0.25, "alpha": 255, "target": target}

    def _update_fade(self):
        if not self.fade["active"]:
            return
        t = min(1.0, (self.now - self.fade["start"]) / max(0.001, self.fade["dur"]))
        if self.fade["dir"] == "out":
            self.fade["alpha"] = 255.0 * t
            if t >= 1.0:
                self.state = self.fade["target"]
                self._on_state_enter()
                self.fade["dir"] = "in"
                self.fade["start"] = self.now
                self.fade["alpha"] = 255.0
        else:
            self.fade["alpha"] = 255.0 * (1.0 - t)
            if t >= 1.0:
                self.fade["active"] = False

    def _on_state_enter(self):
        if self.state == "PLAYING":
            self._begin_session()
        if self.state == "ONLINE":
            # The room is joined by the presence client; there is no separate
            # compatibility probe any more. Any half-finished rename is dropped.
            self.online_edit = None
        self._apply_stage_music()

    def _apply_stage_music(self):
        """Music scores the *menu* screens only (Settings / About / Help / Logs).

        Gameplay and the title stay on ambience + SFX alone — the track is the
        calm around the questions, not a soundtrack under them.
        """
        if not config.MUSIC_ENABLED:
            return
        menu_states = ("SETTINGS", "ABOUT", "HELP", "LOGS", "ONLINE")
        if not config.MUSIC_MENUS_ONLY:
            menu_states = menu_states + ("TITLE", "PLAYING")
        audio.set_sfx_duck(1.0)
        if self.state in menu_states:
            audio.set_music_level(config.MUSIC_VOLUME)
            audio.start_logs_music()
        else:
            audio.fade_logs_music(500)

    def _draw_fade(self):
        if self.fade["active"] and self.fade["alpha"] > 0:
            overlay = self._black_overlay(*self.screen.get_size())
            overlay.set_alpha(max(0, min(255, int(self.fade["alpha"]))))
            self.screen.blit(overlay, (0, 0))
            overlay.set_alpha(255)

    # --- badges --------------------------------------------------------------
    def _maybe_award(self, badge_id):
        if persistence.award_badge(badge_id):
            self.badge_toast_id = badge_id
            self.badge_toast_at = self.now

    # --- action handler ------------------------------------------------------
    def handle_step_action(self, action, step):
        if action == "save_color":
            self.game_state["fav_color"] = step["opts"][self.selected_answer].lower()
            persistence.save_game_state(self.game_state)
        elif action == "start_webcam":
            if not ui.webcam_active:
                ui.start_webcam_nonblocking()
        elif action == "desktop_check":
            self.captured_window_title = os_layer.get_foreground_window_title()
            os_layer.move_window_right(0.8)

            def _restore_desktop():
                time.sleep(4)
                os_layer.move_window_center(0.8)

            threading.Thread(target=_restore_desktop, daemon=True).start()
        elif action == "r3_intro_shake":
            os_layer.shake_game_window(cycles=5, amplitude=15)
            audio.play_deep_rumble()
        elif action == "r3_window_shake":
            os_layer.shake_game_window(cycles=8, amplitude=22)
            audio.play_static_scream()
        elif action == "r3_open_webcam":
            ui.start_webcam_nonblocking()
        elif action == "final_exit":
            self._advance_run()
            return "EXIT"
        elif action == "final_exit_sleep":
            self._advance_run()
            threading.Thread(target=os_layer.put_computer_to_sleep, daemon=True).start()
            return "EXIT"
        elif action == "r3_final_end":
            self.game_state["run_count"] = 99
            self.game_state["_ended"] = True
            persistence.save_game_state(self.game_state)
            self._maybe_award("the_final_eye")
            audio.play_reverse_chord()
            return "EXIT"
        return None

    def _advance_run(self):
        if self.run_count < 4:
            self.run_count += 1
            self.game_state["run_count"] = self.run_count
        self.game_state["last_close_time"] = self.now
        persistence.save_game_state(self.game_state)

    def _confirm_answer(self):
        step = self.active_script[self.current_step]
        if step.get("type") == "wait":
            result = self.handle_step_action(step.get("action"), step)
            if result == "EXIT":
                self.pending_exit = True
                self.exit_message_at = self.now
            self.current_step += 1
            self._reset_question_state()
            return
        elapsed = self.now - self.question_start_time
        answer = step["opts"][self.selected_answer]
        # Little window shuffle on committing to an answer (Windows/macOS).
        os_layer.nudge_window()
        self.session_history.append({"q": step["q"], "a": answer})
        self._remember_asked(step["q"])
        persistence.save_answer(self.game_state, step["_id"], answer, elapsed)
        self._note_answer_meta(step, answer, elapsed)
        # The eye is watching how you answer. It keeps its own tally.
        self._eye_react_to_answer(answer, elapsed)
        # A hand-written question gets its answer reported back to its author.
        social_item = step.get("_social")
        if social_item:
            self._report_social_answer(social_item, answer)
        result = self.handle_step_action(step.get("action"), step)
        scare = step.get("scare")
        if scare and scare in self._used_scares:
            # The model can pick the same effect twice; the player should not
            # see the same trick twice in one session. Authored beats are also
            # checked, but they are written to avoid this by design.
            scare = None
        if scare:
            # The photosensitivity switches and the low-performance mode are
            # applied inside apply_scare, so every effect that reaches the
            # player goes through the same policy.
            if scares.apply_scare(self, scare):
                self._scares_fired += 1
            # Remember it so the AI never fires the same effect twice in a run.
            self._used_scares.add(scare)
        self._enforce_scare_floor()
        if result == "EXIT":
            self.pending_exit = True
            self.exit_message_at = self.now
            return
        # Runtime-injected questions (Classic bite): dynamic extras first, then
        # rebuttals / hesitation / tailored reactions.
        injected = list(step.get("_extra_steps") or [])
        injected += interjections.after_answer(step, answer, elapsed, self.game_state, self.run_count)
        for offset, extra in enumerate(injected):
            self.active_script.insert(self.current_step + 1 + offset, extra)
        self.current_step += 1
        self._skip_inactive()
        # A question someone sent us takes the next slot, ahead of the model.
        if not self._queue_social_question():
            self._prefetch_question(self.current_step)
        self._reset_question_state()
        if self.fx["whisper_until"] <= self.now:
            self._maybe_false_memory()

    def _note_answer_meta(self, step, answer, elapsed):
        """Post-answer bookkeeping Classic kept in save_answer(): hesitation
        counting, the patient_one badge, and contradiction (lie) detection."""
        if elapsed > config.HESITATION_THRESHOLD:
            persistence.record_hesitation(self.game_state)
        if elapsed >= config.PATIENT_ONE_THRESHOLD:
            self._maybe_award("patient_one")
        prev_id = step.get("_contradiction_check")
        if config.ENABLE_CONTRADICTIONS and prev_id:
            prev = self.game_state.get("answers", {}).get(prev_id)
            if prev is not None and answer != prev:
                persistence.record_lie(self.game_state, step["_id"])

    # --- input ---------------------------------------------------------------
    def _bound_key(self, action, default):
        """The key bound to an action, or the default if it is not bound.

        The rebinds live in the save file, so they survive a restart. A name
        the running pygame does not know falls back to the default rather than
        breaking the key handler.
        """
        try:
            s = self.game_state.get("settings", {}) or {}
            kb = s.get("keybinds", {}) or {}
            name = kb.get(action)
            if not name:
                return default
            return pygame.key.key_code(name)
        except Exception:
            return default

    def _handle_key(self, key, unicode=""):
        # Android's system Back key/gesture arrives as K_AC_BACK — map it to
        # ESC so every "leave this screen" path works on a phone.
        if key == getattr(pygame, "K_AC_BACK", None):
            key = pygame.K_ESCAPE
        if self.state == "TITLE":
            self._title_key(key)
        elif self.state == "ONLINE":
            self._online_key(key, unicode)
        elif self.state == "SETTINGS":
            self._settings_key(key)
        elif self.state == "ABOUT":
            self._about_key(key)
        elif self.state == "HELP":
            if key == pygame.K_ESCAPE or key == pygame.K_RETURN:
                audio.play_ui_select_sound()
                self.start_fade("TITLE")
        elif self.state == "LOGS":
            if key == pygame.K_ESCAPE:
                audio.fade_logs_music(400)
                audio.play_ui_select_sound()
                self.start_fade("TITLE")
        elif self.state in ("PLAYING", "EXITFADE"):
            if key == self._bound_key("back", pygame.K_ESCAPE):
                if not getattr(self, "paused", False):
                    self.paused = True
                    self.pause_selected = 0
                    audio.play_ui_nav_sound()
                    return
            if getattr(self, "paused", False):
                self._pause_key(key)
                return
            self._playing_key(key)

    def _title_key(self, key):
        self._check_cheat(key)
        # U opens the download page, but only while an update is actually on
        # offer; otherwise it stays an ordinary unused key.
        if key == pygame.K_u and self.update_available:
            self._open_update_page()
            return
        up = self._bound_key("up", pygame.K_UP)
        down = self._bound_key("down", pygame.K_DOWN)
        confirm = self._bound_key("confirm", pygame.K_RETURN)
        if key == pygame.K_TAB or key == down or key == up:
            n = len(self.menu_options)
            step = 1 if (key == down or key == pygame.K_TAB) else -1
            if key == up:
                step = -1
            self.selected_option = (self.selected_option + step) % n
            audio.play_ui_nav_sound()
        elif key == confirm:
            audio.play_ui_select_sound()
            option = self.menu_options[self.selected_option]
            if option == "PLAY":
                self.start_fade("PLAYING")
            elif option == "SETTINGS":
                self.settings_category_selected = 0
                self.settings_options = self.settings_options_by_category[self.settings_categories[self.settings_category_selected]]
                self.settings_selected = 0
                self.settings_idx = self._load_settings_idx()
                self._apply_settings()
                self.start_fade("SETTINGS")
            elif option == "HELP":
                self.start_fade("HELP")
            elif option == "ONLINE":
                self.start_fade("ONLINE")
            elif option == "ABOUT":
                self.about_selected = 0
                self.start_fade("ABOUT")
            elif option == "LOGS":
                self.start_fade("LOGS")
            elif option == "EXIT":
                # EXIT is a real exit: it stops the loop cleanly. (The window's
                # close button is still the thing it fights you over.)
                self.running = False
        elif key == pygame.K_ESCAPE:
            self._resist_close()

    def _check_cheat(self, key):
        if key in self._CHEAT_CODE:
            if self.now - self._cheat_last > 1.2:
                self._cheat_buffer = []
            self._cheat_buffer.append(key)
            self._cheat_last = self.now
            if self._cheat_buffer == self._CHEAT_CODE:
                self.game_state["logs_unlocked"] = True
                persistence.save_game_state(self.game_state)
                if "LOGS" not in self.menu_options:
                    self.menu_options.insert(len(self.menu_options) - 1, "LOGS")
                    self._maybe_award("the_archivist")
                self._cheat_buffer = []
                audio.play_glitch_sound()
        elif key not in (pygame.K_TAB, pygame.K_RETURN, pygame.K_ESCAPE, pygame.K_UP, pygame.K_DOWN):
            self._cheat_buffer = []

    def _settings_key(self, key):
        if getattr(self, "rebinding", None):
            s = self.game_state.setdefault("settings", {})
            kb = s.setdefault("keybinds", {})
            keyname = pygame.key.name(key).upper()
            # Avoid setting to modifiers in weird states, but just store
            mapping = {
                "Rebind: Up": "up",
                "Rebind: Down": "down",
                "Rebind: Confirm": "confirm",
                "Rebind: Back/Pause": "back",
            }
            action = mapping.get(self.rebinding)
            if action:
                # A key can only drive one action. Reject the clash instead of
                # letting it shadow the other binding.
                clash = None
                for other_action, other_key in kb.items():
                    if other_action == action:
                        continue
                    if other_action == "pause" and action == "back":
                        continue    # back and pause are one action
                    if other_action == "back" and action == "pause":
                        continue
                    if other_key == keyname:
                        clash = other_action
                        break
                if clash:
                    self.rebind_error = "%s IS ALREADY BOUND" % keyname
                    self.rebind_error_until = self.now + 3.0
                    self.rebinding = None
                    audio.play_ui_nav_sound()
                    return
                kb[action] = keyname
                if action == "back":
                    kb["pause"] = keyname
                s["keybinds"] = kb
                persistence.save_game_state(self.game_state)
                self.rebind_error = ""
            self.rebinding = None
            audio.play_ui_select_sound()
            return
        n = len(self.settings_options)
        # Navigation honours the rebinds. The change key and the back key stay
        # on ENTER and ESC here as well, so the player can never rebind
        # themselves out of the screen they rebind in.
        up = self._bound_key("up", pygame.K_UP)
        down = self._bound_key("down", pygame.K_DOWN)
        if key == pygame.K_TAB:
            self.settings_category_selected = (self.settings_category_selected + 1) % len(self.settings_categories)
            cat = self.settings_categories[self.settings_category_selected]
            self.settings_options = self.settings_options_by_category[cat]
            self.settings_selected = 0
            audio.play_ui_nav_sound()
            return
        if key == pygame.K_LEFT:
            self.settings_category_selected = (self.settings_category_selected - 1) % len(self.settings_categories)
            cat = self.settings_categories[self.settings_category_selected]
            self.settings_options = self.settings_options_by_category[cat]
            self.settings_selected = 0
            audio.play_ui_nav_sound()
            return
        if key == pygame.K_RIGHT:
            self.settings_category_selected = (self.settings_category_selected + 1) % len(self.settings_categories)
            cat = self.settings_categories[self.settings_category_selected]
            self.settings_options = self.settings_options_by_category[cat]
            self.settings_selected = 0
            audio.play_ui_nav_sound()
            return
        if key == up or key == down:
            step = 1 if key == down else -1
            self.settings_selected = (self.settings_selected + step) % len(self.settings_options)
            audio.play_ui_nav_sound()
        elif key == pygame.K_RETURN or key == self._bound_key("confirm", pygame.K_RETURN):
            name = self.settings_options[self.settings_selected]
            if name == "< Back":
                audio.play_ui_select_sound()
                self.start_fade("TITLE")
            elif name == "Reset All Data":
                self.game_state = persistence.reset_all_data()
                self.run_count = 1
                self.settings_idx = dict(config.SETTING_DEFAULTS)
                self.settings_idx = self._load_settings_idx()
                self._apply_settings()
                audio.play_error_sound()
            elif name.startswith("Rebind:"):
                self.rebinding = name
                audio.play_ui_nav_sound()
            else:
                opts = config.SETTING_OPTIONS.get(name)
                if not opts:
                    return
                self.settings_idx[name] = (self.settings_idx.get(name, 0) + 1) % len(opts)
                self._apply_settings()
                audio.play_ui_select_sound()
        elif key == pygame.K_ESCAPE:
            if getattr(self, "rebinding", None):
                self.rebinding = None
                audio.play_ui_nav_sound()
                return
            self.start_fade("TITLE")

    def _about_key(self, key):
        if key == pygame.K_UP or key == pygame.K_DOWN or key == pygame.K_TAB:
            step = 1 if (key == pygame.K_DOWN or key == pygame.K_TAB) else -1
            if key == pygame.K_UP:
                step = -1
            self.about_selected = (self.about_selected + step) % 3
            audio.play_ui_nav_sound()
        elif key == pygame.K_RETURN:
            if self.about_selected == 2:
                audio.play_ui_select_sound()
                self.start_fade("TITLE")
        elif key == pygame.K_ESCAPE:
            self.start_fade("TITLE")

    def _pause_key(self, key):
        up = self._bound_key("up", pygame.K_UP)
        down = self._bound_key("down", pygame.K_DOWN)
        confirm = self._bound_key("confirm", pygame.K_RETURN)
        if key == pygame.K_TAB or key == up or key == down:
            delta = 1 if key == down or key == pygame.K_TAB else -1
            if key == up:
                delta = -1
            self.pause_selected = (self.pause_selected + delta) % len(self.pause_options)
            audio.play_ui_nav_sound()
            return
        if key == confirm:
            choice = self.pause_options[self.pause_selected]
            audio.play_ui_select_sound()
            if choice == "RESUME":
                self.paused = False
                return
            if choice == "SETTINGS":
                self.paused = False
                self.settings_category_selected = 0
                self.settings_options = self.settings_options_by_category[self.settings_categories[self.settings_category_selected]]
                self.settings_selected = 0
                self.settings_idx = self._load_settings_idx()
                self._apply_settings()
                self.start_fade("SETTINGS")
                return
            if choice == "MAIN MENU":
                self.paused = False
                self.pending_exit = True
                self.exit_message_at = self.now
                return
            if choice == "EXIT":
                self.paused = False
                self.running = False
                return
        if key == pygame.K_ESCAPE:
            self.paused = False
            audio.play_ui_nav_sound()

    def _playing_key(self, key):
        if self.pending_exit:
            return
        step = self.active_script[self.current_step]
        if step.get("type") == "wait":
            return
        if self.typing_state != "WAITING":
            return
        up = self._bound_key("up", pygame.K_UP)
        down = self._bound_key("down", pygame.K_DOWN)
        confirm = self._bound_key("confirm", pygame.K_RETURN)
        if key == pygame.K_TAB or key == up or key == down:
            delta = 1 if (key == down or key == pygame.K_TAB) else -1
            if key == up:
                delta = -1
            opts = step["opts"]
            self.selected_answer = (self.selected_answer + delta) % len(opts)
            audio.play_ui_nav_sound()
        elif key == confirm:
            audio.play_ui_select_sound()
            self._confirm_answer()

    # --- touch input (Android) ------------------------------------------------
    def _touch_zone(self, x, y, w, h, kind, idx=0):
        """Record a tappable rectangle for this frame's layout.

        Zones are rebuilt every draw pass, so the hit boxes always match what
        is actually on screen — including the squeeze logic that lifts a long
        answer block up from the bottom edge.
        """
        if w <= 0 or h <= 0:
            return
        self._touch_zones.append((pygame.Rect(int(x), int(y), int(w), int(h)), kind, idx))

    def _handle_touch(self, px, py):
        """A finger went down: hit-test this frame's zones and run the action
        the equivalent key would have run.

        Options are tapped *directly* rather than TAB-cycled — on a phone,
        "tap the line you want" is the only comfortable way to play a menu
        game. Taps are ignored mid-transition (fade) and during LOADING so a
        stray double-tap can't fire twice.
        """
        if self.fade["active"] or self.state == "LOADING":
            return
        for rect, kind, idx in self._touch_zones:
            if rect.collidepoint(int(px), int(py)):
                try:
                    self._touch_action(kind, idx)
                except Exception:
                    pass  # a stray tap must never take the game down
                return

    def _touch_action(self, kind, idx):
        if kind == "title":
            self.selected_option = idx
            self._handle_key(pygame.K_RETURN)
        elif kind == "settings":
            self.settings_selected = idx
            self._handle_key(pygame.K_RETURN)
        elif kind == "about":
            self.about_selected = idx
            self._handle_key(pygame.K_RETURN)
        elif kind == "answer":
            # Always preselect the tapped line; the key handler only confirms
            # once the question has finished typing (and ignores wait steps).
            if self.current_step >= len(self.active_script):
                return
            self.selected_answer = idx
            self._handle_key(pygame.K_RETURN)
        elif kind == "back":
            self._handle_key(pygame.K_ESCAPE)
        elif kind == "update":
            self._open_update_page()
        elif kind == "online":
            # The ONLINE screen has two real options now; a tap runs the
            # one that was tapped, exactly like the key would.
            self._online_activate(idx)

    # --- update ---------------------------------------------------------------
    def _update(self):
        self.now = time.time()
        self._update_fade()
        self._update_idle()
        self._update_process_awareness()
        self._poll_social()
        self._poll_update_check()
        self._supervise_overlay()
        if self.state in ("PLAYING", "EXITFADE") and not self.pending_exit:
            self._update_playing()
            self._maybe_comment_on_apps()
            self._update_background_interference()

    def _supervise_overlay(self):
        """Keep the desktop eye alive while the game is not the foreground
        window. If the overlay process dies (or the player kills it) it is
        quietly brought back, with a backoff so a hard failure cannot spin."""
        ov = getattr(self, "_overlay", None)
        if ov is None:
            return
        if getattr(self, "_window_focused", True):
            return
        if ov.supported and not ov.running:
            self._overlay_retry_at = getattr(self, "_overlay_retry_at", 0.0)
            if self.now >= self._overlay_retry_at:
                self._overlay_retry_at = self.now + 5.0
                try:
                    ov.start()
                except Exception:
                    pass

    def _update_process_awareness(self):
        """It watches you open the Task Manager. Twice per second, no polls
        from the render loop — reads the cache os_layer fills in the background."""
        if not (config.ENABLE_TASKMGR_DETECT or config.ENABLE_DISCORD_DETECT):
            return
        if self.state not in ("PLAYING", "EXITFADE"):
            return
        if self.now - self._proc_check_at < 0.5:
            return
        self._proc_check_at = self.now
        procs = os_layer.get_cached_processes()
        if config.ENABLE_TASKMGR_DETECT and procs.get("taskmgr"):
            if not self.game_state.get("taskmgr_seen"):
                self.game_state["taskmgr_seen"] = True
                persistence.save_game_state(self.game_state)
                self._maybe_award("task_manager")
                self._say_aggressive('"The Task Manager will not help you."', duration=4.0)
                self.fx["corrupt_until"] = max(self.fx["corrupt_until"], self.now + 1.5)
                audio.play_glitch_sound()
                # Classic also threw a question at you, not just a whisper.
                if self.state == "PLAYING":
                    self.active_script.insert(
                        self.current_step + 1,
                        interjections.build_taskmgr_comment(self.current_step),
                    )
        if config.ENABLE_DISCORD_DETECT and procs.get("discord"):
            self._maybe_award("not_alone")

    def _update_background_interference(self):
        """Classic's low-level ambient: a cmd flash every ~30s and a random
        error beep, so the machine never feels fully at rest."""
        if not config.ENABLE_BACKGROUND_INTERFERENCE:
            return
        if self.state not in ("PLAYING", "EXITFADE") or self.pending_exit:
            return
        if self.now - self._last_cmd_time > config.BACKGROUND_INTERFERENCE_INTERVAL:
            self._last_cmd_time = self.now
            os_layer.flash_cmd()
        if self.now > self._next_beep_time:
            self._next_beep_time = self.now + random.uniform(*config.BACKGROUND_BEEP_INTERVAL)
            audio.play_error_sound()

    def _maybe_comment_on_apps(self):
        """One-shot beat: it names a program it can see running (run 2+)."""
        if self._app_comment_done or self.run_count < 2:
            return
        if self.now - self._start_time < 12.0:
            return
        self._app_comment_done = True
        comment = os_layer.comment_on_open_apps()
        if comment:
            self.fx["whisper_text"] = '"' + comment.replace("\n", " ") + '"'
            self.fx["whisper_until"] = self.now + 5.0
            audio.play_mechanical_beep()

    def _maybe_false_memory(self):
        """Classic beat: it misquotes an answer you actually gave."""
        # Once per save, Classic threw this as a real question with rebuttals.
        if (not self.game_state.get("false_memory_used")
                and len(self.session_history) >= 4 and random.random() < 0.15):
            self.game_state["false_memory_used"] = True
            persistence.save_game_state(self.game_state)
            self.active_script.insert(self.current_step, interjections.build_false_memory())
            audio.play_glitch_sound()
            return
        history = self.session_history
        if len(history) < 2 or random.random() > 0.18:
            return
        h = random.choice(history[:-1])
        line = 'You said "%s." You said it twice.' % h["a"]
        self._say_aggressive('"' + line + '"', duration=4.5)
        audio.play_glitch_sound()

    def _update_idle(self):
        if self.state in ("PLAYING", "EXITFADE"):
            focused = pygame.key.get_focused()
            if self.idle_tracker["focused"] and not focused:
                self.idle_tracker["focused"] = False
                self.idle_tracker["lost_at"] = self.now
            elif not self.idle_tracker["focused"] and focused:
                self.idle_tracker["focused"] = True
                away = self.now - self.idle_tracker["lost_at"]
                if away > 4.0:
                    self.idle_tracker["last_away"] = away
                    self.idle_tracker["pending"] = True
        if self.idle_tracker.get("pending"):
            self.idle_tracker["pending"] = False
            away = self.idle_tracker["last_away"]
            self._say_aggressive(random.choice([
                '"You were gone %d seconds. Where."' % int(away),
                '"Do not leave it waiting again."',
                '"We counted every second of the %d."' % int(away),
            ]), duration=4.5)
            audio.play_glitch_sound()
            self.fx["corrupt_until"] = max(self.fx["corrupt_until"], self.now + 0.8)

    def _update_playing(self):
        if self.current_step >= len(self.active_script):
            self.pending_exit = True
            return
        step = self.active_script[self.current_step]
        if step.get("type") == "wait":
            if self.wait_start_time == 0:
                self.wait_start_time = self.now
            if self.now - self.wait_start_time >= step.get("time", 4):
                self._confirm_answer()
            return
        if step.get("q") is None:
            # AI placeholder still generating — THINKING dots hold the line.
            self._prefetch_question(self.current_step)
            self.typing_state = "THINKING"
            return
        if not step.get("_seen"):
            # Question just landed after a fetch — give it a real "thinking" beat
            # so fast network responses don't skip the THINKING phase.
            step["_seen"] = True
            # Every new question, the window jumps to a fresh spot near centre
            # (Windows/macOS; a no-op where the OS forbids self-positioning).
            os_layer.move_window_near_center()
            if step.get("_contradiction_check") and config.ENABLE_CONTRADICTIONS:
                step = interjections.contradiction_rephrase(step, self.game_state)
                step["_seen"] = True
                self.active_script[self.current_step] = step
            self.thinking_timer = self.now
            self.typing_state = "THINKING"
        text = step["q"]
        # Prefetch the *next* step only when it does not depend on this answer
        # (machine-state beats). Prefetching an AI question here meant the model
        # was asked before the player had answered, so it always ran ~2 questions
        # behind and never saw the latest answer — the exact bug behind "the
        # answer isn't sent back to the AI".
        nxt_index = self.current_step + 1
        if nxt_index < len(self.active_script):
            nxt = self.active_script[nxt_index]
            if nxt.get("type") == "dynamic_pending" or config.AI_PREFETCH_LOOKAHEAD:
                self._prefetch_question(nxt_index)
        if self.typing_state == "THINKING":
            if self.now - self.thinking_timer > 0.9:
                self.typing_state = "TYPING"
                self.last_type_time = 0
        elif self.typing_state == "TYPING":
            interval = max(0.006, self.game_state.get("settings", {}).get("text_speed", 0.04))
            if self.now - self.last_type_time > interval:
                self.last_type_time = self.now
                self.typing_index += 1
                audio.play_type_sound()
                if self.typing_index >= len(text):
                    self.typing_state = "WAITING"
        elif self.typing_state == "WAITING":
            if self.run_count >= 3:
                self._run3_low_grade_glitch()

    def _run3_low_grade_glitch(self):
        """Run 3 never settles: a slow trickle of tiny corruptions/flickers."""
        if self.now < getattr(self, "_next_r3_glitch", 0.0):
            return
        self._next_r3_glitch = self.now + random.uniform(4.0, 9.0)
        if random.random() < 0.5:
            self.fx["corrupt_until"] = max(self.fx["corrupt_until"], self.now + 0.7)
        elif random.random() < 0.5:
            self.fx["rgb_split_until"] = max(self.fx["rgb_split_until"], self.now + 0.6)
        else:
            self.fx["flicker_until"] = max(self.fx["flicker_until"], self.now + 0.5)
        audio.play_glitch_sound()

    # --- drawing --------------------------------------------------------------
    def _fonts(self):
        """Cached fonts — pygame.font.Font() construction was the single
        biggest per-frame cost (3 objects × 4-6 calls/frame). Rebuild only
        when the window size or text-size setting changes."""
        key = (self.screen.get_width(), self.screen.get_height(),
               self.game_state.get("settings", {}).get("text_size", 1.0))
        if self._font_cache_key != key:
            self._font_cache = ui.get_scaled_fonts(self.game_state, key[0], key[1])
            self._font_cache_key = key
        return self._font_cache

    def _black_overlay(self, w, h):
        """Reusable full-screen black overlay (fades + exits)."""
        if self._black_overlay_key != (w, h):
            self._black_overlay_cache = pygame.Surface((w, h))
            self._black_overlay_cache.fill((0, 0, 0))
            self._black_overlay_key = (w, h)
        return self._black_overlay_cache

    def _draw(self):
        # The window may have been resized since the last frame (the WM does
        # not always wait for our event). Make sure the frame still matches it
        # before anything is drawn, or the copy at the end lands on a surface
        # of a different size and the window goes black.
        self._sync_frame()
        self.screen.fill(config.COLOR_BLACK)
        w, h = self.screen.get_size()
        self._touch_zones = []   # rebuilt below; hit-tested by _handle_touch

        if self.state in ("PLAYING", "EXITFADE"):
            # A violent shake fired alongside an aggressive line outranks the
            # ambient run-3 tremor, so the jolt is unmistakable.
            if self.fx.get("screen_shake_until", 0.0) > self.now:
                amp = int(self.fx.get("shake_amp", 16) or 16)
                self.shake_x = random.randint(-amp, amp)
                self.shake_y = random.randint(-amp, amp)
            elif self.run_count >= 3:
                self.shake_x, self.shake_y = random.randint(-8, 8), random.randint(-8, 8)
            else:
                self.shake_x, self.shake_y = 0, 0
        else:
            self.shake_x, self.shake_y = 0, 0

        # Background dressing goes down *before* the content so the text is
        # painted over it and stays crisp: rolling scan sweep, drifting ash,
        # breathing vignette, and the faint tape head line.
        sset = self.game_state.get("settings", {}) or {}
        vhs = sset.get("vhs_intensity", 1.0)
        perf = str(sset.get("performance_mode", "Medium")).lower()
        crt_enabled = bool(sset.get("crt_enabled", True)) and perf != "low"
        scanlines_enabled = bool(sset.get("scanlines_enabled", True)) and crt_enabled
        vignette_enabled = bool(sset.get("vignette_enabled", True))
        dust_enabled = bool(sset.get("dust_enabled", True)) and perf != "low"
        static_line_enabled = bool(sset.get("static_line_enabled", True)) and perf != "low"
        if vhs > 0 and scanlines_enabled:
            ui.draw_scan_sweep(self.screen, w, h, self.now)
        if dust_enabled:
            ui.draw_dust(self.screen, w, h, self.now)
        if vignette_enabled:
            ui.apply_vignette(self.screen, w, h, self.now, strong=self.run_count >= 3)
        if self.state in ("PLAYING", "EXITFADE") and config.VHS_STATIC_LINE > 0 and static_line_enabled:
            ui.draw_static_line(self.screen, w, h, self.now, config.VHS_STATIC_LINE)

        # Each screen declares the highlighted option while drawing, so the
        # eye can look at the real thing. Clear it first: a screen with no
        # selection must not inherit the previous state's target.
        self._eye_focus_rect = None
        if self.state == "LOADING":
            self._draw_loading(w, h)
        elif self.state == "TITLE":
            self._draw_title(w, h)
        elif self.state == "ONLINE":
            self._draw_online(w, h)
        elif self.state == "SETTINGS":
            self._draw_settings(w, h)
        elif self.state == "ABOUT":
            self._draw_about(w, h)
        elif self.state == "HELP":
            self._draw_help(w, h)
        elif self.state == "LOGS":
            self._draw_logs(w, h)
        elif self.state in ("PLAYING", "EXITFADE"):
            self._draw_playing(w, h)
        if self.state in ("PLAYING", "EXITFADE") and getattr(self, "paused", False):
            self._draw_pause(w, h)
        self._draw_watching_eye(w, h)

        self._draw_fade()
        if self.close_msg_until > self.now:
            font_small = self._fonts()[2]
            msg = os_layer.get_close_intercept_message(self.close_attempts).replace("\n", " ")
            surf = font_small.render(msg, True, config.COLOR_RED)
            self.screen.blit(surf, (w // 2 - surf.get_width() // 2, h - 50))

        if self.badge_toast_id and self.badge_toast_at:
            still = ui.draw_badge_toast(self.screen, w, h, self.badge_toast_id, self.badge_toast_at,
                                        self._fonts()[1], self._fonts()[2], self.now)
            if not still:
                self.badge_toast_id = None

        self._draw_social_notes(w, h)

        # Foreground CRT finish, applied over every state: VHS scanlines, then
        # the full stack (tracking, static, tube curvature, phosphor mask).
        # Last, so the tube look reads as being in front of the content.
        try:
            ui.apply_vhs_effects(self.screen, w, h, self.game_state)
        except Exception:
            pass
        if crt_enabled and vhs > 0:
            try:
                c_int = float(sset.get("crt_intensity", 1.0))
                ui.apply_vhs_pass(self.screen, w, h, self.now, intensity=vhs * c_int, game_state=self.game_state)
            except Exception:
                try:
                    ui.apply_vhs_pass(self.screen, w, h, self.now, intensity=vhs, game_state=self.game_state)
                except Exception:
                    ui.apply_vhs_pass(self.screen, w, h, self.now, intensity=vhs)

        # Present: the frame is the drawing target, the window is the real
        # surface. They are normally identical in size, so this is a straight
        # copy; the scale path only runs if the two ever drift apart. The
        # window surface is fetched fresh — pygame swaps the object when the
        # window manager resizes the window.
        disp = self._display_surface()
        if disp is not None:
            self._make_window_opaque(disp)
            if disp.get_size() == self._frame.get_size():
                disp.blit(self._frame, (0, 0))
            else:
                # Scale into a surface with the frame's own (alpha-free)
                # format and copy that over: scaling straight into the
                # window surface would hand it a fresh, transparent alpha
                # channel and the window would go invisible again.
                scaled = pygame.transform.smoothscale(self._frame, disp.get_size())
                disp.blit(scaled, (0, 0))
        pygame.display.flip()

    def _draw_loading(self, w, h):
        font_large, font_med, font_small = self._fonts()
        t = self.now - self.loading_start
        title = font_large.render(_TITLE, True, config.COLOR_RED)
        sub = font_med.render(_TITLE_SUB, True, (150, 0, 0))
        dots = "..." if t < 0.4 else ("...." if t < 0.8 else ".....")
        cal = font_small.render("CALIBRATING" + dots, True, (90, 90, 90))
        self.screen.blit(title, (w // 2 - title.get_width() // 2, h // 2 - 90))
        self.screen.blit(sub, (w // 2 - sub.get_width() // 2, h // 2 - 40))
        self.screen.blit(cal, (w // 2 - cal.get_width() // 2, h // 2 + 30))
        if t > 1.6:
            self.state = "TITLE"
            self._on_state_enter()

    def _draw_title(self, w, h):
        font_large, font_med, font_small = self._fonts()
        ui.draw_starfield(self.screen, w, h, self.now, self.starfield)
        ui.draw_menu_decorations(self.screen, w, h, self.now, font_small)

        title_color = config.COLOR_WHITE
        if self.run_count >= 3:
            title_color = config.COLOR_RED if random.random() < 0.2 else config.COLOR_DARK_RED
            if random.random() < 0.05:
                ui.render_animated_wrapped_text(self.screen, "THIS IS YOUR LAST CHANCE", font_small,
                                                config.COLOR_RED, 20, 20, 300, self.now)

        title_lines = ["THE", "QUESTION", "GAME"]
        if self.run_count == 2:
            title_lines = ["....", "...", "Leave."]

        base_y = int(h * 0.10)
        # Occasional character scramble, straight from the website's title.
        scramble_on = (self.now % 7.0) < 0.45
        for i, line in enumerate(title_lines):
            sway_x = int(math.sin(self.now * 1.8 + i) * 6)
            sway_y = int(math.cos(self.now * 1.2 + i) * 3)
            draw_line = ui.scramble_text(line, self.now, 0.35) if scramble_on else line
            ui.draw_glowing_text(self.screen, draw_line, font_large,
                                 int(w * 0.08) + sway_x, base_y + i * 65 + sway_y,
                                 self.now, color=title_color, glow_color=(150, 0, 0))
            # Website hero: red/cyan split copies jittering over the base.
            ui.render_glitch_text(self.screen, draw_line, font_large,
                                  int(w * 0.08) + sway_x, base_y + i * 65 + sway_y,
                                  self.now, color=title_color)

        sub = font_med.render(_TITLE_SUB, True, (150, 0, 0))
        self.screen.blit(sub, (int(w * 0.08), base_y + 3 * 65 + 8))

        run_label = font_small.render("SESSION %d / 3" % self.run_count, True, (120, 40, 40))
        self.screen.blit(run_label, (int(w * 0.08), base_y + 3 * 65 + 8 + font_med.get_height() + 6))

        menu_y_start = h - 310 if len(self.menu_options) <= 5 else h - 348
        for i, option in enumerate(self.menu_options):
            sel = (i == self.selected_option)
            base_col = config.COLOR_GREEN if sel else config.COLOR_WHITE
            if self.run_count >= 3 and sel:
                base_col = config.COLOR_RED
            pulse = 0.75 + 0.25 * math.sin(self.now * 2.0 + i * 0.6)
            alpha = int(180 + 75 * pulse)
            if sel:
                p2 = 0.5 + 0.5 * math.sin(self.now * 4.0 + i * 0.6)
                base_col = tuple(min(255, int(c * (0.7 + 0.5 * p2))) for c in base_col)
            prefix = f"> {option}" if sel else f"  {option}"
            if sel:
                ui.render_glitch_text(self.screen, prefix, font_med,
                                      int(w * 0.08), menu_y_start + i * 45,
                                      self.now, color=base_col)
                tw, th = font_med.size(prefix)
                self._eye_focus_rect = (int(w * 0.08), menu_y_start + i * 45,
                                        max(1, tw), max(1, th))
            else:
                surf = font_med.render(prefix, True, base_col)
                try:
                    surf.set_alpha(alpha)
                except Exception:
                    pass
                self.screen.blit(surf, (int(w * 0.08), menu_y_start + i * 45))
            self._touch_zone(int(w * 0.08) - 8, menu_y_start + i * 45,
                             int(w * 0.6) + 16, 44, "title", i)

        if self.update_available:
            version = str(self.update_available.get("version") or "?")
            label = ("UPDATE %s AVAILABLE — TAP TO DOWNLOAD" % version
                     if IS_ANDROID
                     else "UPDATE %s AVAILABLE — [U] DOWNLOAD" % version)
            update_surf = font_small.render(label, True, (210, 185, 80))
            ux = w // 2 - update_surf.get_width() // 2
            uy = h - 50
            self.screen.blit(update_surf, (ux, uy))
            self._touch_zone(ux - 8, uy - 4, update_surf.get_width() + 16,
                             update_surf.get_height() + 8, "update")

        cred = font_small.render("NEPTUNE PRODUCTIONS (C)", True, (60, 60, 60))
        self.screen.blit(cred, (w // 2 - cred.get_width() // 2, h - 28))

        ver = font_small.render("v" + config.VERSION, True, (60, 60, 60))
        # Top-right: the bottom-right corner belongs to the eye now.
        self.screen.blit(ver, (w - ver.get_width() - 12, 8))

    # --- online screens -----------------------------------------------------
    def _draw_notes_toast(self, w, h, font_med, font_small, limit=2):
        """The most recent notices, stacked above the badge toast slot."""
        live = [n for n in self.social_notes
                if self.now - n["at"] < n.get("_ttl", 6.0)]
        if not live:
            return
        for i, note in enumerate(live[-limit:]):
            ui.draw_social_toast(self.screen, w, h, note["text"], note["at"],
                                 font_med, font_small, self.now,
                                 tone=note.get("tone", "info"), slot=i)

    def _draw_social_notes(self, w, h):
        if not self.social_notes:
            return
        font_med, font_small = self._fonts()[1], self._fonts()[2]
        self._draw_notes_toast(w, h, font_med, font_small)
        # Retire anything long past its life so the list cannot grow.
        self.social_notes = [n for n in self.social_notes
                             if self.now - n["at"] < n.get("_ttl", 6.0) + 2.0]

    def _draw_online(self, w, h):
        """The ONLINE entry: the room this session has joined.

        This release is single-player plus questions *received* from the
        operator — writing them lives in a separate sender app. So this screen
        shows the room from the receiving side: the relay's state, who else is
        playing, the name the others see you under, a connection test, and a
        plain explanation of what the room actually is.
        """
        font_large, font_med, font_small = self._fonts()
        font_tiny = ui.get_tiny_font(self.game_state, w, h)
        self._draw_heading("ONLINE", w, h, font_large)
        cx = int(w * 0.08)
        hint_y = h - 42

        # The explanation is anchored to the bottom, so the room list above it
        # can grow into whatever space is left.
        explain_lines = len(ONLINE_EXPLAINER) + len(ONLINE_LOBBY_BLURB) + 1
        explain_top = hint_y - explain_lines * font_tiny.get_linesize() - 10

        y = int(h * 0.20)

        # This half of the game is brand new. Say so before anything else —
        # next to the heading, so it costs no vertical space.
        warn_x = cx + font_large.size("ONLINE")[0] + 34
        self.screen.blit(font_small.render(
            "AN ALPHA. IT WILL BREAK A LOT.",
            True, (215, 160, 60)), (warn_x, int(h * 0.08) + font_large.get_height() // 2))

        status, others = self._online_status()
        if status == "online":
            relay_txt, relay_col = "RELAY: ONLINE", (90, 200, 90)
        elif status == "reconnecting":
            relay_txt, relay_col = "RELAY: RECONNECTING...", (200, 180, 90)
        elif status == "connecting":
            relay_txt, relay_col = "RELAY: CONNECTING...", (200, 180, 90)
        elif status == "disabled":
            relay_txt, relay_col = "MULTIPLAYER IS OFF", (170, 170, 170)
        else:
            relay_txt, relay_col = "RELAY: OFFLINE", (200, 80, 80)
        self.screen.blit(font_med.render(relay_txt, True, relay_col), (cx, y))
        # After a drop that recovered, say so — a silent reconnect looks like a
        # freeze, and this screen is where the player comes to check.
        try:
            reconnects = self.social.reconnects() if self.social else 0
        except Exception:
            reconnects = 0
        if reconnects and status == "online":
            self.screen.blit(font_small.render(
                "RECONNECTED x%d" % reconnects, True, (90, 160, 90)),
                (cx + font_med.size(relay_txt)[0] + 26, y + 10))

        # The name the room knows you by, on the same line.
        if self.online_edit is not None:
            value = self.online_edit["text"] + "_"
            hint = "[ENTER] SAVE  [ESC] CANCEL"
        else:
            value = str(self._social_name()).upper()
            hint = "[N] RENAME"
        name_x = cx + font_med.size(relay_txt)[0] + 26
        self.screen.blit(font_small.render("YOU", True, (110, 110, 110)),
                         (name_x, y + 10))
        self.screen.blit(font_med.render(value, True, (205, 205, 205)),
                         (name_x + 46, y))
        self.screen.blit(font_small.render(hint, True, (80, 80, 80)),
                         (name_x + 46 + font_med.size(value)[0] + 14, y + 10))
        y += font_med.get_linesize() + 8

        # Who else is in the room.
        self.screen.blit(font_small.render(
            "IN THE ROOM NOW (%d)" % len(others), True, (100, 40, 40)), (cx, y))
        y += font_small.get_linesize() + 2

        # Reserve the room for the options and the test result, so the peer
        # list can never push into the explanation below it. The lobby teaser
        # also has to fit, so it is charged against the same budget.
        teaser_h = (len(ONLINE_LOBBY_TEASER) + 1) * font_small.get_linesize() + 8
        reserve = (len(self.online_options) + 1) * font_med.get_linesize() + teaser_h
        peer_slots = int((explain_top - y - reserve) // font_small.get_linesize())
        peer_slots = max(0, min(4, peer_slots))
        if not others:
            self.screen.blit(font_small.render(
                "NOBODY ELSE IS PLAYING RIGHT NOW", True, (80, 80, 80)), (cx, y))
            y += font_small.get_linesize() + 4
        else:
            for peer in others[:peer_slots]:
                pname = str(peer.get("name", "?")).upper()
                plat = str(peer.get("platform", "")).upper()
                self.screen.blit(font_small.render(
                    "%s   (%s)" % (pname, plat), True, (170, 170, 170)), (cx, y))
                y += font_small.get_linesize() + 2
            if len(others) > peer_slots:
                self.screen.blit(font_small.render(
                    "... AND %d MORE" % (len(others) - peer_slots), True,
                    (80, 80, 80)), (cx, y))
                y += font_small.get_linesize() + 2
            y += 4

        # Lobbies: not built, shown anyway. A quiet section that names the shape
        # of what is coming, clearly marked SOON, so nothing here reads as a
        # feature you can press. It is deliberately not focusable.
        self.screen.blit(font_small.render(
            "LOBBIES  —  COMING SOON", True, (100, 40, 40)), (cx, y))
        y += font_small.get_linesize() + 2
        for lobby_name, when in ONLINE_LOBBY_TEASER:
            self.screen.blit(font_small.render("  " + lobby_name, True,
                                               (70, 70, 70)), (cx, y))
            tag = str(when).upper()
            tx = cx + int(w * 0.30)
            self.screen.blit(font_small.render("[" + tag + "]", True,
                                               (60, 60, 60)), (tx, y))
            y += font_small.get_linesize() + 2
        y += 4

        # The options.
        for i, option in enumerate(self.online_options):
            sel = (i == self.online_selected)
            prefix = "> " if sel else "  "
            col = config.COLOR_WHITE if sel else (110, 110, 110)
            surf = font_med.render(prefix + option, True, col)
            self.screen.blit(surf, (cx, y))
            if sel:
                self._eye_focus_rect = (cx, y, max(1, surf.get_width()),
                                        max(1, surf.get_height()))
            self._touch_zone(cx - 8, y - 3, int(w * 0.6) + 16,
                             font_med.get_linesize() + 4, "online", i)
            y += font_med.get_linesize() + 2

        # The result of the connection test, if there is one.
        test = self.online_test or {}
        if test.get("state") == "running":
            self.screen.blit(font_small.render("TESTING...", True, (200, 180, 90)),
                             (cx, y))
        elif test.get("state") in ("ok", "fail"):
            col = (90, 200, 90) if test.get("state") == "ok" else (200, 80, 80)
            self.screen.blit(font_small.render(
                "CONNECTION: " + str(test.get("detail", "")).upper(), True, col),
                (cx, y))

        # What the room is, in the game's own voice.
        ey = explain_top
        self.screen.blit(font_tiny.render("HOW THIS WORKS", True, (120, 45, 45)),
                         (cx, ey))
        ey += font_tiny.get_linesize()
        for line in ONLINE_EXPLAINER:
            self.screen.blit(font_tiny.render(line, True, (140, 140, 140)),
                             (cx, ey))
            ey += font_tiny.get_linesize()
        for line in ONLINE_LOBBY_BLURB:
            self.screen.blit(font_tiny.render(line, True, (110, 90, 60)),
                             (cx, ey))
            ey += font_tiny.get_linesize()

        # Where the block ended: the smoke test uses it to prove the screen
        # still fits in the default window.
        self.online_layout_bottom = ey

        self.screen.blit(font_small.render(
            "[T] TEST CONNECTION   [N] RENAME   [UP/DOWN] MOVE   [ESC] BACK",
            True, (80, 80, 80)), (cx, hint_y))

    def _draw_heading(self, text, w, h, font_large, y_factor=0.08):
        """Section titles get the website's glow + red/cyan glitch split."""
        x, y = int(w * 0.08), int(h * y_factor)
        ui.draw_glowing_text(self.screen, text, font_large, x, y, self.now,
                             color=config.COLOR_RED, glow_color=(150, 0, 0))
        ui.render_glitch_text(self.screen, text, font_large, x, y, self.now,
                              color=config.COLOR_RED)

    def _draw_settings(self, w, h):
        font_large, font_med, font_small = self._fonts()
        self._draw_heading("SETTINGS", w, h, font_large)
        cat = self.settings_categories[self.settings_category_selected]
        cat_surf = font_small.render("[ < ]  %s  [ > ]  (TAB to cycle)" % cat, True, (120, 120, 120))
        self.screen.blit(cat_surf, (int(w * 0.08), int(h * 0.18)))
        start_y = int(h * 0.24)
        pitch = font_med.get_linesize() + 10
        hint_y = h - 60
        # Long categories (GRAPHICS has nine) can be taller than the screen on
        # small displays, so the list scrolls and keeps the selection visible.
        visible = max(1, int((hint_y - start_y) // pitch))
        total = len(self.settings_options)
        scroll = int(getattr(self, "settings_scroll", 0))
        if self.settings_selected < scroll:
            scroll = self.settings_selected
        elif self.settings_selected >= scroll + visible:
            scroll = self.settings_selected - visible + 1
        scroll = max(0, min(scroll, max(0, total - visible)))
        self.settings_scroll = scroll
        s = self.game_state.get("settings", {})
        kb = s.get("keybinds", {})
        for row, i in enumerate(range(scroll, min(total, scroll + visible))):
            option = self.settings_options[i]
            color = config.COLOR_WHITE if i == self.settings_selected else (110, 110, 110)
            prefix = "> " if i == self.settings_selected else "  "
            if option in config.SETTING_OPTIONS:
                idx = self.settings_idx.get(option, 0)
                value = config.SETTING_OPTIONS[option][idx % len(config.SETTING_OPTIONS[option])]
                label = "%s%s   [%s]" % (prefix, option, value)
            elif option.startswith("Rebind:"):
                keymap = {
                    "Rebind: Up": kb.get("up", "UP"),
                    "Rebind: Down": kb.get("down", "DOWN"),
                    "Rebind: Confirm": kb.get("confirm", "RETURN"),
                    "Rebind: Back/Pause": kb.get("back", "ESCAPE"),
                }
                val = keymap.get(option, "?")
                if getattr(self, "rebinding", None) == option and i == self.settings_selected:
                    label = "%s%s   [PRESS KEY...]" % (prefix, option)
                    color = (200, 60, 60)
                else:
                    label = "%s%s   [%s]" % (prefix, option, val)
            else:
                label = prefix + option
            surf = font_med.render(label, True, color)
            y = start_y + row * pitch
            self.screen.blit(surf, (int(w * 0.08), y))
            if i == self.settings_selected:
                self._eye_focus_rect = (int(w * 0.08), y,
                                        max(1, surf.get_width()),
                                        max(1, surf.get_height()))
            self._touch_zone(int(w * 0.08) - 8, y, int(w * 0.8) + 16,
                             pitch - 2, "settings", i)
        if total > visible:
            more = font_small.render("(%d/%d)" % (self.settings_selected + 1, total), True, (90, 90, 90))
            self.screen.blit(more, (w - more.get_width() - 12, int(h * 0.18)))
        if getattr(self, "rebinding", None):
            hint = font_small.render("Press any key to bind (ESC to cancel)", True, (160, 80, 80))
        else:
            hint = font_small.render("TAP: CHANGE/REBIND    [TAB/</>] CATEGORY    [ESC] BACK" if IS_ANDROID
                                     else "[ENTER] CHANGE/REBIND    [TAB/LEFT/RIGHT] CATEGORY    [ESC] BACK", True, (80, 80, 80))
        self.screen.blit(hint, (int(w * 0.08), h - 50))
        # A rejected rebind says so, and says why.
        if getattr(self, "rebind_error", "") and self.now < getattr(self, "rebind_error_until", 0.0):
            err = font_small.render("CANNOT BIND: %s" % self.rebind_error, True, (200, 60, 60))
            self.screen.blit(err, (int(w * 0.08), h - 76))

    def _draw_about(self, w, h):
        font_large, font_med, font_small = self._fonts()
        self._draw_heading("ABOUT", w, h, font_large, 0.06)
        options = ["About Info", "Credits", "< Back"]
        for i, option in enumerate(options):
            color = config.COLOR_WHITE if i == self.about_selected else (110, 110, 110)
            prefix = "> " if i == self.about_selected else "  "
            surf = font_small.render(prefix + option, True, color)
            y = int(h * 0.16) + i * (font_small.get_linesize() + 6)
            self.screen.blit(surf, (int(w * 0.08), y))
            if i == self.about_selected:
                self._eye_focus_rect = (int(w * 0.08), y,
                                        max(1, surf.get_width()),
                                        max(1, surf.get_height()))
            self._touch_zone(int(w * 0.08) - 8, y, int(w * 0.6) + 16,
                             font_small.get_linesize() + 4, "about", i)

        if self.about_selected == 0:
            about_text = self.about_text
            if self.update_available:
                about_text += ("\n\nUPDATE AVAILABLE\nv%s is ready. %s"
                               % (self.update_available.get("version", "?"),
                                  "Tap the banner on the title screen to download."
                                  if IS_ANDROID else
                                  "Press U on the title screen to open the download page."))
            ui.render_text_block(self.screen, about_text, font_small, config.COLOR_WHITE,
                                 int(w * 0.08), int(h * 0.30), int(w * 0.8))
        elif self.about_selected == 1:
            ui.render_text_block(self.screen, CREDITS_TEXT, font_small, config.COLOR_WHITE,
                                 int(w * 0.08), int(h * 0.30), int(w * 0.8))

    def _draw_help(self, w, h):
        font_large, font_med, font_small = self._fonts()
        self._draw_heading("HELP", w, h, font_large)
        ui.render_text_block(self.screen, self.help_text, font_small, config.COLOR_WHITE,
                             int(w * 0.08), int(h * 0.22), int(w * 0.8))
        hint = font_small.render("TAP ANYWHERE TO GO BACK" if IS_ANDROID else "[ESC] BACK",
                                 True, (80, 80, 80))
        self.screen.blit(hint, (int(w * 0.08), h - 50))
        self._touch_zone(0, 0, w, h, "back")   # read-only screen: any tap leaves

    def _draw_logs(self, w, h):
        font_large, font_med, font_small = self._fonts()
        self._draw_heading("LOGS", w, h, font_large, 0.06)
        y = int(h * 0.16)
        for entry in LOGS_ENTRIES:
            for line in entry.split("\n"):
                if y > h - 40:
                    break
                color = (90, 90, 90) if line.startswith("ENTRY") else config.COLOR_WHITE
                ui.render_text_block(self.screen, line, font_small, color,
                                     int(w * 0.08), y, int(w * 0.8))
                y += ui.wrapped_line_count(line, font_small, color, int(w * 0.8)) * (font_small.get_linesize() + 4)
            y += 8
        hint = font_small.render("TAP ANYWHERE TO GO BACK" if IS_ANDROID else "[ESC] BACK",
                                 True, (80, 80, 80))
        self.screen.blit(hint, (int(w * 0.08), h - 50))
        self._touch_zone(0, 0, w, h, "back")   # read-only screen: any tap leaves

    def _draw_pause(self, w, h):
        font_large, font_med, font_small = self._fonts()
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        self.screen.blit(overlay, (0, 0))
        title = font_large.render("PAUSED", True, config.COLOR_WHITE)
        self.screen.blit(title, (w // 2 - title.get_width() // 2, int(h * 0.22)))
        for i, opt in enumerate(self.pause_options):
            color = config.COLOR_WHITE if i == self.pause_selected else (110, 110, 110)
            prefix = "> " if i == self.pause_selected else "  "
            surf = font_med.render(prefix + opt, True, color)
            y = int(h * 0.38) + i * (font_med.get_linesize() + 14)
            self.screen.blit(surf, (int(w * 0.08), y))
            if i == self.pause_selected:
                self._eye_focus_rect = (int(w * 0.08), y,
                                        max(1, surf.get_width()),
                                        max(1, surf.get_height()))
        hint = font_small.render("[ESC] RESUME    [ENTER] SELECT", True, (80, 80, 80))
        self.screen.blit(hint, (int(w * 0.08), h - 50))

    # --- the watching eye ----------------------------------------------------
    # The eye never goes away. While the cursor is in the window it watches the
    # option you have highlighted; with nothing highlighted it stares straight
    # at the player. Once the cursor leaves the window the pupil follows it out
    # of the frame. It blinks at you when you are not looking.
    def _on_window_focus(self, gained):
        """The game window gained or lost focus.

        Losing focus hands the watch over to the desktop eye (Windows and
        macOS only). Regaining focus brings it back into the window.
        """
        self._window_focused = bool(gained)
        ov = getattr(self, "_overlay", None)
        if ov is None:
            return
        try:
            if gained:
                ov.stop()
            else:
                ov.start()
        except Exception:
            pass

    def _eye_cursor_in_window(self, w, h):
        """Where the cursor is, in window coordinates.

        Returns (x, y, inside). When the cursor has left the window but the
        window still has focus, the coordinates are extrapolated so the pupil
        keeps following it off the edge of the screen.
        """
        local = None
        # Preferred: the OS knows where the cursor is even when it is outside
        # our window.
        try:
            gx, gy = os_layer.get_global_cursor()
            bounds = os_layer.get_window_bounds()
            if bounds is not None:
                left, top, bw, bh = bounds
                # The window may be scaled; map desktop pixels onto the frame.
                sx = float(w) / max(1, bw) if bw else 1.0
                sy = float(h) / max(1, bh) if bh else 1.0
                local = ((gx - left) * sx, (gy - top) * sy)
        except Exception:
            local = None
        if local is None:
            try:
                local = pygame.mouse.get_pos()
            except Exception:
                local = (w // 2, h // 2)
        mx, my = local
        inside = (0 <= mx < w and 0 <= my < h)
        return mx, my, inside

    def _eye_anchor(self, w, h):
        """Where the eye sits.

        Bottom-right in the menus, top-right during the game: in gameplay the
        top-right is where the picture scares and the camera feed want to be,
        so the eye gets out of their way and sits above the action instead.
        """
        r = ui.eye_radius(w, h)
        margin = int(r * 0.55)
        if self.state in ("PLAYING", "EXITFADE"):
            ex = w - r - margin
            ey = int(r * 0.75)
        else:
            ex = w - r - margin
            ey = h - r - margin
        return (ex, ey), r

    def _eye_look_target(self, w, h):
        """Where the pupil should point, or None to look at the player.

        Priority, highest first:

        1. The cursor, if it has left the window. The pupil follows it out of
           the frame, so the eye watches where you went.
        2. The highlighted option, declared by the screen that drew it. This
           is the real rect, so scrolling Settings and moving answer blocks
           are followed correctly.
        3. The player, when the cursor is inside but nothing is selected.

        The cursor check comes before the focus check: a cursor that has left
        the window is followed even when the window is not focused, which is
        what keeps the eye working on Linux where there is no desktop overlay.
        """
        try:
            mx, my, inside = self._eye_cursor_in_window(w, h)
        except Exception:
            inside = True
        if not inside:
            return (mx, my)
        if not getattr(self, "_window_focused", True):
            return None
        rect = getattr(self, "_eye_focus_rect", None)
        try:
            if rect is not None and rect[2] > 0 and rect[3] > 0:
                return (rect[0] + rect[2] / 2.0, rect[1] + rect[3] / 2.0)
        except (TypeError, IndexError):
            pass
        return None

    def _eye_scare_active(self):
        """Is something happening right now that the eye should react to?

        Reads the effect timers the scare system writes, so it covers every
        scare the game can fire without the eye having to know their names.
        """
        fx = getattr(self, "fx", None) or {}
        now = getattr(self, "now", time.time())
        for key, value in fx.items():
            if not key.endswith("_until"):
                continue
            try:
                if float(value) > now:
                    return True
            except (TypeError, ValueError):
                continue
        return False

    def _eye_react_to_answer(self, answer, elapsed=0.0):
        """The eye notices how you answer.

        Answer the same thing twice and the pupil tightens a little, and the
        eye holds that stare. Do it three times and it flushes red. Hesitate
        for a long time and it broadens very slightly, because something was
        expected to happen and did not.
        """
        st = self._eye_state
        now = time.time()
        hist = st.setdefault("answers", [])
        hist.append(answer)
        if len(hist) > 6:
            del hist[:-6]

        repeats = 0
        for a in reversed(hist[:-1]):
            if a == answer:
                repeats += 1
            else:
                break

        if repeats >= 2:
            st["reaction_until"] = now + 2.2
            st["reaction_kind"] = "accuse"
            st["reaction_dilation"] = 1.14
            st["reaction_angry"] = True
        elif repeats == 1:
            st["reaction_until"] = now + 1.4
            st["reaction_kind"] = "notice"
            st["reaction_dilation"] = 0.88
            st["reaction_angry"] = False
        else:
            st["reaction_until"] = now + 0.9
            st["reaction_kind"] = "idle"
            st["reaction_dilation"] = 1.0
            st["reaction_angry"] = False

        # A long hesitation gets its own reaction: the pupil broadens a touch.
        try:
            if elapsed > config.HESITATION_THRESHOLD:
                st["reaction_until"] = now + 1.2
                st["reaction_kind"] = "hesitate"
                st["reaction_dilation"] = 1.08
        except Exception:
            pass

    def _eye_dilation(self, now):
        """How open the pupil is right now.

        The base is a slow, irregular pulse — a living pupil is never exactly
        the same size twice. The whole range is deliberately small: the eye
        should feel alive, not like a cartoon pupil zooming in and out.
        """
        st = self._eye_state
        session = max(1, int(getattr(self, "run_count", 1) or 1))
        # Later sessions pulse a little faster, but never much wider.
        rate = 0.82 + 0.10 * (session - 1)
        amp = 0.032 + 0.008 * (session - 1)
        # The phase is measured from a fixed epoch, not from the raw clock, so
        # the sine stays precise however far the clock has run.
        epoch = float(st.get("pulse_epoch") or now or 0.0)
        phase = float(st.get("pulse_phase", 0.0)) + (now - epoch) * rate
        base = 1.0 + amp * math.sin(phase) + 0.010 * math.sin(phase * 2.7)

        if now < st.get("reaction_until", 0.0):
            target = float(st.get("reaction_dilation", 1.0))
            # Ease towards the reaction, then relax back.
            st["reaction_blend"] = min(1.0, st.get("reaction_blend", 0.0) + 0.35)
        else:
            st["reaction_blend"] = max(0.0, st.get("reaction_blend", 0.0) - 0.07)
            target = 1.0
        blend = st.get("reaction_blend", 0.0)
        return base * ((1.0 - blend) + blend * target)

    def _eye_end_active(self):
        """Is the session over?

        When it is, the small corner eye steps aside: there is only going to
        be one eye now, and it is not in the corner.
        """
        if self.state not in ("PLAYING", "EXITFADE"):
            return False
        script = getattr(self, "active_script", None) or []
        return bool(getattr(self, "pending_exit", False)) or \
            self.current_step >= len(script)

    def _draw_end_eye(self, w, h):
        """The end of the session: one big eye, at the back, staring out.

        Drawn behind the text so it reads as something behind the glass,
        watching you read the message it is waiting for you to read.
        """
        st = self._eye_state
        now = time.time()

        # It swells very slowly while you sit there with the message.
        age = max(0.0, now - float(getattr(self, "exit_message_at", now) or now))
        grow = min(1.0, age / 3.0)
        r = int(min(w, h) * (0.26 + 0.20 * grow))
        cx = w // 2
        cy = int(h * 0.46)

        # It looks at you while the cursor is in the window. Once the cursor
        # leaves, the pupil follows it out of the frame.
        try:
            if getattr(self, "_window_focused", True):
                mx, my, inside = self._eye_cursor_in_window(w, h)
            else:
                inside = True
        except Exception:
            inside = True
        target = None if inside else (mx, my)
        px, py = ui.eye_pupil_offset(cx, cy, r, target)

        # A slow pulse, but only a slight one. It is not human any more.
        dil = 1.0 + 0.028 * math.sin(now * 0.85) + 0.010 * math.sin(now * 2.4)

        # It blinks, but rarely, and it takes its time opening again.
        openness = 1.0
        if now >= st["next_blink"] and now >= st["blink_until"]:
            st["blink_start"] = now
            st["blink_until"] = now + 0.45
            st["next_blink"] = now + random.uniform(3.5, 8.0)
        if st["blink_until"] > now:
            t = (now - st["blink_start"]) / max(1e-6, st["blink_until"] - st["blink_start"])
            openness = max(0.0, abs(2.0 * t - 1.0))

        # Dimmed: it is behind the screen, not on it.
        ui.draw_eye(self.screen, cx, cy, r, openness=openness,
                    pupil=(px, py), angry=False, dilation=dil, shade=0.55)

    def _draw_watching_eye(self, w, h):
        """Draw the eye and animate its pupil, lid and blink."""
        # At the end there is only the big one. Do not draw two.
        if self._eye_end_active():
            return
        st = self._eye_state
        (cx, cy), r = self._eye_anchor(w, h)
        st["x"], st["y"], st["radius"] = cx, cy, r

        now = time.time()
        # Later sessions get twitchier: the eye blinks more often.
        session = max(1, int(getattr(self, "run_count", 1) or 1))
        jitter = 1.0 + 0.55 * (session - 1)

        # --- is something happening? -----------------------------------------
        scared = self._eye_scare_active()
        if scared:
            st["scared_until"] = now + 0.9

        angry = now < st.get("scared_until", 0.0)
        # An answer the eye did not like also flushes it red.
        reacting = now < st.get("reaction_until", 0.0)
        if reacting and st.get("reaction_angry"):
            angry = True

        # --- blink timing ----------------------------------------------------
        if now >= st["next_blink"] and now >= st["blink_until"]:
            st["blink_start"] = now
            st["blink_until"] = now + (0.22 if angry else 0.16)
            if angry:
                # A scare makes it blink urgently, over and over.
                st["next_blink"] = now + random.uniform(0.12, 0.35)
            else:
                st["next_blink"] = now + random.uniform(3.5, 11.0) / jitter
        openness = 1.0
        if st["blink_until"] > now:
            # A quick squeeze: fully shut at the midpoint.
            t = (now - st["blink_start"]) / max(1e-6, st["blink_until"] - st["blink_start"])
            openness = max(0.0, abs(2.0 * t - 1.0))

        # --- pick the look target -------------------------------------------
        # None means straight out of the screen at the player. The eye only
        # chases the cursor after it has left the window.
        target = self._eye_look_target(w, h)

        # --- pupil offset ----------------------------------------------------
        px, py = ui.eye_pupil_offset(cx, cy, r, target)
        # Smooth the movement so the eye never snaps, but move fast enough
        # that the pupil visibly leaves the player's face when the cursor
        # crosses the window edge.
        rate = 0.34 if angry else 0.30
        sx = st["pupil_x"] + (px - st["pupil_x"]) * rate
        sy = st["pupil_y"] + (py - st["pupil_y"]) * rate
        st["pupil_x"], st["pupil_y"] = sx, sy

        # --- pupil size ------------------------------------------------------
        dil = self._eye_dilation(now)

        ui.draw_eye(self.screen, cx, cy, r, openness=openness,
                    pupil=(sx, sy), angry=angry, dilation=dil)

    def _draw_playing(self, w, h):
        font_large, font_med, font_small = self._fonts()
        ui.update_webcam_surface()

        if self.pending_exit or self.current_step >= len(self.active_script):
            self.screen.blit(self._black_overlay(w, h), (0, 0))
            # One big eye, at the back, staring from behind the screen. It goes
            # down before the text so the text is painted over it.
            self._draw_end_eye(w, h)
            if not self.pending_exit:
                # The script ran out without an explicit exit. The session is
                # over anyway, so say it and let the eye be seen.
                self.pending_exit = True
                self.exit_message_at = self.now
            # Make leaving explicit: the session is over, reopen for the next.
            font_small = self._fonts()[2]
            if self.run_count >= 3:
                msg = "close this window. do not open it again."
            else:
                msg = "close this window, then open it again for the next session."
            # Bright enough to read over the eye behind it.
            surf = font_small.render(msg, True, (200, 32, 32))
            self.screen.blit(surf, (w // 2 - surf.get_width() // 2, h // 2 + 30))
            if self.now - self.exit_message_at > 2.0:
                self.running = False
            return

        step = self.active_script[self.current_step]
        step_type = step.get("type", "choice")
        shake = (self.shake_x, self.shake_y) if self.state == "PLAYING" else (0, 0)

        base_x = int(w * 0.08) + shake[0]
        base_y = int(h * 0.12) + shake[1]
        max_width = int(w * 0.82)

        if step_type == "wait":
            text = step["q"]
            ui.render_text_block(self.screen, text, font_med, config.COLOR_WHITE,
                                 base_x, base_y, max_width, t=self.now, sway_amp=2,
                                 outline=config.TEXT_OUTLINE_COLOR)
            ui.draw_text(self.screen, ". . .", font_small, config.COLOR_DIM_RED,
                         base_x, h - int(h * 0.18))
        else:
            text = step["q"] or ""
            # A question that arrives from the room is dressed like every other
            # question: no "from X" label, no attribution, nothing. Anything
            # that distinguishes it tells the player somebody is watching, which
            # is the whole thing this screen is not allowed to give away.
            t_color = config.COLOR_RED if ("afraid" in text.lower() or self.run_count >= 3) else config.COLOR_WHITE
            if self.typing_state == "THINKING":
                dots = ["...", "....", ".....", "......"][int(self.now * 2) % 4]
                ui.draw_text(self.screen, dots, font_med, config.COLOR_DIM_RED, base_x, base_y)
            elif self.typing_state == "TYPING":
                partial = text[:self.typing_index]
                sway = self.game_state.get("settings", {}).get("sway_intensity", 1.0)
                sway_amp = int(2 + 4 * sway) if sway > 0 else 0
                ui.render_text_block(self.screen, partial, font_med, t_color,
                                     base_x, base_y, max_width,
                                     t=self.now if sway_amp else None, sway_amp=sway_amp,
                                     alpha_base=255, outline=config.TEXT_OUTLINE_COLOR)
                if partial and int(self.now * 2.4) % 2 == 0:
                    cx, cy = ui.wrap_cursor_pos(partial, font_med, base_x, base_y, max_width)
                    caret = font_med.render("_", True, t_color)
                    self.screen.blit(caret, (cx, cy))
            elif self.typing_state == "WAITING":
                sway = self.game_state.get("settings", {}).get("sway_intensity", 1.0)
                sway_amp = int(2 + 4 * sway) if sway > 0 else 0
                opts = step["opts"]
                opts_x = base_x
                line_h = font_med.get_linesize() + 4
                # Size the question by its *wrapped* height, not its hard-newline
                # count — a soft-wrapped question is several visual lines tall and
                # used to have the options drawn straight on top of it.
                q_lines = ui.wrapped_line_count(text, font_med, t_color, max_width)
                opts_y = base_y + q_lines * line_h + 34
                opts_gap = font_med.get_linesize() + 10
                # Long questions can wrap far enough to push options off-screen;
                # tighten the row gap (and lift the block) rather than overlap.
                bottom = h - 24
                if opts:
                    avail = bottom - opts_y
                    if len(opts) * opts_gap > avail:
                        opts_gap = max(font_med.get_linesize(), avail // len(opts))
                    if opts_y + len(opts) * opts_gap > bottom:
                        opts_y = max(base_y + q_lines * line_h + 12, bottom - len(opts) * opts_gap)
                # Readability wash: a calm patch of screen under the block, so
                # the question doesn't drown in static and scanlines.
                block_bottom = (opts_y + len(opts) * opts_gap) if opts else base_y + q_lines * line_h
                ui.draw_readability_panel(self.screen, base_x - 20, base_y - 16,
                                          max_width + 40, block_bottom - base_y + 30)
                # Website-style body text: red/cyan split + occasional jitter + sway.
                ui.render_glitch_block(self.screen, text, font_med, t_color,
                                       base_x, base_y, max_width,
                                       t=self.now, sway_amp=sway_amp,
                                       alpha_base=255)
                sel_color = config.COLOR_RED if self.run_count >= 3 else config.COLOR_GREEN
                for i, option in enumerate(opts):
                    if i == self.selected_answer:
                        p = 0.5 + 0.5 * math.sin(self.now * 4.0 + i)
                        color = tuple(min(255, int(c * (0.65 + 0.5 * p))) for c in sel_color)
                    else:
                        color = config.COLOR_WHITE
                    prefix = "> " if i == self.selected_answer else "  "
                    ui.draw_text(self.screen, prefix + option, font_med, color,
                                 opts_x, opts_y + i * opts_gap)
                    if i == self.selected_answer:
                        tw, th = font_med.size(prefix + option)
                        self._eye_focus_rect = (opts_x, opts_y + i * opts_gap,
                                                max(1, tw), max(1, th))
                    self._touch_zone(opts_x - 10, opts_y + i * opts_gap,
                                     max_width + 20, opts_gap - 2, "answer", i)
        # whisper reaction line
        if self.fx["whisper_text"] and self.fx["whisper_until"] > self.now:
            ui.draw_text(self.screen, self.fx["whisper_text"].replace("\n", " "),
                         font_small, (150, 0, 0), base_x, h - int(h * 0.28))

        # webcam feed
        if ui.webcam_active and ui.webcam_surface is not None:
            cw, chh = ui.webcam_surface.get_size()
            cam_x = w - cw - 20
            cam_y = h - chh - 40
            self.screen.blit(ui.webcam_surface, (cam_x, cam_y))
            label = font_small.render("CAMERA FEED — ACTIVE", True, config.COLOR_RED)
            self.screen.blit(label, (cam_x, cam_y + chh + 2))

        # picture scare
        if self.local_image is not None:
            iw, ih = self.local_image.get_size()
            self.screen.blit(self.local_image, (w - iw - 40, 40))

        # location card — it names where you are (Classic's location bite)
        loc = step.get("_location_card")
        if loc:
            ui.draw_location_card(self.screen, loc, w, h)

        # overlays
        if self.fx["corrupt_until"] > self.now:
            ui.apply_corruption(self.screen, w, h, self.now)
        if self.fx["flicker_until"] > self.now:
            ui.apply_flicker(self.screen, w, h)
        if self.fx["webcam_flash_until"] > self.now:
            ui.apply_shadow_static(self.screen, w, h, intensity=1.5)
        if self.fx["screen_tear_until"] > self.now:
            ui.apply_screen_tear(self.screen, w, h)
        if self.fx["rgb_split_until"] > self.now:
            amount = 4 + int(4 * math.sin(self.now * 21.0))
            ui.apply_rgb_split(self.screen, w, h, amount=max(2, amount))

        ui.apply_shadow_static(self.screen, w, h,
                               intensity=1.5 if self.run_count >= 3 else 1.0)

        self._draw_malware_overlays(w, h)

    def _draw_malware_overlays(self, w, h):
        """Fake scanner / BSOD / console / file list / security modal.

        All of it is drawn by the game. The only real-world touches elsewhere in
        a scare (clipboard, a Desktop note, the title bar) are handled by
        os_layer and gated by the ACCESSIBILITY setting.
        """
        fx = self.fx
        now = self.now
        try:
            font_large, font_med, font_small = self._fonts()
        except Exception:
            return
        who = ""
        if (fx.get("fake_scan_until", 0) > now or fx.get("fake_terminal_until", 0) > now
                or fx.get("file_names_until", 0) > now):
            try:
                who = os_layer.get_cached_username() or ""
            except Exception:
                who = ""

        def span(key):
            at = float(fx.get(key + "_at", 0.0) or 0.0)
            until = float(fx.get(key + "_until", 0.0) or 0.0)
            return now - at, max(0.1, until - at)

        if fx.get("fake_bsod_until", 0) > now:
            t, d = span("fake_bsod")
            ui.draw_fake_bsod(self.screen, w, h, t, duration=d,
                              font_title=font_large, font_body=font_small)
        if fx.get("fake_scan_until", 0) > now:
            t, d = span("fake_scan")
            ui.draw_fake_scan(self.screen, w, h, t, duration=d,
                              font_title=font_med, font_body=font_small,
                              font_small=font_small, username=who)
        if fx.get("fake_terminal_until", 0) > now:
            t, d = span("fake_terminal")
            ui.draw_fake_terminal(self.screen, w, h, t, duration=d,
                                  lines=fx.get("terminal_lines") or [],
                                  font_body=font_small, font_title=font_small)
        if fx.get("file_names_until", 0) > now:
            t, d = span("file_names")
            sep = "\\" if os_layer.SYSTEM == "Windows" else "/"
            label = (" C:%sUsers%s%s%sDesktop " % (sep, sep, who or "user", sep)
                     if os_layer.SYSTEM == "Windows"
                     else " %s%s%sDesktop " % (sep, "home" + sep, (who or "user") + sep))
            ui.draw_file_list(self.screen, w, h, t, duration=d,
                              names=fx.get("file_names") or [],
                              font_body=font_small, font_title=font_small,
                              title=label)
        if fx.get("security_alert_until", 0) > now:
            t, d = span("security_alert")
            ui.draw_security_alert(self.screen, w, h, t, duration=d,
                                   font_title=font_med, font_body=font_small)

    # --- aggression helpers ----------------------------------------------------

    def _say_aggressive(self, text, duration=3.5, violent=True):
        """Show an aggressive line and shove the window at the same moment — the
        shout and the shake land together.

        Windows/macOS get a real, violent window shake. Elsewhere (Wayland
        forbids self-positioning) it degrades to an in-frame screen shake, so the
        jolt still reads."""
        self.fx["whisper_text"] = text
        self.fx["whisper_until"] = max(float(self.fx.get("whisper_until", 0.0)), self.now + duration)
        if violent:
            os_layer.shake_game_window(cycles=14, amplitude=40)
            self.fx["screen_shake_until"] = self.now + 0.7
            self.fx["shake_amp"] = max(int(self.fx.get("shake_amp", 0) or 0), 16)

    # --- close resistance -------------------------------------------------------
    def _resist_close(self):
        """Close attempts are refused and escalate into scares. Only a
        Task Manager force-kill ends the game."""
        rapid = self.now - self._last_close_try < 4.0 and self.close_attempts > 0
        self._last_close_try = self.now
        self.close_attempts += 1
        # Spamming the close button ranks it up faster than waiting between tries:
        # attempt 4 in a row already counts as a much higher threat level.
        self._close_burst = self._close_burst + 1 if rapid else 0
        n = self.close_attempts + self._close_burst
        self.close_msg_until = self.now + 2.5
        os_layer.attempt_close_with_warning()
        # Immediate and loud: a hissed line plus a violent shake on frame one.
        self._say_aggressive(random.choice(_ANGRY_CLOSE_LINES), duration=3.4, violent=True)
        self.fx["flicker_until"] = max(self.fx["flicker_until"], self.now + 0.45)
        audio.play_error_sound()
        # Windows-first bite: keep the window punched to the front, flash the
        # taskbar entry, and re-kill the system close item as they fight it.
        if os_layer.SYSTEM == "Windows":
            os_layer.set_window_topmost()
            if n >= 2:
                os_layer.flash_window()
            if n >= 4:
                os_layer.force_foreground()
        if n >= 2:
            self.fx["corrupt_until"] = max(self.fx["corrupt_until"], self.now + 0.9)
            os_layer.shake_game_window(cycles=8, amplitude=26)
        if n >= 3:
            self.fx["corrupt_until"] = max(self.fx["corrupt_until"], self.now + 1.7)
            audio.play_glitch_sound()
            os_layer.shake_game_window(cycles=10, amplitude=32)
        if n >= 4:
            os_layer.teleport_window_random()
            audio.play_static_scream()
            os_layer.shake_game_window(cycles=12, amplitude=38)
        if n >= 6:
            _sw, _sh = self.screen.get_size()   # the frame may have been resized
            os_layer.begin_mouse_move(random.randint(40, max(80, _sw - 40)),
                                      random.randint(40, max(80, _sh - 40)))
            os_layer.show_os_notification(config.APP_NAME, "You cannot leave.")
        if n >= 8 and n % 2 == 0:
            # Mid-game: more aggressive repositioning and a hard shake.
            os_layer.teleport_window_random()
            os_layer.shake_game_window(cycles=16, amplitude=44)
        if n >= 10 and n % 3 == 0:
            self.fx["corrupt_until"] = max(self.fx["corrupt_until"], self.now + 2.6)
            audio.play_static_scream()
        if n >= config.CLOSE_RESIST_MAX and n % 4 == 0:
            # "You live here now" phase: constant drift, no rest.
            os_layer.drift_window(8.0)

    # --- main loop ------------------------------------------------------------
    def run(self):
        os_layer.start_window_float()
        self._start_update_check()
        while self.running:
            self.clock.tick(config.FRAMERATE)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    if config.BLOCK_CLOSE_ATTEMPTS:
                        self._resist_close()
                    else:
                        self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_F4 and (event.mod & pygame.KMOD_ALT):
                        if config.BLOCK_CLOSE_ATTEMPTS:
                            self._resist_close()
                        else:
                            self.running = False
                    else:
                        self._handle_key(event.key,
                                         getattr(event, "unicode", "") or "")
                elif event.type == pygame.VIDEORESIZE and not config.WINDOW_LOCKED:
                    self._on_resize(event.w, event.h)
                elif event.type in (getattr(pygame, "WINDOWFOCUSLOST", -1),
                                    getattr(pygame, "WINDOWFOCUSGAINED", -1),
                                    pygame.ACTIVEEVENT):
                    # The window lost or regained focus. When it loses focus
                    # the desktop eye takes over and follows the player around
                    # their computer; the in-game one goes quiet.
                    gained = getattr(event, "gain", None)
                    if event.type == getattr(pygame, "WINDOWFOCUSGAINED", -1):
                        gained = 1
                    elif event.type == getattr(pygame, "WINDOWFOCUSLOST", -1):
                        gained = 0
                    else:
                        # ACTIVEEVENT: gain is 0 (lost), 1 (gained) or
                        # 2 (minimised). A minimised window has lost focus.
                        gained = 1 if gained == 1 else 0
                    self._on_window_focus(gained)
                elif event.type == pygame.MOUSEMOTION:
                    # Subtle hover parallax — the window leans toward the cursor
                    sw, sh = self.screen.get_size()
                    os_layer.set_hover_offset(event.pos[0], event.pos[1], sw, sh)
                elif event.type == pygame.FINGERDOWN and IS_ANDROID:
                    # Touch: FINGER* coordinates are normalized 0..1 over the
                    # window, so scale them to the current framebuffer.
                    w_px, h_px = self.screen.get_size()
                    self._handle_touch(event.x * w_px, event.y * h_px)

            os_layer.update_window_anim()
            os_layer.update_mouse_anim()
            os_layer.nudge_mouse_from_close()
            pic = ui.poll_picture_result()
            if pic is not None:
                self.local_image = pic

            self._update()
            self._draw()
            self._maybe_check_updates()

        audio.stop_ambience()
        # The desktop eye must not outlive the game.
        ov = getattr(self, "_overlay", None)
        if ov is not None:
            try:
                ov.stop()
            except Exception:
                pass
        pygame.quit()


def main():
    Game().run()


if __name__ == "__main__":
    main()
