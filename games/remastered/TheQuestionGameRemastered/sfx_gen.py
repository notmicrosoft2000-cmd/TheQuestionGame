"""Procedural sound generation, written out to real audio files.

On first run the game renders every sound effect (and a low ambience bed) as an
actual file under `assets/`, then plays those files from then on. This keeps the
shipped build light while giving the game a real, inspectable, replaceable sound
folder — drop your own `assets/error.mp3` in and it is used instead.

Writes MP3 when an encoder is available (ffmpeg), otherwise WAV. The generators
themselves are pure numpy and never import the mixer, so this module can run
without an audio device.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import wave

import numpy as np

SAMPLE_RATE = 22050

# name -> (duration seconds, generator)
SOUND_SPECS = {
    "type":        (0.015, "type"),
    "ui_nav":      (0.030, "nav"),
    "ui_select":   (0.080, "select"),
    "mech_beep":   (0.120, "beep"),
    "error":       (0.200, "error"),
    "glitch":      (0.120, "glitch"),
    "static_burst": (0.250, "static"),
    "heartbeat":   (0.180, "heartbeat"),
    "deep_rumble": (0.800, "rumble"),
    "reverse_chord": (1.200, "chord"),
    "static_scream": (0.350, "scream"),
    "ambience":    (4.000, "ambience"),
}


def _t(dur):
    return np.linspace(0.0, dur, max(1, int(SAMPLE_RATE * dur)), False)


def _env_ar(n, attack=0.01, release=0.4):
    a = max(1, int(n * attack))
    r = max(1, int(n * release))
    env = np.ones(n)
    env[:a] = np.linspace(0.0, 1.0, a)
    env[n - r:] = np.linspace(1.0, 0.0, r)
    return env


def _gen(kind, dur):
    rng = np.random.default_rng(abs(hash(kind)) % (2 ** 32))
    t = _t(dur)

    if kind == "type":
        buf = np.zeros(len(t))
        for i in range(len(buf)):
            buf[i] = rng.choice([-8000.0, 8000.0])
        return buf

    if kind == "nav":
        return np.sin(2 * np.pi * 600 * t) * 8000 * _env_ar(len(t), 0.05, 0.5)

    if kind == "select":
        return np.sin(2 * np.pi * 880 * t) * 12000 * _env_ar(len(t), 0.03, 0.6)

    if kind == "beep":
        return np.sin(2 * np.pi * 1200 * t) * 14000 * _env_ar(len(t), 0.02, 0.6)

    if kind == "error":
        wave = np.sin(2 * np.pi * 150 * t) + np.sin(2 * np.pi * 155 * t)
        return np.clip(wave, -1, 1) * 18000 * _env_ar(len(t), 0.02, 0.35)

    if kind == "glitch":
        freq = rng.uniform(300, 2200)
        wave = np.sin(2 * np.pi * freq * t)
        noise = rng.normal(0, 0.4, len(t))
        return np.clip(wave * 0.6 + noise * 0.4, -1, 1) * 16000 * _env_ar(len(t), 0.02, 0.4)

    if kind == "static":
        return np.clip(rng.normal(0, 1.0, len(t)), -1, 1) * 9000 * _env_ar(len(t), 0.02, 0.5)

    if kind == "heartbeat":
        env = np.exp(-t * 25)
        return np.clip(np.sin(2 * np.pi * 55 * t) * env, -1, 1) * 28000

    if kind == "rumble":
        freq = np.linspace(80, 40, len(t))
        wave = np.sin(2 * np.pi * freq * t)
        noise = rng.normal(0, 0.25, len(t))
        combined = np.clip(wave * 0.7 + noise * 0.3, -1, 1)
        return combined * np.exp(-t * 1.2) * 22000

    if kind == "chord":
        env = np.linspace(0, 1, len(t)) ** 2
        freqs = [220, 277, 330, 370]
        wave = sum(np.sin(2 * np.pi * f * t) for f in freqs) / len(freqs)
        return np.clip(wave * env, -1, 1) * 14000

    if kind == "scream":
        freq = np.linspace(400, 3200, len(t))
        wave = np.sin(2 * np.pi * freq * t)
        noise = rng.normal(0, 0.6, len(t))
        env = np.exp(-t * 6)
        return np.clip(wave * 0.5 + noise * 0.5, -1, 1) * env * 20000

    if kind == "ambience":
        # A slow, breathing low drone with a faint tape hiss under it.
        drone = np.sin(2 * np.pi * 50 * t) * 0.5
        drone += np.sin(2 * np.pi * 50.7 * t) * 0.25
        lfo = 0.8 + 0.2 * np.sin(2 * np.pi * 0.13 * t)
        hiss = rng.normal(0, 0.03, len(t))
        return (drone * lfo + hiss) * 12000

    return np.zeros(len(t))


def _to_int16(samples):
    return np.clip(samples, -32768, 32767).astype(np.int16)


def _write_wav(path, samples):
    data = _to_int16(samples)
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        f.writeframes(data.tobytes())
    return path


def _to_wav_16bit_44100(samples):
    """The mixer runs at 44.1k stereo; resample mono 22.05k -> that, for raw use."""
    data = np.clip(samples, -32768, 32767).astype(np.int16)
    if data.size > 1:
        up = np.interp(
            np.linspace(0.0, 1.0, data.size * 2, endpoint=False),
            np.linspace(0.0, 1.0, data.size, endpoint=False),
            data.astype(np.float32),
        ).astype(np.int16)
        data = up
    return np.repeat(data, 2)  # duplicate to stereo


def _encode(src_wav, dst):
    """Transcode a wav to `dst` (mp3/ogg) with whatever encoder exists."""
    ext = os.path.splitext(dst)[1].lower()
    if ext == ".wav":
        shutil.move(src_wav, dst)
        return dst
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        try:
            codec = {"mp3": ["-b:a", "64k"], "ogg": ["-q:a", "3"]}.get(ext.lstrip("."), [])
            r = subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", src_wav] + codec + [dst],
                               capture_output=True, timeout=30)
            if r.returncode == 0 and os.path.exists(dst):
                try:
                    os.remove(src_wav)
                except OSError:
                    pass
                return dst
        except Exception:
            pass
    try:
        import soundfile as sf
        if ext in (".ogg", ".flac", ".wav"):
            data, sr = sf.read(src_wav)
            sf.write(dst, data, sr)
            os.remove(src_wav)
            return dst
    except Exception:
        pass
    # Nothing could transcode it — ship the wav under the intended name.
    shutil.move(src_wav, dst)
    return dst


def _preferred_ext():
    ordered = [".mp3", ".ogg", ".wav"]
    if shutil.which("ffmpeg"):
        return ".mp3"
    try:
        import soundfile as sf  # noqa: F401
        return ".ogg"
    except Exception:
        return ".wav"


def _find_existing(assets_dir, name, allowed):
    for ext in (".mp3", ".ogg", ".wav"):
        if ext not in allowed:
            continue
        p = os.path.join(assets_dir, name + ext)
        if os.path.exists(p) and os.path.getsize(p) > 128:
            return p
    return None


def ensure_assets(assets_dir, names=None, force=False):
    """Make sure every sound exists on disk. Returns {name: path}.

    Existing files are never overwritten (that is the whole point — they are
    user-replaceable), unless `force` is set.
    """
    asked = names or list(SOUND_SPECS)
    ext = _preferred_ext()
    allowed = {".mp3", ".ogg", ".wav"}
    out = {}
    try:
        os.makedirs(assets_dir, exist_ok=True)
    except OSError:
        return out
    for name in asked:
        spec = SOUND_SPECS.get(name)
        if not spec:
            continue
        if not force:
            found = _find_existing(assets_dir, name, allowed)
            if found and found.lower().endswith(ext):
                out[name] = found
                continue
        dur, kind = spec
        tmp_wav = os.path.join(assets_dir, "_%s_tmp.wav" % name)
        try:
            samples = _gen(kind, dur)
            _write_wav(tmp_wav, samples)
            target = os.path.join(assets_dir, name + ext)
            out[name] = _encode(tmp_wav, target)
        except Exception:
            if os.path.exists(tmp_wav):
                try:
                    os.remove(tmp_wav)
                except OSError:
                    pass
            fallback = _find_existing(assets_dir, name, allowed)
            if fallback:
                out[name] = fallback
    return out


if __name__ == "__main__":  # manual: python -m TheQuestionGameRemastered.sfx_gen
    here = os.path.dirname(os.path.abspath(__file__))
    target = os.path.join(here, "assets")
    made = ensure_assets(target, force="--force" in sys.argv)
    for k in sorted(made):
        print("%-14s %s" % (k, made[k]))
