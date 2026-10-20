"""Procedural audio: every sound effect is synthesized once at startup into a
cached pool, plus a looping ambient drone and the LOGS-screen music track."""
import math
import random
import threading
import time

import numpy as np
import pygame

from . import config

_SAMPLE_RATE = 22050
_POOL_SIZE = 5

_SOUND_CACHE = {}
_ambience_channel = None
_logs_music_playing = False


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


def _pick(name):
    pool = _SOUND_CACHE.get(name) or []
    return random.choice(pool) if pool else None


def play_type_sound():
    s = _pick("type")
    if s:
        s.play().set_volume(0.15)


def play_ui_nav_sound():
    s = _pick("ui_nav")
    if s:
        s.play().set_volume(0.2)


def play_ui_select_sound():
    s = _pick("ui_select")
    if s:
        s.play().set_volume(0.3)


def play_mechanical_beep():
    s = _pick("mech_beep")
    if s:
        s.play().set_volume(0.25)


def play_error_sound():
    s = _pick("error")
    if s:
        s.play().set_volume(0.4)


def play_glitch_sound():
    s = _pick("glitch")
    if s:
        s.play().set_volume(0.3)


def play_static_burst():
    s = _pick("static_burst")
    if s:
        s.play().set_volume(0.18)


def play_heartbeat():
    s = _pick("heartbeat")
    if s:
        s.play().set_volume(0.55)


def play_deep_rumble():
    s = _pick("deep_rumble")
    if s:
        s.play().set_volume(0.5)


def play_reverse_chord():
    s = _pick("reverse_chord")
    if s:
        s.play().set_volume(0.35)


def play_static_scream():
    s = _pick("static_scream")
    if s:
        s.play().set_volume(0.45)


def start_ambience():
    global _ambience_channel
    try:
        t = np.linspace(0, 4.0, int(_SAMPLE_RATE * 4.0), False)
        wave = np.sin(2 * np.pi * 50 * t) * 0.5 + np.random.normal(0, 0.03, len(t))
        sound = pygame.mixer.Sound(buffer=np.int16(wave * 12000))
        _ambience_channel = sound.play(-1)
        _ambience_channel.set_volume(0.2)
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


def start_logs_music():
    global _logs_music_playing
    try:
        path = config.asset_path("logsmusic.ogg")
        pygame.mixer.music.load(path)
        pygame.mixer.music.set_volume(0.0)
        pygame.mixer.music.play(-1)
        _logs_music_playing = True

        def _fadein(ms=800):
            steps = max(4, int(ms / 50))
            for i in range(1, steps + 1):
                if not _logs_music_playing:
                    break
                try:
                    pygame.mixer.music.set_volume(float(i) / steps * 0.2)
                except Exception:
                    pass
                time.sleep(ms / steps / 1000.0)

        threading.Thread(target=_fadein, daemon=True).start()
    except Exception:
        pass


def stop_logs_music():
    global _logs_music_playing
    if _logs_music_playing:
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        _logs_music_playing = False


def fade_logs_music(duration_ms=1000):
    global _logs_music_playing
    if _logs_music_playing:
        try:
            pygame.mixer.music.fadeout(int(duration_ms))
        except Exception:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
        _logs_music_playing = False
