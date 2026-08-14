"""Procedural 1993 audio for The Simpler Times.

All sounds are synthesized with numpy at runtime — no audio files, no
samples. PC-speaker bleeps, floppy drive whirr, disk-head seek, filtered
whispers, a low machine drone, and the entity's theme.

The generator functions are pure numpy (no pygame); AudioManager adapts
them to pygame.mixer.Sound.
"""
import numpy as np

SR = 22050

# --------------------------------------------------------------------------
# Pure numpy generators (return int16 mono arrays)
# --------------------------------------------------------------------------
def _env_decay(n, tau_samples):
    return np.exp(-np.arange(n) / float(tau_samples))


def _tone(freq, dur, shape="square", amp=0.5, decay=None, sr=SR):
    n = int(sr * dur)
    t = np.arange(n) / sr
    phase = 2 * np.pi * freq * t
    if shape == "square":
        wave = np.sign(np.sin(phase))
    elif shape == "sine":
        wave = np.sin(phase)
    elif shape == "saw":
        wave = 2.0 * ((freq * t) % 1.0) - 1.0
    else:
        wave = np.sin(phase)
    env = _env_decay(n, decay * sr) if decay else np.ones(n)
    return (wave * env * amp * 32767).astype(np.int16)


def _noise(dur, amp=0.5, decay=None, sr=SR, seed=None):
    rng = np.random.default_rng(seed)
    n = int(sr * dur)
    wave = rng.standard_normal(n)
    env = _env_decay(n, decay * sr) if decay else np.ones(n)
    return (wave * env * amp * 32767).astype(np.int16)


def _bandpass(x, lo, hi, sr=SR):
    """Cheap second-order Butterworth-ish bandpass via two biquad sweeps."""
    n = len(x)
    b, a = _biquad_band(lo, hi, sr)
    out = np.zeros(n)
    for i in range(n):
        out[i] = b[0] * x[i] + b[1] * (x[i - 1] if i else 0) + b[2] * (x[i - 2] if i >= 2 else 0) \
            - a[1] * (out[i - 1] if i else 0) - a[2] * (out[i - 2] if i >= 2 else 0)
    return out


def _biquad_band(lo, hi, sr):
    """RBJ cookbook peaking-filter-like bandpass coefficients."""
    w0 = 2 * np.pi * (lo * hi) ** 0.5 / sr
    bw = np.log2(hi / lo)
    alpha = np.sin(w0) * np.sinh(np.log(2) / 2 * bw * w0 / np.sin(w0))
    a0 = 1 + alpha
    a1 = -2 * np.cos(w0) / a0
    a2 = (1 - alpha) / a0
    b1 = alpha / a0 * 2 * np.cos(w0)
    b0 = alpha / a0
    b2 = -alpha / a0
    return (b0, b1, b2), (1.0, a1, a2)


def gen_beep(freq=880, dur=0.09, amp=0.4):
    return _tone(freq, dur, shape="square", amp=amp, decay=0.05)


def gen_bleep(freq=1200, dur=0.06, amp=0.3):
    return _tone(freq, dur, shape="sine", amp=amp, decay=0.03)


def gen_click(amp=0.5):
    return _noise(0.004, amp=amp, decay=0.002)


def gen_static_burst(dur=0.35, amp=0.6):
    return _noise(dur, amp=amp, decay=dur * 0.8)


def gen_write(dur=0.28, amp=0.5, sr=SR):
    """Disk head seek: two quick frequency sweeps, like a drive stepping."""
    n = int(sr * dur)
    t = np.arange(n) / sr
    steps = 6
    seg = n // steps
    wave = np.zeros(n)
    for s in range(steps):
        i0 = s * seg
        i1 = min(n, i0 + seg)
        tt = t[i0:i1]
        f0 = 140 + s * 40
        f1 = f0 + 160
        wave[i0:i1] = np.sign(np.sin(2 * np.pi * (f0 * tt + (f1 - f0) * tt * tt / (2 * (tt[-1] or 1)))))
    env = np.ones(n)
    env[:seg] = np.linspace(0.3, 1, seg)
    return (wave * env * amp * 32767).astype(np.int16)


def gen_whirr(dur=2.0, amp=0.35, sr=SR, seed=7):
    """Floppy drive spin: bandpass noise with a slow motor ripple."""
    n = int(sr * dur)
    t = np.arange(n) / sr
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(n)
    filtered = _bandpass(noise, 400, 900, sr)
    ripple = 0.5 + 0.5 * np.sin(2 * np.pi * 3.0 * t)      # motor tick
    head = 0.5 + 0.5 * np.sin(2 * np.pi * 0.7 * t)        # slow wobble
    wave = filtered * ripple * head * amp
    return (wave * 32767).astype(np.int16)


