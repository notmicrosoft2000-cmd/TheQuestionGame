"""Rendering helpers for The Simpler Times — amber CRT terminal UI.

Provides fonts, scanlines, vignette, static, glitch, glow text, wrapped
typewriter drawing, terminal panels, and prompts. All overlays are cached
and rebuilt only when the window size changes.
"""
import math
import random

import numpy as np
import pygame

from . import config

# --------------------------------------------------------------------------
# Fonts
# --------------------------------------------------------------------------
_FONT_PATH = None
_FONT_CACHE = {}
_TEXT_SCALE = 1.0


def _font_path():
    global _FONT_PATH
    if _FONT_PATH is None:
        try:
            _FONT_PATH = pygame.font.match_font("courier")
        except Exception:
            _FONT_PATH = None
    return _FONT_PATH


def get_font(size):
    """Return a cached monospace Font for the given pixel height, scaled by
    the player's Text Size setting."""
    key = int(size * _TEXT_SCALE)
    if key not in _FONT_CACHE:
        try:
            _FONT_CACHE[key] = pygame.font.Font(_font_path(), key)
        except Exception:
            _FONT_CACHE[key] = pygame.font.Font(None, key)
    return _FONT_CACHE[key]


def set_text_scale(v):
    """Set the global font-size multiplier (the Text Size setting)."""
    global _TEXT_SCALE
    _TEXT_SCALE = max(0.5, min(2.0, float(v)))


def text_scale():
    return _TEXT_SCALE


def clear_font_cache():
    _FONT_CACHE.clear()


def scale_for(h):
    """Font size scale relative to the 480px reference window height."""
    return max(0.5, h / 480.0)


# --------------------------------------------------------------------------
# Text layout
# --------------------------------------------------------------------------
def word_wrap(text, font, max_width):
    """Split text into wrapped lines fitting max_width (in pixels)."""
    lines = []
    for raw in text.split("\n"):
        words = raw.split(" ")
        cur = ""
        for w in words:
            trial = (cur + " " + w).strip()
            if font.size(trial)[0] <= max_width:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


def draw_wrapped(screen, text, font, color, rect, elapsed=None,
                 chars_per_sec=60, x_off=0, y_off=0, line_spacing=None,
                 sway=0, sway_t=0.0):
    """Draw wrapped text inside rect. If elapsed is not None, reveal it
    typewriter-style. If sway > 0, each line drifts with sin/cos waves like
    the original THE QUESTION GAME (with a soft alpha pulse). Returns True
    once fully revealed."""
    lines = word_wrap(text, font, rect.width)
    spacing = line_spacing or font.get_linesize()
    total_chars = sum(len(l) for l in lines)
    if elapsed is None:
        shown = total_chars
    else:
        shown = min(total_chars, max(0, int(elapsed * chars_per_sec)))

    y = rect.top + y_off
    count = 0
    for i, ln in enumerate(lines):
        surf = font.render(ln, True, color)
        if sway:
            dx = int(math.sin(sway_t * 0.8 + i * 0.6) * sway)
            dy = int(math.cos(sway_t * 1.2 + i * 0.4) * sway * 0.4)
            try:
                surf.set_alpha(int(165 + 55 * (0.5 + 0.5 * math.sin(
                    sway_t * 1.2 + i * 0.9))))
            except Exception:
                pass
        else:
            dx = dy = 0
        x = rect.left + x_off + dx
        yy = y + dy
        if count + len(ln) <= shown:
            screen.blit(surf, (x, yy))
        else:
            rem = max(0, shown - count)
            if rem > 0:
                w = sum(font.size(ch)[0] for ch in ln[:rem])
                screen.blit(surf, (x, yy), area=(0, 0, w, surf.get_height()))
        count += len(ln)
        y += spacing
    return shown >= total_chars


def draw_centered(screen, surf, cy=None):
    """Blit a surface horizontally centered; optionally pin its top at cy."""
    x = (screen.get_width() - surf.get_width()) // 2
    y = cy if cy is not None else (screen.get_height() - surf.get_height()) // 2
    screen.blit(surf, (x, y))


