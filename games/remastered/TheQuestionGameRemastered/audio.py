"""Procedural audio: every sound effect is synthesized once at startup into a
cached pool, plus looping music tracks (menu/logs/bossfight) and ambience."""
import os
import random
import sys
import threading

import numpy as np
import pygame

from . import config

_SAMPLE_RATE = 22050
_POOL_SIZE = 5

_SOUND_CACHE = {}
_ambience_channel = None
_logs_music_playing = False
_current_music = None
_music_lock = threading.Lock()
_sfx_duck = 1.0
# The player's own SFX volume, from the settings screen. Kept apart from the
# duck, which is a transient thing the game does on its own: they multiply.
_sfx_volume = 1.0
# The player's ambience volume. Remembered separately so it can be set before
# the ambience is even playing.
_ambience_volume = 1.0
# The player's music volume, and the level the game itself wants right now.
_music_volume = 1.0
_music_level = 0.5


def set_sfx_duck(factor):
    """Lower (or restore) all sound-effect volumes so music can breathe."""
    global _sfx_duck
    try:
        _sfx_duck = max(0.0, min(1.0, float(factor)))
    except Exception:
        _sfx_duck = 1.0


def _mk(type_sound):
    buf = np.zeros(int(0.015 * _SAMPLE_RATE), dtype=np.int16)
    for i in range(len(buf)):
        buf[i] = int(random.choice([-8000, 8000]))
    return pygame.mixer.Sound(buffer=buf)


def _mk_nav():
    t = np.linspace(0, 0.03, int(_SAMPLE_RATE * 0.03), False)
    wave = np.sin(2 * np.pi * 600 * t)
    return pygame.mixer.Sound(buffer=np.int16(wave * 8000))


def _mk_select():
    t = np.linspace(0, 0.08, int(_SAMPLE_RATE * 0.08), False)
    wave = np.sin(2 * np.pi * 880 * t)
    return pygame.mixer.Sound(buffer=np.int16(wave * 12000))


def _mk_beep():
    t = np.linspace(0, 0.12, int(_SAMPLE_RATE * 0.12), False)
    wave = np.sin(2 * np.pi * 1200 * t)
    return pygame.mixer.Sound(buffer=np.int16(wave * 14000))


def _mk_error():
    t = np.linspace(0, 0.2, int(_SAMPLE_RATE * 0.2), False)
    wave = np.sin(2 * np.pi * 150 * t) + np.sin(2 * np.pi * 155 * t)
    wave = np.clip(wave, -1, 1)
    return pygame.mixer.Sound(buffer=np.int16(wave * 18000))


def _mk_glitch():
    dur = random.uniform(0.05, 0.18)
    t = np.linspace(0, dur, int(_SAMPLE_RATE * dur), False)
    freq = random.uniform(300, 2200)
    wave = np.sin(2 * np.pi * freq * t)
    noise = np.random.normal(0, 0.4, len(t))
    combined = np.clip(wave * 0.6 + noise * 0.4, -1, 1)
    return pygame.mixer.Sound(buffer=np.int16(combined * 16000))


def _mk_static_burst():
    dur = 0.25
    t = np.linspace(0, dur, int(_SAMPLE_RATE * dur), False)
    noise = np.random.normal(0, 1.0, len(t))
    return pygame.mixer.Sound(buffer=np.int16(np.clip(noise, -1, 1) * 9000))


def _mk_heartbeat():
    dur = 0.18
    t = np.linspace(0, dur, int(_SAMPLE_RATE * dur), False)
    env = np.exp(-t * 25)
    wave = np.sin(2 * np.pi * 55 * t) * env
    return pygame.mixer.Sound(buffer=np.int16(np.clip(wave, -1, 1) * 28000))


def _mk_rumble():
    dur = 0.8
    t = np.linspace(0, dur, int(_SAMPLE_RATE * dur), False)
    freq = np.linspace(80, 40, len(t))
    wave = np.sin(2 * np.pi * freq * t)
    noise = np.random.normal(0, 0.25, len(t))
    combined = np.clip(wave * 0.7 + noise * 0.3, -1, 1)
    env = np.exp(-t * 1.2)
    return pygame.mixer.Sound(buffer=np.int16(combined * env * 22000))


def _mk_reverse_chord():
    dur = 1.2
    t = np.linspace(0, dur, int(_SAMPLE_RATE * dur), False)
    env = np.linspace(0, 1, len(t)) ** 2
    freqs = [220, 277, 330, 370]
    wave = sum(np.sin(2 * np.pi * f * t) for f in freqs) / len(freqs)
    wave = wave * env
    return pygame.mixer.Sound(buffer=np.int16(np.clip(wave, -1, 1) * 14000))


def _mk_scream():
    dur = 0.35
    t = np.linspace(0, dur, int(_SAMPLE_RATE * dur), False)
    freq = np.linspace(400, 3200, len(t))
    wave = np.sin(2 * np.pi * freq * t)
    noise = np.random.normal(0, 0.6, len(t))
    env = np.exp(-t * 6)
    combined = np.clip(wave * 0.5 + noise * 0.5, -1, 1) * env
    return pygame.mixer.Sound(buffer=np.int16(combined * 20000))