def gen_heartbeat(dur=0.9, amp=0.55, sr=SR):
    """Two low thumps: lub-dub at ~55 Hz."""
    n = int(sr * dur)
    t = np.arange(n) / sr
    wave = np.zeros(n)
    for start, tau, f in ((0.0, 0.05, 55.0), (0.32, 0.04, 50.0)):
        i0 = int(sr * start)
        i1 = min(n, i0 + int(sr * 0.4))
        tt = t[i0:i1] - start
        seg = np.sin(2 * np.pi * f * tt) * np.exp(-tt / tau)
        wave[i0:i1] += seg
    return (wave * amp * 32767).astype(np.int16)


def gen_whisper(dur=1.6, amp=0.30, sr=SR, seed=11):
    """Filtered noise shaped like a breathy voice saying nothing."""
    n = int(sr * dur)
    t = np.arange(n) / sr
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(n)
    filtered = _bandpass(noise, 800, 2200, sr)
    # formant-ish flutter
    form = (0.6 + 0.4 * np.sin(2 * np.pi * 4.5 * t)) * \
           (0.7 + 0.3 * np.sin(2 * np.pi * 1.7 * t + 0.6))
    attack = np.minimum(1.0, t / 0.12)
    release = np.minimum(1.0, (dur - t) / 0.25)
    wave = filtered * form * attack * release * amp
    return (wave * 32767).astype(np.int16)


def gen_drone(dur=4.0, amp=0.18, sr=SR, seed=3):
    """Low machine hum (looped ambience): 55 + 82.5 Hz with slow tremolo."""
    n = int(sr * dur)
    t = np.arange(n) / sr
    rng = np.random.default_rng(seed)
    trem = 0.75 + 0.25 * np.sin(2 * np.pi * 0.2 * t)
    hum = (np.sin(2 * np.pi * 55 * t) + 0.6 * np.sin(2 * np.pi * 82.5 * t)
           + 0.2 * rng.standard_normal(n) * 0.02)
    wave = hum * trem * amp
    return (wave * 32767).astype(np.int16)


def gen_dialtone(dur=0.6, amp=0.30, sr=SR):
    """North-American dial tone: 350 Hz + 440 Hz."""
    n = int(sr * dur)
    t = np.arange(n) / sr
    wave = 0.5 * (np.sin(2 * np.pi * 350 * t) + np.sin(2 * np.pi * 440 * t))
    env = np.minimum(1.0, t / 0.02)
    return (wave * env * amp * 32767).astype(np.int16)


def gen_dial(dur=2.2, amp=0.35, sr=SR):
    """Rotary pulse dialing: 10 short on-off blips (old phone)."""
    n = int(sr * dur)
    wave = np.zeros(n)
    steps = 10
    seg = n // (steps * 2)
    for s in range(steps):
        i0 = (2 * s) * seg
        i1 = min(n, i0 + seg)
        tt = np.arange(i1 - i0) / sr
        wave[i0:i1] = np.sin(2 * np.pi * 900 * tt) * 0.6
    return (wave * amp * 32767).astype(np.int16)


def gen_modem(dur=5.0, amp=0.35, sr=SR, seed=23):
    """2400-baud modem handshake: chirps, hiss, squeal."""
    n = int(sr * dur)
    t = np.arange(n) / sr
    rng = np.random.default_rng(seed)
    hiss = _bandpass(rng.standard_normal(n), 900, 2400, sr)
    segments = ((0.0, 1.2, 2100.0), (1.2, 2.3, 1200.0), (2.3, 3.4, 980.0))
    wave = np.zeros(n)
    for start, end, f in segments:
        i0, i1 = int(sr * start), min(n, int(sr * end))
        tt = t[i0:i1] - t[i0]
        env = np.sin(np.pi * np.linspace(0, 1, i1 - i0)) ** 0.8
        wave[i0:i1] += np.sin(2 * np.pi * f * tt) * env * 0.5
    ring = 0.5 + 0.5 * np.sin(2 * np.pi * 0.9 * t)
    out = (wave + hiss * 0.6 * ring) * amp
    return (out * 32767).astype(np.int16)


def gen_format(dur=2.0, amp=0.35, sr=SR):
    """Formatting sweep: descending heads with clicks (horror FORMAT)."""
    n = int(sr * dur)
    t = np.arange(n) / sr
    steps = 14
    seg = n // steps
    wave = np.zeros(n)
    for s in range(steps):
        i0 = s * seg
        i1 = min(n, i0 + seg)
        tt = t[i0:i1] - t[i0]
        f = 900 * (1.0 - s / steps)
        wave[i0:i1] = np.sign(np.sin(2 * np.pi * f * tt)) * 0.5
    clicks = np.zeros(n)
    for s in range(steps):
        i = min(n - 1, s * seg)
        clicks[i:i + int(sr * 0.01)] = 1.0
    return ((wave * 0.7 + clicks * 0.5) * amp * 32767).astype(np.int16)