# --------------------------------------------------------------------------
# Glow text
# --------------------------------------------------------------------------
def render_glow_text(text, font, color, glow_color):
    """Render text over a soft multi-offset glow."""
    base = font.render(text, True, color)
    glow = font.render(text, True, glow_color)
    out = pygame.Surface((base.get_width() + 10, base.get_height() + 10), pygame.SRCALPHA)
    for dx, dy in ((-2, -2), (2, -2), (-2, 2), (2, 2), (0, -3), (0, 3), (-3, 0), (3, 0)):
        out.blit(glow, (5 + dx, 5 + dy))
    out.blit(base, (5, 5))
    return out


# --------------------------------------------------------------------------
# Terminal panel
# --------------------------------------------------------------------------
def draw_terminal_panel(screen, rect, title=None, border=config.LINE,
                        fill=config.PANEL, title_color=None):
    """A bordered amber terminal panel with an optional header title."""
    if fill is not None:
        screen.fill(fill, rect)
    pygame.draw.rect(screen, border, rect, 1)
    if title:
        tf = get_font(max(12, int(13 * scale_for(screen.get_height()))))
        tsurf = tf.render(" " + title + " ", True, title_color or config.DIM)
        bx = rect.right - tsurf.get_width() - 8
        screen.blit(tsurf, (bx, rect.top - tsurf.get_height() // 2 + 1))


# --------------------------------------------------------------------------
# Prompt line + caret
# --------------------------------------------------------------------------
def draw_prompt(screen, font, x, y, prefix, value, show_caret,
                color=config.TEXT, caret_color=config.TEXT_BRIGHT):
    """Draw a DOS-style 'prefix' + 'value' line with a blinking block caret."""
    p = font.render(prefix, True, color)
    v = font.render(value, True, config.TEXT_BRIGHT)
    screen.blit(p, (x, y))
    vx = x + p.get_width()
    screen.blit(v, (vx, y))
    if show_caret:
        cx = vx + v.get_width()
        pygame.draw.rect(screen, caret_color, (cx, y, font.size(" ")[0] - 2, v.get_height()))


# --------------------------------------------------------------------------
# CRT overlays (cached per window size)
# --------------------------------------------------------------------------
_SCAN_CACHE = {}
_VIGNETTE_CACHE = {}
_ALPHA_CACHE = {}


def _note_size(size):
    key = size
    if key not in _SCAN_CACHE:
        w, h = size
        scan = pygame.Surface(size, pygame.SRCALPHA)
        for y in range(0, h, 3):
            pygame.draw.line(scan, (0, 0, 0, 70), (0, y), (w, y))
        _SCAN_CACHE[key] = scan

        cx, cy = w / 2.0, h / 2.0
        maxd = (cx * cx + cy * cy) ** 0.5
        yy = np.arange(h)[:, None]
        xx = np.arange(w)[None, :]
        dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        alpha = (np.minimum(1.0, (dist / maxd) ** 2.2) * 120).astype(np.uint8)
        rows = np.zeros((h, w, 4), dtype=np.uint8)
        rows[:, :, 3] = alpha
        vig = pygame.image.frombuffer(rows.tobytes(), size, "RGBA")
        try:
            vig = vig.convert_alpha()  # display-native format: 0.6ms vs 50ms blit
        except pygame.error:
            pass
        _VIGNETTE_CACHE[key] = vig
    return _SCAN_CACHE[size], _VIGNETTE_CACHE[size]


def _alpha_copy(surf, alpha_int):
    """A cached copy of surf with surface-alpha baked in, so per-frame
    set_alpha() conversion thrash (slow on per-pixel-alpha surfaces) is
    avoided."""
    key = (id(surf), alpha_int)
    out = _ALPHA_CACHE.get(key)
    if out is None:
        out = surf.copy()
        out.set_alpha(alpha_int)
        _ALPHA_CACHE[key] = out
    return out


def draw_scanlines(screen, intensity=1.0):
    if intensity <= 0:
        return
    scan, _ = _note_size(screen.get_size())
    if intensity >= 1.0:
        screen.blit(scan, (0, 0))
    else:
        screen.blit(_alpha_copy(scan, int(255 * intensity)), (0, 0))


def draw_vignette(screen, intensity=1.0):
    if intensity <= 0:
        return
    _, vig = _note_size(screen.get_size())
    if intensity >= 1.0:
        screen.blit(vig, (0, 0))
    else:
        screen.blit(_alpha_copy(vig, int(255 * intensity)), (0, 0))


def draw_static(screen, intensity=1.0):
    """Monochrome TV static over the whole screen."""
    if intensity <= 0:
        return
    w, h = screen.get_size()
    sw, sh = max(16, w // 4), max(16, h // 4)
    noise = (np.random.randint(0, 256, (sh, sw, 3))).astype(np.uint8)
    try:
        surf = pygame.image.frombuffer(noise.tobytes(), (sw, sh), "RGB")
        surf = pygame.transform.smoothscale(surf, (w, h))
    except Exception:
        return
    surf.set_alpha(int(255 * min(1.0, intensity)))
    screen.blit(surf, (0, 0))
    surf.set_alpha(255)


def draw_glitch(screen, count=3, amount=24):
    """Draw random horizontal slice distortions (CRT roll)."""
    w, h = screen.get_size()
    for _ in range(count):
        y = random.randint(0, max(0, h - 12))
        sh = random.randint(2, 12)
        dx = random.randint(-amount, amount)
        if y + sh > h:
            continue
        if dx:
            slice_surf = screen.subsurface((0, y, w, sh)).copy()
            screen.blit(slice_surf, (dx, y))
    return random.random() < 0.25  # sometimes draw an inverse band


# --------------------------------------------------------------------------
# VHS static (driven by the VHS Static setting)
# --------------------------------------------------------------------------
_VHS_CACHE = {}


def _vhs_overlay(size):
    """A cached overlay of faint horizontal roll lines."""
    key = size
    ov = _VHS_CACHE.get(key)
    if ov is None:
        w, h = size
        ov = pygame.Surface(size, pygame.SRCALPHA)
        for y in range(0, h, 4):
            pygame.draw.line(ov, (0, 0, 0, 46), (0, y), (w, y))
        _VHS_CACHE[key] = ov
    return ov


def draw_vhs(screen, intensity, t):
    """VHS-era artifacts: a sweeping scan band, roll lines, and glitch bars.
    intensity: 0.0 = off; 1.0 = the default look; higher = more noise."""
    if intensity <= 0:
        return
    w, h = screen.get_size()
    k = min(1.0, intensity)
    screen.blit(_alpha_copy(_vhs_overlay((w, h)), int(200 * k)), (0, 0))

    bh = max(3, int(24 * k))
    by = int((t * 130) % (h + bh)) - bh
    pygame.draw.rect(screen, config.TEXT, (0, by, w, bh))

    if random.random() < 0.55 * intensity:
        gy = random.randint(0, max(0, h - 12))
        gh = random.randint(2, max(3, int(10 * k)))
        screen.fill((0, 0, 0), (0, gy, w, gh))
    if random.random() < 0.35 * intensity:
        sy = random.randint(0, h - 1)
        pygame.draw.line(screen, config.TEXT_BRIGHT, (0, sy), (w, sy))
    if intensity >= 1.4 and random.random() < 0.08:
        gy = random.randint(0, h - 8)
        screen.fill((30, 0, 0), (0, gy, w, random.randint(2, 8)))


# --------------------------------------------------------------------------
# Text corruption (for scares / the entity editing files)
# --------------------------------------------------------------------------
_CORRUPT_CHARS = "█▓▒░#@%&?¡!<>/\\~*"

def corrupt_line(line, chance=0.08, rng=None):
    """Replace characters in a line with glyphs to fake file corruption."""
    r = rng or random
    out = []
    for ch in line:
        if r.random() < chance:
            out.append(r.choice(_CORRUPT_CHARS))
        else:
            out.append(ch)
    return "".join(out)


# --------------------------------------------------------------------------
# Fade overlay
# --------------------------------------------------------------------------
def draw_fade(screen, alpha):
    if alpha <= 0:
        return
    ov = pygame.Surface(screen.get_size())
    ov.set_alpha(min(255, max(0, int(alpha))))
    ov.fill((0, 0, 0))
    screen.blit(ov, (0, 0))
