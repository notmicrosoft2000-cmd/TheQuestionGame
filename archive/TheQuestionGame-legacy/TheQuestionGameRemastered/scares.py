"""The local horror-effect executor. The AI never executes anything directly —
it only picks a name from this fixed set, and the game runs the local effect.

Every effect degrades gracefully to a no-op if the underlying OS feature is
unavailable (no webcam, no Accessibility permission, etc.).
"""
import random
import threading

from . import audio
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
    if not ui.webcam_active:
        ui.start_webcam_nonblocking()
    game.fx["webcam_flash_until"] = game.now + 4.0
    audio.play_static_burst()


def _do_whisper(game):
    line = random.choice(_WHISPERS)
    threading.Thread(target=os_layer.whisper_text, args=(line,), daemon=True).start()
    game.fx["whisper_text"] = '"' + line + '"'
    game.fx["whisper_until"] = game.now + 3.5


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


def _do_reverse_chord(game):
    threading.Thread(target=audio.play_reverse_chord, daemon=True).start()


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
}


def apply_scare(game, name):
    fn = SCARE_REGISTRY.get(name)
    if fn:
        try:
            fn(game)
            return True
        except Exception:
            pass
    return False