def gen_boom(dur=1.4, amp=0.5, sr=SR):
    """Power-down: descending 100 Hz thump into silence."""
    n = int(sr * dur)
    t = np.arange(n) / sr
    f = 110 * np.exp(-t * 1.4)
    wave = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t * 2.6)
    return (wave * amp * 32767).astype(np.int16)


def gen_panic(dur=1.8, amp=0.4, sr=SR):
    """Alarm: two fast beeps repeating (error warning)."""
    n = int(sr * dur)
    t = np.arange(n) / sr
    wave = np.zeros(n)
    for start in (0.0, 0.18, 0.55, 0.73, 1.10, 1.28):
        i0 = int(sr * start)
        i1 = min(n, i0 + int(sr * 0.16))
        tt = t[i0:i1] - t[i0]
        wave[i0:i1] = np.sin(2 * np.pi * 620 * tt) * 0.6
    return (wave * amp * 32767).astype(np.int16)


def gen_theme(dur=6.0, amp=0.30, sr=SR):
    """The entity's theme: slow Am-F-C-G pad, loopable."""
    n = int(sr * dur)
    t = np.arange(n) / sr
    seg = n // 4
    freqs = (220.0, 174.61, 261.63, 196.0)   # A3 F3 C4 G3
    wave = np.zeros(n)
    for i, f in enumerate(freqs):
        i0 = i * seg
        i1 = min(n, i0 + seg)
        tt = t[i0:i1] - t[i0]
        segw = np.sin(2 * np.pi * f * tt) + 0.5 * np.sin(2 * np.pi * 2 * f * tt)
        env = np.sin(np.pi * np.linspace(0, 1, i1 - i0)) ** 0.7
        wave[i0:i1] += segw * env
    wave = wave / 1.5 * amp
    return (wave * 32767).astype(np.int16)


def gen_type(amp=0.6, sr=SR):
    """Single keyboard strike: a short sharp noise click (for ghost typing)."""
    return _noise(0.018, amp=amp, decay=0.006)


def gen_thud(dur=0.4, amp=0.6, sr=SR):
    """Heavy soft door/floor thud: a descending low thump."""
    n = int(sr * dur)
    t = np.arange(n) / sr
    f = 95 * np.exp(-t * 3.0) + 30
    wave = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t * 4.5)
    return (wave * amp * 32767).astype(np.int16)


def gen_knock(dur=1.1, amp=0.55, sr=SR, seed=17):
    """Three slow knocks on wood: 140 Hz bursts with a soft body."""
    n = int(sr * dur)
    t = np.arange(n) / sr
    rng = np.random.default_rng(seed)
    wave = np.zeros(n)
    body = _bandpass(rng.standard_normal(n) * 0.4, 120, 380, sr)
    for start in (0.0, 0.38, 0.76):
        i0 = int(sr * start)
        i1 = min(n, i0 + int(sr * 0.14))
        tt = t[i0:i1] - t[i0]
        wave[i0:i1] += np.sin(2 * np.pi * 140 * tt) * np.exp(-tt / 0.03)
    return ((wave + body * 0.5) * amp * 32767).astype(np.int16)


def gen_breath(dur=4.0, amp=0.30, sr=SR, seed=19):
    """Slow breathing loop: breathy filtered noise swelling in and out."""
    n = int(sr * dur)
    t = np.arange(n) / sr
    rng = np.random.default_rng(seed)
    noise = _bandpass(rng.standard_normal(n), 500, 1100, sr)
    env = np.minimum(1.0, np.maximum(0.0, np.sin(
        2 * np.pi * 0.21 * t - np.pi / 2)) ** 3 * 1.6)
    wave = noise * env * amp
    return (wave * 32767).astype(np.int16)


def gen_tick(dur=0.045, amp=0.5, sr=SR):
    """Clock tick: a bright 2 kHz blip."""
    return _tone(2000, dur, shape="square", amp=amp, decay=dur * 0.6)


def gen_buzz(dur=4.0, amp=0.22, sr=SR, seed=29):
    """Fluorescent tube buzz: 100/120 Hz hum with faint hiss, loopable."""
    n = int(sr * dur)
    t = np.arange(n) / sr
    rng = np.random.default_rng(seed)
    ripple = 0.8 + 0.2 * np.sin(2 * np.pi * 100 * t)
    hum = np.sin(2 * np.pi * 100 * t) + 0.5 * np.sin(2 * np.pi * 120 * t)
    hiss = _bandpass(rng.standard_normal(n), 3000, 7000, sr) * 0.15
    wave = (hum * 0.8 + hiss) * ripple * amp
    return (wave * 32767).astype(np.int16)