def _assets_dir():
    """Where the editable sound assets live (next to the package, or in a bundle)."""
    here = os.path.dirname(os.path.abspath(__file__))
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bundled = os.path.join(meipass, "assets")
        if os.path.isdir(bundled):
            return bundled
    return os.path.join(here, "assets")


def _music_path(name):
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "assets", name))
        candidates.append(os.path.join(meipass, name))
    candidates += [
        os.path.join(here, "assets", name),
        os.path.join(here, name),
        os.path.join(os.path.dirname(here), name),
        name,
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def build_sound_cache():
    _SOUND_CACHE["type"] = [_mk(None) for _ in range(_POOL_SIZE)]
    _SOUND_CACHE["ui_nav"] = [_mk_nav()]
    _SOUND_CACHE["ui_select"] = [_mk_select()]
    _SOUND_CACHE["mech_beep"] = [_mk_beep()]
    _SOUND_CACHE["error"] = [_mk_error()]
    _SOUND_CACHE["glitch"] = [_mk_glitch() for _ in range(_POOL_SIZE)]
    _SOUND_CACHE["static_burst"] = [_mk_static_burst() for _ in range(_POOL_SIZE)]
    _SOUND_CACHE["heartbeat"] = [_mk_heartbeat() for _ in range(_POOL_SIZE)]
    _SOUND_CACHE["deep_rumble"] = [_mk_rumble() for _ in range(_POOL_SIZE)]
    _SOUND_CACHE["reverse_chord"] = [_mk_reverse_chord() for _ in range(_POOL_SIZE)]
    _SOUND_CACHE["static_scream"] = [_mk_scream() for _ in range(_POOL_SIZE)]
    _load_asset_sounds()
    try:
        set_music_level(config.MUSIC_VOLUME)
    except Exception:
        pass


# Map a cache key to the asset basename it should prefer on disk.
ASSET_SOUNDS = {
    "ui_nav": "ui_nav",
    "ui_select": "ui_select",
    "mech_beep": "mech_beep",
    "error": "error",
    "glitch": "glitch",
    "static_burst": "static_burst",
    "heartbeat": "heartbeat",
    "deep_rumble": "deep_rumble",
    "reverse_chord": "reverse_chord",
    "static_scream": "static_scream",
    "ambience": "ambience",
}


def _load_asset_sounds():
    """Prefer real files under assets/; keep the synthesized fallback otherwise.

    On the very first run the assets do not exist yet, so they are generated
    here (see `sfx_gen`) and then loaded. If generation is impossible (no numpy
    writer, read-only folder) the shipped procedural versions stay in place.
    """
    assets_dir = _assets_dir()
    wanted = list(ASSET_SOUNDS.values())
    paths = {}
    try:
        from . import sfx_gen
        paths = sfx_gen.ensure_assets(assets_dir, names=wanted)
    except Exception:
        paths = {}
        for name in wanted:
            p = _music_path(name + ".mp3") or _music_path(name + ".ogg") or _music_path(name + ".wav")
            if p:
                paths[name] = p
    for key, basename in ASSET_SOUNDS.items():
        path = paths.get(basename)
        if not path or not os.path.exists(path):
            continue
        try:
            snd = pygame.mixer.Sound(path)
        except Exception:
            continue
        if key == "ambience":
            _SOUND_CACHE["_ambience_path"] = path
        else:
            _SOUND_CACHE[key] = [snd]


def _pick(name):
    pool = _SOUND_CACHE.get(name) or []
    return random.choice(pool) if pool else None


def _safe_play(sound, volume):
    """play() returns None when the mixer has no free channels — guard it."""
    try:
        chan = sound.play()
        if chan:
            chan.set_volume(volume * _sfx_duck * _sfx_volume)
    except Exception:
        pass


def play_type_sound():
    s = _pick("type")
    if s:
        _safe_play(s, 0.15)


def play_ui_nav_sound():
    s = _pick("ui_nav")
    if s:
        _safe_play(s, 0.2)


def play_ui_select_sound():
    s = _pick("ui_select")
    if s:
        _safe_play(s, 0.3)


def play_mechanical_beep():
    s = _pick("mech_beep")
    if s:
        _safe_play(s, 0.25)


def play_error_sound():
    s = _pick("error")
    if s:
        _safe_play(s, 0.4)


def play_glitch_sound():
    s = _pick("glitch")
    if s:
        _safe_play(s, 0.3)


def play_static_burst():
    s = _pick("static_burst")
    if s:
        _safe_play(s, 0.18)


def play_heartbeat():
    s = _pick("heartbeat")
    if s:
        _safe_play(s, 0.55)


def play_deep_rumble():
    s = _pick("deep_rumble")
    if s:
        _safe_play(s, 0.5)


def play_reverse_chord():
    s = _pick("reverse_chord")
    if s:
        _safe_play(s, 0.35)


_jumpscare_cache = {}


def play_jumpscare():
    path = _music_path("jumpscare.mp3")
    if not path:
        return
    try:
        snd = _jumpscare_cache.get(path)
        if snd is None:
            snd = pygame.mixer.Sound(path)
            _jumpscare_cache[path] = snd
        chan = snd.play()
        if chan:
            chan.set_volume(0.6 * _sfx_duck * _sfx_volume)
    except Exception:
        pass


def play_bossfight():
    play_music("bossfight.mp3", loops=-1, fade_ms=600)


def play_static_scream():
    s = _pick("static_scream")
    if s:
        _safe_play(s, 0.45)


def start_ambience():
    global _ambience_channel
    # Prefer the asset on disk (generated on first run, then user-replaceable).
    path = _SOUND_CACHE.get("_ambience_path")
    if path and os.path.exists(path):
        try:
            snd = _SOUND_CACHE.get("_ambience_sound")
            if snd is None:
                snd = pygame.mixer.Sound(path)
                _SOUND_CACHE["_ambience_sound"] = snd
            _ambience_channel = snd.play(-1)
            if _ambience_channel:
                _ambience_channel.set_volume(0.32 * _ambience_volume)
            return
        except Exception:
            pass
    # Fallback: synthesize the drone in memory.
    try:
        t = np.linspace(0, 30.0, int(_SAMPLE_RATE * 30.0), False)
        # Layered low drone with hiss and slow movement for a less cyclical feel
        drone = np.sin(2 * np.pi * 50 * t) * 0.4
        drone += np.sin(2 * np.pi * 50.6 * t) * 0.25
        drone += np.sin(2 * np.pi * 49.4 * t) * 0.2
        lfo = 0.75 + 0.25 * np.sin(2 * np.pi * 0.08 * t) + 0.1 * np.sin(2 * np.pi * 0.023 * t)
        hiss = np.random.RandomState(12345).normal(0, 0.04, len(t))
        rumble = np.random.RandomState(54321).normal(0, 0.015, len(t))
        wave = (drone * lfo + hiss + rumble) * 0.8
        sound = pygame.mixer.Sound(buffer=np.int16(np.clip(wave, -1, 1) * 14000))
        _ambience_channel = sound.play(-1)
        if _ambience_channel:
            _ambience_channel.set_volume(0.32 * _ambience_volume)
    except Exception:
        pass


def stop_ambience():
    global _ambience_channel
    if _ambience_channel:
        try:
            _ambience_channel.stop()
        except Exception:
            pass
        _ambience_channel = None
    stop_music(600)


def start_logs_music():
    play_music("logsmusic.ogg", loops=-1, fade_ms=400)


def _stop_music(fade_ms=400):
    try:
        pygame.mixer.music.fadeout(int(fade_ms))
    except Exception:
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
    global _current_music, _logs_music_playing
    _current_music = None
    _logs_music_playing = False


def play_music(name, loops=-1, fade_ms=400):
    if not config.MUSIC_ENABLED:
        return
    global _current_music, _logs_music_playing
    # Same track already rolling? Just keep it — do not restart it on every
    # state change (title -> play would otherwise reset the song mid-phrase).
    try:
        if _current_music == name and pygame.mixer.music.get_busy():
            return
    except Exception:
        pass
    path = _music_path(name)
    if not path:
        return
    try:
        pygame.mixer.music.load(path)
        pygame.mixer.music.play(loops=loops, fade_ms=fade_ms)
        _current_music = name
        _logs_music_playing = (name == "logsmusic.ogg")
    except Exception:
        pass


def set_music_volume(volume):
    """The player's music volume, from the settings screen.

    Kept apart from the level the game itself wants for the current screen
    (calm menus, in-game): the two multiply, so the player is always in
    charge of how loud it is.
    """
    global _music_volume
    try:
        _music_volume = max(0.0, min(1.0, float(volume)))
    except Exception:
        _music_volume = 1.0
    _apply_music_volume()


def set_music_level(level):
    """The level the game wants for the music right now."""
    global _music_level
    try:
        _music_level = max(0.0, min(1.0, float(level)))
    except Exception:
        _music_level = 1.0
    _apply_music_volume()


def _apply_music_volume():
    try:
        pygame.mixer.music.set_volume(_music_level * _music_volume)
    except Exception:
        pass


def set_sfx_volume(volume):
    """The player's sound-effect volume, from the settings screen."""
    global _sfx_volume
    try:
        _sfx_volume = max(0.0, min(1.0, float(volume)))
    except Exception:
        _sfx_volume = 1.0


def set_ambience_volume(volume):
    """The player's ambience volume, from the settings screen.

    Remembered even before the ambience starts, so the setting survives being
    applied at launch.
    """
    global _ambience_volume
    try:
        _ambience_volume = max(0.0, min(1.0, float(volume)))
    except Exception:
        _ambience_volume = 1.0
    try:
        if _ambience_channel is not None:
            _ambience_channel.set_volume(0.32 * _ambience_volume)
    except Exception:
        pass


def stop_music(fade_ms=400):
    _stop_music(fade_ms)


def stop_logs_music():
    if _logs_music_playing or _current_music == "logsmusic.ogg":
        _stop_music(0)


def fade_logs_music(duration_ms=800):
    if _logs_music_playing or _current_music == "logsmusic.ogg":
        _stop_music(duration_ms)
