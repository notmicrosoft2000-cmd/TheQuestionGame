"""The local horror-effect executor. The AI never executes anything directly —
it only picks a name from this fixed set, and the game runs the local effect.

Every effect degrades gracefully to a no-op if the underlying OS feature is
unavailable (no webcam, no Accessibility permission, etc.).
"""
import random
import threading

from . import audio
from . import config
from . import os_layer
from . import ui

_WHISPERS = [
    "I can see you.",
    "You should not have come back.",
    "We have your face now.",
    "It is colder in here.",
    "I am closer than you think.",
    "Your answer was wrong.",
    "We never left.",
    "Do not look away.",
]

_NOTIFICATION_BODIES = [
    "We can see this window.",
    "It is almost over. Come back.",
    "Your wallpaper is ours now.",
    "Do not close this.",
    "We counted your pauses.",
]


def _do_flicker(game):
    game.fx["flicker_until"] = game.now + random.uniform(2.0, 3.0)
    audio.play_glitch_sound()


def _do_webcam_flash(game):
    if not config.WEBCAM_ENABLED:
        return
    if not ui.webcam_active:
        ui.start_webcam_nonblocking()
    game.fx["webcam_flash_until"] = game.now + 4.0
    audio.play_static_burst()


def _do_whisper(game):
    line = random.choice(_WHISPERS)
    threading.Thread(target=os_layer.whisper_text, args=(line,), daemon=True).start()
    game.fx["whisper_text"] = '"' + line + '"'
    game.fx["whisper_until"] = game.now + 3.5
    # It says something aggressive — the window should take the hit with it.
    os_layer.shake_game_window(cycles=14, amplitude=40)
    game.fx["screen_shake_until"] = game.now + 0.7
    game.fx["shake_amp"] = max(int(game.fx.get("shake_amp", 0) or 0), 16)


def _do_window_shake(game):
    os_layer.shake_game_window(cycles=8, amplitude=20)
    audio.play_static_burst()


def _do_mouse_move(game):
    w, h = game.screen.get_size()
    os_layer.begin_mouse_move(
        random.randint(100, max(150, w - 100)),
        random.randint(100, max(150, h - 100)),
        0.5,
    )


def _do_wallpaper(game):
    color = game.game_state.get("fav_color", "black")
    os_layer.set_desktop_wallpaper(color)
    audio.play_mechanical_beep()


def _do_picture(game):
    pic = os_layer.get_cached_random_picture()
    if pic:
        ui.request_picture_scaled_async(pic, 260, 260)
        audio.play_ui_nav_sound()


def _do_notification(game):
    body = random.choice(_NOTIFICATION_BODIES)
    os_layer.show_os_notification("The Question Game Remastered", body)
    audio.play_mechanical_beep()


def _do_heartbeat(game):
    def _beat():
        for _ in range(3):
            audio.play_heartbeat()
            import time as _t
            _t.sleep(0.6)
    threading.Thread(target=_beat, daemon=True).start()


def _do_rumble(game):
    audio.play_deep_rumble()


def _do_corruption(game):
    game.fx["corrupt_until"] = game.now + 2.5
    audio.play_static_scream()


def _do_static_scream(game):
    audio.play_static_scream()


def _do_jumpscare(game):
    """The big one — loud stinger + strobe + corruption, only at high escalation."""
    audio.play_jumpscare()
    game.fx["flicker_until"] = game.now + 1.5
    game.fx["corrupt_until"] = max(game.fx["corrupt_until"], game.now + 1.5)
    game.fx["rgb_split_until"] = max(game.fx["rgb_split_until"], game.now + 1.5)


def _do_window_teleport(game):
    os_layer.teleport_window_random()
    audio.play_glitch_sound()


def _do_window_drift(game):
    threading.Thread(target=os_layer.drift_window, args=(8.0,), daemon=True).start()
    audio.play_deep_rumble()


def _do_rgb_split(game):
    game.fx["rgb_split_until"] = game.now + 2.0
    audio.play_mechanical_beep()


def _do_screen_tear(game):
    game.fx["screen_tear_until"] = game.now + 1.5
    audio.play_static_burst()


def _do_reverse_chord(game):
    threading.Thread(target=audio.play_reverse_chord, daemon=True).start()


def _do_windows_shake(game):
    """Windows: shake every OTHER open window on the desktop."""
    os_layer.shake_other_windows()
    audio.play_deep_rumble()


def _do_windows_minimize(game):
    """Windows: minimize everything else, leaving the player alone with us."""
    os_layer.minimize_other_windows()
    audio.play_mechanical_beep()