def gen_murmur(dur=4.0, amp=0.20, sr=SR, seed=31):
    """Distant hall murmur: low band noise with a slow random swell, loopable."""
    n = int(sr * dur)
    t = np.arange(n) / sr
    rng = np.random.default_rng(seed)
    noise = _bandpass(rng.standard_normal(n), 200, 700, sr)
    swell = 0.6 + 0.4 * np.sin(2 * np.pi * 0.13 * t + rng.uniform(0, 6.28))
    wave = noise * swell * amp
    return (wave * 32767).astype(np.int16)


def gen_creak(dur=0.9, amp=0.40, sr=SR, seed=37):
    """A slow floor/door creak: rising glide with noise."""
    n = int(sr * dur)
    t = np.arange(n) / sr
    rng = np.random.default_rng(seed)
    f = 90 + 160 * t
    tone = np.sin(2 * np.pi * np.cumsum(f) / sr)
    hiss = _bandpass(rng.standard_normal(n), 500, 1600, sr) * 0.4
    env = np.sin(np.pi * np.minimum(1.0, t / dur)) ** 1.5
    wave = (tone * 0.7 + hiss) * env * amp
    return (wave * 32767).astype(np.int16)


# --------------------------------------------------------------------------
# pygame adapter
# --------------------------------------------------------------------------
class AudioManager:
    NAMES = ("beep", "bleep", "click", "static_burst", "write", "whirr",
             "heartbeat", "whisper", "drone", "theme",
             "dialtone", "dial", "modem", "format", "boom", "panic",
             "type", "thud", "knock", "breath", "tick", "buzz", "murmur",
             "creak")

    def __init__(self, sample_rate=SR):
        import pygame
        self.sample_rate = sample_rate
        self._sounds = {}
        self._loops = {}
        self._ok = False
        try:
            pygame.mixer.quit()
            for buf in (512, 1024, 2048):
                try:
                    pygame.mixer.init(frequency=sample_rate, size=-16,
                                      channels=1, buffer=buf)
                    break
                except pygame.error:
                    continue
            else:
                pygame.mixer.init()
            self._ok = pygame.mixer.get_init() is not None
        except Exception:
            self._ok = False

    @property
    def ok(self):
        return self._ok

    @staticmethod
    def _to_mixer_format(arr):
        """Resample/remix a 22050 Hz mono int16 array to whatever format the
        mixer actually opened with, so sound plays (not silence) even when
        the preferred init failed and SDL fell back to its defaults."""
        import pygame
        init = pygame.mixer.get_init()
        freq = init[0]
        channels = init[2]
        if freq != SR:
            n = int(len(arr) * freq / SR)
            idx = np.linspace(0, len(arr) - 1, n).astype(np.int64)
            arr = arr[idx]
        if channels == 2:
            arr = np.repeat(arr[:, None], 2, axis=1)
        return arr.astype(np.int16).tobytes()

    def build(self):
        if not self._ok:
            return
        gens = {
            "beep": gen_beep(), "bleep": gen_bleep(),
            "click": gen_click(), "static_burst": gen_static_burst(),
            "write": gen_write(), "whirr": gen_whirr(),
            "heartbeat": gen_heartbeat(), "whisper": gen_whisper(),
            "drone": gen_drone(), "theme": gen_theme(),
            "dialtone": gen_dialtone(), "dial": gen_dial(),
            "modem": gen_modem(), "format": gen_format(),
            "boom": gen_boom(), "panic": gen_panic(),
            "type": gen_type(), "thud": gen_thud(), "knock": gen_knock(),
            "breath": gen_breath(), "tick": gen_tick(),
            "buzz": gen_buzz(), "murmur": gen_murmur(),
            "creak": gen_creak(),
        }
        import pygame
        for name, arr in gens.items():
            self._sounds[name] = pygame.mixer.Sound(
                buffer=self._to_mixer_format(arr))

    def play(self, name, volume=1.0):
        if not self._ok:
            return
        s = self._sounds.get(name)
        if s:
            s.set_volume(max(0.0, min(1.0, volume)))
            s.play()

    def start_loop(self, name, volume=1.0):
        if not self._ok:
            return
        if name in self._loops:
            return
        s = self._sounds.get(name)
        if s:
            s.set_volume(max(0.0, min(1.0, volume)))
            s.play(-1)
            self._loops[name] = s

    def stop_loop(self, name):
        if not self._ok:
            return
        s = self._loops.pop(name, None)
        if s:
            s.stop()

    def stop_all_loops(self):
        for name in list(self._loops):
            self.stop_loop(name)

    def set_loop_volume(self, name, volume):
        if not self._ok:
            return
        s = self._loops.get(name)
        if s:
            s.set_volume(max(0.0, min(1.0, volume)))