# Fixed, AI-choosable set.
SCARE_REGISTRY = {
    "flicker": _do_flicker,
    "webcam_flash": _do_webcam_flash,
    "whisper": _do_whisper,
    "window_shake": _do_window_shake,
    "mouse_move": _do_mouse_move,
    "wallpaper": _do_wallpaper,
    "picture": _do_picture,
    "notification": _do_notification,
    "heartbeat": _do_heartbeat,
    "rumble": _do_rumble,
    "corruption": _do_corruption,
    "static_scream": _do_static_scream,
    "reverse_chord": _do_reverse_chord,
    "window_teleport": _do_window_teleport,
    "window_drift": _do_window_drift,
    "rgb_split": _do_rgb_split,
    "screen_tear": _do_screen_tear,
    "jumpscare": _do_jumpscare,
    "windows_shake": _do_windows_shake,
    "windows_minimize": _do_windows_minimize,
}

# Stacking guard: at most one scare per kind within this window (seconds).
_COOLDOWN = 6.0
_last_applied = {}

# Scares that work by hijacking the *desktop* (window moves, cursor theft,
# wallpaper, minimized apps). On Android the os_layer versions are correct
# no-ops — there is no desktop to hijack — so each gets an in-app stand-in
# below and the hit still lands.
_DESKTOP_SCARES = frozenset({
    "window_shake", "windows_shake", "windows_minimize",
    "window_teleport", "window_drift", "wallpaper", "mouse_move",
})


def _android_stand_in(game, name):
    """Desktop-hijack scare running on a phone? Recreate the *feeling* in-app.

    The port must never let a scare quietly do nothing: a player who reads the
    AI picking "wallpaper" and sees static instead still gets bitten, but a
    scare that evaporates teaches them the game is fake.
    """
    if not config.IS_ANDROID or name not in _DESKTOP_SCARES:
        return
    if name in ("window_shake", "windows_shake", "windows_teleport"):
        game.fx["screen_shake_until"] = max(float(game.fx.get("screen_shake_until", 0.0)),
                                            game.now + 0.9)
        game.fx["shake_amp"] = 24
        if name == "window_teleport":
            # The jump of a teleport reads best as a hard visual lurch.
            game.fx["rgb_split_until"] = max(float(game.fx.get("rgb_split_until", 0.0)),
                                             game.now + 1.0)
    elif name == "window_drift":
        game.fx["screen_shake_until"] = max(float(game.fx.get("screen_shake_until", 0.0)),
                                            game.now + 1.6)
        game.fx["shake_amp"] = 8
    elif name == "mouse_move":
        # No cursor to steal on a touch screen, so it reaches for the answer
        # the player was about to pick instead — same violation, new surface.
        try:
            step = game.active_script[game.current_step]
            opts = step.get("opts") or []
            if opts and game.typing_state == "WAITING":
                game.selected_answer = random.randrange(len(opts))
                audio.play_ui_nav_sound()
                return
        except Exception:
            pass
        game.fx["flicker_until"] = max(float(game.fx.get("flicker_until", 0.0)), game.now + 1.2)
    else:  # wallpaper / windows_minimize: the desktop changed, we show it changed
        game.fx["corrupt_until"] = max(float(game.fx.get("corrupt_until", 0.0)), game.now + 1.2)
        game.fx["flicker_until"] = max(float(game.fx.get("flicker_until", 0.0)), game.now + 1.0)


def apply_scare(game, name):
    fn = SCARE_REGISTRY.get(name)
    if not fn:
        return False
    now = game.now
    if now - _last_applied.get(name, -999.0) < _COOLDOWN:
        return False
    _last_applied[name] = now
    # The operator's sender can fire the same effect gently or hard. A scare
    # sets an "until" timestamp of the form now + duration, so scaling the
    # *duration* is what scales how long it lasts. Scale the clock by mistake
    # and the maths is wrong twice over: 2x makes the effect last for the whole
    # uptime, and 0.5x puts it in the past so nothing shows at all.
    try:
        scale = float(game.fx.get("scare_scale", 1.0) or 1.0)
    except Exception:
        scale = 1.0
    try:
        fn(game)
        _android_stand_in(game, name)
    except Exception:
        return False
    if scale != 1.0:
        # Stretch every deadline the scare just wrote, relative to now, then
        # clamp to the future so a tiny scale cannot retire it instantly.
        for key, value in list(game.fx.items()):
            if not key.endswith("_until"):
                continue
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if value <= now:
                continue
            game.fx[key] = now + (value - now) * max(0.05, scale)
    return True
